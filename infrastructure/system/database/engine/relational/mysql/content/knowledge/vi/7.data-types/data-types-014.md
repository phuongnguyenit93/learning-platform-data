# Chuyển kiểu ngầm định, so sánh số/chuỗi và mất khả năng dùng chỉ mục

MySQL có thể tự chuyển kiểu dữ liệu khi biểu thức so sánh hoặc tính toán kết hợp các giá trị khác kiểu. Điều này giúp một số câu SQL ngắn gọn hơn, nhưng cũng dễ tạo ra kết quả bất ngờ và làm truy vấn không sử dụng được index như mong đợi.

Một trường hợp điển hình là cột mã được khai báo `VARCHAR` nhưng ứng dụng so sánh với một số nguyên. MySQL phải chuyển giá trị để so sánh theo quy tắc kiểu dữ liệu. Nhiều chuỗi khác nhau có thể cùng biểu diễn một giá trị số, nên optimizer không thể luôn dùng index chuỗi để tìm chính xác kết quả. Truy vấn có thể chuyển từ index lookup sang quét nhiều hàng.

Trong module **DATABASE_MYSQL**, hiểu chuyển kiểu ngầm định giúp thiết kế kiểu dữ liệu nhất quán, viết điều kiện lọc chính xác, giữ khả năng sử dụng index, tối ưu join và bind tham số JDBC đúng kiểu. Bài học này tập trung vào quy tắc so sánh số/chuỗi, tác động tới execution plan và cách sửa truy vấn an toàn.

## 1. Chuyển kiểu ngầm định là gì?

Chuyển kiểu ngầm định (implicit type conversion) xảy ra khi MySQL tự chuyển một toán hạng sang kiểu khác để thực hiện phép toán. Ví dụ:

```sql
SELECT
    10 = '10' AS same_numeric_value,
    '010' = 10 AS leading_zero,
    '10' = '010' AS same_string;
```

Kết quả minh họa:

| Biểu thức | Kết quả | Lý do |
|---|---:|---|
| `10 = '10'` | 1 | Một toán hạng là số, phép so sánh được thực hiện theo quy tắc số |
| `'010' = 10` | 1 | Chuỗi được chuyển sang giá trị số 10 |
| `'10' = '010'` | 0 | Hai chuỗi được so sánh như chuỗi |

Điểm cần nhớ: cùng một dữ liệu có thể cho kết quả khác nhau tùy kiểu của hai toán hạng. `'10'` và `'010'` khác nhau khi so sánh chuỗi, nhưng cùng giá trị khi chuyển sang số.

Chuyển kiểu ngầm định cũng xuất hiện trong:

- Điều kiện `WHERE` và `HAVING`.
- Biểu thức `JOIN ... ON` khi hai cột có kiểu khác nhau.
- Các toán tử số học, phép nối chuỗi và biểu thức điều kiện.
- So sánh trong `IN`, `CASE` hoặc `COALESCE` khi các giá trị có kiểu không đồng nhất.

Không nên dựa vào chuyển kiểu ngầm định để biểu diễn quy tắc nghiệp vụ. Hãy chọn kiểu cột đúng bản chất dữ liệu và truyền giá trị so sánh với kiểu tương ứng.

## 2. Quy tắc so sánh kiểu dữ liệu trong MySQL

Quy tắc chuyển kiểu phụ thuộc loại toán hạng. Một số trường hợp phổ biến:

| Hai toán hạng | Cách so sánh thường gặp |
|---|---|
| Hai chuỗi | So sánh theo character set và collation áp dụng |
| Hai số nguyên | So sánh số nguyên |
| DECIMAL với số nguyên hoặc DECIMAL | So sánh theo số thập phân chính xác |
| Số dấu phẩy động với giá trị số | Có thể chuyển sang phép so sánh dấu phẩy động gần đúng |
| Chuỗi với số | Thường chuyển chuỗi sang số và so sánh theo ngữ cảnh số |
| Cột DATETIME/TIMESTAMP với hằng số trong phép so sánh trực tiếp phù hợp | MySQL có thể chuyển hằng số sang kiểu thời gian; một số ngữ cảnh như `IN()` có quy tắc riêng |

