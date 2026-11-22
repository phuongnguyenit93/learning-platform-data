# Ngữ nghĩa affected rows, matched rows và ảnh hưởng từ tùy chọn client

Khi chạy một câu `UPDATE`, MySQL có thể tìm thấy nhiều hàng thỏa điều kiện `WHERE` nhưng chỉ thực sự thay đổi một phần trong số đó. Ví dụ, một câu lệnh tìm thấy 5 đơn hàng đang ở trạng thái `PAID`, nhưng đặt lại trạng thái thành `PAID` không làm thay đổi dữ liệu. Nếu ứng dụng chỉ nhận về một con số mà không hiểu cách tính, nó có thể nhầm rằng không tìm thấy đơn hàng, trong khi thực tế 5 hàng đã khớp điều kiện.

MySQL phân biệt số hàng được tìm thấy (*matched/found rows*) với số hàng thực sự thay đổi (*changed rows*). Số lượng mà client nhận được còn phụ thuộc cờ kết nối `CLIENT_FOUND_ROWS`. Với MySQL Connector/J, thuộc tính `useAffectedRows` điều khiển việc gửi cờ này. Vì vậy, cùng một câu SQL có thể trả về update count khác nhau khi chạy từ hai ứng dụng hoặc hai cấu hình kết nối khác nhau.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế, truy vấn SQL, transaction, kiểm soát đồng thời và vận hành cơ sở dữ liệu quan hệ. Hiểu đúng ngữ nghĩa row count giúp viết repository, API, batch job, lệnh cập nhật hàng loạt và cơ chế optimistic locking chính xác.

Sau bài học, bạn có thể:

- Phân biệt matched rows và changed/affected rows.
- Giải thích kết quả `UPDATE` khi giá trị mới giống giá trị hiện tại.
- Đọc số liệu `Rows matched`, `Changed` và `Warnings` từ MySQL client.
- Dùng `ROW_COUNT()` đúng thời điểm và hiểu giới hạn của nó.
- Giải thích tác động của `CLIENT_FOUND_ROWS` và Connector/J `useAffectedRows`.
- Hiểu row count của `INSERT`, `DELETE` và `INSERT ... ON DUPLICATE KEY UPDATE`.
- Dùng `executeUpdate()` trong JDBC mà không suy luận sai về việc bản ghi có tồn tại.
- Thiết kế optimistic locking và xử lý kết quả cập nhật trong transaction.

## 1. Ba khái niệm cần phân biệt

Trong ngữ cảnh `UPDATE`, ba khái niệm sau không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Matched rows / found rows | Số hàng thỏa điều kiện `WHERE` và được xét để cập nhật | 5 hàng có `status = 'PAID'` |
| Changed rows | Số hàng có ít nhất một giá trị thực sự thay đổi sau khi áp dụng `SET` | Chỉ 2 hàng chuyển từ `NEW` sang `PAID` |
| Affected rows / update count | Con số client hoặc API nhận được; với `UPDATE`, cách tính phụ thuộc `CLIENT_FOUND_ROWS` | Có thể là 2 hoặc 5 trong ví dụ trên |

Theo mặc định ở mức MySQL protocol/API, `UPDATE` báo số hàng thực sự thay đổi. Nếu client kết nối với cờ `CLIENT_FOUND_ROWS`, con số trả về là số hàng khớp `WHERE`, kể cả khi giá trị không đổi.

Đây là khác biệt ở cách báo cáo kết quả cho client. Nó không làm thay đổi điều kiện `WHERE`, dữ liệu được ghi, hoặc quy tắc SQL của câu `UPDATE`.

## 2. Ví dụ cơ bản: matched nhiều hơn changed

Tạo bảng thử nghiệm:

```sql
DROP TABLE IF EXISTS row_count_demo;

CREATE TABLE row_count_demo (
    id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
) ENGINE = InnoDB;

INSERT INTO row_count_demo (id, status, note) VALUES
(1, 'NEW',  'Don hang moi'),
(2, 'PAID', 'Da thanh toan'),
(3, 'PAID', 'Da thanh toan'),
(4, 'NEW',  'Cho xu ly'),
(5, 'PAID', 'Da thanh toan');
```

Chạy câu lệnh:

```sql
UPDATE row_count_demo
SET status = 'PAID'
WHERE id BETWEEN 1 AND 5;
```

