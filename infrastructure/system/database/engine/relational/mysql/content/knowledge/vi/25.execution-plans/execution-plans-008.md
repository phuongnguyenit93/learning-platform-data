# Using index, Using where và Using index condition

## Mục tiêu

Sau bài này, bạn có thể:

- Đọc ba thông tin phổ biến trong cột `Extra` của `EXPLAIN`: `Using index`, `Using where` và `Using index condition`.
- Phân biệt covering index với việc chỉ dùng index để tìm một phần dữ liệu.
- Hiểu điều kiện nào được xử lý trong server, điều kiện nào được đẩy xuống storage engine.
- Giải thích Index Condition Pushdown (ICP) và lợi ích giảm số lần đọc hàng từ clustered index.
- Nhận biết vì sao `Using where` không đồng nghĩa với truy vấn chậm hoặc không dùng index.
- Phân tích khi các thông tin này xuất hiện riêng lẻ hoặc kết hợp với nhau.
- Kiểm tra access path bằng `EXPLAIN`, `EXPLAIN FORMAT=JSON`, `EXPLAIN ANALYZE` và `optimizer_switch`.
- Thiết kế index phù hợp với điều kiện lọc và các cột được truy vấn.

Các ví dụ hướng tới MySQL 8.0/8.4 với InnoDB. Nội dung trong `Extra` phụ thuộc execution plan, dữ liệu, index và phiên bản; kết quả minh họa không phải output cố định cho mọi môi trường.

## 1. Cột Extra trong EXPLAIN cho biết điều gì?

`EXPLAIN` giúp xem MySQL dự định thực thi một câu truy vấn như thế nào. Ở định dạng bảng truyền thống, cột `Extra` cung cấp thông tin bổ sung về cách truy cập và xử lý dữ liệu.

Ví dụ:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name
FROM employees
WHERE dept_id = 10;
```

Một số giá trị `Extra` thường gặp:

| Extra | Ý nghĩa chính |
|---|---|
| `Using index` | Truy vấn có thể lấy các cột cần thiết trực tiếp từ index; đây là covering/index-only access |
| `Using where` | MySQL dùng điều kiện `WHERE` để lọc các hàng được access path trả về; không có nghĩa là truy vấn không dùng index |
| `Using index condition` | Điều kiện có thể kiểm tra từ index được đẩy xuống storage engine bằng Index Condition Pushdown trước khi đọc đầy đủ hàng |

Ba thông tin này mô tả các khía cạnh khác nhau của quá trình thực thi. Chúng không phải ba cấp độ tốt/xấu và không loại trừ nhau trong mọi kế hoạch.

### 1.1. Extra không phải điểm đánh giá hiệu năng

Không thể kết luận truy vấn tốt chỉ vì có `Using index`, hoặc xấu chỉ vì có `Using where`. Cần xem thêm:

- `type`: access method như `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`.
- `possible_keys` và `key`: index có thể dùng và index thực tế được chọn.
- `key_len`: độ dài phần index được dùng để truy cập.
- `rows`: số hàng ước lượng cần đọc.
- `filtered`: tỷ lệ phần trăm hàng còn lại sau điều kiện lọc theo ước lượng.
- `Extra`: cách MySQL xử lý điều kiện, index và dữ liệu bổ sung.
- Actual rows, loops và thời gian từ `EXPLAIN ANALYZE` khi cần đo thực tế.

Một truy vấn dùng index nhưng phải đọc hàng triệu entry vẫn có thể chậm. Một truy vấn có `Using where` trên vài trăm hàng có thể rất nhanh.

## 2. Chuẩn bị bảng ví dụ

Dùng một bảng nhân viên với index ghép trên phòng ban và họ:

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    dept_id INT NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    hire_date DATE NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_dept_lastname (dept_id, last_name)
) ENGINE = InnoDB;
```

Trong InnoDB, secondary index lưu các cột index và khóa chính của hàng tương ứng. Vì vậy, `idx_dept_lastname` có thể cung cấp `dept_id`, `last_name` và `employee_id` mà không cần đọc hàng từ clustered index.

Nạp dữ liệu đủ lớn và có phân bố khác nhau giữa phòng ban, họ, trạng thái để optimizer có cơ sở chọn access path. Nếu bảng chỉ có vài hàng, optimizer có thể chọn table scan dù có index; điều đó không làm ví dụ sai mà phản ánh chi phí thực tế trên bảng nhỏ.

