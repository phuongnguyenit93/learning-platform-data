# getTransaction có thể tạo mới hoặc tham gia giao dịch

## 1. Điều quan trọng nhất: getTransaction không đồng nghĩa luôn BEGIN mới

Trong Spring Framework, `PlatformTransactionManager` cung cấp API lập trình trực tiếp:

~~~java
TransactionStatus status =
    transactionManager.getTransaction(transactionDefinition);
~~~

`getTransaction(...)` **không mặc định tạo một physical transaction mới trong mọi lần gọi**. Kết quả phụ thuộc **`TransactionDefinition`**, nhất là `propagation`, và trạng thái **transaction đang tồn tại** tại thời điểm lời gọi:

- Khi dùng `PROPAGATION_REQUIRED` và **chưa có transaction tương thích**, manager **mở một transaction mới**. `status.isNewTransaction()` thường là `true`.
- Khi dùng `PROPAGATION_REQUIRED` và **đã có transaction tương thích**, manager cho logical scope bên trong **tham gia physical transaction hiện tại**. `status.isNewTransaction()` thường là `false`.
- Khi dùng `PROPAGATION_REQUIRES_NEW`, manager yêu cầu physical transaction mới; khi đã có outer, resource/transaction ngoài được **tạm đình chỉ** theo khả năng của manager.
- Khi dùng `PROPAGATION_NESTED`, nếu có outer và manager hỗ trợ savepoint, inner thường dùng **cùng physical transaction và một savepoint**; khi không có outer, nó mở transaction mới.
- Với `SUPPORTS`/`NOT_SUPPORTED`, `getTransaction` thậm chí có thể trả về một logical status **không có physical transaction mới**.
- Với `MANDATORY` hoặc `NEVER`, cấu hình không phù hợp với việc có/không có outer transaction có thể bị từ chối bằng `IllegalTransactionStateException`.

Cách hiểu chính xác là: **`getTransaction` giải quyết yêu cầu propagation**, không chỉ thực hiện một lệnh “BEGIN” vô điều kiện.

### Vì sao bài này quan trọng?

Nếu code gọi `getTransaction` bên trong một transaction đang tồn tại mà tưởng đã tạo transaction độc lập, việc gọi `commit(innerStatus)` dễ bị hiểu sai là “đã lưu dữ liệu ngay”, trong khi thực tế inner `REQUIRED` chỉ **kết thúc logical scope** và commit vật lý vẫn thuộc outer. Ngược lại, `rollback(innerStatus)` của một participant có thể đánh dấu **toàn transaction chung rollback-only**, khiến outer không commit được dù đã bắt lỗi.

Để không đoán, ta sẽ dùng `TransactionStatus.isNewTransaction()`, `hasSavepoint()`, `TransactionSynchronizationManager.isActualTransactionActive()` và phép thử đọc lại dữ liệu H2.

## 2. Ba phần trong API giao dịch trực tiếp

### 2.1. TransactionDefinition: yêu cầu bạn gửi vào

`TransactionDefinition` mô tả transaction cần được tạo/tham gia. Có thể cấu hình bằng `DefaultTransactionDefinition`:

~~~java
DefaultTransactionDefinition definition =
    new DefaultTransactionDefinition();
definition.setName("create-order");
definition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
definition.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
definition.setTimeout(15);
definition.setReadOnly(false);

TransactionStatus status =
    transactionManager.getTransaction(definition);
~~~

Đây là **mảnh code minh họa**, yêu cầu một `PlatformTransactionManager` đã được khởi tạo; code hoàn chỉnh ở phần 6.

Các thuộc tính cần nhận biết:

| Thuộc tính | Ý nghĩa | Lưu ý khi transaction đã tồn tại |
| --- | --- | --- |
| `propagationBehavior` | Mở mới, tham gia, suspend, savepoint, hoặc yêu cầu có/không có transaction | Đây là **yếu tố đầu tiên** quyết định số lượng physical transactions. |
| `isolationLevel` | Mức cô lập mong muốn | Thường chỉ áp khi **bắt đầu transaction mới** và manager/DB hỗ trợ; inner REQUIRED không tự ghi đè outer. |
| `timeout` | Giới hạn thời gian transaction, đơn vị giây | Inner participant không reset deadline của transaction vật lý ngoài. |
| `readOnly` | Hint/thuộc tính về thao tác đọc | Không phải cơ chế phân quyền và không tự chuyển transaction ngoài sang read-only. |
| `name` | Tên transaction dùng cho diagnostics | Khi dùng API programmatic có thể đặt tên rõ để đọc log/monitoring. |

Nếu truyền `null` vào `getTransaction(null)`, manager dùng **transaction definition mặc định**; trong Spring mặc định propagation thường là `REQUIRED`. Khi mục tiêu là học hoặc yêu cầu cấu hình rõ ràng, nên truyền một `DefaultTransactionDefinition` có tên và propagation cụ thể.

### 2.2. TransactionStatus: kết quả manager trả về

`TransactionStatus` mang trạng thái của **phạm vi transaction được trả về từ lời gọi cụ thể**, không phải “sổ đăng ký toàn bộ transactions”:

~~~java
boolean newTransaction = status.isNewTransaction();
boolean savepoint = status.hasSavepoint();
boolean completed = status.isCompleted();
boolean rollbackOnly = status.isRollbackOnly();
~~~

Đoạn này là **snippet** dùng trong một phạm vi đã gọi `getTransaction`.

- `isNewTransaction()`: manager đã tạo physical transaction mới cho scope này chưa? Trong lab JDBC, standalone `REQUIRED` trả true, còn participant `REQUIRED` trả false.
- `hasSavepoint()`: status có savepoint nested không? Với `NESTED` tham gia JDBC outer có thể true, dù `isNewTransaction()` false.
- `isRollbackOnly()`: status đang yêu cầu rollback thay cho commit ở scope hiện tại hoặc đã nhận marker rollback-only khi manager cho thấy trạng thái ấy.
- `isCompleted()`: status **đã được xử lý kết thúc** qua commit/rollback; không được commit hoặc rollback lại lần hai.

