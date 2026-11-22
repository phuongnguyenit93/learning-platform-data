# GROUP_CONCAT, thứ tự nối và giới hạn group_concat_max_len

## Mục tiêu

Sau bài này, bạn có thể:

- Dùng `GROUP_CONCAT()` để gom nhiều giá trị của các hàng thành một chuỗi trong mỗi nhóm.
- Sắp xếp giá trị ngay bên trong hàm bằng `ORDER BY` và chọn dấu phân tách bằng `SEPARATOR`.
- Kết hợp `DISTINCT`, `CONCAT_WS()` và `COALESCE()` để xử lý dữ liệu trùng hoặc có `NULL`.
- Phân biệt thứ tự nối bên trong `GROUP_CONCAT()` với thứ tự các nhóm ở truy vấn ngoài.
- Cấu hình `group_concat_max_len` theo session/global và phát hiện kết quả bị cắt.
- Chọn cách biểu diễn dữ liệu tổng hợp phù hợp, tránh dùng chuỗi nối như một định dạng trao đổi không an toàn.
- Đánh giá chi phí của `DISTINCT`, sắp xếp và nối chuỗi trên nhóm dữ liệu lớn.

## 1. GROUP_CONCAT dùng để làm gì?

`GROUP_CONCAT()` là hàm tổng hợp của MySQL. Hàm lấy giá trị biểu thức từ nhiều hàng trong cùng một nhóm rồi nối chúng thành một chuỗi. Nó thường được dùng để tạo danh sách tên, nhãn, mã sản phẩm hoặc trạng thái liên quan đến một đối tượng cha.

Ví dụ, một khách hàng có nhiều đơn hàng. Thay vì trả một hàng cho mỗi đơn, báo cáo có thể trả một hàng cho mỗi khách hàng và nối các mã đơn thành danh sách:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(order_id) AS order_ids
FROM orders
GROUP BY customer_id;
```

Kết quả minh họa:

| customer_id | order_ids |
|---:|---|
| 101 | `5001,5002,5008` |
| 102 | `5003,5004` |
| 103 | `5005` |

Mặc định, các giá trị được phân tách bằng dấu phẩy. Không nên giả định thứ tự các phần tử khi không khai báo `ORDER BY` bên trong hàm.

### 1.1. Cú pháp

```sql
GROUP_CONCAT(
    [DISTINCT] expr
    [ORDER BY {col_name | expr} [ASC | DESC] [, ...]]
    [SEPARATOR str_val]
)
```

- `expr`: biểu thức cần nối cho từng hàng.
- `DISTINCT`: loại bỏ các giá trị trùng trước khi nối.
- `ORDER BY`: quy định thứ tự các giá trị bên trong chuỗi kết quả.
- `SEPARATOR`: chọn chuỗi phân tách; mặc định là dấu phẩy `,`.

`GROUP_CONCAT()` là hàm tổng hợp nên thường xuất hiện trong `SELECT` cùng `GROUP BY`, nhưng cũng có thể dùng cho toàn bộ tập kết quả khi không có `GROUP BY`.

### 1.2. Nối toàn bộ tập kết quả thành một chuỗi

Không có `GROUP BY`, hàm tạo một kết quả tổng hợp cho toàn bộ các hàng phù hợp:

```sql
SELECT GROUP_CONCAT(order_id ORDER BY order_id) AS all_order_ids
FROM orders;
```

Truy vấn trả về một hàng. Nếu không có giá trị không-NULL để nối, kết quả là `NULL`.

## 2. Sắp xếp bên trong GROUP_CONCAT

### 2.1. ORDER BY bên trong hàm quyết định thứ tự nối

Giả sử bảng `order_items` lưu các mặt hàng của đơn hàng:

```sql
CREATE TABLE order_items (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_order_line (order_id, line_no)
) ENGINE = InnoDB;
```

Muốn nối tên sản phẩm theo thứ tự dòng hàng:

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        product_name
        ORDER BY line_no ASC, item_id ASC
        SEPARATOR ' | '
    ) AS product_list
FROM order_items
GROUP BY order_id;
```

`ORDER BY` nằm bên trong `GROUP_CONCAT()` nên quyết định thứ tự các tên sản phẩm trong chuỗi. `item_id` là tie-breaker để thứ tự ổn định khi hai dòng có cùng `line_no`.

