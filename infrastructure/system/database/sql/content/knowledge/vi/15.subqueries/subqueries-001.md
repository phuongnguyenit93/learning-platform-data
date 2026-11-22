# Truy vấn con vô hướng và yêu cầu tối đa một hàng trong SQL

Trong SQL, một truy vấn con (*subquery*) là câu `SELECT` được đặt bên trong một câu SQL khác. Khi truy vấn con được dùng ở vị trí **cần một giá trị duy nhất**, nó được gọi là **truy vấn con vô hướng** (*scalar subquery*). Chẳng hạn, ta có thể so sánh lương nhân viên với mức lương trung bình toàn công ty, lấy tên phòng ban từ một mã hoặc đưa mã đơn hàng mới nhất của khách vào một cột kết quả.

Điểm quan trọng nhất của bài học là hợp đồng số lượng kết quả: **truy vấn con vô hướng phải tạo đúng một cột và không quá một hàng**. Một hàng cho một giá trị; không có hàng thường được biểu diễn thành SQL `NULL`; nhiều hơn một hàng thường gây lỗi ở các DBMS như PostgreSQL, MySQL, SQL Server và Oracle. SQLite có cách xử lý khác cần chú ý.

Bài học thuộc chủ đề **Truy vấn con** trong Database SQL, tập trung vào cách nhận diện vị trí vô hướng, phân biệt với truy vấn con nhiều hàng, kiểm soát tình huống 0/1/nhiều hàng, và lựa chọn giữa `UNIQUE`, hàm tổng hợp, `LIMIT 1`/`TOP 1`, `JOIN`, `IN` và `EXISTS` theo đúng nghiệp vụ.

> Các ví dụ hoàn chỉnh sử dụng **PostgreSQL**. Phần so sánh phương ngữ giới thiệu một số khác biệt đáng chú ý ở MySQL/MariaDB, SQL Server, Oracle và SQLite; cần điều chỉnh tên kiểu, cú pháp hạn chế số hàng và cơ chế xử lý lỗi cho đúng phiên bản DBMS.

## 1. Một giá trị khác một hàng và khác một tập hàng

Cùng nhìn ba dạng kết quả:

```text
Một giá trị:
    1500

Một hàng có nhiều cột:
    (employee_id = 3, salary = 1800)

Một tập có nhiều hàng:
    1000
    1200
    1200
```

Trong một vị trí vô hướng như `salary > (...)`, SQL mong biểu thức trong ngoặc là **một giá trị**, chứ không phải một tập các mức lương. Cú pháp:

```sql
SELECT (
    SELECT some_column
    FROM some_table
    WHERE ...
) AS one_value;
```

thể hiện truy vấn con được sử dụng như một biểu thức trong danh sách `SELECT`. Để phù hợp yêu cầu vô hướng, truy vấn con phải có **một cột kết quả** và **tối đa một hàng**.

Phân biệt ba trường hợp:

| Truy vấn con tạo ra | Kết quả ở vị trí vô hướng theo PostgreSQL và nhiều DBMS | Ý nghĩa |
|---|---|---|
| **1 cột × 1 hàng** | Giá trị của ô duy nhất, có thể là `NULL` | Hợp lệ |
| **1 cột × 0 hàng** | SQL `NULL` | Hợp lệ; không tìm thấy hàng |
| **1 cột × hơn 1 hàng** | Lỗi vượt số hàng | Không hợp lệ; không có một giá trị duy nhất |
| **Hơn 1 cột** | Lỗi hình dạng truy vấn con trong ngữ cảnh vô hướng thông thường | Cần chọn đúng một cột hoặc dùng cấu trúc khác |

**Ngoại lệ SQLite:** SQLite cho phép một truy vấn con vô hướng có nhiều hàng và lấy **cột đầu của hàng đầu tiên** theo thứ tự thực thi của truy vấn. Nó không báo lỗi vượt số hàng như PostgreSQL; nếu thiếu `ORDER BY` phù hợp, việc chọn “hàng đầu” không có ý nghĩa ổn định. Vì thế không dùng hành vi SQLite để suy rằng scalar subquery trong SQL nói chung tự chọn hàng đầu tiên.

### 1.1. Truy vấn con không phải phép “lấy phần tử đầu tiên”

Nhìn câu:

```sql
SELECT (
    SELECT salary
    FROM employees
) AS one_salary;
```

Nếu bảng có nhiều nhân viên, truy vấn này **không có quyền tự ý chọn một lương bất kỳ** trên PostgreSQL. Người viết SQL phải trả lời câu hỏi nghiệp vụ: đang cần **mức lương của người cụ thể**, **mức cao nhất**, **trung bình**, hay **một người đứng đầu theo tiêu chí sắp xếp**? Mỗi ý định dẫn tới câu SQL khác nhau.

Không nên sửa lỗi nhiều hàng bằng cách thêm `LIMIT 1` tùy tiện. Điều đó chỉ che việc chưa có quy tắc chọn một hàng.

## 2. Dữ liệu minh họa có thể chạy lại

Tạo hai bảng tạm cho ví dụ trong PostgreSQL:

```sql
CREATE TEMP TABLE demo_departments (
    department_id INTEGER PRIMARY KEY,
    department_name VARCHAR(80) NOT NULL UNIQUE
);

CREATE TEMP TABLE demo_employees (
    employee_id INTEGER PRIMARY KEY,
    employee_name VARCHAR(80) NOT NULL,
    department_id INTEGER
        REFERENCES demo_departments(department_id),
    salary NUMERIC(12, 2) NOT NULL
        CHECK (salary >= 0)
);

INSERT INTO demo_departments (department_id, department_name)
VALUES
    (10, 'Sales'),
    (20, 'Engineering'),
    (30, 'Support'),
    (40, 'Research');

INSERT INTO demo_employees
    (employee_id, employee_name, department_id, salary)
VALUES
    (1, 'An',    10, 1000),
    (2, 'Bình',  10, 1200),
    (3, 'Chi',   20, 1800),
    (4, 'Dũng',  20, 1500),
    (5, 'Hà',    20, 2100),
    (6, 'Lan',   30, 1300),
    (7, 'Minh', NULL,  900),
    (8, 'Nam',   10, 1200);
```

Bảng phòng ban:

| department_id | department_name |
|---:|---|
| 10 | Sales |
| 20 | Engineering |
| 30 | Support |
| 40 | Research |

Bảng nhân viên:

| employee_id | employee_name | department_id | salary |
|---:|---|---:|---:|
| 1 | An | 10 | 1000 |
| 2 | Bình | 10 | 1200 |
| 3 | Chi | 20 | 1800 |
| 4 | Dũng | 20 | 1500 |
| 5 | Hà | 20 | 2100 |
| 6 | Lan | 30 | 1300 |
| 7 | Minh | `NULL` | 900 |
| 8 | Nam | 10 | 1200 |

Phòng `Research` chưa có nhân viên. `Sales` có ba nhân viên; `Engineering` có ba; `Support` có một. Dữ liệu được chọn để thấy rõ cả trường hợp truy vấn con tạo **0, 1 và nhiều hàng**.

## 3. Trường hợp đúng: truy vấn con chỉ trả một hàng

### 3.1. Lấy thuộc tính từ khóa chính

Ví dụ lấy tên phòng ban có mã 20:

```sql
SELECT (
    SELECT department_name
    FROM demo_departments
    WHERE department_id = 20
) AS requested_department;
-- Engineering
```

`department_id` là `PRIMARY KEY` nên tại mọi thời điểm bảng ở trạng thái hợp lệ không thể có hai phòng ban cùng mã 20. Điều kiện bằng khóa chính bảo đảm **tối đa một hàng**, không chỉ do bộ dữ liệu mẫu hiện chưa trùng.

Một điều kiện bằng một cột `UNIQUE NOT NULL` cũng có thể bảo đảm tối đa một hàng, miễn là cách so sánh và phạm vi duy nhất khớp quy tắc nghiệp vụ.

### 3.2. Truy vấn con trong WHERE

Yêu cầu: “Lấy những nhân viên của phòng ban có tên Engineering”.

