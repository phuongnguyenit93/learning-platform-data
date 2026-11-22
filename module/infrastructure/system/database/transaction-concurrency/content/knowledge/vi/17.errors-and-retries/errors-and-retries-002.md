# Nhận diện lỗi bế tắc hoặc tuần tự hóa bằng mã lỗi của hệ quản trị

Khi nhiều giao dịch cùng truy cập dữ liệu, hệ quản trị có thể phải hủy một giao dịch để phá deadlock hoặc để bảo đảm lịch thực thi có thể tuần tự hóa. Ứng dụng cần nhận diện đúng loại lỗi để quyết định có nên chạy lại toàn bộ transaction hay trả lỗi cho người gọi.

Không nên chỉ dựa vào nội dung thông báo lỗi như “deadlock”, “transaction aborted” hoặc “lock timeout”. Nội dung có thể thay đổi theo phiên bản, ngôn ngữ, driver và framework. Cách đáng tin cậy hơn là kết hợp **SQLSTATE**, **mã lỗi riêng của nhà cung cấp** (*vendor error code*) và ngữ cảnh hệ quản trị đang kết nối.

## 1. Phân biệt ba nhóm lỗi thường gặp

Các lỗi đồng thời thường bị nhầm lẫn với nhau, nhưng chúng thể hiện những tình huống khác nhau.

| Nhóm lỗi | Điều gì đã xảy ra? | Hướng xử lý thường gặp |
|---|---|---|
| Deadlock | Các transaction tạo thành chu trình chờ khóa. Hệ quản trị chọn một transaction làm nạn nhân và hủy nó. | Rollback và thử lại toàn bộ transaction nếu nghiệp vụ cho phép. |
| Serialization failure | Lịch chạy đồng thời không thể được chấp nhận như một thứ tự tuần tự hợp lệ theo isolation level. Hệ quản trị hủy một transaction. | Bắt đầu transaction mới, đọc lại dữ liệu và thực hiện lại toàn bộ nghiệp vụ. |
| Lock wait timeout | Một yêu cầu khóa đã chờ quá thời hạn cấu hình. Điều này không chứng minh có chu trình deadlock. | Xem nguyên nhân chờ; có thể thử lại có giới hạn sau khi rollback, hoặc trả lỗi nếu chờ là dấu hiệu của tải quá cao. |

### 1.1. Deadlock

Ví dụ hai transaction khóa hai hàng theo thứ tự ngược nhau:

- T1 giữ khóa hàng A và chờ hàng B.
- T2 giữ khóa hàng B và chờ hàng A.

Không transaction nào có thể tiếp tục để tự giải phóng khóa. Hệ quản trị phát hiện chu trình, chọn một nạn nhân và trả lỗi cho transaction đó.

Deadlock là lỗi cạnh tranh có thể xảy ra ngay cả khi mỗi câu SQL riêng lẻ đều hợp lệ. Ứng dụng thường có thể thử lại transaction bị hủy.

### 1.2. Serialization failure

Ở mức cô lập SERIALIZABLE, hệ quản trị phải bảo đảm kết quả tương đương một thứ tự thực thi tuần tự. Nếu các thao tác đồng thời tạo ra một lịch không đáp ứng bảo đảm này, một transaction có thể bị hủy.

Lỗi này không nhất thiết có deadlock hay một giao dịch phải chờ khóa. Ví dụ, PostgreSQL dùng Serializable Snapshot Isolation để theo dõi phụ thuộc đọc–ghi và có thể trả lỗi serialization failure khi phát hiện lịch chạy nguy hiểm.

Ứng dụng phải đọc lại dữ liệu trong transaction mới. Giữ nguyên quyết định đã tính từ snapshot cũ rồi chỉ chạy lại câu UPDATE cuối cùng là không an toàn.

### 1.3. Lock wait timeout

Timeout cho biết một yêu cầu khóa đã chờ quá lâu theo cấu hình. Có thể chỉ có một transaction giữ khóa lâu, không hề có chu trình chờ.

Ví dụ T1 cập nhật một hàng rồi thực hiện công việc kéo dài trước khi commit. T2 cần khóa cùng hàng và hết thời gian chờ. T2 nhận timeout dù T1 không chờ T2.

Timeout thường cần được điều tra về thời gian transaction, truy vấn chậm, hàng nóng và giới hạn chờ. Có thể retry nếu đó là chính sách của ứng dụng, nhưng không nên ghi nhận timeout như một deadlock.

