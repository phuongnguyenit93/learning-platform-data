# Tự kết nối bảng và quan hệ phân cấp đơn giản trong PostgreSQL

Trong cơ sở dữ liệu quan hệ, không phải lúc nào hai thực thể có quan hệ cũng nằm trong hai bảng khác nhau. Một nhân viên có thể báo cáo cho **một nhân viên khác trong cùng bảng**; một danh mục có thể thuộc về **một danh mục cha cũng ở cùng bảng**; một bình luận có thể trả lời một bình luận khác. PostgreSQL cho phép biểu diễn các trường hợp này bằng **khóa ngoại tự tham chiếu** (*self-referencing foreign key*) và khai thác chúng qua **self join** (*tự kết nối bảng*).

Bài học tập trung vào cách dùng `JOIN` với nhiều bí danh của cùng một bảng, phân biệt `INNER JOIN` và `LEFT JOIN`, truy vấn quan hệ cha–con một cấp, hai cấp và nhiều cấp, đếm cấp dưới, tìm nút gốc/nút lá. Khi độ sâu cây không cố định, bài học giới thiệu `WITH RECURSIVE` như bước mở rộng tự nhiên của phép tự kết nối.

## 1. Self join là gì?

**Self join không phải từ khóa SQL mới.** Đó là việc sử dụng một bảng ở **hai hoặc nhiều vai trò** trong cùng câu `JOIN`. Mỗi vai trò cần một alias để nhận biết cột nào đến từ bản ghi con và cột nào đến từ bản ghi cha.

Giả sử bảng `employees`:

| employee_id | full_name | manager_id |
| ---: | --- | ---: |
| 1 | Linh | NULL |
| 2 | An | 1 |
| 3 | Binh | 1 |
| 4 | Chi | 2 |
| 5 | Dung | 2 |

Các giá trị `manager_id` tham chiếu lại `employee_id`:

- Linh không có quản lý, nên `manager_id IS NULL`.
- An và Binh báo cáo cho Linh.
- Chi và Dung báo cáo cho An.

~~~mermaid
flowchart TD
    L["Linh (1)"] --> A["An (2)"]
    L --> B["Binh (3)"]
    A --> C["Chi (4)"]
    A --> D["Dung (5)"]
~~~

Muốn hiển thị tên quản lý bên cạnh tên nhân viên:

~~~sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    m.full_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON m.employee_id = e.manager_id;
~~~

`e` và `m` **không phải hai bảng khác nhau**: cả hai đều đọc `employees` nhưng đảm nhiệm hai vai trò logic. Điều kiện `m.employee_id = e.manager_id` kết nối một nhân viên với hàng quản lý tương ứng.

## 2. Khóa ngoại tự tham chiếu khác self join như thế nào?

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| Self-referencing foreign key | Ràng buộc tính hợp lệ của dữ liệu được lưu | `manager_id REFERENCES employees(employee_id)` |
| Self join | Kết hợp hai vai trò của cùng bảng trong kết quả truy vấn | `employees e JOIN employees m ON ...` |
| Adjacency list | Mô hình lưu dữ liệu phân cấp bằng cột parent | `employee_id` và `manager_id` |
| Recursive CTE | Truy vấn quan hệ qua số cấp không biết trước | `WITH RECURSIVE hierarchy AS (...)` |

Một self join có thể được thực hiện ngay cả khi chưa khai báo foreign key. Tuy nhiên, khi không có FK, database có thể chứa `manager_id` trỏ đến một nhân viên không tồn tại.

Ngược lại, bảng có FK tự tham chiếu không bắt buộc mọi query đều dùng self join. Nếu chỉ muốn tìm các nhân viên có `manager_id = 1`, câu `WHERE manager_id = 1` đã đủ.

## 3. Chuẩn bị môi trường thực hành

Các ví dụ chạy trong một database **thực hành riêng**, chẳng hạn `pg_hierarchy_lab`. Script bên dưới xóa schema `hier_lab` để tạo lại dữ liệu mẫu: **không chạy trên database chứa dữ liệu thật hoặc schema dùng chung**.

### 3.1. Dựng bảng nhân viên

~~~sql
-- Chỉ chạy trong database dành riêng cho thực hành.
DROP SCHEMA IF EXISTS hier_lab CASCADE;
CREATE SCHEMA hier_lab;

CREATE TABLE hier_lab.employees (
    employee_id integer PRIMARY KEY,
    full_name text NOT NULL,
    department text NOT NULL,
    manager_id integer NULL,

    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id)
        REFERENCES hier_lab.employees(employee_id)
        ON DELETE SET NULL,

    CONSTRAINT chk_no_direct_self_manager
        CHECK (
            manager_id IS NULL
            OR manager_id <> employee_id
        )
);

CREATE INDEX idx_employees_manager
    ON hier_lab.employees(manager_id);
~~~

Giải thích:

- `employee_id PRIMARY KEY` định danh một hàng nhân viên.
- `manager_id` có cùng kiểu `integer`, lưu ID của quản lý trực tiếp.
- `manager_id NULL` cho phép tồn tại nhân viên ở cấp cao nhất.
- Khóa ngoại `fk_employee_manager` đảm bảo ID quản lý khác NULL phải tồn tại trong `employees`.
- `ON DELETE SET NULL` là chính sách **minh họa**, nghĩa là xóa quản lý sẽ bỏ liên kết trực tiếp của nhân viên dưới quyền. Nó không mặc định phù hợp với hệ thống nhân sự thật.
- `CHECK` ngăn một nhân viên tự tham chiếu **trực tiếp** tới bản thân.
- Index `idx_employees_manager` hỗ trợ tìm các nhân viên có cùng `manager_id`.

**Cảnh báo:** khóa ngoại và `CHECK(manager_id <> employee_id)` không ngăn một chu trình dài như A → B → C → A. Các bất biến trên nhiều hàng cần cơ chế kiểm soát bổ sung.

### 3.2. Nạp dữ liệu theo thứ tự cha trước con

~~~sql
INSERT INTO hier_lab.employees
    (employee_id, full_name, department, manager_id)
VALUES
    (1, 'Linh', 'Engineering', NULL),
    (7, 'Giang', 'Operations', NULL);

INSERT INTO hier_lab.employees
    (employee_id, full_name, department, manager_id)
VALUES
    (2, 'An',   'Engineering', 1),
    (3, 'Binh', 'Sales',       1),
    (8, 'Hoa',  'Operations',  7);

INSERT INTO hier_lab.employees
    (employee_id, full_name, department, manager_id)
VALUES
    (4, 'Chi',  'Engineering', 2),
    (5, 'Dung', 'Engineering', 2),
    (6, 'Em',   'Sales',       3);

INSERT INTO hier_lab.employees
    (employee_id, full_name, department, manager_id)
VALUES
    (9, 'Khang', 'Engineering', 5);
~~~

Dữ liệu đầy đủ:

| ID | Nhân viên | manager_id | Phòng ban |
| ---: | --- | ---: | --- |
| 1 | Linh | NULL | Engineering |
| 2 | An | 1 | Engineering |
| 3 | Binh | 1 | Sales |
| 4 | Chi | 2 | Engineering |
| 5 | Dung | 2 | Engineering |
| 6 | Em | 3 | Sales |
| 7 | Giang | NULL | Operations |
| 8 | Hoa | 7 | Operations |
| 9 | Khang | 5 | Engineering |

