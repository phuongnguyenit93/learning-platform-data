# IS NULL, IS NOT NULL và phép so sánh NULL-safe <=>

Trong MySQL, `NULL` biểu thị giá trị chưa biết hoặc không có dữ liệu theo ngữ cảnh của cột. Nó không phải số `0`, chuỗi rỗng `''` hay một giá trị mặc định. Vì `NULL` mang nghĩa “không biết”, các phép so sánh thông thường như `=`, `<>`, `<` hoặc `>` không thể kết luận đúng/sai khi một toán hạng là `NULL`; kết quả thường là `NULL` (UNKNOWN). Để kiểm tra trạng thái thiếu dữ liệu, dùng `IS NULL` và `IS NOT NULL`. Khi cần so sánh hai giá trị mà vẫn coi hai `NULL` là bằng nhau, MySQL cung cấp toán tử NULL-safe equality `<=>`.

Các phép kiểm tra này xuất hiện thường xuyên trong truy vấn tìm kiếm, lọc dữ liệu tùy chọn, join, cập nhật có điều kiện, unique constraint và xử lý tham số từ ứng dụng. Hiểu đúng ngữ nghĩa `NULL` giúp tránh những lỗi khó nhận ra như truy vấn không trả hàng, `NOT IN` loại bỏ toàn bộ kết quả hoặc join bỏ sót bản ghi.

## 1. `NULL` có nghĩa gì?

`NULL` biểu diễn việc giá trị không hiện diện, chưa được biết hoặc không áp dụng trong ngữ cảnh dữ liệu. Ví dụ:

- `shipped_at` là `NULL` khi đơn hàng chưa được giao.
- `middle_name` là `NULL` khi khách hàng không cung cấp tên đệm.
- `cancelled_at` là `NULL` khi đơn hàng chưa bị hủy.
- `approved_by` là `NULL` khi một yêu cầu chưa được phê duyệt.

Không nên dùng `NULL` để biểu diễn mọi trạng thái nghiệp vụ. Nếu cần phân biệt “chưa biết”, “không áp dụng”, “đang chờ” và “đã từ chối”, có thể cần thêm cột trạng thái hoặc mô hình dữ liệu rõ ràng.

Phân biệt các giá trị sau:

| Giá trị | Ý nghĩa | Ví dụ kiểm tra |
|---|---|---|
| `NULL` | Không có giá trị/giá trị chưa biết | `value IS NULL` |
| `0` | Giá trị số bằng không | `value = 0` |
| `''` | Chuỗi rỗng có độ dài bằng 0 | `value = ''` |
| `' '` | Chuỗi chứa một khoảng trắng | `value = ' '` |
| `FALSE` | Giá trị logic sai, thường biểu diễn bằng 0 | `value = FALSE` |

Các giá trị này không thể thay thế cho nhau. Ví dụ, một số tiền bằng `0` có thể là khoản miễn phí hợp lệ; `NULL` có thể có nghĩa là chưa tính được số tiền. Nếu gộp chúng, báo cáo và quy tắc nghiệp vụ sẽ mất thông tin.

## 2. Logic ba giá trị: TRUE, FALSE và UNKNOWN

Trong logic SQL, biểu thức điều kiện có thể cho ba kết quả:

- `TRUE`: điều kiện đúng.
- `FALSE`: điều kiện sai.
- `UNKNOWN`: không thể xác định đúng hay sai, thường do có toán hạng `NULL`.

Ví dụ:

```sql
SELECT
    NULL = NULL AS null_equals_null,
    NULL = 10 AS null_equals_number,
    NULL <> 10 AS null_not_equals_number,
    10 = 10 AS ordinary_equal,
    10 = 20 AS ordinary_not_equal;
```

Ba biểu thức đầu trả về `NULL`; hai biểu thức cuối lần lượt trả về `1` và `0`. Đặc biệt, `NULL = NULL` không trả về `TRUE`. MySQL không thể kết luận hai giá trị chưa biết có giống nhau hay không.

### Vì sao `WHERE column = NULL` không tìm được hàng?

`WHERE` chỉ giữ những hàng mà điều kiện là `TRUE`. Hàng có điều kiện `FALSE` hoặc `UNKNOWN` đều bị loại. Vì `column = NULL` cho kết quả `UNKNOWN`, câu truy vấn sau không tìm được các hàng có cột `shipped_at` là `NULL`:

```sql
SELECT id, shipped_at
FROM orders
WHERE shipped_at = NULL;
```

Đây là cách viết sai nếu mục đích là tìm giá trị thiếu. Hãy dùng:

```sql
SELECT id, shipped_at
FROM orders
WHERE shipped_at IS NULL;
```

Tương tự, `shipped_at <> NULL` cũng không tìm được các hàng khác NULL. Dùng `IS NOT NULL` để kiểm tra cột có giá trị.

### Một số bảng chân trị cần nhớ

| Biểu thức | Kết quả |
|---|---|
| `NULL = NULL` | `UNKNOWN` (`NULL`) |
| `NULL = 1` | `UNKNOWN` (`NULL`) |
| `NULL <> 1` | `UNKNOWN` (`NULL`) |
| `NOT (NULL = 1)` | `UNKNOWN` (`NULL`) |
| `NULL IS NULL` | `TRUE` |
| `NULL IS NOT NULL` | `FALSE` |
| `NULL <=> NULL` | `TRUE` |
| `NULL <=> 1` | `FALSE` |

`NOT` không biến UNKNOWN thành TRUE. Đây là lý do những biểu thức phủ định có liên quan đến `NULL` cần được xem xét cẩn thận.

## 3. Dùng `IS NULL` để tìm giá trị thiếu

Cú pháp:

```sql
expression IS NULL
```

Toán tử trả về `1` nếu biểu thức là `NULL`, ngược lại trả về `0`. Ví dụ với bảng đơn hàng:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    shipped_at DATETIME NULL,
    cancelled_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY idx_orders_shipped_at (shipped_at)
) ENGINE=InnoDB;
```

Tìm các đơn chưa được giao:

```sql
SELECT id, customer_id, status
FROM orders
WHERE shipped_at IS NULL;
```

Tìm các đơn chưa bị hủy:

```sql
SELECT id, customer_id, status
FROM orders
WHERE cancelled_at IS NULL;
```

Kiểm tra nhiều cột cùng lúc:

```sql
SELECT id, customer_id
FROM orders
WHERE shipped_at IS NULL
  AND cancelled_at IS NULL;
```

Điều kiện trên chỉ trả về các đơn chưa có thời điểm giao và chưa có thời điểm hủy. Hãy chắc chắn hai cột này có ý nghĩa nghiệp vụ như vậy; nếu trạng thái đơn hàng đã là nguồn sự thật duy nhất, có thể cần tránh lưu các trạng thái mâu thuẫn giữa `status`, `shipped_at` và `cancelled_at`.

## 4. Dùng `IS NOT NULL` để tìm giá trị đã có

Cú pháp:

```sql
expression IS NOT NULL
```

Toán tử trả về `1` nếu biểu thức không phải `NULL`. Ví dụ, tìm đơn đã có thời điểm giao:

```sql
SELECT id, customer_id, shipped_at
FROM orders
WHERE shipped_at IS NOT NULL;
```

Kết hợp với điều kiện khác:

```sql
SELECT id, customer_id, shipped_at
FROM orders
WHERE shipped_at IS NOT NULL
  AND shipped_at >= '2026-01-01 00:00:00'
ORDER BY shipped_at;
```

`IS NOT NULL` chỉ kiểm tra sự hiện diện của giá trị. Nó không xác nhận ngày giờ hợp lệ theo nghiệp vụ, không xác nhận dữ liệu đã được đồng bộ và cũng không bảo đảm giá trị lớn hơn một mốc cụ thể.

## 5. Toán tử NULL-safe equality `<=>`

MySQL có toán tử `<=>` để so sánh hai biểu thức theo cách an toàn với `NULL`:

```sql
left_expression <=> right_expression
```

Quy tắc:

- Nếu cả hai vế là `NULL`, kết quả là `1`.
- Nếu chỉ một vế là `NULL`, kết quả là `0`.
- Nếu cả hai vế không phải `NULL`, phép so sánh hoạt động tương tự `=`.

Ví dụ:

```sql
SELECT
    NULL <=> NULL AS both_null,
    NULL <=> 10 AS null_and_number,
    10 <=> NULL AS number_and_null,
    10 <=> 10 AS same_number,
    10 <=> 20 AS different_number;
