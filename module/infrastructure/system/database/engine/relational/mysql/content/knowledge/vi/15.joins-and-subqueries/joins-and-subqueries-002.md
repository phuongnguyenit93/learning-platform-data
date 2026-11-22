# LEFT/RIGHT OUTER JOIN và dữ liệu không có bản ghi tương ứng

Trong cơ sở dữ liệu quan hệ, một hàng ở bảng này có thể không có hàng tương ứng ở bảng khác. Một phòng ban có thể chưa có nhân viên; một nhân viên có thể chưa được phân phòng ban; hoặc một khóa tham chiếu có giá trị nhưng bản ghi cha đã bị thiếu do dữ liệu nhập lỗi. Nếu dùng `INNER JOIN`, những hàng không có cặp tương ứng sẽ biến mất khỏi kết quả. `LEFT OUTER JOIN` và `RIGHT OUTER JOIN` cho phép giữ lại các hàng ở một phía và biểu diễn phần không khớp bằng `NULL` ở phía còn lại.

Trong MySQL, từ khóa `OUTER` là tùy chọn: `LEFT JOIN` tương đương `LEFT OUTER JOIN`, và `RIGHT JOIN` tương đương `RIGHT OUTER JOIN`. `LEFT JOIN` giữ tất cả hàng của bảng bên trái; `RIGHT JOIN` giữ tất cả hàng của bảng bên phải. Hiểu chính xác bảng nào được giữ, điều kiện nào thuộc `ON`, điều kiện nào thuộc `WHERE` và cách nhận biết hàng không khớp là nền tảng để viết báo cáo, tìm dữ liệu mồ côi và kiểm tra chất lượng dữ liệu.

Bài học này thuộc module `DATABASE_MYSQL`, nơi bạn thực hành thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và tối ưu truy vấn. Mục tiêu là viết outer join đúng ngữ nghĩa khi dữ liệu có thể thiếu quan hệ, đồng thời tránh vô tình biến outer join thành inner join hoặc nhân bản hàng do quan hệ một-nhiều.

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa `INNER JOIN`, `LEFT JOIN` và `RIGHT JOIN`.
- Xác định phía được bảo toàn và phía có thể được bổ sung `NULL`.
- Đặt điều kiện trong `ON` hoặc `WHERE` theo đúng yêu cầu nghiệp vụ.
- Tìm bản ghi không có đối tượng tương ứng bằng `LEFT JOIN ... IS NULL` và `NOT EXISTS`.
- Phân biệt khóa ngoại `NULL` với khóa tham chiếu không tồn tại.
- Đếm đúng hàng sau outer join và xử lý quan hệ một-nhiều.
- Viết truy vấn `RIGHT JOIN`, chuyển đổi tương đương sang `LEFT JOIN` và hiểu cách mô phỏng `FULL OUTER JOIN` trong MySQL.
- Kiểm tra index và kế hoạch thực thi của outer join.

## 1. Outer join giải quyết vấn đề gì?

Giả sử hệ thống có bảng `departments` và `employees`. Một số phòng ban có nhiều nhân viên, một số phòng ban chưa có nhân viên. Ngoài ra, một nhân viên có thể chưa được gán phòng ban hoặc có `department_id` trỏ tới mã phòng ban không tồn tại.

Nếu câu hỏi là “Liệt kê tất cả phòng ban và nhân viên thuộc từng phòng ban”, `INNER JOIN` sẽ chỉ trả các phòng ban có nhân viên khớp. Những phòng ban chưa có nhân viên bị loại khỏi kết quả. `LEFT JOIN` giữ tất cả phòng ban và đặt các cột nhân viên thành `NULL` nếu không có nhân viên phù hợp.

Nếu câu hỏi là “Liệt kê tất cả nhân viên và phòng ban của họ nếu có”, cần giữ tất cả nhân viên. Có thể dùng `RIGHT JOIN` với `departments` ở bên trái và `employees` ở bên phải, hoặc đổi thứ tự bảng để dùng `LEFT JOIN`.

| Loại JOIN | Hàng được giữ đầy đủ | Khi không có hàng khớp |
| --- | --- | --- |
| `INNER JOIN` | Chỉ các cặp hàng khớp | Hàng không khớp bị loại |
| `LEFT JOIN` | Bảng bên trái | Cột phía phải được đặt `NULL` |
| `RIGHT JOIN` | Bảng bên phải | Cột phía trái được đặt `NULL` |

