# Tên đầy đủ của đối tượng và cách xác định phạm vi tên

Trong SQL, tên `employees`, `hr.employees`, `e.name` và `company_db.hr.employees` không đơn thuần là các chuỗi ký tự có dấu chấm. Mỗi phần của tên chỉ ra **đối tượng cần truy cập** hoặc **phạm vi để tìm đối tượng đó**. Việc hiểu cách DBMS phân giải tên giúp bạn tránh lỗi “không tìm thấy bảng/cột”, tránh nhầm dữ liệu khi có hai đối tượng trùng tên, và viết các câu truy vấn có nhiều bảng, truy vấn con hoặc CTE một cách rõ ràng.

Bài học tập trung vào **cú pháp và ngữ nghĩa**: khi nào dùng tên ngắn, tên đầy đủ, tên thay thế (alias); DBMS tìm tên theo phạm vi nào; những tên nào có hiệu lực ở từng phần của câu truy vấn. Các lệnh minh họa thực hành chính dùng **PostgreSQL**, đồng thời chỉ ra khác biệt quan trọng với MySQL, SQL Server, Oracle và SQLite.

## 1. Identifier, tên đầy đủ và tên ngắn

**Identifier** là tên do người viết SQL đặt cho đối tượng: bảng, view, schema, cột, alias, hàm, v.v. Ví dụ, `employees` là identifier trong:

```sql
SELECT name FROM employees;
```

**Tên ngắn (unqualified name)** chỉ ghi tên đối tượng: `employees`, `name`. **Tên có định danh phạm vi (qualified name)** thêm một hoặc nhiều phần đứng trước, cách nhau bằng dấu chấm:

```text
hr.employees
│       └── tên bảng
└────────── tên schema

e.name
│ └──────── tên cột
└────────── alias của nguồn dữ liệu trong truy vấn

company_db.hr.employees   -- ví dụ tên ba phần ở DBMS có hỗ trợ
```

Dấu chấm chỉ có ý nghĩa sau khi SQL được phân tích theo **vị trí cú pháp**. Trong `FROM hr.employees`, `hr` có thể là schema. Trong `SELECT e.name`, `e` thường là alias đã khai báo trong `FROM`. Không thể nhìn riêng chuỗi `a.b` rồi kết luận `a` luôn là schema.

**Phân giải tên (name resolution)** là quá trình DBMS gắn mỗi tên xuất hiện trong SQL với một đối tượng, cột hoặc biểu thức hợp lệ. Quá trình phân tích cú pháp và liên kết tên diễn ra trước khi DBMS thực thi các phép đọc/ghi dữ liệu. Nếu tên không tồn tại, có nhiều ứng viên gây mơ hồ, hoặc không nằm trong phạm vi được phép tham chiếu, câu SQL có thể bị từ chối ngay từ lúc chuẩn bị.

### Tên một, hai, ba và bốn phần

| Cách viết | Ví dụ | Ý nghĩa điển hình |
| --- | --- | --- |
| Một phần | `employees` | Tên bảng phụ thuộc database/schema mặc định hoặc đường dẫn tìm kiếm |
| Hai phần | `hr.employees` | Thường là `schema.table`; trong MySQL thường là `database.table` |
| Hai phần trong biểu thức | `e.name` | Cột `name` của nguồn dữ liệu được đặt alias `e` |
| Ba phần | `SalesDB.hr.employees` | `database.schema.table` trong SQL Server |
| Bốn phần | `RemoteServer.SalesDB.hr.employees` | Tên máy chủ liên kết + database + schema + object trong SQL Server |

Bảng chỉ mô tả **cách dùng tiêu biểu**, không phải công thức có thể áp dụng nguyên xi cho mọi DBMS hoặc mọi loại đối tượng.

## 2. Phạm vi tên có nhiều tầng

Hãy hình dung một kết nối SQL có ba lớp ngữ cảnh:

```text
KẾT NỐI / SESSION
  └─ Máy chủ, database đang kết nối, người dùng và cấu hình tìm schema
       └─ KHỐI TRUY VẤN (query block)
            ├─ Nguồn dữ liệu trong FROM và alias của chúng
            ├─ Cột do các nguồn đó cung cấp
            └─ Tên kết quả tạo bằng AS (chỉ dùng ở những vị trí cho phép)
                 └─ KHỐI TRUY VẤN LỒNG NHAU
                      ├─ Tên cục bộ của khối trong
                      └─ Một số tên từ khối ngoài dùng cho tương quan
```

Mỗi lớp trả lời một câu hỏi khác nhau:

- **Phạm vi database/schema:** `FROM employees` trỏ tới bảng nào? `FROM hr.employees` có rõ ràng hơn không?
- **Phạm vi của khối truy vấn:** `name` thuộc bảng `e` hay `d`? Alias `e` có được khai báo trong `FROM` của khối này không?
- **Phạm vi của truy vấn lồng:** Truy vấn con nhìn thấy alias của khối ngoài chứ? Tên nội bộ của truy vấn con có dùng được ở bên ngoài không?
- **Phạm vi của biểu thức đầu ra:** Alias đặt bằng `AS` trong `SELECT` có dùng được ở `WHERE`, `GROUP BY` hay `ORDER BY` không?

Các quy tắc này phụ thuộc **loại tên**, **vị trí cú pháp** và **DBMS**. Không có một “namespace toàn cục” duy nhất cho mọi identifier trong SQL.

## 3. Tên bảng được tìm trong database và schema nào?

Giả sử database thực hành `training_lab` có hai schema:

```text
training_lab
├── hr
│   └── employees
└── archive
    └── employees
```

Hai bảng có thể đều tên `employees` vì nằm trong hai schema khác nhau. Tên `hr.employees` và `archive.employees` chỉ rõ bảng đích. Tên ngắn `employees` cần thêm ngữ cảnh của phiên làm việc.

### PostgreSQL: database hiện tại và `search_path`

PostgreSQL kết nối tới một database cụ thể. Trong database đó, `search_path` quyết định thứ tự tìm một số loại đối tượng khi bạn viết tên không ghi schema.

```sql
SELECT current_database() AS current_database_name,
       current_schema()   AS current_schema_name,
       current_user       AS current_role_name;

SHOW search_path;

SELECT * FROM hr.employees;  -- tên xác định schema
SELECT * FROM employees;     -- tên cần phân giải qua search_path
```

Các lệnh `SELECT` giả định bảng đã tồn tại. Không nên đoán database hiện hành chỉ từ tên một tab trong công cụ quản trị; hãy kiểm tra kết nối thực tế.

Với PostgreSQL, tên ba phần `database.schema.table` chỉ có thể nhắc đến **database hiện đang kết nối**; nó không tạo cơ chế truy vấn trực tiếp một database khác. Muốn truy cập dữ liệu khác database cần kết nối phù hợp hoặc cơ chế được cấu hình riêng, chẳng hạn foreign data wrapper.

### Khác biệt theo hệ quản trị

| DBMS | Nơi tìm bảng khi không ghi đủ tên | Ví dụ tên rõ phạm vi |
| --- | --- | --- |
| PostgreSQL | Database đang kết nối; schema theo `search_path` và các quy tắc hệ thống | `hr.employees` |
| MySQL | Database mặc định của kết nối, thường chọn bằng `USE` | `training_lab.employees` |
| SQL Server | Database hiện tại; schema mặc định của user và các quy tắc phân giải liên quan | `TrainingLab.hr.employees` |
| Oracle Database | Schema gắn với user/ngữ cảnh hiện hành, kể cả khả năng tham chiếu schema khác khi đủ quyền | `HR.EMPLOYEES` |
| SQLite | `main`, `temp` và database gắn bằng `ATTACH` theo quy tắc tìm đối tượng | `main.employees` |