## 2. SQLSTATE và vendor error code khác nhau thế nào?

**SQLSTATE** là mã trạng thái gồm năm ký tự được chuẩn hóa theo quy ước SQL. Nó giúp phân loại nhóm lỗi theo cách tương đối độc lập với nhà cung cấp.

**Vendor error code** là mã số do hệ quản trị cụ thể định nghĩa. Nó thường phân biệt rõ hơn một lỗi đặc thù như deadlock victim hoặc lock wait timeout.

Ví dụ:

- PostgreSQL dùng SQLSTATE **40P01** cho deadlock detected và **40001** cho serialization failure.
- MySQL InnoDB dùng vendor code **1213** cho deadlock; SQLSTATE của lỗi này là **40001**.
- SQL Server dùng error number **1205** cho deadlock victim.
- Oracle dùng mã **ORA-00060** cho deadlock detected.

Điểm cần chú ý: cùng một SQLSTATE không nhất thiết mang cùng ngữ nghĩa chi tiết ở mọi hệ quản trị. MySQL dùng **40001** cho deadlock InnoDB, trong khi PostgreSQL dùng **40001** cho serialization failure và **40P01** cho deadlock.

Do đó, nếu ứng dụng hỗ trợ nhiều hệ quản trị, hãy kết hợp mã với database vendor. Không nên viết một quy tắc chung kiểu “SQLSTATE 40001 luôn là deadlock”.

## 3. Các mã lỗi thường gặp theo hệ quản trị

### 3.1. PostgreSQL

| Tình huống | SQLSTATE | Tên/ý nghĩa |
|---|---|---|
| Deadlock | **40P01** | deadlock_detected |
| Serialization failure | **40001** | serialization_failure |
| Không lấy được khóa ngay | **55P03** | lock_not_available |
| Hủy câu lệnh do statement timeout | **57014** | query_canceled |

Ví dụ PostgreSQL:

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE account_id = 10;

-- Nếu transaction khác tạo chu trình chờ,
-- PostgreSQL có thể trả SQLSTATE 40P01.

COMMIT;
~~~

Với SERIALIZABLE:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;

-- Các thao tác đọc/ghi tiếp theo có thể tạo
-- phụ thuộc không thể tuần tự hóa.

COMMIT;
~~~

Nếu PostgreSQL trả **40001**, ứng dụng phải rollback và chạy lại toàn bộ transaction. Sau một lỗi làm transaction bị đánh dấu aborted, không thể tiếp tục dùng transaction đó để chạy lại câu SQL.

**55P03** có thể xuất hiện khi dùng NOWAIT hoặc cấu hình lock_timeout. Đây là lỗi không lấy được khóa theo yêu cầu, không phải mã deadlock. **57014** là query canceled; nguyên nhân có thể là statement timeout hoặc thao tác hủy câu lệnh. Cần xem ngữ cảnh thay vì tự động coi mọi trường hợp là lỗi đồng thời có thể retry.

Trong JDBC, driver PostgreSQL thường cung cấp SQLSTATE qua SQLException.getSQLState(). Có thể kiểm tra thêm kiểu exception cụ thể do driver cung cấp, nhưng SQLSTATE là căn cứ quan trọng để phân loại.

### 3.2. MySQL InnoDB

| Tình huống | Vendor error code | SQLSTATE | Ý nghĩa |
|---|---:|---|---|
| Deadlock | **1213** | **40001** | ER_LOCK_DEADLOCK |
| Lock wait timeout | **1205** | **HY000** | ER_LOCK_WAIT_TIMEOUT |
| Duplicate key | **1062** | **23000** | ER_DUP_ENTRY |

Ví dụ deadlock:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100
WHERE account_id = 10;

-- Một transaction khác giữ khóa cần thiết
-- và tạo chu trình chờ.

COMMIT;
~~~

Khi InnoDB phát hiện deadlock, nó chọn một transaction làm nạn nhân và rollback transaction đó. Lỗi thường có vendor code **1213**.

Lỗi **1205** khác với **1213**: nó biểu thị lock wait timeout. Theo mặc định, InnoDB thường rollback câu lệnh bị timeout; việc rollback toàn transaction còn phụ thuộc cấu hình như innodb_rollback_on_timeout. Ứng dụng nên chủ động rollback transaction hiện tại trước khi thử lại để tránh tiếp tục trên trạng thái không mong muốn.

