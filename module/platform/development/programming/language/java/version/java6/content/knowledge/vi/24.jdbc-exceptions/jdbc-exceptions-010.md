# Ngoại lệ JDBC: Bảo toàn nguyên nhân lỗi khi chuyển sang ngoại lệ của ứng dụng

## Mục tiêu học tập

Trong JDBC, khi **Connection**, **PreparedStatement** hay **ResultSet** gặp lỗi, driver thường báo một **java.sql.SQLException** hoặc subclass của nó. Tuy nhiên, tầng service/domain/controller của ứng dụng thường không muốn công khai API JDBC, SQL text, error message nội bộ hoặc mã lỗi vendor. Tình huống đó cần **exception translation**: chuyển ngoại lệ tầng lưu trữ thành một **ngoại lệ của ứng dụng** có ý nghĩa nghiệp vụ mà **vẫn giữ được nguyên nhân gốc**.

Ví dụ:

~~~text
JDBC driver / Database
        │
        ▼
SQLIntegrityConstraintViolationException
  SQLState=23505, vendorCode=7301
  cause=IOException
  nextException=SQLException(...)
  suppressed=SQLException từ close()
        │
        │  catch (SQLException original)
        ▼
OrderStorageException("ORDER_STORE_FAILED", original)
        │
        ├── Public code/message: ổn định, không chứa SQL/PII
        └── getCause(): chính original SQLException
              ├── getSQLState()/getErrorCode()
              ├── getNextException()
              ├── getCause()
              └── getSuppressed()
~~~

**Nguyên tắc cốt lõi:** Khi wrap, **đưa nguyên ngoại lệ gốc vào constructor nhận Throwable**. Không chỉ copy thông báo lỗi. Với Java, cách chuẩn là **super(message, cause)** trong custom exception. Cách này giữ được liên kết nguyên nhân để debugging, tracing và xử lý có kiểm soát ở tầng phù hợp, trong khi message của ngoại lệ mới có thể được thiết kế an toàn, có cấu trúc và không ràng buộc vào database vendor.

Bài này giúp bạn:

1. Hiểu **Throwable.getCause**, **SQLException.getSQLState/getErrorCode**, **SQLException.getNextException**, **Throwable.getSuppressed** và cách chúng liên hệ với nhau.
2. Viết **custom checked/unchecked application exception** có constructor nhận **cause**, dùng **super(message, cause)**.
3. Phân biệt **cause chain**, **JDBC next-exception chain** và **suppressed exceptions**; khi wrap, biết phải truy cập dữ liệu ở cấp nào.
4. Phân biệt **public error message/code** với **diagnostics riêng tư** để tránh rò SQL text, account, access token và thông tin cá nhân.
5. Chỉ wrap ở **ranh giới abstraction** phù hợp, tránh wrap lặp nhiều tầng hoặc log trùng.
6. Hiểu **try-with-resources** bảo toàn lỗi chính và ghi nhận lỗi cleanup dưới dạng suppressed exception.
7. Xử lý **SQLException subclasses**, SQLState/vendor code và retry policy mà không đánh mất lỗi gốc hoặc blind retry thao tác ghi.
8. Biên dịch và chạy chương trình **Java 17+ độc lập** dùng JDBC test double, tạo lỗi có cause/next/suppressed, wrap sang StorageFailure rồi kiểm chứng toàn bộ thông tin.
9. Thiết kế **unit/integration tests** cho error translation từ JDBC driver thật.
10. Nhận biết các anti-pattern: **throw new AppException(e.getMessage())**, **throw new RuntimeException()** không cause, catch rồi chỉ in stacktrace, tự thay stacktrace, hoặc biến mọi SQLException thành một error code gây mất ý nghĩa.

**Phạm vi:** API này còn nguyên giá trị trong Java 17+ và Java SE 26; ví dụ đã được biên dịch bằng **javac --release 17** và kiểm thử trên **OpenJDK 24.0.2**. Không dựa vào một cơ chế exception legacy đã lỗi thời.

## 1. Tại sao phải dịch SQLException?

Trong một kiến trúc nhiều lớp:

~~~text
HTTP / gRPC / UI
       │
       ▼
  Application Service
       │
       ▼
  Repository / DAO
       │
       ▼
    JDBC Driver
       │
       ▼
      DBMS
~~~

Repository biết **Connection**, **PreparedStatement**, **ResultSet**, SQLState và vendor error codes. Service lại quan tâm **không lưu được đơn hàng**, **dữ liệu bị xung đột**, **hệ thống lưu trữ tạm thời không sẵn sàng**. Controller quan tâm **mã lỗi công khai**, HTTP status và thông báo an toàn cho client.

Nếu để SQLException tràn qua mọi tầng, nhiều interface nghiệp vụ bị ràng buộc vào JDBC, API client dễ lộ chi tiết SQL hoặc error vendor, và code nghiệp vụ phải tự xử lý những lỗi tầng persistence không thuộc trách nhiệm của nó.

Nếu chỉ đổi sang **new RuntimeException("Lưu thất bại")** mà không lưu cause, debugger mất stack trace SQL gốc, SQLState, vendor error code, các exceptions được driver nối qua **getNextException** và các lỗi close bị suppressed.

**Mục tiêu của exception translation không phải xóa dấu vết JDBC**, mà là **tách public abstraction khỏi private diagnostics**.

### 1.1. Hai mặt của cùng một lỗi

| Mặt | Dành cho | Nên chứa |
| --- | --- | --- |
| **Application error** | Service/controller, API contract | Mã lỗi ổn định, mô tả không lộ dữ liệu, operation context đã kiểm soát |
| **Underlying SQLException** | Logging bảo mật, telemetry, đội vận hành | SQLState, vendorCode, subclass, cause, nextException, suppressed |
| **API response** | Client không đáng tin | Public error code, message an toàn, correlation ID phù hợp |
| **Internal trace** | Người có quyền debug | Cause chain/stacktrace đã được phân loại bảo mật, có giới hạn và redaction |

**Không copy trực tiếp SQLException.getMessage() vào public error message.** Một database driver có thể đưa vào message các giá trị khóa, tên bảng/cột, SQL fragment, dữ liệu người dùng hoặc connection string.

### 1.2. Khi nào không cần wrap?

Không phải mọi nơi đều cần tạo custom exception:

- Nếu method đã là một **JDBC-level helper** công khai **throws SQLException**, nó có thể để nguyên ngoại lệ cho caller có responsibility phù hợp.
- Nếu một tầng thật sự có thể xử lý lỗi và tiếp tục an toàn, nó có thể xử lý tại chỗ thay vì wrap.
- Nếu cùng một abstraction đã có exception giàu ngữ nghĩa và cause đầy đủ, **không wrap thêm một lớp y hệt chỉ để thay câu chữ**.
- Nếu code ở tầng service đã nhận **OrderStorageException**, không cần tiếp tục wrap bằng “ServiceFailure” chỉ để che lại.
- Không catch **Error**, **InterruptedException** hoặc các loại runtime exception không liên quan rồi chuyển toàn bộ sang “database lỗi”; điều đó sẽ che bug và làm sai cancellation semantics.