### 2.2. ORDER BY bên ngoài không sắp xếp phần tử trong chuỗi

Hai vị trí `ORDER BY` có vai trò khác nhau:

```sql
SELECT
    order_id,
    GROUP_CONCAT(product_name SEPARATOR ', ') AS product_list
FROM order_items
GROUP BY order_id
ORDER BY order_id DESC;
```

`ORDER BY order_id DESC` sắp xếp các hàng kết quả (các nhóm đơn hàng). Nó không xác định thứ tự tên sản phẩm bên trong `product_list`.

Muốn kiểm soát cả hai cấp:

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        product_name
        ORDER BY line_no, item_id
        SEPARATOR ', '
    ) AS product_list
FROM order_items
GROUP BY order_id
ORDER BY order_id DESC;
```

### 2.3. Sắp xếp theo biểu thức

Có thể sắp xếp theo trạng thái ưu tiên, thời điểm hoặc biểu thức tính toán:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR '; '
    ) AS recent_orders
FROM orders
GROUP BY customer_id;
```

Nếu nhiều hàng có cùng giá trị sắp xếp, thêm cột duy nhất để có thứ tự xác định. Không dựa vào thứ tự vật lý của hàng hoặc thứ tự index khi không có `ORDER BY`.

## 3. Chọn dấu phân tách với SEPARATOR

### 3.1. Dùng dấu phân tách mặc định

```sql
SELECT
    customer_id,
    GROUP_CONCAT(order_id) AS order_ids
FROM orders
GROUP BY customer_id;
```

Kết quả mặc định có dạng `5001,5002,5008`.

### 3.2. Dùng dấu phân tách tùy chỉnh

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR ' / '
    ) AS order_ids
FROM orders
GROUP BY customer_id;
```

`SEPARATOR` nhận một chuỗi cố định. Có thể dùng dấu phẩy kèm khoảng trắng, dấu chấm phẩy, dấu gạch đứng hoặc ký tự khác phù hợp với mục đích hiển thị.

### 3.3. SEPARATOR rỗng

Nếu muốn nối liền các giá trị:

```sql
SELECT GROUP_CONCAT(product_code ORDER BY product_code SEPARATOR '')
       AS combined_codes
FROM products;
```

Không có ký tự phân tách, ranh giới giữa các giá trị có thể không còn rõ ràng. Chỉ dùng khi định dạng đầu ra có quy tắc độ dài hoặc cấu trúc khác giúp tách được từng phần tử.

### 3.4. Dữ liệu có chứa chính dấu phân tách

Nếu tên sản phẩm có thể chứa `,` mà kết quả cũng dùng dấu phẩy, người đọc hoặc chương trình phía client không thể chắc chắn dấu phẩy nào là ranh giới giữa hai phần tử. Ví dụ `Tea, green, Coffee` có thể là ba mục hoặc hai mục tùy dữ liệu gốc.

Vì vậy:

- Dùng `GROUP_CONCAT()` cho chuỗi trình bày khi định dạng đã được kiểm soát.
- Nếu phải phân tích lại, cần một quy tắc escape/unescape rõ ràng và được kiểm thử.
- Nếu cần trao đổi dữ liệu có cấu trúc, cân nhắc JSON thay vì tự tạo định dạng phân tách bằng dấu phẩy.

`GROUP_CONCAT()` không tự escape separator xuất hiện trong dữ liệu. Đừng coi chuỗi nối là CSV hợp lệ hoặc định dạng serialization an toàn nếu chưa xử lý quoting, escaping và encoding.

## 4. DISTINCT và loại bỏ giá trị trùng

### 4.1. DISTINCT trong GROUP_CONCAT

Khi một truy vấn JOIN tạo ra nhiều hàng lặp, `DISTINCT` có thể loại bỏ các giá trị lặp trước khi nối:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        DISTINCT status
        ORDER BY status
        SEPARATOR ', '
    ) AS statuses
FROM orders
GROUP BY customer_id;
```

Mỗi trạng thái chỉ xuất hiện một lần trong danh sách của khách hàng.

### 4.2. DISTINCT chịu ảnh hưởng của collation

Với biểu thức chuỗi, việc xác định hai giá trị có trùng nhau hay không chịu ảnh hưởng của charset/collation. Nếu collation không phân biệt hoa thường, `Paid` và `PAID` có thể được xem là cùng một giá trị khi áp dụng `DISTINCT`.

