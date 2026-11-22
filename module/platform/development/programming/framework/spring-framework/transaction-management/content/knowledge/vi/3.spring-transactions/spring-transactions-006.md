# TransactionException và lỗi hạ tầng giao dịch

## 1. Mục tiêu và vị trí trong mô hình Spring

Khi một phương thức gắn `@Transactional` thất bại, lỗi không nhất thiết đến từ câu SQL hoặc logic nghiệp vụ. Spring còn có thể không mở được transaction, phát hiện một transaction đã bị đánh dấu rollback-only, không commit/rollback được, hoặc từ chối cách sử dụng transaction API. Nhóm lỗi này được biểu diễn qua `org.springframework.transaction.TransactionException` và các lớp con.

Bài này tập trung vào **mô hình transaction của Spring**, đặc biệt là ý nghĩa của exception tại ranh giới giữa application, `PlatformTransactionManager` và hệ thống lưu trữ. Sau bài học, bạn cần:

1. Phân biệt lỗi nghiệp vụ, lỗi truy cập dữ liệu và lỗi từ hạ tầng điều phối transaction.
2. Nhận diện các loại `TransactionException` quan trọng, thời điểm chúng xuất hiện và mức độ chắc chắn về trạng thái dữ liệu.
3. Giải thích đúng `UnexpectedRollbackException` khi một transaction đã bị đánh dấu rollback-only.
4. Biết điều tra nguyên nhân gốc, quyết định xử lý/retry và kiểm chứng rollback/commit bằng dữ liệu.
5. Viết được integration test cho đường đi transaction thực và unit test mô phỏng lỗi tại transaction manager.

Phạm vi: **Spring Framework 6.x, mô hình transaction imperative với JDBC**; ví dụ dùng Java 17+, Spring Boot 3.3.x, H2, Spring Test/JUnit 5. Với JPA, JTA hoặc reactive transaction, một số lỗi có thể xuất hiện ở thời điểm khác và được dịch sang loại exception khác. Không suy ra từ tên exception rằng mọi database hay mọi transaction manager đều xử lý giống nhau.

## 2. Ba nguồn lỗi cần tách bạch

Đặt mô hình sau trước khi đọc stack trace:

```text
HTTP / job / caller
      |
      v
@Transactional proxy / TransactionInterceptor
      |              |
      |              +-- PlatformTransactionManager
      |                       | begin / join
      |                       | commit / rollback
      v                       v
Service -> Repository/JdbcTemplate -> Connection / Database
```

| Nguồn lỗi | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Nghiệp vụ / Java** | `IllegalArgumentException`, `BusinessRuleException` | Code quyết định thao tác không hợp lệ; rule rollback phụ thuộc exception và cấu hình |
| **Truy cập dữ liệu** | `DataIntegrityViolationException`, `CannotGetJdbcConnectionException` | Spring đã dịch lỗi truy cập DB qua họ `org.springframework.dao.DataAccessException` |
| **Hạ tầng transaction** | `CannotCreateTransactionException`, `UnexpectedRollbackException`, `TransactionSystemException` | Spring/transaction manager gặp lỗi khi tạo, tham gia, kết thúc hoặc sử dụng transaction |

**`DataAccessException` không phải lớp con của `TransactionException`.** Cả hai là họ runtime exception riêng. Lỗi SQL do `JdbcTemplate` ném thường là `DataAccessException`; lỗi commit/rollback từ `PlatformTransactionManager` thường thuộc họ `TransactionException`, **nhưng không phải luôn luôn**: `JdbcTransactionManager` có thể chuyển lỗi ở bước commit/rollback thành `DataAccessException`, giống cơ chế dịch lỗi của `JdbcTemplate`.

`@Transactional` mặc định rollback khi `RuntimeException` hoặc `Error` thoát ra khỏi phương thức qua transaction interceptor; checked exception không mặc định gây rollback (trừ khi cấu hình khác). Vì `TransactionException` và `DataAccessException` đều là runtime exception, chúng thường kích hoạt rule rollback mặc định **nếu phát sinh trong phạm vi mà interceptor còn đang xử lý**. Tuy nhiên lỗi phát sinh ngay trong `commit()` hoặc `rollback()` không thể đơn giản coi là "một exception nghiệp vụ khiến Spring rollback": transaction manager có thể đã kết thúc hoặc đang ở trạng thái không xác định.

## 3. Một transaction có thể lỗi ở những giai đoạn nào?

