# Thử lại giao dịch khi phát hiện xung đột

Trong hệ thống có nhiều người dùng, hai giao dịch có thể cùng truy cập hoặc cập nhật dữ liệu tại một thời điểm. Cơ sở dữ liệu đôi khi phải **chọn một giao dịch để hủy** nhằm ngăn kết quả không nhất quán hoặc tháo gỡ tình trạng chờ khóa. Ứng dụng Java không nên coi mọi lần hủy như lỗi vĩnh viễn: một số xung đột có thể được giải quyết bằng cách **thử lại toàn bộ giao dịch (transaction retry)** sau một khoảng chờ ngắn.

Bài học nằm trong chương **Kiểm soát đồng thời** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, liên hệ việc thiết kế ranh giới persistence cho Java với tính cô lập, xử lý lỗi kết nối, tính toàn vẹn dữ liệu và hiệu năng. Trọng tâm là quyết định **khi nào được retry, retry phần nào và giới hạn ra sao** để một lần thử lại vừa đúng về nghiệp vụ vừa không gây thêm tranh chấp.

Các ví dụ SQL dùng PostgreSQL và SQLSTATE tương ứng. Nguyên tắc tổng quát áp dụng cho cơ sở dữ liệu có giao dịch, nhưng mã lỗi và cách phát hiện xung đột phải được kiểm tra theo từng hệ quản trị/driver.

## 1. Giao dịch bị xung đột nghĩa là gì?

Một giao dịch có thể thực thi hoàn toàn hợp lệ khi chạy riêng lẻ nhưng không thể cùng hoàn tất với giao dịch khác trong một lịch thực thi đồng thời. Có ba tình huống phổ biến:

1. **Xung đột ghi trên cùng dữ liệu:** hai giao dịch cùng muốn thay đổi một hàng hoặc cùng phiên bản dữ liệu; một giao dịch có thể phải chờ, thất bại hoặc được yêu cầu chạy lại.
2. **Deadlock:** T1 giữ khóa A và chờ khóa B, trong khi T2 giữ B và chờ A. DBMS có thể chọn một transaction làm nạn nhân, rollback nó để transaction còn lại tiến lên.
3. **Không thể tuần tự hóa (serialization failure):** các lần đọc/ghi tạo quan hệ phụ thuộc mà nếu cho mọi transaction commit sẽ không thể giải thích như một thứ tự chạy tuần tự hợp lệ; một giao dịch bị hủy để bảo vệ tính cô lập.

Các trường hợp này khác với **lỗi dữ liệu hoặc lỗi nghiệp vụ có tính ổn định**, chẳng hạn khóa ngoại không tồn tại, giá trị âm vi phạm CHECK, yêu cầu vượt hạn mức thật sự hoặc thiếu quyền. Chạy lại nguyên xi thường không chữa được lỗi ổn định.

### Ví dụ nhanh: hai giao dịch muốn đặt chỗ cuối cùng

Một lớp học chỉ còn **một chỗ**. Hai người cùng gửi yêu cầu đăng ký.

~~~text
Ban đầu: sức chứa = 10, đã đăng ký = 9

T1: đọc 9 < 10 -> còn chỗ
T2: đọc 9 < 10 -> còn chỗ
T1: chèn đăng ký của người A
T2: chèn đăng ký của người B

Nếu cả hai cùng commit: 11 đăng ký > 10, vi phạm nghiệp vụ.
~~~

Với transaction và cơ chế kiểm soát đồng thời được thiết kế đúng, DBMS hoặc tầng ứng dụng phải ngăn lịch chạy dẫn đến quá sức chứa. Ở PostgreSQL mức **SERIALIZABLE**, DBMS có thể từ chối một transaction với **SQLSTATE 40001**. Lần retry phải **đếm lại số đăng ký**: khi thấy lớp đã đủ 10 chỗ, ứng dụng trả kết quả “hết chỗ” thay vì chèn tiếp.

Đó là khác biệt cốt lõi giữa **thử lại nghiệp vụ** và **gửi lại câu INSERT một cách mù quáng**.

## 2. Tại sao DBMS chủ động hủy một giao dịch?

Giao dịch đồng thời đem lại thông lượng cao vì CPU và I/O có thể phục vụ nhiều công việc chồng lấn. Để giữ dữ liệu nhất quán, bộ máy quản lý giao dịch, khóa và phiên bản bản ghi phải xử lý những phụ thuộc không thể cùng thỏa mãn.

~~~mermaid
flowchart TD
    A["Bắt đầu giao dịch"] --> B["Đọc, kiểm tra, ghi dữ liệu"]
    B --> C{"Kết quả có thể commit?"}
    C -->|Có| D["COMMIT thành công"]
    C -->|Xung đột có thể retry| E["Giao dịch bị từ chối"]
    C -->|Lỗi nghiệp vụ/không thể retry| F["Trả lỗi hoặc từ chối"]
    E --> G["ROLLBACK / dọn tài nguyên"]
    G --> H{"Còn ngân sách retry?"}
    H -->|Có| I["Backoff + jitter bên ngoài transaction"]
    I --> A
    H -->|Không| J["Trả lỗi tạm thời"]
~~~

