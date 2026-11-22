# Điều kiện có thể khai thác chỉ mục và tránh chuyển kiểu ngoài ý muốn

Một truy vấn có thể có index phù hợp nhưng MySQL vẫn phải quét nhiều hàng nếu điều kiện WHERE bọc cột trong hàm, thực hiện phép tính trên cột hoặc so sánh hai phía có kiểu dữ liệu không tương thích. Điều kiện được viết sao cho optimizer có thể dùng index để định vị vùng dữ liệu thường được gọi là **sargable predicate**.

Với module **DATABASE_MYSQL**, viết điều kiện sargable giúp giảm số hàng cần đọc, tận dụng index range/ref lookup và tránh kết quả sai do implicit conversion. Bài này tập trung vào cách viết điều kiện trên số, chuỗi và ngày giờ; cách xử lý collation; cách bind parameter đúng kiểu trong Java/JDBC; và cách kiểm chứng bằng EXPLAIN.

## 1. Sargable predicate là gì?

Sargable là cách gọi điều kiện có thể được chuyển thành thao tác tìm kiếm trên index. Ví dụ, nếu có index trên created_at:

~~~sql
-- Có thể dùng index range trên created_at
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Điều kiện tạo ra một khoảng rõ ràng trên giá trị được lưu trong index. MySQL có thể định vị điểm bắt đầu và đọc các entry trong khoảng cần thiết.

Ngược lại:

~~~sql
-- Hàm được áp dụng lên cột được index
SELECT order_id, created_at
FROM orders
WHERE YEAR(created_at) = 2026;
~~~

Với B-tree index thông thường trên created_at, optimizer không thể trực tiếp dùng giá trị YEAR(created_at) để định vị một khoảng khóa như câu lệnh đầu. Nó có thể phải đánh giá hàm trên nhiều hàng hoặc chọn một kế hoạch khác.

Sargable không có nghĩa optimizer chắc chắn chọn index. Nếu điều kiện khớp phần lớn bảng, table scan vẫn có thể rẻ hơn. Sargability chỉ tạo cơ hội cho optimizer sử dụng index hiệu quả.

## 2. Tránh bọc cột được index trong hàm

Một quy tắc thực tế: nếu muốn tận dụng B-tree index trên một cột, hãy giữ cột đó ở dạng trực tiếp trong điều kiện và chuyển đổi giá trị đầu vào thay vì chuyển đổi từng hàng của cột.

### Ngày giờ

Không nên:

~~~sql
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-01-15';
~~~

Viết lại thành khoảng nửa mở:

~~~sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
~~~

Điều kiện thứ hai có thể dùng index range trên created_at và không bỏ sót phần microsecond cuối ngày.

### Số học trên cột

Giả sử có index trên salary. Tránh:

~~~sql
WHERE salary * 1.10 > 10000
~~~

Có thể chuyển phép tính sang phía hằng số:

~~~sql
WHERE salary > 10000 / 1.10
~~~

Đây là phép biến đổi đại số cho ví dụ đơn giản. Với DECIMAL, scale, rounding và kiểu tham số cần được chọn cẩn thận để giữ đúng quy tắc nghiệp vụ. Không áp dụng máy móc nếu phép biến đổi làm thay đổi độ chính xác hoặc cách xử lý NULL.

### Chuỗi chuẩn hóa

Nếu email có index và collation đã không phân biệt hoa/thường theo yêu cầu, không cần gọi LOWER trên cột:

~~~sql
-- Có thể cản trở lookup bằng index thông thường
WHERE LOWER(email) = LOWER(?)

-- So sánh trực tiếp nếu collation/schema đã đáp ứng quy tắc
WHERE email = ?
~~~

Nếu nghiệp vụ bắt buộc so sánh theo dạng chuẩn hóa nhưng cột vẫn lưu nguyên bản, cân nhắc generated column chứa giá trị chuẩn hóa hoặc functional index. Cần kiểm tra biểu thức, collation và phiên bản MySQL trước khi áp dụng.

## 3. So sánh giá trị cùng kiểu dữ liệu

MySQL có thể tự chuyển kiểu khi so sánh hai biểu thức khác kiểu. Việc chuyển đổi ngầm giúp SQL linh hoạt nhưng có thể:

- Làm kết quả khác với ý nghĩa nghiệp vụ.
- Khiến optimizer khó dùng index trên cột.
- Tạo warning khi chuỗi không chuyển được thành số hoặc ngày.
- Làm mất số 0 đầu của mã định danh.
- Gây sai khác do signed/unsigned hoặc character set/collation.

