# Phân biệt lỗi nghiệp vụ với lỗi commit hoặc rollback khi dùng API giao dịch trực tiếp của Spring

## 1. Vấn đề thực tế: ba loại thất bại không thể xử lý giống nhau

Một ứng dụng đặt hàng thường làm các bước: kiểm tra quy tắc nghiệp vụ, cập nhật cơ sở dữ liệu, commit transaction rồi trả kết quả. Trong luồng ấy có thể xuất hiện những lỗi khác nhau:

- **Lỗi nghiệp vụ (business/domain error):** ví dụ số dư không đủ, đơn hàng đã đóng, số tiền không hợp lệ. Code ứng dụng từ chối yêu cầu theo một quy tắc cụ thể.
- **Lỗi thao tác dữ liệu:** ví dụ câu lệnh SQL vi phạm khóa duy nhất hoặc kết nối DB bị lỗi trong khi xử lý. Đây là lỗi tài nguyên; nó có thể được ánh xạ thành domain error chỉ khi ứng dụng hiểu chính xác nguyên nhân.
- **Lỗi commit:** business callback đã kết thúc bình thường nhưng transaction manager không hoàn tất bước commit theo dự kiến.
- **Lỗi rollback:** sau một lỗi nghiệp vụ hoặc lỗi SQL, ứng dụng yêu cầu rollback, nhưng manager/resource thất bại khi hoàn tác.

Tình huống thứ nhất:

~~~text
BEGIN T1
  kiểm tra business: OK
  INSERT: OK
  callback trả "OK"
COMMIT T1 -> TransactionSystemException
Caller nhận lỗi ở giai đoạn COMMIT.
~~~

Tình huống thứ hai:

~~~text
BEGIN T2
  callback ném BusinessRuleException
ROLLBACK T2 -> TransactionSystemException
Caller có thể nhận lỗi ROLLBACK thay vì lỗi business ban đầu.
~~~

**Nguyên tắc:** phải xác định **lỗi xảy ra ở giai đoạn nào**, **nguyên nhân gốc là gì** và **trạng thái transaction đã biết chắc hay chưa**. Không thể chỉ dựa vào class exception cuối cùng rồi khẳng định dữ liệu chắc chắn commit hoặc rollback.

Bài Knowledge này thuộc nhóm **API giao dịch trực tiếp** của Spring Framework, tập trung vào:

- `TransactionTemplate.execute(TransactionCallback)`: Spring quản lý vòng đời transaction qua callback.
- `PlatformTransactionManager`: lập trình viên trực tiếp gọi `getTransaction(...)`, `commit(status)`, `rollback(status)`.

Sau bài học, bạn sẽ biết phân loại lỗi domain và lỗi hạ tầng, bảo toàn lỗi gốc khi rollback cũng thất bại, tránh gọi rollback lần hai sau lỗi commit, sử dụng `setRollbackOnly()` đúng cách và thiết kế retry/idempotency an toàn.

## 2. Bốn giai đoạn và exception đặc trưng

~~~mermaid
flowchart TD
    A["Caller"] --> B["getTransaction(definition)"]
    B --> C{"Begin có thành công?"}
    C -->|"Không"| D["Lỗi tạo transaction"]
    C -->|"Có"| E["Business body / SQL"]
    E --> F{"Body ném lỗi?"}
    F -->|"Có"| G["rollback(status)"]
    G --> H{"Rollback thành công?"}
    H -->|"Có"| I["Trả lỗi body ban đầu"]
    H -->|"Không"| J["Lỗi rollback có thể che lỗi body"]
    F -->|"Không"| K["commit(status)"]
    K --> L{"Commit thành công?"}
    L -->|"Có"| M["Trả kết quả"]
    L -->|"Không"| N["Lỗi commit; xác minh trạng thái cuối"]
~~~

| Pha | Ví dụ lỗi | Kết luận an toàn |
| --- | --- | --- |
| **Begin** | `CannotCreateTransactionException` | Chưa lấy được status hợp lệ để rollback |
| **Business body** | `BusinessRuleException` | Domain từ chối; cần hoàn tác các ghi đã tham gia transaction nếu nghiệp vụ yêu cầu |
| **SQL body** | `DataIntegrityViolationException` | SQL/constraint thất bại; không tự đồng nghĩa lỗi commit |
| **Commit** | `UnexpectedRollbackException` | Coordinator rollback khi caller mong commit |
| **Commit** | `TransactionSystemException` | Commit gặp sự cố; có trường hợp outcome cần đối soát |
| **Rollback** | `TransactionSystemException` | Hoàn tác gặp sự cố; phải giữ lỗi gốc và xác minh trạng thái |

