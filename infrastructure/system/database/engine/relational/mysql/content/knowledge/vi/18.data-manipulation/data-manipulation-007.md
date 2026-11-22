# DELETE một bảng, nhiều bảng và xóa dữ liệu cha con

Trong MySQL, `DELETE` dùng để xóa các dòng dữ liệu đang lưu trong bảng. Câu lệnh có thể nhắm đến một bảng, dùng `JOIN` để xác định dòng cần xóa, hoặc xóa dữ liệu ở nhiều bảng trong cùng một câu lệnh. Khi các bảng liên kết bằng khóa ngoại, kết quả còn phụ thuộc vào quy tắc `ON DELETE` được khai báo trong quan hệ cha con.

Bài học này thuộc phần **Thay đổi dữ liệu** của MySQL. Sau khi hoàn thành, bạn có thể chọn đúng cú pháp `DELETE`, dự đoán ảnh hưởng lên bảng liên quan, kiểm tra dữ liệu trước khi xóa và dùng transaction để kiểm soát thao tác có rủi ro cao.

## 1. Cú pháp DELETE một bảng

Cú pháp cơ bản:

```sql
DELETE FROM ten_bang
WHERE dieu_kien;
```

`WHERE` xác định những dòng bị xóa. Nếu bỏ `WHERE`, MySQL xóa toàn bộ dòng trong bảng nhưng vẫn giữ cấu trúc bảng, các cột, index và constraint.

Ví dụ, xóa một nhân viên theo khóa chính:

```sql
DELETE FROM employees
WHERE employee_id = 105;
```

Xóa nhiều nhân viên theo điều kiện:

```sql
DELETE FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01';
```

Các điều kiện trong `WHERE` tuân theo quy tắc biểu thức của SQL. Có thể kết hợp `AND`, `OR`, `IN`, `BETWEEN`, `LIKE`, điều kiện trên ngày giờ hoặc subquery. Hãy dùng dấu ngoặc khi kết hợp `AND` và `OR` để biểu đạt rõ thứ tự logic.

```sql
DELETE FROM employees
WHERE status = 'INACTIVE'
  AND (department_id = 10 OR department_id = 20);
```

### Xem trước những dòng sẽ bị xóa

Trước khi chạy `DELETE`, hãy chạy một câu `SELECT` với cùng điều kiện. Kết quả giúp xác nhận phạm vi dữ liệu và phát hiện lỗi như thiếu điều kiện, sai khóa hoặc nhầm mốc thời gian.

```sql
SELECT employee_id, full_name, status, hired_at
FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01'
ORDER BY hired_at, employee_id;
```

Nếu chỉ cần biết số dòng dự kiến bị ảnh hưởng, dùng `COUNT(*)` với cùng điều kiện:

```sql
SELECT COUNT(*) AS rows_to_delete
FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01';
```

Sau khi đã xác nhận kết quả, mới thực hiện câu `DELETE` tương ứng. Không nên dựa vào việc ứng dụng hiển thị ít dòng hoặc màn hình đang lọc dữ liệu để suy ra phạm vi xóa ở máy chủ.

### ORDER BY và LIMIT khi xóa từng đợt

Với cú pháp xóa một bảng, MySQL cho phép dùng `ORDER BY` và `LIMIT`. Điều này hữu ích khi dọn dữ liệu cũ theo từng đợt để giảm lượng khóa và undo log phát sinh trong một lần chạy.

```sql
DELETE FROM api_requests
WHERE created_at < '2025-01-01'
ORDER BY created_at, request_id
LIMIT 1000;
```

Câu lệnh trên xóa tối đa 1.000 dòng cũ nhất thỏa điều kiện. Khóa phụ `request_id` làm thứ tự ổn định hơn khi nhiều dòng có cùng `created_at`. Có thể chạy lại theo từng đợt cho đến khi không còn dòng phù hợp; trong quy trình vận hành, nên kiểm tra số dòng mỗi đợt và commit theo lô phù hợp.

