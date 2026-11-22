# DETERMINISTIC, đặc tính truy cập dữ liệu và binary logging

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt `DETERMINISTIC` và `NOT DETERMINISTIC` trong stored function.
- Giải thích bốn đặc tính truy cập dữ liệu: `NO SQL`, `CONTAINS SQL`, `READS SQL DATA` và `MODIFIES SQL DATA`.
- Hiểu vì sao các đặc tính routine là cam kết do người viết khai báo, không phải kết quả MySQL tự phân tích và xác minh toàn bộ thân routine.
- Chọn khai báo đúng với hành vi thực tế của function.
- Giải thích rủi ro của statement-based replication khi function có kết quả hoặc tác dụng phụ không nhất quán.
- Phân biệt `STATEMENT`, `ROW` và `MIXED` binary log format.
- Kiểm tra `log_bin`, `binlog_format` và `log_bin_trust_function_creators`.
- Hiểu điều kiện tạo stored function khi binary logging bật và trust creators bị tắt.
- Đánh giá các trường hợp cần kiểm thử trên source/replica trước khi phát hành.

Các ví dụ hướng tới MySQL 8.0/8.4. Binary logging, quyền quản trị và một số hành vi replication có thể khác theo phiên bản hoặc cấu hình; luôn kiểm tra đúng server đang vận hành.

## 1. Vì sao stored function cần khai báo đặc tính?

Stored function là routine trả về một giá trị và có thể được gọi trong biểu thức SQL, chẳng hạn trong `SELECT`, `WHERE`, `ORDER BY` hoặc biểu thức của lệnh ghi dữ liệu.

Ví dụ:

```sql
CREATE FUNCTION fn_line_total(
    p_quantity INT,
    p_unit_price DECIMAL(12,2)
)
RETURNS DECIMAL(14,2)
DETERMINISTIC
NO SQL
RETURN p_quantity * p_unit_price;
```

Function trên chỉ tính kết quả từ hai tham số. Cùng một cặp tham số sẽ cho cùng kết quả, không đọc hoặc ghi bảng. Vì vậy, khai báo `DETERMINISTIC` và `NO SQL` mô tả đúng hành vi.

MySQL cho phép khai báo đặc tính của routine để mô tả tính xác định và mức độ truy cập dữ liệu. Những khai báo này có ý nghĩa đối với việc quản trị routine và các quy tắc binary logging, nhưng không thay thế việc hiểu và kiểm tra nội dung function.

Hai nhóm đặc tính độc lập với nhau:

- **Tính xác định:** cùng đầu vào có luôn cho cùng kết quả hay không?
- **Truy cập dữ liệu:** routine có chứa SQL, đọc dữ liệu hay có thể sửa dữ liệu không?

Một function có thể `DETERMINISTIC` nhưng `READS SQL DATA` nếu dữ liệu nó đọc thực sự không đổi theo hợp đồng của hệ thống. Ngược lại, một function có thể `NOT DETERMINISTIC` và `NO SQL` nếu kết quả phụ thuộc thời gian hiện tại nhưng không truy cập bảng.

## 2. DETERMINISTIC và NOT DETERMINISTIC

### 2.1. DETERMINISTIC

`DETERMINISTIC` có nghĩa function luôn trả cùng kết quả khi được gọi với cùng giá trị tham số đầu vào.

Ví dụ:

```sql
DELIMITER $$

CREATE FUNCTION fn_normalize_code(p_code VARCHAR(40))
RETURNS VARCHAR(40)
DETERMINISTIC
NO SQL
BEGIN
    RETURN UPPER(TRIM(p_code));
END$$

DELIMITER ;
```

Với cùng chuỗi đầu vào, function chuẩn hóa theo cùng một phép biến đổi. Nó không phụ thuộc bảng, thời gian hiện tại, số ngẫu nhiên hoặc trạng thái session.

Các phép tính số học thuần túy, chuẩn hóa chuỗi theo quy tắc cố định hoặc chuyển đổi giá trị không phụ thuộc trạng thái bên ngoài thường phù hợp với `DETERMINISTIC`.

### 2.2. NOT DETERMINISTIC

`NOT DETERMINISTIC` mô tả function có thể trả kết quả khác nhau dù các tham số đầu vào giống nhau.

Ví dụ:

```sql
CREATE FUNCTION fn_days_since(p_created_at DATE)
RETURNS INT
NOT DETERMINISTIC
NO SQL
RETURN DATEDIFF(CURRENT_DATE, p_created_at);
```

Kết quả thay đổi theo ngày hiện tại. Gọi function với cùng `p_created_at` ở hai ngày khác nhau có thể cho kết quả khác nhau, nên khai báo `NOT DETERMINISTIC`.

### 2.3. Nguồn phụ thuộc khiến function không xác định

Các nguồn phụ thuộc thường gặp:

- `CURRENT_DATE`, `CURRENT_TIME`, `NOW()` hoặc thời gian hiện tại.
- `SYSDATE()` trong cấu hình thông thường.
- Số ngẫu nhiên hoặc giá trị định danh được tạo mới như `UUID()`.
- Dữ liệu trong bảng có thể thay đổi giữa các lần gọi.
- Biến session, user variable, timezone hoặc trạng thái kết nối.
- Trạng thái bên ngoài không được biểu diễn đầy đủ qua tham số đầu vào.