MySQL dùng SQLSTATE **40001** cho deadlock InnoDB. Vì vậy, khi phân loại MySQL, hãy ưu tiên vendor code **1213** để nhận diện deadlock và dùng **1205** để nhận diện lock wait timeout. Đừng chỉ nhìn SQLSTATE rồi gắn nhãn deadlock cho mọi lỗi 40001.

### 3.3. SQL Server

| Tình huống | Error number | Ý nghĩa |
|---|---:|---|
| Deadlock victim | **1205** | Transaction bị chọn làm nạn nhân deadlock và rollback |
| Lock request timeout | **1222** | Yêu cầu khóa vượt quá thời gian chờ |
| Snapshot update conflict | **3960** | Transaction SNAPSHOT gặp xung đột cập nhật |

Ví dụ deadlock victim:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.Account
SET Balance = Balance - 100
WHERE AccountId = 10;

-- Nếu SQL Server chọn transaction làm deadlock victim,
-- lỗi 1205 được trả về và transaction bị rollback.

COMMIT TRANSACTION;
~~~

**1205** là dấu hiệu deadlock rõ ràng. **1222** là lock timeout và không chứng minh có deadlock. **3960** là xung đột khi dùng snapshot isolation; ứng dụng thường phải bắt đầu transaction mới và đọc lại dữ liệu.

Với SQL Server JDBC Driver, có thể lấy mã lỗi qua SQLServerException.getErrorCode() hoặc phương thức kế thừa SQLException.getErrorCode(). SQLSTATE cũng được cung cấp, nhưng vendor error number giúp phân biệt các tình huống SQL Server cụ thể.

### 3.4. Oracle Database

| Tình huống | Oracle error | Ý nghĩa |
|---|---|---|
| Deadlock | **ORA-00060** | Deadlock detected while waiting for resource |
| Serialization conflict | **ORA-08177** | Cannot serialize access for this transaction |
| Resource busy với NOWAIT | **ORA-00054** | Resource busy and acquire with NOWAIT specified |
| Hết thời gian chờ khóa | **ORA-30006** | Resource busy; acquire with WAIT timeout expired |

**ORA-00060** là lỗi deadlock. Oracle thường rollback câu lệnh gây deadlock; ứng dụng cần rollback transaction theo ranh giới nghiệp vụ rồi thử lại toàn bộ đơn vị công việc để không giữ các quyết định trước đó.

**ORA-08177** xuất hiện khi transaction ở SERIALIZABLE không thể tiếp tục do dữ liệu đã thay đổi theo cách xung đột với snapshot của transaction. Đây là lỗi serialization, không phải deadlock.

**ORA-00054** và **ORA-30006** phản ánh không lấy được tài nguyên theo chính sách chờ. Chúng không tự chứng minh có chu trình deadlock.

Trong JDBC Oracle, vendor code có thể được lấy qua SQLException.getErrorCode(). Thông thường mã trả về là phần số của Oracle error, chẳng hạn **60** cho ORA-00060 và **8177** cho ORA-08177; thông báo có thể chứa tiền tố ORA. Hãy kiểm tra driver và cách framework bọc exception trong ứng dụng thực tế.

## 4. Bảng đối chiếu nhanh

| Hệ quản trị | Deadlock | Serialization conflict | Lock timeout / không lấy được khóa |
|---|---|---|---|
| PostgreSQL | SQLSTATE **40P01** | SQLSTATE **40001** | **55P03** cho lock not available; **57014** có thể là query canceled |
| MySQL InnoDB | Code **1213**, SQLSTATE **40001** | Tùy tình huống và engine; phân biệt bằng mã cụ thể | Code **1205**, SQLSTATE **HY000** |
| SQL Server | Error **1205** | Error **3960** cho snapshot update conflict | Error **1222** |
| Oracle | **ORA-00060** / vendor code **60** | **ORA-08177** / vendor code **8177** | **ORA-00054**, **ORA-30006** |

Các mã trên là những mã thường gặp cho các tình huống được nêu. Driver, phiên bản, framework và cấu hình timeout có thể ảnh hưởng cách exception được bọc hoặc cách SQLSTATE được cung cấp. Hãy xác nhận bằng tài liệu đúng phiên bản đang triển khai và kiểm tra cả mã nhà cung cấp lẫn SQLSTATE.

## 5. Nhận diện lỗi trong Java JDBC

