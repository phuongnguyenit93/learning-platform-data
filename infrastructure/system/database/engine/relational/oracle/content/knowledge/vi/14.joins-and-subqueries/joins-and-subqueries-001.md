# INNER JOIN theo khóa đơn, khóa ghép và điều kiện nhiều cột trong Oracle Database

`INNER JOIN` kết hợp các hàng từ hai hoặc nhiều bảng khi điều kiện nối giữa chúng được thỏa mãn. Trong mô hình quan hệ, điều kiện nối thường dựa trên khóa chính và khóa ngoại, nhưng cũng có thể dùng nhiều cột để xác định một bản ghi tương ứng.

Có ba trường hợp cần phân biệt:

- **Nối theo khóa đơn:** một cột ở bảng này khớp với một cột ở bảng kia, ví dụ `EMPLOYEES.DEPT_ID = DEPARTMENTS.DEPT_ID`.
- **Nối theo khóa ghép:** phải so khớp đầy đủ nhiều cột cấu thành khóa, ví dụ `(TENANT_ID, PROJECT_CODE)`.
- **Nối theo nhiều điều kiện:** một hàng chỉ khớp khi đồng thời thỏa nhiều điều kiện trong mệnh đề `ON`, thường kết hợp bằng `AND`.

Nếu bỏ sót một thành phần khóa ghép, truy vấn có thể ghép nhầm dữ liệu giữa các tenant hoặc tạo ra nhiều dòng hơn dự kiến. Nếu hiểu sai bản chất `INNER JOIN`, người viết có thể vô tình loại bỏ những hàng không có bản ghi tương ứng ở bảng còn lại.

Bài học này trình bày cú pháp Oracle SQL, cách đọc quan hệ cha–con, xử lý khóa đơn và khóa ghép, kết hợp điều kiện nhiều cột, kiểm soát số dòng sau join, các lỗi thường gặp và ví dụ thực hành.

## 1. INNER JOIN là gì?

### 1.1. Ý nghĩa

`INNER JOIN` chỉ trả về các tổ hợp hàng mà điều kiện nối đánh giá là **TRUE**. Những hàng không tìm được hàng tương ứng ở phía còn lại sẽ không xuất hiện trong kết quả.

Ví dụ mô hình phòng ban và nhân viên:

```text
DEMO_DEPARTMENTS                 DEMO_EMPLOYEES
+---------+-------------+         +--------+----------+---------+
| DEPT_ID | DEPT_NAME  |         | EMP_ID | EMP_NAME | DEPT_ID |
+---------+-------------+         +--------+----------+---------+
| 10      | Engineering |         | 101    | An       | 10      |
| 20      | Sales       |         | 102    | Binh     | 10      |
| 30      | Finance     |         | 103    | Chi      | 20      |
+---------+-------------+         | 104    | Dung     | NULL    |
                                  +--------+----------+---------+
                 DEPT_ID = DEPT_ID
                         |
                         v
                 INNER JOIN result
                 +--------+----------+-------------+
                 | EMP_ID | EMP_NAME | DEPT_NAME   |
                 +--------+----------+-------------+
                 | 101    | An       | Engineering |
                 | 102    | Binh     | Engineering |
                 | 103    | Chi      | Sales       |
                 +--------+----------+-------------+
```

- Nhân viên 101 và 102 thuộc phòng ban 10.
- Nhân viên 103 thuộc phòng ban 20.
- Nhân viên 104 có `DEPT_ID=NULL` nên không khớp bằng phép so sánh `=`.
- Phòng ban 30 không có nhân viên nên cũng không xuất hiện trong kết quả.

### 1.2. Cú pháp ANSI JOIN trong Oracle

Cú pháp khuyến nghị:

```sql
SELECT select_list
FROM   table_a a
INNER JOIN table_b b
        ON a.key_column = b.key_column;
```

Ví dụ:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
ORDER  BY e.emp_id;
```

Các thành phần:

- `DEMO_EMPLOYEES e`: bảng nhân viên, bí danh `e`.
- `DEMO_DEPARTMENTS d`: bảng phòng ban, bí danh `d`.
- `ON d.dept_id = e.dept_id`: điều kiện nối.
- `SELECT` chỉ lấy các cột cần trình bày.
- `ORDER BY` quy định thứ tự kết quả; join tự nó không bảo đảm thứ tự.

Trong Oracle, `JOIN` không ghi loại join trong một số cú pháp sẽ mặc định là inner join. Tuy nhiên, viết rõ `INNER JOIN` giúp người đọc hiểu ý định ngay.

### 1.3. INNER JOIN khác WHERE như thế nào?

Cú pháp cũ có thể đặt điều kiện nối trong `WHERE`:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e,
       demo_departments d
WHERE  d.dept_id = e.dept_id;
```

Với inner join đơn giản, kết quả tương đương với cú pháp ANSI:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id;
```

Tuy nhiên, nên dùng cú pháp ANSI `JOIN ... ON` để phân biệt rõ **điều kiện nối bảng** và **điều kiện lọc hàng**. Khi truy vấn có nhiều bảng hoặc outer join, sự phân tách này đặc biệt hữu ích và tránh các lỗi do trộn cú pháp cũ với cú pháp mới.

## 2. Chuẩn bị dữ liệu thực hành khóa đơn

### 2.1. Tạo bảng phòng ban

```sql
CREATE TABLE demo_departments (
    dept_id   NUMBER(5) PRIMARY KEY,
    dept_name VARCHAR2(100) NOT NULL
);
```

### 2.2. Tạo bảng nhân viên

```sql
CREATE TABLE demo_employees (
    emp_id   NUMBER(10) PRIMARY KEY,
    emp_name VARCHAR2(100) NOT NULL,
    dept_id  NUMBER(5),
    CONSTRAINT fk_demo_emp_dept
        FOREIGN KEY (dept_id)
        REFERENCES demo_departments(dept_id)
);
```

Cột `DEPT_ID` ở bảng nhân viên là khóa ngoại tham chiếu khóa chính phòng ban. Cột này cho phép NULL vì chưa khai báo `NOT NULL`.

### 2.3. Thêm dữ liệu

```sql
INSERT INTO demo_departments VALUES (10, 'Engineering');
INSERT INTO demo_departments VALUES (20, 'Sales');
INSERT INTO demo_departments VALUES (30, 'Finance');

