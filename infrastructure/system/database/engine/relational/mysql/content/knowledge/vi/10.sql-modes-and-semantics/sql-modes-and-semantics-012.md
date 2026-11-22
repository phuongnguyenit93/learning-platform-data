# Kiểm chứng hành vi SQL khi thay đổi phiên bản hoặc cấu hình phiên

Một câu SQL không phải lúc nào cũng cho cùng kết quả trên mọi MySQL server. Hành vi của nó có thể thay đổi theo phiên bản MySQL, `sql_mode`, múi giờ, character set, collation, isolation level, `autocommit` và các biến cấu hình gắn với session. Vì vậy, khi nâng cấp server, thay đổi cấu hình hoặc chuyển ứng dụng sang connection pool, cần kiểm chứng hành vi thực tế bằng một bộ thử nghiệm có thể lặp lại.

Trong module `DATABASE_MYSQL`, điều này liên quan trực tiếp tới thiết kế bảng, kiểu dữ liệu, truy vấn SQL, transaction và vận hành. Một thay đổi cấu hình có thể khiến dữ liệu trước đây được chấp nhận nay bị từ chối, làm thay đổi cách so sánh chuỗi, cách nhóm dữ liệu hoặc cách đọc thời gian. Mục tiêu của bài học là giúp bạn ghi nhận môi trường, cô lập từng biến, xây dựng ca kiểm thử có kết quả mong đợi và triển khai thay đổi an toàn.

## 1. Vì sao cùng câu SQL có thể cho kết quả khác nhau?

Có bốn nhóm yếu tố chính:

1. **Phiên bản server:** MySQL có thể thay đổi cú pháp được hỗ trợ, giá trị mặc định, cách kiểm tra dữ liệu, optimizer và hành vi của một số hàm qua các phiên bản.
2. **Cấu hình toàn cục:** biến global đặt mặc định cho các session mới hoặc điều khiển hành vi chung của server. Thay đổi global thường không tự cập nhật các session đã mở.
3. **Cấu hình session:** mỗi connection có thể có `sql_mode`, `time_zone`, charset/collation, isolation level và trạng thái transaction riêng.
4. **Đối tượng được tạo trước đó:** stored procedure, function, trigger và event có thể giữ `sql_mode` tại thời điểm được tạo; thay đổi session của client không nhất thiết thay đổi cách các đối tượng đó chạy.

Ví dụ, câu `INSERT` ghi một chuỗi dài hơn `VARCHAR` có thể bị từ chối trong strict mode, nhưng có thể được cắt và phát warning trong chế độ không strict. Một truy vấn aggregate có thể chạy ở server không bật `ONLY_FULL_GROUP_BY` nhưng bị từ chối ở server bật mode đó. Cùng một giá trị `TIMESTAMP` có thể hiển thị khác nhau khi hai connection dùng `time_zone` khác nhau.

## 2. Ghi nhận fingerprint của môi trường trước khi thử

Trước khi so sánh hai server hoặc hai cấu hình, hãy ghi lại phiên bản và các biến quan trọng. Nếu không có fingerprint, bạn khó xác định khác biệt đến từ server hay từ session của ứng dụng.

```sql
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution,
    @@hostname AS server_host,
    @@port AS server_port,
    CONNECTION_ID() AS connection_id;

SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode,
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@GLOBAL.autocommit AS global_autocommit,
    @@SESSION.autocommit AS session_autocommit,
    @@character_set_client AS character_set_client,
    @@character_set_connection AS character_set_connection,
    @@collation_connection AS collation_connection;

SHOW VARIABLES LIKE 'transaction_isolation';
SHOW VARIABLES LIKE 'tx_isolation';
SHOW VARIABLES LIKE 'innodb_strict_mode';
```

`transaction_isolation` là tên biến dùng trong MySQL 8.0; các bản MySQL 5.7 thường dùng `tx_isolation`. Dùng `SHOW VARIABLES` giúp kiểm tra tên nào tồn tại trên phiên bản đang chạy. `innodb_strict_mode` là cấu hình riêng của InnoDB, không phải thành phần của `sql_mode`.