Một số ORM như JPA/Hibernate có thể **flush dữ liệu trễ** tại commit. Vì thế, lỗi constraint vẫn có thể xuất hiện ở commit phase, dù lỗi gốc là dữ liệu không hợp lệ. Ghi nhận **pha quan sát** và **nguyên nhân kỹ thuật** riêng biệt.

### Phân biệt các tín hiệu

**Lỗi nghiệp vụ** trả lời: yêu cầu không thỏa quy tắc domain nào?

**Lỗi commit hoặc rollback** trả lời: hệ thống điều phối transaction có hoàn tất hoặc hoàn tác được không?

Hai điều này có thể cùng xuất hiện: `BusinessRuleException` xảy ra đầu tiên, sau đó `TransactionSystemException` phát sinh khi rollback. Caller có thể chỉ thấy exception transaction nếu không lưu thông tin lỗi trước đó.

## 3. Lỗi nghiệp vụ: exception hay Outcome?

Ví dụ luật domain:

~~~java
if (amount <= 0) {
    throw new BusinessRuleException("INVALID_AMOUNT");
}
~~~

Đây là đoạn minh họa; class `BusinessRuleException` được định nghĩa đầy đủ ở mục 8. Nó có thể là runtime exception riêng biệt với các lỗi hạ tầng Spring.

Khi nghiệp vụ từ chối **trước khi ghi DB**, không nhất thiết phải mở transaction. Khi đã ghi một phần và sau đó domain từ chối, cần quyết định transaction có được giữ các thay đổi ấy hay không.

Với `TransactionTemplate`, cách ném runtime exception:

~~~java
try {
    template.execute(status -> {
        verifyBusinessRules();
        writeRows();
        return null;
    });
} catch (BusinessRuleException ex) {
    // Domain từ chối; template đã yêu cầu rollback.
}
~~~

Đây là đoạn minh họa cần biến `template` và hai helper thực tế. Exception ban đầu sẽ được ném lại nếu rollback **thành công**.

Nếu nghiệp vụ từ chối là một kết quả bình thường, có thể trả Outcome thay vì ném exception:

~~~java
Outcome outcome = template.execute(status -> {
    saveSomeData();
    status.setRollbackOnly();
    return new Outcome("DECLINED");
});
~~~

Đây cũng là đoạn minh họa. Nếu đã lưu dữ liệu rồi trả `DECLINED` **mà không gọi `setRollbackOnly()`**, template vẫn có thể commit vì callback đã hoàn thành bình thường.

**Đừng dùng `catch(RuntimeException)` rồi mặc nhiên trả business error.** `DataAccessException` và `TransactionException` đều là runtime exceptions, nhưng không phải domain rejection.

## 4. TransactionTemplate: callback thành công chưa phải commit thành công

Ví dụ:

~~~java
TransactionTemplate template = new TransactionTemplate(manager);
String result = template.execute(status -> {
    jdbc.update("INSERT INTO tx_event(id, description) VALUES (?, ?)",
                1L, "saved");
    return "OK";
});
~~~

Đây là snippet cần các biến `manager` và `jdbc` được cung cấp bởi Spring.

Đường xử lý phổ biến của `TransactionTemplate.execute(...)`:

1. `getTransaction(...)` lấy/bắt đầu transaction.
2. Gọi `TransactionCallback.doInTransaction(status)`.
3. Callback trả bình thường → gọi `commit(status)`. Nếu `status` rollback-only, manager có thể thực hiện rollback theo contract.
4. Callback ném `RuntimeException` hoặc `Error` → cố gọi `rollback(status)`.
5. Nếu rollback thành công, exception callback được ném lại cho caller.
6. Nếu rollback thất bại, exception transaction có thể **thay thế exception callback làm lỗi bề mặt**.
7. Nếu commit thất bại, `execute(...)` **ném lỗi commit** dù callback vừa trả `"OK"`.

~~~text
TransactionTemplate.execute
    begin
    callback -> return "OK"
    commit
        thành công -> execute trả "OK"
        lỗi        -> execute ném exception
~~~

Vì vậy không nên phát event `ORDER_COMMITTED` không thể rollback ngay trong callback. Trong scope sở hữu transaction mới, chỉ sau `execute(...)` hoàn tất thành công mới có căn cứ manager đã commit.

### Runtime và checked exceptions

Giao diện `TransactionCallback<T>` **không khai báo checked exceptions**. Một lambda ném trực tiếp `IOException` cần được catch/chuyển đổi, hoặc biểu diễn lỗi bằng Outcome + `setRollbackOnly()`.

Ví dụ cách giữ cause của checked exception:

~~~java
try {
    callExternalLibrary();
} catch (IOException ex) {
    throw new IllegalStateException("External operation failed", ex);
}
~~~

Đây là snippet minh họa cần helper `callExternalLibrary()`. Lúc này exception thoát callback là **unchecked**, nên template yêu cầu rollback. Tuy nhiên, với HTTP/API bên ngoài, rollback DB không thu hồi side effect mạng đã hoàn tất.

