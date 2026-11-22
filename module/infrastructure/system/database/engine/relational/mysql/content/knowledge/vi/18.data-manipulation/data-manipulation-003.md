# INSERT IGNORE, warning và nguy cơ che giấu dữ liệu không hợp lệ

MySQL có modifier INSERT IGNORE để tiếp tục xử lý khi một số lỗi phát sinh trong lúc chèn dữ liệu. Với hàng vi phạm khóa PRIMARY KEY hoặc UNIQUE, MySQL thường bỏ qua hàng xung đột và phát warning. Với một số lỗi chuyển đổi dữ liệu, giá trị có thể bị điều chỉnh hoặc cắt về dạng có thể lưu rồi được chèn kèm warning.

Cơ chế này hữu ích khi nhập dữ liệu lặp có chủ đích, đồng bộ theo khóa nguồn hoặc chạy batch cần bỏ qua bản ghi đã tồn tại. Tuy nhiên, INSERT IGNORE có thể làm dữ liệu sai lọt vào bảng mà câu lệnh vẫn báo thành công. Nếu chỉ kiểm tra câu lệnh có lỗi hay không, hệ thống có thể bỏ sót dữ liệu bị cắt, số ngoài miền, ngày không hợp lệ hoặc bản ghi bị bỏ qua.

Trong module **DATABASE_MYSQL**, INSERT IGNORE cần được hiểu cùng ràng buộc khóa, SQL mode, warning diagnostics, transaction và quy trình kiểm soát dữ liệu nhập. Bài học này phân biệt hành vi bỏ qua duplicate với ép kiểu dữ liệu, hướng dẫn đọc warning, xử lý trong Java/JDBC và xây dựng quy trình import có thể đối soát.

## 1. INSERT IGNORE là gì?

INSERT IGNORE là một biến thể của INSERT. Từ khóa IGNORE yêu cầu MySQL hạ một số lỗi trong lúc chèn thành warning và tiếp tục xử lý các hàng còn lại, thay vì dừng toàn bộ câu lệnh ngay tại lỗi thuộc nhóm được phép bỏ qua.

Cú pháp cơ bản:

```sql
INSERT IGNORE INTO table_name (column_a, column_b)
VALUES
    (value_a1, value_b1),
    (value_a2, value_b2);
```

Cũng có thể dùng với INSERT ... SELECT:

```sql
INSERT IGNORE INTO target_table (id, name)
SELECT source_id, source_name
FROM staging_table;
```

Điều quan trọng là IGNORE không có nghĩa "bỏ qua mọi lỗi". Cú pháp SQL sai, bảng không tồn tại, thiếu quyền, lỗi kết nối và nhiều lỗi thực thi nghiêm trọng vẫn làm câu lệnh thất bại. Với từng loại ràng buộc và kiểu dữ liệu, cần kiểm tra hành vi đúng phiên bản MySQL và storage engine đang dùng.

## 2. Hai hành vi cần phân biệt: bỏ qua hàng và điều chỉnh giá trị

INSERT IGNORE thường được dùng cho hai nhóm tình huống rất khác nhau:

| Tình huống | Hành vi thường gặp | Rủi ro |
|---|---|---|
| Trùng PRIMARY KEY hoặc UNIQUE | Hàng mới bị bỏ qua, hàng cũ giữ nguyên | Không biết có bao nhiêu hàng bị bỏ nếu không đọc warning và đối soát |
| Giá trị không hợp lệ hoặc ngoài miền | Một số lỗi chuyển thành warning; giá trị có thể bị ép về giá trị gần nhất hoặc bị cắt rồi chèn | Dữ liệu đã biến đổi vẫn nằm trong bảng |
| Một số vi phạm ràng buộc khác | Có thể bị từ chối, bỏ hàng hoặc xử lý theo quy tắc riêng của lỗi và phiên bản | Không được giả định mọi constraint đều được IGNORE xử lý giống duplicate |
| Lỗi cú pháp hoặc lỗi hạ tầng | Câu lệnh vẫn thất bại | IGNORE không thay thế xử lý lỗi ứng dụng |