Nên lưu kết quả fingerprint cùng phiên bản ứng dụng, migration schema và thời điểm kiểm thử. Khi so sánh dev, test, staging và production, kiểm tra cả server lẫn session được tạo bởi driver hoặc connection pool.

## 3. Phân biệt GLOBAL và SESSION

Nhiều biến MySQL có hai phạm vi:

- `GLOBAL`: giá trị cấp server. Khi thay đổi, thường dùng làm giá trị mặc định cho connection mở sau đó.
- `SESSION`: giá trị của connection hiện tại. Thay đổi chỉ tác động tới session đang chạy.

Kiểm tra riêng hai phạm vi:

```sql
SELECT @@GLOBAL.sql_mode;
SELECT @@SESSION.sql_mode;
```

Đặt cấu hình cho connection hiện tại:

```sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';
```

Đặt giá trị global cho các connection mới (cần quyền quản trị phù hợp):

```sql
SET GLOBAL sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';
```

Sau lệnh `SET GLOBAL`, hãy mở một connection mới để kiểm tra giá trị mặc định đã được nhận. Connection đang chạy cần được kiểm tra riêng; không giả định nó tự đổi `@@SESSION.sql_mode`.

### Thay đổi một mode mà không vô tình xóa các mode khác

Gán trực tiếp `SET SESSION sql_mode = '...'` thay thế toàn bộ danh sách mode của session. Nếu chỉ muốn thêm hoặc bỏ một mode, có thể dùng helper trong schema `sys` nếu môi trường có cài đặt:

```sql
SET SESSION sql_mode = sys.list_add(@@SESSION.sql_mode, 'ANSI_QUOTES');
SET SESSION sql_mode = sys.list_drop(@@SESSION.sql_mode, 'ANSI_QUOTES');
```

Nếu không dùng `sys.list_add()` hoặc `sys.list_drop()`, hãy đọc danh sách hiện tại, tạo danh sách mới có kiểm soát và xác nhận lại sau khi gán. Tránh nối chuỗi tùy tiện khiến mode bị lặp hoặc vô tình bị bỏ sót.

## 4. Thay đổi SQL mode tạm thời và lâu dài

### Thay đổi tạm thời trong một session

Đây là cách phù hợp để kiểm thử hành vi mà không ảnh hưởng connection khác:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;

-- Chạy các ca kiểm thử tại đây.