Đặc biệt, `status.isNewTransaction() == false` **không luôn đồng nghĩa** với “đang tham gia một physical transaction”. Với `SUPPORTS` mà **không có transaction nào**, status cũng không phải transaction mới, nhưng `TransactionSynchronizationManager.isActualTransactionActive()` có thể false. Cần xét đồng thời propagation và actual transaction activity.

### 2.3. PlatformTransactionManager: bắt đầu/tham gia và hoàn tất

Ba method cơ bản:

~~~java
TransactionStatus getTransaction(TransactionDefinition definition);
void commit(TransactionStatus status);
void rollback(TransactionStatus status);
~~~

`commit(status)` và `rollback(status)` xử lý **theo status do manager trả về**. Chúng không nhất thiết đều là câu lệnh JDBC `COMMIT`/`ROLLBACK` trên một connection mới:

- `commit` cho owner của physical transaction: thực hiện commit thật khi mọi điều kiện cho phép.
- `commit` cho participant `REQUIRED`: kết thúc logical scope, **không commit sớm physical transaction của outer**.
- `rollback` cho owner: rollback physical transaction của chính nó.
- `rollback` cho participant `REQUIRED`: trong manager Spring JDBC mặc định có thể đánh dấu shared transaction **rollback-only** thay vì rollback độc lập.
- `rollback` cho nested savepoint scope: có thể rollback **đến savepoint**, nếu manager/driver hỗ trợ.

**Không dùng `status.isNewTransaction()` làm lý do để bỏ `commit/rollback` cho participant**: manager trả về status thì caller vẫn phải hoàn tất scope phù hợp. `isNewTransaction` giúp hiểu hành vi, không thay thế completion API.

## 3. Tại sao cùng REQUIRED có hai kết quả?

### 3.1. Chưa có outer

~~~text
Caller
    |
    v
manager.getTransaction(REQUIRED)
    |
    +-- Không thấy transaction đang hoạt động trên resource
    +-- Mở physical transaction T1
    +-- Trả status: newTransaction=true
    |
    +-- JDBC UPDATE A +10 trong T1
    |
    v
manager.commit(status)
    |
    +-- COMMIT T1 thật
    v
Caller đọc DB: A đã tăng 10
~~~

Transaction manager phải quản lý cùng resource với JDBC operations, ví dụ `DataSourceTransactionManager` và `JdbcTemplate` cùng `DataSource`. Nếu SQL thực thi bằng một connection độc lập, kết quả không nhất thiết nằm trong T1.

### 3.2. Đã có outer

~~~text
Caller
    |
    v
manager.getTransaction(REQUIRED)    -> OUTER T1, newTransaction=true
    |
    +-- UPDATE A +10 (chưa commit)
    |
    +-- manager.getTransaction(REQUIRED)
    |           |
    |           +-- INNER tham gia T1
    |           +-- inner.isNewTransaction() == false
    |           +-- UPDATE B +10 (cũng trong T1)
    |           |
    |           v
    |      manager.commit(inner)
    |           |
    |           +-- Chỉ hoàn tất logical INNER
    |           +-- Chưa commit physical T1
    |
    +-- manager.rollback(outer)
                |
                +-- ROLLBACK toàn bộ T1

Sau cùng: A và B đều không tăng.
~~~

Một người đọc log chỉ thấy hai lần `getTransaction` nhưng **không được kết luận đã có T1 và T2**. Với `REQUIRED` và manager/resource phù hợp, chỉ có **một physical transaction T1**, dù code giữ hai `TransactionStatus` khác nhau.

Điều ngược lại cũng quan trọng: hai lần gọi standalone `getTransaction(REQUIRED)` liên tiếp, nếu lời gọi thứ nhất đã commit trước khi lời gọi thứ hai bắt đầu và không có outer, thì mỗi lời gọi có **một physical transaction riêng**. Lỗi ở transaction thứ hai không thể rollback transaction thứ nhất đã commit.

## 4. Ma trận propagation: getTransaction sẽ làm gì?

| Propagation | Chưa có transaction | Đã có transaction phù hợp | Điểm cần nhớ |
| --- | --- | --- | --- |
| `PROPAGATION_REQUIRED` | Mở T1 mới | Tham gia T1 | Mặc định, thường dùng nhất. |
| `PROPAGATION_SUPPORTS` | Có thể trả status không có physical transaction | Tham gia T1 | `newTransaction=false` một mình không chứng minh đang join. |
| `PROPAGATION_MANDATORY` | **Lỗi**: đòi hỏi transaction đã có | Tham gia T1 | Dùng khi inner chỉ hợp lệ trong workflow đã có transaction. |
| `PROPAGATION_REQUIRES_NEW` | Mở T1 mới | Suspend T1, mở T2 độc lập | Inner commit có thể còn khi outer rollback. |
| `PROPAGATION_NOT_SUPPORTED` | Chạy không có physical transaction | Suspend T1, chạy ngoài physical transaction | Không dùng nếu cần atomicity với outer. |
| `PROPAGATION_NEVER` | Chạy không có physical transaction | **Lỗi**: không cho có transaction | Dùng để khẳng định một thao tác không được gọi trong transaction. |
| `PROPAGATION_NESTED` | Mở T1 mới | Savepoint trong T1 khi được hỗ trợ | Không phải commit độc lập như REQUIRES_NEW. |

Bảng mô tả Spring imperative transaction với manager hỗ trợ từng propagation. `DataSourceTransactionManager` xử lý nested qua JDBC savepoints khi được phép; các manager JPA/JTA có thể hỗ trợ/giới hạn khác. Không suy diễn rằng cùng một annotation hoặc `TransactionDefinition` có kết quả giống nhau trên mọi manager.

### Ví dụ khác nhau về isNewTransaction

