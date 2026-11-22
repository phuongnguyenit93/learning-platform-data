# Truy vấn con nhiều hàng với IN

## 1. Khi điều kiện lọc cần một tập giá trị từ truy vấn khác

Giả sử hệ thống có bảng `employees` lưu nhân viên và bảng `projects` lưu dự án. Cần trả lời câu hỏi:

> Những nhân viên nào thuộc phòng ban đang có ít nhất một dự án mở?

Ta không biết trước danh sách mã phòng ban đủ điều kiện. Danh sách này **được xác định bằng một truy vấn khác**, có thể trả nhiều hàng. Toán tử `IN` giúp kiểm tra một giá trị có thuộc tập giá trị do **truy vấn con (subquery)** trả về hay không:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
)
ORDER BY e.employee_id;
~~~

Cấu trúc cần ghi nhớ:

~~~sql
SELECT <cac_cot_can_lay>
FROM <bang_ngoai>
WHERE <bieu_thuc> IN (
    SELECT <mot_cot>
    FROM <bang_nguon_khac>
    WHERE <dieu_kien_cua_truy_van_con>
);
~~~

Trong ví dụ, **truy vấn con** xác định tập mã phòng ban có dự án mở, còn **truy vấn ngoài** dùng kết quả đó để lọc nhân viên. Truy vấn con có thể trả **0, 1 hoặc nhiều hàng**; `IN` vẫn là cú pháp phù hợp.

Đây là sự khác biệt quan trọng so với so sánh bằng `=`: phép `= (SELECT ...)` ở ngữ cảnh so sánh scalar yêu cầu truy vấn con trả **không quá một hàng**; nếu có nhiều hàng, phần lớn DBMS sẽ báo lỗi. `IN` được thiết kế chính cho **tư cách thành viên trong một tập kết quả**.

Bài học này sẽ làm rõ:

1. `IN (subquery)` xử lý nhiều hàng như thế nào.
2. Vì sao truy vấn con dạng này thường chỉ trả **một cột**.
3. Giá trị lặp, tập rỗng và `NULL` ảnh hưởng đến kết quả ra sao.
4. Khác biệt giữa `IN`, `NOT IN`, `EXISTS` và `JOIN`.
5. Truy vấn con **không tương quan** và **có tương quan**, cùng các nguyên tắc hiệu năng, khả chuyển và bảo mật.

## 2. Dữ liệu mẫu

Ví dụ sử dụng cú pháp SQL quan hệ thông dụng. DDL dưới đây tương thích về ý tưởng với PostgreSQL và có thể điều chỉnh ít nhiều cho MySQL, SQL Server hoặc SQLite.

### 2.1. Tạo ba bảng

~~~sql
CREATE TABLE departments (
    department_id   INTEGER PRIMARY KEY,
    department_name VARCHAR(80) NOT NULL,
    city            VARCHAR(50) NOT NULL
);

CREATE TABLE employees (
    employee_id      INTEGER PRIMARY KEY,
    employee_name    VARCHAR(80) NOT NULL,
    department_id    INTEGER,
    employment_status VARCHAR(20) NOT NULL,
    experience_years INTEGER NOT NULL,
    FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
);

CREATE TABLE projects (
    project_id            INTEGER PRIMARY KEY,
    project_name          VARCHAR(80) NOT NULL,
    department_id         INTEGER,
    project_status        VARCHAR(20) NOT NULL,
    required_experience   INTEGER NOT NULL,
    FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
);
~~~

Hai cột `employees.department_id` và `projects.department_id` đều **cho phép `NULL`**, để minh họa ảnh hưởng của dữ liệu chưa được gán phòng ban. Khóa ngoại giúp đảm bảo mã phòng ban khác `NULL` trỏ đến một phòng ban hiện có, nhưng không tự biến `NULL` thành một giá trị phòng ban.

### 2.2. Thêm dữ liệu

~~~sql
INSERT INTO departments (
    department_id, department_name, city
) VALUES
    (10, 'Data',      'Ha Noi'),
    (20, 'Analytics', 'Da Nang'),
    (30, 'Platform',  'Ho Chi Minh'),
    (40, 'Security',  'Hue');

INSERT INTO employees (
    employee_id, employee_name, department_id,
    employment_status, experience_years
) VALUES
    (1, 'An',   10, 'ACTIVE',   5),
    (2, 'Binh', 10, 'INACTIVE', 2),
    (3, 'Chi',  20, 'ACTIVE',   3),
    (4, 'Dung', 30, 'ACTIVE',   8),
    (5, 'Ha',   NULL, 'ACTIVE', 1),
    (6, 'Lan',  20, 'ACTIVE',   1),
    (7, 'Minh', 40, 'ACTIVE',   4);

INSERT INTO projects (
    project_id, project_name, department_id,
    project_status, required_experience
) VALUES
    (101, 'SQL Migration',   10, 'OPEN', 4),
    (102, 'Internal API',    10, 'DONE', 2),
    (103, 'BI Dashboard',    20, 'OPEN', 2),
    (104, 'Platform Core',   30, 'DONE', 4),
    (105, 'Security Audit',  40, 'OPEN', 4),
    (106, 'Independent',     NULL, 'OPEN', 1),
    (107, 'SQL Reporting',   10, 'OPEN', 3);
~~~

Các dữ kiện cần nhớ:

| Phòng ban | Mã | Nhân viên | Dự án OPEN |
| --- | ---: | --- | --- |
| Data | 10 | An, Binh | SQL Migration, SQL Reporting |
| Analytics | 20 | Chi, Lan | BI Dashboard |
| Platform | 30 | Dung | Không có; chỉ có dự án DONE |
| Security | 40 | Minh | Security Audit |
| Chưa gán phòng | NULL | Ha | Independent, chưa gán phòng |

Kết quả truy vấn con tìm các phòng ban của dự án mở là:

~~~sql
SELECT p.department_id
FROM projects AS p
WHERE p.project_status = 'OPEN'
ORDER BY p.project_id;
~~~

| department_id |
| ---: |
| 10 |
| 20 |
| 40 |
| NULL |
| 10 |

Có **năm hàng**, nhưng chỉ có ba mã phòng ban khác `NULL`: `10`, `20`, `40`. Mã `10` xuất hiện **hai lần**; bảng còn có một dự án OPEN chưa được gán phòng nên kết quả có `NULL`.

Những tình huống này giúp phân biệt rõ cách `IN`, `NOT IN` và `JOIN` hoạt động.

## 3. IN kiểm tra tư cách thành viên, không nhân số hàng

Một biểu thức:

~~~sql
e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
)
~~~

có thể được hiểu theo ý nghĩa:

> Có **ít nhất một** giá trị `department_id` do truy vấn con trả ra khớp với `e.department_id` hay không?

Kết quả của điều kiện là giá trị logic `TRUE`, `FALSE` hoặc `UNKNOWN` tùy trường hợp `NULL`. Trong `WHERE`, chỉ những hàng có điều kiện là **`TRUE`** mới được giữ.

Chạy câu truy vấn đầy đủ:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
)
ORDER BY e.employee_id;
~~~

Kết quả:

| employee_id | employee_name | department_id |
| ---: | --- | ---: |
| 1 | An | 10 |
| 2 | Binh | 10 |
| 3 | Chi | 20 |
| 6 | Lan | 20 |
| 7 | Minh | 40 |

**Tại sao kết quả có năm nhân viên chứ không phải nhiều hơn?**

- An và Binh thuộc phòng 10; phòng 10 xuất hiện **hai lần** trong truy vấn con nhưng mỗi nhân viên chỉ xuất hiện **một lần** ở kết quả `IN`.
- Chi và Lan thuộc phòng 20; phòng này có một dự án OPEN.
- Minh thuộc phòng 40; phòng này có một dự án OPEN.
- Dung thuộc phòng 30; phòng này không xuất hiện trong tập mã phòng ban của dự án OPEN.
- Ha có `department_id = NULL`; việc truy vấn con cũng trả `NULL` **không làm `NULL = NULL` trở thành `TRUE`**.

Điểm mấu chốt: **`IN` là điều kiện lọc hàng của truy vấn ngoài**. Nó không kết hợp mỗi hàng nhân viên với từng dự án; vì vậy nó **không tự nhân hàng nhân viên** dù truy vấn con có giá trị lặp.

### Sơ đồ luồng dữ liệu

~~~text
projects (lọc project_status = 'OPEN')
            │
            ▼
    department_id từ truy vấn con
       10, 20, 40, NULL, 10
            │
            ▼
     Kiểm tra từng employee
     department_id IN (...)
            │
       TRUE / FALSE / UNKNOWN
            │
            ▼
   WHERE chỉ giữ những hàng TRUE
            │
            ▼
      An, Binh, Chi, Lan, Minh
~~~

Sơ đồ thể hiện **ngữ nghĩa**. Nó không khẳng định DBMS thực thi bằng cách tạo một danh sách vật lý rồi lần lượt duyệt từng nhân viên; bộ tối ưu có thể dùng semi-join, hash, index hoặc kế hoạch khác.

## 4. Từ danh sách hằng đến truy vấn con

`IN` có thể xuất hiện với danh sách giá trị viết trực tiếp:

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE department_id IN (10, 20, 40)
ORDER BY employee_id;
~~~

Câu trên trả `1, 2, 3, 6, 7`. Khi danh sách mã phòng ban phải được **tính từ dữ liệu hiện có**, thay danh sách hằng bằng truy vấn con:

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM projects
    WHERE project_status = 'OPEN'
)
ORDER BY employee_id;
~~~

Hai truy vấn trả cùng danh sách nhân viên **với dữ liệu mẫu hiện tại**, nhưng không phải lúc nào cũng tương đương về bản chất:

- Danh sách `(10, 20, 40)` là **mã cố định** tại thời điểm viết SQL.
- Truy vấn con lấy **kết quả động** từ bảng `projects`.
- Nếu ngày mai phòng 30 mở dự án, truy vấn con sẽ tự nhận diện phòng 30 mà không cần sửa danh sách hằng.
- Giá trị `NULL` và giá trị lặp trong tập do truy vấn con trả ra phải được hiểu theo logic SQL, không phải như một danh sách trong bộ nhớ của ngôn ngữ lập trình.

`IN` với danh sách hằng thường hợp lý khi tập điều kiện nhỏ và được xác định sẵn bởi nghiệp vụ. `IN` với truy vấn con phù hợp khi **tập giá trị phụ thuộc vào dữ liệu hoặc một điều kiện truy vấn khác**.

## 5. Truy vấn con của IN thường trả một cột

Với dạng **so sánh một giá trị**:

~~~sql
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
)
~~~

vế trái là **một giá trị** `e.department_id`, nên truy vấn con phải cung cấp **một cột** có kiểu có thể so sánh tương thích.

Câu sau không hợp lệ trong ngữ cảnh `IN` một cột thông thường:

~~~sql
-- Sai: vế trái là một mã phòng ban,
-- truy vấn con lại trả cả mã dự án và mã phòng ban.
SELECT e.employee_id
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.project_id, p.department_id
    FROM projects AS p
);
~~~

Cũng không nên tùy tiện viết `SELECT *`:

~~~sql
-- Sai nếu projects có nhiều cột.
WHERE e.department_id IN (SELECT * FROM projects)
~~~

Hãy chọn chính xác cột mang ý nghĩa tư cách thành viên:

~~~sql
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
)
~~~

### Kiểu dữ liệu phải có khả năng so sánh

Mã phòng ban là `INTEGER` trong cả hai bảng. Nếu một cột là số còn cột kia chứa văn bản bất kỳ, các DBMS có thể báo lỗi kiểu hoặc thực hiện chuyển kiểu ngầm khác nhau. Không dựa vào việc một DBMS tự chuyển chuỗi `'10'` thành số `10` để viết truy vấn khả chuyển.

Nếu cần chuyển kiểu, hãy thiết kế **kiểu dữ liệu và quy tắc chuyển đổi rõ ràng**. Tránh chuyển cả cột tham gia truy vấn sang text chỉ để phép so sánh chạy được, vì có thể làm sai ý nghĩa và ảnh hưởng khả năng sử dụng chỉ mục.

### IN với nhiều cột: một trường hợp mở rộng

Một số DBMS hỗ trợ cú pháp so sánh **bộ giá trị (row-value comparison)**:

~~~sql
-- Ví dụ ở hệ hỗ trợ row-value IN như PostgreSQL:
SELECT e.employee_id
FROM employees AS e
WHERE (e.department_id, e.experience_years) IN (
    SELECT p.department_id, p.required_experience
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
);
~~~

Ở đây vế trái có **hai thành phần**, và truy vấn con trả **hai cột tương ứng**. Điều kiện kiểm tra **cặp giá trị bằng nhau**, không phải kiểm tra số năm kinh nghiệm “lớn hơn yêu cầu”. Với dữ liệu mẫu, các cặp chính xác trùng là `(40,4)` của Minh; các dự án khác không có cặp bằng đúng như vậy.

Cú pháp và cách tối ưu tuple/row-value khác nhau giữa DBMS. Phần lớn bài học tập trung vào `IN` **một cột**; khi cần so sánh nhiều thuộc tính với điều kiện không đơn thuần là bằng nhau, `EXISTS` hoặc `JOIN` thường dễ biểu đạt hơn.

## 6. Truy vấn con có thể trả 0, 1 hoặc nhiều hàng

### 6.1. Trả nhiều hàng: đúng mục đích của IN

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM projects
    WHERE project_status = 'OPEN'
)
ORDER BY employee_id;
~~~

Truy vấn con có năm hàng trong dữ liệu mẫu, không làm `IN` báo lỗi. `IN` đánh giá tư cách thành viên theo các giá trị được trả.

### 6.2. Trả một hàng: IN vẫn hợp lệ

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM projects
    WHERE project_id = 103
);
~~~

Dự án 103 thuộc phòng 20, nên kết quả có `Chi` và `Lan`. Truy vấn con chỉ trả một hàng nhưng `IN` vẫn hợp lệ.