```

Kết quả lần lượt là `1`, `0`, `0`, `1`, `0`. Không có kết quả UNKNOWN từ việc một trong hai toán hạng là `NULL`.

### So sánh với `=` và `IS NULL`

| Biểu thức | Khi hai vế đều NULL | Khi một vế NULL, một vế có giá trị |
|---|---:|---:|
| `a = b` | `NULL` | `NULL` |
| `a <=> b` | `1` | `0` |
| `a IS NULL` | `1` nếu `a` NULL | `0` nếu `a` không NULL |

`a <=> NULL` tương đương kiểm tra `a IS NULL`, nhưng `IS NULL` diễn đạt ý định rõ hơn khi kiểm tra một cột với literal NULL. `<=>` hữu ích khi cả hai phía đều là biểu thức hoặc tham số có thể NULL.

### Dùng `<=>` để so sánh tham số tùy chọn

Giả sử ứng dụng tìm đơn hàng theo mã vận chuyển có thể chưa được cấp. Nếu tham số `tracking_code` là NULL, yêu cầu có thể là tìm các hàng có `tracking_code` cũng NULL. Dùng:

```sql
SELECT id, status, tracking_code
FROM shipments
WHERE tracking_code <=> ?;
```

Prepared statement bind một mã vận chuyển hoặc bind SQL NULL. Khi tham số là NULL, điều kiện tìm các hàng NULL; khi tham số có giá trị, điều kiện so sánh bằng thông thường.

Nếu dùng `tracking_code = ?` và bind NULL, kết quả điều kiện là UNKNOWN và không hàng nào được chọn. Vì vậy hãy chọn toán tử theo đúng yêu cầu nghiệp vụ.

## 6. Dùng NULL-safe equality trong JOIN

Phép nối thông thường:

```sql
SELECT a.id, b.id
FROM source_a AS a
JOIN source_b AS b
  ON a.external_ref = b.external_ref;
```

Nếu cả `a.external_ref` và `b.external_ref` đều NULL, điều kiện `=` trả về UNKNOWN và hai hàng không khớp. Nếu nghiệp vụ muốn coi hai giá trị NULL là cùng một trạng thái và nối chúng với nhau, có thể dùng `<=>`:

```sql
SELECT a.id, b.id
FROM source_a AS a
JOIN source_b AS b
  ON a.external_ref <=> b.external_ref;
```

Tuy nhiên, phải cẩn thận: nếu bảng A có 5 hàng NULL và bảng B có 8 hàng NULL, các hàng NULL có thể tạo ra 40 cặp khớp. Đây là phép nối nhiều-nhiều hợp lệ theo toán tử, nhưng thường không phải điều mong muốn đối với khóa ngoại hoặc mã tham chiếu.

Không dùng `<=>` cho khóa định danh nếu NULL thực sự có nghĩa là “không biết đối tượng nào”. Trong trường hợp đó, các giá trị NULL không nên được xem là cùng một đối tượng. Hãy xác định ý nghĩa nghiệp vụ trước khi chọn điều kiện JOIN.

## 7. Dùng `<=>` trong cập nhật có điều kiện

Một số thao tác cần cập nhật hàng chỉ khi giá trị hiện tại vẫn bằng giá trị mà ứng dụng đã đọc. Nếu cột có thể NULL, phép `=` thông thường không thể so sánh trạng thái NULL một cách an toàn.

Ví dụ cập nhật trạng thái ghi nhận giao hàng nếu `shipped_at` vẫn bằng giá trị cũ mà ứng dụng quan sát:

```sql
UPDATE orders
SET shipped_at = '2026-02-10 09:30:00'
WHERE id = 1001
  AND shipped_at <=> NULL;
```

Ở ví dụ trên, có thể viết rõ hơn bằng `shipped_at IS NULL` vì giá trị kỳ vọng cũ là NULL. Nhưng khi giá trị cũ là một tham số tùy chọn:

```sql
UPDATE orders
SET status = ?
WHERE id = ?
  AND status <=> ?;
