# Khóa và đồng thời

## SELECT FOR UPDATE và SELECT FOR SHARE

InnoDB hỗ trợ hai dạng locking read phổ biến: `SELECT ... FOR UPDATE` và `SELECT ... FOR SHARE`. Chúng cho phép transaction đọc các hàng hiện hành đồng thời đặt khóa trên những hàng được đọc. Cách này hữu ích khi ứng dụng cần kiểm tra trạng thái rồi quyết định cập nhật, giữ một hàng ổn định trong lúc thực hiện nghiệp vụ hoặc phân chia công việc giữa nhiều worker.

Hai câu lệnh có mục đích khác nhau. `FOR UPDATE` lấy khóa độc quyền, phù hợp khi transaction dự định sửa hoặc xóa hàng. `FOR SHARE` lấy khóa chia sẻ, cho phép transaction khác cũng đọc có khóa chia sẻ nhưng ngăn thay đổi xung đột cho đến khi transaction kết thúc. Chúng là công cụ kiểm soát đồng thời ở mức hàng; muốn sử dụng đúng phải hiểu transaction scope, phạm vi khóa theo chỉ mục, mức cô lập và cách xử lý chờ khóa.

### 1. Locking read khác SELECT thường như thế nào?

Một `SELECT` thông thường trong InnoDB là consistent read. Nó đọc phiên bản phù hợp với read view theo MVCC và không lấy khóa hàng chỉ vì đọc. Nếu transaction khác đang giữ khóa độc quyền trên một hàng, consistent read thường vẫn có thể đọc phiên bản đã commit trước đó mà không phải chờ transaction ghi kết thúc.

`SELECT ... FOR UPDATE` và `SELECT ... FOR SHARE` là locking read. Chúng đọc dữ liệu hiện hành và đặt khóa trên các hàng/index record được truy cập. Nếu khóa xung đột đang được transaction khác giữ, câu lệnh phải chờ, hoặc trả lỗi/bỏ qua hàng nếu dùng `NOWAIT`/`SKIP LOCKED`.

| Đặc điểm | `SELECT` thường | `SELECT ... FOR SHARE` | `SELECT ... FOR UPDATE` |
| --- | --- | --- | --- |
| Kiểu đọc | Consistent read theo MVCC | Current/locking read | Current/locking read |
| Khóa hàng | Không lấy khóa hàng chỉ để đọc | Shared lock (S) | Exclusive lock (X) |
| Transaction khác đọc thường | Thường đọc được phiên bản đã commit mà không chờ khóa hàng | Đọc thường vẫn có thể dùng MVCC | Đọc thường vẫn có thể dùng MVCC |
| Transaction khác locking read | Không tạo khóa hàng để cản trở | `FOR SHARE` tương thích; `FOR UPDATE` xung đột | `FOR SHARE` và `FOR UPDATE` đều xung đột |
| Mục đích | Đọc báo cáo hoặc snapshot nhất quán | Giữ hàng ổn định khi cần đọc có phối hợp | Đọc hàng sẽ được cập nhật/xóa hoặc được claim |

Khóa của locking read thường được giữ đến khi transaction `COMMIT` hoặc `ROLLBACK`. Vì vậy, một transaction có thể đọc cùng một giá trị hiện hành rồi giữ quyền bảo vệ hàng đó trong khi thực hiện thêm các câu lệnh liên quan.

### 2. Cú pháp FOR UPDATE và FOR SHARE

Cú pháp cơ bản trong MySQL 8.0:

```sql
SELECT danh_sach_cot
FROM ten_bang
WHERE dieu_kien
FOR UPDATE;

SELECT danh_sach_cot
FROM ten_bang
WHERE dieu_kien
FOR SHARE;
```

Có thể kết hợp với `JOIN`, `ORDER BY`, `LIMIT` và các tùy chọn xử lý khóa:

```sql
SELECT id, status
FROM orders
WHERE status = 'pending'
ORDER BY id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

Trong MySQL 8.0, `FOR SHARE` là cú pháp hiện đại thay cho cách viết cũ `LOCK IN SHARE MODE`. Với truy vấn nối nhiều bảng, phiên bản hỗ trợ cú pháp `OF` để chỉ định bảng cần khóa, ví dụ `FOR UPDATE OF o`. Nếu không chỉ định phạm vi, locking clause áp dụng cho các bảng được tham chiếu trong query block theo quy tắc của MySQL.

Hai mệnh đề này cần được đặt trong một transaction có phạm vi đủ dài. Cách rõ ràng nhất là dùng `START TRANSACTION`, thực hiện locking read và các thao tác liên quan, rồi kết thúc bằng `COMMIT` hoặc `ROLLBACK`:

```sql
START TRANSACTION;