INSERT INTO demo_employees VALUES (101, 'An', 10);
INSERT INTO demo_employees VALUES (102, 'Binh', 10);
INSERT INTO demo_employees VALUES (103, 'Chi', 20);
INSERT INTO demo_employees VALUES (104, 'Dung', NULL);

COMMIT;
```

Dữ liệu này có:
- Ba phòng ban.
- Bốn nhân viên.
- Hai nhân viên cùng thuộc phòng ban 10.
- Một nhân viên chưa gắn phòng ban.
- Phòng ban 30 chưa có nhân viên.

### 2.4. Nối theo khóa đơn

```sql
SELECT e.emp_id,
       e.emp_name,
       e.dept_id,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON e.dept_id = d.dept_id
ORDER  BY e.emp_id;
```

Kết quả:

| EMP_ID | EMP_NAME | DEPT_ID | DEPT_NAME |
| ---: | --- | ---: | --- |
| 101 | An | 10 | Engineering |
| 102 | Binh | 10 | Engineering |
| 103 | Chi | 20 | Sales |

Hàng nhân viên 104 không được trả về vì `NULL = 10` hoặc `NULL = NULL` không đánh giá là TRUE trong điều kiện join. Phòng ban Finance cũng không xuất hiện vì không có nhân viên nào khớp.

### 2.5. Khóa đơn không có nghĩa quan hệ một-một

Một khóa chính ở bảng cha có thể được tham chiếu bởi nhiều hàng ở bảng con. Trong ví dụ:

- `DEMO_DEPARTMENTS.DEPT_ID` là duy nhất.
- `DEMO_EMPLOYEES.DEPT_ID` có thể lặp.
- Một phòng ban có thể có nhiều nhân viên.

Đây là quan hệ **một-nhiều (1:N)**. Khi join, một hàng phòng ban có thể xuất hiện nhiều lần, một lần cho mỗi nhân viên khớp.

Nếu cột nối ở cả hai bảng đều duy nhất, kết quả có thể là một-một. Nếu không có tính duy nhất ở cả hai phía, một giá trị có thể khớp nhiều hàng ở cả hai bảng và tạo quan hệ nhiều-nhiều trong kết quả.

## 3. Nối theo khóa đơn với điều kiện lọc

### 3.1. Lọc một bảng sau khi nối

Ví dụ chỉ lấy nhân viên thuộc Engineering:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
WHERE  d.dept_name = 'Engineering'
ORDER  BY e.emp_id;
```

`ON` xác định hai bảng liên kết theo `DEPT_ID`. `WHERE` lọc các hàng đã tham gia kết quả join theo tên phòng ban.

### 3.2. Điều kiện lọc và điều kiện nối có thể cùng nằm trong ON

Ví dụ:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
       AND d.dept_name = 'Engineering'
ORDER  BY e.emp_id;
```

Vì đây là `INNER JOIN`, chuyển điều kiện lọc tương ứng từ `ON` sang `WHERE` thường cho cùng tập kết quả. Dù vậy, cách viết nên nhất quán và dễ đọc:

- `ON` mô tả cách hai bảng khớp nhau.
- `WHERE` mô tả tiêu chí lọc kết quả.

Với `LEFT JOIN` hoặc `RIGHT JOIN`, vị trí điều kiện có thể làm thay đổi ý nghĩa đáng kể; không chuyển điều kiện giữa ON và WHERE một cách máy móc.

### 3.3. Nối nhiều bảng theo chuỗi

Ví dụ hệ thống có nhân viên, phòng ban và địa điểm làm việc:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name,
       l.city
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
INNER JOIN demo_department_locations dl
        ON dl.dept_id = d.dept_id
INNER JOIN demo_locations l
        ON l.location_id = dl.location_id
ORDER  BY e.emp_id;
```

Mỗi lần `INNER JOIN` thêm một quan hệ vào tập kết quả. Một hàng chỉ tiếp tục tồn tại nếu khớp với điều kiện nối ở từng bước.

Bảng `DEMO_DEPARTMENT_LOCATIONS` và `DEMO_LOCATIONS` trong ví dụ này là mô hình mở rộng minh họa; cần tạo và nạp dữ liệu tương ứng trước khi chạy truy vấn. Không chạy truy vấn khi các bảng đó chưa tồn tại.

### 3.4. Alias giúp tránh nhập nhằng

Khi nhiều bảng có cột cùng tên, luôn dùng bí danh:

```sql
SELECT e.emp_id,
       e.dept_id AS employee_dept_id,
       d.dept_id AS department_id
FROM   demo_employees e
INNER JOIN demo_departments d
        ON e.dept_id = d.dept_id;
```

Nếu viết `SELECT dept_id` khi cả hai bảng đều có cột `DEPT_ID`, Oracle có thể báo `ORA-00918: column ambiguously defined`. Dùng `e.dept_id` hoặc `d.dept_id` để xác định nguồn cột.

## 4. INNER JOIN theo khóa ghép (composite key)

### 4.1. Khóa ghép là gì?

Khóa ghép gồm **hai hoặc nhiều cột kết hợp với nhau** để xác định duy nhất một hàng. Từng cột riêng lẻ có thể lặp, nhưng tổ hợp của chúng là duy nhất.

Ví dụ hệ thống nhiều tenant có thể có cùng mã dự án:

| TENANT_ID | PROJECT_CODE | PROJECT_NAME |
| ---: | --- | --- |
| 1 | ERP | ERP - Tenant A |
| 2 | ERP | ERP - Tenant B |
| 1 | CRM | CRM - Tenant A |

Ở đây `PROJECT_CODE` không duy nhất trên toàn bảng vì cả tenant 1 và tenant 2 đều có dự án ERP. Khóa định danh thực sự là:

```text
(TENANT_ID, PROJECT_CODE)
```

Chỉ nối theo `PROJECT_CODE` là thiếu một phần khóa và có thể ghép dự án của tenant này với task của tenant khác.

### 4.2. Tạo bảng cha có khóa chính ghép

```sql
CREATE TABLE demo_projects (
    tenant_id    NUMBER(5) NOT NULL,
    project_code VARCHAR2(20) NOT NULL,
    project_name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_demo_projects
        PRIMARY KEY (tenant_id, project_code)
);
```

Oracle bảo đảm tổ hợp `TENANT_ID` và `PROJECT_CODE` là duy nhất.

### 4.3. Tạo bảng con tham chiếu khóa ghép