~~~mermaid
flowchart TD
    L["Linh (1)"] --> A["An (2)"]
    L --> B["Binh (3)"]
    A --> C["Chi (4)"]
    A --> D["Dung (5)"]
    D --> K["Khang (9)"]
    B --> E["Em (6)"]
    G["Giang (7)"] --> H["Hoa (8)"]
~~~

Đây là **rừng (forest)** gồm hai cây, vì có hai nút gốc Linh và Giang. Foreign key tự tham chiếu không bắt buộc toàn bảng chỉ được có một root.

Đọc lại:

~~~sql
SELECT employee_id, full_name, manager_id
FROM hier_lab.employees
ORDER BY employee_id;
~~~

Dữ liệu mẫu không phụ thuộc vào đồng hồ, ngẫu nhiên hay giá trị identity, giúp kết quả trong bài tái lập được.

## 4. Lấy nhân viên và quản lý bằng LEFT SELF JOIN

~~~sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    e.manager_id,
    m.full_name AS manager_name
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
~~~

Kết quả:

| employee_id | employee_name | manager_id | manager_name |
| ---: | --- | ---: | --- |
| 1 | Linh | NULL | NULL |
| 2 | An | 1 | Linh |
| 3 | Binh | 1 | Linh |
| 4 | Chi | 2 | An |
| 5 | Dung | 2 | An |
| 6 | Em | 3 | Binh |
| 7 | Giang | NULL | NULL |
| 8 | Hoa | 7 | Giang |
| 9 | Khang | 5 | Dung |

### Vì sao phải dùng LEFT JOIN?

`LEFT JOIN` giữ **mọi hàng ở phía nhân viên `e`**. Khi `e.manager_id` là NULL, biểu thức `m.employee_id = e.manager_id` không tìm thấy quản lý tương ứng, nên `m.full_name` là NULL nhưng nhân viên vẫn được trả về.

Nếu thay bằng `INNER JOIN`:

~~~sql
SELECT
    e.full_name AS employee,
    m.full_name AS manager
FROM hier_lab.employees AS e
INNER JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
~~~

thì Linh và Giang không xuất hiện. Với dữ liệu mẫu:

- `INNER JOIN`: **7 hàng** (nhân viên có quản lý).
- `LEFT JOIN`: **9 hàng** (tất cả nhân viên).

Hai cách đều đúng tùy câu hỏi. “Danh sách mọi nhân viên kèm quản lý nếu có” cần `LEFT JOIN`; “chỉ người đã có quản lý” có thể dùng `INNER JOIN`.

## 5. Tại sao alias là phần không thể thiếu?

Trong self join, alias cho biết vai trò của mỗi lần tham chiếu bảng:

~~~sql
FROM hier_lab.employees AS employee
LEFT JOIN hier_lab.employees AS manager
    ON manager.employee_id = employee.manager_id
~~~

Ở đây tên `employee` và `manager` không phải schema/table mới, mà là bí danh trong phạm vi câu truy vấn.

Một lỗi rất dễ mắc:

~~~sql
-- Sai ngữ nghĩa: nhân viên ghép với chính mình.
ON manager.employee_id = employee.employee_id
~~~

Điều kiện đó có thể trả kết quả trông “đẹp” vì khóa chính của mỗi nhân viên luôn khớp chính nó, nhưng `manager_name` sẽ trở thành tên nhân viên, không phải tên quản lý.

Đúng:

~~~sql
ON manager.employee_id = employee.manager_id
~~~

Nếu có thêm cấp, dùng alias phân biệt `e`, `m` và `gm` hoặc `child`, `parent` và `grandparent`. Với truy vấn dài, tên theo vai trò thường dễ kiểm tra hơn các alias vô nghĩa như `a`, `b`, `c`.

## 6. Tìm cấp dưới trực tiếp của một quản lý

Truy vấn từ phía quản lý sang nhân viên dưới quyền:

~~~sql
SELECT
    manager.employee_id AS manager_id,
    manager.full_name AS manager_name,
    employee.employee_id AS report_id,
    employee.full_name AS report_name
FROM hier_lab.employees AS manager
JOIN hier_lab.employees AS employee
    ON employee.manager_id = manager.employee_id
WHERE manager.employee_id = 1
ORDER BY employee.employee_id;
~~~

Kết quả:

| manager_name | report_id | report_name |
| --- | ---: | --- |
| Linh | 2 | An |
| Linh | 3 | Binh |

Đó là **cấp dưới trực tiếp** của Linh. Chi, Dung, Em và Khang cũng nằm trong tổ chức dưới Linh nhưng không trực tiếp báo cáo cho Linh.

Nếu chỉ cần ID và tên của cấp dưới, không cần thông tin quản lý từ bảng ở vai trò thứ hai:

~~~sql
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 1
ORDER BY employee_id;
~~~

Câu này đơn giản hơn và đúng mục tiêu. **Không nên JOIN chỉ để có JOIN.** Chọn self join khi kết quả thực sự cần thông tin từ hai vai trò hoặc một điều kiện so sánh giữa chúng.

## 7. Tìm root: các nút không có cha

Trong adjacency list, root thường có `manager_id IS NULL`:

~~~sql
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id IS NULL
ORDER BY employee_id;
~~~

Kết quả là Linh (1) và Giang (7).

`WHERE manager_id = NULL` là sai vì trong SQL phép so sánh với NULL không trả TRUE. Phải dùng `IS NULL`.

### Có thể dùng self join để tìm root không?

~~~sql
SELECT e.employee_id, e.full_name
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
WHERE m.employee_id IS NULL
ORDER BY e.employee_id;
~~~

Nếu FK hợp lệ, kết quả giống truy vấn `WHERE e.manager_id IS NULL`. Nhưng hai truy vấn có điểm khác trong một bảng **không có FK**:

- `e.manager_id IS NULL` tìm những bản ghi **không khai báo cha**.
- `m.employee_id IS NULL` sau LEFT JOIN còn có thể tìm bản ghi có ID cha **không tồn tại** (*orphan*).

Vì vậy, khi yêu cầu “nút gốc”, dùng điều kiện trực tiếp `manager_id IS NULL` thường rõ nghĩa hơn. Khi chẩn đoán dữ liệu mồ côi, dùng LEFT JOIN kèm điều kiện phân biệt.

## 8. Tìm leaf: nhân viên không quản lý ai

Leaf là nút **không có con trực tiếp**. Dùng self join:

~~~sql
SELECT
    manager.employee_id,
    manager.full_name
FROM hier_lab.employees AS manager
LEFT JOIN hier_lab.employees AS report
    ON report.manager_id = manager.employee_id
WHERE report.employee_id IS NULL
ORDER BY manager.employee_id;
~~~

Kết quả:

| ID | Nhân viên |
| ---: | --- |
| 4 | Chi |
| 6 | Em |
| 8 | Hoa |
| 9 | Khang |

Dung không phải leaf vì quản lý Khang.

Có thể dùng `NOT EXISTS` để biểu diễn điều kiện “không có con”:

~~~sql
SELECT
    e.employee_id,
    e.full_name