Outer join không tự tạo ra một bản ghi thật trong bảng còn thiếu. Các giá trị `NULL` trong kết quả là hàng bổ sung do phép join tạo ra để giữ hàng ở phía được bảo toàn.

## 2. Tạo fixture để quan sát hàng khớp và không khớp

Chạy ví dụ trong cùng một session MySQL. Không khai báo foreign key ở fixture này vì ta muốn chủ động tạo một nhân viên có `department_id` không tồn tại để kiểm tra dữ liệu mồ côi.

```sql
DROP TEMPORARY TABLE IF EXISTS employees;
DROP TEMPORARY TABLE IF EXISTS departments;

CREATE TEMPORARY TABLE departments (
    department_id INT UNSIGNED NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (department_id)
) ENGINE = InnoDB;

CREATE TEMPORARY TABLE employees (
    employee_id INT UNSIGNED NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    department_id INT UNSIGNED NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (employee_id),
    KEY idx_employees_department (department_id)
) ENGINE = InnoDB;

INSERT INTO departments (department_id, department_name) VALUES
(10, 'Engineering'),
(20, 'Sales'),
(30, 'Legal'),
(40, 'Operations');

INSERT INTO employees (employee_id, employee_name, department_id, is_active) VALUES
(1, 'An',     10, 1),
(2, 'Binh',   10, 1),
(3, 'Chi',    20, 1),
(4, 'Dung', NULL, 1),
(5, 'Em',     99, 1),
(6, 'Giang',  20, 0);
```

Các trường hợp trong fixture:

| Bản ghi | Ý nghĩa |
| --- | --- |
| Department 10 | Có hai nhân viên đang hoạt động |
| Department 20 | Có một nhân viên hoạt động và một nhân viên không hoạt động |
| Department 30 và 40 | Không có nhân viên |
| Employee 4 | `department_id IS NULL`, chưa được gán phòng ban |
| Employee 5 | `department_id = 99`, nhưng không có phòng ban 99 |
| Employee 6 | Có phòng ban hợp lệ nhưng `is_active = 0` |

Fixture phân biệt ba trạng thái thường bị gộp nhầm: không có khóa tham chiếu (`NULL`), có khóa tham chiếu nhưng không tìm thấy bản ghi cha (orphan key), và có quan hệ hợp lệ.

## 3. LEFT JOIN — giữ tất cả hàng bên trái

Cú pháp:

```sql
SELECT select_list
FROM left_table AS l
LEFT [OUTER] JOIN right_table AS r
    ON join_condition;
```

Với `LEFT JOIN`, mọi hàng từ `left_table` đều xuất hiện ít nhất một lần. Nếu một hàng bên trái có một hoặc nhiều hàng bên phải thỏa `ON`, kết quả có một hàng cho mỗi cặp khớp. Nếu không có hàng bên phải phù hợp, MySQL tạo một hàng kết quả với tất cả cột phía phải là `NULL`.

Ví dụ liệt kê tất cả phòng ban và nhân viên:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

Kết quả mong đợi:

| department_id | department_name | employee_id | employee_name |
| ---: | --- | ---: | --- |
| 10 | Engineering | 1 | An |
| 10 | Engineering | 2 | Binh |
| 20 | Sales | 3 | Chi |
| 20 | Sales | 6 | Giang |
| 30 | Legal | `NULL` | `NULL` |
| 40 | Operations | `NULL` | `NULL` |

Employee 4 và 5 không xuất hiện vì truy vấn giữ tất cả phòng ban, không giữ tất cả nhân viên. Đây là điểm cần xác định trước khi chọn phía trái/phải.

### 3.1. Một hàng trái có nhiều hàng phải

Department 10 xuất hiện hai lần vì có hai nhân viên. `LEFT JOIN` không gom các hàng con thành một hàng. Nếu muốn một hàng cho mỗi phòng ban, hãy dùng aggregate hoặc truy vấn con phù hợp:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Kết quả có bốn phòng ban, với số nhân viên lần lượt là 2, 2, 0, 0. Ở đây `COUNT(e.employee_id)` đếm khóa chính của hàng bên phải. Với phòng ban không có nhân viên, cột `employee_id` được bổ sung là `NULL`, nên count bằng 0.