Đừng giả định `rollbackFor` của `@Transactional` được áp dụng cho mọi `TransactionTemplate`. Template có hành vi callback riêng; nếu cần xử lý checked exception và preserve signature, manager trực tiếp là một lựa chọn.

### setRollbackOnly không tự tạo business exception

~~~java
String result = template.execute(status -> {
    status.setRollbackOnly();
    return "DECLINED";
});
~~~

Khi template bắt đầu transaction mới, local rollback-only khiến manager rollback thay vì commit; callback vẫn có thể trả Outcome bình thường. Nếu template **tham gia transaction ngoài** bằng REQUIRED, rollback-only có thể làm transaction chung không commit, dẫn đến `UnexpectedRollbackException` ở outer boundary. Luôn xem propagation và ai sở hữu physical transaction.

## 5. Các exception giao dịch cần hiểu

| Exception | Ý nghĩa điển hình |
| --- | --- |
| `CannotCreateTransactionException` | Manager không tạo/tham gia được transaction |
| `TransactionTimedOutException` | Deadline transaction được phát hiện quá hạn |
| `IllegalTransactionStateException` | Lỗi sử dụng trạng thái transaction, ví dụ hoàn tất status hai lần |
| `UnexpectedRollbackException` | Caller mong commit nhưng coordinator rollback |
| `TransactionSystemException` | Lỗi transaction system, có thể ở commit hoặc rollback |
| `HeuristicCompletionException` | Tình huống heuristic của coordinator phân tán, có thể mixed outcome |

### 5.1. UnexpectedRollbackException: thường có rollback thật

Ví dụ:

~~~text
Outer REQUIRED: tạo T1
  Inner REQUIRED: tham gia T1
    Inner ném RuntimeException
    Transaction interceptor đánh dấu T1 rollback-only
  Outer catch exception rồi return bình thường
Outer gọi commit
  Manager thấy rollback-only, rollback T1
  Caller nhận UnexpectedRollbackException
~~~

Đây **không phải** “DB chắc chắn đã commit nhưng mất phản hồi”. Nó thông báo commit mong đợi đã **không xảy ra** vì coordinator rollback.

### 5.2. TransactionSystemException: che mất lỗi ứng dụng trước đó

Khi callback ném `BusinessRuleException`, template cố rollback. Nếu rollback ném `TransactionSystemException`, exception cuối có thể là lỗi transaction chứ không phải lỗi domain.

Spring `TransactionTemplate` có đường giữ lỗi gốc bằng `TransactionSystemException.initApplicationException(original)`. Caller có thể hỏi:

~~~java
catch (TransactionSystemException ex) {
    Throwable initial = ex.getApplicationException();
    // initial có thể là BusinessRuleException.
}
~~~

Đây là snippet minh họa. `getApplicationException()` có thể trả **null**, chẳng hạn commit failure sau callback thành công. Với những loại runtime exception rollback khác, không phải lúc nào lỗi gốc cũng được lưu theo cơ chế này. Nếu tự dùng manager, hãy bảo toàn lỗi bằng suppressed/cause hoặc context logging.

### 5.3. DataAccessException xuất hiện trong body hoặc tại commit

Với JDBC, INSERT vi phạm primary key thường ném `DataIntegrityViolationException` tại câu SQL. Với JPA hoặc deferred constraint, lỗi có thể lộ diện tại flush/commit. Phân biệt:

- **Nguồn:** ràng buộc database hoặc lỗi SQL.
- **Pha quan sát:** body hay commit.
- **Kết quả transaction:** rollback thành công, failed commit hay chưa xác nhận.

Không áp một nhãn domain cho tất cả constraint violations. Chỉ ánh xạ khi constraint cụ thể tương ứng business rule đã được xác định, ví dụ khóa duy nhất của idempotency key.

## 6. PlatformTransactionManager trực tiếp: cách viết try/catch đúng

Các phương thức:

~~~java
TransactionStatus status = manager.getTransaction(definition);
// Thực hiện các thao tác thuộc scope này.
manager.commit(status);
~~~

Đây là skeleton; khi body lỗi phải rollback.

### Anti-pattern: rollback sau lỗi commit

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    writeBusinessData();
    manager.commit(status);
} catch (RuntimeException ex) {
    manager.rollback(status);  // SAI nếu exception phát sinh từ commit!
    throw ex;
}
~~~

Đây là **anti-pattern**. Hợp đồng Spring `PlatformTransactionManager.commit(status)` chỉ rõ transaction được hoàn tất và cleanup khi lời gọi commit kết thúc **dù commit thành công hay ném exception**. Vì vậy **không gọi `rollback(status)` sau khi `commit(status)` ném lỗi**. Làm vậy có thể ném `IllegalTransactionStateException` và che lỗi commit gốc.

