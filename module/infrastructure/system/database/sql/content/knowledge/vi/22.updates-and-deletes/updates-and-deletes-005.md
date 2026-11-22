# DELETE có điều kiện và kiểm tra hàng bị ảnh hưởng

Xóa dữ liệu là một trong những thao tác SQL cần được kiểm soát chặt chẽ nhất. Khi chạy `DELETE`, cơ sở dữ liệu có thể xóa những bản ghi đang được ứng dụng sử dụng, kích hoạt ràng buộc khóa ngoại, xóa dây chuyền các hàng liên quan hoặc làm thay đổi kết quả báo cáo. Một điều kiện `WHERE` viết thiếu, hoặc một dấu so sánh ngày viết sai, có thể khiến số hàng bị xóa lớn hơn dự kiến.

Vì vậy, bài toán **“DELETE có điều kiện và kiểm tra hàng bị ảnh hưởng”** không chỉ là ghi nhớ cú pháp `DELETE FROM ... WHERE ...`. Ta cần biết cách:

- Xác định **chính xác tập hàng** được phép xóa theo điều kiện nghiệp vụ.
- Dùng `SELECT` xem trước và đếm ứng viên trước khi thao tác.
- Thực hiện thử trong **giao dịch**, quan sát hàng thực sự bị xóa và sử dụng `ROLLBACK` khi cần.
- Hiểu sự khác nhau giữa **số hàng khớp điều kiện**, **số hàng thực sự bị xóa từ bảng đích** và **các hàng liên quan bị ảnh hưởng do ràng buộc hoặc trigger**.
- Sử dụng `RETURNING`, `OUTPUT`, số hàng bị ảnh hưởng do driver trả về hoặc hàm/biến đặc thù của hệ quản trị.
- Xử lý `AND`/`OR`, `NULL`, truy vấn con, khóa ngoại, xóa theo lô và dữ liệu bị thay đổi đồng thời.
- Biết khi nào cần **xóa cứng**, **xóa mềm**, hoặc hoàn toàn **không nên xóa**.

Ví dụ chính chạy trên **PostgreSQL**, dùng dữ liệu thực hành có thể tạo lại. Phần sau đối chiếu với SQL Server, MySQL, SQLite và Oracle, vì các hệ quản trị không có cú pháp hay cơ chế báo số hàng thay đổi hoàn toàn giống nhau.

> **Nguyên tắc xuyên suốt:** Chỉ chạy `DELETE` sau khi xác nhận rõ bảng đích, quy tắc `WHERE`, danh sách khóa sẽ bị xóa và cách kiểm tra kết quả. Những lệnh trong bài dành cho database thực hành riêng, không thực hiện trực tiếp trên dữ liệu sản xuất.

## 1. DELETE có điều kiện hoạt động thế nào?

Cú pháp cơ bản:

```sql
DELETE FROM table_name
WHERE condition;
```

SQL đánh giá điều kiện `WHERE` trên những hàng của **bảng đích**. Hàng có điều kiện là `TRUE` sẽ là đối tượng xóa; hàng có `FALSE` hoặc `UNKNOWN` không được chọn theo điều kiện đó. Nếu bảng có trigger, khóa ngoại hoặc quy tắc bổ sung, việc thực thi còn phải tuân theo các cơ chế ấy.

Ví dụ:

```sql
DELETE FROM orders_demo
WHERE status = 'CANCELLED';
```

Lệnh này yêu cầu xóa **tất cả đơn có trạng thái `CANCELLED`** trong bảng `orders_demo`, không quan tâm thời gian đơn hay khách hàng. Nếu chỉ muốn xóa đơn đã hủy **trước một mốc ngày**, cần thêm điều kiện:

```sql
DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01';
```

Hai điều kiện nối bởi `AND` nghĩa là một hàng phải **đồng thời** có trạng thái `CANCELLED` **và** ngày đơn nhỏ hơn ngày 01/07/2025 mới được chọn.

### 1.1. WHERE quyết định phạm vi xóa

| Câu lệnh | Ý nghĩa |
|---|---|
| `DELETE FROM orders_demo WHERE order_id = 103` | Xóa đơn có ID 103 nếu tồn tại |
| `DELETE FROM orders_demo WHERE customer_id = 2` | Xóa mọi đơn của khách 2 |
| `DELETE FROM orders_demo WHERE status = 'CANCELLED'` | Xóa mọi đơn đã hủy |
| `DELETE FROM orders_demo WHERE status = 'CANCELLED' AND ordered_on < DATE '2025-07-01'` | Chỉ xóa đơn đã hủy trước mốc |
| `DELETE FROM orders_demo` | **Xóa tất cả hàng** của bảng, nếu không bị ràng buộc khác ngăn cản |

**Cảnh báo:** `DELETE FROM orders_demo;` không có `WHERE`. Nếu thực thi thành công, câu này sẽ xóa toàn bộ hàng của bảng đích. Đây **không** phải cách viết tương đương với “không có hàng nào cần xóa”. Trong bài học, mọi ví dụ xóa dữ liệu nghiệp vụ đều kèm điều kiện cụ thể.

### 1.2. DELETE khác SELECT và UPDATE

- `SELECT` chỉ đọc và trả hàng thỏa điều kiện; bản thân nó không xóa.
- `UPDATE ... SET ... WHERE ...` sửa giá trị của hàng đang tồn tại.
- `DELETE FROM ... WHERE ...` loại các hàng thỏa điều kiện khỏi bảng.

Không nên dùng `DELETE` nếu nghiệp vụ chỉ cần ẩn bản ghi khỏi màn hình hoặc đổi trạng thái bản ghi. Trường hợp đó có thể phù hợp hơn với `UPDATE` hoặc **xóa mềm** (*soft delete*), được giải thích ở mục sau.

## 2. Dữ liệu mẫu xuyên suốt

Ta tạo ba bảng:

1. `customers_demo`: danh sách khách hàng.
2. `orders_demo`: các đơn hàng; đây sẽ là **bảng đích** của những ví dụ `DELETE` chính.
3. `order_notes_demo`: ghi chú của đơn; có quan hệ khóa ngoại `ON DELETE CASCADE` để quan sát tác động xóa dây chuyền.

Cấu trúc:

```text
customers_demo
  customer_id (PK)
       |
       | 1 khách - nhiều đơn
       v
orders_demo
  order_id (PK)
  customer_id (FK)
       |
       | 1 đơn - nhiều ghi chú
       v
order_notes_demo
  note_id (PK)
  order_id (FK ON DELETE CASCADE)
```

### 2.1. Tạo bảng trong PostgreSQL

```sql
CREATE TABLE customers_demo (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE orders_demo (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES customers_demo(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    ordered_on DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0)
);

CREATE TABLE order_notes_demo (
    note_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES orders_demo(order_id)
        ON DELETE CASCADE,
    note_text TEXT NOT NULL
);
```

Các ràng buộc `PRIMARY KEY`, `NOT NULL` và `CHECK` giúp dữ liệu mẫu có khóa định danh rõ và trạng thái hợp lệ. `order_notes_demo.order_id` tham chiếu `orders_demo.order_id`: khi một đơn bị xóa thành công, PostgreSQL tự xóa những ghi chú tham chiếu đơn đó vì `ON DELETE CASCADE`.

**Điểm quan trọng:** không phải mọi khóa ngoại đều có `ON DELETE CASCADE`. Nếu dùng `RESTRICT` hoặc `NO ACTION`, việc xóa hàng cha khi còn hàng con tham chiếu có thể bị từ chối. Ta sẽ so sánh ở mục 9.

### 2.2. Nạp khách hàng

```sql
INSERT INTO customers_demo (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung'),
    (5, 'Em');
```

### 2.3. Nạp đơn hàng

```sql
INSERT INTO orders_demo
    (order_id, customer_id, status, ordered_on, amount)
VALUES
    (101, 1, 'NEW',       DATE '2025-06-01', 100.00),
    (102, 1, 'PAID',      DATE '2025-06-02', 120.00),
    (103, 2, 'CANCELLED', DATE '2025-01-05',  80.00),
    (104, 2, 'CANCELLED', DATE '2025-06-25',  70.00),
    (105, 3, 'CANCELLED', DATE '2025-07-01',  50.00),
    (106, 3, 'PAID',      DATE '2025-05-10', 200.00),
    (107, 4, 'NEW',       DATE '2025-06-15',  90.00),
    (108, 4, 'CANCELLED', DATE '2025-03-01',  30.00),
    (109, 5, 'CANCELLED', DATE '2025-06-30',  40.00),
    (110, 5, 'CANCELLED', DATE '2025-04-12',  60.00),
    (111, 2, 'NEW',       DATE '2025-08-01', 110.00),
    (112, 4, 'CANCELLED', DATE '2025-01-15',  20.00);
```

### 2.4. Nạp ghi chú

```sql
INSERT INTO order_notes_demo (note_id, order_id, note_text)
VALUES
    (301, 103, 'Khách yêu cầu hủy'),
    (302, 103, 'Đã xác nhận hủy'),
    (303, 110, 'Hủy trước khi đóng gói'),
    (304, 105, 'Đơn hủy tại ngày mốc');
```

### 2.5. Đọc dữ liệu nguồn

| order_id | customer_id | status | ordered_on | amount | Số ghi chú |
|---:|---:|---|---|---:|---:|
| 101 | 1 | NEW | 2025-06-01 | 100.00 | 0 |
| 102 | 1 | PAID | 2025-06-02 | 120.00 | 0 |
| 103 | 2 | CANCELLED | 2025-01-05 | 80.00 | 2 |
| 104 | 2 | CANCELLED | 2025-06-25 | 70.00 | 0 |
| 105 | 3 | CANCELLED | 2025-07-01 | 50.00 | 1 |
| 106 | 3 | PAID | 2025-05-10 | 200.00 | 0 |
| 107 | 4 | NEW | 2025-06-15 | 90.00 | 0 |
| 108 | 4 | CANCELLED | 2025-03-01 | 30.00 | 0 |
| 109 | 5 | CANCELLED | 2025-06-30 | 40.00 | 0 |
| 110 | 5 | CANCELLED | 2025-04-12 | 60.00 | 1 |
| 111 | 2 | NEW | 2025-08-01 | 110.00 | 0 |
| 112 | 4 | CANCELLED | 2025-01-15 | 20.00 | 0 |