Không chỉ nhìn vào câu `RETURN`. Hãy xem toàn bộ routine, function được gọi lồng bên trong và mọi trạng thái mà kết quả phụ thuộc.

### 2.4. Đọc bảng vẫn có thể không deterministic

Ví dụ function tra cứu mức thuế hiện hành:

```sql
CREATE TABLE tax_rates (
    region_code CHAR(2) NOT NULL,
    valid_from DATE NOT NULL,
    rate DECIMAL(6,4) NOT NULL,
    PRIMARY KEY (region_code, valid_from)
) ENGINE = InnoDB;
```

```sql
DELIMITER $$

CREATE FUNCTION fn_current_tax_rate(p_region_code CHAR(2))
RETURNS DECIMAL(6,4)
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_rate DECIMAL(6,4) DEFAULT NULL;

    SELECT rate
      INTO v_rate
      FROM tax_rates
     WHERE region_code = p_region_code
       AND valid_from <= CURRENT_DATE
     ORDER BY valid_from DESC
     LIMIT 1;

    RETURN v_rate;
END$$

DELIMITER ;
```

Function đọc dữ liệu (`READS SQL DATA`). Mức thuế có thể thay đổi khi bảng được cập nhật và điều kiện `CURRENT_DATE` cũng thay đổi theo ngày. Do đó, khai báo `NOT DETERMINISTIC` phản ánh đúng ngữ nghĩa.

Nếu một function đọc bảng cấu hình được cam kết bất biến, có thể có trường hợp kết quả ổn định theo tham số trong suốt vòng đời hệ thống. Tuy nhiên, phải chứng minh được hợp đồng bất biến đó và xét cả các phụ thuộc khác. Không khai báo `DETERMINISTIC` chỉ vì dữ liệu thường ít thay đổi.

### 2.5. Mặc định khi bỏ qua khai báo

Nếu không khai báo tính xác định, MySQL mặc định routine là `NOT DETERMINISTIC`. Không khai báo đặc tính truy cập dữ liệu thì mặc định là `CONTAINS SQL`.

Khi binary logging bật và `log_bin_trust_function_creators` tắt, các mặc định này có thể khiến câu lệnh tạo function không đáp ứng yêu cầu khai báo. Vì vậy, hãy ghi rõ đặc tính đúng thay vì dựa vào mặc định.

## 3. Bốn đặc tính truy cập dữ liệu SQL

Đặc tính truy cập dữ liệu mô tả loại câu lệnh SQL mà routine chứa. Chúng không phải quyền SQL được cấp cho tài khoản và cũng không quyết định `SQL SECURITY`.

| Đặc tính | Ý nghĩa | Ví dụ hành vi |
|---|---|---|
| `NO SQL` | Routine không chứa câu lệnh SQL | Tính toán từ tham số |
| `CONTAINS SQL` | Có câu lệnh SQL nhưng không đọc hoặc sửa dữ liệu SQL | Gán biến cục bộ, xử lý biểu thức |
| `READS SQL DATA` | Có thể đọc dữ liệu nhưng không sửa dữ liệu | `SELECT` từ bảng |
| `MODIFIES SQL DATA` | Có thể sửa dữ liệu | `INSERT`, `UPDATE`, `DELETE` |

### 3.1. NO SQL

`NO SQL` dùng cho routine không chứa câu lệnh SQL. Ví dụ function chỉ tính từ tham số:

```sql
CREATE FUNCTION fn_discounted_price(
    p_price DECIMAL(12,2),
    p_percent DECIMAL(5,2)
)
RETURNS DECIMAL(12,2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_price * (1 - p_percent / 100), 2);
```

Function không truy vấn bảng và không ghi dữ liệu. Không khai báo `READS SQL DATA` chỉ vì function được gọi bên trong một câu SQL; đặc tính này nói về nội dung truy cập dữ liệu của routine.

### 3.2. CONTAINS SQL

`CONTAINS SQL` mô tả routine có câu lệnh SQL nhưng không chứa thao tác đọc hoặc sửa dữ liệu. Ví dụ routine có xử lý biến cục bộ:

```sql
DELIMITER $$

CREATE FUNCTION fn_format_code(p_code VARCHAR(40))
RETURNS VARCHAR(40)
DETERMINISTIC
CONTAINS SQL
BEGIN
    DECLARE v_code VARCHAR(40);
    SET v_code = UPPER(TRIM(p_code));
    RETURN v_code;
END$$

DELIMITER ;
```

`CONTAINS SQL` không có nghĩa routine được phép đọc hoặc ghi bảng. Nếu có `SELECT` đọc dữ liệu, hãy khai báo `READS SQL DATA`; nếu có thao tác sửa dữ liệu, khai báo `MODIFIES SQL DATA`.

### 3.3. READS SQL DATA

`READS SQL DATA` dùng khi routine có câu lệnh đọc dữ liệu, chẳng hạn `SELECT ... INTO`:

```sql
DELIMITER $$

CREATE FUNCTION fn_product_price(p_product_id BIGINT)
RETURNS DECIMAL(12,2)
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_price DECIMAL(12,2) DEFAULT NULL;

    SELECT price
      INTO v_price
      FROM products
     WHERE product_id = p_product_id;

    RETURN v_price;
END$$

DELIMITER ;
```

Function đọc bảng `products`. Nếu giá có thể thay đổi, cùng một `product_id` có thể trả kết quả khác nhau ở những thời điểm khác nhau. Vì thế, `NOT DETERMINISTIC` là lựa chọn phù hợp với bảng giá có thể cập nhật.

### 3.4. MODIFIES SQL DATA

`MODIFIES SQL DATA` dùng khi routine có thể thực hiện thao tác thay đổi dữ liệu, chẳng hạn `INSERT`, `UPDATE` hoặc `DELETE`.

Ví dụ minh họa một function ghi nhận sự kiện vào bảng audit:

```sql
CREATE TABLE function_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_code VARCHAR(40) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (audit_id)
) ENGINE = InnoDB;
```

```sql
DELIMITER $$

CREATE FUNCTION fn_record_event(p_event_code VARCHAR(40))
RETURNS BIGINT UNSIGNED
NOT DETERMINISTIC
MODIFIES SQL DATA
BEGIN
    INSERT INTO function_audit (event_code)
    VALUES (p_event_code);

    RETURN LAST_INSERT_ID();
END$$

DELIMITER ;
```

Đây là ví dụ về khai báo truy cập dữ liệu, không phải khuyến nghị đưa side effect vào function được gọi tùy ý từ câu SELECT. Stored function có các giới hạn riêng: chẳng hạn không được sửa một bảng mà câu lệnh gọi function đang sử dụng, không được tự điều khiển transaction bằng `COMMIT`/`ROLLBACK`, và không được trả result set theo cách stored procedure có thể làm. Hãy cân nhắc stored procedure hoặc thao tác DML tường minh nếu mục tiêu chính là ghi dữ liệu.

Lưu ý về binary logging: khi `log_bin_trust_function_creators = 0`, chỉ khai báo `MODIFIES SQL DATA` không đáp ứng điều kiện tạo function. Ví dụ này có thể bị từ chối khi binary logging bật nếu không có cấu hình/quyền phù hợp. Không đổi khai báo thành `NO SQL` hoặc `DETERMINISTIC` để né kiểm tra; phải phản ánh đúng hành vi và theo quy trình DBA.

### 3.5. Các đặc tính là mô tả, không phải cơ chế chặn

Các đặc tính này chỉ mang tính advisory: MySQL không dùng chúng để giới hạn loại câu lệnh mà routine được phép thực thi và không xác minh toàn bộ body có tuân thủ khai báo hay không. Ví dụ, routine khai báo `NO SQL` nhưng thân routine lại đọc bảng là khai báo sai; server không nên được xem như đã kiểm chứng điều đó chỉ vì `CREATE FUNCTION` thành công.

Tương tự, `READS SQL DATA` không phải cơ chế cấp quyền chỉ đọc. Quyền thực tế còn phụ thuộc `DEFINER`/`INVOKER`, privilege của tài khoản và câu lệnh bên trong.

## 4. Tính xác định và truy cập dữ liệu là hai trục độc lập

Không suy ra `DETERMINISTIC` chỉ từ `NO SQL`, hoặc suy ra `NOT DETERMINISTIC` chỉ từ `READS SQL DATA`. Cần xem cả logic và dữ liệu mà function sử dụng.

| Ví dụ | Tính xác định phù hợp | Truy cập dữ liệu phù hợp | Lý do |
|---|---|---|---|
| Nhân hai tham số | `DETERMINISTIC` | `NO SQL` | Chỉ phụ thuộc đầu vào |
| Chuẩn hóa chuỗi bằng quy tắc cố định | `DETERMINISTIC` | `NO SQL` hoặc `CONTAINS SQL` tùy thân routine | Không đọc trạng thái bên ngoài |
| Tính số ngày từ ngày hiện tại | `NOT DETERMINISTIC` | `NO SQL` | Phụ thuộc thời gian |
| Đọc giá hiện hành từ bảng | Thường `NOT DETERMINISTIC` | `READS SQL DATA` | Bảng có thể thay đổi |
| Ghi audit row | Thường `NOT DETERMINISTIC` | `MODIFIES SQL DATA` | Có tác dụng phụ ghi dữ liệu |
| Đọc bảng được bảo đảm bất biến | Có thể `DETERMINISTIC` nếu mọi phụ thuộc đều ổn định | `READS SQL DATA` | Cần hợp đồng bất biến rõ ràng |

Ví dụ, function đọc một bảng cấu hình nhưng cũng gọi `CURRENT_DATE` không thể được xem là deterministic chỉ vì bảng cấu hình hiếm khi thay đổi. Một function thuần số học nhưng dùng `RAND()` cũng không phải deterministic.

## 5. Binary logging và replication

