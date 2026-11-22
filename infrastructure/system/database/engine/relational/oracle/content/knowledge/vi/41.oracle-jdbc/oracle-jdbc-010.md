# Batch DML, JDBC standard batching và xử lý BatchUpdateException

Khi ứng dụng Java ghi nhiều bản ghi vào Oracle Database, việc gửi từng câu INSERT, UPDATE hoặc DELETE riêng lẻ có thể tạo ra rất nhiều network round trips. Mỗi lần gọi executeUpdate thường cần gửi lệnh tới database và nhận phản hồi. Nếu ứng dụng xử lý hàng chục nghìn bản ghi, chi phí trao đổi qua mạng và xử lý ở client có thể trở thành phần đáng kể của tổng thời gian.

**JDBC batching** cho phép gom nhiều lệnh DML vào một batch rồi gửi để database xử lý theo nhóm. Cách này đặc biệt hiệu quả với PreparedStatement khi cùng một SQL được thực hiện nhiều lần với các bộ bind values khác nhau. Oracle JDBC driver sử dụng standard JDBC batching để giảm round trips; với PreparedStatement, driver có thể dùng array binding để truyền nhiều bộ giá trị bind trong một lần trao đổi.

Batch không có nghĩa là mọi câu lệnh trở thành một SQL statement duy nhất, không tự động làm transaction thành công toàn bộ, và không thay thế việc quản lý commit/rollback. Khi một lệnh trong batch lỗi, JDBC ném BatchUpdateException. Ứng dụng phải đọc update counts, xác định phần nào đã thực thi, quyết định rollback hoặc tiếp tục theo transaction policy, rồi xử lý retry an toàn.

Bài học thuộc nhóm **Oracle JDBC** của Database Engine Relational Oracle. Nội dung tập trung vào Batch DML, standard JDBC batching, PreparedStatement, batch size, transaction boundaries, BatchUpdateException, update counts, xử lý lỗi và những đặc điểm riêng của Oracle JDBC.

Sau bài này, bạn có thể:

- Giải thích Batch DML và lợi ích giảm network round trips.
- Phân biệt executeUpdate với addBatch/executeBatch.
- Dùng Statement và PreparedStatement batching đúng cách.
- Ưu tiên PreparedStatement cho Oracle JDBC standard batching.
- Hiểu vì sao Oracle-specific update batching đã deprecated và trở thành no-op ở driver 12.2 trở lên.
- Kiểm tra driver có hỗ trợ batch updates hay không.
- Chọn batch size và transaction chunk size phù hợp.
- Quản lý auto-commit, commit, rollback và savepoint.
- Đọc update counts và các hằng SUCCESS_NO_INFO, EXECUTE_FAILED.
- Xử lý BatchUpdateException theo JDBC contract.
- Hiểu hành vi dừng tại lệnh lỗi của Oracle JDBC standard batching.
- Thiết kế retry/idempotency để tránh insert trùng hoặc cập nhật lặp.
- Xử lý lỗi constraint, dữ liệu không hợp lệ và lỗi kết nối.
- Dùng executeLargeBatch khi cần update counts kiểu long và driver hỗ trợ.
- So sánh JDBC batching với set-based SQL, PL/SQL FORALL và công cụ bulk load.
- Đo hiệu năng và thiết kế bài thực hành có thể tái hiện.

> **Phạm vi ví dụ:** Ví dụ Java dùng JDBC chuẩn và Oracle Database 19c JDBC driver. Các API cơ bản áp dụng cho nhiều JDBC drivers, nhưng hiệu năng và hành vi khi batch lỗi có thể khác theo driver. Kiểm tra phiên bản JDK, Oracle JDBC driver, database version và transaction configuration thực tế trước khi triển khai.

## 1. Batch DML là gì?

DML là các lệnh thao tác dữ liệu:

- INSERT: thêm bản ghi.
- UPDATE: thay đổi bản ghi.
- DELETE: xóa bản ghi.
- MERGE: kết hợp insert/update theo điều kiện.

Batch DML gom nhiều lần thực hiện DML vào một nhóm.

### 1.1. Thực thi từng lệnh

~~~java
String sql = "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderRow row : rows) {
        ps.setLong(1, row.orderId());
        ps.setLong(2, row.customerId());
        ps.setBigDecimal(3, row.amount());
        ps.executeUpdate();
    }
}
~~~

Nếu rows có 10.000 phần tử, ứng dụng gọi executeUpdate 10.000 lần. Tùy driver, network và statement lifecycle, điều này có thể tạo ra nhiều round trips.

### 1.2. Gom lệnh thành batch

~~~java
String sql = "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderRow row : rows) {
        ps.setLong(1, row.orderId());
        ps.setLong(2, row.customerId());
        ps.setBigDecimal(3, row.amount());
        ps.addBatch();
    }

    int[] updateCounts = ps.executeBatch();
}
~~~

Ứng dụng vẫn cung cấp từng bộ bind values, nhưng gửi batch để driver thực thi theo nhóm.

### 1.3. Lợi ích

- Giảm network round trips.
- Giảm overhead gọi JDBC API cho từng dòng.
- Tận dụng PreparedStatement và bind variables.
- Giảm chi phí parse/execute lặp lại.
- Tăng throughput cho workload insert/update/delete có cấu trúc lặp.

### 1.4. Batch không phải parallel execution

Batching chủ yếu gom việc gửi và thực thi nhiều lệnh. Nó không mặc nhiên chạy mọi lệnh song song trên database. Không được giả định batch sẽ dùng nhiều CPU cores hoặc tạo nhiều database sessions.

### 1.5. Batch không tự bảo đảm transaction atomic

Batch có thể có một số lệnh thực thi thành công trước khi lệnh sau lỗi. Nếu auto-commit tắt, các thay đổi thành công đó vẫn nằm trong transaction hiện tại cho đến khi ứng dụng COMMIT hoặc ROLLBACK.

Vì vậy, cần thiết kế transaction boundary riêng với batch boundary.

## 2. Khi nào nên dùng JDBC batching?

Batching phù hợp khi ứng dụng lặp lại cùng một câu DML với nhiều bộ dữ liệu.

### 2.1. Các tình huống phù hợp

- Import dữ liệu từ CSV hoặc file.
- Ghi hàng nghìn đơn hàng.
- Cập nhật trạng thái nhiều bản ghi.
- Ghi log nghiệp vụ theo lô.
- Đồng bộ dữ liệu từ hệ thống ngoài.
- Xóa dữ liệu theo danh sách khóa.
- Nạp dữ liệu staging bằng PreparedStatement.

### 2.2. Khi nào không nên batch?

- Chỉ có một hoặc vài lệnh DML.
- Các câu SQL hoàn toàn khác nhau và không thể gom hợp lý.
- Dữ liệu có thể xử lý bằng một câu SQL set-based duy nhất.
- Một batch giữ transaction quá lâu hoặc tạo lock/undo quá lớn.
- Lệnh cần trả ResultSet hoặc có semantics không phù hợp với batch.
- Ứng dụng cần xử lý từng kết quả ngay sau mỗi lệnh.

### 2.3. Set-based SQL thường tốt hơn loop batch

Nếu dữ liệu đã nằm trong database, một câu INSERT ... SELECT hoặc MERGE có thể tốt hơn việc đọc từng dòng lên Java rồi gửi lại.

Ví dụ, thay vì đọc hàng nghìn dòng rồi update từng dòng:

~~~sql
UPDATE app_order
SET status = 'EXPIRED'
WHERE status = 'PENDING'
  AND created_at < :cutoff_date;
~~~

Một câu UPDATE có thể xử lý toàn bộ tập dữ liệu ngay tại database, tránh chuyển dữ liệu qua ứng dụng.

