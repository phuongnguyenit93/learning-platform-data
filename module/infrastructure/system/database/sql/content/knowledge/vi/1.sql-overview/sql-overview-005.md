# SQL khai báo và sự khác biệt với xử lý tuần tự từng hàng

## 1. Cùng một bài toán, hai cách diễn đạt

Giả sử ứng dụng quản lý nhân sự cần lấy **những nhân viên đang làm việc, có lương từ 25 triệu đồng trở lên**, rồi sắp xếp theo lương giảm dần. Có hai hướng tư duy:

- **Tư duy khai báo (declarative):** mô tả tập kết quả cần nhận và các điều kiện phải thỏa mãn.
- **Tư duy xử lý tuần tự từng hàng (row-by-row, thường mang tính mệnh lệnh/procedural):** tự quy định cách duyệt từng bản ghi, kiểm tra điều kiện, thêm vào danh sách và sắp xếp.

SQL chủ yếu sử dụng tư duy thứ nhất. Với câu truy vấn:

```sql
SELECT employee_id, full_name, salary
FROM employees
WHERE active = TRUE
  AND salary >= 25000000
ORDER BY salary DESC, employee_id ASC;
```

Người viết SQL nói **cần dữ liệu gì**: lấy ba cột, chỉ giữ nhân viên còn làm việc và đạt ngưỡng lương, sau đó sắp xếp kết quả. Người viết **không chỉ định** cơ sở dữ liệu phải đọc hàng nào trước, quét bảng hay dùng chỉ mục, hoặc dùng thuật toán sắp xếp nào. Hệ quản trị cơ sở dữ liệu (DBMS) lập kế hoạch thực thi những yêu cầu đó.

Ngược lại, cách xử lý ở tầng ứng dụng có thể được mô tả bằng mã giả:

```python
# Mã giả để minh họa tư duy tuần tự; không phải mã kết nối DB hoàn chỉnh.
employees = db.query("SELECT employee_id, full_name, salary, active FROM employees")
result = []

for employee in employees:
    if employee.active and employee.salary >= 25_000_000:
        result.append({
            "employee_id": employee.employee_id,
            "full_name": employee.full_name,
            "salary": employee.salary,
        })

result.sort(key=lambda e: (-e["salary"], e["employee_id"]))
```

Mã giả trên mô tả rõ **làm như thế nào**: lấy dữ liệu, duyệt từng phần tử, kiểm tra, thêm vào mảng và sắp xếp ở ứng dụng. Nó có thể cho kết quả tương đương, nhưng phải chuyển nhiều dữ liệu hơn từ DB sang ứng dụng và bỏ qua cơ hội để DB tận dụng chỉ mục hoặc lọc từ sớm. Việc có vòng `for` không tự động là sai; khác biệt cốt lõi nằm ở nơi đặt logic xử lý và mức độ chúng ta bắt DB thực hiện một kế hoạch cụ thể.

### Dữ liệu ví dụ dùng xuyên suốt bài

Các ví dụ dưới đây dùng cú pháp SQL phổ biến, với kiểu `BOOLEAN` và giá trị `TRUE` như trong PostgreSQL. Một số hệ quản trị khác có cú pháp kiểu boolean hoặc hàm số hơi khác.

```sql
CREATE TABLE departments (
    department_id   INTEGER PRIMARY KEY,
    department_name VARCHAR(80) NOT NULL
);

CREATE TABLE employees (
    employee_id   INTEGER PRIMARY KEY,
    full_name     VARCHAR(80) NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(department_id),
    salary        DECIMAL(12, 2) NOT NULL,
    active        BOOLEAN NOT NULL
);

INSERT INTO departments (department_id, department_name) VALUES
    (10, 'Ky thuat'),
    (20, 'Kinh doanh'),
    (30, 'Ho tro');

INSERT INTO employees
    (employee_id, full_name, department_id, salary, active)
VALUES
    (101, 'An',   10, 20000000, TRUE),
    (102, 'Binh', 10, 30000000, TRUE),
    (103, 'Chi',  20, 18000000, TRUE),
    (104, 'Dung', 20, 35000000, FALSE),
    (105, 'Ha',   10, 25000000, TRUE),
    (106, 'Lan',  30, 40000000, TRUE);
```

Sau khi tạo dữ liệu, truy vấn ở đầu bài trả về:

| employee_id | full_name | salary |
| ---: | --- | ---: |
| 106 | Lan | 40000000.00 |
| 102 | Binh | 30000000.00 |
| 105 | Ha | 25000000.00 |

Nhân viên Dung dù có mức lương cao nhưng `active = FALSE`, nên bị loại. An và Chi còn làm việc nhưng chưa đạt ngưỡng lương.

## 2. Khai báo trong SQL có nghĩa là gì?

### Diễn đạt kết quả, không ra lệnh từng bước vật lý

Một câu `SELECT` thường mô tả các phép biến đổi dữ liệu ở mức logic:

| Thành phần | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| `FROM` / `JOIN` | Lấy dữ liệu từ quan hệ/bảng nào, nối theo quan hệ nào? | `FROM employees e JOIN departments d ON ...` |
| `WHERE` | Giữ những hàng nào trước khi nhóm? | `WHERE e.active = TRUE` |
| `GROUP BY` | Gom những hàng nào thành một nhóm? | `GROUP BY e.department_id` |
| `HAVING` | Giữ những nhóm nào? | `HAVING COUNT(*) >= 2` |
| `SELECT` | Trả về cột/biểu thức gì? | `SELECT department_id, AVG(salary)` |
| `ORDER BY` | Kết quả cuối cần sắp xếp ra sao? | `ORDER BY salary DESC` |

Ví dụ, để thống kê số nhân viên đang làm việc và mức lương trung bình theo phòng ban, chỉ lấy các phòng ban có ít nhất hai nhân viên đang làm việc:

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count,
    AVG(salary) AS average_salary
FROM employees
WHERE active = TRUE
GROUP BY department_id
HAVING COUNT(*) >= 2
ORDER BY department_id;
```

Với dữ liệu mẫu, kết quả là:

| department_id | employee_count | average_salary |
| ---: | ---: | ---: |
| 10 | 3 | 25000000.00 |

Không cần tự tạo các bộ đếm, mảng nhóm hay vòng lặp cộng dồn ở ứng dụng. Câu lệnh mô tả phép lọc, nhóm, đếm và trung bình để DBMS thực hiện trên các hàng phù hợp.

### Thứ tự viết câu lệnh khác thứ tự xử lý logic

Để *hiểu ý nghĩa* của một truy vấn thông thường, có thể hình dung thứ tự logic như sau:

```text
FROM / JOIN / ON
       ↓
     WHERE
       ↓
    GROUP BY
       ↓
     HAVING
       ↓
 SELECT (biểu thức kết quả)
       ↓
    DISTINCT (nếu có)
       ↓
    ORDER BY
       ↓
 LIMIT / FETCH (nếu có)
```

Đây là **mô hình suy luận về kết quả**, không phải lịch thao tác vật lý mà DBMS buộc phải thực hiện. Ngoài ra, các tính năng như hàm cửa sổ (`OVER`), tập hợp câu truy vấn (`UNION`) và từng hệ SQL có chi tiết xử lý riêng. Đặc biệt, `WHERE` lọc các hàng **trước khi** tính `GROUP BY`; `HAVING` lọc các **nhóm sau khi** tổng hợp. Vì vậy không thể dùng `AVG(salary)` trực tiếp trong `WHERE` của cùng mức truy vấn để lọc nhóm.

## 3. Ai quyết định cách thực thi SQL?

Khi nhận một câu SQL, DBMS phân tích cú pháp và ý nghĩa, tìm những cách thực thi hợp lệ, ước tính chi phí dựa trên dữ liệu/thống kê và chọn **kế hoạch thực thi (execution plan)**. Một cách nhìn khái quát:

```text
SQL khai báo
    ↓
Phân tích cú pháp và kiểm tra tên bảng/cột
    ↓
Tối ưu hóa truy vấn (query optimizer)
    ↓
Kế hoạch vật lý: quét bảng/chỉ mục, nối, lọc, nhóm, sắp xếp...
    ↓
