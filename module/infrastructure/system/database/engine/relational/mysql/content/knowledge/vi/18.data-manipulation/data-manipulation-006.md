# UPDATE một bảng và cập nhật nhiều bảng

`UPDATE` thay đổi giá trị của các cột trong những hàng đã tồn tại. Trong MySQL, bạn có thể cập nhật một bảng theo điều kiện của chính bảng đó, dùng dữ liệu từ bảng liên quan để cập nhật một bảng đích, hoặc cập nhật nhiều bảng trong cùng một câu lệnh. Chọn đúng dạng `UPDATE` giúp câu lệnh dễ kiểm soát, tránh cập nhật nhầm hàng và hiểu rõ giới hạn của cú pháp.

## Mục tiêu

Sau bài học, bạn có thể:

- Viết `UPDATE` cho một bảng với biểu thức, điều kiện và giá trị mặc định.
- Dùng `ORDER BY` và `LIMIT` để kiểm soát thứ tự hoặc chia nhỏ lần cập nhật một bảng.
- Dùng `UPDATE ... JOIN` để lấy dữ liệu từ bảng liên quan và cập nhật một hoặc nhiều bảng.
- Nhận biết các giới hạn của cú pháp cập nhật nhiều bảng, đặc biệt với `ORDER BY`, `LIMIT`, quan hệ khóa ngoại và phép nối có nhiều kết quả trùng khóa.
- Kiểm tra phạm vi ảnh hưởng và xác nhận kết quả trước khi hoàn tất thay đổi.

Các ví dụ dùng cú pháp MySQL hiện đại và giả định bảng đã tồn tại với những cột được nêu trong ví dụ.

## 1. Cập nhật một bảng

### Cú pháp

```sql
UPDATE [LOW_PRIORITY] [IGNORE] ten_bang
SET cot_1 = bieu_thuc_1,
    cot_2 = bieu_thuc_2,
    ...
[WHERE dieu_kien]
[ORDER BY bieu_thuc [ASC | DESC], ...]
[LIMIT so_hang];
```

`SET` xác định các cột cần thay đổi và giá trị mới. Mỗi vế gán có thể dùng hằng số, phép tính, hàm, biểu thức điều kiện hoặc từ khóa `DEFAULT`. `WHERE` chọn các hàng cần cập nhật. Nếu bỏ `WHERE`, tất cả hàng trong bảng đều thuộc phạm vi cập nhật.

Ví dụ tăng lương 8% cho nhân viên đang làm việc tại phòng ban số 12:

```sql
UPDATE employees
SET salary = ROUND(salary * 1.08, 2),
    updated_at = CURRENT_TIMESTAMP
WHERE department_id = 12
  AND status = 'ACTIVE';
```

Biểu thức ở `SET` được tính dựa trên giá trị cột của hàng đang được cập nhật. Vì vậy, `salary = salary * 1.08` không cần truy vấn giá trị lương trước rồi ghép vào câu lệnh.

### Cập nhật bằng điều kiện chính xác

Khi cập nhật một bản ghi theo khóa chính, điều kiện thường rất rõ ràng:

```sql
UPDATE customers
SET email = 'lan.nguyen@example.com',
    updated_at = CURRENT_TIMESTAMP
WHERE customer_id = 105;
```

Điều kiện có thể kết hợp nhiều cột, khoảng giá trị và trạng thái:

```sql
UPDATE subscriptions
SET status = 'EXPIRED'
WHERE status = 'ACTIVE'
  AND expires_at < CURRENT_DATE;
```

Với cột có thể chứa `NULL`, hãy dùng `IS NULL` hoặc `IS NOT NULL`; phép so sánh `= NULL` không cho kết quả đúng như mong muốn:

```sql
UPDATE customers
SET phone_verified = 0
WHERE phone_number IS NULL;
```

### Gán giá trị mặc định và cập nhật có điều kiện

`DEFAULT` yêu cầu MySQL gán giá trị mặc định được khai báo cho cột:

```sql
UPDATE products
SET status = DEFAULT
WHERE product_id = 230;
```