SELECT id, status
FROM orders
WHERE id = 1001
FOR UPDATE;

-- Kiểm tra và thực hiện nghiệp vụ liên quan ở đây.

COMMIT;
```

Nếu chỉ chạy locking read như một statement độc lập trong chế độ autocommit, transaction ngầm kết thúc ngay sau statement và khóa được giải phóng; các câu lệnh sau không còn được bảo vệ bởi khóa đó. Không nên mở transaction rồi để nó tồn tại trong lúc chờ người dùng, gọi dịch vụ bên ngoài hoặc xử lý tác vụ kéo dài.

### 3. SELECT ... FOR UPDATE: khóa độc quyền để chuẩn bị ghi

`FOR UPDATE` yêu cầu InnoDB lấy khóa độc quyền trên các hàng được đọc. Transaction khác không thể đồng thời lấy shared lock hoặc exclusive lock xung đột trên cùng hàng cho đến khi khóa được giải phóng. Tuy nhiên, consistent read thông thường vẫn có thể đọc phiên bản cũ đã commit nhờ MVCC.

Ví dụ, một ứng dụng cần kiểm tra số lượng tồn kho rồi trừ một đơn vị:

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory (id, sku, quantity)
VALUES (1, 'KB-100', 5);
```

Transaction giữ khóa độc quyền trong lúc kiểm tra và cập nhật:

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE id = 1
FOR UPDATE;

-- Ứng dụng kiểm tra quantity > 0.

UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1
  AND quantity > 0;

-- Kiểm tra số hàng bị tác động trước khi quyết định commit.
COMMIT;
```

Nếu hai phiên cùng chạy quy trình này cho `id = 1`, phiên lấy khóa trước sẽ tiếp tục. Phiên còn lại phải đợi. Sau khi phiên đầu commit, phiên sau tiếp tục trên trạng thái hiện hành và đọc được số lượng mới. Nhờ đó, hai phiên không cùng dựa trên một giá trị tồn kho cũ để trừ hàng.

Trong ví dụ thực tế, ứng dụng cần kiểm tra kết quả của `UPDATE`. Nếu không có hàng nào được cập nhật, tồn kho có thể đã bằng 0 hoặc điều kiện nghiệp vụ không còn đúng; khi đó cần rollback hoặc trả kết quả hết hàng phù hợp. `FOR UPDATE` bảo vệ đoạn đọc-ghi, nhưng không tự thay thế việc kiểm tra điều kiện và xử lý kết quả.

### 4. SELECT ... FOR SHARE: khóa chia sẻ để giữ dữ liệu ổn định

`FOR SHARE` lấy shared lock trên các hàng được đọc. Nhiều transaction có thể cùng giữ shared lock trên một hàng. Nhưng transaction khác không thể sửa hoặc xóa hàng đó trong khi shared lock còn tồn tại, và không thể lấy exclusive lock để cập nhật.

Ví dụ, transaction đọc một cấu hình giá và cần bảo đảm giá không bị thay đổi trong suốt một phép tính gồm nhiều bước:

```sql
START TRANSACTION;

SELECT price, currency
FROM product_price
WHERE product_id = 501
FOR SHARE;

-- Thực hiện các truy vấn đọc liên quan và tính toán nghiệp vụ.

COMMIT;
```

Trong thời gian transaction giữ shared lock, một phiên khác muốn cập nhật giá của `product_id = 501` phải chờ. Các transaction khác vẫn có thể cùng đọc hàng bằng `FOR SHARE`.

Chỉ dùng `FOR SHARE` khi thực sự cần ngăn thay đổi đồng thời. Nếu chỉ cần một ảnh chụp nhất quán để hiển thị hoặc tổng hợp báo cáo, `SELECT` thường thường phù hợp hơn và ít gây cản trở ghi hơn.

### 5. Khả năng tương thích của shared lock và exclusive lock

Với cùng một hàng, quy tắc tương thích cơ bản như sau:

| Khóa đang được giữ | Yêu cầu `FOR SHARE` (S) | Yêu cầu `FOR UPDATE` (X) |
| --- | --- | --- |
| Không có khóa xung đột | Được cấp | Được cấp |
| Shared lock (S) | Có thể cùng tồn tại | Phải chờ |
| Exclusive lock (X) | Phải chờ | Phải chờ |

Một câu `UPDATE` hoặc `DELETE` cũng cần khóa độc quyền trên hàng mà nó thay đổi. Vì vậy, nó phải chờ nếu hàng đang được transaction khác giữ shared lock hoặc exclusive lock.

Ví dụ với hai phiên:

**Phiên A:**

```sql
START TRANSACTION;

