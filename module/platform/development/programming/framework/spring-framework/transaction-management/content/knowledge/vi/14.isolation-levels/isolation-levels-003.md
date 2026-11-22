# `ISOLATION_DEFAULT` sử dụng mặc định của tài nguyên trong Spring Transaction Management

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác `Isolation.DEFAULT`/`TransactionDefinition.ISOLATION_DEFAULT` có ý nghĩa gì trong `@Transactional`.
2. Phân biệt **isolation được khai báo trong Spring** với **isolation thực tế của JDBC connection/transaction**.
3. Hiểu vì sao `DEFAULT` **không đồng nghĩa** với `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE` hay “không có isolation”.
4. Truy nguyên nguồn cấu hình isolation: database server, JDBC driver/session, connection pool và transaction manager.
5. Dự đoán hành vi khi method `REQUIRED` **tham gia transaction hiện có**, method `REQUIRES_NEW` mở transaction riêng, hoặc method `NESTED` dùng cùng transaction vật lý.
6. Chạy ví dụ **Java 17+, Spring Boot, HikariCP, H2, Spring JDBC**, quan sát `Connection.getTransactionIsolation()` và viết test kiểm chứng thay vì chỉ đoán theo annotation.
7. Biết khi nào để `DEFAULT`, khi nào phải ghi một mức isolation cụ thể, và cách tránh lỗi khi chuyển DB hoặc cấu hình connection pool.

**Chủ đề:** mức cô lập `ISOLATION_DEFAULT` trong Spring Framework transaction management. Trọng tâm không phải xếp hạng tất cả isolation levels, mà là hiểu **ai quyết định mức thực tế khi Spring không chỉ định mức riêng**.

---

## 1. Kết luận quan trọng nhất

Trong Spring:

```java
@Transactional
public void process() {
    // ...
}
```

có isolation mặc định giống với:

```java
@Transactional(isolation = Isolation.DEFAULT)
public void process() {
    // ...
}
```

`Isolation.DEFAULT` **không yêu cầu Spring thiết lập một mức cô lập cụ thể**. Theo `TransactionDefinition`, nó có giá trị đặc biệt `ISOLATION_DEFAULT = -1` và mang ý nghĩa *sử dụng mức mặc định của tài nguyên giao dịch bên dưới*.

Với **Spring JDBC + `DataSourceTransactionManager`**, khi bắt đầu transaction mới có `Isolation.DEFAULT`, Spring **không gọi `Connection.setTransactionIsolation(...)` để ép một mức cụ thể**. Transaction sử dụng mức cô lập mà **JDBC connection vừa được cấp đang có**. Connection đó có thể đã được thiết lập bởi DBMS, JDBC driver, cấu hình pool hoặc initialization SQL.

Điều này **không** có nghĩa transaction chạy “không có isolation”, “không dùng lock”, hoặc “luôn `READ_COMMITTED`”. Nó chỉ có nghĩa: **Spring không override mức isolation của connection trong transaction definition này**.

```text
@Transactional(isolation = Isolation.DEFAULT)
                  |
                  v
     Spring TransactionInterceptor
                  |
         New JDBC transaction?
                  |
                  v
   DataSourceTransactionManager lấy Connection
                  |
                  v
  Isolation.DEFAULT => không ép JDBC isolation mới
                  |
                  v
   Transaction sử dụng isolation hiện có của Connection
                  |
                  v
   Database thực thi theo semantics của mức đó
```

Nếu application được chuyển từ PostgreSQL sang MySQL InnoDB, hoặc một connection pool được đổi cấu hình, cùng annotation `Isolation.DEFAULT` **có thể** dẫn đến mức isolation thực tế khác nhau. Muốn yêu cầu mức nhất quán, cần cấu hình rõ ở đúng tầng và kiểm chứng DB hỗ trợ.

## 2. `DEFAULT` là một sentinel, không phải mức cô lập JDBC

Các enum trong Spring:

```java
import org.springframework.transaction.annotation.Isolation;

Isolation.DEFAULT;
Isolation.READ_UNCOMMITTED;
Isolation.READ_COMMITTED;
Isolation.REPEATABLE_READ;
Isolation.SERIALIZABLE;
```

Bảng giá trị:

| Tên Spring | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| `Isolation.DEFAULT` | `-1` | **Không chọn một isolation cụ thể**; dùng default của resource/transaction manager |
| `Isolation.READ_UNCOMMITTED` | `1` | Yêu cầu mức JDBC `TRANSACTION_READ_UNCOMMITTED` |
| `Isolation.READ_COMMITTED` | `2` | Yêu cầu mức JDBC `TRANSACTION_READ_COMMITTED` |
| `Isolation.REPEATABLE_READ` | `4` | Yêu cầu mức JDBC `TRANSACTION_REPEATABLE_READ` |
| `Isolation.SERIALIZABLE` | `8` | Yêu cầu mức JDBC `TRANSACTION_SERIALIZABLE` |

Giá trị `1, 2, 4, 8` của bốn mức cụ thể tương ứng hằng số trong `java.sql.Connection`. **`-1` không phải một mức JDBC**, nên không được gọi `connection.setTransactionIsolation(-1)`.

Các hằng số liên quan:

```java
import java.sql.Connection;
import org.springframework.transaction.TransactionDefinition;

int useResourceDefault = TransactionDefinition.ISOLATION_DEFAULT; // -1
int readCommitted = Connection.TRANSACTION_READ_COMMITTED;       // 2
int repeatableRead = Connection.TRANSACTION_REPEATABLE_READ;     // 4
```

Đoạn trên chỉ nhằm minh họa giá trị hằng số; chương trình chạy hoàn chỉnh sẽ có ở mục 8. Trong JDBC còn có `Connection.TRANSACTION_NONE = 0`, mang nghĩa kết nối/driver không hỗ trợ transaction, **không tương đương** `ISOLATION_DEFAULT = -1`.

### Mặc định của `@Transactional`

Nếu không cấu hình thuộc tính nào:

```java
@Transactional
public void executeBusinessStep() {
    // ...
}
```

Spring thường hiểu là `Propagation.REQUIRED`, `Isolation.DEFAULT`, `readOnly = false`, timeout mặc định và rollback rules mặc định. Những thuộc tính này **độc lập**:

- **Propagation**: có mở transaction mới hay tham gia transaction đang tồn tại?
- **Isolation**: nếu transaction vật lý mới được mở, nó sẽ sử dụng mức cô lập nào?
- **Read-only**: gợi ý/chính sách chỉ đọc, không phải isolation.
- **Rollback rules**: exception nào khiến interceptor rollback, không phải isolation.

Không được hiểu `Isolation.DEFAULT` là “không có transaction”. Có transaction hay không phụ thuộc vào propagation, transaction manager, việc caller đi qua Spring proxy và tài nguyên được dùng.

## 3. “Mặc định của tài nguyên” là mặc định của tầng nào?

Trong triển khai JDBC, mức thực tế của connection có thể chịu ảnh hưởng từ nhiều tầng:

```text
DBMS / server / database-level settings
             |
             v
JDBC driver / session initialization
             |
             v
DataSource / connection pool (HikariCP, ... )
             |
             v
Connection được mượn từ pool
             |
             v
Spring JDBC TransactionManager
   | Isolation.DEFAULT -> giữ nguyên mức hiện có
   | Isolation.READ_COMMITTED -> yêu cầu đổi nếu cần
             |
             v
Transaction vật lý thực thi bằng JDBC connection đó
```

Các điểm cần phân biệt:

1. **DBMS default**: cấu hình mặc định của PostgreSQL, MySQL InnoDB, H2 hay database khác. Nó có thể được administrator thay đổi.
2. **JDBC connection/session state**: driver và các lệnh initialization có thể thiết lập isolation trước khi Spring nhận connection.
3. **Connection pool policy**: pool như HikariCP có thể đặt `transactionIsolation` cho các connection nó quản lý, **khác mức mặc định ban đầu của DB server**.
4. **Transaction manager override**: nếu method yêu cầu một mức cụ thể khi mở transaction, Spring JDBC có thể tạm đổi isolation của connection.
5. **Transaction đang tồn tại**: nếu method chỉ *tham gia* transaction bên ngoài, isolation đã được xác lập bởi transaction ngoài; annotation của inner method không mặc nhiên thay đổi nó.

Vì vậy, một câu trả lời “`Isolation.DEFAULT` = `READ_COMMITTED`” là **sai khi áp dụng chung**. Có hệ thống mà kết quả quan sát là `READ_COMMITTED`, nhưng đó là do **tài nguyên đang cấu hình như vậy**, không phải do hằng số `DEFAULT` quy định.

### Ví dụ ba database với cấu hình gốc thường gặp

| DBMS/engine | Mức mặc định thường được tài liệu công bố | Điều cần nhớ |
| --- | --- | --- |
| PostgreSQL | `READ COMMITTED` | Cài đặt/session có thể thay đổi; `READ UNCOMMITTED` được xử lý tương đương `READ COMMITTED` |
| MySQL InnoDB | `REPEATABLE READ` | Session/global `transaction_isolation` có thể khác mặc định |
| H2 | `READ COMMITTED` | Demo/test có thể đổi mức của connection qua JDBC/pool |

Đây là các giá trị **thông thường khi chưa cấu hình override**, không phải bảng hứa hẹn mức isolation của mọi instance đang chạy. Một datasource trỏ tới PostgreSQL nhưng pool đã đặt `TRANSACTION_REPEATABLE_READ` có thể khiến transaction Spring `DEFAULT` chạy ở `REPEATABLE_READ`.

Nguồn chính thức: PostgreSQL `SET TRANSACTION`, MySQL 8.4 InnoDB Transaction Isolation Levels và H2 Transaction Isolation — các URL có ở cuối bài.

## 4. Spring JDBC thực hiện `Isolation.DEFAULT` như thế nào?

Về ý tưởng, khi `DataSourceTransactionManager` bắt đầu một transaction JDBC mới:

```text
doBegin()
  -> lấy JDBC Connection
  -> đọc TransactionDefinition.getIsolationLevel()
  -> chuẩn bị connection
     nếu isolation == ISOLATION_DEFAULT:
         KHÔNG ép Connection.setTransactionIsolation(...)
     nếu isolation là mức cụ thể và khác mức đang có:
         ghi lại mức trước đó
         Connection.setTransactionIsolation(requestedLevel)
  -> chuyển sang giao dịch (autoCommit=false nếu cần)
  -> bind Connection vào transaction context
```

Khi transaction kết thúc, Spring cố phục hồi các đặc tính connection đã thay đổi cho transaction đó, bao gồm isolation trước đó nếu Spring đã override. Điều này đặc biệt quan trọng khi connection được **trả lại pool** để các request khác tái sử dụng.

Đây là mô tả cơ chế, **không phải bản sao nguồn Spring**. Spring cung cấp các API liên quan:

- `TransactionDefinition.getIsolationLevel()` — giá trị trong transaction definition.
- `DataSourceUtils.prepareConnectionForTransaction(...)` — chuẩn bị JDBC connection.
- `Connection.getTransactionIsolation()` — đọc mức JDBC **thực tế được báo bởi connection**.
- `Connection.setTransactionIsolation(int)` — yêu cầu connection đổi sang mức JDBC cụ thể.
- `DataSourceUtils.resetConnectionAfterTransaction(...)` — phục hồi isolation cũ khi cần.

**Quan trọng:** Spring chỉ có thể điều khiển những thứ transaction manager và driver hỗ trợ. Một manager không hỗ trợ custom isolation có thể chấp nhận `DEFAULT` nhưng từ chối yêu cầu khác. Database có thể có hành vi ánh xạ, giới hạn hoặc báo lỗi với mức isolation nhất định. Vì thế, đừng chỉ dựa vào enum để hứa DB chắc chắn ngăn được một kiểu bất thường nào đó.

## 5. Sự khác nhau giữa “không override” và “ép `READ_COMMITTED`”

Cùng một service, xét hai method:

```java
@Transactional(isolation = Isolation.DEFAULT)
public void processWithResourceDefault() {
    // ...
}

@Transactional(isolation = Isolation.READ_COMMITTED)
public void processWithExplicitReadCommitted() {
    // ...
}
```

Cả hai chỉ là snippet, không phải project Java độc lập. Giả sử HikariCP cấp JDBC connection đang có isolation `REPEATABLE_READ`:

| Bước | Với `DEFAULT` | Với `READ_COMMITTED` |
| --- | --- | --- |
| Borrow JDBC connection | Có mức `REPEATABLE_READ` | Có mức `REPEATABLE_READ` |
| Spring kiểm tra isolation definition | `-1` | `2` |
| Spring có đổi isolation trước transaction không? | **Không ép đổi** | Có thể gọi `setTransactionIsolation(2)` |
| Isolation đang dùng trong transaction | `REPEATABLE_READ` | `READ_COMMITTED` nếu driver chấp nhận |
| Khi kết thúc | Không cần undo override isolation của Spring | Spring cố phục hồi mức cũ `REPEATABLE_READ` |
| Lần borrow tiếp theo | Theo resource/pool state | Theo resource/pool state đã phục hồi |

Một annotation có `DEFAULT` **không tự chạy lệnh** “đặt connection về mặc định ban đầu của DB”. Nếu connection pool đã cấu hình một mức khác, `DEFAULT` tiếp tục dùng mức đó.

### Vì sao `DEFAULT` không nhất thiết giống mức mặc định DBMS?

Chẳng hạn H2 mặc định `READ_COMMITTED`, nhưng cấu hình HikariCP:

```yaml
spring:
  datasource:
    hikari:
      transaction-isolation: TRANSACTION_REPEATABLE_READ
```

khiến HikariCP cung cấp connection có isolation `REPEATABLE_READ` (nếu driver hỗ trợ). Một transaction Spring bắt đầu với `Isolation.DEFAULT` sẽ **giữ nguyên** isolation của connection đó. Cùng app nhưng bỏ cấu hình trên thì connection mới thường quay về mặc định từ H2/driver, tức `READ_COMMITTED`.

Đây là một ví dụ làm rõ nguyên lý **mặc định của tài nguyên thực tế**. Pool là một phần của hạ tầng cấp tài nguyên, không phải một transaction level mới.