```text
(1) Nhận lời gọi service qua proxy
       |
(2) TransactionManager.getTransaction(...)
       |  không mở được -> CannotCreateTransactionException
       v
(3) Chạy service / SQL
       |  lỗi DB -> DataAccessException, hoặc lỗi nghiệp vụ
       v
(4) Chọn commit hay rollback theo rule / rollback-only
       |
       +-- rollback-only nhưng caller định commit
       |         -> UnexpectedRollbackException
       |
       +-- commit/rollback lỗi tài nguyên
       |         -> TransactionSystemException hoặc DataAccessException
       v
(5) Cleanup / trả kết quả cho caller
```

| Thời điểm | Câu hỏi cần điều tra | Có thể kết luận gì về dữ liệu? |
| --- | --- | --- |
| **Chưa bắt đầu** | Có kết nối không? Cấu hình đúng manager? Có thiếu transaction capability? | Nếu transaction chưa được tạo, không có commit từ transaction đó; các tác dụng đã xảy ra ở nơi khác vẫn có thể tồn tại |
| **Trong method** | Lệnh nào lỗi? Exception có thoát qua proxy không? Transaction đã rollback-only? | Chưa kết luận commit; phải để boundary kết thúc rồi đọc lại dữ liệu |
| **Lúc commit** | Database có xác nhận commit hay chỉ mất kết nối/timeout? | **Có thể chưa rõ outcome**; không mặc định coi là rollback |
| **Lúc rollback** | Rollback thực hiện thành công hay ném lỗi mới? | Không thể khẳng định mọi thay đổi đã hủy nếu rollback thất bại; phải kiểm chứng |
| **Sau khi transaction kết thúc** | Có callback đồng bộ hóa, publish event hoặc tác vụ ngoài DB bị lỗi? | Có trường hợp dữ liệu đã commit dù caller nhận exception từ tác vụ sau commit |

Điểm dễ mắc lỗi nhất là **đồng nhất “caller nhận exception” với “database đã rollback”**. Một exception có thể phát sinh **sau khi SQL đã được gửi hoặc sau khi database chấp nhận commit**. Nếu mạng đứt ngay thời điểm commit, application có thể không biết chắc database đã commit hay chưa. Với những thao tác có tác dụng nghiệp vụ, việc retry mù có thể tạo bản ghi trùng hoặc thực hiện lại giao dịch đã thành công.

## 4. Họ `TransactionException`: ý nghĩa và cách xử lý

`TransactionException` là lớp trừu tượng trong `org.springframework.transaction`, kế thừa `NestedRuntimeException` (một `RuntimeException`). Không khởi tạo trực tiếp lớp này; Spring và các transaction manager ném các lớp con cụ thể.

### 4.1. Các loại thường gặp

| Loại exception | Tình huống tiêu biểu | Cách tiếp cận |
| --- | --- | --- |
| `CannotCreateTransactionException` | Không bắt đầu được transaction vì không lấy được tài nguyên hoặc API transaction nền từ chối | Kiểm tra kết nối, DB availability, pool, credentials, manager và nguyên nhân gốc |
| `UnexpectedRollbackException` | Outer scope định commit, nhưng physical transaction đã rollback hoặc bị đánh dấu rollback-only | Truy ra scope gây rollback-only; kiểm tra propagation và điểm bắt lỗi |
| `TransactionSystemException` | Lỗi hệ thống ở commit/rollback hoặc cơ chế transaction nền | Đọc `cause`, `getApplicationException()` và `getOriginalException()`; xác minh trạng thái dữ liệu |
| `TransactionTimedOutException` | Deadline transaction bị vượt quá và hạ tầng phát hiện | Phân tích query/lock, timeout, connection pool và thời điểm phát hiện |
| `TransactionUsageException` và các lớp con | Sử dụng API/trạng thái transaction không hợp lệ | Sửa code hoặc cấu hình; retry không giải quyết lỗi thiết kế |
| `HeuristicCompletionException` | Coordinator của distributed transaction báo kết quả heuristic, có thể commit/rollback không đồng nhất | Đối soát từng tài nguyên; cần quy trình khôi phục, không giả định atomic rollback |

Một số lớp con cụ thể của `TransactionUsageException`:

- `IllegalTransactionStateException`: thao tác hoặc trạng thái transaction không hợp lệ; ví dụ dùng propagation không tương thích với transaction hiện có.
- `InvalidIsolationLevelException`: yêu cầu isolation level không được transaction manager/tài nguyên hỗ trợ.
- `NoTransactionException`: API kỳ vọng một transaction status nhưng không có status thích hợp, ví dụ gọi `TransactionAspectSupport.currentTransactionStatus()` ngoài ngữ cảnh interceptor.
- `InvalidTimeoutException`: thời hạn transaction khai báo không hợp lệ.