```sql
SELECT employee_id, employee_name, department_id
FROM demo_employees
WHERE department_id = (
    SELECT department_id
    FROM demo_departments
    WHERE department_name = 'Engineering'
)
ORDER BY employee_id;
-- 3, 4, 5
```

Bên trong, `department_name` được khai báo `UNIQUE NOT NULL` nên chỉ có tối đa một `department_id`. Truy vấn ngoài dùng giá trị đó để lọc.

Cách diễn đạt này phù hợp khi mong đợi **một phòng ban có tên duy nhất**. Nếu tên phòng ban được phép lặp theo chi nhánh, điều kiện chỉ theo tên không còn đủ; cần bổ sung phạm vi (ví dụ `tenant_id`), dùng khóa duy nhất ghép hoặc đổi cách truy vấn.

### 3.3. Không có hàng: kết quả vô hướng là NULL

```sql
SELECT (
    SELECT department_name
    FROM demo_departments
    WHERE department_id = 999
) AS missing_department;
-- NULL
```

Ở đây truy vấn con không tìm được hàng nào. Biểu thức vô hướng trả về **SQL `NULL`**; không mặc định là chuỗi rỗng, số 0 hoặc lỗi “không tìm thấy”. Nếu yêu cầu nghiệp vụ cần cảnh báo không tìm thấy, ứng dụng phải kiểm tra kết quả hoặc viết quy tắc SQL tương ứng.

So sánh qua `WHERE`:

```sql
SELECT employee_id, employee_name
FROM demo_employees
WHERE department_id = (
    SELECT department_id
    FROM demo_departments
    WHERE department_name = 'Unknown'
);
```

Truy vấn con không có hàng nên phần bên phải là `NULL`. Phép `department_id = NULL` cho kết quả logic **UNKNOWN**, không phải `TRUE`; do đó truy vấn ngoài không chọn dòng nào.

Đặc biệt, **0 hàng từ scalar subquery** không giống với “một hàng có giá trị 0”. Việc tự dùng `COALESCE(subquery, 0)` chỉ hợp lệ khi 0 là giá trị dự phòng có ý nghĩa trong nghiệp vụ.

## 4. Lỗi nhiều hàng: nguyên nhân thường gặp nhất

Bây giờ thử lấy lương của nhân viên phòng Sales:

```sql
-- PostgreSQL: lỗi vì Sales có ba nhân viên.
SELECT (
    SELECT salary
    FROM demo_employees
    WHERE department_id = 10
) AS sales_salary;
```

Truy vấn trong trả về ba dòng: `1000`, `1200` và `1200`. PostgreSQL báo lỗi đại ý:

```text
more than one row returned by a subquery used as an expression
```

Các dòng có cùng lương `1200` vẫn là **hai hàng**. Yêu cầu vô hướng không được xác định bằng “các giá trị trông có giống nhau không”, mà bằng số hàng sau khi thực hiện truy vấn con.

### 4.1. DISTINCT không tự bảo đảm một hàng

```sql
SELECT (
    SELECT DISTINCT salary
    FROM demo_employees
    WHERE department_id = 10
) AS salary;
```

Đơn Sales có hai mức lương khác nhau `1000` và `1200`. `DISTINCT` loại bản sao của `1200` nhưng vẫn còn **hai hàng**, nên truy vấn vô hướng vẫn lỗi.

Chỉ khi dữ liệu và ràng buộc thực sự bảo đảm một giá trị duy nhất trong mọi trạng thái hợp lệ, việc dùng `DISTINCT` mới có thể không vượt một hàng. Không nên dựa vào dữ liệu ngẫu nhiên hoặc tập dữ liệu thử để thay cho quy tắc nghiệp vụ.

### 4.2. ORDER BY không giải quyết yêu cầu số hàng

```sql
-- Vẫn trả nhiều hàng bên trong.
SELECT (
    SELECT salary
    FROM demo_employees
    WHERE department_id = 10
    ORDER BY salary DESC
) AS salary;
```

`ORDER BY` chỉ sắp xếp các hàng, **không làm số hàng giảm từ ba xuống một**. Nếu muốn một người đứng đầu, cần quy tắc chọn **một hàng** bằng công cụ hạn chế số hàng thích hợp và khóa phân định; nếu muốn mức lương lớn nhất, dùng `MAX`.

### 4.3. Hai cột không thể trở thành một giá trị vô hướng thông thường

```sql
-- PostgreSQL: lỗi vì truy vấn con trả hơn một cột.
SELECT (
    SELECT employee_id, employee_name
    FROM demo_employees
    WHERE employee_id = 3
) AS employee_value;
```

Dù điều kiện `employee_id = 3` chỉ trả một **hàng**, truy vấn con lại có **hai cột**, không phải một giá trị thông thường. Có thể chọn một cột hoặc dùng `JOIN` khi cần nhiều thuộc tính. Một số DBMS có khái niệm row constructor/composite type ở những ngữ cảnh riêng; không nên nhầm những cú pháp chuyên biệt ấy với scalar subquery đơn cột.

## 5. Chọn cách khắc phục theo câu hỏi nghiệp vụ

Không tồn tại một mẹo SQL duy nhất để “sửa lỗi subquery trả nhiều hàng” mà luôn giữ đúng ý nghĩa. Hãy chọn dựa trên mục đích thực tế:

| Câu hỏi thật sự | Cách viết phù hợp |
|---|---|
| “Phòng ban có mã 20 tên gì?” | Truy vấn con theo `PRIMARY KEY`/`UNIQUE` |
| “Lương **cao nhất** của Sales là bao nhiêu?” | `MAX(salary)` |
| “Lương **trung bình** của Sales là bao nhiêu?” | `AVG(salary)` |
| “**Có** nhân viên nào thuộc Sales không?” | `EXISTS` |
| “Nhân viên này có mã thuộc **tập mã** được chọn không?” | `IN (subquery)` hoặc `EXISTS` |
| “Lương nhân viên cao hơn **mọi** lương trong Sales?” | `> ALL (subquery)` nếu nghiệp vụ thật sự muốn như vậy |
| “Bản ghi **mới nhất** theo ngày, rồi ID?” | `ORDER BY ... LIMIT 1`/`TOP 1`/`FETCH FIRST` theo DBMS |
| “Lấy nhiều thuộc tính của bản ghi khớp?” | `JOIN`, `LATERAL`/`APPLY` hoặc truy vấn có cấu trúc khác |
| “Có nhiều bản ghi trùng nhưng nghiệp vụ chỉ cho một?” | Xác định khóa và áp dụng `UNIQUE`/`PRIMARY KEY`, xử lý dữ liệu trùng |

Mỗi lựa chọn trả lời một câu hỏi khác nhau. `MAX` có thể là lựa chọn đúng cho “mức lớn nhất” nhưng sai cho “lương của người đầu tiên”; `LIMIT 1` có thể chọn một hàng nhưng không thay cho khóa duy nhất của mã nghiệp vụ.

## 6. Hàm tổng hợp bảo đảm một hàng khi không GROUP BY

Một trong những cách tạo giá trị vô hướng tự nhiên nhất là dùng **hàm tổng hợp** trên toàn tập hàng được lọc, **không có `GROUP BY`**.

```sql
SELECT
    (SELECT MAX(salary)
     FROM demo_employees
     WHERE department_id = 10) AS max_sales_salary,

    (SELECT AVG(salary)
     FROM demo_employees
     WHERE department_id = 10) AS avg_sales_salary,

    (SELECT COUNT(*)
     FROM demo_employees
     WHERE department_id = 10) AS sales_employee_count;
```

Kết quả:

| max_sales_salary | avg_sales_salary | sales_employee_count |
|---:|---:|---:|
| 1200 | 1133.333... | 3 |

Với `AVG` kiểu `NUMERIC`, độ dài phần thập phân cụ thể trong hiển thị phụ thuộc DBMS và công cụ truy vấn. Điểm chính là mỗi truy vấn tổng hợp **không `GROUP BY`** chỉ tạo **một hàng**.

### 6.1. Khi không có dòng đầu vào

```sql
SELECT
    (SELECT COUNT(*)
     FROM demo_employees
     WHERE department_id = 40) AS research_count,

    (SELECT AVG(salary)
     FROM demo_employees
     WHERE department_id = 40) AS research_average,

    (SELECT MAX(salary)
     FROM demo_employees
     WHERE department_id = 40) AS research_max;
```

