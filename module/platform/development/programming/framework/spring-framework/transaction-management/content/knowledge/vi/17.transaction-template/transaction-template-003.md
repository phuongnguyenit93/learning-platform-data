# TransactionTemplate: execute và executeWithoutResult trong Spring Transaction Management

## 1. Khi nào cần điều khiển transaction bằng code?

Phần lớn ứng dụng Spring quản lý transaction theo cách khai báo:

```java
@Transactional
public void createOrder() {
    // Các thao tác DB.
}
```

Với `@Transactional`, Spring AOP và `PlatformTransactionManager` xác định lúc bắt đầu, commit hay rollback ở ranh giới phương thức được proxy gọi. Cách này thường gọn và nên ưu tiên khi phần lớn nghiệp vụ đều có ranh giới transaction cố định.

Tuy nhiên, đôi khi cần **chọn một khối code cụ thể** làm transaction mà không muốn toàn bộ method bao ngoài nằm trong transaction. Ví dụ: đọc dữ liệu từ API ở ngoài transaction, tính một phương án, rồi chỉ bao **hai câu SQL cuối** trong cùng transaction. Hoặc một method có nhiều nhánh, mỗi nhánh cần isolation/propagation khác nhau.

Trong các trường hợp đó, Spring cung cấp `org.springframework.transaction.support.TransactionTemplate` để quản lý giao dịch **programmatic** (bằng code). Nó lấy `PlatformTransactionManager` và nhận một callback chứa các thao tác cần chạy trong scope transaction.

Hai API học trong bài:

```java
<T> T execute(TransactionCallback<T> action);

void executeWithoutResult(
    java.util.function.Consumer<TransactionStatus> action);
```

Chúng đều chạy code trong scope được điều phối bởi transaction manager, tự xử lý khởi tạo/tham gia transaction, commit hoặc rollback khi callback hoàn tất. Khác biệt cốt lõi là **callback có trả dữ liệu cho caller hay không**.

- `execute(...)`: cần **giá trị trả về**, ví dụ mã đơn hàng, tổng tiền, một DTO hoặc kết quả SELECT.
- `executeWithoutResult(...)`: chỉ cần **thực hiện tác vụ**, không phải trả một giá trị nghiệp vụ; kiểu trả về của phương thức là `void`.

**Quan trọng:** cả hai đều nhận được `TransactionStatus` trong lambda. `executeWithoutResult` không có nghĩa “không thể rollback thủ công”; có thể gọi `status.setRollbackOnly()` như với `execute`.

## 2. Vị trí của TransactionTemplate trong Spring

Sơ đồ:

```text
Service / application code
   |
   +-- transactionTemplate.execute(callback)
   |       hoặc
   +-- transactionTemplate.executeWithoutResult(callback)
                |
                v
         TransactionTemplate
                |
                v
         PlatformTransactionManager
                |
      +---------+----------+
      |                    |
      v                    v
 JDBC DataSource        JPA EntityManager
 /connection manager    /transaction manager
      |                    |
      +---------+----------+
                |
        Resource transaction:
      begin / participate / commit / rollback
```

`TransactionTemplate` tự nó **không** chứa kết nối DB và không tạo bảng. Nó cần một transaction manager thích hợp:

- Với Spring JDBC, thường dùng `JdbcTransactionManager` hoặc `DataSourceTransactionManager` gắn với đúng `DataSource`.
- Với JPA, dùng `JpaTransactionManager` phù hợp với `EntityManagerFactory`.
- Với reactive (R2DBC/WebFlux), cơ chế tương ứng là `TransactionalOperator`; không áp dụng trực tiếp mô hình callback imperative vào một reactive chain rồi cho rằng transaction tự đi theo tín hiệu bất đồng bộ.

Spring Boot có thể tự cấu hình manager nếu đủ dependency và chỉ có một tài nguyên thích hợp. Trong dự án không dùng Boot, phải cấu hình các bean này một cách rõ ràng.

**Khác với lời gọi qua `@Transactional` proxy:** khi application gọi trực tiếp `transactionTemplate.execute(...)`, scope transaction của template được kích hoạt **bằng lời gọi method đó**, không phụ thuộc việc method chứa lời gọi template có được Spring AOP proxy intercept hay không. Dù vậy, template vẫn cần đúng manager và các DAO phải dùng tài nguyên tham gia transaction do Spring quản lý.

## 3. API và callback khác nhau ở kiểu trả về

### 3.1. `execute(TransactionCallback<T>)`

`TransactionCallback<T>` có một method nhận `TransactionStatus` và trả `T`:

```java
@FunctionalInterface
public interface TransactionCallback<T> {
    T doInTransaction(TransactionStatus status);
}
```

Đây là **chữ ký rút gọn để giải thích**, không phải mã định nghĩa lại interface vào dự án. `TransactionTemplate.execute(...)` trả kết quả do callback tạo ra; trong một transaction mới bình thường, việc commit/rollback được template xử lý sau khi callback trả về.

Ví dụ khi cần ID vừa tạo:

```java
Long id = tx.execute(status -> {
    jdbc.update(
        "INSERT INTO customers(id, name) VALUES (?, ?)",
        42L, "Mai");
    return 42L;
});
```

Ví dụ dùng `JdbcTemplate` và bảng `customers` đã được tạo sẵn; đây là **mảnh code minh họa**. Khi callback kết thúc, template cố hoàn tất transaction rồi phương thức `execute` mới trả kết quả. Giá trị trả về có thể là `null` nếu callback trả `null`.

Quan trọng:

- `return 42L` trong lambda **không** có nghĩa “vừa thực thi `COMMIT` bằng lệnh return”.
- Nếu code gắn `status.setRollbackOnly()` rồi vẫn `return 42L`, caller **vẫn có thể nhận 42L**, mặc dù thay đổi DB đã rollback. **Kết quả callback không phải bằng chứng commit.**
- Nếu callback ném `RuntimeException` hoặc `Error` ra ngoài, template thường yêu cầu rollback theo contract và chuyển lỗi cho caller.
- Nếu commit hoặc rollback của manager thất bại, caller có thể nhận `TransactionException`/ngoại lệ liên quan thay vì giá trị callback.