### 2.1. Duplicate key: bỏ qua hàng xung đột

Giả sử bảng có unique key trên email:

```sql
CREATE TABLE members (
    member_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (member_id),
    UNIQUE KEY uk_members_email (email)
) ENGINE = InnoDB;
```

Chèn một thành viên:

```sql
INSERT INTO members (email, display_name)
VALUES ('an@example.com', 'An');
```

Chèn lại cùng email:

```sql
INSERT IGNORE INTO members (email, display_name)
VALUES ('an@example.com', 'An Nguyen');

SHOW WARNINGS;
```

Do email đã tồn tại, hàng mới bị bỏ qua. Hàng hiện tại không được cập nhật thành An Nguyen. Đây là khác biệt quan trọng giữa INSERT IGNORE và INSERT ... ON DUPLICATE KEY UPDATE.

Nếu bảng không có PRIMARY KEY hoặc UNIQUE KEY phù hợp, hai hàng có cùng nội dung vẫn có thể được chèn. MySQL không tự so sánh toàn bộ các cột để quyết định chúng là duplicate.

### 2.2. Duplicate trên bất kỳ unique key nào

Nếu bảng có nhiều unique index, một hàng có thể xung đột với bất kỳ index nào trong số đó. Ví dụ bảng có unique key trên external_id và email; chỉ cần một trong hai giá trị đã tồn tại thì hàng mới có thể bị bỏ qua.

```sql
CREATE TABLE imported_accounts (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_id VARCHAR(40) NOT NULL,
    email VARCHAR(254) NOT NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uk_external_id (external_id),
    UNIQUE KEY uk_email (email)
) ENGINE = InnoDB;
```

Với dữ liệu import, cần xác định rõ khóa nào định nghĩa một bản ghi là đã tồn tại. Một hàng có external_id mới nhưng email thuộc tài khoản khác không nhất thiết là duplicate có thể bỏ qua về mặt nghiệp vụ. INSERT IGNORE không hiểu ý nghĩa của các khóa; nó chỉ tuân thủ các unique constraint.

## 3. INSERT IGNORE có thể biến dữ liệu sai thành warning

Đây là rủi ro lớn nhất khi dùng IGNORE như một cách "làm cho batch chạy thành công".

Giả sử bảng có cột tuổi kiểu TINYINT UNSIGNED:

```sql
CREATE TABLE import_probe (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_key VARCHAR(40) NOT NULL,
    email VARCHAR(254) NOT NULL,
    age TINYINT UNSIGNED NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_source_key (source_key),
    UNIQUE KEY uk_email (email)
) ENGINE = InnoDB;
```

Chèn nhiều hàng bằng INSERT IGNORE:

```sql
INSERT IGNORE INTO import_probe (source_key, email, age)
VALUES
    ('src-001', 'linh@example.com', 30),
    ('src-002', 'linh@example.com', 28),
    ('src-003', 'mai@example.com', 300),
    ('src-004', 'not-an-email', 22);

SHOW WARNINGS;
```

Các kết quả cần chú ý:

- Hàng src-001 được chèn nếu chưa tồn tại.
- Hàng src-002 xung đột unique email với src-001 nên bị bỏ qua; tên hoặc các cột khác của hàng cũ không được cập nhật.
- age = 300 vượt miền TINYINT UNSIGNED (0 đến 255). Trong trường hợp lỗi chuyển đổi số được IGNORE xử lý thành warning, giá trị có thể được điều chỉnh về giới hạn 255 và hàng vẫn được chèn.
- not-an-email vẫn là một chuỗi hợp lệ đối với VARCHAR. Nếu schema không có constraint hoặc quy tắc xác thực email, MySQL không tự hiểu đây là email sai định dạng.