Ví dụ kiểm tra:

```sql
SELECT
    GROUP_CONCAT(DISTINCT status ORDER BY status) AS distinct_statuses
FROM orders;
```

Nếu cần phân biệt hoa thường, hãy chọn collation phù hợp hoặc chuyển biểu thức sang collation mong muốn một cách tường minh. Đừng cho rằng `DISTINCT` luôn so sánh byte tuyệt đối.

### 4.3. DISTINCT có thể che giấu vấn đề JOIN

Giả sử một truy vấn JOIN bảng đơn hàng với bảng lịch sử trạng thái, một đơn hàng có nhiều dòng lịch sử. `GROUP_CONCAT(product_name)` có thể lặp sản phẩm do quan hệ JOIN làm nhân số hàng.

Thêm `DISTINCT` có thể làm chuỗi trông đúng hơn, nhưng cũng có thể che giấu lỗi cardinality hoặc loại bỏ các mục lặp có ý nghĩa nghiệp vụ. Trước khi dùng, hãy kiểm tra số hàng sau JOIN và xác định vì sao có trùng. Nếu cần, tổng hợp ở subquery riêng theo đúng khóa rồi mới JOIN kết quả.

Ví dụ cấu trúc tổng hợp trước:

```sql
SELECT
    oi.order_id,
    GROUP_CONCAT(
        oi.product_name
        ORDER BY oi.line_no, oi.item_id
        SEPARATOR ', '
    ) AS products
FROM order_items AS oi
GROUP BY oi.order_id;
```

Truy vấn này tạo đúng một hàng cho mỗi `order_id` trước khi kết hợp với các bảng có quan hệ một-nhiều khác.

## 5. Nối nhiều cột trong mỗi hàng

`GROUP_CONCAT()` nhận một biểu thức. Khi muốn đưa nhiều cột của cùng một hàng vào một phần tử, hãy tạo biểu thức bằng `CONCAT()` hoặc `CONCAT_WS()`.

### 5.1. Dùng CONCAT

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        CONCAT(product_name, ' x ', quantity)
        ORDER BY line_no, item_id
        SEPARATOR '; '
    ) AS item_summary
FROM order_items
GROUP BY order_id;
```

Mỗi dòng hàng trở thành một đoạn như `Keyboard x 2`; các đoạn được nối bằng `; `.

Lưu ý: `CONCAT()` trả về `NULL` nếu một trong các đối số là `NULL`. Vì `GROUP_CONCAT()` bỏ qua biểu thức có giá trị `NULL`, cả phần tử có thể biến mất khỏi kết quả.

### 5.2. Dùng CONCAT_WS để xử lý NULL

`CONCAT_WS(separator, ...)` bỏ qua các đối số `NULL` sau separator:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        CONCAT_WS(' ', first_name, middle_name, last_name)
        ORDER BY last_name, first_name
        SEPARATOR ' | '
    ) AS customer_names
FROM customer_contacts
GROUP BY customer_id;
```

`CONCAT_WS()` giúp trường `middle_name` có thể `NULL` mà không làm toàn bộ biểu thức thành `NULL`. Tuy nhiên, nếu tất cả các đối số dữ liệu đều NULL, biểu thức có thể trở thành chuỗi rỗng; cần xác định có muốn giữ hay loại phần tử rỗng đó không.

### 5.3. Ép kiểu và định dạng số/ngày giờ

Khi nối số tiền, số lượng hoặc ngày giờ, nên định dạng rõ ràng:

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        CONCAT(
            product_name,
            ' (', quantity,
            ', ', FORMAT(unit_price, 2), ')'
        )
        ORDER BY line_no, item_id
        SEPARATOR ' | '
    ) AS item_details
FROM order_items
GROUP BY order_id;
```

`FORMAT()` tạo chuỗi hiển thị và có thể áp dụng quy tắc dấu phân cách theo locale; không dùng kết quả này làm dữ liệu số để tính toán tiếp. Với báo cáo tài chính hoặc API, hãy giữ số ở kiểu số cho đến bước trình bày cuối cùng.

## 6. Xử lý NULL và nhóm không có giá trị

### 6.1. GROUP_CONCAT bỏ qua NULL

Các giá trị `NULL` trong biểu thức được bỏ qua khi nối:

```sql
SELECT
    GROUP_CONCAT(phone ORDER BY phone SEPARATOR ', ') AS phone_list