Wrap nên diễn ra tại **ranh giới abstraction**, ví dụ **DAO/Repository JDBC → Application persistence error**, nơi việc thay đổi public contract thực sự có giá trị.

## 2. Các loại chuỗi ngoại lệ trong Java/JDBC

### 2.1. Throwable.getCause(): liên kết nguyên nhân

Một **Throwable** có thể giữ một **cause** là một Throwable khác khiến nó được tạo. Ví dụ:

~~~text
OrderStorageException
      │ getCause()
      ▼
SQLIntegrityConstraintViolationException
      │ getCause()
      ▼
IOException
~~~

Đây là **cause chain**. Trong stack trace in bằng printStackTrace, Java thường thể hiện dạng **Caused by:**. Cấu trúc cho phép bạn giữ ngữ cảnh tầng trên nhưng vẫn truy ra nguyên nhân ở tầng dưới.

**Cause không phải message.** Khi tạo ngoại lệ:

~~~java
throw new OrderStorageException("ORDER_STORE_FAILED", original);
~~~

constructor custom cần gọi **super(message, original)** hoặc tương đương, không phải lấy **original.toString()** gắn vào message rồi bỏ reference đến original.

### 2.2. SQLException.getNextException(): chuỗi lỗi JDBC

SQLException có method:

~~~java
SQLException next = sqlException.getNextException();
~~~

Đó là một **chuỗi SQLException bổ sung** do driver hoặc ứng dụng set bằng **setNextException(SQLException)**. Nó **khác với cause chain**. Một SQLException có thể có đồng thời:

~~~text
SQLException (primary)
    │
    ├── getCause() ────────────> IOException
    │
    ├── getNextException() ────> SQLException (additional diagnostic)
    │                             └── getNextException() → ...
    │
    └── getSuppressed() ───────> SQLException (resource close failure)
~~~

Nếu bạn bọc **chính đối tượng SQLException primary** bằng constructor cause, các liên kết con trên vẫn ở đó. Nếu chỉ bọc message string thì chúng bị mất khỏi chuỗi có thể truy cập.

**SQLException implements Iterable<Throwable>**: vòng for-each trên SQLException có thể duyệt chained SQLExceptions và causes theo thứ tự do API định nghĩa. Tuy vậy, khi cần tách rõ primary SQLState và next exceptions, thường đọc bằng các method tường minh dễ audit và giới hạn hơn.

### 2.3. Throwable.getSuppressed(): các lỗi đi kèm

**Suppressed exception** là một nhánh khác với cause. Một trường hợp điển hình:

1. **PreparedStatement.executeUpdate()** ném SQLException chính.
2. Trong khi unwinding, **PreparedStatement.close()** cũng ném SQLException.
3. **try-with-resources** giữ SQLException từ executeUpdate làm **primary exception**.
4. SQLException từ close được thêm vào **primary.getSuppressed()**.

Nếu sau đó repository chuyển primary thành application exception bằng cause, **suppressed sẽ nằm trên SQLException gốc**:

~~~java
// Giả sử appError là application exception đã bọc original SQLException.
SQLException original = (SQLException) appError.getCause();
Throwable[] closeFailures = original.getSuppressed();
~~~

**Không mặc định** appError.getSuppressed() chứa cùng những lỗi cleanup. Wrapper mới và nguyên nhân gốc là **hai Throwable riêng**, mỗi object có suppressed list riêng. Muốn tìm cleanup failures, xem **original.getSuppressed()**.

### 2.4. Bảng phân biệt nhanh

| API | Phản ánh | Có được giữ khi wrap bằng cause? |
| --- | --- | --- |
| **Throwable.getCause()** | Nguyên nhân của Throwable | Có, wrapper.getCause() trỏ tới original |
| **SQLException.getSQLState()** | Mã SQLState của SQLException | Có, truy cập trên original |
| **SQLException.getErrorCode()** | Mã vendor của SQLException | Có, truy cập trên original |
| **SQLException.getNextException()** | Chained SQLException | Có, do original object vẫn được giữ |
| **Throwable.getSuppressed()** | Lỗi bị suppressed trên chính Throwable | Có, trên original; không tự chuyển sang wrapper |
| **Throwable.getStackTrace()** | Stack frames tại thời điểm lỗi | Giữ trên original, wrapper có stack trace riêng |
| **Throwable.getMessage()** | Detail message | Giữ message original; wrapper có public message riêng |

## 3. Cách chuẩn để viết custom application exception

### 3.1. Chọn checked hay unchecked

Một application exception có thể:

- **extends RuntimeException**: không cần khai báo **throws** trong method signature; phù hợp với những framework/application layers có cơ chế tập trung xử lý persistence failure.
- **extends Exception**: checked exception, buộc caller bắt hoặc khai báo; có thể phù hợp nếu lỗi là một phần business contract được xử lý trực tiếp.

**Không có quy định Java bắt buộc mọi persistence error phải unchecked.** Chọn theo kiến trúc, API contracts và cách application muốn người gọi xử lý. Hai cách đều có thể bảo toàn cause bằng constructor **super(message, cause)**.

### 3.2. Unchecked exception với stable code

~~~java
// Mảnh minh họa; Java 17+.
public final class OrderStorageException extends RuntimeException {
    private final String errorCode;

