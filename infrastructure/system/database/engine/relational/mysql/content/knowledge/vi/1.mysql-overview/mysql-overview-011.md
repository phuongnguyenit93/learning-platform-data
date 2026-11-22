# Trình tự học từ môi trường thực hành đến ứng dụng và vận hành cơ sở dữ liệu quan hệ

MySQL là hệ quản trị cơ sở dữ liệu quan hệ (RDBMS). Dữ liệu được tổ chức thành các bảng có hàng và cột; các bảng liên kết với nhau bằng khóa, còn SQL được dùng để định nghĩa cấu trúc, đọc và thay đổi dữ liệu. Khi đưa MySQL vào một ứng dụng thực tế, chỉ biết viết câu `SELECT` là chưa đủ: bạn còn phải thiết kế mô hình dữ liệu, chọn kiểu dữ liệu và ràng buộc phù hợp, hiểu index, xử lý giao dịch đồng thời, bảo vệ quyền truy cập và có khả năng phục hồi khi sự cố xảy ra.

Bài học này xây dựng lộ trình làm chủ MySQL theo đúng trình tự công việc: bắt đầu từ môi trường thực hành, đi qua thiết kế bảng và truy vấn SQL, kết nối ứng dụng, rồi tiến tới đọc kế hoạch thực thi, tối ưu truy vấn, transaction, kiểm soát đồng thời và vận hành. Mục tiêu của module là giúp bạn làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ.

Sau khi hoàn thành lộ trình, bạn nên có thể tự xây dựng một schema nhỏ, giải thích được các quyết định thiết kế, viết truy vấn đúng, tích hợp truy vấn an toàn vào ứng dụng, tìm nguyên nhân của truy vấn chậm và mô tả cách sao lưu cũng như khôi phục dữ liệu.

## 1. Hiểu các thành phần trước khi viết SQL

Một hệ thống MySQL thường có các thành phần sau:

- **MySQL Server** nhận kết nối, xác thực tài khoản, phân tích và thực thi SQL, quản lý transaction, khóa và lưu trữ dữ liệu.
- **Database (schema)** là vùng chứa các đối tượng như bảng, view, index, trigger và routine.
- **Table** lưu dữ liệu theo hàng và cột. Mỗi cột có kiểu dữ liệu và có thể có ràng buộc.
- **Client** như MySQL Shell, dòng lệnh `mysql` hoặc một công cụ quản trị gửi SQL tới server và hiển thị kết quả.
- **Ứng dụng** kết nối tới server thông qua driver hoặc thư viện tương ứng với ngôn ngữ lập trình.
- **Storage engine** quyết định cách dữ liệu được lưu và một số hành vi truy cập. InnoDB là lựa chọn phổ biến cho ứng dụng giao dịch vì hỗ trợ transaction, khóa ở mức hàng và khóa ngoại.

SQL thường được chia thành các nhóm thao tác. DDL (ví dụ `CREATE`, `ALTER`, `DROP`) định nghĩa cấu trúc; DML (ví dụ `INSERT`, `UPDATE`, `DELETE`) thay đổi dữ liệu; truy vấn `SELECT` đọc dữ liệu; các lệnh transaction như `START TRANSACTION`, `COMMIT` và `ROLLBACK` điều khiển một đơn vị công việc. Hãy phân biệt rõ thay đổi cấu trúc với thay đổi dữ liệu vì chúng có vòng đời triển khai và rủi ro khác nhau.

## 2. Dựng môi trường thực hành có thể kiểm tra được

Bạn cần một MySQL Server có thể kết nối, một client để chạy SQL và một schema dùng riêng cho bài tập. Có thể cài MySQL trực tiếp hoặc chạy trong môi trường container; điều quan trọng là ghi lại cách khởi động, dừng, kết nối và xem log để có thể tái tạo môi trường khi cần.

Sau khi kết nối, kiểm tra server và database hiện tại:

```sql
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution,
    DATABASE() AS current_database;
```

Tạo một schema thực hành dùng bộ ký tự Unicode đầy đủ:

```sql
CREATE DATABASE learning_shop
    CHARACTER SET utf8mb4;

USE learning_shop;

SELECT DATABASE();
```