Nếu biết chắc truy vấn con trả đúng một giá trị và chỉ muốn so sánh scalar, đôi khi có thể dùng `= (SELECT ...)`; tuy nhiên nếu sau này truy vấn con trả nhiều hàng, phép so sánh scalar có thể thất bại, còn `IN` vẫn tiếp tục có nghĩa “thuộc tập”.

### 6.3. Trả 0 hàng: không có giá trị nào để khớp

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM projects
    WHERE project_status = 'CANCELLED'
);
~~~

Dữ liệu mẫu không có dự án `CANCELLED`, nên truy vấn con trả tập rỗng và kết quả truy vấn ngoài cũng **0 hàng**.

Về mặt logic SQL, `x IN (truy_vấn_rỗng)` là **`FALSE`** vì không tồn tại giá trị nào khớp. Kể cả nếu `x` là `NULL`, tập rỗng vẫn không chứa phần tử, nên không có cặp so sánh nào tạo `UNKNOWN`.

Đây là một điểm khác với việc truy vấn con trả **một hàng có giá trị `NULL`**: tập `{NULL}` không phải là tập rỗng.

### 6.4. Giá trị trùng không làm thay đổi ý nghĩa membership

~~~sql
SELECT department_id
FROM projects
WHERE project_status = 'OPEN';
-- Có thể thấy: 10, 20, 40, NULL, 10
~~~

Viết:

~~~sql
SELECT DISTINCT department_id
FROM projects
WHERE project_status = 'OPEN';
-- Có các giá trị phân biệt: 10, 20, 40, NULL
~~~

Với `IN` một cột, các giá trị trùng như mã `10` không làm tăng số hàng nhân viên được trả. Do đó **không bắt buộc dùng `DISTINCT` trong truy vấn con chỉ để tránh nhân hàng**.

`DISTINCT` đôi khi được bộ tối ưu tự xử lý hoặc có ý nghĩa khi cùng kết quả được dùng cho mục đích khác, nhưng thêm nó máy móc có thể tạo công việc loại trùng không cần thiết. Hãy để bộ tối ưu lựa chọn chiến lược membership thích hợp và dùng `EXPLAIN` khi cần.

## 7. NULL trong IN: kết quả không chỉ có TRUE và FALSE

SQL sử dụng **logic ba giá trị**: `TRUE`, `FALSE` và `UNKNOWN`. Với một danh sách hoặc truy vấn con có `NULL`, kết quả `IN` có thể là `UNKNOWN`.

Hãy xem bảng logic:

| Giá trị cần kiểm tra | Tập truy vấn con | `IN` | Lý do |
| --- | --- | --- | --- |
| `10` | `{10, 20}` | TRUE | Có giá trị bằng 10 |
| `30` | `{10, 20}` | FALSE | Không có giá trị khớp và không có NULL |
| `10` | `{10, NULL}` | TRUE | Một so sánh đã là TRUE |
| `30` | `{10, NULL}` | UNKNOWN | Không có giá trị khớp; so với NULL là UNKNOWN |
| `NULL` | `{10, 20}` | UNKNOWN | Giá trị trái là NULL |
| `NULL` | `{NULL}` | UNKNOWN | `NULL = NULL` không phải TRUE |
| `30` | Tập rỗng | FALSE | Không tồn tại phần tử để khớp |
| `NULL` | Tập rỗng | FALSE | Không tồn tại phần tử để khớp |

Trong `WHERE`, chỉ **`TRUE`** được giữ; `FALSE` và `UNKNOWN` đều bị loại. Vì vậy trong truy vấn `IN` ban đầu:

- An, Binh thuộc mã `10` → `TRUE`.
- Chi, Lan thuộc mã `20` → `TRUE`.
- Minh thuộc mã `40` → `TRUE`.
- Dung có mã `30`, không có trong các mã khác `NULL` nhưng truy vấn con có `NULL` → `UNKNOWN`.
- Ha có mã `NULL` → `UNKNOWN`.

Truy vấn vẫn trả năm nhân viên như mong đợi. Nhưng **không thể suy ra “không được trả về” nghĩa là biểu thức IN đã là FALSE**: với Dung và Ha, nó có thể là `UNKNOWN`.

### Nếu muốn lọc ra người chưa có phòng ban

Đừng dùng:

~~~sql
-- Không tìm được hàng employee.department_id = NULL:
WHERE department_id IN (
    SELECT department_id
    FROM projects
    WHERE project_status = 'OPEN'
)
~~~

chỉ vì truy vấn con có dự án `NULL`. Kiểm tra thiếu dữ liệu bằng:

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE department_id IS NULL;
-- Ha
~~~

Nếu nghiệp vụ muốn “nhân viên có cùng giá trị phòng ban hoặc cả hai cùng chưa gán phòng”, đó là quy tắc **so sánh an toàn với `NULL`** riêng. Hãy diễn đạt rõ, chẳng hạn với `IS NOT DISTINCT FROM` ở DBMS hỗ trợ, hoặc mẫu điều kiện `(a = b OR (a IS NULL AND b IS NULL))` ở phép nối/tồn tại. Không mặc định `IN` cho kết quả đó.

## 8. Cạm bẫy của NOT IN khi truy vấn con có NULL

`NOT IN` có vẻ là cách tự nhiên để hỏi:

> Những phòng ban nào không có dự án OPEN?

Một câu dễ viết:

~~~sql
SELECT d.department_id, d.department_name
FROM departments AS d
WHERE d.department_id NOT IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
)
ORDER BY d.department_id;
~~~

**Kết quả trong dữ liệu mẫu: không có hàng nào.** Đây là một bẫy phổ biến.

Truy vấn con trả `10, 20, 40, NULL, 10`. Với phòng 30, không có dự án OPEN thuộc phòng 30; nhưng điều kiện trở thành ý nghĩa:

~~~sql
30 <> 10
AND 30 <> 20
AND 30 <> 40
AND 30 <> NULL
AND 30 <> 10
~~~

Các so sánh với mã 10, 20, 40 là `TRUE`, nhưng `30 <> NULL` là `UNKNOWN`, nên toàn bộ điều kiện là **`UNKNOWN`**, không phải `TRUE`. `WHERE` loại phòng 30. Những phòng 10, 20, 40 thì có một phép so sánh khớp bằng nên `NOT IN` là `FALSE`.

**Lưu ý:** toán tử `NOT IN` trong SQL không có nghĩa “bỏ qua những hàng trong truy vấn con mang `NULL`”. Khi truy vấn con có `NULL`, các giá trị chưa khớp có thể chuyển thành `UNKNOWN`.

### 8.1. Cách sửa thứ nhất: loại NULL ở truy vấn con

Vì khóa của bảng `departments` là `NOT NULL`, ta có thể lọc các dự án chưa gán phòng:

~~~sql
SELECT d.department_id, d.department_name
FROM departments AS d
WHERE d.department_id NOT IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id IS NOT NULL
)
ORDER BY d.department_id;
-- 30, Platform
~~~

Tập tham chiếu giờ chỉ có các mã phòng ban xác định. Phòng 30 không nằm trong tập nên được chọn.

Cách này phù hợp khi **đã xác định rõ hai phía so sánh đều không `NULL`** (hoặc đã có quy tắc xử lý khác đối với `NULL` phía ngoài).