### Mẫu đúng: tách try của body khỏi commit

~~~java
TransactionStatus status = manager.getTransaction(definition);

try {
    writeBusinessData();
} catch (RuntimeException | Error original) {
    try {
        manager.rollback(status);
    } catch (TransactionException rollbackFailure) {
        rollbackFailure.addSuppressed(original);
        throw rollbackFailure;
    }
    throw original;
}

// Không nằm trong catch xử lý lỗi body.
manager.commit(status);
~~~

Đây là snippet mô tả pattern; mục 8 có phương thức Java đầy đủ dùng cùng cách.

Những điều phải nhớ:

1. Nếu `getTransaction(...)` thất bại, bạn chưa có status hợp lệ để rollback.
2. Nếu body thất bại **trước khi gọi commit**, rollback một lần bằng status vừa nhận.
3. Nếu rollback thất bại, **bảo toàn exception body ban đầu** (ví dụ `rollbackFailure.addSuppressed(original)`).
4. Nếu body thành công, gọi commit ngoài catch của body.
5. Nếu commit ném exception, không rollback tiếp cùng status; truyền lỗi cho caller để phân loại/đối soát.
6. Nếu manager tham gia transaction ngoài, lệnh `commit(status)` của scope con có thể chưa là physical commit cuối.

### Nếu business code có checked exception

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    operationThatMayThrowIOException();
} catch (IOException original) {
    try {
        manager.rollback(status);
    } catch (TransactionException rollbackFailure) {
        rollbackFailure.addSuppressed(original);
        throw rollbackFailure;
    }
    throw original;
}
manager.commit(status);
~~~

Đây là snippet cần helper và method `throws IOException`. Với manual manager, lập trình viên tự quyết định bắt/rollback/rethrow checked exception. Không có quy tắc tự động “checked exception không rollback” trừ khi chính code của bạn triển khai quyết định đó.

## 7. Trạng thái kết thúc: commit, rollback và unknown

### Lỗi commit có thể không xác định outcome

~~~text
Application ------------------> Database: COMMIT
                      (mất kết nối trước ACK)
Application <----------X------- Database: không nhận phản hồi
~~~

Một DB có thể đã commit trước khi đường mạng hỏng, hoặc chưa. Chỉ từ exception phía client không luôn xác định được. **Không retry ghi với key mới một cách mù quáng**, nhất là lệnh thanh toán/chuyển tiền.

Cách an toàn:

1. Cấp **idempotency key** cho logical operation.
2. Đặt unique constraint trên key và ghi cùng transaction với business change.
3. Khi commit outcome không rõ, đối soát qua kết nối mới theo key và trạng thái nghiệp vụ.
4. Chỉ retry khi contract cho phép; giới hạn số lần và có backoff.
5. Xử lý tình huống replica lag hoặc transaction đầu vẫn đang hoàn tất; một SELECT không thấy dữ liệu ngay lập tức chưa phải bằng chứng tuyệt đối chưa commit.

### Bảng trạng thái

| Tín hiệu | Điều có thể kết luận |
| --- | --- |
| Commit scope mới trả thành công | Manager hoàn tất commit theo contract của resource |
| Rollback trả thành công | Manager báo rollback của scope phù hợp đã hoàn tất |
| `UnexpectedRollbackException` | Coordinator rollback thay vì commit dự kiến |
| Rollback `TransactionSystemException` | Không xác nhận rollback thành công, cần điều tra |
| Lỗi mạng/resource ở commit | Có thể chưa xác nhận outcome, cần đối soát |
| SQL constraint trong body | SQL đó thất bại, nhưng phải xem transaction đã rollback chưa |
| Callback trả business Outcome | Không suy ra commit hay rollback nếu không xem status và completion |

Không dùng nhãn UNKNOWN cho mọi lỗi: `UnexpectedRollbackException` có tín hiệu rollback rõ hơn. Nhưng với lỗi network đúng thời điểm commit, phải thận trọng.

## 8. Bài thực hành Java 17+: lỗi nghiệp vụ, lỗi SQL và lỗi commit/rollback giả lập

Bài thực hành chia hai phần:

- **Spring Boot + JDBC/H2 thật:** kiểm chứng dữ liệu commit/rollback của callback.
- **Fake `PlatformTransactionManager` trong bộ thử riêng:** tiêm lỗi commit và rollback để biết exception nào đến caller. Fake manager **không giao tiếp với DB**, nên không thể dùng nó chứng minh DB đã commit/rollback.

### 8.1. Maven project

Tạo Spring Boot 3.x Maven project tương thích Java 17+, chọn **JDBC API** (`spring-boot-starter-jdbc`) và **H2 Database**. Giữ file `pom.xml` hoàn chỉnh của Spring Initializr. Dependencies:

~~~xml
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
</dependencies>
~~~