`utf8mb4` hỗ trợ đầy đủ Unicode, bao gồm nhiều ký tự ngoài nhóm BMP và emoji. Khi làm việc với một hệ thống có sẵn, hãy kiểm tra charset và collation hiện tại trước khi thay đổi; collation quyết định cách so sánh và sắp xếp chuỗi, vì vậy nó có thể ảnh hưởng tới kết quả truy vấn và tính duy nhất của dữ liệu.

Tạo một tài khoản riêng cho ứng dụng hoặc bài tập. Ví dụ dưới đây cấp các quyền thao tác dữ liệu cơ bản trên đúng schema:

```sql
CREATE USER 'shop_app'@'localhost'
    IDENTIFIED BY 'replace_with_a_secret';

GRANT SELECT, INSERT, UPDATE, DELETE
    ON learning_shop.*
    TO 'shop_app'@'localhost';
```

Thay mật khẩu minh họa bằng secret được quản lý an toàn. Phần host (`localhost` trong ví dụ) phải khớp với cách client kết nối; nếu ứng dụng chạy ở máy hoặc container khác, cần cấu hình host và giới hạn mạng phù hợp. Không dùng tài khoản quản trị `root` làm tài khoản chạy ứng dụng.

Một môi trường thực hành tốt phải cho phép bạn trả lời được: server đang chạy phiên bản nào, ứng dụng kết nối tới host và port nào, đang dùng schema nào, tài khoản có quyền gì, và log nằm ở đâu. Ghi các thông tin này vào hướng dẫn phát triển của dự án, nhưng tuyệt đối không ghi mật khẩu thật vào tài liệu hoặc mã nguồn.

## 3. Thiết kế mô hình dữ liệu trước khi tạo bảng

Hãy bắt đầu từ nghiệp vụ và các quy tắc dữ liệu, không bắt đầu bằng việc tạo bảng theo cảm tính. Với một cửa hàng trực tuyến đơn giản, các thực thể có thể gồm khách hàng, sản phẩm, đơn hàng và dòng sản phẩm trong đơn hàng.

Các quan hệ thường gặp:

- **Một-một (1:1):** một tài khoản có một hồ sơ mở rộng. Chỉ tách bảng khi có lý do về vòng đời, quyền truy cập hoặc cấu trúc dữ liệu.
- **Một-nhiều (1:N):** một khách hàng có nhiều đơn hàng. Khóa ngoại `customer_id` nằm ở bảng `orders`.
- **Nhiều-nhiều (N:N):** một đơn hàng chứa nhiều sản phẩm và một sản phẩm xuất hiện trong nhiều đơn hàng. Cần bảng liên kết, chẳng hạn `order_items`, để biểu diễn quan hệ này và lưu các thuộc tính của từng dòng hàng.

Chuẩn hóa giúp mỗi sự kiện hoặc thuộc tính được lưu ở nơi phù hợp, giảm dữ liệu trùng lặp và tránh lỗi khi thêm, sửa hoặc xóa. Ví dụ, tên và email khách hàng thuộc bảng `customers`; thông tin chung của đơn hàng thuộc `orders`; số lượng và giá tại thời điểm mua thuộc `order_items`. Giá bán tại thời điểm mua nên được lưu trên dòng đơn hàng để lịch sử đơn không thay đổi khi giá hiện tại của sản phẩm được cập nhật.

### Chọn kiểu dữ liệu và ràng buộc