Đây là bản tóm tắt cho các trường hợp thường gặp. Biểu thức phức tạp, kiểu temporal, binary string, JSON, collation và các hàm có quy tắc riêng có thể có hành vi khác. Khi cần kết quả chính xác, kiểm tra tài liệu kiểu dữ liệu và thử trên phiên bản server đang chạy.

### 2.1. So sánh chuỗi với chuỗi

Khi hai toán hạng là chuỗi, MySQL so sánh theo quy tắc character set và collation. Ví dụ:

```sql
SELECT
    '10' = '010' AS string_equal,
    'A' = 'a' AS case_equal;
```

Kết quả phụ thuộc collation cho phép phân biệt hoa/thường hay không. Với collation không phân biệt hoa/thường, `'A'` và `'a'` có thể được xem là bằng nhau.

Nếu cột lưu mã định danh như số tài khoản, mã bưu chính hoặc mã sản phẩm có số 0 ở đầu, hãy lưu dưới dạng chuỗi và so sánh bằng chuỗi. Các số 0 ở đầu là một phần của mã, không phải phần định dạng số có thể bỏ đi.

### 2.2. So sánh chuỗi với số

Khi một toán hạng là chuỗi và toán hạng kia là số, MySQL có thể chuyển chuỗi sang giá trị số để so sánh. Ví dụ:

```sql
SELECT
    '00123' = 123 AS leading_zero_match,
    '123' = 123 AS exact_digits_match;
```

Cả hai biểu thức có thể trả về 1 vì các chuỗi được diễn giải thành giá trị số 123. Điều này khác hoàn toàn so với phép so sánh chuỗi.

Chuỗi không phải số hợp lệ hoặc chỉ có một phần biểu diễn số có thể dẫn tới kết quả gây bất ngờ và warning. Ví dụ:

```sql
SELECT CAST('123xyz' AS DECIMAL(10, 2));
SHOW WARNINGS;
```

MySQL có thể chuyển phần đầu nhận diện được thành số và phát cảnh báo về phần dữ liệu không hợp lệ. Không nên dùng hành vi này để xác thực mã hoặc dữ liệu nghiệp vụ. Hãy kiểm tra định dạng đầu vào trước khi lưu hoặc so sánh.

### 2.3. So sánh số nguyên với DECIMAL và FLOAT

Các kiểu số không giống nhau về độ chính xác:

- `TINYINT`, `INT`, `BIGINT` biểu diễn số nguyên.
- `DECIMAL(p,s)` lưu số thập phân chính xác với độ chính xác và scale được khai báo.
- `FLOAT` và `DOUBLE` dùng biểu diễn dấu phẩy động gần đúng.

Nếu nghiệp vụ cần tiền hoặc giá trị thập phân phải so sánh chính xác, thường nên dùng `DECIMAL` thay vì `FLOAT`/`DOUBLE`. Trộn kiểu số có thể làm MySQL chuyển biểu thức sang kiểu gần đúng, khiến kết quả so sánh khác kỳ vọng ở các giá trị biên.

## 3. Vì sao so sánh cột chuỗi với số có thể làm mất index?

Giả sử bảng lưu mã khách hàng dưới dạng chuỗi:

```sql
CREATE TABLE external_codes (
    code VARCHAR(20) NOT NULL,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (code)
) ENGINE = InnoDB;
```

Dữ liệu có thể chứa các giá trị:

```sql
INSERT INTO external_codes (code, description) VALUES
    ('123', 'Mã tiêu chuẩn'),
    ('00123', 'Mã có số 0 ở đầu'),
    ('123A', 'Mã có hậu tố chữ');
```

Nếu ứng dụng chạy:

```sql
SELECT code, description
FROM external_codes
WHERE code = 123;
```

