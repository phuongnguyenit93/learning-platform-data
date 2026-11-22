# rewriteBatchedStatements, batch DML và xử lý lỗi từng phần

JDBC cho phép gom nhiều thao tác ghi vào một batch rồi gửi bằng `executeBatch()`. Với MySQL Connector/J, thuộc tính kết nối `rewriteBatchedStatements` có thể giúp driver biến batch thành ít lần trao đổi với server hơn. Khi dùng đúng cách, batch DML giảm chi phí round trip và tăng throughput; khi dùng thiếu kiểm soát, nó có thể tạo câu lệnh quá lớn, tăng áp lực bộ nhớ, làm transaction kéo dài hoặc khiến kết quả lỗi khó xác định.

Một điểm quan trọng là **batch JDBC, câu SQL được rewrite và transaction là ba khái niệm khác nhau**. JDBC mô tả cách client gửi nhiều lệnh; Connector/J quyết định có thể rewrite batch ra sao; transaction của MySQL quyết định phạm vi commit/rollback. Vì vậy, bật `rewriteBatchedStatements=true` không tự động bảo đảm toàn bộ batch là một transaction nguyên tử hoặc có thể biết chính xác từng hàng đã được ghi.

Bài học này tập trung vào MySQL Connector/J và JDBC. Ví dụ Java dùng `PreparedStatement`, InnoDB và MySQL 8.0; hành vi rewrite cụ thể phụ thuộc phiên bản Connector/J, loại câu lệnh, cấu hình prepared statement và server. Hãy kiểm thử bằng đúng driver đang triển khai.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt `addBatch()`, `executeBatch()` và transaction commit.
- Giải thích mục đích và giới hạn của `rewriteBatchedStatements`.
- Hiểu sự khác nhau giữa rewrite thành multi-value INSERT và gửi nhiều câu lệnh trong một lần trao đổi.
- Đọc update count, `BatchUpdateException` và các mã `SUCCESS_NO_INFO`/`EXECUTE_FAILED`.
- Thiết kế batch size, transaction boundary và retry an toàn.
- Xử lý lỗi một phần, lỗi kết nối không rõ kết quả và generated keys.
- Đo hiệu năng batch mà không làm mất tính toàn vẹn dữ liệu.

## 1. JDBC batch DML hoạt động thế nào?

JDBC batch cho phép ứng dụng xếp nhiều thao tác ghi rồi gửi theo nhóm. Với `PreparedStatement`, ứng dụng dùng một mẫu SQL và nhiều bộ tham số. Mỗi lần gọi `addBatch()` lưu bộ tham số hiện tại vào batch; `executeBatch()` yêu cầu driver thực thi các phần tử đã xếp.

Ví dụ một câu insert với nhiều bộ tham số:

```java
String sql = "INSERT INTO inventory (sku, warehouse_id, quantity) "
        + "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "SKU-1001");
    ps.setLong(2, 10L);
    ps.setInt(3, 25);
    ps.addBatch();

    ps.setString(1, "SKU-1002");
    ps.setLong(2, 10L);
    ps.setInt(3, 40);
    ps.addBatch();

    int[] counts = ps.executeBatch();
}
```

Trong ví dụ, client tạo hai phần tử batch. Khi `executeBatch()` chạy, Connector/J có thể gửi chúng theo cách thông thường hoặc rewrite nếu câu lệnh và cấu hình đáp ứng điều kiện. `addBatch()` không có nghĩa dữ liệu đã được gửi tới server, và `executeBatch()` cũng không có nghĩa dữ liệu đã commit.

### 1.1. Statement batch và PreparedStatement batch

- `Statement.addBatch(String sql)` dùng khi batch chứa các câu SQL khác nhau. Ứng dụng phải tự xây dựng SQL, nên dễ mắc lỗi escape và SQL injection nếu ghép dữ liệu đầu vào.
- `PreparedStatement.addBatch()` dùng cùng một câu SQL với nhiều bộ tham số. Đây thường là lựa chọn phù hợp cho batch insert/update/delete có cấu trúc giống nhau.

Ưu tiên `PreparedStatement` để bind dữ liệu theo kiểu, giảm việc tạo chuỗi SQL và tận dụng cơ chế prepared statement của driver/server khi phù hợp. Không ghép giá trị người dùng vào SQL chỉ để cố đạt rewrite.