Ví dụ cho thấy hai vấn đề khác nhau: một hàng có thể bị bỏ qua vì duplicate, còn hàng khác vẫn được chèn sau khi giá trị bị điều chỉnh. Warning không có nghĩa mọi hàng có warning đều bị loại khỏi bảng.

Hành vi cụ thể của giá trị sai còn phụ thuộc kiểu cột, SQL mode, constraint, storage engine và phiên bản. Hãy kiểm thử trên chính môi trường đích, đặc biệt với ngày giờ, ENUM, chuỗi quá dài, số âm cho cột UNSIGNED và CHECK constraint.

## 4. Quan hệ giữa INSERT IGNORE và strict SQL mode

Strict SQL mode được thiết kế để từ chối nhiều giá trị không hợp lệ thay vì âm thầm ép kiểu. Hai mode thường gặp:

- STRICT_TRANS_TABLES: strict behavior cho transactional table và có quy tắc riêng với non-transactional table.
- STRICT_ALL_TABLES: strict behavior rộng hơn cho mọi storage engine.

Kiểm tra SQL mode của server và session:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

Với strict mode, một INSERT thông thường có thể thất bại khi dữ liệu bị cắt hoặc nằm ngoài miền. Khi thêm IGNORE, một số lỗi dữ liệu vốn sẽ là lỗi strict có thể bị chuyển thành warning và giá trị được điều chỉnh để tiếp tục chèn.

Ví dụ:

```sql
INSERT INTO import_probe (source_key, email, age)
VALUES ('src-005', 'hoa@example.com', 300);
```

Trong strict mode, thao tác này thường bị từ chối do age ngoài miền. Nếu đổi thành INSERT IGNORE, MySQL có thể phát warning và lưu giá trị đã điều chỉnh.

Không nên tắt strict mode để batch chạy qua. Cũng không nên cho rằng strict mode bảo vệ dữ liệu tuyệt đối khi câu lệnh dùng IGNORE. Muốn đảm bảo dữ liệu đúng, cần xác thực trước khi ghi và kiểm tra warning sau khi ghi.

## 5. Đọc warning ngay sau câu lệnh

Sau INSERT IGNORE, chạy SHOW WARNINGS ngay để xem thông tin chẩn đoán:

```sql
INSERT IGNORE INTO members (email, display_name)
VALUES
    ('an@example.com', 'Another An'),
    ('binh@example.com', 'Binh');

SHOW WARNINGS;
```

SHOW WARNINGS trả về các cột:

| Cột | Ý nghĩa |
|---|---|
| Level | Mức độ: Note, Warning hoặc Error |
| Code | Mã lỗi MySQL |
| Message | Nội dung mô tả |

Một số mã thường gặp trong quá trình nhập dữ liệu:

| Mã | Tình huống thường gặp |
|---:|---|
| 1062 | Duplicate entry cho PRIMARY KEY hoặc UNIQUE |
| 1264 | Giá trị số ngoài miền |
| 1265 | Data truncated |
| 1366 | Incorrect value hoặc lỗi chuyển đổi kiểu dữ liệu trong một số ngữ cảnh |

Mã và nội dung thực tế cần được đọc từ server; không nên chỉ dựa vào một danh sách mã cố định để phân loại mọi phiên bản.

Có thể xem tổng số warning của câu lệnh gần nhất:

```sql
SHOW COUNT(*) WARNINGS;
```

Hoặc xem một phần danh sách:

```sql
SHOW WARNINGS LIMIT 100;
```

### 5.1. Đọc warning trước khi chạy câu lệnh khác

Hãy gọi SHOW WARNINGS ngay sau INSERT IGNORE. Một câu lệnh tiếp theo có thể thay thế diagnostics area của câu lệnh trước, khiến bạn không còn đọc được đầy đủ thông tin cần kiểm tra.

