# TINYINT, SMALLINT, MEDIUMINT, INT, BIGINT và SIGNED/UNSIGNED

MySQL cung cấp năm kiểu số nguyên phổ biến: `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT` và `BIGINT`. Chúng khác nhau về dung lượng lưu trữ và miền giá trị. Mỗi kiểu còn có thể dùng dạng `SIGNED` hoặc `UNSIGNED`: dạng signed biểu diễn cả số âm và số không âm, còn unsigned chỉ biểu diễn số không âm và mở rộng giới hạn trên.

Chọn đúng kiểu số nguyên ảnh hưởng tới thiết kế bảng, khóa chính, khóa ngoại, index và cách ứng dụng Java truyền/nhận dữ liệu. Với module `DATABASE_MYSQL`, đây là nền tảng để thiết kế schema, viết truy vấn SQL, tối ưu index và xử lý transaction an toàn. Mục tiêu là chọn kiểu vừa đủ cho miền giá trị nghiệp vụ, đồng thời tương thích với các bảng và kiểu dữ liệu ở tầng ứng dụng.

## Mục tiêu

Sau bài này, bạn có thể:

- So sánh dung lượng và miền giá trị của năm kiểu số nguyên MySQL.
- Tính được miền `SIGNED` và `UNSIGNED` từ số bit.
- Chọn kiểu phù hợp cho số lượng, trạng thái, mã định danh và bộ đếm.
- Hiểu tác động của signedness tới phép toán, so sánh, `AUTO_INCREMENT` và khóa ngoại.
- Nhận biết overflow, strict SQL mode, display width và các alias như `BOOLEAN`.
- Thiết kế cột số nguyên tương thích với Java/JDBC và kiểm tra dữ liệu thực tế.

## 1. Dung lượng lưu trữ và miền giá trị

Năm kiểu số nguyên có kích thước cố định như sau:

| Kiểu | Số bit | Dung lượng | Miền SIGNED | Miền UNSIGNED |
|---|---:|---:|---:|---:|
| `TINYINT` | 8 | 1 byte | -128 đến 127 | 0 đến 255 |
| `SMALLINT` | 16 | 2 byte | -32.768 đến 32.767 | 0 đến 65.535 |
| `MEDIUMINT` | 24 | 3 byte | -8.388.608 đến 8.388.607 | 0 đến 16.777.215 |
| `INT` (`INTEGER`) | 32 | 4 byte | -2.147.483.648 đến 2.147.483.647 | 0 đến 4.294.967.295 |
| `BIGINT` | 64 | 8 byte | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | 0 đến 18.446.744.073.709.551.615 |

Kích thước lưu trữ không thay đổi khi thêm `UNSIGNED`. Ví dụ, `INT` và `INT UNSIGNED` đều chiếm 4 byte; khác biệt nằm ở cách diễn giải bit và miền giá trị.

### 1.1. Công thức tính miền giá trị

Với kiểu số nguyên có \(n\) bit:

- `SIGNED`: từ \(-2^{n-1}\) đến \(2^{n-1}-1\).
- `UNSIGNED`: từ \(0\) đến \(2^n-1\).

Ví dụ với `SMALLINT` có 16 bit:

\[
\text{SIGNED}: -2^{15} \ldots 2^{15}-1
= -32768 \ldots 32767
\]

\[
\text{UNSIGNED}: 0 \ldots 2^{16}-1
= 0 \ldots 65535
\]

Một bit được dùng làm bit dấu trong biểu diễn signed, nên miền dương tối đa của signed chỉ bằng một nửa miền unsigned (trừ khác biệt một đơn vị ở đầu mút). Unsigned dùng toàn bộ bit để biểu diễn giá trị không âm.

### 1.2. Vì sao có `MEDIUMINT`?