JDBC cung cấp một số lớp exception hữu ích:

- **SQLException:** lớp cơ sở cho lỗi truy cập dữ liệu; có SQLSTATE, vendor code và chuỗi exception tiếp theo.
- **SQLTransactionRollbackException:** biểu thị transaction bị rollback do lỗi đồng thời hoặc lý do liên quan theo phân loại driver.
- **SQLTransientException:** lỗi tạm thời mà thao tác có thể thành công nếu thử lại.
- **SQLTimeoutException:** thao tác vượt thời gian cho phép.

Không phải driver nào cũng ánh xạ mọi deadlock hoặc serialization failure vào cùng một lớp exception. Vì vậy, không nên chỉ dựa vào instanceof SQLTransientException. Hãy kiểm tra cả SQLSTATE và vendor code trong chuỗi exception.

Ví dụ helper đọc toàn bộ chuỗi SQLException:

~~~java
import java.sql.SQLException;

static boolean containsSqlState(SQLException error, String expected) {
    for (SQLException current = error;
         current != null;
         current = current.getNextException()) {

        if (expected.equals(current.getSQLState())) {
            return true;
        }
    }
    return false;
}

static boolean containsVendorCode(SQLException error, int expected) {
    for (SQLException current = error;
         current != null;
         current = current.getNextException()) {

        if (current.getErrorCode() == expected) {
            return true;
        }
    }
    return false;
}
~~~

Một số driver đặt lỗi gốc trong getCause() thay vì chỉ trong getNextException(). Trong ứng dụng thực tế, hãy duyệt cả cause chain, đồng thời tránh lặp vô hạn nếu exception có tham chiếu vòng. Nếu dùng framework, có thể cần đi từ exception framework đến nguyên nhân JDBC bên dưới.

### 5.1. Phân loại theo database vendor

Không nên phân loại chỉ dựa vào một mã dùng chung. Ví dụ:

~~~java
enum DatabaseVendor {
    POSTGRESQL,
    MYSQL,
    SQL_SERVER,
    ORACLE
}

enum ConcurrencyFailure {
    DEADLOCK,
    SERIALIZATION_FAILURE,
    LOCK_TIMEOUT,
    OTHER
}
~~~

Logic phân loại có thể được viết theo nguyên tắc:

~~~java
static ConcurrencyFailure classify(
        SQLException error,
        DatabaseVendor vendor) {

    switch (vendor) {
        case POSTGRESQL:
            if (containsSqlState(error, "40P01")) {
                return ConcurrencyFailure.DEADLOCK;
            }
            if (containsSqlState(error, "40001")) {
                return ConcurrencyFailure.SERIALIZATION_FAILURE;
            }
            if (containsSqlState(error, "55P03")) {
                return ConcurrencyFailure.LOCK_TIMEOUT;
            }
            break;

        case MYSQL:
            if (containsVendorCode(error, 1213)) {
                return ConcurrencyFailure.DEADLOCK;
            }
            if (containsVendorCode(error, 1205)) {
                return ConcurrencyFailure.LOCK_TIMEOUT;
            }
            break;

        case SQL_SERVER:
            if (containsVendorCode(error, 1205)) {
                return ConcurrencyFailure.DEADLOCK;
            }
            if (containsVendorCode(error, 3960)) {
                return ConcurrencyFailure.SERIALIZATION_FAILURE;
            }
            if (containsVendorCode(error, 1222)) {
                return ConcurrencyFailure.LOCK_TIMEOUT;
            }
            break;

        case ORACLE:
            if (containsVendorCode(error, 60)) {
                return ConcurrencyFailure.DEADLOCK;
            }
            if (containsVendorCode(error, 8177)) {
                return ConcurrencyFailure.SERIALIZATION_FAILURE;
            }
            if (containsVendorCode(error, 54)
                    || containsVendorCode(error, 30006)) {
                return ConcurrencyFailure.LOCK_TIMEOUT;
            }
            break;
    }

    return ConcurrencyFailure.OTHER;
}
~~~

Đây là ví dụ minh họa cho một danh sách mã thường gặp, không phải thư viện phân loại hoàn chỉnh. Có thể cần bổ sung mã theo phiên bản, driver, loại storage engine và cấu hình ứng dụng. Với PostgreSQL, **55P03** thường là không lấy được khóa theo yêu cầu; nếu muốn tách riêng NOWAIT và lock timeout thì cần thêm ngữ cảnh cấu hình hoặc thông tin chi tiết của driver.