```sql
CREATE TABLE demo_project_tasks (
    task_id      NUMBER(10) PRIMARY KEY,
    tenant_id    NUMBER(5) NOT NULL,
    project_code VARCHAR2(20) NOT NULL,
    task_name    VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_demo_task_project
        FOREIGN KEY (tenant_id, project_code)
        REFERENCES demo_projects (tenant_id, project_code)
);
```

Thứ tự cột trong FK phải tương ứng với thứ tự cột trong khóa được tham chiếu:

- Cột thứ nhất: `TENANT_ID`.
- Cột thứ hai: `PROJECT_CODE`.

Khóa ngoại ghép này bảo đảm mỗi task tham chiếu một dự án đúng theo cả tenant và mã dự án.

### 4.4. Thêm dữ liệu hai tenant có cùng project code

```sql
INSERT INTO demo_projects VALUES (1, 'ERP', 'ERP - Tenant A');
INSERT INTO demo_projects VALUES (2, 'ERP', 'ERP - Tenant B');
INSERT INTO demo_projects VALUES (1, 'CRM', 'CRM - Tenant A');

INSERT INTO demo_project_tasks VALUES (
    101, 1, 'ERP', 'Build finance module'
);
INSERT INTO demo_project_tasks VALUES (
    102, 2, 'ERP', 'Build sales module'
);
INSERT INTO demo_project_tasks VALUES (
    103, 1, 'CRM', 'Design customer screen'
);

COMMIT;
```

### 4.5. INNER JOIN đúng theo cả hai cột khóa

```sql
SELECT t.task_id,
       t.task_name,
       t.tenant_id,
       t.project_code,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code
ORDER  BY t.task_id;
```

Kết quả:

| TASK_ID | TASK_NAME | TENANT_ID | PROJECT_CODE | PROJECT_NAME |
| ---: | --- | ---: | --- | --- |
| 101 | Build finance module | 1 | ERP | ERP - Tenant A |
| 102 | Build sales module | 2 | ERP | ERP - Tenant B |
| 103 | Design customer screen | 1 | CRM | CRM - Tenant A |

Mỗi task chỉ ghép với dự án có **đúng tenant và đúng project code**.

### 4.6. Sai lầm: chỉ nối theo một thành phần khóa

Truy vấn sai:

```sql
SELECT t.task_id,
       t.tenant_id AS task_tenant,
       t.project_code,
       p.tenant_id AS project_tenant,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.project_code = t.project_code
ORDER  BY t.task_id, p.tenant_id;
```

Với `PROJECT_CODE='ERP'`:

- Task 101 của tenant 1 khớp cả dự án ERP tenant 1 và ERP tenant 2.
- Task 102 của tenant 2 cũng khớp cả hai dự án ERP.
- Task 103 của CRM tenant 1 khớp một dự án CRM.

Kết quả có **5 dòng thay vì 3**. Hai task ERP bị nhân đôi và có thể hiển thị thông tin dự án của tenant sai.

Đây là lỗi nghiêm trọng trong hệ thống multi-tenant: dữ liệu có thể bị lẫn giữa các khách hàng/đơn vị. Cần nối đủ tất cả thành phần định danh của khóa.

### 4.7. Không chỉ vì tên cột giống nhau mà phải nối

Nếu hai bảng có các cột cùng tên, điều đó không chứng minh chúng cùng tạo thành một khóa. Ngược lại, tên cột khác nhau vẫn có thể biểu diễn cùng một định danh nghiệp vụ.

Ví dụ:

```sql
SELECT t.task_id,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.owner_tenant
       AND p.project_code = t.parent_project_code;
```

Đây là ví dụ minh họa về việc nối các cột có tên khác nhau nhưng cùng ý nghĩa theo mô hình dữ liệu. Truy vấn chỉ chạy nếu bảng có các cột `OWNER_TENANT` và `PARENT_PROJECT_CODE` tương ứng; trong bảng demo phía trên, tên cột là `TENANT_ID` và `PROJECT_CODE`.

## 5. Điều kiện nối nhiều cột bằng AND

### 5.1. Mỗi điều kiện mô tả một thành phần của quan hệ

Một điều kiện join có thể chứa nhiều biểu thức:

```sql
SELECT ...
FROM   table_a a
INNER JOIN table_b b
        ON a.col_1 = b.col_1
       AND a.col_2 = b.col_2
       AND a.col_3 = b.col_3;
```

Toàn bộ điều kiện phải đúng để hàng được ghép. Đây thường là dạng join theo composite key hoặc theo một bộ thuộc tính nghiệp vụ.

### 5.2. Ví dụ: ghép bảng giá theo vùng và SKU

Giả sử giá sản phẩm khác nhau theo từng vùng. Mã SKU có thể giống nhau ở nhiều vùng, nên chỉ dùng SKU là không đủ.

Tạo bảng giá:

```sql
CREATE TABLE demo_region_prices (
    region_code VARCHAR2(10) NOT NULL,
    sku         VARCHAR2(30) NOT NULL,
    unit_price  NUMBER(12,2) NOT NULL,
    CONSTRAINT pk_demo_region_prices
        PRIMARY KEY (region_code, sku)
);
```

Tạo bảng dòng bán:

```sql
CREATE TABLE demo_sales_lines (
    line_id     NUMBER(10) PRIMARY KEY,
    region_code VARCHAR2(10) NOT NULL,
    sku         VARCHAR2(30) NOT NULL,
    quantity    NUMBER(10) NOT NULL
);
```

Nạp dữ liệu:

```sql
INSERT INTO demo_region_prices VALUES ('NORTH', 'SKU-A', 100);
INSERT INTO demo_region_prices VALUES ('SOUTH', 'SKU-A', 120);
INSERT INTO demo_region_prices VALUES ('NORTH', 'SKU-B', 200);

INSERT INTO demo_sales_lines VALUES (1, 'NORTH', 'SKU-A', 2);
INSERT INTO demo_sales_lines VALUES (2, 'SOUTH', 'SKU-A', 3);
INSERT INTO demo_sales_lines VALUES (3, 'NORTH', 'SKU-B', 1);

COMMIT;
```

Nối đúng theo vùng và SKU:

```sql
SELECT s.line_id,
       s.region_code,
       s.sku,
       s.quantity,
       p.unit_price,
       s.quantity * p.unit_price AS line_total
FROM   demo_sales_lines s
INNER JOIN demo_region_prices p
        ON p.region_code = s.region_code
       AND p.sku = s.sku
ORDER  BY s.line_id;
```

Kết quả:

| LINE_ID | REGION_CODE | SKU | QUANTITY | UNIT_PRICE | LINE_TOTAL |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | NORTH | SKU-A | 2 | 100 | 200 |
| 2 | SOUTH | SKU-A | 3 | 120 | 360 |
| 3 | NORTH | SKU-B | 1 | 200 | 200 |

Nếu chỉ nối theo `SKU`, dòng bán NORTH/SKU-A có thể ghép nhầm với giá SOUTH/SKU-A. Điều kiện `REGION_CODE` là thành phần bắt buộc để xác định giá đúng.

### 5.3. Thêm điều kiện so khớp trạng thái hoặc hiệu lực

Một số mô hình cần khớp theo khóa và điều kiện trạng thái:

```sql
SELECT o.order_id,
       o.customer_id,
       c.customer_name
FROM   orders o
INNER JOIN customers c
        ON c.customer_id = o.customer_id
       AND c.is_active = 'Y';
```

Câu truy vấn chỉ trả đơn hàng có khách hàng tương ứng đang active. Điều kiện `IS_ACTIVE` không nhất thiết là một phần của khóa chính, nhưng là một điều kiện bổ sung để xác định hàng nào được phép tham gia kết quả.

Nếu mục tiêu là lấy tất cả đơn hàng và chỉ hiển thị tên khách hàng khi khách active, đó lại là bài toán khác, thường cần `LEFT JOIN`. Không đổi loại join hoặc chuyển điều kiện vị trí khác mà chưa xác định rõ yêu cầu.

### 5.4. Điều kiện nhiều cột có thể dùng toán tử khác dấu bằng

Không phải mọi join đều là equality join. Ví dụ ghép nhân viên với khoảng lương hoặc bảng phân bậc:

```sql
SELECT e.emp_id,
       e.salary,
       g.grade_name
FROM   employees e
INNER JOIN salary_grades g
        ON e.salary >= g.min_salary
       AND e.salary <  g.max_salary;
```

Đây là join theo **khoảng giá trị**. Một nhân viên chỉ ghép với bậc lương có khoảng chứa mức lương của họ.

Điều kiện dạng khoảng cần bảo đảm các khoảng không chồng lấn ngoài ý muốn. Nếu hai hàng bảng bậc cùng thỏa điều kiện, một nhân viên có thể xuất hiện nhiều lần. Với ví dụ này, quy ước khoảng nửa mở `[min_salary, max_salary)` giúp tránh việc hai bậc cùng nhận một mức lương đúng tại ranh giới, nếu dữ liệu khoảng được thiết kế liền kề.

## 6. INNER JOIN nhiều bảng và thứ tự logic

### 6.1. Nối theo một chuỗi quan hệ

Ví dụ nhân viên → phòng ban → công ty:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name,
       c.company_name
FROM   employees e
INNER JOIN departments d
        ON d.dept_id = e.dept_id
INNER JOIN companies c
        ON c.company_id = d.company_id
ORDER  BY c.company_name, d.dept_name, e.emp_name;
```

Mỗi mệnh đề join bổ sung một bảng và điều kiện tương ứng. Nếu nhân viên không có phòng ban hoặc phòng ban không có công ty khớp, hàng đó bị loại khỏi kết quả inner join.

### 6.2. Nối theo nhiều cột trên một chuỗi nhiều bảng

```sql
SELECT l.line_id,
       o.order_no,
       p.product_name,
       w.warehouse_name
FROM   order_lines l
INNER JOIN orders o
        ON o.tenant_id = l.tenant_id
       AND o.order_id = l.order_id
INNER JOIN products p
        ON p.tenant_id = l.tenant_id
       AND p.product_id = l.product_id
INNER JOIN warehouses w
        ON w.tenant_id = l.tenant_id
       AND w.warehouse_id = l.warehouse_id
ORDER  BY o.order_no, l.line_id;
```

Ví dụ cho hệ thống multi-tenant: mỗi quan hệ được nối theo cả tenant và ID của đối tượng. Điều kiện tenant cần được lặp lại ở từng quan hệ nếu tenant là một phần của định danh hoặc phạm vi dữ liệu.

Không phải hệ thống nào cũng cần cột tenant ở mọi bảng. Hãy dựa trên khóa và ràng buộc thật trong schema; không tự thêm điều kiện tenant nếu nó không thuộc mô hình dữ liệu.

### 6.3. Bí danh và tên cột trong nhiều bảng

Nên:
- Dùng bí danh ngắn nhưng có nghĩa, như `e` cho employees, `d` cho departments.
- Định danh cột có tiền tố bí danh trong `SELECT`, `ON`, `WHERE`.
- Đặt tên output rõ ràng bằng `AS` khi hai cột có cùng tên.
- Giữ các điều kiện nối gần bảng được nối để dễ đọc.

Ví dụ:

```sql
SELECT o.order_id,
       o.customer_id AS order_customer_id,
       c.customer_id AS matched_customer_id,
       c.customer_name
FROM   orders o
INNER JOIN customers c
        ON c.customer_id = o.customer_id;
```

## 7. NULL trong điều kiện INNER JOIN

### 7.1. NULL không khớp NULL bằng dấu bằng

Ví dụ:

```sql
SELECT a.id,
       a.code,
       b.description
FROM   source_a a
INNER JOIN source_b b
        ON a.code = b.code;
```

Nếu `A.CODE` và `B.CODE` đều NULL, điều kiện `A.CODE = B.CODE` không trả TRUE; kết quả là UNKNOWN. Vì thế hai hàng NULL không khớp nhau trong inner join bằng dấu `=`.

### 7.2. Nếu NULL có ý nghĩa “cùng chưa xác định”?

Thông thường, không nên tự động coi hai NULL là cùng một khóa. Nếu nghiệp vụ thực sự yêu cầu hai trạng thái thiếu dữ liệu được xem như khớp, cần diễn đạt quy tắc rõ ràng, ví dụ:

```sql
ON (
       a.code = b.code
       OR (a.code IS NULL AND b.code IS NULL)
   )