`MEDIUMINT` có 24 bit, nằm giữa `SMALLINT` và `INT`. Nó hữu ích khi miền dữ liệu lớn hơn 65.535 nhưng vẫn nằm trong khoảng 16.777.215 và cần tiết kiệm một byte cho mỗi giá trị so với `INT`. Tuy nhiên, nó ít phổ biến hơn `INT`; một số hệ sinh thái, driver hoặc công cụ có thể ánh xạ kiểu này không trực quan bằng các kiểu 8/16/32/64 bit. Cần cân nhắc khả năng tích hợp và bảo trì, không chỉ dung lượng.

## 2. Khai báo SIGNED và UNSIGNED

Kiểu số nguyên mặc định là signed. Có thể viết rõ `SIGNED` để tài liệu schema dễ đọc, nhưng thường không cần vì đó là mặc định:

```sql
CREATE TABLE temperature_reading (
    reading_id BIGINT NOT NULL AUTO_INCREMENT,
    temperature_c SMALLINT SIGNED NOT NULL,
    sensor_offset TINYINT SIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (reading_id)
) ENGINE=InnoDB;
```

Khi miền nghiệp vụ không chấp nhận số âm, có thể dùng `UNSIGNED`:

```sql
CREATE TABLE inventory_summary (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    reorder_level SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;
```

`UNSIGNED` không thay thế cho kiểm tra nghiệp vụ. Ví dụ, `quantity INT UNSIGNED` vẫn cho phép giá trị lớn tới 4.294.967.295, dù một cửa hàng có thể chỉ cho phép tồn kho tối đa vài triệu đơn vị. Nếu cần giới hạn nhỏ hơn miền của kiểu dữ liệu, hãy thêm ràng buộc hoặc kiểm tra ở tầng nghiệp vụ.

### 2.1. Chọn signed hay unsigned?

Chọn `UNSIGNED` khi tất cả giá trị hợp lệ đều không âm và cần thêm miền dương, ví dụ số lượng hàng, số lần thử, dung lượng byte hoặc bộ đếm. Chọn `SIGNED` khi giá trị có thể âm, ví dụ nhiệt độ, số dư có thể âm, chênh lệch, tọa độ tương đối hoặc delta.

Không nên tự động đổi mọi ID sang unsigned. Hãy xét hệ thống đang tích hợp, kiểu cột tham chiếu, ngôn ngữ ứng dụng và khả năng dùng chung schema. Signed `BIGINT` thường tương thích tự nhiên với kiểu Java `long`; `BIGINT UNSIGNED` có miền vượt quá giới hạn của Java `long`.

## 3. Chọn kiểu số nguyên theo dữ liệu nghiệp vụ

Một cách chọn thực tế là xác định giá trị nhỏ nhất/lớn nhất có thể xảy ra, tính tốc độ tăng trưởng và dự phòng cho vòng đời hệ thống. Không chọn chỉ theo số lượng bản ghi hiện tại.

| Dữ liệu | Kiểu gợi ý | Lý do và lưu ý |
|---|---|---|
| Cờ trạng thái nhỏ hoặc mã trạng thái có miền giới hạn | `TINYINT` hoặc `TINYINT UNSIGNED` | Đủ cho vài giá trị; nên có `CHECK` hoặc enum nghiệp vụ rõ ràng nếu cần giới hạn tập giá trị |
| Số lượng nhỏ, số lần thử có giới hạn | `SMALLINT UNSIGNED` | Miền 0–65.535; chỉ dùng nếu giới hạn tối đa phù hợp |
| Mã số/đếm có thể tới vài triệu | `MEDIUMINT` hoặc `MEDIUMINT UNSIGNED` | Tiết kiệm một byte so với `INT`, nhưng cần cân nhắc hỗ trợ của công cụ và driver |
| Số lượng thông thường, mã nội bộ, số bản ghi theo phạm vi lớn | `INT` hoặc `INT UNSIGNED` | Phù hợp nhiều ứng dụng; 4 byte |
| ID toàn hệ thống, bộ đếm lớn, dữ liệu tăng lâu dài | `BIGINT` hoặc `BIGINT UNSIGNED` | Miền rất lớn; 8 byte và index lớn hơn `INT` |
| Nhiệt độ, số dư có thể âm, độ lệch | Kiểu `SIGNED` đủ rộng | Không thể biểu diễn số âm bằng unsigned |