Binary log ghi lại các sự kiện thay đổi dữ liệu và thay đổi schema để phục vụ replication, point-in-time recovery và các mục đích vận hành khác.

Khi function được gọi trong câu SQL làm thay đổi dữ liệu, cách ghi binary log ảnh hưởng tới việc replica áp dụng thay đổi như thế nào.

### 5.1. Statement-based logging

Với `binlog_format = STATEMENT`, binary log ghi câu lệnh SQL. Replica thực thi lại câu lệnh đó.

Nếu function phụ thuộc thời gian, số ngẫu nhiên, trạng thái session hoặc dữ liệu khác nhau giữa source và replica, kết quả thực thi lại có thể không giống nhau. Điều này có thể làm dữ liệu replica lệch khỏi source.

Ví dụ khái niệm:

```sql
UPDATE orders
SET reference_code = fn_generate_reference(order_id)
WHERE status = 'PENDING';
```

Nếu function tạo giá trị khác nhau ở mỗi lần gọi và statement được chạy lại trên replica, kết quả có thể khác source trừ khi MySQL có cơ chế ghi nhận đặc biệt cho hàm cụ thể hoặc statement được xử lý theo cách an toàn.

### 5.2. Row-based logging

Với `binlog_format = ROW`, binary log ghi thay đổi ở mức hàng. Replica áp dụng row event đã được ghi, thay vì thực thi lại toàn bộ câu DML ban đầu để tự tính các giá trị hàng.

Điều này thường giảm rủi ro sai khác do function không deterministic trong các thao tác DML được ghi theo row. Tuy nhiên, row-based logging không biến khai báo routine sai thành đúng và không loại bỏ mọi vấn đề liên quan DDL, routine definition, side effect hoặc các statement được ghi theo statement.

### 5.3. Mixed logging

Với `binlog_format = MIXED`, MySQL chọn statement-based hoặc row-based cho từng statement theo quy tắc của server. Một số statement được xác định là không an toàn cho statement-based logging có thể được chuyển sang row-based logging.

Mixed mode hữu ích nhưng không nên được hiểu là hệ thống tự phát hiện được mọi function khai báo sai. Đặc tính routine vẫn cần trung thực và phải kiểm thử trên topology thực tế.

### 5.4. So sánh ba định dạng

| Định dạng | Nội dung chính trong binary log | Ảnh hưởng khi function không deterministic |
|---|---|---|
| `STATEMENT` | Câu lệnh SQL | Replica thực thi lại; cần đặc biệt chú ý tính an toàn và trạng thái phụ thuộc |
| `ROW` | Thay đổi hàng | Replica áp dụng row event; thường tránh tính lại biểu thức function cho DML đó |
| `MIXED` | Kết hợp statement và row | Server tự chuyển một số statement không an toàn sang row |

Không chọn format chỉ dựa trên một function. Cần xét dung lượng binary log, khả năng audit, workload, replication topology, phiên bản và yêu cầu phục hồi.

## 6. Các hàm built-in và tính không xác định

Một số built-in có hành vi đặc biệt khi binary logging. Không nên gom mọi hàm thay đổi theo thời gian hoặc ngẫu nhiên vào cùng một nhóm “replication luôn sai”.

| Hàm/nhóm hàm | Đặc điểm | Lưu ý replication |
|---|---|---|
| `CURRENT_DATE` | Phụ thuộc ngày hiện tại | Không deterministic theo cùng input qua các ngày; đánh giá riêng cách statement được ghi và timezone của source/replica |
| `NOW()`, `CURRENT_TIMESTAMP` và synonym | Phụ thuộc thời gian hiện tại | Binary log ghi timestamp để source/replica dùng cùng mốc cho statement; function vẫn không deterministic theo cùng input qua các thời điểm |
| `RAND()` | Tạo số ngẫu nhiên | MySQL ghi seed để hỗ trợ statement-based replication; trong stored routine, `RAND()` được tái lập đúng khi chỉ được gọi một lần trong mỗi lần thực thi routine |
| `UUID()`, `UUID_SHORT()`, `USER()`, `CURRENT_USER()`, `VERSION()`, `LOAD_FILE()` | Phụ thuộc server, kết nối hoặc trạng thái bên ngoài | Một số hàm được ghi nguyên giá trị/không tái tạo giống nhau trên replica; statement-based replication có thể không an toàn, Mixed tự chuyển một số trường hợp sang row |
| `SYSDATE()` | Trả thời điểm thực thi hàm | Không bị chi phối bởi timestamp statement trong binary log nên có thể không an toàn với statement-based replication; `--sysdate-is-now` làm nó hoạt động như `NOW()` và cần cấu hình nhất quán trên source/replica |

Điểm quan trọng: một hàm có thể được MySQL xử lý đặc biệt trong binary log nhưng vẫn không đáp ứng định nghĩa `DETERMINISTIC` theo nghĩa cùng đầu vào luôn cho cùng kết quả. Không dùng các quy tắc an toàn đặc biệt của built-in để khai báo sai đặc tính cho custom function.

## 7. Điều kiện tạo stored function khi binary logging bật