Đọc và xử lý dữ liệu → trả kết quả
```

Chẳng hạn với điều kiện `salary >= 25000000`, hệ quản trị có thể:

- Quét bảng rồi kiểm tra điều kiện trên các hàng.
- Dùng chỉ mục phù hợp để tìm một phần dữ liệu, rồi đọc những cột còn thiếu từ bảng.
- Đổi thứ tự một số thao tác mà vẫn giữ nguyên ý nghĩa truy vấn.
- Chọn thuật toán nối bảng hoặc tổng hợp khác nhau tùy kích thước dữ liệu, chỉ mục và thống kê.

**SQL khai báo không có nghĩa DBMS không duyệt từng hàng.** Ở mức vật lý, một phép quét bảng, index scan hay nested-loop join vẫn có thể xử lý lần lượt nhiều bản ghi. Sự khác biệt là ứng dụng mô tả *đích đến*, còn bộ tối ưu được quyền chọn *đường đi* phù hợp. Kế hoạch tốt nhất không cố định: sau khi có thêm dữ liệu hoặc chỉ mục, cùng một câu SQL có thể chạy bằng kế hoạch khác.

Bạn có thể quan sát kế hoạch được chọn bằng lệnh `EXPLAIN`. Ví dụ với PostgreSQL:

```sql
EXPLAIN
SELECT employee_id, full_name, salary
FROM employees
WHERE active = TRUE
  AND salary >= 25000000
ORDER BY salary DESC, employee_id ASC;
```

`EXPLAIN` cho biết kế hoạch dự kiến, chẳng hạn quét bảng và sắp xếp. Kết quả cụ thể phụ thuộc hệ quản trị, thống kê, số hàng và chỉ mục; không nên giả định DB phải dùng index. PostgreSQL có thêm `EXPLAIN (ANALYZE, BUFFERS)` để quan sát thực thi thật, nhưng tùy chọn `ANALYZE` **chạy câu lệnh**, nên cần thận trọng khi dùng với `UPDATE`, `DELETE` hoặc dữ liệu đang hoạt động.

## 4. Khác biệt rõ nhất: cập nhật cả tập hợp hay lặp qua từng bản ghi

Giả sử cần tăng lương 5% cho **toàn bộ nhân viên đang làm việc tại phòng 10**.

### Cách từng hàng ở ứng dụng

```python
# Mã giả: lấy danh sách ID rồi gửi một lệnh UPDATE cho mỗi ID.
ids = db.query("SELECT employee_id FROM employees WHERE department_id = 10 AND active = TRUE")

for row in ids:
    db.execute(
        "UPDATE employees SET salary = salary * 1.05 WHERE employee_id = ?",
        [row.employee_id],
    )
```

Với ba nhân viên phù hợp, ví dụ này có một truy vấn lấy ID và ba lệnh `UPDATE`; với hàng nghìn nhân viên, số lượt gửi câu lệnh có thể tăng tương ứng. Trong ứng dụng thật còn cần quản lý transaction, lỗi giữa chừng và việc tập ID có thể thay đổi khi có giao dịch đồng thời.

### Cách khai báo trên tập hợp

```sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10
  AND active = TRUE;