`Research` chưa có nhân viên. Truy vấn kết quả:

| research_count | research_average | research_max |
|---:|---|---|
| 0 | `NULL` | `NULL` |

Đây là một khác biệt tinh tế:

- `SELECT salary ... WHERE department_id = 40` **không trả hàng** và khi đặt ở vị trí vô hướng được biểu diễn thành `NULL`.
- `SELECT COUNT(*) ... WHERE department_id = 40` **trả một hàng chứa 0**.
- `SELECT AVG(salary) ...` hoặc `MAX(salary) ...` **trả một hàng chứa `NULL`** khi không có giá trị để tính.

Ở tầng ngoài, cả hai tình huống “không có hàng” và “có một hàng chứa `NULL`” có thể cùng xuất hiện dưới dạng scalar `NULL`, nhưng ý nghĩa truy vấn và khả năng kiểm tra khác nhau.

### 6.2. GROUP BY có thể phá bảo đảm một hàng

So sánh hai truy vấn:

```sql
-- Một giá trị trung bình toàn bảng.
SELECT (
    SELECT AVG(salary)
    FROM demo_employees
) AS company_avg_salary;
-- 1375

-- Có nhiều nhóm phòng ban: không hợp lệ trong ngữ cảnh vô hướng.
SELECT (
    SELECT AVG(salary)
    FROM demo_employees
    GROUP BY department_id
) AS avg_by_department;
```

Truy vấn thứ hai có nhiều nhóm (kể cả nhóm `department_id IS NULL`), nên có thể trả nhiều hàng và gây lỗi. **Không phải cứ có hàm `AVG`/`MAX`/`COUNT` là truy vấn con vô hướng an toàn**; phải xem toàn bộ `GROUP BY`, `HAVING`, `DISTINCT` và điều kiện lọc.

Nếu `GROUP BY` theo đúng một khóa đã bị ràng buộc bằng điều kiện tương quan, số nhóm có thể là 0 hoặc 1; tuy nhiên, nếu mục tiêu là tính tổng cho một khóa duy nhất, thường không cần thêm `GROUP BY` bên trong scalar subquery.

## 7. Truy vấn con không tương quan: dùng một giá trị chung

**Truy vấn con không tương quan** (*uncorrelated subquery*) không tham chiếu cột của câu SQL bên ngoài. Nó có thể tạo một ngưỡng chung cho nhiều hàng.

Ví dụ: “Lấy nhân viên có lương lớn hơn mức trung bình toàn công ty.”

```sql
SELECT employee_id, employee_name, salary
FROM demo_employees
WHERE salary > (
    SELECT AVG(salary)
    FROM demo_employees
)
ORDER BY employee_id;
```

Tổng lương trong dữ liệu mẫu là `11000` cho 8 nhân viên, nên trung bình là `1375`. Các nhân viên có lương lớn hơn trung bình là:

| employee_id | employee_name | salary |
|---:|---|---:|
| 3 | Chi | 1800 |
| 4 | Dũng | 1500 |
| 5 | Hà | 2100 |

Biểu thức `AVG(salary)` không có `GROUP BY` nên trả một giá trị duy nhất. Về mặt logic, mọi hàng bên ngoài so sánh với cùng ngưỡng `1375`.

Không nên khẳng định DBMS vật lý luôn chạy truy vấn con đúng một lần: bộ tối ưu có thể biến đổi hoặc tính toán theo kế hoạch riêng. Điều được bảo đảm là **kết quả logic** của câu truy vấn, không phải số lượt gọi vật lý cụ thể.

### 7.1. Đặt scalar subquery trong SELECT

```sql
SELECT
    employee_id,
    employee_name,
    salary,
    (SELECT AVG(salary) FROM demo_employees) AS company_avg_salary
FROM demo_employees
ORDER BY employee_id;
```

Mỗi dòng nhân viên có thêm cột trung bình toàn công ty. Không vì xuất hiện trong nhiều hàng đầu ra mà truy vấn con tạo nhiều giá trị; nó vẫn là một biểu thức vô hướng tại vị trí của từng hàng.

Nếu kết quả cần chứa nhiều thống kê chung như tổng số nhân viên, lương cao nhất, trung bình, có thể tính một lần về mặt cấu trúc truy vấn bằng CTE rồi `CROSS JOIN` kết quả tổng hợp:

```sql
WITH company_stats AS (
    SELECT
        COUNT(*) AS employee_count,
        AVG(salary) AS average_salary,
        MAX(salary) AS highest_salary
    FROM demo_employees
)
SELECT
    e.employee_id,
    e.employee_name,
    s.employee_count,
    s.average_salary,
    s.highest_salary
FROM demo_employees AS e
CROSS JOIN company_stats AS s
ORDER BY e.employee_id;
```

CTE này trả một hàng vì tổng hợp không `GROUP BY`; `CROSS JOIN` với một hàng không nhân thêm số nhân viên. Cách này giúp diễn đạt rõ việc dùng chung các chỉ tiêu, nhưng hiệu năng thực tế vẫn tùy tối ưu hóa DBMS.

## 8. Truy vấn con tương quan: giá trị phụ thuộc hàng bên ngoài

**Truy vấn con tương quan** (*correlated subquery*) tham chiếu ít nhất một giá trị từ hàng đang xử lý của truy vấn ngoài.

Ví dụ: “Với mỗi phòng ban, đếm số nhân viên và tính lương trung bình của phòng đó.”

```sql
SELECT
    d.department_id,
    d.department_name,
    (
        SELECT COUNT(*)
        FROM demo_employees AS e
        WHERE e.department_id = d.department_id
    ) AS employee_count,
    (
        SELECT AVG(e.salary)
        FROM demo_employees AS e
        WHERE e.department_id = d.department_id
    ) AS average_salary
FROM demo_departments AS d
ORDER BY d.department_id;
```

Kết quả:

| department_id | department_name | employee_count | average_salary |
|---:|---|---:|---:|
| 10 | Sales | 3 | 1133.333... |
| 20 | Engineering | 3 | 1800 |
| 30 | Support | 1 | 1300 |
| 40 | Research | 0 | `NULL` |

Ở đây `d.department_id` là cột **của truy vấn ngoài**, được tham chiếu trong điều kiện của truy vấn con. Mỗi phòng ban có một tập nhân viên tương ứng; `COUNT(*)` và `AVG(e.salary)` không `GROUP BY` nên mỗi lần tính theo khóa phòng ban đều cho một giá trị vô hướng.

### 8.1. Đọc phạm vi bí danh

```sql
SELECT d.department_name,
       (
           SELECT AVG(e.salary)
           FROM demo_employees AS e
           WHERE e.department_id = d.department_id
       ) AS dept_avg
FROM demo_departments AS d;
```

- `d`: bí danh bảng phòng ban ở **ngoài**.
- `e`: bí danh bảng nhân viên ở **trong**.
- `e.department_id = d.department_id`: điều kiện kết nối hai phạm vi.
- `AVG(e.salary)`: ép nhiều mức lương của **một phòng ban** thành một giá trị.

Nếu quên điều kiện tương quan, ví dụ chỉ viết `SELECT AVG(e.salary) FROM demo_employees e`, mọi phòng ban sẽ nhận **trung bình toàn công ty**, không phải trung bình riêng. Truy vấn vẫn chạy và có thể cho kết quả hợp lệ về cú pháp nhưng sai nghiệp vụ.