Các tình huống tạo transaction/suspend transaction không được hỗ trợ có thể phát sinh `NestedTransactionNotSupportedException` hoặc `TransactionSuspensionNotSupportedException`. Chẳng hạn, `PROPAGATION_NESTED` cần hỗ trợ savepoint tương ứng; không thể cho rằng mọi JPA/JTA transaction manager đều hỗ trợ nó.

### 4.2. `CannotCreateTransactionException`: lỗi trước khi phần thân nghiệp vụ chạy

Giả sử transaction manager cần lấy một JDBC connection và bắt đầu transaction:

```text
Service proxy
  -> transactionManager.getTransaction(...)
      -> DataSource.getConnection()
          -> pool hết connection / DB không truy cập được
      -> BEGIN thất bại
  -> CannotCreateTransactionException
Service body: chưa chạy
```

Trường hợp này khác với lỗi SQL **sau** khi transaction đã bắt đầu. Chỉ thấy `CannotCreateTransactionException` chưa đủ để quy kết duy nhất rằng DB sập: pool hết connection, cấu hình sai, tài nguyên nền hoặc driver cũng có thể gây ra. Hãy xem **cause chain** và log chính xác ở thời điểm `getTransaction`.

**Hướng xử lý:** kiểm tra pool metrics (active, idle, pending), giới hạn kết nối database, DNS/network, credentials, transaction manager bean đang dùng và áp lực tải. Chỉ cân nhắc retry có giới hạn, backoff và idempotency khi xác minh đó là lỗi tạm thời; sai cấu hình hoặc thiếu quyền không được chữa bằng lặp vô hạn.

### 4.3. `UnexpectedRollbackException`: rollback đã được quyết định nhưng caller nghĩ sẽ commit

Đây là trường hợp đặc biệt trong `PROPAGATION_REQUIRED`:

```text
Outer @Transactional (REQUIRED)
    INSERT outer
    |
    +--> Inner @Transactional (REQUIRED), gọi QUA PROXY
             INSERT inner
             throw IllegalStateException
             -> interceptor của inner đánh dấu shared transaction rollback-only
    |
    catch IllegalStateException trong outer
    return bình thường
    |
Outer interceptor định commit
    -> thấy rollback-only -> rollback
    -> ném UnexpectedRollbackException cho caller
```

Điểm mấu chốt: hai transaction scope *logic* có thể tham gia **cùng physical transaction**. Việc outer bắt exception chỉ xử lý exception Java; nó **không xóa rollback-only marker** của physical transaction. Spring ném `UnexpectedRollbackException` để caller không hiểu sai rollback thành commit.

Không phải cứ `catch` một `RuntimeException` là chắc chắn gặp `UnexpectedRollbackException`. Nếu lỗi được ném và bắt **hoàn toàn bên trong cùng một method** trước khi interceptor thấy lỗi và không có thành phần nào đánh dấu rollback-only, outer scope có thể commit. Cũng không nên tạo lỗi bằng `this.innerMethod()` rồi kỳ vọng metadata `@Transactional` của inner được áp dụng: lời gọi nội bộ thường bỏ qua proxy Spring.

**Hướng xử lý:** xác định method nào đánh dấu rollback-only, ai gọi ai qua proxy, propagation, hành vi repository/ORM, và phạm vi nghiệp vụ nào thực sự cần nguyên tử. Nếu một thao tác phải độc lập với outer transaction, thiết kế ranh giới và `REQUIRES_NEW` một cách có chủ đích (kể cả chi phí connection); không đổi propagation chỉ để “làm biến mất exception”.

### 4.4. `TransactionSystemException`: lỗi hạ tầng khi kết thúc

`TransactionSystemException` thường báo lỗi hệ thống transaction lúc `commit` hoặc `rollback`. Đặc biệt, khi application ném một exception **và bước rollback lại thất bại**, exception hạ tầng có thể che exception gốc. Spring cung cấp:

- `getApplicationException()`: application exception được lưu lại khi có.
- `getOriginalException()`: ưu tiên application exception ban đầu; nếu không có thì trả cause của `TransactionSystemException`.
- `getCause()`: cause trực tiếp của lỗi transaction.

```java
// Đoạn minh họa dùng tại boundary xử lý lỗi, không phải chương trình độc lập.
catch (TransactionSystemException ex) {
    Throwable original = ex.getOriginalException();
    log.error("Transaction system failure; original={}",
            original == null ? "(unknown)" : original.toString(), ex);
    throw ex;
}
```