Tổng ban đầu:

- `orders_demo` có **12 hàng**.
- `order_notes_demo` có **4 hàng**.
- Có **7 đơn `CANCELLED`**: 103, 104, 105, 108, 109, 110, 112.
- Trong số đó, **6 đơn được hủy trước 01/07/2025**: **103, 104, 108, 109, 110, 112**.
- Đơn **105** bị hủy **đúng ngày 01/07/2025**, nên không thuộc điều kiện `ordered_on < DATE '2025-07-01'`.
- Các đơn 103 và 110 có tổng **3 ghi chú**, sẽ bị xóa dây chuyền nếu hai đơn cha bị xóa.

Những con số này là **kết quả kỳ vọng cho bài thực hành**, giúp ta kiểm tra số hàng và danh tính các hàng bị ảnh hưởng sau `DELETE`.

## 3. Mẫu DELETE có điều kiện với WHERE

Giả sử chính sách minh họa là:

> Chỉ xóa những đơn đã hủy có ngày đặt **trước ngày 01/07/2025**; giữ lại mọi đơn khác.

Câu lệnh:

```sql
DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01';
```

Trong dữ liệu mẫu, **6 đơn khớp**: 103, 104, 108, 109, 110, 112.

### 3.1. Đọc điều kiện theo từng phần

```sql
WHERE status = 'CANCELLED'
```

chỉ giữ các đơn đã hủy. Trên dữ liệu ban đầu, có 7 đơn.

```sql
AND ordered_on < DATE '2025-07-01'
```

giữ những đơn trước mốc ngày, nên đơn 105 đúng ngày mốc bị loại. Tập cuối còn 6.

### 3.2. Dấu < khác <=

So sánh:

| Điều kiện ngày | Đơn 105 có ngày 01/07/2025 | Số đơn `CANCELLED` được chọn |
|---|---|---:|
| `ordered_on < DATE '2025-07-01'` | Không | 6 |
| `ordered_on <= DATE '2025-07-01'` | Có | 7 |

Chỉ một ký tự `=` có thể thay đổi phạm vi xóa. Khi dùng mốc ngày, hãy ghi rõ chính sách là **“trước”**, **“đến hết ngày”** hay **“từ ngày”**.

Nếu cột chứa **ngày và giờ** (ví dụ `TIMESTAMP`), muốn xóa toàn bộ dữ liệu **trước tháng 7** thường nên viết khoảng:

```sql
WHERE ordered_at < TIMESTAMP '2025-07-01 00:00:00'
```

thay vì chỉ so bằng một ngày hoặc dựa vào thời điểm `23:59:59` có thể bỏ sót phần giây. Với hệ thống đa múi giờ, phải xác định mốc thời gian theo múi giờ nghiệp vụ.

### 3.3. AND và OR cần dấu ngoặc

Giả sử muốn xóa **đơn đã hủy trước tháng 7** hoặc **đơn cụ thể 111**:

```sql
WHERE
    (
        status = 'CANCELLED'
        AND ordered_on < DATE '2025-07-01'
    )
    OR order_id = 111
```

Kết quả là 6 đơn cũ đã hủy **cộng thêm 111**, tổng 7. Nếu dùng:

```sql
WHERE
    status = 'CANCELLED'
    AND (
        ordered_on < DATE '2025-07-01'
        OR order_id = 111
    )
```

thì đơn 111 vẫn **không** được chọn vì trạng thái là `NEW`, không phải `CANCELLED`. Kết quả trở về 6 đơn.

SQL ưu tiên `AND` trước `OR` khi không có ngoặc. Đối với thao tác xóa, nên dùng **dấu ngoặc diễn đạt ý định rõ ràng**, không để người duy trì suy luận thứ tự ưu tiên.

### 3.4. Điều kiện theo khóa là cách khoanh vùng chặt

Nếu biết chính xác mã bản ghi cần xóa:

```sql
DELETE FROM orders_demo
WHERE order_id = 103;
```

Vì `order_id` là khóa chính, lệnh này xóa **tối đa một hàng trong bảng `orders_demo`**. Nếu không có ID 103, nó xóa 0 hàng.

Lọc theo khóa chính thường an toàn hơn một điều kiện quá rộng, nhưng vẫn phải xác minh rằng **ID đó thuộc đúng đối tượng nghiệp vụ** và không bị đọc nhầm giữa môi trường thử nghiệm với môi trường thật.

## 4. Xem trước đúng tập hàng trước khi DELETE

Trước khi xóa, hãy đổi **chỉ phần lệnh thao tác** thành `SELECT` nhưng giữ nguyên điều kiện nghiệp vụ.

### 4.1. Liệt kê hàng dự kiến xóa

```sql
SELECT
    order_id,
    customer_id,
    status,
    ordered_on,
    amount
FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01'
ORDER BY ordered_on, order_id;
```

Kết quả:

| order_id | customer_id | status | ordered_on |
|---:|---:|---|---|
| 103 | 2 | CANCELLED | 2025-01-05 |
| 112 | 4 | CANCELLED | 2025-01-15 |
| 108 | 4 | CANCELLED | 2025-03-01 |
| 110 | 5 | CANCELLED | 2025-04-12 |
| 104 | 2 | CANCELLED | 2025-06-25 |
| 109 | 5 | CANCELLED | 2025-06-30 |

Quan sát danh sách **khóa chính**, không chỉ số lượng. Một điều kiện có thể vô tình chọn **6 hàng sai** nhưng vẫn đúng kỳ vọng về số đếm. Danh sách ID giúp phát hiện sai phạm vi.

### 4.2. Đếm trước khi xóa

```sql
SELECT COUNT(*) AS candidate_count
FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01';
-- 6
```

`COUNT(*)` là số **hàng ứng viên tại thời điểm truy vấn đọc**. Chưa có hàng nào bị xóa vì câu này chỉ `SELECT`.

### 4.3. Không coi SELECT xem trước là bảo đảm tuyệt đối

Nếu một phiên khác đang thêm, sửa hoặc xóa đơn, tập ứng viên có thể **thay đổi giữa lúc xem trước và lúc chạy `DELETE`**. Trên PostgreSQL ở mức cô lập `READ COMMITTED` thông dụng, hai câu lệnh riêng có thể quan sát những snapshot khác nhau.

Vì thế quy trình tốt bao gồm:

1. Dùng `SELECT` để kiểm tra điều kiện và tập ứng viên.
2. Dùng **transaction** khi tiến hành xóa có rủi ro.
3. Kiểm tra **kết quả thực sự của `DELETE`**, không chỉ tin vào số đếm `SELECT` trước đó.
4. Với nghiệp vụ yêu cầu xóa **đúng một tập khóa đã chốt**, dùng chiến lược khóa/snapshot hoặc bảng khóa ứng viên phù hợp và kiểm tra lại dưới điều kiện đồng thời thực tế.

## 5. Thực hành an toàn bằng BEGIN, RETURNING và ROLLBACK

PostgreSQL hỗ trợ giao dịch tường minh:

```sql
BEGIN;

-- SELECT, DELETE, SELECT để quan sát trong cùng giao dịch.

ROLLBACK;
```

Khi `ROLLBACK` được thực hiện và giao dịch chưa được `COMMIT`, các thay đổi dữ liệu của giao dịch sẽ bị hủy. Nhờ đó, ta có thể thử thao tác xóa trên bộ dữ liệu mẫu rồi đưa nó trở về trạng thái ban đầu.

### 5.1. Xóa và trả về các hàng đã xóa

```sql
BEGIN;

DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01'
RETURNING
    order_id,
    customer_id,
    status,
    ordered_on,
    amount;

ROLLBACK;
```

`RETURNING` của PostgreSQL trả **những hàng thuộc bảng đích đã thực sự bị xóa**. Trong ví dụ này nó trả **6 hàng**, với các ID **103, 104, 108, 109, 110, 112**.

Các cột được trả là giá trị của hàng bị xóa, hữu ích để kiểm tra ID và dữ liệu trước khi hàng biến mất khỏi bảng. **Không mặc định thứ tự các hàng `RETURNING`**: nếu cần in theo ngày/ID, có thể xử lý thứ tự ở ứng dụng hoặc dùng một CTE bao quanh rồi `ORDER BY` kết quả.

Trong `psql` hoặc công cụ SQL tương ứng, PostgreSQL còn có thể hiển thị thông tin lệnh dạng:

```text
DELETE 6
```

Con số 6 ở đây là **số hàng xóa trực tiếp từ bảng `orders_demo`** do lệnh `DELETE` báo cáo. Các ghi chú bị xóa dây chuyền bởi `ON DELETE CASCADE` **không làm con số này tăng thành 9**.

### 5.2. Quan sát số hàng còn lại trong cùng giao dịch

```sql
BEGIN;

SELECT COUNT(*) AS orders_before
FROM orders_demo;
-- 12

DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01'
RETURNING order_id;
-- 6 ID

SELECT COUNT(*) AS orders_after
FROM orders_demo;
-- 6

SELECT COUNT(*) AS notes_after
FROM order_notes_demo;
-- 1

ROLLBACK;
```

Trong giao dịch, sau khi xóa thành công:

- Bảng đơn từ **12** còn **6 hàng**.
- Ghi chú từ **4** còn **1 hàng**: ghi chú 304 của đơn 105, vì đơn 105 không bị xóa.
- Các ghi chú 301, 302 của đơn 103 và ghi chú 303 của đơn 110 đã bị xóa **qua `ON DELETE CASCADE`**.
- Sau `ROLLBACK`, bảng đơn và ghi chú trở về **12 và 4 hàng**.

Đây là cách quan sát tác động thực tế mà không phải giữ thay đổi.

**Lưu ý:** Đừng chạy `COMMIT` nếu bạn chỉ định thử `DELETE` rồi muốn khôi phục. Một khi transaction đã commit, `ROLLBACK` chạy sau đó **không hoàn tác** được giao dịch đã hoàn tất. Việc khôi phục khi đó phụ thuộc bản sao lưu, lịch sử/temporal table hoặc cơ chế phục hồi đã chuẩn bị.