MySQL có cơ chế bảo vệ khi binary logging bật để hạn chế function có thể gây khác biệt giữa source và replica.

### 7.1. log_bin_trust_function_creators

Biến hệ thống `log_bin_trust_function_creators` quyết định server có tin người tạo stored function/trigger tự chịu trách nhiệm về an toàn binary logging hay không.

Kiểm tra trạng thái:

```sql
SELECT
    @@GLOBAL.log_bin AS log_bin,
    @@GLOBAL.binlog_format AS binlog_format,
    @@GLOBAL.log_bin_trust_function_creators
        AS log_bin_trust_function_creators;
```

`log_bin` cho biết binary logging có bật hay không. `binlog_format` cho biết định dạng hiện tại. `log_bin_trust_function_creators` là biến global, mặc định là `OFF`; biến này được đánh dấu deprecated trong MySQL 8.4, vì vậy cần xem tài liệu phiên bản mục tiêu và chính sách nâng cấp trước khi thiết kế phụ thuộc lâu dài vào nó.

### 7.2. Khi trust creators tắt

Khi binary logging bật và `log_bin_trust_function_creators = 0`, MySQL áp dụng kiểm tra bổ sung khi tạo stored function:

- Người tạo function cần quyền `CREATE ROUTINE` (khi tạo) hoặc `ALTER ROUTINE` (khi thay đổi characteristic), đồng thời cần quyền `SUPER` theo kiểm tra binary logging của MySQL trong chế độ này.
- Function phải khai báo ít nhất một trong các đặc tính: `DETERMINISTIC`, `NO SQL` hoặc `READS SQL DATA`.

Ví dụ function không khai báo đặc tính phù hợp có thể gặp lỗi 1418:

```text
ERROR 1418 (HY000): This function has none of DETERMINISTIC,
NO SQL, or READS SQL DATA in its declaration and binary logging
is enabled (you *might* want to use the less safe
log_bin_trust_function_creators variable)
```

Nếu người tạo không có quyền quản trị cần thiết, có thể gặp lỗi 1419 liên quan tới `SUPER` và binary logging.

Điều kiện trên là kiểm tra khai báo và quyền. Server không chứng minh function thực sự deterministic hoặc chỉ đọc dữ liệu.

### 7.3. Đặc tính nào đáp ứng kiểm tra khai báo?

Trong chế độ trust tắt, một trong các khai báo sau đáp ứng phần đặc tính:

```sql
DETERMINISTIC
```

hoặc:

```sql
NO SQL
```

hoặc:

```sql
READS SQL DATA
```

Chỉ khai báo `CONTAINS SQL` hoặc `MODIFIES SQL DATA` không đáp ứng danh sách này. Điều đó không có nghĩa phải khai báo sai routine là `NO SQL` để tạo được function. Hãy mô tả đúng hành vi và xử lý quyền/cấu hình theo chính sách của DBA.

### 7.4. Khi trust creators bật

Nếu `log_bin_trust_function_creators = 1`, server nới lỏng các kiểm tra đặc biệt về quyền và đặc tính khi tạo stored function/trigger trong điều kiện binary logging.

Điều này không:

- Tự biến function thành deterministic.
- Xác minh function có an toàn cho statement-based replication hay không.
- Tắt binary logging.
- Thay đổi `binlog_format`.
- Thay thế review routine hoặc kiểm thử replication.

Đây là quyết định cấu hình ở cấp server. Chỉ DBA hoặc người có quyền quản trị phù hợp mới nên thay đổi sau khi đánh giá chính sách bảo mật và replication.

### 7.5. Thay đổi biến cần kiểm soát

Ví dụ cú pháp thay đổi global variable:

```sql
SET GLOBAL log_bin_trust_function_creators = 1;
```

Lệnh yêu cầu quyền quản trị biến hệ thống phù hợp; trên MySQL hiện đại, `SYSTEM_VARIABLES_ADMIN` được dùng cho nhiều thao tác quản trị system variable. Quy tắc tạo/thay đổi stored function trong kiểm tra binary logging vẫn có thông báo và điều kiện `SUPER` riêng, vì vậy không đồng nhất hai loại quyền này.

Không chạy lệnh này chỉ để làm biến mất lỗi tạo function. Nếu chính sách yêu cầu trust creators tắt, hãy khai báo đúng routine và xin đúng quyền theo quy trình. Nếu DBA quyết định bật, cần ghi nhận thay đổi cấu hình, phạm vi ảnh hưởng và cách duy trì qua restart.

### 7.6. Điều kiện lúc tạo function khác điều kiện lúc gọi function

Đây là hai bước kiểm tra riêng, dễ bị nhầm:

| Thời điểm | Với binary logging bật và trust creators tắt |
|---|---|
| `CREATE FUNCTION`/`ALTER FUNCTION` | Cần quyền quản trị mà server yêu cầu và phải khai báo ít nhất một trong `DETERMINISTIC`, `NO SQL`, `READS SQL DATA` |
| Gọi function khi `binlog_format = STATEMENT` | Function phải có khai báo `DETERMINISTIC`; nếu không, statement có thể bị từ chối khi thực thi |
| Gọi function khi `binlog_format = ROW` hoặc `MIXED` | Server chấp nhận và replicate statement theo row-based format trong trường hợp được mô tả trong tài liệu; vẫn phải bảo đảm routine và tác dụng phụ an toàn |