Đoạn trên giả định biến `log` đã được khai báo và ứng dụng đang ở một tầng có quyền xử lý/log lỗi. Khi log, tránh ghi mật khẩu, chuỗi kết nối chứa secret hoặc dữ liệu cá nhân. Nếu lỗi ở commit, đừng khẳng định chắc chắn DB đã rollback mà chưa kiểm chứng kết quả.

### 4.5. `TransactionTimedOutException`: timeout không phải đồng hồ “hủy mọi thứ”

Transaction timeout do Spring/driver/database phối hợp áp dụng; cách phát hiện phụ thuộc manager, database, câu lệnh và lúc hạ tầng kiểm tra deadline. `@Transactional(timeout = 3)` **không phải bảo đảm** mọi tác vụ CPU, HTTP hay I/O ngoài database sẽ bị hủy chính xác sau 3 giây. Timeout có thể khiến transaction bị rollback, hoặc xuất hiện khi query/commit được kiểm tra; phải quan sát context và trạng thái sau boundary.

Khi gặp timeout, xem lock wait, slow query, pool starvation, timeout riêng của JDBC statement, database và request; chú ý timeout outer/inner có thể bị chi phối bởi propagation. Không tăng timeout vô hạn để che một query hoặc lock deadlock.

### 4.6. `HeuristicCompletionException` và mức độ chắc chắn

Trong transaction phân tán, coordinator có thể báo các tài nguyên đã hoàn tất không đồng nhất (heuristic outcome). Đây là cảnh báo về **tính nhất quán giữa tài nguyên**, không phải một exception nghiệp vụ có thể xử lý bằng `catch` rồi tiếp tục như chưa có gì xảy ra. Cần dữ liệu đối soát, xử lý bù và quyết định vận hành rõ ràng. Với transaction JDBC một datasource, thường không gặp loại này.

## 5. Khi gặp exception, rollback rule thực sự chạy lúc nào?

Thử xét một service chỉ dùng transaction manager/JDBC bình thường:

| Diễn biến | Rule và kết quả điển hình |
| --- | --- |
| Method ném `IllegalArgumentException` ra qua transactional interceptor | Mặc định yêu cầu rollback |
| Method ném checked `IOException` ra ngoài, không có `rollbackFor` | Mặc định **không** yêu cầu rollback chỉ vì exception đó |
| Method ném checked `IOException`, khai báo `@Transactional(rollbackFor = IOException.class)` | Spring yêu cầu rollback khi lỗi thoát qua interceptor |
| Method bắt hết lỗi trước khi return | Interceptor có thể thấy return bình thường; nếu transaction đã rollback-only thì vẫn rollback |
| Inner `REQUIRED` thất bại, outer bắt exception | Shared physical transaction có thể đã rollback-only; outer commit phát sinh `UnexpectedRollbackException` |
| Transaction manager `commit()` thất bại | Kết quả dữ liệu phụ thuộc bước đã hoàn tất; **không** giả định rollback thành công |
| JDBC query ném `DataIntegrityViolationException` | Thuộc `DataAccessException`, không phải `TransactionException`; thường gây rollback nếu thoát qua interceptor |

Thông thường khi muốn giữ exception gốc và đảm bảo rule rollback, nên để lỗi không thể phục hồi thoát qua service boundary. Nếu nghiệp vụ cho phép phục hồi, thiết kế rõ phạm vi transaction; đừng dùng `catch (Exception ignored)` ở mọi lớp. Khi phải chủ động yêu cầu rollback trong một transactional method, có thể dùng `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`, nhưng phương pháp này phụ thuộc ngữ cảnh Spring transaction interceptor và không nên là mặc định cho luồng nghiệp vụ.

**Không gọi thủ công `rollback(status)` sau khi `PlatformTransactionManager.commit(status)` đã ném exception.** Theo contract của `PlatformTransactionManager`, status đã được hoàn tất/dọn dẹp khi `commit` trả về, kể cả lúc ném lỗi; `rollback` tiếp sẽ dẫn tới lỗi trạng thái và không chứng minh được điều gì về commit đã diễn ra.

## 6. Thực hành chạy được: lỗi SQL so với `UnexpectedRollbackException`

Ta dựng ví dụ Spring Boot dùng H2 để thấy rõ hai loại exception khác nhau: lỗi SQL trong service và lỗi rollback-only tại ranh giới transaction. Ví dụ dùng **hai Spring bean khác nhau** để lời gọi inner thực sự qua proxy.