Có thể dùng `CASE` để chọn giá trị mới theo từng hàng:

```sql
UPDATE inventory
SET stock_status = CASE
        WHEN quantity = 0 THEN 'OUT_OF_STOCK'
        WHEN quantity <= reorder_level THEN 'LOW_STOCK'
        ELSE 'AVAILABLE'
    END,
    checked_at = CURRENT_TIMESTAMP
WHERE warehouse_id = 7;
```

Các cột trong cùng một câu lệnh có thể được cập nhật đồng thời. Tuy nhiên, với cú pháp cập nhật một bảng, MySQL thường đánh giá các phép gán trong `SET` từ trái sang phải. Nếu phép gán sau cần giá trị cũ của cột, hãy gán cột phụ thuộc trước:

```sql
UPDATE counters
SET previous_value = current_value,
    current_value = current_value + 1
WHERE counter_id = 1;
```

Ở ví dụ này, `previous_value` nhận giá trị `current_value` trước khi tăng. Nếu đảo thứ tự hai phép gán, phép gán sau có thể đọc giá trị đã được cập nhật. Không nên dựa vào quy tắc thứ tự phép gán này khi chuyển sang cú pháp cập nhật nhiều bảng; thứ tự đánh giá phép gán trong trường hợp đó không được bảo đảm.

### `ORDER BY` và `LIMIT`

Với cú pháp cập nhật một bảng, `ORDER BY` xác định thứ tự xử lý hàng và `LIMIT` giới hạn số hàng thỏa điều kiện được xét đến:

```sql
UPDATE task_queue
SET state = 'PROCESSING',
    claimed_at = CURRENT_TIMESTAMP
WHERE state = 'READY'
ORDER BY priority DESC, task_id ASC
LIMIT 20;
```

Nên thêm cột phân định duy nhất, chẳng hạn khóa chính, vào cuối `ORDER BY` để thứ tự ổn định khi nhiều hàng có cùng mức ưu tiên. `LIMIT` là giới hạn số hàng khớp với điều kiện `WHERE`; số hàng thực sự thay đổi có thể thấp hơn nếu một số hàng đã mang giá trị được gán.

Một cách dùng phổ biến là chia một tác vụ cập nhật lớn thành nhiều đợt:

```sql
UPDATE event_log
SET archived = 1
WHERE archived = 0
  AND created_at < '2025-01-01'
ORDER BY event_id
LIMIT 500;
```

Ứng dụng hoặc tác vụ vận hành có thể thực hiện lại câu lệnh theo từng đợt, kiểm tra số hàng thay đổi và dừng khi không còn hàng phù hợp. Điều kiện phải giúp các hàng đã xử lý rời khỏi tập cần cập nhật; nếu không, các lần chạy sau có thể tiếp tục gặp cùng một tập hàng.

`ORDER BY` và `LIMIT` không áp dụng cho cú pháp cập nhật nhiều bảng được trình bày ở phần sau.

### `LOW_PRIORITY` và `IGNORE`

- `LOW_PRIORITY` trì hoãn câu lệnh cho đến khi không còn phiên khác đang đọc bảng trên các storage engine dùng khóa ở cấp bảng. Tùy chọn này không tạo lợi ích tương tự với InnoDB, vốn sử dụng khóa ở cấp hàng cho phần lớn thao tác cập nhật.
- `IGNORE` yêu cầu MySQL tiếp tục trong một số tình huống lỗi dữ liệu hoặc xung đột khóa, có thể bỏ qua hàng gây xung đột và phát cảnh báo. Kết quả có thể là chỉ một phần hàng được cập nhật. Sau khi dùng tùy chọn này, cần kiểm tra số hàng và `SHOW WARNINGS`; không dùng nó chỉ để che giấu lỗi dữ liệu.

## 2. Dùng bảng liên quan để cập nhật một bảng

`UPDATE` có thể kết hợp các bảng bằng `JOIN`. Bảng được dùng để tra cứu có thể cung cấp giá trị hoặc điều kiện, trong khi chỉ một bảng đích được cập nhật.