Kiểm tra cấu trúc index:

```sql
SHOW INDEX FROM employees;
```

## 3. Using index: covering index

`Using index` trong `Extra` cho biết MySQL có thể đáp ứng các cột cần thiết của truy vấn từ index mà không cần đọc đầy đủ hàng trong clustered index/table row. Cách truy cập này thường được gọi là covering index hoặc index-only access.

### 3.1. Ví dụ truy vấn được index bao phủ

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name
FROM employees
WHERE dept_id = 10;
```

Index `idx_dept_lastname (dept_id, last_name)` chứa:

- `dept_id` và `last_name` do khai báo trong index.
- `employee_id` do InnoDB lưu primary key trong mỗi secondary index entry.

Do đó, truy vấn có thể lấy các cột được SELECT trực tiếp từ secondary index. Trong `Extra`, MySQL thường hiển thị `Using index` nếu optimizer chọn access path này.

### 3.2. Covering index không có nghĩa là không đọc index

MySQL vẫn phải đọc các index page và duyệt các entry phù hợp. `Using index` chỉ cho biết không cần truy cập thêm clustered record để lấy cột còn thiếu.

Nếu điều kiện lọc trả về rất nhiều entry, truy vấn vẫn có thể tốn I/O và CPU. Nếu optimizer chọn `type = index`, có thể đang quét toàn bộ index; đây vẫn là index scan, không đồng nghĩa với lookup chọn lọc.

### 3.3. Covering index phụ thuộc cột truy vấn

Thêm cột `salary` vào SELECT:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10;
```

`salary` không nằm trong `idx_dept_lastname` và cũng không phải primary key. InnoDB phải đọc clustered record để lấy lương. Vì thế, index hiện tại không còn bao phủ toàn bộ truy vấn và `Using index` có thể biến mất.

Có thể tạo covering index lớn hơn:

```sql
CREATE INDEX idx_dept_lastname_salary
ON employees (dept_id, last_name, salary);
```

Nhưng không nên thêm cột vào index chỉ để ép `Using index`. Index rộng làm tăng dung lượng, chi phí ghi, buffer pool pressure và chi phí bảo trì. Chỉ tạo khi workload đọc đủ quan trọng và lợi ích đã được đo.

### 3.4. Using index có thể xuất hiện cùng Using where

Ví dụ:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name
FROM employees
WHERE dept_id = 10
  AND last_name LIKE 'Ng%';
```

Các cột cần đọc đều có trong index. MySQL có thể dùng index để tìm phạm vi và lấy kết quả mà không đọc clustered record (`Using index`). Đồng thời, điều kiện `WHERE` vẫn được đánh giá trên các entry được truy cập, nên tùy access plan `Extra` có thể hiển thị thêm `Using where`.

`Using index` trả lời câu hỏi “có cần đọc đầy đủ hàng để lấy cột không?”. `Using where` trả lời câu hỏi “có điều kiện lọc được áp dụng lên hàng/entry không?”. Hai ý nghĩa này không mâu thuẫn.

## 4. Using where: server còn phải lọc kết quả

`Using where` cho biết MySQL áp dụng điều kiện `WHERE` để loại các hàng không phù hợp khỏi kết quả của access path. Điều kiện có thể được dùng một phần để tìm bằng index, phần còn lại được đánh giá sau đó.

`Using where` không tự cho biết điều kiện được kiểm tra ở server hay storage engine bằng ICP. Cần đọc cùng các thông tin khác trong `Extra` và execution plan.

### 4.1. Lọc sau khi dùng index để tìm một phần dữ liệu

Với index `(dept_id, last_name)`, chạy:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name, status, salary
FROM employees FORCE INDEX (idx_dept_lastname)
WHERE dept_id = 10
  AND status = 'ACTIVE';
```

Index có thể giúp tìm các nhân viên thuộc phòng ban 10. Nhưng `status` không nằm trong index. MySQL phải lấy hàng tương ứng rồi kiểm tra `status = 'ACTIVE'` ở server. `Extra` thường có `Using where`.

`FORCE INDEX` ở đây chỉ giúp minh họa một access path dễ quan sát. Không nên thêm `FORCE INDEX` vào production chỉ vì muốn thấy một giá trị Extra cụ thể; hãy để optimizer chọn và chỉ can thiệp khi đã đo, chứng minh được lợi ích.

### 4.2. Lọc sau table scan

```sql
EXPLAIN
SELECT employee_id, dept_id, status, salary
FROM employees
WHERE status = 'ACTIVE';
```

