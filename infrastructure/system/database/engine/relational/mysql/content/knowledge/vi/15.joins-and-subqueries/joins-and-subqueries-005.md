# USING, NATURAL JOIN và rủi ro khi schema thay đổi

Khi kết hợp hai bảng trong MySQL, bạn thường viết điều kiện nối bằng `ON`:

```sql
SELECT e.employee_id, e.employee_name, d.department_name
FROM employee AS e
JOIN department AS d
    ON d.department_id = e.department_id;
```

Nếu hai bảng có cột khóa cùng tên, MySQL còn cung cấp cú pháp `USING`. Cú pháp này rút gọn phép nối bằng đẳng thức trên các cột được liệt kê và gộp mỗi cặp cột chung thành một cột trong kết quả. `NATURAL JOIN` đi xa hơn: MySQL tự lấy **tất cả tên cột xuất hiện ở cả hai bảng** làm điều kiện nối.

`USING` hữu ích khi danh sách cột chung đã được xác định rõ. `NATURAL JOIN` có thể ngắn hơn, nhưng điều kiện nối phụ thuộc trực tiếp vào cấu trúc schema hiện tại. Khi một migration thêm cột trùng tên vào cả hai bảng, kết quả nối có thể thay đổi dù câu SQL không đổi. Hiểu rõ khác biệt này giúp tránh lỗi dữ liệu khó phát hiện trong truy vấn, view và báo cáo.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Viết `JOIN ... USING (column_list)` và hiểu điều kiện đẳng thức được tạo ra.
- Phân biệt `ON`, `USING` và `NATURAL JOIN`.
- Giải thích cách MySQL gộp cột chung trong kết quả của `USING` và `NATURAL JOIN`.
- Hiểu cách `LEFT JOIN` và `RIGHT JOIN` xử lý cột chung đã gộp.
- Nhận biết ảnh hưởng của `NULL`, kiểu dữ liệu, dấu số và collation đến điều kiện nối.
- Tái hiện rủi ro khi `NATURAL JOIN` tự động thay đổi điều kiện sau khi schema được mở rộng.
- Chọn cú pháp nối phù hợp và viết select list ổn định khi schema thay đổi.
- Kiểm tra kế hoạch thực thi và quản lý thay đổi schema có kiểm soát.

## 1. Chuẩn bị dữ liệu thực hành

Ví dụ đầu tiên dùng hai bảng nhân viên và phòng ban. Cả hai có cột `department_id`, nhưng chưa có cột chung nào khác:

```sql
CREATE TABLE join_department_demo (
    department_id INT NOT NULL,
    department_name VARCHAR(80) NOT NULL,
    PRIMARY KEY (department_id)
) ENGINE = InnoDB;

CREATE TABLE join_employee_demo (
    employee_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    department_id INT NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_join_employee_department (department_id),
    CONSTRAINT fk_join_employee_department
        FOREIGN KEY (department_id)
        REFERENCES join_department_demo (department_id)
) ENGINE = InnoDB;

INSERT INTO join_department_demo (department_id, department_name)
VALUES
    (10, 'Engineering'),
    (20, 'Finance'),
    (30, 'Operations');

INSERT INTO join_employee_demo
    (employee_id, employee_name, department_id)
VALUES
    (1001, 'An', 10),
    (1002, 'Binh', 10),
    (1003, 'Chi', 20),
    (1004, 'Dung', 30);
```

Kiểm tra dữ liệu:

```sql
SELECT * FROM join_department_demo ORDER BY department_id;
SELECT * FROM join_employee_demo ORDER BY employee_id;
```

Các bảng có một cột khóa ngoại cùng tên là `department_id`. Đây là trường hợp phù hợp để minh họa `USING`.

## 2. JOIN ... USING: chỉ rõ cột chung cần nối

Cú pháp cơ bản:

```sql
SELECT select_list
FROM table_a
JOIN table_b USING (common_column);
```

Danh sách trong `USING` phải chứa tên cột tồn tại ở cả hai phía của phép nối. Có thể liệt kê nhiều cột:

```sql
SELECT select_list
FROM table_a
JOIN table_b USING (key_part_1, key_part_2);
```

Với dữ liệu mẫu:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    department_name
FROM join_employee_demo
JOIN join_department_demo USING (department_id)
ORDER BY department_id, employee_id;
```

Điều kiện này tương đương về logic với:

```sql
SELECT
    e.department_id,
    e.employee_id,
    e.employee_name,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id
ORDER BY e.department_id, e.employee_id;
```

Trong ví dụ, `USING (department_id)` tạo điều kiện tương đương:

```sql
e.department_id = d.department_id
```

Điểm khác biệt quan trọng nằm ở cách trình bày cột kết quả: với `USING`, hai cột `department_id` được gộp thành một cột chung. Với `ON`, cả hai cột nguồn vẫn là hai cột riêng nếu bạn dùng `SELECT *`.

### 2.1. USING chỉ nhận tên cột, không nhận biểu thức

Danh sách `USING` chỉ chứa tên cột chung, không phải biểu thức tùy ý:

```sql
-- Hợp lệ
SELECT *
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);
```

Không viết tên đã định danh bằng alias trong danh sách:

```sql
-- Không hợp lệ: USING nhận tên cột, không nhận e.department_id
SELECT *
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (e.department_id);
```

Nếu hai bảng dùng tên cột khác nhau, hoặc cần nối bằng biểu thức, hãy dùng `ON`:

```sql
SELECT *
FROM employee_source AS e
JOIN department_source AS d
    ON e.dept_code = d.department_code;
```

### 2.2. USING với khóa ghép

Khi định danh gồm nhiều cột, liệt kê đầy đủ các thành phần:

```sql
SELECT
    tenant_id,
    department_id,
    employee_id,
    department_name
FROM tenant_employee
JOIN tenant_department
USING (tenant_id, department_id);
```

Điều kiện tương đương là:

```sql
tenant_employee.tenant_id = tenant_department.tenant_id
AND tenant_employee.department_id = tenant_department.department_id
```

Nếu chỉ nối bằng `department_id` mà bỏ `tenant_id`, dữ liệu giữa hai tenant có thể ghép nhầm. Cú pháp ngắn không thay thế việc xác định đầy đủ khóa nghiệp vụ.

## 3. Cột chung được gộp như thế nào?

Với `JOIN ... USING (department_id)`, MySQL trình bày một cột `department_id` chung thay vì hai cột riêng. Quy tắc này ảnh hưởng đến `SELECT *` và thứ tự các cột trả về.

Ví dụ:

```sql
SELECT *
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);
```

Các cột chung được đưa ra một lần. Với `USING`, các cột chung xuất hiện trước, sau đó là các cột chỉ có ở bảng bên trái, rồi đến các cột chỉ có ở bảng bên phải. Nếu schema thêm hoặc xóa cột, hình dạng và thứ tự kết quả của `SELECT *` có thể thay đổi.

Với `ON`, hai cột khóa nguồn vẫn độc lập trong kết quả:

```sql
SELECT *
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id;
```

Kết quả có cả `e.department_id` và `d.department_id`. Điều này có thể hữu ích khi cần đối chiếu hai giá trị nguồn, nhưng thường không cần thiết trong truy vấn nghiệp vụ thông thường.

**Khuyến nghị:** trong truy vấn dùng cho API, view hoặc báo cáo lâu dài, hãy liệt kê cột rõ ràng và đặt alias cho cột kết quả. Đừng để hợp đồng dữ liệu của ứng dụng phụ thuộc vào thứ tự cột ngầm định của `SELECT *`.

### 3.1. Cột gộp trong INNER, LEFT và RIGHT JOIN

Với các cột trong danh sách `USING`, MySQL gộp mỗi cặp thành một cột chung. Giá trị cột chung phụ thuộc loại join:

| Loại join | Giá trị cột chung trong kết quả |
|---|---|
| `INNER JOIN ... USING` | Giá trị của cột chung sau khi hai phía khớp nhau |
| `LEFT JOIN ... USING` | Giá trị từ bảng bên trái |
| `RIGHT JOIN ... USING` | Giá trị từ bảng bên phải |

Với inner join, hai giá trị phải bằng nhau để hàng được ghép. Với left join, nếu không có hàng bên phải, cột phía phải được mở rộng thành `NULL`, còn cột chung vẫn thể hiện giá trị từ hàng bên trái.

Ví dụ, liệt kê tất cả phòng ban, kể cả phòng chưa có nhân viên:

```sql
SELECT
    department_id,
    department_name,
    employee_id,
    employee_name