SET SESSION sql_mode = @saved_sql_mode;
```

Biến `@saved_sql_mode` là user variable của connection hiện tại. Nếu client dừng giữa chừng hoặc connection bị đóng, session kết thúc; tuy nhiên trong script kiểm thử nên luôn có bước khôi phục để các câu lệnh tiếp theo không bị ảnh hưởng ngoài dự kiến.

### Thay đổi runtime ở cấp server

`SET GLOBAL` thay đổi giá trị global trong bộ nhớ, nhưng không tự ghi vào cấu hình khởi động. Sau khi restart, giá trị có thể quay lại cấu hình trong file option hoặc nguồn cấu hình khác.

### Lưu cấu hình qua lần khởi động lại

Trên MySQL 8.0.11 trở lên, `SET PERSIST` có thể thay đổi biến global động và lưu giá trị vào file cấu hình persist để giữ qua restart:

```sql
SET PERSIST sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';
```

`SET PERSIST_ONLY` lưu giá trị cho lần khởi động tiếp theo mà không áp dụng thay đổi runtime; lệnh này hữu ích cho một số biến chỉ có thể thay đổi lúc khởi động. Không phải mọi biến đều hỗ trợ cùng phạm vi hoặc cùng cách thay đổi. Hãy kiểm tra tài liệu của biến và phiên bản trước khi dùng.

Trong môi trường production, cấu hình nên được quản lý qua quy trình triển khai có kiểm soát (configuration management, option file hoặc nền tảng quản trị). Tránh để cùng một biến được đặt khác nhau ở nhiều nguồn mà không biết nguồn nào có ưu tiên.

## 5. Những SQL mode có thể thay đổi hành vi truy vấn

`sql_mode` là danh sách các chế độ ảnh hưởng cách MySQL phân tích SQL và kiểm tra dữ liệu. Một số mode quan trọng:

| SQL mode | Hành vi có thể thay đổi | Rủi ro cần kiểm tra |
|---|---|---|
| `STRICT_TRANS_TABLES` | Từ chối nhiều giá trị không hợp lệ hoặc bị cắt đối với bảng transactional; một số trường hợp với bảng non-transactional có quy tắc xử lý khác | Import dữ liệu cũ có thể bắt đầu lỗi. |
| `STRICT_ALL_TABLES` | Áp dụng strict validation cho cả bảng non-transactional theo quy tắc mode | Batch insert có thể dừng hoặc để lại phần đã ghi ở engine không transactional. |
| `ONLY_FULL_GROUP_BY` | Kiểm tra các cột không aggregate trong truy vấn nhóm | Truy vấn báo cáo trước đây chạy có thể bị từ chối. |
| `ANSI_QUOTES` | Dấu `"` được hiểu là quote cho identifier thay vì string literal | SQL tạo động hoặc câu lệnh dùng double quote cho chuỗi có thể hỏng. |
| `NO_BACKSLASH_ESCAPES` | Backslash không còn là escape character trong string literal | Literal và SQL được tạo từ ứng dụng có thể thay đổi ý nghĩa. |
| `PIPES_AS_CONCAT` | `||` được hiểu là phép nối chuỗi thay vì OR logic | Biểu thức cũ có thể trả kết quả khác. |
| `NO_ENGINE_SUBSTITUTION` | Không âm thầm thay storage engine khi engine yêu cầu không khả dụng | DDL có thể báo lỗi thay vì tạo bảng bằng engine mặc định khác. |
| `ALLOW_INVALID_DATES` | Nới một số kiểm tra ngày/tháng trong phạm vi mode cho phép | Dữ liệu ngày không hợp lệ có thể lọt vào hệ thống. |

Danh sách mode được hỗ trợ và trạng thái deprecated thay đổi theo phiên bản. Một số mode cũ đã bị loại bỏ hoặc không còn tác dụng như trước; không sao chép nguyên một danh sách `sql_mode` từ hướng dẫn của phiên bản khác mà không kiểm tra server đích.

### Strict mode và dữ liệu không hợp lệ

Strict mode giúp phát hiện sớm dữ liệu sai thay vì âm thầm cắt hoặc ép giá trị. Tuy nhiên, `STRICT_TRANS_TABLES` và `STRICT_ALL_TABLES` không hoàn toàn giống nhau khi thao tác trên engine non-transactional hoặc batch nhiều hàng. `INSERT IGNORE` và `UPDATE IGNORE` cũng có thể hạ một số lỗi xuống warning, vì vậy cần kiểm tra cả câu lệnh thực tế chứ không chỉ mode.

### `ONLY_FULL_GROUP_BY`

Mode này yêu cầu cột trong `SELECT` của truy vấn aggregate phải được aggregate, có trong `GROUP BY` hoặc được chứng minh phụ thuộc hàm vào các cột nhóm theo quy tắc MySQL. Nếu ứng dụng dựa vào việc chọn tùy ý một giá trị trong nhóm, kết quả có thể không xác định và bị từ chối khi mode được bật.

## 6. Kiểm chứng strict mode bằng dữ liệu thử nghiệm

Tạo bảng trong schema riêng dành cho kiểm thử:

```sql
CREATE TABLE mode_probe (
    id INT NOT NULL PRIMARY KEY,
    label VARCHAR(4) NOT NULL
) ENGINE=InnoDB;
```

Lưu mode hiện tại rồi chạy riêng câu `INSERT` trong strict mode. Câu lệnh này được kỳ vọng báo lỗi vì `label` dài hơn giới hạn cột:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = 'STRICT_TRANS_TABLES';
```

Chạy riêng câu lệnh sau; đây là lỗi dự kiến:

```sql
INSERT INTO mode_probe (id, label)
VALUES (1, 'ABCDE');
```

Ngay sau lỗi, đọc warning/error của statement:

```sql
SHOW WARNINGS;
```

Sau khi ghi nhận lỗi strict mode, chạy phần non-strict trong cùng connection:

```sql
SET SESSION sql_mode = '';