Ví dụ, function khai báo `NOT DETERMINISTIC READS SQL DATA` có thể đáp ứng phần điều kiện characteristic khi tạo function, nhưng điều đó không có nghĩa nó được phép gọi trong mọi statement-based logging context. Nếu `binlog_format = STATEMENT`, yêu cầu `DETERMINISTIC` khi thực thi vẫn có thể làm lời gọi bị từ chối.

Ngược lại, khai báo `DETERMINISTIC` không bảo đảm body thực sự deterministic. Nếu server phát hiện hoặc cảnh báo một statement không an toàn, cần xử lý nguyên nhân; không dựa vào keyword để bỏ qua cảnh báo. Khi `log_bin_trust_function_creators = 1`, các kiểm tra này được nới lỏng, nhưng rủi ro dữ liệu vẫn thuộc trách nhiệm người thiết kế và vận hành.

## 8. Phạm vi của quy tắc: function, trigger và procedure

Không áp dụng máy móc quy tắc tạo function cho mọi stored program.

- Stored function có các đặc tính `DETERMINISTIC` và SQL data access; chúng có thể được gọi trong biểu thức SQL.
- Trigger được thực thi khi có sự kiện trên bảng. Trigger không khai báo `DETERMINISTIC` hoặc bốn đặc tính truy cập dữ liệu theo cú pháp routine như function; MySQL xem trigger là deterministic theo giả định mặc định, dù body vẫn có thể chứa hành vi không deterministic.
- Stored procedure có thể khai báo routine characteristics, nhưng quy tắc binary logging đặc biệt về creator và function declaration tập trung vào stored function và trigger.

Stored procedure thường phù hợp hơn cho quy trình nghiệp vụ có nhiều bước DML, transaction control hoặc trả result set. Function phù hợp cho phép tính trả một giá trị và nên hạn chế side effect để dễ hiểu, kiểm thử và replication.

## 9. Kiểm tra đặc tính đã khai báo của routine

### 9.1. SHOW CREATE FUNCTION

```sql
SHOW CREATE FUNCTION app_db.fn_line_total;
```

Output cho biết định nghĩa function, definer, SQL mode và các characteristic đã khai báo. Đây là cách trực tiếp để đối chiếu với source control.

### 9.2. INFORMATION_SCHEMA.ROUTINES

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SECURITY_TYPE,
    DEFINER,
    SQL_MODE
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'app_db'
  AND ROUTINE_TYPE = 'FUNCTION'
ORDER BY ROUTINE_NAME;
```

Các cột cần chú ý:

| Cột | Nội dung |
|---|---|
| `IS_DETERMINISTIC` | `YES` hoặc `NO` theo khai báo đã lưu |
| `SQL_DATA_ACCESS` | `NO SQL`, `CONTAINS SQL`, `READS SQL DATA` hoặc `MODIFIES SQL DATA` |
| `SECURITY_TYPE` | `DEFINER` hoặc `INVOKER` |
| `DEFINER` | Tài khoản thực thi theo security context |
| `SQL_MODE` | SQL mode được lưu khi routine được tạo |

Metadata phản ánh declaration. Nó không phải bằng chứng MySQL đã kiểm tra toàn bộ body có tuân thủ declaration hay không.

### 9.3. SHOW FUNCTION STATUS

```sql
SHOW FUNCTION STATUS
WHERE Db = 'app_db';
```

Lệnh này hữu ích để kiểm kê routine, người định nghĩa, thời điểm tạo và cập nhật. Để xem đầy đủ body và characteristic, kết hợp `SHOW CREATE FUNCTION`.

### 9.4. Kiểm tra biến binary logging

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'log_bin',
    'binlog_format',
    'log_bin_trust_function_creators'
);
```

Kiểm tra trên source và các replica có cấu hình liên quan. Không suy ra cấu hình của mọi node chỉ từ kết quả trên một server.

## 10. Ví dụ hoàn chỉnh: function thuần và function đọc bảng

### 10.1. Function tính toán thuần

```sql
DELIMITER $$

CREATE FUNCTION fn_net_amount(
    p_gross_amount DECIMAL(14,2),
    p_discount_percent DECIMAL(5,2)
)
RETURNS DECIMAL(14,2)
DETERMINISTIC
NO SQL
SQL SECURITY INVOKER
BEGIN
    RETURN ROUND(
        p_gross_amount * (1 - p_discount_percent / 100),
        2
    );
END$$

DELIMITER ;
```

Thử:

```sql
SELECT fn_net_amount(1000.00, 10.00) AS net_amount;
```

Với cùng tham số, kết quả không phụ thuộc bảng hay thời gian. `NO SQL` và `DETERMINISTIC` phù hợp.

### 10.2. Function đọc bảng cấu hình

```sql
CREATE TABLE shipping_rates (
    zone_code VARCHAR(10) NOT NULL,
    effective_from DATE NOT NULL,
    fee DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (zone_code, effective_from)
) ENGINE = InnoDB;
```