FROM customers;
```

Khách hàng có `phone IS NULL` không tạo phần tử `NULL` trong chuỗi.

### 6.2. Không có giá trị không-NULL thì kết quả là NULL

Nếu tất cả giá trị của nhóm là NULL hoặc tập đầu vào không có hàng phù hợp, `GROUP_CONCAT()` trả về `NULL`:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(phone ORDER BY phone) AS phone_list
FROM customers
GROUP BY customer_id;
```

Nếu API muốn chuỗi rỗng thay vì NULL, dùng `COALESCE()`:

```sql
SELECT
    customer_id,
    COALESCE(
        GROUP_CONCAT(phone ORDER BY phone SEPARATOR ', '),
        ''
    ) AS phone_list
FROM customers
GROUP BY customer_id;
```

Đây là quyết định định dạng kết quả. `NULL` và chuỗi rỗng có ngữ nghĩa khác nhau; chỉ chuyển sang `''` nếu phía tiêu thụ thật sự muốn quy ước đó.

### 6.3. LEFT JOIN và nhóm không có hàng con

Muốn hiển thị tất cả khách hàng, kể cả người chưa có đơn hàng:

```sql
SELECT
    c.customer_id,
    c.full_name,
    GROUP_CONCAT(
        o.order_id
        ORDER BY o.created_at DESC, o.order_id DESC
        SEPARATOR ', '
    ) AS order_ids
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name;
```

Với khách hàng không có đơn, `o.order_id` là NULL do LEFT JOIN và kết quả `GROUP_CONCAT()` là NULL. Nếu muốn hiển thị chuỗi rỗng, bọc bằng `COALESCE()`.

Không dùng `GROUP_CONCAT(CONCAT(o.order_id, ':', o.status))` một cách thiếu kiểm tra trong truy vấn LEFT JOIN. Nếu biểu thức tạo ra chuỗi giả hoặc rỗng cho hàng NULL mở rộng, kết quả có thể không đúng ý định. Hãy kiểm tra NULL ở biểu thức hoặc dùng `CASE WHEN o.order_id IS NOT NULL THEN ... END`.

## 7. GROUP_CONCAT và GROUP BY

### 7.1. Mỗi nhóm có một chuỗi tổng hợp

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR ', '
    ) AS order_ids
FROM orders
GROUP BY customer_id;
```

Mỗi `customer_id` tạo một nhóm. `COUNT(*)` đếm hàng của nhóm, còn `GROUP_CONCAT()` nối các mã đơn của cùng nhóm.

### 7.2. ONLY_FULL_GROUP_BY

Khi bật `ONLY_FULL_GROUP_BY`, cột trong `SELECT` phải được nhóm, được tổng hợp hoặc được MySQL xác định phụ thuộc hàm vào các cột group theo quy tắc của phiên bản.

Ví dụ không an toàn:

```sql
-- customer_name không được nhóm hoặc tổng hợp
SELECT
    customer_id,
    customer_name,
    GROUP_CONCAT(order_id)
FROM orders
GROUP BY customer_id;
```

Nếu `customer_name` không phải cột của bảng `orders` hoặc không được xác định phụ thuộc hàm hợp lệ, truy vấn có thể bị từ chối. Cách rõ ràng là JOIN tới bảng khách hàng và nhóm các cột cần thiết:

```sql
SELECT
    c.customer_id,
    c.full_name,
    GROUP_CONCAT(o.order_id ORDER BY o.order_id) AS order_ids
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name;
```

Không tắt `ONLY_FULL_GROUP_BY` chỉ để truy vấn chạy. Hãy xác định đúng quy tắc chọn giá trị đại diện cho mỗi nhóm.

### 7.3. Điều kiện lọc nhóm bằng HAVING

`WHERE` lọc hàng trước khi nhóm; `HAVING` lọc kết quả nhóm sau khi tổng hợp:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(order_id ORDER BY order_id) AS order_ids,
    COUNT(*) AS order_count
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
HAVING COUNT(*) >= 3;
```

Chỉ khách hàng có ít nhất ba đơn trong khoảng thời gian được chọn mới xuất hiện. Có thể dùng `HAVING` với biểu thức tổng hợp, nhưng không nên dùng thay `WHERE` cho điều kiện lọc hàng thông thường.