Một ứng dụng hỗ trợ nhiều database nên xác định vendor từ cấu hình DataSource hoặc DatabaseMetaData.getDatabaseProductName(), sau đó dùng classifier tương ứng. Không nên suy ra vendor bằng cách tìm từ khóa trong message.

## 6. Framework có thể bọc mã lỗi gốc

Nếu dùng Spring JDBC hoặc Spring Data, lỗi JDBC thường được chuyển thành các exception trong hệ thống DataAccessException.

Các loại có thể gặp gồm:

- **DeadlockLoserDataAccessException:** deadlock victim.
- **CannotSerializeTransactionException:** transaction không thể được tuần tự hóa.
- **PessimisticLockingFailureException:** lỗi liên quan khóa bi quan.
- **TransientDataAccessException:** nhóm lỗi tạm thời có thể cân nhắc retry.

Tên lớp cụ thể phụ thuộc phiên bản Spring và cơ chế exception translation. Để phân loại chính xác, cần kiểm tra root cause và mã lỗi gốc thay vì chỉ dựa vào lớp exception ngoài cùng.

Ví dụ, một DataAccessException có thể bọc SQLException, còn SQLException lại có chuỗi exception khác. Hãy giữ thông tin SQLSTATE và vendor code trong log để việc điều tra không mất chi tiết.

## 7. Retry đúng ranh giới transaction

Khi nhận deadlock hoặc serialization failure, transaction hiện tại thường đã bị rollback hoặc không còn ở trạng thái có thể tiếp tục. Vì vậy, phải tạo một transaction mới và chạy lại toàn bộ đơn vị nghiệp vụ.

Quy trình:

1. Phân loại lỗi dựa trên database vendor, SQLSTATE và vendor code.
2. Rollback hoặc đóng transaction hiện tại.
3. Bắt đầu transaction mới.
4. Đọc lại toàn bộ dữ liệu cần thiết.
5. Tính toán lại các quyết định nghiệp vụ.
6. Thực hiện lại các câu lệnh ghi.
7. Commit nếu thành công; nếu lỗi đồng thời lại xảy ra, thử lại trong giới hạn cấu hình.

Không nên chỉ chạy lại câu UPDATE cuối cùng trong transaction đã bị rollback. Ví dụ, nếu transaction đọc số dư 1.000, tính số dư mới 800 rồi bị hủy, lần thử lại phải đọc số dư hiện tại và tính lại từ đầu.

### 7.1. Ví dụ retry với JDBC

Mã minh họa sau giả sử hàm performBusinessOperation thực hiện toàn bộ nghiệp vụ trong connection được truyền vào. Mỗi lần thử sử dụng một transaction mới:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransactionRunner {
    private final DataSource dataSource;
    private final int maxAttempts;

    public TransactionRunner(DataSource dataSource, int maxAttempts) {
        this.dataSource = dataSource;
        this.maxAttempts = maxAttempts;
    }

    public Result execute() throws Exception {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try (Connection connection = dataSource.getConnection()) {
                connection.setAutoCommit(false);

                try {
                    Result result = performBusinessOperation(connection);
                    connection.commit();
                    return result;
                } catch (SQLException | RuntimeException error) {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackError) {
                        error.addSuppressed(rollbackError);
                    }
                    throw error;
                }
            } catch (SQLException error) {
                ConcurrencyFailure failure =
                    classify(error, DatabaseVendor.POSTGRESQL);

                boolean retryable =
                    failure == ConcurrencyFailure.DEADLOCK
                    || failure == ConcurrencyFailure.SERIALIZATION_FAILURE;

                if (!retryable || attempt == maxAttempts) {
                    throw error;
                }

                pauseBeforeRetry(attempt);
            }
        }

        throw new IllegalStateException("Unreachable");
    }

    private Result performBusinessOperation(Connection connection)
            throws SQLException {
        // Đọc dữ liệu, kiểm tra điều kiện và ghi trong transaction này.
        throw new UnsupportedOperationException("Implement business operation");
    }

    private void pauseBeforeRetry(int attempt) throws InterruptedException {
        long baseMillis = 50L;
        long capMillis = 1000L;
        long exponential = Math.min(
            capMillis,
            baseMillis * (1L << Math.min(attempt - 1, 10))
        );

        long jitter = java.util.concurrent.ThreadLocalRandom.current()
            .nextLong(Math.max(1L, exponential / 2), exponential + 1);

        try {
            Thread.sleep(jitter);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
        }
    }
}
~~~