Nếu không có index phù hợp trên `status` và optimizer chọn quét bảng (`type = ALL`), server vẫn phải kiểm tra điều kiện `status = 'ACTIVE'` trên các hàng đã đọc. `Extra` có thể hiển thị `Using where`.

Đây không nhất thiết là vấn đề nếu bảng nhỏ hoặc phần lớn hàng đều có trạng thái ACTIVE. Nếu bảng lớn và điều kiện chọn lọc cao, hãy đánh giá index trên `status` hoặc index ghép theo workload thực tế.

### 4.3. Using where không có nghĩa không dùng index

Ví dụ truy vấn có index cho một phần điều kiện và lọc phần còn lại:

```sql
SELECT employee_id, dept_id, status
FROM employees
WHERE dept_id = 10
  AND status = 'ACTIVE';
```

Optimizer có thể dùng `idx_dept_lastname` để giới hạn theo `dept_id`, sau đó áp dụng điều kiện trạng thái cho từng hàng được đọc. Kế hoạch vẫn dùng index, nhưng còn residual predicate.

Khi thấy `Using where`, hãy xem `key`, `rows`, `filtered` và cột tham gia index trước khi kết luận.

## 5. Using index condition: Index Condition Pushdown (ICP)

Index Condition Pushdown là tối ưu hóa cho phép MySQL đẩy một phần điều kiện `WHERE` xuống storage engine. Storage engine có thể kiểm tra điều kiện dựa trên các cột có trong index trước khi đọc đầy đủ hàng từ clustered index.

Nếu điều kiện không đạt, InnoDB bỏ qua việc đọc clustered record cho entry đó. Nếu điều kiện đạt, engine mới tiếp tục lấy đầy đủ hàng khi truy vấn cần các cột không có trong secondary index.

Trong `EXPLAIN`, dấu hiệu thường gặp là:

```text
Using index condition
```

### 5.1. Ví dụ ICP với index ghép

Truy vấn cần lương, nhưng index chỉ có phòng ban và họ:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

Phân tích:

1. `dept_id = 10` dùng phần đầu của index `idx_dept_lastname` để tìm các entry thuộc phòng ban 10.
2. `last_name LIKE '%son'` có wildcard ở đầu nên không tạo được một range B-tree thông thường trên `last_name`.
3. Tuy vậy, `last_name` có trong index. InnoDB có thể kiểm tra điều kiện này ngay trên index entry bằng ICP.
4. Chỉ các entry có họ phù hợp mới cần đọc clustered record để lấy `salary`.

Nếu optimizer chọn index và ICP, `Extra` có thể hiển thị `Using index condition`.

### 5.2. ICP giảm đọc hàng, không nhất thiết giảm số index entry phải quét

Trong ví dụ trên, engine vẫn phải duyệt các index entry thuộc phạm vi `dept_id = 10` để kiểm tra phần đuôi của `last_name`. ICP không biến `LIKE '%son'` thành một phép tìm kiếm B-tree theo prefix.

Lợi ích là những entry không khớp `LIKE` có thể bị loại trước khi đọc clustered record. Nếu phần lớn entry không khớp và việc lấy hàng từ clustered index tốn kém, ICP có thể giảm I/O đáng kể.

Nếu gần như mọi entry đều khớp, lợi ích có thể nhỏ. Nếu phạm vi `dept_id = 10` đã rất hẹp, chi phí kiểm tra ICP cũng có thể không đáng kể.

### 5.3. ICP khác covering index

Hai khái niệm này thường bị nhầm:

| Đặc điểm | Using index | Using index condition |
|---|---|---|
| Ý nghĩa | Index chứa đủ cột cần cho truy vấn | Storage engine kiểm tra điều kiện từ cột index trước khi đọc hàng đầy đủ |
| Có cần đọc clustered record không? | Không cần nếu access path thực sự covering | Có thể cần đọc cho entry vượt qua điều kiện nếu SELECT cần cột ngoài index |
| Mục tiêu | Tránh đọc hàng đầy đủ | Giảm số hàng phải đọc đầy đủ |
| Thông tin trong Extra | `Using index` | `Using index condition` |

Trong ví dụ ICP, truy vấn cần `salary` nhưng index không chứa `salary`, nên các entry vượt qua ICP vẫn cần đọc hàng đầy đủ. `Using index condition` không có nghĩa truy vấn đã được index bao phủ.