FROM hier_lab.employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM hier_lab.employees AS child
    WHERE child.manager_id = e.employee_id
)
ORDER BY e.employee_id;
~~~

Hai truy vấn trả cùng tập kết quả với dữ liệu mẫu. `NOT EXISTS` diễn đạt rất rõ yêu cầu tồn tại, còn `LEFT JOIN ... IS NULL` thuận tiện khi người học đang làm việc với các kiểu JOIN.

**Root không đồng nghĩa với leaf.** Một cây chỉ có một nút khiến nút đó vừa là root vừa là leaf. Trong dữ liệu mẫu, hai root đều có con nên không phải leaf.

## 9. Đếm cấp dưới trực tiếp bằng self join

~~~sql
SELECT
    manager.employee_id,
    manager.full_name AS manager_name,
    COUNT(report.employee_id) AS direct_report_count
FROM hier_lab.employees AS manager
LEFT JOIN hier_lab.employees AS report
    ON report.manager_id = manager.employee_id
GROUP BY manager.employee_id, manager.full_name
ORDER BY manager.employee_id;
~~~

Kết quả:

| ID | manager_name | direct_report_count |
| ---: | --- | ---: |
| 1 | Linh | 2 |
| 2 | An | 2 |
| 3 | Binh | 1 |
| 4 | Chi | 0 |
| 5 | Dung | 1 |
| 6 | Em | 0 |
| 7 | Giang | 1 |
| 8 | Hoa | 0 |
| 9 | Khang | 0 |

### Tại sao COUNT(report.employee_id), không phải COUNT(*)?

Với `LEFT JOIN`, một quản lý không có nhân viên vẫn tạo **một hàng kết quả** mà các cột `report` là NULL. `COUNT(*)` đếm cả hàng đó, nên có thể trả 1 cho người không có cấp dưới. `COUNT(report.employee_id)` bỏ qua NULL và cho kết quả 0 như mong muốn.

Phân biệt:

- `direct_report_count` = số con trực tiếp.
- `total_descendant_count` = số người nằm dưới ở **mọi độ sâu**.

Linh có 2 con trực tiếp nhưng **6 hậu duệ** (An, Binh, Chi, Dung, Em, Khang). Muốn đếm mọi hậu duệ cần duyệt nhiều cấp.

## 10. Tìm hai nhân viên cùng quản lý

Trong cây, hai nút cùng cha thường được gọi là **siblings**. Ta dùng self join với hai alias đều là nhân viên:

~~~sql
SELECT
    a.employee_id AS first_id,
    a.full_name AS first_employee,
    b.employee_id AS second_id,
    b.full_name AS second_employee,
    a.manager_id
FROM hier_lab.employees AS a
JOIN hier_lab.employees AS b
    ON a.manager_id = b.manager_id
   AND a.employee_id < b.employee_id
WHERE a.manager_id IS NOT NULL
ORDER BY a.manager_id, a.employee_id, b.employee_id;
~~~

Kết quả:

| first_employee | second_employee | manager_id |
| --- | --- | ---: |
| An | Binh | 1 |
| Chi | Dung | 2 |

Điều kiện `a.employee_id < b.employee_id` vừa ngăn ghép một nhân viên với chính mình, vừa tránh trả cùng một cặp ở hai chiều (An, Binh) và (Binh, An). Nếu chỉ viết `a.employee_id <> b.employee_id`, cặp có thể xuất hiện **hai lần** theo thứ tự đảo ngược.

`WHERE a.manager_id IS NOT NULL` làm rõ rằng siblings phải có một quản lý thực sự. Hai root có `manager_id NULL` vốn không khớp nhau qua toán tử `=`, vì SQL không coi `NULL = NULL` là TRUE.

### Tìm các nhân viên thuộc cùng phòng ban có cùng quản lý

Có thể mở rộng:

~~~sql
SELECT a.full_name, b.full_name, a.department
FROM hier_lab.employees AS a
JOIN hier_lab.employees AS b
    ON a.manager_id = b.manager_id
   AND a.department = b.department
   AND a.employee_id < b.employee_id
WHERE a.manager_id IS NOT NULL
ORDER BY a.employee_id, b.employee_id;
~~~

Với dữ liệu mẫu, Chi và Dung thuộc Engineering và cùng quản lý An. An thuộc Engineering nhưng Binh thuộc Sales nên cặp An–Binh không xuất hiện trong truy vấn bổ sung điều kiện phòng ban.

## 11. Self join hai lần: lấy quản lý và quản lý cấp trên

Khi muốn truy vấn **hai cấp cố định**, sử dụng ba alias:

~~~sql
SELECT
    employee.employee_id,
    employee.full_name AS employee_name,
    manager.full_name AS manager_name,
    grand_manager.full_name AS grand_manager_name
FROM hier_lab.employees AS employee
LEFT JOIN hier_lab.employees AS manager
    ON manager.employee_id = employee.manager_id
LEFT JOIN hier_lab.employees AS grand_manager
    ON grand_manager.employee_id = manager.manager_id
ORDER BY employee.employee_id;
~~~

Một số kết quả:

| employee | manager | grand_manager |
| --- | --- | --- |
| Linh | NULL | NULL |
| An | Linh | NULL |
| Chi | An | Linh |
| Dung | An | Linh |
| Em | Binh | Linh |
| Khang | Dung | An |
| Giang | NULL | NULL |
| Hoa | Giang | NULL |

Vì mỗi cấp dùng `LEFT JOIN`, các nút chỉ có một cấp hoặc không có quản lý vẫn được giữ.

Nếu dùng `INNER JOIN` ở cấp `grand_manager`, nhiều nhân viên bị loại dù họ hoàn toàn hợp lệ — đơn giản vì họ không có đủ hai cấp quản lý phía trên.

### Ba cấp cố định

Đối với Khang:

~~~sql
SELECT
    e.full_name AS employee_name,
    m.full_name AS manager_name,
    gm.full_name AS grand_manager_name,
    t.full_name AS third_level_manager_name
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
LEFT JOIN hier_lab.employees AS gm
    ON gm.employee_id = m.manager_id
LEFT JOIN hier_lab.employees AS t
    ON t.employee_id = gm.manager_id
WHERE e.employee_id = 9;
~~~

Kết quả: **Khang → Dung → An → Linh**.

Cách này dễ hiểu nếu yêu cầu thật sự cố định “lấy tối đa ba quản lý phía trên”. Nhưng nếu tổ chức có thể có hai, năm hoặc mười cấp, không nên thêm vô hạn alias; hãy dùng đệ quy.

## 12. Bảng quyết định: khi nào self join là đủ?

| Yêu cầu | Gợi ý |
| --- | --- |
| Tên cha trực tiếp | `LEFT JOIN` cùng bảng |
| Tất cả con trực tiếp của một ID | `WHERE parent_id = ?` |
| Các node không có cha | `WHERE parent_id IS NULL` |
| Các node không có con | `NOT EXISTS` hoặc `LEFT JOIN ... IS NULL` |
| Đếm con trực tiếp | `LEFT JOIN` + `COUNT(child.id)` |
| Các cặp có cùng cha | Self join hai alias child |
| Cha và ông/bà (hai cấp) | Hai self join |
| Mọi tổ tiên hoặc hậu duệ, cây sâu không cố định | `WITH RECURSIVE` |
| Tổng số người dưới một quản lý ở mọi cấp | Recursive CTE + `COUNT` |
| Kiểm tra toàn bộ đồ thị có cycle không | Quy trình kiểm chứng phân cấp riêng |