```

Toán tử cho phép điều kiện khớp cả trường hợp giá trị cũ là NULL. Ứng dụng cần kiểm tra số hàng bị ảnh hưởng để biết cập nhật có thành công theo điều kiện kỳ vọng hay không. Nếu không có hàng nào bị ảnh hưởng, dữ liệu có thể đã được transaction khác cập nhật hoặc không còn khớp điều kiện.

## 8. `NULL` trong UNIQUE index và ràng buộc

MySQL cho phép nhiều hàng có giá trị NULL trong một unique index đơn cột. Ví dụ:

```sql
CREATE TABLE customer_contacts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customer_contacts_email (email)
) ENGINE=InnoDB;

INSERT INTO customer_contacts (email)
VALUES (NULL), (NULL), ('an@example.test');
```

Các hàng NULL không bị xem là giá trị trùng nhau bởi unique index; vì thế có thể tồn tại nhiều hàng không có email. Hai hàng có cùng email không NULL sẽ vi phạm unique constraint.

Với unique index nhiều cột, nếu một hoặc nhiều thành phần khóa là NULL, MySQL có thể cho phép nhiều hàng có cùng các giá trị còn lại. Ví dụ `UNIQUE (tenant_id, external_ref)` không nhất thiết bảo đảm mỗi tenant chỉ có một hàng `external_ref IS NULL`. Nếu nghiệp vụ cần một quy tắc khác, phải mô hình hóa và kiểm tra riêng.

Nếu email là bắt buộc và phải duy nhất, hãy khai báo `NOT NULL` cùng `UNIQUE`. Nếu email tùy chọn, cho phép NULL có thể phù hợp. Đừng thay NULL bằng chuỗi rỗng chỉ để né quy tắc unique; chuỗi rỗng là một giá trị thực và chỉ có thể xuất hiện một lần trong unique index đơn cột.

## 9. NULL trong hàm aggregate, DISTINCT và GROUP BY

Các hàm aggregate thường bỏ qua NULL ở đối số:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(shipped_at) AS rows_with_shipped_at,
    COUNT(*) - COUNT(shipped_at) AS rows_without_shipped_at
FROM orders;
```

- `COUNT(*)` đếm tất cả hàng.
- `COUNT(shipped_at)` chỉ đếm hàng mà `shipped_at` không NULL.
- `SUM`, `AVG`, `MIN` và `MAX` thường bỏ qua giá trị NULL; nếu không có giá trị khác NULL, kết quả có thể là NULL.

`GROUP BY` gom các giá trị NULL vào cùng một nhóm:

```sql
SELECT shipped_at, COUNT(*) AS order_count
FROM orders
GROUP BY shipped_at;
```

Kết quả có thể có một nhóm `shipped_at = NULL`. `SELECT DISTINCT` cũng chỉ giữ một đại diện cho các giá trị NULL trùng nhau trong tập kết quả. Trong khi đó, `COUNT(DISTINCT shipped_at)` không đếm NULL.

Nếu cần hiển thị giá trị thay thế cho NULL, dùng `COALESCE()` hoặc `IFNULL()` ở danh sách SELECT:

```sql
SELECT
    id,
    CASE
        WHEN shipped_at IS NULL THEN 'Chưa giao'
        ELSE DATE_FORMAT(shipped_at, '%Y-%m-%d %H:%i:%s')
    END AS shipping_status
FROM orders;
```

Ví dụ dùng `CASE` để trả về chuỗi mô tả thống nhất: khi `shipped_at` NULL thì hiển thị `Chưa giao`, còn khi có giá trị thì định dạng ngày giờ thành chuỗi. Nếu cần giữ kiểu `DATETIME` cho phép tính tiếp theo, hãy trả về NULL hoặc một giá trị ngày giờ khác cùng kiểu thay vì thay bằng chuỗi mô tả.

## 10. Cạm bẫy `NOT IN` khi tập con chứa NULL

Một lỗi phổ biến là dùng `NOT IN` với subquery có thể trả về NULL. Ví dụ:

```sql
SELECT c.id
FROM customers AS c
WHERE c.id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

Nếu `orders.customer_id` chứa một NULL, biểu thức `c.id NOT IN (...)` có thể trở thành UNKNOWN cho các giá trị không khớp khác, khiến truy vấn không trả về những khách hàng mong muốn. Điều này xảy ra do phép so sánh với NULL trong danh sách tạo kết quả UNKNOWN.

Một cách an toàn và thường dễ đọc hơn là `NOT EXISTS`:

```sql
SELECT c.id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
```

Nếu `customer_id` là khóa ngoại `NOT NULL`, `NOT IN` không gặp đúng vấn đề NULL này; tuy nhiên `NOT EXISTS` diễn đạt trực tiếp ý nghĩa “không có hàng liên quan” và tránh phụ thuộc dữ liệu subquery có NULL hay không.

## 11. NULL và thứ tự sắp xếp

Trong MySQL, khi sắp xếp tăng dần (`ORDER BY column ASC`), NULL thường đứng trước các giá trị không NULL; khi sắp xếp giảm dần (`DESC`), NULL đứng sau. Nếu cần thứ tự khác, có thể sắp xếp tường minh bằng biểu thức:

```sql
SELECT id, shipped_at
FROM orders
ORDER BY (shipped_at IS NULL) ASC, shipped_at ASC;
```

Biểu thức `(shipped_at IS NULL)` trả về `0` cho hàng có giá trị và `1` cho hàng NULL, nên các hàng có thời điểm giao được xếp trước, hàng chưa giao ở cuối. Nếu truy vấn này quan trọng về hiệu năng, hãy kiểm tra `EXPLAIN`; biểu thức trong `ORDER BY` có thể cần chiến lược index riêng tùy workload.

## 12. NULL, index và kế hoạch thực thi

Index B-tree của MySQL lưu thông tin về giá trị NULL, vì vậy điều kiện `IS NULL` trên cột được index có thể sử dụng index. Ví dụ:

```sql
EXPLAIN
SELECT id, customer_id
FROM orders
WHERE shipped_at IS NULL;
```

Điều kiện `IS NOT NULL` cũng có thể được thực hiện bằng range trên index trong một số trường hợp. Tuy nhiên, nếu phần lớn hàng đều không NULL, optimizer có thể thấy table scan rẻ hơn. Không nên kết luận một toán tử luôn dùng hoặc luôn bỏ qua index; hãy kiểm tra kế hoạch thực thi và độ chọn lọc trên dữ liệu gần thực tế.

`<=>` có thể dùng trong điều kiện tìm kiếm tương đương khi cột được index, nhưng kế hoạch còn phụ thuộc kiểu dữ liệu, biểu thức và giá trị tham số. Kiểm tra bằng `EXPLAIN` hoặc `EXPLAIN ANALYZE` phù hợp với phiên bản và môi trường. Tránh bọc cột bằng `COALESCE()` hoặc hàm khác trong `WHERE` nếu muốn optimizer tận dụng index thông thường:

```sql
-- Rõ ràng, có thể dùng index trên shipped_at
SELECT id
FROM orders
WHERE shipped_at IS NULL;

-- Biểu thức trên cột có thể làm mất khả năng dùng index thông thường
SELECT id
FROM orders
WHERE COALESCE(shipped_at, '1000-01-01 00:00:00') = '1000-01-01 00:00:00';
```

Truy vấn thứ hai còn có nguy cơ nhầm một giá trị sentinel với dữ liệu thật. Dùng `IS NULL` trực tiếp thường rõ ràng và dễ tối ưu hơn.

## 13. Bind NULL từ ứng dụng Java/JDBC

Khi dùng prepared statement, không truyền chuỗi `'NULL'` để biểu diễn SQL NULL. Chuỗi đó là bốn ký tự `N`, `U`, `L`, `L`. Hãy dùng API bind NULL đúng kiểu dữ liệu.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public class ShipmentRepository {
    private final DataSource dataSource;

    public ShipmentRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int findShipmentsByOptionalTrackingCode(String trackingCode)
            throws SQLException {
        String sql = "SELECT id FROM shipments WHERE tracking_code <=> ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            if (trackingCode == null) {
                statement.setNull(1, Types.VARCHAR);
            } else {
                statement.setString(1, trackingCode);
            }

            int count = 0;
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    count++;
                }
            }
            return count;
        }
    }
}
```