    public OrderStorageException(
            String errorCode, String safeMessage, SQLException cause) {
        super(safeMessage, java.util.Objects.requireNonNull(cause));
        this.errorCode = java.util.Objects.requireNonNull(errorCode);
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

**safeMessage** là thông điệp do ứng dụng định nghĩa, không được tạo bằng cách nối vào **cause.getMessage()**. **errorCode** là mã công khai do ứng dụng kiểm soát, không nhất thiết trùng SQLState/vendor code.

Không phải mọi ứng dụng đều cần expose getter cho underlying SQLException ở public API. **getCause()** đã có sẵn; application có thể chỉ dùng nó trong logging/monitoring ở phía server.

### 3.3. Checked variant

~~~java
// Mảnh minh họa cho API dùng checked exceptions.
public final class StorageOperationException extends Exception {
    public StorageOperationException(String safeMessage, SQLException cause) {
        super(safeMessage, java.util.Objects.requireNonNull(cause));
    }
}
~~~

Nếu API chọn checked, caller có thể **throws StorageOperationException** và bắt theo logic nghiệp vụ. Nguyên nhân JDBC vẫn được giữ giống unchecked variant.

### 3.4. Cách wrap tại repository boundary

~~~java
// Mảnh code với Connection connection, long orderId và dữ liệu đã validate.
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO orders(id, status) VALUES (?, ?)")) {
    ps.setLong(1, orderId);
    ps.setString(2, "NEW");
    ps.executeUpdate();
} catch (SQLException original) {
    throw new OrderStorageException(
            "ORDER_STORE_FAILED",
            "Unable to save order",
            original);
}
~~~

**Đây là mảnh minh họa, không phải một file chạy độc lập**. Connection và schema phải có thật. Repository sở hữu Statement nên dùng try-with-resources; còn Connection có thể do transaction manager/caller sở hữu, vì vậy không tự close Connection nếu scope này không có ownership.

Nếu Statement.close cũng fail trong khi executeUpdate lỗi, **try-with-resources đã gắn close failure vào original.getSuppressed() trước khi catch chạy**. Constructor cause giữ original object cùng các suppressed exceptions bên trong.

## 4. Anti-pattern làm mất nguyên nhân hoặc gây rò dữ liệu

### 4.1. Chỉ copy message, mất cause

~~~java
// SAI: mất SQLState, vendorCode, cause, next exceptions và suppressed.
catch (SQLException e) {
    throw new RuntimeException(e.getMessage());
}
~~~

Wrapper mới có **getCause() == null**. Một log của wrapper có thể không cho thấy stacktrace gốc. Thêm nữa, thông báo của driver có thể chứa email, tên bảng, dữ liệu input hoặc SQL text.

### 4.2. Tạo ngoại lệ không cause

~~~java
// SAI: không bảo toàn liên kết nguyên nhân.
catch (SQLException e) {
    throw new IllegalStateException("Database operation failed");
}
~~~

Dù message an toàn hơn ví dụ trước, nguyên nhân gốc bị cắt đứt và việc debug khó hơn nhiều.

### 4.3. Throw cùng một lỗi dưới dạng message string

~~~java
// SAI: giữ chữ nhưng không giữ object.
catch (SQLException e) {
    throw new RuntimeException("SQL problem: " + e);
}
~~~

**e.toString()** chỉ là một String. Nó không thay thế **Throwable cause**; đồng thời có thể đưa vendor/private details vào message công khai.

### 4.4. Chỉ ghi log rồi nuốt lỗi

~~~java
// SAI: caller nghĩ thao tác đã thành công.
catch (SQLException e) {
    e.printStackTrace();
}
~~~

Nếu thao tác là INSERT order, trả về bình thường sau khi lỗi có thể khiến tầng trên gửi confirmation sai, mất event hoặc trả HTTP 200 không đúng. **Không tự nuốt lỗi** trừ khi nghiệp vụ thật sự có fallback an toàn được thiết kế.

### 4.5. Log đầy đủ ở mọi tầng

Một lỗi được log từ repository, service, controller, rồi lại từ global exception handler có thể xuất hiện bốn lần với stack trace chứa dữ liệu nhạy cảm. Nguyên tắc hợp lý là **translate at boundary, log once at the right observability boundary**, giữ cause trong object và dùng redaction phù hợp.

Không in full SQLException message hoặc printStackTrace trực tiếp ra HTTP response, public logs, browser console hoặc một channel ít bảo mật.

### 4.6. Bắt Throwable quá rộng

~~~java
// SAI: che bug hoặc lỗi nghiêm trọng.
try {
    performJdbcWork();
} catch (Throwable t) {
    throw new RuntimeException("Database failed", t);
}
~~~

**Throwable** bao gồm Error. Không nên chuyển các lỗi như OutOfMemoryError thành business persistence error. Bắt **SQLException** tại ranh giới JDBC hoặc bắt những loại được API quy định.

## 5. Constructor cause và initCause

### 5.1. Ưu tiên super(message, cause)

**Throwable(String message, Throwable cause)** là constructor chính thức để ghi nhận cause ngay khi tạo đối tượng. Custom exception nên cung cấp overload phù hợp:

~~~java
public final class RepositoryException extends RuntimeException {
    public RepositoryException(String message, SQLException cause) {
        super(message, cause);
    }
}
~~~

Cách này ngắn, rõ ràng và tránh phải tạo exception rồi mutate state.

### 5.2. initCause chỉ là giải pháp dự phòng

**Throwable.initCause(Throwable)** vẫn được hỗ trợ. Nó hữu ích với một kiểu ngoại lệ không có constructor nhận cause, nhưng **chỉ được gọi tối đa một lần** và không được gọi sau khi một constructor đã gán cause (kể cả gán null). Nếu gọi hai lần, có thể nhận **IllegalStateException**. Nó cũng không cho phép throwable trở thành cause của chính mình.

~~~java
IllegalStateException ex = new IllegalStateException("Old API message");
ex.initCause(sqlFailure);
throw ex;
~~~

**Mảnh code có sqlFailure là Throwable đã có**. Với custom exception mới, hãy **thiết kế constructor nhận cause** thay vì dựa vào initCause.

### 5.3. Không làm giả original stack trace

Đừng tự gọi **setStackTrace()** bằng một stack trace được copy, đừng replace cause bằng một exception chỉ có String message và cũng đừng tạo wrapper bằng cách clone stack trace rồi bỏ nguyên nhân. **Stacktrace của wrapper** cho thấy nơi chuyển lỗi; **stacktrace của cause** cho thấy nơi JDBC lỗi ban đầu. Hai thông tin bổ sung cho nhau.

## 6. Ví dụ Java 17+ hoàn chỉnh: bọc SQLException mà không mất dấu vết

Chương trình **JdbcCausePreservationDemo.java** bên dưới dùng một **JDBC test double** bằng **java.lang.reflect.Proxy**. Nó chủ động giả lập:

1. Một **SQLIntegrityConstraintViolationException** với **SQLState=23505**, **vendorCode=7301** và một **IOException** làm root cause.
2. Một SQLException bổ sung từ **setNextException** với SQLState=01000.
3. **PreparedStatement.executeUpdate()** ném exception chính.
4. **PreparedStatement.close()** cũng ném SQLException (state HY000), được **try-with-resources tự động suppressed vào exception chính**.
5. Repository bắt SQLException và chuyển thành **StorageFailure extends RuntimeException**, dùng **super(safeMessage, original)**.
6. Client nhìn thấy publicCode/publicMessage an toàn; phía service/debug vẫn lấy **đúng original Throwable reference** qua getCause.
7. Một SQLTransactionRollbackException khác được wrap để chứng minh subclass và SQLState vẫn còn.
8. Một wrapper sai không cause làm mất liên kết.
9. **initCause** vẫn có thể giữ cause khi class cũ không có constructor phù hợp.

**Lưu ý:** Đây là test double **không kết nối DB, không chạy SQL thật, không có transaction thật**. Các SQLState/vendor codes là giá trị test tự tạo, không phải kết quả từ một database product. Mục tiêu là kiểm chứng chính xác **Java/JDBC exception semantics**, không mô phỏng toàn bộ driver.

### 6.1. File JdbcCausePreservationDemo.java

~~~java
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLIntegrityConstraintViolationException;
import java.sql.SQLTransactionRollbackException;
import java.util.Objects;

public final class JdbcCausePreservationDemo {