SELECT balance
FROM account
WHERE id = 10
FOR SHARE;
```

**Phiên B:**

```sql
UPDATE account
SET balance = balance - 100
WHERE id = 10;
-- Phải chờ shared lock của phiên A được giải phóng.
```

**Phiên A:**

```sql
COMMIT;
```

Sau khi A commit, khóa chia sẻ được giải phóng và B có thể tiếp tục. Nếu A giữ transaction quá lâu, các phiên ghi liên quan cũng phải chờ lâu theo.

### 6. FOR SHARE rồi nâng cấp lên FOR UPDATE có thể gây deadlock

Một lỗi thiết kế thường gặp là hai transaction cùng đọc một hàng bằng `FOR SHARE`, sau đó cả hai đều muốn nâng khóa lên exclusive để cập nhật. Shared lock của hai transaction tương thích nên cả hai có thể đọc thành công. Nhưng khi mỗi bên yêu cầu exclusive lock, mỗi bên phải chờ shared lock mà bên kia đang giữ. InnoDB phát hiện chu trình chờ và hủy một transaction để phá deadlock.

Mô phỏng:

```sql
-- Phiên A
START TRANSACTION;
SELECT quantity FROM inventory WHERE id = 1 FOR SHARE;

-- Phiên B
START TRANSACTION;
SELECT quantity FROM inventory WHERE id = 1 FOR SHARE;

-- Phiên A: cần nâng lên exclusive để ghi
UPDATE inventory SET quantity = quantity - 1 WHERE id = 1;
-- Chờ phiên B.

-- Phiên B: cũng cần nâng lên exclusive
UPDATE inventory SET quantity = quantity - 1 WHERE id = 1;
-- Hai phiên tạo chu trình chờ; một transaction có thể bị rollback do deadlock.
```

Nếu ngay từ đầu biết sẽ cập nhật hoặc xóa hàng, hãy dùng `FOR UPDATE` thay cho `FOR SHARE`. Nếu chỉ cần kiểm tra điều kiện và thay đổi một giá trị, cân nhắc một câu DML nguyên tử có điều kiện trong `WHERE` để tránh tách thao tác thành nhiều bước.

### 7. Phạm vi khóa phụ thuộc chỉ mục và mức cô lập

Locking read không nhất thiết chỉ khóa đúng số hàng được trả về. InnoDB thường khóa các index record mà quá trình thực thi quét qua; phạm vi cụ thể phụ thuộc điều kiện, chỉ mục được chọn, kế hoạch truy cập và mức cô lập.

- Nếu điều kiện tìm kiếm dùng khóa chính hoặc unique index với phép so sánh bằng cho một hàng tồn tại, InnoDB thường chỉ cần khóa record tương ứng.
- Nếu điều kiện quét một phạm vi hoặc dùng chỉ mục không duy nhất ở `REPEATABLE READ`, InnoDB có thể dùng next-key lock, kết hợp record lock với gap lock trên khoảng chỉ mục liền trước.
- Ở `READ COMMITTED`, gap locking cho tìm kiếm và quét thông thường thường được tắt; ngoại lệ vẫn tồn tại cho kiểm tra khóa ngoại và kiểm tra khóa trùng.
- Nếu thiếu chỉ mục phù hợp, MySQL có thể phải quét nhiều index record hơn dự kiến, làm phạm vi khóa và số transaction phải chờ tăng lên.

Ví dụ khóa một đơn hàng theo khóa chính:

```sql
START TRANSACTION;

SELECT id, status
FROM orders
WHERE id = 1001
FOR UPDATE;

COMMIT;
```

Điều kiện bằng trên khóa chính giúp xác định một record cụ thể. Ngược lại, truy vấn theo trạng thái có thể phải khóa nhiều record phù hợp trong phạm vi index:

```sql
START TRANSACTION;

SELECT id
FROM orders
WHERE status = 'pending'
ORDER BY created_at
FOR UPDATE;