```

Nhưng cách này có thể ghép mọi hàng NULL của bảng A với mọi hàng NULL của bảng B, tạo ra nhiều cặp không mong muốn. Trước khi dùng, phải xác định liệu NULL có phải một giá trị nhóm hợp lệ hay chỉ là thông tin chưa biết.

### 7.3. NVL/COALESCE trong điều kiện join

Có thể thấy cách viết:

```sql
ON NVL(a.code, '#NULL#') = NVL(b.code, '#NULL#')
```

Cách này thay NULL bằng một giá trị giả. Nếu giá trị giả thực sự tồn tại trong dữ liệu, các hàng không NULL có thể bị ghép nhầm; ngoài ra, hàm trên cột có thể ảnh hưởng khả năng sử dụng index.

Nếu cần so sánh NULL-safe, dùng biểu thức có kiểm soát và chọn sentinel không thể xuất hiện theo ràng buộc dữ liệu, hoặc viết điều kiện `a.code = b.code OR (a.code IS NULL AND b.code IS NULL)`. Không dùng sentinel tùy tiện.

## 8. Cardinality: vì sao một join có thể tạo nhiều dòng?

### 8.1. Mối quan hệ một-nhiều

Với bảng phòng ban và nhân viên:

- Một hàng phòng ban có thể khớp nhiều hàng nhân viên.
- Kết quả có một dòng cho mỗi cặp phòng ban–nhân viên.
- Số hàng kết quả không nhất thiết bằng số hàng của bảng ít hơn.

Ví dụ phòng ban Engineering có hai nhân viên nên xuất hiện hai dòng. Đây không phải lỗi; đó là kết quả đúng của quan hệ 1:N.

### 8.2. Nhiều-nhiều hoặc khóa không duy nhất

Nếu cột nối không duy nhất ở cả hai phía, một giá trị có thể khớp nhiều hàng từ bảng A và nhiều hàng từ bảng B.

Giả sử code `X` có 2 hàng ở bảng A và 3 hàng ở bảng B, inner join theo code sẽ tạo:

\[
2 \times 3 = 6 \text{ hàng}
\]

Đây là phép kết hợp mọi cặp thỏa điều kiện. Nếu kết quả nhiều hơn mong đợi, hãy kiểm tra tính duy nhất của khóa nối và số lần xuất hiện ở mỗi bảng.

### 8.3. Kiểm tra khóa có bị lặp

Ví dụ:

```sql
SELECT tenant_id,
       project_code,
       COUNT(*) AS row_count
FROM   demo_projects
GROUP  BY tenant_id, project_code
HAVING COUNT(*) > 1;
```

Nếu bảng đã có khóa chính ghép `(TENANT_ID, PROJECT_CODE)` đang được bật, truy vấn này không trả hàng. Với bảng staging hoặc dữ liệu nguồn chưa có constraint, nó giúp phát hiện tổ hợp khóa bị lặp trước khi join.

### 8.4. Kiểm tra số lượng match của từng hàng

```sql
SELECT t.task_id,
       COUNT(p.project_code) AS matched_projects
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code
GROUP  BY t.task_id
HAVING COUNT(p.project_code) <> 1;
```

Vì bảng con có FK ghép và bảng cha có PK ghép đang được bật, mỗi task hợp lệ thường có đúng một dự án khớp. Truy vấn không trả hàng là kết quả kỳ vọng trong trạng thái dữ liệu này. Nếu constraint bị disable/novalidate hoặc nguồn dữ liệu chưa được kiểm soát, đây là cách kiểm tra cardinality thực tế.

## 9. INNER JOIN và khóa ngoại: mối quan hệ nhưng không đồng nhất

### 9.1. JOIN không yêu cầu phải có FOREIGN KEY

SQL cho phép nối hai cột ngay cả khi database không có constraint FK:

```sql
SELECT a.source_id,
       b.reference_name
FROM   import_rows a
INNER JOIN reference_data b
        ON b.external_code = a.external_code;
```

Điều kiện join chỉ yêu cầu biểu thức có thể so sánh. Tuy nhiên, không có FK nghĩa là Oracle không tự bảo đảm mọi mã ở bảng import đều tồn tại trong bảng tham chiếu.

### 9.2. FOREIGN KEY không tự động tạo truy vấn JOIN

FK là **ràng buộc toàn vẹn dữ liệu**. Nó bảo đảm quan hệ hợp lệ theo cấu hình constraint. Người viết vẫn phải khai báo `JOIN` khi muốn lấy cột từ hai bảng trong một câu SELECT.

Ví dụ:
- FK bảo đảm `EMPLOYEES.DEPT_ID` tham chiếu phòng ban hợp lệ khi constraint được bật và validate theo trạng thái.
- INNER JOIN dùng quan hệ đó để lấy `DEPT_NAME` cùng với nhân viên.

### 9.3. Nối theo khóa duy nhất được tham chiếu

Khi nối theo khóa đơn hoặc khóa ghép, nên hiểu rõ phía nào được bảo đảm duy nhất:
- PK/UK ở bảng cha bảo đảm mỗi khóa có tối đa một hàng tương ứng.
- FK ở bảng con có thể lặp ở nhiều hàng.
- Nếu join theo đầy đủ khóa cha, mỗi hàng con hợp lệ khớp tối đa một hàng cha.

Nếu chỉ dùng một cột không duy nhất của bảng cha, kết quả có thể nhân bản ngay cả khi bảng có một FK hợp lệ trên một bộ cột khác.

## 10. USING và NATURAL JOIN trong Oracle

### 10.1. USING khi cột nối cùng tên

Oracle hỗ trợ cú pháp `USING` khi các cột nối có cùng tên:

```sql
SELECT e.emp_id,
       e.emp_name,
       dept_id,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        USING (dept_id);
```

`USING (dept_id)` tương đương nối theo cột cùng tên `DEPT_ID`. Trong danh sách SELECT, cột dùng trong `USING` được tham chiếu như một cột chung; không nên viết `e.dept_id` hoặc `d.dept_id` cho chính cột USING đó.

Khi join theo khóa ghép cùng tên, có thể liệt kê các cột:

```sql
SELECT t.task_id,
       tenant_id,
       project_code,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        USING (tenant_id, project_code);