~~~text
getTransaction(REQUIRED), chưa có outer   -> new=true
getTransaction(REQUIRED), có outer        -> new=false
getTransaction(REQUIRES_NEW), có outer    -> new=true
getTransaction(NESTED), có outer savepoint-> new=false; hasSavepoint=true
getTransaction(NESTED), chưa có outer     -> new=true;  hasSavepoint=false
getTransaction(SUPPORTS), chưa có outer   -> new=false; actualActive=false
~~~

**Chú ý thực tế:** `REQUIRES_NEW` có thể cần **connection JDBC riêng** trong khi outer vẫn giữ connection của mình. Nếu inner ghi cùng hàng mà outer đang giữ lock, có nguy cơ chờ khóa hoặc deadlock. Các test dùng hai hàng A/B riêng để tránh biến một bài về propagation thành bài về lock contention.

## 5. Commit, rollback và lỗi hay bị hiểu sai

### 5.1. Commit một participant không commit physical transaction

Gọi `manager.commit(innerStatus)` cho một inner `REQUIRED` không giải phóng commit của outer transaction. Nếu sau đó outer gọi `rollback(outerStatus)`, tất cả cập nhật của inner lẫn outer trong shared transaction bị hoàn tác. Đây là hành vi có chủ đích của transaction scopes.

### 5.2. Rollback một participant có thể làm outer không commit được

Với `DataSourceTransactionManager` và `AbstractPlatformTransactionManager` trong cấu hình mặc định, `globalRollbackOnParticipationFailure=true`. Khi một inner `REQUIRED` gọi `manager.rollback(innerStatus)`, manager **đánh dấu shared transaction rollback-only**. Nếu outer sau đó cố `commit(outerStatus)`, Spring thường rollback và ném `UnexpectedRollbackException`.

~~~text
OUTER T1 bắt đầu
  +-- UPDATE A +10
  +-- INNER REQUIRED tham gia T1
        +-- UPDATE B +10
        +-- rollback(innerStatus)
        +-- shared T1 bị đánh dấu rollback-only
  +-- OUTER cố commit(outerStatus)
        +-- T1 ROLLBACK
        +-- UnexpectedRollbackException
Kết quả: A/B đều giữ nguyên.
~~~

Một inner participant không có physical transaction riêng để tự rollback. **Đừng bắt `UnexpectedRollbackException` rồi cố gọi `commit` lại trên status đã completed**. Cần xem nguyên nhân ban đầu và ranh giới nghiệp vụ.

### 5.3. setRollbackOnly và rollback(status) không hoàn toàn giống nhau

`status.setRollbackOnly()` yêu cầu rollback lúc scope được hoàn tất. Với owner transaction, một lệnh `commit(status)` sau đó có thể dẫn tới rollback do local rollback-only thay vì commit. Với participant, marker có thể lan tới shared transaction. Sự khác biệt chi tiết giữa local rollback-only marker và global rollback-only do inner `rollback(status)` phụ thuộc manager và scope.

Trong phần lab:

- Ta dùng `outer.setRollbackOnly()` để **cố ý rollback outer** sau khi inner `REQUIRED` đã hoàn tất bình thường. Đây là quyết định có chủ đích của owner.
- Ta dùng `manager.rollback(innerStatus)` để minh họa inner participant **đánh dấu shared transaction** khiến outer commit có thể báo `UnexpectedRollbackException`.

Không viết ứng dụng thật theo lối “có ngoại lệ nào cũng gọi cả rollback lẫn setRollbackOnly” vì dễ làm sai lifecycle của status.

### 5.4. Gọi commit/rollback đúng một lần

Mỗi status được xử lý hoàn tất một lần. Một pattern an toàn hơn code `finally { rollback(status); }` vô điều kiện là:

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    doBusinessWork();
    manager.commit(status);
} catch (RuntimeException | Error failure) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw failure;
}
~~~

Đây là **snippet**, chưa có khai báo `manager`, `definition`, `doBusinessWork`. `isCompleted()` ngăn rollback lần hai khi `commit` đã xử lý status rồi mới ném exception, ví dụ `UnexpectedRollbackException` ở outer boundary. Tuy vậy code production cần cân nhắc: nếu rollback cũng thất bại, exception rollback có thể che exception gốc; nên log lỗi thứ cấp và giữ root cause khi cần.

**Đặc biệt:** `getTransaction` có thể tự ném exception (ví dụ `MANDATORY` thiếu outer) **trước khi có status**. Không cố rollback một status chưa từng được cấp.

### 5.5. Checked exception cần được xử lý bằng logic trực tiếp

Khi dùng `@Transactional`, interceptor tự đánh giá rollback rules theo exception. Nhưng khi bạn **tự gọi `getTransaction`**, chính code của bạn phải chọn `commit/rollback`. `PlatformTransactionManager` không tự đọc Java checked/unchecked exception từ một method body mà nó không intercept.

Ví dụ với một checked `IOException` từ việc đọc file:

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    importFile();
    manager.commit(status);
} catch (IOException ex) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw ex;
}
~~~

Đây là **snippet về quyết định nghiệp vụ**, yêu cầu manager, definition và method `importFile()` thực tế. Cách xử lý nên mô tả rõ transaction còn hợp lệ không. Nếu import lỗi khiến cả lô không hoàn tất, rollback là lựa chọn thường đúng. Không cần phụ thuộc `rollbackFor` khi chính bạn trực tiếp điều phối status.

### 5.6. TransactionTemplate khi cần code gọn

`TransactionTemplate` bọc việc gọi manager, commit, rollback và exception handling vào template callback. Nó hữu ích khi chỉ cần vài phạm vi transaction trực tiếp:

~~~java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
String result = template.execute(status -> {
    // JDBC trong transaction; trả về kết quả nghiệp vụ.
    return "OK";
});
~~~

Đây là snippet minh họa; cần một bean `manager` thực tế. `TransactionTemplate` giúp tránh lặp lifecycle code, nhưng **không thay đổi propagation semantics**: khi callback tham gia transaction ngoài, commit cuối vẫn do outer nắm.

Bài này cố ý dùng `PlatformTransactionManager` trực tiếp trong lab để nhìn rõ `getTransaction`, `commit`, `rollback`.