    static final class StorageFailure extends RuntimeException {
        private final String publicCode;

        StorageFailure(String publicCode, SQLException cause) {
            super("Unable to save order", Objects.requireNonNull(cause));
            this.publicCode = Objects.requireNonNull(publicCode);
        }

        String publicCode() {
            return publicCode;
        }
    }

    static final class SimulatedDriver {
        final SQLException primary = new SQLIntegrityConstraintViolationException(
                "Duplicate key for secret@example.invalid",
                "23505", 7301, new IOException("synthetic I/O failure"));

        SimulatedDriver() {
            primary.setNextException(
                    new SQLException("Additional vendor diagnostic", "01000", 91));
        }

        PreparedStatement prepare() {
            return (PreparedStatement) Proxy.newProxyInstance(
                JdbcCausePreservationDemo.class.getClassLoader(),
                new Class<?>[] {PreparedStatement.class},
                (proxy, method, args) -> {
                    switch (method.getName()) {
                        case "setLong": return null;
                        case "executeUpdate": throw primary;
                        case "close":
                            throw new SQLException(
                                    "Cleanup failed", "HY000", 99);
                        default:
                            throw new SQLFeatureNotSupportedException(
                                    "Fake method not implemented: " + method.getName());
                    }
                });
        }
    }

    static void saveOrder(SimulatedDriver driver) {
        try (PreparedStatement ps = driver.prepare()) {
            ps.setLong(1, 7L);
            ps.executeUpdate();
        } catch (SQLException original) {
            throw new StorageFailure("ORDER_STORE_FAILED", original);
        }
    }