### 3.2. `executeWithoutResult(Consumer<TransactionStatus>)`

Khi không cần trả về dữ liệu:

```java
tx.executeWithoutResult(status -> {
    jdbc.update(
        "UPDATE customers SET active = ? WHERE id = ?",
        true, 42L);
});
```

Đây cũng là mảnh minh họa: `tx` là `TransactionTemplate` hoặc `TransactionOperations` có manager thật, `jdbc` được cấu hình đúng.

**Consumer có một tham số `TransactionStatus`.** Cú pháp là `status -> { ... }`, **không phải** một `Runnable` kiểu `() -> { ... }`. Callback không cần viết `return null`. Một `return;` đơn thuần có thể dùng để kết thúc sớm callback kiểu `void` nhưng vẫn đi qua logic kết thúc transaction của template.

Ví dụ đánh dấu rollback:

```java
tx.executeWithoutResult(status -> {
    jdbc.update(
        "INSERT INTO customers(id, name) VALUES (?, ?)",
        43L, "An");

    boolean rejected = true;
    if (rejected) {
        status.setRollbackOnly();
        return;
    }
});
```

Nếu template bắt đầu transaction vật lý mới và không có lỗi khác, dữ liệu ID 43 sẽ bị rollback dù callback **không ném exception**.

### 3.3. Phương thức không trả kết quả không đồng nghĩa chạy “fire-and-forget”

`executeWithoutResult` **chạy đồng bộ**, cũng như `execute` trong mô hình imperative. Caller không nhận giá trị nghiệp vụ, nhưng Spring vẫn phải xử lý transaction completion trước khi lời gọi trở về bình thường. Nếu callback ném runtime exception, lỗi vẫn đi ra caller.

Không nhầm `executeWithoutResult` với:

- `@Async`, `CompletableFuture.runAsync(...)` hoặc việc đẩy tác vụ sang thread khác.
- Một lời gọi SQL tự động commit không phụ thuộc transaction.
- Phương thức chỉ chạy lệnh ghi: callback `void` vẫn có thể SELECT hoặc gọi các thao tác khác.

## 4. So sánh nhanh hai phương thức

| Tiêu chí | `execute(...)` | `executeWithoutResult(...)` |
| --- | --- | --- |
| Input | `TransactionCallback<T>` | `Consumer<TransactionStatus>` |
| Kiểu callback | Nhận `status`, trả `T` | Nhận `status`, không trả giá trị |
| Kiểu trả về API | `T` (có thể `null`) | `void` |
| Dùng khi | Tạo ID, trả DTO, count, kết quả nghiệp vụ | Insert/update/log một tác vụ không cần trả kết quả |
| Có truy cập `TransactionStatus`? | Có | **Có** |
| Có thể gọi `setRollbackOnly()`? | Có | **Có** |
| Runtime exception thoát callback | Template rollback theo contract và chuyển lỗi | Tương tự |
| Callback kết thúc bình thường | Template cố hoàn tất transaction (commit nếu thích hợp) | Tương tự |
| Cần gọi `commit()` bằng tay? | Không | Không |
| Dùng được Java lambda? | Có | Có |
| Phù hợp khi đã có outer transaction? | Có, theo propagation của template | Có, theo propagation của template |

**Chọn API theo nhu cầu return**, không theo mức độ “an toàn”, không theo loại statement SELECT/UPDATE, cũng không theo ý muốn commit. Hai API có cùng hạ tầng transaction.

## 5. Một vòng đời transaction điển hình

Giả sử transaction manager quản lý JDBC connection và template mặc định `PROPAGATION_REQUIRED`:

```text
Caller
  |
  v
transactionTemplate.execute(callback)
  |
  +-- lấy transaction từ PlatformTransactionManager
  |       nếu chưa có -> mở transaction T
  |       nếu đã có -> thường tham gia T
  |
  +-- chạy callback(status)
  |       +-- SQL 1
  |       +-- SQL 2
  |       +-- return result / kết thúc void
  |
  +-- nếu kết thúc bình thường và không rollback-only
  |       -> manager cố commit transaction mới do scope sở hữu
  |
  +-- nếu callback throw RuntimeException/Error
  |       -> manager xử lý rollback scope
  |
  +-- nếu status.setRollbackOnly()
  |       -> manager xử lý rollback/đánh dấu rollback-only
  |
  +-- release/cleanup tài nguyên cần thiết
  v
Caller nhận result (execute) / kết thúc void
hoặc nhận exception
```

Bức tranh này cố ý phân biệt **scope transaction logic** và **transaction vật lý**. Nếu template chỉ tham gia một transaction outer đã mở, callback kết thúc **không tự commit physical transaction**; outer vẫn là nơi quyết định kết thúc. Với `PROPAGATION_NESTED`, rollback có thể quay về savepoint nếu manager hỗ trợ. Với `REQUIRES_NEW`, template mở transaction vật lý độc lập trong điều kiện phù hợp.

Một sơ đồ đơn giản “execute xong là đã commit” chỉ chính xác khi template **sở hữu transaction mới**, manager commit thành công, không có lỗi/rollback-only và không có phạm vi ngoài đang sở hữu cùng physical transaction.

### 5.1. `TransactionStatus` báo điều gì?

Các method thường hữu ích:

```java
tx.executeWithoutResult(status -> {
    boolean newTransaction = status.isNewTransaction();
    boolean rollbackRequested = status.isRollbackOnly();

    System.out.println("new=" + newTransaction
        + ", rollbackOnly=" + rollbackRequested);
});
```

Nếu code chạy với default `REQUIRED` và chưa có outer transaction, thường thấy `new=true`. Nhưng `isNewTransaction()` không phải một kiểm tra xem mọi SQL đã được commit; tại thời điểm callback, transaction vẫn đang thực thi.

Những method đáng biết:

| `TransactionStatus` API | Ý nghĩa |
| --- | --- |
| `isNewTransaction()` | Scope hiện tại có phải một transaction mới theo manager không |
| `isRollbackOnly()` | Status đang được đánh dấu rollback-only không |
| `setRollbackOnly()` | Yêu cầu outcome rollback khi manager xử lý scope |
| `hasSavepoint()` | Status có JDBC savepoint do manager tạo không |
| `isCompleted()` | Status đã hoàn tất chưa; trong callback bình thường chưa hoàn tất |
| `flush()` | Yêu cầu flush nếu manager/resource hỗ trợ; **không phải commit** |

Không dùng `status.isCompleted()` để kiểm tra commit ngay **bên trong** callback; kết thúc transaction xảy ra khi Spring trở về từ callback và xử lý completion. `flush()` cũng không làm mọi thay đổi bền vững: transaction vẫn có thể rollback.

## 6. Exception và rollback: giống nhau ở cả hai API

### 6.1. Runtime exception

```java
try {
    tx.executeWithoutResult(status -> {
        jdbc.update(
            "INSERT INTO events(id, label) VALUES (?, ?)",
            10L, "before-error");
        throw new IllegalStateException("business failure");
    });
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage());
}
```

Đây là mảnh minh họa; bảng `events` và field `jdbc` cần tồn tại. Với một transaction mới của Spring JDBC, INSERT đã chạy sẽ được rollback, rồi caller nhận `IllegalStateException`. Nếu lỗi phát sinh trước khi callback bắt đầu hoặc từ chính database/manager, transaction error cũng có thể truyền ra.

### 6.2. Chủ động rollback mà không ném exception

```java
String decision = tx.execute(status -> {
    jdbc.update(
        "INSERT INTO events(id, label) VALUES (?, ?)",
        11L, "will-rollback");

    status.setRollbackOnly();
    return "REJECTED";
});
```

Với transaction mới, callback trả `"REJECTED"` và template có thể trả chuỗi này cho caller **sau khi xử lý rollback**. Không có bản ghi ID 11 trong DB. Tình huống này hữu ích để trả một kết quả nghiệp vụ thay vì exception, nhưng application phải **hiểu rõ mã kết quả**; tuyệt đối không cho rằng có response tức là đã commit.

Biến thể void:

```java
tx.executeWithoutResult(status -> {
    jdbc.update(
        "INSERT INTO events(id, label) VALUES (?, ?)",
        12L, "also-rollback");
    status.setRollbackOnly();
});
```

Outcome DB tương tự nhưng caller không nhận một kết quả nghiệp vụ trực tiếp.

### 6.3. Bắt và nuốt lỗi bên trong callback

```java
tx.executeWithoutResult(status -> {
    try {
        riskyOperation();
    } catch (IllegalArgumentException ex) {
        // Chỉ log, không rethrow, không mark rollback-only.
    }
});
```

Đây là code minh họa với helper chưa định nghĩa. Khi callback kết thúc bình thường mà không có rollback-only/lỗi transaction khác, template có thể **commit** các SQL đã chạy trước lỗi. Một exception đã bị catch bên trong callback **không tự kích hoạt rollback policy** của template.

Khi nghiệp vụ phải hủy thao tác, hãy:

- Để exception phù hợp **thoát khỏi callback**; hoặc
- Gọi `status.setRollbackOnly()` rồi trả một kết quả thất bại rõ ràng; hoặc
- Rethrow sau khi log, không catch-and-ignore.

### 6.4. Checked exception trong callback lambda

`TransactionCallback.doInTransaction(...)` và `Consumer.accept(...)` **không khai `throws IOException` hoặc checked exception tùy ý**. Vì thế đoạn sau **không compile** nếu `performIO()` khai `throws IOException` mà không được catch:

```java
// SAI nếu performIO() khai throws IOException:
tx.execute(status -> {
    performIO();
    return "done";
});
```

Phải chuyển lỗi về hợp đồng phù hợp. Ví dụ, nếu lỗi I/O phải làm transaction rollback:

```java
String result = tx.execute(status -> {
    try {
        performIO();
        return "DONE";
    } catch (java.io.IOException ex) {
        throw new IllegalStateException("I/O failure", ex);
    }
});
```

Đây là code minh họa; `performIO()` là method chưa định nghĩa. `IllegalStateException` là runtime, template sẽ yêu cầu rollback và chuyển exception ra caller.

Nếu lỗi checked là một kết quả nghiệp vụ mà caller **không muốn ném**:

```java
String result = tx.execute(status -> {
    try {
        performCheckedBusinessStep();
        return "ACCEPTED";
    } catch (BusinessCheckedException ex) {
        status.setRollbackOnly();
        return "REJECTED";
    }
});
```

Các helper/exception là minh họa. Cách này yêu cầu caller xử lý chuỗi `REJECTED` như một kết quả **không commit**. Nếu cần giữ checked exception trong API, có thể xử lý qua wrapper runtime rồi chuyển đổi tại boundary ngoài sau khi transaction đã được xử lý, cẩn thận với nguyên nhân gốc.

**Không giả định `@Transactional(rollbackFor=...)` tự áp dụng cho lambda trong `TransactionTemplate`.** Template có quy tắc exception/callback riêng; nó không đọc annotation trên lambda để bổ sung rollback rules.

## 7. Ví dụ đầy đủ chạy được: Spring Boot, Java 17, H2

Ta xây một ứng dụng **Java 17 + Spring Boot 3.3.13 + Spring JDBC + H2 in-memory**. Ví dụ chỉ dùng **programmatic transaction**; service không có `@Transactional`. Ta sẽ quan sát:

1. `execute` vừa INSERT vừa trả tổng số bản ghi.
2. `executeWithoutResult` INSERT mà không trả kết quả.
3. `execute` gọi `setRollbackOnly()` nhưng vẫn trả một chuỗi.
4. `executeWithoutResult` ném runtime exception và rollback tự động.

Tất cả những trường hợp này sẽ được kiểm tra bằng cách đọc DB **sau khi lời gọi template đã kết thúc**.

### 7.1. Cấu trúc file

```text
transaction-template-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/main/
    ├── java/demo/template/
    │   ├── TemplateApplication.java
    │   └── TemplateLedgerService.java
    └── resources/
        ├── application.yml
        └── schema.sql
```