### 8.2. Cách sửa thứ hai: dùng NOT EXISTS

Một cách diễn đạt thường rõ nghĩa hơn để hỏi “không có hàng liên quan nào”:

~~~sql
SELECT d.department_id, d.department_name
FROM departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id = d.department_id
)
ORDER BY d.department_id;
-- 30, Platform
~~~

`EXISTS` kiểm tra liệu truy vấn con có **ít nhất một hàng thỏa `WHERE`** hay không. Một dự án có `p.department_id = NULL` không khớp với mã phòng ban `30` (hoặc bất cứ mã phòng ban xác định nào), nên không vô hiệu hóa toàn bộ điều kiện `NOT EXISTS`.

Sự khác biệt đặc biệt hữu ích khi truy vấn con có cột nullable. Dù vậy, dùng `NOT EXISTS` cũng phải diễn đạt đúng **quy tắc về `NULL` của nghiệp vụ**; nếu hai giá trị cùng `NULL` cần được coi là khớp, phép `=` bên trong cũng chưa đủ.

### 8.3. Nếu phía ngoài có NULL thì sao?

Xét nhân viên chưa được gán phòng Ha:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id NOT IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id IS NOT NULL
);
~~~

Dù đã loại `NULL` ở truy vấn con, `e.department_id` của Ha vẫn là `NULL`. Vì vậy `NULL NOT IN {10, 20, 40}` là `UNKNOWN`, và Ha không được chọn.

Nếu yêu cầu là “nhân viên chưa thuộc phòng ban đang mở dự án, **bao gồm người chưa gán phòng**”, cần quy tắc riêng:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IS NULL
   OR e.department_id NOT IN (
       SELECT p.department_id
       FROM projects AS p
       WHERE p.project_status = 'OPEN'
         AND p.department_id IS NOT NULL
   )
ORDER BY e.employee_id;
-- Dung (4), Ha (5)
~~~

Một biểu thức `NOT EXISTS` có tương quan cũng có thể trả Dung và Ha:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id = e.department_id
)
ORDER BY e.employee_id;
-- Dung (4), Ha (5)
~~~

Kết quả chọn Ha ở truy vấn thứ hai là **đúng cho ý nghĩa “không tồn tại dự án OPEN khớp phòng ban đã biết”**, chứ không khẳng định Ha không có dự án liên quan trong thế giới thực. Cần thống nhất ngữ nghĩa dữ liệu chưa gán phòng.

## 9. IN và EXISTS: giống mục tiêu, khác cách biểu đạt

Để tìm nhân viên thuộc phòng có dự án OPEN, có thể dùng `IN`:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
)
ORDER BY e.employee_id;
~~~

Hoặc dùng `EXISTS` với truy vấn con có tương quan:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE EXISTS (
    SELECT 1
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id = e.department_id
)
ORDER BY e.employee_id;
~~~

Với dữ liệu mẫu, cả hai trả **1, 2, 3, 6, 7**. Vì sao?

- `IN` kiểm tra mã phòng của nhân viên có nằm trong tập mã do truy vấn con trả không.
- `EXISTS` kiểm tra có ít nhất một dự án OPEN mà mã phòng khớp mã của nhân viên không.
- Trong cả hai trường hợp, một nhân viên **không được nhân hàng** chỉ vì có hai dự án khớp.
- Một dự án với `department_id = NULL` không làm xuất hiện Ha, vì `NULL = NULL` không là `TRUE` trong điều kiện tương quan.

### Chọn IN hay EXISTS?

| Tiêu chí | `IN (subquery)` | `EXISTS (subquery)` |
| --- | --- | --- |
| Câu hỏi tự nhiên | “Giá trị này thuộc tập giá trị nào?” | “Có tồn tại ít nhất một hàng thỏa điều kiện này không?” |
| Kết quả truy vấn con | Thường là **một cột** khi so sánh scalar | Có thể `SELECT 1` hoặc biểu thức khác; chỉ sự tồn tại của hàng có ý nghĩa |
| Giá trị lặp | Không làm tăng số hàng truy vấn ngoài | Không làm tăng số hàng truy vấn ngoài |
| `NULL` | Cần hiểu logic ba giá trị | `EXISTS` tự là TRUE/FALSE theo sự tồn tại, nhưng điều kiện nội bộ vẫn có logic NULL |
| Tương quan | Có thể có hoặc không | Thường dùng với tương quan, nhưng không bắt buộc |
| Tối ưu hóa | DBMS có thể triển khai bằng semi-join/hash/index | DBMS cũng có thể triển khai bằng semi-join/hash/index |

**Không có quy tắc hiệu năng tuyệt đối** rằng `EXISTS` luôn nhanh hơn `IN` hay ngược lại. Bộ tối ưu của các hệ hiện đại thường nhận ra cấu trúc membership và biến đổi thành kế hoạch tương tự. Hiệu năng thực tế phụ thuộc dữ liệu, chỉ mục, cách viết biểu thức, thống kê và DBMS.

Đặc biệt, **`NOT IN` và `NOT EXISTS` không tự tương đương khi có `NULL`**. Đây là nơi cần cẩn trọng hơn so với hai dạng dương.

## 10. IN so với JOIN: tránh nhân hàng không mong muốn

Nếu thay `IN` bằng `JOIN` trực tiếp trên `projects`:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    p.project_id
FROM employees AS e
JOIN projects AS p
    ON p.department_id = e.department_id
WHERE p.project_status = 'OPEN'
ORDER BY e.employee_id, p.project_id;
~~~

Kết quả:

| employee_id | employee_name | project_id |
| ---: | --- | ---: |
| 1 | An | 101 |
| 1 | An | 107 |
| 2 | Binh | 101 |
| 2 | Binh | 107 |
| 3 | Chi | 103 |
| 6 | Lan | 103 |
| 7 | Minh | 105 |

Có **bảy hàng**. An và Binh mỗi người xuất hiện **hai lần**, vì phòng Data có hai dự án OPEN. Điều này **đúng** nếu câu hỏi là “mỗi cặp nhân viên–dự án OPEN trong cùng phòng”; nhưng **sai về mức hạt kết quả** nếu chỉ muốn danh sách nhân viên.

Nếu chỉ muốn biết nhân viên **có ít nhất một dự án OPEN trong phòng**, dùng `IN` hoặc `EXISTS` thường biểu đạt rõ hơn, không cần `DISTINCT` để khử các bản sao do `JOIN` tạo.

Có thể viết `JOIN` với tập mã phòng ban đã loại trùng:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
JOIN (
    SELECT DISTINCT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id IS NOT NULL
) AS open_departments
    ON open_departments.department_id = e.department_id
ORDER BY e.employee_id;
~~~

Kết quả cũng là **1, 2, 3, 6, 7**, nhưng câu SQL dài hơn và có thêm bước tạo tập duy nhất. Trong tình huống chỉ xét membership, cách `IN` thường trực quan.

### Phân biệt nhu cầu trả kết quả