MySQL phải so sánh cột chuỗi với một giá trị số. Các chuỗi như `'123'`, `'00123'` và trong một số ngữ cảnh cả chuỗi có phần số kèm ký tự có thể cùng chuyển thành giá trị số tương đương. Optimizer không thể đơn giản tìm một khóa chuỗi duy nhất trong B-tree và bỏ qua các giá trị còn lại có thể khớp theo phép chuyển kiểu.

Do đó, MySQL thường không thể dùng index trên cột chuỗi để thực hiện phép tìm kiếm chính xác cho điều kiện trộn chuỗi và số này. Nó có thể phải quét bảng hoặc quét một phạm vi lớn rồi chuyển từng giá trị để so sánh.

Cách đúng khi `code` là mã định danh dạng chuỗi:

```sql
SELECT code, description
FROM external_codes
WHERE code = '123';
```

Hằng số chuỗi có cùng kiểu ngữ nghĩa với cột. Optimizer có thể dùng primary key để tìm giá trị chính xác. Kết quả chỉ khớp mã `'123'`, không khớp `'00123'`.

### 3.1. Vì sao optimizer không thể chỉ chuyển hằng số sang chuỗi?

Nếu MySQL tự chuyển số 123 thành chuỗi `'123'` trong mọi trường hợp, kết quả sẽ thay đổi so với quy tắc so sánh số. Ví dụ `'00123' = 123` có thể đúng trong so sánh số nhưng `'00123' = '123'` là sai trong so sánh chuỗi.

Do một giá trị số có thể tương ứng với nhiều cách biểu diễn chuỗi, tìm đúng một khóa `'123'` không đủ để bảo đảm tìm đủ mọi hàng thỏa điều kiện số. Đó là lý do phép so sánh kiểu hỗn hợp trên cột chuỗi có thể làm index không dùng được theo cách lookup thông thường.

### 3.2. Không nhầm với cột số so sánh hằng chuỗi

Trường hợp ngược lại thường thuận lợi hơn:

```sql
CREATE TABLE numeric_codes (
    code BIGINT NOT NULL,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (code)
) ENGINE = InnoDB;

SELECT code, description
FROM numeric_codes
WHERE code = '123';
```

Nếu cột là kiểu số và toán hạng còn lại là một hằng chuỗi có thể chuyển thành số, optimizer có thể chuyển hằng số sang kiểu số và sử dụng index của cột. Tuy vậy, hãy truyền đúng kiểu từ ứng dụng và xác minh kế hoạch bằng `EXPLAIN`, đặc biệt khi tham số không phải hằng số đơn giản hoặc biểu thức phức tạp.

## 4. Hàm chuyển kiểu trên cột cũng có thể làm index không được sử dụng

Một cách viết thường gặp là chuyển cột về số ngay trong điều kiện:

```sql
SELECT code, description
FROM external_codes
WHERE CAST(code AS UNSIGNED) = 123;
```

Biểu thức này buộc MySQL áp dụng hàm `CAST` lên giá trị của từng hàng. Index B-tree thông thường được tổ chức theo giá trị `code` nguyên bản, không phải theo kết quả của biểu thức `CAST(code AS UNSIGNED)`. Vì thế optimizer thường không thể dùng index `code` như một lookup trực tiếp.

Tương tự, các biểu thức sau có thể khiến index thường khó được dùng:

```sql
WHERE LOWER(email) = 'user@example.com'
WHERE YEAR(created_at) = 2026
WHERE amount + 0 = 100
```

Các ví dụ này đều biến đổi cột trước khi so sánh. Tùy biểu thức và phiên bản, optimizer có thể áp dụng một số phép biến đổi hoặc dùng functional index, nhưng không nên mặc định index cột gốc vẫn có hiệu quả.