Một lỗi **serialization failure** có thể phát sinh ở câu lệnh giữa giao dịch hoặc tại **COMMIT**. Một deadlock cũng có thể được phát hiện trong lúc đang chờ khóa. Khi transaction đã bị từ chối, **ảnh chụp dữ liệu, kết quả SELECT và quyết định nghiệp vụ của lần thử đó phải bỏ đi**.

**Retry đúng:** mở một transaction mới, đọc lại dữ liệu, kiểm tra lại điều kiện, chạy lại các thao tác ghi và commit.

**Retry sai:** giữ kết quả COUNT/SELECT cũ, tiếp tục trên connection đang có transaction lỗi, hoặc chỉ chạy lại lệnh UPDATE cuối cùng. Những cách đó có thể tái tạo quyết định lỗi thời và phá bất biến dữ liệu.

## 3. Nhận diện lỗi có thể thử lại

Không nên thiết kế kiểu **catch (SQLException) -> retry**. JDBC cung cấp **SQLException.getSQLState()** và đôi khi thông tin lỗi có thể nằm trong chuỗi **getNextException()**. Cần có danh sách cho phép rõ ràng theo DBMS.

### 3.1. Bảng tham chiếu PostgreSQL

| SQLSTATE | Ý nghĩa | Hành động thông dụng |
|---|---|---|
| **40001** | serialization_failure | **Retry toàn bộ transaction** sau khi dọn transaction cũ |
| **40P01** | deadlock_detected | Thường **retry toàn bộ transaction**, đồng thời xem lại thứ tự khóa |
| **55P03** | lock_not_available | Có thể retry theo chính sách nếu ứng dụng chủ động dùng NOWAIT hoặc cơ chế khóa tương tự; cần giới hạn |
| **57014** | query_canceled | Có thể do statement timeout hoặc yêu cầu hủy; **không mặc định retry**, phải xác định nguyên nhân và deadline |
| **23505** | unique_violation | Thường là lỗi dữ liệu/nghiệp vụ; **không retry mặc định** |
| **23503** | foreign_key_violation | Lỗi ràng buộc; **không retry mặc định** |
| **08xxx** | Lớp lỗi kết nối | Có thể **không biết COMMIT đã có hiệu lực hay chưa**; cần đối soát, không retry ghi vô điều kiện |

Hai mã **40001** và **40P01** là lựa chọn khởi đầu hợp lý cho một **allowlist** retry giao dịch trong PostgreSQL. Tuy vậy, chính sách vẫn phải xem **tính idempotent**, deadline và side effect của nghiệp vụ.

**Ngoại lệ cần phân tích riêng:** trong một số lịch chạy đồng thời, PostgreSQL có thể biểu hiện tranh chấp bằng lỗi **23505** hoặc lỗi kiểm tra ràng buộc khác mà một lịch chạy tuần tự có thể tránh. Điều đó **không có nghĩa** mọi 23505 được retry: cần hiểu cách sinh khóa và bảo đảm không tạo vòng lặp vô hạn. Với khóa nghiệp vụ trùng thật, retry sẽ không giải quyết được.

### 3.2. Khác biệt giữa các hệ quản trị

Không thể lấy SQLSTATE của PostgreSQL làm một giao thức chung cho mọi DBMS:

- **MySQL/InnoDB:** deadlock thường nhận diện qua mã lỗi nhà cung cấp **1213**, lock wait timeout qua **1205**; hành vi rollback và mã SQLSTATE phải kiểm tra với driver. Một số lỗi deadlock có SQLSTATE 40001.
- **SQL Server:** deadlock victim thường có mã lỗi **1205**; không được nhầm với 1205 của MySQL nếu chỉ so số nguyên.
- **Oracle:** **ORA-00060** là deadlock; **ORA-08177** có thể xuất hiện khi giao dịch không thể tuần tự hóa.

Bản đồ mã lỗi nên được cấu hình ở tầng truy cập dữ liệu hoặc adapter theo DBMS, không rải các câu so chuỗi lỗi trong từng controller.

### 3.3. Phân biệt xung đột với kết quả nghiệp vụ

Một giao dịch thử đặt chỗ có thể trả “lớp đã đầy” sau khi retry. Đây là **kết quả nghiệp vụ hợp lệ**. Nó không phải lỗi SQL và không nên retry tiếp.

Ngược lại, một transaction bị hủy với **40001** chưa nói rằng yêu cầu nghiệp vụ sai; nó cho biết lần thực thi đồng thời đó không được chấp nhận. Ứng dụng cần chạy lại với dữ liệu mới nếu còn ngân sách.

## 4. Minh họa bằng hai phiên SQL

Giả sử PostgreSQL quản lý lớp học và đăng ký:

~~~sql
CREATE TABLE classes (
    id BIGINT PRIMARY KEY,
    capacity INTEGER NOT NULL CHECK (capacity > 0)
);

CREATE TABLE class_enrollments (
    request_id VARCHAR(80) PRIMARY KEY,
    class_id BIGINT NOT NULL REFERENCES classes(id),
    student_id BIGINT NOT NULL,
    UNIQUE (class_id, student_id)
);

INSERT INTO classes (id, capacity) VALUES (42, 1);
~~~

Ví dụ dùng lớp có sức chứa **1**, ban đầu chưa có đăng ký. Mỗi transaction sẽ đọc sức chứa và số lượng đăng ký, nếu còn chỗ mới INSERT. Kiểm tra này **phụ thuộc vào nhiều hàng**, nên chỉ có CHECK trên bảng classes chưa đủ để giới hạn tổng số bản ghi trong class_enrollments.