### 1.2. Batch không đồng nghĩa transaction

Batch là nhóm lệnh được client gửi cùng nhau. Transaction là nhóm thay đổi dữ liệu được commit hoặc rollback theo engine và ranh giới transaction của MySQL.

| Cơ chế | Trách nhiệm |
|---|---|
| `addBatch()` | Xếp thao tác vào batch ở phía JDBC |
| `executeBatch()` | Yêu cầu driver gửi/thực thi batch và trả update counts hoặc lỗi |
| `setAutoCommit(false)` | Chuyển connection sang chế độ transaction do ứng dụng quản lý; transaction bắt đầu khi có thao tác transactional |
| `commit()` | Xác nhận các thay đổi trong transaction hiện tại |
| `rollback()` | Hoàn tác các thay đổi transactional chưa commit |

Nếu connection đang `autoCommit=true`, mỗi câu SQL được server thực thi có thể commit độc lập theo quy tắc autocommit. Nếu driver rewrite nhiều thao tác thành một câu SQL, ranh giới statement cũng thay đổi. Muốn kiểm soát rõ transaction boundary, hãy đặt `autoCommit=false`, xác định batch nào thuộc transaction nào và commit có chủ đích.

## 2. `rewriteBatchedStatements` là gì?

`rewriteBatchedStatements` là thuộc tính kết nối của MySQL Connector/J. Khi bật, driver cố gắng rewrite các batch tương thích để giảm số lần trao đổi với MySQL. Ví dụ, nhiều lần insert cùng cấu trúc có thể được gộp thành một multi-value INSERT; các dạng batch khác có thể được gửi theo cơ chế multi-query hoặc một cách tối ưu phù hợp với phiên bản driver.

Ví dụ URL kết nối:

```text
jdbc:mysql://db.example:3306/app?rewriteBatchedStatements=true
```

Ví dụ dùng `DriverManager` với property trên URL:

```java
String url = "jdbc:mysql://db.example:3306/app?rewriteBatchedStatements=true";
Properties properties = new Properties();
properties.setProperty("user", "app_writer");
properties.setProperty("password", readSecret("mysql/app-writer"));
try (Connection connection = DriverManager.getConnection(url, properties)) {
    // Dùng connection đã cấu hình rewriteBatchedStatements.
}
```

Với `DataSource` hoặc connection pool, đặt cùng property qua cơ chế cấu hình của thư viện đó. Không ghi mật khẩu thật vào source code, URL được commit hoặc log.

### 2.1. Multi-value INSERT

Với batch insert phù hợp, driver có thể biến nhiều bộ giá trị thành một câu dạng:

```sql
INSERT INTO inventory (sku, warehouse_id, quantity)
VALUES
  ('SKU-1001', 10, 25),
  ('SKU-1002', 10, 40),
  ('SKU-1003', 12, 15);
```

Thay vì gửi một request cho mỗi hàng, client gửi một câu SQL chứa nhiều hàng. Điều này thường giảm round trip và chi phí parse/execute lặp lại.

### 2.2. Multi-query và các batch khác

Không phải mọi batch đều có thể chuyển thành multi-value INSERT. Với các câu lệnh khác nhau hoặc một số dạng update/delete, driver có thể sử dụng nhiều câu lệnh trong một lần trao đổi. Cách rewrite phụ thuộc loại statement, phiên bản Connector/J và cấu hình kết nối.

Do đó, không nên giả định rằng:

- Mọi câu `UPDATE` trong batch đều được hợp nhất thành một câu update duy nhất.
- Mọi `PreparedStatement` đều được rewrite theo cùng một cách.
- Bật rewrite sẽ luôn tạo đúng một round trip cho toàn bộ batch.
- Kết quả update count luôn cho biết chính xác số hàng của từng phần tử ban đầu.

Hãy kiểm tra tài liệu đúng phiên bản, log driver nếu có thể và đo thực tế. Với batch lớn, driver có thể chia thành nhiều nhóm nhỏ dựa trên giới hạn packet hoặc giới hạn nội bộ.

### 2.3. Bật rewrite không giống bật multi-query tùy ý