Đây là **trích đoạn dependencies**, không phải toàn bộ `pom.xml`.

Cấu trúc:

~~~text
src/main/
  java/com/example/txerrors/
    TxErrorApplication.java
    BusinessRuleException.java
    FaultSimulation.java
  resources/
    schema.sql
    application.properties
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE tx_event (
    id BIGINT PRIMARY KEY,
    description VARCHAR(120) NOT NULL
);
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:tx_error_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

H2 in-memory làm ví dụ độc lập với PostgreSQL/MySQL và có dữ liệu trống khi khởi động JVM mới.

### 8.2. BusinessRuleException.java

~~~java
package com.example.txerrors;

public final class BusinessRuleException extends RuntimeException {
    public BusinessRuleException(String code) {
        super(code);
    }
}
~~~

Đây là **file đầy đủ**. Mã lỗi domain được đặt trong message để stdout ngắn gọn; ở hệ thống thật có thể dùng field `code` riêng.

### 8.3. TxErrorApplication.java

~~~java
package com.example.txerrors;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TxErrorApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxErrorApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {

        return args -> {
            TransactionTemplate template = new TransactionTemplate(manager);

            // Callback và commit thành công.
            template.execute(status -> {
                insert(jdbc, 1L, "accepted");
                return null;
            });
            System.out.println("after success rows=" + count(jdbc));

            // Lỗi nghiệp vụ ném từ callback.
            try {
                template.execute(status -> {
                    insert(jdbc, 2L, "rejected");
                    throw new BusinessRuleException("LIMIT_EXCEEDED");
                });
            } catch (BusinessRuleException ex) {
                System.out.println("business code=" + ex.getMessage());
            }
            System.out.println("after business rows=" + count(jdbc));

            // Business Outcome không ném exception.
            Outcome denied = template.execute(status -> {
                insert(jdbc, 3L, "declined");
                status.setRollbackOnly();
                return new Outcome("DECLINED");
            });
            System.out.printf(
                "outcome=%s, rows=%d%n", denied.code(), count(jdbc));

            // Lỗi SQL được phát hiện trong callback JDBC.
            try {
                template.execute(status -> {
                    insert(jdbc, 4L, "before duplicate");
                    insert(jdbc, 1L, "duplicate key");
                    return null;
                });
            } catch (DataIntegrityViolationException ex) {
                System.out.println(
                    "sql error=DataIntegrityViolationException");
            }
            System.out.println("after sql rows=" + count(jdbc));

            // Vòng đời thủ công: getTransaction/commit.
            insertManually(manager, jdbc, 5L);
            System.out.println("after manual rows=" + count(jdbc));

            // Chỉ test đường exception, không tác động DB thật.
            FaultSimulation.run();
        };
    }

    private static void insert(
            JdbcTemplate jdbc, long id, String description) {
        jdbc.update(
            "INSERT INTO tx_event(id, description) VALUES (?, ?)",
            id, description);
    }

    private static int count(JdbcTemplate jdbc) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_event", Integer.class);
        return result;
    }

    private static void insertManually(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc, long id) {

        DefaultTransactionDefinition definition =
            new DefaultTransactionDefinition();
        definition.setName("manual-insert");

        TransactionStatus status = manager.getTransaction(definition);

        try {
            insert(jdbc, id, "manual");
        } catch (RuntimeException | Error original) {
            try {
                manager.rollback(status);
            } catch (TransactionException rollbackFailure) {
                rollbackFailure.addSuppressed(original);
                throw rollbackFailure;
            }
            throw original;
        }

        // Nằm NGOÀI catch của phần body.
        // Nếu commit ném lỗi, KHÔNG rollback lại status.
        manager.commit(status);
    }

    private record Outcome(String code) {}
}
~~~

Giải thích:

1. Id=1 được commit, count=1.
2. Id=2 được ghi rồi domain exception thoát callback; template rollback, count vẫn 1.
3. Id=3 được ghi rồi status rollback-only, callback trả Outcome; count vẫn 1.
4. Id=4 được ghi, sau đó INSERT trùng PK id=1 gây `DataIntegrityViolationException`; template rollback id=4, count vẫn 1.
5. `insertManually` commit id=5 qua API trực tiếp, count=2.
6. `FaultSimulation.run()` không dùng H2; nó chỉ mô phỏng lỗi manager ở commit/rollback.

Trong demo, `CommandLineRunner` không có transaction bao ngoài, nên mỗi lời gọi `template.execute` dùng propagation REQUIRED mặc định và tạo một transaction mới với cấu hình một DataSource. `JdbcTemplate` và manager cùng quản lý H2.

### 8.4. FaultSimulation.java

~~~java
package com.example.txerrors;

import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.TransactionSystemException;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

final class FaultSimulation {

    private FaultSimulation() {}