Hãy chọn kiểu dữ liệu đúng từ schema và truyền giá trị so sánh cùng kiểu với cột.

Quy tắc này cũng áp dụng cho JOIN. Nếu customers.customer_id là BIGINT UNSIGNED nhưng orders.customer_id lại là VARCHAR, biểu thức nối có thể cần chuyển kiểu và làm giảm khả năng dùng index ở một hoặc cả hai phía. Hãy thống nhất kiểu, signedness và ý nghĩa dữ liệu của các cột liên kết ngay trong schema:

~~~sql
-- Hai cột liên kết nên có cùng kiểu và signedness
customers.customer_id BIGINT UNSIGNED NOT NULL
orders.customer_id    BIGINT UNSIGNED NOT NULL
~~~

Không giải quyết sai khác schema bằng cách CAST cột trong mọi câu JOIN. Nếu phải chuyển đổi dữ liệu cũ, hãy chuẩn hóa kiểu ở migration hoặc tạo cột chuyển tiếp có index trong giai đoạn chuyển đổi.

### Chuỗi mã định danh không phải số

Giả sử customer_code là VARCHAR và có index:

~~~sql
CREATE TABLE external_customers (
    customer_code VARCHAR(32) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (customer_code)
) ENGINE=InnoDB;
~~~

Không nên so sánh mã chuỗi với số:

~~~sql
-- MySQL có thể chuyển chuỗi sang số để so sánh
SELECT customer_code, full_name
FROM external_customers
WHERE customer_code = 123;
~~~

Khi so sánh cột chuỗi với số, MySQL có thể chuyển các giá trị chuỗi sang kiểu số. Những chuỗi như '00123', '123' hoặc chuỗi có ký tự không phải số có thể bị diễn giải theo giá trị số thay vì được so sánh như mã nguyên văn. Điều này vừa dễ sai nghiệp vụ vừa có thể ngăn index chuỗi được dùng cho lookup hiệu quả.

Viết đúng kiểu:

~~~sql
SELECT customer_code, full_name
FROM external_customers
WHERE customer_code = '00123';
~~~

Nếu mã có số 0 đầu, dấu gạch hoặc chữ cái, hãy lưu và so sánh bằng CHAR/VARCHAR. Không chuyển mã định danh thành số chỉ vì phần lớn ký tự của nó là chữ số.

### Cột số nên được so sánh với giá trị số

Nếu order_id là BIGINT UNSIGNED, bind tham số kiểu số nguyên không dấu tương ứng:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE order_id = 123456;
~~~

Tránh truyền một chuỗi tùy ý rồi dựa vào việc MySQL tự ép kiểu. Với giá trị ngoài phạm vi kiểu số hoặc chuỗi không hợp lệ, kết quả chuyển đổi có thể tạo warning hoặc lỗi tùy ngữ cảnh.

## 4. Chú ý signed và unsigned

MySQL phân biệt kiểu số có dấu và không dấu. Ví dụ INT và INT UNSIGNED có miền giá trị khác nhau. Khi so sánh hai biểu thức khác signedness, quy tắc chuyển kiểu có thể làm thay đổi kết quả ở các giá trị biên.

Nếu khóa chính được khai báo:

~~~sql
customer_id BIGINT UNSIGNED NOT NULL
~~~

hãy dùng kiểu tham số tương ứng và không truyền số âm. Ở tầng Java, long là kiểu signed; trước khi bind cần xác thực giá trị không âm và nằm trong miền BIGINT UNSIGNED mà ứng dụng hỗ trợ. Nếu miền nghiệp vụ vượt khả năng biểu diễn của Java long, dùng BigInteger và chiến lược bind/serialize phù hợp.

Không CAST cột khóa sang SIGNED hoặc UNSIGNED trong WHERE chỉ để làm hai phía giống nhau:

~~~sql
-- Có thể khiến index trên customer_id khó được dùng trực tiếp
WHERE CAST(customer_id AS SIGNED) = ?
~~~

Hãy chuẩn hóa kiểu tham số ở tầng ứng dụng hoặc CAST giá trị tham số sang kiểu cột khi có lý do rõ ràng. Cột nên giữ nguyên để index có thể được khai thác.

## 5. Tránh chuyển đổi ngày giờ ngầm

Với DATE, DATETIME hoặc TIMESTAMP, truyền literal theo định dạng ISO mà MySQL hiểu rõ:

~~~sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Không truyền ngày theo định dạng phụ thuộc locale như '01/02/2026' rồi mong MySQL tự hiểu đó là ngày 1 tháng 2 hay ngày 2 tháng 1.

Nếu nguồn là chuỗi theo định dạng riêng, chuyển đổi chuỗi ở phía giá trị đầu vào:

~~~sql
WHERE created_at >= STR_TO_DATE(?, '%d/%m/%Y')
  AND created_at <  STR_TO_DATE(?, '%d/%m/%Y')
~~~

Trong ứng dụng, tốt hơn là parse chuỗi thành LocalDate/LocalDateTime rồi bind đúng kiểu JDBC. Khi cần lọc một ngày trên DATETIME, tạo khoảng bắt đầu ngày đến trước ngày kế tiếp; không gọi DATE() trên cột nếu muốn dùng index range thông thường.

Với TIMESTAMP, cần hiểu session time_zone và cách driver chuyển đổi thời điểm. Đừng bỏ offset của dữ liệu nguồn rồi giả định chuỗi còn lại là UTC. Kiểu tham số và quy tắc timezone phải thống nhất với schema và nghiệp vụ.

## 6. Tránh chuyển đổi character set và collation ngoài ý muốn

So sánh chuỗi chịu ảnh hưởng của character set và collation. Collation quyết định quy tắc so sánh như phân biệt hoa/thường hoặc dấu.

Kiểm tra cấu hình cột:

~~~sql
SHOW FULL COLUMNS FROM customers;

SELECT
    CHARSET(customer_code),
    COLLATION(customer_code)
FROM customers
LIMIT 1;
~~~

Nếu cột dùng collation không phân biệt hoa/thường, phép so sánh có thể xem 'ABC' và 'abc' là bằng nhau. Nếu mã định danh cần phân biệt hoa/thường, chọn collation phù hợp ngay ở schema.

Không áp dụng COLLATE hoặc CONVERT trên cột được index trong mọi truy vấn một cách tùy tiện:

~~~sql
-- Có thể thay đổi biểu thức được so sánh và hạn chế dùng index hiện tại
WHERE customer_code COLLATE utf8mb4_bin = ?
~~~

Nếu cần collation khác với quy tắc lưu trữ hiện tại, hãy xem xét đổi collation cột/index hoặc tạo cột chuẩn hóa/functional index phù hợp. Đổi collation có thể ảnh hưởng unique constraint vì hai chuỗi trước đây khác nhau có thể trở thành bằng nhau theo quy tắc mới; cần kiểm tra duplicate trước migration.

## 7. LIKE và khả năng dùng B-tree index

Với index trên customer_code, tìm prefix cố định thường có thể tạo range:

~~~sql
SELECT customer_code
FROM external_customers
WHERE customer_code LIKE 'CUS-2026%';
~~~

Wildcard ở đầu làm MySQL không biết điểm bắt đầu của prefix:

~~~sql
-- Thường không thể dùng B-tree để định vị prefix
WHERE customer_code LIKE '%2026'
~~~

Nếu nghiệp vụ cần tìm chuỗi con ở bất kỳ vị trí nào, cân nhắc FULLTEXT cho loại nội dung phù hợp, một search engine hoặc cấu trúc dữ liệu chuyên dụng. FULLTEXT không tương đương phép tìm substring chính xác cho mọi chuỗi/mã.

Kết quả LIKE còn phụ thuộc collation và escaping của wildcard '%' và '_'. Nếu người dùng nhập chuỗi literal có chứa wildcard, ứng dụng cần escape đúng cách và khai báo ESCAPE nếu cần.

## 8. OR, IN và các điều kiện phủ định

Điều kiện IN trên cùng một cột có thể được optimizer chuyển thành nhiều lookup/range:

~~~sql
SELECT order_id
FROM orders
WHERE status IN ('PAID', 'SHIPPED', 'DELIVERED');
~~~

Điều kiện OR trên các cột có index khác nhau có thể dùng Index Merge trong một số trường hợp:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE email = 'a@example.com'
   OR phone = '+84123456789';
~~~

Nhưng không phải mọi OR đều dùng index tốt. Nếu một nhánh không chọn lọc hoặc không có index, optimizer có thể chọn scan. Hãy kiểm tra EXPLAIN trước khi viết lại.

Không tự động thay OR bằng UNION ALL: một hàng thỏa cả hai nhánh sẽ xuất hiện hai lần nếu không xử lý trùng, làm thay đổi ngữ nghĩa. Nếu viết lại bằng UNION, thao tác loại trùng có thêm chi phí và có thể loại những hàng vốn được phép lặp.