## 8. group_concat_max_len và giới hạn kết quả

### 8.1. Giá trị mặc định

MySQL giới hạn độ dài kết quả của `GROUP_CONCAT()` bằng biến hệ thống `group_concat_max_len`. Giá trị mặc định thường là `1024` byte. Giá trị tối đa thực tế còn bị giới hạn bởi `max_allowed_packet`.

Kiểm tra các giá trị:

```sql
SELECT
    @@SESSION.group_concat_max_len AS session_group_concat_max_len,
    @@GLOBAL.group_concat_max_len AS global_group_concat_max_len,
    @@max_allowed_packet AS max_allowed_packet;
```

Độ dài được tính theo byte, không phải số ký tự hiển thị. Với `utf8mb4`, một ký tự có thể chiếm tối đa bốn byte; do đó giới hạn 1024 byte có thể chứa ít hơn 1024 ký tự.

### 8.2. Kết quả bị cắt

Nếu chuỗi tổng hợp vượt giới hạn, MySQL cắt kết quả theo giới hạn cấu hình và phát warning. Truy vấn vẫn có thể trả về một chuỗi có vẻ hợp lệ nhưng thiếu phần tử ở cuối. Đây là rủi ro quan trọng khi dùng `GROUP_CONCAT()` để tạo báo cáo hoặc dữ liệu trao đổi.

Ví dụ thử nghiệm:

```sql
SET SESSION group_concat_max_len = 32;

SELECT GROUP_CONCAT(product_name ORDER BY item_id SEPARATOR ', ')
       AS product_list
FROM order_items;

SHOW WARNINGS;
```

Lệnh `SHOW WARNINGS` cần chạy ngay sau câu SELECT để kiểm tra cảnh báo do câu lệnh đó phát ra. Trong thực tế, hãy khôi phục hoặc đặt giới hạn session phù hợp sau thử nghiệm.

### 8.3. Tăng giới hạn cho session hiện tại

```sql
SET SESSION group_concat_max_len = 16384;

SELECT @@SESSION.group_concat_max_len;
```

Thay đổi SESSION chỉ ảnh hưởng connection hiện tại. Đây thường là cách phù hợp nếu chỉ một báo cáo cần chuỗi dài hơn. Không cần thay đổi cấu hình toàn server cho một truy vấn riêng lẻ.

### 8.4. Đặt mặc định GLOBAL

```sql
SET GLOBAL group_concat_max_len = 16384;
```

Giá trị GLOBAL được dùng làm mặc định cho các session mới; các session đang tồn tại giữ giá trị SESSION của chúng. Muốn duy trì sau restart, dùng file cấu hình server hoặc cơ chế persist được phiên bản hỗ trợ, sau khi đánh giá bộ nhớ và tải của hệ thống.

Ví dụ cấu hình:

```ini
[mysqld]
group_concat_max_len = 16384
```

Không tăng giới hạn lên một con số cực lớn theo thói quen. Giá trị lớn có thể làm các nhóm rất lớn tạo chuỗi chiếm nhiều bộ nhớ, tăng chi phí truyền kết quả và gây áp lực lên ứng dụng. Hãy chọn giới hạn theo kích thước kết quả tối đa có ý nghĩa.

### 8.5. max_allowed_packet vẫn là giới hạn

Tăng `group_concat_max_len` không đồng nghĩa có thể trả về chuỗi vô hạn. `max_allowed_packet` đặt giới hạn cho kích thước gói/kết quả được phép trong giao tiếp và có thể giới hạn kết quả thực tế. Cả hai biến cần được xem xét cùng nhau; không tăng `max_allowed_packet` nếu chưa hiểu ảnh hưởng tới server/client và nhu cầu ứng dụng.

### 8.6. Kiểm tra warning trong ứng dụng

Khi dùng JDBC, ứng dụng có thể kiểm tra warning của `Statement`/`ResultSet` theo driver:

```java
try (var statement = connection.createStatement()) {
    try (var result = statement.executeQuery(
            "SELECT GROUP_CONCAT(order_id) FROM orders")) {
        if (result.next()) {
            String orderIds = result.getString(1);
        }
    }

    SQLWarning warning = statement.getWarnings();
    while (warning != null) {
        // Ghi nhận SQLState, vendor code và message để giám sát
        warning = warning.getNextWarning();
    }
}
```