**Quy tắc lựa chọn:** Nếu dữ liệu đã ở trong Oracle và có thể mô tả thao tác bằng một câu SQL set-based, hãy cân nhắc SQL đó trước. JDBC batching phù hợp khi ứng dụng có nhiều bộ dữ liệu riêng cần gửi tới database.

## 3. Standard JDBC batching hoạt động ra sao?

JDBC cung cấp các API chuẩn để thêm lệnh vào batch và thực thi batch.

### 3.1. Với Statement

Statement có thể thêm SQL text:

~~~java
try (Statement st = connection.createStatement()) {
    st.addBatch("UPDATE app_order SET status = 'READY' WHERE order_id = 1001");
    st.addBatch("UPDATE app_order SET status = 'READY' WHERE order_id = 1002");
    st.addBatch("DELETE FROM app_order_stage WHERE batch_id = 20");

    int[] counts = st.executeBatch();
}
~~~

Đây là API JDBC chuẩn, nhưng với Oracle JDBC driver, generic Statement không có true batching mang lại hiệu quả như PreparedStatement. Ngoài ra, SQL text được nối động có nguy cơ SQL injection và làm tăng parse overhead.

### 3.2. Với PreparedStatement

PreparedStatement dùng một SQL cố định với bind parameters:

~~~java
String sql =
    "UPDATE app_order SET status = ? WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "READY");
    ps.setLong(2, 1001L);
    ps.addBatch();

    ps.setString(1, "READY");
    ps.setLong(2, 1002L);
    ps.addBatch();

    int[] counts = ps.executeBatch();
}
~~~

Đây là hình thức được Oracle JDBC khuyến nghị cho standard update batching. Mỗi lần gọi addBatch ghi nhận một bộ giá trị bind cho cùng SQL.

### 3.3. Chu trình chuẩn

~~~text
prepareStatement(sql)
        |
        v
set parameter values
        |
        v
addBatch()
        |
        v
set next parameter values
        |
        v
addBatch()
        |
        v
... repeat ...
        |
        v
executeBatch()
        |
        v
inspect update counts
        |
        v
commit or rollback transaction
~~~

### 3.4. Các method chính

| API | Mục đích |
| --- | --- |
| addBatch() | Thêm bộ bind hiện tại của PreparedStatement vào batch |
| addBatch(String sql) | Thêm SQL text vào batch của Statement |
| executeBatch() | Gửi batch và trả int[] update counts |
| clearBatch() | Xóa các lệnh đang chờ trong batch |
| executeLargeBatch() | Thực thi batch và trả long[] update counts nếu driver hỗ trợ |
| getUpdateCounts() | Đọc kết quả của các lệnh đã thực thi khi BatchUpdateException xảy ra |
| getLargeUpdateCounts() | Đọc update counts kiểu long từ BatchUpdateException |

### 3.5. Không gọi executeUpdate sau mỗi addBatch

Nếu gọi executeUpdate trong vòng lặp, từng DML được thực thi riêng. Muốn gom batch, phải gọi addBatch cho mỗi bộ dữ liệu và gọi executeBatch khi đạt batch size.

## 4. Vì sao nên dùng PreparedStatement?

Oracle JDBC driver tối ưu standard batching cho PreparedStatement.

### 4.1. Cùng một SQL, nhiều bộ bind

~~~java
String sql =
    "INSERT INTO employee_stage(employee_id, department_id, salary) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (EmployeeRow row : employeeRows) {
        ps.setLong(1, row.employeeId());
        ps.setInt(2, row.departmentId());
        ps.setBigDecimal(3, row.salary());
        ps.addBatch();
    }

    ps.executeBatch();
}
~~~

SQL được prepare một lần. Mỗi lần addBatch thêm bộ bind values tiếp theo.

### 4.2. Parameter phải được gán cho mỗi record

Không bỏ qua parameter chỉ vì giá trị giống record trước. Hãy set đầy đủ các placeholder cho mỗi record:

~~~java
ps.setLong(1, row.employeeId());
ps.setInt(2, row.departmentId());
ps.setBigDecimal(3, row.salary());
ps.addBatch();
~~~

Nếu parameter không được gán lại, giá trị cũ có thể bị giữ lại tùy trạng thái PreparedStatement. Việc set đầy đủ giúp tránh ghi nhầm dữ liệu.

### 4.3. Dùng setNull cho giá trị NULL

~~~java
if (row.managerId() == null) {
    ps.setNull(4, Types.NUMERIC);
} else {
    ps.setLong(4, row.managerId());
}
~~~

Đừng truyền chuỗi "NULL" thay cho SQL NULL.

### 4.4. Không nối dữ liệu vào SQL

Không nên:

~~~java
String sql =
    "INSERT INTO app_user(user_name) VALUES ('" + userName + "')";
~~~

Nên:

~~~java
String sql = "INSERT INTO app_user(user_name) VALUES (?)";
PreparedStatement ps = connection.prepareStatement(sql);
ps.setString(1, userName);
~~~

Bind parameters giúp tránh SQL injection và hỗ trợ statement reuse.

## 5. Oracle JDBC: standard batching và proprietary batching

Đây là điểm riêng của Oracle cần nắm rõ khi nâng cấp driver.

### 5.1. Oracle-specific update batching cũ

Oracle từng cung cấp proprietary update batching qua các API/thuộc tính riêng của Oracle JDBC, ví dụ cấu hình execute batch size trên OraclePreparedStatement.

Oracle update batching đã bị deprecated từ Oracle Database 12c Release 1 (12.1). Từ Oracle Database 12c Release 2 (12.2), tính năng proprietary này là no-op: batch size được chỉ định không có hiệu lực và ứng dụng có thể quay về thực hiện từng dòng.

### 5.2. Dùng standard JDBC batching

Oracle khuyến nghị dùng API JDBC chuẩn:

- PreparedStatement.addBatch()
- PreparedStatement.executeBatch()
- PreparedStatement.clearBatch()

Không dựa vào proprietary setExecuteBatch hoặc các API cũ để tối ưu driver 12.2 trở lên.

### 5.3. Oracle JDBC có true batching cho loại statement nào?

Oracle JDBC hỗ trợ standard batching qua Statement, PreparedStatement và CallableStatement theo API JDBC, nhưng implementation không thực hiện true batching cho generic Statement và CallableStatement. Hiệu năng batching rõ rệt chủ yếu đạt được với PreparedStatement.

Oracle implementation có hỗ trợ CallableStatement batching khi không có OUT parameters theo phạm vi được tài liệu hóa, nhưng không nên kỳ vọng cùng lợi ích performance như PreparedStatement.

### 5.4. Bảng so sánh

| Cách dùng | Oracle JDBC 19c |
| --- | --- |
| PreparedStatement + addBatch/executeBatch | Lựa chọn được khuyến nghị; có batching thực sự |
| Statement + addBatch(String) | API chuẩn được hỗ trợ nhưng không có true batching như PreparedStatement |
| CallableStatement batching | Có giới hạn; không có true batching tương tự PreparedStatement |
| Oracle proprietary update batching | Deprecated từ 12.1; no-op từ 12.2 |

### 5.5. Kiểm tra driver

Có thể kiểm tra JDBC driver hỗ trợ batch updates:

~~~java
DatabaseMetaData meta = connection.getMetaData();

boolean supportsBatch = meta.supportsBatchUpdates();
System.out.println("Batch updates supported: " + supportsBatch);
~~~

Đây là kiểm tra capability chung của driver. Nó không bảo đảm mọi loại Statement đều có cùng hiệu năng hoặc semantics. Với Oracle, ưu tiên PreparedStatement.

## 6. Ví dụ INSERT batch cơ bản

Ví dụ dùng Java 8 trở lên, PreparedStatement và try-with-resources.

### 6.1. Model dữ liệu

~~~java
import java.math.BigDecimal;