Nếu batch có nhiều warning, số message lưu để hiển thị có thể bị giới hạn bởi biến max_error_count. Vì vậy, danh sách SHOW WARNINGS có thể không chứa toàn bộ message khi số lượng quá lớn. Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'max_error_count';
```

Không coi số warning là số hàng bị bỏ qua. Một hàng có thể phát nhiều warning; warning cũng có thể đến từ hàng đã được chèn với giá trị điều chỉnh. Cần kết hợp warning với số hàng bị ảnh hưởng và dữ liệu staging để phân loại chính xác.

## 6. Phân biệt INSERT IGNORE, ON DUPLICATE KEY UPDATE và REPLACE

Ba cách này có mục tiêu khác nhau:

| Câu lệnh | Khi duplicate key | Có thay đổi hàng cũ? | Đặc điểm |
|---|---|---|---|
| INSERT IGNORE | Bỏ qua hàng xung đột và phát warning | Không | Phù hợp khi duplicate là trường hợp có thể chấp nhận và cần bỏ qua |
| INSERT ... ON DUPLICATE KEY UPDATE | Chạy nhánh UPDATE | Có | Phù hợp cho upsert khi cần cập nhật hàng đã tồn tại |
| REPLACE | Xóa hàng xung đột rồi chèn hàng mới theo semantics của REPLACE | Có, có thể tác động FK/trigger và auto-increment | Không phải một dạng UPDATE đơn giản |

Ví dụ ON DUPLICATE KEY UPDATE:

```sql
INSERT INTO members (email, display_name)
VALUES ('an@example.com', 'An Nguyen')
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name);
```

Cú pháp VALUES(column) trong nhánh UPDATE đã bị deprecated ở các phiên bản MySQL mới; với MySQL 8.0.19 trở lên, có thể dùng row alias theo cú pháp được phiên bản hỗ trợ. Hãy kiểm tra cú pháp đúng phiên bản khi triển khai.

Ví dụ REPLACE:

```sql
REPLACE INTO members (member_id, email, display_name)
VALUES (1, 'an@example.com', 'An New');
```

REPLACE có thể xóa hàng cũ gây xung đột rồi chèn hàng mới. Điều này có thể tạo tác động phụ đến khóa ngoại, trigger, audit và auto-increment. Không dùng REPLACE chỉ để tránh lỗi duplicate.

## 7. INSERT IGNORE không phải cơ chế cập nhật hoặc đồng bộ hoàn chỉnh

Nếu hàng đã tồn tại, INSERT IGNORE giữ nguyên dữ liệu cũ. Ví dụ:

```sql
INSERT IGNORE INTO members (email, display_name)
VALUES ('an@example.com', 'An Updated');
```

Nếu email đã tồn tại với display_name = 'An', tên sẽ không đổi thành An Updated. Ứng dụng cần chọn rõ một trong các chính sách:

- Chỉ chèn mới; duplicate là bản ghi đã xử lý và được bỏ qua.
- Cập nhật một số trường khi khóa nghiệp vụ đã tồn tại.
- Từ chối nếu cùng khóa nhưng nội dung khác.
- Ghi nhận xung đột để người hoặc quy trình nghiệp vụ giải quyết.

Không dùng INSERT IGNORE như một cách đồng bộ dữ liệu hai chiều. Nó không so sánh phiên bản bản ghi, thời điểm cập nhật hoặc nguồn dữ liệu đáng tin cậy.

## 8. Những lỗi không nên kỳ vọng IGNORE xử lý

IGNORE chỉ ảnh hưởng đến một số lỗi trong quá trình chèn. Nó không phải cơ chế bắt mọi exception.

Các trường hợp như lỗi cú pháp, thiếu bảng, thiếu quyền, lỗi kết nối, deadlock hoặc lỗi thực thi nghiêm trọng vẫn cần được xử lý theo quy trình thông thường. Với lỗi foreign key, CHECK và các ràng buộc khác, không suy diễn hành vi chỉ từ việc tên câu lệnh có IGNORE; cần kiểm tra tài liệu đúng phiên bản và thử trong database lab.

Đặc biệt, IGNORE không tắt PRIMARY KEY, UNIQUE, NOT NULL, CHECK hay FOREIGN KEY. Ràng buộc vẫn là một phần của tính toàn vẹn dữ liệu; một số vi phạm có thể bị chuyển thành warning hoặc làm hàng bị bỏ qua theo quy tắc của server, trong khi các trường hợp khác vẫn phát lỗi.

Không bỏ qua SQLWarning ở tầng ứng dụng. Một thao tác JDBC có thể trả về số hàng bị ảnh hưởng mà không ném SQLException, trong khi dữ liệu đã bị điều chỉnh hoặc hàng đã bị loại.

## 9. Dùng INSERT IGNORE trong transaction

Với InnoDB, các hàng được chèn thành công trong một câu INSERT IGNORE thuộc transaction hiện tại. Những hàng bị bỏ qua không tạo bản ghi. Warning không tự động rollback transaction.

Ví dụ:

```sql
START TRANSACTION;