Ví dụ cần import `java.sql.SQLWarning`. Cách warning được gắn vào Statement/Connection có thể phụ thuộc driver; hãy xác minh trên Connector/J đang dùng và không bỏ qua warning chỉ vì truy vấn không ném exception.

## 9. Kiểu dữ liệu kết quả và charset

`GROUP_CONCAT()` trả về một chuỗi. Kiểu kết quả và thuộc tính binary/nonbinary phụ thuộc đối số và cấu hình. Trong MySQL, khi `group_concat_max_len` không vượt quá 512, metadata kết quả có thể là `VARCHAR`/`VARBINARY`; khi lớn hơn 512, có thể là `TEXT`/`BLOB` tương ứng. Ứng dụng nên đọc theo kiểu chuỗi/byte phù hợp và không dựa vào một metadata type cố định khi cấu hình thay đổi.

Character set của biểu thức đầu vào ảnh hưởng character set kết quả. Nếu nối dữ liệu đa ngôn ngữ, bảo đảm các cột và connection dùng charset phù hợp, thường là `utf8mb4`. Tránh chuyển đổi sai charset trước khi nối vì `GROUP_CONCAT()` không sửa được dữ liệu đã bị mojibake.

Ví dụ kiểm tra:

```sql
SELECT
    CHARSET(GROUP_CONCAT(full_name ORDER BY full_name)) AS result_charset,
    COLLATION(GROUP_CONCAT(full_name ORDER BY full_name)) AS result_collation
FROM customers;
```

Với dữ liệu nhị phân, kết quả có thể mang tính binary. Không giả định mọi giá trị tổng hợp đều là văn bản UTF-8.

## 10. GROUP_CONCAT trong các truy vấn thực tế

### 10.1. Danh sách sản phẩm theo đơn hàng

```sql
SELECT
    oi.order_id,
    GROUP_CONCAT(
        CONCAT(oi.product_name, ' x', oi.quantity)
        ORDER BY oi.line_no, oi.item_id
        SEPARATOR '; '
    ) AS items
FROM order_items AS oi
GROUP BY oi.order_id;
```

### 10.2. Danh sách tag duy nhất theo bài viết

```sql
SELECT
    pt.post_id,
    GROUP_CONCAT(
        DISTINCT t.tag_name
        ORDER BY t.tag_name
        SEPARATOR ', '
    ) AS tags
FROM post_tags AS pt
JOIN tags AS t
  ON t.tag_id = pt.tag_id
GROUP BY pt.post_id;
```

### 10.3. Danh sách trạng thái theo thời gian

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        CONCAT(status, ' @ ', DATE_FORMAT(changed_at, '%Y-%m-%d %H:%i:%s'))
        ORDER BY changed_at, history_id
        SEPARATOR ' -> '
    ) AS status_history
FROM order_status_history
GROUP BY order_id;
```

Thứ tự theo `changed_at` và `history_id` giúp lịch sử ổn định khi nhiều sự kiện có cùng thời điểm.

### 10.4. Kết hợp với điều kiện lọc

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR ', '
    ) AS paid_orders
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2;
```

Chỉ các đơn `PAID` tham gia tổng hợp; `HAVING` giữ lại khách hàng có ít nhất hai đơn phù hợp.

## 11. GROUP_CONCAT, JSON_ARRAYAGG và định dạng trao đổi

`GROUP_CONCAT()` phù hợp với chuỗi hiển thị hoặc danh sách đơn giản. Nếu cần trả dữ liệu có cấu trúc cho API, `JSON_ARRAYAGG()` có thể phù hợp hơn:

```sql
SELECT
    order_id,
    JSON_ARRAYAGG(
        JSON_OBJECT(
            'itemId', item_id,
            'productName', product_name,
            'quantity', quantity
        )
    ) AS items_json
FROM order_items
GROUP BY order_id;
```

JSON giữ ranh giới kiểu dữ liệu và escape chuỗi theo định dạng, nên an toàn hơn việc tự tách chuỗi bằng dấu phẩy. Tuy nhiên, cần kiểm tra hỗ trợ JSON của phiên bản MySQL và giới hạn kết quả.