## 4. RIGHT JOIN — giữ tất cả hàng bên phải

Cú pháp:

```sql
SELECT select_list
FROM left_table AS l
RIGHT [OUTER] JOIN right_table AS r
    ON join_condition;
```

Với `RIGHT JOIN`, mọi hàng của bảng bên phải được giữ lại. Nếu không có hàng trái phù hợp, các cột từ bảng bên trái nhận `NULL`.

Ví dụ: liệt kê mọi nhân viên và phòng ban tương ứng nếu có:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.department_id AS employee_department_id
FROM departments AS d
RIGHT JOIN employees AS e
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

Kết quả mong đợi:

| department_id | department_name | employee_id | employee_name | employee_department_id |
| ---: | --- | ---: | --- | ---: |
| 10 | Engineering | 1 | An | 10 |
| 10 | Engineering | 2 | Binh | 10 |
| 20 | Sales | 3 | Chi | 20 |
| `NULL` | `NULL` | 4 | Dung | `NULL` |
| `NULL` | `NULL` | 5 | Em | 99 |
| 20 | Sales | 6 | Giang | 20 |

Employee 4 và 5 vẫn xuất hiện vì bảng `employees` nằm ở phía phải được bảo toàn. Employee 4 chưa có mã phòng ban; employee 5 có mã 99 nhưng không có hàng phòng ban khớp.

### 4.1. Viết RIGHT JOIN thành LEFT JOIN

Truy vấn trên có thể viết lại bằng cách đổi thứ tự hai bảng:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.department_id AS employee_department_id
FROM employees AS e
LEFT JOIN departments AS d
    ON d.department_id = e.department_id
ORDER BY e.employee_id;
```

Hai truy vấn có cùng ý nghĩa và tập kết quả. Nhiều nhóm phát triển ưu tiên `LEFT JOIN` vì có thể đọc từ bảng cần giữ đầy đủ sang bảng bổ sung. Tuy nhiên, `RIGHT JOIN` vẫn là cú pháp hợp lệ trong MySQL; điều quan trọng là hiểu đúng phía được bảo toàn.

## 5. Phân biệt ON và WHERE trong outer join

Đây là phần dễ gây lỗi nhất khi dùng outer join. Điều kiện trong `ON` quyết định hàng nào được coi là khớp. Điều kiện trong `WHERE` lọc kết quả sau khi phép join đã tạo các hàng có cột `NULL` ở phía không khớp.

### 5.1. Giữ mọi phòng ban nhưng chỉ ghép nhân viên đang hoạt động

Yêu cầu: liệt kê tất cả phòng ban; chỉ ghép nhân viên `is_active = 1`.

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
   AND e.is_active = 1
ORDER BY d.department_id, e.employee_id;
```

Kết quả vẫn có đủ bốn phòng ban. Department 20 chỉ ghép employee 3; employee 6 không thỏa điều kiện trong `ON`, nên không được ghép. Department 30 và 40 không có nhân viên hoạt động, vì vậy các cột employee là `NULL`.