```sql
DELIMITER $$

CREATE FUNCTION fn_shipping_fee(p_zone_code VARCHAR(10))
RETURNS DECIMAL(12,2)
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_fee DECIMAL(12,2) DEFAULT NULL;

    SELECT fee
      INTO v_fee
      FROM shipping_rates
     WHERE zone_code = p_zone_code
       AND effective_from <= CURRENT_DATE
     ORDER BY effective_from DESC
     LIMIT 1;

    RETURN v_fee;
END$$

DELIMITER ;
```

Function đọc bảng và phụ thuộc ngày hiện tại. Khai báo `NOT DETERMINISTIC READS SQL DATA` mô tả đúng hai đặc điểm đó.

### 10.3. Kiểm tra định nghĩa và metadata

```sql
SHOW CREATE FUNCTION fn_net_amount;
SHOW CREATE FUNCTION fn_shipping_fee;

SELECT
    ROUTINE_NAME,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE()
  AND ROUTINE_TYPE = 'FUNCTION';
```

So sánh kết quả với logic thực tế. Nếu body thay đổi, cần xem lại cả hai đặc tính, không chỉ cập nhật phần SQL.

## 11. Quy trình đánh giá function trước khi bật binary logging

Trước khi tạo hoặc phát hành function trong hệ thống có replication, thực hiện các bước:

1. **Xác định mục đích:** function chỉ tính một giá trị, đọc bảng hay có side effect ghi dữ liệu?
2. **Liệt kê đầu vào thực:** tham số, thời gian, session state, bảng, routine khác và mọi trạng thái bên ngoài.
3. **Chọn tính xác định:** khai báo `DETERMINISTIC` chỉ khi cùng tham số thực sự luôn cho cùng kết quả; nếu không, dùng `NOT DETERMINISTIC`.
4. **Chọn SQL data access:** dùng đúng một trong `NO SQL`, `CONTAINS SQL`, `READS SQL DATA`, `MODIFIES SQL DATA`.
5. **Kiểm tra binary log:** xác nhận `log_bin`, `binlog_format` và `log_bin_trust_function_creators`.
6. **Kiểm tra quyền:** xác nhận `CREATE ROUTINE`, quyền quản trị mà cấu hình hiện tại yêu cầu và quyền của definer/invoker.
7. **Kiểm thử trên staging:** tạo function, gọi từ SELECT và DML đại diện, xác nhận output và tác dụng phụ.
8. **Kiểm thử replication:** kiểm tra dữ liệu trên source và replica với đúng binlog format của production.
9. **Triển khai definition nhất quán:** bảo đảm routine definition, definer và quyền tồn tại trên các node cần thiết.
10. **Giám sát:** theo dõi replication errors, lag và các chênh lệch dữ liệu sau khi phát hành.

## 12. Các tình huống replication cần chú ý

### 12.1. Function trả giá trị theo thời gian

Function dựa trên `CURRENT_DATE` hoặc thời gian hiện tại không deterministic theo cùng input qua nhiều thời điểm. Hãy khai báo đúng và hiểu cách built-in được ghi vào binary log. Nếu logic nghiệp vụ cần cùng một ngày áp dụng cho toàn bộ batch, truyền ngày đó thành tham số tường minh thường dễ kiểm thử hơn.

### 12.2. Function đọc bảng cấu hình

Nếu function đọc bảng giá, tỷ giá hoặc thuế, source và replica phải có trạng thái dữ liệu phù hợp tại thời điểm statement được áp dụng. Khi dữ liệu cấu hình thay đổi theo quy trình riêng, cần đảm bảo thứ tự replication và không dựa vào một bảng ngoài binary log.

### 12.3. Function sinh UUID hoặc giá trị ngẫu nhiên

Kết quả có thể khác giữa các lần gọi. Với DML quan trọng, xem xét row-based logging và kiểm thử trên đúng phiên bản. Không tự đánh dấu `DETERMINISTIC` để vượt qua kiểm tra tạo function.

### 12.4. Function có side effect

Function sửa bảng tạo thêm tác dụng phụ ngoài giá trị trả về. Nếu câu SQL bị retry, chạy lại hoặc được thực thi theo format khác, số lần ghi và thứ tự tác dụng phụ cần được đánh giá. Ưu tiên DML/procedure tường minh khi side effect là mục đích chính.

### 12.5. Khác biệt cấu hình giữa source và replica

Kiểm tra timezone, SQL mode, collation, routine definition, definer và privilege trên các node. Một function có thể chạy thành công ở source nhưng lỗi trên replica nếu routine hoặc tài khoản definer không có ở đó.