### 4.1. Session A

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT capacity FROM classes WHERE id = 42;
-- 1

SELECT COUNT(*) FROM class_enrollments WHERE class_id = 42;
-- 0

INSERT INTO class_enrollments (request_id, class_id, student_id)
VALUES ('REQUEST-A', 42, 1001);

-- Dừng ở đây; chuyển sang Session B để thực hiện phần đọc và INSERT.
-- Sau đó COMMIT:
COMMIT;
~~~

### 4.2. Session B

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT capacity FROM classes WHERE id = 42;
-- 1

SELECT COUNT(*) FROM class_enrollments WHERE class_id = 42;
-- 0 nếu chạy xen kẽ trước khi A commit

INSERT INTO class_enrollments (request_id, class_id, student_id)
VALUES ('REQUEST-B', 42, 1002);

COMMIT;
~~~

Để quan sát, cần **hai connection khác nhau** và điều phối cho cả hai transaction có ảnh chụp dữ liệu nhìn thấy lớp trống. Nếu chạy hết Session A rồi mới đến B, Session B sẽ đọc COUNT = 1 và tự từ chối đăng ký; không có xung đột cần hủy.

Trong lịch chồng lấn ở mức SERIALIZABLE của PostgreSQL, DBMS có thể từ chối một giao dịch với:

~~~text
SQLSTATE 40001
ERROR: could not serialize access due to read/write dependencies among transactions
~~~

Chữ trong thông báo và câu lệnh nào nhận lỗi có thể khác nhau. **Không viết code phân loại bằng cách so văn bản lỗi**. Sau rollback, giao dịch bị hủy retry từ đầu, đọc COUNT = 1 và trả “hết chỗ”. Sức chứa được bảo toàn.

Cũng có thể dùng mô hình cập nhật **một bộ đếm còn chỗ bằng UPDATE ... WHERE available > 0** để tránh việc đếm toàn bộ đăng ký ở mỗi yêu cầu; phương án phù hợp phải bảo đảm bộ đếm và bản ghi đăng ký được cập nhật trong **cùng transaction** và mọi luồng ghi dùng cùng quy tắc.

## 5. Quy trình retry toàn bộ giao dịch

Một retry policy đúng nên trả lời sáu câu hỏi:

1. **Giao dịch nào có thể retry?** Chỉ thao tác có ranh giới rõ, không phát sinh side effect không thể hoàn tác trong phần thử lại, và có cơ chế idempotency khi cần.
2. **Lỗi nào được retry?** Danh sách mã lỗi tạm thời được kiểm soát theo DBMS; ví dụ PostgreSQL 40001/40P01.
3. **Retry từ đâu?** Từ bước **tạo transaction mới + đọc lại dữ liệu**, không phải từ câu lệnh bị lỗi.
4. **Bao nhiêu lần?** Giới hạn tổng số attempts và tổng thời gian; không thử vô hạn.
5. **Chờ bao lâu?** Backoff tăng dần có jitter để tránh nhiều request cùng đập lại vào một hàng nóng.
6. **Khi không thành công?** Trả lỗi tạm thời có thể hiểu được, giữ thông tin nguyên nhân, ghi metric và không tự động báo thành công.

Trình tự an toàn cho một lượt thử:

~~~text
1. Xin connection / transaction mới
2. Thiết lập isolation + timeout cần thiết
3. Đọc dữ liệu cần kiểm tra
4. Tính lại quyết định nghiệp vụ
5. Ghi các thay đổi
6. COMMIT
7. Nếu 40001/40P01: ROLLBACK hoặc dọn transaction, trả connection an toàn
8. Chỉ khi còn ngân sách: đợi backoff, quay lại bước 1
~~~

**Vị trí chờ retry:** luôn nằm **ngoài transaction**; không giữ connection hay khóa trong lúc chờ backoff.

### 5.1. Giới hạn số lần thử và thời gian tổng

Định nghĩa rõ:

- **maxAttempts = 3** có nghĩa tối đa **ba lượt** tất cả, gồm một lần đầu và tối đa hai retry.
- **Deadline** có nghĩa tổng thời gian thực thi, chờ khóa, SQL timeout và backoff của cả yêu cầu không vượt ngân sách vận hành.
- **Failure budget** có nghĩa khi đã tiêu hết, trả lỗi cho tầng gọi (ví dụ HTTP 503 hoặc lỗi ứng dụng phù hợp) để tránh giữ request vô hạn.

Một request có ba attempts, mỗi lượt mất 800 ms, cộng hai lần backoff 100 ms và 200 ms đã tốn **2,7 giây** dù không có câu SQL nào thành công ở cuối. Đối với API có timeout 2 giây, cấu hình như vậy không hợp lý.

### 5.2. Backoff và jitter

Cách thường dùng là **exponential backoff có giới hạn**, ví dụ trần chờ tăng theo lượt: 50 ms, 100 ms, 200 ms, 400 ms, tối đa 500 ms. Với **full jitter**, mỗi lượt chọn ngẫu nhiên từ 0 đến trần tương ứng.