### 5.3. BEGIN/ROLLBACK dùng để kiểm soát, không thay thế xác nhận

Một giao dịch không tự biết quy tắc nghiệp vụ đúng hay sai. Nếu `DELETE` chọn sai 6 hàng và bạn `COMMIT`, tính nguyên tử của giao dịch không làm kết quả trở nên đúng. Vẫn cần kiểm tra tập khóa bị xóa và kết quả trả về trước khi quyết định commit.

Ngoài ra, không phải mọi hành động bên ngoài database đều được hoàn tác bởi rollback: ví dụ thông báo đã gửi qua API, tệp đã xóa ngoài hệ thống hoặc side effect không giao dịch của một tích hợp. Vì vậy, với các quy trình có tác động liên hệ thống, cần thiết kế cơ chế phối hợp riêng.

## 6. Kiểm tra số hàng bị xóa ngay trong SQL

### 6.1. Dùng CTE chứa DELETE ... RETURNING trong PostgreSQL

Đôi khi chỉ cần số đếm hoặc muốn tổng hợp thông tin từ các hàng đã xóa. PostgreSQL cho phép đặt `DELETE ... RETURNING` trong một **data-modifying CTE**:

```sql
BEGIN;

WITH deleted_orders AS (
    DELETE FROM orders_demo
    WHERE status = 'CANCELLED'
      AND ordered_on < DATE '2025-07-01'
    RETURNING order_id, customer_id, amount
)
SELECT
    COUNT(*) AS deleted_count,
    COALESCE(SUM(amount), 0) AS deleted_amount_total
FROM deleted_orders;

ROLLBACK;
```

Kết quả:

| deleted_count | deleted_amount_total |
|---:|---:|
| 6 | 300.00 |

Tổng 300 gồm 80 + 70 + 30 + 40 + 60 + 20. `deleted_orders` trong ví dụ **không chỉ là truy vấn đọc**: CTE thực sự thực hiện `DELETE` rồi đưa các hàng đã xóa ra qua `RETURNING` cho phần `SELECT` cuối.

**Không chuyển nguyên mẫu này sang mọi hệ quản trị.** PostgreSQL hỗ trợ data-modifying CTE, nhưng SQL Server, MySQL, SQLite và Oracle có giới hạn/cú pháp khác, không nhất thiết cho phép `WITH deleted AS (DELETE ... RETURNING ...) SELECT ...`.

### 6.2. Dùng RETURNING để kiểm tra danh tính chứ không chỉ số lượng

Số đếm đúng **không đủ** khi xóa dữ liệu quan trọng. Có thể cần danh sách:

```sql
BEGIN;

WITH deleted_orders AS (
    DELETE FROM orders_demo
    WHERE status = 'CANCELLED'
      AND ordered_on < DATE '2025-07-01'
    RETURNING order_id, ordered_on
)
SELECT order_id, ordered_on
FROM deleted_orders
ORDER BY ordered_on, order_id;

ROLLBACK;
```

Kết quả được sắp **103, 112, 108, 110, 104, 109**, tương tự truy vấn xem trước. So sánh tập ID thực xóa với tập dự kiến giúp phát hiện điều kiện đổi ý nghĩa hoặc dữ liệu thay đổi giữa các bước.

### 6.3. Số hàng bị ảnh hưởng là tín hiệu nghiệp vụ

Giả sử ứng dụng yêu cầu **xóa đúng một đơn**:

```sql
DELETE FROM orders_demo
WHERE order_id = 103
  AND status = 'CANCELLED';
```

Có ba kết quả đáng phân biệt:

| Số hàng đích bị xóa | Ý nghĩa khả dĩ |
|---:|---|
| 1 | Khớp điều kiện và xóa thành công một đơn |
| 0 | Không có ID đó, hoặc trạng thái không còn `CANCELLED`, hoặc quy tắc/trigger ảnh hưởng kết quả |
| Lớn hơn 1 | Không thể xảy ra với `order_id` là khóa chính trong bảng ví dụ; nếu một truy vấn dùng khóa không duy nhất thì phải kiểm tra lại |

Số **0** không nhất thiết là lỗi SQL. Một câu `DELETE` hợp lệ có thể xóa 0 hàng. Với nghiệp vụ “xóa nếu còn tồn tại”, đó có thể là kết quả chấp nhận được. Với nghiệp vụ “bắt buộc phải xóa đúng một bản ghi”, số 0 cần được xử lý như một **xung đột/trạng thái thay đổi** hoặc trường hợp không tìm thấy.

### 6.4. Đừng chỉ lấy hiệu của COUNT trước và sau

Ví dụ `COUNT(*)` từ 12 xuống 6 cho thấy chênh lệch 6 trong giao dịch thực hành. Nhưng trên hệ thống có truy cập đồng thời, số hàng của bảng có thể tăng/giảm bởi các phiên khác. Hiệu `COUNT(before) - COUNT(after)` không nhất thiết bằng số hàng mà **câu `DELETE` của bạn trực tiếp xóa**.

Để đo tác động của **một câu lệnh**, ưu tiên thông tin do chính câu lệnh/driver cung cấp, hoặc `RETURNING`/`OUTPUT`. Cần thêm danh tính hàng thì ghi lại khóa đã xóa. Truy vấn tổng số hàng trước/sau chỉ là một phép quan sát bổ sung.

## 7. Xóa có điều kiện liên quan đến bảng khác

Nhiều quy tắc xóa phụ thuộc **bảng liên quan**. Ví dụ chỉ xóa những đơn `CANCELLED` cũ **không có ghi chú**, hoặc chỉ xóa ghi chú của những đơn đã hủy trước mốc.

### 7.1. DELETE với EXISTS

Ví dụ cần xóa **ghi chú của những đơn đã hủy trước tháng 7**, không xóa các đơn:

```sql
BEGIN;

DELETE FROM order_notes_demo AS n
WHERE EXISTS (
    SELECT 1
    FROM orders_demo AS o
    WHERE o.order_id = n.order_id
      AND o.status = 'CANCELLED'
      AND o.ordered_on < DATE '2025-07-01'
)
RETURNING n.note_id, n.order_id;

ROLLBACK;
```

Kết quả có **3 ghi chú**: 301, 302, 303.

Với mỗi hàng ghi chú, `EXISTS` hỏi “có đơn liên quan đã hủy trước ngày mốc không?”. Câu lệnh chỉ xóa trong **`order_notes_demo`**, không xóa bản ghi đơn. Nếu một đơn có nhiều ghi chú, mỗi ghi chú phù hợp là một hàng đích riêng.

### 7.2. DELETE với NOT EXISTS

Một quy tắc khác: **chỉ xóa đơn đã hủy cũ nếu không có ghi chú liên quan**.

```sql
BEGIN;

DELETE FROM orders_demo AS o
WHERE o.status = 'CANCELLED'
  AND o.ordered_on < DATE '2025-07-01'
  AND NOT EXISTS (
      SELECT 1
      FROM order_notes_demo AS n
      WHERE n.order_id = o.order_id
  )
RETURNING o.order_id;

ROLLBACK;
```

Kết quả có **4 đơn**: **104, 108, 109, 112**. Đơn 103 và 110 không được chọn vì có ghi chú. Đơn 105 không thuộc điều kiện ngày.

Đây là một **quy tắc nghiệp vụ khác** với lệnh xóa 6 đơn ở mục 3; không nên coi nó chỉ là “một cách viết khác” của cùng thao tác.

**Bẫy `NOT IN`:** Nếu subquery trong `NOT IN` trả các giá trị `NULL`, kết quả phủ định có thể là `UNKNOWN` và bỏ sót hàng cần tìm. `NOT EXISTS` tương quan thường diễn đạt việc không có hàng liên quan trực tiếp và dễ kiểm soát ý nghĩa `NULL` hơn.

### 7.3. PostgreSQL DELETE ... USING

PostgreSQL cho phép đưa bảng nguồn khác vào câu lệnh xóa thông qua `USING`. Ví dụ xóa ghi chú của đơn `CANCELLED` cũ:

```sql
BEGIN;

DELETE FROM order_notes_demo AS n
USING orders_demo AS o
WHERE o.order_id = n.order_id
  AND o.status = 'CANCELLED'
  AND o.ordered_on < DATE '2025-07-01'
RETURNING n.note_id, n.order_id;

ROLLBACK;
```

Kết quả vẫn là **3 ghi chú** (301, 302, 303).

Đừng hiểu `USING orders_demo AS o` là xóa luôn `orders_demo`. Bảng đích nằm ngay sau `DELETE FROM`, ở đây là `order_notes_demo AS n`. Bảng `orders_demo` chỉ cung cấp điều kiện nối.

### 7.4. Một hàng đích khớp nhiều hàng nguồn không được tính thành nhiều hàng đã xóa

Giả sử ta xóa **đơn đã hủy cũ có ít nhất một ghi chú**:

```sql
BEGIN;

DELETE FROM orders_demo AS o
USING order_notes_demo AS n
WHERE n.order_id = o.order_id
  AND o.status = 'CANCELLED'
  AND o.ordered_on < DATE '2025-07-01'
RETURNING o.order_id;

ROLLBACK;
```

Đơn 103 có **hai ghi chú** (301, 302); đơn 110 có **một ghi chú** (303). Phép nối điều kiện tạo **ba cặp đơn–ghi chú**, nhưng `DELETE` chỉ xóa **hai hàng đơn đích 103 và 110**. Mỗi hàng của bảng đích không bị xóa nhiều lần chỉ vì khớp nhiều hàng nguồn.

Do `ON DELETE CASCADE`, **ba ghi chú** của hai đơn đó cũng bị xóa dây chuyền. Vì vậy phải phân biệt:

- **3 cặp hàng ghép** trong logic nối.
- **2 hàng `orders_demo` trực tiếp bị xóa** (số hàng lệnh `DELETE` báo).
- **3 hàng `order_notes_demo` bị xóa do khóa ngoại**.

Đừng nhầm số hàng của `JOIN` với số hàng đích bị xóa.

### 7.5. DELETE dựa trên danh sách khóa bằng IN

Nếu một truy vấn con xác định tập ID cần xóa:

```sql
BEGIN;

DELETE FROM orders_demo
WHERE order_id IN (
    SELECT order_id
    FROM orders_demo
    WHERE status = 'CANCELLED'
      AND ordered_on < DATE '2025-07-01'
)
RETURNING order_id;

ROLLBACK;
```

Trong PostgreSQL, câu này chọn cùng 6 đơn, nhưng không cần vòng qua chính bảng nếu điều kiện đã nằm ngay trên bảng đích. Nó minh họa cú pháp `IN (subquery)`; trên các DBMS khác có thể có giới hạn khi **đọc và sửa cùng bảng** trong một câu lệnh.

Trong thực tế, `IN` phù hợp hơn khi tập khóa đến từ **một bảng/quy trình khác**. Với điều kiện đơn giản trên chính bảng đích, viết trực tiếp `WHERE status = ... AND ordered_on < ...` thường rõ ràng hơn.

## 8. NULL và logic ba giá trị trong DELETE

Một điều kiện `WHERE` trong `DELETE` hoạt động theo cùng logic ba giá trị như `SELECT`:

- `TRUE`: hàng được chọn để xóa.
- `FALSE`: không chọn.
- `UNKNOWN`: cũng không chọn.

Ví dụ giả sử một bảng có cột `cancelled_at` cho phép `NULL`. Câu:

```sql
DELETE FROM some_table
WHERE cancelled_at < DATE '2025-07-01';
```

**Không xóa** những hàng có `cancelled_at = NULL`, vì phép so sánh với `NULL` cho `UNKNOWN`.

Nếu quy tắc thực sự yêu cầu xóa cả các hàng có ngày chưa xác định, phải thể hiện rõ:

```sql
-- Chỉ minh họa ý định; cân nhắc kỹ vì xóa cả hàng thiếu ngày.
DELETE FROM some_table
WHERE cancelled_at < DATE '2025-07-01'
   OR cancelled_at IS NULL;
```

Trong nhiều hệ thống, **thiếu ngày** nên được đưa vào hàng chờ kiểm tra thay vì tự động xóa. Việc mở rộng điều kiện với `OR ... IS NULL` là quyết định nghiệp vụ, không phải bước sửa cú pháp bắt buộc.

### 8.1. IS NULL chứ không dùng = NULL

```sql
-- Sai ý định:
WHERE cancelled_at = NULL

-- Đúng để tìm giá trị thiếu:
WHERE cancelled_at IS NULL
```

Đừng dùng `= NULL` hoặc `<> NULL` để xác định hàng cần xóa.

### 8.2. Chuỗi trạng thái cũng cần đúng dữ liệu

Trong bảng mẫu `status` là văn bản, các giá trị được ràng buộc `NEW`, `PAID`, `CANCELLED`. Điều kiện:

```sql
WHERE status = 'CANCELLED'
```

không tự có nghĩa giống `'cancelled'`, `' CANCELLED '` hoặc các mã trạng thái khác trên mọi hệ quản trị. Khả năng so khớp phụ thuộc dữ liệu, collation và quy tắc chuẩn hóa. Nếu bảng staging có trạng thái không chuẩn, nên phát hiện và xử lý có kiểm soát thay vì mở rộng điều kiện xóa tùy tiện.

### 8.3. NOT IN và giá trị NULL trong tập con

```sql
-- Dạng có thể sai khi subquery trả NULL:
WHERE order_id NOT IN (
    SELECT maybe_order_id
    FROM another_table
)
```

Một `NULL` trong tập con có thể khiến điều kiện `NOT IN` thành `UNKNOWN` ngay cả khi một ID không trùng bất kỳ giá trị đã biết nào. Với yêu cầu “không có hàng liên quan”, có thể viết:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM another_table AS x
    WHERE x.maybe_order_id = orders_demo.order_id
)
```

**Nhưng** dùng `NOT EXISTS` chỉ đúng khi ngữ nghĩa “không tồn tại hàng khớp” thực sự là điều kiện được phép xóa. Không được thay thế tự động mọi `NOT IN` trong một câu xóa nguy hiểm mà chưa xác minh dữ liệu và ý nghĩa khóa.

## 9. Khóa ngoại, ON DELETE CASCADE và số hàng gián tiếp

Ràng buộc khóa ngoại có thể quyết định một thao tác `DELETE` thành công hay bị từ chối, và có thể tạo tác động trên nhiều bảng.

### 9.1. Các hành vi phổ biến của khóa ngoại

| Cấu hình khóa ngoại phía bảng con | Tác động khi xóa hàng cha |
|---|---|
| `ON DELETE CASCADE` | Tự động xóa các hàng con tham chiếu hàng cha |
| `ON DELETE SET NULL` | Đặt cột khóa ngoại của hàng con thành `NULL` nếu cấu trúc cột cho phép |
| `ON DELETE RESTRICT` | Từ chối xóa cha nếu còn con tham chiếu |
| `ON DELETE NO ACTION` | Kiểm tra ràng buộc theo cơ chế DBMS; ở một số hệ có thể hoãn kiểm tra nếu được khai báo phù hợp |
| `ON DELETE SET DEFAULT` | Đặt khóa ngoại về giá trị mặc định nếu cấu hình và ràng buộc cho phép |

Không giả định rằng khóa ngoại mặc định luôn là `CASCADE`. Bảng `order_notes_demo` trong bài **chủ động** khai báo `ON DELETE CASCADE`.

### 9.2. Một DELETE có thể ảnh hưởng nhiều bảng

Ví dụ lệnh xóa 6 đơn cũ:

```sql
DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01';
```

Trên dữ liệu ban đầu:

| Bảng | Số hàng trước | Số hàng sau | Giảm |
|---|---:|---:|---:|
| `orders_demo` | 12 | 6 | 6 |
| `order_notes_demo` | 4 | 1 | 3 |

**Lệnh báo 6 hàng trực tiếp bị xóa từ bảng đơn**, không báo 9, vì ba ghi chú là tác động dây chuyền của quan hệ khóa ngoại. Đếm số hàng “bị ảnh hưởng” trong giao diện công cụ SQL **không phải lúc nào cũng tổng số thay đổi trên toàn bộ hệ thống**.

Ngoài khóa ngoại, còn có thể có:

- **Trigger** ghi audit, xóa hoặc cập nhật thêm bảng khác.
- **Quy tắc bảo mật/quyền truy cập** hạn chế thao tác.
- **Partitioning** hoặc cơ chế lưu trữ đặc biệt.
- **Hàng liên quan thuộc hệ thống khác** không được database tự biết để bảo vệ.

Khi làm việc với hệ thống thật, cần biết bản đồ quan hệ của bảng trước khi xóa.

### 9.3. Nếu khóa ngoại ngăn xóa

Nếu thay cấu hình của `order_notes_demo.order_id` thành `ON DELETE RESTRICT`, cố xóa đơn 103 khi còn ghi chú có thể dẫn đến **lỗi ràng buộc khóa ngoại** và thao tác không thành công. Lúc đó không nên cố gỡ ràng buộc hoặc xóa con một cách mù quáng chỉ để cho câu `DELETE` chạy được.

Phải xác định nghiệp vụ: ghi chú có được xóa không, có cần lưu giữ lịch sử không, hoặc đơn đáng lẽ chỉ được chuyển sang trạng thái `ARCHIVED`. Ràng buộc khóa ngoại đang giúp bảo vệ tính toàn vẹn quan hệ.

## 10. Kiểm tra số hàng bị ảnh hưởng từ ứng dụng

Nhiều ứng dụng thực thi SQL thông qua driver. Ngoài `RETURNING` của database, driver thường có API cung cấp **số hàng thay đổi trực tiếp bởi lệnh DML**.

### 10.1. JDBC: PreparedStatement.executeUpdate()

Ví dụ Java dùng JDBC và một `DataSource` đã được cấu hình (đoạn mã minh họa, không bao gồm cấu hình kết nối):

```java
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class OrderCleanup {
    public static void deleteOldCancelledOrders(DataSource dataSource)
            throws SQLException {

        String sql = """
            DELETE FROM orders_demo
            WHERE status = ?
              AND ordered_on < ?
            """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setString(1, "CANCELLED");
                ps.setDate(2, Date.valueOf("2025-07-01"));

                int affectedRows = ps.executeUpdate();

                // Giá trị 6 chỉ là kỳ vọng của bộ dữ liệu thực hành.
                if (affectedRows != 6) {
                    throw new IllegalStateException(
                        "Unexpected deleted rows: " + affectedRows
                    );
                }

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                connection.rollback();
                throw error;
            }
        }
    }
}
```

Giải thích:

1. `PreparedStatement` truyền hai giá trị điều kiện bằng **tham số**, tránh nối chuỗi đầu vào thành SQL và giúp kiểm soát kiểu dữ liệu.
2. `executeUpdate()` trả về `int` đại diện cho **số hàng bị ảnh hưởng trực tiếp** của lệnh `DELETE` trên driver hỗ trợ.
3. Kịch bản thực hành kỳ vọng **6**. Nếu số lượng khác, mã ném lỗi, đi vào `catch` và `rollback`.
4. Chỉ khi không có lỗi và số hàng đúng kỳ vọng mới `commit`.
5. `try-with-resources` đóng statement/connection sau khi kết thúc.

**Đừng áp dụng cứng điều kiện `affectedRows == 6` vào hệ thống thật.** Số 6 chỉ đúng với bộ dữ liệu mẫu tại trạng thái ban đầu. Trong ứng dụng sản xuất, ngưỡng có thể là “tối đa 100 hàng”, “đúng một hàng theo ID” hoặc số khóa đã chốt từ một tác vụ riêng. Quy tắc phải dựa trên nghiệp vụ.

### 10.2. Tại sao phải kiểm tra affectedRows trước COMMIT?

Nếu số hàng lớn hơn dự kiến nhưng ứng dụng **đã commit**, việc phát hiện lỗi sau commit không thể được sửa chỉ bằng `rollback()`. Kiểm tra và quyết định **trong giao dịch trước khi commit** giúp có cơ hội hủy thao tác.

Đồng thời phải nhớ: kiểm tra số lượng **không kiểm tra danh tính hàng**. Nếu có yêu cầu bảo vệ nghiêm ngặt, nên dùng cơ chế trả ID bị xóa hoặc lưu tập khóa ứng viên đáng tin cậy để đối chiếu.

### 10.3. JDBC và RETURNING không giống executeUpdate thông thường

PostgreSQL:

```sql
DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01'
RETURNING order_id;
```

là một câu `DELETE` **trả tập hàng**. Khi chạy qua JDBC PostgreSQL, thường cần API xử lý `ResultSet` như `executeQuery()` hoặc `execute()` phù hợp với statement có `RETURNING`, rồi đọc hết các ID, thay vì mặc định dùng `executeUpdate()` như lệnh DML không trả hàng. Một số driver sẽ từ chối `executeUpdate()` nếu SQL trả kết quả.

Ví dụ ý tưởng:

```java
String sql = """
    DELETE FROM orders_demo
    WHERE status = ?
      AND ordered_on < ?
    RETURNING order_id
    """;

