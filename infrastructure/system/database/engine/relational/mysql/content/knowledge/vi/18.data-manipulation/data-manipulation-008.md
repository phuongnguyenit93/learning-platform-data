# Thay đổi dữ liệu

## ORDER BY/LIMIT trong DML và giới hạn theo dạng câu lệnh

Trong MySQL, `ORDER BY` và `LIMIT` giúp chọn một tập con bản ghi theo thứ tự xác định khi cập nhật hoặc xóa dữ liệu theo từng đợt. Tuy nhiên, hai mệnh đề này không được phép đặt tùy ý ở cuối mọi câu lệnh DML. Khả năng sử dụng phụ thuộc vào dạng cú pháp cụ thể: `UPDATE` và `DELETE` một bảng hỗ trợ trực tiếp; dạng nhiều bảng không hỗ trợ; còn `INSERT ... SELECT` chỉ dùng chúng bên trong truy vấn `SELECT` nguồn.

Nắm rõ giới hạn cú pháp giúp tránh lỗi khi viết SQL, đồng thời giúp thiết kế các đợt thay đổi dữ liệu có thể kiểm soát, kiểm tra kế hoạch truy cập và vận hành an toàn trên bảng lớn.

### 1. Phân biệt vị trí của ORDER BY và LIMIT

`ORDER BY` xác định thứ tự các hàng được xét hoặc xử lý. `LIMIT` giới hạn số hàng trong tập kết quả phù hợp được tác động. Trong DML, chúng có ý nghĩa theo từng loại câu lệnh:

| Dạng câu lệnh MySQL | `ORDER BY` / `LIMIT` ở cấp câu lệnh DML | Cách hiểu |
| --- | --- | --- |
| `UPDATE` một bảng | Có cả hai | Sắp thứ tự các hàng được cập nhật và giới hạn số hàng khớp điều kiện |
| `DELETE` một bảng | Có cả hai | Sắp thứ tự các hàng bị xóa và giới hạn số hàng bị xóa |
| `UPDATE` nhiều bảng, thường dùng `JOIN` | Không | Cú pháp nhiều bảng không có nhánh `ORDER BY` hoặc `LIMIT` |
| `DELETE` nhiều bảng, như `DELETE t1 FROM ... JOIN ...` | Không | Cú pháp nhiều bảng không có nhánh `ORDER BY` hoặc `LIMIT` |
| `INSERT ... VALUES` hoặc `INSERT ... SET` | Không | Không có tập truy vấn nguồn để đặt `ORDER BY` / `LIMIT` |
| `INSERT ... SELECT` | Có trong `SELECT` nguồn | Hai mệnh đề giới hạn và sắp xếp các hàng được truy vấn để chèn |
| `REPLACE ... VALUES` hoặc `REPLACE ... SET` | Không | Không hỗ trợ mệnh đề cấp lệnh này |
| `REPLACE ... SELECT` | Có trong `SELECT` nguồn | Hai mệnh đề thuộc truy vấn nguồn, không thuộc phần `REPLACE` bên ngoài |
| `TRUNCATE TABLE` | Không | Đây là lệnh DDL làm rỗng toàn bảng, không phải DML có thể lọc theo hàng |

Điểm cần nhớ là phải đọc đúng **dạng cú pháp** đang dùng. Một câu `UPDATE` chỉ cập nhật một bảng đích thông qua dạng `UPDATE ... JOIN` vẫn thuộc cú pháp cập nhật nhiều bảng của MySQL; không thể thêm `ORDER BY` hoặc `LIMIT` vào cuối câu lệnh đó.

### 2. UPDATE một bảng: chọn hàng và giới hạn số hàng cập nhật

Cú pháp rút gọn:

```sql
UPDATE ten_bang
SET cot = gia_tri
WHERE dieu_kien
ORDER BY cot_sap_xep [ASC | DESC], khoa_chinh
LIMIT so_hang;
```