INSERT IGNORE INTO members (email, display_name)
VALUES
    ('an@example.com', 'An'),
    ('binh@example.com', 'Binh'),
    ('an@example.com', 'Duplicate An');

SHOW WARNINGS;

-- Ứng dụng hoặc người vận hành phân loại warning:
-- Nếu chỉ có duplicate đã được chấp nhận thì COMMIT.
-- Nếu có warning dữ liệu ngoài dự kiến thì ROLLBACK.

COMMIT;
```

Trong ví dụ, quyết định COMMIT hay ROLLBACK là bước có điều kiện ở ứng dụng hoặc quy trình vận hành. SQL không tự động rollback chỉ vì có warning.

Nếu phát hiện warning ngoài danh sách cho phép, có thể rollback toàn bộ phần ghi trong transaction InnoDB. Cần lưu ý rollback dữ liệu không đồng nghĩa thu hồi các giá trị AUTO_INCREMENT đã cấp; khoảng trống ID vẫn có thể xuất hiện.

Không dựa vào transaction để làm cho bảng non-transactional có thể rollback. Nếu cần atomicity, dùng InnoDB và kiểm tra storage engine của bảng đích.

## 10. Quy trình import an toàn với staging table

Một batch import đáng tin cậy cần phân biệt dữ liệu hợp lệ, duplicate được chấp nhận và dữ liệu bị từ chối. Đừng đưa dữ liệu thô trực tiếp vào bảng nghiệp vụ bằng INSERT IGNORE rồi xem câu lệnh thành công là hoàn tất.

Quy trình đề xuất:

1. **Nhận dữ liệu vào staging.** Lưu source_row_id, source_key và giá trị thô; giữ được khả năng truy ngược về file hoặc message nguồn.
2. **Kiểm tra cấu trúc.** Xác nhận số cột, kiểu dữ liệu, encoding, định dạng ngày và trường bắt buộc.
3. **Xác thực nghiệp vụ.** Kiểm tra miền số, độ dài, format, quan hệ tham chiếu và quy tắc nghiệp vụ.
4. **Phân loại bản ghi.** Gắn trạng thái VALID, DUPLICATE, INVALID hoặc NEEDS_REVIEW cùng lý do cụ thể.
5. **Chỉ chuyển dữ liệu hợp lệ.** Dùng INSERT thông thường khi không kỳ vọng duplicate; dùng INSERT IGNORE nếu duplicate theo khóa nguồn là trường hợp đã được cho phép.
6. **Đọc warning.** Phân loại duplicate key và warning chuyển đổi; warning ngoài dự kiến phải làm batch thất bại hoặc chuyển vào quy trình xử lý.
7. **Đối soát số lượng.** So sánh tổng dòng nguồn với số dòng hợp lệ đã chèn, duplicate được chấp nhận, invalid bị từ chối và dòng cần review.
8. **Lưu audit.** Ghi batch_id, nguồn, thời điểm, số hàng, warning, kết quả và lý do reject.
9. **Commit có kiểm soát.** Chỉ commit khi các điều kiện chất lượng và đối soát đạt yêu cầu.

Ví dụ staging giữ dữ liệu thô:

```sql
CREATE TABLE member_import_stage (
    batch_id BIGINT NOT NULL,
    source_row_id BIGINT NOT NULL,
    source_key VARCHAR(80) NULL,
    email_raw TEXT NULL,
    age_raw VARCHAR(40) NULL,
    validation_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    reject_reason VARCHAR(255) NULL,
    PRIMARY KEY (batch_id, source_row_id)
) ENGINE = InnoDB;
```

Sau khi xác thực bằng ứng dụng hoặc câu truy vấn phù hợp, chuyển những hàng VALID sang bảng đích. Không ép kiểu từ chuỗi thô mà không kiểm tra trước; nếu chuyển đổi thất bại, dữ liệu có thể bị cắt hoặc thay đổi tùy SQL mode.

Ví dụ chuyển các hàng đã được đánh dấu hợp lệ:

```sql
INSERT INTO members (email, display_name)
SELECT
    s.email_raw,
    s.source_key