~~~text
Lượt thử 1: thực thi ngay
Thất bại -> chọn ngẫu nhiên trong [0, 50] ms
Lượt thử 2: thực thi lại
Thất bại -> chọn ngẫu nhiên trong [0, 100] ms
Lượt thử 3: thực thi lại (nếu còn ngân sách)
~~~

Jitter giúp nhiều client tránh lập tức đồng loạt thử lại sau một xung đột. Tuy nhiên, **backoff không bảo đảm chắc chắn hết deadlock**. Nếu logic luôn lấy khóa theo hai thứ tự ngược nhau, cần sửa thiết kế khóa.

## 6. Cài đặt JDBC: retry transaction đặt chỗ

Ví dụ sau sử dụng bảng ở mục 4, **DataSource** và JDBC 4.x. Mỗi attempt dùng **một connection độc lập** và transaction mức **SERIALIZABLE**. Giá trị **requestId** được giữ cố định giữa các attempts để hỗ trợ truy vết và chống thực hiện trùng nghiệp vụ.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.ThreadLocalRandom;
import javax.sql.DataSource;

public final class EnrollmentService {
    public enum Result { CREATED, ALREADY_REGISTERED, FULL }

    private static final int MAX_ATTEMPTS = 3;
    private static final long MAX_BACKOFF_MS = 500;

    private final DataSource dataSource;

    public EnrollmentService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Result enroll(long classId, long studentId, String requestId)
            throws SQLException, InterruptedException {
        if (classId <= 0 || studentId <= 0
                || requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Tham số đăng ký không hợp lệ");
        }

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                return enrollOnce(classId, studentId, requestId);
            } catch (SQLException failure) {
                if (!isRetryable(failure) || attempt == MAX_ATTEMPTS) {
                    throw failure;
                }
                long capMs = Math.min(MAX_BACKOFF_MS, 50L << (attempt - 1));
                long delayMs = ThreadLocalRandom.current()
                        .nextLong(capMs + 1);
                // Connection của attempt trước đã được đóng ở đây.
                Thread.sleep(delayMs);
            }
        }
        throw new IllegalStateException("Vòng lặp retry không hợp lệ");
    }

    private static boolean isRetryable(SQLException failure) {
        // Ví dụ cho PostgreSQL; mã lỗi cần thay theo DBMS.
        String state = failure.getSQLState();
        return "40001".equals(state) || "40P01".equals(state);
    }

    private Result enrollOnce(long classId, long studentId, String requestId)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException("Cần connection chưa có transaction");
            }

            int originalIsolation = connection.getTransactionIsolation();
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE);
            connection.setAutoCommit(false);

            boolean transactionEnded = false;
            try {
                // Kiểm tra idempotency bằng request ID cố định.
                try (PreparedStatement q = connection.prepareStatement(
                        "SELECT class_id, student_id "
                        + "FROM class_enrollments WHERE request_id = ?")) {
                    q.setString(1, requestId);
                    try (ResultSet rs = q.executeQuery()) {
                        if (rs.next()) {
                            if (rs.getLong(1) != classId
                                    || rs.getLong(2) != studentId) {
                                throw new IllegalArgumentException(
                                        "requestId đã được dùng cho dữ liệu khác");
                            }
                            connection.commit();
                            transactionEnded = true;
                            return Result.ALREADY_REGISTERED;
                        }
                    }
                }

                Integer capacity = null;
                try (PreparedStatement q = connection.prepareStatement(
                        "SELECT capacity FROM classes WHERE id = ?")) {
                    q.setLong(1, classId);
                    try (ResultSet rs = q.executeQuery()) {
                        if (rs.next()) {
                            capacity = rs.getInt(1);
                        }
                    }
                }
                if (capacity == null) {
                    throw new IllegalArgumentException("Lớp không tồn tại");
                }

                long enrolled;
                try (PreparedStatement q = connection.prepareStatement(
                        "SELECT COUNT(*) FROM class_enrollments WHERE class_id = ?")) {
                    q.setLong(1, classId);
                    try (ResultSet rs = q.executeQuery()) {
                        rs.next();
                        enrolled = rs.getLong(1);
                    }
                }

                if (enrolled >= capacity) {
                    connection.commit(); // Kết thúc transaction chỉ đọc.
                    transactionEnded = true;
                    return Result.FULL;
                }

                try (PreparedStatement insert = connection.prepareStatement(
                        "INSERT INTO class_enrollments "
                        + "(request_id, class_id, student_id) VALUES (?, ?, ?)")) {
                    insert.setString(1, requestId);
                    insert.setLong(2, classId);
                    insert.setLong(3, studentId);

                    if (insert.executeUpdate() != 1) {
                        throw new SQLException("Không chèn được đăng ký");
                    }
                }

                connection.commit();
                transactionEnded = true;
                return Result.CREATED;
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                if (transactionEnded) {
                    // Không bật autoCommit khi rollback thất bại:
                    // setAutoCommit(true) có thể commit giao dịch còn mở.
                    connection.setAutoCommit(true);
                    connection.setTransactionIsolation(originalIsolation);
                }
            }
        }
    }
}
~~~

### 6.1. Mã trên xử lý những tình huống nào?