Ví dụ này dùng `<=>` vì tham số có thể NULL và yêu cầu NULL khớp với NULL. Nếu yêu cầu là “khi tham số NULL thì bỏ qua bộ lọc”, logic phải được viết khác, ví dụ:

```sql
SELECT id
FROM shipments
WHERE (? IS NULL OR tracking_code = ?);
```

Trong trường hợp đó, ứng dụng bind cùng tham số hai lần. Hãy phân biệt rõ ba yêu cầu khác nhau:

1. Tham số NULL phải tìm hàng có cột NULL: dùng `column <=> ?`.
2. Tham số NULL nghĩa là không lọc theo cột: dùng điều kiện tùy chọn như `(? IS NULL OR column = ?)` hoặc xây dựng truy vấn theo allowlist.
3. Tham số NULL không hợp lệ: kiểm tra ở ứng dụng và từ chối trước khi chạy SQL.

Đừng chọn `<=>` chỉ vì nó “an toàn với NULL”; nó thay đổi ý nghĩa nghiệp vụ của phép so sánh.

## 14. Chọn `NOT NULL` hay cho phép NULL khi thiết kế schema

Một cột nên cho phép NULL khi việc không có giá trị là một trạng thái hợp lệ và có ý nghĩa. Nếu giá trị bắt buộc để xác định một hàng hoặc thực hiện nghiệp vụ, hãy khai báo `NOT NULL`.

Ví dụ:

```sql
CREATE TABLE payment_attempts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    provider_reference VARCHAR(100) NULL,
    settled_at DATETIME NULL,
    amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_payment_attempts_provider_reference (provider_reference)
) ENGINE=InnoDB;
```

`provider_reference` có thể NULL trước khi nhà cung cấp trả mã tham chiếu; `settled_at` có thể NULL khi thanh toán chưa được quyết toán; `amount` là bắt buộc nên dùng `NOT NULL`. Hãy ghi rõ ý nghĩa NULL trong tài liệu nghiệp vụ và kiểm tra các trạng thái liên quan bằng constraint hoặc logic transaction khi cần.

Lưu ý rằng `DEFAULT` không có nghĩa là explicit NULL sẽ tự chuyển thành giá trị mặc định. Nếu một cột nullable có default, bỏ cột khỏi câu INSERT hoặc dùng từ khóa `DEFAULT` sẽ áp dụng default; truyền `NULL` tường minh sẽ lưu NULL. Đây là khác biệt quan trọng khi ứng dụng bind tham số.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `= NULL` hoặc `<> NULL` | Điều kiện thành UNKNOWN, không lọc được như mong muốn | Dùng `IS NULL` hoặc `IS NOT NULL`. |
| Nghĩ NULL bằng 0 hoặc chuỗi rỗng | Báo cáo và kiểm tra dữ liệu sai | Giữ ý nghĩa riêng cho NULL, 0 và `''`. |
| Dùng `=` khi tham số có thể NULL | Không khớp hàng có cột NULL | Dùng `<=>` nếu NULL phải khớp NULL. |
| Dùng `<=>` trong JOIN khóa tùy chọn mà không đánh giá số hàng NULL | Có thể tạo nhiều cặp khớp NULL | Xác định NULL có đại diện cùng một thực thể hay không. |
| Dùng `NOT IN` với subquery có NULL | Truy vấn có thể trả thiếu hoặc không trả hàng | Dùng `NOT EXISTS` hoặc loại NULL có chủ đích trong subquery. |
| Nghĩ unique index chỉ cho phép một NULL | Hiểu sai hành vi constraint | MySQL cho phép nhiều NULL trong unique index; dùng `NOT NULL` nếu cần bắt buộc. |
| Dùng `COALESCE()` trên cột trong WHERE | Có thể mất khả năng sử dụng index và nhầm sentinel | Dùng `IS NULL`/`IS NOT NULL` trực tiếp. |
| Bind chuỗi `'NULL'` | Lưu chữ NULL thay vì SQL NULL | Dùng `PreparedStatement.setNull()`. |
| Dùng NULL cho nhiều trạng thái nghiệp vụ | Không phân biệt được lý do thiếu dữ liệu | Thêm trạng thái hoặc mô hình dữ liệu rõ ràng. |