FROM member_import_stage AS s
WHERE s.batch_id = 20261119
  AND s.validation_status = 'VALID';
```

Nếu quy trình cho phép cùng một source_key được gửi lại, hãy thiết kế unique key theo định danh nguồn và dùng INSERT IGNORE một cách có chủ đích. Vẫn phải kiểm tra warning sau mỗi batch.

## 11. Đối soát duplicate và tính idempotent

Import idempotent nghĩa là chạy lại cùng một batch không tạo thêm bản ghi nghiệp vụ ngoài ý muốn. Cách chắc chắn hơn là dùng khóa nguồn ổn định và unique constraint:

```sql
ALTER TABLE members
    ADD COLUMN source_system VARCHAR(40) NOT NULL,
    ADD COLUMN source_member_id VARCHAR(80) NOT NULL,
    ADD UNIQUE KEY uk_member_source (
        source_system,
        source_member_id
    );
```

Thiết kế thực tế phải xử lý dữ liệu cũ, nullability và khả năng source ID bị tái sử dụng trước khi thêm constraint.

Sau đó, INSERT IGNORE có thể giúp bỏ qua các bản ghi đã nhập từ cùng nguồn. Nhưng cần phân biệt hai trường hợp:

- Cùng source_system và source_member_id, nội dung giống nhau: có thể là lần gửi lại hợp lệ.
- Cùng khóa nguồn nhưng email hoặc dữ liệu nghiệp vụ khác: có thể là xung đột cập nhật, cần xử lý theo version hoặc chính sách đồng bộ.

Unique key chỉ bảo đảm tính duy nhất của khóa. Nó không chứng minh các cột còn lại giống nhau hoặc dữ liệu mới hơn. Muốn đồng bộ cập nhật, cần version, updated_at đáng tin cậy hoặc quy tắc xử lý xung đột.

Tránh dùng SELECT trước để kiểm tra duplicate rồi mới INSERT như lớp bảo vệ duy nhất:

```sql
SELECT 1
FROM members
WHERE email = 'an@example.com';
```

Giữa SELECT và INSERT, một transaction khác có thể chèn cùng email. Đây là race condition. UNIQUE constraint là lớp bảo vệ cuối cùng ở database. Có thể dùng INSERT IGNORE để xử lý duplicate đã dự kiến, nhưng phải đọc warning để biết điều gì đã xảy ra.

## 12. Theo dõi kết quả ở Java/JDBC

JDBC có thể trả số hàng bị ảnh hưởng mà không ném SQLException khi INSERT IGNORE gặp duplicate hoặc một số lỗi được hạ thành warning. Vì vậy, chỉ gọi executeUpdate() rồi bỏ qua warning là chưa đủ.

Ví dụ:

```java
String sql = """
    INSERT IGNORE INTO members (email, display_name)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    ps.setString(2, displayName);

    int affectedRows = ps.executeUpdate();

    SQLWarning warning = ps.getWarnings();
    while (warning != null) {
        System.err.printf(
            "MySQL warning: code=%d, state=%s, message=%s%n",
            warning.getErrorCode(),
            warning.getSQLState(),
            warning.getMessage()
        );
        warning = warning.getNextWarning();
    }

    ps.clearWarnings();

    System.out.println("Affected rows: " + affectedRows);
}
```

Đoạn code giả định đã import các kiểu JDBC cần thiết từ java.sql. Với batch insert, driver có thể trả mảng update count và warning theo cách phụ thuộc cấu hình/phiên bản Connector/J; cần kiểm thử cách lấy diagnostics trên đúng driver đang triển khai.

Trong ứng dụng production:

- Ghi log warning có batch ID, source row ID nếu có và mã lỗi.
- Phân loại warning được chấp nhận (ví dụ duplicate theo khóa nguồn) với warning dữ liệu (truncation, out-of-range, conversion).
- Không log dữ liệu cá nhân hoặc bí mật vượt quá chính sách bảo vệ dữ liệu.
- Nếu warning không thuộc danh sách cho phép, đánh dấu batch thất bại và rollback transaction khi còn có thể.
- Đối soát số hàng được chèn với số hàng nguồn đã phân loại.

## 13. Đếm hàng và đọc kết quả đúng cách

Không đồng nhất các đại lượng sau:

| Đại lượng | Cho biết điều gì |
|---|---|
| Số hàng nguồn | Có bao nhiêu bản ghi được gửi vào batch |
| Affected rows | Số hàng MySQL báo bị tác động theo semantics của câu lệnh và driver |
| Warning count | Có bao nhiêu warning/note/error diagnostics được ghi nhận cho statement |
| Số hàng thực tế trong bảng | Trạng thái dữ liệu sau thao tác |
| Số hàng duplicate | Cần phân loại theo khóa và nguồn, không suy ra đơn giản từ warning count |

Một câu INSERT IGNORE có thể chèn một số hàng, bỏ qua một số hàng duplicate và chèn thêm hàng có giá trị đã được điều chỉnh. Vì vậy, phép tính "số nguồn trừ affected rows bằng số duplicate" không đáng tin cậy nếu batch có warning chuyển đổi hoặc nhiều loại lỗi.

Nếu cần số liệu chính xác theo từng dòng, hãy gắn source_row_id trong staging và lưu trạng thái xử lý riêng. Warning tổng hợp của một statement không phải một bảng audit đầy đủ.

## 14. Các tình huống nên và không nên dùng INSERT IGNORE

| Tình huống | Khuyến nghị |
|---|---|
| Nhận lại message đã xử lý, unique source key xác định idempotency | Có thể dùng nếu duplicate là kết quả được mong đợi và warning được kiểm soát |
| Import danh sách mà email trùng được phép bỏ qua theo quy tắc rõ ràng | Có thể dùng, nhưng phải ghi nhận số hàng bị bỏ và đối soát |
| Dữ liệu có thể chứa chuỗi quá dài hoặc số ngoài miền | Không dùng IGNORE để "sửa hộ"; validate và reject trước |
| Dữ liệu ngày giờ chưa rõ format | Chuẩn hóa và xác thực trước khi ghi |
| Đồng bộ cần cập nhật hàng cũ | Dùng upsert với chính sách cập nhật có version hoặc timestamp |
| Cần đảm bảo tất cả hàng được chèn thành công | Dùng INSERT thường trong transaction và xử lý lỗi rõ ràng |
| Không có unique key để xác định duplicate | Thiết kế khóa nghiệp vụ trước; IGNORE không tự nhận diện hàng trùng |

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ IGNORE chỉ bỏ duplicate | Giá trị sai có thể bị cắt hoặc ép kiểu rồi vẫn được chèn | Đọc toàn bộ warning và validate trước |
| Nghĩ câu lệnh không ném lỗi nghĩa là mọi hàng hợp lệ | Một phần hàng có thể bị bỏ hoặc bị biến đổi | Đối soát nguồn, affected rows và staging |
| Dùng IGNORE để thay strict mode | Dữ liệu không hợp lệ có thể đi vào bảng | Giữ strict mode, xác thực trước khi ghi |
| Không có unique key nhưng kỳ vọng tự loại trùng | Hàng giống nhau vẫn được chèn | Tạo unique constraint theo khóa nghiệp vụ |
| Dùng IGNORE để cập nhật dữ liệu cũ | Hàng cũ không được cập nhật | Dùng ON DUPLICATE KEY UPDATE hoặc quy trình đồng bộ |
| Chỉ đọc warning count | Không biết warning thuộc loại nào | Đọc Level, Code và Message |
| Chạy câu lệnh khác trước SHOW WARNINGS | Mất diagnostics cần kiểm tra | Đọc warning ngay sau statement |
| Cho rằng warning count bằng số hàng bị bỏ | Một hàng có thể có nhiều warning hoặc vẫn được chèn | Dùng staging để đối soát theo dòng |
| Dùng REPLACE như UPDATE | Hàng cũ có thể bị xóa rồi chèn lại | Chọn câu lệnh theo semantics và kiểm tra FK/trigger |

## 16. Checklist vận hành cho batch INSERT IGNORE

Trước khi chạy:

- Xác định khóa PRIMARY KEY/UNIQUE nào dùng để nhận diện duplicate.
- Xác định duplicate nào được chấp nhận và duplicate nào là xung đột nghiệp vụ.
- Kiểm tra SQL mode, kiểu cột, nullability, default và constraint.
- Xác thực định dạng, độ dài, miền số và ngày giờ trước khi ghi.
- Chạy thử trên staging hoặc một batch nhỏ đại diện.
- Chuẩn bị cách lấy warning từ SQL client hoặc JDBC.

Sau khi chạy:

- Đọc SHOW WARNINGS ngay sau statement.
- Phân loại duplicate warning và warning dữ liệu.
- Kiểm tra affected rows và tổng số dòng trong batch.
- Đối soát các hàng bị bỏ, hàng bị reject và hàng đã chèn.
- Rollback transaction nếu có warning ngoài danh sách cho phép.
- Lưu audit log và thông tin batch để có thể điều tra hoặc chạy lại an toàn.

## 17. Ghi nhớ

- INSERT IGNORE hạ một số lỗi khi chèn thành warning và cho phép statement tiếp tục.
- Duplicate PRIMARY KEY/UNIQUE thường khiến hàng xung đột bị bỏ qua; dữ liệu hàng cũ không được cập nhật.
- Một số lỗi chuyển đổi có thể làm giá trị bị cắt hoặc ép về giới hạn rồi vẫn được chèn.
- IGNORE không có nghĩa bỏ qua mọi lỗi và không tắt các ràng buộc dữ liệu.
- Strict SQL mode vẫn quan trọng; IGNORE có thể thay đổi cách xử lý một số lỗi vốn sẽ bị strict mode từ chối.
- Đọc SHOW WARNINGS ngay sau statement; phân tích Level, Code và Message.
- Warning count không bằng số hàng bị bỏ và không cho biết đầy đủ hàng nào đã bị biến đổi.
- Dùng unique key ổn định để hỗ trợ idempotent import; không dựa vào SELECT trước INSERT vì có race condition.
- Dùng staging table để xác thực, phân loại, reject và đối soát theo source row.
- Trong Java/JDBC, kiểm tra SQLWarning chain sau executeUpdate hoặc batch execution.
- Chỉ chấp nhận warning đã được định nghĩa trước; warning dữ liệu ngoài dự kiến phải được xử lý như một lỗi chất lượng dữ liệu.

INSERT IGNORE là công cụ hữu ích khi việc bỏ qua duplicate đã được xác định rõ. Hãy kết hợp nó với strict mode, constraint, warning diagnostics và đối soát theo từng dòng để batch import có thể chạy lặp an toàn mà không âm thầm làm giảm chất lượng dữ liệu.