FROM join_department_demo
LEFT JOIN join_employee_demo USING (department_id)
ORDER BY department_id, employee_id;
```

Nếu một phòng ban chưa có nhân viên, `department_id` vẫn có giá trị của phòng ban; `employee_id` và `employee_name` là `NULL`. Vì vậy, khi đếm hàng phía phải trong truy vấn outer join, dùng khóa không null của bảng con, ví dụ `COUNT(employee_id)`, thay vì `COUNT(*)`.

### 3.2. Khi cần nhìn riêng hai giá trị khóa nguồn

Nếu mục tiêu là kiểm tra hoặc đối chiếu hai cột nguồn, dùng `ON` và chọn rõ từng phía:

```sql
SELECT
    e.department_id AS employee_department_id,
    d.department_id AS directory_department_id,
    e.employee_name,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id;
```

Cách viết này làm rõ nguồn của từng giá trị và thuận tiện cho truy vấn kiểm tra chất lượng dữ liệu. `USING` phù hợp khi bạn muốn biểu diễn một khóa chung đã được xác định, không cần hai bản sao của cột khóa trong kết quả.

## 4. NATURAL JOIN tự chọn mọi cột cùng tên

`NATURAL JOIN` không nhận danh sách cột. MySQL tự tìm các tên cột xuất hiện ở cả hai bảng và tạo điều kiện bằng nhau trên **tất cả** các cặp tên trùng đó.

Cú pháp:

```sql
SELECT select_list
FROM table_a
NATURAL JOIN table_b;
```

Với schema ban đầu, hai bảng chỉ có cột chung `department_id`, vì vậy:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    department_name
FROM join_employee_demo
NATURAL JOIN join_department_demo
ORDER BY department_id, employee_id;
```

hiện có kết quả giống phép nối:

```sql
... JOIN ... USING (department_id)
```

Tuy nhiên, sự giống nhau này chỉ đúng vì hiện tại `department_id` là tên cột chung duy nhất. `NATURAL JOIN` không biết khóa ngoại nào được khai báo và cũng không đọc ý nghĩa nghiệp vụ của các cột. Nó chỉ dựa trên tên cột.

### 4.1. NATURAL LEFT JOIN và NATURAL RIGHT JOIN

MySQL hỗ trợ các dạng outer natural join:

```sql
SELECT *
FROM join_department_demo
NATURAL LEFT JOIN join_employee_demo;

SELECT *
FROM join_employee_demo
NATURAL RIGHT JOIN join_department_demo;
```

Hai truy vấn trên giữ lại tất cả hàng từ phía được bảo toàn tương ứng. Các cột chung vẫn được gộp theo quy tắc của natural/using join.

### 4.2. Không có cột chung

Nếu hai bảng không có bất kỳ tên cột chung nào, `NATURAL JOIN` không có điều kiện bằng nhau để ghép và hành xử như tích Descartes (cross join). Nếu bảng trái có 10 hàng và bảng phải có 20 hàng, kết quả có thể có 200 tổ hợp.

Điều này dễ gây tăng số hàng đột ngột nếu một migration đổi tên hoặc loại bỏ cột chung. Khi cần tích Descartes có chủ ý, hãy viết `CROSS JOIN` để người đọc thấy rõ ý định; không dựa vào `NATURAL JOIN` để tạo tích Descartes ngầm.