Có 5 hàng thỏa `WHERE`, nhưng chỉ hàng 1 và 4 đổi từ `NEW` thành `PAID`. Ba hàng còn lại đã có giá trị `PAID` nên không cần ghi thay đổi.

| Chỉ số | Kết quả |
| --- | ---: |
| Matched rows | 5 |
| Changed rows | 2 |
| Update count mặc định khi không bật `CLIENT_FOUND_ROWS` | 2 |
| Update count khi bật `CLIENT_FOUND_ROWS` | 5 |

MySQL nhận biết khi một cột được gán đúng giá trị hiện tại và không thực hiện thay đổi dữ liệu cho hàng đó. Vì vậy, một câu `UPDATE` thành công về cú pháp có thể trả update count bằng 0.

### 2.1. Cập nhật cùng một giá trị

Sau khi tất cả hàng đều có `status = 'PAID'`, chạy lại:

```sql
UPDATE row_count_demo
SET status = 'PAID'
WHERE id BETWEEN 1 AND 5;
```

Lúc này matched rows vẫn là 5, changed rows là 0. Client dùng changed-rows semantics nhận 0; client dùng found-rows semantics nhận 5.

Đây là tình huống dễ gây lỗi trong ứng dụng: nếu code hiểu `updateCount == 0` luôn có nghĩa “không tìm thấy bản ghi”, code sẽ báo sai khi bản ghi tồn tại nhưng đã có giá trị mong muốn.

## 3. Quan sát kết quả trong MySQL command-line client

Khi chạy `UPDATE` bằng client dòng lệnh `mysql`, thông tin kết quả thường có dạng:

```text
Query OK, 2 rows affected
Rows matched: 5  Changed: 2  Warnings: 0
```

Ba con số cung cấp thông tin khác nhau:

- `Rows matched`: số hàng thỏa điều kiện cập nhật.
- `Changed`: số hàng thực sự thay đổi.
- `Warnings`: số cảnh báo phát sinh trong quá trình thực thi.

Phần `Rows matched` và `Changed` hữu ích khi kiểm tra dữ liệu hoặc điều tra một câu cập nhật hàng loạt. Trong ứng dụng JDBC, `executeUpdate()` chỉ trả về một số nguyên update count; nó không trả riêng cả hai con số như phần thông tin chi tiết của MySQL client.

Nếu dùng C API, hàm `mysql_info()` có thể cung cấp chuỗi thông tin về số hàng khớp, số hàng cập nhật và số cảnh báo. Cờ `CLIENT_FOUND_ROWS` quyết định cách tính affected-rows value mà API trả về.

## 4. ROW_COUNT() và thời điểm đọc

`ROW_COUNT()` trả số hàng bị ảnh hưởng bởi câu lệnh gần nhất theo ngữ nghĩa row count của kết nối. Với `UPDATE`, nó chịu ảnh hưởng của `CLIENT_FOUND_ROWS` giống affected-rows value mà MySQL báo cho client.

Ví dụ:

```sql
UPDATE row_count_demo
SET note = 'Da kiem tra'
WHERE id IN (1, 2);

SELECT ROW_COUNT() AS update_count;
```

Hãy gọi `ROW_COUNT()` ngay sau câu lệnh cần đo. Nếu chạy một câu SQL khác trước đó, giá trị mà `ROW_COUNT()` đọc sẽ thuộc câu lệnh mới hơn, không còn là kết quả `UPDATE` ban đầu.

Một số giá trị tổng quát:

| Câu lệnh ngay trước đó | Kết quả `ROW_COUNT()` |
| --- | --- |
| `UPDATE`, `INSERT`, `DELETE` | Số hàng bị ảnh hưởng theo ngữ nghĩa của câu lệnh và kết nối |
| `CREATE TABLE`, `DROP TABLE` | `0` |
| `SELECT` trả result set | `-1` |
| `SELECT ... INTO OUTFILE` | Số hàng ghi ra file |

Không nhầm `ROW_COUNT()` với `FOUND_ROWS()`. `FOUND_ROWS()` liên quan đến số hàng của một `SELECT` có `LIMIT` và cơ chế `SQL_CALC_FOUND_ROWS`; cơ chế này đã deprecated trong MySQL. Nó không phải hàm để lấy matched rows của một câu `UPDATE`.

## 5. CLIENT_FOUND_ROWS là gì?