## 6. Khi method tham gia transaction đang tồn tại

Thuộc tính isolation của Spring được thiết kế để có hiệu lực **khi bắt đầu transaction mới**, điển hình với `REQUIRED` khi chưa có transaction hoặc `REQUIRES_NEW` khi mở một transaction độc lập.

Giả sử:

```java
@Service
public class OuterService {

    private final InnerService inner;

    public OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void outer() {
        inner.inner();
    }
}
```

```java
@Service
public class InnerService {

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void inner() {
        // ...
    }
}
```

Hai class là snippet minh họa trong cùng ứng dụng đã bật transaction management. **Nếu** `OuterService.outer()` gọi qua Spring proxy và tạo transaction vật lý T ở `READ_COMMITTED`, lời gọi qua proxy của `InnerService.inner()` với `REQUIRED` **tham gia T**. Mặc định Spring transaction manager **không tạo một T mới** và không tự đổi mức cô lập của physical transaction đang tồn tại thành `SERIALIZABLE`.

```text
Caller
   |
   v
Outer proxy: BEGIN T với READ_COMMITTED
   |
   v
OuterService.outer()
   |
   v
Inner proxy: REQUIRED -> join T
   |  Method khai báo SERIALIZABLE
   |  Nhưng T đã có isolation READ_COMMITTED
   v
InnerService.inner() chạy trong chính T (READ_COMMITTED)
   |
   v
Outer proxy: COMMIT/ROLLBACK T
```

**Quy tắc thực hành:** isolation của **transaction vật lý ngoài** thường thắng khi scope trong tham gia cùng transaction. Đây không phải “inner `SERIALIZABLE` nâng cấp bảo vệ cho một phần nhỏ của T”.

### `validateExistingTransaction`

`AbstractPlatformTransactionManager` có cờ `validateExistingTransaction`:

- **Mặc định thường là `false`**: inner participant có thể join transaction hiện có dù khai báo isolation khác; physical T vẫn giữ isolation của owner.
- **Bật `true`**: manager có thể **từ chối** tham gia khi isolation/read-only khai báo trong inner không tương thích với transaction hiện hữu, thay vì âm thầm chấp nhận mismatch.

Ví dụ cấu hình tường minh:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
```

Đây là **phương án cấu hình thay thế** bean manager của demo ở mục 8, **không thêm bean thứ hai** vào cùng context. Với outer yêu cầu `READ_COMMITTED` và inner yêu cầu `SERIALIZABLE`, manager có thể ném `IllegalTransactionStateException` khi inner cố join. Bật validation hữu ích khi contract của service đòi hỏi tính nhất quán cao, nhưng thay đổi hành vi runtime; phải kiểm thử trước khi áp dụng.

**Lưu ý khác:** dữ liệu `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` phản ánh isolation được Spring công bố trong transaction context, và có thể là `null` khi declaration là `DEFAULT`. Giá trị đó **không thay thế** `Connection.getTransactionIsolation()` để chứng minh effective level của connection.

## 7. `REQUIRES_NEW` và `NESTED`: đừng suy luận từ tên method

| Tình huống | Isolation thực tế của phần inner |
| --- | --- |
| `REQUIRED`, không có T trước đó, `Isolation.DEFAULT` | Transaction mới dùng mức hiện tại của connection/resource |
| `REQUIRED`, đang có T ngoài ở `READ_COMMITTED`, inner `DEFAULT` | Dùng `READ_COMMITTED` của T ngoài |
| `REQUIRED`, đang có T ngoài ở `READ_COMMITTED`, inner yêu cầu `SERIALIZABLE`, validation mặc định tắt | Thường vẫn dùng `READ_COMMITTED` của T ngoài |
| `REQUIRES_NEW`, inner `Isolation.DEFAULT` | Tạm đình chỉ T ngoài; transaction inner mới dùng **connection/resource default** của nó |
| `REQUIRES_NEW`, inner yêu cầu `SERIALIZABLE` | Transaction inner mới yêu cầu `SERIALIZABLE` nếu manager/driver hỗ trợ |
| `NESTED` trong T ngoài | Với JDBC savepoint, dùng **cùng physical transaction và connection** nên không tự có isolation riêng |
| `SUPPORTS` khi không có T | Không tự mở physical transaction; isolation declaration không có effect như một transaction mới |

`REQUIRES_NEW` có thể cần một **connection riêng** trong lúc outer vẫn giữ connection của nó. Pool cần đủ capacity để không gây chờ hoặc cạn connection. `NESTED` dùng savepoint khi manager/driver hỗ trợ và không thể tạo một mức isolation riêng cho “transaction con” trên cùng connection.

**Không đổi propagation chỉ để ép isolation của một đoạn code**, trừ khi bạn thật sự muốn thay đổi boundary, thời điểm commit và atomicity. `REQUIRES_NEW` có transaction riêng: inner có thể commit dù outer sau đó rollback. Đó là thay đổi ý nghĩa nghiệp vụ, không chỉ thay một con số cấu hình.

---

## 8. Ví dụ chạy được với Java 17+, Spring Boot 3.3.5, H2 và HikariCP

Demo dùng H2 vì có thể chạy in-memory; HikariCP là connection pool do `spring-boot-starter-jdbc` đưa vào cấu hình thông thường. Ta **cố ý** cấu hình isolation của pool thành `REPEATABLE_READ` trong khi H2 nguyên bản thường mặc định `READ_COMMITTED`.

Nhờ đó, nếu `Isolation.DEFAULT` thực sự dùng mức của resource, chương trình phải quan sát **`REPEATABLE_READ`** chứ không tự áp `READ_COMMITTED`.

Đồng thời, demo tạo một transaction với `READ_COMMITTED` tường minh, rồi thử:

- `REQUIRED` inner khai báo `SERIALIZABLE`: **tham gia outer**, không đổi isolation.
- `REQUIRES_NEW` inner khai báo `DEFAULT`: **mở transaction mới**, dùng mức của connection mới từ pool.
- Khi transaction `READ_COMMITTED` kết thúc, lần gọi `DEFAULT` kế tiếp thấy pool resource default trở lại.

### 8.1. Cấu trúc project

```text
isolation-default-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/isolation/
    │   │   ├── IsolationProbe.java
    │   │   ├── IsolationOuterService.java
    │   │   └── IsolationDefaultApplication.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/example/isolation/
            └── IsolationDefaultApplicationTest.java
```

Đây là **project hoàn chỉnh** nếu bạn tạo đúng các file dưới đây trong một dự án Gradle có wrapper. Không cần schema vì bài tập đo isolation trực tiếp trên JDBC connection, không cần tạo bảng.

### 8.2. `settings.gradle`

```groovy
rootProject.name = 'isolation-default-demo'
```

### 8.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate`, JDBC transaction manager infrastructure và HikariCP. Spring Boot quản lý phiên bản Spring Framework/Hikari/H2 qua dependency management, nên tránh tự trộn các JAR Spring không cùng version.

### 8.4. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:isolation_default_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 4
      transaction-isolation: TRANSACTION_REPEATABLE_READ