| Tình huống | Kết quả |
|---|---|
| Lớp còn chỗ, transaction commit thành công | **CREATED** |
| requestId đã tồn tại với đúng classId, studentId | **ALREADY_REGISTERED** |
| Lớp đã đủ chỗ trong ảnh chụp được chấp nhận | **FULL** |
| Hai transaction chồng lấn, một bên bị từ chối với **40001** | Bên bị từ chối dọn transaction, chờ ngẫu nhiên rồi **đọc lại từ đầu** |
| Deadlock do DBMS trả **40P01** | Retry tương tự, nhưng vẫn nên xem lại thứ tự khóa |
| Thiếu lớp hoặc requestId dùng cho dữ liệu khác | Lỗi nghiệp vụ, **không retry** |
| INSERT vi phạm ràng buộc UNIQUE **23505** | Không tự động retry; cần phân loại trùng requestId hay trùng học viên theo nghiệp vụ |

Lưu ý: **ALREADY_REGISTERED** trong ví dụ chỉ kiểm tra cùng **requestId**. Nếu cùng học viên gửi requestId mới để đăng ký cùng lớp, ràng buộc **UNIQUE(class_id, student_id)** từ chối lệnh INSERT. Dịch vụ thực tế có thể xử lý lỗi 23505 bằng cách tra cứu bản ghi đã tồn tại, so sánh dữ liệu đầu vào, rồi trả “đã đăng ký” nếu chính sách cho phép; không được trả thành công một cách mù quáng vì bất kỳ lỗi UNIQUE nào.

### 6.2. Các giới hạn quan trọng của ví dụ

Mã này là minh họa có kiểm soát cho giao dịch JDBC do service tự sở hữu. Ở production cần bổ sung **deadline tổng**, timeout câu SQL, tracing, metric retry, bảo đảm connection pool khôi phục hoặc loại bỏ connection hỏng, và phân loại ngoại lệ theo driver/framework. Khi exception xảy ra trong bước dọn dẹp hoặc phục hồi cấu hình, phải giữ nguyên nguyên nhân gốc nếu có và kiểm tra trạng thái kết nối trước khi cho mượn lại.

Khi **rollback thất bại**, connection phải được xem là không đáng tin cho tới khi pool/driver xác định nó an toàn. Khi **COMMIT báo lỗi kết nối**, có thể không xác định transaction đã commit hay chưa; chính sách **chỉ retry 40001/40P01** trong ví dụ cố ý không tự động thử lại mọi lỗi kết nối.

**Không gọi HTTP, gửi email hoặc xuất bản sự kiện bên ngoài DB trong hàm enrollOnce.** Transaction bị retry có thể chạy phần thân nhiều lần; side effect bên ngoài không tự rollback theo cơ sở dữ liệu.

## 7. Lỗi xảy ra lúc COMMIT: giới hạn của retry

Một lỗi có thể retry về mặt kỹ thuật chưa chắc an toàn để thử lại nghiệp vụ.

Xét quy trình:

~~~text
Client -> DB:  COMMIT chuyển tiền 1.000.000 đồng
DB:          Đã commit
Mạng:        Mất kết nối trước khi phản hồi tới client
Client:      Thấy SQLException
~~~

Từ góc nhìn client, **không thể kết luận chỉ dựa vào SQLException rằng COMMIT đã thất bại**. Nếu lập tức tạo một giao dịch mới với mã yêu cầu mới, người nhận có thể được cộng tiền hai lần.

Với những nghiệp vụ không được thực hiện trùng như thanh toán, đặt hàng hay cấp quyền, cần:

1. **Operation ID/idempotency key ổn định** cho cùng một yêu cầu.
2. **Ghi operation ID và thay đổi nghiệp vụ trong cùng transaction** để khi commit thành công có bằng chứng kiểm tra.
3. **Đối soát dữ liệu trên nguồn có thẩm quyền** sau khi kết nối hồi phục, xác minh mã đã tồn tại và nội dung có khớp yêu cầu ban đầu hay không.
4. **Chỉ thực hiện lại** theo giao thức idempotency đã được thiết kế; không mặc định “không nhận được phản hồi” nghĩa là “chưa thực hiện”.

Đối với **40001** được DBMS xác định là transaction bị hủy, chạy lại toàn transaction là cách thường dùng. Với lỗi mạng/timeout quanh COMMIT, phải đi theo đường **kết quả chưa xác định (unknown commit outcome)** và đối soát trước.

## 8. Retry kết hợp với Spring và ORM

Trong ứng dụng Spring, cách phổ biến là đặt transaction ở phương thức service do Spring quản lý:

~~~java
@Service
public class EnrollmentCommandService {
    private final EnrollmentRepository repository;