```

Cú pháp USING ngắn hơn, nhưng `ON` thường linh hoạt hơn khi tên cột khác nhau hoặc có điều kiện bổ sung.

### 10.2. Khi nên ưu tiên ON

Dùng `ON` khi:
- Hai cột nối có tên khác nhau.
- Cần nhiều điều kiện kết hợp.
- Cần thêm điều kiện hiệu lực/trạng thái.
- Muốn định danh rõ cột từ từng bảng.
- Cần biểu thức không chỉ là so sánh cột cùng tên.

Ví dụ:

```sql
SELECT t.task_id,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code;
```

### 10.3. NATURAL JOIN cần thận trọng

`NATURAL JOIN` tự động dùng **tất cả cột cùng tên** giữa hai bảng làm điều kiện nối. Điều này có thể tạo kết quả khó dự đoán khi schema thay đổi.

Ví dụ hai bảng cùng có `TENANT_ID`, `STATUS` và `CREATED_AT`. `NATURAL JOIN` sẽ dùng toàn bộ các cột cùng tên theo quy tắc của Oracle, không chỉ khóa mà người viết nghĩ đến.

Vì vậy, với truy vấn ứng dụng và báo cáo cần ổn định, nên viết rõ `ON` hoặc `USING` để người bảo trì thấy chính xác các cột nối. Không chọn NATURAL JOIN chỉ để giảm số ký tự SQL.

## 11. Tối ưu và index cho INNER JOIN

### 11.1. Index ở cột khóa nối

Trong ví dụ khóa đơn, bảng cha có PK trên `DEPT_ID`, Oracle thường có unique index hỗ trợ constraint đó. Bảng con có thể cần index trên `DEPT_ID` tùy truy vấn và workload.

Với khóa ghép:

```sql
PRIMARY KEY (tenant_id, project_code)
```

Oracle tạo cơ chế index hỗ trợ khóa chính. Thứ tự cột trong index ghép có ý nghĩa với các truy vấn lọc theo tiền tố của index. Index trên bảng con có thể được cân nhắc:

```sql
CREATE INDEX idx_demo_task_project
ON demo_project_tasks (tenant_id, project_code);
```

Index này có thể hỗ trợ join và truy vấn theo tenant/project, nhưng không nên tạo trùng với index đã tồn tại hoặc tạo chỉ vì một câu join đơn lẻ. Kiểm tra `USER_INDEXES` và `USER_IND_COLUMNS` trước khi thay đổi schema.

### 11.2. Thứ tự cột trong composite index

Index:

```sql
(tenant_id, project_code)
```

thường phù hợp với điều kiện:
- `tenant_id = :tenant_id`;
- `tenant_id = :tenant_id AND project_code = :project_code`.

Một truy vấn chỉ lọc `project_code` có thể không tận dụng index này hiệu quả như truy vấn bắt đầu bằng cột đầu tiên, tùy optimizer và cấu trúc index. Không đảo thứ tự cột tùy tiện; dựa trên các truy vấn thực tế và phân bố dữ liệu.

### 11.3. Optimizer có thể đổi thứ tự thực hiện join

Thứ tự bảng được viết trong SQL không nhất thiết là thứ tự Oracle truy cập bảng. Cost-based optimizer đánh giá:
- Thống kê bảng/cột/index.
- Số lượng hàng dự kiến sau mỗi điều kiện.
- Độ chọn lọc và phân bố dữ liệu.
- Các đường truy cập có sẵn.
- Chi phí join và bộ nhớ.

Do đó, không cần ép thứ tự join chỉ dựa trên cách đọc câu SQL. Hãy xem execution plan và số liệu thực tế nếu cần tối ưu.

### 11.4. Xem execution plan

Ví dụ:

```sql
EXPLAIN PLAN FOR
SELECT t.task_id,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code;

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` hiển thị kế hoạch ước lượng. Kế hoạch thực tế có thể khác do bind values, thống kê, dữ liệu và môi trường. Với workload sản xuất, dùng công cụ/plan của cursor đã chạy và số liệu runtime theo quyền được cấp.

Các phương pháp join như nested loops, hash join hoặc sort merge join được optimizer chọn theo chi phí. Không có một loại join luôn tốt nhất cho mọi kích thước và phân bố dữ liệu.

### 11.5. Chọn đúng cột thay vì SELECT *

Khi join nhiều bảng, tránh `SELECT *` nếu không cần toàn bộ cột:
- Giảm dữ liệu truyền về client.
- Tránh trùng tên cột trong output.
- Làm rõ bảng nào cung cấp dữ liệu.
- Hạn chế việc ứng dụng phụ thuộc vào cột mới được thêm sau này.

Ví dụ:

```sql
SELECT t.task_id,
       t.task_name,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code;
```

## 12. Lỗi thường gặp khi viết INNER JOIN

### 12.1. ORA-00918: column ambiguously defined

**Nguyên nhân:** chọn một cột cùng tên từ nhiều bảng mà không định danh bí danh.

Không rõ:

```sql
SELECT dept_id
FROM   demo_employees e
JOIN   demo_departments d
       ON d.dept_id = e.dept_id;