### 5.4. ICP không áp dụng cho mọi access path

ICP chỉ có ích khi MySQL có index access và có điều kiện có thể kiểm tra từ các cột index trước khi lấy hàng đầy đủ. Một số điều kiện phổ biến:

- Access method phù hợp như `range`, `ref`, `eq_ref` hoặc `ref_or_null`.
- Điều kiện được đẩy xuống chỉ tham chiếu các cột có trong index.
- Truy vấn cần lấy thêm cột từ hàng đầy đủ để trả kết quả hoặc xử lý tiếp.
- Storage engine và dạng index hỗ trợ ICP.

Với InnoDB, ICP được áp dụng cho secondary index; nó không giúp giảm clustered-record lookup khi truy cập trực tiếp clustered index theo cách tương tự. Nếu truy vấn đã được covering index đáp ứng, không cần ICP vì không cần đọc hàng đầy đủ.

Các điều kiện chứa subquery hoặc stored function không thể được đẩy xuống theo cách này. Optimizer cũng có thể không chọn ICP nếu đánh giá chi phí không có lợi.

## 6. So sánh ba tình huống trên cùng một index

Giả sử có index:

```sql
KEY idx_dept_lastname (dept_id, last_name)
```

Ba truy vấn sau minh họa ba mục tiêu khác nhau:

### Trường hợp A: Covering index

```sql
SELECT employee_id, dept_id, last_name
FROM employees
WHERE dept_id = 10;
```

- Tất cả cột cần thiết có trong secondary index (primary key được lưu trong entry).
- Có thể không cần đọc clustered record.
- `Extra` có thể hiển thị `Using index`.

### Trường hợp B: Residual filter ở server

```sql
SELECT employee_id, dept_id, last_name, status, salary
FROM employees FORCE INDEX (idx_dept_lastname)
WHERE dept_id = 10
  AND status = 'ACTIVE';
```

- `dept_id` dùng để tìm trong index.
- `status` không có trong index nên không thể kiểm tra bằng ICP từ index này.
- Hàng đầy đủ được đọc để lấy `status` và `salary`; server áp dụng điều kiện còn lại.
- `Extra` thường có `Using where`.

### Trường hợp C: ICP

```sql
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

- `dept_id` dùng để tìm phạm vi index.
- `last_name` có trong index nên điều kiện LIKE có thể được kiểm tra trong storage engine.
- Chỉ entry phù hợp mới cần lấy `salary` từ clustered record.
- `Extra` có thể hiển thị `Using index condition`.

### 6.1. Extra có thể kết hợp

Một execution plan có thể cần nhiều bước xử lý, vì vậy Extra có thể chứa nhiều thông tin, ví dụ `Using index condition; Using where` hoặc `Using where; Using index` tùy truy vấn và phiên bản.

Đừng yêu cầu một truy vấn phải hiển thị đúng một chuỗi Extra duy nhất. Hãy hiểu từng thành phần và đối chiếu với cột `key`, `type`, `rows` cùng execution tree.

## 7. Bật/tắt Index Condition Pushdown để kiểm tra

ICP được điều khiển bằng cờ `index_condition_pushdown` trong `optimizer_switch`. Trong các phiên bản MySQL 8.0/8.4, cờ này thường được bật mặc định.

Kiểm tra:

```sql
SELECT @@SESSION.optimizer_switch;
```

Tắt ICP trong session hiện tại để so sánh kế hoạch:

```sql
SET SESSION optimizer_switch = 'index_condition_pushdown=off';

EXPLAIN
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

Bật lại:

```sql
SET SESSION optimizer_switch = 'index_condition_pushdown=on';
```

Khi ICP tắt, storage engine không kiểm tra điều kiện phụ trên index theo cơ chế ICP; MySQL có thể phải đọc thêm clustered record rồi lọc ở server. Trong `Extra`, `Using index condition` có thể biến mất và thay bằng cách mô tả khác, chẳng hạn `Using where`.

Kết quả cụ thể phụ thuộc optimizer, dữ liệu và index. Nếu bảng nhỏ hoặc optimizer chọn table scan, bật/tắt ICP có thể không tạo khác biệt quan sát được.

Không tắt ICP toàn cục để xử lý một truy vấn riêng. Dùng session-level setting trong môi trường thử nghiệm hoặc benchmark để so sánh, sau đó khôi phục cấu hình ban đầu.

## 8. Đọc EXPLAIN ở các định dạng khác nhau