Ví dụ, chuyển tối đa 200 đơn hàng đã hết hạn từ `pending` sang `expired`:

```sql
UPDATE orders
SET status = 'expired'
WHERE status = 'pending'
  AND expires_at < CURRENT_TIMESTAMP
ORDER BY expires_at ASC, id ASC
LIMIT 200;
```

MySQL xét các hàng thỏa `WHERE` theo thứ tự `expires_at`, sau đó dùng `id` để phân định các hàng có cùng thời điểm hết hạn. Tối đa 200 hàng khớp điều kiện được cập nhật trong lần chạy này.

Với `UPDATE`, `LIMIT` là giới hạn số **hàng khớp điều kiện**, không phải số hàng có giá trị thực sự thay đổi. Nếu một hàng đã mang giá trị được gán, hàng đó vẫn có thể được tính vào giới hạn khi nó khớp `WHERE`. Vì vậy, khi cần xử lý theo lô, điều kiện `WHERE` nên loại các hàng đã xử lý khỏi những lần chạy tiếp theo, chẳng hạn bằng cách đổi trạng thái từ `pending` sang `expired`.

`ORDER BY` còn có thể quyết định thứ tự cập nhật, hữu ích khi việc cập nhật có ràng buộc duy nhất. Ví dụ, nếu `position` có unique index, tăng giá trị theo thứ tự giảm dần sẽ xử lý vị trí lớn trước để tránh đụng vào giá trị của hàng chưa được cập nhật:

```sql
UPDATE sequence_item
SET position = position + 1
ORDER BY position DESC;
```

Thứ tự này chỉ có tác dụng trong quá trình thực thi câu lệnh; nó không tạo ra cam kết rằng những lần `SELECT` sau sẽ trả hàng theo thứ tự đó. Muốn kết quả truy vấn có thứ tự, vẫn phải viết `ORDER BY` trong chính câu `SELECT`.

### 3. DELETE một bảng: xóa theo lô

Cú pháp rút gọn:

```sql
DELETE FROM ten_bang
WHERE dieu_kien
ORDER BY cot_sap_xep [ASC | DESC], khoa_chinh
LIMIT so_hang;
```

Ví dụ, xóa tối đa 500 dòng nhật ký cũ nhất:

```sql
DELETE FROM event_log
WHERE created_at < '2026-01-01'
ORDER BY created_at ASC, id ASC
LIMIT 500;
```

`ORDER BY` quyết định những dòng nào được chọn trước khi áp dụng giới hạn. Nếu bỏ `ORDER BY`, MySQL có thể xóa bất kỳ 500 dòng nào trong số các dòng thỏa điều kiện; ứng dụng không nên dựa vào thứ tự vật lý của bảng hay thứ tự tình cờ mà một lần chạy trả về.

Thêm khóa duy nhất như `id` làm tiêu chí cuối giúp thứ tự ổn định khi nhiều dòng có cùng `created_at`. Nếu chỉ sắp xếp theo thời gian mà nhiều dòng trùng thời gian, thứ tự giữa các dòng đó không được xác định đầy đủ; ở các lần chạy khác nhau, nhóm dòng được chọn có thể khác.

### 4. LIMIT trong UPDATE và DELETE không có OFFSET

Ở cú pháp `UPDATE` một bảng và `DELETE` một bảng, MySQL nhận dạng dạng `LIMIT so_hang`:

```sql
DELETE FROM event_log
WHERE severity = 'debug'
ORDER BY id
LIMIT 1000;
```

Không dùng dạng phân trang `LIMIT offset, so_hang` hoặc `LIMIT so_hang OFFSET offset` trực tiếp ở cuối các câu lệnh `UPDATE` / `DELETE` này. Hai dạng có `OFFSET` thuộc cú pháp truy vấn `SELECT`.