    public static void main(String[] args) {
        SimulatedDriver driver = new SimulatedDriver();
        try {
            saveOrder(driver);
        } catch (StorageFailure applicationError) {
            SQLException original = (SQLException) applicationError.getCause();
            System.out.println("appCode=" + applicationError.publicCode());
            System.out.println("publicMessage=" + applicationError.getMessage());
            System.out.println("sameCause=" + (original == driver.primary));
            System.out.println("causeType="
                    + original.getClass().getSimpleName());
            System.out.println("sqlState=" + original.getSQLState());
            System.out.println("vendorCode=" + original.getErrorCode());
            System.out.println("rootCause="
                    + original.getCause().getClass().getSimpleName());
            System.out.println("nextState="
                    + original.getNextException().getSQLState());
            System.out.println("suppressedCount="
                    + original.getSuppressed().length);
            System.out.println("suppressedState="
                    + ((SQLException) original.getSuppressed()[0]).getSQLState());
            System.out.println("publicMessageLeaksSecret="
                    + applicationError.getMessage().contains("secret@"));
            System.out.println("wrapperSuppressedCount="
                    + applicationError.getSuppressed().length);
        }

        SQLException retryable = new SQLTransactionRollbackException(
                "Serialization conflict", "40001", 1205);
        StorageFailure wrappedRetryable =
                new StorageFailure("ORDER_STORE_FAILED", retryable);
        System.out.println("transientCauseType="
                + wrappedRetryable.getCause().getClass().getSimpleName());
        System.out.println("transientState="
                + ((SQLException) wrappedRetryable.getCause()).getSQLState());

        RuntimeException lost = new RuntimeException("Operation failed");
        System.out.println("badWrapperCause=" + lost.getCause());

        IllegalStateException legacy = new IllegalStateException(
                "Legacy-style message");
        legacy.initCause(retryable);
        System.out.println("initCauseRetainsOriginal="
                + (legacy.getCause() == retryable));
    }
}
~~~

### 6.2. Biên dịch và chạy

Lưu file với đúng tên **JdbcCausePreservationDemo.java**, dùng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 --release 17 JdbcCausePreservationDemo.java
java JdbcCausePreservationDemo
~~~

Các lệnh này chạy được trong Windows PowerShell và shell Unix-like. **Không cần DBMS, JDBC URL, username/password, Maven, Gradle hay JDBC driver JAR**. Fake PreparedStatement chỉ hỗ trợ những methods mà ví dụ gọi, còn các method khác chủ động báo SQLFeatureNotSupportedException.

### 6.3. Stdout chính xác đã kiểm chứng

~~~text
appCode=ORDER_STORE_FAILED
publicMessage=Unable to save order
sameCause=true
causeType=SQLIntegrityConstraintViolationException
sqlState=23505
vendorCode=7301
rootCause=IOException
nextState=01000
suppressedCount=1
suppressedState=HY000
publicMessageLeaksSecret=false
wrapperSuppressedCount=0
transientCauseType=SQLTransactionRollbackException
transientState=40001
badWrapperCause=null
initCauseRetainsOriginal=true
~~~

**Đã compile và chạy thành công trên OpenJDK 24.0.2 với --release 17, so khớp toàn bộ 16 dòng stdout.** Chương trình dùng giá trị giả lập nên kết quả deterministic; **không phải tuyên bố driver thực sẽ trả cùng SQLState/vendorCode**.

### 6.4. Giải thích từng nhóm kết quả

**Application exception hợp lệ:**

- **appCode=ORDER_STORE_FAILED**: mã lỗi công khai do ứng dụng sở hữu.
- **publicMessage=Unable to save order**: thông báo ổn định, không đưa thông điệp của driver vào public contract.
- **sameCause=true**: wrapper trỏ tới **đúng cùng đối tượng SQLException**, không phải một object được tạo lại chỉ chứa message.
- **causeType=SQLIntegrityConstraintViolationException**: subtype JDBC gốc không mất.
- **sqlState=23505**, **vendorCode=7301**: các trường của SQLException gốc còn truy cập được.
- **rootCause=IOException**: nguyên nhân Throwable bên dưới vẫn nằm trong cause chain.

**JDBC next-exception chain:**

- **nextState=01000**: original SQLException có một next exception; việc wrap không làm mất nó.
- **getNextException() khác getCause()**. Chương trình cố ý kiểm tra cả hai.

**Suppressed cleanup error:**

- **suppressedCount=1**, **suppressedState=HY000**: trong khi executeUpdate ném primary SQLException, close cũng ném; try-with-resources thêm close failure vào original.getSuppressed().
- **wrapperSuppressedCount=0**: suppressed không tự dời lên StorageFailure. Phải đi xuống original cause để đọc.
- Vì vậy test này chứng minh cả primary failure và secondary cleanup failure đều được bảo toàn.

**Bảo mật thông điệp:**

- **publicMessageLeaksSecret=false**: thông điệp ở wrapper không chứa chuỗi nhạy cảm giả lập nằm trong underlying SQLException.
- **Điều này không có nghĩa toàn bộ exception đã được redacted**: nếu gọi printStackTrace() trên wrapper, Java sẽ hiển thị cause, bao gồm message của JDBC gốc. Đừng đưa stack trace hoặc cause object nguyên trạng vào API client/public logs.

**Classification và anti-pattern:**

- **transientCauseType=SQLTransactionRollbackException**, **transientState=40001**: khi wrapper giữ cause, lớp lỗi JDBC và SQLState vẫn có thể được xem xét ở tầng xử lý có quyền.
- **badWrapperCause=null**: tạo RuntimeException chỉ có message sẽ không giữ original.
- **initCauseRetainsOriginal=true**: initCause còn dùng được, nhưng nên ưu tiên constructor nhận cause đối với custom exception mới.

## 7. Giữ nguyên cause chưa đủ: giữ đúng chính sách phân loại

Khi chuyển SQLException thành application exception, bạn có thể vẫn cần phân loại:

- **SQLTransientException**: có thể đáng retry nếu thao tác repeatable và còn budget/deadline.
- **SQLNonTransientException**: nên sửa nguyên nhân thay vì blind retry.
- **SQLRecoverableException**: application-level recovery, tối thiểu đóng Connection cũ và mở Connection mới; có thể cần replay toàn transaction khi **an toàn**.
- **SQLIntegrityConstraintViolationException**: có thể liên quan unique/FK/check constraints; ứng dụng chỉ trả mã “đã tồn tại” nếu xác định đúng business semantics, không chỉ dựa vào tên class.
- **SQLTransactionRollbackException**: có thể là rollback do deadlock/serialization, cần replay toàn transaction thay vì statement cuối.

Việc wrap **không làm SQLRecoverableException trở thành RuntimeException có thể retry vô điều kiện**. Nếu mất response của COMMIT, outcome có thể chưa rõ, và retry trực tiếp một lệnh UPDATE/payment có thể thực thi tác động hai lần.

### 7.1. Có thể phân loại trước khi wrap

~~~java
// Mảnh minh họa trong catch (SQLException original).
boolean mayBeTransient = original instanceof SQLTransientException;
boolean requiresConnectionRecovery =
        original instanceof SQLRecoverableException;

throw new OrderStorageException(
        "ORDER_STORE_FAILED",
        "Unable to save order",
        original);
~~~

Tầng repository có thể lưu **classification metadata** trong exception/domain result nếu contract của ứng dụng cần, nhưng **không nên tạo public retry flag** chỉ từ Java subtype mà không xét idempotency. Mã nên có một nơi quyết định policy thay vì logic retry rải rác giữa DAO/service/controller.

### 7.2. Hoặc phân loại sau khi wrap

~~~java
// Mảnh minh họa, applicationError đã là OrderStorageException.
Throwable cause = applicationError.getCause();
if (cause instanceof SQLRecoverableException recoverable) {
    // Recovery theo transaction owner và business-safety contract.
}
~~~

Dạng pattern matching **instanceof** được Java 17 hỗ trợ. Không bắt đầu replay chỉ bởi phát hiện cause là recoverable. Đầu tiên cần xác định transaction có thể đã commit và liệu operation đã có idempotency protection.

### 7.3. Tránh lặp lại sai ranh giới transaction

Một application exception “Storage failed” có thể được ném sau:

~~~text
BEGIN
  INSERT order
  UPDATE inventory
  INSERT outbox event
COMMIT
~~~

Nếu một lỗi khiến transaction chắc chắn rollback, retry có thể phải chạy lại **toàn bộ workflow**. Nếu response của COMMIT mất, kết quả không rõ; phải **reconcile theo operation ID** trước khi replay. Repository-level catch không được tự ý quyết định toàn bộ điều đó nếu nó không sở hữu transaction.

**Giữ cause** là điều kiện cần cho debugging, nhưng **giữ đúng transaction/commit semantics** là điều kiện cần cho tính đúng đắn của hệ thống.

## 8. Exception translation và public API response

Một cách phân tầng hợp lý:

1. Repository bắt **SQLException original** và tạo **OrderStorageException(safeMessage, original)**.
2. Application service quyết định business action: retry nếu đã chứng minh safe-to-repeat, hoặc trả lỗi.
3. Global error handler ánh xạ **application error code** thành HTTP/gRPC response an toàn.
4. Server observability lưu error classification và correlation ID, chỉ ghi chi tiết driver/cause trong kênh đã được cấp quyền và có redaction phù hợp.

Ví dụ **response công khai**:

~~~json
{
  "code": "ORDER_STORE_FAILED",
  "message": "Unable to save order",
  "requestId": "req-example-123"
}
~~~

**Đây là JSON minh họa**, không có SQLState/vendorCode, SQL text, email hay database endpoint. ID là giá trị giả, không phải dữ liệu thật.

Những thông tin **không nên trả trực tiếp** qua API public:

- SQL statement có parameter values hoặc chứa user input.
- SQLException.getMessage() chưa qua kiểm soát.
- Database account, JDBC URL, hostname nội bộ hoặc credentials.
- Full stack trace, next exception chain và suppressed diagnostics.
- Giá trị unique key chứa email/định danh cá nhân.
- Internal vendor code nếu nó trở thành fingerprint của database hạ tầng.

### 8.1. Không làm mất diagnostics chỉ để tránh lộ dữ liệu

Giải pháp đúng không phải xóa cause mà là **kiểm soát nơi cause được serialize/log**. Trong nội bộ, team vận hành có thể cần SQLState, vendor code, driver version, sanitized operation name, connection context và error correlation ID.

Nếu organization có chính sách log bảo mật nghiêm ngặt, có thể thu thập những trường **đã sanitize** thay vì in full stack trace. Việc giữ cause trong memory **không bắt buộc** public logger phải render nó.

### 8.2. Tránh serializing exception object

Không gửi trực tiếp một RuntimeException/Throwable sang JSON serializer rồi trông chờ các nested causes luôn an toàn. Throwable có nhiều fields và nested relationships. Hãy tạo một **response DTO** riêng chỉ có những field đã được phê duyệt.

### 8.3. Khi nào dùng HTTP 409 hay 500?

Một **SQLIntegrityConstraintViolationException** không tự chứng minh trường hợp phải trả **409 Conflict**. Nó có thể là internal foreign-key bug hoặc một constraint liên quan tới hạ tầng. Chỉ khi business contract xác định rõ đây là “resource already exists” hoặc conflict do client có thể giải quyết, service mới ánh xạ sang 409. Trường hợp khác có thể là server error với public code an toàn.

Tương tự, không trả 503 chỉ vì bất kỳ SQLException nào được wrap thành persistence exception; phải xác định thực sự là service unavailable và có retry guidance phù hợp.

## 9. Khi nhiều nơi cùng throw, giữ cause một cách có chủ đích

### 9.1. Wrap tại nơi đổi abstraction

~~~text
JDBC SQLException
      │
      ▼
Repository dịch sang OrderStorageException + original cause
      │
      ▼
Service sử dụng đúng OrderStorageException
      │
      ▼
Controller/API tạo safe response
~~~

Nếu service chỉ catch OrderStorageException rồi throw new ServiceException("Failure", e) mà không thêm ý nghĩa/domain context, hệ thống xuất hiện nhiều tầng wrapper gây noise trong log và khó truy tìm lỗi quan trọng.

Nếu thật sự đổi abstraction nữa (ví dụ storage failure làm hỏng một business transaction có mã lỗi riêng), vẫn có thể wrap và giữ cause, nhưng nên có **lý do rõ** và một public error contract ổn định.

### 9.2. Không “replace” SQLException bằng SQLException mới không cause

~~~java
// SAI: tạo một SQLException khác chỉ dựa vào message.
catch (SQLException e) {
    throw new SQLException("Persistence failed", e.getSQLState());
}
~~~

Lỗi này trông có SQLState nhưng **không giữ object gốc**, có thể mất vendor code, original subclass, nested cause, next chain và suppressed cleanup errors.

Nếu vì contract bạn thực sự cần SQLException mới, **SQLException có constructors nhận cause**, ví dụ:

~~~java
// Mảnh minh họa khi API cần tiếp tục throws SQLException.
catch (SQLException original) {
    throw new SQLException(
            "Persistence failed", original.getSQLState(),
            original.getErrorCode(), original);
}
~~~

Tuy vậy, khi “chuyển sang ngoại lệ ứng dụng”, class mới nên phản ánh **application abstraction** thay vì chỉ nhân bản một SQLException khác.

### 9.3. Đừng chỉ copy getStackTrace

~~~java
// SAI: stacktrace copy không phải causal link.
RuntimeException copy = new RuntimeException("Failed");
copy.setStackTrace(original.getStackTrace());
throw copy;
~~~

Cách này làm mất runtime type SQL gốc và những method quan trọng. Giữ original cause mới đúng.

## 10. Error context: thêm đúng thông tin, tránh nhầm nguồn lỗi

Một application exception có thể thêm:

- **Operation code**: ORDER_STORE_FAILED, ORDER_LOOKUP_FAILED.
- **Stable subsystem name**: storage, customer repository.
- **Correlation ID** nếu policy cho phép.
- **Retry classification** ở tầng nội bộ khi được định nghĩa rõ.
- **Context đã được sanitize**: không gồm raw SQL parameters, token, password, PII.

Không dùng **SQLException.getMessage()** làm context field mặc định. Message có thể mang dữ liệu riêng tư. Một Java exception với cause vẫn có thể được log ở kênh nội bộ theo policy, nhưng **public response** cần tách riêng.

### 10.1. Tránh nội suy raw SQL

Không nên:

~~~java
// Mã SAI: có thể rò câu SQL và dữ liệu trong log/API.
throw new RuntimeException(
        "SQL failed: " + sql + " params=" + params, original);
~~~

Dù cause được giữ, message của wrapper đã chứa dữ liệu có thể nhạy cảm. Thay bằng **mã operation** và các fields có kiểm soát.

### 10.2. SQLState/vendor code có đủ để debug không?

Không phải lúc nào cũng đủ: DBMS version, driver name/version, schema migration state, connection pool status, trace ID và exception chain có thể cần thiết. Tuy nhiên, không nên tự động log mọi thứ với mức DEBUG trên production nếu có rủi ro bảo mật/chi phí.

Một mẫu internal event tốt có thể có:

~~~text
operation=ORDER_STORE
publicCode=ORDER_STORE_FAILED
jdbcExceptionType=SQLIntegrityConstraintViolationException
sqlState=23505
vendorCode=7301
correlationId=req-example-123
causePresent=true
nextExceptionCount=1
suppressedCount=1
~~~

**Các giá trị này là dữ liệu test minh họa**, không phải log production thực tế. Không kèm SQL parameters hoặc email.

## 11. try-with-resources và bảo toàn lỗi cleanup

### 11.1. Vì sao finally dễ che lỗi nếu viết sai?

Nếu code tự đóng resource trong finally:

~~~java
// Mảnh code minh họa một pattern dễ gây che lỗi.
try {
    doJdbcWork();
} finally {
    statement.close(); // Nếu close throw, có thể che lỗi chính.
}
~~~

Nếu **doJdbcWork()** ném SQLException và **statement.close()** cũng ném SQLException, người gọi có thể chỉ thấy close failure nếu không quản lý cẩn thận.

### 11.2. try-with-resources giúp giữ lỗi chính

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.executeUpdate(); // Ném SQLException chính.
} catch (SQLException original) {
    // original.getSuppressed() có thể chứa SQLException từ ps.close().
    throw new OrderStorageException(
            "ORDER_STORE_FAILED", "Unable to save order", original);
}
~~~