## 13. Lỗi thường gặp và cách xử lý

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| Lỗi 1418 khi CREATE FUNCTION | Binary logging bật, trust creators tắt và function thiếu khai báo được chấp nhận | Khai báo đúng `DETERMINISTIC`, `NO SQL` hoặc `READS SQL DATA` nếu thực sự phù hợp; kiểm tra policy/privilege |
| Lỗi 1419 về SUPER | Creator thiếu quyền quản trị mà cấu hình binary logging yêu cầu | Kiểm tra `log_bin_trust_function_creators` và quyền theo phiên bản; làm việc với DBA |
| Gắn `DETERMINISTIC` để CREATE thành công dù function đọc dữ liệu thay đổi | Nhầm khai báo là xác minh của server | Sửa declaration theo logic thật; đánh giá replication safety |
| Function đọc bảng nhưng khai báo `NO SQL` | Nhầm SQL data access với quyền hoặc cách gọi SQL | Dùng `READS SQL DATA` |
| Function có INSERT nhưng khai báo `CONTAINS SQL` | Đặc tính không phản ánh thao tác ghi | Dùng `MODIFIES SQL DATA` và xem lại thiết kế side effect |
| Cùng tham số nhưng kết quả khác | Phụ thuộc thời gian, bảng, session hoặc trạng thái ngoài | Khai báo `NOT DETERMINISTIC`; đưa phụ thuộc thành tham số nếu phù hợp |
| Source và replica khác kết quả | Statement được thực thi lại với trạng thái/giá trị khác | Kiểm tra binlog format, function body, built-in và trạng thái dữ liệu |
| Nghĩ ROW khiến mọi khai báo không còn quan trọng | Row logging chỉ thay đổi cách ghi DML, không xác minh routine | Vẫn khai báo đúng, kiểm thử DDL và replication topology |
| Bật trust creators để bỏ lỗi | Nới lỏng kiểm tra chứ không làm function an toàn | Chỉ thay đổi theo quyết định DBA và có review/kiểm thử |
| Xem metadata rồi kết luận body tuân thủ | Metadata chỉ phản ánh declaration | Đọc `SHOW CREATE FUNCTION` và kiểm tra logic thực tế |

## 14. Checklist trước production

- [ ] Đã xác định function thực sự phụ thuộc vào những input và trạng thái nào.
- [ ] `DETERMINISTIC`/`NOT DETERMINISTIC` phản ánh đúng ngữ nghĩa.
- [ ] Đặc tính SQL data access khớp câu lệnh thực tế trong routine.
- [ ] Không dùng `DETERMINISTIC` hoặc `NO SQL` chỉ để vượt qua lỗi tạo function.
- [ ] Đã hiểu đặc tính routine là advisory và server không xác minh toàn bộ body.
- [ ] Đã kiểm tra `@@GLOBAL.log_bin`.
- [ ] Đã kiểm tra `@@GLOBAL.binlog_format` trên đúng node.
- [ ] Đã kiểm tra `@@GLOBAL.log_bin_trust_function_creators`.
- [ ] Đã xác nhận quyền CREATE ROUTINE và quyền quản trị cần thiết.
- [ ] Đã xem xét tác động của `STATEMENT`, `ROW` hoặc `MIXED` với workload.
- [ ] Đã kiểm thử function có thời gian, random, UUID hoặc đọc bảng thay đổi.
- [ ] Đã kiểm thử side effect và giới hạn stored function.
- [ ] Đã kiểm tra routine definition, definer và quyền trên replica.
- [ ] Đã xác minh dữ liệu source/replica sau các DML đại diện.
- [ ] Có kế hoạch giám sát replication error và xử lý sai khác dữ liệu.

## 15. Kết luận

`DETERMINISTIC` mô tả function luôn trả cùng kết quả với cùng tham số; `NOT DETERMINISTIC` dùng khi kết quả có thể thay đổi do thời gian, dữ liệu bảng hoặc trạng thái khác. `NO SQL`, `CONTAINS SQL`, `READS SQL DATA` và `MODIFIES SQL DATA` mô tả mức độ truy cập dữ liệu của routine. Hai nhóm đặc tính độc lập và đều phải phản ánh đúng thân routine.

Binary logging quyết định replica nhận câu lệnh hay thay đổi hàng. Statement-based logging có thể khiến function được thực thi lại trên replica; row-based logging ghi thay đổi hàng và thường giảm rủi ro khác biệt cho DML; mixed mode kết hợp hai cách. Khi binary logging bật và `log_bin_trust_function_creators` tắt, MySQL áp dụng điều kiện bổ sung về quyền và khai báo khi tạo stored function. Các characteristic là advisory, không phải bằng chứng server đã xác minh function an toàn. Hãy kiểm tra cấu hình, quyền, routine definition và dữ liệu source/replica trước khi phát hành.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: CREATE PROCEDURE and CREATE FUNCTION Statements](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual: Stored Program Binary Logging](https://dev.mysql.com/doc/refman/8.4/en/stored-programs-logging.html)
- [MySQL 8.4 Reference Manual: Binary Log Formats](https://dev.mysql.com/doc/refman/8.4/en/binary-log-formats.html)
- [MySQL 8.4 Reference Manual: Stored Program Restrictions](https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html)
- [MySQL 8.4 Reference Manual: Replication and Binary Logging Options and Variables](https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html)
- [MySQL 8.4 Reference Manual: Replication and System Functions](https://dev.mysql.com/doc/refman/8.4/en/replication-features-functions.html)