Để xử lý tiếp một lô sau, có thể chạy lại cùng câu lệnh nếu thao tác làm các hàng vừa xử lý không còn thỏa `WHERE` (ví dụ xóa hàng, hoặc đổi trạng thái của hàng). Nếu cần tiến theo một mốc khóa, dùng điều kiện khóa trong `WHERE`, chẳng hạn `id > gia_tri_id_cuoi`, kết hợp `ORDER BY id LIMIT so_hang`. Cách này tránh phải bỏ qua một số lượng lớn hàng bằng offset và giúp xác định rõ điểm tiếp tục.

### 5. INSERT ... SELECT: giới hạn nằm trong truy vấn nguồn

`INSERT ... VALUES` và `INSERT ... SET` không có `ORDER BY` hoặc `LIMIT` ở cấp câu lệnh. Ví dụ sau chèn hai giá trị đã nêu trực tiếp, không có mệnh đề giới hạn:

```sql
INSERT INTO tag (name)
VALUES ('database'), ('mysql');
```

Với `INSERT ... SELECT`, có thể sắp xếp và giới hạn tập hàng do `SELECT` tạo ra:

```sql
INSERT INTO archived_orders (id, customer_id, created_at)
SELECT id, customer_id, created_at
FROM orders
WHERE created_at < '2025-01-01'
ORDER BY created_at ASC, id ASC
LIMIT 500;
```

Trong ví dụ này, `ORDER BY` và `LIMIT` thuộc truy vấn `SELECT`. Chúng quyết định tối đa 500 hàng nguồn nào được đưa vào thao tác chèn. Không được hiểu đây là một `LIMIT` độc lập đặt sau toàn bộ câu lệnh `INSERT`.

Quy tắc vị trí tương tự áp dụng cho `REPLACE ... SELECT`. Với `INSERT ... ON DUPLICATE KEY UPDATE`, phần cập nhật khi trùng khóa không có `ORDER BY` / `LIMIT` riêng; nếu câu lệnh dùng `INSERT ... SELECT`, các mệnh đề này vẫn thuộc truy vấn nguồn.

### 6. UPDATE / DELETE nhiều bảng không nhận ORDER BY hoặc LIMIT

MySQL có cú pháp cập nhật nhiều bảng, thường kết hợp bảng đích với bảng khác qua `JOIN`:

```sql
UPDATE orders AS o
JOIN customers AS c ON c.id = o.customer_id
SET o.review_flag = 1
WHERE c.segment = 'business';
```

Đây là cú pháp `UPDATE` nhiều bảng. Dù chỉ gán cột của `orders`, không thể nối thêm `ORDER BY` hoặc `LIMIT` vào cuối câu lệnh. Câu `DELETE` nhiều bảng cũng có giới hạn tương tự:

```sql
DELETE o
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE c.segment = 'inactive';
```

Không thêm `ORDER BY ... LIMIT ...` vào dạng `DELETE ... FROM ... JOIN ...` hoặc dạng `DELETE ... USING ...`. Nếu cần giới hạn số khóa được chọn từ một phép nối, hãy thực hiện việc chọn khóa trong một truy vấn riêng, sau đó dùng tập khóa đó cho thao tác nhiều bảng.

Ví dụ dùng bảng tạm để giới hạn trước 100 đơn hàng theo thời điểm tạo, sau đó xóa các đơn đã chọn:

```sql
CREATE TEMPORARY TABLE batch_order_ids (
    id BIGINT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

INSERT INTO batch_order_ids (id)
SELECT o.id
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE c.segment = 'inactive'
ORDER BY o.created_at ASC, o.id ASC
LIMIT 100;

DELETE o
FROM orders AS o
JOIN batch_order_ids AS b ON b.id = o.id;

DROP TEMPORARY TABLE batch_order_ids;
```