COMMIT;
```

Nếu bảng có nhiều đơn pending, truy vấn thứ hai có thể giữ rất nhiều khóa. Một chỉ mục phù hợp như `(status, created_at, id)` có thể giảm lượng dữ liệu phải quét và giúp thứ tự truy cập có thể dự đoán hơn. Dù vậy, chỉ mục không tự giới hạn số hàng bị khóa; nếu chỉ cần một lô nhỏ, phải thiết kế `LIMIT` và điều kiện chọn phù hợp.

Với secondary index, InnoDB cũng cần khóa record tương ứng trong clustered index để bảo vệ hàng dữ liệu. Vì thế, phạm vi khóa không chỉ được hiểu bằng tên cột xuất hiện trong `WHERE`.

### 8. NOWAIT và SKIP LOCKED khi không muốn chờ khóa

MySQL hỗ trợ hai tùy chọn cho locking read:

- `NOWAIT`: nếu hàng cần khóa đang bị transaction khác khóa xung đột, câu lệnh trả lỗi ngay thay vì chờ.
- `SKIP LOCKED`: bỏ qua các hàng đang bị khóa xung đột và trả về những hàng có thể khóa ngay.

Ví dụ với `NOWAIT`:

```sql
START TRANSACTION;

SELECT id, status
FROM orders
WHERE id = 1001
FOR UPDATE NOWAIT;

COMMIT;
```

Nếu phiên khác đang giữ khóa xung đột trên hàng `id = 1001`, ứng dụng nhận lỗi ngay và có thể trả thông báo bận, thử lại sau hoặc chọn luồng xử lý khác. Không nên retry liên tục không giới hạn vì điều đó có thể làm tăng tải và cạnh tranh khóa.

`SKIP LOCKED` thường hữu ích cho bảng hàng đợi, nơi nhiều worker cùng nhận việc:

```sql
START TRANSACTION;

SELECT id
FROM job_queue
WHERE status = 'pending'
ORDER BY id
LIMIT 10
FOR UPDATE SKIP LOCKED;

-- Ứng dụng nhận danh sách id rồi cập nhật các hàng đó.
UPDATE job_queue
SET status = 'processing', claimed_by = 'worker-A'
WHERE id IN (101, 102, 103);

COMMIT;
```

Danh sách `id` trong câu `UPDATE` phải là các giá trị thực tế mà câu `SELECT` trả về; ví dụ trên minh họa dạng câu lệnh. Khi worker A đã khóa một số hàng, worker B có thể chạy cùng truy vấn `SKIP LOCKED` và lấy các hàng chưa bị khóa thay vì chờ A.

Đổi lại, kết quả `SKIP LOCKED` không phải một ảnh chụp đầy đủ nhất quán của toàn bộ hàng phù hợp: các hàng đang bị khóa bị bỏ qua. Chỉ dùng nó cho quy trình nhận việc hoặc trường hợp chấp nhận bỏ qua tạm thời. Không dùng để tạo báo cáo cần đầy đủ dữ liệu. `NOWAIT` và `SKIP LOCKED` xử lý xung đột row lock; khóa ở cấp bảng hoặc metadata vẫn có thể khiến câu lệnh chờ.

Đối với hàng đợi production, nên cập nhật trạng thái claim và thông tin worker trong cùng transaction với locking read, sau đó commit nhanh. Công việc xử lý dài nên thực hiện sau khi đã claim; cần có lease hoặc thời hạn nhận việc để phục hồi hàng bị bỏ lại nếu worker dừng đột ngột. Nếu commit trước khi đánh dấu trạng thái, worker khác có thể nhận lại cùng một hàng sau khi khóa được giải phóng.

### 9. Locking clause trong JOIN và subquery

Với truy vấn nhiều bảng, locking clause có thể khóa các hàng được đọc từ những bảng liên quan. Nếu chỉ muốn khóa bảng đích, có thể dùng `OF` khi phiên bản MySQL hỗ trợ:

```sql
START TRANSACTION;

SELECT o.id, o.status, c.name
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE o.id = 1001
FOR UPDATE OF o;

COMMIT;
```

Trong ví dụ, mục tiêu là khóa hàng đơn hàng của `o`; bảng `customers` chỉ được đọc để lấy tên. Nếu bỏ `OF o`, locking clause áp dụng rộng hơn theo quy tắc của query block và có thể khóa hàng ở nhiều bảng được tham chiếu.

Một điểm dễ bỏ sót là locking clause ở query block bên ngoài không tự động khóa các hàng được đọc trong subquery. Nếu cần khóa cả bảng trong subquery, phải đặt locking clause trong chính subquery đó:

```sql
START TRANSACTION;

SELECT o.id
FROM orders AS o
WHERE o.customer_id = (
    SELECT c.id
    FROM customers AS c
    WHERE c.email = 'buyer@example.com'
    FOR SHARE
)
FOR UPDATE;