Gradle Wrapper là phần có thể được tạo bởi Spring Initializr hoặc `gradle wrapper` bằng bản Gradle tương thích; danh sách cấu trúc nêu nơi đặt các file cần thiết.

**`settings.gradle`**

```groovy
rootProject.name = 'transaction-template-lab'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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

Spring Boot JDBC starter cung cấp `JdbcTemplate` và infrastructure giao dịch, tự quản lý phiên bản Spring modules; H2 driver được nạp runtime. Không cần tự thêm `spring-tx` phiên bản riêng hay JPA để chạy bài lab này.

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:templatelab;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_events (
    id BIGINT PRIMARY KEY,
    label VARCHAR(40) NOT NULL
);
```

Spring Boot chạy SQL initializer cho embedded DB khi khởi động, tạo bảng rỗng trước khi `CommandLineRunner` thực thi. H2 in-memory tồn tại theo JVM; mỗi lần chạy một JVM mới sẽ bắt đầu từ dữ liệu rỗng, nên output bên dưới được xác định. `DB_CLOSE_DELAY=-1` chỉ kéo dài tuổi thọ DB tới khi JVM dừng, không biến nó thành database lưu trên đĩa.

### 7.2. Service: cả hai API trên cùng một TransactionTemplate

**`src/main/java/demo/template/TemplateLedgerService.java`**

```java
package demo.template;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TemplateLedgerService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;

    public TemplateLedgerService(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {

        this.jdbc = jdbc;
        this.tx = new TransactionTemplate(manager);
    }

    // execute: callback trả về số bản ghi trong transaction.
    public Long createAndCount(long id, String label) {
        return tx.execute(status -> {
            jdbc.update(
                "INSERT INTO tx_events (id, label) VALUES (?, ?)",
                id, label);

            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events",
                Long.class);
        });
    }

    // executeWithoutResult: không trả giá trị nghiệp vụ.
    public void writeAudit(long id, String label) {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "INSERT INTO tx_events (id, label) VALUES (?, ?)",
                id, label);
        });
    }

    // execute: vẫn có return value dù transaction bị rollback.
    public String rollbackAndReturn(long id) {
        return tx.execute(status -> {
            jdbc.update(
                "INSERT INTO tx_events (id, label) VALUES (?, ?)",
                id, "rollback-only");

            status.setRollbackOnly();
            return "computed";
        });
    }

    // executeWithoutResult: unchecked exception gây rollback.
    public void insertThenFail(long id) {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "INSERT INTO tx_events (id, label) VALUES (?, ?)",
                id, "will-fail");

            throw new IllegalStateException("simulated failure");
        });
    }
}
```

Giải thích các design decisions:

- `TemplateLedgerService` được Spring tạo, nhận `JdbcTemplate` và `PlatformTransactionManager` qua constructor injection.
- `new TransactionTemplate(manager)` được tạo **một lần** và giữ làm field `final`. Template không chứa state hội thoại per request và có thể tái sử dụng khi configuration không đổi.
- Các method service **không** cần `@Transactional` bởi vì code tự mở scope bằng template.
- `createAndCount` trả `Long` từ `COUNT(*)`. `COUNT(*)` ở H2 là kiểu số nguyên lớn; dùng `Long.class` để rõ kiểu.
- `writeAudit` dùng void callback vì caller không cần một value; `JdbcTemplate.update` vẫn trả update count nhưng callback cố ý không lấy nó.
- `rollbackAndReturn` yêu cầu rollback sau INSERT rồi trả `"computed"`. Điều này cố ý chứng minh **giá trị trả về từ `execute` không phải bằng chứng ghi dữ liệu thành công**.
- `insertThenFail` minh họa rollback khi runtime exception thoát ra khỏi lambda `Consumer<TransactionStatus>`.

### 7.3. Main và output kiểm chứng

**`src/main/java/demo/template/TemplateApplication.java`**

```java
package demo.template;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TemplateApplication {

    public static void main(String[] args) {
        SpringApplication.run(TemplateApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TemplateLedgerService service, JdbcTemplate jdbc) {
        return args -> {
            System.out.println("Before: " + rows(jdbc));

            Long count = service.createAndCount(1L, "create");
            System.out.println("execute result: " + count);
            System.out.println("After execute: " + rows(jdbc));

            service.writeAudit(2L, "audit");
            System.out.println(
                "After executeWithoutResult: " + rows(jdbc));

            String result = service.rollbackAndReturn(3L);
            System.out.println("rollbackOnly result: " + result);
            System.out.println(
                "After rollbackOnly: " + rows(jdbc));

            try {
                service.insertThenFail(4L);
            } catch (IllegalStateException ex) {
                System.out.println("Caught: " + ex.getMessage());
            }
            System.out.println("After exception: " + rows(jdbc));
        };
    }

    private static List<String> rows(JdbcTemplate jdbc) {
        return jdbc.query(
            "SELECT id, label FROM tx_events ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + ":" + rs.getString("label"));
    }
}
```

**Chạy trong thư mục project có Gradle Wrapper:**

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Bỏ qua log khởi động Spring/Gradle; các dòng `System.out.println` được in theo thứ tự:

```text
Before: []
execute result: 1
After execute: [1:create]
After executeWithoutResult: [1:create, 2:audit]
rollbackOnly result: computed
After rollbackOnly: [1:create, 2:audit]
Caught: simulated failure
After exception: [1:create, 2:audit]
```

**Vì sao từng kết quả đúng?**

1. Bảng ban đầu rỗng.
2. `createAndCount` INSERT ID 1, chạy SELECT COUNT trong cùng transaction, trả 1, manager commit thành công trước khi method `execute` hoàn tất; DB có ID 1.
3. `writeAudit` INSERT ID 2 trong callback void, manager commit; DB có 1 và 2.
4. `rollbackAndReturn` INSERT ID 3, đánh dấu rollback-only rồi trả chuỗi; template rollback trước khi trả về. Caller **nhận `computed`**, nhưng DB vẫn chỉ có ID 1 và 2.
5. `insertThenFail` INSERT ID 4 rồi ném `IllegalStateException`; template rollback, caller bắt lỗi. DB vẫn chỉ có ID 1 và 2.