Trong ví dụ, classifier cần nhận đúng vendor của DataSource. Nếu dùng MySQL, SQL Server hoặc Oracle thì truyền vendor tương ứng. Hàm performBusinessOperation phải thực hiện toàn bộ thao tác đọc–kiểm tra–ghi, không được dựa vào giá trị đã đọc trong lần thử trước.

Ví dụ trên chỉ retry deadlock và serialization failure. Lock timeout có thể được thêm vào chính sách retry riêng nếu ứng dụng hiểu rõ nguyên nhân chờ và muốn thử lại. Không nên tự động retry mọi SQLException.

Trong code production, nên giới hạn số lần thử nhỏ và cấu hình được, tránh vòng lặp retry không giới hạn khi database đang quá tải. Cũng cần tránh shift overflow trong backoff và dùng bộ tạo jitter phù hợp với chính sách hệ thống.

### 7.2. Retry với Spring

Nếu dùng Spring transaction management, mỗi lần thử phải gọi một ranh giới transaction mới. Có thể dùng TransactionTemplate để mỗi lần execute tạo transaction riêng:

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return transactionTemplate.execute(status -> {
            return performBusinessOperation();
        });
    } catch (RuntimeException error) {
        ConcurrencyFailure failure = classifyFrameworkException(error);

        if (!isRetryable(failure) || attempt == maxAttempts) {
            throw error;
        }

        pauseBeforeRetry(attempt);
    }
}
~~~

Đoạn retry nên nằm bên ngoài phương thức được quản lý bởi transaction. Nếu bắt lỗi và thử lại bên trong cùng một phương thức @Transactional, lần thử sau có thể vẫn chạy trong transaction đã bị đánh dấu rollback-only hoặc đã hỏng.

Nếu dùng @Retryable, hãy cấu hình thứ tự giữa retry interceptor và transaction interceptor để mỗi lần retry tạo một transaction mới. Không giả định thứ tự mặc định của mọi cấu hình đều đáp ứng điều này.

## 8. Lỗi nào không nên tự động retry?

Không phải mọi lỗi SQL đều là lỗi tạm thời.

| Loại lỗi | Ví dụ mã thường gặp | Có nên retry nguyên trạng? |
|---|---|---|
| Deadlock | PostgreSQL 40P01, MySQL 1213, SQL Server 1205, Oracle 60 | Có thể retry toàn bộ transaction |
| Serialization failure | PostgreSQL 40001, SQL Server 3960, Oracle 8177 | Có thể retry toàn bộ transaction |
| Lock timeout | MySQL 1205, SQL Server 1222, PostgreSQL 55P03 trong ngữ cảnh khóa | Tùy chính sách và nguyên nhân chờ |
| Duplicate key | PostgreSQL 23505, MySQL 1062, SQL Server 2601/2627, Oracle 1 | Thường không; xử lý như xung đột nghiệp vụ hoặc dữ liệu |
| Foreign key violation | PostgreSQL 23503, MySQL 1452, SQL Server 547, Oracle 2291 | Không retry nếu dữ liệu đầu vào không đổi |
| Syntax/permission error | Mã cú pháp hoặc quyền truy cập tương ứng | Không retry |
| Connection failure | Lỗi mạng hoặc mất kết nối | Chỉ retry khi xác định được trạng thái commit và tính idempotent |

Một trường hợp đặc biệt là mất kết nối ngay sau khi gửi COMMIT. Client có thể không biết transaction đã commit hay chưa. Không được giả định rằng lỗi kết nối đồng nghĩa transaction chưa commit. Hãy dùng idempotency key hoặc cơ chế đối soát để xác định kết quả trước khi chạy lại một thao tác có tác động tài chính hoặc không thể lặp.

## 9. Retry phải an toàn với side effect

Giả sử transaction tạo đơn hàng và sau đó gửi email xác nhận. Nếu database deadlock sau khi ứng dụng đã gửi email, retry toàn bộ nghiệp vụ có thể gửi email hai lần.

Một số cách xử lý:

- Chỉ gửi email sau khi transaction commit thành công.
- Ghi sự kiện cần gửi vào bảng outbox trong cùng transaction.
- Worker đọc outbox sau commit và gửi sự kiện.
- Dùng idempotency key hoặc mã sự kiện duy nhất để tránh xử lý trùng.
- Đảm bảo thao tác gọi API bên ngoài có cơ chế idempotency nếu nhà cung cấp hỗ trợ.