```

Câu lệnh này diễn đạt một quy tắc cho **mọi hàng thỏa điều kiện**. DBMS tự tìm các hàng, cập nhật giá trị và áp dụng các ràng buộc liên quan. Sau cập nhật, lương của An là 21 triệu, Binh là 31,5 triệu và Ha là 26,25 triệu; những nhân viên khác không đổi.

Nếu nghiệp vụ chỉ cho phép hai chữ số thập phân, nên xác định rõ quy tắc làm tròn phù hợp và kiểu dữ liệu lưu trữ. Với cột `DECIMAL(12,2)` của ví dụ, các kết quả trên đều biểu diễn chính xác đến hai chữ số.

Một lưu ý quan trọng: **đừng quên `WHERE` khi chỉ muốn sửa một tập con**. `UPDATE employees SET salary = salary * 1.05;` sẽ áp dụng cho toàn bộ bảng. Trước các thao tác ghi, có thể dùng `SELECT` với chính điều kiện lọc để kiểm tra những hàng dự kiến tác động và chạy trong transaction thích hợp.

### Vì sao thường hiệu quả hơn?

| Khía cạnh | Nhiều lệnh xử lý từng hàng từ ứng dụng | Một câu lệnh xử lý theo tập hợp |
| --- | --- | --- |
| Giao tiếp ứng dụng–DB | Có thể phát sinh nhiều lượt gửi lệnh | Thường một lượt gửi lệnh |
| Dữ liệu truyền qua mạng | Có thể phải lấy ID/giá trị từng hàng về ứng dụng | Có thể chỉ gửi điều kiện và biểu thức cập nhật |
| Tối ưu hóa | DB chỉ nhìn thấy từng thao tác riêng lẻ | DB nhìn thấy toàn bộ yêu cầu của một câu lệnh |
| Quản lý lỗi | Cần phối hợp nhiều lần cập nhật | Có đơn vị câu lệnh rõ ràng hơn để kết hợp với transaction |
| Tính dễ đọc | Logic phân tán ở vòng lặp và các lệnh DB | Quy tắc cập nhật nằm trong một biểu thức SQL |

Đây là những lợi thế **thường gặp**, không phải cam kết rằng một câu SQL luôn nhanh hơn mọi thuật toán tuần tự. Câu SQL vẫn có thể chậm vì thiếu chỉ mục, đọc quá nhiều hàng, khóa tranh chấp, kế hoạch xấu hoặc biểu thức quá tốn kém. Đo đạc thực tế và xem execution plan mới giúp xác định nguyên nhân.

## 5. JOIN: xử lý quan hệ dữ liệu thay cho truy vấn lặp N+1

Giả sử mỗi nhân viên có `department_id`, còn tên phòng ban nằm ở bảng `departments`. Một cách viết ở ứng dụng là: lấy danh sách nhân viên, sau đó **với mỗi nhân viên** lại gửi `SELECT department_name ... WHERE department_id = ?`.

Nếu danh sách có `N` nhân viên, cách này có thể tạo ra **1 + N truy vấn** (một truy vấn lấy danh sách và N truy vấn tìm phòng ban): vấn đề thường được gọi là **N+1 queries**. Dù có nhiều nhân viên chung một phòng, ví dụ không có cache vẫn truy vấn lặp.

SQL khai báo trực tiếp mối quan hệ giữa hai bảng:

```sql
SELECT
    e.employee_id,
    e.full_name,
    d.department_name
FROM employees AS e
JOIN departments AS d
    ON d.department_id = e.department_id
WHERE e.active = TRUE
ORDER BY e.employee_id;
```

Ở đây `JOIN` chỉ rõ điều kiện ghép; DBMS quyết định thuật toán nối và có thể tận dụng chỉ mục. Một câu `JOIN` không đồng nghĩa với chỉ một lần đọc vật lý: DBMS vẫn có thể thực hiện nhiều thao tác nội bộ, nhưng ứng dụng không phải gửi một câu truy vấn cho từng nhân viên.

`JOIN` mặc định là `INNER JOIN`, nên chỉ trả những hàng có bản ghi tương ứng ở cả hai bên. Nếu muốn giữ cả nhân viên chưa có phòng ban hợp lệ, cần xem lại thiết kế khóa ngoại và cân nhắc `LEFT JOIN` theo yêu cầu nghiệp vụ.

## 6. Bài toán phức tạp vẫn có thể khai báo theo tập hợp

Yêu cầu: **tìm hai nhân viên có lương cao nhất trong mỗi phòng ban**, kể cả nhân viên không còn làm việc (vì đề bài này không yêu cầu lọc `active`). Nếu dùng thuật toán tuần tự, ứng dụng có thể tạo nhóm, sắp xếp từng nhóm rồi lấy hai phần tử đầu.

Với SQL có **hàm cửa sổ (window function)**:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        full_name,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id ASC
        ) AS position_in_department
    FROM employees
)
SELECT
    department_id,
    employee_id,
    full_name,
    salary
FROM ranked_employees
WHERE position_in_department <= 2
ORDER BY department_id, position_in_department;
```

`PARTITION BY` chia hàng thành các nhóm logic theo phòng ban; `ORDER BY` bên trong `OVER` xếp thứ tự **trong mỗi nhóm**; `ROW_NUMBER()` đánh số từng hàng theo thứ tự đó. `employee_id` đóng vai trò điều kiện phụ để khi hai người có cùng lương, thứ hạng vẫn ổn định. Câu truy vấn bên ngoài mới lọc `position_in_department <= 2`, vì kết quả hàm cửa sổ không dùng trực tiếp trong `WHERE` cùng mức truy vấn theo SQL thông dụng.

Trên dữ liệu mẫu ban đầu, kết quả là:

| department_id | employee_id | full_name | salary |
| ---: | ---: | --- | ---: |
| 10 | 102 | Binh | 30000000.00 |
| 10 | 105 | Ha | 25000000.00 |
| 20 | 104 | Dung | 35000000.00 |
| 20 | 103 | Chi | 18000000.00 |
| 30 | 106 | Lan | 40000000.00 |