Các giá trị này giả định không có một transaction ngoài đang bao bọc runner, H2/manager hoạt động bình thường, không có actor khác sửa bảng, và code đúng như trình bày. Runner **không** dùng `@Transactional` và đọc lại bảng sau mỗi lời gọi template, nên đo được outcome đã hoàn tất.

Đây là project Spring Boot **đầy đủ khi ghép các file vào đúng vị trí và có Gradle Wrapper**. Những đoạn Java riêng lẻ ở các phần trước là mảnh minh họa, không phải file có thể chạy chỉ với `javac` thiếu classpath Spring.

## 8. Viết test cho kết quả commit và rollback

Nếu muốn biến các kết luận thành kiểm thử tự động, thêm file:

**`src/test/java/demo/template/TemplateLedgerServiceTest.java`**

```java
package demo.template;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class TemplateLedgerServiceTest {

    @Autowired
    private TemplateLedgerService service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
    }

    @Test
    void executeReturnsCountAndCommits() {
        assertEquals(1L, service.createAndCount(100L, "test"));
        assertEquals(
            1L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events",
                Long.class));
    }

    @Test
    void executeWithoutResultAndRollbackOnly() {
        service.writeAudit(101L, "audit");
        assertEquals("computed", service.rollbackAndReturn(102L));
        assertEquals(
            1L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events",
                Long.class));
    }

    @Test
    void runtimeFailureRollsBack() {
        assertThrows(
            IllegalStateException.class,
            () -> service.insertThenFail(103L));
        assertEquals(
            0L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events",
                Long.class));
    }
}
```

Chạy:

```bash
./gradlew test
```

Test cố ý **không** có `@Transactional` trên class/method test. Nếu test được Spring TestContext tự bọc transaction, một transaction ngoài có thể ảnh hưởng timing của commit và visibility; test không còn trực tiếp đo một transaction mới do template sở hữu.

Khi dùng `@SpringBootTest`, `CommandLineRunner` của ứng dụng có thể chạy trong lúc context khởi tạo; `@BeforeEach` của test đã xóa bảng demo trước từng test, bảo đảm expected count. Chỉ dùng SQL reset này trong database test riêng. Nếu chạy test song song chia sẻ một H2 database, cần cô lập data/test context để tránh race.

**Kiểm thử đúng cần quan sát database sau khi phương thức đã hoàn tất**; riêng `status.isRollbackOnly()` trong callback chỉ xác nhận flag, không thay cho kiểm chứng rollback thực tế.

## 9. Khai báo TransactionTemplate và các thuộc tính transaction

### 9.1. Constructor và cấu hình mặc định

Cách cơ bản:

```java
TransactionTemplate tx = new TransactionTemplate(manager);
```

`manager` là `PlatformTransactionManager` đã được cấu hình. Template mặc định dùng các giá trị của `DefaultTransactionDefinition`:

| Thuộc tính | Mặc định thông dụng |
| --- | --- |
| `propagation` | `PROPAGATION_REQUIRED` |
| `isolation` | `ISOLATION_DEFAULT` |
| `timeout` | `TIMEOUT_DEFAULT` (thường `-1`) |
| `readOnly` | `false` |
| `name` | Không có tên riêng được thiết lập |

Có thể set một lần khi dựng bean:

```java
@Configuration
public class TxTemplateConfig {

    @Bean
    TransactionTemplate orderTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED);
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED);
        tx.setTimeout(30);
        tx.setReadOnly(false);
        tx.setName("order-processing");
        return tx;
    }
}
```

Đây là **đoạn cấu hình minh họa**, cần import `@Configuration`, `@Bean`, `TransactionTemplate`, `TransactionDefinition`, `PlatformTransactionManager` và injection/qualifier thích hợp nếu có nhiều managers/templates. Không thêm class này vào project ở phần 7 nếu không chủ đích đổi cấu hình demo; project đó đã tự tạo một template mặc định trong service.

`timeout` và `isolation` chủ yếu có ý nghĩa khi **một transaction mới được mở** và manager/database hỗ trợ. Nếu `REQUIRED` tham gia transaction đã tồn tại, không tự áp dụng lại timeout/isolation riêng của template lên physical transaction ngoài. Với strict validation của manager, một isolation mismatch rõ ràng có thể gây lỗi thay vì bị bỏ qua.

### 9.2. Thread safety và chia sẻ instance

Spring document `TransactionTemplate` là thread-safe về việc thực thi vì template **không giữ conversation state của mỗi transaction**. Tuy nhiên, template có **configuration state** (propagation, timeout, read-only, isolation, name). Nếu nhiều service dùng chính sách giống nhau, có thể dùng chung một template đã cấu hình cố định.

**Không làm thế này trong code có nhiều thread:**

```java
sharedTx.setIsolationLevel(
    TransactionDefinition.ISOLATION_SERIALIZABLE);
sharedTx.execute(status -> doWorkA());

sharedTx.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED);
sharedTx.execute(status -> doWorkB());
```

Hai thread cùng thay đổi configuration trên một shared instance có thể khiến các lần gọi chạy dưới policy ngoài dự kiến. Nên tạo **hai TransactionTemplate instance** cấu hình độc lập, ví dụ một cho `READ_COMMITTED` và một cho `SERIALIZABLE`, rồi coi cấu hình đó là bất biến sau lúc khởi tạo.

**Phân biệt:** `TransactionStatus` được cấp riêng cho từng lần thực thi callback; không giữ status làm field dùng chung và không lưu nó để xử lý sau khi template kết thúc.

### 9.3. Một số propagation quan trọng