Một phép tự JOIN đi **một cạnh** quan hệ. Nối thêm một alias đi thêm một cấp; recursive CTE lặp lại quy tắc kết nối theo dữ liệu.

## 13. Giới hạn khi tự JOIN nhiều cấp

Giả sử cấu trúc tổ chức:

~~~text
CEO
 └── VP
     └── Director
         └── Manager
             └── Team Lead
                 └── Engineer
~~~

Một truy vấn có ba self join chỉ nhìn thấy tối đa ba cấp phía trên Engineer. Nếu sau này có tầng thứ bảy, phải sửa câu SQL. Một số điểm bất tiện:

- Cần nhiều alias, dễ nhầm điều kiện `ON`.
- Số cột được tạo cố định: `parent_1`, `parent_2`, `parent_3`...
- Không lấy được mọi hậu duệ khi độ sâu chưa biết trước.
- Không thuận tiện để tính chiều cao nhánh hoặc sinh đường dẫn đầy đủ.
- Không tự có cơ chế phát hiện vòng lặp trong dữ liệu.

PostgreSQL cung cấp **recursive common table expression (CTE)** để giải quyết bài toán đi qua số cạnh biến thiên của một quan hệ tự tham chiếu.

## 14. WITH RECURSIVE: duyệt từ root xuống mọi cấp

Recursive CTE có hai phần:

1. **Anchor:** chọn các nút xuất phát, ví dụ các root `manager_id IS NULL`.
2. **Recursive term:** từ những nút tìm được, tự JOIN với bảng nhân viên để lấy con trực tiếp, rồi tiếp tục lặp.

~~~mermaid
flowchart TD
    A["Anchor: nút gốc"] --> B["Tập nút hiện tại"]
    B --> C["JOIN tìm các nút con"]
    C --> D{"Có nút con mới?"}
    D -->|"Có"| B
    D -->|"Không"| E["Hoàn thành tập kết quả"]
~~~

Truy vấn:

~~~sql
WITH RECURSIVE employee_tree AS (
    -- Anchor: mọi nhân viên không có quản lý.
    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        0 AS depth,
        ARRAY[e.employee_id] AS path_ids
    FROM hier_lab.employees AS e
    WHERE e.manager_id IS NULL

    UNION ALL

    -- Tìm các nhân viên có quản lý ở cấp đã biết.
    SELECT
        child.employee_id,
        child.full_name,
        child.manager_id,
        parent.depth + 1,
        parent.path_ids || child.employee_id
    FROM hier_lab.employees AS child
    JOIN employee_tree AS parent
        ON child.manager_id = parent.employee_id
    WHERE NOT child.employee_id = ANY(parent.path_ids)
)
SELECT
    employee_id,
    full_name,
    manager_id,
    depth,
    path_ids
FROM employee_tree
ORDER BY path_ids;
~~~

Giải thích:

- `depth = 0` cho root, mỗi lần đi xuống con tăng 1.
- `path_ids` là mảng các `employee_id` từ root tới nút hiện tại.
- `UNION ALL` ghép kết quả anchor với các vòng đệ quy, không tự loại các hàng lặp.
- `NOT child.employee_id = ANY(parent.path_ids)` tránh đi lại một ID đã nằm trên đường đi hiện tại; đây là cách phòng vòng lặp khi truy vấn một nhánh.
- `ORDER BY path_ids` giúp đầu ra có thứ tự theo đường dẫn ID. Không phụ thuộc vào thứ tự vật lý của bảng.

Kết quả về độ sâu:

| ID | Nhân viên | depth |
| ---: | --- | ---: |
| 1 | Linh | 0 |
| 2 | An | 1 |
| 3 | Binh | 1 |
| 4 | Chi | 2 |
| 5 | Dung | 2 |
| 6 | Em | 2 |
| 7 | Giang | 0 |
| 8 | Hoa | 1 |
| 9 | Khang | 3 |

**Thứ tự xuất kết quả không tự được bảo đảm bởi bản thân đệ quy**; khi cần thứ tự hiển thị có ý nghĩa, dùng `ORDER BY` ở truy vấn cuối.

### Giới hạn của cơ chế chặn cycle bằng path

Điều kiện mảng đường dẫn chỉ ngăn quay lại **một nút đã nằm trên cùng đường đi**. Nó không xóa cycle đã có trong dữ liệu. Hơn nữa, một tập nút tạo vòng nhưng **không nối với root** sẽ không được nhìn thấy khi anchor chỉ lấy root. Muốn kiểm tra toàn bộ đồ thị cần logic chẩn đoán riêng.

## 15. Truy vấn toàn bộ nhánh của một nhân viên

Lấy tất cả nhân viên nằm dưới An (ID 2). Đặt anchor là chính An:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT
        employee_id,
        full_name,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE employee_id = 2

    UNION ALL

    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        s.depth + 1,
        s.path_ids || e.employee_id
    FROM hier_lab.employees AS e
    JOIN subtree AS s
        ON e.manager_id = s.employee_id
    WHERE NOT e.employee_id = ANY(s.path_ids)
)
SELECT employee_id, full_name, depth
FROM subtree
ORDER BY depth, employee_id;
~~~

Kết quả:

| ID | Nhân viên | depth tính từ An |
| ---: | --- | ---: |
| 2 | An | 0 |
| 4 | Chi | 1 |
| 5 | Dung | 1 |
| 9 | Khang | 2 |

Nếu muốn **chỉ hậu duệ**, loại anchor ở truy vấn cuối:

~~~sql
-- Đặt trong cùng câu WITH RECURSIVE ... SELECT.
SELECT employee_id, full_name, depth
FROM subtree
WHERE depth > 0
ORDER BY depth, employee_id;
~~~

Tên CTE `subtree` chỉ tồn tại trong **một câu SQL**. Không thể chạy riêng câu `SELECT FROM subtree` ở phiên lệnh tiếp theo nếu không viết lại CTE hoặc đóng gói vào view/function.

## 16. Đếm tổng hậu duệ, không chỉ con trực tiếp

Để tính tổng toàn bộ nhân viên nằm dưới Linh (ID 1):

~~~sql
WITH RECURSIVE branch AS (
    SELECT
        employee_id,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE employee_id = 1

    UNION ALL

    SELECT
        e.employee_id,
        e.manager_id,
        b.depth + 1,
        b.path_ids || e.employee_id
    FROM hier_lab.employees AS e
    JOIN branch AS b
        ON e.manager_id = b.employee_id
    WHERE NOT e.employee_id = ANY(b.path_ids)
)
SELECT COUNT(*) AS total_descendants
FROM branch
WHERE depth > 0;
~~~

Kết quả: **6**, gồm An, Binh, Chi, Dung, Em và Khang.

Trong khi đó:

~~~sql
SELECT COUNT(*) AS direct_reports
FROM hier_lab.employees
WHERE manager_id = 1;
~~~