public class OrderRow {
    private final long orderId;
    private final long customerId;
    private final BigDecimal amount;

    public OrderRow(long orderId, long customerId, BigDecimal amount) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.amount = amount;
    }

    public long getOrderId() {
        return orderId;
    }

    public long getCustomerId() {
        return customerId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

### 6.2. Batch INSERT

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

public class OrderBatchWriter {
    public int[] insertOrders(
            Connection connection,
            List<OrderRow> rows) throws SQLException {

        String sql =
            "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            for (OrderRow row : rows) {
                ps.setLong(1, row.getOrderId());
                ps.setLong(2, row.getCustomerId());
                ps.setBigDecimal(3, row.getAmount());
                ps.addBatch();
            }

            return ps.executeBatch();
        }
    }
}
~~~

Method này chỉ thực hiện batch. Transaction commit/rollback do caller quản lý. Tách transaction ownership ra khỏi repository/helper giúp tránh commit ngoài ý muốn khi method được gọi trong transaction lớn hơn.

## 7. Quản lý transaction khi batch DML

Batch có thể thực thi thành công một phần rồi gặp lỗi. Nếu muốn kiểm soát kết quả, nên tắt auto-commit và quản lý transaction tường minh.

### 7.1. Auto-commit

Mặc định JDBC Connection thường bật auto-commit. Khi auto-commit bật, transaction được commit tự động theo quy tắc hoàn tất statement của JDBC driver.

Với batch DML, không nên dựa vào auto-commit nếu ứng dụng cần rollback các lệnh đã thực thi trước khi batch lỗi.

### 7.2. Tắt auto-commit

~~~java
connection.setAutoCommit(false);
~~~

Sau khi thực hiện batch thành công:

~~~java
connection.commit();
~~~

Khi có lỗi:

~~~java
connection.rollback();
~~~

### 7.3. Ví dụ transaction đầy đủ

~~~java
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

public class OrderBatchService {
    public void insertOrders(
            Connection connection,
            List<OrderRow> rows) throws SQLException {

        String sql =
            "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

        boolean originalAutoCommit = connection.getAutoCommit();

        try {
            connection.setAutoCommit(false);

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                for (OrderRow row : rows) {
                    ps.setLong(1, row.getOrderId());
                    ps.setLong(2, row.getCustomerId());
                    ps.setBigDecimal(3, row.getAmount());
                    ps.addBatch();
                }

                int[] counts = ps.executeBatch();
                System.out.println("Batch commands: " + counts.length);
            }

            connection.commit();

        } catch (BatchUpdateException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }

            logBatchFailure(e);
            throw e;

        } catch (SQLException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }

            throw e;

        } finally {
            connection.setAutoCommit(originalAutoCommit);
        }
    }

    private void logBatchFailure(BatchUpdateException e) {
        System.err.println("Batch failed: " + e.getMessage());
        System.err.println("SQLState: " + e.getSQLState());
        System.err.println("Vendor code: " + e.getErrorCode());
    }
}
~~~

Ví dụ trên giả định method sở hữu transaction trên connection. Nếu connection đã tham gia transaction do service/caller quản lý, không tự ý set auto-commit, commit hoặc rollback toàn bộ connection bên trong repository method.

### 7.4. Rollback tác động đến transaction hiện tại

connection.rollback() rollback toàn bộ thay đổi chưa commit trong transaction, không chỉ những câu lệnh thuộc batch vừa lỗi.

Nếu trước batch đã có các DML khác chưa commit, chúng cũng bị rollback. Hãy đặt transaction boundary đúng ở tầng service.

### 7.5. Savepoint nếu cần rollback một phần

Nếu transaction có công việc trước batch và chỉ muốn hủy phần DML từ batch trở đi:

~~~java
Savepoint beforeBatch = connection.setSavepoint();

try {
    ps.executeBatch();
} catch (BatchUpdateException e) {
    connection.rollback(beforeBatch);
    throw e;
}
~~~

Savepoint chỉ có ý nghĩa khi auto-commit tắt và database/driver hỗ trợ. Nó không thay thế transaction design rõ ràng.

## 8. Batch size và transaction chunk size

Batch size là số lệnh được thêm trước mỗi executeBatch. Transaction chunk size là số bản ghi được commit trong một transaction. Hai giá trị có thể giống hoặc khác nhau.

### 8.1. Batch size quá nhỏ

Nếu batch chỉ có một hoặc hai lệnh, lợi ích giảm round trips có thể không đáng kể.

### 8.2. Batch size quá lớn

Batch rất lớn có thể:

- Tăng memory sử dụng ở Java client và JDBC driver.
- Tăng kích thước buffer.
- Tăng thời gian chờ trước khi batch được gửi.
- Tăng lượng công việc thực thi trong một lần.
- Làm lỗi khó cô lập và retry.
- Tạo áp lực undo, redo, locks và transaction duration nếu commit quá thưa.

### 8.3. Oracle khuyến nghị batch size khoảng 100 hoặc thấp hơn

Oracle JDBC 19c coding tips khuyến nghị giữ batch sizes trong khoảng 100 hoặc ít hơn. Batch lớn hơn thường ít hoặc không đem lại thêm cải thiện và có thể làm hiệu năng giảm do tài nguyên client cần để xử lý batch.

Đây là điểm khởi đầu, không phải giới hạn cứng. Hãy đo trên workload, schema, network và driver thật.

### 8.4. Bắt đầu bằng giá trị thực nghiệm

Có thể benchmark:

| Batch size | Mục đích |
| ---: | --- |
| 10 | Baseline nhỏ |
| 25 | Kiểm tra mức giảm round trips |
| 50 | Batch trung bình |
| 100 | Mốc Oracle khuyến nghị để bắt đầu |
| 200 | Kiểm tra xem batch lớn hơn có lợi không |

Không chọn batch size chỉ theo số lượng dòng. Độ rộng row, LOB, network, driver và transaction behavior đều ảnh hưởng.

### 8.5. Ví dụ xử lý theo chunk

~~~java
private static final int BATCH_SIZE = 100;

public void insertInChunks(
        Connection connection,
        List<OrderRow> rows) throws SQLException {

    String sql =
        "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        int pending = 0;

        for (OrderRow row : rows) {
            ps.setLong(1, row.getOrderId());
            ps.setLong(2, row.getCustomerId());
            ps.setBigDecimal(3, row.getAmount());
            ps.addBatch();
            pending++;

            if (pending == BATCH_SIZE) {
                ps.executeBatch();
                connection.commit();
                ps.clearBatch();
                pending = 0;
            }
        }

        if (pending > 0) {
            ps.executeBatch();
            connection.commit();
            ps.clearBatch();
        }
    }
}
~~~

Đoạn code này yêu cầu auto-commit đã được tắt và method được quyền commit transaction. Trong ứng dụng thực tế cần thêm rollback khi lỗi và tránh commit trong repository nếu transaction thuộc quyền sở hữu của service.

### 8.6. Batch size khác transaction size

Ví dụ:

~~~text
Transaction gồm 1.000 rows
    Batch 1: 100 rows -> executeBatch
    Batch 2: 100 rows -> executeBatch
    ...
    Batch 10: 100 rows -> executeBatch
    COMMIT
~~~

Mười lần executeBatch vẫn nằm trong cùng transaction nếu không commit giữa các batch.

Hoặc:

~~~text
Chunk 1: 1.000 rows -> 10 batches -> COMMIT
Chunk 2: 1.000 rows -> 10 batches -> COMMIT
Chunk 3: 1.000 rows -> 10 batches -> COMMIT
~~~

Commit mỗi chunk làm transaction ngắn hơn nhưng job không còn atomic trên toàn bộ tập dữ liệu. Cần thiết kế restart/checkpoint.

## 9. Update counts sau executeBatch