`CLIENT_FOUND_ROWS` là cờ capability do client gửi trong quá trình thiết lập kết nối với MySQL Server. Cờ này yêu cầu server báo số hàng được tìm thấy bởi điều kiện `WHERE` của `UPDATE`, thay vì chỉ số hàng thực sự thay đổi.

| Kết nối | Hành vi với `UPDATE` không thay đổi giá trị |
| --- | --- |
| Không gửi `CLIENT_FOUND_ROWS` | Update count bằng số hàng changed; trường hợp no-op trả `0` |
| Có gửi `CLIENT_FOUND_ROWS` | Update count bằng số hàng matched; trường hợp no-op vẫn có thể trả số lớn hơn `0` |

Đây là tùy chọn ở cấp kết nối, được quyết định khi client kết nối. Không thể coi nó là một `SET sql_mode` hay một mệnh đề trong câu SQL. Hai connection tới cùng server có thể dùng hai hành vi row count khác nhau.

`CLIENT_FOUND_ROWS` không làm câu `UPDATE` sửa thêm hàng. Nó chỉ thay đổi con số affected rows được báo lại. Nếu một hàng không thỏa `WHERE`, cờ này cũng không khiến hàng đó được tính là matched.

## 6. Ảnh hưởng của MySQL Connector/J

Với ứng dụng Java, thuộc tính kết nối MySQL Connector/J có tên `useAffectedRows` điều khiển việc driver có gửi `CLIENT_FOUND_ROWS` hay không.

| Connector/J property | Giá trị mặc định | Cờ gửi tới server | Update count của `UPDATE` |
| --- | --- | --- | --- |
| `useAffectedRows=false` | Có | Có `CLIENT_FOUND_ROWS` | Số hàng matched |
| `useAffectedRows=true` | Không | Không gửi `CLIENT_FOUND_ROWS` | Số hàng actually changed |

Tên thuộc tính dễ gây nhầm. Khi `useAffectedRows=true`, driver bỏ cờ `CLIENT_FOUND_ROWS` để dùng changed-rows semantics của MySQL. Tài liệu Connector/J ghi rõ tùy chọn này không JDBC-compliant theo cách nó thay đổi row count, có thể làm hỏng ứng dụng đang dựa vào found-rows behavior, nhưng cho kết quả update count đúng theo quy tắc MySQL của `INSERT ... ON DUPLICATE KEY UPDATE`.

Ví dụ URL kết nối:

```text
# Hành vi mặc định: found rows
jdbc:mysql://localhost:3306/shop

# Hành vi changed rows của MySQL
jdbc:mysql://localhost:3306/shop?useAffectedRows=true
```

Nếu URL có nhiều thuộc tính, nối bằng `&`:

```text
jdbc:mysql://localhost:3306/shop?useSSL=true&useAffectedRows=true
```

Thuộc tính này cần được cấu hình nhất quán cho connection pool. Thay đổi cấu hình trong file mà không tạo lại pool hoặc connection vật lý có thể khiến ứng dụng tiếp tục sử dụng hành vi cũ.

### 6.1. Kiểm tra hành vi bằng JDBC

```java
String sql = "UPDATE row_count_demo SET status = ? WHERE id BETWEEN ? AND ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "PAID");
    statement.setLong(2, 1L);
    statement.setLong(3, 5L);

    int updateCount = statement.executeUpdate();
    System.out.println("Update count = " + updateCount);
}
```

Chạy đoạn code với hai connection pool hoặc hai URL khác nhau:

- Với `useAffectedRows=false`, nếu cả 5 hàng khớp, update count là 5.
- Với `useAffectedRows=true`, nếu chỉ 2 hàng thay đổi, update count là 2; nếu chạy lại và không còn thay đổi, update count là 0.

Để tránh test phụ thuộc dữ liệu cũ, reset dữ liệu mẫu trước mỗi lần chạy và kiểm tra trạng thái của bảng sau câu `UPDATE`.

### 6.2. executeUpdate(), executeLargeUpdate() và batch

JDBC cung cấp các API sau:

- `executeUpdate()` trả update count kiểu `int` cho một câu lệnh DML.
- `executeLargeUpdate()` trả update count kiểu `long`, phù hợp khi số hàng có thể vượt giới hạn `int` và driver hỗ trợ.
- `getUpdateCount()` hoặc `getLargeUpdateCount()` lấy update count của kết quả hiện tại khi dùng API execute tổng quát.
- `executeBatch()` trả mảng số lượng cập nhật cho từng phần tử batch; một số driver có thể trả `Statement.SUCCESS_NO_INFO` hoặc `Statement.EXECUTE_FAILED` theo quy tắc JDBC.

Không giả định mọi giá trị batch đều là số hàng chính xác. Hãy xử lý các hằng số trạng thái và kiểm tra `BatchUpdateException` khi một phần batch thất bại.

## 7. Row count của các câu lệnh DML khác

Ngữ nghĩa row count của `UPDATE` dễ gây nhầm lẫn nhất, nhưng `INSERT`, `DELETE` và các câu lệnh kết hợp cũng có quy tắc riêng.

| Câu lệnh | Cách hiểu row count phổ biến |
| --- | --- |
| `INSERT` | Số hàng được chèn thành công |
| `DELETE` | Số hàng bị xóa |
| `UPDATE` mặc định | Số hàng thực sự thay đổi |
| `UPDATE` với `CLIENT_FOUND_ROWS` | Số hàng khớp điều kiện `WHERE` |
| `REPLACE` | Có thể tính 2 cho một hàng bị xóa do trùng khóa rồi chèn hàng mới |
| `INSERT ... ON DUPLICATE KEY UPDATE` | 1 khi insert mới, 2 khi cập nhật hàng trùng, 0 khi hàng trùng được giữ nguyên; với `CLIENT_FOUND_ROWS`, trường hợp giữ nguyên là 1 |

### 7.1. INSERT ... ON DUPLICATE KEY UPDATE

Ví dụ:

```sql
DROP TABLE IF EXISTS upsert_demo;

CREATE TABLE upsert_demo (
    id BIGINT UNSIGNED NOT NULL,
    label VARCHAR(50) NOT NULL,
    PRIMARY KEY (id)
) ENGINE = InnoDB;
```

Chèn hàng mới:

```sql
INSERT INTO upsert_demo (id, label)
VALUES (1, 'alpha') AS incoming
ON DUPLICATE KEY UPDATE label = incoming.label;
```

Row count là `1` vì một hàng được insert. Chạy lại với giá trị mới:

```sql
INSERT INTO upsert_demo (id, label)
VALUES (1, 'beta') AS incoming
ON DUPLICATE KEY UPDATE label = incoming.label;
```

Row count là `2` khi hàng hiện có được cập nhật. Chạy lần nữa với cùng giá trị:

```sql
INSERT INTO upsert_demo (id, label)
VALUES (1, 'beta') AS incoming
ON DUPLICATE KEY UPDATE label = incoming.label;
```

Kết quả là `0` nếu connection không gửi `CLIENT_FOUND_ROWS`; nếu cờ được gửi, kết quả là `1`. Với câu lệnh nhiều hàng, quy tắc được tính theo từng hàng rồi cộng lại.

Khi dùng cú pháp row alias sau `VALUES`, hãy bảo đảm phiên bản MySQL hỗ trợ cú pháp này. Không dùng `VALUES(column)` trong ví dụ mới nếu mục tiêu là code theo MySQL hiện đại, vì hàm đó đã deprecated trong `ON DUPLICATE KEY UPDATE` ở các phiên bản MySQL mới.

### 7.2. INSERT IGNORE và warnings

`INSERT IGNORE` có thể bỏ qua hàng vi phạm một số ràng buộc hoặc điều chỉnh giá trị lỗi thành giá trị gần nhất tùy loại lỗi, đồng thời phát sinh warning. Row count chỉ phản ánh các hàng được xử lý theo quy tắc của câu lệnh; nó không tự cho biết đầy đủ số hàng bị bỏ qua.

Sau lệnh cần điều tra, xem thông tin warning ngay:

```sql
SHOW WARNINGS;
```

Nếu cần biết số bản ghi hợp lệ, trùng lặp và bị loại, hãy thiết kế quy trình import có staging table và thống kê riêng. Đừng dùng riêng update count để làm báo cáo chất lượng dữ liệu.

## 8. LIMIT trong UPDATE đếm hàng matched

Trong một câu `UPDATE` có `LIMIT`, giới hạn áp dụng cho số hàng thỏa điều kiện được tìm thấy, không phải số hàng thực sự thay đổi.