Ưu tiên viết điều kiện theo dạng cột nguyên bản so sánh với giá trị đã chuẩn hóa:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
```

Thay vì:

```sql
WHERE YEAR(created_at) = 2026
```

Dạng khoảng giữ cột `created_at` không bị bọc trong hàm, thường cho phép range scan trên index thời gian.

## 5. Cách viết lại truy vấn để giữ index

### 5.1. Đặt kiểu đúng ở phía hằng số hoặc tham số

Nếu cột lưu chuỗi:

```sql
-- Không nên: so sánh cột VARCHAR với số
SELECT *
FROM external_codes
WHERE code = 123;

-- Nên: so sánh chuỗi với chuỗi
SELECT *
FROM external_codes
WHERE code = '123';
```

Nếu cột lưu số:

```sql
-- Cột BIGINT được so sánh với giá trị số
SELECT *
FROM numeric_codes
WHERE code = 123;
```

Tránh bọc cột được đánh index trong `CAST` hoặc hàm khác nếu mục tiêu là dùng index thông thường. Khi cần chuyển kiểu, hãy chuyển giá trị đầu vào trước khi gửi truy vấn.

### 5.2. Dùng CAST rõ ràng ở phía giá trị

Khi đầu vào ban đầu là chuỗi nhưng cột thực sự là số, có thể chuyển giá trị tham số sang kiểu số trước:

```sql
SELECT *
FROM numeric_codes
WHERE code = CAST('123' AS UNSIGNED);
```

Biểu thức phía phải là giá trị có thể tính trước, còn cột được giữ nguyên. Optimizer có thể sử dụng index của cột số. Dù vậy, cần xác minh dữ liệu đầu vào hợp lệ và kiểm tra bằng `EXPLAIN`.

Nếu cột là chuỗi mã định danh, không chuyển tham số sang số. Hãy giữ số 0 ở đầu và mọi ký tự có ý nghĩa nghiệp vụ.

### 5.3. Chuẩn hóa schema khi hai cột cùng biểu diễn một khái niệm

Một lỗi thiết kế phổ biến là dùng `customer_id BIGINT` trong bảng này nhưng dùng `customer_id VARCHAR(30)` trong bảng khác. Khi join, MySQL phải giải quyết khác biệt kiểu dữ liệu, có thể gây chuyển kiểu và làm giảm khả năng dùng index.

Ví dụ không tốt:

```sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON o.customer_id = c.customer_id;
```

Nếu một cột là `BIGINT` và cột kia là `VARCHAR`, optimizer có thể không dùng index hiệu quả ở phía chuỗi. Hơn nữa, các giá trị như `'0012'` và `'12'` có thể được coi là bằng nhau theo so sánh số, dù khác nhau về mã định danh.

Cách tốt nhất là đồng bộ kiểu, signedness và ý nghĩa dữ liệu của hai cột liên kết. Ví dụ, nếu customer ID là số nguyên, cả hai bảng nên dùng cùng kiểu `BIGINT` và cùng quy tắc signed/unsigned. Nếu mã khách hàng có chữ hoặc số 0 ở đầu, cả hai bên nên dùng cùng kiểu chuỗi và collation phù hợp.

Nếu chưa thể đổi schema ngay, có thể chuẩn hóa ở tầng dữ liệu trung gian hoặc tạo cột chuẩn hóa có index sau khi kiểm tra và làm sạch dữ liệu. Tránh chuyển kiểu trực tiếp cột lớn trong điều kiện join trên mỗi truy vấn.

## 6. Khi nghiệp vụ thật sự cần so sánh số từ cột chuỗi

Có trường hợp hệ thống cũ lưu số dưới dạng chuỗi, ví dụ dữ liệu import từ CSV. Nếu nghiệp vụ cần so sánh theo giá trị số, trước tiên phải xác định quy tắc dữ liệu:

- Chuỗi có được phép có số 0 ở đầu không?
- Có dấu cộng/trừ không?
- Có khoảng trắng hoặc dấu phân cách hàng nghìn không?
- Có giá trị rỗng, chữ hoặc định dạng sai không?
- Có giới hạn miền số và overflow không?

Không nên chỉ viết `CAST(code AS UNSIGNED)` rồi xem mọi dữ liệu là hợp lệ. Ví dụ `'ABC'` có thể chuyển thành 0 kèm warning; dữ liệu sai có thể bị gộp vào cùng nhóm giá trị số.

### 6.1. Làm sạch và chuyển sang cột số

Giải pháp tốt về lâu dài là xác thực dữ liệu, thêm cột số có kiểu phù hợp và index cột đó. Ví dụ minh họa khi dữ liệu đã được kiểm tra hợp lệ:

```sql
ALTER TABLE external_codes
    ADD COLUMN numeric_code BIGINT UNSIGNED NULL;