Các điều kiện phủ định như <> hoặc NOT IN thường khó chọn lọc và có thể phải đọc nhiều hàng. Riêng NOT IN còn có bẫy NULL ở tập con; nếu ý định là anti-join, cân nhắc NOT EXISTS và kiểm tra nullability.

## 9. NULL và điều kiện có thể dùng index

Không dùng phép bằng để kiểm tra NULL:

~~~sql
-- Sai ý nghĩa: phép so sánh trả UNKNOWN
WHERE deleted_at = NULL

-- Đúng
WHERE deleted_at IS NULL
~~~

B-tree index của MySQL có thể chứa giá trị NULL; điều kiện IS NULL có thể sử dụng index nếu optimizer thấy có lợi. Tuy nhiên, nếu phần lớn hàng đều NULL, điều kiện có thể không đủ chọn lọc để index đem lại lợi ích.

Khi cần so sánh null-safe giữa hai biểu thức, MySQL có toán tử <=>. Nhưng không nên bọc cột trong COALESCE/IFNULL chỉ để thay NULL thành một giá trị giả nếu điều đó làm thay đổi ngữ nghĩa hoặc cản trở index:

~~~sql
-- Hàm trên cột
WHERE COALESCE(deleted_at, '9999-12-31') > ?

-- Nếu đúng nghiệp vụ, tách điều kiện trực tiếp
WHERE deleted_at > ?
   OR deleted_at IS NULL
~~~

Hai câu lệnh chỉ tương đương khi quy tắc nghiệp vụ xác định NULL được xem là giá trị lớn hơn mọi mốc thời gian. Hãy xác minh ngữ nghĩa trước khi viết lại; OR có thể cần kế hoạch khác và phải được đo bằng EXPLAIN.

## 10. Composite index và thứ tự điều kiện

Giả sử truy vấn thường lọc theo status và khoảng created_at:

~~~sql
CREATE INDEX idx_orders_status_created
    ON orders (status, created_at);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

Index có equality trên cột đầu tiên status và range trên created_at, nên có thể dùng cả hai phần để xác định vùng khóa. Thứ tự cột trong index quan trọng hơn thứ tự viết điều kiện trong WHERE.

Nếu chỉ lọc created_at mà không có status, index này không có leftmost prefix phù hợp cho lookup trực tiếp theo created_at. Có thể cần index riêng bắt đầu bằng created_at nếu workload thực tế yêu cầu.

Không tạo một index cho mọi hoán vị cột. Mỗi index làm tăng dung lượng và chi phí ghi; hãy gom các truy vấn theo mẫu điều kiện và thứ tự sắp xếp để chọn một tập index tối thiểu có lợi.

## 11. Khi nào nên dùng generated column hoặc functional index?

Đôi khi nghiệp vụ thực sự cần tìm theo biểu thức, chẳng hạn email không phân biệt hoa/thường trong khi vẫn muốn lưu giá trị gốc. Có thể tạo generated column chuẩn hóa rồi đánh index:

~~~sql
CREATE TABLE users (
    user_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(255) NOT NULL,
    email_normalized VARCHAR(255)
        GENERATED ALWAYS AS (LOWER(email)) STORED,
    PRIMARY KEY (user_id),
    KEY idx_users_email_normalized (email_normalized)
) ENGINE=InnoDB;
~~~

Truy vấn:

~~~sql
SELECT user_id, email
FROM users
WHERE email_normalized = LOWER(?);
~~~

Functional index được hỗ trợ từ MySQL 8.0.13:

~~~sql
CREATE INDEX idx_users_lower_email
    ON users ((LOWER(email)));
~~~

Biểu thức truy vấn cần khớp với functional key part theo các quy tắc của MySQL. Generated column tường minh thường dễ quan sát và tái sử dụng hơn trong schema. Cả hai cách đều có chi phí lưu trữ/duy trì khi dữ liệu thay đổi; không tạo chỉ vì muốn giữ một điều kiện không sargable mà chưa đo lợi ích.

## 12. Bind parameter đúng kiểu trong Java/JDBC

PreparedStatement giúp tách dữ liệu khỏi cấu trúc SQL và cho phép driver gửi giá trị theo kiểu phù hợp. Không nối chuỗi tham số vào SQL và không bind mọi giá trị dưới dạng String.

### Chuỗi