    public EnrollmentCommandService(EnrollmentRepository repository) {
        this.repository = repository;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public EnrollmentResult enrollOnce(EnrollmentCommand command) {
        EnrollmentResult existing = repository.findExisting(command);
        if (existing != null) {
            return existing;
        }

        int capacity = repository.getCapacity(command.classId());
        long count = repository.countEnrollments(command.classId());

        if (count >= capacity) {
            return EnrollmentResult.full();
        }

        repository.insert(command);
        return EnrollmentResult.created();
    }
}
~~~

Đây là **mã minh họa kiến trúc**, các kiểu EnrollmentRepository, EnrollmentCommand và EnrollmentResult do ứng dụng tự định nghĩa; cần bổ sung imports của Spring nếu dùng trực tiếp.

Điều quan trọng là **retry phải bao bên ngoài ranh giới transaction**. Spring có thể chỉ phát hiện serialization failure khi transaction interceptor thực hiện commit **sau khi method trả về**. Nếu retry loop nằm bên trong method **@Transactional**, nó có thể không bắt được lỗi commit, hoặc cứ chạy lại trong cùng transaction đã bị đánh dấu rollback-only.

Một cấu trúc hợp lý:

~~~text
HTTP handler / application service
    |
    +-- Retry policy (maxAttempts + backoff + deadline)
           |
           +-- Gọi bean @Transactional thông qua Spring proxy
                  |
                  +-- đọc điều kiện -> ghi -> COMMIT/ROLLBACK
           |
           +-- Nếu 40001/40P01: gọi bean lại => transaction mới
~~~

Nếu dùng **@Retryable**, **RetryTemplate** hoặc interceptor riêng, phải kiểm tra **thứ tự AOP advice** để mỗi attempt thực sự tạo một transaction mới. Gọi method **@Transactional** qua **self-invocation** (method trong cùng object gọi nhau) có thể bỏ qua proxy, khiến transaction không được áp dụng như kỳ vọng.

Ngoài ra, JPA/Hibernate có thể bọc SQLException vào exception của ORM, Spring có thể ánh xạ thành lớp exception riêng. Logic phân loại phải đọc **SQLSTATE hoặc mã vendor ở nguyên nhân gốc** khi phù hợp; tránh retry mọi **DataAccessException**. Sau lỗi transaction, **EntityManager/persistence context** đang giữ entity trạng thái cũ cũng không nên dùng lại cho lần retry như thể nó vẫn hợp lệ; mỗi attempt cần transaction và ngữ cảnh persistence sạch.

## 9. Làm sao tránh retry storm?

**Retry storm** xảy ra khi nhiều request thất bại cùng lúc và tất cả lập tức gửi lại, làm hàng nóng hoặc DB càng quá tải. Một chính sách retry bền vững cần kết hợp:

- **Giới hạn attempts:** ví dụ 3, không tiếp tục vô hạn.
- **Backoff có jitter:** giải đồng bộ các request cùng lỗi.
- **Giới hạn deadline:** không tiếp tục khi thời gian còn lại không đủ để có ý nghĩa.
- **Giới hạn concurrency:** connection pool và hàng đợi request có giới hạn; retry cũng tiêu thụ tài nguyên.
- **Phân biệt lỗi:** lỗi logic, UNIQUE và quyền truy cập không được đưa vào vòng lặp tự động.
- **Giữ transaction ngắn:** đưa gọi HTTP, gửi email và xử lý nặng ra ngoài transaction.
- **Giảm tranh chấp gốc:** thống nhất thứ tự lấy khóa, tối ưu chỉ mục, thu hẹp phạm vi đọc, dùng UPDATE nguyên tử hoặc mô hình dữ liệu khác khi phù hợp.

### 9.1. Deadlock cần cả retry và thiết kế lại thứ tự khóa

Giả sử chuyển tiền giữa hai tài khoản: giao dịch T1 khóa tài khoản A trước B, còn T2 khóa B trước A. Hai giao dịch có thể chờ nhau theo vòng.

Có thể giảm nguy cơ bằng quy tắc **khóa tài khoản có ID nhỏ trước**, rồi khóa tài khoản còn lại, áp dụng nhất quán cho mọi đường chuyển tiền. Retry giúp vượt qua một deadlock đơn lẻ; quy tắc khóa thống nhất giúp giảm tần suất deadlock về lâu dài.

~~~text
Sai:
T1: lock A -> chờ B
T2: lock B -> chờ A

Thiết kế nhất quán:
T1: lock min(A,B) -> lock max(A,B)
T2: lock min(A,B) -> lock max(A,B)
~~~

Khóa có thể tăng thời gian chờ, nên cần đo trong tải thật. SERIALIZABLE/SSI cũng có thể sinh serialization failure dù không có deadlock kiểu hai khóa đối xứng.

### 9.2. Cách chọn mức cô lập và cơ chế ghi

Một transaction cập nhật đúng một hàng bằng:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE sku = 'SKU-42' AND available > 0;
~~~

có thể dùng kiểm tra và ghi trên cùng hàng để tránh nhiều lỗi tranh chấp nghiệp vụ. Ứng dụng phải kiểm tra đúng **một hàng được cập nhật** và đặt các bước liên quan trong cùng transaction. Điều này đôi khi hiệu quả hơn quy trình “SELECT số lượng -> tính trong Java -> UPDATE”.

Ngược lại, quy tắc “tối đa N bản ghi trong một tập mà không có hàng tổng điều phối” thường yêu cầu transaction đủ mạnh, khóa chủ đích hoặc thiết kế cập nhật tập dữ liệu chặt chẽ.

Không chọn retry như giải pháp thay thế cho **thiếu ràng buộc cơ sở dữ liệu** hay lỗi thiết kế đồng thời. Retry chỉ xử lý các lần thực thi bị từ chối; nó không làm một thuật toán sai trở thành đúng.

## 10. Tính nhất quán của side effect ngoài cơ sở dữ liệu

Một transaction gửi email xác nhận **trước COMMIT** có thể gặp xung đột và rollback sau khi email đã gửi. Khi retry, email có thể được gửi lần nữa dù chỉ có một lượt ghi cuối cùng được commit.

Cần phân loại side effect:

| Tác dụng | Có tự rollback cùng transaction DB? | Hướng thiết kế |
|---|---|---|
| INSERT/UPDATE/DELETE trên cùng cơ sở dữ liệu và connection | Có, theo bảo đảm transaction DBMS | Nằm trong transaction |
| Gửi email/SMS | Không | Gửi sau commit theo cơ chế đáng tin cậy, ví dụ outbox + worker |
| Gọi cổng thanh toán HTTP | Không | Idempotency key phía đối tác, trạng thái yêu cầu, saga/bù trừ khi phù hợp |
| Publish sự kiện tới message broker độc lập | Không mặc định | Transactional outbox hoặc phối hợp giao dịch theo hạ tầng |
| Ghi log giám sát kỹ thuật | Không nhất thiết | Cho phép ghi lặp nhưng gắn correlation ID và attempt number |

**Transactional outbox** lưu thông điệp cần phát vào bảng outbox **trong cùng giao dịch với dữ liệu nghiệp vụ**. Một worker khác đọc các hàng đã commit để gửi ra ngoài. Bên nhận thường vẫn cần xử lý idempotent vì có thể nhận lặp.

Đừng phát sự kiện “đặt chỗ thành công” khi transaction mới chỉ chèn hàng nhưng **chưa commit**.

## 11. Đo retry để biết hệ thống đang khỏe hay yếu

Một API có thể trả thành công 99,9% nhưng bên dưới cần thực thi mỗi giao dịch trung bình ba lần; tải DB và độ trễ có thể đang tăng nguy hiểm. Cần đo **cả kết quả cuối cùng lẫn chi phí attempts**.

Các metric gợi ý:

| Metric | Cách đọc |
|---|---|
| **transaction_attempts_total** | Số lượt thực thi, gồm lượt đầu và mọi retry |
| **transaction_retry_total{reason}** | Số retry theo 40001, 40P01 hoặc lý do đã phân loại |
| **transaction_retry_exhausted_total** | Yêu cầu hết ngân sách vẫn không hoàn tất |
| **transaction_duration_ms** | Thời gian từng attempt |
| **request_duration_ms** | Thời gian đầu cuối gồm mọi attempt và backoff |
| **transaction_commits_total** | Số transaction commit thành công |
| **deadlock/serialization failure rate** | Tỷ lệ xung đột cần giải quyết ở DB và application |
| **pool_active_connections / queue wait** | Dấu hiệu retry đang làm connection pool cạn |

Trong PostgreSQL có thể xem thống kê tổng hợp:

~~~sql
SELECT datname, xact_commit, xact_rollback, deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

**xact_rollback không chỉ đếm lỗi 40001**, còn gồm rollback vì các nguyên nhân khác. Muốn biết chính xác tỷ lệ retry, tốt nhất ghi metric phân loại **SQLSTATE** ở tầng ứng dụng và kết hợp log DB. **deadlocks** cũng không đại diện tất cả serialization failures.

Xem transaction đang mở lâu:

~~~sql
SELECT pid, state, now() - xact_start AS transaction_age,
       wait_event_type, wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Việc quan sát phải phù hợp với quyền truy cập và chính sách ghi log. Không ghi thông tin nhạy cảm, mật khẩu hoặc toàn bộ nội dung request trong thông báo retry.

### 11.1. Thử nghiệm đồng thời có kiểm soát

Một bài kiểm thử hữu ích nên:

1. Tạo lớp có sức chứa nhỏ, ví dụ **1 hoặc 2** chỗ.
2. Dùng nhiều luồng Java và connection độc lập gửi đăng ký gần như đồng thời, mỗi yêu cầu có requestId riêng.
3. Bảo đảm mọi lượt dùng logic kiểm tra và INSERT trong cùng transaction SERIALIZABLE.
4. Ghi tổng attempts, số 40001/40P01, kết quả CREATED/FULL, latency và số connection sử dụng.
5. Kiểm tra cuối cùng **COUNT(class_enrollments) <= capacity**.
6. Chạy lại với trường hợp requestId bị gửi lặp và với cấu hình retry bị giới hạn, xác nhận không tạo đăng ký trùng.

Các bộ kiểm thử phải điều khiển lịch thực thi đủ chồng lấn; chạy tuần tự hai request không chứng minh khả năng chống write skew. Với quy trình xử lý lỗi COMMIT không rõ, cần bổ sung thử nghiệm đối soát idempotency riêng.

## 12. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Retry **câu UPDATE/INSERT cuối** | Dùng quyết định dựa trên dữ liệu cũ | Retry cả transaction gồm các SELECT |
| Retry trên cùng transaction đã aborted | DBMS tiếp tục từ chối câu lệnh | Rollback và mở transaction mới |
| Retry mọi SQLException | Lặp vô hạn lỗi dữ liệu hoặc gây tác dụng trùng | Dùng allowlist lỗi transient theo DBMS |
| Retry vô hạn không có backoff | Retry storm, tăng tải và độ trễ | Max attempts + jitter + deadline |
| Sleep khi vẫn giữ connection/khóa | Tăng tranh chấp và cạn pool | Dọn transaction rồi mới sleep |
| Gửi email ngay trong attempt | Email có thể được gửi nhiều lần | Outbox hoặc cơ chế sau commit đáng tin |
| Thử lại lỗi mạng lúc COMMIT như 40001 | Có thể ghi kép nghiệp vụ đã commit | Idempotency key và đối soát |
| Nuốt lỗi SQL rồi vẫn commit | Lưu trạng thái dở dang | Đánh dấu thất bại, rollback và báo lỗi |
| Trong Spring, retry nằm bên trong method @Transactional | Lặp trong transaction lỗi; không bắt lỗi commit | Retry bao ngoài transaction proxy |
| Không đo attempts và tỷ lệ 40001 | Không thấy chi phí thật và tranh chấp tăng | Instrument per-attempt và end-to-end |
| Không khống chế timeout | Request kẹt dù SQL bị hủy nhiều lần | Deadline, statement timeout và giới hạn retry |

## 13. Bài tập tình huống

### Bài 1. Serialization failure ở câu COMMIT

Ứng dụng đã thực hiện SELECT kiểm tra số lượng, INSERT đăng ký rồi gọi COMMIT. JDBC báo **SQLSTATE 40001**. Kỹ sư chỉ chạy lại INSERT vì “SELECT đã thành công”. Điều gì sai?

**Gợi ý:** toàn bộ snapshot và quyết định của attempt cũ đã không được chấp nhận. Lần mới phải mở transaction mới, đọc và kiểm tra số chỗ lại, rồi quyết định có INSERT hay không.

### Bài 2. Xử lý UNIQUE violation

Hai request cùng sinh mã đơn hàng **ORDER-100**. Request thứ hai nhận **23505**. Có nên retry vô điều kiện ba lần?

**Gợi ý:** không. Nếu mã thật sự cố định thì retry vẫn trùng. Cần hiểu đây là idempotent request có cùng dữ liệu, lỗi thuật toán tạo mã, hay một xung đột có thể giải quyết bằng cách tạo mã khác theo chính sách đã xác minh.

### Bài 3. Retry sau COMMIT timeout

Client gửi giao dịch thanh toán rồi mất kết nối khi COMMIT. Có được mặc định tạo yêu cầu mới với mã khác?

**Gợi ý:** không. Giao dịch có thể đã commit. Phải đối soát qua operation ID ổn định và nguồn dữ liệu có thẩm quyền; tránh tính tiền hai lần.

### Bài 4. Deadlock hai tài khoản

T1 khóa account 10 trước account 20. T2 khóa account 20 trước account 10. Hãy nêu hai biện pháp giảm lỗi.

**Gợi ý:** (1) lấy khóa theo thứ tự ID thống nhất; (2) với deadlock tạm thời, rollback và retry toàn transaction với giới hạn/backoff. Đo lại tỷ lệ deadlock sau thay đổi.

### Bài 5. Xác định ngân sách retry

API đặt chỗ có deadline 1 giây, mỗi attempt mất tối đa 400 ms. Có phù hợp cấu hình tối đa năm attempts và backoff 100–500 ms không?

**Gợi ý:** thường không. Trong trường hợp xấu, chỉ ba attempts đã vượt deadline. Cần phối hợp timeout từng attempt, backoff và deadline toàn request.

### Bài 6. Spring transaction proxy

Một service đánh dấu **@Transactional**, bên trong chứa vòng lặp retry bắt **DataAccessException**. Tại sao vẫn có thể thất bại lúc commit?

**Gợi ý:** commit diễn ra ở transaction interceptor sau khi method trả về; vòng lặp nội bộ không bắt được lỗi đó. Retry cần bao ngoài mỗi lần gọi qua proxy để có transaction mới.

### Bài 7. Đo sự cố

Sau triển khai, tỷ lệ request cuối cùng thành công không đổi nhưng **transaction_attempts_total / transaction_commits_total** tăng từ gần 1 lên 2,5. Diễn giải thế nào?

**Gợi ý:** hệ thống đang tiêu thụ nhiều công việc DB hơn trên mỗi giao dịch thành công. Cần kiểm tra xung đột, hot keys, thời gian giao dịch, retry policy và tải đồng thời dù người dùng chưa thấy lỗi.

## 14. Ghi nhớ và áp dụng

**Thử lại giao dịch khi phát hiện xung đột** là một phần của thiết kế kiểm soát đồng thời, không chỉ là một vòng lặp catch exception. Retry chỉ hợp lý khi **DBMS xác định lỗi là transient và việc chạy lại nghiệp vụ an toàn**. Trong PostgreSQL, hai tín hiệu thường dùng là **40001** (serialization failure) và **40P01** (deadlock), nhưng vẫn phải giới hạn attempts và tính đến deadline.

Một attempt mới phải có **transaction mới, lần đọc mới và quyết định nghiệp vụ mới**. Chờ backoff ở ngoài transaction; không phát side effect ngoài DB trong phần có thể lặp; sử dụng idempotency và đối soát khi kết quả COMMIT không rõ. Sau cùng, đo tỷ lệ xung đột và số lần retry để tìm nguyên nhân như khóa lấy sai thứ tự, transaction quá dài hoặc phạm vi đọc quá rộng. Đó là cách giữ dữ liệu nhất quán, duy trì hiệu năng và vận hành tầng persistence Java một cách tin cậy.