Kiểu dữ liệu của `batch_order_ids.id` cần khớp với kiểu và signedness của `orders.id`. Giới hạn 100 nằm trong `INSERT ... SELECT`; câu `DELETE` nhiều bảng chỉ dùng phép nối với danh sách khóa đã chọn nên không vi phạm giới hạn cú pháp. Nếu có nhiều phiên đồng thời sửa cùng dữ liệu, cần thiết kế transaction và cơ chế khóa/nhận việc phù hợp để tập khóa được chọn không bị thay đổi ngoài dự kiến giữa bước chọn và bước xóa.

### 7. Chọn chỉ mục và vận hành các lô DML

`ORDER BY` và `LIMIT` chỉ hữu ích khi tập hàng cần xử lý được tìm kiếm với chi phí hợp lý. Với câu cập nhật đơn hàng ở trên, một chỉ mục bắt đầu bằng cột lọc bằng rồi đến các cột sắp xếp có thể giúp MySQL tìm hàng theo thứ tự hiệu quả hơn, ví dụ cân nhắc chỉ mục `(status, expires_at, id)`. Chỉ mục thực tế phải dựa trên phân bố dữ liệu, các truy vấn khác và chi phí ghi bổ sung; không tạo chỉ mục chỉ vì một câu lệnh có `LIMIT`.

Có thể kiểm tra truy vấn chọn cùng tập khóa bằng `EXPLAIN`:

```sql
EXPLAIN
SELECT id
FROM orders
WHERE status = 'pending'
  AND expires_at < CURRENT_TIMESTAMP
ORDER BY expires_at ASC, id ASC
LIMIT 200;
```

Truy vấn này giúp xem MySQL dự kiến dùng chỉ mục nào, ước lượng số hàng phải đọc và có cần sắp xếp bổ sung hay không. Khi dữ liệu lớn, cần chú ý trường hợp phải đọc nhiều hàng rồi mới loại bỏ phần lớn chúng hoặc phải sort một tập rất lớn trước khi lấy `LIMIT`.

Khi chạy DML theo lô trong InnoDB, nên chọn kích thước lô phù hợp với thời gian khóa, dung lượng undo/redo và khả năng phục hồi. Các lô nhỏ thường dễ kiểm soát hơn một câu lệnh tác động đến hàng triệu bản ghi trong một transaction dài. Tuy nhiên, `LIMIT` tự nó không bảo đảm một quy trình xử lý hàng đợi an toàn khi có nhiều worker: các phiên đồng thời có thể cùng nhìn thấy ứng viên hoặc dữ liệu có thể đổi giữa các bước. Khi yêu cầu xử lý đúng một lần, hãy kết hợp transaction, khóa hàng hoặc cơ chế claim trạng thái và thiết kế thao tác có thể chạy lại an toàn.

### 8. Checklist trước khi chạy

1. Xác định câu lệnh đang dùng cú pháp một bảng hay nhiều bảng; `UPDATE ... JOIN` và `DELETE ... FROM ... JOIN` thuộc dạng nhiều bảng.
2. Đặt `ORDER BY` / `LIMIT` đúng vị trí mà cú pháp của câu lệnh cho phép. Với `INSERT ... SELECT`, chúng nằm trong `SELECT` nguồn.
3. Khi dùng `LIMIT` để chọn một lô, thêm khóa duy nhất vào cuối `ORDER BY` để kết quả chọn ổn định.
4. Với `UPDATE` / `DELETE` một bảng, dùng `LIMIT so_hang`; không đặt offset ở cấp DML.
5. Kiểm tra điều kiện `WHERE`, chỉ mục và kế hoạch truy cập trước khi chạy trên bảng lớn.
6. Nếu chia lô, bảo đảm hàng đã xử lý không bị chọn lại ngoài ý muốn và có phương án transaction/đồng thời phù hợp.

Hiểu đúng vị trí của `ORDER BY` và `LIMIT` giúp viết được câu lệnh hợp lệ, chọn đúng tập bản ghi và chia nhỏ các thay đổi dữ liệu để kiểm soát tốt hơn trong vận hành MySQL.