### 8.2. Lọc mỗi nhân viên theo trung bình phòng ban

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary
FROM demo_employees AS e
WHERE e.salary > (
    SELECT AVG(x.salary)
    FROM demo_employees AS x
    WHERE x.department_id = e.department_id
)
ORDER BY e.employee_id;
```

Kết quả: ID **2 (Bình)**, **5 (Hà)** và **8 (Nam)**.

- Sales có trung bình khoảng `1133.33`, nên hai nhân viên lương 1200 cao hơn.
- Engineering có trung bình 1800, nên chỉ lương 2100 lớn hơn.
- Support có một nhân viên lương bằng trung bình 1300, nên không được chọn.
- Nhân viên ID 7 có `department_id NULL`. Điều kiện `x.department_id = NULL` trong truy vấn con không khớp hàng nào, `AVG` trả `NULL`; phép `900 > NULL` là `UNKNOWN`, nên ID 7 không được chọn.

Nếu ứng dụng muốn nhân viên chưa gán phòng ban được so sánh với một mức chung, phải viết thêm **quy tắc nghiệp vụ** thay vì tự động coi `NULL` là một phòng ban bình thường.

### 8.3. Không đồng nhất “tương quan” với “chắc chắn chạy N lần”

Về cách hiểu logic, truy vấn con được xét trong ngữ cảnh của từng hàng ngoài. Nhưng bộ tối ưu có thể *decorrelate* (biến đổi thành phép JOIN/tổng hợp), ghi nhớ kết quả cho các khóa lặp hoặc áp dụng cách thực thi khác. Không đoán độ phức tạp chỉ bằng việc thấy cú pháp tương quan; hãy dùng `EXPLAIN` trên DBMS và dữ liệu thực tế.

## 9. Khi nào dùng IN, EXISTS, ANY/ALL thay vì scalar subquery?

Một lỗi phổ biến là viết `= (SELECT ...)` trong khi câu hỏi thật sự liên quan đến **một tập giá trị**.

### 9.1. `IN`: một giá trị có thuộc tập kết quả không?

Yêu cầu: “Lấy nhân viên thuộc **những phòng ban có tên Sales hoặc Support**.”

```sql
-- Không phù hợp: truy vấn con có hai phòng ban.
SELECT employee_id
FROM demo_employees
WHERE department_id = (
    SELECT department_id
    FROM demo_departments
    WHERE department_name IN ('Sales', 'Support')
);
```

Phải dùng toán tử tập hợp:

```sql
SELECT employee_id, employee_name, department_id
FROM demo_employees
WHERE department_id IN (
    SELECT department_id
    FROM demo_departments
    WHERE department_name IN ('Sales', 'Support')
)
ORDER BY employee_id;
-- 1, 2, 6, 8
```

`IN` nhận một tập giá trị có thể nhiều hàng; không có yêu cầu vô hướng “tối đa một hàng” ở vế phải. Vế phải phải phù hợp số cột của phép so sánh (ở đây là một cột `department_id`).

### 9.2. `EXISTS`: có ít nhất một hàng thỏa không?

Yêu cầu: “Liệt kê các phòng ban có nhân viên.”

```sql
SELECT d.department_id, d.department_name
FROM demo_departments AS d
WHERE EXISTS (
    SELECT 1
    FROM demo_employees AS e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
-- 10, 20, 30
```

`EXISTS` hỏi truy vấn con có **ít nhất một hàng** hay không. Nó không cần một giá trị duy nhất và không quan tâm biểu thức `SELECT 1` có ý nghĩa số học gì. `EXISTS` cũng hoạt động đúng khi có hàng chứa `NULL` ở các cột được chọn, vì việc có hàng mới là điều kiện quyết định.

Nếu câu hỏi là “không có nhân viên”, dùng `NOT EXISTS`:

```sql
SELECT d.department_id, d.department_name
FROM demo_departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_employees AS e
    WHERE e.department_id = d.department_id
);
-- 40, Research
```

### 9.3. `ANY` và `ALL`: so sánh với nhiều giá trị

Yêu cầu: “Lương nhân viên lớn hơn **mọi mức lương thuộc phòng Sales**.”

```sql
SELECT employee_id, employee_name, salary
FROM demo_employees
WHERE salary > ALL (
    SELECT salary
    FROM demo_employees
    WHERE department_id = 10
)
ORDER BY employee_id;
-- 3, 4, 5, 6
```

Mức cao nhất trong Sales là 1200; các nhân viên lương trên 1200 (ID 3, 4, 5, 6) đều thỏa. Vì dữ liệu mẫu `salary NOT NULL` và Sales có hàng, biểu thức `> ALL` ở đây tương đương về kết quả với so sánh lớn hơn `MAX(salary)` của Sales.

Nhưng `ALL` có **ngữ nghĩa tập rỗng và `NULL`** riêng: so sánh với tập rỗng thường cho `TRUE` theo logic lượng từ, trong khi `> (SELECT MAX(...) ... trên tập rỗng)` so với `NULL` cho `UNKNOWN`. Không thay hai kiểu viết cho nhau khi chưa xem dữ liệu rỗng và giá trị thiếu.

`> ANY (subquery)` có nghĩa lớn hơn **ít nhất một** giá trị của tập, không phải lớn hơn tất cả. Các toán tử này không phải scalar subquery: chúng được thiết kế để xử lý tập nhiều hàng.

### 9.4. Số lượng hàng không phải điều kiện tồn tại duy nhất

Có thể viết:

```sql
WHERE (
    SELECT COUNT(*)
    FROM demo_employees AS e
    WHERE e.department_id = d.department_id
) > 0
```

để kiểm tra phòng ban có nhân viên, nhưng `EXISTS` thường diễn đạt ý định trực tiếp hơn và có thể giúp optimizer dừng tìm khi đã phát hiện một hàng. Không nên chuyển tất cả bài toán “có hay không” thành scalar `COUNT` nếu không thực sự cần đếm.

## 10. Khi muốn một hàng mới nhất: phải xác định thứ tự

Một trường hợp hay gặp là “lấy **đơn mới nhất của mỗi khách hàng**”. Đây là bài toán chọn một hàng có thứ tự, không phải lấy một giá trị tùy ý.

Tạo dữ liệu độc lập:

```sql
CREATE TEMP TABLE demo_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TEMP TABLE demo_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES demo_customers(customer_id),
    created_at TIMESTAMP NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL
);

INSERT INTO demo_customers (customer_id, customer_name)
VALUES (101, 'An'), (102, 'Bình'), (103, 'Chi');

INSERT INTO demo_orders
    (order_id, customer_id, created_at, total_amount)
VALUES
    (5001, 101, TIMESTAMP '2026-11-10 09:00:00', 400),
    (5002, 101, TIMESTAMP '2026-11-12 11:00:00', 600),
    (5003, 102, TIMESTAMP '2026-11-11 12:00:00', 300),
    (5004, 102, TIMESTAMP '2026-11-11 12:00:00', 700);
```

Khách 101 có đơn mới nhất 5002. Khách 102 có **hai đơn cùng timestamp** nên cần một tiêu chí phụ để phân định. Khách 103 chưa có đơn.

### 10.1. PostgreSQL/MySQL/SQLite: `ORDER BY ... LIMIT 1`

```sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT o.order_id
        FROM demo_orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 1
    ) AS latest_order_id
FROM demo_customers AS c
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name | latest_order_id |
|---:|---|---:|
| 101 | An | 5002 |
| 102 | Bình | 5004 |
| 103 | Chi | `NULL` |

Ở đây `LIMIT 1` bảo đảm truy vấn con không trả quá một hàng; `ORDER BY created_at DESC, order_id DESC` diễn đạt **đơn có timestamp mới nhất**, và nếu bằng nhau, chọn ID lớn hơn. Nếu chỉ viết `LIMIT 1` mà không có `ORDER BY`, “mới nhất” không được bảo đảm.

**Thứ tự có ý nghĩa:** nếu `created_at` có thể `NULL`, phải xác định vị trí `NULL` theo DBMS và quy tắc nghiệp vụ, ví dụ PostgreSQL `ORDER BY created_at DESC NULLS LAST, order_id DESC`. Trong dữ liệu mẫu, `created_at NOT NULL` để tập trung vào câu hỏi số hàng.

### 10.2. `MAX(created_at)` có thay cho một hàng mới nhất không?

```sql
SELECT
    c.customer_id,
    (
        SELECT MAX(o.created_at)
        FROM demo_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS latest_time
FROM demo_customers AS c;
```

Truy vấn này lấy **thời gian gần nhất**, không chọn được `order_id` một cách duy nhất khi có hai đơn cùng thời điểm như khách 102. Nếu cần đúng một đơn hàng, phải có quy tắc phân định (ví dụ `order_id DESC`) và cách chọn đúng hàng.