trả **2**. Đây là hai thước đo khác nhau. Trong báo cáo tổ chức cần thống nhất “số cấp dưới” đang nghĩa là cấp dưới trực tiếp hay tất cả hậu duệ.

## 17. Tìm mọi tổ tiên từ một nhân viên lên root

Đệ quy cũng có thể đi **ngược hướng**, từ bản ghi con tới cha:

~~~sql
WITH RECURSIVE manager_chain AS (
    SELECT
        employee_id,
        full_name,
        manager_id,
        0 AS steps_up,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE employee_id = 9

    UNION ALL

    SELECT
        m.employee_id,
        m.full_name,
        m.manager_id,
        c.steps_up + 1,
        c.path_ids || m.employee_id
    FROM hier_lab.employees AS m
    JOIN manager_chain AS c
        ON m.employee_id = c.manager_id
    WHERE NOT m.employee_id = ANY(c.path_ids)
)
SELECT employee_id, full_name, steps_up
FROM manager_chain
ORDER BY steps_up;
~~~

Kết quả:

| ID | Nhân viên | steps_up |
| ---: | --- | ---: |
| 9 | Khang | 0 |
| 5 | Dung | 1 |
| 2 | An | 2 |
| 1 | Linh | 3 |

Ta thấy đường đi: **Khang → Dung → An → Linh**. Một self join hai cấp sẽ chỉ trả được Dung và An; recursive CTE đi tới khi không còn quản lý phía trên.

### Truy vấn gốc của một nhánh

Nếu chỉ cần root của Khang, có thể thêm vào SELECT cuối:

~~~sql
-- Trong cùng câu WITH RECURSIVE manager_chain AS (...):
SELECT employee_id, full_name
FROM manager_chain
WHERE manager_id IS NULL;
~~~

Với dữ liệu hợp lệ, câu này tìm Linh. Nếu dữ liệu mồ côi hoặc có cycle, chuỗi có thể không tới được một root, vì vậy kết quả rỗng không nhất thiết có nghĩa nhân viên “không tồn tại”.

## 18. Xây dựng đường dẫn hiển thị của cây

Một ứng dụng thường muốn hiển thị đường dẫn như:

~~~text
Linh > An > Dung > Khang
~~~

Ta có thể mở rộng recursive CTE:

~~~sql
WITH RECURSIVE employee_paths AS (
    SELECT
        employee_id,
        full_name,
        manager_id,
        0 AS depth,
        full_name::text AS display_path,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE manager_id IS NULL

    UNION ALL

    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        p.depth + 1,
        p.display_path || ' > ' || e.full_name,
        p.path_ids || e.employee_id
    FROM hier_lab.employees AS e
    JOIN employee_paths AS p
        ON e.manager_id = p.employee_id
    WHERE NOT e.employee_id = ANY(p.path_ids)
)
SELECT employee_id, full_name, depth, display_path
FROM employee_paths
ORDER BY path_ids;
~~~

Một số dòng mong đợi:

~~~text
Linh
Linh > An
Linh > An > Chi
Linh > An > Dung
Linh > An > Dung > Khang
Linh > Binh
Linh > Binh > Em
Giang
Giang > Hoa
~~~

`display_path` dùng để **hiển thị**, còn `path_ids` dùng khóa ổn định để xác định các nút đã đi qua và tránh cycle trong đường hiện tại. Không nên dùng tên làm khóa định danh vì hai nhân viên có thể trùng tên hoặc thay đổi tên.

## 19. Danh mục sản phẩm: ví dụ tự tham chiếu khác

Quan hệ phân cấp bằng self join cũng xuất hiện ở danh mục sản phẩm:

~~~sql
CREATE TABLE hier_lab.categories (
    category_id integer PRIMARY KEY,
    category_name text NOT NULL,
    parent_id integer NULL
        REFERENCES hier_lab.categories(category_id)
        ON DELETE RESTRICT,
    CHECK (parent_id IS NULL OR parent_id <> category_id)
);

CREATE INDEX idx_categories_parent
ON hier_lab.categories(parent_id);
~~~

Nạp dữ liệu:

~~~sql
INSERT INTO hier_lab.categories
    (category_id, category_name, parent_id)
VALUES (10, 'Products', NULL);

INSERT INTO hier_lab.categories
    (category_id, category_name, parent_id)
VALUES
    (11, 'Electronics', 10),
    (12, 'Books', 10);

INSERT INTO hier_lab.categories
    (category_id, category_name, parent_id)
VALUES
    (13, 'Phones', 11),
    (14, 'Laptops', 11),
    (15, 'Fiction', 12),
    (16, 'Nonfiction', 12);

INSERT INTO hier_lab.categories
    (category_id, category_name, parent_id)
VALUES (17, 'Smartphones', 13);
~~~

Sơ đồ:

~~~mermaid
flowchart TD
    P["Products (10)"] --> E["Electronics (11)"]
    P --> B["Books (12)"]
    E --> PH["Phones (13)"]
    E --> LP["Laptops (14)"]
    PH --> S["Smartphones (17)"]
    B --> F["Fiction (15)"]
    B --> N["Nonfiction (16)"]
~~~

### 19.1. Danh mục và cha trực tiếp

~~~sql
SELECT
    c.category_id,
    c.category_name,
    p.category_name AS parent_name
FROM hier_lab.categories AS c
LEFT JOIN hier_lab.categories AS p
    ON p.category_id = c.parent_id
ORDER BY c.category_id;
~~~

Products không có cha; Electronics có cha Products; Phones có cha Electronics.

### 19.2. Hai cấp cha bằng self join

~~~sql
SELECT
    child.category_name AS category,
    parent.category_name AS parent_category,
    grandparent.category_name AS grandparent_category
FROM hier_lab.categories AS child
LEFT JOIN hier_lab.categories AS parent
    ON parent.category_id = child.parent_id
LEFT JOIN hier_lab.categories AS grandparent
    ON grandparent.category_id = parent.parent_id
WHERE child.category_id = 17;
~~~

Kết quả của Smartphones:

~~~text
category             = Smartphones
parent_category      = Phones
grandparent_category = Electronics
~~~

Muốn lấy đến Products cần thêm self join một cấp nữa, hoặc chuyển sang recursive CTE.

### 19.3. Mọi hậu duệ của Electronics

~~~sql
WITH RECURSIVE category_tree AS (
    SELECT
        c.category_id,
        c.category_name,
        c.parent_id,
        0 AS depth,
        ARRAY[c.category_id] AS path_ids
    FROM hier_lab.categories AS c
    WHERE c.category_id = 11

    UNION ALL

    SELECT
        child.category_id,
        child.category_name,
        child.parent_id,
        parent.depth + 1,
        parent.path_ids || child.category_id
    FROM hier_lab.categories AS child
    JOIN category_tree AS parent
        ON child.parent_id = parent.category_id
    WHERE NOT child.category_id = ANY(parent.path_ids)
)
SELECT category_id, category_name, depth
FROM category_tree
WHERE depth > 0
ORDER BY depth, category_id;
~~~

Kết quả:

| ID | Danh mục | depth |
| ---: | --- | ---: |
| 13 | Phones | 1 |
| 14 | Laptops | 1 |
| 17 | Smartphones | 2 |