`rewriteBatchedStatements` là tối ưu hóa cho batch do JDBC quản lý. Nó không nên được dùng như lý do để ghép chuỗi SQL đầu vào hoặc bật một API chạy nhiều câu lệnh không kiểm soát. Vẫn dùng parameter binding và quyền database tối thiểu.

Các thuộc tính khác như `useServerPrepStmts`, `allowMultiQueries`, `continueBatchOnError` và `useAffectedRows` có mục đích riêng. Sự kết hợp của chúng có thể ảnh hưởng cách driver thực thi hoặc báo kết quả; không thay đổi đồng loạt trong production nếu chưa thử nghiệm.

## 3. Đo lợi ích và chọn batch size

Batch thường tăng throughput vì giảm round trip, nhưng batch càng lớn không phải lúc nào cũng càng nhanh. Batch quá lớn có thể:

- Tạo SQL/packet lớn, chạm giới hạn `max_allowed_packet` hoặc giới hạn của driver.
- Tăng bộ nhớ phía JVM để giữ tham số và kết quả.
- Tăng thời gian một lần `executeBatch()` và làm request khó hủy đúng lúc.
- Giữ lock lâu hơn nếu nhiều thao tác nằm trong cùng transaction.
- Tạo transaction lớn, tăng undo/redo, binary log và replica lag.
- Làm lỗi một phần khó xác định và retry tốn kém hơn.

Chọn batch size theo cả số hàng và kích thước byte. Một batch 1.000 hàng với ba số nguyên khác hẳn 1.000 hàng chứa JSON hoặc BLOB lớn. Bắt đầu bằng một mức vừa phải, đo p95/p99 thời gian execute, memory, packet, lock wait và replica lag, rồi điều chỉnh.

Ví dụ, 500 hoặc 1.000 hàng có thể là điểm bắt đầu thử nghiệm cho bảng nhỏ, nhưng không phải giá trị tối ưu chung. Với payload lớn, có thể cần batch nhỏ hơn; với row hẹp và đường mạng có độ trễ cao, batch lớn hơn có thể có lợi.

### 3.1. Đo throughput

Một phép đo có ích cần so sánh cùng dữ liệu, cùng schema và cùng tải:

1. Chạy batch với `rewriteBatchedStatements=false`.
2. Chạy lại trên môi trường tương đương với `rewriteBatchedStatements=true`.
3. Giữ nguyên batch size, transaction boundary, connection pool và số worker.
4. Đo rows/second, p95/p99 execute time, CPU, disk I/O, network round trips nếu quan sát được, lock wait và replica lag.
5. Xác minh số hàng và giá trị dữ liệu sau mỗi lượt.

Không chỉ so thời gian của một batch đơn lẻ. Tải đồng thời và transaction commit thường quyết định hiệu năng tổng thể của ứng dụng.

## 4. Update counts và kết quả thực thi

`executeBatch()` trả về mảng `int[]` update counts. Theo JDBC, mỗi phần tử thường biểu thị số hàng bị ảnh hưởng bởi phần tử tương ứng. Tuy nhiên, driver có thể trả các hằng số đặc biệt:

| Giá trị | Ý nghĩa |
|---|---|
| `1`, `2`, ... | Số hàng bị ảnh hưởng được driver báo cáo |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Phần tử thành công nhưng driver không xác định được số hàng chính xác |
| `Statement.EXECUTE_FAILED` (`-3`) | Phần tử thất bại trong kết quả batch có thông tin lỗi từng phần |

Khi batch được rewrite, mapping từ một câu SQL đã gộp về từng phần tử ban đầu có thể không đầy đủ. Không dùng update counts như bằng chứng duy nhất rằng mỗi record đã được ghi đúng. Đối chiếu thêm bằng khóa nghiệp vụ, số hàng, trạng thái batch và truy vấn kiểm tra.

Ví dụ kiểm tra kết quả:

```java
int[] counts = ps.executeBatch();

for (int i = 0; i < counts.length; i++) {
    int count = counts[i];
    if (count == Statement.EXECUTE_FAILED) {
        throw new SQLException("Batch item failed at index " + i);
    }
    if (count == Statement.SUCCESS_NO_INFO) {
        // Thành công nhưng không có số hàng chính xác.
        continue;
    }
    if (count < 0) {
        throw new SQLException("Unexpected batch update count: " + count);
    }
}
```