Không viết `SELECT MAX(created_at), order_id ...` rồi coi chúng luôn đến từ cùng hàng mà không có quy tắc nhóm/truy vấn phù hợp. Một chỉ tiêu tổng hợp và một thuộc tính của hàng cần được liên kết đúng về mặt logic.

### 10.3. Dùng `LEFT JOIN LATERAL` khi cần nhiều cột của cùng hàng

Scalar subquery thường trả **một cột**. Nếu muốn cả ID, thời gian và số tiền của đơn mới nhất, việc lặp ba scalar subquery có thể làm SQL dài và khó duy trì. PostgreSQL hỗ trợ `LATERAL`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id AS latest_order_id,
    recent.created_at AS latest_order_time,
    recent.total_amount AS latest_order_amount
FROM demo_customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.created_at,
        o.total_amount
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE
ORDER BY c.customer_id;
```

`LATERAL` cho phép truy vấn con trong `FROM` tham chiếu cột của `c`; `LEFT JOIN` giữ khách không có đơn. Phương thức này trả nhiều cột nhưng vẫn chỉ một hàng đơn mới nhất cho mỗi khách nhờ `LIMIT 1`.

Trên SQL Server, ý tưởng tương ứng thường dùng `OUTER APPLY` và `TOP (1)`. Nếu cần **tất cả đơn đồng hạng** thay vì ép chọn một, không dùng hạn chế một hàng; có thể cân nhắc `RANK`/`DENSE_RANK` hoặc điều kiện theo timestamp lớn nhất.

## 11. Cú pháp giới hạn một hàng giữa các DBMS

| DBMS | Cú pháp thường dùng khi cần một hàng có thứ tự | Lưu ý |
|---|---|---|
| PostgreSQL | `ORDER BY ... LIMIT 1`; cũng hỗ trợ `FETCH FIRST 1 ROW ONLY` | Chọn tiêu chí phân định khi giá trị sort bằng nhau |
| MySQL / MariaDB | `ORDER BY ... LIMIT 1` | Không dựa vào thứ tự vật lý của bảng |
| SQLite | `ORDER BY ... LIMIT 1` | Scalar subquery nhiều hàng có hành vi riêng: lấy hàng đầu thay vì báo lỗi |
| SQL Server | `SELECT TOP (1) ... ORDER BY ...` | `TOP (1)` đặt sau `SELECT` trong T-SQL |
| Oracle Database | `ORDER BY ... FETCH FIRST 1 ROW ONLY` ở các phiên bản hỗ trợ | Các phiên bản cũ có cách dùng `ROWNUM`; cần sắp trước khi cắt số hàng |

Ví dụ ý tưởng lấy `order_id` của đơn mới nhất theo khách:

**PostgreSQL / MySQL / MariaDB / SQLite**:

```sql
SELECT (
    SELECT order_id
    FROM orders
    WHERE customer_id = 101
    ORDER BY created_at DESC, order_id DESC
    LIMIT 1
) AS latest_order_id;
```

**SQL Server**:

```sql
SELECT (
    SELECT TOP (1) order_id
    FROM dbo.orders
    WHERE customer_id = 101
    ORDER BY created_at DESC, order_id DESC
) AS latest_order_id;
```

**Oracle Database** (phiên bản hỗ trợ `FETCH FIRST`):

```sql
SELECT (
    SELECT order_id
    FROM orders
    WHERE customer_id = 101
    ORDER BY created_at DESC, order_id DESC
    FETCH FIRST 1 ROW ONLY
) AS latest_order_id
FROM dual;
```

Các ví dụ giả định tồn tại bảng `orders` với các cột phù hợp. Chúng minh họa **phương ngữ chọn một hàng**, không phải yêu cầu tạo các bảng giống hoàn toàn trên mọi hệ.

### 11.1. Vì sao `LIMIT 1` không luôn là giải pháp tốt?

Nếu truy vấn dự kiến phải tìm đúng **một bản ghi theo mã nghiệp vụ duy nhất**, thêm `LIMIT 1` chỉ giải quyết triệu chứng. Giả sử hai tài khoản cùng `employee_code` do thiếu `UNIQUE`, `LIMIT 1` sẽ âm thầm chọn một tài khoản. Hệ thống có thể trả sai danh tính, nhầm quyền truy cập hoặc tính toán dựa trên dữ liệu không nhất quán.

Giải pháp đúng là xác định quy tắc duy nhất, xử lý dữ liệu trùng và thêm ràng buộc `UNIQUE` phù hợp, không phải cố định một hàng tình cờ. `LIMIT 1` phù hợp cho **chọn đầu bảng xếp hạng/mới nhất** khi nhiều hàng là hợp lệ và quy tắc chọn đã được định nghĩa.

## 12. Scalar subquery và NULL: ba câu hỏi khác nhau

Hãy phân biệt:

1. **Không tìm thấy hàng:** scalar subquery cho `NULL`.
2. **Tìm một hàng nhưng cột chọn là `NULL`:** scalar subquery cũng cho `NULL`.
3. **Tìm nhiều hàng:** nhiều DBMS báo lỗi; không trở thành `NULL`.

Từ góc nhìn giá trị đầu ra, hai trường hợp đầu cùng là `NULL` nhưng nghiệp vụ có thể rất khác.

Ví dụ:

```sql
-- Không có phòng ban 999: không tìm thấy hàng.
SELECT (
    SELECT department_name
    FROM demo_departments
    WHERE department_id = 999
);

-- Phòng ban Research tồn tại nhưng chưa có lương để tính:
SELECT (
    SELECT AVG(salary)
    FROM demo_employees
    WHERE department_id = 40
);
```

Cả hai trả `NULL` dưới dạng scalar, nhưng lý do là khác nhau. Nếu cần phân biệt, có thể bổ sung chỉ tiêu tồn tại/đếm hàng:

```sql
SELECT
    d.department_id,
    d.department_name,
    (SELECT COUNT(*)
     FROM demo_employees e
     WHERE e.department_id = d.department_id) AS employee_count,
    (SELECT AVG(e.salary)
     FROM demo_employees e
     WHERE e.department_id = d.department_id) AS average_salary
FROM demo_departments d
WHERE d.department_id = 40;
```

Bản ghi trả về `Research` có `employee_count = 0` và `average_salary = NULL`. Không cần biến trung bình thiếu dữ liệu thành số 0, vì “chưa có nhân viên” không có một mức lương trung bình xác định.

### 12.1. COALESCE cho giá trị dự phòng

```sql
SELECT
    d.department_id,
    COALESCE(
        (
            SELECT AVG(e.salary)
            FROM demo_employees e
            WHERE e.department_id = d.department_id
        ),
        0
    ) AS average_salary_or_zero
FROM demo_departments d;
```

`COALESCE` thay `NULL` bằng 0 trong kết quả. Điều này có thể hữu ích khi hiển thị biểu đồ bắt buộc có số, nhưng phải hiểu rằng 0 là **quy ước đầu ra**, không phải trung bình thực tế của một phòng ban rỗng.

Nếu cần phân biệt có/không dữ liệu, nên trả cả `employee_count` hoặc cờ trạng thái thay vì xóa dấu hiệu thiếu dữ liệu.

### 12.2. Dùng `IS NULL` thay vì `= NULL`

```sql
-- Sai ý nghĩa: NULL = NULL là UNKNOWN.
WHERE (SELECT AVG(salary)
       FROM demo_employees
       WHERE department_id = 40) = NULL

-- Đúng khi muốn kiểm tra giá trị kết quả thiếu.
WHERE (SELECT AVG(salary)
       FROM demo_employees
       WHERE department_id = 40) IS NULL
```

Tuy nhiên, nếu câu hỏi là **“không có nhân viên”**, `NOT EXISTS` hoặc `COUNT(*) = 0` thường phản ánh ý định trực tiếp hơn việc kiểm tra `AVG(...) IS NULL`, nhất là khi cột lương có thể `NULL`.

## 13. Scalar subquery trong UPDATE và INSERT

Truy vấn con vô hướng không chỉ xuất hiện trong `SELECT` và `WHERE`. Nó còn có thể cung cấp giá trị cập nhật/chèn. Hợp đồng **một cột, tối đa một hàng** vẫn quan trọng.

### 13.1. UPDATE giá trị theo số liệu tổng hợp

Giả sử có bảng lưu chỉ tiêu tổng hợp cho các phòng ban:

```sql
CREATE TEMP TABLE demo_department_metrics (
    department_id INTEGER PRIMARY KEY
        REFERENCES demo_departments(department_id),
    average_salary NUMERIC(12, 2)
);