executeBatch trả int[]; mỗi phần tử tương ứng với một lệnh được thêm theo thứ tự addBatch.

### 9.1. Giá trị không âm

Một số nguyên từ 0 trở lên biểu thị số rows bị ảnh hưởng bởi lệnh đó.

Ví dụ:

~~~java
int[] counts = ps.executeBatch();

for (int count : counts) {
    System.out.println("Rows affected: " + count);
}
~~~

UPDATE có thể trả 0 nếu WHERE không tìm thấy dòng. Điều này không nhất thiết là lỗi SQL.

### 9.2. SUCCESS_NO_INFO

Statement.SUCCESS_NO_INFO có giá trị -2. Nó biểu thị command thực thi thành công nhưng driver không biết số rows bị ảnh hưởng.

Không diễn giải -2 là zero rows.

### 9.3. EXECUTE_FAILED

Statement.EXECUTE_FAILED có giá trị -3. Nó biểu thị command thất bại trong trường hợp driver tiếp tục xử lý các lệnh sau lỗi.

Một driver dừng tại lỗi có thể chỉ trả counts của các lệnh thành công trước lỗi và không có phần tử EXECUTE_FAILED cho lệnh lỗi.

### 9.4. Bảng update counts

| Giá trị | Ý nghĩa |
| ---: | --- |
| 0 hoặc số dương | Số rows bị ảnh hưởng |
| -2 / SUCCESS_NO_INFO | Thành công, số rows không xác định |
| -3 / EXECUTE_FAILED | Lệnh thất bại; chỉ xuất hiện nếu driver tiếp tục sau lỗi |

### 9.5. Không giả định update count bằng số dòng input

Với UPDATE hoặc DELETE, một input record có thể ảnh hưởng:

- 0 rows: không có dòng phù hợp.
- 1 row: đúng một dòng.
- Nhiều rows: điều kiện WHERE khớp nhiều dòng.
- SUCCESS_NO_INFO: driver không cung cấp số lượng.

Nếu nghiệp vụ yêu cầu đúng một dòng, cần kiểm tra count và áp dụng policy phù hợp.

## 10. BatchUpdateException là gì?

BatchUpdateException là subclass của SQLException. JDBC ném exception này khi một command trong batch không thực thi thành công.

### 10.1. Thông tin có thể lấy

- getMessage(): thông báo lỗi.
- getSQLState(): SQLState.
- getErrorCode(): vendor-specific error code, ví dụ mã Oracle.
- getUpdateCounts(): update counts kiểu int.
- getLargeUpdateCounts(): update counts kiểu long.
- getNextException(): SQLException tiếp theo trong exception chain.
- getCause(): nguyên nhân gốc nếu có.

### 10.2. JDBC cho phép hai cách xử lý sau lỗi

Theo JDBC contract, driver có thể:

1. Dừng xử lý ngay khi gặp command lỗi.
2. Tiếp tục xử lý các command còn lại sau khi một command lỗi.

Behavior phải nhất quán với một DBMS/driver implementation.

Nếu driver dừng:

- Update counts chứa kết quả của các command thực thi thành công trước lỗi.
- Array thường ngắn hơn batch ban đầu.

Nếu driver tiếp tục:

- Array có một phần tử cho mỗi command.
- Command lỗi có thể được đánh dấu EXECUTE_FAILED.
- Command thành công nhưng không biết số rows có thể là SUCCESS_NO_INFO.

### 10.3. Hành vi Oracle JDBC standard batching

Với Oracle JDBC standard batching được mô tả trong Oracle Database 19c JDBC Developer's Guide:

- Nếu một operation trong batch lỗi hoặc cố trả ResultSet trong executeBatch, quá trình xử lý dừng.
- BatchUpdateException được ném.
- Update counts chứa số lần thực thi thành công trước khi lỗi.
- Nếu batch có 5 records và lỗi ở record thứ 4, update counts có 3 phần tử đại diện cho 3 records đầu đã thực thi thành công.
- Các lệnh sau record lỗi không được thực thi trong batch đó.

Đây là hành vi Oracle JDBC cụ thể. Code portable vẫn nên đọc update counts và không hard-code giả định mọi JDBC driver đều dừng giống Oracle.

### 10.4. Update counts không có nghĩa dữ liệu đã commit

Update count chỉ phản ánh lệnh đã được thực thi trong transaction. Nếu auto-commit tắt, các thay đổi vẫn có thể bị rollback. Chỉ sau commit thành công mới có thể xem thay đổi là đã commit.

## 11. Đọc BatchUpdateException đúng cách

### 11.1. Ví dụ bắt exception

~~~java
try {
    int[] counts = ps.executeBatch();
    System.out.println("Success commands: " + counts.length);

} catch (BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();

    System.err.println("Batch failed: " + e.getMessage());
    System.err.println("SQLState: " + e.getSQLState());
    System.err.println("Oracle/vendor code: " + e.getErrorCode());
    System.err.println("Reported counts: " + counts.length);

    for (int i = 0; i < counts.length; i++) {
        System.err.println("Command " + i + " count=" + counts[i]);
    }

    throw e;
}
~~~

### 11.2. Xử lý JDBC driver có thể tiếp tục hoặc dừng

~~~java
int[] counts = e.getUpdateCounts();

for (int i = 0; i < counts.length; i++) {
    int count = counts[i];

    if (count == Statement.EXECUTE_FAILED) {
        System.err.println("Command " + i + " failed");
    } else if (count == Statement.SUCCESS_NO_INFO) {
        System.out.println("Command " + i + " succeeded; row count unknown");
    } else {
        System.out.println(
            "Command " + i + " affected " + count + " rows"
        );
    }
}
~~~

Nếu driver dừng, array có thể chỉ chứa prefix các lệnh thành công. Không được coi phần tử cuối của array là lệnh lỗi; nó có thể là lệnh thành công cuối cùng trước lệnh lỗi.

### 11.3. Tìm exception chain

~~~java
SQLException next = e.getNextException();

while (next != null) {
    System.err.println("Chained SQL error: " + next.getMessage());
    System.err.println("SQLState: " + next.getSQLState());
    System.err.println("Vendor code: " + next.getErrorCode());
    next = next.getNextException();
}
~~~

Oracle errors thường có mã vendor riêng, ví dụ:

- ORA-00001: unique constraint violated.
- ORA-01400: cannot insert NULL.
- ORA-02291: parent key not found.
- ORA-02292: child record found.
- ORA-12899: value too large for column.

Đọc cả message và exception chain để tìm nguyên nhân thực tế.

## 12. Mapping update counts với input records

Khi batch được tạo từ một List, ứng dụng thường cần biết record input nào đã được thực thi.

### 12.1. Lưu thứ tự input

~~~java
List<OrderRow> batchRows = new ArrayList<>();

for (OrderRow row : inputRows) {
    ps.setLong(1, row.getOrderId());
    ps.setLong(2, row.getCustomerId());
    ps.setBigDecimal(3, row.getAmount());
    ps.addBatch();
    batchRows.add(row);
}
~~~

### 12.2. Mapping khi executeBatch thành công

Khi thành công, số update counts theo thứ tự các lệnh addBatch:

~~~java
int[] counts = ps.executeBatch();

for (int i = 0; i < counts.length; i++) {
    OrderRow row = batchRows.get(i);
    System.out.println(
        "orderId=" + row.getOrderId() +
        ", updateCount=" + counts[i]
    );
}
~~~

### 12.3. Mapping khi Oracle driver dừng tại lỗi

Với Oracle JDBC behavior, nếu exception counts có 3 phần tử thì 3 lệnh đầu đã thực thi thành công; command tiếp theo trong batch là vị trí lỗi theo thứ tự addBatch. Các lệnh sau đó chưa được thực thi.

Ví dụ batch 5 records:

| Input index | Order ID | Kết quả |
| ---: | ---: | --- |
| 0 | 1001 | Thành công |
| 1 | 1002 | Thành công |
| 2 | 1003 | Thành công |
| 3 | 1004 | Lỗi |
| 4 | 1005 | Chưa chạy |

Trong trường hợp này, getUpdateCounts() của Oracle JDBC có thể chứa ba phần tử tương ứng 1001, 1002 và 1003.

Đừng áp dụng giả định này cho driver khác nếu chưa đọc documentation của driver đó.

### 12.4. Không dùng counts để quyết định commit một cách mù quáng

Một số command đã chạy không có nghĩa transaction nên commit một phần. Quyết định commit/rollback phải dựa trên business atomicity:

- Nếu batch là một đơn vị nghiệp vụ nguyên tử, rollback cả transaction.
- Nếu mỗi record độc lập và chấp nhận partial success, commit theo chunk và ghi checkpoint.
- Nếu cần tiếp tục các record hợp lệ, tách record lỗi ra xử lý riêng sau khi transaction được khôi phục theo policy.

## 13. Mẫu xử lý lỗi có rollback

Đây là pattern phù hợp khi cả batch là một đơn vị transaction: nếu bất kỳ lệnh nào lỗi, rollback toàn bộ thay đổi chưa commit.

~~~java
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

public class AtomicBatchWriter {
    public void write(
            Connection connection,
            List<OrderRow> rows) throws SQLException {

        String sql =
            "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

        boolean originalAutoCommit = connection.getAutoCommit();

        try {
            connection.setAutoCommit(false);

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                for (OrderRow row : rows) {
                    ps.setLong(1, row.getOrderId());
                    ps.setLong(2, row.getCustomerId());
                    ps.setBigDecimal(3, row.getAmount());
                    ps.addBatch();
                }

                int[] counts = ps.executeBatch();
                logCounts(counts);
            }

            connection.commit();

        } catch (BatchUpdateException e) {
            rollbackPreservingOriginal(connection, e);
            logBatchException(e);
            throw e;

        } catch (SQLException e) {
            rollbackPreservingOriginal(connection, e);
            throw e;

        } finally {
            connection.setAutoCommit(originalAutoCommit);
        }
    }

    private void rollbackPreservingOriginal(
            Connection connection,
            SQLException original) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            original.addSuppressed(rollbackError);
        }
    }

    private void logCounts(int[] counts) {
        for (int i = 0; i < counts.length; i++) {
            System.out.println("index=" + i + ", count=" + counts[i]);
        }
    }

    private void logBatchException(BatchUpdateException e) {
        System.err.println(e.getMessage());
        System.err.println("SQLState=" + e.getSQLState());
        System.err.println("VendorCode=" + e.getErrorCode());

        int[] counts = e.getUpdateCounts();
        System.err.println("Successful/reported commands=" + counts.length);
    }
}
~~~

Đây là ví dụ transaction-owning service. Trong hệ thống có transaction manager hoặc Spring-managed transaction, không tự set auto-commit và commit/rollback trực tiếp trong repository.

## 14. Partial success và retry

Một batch có thể thực thi một phần trước khi lỗi. Đây là nơi ứng dụng cần có chính sách retry rõ ràng.

### 14.1. Không retry cả batch một cách mù quáng

Giả sử:

- Batch có 100 records.
- 35 records đã thực thi.
- Record thứ 36 gặp unique constraint violation.
- 64 records còn lại chưa thực thi trên Oracle JDBC.

Nếu ứng dụng gửi lại cả 100 records mà không rollback transaction hoặc không có idempotency, các record đầu có thể bị insert trùng.

### 14.2. Nếu rollback toàn transaction

Khi auto-commit tắt và rollback thành công:

- Các DML đã thực thi trong transaction hiện tại bị rollback.
- Có thể sửa dữ liệu lỗi và retry transaction.
- Các transaction đã commit trước đó (nếu có chunk commits) vẫn tồn tại.

### 14.3. Nếu commit theo chunk

Ví dụ 10.000 rows, chunk 100:

~~~text
Chunk 1 -> execute -> commit
Chunk 2 -> execute -> commit
Chunk 3 -> error -> rollback current chunk
Chunk 4..N -> chưa chạy
~~~

Khi đó 200 rows của hai chunk đầu đã commit. Retry phải bắt đầu từ checkpoint sau chunk 2 hoặc phải dùng cơ chế upsert/idempotency.

### 14.4. Idempotency

Một thao tác idempotent có thể được thực hiện lại mà không tạo kết quả sai hoặc duplicate.

Các cách hỗ trợ:

- Business key duy nhất có unique constraint.
- Import batch ID và source record ID.
- Staging table có trạng thái xử lý.
- MERGE theo khóa nghiệp vụ.
- Checkpoint đã commit.
- Transaction log ghi rõ batch/chunk nào đã hoàn tất.

### 14.5. Không suy luận commit từ update counts

Nếu kết nối bị đứt ngay sau khi client gửi COMMIT, client có thể không biết database đã commit hay chưa. Update counts trước đó không giải quyết được transaction outcome ambiguity.

Khi retry sau lỗi kết nối, phải đối chiếu transaction/business key hoặc checkpoint trên database. Không gửi lại dữ liệu một cách mù quáng.

## 15. Savepoint và xử lý record lỗi riêng lẻ

Nếu yêu cầu nghiệp vụ cho phép giữ các công việc trước batch nhưng rollback phần batch hiện tại, dùng savepoint.

### 15.1. Ví dụ

~~~java
Savepoint beforeBatch = connection.setSavepoint();

try {
    ps.executeBatch();
    connection.releaseSavepoint(beforeBatch);
} catch (BatchUpdateException e) {
    connection.rollback(beforeBatch);
    throw e;
}
~~~

Rollback savepoint sẽ hoàn tác thay đổi kể từ savepoint, giữ lại thay đổi trước đó trong cùng transaction.

### 15.2. Tách record lỗi

Một chiến lược khác:

1. Thử batch.
2. Nếu lỗi, rollback batch/chunk.
3. Xác định record lỗi bằng update counts và Oracle error.
4. Ghi record lỗi vào reject table hoặc file.
5. Chạy lại các record hợp lệ theo batch mới.

Không tự động thực hiện chiến lược này nếu lỗi không phải lỗi dữ liệu. Lỗi network, deadlock, tablespace full hoặc database unavailable không nên bị phân loại thành record lỗi đơn lẻ.

### 15.3. Batch nhỏ hơn để cô lập lỗi

Nếu dữ liệu đầu vào có thể chứa record lỗi bất thường, batch size nhỏ hơn giúp giảm phạm vi cần điều tra. Đổi lại sẽ tăng số lần executeBatch và network round trips.

Có thể dùng chiến lược chia đôi batch để tìm record lỗi trong một tập lớn, nhưng phải kiểm soát transaction và tính idempotent của DML.

## 16. Dùng executeLargeBatch

JDBC 4.2 bổ sung executeLargeBatch và getLargeUpdateCounts để trả update counts kiểu long.

### 16.1. Khi nào cần?

Nếu một command có thể ảnh hưởng hơn Integer.MAX_VALUE rows, int update count không đủ để biểu diễn chính xác.

### 16.2. Ví dụ

~~~java
long[] counts = ps.executeLargeBatch();

for (long count : counts) {
    System.out.println("Rows affected: " + count);
}
~~~

### 16.3. Xử lý exception

~~~java
try {
    long[] counts = ps.executeLargeBatch();
} catch (BatchUpdateException e) {
    long[] counts = e.getLargeUpdateCounts();
    System.err.println("Reported commands: " + counts.length);
}
~~~

### 16.4. Kiểm tra driver support