Nếu nghiệp vụ yêu cầu mỗi lệnh phải tác động đúng một hàng, cần xác định liệu driver có trả count chính xác trong cấu hình đang dùng hay không. Một kết quả `SUCCESS_NO_INFO` không thể chứng minh điều kiện “đúng một hàng” theo từng phần tử.

## 5. Xử lý `BatchUpdateException` và lỗi từng phần

Khi một phần tử batch thất bại, JDBC ném `BatchUpdateException`, một subclass của `SQLException`. Có thể lấy update counts của những phần tử driver đã xử lý:

```java
try {
    int[] counts = ps.executeBatch();
    // Kiểm tra kết quả khi batch hoàn tất.
} catch (BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();

    for (int i = 0; i < counts.length; i++) {
        System.err.printf("item=%d count=%d%n", i, counts[i]);
    }

    System.err.println("SQLState=" + e.getSQLState());
    System.err.println("VendorCode=" + e.getErrorCode());
    throw e;
}
```

Độ dài và ý nghĩa mảng update counts phụ thuộc cách driver xử lý batch. Driver có thể dừng tại lỗi hoặc tiếp tục các phần tử còn lại theo cấu hình và cách rewrite. Không được mặc định rằng phần tử sau index lỗi chắc chắn chưa chạy, hoặc chắc chắn đã chạy.

### 5.1. `continueBatchOnError`

Connector/J có thuộc tính `continueBatchOnError` để điều khiển việc tiếp tục xử lý batch khi một lệnh thất bại trong những trường hợp driver thực thi được từng phần tử. Mặc định thường là `true` trong Connector/J, nhưng cần xác nhận phiên bản đang dùng.

Khi bật, driver có thể tiếp tục những lệnh còn lại sau lỗi và ném `BatchUpdateException` với update counts. Khi tắt, driver có thể dừng tại lỗi đầu tiên. Tuy nhiên, nếu batch đã được rewrite thành một câu SQL duy nhất, server có thể chỉ trả kết quả ở cấp câu lệnh đó; driver không thể bảo đảm xử lý tiếp từng record như một vòng lặp độc lập.

Vì vậy, `continueBatchOnError` không tạo ra cơ chế “mỗi hàng độc lập và lỗi hàng nào chỉ ảnh hưởng hàng đó”. Muốn có khả năng cách ly lỗi theo record, cần chia batch nhỏ, validate trước, dùng savepoint/transaction hoặc đưa dữ liệu vào staging để phân loại.

### 5.2. Các kiểu lỗi khác nhau

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Dữ liệu không hợp lệ | Giá trị sai kiểu, NOT NULL, độ dài cột | Ghi nhận record lỗi, sửa nguồn hoặc đưa vào bảng quarantine |
| Vi phạm constraint | Duplicate key, foreign key | Kiểm tra khóa nghiệp vụ và dữ liệu tham chiếu; không retry nguyên trạng |
| Lỗi cạnh tranh | Deadlock, lock wait timeout | Retry toàn transaction theo chính sách có backoff sau khi xác định trạng thái rollback |
| Lỗi cấu hình | Thiếu quyền, sai schema/table | Sửa cấu hình hoặc grant; không retry lặp vô hạn |
| Lỗi kết nối | Socket timeout, server mất kết nối khi execute/commit | Kết quả có thể không rõ; kiểm tra trạng thái dữ liệu trước khi retry |
| Lỗi tài nguyên | Packet quá lớn, hết dung lượng, server overload | Giảm batch, kiểm tra packet/disk/load và chạy lại có kiểm soát |

## 6. Transaction boundary và tính nguyên tử

Với bảng InnoDB, transaction cho phép gom nhiều thay đổi thành một đơn vị commit/rollback. JDBC cần quản lý ranh giới transaction rõ ràng:

```java
connection.setAutoCommit(false);
try {
    // Thực hiện một hoặc nhiều executeBatch().
    connection.commit();
} catch (SQLException e) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        e.addSuppressed(rollbackError);
        // Không tái sử dụng connection nếu trạng thái transaction không rõ.
    }
    throw e;
}
```