Nếu bài toán là *giữ mọi người đồng hạng nhì* thay vì đúng tối đa hai người, cần xem xét `RANK()` hoặc `DENSE_RANK()` và xác định rõ quy tắc hòa hạng. SQL không tự quyết định ý nghĩa nghiệp vụ thay người viết.

## 7. Những ngộ nhận cần tránh

### “SQL khai báo” không có nghĩa là không có thứ tự

Câu `SELECT ... FROM employees` **không bảo đảm thứ tự trả về**, kể cả khi bảng có khóa chính hoặc dữ liệu thường xuất hiện theo cùng một trình tự. Chỉ `ORDER BY` ở mức truy vấn trả về cuối mới xác định thứ tự hiển thị; nếu muốn thứ tự hoàn toàn ổn định, cần bổ sung cột phá hòa khi các giá trị sắp xếp trùng nhau.

### SQL làm việc với tập hợp, nhưng kết quả có thể lặp

Tư duy **set-based** nhấn mạnh xử lý nhiều hàng bằng một biểu thức. Tuy nhiên, kết quả `SELECT` trong SQL thông thường có **bag/multiset semantics**: các hàng trùng nhau có thể xuất hiện nhiều lần. `DISTINCT` dùng để loại bản sao theo các cột được chọn. Vì vậy “theo tập hợp” trong kỹ thuật lập trình SQL không có nghĩa mọi kết quả mặc định là tập toán học không có phần tử trùng.

### `NULL` không giống `FALSE` hay số 0

SQL sử dụng logic ba giá trị `TRUE`, `FALSE`, `UNKNOWN` trong các điều kiện liên quan đến `NULL`. Ví dụ:

```sql
-- Với cột nullable: salary = NULL là sai cách kiểm tra giá trị thiếu.
SELECT employee_id
FROM employees
WHERE salary IS NULL;
```

Với bảng mẫu, `salary` được định nghĩa `NOT NULL`, nên truy vấn trên không có hàng nào. Nếu cột cho phép thiếu dữ liệu, điều kiện `salary >= 25000000` không nhận hàng có `salary IS NULL`, vì phép so sánh cho kết quả `UNKNOWN` và `WHERE` chỉ giữ các hàng có điều kiện `TRUE`. Dùng `IS NULL` / `IS NOT NULL` để kiểm tra sự thiếu vắng, đồng thời xác định nghiệp vụ có cần `COALESCE` để thay thế mặc định hay không.

### Một câu SQL không tự giải quyết mọi vấn đề transaction

Một lệnh `UPDATE` theo tập hợp là đơn vị thao tác rõ ràng, nhưng **transaction** vẫn quyết định việc nhiều câu lệnh có cùng commit/rollback hay không. Khi có giao dịch đồng thời, cần hiểu mức cách ly (isolation level), khóa và khả năng xung đột. Ví dụ thao tác “đọc lương vào ứng dụng → tính số mới → ghi trở lại” có thể gây **lost update** nếu hai tác vụ cùng dựa trên giá trị cũ và không có cơ chế bảo vệ phù hợp.

Biểu thức `SET salary = salary * 1.05` cho DB tính dựa trên giá trị hàng khi cập nhật; cách này tránh được một số rủi ro của việc tự đọc rồi ghi giá trị tuyệt đối, nhưng **không** bảo đảm loại bỏ mọi lỗi đồng thời. Những nghiệp vụ gồm nhiều bước như chuyển tiền vẫn phải dùng transaction, ràng buộc, mức cách ly và cách khóa phù hợp.

### SQL và lập trình tuần tự không loại trừ nhau

DBMS có thể thực thi thuật toán lặp ở bên trong. Một số hệ có ngôn ngữ thủ tục như PL/pgSQL, T-SQL, cursor hoặc stored procedure, cho phép vòng lặp và điều kiện. Ứng dụng cũng có thể kết hợp một `SELECT` khai báo với xử lý từng phần tử trả về. Ranh giới cần phân biệt là **cách biểu đạt yêu cầu với DBMS** và **kế hoạch xử lý do ai quyết định**, chứ không phải “SQL không bao giờ có vòng lặp”.

## 8. Khi nào chọn SQL theo tập hợp, khi nào cần xử lý tuần tự?