INSERT INTO mode_probe (id, label)
VALUES (2, 'ABCDE');

SHOW WARNINGS;

SELECT id, label, CHAR_LENGTH(label) AS label_length
FROM mode_probe
ORDER BY id;

SET SESSION sql_mode = @saved_sql_mode;
```

Trong strict mode, giá trị vượt độ dài cột thường bị từ chối. Trong chế độ không strict, MySQL có thể cắt giá trị xuống độ dài cho phép và phát warning. `SHOW WARNINGS` phải được chạy ngay sau câu lệnh cần kiểm tra vì câu SQL tiếp theo có thể thay đổi danh sách warning hiện tại.

Đừng chạy ví dụ này trên bảng nghiệp vụ: mục đích là quan sát sự khác nhau giữa lỗi và warning trong một bảng thử nghiệm có thể xóa bỏ.

## 7. Kiểm chứng `ONLY_FULL_GROUP_BY`

Tạo dữ liệu mẫu:

```sql
CREATE TABLE sales_mode_probe (
    customer_id INT NOT NULL,
    region VARCHAR(30) NOT NULL,
    amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;

INSERT INTO sales_mode_probe (customer_id, region, amount)
VALUES
    (1, 'North', 100.00),
    (1, 'North', 150.00),
    (2, 'South', 200.00);
```

Truy vấn có thể bị từ chối khi `ONLY_FULL_GROUP_BY` bật. Lưu mode trước, sau đó chạy riêng câu `SELECT` để ghi nhận lỗi:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = 'ONLY_FULL_GROUP_BY';

SELECT customer_id, region, SUM(amount)
FROM sales_mode_probe
GROUP BY customer_id;
```

Sau khi ghi nhận lỗi dự kiến, khôi phục mode:

```sql
SET SESSION sql_mode = @saved_sql_mode;
```

`region` không nằm trong `GROUP BY` và không được aggregate. Nếu nghiệp vụ muốn hiển thị vùng, cần xác định quan hệ dữ liệu rõ ràng. Nếu mỗi customer chỉ có một region, có thể mô hình hóa bằng khóa và quan hệ phù hợp; không nên tắt mode để lấy một giá trị tùy ý.

Một truy vấn xác định hơn:

```sql
SELECT customer_id, region, SUM(amount) AS total_amount
FROM sales_mode_probe
GROUP BY customer_id, region;
```

Truy vấn này nhóm theo cả customer và region nên kết quả có ngữ nghĩa rõ ràng. Khi cần một hàng đại diện theo tiêu chí, hãy dùng hàm aggregate thích hợp, subquery hoặc window function tùy phiên bản, thay vì phụ thuộc giá trị không xác định.

## 8. Kiểm chứng mode ảnh hưởng cú pháp literal

### `ANSI_QUOTES`

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = '';
SELECT "hello" AS result;

SET SESSION sql_mode = 'ANSI_QUOTES';
```

Chạy riêng câu sau để quan sát lỗi identifier nếu không có cột tên `hello`:

```sql
SELECT "hello" AS result;
```

Sau khi ghi nhận kết quả, khôi phục mode:

```sql
SET SESSION sql_mode = @saved_sql_mode;
```

Ở chế độ đầu, dấu ngoặc kép có thể dùng cho string literal. Khi `ANSI_QUOTES` bật, dấu ngoặc kép dùng để quote identifier; nếu không có cột hoặc identifier tên `hello`, câu lệnh thứ hai báo lỗi. Dùng dấu nháy đơn cho string literal và backtick cho identifier MySQL khi cần quote tên đối tượng.

### `NO_BACKSLASH_ESCAPES`

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = '';
SELECT HEX('a\nb') AS default_escaped_value;

SET SESSION sql_mode = 'NO_BACKSLASH_ESCAPES';
SELECT HEX('a\nb') AS literal_backslash_value;
SET SESSION sql_mode = @saved_sql_mode;
```

Trong mode mặc định, `\n` trong literal được diễn giải thành ký tự xuống dòng; khi `NO_BACKSLASH_ESCAPES` bật, backslash và chữ `n` được giữ nguyên. Vì vậy hai kết quả `HEX()` khác nhau. Điều này đặc biệt quan trọng với SQL được tạo bằng cách nối chuỗi. Ứng dụng nên dùng prepared statement thay vì tự escape dữ liệu theo giả định về mode.

Khi thử các mode cú pháp, hãy khôi phục `sql_mode` sau bài thử và chạy lại trên đúng phiên bản driver/server mà ứng dụng dùng.

## 9. Các cấu hình session khác cũng cần được kiểm chứng

Chỉ kiểm tra `sql_mode` là chưa đủ. Các biến dưới đây có thể làm cùng câu SQL hoặc cùng dữ liệu có cách diễn giải khác nhau:

| Cấu hình | Phạm vi thường gặp | Hành vi bị ảnh hưởng |
|---|---|---|
| `time_zone` | Global và session | Hiển thị/ghi `TIMESTAMP`, hàm thời gian và chuyển đổi giờ. |
| `character_set_client` | Session | Charset mà server dùng để diễn giải byte client gửi. |
| `character_set_connection` | Session | Charset trung gian cho literal và biểu thức chuỗi. |
| `collation_connection` | Session | Quy tắc so sánh của biểu thức chuỗi có liên quan tới connection. |
| `transaction_isolation` / `tx_isolation` | Global và session, tên phụ thuộc phiên bản | Snapshot, locking và khả năng quan sát thay đổi đồng thời. |
| `autocommit` | Global và session | Mỗi statement có tự commit hay nằm trong transaction đang mở. |
| `foreign_key_checks` | Global và session | Kiểm tra ràng buộc khóa ngoại trong thao tác ghi. |
| `innodb_strict_mode` | Global và session | Kiểm tra một số cấu hình và thao tác InnoDB. |
| `optimizer_switch` | Global và session | Một số lựa chọn của optimizer và kế hoạch thực thi. |

Kiểm tra cấu hình session trước khi chạy test:

```sql
SELECT
    @@SESSION.time_zone,
    @@SESSION.autocommit,
    @@SESSION.foreign_key_checks,
    @@SESSION.innodb_strict_mode,
    @@SESSION.optimizer_switch,
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.collation_connection;
```

Đối với isolation level, có thể dùng:

```sql
SHOW SESSION VARIABLES LIKE '%isolation%';
```

Sau đó chọn biến đúng với phiên bản và kiểm tra giá trị đang có. Không giả định một tên biến hoặc một giá trị mặc định luôn tồn tại trên mọi bản MySQL.

## 10. Connection pool có thể làm lộ lỗi cấu hình session

Trong ứng dụng Java hoặc server backend, connection pool giữ các kết nối vật lý để tái sử dụng. Mỗi connection có trạng thái session riêng. Nếu request A thay đổi `sql_mode`, `time_zone`, `autocommit` hoặc isolation level rồi trả connection về pool mà không reset, request B có thể nhận một connection với trạng thái khác mặc định.

Ví dụ một request thay đổi session:

```sql
SET SESSION time_zone = '+07:00';
SET SESSION sql_mode = 'ANSI_QUOTES';
```

Request tiếp theo có thể bất ngờ chạy trong session time zone hoặc SQL mode đó nếu pool không khôi phục trạng thái. Một số pool/driver có thể reset một phần trạng thái khi trả connection, nhưng không nên giả định mọi biến tùy chỉnh đều được reset.

Các nguyên tắc khi dùng pool:

1. Thiết lập trạng thái chuẩn khi connection vật lý được tạo, ví dụ session time zone UTC và `sql_mode` đã thống nhất.
2. Hạn chế thay đổi biến session trong code nghiệp vụ. Nếu bắt buộc, lưu và khôi phục giá trị trước khi trả connection.
3. Kiểm tra cấu hình reset của pool và xác minh bằng một bài test mượn-trả-mượn.
4. Không chia sẻ một JDBC `Connection` đồng thời giữa nhiều request hoặc thread.
5. Đặt transaction isolation và autocommit theo cấu hình pool/driver đã kiểm chứng.
6. Ghi fingerprint session trong log chẩn đoán ở mức phù hợp; không ghi thông tin bí mật.

Một test đơn giản là mượn connection A, đổi session variable, trả về pool, rồi mượn lại connection. Kiểm tra `CONNECTION_ID()` để biết có tái sử dụng cùng session vật lý không và đọc lại các biến. Nếu connection ID khác, pool có thể đã tạo connection mới; nếu giống, xác minh trạng thái đã được reset theo chính sách.

## 11. Stored program giữ SQL mode tại thời điểm tạo

MySQL lưu `sql_mode` có hiệu lực khi tạo stored procedure, function, trigger hoặc event. Khi đối tượng chạy, server dùng mode được lưu cùng đối tượng, thay vì đơn giản lấy toàn bộ `@@SESSION.sql_mode` hiện tại của client gọi nó.

Điều này có nghĩa là chỉ thay đổi `SET GLOBAL sql_mode` hoặc session của ứng dụng không đảm bảo thay đổi hành vi của stored program đã tồn tại. Khi nâng cấp hoặc chuẩn hóa SQL mode, cần kiểm tra các đối tượng được tạo dưới mode cũ.

Có thể xem định nghĩa procedure:

```sql
SHOW CREATE PROCEDURE learning_shop.create_order;
```

Kết quả có phần `sql_mode` gắn với routine. Với trigger, dùng:

```sql
SHOW CREATE TRIGGER learning_shop.orders_after_insert;
```

Nếu cần đối tượng dùng mode mới, quy trình thường là script hóa định nghĩa, tạo lại đối tượng dưới session có `sql_mode` mong muốn và kiểm thử trước khi triển khai. Hãy lưu DDL trong migration/version control để có thể tái tạo chính xác.

## 12. Xây dựng bộ kiểm thử hành vi có thể lặp lại

Một bộ test tốt cần kiểm tra cả kết quả lẫn cách server phản hồi. Với mỗi ca thử, ghi:

- Phiên bản MySQL và distribution.
- Global/session variables liên quan.
- Schema, engine, DDL và dữ liệu đầu vào.
- Câu SQL và thứ tự thực thi.
- Kết quả trả về, số hàng bị ảnh hưởng và trạng thái transaction.
- SQLSTATE, error code và warning nếu có.
- Giá trị sau cùng trong database, không chỉ response của driver.

### Ma trận kiểm thử đề xuất

| Nhóm | Biến thể cần so sánh | Điều cần xác nhận |
|---|---|---|
| Phiên bản | Bản đang chạy và bản mục tiêu nâng cấp | Cú pháp, default mode, warning/error và kết quả truy vấn. |
| Strictness | Strict và non-strict | Dữ liệu sai bị từ chối hay bị chuyển đổi/cắt kèm warning. |
| Grouping | Có và không `ONLY_FULL_GROUP_BY` | Truy vấn aggregate có xác định và tương thích không. |
| Literal | Có/không `ANSI_QUOTES`, `NO_BACKSLASH_ESCAPES` | Câu SQL literal và SQL động có đổi ý nghĩa không. |
| Time zone | UTC và vùng nghiệp vụ | `TIMESTAMP`, hàm thời gian và ranh giới ngày có đúng không. |
| Charset/collation | Cấu hình cũ và mới | So sánh, unique index, join và sắp xếp có đổi không. |
| Transaction | Các isolation level và autocommit dự kiến | Commit, rollback, snapshot và locking có đúng yêu cầu không. |
| Connection pool | Connection mới và connection tái sử dụng | Session state có được khởi tạo/reset đúng không. |
| Stored program | Routine tạo dưới mode cũ và mới | Mode lưu cùng đối tượng có làm thay đổi hành vi không. |

### Mẫu kịch bản test

```text
Test ID: SQLMODE-STRICT-001
Server: MySQL <version>
Session sql_mode: STRICT_TRANS_TABLES
Schema: isolated_test_schema
Table: mode_probe (InnoDB, label VARCHAR(4))
Input: 'ABCDE'
Expected: statement rejected; row count unchanged
Capture: SQLSTATE, error code, SHOW WARNINGS, SELECT after attempt
```

Mẫu này giúp biến một nhận xét mơ hồ như “strict mode gây lỗi” thành một ca kiểm thử có thể tự động hóa và so sánh giữa các phiên bản.

## 13. Quy trình kiểm chứng khi nâng cấp MySQL hoặc đổi cấu hình

### Trước thay đổi

1. Ghi fingerprint server và session ở môi trường hiện tại.
2. Lưu cấu hình global, file option và cấu hình driver/pool.
3. Lưu DDL, migration, stored routine, trigger và event liên quan.
4. Thu thập các truy vấn quan trọng, dữ liệu đại diện và kết quả hiện tại.
5. Xác định biến nào sẽ thay đổi và phạm vi global/session của từng biến.

### Trong môi trường thử nghiệm

1. Dựng server phiên bản đích với cấu hình dự kiến.
2. Khôi phục schema và dữ liệu đã ẩn danh hoặc bộ fixture tương đương.
3. Chạy bộ regression test với đúng driver và connection pool.
4. So sánh kết quả, warning, SQLSTATE, row count, transaction outcome và kế hoạch thực thi.
5. Kiểm tra stored program được tạo lại dưới mode dự kiến.
6. Thử rollback migration hoặc phục hồi snapshot nếu kết quả không đạt.

### Khi triển khai

1. Đưa cấu hình vào nguồn quản lý chính thức và ghi lại giá trị trước/sau.
2. Áp dụng theo thứ tự phù hợp: cấu hình server, restart nếu cần, tạo connection mới, cập nhật stored program và triển khai ứng dụng.
3. Xác minh fingerprint trên các connection mới và connection được pool tái sử dụng.
4. Theo dõi lỗi SQL, warning, tỷ lệ rollback, deadlock, latency và lỗi dữ liệu.
5. Có phương án quay lui cấu hình hoặc phục hồi dữ liệu nếu thay đổi làm sai ngữ nghĩa.

Không thay đổi nhiều biến cùng lúc nếu chưa có bằng chứng chúng cần thay đổi đồng thời. Khi có lỗi, cô lập biến và tái hiện trên schema thử nghiệm để tìm nguyên nhân.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Chỉ ghi nhận phiên bản server | Bỏ sót SQL mode hoặc session state khác nhau | Thu thập fingerprint server và từng connection. |
| Nghĩ `SET GLOBAL` đổi session đang mở | Ứng dụng đang chạy tiếp tục dùng cấu hình cũ | Mở connection mới hoặc chủ động đặt session. |
| Gán `sql_mode` mới mà không giữ mode cũ | Vô tình bỏ strictness hoặc mode cần thiết khác | So sánh danh sách và chỉ thêm/bỏ mode có chủ đích. |
| Dựa vào default của phiên bản | Hành vi thay đổi sau upgrade | Khai báo cấu hình cần thiết tường minh và test trên phiên bản đích. |
| Bỏ qua warning | Dữ liệu có thể đã bị cắt hoặc chuyển đổi | Đọc `SHOW WARNINGS` ngay sau statement và kiểm tra dữ liệu sau ghi. |
| Nghĩ đổi session của client sẽ đổi stored procedure cũ | Routine vẫn chạy theo `sql_mode` lúc tạo | Kiểm tra `SHOW CREATE` và tái tạo routine qua migration nếu cần. |
| Cho rằng pool luôn reset mọi session variable | Trạng thái request trước rò rỉ sang request sau | Kiểm tra cấu hình pool và test mượn/trả connection. |
| Test chỉ trên dữ liệu hợp lệ | Bỏ sót khác biệt strict mode, grouping hoặc charset | Thêm dữ liệu biên, sai định dạng và trường hợp trùng. |
| Chỉ kiểm tra response của ứng dụng | Không biết database đã ghi một phần hay chưa | Kiểm tra row count, warning, transaction và trạng thái dữ liệu cuối. |

## 15. Bài tập thực hành

### Bài tập A — Lập fingerprint hai môi trường

1. Chạy truy vấn fingerprint trên hai MySQL server hoặc hai session có cấu hình khác nhau.
2. So sánh version, `sql_mode`, time zone, charset/collation, autocommit và isolation.
3. Ghi biến nào khác nhau và biến đó ảnh hưởng câu SQL nào.
4. Đề xuất một cấu hình chuẩn cho ứng dụng.

### Bài tập B — Kiểm chứng strict mode và grouping

1. Tạo `mode_probe` và `sales_mode_probe` trong schema riêng.
2. Thử insert giá trị vượt độ dài trong strict và non-strict mode.
3. Ghi lại error, warning và dữ liệu cuối cùng.
4. Chạy truy vấn aggregate với `ONLY_FULL_GROUP_BY` bật/tắt.
5. Viết lại truy vấn để có ngữ nghĩa xác định và chạy được trong mode nghiêm ngặt.

### Bài tập C — Kiểm tra session state qua pool

1. Mượn một connection và ghi `CONNECTION_ID()` cùng `@@SESSION.sql_mode`.
2. Thay đổi `sql_mode` và `time_zone`, sau đó trả connection về pool.
3. Mượn connection tiếp theo và kiểm tra ID, mode, time zone.
4. Xác định pool có reset trạng thái hay không.
5. Cấu hình initialization/reset phù hợp và chạy lại.

### Bài tập D — Kiểm tra stored routine sau thay đổi mode

1. Tạo procedure trong session có một `sql_mode` xác định.
2. Đổi session mode của client rồi gọi procedure.
3. Dùng `SHOW CREATE PROCEDURE` để xem mode được lưu.
4. Tạo lại procedure dưới mode mới và so sánh kết quả.
5. Đưa định nghĩa procedure vào migration để có thể tái tạo.

### Bài tập E — Diễn tập nâng cấp phiên bản

1. Chọn một phiên bản MySQL hiện tại và một phiên bản đích trong môi trường test.
2. Ghi fingerprint, DDL, routine và fixture trên phiên bản hiện tại.
3. Chạy cùng bộ test trên phiên bản đích.
4. So sánh SQLSTATE, warning, dữ liệu sau ghi và kết quả truy vấn.
5. Phân loại khác biệt do phiên bản, SQL mode, session variable hoặc driver.
6. Viết checklist rollout và phương án quay lui.

Bạn hoàn thành bài khi có thể tái hiện một khác biệt hành vi bằng ca test rõ ràng, xác định được phạm vi global/session, giải thích ảnh hưởng của mode, kiểm tra session qua pool và xây dựng bộ regression test cho nâng cấp MySQL.

## 16. Nguyên tắc cần ghi nhớ

- Luôn ghi nhận phiên bản MySQL cùng fingerprint cấu hình server và session.
- Phân biệt `GLOBAL` với `SESSION`; thay đổi global không tự cập nhật connection đang mở.
- `SET SESSION sql_mode` thay thế danh sách mode hiện tại; chỉ thêm/bỏ mode có kiểm soát.
- Strict mode, `ONLY_FULL_GROUP_BY`, `ANSI_QUOTES` và các mode cú pháp có thể làm câu SQL cũ thay đổi kết quả hoặc phát sinh lỗi.
- Kiểm tra cả warning, SQLSTATE, error code, row count và dữ liệu sau cùng.
- `time_zone`, charset/collation, isolation và autocommit cũng là một phần của trạng thái session cần kiểm thử.
- Connection pool phải khởi tạo và reset session state có chủ đích.
- Stored program có thể giữ `sql_mode` tại thời điểm tạo; kiểm tra và tái tạo qua migration khi cần.
- Kiểm thử trên đúng phiên bản, driver và dữ liệu đại diện trước khi rollout cấu hình mới.

Khi có bộ kiểm chứng tái lập, việc thay đổi phiên bản hoặc cấu hình MySQL trở nên có thể đánh giá bằng bằng chứng. Bạn sẽ biết câu SQL nào đổi hành vi, session nào đang dùng giá trị nào và cần điều chỉnh schema, truy vấn, routine hay quy trình triển khai ở đâu.