-- Sau khi xác thực và backfill các giá trị hợp lệ:
CREATE INDEX idx_external_codes_numeric
    ON external_codes (numeric_code);
```

Ứng dụng có thể truy vấn:

```sql
SELECT code, description
FROM external_codes
WHERE numeric_code = 123;
```

Trong triển khai thực tế, cần thiết kế cách duy trì cột số khi thêm hoặc cập nhật dữ liệu: cập nhật đồng thời từ ứng dụng, dùng generated column nếu biểu thức chuyển đổi phù hợp, hoặc chạy quy trình đồng bộ có kiểm soát. Trước khi backfill, phải xử lý giá trị không hợp lệ, tràn số và quy tắc số 0 ở đầu.

### 6.2. Generated column hoặc functional index

MySQL hỗ trợ generated column và functional index trong các phiên bản phù hợp. Với MySQL 8.0.13 trở lên, có thể tạo functional index cho biểu thức nếu kiểu biểu thức và giới hạn index được hỗ trợ:

```sql
CREATE INDEX idx_code_numeric_expr
    ON external_codes ((CAST(code AS UNSIGNED)));
```

Một lựa chọn khác là generated column được đánh index:

```sql
ALTER TABLE external_codes
    ADD COLUMN code_as_number BIGINT UNSIGNED
        GENERATED ALWAYS AS (CAST(code AS UNSIGNED)) STORED,
    ADD INDEX idx_code_as_number (code_as_number);