```

Rõ ràng:

```sql
SELECT e.dept_id AS employee_dept_id,
       d.dept_id AS department_id
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id;
```

### 12.2. Kết quả nhiều dòng hơn dự kiến

Nguyên nhân thường gặp:
- Nối thiếu một thành phần của khóa ghép.
- Cột được chọn làm khóa không duy nhất.
- Dữ liệu nguồn có duplicate.
- Join nhiều bảng 1:N làm nhân bản hàng.

Cách xử lý:
1. Xác định grain của kết quả mong muốn.
2. Kiểm tra PK/UK và các cột join.
3. Đếm số hàng mỗi khóa ở hai phía.
4. Bổ sung đầy đủ điều kiện join.
5. Tổng hợp trước khi join nếu mục tiêu là báo cáo ở mức khác.

Không thêm `DISTINCT` một cách máy móc để che lỗi join. DISTINCT có thể loại các dòng trùng hoàn toàn trong output nhưng không khôi phục được quan hệ đúng nếu các cột khác nhau hoặc aggregate đã bị nhân bản.

### 12.3. Kết quả thiếu hàng

Nguyên nhân:
- Dùng INNER JOIN nhưng có hàng không có bản ghi tương ứng.
- Một thành phần khóa ghép không khớp.
- Cột join chứa NULL.
- Điều kiện bổ sung trong ON quá chặt.
- Có WHERE lọc mất hàng sau join.
- Sai kiểu dữ liệu hoặc dữ liệu có khoảng trắng/collation khác nhau.

Nếu yêu cầu giữ cả hàng không có đối tác, cần đánh giá `LEFT JOIN` thay vì cố sửa inner join để giữ chúng.

### 12.4. Nối chỉ theo một cột trong khóa ghép

Ví dụ sai:

```sql
ON p.project_code = t.project_code
```

Nếu khóa thật là `(TENANT_ID, PROJECT_CODE)`, điều kiện phải là:

```sql
ON p.tenant_id = t.tenant_id
AND p.project_code = t.project_code
```

Thiếu tenant có thể gây rò rỉ hoặc trộn dữ liệu giữa các phạm vi khách hàng.

### 12.5. Dùng điều kiện nối sai kiểu dữ liệu

Ví dụ một bảng dùng `NUMBER` còn bảng kia dùng `VARCHAR2` để lưu ID. Oracle có thể thực hiện implicit conversion hoặc phát sinh lỗi khi gặp chuỗi không chuyển được sang số.

Nên chuẩn hóa kiểu dữ liệu hai phía theo cùng ý nghĩa, hoặc chuyển đổi có kiểm soát ở đúng nơi. Tránh áp hàm chuyển đổi lên cột lớn trong điều kiện join mà chưa đánh giá hiệu năng.

### 12.6. Đặt điều kiện sai vị trí

Với INNER JOIN, một số điều kiện lọc có thể chuyển giữa ON và WHERE mà không đổi kết quả. Nhưng khi truy vấn thay đổi thành OUTER JOIN, điều kiện trong WHERE có thể loại hàng null-extended và làm kết quả hoạt động như inner join.

Giữ rõ điều kiện quan hệ trong ON và điều kiện lọc chung trong WHERE để tránh thay đổi ngữ nghĩa ngoài dự định khi mở rộng truy vấn.

### 12.7. Nối cột có cùng tên nhưng khác ý nghĩa

Ví dụ hai bảng đều có `STATUS`, nhưng một cột là trạng thái đơn hàng, cột còn lại là trạng thái thanh toán. Không được tự nối `a.status = b.status` chỉ vì tên giống nhau. Điều kiện join phải dựa trên khóa/quan hệ nghiệp vụ, không dựa trên sự trùng tên.

## 13. Quy trình xây dựng truy vấn INNER JOIN

Trước khi viết câu SQL, xác định:

1. **Bảng gốc:** hàng kết quả cần đại diện cho đối tượng nào?
2. **Bảng cần lấy thêm:** thông tin nào nằm ở bảng khác?
3. **Khóa nối:** khóa đơn hay khóa ghép?
4. **Tính duy nhất:** khóa phía cha có PK/UK không? Có thể khớp nhiều hàng không?
5. **NULL:** các cột join có thể NULL không và NULL có ý nghĩa gì?
6. **Điều kiện bổ sung:** có cần tenant, trạng thái, thời gian hiệu lực hoặc vùng không?
7. **Cardinality:** kết quả dự kiến một-một, một-nhiều hay nhiều-nhiều?
8. **Loại join:** chỉ muốn các cặp khớp (INNER) hay cần giữ hàng không khớp (OUTER)?
9. **Cột output:** chọn rõ cột và bí danh.
10. **Hiệu năng:** index, thống kê và execution plan có phù hợp không?

Mẫu khóa đơn:

```sql
SELECT a.id,
       a.description,
       b.display_name
FROM   table_a a
INNER JOIN table_b b
        ON b.id = a.b_id
WHERE  a.status = 'ACTIVE';
```

Mẫu khóa ghép:

```sql
SELECT c.child_id,
       p.parent_name
FROM   child_table c
INNER JOIN parent_table p
        ON p.tenant_id = c.tenant_id
       AND p.parent_code = c.parent_code;
```

Mẫu điều kiện nhiều cột:

```sql
SELECT s.line_id,
       p.unit_price
FROM   sales_lines s
INNER JOIN price_list p
        ON p.region_code = s.region_code
       AND p.sku = s.sku
       AND p.currency_code = s.currency_code;
```

Các ví dụ là khung cú pháp; tên bảng/cột phải khớp schema thực tế.

## 14. Bài thực hành tổng hợp

Các bảng `DEMO_DEPARTMENTS`, `DEMO_EMPLOYEES`, `DEMO_PROJECTS`, `DEMO_PROJECT_TASKS`, `DEMO_REGION_PRICES` và `DEMO_SALES_LINES` được tạo ở các phần trước. Thực hiện trong schema học tập.

### Bài 1 — INNER JOIN khóa đơn

Lấy mã nhân viên, tên nhân viên và tên phòng ban:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
ORDER  BY e.emp_id;
```

**Kỳ vọng:** ba dòng nhân viên An, Binh và Chi. Dung không có phòng ban nên không xuất hiện.

### Bài 2 — Lọc theo bảng cha

Chỉ lấy nhân viên thuộc phòng ban Sales:

```sql
SELECT e.emp_id, e.emp_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
WHERE  d.dept_name = 'Sales';
```

**Kỳ vọng:** nhân viên 103.

### Bài 3 — INNER JOIN khóa ghép

```sql
SELECT t.task_id,
       t.tenant_id,
       t.project_code,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code
ORDER  BY t.task_id;
```

**Kỳ vọng:** ba task, mỗi task gắn đúng dự án trong tenant của nó.

### Bài 4 — Quan sát lỗi thiếu một thành phần khóa

Chạy có chủ đích trong môi trường demo:

```sql
SELECT t.task_id,
       t.tenant_id AS task_tenant,
       p.tenant_id AS project_tenant,
       t.project_code
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.project_code = t.project_code
ORDER  BY t.task_id, p.tenant_id;
```

**Kỳ vọng:** năm dòng, trong đó hai task ERP bị ghép với cả hai tenant. So sánh với bài 3 để nhận ra fan-out.

### Bài 5 — Nối theo hai điều kiện nghiệp vụ

```sql
SELECT s.line_id,
       s.region_code,
       s.sku,
       s.quantity,
       p.unit_price,
       s.quantity * p.unit_price AS line_total
FROM   demo_sales_lines s
INNER JOIN demo_region_prices p
        ON p.region_code = s.region_code
       AND p.sku = s.sku
ORDER  BY s.line_id;
```

**Kỳ vọng:** ba dòng với giá đúng theo vùng.

### Bài 6 — Đếm số task theo dự án

```sql
SELECT p.tenant_id,
       p.project_code,
       p.project_name,
       COUNT(t.task_id) AS task_count
FROM   demo_projects p
INNER JOIN demo_project_tasks t
        ON t.tenant_id = p.tenant_id
       AND t.project_code = p.project_code
GROUP  BY p.tenant_id, p.project_code, p.project_name
ORDER  BY p.tenant_id, p.project_code;
```

**Kỳ vọng:** mỗi dự án trong ba dự án có một task. Nếu muốn hiển thị cả dự án không có task, cần xem xét LEFT JOIN.

### Bài 7 — Phát hiện key trùng trong dữ liệu nguồn