## 5. Rủi ro schema drift: điều kiện nối thay đổi mà SQL không đổi

Rủi ro lớn nhất của `NATURAL JOIN` là danh sách cột dùng để nối không được ghi trong câu SQL. Nó được tính lại dựa trên schema tại thời điểm truy vấn chạy.

Hãy xem ví dụ ban đầu:

```sql
SELECT
    department_id,
    employee_id,
    department_name
FROM join_employee_demo
NATURAL JOIN join_department_demo;
```

Lúc đầu, cột chung duy nhất là `department_id`. Mỗi nhân viên được ghép với phòng ban theo mã phòng.

Giả sử sau này hai nhóm phát triển bổ sung cột `status`:

- Bảng nhân viên dùng `status` để biểu thị trạng thái làm việc: `ACTIVE`, `ON_LEAVE`.
- Bảng phòng ban dùng `status` để biểu thị trạng thái vận hành: `OPEN`, `CLOSED`.

Hai cột cùng tên nhưng có ý nghĩa khác nhau. Thực hiện migration:

```sql
ALTER TABLE join_employee_demo
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';

ALTER TABLE join_department_demo
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'OPEN';
```

Giờ đây hai bảng có hai tên cột chung: `department_id` và `status`. Câu `NATURAL JOIN` cũ tự động tương đương với:

```sql
SELECT
    e.department_id,
    e.employee_id,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id
   AND e.status = d.status;
```

Nhưng `ACTIVE` không bằng `OPEN`, `ON_LEAVE` cũng không bằng `CLOSED`. Những hàng từng ghép được theo phòng ban có thể biến mất khỏi kết quả. Không có lỗi cú pháp; truy vấn vẫn chạy, nhưng ngữ nghĩa đã thay đổi.

Kiểm tra:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    status
FROM join_employee_demo
NATURAL JOIN join_department_demo;
```

Kết quả có thể không còn hàng nào trong dữ liệu mẫu sau migration trên. Điều này minh họa lỗi nguy hiểm: schema thay đổi làm thay đổi điều kiện nối ngầm, và ứng dụng chỉ phát hiện khi kết quả thiếu hoặc sai.

### 5.1. Cùng tên không có nghĩa cùng ý nghĩa

Các tên cột thường xuất hiện ở nhiều bảng nhưng không phải lúc nào cũng là khóa nối:

- `status`: trạng thái đơn hàng, trạng thái tài khoản, trạng thái phòng ban.
- `created_at`: thời điểm tạo nhân viên, tạo phòng ban hoặc tạo bản ghi đồng bộ.
- `updated_at`: thời điểm cập nhật của từng thực thể.
- `name`: tên nhân viên, tên phòng ban, tên khách hàng.
- `tenant_id`: phạm vi tenant có thể cần tham gia khóa ghép, nhưng cũng có thể mang ngữ nghĩa khác ở nguồn dữ liệu cũ.

Nếu hai bảng có cùng tên `created_at`, `NATURAL JOIN` có thể yêu cầu hai thời điểm tạo bằng nhau. Đây gần như chắc chắn không phải điều kiện nối mong muốn. Tương tự, thêm `tenant_id` có thể vô tình làm phép nối trở nên chặt hơn hoặc thay đổi phạm vi dữ liệu.

### 5.2. Schema drift còn thay đổi hình dạng kết quả

Natural join không chỉ thay đổi điều kiện. Khi có thêm cột chung, số cột gộp và thứ tự cột của kết quả `SELECT *` cũng thay đổi. Nếu ứng dụng ánh xạ kết quả theo vị trí cột, hoặc view/API trả toàn bộ cột, migration có thể phá vỡ hợp đồng dữ liệu dù câu truy vấn vẫn hợp lệ.

Việc đổi tên hoặc xóa một cột chung cũng làm điều kiện natural join thay đổi. Nếu tất cả cột chung bị loại bỏ, truy vấn có thể chuyển thành tích Descartes. Vì vậy, `NATURAL JOIN` khiến tính đúng đắn của truy vấn phụ thuộc mạnh vào các thay đổi schema tưởng như không liên quan.

## 6. USING giảm rủi ro nào và vẫn cần quản lý điều gì?

`USING` ghi rõ danh sách cột nối ngay trong câu SQL:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    department_name,
    e.status AS employee_status,
    d.status AS department_status
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);
```