Tên `catalog` theo chuẩn SQL là một tầng định danh phía trên schema, nhưng cách DBMS biểu diễn và hỗ trợ tầng này khác nhau. Đừng mặc định `CREATE SCHEMA` trong MySQL tương đương `CREATE SCHEMA` trong PostgreSQL: MySQL xem `SCHEMA` gần như đồng nghĩa với `DATABASE`.

## 4. Tạo dữ liệu để quan sát cách phân giải tên

Ví dụ sau dành cho **PostgreSQL**. Hãy kết nối tới database học tập nơi bạn có quyền tạo schema. Chạy toàn bộ khối **một lần** trên schema chưa tồn tại; nếu đã có `name_scope_lab`, dùng schema thực hành khác của riêng bạn. Các lệnh này tạo bảng và thêm dữ liệu mẫu.

```sql
CREATE SCHEMA name_scope_lab;

CREATE TABLE name_scope_lab.departments (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE name_scope_lab.employees (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    department_id INTEGER NOT NULL
        REFERENCES name_scope_lab.departments(id),
    manager_id    INTEGER
        REFERENCES name_scope_lab.employees(id),
    salary        NUMERIC(12, 2) NOT NULL
);

INSERT INTO name_scope_lab.departments (id, name)
VALUES (10, 'Engineering'),
       (20, 'Support');

INSERT INTO name_scope_lab.employees
    (id, name, department_id, manager_id, salary)
VALUES
    (1, 'An',   10, NULL, 3000.00),
    (2, 'Binh', 10, 1,    2500.00),
    (3, 'Chi',  20, 1,    2000.00);

SELECT id, name
FROM name_scope_lab.employees
ORDER BY id;
```

Bài thực hành dùng cả hai bảng có cột `id` và `name`. Điều này tạo điều kiện để thấy rõ lỗi mơ hồ khi nối bảng mà chỉ ghi tên cột ngắn.

## 5. Phạm vi tên cột: một bảng và nhiều bảng

Khi một khối truy vấn chỉ có một bảng `FROM`, tên cột không có tiền tố thường đủ rõ:

```sql
SELECT id, name, salary
FROM name_scope_lab.employees
WHERE salary >= 2500;
```

Khi truy vấn nối nhiều bảng, mỗi cột phải được gắn với nguồn tương ứng. Xét câu SQL:

```sql
SELECT id, name
FROM name_scope_lab.employees AS e
JOIN name_scope_lab.departments AS d
  ON e.department_id = d.id;
```

Trong PostgreSQL, câu này bị lỗi **`column reference "id" is ambiguous`** vì cả `e` và `d` đều có cột `id`. Cột `name` cũng gây mơ hồ. Cách viết rõ ràng:

```sql
SELECT e.id,
       e.name AS employee_name,
       d.name AS department_name
FROM name_scope_lab.employees AS e
JOIN name_scope_lab.departments AS d
  ON e.department_id = d.id
ORDER BY e.id;
```

Ở đây:

- `name_scope_lab.employees` là **tên bảng có schema**.
- `AS e` khai báo **alias của bảng** trong khối truy vấn.
- `e.name` là **tham chiếu cột** dựa vào alias `e`.
- `AS employee_name` đặt tên cho **cột kết quả**; nó không đổi tên cột thật trong bảng.

Alias bảng `e` và `d` làm SQL ngắn hơn mà vẫn chính xác. Nếu viết hai bảng cùng có `id`, hãy dùng `e.id` hoặc `d.id` theo đúng ý nghĩa, không dựa vào thứ tự xuất hiện trong `FROM` để phỏng đoán.

### Alias bảng che tên gốc trong cùng khối truy vấn

Trong PostgreSQL, sau khi đặt alias cho một bảng ở `FROM`, những nơi tham chiếu bảng đó trong cùng khối phải dùng alias:

```sql
-- Đúng
SELECT e.name
FROM name_scope_lab.employees AS e;

-- Sai trong PostgreSQL: đã đặt alias e nhưng vẫn tham chiếu tên bảng gốc
SELECT employees.name
FROM name_scope_lab.employees AS e;
```

Alias dùng trong biểu thức SQL **không phải schema**. Ví dụ, `e.name` ở `SELECT` trỏ tới cột `name` của nguồn `e`, trong khi `name_scope_lab.employees` sau `FROM` trỏ tới bảng lưu trữ.

## 6. Alias của cột kết quả có phạm vi riêng

So sánh hai cách dùng `annual_salary`:

```sql
-- Đúng trong PostgreSQL: ORDER BY được dùng alias đầu ra
SELECT e.name,
       e.salary * 12 AS annual_salary
FROM name_scope_lab.employees AS e
ORDER BY annual_salary DESC;

-- Sai: WHERE không tham chiếu được alias kết quả vừa đặt ở SELECT
SELECT e.name,
       e.salary * 12 AS annual_salary
FROM name_scope_lab.employees AS e
WHERE annual_salary > 30000;
```

Cách sửa câu thứ hai:

```sql
SELECT e.name,
       e.salary * 12 AS annual_salary
FROM name_scope_lab.employees AS e
WHERE e.salary * 12 > 30000
ORDER BY annual_salary DESC;
```

Lý do không chỉ là vị trí chữ viết trong câu lệnh. Về **ngữ nghĩa của các mệnh đề**, `WHERE` lọc các hàng nguồn; alias `annual_salary` là tên đầu ra của `SELECT`. PostgreSQL cho phép dùng tên đầu ra trong `ORDER BY` (và một số cách dùng ở `GROUP BY`), nhưng không trong `WHERE` hay `HAVING` theo cách trên. Các DBMS có ngoại lệ khác nhau ở từng mệnh đề, nên viết rõ biểu thức/nguồn dữ liệu khi cần câu lệnh dễ chuyển hệ.

Ví dụ gộp nhóm:

```sql
SELECT d.name AS department_name,
       COUNT(*) AS employee_count
FROM name_scope_lab.employees AS e
JOIN name_scope_lab.departments AS d
  ON e.department_id = d.id
GROUP BY d.id, d.name
ORDER BY employee_count DESC, department_name;
```

`GROUP BY` ghi cột nguồn `d.id`, `d.name`. `ORDER BY` dùng alias đầu ra `employee_count`, `department_name`. Việc một alias đầu ra trùng với tên cột nguồn có thể dẫn tới quy tắc ưu tiên khác nhau giữa `ORDER BY` và `GROUP BY`, vì vậy nên tránh đặt alias gây xung đột tên khi không cần thiết.

## 7. Phạm vi của truy vấn con và truy vấn tương quan

Mỗi khối `SELECT` có phạm vi tên nguồn dữ liệu riêng. Alias khai báo **bên trong** truy vấn con không tự động xuất hiện ở khối **bên ngoài**.

```sql
SELECT filtered.name
FROM (
    SELECT e.name, e.salary
    FROM name_scope_lab.employees AS e
    WHERE e.salary >= 2500
) AS filtered
ORDER BY filtered.salary DESC;
```

- `e` chỉ dùng trong truy vấn con (khối nằm trong ngoặc).
- `filtered` là alias của **bảng dẫn xuất** (derived table) trong truy vấn ngoài.
- Truy vấn ngoài nhìn thấy các cột `name`, `salary` được truy vấn con xuất ra; nó không thể dùng `e.name` từ khối trong.

Một **truy vấn tương quan (correlated subquery)** lại cố ý tham chiếu tên thuộc khối ngoài. Ví dụ tìm nhân viên có lương cao hơn mức trung bình của chính phòng ban:

```sql
SELECT e.name, e.salary, e.department_id
FROM name_scope_lab.employees AS e
WHERE e.salary > (
    SELECT AVG(inner_e.salary)
    FROM name_scope_lab.employees AS inner_e
    WHERE inner_e.department_id = e.department_id
)
ORDER BY e.id;
```

Trong câu trên, `inner_e` thuộc khối truy vấn con; `e.department_id` được tìm trong khối ngoài. Với dữ liệu mẫu, `An` có lương `3000` cao hơn mức trung bình `2750` của phòng Engineering; `Binh` và `Chi` không thỏa điều kiện.

Một quy tắc thực hành tốt là **đặt alias khác nhau cho từng khối khi có tương quan**. Nếu dùng lại `e` trong truy vấn con, alias cục bộ có thể che alias bên ngoài; một điều kiện vốn phải so sánh dữ liệu giữa hai khối có thể vô tình trở thành so sánh trong cùng một khối.

### Khi nào truy vấn con không được thấy tên ngoài?

Không phải mọi vị trí lồng SQL đều tự do tham chiếu cột ở bên ngoài. Trong PostgreSQL, một bảng dẫn xuất thông thường ở `FROM` không được tùy ý đọc cột của các nguồn `FROM` đứng trước; muốn cho phép kiểu phụ thuộc đó, có thể dùng `LATERAL`:

```sql
SELECT d.name AS department_name,
       best.name AS highest_paid_employee
FROM name_scope_lab.departments AS d
LEFT JOIN LATERAL (
    SELECT e.name
    FROM name_scope_lab.employees AS e
    WHERE e.department_id = d.id
    ORDER BY e.salary DESC
    LIMIT 1
) AS best ON TRUE
ORDER BY d.id;
```

Trong ví dụ này, `LATERAL` cho phép truy vấn con ở `FROM` sử dụng `d.id` từ nguồn đứng trước. SQL Server có cú pháp `APPLY` cho nhiều tình huống tương tự; không nên coi `LATERAL` là từ khóa được mọi DBMS hỗ trợ giống nhau.

## 8. Phạm vi tên của CTE với `WITH`

**Common Table Expression (CTE)** gán tên cho một kết quả truy vấn tạm trong phạm vi một câu lệnh. CTE không phải bảng được lưu lâu dài trong schema:

```sql
WITH high_salary_employees AS (
    SELECT e.name, e.salary
    FROM name_scope_lab.employees AS e
    WHERE e.salary >= 2500
)
SELECT h.name
FROM high_salary_employees AS h
ORDER BY h.salary DESC;
```

Tên `high_salary_employees` có hiệu lực trong câu lệnh chứa `WITH`, chứ không tồn tại để câu `SELECT` tiếp theo tự sử dụng. Các cột mà truy vấn ngoài được phép gọi là những cột CTE xuất ra (`name`, `salary`), không phải mọi cột từng có trong bảng gốc.

Một CTE có thể **trùng tên ngắn với bảng thật**, khiến tham chiếu trong `FROM` gắn với CTE thay vì bảng thật ở cùng phạm vi:

```sql
WITH employees AS (
    SELECT name
    FROM name_scope_lab.employees
    WHERE salary >= 2500
)
SELECT name
FROM employees;  -- tên này chỉ CTE của câu lệnh
```

Trong PostgreSQL, `name_scope_lab.employees` vẫn chỉ bảng vật lý, còn `employees` không có tiền tố trong `FROM` của truy vấn chính ở ví dụ này là CTE. Đây là một dạng **che tên (shadowing)**, gần giống việc alias bảng che tên bảng gốc nhưng áp dụng cho một loại tên khác.

CTE cũng có quy tắc phạm vi với CTE khác trong cùng `WITH`, và `WITH RECURSIVE` có quy tắc bổ sung. Không nên suy ra rằng mọi CTE có thể tham chiếu mọi CTE khác bất kể thứ tự khai báo hoặc cú pháp DBMS.