### 8.1. Traditional EXPLAIN

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

Traditional format phù hợp để đọc nhanh `type`, `key`, `rows`, `filtered` và `Extra`.

### 8.2. EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

JSON cung cấp cấu trúc chi tiết hơn. Tùy phiên bản và plan, hãy tìm các thông tin như:

- `used_key_parts`: phần cột index được dùng cho access.
- `index_condition`: điều kiện được đẩy xuống index/storage engine.
- `attached_condition`: điều kiện gắn với bước truy cập hoặc được xử lý ở tầng server.
- `using_index`: thông tin về covering index khi có.

Không phải mọi node đều có đủ các thuộc tính trên. Đọc chúng trong ngữ cảnh node/table tương ứng, không chỉ tìm chuỗi tên thuộc tính trên toàn JSON.

### 8.3. EXPLAIN FORMAT=TREE

```sql
EXPLAIN FORMAT=TREE
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

TREE trình bày các iterator theo cấu trúc thực thi. Nó hữu ích để thấy thứ tự access, filter và join, nhưng không phải lúc nào cũng trình bày đúng chuỗi `Extra` như traditional format.

### 8.4. EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

`EXPLAIN ANALYZE` thực sự chạy truy vấn rồi hiển thị số hàng và thời gian thực tế của các iterator. Dùng nó để kiểm tra liệu số hàng ước lượng có gần với thực tế hay không và filter loại được bao nhiêu hàng.

Lệnh này tạo tải thật. Chỉ chạy trên dữ liệu và môi trường phù hợp; tránh dùng tùy tiện với truy vấn nặng hoặc truy vấn có tác động ngoài ý muốn.

## 9. Chọn index để hỗ trợ ICP và covering access

Index nên được thiết kế từ workload, gồm điều kiện lọc, JOIN, thứ tự sắp xếp và các cột cần trả về.

### 9.1. Đặt cột lọc chính ở đầu index

Với truy vấn:

```sql
WHERE dept_id = 10
  AND last_name LIKE '%son'