Không giả định thứ tự phần tử của `JSON_ARRAYAGG()` luôn được bảo đảm nếu tài liệu phiên bản không quy định thứ tự. Nếu thứ tự là yêu cầu nghiệp vụ, hãy kiểm tra khả năng sắp xếp trong phiên bản mục tiêu hoặc sắp xếp sau khi nhận dữ liệu bằng một quy trình có bảo đảm. `GROUP_CONCAT()` cho phép khai báo `ORDER BY` trực tiếp bên trong hàm.

## 12. Hiệu năng và giới hạn thực tế

### 12.1. DISTINCT và ORDER BY có chi phí

Trong một nhóm lớn, `DISTINCT` cần xác định các giá trị trùng; `ORDER BY` bên trong hàm cần sắp xếp các giá trị trước khi nối. Cả hai đều có thể làm tăng CPU, bộ nhớ và chi phí xử lý tạm.

Chỉ dùng `DISTINCT` nếu ngữ nghĩa yêu cầu loại trùng. Chỉ dùng `ORDER BY` nếu thứ tự kết quả quan trọng, nhưng với báo cáo hoặc API thường nên khai báo để kết quả xác định.

### 12.2. Lọc dữ liệu trước khi tổng hợp

Giảm số hàng tham gia nhóm bằng `WHERE` khi điều kiện lọc áp dụng cho từng hàng:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(order_id ORDER BY created_at DESC, order_id DESC) AS order_ids
FROM orders
WHERE created_at >= '2026-01-01'
  AND status = 'PAID'
GROUP BY customer_id;
```

Index có thể giúp lọc và nhóm tùy phân bố dữ liệu, nhưng không có một index chung phù hợp mọi truy vấn. Hãy dùng `EXPLAIN` để kiểm tra access path và đo trên dữ liệu gần production.

### 12.3. Tránh tạo một chuỗi khổng lồ cho nhóm không giới hạn

Một khách hàng có thể có hàng triệu sự kiện. Nối tất cả ID vào một chuỗi không nhất thiết là cách trả dữ liệu tốt. Hãy cân nhắc:

- Phân trang chi tiết thay vì gom toàn bộ.
- Giới hạn khoảng thời gian hoặc số lượng phần tử theo yêu cầu báo cáo.
- Tạo bảng tổng hợp/materialized result theo lịch nếu báo cáo được gọi thường xuyên.
- Trả JSON hoặc nhiều hàng có cấu trúc thay vì một chuỗi khó phân tích.
- Tách endpoint lấy danh sách chi tiết khỏi endpoint lấy số liệu tổng quan.

`group_concat_max_len` chỉ là giới hạn kỹ thuật, không phải chính sách nghiệp vụ cho phép bỏ qua phần còn lại của danh sách.

### 12.4. Kiểm tra execution plan và số lượng dữ liệu

```sql
EXPLAIN
SELECT
    customer_id,
    GROUP_CONCAT(order_id ORDER BY created_at DESC, order_id DESC)
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
```

Quan sát index được chọn, số hàng ước lượng, cách nhóm và điều kiện lọc. Có thể dùng `EXPLAIN ANALYZE` trên MySQL hỗ trợ để xem số hàng và thời gian thực tế; lệnh này thực thi truy vấn nên cần cân nhắc tải trên production.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Không có ORDER BY bên trong hàm | Thứ tự các phần tử không xác định | Khai báo `ORDER BY` với tie-breaker duy nhất |
| Chỉ ORDER BY bên ngoài | Chỉ sắp xếp các nhóm, không sắp xếp phần tử trong chuỗi | Đặt ORDER BY bên trong `GROUP_CONCAT()` |
| Không tăng `group_concat_max_len` khi cần | Kết quả bị cắt và có warning | Kiểm tra giới hạn, tăng SESSION hợp lý và đọc warning |
| Nghĩ giới hạn tính theo ký tự | Dữ liệu UTF-8 có thể bị cắt sớm hơn dự kiến | Tính theo byte và tính đến ký tự nhiều byte |
| Dùng DISTINCT để che lỗi JOIN | Mất dữ liệu lặp có ý nghĩa hoặc che cardinality sai | Kiểm tra quan hệ JOIN và tổng hợp theo khóa trước |
| Nối chuỗi rồi parse bằng dấu phẩy | Giá trị chứa dấu phân tách làm sai cấu trúc | Dùng escaping rõ ràng hoặc JSON có cấu trúc |
| Không xử lý NULL | Kết quả toàn NULL trả NULL; biểu thức CONCAT có thể bị bỏ | Dùng `CONCAT_WS`, `CASE` hoặc `COALESCE` theo ý nghĩa |
| Tăng max_len quá lớn | Chuỗi nhóm lớn gây áp lực bộ nhớ và truyền dữ liệu | Giới hạn số phần tử hoặc đổi cách truy vấn/API |
| Cho rằng JSON_ARRAYAGG có thứ tự mặc định | Thứ tự phần tử có thể không được bảo đảm | Kiểm tra tài liệu phiên bản và sắp xếp theo cơ chế xác định |

## 14. Bộ truy vấn kiểm tra nhanh

```sql
-- Danh sách có thứ tự và separator tùy chỉnh
SELECT
    customer_id,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR ' | '
    ) AS order_list