**sql** và **connection** do caller cung cấp; đây là mảnh minh họa. Với try-with-resources, Java bảo toàn exception đầu tiên từ body làm primary và add suppressed cho lỗi close.

**Nếu body không lỗi và close lỗi**, close exception có thể trở thành primary. Vì vậy không mặc định mọi SQLException bắt được sau TWR đều do execute.

### 11.3. Custom cleanup với nhiều JDBC resources

Trong code không thể dùng TWR cho một resource cụ thể, cần:

- Giữ **primary Throwable**.
- Cố gắng cleanup mọi resource đã tạo.
- Nếu cleanup fail, **addSuppressed** vào primary khi phù hợp.
- Nếu không có primary, quyết định báo cleanup failure thành primary.
- Không suppress chính primary vào nó (Java cấm self-suppression).
- Không catch rồi bỏ qua mọi cleanup error mà không có policy vận hành.

**Throwable.addSuppressed** vẫn còn được hỗ trợ và được dùng bởi Java TWR; nó không phải một API legacy. Dùng nó khi thật sự có multiple sibling failures chứ không cố biến mọi error thành một chuỗi dài thiếu ý nghĩa.

### 11.4. Giữ suppressed đúng cấp sau wrapping

~~~java
// Mảnh minh họa sau khi đã có StorageFailure applicationError.
Throwable original = applicationError.getCause();
Throwable[] cleanup = original.getSuppressed();

// Không giả định applicationError.getSuppressed() giống cleanup.
~~~

Như ví dụ runnable, wrapperSuppressedCount=0 nhưng original suppressedCount=1. **Đây là kết quả đúng**, không phải lỗi của Java.

## 12. Chuyển SQL lỗi sang application exception trong transaction

### 12.1. Repository không phải transaction owner

Nếu transaction manager mở Connection và transaction, repository thường chỉ nên quản lý PreparedStatement/ResultSet; không tự commit/rollback hoặc close Connection nếu chưa được giao ownership.

Exception translation:

~~~text
Service transaction scope
      │
      ├── Repository.saveA() → JDBC
      ├── Repository.saveB() → JDBC
      ├── Repository.saveC() → JDBC error
      │                       └── DomainStorageException(cause=SQLException)
      │
      └── Transaction manager quyết định rollback/recovery
~~~

Nếu repository catch SQLException rồi gọi commit/rollback và “đổi lỗi thành success”, transaction manager có thể không biết state đúng. Giữ cause giúp coordinator/handler có context, nhưng **không tự thay thế ownership protocol**.