| Yêu cầu | Một hàng đại diện cho | Lựa chọn phù hợp |
| --- | --- | --- |
| Nhân viên thuộc phòng có dự án OPEN | Nhân viên | `IN` hoặc `EXISTS` |
| Liệt kê nhân viên cùng từng dự án OPEN của phòng | Cặp nhân viên–dự án | `JOIN` |
| Đếm số dự án OPEN của từng phòng | Phòng ban | `GROUP BY` và `COUNT` |
| Chọn nhân viên thuộc một danh sách mã phòng ban từ bảng khác | Nhân viên | `IN (SELECT department_id ...)` |
| Tìm phòng ban không có dự án OPEN | Phòng ban | `NOT EXISTS` hoặc `NOT IN` khi đã xử lý `NULL` |

Trước khi chọn toán tử, hãy tự hỏi: **“Truy vấn cần kiểm tra sự tồn tại hay thực sự cần một hàng cho từng cặp liên kết?”**

## 11. IN với nhiều điều kiện ở truy vấn ngoài

Một truy vấn con xác định **tập giá trị có liên quan**, còn truy vấn ngoài có thể áp dụng các điều kiện bổ sung.

Ví dụ chỉ lấy nhân viên **đang làm việc** thuộc phòng có dự án mở:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id
FROM employees AS e
WHERE e.employment_status = 'ACTIVE'
  AND e.department_id IN (
      SELECT p.department_id
      FROM projects AS p
      WHERE p.project_status = 'OPEN'
  )
ORDER BY e.employee_id;
~~~

Kết quả:

| employee_id | employee_name | department_id |
| ---: | --- | ---: |
| 1 | An | 10 |
| 3 | Chi | 20 |
| 6 | Lan | 20 |
| 7 | Minh | 40 |

Binh không xuất hiện vì `employment_status = 'INACTIVE'`, dù phòng Data có dự án OPEN.

**Điều kiện ở đâu quyết định ý nghĩa của bộ lọc:**

- `p.project_status = 'OPEN'` trong truy vấn con xác định **tập phòng ban** hợp lệ.
- `e.employment_status = 'ACTIVE'` ở truy vấn ngoài xác định **nhân viên** hợp lệ.
- `e.department_id IN (...)` nối hai ý nghĩa đó bằng kiểm tra membership.

Khi chuyển điều kiện vào/ra truy vấn con, phải biết nó tham chiếu bảng nào và có làm thay đổi tập giá trị đủ điều kiện hay không.

### Nhiều cấp IN lồng nhau

Giả sử chỉ xét các phòng ban **ở Hà Nội** và đang có dự án OPEN:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id IN (
          SELECT d.department_id
          FROM departments AS d
          WHERE d.city = 'Ha Noi'
      )
)
ORDER BY e.employee_id;
-- 1, An; 2, Binh
~~~

Truy vấn con ở mức trong cùng trả danh sách mã phòng ở Hà Nội (chỉ mã 10 trong dữ liệu mẫu). Truy vấn con mức tiếp theo lấy mã phòng của dự án OPEN thuộc tập đó. Truy vấn ngoài trả nhân viên có mã phòng nằm trong tập cuối cùng.

Câu SQL này hợp lệ về mục đích, nhưng nếu nhiều cấp lồng nhau khiến truy vấn khó đọc, `JOIN` bên trong truy vấn con hoặc một `CTE` có thể giúp đặt tên các tập trung gian rõ hơn. Không nên lồng truy vấn chỉ để chứng minh có thể lồng.

## 12. Truy vấn con không tương quan và có tương quan

### 12.1. Không tương quan: độc lập với hàng của truy vấn ngoài

Ví dụ ban đầu:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
);
~~~

Truy vấn con chỉ tham chiếu `projects`, không sử dụng cột nào của alias `e` ở truy vấn ngoài. Đây là **truy vấn con không tương quan (uncorrelated subquery)**.

Về ngữ nghĩa, tập mã phòng ban được xác định từ dữ liệu dự án không phụ thuộc vào nhân viên cụ thể đang được kiểm tra. Bộ tối ưu có thể tính hoặc triển khai tập đó theo nhiều chiến lược.

### 12.2. Có tương quan: tập giá trị phụ thuộc vào hàng bên ngoài

Một yêu cầu khác:

> Lấy nhân viên có ít nhất một dự án OPEN trong phòng của họ mà yêu cầu số năm kinh nghiệm **không vượt quá** kinh nghiệm hiện có của nhân viên.

Ở đây điều kiện trong truy vấn con cần đọc `e.experience_years` của nhân viên hiện tại:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.experience_years
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.required_experience <= e.experience_years
)
ORDER BY e.employee_id;
~~~

Truy vấn con tham chiếu `e.experience_years`, là cột **ở ngoài phạm vi truy vấn con**. Đây là **correlated subquery**.

Với dữ liệu mẫu:

| employee_id | employee_name | experience_years | Lý do |
| ---: | --- | ---: | --- |
| 1 | An | 5 | Dự án 101 yêu cầu 4 năm; dự án 107 yêu cầu 3 |
| 3 | Chi | 3 | Dự án 103 yêu cầu 2 năm |
| 7 | Minh | 4 | Dự án 105 yêu cầu 4 năm |

Binh có 2 năm, trong khi hai dự án OPEN của phòng 10 cần ít nhất 4 và 3 năm. Lan có 1 năm nhưng dự án OPEN phòng 20 cần 2 năm. Dung có 8 năm nhưng phòng 30 không có dự án OPEN. Ha không có phòng ban xác định.

### Đọc kỹ phạm vi biến

Trong đoạn:

~~~sql
WHERE p.required_experience <= e.experience_years
~~~

- `p.required_experience` là cột từ `projects` **trong truy vấn con**.
- `e.experience_years` là cột từ `employees` **ở truy vấn ngoài**.

Cách viết alias tường minh giúp tránh lỗi do SQL tự tìm một tên cột không được đặt tiền tố trong các phạm vi lồng nhau. Nếu truy vấn con dùng một tên cột tưởng thuộc bảng con nhưng thực tế chỉ tồn tại ở bảng ngoài, một số DBMS có thể **ràng buộc nó vào cột ngoài** và khiến điều kiện có ý nghĩa hoàn toàn khác. Đây là lỗi khó nhận ra nếu không đặt alias.

### Truy vấn có tương quan không nhất thiết chạy từng hàng một

Về mặt **mô hình logic**, ta có thể nghĩ tập giá trị của truy vấn con thay đổi theo nhân viên đang xét. Nhưng không được kết luận DBMS chắc chắn chạy một truy vấn SQL vật lý riêng cho mỗi nhân viên. Bộ tối ưu có thể biến đổi thành join, semi-join, subplan có cache hoặc cách khác tùy trường hợp.

### Viết lại bằng EXISTS

Với điều kiện phải có dự án trong phòng và đạt kinh nghiệm tối thiểu, `EXISTS` có thể rõ ràng hơn:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE EXISTS (
    SELECT 1
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id = e.department_id
      AND p.required_experience <= e.experience_years
)
ORDER BY e.employee_id;
-- 1, 3, 7
~~~

Hai cách có cùng ý nghĩa lọc trong dữ liệu mẫu. `EXISTS` phù hợp khi trọng tâm là **“có ít nhất một dự án phù hợp”** thay vì tạo ra một tập giá trị cột để kiểm tra membership.