```

Index `(dept_id, last_name)` cho phép giới hạn theo `dept_id` trước, sau đó kiểm tra `last_name` bằng ICP nếu optimizer thấy phù hợp.

Nếu đảo thứ tự thành `(last_name, dept_id)`, điều kiện LIKE có wildcard đầu chuỗi không tạo range thông thường trên `last_name`; optimizer có thể không tận dụng tốt `dept_id` ở cột thứ hai do quy tắc leftmost prefix.

### 9.2. Thêm cột để covering phải cân nhắc chi phí

Nếu truy vấn thường xuyên đọc `salary`, có thể cân nhắc index `(dept_id, last_name, salary)` để bao phủ. Tuy nhiên:

- Index lớn hơn và cần thêm page.
- INSERT/UPDATE `salary` phải cập nhật index.
- Buffer pool chứa ít entry hữu ích hơn trên mỗi page.
- Chi phí backup, rebuild và bảo trì index tăng.

Chỉ tạo covering index nếu giảm clustered lookup đem lại lợi ích lớn hơn chi phí ghi và lưu trữ.

### 9.3. Đừng thêm cột không cần thiết chỉ để loại Using where

`Using where` không phải một lỗi cần xóa khỏi plan bằng mọi giá. Nếu filter còn lại rẻ và chỉ áp dụng trên ít hàng, việc thêm cột vào index có thể làm hệ thống chậm hơn do write amplification.

Mục tiêu là giảm tổng chi phí workload, không phải làm cho cột Extra trông “đẹp”.

## 10. Quy trình phân tích một truy vấn có Extra

Khi gặp `Using index`, `Using where` hoặc `Using index condition`, làm theo trình tự:

1. **Đọc SQL:** xác định cột được SELECT, JOIN, WHERE và ORDER BY.
2. **Đọc index:** kiểm tra thứ tự cột, unique hay non-unique, primary key và cột nào thực sự có trong index.
3. **Đọc access method:** xem `type`, `key`, `key_len`, `rows` và `filtered`.
4. **Giải nghĩa Extra:** xác định covering, residual filter hay ICP.
5. **Kiểm tra số hàng:** so sánh estimated rows với actual rows bằng `EXPLAIN ANALYZE` khi phù hợp.
6. **Xác định điểm tốn kém:** nhiều index entry phải quét, nhiều clustered lookup, filter loại ít hàng hay sort lớn?
7. **Đề xuất thay đổi:** điều chỉnh index, predicate hoặc cột SELECT nếu có lợi cho workload.
8. **Đo lại:** so sánh latency, rows examined, I/O và chi phí ghi sau khi thay đổi.

## 11. Những lỗi thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| `Using index` nghĩa là truy vấn không đọc dữ liệu | MySQL vẫn đọc index entry; chỉ tránh đọc clustered record để lấy cột còn thiếu | Kiểm tra số entry phải duyệt và access type |
| `Using where` nghĩa là không dùng index | Index có thể được dùng cho một phần predicate, phần còn lại lọc sau | Đọc `key`, `rows`, `filtered` và predicate |
| `Using index condition` nghĩa là covering index | ICP vẫn có thể phải đọc hàng đầy đủ sau khi entry vượt qua điều kiện | Kiểm tra các cột SELECT có nằm trong index không |
| ICP biến LIKE '%x' thành index range | ICP chỉ kiểm tra điều kiện trên entry; không biến wildcard đầu thành range B-tree | Xem range access và số index entry được quét |
| Cứ thêm cột vào index là tốt | Index rộng tăng dung lượng và chi phí ghi | Chỉ thêm khi workload và số đo chứng minh lợi ích |
| Extra chỉ có một giá trị | Nhiều thuộc tính xử lý có thể xuất hiện cùng nhau | Đọc từng thành phần trong ngữ cảnh plan |
| `EXPLAIN ANALYZE` chỉ ước lượng | Lệnh thực sự thực thi truy vấn | Cân nhắc tải trước khi chạy |
| Bảng nhỏ không chọn index là lỗi optimizer | Table scan có thể rẻ hơn với bảng nhỏ hoặc điều kiện ít chọn lọc | Kiểm tra dữ liệu và đo thực tế |

## 12. Checklist trước khi tối ưu production

- [ ] Đã hiểu `Using index` là covering access và kiểm tra đủ cột SELECT/JOIN/WHERE cần thiết.
- [ ] Đã hiểu `Using where` chỉ cho biết có filter, không tự kết luận truy vấn chậm.
- [ ] Đã xác định predicate nào được dùng để tìm range và predicate nào là residual filter.
- [ ] Đã kiểm tra `Using index condition` có thực sự áp dụng ICP trên secondary index hay không.
- [ ] Đã phân biệt ICP với covering index.
- [ ] Đã xem `type`, `key`, `key_len`, `rows`, `filtered` và Extra.
- [ ] Đã kiểm tra số index entry và clustered row lookup cần thực hiện.
- [ ] Đã đánh giá lợi ích ICP trên phân bố dữ liệu gần production.
- [ ] Đã cân nhắc chi phí index rộng, write amplification và buffer pool.
- [ ] Đã dùng `EXPLAIN ANALYZE` an toàn để đối chiếu actual rows khi cần.
- [ ] Đã đo latency và tài nguyên trước/sau thay đổi.
- [ ] Không thêm `FORCE INDEX` hoặc tắt ICP chỉ để làm thay đổi chuỗi Extra.

## 13. Kết luận

`Using index` cho biết truy vấn có thể được bao phủ bởi index nên không cần đọc đầy đủ hàng để lấy các cột cần thiết. `Using where` cho biết MySQL còn áp dụng điều kiện lọc lên các hàng/entry được truy cập; điều này vẫn có thể xảy ra khi index đã được sử dụng. `Using index condition` biểu thị Index Condition Pushdown: storage engine kiểm tra điều kiện dựa trên cột index trước khi đọc clustered record, nhờ đó giảm số lần đọc hàng đầy đủ khi nhiều entry bị loại.

Ba thông tin này mô tả các giai đoạn khác nhau và có thể xuất hiện cùng nhau. Hãy xem SQL, index, access method, estimated/actual rows và execution plan đầy đủ trước khi tối ưu. Thiết kế index nhằm giảm tổng chi phí đọc/ghi của workload, không nhằm loại bỏ một dòng `Extra` khỏi output.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: EXPLAIN Output Format](https://dev.mysql.com/doc/refman/8.4/en/explain-output.html)
- [MySQL 8.4 Reference Manual: Index Condition Pushdown Optimization](https://dev.mysql.com/doc/refman/8.4/en/index-condition-pushdown-optimization.html)
- [MySQL 8.4 Reference Manual: Optimizer Switch](https://dev.mysql.com/doc/refman/8.4/en/switchable-optimizations.html)