## 9. Dấu nháy và cách viết hoa có thể đổi tên đối tượng

Tên không đặt dấu nháy và tên có dấu nháy không phải lúc nào cũng tương đương.

Trong PostgreSQL, identifier **không quote** được chuyển thành chữ thường. Identifier **đặt trong dấu nháy kép** giữ nguyên chữ hoa/chữ thường:

```sql
-- Ví dụ độc lập để minh họa cú pháp, không cần chạy cùng dữ liệu mẫu
CREATE TABLE name_scope_lab."EmployeeRecords" (
    "EmployeeId" INTEGER PRIMARY KEY
);

SELECT "EmployeeId"
FROM name_scope_lab."EmployeeRecords";
```

`EmployeeRecords` không quote sẽ bị hiểu như `employeerecords` trong PostgreSQL, nên không chỉ đúng bảng vừa tạo. Trong SQL chuẩn, dấu nháy kép dùng để phân biệt identifier có quote; dấu nháy đơn chỉ một giá trị chuỗi như `'An'`.

Cần phân biệt **dấu chấm làm ký hiệu phân tách** với **dấu chấm nằm trong tên đã quote**:

```sql
-- PostgreSQL: schema name_scope_lab, bảng tên là employees
SELECT * FROM name_scope_lab.employees;

-- Đây sẽ là tên MỘT bảng chứa dấu chấm nếu bảng đó được tạo:
-- SELECT * FROM "name_scope_lab.employees";
```

Trường hợp thứ hai là một identifier được quote nguyên khối, không có cùng ý nghĩa với `schema.table`. Trong thực hành, nên dùng identifier chữ thường dạng `snake_case`, như `employee_records` hoặc `department_id`, để hạn chế phải quote.

MySQL thường dùng dấu backtick cho identifier; SQL Server hỗ trợ dấu ngoặc vuông `[Name]` và dấu nháy kép theo cấu hình; các quy tắc phân biệt chữ hoa/chữ thường còn có thể phụ thuộc hệ điều hành hoặc collation. Đừng chuyển nguyên cách quote của một DBMS sang hệ khác khi chưa kiểm tra.

## 10. Phạm vi tên và quyền truy cập là hai vấn đề khác nhau

Tên đầy đủ giúp chỉ đúng đối tượng, nhưng **không tự cấp quyền**. Chẳng hạn `SELECT * FROM name_scope_lab.employees` có thể xác định đúng bảng mà vẫn bị từ chối nếu role đang dùng thiếu quyền truy cập.

Trong PostgreSQL, quyền kết nối database, quyền `USAGE` trên schema và quyền `SELECT` trên bảng là các tầng riêng. Việc thiết lập `search_path` tới một schema không có nghĩa mọi bảng trong schema đó đều đọc được.

Ngược lại, thiếu quyền hoặc hạn chế hiển thị metadata có thể làm khó việc tìm tên đối tượng. Vì vậy khi thấy lỗi, hãy phân biệt:

1. **Sai ngữ cảnh:** kết nối nhầm database hoặc tra sai schema.
2. **Sai tên/phạm vi:** alias không tồn tại, tham chiếu cột mơ hồ, cột ngoài phạm vi, quote sai chữ hoa.
3. **Thiếu quyền:** tìm được đối tượng nhưng không thể thực hiện thao tác.

Tên schema rõ ràng cũng giúp giảm sự phụ thuộc vào `search_path` của phiên. Trong mã có đặc quyền cao, càng cần kiểm soát nguồn của identifier và cấu hình phạm vi tìm kiếm để tránh sử dụng nhầm đối tượng trùng tên ở schema khác.

## 11. Cách kiểm tra DBMS đang phân giải tên ra sao

Với PostgreSQL, có thể làm ba bước sau trước khi sửa SQL:

### Bước 1: Kiểm tra ngữ cảnh kết nối