Ví dụ:

```sql
UPDATE row_count_demo
SET status = 'PAID'
WHERE status = 'PAID'
ORDER BY id
LIMIT 3;
```

MySQL dừng sau khi tìm thấy 3 hàng thỏa điều kiện, kể cả khi cả 3 hàng đã có `status = 'PAID'` và không thay đổi. Vì vậy, update count có thể là 0 theo changed-rows semantics dù `LIMIT 3` đã tìm thấy đủ 3 hàng.

Khi cập nhật theo batch, không dùng `LIMIT` cùng với giả định rằng update count chính là số hàng đã được quét. Nếu cần tiến độ batch, thiết kế khóa phân trang hoặc checkpoint riêng, ví dụ theo khóa chính tăng dần.

## 9. Ảnh hưởng tới logic ứng dụng

### 9.1. Không dùng update count bằng 0 để kết luận bản ghi không tồn tại

Đoạn code sau có thể sai:

```java
int updated = repository.updateStatus(orderId, "PAID");
if (updated == 0) {
    throw new NotFoundException("Order not found");
}
```

Nếu đơn hàng tồn tại và đã ở trạng thái `PAID`, câu `UPDATE` có thể không làm thay đổi dữ liệu và trả 0 khi dùng changed-rows semantics. Kết luận “không tìm thấy” là sai.

Hãy xác định rõ ý nghĩa mà nghiệp vụ cần:

- Nếu cần biết có hàng nào khớp điều kiện hay không, cấu hình found-rows behavior hoặc dùng một truy vấn kiểm tra phù hợp.
- Nếu cần biết có dữ liệu thay đổi hay không, dùng changed-rows behavior.
- Nếu cần phân biệt “không tồn tại”, “đã ở trạng thái mong muốn” và “đã thay đổi”, thiết kế API/repository trả kết quả nghiệp vụ rõ ràng thay vì chỉ trả một số nguyên.

Một kiểu kết quả có thể là:

```java
public enum UpdateOutcome {
    NOT_FOUND,
    UNCHANGED,
    CHANGED
}
```

Để phân biệt ba trường hợp một cách chính xác trong môi trường có cập nhật đồng thời, cần thiết kế transaction và khóa phù hợp; không nên chạy một `SELECT` kiểm tra tách rời rồi giả định trạng thái vẫn giữ nguyên đến câu `UPDATE` tiếp theo.

### 9.2. Optimistic locking với version column

Optimistic locking thường dùng cột `version` để ngăn ghi đè thay đổi của session khác:

```sql
CREATE TABLE inventory_versioned (
    item_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;

UPDATE inventory_versioned
SET quantity = ?,
    version = version + 1
WHERE item_id = ?
  AND version = ?;
```

Nếu update count là 1, hàng đã khớp ID và version, đồng thời version được tăng. Nếu update count là 0, không có hàng khớp cả ID lẫn version hiện tại; có thể hàng không tồn tại hoặc một transaction khác đã cập nhật trước.

Vì `version` luôn tăng trong mỗi lần cập nhật thành công, hàng matched cũng là hàng changed. Do đó, trường hợp này tránh được nhầm lẫn giữa no-op update và matched row. Repository vẫn cần quyết định cách phân biệt bản ghi không tồn tại với version xung đột nếu nghiệp vụ yêu cầu hai lỗi khác nhau.

Ví dụ JDBC:

```java
String sql = """
    UPDATE inventory_versioned
    SET quantity = ?, version = version + 1
    WHERE item_id = ? AND version = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, newQuantity);
    statement.setLong(2, itemId);
    statement.setLong(3, expectedVersion);

    int changed = statement.executeUpdate();
    if (changed == 0) {
        // Không có hàng phù hợp với item_id và expectedVersion.
        // Xử lý not-found hoặc optimistic-lock conflict theo hợp đồng ứng dụng.
    } else if (changed == 1) {
        // Cập nhật thành công; version đã tăng.
    }
}
```

Nếu dùng `useAffectedRows=false`, matched-rows semantics vẫn trả 1 khi điều kiện khớp. Vì câu lệnh có tăng version, changed-rows semantics cũng trả 1. Điều này làm optimistic locking ít nhạy cảm với khác biệt cấu hình row count.

### 9.3. Update count không đồng nghĩa transaction đã commit