`LIMIT` không thay thế cho `WHERE`: nếu điều kiện bị thiếu hoặc sai, câu lệnh vẫn có thể xóa nhầm một nhóm dòng. Khi cần xóa nhiều dữ liệu, hãy xác định điều kiện rõ ràng và dùng index phù hợp cho cột lọc hoặc cột sắp xếp.

## 2. DELETE kết hợp JOIN để chọn dòng cần xóa

Đôi khi điều kiện xóa nằm ở bảng khác. Cú pháp `DELETE ... FROM ... JOIN` cho phép nối bảng để tìm dòng mục tiêu. Ví dụ, chỉ xóa nhân viên thuộc phòng ban đã lưu trữ:

```sql
DELETE e
FROM employees AS e
JOIN departments AS d
  ON d.department_id = e.department_id
WHERE d.is_archived = 1;
```

`e` là alias của `employees`; phần `DELETE e` chỉ định bảng nhận thao tác xóa. Bảng `departments` tham gia phép nối để lọc, nhưng không bị xóa. Đây là cú pháp nhiều bảng theo cách xác định mục tiêu, dù danh sách mục tiêu chỉ có một bảng.

Hãy xem trước chính phép nối đó bằng `SELECT`:

```sql
SELECT e.employee_id, e.full_name, d.department_name
FROM employees AS e
JOIN departments AS d
  ON d.department_id = e.department_id
WHERE d.is_archived = 1;
```

Một ứng dụng khác là xóa sản phẩm đã ngừng kinh doanh và không còn xuất hiện trong dòng hàng nào. Dùng `LEFT JOIN` để tìm sản phẩm không có dòng khớp ở `order_items`:

```sql
DELETE p
FROM products AS p
LEFT JOIN order_items AS oi
  ON oi.product_id = p.product_id
WHERE oi.item_id IS NULL
  AND p.is_discontinued = 1;
```

Điều kiện `oi.item_id IS NULL` chọn những sản phẩm không có bản ghi liên quan. Câu lệnh chỉ xóa từ `products`; `order_items` được dùng để xác định sản phẩm đủ điều kiện.

Khi dùng `JOIN`, cần kiểm tra chính xác điều kiện nối. Một điều kiện nối thiếu hoặc nối nhầm khóa có thể mở rộng tập dòng mục tiêu ngoài dự kiến. Nếu một bảng có nhiều dòng khớp với một dòng ở bảng kia, hãy kiểm tra kết quả `SELECT` trước khi xóa để hiểu đầy đủ phạm vi tác động.

## 3. Xóa dữ liệu ở nhiều bảng trong một câu lệnh

MySQL hỗ trợ multi-table `DELETE`, trong đó danh sách alias ngay sau `DELETE` chỉ ra các bảng sẽ bị xóa dòng. Ví dụ dưới đây xóa tài khoản đã đóng và các phiên đăng nhập cũ tương ứng:

```sql
DELETE u, s
FROM users AS u
JOIN sessions AS s
  ON s.user_id = u.user_id
WHERE u.account_status = 'CLOSED'
  AND s.last_seen_at < '2025-01-01';
```

Trong ví dụ này, các dòng khớp ở cả `users` và `sessions` đều là mục tiêu xóa. Nếu chỉ viết `DELETE s`, MySQL chỉ xóa các dòng ở `sessions`; các dòng `users` vẫn còn. Cú pháp multi-table cũng có dạng `DELETE FROM ... USING ...`, nhưng dạng `DELETE alias_list FROM ... JOIN ...` thường dễ đọc khi cần chỉ rõ bảng mục tiêu.

Một số điểm cần nhớ:

- Multi-table `DELETE` không hỗ trợ `ORDER BY` hoặc `LIMIT`. Nếu cần chia nhỏ dữ liệu, hãy xác định tập khóa cần xóa theo từng lô rồi thực hiện thao tác phù hợp.
- Danh sách sau `DELETE` phải chứa đúng alias của những bảng muốn xóa. Bảng chỉ xuất hiện trong `FROM` hoặc `JOIN` sẽ không tự động bị xóa.
- Ví dụ trên giả định quan hệ giữa hai bảng cho phép xóa đồng thời. Nếu có khóa ngoại ràng buộc thứ tự xóa, hãy thiết kế thao tác theo quy tắc khóa ngoại; với InnoDB, thứ tự mà optimizer chọn cho multi-table `DELETE` có thể xung đột với thứ tự cha con và khiến câu lệnh thất bại, được rollback.

Nếu có khóa ngoại, thường nên dùng `ON DELETE CASCADE` khi nghiệp vụ cho phép hoặc xóa bảng con trước bảng cha trong cùng một transaction. Phần tiếp theo trình bày cách chọn cách xử lý đó.

## 4. Xóa dữ liệu cha con bằng khóa ngoại

Giả sử hệ thống bán hàng có ba bảng: `customers` là bảng cha, `orders` là bảng con của `customers`, và `order_items` là bảng con của `orders`. Quan hệ được khai báo bằng khóa ngoại trong InnoDB:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_orders_customer_id (customer_id),
    CONSTRAINT fk_orders_customer
      FOREIGN KEY (customer_id)
      REFERENCES customers (customer_id)
      ON DELETE CASCADE
) ENGINE = InnoDB;

CREATE TABLE order_items (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(120) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (item_id),
    KEY ix_order_items_order_id (order_id),
    CONSTRAINT fk_items_order
      FOREIGN KEY (order_id)
      REFERENCES orders (order_id)
      ON DELETE CASCADE
) ENGINE = InnoDB;
```

Với hai khóa ngoại dùng `ON DELETE CASCADE`, xóa một khách hàng sẽ kéo theo các đơn hàng của khách hàng đó; xóa từng đơn hàng lại kéo theo các dòng hàng của đơn hàng đó:

```sql
DELETE FROM customers
WHERE customer_id = 42;
```

MySQL thực hiện các hành động cascade theo chuỗi quan hệ đã khai báo. Không cần viết thêm câu `DELETE` riêng cho `orders` và `order_items`. Cơ chế này phù hợp khi dữ liệu con không có ý nghĩa độc lập sau khi dữ liệu cha bị xóa, ví dụ các dòng chi tiết của một đơn hàng đã bị xóa theo chính sách lưu trữ.

### Các lựa chọn ON DELETE

Quy tắc `ON DELETE` quyết định điều gì xảy ra với dòng con khi dòng cha bị xóa:

| Quy tắc | Hành vi |
| --- | --- |
| `RESTRICT` | Từ chối xóa dòng cha nếu vẫn còn dòng con tham chiếu. Đây là hành vi mặc định khi không chỉ định quy tắc xóa trong InnoDB. |
| `NO ACTION` | Với InnoDB, có hành vi tương đương `RESTRICT`. |
| `CASCADE` | Tự động xóa các dòng con tham chiếu; hành động có thể tiếp tục qua các quan hệ con nhiều cấp. |
| `SET NULL` | Đặt cột khóa ngoại ở dòng con thành `NULL`; cột đó phải cho phép `NULL`. |

Chọn `CASCADE` theo quy tắc nghiệp vụ, không chỉ vì nó làm câu lệnh ngắn hơn. Một thao tác xóa ở bảng cha có thể xóa số lượng lớn dòng ở nhiều bảng. Với dữ liệu cần lưu để kiểm toán, đối soát hoặc đáp ứng thời hạn lưu trữ, có thể phải giữ bản ghi, chuyển trạng thái hoặc lưu trữ dữ liệu thay vì cascade.

### Khi khóa ngoại dùng RESTRICT

Nếu khóa ngoại không cho phép cascade, MySQL từ chối xóa dòng cha khi vẫn còn dòng con tham chiếu. Khi đó, xóa theo thứ tự từ bảng con sâu nhất lên bảng cha. Ví dụ, với quan hệ `order_items` → `orders` → `customers` dùng `RESTRICT`:

```sql
START TRANSACTION;