### 12.2. Không mất thông tin rollback/commit outcome

Với **SQLTransactionRollbackException**, application có thể cần replay toàn transaction nếu workflow repeatable. Với **SQLRecoverableException**, cần Connection mới. Với **COMMIT response mất**, kết quả có thể đã commit: không blind retry, phải đối chiếu theo idempotency key/status.

Khi wrap, nguyên class của SQLException vẫn nằm trong cause chain, nhưng handler phải **thận trọng với transaction outcome**. “Cause is transient” không đồng nghĩa “mutation repeatable”.

### 12.3. Transaction side effects ngoài JDBC

Trong một workflow vừa ghi DB vừa gửi email hoặc message, rollback DB không tự thu hồi email/message đã phát. Nếu retry toàn workflow không có idempotency/outbox, có thể gửi nhiều lần. Cause preservation hỗ trợ diagnostics; correctness cần một **business-level consistency strategy**.

## 13. Ngoại lệ khi thực hiện batch hoặc LOB

### 13.1. BatchUpdateException

**BatchUpdateException** giữ **update counts** cho các statements trong batch và có thể có next exceptions. Nếu chỉ copy message thành một AppException, bạn mất khả năng phân tích partial outcome. Bằng cách giữ original cause, tầng có quyền có thể xem:

~~~java
// Mảnh minh họa sau khi bắt application exception có cause JDBC.
Throwable cause = applicationError.getCause();
if (cause instanceof java.sql.BatchUpdateException batch) {
    int[] counts = batch.getUpdateCounts();
    // Diễn giải theo JDBC/driver/transaction contract.
}
~~~

Dù có counts, **không mặc định retry toàn batch**: có thể đã có partial success hoặc commit outcome không rõ.

### 13.2. SQLClientInfoException

**SQLClientInfoException** có **getFailedProperties()**, cho biết client information properties bị từ chối. Giữ nguyên SQLException gốc bảo toàn map riêng của subclass đó nếu caller thật sự cần điều tra.

~~~java
// Mảnh minh họa, applicationError có SQLException làm cause.
Throwable cause = applicationError.getCause();
if (cause instanceof java.sql.SQLClientInfoException clientInfoError) {
    var failed = clientInfoError.getFailedProperties();
    // Log tên property/reason an toàn; không log value nhạy cảm.
}
~~~

Đừng tạo SQLException mới loại chung chỉ từ SQLState nếu bạn cần dữ liệu subclass như update counts hoặc failed properties.

### 13.3. LOB/SQLXML resource failures

Một thao tác có thể thất bại khi đọc dữ liệu hoặc giải phóng Blob/Clob/SQLXML. Nếu close/free ở cleanup cũng fail, cần giữ primary và secondary errors đúng cấp. **free()** trên JDBC LOB không thay đổi dữ liệu trong DB; nó giải phóng tài nguyên của object. Không vứt bỏ nguyên nhân đọc/ghi chính rồi chỉ ném “cleanup failed”.

## 14. Kiểm thử application exception translation

### 14.1. Unit tests không cần DBMS

Dùng test double hoặc stub DAO phát sinh SQLException có SQLState, vendor code, cause, next và suppressed. Assertions quan trọng:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Public code ổn định | ORDER_STORE_FAILED |
| Public message an toàn | Không copy driver message, SQL hoặc PII |
| Wrapper.getCause | Chính reference tới SQLException gốc |
| Cause runtime class | Giữ nguyên subclass, ví dụ SQLIntegrityConstraintViolationException |
| SQLState/vendorCode | Truy cập được từ original |
| Root cause | Vẫn còn Throwable bên dưới |
| Next exception | SQL chain gốc vẫn có |
| Suppressed | Close failure được giữ trên original |
| Wrapper suppressed | Không mặc định phải copy từ original |
| Retry classification | Có thể xem original subtype, nhưng không tự blind retry |
| No swallowed failure | Repository ném lỗi ra caller |
| No duplicate logging | Một vị trí chịu trách nhiệm render error |
| Safe API response | Không serialize Throwable/stacktrace |

Mã runnable ở phần 6 chính là một unit demonstration đáp ứng nhiều hàng ở trên, không đòi hỏi DBMS.

### 14.2. Integration tests với JDBC driver thật

Một số behavior từ driver/DBMS không thể được fake chứng minh:

1. Một duplicate unique key sinh **SQLException subtype** nào, SQLState/vendorCode gì?
2. Driver có nối **getNextException()** khi lỗi batch/failover không?
3. Statement/ResultSet/Connection.close có thể thêm suppressed như thế nào?
4. Transaction rollback/commit failure mapping ra sao?
5. Connection pool có đóng/evict session hỏng đúng không?
6. Error message có chứa dữ liệu client/SQL parameter có tính nhạy cảm không?
7. Error translation có đổi behavior khi driver hoặc DBMS nâng phiên bản không?
8. Global error handler có chỉ trả public fields không?
9. Lỗi được log mấy lần? Có trace/correlation ID để tra cứu nội bộ?
10. Cause chain có giữ subclass đặc thù như BatchUpdateException và counts?
11. Các trường SQLState có thể null; logger/metrics có xử lý null an toàn?
12. Ranh giới transaction có giữ nguyên failure và rollback policy của service?

**Không nên cố gây lỗi destructive trên production database**. Tạo schema/data test phù hợp và dùng credentials ít quyền để kiểm tra.

### 14.3. Kiểm thử không lộ dữ liệu

Chọn một chuỗi giả có dạng secret@example.invalid trong underlying SQLException của test. Xác nhận:

- **Public message** không chứa chuỗi đó.
- **Response DTO** không chứa original cause.
- **Internal diagnostic** chỉ ghi sanitized SQLState/vendor code và context được phép.
- **Không in toàn bộ stacktrace** trong channel public.
- Những kênh log có full cause phải được xem xét quyền truy cập và retention.
- Có cơ chế redaction khi driver message có PII hoặc token.

Trong chương trình, **publicMessageLeaksSecret=false** chứng minh public message riêng an toàn; nó **không chứng minh stacktrace tự được sanitize**.