### 5.2. Đưa điều kiện sang WHERE làm mất hàng không khớp

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
WHERE e.is_active = 1
ORDER BY d.department_id, e.employee_id;
```

Với department 30 và 40, `e.is_active` là `NULL`; điều kiện `NULL = 1` không phải `TRUE`, nên các hàng đó bị loại. Kết quả không còn giữ mọi phòng ban. Điều kiện `WHERE` này làm truy vấn có hành vi tương tự inner join đối với điều kiện hoạt động.

Quy tắc thực hành:

- Muốn giữ mọi hàng ở phía được bảo toàn và chỉ giới hạn các hàng ghép ở phía còn lại: đặt điều kiện ghép trong `ON`.
- Muốn loại cả hàng được bảo toàn khi điều kiện không thỏa: đặt điều kiện trong `WHERE`.
- Đừng di chuyển điều kiện giữa `ON` và `WHERE` mà không kiểm tra lại expected result.

### 5.3. Điều kiện WHERE trên phía được bảo toàn

Điều kiện `WHERE` trên bảng bên trái của `LEFT JOIN` vẫn lọc hàng trái như bình thường:

```sql
SELECT d.department_id, d.department_name, e.employee_name
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
WHERE d.department_id IN (10, 20);
```

Kết quả chỉ giữ phòng ban 10 và 20. Điều đó không làm mất ý nghĩa outer join đối với hai phòng ban còn lại trong tập được chọn; bảng trái vẫn được bảo toàn sau khi điều kiện lọc áp dụng.

Với `RIGHT JOIN`, nguyên tắc tương tự nhưng phía được bảo toàn là bảng bên phải. Nếu cần giữ mọi nhân viên, hãy đặt điều kiện giới hạn phòng ban tùy chọn trong `ON`; đặt điều kiện cột phòng ban trong `WHERE` có thể loại nhân viên không có phòng ban khớp.

## 6. Tìm bản ghi không có bản ghi tương ứng

Một ứng dụng phổ biến của outer join là tìm hàng ở một bảng không có hàng liên quan ở bảng kia. Đây thường được gọi là anti-join.

### 6.1. Phòng ban chưa có nhân viên

```sql
SELECT
    d.department_id,
    d.department_name
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
```

Expected result: department 30 và 40. `employee_id` là primary key, không thể `NULL` ở một hàng thật. Vì vậy, khi nó là `NULL` trong kết quả outer join, ta biết không có hàng employee nào khớp.

### 6.2. Dùng NOT EXISTS

Cùng yêu cầu có thể viết bằng `NOT EXISTS`:

```sql
SELECT d.department_id, d.department_name
FROM departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees AS e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
```

`NOT EXISTS` diễn đạt trực tiếp rằng không tồn tại hàng con tương ứng. Nó không cần tạo hàng bổ sung có các cột `NULL` rồi lọc lại. Optimizer MySQL có thể chuyển một số truy vấn dạng này thành anti-join; hãy kiểm tra `EXPLAIN` với truy vấn và phiên bản thực tế.

`NOT EXISTS` thường an toàn hơn `NOT IN` khi tập con có thể chứa `NULL`, vì một giá trị `NULL` trong subquery có thể làm kết quả `NOT IN` trở thành `UNKNOWN`.

### 6.3. Chọn cột kiểm tra IS NULL đúng

Khi dùng `LEFT JOIN ... WHERE right_column IS NULL`, cột kiểm tra phải là cột chắc chắn `NOT NULL` ở một hàng thật, thường là primary key hoặc unique key được khai báo `NOT NULL`.

Không nên dùng:

```sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
LEFT JOIN departments AS d
    ON d.department_id = e.department_id
WHERE d.department_name IS NULL;
```

Truy vấn này có thể tìm cả hàng không khớp lẫn hàng khớp với một phòng ban mà `department_name` được phép `NULL` trong schema khác. Trong fixture hiện tại `department_name` là `NOT NULL`, nhưng dùng khóa chính vẫn thể hiện ý nghĩa kiểm tra rõ hơn:

```sql
WHERE d.department_id IS NULL
```

## 7. Phân biệt khóa ngoại NULL và khóa mồ côi

Ở bảng `employees`, có hai trường hợp khác nhau:

- Employee 4 có `department_id IS NULL`: chưa chỉ định phòng ban.
- Employee 5 có `department_id = 99`: có mã tham chiếu nhưng không có phòng ban 99.

Để tìm tất cả nhân viên chưa ghép được với phòng ban:

```sql
SELECT e.employee_id, e.employee_name, e.department_id
FROM employees AS e
LEFT JOIN departments AS d
    ON d.department_id = e.department_id
WHERE d.department_id IS NULL
ORDER BY e.employee_id;
```

Kết quả gồm employee 4 và 5.

Để phân loại rõ hai trường hợp:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    CASE
        WHEN e.department_id IS NULL THEN 'NOT_ASSIGNED'
        WHEN d.department_id IS NULL THEN 'ORPHAN_REFERENCE'
        ELSE 'MATCHED'
    END AS relation_status
FROM employees AS e
LEFT JOIN departments AS d
    ON d.department_id = e.department_id
ORDER BY e.employee_id;
```

Kết quả phân loại:

| employee_id | relation_status |
| ---: | --- |
| 1 | MATCHED |
| 2 | MATCHED |
| 3 | MATCHED |
| 4 | NOT_ASSIGNED |
| 5 | ORPHAN_REFERENCE |
| 6 | MATCHED |