Ưu tiên diễn đạt bằng SQL theo tập hợp khi nghiệp vụ chủ yếu là **lọc, nối bảng, nhóm, thống kê, sắp xếp, phân hạng hoặc cập nhật hàng loạt**. Cách này thường giảm lượt trao đổi qua mạng và giúp DBMS tận dụng khả năng tối ưu.

Xử lý tuần tự có thể phù hợp khi từng phần tử cần gọi một dịch vụ bên ngoài, có công việc phụ thuộc vào kết quả của phần tử trước, hoặc thuật toán không thể biểu đạt hợp lý bằng các cấu trúc SQL sẵn có. Khi đó, có thể cân nhắc lấy dữ liệu theo lô, tránh N+1, giới hạn số hàng đưa về ứng dụng, và quản lý lỗi/transaction cẩn thận. Với xử lý khối lượng lớn, `INSERT ... SELECT`, `UPDATE ... FROM` (tùy hệ), thao tác hàng loạt/batch hoặc window function thường là các công cụ đáng xem xét.

Để đánh giá hiệu năng, nên xem **số lượt trao đổi ứng dụng–DB, lượng dữ liệu di chuyển, hàng được đọc/cập nhật, kế hoạch thực thi, chỉ mục, khóa và thời gian thực tế**. Một truy vấn SQL lớn được viết kém vẫn có thể tệ hơn phương án hợp lý khác; lựa chọn dựa trên yêu cầu và phép đo, không dựa vào khẩu hiệu “không bao giờ dùng vòng lặp”.

## 9. Tự thực hành

Các bài sau sử dụng **dữ liệu mẫu ban đầu ở mục 1**; nếu đã thực hiện `UPDATE` trong mục 4, hãy khôi phục dữ liệu ban đầu trước khi so sánh kết quả.

**Bài 1 — Lọc và sắp xếp.** Viết một câu SQL lấy `employee_id`, `full_name`, `salary` của nhân viên còn làm việc ở phòng 10, có lương ít nhất 25 triệu, xếp theo lương giảm dần. Với dữ liệu ban đầu, kết quả gồm Binh rồi Ha.

<details>
<summary>Gợi ý lời giải bài 1</summary>

```sql
SELECT employee_id, full_name, salary
FROM employees
WHERE department_id = 10
  AND active = TRUE
  AND salary >= 25000000
ORDER BY salary DESC, employee_id ASC;
```

</details>

**Bài 2 — Nhóm.** Thống kê số nhân viên đang làm việc theo từng phòng ban, kể cả phòng chỉ có một nhân viên đang làm việc. Dùng `COUNT(*)` và `GROUP BY`; kết quả lần lượt là phòng 10: 3, phòng 20: 1, phòng 30: 1.

<details>
<summary>Gợi ý lời giải bài 2</summary>

```sql
SELECT department_id, COUNT(*) AS active_count
FROM employees
WHERE active = TRUE
GROUP BY department_id
ORDER BY department_id;
```

</details>

**Bài 3 — Lý giải.** Vì sao lặp 10.000 lần `SELECT department_name ... WHERE department_id = ?` thường bất lợi so với một `JOIN` khi lấy phòng ban của 10.000 nhân viên? Trả lời bằng ba ý: số lượt gửi truy vấn, khả năng tối ưu của DBMS, và dữ liệu đi qua mạng.

**Bài 4 — Phân biệt.** Đúng hay sai: “Vì SQL khai báo nên DBMS không bao giờ phải quét tuần tự từng hàng.” Giải thích vì sao **sai**, đồng thời nêu ít nhất hai dạng thao tác vật lý DBMS có thể chọn.

## Kết luận

SQL khai báo giúp người lập trình tập trung vào **điều kiện và hình dạng kết quả**. DBMS nhận trách nhiệm tìm và thực thi một kế hoạch phù hợp; nó vẫn có thể duyệt từng hàng ở mức vật lý. Xử lý tuần tự từng hàng ở ứng dụng chỉ định nhiều bước cụ thể và có thể gây thêm truy vấn hoặc truyền dữ liệu khi bài toán vốn diễn đạt được bằng phép toán trên tập hợp. Khi gặp yêu cầu xử lý dữ liệu, hãy thử viết **một phép biến đổi trên các hàng phù hợp** trước, sau đó dùng execution plan và số đo thực tế để quyết định cách triển khai.