executeLargeBatch là method của JDBC API hiện đại, nhưng driver/version phải hỗ trợ phù hợp. Nếu ứng dụng dùng Oracle JDBC driver cũ, hãy kiểm tra JDBC compliance và tài liệu driver trước khi chuyển sang API này.

## 17. Batch INSERT với Oracle sequence

Oracle thường dùng sequence để sinh khóa chính.

### 17.1. Dùng sequence trong SQL

~~~java
String sql =
    "INSERT INTO app_order(order_id, customer_id, amount) " +
    "VALUES (app_order_seq.NEXTVAL, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderRow row : rows) {
        ps.setLong(1, row.getCustomerId());
        ps.setBigDecimal(2, row.getAmount());
        ps.addBatch();
    }

    ps.executeBatch();
}
~~~

### 17.2. Sequence có thể có khoảng trống

Sequence không bảo đảm giá trị liên tiếp không có khoảng trống. Rollback, cache, instance failure hoặc concurrent sessions có thể khiến sequence values bị bỏ qua.

Không dùng sequence để tạo số thứ tự nghiệp vụ bắt buộc liên tục tuyệt đối.

### 17.3. Cần biết generated ID?

Nếu ứng dụng cần mapping ID được sinh cho từng input row:

- Có thể cấp sequence values trước khi addBatch.
- Có thể dùng một cơ chế key generation riêng.
- Có thể lưu source key cùng ID trong staging table.
- Phải kiểm tra khả năng batch generated keys của Oracle JDBC driver/version.

Không giả định mọi driver trả generated keys theo batch với semantics giống nhau. Kiểm thử driver cụ thể trước khi thiết kế phụ thuộc vào thứ tự generated keys.

## 18. Batch UPDATE và DELETE

### 18.1. Batch UPDATE

~~~java
String sql =
    "UPDATE app_order SET status = ? WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderStatusChange change : changes) {
        ps.setString(1, change.status());
        ps.setLong(2, change.orderId());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

### 18.2. Batch DELETE

~~~java
String sql = "DELETE FROM app_order_stage WHERE stage_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (Long stageId : stageIds) {
        ps.setLong(1, stageId);
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

### 18.3. UPDATE count bằng 0

Nếu update count là 0, có thể:

- Record không tồn tại.
- WHERE condition không khớp.
- Record đã được xử lý trước đó.

Đây có thể là kết quả hợp lệ hoặc lỗi nghiệp vụ tùy yêu cầu. Ứng dụng phải định nghĩa rõ.

### 18.4. Optimistic locking

Có thể dùng version column:

~~~sql
UPDATE app_order
SET status = ?, version_no = version_no + 1
WHERE order_id = ?
  AND version_no = ?
~~~

Nếu update count là 0, dữ liệu đã thay đổi hoặc record không tồn tại. Batching không loại bỏ optimistic locking; nó chỉ gom việc gửi các lệnh.

## 19. Batch và các ràng buộc Oracle

Batch DML vẫn tuân theo database constraints, triggers, indexes và transaction rules.

### 19.1. Constraints

Các lỗi thường gặp:

- Unique constraint.
- Foreign key.
- NOT NULL.
- CHECK constraint.
- Data length/precision overflow.

Batch không bỏ qua validation của database.

### 19.2. Triggers

Trigger vẫn chạy theo từng DML row/statement tùy loại trigger. Batch không có nghĩa trigger chỉ chạy một lần cho toàn bộ batch.

### 19.3. Indexes

Mỗi INSERT/UPDATE/DELETE vẫn phải duy trì các index liên quan. Nếu nạp lượng dữ liệu rất lớn, index maintenance có thể chiếm nhiều thời gian hơn chi phí round trips.

### 19.4. Undo và redo

DML vẫn tạo undo/redo theo semantics của database. Batching không làm DML trở thành NOLOGGING và không loại bỏ transaction logging.

### 19.5. Locks

Nếu commit quá thưa, row locks có thể được giữ lâu hơn. Điều này có thể ảnh hưởng transaction khác và gây contention.

## 20. Batch DML và bulk processing trong Oracle

JDBC batching chỉ là một trong nhiều cách nạp dữ liệu.

### 20.1. JDBC standard batching

Phù hợp khi:

- Dữ liệu đến từ Java application.
- Cùng SQL được thực hiện với nhiều bind values.
- Muốn giảm network round trips.
- Cần kiểm soát transaction từ Java.

### 20.2. Set-based SQL

Phù hợp khi dữ liệu đã nằm trong database:

~~~sql
INSERT INTO app_order_archive(order_id, customer_id, amount)
SELECT order_id, customer_id, amount
FROM app_order
WHERE created_at < :cutoff_date;
~~~

Database xử lý tập dữ liệu tại chỗ, tránh chuyển rows qua Java.

### 20.3. PL/SQL FORALL

FORALL là bulk DML trong PL/SQL. Nó cho phép PL/SQL bind nhiều phần tử collection vào một DML statement, giảm context switches giữa PL/SQL và SQL engine.

Ví dụ khái niệm:

~~~sql
DECLARE
    TYPE t_order_ids IS TABLE OF app_order.order_id%TYPE;
    l_ids t_order_ids := t_order_ids(1001, 1002, 1003);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE app_order
        SET status = 'READY'
        WHERE order_id = l_ids(i);
END;
/
~~~

FORALL phù hợp khi logic và collection đã nằm trong PL/SQL. Nó không phải JDBC API và không thay thế transaction boundary.

### 20.4. SAVE EXCEPTIONS trong FORALL

PL/SQL FORALL có SAVE EXCEPTIONS để tiếp tục xử lý các iteration khác và lưu lỗi trong SQL%BULK_EXCEPTIONS. Đây là cơ chế riêng của PL/SQL, khác BatchUpdateException của JDBC.

### 20.5. SQL*Loader và external tables

Với file lớn và hàng triệu bản ghi, SQL*Loader hoặc external tables có thể phù hợp hơn JDBC batching. Chúng cung cấp cơ chế load dữ liệu chuyên dụng, có thể hỗ trợ direct path và xử lý file hiệu quả.

### 20.6. So sánh

| Phương pháp | Dữ liệu đến từ | Điểm mạnh |
| --- | --- | --- |
| JDBC batching | Java application | Giảm round trips khi gửi nhiều bộ bind |
| Set-based SQL | Đã nằm trong database | Xử lý dữ liệu ngay tại database |
| PL/SQL FORALL | PL/SQL collections | Giảm context switches cho bulk DML |
| SQL*Loader | File ngoài database | Bulk load chuyên dụng |
| External tables | File được database đọc như table | Kết hợp SQL với dữ liệu file |

## 21. Hiệu năng và cách đo

Không kết luận batch nhanh hơn chỉ vì dùng executeBatch. Phải đo trên workload tương đương.

### 21.1. Các chỉ số nên ghi

- Tổng số rows input.
- Số rows commit thành công.
- Batch size.
- Transaction chunk size.
- Tổng thời gian.
- Rows per second.
- Số lần executeBatch.
- Số lần round trip nếu đo được.
- Client CPU và memory.
- Database CPU.
- Logical/physical reads.
- Redo/undo generation.
- Lock waits.
- Số lỗi và retry.

### 21.2. So sánh executeUpdate và executeBatch

Chạy cùng:

- Dataset.
- SQL.
- Bind values.
- Index/constraints.
- Transaction policy.
- Commit frequency.
- Network path.

Chỉ thay cách gửi DML để kết quả có thể so sánh.

### 21.3. Đo elapsed time trong Java

~~~java
long start = System.nanoTime();

int[] counts = ps.executeBatch();

long elapsedNanos = System.nanoTime() - start;
double elapsedMillis = elapsedNanos / 1_000_000.0;

System.out.println("Batch elapsed ms: " + elapsedMillis);
System.out.println("Commands: " + counts.length);
~~~