## 15. Các lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| new AppException(e.getMessage()) | Mất original cause và lộ message | Constructor nhận cause + safeMessage |
| new RuntimeException("failed") | Không có SQLState/vendor code/stack gốc | super(message, cause) |
| new SQLException("error", state) | Mất subtype/next/suppressed nếu bỏ original | Dùng constructor có cause hoặc giữ original |
| Catch rồi printStackTrace và return | Báo thành công giả | Propagate đúng application exception |
| Nhiều tầng wrap không lý do | Stacktrace dài, khó hiểu | Wrap ở abstraction boundary |
| Log nguyên exception ở mọi layer | Duplicate logs, có thể lộ data | Log một lần ở boundary phù hợp |
| Bỏ cause để redaction | Mất diagnostics | Giữ cause nội bộ, tách public DTO |
| Đưa exception object vào JSON | Lộ SQL/PII/stacktrace | Response DTO chỉ có safe fields |
| Tự sao chép stacktrace nhưng không cause | Mất chain và subtype | Giữ nguyên Throwable reference |
| Coi getNextException là getCause | Bỏ sót JDBC diagnostics | Đọc hai chain riêng |
| Coi wrapper.getSuppressed là suppressed của original | Không thấy cleanup failure | Đọc original.getSuppressed |
| Catch Throwable/Exception quá rộng | Che programming bugs và cancellation | Catch SQLException ở JDBC boundary |
| Retry chỉ dựa trên SQLState | Sai commit/transaction outcome | Business safe-to-repeat + driver mapping |
| Wrapper chung che BatchUpdateException | Không đọc được counts | Giữ original subclass trong cause |
| Bắt SQLRecoverableException rồi chạy lại statement cũ | Sử dụng session đã hỏng | Reconnect, replay toàn transaction khi an toàn |
| Custom constructor chỉ nhận String | Khó giữ nguyên nhân | Thêm overload (message, Throwable) |
| initCause sau constructor đã có cause | IllegalStateException | Chọn một cách gán cause duy nhất |
| finally close che lỗi chính | Mất lỗi execute ban đầu | try-with-resources/addSuppressed |
| Test fake pass → kết luận vendor tương tự | Sai giả định về driver | Integration test thật |

## 16. Bài tập tự luyện

1. Chạy chương trình, giải thích vì sao **sameCause=true** dù wrapper và SQLException là hai objects khác nhau.
2. Thay wrapper thành **new RuntimeException(original.getMessage())** rồi so sánh getCause, SQLState và public message.
3. Thay bằng **new RuntimeException("Failed", original)** và giải thích vì sao cause giữ được nhưng application error contract chưa rõ.
4. Đổi SQLState/vendorCode của lỗi fake, kiểm tra original values có còn sau wrap không.
5. Bỏ **setNextException(...)** rồi kiểm tra nextState; thiết kế code xử lý null an toàn.
6. Đổi fake close để không ném SQLException; dự đoán suppressedCount.
7. Thêm một SQLException close failure thứ hai bằng nested resources; kiểm tra suppressed count/order.
8. Thử **printStackTrace** trên wrapper trong **môi trường local test**, quan sát Caused by/Suppressed rồi giải thích vì sao không đưa stack trace lên public API.
9. Tạo một checked StorageOperationException extends Exception với constructor nhận original SQLException.
10. Viết một global exception handler trả safe error DTO, không serialize Throwable.
11. Thêm kiểm tra SQLTransactionRollbackException trong underlying cause và xây policy retry **toàn transaction** khi operation idempotent.
12. Tạo một BatchUpdateException fake chứa updateCounts; đảm bảo wrapper vẫn cho truy cập counts.
13. Tạo SQLException với getCause() là IOException và next SQLException khác, vẽ sơ đồ graph.
14. Viết một logger ghi **operation/code/SQLState/vendorCode** không chứa database message/SQL parameters.
15. Test SQLException.getSQLState() có thể null; không để metrics crash.
16. Thử gọi **initCause** hai lần và bắt IllegalStateException; nêu lý do constructor nhận cause tốt hơn.
17. Kiểm tra application exception ở service layer không bị wrap thêm chỉ để đổi text.
18. Thiết kế integration test với DB test cho unique constraint, batch failures và cleanup errors.
19. Thiết kế redaction policy để các log nội bộ có nguyên nhân gốc nhưng không phát tán credentials/PII.
20. Giải thích tại sao **giữ cause** có giá trị quan sát nhưng **không thay thế idempotency** trong nghiệp vụ ghi.

## 17. Checklist production

- [ ] Chỉ dịch SQLException ở ranh giới abstraction rõ ràng.
- [ ] Custom application exception có constructor nhận cause, gọi super(message, cause).
- [ ] Original SQLException object vẫn là cause hoặc nằm trong cause chain.
- [ ] Public code/message do app định nghĩa và không có SQL/PII/secret.
- [ ] Không dùng getMessage()/toString() của driver làm public message.
- [ ] Không serialize Throwable/stacktrace/nextException vào API response.
- [ ] SQLState/vendor code, class name và correlation ID có thể tra cứu nội bộ an toàn.
- [ ] Phân biệt cause chain, SQLException next-exception chain và suppressed chain.
- [ ] Khi try-with-resources close fail, primary exception được giữ và close failure suppressed.
- [ ] Không bắt Throwable rồi chuyển mọi thứ thành persistence failure.
- [ ] Không log trùng ở mọi tầng hoặc bỏ hết lỗi rồi trả success.
- [ ] Không thay stacktrace thủ công để giả tạo nguyên nhân.
- [ ] Không dùng initCause khi constructor đã có cause; custom mới nên có cause constructor.
- [ ] Không blind retry chỉ bởi underlying exception transient/recoverable.
- [ ] Commit ambiguity cần idempotency/reconciliation, không mất transaction context.
- [ ] BatchUpdateException/update counts và subclass metadata vẫn có thể truy cập.
- [ ] Có tests cho lỗi từ driver, cleanup, SQLState=null, next/suppressed và public response.
- [ ] Tài liệu/logging/exception mapping phù hợp JDBC driver + database versions hiện dùng.
- [ ] Connection/PreparedStatement/ResultSet được đóng theo ownership, không làm sai transaction manager.
- [ ] Không dùng JDBC test double như chứng cứ driver thực thi SQL thật.

## Kết luận

**Bảo toàn nguyên nhân lỗi khi chuyển sang ngoại lệ ứng dụng** là một yêu cầu thiết kế quan trọng của hệ thống JDBC. Cách chuẩn là **catch (SQLException original) → throw new ApplicationException(safeMessage, original)**, với custom constructor gọi **super(message, cause)**. Mọi thông tin của original SQLException (SQLState, vendor code, subtype, next chain, cause và suppressed cleanup errors) vẫn được truy cập từ cause.

Tầng public chỉ nhận **mã và thông điệp an toàn**; tầng diagnostics có thể truy cập nguyên nhân đầy đủ theo quy trình bảo mật. Không làm mất cause chỉ để redaction, không log hoặc serialize toàn bộ exception ở nơi client có thể nhìn thấy. Đồng thời, giữ cause giúp quan sát và phân loại lỗi nhưng **không tự chứng minh retry là an toàn**, nhất là trong trường hợp transaction COMMIT có kết quả không rõ.

**Tài liệu chính thức hiện hành:**

- [Throwable — Java SE 26 (getCause, constructors, initCause, suppressed)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html)
- [SQLException — Java SE 26 (SQLState, vendorCode, next exception)](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html)
- [SQLIntegrityConstraintViolationException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLIntegrityConstraintViolationException.html)
- [SQLTransactionRollbackException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html)
- [BatchUpdateException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/BatchUpdateException.html)
- [SQLClientInfoException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLClientInfoException.html)
- [Throwable — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [SQLException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html)