## 16. Bài tập thực hành

### Bài tập A — Quan sát logic ba giá trị

1. Chạy `SELECT NULL = NULL`, `NULL <> 1`, `NOT (NULL = 1)`.
2. So sánh với `NULL IS NULL`, `NULL IS NOT NULL` và `NULL <=> NULL`.
3. Ghi lại kết quả và giải thích vì sao WHERE loại hàng có điều kiện UNKNOWN.

### Bài tập B — Lọc đơn hàng theo NULL

1. Tạo bảng `orders` với `shipped_at` và `cancelled_at` nullable.
2. Chèn hàng có cả hai cột NULL, chỉ một cột NULL và cả hai có giá trị.
3. Viết truy vấn tìm đơn chưa giao, đã giao và chưa giao cũng chưa hủy.
4. So sánh kết quả của `= NULL` với `IS NULL`.

### Bài tập C — So sánh NULL-safe

1. Tạo bảng có cột `external_ref` nullable.
2. Dùng `=` và `<=>` để so sánh hai hàng NULL.
3. Dùng `<=> ?` trong prepared statement với tham số có giá trị và tham số NULL.
4. Thử JOIN hai bảng có nhiều hàng NULL và đếm số cặp được tạo.
5. Giải thích khi nào không nên dùng NULL-safe equality trong JOIN.

### Bài tập D — Unique index và aggregate

1. Tạo unique index trên một cột nullable.
2. Chèn nhiều hàng NULL và thử chèn giá trị không NULL trùng nhau.
3. So sánh `COUNT(*)`, `COUNT(column)` và `COUNT(DISTINCT column)`.
4. Dùng `GROUP BY column` để quan sát nhóm NULL.
5. Đề xuất schema nếu nghiệp vụ yêu cầu giá trị bắt buộc duy nhất.

### Bài tập E — Tối ưu và xử lý NULL từ Java

1. Tạo index trên cột nullable.
2. Chạy `EXPLAIN` với `IS NULL`, `IS NOT NULL` và `<=> ?`.
3. So sánh với điều kiện dùng `COALESCE()`.
4. Viết JDBC method bind NULL bằng `setNull()` và đọc kết quả.
5. Kiểm tra số hàng trả về khi tham số NULL theo từng yêu cầu nghiệp vụ.

Bạn hoàn thành bài khi có thể giải thích logic ba giá trị, chọn đúng `IS NULL`/`IS NOT NULL`/`<=>`, dự đoán ảnh hưởng tới JOIN và unique index, tránh lỗi `NOT IN`, và truyền SQL NULL đúng cách từ ứng dụng.

## 17. Nguyên tắc cần ghi nhớ

- `NULL` không bằng `0`, `FALSE` hoặc chuỗi rỗng; nó biểu diễn trạng thái thiếu hoặc chưa biết.
- Phép so sánh thông thường với NULL trả về UNKNOWN; `WHERE` chỉ giữ hàng có điều kiện TRUE.
- Dùng `IS NULL` để tìm giá trị NULL và `IS NOT NULL` để tìm giá trị hiện diện.
- `<=>` là phép so sánh bằng an toàn với NULL: hai NULL được xem là bằng nhau, một NULL và một giá trị khác được xem là khác nhau.
- Chỉ dùng `<=>` trong JOIN khi nghiệp vụ thực sự muốn NULL khớp NULL; nếu không, có thể phát sinh nhiều cặp khớp ngoài ý muốn.
- MySQL cho phép nhiều NULL trong unique index; dùng `NOT NULL` nếu cột bắt buộc phải có giá trị.
- Aggregate bỏ qua NULL ở đối số; `COUNT(*)` vẫn đếm mọi hàng.
- `NOT IN` dễ bị ảnh hưởng bởi NULL trong tập con; `NOT EXISTS` thường là lựa chọn rõ ràng hơn.
- Dùng `EXPLAIN` để xác nhận khả năng tận dụng index và bind SQL NULL bằng API đúng kiểu của driver.

Khi hiểu đúng `NULL`, bạn có thể viết điều kiện lọc chính xác, so sánh tham số tùy chọn an toàn, thiết kế constraint phù hợp và tránh các lỗi truy vấn do logic ba giá trị trong MySQL.