~~~java
String sql = "SELECT customer_code, full_name " +
             "FROM external_customers " +
             "WHERE customer_code = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "00123");
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            String code = rs.getString("customer_code");
        }
    }
}
~~~

### Số nguyên

~~~java
String sql = "SELECT order_id FROM orders WHERE order_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 123456L);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
        }
    }
}
~~~

### Số thập phân

~~~java
String sql = "SELECT payment_id FROM payments WHERE amount >= ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setBigDecimal(1, new BigDecimal("1000.00"));
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long paymentId = rs.getLong("payment_id");
        }
    }
}
~~~

### Ngày

~~~java
String sql = "SELECT order_id FROM orders WHERE order_date = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setObject(1, LocalDate.of(2026, 1, 15));
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
        }
    }
}
~~~

Các ví dụ giả định đã import java.sql.PreparedStatement, java.sql.ResultSet, java.math.BigDecimal và java.time.LocalDate; connection là JDBC Connection đang mở. Cách viết chuỗi SQL dùng được cả trên các phiên bản Java trước text block. setObject(LocalDate) cần driver JDBC hỗ trợ JDBC 4.2; với DATETIME/TIMESTAMP, dùng LocalDateTime/Instant hoặc JDBC temporal type theo quy tắc timezone của ứng dụng và driver.

PreparedStatement không tự sửa schema sai. Nếu cột là VARCHAR nhưng ứng dụng bind số, hoặc cột là BIGINT nhưng ứng dụng gửi chuỗi tùy ý, vẫn cần chuẩn hóa kiểu ở biên ứng dụng.

## 13. CAST tham số hay CAST cột?

Nếu đầu vào đến dưới dạng chuỗi nhưng cột là số, ép kiểu tham số thường thuận lợi hơn:

~~~sql
-- Ưu tiên giữ nguyên cột được index
WHERE order_id = CAST(? AS UNSIGNED)

-- Tránh bọc cột
WHERE CAST(order_id AS CHAR) = ?
~~~

Tuy nhiên, tốt nhất vẫn là parse dữ liệu đầu vào và bind đúng kiểu từ Java. CAST tham số chỉ nên dùng khi có lý do về giao thức hoặc kiểu biểu thức; nó không thay thế validation.

Nếu dữ liệu nguồn không hợp lệ, CAST có thể trả giá trị chuyển đổi kèm warning hoặc lỗi tùy kiểu và SQL mode. Không xem CAST là bộ xác thực. Hãy kiểm tra dữ liệu trước khi truy vấn hoặc ghi.

## 14. Kiểm chứng bằng EXPLAIN

Không kết luận index có được dùng chỉ từ hình thức câu SQL. Hãy kiểm tra kế hoạch:

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
~~~

Các cột cần xem:

- type: access method như range, ref, index hoặc ALL.
- possible_keys: index optimizer xem xét.
- key: index thực tế được chọn.
- key_len: độ dài phần key được dùng.
- rows: số hàng ước lượng cần đọc.
- filtered: tỷ lệ hàng còn lại sau điều kiện lọc bổ sung.
- Extra: Using index, Using index condition, Using where, Using filesort...

So sánh với điều kiện bọc cột:

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-01-15';
~~~

Kế hoạch có thể thay đổi theo dữ liệu, index, phiên bản và thống kê. Không phải mọi truy vấn dùng ALL đều sai; bảng nhỏ hoặc điều kiện trả về phần lớn hàng có thể khiến table scan rẻ hơn.

Nếu cần đo số hàng và thời gian thực tế, dùng EXPLAIN ANALYZE trên SELECT phù hợp trong môi trường đã đánh giá tải. Lệnh này thực thi truy vấn thật, nên không dùng tùy tiện với truy vấn nặng.

## 15. Quy trình sửa điều kiện không sargable

1. Xác định cột được index và kiểu dữ liệu khai báo của nó.
2. Đọc biểu thức WHERE, JOIN và ORDER BY để tìm hàm, phép tính hoặc ép kiểu trên cột.
3. Kiểm tra kiểu của literal và parameter ở phía ứng dụng.
4. Xác nhận ý nghĩa nghiệp vụ của NULL, collation, signedness và timezone.
5. Viết lại điều kiện để giữ nguyên cột và chuyển đổi phía giá trị đầu vào.
6. Nếu cần truy vấn theo biểu thức, cân nhắc generated column hoặc functional index.
7. Chạy EXPLAIN trước và sau với cùng bộ tham số.
8. Đo EXPLAIN ANALYZE khi phù hợp để so số hàng thực tế và thời gian.
9. Kiểm tra kết quả nghiệp vụ có giữ nguyên, đặc biệt ở giá trị biên và dữ liệu không hợp lệ.
10. Đo cả chi phí ghi nếu thêm index hoặc generated column.