Khi hai bảng được thêm cột `status`, điều kiện nối vẫn chỉ là `department_id`. Câu truy vấn không tự động bắt đầu so sánh status. Đây là ưu điểm lớn so với `NATURAL JOIN`.

Tuy vậy, `USING` vẫn phụ thuộc vào các cột được nêu rõ:

- Nếu một cột trong danh sách bị đổi tên hoặc xóa ở một phía, truy vấn sẽ lỗi cho đến khi được cập nhật.
- Nếu kiểu dữ liệu, signedness hoặc collation của cột nối thay đổi, phép so sánh có thể phát sinh chuyển đổi hoặc thay đổi ngữ nghĩa.
- Nếu khóa nghiệp vụ thực tế trở thành khóa ghép, danh sách `USING` phải được mở rộng đúng lúc.
- Nếu cột chung không còn đại diện cùng một khái niệm, cần sửa mô hình hoặc chuyển sang `ON` với biểu thức rõ nghĩa.

Điểm khác biệt là thay đổi schema không tự thêm một điều kiện mới vào `USING`; chỉ danh sách đã viết mới được dùng.

## 7. ON, USING hay NATURAL JOIN?

| Cú pháp | Điều kiện nối | Cột chung trong kết quả | Mức phụ thuộc schema |
|---|---|---|---|
| `JOIN ... ON expression` | Biểu thức do người viết chỉ định | Giữ riêng hai cột nếu chọn cả hai | Thấp nhất; điều kiện hiện rõ trong SQL |
| `JOIN ... USING (a, b)` | Đẳng thức trên danh sách cột cùng tên được chỉ rõ | Gộp các cột đã liệt kê | Có phụ thuộc vào danh sách tên đã ghi |
| `NATURAL JOIN` | Đẳng thức trên tất cả tên cột chung | Gộp tất cả cột chung | Cao; thay đổi theo mọi cột chung trong schema |

### 7.1. Chọn ON khi

- Hai cột nối có tên khác nhau.
- Điều kiện nối không chỉ là đẳng thức trực tiếp.
- Cần nối bằng nhiều biểu thức, phép biến đổi hoặc điều kiện bổ sung.
- Cần so sánh null-safe bằng toán tử `<=>` của MySQL.
- Cần giữ và hiển thị riêng hai cột nguồn để kiểm tra.
- Muốn điều kiện nối tường minh nhất trong code production.

Ví dụ dùng null-safe equality:

```sql
SELECT *
FROM source_a AS a
JOIN source_b AS b
    ON a.external_code <=> b.external_code;
```

Khác với phép bằng thông thường, toán tử `<=>` của MySQL xem hai giá trị NULL là bằng nhau. `USING` và `NATURAL JOIN` biểu diễn phép nối bằng thông thường; chúng không cung cấp cú pháp để thay bằng null-safe equality.

### 7.2. Chọn USING khi

- Hai bảng có cột khóa cùng tên và cùng ý nghĩa.
- Điều kiện nối là phép bằng trên một hoặc nhiều cột đã biết.
- Muốn danh sách khóa được nối thể hiện ngay trong câu SQL.
- Muốn cột khóa chung chỉ xuất hiện một lần trong kết quả.

Ví dụ:

```sql
SELECT
    tenant_id,
    department_id,
    employee_id,
    department_name
FROM tenant_employee
JOIN tenant_department
USING (tenant_id, department_id);
```

### 7.3. Vì sao nên thận trọng với NATURAL JOIN?