## 6. Lab runnable: Java 17, Spring Boot, JDBC, H2 và JUnit 5

Bài thực hành dùng **Java 17+**, **Spring Boot 3.5.0**, Spring JDBC, H2 in-memory và JUnit 5. Nó tạo một bảng số dư demo với A=100, B=200; các method cập nhật +10 trong transaction. Sau mỗi lời gọi, test đọc lại database để phân biệt **inner join** và **independent commit**.

### 6.1. Cấu trúc dự án

~~~text
direct-get-transaction-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/directtx/
    │   │   ├── DirectTxApplication.java
    │   │   └── DirectTxService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/directtx/
            └── DirectTxServiceTest.java
~~~

Ở đây **service không có `@Transactional`**: ta muốn chứng minh giao dịch có thể được mở/tham gia **bằng API trực tiếp**, không phụ thuộc lời gọi qua Spring AOP proxy. Service vẫn là Spring bean để dependency injection và dùng cùng transaction manager/DataSource. Các test không được bọc trong Spring Test transaction.

### 6.2. pom.xml

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
    <artifactId>direct-get-transaction-lab</artifactId>
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

### 6.3. application.properties và schema.sql

Tệp `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:direct_get_transaction_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Tệp `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE demo_account (
    id BIGINT PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

H2 là database trong bộ nhớ JVM. Test sẽ xóa và chèn hai hàng A=100/B=200 trước từng trường hợp. Không dùng dữ liệu production hoặc giả định ví dụ này đủ an toàn cho thao tác chuyển tiền thật.

### 6.4. DirectTxApplication.java

Tệp `src/main/java/com/example/directtx/DirectTxApplication.java`:

~~~java
package com.example.directtx;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class DirectTxApplication {
    public static void main(String[] args) {
        SpringApplication.run(DirectTxApplication.class, args);
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
~~~

Ta chủ động khai báo **một** `DataSourceTransactionManager` dùng **cùng DataSource** với `JdbcTemplate`. `setNestedTransactionAllowed(true)` làm rõ mục đích thử `NESTED`; H2 hỗ trợ JDBC savepoints. Với JPA/JTA hoặc nhiều datasources, cần kiểm tra capability và manager thực tế, không sao chép assumptions từ JDBC lab này.

### 6.5. DirectTxService.java — phần trung tâm của bài

Tệp `src/main/java/com/example/directtx/DirectTxService.java`:

~~~java
package com.example.directtx;

import java.util.function.Function;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class DirectTxService {
    public record StatusView(
        boolean newTransaction,
        boolean hasSavepoint,
        boolean active
    ) {}

    public record PairView(StatusView outer, StatusView inner) {}

    private final PlatformTransactionManager manager;
    private final JdbcTemplate jdbc;

    public DirectTxService(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        this.manager = manager;
        this.jdbc = jdbc;
    }

    private DefaultTransactionDefinition definition(
            int propagation,
            String name) {
        DefaultTransactionDefinition d =
            new DefaultTransactionDefinition();
        d.setPropagationBehavior(propagation);
        d.setName(name);
        return d;
    }

    private StatusView view(TransactionStatus status) {
        return new StatusView(
            status.isNewTransaction(),
            status.hasSavepoint(),
            TransactionSynchronizationManager
                .isActualTransactionActive()
        );
    }

    private void add(long id, long delta) {
        int changed = jdbc.update(
            "UPDATE demo_account SET amount = amount + ? WHERE id = ?",
            delta, id
        );
        if (changed != 1) {
            throw new IllegalStateException("Account not found: " + id);
        }
    }

    // Programmatic transaction boundary:
    // getTransaction có thể tạo mới HOẶC tham gia tùy propagation.
    private <T> T within(
            int propagation,
            String name,
            Function<TransactionStatus, T> work) {

        DefaultTransactionDefinition definition =
            definition(propagation, name);

        TransactionStatus status =
            manager.getTransaction(definition);

        try {
            T result = work.apply(status);
            manager.commit(status);
            return result;
        } catch (RuntimeException | Error failure) {
            // commit có thể đã hoàn tất status rồi mới ném lỗi.
            if (!status.isCompleted()) {
                manager.rollback(status);
            }
            throw failure;
        }
    }

    // A. REQUIRED: chưa có outer, manager mở physical transaction mới.
    public StatusView requiredStandalone() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "required-standalone",
            status -> {
                add(1L, 10L);
                return view(status);
            }
        );
    }

    // B. REQUIRED inner: tham gia outer; inner commit KHÔNG commit thật.
    public PairView requiredInnerThenOuterRollsBack() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-required",
            outer -> {
                add(1L, 10L);
                StatusView innerView = within(
                    TransactionDefinition.PROPAGATION_REQUIRED,
                    "inner-required",
                    inner -> {
                        add(2L, 10L);
                        return view(inner);
                    }
                );
                // Inner commit đã chạy; outer vẫn sở hữu T1.
                outer.setRollbackOnly();
                return new PairView(view(outer), innerView);
            }
        );
    }

    // C. REQUIRES_NEW inner: B commit độc lập, outer rollback A.
    public PairView requiresNewInnerThenOuterRollsBack() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-for-requires-new",
            outer -> {
                add(1L, 10L);
                StatusView innerView = within(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW,
                    "inner-requires-new",
                    inner -> {
                        add(2L, 10L);
                        return view(inner);
                    }
                );
                outer.setRollbackOnly();
                return new PairView(view(outer), innerView);
            }
        );
    }

    // D. Một participant REQUIRED rollback: shared T1 rollback-only.
    public void participantRollbackPreventsOuterCommit() {
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-marked-rollback",
            outer -> {
                add(1L, 10L);

                TransactionStatus inner = manager.getTransaction(
                    definition(
                        TransactionDefinition.PROPAGATION_REQUIRED,
                        "inner-explicit-rollback"
                    )
                );
                try {
                    add(2L, 10L);
                    manager.rollback(inner);
                } catch (RuntimeException | Error failure) {
                    if (!inner.isCompleted()) {
                        manager.rollback(inner);
                    }
                    throw failure;
                }

                // Outer cố commit ở within(...), nhưng T1 đã rollback-only.
                return null;
            }
        );
    }

    // E. SUPPORTS không có outer: không tạo physical transaction mới.
    public StatusView supportsStandalone() {
        return within(
            TransactionDefinition.PROPAGATION_SUPPORTS,
            "supports-no-outer",
            this::view
        );
    }

    // F. MANDATORY không có outer: getTransaction ném exception.
    public void mandatoryStandalone() {
        within(
            TransactionDefinition.PROPAGATION_MANDATORY,
            "mandatory-no-outer",
            status -> null
        );
    }

    // G. MANDATORY có outer: tham gia physical T1.
    public PairView mandatoryJoiningOuter() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-for-mandatory",
            outer -> {
                StatusView innerView = within(
                    TransactionDefinition.PROPAGATION_MANDATORY,
                    "inner-mandatory",
                    this::view
                );
                return new PairView(view(outer), innerView);
            }
        );
    }

    // H. NESTED chưa có outer: transaction mới, KHÔNG phải savepoint.
    public StatusView nestedStandalone() {
        return within(
            TransactionDefinition.PROPAGATION_NESTED,
            "nested-no-outer",
            this::view
        );
    }

    // I. NESTED có outer: savepoint trong cùng physical transaction.
    public PairView nestedJoiningOuter() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-for-nested",
            outer -> {
                StatusView innerView = within(
                    TransactionDefinition.PROPAGATION_NESTED,
                    "inner-nested",
                    this::view
                );
                return new PairView(view(outer), innerView);
            }
        );
    }

    // J. REQUIRED mới nhưng gặp lỗi: rollback toàn transaction mới.
    public void requiredStandaloneFailure() {
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "required-fail",
            status -> {
                add(1L, 10L);
                throw new IllegalStateException("controlled failure");
            }
        );
    }

    // K. Hai lời gọi standalone khác nhau: T1 commit rồi T2 fail.
    public void twoSeparateRequiredCalls() {
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "first-required",
            status -> {
                add(1L, 10L);
                return null;
            }
        );
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "second-required",
            status -> {
                add(2L, 10L);
                throw new IllegalStateException("second step failed");
            }
        );
    }

    // L. NEVER không cho tham gia outer đang hoạt động.
    public void neverInsideOuter() {
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-for-never",
            outer -> within(
                TransactionDefinition.PROPAGATION_NEVER,
                "inner-never",
                status -> null
            )
        );
    }
}
~~~