### 6.1. Cấu trúc dự án và Gradle

```text
transaction-errors/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txerrors/
    │   │   ├── TxErrorsApplication.java
    │   │   ├── InnerStep.java
    │   │   └── WorkflowService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txerrors/
        ├── TransactionFailureIntegrationTest.java
        └── TransactionManagerBoundaryTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'transaction-errors'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

Dùng Java 17 trở lên và Gradle phù hợp với plugin Spring Boot 3.3.5. Nếu dự án được tạo qua Spring Initializr, Gradle Wrapper thường đã có sẵn; nếu tạo file thủ công, cần tạo wrapper hoặc dùng Gradle đã cài. Mã là ứng dụng Java/Spring đầy đủ với JUnit; không dùng `javac` trần khi chưa cấu hình classpath của dependency Spring.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txerrors;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE
);
```

Cột `code` có ràng buộc `UNIQUE` để tạo lỗi SQL một cách xác định. H2 là test database; production nên xác nhận hành vi với hệ database thật.

### 6.2. Ứng dụng khởi động

`src/main/java/com/example/txerrors/TxErrorsApplication.java`:

```java
package com.example.txerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxErrorsApplication.class, args);
    }
}
```

`src/main/java/com/example/txerrors/InnerStep.java`:

```java
package com.example.txerrors;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerStep {
    private final JdbcTemplate jdbc;

    public InnerStep(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional // propagation = REQUIRED theo mặc định
    public void writeThenFail() {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "inner");
        throw new IllegalStateException("Simulated failure inside REQUIRED");
    }
}
```

`src/main/java/com/example/txerrors/WorkflowService.java`:

```java
package com.example.txerrors;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WorkflowService {
    private final JdbcTemplate jdbc;
    private final InnerStep inner;

    public WorkflowService(JdbcTemplate jdbc, InnerStep inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void success() {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "success");
    }

    @Transactional
    public void outerCatchesInnerFailure() {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "outer");

        try {
            inner.writeThenFail(); // qua bean khác: interceptor của inner chạy
        } catch (IllegalStateException expected) {
            // Cố ý bắt để minh họa: lỗi Java biến mất,
            // nhưng physical transaction đã bị đánh dấu rollback-only.
        }
        // Kết thúc bình thường ở mức Java; proxy outer vẫn phải xử lý commit.
    }

    @Transactional
    public void duplicateKeyFailure() {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "duplicate");
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "duplicate");
    }
}
```

Nếu inner ném `IllegalStateException`, Spring interceptor của inner gặp runtime exception, tham gia cùng physical transaction `REQUIRED` và đánh dấu rollback-only. Outer bắt lỗi Java rồi return, nhưng interceptor outer vẫn phát hiện rollback-only khi định commit. Trong phương thức thứ ba, lỗi database xảy ra ở lệnh `INSERT` thứ hai, được `JdbcTemplate` dịch sang họ `DataAccessException`.

### 6.3. Integration test quan sát dữ liệu sau transaction boundary

`src/test/java/com/example/txerrors/TransactionFailureIntegrationTest.java`:

```java
package com.example.txerrors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TransactionFailureIntegrationTest {
    @Autowired
    private WorkflowService workflow;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void clear() {
        jdbc.update("DELETE FROM tx_events");
    }

    private long countRows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events", Long.class);
    }

    @Test
    void normalCompletionCommits() {
        workflow.success();
        assertEquals(1L, countRows());
    }

    @Test
    void catchingInnerFailureStillEndsWithUnexpectedRollback() {
        assertThrows(UnexpectedRollbackException.class,
                workflow::outerCatchesInnerFailure);
        assertEquals(0L, countRows());
    }

    @Test
    void duplicateSqlKeyThrowsDataAccessExceptionAndRollsBack() {
        assertThrows(DataIntegrityViolationException.class,
                workflow::duplicateKeyFailure);
        assertEquals(0L, countRows());
    }
}
```

**Không đặt `@Transactional` lên class test này.** Nếu test tự mở transaction và rollback ở cuối, bạn có thể nhìn thấy dữ liệu chưa commit và vô tình che khuất commit/rollback của service. Ở đây, mỗi test gọi bean từ bên ngoài, để proxy/service transaction **kết thúc**, rồi truy vấn số hàng bằng `JdbcTemplate`.

Bảng kỳ vọng:

| Test | Exception caller nhận | Số hàng sau lời gọi | Điều được chứng minh |
| --- | --- | ---: | --- |
| `normalCompletionCommits` | Không | 1 | Commit thành công |
| `catchingInnerFailureStillEndsWithUnexpectedRollback` | `UnexpectedRollbackException` | 0 | Outer không thể commit transaction đã rollback-only |
| `duplicateSqlKeyThrowsDataAccessExceptionAndRollsBack` | `DataIntegrityViolationException` (thường là subtype `DuplicateKeyException`) | 0 | SQL/data-access failure khác transaction-infrastructure exception nhưng vẫn gây rollback khi thoát qua proxy |

JUnit không bảo đảm thứ tự thực thi test; bảng trên mô tả từng test độc lập chứ không phải thứ tự log. H2 cho phép test đơn giản và nhất quán, nhưng không thay thế bài test khóa/isolation trên database production.

## 7. Unit test mô phỏng lỗi bắt đầu transaction và lỗi commit

Một lỗi hạ tầng thật (mất kết nối, commit thất bại) khó gây ra một cách ổn định trong mọi môi trường. Để **kiểm tra ranh giới API**, có thể dùng transaction manager giả lập. Bài test dưới đây chỉ xác minh cách `TransactionTemplate` truyền exception từ manager; **không chứng minh outcome của một database thật**.

`src/test/java/com/example/txerrors/TransactionManagerBoundaryTest.java`:

```java
package com.example.txerrors;

import org.junit.jupiter.api.Test;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.TransactionSystemException;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertThrows;

class TransactionManagerBoundaryTest {
    @Test
    void beginFailurePreventsBusinessCallback() {
        PlatformTransactionManager manager = new PlatformTransactionManager() {
            @Override
            public TransactionStatus getTransaction(TransactionDefinition definition) {
                throw new CannotCreateTransactionException("Simulated BEGIN failure");
            }

            @Override
            public void commit(TransactionStatus status) {
                throw new AssertionError("commit must not run");
            }

            @Override
            public void rollback(TransactionStatus status) {
                throw new AssertionError("rollback must not run");
            }
        };

        TransactionTemplate template = new TransactionTemplate(manager);

        assertThrows(CannotCreateTransactionException.class,
                () -> template.execute(status -> {
                    throw new AssertionError("callback must not run");
                }));
    }

    @Test
    void commitFailurePropagatesWithoutManualRollback() {
        PlatformTransactionManager manager = new PlatformTransactionManager() {
            @Override
            public TransactionStatus getTransaction(TransactionDefinition definition) {
                return new SimpleTransactionStatus();
            }

            @Override
            public void commit(TransactionStatus status) {
                throw new TransactionSystemException("Simulated COMMIT failure");
            }

            @Override
            public void rollback(TransactionStatus status) {
                throw new AssertionError("do not roll back after commit failure");
            }
        };

        TransactionTemplate template = new TransactionTemplate(manager);

        assertThrows(TransactionSystemException.class,
                () -> template.execute(status -> "business callback completed"));
    }
}
```

Trong test thứ nhất, `getTransaction` ném lỗi trước khi callback bắt đầu: ta biết callback chưa chạy. Trong test thứ hai, callback đã kết thúc, nhưng `commit` ném exception. Transaction manager ở đây cố ý **không kết nối database**; vì vậy không thể kết luận bất cứ điều gì về commit thực tế. Đây là lý do production cần cơ chế idempotency và đối soát dữ liệu khi gặp sự cố ở ranh giới commit.

Để chạy đầy đủ **5 test** (3 integration, 2 unit), ở thư mục có `build.gradle`:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

**Kết quả kỳ vọng:** cả 5 test pass, nếu Java 17+, Gradle/dependencies và schema H2 được thiết lập đúng. Bộ test không in một stdout cố định; xem kết quả JUnit và báo cáo `build/reports/tests/test/index.html`. Nếu cần thử mất kết nối/timeout thật, dùng database container và một công cụ kiểm soát lỗi tài nguyên ở môi trường test riêng, rồi xác minh lại trạng thái sau sự cố. Đừng giả mạo một exception rồi tuyên bố đã kiểm thử được atomicity của DB.

## 8. Xử lý lỗi có trách nhiệm tại boundary

Bất kỳ chiến lược lỗi transaction nào cũng nên trả lời **hai câu hỏi độc lập**: *nguyên nhân có thể khắc phục không?* và *trạng thái của thao tác đã chắc chắn chưa?*