`NATURAL JOIN` có thể ngắn gọn trong truy vấn thử nghiệm hoặc dữ liệu nhỏ có schema được kiểm soát chặt. Nhưng trong ứng dụng lâu dài, view, báo cáo và hệ thống có nhiều nhóm cùng thay đổi bảng, danh sách cột chung không được thể hiện trong SQL khiến việc review khó hơn.

Một migration thêm cột cho mục đích riêng có thể âm thầm thêm điều kiện nối. Vì vậy, hãy ưu tiên `ON` hoặc `USING` với danh sách cột được chỉ rõ trong truy vấn production.

## 8. NULL và điều kiện nối bằng USING

`USING` tạo phép so sánh bằng giữa hai cột. Theo logic SQL, `NULL = NULL` không trả về TRUE mà trả về UNKNOWN; vì vậy hai hàng có khóa nối NULL không khớp nhau.

Ví dụ:

```sql
CREATE TABLE nullable_key_a (
    row_id INT NOT NULL PRIMARY KEY,
    external_code VARCHAR(20) NULL
);

CREATE TABLE nullable_key_b (
    row_id INT NOT NULL PRIMARY KEY,
    external_code VARCHAR(20) NULL
);

INSERT INTO nullable_key_a VALUES (1, NULL), (2, 'A-10');
INSERT INTO nullable_key_b VALUES (1, NULL), (2, 'A-10');

SELECT *
FROM nullable_key_a
JOIN nullable_key_b USING (external_code);
```

Chỉ các hàng có `external_code = 'A-10'` khớp. Hai hàng có NULL không được ghép.

Nếu nghiệp vụ yêu cầu NULL khớp NULL, dùng `ON` với `<=>`:

```sql
SELECT
    a.row_id AS a_row_id,
    b.row_id AS b_row_id,
    a.external_code
FROM nullable_key_a AS a
JOIN nullable_key_b AS b
    ON a.external_code <=> b.external_code;
```

Hãy cân nhắc kỹ ý nghĩa của NULL trước khi dùng null-safe equality. Nếu NULL có nghĩa “chưa biết mã”, ghép mọi hàng NULL với nhau có thể tạo nhiều cặp không mong muốn. Với khóa định danh bắt buộc, thường nên khai báo `NOT NULL` và dùng giá trị khóa hợp lệ.

## 9. Kiểu dữ liệu và collation của cột nối

Các cột được nối nên có kiểu dữ liệu tương thích. Ví dụ, khóa số nên thống nhất `INT` với `INT`, hoặc `BIGINT UNSIGNED` với `BIGINT UNSIGNED` ở cả hai phía. Nếu một cột là signed và cột còn lại unsigned, hoặc một bên là số còn bên kia là chuỗi, MySQL có thể phải chuyển đổi kiểu khi so sánh.

Với cột chuỗi, hãy kiểm tra:

- Character set và collation.
- Độ dài và kiểu dữ liệu.
- Quy tắc hoa thường, dấu và khoảng trắng của khóa.
- Dữ liệu có được chuẩn hóa giống nhau ở hai bảng hay không.

Hai cột cùng tên chưa chắc có kiểu và quy tắc so sánh giống nhau. `USING` không tự sửa dữ liệu hoặc đồng nhất schema; nó chỉ tạo phép so sánh theo các cột được nêu. Hãy kiểm tra định nghĩa bằng:

```sql
SHOW CREATE TABLE join_employee_demo;
SHOW CREATE TABLE join_department_demo;
```

Đối với join trên cột có index, việc chuyển đổi kiểu hoặc áp dụng hàm lên cột có thể làm giảm khả năng dùng index. Hãy thiết kế hai phía tương thích và xác minh kế hoạch bằng `EXPLAIN`.

## 10. USING và NATURAL JOIN không tự động nhanh hơn ON

`USING` và `NATURAL JOIN` là cú pháp mô tả điều kiện nối. Khi chúng biểu diễn cùng một phép nối bằng trên cùng cột, optimizer có thể xây dựng kế hoạch tương đương với `ON`. Không nên chọn `USING` chỉ vì kỳ vọng nó nhanh hơn.