## 13. Lọc theo một cột từ bảng khác: ví dụ phòng ban tại thành phố

Không phải truy vấn con nào cũng phải xuất phát từ bảng dự án. Ví dụ:

> Lấy các nhân viên thuộc phòng ban ở Hà Nội hoặc Đà Nẵng.

~~~sql
SELECT e.employee_id, e.employee_name, e.department_id
FROM employees AS e
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments AS d
    WHERE d.city IN ('Ha Noi', 'Da Nang')
)
ORDER BY e.employee_id;
~~~

Kết quả: **An, Binh, Chi, Lan** (ID `1, 2, 3, 6`).

Ở đây có **hai lần `IN`**:

- `d.city IN ('Ha Noi', 'Da Nang')`: kiểm tra thành phố thuộc **danh sách hằng**.
- `e.department_id IN (SELECT ...)`: kiểm tra mã phòng của nhân viên thuộc **tập mã từ truy vấn con**.

Cấu trúc này tự nhiên khi các danh mục đủ điều kiện được lưu trong bảng khác. Việc viết một câu `JOIN` vẫn có thể cho cùng tập nhân viên nếu khóa phòng ban là duy nhất:

~~~sql
SELECT e.employee_id, e.employee_name, e.department_id
FROM employees AS e
JOIN departments AS d
    ON d.department_id = e.department_id
WHERE d.city IN ('Ha Noi', 'Da Nang')
ORDER BY e.employee_id;
~~~

Vì `departments.department_id` là khóa chính, một nhân viên khớp tối đa một phòng ban nên phép nối này không nhân hàng. Nhưng điều đó đến từ **ràng buộc duy nhất của cột nối**, không phải mọi phép `JOIN` đều giữ nguyên số hàng.

## 14. IN không tự sắp xếp kết quả ngoài

Một hiểu nhầm là thứ tự các mã trong truy vấn con sẽ quyết định thứ tự nhân viên trả ra. Không đúng.

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
)
ORDER BY e.employee_id DESC;
~~~

Trong ví dụ này, thứ tự hàng theo **`e.employee_id DESC`**, vì đó là `ORDER BY` của truy vấn **ngoài cùng**. Thứ tự các giá trị mà truy vấn con tạo ra không có ý nghĩa sắp xếp đối với phép kiểm tra `IN`.

Không nên thêm `ORDER BY` vào truy vấn con chỉ nhằm làm cho kết quả `IN` “có thứ tự”. Một số DBMS còn hạn chế vị trí `ORDER BY` trong subquery nếu không có cú pháp giới hạn hàng tương ứng; kể cả khi cho phép, nó không biến membership thành một phép sắp xếp.

Nếu cần hiển thị nhân viên theo tên:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
)
ORDER BY e.employee_name ASC, e.employee_id ASC;
~~~

Thêm `employee_id` làm khóa phá hòa để có thứ tự ổn định khi hai nhân viên trùng tên.

## 15. Hiệu năng: bộ tối ưu có thể biến IN thành semi-join

Khi dữ liệu lớn, hiệu năng của `IN (subquery)` phụ thuộc vào nhiều yếu tố:

- Số hàng ở truy vấn ngoài và mức độ chọn lọc của các điều kiện.
- Số mã khác nhau mà truy vấn con tạo ra.
- Có `NULL` và giá trị trùng hay không.
- Khả năng sử dụng chỉ mục trên các cột lọc và cột so sánh.
- Thống kê dữ liệu, kiểu dữ liệu, collation, điều kiện tương quan.
- Chiến lược tối ưu của DBMS và phiên bản đang chạy.

Một số kế hoạch có thể thực thi `IN` như **semi-join**: chỉ kiểm tra có hàng khớp hay không, không cần tạo ra mọi cặp kết quả như `INNER JOIN` thông thường. Hệ cũng có thể dùng hash tập giá trị, index lookup, materialization hoặc xử lý riêng cho subquery có tương quan.

Không có quy tắc tuyệt đối rằng “`IN` luôn chậm vì chạy subquery cho mỗi hàng” hay “`EXISTS` luôn nhanh hơn `IN`”. Hãy kiểm tra kế hoạch thực tế.

### 15.1. Chỉ mục mẫu

~~~sql
CREATE INDEX idx_projects_status_department
    ON projects (project_status, department_id);

CREATE INDEX idx_employees_department
    ON employees (department_id);
~~~

Chỉ mục `projects(project_status, department_id)` có thể hỗ trợ chọn dự án có trạng thái OPEN rồi đọc mã phòng ban. Chỉ mục `employees(department_id)` có thể hữu ích trong các kế hoạch tìm nhân viên theo tập mã phòng.

Với truy vấn có điều kiện kinh nghiệm:

~~~sql
CREATE INDEX idx_projects_status_dept_experience
    ON projects (
        project_status,
        department_id,
        required_experience
    );
~~~

Chỉ mục này là một **ứng viên** chứ không phải công thức bắt buộc. Mức hữu ích tùy phân phối giá trị, thứ tự điều kiện, số lượng hàng và kế hoạch chọn. Nhiều chỉ mục cũng làm tăng chi phí ghi và dung lượng lưu trữ.

### 15.2. Xem execution plan

Ví dụ PostgreSQL:

~~~sql
EXPLAIN
SELECT e.employee_id
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
);
~~~

`EXPLAIN` cho biết **kế hoạch dự kiến**; `EXPLAIN (ANALYZE, BUFFERS)` có thể đo thực thi thật, nhưng `ANALYZE` sẽ chạy truy vấn. Trên bộ dữ liệu mẫu rất nhỏ, DBMS có thể chọn quét tuần tự thay vì dùng chỉ mục; đó là lựa chọn bình thường, không đủ để kết luận về hiệu năng ở production.

Một quy trình hợp lý khi truy vấn chậm là:

1. Kiểm tra truy vấn con trả đúng cột và tập giá trị dự kiến.
2. Xác nhận kiểu dữ liệu và điều kiện có dùng được chỉ mục không.
3. Xem execution plan, số hàng ước lượng/thực tế và các bước quét/sắp xếp.
4. Xem xét chỉ mục, thống kê, viết lại bằng `EXISTS`/`JOIN` nếu phù hợp **ngữ nghĩa** và **đo đạc**.
5. Đánh giá với lượng dữ liệu, tỷ lệ trùng và phân phối `NULL` đại diện cho môi trường thật.

Không thêm `DISTINCT` hoặc viết lại bằng `JOIN` chỉ để hy vọng nhanh hơn mà chưa đo.

## 16. Tính khả chuyển giữa các hệ SQL

Những nguyên tắc sau được hỗ trợ rộng rãi trong SQL tiêu chuẩn và các DBMS phổ biến:

- `x IN (SELECT col FROM ...)` cho phép truy vấn con trả nhiều hàng.
- Với vế trái scalar, truy vấn con cần trả một cột tương thích để so sánh.
- `IN` không nhân hàng ngoài chỉ vì có giá trị trùng trong truy vấn con.
- `NULL` làm phát sinh logic ba giá trị; `NOT IN` có thể gây kết quả bất ngờ.
- `EXISTS`/`NOT EXISTS` kiểm tra sự có/không có hàng khớp.
- Thứ tự kết quả ngoài chỉ được xác định khi có `ORDER BY` ngoài cùng.