Ví dụ đồng bộ mức chiết khấu mặc định từ khách hàng sang các đơn hàng đang chờ xử lý:

```sql
UPDATE orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
SET o.discount_rate = c.default_discount,
    o.updated_at = CURRENT_TIMESTAMP
WHERE o.status = 'PENDING'
  AND c.active = 1;
```

Trong câu lệnh này, `customers` chỉ tham gia phép nối và cung cấp `default_discount`; các cột được gán đều thuộc bảng `orders`. Câu lệnh dùng cú pháp `UPDATE` nhiều bảng vì phần `table_references` có phép nối. Do đó, không thể thêm `ORDER BY` hoặc `LIMIT` theo cú pháp cập nhật một bảng vào ví dụ này.

Điều kiện nối cần thể hiện đúng quan hệ giữa hai bảng. Nếu mỗi đơn hàng chỉ thuộc một khách hàng, `customers.customer_id` nên là khóa chính hoặc có ràng buộc `UNIQUE`. Nếu phép nối tạo nhiều hàng nguồn cho cùng một đơn hàng, không nên dựa vào một hàng nguồn bất kỳ để quyết định giá trị cập nhật. Hãy bảo đảm khóa nối duy nhất hoặc chuẩn hóa dữ liệu nguồn thành một hàng cho mỗi khóa đích trước khi cập nhật.

## 3. Cập nhật nhiều bảng trong cùng câu lệnh

### Cú pháp

```sql
UPDATE [LOW_PRIORITY] [IGNORE] table_references
SET bang_1.cot_a = bieu_thuc_a,
    bang_2.cot_b = bieu_thuc_b,
    ...
[WHERE dieu_kien];
```

Trong `table_references`, liệt kê các bảng và quan hệ nối. Trong `SET`, chỉ rõ cột thuộc từng bảng cần cập nhật. Một câu lệnh có thể cập nhật cột của một hoặc nhiều bảng trong danh sách; bảng chỉ dùng để tra cứu không tự động bị thay đổi.

Ví dụ cập nhật giá sản phẩm và cờ cần nhập thêm hàng cho kho số 7:

```sql
UPDATE products AS p
JOIN inventory AS i
  ON i.product_id = p.product_id
 AND i.warehouse_id = 7
SET p.price = ROUND(p.price * 1.05, 2),
    i.restock_required = CASE
        WHEN i.quantity < i.reorder_level THEN 1
        ELSE 0
    END
WHERE p.active = 1;
```

`products` và `inventory` đều có cột được cập nhật. Điều kiện `warehouse_id = 7` được đặt trong phép nối để chỉ lấy bản ghi tồn kho của kho cần xử lý. Thiết kế dữ liệu nên bảo đảm mỗi cặp `(product_id, warehouse_id)` xác định tối đa một hàng tồn kho, thường bằng ràng buộc `UNIQUE`. Khi quan hệ nối có tính duy nhất, mỗi sản phẩm chỉ ghép với một hàng tồn kho của kho đó và kết quả dễ dự đoán.

### Những giới hạn cần nhớ

**Không có `ORDER BY` và `LIMIT`.** Cú pháp cập nhật nhiều bảng không hỗ trợ hai mệnh đề này. Nếu cần chia nhỏ khối lượng công việc, hãy xác định tập khóa cần xử lý trước, sau đó cập nhật theo từng tập khóa bằng cách phù hợp với nghiệp vụ; không thêm `LIMIT` trực tiếp vào câu lệnh `UPDATE ... JOIN`.

**Một hàng đích chỉ được cập nhật một lần.** Nếu phép nối tạo nhiều kết quả cùng trỏ đến một hàng của bảng đích, MySQL vẫn cập nhật hàng đó một lần. Vì vậy, khi nhiều hàng nguồn khớp cùng một hàng đích, không nên giả định một hàng nguồn cụ thể sẽ được chọn để cung cấp giá trị. Hãy làm cho quan hệ nối duy nhất hoặc tổng hợp/chọn dữ liệu nguồn một cách tường minh trước khi cập nhật.