| Lỗi | Hướng phản ứng | Có thể retry tự động? |
| --- | --- | --- |
| `CannotCreateTransactionException` trước khi callback chạy | Kiểm tra connectivity/pool, cảnh báo và giới hạn tải | Có thể, nếu lỗi tạm thời và operation idempotent |
| `TransactionUsageException` | Sửa cấu hình hoặc code giao dịch | Không nên retry cùng thao tác chưa sửa |
| `TransactionTimedOutException` | Đo lock/query/timeout; dừng chuỗi xử lý không an toàn | Cân nhắc sau khi biết trạng thái và idempotency |
| `UnexpectedRollbackException` | Xác định ai đánh dấu rollback-only và sửa boundary/logic | Không retry mù để che lỗi nghiệp vụ |
| `TransactionSystemException` ở commit/rollback | Bảo tồn cause; kiểm tra dữ liệu và các tác vụ phụ | **Không tự retry khi commit outcome chưa biết** |
| `HeuristicCompletionException` | Đối soát từng tài nguyên và xử lý bù | Không thể coi một retry đơn giản là phục hồi |

### 8.1. Idempotency trước khi retry

Ví dụ API tạo thanh toán có `requestId` duy nhất do caller cung cấp. Nếu kết nối đứt lúc commit, API có thể nhận exception dù database đã lưu thanh toán. Nếu client gửi lại **cùng requestId**, server phải tra cứu kết quả đã có trước khi tạo giao dịch mới, hoặc dựa vào unique constraint và logic đọc lại để trả cùng kết quả an toàn. Không tạo requestId mới cho mỗi lần retry rồi kỳ vọng "at least once" tự biến thành "exactly once".

Khi phát sinh lỗi commit, quy trình an toàn là ghi nhận định danh thao tác, tra cứu trạng thái ở nguồn sự thật và xử lý tình huống *chưa có / đã có / đang chờ đối soát*. Không thể suy ra từ `catch (TransactionException)` rằng mọi thay đổi đều đã hủy. Với email, message broker hoặc HTTP nằm ngoài transaction database, cần thiết kế outbox/idempotency/compensation phù hợp.

### 8.2. Ghi log và quan sát

Nên ghi nhận các dữ kiện có ích để debug:

- Request/job/correlation ID và operation ID; tên transaction/service, transaction manager được chọn.
- Giai đoạn: acquire connection, begin, SQL, flush, commit, rollback hay callback sau commit.
- Exception **cụ thể**, cause chain; với `TransactionSystemException` xem application exception được bảo tồn.
- SQLState/mã lỗi database (nếu có), thời gian transaction/query, pool usage, lock wait và thời điểm timeout.
- Bằng chứng dữ liệu sau transaction: có hoặc không có bản ghi với business key cụ thể.

Trong ứng dụng mẫu có thể tăng log để quan sát lúc Spring mở và kết thúc transaction:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Các tên log/thông điệp khác nhau giữa phiên bản và manager, nên **đừng viết test phụ thuộc chuỗi log cố định**. Không ghi credentials, dữ liệu cá nhân nhạy cảm hoặc toàn bộ SQL parameter vào log production.

### 8.3. Đọc trạng thái transaction một cách đúng ngữ cảnh

`TransactionSynchronizationManager.isActualTransactionActive()` có thể cho biết một transaction đang được Spring đánh dấu hoạt động trong ngữ cảnh hiện tại. Nó **không chứng minh** transaction ấy sẽ commit. `TransactionAspectSupport.currentTransactionStatus()` cung cấp `TransactionStatus` trong ngữ cảnh interceptor phù hợp; gọi ngoài ngữ cảnh có thể ném `NoTransactionException`.

Với `@Transactional` imperative, ngữ cảnh thường gắn với thread. Không tự cho rằng transaction được truyền qua `@Async` hay thread do application tạo. Transaction reactive dùng Reactor context và `ReactiveTransactionManager`, cần xử lý riêng theo publisher signal và reactive operator.

## 9. Các nhầm lẫn dễ gây sự cố