Đoạn code chỉ là khung cho một connection được ứng dụng sở hữu. Với connection lấy từ pool, để pool hoặc transaction manager reset trạng thái theo quy ước của nó. Không gọi `setAutoCommit(true)` vô điều kiện trong `finally` sau một lỗi chưa rollback thành công: JDBC có thể commit transaction đang còn mở khi chuyển autocommit về true. Nếu rollback hoặc reset connection thất bại, loại connection khỏi pool theo API của pool thay vì tái sử dụng một connection có trạng thái không rõ.

### 6.1. Một batch trong một transaction

Nếu `autoCommit=false`, nhiều câu DML transactional đã thực thi vẫn chưa được commit cho đến khi ứng dụng gọi `commit()`. Nếu batch phát sinh lỗi, ứng dụng có thể rollback transaction để hoàn tác những thay đổi InnoDB chưa commit.

Đây là lựa chọn phù hợp khi các hàng trong một batch phải cùng thành công hoặc cùng thất bại. Tuy nhiên, transaction quá lớn làm tăng thời gian giữ lock, undo/redo, binary log và khả năng replica lag. Chỉ dùng một transaction rất lớn khi nghiệp vụ thực sự cần tính nguyên tử ở phạm vi đó và tài nguyên đã được kiểm chứng.

### 6.2. Commit theo chunk

Với import hàng triệu record, thường chia thành nhiều chunk, mỗi chunk là một transaction riêng. Ví dụ 500 record được gửi trong một batch và commit, sau đó tiếp tục chunk kế tiếp.

Lợi ích:

- Giới hạn thời gian giữ lock và kích thước transaction.
- Giảm lượng rollback nếu một chunk gặp lỗi.
- Dễ checkpoint và tiếp tục sau khi tiến trình bị dừng.
- Điều tiết tốc độ theo tải và replica lag.

Đổi lại, toàn bộ import không còn nguyên tử. Nếu chunk thứ 12 thất bại, các chunk trước đó có thể đã commit. Ứng dụng cần lưu tiến độ và có cách chạy lại an toàn.

### 6.3. Rewrite có thể thay đổi failure boundary

Giả sử batch có 100 lệnh insert. Nếu driver gửi từng lệnh riêng với autocommit bật, một số lệnh đầu có thể đã commit trước khi một lệnh sau thất bại. Nếu driver rewrite thành một multi-value INSERT trên InnoDB, server xử lý chúng như một statement; lỗi statement có thể khiến toàn statement rollback theo quy tắc transactional engine. Nếu driver dùng multi-query gồm nhiều statement, mỗi statement có thể có ranh giới autocommit riêng khi connection đang bật autocommit.

Trong explicit transaction với InnoDB, các DML transactional được thực hiện trong cùng transaction có thể rollback cùng nhau. Tuy nhiên, cần phân biệt lỗi statement, lỗi deadlock khiến InnoDB rollback transaction, lỗi timeout và các câu lệnh có implicit commit. Không đưa DDL hoặc thao tác implicit commit vào cùng một batch DML với giả định rollback sẽ hoàn tác tất cả.

Với bảng nontransactional, rollback không thể hoàn tác các thay đổi đã ghi như InnoDB. Muốn có hành vi rollback nhất quán, ưu tiên bảng InnoDB và kiểm tra các trigger/side effect liên quan.

## 7. Ví dụ batch insert theo chunk

Ví dụ sau dùng `PreparedStatement`, batch size cố định và commit từng chunk. Mục tiêu là giới hạn transaction, không phải khẳng định batch size này phù hợp với mọi workload.

```java
int batchSize = 500;
int pending = 0;
String sql = "INSERT INTO import_orders "
        + "(source_order_id, customer_id, amount) VALUES (?, ?, ?)";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (OrderRow row : rows) {
            ps.setString(1, row.getSourceOrderId());
            ps.setLong(2, row.getCustomerId());
            ps.setBigDecimal(3, row.getAmount());
            ps.addBatch();
            pending++;

            if (pending == batchSize) {
                ps.executeBatch();
                // Ghi checkpoint trong cùng transaction với dữ liệu chunk.
                connection.commit();
                ps.clearBatch();
                pending = 0;
            }
        }

        if (pending > 0) {
            ps.executeBatch();
            // Ghi checkpoint trong cùng transaction với dữ liệu chunk cuối.
            connection.commit();
            ps.clearBatch();
        }
    } catch (SQLException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
            // Đánh dấu connection không còn an toàn để tái sử dụng.
        }
        throw e;
    }
}
```