**Không có bảo đảm về thứ tự các phép gán.** Với cập nhật nhiều bảng, không dựa vào thứ tự các phép gán trong `SET` để truyền giá trị mới giữa các cột. Hãy viết mỗi biểu thức sao cho kết quả không phụ thuộc vào thứ tự đánh giá, hoặc tách thành các câu lệnh có thứ tự rõ ràng trong cùng một transaction.

**Chú ý khóa ngoại InnoDB.** Khi có khóa ngoại giữa các bảng, thứ tự xử lý nội bộ do bộ tối ưu chọn có thể khác thứ tự quan hệ cha-con. Một câu lệnh cập nhật nhiều bảng có thể thất bại và được rollback nếu thứ tự đó vi phạm ràng buộc. Khi thay đổi khóa được tham chiếu, hãy thiết kế `ON UPDATE` phù hợp nếu nghiệp vụ cần lan truyền thay đổi; trong trường hợp khác, cập nhật theo từng bảng và thứ tự được kiểm soát trong transaction thường dễ xử lý hơn.

**Xem xét trigger và tác động phụ.** Trigger `UPDATE` của mỗi bảng bị thay đổi có thể được kích hoạt. Nếu trigger ghi lịch sử, điều chỉnh số dư hoặc thay đổi dữ liệu liên quan, hãy tính các tác động đó khi dự đoán kết quả của một câu lệnh cập nhật nhiều bảng.

## 4. Kiểm tra trước và sau khi cập nhật

Một câu lệnh đúng cú pháp vẫn có thể chọn sai tập hàng. Trước khi chạy thay đổi quan trọng, hãy dùng cùng điều kiện để xem trước phạm vi:

```sql
SELECT employee_id, department_id, salary, status
FROM employees
WHERE department_id = 12
  AND status = 'ACTIVE'
ORDER BY employee_id;
```

Nếu câu lệnh `UPDATE` dùng `JOIN`, hãy chạy một câu `SELECT` với cùng phép nối và điều kiện để xem khóa của các hàng đích cùng giá trị nguồn dự kiến. Đặc biệt, kiểm tra xem mỗi khóa đích có khớp đúng số hàng nguồn mà thiết kế yêu cầu hay không.

Với bảng InnoDB, có thể đặt thay đổi trong transaction để kiểm tra trước khi xác nhận:

```sql
START TRANSACTION;

UPDATE employees
SET salary = ROUND(salary * 1.08, 2)
WHERE department_id = 12
  AND status = 'ACTIVE';

SELECT employee_id, salary
FROM employees
WHERE department_id = 12
  AND status = 'ACTIVE'
ORDER BY employee_id;

-- Nếu kết quả đúng:
COMMIT;

-- Nếu kết quả không đúng, dùng ROLLBACK thay cho COMMIT.
```

Trong phiên làm việc thực tế, chỉ chạy một trong hai lệnh kết thúc transaction: `COMMIT` để lưu thay đổi hoặc `ROLLBACK` để hủy thay đổi chưa commit. Transaction chỉ có thể rollback những thay đổi trên storage engine có hỗ trợ transaction, chẳng hạn InnoDB.

Sau câu lệnh, có thể kiểm tra số hàng mà máy khách báo đã khớp, đã thay đổi và số cảnh báo. `ROW_COUNT()` trả về số hàng bị ảnh hưởng theo quy tắc của kết nối hiện tại; tùy chọn client `CLIENT_FOUND_ROWS` có thể làm thay đổi cách số hàng được báo cáo. Nếu dùng `IGNORE`, chạy `SHOW WARNINGS` ngay sau câu lệnh để xem các vấn đề đã được hạ xuống thành cảnh báo.

## 5. Hiệu năng và lỗi thường gặp