DELETE oi
FROM order_items AS oi
JOIN orders AS o
  ON o.order_id = oi.order_id
WHERE o.customer_id = 42;

DELETE FROM orders
WHERE customer_id = 42;

DELETE FROM customers
WHERE customer_id = 42;

COMMIT;
```

Câu lệnh đầu xóa các dòng hàng, câu lệnh thứ hai xóa đơn hàng đã hết dòng con, và câu lệnh cuối cùng xóa khách hàng. Nếu một bước gặp lỗi hoặc kết quả kiểm tra không đúng, chạy `ROLLBACK` thay cho `COMMIT` để hoàn tác các thay đổi trong transaction. Trình tự này cũng giúp người đọc nhìn thấy rõ dữ liệu nào sẽ bị xóa ở từng cấp.

Không nên tắt `FOREIGN_KEY_CHECKS` chỉ để ép xóa dữ liệu cha. Tắt kiểm tra khóa ngoại không thực hiện cascade; thao tác đó có thể để lại dòng con mồ côi. Khi bật kiểm tra trở lại, MySQL không tự quét và xác minh lại toàn bộ dữ liệu cũ để sửa các quan hệ đã vi phạm.

## 5. Dùng transaction để kiểm soát thao tác xóa

Với bảng InnoDB, `DELETE` là thao tác có thể rollback khi nằm trong transaction. Điều này cho phép kiểm tra phạm vi và kết quả trước khi xác nhận:

```sql
START TRANSACTION;

DELETE FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01';

SELECT COUNT(*) AS remaining_rows
FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01';

-- Nếu kết quả đúng:
COMMIT;