Ví dụ giả định method sở hữu connection lấy từ `DataSource`; đóng connection sẽ trả nó về pool hoặc đóng kết nối vật lý theo cấu hình. Nếu ứng dụng dùng transaction manager, để transaction manager quản lý commit/rollback và không trộn thủ công hai cơ chế. Trong ví dụ thực tế, cần thêm xử lý update counts và ghi checkpoint cùng transaction với dữ liệu chunk nếu có thể. Nếu một chunk đã commit, rollback ở chunk sau không hoàn tác được chunk trước đó.

Không gọi `setAutoCommit(true)` vô điều kiện trong `finally` sau một lỗi chưa rollback thành công: JDBC có thể commit transaction đang còn mở khi chuyển autocommit về true. Nếu rollback hoặc reset connection thất bại, loại connection khỏi pool theo API của pool thay vì tái sử dụng một connection có trạng thái không rõ.

Với Spring, để tránh vô tình mở một transaction quá lớn, có thể đặt transaction boundary ở service xử lý từng chunk. Cần chú ý propagation và việc `JdbcTemplate.batchUpdate()` có thể chia batch theo kích thước được cấu hình; transaction vẫn do Spring transaction manager quản lý.

## 8. Retry an toàn và idempotency

Retry là cần thiết khi gặp lỗi tạm thời, nhưng retry mù có thể tạo duplicate hoặc nhân đôi tác động. Một trường hợp khó là client mất kết nối ngay sau khi gửi batch: server có thể đã commit nhưng phản hồi chưa tới client. Ứng dụng không biết chắc batch đã thành công hay chưa.

### 8.1. Dùng khóa idempotency

Nếu mỗi record có định danh từ hệ thống nguồn, lưu định danh đó bằng unique key:

```sql
CREATE TABLE import_orders (
  source_order_id VARCHAR(80) NOT NULL,
  customer_id BIGINT NOT NULL,
  amount DECIMAL(12, 2) NOT NULL,
  imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (source_order_id)
) ENGINE = InnoDB;
```

Unique key giúp lần chạy lại nhận diện record đã được nạp. Có thể dùng `INSERT ... ON DUPLICATE KEY UPDATE` nếu quy tắc nghiệp vụ cho phép cập nhật lại bản ghi; cần định nghĩa rõ cột nào được cập nhật và cách tránh ghi đè dữ liệu mới hơn bằng dữ liệu cũ.

Không dùng `INSERT IGNORE` hoặc upsert một cách tổng quát để che mọi lỗi. Các thao tác đó có thể biến dữ liệu sai thành warnings hoặc cập nhật ngoài ý muốn. Idempotency phải phản ánh định danh và quy tắc nghiệp vụ, không chỉ là tránh exception.

### 8.2. Checkpoint theo chunk

Một bảng điều phối import có thể lưu `batch_id`, khoảng khóa nguồn, trạng thái, số hàng dự kiến, số hàng xử lý và thời điểm commit. Cập nhật checkpoint trong cùng transaction với dữ liệu của chunk nếu có thể, để checkpoint không vượt trước dữ liệu đã commit.

Khi worker khởi động lại:

1. Đọc trạng thái batch và checkpoint cuối đã commit.
2. Xác minh chunk cuối có dữ liệu đầy đủ theo idempotency key.
3. Chỉ xử lý phần chưa hoàn tất.
4. Ghi nhận lỗi record riêng để có thể sửa và phát lại.

Nếu trạng thái commit không rõ do mất kết nối, truy vấn theo batch ID hoặc khóa nguồn trước khi chạy lại. Không giả định lỗi phía client đồng nghĩa server rollback.

### 8.3. Retry deadlock và timeout

Deadlock InnoDB thường khiến một transaction được chọn làm nạn nhân và bị rollback. Khi đó, retry phải chạy lại toàn bộ transaction, không chỉ lệnh cuối trong batch. Dùng số lần thử giới hạn, exponential backoff có jitter và log SQLState/vendor code.