Trong schema production, foreign key có thể ngăn việc tạo khóa mồ côi mới. Tuy nhiên, cột foreign key nullable vẫn có thể nhận `NULL` nếu không khai báo `NOT NULL`; `NULL` thường biểu thị không có quan hệ được chỉ định. Outer join hữu ích để rà soát dữ liệu cũ, dữ liệu import hoặc schema chưa có ràng buộc tham chiếu.

## 8. COUNT và aggregate sau outer join

Outer join tạo hàng bổ sung cho phía không khớp. Vì vậy, chọn biểu thức đếm đúng là rất quan trọng.

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS joined_rows,
    COUNT(e.employee_id) AS employee_count,
    COUNT(e.department_id) AS non_null_department_values
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Với department 30 và 40:

- `COUNT(*) = 1` vì hàng phòng ban vẫn xuất hiện trong kết quả join.
- `COUNT(e.employee_id) = 0` vì không có employee thật được ghép.
- `COUNT(e.department_id) = 0` vì cột phía phải trong hàng bổ sung là `NULL`.

Khi cần đếm nhân viên, dùng `COUNT(e.employee_id)` vì `employee_id` là khóa chính không nullable. Nếu dùng `COUNT(*)`, mọi phòng ban không có nhân viên vẫn bị đếm thành một hàng.

### 8.1. SUM và AVG sau LEFT JOIN

`SUM(e.salary)` hoặc `AVG(e.salary)` trên nhóm không có nhân viên sẽ trả `NULL`. Nếu báo cáo cần hiển thị 0, có thể dùng `COALESCE(SUM(e.salary), 0)`. Hãy quyết định điều đó theo ngữ nghĩa báo cáo.

Không đặt `COALESCE()` vào từng hàng trước aggregate nếu điều đó làm thay đổi mẫu số trung bình:

```sql
-- Trung bình của các giá trị salary có dữ liệu
AVG(e.salary)

-- Mỗi hàng NULL được đổi thành 0 trước khi tính trung bình
AVG(COALESCE(e.salary, 0))
```

Hai biểu thức có ý nghĩa khác nhau. Với phòng ban không có nhân viên, biểu thức thứ hai có thể tính trên hàng bổ sung của outer join và trả 0 thay vì `NULL`. Với nhóm có nhân viên nhưng một số salary NULL, biểu thức thứ hai xem các salary thiếu như 0, làm giảm trung bình. Chỉ dùng cách này khi nghiệp vụ thực sự định nghĩa giá trị thiếu là 0.

## 9. JOIN một-nhiều và nguy cơ nhân bản hàng

Outer join không bảo đảm mỗi hàng phía được bảo toàn chỉ xuất hiện một lần. Nếu một phòng ban có nhiều nhân viên, phòng ban được lặp lại cho mỗi nhân viên. Nếu join thêm một bảng con một-nhiều khác, số hàng có thể tăng theo tích số lượng hàng ở các quan hệ con.

Ví dụ, nếu một phòng ban có 2 nhân viên và mỗi nhân viên có 3 kỹ năng, join `departments -> employees -> employee_skills` có thể tạo 6 hàng cho phòng ban đó. Khi đó `COUNT(e.employee_id)` có thể đếm mỗi nhân viên nhiều lần.

Nếu cần đếm nhân viên duy nhất trong join nhiều bảng, có thể dùng `COUNT(DISTINCT e.employee_id)`, nhưng trước hết cần hiểu cardinality và mục đích phép đếm. Nếu cần tổng hợp từng bảng con, thường nên aggregate về một hàng trên mỗi khóa cha trước khi join.

Ví dụ tổng hợp số nhân viên hoạt động theo phòng ban:

```sql
SELECT
    d.department_id,
    d.department_name,
    COALESCE(employee_totals.active_employee_count, 0) AS active_employee_count
FROM departments AS d
LEFT JOIN (
    SELECT department_id, COUNT(*) AS active_employee_count
    FROM employees
    WHERE is_active = 1
    GROUP BY department_id
) AS employee_totals
    ON employee_totals.department_id = d.department_id
ORDER BY d.department_id;
```

Derived table chỉ có tối đa một hàng cho mỗi `department_id`, nhờ vậy kết quả có đúng một hàng cho mỗi phòng ban.

## 10. RIGHT JOIN và cách đọc điều kiện

Với `RIGHT JOIN`, bảng bên phải là phía được bảo toàn. Trong truy vấn:

```sql
SELECT d.department_name, e.employee_name
FROM departments AS d
RIGHT JOIN employees AS e
    ON e.department_id = d.department_id
WHERE d.department_name = 'Sales';
```

`WHERE d.department_name = 'Sales'` loại employee không có phòng ban khớp, vì `d.department_name` là `NULL` cho các hàng đó. Nếu muốn giữ mọi employee và chỉ hiển thị tên phòng ban khi phòng ban có tên Sales, điều kiện phải nằm trong `ON`:

```sql
SELECT d.department_name, e.employee_name
FROM departments AS d
RIGHT JOIN employees AS e
    ON e.department_id = d.department_id
   AND d.department_name = 'Sales';
```

Truy vấn thứ hai giữ toàn bộ nhân viên; những người không thuộc Sales có cột phòng ban được bổ sung `NULL`. Tuy nhiên, nếu mục tiêu là chỉ liệt kê nhân viên Sales thì điều kiện `WHERE` mới là đúng. Hãy chọn vị trí điều kiện theo câu hỏi nghiệp vụ, không theo một quy tắc máy móc rằng mọi điều kiện phải nằm trong `ON`.

## 11. FULL OUTER JOIN không có cú pháp trực tiếp trong MySQL

MySQL không cung cấp cú pháp `FULL OUTER JOIN` trực tiếp. Nếu cần giữ tất cả hàng từ cả hai phía, có thể ghép:

1. Một `LEFT JOIN` để lấy mọi phòng ban cùng nhân viên khớp hoặc `NULL`.
2. Một truy vấn lấy những nhân viên chưa có phòng ban khớp.
3. Dùng `UNION ALL` để nối hai tập kết quả.

Ví dụ:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id

UNION ALL

SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM employees AS e
LEFT JOIN departments AS d
    ON d.department_id = e.department_id