Để đo toàn job, bắt đầu timer trước khi đọc input và kết thúc sau khi commit cuối cùng.

### 21.4. Warm-up và nhiều lần chạy

Một lần chạy có thể bị ảnh hưởng bởi:

- Cold cache.
- JIT compilation.
- Network fluctuation.
- Concurrent workloads.
- Parse/statement cache.
- Storage cache.

Chạy nhiều lần, phân biệt warm-up với steady state và báo cáo median/percentile nếu cần.

### 21.5. Không tăng batch size vô hạn

Batch size lớn hơn có thể giảm số lần executeBatch nhưng tăng memory và độ trễ trước khi gửi. Hãy đo throughput và memory đồng thời.

## 22. Troubleshooting

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Batch không nhanh hơn executeUpdate | Dùng Statement hoặc CallableStatement trên Oracle | Dùng PreparedStatement standard batching |
| Batch size cấu hình nhưng vẫn từng dòng | Dùng proprietary Oracle batching trên driver 12.2+ | Chuyển sang addBatch/executeBatch |
| BatchUpdateException | Một command lỗi hoặc cố trả ResultSet | Đọc message, vendor code, update counts và exception chain |
| ORA-00001 | Duplicate key trong batch | Kiểm tra input key, unique constraint và retry policy |
| ORA-01400 | Giá trị NULL cho cột NOT NULL | Validate input hoặc set giá trị hợp lệ |
| ORA-02291 | Foreign key không tìm thấy parent | Đảm bảo parent tồn tại hoặc đúng thứ tự load |
| ORA-12899 | Giá trị quá dài | Kiểm tra độ dài/encoding và schema |
| ORA-00060 | Deadlock | Kiểm tra thứ tự cập nhật, transaction concurrency và retry có backoff |
| OutOfMemoryError | Batch quá lớn hoặc giữ input/result quá nhiều | Giảm batch/chunk size và stream dữ liệu |
| Undo tablespace pressure | Transaction quá dài hoặc commit quá thưa | Chọn transaction chunk size phù hợp |
| Lock contention | Nhiều transaction cập nhật cùng rows | Giảm transaction duration, chuẩn hóa thứ tự khóa |
| Retry tạo duplicate rows | Không có idempotency hoặc transaction outcome chưa rõ | Dùng business key/checkpoint và đối chiếu trước retry |
| Counts array ngắn hơn batch | Driver dừng tại lệnh lỗi | Xác định prefix thành công và vị trí lỗi theo driver behavior |
| EXECUTE_FAILED xuất hiện | Driver tiếp tục sau command lỗi | Đọc từng phần tử và xử lý theo JDBC contract |
| executeLargeBatch không hoạt động | Driver/JDBC version không hỗ trợ | Kiểm tra driver version và JDBC capability |

## 23. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Batch là một SQL statement duy nhất | Batch là nhóm command được gửi/thực thi theo API batching |
| Batch luôn chạy song song | Không; batching chủ yếu giảm round trips và overhead |
| Batch luôn commit toàn bộ hoặc không gì cả | Không; command có thể đã thực thi một phần trước lỗi |
| executeBatch tự commit | Transaction behavior phụ thuộc auto-commit và driver |
| SUCCESS_NO_INFO nghĩa là 0 rows | Nó nghĩa là thành công nhưng không biết số rows |
| EXECUTE_FAILED luôn xuất hiện khi có lỗi | Chỉ xuất hiện khi driver tiếp tục xử lý sau lỗi |
| BatchUpdateException luôn có counts cho toàn batch | Array có thể chỉ chứa prefix command thành công |
| Oracle JDBC tiếp tục sau lỗi như mọi driver | Oracle standard batching dừng tại command lỗi theo tài liệu 19c |
| Update counts nghĩa dữ liệu đã commit | Counts chỉ xác nhận command đã thực thi; commit là bước riêng |
| Có thể retry toàn batch sau lỗi | Có nguy cơ duplicate nếu phần trước đã commit hoặc outcome chưa rõ |
| Batch size càng lớn càng nhanh | Batch quá lớn có thể giảm performance và tăng memory |
| Statement batching có hiệu năng như PreparedStatement trên Oracle | Oracle true batching chủ yếu ở PreparedStatement |
| Oracle proprietary batching vẫn hoạt động ở driver mới | No-op từ 12.2 |
| JDBC batching thay thế FORALL | Hai cơ chế hoạt động ở các tầng khác nhau |
| Batch DML bỏ qua triggers/constraints | Mọi database rules vẫn được áp dụng |

## 24. Checklist triển khai batch DML

**Thiết kế SQL**

- DML có cùng cấu trúc và phù hợp PreparedStatement không?
- Có thể dùng một câu SQL set-based thay vì loop không?
- WHERE clause có index phù hợp không?
- Các bind parameters có được set đầy đủ mỗi record không?
- Có cần generated keys không?

**Driver và API**

- Oracle JDBC driver version đã xác định chưa?
- Có dùng standard addBatch/executeBatch không?
- Có tránh proprietary Oracle update batching không?
- Có kiểm tra supportsBatchUpdates không?
- Có dùng PreparedStatement cho performance không?

**Batch và transaction**

- Batch size đã benchmark chưa?
- Transaction chunk size đã xác định chưa?
- Auto-commit có được quản lý đúng không?
- Ai sở hữu commit/rollback?
- Có rollback khi BatchUpdateException không?
- Có checkpoint khi commit theo chunk không?

**Error handling**

- Đã đọc getUpdateCounts/getLargeUpdateCounts chưa?
- Có xử lý SUCCESS_NO_INFO và EXECUTE_FAILED không?
- Có đọc SQLState, vendor code và nextException không?
- Có mapping counts với input order không?
- Retry có idempotent không?
- Có xử lý unknown commit outcome không?

**Vận hành**

- Có log batch ID, chunk ID và số rows?
- Có metric elapsed time/throughput?
- Có giới hạn memory và input buffering?
- Có kiểm soát undo/redo/locks?
- Có kiểm thử với constraint errors và network errors?

## 25. Bài thực hành tổng hợp

Lab tạo bảng staging, insert nhiều rows bằng PreparedStatement batch, thử một lỗi unique constraint và đọc BatchUpdateException.

### Bước 1 — Tạo bảng

~~~sql
CREATE TABLE jdbc_batch_lab (
    id          NUMBER PRIMARY KEY,
    description VARCHAR2(100) NOT NULL,
    amount      NUMBER(12,2)
);
~~~

### Bước 2 — Tạo dữ liệu Java

~~~java
List<LabRow> rows = new ArrayList<>();

for (int i = 1; i <= 250; i++) {
    rows.add(new LabRow(
        i,
        "row-" + i,
        new BigDecimal(i).setScale(2)
    ));
}
~~~

### Bước 3 — Insert bằng PreparedStatement

~~~java
String sql =
    "INSERT INTO jdbc_batch_lab(id, description, amount) VALUES (?, ?, ?)";

connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    int pending = 0;

    for (LabRow row : rows) {
        ps.setInt(1, row.id());
        ps.setString(2, row.description());
        ps.setBigDecimal(3, row.amount());
        ps.addBatch();
        pending++;

        if (pending == 100) {
            int[] counts = ps.executeBatch();
            System.out.println("Executed commands: " + counts.length);
            ps.clearBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        int[] counts = ps.executeBatch();
        System.out.println("Final commands: " + counts.length);
        ps.clearBatch();
    }

    connection.commit();

} catch (BatchUpdateException e) {
    connection.rollback();

    System.err.println("Batch error: " + e.getMessage());
    System.err.println("Oracle error code: " + e.getErrorCode());

    int[] counts = e.getUpdateCounts();
    System.err.println("Reported update counts: " + counts.length);

    throw e;
}
~~~