// Trong một giao dịch đang mở:
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "CANCELLED");
    ps.setDate(2, Date.valueOf("2025-07-01"));

    int returnedIds = 0;
    try (var rs = ps.executeQuery()) {
        while (rs.next()) {
            int deletedOrderId = rs.getInt("order_id");
            // Ghi nhận ID để so với tập dự kiến hoặc phục vụ audit.
            returnedIds++;
        }
    }

    // Kiểm tra returnedIds, rồi commit/rollback theo quy tắc ứng dụng.
}
```

Đoạn này giả định có biến `connection` và giao dịch đã được thiết lập; nó minh họa cách **đọc ID của hàng bị xóa**, không phải một chương trình ứng dụng hoàn chỉnh. Phải xử lý transaction và exception như ví dụ trước.

**Đừng tạo log ngoài database rồi cho rằng rollback sẽ hoàn tác cả log đó.** Nếu cần nhật ký có tính nguyên tử cùng thao tác xóa, hãy thiết kế audit trong cùng giao dịch/database hoặc cơ chế đáng tin cậy tương đương.

## 11. Xóa theo lô để kiểm soát số hàng

Xóa một lượng dữ liệu lớn trong một lệnh có thể tạo giao dịch dài, giữ khóa lâu và tốn tài nguyên lưu phiên bản. Với dữ liệu cũ cần dọn định kỳ, nhiều hệ thống chọn **xóa theo lô** (*batch delete*).

### 11.1. PostgreSQL không có DELETE ... LIMIT trực tiếp

Không viết:

```sql
-- Không phải cú pháp DELETE thông dụng của PostgreSQL:
DELETE FROM orders_demo
WHERE status = 'CANCELLED'
LIMIT 2;
```

Thay vào đó, chọn một **tập khóa giới hạn** rồi xóa theo khóa:

```sql
BEGIN;

WITH batch AS (
    SELECT order_id
    FROM orders_demo
    WHERE status = 'CANCELLED'
      AND ordered_on < DATE '2025-07-01'
    ORDER BY ordered_on, order_id
    LIMIT 2
)
DELETE FROM orders_demo AS o
USING batch AS b
WHERE o.order_id = b.order_id
RETURNING o.order_id, o.ordered_on;

ROLLBACK;
```

Trên dữ liệu mẫu, lô đầu chọn hai đơn **103 (05/01)** và **112 (15/01)**, vì chúng là hai đơn đã hủy cũ nhất trong tập ứng viên.

Điều kiện `ORDER BY ordered_on, order_id` trong CTE giúp xác định **hai khóa được chọn**, không có nghĩa PostgreSQL sẽ trả các hàng `RETURNING` theo thứ tự đó. `order_id` là khóa phân định khi hai đơn có cùng ngày.

### 11.2. Xóa có khóa hàng trong môi trường nhiều worker

PostgreSQL còn có thể dùng `FOR UPDATE SKIP LOCKED` khi nhiều worker cùng nhận các công việc dọn dữ liệu:

```sql
BEGIN;