Với cây danh mục, quan hệ này vẫn là **một bảng tự tham chiếu**, chỉ đổi tên từ `manager_id` sang `parent_id`. Mẫu JOIN không thay đổi về bản chất.

## 20. Adjacency list: ưu và nhược điểm

Mô hình một cột `parent_id` trong mỗi hàng được gọi là **adjacency list**.

**Ưu điểm:**

- Cấu trúc dễ hiểu, mỗi bản ghi lưu cha trực tiếp.
- FK bảo vệ cha tồn tại.
- Thêm một nút hoặc đổi cha thường chỉ cập nhật một hàng.
- Truy vấn một cấp đơn giản, dễ đánh index.
- `WITH RECURSIVE` hỗ trợ truy vấn nhiều cấp mà không cần lưu đường dẫn sẵn.

**Hạn chế:**

- Tính tất cả tổ tiên/hậu duệ cần đệ quy.
- Kiểm soát chu trình không thể chỉ dựa vào FK.
- Cây rất sâu hoặc rộng có thể khiến traversal tốn tài nguyên.
- Nếu cần truy vấn đường dẫn cực kỳ thường xuyên, có thể phải cân nhắc mô hình bổ sung như closure table hoặc materialized path.

Có những mô hình phân cấp khác như **materialized path**, **closure table**, **nested sets**. Chúng thay đổi cách đánh đổi giữa tốc độ truy vấn và chi phí cập nhật. Với phân cấp đơn giản, adjacency list thường là điểm bắt đầu hợp lý trước khi tối ưu.

## 21. Vì sao khóa ngoại không đủ để loại trừ cycle?

Ràng buộc:

~~~sql
CHECK (manager_id IS NULL OR manager_id <> employee_id)
~~~

chỉ ngăn một hàng tự tham chiếu trực tiếp, ví dụ `employee_id = 2, manager_id = 2`.

Nó không ngăn:

~~~text
An (2) -> Khang (9) -> Dung (5) -> An (2)
~~~

vì từng giá trị `manager_id` đều trỏ đến một nhân viên khác và không vi phạm FK.

Một ví dụ **chỉ để thí nghiệm trong transaction rồi ROLLBACK**:

~~~sql
BEGIN;

UPDATE hier_lab.employees
SET manager_id = 9
WHERE employee_id = 2;

SELECT employee_id, full_name, manager_id
FROM hier_lab.employees
WHERE employee_id IN (2, 5, 9)
ORDER BY employee_id;

ROLLBACK;
~~~

Nếu commit, An báo cáo cho Khang, trong khi Khang báo cáo cho Dung và Dung báo cáo cho An, tạo thành chu trình. PostgreSQL không tự từ chối chỉ nhờ FK/check hiện tại.

### Cần làm gì để bảo vệ cấu trúc cây?

- Trước khi chuyển một nút sang cha mới, kiểm tra cha mới **không nằm trong tập hậu duệ của nút đó**.
- Thực hiện kiểm tra và cập nhật trong transaction, có cơ chế xử lý đồng thời thích hợp.
- Khi có nhiều phiên ghi, tránh tình huống hai transaction cùng thay đổi quan hệ dựa trên snapshot riêng khiến kết quả sau commit có cycle.
- Cân nhắc trigger/constraint trigger hoặc phương án quản lý phân cấp ở database khi yêu cầu toàn vẹn bắt buộc.
- Khi đọc, dùng guard dựa trên path hoặc `CYCLE` ở phiên bản hỗ trợ, để không duyệt vô hạn.

**Chặn lặp khi truy vấn không tương đương chặn dữ liệu sai được ghi vào bảng.** Hai vấn đề cần giải pháp độc lập.

## 22. CYCLE trong PostgreSQL 14 trở lên

PostgreSQL hỗ trợ mệnh đề `CYCLE` trong recursive CTE từ **PostgreSQL 14**. Cú pháp giúp theo dõi các khóa đã gặp trên một đường duyệt:

~~~sql
WITH RECURSIVE descendants AS (
    SELECT
        employee_id,
        full_name,
        manager_id,
        0 AS depth
    FROM hier_lab.employees
    WHERE employee_id = 2

    UNION ALL

    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        d.depth + 1
    FROM hier_lab.employees AS e
    JOIN descendants AS d
        ON e.manager_id = d.employee_id
)
CYCLE employee_id SET is_cycle USING cycle_path
SELECT
    employee_id,
    full_name,
    depth,
    is_cycle
FROM descendants
ORDER BY cycle_path;
~~~

`CYCLE` tạo cờ `is_cycle` và thông tin đường dẫn `cycle_path`, đồng thời có cơ chế tránh mở rộng vô hạn khi một ID lặp lại trong đường đi. Nó giúp chẩn đoán những cây đã chứa dữ liệu bất thường.

Trên PostgreSQL **13 trở xuống**, không dùng cú pháp này; hãy dùng guard thủ công với mảng `path_ids` như các truy vấn trước đó.

`CYCLE` **không phải ràng buộc toàn cục trên bảng** và không tự sửa dữ liệu sai. Để ngăn các thao tác ghi tạo vòng, vẫn cần thiết kế transaction/constraint/nghiệp vụ.

## 23. Phân biệt root, orphan và thành phần cycle

Một hàng có thể ở các trạng thái khác nhau:

| Trạng thái | parent_id | Hàng cha có tồn tại? | Ý nghĩa |
| --- | --- | --- | --- |
| Root | NULL | Không cần | Nút gốc hợp lệ |
| Child | ID khác NULL | Có | Nút con hợp lệ |
| Orphan | ID khác NULL | Không | Tham chiếu mồ côi, thường do thiếu FK/dữ liệu lỗi |
| Cycle component | ID khác NULL | Có thể mọi cha đều tồn tại | Quan hệ không còn là cây |

Nếu một thành phần hoàn toàn tạo vòng nhưng **không nối với root**, truy vấn recursive có anchor `manager_id IS NULL` sẽ không đi tới thành phần đó.

### Truy vấn tìm orphan

~~~sql
SELECT
    e.employee_id,
    e.full_name,
    e.manager_id
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
WHERE e.manager_id IS NOT NULL
  AND m.employee_id IS NULL
ORDER BY e.employee_id;
~~~

Với dữ liệu lab đã được bảo vệ bằng FK hợp lệ, kết quả **rỗng**.

Truy vấn tương đương bằng `NOT EXISTS`:

~~~sql
SELECT e.employee_id, e.full_name, e.manager_id
FROM hier_lab.employees AS e
WHERE e.manager_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM hier_lab.employees AS m
      WHERE m.employee_id = e.manager_id
  );
~~~

Một FK hợp lệ giúp tránh orphan, nhưng không tự bảo đảm cấu trúc **không có cycle** hoặc **chỉ có một root**.

## 24. Thay đổi cha và quản lý vòng đời quan hệ

Giả sử muốn chuyển Dung (5) từ quản lý An (2) sang quản lý Binh (3):

~~~sql
BEGIN;

UPDATE hier_lab.employees
SET manager_id = 3
WHERE employee_id = 5;

SELECT
    e.full_name AS employee,
    m.full_name AS manager
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
WHERE e.employee_id = 5;

ROLLBACK;
~~~

Trong transaction, quản lý của Dung là Binh. Sau rollback, Dung lại báo cáo cho An.