### 6.6. Vì sao code này khác @Transactional?

`DirectTxService` không cần annotation `@Transactional` vì nó **tự gọi manager.getTransaction(...)**. Transaction manager vẫn liên kết JDBC connection với thread khi mở transaction; các câu SQL từ `JdbcTemplate` dùng đúng resource.

Hàm `within(...)`:

1. Tạo `DefaultTransactionDefinition` với propagation và tên rõ ràng.
2. Gọi `manager.getTransaction(definition)` trước body.
3. Chạy work khi status đang active/participant.
4. Gọi `manager.commit(status)` sau thành công.
5. Nếu code ném RuntimeException/Error, gọi `manager.rollback(status)` nếu status chưa completed.
6. **Không rollback lại** khi `commit` đã tự hoàn tất và ném exception do rollback-only.

`within(...)` là **helper cho bài thực hành**, không phải một thư viện giao dịch production hoàn chỉnh. Nó dùng `Function` nên chỉ thể hiện các exception unchecked. Với checked exceptions, code thật cần giao diện callback có `throws` phù hợp hoặc khối try/catch rõ ràng. Trong hệ thống lớn, `TransactionTemplate` thường gọn và an toàn hơn việc lặp lại boilerplate như trên.

Vì transaction được quản lý **trực tiếp**, lời gọi `within(...)` bên trong cùng bean vẫn đi qua manager: không gặp bẫy self-invocation giống annotation `@Transactional` trên một method được gọi bằng `this.inner()`. Tuy nhiên các resource phải đúng manager, thread và datasource.

### 6.7. DirectTxServiceTest.java: kiểm chứng 12 tình huống

Tệp `src/test/java/com/example/directtx/DirectTxServiceTest.java`:

~~~java
package com.example.directtx;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DirectTxServiceTest {
    @Autowired
    private DirectTxService service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM demo_account");
        jdbc.update(
            "INSERT INTO demo_account (id, amount) VALUES (?, ?)",
            1L, 100L
        );
        jdbc.update(
            "INSERT INTO demo_account (id, amount) VALUES (?, ?)",
            2L, 200L
        );
    }

    private long amount(long id) {
        Long result = jdbc.queryForObject(
            "SELECT amount FROM demo_account WHERE id = ?",
            Long.class, id
        );
        if (result == null) {
            throw new AssertionError("Missing account " + id);
        }
        return result;
    }

    @Test
    void requiredStartsNewWhenNoTransactionExists() {
        DirectTxService.StatusView s = service.requiredStandalone();

        assertTrue(s.newTransaction());
        assertTrue(s.active());
        assertFalse(s.hasSavepoint());
        assertEquals(110L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void requiredParticipantDoesNotCommitBeforeOuter() {
        DirectTxService.PairView p =
            service.requiredInnerThenOuterRollsBack();

        assertTrue(p.outer().newTransaction());
        assertFalse(p.inner().newTransaction());
        assertTrue(p.inner().active());
        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void requiresNewParticipantCommitsIndependently() {
        DirectTxService.PairView p =
            service.requiresNewInnerThenOuterRollsBack();

        assertTrue(p.outer().newTransaction());
        assertTrue(p.inner().newTransaction());
        assertEquals(100L, amount(1L));
        assertEquals(210L, amount(2L));
    }

    @Test
    void participatingRollbackMarksSharedTransactionRollbackOnly() {
        assertThrows(
            UnexpectedRollbackException.class,
            service::participantRollbackPreventsOuterCommit
        );
        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void supportsWithoutOuterHasNoPhysicalTransaction() {
        DirectTxService.StatusView s = service.supportsStandalone();

        assertFalse(s.newTransaction());
        assertFalse(s.active());
        assertFalse(s.hasSavepoint());
    }

    @Test
    void mandatoryWithoutOuterRejectsCall() {
        assertThrows(
            IllegalTransactionStateException.class,
            service::mandatoryStandalone
        );
    }

    @Test
    void mandatoryWithOuterJoinsExistingTransaction() {
        DirectTxService.PairView p =
            service.mandatoryJoiningOuter();

        assertTrue(p.outer().newTransaction());
        assertFalse(p.inner().newTransaction());
        assertTrue(p.inner().active());
    }

    @Test
    void nestedWithoutOuterStartsNewTransaction() {
        DirectTxService.StatusView s = service.nestedStandalone();

        assertTrue(s.newTransaction());
        assertFalse(s.hasSavepoint());
        assertTrue(s.active());
    }

    @Test
    void nestedWithOuterUsesSavepoint() {
        DirectTxService.PairView p = service.nestedJoiningOuter();

        assertTrue(p.outer().newTransaction());
        assertFalse(p.inner().newTransaction());
        assertTrue(p.inner().hasSavepoint());
        assertTrue(p.inner().active());
    }

    @Test
    void failedStandaloneRequiredRollsBackItsOwnTransaction() {
        assertThrows(
            IllegalStateException.class,
            service::requiredStandaloneFailure
        );
        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void separateStandaloneRequiredCallsAreNotAtomicTogether() {
        assertThrows(
            IllegalStateException.class,
            service::twoSeparateRequiredCalls
        );
        assertEquals(110L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void neverCannotBeCalledInsideTransaction() {
        assertThrows(
            IllegalTransactionStateException.class,
            service::neverInsideOuter
        );
        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }
}
~~~

**Không annotate `@Transactional` trên test class.** Nếu test framework mở transaction ngoài, phép thử `requiredStartsNewWhenNoTransactionExists` sẽ không còn là “chưa có outer”, và `mandatoryWithoutOuterRejectsCall` có thể không ném exception. Bài lab cần chính xác tình huống **có/không có transaction trước getTransaction**.

`@BeforeEach` reset dữ liệu ngoài test transaction trước mỗi lần chạy. Assert đọc lại qua `JdbcTemplate` sau khi service method hoàn tất, nên kết quả phản ánh commit/rollback thật trên H2.

## 7. Chạy lab và đọc kết quả

Cần Java 17+, Maven và khả năng tải dependencies lần đầu. Từ thư mục `direct-get-transaction-lab`:

~~~bash
java -version
mvn -version
mvn test
~~~

Nếu project có Maven Wrapper, dùng `./mvnw test` trên Linux/macOS hoặc `.\mvnw.cmd test` trong Windows PowerShell.

Với source và database H2 tương thích, dự kiến **12 tests pass, 0 failures, 0 errors**. Đây là **kết quả dự kiến** theo code, không phải log của lượt chạy đã được thực hiện.

| Test | Dự kiến | Điều chứng minh |
| --- | --- | --- |
| `requiredStartsNewWhenNoTransactionExists` | new=true; A=110, B=200 | REQUIRED mở mới khi chưa có outer. |
| `requiredParticipantDoesNotCommitBeforeOuter` | inner new=false; A=100, B=200 | Commit của inner participant không commit vật lý; outer rollback được cả hai. |
| `requiresNewParticipantCommitsIndependently` | inner new=true; A=100, B=210 | REQUIRES_NEW có commit độc lập. |
| `participatingRollbackMarksSharedTransactionRollbackOnly` | UnexpectedRollbackException; A=100, B=200 | Rollback inner REQUIRED có thể làm outer commit thất bại. |
| `supportsWithoutOuterHasNoPhysicalTransaction` | new=false; active=false | getTransaction có thể không bắt đầu physical transaction. |
| `mandatoryWithoutOuterRejectsCall` | IllegalTransactionStateException | MANDATORY đòi hỏi transaction đã có. |
| `mandatoryWithOuterJoinsExistingTransaction` | inner new=false; active=true | MANDATORY tham gia outer. |
| `nestedWithoutOuterStartsNewTransaction` | new=true; savepoint=false | NESTED không có outer mở transaction mới. |
| `nestedWithOuterUsesSavepoint` | new=false; savepoint=true | NESTED có outer tạo savepoint nếu được hỗ trợ. |
| `failedStandaloneRequiredRollsBackItsOwnTransaction` | A=100, B=200 | REQUIRED standalone thất bại rollback physical transaction. |
| `separateStandaloneRequiredCallsAreNotAtomicTogether` | A=110, B=200 | Hai getTransaction standalone liên tiếp không tự tạo outer bao chung. |
| `neverCannotBeCalledInsideTransaction` | IllegalTransactionStateException | NEVER từ chối khi đang có outer. |

### Hai quan sát quan trọng nhất

**Quan sát 1 — `commit(inner)` không đồng nghĩa đã commit DB.** Test `requiredParticipantDoesNotCommitBeforeOuter` ghi A trong outer, ghi B trong inner REQUIRED rồi commit inner. Sau đó outer `setRollbackOnly` và kết thúc; cả A, B đều trở về giá trị ban đầu. Vậy inner `commit` chỉ hoàn tất **logical scope**, không phải physical commit.

**Quan sát 2 — rollback inner REQUIRED có thể khiến outer mất quyền commit.** Trong test `participatingRollbackMarksSharedTransactionRollbackOnly`, `rollback(inner)` đánh dấu transaction chung. Outer tuy không tự ném exception trong business body nhưng gọi `commit(outer)` dẫn đến `UnexpectedRollbackException`. Đây là lý do transaction status của participant vẫn có ý nghĩa, ngay khi `isNewTransaction()` là false.

### Ý nghĩa của 12 test

Mục tiêu không phải chỉ đạt số lượng test; mỗi test thay đổi **một điều kiện**: propagation hoặc trạng thái outer. Các giá trị `newTransaction`, `hasSavepoint` và các phép đọc DB sau completion là bằng chứng mạnh hơn việc chỉ đếm số lần method `getTransaction` được gọi.

## 8. Lỗi phổ biến và cách tránh

### 8.1. Đồng nhất logical scope với physical transaction

Hai calls `getTransaction(REQUIRED)` khi đã có outer có thể trả về hai statuses khác nhau nhưng vẫn dùng **một JDBC transaction**. Không dùng số `TransactionStatus` để đếm số physical transactions.

### 8.2. Dựa vào isNewTransaction=false để bỏ commit/rollback

`isNewTransaction` nói scope có mở physical transaction mới hay không; nó không nói status có thể bị bỏ mặc. Mọi status được manager trả về nên được xử lý completion đúng lifecycle, kể cả participant. Không gọi commit/rollback lại trên status đã `isCompleted=true`.

### 8.3. Dùng transaction manager khác với JdbcTemplate

Nếu manager quản lý `DataSource A` nhưng code JDBC lấy connection từ `DataSource B`, việc getTransaction tạo mới/tham gia cho A không tự điều khiển B. Phải bảo đảm đúng **manager, datasource, thread và resource**. Với nhiều managers, chọn rõ qualifier và đặt kiểm thử thực tế.

### 8.4. Dùng REQUIRES_NEW như cách sửa mọi vấn đề

`REQUIRES_NEW` đổi semantics thành transaction độc lập; inner commit có thể còn sau outer rollback. Nó có thể cần connection thứ hai và gặp lock wait nếu inner ghi cùng hàng outer đang giữ lock. Đặt propagation theo bất biến nghiệp vụ, không chỉ theo mong muốn “có transaction mới”.

### 8.5. Không phân biệt rollback-only của inner với outer

Inner `REQUIRED` gọi `rollback(innerStatus)` thường đánh dấu global rollback-only khi tham gia. Outer catch lỗi hoặc business body trả về bình thường không thể tự xóa marker đã đặt; `UnexpectedRollbackException` tại outer commit là tín hiệu rằng commit đã không xảy ra.

### 8.6. Catch mọi exception rồi commit dù operation lỗi

Khi quản lý trực tiếp, chính bạn quyết định trạng thái transaction. Nếu code catch lỗi DB rồi tiếp tục `commit`, dữ liệu có thể dở dang hoặc transaction đã không thể commit. Không dùng pattern “nuốt mọi exception”, phải rollback theo bất biến và hiểu DB behavior sau lỗi.

### 8.7. Gọi getTransaction xong không hoàn tất status

Quên `commit`/`rollback` có thể giữ connection/locks/resource binding lâu, làm ảnh hưởng lời gọi sau và cạn pool. Mỗi `getTransaction` trả status hợp lệ cần có đường completion rõ. Nếu exception từ `getTransaction` xảy ra trước khi status được trả về, không giả vờ đã có status để rollback.

### 8.8. Rollback/commit hai lần

Sau `manager.commit(status)` hoặc `manager.rollback(status)`, status có thể `isCompleted=true`. Gọi lại có thể ném `IllegalTransactionStateException` hoặc làm error handling khó hiểu. Trong code mẫu, `if (!status.isCompleted())` tránh rollback lần hai khi `commit` đã xử lý rollback-only và ném exception.

### 8.9. Đánh đồng transaction programmatic với @Transactional

`@Transactional` dựa vào interceptor/proxy hoặc AspectJ weaving, đánh giá rollback rules khi method ném exception. `manager.getTransaction` là **lời gọi Java trực tiếp**, không cần proxy trên method đó, nhưng caller phải tự bảo đảm completion. Nếu một phương thức programmatic nằm bên trong một scope `@Transactional` đang mở, nó **có thể tham gia** transaction ấy khi dùng cùng manager/resource và propagation phù hợp; không phải hai thế giới tách biệt.

### 8.10. Không kiểm tra manager hỗ trợ

`PROPAGATION_NESTED` cần savepoint support khi có outer. `REQUIRES_NEW` cần suspension/resource handling, `isolation` và `timeout` phụ thuộc manager/driver/database. Với JPA/JTA/reactive transaction manager, semantics implementation khác lab JDBC này; không sao chép `DataSourceTransactionManager` như giải pháp chung cho mọi hạ tầng.

### 8.11. Thử nghiệm trong @Transactional test

Khi test class gắn `@Transactional`, framework mở transaction bao ngoài và các `getTransaction(REQUIRED)` trong service có thể **join test transaction**, làm kết quả `newTransaction` và commit/rollback bị thay đổi. Với bài cần phân biệt standalone/join, test không nên vô tình có transaction ngoài.

### 8.12. Không biết thời điểm transaction kết thúc khi trả về status

Đừng trả `TransactionStatus` sống ra controller để controller tùy tiện commit sau khi resource/thread đã khác. Nếu cần hiển thị thông tin, hãy tạo `record` hoặc DTO **snapshot trước completion**, rồi hoàn tất status trong cùng phạm vi được quản lý. Đó là lý do lab trả `StatusView` chứ không trả một status đang hoạt động.

## 9. Quy trình thiết kế khi dùng getTransaction trực tiếp

Với một tính năng gồm nhiều câu SQL, nên làm lần lượt:

1. **Xác định bất biến nguyên tử**: các thay đổi nào phải commit hoặc rollback cùng nhau?
2. **Xác định transaction hiện tại**: một service hoặc caller có thể đã mở transaction trên cùng manager/resource chưa?
3. **Chọn propagation**: REQUIRED để tham gia nếu có; REQUIRES_NEW để độc lập; NESTED để rollback cục bộ bằng savepoint khi hỗ trợ; MANDATORY để bắt buộc outer.
4. **Tạo TransactionDefinition**: set propagation, isolation, timeout, readOnly và name khi có lý do.
5. **Gọi getTransaction đúng một lần cho mỗi scope** và giữ status cục bộ.
6. **Thực hiện SQL bằng resource do manager quản lý**, như JdbcTemplate cùng DataSource.
7. **Kết thúc scope đúng một lần**: commit thành công hoặc rollback theo lỗi/bất biến; không nuốt exception.
8. **Kiểm tra rollback-only, unexpected rollback** nếu đang tham gia transaction ngoài.
9. **Test standalone và nested/join** riêng: quan sát isNewTransaction, hasSavepoint, actualActive và persisted state.
10. **Cân nhắc TransactionTemplate** nếu logic chỉ cần một phạm vi đơn giản để giảm boilerplate và lỗi vòng đời.

Nếu hệ thống có nhiều bước và cần cùng atomicity, cách rõ nhất thường là **một transaction ở facade nghiệp vụ**, các bước con `REQUIRED` tham gia. Chỉ mở independent transaction khi nghiệp vụ thật sự cho phép dữ liệu bên trong sống sót sau khi outer thất bại.

## 10. Câu hỏi tự đánh giá

1. **`manager.getTransaction(REQUIRED)` có luôn mở transaction mới không?** — Không; nó có thể **tham gia transaction đang tồn tại**.
2. **Khi không có outer, REQUIRED trả `isNewTransaction()` thế nào?** — Thường true với JDBC manager trong lab.
3. **Khi đã có outer, REQUIRED trả thế nào?** — Thường false vì tham gia cùng physical transaction.
4. **`commit(innerStatus)` trên participant có commit database ngay không?** — Không; outer sở hữu commit vật lý.
5. **Nếu outer rollback sau inner participant commit, thay đổi inner có còn không?** — Không, nếu cùng physical transaction.
6. **`rollback(innerStatus)` có thể làm outer commit gặp gì?** — Có thể đánh dấu rollback-only và gây `UnexpectedRollbackException`.
7. **`REQUIRES_NEW` có đảm bảo inner rollback theo outer không?** — Không; nó có independent commit.
8. **`NESTED` trong JDBC khi có outer khác REQUIRES_NEW thế nào?** — NESTED dùng savepoint trong cùng physical transaction; REQUIRES_NEW mở physical transaction độc lập.
9. **`NESTED` khi chưa có outer có bắt buộc savepoint không?** — Không; có thể mở transaction mới và hasSavepoint=false.
10. **`MANDATORY` khi không có outer làm gì?** — Ném `IllegalTransactionStateException`.
11. **`SUPPORTS` khi không có outer có thể có status không phải transaction mới không?** — Có; status tồn tại nhưng actual transaction có thể không active.
12. **`getTransaction(null)` thường mang propagation nào theo default?** — Mặc định thông dụng là REQUIRED.
13. **Khi dùng API trực tiếp, exception checked có tự kích hoạt rollbackFor không?** — Không có interceptor áp rule; caller tự quyết định commit/rollback.
14. **Khi nào không được rollback lại status trong catch?** — Khi status đã completed sau commit/rollback hoặc manager đã xử lý nó.
15. **Tại sao không để test có @Transactional?** — Vì test transaction có thể làm thay đổi trạng thái outer mà bài đang đo.
16. **Muốn code ngắn hơn nhưng giữ programmatic transaction semantics dùng gì?** — `TransactionTemplate`.

## 11. Bài tập mở rộng

**Bài A — REQUIRED trong facade:** thêm một method ngoài sử dụng `getTransaction(REQUIRED)` bao hai lần `required...` bên trong. Dự đoán `isNewTransaction` của từng scope, rollback một scope bên trong, rồi kiểm tra tại outer commit.

**Bài B — Độc lập bằng REQUIRES_NEW:** đổi inner từ REQUIRED sang REQUIRES_NEW trên một bản sao của test, cho outer và inner cập nhật **hai hàng khác nhau**. Dự đoán dữ liệu sau outer rollback và giải thích vì sao inner commit vẫn còn.

**Bài C — MANDATORY và NEVER:** trong những lời gọi có/không có transaction, dùng `getTransaction(MANDATORY)` và `getTransaction(NEVER)`. Viết bảng điều kiện nào chấp nhận và điều kiện nào ném exception trước khi thực hiện test.

**Bài D — Nested savepoint:** với `DataSourceTransactionManager` hỗ trợ savepoint, gọi `getTransaction(NESTED)` khi outer tồn tại, cập nhật B rồi rollback nested. Tiếp tục cập nhật A trong outer và commit. So sánh với `rollback(inner REQUIRED)` vốn có thể mark global rollback-only.

**Bài E — Exception handling:** sửa helper `within` để hỗ trợ checked exception bằng callback có `throws Exception`. Bảo đảm rollback đúng khi checked exception biểu thị thất bại nghiệp vụ và không rollback hai lần nếu `commit` đã completed.

**Bài F — Quan sát logs:** bật logging transaction manager ở môi trường thử nghiệm và đối chiếu khi nào có physical transaction start, participate, suspend, resume, commit/rollback. Tránh log thông tin nhạy cảm từ dữ liệu nghiệp vụ.

## 12. Tổng kết

`PlatformTransactionManager.getTransaction(TransactionDefinition)` là API **đánh giá yêu cầu propagation** theo trạng thái giao dịch hiện tại. Nó có thể **tạo mới**, **tham gia**, **tạm đình chỉ transaction ngoài**, **tạo savepoint**, **chạy ngoài transaction** hoặc **từ chối lời gọi** tùy cấu hình và khả năng manager.

**Điểm quyết định:** một `TransactionStatus` không đồng nghĩa một physical transaction mới. Hãy đọc `isNewTransaction()` và trạng thái transaction thật, xem propagation và completion semantics, rồi kiểm chứng persisted data.

Với `REQUIRED`, **commit participant không commit sớm physical transaction**, còn **rollback participant có thể khiến outer mất quyền commit**. Khi cần tránh lỗi vòng đời do lập trình thủ công, cân nhắc `TransactionTemplate` hoặc `@Transactional` tại ranh giới service phù hợp.

### Tài liệu chính thức

- [Spring Framework — Understanding the Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — AbstractPlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework — PlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html)
- [Spring Framework — TransactionStatus API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