Ví dụ bảng đơn hàng có thể dùng `BIGINT` cho ID, `INT UNSIGNED` cho số lượng dòng hoặc tổng số đơn vị, và `TINYINT UNSIGNED` cho trạng thái. Tuy nhiên, tiền tệ thường cần `DECIMAL`, không dùng số nguyên nếu nghiệp vụ cần phần lẻ theo đơn vị tiền. Kiểu dữ liệu phải phản ánh đơn vị và độ chính xác, không chỉ độ lớn.

### 3.1. Ước lượng tăng trưởng ID

Giả sử hệ thống tạo trung bình 2 triệu bản ghi mỗi ngày:

- `INT SIGNED` có tối đa 2.147.483.647 giá trị dương. Nếu bắt đầu từ 1 và tăng đều 2 triệu/ngày, miền dương có thể cạn sau khoảng 1.073 ngày, xấp xỉ 2,94 năm.
- `INT UNSIGNED` có tối đa 4.294.967.295 giá trị, tương đương khoảng 2.147 ngày ở tốc độ đó, xấp xỉ 5,88 năm.
- `BIGINT SIGNED` có miền dương tới hơn 9,22 quintillion, đủ rộng cho phần lớn hệ thống nghiệp vụ thông thường.

Đây chỉ là phép ước lượng tuyến tính. ID có thể bị tiêu thụ bởi transaction rollback, thao tác xóa, import, batch và nhiều node ghi. Khi thiết kế khóa chính, hãy tính theo tốc độ cấp ID thực tế và thời hạn vận hành dự kiến.

## 4. AUTO_INCREMENT và kiểu số nguyên

`AUTO_INCREMENT` dùng với cột số nguyên được index, thường là primary key. Giá trị tự tăng phụ thuộc kiểu dữ liệu và signedness của cột. Khi chạm giới hạn kiểu, MySQL không thể tiếp tục cấp giá trị mới vượt miền.

Ví dụ:

```sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

`BIGINT UNSIGNED` có miền dương lớn, phù hợp với ID không âm có vòng đời dài. Tuy nhiên, nếu ứng dụng Java dùng `long`, hãy cân nhắc `BIGINT` signed để giữ ánh xạ đơn giản. Nếu thật sự cần miền trên `Long.MAX_VALUE`, ứng dụng phải dùng kiểu có thể biểu diễn đầy đủ giá trị và kiểm tra mapping của JDBC driver.

Các điểm cần nhớ:

- `AUTO_INCREMENT` không đảm bảo dãy số liên tục. Rollback, lỗi insert, cache cấp ID và thao tác xóa có thể tạo khoảng trống.
- Không dùng ID tự tăng làm số thứ tự nghiệp vụ cần liên tục hoặc không được bỏ số.
- Không giả định `AUTO_INCREMENT` bắt đầu lại từ 1 sau khi xóa hết hàng.
- Khi cột gần hết miền, việc đổi từ `INT` sang `BIGINT` có thể cần DDL tốn thời gian và ảnh hưởng đến khóa ngoại/index; hãy lập kế hoạch trước khi chạm ngưỡng.

## 5. Tác động tới index, row size và khóa ngoại

### 5.1. Kiểu nhỏ hơn có thể giúp index gọn hơn

Trong InnoDB, khóa chính được lưu trong clustered index và giá trị khóa chính cũng xuất hiện trong các secondary index để xác định bản ghi. Vì vậy, kích thước khóa chính có thể ảnh hưởng tới kích thước nhiều index khác. Nếu dùng `BIGINT` thay cho `INT`, phần giá trị khóa tăng từ 4 lên 8 byte; trên bảng lớn với nhiều secondary index, chênh lệch có thể đáng kể.

Kiểu nhỏ hơn cũng có thể giảm dung lượng row và tăng số bản ghi trên một page. Nhưng không nên chọn `TINYINT` nếu miền dữ liệu có nguy cơ vượt 255 chỉ để tiết kiệm vài byte. Một lần thay đổi kiểu sau này có thể cần rebuild bảng/index, cập nhật khóa ngoại và triển khai đồng bộ ứng dụng.

### 5.2. Khóa ngoại cần khớp kiểu và signedness

Với khóa ngoại dùng cột số nguyên, kiểu dữ liệu và dấu phải tương thích, bao gồm kích thước số nguyên và signedness. Ví dụ, `BIGINT UNSIGNED` nên tham chiếu tới `BIGINT UNSIGNED`, không ghép với `BIGINT` signed.

Ví dụ đúng:

```sql
CREATE TABLE account (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

CREATE TABLE account_event (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_id BIGINT UNSIGNED NOT NULL,
    event_type TINYINT UNSIGNED NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_account_event_account_id (account_id),
    CONSTRAINT fk_account_event_account
        FOREIGN KEY (account_id)
        REFERENCES account (account_id)
) ENGINE=InnoDB;
```

Ví dụ không tương thích về signedness:

```sql
-- account.account_id là BIGINT UNSIGNED
-- Cột con sau đây là BIGINT signed: không khớp kiểu khóa ngoại.
CREATE TABLE invalid_account_event (
    event_id BIGINT NOT NULL AUTO_INCREMENT,
    account_id BIGINT NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_invalid_account_event_account_id (account_id),
    CONSTRAINT fk_invalid_account_event_account
        FOREIGN KEY (account_id)
        REFERENCES account (account_id)
) ENGINE=InnoDB;
```

Đoạn thứ hai được đưa ra để nhận diện lỗi thiết kế; không dùng nó làm schema hợp lệ. Khi tạo khóa ngoại, cần xét thêm engine hỗ trợ, index, collation/charset đối với kiểu chuỗi và các quy tắc của phiên bản MySQL.

## 6. Overflow và SQL mode

Overflow xảy ra khi giá trị đưa vào cột vượt miền biểu diễn. Hành vi cụ thể phụ thuộc SQL mode của phiên server.

Kiểm tra mode hiện tại:

```sql
SELECT @@GLOBAL.sql_mode;
SELECT @@SESSION.sql_mode;
```

Với strict mode như `STRICT_TRANS_TABLES` hoặc `STRICT_ALL_TABLES`, thao tác ghi giá trị ngoài miền thường bị từ chối bằng lỗi. Trong chế độ không strict, MySQL có thể điều chỉnh giá trị về giới hạn gần nhất và phát cảnh báo. Với cột unsigned, giá trị âm cũng là ngoài miền; tùy mode, thao tác có thể bị từ chối hoặc được điều chỉnh về 0 kèm warning.

Ví dụ bảng thử nghiệm:

```sql
CREATE TABLE integer_limits (
    id INT UNSIGNED NOT NULL,
    small_value SMALLINT SIGNED NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Giá trị ở biên hợp lệ:

```sql
INSERT INTO integer_limits (id, small_value)
VALUES (4294967295, -32768);

SELECT * FROM integer_limits;
```

Giá trị sau vượt miền của `INT UNSIGNED`:

```sql
INSERT INTO integer_limits (id, small_value)
VALUES (4294967296, 0);
```

Giá trị sau vượt miền của `SMALLINT SIGNED`:

```sql
INSERT INTO integer_limits (id, small_value)
VALUES (1, 32768);
```

Trong strict mode, hai lệnh vượt miền sẽ báo lỗi. Trong non-strict mode, hãy đọc warning ngay sau câu lệnh để biết giá trị đã bị điều chỉnh ra sao:

```sql
SHOW WARNINGS;
```

Không dựa vào việc MySQL có thể clip giá trị để chấp nhận dữ liệu sai. Ứng dụng nên validate trước khi ghi, database nên dùng kiểu và constraint đúng, còn hệ thống giám sát cần ghi nhận lỗi ghi dữ liệu.

## 7. Signed và unsigned trong biểu thức SQL

Signedness ảnh hưởng tới cách MySQL đánh giá biểu thức số. Khi trộn giá trị signed và unsigned, phép so sánh hoặc phép toán có thể có kết quả khác với điều người viết truy vấn mong đợi do quy tắc chuyển kiểu.

Ví dụ, phép trừ unsigned có thể tạo kết quả âm về mặt toán học nhưng không biểu diễn được bằng kiểu unsigned. MySQL có SQL mode `NO_UNSIGNED_SUBTRACTION` để thay đổi cách xử lý kết quả phép trừ giữa các số nguyên unsigned; nếu không bật mode phù hợp, phép trừ có thể báo lỗi khi kết quả vượt miền unsigned.

Các nguyên tắc an toàn:

- Giữ cùng signedness giữa các cột dùng để join, so sánh và tham chiếu khóa ngoại.
- Không trộn số âm với cột unsigned nếu nghiệp vụ chưa định nghĩa rõ cách xử lý.
- Khi cần phép toán có thể âm, dùng kiểu signed đủ rộng hoặc ép kiểu có chủ đích.
- Kiểm tra kiểu dữ liệu của biểu thức trung gian, không chỉ kiểu cột đầu vào.
- Dùng `CAST()` khi cần thay đổi kiểu một cách rõ ràng, nhưng phải xác minh miền giá trị sau chuyển đổi.

Ví dụ minh họa phép trừ và mode:

```sql
SELECT CAST(0 AS UNSIGNED) - CAST(1 AS UNSIGNED);
```

Trên cấu hình không dùng `NO_UNSIGNED_SUBTRACTION`, biểu thức này có thể báo lỗi vì kết quả toán học là -1 nhưng kiểu kết quả unsigned không biểu diễn được. Không nên dùng unsigned cho các phép tính chênh lệch có khả năng âm.

## 8. Display width, ZEROFILL và BOOLEAN

### 8.1. `INT(11)` không có nghĩa là 11 chữ số

Trong cú pháp cũ, MySQL cho phép khai báo như `INT(11)` hoặc `TINYINT(1)`. Con số trong ngoặc là display width, không phải số byte, độ chính xác hay giới hạn giá trị. `INT(1)` và `INT(11)` vẫn có cùng kích thước 4 byte và cùng miền giá trị.

Display width cho kiểu số nguyên đã bị deprecated từ MySQL 8.0.17. Khi tạo schema mới, nên khai báo `INT`, `BIGINT UNSIGNED`... mà không thêm display width. Nếu cần hiển thị mã có số 0 ở đầu như `00042`, hãy xử lý ở tầng trình bày hoặc dùng chuỗi nếu số 0 đầu là một phần của định danh.

### 8.2. `ZEROFILL`

`ZEROFILL` từng được dùng để hiển thị số với số 0 ở đầu theo display width. Thuộc tính này cũng làm cột trở thành `UNSIGNED` và đã bị deprecated. Không dùng `ZEROFILL` cho thiết kế mới; định dạng số thuộc trách nhiệm của ứng dụng hoặc lớp báo cáo.

### 8.3. `BOOLEAN` và `BOOL`

Trong MySQL, `BOOLEAN` và `BOOL` là alias của `TINYINT(1)`. Giá trị 0 được xem là false, giá trị khác 0 được xem là true trong ngữ cảnh boolean. Tuy nhiên, alias này không tự giới hạn cột chỉ nhận 0 hoặc 1.

Nếu cần cột chỉ có hai giá trị, có thể viết:

```sql
CREATE TABLE feature_flag (
    feature_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    is_enabled TINYINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (feature_id),
    CONSTRAINT chk_feature_flag_is_enabled
        CHECK (is_enabled IN (0, 1))
) ENGINE=InnoDB;
```

MySQL thực thi `CHECK` constraint từ phiên bản 8.0.16. Với phiên bản cũ hơn, cần kiểm tra giới hạn của server và thực hiện validation ở tầng ứng dụng hoặc trigger phù hợp. Một số JDBC driver có thể ánh xạ `TINYINT(1)` thành kiểu boolean tùy cấu hình; điều đó không biến cột thành boolean hai trạng thái ở phía database.

## 9. Ánh xạ số nguyên với Java và JDBC

Khi ứng dụng Java kết nối MySQL qua JDBC, cần xét cả miền giá trị Java và MySQL:

| MySQL | Kiểu Java thường dùng | Lưu ý |
|---|---|---|
| `TINYINT` signed | `byte` | Miền -128 đến 127 |
| `TINYINT UNSIGNED` | `short` hoặc kiểu rộng hơn | Java `byte` không chứa đủ miền 0–255 |
| `SMALLINT` signed | `short` | Miền -32.768 đến 32.767 |
| `SMALLINT UNSIGNED` | `int` | Java `short` không chứa đủ miền 0–65.535 |
| `MEDIUMINT` | `int` | Java `int` đủ cho miền signed và unsigned của MEDIUMINT |
| `INT` signed | `int` | Miền tương ứng 32-bit signed |
| `INT UNSIGNED` | `long` | Java `int` không chứa đủ miền 0–4.294.967.295 |
| `BIGINT` signed | `long` | Miền tương ứng 64-bit signed |
| `BIGINT UNSIGNED` | `BigInteger` hoặc kiểu biểu diễn phù hợp | Giá trị unsigned có thể lớn hơn `Long.MAX_VALUE` |

Đây là hướng ánh xạ theo miền giá trị, không phải cam kết mọi JDBC getter hoặc driver đều trả về đúng kiểu Java đó trong mọi trường hợp. Hãy kiểm tra tài liệu Connector/J và dùng `ResultSetMetaData`, `getObject()` hoặc kiểu getter phù hợp để xác nhận mapping.

Ví dụ đọc một `INT UNSIGNED` an toàn vào `long`:

```java
long quantity = resultSet.getLong("quantity");
```

Java `long` chứa được toàn bộ miền `INT UNSIGNED`. Với `BIGINT UNSIGNED`, Java `long` không thể biểu diễn các giá trị lớn hơn 9.223.372.036.854.775.807. Nếu nghiệp vụ cần miền đầy đủ, hãy dùng `BigInteger` hoặc biểu diễn thập phân/chuỗi theo mapping đã kiểm thử; không ép về `long` rồi chấp nhận tràn số.

Khi ghi tham số, chọn setter phù hợp với miền và kiểu cột, ví dụ `setInt`, `setLong` hoặc `setBigDecimal`/cách bind tương ứng cho kiểu lớn. Validate giá trị trước khi bind để tránh gửi giá trị ngoài miền và phụ thuộc vào hành vi SQL mode.

## 10. Thay đổi kiểu số nguyên trong schema hiện có

Khi một cột gần chạm giới hạn, có thể cần đổi từ kiểu nhỏ sang kiểu rộng hơn, chẳng hạn `INT` sang `BIGINT`. Đây là thay đổi schema có ảnh hưởng tới dữ liệu, index, khóa ngoại và ứng dụng.

Trước khi thay đổi, kiểm tra:

1. Giá trị nhỏ nhất/lớn nhất hiện tại và tốc độ tăng trưởng.
2. Các bảng có khóa ngoại tham chiếu hoặc được tham chiếu bởi cột này.
3. Index, primary key, unique key, partitioning và trigger liên quan.
4. Kiểu tương ứng trong entity, DTO, API, event/message và code JDBC.
5. Kích thước bảng, thời gian DDL, lock/metadata lock và phương án rollback.

Ví dụ kiểm tra miền dữ liệu:

```sql
SELECT
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    COUNT(*) AS row_count
FROM orders;
```

Nếu cột hiện là `INT` và muốn chuyển sang `BIGINT`, câu lệnh minh họa là:

```sql
ALTER TABLE orders
    MODIFY COLUMN order_id BIGINT NOT NULL AUTO_INCREMENT;
```

Lệnh trên chỉ là minh họa cho một cột tự tăng không có ràng buộc phụ thuộc. Trong schema thật, phải giữ nguyên các thuộc tính `UNSIGNED`, `NOT NULL`, `DEFAULT`, comment, index và quan hệ khóa ngoại cần thiết. Nếu cột được tham chiếu bởi khóa ngoại, có thể phải điều chỉnh cả cột cha và cột con theo đúng thứ tự triển khai.

Không thực hiện DDL lớn trên production khi chưa biết thuật toán ALTER, mức độ khóa và thời gian chạy. Thử trên bản sao có kích thước gần thực tế, backup trước khi thay đổi và xác minh ứng dụng sau migration.

## 11. Bài thực hành

Thực hiện trong database lab riêng:

1. Tạo một bảng có đủ năm kiểu `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT` và `BIGINT`; dùng cả signed và unsigned.
2. Ghi lại `DATA_TYPE`, `COLUMN_TYPE` và `NUMERIC_PRECISION` trong `information_schema.COLUMNS` để thấy sự khác nhau giữa kiểu và thuộc tính unsigned.
3. Thử insert giá trị nhỏ nhất/lớn nhất hợp lệ của `TINYINT`, `SMALLINT` và `INT` theo cả hai signedness.
4. Thử một giá trị vượt miền trong strict mode; đọc lỗi và so sánh với hành vi trong môi trường non-strict lab nếu có.
5. Tạo hai bảng cha/con có khóa ngoại `BIGINT UNSIGNED`; sau đó thử thiết kế cột con signed để quan sát lỗi không tương thích.
6. Viết một truy vấn có phép trừ unsigned và giải thích vì sao kết quả âm không phù hợp với kiểu unsigned.
7. Tạo cột `TINYINT` cho trạng thái, thêm `CHECK (status IN (...))` và thử giá trị ngoài tập cho phép trên MySQL 8.0.16 trở lên.
8. Viết một class Java nhỏ đọc `INT UNSIGNED` và `BIGINT` qua JDBC; xác minh kiểu Java, miền giá trị và cách xử lý khi giá trị vượt `Long.MAX_VALUE`.

Bạn hoàn thành bài khi có thể chọn kiểu theo miền nghiệp vụ, giải thích tác động của signedness, phát hiện overflow và thiết kế khóa ngoại/ánh xạ Java không làm mất dữ liệu.

## 12. Nguyên tắc thiết kế

- Chọn kiểu số nguyên dựa trên miền giá trị hiện tại, tốc độ tăng trưởng và tuổi thọ hệ thống.
- `UNSIGNED` mở rộng miền không âm nhưng không biểu diễn được số âm; dung lượng byte không đổi.
- Giữ cùng kích thước và signedness cho các cột liên kết bằng khóa ngoại.
- Dùng `BIGINT` khi cần miền lớn, nhưng cân nhắc chi phí lưu trữ/index và mapping của ứng dụng.
- Không nhầm `INT(11)` với giới hạn 11 chữ số; display width không thay đổi miền giá trị.
- Không dùng `ZEROFILL` cho schema mới; định dạng số thuộc tầng trình bày.
- `BOOLEAN` là alias của `TINYINT(1)`, cần `CHECK` nếu chỉ chấp nhận 0 và 1.
- Validate miền dữ liệu ở ứng dụng và database; không dựa vào clipping trong non-strict mode.
- Lập kế hoạch migration trước khi cột tự tăng hoặc bộ đếm chạm giới hạn.