-- Nếu phát hiện xóa nhầm, dùng ROLLBACK thay cho COMMIT.
```

Trong ví dụ thực tế, hãy chạy câu `SELECT` xem trước ngay sau `START TRANSACTION` và trước `DELETE`; câu `SELECT` sau `DELETE` dùng để xác minh các dòng thỏa điều kiện còn lại. Chỉ `COMMIT` khi kết quả đúng với dự kiến. Nếu chế độ autocommit đang bật và không mở transaction tường minh, mỗi câu lệnh thường được commit riêng, nên không thể dùng `ROLLBACK` sau khi câu `DELETE` đã commit.

Transaction không thay thế cho backup hoặc quy trình phê duyệt xóa dữ liệu quan trọng. Nó cũng chỉ bảo đảm rollback cho các thay đổi trên storage engine có hỗ trợ transaction, chẳng hạn InnoDB. Hãy xác nhận engine của các bảng trước khi dựa vào khả năng rollback.

## 6. Hiệu năng và vận hành khi xóa nhiều dữ liệu

Một câu `DELETE` lớn có thể giữ khóa lâu, tạo nhiều undo log, làm tăng tải I/O và ảnh hưởng các giao dịch khác. Khi dọn dữ liệu lịch sử, cân nhắc các điểm sau:

1. **Lọc bằng điều kiện có chủ đích.** Dùng khóa chính, khoảng thời gian hoặc trạng thái đã xác minh; tránh quét và xóa toàn bảng ngoài kế hoạch.
2. **Đặt index cho điều kiện và phép nối.** Index trên cột lọc và cột nối giúp MySQL tìm dòng mục tiêu hiệu quả hơn. InnoDB yêu cầu index phù hợp cho khóa ngoại và có thể tự tạo index phía bảng con nếu chưa có index thích hợp.
3. **Chia lô khi xóa lượng lớn.** Với single-table `DELETE`, có thể kết hợp `ORDER BY` và `LIMIT`, rồi kiểm tra và commit từng lô. Chọn kích thước lô dựa trên tải thực tế và thời gian khóa.
4. **Theo dõi quan hệ phụ thuộc.** Kiểm tra các khóa ngoại, cascade và bảng có trigger trước khi xóa. Một câu lệnh xóa ở bảng cha có thể gây ra nhiều thay đổi gián tiếp.
5. **Kiểm tra môi trường và khả năng khôi phục.** Xác nhận máy chủ, schema, điều kiện lọc và backup trước thao tác ảnh hưởng dữ liệu quan trọng.

Không dùng `LIMIT` một cách tùy tiện để thay thế kế hoạch xóa theo lô. Nếu không có `ORDER BY`, nhóm dòng bị xóa ở mỗi lần chạy có thể không theo thứ tự nghiệp vụ mong muốn. Với multi-table `DELETE`, do không có `ORDER BY` và `LIMIT`, hãy thiết kế bước chọn khóa mục tiêu riêng nếu cần kiểm soát từng lô.

## 7. Phân biệt DELETE, TRUNCATE và DROP

Ba lệnh đều có thể xuất hiện trong quy trình dọn dữ liệu nhưng tác động khác nhau:

| Lệnh | Tác động | Điều cần nhớ |
| --- | --- | --- |
| `DELETE FROM t WHERE ...` | Xóa các dòng thỏa điều kiện; không có `WHERE` thì xóa mọi dòng. | Là DML; với InnoDB có thể rollback trong transaction; kích hoạt trigger `DELETE`; không đặt lại bộ đếm `AUTO_INCREMENT`. |
| `TRUNCATE TABLE t` | Xóa toàn bộ dữ liệu trong bảng. | Không có `WHERE`; là DDL và gây implicit commit; đặt lại `AUTO_INCREMENT`; không kích hoạt trigger `DELETE`; không thể truncate bảng đang được khóa ngoại từ bảng khác tham chiếu. |
| `DROP TABLE t` | Xóa cả bảng và cấu trúc của bảng. | Các cột, index và định nghĩa bảng bị loại bỏ; đây không phải lựa chọn để chỉ xóa dữ liệu. |

Nếu cần xóa có điều kiện, cần kiểm soát transaction hoặc phải xử lý quan hệ cha con theo từng dòng, dùng `DELETE`. Chỉ cân nhắc `TRUNCATE` khi chủ đích là làm rỗng toàn bộ bảng và đã kiểm tra các ràng buộc liên quan.

## 8. Quy trình thực hành an toàn

Trước một thao tác xóa trên môi trường dùng chung hoặc production, có thể áp dụng trình tự sau:

1. Xác nhận đúng máy chủ, database và bảng đích.
2. Viết điều kiện `WHERE` hoặc phép `JOIN` đầy đủ; không chạy ngay câu lệnh xóa đầu tiên.
3. Chuyển điều kiện đó thành `SELECT` để xem các khóa và số dòng bị ảnh hưởng.
4. Kiểm tra khóa ngoại, hành động `ON DELETE`, trigger và các bảng liên quan.
5. Mở transaction nếu engine hỗ trợ; thực hiện xóa, kiểm tra kết quả rồi mới `COMMIT`.
6. Với dữ liệu lớn, xóa theo lô và theo dõi tải hệ thống; bảo đảm có phương án khôi phục phù hợp.

Các lỗi thường gặp là bỏ quên `WHERE`, dùng `JOIN` sai khóa, nghĩ rằng multi-table `DELETE` tự xóa mọi bảng tham gia phép nối, xóa cha trước khi xử lý con trong quan hệ `RESTRICT`, hoặc tắt kiểm tra khóa ngoại để vượt qua lỗi. Khi gặp lỗi ràng buộc, hãy đọc tên constraint trong thông báo lỗi và kiểm tra dòng con đang tham chiếu trước khi quyết định thay đổi chính sách xóa.

`DELETE` là công cụ mạnh để quản lý vòng đời dữ liệu. Câu lệnh đúng phải xác định được chính xác dòng mục tiêu, tuân thủ quan hệ khóa ngoại và có cách xác minh hoặc khôi phục phù hợp với mức độ quan trọng của dữ liệu.