    static void run() {
        // Callback thành công, manager giả lập lỗi COMMIT.
        try {
            TransactionTemplate template =
                new TransactionTemplate(new FaultManager(Phase.COMMIT));

            template.execute(status -> "callback-success");
        } catch (TransactionSystemException ex) {
            System.out.println("commit phase=" + ex.getMessage());
            System.out.println(
                "commit had business error=" +
                (ex.getApplicationException() != null));
        }

        // Callback lỗi nghiệp vụ, manager giả lập lỗi ROLLBACK.
        try {
            TransactionTemplate template =
                new TransactionTemplate(new FaultManager(Phase.ROLLBACK));

            template.execute(status -> {
                throw new BusinessRuleException("POLICY_DENIED");
            });
        } catch (TransactionSystemException ex) {
            System.out.println("rollback phase=" + ex.getMessage());
            System.out.println(
                "original business preserved=" +
                (ex.getApplicationException()
                    instanceof BusinessRuleException));
        }
    }

    private enum Phase { COMMIT, ROLLBACK }

    private static final class FaultManager
            implements PlatformTransactionManager {

        private final Phase failingPhase;

        FaultManager(Phase failingPhase) {
            this.failingPhase = failingPhase;
        }

        @Override
        public TransactionStatus getTransaction(
                TransactionDefinition definition) {
            // Fake status, KHÔNG mở giao dịch DB.
            return new SimpleTransactionStatus(true);
        }

        @Override
        public void commit(TransactionStatus status) {
            if (failingPhase == Phase.COMMIT) {
                throw new TransactionSystemException("COMMIT_FAULT");
            }
        }

        @Override
        public void rollback(TransactionStatus status) {
            if (failingPhase == Phase.ROLLBACK) {
                throw new TransactionSystemException("ROLLBACK_FAULT");
            }
        }
    }
}
~~~

**Giới hạn quan trọng:** `FaultManager` là test double tối thiểu. Nó không mở transaction, không commit/rollback DB và không đại diện cho mọi trạng thái/cleanup của manager production. Nó chỉ giúp kiểm chứng **exception routing** của `TransactionTemplate` một cách tái lập.

Trong đường `TransactionTemplate` khi rollback ném `TransactionSystemException`, Spring lưu exception callback ban đầu qua `initApplicationException(...)`. Vì vậy case ROLLBACK_FAULT có thể đọc lại `BusinessRuleException`. Case COMMIT_FAULT không có business exception trước đó, nên `getApplicationException() == null`.

### 8.5. Chạy và expected stdout