```

Hai thuộc tính quan trọng:

- `spring.datasource.hikari.transaction-isolation`: tên hằng JDBC mà **HikariCP** sử dụng để đặt isolation baseline của connection trong pool. Ở đây là `TRANSACTION_REPEATABLE_READ`, **khác H2 server default**.
- `maximum-pool-size: 4`: cho phép một outer transaction giữ connection trong lúc một `REQUIRES_NEW` inner transaction cần connection thứ hai. Demo không tải cao, nhưng thiết lập làm rõ yêu cầu tài nguyên.

`DB_CLOSE_DELAY=-1` giữ database H2 in-memory cho tới khi JVM kết thúc. Các transaction demo chỉ đọc metadata của connection, không sửa database, do đó không có fixture cần reset.

**Đừng nhầm:** setting `spring.datasource.hikari.transaction-isolation` là một setting **của pool**. Nó không thay đổi giá trị `Isolation.DEFAULT` trong Spring; nó thay đổi **resource isolation level mà `DEFAULT` sẽ kế thừa**.

### 8.5. `src/main/java/example/isolation/IsolationProbe.java`

```java
package example.isolation;

import java.sql.Connection;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class IsolationProbe {
    private final JdbcTemplate jdbc;

    public IsolationProbe(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static String isolationName(int level) {
        return switch (level) {
            case Connection.TRANSACTION_NONE -> "NONE";
            case Connection.TRANSACTION_READ_UNCOMMITTED ->
                "READ_UNCOMMITTED";
            case Connection.TRANSACTION_READ_COMMITTED ->
                "READ_COMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ ->
                "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE ->
                "SERIALIZABLE";
            default -> "UNKNOWN(" + level + ")";
        };
    }

    public String observeConnection() {
        Integer level = jdbc.execute(
            (ConnectionCallback<Integer>) Connection::getTransactionIsolation
        );
        if (level == null) {
            throw new IllegalStateException(
                "JDBC did not return an isolation level"
            );
        }

        boolean active = TransactionSynchronizationManager
            .isActualTransactionActive();

        return isolationName(level) + ", active=" + active;
    }

    @Transactional
    public String implicitDefault() {
        return observeConnection();
    }

    @Transactional(isolation = Isolation.DEFAULT)
    public String explicitDefault() {
        return observeConnection();
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public String explicitReadCommitted() {
        return observeConnection();
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public String requiredRequestSerializable() {
        return observeConnection();
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.DEFAULT
    )
    public String requiresNewResourceDefault() {
        return observeConnection();
    }
}
```

`observeConnection()` gọi `JdbcTemplate.execute(ConnectionCallback)` nên lấy đúng connection JDBC đang được Spring gắn với transaction khi được gọi trong transactional method. Nó **không** tự gọi `dataSource.getConnection()` để vô tình mượn connection khác từ pool.

`TransactionSynchronizationManager.isActualTransactionActive()` giúp kiểm tra method đang ở trong transaction imperative của Spring. Trong demo, các method transactional được gọi từ bên ngoài qua Spring proxy, nên `active=true`.

**Quan trọng:** `observeConnection()` không mang `@Transactional` riêng. Nó là helper được gọi khi một transaction đã mở; self-invocation tới helper **không cần** tạo transaction advice mới. Ngược lại, các method `implicitDefault()`, `explicitReadCommitted()` và `requiredRequestSerializable()` phải được **bean khác gọi qua Spring proxy** để metadata của chính chúng có hiệu lực.

### 8.6. `src/main/java/example/isolation/IsolationOuterService.java`

```java
package example.isolation;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IsolationOuterService {
    private final IsolationProbe probe;

    public IsolationOuterService(IsolationProbe probe) {
        this.probe = probe;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public String requiredJoinsOuter() {
        return probe.requiredRequestSerializable();
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public String newTransactionFromOuter() {
        String inner = probe.requiresNewResourceDefault();
        String resumedOuter = probe.observeConnection();
        return "inner=" + inner + " | outer=" + resumedOuter;
    }
}
```

`requiredJoinsOuter()` tạo physical transaction T ở `READ_COMMITTED`. Method inner `requiredRequestSerializable()` mang `Propagation.REQUIRED`, được gọi **qua bean khác** nên transaction interceptor hoạt động, nhưng nó **tham gia T**. Manager mặc định không ép T lên `SERIALIZABLE` theo annotation của participant.

`newTransactionFromOuter()` cũng bắt đầu T ở `READ_COMMITTED`, nhưng method inner có `REQUIRES_NEW`: Spring tạm đình chỉ T, mượn connection khác, mở transaction mới với `DEFAULT`. Connection mới đến từ pool có baseline `REPEATABLE_READ`. Khi inner kết thúc, outer T được resume với connection `READ_COMMITTED` ban đầu. Kết quả method trả cả hai mức, giúp thấy rõ **hai physical transactions** có isolation khác nhau trong cùng call chain.

### 8.7. `src/main/java/example/isolation/IsolationDefaultApplication.java`

```java
package example.isolation;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Isolation;

@SpringBootApplication
@EnableTransactionManagement
public class IsolationDefaultApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationDefaultApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    ApplicationRunner printResults(
            IsolationProbe probe,
            IsolationOuterService outer) {
        return args -> {
            System.out.println(
                "Isolation.DEFAULT.value()=" + Isolation.DEFAULT.value()
            );
            System.out.println(
                "Implicit DEFAULT=" + probe.implicitDefault()
            );
            System.out.println(
                "Explicit DEFAULT=" + probe.explicitDefault()
            );
            System.out.println(
                "Explicit READ_COMMITTED=" +
                probe.explicitReadCommitted()
            );
            System.out.println(
                "DEFAULT after override=" + probe.explicitDefault()
            );
            System.out.println(
                "REQUIRED joined=" + outer.requiredJoinsOuter()
            );
            System.out.println(
                "REQUIRES_NEW DEFAULT=" + outer.newTransactionFromOuter()
            );
        };
    }
}
```

Ứng dụng định nghĩa **một `PlatformTransactionManager` duy nhất**, dùng đúng `DataSource` mà `JdbcTemplate` sử dụng. `@EnableTransactionManagement` bật transaction interception. `ApplicationRunner` nhận các service bean từ Spring container, do đó các lời gọi công khai **đi qua proxy**, tránh lỗi self-invocation.

`new DataSourceTransactionManager(dataSource)` dùng default `validateExistingTransaction=false`, đúng tiền đề khi inner `REQUIRED` đưa ra isolation request không tương thích nhưng vẫn được phép join trong demo.

### 8.8. Chạy ứng dụng

Trên Linux/macOS:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu project chưa có Gradle wrapper, có thể dùng `gradle bootRun` sau khi đã cài bản Gradle tương thích, hoặc tạo wrapper bằng Gradle. Không dùng `javac`/`java` mà bỏ classpath Spring/H2.

**Những dòng do ứng dụng in ra**, không tính startup logs của Spring Boot/Hikari/Gradle:

```text
Isolation.DEFAULT.value()=-1
Implicit DEFAULT=REPEATABLE_READ, active=true
Explicit DEFAULT=REPEATABLE_READ, active=true
Explicit READ_COMMITTED=READ_COMMITTED, active=true
DEFAULT after override=REPEATABLE_READ, active=true
REQUIRED joined=READ_COMMITTED, active=true
REQUIRES_NEW DEFAULT=inner=REPEATABLE_READ, active=true | outer=READ_COMMITTED, active=true
```

Đây là kết quả **dự kiến dựa trên code, cấu hình Hikari và H2**, không phải khẳng định đã thực thi Gradle trong môi trường này. Các giá trị isolation là tên chuyển đổi từ `Connection.getTransactionIsolation()` trong code.

### 8.9. Giải thích chính xác từng dòng

**`Isolation.DEFAULT.value()=-1`:** xác nhận đây là sentinel của Spring, không phải JDBC `Connection.TRANSACTION_NONE` hay một mức cô lập cố định.

**`Implicit DEFAULT` và `Explicit DEFAULT`:** có cùng kết quả `REPEATABLE_READ` vì cả hai để transaction manager dùng mức của connection Hikari cung cấp. Việc annotation ghi chữ `DEFAULT` hay không không thay đổi kết quả.

**`Explicit READ_COMMITTED`:** vì Spring đã tạo transaction mới có yêu cầu cụ thể, manager tạm đổi isolation từ baseline `REPEATABLE_READ` thành `READ_COMMITTED` trên connection. Driver H2 hỗ trợ mức này.

**`DEFAULT after override`:** sau khi method explicit kết thúc, Spring/connection pool khôi phục trạng thái connection phù hợp. Transaction mới `DEFAULT` lại thấy baseline `REPEATABLE_READ`, không bị một request trước đó “để lại” `READ_COMMITTED`.

**`REQUIRED joined`:** outer đã mở physical transaction `READ_COMMITTED`. Inner yêu cầu `SERIALIZABLE` nhưng chỉ tham gia T, nên quan sát thực tế là `READ_COMMITTED`. Đây là lý do đừng tin rằng khai báo isolation cao trong một method `REQUIRED` nhất định sẽ tăng isolation khi nó được gọi từ service ngoài.

**`REQUIRES_NEW DEFAULT`:** inner được cấp transaction riêng và connection khác từ pool, thấy `REPEATABLE_READ`; sau đó outer tiếp tục trên T với `READ_COMMITTED`. Hai mức cùng tồn tại nhưng thuộc **hai transactions vật lý khác nhau**.

## 9. Kiểm thử JUnit 5 để ngăn thay đổi cấu hình không chủ ý

Tạo `src/test/java/example/isolation/IsolationDefaultApplicationTest.java`:

```java
package example.isolation;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Isolation;

@SpringBootTest
class IsolationDefaultApplicationTest {
    @Autowired IsolationProbe probe;
    @Autowired IsolationOuterService outer;

    @Test
    void defaultIsSpringSentinelNotAConcreteJdbcLevel() {
        assertEquals(-1, Isolation.DEFAULT.value());
    }

    @Test
    void implicitAndExplicitDefaultsUseConfiguredResource() {
        assertEquals(
            "REPEATABLE_READ, active=true",
            probe.implicitDefault()
        );
        assertEquals(
            "REPEATABLE_READ, active=true",
            probe.explicitDefault()
        );
    }

    @Test
    void explicitOverrideIsTemporaryForThisTransaction() {
        assertEquals(
            "READ_COMMITTED, active=true",
            probe.explicitReadCommitted()
        );
        assertEquals(
            "REPEATABLE_READ, active=true",
            probe.explicitDefault()
        );
    }

    @Test
    void requiredParticipantKeepsOuterIsolation() {
        assertEquals(
            "READ_COMMITTED, active=true",
            outer.requiredJoinsOuter()
        );
    }

    @Test
    void requiresNewUsesItsOwnResourceDefault() {
        assertEquals(
            "inner=REPEATABLE_READ, active=true | " +
            "outer=READ_COMMITTED, active=true",
            outer.newTransactionFromOuter()
        );
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test không mang `@Transactional`, nên không bị test framework tự mở một transaction bao ngoài làm thay đổi câu hỏi “method này có thật sự bắt đầu transaction mới không?”. `@SpringBootTest` có thể gọi `ApplicationRunner` khi dựng context và in những dòng từ demo; điều đó không tác động đến assertions vì mỗi case chỉ quan sát JDBC connection metadata, không sửa dữ liệu.

**Không dùng Mockito để xác nhận effective isolation.** Mock `JdbcTemplate` hoặc mock transaction manager có thể chứng minh code gọi một API, nhưng không chứng minh Hikari/driver/database thực tế cấp connection ở isolation nào. Test tích hợp trên DB/driver đại diện gần với production là lựa chọn đúng.

### Nếu xóa cấu hình `hikari.transaction-isolation` thì sao?

Với H2 mặc định, hai dòng `DEFAULT` ở demo dự kiến trở thành `READ_COMMITTED`, trong khi explicit `READ_COMMITTED` vẫn là `READ_COMMITTED`. Bài kiểm thử hiện tại **cố ý assert `REPEATABLE_READ`** để bảo vệ hợp đồng cấu hình pool. Nếu xóa setting, cần sửa assertion theo yêu cầu mới, không coi test fail là Spring chọn sai default.

### Nếu đổi sang PostgreSQL hoặc MySQL thì sao?

Không sửa assertion theo suy đoán. Chạy một test tích hợp thực sự với database, JDBC driver, pool, quyền và cấu hình session tương ứng. Đặc biệt chú ý mức mặc định của **connection đi ra từ pool** chứ không chỉ tham khảo mức mặc định ghi trên trang tài liệu DBMS.

## 10. Không nên đo bằng connection không tham gia transaction

Một cách dễ gây nhầm lẫn:

```java
@Transactional
public void businessMethod() throws Exception {
    try (Connection other = dataSource.getConnection()) {
        System.out.println(other.getTransactionIsolation());
    }
}
```

Đây là snippet minh họa có `DataSource` sẵn, không phải file hoàn chỉnh. Nếu `dataSource` là pool, `getConnection()` có thể mượn **một connection khác** không phải connection được Spring bind vào transaction hiện tại. Kết quả có thể phản ánh baseline của pool nhưng không phải effective isolation của SQL nghiệp vụ trong T.

Để đo isolation của **chính transactional connection** trong Spring JDBC, dùng `JdbcTemplate.execute(ConnectionCallback)` như code demo, hoặc dùng `DataSourceUtils.getConnection(dataSource)` theo contract và nhớ release đúng API:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    int effectiveLevel = connection.getTransactionIsolation();
    System.out.println(effectiveLevel);
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

Đoạn này cũng chỉ là snippet, cần import `DataSource`, `Connection`, `DataSourceUtils` và một context đang quản lý transaction. Không tự `connection.close()` tùy tiện trên connection đang Spring bind nếu bạn lấy theo cơ chế transaction-aware và chưa hiểu quy tắc release.

Một phép đo hữu ích khác là:

```java
Integer declaredLevel = TransactionSynchronizationManager
    .getCurrentTransactionIsolationLevel();
```

Nhưng giá trị trên có thể `null` khi transaction dùng `Isolation.DEFAULT`. `null` không có nghĩa database đang chạy `TRANSACTION_NONE` hay không có isolation. Muốn biết isolation JDBC **thực tế**, đọc `Connection.getTransactionIsolation()`.

## 11. Vì sao connection pool là một phần của câu trả lời?

Pool không chỉ giảm chi phí mở kết nối. Nó còn có thể quản lý **trạng thái mặc định của mỗi connection**:

- Isolation level.
- `autoCommit`.
- Read-only state.
- Default catalog/schema.
- Initialization SQL hoặc session-level settings theo công cụ/driver.

HikariCP có thuộc tính `transactionIsolation`, nhận giá trị như `TRANSACTION_READ_COMMITTED` và `TRANSACTION_REPEATABLE_READ`. Nếu thuộc tính **không đặt**, Hikari thông thường kế thừa mức mà driver/database cung cấp cho connection. Nếu thuộc tính **được đặt**, connection từ pool có thể có một baseline khác với DB default.

Điều này làm rõ sự khác nhau giữa hai câu:

- **“Mặc định của database server là READ_COMMITTED.”** Đây là một setting/tài liệu của server.
- **“Connection mà Spring dùng có isolation REPEATABLE_READ.”** Đây là trạng thái của tài nguyên JDBC **trong ứng dụng**; có thể do pool hoặc session settings.

Spring `Isolation.DEFAULT` thường chọn cách **không override câu thứ hai**, chứ không truy cập server để tra lại câu thứ nhất rồi ép connection trở về đó.

### Trạng thái bị “rò rỉ” giữa các lần dùng connection

Nếu application tự chạy một lệnh SQL đổi **session isolation** hoặc tự gọi `Connection.setTransactionIsolation` ngoài transaction manager, pool có thể phát hiện và reset theo API được hỗ trợ, hoặc có thể **không biết** một thay đổi chỉ thực hiện bằng SQL session-specific. Kết quả là một connection sau khi trả pool có thể mang trạng thái không mong muốn cho người mượn tiếp theo.

Vì vậy:

1. Chọn một nơi rõ ràng để cấu hình isolation baseline (database/session/pool).
2. Ưu tiên `@Transactional(isolation = ...)` cho override của transaction cụ thể, để transaction manager quản lý vòng đời.
3. Tránh đổi isolation giữa một transaction đang thực hiện SQL khi database có giới hạn hoặc câu lệnh có implicit commit.
4. Không giả định pool tự chữa mọi câu `SET SESSION ...` viết thủ công.
5. Dùng integration test quan sát mức thực tế qua transactional connection.

## 12. Isolation ảnh hưởng lỗi đọc nào? `DEFAULT` không trả lời câu hỏi này

Khi nhiều transaction chạy đồng thời, DBMS cần quyết định các câu lệnh được phép nhìn thấy bản ghi nào. Bốn mức isolation JDBC quen thuộc liên quan đến:

- **Dirty read:** một transaction đọc dữ liệu transaction khác chưa commit.
- **Non-repeatable read:** cùng một hàng đọc hai lần trong một transaction nhưng nhận giá trị khác nhau do transaction khác commit.
- **Phantom:** cùng một điều kiện truy vấn nhận tập hàng khác nhau sau transaction khác commit thêm/xóa hàng phù hợp.
- **Serialization anomalies:** kết quả của các transaction đồng thời không tương đương một lịch thực thi tuần tự hợp lệ.

Bảng tổng quan theo định nghĩa cổ điển của các mức isolation; DBMS cụ thể có thể triển khai mạnh/yếu hơn một số trực giác trong bảng:

| Mức JDBC | Dirty read | Non-repeatable read | Phantom theo định nghĩa cổ điển |
| --- | --- | --- | --- |
| `READ_UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ_COMMITTED` | Không | Có thể | Có thể |
| `REPEATABLE_READ` | Không | Không theo định nghĩa mức | Phụ thuộc định nghĩa/DBMS |
| `SERIALIZABLE` | Không | Không | Không trong mô hình tuần tự hóa đúng |

**Đừng cố đưa `DEFAULT` thành một hàng trong bảng**: `DEFAULT` không phải level kỹ thuật của engine. Nếu `DEFAULT` quan sát thành `READ_COMMITTED`, phân tích lỗi đọc theo semantics `READ_COMMITTED` của database đó; nếu thành `REPEATABLE_READ`, phải xem semantics `REPEATABLE_READ` thực tế của engine đó.

Ví dụ PostgreSQL có MVCC và triển khai `REPEATABLE READ` theo snapshot isolation với các tính chất không trùng một-một cách hiểu cổ điển về phantom. MySQL InnoDB có consistent nonlocking reads và locking reads với cơ chế khác nhau. Từ enum trong Spring **không thể** suy ra mọi chi tiết của engine.

### Một lịch đọc minh họa

```text
T1 (DEFAULT -> READ_COMMITTED)     T2
--------------------------------  --------------------------
BEGIN
SELECT price FROM products WHERE id=1  -> 100
                                  BEGIN
                                  UPDATE products SET price=120 WHERE id=1
                                  COMMIT
SELECT price FROM products WHERE id=1  -> có thể là 120
COMMIT
```

Đây là ví dụ **khái niệm về non-repeatable read**. Giá trị quan sát phụ thuộc DBMS, statement type, isolation thật của connection và transaction T2. Nếu `DEFAULT` thực tế là `REPEATABLE_READ`, cùng lịch đọc có thể cho hai lần đọc cùng một snapshot với cùng giá trị, tùy engine.

**Điểm học:** phải quan sát hoặc xác định effective isolation, rồi mới đánh giá concurrency anomalies. Không viết test concurrency chỉ với giả định “Spring mặc định luôn READ_COMMITTED”.

## 13. Vì sao cấu hình `Isolation.DEFAULT` thường là lựa chọn tốt?

Nhiều ứng dụng có transaction service đơn giản:

```java
@Service
public class CatalogService {
    @Transactional(readOnly = true)
    public ProductView load(long id) {
        return repository.load(id);
    }
}
```

Snippet này minh họa một service có repository/DTO từ ứng dụng. `@Transactional(readOnly = true)` vẫn để **isolation mặc định**, không biến thành một isolation level khác chỉ vì read-only.

Giữ `DEFAULT` thường phù hợp khi:

- DBA hoặc platform team đã định nghĩa một **isolation policy hợp lý ở DB/pool** cho workload của hệ thống.
- Các transaction không đòi cơ chế consistency đặc biệt bên ngoài default.
- Ứng dụng cần chạy trên nhiều môi trường nhưng mỗi môi trường được test và quản lý resource policy rõ.
- Muốn tránh chi phí/giới hạn của việc ép `SERIALIZABLE` không cần thiết.
- Không muốn mỗi service method lặp một mức isolation giống nhau khi chính sách thống nhất đã nằm ở tầng datasource.

Tuy nhiên, `DEFAULT` **không đồng nghĩa “cứ để tự chạy là an toàn”**. Với các operation như đặt hàng, trừ tồn kho, tạo số thứ tự, chuyển tiền hoặc xác nhận thanh toán, vẫn phải thiết kế invariant, constraints, optimistic locking, conditional `UPDATE`, retry khi có serialization error và test concurrency phù hợp. Isolation chỉ là một phần của hệ thống đảm bảo nhất quán.

### Khi nào nên khai báo mức cụ thể?

Nếu nghiệp vụ có một yêu cầu concurrency đủ rõ, và DB/transaction manager hỗ trợ:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void allocateSequence() {
    // ...
}
```

Snippet này cần method đi qua Spring proxy và **bắt đầu transaction vật lý mới** thì yêu cầu mới có thể được áp dụng. Nếu method chỉ tham gia T ngoài có isolation yếu hơn, không được giả định annotation này tự nâng cấp T. Có thể dùng validation để tránh mismatch, hoặc sắp xếp transaction boundary sao cho method sở hữu T đúng mức ngay từ đầu.

Ngay cả ở `SERIALIZABLE`, DB có thể phát hiện serialization conflict và **abort một transaction**; application cần chiến lược retry an toàn và idempotency. Đừng diễn giải mức cô lập cao là “không bao giờ gặp deadlock hoặc lỗi”.

## 14. Một transaction mới, một participant, và transaction độc lập

Bảng quyết định nhanh:

| Caller có T? | Propagation của method | Isolation declaration | Spring JDBC thường làm gì? |
| --- | --- | --- | --- |
| Không | `REQUIRED` | `DEFAULT` | Bắt đầu T mới, giữ resource connection isolation |
| Không | `REQUIRED` | `READ_COMMITTED` | Bắt đầu T mới, yêu cầu JDBC `READ_COMMITTED` |
| Có | `REQUIRED` | `DEFAULT` | Join T, dùng isolation của T |
| Có | `REQUIRED` | `SERIALIZABLE` | Mặc định join T và không tự đổi isolation; validation có thể từ chối mismatch |
| Có | `REQUIRES_NEW` | `DEFAULT` | Tạm dừng T ngoài, mở T mới dùng resource default của connection mới |
| Có | `REQUIRES_NEW` | `READ_COMMITTED` | Mở T mới, yêu cầu `READ_COMMITTED` |
| Có | `NESTED` | `DEFAULT` | Dùng savepoint trong T (nếu hỗ trợ), kế thừa isolation của T |
| Không | `SUPPORTS` | `DEFAULT` | Không tạo physical transaction chỉ vì annotation |

**Đọc bảng từ trái sang phải.** Nếu bạn bắt đầu từ isolation enum mà bỏ qua “transaction mới hay join?”, bạn rất dễ rút ra kết luận sai.

### Những ranh giới proxy có thể làm bảng thay đổi

`@Transactional` theo mặc định của Spring AOP cần lời gọi **qua Spring proxy**. Ví dụ:

```java
@Service
public class WrongService {

    public void outer() {
        inner();
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void inner() {
        // ...
    }
}
```

`outer()` gọi `this.inner()` nên invocation bên trong không đi lại qua proxy của chính bean. Nếu không có transaction boundary nào khác, `inner()` có thể không nhận transaction advice dù annotation hiện diện. Đổi từ JDK proxy sang CGLIB **không chữa** self-invocation trong proxy mode.

Tách transactional method sang một bean khác, hoặc đặt annotation đúng ở entrypoint mà caller thực sự gọi, hoặc dùng programmatic transaction API là những lựa chọn rõ ràng hơn.

## 15. Tự kiểm chứng trong môi trường thật

Trước khi kết luận `Isolation.DEFAULT` của production là gì, hãy kiểm tra từ **đường thực thi ứng dụng**.

### 15.1. Đọc JDBC connection đang tham gia transaction

```java
@Transactional
public int currentIsolation(JdbcTemplate jdbc) {
    Integer level = jdbc.execute(
        (ConnectionCallback<Integer>) Connection::getTransactionIsolation
    );
    if (level == null) {
        throw new IllegalStateException("No JDBC isolation reported");
    }
    return level;
}
```

Đây là **snippet minh họa ý tưởng**, không phải class độc lập. Method annotation chỉ có tác dụng nếu được Spring transaction infrastructure xử lý; imports cũng giống project ở mục 8. Ở code service thật, injection `JdbcTemplate` qua constructor thường tốt hơn truyền vào argument.

Quan trọng nhất là `JdbcTemplate` lấy **connection thuộc transaction hiện tại**. Nếu bạn chỉ gọi `dataSource.getConnection()` từ thread khác hoặc mượn một connection khác, kết quả có thể không phản ánh transaction đang điều tra.

### 15.2. Kiểm tra session setting ở DBMS

DBMS có công cụ riêng. Ví dụ:

```sql
-- PostgreSQL: mức cô lập của transaction hiện tại
SHOW transaction_isolation;
```

```sql
-- MySQL: mức cô lập của session hiện tại
SELECT @@transaction_isolation;
```

Đây là cú pháp cho hai DBMS riêng, **không chạy nguyên hai block trên H2**. Cần thực thi trên connection/session đúng đang phục vụ transaction cần kiểm tra; chạy một SQL client độc lập có thể chỉ cho bạn mức của session trong client đó, không phải connection của application.

Khi điều tra sự khác biệt dev/staging/prod, đối chiếu:

1. Database name/version/engine và server configuration.
2. Driver và JDBC URL.
3. HikariCP/pool isolation property, initialization SQL.
4. Transaction manager cụ thể (`DataSourceTransactionManager`, `JdbcTransactionManager`, `JpaTransactionManager`, manager khác).
5. Annotation/propagation và xem method thật sự bắt đầu T mới hay join T.
6. `Connection.getTransactionIsolation()` **ngay trong transactional method**.
7. Concurrency test và query behavior đặc thù DBMS.

### 15.3. Dùng log đúng mức

Trong môi trường debug, có thể bổ sung:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.jdbc.datasource.DataSourceTransactionManager: DEBUG
```

Đây là tùy chọn chẩn đoán, **không cần** cho stdout của demo. Không nên bật TRACE trên hệ thống tải cao nếu chưa đánh giá volume/log privacy. Log transaction manager giúp theo dõi bắt đầu/participate/commit/rollback, nhưng muốn biết effective JDBC level vẫn nên đọc connection hoặc session chính xác.

## 16. Lỗi thường gặp và cách sửa

| Nhận định hoặc triệu chứng | Vì sao có thể sai | Hướng xử lý |
| --- | --- | --- |
| “`Isolation.DEFAULT` nghĩa là `READ_COMMITTED`.” | DEFAULT chỉ là sentinel `-1` | Đọc connection; kiểm tra DB/pool |
| “`DEFAULT` nghĩa là không có isolation.” | Không phải `TRANSACTION_NONE` | Phân biệt metadata Spring với JDBC level |
| “Spring luôn tự đặt isolation về mặc định của DB.” | Với DEFAULT Spring JDBC thường **không override connection** | Kiểm tra resource state tại thời điểm borrow |
| “H2 mặc định READ_COMMITTED nên demo phải in READ_COMMITTED.” | Demo cố ý cấu hình Hikari `REPEATABLE_READ` | Xem `spring.datasource.hikari.transaction-isolation` |
| “Method inner `SERIALIZABLE` sẽ nâng isolation của outer.” | Inner `REQUIRED` chỉ tham gia physical T đã có | Đặt boundary đúng hoặc bật validation |
| “Method inner `DEFAULT` trong `REQUIRES_NEW` kế thừa isolation outer.” | `REQUIRES_NEW` tạo T riêng, thường connection khác | Đọc isolation của connection inner |
| “Cùng tên DB là cùng connection.” | Connection pool cấp nhiều connection/session | Dùng transaction-bound connection để đo |
| “Sau khi explicit override, pool sẽ giữ mãi mức đó.” | Spring/pool quản lý reset khi kết thúc transaction | Test `DEFAULT after override` |
| “Chỉ cần đọc `TransactionSynchronizationManager` là biết level.” | `DEFAULT` có thể cho context isolation là `null` | Dùng `Connection.getTransactionIsolation()` |
| “READ_ONLY đồng nghĩa SERIALIZABLE.” | Read-only là một thuộc tính khác | Kiểm tra `isolation` và read-only riêng |
| “Tăng isolation có thể sửa mọi lost update.” | Còn phụ thuộc DB, SQL, locking, constraint, retry | Thiết kế invariant và test concurrent |
| “Tất cả transaction managers hỗ trợ custom isolation.” | Một số resource/manager không hỗ trợ | Kiểm tra API và driver, có thể cần `DEFAULT` |
| “Đổi DB mà không cần kiểm thử khi dùng DEFAULT.” | Resource default có thể khác | Có integration/concurrency tests |
| “Annotation có mặt nghĩa là interceptor chạy.” | Self-invocation, `new`, method không được proxy | Kiểm tra Spring bean/proxy call path |
| “Session SQL luôn an toàn giữa transaction.” | Một số lệnh thay isolation có timing/commit constraints | Dùng transaction manager, hiểu DBMS |

## 17. Bài tập tình huống

### Tình huống A: cùng code, hai datasource

Service:

```java
@Transactional(isolation = Isolation.DEFAULT)
public void report() {
    // ...
}
```

Ở môi trường A, resource connection có isolation `READ_COMMITTED`. Ở môi trường B, pool cấu hình `REPEATABLE_READ`.

**Hỏi:** Spring có tự làm hai môi trường giống nhau không?

**Đáp án:** Không. Cùng metadata `DEFAULT` chỉ biểu thị Spring không áp mức riêng; isolation thực tế có thể khác theo connection của từng resource. Phải test cả hai môi trường hoặc đặt policy nhất quán.

### Tình huống B: outer `READ_COMMITTED`, inner `SERIALIZABLE`

Outer đã bắt đầu T, inner `REQUIRED` join cùng T; validation mặc định tắt.

**Hỏi:** Inner có thực thi ở `SERIALIZABLE` không?

**Đáp án:** Thông thường không; nó chạy trong T ở `READ_COMMITTED`. Nếu bật validate existing transaction, request không tương thích có thể bị từ chối thay vì bị bỏ qua.

### Tình huống C: outer `READ_COMMITTED`, inner `REQUIRES_NEW DEFAULT`

Pool có `TRANSACTION_REPEATABLE_READ`.

**Hỏi:** Isolation của inner là gì?

**Đáp án:** Nếu driver/manager hỗ trợ và connection mới từ pool có baseline như cấu hình, inner chạy `REPEATABLE_READ`. Outer tiếp tục ở `READ_COMMITTED` sau khi inner kết thúc.

### Tình huống D: in `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()`

Method mới có `Isolation.DEFAULT` trả `null` từ API context.

**Hỏi:** Có chứng minh DB đang không có isolation không?

**Đáp án:** Không. `null` ở đây có thể chỉ có nghĩa Spring không ghi isolation override vào transaction metadata. Phải đọc `Connection.getTransactionIsolation()`.

### Tình huống E: không hề gọi SQL

Một method được `@Transactional` mở transaction mới và đọc connection isolation, nhưng không SELECT/UPDATE.

**Hỏi:** Việc đo mức isolation có ý nghĩa không?

**Đáp án:** Có, vì nó xác nhận mức JDBC connection đang sử dụng, nhưng **chưa chứng minh** DBMS sẽ ngăn các concurrency anomalies nào trong dữ liệu thực. Muốn kiểm chứng hành vi giao dịch, viết test nhiều connection và SQL thích hợp.

### Tình huống F: di chuyển từ H2 test sang MySQL InnoDB production

H2 chạy `READ_COMMITTED` mặc định, MySQL InnoDB thường `REPEATABLE_READ` mặc định, service dùng `Isolation.DEFAULT`.

**Hỏi:** Có thể coi semantics test và production giống nhau không?

**Đáp án:** Không. Trước hết kiểm tra pool/session thật; nếu isolation khác, các quan sát concurrent reads/locks có thể khác. Test H2 hữu ích để chứng minh Spring wiring, nhưng không thay thế integration test trên engine production.

## 18. Checklist lựa chọn và kiểm chứng `ISOLATION_DEFAULT`

1. Xác định transaction manager thực tế và tài nguyên mà nó quản lý.
2. Hiểu `Isolation.DEFAULT` là **`ISOLATION_DEFAULT = -1`**, không phải một JDBC isolation level.
3. Kiểm tra `@Transactional` có chạy qua Spring proxy và method có thật sự mở transaction vật lý mới không.
4. Nếu `REQUIRED` join T đã có, dùng isolation của T đó; không kỳ vọng annotation inner tự đổi isolation.
5. Nếu `REQUIRES_NEW`, kiểm tra isolation của **connection/resource mới**, cùng rủi ro connection pool.
6. Nếu dùng pool, xem chính sách `transactionIsolation` và initialization/session settings; không chỉ DB default.
7. Đo effective level bằng `Connection.getTransactionIsolation()` **trên transaction-bound connection**.
8. Xác minh Spring/driver restore isolation sau khi một transaction explicit isolation kết thúc.
9. Nếu service có yêu cầu consistency riêng, đặt isolation tại đúng outer physical transaction boundary hoặc bật validation để phát hiện mismatch.
10. Không suy ra đầy đủ MVCC/locking/phantom semantics chỉ từ tên mức isolation; kiểm thử trên DBMS thực tế.
11. Giữ điều kiện nghiệp vụ đúng bằng constraints, conditional updates, lock/retry khi cần; isolation không thay tất cả các lớp bảo vệ.
12. Ghi rõ default isolation mong đợi của mỗi môi trường; dùng integration tests để cảnh báo khi datasource/pool/database configuration thay đổi.

## Tài liệu tham khảo chính thức

- Spring Framework — `@Transactional` settings và mặc định isolation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `TransactionDefinition` API, `ISOLATION_DEFAULT`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — `Isolation` enum: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/annotation/Isolation.html
- Spring Framework — `DataSourceTransactionManager`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `DataSourceUtils` và JDBC connection preparation: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — Transaction Propagation (`REQUIRED`, `REQUIRES_NEW`, `NESTED`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- HikariCP — Configuration, thuộc tính `transactionIsolation`: https://github.com/brettwooldridge/HikariCP/wiki/Configuration
- H2 Database — Transaction Isolation: https://h2database.com/html/advanced.html#transaction_isolation
- PostgreSQL — `SET TRANSACTION`, mặc định `READ COMMITTED`: https://www.postgresql.org/docs/current/sql-set-transaction.html
- MySQL 8.4 — InnoDB Transaction Isolation Levels, mặc định `REPEATABLE READ`: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html