## 16. Các lỗi thường gặp

| Cách viết | Vấn đề có thể gặp | Hướng xử lý |
|---|---|---|
| YEAR(date_col) = 2026 | Hàm bọc cột ngày | Dùng khoảng thời gian |
| DATE(date_col) = ngày | Hàm bọc cột DATETIME | Dùng khoảng nửa mở |
| numeric_col + 1 = ? | Phép tính trên cột | Chuyển đổi phía tham số nếu tương đương |
| varchar_code = 123 | So sánh chuỗi với số, mất ngữ nghĩa mã | Bind chuỗi đúng kiểu |
| CAST(indexed_col AS CHAR) = ? | Ép kiểu trên cột | Bind/CAST tham số |
| LOWER(indexed_col) = ? | Hàm trên cột | Collation phù hợp hoặc generated/functional index |
| LIKE '%suffix' | Wildcard đầu chuỗi | Search strategy khác nếu cần substring |
| COALESCE(indexed_col, ...) = ? | Hàm trên cột và thay đổi NULL semantics | Tách điều kiện nếu đúng nghiệp vụ |
| Bind mọi parameter bằng setString | Implicit conversion và sai kiểu | Dùng setLong, setBigDecimal, setString, setObject phù hợp |

## 17. Checklist trước khi đưa truy vấn vào production

1. Cột lọc/join có index phù hợp không?
2. Có áp dụng hàm, phép tính hoặc CAST trực tiếp lên cột được index không?
3. Kiểu parameter có khớp kiểu cột và signedness không?
4. Mã định danh có bị so sánh như số không?
5. Chuỗi có character set/collation đúng với nghiệp vụ không?
6. Điều kiện ngày giờ có dùng khoảng rõ ràng và đúng timezone không?
7. NULL có được xử lý bằng IS NULL/IS NOT NULL hoặc logic phù hợp không?
8. LIKE có prefix cố định hay wildcard ở đầu?
9. Composite index có được dùng theo leftmost prefix không?
10. EXPLAIN có chọn access path hợp lý với độ chọn lọc dữ liệu không?
11. Kết quả có được kiểm tra ở giá trị biên, chuỗi không hợp lệ và dữ liệu NULL không?
12. Nếu thêm functional index/generated column, lợi ích đọc có bù chi phí ghi và lưu trữ không?

## 18. Bài tập thực hành

1. Tạo index trên orders.created_at bằng CREATE INDEX idx_orders_created_at ON orders (created_at); so sánh EXPLAIN của YEAR(created_at) = 2026 và điều kiện khoảng năm 2026.
2. Tạo bảng external_customers có customer_code VARCHAR và index; so sánh điều kiện customer_code = 123 với customer_code = '00123'.
3. Thử dữ liệu mã '00123', '123' và '123A'; giải thích rủi ro khi so sánh chuỗi với số.
4. Tạo truy vấn salary * 1.1 > ? rồi viết lại để giữ cột salary trực tiếp; kiểm tra kết quả ở giá trị biên.
5. So sánh LIKE 'CUS-2026%' và LIKE '%2026' trên cùng cột có index.
6. Dùng PreparedStatement với setString, setLong và setBigDecimal cho đúng kiểu cột.
7. Kiểm tra CHARSET và COLLATION của một cột; thử truy vấn phân biệt hoa/thường theo yêu cầu.
8. Tạo generated column LOWER(email), đánh index và so sánh kế hoạch với truy vấn LOWER(email) không có functional index.
9. Dùng EXPLAIN và EXPLAIN ANALYZE để so sánh số hàng ước lượng với số hàng thực tế sau khi sửa điều kiện.
10. Viết một ghi chú giải thích vì sao truy vấn mới giữ nguyên ngữ nghĩa nhưng có access path tốt hơn.

Bạn hoàn thành bài khi nhận diện được điều kiện không sargable, biết chuyển đổi giá trị đầu vào thay vì bọc cột, truyền parameter đúng kiểu và chứng minh thay đổi bằng EXPLAIN. Mục tiêu là giữ ngữ nghĩa nghiệp vụ chính xác đồng thời giúp MySQL định vị dữ liệu bằng index.