`executeUpdate()` trả kết quả của câu DML trong transaction hiện tại. Nếu connection đang ở chế độ transaction thủ công, kết quả đó chưa chứng minh thay đổi đã được commit bền vững.

```java
connection.setAutoCommit(false);
try {
    int changed = statement.executeUpdate();
    // Kiểm tra changed theo quy tắc nghiệp vụ.
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
```

Nếu rollback, thay đổi InnoDB trong transaction bị hoàn tác dù `executeUpdate()` trước đó trả về 1. Hãy phân biệt “câu lệnh đã tác động tới hàng trong transaction” với “transaction đã commit thành công”.

## 10. Cần cả matched count và changed count thì làm sao?

JDBC `executeUpdate()` trả về một update count, không có API chuẩn trả đồng thời hai số matched và changed. Có một số cách xử lý:

1. **Dùng công cụ dòng lệnh hoặc C API khi điều tra:** MySQL client có thể hiển thị `Rows matched`, `Changed` và `Warnings`; C API có `mysql_info()`.
2. **Chọn một semantics cho ứng dụng:** dùng `useAffectedRows` nhất quán nếu nghiệp vụ chỉ cần matched hoặc changed count.
3. **Đếm riêng có kiểm soát:** nếu cần cả hai số cho một nghiệp vụ, có thể đếm các hàng dự kiến khớp và thực hiện cập nhật trong cùng transaction với chiến lược khóa phù hợp. Cần tính đến isolation level, locking và cạnh tranh đồng thời; một `SELECT COUNT(*)` chạy trước một `UPDATE` bên ngoài transaction không bảo đảm hai con số mô tả cùng một tập hàng.
4. **Thiết kế kết quả nghiệp vụ:** với thao tác trạng thái, version hoặc quy trình duyệt, có thể lưu audit event hoặc trạng thái trước/sau để biết điều gì thực sự xảy ra.

Không nên gửi hai câu SQL rời rạc rồi cộng/trừ update count để suy ra matched rows nếu có transaction khác có thể thay đổi dữ liệu giữa hai câu lệnh.

## 11. Đây không phải SQL mode

Tên chương có “SQL mode và ngữ nghĩa”, nhưng cần phân biệt rõ:

- `sql_mode` là biến session/global điều khiển cách MySQL xử lý một số cú pháp và dữ liệu, ví dụ strict mode, `ONLY_FULL_GROUP_BY` hoặc chế độ tương thích.
- `CLIENT_FOUND_ROWS` là cờ capability ở cấp kết nối client/server.
- Connector/J `useAffectedRows` là thuộc tính driver điều khiển việc gửi cờ `CLIENT_FOUND_ROWS`.

Thay đổi `sql_mode` không tự chuyển `UPDATE` từ changed-rows sang found-rows semantics. Hai kết nối có cùng `sql_mode` nhưng khác `CLIENT_FOUND_ROWS` vẫn có thể nhận update count khác nhau cho cùng câu SQL.

Kiểm tra SQL mode riêng biệt:

```sql
SELECT @@global.sql_mode, @@session.sql_mode;
```

Kiểm tra Connector/J bằng cấu hình URL hoặc DataSource mà ứng dụng đang sử dụng. Không thể suy ra `useAffectedRows` chỉ từ `@@sql_mode`.

## 12. Quy trình kiểm tra khi hai môi trường trả row count khác nhau

Khi cùng câu `UPDATE` trả số hàng khác nhau giữa local, test và production, kiểm tra theo thứ tự:

1. Xác nhận cùng schema, dữ liệu và câu lệnh SQL.
2. Kiểm tra số hàng thực sự thỏa `WHERE` bằng truy vấn `SELECT` có cùng điều kiện.
3. Xác định có hàng nào đã mang giá trị mà `SET` đang gán hay không.
4. Xác định driver/client và phiên bản đang dùng.
5. Với Connector/J, kiểm tra `useAffectedRows` trong URL hoặc cấu hình DataSource.
6. Kiểm tra connection pool đã được tạo lại sau khi thay đổi thuộc tính kết nối chưa.
7. So sánh update count từ JDBC với output của MySQL client trên cùng dữ liệu.
8. Kiểm tra warning, transaction commit/rollback và trigger nếu kết quả vẫn không giải thích được.

Ví dụ truy vấn xác định tập hàng matched trước khi thử:

```sql
SELECT COUNT(*) AS matched_rows
FROM row_count_demo
WHERE id BETWEEN 1 AND 5;

SELECT COUNT(*) AS already_paid
FROM row_count_demo
WHERE id BETWEEN 1 AND 5
  AND status = 'PAID';
```

Hai truy vấn này giúp hiểu dữ liệu hiện tại, nhưng nếu hệ thống có cập nhật đồng thời thì chúng chỉ phản ánh snapshot/thời điểm của từng câu. Khi cần số liệu nhất quán với thao tác ghi, hãy thiết kế transaction và khóa theo yêu cầu.

## 13. Bài tập thực hành

1. Tạo bảng `row_count_demo` và dữ liệu mẫu ở phần 2. Chạy `UPDATE` đặt tất cả trạng thái thành `PAID`.
2. Quan sát output `Rows matched`, `Changed`, `Warnings` bằng MySQL command-line client.
3. Chạy lại cùng câu `UPDATE` và giải thích vì sao changed rows bằng 0 trong khi matched rows vẫn bằng 5.
4. Gọi `SELECT ROW_COUNT()` ngay sau `UPDATE`. Chạy một câu lệnh khác trước rồi gọi lại để quan sát giá trị thay đổi.
5. Tạo hai cấu hình JDBC: mặc định `useAffectedRows=false` và `useAffectedRows=true`. Chạy cùng câu `UPDATE` và so sánh `executeUpdate()`.
6. Thực hành `INSERT ... ON DUPLICATE KEY UPDATE` với ba trường hợp: insert mới, cập nhật giá trị khác và cập nhật giá trị giống hệt. Ghi nhận row count ở hai cấu hình JDBC.
7. Viết repository cập nhật trạng thái. Chứng minh vì sao `updateCount == 0` không luôn có nghĩa là bản ghi không tồn tại.
8. Thêm cột `version` và triển khai optimistic locking. Mở hai connection đọc cùng version rồi thử cập nhật lần lượt.
9. Thực hiện một `UPDATE` trong transaction, nhận update count rồi rollback. Xác minh dữ liệu cuối cùng và giải thích khác biệt giữa statement count với commit.
10. Viết tài liệu cấu hình cho ứng dụng, nêu rõ semantics row count mà code nghiệp vụ mong đợi.

## 14. Checklist trước khi đưa code vào production

- [ ] Đã xác định nghiệp vụ cần matched rows hay changed rows.
- [ ] Không dùng update count bằng 0 để kết luận bản ghi không tồn tại nếu chưa xác định semantics.
- [ ] Đã ghi nhận cấu hình `CLIENT_FOUND_ROWS` hoặc Connector/J `useAffectedRows`.
- [ ] Mọi connection trong pool dùng cấu hình row count thống nhất.
- [ ] Logic `INSERT ... ON DUPLICATE KEY UPDATE` đã được kiểm thử với trường hợp no-op.
- [ ] Batch update xử lý `SUCCESS_NO_INFO`, `EXECUTE_FAILED` và `BatchUpdateException`.
- [ ] Optimistic locking có version predicate và tăng version trong cùng câu `UPDATE`.
- [ ] Row count được phân biệt với kết quả commit/rollback của transaction.
- [ ] Các test integration bao gồm dữ liệu đã mang giá trị đích trước khi update.
- [ ] Log và metric ghi rõ ngữ nghĩa count để tránh so sánh sai giữa các môi trường.

## 15. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể giải thích bằng ví dụ vì sao matched rows có thể lớn hơn changed rows, xác định cách MySQL báo update count khi có hoặc không có `CLIENT_FOUND_ROWS`, cấu hình và kiểm tra `useAffectedRows` trong Connector/J, hiểu row count đặc biệt của upsert, và viết logic JDBC không nhầm no-op update với bản ghi không tồn tại. Bạn cũng cần biết cách dùng version column cho optimistic locking và phân biệt kết quả DML với trạng thái commit của transaction.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Information Functions (`ROW_COUNT()`)](https://dev.mysql.com/doc/refman/8.4/en/information-functions.html)
- [MySQL 8.4 Reference Manual — UPDATE Statement](https://dev.mysql.com/doc/refman/8.4/en/update.html)
- [MySQL 8.4 Reference Manual — INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
- [MySQL Connector/J Developer Guide — Connection Property `useAffectedRows`](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-connection.html)