Hiệu năng phụ thuộc vào:

- Index trên cột khóa nối.
- Số hàng và độ chọn lọc của điều kiện.
- Thống kê của optimizer.
- Kiểu dữ liệu và phép chuyển đổi khi so sánh.
- Các điều kiện lọc bổ sung và thứ tự join mà optimizer chọn.
- Số cột cần đọc và số hàng thực sự trả về.

Ví dụ kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT
    e.employee_id,
    e.employee_name,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);

EXPLAIN
SELECT
    e.employee_id,
    e.employee_name,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id;
```

Hai truy vấn có cùng điều kiện logic nên thường có kế hoạch tương tự. Trên bảng mẫu nhỏ, MySQL có thể chọn table scan vì chi phí thấp; điều đó không chứng minh index không có ích trên bảng lớn. Hãy thử với dữ liệu và thống kê gần workload thật.

## 11. Cách kiểm tra tác động khi schema thay đổi

Trước khi thêm cột có tên phổ biến vào một bảng đang tham gia join, hãy tìm các truy vấn, view và stored program sử dụng `NATURAL JOIN`. Nếu có, kiểm tra danh sách cột chung trước và sau migration.

Có thể xem cấu trúc bảng:

```sql
SHOW COLUMNS FROM join_employee_demo;
SHOW COLUMNS FROM join_department_demo;
```

Hoặc kiểm tra các tên cột chung bằng metadata:

```sql
SELECT
    a.COLUMN_NAME,
    a.COLUMN_TYPE AS employee_column_type,
    b.COLUMN_TYPE AS department_column_type,
    a.IS_NULLABLE AS employee_nullable,
    b.IS_NULLABLE AS department_nullable
FROM information_schema.columns AS a
JOIN information_schema.columns AS b
    ON b.COLUMN_NAME = a.COLUMN_NAME
WHERE a.TABLE_SCHEMA = DATABASE()
  AND b.TABLE_SCHEMA = DATABASE()
  AND a.TABLE_NAME = 'join_employee_demo'
  AND b.TABLE_NAME = 'join_department_demo'
ORDER BY a.ORDINAL_POSITION;
```

Truy vấn trên giúp liệt kê tên cột chung và so sánh kiểu/nullability cơ bản. Nó không thể xác định hai cột có cùng ý nghĩa nghiệp vụ hay không; việc đó cần được xác nhận trong thiết kế dữ liệu.

Quy trình review migration nên gồm:

1. Tìm câu truy vấn dùng `NATURAL JOIN` trên các bảng bị thay đổi.
2. Liệt kê tên cột chung hiện tại và tên cột chung sau migration.
3. Viết lại điều kiện nối thành `ON` hoặc `USING` với khóa nghiệp vụ chính xác.
4. So sánh số hàng, khóa định danh và các trường hợp không khớp trước/sau.
5. Kiểm tra kết quả `SELECT *` nếu ứng dụng hoặc view đang phụ thuộc thứ tự cột.
6. Chạy kiểm thử tích hợp cho các truy vấn, view và báo cáo liên quan.
7. Triển khai migration cùng thay đổi truy vấn theo một kế hoạch tương thích.

## 12. Ví dụ chuyển NATURAL JOIN thành USING hoặc ON

Giả sử truy vấn hiện tại:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    department_name
FROM join_employee_demo
NATURAL JOIN join_department_demo;
```

Nếu ý nghĩa nghiệp vụ là ghép nhân viên theo phòng ban, thay bằng `USING`:

```sql
SELECT
    department_id,
    e.employee_id,
    e.employee_name,
    d.department_name,
    e.status AS employee_status,
    d.status AS department_status
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);
```

Hoặc dùng `ON` nếu muốn điều kiện hoàn toàn tường minh:

```sql
SELECT
    e.department_id,
    e.employee_id,
    e.employee_name,
    d.department_name,
    e.status AS employee_status,
    d.status AS department_status
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id;
```