WITH batch AS (
    SELECT order_id
    FROM orders_demo
    WHERE status = 'CANCELLED'
      AND ordered_on < DATE '2025-07-01'
    ORDER BY ordered_on, order_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
DELETE FROM orders_demo AS o
USING batch AS b
WHERE o.order_id = b.order_id
RETURNING o.order_id;

COMMIT;
```

Đây là **mẫu nâng cao**. `SKIP LOCKED` bỏ qua hàng đang bị giao dịch khác giữ khóa, phù hợp một số bài toán chia việc. Nhưng lô lấy được có thể **không phải đúng hai đơn cũ nhất tuyệt đối** nếu những hàng đứng đầu đang bị khóa. Không nên áp dụng máy móc với những quy trình yêu cầu thứ tự tuyệt đối hoặc snapshot đầy đủ.

Trong ứng dụng thực, mỗi lô cần xử lý lỗi, kiểm tra số hàng, retry có kiểm soát, giới hạn tải và lưu tiến độ nếu cần. Việc chạy `COMMIT` trong ví dụ thứ hai **giữ lại thay đổi**, nên chỉ dùng trên môi trường được phép dọn; trong bài thực hành hãy thay `COMMIT` bằng `ROLLBACK`.

### 11.3. Xóa nhiều lô không phải một giao dịch nguyên tử duy nhất

Nếu ứng dụng commit sau mỗi lô, lô thứ nhất có thể đã xóa thành công dù lô thứ ba lỗi. Đó có thể là thiết kế hợp lý cho bảo trì, nhưng khác với yêu cầu “**toàn bộ chiến dịch xóa hoặc thành công hết, hoặc không làm gì**”.

Phải chọn chiến lược theo nghiệp vụ:

- Giao dịch một lần: tính nguyên tử tốt hơn nhưng có thể rất nặng.
- Chia lô commit từng phần: giảm thời gian khóa, nhưng cần khả năng tiếp tục và kiểm tra tiến độ.
- Xóa hoặc lưu trữ bằng partition: có thể phù hợp khi dữ liệu được phân vùng theo kỳ và chính sách dọn dựa trên toàn bộ phân vùng.

Không đồng nhất `DELETE` với `TRUNCATE` hoặc `DROP TABLE`: những lệnh này có phạm vi và hành vi ràng buộc/giao dịch khác, không phải cách thay thế đơn giản cho việc xóa có `WHERE`.

## 12. Số hàng bị ảnh hưởng trong các phương ngữ SQL

**Ngữ nghĩa chung:** xác định bảng đích và điều kiện xóa, rồi đọc số hàng mà câu lệnh DML trực tiếp thay đổi. Nhưng cú pháp lấy danh sách hàng hoặc số lượng khác nhau theo DBMS và phiên bản.

### 12.1. PostgreSQL: RETURNING và trạng thái lệnh

```sql
BEGIN;

DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01'
RETURNING order_id, status;

ROLLBACK;
```

PostgreSQL trả các hàng bị xóa qua `RETURNING` và thông tin lệnh `DELETE 6` trên dữ liệu mẫu. Trong hàm/khối **PL/pgSQL**, còn có thể đọc số hàng của câu SQL vừa thực hiện bằng `GET DIAGNOSTICS ... = ROW_COUNT`:

```sql
-- Minh họa trong khối PL/pgSQL;
-- dùng transaction bên ngoài nếu cần ROLLBACK.
DO $$
DECLARE
    deleted_count BIGINT;
BEGIN
    DELETE FROM orders_demo
    WHERE status = 'CANCELLED'
      AND ordered_on < DATE '2025-07-01';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Deleted order rows: %', deleted_count;
END
$$;
```

Khối `DO` **thực sự xóa dữ liệu** nếu được chạy. Để thử mà không giữ thay đổi, hãy đặt `BEGIN;` trước khối, `ROLLBACK;` sau khối trong cùng kết nối/giao dịch. Biến `ROW_COUNT` đọc kết quả của câu lệnh trước đó theo quy tắc PL/pgSQL; cần lấy **ngay sau `DELETE`** trước khi một câu SQL khác thay đổi trạng thái đếm.

### 12.2. SQL Server: OUTPUT và @@ROWCOUNT

SQL Server dùng `OUTPUT deleted.column` để trả cột của hàng bị xóa:

```sql
-- SQL Server
BEGIN TRANSACTION;

DELETE o
OUTPUT deleted.order_id, deleted.status
FROM dbo.orders_demo AS o
WHERE o.status = 'CANCELLED'
  AND o.ordered_on < '2025-07-01';

SELECT @@ROWCOUNT AS affected_rows;

ROLLBACK TRANSACTION;
```

`OUTPUT` trả các hàng bị xóa. `@@ROWCOUNT` phản ánh số hàng bị tác động bởi **câu SQL ngay trước đó** trong ngữ cảnh sử dụng; hãy đọc/gán nó **ngay sau `DELETE`**. Nếu bạn chạy một câu `SELECT` hay lệnh khác trước khi kiểm tra, giá trị có thể không còn là số hàng của `DELETE`.

Ví dụ lưu số đếm ngay:

```sql
DELETE FROM dbo.orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < '2025-07-01';

DECLARE @deleted_count INT = @@ROWCOUNT;
SELECT @deleted_count AS affected_rows;
```

Đoạn thứ hai chỉ minh họa cách đọc số đếm; nó có tác dụng xóa thật nếu chạy ngoài giao dịch thử. SQL Server còn hỗ trợ các mẫu `DELETE ... FROM ... JOIN ...`, nhưng cú pháp không giống `DELETE ... USING` của PostgreSQL.

### 12.3. MySQL: ROW_COUNT() và DELETE ... LIMIT

MySQL dùng `ROW_COUNT()` để đọc số hàng bị ảnh hưởng bởi câu lệnh trước:

```sql
-- MySQL với engine hỗ trợ giao dịch như InnoDB
START TRANSACTION;

DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < '2025-07-01';

SELECT ROW_COUNT() AS affected_rows;

ROLLBACK;
```

Với dữ liệu mẫu tương đương, giá trị mong đợi là **6**. Cần gọi `ROW_COUNT()` **ngay sau `DELETE`**; một lệnh khác chen vào có thể làm thay đổi giá trị báo cáo.

MySQL hỗ trợ `ORDER BY` và `LIMIT` cho một số dạng **single-table DELETE**:

```sql
-- MySQL: xóa tối đa 2 đơn khớp điều kiện
DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < '2025-07-01'
ORDER BY ordered_on, order_id
LIMIT 2;
```

Đừng chuyển `DELETE ... LIMIT` này sang PostgreSQL vì cú pháp và khả năng hỗ trợ khác. Các dạng xóa **nhiều bảng** của MySQL có cú pháp và giới hạn riêng.

MySQL thông dụng không có `DELETE ... RETURNING` tổng quát tương đương PostgreSQL; nếu cần biết ID đã xóa, ứng dụng có thể phải khóa/chốt danh sách ID trước trong giao dịch và kiểm tra danh tính bằng cơ chế phù hợp.

### 12.4. SQLite: RETURNING và changes()

SQLite từ phiên bản **3.35.0** hỗ trợ `RETURNING`:

```sql
-- SQLite mới (RETURNING từ 3.35.0)
BEGIN;

DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < '2025-07-01'
RETURNING order_id;

SELECT changes() AS affected_rows;

ROLLBACK;
```

Trong giao diện/driver, cần **đọc hết tập kết quả của `RETURNING`** trước khi bắt đầu một lệnh khác trên cùng statement/kết nối theo quy tắc API. `changes()` đếm các hàng **trực tiếp** bị thay đổi bởi thao tác gần nhất trên kết nối, không cộng các hàng bị thay đổi do trigger hoặc hành động khóa ngoại gián tiếp.

SQLite thường yêu cầu bật `PRAGMA foreign_keys = ON` trước giao dịch để ràng buộc khóa ngoại được thực thi; nếu không bật, `ON DELETE CASCADE` trong schema có thể **không hoạt động**. Do đó số hàng ghi chú bị xóa dây chuyền trong SQLite cần được kiểm tra theo cấu hình kết nối thực tế.

### 12.5. Oracle: SQL%ROWCOUNT trong PL/SQL

Oracle PL/SQL có thuộc tính `SQL%ROWCOUNT` để lấy số hàng tác động của lệnh SQL ngầm vừa thực thi:

```sql
-- Oracle PL/SQL, minh họa xóa và rollback.
BEGIN
    DELETE FROM orders_demo
    WHERE status = 'CANCELLED'
      AND ordered_on < DATE '2025-07-01';

    DBMS_OUTPUT.PUT_LINE(
        'Deleted order rows: ' || SQL%ROWCOUNT
    );

    ROLLBACK;
END;
/
```

Trong Oracle, cú pháp `RETURNING ... INTO` có thể dùng để lấy dữ liệu hàng thay đổi trong ngữ cảnh thích hợp, khác với cách trả tập kết quả `RETURNING` của PostgreSQL. Nếu xóa nhiều hàng và cần nhận danh sách ID trong PL/SQL, có thể cần cơ chế thu thập nhiều giá trị như `BULK COLLECT` theo cú pháp Oracle tương ứng. Không giả định `DELETE ... RETURNING order_id` một mình trả một result set kiểu PostgreSQL trên Oracle.

### 12.6. Bảng so sánh nhanh

| DBMS | Xem danh tính hàng bị xóa | Đọc số hàng lệnh DELETE tác động |
|---|---|---|
| PostgreSQL | `DELETE ... RETURNING ...` | Command tag `DELETE n`; trong PL/pgSQL dùng `GET DIAGNOSTICS ... ROW_COUNT` |
| SQL Server | `OUTPUT deleted.col` | `@@ROWCOUNT` ngay sau lệnh |
| MySQL | Thường cần cách lưu/đối chiếu khóa qua ứng dụng và transaction | `ROW_COUNT()` ngay sau lệnh |
| SQLite | `RETURNING` từ 3.35.0 | `changes()` trên kết nối |
| Oracle | `RETURNING ... INTO` với cấu trúc PL/SQL/API phù hợp | `SQL%ROWCOUNT` trong PL/SQL |
| JDBC (driver hỗ trợ) | `ResultSet` nếu câu SQL trả dữ liệu | `PreparedStatement.executeUpdate()` cho DML không trả tập hàng |

Đặc biệt cần phân biệt **số hàng đích trực tiếp**, **số dòng kết quả `RETURNING`/`OUTPUT`**, **số hàng con xóa theo cascade**, và **số hàng nghiệp vụ bị ảnh hưởng gián tiếp**. Chúng có thể khác nhau dù mỗi cơ chế hoạt động đúng.

## 13. Đồng thời, khóa và kiểm tra trước/sau

Trong môi trường nhiều người dùng, một hàng có thể bị sửa từ `CANCELLED` thành trạng thái khác giữa lúc ứng dụng đọc và xóa. Điều kiện `WHERE` khi xóa là một phần bảo vệ quan trọng:

```sql
DELETE FROM orders_demo
WHERE order_id = 103
  AND status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01';
```

Nếu đơn 103 đã được chuyển trạng thái hoặc ngày không còn phù hợp tại thời điểm thao tác, số hàng bị xóa có thể là **0**, thay vì xóa nhầm một bản ghi mà người dùng khác vừa thay đổi.

### 13.1. Optimistic concurrency qua số hàng

Một mô hình thường gặp:

1. Ứng dụng đọc một hàng và trạng thái hiện tại.
2. Người dùng xác nhận muốn xóa **nếu trạng thái chưa thay đổi**.
3. `DELETE` dùng cả khóa và trạng thái/phiên bản:

```sql
DELETE FROM orders_demo
WHERE order_id = 103
  AND status = 'CANCELLED';
```

4. Nếu số hàng bị xóa là **1**, thao tác khớp điều kiện.
5. Nếu số hàng bị xóa là **0**, ứng dụng cần xử lý trường hợp không tìm thấy hoặc dữ liệu đã thay đổi.

Với hệ thống sử dụng cột phiên bản `row_version`, có thể đưa phiên bản đã đọc vào `WHERE` để ngăn thao tác trên phiên bản cũ. Bảng `orders_demo` trong bài **không có** cột đó; ví dụ trên kiểm tra trạng thái, không phải khóa phiên bản đầy đủ.

### 13.2. Chỉ kiểm tra số lượng có thể bỏ sót thay đổi về danh tính

Giả sử lần xem trước tìm 6 đơn; sau đó một đơn được sửa không còn đủ điều kiện, đồng thời một đơn khác trở thành đủ điều kiện. Lệnh `DELETE` sau đó có thể vẫn xóa **6 hàng**, nhưng **tập ID khác với lần xem trước**.

Vì vậy, khi chính sách yêu cầu **đúng tập khóa đã xác nhận**, phải chốt và bảo vệ tập đó trong một giao dịch/chiến lược khóa thích hợp, không chỉ so `COUNT = 6`. `RETURNING order_id` giúp ghi nhận những hàng thật sự bị xóa.

### 13.3. Khóa ứng viên trong giao dịch khi cần

Trong PostgreSQL, có thể khóa các hàng được xem trước:

```sql
BEGIN;

SELECT order_id, status, ordered_on
FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01'
ORDER BY ordered_on, order_id
FOR UPDATE;

-- Đánh giá tập ID, rồi thực thi thao tác cùng giao dịch.
-- DELETE ... WHERE order_id IN (... khóa đã chốt ...)

ROLLBACK;
```

`FOR UPDATE` giúp bảo vệ các **hàng đã khóa** khỏi những cập nhật cạnh tranh theo cơ chế khóa của PostgreSQL. Nhưng nó **không tự ngăn các hàng mới thỏa điều kiện được thêm vào** hoặc mọi hình thức phantom trong mọi mức cô lập. Với thao tác cần bảo đảm tập ứng viên không thay đổi, phải xét isolation level, cách chốt khóa, cách ghép điều kiện và hệ thống ghi đồng thời.

Không giữ transaction mở lâu chỉ để chờ người dùng xem màn hình xác nhận; khóa kéo dài có thể làm chậm các giao dịch khác. Thiết kế xác nhận và thực thi cần cân bằng tính nhất quán với thời gian khóa.

## 14. DELETE cứng, xóa mềm và lưu trữ dữ liệu

`DELETE` là **xóa cứng** (*hard delete*) khỏi bảng hiện tại. Trong nhiều hệ thống, yêu cầu “không hiển thị nữa” **không có nghĩa được phép xóa vĩnh viễn**:

- Đơn đã thanh toán có thể phải giữ để đối soát và kiểm toán.
- Lịch sử thay đổi có thể cần lưu trong bảng sự kiện/audit.
- Hệ thống có chính sách thời hạn lưu trữ và yêu cầu bảo vệ dữ liệu cá nhân.
- Dữ liệu có thể còn được các bảng khác hoặc hệ thống tích hợp tham chiếu.

### 14.1. Xóa mềm bằng UPDATE

Ví dụ một schema **giả định** có cột `deleted_at`:

```sql
-- Chỉ minh họa; bảng mẫu orders_demo chưa có cột deleted_at.
UPDATE orders_demo
SET deleted_at = CURRENT_TIMESTAMP
WHERE order_id = 103
  AND deleted_at IS NULL;
```

Bản ghi vẫn tồn tại, nhưng ứng dụng có thể dùng:

```sql
WHERE deleted_at IS NULL
```

để chỉ hiển thị bản ghi đang hoạt động. Cách này giúp bảo toàn lịch sử nhưng kéo theo các vấn đề mới: truy vấn phải lọc nhất quán, ràng buộc duy nhất cho bản ghi chưa xóa cần thiết kế, dữ liệu vẫn chiếm dung lượng và xóa mềm **không tự thực hiện nghĩa vụ xóa dữ liệu** nếu pháp luật/chính sách yêu cầu xóa thật.

### 14.2. Lưu trữ trước khi xóa

Một quy trình lưu trữ có thể:

1. Chọn tập bản ghi đủ điều kiện.
2. Sao chép dữ liệu cần giữ vào kho lưu trữ theo quy tắc xác nhận.
3. Kiểm tra số lượng, khóa và tính toàn vẹn.
4. Xóa ở bảng nguồn trong phạm vi được phép.
5. Ghi nhận thời điểm, người/tác vụ, chính sách và kết quả.

Không nên xem thao tác `INSERT vào archive` rồi `DELETE từ source` là nguyên tử **nếu hai thao tác không được đặt trong cùng một cơ chế giao dịch phù hợp**. Với dữ liệu lớn, lưu trữ/xóa theo partition hoặc quy trình bất đồng bộ có thể cần thiết kế riêng.

## 15. Những lỗi thường gặp với DELETE và số hàng bị ảnh hưởng

### Lỗi 1 — Quên WHERE

`DELETE FROM orders_demo;` cố xóa mọi hàng. Đây là lỗi phạm vi nghiêm trọng nhất. Trước khi chạy, luôn xác nhận câu lệnh có điều kiện đúng nghiệp vụ.

### Lỗi 2 — Dùng <= thay cho <

`ordered_on <= DATE '2025-07-01'` bao gồm cả đơn 105 đúng ngày mốc; `ordered_on < DATE '2025-07-01'` thì không. Phải diễn đạt chính xác ranh giới.

### Lỗi 3 — Dùng OR thiếu ngoặc

`status = 'CANCELLED' AND ordered_on < cutoff OR customer_id = 2` có thể chọn **mọi đơn của khách 2**, kể cả đơn chưa hủy. Dùng ngoặc phù hợp và thử `SELECT` trước khi xóa.

### Lỗi 4 — Chỉ đếm trước, không kiểm tra sau DELETE

`SELECT COUNT(*) = 6` không chứng minh lệnh xóa sau đó tác động đúng 6 hàng, nhất là khi dữ liệu có thể đổi đồng thời. Dùng số hàng báo bởi lệnh và `RETURNING`/`OUTPUT` khi cần.

### Lỗi 5 — Đếm đúng nhưng xóa sai ID

Hai tập có cùng 6 hàng có thể không phải cùng 6 ID. Với thao tác rủi ro, kiểm tra **danh tính các hàng** thay vì chỉ số lượng.

### Lỗi 6 — Nhầm DELETE n với tổng số hàng liên quan bị ảnh hưởng

Xóa 6 đơn cũ có thể làm xóa dây chuyền 3 ghi chú; PostgreSQL vẫn báo `DELETE 6` cho bảng đơn. Không cộng ngầm các thay đổi cascade vào số hàng trực tiếp.

### Lỗi 7 — Nghĩ JOIN tạo ba cặp thì phải xóa ba đơn

Đơn 103 có hai ghi chú, đơn 110 một ghi chú. `DELETE orders USING notes` chọn **2 đơn đích**, dù ghép được **3 cặp** đơn–ghi chú. Số cặp ghép không bằng số hàng đích bị xóa.

### Lỗi 8 — Cho rằng DELETE 0 luôn là lỗi

`DELETE` xóa 0 hàng có thể hoàn toàn hợp lệ: hàng đã được xóa trước đó hoặc không còn khớp trạng thái. Hệ thống phải định nghĩa khi nào 0 là chấp nhận được và khi nào cần báo xung đột.

### Lỗi 9 — Dùng = NULL

`WHERE some_col = NULL` không bắt những hàng thiếu giá trị. Dùng `IS NULL` và cân nhắc liệu hàng thiếu giá trị có nên bị xóa hay chỉ cần đưa vào danh sách xử lý.

### Lỗi 10 — Dùng NOT IN với tập con có NULL

`NOT IN` chứa `NULL` có thể trả `UNKNOWN`, dẫn đến không xóa những hàng mà người viết tưởng sẽ được chọn. Dùng `NOT EXISTS` hoặc lọc `NULL` ở tập con sau khi hiểu đúng nghiệp vụ.

### Lỗi 11 — Lấy số hàng bị ảnh hưởng quá muộn

`@@ROWCOUNT` của SQL Server và `ROW_COUNT()` của MySQL cần được đọc **ngay sau lệnh quan tâm**, tránh lệnh khác ghi đè trạng thái. `changes()` của SQLite cũng có ngữ nghĩa kết nối/lệnh cụ thể.

### Lỗi 12 — Gọi JDBC executeUpdate cho statement trả RETURNING

`DELETE ... RETURNING` tạo tập kết quả; trên PostgreSQL JDBC cần dùng API đọc `ResultSet` thích hợp. Với `DELETE` không trả tập hàng, `executeUpdate()` thường là cách lấy số hàng trực tiếp.

### Lỗi 13 — Nghĩ ROLLBACK sửa được sau COMMIT

Sau commit, rollback tiếp theo không hoàn tác được giao dịch đã kết thúc. Phải kiểm tra danh tính/số lượng trước khi quyết định commit.

### Lỗi 14 — Thay DELETE bằng TRUNCATE để nhanh hơn

`TRUNCATE` thường áp dụng ở **mức toàn bảng/phân vùng**, không có `WHERE` như `DELETE` và có quy tắc khóa, trigger, khóa ngoại, identity/giao dịch phụ thuộc DBMS. Không thay thế hai lệnh cho nhau mà không xét phạm vi và tác động.

### Lỗi 15 — Bỏ qua dữ liệu con hoặc trigger

`ON DELETE CASCADE` có thể xóa thêm dữ liệu; `RESTRICT`/`NO ACTION` có thể khiến lệnh thất bại. Cần biết toàn bộ quan hệ và trigger liên quan trước khi chạy dọn dữ liệu.

### Lỗi 16 — Xóa cứng khi chỉ cần ẩn bản ghi

Đối với đơn đã thanh toán hoặc lịch sử quan trọng, có thể cần archive/soft delete thay vì hard delete. Lựa chọn phụ thuộc chính sách lưu trữ và quy định áp dụng.

### Lỗi 17 — Xóa theo lô mà không cố định tập khóa

`LIMIT 2` không kèm thứ tự ổn định có thể chọn bất kỳ hai ứng viên nào. Dùng `ORDER BY` phù hợp với khóa phân định trong bước chọn lô, đồng thời kiểm soát trường hợp ghi đồng thời.

### Lỗi 18 — Tin rằng mọi DBMS đều hỗ trợ cùng cú pháp

PostgreSQL dùng `DELETE ... RETURNING` và `DELETE ... USING`; SQL Server dùng `OUTPUT deleted...`; MySQL có `ROW_COUNT()` và một số dạng `DELETE ... ORDER BY ... LIMIT`; SQLite có `changes()`; Oracle có `SQL%ROWCOUNT`. Cần viết đúng phương ngữ và phiên bản.

## 16. Bài tập thực hành

Các bài dưới đây dùng đúng bộ dữ liệu ở mục 2, trừ khi có ghi rõ điều kiện giả định khác. **Mỗi bài là một tình huống độc lập**, bắt đầu từ trạng thái bảng ban đầu. Đối với lệnh `DELETE`, hãy sử dụng `BEGIN ... ROLLBACK` khi thực hành để không phải nạp lại dữ liệu cho bài sau.

### Bài 1 — Chọn đúng ứng viên xóa

Yêu cầu: tìm tất cả đơn `CANCELLED` trước `DATE '2025-07-01'` nhưng **chưa xóa**. Hãy viết `SELECT` có `ORDER BY ordered_on, order_id`.

```sql
SELECT order_id, ordered_on
FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01'
ORDER BY ordered_on, order_id;
```

**Đáp án:** `103, 112, 108, 110, 104, 109` theo thứ tự ngày; tổng **6 hàng**.

### Bài 2 — Xóa có điều kiện và RETURNING

Viết lệnh xóa cùng tập ứng viên bài 1, trả về `order_id` và `status` bằng `RETURNING`.

```sql
BEGIN;

DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01'
RETURNING order_id, status;

ROLLBACK;
```

**Đáp án:** xóa **6 hàng đơn** trong giao dịch; `ROLLBACK` khôi phục chúng.

### Bài 3 — Dấu so sánh ngày

Thay `ordered_on < DATE '2025-07-01'` bằng `ordered_on <= DATE '2025-07-01'`.

**Đáp án:** số đơn `CANCELLED` khớp tăng từ **6 lên 7**; đơn **105** được chọn thêm vì nằm đúng ngày mốc.

### Bài 4 — Đếm và kiểm tra hàng trước/sau trong transaction

Trong cùng giao dịch, chạy:

```sql
BEGIN;

SELECT COUNT(*) AS before_count FROM orders_demo;

DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < DATE '2025-07-01';

SELECT COUNT(*) AS after_count FROM orders_demo;
SELECT COUNT(*) AS notes_after FROM order_notes_demo;

ROLLBACK;
```

**Đáp án:** đơn từ **12 còn 6**, ghi chú từ **4 còn 1** trong giao dịch. Vì sao số hàng đơn bị xóa là 6 chứ không phải 9 dù có thêm 3 ghi chú bị cascade?

### Bài 5 — Xóa đúng một đơn theo ID và trạng thái

```sql
BEGIN;

DELETE FROM orders_demo
WHERE order_id = 103
  AND status = 'CANCELLED'
RETURNING order_id;

ROLLBACK;
```

**Đáp án:** một hàng đơn `103`. Nếu đổi thành `order_id = 103 AND status = 'PAID'` thì xóa **0 hàng**.

### Bài 6 — AND, OR và ngoặc

So sánh hai điều kiện:

```sql
-- A
WHERE status = 'CANCELLED'
  AND (ordered_on < DATE '2025-07-01' OR order_id = 111)

-- B
WHERE (status = 'CANCELLED'
       AND ordered_on < DATE '2025-07-01')
   OR order_id = 111
```

**Đáp án:** A chọn **6 đơn**, vì 111 không `CANCELLED`; B chọn **7 đơn** vì thêm ID 111 độc lập với trạng thái.

### Bài 7 — Khách 2 có những đơn CANCELLED nào?

Viết `DELETE` có điều kiện `customer_id = 2 AND status = 'CANCELLED'`, trả ID.

**Đáp án:** đơn **103 và 104**, tổng **2 hàng**. Đơn 111 của khách 2 có `status = 'NEW'`, không được chọn.

### Bài 8 — Chỉ xóa đơn cũ không có ghi chú

Dùng `NOT EXISTS` đối chiếu `order_notes_demo`:

```sql
BEGIN;

DELETE FROM orders_demo AS o
WHERE o.status = 'CANCELLED'
  AND o.ordered_on < DATE '2025-07-01'
  AND NOT EXISTS (
      SELECT 1
      FROM order_notes_demo AS n
      WHERE n.order_id = o.order_id
  )
RETURNING o.order_id;

ROLLBACK;
```

**Đáp án:** **104, 108, 109, 112**, tổng **4 đơn**. Đơn 103 và 110 có ghi chú nên không khớp `NOT EXISTS`.

### Bài 9 — Xóa ghi chú, giữ nguyên đơn

Dùng `DELETE FROM order_notes_demo` với `EXISTS` hoặc `USING` để chỉ xóa ghi chú của đơn `CANCELLED` trước tháng 7.

**Đáp án:** ghi chú **301, 302, 303** bị xóa trực tiếp; không có đơn nào bị xóa từ `orders_demo`.

### Bài 10 — Số hàng JOIN khác số hàng DELETE

Viết lệnh:

```sql
BEGIN;

DELETE FROM orders_demo AS o
USING order_notes_demo AS n
WHERE o.order_id = n.order_id
  AND o.status = 'CANCELLED'
  AND o.ordered_on < DATE '2025-07-01'
RETURNING o.order_id;

ROLLBACK;
```

**Đáp án:** trả **2 đơn**: 103 và 110. Phép nối có thể tạo 3 cặp đơn–ghi chú, nhưng mỗi hàng đơn đích chỉ bị xóa một lần.

### Bài 11 — Đếm bằng data-modifying CTE

Viết `WITH deleted AS (DELETE ... RETURNING amount) SELECT COUNT(*), SUM(amount) FROM deleted` trong PostgreSQL.

**Đáp án:** **deleted_count = 6**, **SUM(amount) = 300.00** trên dữ liệu ban đầu. Câu lệnh vẫn thực sự xóa dữ liệu, nên dùng transaction rollback khi học.

### Bài 12 — Xóa lô hai đơn cũ nhất

Trong PostgreSQL, chọn `order_id` bằng `ORDER BY ordered_on, order_id LIMIT 2` trong CTE, rồi xóa bằng `USING`.

**Đáp án:** **103 và 112** là hai đơn `CANCELLED` cũ nhất trước 01/07/2025. Nếu xóa lô và commit, lần chạy kế tiếp sẽ chọn những đơn còn lại theo thứ tự mới.

### Bài 13 — SQL Server trả về ID và số hàng

Chuyển bài 2 sang SQL Server bằng `OUTPUT deleted.order_id` và `@@ROWCOUNT`.

**Đáp án định hướng:**

```sql
BEGIN TRANSACTION;

DELETE FROM dbo.orders_demo
OUTPUT deleted.order_id
WHERE status = 'CANCELLED'
  AND ordered_on < '2025-07-01';

SELECT @@ROWCOUNT AS affected_rows;
ROLLBACK TRANSACTION;
```

Kỳ vọng **6 hàng**; phải đọc `@@ROWCOUNT` ngay sau `DELETE`.

### Bài 14 — MySQL trả số hàng

Trên MySQL có schema tương đương và engine giao dịch, dùng:

```sql
START TRANSACTION;

DELETE FROM orders_demo
WHERE status = 'CANCELLED'
  AND ordered_on < '2025-07-01';

SELECT ROW_COUNT() AS affected_rows;
ROLLBACK;
```

**Đáp án:** kỳ vọng **6**. Đừng viết `RETURNING` theo cú pháp PostgreSQL rồi giả định mọi bản MySQL hỗ trợ.

### Bài 15 — Xử lý số hàng = 0

Giả sử ứng dụng chạy:

```sql
DELETE FROM orders_demo
WHERE order_id = 999
  AND status = 'CANCELLED';
```

**Đáp án:** xóa **0 hàng** vì mẫu không có ID 999. Nếu người dùng yêu cầu “xóa nếu tồn tại”, 0 có thể chấp nhận. Nếu thao tác bắt buộc tác động đúng một hàng, ứng dụng cần báo “không tìm thấy hoặc trạng thái đã thay đổi”, không tự coi nó là lỗi cú pháp SQL.

### Bài 16 — Chọn hard delete hay soft delete?

Một hệ thống cần giữ đơn `PAID` trong nhiều năm để phục vụ kiểm toán, nhưng không muốn hiện chúng ở màn hình vận hành. Nên xóa `DELETE` ngay hay đánh dấu ngừng hiển thị?

**Đáp án định hướng:** thường không nên xóa cứng chỉ để ẩn khỏi giao diện. Có thể dùng trạng thái lưu trữ/xóa mềm và bộ lọc hiển thị, đồng thời tuân thủ chính sách lưu trữ và yêu cầu bảo vệ dữ liệu cụ thể.

### Bài 17 — Kiểm tra danh tính khi số lượng bằng nhau

Trước lúc chạy xóa, truy vấn xem trước trả 6 ID. Một giao dịch khác làm thay đổi dữ liệu, khiến câu `DELETE` vẫn báo 6 hàng nhưng ID bị xóa khác một ID dự kiến. Có thể kết luận thao tác an toàn vì số hàng đúng 6 không?

**Đáp án:** **không**. Cần kiểm tra danh tính hàng, ví dụ `RETURNING order_id`, và dùng transaction/khóa/snapshot phù hợp nếu yêu cầu phải xóa đúng tập khóa đã chốt.

### Bài 18 — Thiết kế quy trình xóa định kỳ

Giả sử mỗi đêm cần xóa một số đơn `CANCELLED` hết hạn, tối đa 500 đơn mỗi lô. Hãy đề xuất các bước:

**Đáp án định hướng:** xác định chính sách giữ dữ liệu; dùng `SELECT` xem trước điều kiện/khóa; chọn lô có `ORDER BY` ổn định; thực thi trong transaction; đọc số hàng và ID thực xóa; quyết định commit/rollback; ghi tiến độ và audit theo cách phù hợp; xử lý khóa ngoại, lỗi, retry và dừng khi không còn ứng viên. Đánh giá ảnh hưởng của xóa dây chuyền và tránh giao dịch dài.

## 17. Bảng ghi nhớ nhanh

| Mục tiêu | Mẫu SQL/cơ chế | Điểm cần nhớ |
|---|---|---|
| Xóa theo điều kiện | `DELETE FROM table WHERE predicate` | Không bỏ `WHERE` ngoài ý muốn |
| Xem trước | `SELECT ... WHERE cùng predicate` | Kiểm tra cả ID và số lượng |
| Đếm ứng viên | `SELECT COUNT(*) ... WHERE ...` | Đây chưa phải số hàng đã xóa |
| Thử và khôi phục | `BEGIN; DELETE ...; ROLLBACK;` | Rollback phải diễn ra trước commit |
| Trả ID đã xóa trên PostgreSQL | `DELETE ... RETURNING id` | Không bảo đảm thứ tự trả về |
| Đếm bằng CTE PostgreSQL | `WITH deleted AS (DELETE ... RETURNING ...) SELECT COUNT(*)` | Bản thân CTE thực hiện xóa |
| Xóa theo quan hệ | `EXISTS`, `NOT EXISTS`, `DELETE ... USING` | Bảng sau `DELETE FROM` là đích |
| Kiểm tra hàng bị ảnh hưởng | JDBC `executeUpdate()`, PostgreSQL command tag | Thường là hàng đích trực tiếp |
| Đọc số hàng SQL Server | `@@ROWCOUNT` | Đọc ngay sau câu DML |
| Đọc số hàng MySQL | `ROW_COUNT()` | Đọc ngay sau câu DML |
| Đọc số hàng SQLite | `changes()` | Không tính tác động cascade gián tiếp |
| Đọc số hàng Oracle PL/SQL | `SQL%ROWCOUNT` | Đọc ngay sau câu SQL quan tâm |
| Khóa ngoại `CASCADE` | Tự xóa hàng con | Không tự cộng vào số hàng DELETE cha |
| Khóa ngoại `RESTRICT/NO ACTION` | Có thể ngăn xóa cha | Xem đúng ràng buộc và nghiệp vụ |
| Xóa từng lô | Chọn khóa theo thứ tự rồi DELETE | Kiểm tra lô, khóa, retry và giao dịch |
| Tránh xóa nhầm khi có thay đổi đồng thời | `WHERE id = ? AND status/version = ?` | Số hàng 0 có thể báo trạng thái cũ |
| Chỉ muốn ẩn bản ghi | `UPDATE` trạng thái/`deleted_at` | Không bắt buộc hard delete |

## Kết luận

Một câu `DELETE` có điều kiện chỉ an toàn khi ta **hiểu rõ những hàng nào được phép xóa và kiểm chứng kết quả thực tế**.

- `WHERE` quyết định phạm vi xóa; phải kiểm tra toán tử ngày, dấu ngoặc `AND`/`OR`, `NULL` và điều kiện quan hệ.
- Trước khi xóa, dùng `SELECT` với cùng điều kiện để xem **ID, số lượng và dữ liệu của tập ứng viên**.
- Trong PostgreSQL, `DELETE ... RETURNING` cho biết chính xác những hàng đích đã xóa; `BEGIN ... ROLLBACK` cho phép quan sát và hoàn tác trong một giao dịch thử nghiệm.
- Phải phân biệt **số hàng khớp ở lần xem trước**, **số hàng bị xóa trực tiếp**, **số hàng liên quan bị cascade** và **tổng tác động nghiệp vụ**.
- Với ứng dụng, dùng API số hàng bị ảnh hưởng hoặc cơ chế như `@@ROWCOUNT`, `ROW_COUNT()`, `changes()`, `SQL%ROWCOUNT` theo đúng DBMS. Nếu cần danh tính hàng, dùng `RETURNING`/`OUTPUT` hay cơ chế tương đương.
- Số hàng bị xóa đúng kỳ vọng là một tín hiệu hữu ích, **không thay thế việc kiểm tra tập ID**, nhất là khi có cập nhật đồng thời.
- Với dữ liệu lớn hoặc có yêu cầu lưu trữ, cân nhắc xóa theo lô, khóa ngoại, audit, xóa mềm và giao dịch phù hợp.

Thói quen quan trọng nhất là coi thao tác xóa như một quy trình gồm **xác định điều kiện → xem trước → xóa có kiểm soát → xác minh số hàng và danh tính → commit hoặc rollback**. Làm được từng bước một cách rõ ràng sẽ giúp tránh những sự cố mất dữ liệu khó khôi phục trong hệ thống SQL thực tế.