Transaction retry nên lặp lại phần nghiệp vụ có thể rollback trong database. Những tác động bên ngoài cần được trì hoãn hoặc thiết kế idempotent.

## 10. Ghi log để nhận diện đúng nguyên nhân

Khi bắt lỗi đồng thời, log nên có đủ thông tin để điều tra mà không làm lộ dữ liệu nhạy cảm:

- Database vendor và phiên bản driver.
- SQLSTATE và vendor error code.
- Loại lỗi đã phân loại: deadlock, serialization failure, lock timeout hoặc lỗi khác.
- Tên nghiệp vụ hoặc transaction operation.
- Số lần retry hiện tại và giới hạn tối đa.
- Thời gian transaction chạy trước khi lỗi xảy ra.
- Correlation ID hoặc request ID.
- Deadlock graph hoặc thông tin chẩn đoán do hệ quản trị cung cấp khi có thể.

Không nên chỉ ghi thông báo “retry failed”. Nếu log có SQLSTATE và vendor code, nhóm vận hành có thể phân biệt lỗi do deadlock với timeout hoặc lỗi dữ liệu.

Cần tránh ghi toàn bộ payload, thông tin thanh toán, token hoặc dữ liệu cá nhân vào log. Hãy log khóa định danh đã được phép, mã request và thông tin chẩn đoán cần thiết.

## 11. Khi deadlock hoặc serialization failure xảy ra thường xuyên

Retry là cơ chế phục hồi, không phải cách duy nhất để xử lý một thiết kế có tranh chấp cao.

Nếu tỷ lệ lỗi tăng, hãy xem:

1. Có transaction nào giữ khóa quá lâu không?
2. Các luồng cập nhật nhiều bảng có cùng thứ tự lấy khóa không?
3. Trigger có đọc hoặc ghi thêm bảng nào mà ứng dụng không biết không?
4. Truy vấn có quét phạm vi lớn do thiếu chỉ mục không?
5. Có hàng summary hoặc tài nguyên nóng bị nhiều transaction cập nhật không?
6. Isolation level có cao hơn mức cần thiết hoặc predicate read quá rộng không?
7. Có thể gộp kiểm tra và cập nhật vào một câu lệnh nguyên tử không?
8. Có thể phân vùng workload hoặc giảm thời gian transaction không?

Hãy xem deadlock graph, lock wait report, execution plan và thống kê retry. Nếu chỉ tăng số lần retry mà không xử lý nguyên nhân, hệ thống có thể tạo thêm tải và làm thời gian phản hồi xấu hơn.

## 12. Checklist nhận diện và xử lý lỗi

- [ ] Đã xác định database vendor và phiên bản driver chưa?
- [ ] Đã lấy SQLSTATE và vendor error code từ exception gốc chưa?
- [ ] Đã phân biệt deadlock với serialization failure chưa?
- [ ] Đã phân biệt lock timeout với deadlock chưa?
- [ ] Có kiểm tra toàn bộ SQLException chain và framework cause không?
- [ ] Chỉ retry các lỗi được xác định là tạm thời và có thể phục hồi không?
- [ ] Mỗi lần retry có dùng transaction mới không?
- [ ] Toàn bộ bước đọc, kiểm tra và ghi có được chạy lại không?
- [ ] Số lần retry có giới hạn và có backoff/jitter không?
- [ ] Side effect bên ngoài có idempotent hoặc được xử lý qua outbox không?
- [ ] Log có lưu SQLSTATE, vendor code, operation và số lần retry không?
- [ ] Khi lỗi xảy ra thường xuyên, có điều tra deadlock graph và lock wait thay vì chỉ tăng retry không?

Nhận diện lỗi bằng SQLSTATE và vendor error code giúp ứng dụng phân biệt deadlock, serialization failure và lock timeout một cách có căn cứ. Sau khi phân loại, chỉ những lỗi phù hợp mới được retry; mỗi lần thử phải chạy trong transaction mới và tính toán lại từ dữ liệu hiện hành. Một chính sách retry có giới hạn giúp hệ thống phục hồi khi tranh chấp ngắn hạn, còn việc theo dõi mã lỗi và deadlock diagnostics giúp tìm nguyên nhân cần sửa trong thiết kế truy vấn và transaction.