Trong thư mục Maven có `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Bỏ qua log Spring/H2 (có thể có log lỗi rollback cố tình từ fake), các dòng do `System.out` trong chương trình in là:

~~~text
after success rows=1
business code=LIMIT_EXCEEDED
after business rows=1
outcome=DECLINED, rows=1
sql error=DataIntegrityViolationException
after sql rows=1
after manual rows=2
commit phase=COMMIT_FAULT
commit had business error=false
rollback phase=ROLLBACK_FAULT
original business preserved=true
~~~

**Đọc kết quả:**

- `after business rows=1`: lỗi nghiệp vụ đã làm rollback transaction chứa id=2.
- `outcome=DECLINED, rows=1`: rollback-only hủy INSERT id=3 dù callback trả bình thường.
- `after sql rows=1`: lỗi SQL trong callback đã làm rollback id=4.
- `after manual rows=2`: manager trực tiếp đã commit id=5.
- `commit had business error=false`: callback fake hoàn thành, lỗi chỉ nằm ở commit.
- `original business preserved=true`: lỗi rollback của fake trở thành exception bề mặt, nhưng lỗi domain từ callback vẫn được Spring giữ lại.

Không nhầm các kết quả của **fake** với một kiểm thử có DB thật.

## 9. Cách xử lý khi commit outcome không rõ

Một thiết kế tạo thanh toán an toàn không nên retry vô điều kiện khi COMMIT bị mất phản hồi. Các biện pháp:

- Cấp **idempotency key** cho logical request.
- Có unique constraint trên key ở DB.
- Ghi idempotency record **cùng transaction** với business data.
- Khi commit không rõ, đối soát bằng connection mới theo key và trạng thái nghiệp vụ.
- Retry chỉ khi đã đủ thông tin hoặc giao thức idempotent cho phép; có giới hạn lần thử và backoff.
- Không coi kết quả SELECT ngay trên replica chưa đồng bộ là bằng chứng tuyệt đối chưa commit.

Một lỗi nghiệp vụ ổn định như `INVALID_AMOUNT` thường không nên được retry với cùng input. Lỗi deadlock/serialization hoặc lỗi DB tạm thời có thể retry **toàn bộ transaction** khi thao tác idempotent và có chính sách rõ.

**Phân biệt:** `UnexpectedRollbackException` cho biết coordinator rollback thay vì commit; không đưa mọi lỗi commit vào cùng nhóm UNKNOWN.

## 10. Phân loại lỗi khi trả API và ghi log

Có thể thiết kế tầng nghiệp vụ và tầng transaction riêng:

| Tình huống | Cách phản hồi thường phù hợp |
| --- | --- |
| Validation/domain rejection và rollback thành công | Mã business ổn định; 400/409/422 tùy API contract |
| Data-access error không dự kiến | Lỗi hạ tầng; thường 500/503 tùy ngữ cảnh |
| Transaction begin/commit/rollback lỗi | Lỗi kỹ thuật; correlation ID, log phase và nguyên nhân |
| Commit outcome chưa xác nhận | Trạng thái cần đối soát hoặc lỗi kỹ thuật; không tuyên bố đã hủy ghi dữ liệu |
| Rollback failure che lỗi business | Ưu tiên cảnh báo hạ tầng, bảo toàn business code trong diagnosis |
| Idempotency key đã có kết quả cũ | Đối soát, trả kết quả tương ứng theo contract |

Các mã HTTP chỉ là **ví dụ thiết kế**, không phải ánh xạ cứng của Spring. Nếu tình huống tài chính có outcome UNKNOWN, không trả thông báo “tiền chưa bị trừ” khi chưa đủ bằng chứng.

Mẫu log:

~~~text
operation=createOrder
correlationId=request-123
phase=ROLLBACK
errorFamily=TRANSACTION_SYSTEM
errorType=TransactionSystemException
originalBusinessCode=LIMIT_EXCEEDED
outcome=UNKNOWN
~~~

Đây là **mẫu minh họa**, không phải stdout của chương trình. Chỉ dùng `outcome=UNKNOWN` khi dữ liệu thực sự chưa xác định. Tránh log PII, credentials, access token và payload nhạy cảm không cần thiết.

## 11. Kiểm thử cần có

### Unit test bằng fake/mock manager

- `getTransaction(...)` ném lỗi: callback không chạy và không rollback với status chưa tồn tại.
- Callback ném business exception: template yêu cầu rollback.
- Callback hoàn thành: template gọi commit.
- Callback hoàn thành, commit fail: commit exception được truyền tới caller.
- Callback ném business exception, rollback fail: transaction exception bề mặt và lỗi business gốc được giữ.
- Code manual **không gọi rollback thêm sau khi commit exception**.
- Code manual bảo toàn original exception bằng suppressed nếu rollback fail.

### Integration test với database

- Callback INSERT rồi return: dữ liệu tồn tại sau commit.
- Callback INSERT rồi ném domain exception: dữ liệu không tồn tại sau rollback.
- Callback INSERT rồi `setRollbackOnly()`: dữ liệu không tồn tại dù callback trả Outcome.
- Callback INSERT rồi vi phạm PK: dữ liệu INSERT trước lỗi không còn sau rollback.
- Nếu dùng ORM/DB có deferred constraints: kiểm thử cả lỗi flush/commit-time.
- Nếu production dùng PostgreSQL/MySQL, chạy integration test trên đúng DBMS tương ứng (ví dụ Testcontainers).

**Lưu ý Spring Test:** test method có `@Transactional` có thể mở transaction ngoài và tự rollback cuối test. Nó thay đổi ngữ nghĩa của `TransactionTemplate` REQUIRED và che physical commit thật. Với test muốn quan sát commit, chạy từ caller không có transaction bao ngoài.

## 12. Những lỗi tư duy phổ biến

**Sai 1:** Mọi `RuntimeException` đều là business rejection. `TransactionException` và `DataAccessException` cũng là runtime exceptions.

**Sai 2:** Callback trả `"SUCCESS"` nghĩa là commit hoàn tất. Template commit **sau callback**.

**Sai 3:** `status.setRollbackOnly()` sẽ ném exception. Nó chỉ đánh dấu cách hoàn tất; callback vẫn có thể trả Outcome.

**Sai 4:** Đặt `commit(status)` trong try body rồi gọi rollback ở catch chung. Commit đã cleanup status, không rollback lần hai.

**Sai 5:** Business exception bị rollback exception che nghĩa là business error chưa từng xảy ra. Cần xem `getApplicationException()` hoặc suppressed/cause.

**Sai 6:** `TransactionSystemException` ở commit chắc chắn có nghĩa DB đã rollback. Outcome đôi khi không rõ.

**Sai 7:** `UnexpectedRollbackException` nghĩa là DB đã commit. Thực tế nó báo rollback ngoài mong đợi.

**Sai 8:** Lỗi constraint ở body có nghĩa commit error. Phải phân biệt pha; ORM có thể phát hiện constraint muộn tại flush.

**Sai 9:** Lambda `TransactionTemplate` trực tiếp ném mọi checked exception. Callback API không khai báo checked exceptions.

**Sai 10:** Retry bằng business ID mới ngay sau lỗi commit. Có thể ghi trùng nếu commit đầu đã thành công nhưng mất phản hồi.

**Sai 11:** Fake manager chứng minh database đã rollback. Fake chỉ kiểm tra cách API truyền exception.

**Sai 12:** Gọi commit/rollback hai lần trên một status hoàn tất. Mỗi transaction scope cần một lần completion thích hợp.

## 13. Bài tập tự kiểm tra

**Câu 1.** Callback INSERT id=10 rồi ném `BusinessRuleException`. Rollback thành công. Caller nhận gì?

**Đáp án:** BusinessRuleException và dữ liệu INSERT thuộc transaction đã rollback; đây là lỗi domain trong body, không phải commit failure.

**Câu 2.** Callback trả thành công rồi commit ném lỗi. Có trả OK cho client không?

**Đáp án:** Không. Phải xử lý lỗi commit và xác minh outcome khi cần.

**Câu 3.** Rollback fail sau business exception. Cần bảo toàn gì?

**Đáp án:** Lỗi transaction và lỗi domain gốc; trong đường template có thể xem `TransactionSystemException.getApplicationException()`.

**Câu 4.** Vì sao không rollback trong catch bao cả commit?

**Đáp án:** Nếu lỗi ném từ commit, status đã hoàn tất/cleanup, rollback thêm có thể gây `IllegalTransactionStateException` và che lỗi commit.

**Câu 5.** Callback return `DECLINED` sau khi INSERT nhưng không rollback-only, có chắc dữ liệu bị hủy không?

**Đáp án:** Không. Callback return bình thường có thể dẫn tới commit.

**Câu 6.** `UnexpectedRollbackException` xuất hiện khi outer commit sau khi inner REQUIRED đã đánh dấu rollback-only. Trạng thái T1?

**Đáp án:** T1 bị rollback thay vì commit dự kiến. Cần tìm scope đã đánh dấu rollback-only.

**Câu 7.** Mất phản hồi COMMIT nhưng ứng dụng đã gửi lệnh commit. Có thể retry với key mới không?

**Đáp án:** Không nên. Cần đối soát theo idempotency key và tránh thực thi logical command hai lần.

**Câu 8.** JDBC ném `DataIntegrityViolationException` do duplicate PK ngay trong callback. Có phải lỗi ở commit không?

**Đáp án:** Không, trong lịch này nó phát sinh ở body; template yêu cầu rollback. Một công nghệ flush muộn có thể phát hiện lỗi tương tự ở commit.

## 14. Checklist và kết luận

- [ ] Phân loại rõ domain error, lỗi SQL/body, lỗi begin, commit và rollback.
- [ ] Callback success không bị nhầm là commit success.
- [ ] Business Outcome sau ghi một phần có `setRollbackOnly()` nếu cần hủy.
- [ ] Lỗi rollback không làm mất lỗi nghiệp vụ ban đầu.
- [ ] `PlatformTransactionManager.commit(status)` được đặt ngoài catch chỉ dành cho body.
- [ ] **Không gọi rollback cùng status sau commit exception**.
- [ ] Không tái sử dụng completed `TransactionStatus`.
- [ ] Đã hiểu propagation và physical transaction owner.
- [ ] Không coi mọi runtime exception là business error.
- [ ] Khi commit outcome không rõ: có idempotency và reconciliation.
- [ ] Có unit tests bằng fake và integration tests bằng DB thật.
- [ ] Log có phase, correlation ID và error chain, không lộ dữ liệu nhạy cảm.

**Kết luận:** lỗi nghiệp vụ giải thích *quy tắc domain nào thất bại*, còn lỗi commit/rollback giải thích *hạ tầng transaction có hoàn tất hoặc hoàn tác được không*. Hai loại lỗi có thể xuất hiện trong cùng một lần xử lý. `TransactionTemplate` xử lý boilerplate nhưng vẫn có thể ném exception sau callback; `PlatformTransactionManager` cho phép kiểm soát trực tiếp nhưng đòi hỏi phân chia try/catch đúng.

Điểm cần nhớ nhất: **khi `commit(status)` ném exception, không rollback lại status đó**. Nếu commit outcome chưa xác nhận, không khẳng định DB đã rollback; hãy đối soát và retry an toàn.

### Tài liệu chính thức

- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring API — PlatformTransactionManager: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html
- Spring API — TransactionTemplate: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring API — TransactionSystemException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionSystemException.html
- Spring API — UnexpectedRollbackException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/UnexpectedRollbackException.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring source — TransactionTemplate.java: https://github.com/spring-projects/spring-framework/blob/main/spring-tx/src/main/java/org/springframework/transaction/support/TransactionTemplate.java