INSERT INTO demo_department_metrics (department_id)
SELECT department_id
FROM demo_departments;

UPDATE demo_department_metrics AS m
SET average_salary = (
    SELECT AVG(e.salary)
    FROM demo_employees AS e
    WHERE e.department_id = m.department_id
);
```

Mỗi dòng `m` được gán một giá trị trung bình tương ứng. Phòng Research chưa có nhân viên nên `average_salary` nhận `NULL`. Trường này phải cho phép `NULL`, như định nghĩa bảng, nếu muốn lưu trạng thái chưa có dữ liệu.

Nếu thay truy vấn con bằng `SELECT e.salary FROM demo_employees e WHERE ...`, các phòng ban có nhiều nhân viên sẽ gây lỗi trong PostgreSQL vì có nhiều hàng. Việc đưa scalar subquery vào `UPDATE` **không bỏ qua quy tắc cardinality**.

### 13.2. INSERT với kết quả truy vấn con

```sql
-- Ví dụ giả sử bảng department_labels có cột name và dept_id.
INSERT INTO department_labels (dept_id, name)
VALUES (
    20,
    (
        SELECT department_name
        FROM demo_departments
        WHERE department_id = 20
    )
);
```

Truy vấn con theo PK trả `Engineering`. Tuy nhiên, SQL này giả định bảng `department_labels` đã tồn tại. Nếu không tìm thấy phòng ban, scalar trả `NULL`; cột đích `NOT NULL` sẽ khiến thao tác bị từ chối. Nếu không thể chấp nhận bản ghi thiếu phòng ban, phải xác định cách xử lý thay vì chỉ dựa vào giá trị mặc định.

Trong một số trường hợp, `INSERT ... SELECT ...` phù hợp hơn `INSERT ... VALUES (subquery)`, đặc biệt khi muốn chỉ chèn **nếu** có hàng nguồn:

```sql
-- Cùng giả định department_labels tồn tại.
INSERT INTO department_labels (dept_id, name)
SELECT department_id, department_name
FROM demo_departments
WHERE department_id = 20;
```

Nếu không có hàng nguồn, dạng `INSERT ... SELECT` không chèn hàng nào; khác với `VALUES (..., scalar_subquery)` có thể cố chèn một hàng với `NULL`.

## 14. Truy vấn con vô hướng và JOIN: cùng mục đích, khác hình dạng

Nhiều truy vấn con vô hướng có thể viết lại dưới dạng `JOIN` khi dữ liệu liên kết đúng một bản ghi.

Ví dụ tên phòng ban cho từng nhân viên:

**Scalar subquery:**

```sql
SELECT
    e.employee_id,
    e.employee_name,
    (
        SELECT d.department_name
        FROM demo_departments AS d
        WHERE d.department_id = e.department_id
    ) AS department_name
FROM demo_employees AS e
ORDER BY e.employee_id;
```

**LEFT JOIN:**

```sql
SELECT
    e.employee_id,
    e.employee_name,
    d.department_name
FROM demo_employees AS e
LEFT JOIN demo_departments AS d
    ON d.department_id = e.department_id
ORDER BY e.employee_id;
```

Cả hai trả tên phòng ban cho nhân viên có mã phòng ban hợp lệ và trả `NULL` cho nhân viên ID 7 chưa được gán phòng ban. `LEFT JOIN` giữ lại hàng ngoài; nếu dùng `INNER JOIN`, nhân viên chưa có phòng ban sẽ bị loại.

### 14.1. JOIN có thể nhân số hàng nếu khóa không duy nhất

Giả sử nối tới bảng dữ liệu phụ không có khóa duy nhất. Một `LEFT JOIN` có thể tạo **nhiều hàng** ngoài cho một hàng gốc; scalar subquery tương ứng trên PostgreSQL sẽ **báo lỗi** nếu trả nhiều hàng. Đây là khác biệt quan trọng:

- Scalar subquery ở ngữ cảnh đơn trị nêu rõ kỳ vọng **không quá một kết quả**.
- JOIN đưa tất cả các cặp khớp vào kết quả, nên có thể **nhân dòng** khi một hàng cha khớp nhiều dòng con.

Không đổi scalar subquery sang JOIN một cách máy móc mà chưa xét cardinality và yêu cầu một dòng một thực thể.

### 14.2. Tránh lặp nhiều scalar subquery cho cùng dữ liệu

Nếu cần tên, địa điểm và quản lý phòng ban từ cùng hàng `departments`, một `JOIN` có thể rõ và hiệu quả hơn ba scalar subquery gần như giống hệt nhau. Nếu nguồn có thể nhiều hàng và muốn lấy một hàng theo thứ tự, cân nhắc `LATERAL`/`APPLY` hoặc window function như `ROW_NUMBER()`.

Không có quy tắc rằng JOIN luôn nhanh hơn scalar subquery; bộ tối ưu có thể chuyển đổi hình thức, và nhu cầu trả một hay nhiều hàng khác nhau. Điều quan trọng trước hết là **đúng ngữ nghĩa và không vô tình nhân bản kết quả**.

## 15. Ràng buộc UNIQUE là bảo đảm thiết kế, không chỉ là mẹo truy vấn

Một truy vấn con theo khóa được bảo vệ `UNIQUE`/`PRIMARY KEY` có bảo đảm tối đa một hàng mạnh hơn việc “chạy thử thấy một hàng”. Cần xác định phạm vi khóa.

Ví dụ trong hệ thống đa tổ chức, cùng một mã nhân viên có thể xuất hiện ở nhiều tenant:

```sql
CREATE TABLE tenant_staff (
    staff_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    employee_code VARCHAR(30) NOT NULL,
    full_name TEXT NOT NULL,
    CONSTRAINT uq_tenant_employee_code
        UNIQUE (tenant_id, employee_code)
);
```

Truy vấn:

```sql
SELECT (
    SELECT staff_id
    FROM tenant_staff
    WHERE employee_code = 'E001'
);
```

**không được bảo đảm vô hướng**, vì các tenant khác nhau có thể cùng `E001`. Cần đưa **đủ khóa ghép**:

```sql
SELECT (
    SELECT staff_id
    FROM tenant_staff
    WHERE tenant_id = 10
      AND employee_code = 'E001'
) AS staff_id;
```

Khi cả `tenant_id` và `employee_code` được xác định, ràng buộc duy nhất ghép bảo đảm tối đa một hàng. Nếu không có dòng phù hợp, scalar trả `NULL`.

### 15.1. Cẩn trọng với UNIQUE và NULL

Trong nhiều DBMS, `UNIQUE` có thể cho phép nhiều `NULL`. Vì thế một cột `UNIQUE` nhưng vẫn cho phép `NULL` không tự bảo đảm một định danh bắt buộc theo yêu cầu nghiệp vụ. Với điều kiện so sánh `col = :value` khi `:value` là `NULL`, SQL còn có logic ba giá trị dẫn tới không khớp thông thường.

Nếu cần một khóa ứng viên nghiệp vụ luôn xác định, hãy cân nhắc `NOT NULL` kết hợp `UNIQUE`; đồng thời lưu ý sự khác biệt về `NULL`, collation và khoảng trắng giữa các DBMS.

### 15.2. Đừng giấu dữ liệu trùng bằng MIN/MAX hoặc LIMIT nếu nó là lỗi

Giả sử email tài khoản phải duy nhất nhưng dữ liệu đang có hai tài khoản cùng email. Thêm:

```sql
-- Có thể trả một ID nhưng che vấn đề trùng nghiệp vụ.
SELECT MIN(account_id)
FROM accounts
WHERE email = 'user@example.test';
```

hoặc:

```sql
SELECT account_id
FROM accounts
WHERE email = 'user@example.test'
ORDER BY account_id
LIMIT 1;
```

không chứng minh hai tài khoản là một thực thể. Với nghiệp vụ đăng nhập/phân quyền, đây có thể là lỗi nghiêm trọng. Cần phát hiện dữ liệu trùng, xử lý rồi ràng buộc duy nhất, thay vì chọn tùy ý một bản ghi.

## 16. Hiệu năng: hiểu kế hoạch truy vấn và chỉ mục

### 16.1. Truy vấn con theo khóa ngoại hoặc khóa chính

```sql
SELECT
    e.employee_id,
    (
        SELECT d.department_name
        FROM demo_departments AS d
        WHERE d.department_id = e.department_id
    ) AS department_name