Đoạn lab trên minh họa một transaction duy nhất gồm nhiều batches. Nếu bất kỳ batch nào lỗi, rollback toàn bộ transaction chưa commit.

### Bước 4 — Kiểm tra dữ liệu

~~~sql
SELECT COUNT(*) AS total_rows
FROM jdbc_batch_lab;

SELECT MIN(id), MAX(id)
FROM jdbc_batch_lab;
~~~

### Bước 5 — Thử duplicate key

Thêm một input row có ID đã tồn tại:

~~~java
rows.add(new LabRow(
    1,
    "duplicate-row",
    new BigDecimal("999.00")
));
~~~

Chạy batch và quan sát BatchUpdateException.

### Bước 6 — Đọc update counts

~~~java
catch (BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();

    for (int i = 0; i < counts.length; i++) {
        int count = counts[i];

        if (count == Statement.EXECUTE_FAILED) {
            System.out.println("Failed command at index " + i);
        } else if (count == Statement.SUCCESS_NO_INFO) {
            System.out.println("Success, count unknown at index " + i);
        } else {
            System.out.println("Index " + i + " affected " + count);
        }
    }
}
~~~

Với Oracle JDBC, kiểm tra độ dài counts để xác định số command thành công trước lệnh lỗi theo behavior của driver.

### Bước 7 — So sánh batch size

Chạy lại lab với batch sizes:

- 10.
- 25.
- 50.
- 100.
- 200.

Ghi elapsed time, throughput và memory. Dùng cùng dữ liệu và transaction policy.

### Bước 8 — So sánh executeUpdate

Viết phiên bản vòng lặp executeUpdate với cùng SQL và bind values. So sánh thời gian với standard batching.

### Bước 9 — Kiểm tra rollback

Sau khi cố tình gây lỗi trong một transaction:

~~~sql
SELECT COUNT(*)
FROM jdbc_batch_lab;
~~~

Xác nhận rollback đã hoàn tác những thay đổi trong transaction chưa commit.

## 26. Câu hỏi tự kiểm tra

1. Batch DML là gì?
2. Batching giảm loại chi phí nào?
3. Batch có tự chạy song song không?
4. Vì sao PreparedStatement phù hợp với Oracle JDBC batching?
5. addBatch và executeBatch khác nhau thế nào?
6. clearBatch dùng để làm gì?
7. Oracle-specific update batching có trạng thái gì từ 12.2?
8. Oracle JDBC có true batching cho Statement và CallableStatement không?
9. supportsBatchUpdates kiểm tra điều gì?
10. Auto-commit nên được quản lý thế nào khi cần rollback batch?
11. Batch size khác transaction chunk size thế nào?
12. Vì sao Oracle khuyến nghị batch size khoảng 100 hoặc thấp hơn?
13. Update count bằng 0 có luôn là lỗi không?
14. SUCCESS_NO_INFO nghĩa là gì?
15. EXECUTE_FAILED xuất hiện trong trường hợp nào?
16. BatchUpdateException là subclass của class nào?
17. JDBC driver có bắt buộc dừng tại command lỗi không?
18. Oracle JDBC standard batching xử lý command lỗi thế nào?
19. getUpdateCounts trả về thông tin gì?
20. Vì sao counts không chứng minh transaction đã commit?
21. Khi rollback connection, những DML nào bị rollback?
22. Savepoint giúp ích gì khi batch lỗi?
23. Vì sao không retry toàn batch một cách mù quáng?
24. Idempotency giúp gì cho batch import?
25. Khi nào cần executeLargeBatch?
26. Sequence có bảo đảm giá trị liên tục không?
27. Batch DML có bỏ qua triggers và constraints không?
28. Khi nào set-based SQL tốt hơn JDBC batching?
29. FORALL khác JDBC batching thế nào?
30. Những metric nào nên đo khi tuning batch size?

**Gợi ý trả lời:**

1. Gom nhiều DML commands và thực thi bằng một batch.
2. Network round trips và JDBC/parse overhead lặp lại.
3. Không mặc nhiên; batching chủ yếu gom gửi và thực thi.
4. Cùng SQL được tái sử dụng với nhiều bind sets và Oracle có true batching cho PreparedStatement.
5. addBatch thêm command; executeBatch gửi và thực thi nhóm.
6. Xóa các command đang chờ trong batch.
7. Proprietary batching là no-op; dùng standard JDBC batching.
8. Không có true batching như PreparedStatement trong Oracle driver.
9. Driver có hỗ trợ JDBC batch updates hay không.
10. Tắt auto-commit và commit/rollback tường minh.
11. Batch size là số command mỗi executeBatch; transaction chunk size là số rows mỗi transaction commit.
12. Batch lớn hơn ít cải thiện và có thể tăng client resource usage.
13. Không; có thể WHERE không khớp dòng nào.
14. Command thành công nhưng số rows không xác định.
15. Khi driver tiếp tục xử lý sau lỗi và đánh dấu command lỗi.
16. SQLException.
17. Không; driver có thể dừng hoặc tiếp tục theo JDBC contract.
18. Dừng tại operation lỗi và counts chứa các command thành công trước đó.
19. Update counts của các command đã thực thi thành công hoặc trạng thái theo driver behavior.
20. Counts phản ánh execution trong transaction; commit là bước riêng.
21. Toàn bộ thay đổi chưa commit trong transaction hiện tại.
22. Rollback một phần transaction về điểm savepoint.
23. Có thể duplicate hoặc thực thi lại DML đã commit.
24. Cho phép retry mà không tạo tác dụng phụ lặp.
25. Khi update count có thể vượt Integer.MAX_VALUE và driver hỗ trợ.
26. Không; rollback, cache và concurrent sessions có thể tạo khoảng trống.
27. Không; database constraints và triggers vẫn áp dụng.
28. Khi dữ liệu đã nằm trong database và có thể xử lý bằng một câu SQL.
29. FORALL là bulk DML trong PL/SQL; JDBC batching gửi DML từ Java.
30. Elapsed time, throughput, batch size, memory, round trips, CPU, redo/undo, locks và error rate.

## Tài liệu Oracle và JDBC tham khảo

- [Oracle Database 19c JDBC Developer's Guide — Performance Extensions / Update Batching](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/performance-extensions.html): standard batching, proprietary batching, Oracle driver behavior và error handling.
- [Oracle Database 19c JDBC Developer's Guide — JDBC Coding Tips](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/JDBC-coding-tips.html): khuyến nghị batch size khoảng 100 hoặc thấp hơn.
- [Oracle Database 19c JDBC Developer's Guide — JDBC Batching Error Handling](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/performance-extensions.html): BatchUpdateException và update counts trong Oracle JDBC.
- [Java SE 21 API — BatchUpdateException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/BatchUpdateException.html): getUpdateCounts, getLargeUpdateCounts và behavior khi driver dừng/tiếp tục.
- [Java SE 21 API — Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): addBatch, executeBatch, executeLargeBatch, SUCCESS_NO_INFO và EXECUTE_FAILED.
- [Oracle Database 19c PL/SQL Language Reference — FORALL Statement](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/FORALL-statement.html): bulk DML trong PL/SQL.

**Nguyên tắc cần nhớ:** Với Oracle JDBC, dùng PreparedStatement và standard addBatch/executeBatch để giảm network round trips. Bắt đầu thử batch size khoảng 100 hoặc thấp hơn rồi benchmark. Tắt auto-commit khi cần kiểm soát rollback. BatchUpdateException cung cấp update counts nhưng không tự quyết định transaction có commit hay không. JDBC driver nói chung có thể dừng hoặc tiếp tục sau lỗi; Oracle JDBC standard batching dừng tại command lỗi và trả counts của các command thành công trước đó. Thiết kế transaction boundary, idempotency và retry policy trước khi đưa batch DML vào production.