Điều kiện `WHERE` và điều kiện nối quyết định phạm vi quét cũng như các hàng InnoDB cần khóa. Hãy chọn khóa nối đúng, dùng chỉ mục phù hợp cho các cột lọc thường xuyên và tránh cập nhật phạm vi rộng ngoài dự kiến. Với bảng lớn, cập nhật theo lô có thể giảm thời gian giữ khóa và giúp theo dõi tiến độ; kích thước lô cần phù hợp với tải hệ thống.

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Tất cả hàng bị thay đổi | Bỏ `WHERE` hoặc điều kiện quá rộng | Chạy `SELECT` với đúng điều kiện trước khi cập nhật |
| Không có hàng thay đổi | Điều kiện không khớp, giá trị đã giống giá trị mới, hoặc phép nối không tìm thấy hàng | Kiểm tra điều kiện và phép nối bằng `SELECT` |
| Cập nhật sai giá trị từ bảng liên quan | Một khóa đích khớp nhiều hàng nguồn | Bảo đảm tính duy nhất hoặc tổng hợp dữ liệu nguồn trước |
| Lỗi khóa ngoại | Thứ tự cập nhật không phù hợp với quan hệ cha-con | Xem lại `ON UPDATE`, thứ tự cập nhật và transaction |
| Câu lệnh nhiều bảng báo lỗi cú pháp khi có `LIMIT` | `LIMIT` không được hỗ trợ trong cú pháp cập nhật nhiều bảng | Chọn tập khóa theo lô rồi cập nhật theo cách phù hợp |
| Có cảnh báo nhưng câu lệnh vẫn chạy | Dùng `IGNORE` hoặc chuyển đổi dữ liệu có cảnh báo | Đọc `SHOW WARNINGS` và xác minh từng trường hợp |

Không nên coi `UPDATE` thành công là bằng chứng duy nhất cho thấy nghiệp vụ đã đúng. Hãy xác nhận cả số hàng, giá trị sau cập nhật và các tác động liên quan như trigger hoặc ràng buộc khóa ngoại.

## 6. Bài thực hành

Giả sử có các bảng `employees(employee_id, department_id, salary, status, updated_at)`, `departments(department_id, bonus_rate)` và `payroll_summary(department_id, total_salary, updated_at)`.

1. Tăng lương 5% cho nhân viên đang làm việc thuộc phòng ban số 4. Cập nhật thêm `updated_at`.
2. Dùng `JOIN` để tăng `employees.salary` theo `departments.bonus_rate` qua `department_id`. Chỉ cập nhật nhân viên đang làm việc.
3. Dùng một câu lệnh cập nhật nhiều bảng để thay đổi `departments.bonus_rate` và `payroll_summary.updated_at`, nối hai bảng bằng `department_id`. Giả sử `payroll_summary.department_id` là duy nhất; chỉ chọn phòng ban có ít nhất một nhân viên đang làm việc.
4. Giải thích vì sao không thể thêm `ORDER BY` và `LIMIT` vào câu lệnh ở câu 3. Đề xuất cách kiểm tra và chia nhỏ công việc nếu số hàng quá lớn.
5. Viết các truy vấn `SELECT` để xem trước hàng sẽ bị thay đổi và kiểm tra kết quả sau khi cập nhật.

## Ghi nhớ

- `UPDATE` một bảng hỗ trợ `WHERE`, `ORDER BY` và `LIMIT`; bỏ `WHERE` nghĩa là cập nhật mọi hàng.
- `UPDATE ... JOIN` có thể chỉ cập nhật bảng đích hoặc cập nhật nhiều bảng, tùy các cột xuất hiện trong `SET`.
- Cú pháp cập nhật nhiều bảng không hỗ trợ `ORDER BY` và `LIMIT`; mỗi hàng đích được cập nhật một lần dù phép nối có nhiều kết quả trùng hàng.
- Giữ phép nối có tính duy nhất và không phụ thuộc vào thứ tự đánh giá phép gán trong cập nhật nhiều bảng.
- Xem trước phạm vi bằng `SELECT`, kiểm tra kết quả và dùng transaction InnoDB khi cần khả năng xác nhận hoặc hoàn tác.