Khi làm thật, ứng dụng nên xác định: quản lý mới có quyền nhận nhân viên không; chuyển nhánh có tạo cycle không; có cần lưu lịch sử reporting line không; nhiều phiên có thể đồng thời thay đổi cây không.

### Khi xóa cha thì sao?

Lab đã khai báo:

~~~sql
ON DELETE SET NULL
~~~

Nếu xóa An, Chi và Dung mất quản lý trực tiếp; Khang vẫn có quản lý Dung.

~~~sql
BEGIN;

DELETE FROM hier_lab.employees
WHERE employee_id = 2;

SELECT employee_id, full_name, manager_id
FROM hier_lab.employees
WHERE employee_id IN (4, 5, 9)
ORDER BY employee_id;

ROLLBACK;
~~~

Trong transaction:

- Chi (4) có `manager_id NULL`.
- Dung (5) có `manager_id NULL`.
- Khang (9) vẫn có `manager_id = 5`.

`ON DELETE CASCADE` thay vì `SET NULL` có thể xóa cả nhánh nhân viên theo những quan hệ cascade. Với dữ liệu nhân sự, hành vi đó thường không phù hợp. Khi chọn `ON DELETE`, phải xem **vòng đời dữ liệu** chứ không chỉ tính hợp lệ của SQL.

## 25. Chỉ mục trong bảng phân cấp

Hai đường truy cập phổ biến:

- Tìm một nút theo `employee_id`: đã có index từ `PRIMARY KEY`.
- Tìm các nút con theo `manager_id`: cần cân nhắc index riêng.

~~~sql
CREATE INDEX idx_employees_manager
ON hier_lab.employees(manager_id);
~~~

Index trên cột FK của bảng con **không tự được PostgreSQL tạo trong mọi trường hợp**. Nếu truy vấn thường xuyên lấy con theo cha, index `manager_id` thường hữu ích.

Nếu cần lấy danh sách con sắp theo ID:

~~~sql
CREATE INDEX idx_employees_manager_child
ON hier_lab.employees(manager_id, employee_id);
~~~

Index ghép này có thể phục vụ điều kiện lọc theo `manager_id` và thứ tự `employee_id`, tùy kế hoạch. Trước khi giữ cả hai index trong ứng dụng thật, đánh giá xem một index ghép đã đủ chưa để tránh overhead ghi và dung lượng.

### Dùng EXPLAIN

~~~sql
EXPLAIN
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 2;
~~~

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 2;
~~~

Với bảng chỉ chín hàng, PostgreSQL có thể chọn quét tuần tự dù có index; điều này không chứng minh index sai. Cần xem số hàng thật, thống kê và workload.

Recursive CTE trên cây lớn có thể tiêu thụ bộ nhớ hoặc tạo nhiều hàng trung gian. Hãy xác định rõ anchor, bảo vệ cycle, cân nhắc depth tối đa theo nghiệp vụ và đo trên dữ liệu đại diện thay vì suy từ một ví dụ nhỏ.

## 26. Cấp dưới cùng cha khác với cùng độ sâu

Có ít nhất hai cách hiểu “cùng cấp”:

- **Cùng một cha**: siblings, tìm bằng self join điều kiện `a.manager_id = b.manager_id`.
- **Cùng độ sâu từ root**: có cùng `depth`, dù thuộc hai nhánh khác nhau hoặc hai cây khác nhau.

Ở dữ liệu mẫu, An, Binh và Hoa cùng `depth = 1`, nhưng Hoa báo cáo cho Giang, không phải Linh.

### Truy vấn độ sâu toàn bảng

~~~sql
WITH RECURSIVE tree AS (
    SELECT
        employee_id,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE manager_id IS NULL

    UNION ALL

    SELECT
        e.employee_id,
        e.manager_id,
        t.depth + 1,
        t.path_ids || e.employee_id
    FROM hier_lab.employees AS e
    JOIN tree AS t
        ON e.manager_id = t.employee_id
    WHERE NOT e.employee_id = ANY(t.path_ids)
)
SELECT
    t.depth,
    e.employee_id,
    e.full_name
FROM tree AS t
JOIN hier_lab.employees AS e
    ON e.employee_id = t.employee_id
ORDER BY t.depth, t.employee_id;
~~~

Self join một cấp không đủ để tính độ sâu tùy ý vì độ sâu là kết quả của **việc đi theo nhiều cạnh** của quan hệ.

## 27. Những sai lầm thường gặp

### 27.1. Không đặt alias cho từng vai trò

Cùng bảng được tham chiếu nhiều lần cần alias rõ ràng. Dùng `employee` và `manager` hoặc `child` và `parent`.

### 27.2. JOIN theo ID của chính hàng

`m.employee_id = e.employee_id` làm nhân viên khớp với chính mình. Đúng là `m.employee_id = e.manager_id`.

### 27.3. Dùng INNER JOIN rồi mất root

Root có `manager_id NULL` nên không có hàng quản lý. Khi muốn giữ toàn bộ nhân viên, dùng `LEFT JOIN`.

### 27.4. So sánh NULL bằng dấu bằng

`WHERE manager_id = NULL` không tìm root. Dùng `IS NULL`.

### 27.5. Dùng COUNT(*) để đếm con sau LEFT JOIN

Người không có con vẫn tạo hàng bảo toàn. Dùng `COUNT(child.employee_id)`.

### 27.6. Nhầm cấp dưới trực tiếp với mọi hậu duệ

Một self join đi một cấp. Cần recursive CTE nếu muốn toàn bộ nhánh với độ sâu thay đổi.

### 27.7. Truy vấn siblings không loại cặp trùng hai chiều

`a.employee_id <> b.employee_id` trả cả (A,B) và (B,A). Dùng `a.employee_id < b.employee_id` khi cần mỗi cặp một lần.

### 27.8. Cho rằng FK tự ngăn mọi cycle

FK chỉ đảm bảo parent tồn tại; CHECK một hàng chỉ ngăn tự trỏ trực tiếp. Cycle nhiều hàng cần bảo vệ riêng.

### 27.9. Duyệt từ root rồi nghĩ đã thấy mọi hàng

Một thành phần có cycle không nối root sẽ không xuất hiện khi anchor chỉ lấy `manager_id IS NULL`.

### 27.10. Recursive CTE không có guard khi dữ liệu có cycle

`UNION ALL` cùng một cạnh vòng có thể sinh hàng lặp vô hạn. Dùng path guard hoặc `CYCLE` khi phù hợp.

### 27.11. Trông chờ thứ tự mặc định của recursive CTE

Kết quả SQL không có thứ tự được cam kết nếu thiếu `ORDER BY`. Dùng thứ tự theo path, depth và ID.

### 27.12. Xóa quản lý bằng CASCADE mà không kiểm tra vòng đời dữ liệu

Có thể kéo theo xóa cả nhánh; cần xem yêu cầu lưu trữ và nghiệp vụ.

### 27.13. Thêm index theo thói quen

Index giúp đọc nhưng tốn dung lượng và overhead ghi. So sánh kế hoạch trước khi giữ nhiều index gần trùng.

### 27.14. Dùng recursion cho yêu cầu chỉ có một cấp

Nếu chỉ tìm direct reports, `WHERE manager_id = ?` đơn giản hơn nhiều.