```sql
SELECT current_database(), current_schema(), current_user;
SHOW search_path;
```

Nếu muốn thử thay đổi cách tìm tên ngắn trong **phiên hiện tại**:

```sql
SET search_path TO name_scope_lab, public;

SELECT name FROM employees ORDER BY id;

RESET search_path;
```

Sau `SET`, `employees` không ghi schema có thể được tìm trong `name_scope_lab` trước. `RESET` trả cấu hình về giá trị mặc định đang áp dụng cho phiên; không nhất thiết mặc định đó luôn là `public`. Lưu ý PostgreSQL còn có quy tắc phân giải riêng cho `pg_catalog`, schema tạm và một số loại đối tượng, nên `search_path` không phải công thức áp dụng giống hệt cho mọi identifier.

### Bước 2: Tra cứu đối tượng trong metadata

```sql
SELECT table_catalog, table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'name_scope_lab'
ORDER BY table_name;

SELECT table_schema, table_name, column_name, ordinal_position
FROM information_schema.columns
WHERE table_schema = 'name_scope_lab'
  AND table_name = 'employees'
ORDER BY ordinal_position;
```

`information_schema` là giao diện metadata dựa trên chuẩn SQL; khả năng hiện đối tượng có thể phụ thuộc quyền người dùng và khác nhau giữa DBMS. Trong PostgreSQL, có thể kiểm tra cách tên bảng được phân giải bằng:

```sql
SELECT to_regclass('name_scope_lab.employees') AS resolved_table;
```

Nếu nhận `NULL`, hãy kiểm tra chính tả, database và tên schema thay vì đoán đối tượng đã bị xóa. `to_regclass` là hàm đặc thù PostgreSQL, không phải SQL chuẩn.

### Bước 3: Thu hẹp câu SQL bị lỗi

Khi một truy vấn nối nhiều bảng bị lỗi mơ hồ, thử thêm alias đầy đủ cho mọi cột dùng chung. Khi một truy vấn con báo không nhận ra alias, xác định alias được khai báo trong **khối SELECT nào**. Khi một câu `WHERE` không nhận ra tên, xác định đó là **cột nguồn** hay **alias đầu ra**.

| Dấu hiệu lỗi | Câu hỏi cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `relation "employees" does not exist` | Có kết nối đúng database? Schema có trong `search_path`? Tên có quote/case đặc biệt? | Thử `name_scope_lab.employees` và kiểm tra metadata |
| `column reference "name" is ambiguous` | Có nhiều nguồn cùng có cột `name`? | Viết `e.name` hoặc `d.name` |
| `missing FROM-clause entry for table "e"` | Alias `e` có được khai báo trong khối đang dùng không? Có bị alias khác thay thế không? | Kiểm tra `FROM` và phạm vi truy vấn ngoài/trong |
| `column "annual_salary" does not exist` trong `WHERE` | `annual_salary` chỉ là alias ở `SELECT`? | Viết lại biểu thức gốc hoặc dùng truy vấn ngoài/CTE |
| `permission denied for schema ...` | Role có quyền `USAGE` trên schema và quyền thao tác trên đối tượng? | Kiểm tra quyền phù hợp; không giải quyết bằng cách đổi tên ngắn |

Thông báo lỗi trong bảng là các dạng thường thấy ở PostgreSQL; DBMS khác có thể dùng mã lỗi và thông điệp khác.

## 12. Tên đầy đủ trong SQL động và ứng dụng

Khi ứng dụng nhận input từ người dùng, **giá trị dữ liệu** và **tên đối tượng SQL** phải được xử lý khác nhau. Một tham số bind dành cho giá trị trong điều kiện, không thay thế được vị trí tên bảng/schema:

```sql
-- PostgreSQL: một prepared statement có tham số giá trị
PREPARE find_employee(integer) AS
SELECT e.id, e.name
FROM name_scope_lab.employees AS e
WHERE e.id = $1;

EXECUTE find_employee(2);
DEALLOCATE find_employee;
```