| Template propagation | Khi caller đã có transaction vật lý | Kết quả chính |
| --- | --- | --- |
| `REQUIRED` | Tham gia transaction đã có | Caller ngoài sở hữu commit cuối cùng |
| `REQUIRES_NEW` | Tạm ngưng transaction ngoài khi manager hỗ trợ và mở transaction mới | Outcome inner độc lập hơn; có thể cần connection khác |
| `NESTED` | Tham gia physical transaction qua savepoint nếu hỗ trợ | Rollback inner có thể quay về savepoint |
| `SUPPORTS` | Tham gia nếu đã có; có thể chạy không có actual transaction nếu chưa có | Không tự bảo đảm transaction mới |
| `MANDATORY` | Yêu cầu outer phải tồn tại | Báo lỗi nếu không có transaction |
| `NOT_SUPPORTED` | Tạm ngưng outer; chạy không có actual transaction | Không phù hợp nếu cần nhóm SQL atomic như ví dụ |

`setRollbackOnly()` có ý nghĩa khác nhau khi template **sở hữu transaction mới** và khi nó **tham gia scope ngoài**. Với `REQUIRED` đang tham gia một transaction chia sẻ, Spring có thể đánh dấu **transaction chung rollback-only**; outer cố commit sau đó có thể nhận `UnexpectedRollbackException`. Với `NESTED`, manager JDBC có savepoint có thể rollback riêng phần nested. Không giả định mọi call `executeWithoutResult` đều sở hữu physical transaction riêng.

### 9.4. Transaction name

`TransactionTemplate` kế thừa cấu hình từ `DefaultTransactionDefinition`, có thể đặt tên:

```java
tx.setName("settle-invoice");
```

Tên có thể giúp log/monitoring và metadata transaction theo manager phù hợp. Không đặt lại tên trên shared template mỗi request; nếu cần tên transaction cho các nghiệp vụ khác nhau, tạo template khác hoặc quản lý definition phù hợp. Tên transaction không phải một SQL transaction identifier toàn cầu.

## 10. execute và executeWithoutResult khi tham gia transaction ngoài

Đây là nơi dễ nhầm nhất nếu chỉ học từ một ví dụ không có outer.

Giả sử một facade đã mở transaction T bằng `@Transactional` và gọi service sử dụng `TransactionTemplate` mặc định `REQUIRED`:

```java
@Transactional
public void outerBusinessOperation() {
    // Ghi A trong transaction T.

    helperService.usingTemplate();

    // Ghi C trong transaction T.
}
```

Nếu `helperService.usingTemplate()` gọi:

```java
tx.executeWithoutResult(status -> {
    // Ghi B trong cùng transaction T nếu manager/resource phù hợp.
});
```

thì **callback kết thúc bình thường không tự commit T**. T vẫn đang do outer quản lý; khi outer rollback, A/B/C đều có thể bị hủy.

Trường hợp inner:

```java
tx.executeWithoutResult(status -> {
    status.setRollbackOnly();
});
```

có thể làm T bị đánh dấu rollback-only. Nếu outer catch/tiếp tục rồi cố commit, Spring có thể phát sinh `UnexpectedRollbackException`. Nên tránh sử dụng return value hoặc dấu hiệu “callback đã chạy xong” để tuyên bố transaction đã commit khi đang ở trong outer scope.

**Cẩn thận với annotation và template trùng nhau:** Một method vừa có `@Transactional` vừa dùng template `REQUIRED` thường tạo **hai scope logic tham gia cùng physical transaction**, không tạo hai commits độc lập. Hãy xác định boundary thực sự thay vì lồng chỉ vì thấy code cần “chắc ăn”.

## 11. Ví dụ luồng nghiệp vụ: thu hẹp thời gian giữ transaction

Một lợi ích rõ của programmatic style là giữ các hoạt động không thuộc DB transaction ở ngoài:

```java
public Receipt process(Request request) {
    // 1. Không giữ DB transaction trong các bước dài.
    ExternalQuote quote = quoteClient.fetchQuote(request);
    ValidatedOrder valid = validator.validate(request, quote);

    // 2. Chỉ bao phần SQL cần atomicity.
    Receipt receipt = tx.execute(status -> {
        long orderId = orders.insert(valid);
        inventory.reserve(valid);
        return new Receipt(orderId, valid.total());
    });

    // 3. Chỉ làm bước sau-commit khi execute đã trở về bình thường
    //    và template thật sự sở hữu boundary commit.
    notifier.scheduleReceipt(receipt);
    return receipt;
}
```

Đoạn này là **pseudocode Java minh họa**, với `Request`, `Receipt`, `ExternalQuote`, repositories và dịch vụ chưa định nghĩa. Thứ tự gợi ý: chuẩn bị/validate ở ngoài, dùng `execute` cho vùng SQL cần trả một result, sau đó phát thông báo qua cơ chế phù hợp.

Nhưng có các giới hạn:

- Nếu template `REQUIRED` **tham gia transaction outer** thay vì tự mở, code sau `execute` **có thể chạy trước outer commit**. Không gọi nó là after-commit thật nếu không có bằng chứng boundary.
- Nếu `status.setRollbackOnly()` nhưng callback vẫn trả `Receipt`, code sau có thể xử lý một receipt chưa được lưu.
- Nếu notification HTTP/email thất bại sau DB commit, transaction local không tự rollback kết quả DB; cần outbox/compensation/idempotency theo nghiệp vụ.
- Nếu cần chắc chắn phát event sau commit, dùng transaction synchronization/transactional outbox có thiết kế rõ; không dựa vào vị trí của một dòng Java một cách máy móc.

## 12. Phân biệt TransactionTemplate với @Transactional và tự gọi manager

| Tiêu chí | `TransactionTemplate` | `@Transactional` | `PlatformTransactionManager` trực tiếp |
| --- | --- | --- | --- |
| Cách định nghĩa boundary | Code block callback | Annotation trên method/type | Lấy status và gọi commit/rollback thủ công |
| Tự quản boilerplate transaction | **Có** | **Có** | Phần lớn phải tự viết |
| Cần đi qua Spring AOP proxy cho chính boundary? | **Không** | Thường **có** trong proxy mode | Không |
| Có trả kết quả từ boundary? | `execute` trả `T`; void API khác | Method Java trả giá trị của nó | Do caller tự tổ chức |
| Cấu hình policy | Thuộc tính trên template | Thuộc tính annotation | `TransactionDefinition` do code tạo |
| Độ kết dính vào Spring API ở business code | Cao hơn | Thấp hơn | Cao nhất |
| Phù hợp với | Một số block transaction đặc biệt, scope động | Nhiều service methods có boundary ổn định | Framework/infra hoặc nhu cầu kiểm soát rất thấp tầng |