FROM demo_employees AS e;
```

Nếu `demo_departments.department_id` là PK, DBMS thường có chỉ mục phù hợp để tra một hàng cha. Với bảng nhỏ, bộ tối ưu có thể dùng cách khác như quét bảng; không có bảo đảm “mỗi hàng ngoài bắt buộc sẽ thực hiện một lần truy vấn chỉ mục”.

### 16.2. Tương quan nhiều hàng và tập dữ liệu lớn

Một scalar subquery tương quan tính `AVG(salary)` cho từng nhân viên có thể đắt hơn một truy vấn đã tổng hợp theo phòng ban nếu DBMS không tối ưu tốt. Có thể viết lại:

```sql
WITH dept_average AS (
    SELECT department_id, AVG(salary) AS avg_salary
    FROM demo_employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
)
SELECT
    e.employee_id,
    e.employee_name,
    e.salary
FROM demo_employees AS e
JOIN dept_average AS d
  ON d.department_id = e.department_id
WHERE e.salary > d.avg_salary
ORDER BY e.employee_id;
```

Truy vấn này cho cùng ID **2, 5, 8** như ví dụ tương quan ở phần 8 khi áp dụng trên bảng mẫu. Việc tổng hợp theo phòng ban được diễn đạt tường minh. Tuy nhiên, trên một hệ thống cụ thể, scalar subquery cũng có thể được optimizer biến đổi thành kế hoạch tương tự.

### 16.3. Chỉ mục cho “hàng mới nhất”

Với truy vấn:

```sql
SELECT o.order_id
FROM demo_orders AS o
WHERE o.customer_id = 101
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 1;
```

trong PostgreSQL, có thể cân nhắc chỉ mục ghép:

```sql
CREATE INDEX idx_demo_orders_customer_recent
ON demo_orders (customer_id, created_at DESC, order_id DESC);
```

Chỉ mục có thể giúp tìm các đơn của khách theo thứ tự mới nhất, đặc biệt khi mỗi khách có nhiều đơn. Cần xem chỉ mục hiện tại, độ lớn bảng, tần suất cập nhật và kế hoạch `EXPLAIN` trước khi thêm.

### 16.4. Đo thay vì suy đoán

Trên PostgreSQL, có thể dùng:

```sql
EXPLAIN
SELECT e.employee_id, e.employee_name
FROM demo_employees AS e
WHERE e.salary > (
    SELECT AVG(x.salary)
    FROM demo_employees AS x
    WHERE x.department_id = e.department_id
);
```

`EXPLAIN` cho biết kế hoạch dự kiến của DBMS. `EXPLAIN ANALYZE` thực thi truy vấn để đo thực tế, nên cần cân nhắc trên môi trường có dữ liệu nhạy cảm/tải cao hoặc với câu `UPDATE`/`DELETE`. Dù câu lệnh tương quan có vẻ lặp, hãy dựa vào kế hoạch thực tế thay vì quy tắc “subquery luôn chậm”.

## 17. Khác biệt theo hệ quản trị khi truy vấn con nhiều hàng

| DBMS | 0 hàng trong scalar subquery | > 1 hàng trong scalar subquery | Ghi chú |
|---|---|---|---|
| **PostgreSQL** | `NULL` | Báo lỗi | Lỗi thường gặp: *more than one row returned by a subquery used as an expression* |
| **MySQL / MariaDB** | `NULL` | Báo lỗi | Thông báo phổ biến: *Subquery returns more than 1 row* |
| **SQL Server** | `NULL` | Báo lỗi | Thông báo kiểu *Subquery returned more than 1 value* |
| **Oracle Database** | `NULL` | Báo lỗi | ORA-01427: *single-row subquery returns more than one row* |
| **SQLite** | `NULL` | Không báo lỗi cardinality; lấy hàng đầu tiên | Nếu không có thứ tự xác định thì giá trị được lấy có thể khó dự đoán |

Vì SQLite cho phép dùng hàng đầu tiên, một truy vấn “có vẻ chạy tốt” trên SQLite có thể thất bại khi chuyển sang PostgreSQL hoặc Oracle. Cách viết an toàn cho ứng dụng đa DBMS vẫn là **bảo đảm đúng một cột và tối đa một hàng bằng logic truy vấn hoặc ràng buộc dữ liệu**.

Ngay cả trên SQLite, phải có quy tắc `ORDER BY` và giới hạn một hàng rõ ràng nếu ý định là “chọn đầu bảng xếp hạng”; nhưng **không dùng nó để che quy tắc định danh phải duy nhất**.

### 17.1. Lỗi xảy ra ở thời điểm thực thi

Một scalar subquery có cấu trúc cú pháp hợp lệ nhưng kết quả nhiều hàng **chỉ bị phát hiện khi câu lệnh thực thi với dữ liệu tạo ra nhiều hàng** trên những DBMS kiểm tra cardinality. Vì vậy có trường hợp:

- Trên dữ liệu thử chỉ có một hàng nên truy vấn chạy.
- Khi nhập thêm bản ghi hợp lệ theo schema hiện tại, truy vấn bắt đầu lỗi.
- Nếu không có ràng buộc duy nhất, lỗi có thể xuất hiện sau nhiều tháng vận hành.

Với yêu cầu “không quá một hàng”, nên xây chứng cứ từ **khóa**, **hàm tổng hợp** hoặc **tiêu chí chọn có thứ tự** thay vì chỉ trông đợi dữ liệu hiện tại.

### 17.2. Viết xử lý lỗi ở ứng dụng

Ứng dụng Java/JDBC nên phân biệt:

- **Không tìm thấy hàng ở truy vấn con vô hướng:** SQL có thể trả `NULL` trong ô kết quả; không có ngoại lệ “no row” riêng cho truy vấn con ấy.
- **Nhiều hàng ở nơi không được phép:** DBMS có thể ném lỗi SQL; ứng dụng nên ghi nhận thông báo và xử lý theo chính sách, không tự động thử lại bằng `LIMIT 1`.
- **Truy vấn ngoài không trả hàng:** đây lại là một tình huống khác, ví dụ `SELECT ... WHERE condition` không khớp dòng nào.

Nếu dùng ORM, việc ánh xạ `NULL` sang kiểu tham chiếu hoặc kiểu tùy chọn cần được xác định; không ép một giá trị có thể `NULL` vào primitive Java mà không có chính sách phù hợp.

## 18. Các lỗi thiết kế hay gặp

| Sai lầm | Vì sao xảy ra vấn đề | Cách xử lý |
|---|---|---|
| Dùng `= (SELECT ...)` cho tập nhiều ID | Truy vấn con nhiều hàng không vô hướng | Dùng `IN` hoặc `EXISTS` |
| Cho rằng chỉ cần `SELECT DISTINCT` là đủ một hàng | Có thể còn nhiều giá trị khác nhau | Chứng minh ràng buộc duy nhất hoặc đổi bài toán |
| Chỉ thêm `ORDER BY` trong scalar subquery nhiều hàng | Sắp xếp không giảm số dòng | Chọn aggregate hoặc giới hạn một hàng có tiêu chí |
| Thêm `LIMIT 1` không có `ORDER BY` | Giá trị được chọn không ổn định | Xác định tiêu chí chọn và khóa phân định |
| Dùng `LIMIT 1` để né dữ liệu trùng mã nghiệp vụ | Che vi phạm tính duy nhất | Sửa dữ liệu, áp `UNIQUE` đúng phạm vi |
| Nghĩ `COUNT(*)` tập rỗng trả `NULL` | Đếm sai/hiểu nhầm không có dữ liệu | `COUNT(*)` không `GROUP BY` trả 0 |
| Nghĩ `AVG` có `GROUP BY` chắc chắn một hàng | Có thể có nhiều nhóm | Giới hạn nhóm hoặc bỏ `GROUP BY` nếu thích hợp |
| So sánh `= NULL` sau scalar không có hàng | Biểu thức cho `UNKNOWN` | Dùng `IS NULL` khi muốn kiểm tra giá trị thiếu |
| Quên điều kiện tương quan | Lấy chỉ tiêu toàn bảng cho từng nhóm | Nối rõ cột ngoài và trong bằng alias |
| Tham chiếu thiếu thành phần khóa ghép | Có thể khớp nhiều tenant/chi nhánh | Dùng đủ các cột của khóa nghiệp vụ |
| Dùng scalar subquery để trả nhiều thuộc tính | Hình dạng một giá trị không phù hợp | Dùng `JOIN`/`LATERAL`/`APPLY` |
| Chuyển scalar thành JOIN nhưng quên quan hệ một-nhiều | Nhân dòng kết quả | Kiểm tra cardinality và chọn cấu trúc đúng |
| Cho rằng SQLite sẽ báo lỗi như PostgreSQL | SQLite có thể âm thầm lấy hàng đầu | Thiết kế truy vấn đúng cardinality không phụ thuộc DBMS |
| Dựa vào scalar subquery để đo thời gian thực thi | Có thể bị optimizer biến đổi | Xem `EXPLAIN` và đo trên dữ liệu đại diện |

## 19. Bài tập thực hành kèm giải thích

### Bài 1. Một hàng theo khóa chính

**Yêu cầu:** viết scalar subquery lấy tên phòng ban có `department_id = 30`.

**Đáp án:**

```sql
SELECT (
    SELECT department_name
    FROM demo_departments
    WHERE department_id = 30
) AS department_name;
-- Support
```

`department_id` là khóa chính nên tối đa một hàng.

### Bài 2. Dự đoán 0 hàng và 3 hàng

**Câu hỏi:** hai biểu thức sau trả gì trong PostgreSQL?

```sql
SELECT (
    SELECT salary FROM demo_employees WHERE employee_id = 999
);