WHERE d.department_id IS NULL
ORDER BY department_id, employee_id;
```

Nhánh đầu lấy tất cả phòng ban, kể cả phòng ban không có nhân viên. Nhánh sau chỉ lấy nhân viên không khớp phòng ban, tránh lặp lại các cặp đã có trong nhánh đầu. `UNION ALL` giữ nguyên các hàng; dùng `UNION` có thể loại các hàng trùng theo toàn bộ cột kết quả và làm thay đổi ngữ nghĩa nếu hai hàng hợp lệ có giá trị giống nhau.

Đây là mô phỏng full outer join theo khóa ghép đã khai báo. Nếu điều kiện join phức tạp hoặc có nhiều cột nullable, hãy kiểm tra khóa nhận diện hàng không khớp và cardinality cẩn thận.

## 12. NULL trong điều kiện JOIN

Với phép so sánh bằng thông thường:

```sql
ON e.department_id = d.department_id
```

Nếu `e.department_id` là `NULL`, biểu thức so sánh không trả `TRUE`, vì vậy employee đó không khớp phòng ban nào. Đây thường là hành vi mong muốn khi `NULL` nghĩa là chưa được gán.

MySQL có toán tử null-safe equality `<=>`:

```sql
ON e.department_id <=> d.department_id
```

`<=>` xem `NULL <=> NULL` là `TRUE`. Chỉ dùng khi nghiệp vụ định nghĩa hai giá trị NULL là cùng một nhóm quan hệ. Nếu có nhiều hàng NULL ở cả hai phía, chúng có thể ghép chéo với nhau và tạo nhiều hàng ngoài dự kiến. Với khóa ngoại nullable, thông thường không nên coi tất cả giá trị NULL là cùng một thực thể cha.

Đừng nhầm `NULL` do không có hàng khớp với `NULL` vốn có trong một hàng thật. Khi cần phân biệt, hãy kiểm tra khóa chính không nullable của phía được ghép, hoặc thêm cột đánh dấu/metadata phù hợp trong truy vấn.

## 13. Index và hiệu năng của outer join

Outer join thường cần tìm hàng khớp theo khóa. Index trên cột join của bảng được tra cứu có thể giúp giảm số hàng phải quét.

Trong fixture:

- `departments.department_id` là primary key.
- `employees.department_id` có index `idx_employees_department`.

Đây là bố cục thường gặp: bảng cha có primary/unique key, bảng con có index trên foreign key. Trong InnoDB, khai báo foreign key thường yêu cầu index phù hợp ở bảng con; nếu chưa có index phù hợp, MySQL có thể tạo index cần thiết.

Kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

Quan sát:

- Bảng nào được đọc trước và thứ tự join mà optimizer chọn.
- `type`, `possible_keys`, `key`, `rows` và `Extra`.
- Điều kiện join có dùng index hay phải quét nhiều hàng.
- Số hàng thực tế so với ước lượng nếu dùng `EXPLAIN ANALYZE`.

Một số nguyên tắc:

- Kiểu dữ liệu của hai cột join nên tương thích, bao gồm signedness của số nguyên, charset và collation của chuỗi.
- Index trên cột join thường quan trọng, nhưng không phải mọi outer join đều cần một index mới; xem xét index hiện có và workload tổng thể.
- Không bọc cột join trong hàm nếu không có lý do và index phù hợp, vì có thể làm điều kiện khó sử dụng index.
- Lọc hàng ở phía không được bảo toàn trong `ON` khi muốn giữ mọi hàng phía được bảo toàn.
- Đừng kết luận từ fixture vài hàng; đánh giá trên dữ liệu có quy mô và phân bố gần thực tế.

`EXPLAIN ANALYZE` thực thi truy vấn thật. Chỉ dùng trên truy vấn và môi trường có thể chấp nhận tải phát sinh.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đổi `LEFT JOIN` thành `INNER JOIN` mà không xét hàng thiếu | Hàng cha không có hàng con biến mất | Giữ outer join nếu nghiệp vụ cần hàng không khớp |
| Đặt điều kiện bảng phải trong `WHERE` | Có thể loại các hàng được bổ sung NULL | Đặt trong `ON` nếu chỉ muốn giới hạn hàng được ghép |
| Dùng `COUNT(*)` để đếm hàng con sau LEFT JOIN | Hàng cha không có con bị đếm thành 1 | Dùng `COUNT(child.primary_key)` |
| Kiểm tra `IS NULL` trên cột nullable của hàng thật | Nhầm hàng khớp có giá trị NULL với hàng không khớp | Kiểm tra primary key hoặc cột NOT NULL |
| Dùng `NOT IN` với subquery có NULL | Điều kiện có thể thành UNKNOWN và không trả hàng mong muốn | Dùng `NOT EXISTS` hoặc loại NULL có chủ đích |
| Nghĩ LEFT JOIN chỉ trả một hàng cho mỗi hàng trái | Bỏ sót quan hệ một-nhiều | Kiểm tra cardinality và aggregate khi cần |
| Dùng `<=>` cho khóa nullable mà không hiểu hệ quả | Các hàng NULL có thể ghép chéo | Dùng `=` cho quan hệ khóa thông thường |
| Dùng `UNION` khi mô phỏng FULL OUTER JOIN | Loại các hàng trùng hợp lệ | Dùng `UNION ALL` với nhánh anti-join |
| Không thêm ORDER BY | Thứ tự kết quả không được bảo đảm | Thêm thứ tự và khóa phân xử duy nhất nếu cần |

## 15. Quy trình chọn JOIN theo câu hỏi

Trước khi viết SQL, xác định bảng nào phải xuất hiện đầy đủ:

| Câu hỏi | Cấu trúc thường phù hợp |
| --- | --- |
| Chỉ cần hàng có quan hệ ở cả hai bảng | `INNER JOIN` |
| Giữ mọi phòng ban, thêm nhân viên nếu có | `departments LEFT JOIN employees` |
| Giữ mọi nhân viên, thêm phòng ban nếu có | `employees LEFT JOIN departments` hoặc `departments RIGHT JOIN employees` |
| Tìm phòng ban không có nhân viên | `LEFT JOIN ... WHERE employee_pk IS NULL` hoặc `NOT EXISTS` |
| Tìm nhân viên chưa có phòng ban hợp lệ | `employees LEFT JOIN departments ... WHERE department_pk IS NULL` |
| Giữ mọi hàng ở cả hai phía | Mô phỏng bằng `LEFT JOIN UNION ALL` với nhánh anti-join |

Sau khi chọn loại join:

1. Viết điều kiện ghép bằng khóa và xác định cột có thể NULL.
2. Xác định điều kiện nào quyết định “khớp” và đặt trong `ON`.
3. Xác định điều kiện nào lọc kết quả cuối và đặt trong `WHERE`.
4. Kiểm tra số hàng dự kiến cho quan hệ một-một, một-nhiều và không có quan hệ.
5. Chọn cột khóa không nullable để phát hiện hàng không khớp.
6. Kiểm tra kết quả và `EXPLAIN` trên dữ liệu đại diện.

## 16. Bài tập thực hành

1. Chạy fixture ở phần 2. Viết `LEFT JOIN` để liệt kê mọi phòng ban và nhân viên; đối chiếu bốn phòng ban đều xuất hiện.
2. Viết `RIGHT JOIN` để liệt kê mọi nhân viên và phòng ban nếu có. Viết lại truy vấn tương đương bằng `LEFT JOIN` và so sánh kết quả.
3. Đặt `e.is_active = 1` trong `ON`, sau đó chuyển sang `WHERE`. Ghi nhận phòng ban nào biến mất và giải thích.
4. Tìm phòng ban không có nhân viên bằng `LEFT JOIN ... IS NULL`, rồi viết lại bằng `NOT EXISTS`.
5. Tìm nhân viên không có phòng ban hợp lệ. Phân biệt employee có `department_id IS NULL` với employee có khóa mồ côi.
6. So sánh `COUNT(*)` và `COUNT(e.employee_id)` cho từng phòng ban sau `LEFT JOIN`.
7. Thêm một bảng kỹ năng có nhiều hàng cho mỗi nhân viên. Quan sát số hàng bị nhân lên khi join và sửa bằng aggregate trước khi join.
8. Thử `<=>` với các khóa NULL ở hai phía. Giải thích nguy cơ ghép chéo nếu có nhiều hàng NULL.
9. Mô phỏng `FULL OUTER JOIN` bằng `LEFT JOIN UNION ALL` và nhánh anti-join. Kiểm tra cả phòng ban không nhân viên và nhân viên không phòng ban.
10. Chạy `EXPLAIN` cho truy vấn phòng ban/nhân viên; so sánh kế hoạch khi có và không có index trên `employees.department_id` trong một bảng lab riêng.

## 17. Checklist trước khi đưa outer join vào production

- [ ] Đã xác định rõ bảng nào cần được giữ đầy đủ.
- [ ] Điều kiện `ON` phản ánh đúng quy tắc ghép giữa hai bảng.
- [ ] Điều kiện `WHERE` không vô tình loại hàng được bảo toàn.
- [ ] Đã kiểm tra cả quan hệ không khớp, khóa ngoại NULL và khóa mồ côi.
- [ ] Cột dùng để phát hiện hàng không khớp là khóa hoặc cột `NOT NULL`.
- [ ] Đã dùng `COUNT(child_pk)` khi cần đếm hàng con sau outer join.
- [ ] Đã kiểm tra cardinality một-nhiều và nguy cơ nhân bản khi join nhiều bảng con.
- [ ] Đã cân nhắc `NOT EXISTS` cho truy vấn anti-join.
- [ ] Đã xác định có thực sự cần `<=>` cho NULL-safe equality hay không.
- [ ] Kiểu dữ liệu và index trên các cột join tương thích.
- [ ] Có `ORDER BY` tường minh nếu thứ tự là một phần kết quả nghiệp vụ.
- [ ] Kế hoạch thực thi được kiểm tra bằng `EXPLAIN` trên dữ liệu đại diện.

## 18. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể chọn đúng `LEFT JOIN` hoặc `RIGHT JOIN` theo phía cần giữ, giải thích được các cột NULL được tạo ra khi không có hàng khớp, đặt điều kiện trong `ON`/`WHERE` theo đúng ngữ nghĩa, tìm được bản ghi không có quan hệ bằng anti-join, phân biệt khóa ngoại NULL với khóa mồ côi và tránh đếm sai sau outer join. Bạn cũng cần viết được truy vấn tương đương giữa RIGHT và LEFT JOIN, biết giới hạn FULL OUTER JOIN của MySQL và kiểm tra index/kế hoạch thực thi phù hợp.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — JOIN Clause](https://dev.mysql.com/doc/refman/8.4/en/join.html)
- [MySQL 8.4 Reference Manual — JOIN Optimization](https://dev.mysql.com/doc/refman/8.4/en/outer-join-optimization.html)
- [MySQL 8.4 Reference Manual — EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