| Nhu cầu | Kiểu hoặc ràng buộc thường dùng | Lưu ý |
|---|---|---|
| Khóa định danh | `INT` hoặc `BIGINT`, có thể dùng `AUTO_INCREMENT` | Chọn theo quy mô và giữ kiểu tương thích giữa khóa chính, khóa ngoại. |
| Tiền và số thập phân chính xác | `DECIMAL(p,s)` | Tránh `FLOAT` hoặc `DOUBLE` cho giá trị tiền tệ cần tính chính xác. |
| Chuỗi có độ dài giới hạn | `VARCHAR(n)` | Chọn giới hạn theo quy tắc nghiệp vụ; dùng `utf8mb4` khi cần Unicode. |
| Văn bản dài | `TEXT` | Không dùng thay cho mọi chuỗi; cân nhắc nhu cầu tìm kiếm và index. |
| Ngày và thời gian | `DATE`, `DATETIME`, `TIMESTAMP` | Xác định rõ múi giờ và ý nghĩa thời gian trước khi chọn kiểu. |
| Dữ liệu bán cấu trúc | `JSON` | Hữu ích cho thuộc tính linh hoạt; không nên thay thế các quan hệ cần join và ràng buộc. |
| Giá trị bắt buộc | `NOT NULL` | Biểu diễn quy tắc dữ liệu ngay tại database. |
| Giá trị duy nhất | `PRIMARY KEY`, `UNIQUE` | Chọn cột hoặc tổ hợp cột thực sự phải duy nhất. |
| Quan hệ giữa bảng | `FOREIGN KEY` | Giúp database kiểm soát tính toàn vẹn tham chiếu. |

`PRIMARY KEY` định danh duy nhất một hàng. `UNIQUE` ngăn các giá trị hoặc tổ hợp giá trị bị trùng. `FOREIGN KEY` bảo đảm hàng tham chiếu tới một hàng hợp lệ ở bảng cha theo quy tắc đã khai báo. `DEFAULT` cung cấp giá trị mặc định; `CHECK` có thể diễn đạt một số điều kiện miền dữ liệu tùy phiên bản MySQL đang dùng. Các ràng buộc này là lớp bảo vệ quan trọng ngay cả khi ứng dụng đã kiểm tra dữ liệu.