SELECT (
    SELECT salary FROM demo_employees WHERE department_id = 10
);
```

**Đáp án:** câu đầu trả SQL `NULL` vì không có nhân viên 999; câu sau báo lỗi vì Sales có ba hàng. Hai tình huống không giống nhau.

### Bài 3. Lương cao nhất Sales

**Yêu cầu:** sửa truy vấn có nhiều hàng sao cho trả **lương lớn nhất** của Sales.

**Đáp án:**

```sql
SELECT (
    SELECT MAX(salary)
    FROM demo_employees
    WHERE department_id = 10
) AS max_sales_salary;
-- 1200
```

`MAX` trả một giá trị từ toàn tập, không chọn ngẫu nhiên nhân viên.

### Bài 4. Nhân viên lương trên trung bình của phòng mình

**Đáp án:**

```sql
SELECT e.employee_id, e.employee_name
FROM demo_employees e
WHERE e.salary > (
    SELECT AVG(x.salary)
    FROM demo_employees x
    WHERE x.department_id = e.department_id
)
ORDER BY e.employee_id;
-- 2, 5, 8
```

Đây là scalar subquery **tương quan**, vì truy vấn trong dùng `e.department_id` của truy vấn ngoài.

### Bài 5. Tập nhiều phòng ban

**Yêu cầu:** chọn nhân viên ở Sales **hoặc** Support, không dùng JOIN.

**Đáp án:**

```sql
SELECT employee_id, employee_name
FROM demo_employees
WHERE department_id IN (
    SELECT department_id
    FROM demo_departments
    WHERE department_name IN ('Sales', 'Support')
)
ORDER BY employee_id;
-- 1, 2, 6, 8
```

Không dùng `department_id = (SELECT ...)` vì truy vấn con có hai ID phòng ban.

### Bài 6. Phòng ban trống

**Yêu cầu:** đưa ra phòng ban chưa có nhân viên.

**Đáp án:**

```sql
SELECT d.department_id, d.department_name
FROM demo_departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_employees AS e
    WHERE e.department_id = d.department_id
);
-- 40, Research
```

`NOT EXISTS` trả lời câu hỏi tồn tại một cách trực tiếp; không cần scalar subquery trả số lương hay ID.

### Bài 7. Đơn hàng mới nhất và tình huống đồng hạng

**Yêu cầu:** lấy mã đơn gần nhất của khách 102, chọn ID lớn hơn nếu cùng thời điểm.

**Đáp án PostgreSQL:**

```sql
SELECT (
    SELECT order_id
    FROM demo_orders
    WHERE customer_id = 102
    ORDER BY created_at DESC, order_id DESC
    LIMIT 1
) AS latest_order_id;
-- 5004
```

Nếu bỏ `order_id DESC`, đơn 5003 và 5004 có cùng `created_at` nên không có quy tắc phân định chắc chắn.

### Bài 8. Khóa ghép của hệ thống đa tenant

**Câu hỏi:** bảng `tenant_staff` có ràng buộc `UNIQUE(tenant_id, employee_code)`. Truy vấn chỉ theo `employee_code = 'E001'` có bảo đảm scalar không?

**Đáp án:** không. Cùng mã có thể xuất hiện ở nhiều tenant. Phải bổ sung điều kiện `tenant_id` hoặc dùng một khóa khác duy nhất toàn hệ thống.

### Bài 9. Aggregate trên tập rỗng

**Câu hỏi:** tại sao hai biểu thức sau cho kết quả khác nhau khi không có nhân viên Research?

```sql
SELECT
    (SELECT COUNT(*) FROM demo_employees WHERE department_id = 40)
        AS employee_count,
    (SELECT AVG(salary) FROM demo_employees WHERE department_id = 40)
        AS average_salary;
```

**Đáp án:** `COUNT(*)` trả một hàng chứa 0; `AVG` trả một hàng chứa `NULL` vì không có lương để lấy trung bình. Cả hai đều hợp lệ ở vị trí scalar vì không trả nhiều hơn một hàng.

### Bài 10. Phân biệt hai ý định

Một người viết:

```sql
SELECT (
    SELECT employee_id
    FROM demo_employees
    WHERE department_id = 10
    LIMIT 1
);
```

**Câu hỏi:** câu này có nghĩa là “nhân viên giỏi nhất của Sales” không?

**Đáp án:** không. Nếu không có `ORDER BY` và tiêu chí đánh giá “giỏi nhất”, câu lệnh chỉ giới hạn một hàng bất kỳ. Cần nêu rõ thước đo, ví dụ lương cao nhất với `ORDER BY salary DESC, employee_id ASC LIMIT 1` nếu nghiệp vụ xác định tiêu chí như vậy; hoặc dùng truy vấn khác khi muốn tất cả người đồng hạng.

## Kết luận

Truy vấn con vô hướng là **truy vấn con được dùng như một biểu thức giá trị đơn**. Trong PostgreSQL và nhiều DBMS khác, nó phải trả **đúng một cột, không quá một hàng**: một hàng tạo giá trị, không có hàng tạo `NULL`, nhiều hàng gây lỗi. SQLite có ngoại lệ khi nhiều hàng: có thể lấy hàng đầu thay vì báo lỗi, nên thiết kế portable không được dựa vào hành vi này.

Để bảo đảm một giá trị đúng, hãy chọn **khóa duy nhất** khi tìm một thực thể, **hàm tổng hợp không `GROUP BY`** khi cần thống kê, **`ORDER BY` cộng giới hạn một hàng** khi nghiệp vụ thực sự muốn chọn đầu danh sách, và **`IN`/`EXISTS`/`ANY`/`ALL` hoặc `JOIN`** khi câu hỏi là về nhiều hàng. Với subquery tương quan, phải viết rõ điều kiện kết nối với hàng ngoài; với dữ liệu lớn, đánh giá kế hoạch và chỉ mục. Hiểu đúng hợp đồng số lượng hàng giúp câu SQL không chỉ chạy được mà còn phản ánh chính xác điều ứng dụng cần hỏi.