1. **“TransactionException là tất cả lỗi DB.”** Sai: `DataAccessException` là họ riêng và có thể xuất hiện cả ở commit/rollback tùy manager.
2. **“Gặp exception nghĩa là chắc chắn rollback.”** Sai: checked exception mặc định, lỗi sau commit, hoặc commit outcome không rõ đều là phản ví dụ.
3. **“Outer đã catch nên transaction sẽ commit.”** Sai nếu inner `REQUIRED` đã đánh dấu rollback-only.
4. **“Bắt `UnexpectedRollbackException` ngay trong chính outer method.”** Thường không bắt được lỗi do interceptor outer ném **sau khi method body return**; caller bên ngoài proxy mới thấy.
5. **“`@Transactional` trên inner tự hoạt động khi gọi `this.inner()`.”** Proxy mode mặc định không intercept self-invocation.
6. **“Lỗi rollback che nguyên nhân gốc nên không thể tìm ra.”** Hãy kiểm tra cause chain và, nếu có, `TransactionSystemException.getOriginalException()`.
7. **“Commit ném lỗi thì gọi rollback lần nữa.”** Vi phạm contract của `PlatformTransactionManager.commit`; không chứng minh được dữ liệu chưa commit.
8. **“Retry ngay sẽ giải quyết mọi exception.”** Với commit chưa rõ outcome, retry không idempotent có thể nhân đôi tác vụ.
9. **“`@Transactional` tự rollback email/HTTP call.”** Transaction JDBC chỉ bao phủ tài nguyên tham gia; external side effects cần cơ chế khác.
10. **“Test có `@Transactional` đọc thấy dữ liệu nghĩa là đã commit.”** Spring test thường rollback transaction test ở cuối; phải quan sát sau boundary thật.
11. **“`timeout = N` là toàn bộ request bị hủy sau N giây.”** Timeout transaction phụ thuộc khả năng thực thi của hạ tầng và chỉ áp dụng đúng phạm vi được quản lý.
12. **“`REQUIRES_NEW` là cách chữa mọi rollback-only.”** Nó mở transaction độc lập, có thể giữ thay đổi dù outer rollback và sử dụng thêm connection; phải phù hợp invariant nghiệp vụ.

## 10. Checklist chẩn đoán một lỗi transaction ngoài thực tế

Giả sử production báo "không tạo được đơn" và stack trace kết thúc bằng `TransactionException`:

1. **Phân loại** exception cụ thể; tìm cause gốc trước khi dự đoán status dữ liệu.
2. **Đánh dấu giai đoạn**: `getTransaction`, SQL, flush, commit, rollback, callback; lưu transaction manager/DB resource.
3. **Kiểm tra đường gọi qua proxy** và propagation: outer/inner có chung physical transaction không?
4. **Kiểm tra rollback rule**: runtime/checked exception, `rollbackFor`, nơi `catch`, rollback-only marker.
5. **Đọc sau boundary** bằng connection/ngữ cảnh độc lập, ưu tiên truy vấn bằng business key/idempotency key.
6. **Với commit không rõ trạng thái**, tạm dừng retry không idempotent, đối soát trước khi xử lý lại.
7. **Tái hiện có kiểm soát**: một integration test cho kết quả dữ liệu; một test lỗi giả lập cho từng boundary phù hợp.
8. **Sửa nguyên nhân** (manager/config, timeout, propagation, logic nghiệp vụ hoặc SQL) rồi kiểm tra cả nhánh thành công và nhánh lỗi.

### Tự kiểm tra

**Câu 1.** `JdbcTemplate` ném `DuplicateKeyException`. Có phải `TransactionException` không?  
**Đáp án:** Không. Nó thuộc họ `DataAccessException` (cụ thể là một `DataIntegrityViolationException`), nhưng vẫn là runtime exception và thường kích hoạt rollback mặc định nếu thoát qua transaction interceptor.

**Câu 2.** Inner `REQUIRED` ném runtime exception, outer bắt và return. Vì sao caller ngoài vẫn nhận `UnexpectedRollbackException`?  
**Đáp án:** Inner interceptor đã đánh dấu physical transaction dùng chung rollback-only; outer định commit một transaction không còn được phép commit, nên Spring thông báo rollback ngoài dự kiến.

**Câu 3.** `TransactionSystemException` ở commit có cho phép giả định database chưa ghi dữ liệu?  
**Đáp án:** Không. Có trường hợp outcome không rõ; cần tra cứu trạng thái bằng định danh nghiệp vụ và cơ chế idempotency/đối soát.

**Câu 4.** Khi `commit(status)` ném lỗi, có nên gọi `rollback(status)` ngay?  
**Đáp án:** Không. `PlatformTransactionManager` xem status đã hoàn tất/cleanup sau commit attempt; rollback thêm trên cùng status không phải phương pháp khôi phục hợp lệ.

**Câu 5.** Unit test giả lập `CannotCreateTransactionException` có thay thế được kiểm thử mất kết nối trên database thật không?  
**Đáp án:** Không. Nó xác minh exception path của code; muốn kiểm chứng tác động thực tế phải dùng integration test/kiểm thử lỗi tài nguyên được kiểm soát.

## Tài liệu chính thức

- [Spring Framework — TransactionException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionException.html)
- [Spring Framework — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Controlling Database Connections / JdbcTransactionManager](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