Lock wait timeout thường rollback statement đang chờ theo cấu hình mặc định; transaction có thể vẫn còn hoạt động. Ứng dụng phải quyết định rollback toàn transaction trước khi retry để giữ logic nhất quán. Không retry vô hạn vì có thể làm tăng tải và kéo dài tình trạng tranh chấp.

Lỗi duplicate key, dữ liệu sai hoặc thiếu quyền thường không tự hết khi retry. Phân loại lỗi trước khi quyết định thử lại.

## 9. Generated keys trong batch

Nếu bảng dùng `AUTO_INCREMENT`, JDBC có thể yêu cầu generated keys:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customers (email) VALUES (?)",
        Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "a@example.test");
    ps.addBatch();
    ps.setString(1, "b@example.test");
    ps.addBatch();

    ps.executeBatch();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        while (keys.next()) {
            long id = keys.getLong(1);
            // Ghi nhận khóa được trả về.
        }
    }
}
```

Khi rewrite batch insert thành multi-value INSERT, Connector/J có thể tối ưu việc lấy generated keys, nhưng ứng dụng cần kiểm tra hành vi của phiên bản driver/server đang dùng. Không tự suy ra ID liên tiếp bằng cách lấy ID đầu cộng chỉ số hàng: `AUTO_INCREMENT` có thể có khoảng trống do rollback, concurrency, cấu hình increment/offset hoặc thao tác khác.

Nếu cần ánh xạ chắc chắn ID database về từng record nguồn, nên dùng khóa nghiệp vụ/idempotency key rồi truy vấn lại theo các khóa đó, hoặc kiểm thử rõ `getGeneratedKeys()` với đúng cấu hình rewrite trước khi phụ thuộc vào thứ tự trả về.

## 10. Cấu hình và kiểm thử Connector/J

Các property có thể ảnh hưởng batch:

| Property | Vai trò | Lưu ý |
|---|---|---|
| `rewriteBatchedStatements` | Cho phép driver rewrite batch tương thích | Mặc định thường là `false`; đo trước/sau và kiểm tra loại statement được rewrite |
| `continueBatchOnError` | Tiếp tục xử lý các lệnh sau lỗi trong trường hợp có thể thực thi từng phần tử | Không bảo đảm cô lập lỗi từng hàng khi batch đã rewrite thành một statement |
| `useServerPrepStmts` | Dùng server-side prepared statements khi được hỗ trợ | Tương tác với rewrite phụ thuộc driver/server version; kiểm thử cấu hình kết hợp |
| `allowMultiQueries` | Cho phép client gửi nhiều câu SQL phân tách trong một statement | Không phải thay thế cho JDBC batch hoặc parameter binding |
| `useAffectedRows` | Ảnh hưởng cách MySQL/driver báo số hàng affected/found trong một số UPDATE | Cần thống nhất cách diễn giải update counts trong ứng dụng |

Kiểm tra property đã áp dụng bằng cấu hình connection pool hoặc API metadata của driver. Không đưa password vào URL nếu URL được log. Ưu tiên secret manager hoặc cơ chế credential của môi trường.

Một ma trận kiểm thử nên bao gồm:

- Rewrite bật và tắt.
- `autoCommit=true` và `false`.
- `PreparedStatement` insert, update và delete.
- Batch không lỗi, duplicate key ở giữa batch và lỗi dữ liệu ở cuối batch.
- Lỗi deadlock, lock wait timeout và mất kết nối khi execute/commit.
- Batch có generated keys.
- Kích thước record nhỏ và lớn, gần giới hạn packet.
- Replica đang chạy và tải đồng thời tương tự production.

Sau mỗi trường hợp, kiểm tra dữ liệu thực tế, update counts, transaction state, log và khả năng retry. Đây là cách xác định failure boundary của driver cụ thể.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Bật rewrite nhưng tốc độ không đổi | Statement không được rewrite, batch quá nhỏ hoặc bottleneck nằm ở storage/index | Kiểm tra loại SQL, driver version và đo round trip/DB load |
| `PacketTooBigException` hoặc packet quá lớn | Batch chứa quá nhiều dữ liệu hoặc row payload lớn | Giảm batch size theo byte, kiểm tra `max_allowed_packet` ở server và driver |
| `BatchUpdateException` nhưng không rõ record lỗi | Update counts không đầy đủ hoặc rewrite làm thay đổi failure boundary | Ghi batch ID, chia nhỏ để cách ly lỗi và kiểm tra dữ liệu bằng khóa nguồn |
| Một phần dữ liệu đã có sau exception | Autocommit hoặc các statement đã commit trước khi lỗi xảy ra | Kiểm tra trạng thái trước retry; dùng idempotency key/checkpoint |
| Duplicate key khi chạy lại | Batch trước có thể đã commit dù client không nhận response | Đối chiếu record theo khóa nghiệp vụ và thiết kế upsert có quy tắc |
| Replica lag tăng | Transaction/chunk lớn tạo nhiều binlog hoặc replica apply chậm | Giảm batch/transaction size và điều tiết theo lag |
| Deadlock khi nhiều worker batch song song | Các worker cập nhật khóa theo thứ tự khác nhau | Sắp xếp theo khóa, giảm concurrency và retry toàn transaction |
| Generated key không ánh xạ như mong đợi | Driver rewrite, auto-increment concurrency hoặc giả định ID liên tiếp | Kiểm thử `getGeneratedKeys()` và truy vấn lại theo khóa nguồn |

## 12. Bài thực hành

Một dịch vụ Java dùng MySQL Connector/J để nhập 200.000 giao dịch từ file. Mỗi giao dịch có `source_txn_id` duy nhất, `account_id`, `amount` và `created_at`. Dịch vụ hiện gọi `executeUpdate()` từng hàng; tốc độ thấp. Nhóm phát triển muốn bật `rewriteBatchedStatements=true` và chạy bốn worker song song.

Hãy thiết kế giải pháp và trả lời:

1. Vì sao `PreparedStatement.addBatch()` phù hợp hơn việc nối 200.000 chuỗi SQL?
2. `rewriteBatchedStatements` có thể biến batch INSERT thành dạng SQL nào? Vì sao không thể khẳng định mọi loại DML đều rewrite giống nhau?
3. Chọn batch size ban đầu theo số hàng và kích thước byte như thế nào? Cần đo những chỉ số nào?
4. Nếu mỗi chunk commit riêng, điều gì xảy ra khi worker thất bại ở chunk thứ 20?
5. `BatchUpdateException.getUpdateCounts()` có thể chứa những giá trị nào? Vì sao `SUCCESS_NO_INFO` không chứng minh chính xác số hàng?
6. `continueBatchOnError=true` có bảo đảm driver tiếp tục từng record khi batch đã rewrite không? Giải thích.
7. Nếu client timeout ngay sau `executeBatch()` hoặc `commit()`, làm sao biết dữ liệu đã ghi hay chưa trước khi retry?
8. Thiết kế unique key/idempotency key và checkpoint để chạy lại không tạo giao dịch trùng.
9. Khi deadlock xảy ra, cần retry statement hay toàn transaction? Cách xử lý lock wait timeout khác gì?
10. Nếu cần generated keys cho từng giao dịch nguồn, làm sao xác minh ánh xạ ID trong cấu hình rewrite?
11. Bốn worker có thể gây deadlock hoặc replica lag như thế nào? Bạn sẽ điều tiết concurrency ra sao?

Hãy thử trên bảng InnoDB với dữ liệu mẫu có duplicate key ở đầu, giữa và cuối batch; thử cả autocommit và explicit transaction, rewrite bật/tắt. Sau mỗi lần chạy, đối chiếu số record theo `source_txn_id`, transaction state và update counts.

## Kết luận

`rewriteBatchedStatements` có thể giảm round trip bằng cách rewrite batch JDBC tương thích, đặc biệt với các batch insert có thể gộp thành multi-value INSERT. Nó không quyết định transaction boundary và không bảo đảm kết quả update count hoặc lỗi từng record luôn đầy đủ. Muốn batch DML vừa nhanh vừa an toàn, hãy dùng `PreparedStatement`, chọn batch size theo kích thước dữ liệu, quản lý transaction theo chunk, đọc `BatchUpdateException`, xây idempotency key/checkpoint và kiểm thử failure boundary trên đúng phiên bản Connector/J. Khi trạng thái commit không rõ, hãy kiểm tra dữ liệu theo khóa nguồn trước khi retry.