Phần lớn dự án nên ưu tiên declarative `@Transactional` để business code dễ đọc. `TransactionTemplate` rất hữu ích khi chỉ **một phần method** cần transaction hoặc khi muốn cấu hình một số chính sách cụ thể. Việc tự gọi manager:

```java
TransactionStatus status = manager.getTransaction(definition);
try {
    doWork();
    manager.commit(status);
} catch (RuntimeException ex) {
    manager.rollback(status);
    throw ex;
}
```

là **mảnh minh họa** và có thể cần xử lý thêm failure trong `commit`, `rollback`, `Error`, transaction owner, lifecycle status. Không nên tự viết boilerplate này khi `TransactionTemplate` đã giải quyết công việc đó.

## 13. Các lỗi và ngộ nhận thường gặp

### 13.1. Trả `null` bằng `execute` rồi nghĩ transaction không commit

`execute` cho phép callback trả `null`. Điều đó **không tự rollback**. Nếu method chỉ thực hiện SQL và không cần kết quả, `executeWithoutResult` diễn đạt ý định tốt hơn:

```java
// Hợp lệ nhưng rườm rà:
tx.execute(status -> {
    jdbc.update("DELETE FROM tx_events WHERE id=?", 7L);
    return null;
});

// Rõ mục đích hơn:
tx.executeWithoutResult(status ->
    jdbc.update("DELETE FROM tx_events WHERE id=?", 7L));
```

Hai đoạn có thể cho cùng kết quả DB dưới cùng transaction definition, nhưng chỉ API thứ hai trả `void` đúng ý.

### 13.2. Viết lambda sai chữ ký

Sai:

```java
tx.executeWithoutResult(() -> {
    performOperation();
});
```

Vì `executeWithoutResult` nhận `Consumer<TransactionStatus>`, lambda phải có **một** tham số:

```java
tx.executeWithoutResult(status -> {
    performOperation();
});
```

`performOperation()` là helper minh họa. Có thể không sử dụng `status` bên trong body, nhưng tham số vẫn cần trong lambda.

Sai khác:

```java
tx.executeWithoutResult(status -> {
    performOperation();
    return 42; // Không compile: callback void.
});
```

Nếu cần 42, dùng `tx.execute(status -> { performOperation(); return 42; })`.

### 13.3. Gọi `status.setRollbackOnly()` rồi vẫn báo “thành công”

Một callback có thể trả giá trị/return void mặc dù đã yêu cầu rollback. Hãy chọn kết quả `FAILED/REJECTED` rõ ràng, hoặc ném exception phù hợp; không dùng successful HTTP response/định danh vừa tính như bằng chứng DB đã commit.

### 13.4. Bắt exception trong callback và nuốt

Nếu callback trả về bình thường, template không biết rằng application đã coi một lỗi là nghiêm trọng. Để exception thoát ra hoặc gọi `setRollbackOnly()`. Không catch `Exception` chung rồi cố commit một transaction DB đã mất khả năng hoạt động.

### 13.5. Nghĩ mọi checked exception có thể throw thẳng từ lambda

`TransactionCallback`/`Consumer` không khai checked `throws` tùy ý. Cần catch và xử lý, wrap thành runtime, hoặc thiết kế result contract. Không nhầm với khả năng `@Transactional(rollbackFor=CheckedException.class)` ở declarative approach.

### 13.6. Tạo template nhưng sai transaction manager

Nếu `JdbcTemplate` dùng DataSource A còn template trỏ transaction manager của DataSource B, hai phần **không tự nhiên tạo thành cùng transaction**. Với nhiều managers, dùng đúng bean/qualifier và test rollback sau SQL thật.

### 13.7. Truy cập tài nguyên ngoài transaction

Một DAO tạo connection riêng qua `DriverManager.getConnection(...)` có thể không dùng connection do Spring bind trên thread. `TransactionTemplate` không biến những SQL đó thành một transaction chung chỉ bằng việc bao callback. Dùng `JdbcTemplate` cùng DataSource hoặc cơ chế tham gia transaction đã kiểm chứng.

### 13.8. Trả collection/stream lười từ `execute`

```java
Stream<Order> stream = tx.execute(status -> {
    return repository.streamAllOrders();
});
```

Đoạn này là minh họa; `Order`/repository chưa định nghĩa. Nếu stream phải được tiêu thụ trong transaction mà caller chỉ duyệt **sau khi execute kết thúc**, persistence context/connection có thể đã đóng hoặc transaction không còn. Dùng giá trị đã materialize đầy đủ trong callback, hoặc thiết kế consumption/transaction boundary thích hợp.

### 13.9. Nghĩ `executeWithoutResult` chạy nền

Cả hai API chạy **đồng bộ**; không thay thế queue, thread hoặc scheduler. Nếu callback tự tạo thread mới, transaction JDBC thread-bound **không tự chuyển** sang thread đó. Nên để mỗi async task sở hữu transaction riêng một cách chủ đích.

### 13.10. Thay đổi cấu hình template sau khi nhiều request đã sử dụng

Template thread-safe cho các lần execute **với cấu hình ổn định**; đừng đổi propagation/isolation/timeout trên singleton cùng lúc các thread khác đang dùng. Dùng nhiều template độc lập khi cần policies khác.

### 13.11. Tự động giả định mọi lỗi SQL đều có thể retry

Deadlock, constraint violation, serialization failure, connection error có cách xử lý khác nhau. Một số lỗi yêu cầu hủy transaction và retry **toàn scope**; một số là lỗi dữ liệu không nên retry. Đặc biệt, external side effects trong callback có thể bị lặp khi retry.

## 14. Checklist thiết kế một callback transaction an toàn

Trước khi đưa `TransactionTemplate` vào production:

1. Xác định **transaction manager và DataSource/EntityManagerFactory** đang được sử dụng; không chọn theo tên mơ hồ khi có nhiều beans.
2. Chọn `execute` nếu thực sự cần trả giá trị; dùng `executeWithoutResult` khi không có result.
3. Đặt đúng SQL cần atomicity **bên trong cùng callback**. Không để một câu SQL liên quan vô tình chạy ngoài boundary.
4. Chọn propagation có chủ đích. Nếu `REQUIRED` có thể tham gia outer, không giả định callback vừa kết thúc là physical commit xong.
5. Khai isolation/read-only/timeout khi có nhu cầu được kiểm chứng; đừng tùy tiện nâng isolation hoặc giữ transaction quá lâu.
6. Với exception, xác định lỗi nào phải rollback; đừng nuốt lỗi rồi trả success.
7. Với `setRollbackOnly()`, phản ánh outcome thất bại trong return object/status; không lấy result callback làm commit receipt.
8. Tránh làm network call dài, sleep, chờ user input hoặc emit external side effects trực tiếp trong callback.
9. Không thay đổi config của shared template sau khởi tạo.
10. Test cả đường success, unchecked exception, explicit rollback-only, thiếu dữ liệu và DB constraint failure.
11. Test bên ngoài transaction test tự động nếu mục tiêu là xác nhận **commit vật lý**.
12. Với reactive code, dùng `TransactionalOperator`, không dùng template imperative cho publisher rồi nghĩ scope sẽ tồn tại tới lúc subscriber tiêu thụ.

## 15. Câu hỏi tự đánh giá

**1. Khi nào nên dùng `execute` thay vì `executeWithoutResult`?**

Khi callback cần trả giá trị nghiệp vụ cho caller. Ví dụ mã đơn hàng, kết quả SELECT, DTO hoặc count. Không nên chọn dựa trên việc SQL là SELECT hay UPDATE.

**2. `executeWithoutResult(status -> ...)` có lấy được `TransactionStatus` không?**

Có. Lambda nhận `TransactionStatus` và có thể gọi `status.setRollbackOnly()`. Tên method chỉ nói **không trả một result object** cho caller.

**3. `execute(status -> { status.setRollbackOnly(); return 42; })` có thể trả 42 không?**

Có, nếu rollback hoàn tất bình thường trong một transaction mới; callback return value có thể được trả dù DB rollback. Do đó 42 không phải bằng chứng commit.

**4. `executeWithoutResult` có tự khởi chạy task trên thread khác không?**

Không. Đây là API đồng bộ, quản lý scope transaction trên đường thực thi hiện tại. Nếu chủ động tạo thread khác, transaction không tự lan sang thread đó.

**5. Vì sao hai câu SQL thuộc cùng callback có thể rollback cùng nhau?**

Vì transaction manager quản lý cùng transaction/tài nguyên, và template bọc toàn bộ callback trong một transaction scope theo propagation. Nếu DAO dùng connection khác ngoài Spring, guarantee này không còn đúng tự động.

**6. Khi một template `REQUIRED` được gọi trong outer `@Transactional`, callback return có commit DB ngay không?**

Không nhất thiết. Template thường tham gia transaction ngoài và owner outer vẫn quyết định commit vật lý.

**7. `TransactionCallbackWithoutResult` khác `executeWithoutResult` như thế nào?**

`TransactionCallbackWithoutResult` là class callback theo kiểu anonymous class cũ, dùng với `execute(new TransactionCallbackWithoutResult() {...})`. `executeWithoutResult` là convenience method chấp nhận `Consumer<TransactionStatus>`, dễ dùng lambda và trả `void`. Trong Spring 7, class callback cũ đã được đánh dấu deprecated; lựa chọn lambda mới thường rõ ràng hơn.

**8. Nếu callback bắt IOException rồi return bình thường thì có rollback không?**

Không tự động chỉ vì có IOException đã bị catch. Cần mark rollback-only hoặc chuyển lỗi thành runtime exception thoát khỏi callback khi nghiệp vụ phải rollback.

**9. Có nên dựng một `TransactionTemplate` mới mỗi lần request rồi thay cấu hình liên tục không?**

Thông thường không cần. Có thể tạo một lần, giữ cấu hình ổn định, chia sẻ theo policy; tạo instance khác nếu cần isolation/propagation khác.

## 16. Ghi nhớ

`TransactionTemplate` cung cấp ranh giới transaction programmatic theo cơ chế callback:

- **`execute(TransactionCallback<T>)`**: chạy code và trả `T` (có thể `null`).
- **`executeWithoutResult(Consumer<TransactionStatus>)`**: chạy code, trả `void`, vẫn được thao tác `TransactionStatus`.
- Với transaction mới do template sở hữu, callback kết thúc bình thường và không rollback-only thì manager cố commit; ném unchecked exception hoặc gọi `status.setRollbackOnly()` thì rollback.
- **Return value không phải chứng nhận commit** và completion của một scope tham gia outer không phải physical commit.
- Template thread-safe khi dùng cấu hình ổn định, nhưng không quản lý một connection/transaction cho mọi thread bất kể context.
- Trong đa số service methods, `@Transactional` vẫn là cách diễn đạt tốt; dùng template khi cần một khối code cụ thể hoặc policy programmatic có chủ đích.

Để kiểm tra nhanh điều hiểu đúng, hãy chạy project H2 ở phần 7: sau `execute` và `executeWithoutResult` thành công, DB có ID 1 và 2; sau callback trả chuỗi nhưng `setRollbackOnly`, và sau callback ném runtime exception, DB **vẫn chỉ có ID 1 và 2**.

## Tài liệu tham khảo chính thức

- Spring Framework — *Programmatic Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — *Choosing Between Programmatic and Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-decl-vs-prog.html
- Spring Framework 6.2 — *TransactionTemplate API*: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework 6.0 — *TransactionOperations API* (gồm `executeWithoutResult`, có từ 5.2): https://docs.spring.io/spring-framework/docs/6.0.3/javadoc-api/org/springframework/transaction/support/TransactionOperations.html
- Spring Framework — *TransactionStatus API*: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — *TransactionDefinition API*: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — *Transaction Propagation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Boot 3.3 — *SQL Databases*: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