FROM orders
GROUP BY customer_id;

-- Loại bỏ trạng thái trùng theo collation của biểu thức
SELECT
    customer_id,
    GROUP_CONCAT(DISTINCT status ORDER BY status SEPARATOR ', ') AS statuses
FROM orders
GROUP BY customer_id;

-- Xử lý kết quả NULL
SELECT
    customer_id,
    COALESCE(GROUP_CONCAT(phone ORDER BY phone), '') AS phone_list
FROM customers
GROUP BY customer_id;

-- Kiểm tra giới hạn
SELECT
    @@SESSION.group_concat_max_len,
    @@GLOBAL.group_concat_max_len,
    @@max_allowed_packet;

-- Đặt giới hạn cho session hiện tại
SET SESSION group_concat_max_len = 16384;

-- Chạy truy vấn tổng hợp cần kiểm tra
SELECT GROUP_CONCAT(order_id ORDER BY order_id SEPARATOR ', ')
FROM orders;

-- Kiểm tra warning ngay sau truy vấn tổng hợp cần theo dõi
SHOW WARNINGS;
```

Các truy vấn dùng `orders` và `customers` làm ví dụ. `SHOW WARNINGS` phải chạy ngay sau câu lệnh cần kiểm tra; nếu chạy một câu SQL khác trước đó, danh sách warning có thể không còn là warning của truy vấn tổng hợp.

## 15. Checklist khi dùng GROUP_CONCAT

- [ ] Đã xác định rõ đơn vị nhóm và `GROUP BY` đúng khóa.
- [ ] Có `ORDER BY` bên trong hàm khi thứ tự phần tử quan trọng.
- [ ] Có tie-breaker duy nhất nếu giá trị sắp xếp có thể trùng.
- [ ] `SEPARATOR` phù hợp với mục đích hiển thị và dữ liệu không gây nhập nhằng.
- [ ] `DISTINCT` phản ánh đúng nghiệp vụ và collation đã được xem xét.
- [ ] Đã hiểu `NULL` bị bỏ qua và kết quả toàn NULL là NULL.
- [ ] Đã kiểm tra `group_concat_max_len` và `max_allowed_packet`.
- [ ] Đã kiểm tra warning để phát hiện chuỗi bị cắt.
- [ ] Đã tính theo byte khi dữ liệu dùng charset nhiều byte như utf8mb4.
- [ ] Đã đo chi phí của sắp xếp, loại trùng và nhóm lớn.
- [ ] Không dùng chuỗi nối làm serialization nếu chưa có quy tắc escaping rõ.
- [ ] Đã cân nhắc JSON hoặc phân trang nếu cần trao đổi danh sách lớn có cấu trúc.

## 16. Kết luận

`GROUP_CONCAT()` gom nhiều giá trị của một nhóm thành một chuỗi. `ORDER BY` bên trong hàm kiểm soát thứ tự nối, `SEPARATOR` chọn dấu phân tách và `DISTINCT` loại bỏ giá trị trùng theo quy tắc so sánh của biểu thức. Các giá trị NULL bị bỏ qua; nếu không có giá trị nào để nối, kết quả là NULL.

Độ dài kết quả chịu giới hạn của `group_concat_max_len` và `max_allowed_packet`. Khi vượt giới hạn, chuỗi có thể bị cắt kèm warning mà truy vấn vẫn trả kết quả. Hãy đặt giới hạn hợp lý theo session, kiểm tra warning, dùng thứ tự xác định và chọn JSON hoặc phân trang khi cần dữ liệu có cấu trúc lớn.