## 28. Bài tập thực hành có đáp án

Dữ liệu lấy từ mục 3; không commit các thao tác cập nhật/xóa thử nghiệm.

### Bài 1. Nhân viên và quản lý trực tiếp

~~~sql
SELECT e.full_name AS employee, m.full_name AS manager
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
~~~

**Kết quả:** Linh và Giang có manager NULL; An/Binh thuộc Linh; Chi/Dung thuộc An; Em thuộc Binh; Hoa thuộc Giang; Khang thuộc Dung.

### Bài 2. Cấp dưới trực tiếp của Linh

~~~sql
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 1
ORDER BY employee_id;
~~~

**Kết quả:** An (2), Binh (3).

### Bài 3. Nút gốc

~~~sql
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id IS NULL
ORDER BY employee_id;
~~~

**Kết quả:** Linh và Giang; có hai root nên đây là forest.

### Bài 4. Nhân viên không có cấp dưới

~~~sql
SELECT e.employee_id, e.full_name
FROM hier_lab.employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM hier_lab.employees AS child
    WHERE child.manager_id = e.employee_id
)
ORDER BY e.employee_id;
~~~

**Kết quả:** Chi, Em, Hoa, Khang.

### Bài 5. Đếm cấp dưới trực tiếp của An

~~~sql
SELECT COUNT(*) AS direct_reports
FROM hier_lab.employees
WHERE manager_id = 2;
~~~

**Kết quả:** 2 (Chi, Dung).

### Bài 6. Tìm cặp cùng quản lý

~~~sql
SELECT a.full_name AS first_name, b.full_name AS second_name
FROM hier_lab.employees AS a
JOIN hier_lab.employees AS b
    ON a.manager_id = b.manager_id
   AND a.employee_id < b.employee_id
WHERE a.manager_id IS NOT NULL
ORDER BY a.manager_id, a.employee_id;
~~~

**Kết quả:** (An, Binh) và (Chi, Dung).

### Bài 7. Quản lý và quản lý cấp trên của Khang

~~~sql
SELECT
    e.full_name AS employee,
    m.full_name AS manager,
    gm.full_name AS grand_manager
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
LEFT JOIN hier_lab.employees AS gm
    ON gm.employee_id = m.manager_id
WHERE e.employee_id = 9;
~~~

**Kết quả:** Khang → Dung → An.

### Bài 8. Tổng hậu duệ của Linh

Dùng recursive CTE ở mục 16 với anchor `employee_id = 1`.

**Kết quả:** 6, khác với 2 con trực tiếp.

### Bài 9. Đường quản lý từ Khang lên root

Dùng recursive CTE ở mục 17 với anchor `employee_id = 9`.

**Kết quả:** Khang → Dung → An → Linh.

### Bài 10. Các danh mục con trực tiếp của Electronics

~~~sql
SELECT category_id, category_name
FROM hier_lab.categories
WHERE parent_id = 11
ORDER BY category_id;
~~~

**Kết quả:** Phones (13), Laptops (14).

### Bài 11. Các hậu duệ của Electronics

Dùng recursive CTE của mục 19 với anchor danh mục 11.

**Kết quả:** Phones và Laptops ở depth 1, Smartphones ở depth 2.

### Bài 12. Vì sao CHECK không chặn cycle dài?

Nếu A trỏ B, B trỏ C và C trỏ A, từng hàng đều có `parent_id <> id` nhưng toàn bộ cấu trúc tạo thành vòng. **Đáp án:** cần kiểm soát quan hệ nhiều hàng/transaction, không chỉ CHECK một hàng.

### Bài 13. Vì sao hai root không được ghép làm sibling?

`NULL = NULL` không trả TRUE. Hơn nữa, trong cây tổ chức, hai root không có chung một quản lý thực sự. Muốn nhóm root cần định nghĩa quy tắc nghiệp vụ riêng, không mặc định chúng là siblings.

### Bài 14. Self join nào cho 7 hàng, self join nào cho 9 hàng?

`INNER JOIN` từ nhân viên tới quản lý trả 7 vì loại hai root. `LEFT JOIN` trả 9 vì giữ Linh và Giang dù phía quản lý là NULL.

## 29. Quy trình giải quyết một yêu cầu phân cấp

Khi được yêu cầu viết SQL về quan hệ cha–con, hãy đi lần lượt:

1. Xác định **ID định danh** của mỗi nút.
2. Xác định cột `parent_id`/`manager_id` và liệu NULL có nghĩa root không.
3. Kiểm tra self-referencing FK và ràng buộc toàn vẹn.
4. Xác định mục tiêu là một cấp, số cấp cố định hay mọi cấp.
5. Với một cấp, chọn `JOIN`/`LEFT JOIN` hoặc `WHERE parent_id=?`.
6. Đặt alias theo vai trò: child, parent, grandparent.
7. Với root hoặc leaf, dùng `IS NULL` hoặc `NOT EXISTS` thích hợp.
8. Với nhiều cấp biến thiên, dùng `WITH RECURSIVE`, anchor rõ ràng và điều kiện JOIN cùng bảng.
9. Bổ sung cơ chế phòng cycle và kiểm soát depth khi dữ liệu có thể không tin cậy.
10. Thêm `ORDER BY` khi cần thứ tự cây hoặc kết quả ổn định.
11. Cân nhắc index ở parent-id phía con và đo bằng `EXPLAIN`.
12. Xác định chính sách thay đổi/xóa cha và kiểm soát nghiệp vụ khi nhiều writer cùng thao tác.

Không cần tạo thêm bảng cho mỗi cấp quản lý. Một bảng tự tham chiếu đã đủ để lưu cấu trúc phân cấp dạng adjacency list; vấn đề còn lại là **truy vấn đúng số cấp và bảo vệ những quan hệ mà nghiệp vụ cho phép**.

## 30. Tổng kết

Self join trong PostgreSQL là cách **dùng cùng bảng ở nhiều vai trò**, thường xuyên gặp trong dữ liệu phân cấp:

~~~sql
-- Tên quản lý trực tiếp của mọi nhân viên.
SELECT e.full_name, m.full_name AS manager
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id;

-- Những nhân viên là root.
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id IS NULL;

-- Những nhân viên báo cáo trực tiếp cho Linh (ID 1).
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 1;

-- Những nhân viên không có con.
SELECT e.employee_id, e.full_name
FROM hier_lab.employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM hier_lab.employees AS child
    WHERE child.manager_id = e.employee_id
);
~~~

Khi chỉ cần một hoặc hai cấp, `LEFT JOIN`/`INNER JOIN` với alias rõ ràng là giải pháp trực tiếp. Khi cần **mọi cấp trong cây**, dùng `WITH RECURSIVE` để lặp lại quan hệ cha–con cho đến khi không còn nút cần duyệt.

Khóa ngoại tự tham chiếu bảo đảm **cha tồn tại**, nhưng không mặc nhiên bảo đảm **không có chu trình** hay chỉ có một root. Kết hợp đúng constraint, kiểm soát cập nhật, index và logic truy vấn sẽ giúp mô hình phân cấp đơn giản trở nên đáng tin cậy, dễ mở rộng và dễ bảo trì trong PostgreSQL.