Khác biệt cần kiểm tra theo DBMS:

| Vấn đề | Lưu ý |
| --- | --- |
| Cú pháp row-value `(a,b) IN (SELECT x,y ...)` | Hỗ trợ và tối ưu không đồng nhất giữa hệ và phiên bản |
| Kiểu dữ liệu so sánh | Có DBMS tự ép kiểu; có hệ yêu cầu cùng kiểu hoặc kiểm tra chặt |
| CTE và subquery materialization | Quyết định vật chất hóa, inline và cache phụ thuộc bộ tối ưu |
| `EXPLAIN` / execution plan | Cú pháp và trường thông tin khác nhau |
| Index cho khóa ngoại | Không phải hệ nào cũng tự tạo index ở cột FK |
| Phân trang/kết hợp `ORDER BY` | `LIMIT`, `TOP`, `FETCH` và quy tắc trong subquery khác nhau |
| So sánh chuỗi | Collation có thể khác; nếu `IN` dùng chuỗi, kết quả khớp có thể phụ thuộc chữ hoa/thường, dấu và kiểu |

Nếu cùng một cột `department_id` trong mọi bảng được thiết kế nhất quán kiểu `INTEGER`, truy vấn sẽ rõ nghĩa và khả chuyển hơn so với việc có bảng lưu mã dưới dạng chuỗi rồi phụ thuộc ép kiểu ngầm.

## 17. An toàn khi tập giá trị đến từ người dùng

`IN (subquery)` khác với dạng danh sách giá trị truyền từ ứng dụng, nhưng cả hai đều cần quan tâm đến **SQL injection**.

Một yêu cầu như “lọc nhân viên theo các phòng ban người dùng chọn” có thể cần tham số hóa. Không xây câu SQL bằng cách nối dữ liệu người dùng trực tiếp vào chuỗi:

~~~java
// Không dùng: clientIds đến từ input có thể bị can thiệp.
String sql = "SELECT * FROM employees WHERE department_id IN ("
        + clientIds + ")";
~~~

Với JDBC và danh sách có số phần tử biến động, cần tạo đúng số placeholder `?` rồi bind từng giá trị, hoặc dùng giải pháp chuyên biệt theo DBMS (mảng PostgreSQL với `ANY`, table-valued parameters ở SQL Server, bảng tạm, bảng tiêu chí, v.v.).

Ví dụ khi đã có **chính xác ba mã**:

~~~java
String sql = """
    SELECT employee_id, employee_name
    FROM employees
    WHERE department_id IN (?, ?, ?)
    ORDER BY employee_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, 10);
    ps.setInt(2, 20);
    ps.setInt(3, 40);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("employee_id"));
        }
    }
}
~~~

Lưu ý: nhiều DBMS không cho phép `IN ()` với danh sách rỗng; ứng dụng cần xử lý trường hợp không có ID được chọn bằng cách trả danh sách rỗng hoặc một điều kiện luôn sai theo cách phù hợp. Một dấu `?` đơn không mặc định có thể chứa cả chuỗi `"10,20,40"` rồi được SQL hiểu thành ba giá trị. Cách bind phụ thuộc driver/ORM và DBMS.

Với `IN (subquery)`, tham số người dùng cũng nên được bind ở **điều kiện trong subquery**, ví dụ:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = ?
);
~~~

Giá trị trạng thái là dữ liệu, được bind bằng driver. Không tạo SQL bằng cách ghép trực tiếp chuỗi `'OPEN'` do người dùng gửi vào.

## 18. Những lỗi thường gặp

| Lỗi / ngộ nhận | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `= (SELECT department_id ...)` dù truy vấn con có thể trả nhiều hàng | Lỗi “subquery returns more than one row” hoặc tương đương | Dùng `IN` khi muốn kiểm tra thuộc tập |
| Truy vấn con của `IN` scalar trả hai cột | Không khớp số thành phần cần so sánh | Chọn đúng một cột hoặc thiết kế tuple theo DBMS |
| Dùng `SELECT *` trong subquery có nhiều cột | Không tương thích vế trái scalar | Liệt kê chính xác cột membership |
| Nghĩ `IN` tự nhân hàng vì phòng 10 xuất hiện hai lần | Dự đoán sai số hàng | `IN` chỉ lọc; giá trị trùng không nhân hàng |
| Dùng `NOT IN` mà subquery có `NULL` | Có thể không trả hàng dù tồn tại giá trị không thuộc tập | Lọc `NULL` hoặc dùng `NOT EXISTS` đúng nghiệp vụ |
| Nghĩ `NULL IN (SELECT NULL)` là TRUE | Sai logic ba giá trị | Dùng `IS NULL` hoặc so sánh null-safe khi cần |
| Thêm `DISTINCT` vào subquery chỉ để tránh trùng nhân viên | Có thể thêm công việc không cần thiết | Không bắt buộc DISTINCT cho membership |
| Thay `IN` bằng `JOIN` mà không xét bội số | Nhân hàng nhân viên khi có nhiều dự án | Dùng `IN`/`EXISTS` khi chỉ cần kiểm tra tồn tại |
| Dùng alias/cột không đủ tên trong truy vấn có tương quan | Có thể tham chiếu nhầm cột từ cấp ngoài | Luôn dùng `e.col`, `p.col` rõ ràng |
| Thêm `ORDER BY` ở subquery để quyết định thứ tự kết quả | Không quyết định thứ tự output bên ngoài | `ORDER BY` ở truy vấn ngoài |
| Ép kiểu số thành chuỗi tùy tiện | So sánh lệch kiểu, index kém hữu ích | Thiết kế kiểu dữ liệu nhất quán |
| Tin `IN` luôn chậm/nhanh hơn `EXISTS` | Quyết định tối ưu không có căn cứ | Xem execution plan trên dữ liệu đại diện |
| Ghép danh sách ID của người dùng vào SQL | Nguy cơ SQL injection | Placeholder, bind params, table-valued input |
| Không xử lý tập tham số rỗng ở ứng dụng | Có thể sinh `IN ()` không hợp lệ | Xử lý danh sách rỗng tường minh |

## 19. Bài tập thực hành

Sử dụng dữ liệu mẫu ở mục 2. Nếu đã sửa bảng, khởi tạo lại để kết quả trùng các đáp án. Thực hành dự đoán kết quả trước khi đọc đáp án.

### Bài 1 — Nhân viên ở phòng có dự án OPEN

Viết truy vấn dùng `IN (subquery)` để lấy `employee_id`, `employee_name` của nhân viên thuộc phòng có dự án mở, sắp theo mã nhân viên.

**Đáp án:**

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
)
ORDER BY e.employee_id;
~~~

Kết quả: **1 An, 2 Binh, 3 Chi, 6 Lan, 7 Minh**.

### Bài 2 — Thêm điều kiện ACTIVE

Chỉ lấy nhân viên đang làm việc thuộc phòng có dự án OPEN. Điều kiện trạng thái nhân viên nên đặt ở đâu?

**Đáp án:**

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.employment_status = 'ACTIVE'
  AND e.department_id IN (
      SELECT p.department_id
      FROM projects AS p
      WHERE p.project_status = 'OPEN'
  )
ORDER BY e.employee_id;
~~~

Kết quả: **1 An, 3 Chi, 6 Lan, 7 Minh**. Điều kiện về nhân viên nằm ở truy vấn ngoài; điều kiện về dự án nằm trong truy vấn con.

### Bài 3 — Giá trị lặp có tạo thêm nhân viên không?

Truy vấn con trả các mã `10, 20, 40, NULL, 10`. Vì sao An không xuất hiện hai lần dù mã 10 được trả hai lần?

**Đáp án:** `IN` kiểm tra **có khớp ít nhất một giá trị hay không**, không nối từng hàng nhân viên với mỗi hàng dự án. An là **một hàng nguồn** và được giữ một lần. Nếu dùng `JOIN projects`, An có thể xuất hiện hai lần vì có hai cặp nhân viên–dự án khớp.

### Bài 4 — Tìm phòng ban không có dự án OPEN

Đoán kết quả câu sau:

~~~sql
SELECT department_id
FROM departments
WHERE department_id NOT IN (
    SELECT department_id
    FROM projects
    WHERE project_status = 'OPEN'
);
~~~

Sau đó sửa truy vấn để trả đúng phòng Platform.

**Đáp án:** truy vấn đầu **không trả hàng** vì truy vấn con có `NULL`. Cách sửa:

~~~sql
SELECT d.department_id, d.department_name
FROM departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id = d.department_id
)
ORDER BY d.department_id;
~~~

Kết quả: **30, Platform**. Có thể dùng `NOT IN` nếu lọc `p.department_id IS NOT NULL` trong truy vấn con và phía ngoài là khóa phòng ban không `NULL`.

### Bài 5 — Phân biệt hai cách lọc nhân viên

Chọn truy vấn hợp lý hơn khi chỉ cần **mỗi nhân viên một hàng**:

~~~sql
-- A
SELECT e.employee_id
FROM employees AS e
JOIN projects AS p
    ON p.department_id = e.department_id
WHERE p.project_status = 'OPEN';

-- B
SELECT e.employee_id
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
);
~~~

**Đáp án:** **B** diễn đạt đúng membership. A trả **bảy hàng** trong dữ liệu mẫu, gồm An và Binh mỗi người hai lần. B trả **năm hàng**, mỗi nhân viên chỉ xuất hiện một lần.

### Bài 6 — Truy vấn con tương quan

Tìm nhân viên thuộc phòng có dự án OPEN mà yêu cầu kinh nghiệm không lớn hơn kinh nghiệm của họ. Viết bằng `IN` và giải thích cột nào đến từ truy vấn ngoài.

**Đáp án:**

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IN (
    SELECT p.department_id
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.required_experience <= e.experience_years
)
ORDER BY e.employee_id;
~~~

Kết quả: **1 An, 3 Chi, 7 Minh**. `e.experience_years` là cột từ **truy vấn ngoài**; vì truy vấn con tham chiếu nó nên đây là correlated subquery.

### Bài 7 — Tập rỗng khác tập chứa NULL

Hai truy vấn con sau tác động thế nào đến `IN`?

~~~sql
-- A: truy vấn con trả không hàng.
SELECT department_id
FROM projects
WHERE project_status = 'CANCELLED';

-- B: truy vấn con trả một hàng NULL.
SELECT department_id
FROM projects
WHERE project_id = 106;
~~~

**Đáp án:** với A, `x IN (subquery)` là `FALSE` cho mọi `x` vì tập rỗng. Với B, nếu `x` là một mã phòng ban bất kỳ hoặc `NULL`, không có phép so sánh nào tạo `TRUE`; biểu thức là `UNKNOWN` do phần tử trong truy vấn con là `NULL`. Trong `WHERE`, cả hai trường hợp đều không giữ hàng, nhưng **giá trị logic không giống nhau**.

### Bài 8 — Lọc theo thành phố của phòng ban

Dùng `IN (subquery)` để lấy nhân viên thuộc phòng ban có thành phố `Ha Noi` hoặc `Da Nang`.

**Đáp án:**

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments AS d
    WHERE d.city IN ('Ha Noi', 'Da Nang')
)
ORDER BY e.employee_id;
~~~

Kết quả: **1 An, 2 Binh, 3 Chi, 6 Lan**.

### Bài 9 — NOT EXISTS với nhân viên chưa có phòng

Một yêu cầu là liệt kê nhân viên **không có dự án OPEN khớp phòng ban**, kể cả nhân viên chưa được gán phòng. Hãy viết truy vấn.

**Đáp án:**

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM projects AS p
    WHERE p.project_status = 'OPEN'
      AND p.department_id = e.department_id
)
ORDER BY e.employee_id;
~~~

Kết quả: **4 Dung, 5 Ha**. Ha được chọn vì không tìm được một dự án OPEN có mã phòng ban **khớp bằng `TRUE`** với `NULL` của Ha; đây là quy tắc về sự tồn tại cặp khớp, không phải khẳng định nghiệp vụ rằng Ha chắc chắn không liên quan đến dự án nào.

### Bài 10 — Quyết định IN hay JOIN

Có hai câu hỏi:

1. “Những nhân viên nào thuộc phòng đang có dự án mở?”
2. “Mỗi nhân viên đang làm việc trong phòng có thể được ghép với những dự án mở nào của phòng?”

**Đáp án:** câu 1 thích hợp dùng `IN` hoặc `EXISTS` vì chỉ hỏi có dự án hay không, **mỗi nhân viên một hàng**. Câu 2 cần `JOIN` giữa nhân viên và dự án, vì mỗi cặp nhân viên–dự án là một hàng đầu ra có ý nghĩa; các nhân viên ở phòng có hai dự án sẽ xuất hiện hai hàng.

## 20. Kết luận

`IN (subquery)` là công cụ trực quan khi cần lọc một giá trị theo **tập giá trị trả về từ truy vấn khác**, kể cả tập có nhiều hàng. Với vế trái là một giá trị, truy vấn con thường cung cấp **một cột** cùng kiểu so sánh phù hợp. Giá trị lặp trong subquery **không nhân hàng** ngoài; truy vấn con rỗng khiến `IN` không khớp; còn `NULL` cần được hiểu theo **logic ba giá trị**.

Khi dùng `NOT IN`, phải đặc biệt cẩn trọng nếu truy vấn con hoặc phía ngoài chứa `NULL`: điều kiện có thể là `UNKNOWN` và làm mất những hàng mà người viết tưởng sẽ được chọn. `NOT EXISTS` thường diễn đạt rõ hơn bài toán “không tồn tại hàng liên quan”.

Hãy lựa chọn đúng mức hạt dữ liệu: **`IN`/`EXISTS` khi hỏi tư cách thành viên hoặc tồn tại**, `JOIN` khi cần kết quả cho từng cặp liên quan, `GROUP BY` khi cần tổng hợp. Cuối cùng, dùng alias rõ ràng, tham số hóa đầu vào và đo kế hoạch truy vấn trên dữ liệu thực trước khi đưa ra kết luận về hiệu năng.