COMMIT;
```

Ở đây, `FOR UPDATE` khóa các hàng đơn hàng được truy vấn ngoài, còn `FOR SHARE` khóa hàng khách hàng được truy vấn trong. Hãy chỉ khóa các bảng thực sự cần bảo vệ để giảm cạnh tranh và tránh giữ khóa không cần thiết.

### 10. Deadlock, lock wait timeout và cách xử lý

Locking read giúp phối hợp các transaction nhưng không loại bỏ deadlock. Deadlock có thể xảy ra khi các transaction khóa nhiều hàng theo thứ tự khác nhau, nâng shared lock lên exclusive lock hoặc giữ khóa quá lâu trong khi chờ tài nguyên khác.

Một số nguyên tắc giảm rủi ro:

1. Truy cập nhiều hàng theo một thứ tự nhất quán ở mọi luồng nghiệp vụ.
2. Dùng điều kiện tìm kiếm có chỉ mục để thu hẹp số record bị quét và khóa.
3. Giữ transaction ngắn; không gọi HTTP, gửi email hoặc chờ người dùng trong khi đang giữ khóa.
4. Dùng `FOR UPDATE` ngay từ đầu nếu chắc chắn sẽ sửa hàng; tránh nâng cấp từ `FOR SHARE` không cần thiết.
5. Xử lý lỗi deadlock bằng cách thử lại toàn bộ transaction sau khi rollback, với giới hạn số lần và backoff phù hợp.
6. Phân biệt deadlock với lock wait timeout; ghi log đủ thông tin để điều tra transaction, truy vấn và thứ tự khóa.

InnoDB tự phát hiện deadlock và chọn một transaction làm nạn nhân để rollback. Lock wait timeout thường phát sinh khi phải chờ khóa quá thời gian cấu hình; tùy cấu hình, chỉ statement bị lỗi hoặc toàn transaction bị rollback. Ứng dụng nên xử lý rõ trạng thái transaction và không tiếp tục sử dụng một transaction đã bị rollback ngoài dự kiến.

### 11. Kiểm tra transaction và khóa đang chờ

Khi một locking read bị chờ lâu, hãy xác định transaction nào đang giữ khóa, transaction nào đang đợi và truy vấn nào tạo ra xung đột. Có thể bắt đầu bằng:

```sql
SELECT CONNECTION_ID();
SELECT @@autocommit, @@transaction_isolation;
SHOW ENGINE INNODB STATUS;
```

`SHOW ENGINE INNODB STATUS` cung cấp thông tin về deadlock gần nhất và trạng thái InnoDB. Trong MySQL 8.0, các bảng hệ thống trong `performance_schema` và các view `sys` có thể hỗ trợ xem transaction, data lock và lock wait; tên cột và quyền truy cập phụ thuộc phiên bản/cấu hình. Ví dụ truy vấn tổng quan transaction đang mở:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx;
```

Kết hợp thông tin transaction với `EXPLAIN` của câu truy vấn để tìm nguyên nhân quét quá rộng hoặc dùng chỉ mục không phù hợp. Khi xử lý sự cố, không vội `KILL` session trước khi xác định nghiệp vụ và tác động của rollback.

### 12. Checklist chọn locking read

1. Dùng `SELECT` thường nếu chỉ cần đọc snapshot nhất quán và không cần ngăn transaction khác cập nhật.
2. Dùng `SELECT ... FOR UPDATE` khi transaction sẽ sửa/xóa hàng hoặc cần claim hàng độc quyền.
3. Dùng `SELECT ... FOR SHARE` khi nhiều transaction có thể cùng đọc nhưng phải ngăn cập nhật xung đột trong thời gian ngắn.
4. Bọc locking read và các câu lệnh phụ thuộc vào nó trong cùng transaction; commit hoặc rollback sớm.
5. Kiểm tra chỉ mục và phạm vi quét để tránh khóa nhiều record/gap hơn cần thiết.
6. Dùng `NOWAIT` nếu nghiệp vụ cần phản hồi ngay khi bận; dùng `SKIP LOCKED` cho hàng đợi chấp nhận bỏ qua hàng đang được worker khác xử lý.
7. Chuẩn bị xử lý deadlock, timeout và retry an toàn; không retry vô hạn.
8. Với nhiều bảng hoặc subquery, xác định rõ query block và bảng thực sự cần khóa.

`FOR UPDATE` và `FOR SHARE` biến một lần đọc thành thao tác đọc có khóa, cho phép transaction phối hợp với nhau trên dữ liệu hiện hành. Chọn đúng loại khóa, giới hạn phạm vi truy cập và kết thúc transaction đúng lúc giúp bảo vệ tính đúng đắn của nghiệp vụ mà vẫn giữ khả năng xử lý đồng thời của InnoDB.