Hai cách trên giữ điều kiện nối theo `department_id` ngay cả khi cả hai bảng có thêm `status`, `created_at` hoặc `updated_at`. Nếu sau này khóa phòng ban chuyển thành khóa ghép theo tenant, hãy cập nhật danh sách `USING (tenant_id, department_id)` hoặc điều kiện `ON` theo đúng mô hình mới.

## 13. Những lỗi thường gặp

- Nghĩ `NATURAL JOIN` tự nối theo primary key hoặc foreign key; thực tế nó dùng tất cả tên cột chung.
- Nghĩ `USING` và `NATURAL JOIN` chỉ là cách viết khác nhau của `ON` mà không có khác biệt về hình dạng kết quả.
- Dùng `NATURAL JOIN` giữa hai bảng có các cột phổ biến như `status`, `created_at`, `name` nhưng không kiểm tra ý nghĩa.
- Thêm cột cùng tên vào hai bảng và vô tình làm thay đổi điều kiện natural join.
- Đổi tên hoặc xóa cột chung khiến natural join đổi điều kiện hoặc không còn điều kiện nối.
- Không có cột chung nhưng vẫn dùng natural join, vô tình tạo tích Descartes.
- Dùng `USING` với tên cột chỉ tồn tại ở một bảng hoặc ghi alias có định danh trong danh sách.
- Chỉ nối một phần khóa ghép, làm ghép nhầm dữ liệu giữa tenant hoặc phạm vi nghiệp vụ.
- Giả định hai giá trị NULL sẽ khớp nhau trong USING; phép bằng thông thường không khớp NULL với NULL.
- Dùng `SELECT *` rồi phụ thuộc thứ tự cột gộp, khiến schema change phá hợp đồng kết quả.
- Nghĩ `USING` nhanh hơn `ON` mà không đo execution plan.
- Bỏ qua khác biệt kiểu dữ liệu, signedness hoặc collation giữa hai cột nối.

## 14. Checklist chọn và review cú pháp JOIN

- Đã xác định khóa nghiệp vụ đầy đủ và mọi thành phần của khóa ghép.
- Đã xác nhận cột hai phía có cùng ý nghĩa, kiểu dữ liệu và quy tắc so sánh.
- Đã dùng `ON` khi tên cột khác nhau, cần biểu thức tùy chỉnh hoặc null-safe equality.
- Đã dùng `USING` khi các cột nối cùng tên, cùng ý nghĩa và danh sách được xác định rõ.
- Đã tránh `NATURAL JOIN` trong truy vấn production phụ thuộc schema thay đổi theo thời gian.
- Đã hiểu các cột USING/NATURAL được gộp và ảnh hưởng đến `SELECT *`.
- Đã kiểm tra hành vi của `LEFT JOIN`/`RIGHT JOIN` với hàng không khớp và cột gộp.
- Đã kiểm tra NULL có thể xuất hiện trong khóa và quyết định rõ có cần null-safe equality hay không.
- Đã kiểm tra tên cột chung trước/sau migration nếu còn natural join trong hệ thống.
- Đã liệt kê cột kết quả rõ ràng cho API, view và báo cáo.
- Đã kiểm tra index và execution plan bằng `EXPLAIN` trên dữ liệu phù hợp.
- Đã có kiểm thử tích hợp cho truy vấn phụ thuộc vào schema đang thay đổi.

`USING` là lựa chọn ngắn gọn và tường minh khi hai bảng nối bằng các cột cùng tên đã được xác định. `NATURAL JOIN` tự suy luận điều kiện từ mọi tên cột chung, vì vậy một thay đổi schema tưởng như không liên quan có thể âm thầm đổi kết quả hoặc làm truy vấn thành tích Descartes. Trong hệ thống cần bảo trì lâu dài, hãy ưu tiên `ON` hoặc `USING` với danh sách khóa rõ ràng, tránh phụ thuộc vào `SELECT *`, và kiểm tra các truy vấn join trong mỗi lần migration.