```sql
SELECT region_code,
       sku,
       COUNT(*) AS duplicate_count
FROM   demo_region_prices
GROUP  BY region_code, sku
HAVING COUNT(*) > 1;
```

**Kỳ vọng:** không có dòng vì tổ hợp vùng/SKU được bảo vệ bởi khóa chính ghép.

### Bài 8 — Phân biệt JOIN với lọc

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
       AND d.dept_name = 'Engineering'
ORDER  BY e.emp_id;
```

Viết lại bằng cách chuyển điều kiện tên phòng ban sang `WHERE`. Với inner join này, kết quả phải tương đương.

### Bài 9 — Dùng USING với cột cùng tên

```sql
SELECT emp_id,
       emp_name,
       dept_id,
       dept_name
FROM   demo_employees
INNER JOIN demo_departments
        USING (dept_id)
ORDER  BY emp_id;
```

**Kỳ vọng:** cùng các hàng như bài 1. Lưu ý cột `DEPT_ID` trong `USING` được tham chiếu như cột chung.

### Bài 10 — Xem metadata index

```sql
SELECT i.index_name,
       i.table_name,
       c.column_name,
       c.column_position
FROM   user_indexes i
JOIN   user_ind_columns c
       ON c.index_name = i.index_name
      AND c.table_name = i.table_name
WHERE  i.table_name IN (
         'DEMO_PROJECTS',
         'DEMO_PROJECT_TASKS',
         'DEMO_REGION_PRICES',
         'DEMO_SALES_LINES'
       )
ORDER  BY i.table_name, i.index_name, c.column_position;
```

**Mục tiêu:** quan sát các index được tạo để hỗ trợ PK và các index do người dùng tạo. Không mặc định rằng mọi FK đều tự sinh index ở bảng con.

## 15. Câu hỏi tự kiểm tra

1. `INNER JOIN` trả về những hàng nào từ hai bảng?
2. Vì sao nhân viên có `DEPT_ID=NULL` không xuất hiện trong inner join bằng `=`?
3. Khóa đơn khác khóa ghép thế nào?
4. Nếu khóa cha là `(TENANT_ID, PROJECT_CODE)`, cần bao nhiêu điều kiện nối để khớp đúng khóa?
5. Điều gì có thể xảy ra nếu chỉ nối theo `PROJECT_CODE` khi mã dự án lặp giữa tenant?
6. `AND` trong mệnh đề ON có ý nghĩa gì khi nối theo nhiều cột?
7. Một phòng ban có ba nhân viên. Sau inner join, phòng ban đó có thể xuất hiện bao nhiêu dòng?
8. INNER JOIN có yêu cầu bảng phải khai báo FOREIGN KEY không?
9. FOREIGN KEY có tự động tạo câu SELECT JOIN không?
10. Vì sao nên dùng bí danh bảng trong truy vấn nhiều bảng?
11. `USING (dept_id)` khác `ON e.dept_id = d.dept_id` ở điểm cú pháp nào?
12. Vì sao cần thận trọng với NATURAL JOIN?
13. Nếu hai cột join đều NULL, phép bằng có làm chúng khớp nhau không?
14. Một join trả nhiều dòng hơn dự kiến. Nên kiểm tra điều gì trước khi thêm DISTINCT?
15. Tại sao `COUNT(*)` sau join có thể lớn hơn số hàng của bảng cha?
16. Điều kiện lọc trong ON và WHERE có luôn tương đương không?
17. Khi nối bảng giá theo vùng và SKU, vì sao chỉ nối SKU có thể sai?
18. Oracle có bắt buộc thực hiện join theo đúng thứ tự bảng được viết trong FROM không?
19. Index ghép `(TENANT_ID, PROJECT_CODE)` hỗ trợ tốt những kiểu điều kiện nào?
20. Nếu cần giữ các hàng không có bản ghi khớp, có nên tiếp tục dùng INNER JOIN không?

**Gợi ý đáp án:**

1. Chỉ các tổ hợp hàng mà điều kiện nối đánh giá TRUE.
2. So sánh với NULL cho UNKNOWN, không phải TRUE.
3. Khóa đơn có một cột; khóa ghép có từ hai cột trở lên tạo thành một định danh.
4. Cần so khớp cả hai cột.
5. Có thể ghép chéo tenant và nhân bản dòng.
6. Tất cả điều kiện phải đúng để hai hàng được ghép.
7. Ba dòng, mỗi nhân viên một cặp kết quả.
8. Không; JOIN là cú pháp truy vấn, có thể nối theo điều kiện dù không có FK.
9. Không; FK là constraint, truy vấn vẫn phải viết JOIN.
10. Tránh nhập nhằng tên cột và làm rõ nguồn dữ liệu.
11. USING dùng cột cùng tên; ON cho phép biểu thức và tên cột khác nhau.
12. Nó tự dùng mọi cột cùng tên, schema thay đổi có thể làm đổi điều kiện nối.
13. Không; NULL = NULL là UNKNOWN.
14. Kiểm tra khóa nối, uniqueness, duplicate và cardinality.
15. Vì một hàng cha có thể khớp nhiều hàng con.
16. Không; với outer join vị trí điều kiện có thể thay đổi kết quả.
17. Cùng SKU có thể có giá khác nhau theo vùng.
18. Không; optimizer có thể chọn thứ tự thực thi khác.
19. Điều kiện có tenant_id và tùy chọn project_code; tiền tố tenant_id cũng thường hữu ích.
20. Không; cân nhắc LEFT JOIN theo yêu cầu giữ hàng không khớp.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cú pháp SELECT, join clause, ON và USING.
- [Oracle Database SQL Language Reference — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html): các loại join và cách kết hợp bảng.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): bảng, khóa, quan hệ và toàn vẹn dữ liệu.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer, access paths và các phương pháp join.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): metadata index, constraint và các dictionary views.

Khi viết INNER JOIN, hãy xác định **đúng khóa và đầy đủ các thành phần của khóa** trước khi thêm điều kiện lọc. Với khóa ghép, mọi thành phần cần thiết phải được nối tương ứng; với điều kiện nhiều cột, dùng `AND` để diễn đạt quan hệ đồng thời. Sau đó kiểm tra tính duy nhất và cardinality để biết vì sao kết quả có số dòng như vậy. Dùng bí danh, chọn cột rõ ràng và đối chiếu execution plan khi cần tối ưu sẽ giúp truy vấn Oracle dễ hiểu và đáng tin cậy hơn.