Ví dụ tạo hai bảng cơ bản:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created (customer_id, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Trong ví dụ, `id` là khóa chính; email khách hàng có ràng buộc duy nhất; `customer_id` liên kết đơn hàng với khách hàng; `total_amount` dùng `DECIMAL`; cả hai bảng dùng InnoDB. Index trên `orders` được đưa vào để hỗ trợ các truy vấn tìm đơn theo khách hàng và thời gian; ở giai đoạn đầu, hãy xem nó như một giả thuyết thiết kế cần kiểm chứng bằng truy vấn thực tế.

Trước khi chốt schema, hãy thử các tình huống dữ liệu không hợp lệ: email trùng, đơn hàng tham chiếu khách hàng không tồn tại, trường bắt buộc bị bỏ trống và giá trị vượt giới hạn. Một thiết kế tốt khiến các trường hợp sai bị từ chối ở đúng tầng dữ liệu.

## 4. Học SQL từ thao tác đơn lẻ đến truy vấn kết hợp

Học theo thứ tự: thêm dữ liệu, đọc dữ liệu, cập nhật, xóa, rồi kết hợp nhiều bảng và tổng hợp. Luôn kiểm tra điều kiện `WHERE` trước khi chạy `UPDATE` hoặc `DELETE`; một câu lệnh thiếu điều kiện có thể tác động tới toàn bộ bảng.

```sql
INSERT INTO customers (email, full_name)
VALUES ('linh@example.test', 'Nguyen Minh Linh');

SELECT id, email, full_name, created_at
FROM customers
WHERE email = 'linh@example.test';

UPDATE customers
SET full_name = 'Nguyen Minh Linh'
WHERE email = 'linh@example.test';
```

Khi truy vấn nhiều bảng, dùng `JOIN` theo khóa quan hệ. Ví dụ lấy các đơn gần đây cùng tên khách hàng:

```sql
SELECT
    o.id,
    c.full_name,
    o.status,
    o.total_amount,
    o.created_at
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE o.created_at >= '2026-01-01'
ORDER BY o.created_at DESC
LIMIT 20;
```

`INNER JOIN` chỉ trả về các hàng có cặp khớp ở cả hai phía. `LEFT JOIN` giữ lại hàng ở bảng bên trái kể cả khi không có hàng khớp bên phải. Khi dùng `LEFT JOIN` để tìm khách hàng chưa có đơn, hãy chú ý điều kiện đặt trong `ON` hay `WHERE`, vì điều kiện ở `WHERE` có thể loại bỏ các hàng có giá trị `NULL` và làm thay đổi ý nghĩa của phép nối.

Các hàm tổng hợp như `COUNT`, `SUM`, `AVG`, `MIN` và `MAX` thường đi cùng `GROUP BY`. `WHERE` lọc hàng trước khi nhóm; `HAVING` lọc nhóm sau khi tổng hợp:

```sql
SELECT
    c.id,
    c.full_name,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_spent
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
GROUP BY c.id, c.full_name
HAVING COUNT(o.id) >= 2
ORDER BY total_spent DESC;
```

Sau khi vững các thao tác trên, học tiếp subquery và CTE (`WITH`) để chia truy vấn phức tạp thành các phần có tên rõ ràng. Khi đọc một câu SQL dài, hãy xác định lần lượt nguồn dữ liệu (`FROM`), quan hệ (`JOIN`), điều kiện (`WHERE`), cách nhóm (`GROUP BY`), điều kiện nhóm (`HAVING`) và thứ tự/kích thước kết quả (`ORDER BY`, `LIMIT`).

## 5. Kết nối MySQL với ứng dụng

Ứng dụng không nên ghép chuỗi đầu vào của người dùng trực tiếp vào câu SQL. Hãy dùng prepared statement hoặc API bind parameter của driver để truyền giá trị riêng với cấu trúc câu lệnh. Ví dụ minh họa:

```sql
SELECT id, status, total_amount
FROM orders
WHERE customer_id = ?
  AND created_at >= ?
ORDER BY created_at DESC;
```

Dấu `?` là placeholder minh họa; cú pháp bind cụ thể phụ thuộc driver và ngôn ngữ lập trình. Prepared statement giúp dữ liệu đầu vào không bị diễn giải như một phần cú pháp SQL, từ đó giảm nguy cơ SQL injection và giúp tái sử dụng câu lệnh trong nhiều trường hợp.

Khi tích hợp database vào ứng dụng, hãy thiết kế các điểm sau:

1. **Driver và connection pool:** dùng driver được hỗ trợ cho nền tảng ứng dụng. Pool tái sử dụng kết nối, giới hạn số kết nối đồng thời và tránh tạo một kết nối mới cho mỗi thao tác nhỏ.
2. **Quản lý cấu hình:** tách host, port, schema, tài khoản và secret khỏi mã nguồn. Môi trường phát triển, kiểm thử và sản xuất nên có cấu hình và tài khoản riêng.
3. **Tham số hóa truy vấn:** bind giá trị đầu vào; tên bảng, tên cột hoặc chiều sắp xếp động phải được chọn từ danh sách cho phép vì không phải mọi thành phần SQL đều có thể bind như một giá trị.
4. **Ranh giới transaction:** gom các thao tác phải thành công hoặc thất bại cùng nhau vào một transaction. Không giữ transaction mở trong lúc chờ người dùng hoặc gọi dịch vụ mạng lâu.
5. **Migration:** lưu thay đổi schema thành các migration có thứ tự và có thể kiểm tra trong quy trình triển khai. Không để mỗi máy hoặc mỗi môi trường tự sửa cấu trúc theo cách riêng.
6. **Xử lý lỗi:** phân biệt lỗi dữ liệu (ví dụ vi phạm unique), lỗi kết nối, timeout và deadlock. Chỉ retry những thao tác có thể retry an toàn; với transaction bị deadlock, thường phải chạy lại toàn bộ đơn vị công việc.

Ngoài ra, chú ý lỗi N+1: ứng dụng tải danh sách nhiều hàng rồi phát sinh thêm một truy vấn cho từng hàng. Hãy xem xét `JOIN`, truy vấn theo lô hoặc cơ chế eager loading phù hợp. Với danh sách lớn, chọn các cột cần dùng và phân trang có thứ tự ổn định; phân trang bằng `OFFSET` rất lớn có thể ngày càng tốn chi phí, khi đó có thể cân nhắc keyset pagination dựa trên khóa hoặc cặp cột sắp xếp.

## 6. Đọc kế hoạch thực thi và tối ưu truy vấn

Một câu SQL ngắn chưa chắc chạy nhanh. Thời gian thực thi phụ thuộc vào số hàng cần đọc, index phù hợp, cách nối bảng, thống kê dữ liệu, tải hệ thống và lượng dữ liệu phải trả về. Khi một truy vấn chậm, hãy tái hiện nó với tham số và lượng dữ liệu gần thực tế, đo thời gian, rồi kiểm tra kế hoạch thực thi.

Ví dụ, truy vấn đơn theo khách hàng và thời gian:

```sql
EXPLAIN
SELECT id, status, total_amount, created_at
FROM orders
WHERE customer_id = 7
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 20;
```

Trong kết quả `EXPLAIN`, hãy tập trung vào:

- `type`: kiểu truy cập mà optimizer chọn. Đọc tuần tự toàn bảng (`ALL`) có thể đáng chú ý khi bảng lớn, nhưng không tự động là lỗi nếu bảng nhỏ hoặc truy vấn cần phần lớn dữ liệu.
- `possible_keys` và `key`: index nào có thể dùng và index nào thực sự được chọn.
- `rows`: ước lượng số hàng cần đọc. Đây là ước lượng, không phải lúc nào cũng là số hàng thực tế.
- `filtered` và `Extra`: thông tin bổ sung về điều kiện lọc, sắp xếp hoặc cách thực thi.

Index là cấu trúc phụ giúp tìm hàng nhanh hơn, nhưng mỗi index cũng chiếm dung lượng và làm tăng chi phí `INSERT`, `UPDATE`, `DELETE`. Với index ghép `(customer_id, created_at)`, thứ tự cột quan trọng: index thường hữu ích cho điều kiện bắt đầu bằng `customer_id`, và có thể hỗ trợ tiếp điều kiện theo `created_at` nhờ quy tắc tiền tố trái. Một index ghép không tương đương với mọi tổ hợp index riêng lẻ.

Một số nguyên tắc thực hành:

- Tạo index dựa trên các truy vấn thường dùng và điều kiện lọc, nối, sắp xếp thực tế; tránh index mọi cột.
- Đặt các cột trong index ghép theo mẫu truy vấn và độ chọn lọc phù hợp, sau đó xác minh bằng `EXPLAIN`.
- Tránh bọc cột cần lọc bằng hàm hoặc ép kiểu không cần thiết, vì có thể khiến optimizer khó tận dụng index. Ví dụ, lọc theo một khoảng thời gian thường thân thiện với index hơn việc áp dụng `DATE(created_at)` lên từng hàng.
- `LIKE 'abc%'` có thể tận dụng index trong một số điều kiện; tìm kiếm có wildcard ở đầu như `LIKE '%abc'` thường không dùng được index B-tree thông thường để tìm điểm bắt đầu.
- Chỉ lấy cột cần thiết thay vì luôn dùng `SELECT *`; giảm dữ liệu đọc, truyền và xử lý.
- Xem xét số hàng thực tế, độ phân bố dữ liệu và thống kê; một kế hoạch tốt trên bộ dữ liệu nhỏ có thể khác khi dữ liệu tăng lên.

Một số phiên bản MySQL hỗ trợ `EXPLAIN ANALYZE`, cung cấp số liệu thực thi thực tế nhưng đồng thời thực sự chạy câu truy vấn. Chỉ dùng nó khi hiểu tác động và truy vấn an toàn với môi trường đang kiểm tra. Đừng tối ưu dựa vào một chỉ số đơn lẻ; hãy so sánh thời gian, lượng hàng đọc, tải server và kết quả nghiệp vụ trước/sau thay đổi.

## 7. Transaction và kiểm soát truy cập đồng thời

Transaction gom nhiều thao tác thành một đơn vị công việc. Với InnoDB, các thuộc tính ACID là nền tảng để xử lý dữ liệu đáng tin cậy:

- **Atomicity:** hoặc toàn bộ thay đổi trong transaction được xác nhận, hoặc bị hoàn tác.
- **Consistency:** transaction phải đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ khác theo các ràng buộc và quy tắc ứng dụng.
- **Isolation:** các transaction đồng thời được kiểm soát để hạn chế việc nhìn thấy trạng thái trung gian hoặc cập nhật xung đột.
- **Durability:** sau khi commit thành công, thay đổi được bảo vệ theo cơ chế lưu trữ và cấu hình độ bền của server.

Ví dụ khi tạo một dòng đơn hàng cần giảm tồn kho, việc kiểm tra tồn kho và ghi đơn phải nằm trong cùng transaction:

```sql
START TRANSACTION;

UPDATE inventory
SET available = available - 1
WHERE product_id = 42
  AND available > 0;

-- Ứng dụng đọc số hàng bị ảnh hưởng ngay sau UPDATE.
-- Nếu số hàng khác 1: ROLLBACK và báo hết hàng.
-- Nếu bằng 1: tiếp tục ghi dòng đơn hàng.

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (9001, 42, 1, 199000.00);

COMMIT;
```

Ví dụ giả định ứng dụng kiểm tra số hàng bị ảnh hưởng ngay sau `UPDATE` trên cùng kết nối. Nếu không giảm được đúng một hàng, ứng dụng phải `ROLLBACK` thay vì ghi tiếp dòng đơn hàng. Nếu mọi thao tác thành công, `COMMIT` xác nhận toàn bộ thay đổi. Khi có lỗi giữa chừng, dùng `ROLLBACK` để hoàn tác.

Hai transaction có thể cùng đọc hoặc cập nhật một dữ liệu. InnoDB sử dụng MVCC và các loại khóa để kiểm soát tương tác này. Mức cô lập transaction quyết định những thay đổi nào transaction có thể quan sát; các mức thường gặp gồm `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. Mỗi mức có đánh đổi về tính nhất quán, khả năng đồng thời và chi phí khóa. Hãy kiểm tra cấu hình thực tế của server và chọn mức cô lập theo yêu cầu nghiệp vụ, không đổi mức cô lập chỉ vì một ví dụ trên mạng.

Khi cần đọc rồi cập nhật một hàng theo cách tránh transaction khác chen vào giữa, có thể dùng khóa tường minh trong transaction, chẳng hạn `SELECT ... FOR UPDATE`. Khóa được giữ cho tới khi transaction kết thúc. Điều này giúp bảo vệ thao tác đọc-sửa-ghi nhưng cũng có thể làm các transaction khác phải chờ.

Deadlock xảy ra khi các transaction giữ khóa mà transaction còn lại cần. MySQL có thể chọn một transaction làm nạn nhân và hoàn tác nó. Để giảm rủi ro, hãy giữ transaction ngắn, truy cập nhiều hàng theo cùng thứ tự nhất quán, tạo index phù hợp cho điều kiện cập nhật và xử lý lỗi deadlock bằng cách retry toàn bộ transaction với số lần giới hạn. Không retry vô hạn và không giả định chỉ cần chạy lại câu SQL cuối cùng.

## 8. Phân quyền, sao lưu và khôi phục

### Phân quyền và bảo vệ kết nối

Áp dụng nguyên tắc quyền tối thiểu: tài khoản ứng dụng chỉ có các quyền cần cho chức năng của nó trên schema cần thiết. Tách tài khoản đọc báo cáo, tài khoản migration và tài khoản quản trị nếu vai trò của chúng khác nhau. Rà soát quyền định kỳ, giới hạn nguồn kết nối bằng cấu hình mạng và dùng TLS khi dữ liệu truyền qua mạng cần được bảo vệ.

Secret phải được lưu trong secret manager hoặc cơ chế cấu hình an toàn của môi trường triển khai; không commit mật khẩu vào Git, không ghi mật khẩu vào log và không đưa thông tin xác thực vào câu lệnh có thể bị lưu trong lịch sử terminal. Với lỗi truy cập, kiểm tra đồng thời user, host, quyền trên schema và cấu hình kết nối.

### Sao lưu và diễn tập khôi phục

Backup chỉ có giá trị khi có thể khôi phục được trong thời gian chấp nhận được. Một bản dump logic cho schema thực hành có thể được tạo bằng `mysqldump`:

```bash
mysqldump --single-transaction --routines --triggers --events \
  -u backup_user -p learning_shop > learning_shop.sql
```

Lệnh yêu cầu nhập mật khẩu tương tác. `--single-transaction` tạo snapshot nhất quán cho các bảng transactional như InnoDB trong điều kiện phù hợp; tránh chạy DDL làm thay đổi cấu trúc bảng trong lúc dump. Nếu database dùng storage engine khác hoặc có yêu cầu nhất quán đặc biệt, cần chọn phương thức backup tương ứng.

Khôi phục vào schema đã chuẩn bị bằng client `mysql`:

```bash
mysql -u restore_user -p learning_shop < learning_shop.sql
```

Sau khi restore, kiểm tra số lượng bảng, dữ liệu quan trọng, ràng buộc, quyền truy cập và một số truy vấn nghiệp vụ đại diện. Với môi trường quan trọng, hãy diễn tập trên máy hoặc cụm riêng, đo thời gian khôi phục và xác nhận dữ liệu đạt mốc mong muốn. Replication giúp tăng khả năng sẵn sàng hoặc phân tải đọc trong một số kiến trúc, nhưng không thay thế backup: thao tác xóa nhầm có thể được sao chép sang replica.

### Theo dõi và xử lý sự cố vận hành

Theo dõi các chỉ số gắn với trải nghiệm ứng dụng và sức khỏe database: độ trễ truy vấn, số kết nối đang dùng, tỷ lệ lỗi và timeout, truy vấn chậm, deadlock, dung lượng đĩa, mức sử dụng bộ nhớ, trạng thái backup và độ trễ replication nếu có. Bật và quản lý slow query log theo chính sách phù hợp để tìm các truy vấn cần điều tra.

Khi xử lý sự cố, đi theo chuỗi bằng chứng: xác định thời điểm và phạm vi ảnh hưởng; kiểm tra ứng dụng có tăng lỗi hoặc thời gian chờ không; xem kết nối và truy vấn đang chạy; tìm truy vấn chậm hoặc lock wait; đối chiếu thay đổi triển khai và tải dữ liệu; sau đó mới quyết định sửa SQL, index, cấu hình hay năng lực hạ tầng. Ghi lại nguyên nhân gốc, cách khắc phục và biện pháp ngăn tái diễn.

Một số tình huống nên luyện tập:

| Triệu chứng | Hướng kiểm tra đầu tiên |
|---|---|
| Truy vấn đột nhiên chậm | So sánh `EXPLAIN`, lượng hàng, index và slow query log; kiểm tra thay đổi dữ liệu hoặc triển khai. |
| Lỗi duplicate key | Xác định ràng buộc unique, dữ liệu đầu vào và tính idempotent của thao tác ghi. |
| Lỗi foreign key | Kiểm tra hàng cha, thứ tự ghi/xóa, kiểu dữ liệu khóa và quy tắc tham chiếu. |
| Deadlock hoặc lock wait timeout | Xác định các transaction liên quan, thứ tự truy cập hàng, thời gian giữ khóa và index. |
| Không tạo được kết nối | Kiểm tra host/port, tài khoản-host, quyền, giới hạn kết nối, mạng và trạng thái server. |
| Backup có nhưng restore lỗi | Kiểm tra phiên bản, quyền, dung lượng, tính đầy đủ của dump và quy trình diễn tập. |

## 9. Lộ trình thực hành đề xuất

Học theo từng chặng và chỉ chuyển sang chặng tiếp theo khi có sản phẩm kiểm chứng được:

| Chặng | Nội dung cần nắm | Sản phẩm kiểm chứng |
|---|---|---|
| 1. Môi trường | Kết nối server, client, schema, tài khoản và log | Tạo schema, kết nối lại được và giải thích cấu hình kết nối. |
| 2. Mô hình dữ liệu | Thực thể, quan hệ, chuẩn hóa, kiểu dữ liệu và ràng buộc | ERD nhỏ và DDL tạo được bảng có PK, UNIQUE, FK. |
| 3. SQL nền tảng | CRUD, JOIN, GROUP BY, HAVING, subquery và CTE | Bộ truy vấn đáp ứng các yêu cầu đọc và báo cáo cơ bản. |
| 4. Tích hợp ứng dụng | Driver, pool, prepared statement, migration và xử lý lỗi | Một chức năng ứng dụng đọc/ghi dữ liệu an toàn. |
| 5. Tối ưu | Index đơn/ghép, EXPLAIN và đo hiệu năng | Giải thích kế hoạch thực thi và chứng minh một cải thiện bằng phép đo. |
| 6. Transaction | ACID, isolation, lock, deadlock và retry | Một luồng đặt hàng không làm âm tồn kho khi có nhiều yêu cầu đồng thời. |
| 7. Bảo mật và phục hồi | Quyền tối thiểu, backup, restore và kiểm tra sau restore | Tài khoản có quyền giới hạn và một lần khôi phục đã xác minh. |
| 8. Vận hành | Monitoring, slow query, dung lượng, lỗi kết nối và runbook | Hướng dẫn chẩn đoán một số lỗi thường gặp cùng chỉ số cần theo dõi. |

### Bài tập tổng hợp: cơ sở dữ liệu cửa hàng nhỏ

Xây dựng schema gồm `customers`, `products`, `orders`, `order_items` và `inventory`. Tự xác định khóa chính, khóa ngoại, ràng buộc duy nhất, kiểu dữ liệu và index dựa trên yêu cầu nghiệp vụ. Sau đó hoàn thành các việc sau:

1. Thêm khách hàng, sản phẩm và đơn hàng; kiểm tra trường hợp email trùng và khóa ngoại không hợp lệ.
2. Viết truy vấn lấy lịch sử mua hàng của một khách hàng, danh sách sản phẩm trong một đơn và doanh thu theo ngày.
3. Kết nối schema từ một ứng dụng nhỏ bằng prepared statement và tài khoản chỉ có quyền cần thiết.
4. Dùng `EXPLAIN` kiểm tra truy vấn lịch sử mua hàng; đề xuất index dựa trên điều kiện lọc và thứ tự sắp xếp, rồi đo lại.
5. Viết luồng tạo đơn trong transaction: kiểm tra và giảm tồn kho, ghi đơn hàng và các dòng hàng; rollback khi không đủ hàng.
6. Mở hai phiên kết nối để thử cập nhật cùng một sản phẩm, quan sát việc chờ khóa hoặc deadlock và kiểm tra kết quả cuối cùng.
7. Dump schema, khôi phục sang một schema thử nghiệm và xác minh dữ liệu bằng truy vấn nghiệp vụ.

Bạn hoàn thành bài tập khi có thể giải thích vì sao chọn từng kiểu dữ liệu và index, chứng minh ràng buộc ngăn dữ liệu sai, trình bày kế hoạch thực thi của truy vấn chính, mô tả cách transaction bảo vệ tồn kho và khôi phục thành công từ bản backup.

## 10. Những nguyên tắc cần giữ khi làm việc với MySQL

- Thiết kế từ quy tắc nghiệp vụ và quan hệ dữ liệu; dùng khóa và constraint để bảo vệ tính toàn vẹn.
- Chọn kiểu dữ liệu đủ chính xác và phù hợp; dùng `DECIMAL` cho tiền, xác định rõ múi giờ và charset.
- Tham số hóa dữ liệu đầu vào; không nối chuỗi tùy tiện để tạo SQL.
- Đo và đọc `EXPLAIN` trước khi thay đổi index hoặc viết lại truy vấn.
- Giữ transaction ngắn, xác định rõ điều kiện commit/rollback và xử lý deadlock có giới hạn.
- Cấp quyền tối thiểu cho từng vai trò; quản lý secret và kết nối an toàn.
- Xem backup là một quy trình gồm tạo bản sao, bảo quản, kiểm tra và diễn tập restore.
- Theo dõi hệ thống bằng số liệu và bằng chứng; ghi lại nguyên nhân gốc sau sự cố.

Đi theo trình tự này giúp bạn xây nền tảng MySQL từ thao tác dữ liệu cơ bản tới khả năng phát triển ứng dụng và vận hành hệ thống quan hệ có độ tin cậy. Khi gặp một vấn đề thực tế, hãy quay lại đúng lớp liên quan: mô hình dữ liệu, câu SQL, kế hoạch thực thi, transaction, quyền truy cập hoặc quy trình vận hành; sau đó xác minh kết quả bằng dữ liệu và phép đo.