```

Hai cách này chỉ phù hợp khi quy tắc chuyển đổi đã rõ và mọi giá trị trong cột nguồn đều được xử lý an toàn. Nếu cột có chuỗi sai định dạng, phép CAST có thể sinh warning hoặc kết quả không phù hợp nghiệp vụ. Functional index cũng phải khớp biểu thức truy vấn để optimizer nhận diện và tận dụng. Hãy kiểm tra tài liệu phiên bản, thử dữ liệu biên và xem `EXPLAIN`.

Đối với dữ liệu có thể thay đổi định dạng hoặc có nhiều loại mã, một cột số được chuẩn hóa và duy trì rõ ràng thường dễ kiểm soát hơn một biểu thức chuyển đổi ngầm trên cột chuỗi.

## 7. Kiểm tra bằng EXPLAIN và SHOW WARNINGS

Không nên suy luận index có được dùng chỉ từ cách viết câu SQL. Hãy quan sát kế hoạch thực thi.

### 7.1. So sánh hai điều kiện

Giả sử `external_codes.code` là `VARCHAR` và có primary key. So sánh:

```sql
EXPLAIN
SELECT code, description
FROM external_codes
WHERE code = '123';
```

Và:

```sql
EXPLAIN
SELECT code, description
FROM external_codes
WHERE code = 123;
```

Ở truy vấn đầu, optimizer có thể dùng primary key lookup vì so sánh chuỗi với chuỗi. Ở truy vấn thứ hai, việc chuyển kiểu từ chuỗi sang số có thể khiến index chuỗi không thể dùng cho lookup tương đương. Kế hoạch thực tế còn phụ thuộc kích thước bảng, thống kê, dữ liệu và phiên bản.

Các cột quan trọng trong kết quả EXPLAIN dạng truyền thống:

- `type`: kiểu truy cập như `const`, `ref`, `range` hoặc `ALL`.
- `possible_keys`: index optimizer có thể cân nhắc.
- `key`: index thực tế được chọn, nếu có.
- `rows`: số hàng ước lượng cần đọc.
- `filtered`: tỷ lệ hàng ước lượng còn lại sau điều kiện lọc.

`type = ALL` thường biểu thị table scan. Tuy nhiên, table scan không phải lúc nào cũng xấu: với bảng rất nhỏ hoặc truy vấn đọc phần lớn bảng, optimizer có thể chọn scan vì chi phí thấp hơn.

### 7.2. Dùng EXPLAIN ANALYZE khi cần số liệu thực tế

Trên các phiên bản hỗ trợ, có thể chạy:

```sql
EXPLAIN ANALYZE
SELECT code, description
FROM external_codes
WHERE code = '123';
```

`EXPLAIN ANALYZE` thực thi câu truy vấn và báo thời gian, số hàng thực tế cùng số vòng lặp của các iterator. Chỉ dùng với câu truy vấn có thể thực thi an toàn; không coi đây là lệnh chỉ đọc kế hoạch như `EXPLAIN` thông thường.

### 7.3. Xem warning do chuyển kiểu

Ngay sau câu lệnh có warning, chạy:

```sql
SHOW WARNINGS;
```

Warning có thể chỉ ra chuỗi không chuyển được hoàn toàn, giá trị bị cắt hoặc chuyển đổi không như mong đợi. Một số biểu thức so sánh có thể không phát warning theo cách bạn mong đợi, vì vậy việc không có warning không chứng minh dữ liệu đã hợp lệ.

## 8. Bind tham số JDBC đúng kiểu

Ứng dụng Java thường sử dụng prepared statement. Kiểu của tham số nên khớp với kiểu cột để giữ ngữ nghĩa rõ ràng và tránh chuyển kiểu ngoài ý muốn.

Ví dụ, nếu `code` là `VARCHAR(20)` (đoạn text block dưới đây dùng cú pháp Java 15 trở lên):

```java
String sql = """
    SELECT code, description
    FROM external_codes
    WHERE code = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, externalCode);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("code"));
        }
    }
}
```

Nếu cột là `BIGINT`, dùng `setLong`; nếu là `DECIMAL`, dùng `setBigDecimal`. Với `DATE` và `TIMESTAMP`, chọn kiểu JDBC tương ứng hoặc kiểu Java time được driver hỗ trợ.

Không dùng `setString` cho mọi tham số chỉ vì dữ liệu đầu vào đến từ HTTP hoặc JSON. Hãy parse và validate đầu vào thành kiểu Java phù hợp trước khi bind. Cũng không nối chuỗi đầu vào vào SQL; prepared statement vừa giúp bind kiểu dữ liệu rõ ràng vừa tránh SQL injection.

Nếu ứng dụng đang bind một số nguyên cho cột mã chuỗi, sửa ở tầng repository/service để truyền mã dưới dạng `String`. Nếu dữ liệu thực sự là số, hãy sửa schema và contract ứng dụng cho thống nhất thay vì chuyển đổi ở mỗi truy vấn.

## 9. Quy trình xử lý truy vấn bị mất index do chuyển kiểu

Khi một truy vấn chậm hoặc optimizer không dùng index như mong đợi, hãy thực hiện:

1. **Kiểm tra định nghĩa cột.** Dùng `SHOW CREATE TABLE` hoặc `INFORMATION_SCHEMA.COLUMNS` để xác nhận kiểu dữ liệu, signedness, character set và collation.
2. **Kiểm tra kiểu toán hạng.** Xác định cột được so sánh với số, chuỗi, temporal value hay biểu thức khác.
3. **Xác định ngữ nghĩa dữ liệu.** Đây là số lượng hay mã định danh? Số 0 ở đầu có ý nghĩa không? Có giá trị không hợp lệ không?
4. **Đọc kế hoạch.** Chạy `EXPLAIN`, kiểm tra `key`, `type`, `rows` và điều kiện lọc.
5. **Viết lại điều kiện.** Giữ nguyên cột được đánh index, chuyển hoặc bind giá trị phía đối diện theo kiểu đúng.
6. **Kiểm tra join.** Đảm bảo hai cột liên kết có kiểu, độ dài, signedness và collation tương thích.
7. **Kiểm thử kết quả.** Bao gồm chuỗi có số 0 ở đầu, khoảng trắng, ký tự không phải số, NULL, giá trị lớn và giá trị biên.
8. **Đo lại.** So sánh execution plan, thời gian và số hàng đọc trên dữ liệu đại diện.
9. **Chuẩn hóa dài hạn.** Nếu truy vấn liên tục phải chuyển kiểu, xem xét migration schema hoặc cột chuẩn hóa có index.

## 10. Những sai lầm thường gặp

| Cách viết hoặc giả định | Vấn đề | Cách xử lý |
|---|---|---|
| `WHERE varchar_code = 123` | So sánh kiểu hỗn hợp, có thể không dùng index chuỗi | Dùng `WHERE varchar_code = '123'` nếu đó là mã chuỗi |
| `WHERE CAST(code AS UNSIGNED) = 123` | Hàm áp dụng trên cột làm index thường khó được dùng | Chuẩn hóa dữ liệu hoặc tạo cột/functional index phù hợp |
| Join `BIGINT` với `VARCHAR` | Chuyển kiểu khi join, có thể mất index và thay đổi ngữ nghĩa | Đồng bộ kiểu dữ liệu hai cột |
| Lưu mã có số 0 đầu dưới kiểu số | Mất thông tin định danh | Dùng kiểu chuỗi |
| Dùng `FLOAT` cho tiền | Sai số dấu phẩy động | Dùng `DECIMAL` |
| Bind mọi tham số bằng `setString` | Kiểu tham số không phản ánh kiểu cột | Dùng `setLong`, `setBigDecimal`, `setString` đúng ngữ nghĩa |
| Chỉ nhìn `possible_keys` trong EXPLAIN | Index có thể được cân nhắc nhưng không được chọn | Kiểm tra cột `key` và access type |
| Coi table scan luôn là lỗi | Scan có thể tối ưu với bảng nhỏ hoặc truy vấn lấy nhiều hàng | Đánh giá số hàng, chi phí và workload |

## 11. Ghi nhớ

- MySQL tự chuyển kiểu trong nhiều biểu thức; kết quả phụ thuộc kiểu của cả hai toán hạng.
- Chuỗi so sánh với chuỗi theo collation; chuỗi so sánh với số thường được chuyển sang số.
- Nhiều chuỗi khác nhau có thể cùng giá trị số, vì vậy so sánh cột VARCHAR với hằng số số có thể làm index chuỗi không dùng được cho lookup.
- Tránh bọc cột có index trong CAST hoặc hàm khi có thể chuyển giá trị đầu vào thay thế.
- Hai cột dùng trong JOIN nên có kiểu dữ liệu, signedness và quy tắc collation tương thích.
- Mã định danh có số 0 ở đầu hoặc ký tự chữ phải được lưu và so sánh như chuỗi.
- Dùng EXPLAIN, EXPLAIN ANALYZE và SHOW WARNINGS để kiểm tra kế hoạch, chi phí thực tế và vấn đề chuyển kiểu.
- Trong Java, bind tham số bằng kiểu JDBC phù hợp với kiểu cột; không dùng một kiểu chuỗi cho tất cả dữ liệu.
- Nếu nghiệp vụ cần so sánh số từ dữ liệu chuỗi, hãy xác thực, chuẩn hóa và đánh index cho biểu thức hoặc cột chuẩn hóa một cách có chủ đích.

Khi kiểm soát được kiểu của cột, toán hạng và tham số, bạn vừa giữ được ngữ nghĩa dữ liệu chính xác vừa giúp optimizer có cơ hội sử dụng index phù hợp, từ đó giảm quét dữ liệu và cải thiện hiệu năng truy vấn MySQL.