`$1` ở đây đại diện cho **giá trị id**, không phải identifier. Không nên tạo SQL bằng cách ghép trực tiếp một chuỗi tên bảng do người dùng nhập vào `FROM`. Nếu buộc phải chọn bảng/schema động, ứng dụng cần giới hạn danh sách tên hợp lệ và quote identifier bằng cơ chế an toàn của driver/thư viện cho DBMS cụ thể. Ghi `schema.table` rõ ràng vẫn cần thiết, nhưng nó không thay thế biện pháp xác thực input.

## 13. Bài tập vận dụng

Hãy dùng dữ liệu `name_scope_lab` đã tạo ở mục 4 trong PostgreSQL. Đọc từng yêu cầu, dự đoán cách phân giải tên, rồi mới chạy câu SQL hợp lệ.

**Bài 1 — Tên đầy đủ và tên ngắn.** Chạy `SELECT * FROM name_scope_lab.employees`. Tiếp theo thử `SELECT * FROM employees` trước và sau `SET search_path TO name_scope_lab, public`. Giải thích tại sao tên ngắn phụ thuộc ngữ cảnh, còn tên có schema xác định rõ bảng.

**Bài 2 — Hai cột trùng tên.** Cho câu:

```sql
SELECT name
FROM name_scope_lab.employees AS e
JOIN name_scope_lab.departments AS d
  ON e.department_id = d.id;
```

Vì sao `name` gây lỗi? Hãy sửa để trả về `employee_name` và `department_name`.

**Bài 3 — Phạm vi alias.** Vì sao câu dưới đây sai trong PostgreSQL? Viết lại cho đúng.

```sql
SELECT e.name, e.salary * 12 AS annual_salary
FROM name_scope_lab.employees AS e
WHERE annual_salary >= 30000;
```

**Bài 4 — Truy vấn tương quan.** Trong ví dụ tìm lương cao hơn trung bình phòng ban ở mục 7, chỉ ra alias nào thuộc truy vấn ngoài, alias nào thuộc truy vấn con, và đâu là tham chiếu tạo ra sự tương quan.

**Bài 5 — CTE che tên.** Với `WITH employees AS (...) SELECT ... FROM employees`, tên `employees` ở `FROM` cuối cùng trỏ tới đâu? Nếu muốn đọc bảng vật lý thì viết thế nào?

### Gợi ý đáp án

- **Bài 1:** Tên `name_scope_lab.employees` chỉ rõ schema và bảng của database đang kết nối; `employees` cần `search_path` có schema phù hợp hoặc một đối tượng cùng tên ở nơi khác.
- **Bài 2:** Cả `e` và `d` đều có cột `name`. Viết `SELECT e.name AS employee_name, d.name AS department_name ...`.
- **Bài 3:** `annual_salary` là alias đầu ra của `SELECT`, không phải tên cột nguồn trong `WHERE`. Thay bằng `WHERE e.salary * 12 >= 30000`; `ORDER BY annual_salary` vẫn dùng được.
- **Bài 4:** `e` thuộc khối ngoài, `inner_e` thuộc khối trong, và `inner_e.department_id = e.department_id` liên hệ các hàng của hai phạm vi.
- **Bài 5:** `employees` không có tiền tố đang chỉ CTE trong câu lệnh; `name_scope_lab.employees` chỉ bảng vật lý.

Khi đọc một câu SQL khó, hãy xác định theo thứ tự: **tên xuất hiện ở mệnh đề nào → tên thuộc loại gì (bảng, cột, alias, CTE) → phạm vi gần nhất khai báo tên đó → database/schema nào được dùng nếu cần tra đối tượng lưu trữ**. Cách đọc này giúp phân biệt lỗi cú pháp với lỗi phân giải tên và với lỗi quyền truy cập.
