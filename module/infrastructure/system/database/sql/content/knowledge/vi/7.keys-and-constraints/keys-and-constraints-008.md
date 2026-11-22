# Khóa ngoại tự tham chiếu và quan hệ phân cấp

Trong nhiều ứng dụng, các bản ghi của **cùng một loại đối tượng** có quan hệ cha–con: nhân viên báo cáo cho quản lý, danh mục sản phẩm có danh mục con, bình luận có phản hồi, phòng ban thuộc phòng ban cấp trên. Những quan hệ này khác với ví dụ khóa ngoại thông thường giữa hai bảng khác nhau: **cột khóa ngoại trỏ về khóa của chính bảng đang chứa nó**.

Đây là **khóa ngoại tự tham chiếu** (*self-referencing foreign key*), một cách phổ biến để lưu **cấu trúc phân cấp** (*hierarchy*) bằng mô hình *danh sách kề* (*adjacency list*). Khóa ngoại giúp ngăn tham chiếu đến bản ghi không tồn tại; để bảo đảm dữ liệu thực sự tạo thành một cây hợp lệ, ta còn phải hiểu cách biểu diễn nút gốc, truy vấn nhiều cấp, xử lý xóa hoặc di chuyển nhánh và phòng tránh chu trình.

Bài học dùng **PostgreSQL** để minh họa SQL có thể thực hành. Các khái niệm cốt lõi về khóa chính, khóa ngoại và phân cấp áp dụng cho nhiều hệ quản trị cơ sở dữ liệu quan hệ; cú pháp CTE đệ quy và cơ chế xử lý một số ràng buộc có thể khác nhau giữa các sản phẩm.

## 1. Khóa ngoại tự tham chiếu là gì?

**Khóa ngoại (foreign key)** là ràng buộc yêu cầu giá trị trong một hay nhiều cột tham chiếu phải tương ứng với khóa được phép tham chiếu ở bảng đích, trừ trường hợp `NULL` được cho phép theo quy tắc khóa ngoại. Khi bảng đích **chính là bảng chứa khóa ngoại**, ta gọi đó là **khóa ngoại tự tham chiếu**.

Ví dụ tổ chức nhân sự:

```text
employees
┌─────────────┬───────────────┬────────────┐
│ employee_id │ employee_name │ manager_id │
├─────────────┼───────────────┼────────────┤
│           1 │ Lan           │ NULL       │
│           2 │ Minh          │ 1          │
│           3 │ Hoa           │ 1          │
│           4 │ An            │ 2          │
└─────────────┴───────────────┴────────────┘

employees.manager_id ──FK──► employees.employee_id
```

Ở đây:

- `employee_id` là **khóa chính (PRIMARY KEY)**: định danh duy nhất mỗi nhân viên.
- `manager_id` là **khóa ngoại**: nếu có giá trị, nó phải trỏ đến `employee_id` của một hàng trong chính bảng `employees`.
- `manager_id IS NULL` biểu thị nhân viên **không có quản lý cấp trên** trong mô hình hiện tại, thường là nút gốc.
- Nhiều nhân viên có thể cùng `manager_id`, tạo quan hệ **một quản lý – nhiều cấp dưới**.

Quan hệ được biểu diễn theo hướng: **mỗi hàng con giữ ID của hàng cha**, thay vì hàng cha phải chứa danh sách tất cả ID của con.

| Khái niệm | Trong bảng `employees` |
|---|---|
| Nút (*node*) | Một nhân viên |
| Nút cha (*parent*) | Quản lý trực tiếp |
| Nút con (*child*) | Nhân viên báo cáo trực tiếp |
| Nút gốc (*root*) | Nhân viên có `manager_id IS NULL` |
| Nút lá (*leaf*) | Nhân viên không quản lý ai |
| Tổ tiên (*ancestor*) | Quản lý trực tiếp hoặc gián tiếp ở các cấp trên |
| Hậu duệ (*descendant*) | Cấp dưới trực tiếp hoặc gián tiếp ở các cấp dưới |
| Độ sâu (*depth*) | Số cạnh từ nút gốc tới nút đang xét |

Khóa ngoại **không tự nói rằng bảng phải chỉ có một gốc, không có chu trình hay có độ sâu tối đa**. Các đặc tính đó là quy tắc bổ sung của mô hình phân cấp.

## 2. Ví dụ dữ liệu cây tổ chức

Giả sử công ty có cấu trúc sau:

```text
Lan (1) — CEO
├── Minh (2) — Engineering Director
│   ├── An (4) — Backend Lead
│   │   ├── Chi (6) — Developer
│   │   └── Dung (7) — Developer
│   └── Binh (5) — QA Lead
└── Hoa (3) — Sales Director
    └── Giang (8) — Account Executive
```

Tám người cùng nằm trong một bảng. Quan hệ cha–con chỉ cần một cột `manager_id`:

| employee_id | employee_name | manager_id | Vai trò |
|---:|---|---:|---|
| 1 | Lan | `NULL` | CEO |
| 2 | Minh | 1 | Engineering Director |
| 3 | Hoa | 1 | Sales Director |
| 4 | An | 2 | Backend Lead |
| 5 | Binh | 2 | QA Lead |
| 6 | Chi | 4 | Developer |
| 7 | Dung | 4 | Developer |
| 8 | Giang | 3 | Account Executive |

Quan sát: Chi (6) chỉ lưu `manager_id = 4`; thông tin “Chi thuộc nhánh Minh và báo cáo gián tiếp cho Lan” được suy ra bằng cách đi theo nhiều liên kết, không cần lưu thêm ID của tất cả tổ tiên trong mỗi hàng.

## 3. Tạo bảng với khóa ngoại trỏ về chính nó

Chạy phần minh họa này trên **cơ sở dữ liệu thực hành**, không dùng bảng nhân sự thật. Trong PostgreSQL:

```sql
CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    employee_name VARCHAR(100) NOT NULL,
    job_title VARCHAR(100) NOT NULL,
    manager_id INTEGER,

    CONSTRAINT fk_employees_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees(employee_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_employee_not_own_manager
        CHECK (manager_id IS NULL OR manager_id <> employee_id)
);

CREATE INDEX idx_employees_manager_id
    ON employees(manager_id);
```

Các phần của định nghĩa có mục đích khác nhau:

1. **`PRIMARY KEY (employee_id)`** bảo đảm mỗi nhân viên có ID riêng; PostgreSQL tự tạo chỉ mục tương ứng cho khóa chính.
2. **`FOREIGN KEY (manager_id) REFERENCES employees(employee_id)`** bảo đảm mỗi ID quản lý không `NULL` trỏ đến một nhân viên đang tồn tại **trong chính bảng**.
3. **`manager_id INTEGER` không có `NOT NULL`** cho phép các nút gốc, chẳng hạn CEO chưa có cấp trên trong hệ thống.
4. **`ON DELETE RESTRICT`** chặn xóa một nhân viên khi còn nhân viên khác tham chiếu người đó làm quản lý. Nhờ vậy, không vô tình làm mất liên kết của cấp dưới.
5. **`CHECK (manager_id IS NULL OR manager_id <> employee_id)`** chặn một người tự quản lý **trực tiếp**. Nó **không** ngăn chu trình dài hơn hai hoặc nhiều nút.
6. **Chỉ mục trên `manager_id`** giúp truy vấn cấp dưới trực tiếp và nhiều lần nối từ cha sang con. Trong PostgreSQL, khóa ngoại **không tự tạo chỉ mục trên cột tham chiếu**; quyết định tạo chỉ mục phụ thuộc tần suất truy vấn và cập nhật.

Có thể dùng cú pháp rút gọn:

```sql
-- Tương đương về ý nghĩa cơ bản với FK riêng ở trên:
manager_id INTEGER REFERENCES employees(employee_id)
```

Đoạn rút gọn chỉ minh họa cách khai báo khóa ngoại; đừng chèn nguyên văn nó vào bảng đã tạo. Ở định nghĩa đầy đủ, ta đặt tên constraint để dễ đọc lỗi và chủ động chọn hành vi khi xóa.

### 3.1. Tạo FK sau khi bảng đã tồn tại

Nếu bảng đã có cột `manager_id` mà chưa có ràng buộc, có thể thêm khóa ngoại:

```sql
-- Ví dụ độc lập, chỉ dùng khi constraint chưa tồn tại:
ALTER TABLE employees
ADD CONSTRAINT fk_employees_manager
FOREIGN KEY (manager_id)
REFERENCES employees(employee_id);
```

Với bảng đang có dữ liệu, hệ quản trị phải kiểm tra xem những ID quản lý không `NULL` có thực sự tồn tại hay không. Nếu đã có hàng mồ côi, thao tác thêm ràng buộc có thể thất bại. Không chạy lệnh minh họa này lần thứ hai trên bảng vừa tạo ở đầu mục 3 vì constraint đã có tên đó.

## 4. Nạp dữ liệu theo thứ tự cha trước con

Trong ví dụ đơn giản, tạo nút gốc trước rồi đến các cấp con để mỗi lần `INSERT` đều thỏa khóa ngoại:

```sql
INSERT INTO employees
    (employee_id, employee_name, job_title, manager_id)
VALUES
    (1, 'Lan', 'CEO', NULL);

INSERT INTO employees
    (employee_id, employee_name, job_title, manager_id)
VALUES
    (2, 'Minh', 'Engineering Director', 1),
    (3, 'Hoa', 'Sales Director', 1);

INSERT INTO employees
    (employee_id, employee_name, job_title, manager_id)
VALUES
    (4, 'An', 'Backend Lead', 2),
    (5, 'Binh', 'QA Lead', 2),
    (8, 'Giang', 'Account Executive', 3);

INSERT INTO employees
    (employee_id, employee_name, job_title, manager_id)
VALUES
    (6, 'Chi', 'Developer', 4),
    (7, 'Dung', 'Developer', 4);
```

Do khóa ngoại được kiểm tra khi ghi theo cấu hình ví dụ, `INSERT` người quản lý cần thực hiện trước `INSERT` cấp dưới của họ. Không nhất thiết phải nhập theo độ sâu nếu có cơ chế ràng buộc trì hoãn hoặc quy trình nhập dữ liệu đặc biệt, nhưng **cha trước con** là cách dễ hiểu nhất cho bài nhập môn.

### 4.1. Giá trị nào hợp lệ?

Thử suy luận các thao tác sau **từ dữ liệu đã nạp**:

```sql
-- Hợp lệ: nhân viên mới báo cáo cho Minh (2).
INSERT INTO employees
    (employee_id, employee_name, job_title, manager_id)
VALUES (9, 'Hanh', 'Engineer', 2);

-- Không hợp lệ: không có nhân viên mang ID 999.
-- INSERT INTO employees
--     (employee_id, employee_name, job_title, manager_id)
-- VALUES (10, 'Khoa', 'Engineer', 999);

-- Không hợp lệ: một người tự nhận mình là quản lý trực tiếp.
-- INSERT INTO employees
--     (employee_id, employee_name, job_title, manager_id)
-- VALUES (11, 'Linh', 'Engineer', 11);
```

Lệnh đầu được phép vì quản lý 2 có thật. Lệnh thứ hai vi phạm khóa ngoại, lệnh thứ ba vi phạm ràng buộc `CHECK`. **Để giữ nguyên bộ tám nhân viên cho các phần tiếp theo**, hãy bỏ qua lệnh thêm ID 9 hoặc xóa nhân viên thử nghiệm đó trước khi tiếp tục.

## 5. Truy vấn một cấp bằng self JOIN

Khi muốn hiển thị tên nhân viên và tên quản lý, ta nối bảng với chính nó, dùng hai **bí danh** để phân biệt vai trò:

```sql
SELECT
    e.employee_id,
    e.employee_name AS employee,
    m.employee_name AS manager
FROM employees AS e
LEFT JOIN employees AS m
    ON e.manager_id = m.employee_id
ORDER BY e.employee_id;
```

Kết quả chính:

| employee_id | employee | manager |
|---:|---|---|
| 1 | Lan | `NULL` |
| 2 | Minh | Lan |
| 3 | Hoa | Lan |
| 4 | An | Minh |
| 5 | Binh | Minh |
| 6 | Chi | An |
| 7 | Dung | An |
| 8 | Giang | Hoa |

- `e` là bản ghi nhân viên; `m` là bản ghi quản lý, cùng thuộc bảng `employees` nhưng có vai trò khác nhau trong câu truy vấn.
- `LEFT JOIN` giữ cả Lan, người có `manager_id = NULL`. Với `INNER JOIN`, Lan sẽ bị loại vì không có hàng quản lý để ghép.
- Đây là **nối một bước**: câu SQL chỉ tìm quản lý **trực tiếp**, không đi tiếp đến quản lý của quản lý.

Muốn tìm các nhân viên **báo cáo trực tiếp cho Minh**:

```sql
SELECT employee_id, employee_name
FROM employees
WHERE manager_id = 2
ORDER BY employee_id;
-- An (4), Binh (5)
```

Muốn đếm số cấp dưới **trực tiếp** của từng quản lý, kể cả người không có cấp dưới:

```sql
SELECT
    m.employee_id,
    m.employee_name,
    COUNT(e.employee_id) AS direct_report_count
FROM employees AS m
LEFT JOIN employees AS e
    ON e.manager_id = m.employee_id
GROUP BY m.employee_id, m.employee_name
ORDER BY m.employee_id;
```

Ở đây dùng `COUNT(e.employee_id)` thay vì `COUNT(*)` vì với `LEFT JOIN`, người không có cấp dưới vẫn có một hàng nối được bổ sung các cột bên phải bằng `NULL`; `COUNT(*)` sẽ đếm hàng đó thành 1, còn `COUNT(e.employee_id)` trả 0.

| Nhân viên | Số cấp dưới trực tiếp |
|---|---:|
| Lan | 2 |
| Minh | 2 |
| Hoa | 1 |
| An | 2 |
| Binh | 0 |
| Chi | 0 |
| Dung | 0 |
| Giang | 0 |

Một cấp có thể truy vấn bằng self JOIN thông thường. Để tìm **tất cả cấp dưới qua nhiều tầng**, cần cách duyệt phân cấp.

## 6. Truy vấn nhiều cấp với WITH RECURSIVE

Các cây có thể sâu 2, 5 hoặc hàng chục cấp; không thể dự đoán sẵn phải viết bao nhiêu `JOIN`. PostgreSQL hỗ trợ **common table expression đệ quy** (*recursive CTE*) với `WITH RECURSIVE`: bắt đầu từ tập nút gốc (*anchor*), rồi lặp bước tìm các nút con của những nút đã tìm được.

### 6.1. Hiển thị toàn bộ cây từ các nút gốc

```sql
WITH RECURSIVE org_chart AS (
    -- Anchor: tất cả nút gốc.
    SELECT
        employee_id,
        employee_name,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS path
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive step: tìm các cấp dưới trực tiếp của từng nút.
    SELECT
        child.employee_id,
        child.employee_name,
        child.manager_id,
        parent.depth + 1,
        parent.path || child.employee_id
    FROM employees AS child
    JOIN org_chart AS parent
        ON child.manager_id = parent.employee_id
    WHERE NOT (child.employee_id = ANY(parent.path))
)
SELECT
    employee_id,
    manager_id,
    depth,
    REPEAT('  ', depth) || employee_name AS employee_hierarchy
FROM org_chart
ORDER BY path;
```

Trong PostgreSQL, `ARRAY[employee_id]` tạo mảng ID dọc theo đường đi; toán tử `||` nối thêm ID con vào mảng. `ORDER BY path` sắp xếp theo dãy ID đường đi để bản ghi con nằm gần nhánh cha. `REPEAT('  ', depth)` thụt lề để dễ đọc.

Kết quả về thứ tự theo đường đi sẽ có dạng:

```text
employee_id | manager_id | depth | employee_hierarchy
------------+------------+-------+-------------------------
1           | NULL       | 0     | Lan
2           | 1          | 1     |   Minh
4           | 2          | 2     |     An
6           | 4          | 3     |       Chi
7           | 4          | 3     |       Dung
5           | 2          | 2     |     Binh
3           | 1          | 1     |   Hoa
8           | 3          | 2     |     Giang
```

Giải thích ba bộ phận quan trọng:

1. **Anchor:** `WHERE manager_id IS NULL` tìm gốc (ở bộ dữ liệu này là Lan) với `depth = 0`.
2. **Recursive step:** tìm `child.manager_id = parent.employee_id`, tăng độ sâu thêm 1 và mở rộng `path`.
3. **Điều kiện bảo vệ:** `WHERE NOT (child.employee_id = ANY(parent.path))` không cho một ID đã có trong đường đi xuất hiện lại trong cùng nhánh, tránh truy vấn lặp mãi nếu dữ liệu có chu trình. Nó không thay thế ràng buộc toàn vẹn chống chu trình khi ghi.

**Lưu ý:** nếu tồn tại một nhóm bản ghi tạo thành chu trình mà **không có đường đi từ nút gốc**, truy vấn bắt đầu tại `manager_id IS NULL` sẽ **không nhìn thấy nhóm đó**. Kết quả cây trông bình thường không chứng minh toàn bộ bảng không có chu trình.

### 6.2. Lấy toàn bộ hậu duệ của một người

Giả sử cần tìm tất cả người thuộc bộ phận do **Minh (2)** quản lý, gồm cấp dưới trực tiếp và gián tiếp:

```sql
WITH RECURSIVE subtree AS (
    SELECT
        employee_id,
        employee_name,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS path
    FROM employees
    WHERE employee_id = 2

    UNION ALL

    SELECT
        e.employee_id,
        e.employee_name,
        e.manager_id,
        s.depth + 1,
        s.path || e.employee_id
    FROM employees AS e
    JOIN subtree AS s
        ON e.manager_id = s.employee_id
    WHERE NOT (e.employee_id = ANY(s.path))
)
SELECT employee_id, employee_name, depth
FROM subtree
WHERE depth > 0
ORDER BY path;
```

Kết quả là **An (4), Chi (6), Dung (7), Binh (5)** theo thứ tự đường đi; `depth = 1` là quản lý trực tiếp của các nhân viên đó, `depth = 2` là cấp dưới xa hơn. Điều kiện `WHERE depth > 0` ở truy vấn ngoài loại bỏ chính Minh, vì anchor cũng là một hàng của CTE.

Khác với lọc `WHERE manager_id = 2` chỉ trả hai cấp dưới trực tiếp (An, Binh), CTE đệ quy trả **toàn bộ nhánh** với độ sâu không cần biết trước.

### 6.3. Tìm chuỗi quản lý từ một nhân viên lên gốc

Để tìm những người quản lý của **Chi (6)**, đổi hướng nối: từ hàng hiện tại đi theo `manager_id` lên hàng quản lý.

```sql
WITH RECURSIVE management_chain AS (
    SELECT
        employee_id,
        employee_name,
        manager_id,
        0 AS steps_up,
        ARRAY[employee_id] AS path
    FROM employees
    WHERE employee_id = 6

    UNION ALL

    SELECT
        manager.employee_id,
        manager.employee_name,
        manager.manager_id,
        c.steps_up + 1,
        c.path || manager.employee_id
    FROM management_chain AS c
    JOIN employees AS manager
        ON manager.employee_id = c.manager_id
    WHERE NOT (manager.employee_id = ANY(c.path))
)
SELECT employee_id, employee_name, steps_up
FROM management_chain
WHERE steps_up > 0
ORDER BY steps_up;
```

Kết quả: **An (4) → Minh (2) → Lan (1)**. `steps_up = 1` nghĩa là quản lý trực tiếp, `steps_up = 2` là quản lý cấp trên một bậc nữa. Trong cây hợp lệ, khi gặp nút có `manager_id IS NULL`, bước đệ quy không tìm được hàng quản lý tiếp theo và dừng.

### 6.4. Đếm số hậu duệ, khác số cấp dưới trực tiếp

Nếu cần thống kê **tất cả cấp dưới của mỗi người**, có thể bắt đầu một đường duyệt từ từng nhân viên:

```sql
WITH RECURSIVE reporting AS (
    SELECT
        employee_id AS root_id,
        employee_id,
        ARRAY[employee_id] AS path
    FROM employees

    UNION ALL

    SELECT
        r.root_id,
        e.employee_id,
        r.path || e.employee_id
    FROM reporting AS r
    JOIN employees AS e
        ON e.manager_id = r.employee_id
    WHERE NOT (e.employee_id = ANY(r.path))
)
SELECT
    root_id AS manager_employee_id,
    COUNT(*) - 1 AS total_descendants
FROM reporting
GROUP BY root_id
ORDER BY root_id;
```

Với dữ liệu tám nhân viên, Lan có **7** hậu duệ; Minh có **4**; Hoa và An lần lượt có **1** và **2**; các nút lá có **0**. `COUNT(*) - 1` loại trừ hàng anchor là chính nhân viên đó. Truy vấn nhiều điểm bắt đầu này có thể tốn tài nguyên ở cây lớn; sử dụng cho nhu cầu báo cáo cụ thể và đo hiệu năng trên dữ liệu thực tế.

## 7. Khóa ngoại tự tham chiếu bảo đảm điều gì và không bảo đảm điều gì?

Đây là điểm quan trọng nhất khi thiết kế dữ liệu phân cấp.

| Tình huống | Chỉ `FOREIGN KEY` có ngăn được không? | Cần gì thêm? |
|---|---|---|
| `manager_id` trỏ ID không tồn tại | **Có** | Khóa ngoại hợp lệ |
| `manager_id` là `NULL` khi cột cho phép NULL | **Không ngăn**, đây là giá trị hợp lệ | Quy định nút gốc theo nghiệp vụ |
| Một nhân viên tự trỏ chính mình | **Không**; hàng đó có ID tồn tại | `CHECK (manager_id IS NULL OR manager_id <> employee_id)` |
| Chu trình A → B → C → A | **Không** | Kiểm tra cây/chu trình trong giao dịch hoặc cơ chế ràng buộc bổ sung |
| Có hơn một nút gốc | **Không** | Quy tắc riêng nếu hệ thống bắt buộc đúng một gốc |
| Chiều sâu vượt ngưỡng | **Không** | Ràng buộc theo nghiệp vụ, có thể cần kiểm tra đệ quy |
| Cùng một quản lý có quá nhiều cấp dưới | **Không** | Ràng buộc/quy tắc nghiệp vụ riêng |

### 7.1. Chu trình nhiều nút vẫn có thể hợp lệ theo FK

Xét dữ liệu đã có:

```text
Lan (1) → Minh (2) → An (4) → Chi (6)
```

Đây là đường đi **từ quản lý xuống cấp dưới**. Bây giờ nếu gán **quản lý của Minh là Chi**, ta tạo chu trình:

```text
Minh (2) → An (4) → Chi (6) → Minh (2)
```

Trong bảng, liên kết thực tế được lưu theo hướng `child.manager_id = parent.id`:

```text
2.manager_id = 6
4.manager_id = 2
6.manager_id = 4
```

Mọi mã quản lý đều tồn tại; không ai tự trỏ vào chính mình, nên cả **FOREIGN KEY** lẫn `CHECK (manager_id <> employee_id)` đều không phát hiện chu trình ba nút. Có thể minh họa trong một giao dịch rồi hủy ngay:

```sql
BEGIN;

-- Chỉ để quan sát tình huống sai; sẽ không COMMIT.
UPDATE employees
SET manager_id = 6
WHERE employee_id = 2;

-- Kiểm tra dữ liệu/đường đi nếu cần.

ROLLBACK;
```

Trong dữ liệu hợp lệ, mỗi nút có tối đa một cha, và nếu mọi chuỗi cha đều kết thúc ở một gốc thì ta có một **rừng cây** (*forest*) hoặc một cây nếu chỉ có một gốc. Nhưng nếu có chu trình, cấu trúc không còn là cây hợp lệ dù vẫn thỏa khóa ngoại.

### 7.2. Kiểm tra trước khi di chuyển nhánh

Giả sử cần chuyển **Minh (2)** sang báo cáo cho **Chi (6)**. Trước khi cập nhật `manager_id`, cần kiểm tra Chi **có đang là hậu duệ của Minh không**. Nếu có, cập nhật đó sẽ tạo chu trình.

```sql
WITH RECURSIVE descendants AS (
    SELECT
        employee_id,
        ARRAY[employee_id] AS path
    FROM employees
    WHERE employee_id = 2

    UNION ALL

    SELECT
        e.employee_id,
        d.path || e.employee_id
    FROM employees AS e
    JOIN descendants AS d
        ON e.manager_id = d.employee_id
    WHERE NOT (e.employee_id = ANY(d.path))
)
SELECT employee_id
FROM descendants
WHERE employee_id = 6;
```

Truy vấn trả **6**, chứng tỏ Chi nằm trong nhánh của Minh; không nên thực hiện `UPDATE employees SET manager_id = 6 WHERE employee_id = 2`. Đây là nguyên tắc phổ quát khi đổi cha của một nút: **cha mới không được là chính nút đó hoặc một hậu duệ của nó**.

Một truy vấn kiểm tra trước khi cập nhật trong ứng dụng **chưa đủ** bảo đảm toàn vẹn dưới truy cập đồng thời: hai giao dịch có thể cùng thấy trạng thái hợp lệ rồi đồng thời tạo các liên kết hình thành chu trình. Nếu yêu cầu *không có chu trình* là bất biến bắt buộc, cần thiết kế cơ chế thực thi ở cấp ghi dữ liệu, ví dụ kiểm tra trong giao dịch cùng chiến lược khóa/đồng bộ thích hợp, hoặc trigger/ràng buộc chuyên biệt có xét cạnh tranh. Không nên coi `CHECK` đơn giản hay việc đọc trước rồi cập nhật là bảo đảm tuyệt đối.

### 7.3. Kiểm tra dữ liệu có chứa chu trình hay không

Khi nhập dữ liệu từ hệ thống khác, có thể duyệt **theo quan hệ cha từ mọi nhân viên** và đánh dấu nếu một ID xuất hiện lại trên cùng đường:

```sql
WITH RECURSIVE walk AS (
    SELECT
        employee_id AS start_id,
        employee_id AS current_id,
        manager_id,
        ARRAY[employee_id] AS path,
        FALSE AS has_cycle
    FROM employees

    UNION ALL

    SELECT
        w.start_id,
        parent.employee_id,
        parent.manager_id,
        w.path || parent.employee_id,
        parent.employee_id = ANY(w.path)
    FROM walk AS w
    JOIN employees AS parent
        ON parent.employee_id = w.manager_id
    WHERE NOT w.has_cycle
)
SELECT DISTINCT start_id
FROM walk
WHERE has_cycle
ORDER BY start_id;
```

Với bộ dữ liệu hợp lệ ở mục 4, kết quả **không có hàng**. Nếu tồn tại chu trình, truy vấn trả các **điểm xuất phát có đường đi lên cấp trên chạm chu trình**; một điểm xuất phát được báo không nhất thiết là nút nằm bên trong chu trình. Điều kiện `WHERE NOT w.has_cycle` dừng nhánh sau khi đã phát hiện ID lặp, tránh lặp đệ quy mãi.

Truy vấn này dùng kiểu mảng và các toán tử của PostgreSQL. Với RDBMS khác, có thể dùng cơ chế đánh dấu chu trình của hệ đó hoặc phương pháp tương đương. Việc kiểm tra phát hiện chu trình là hoạt động **chẩn đoán**, không tự chặn một lệnh ghi khác tạo chu trình sau khi truy vấn kết thúc.

## 8. Xóa, cập nhật và chuyển một nhánh phân cấp

Một khóa ngoại tự tham chiếu làm phát sinh câu hỏi: nếu xóa người quản lý thì những cấp dưới sẽ ra sao? Hành vi này được xác định một phần bởi **referential actions** của khóa ngoại và một phần bởi nghiệp vụ.

### 8.1. ON DELETE RESTRICT

Trong bảng mẫu, khóa ngoại được định nghĩa:

```sql
FOREIGN KEY (manager_id)
REFERENCES employees(employee_id)
ON DELETE RESTRICT
```

Vì có An (4) và Binh (5) báo cáo cho Minh (2), lệnh sau **không hợp lệ**:

```sql
-- Dự kiến lỗi khóa ngoại; không chạy nếu chưa muốn quan sát lỗi.
-- DELETE FROM employees WHERE employee_id = 2;
```

`RESTRICT` ngăn xóa hàng cha còn được tham chiếu. Nhờ đó, không thể vô tình làm “mất quản lý” của các hàng con. Nếu doanh nghiệp thực sự cần bỏ một quản lý, phải **chọn cách xử lý cấp dưới trước**.

### 8.2. ON DELETE SET NULL

Nếu mô hình cho phép tự động đưa cấp dưới trực tiếp thành nút gốc khi xóa cha, có thể dùng ràng buộc:

```sql
-- Ví dụ lựa chọn schema thay thế, không chạy trên bảng đang có FK khác.
CONSTRAINT fk_employees_manager
    FOREIGN KEY (manager_id)
    REFERENCES employees(employee_id)
    ON DELETE SET NULL
```

Khi xóa Minh, `manager_id` của **An và Binh** sẽ thành `NULL`; nhưng **Chi và Dung vẫn báo cáo cho An**. Đây là thao tác ngắt một liên kết cha–con, không có nghĩa toàn bộ hậu duệ đều bị đặt `NULL`. Để `SET NULL` hoạt động, cột khóa ngoại phải chấp nhận `NULL`.

### 8.3. ON DELETE CASCADE

`ON DELETE CASCADE` tự xóa các hàng con tham chiếu khi cha bị xóa. Trên quan hệ phân cấp, sự xóa có thể **lan xuống cả nhánh** qua nhiều cấp. Xóa Minh có thể kéo theo An, Binh, Chi và Dung. Điều đó có thể hợp lý với một số dữ liệu tạm hoặc cấu trúc chỉ thuộc sở hữu duy nhất của cha, nhưng **rất rủi ro** với nhân sự, lịch sử đơn hàng, bình luận có giá trị hoặc dữ liệu cần lưu giữ.

| Chính sách | Kết quả khi xóa nút có con | Khi nào nên cân nhắc |
|---|---|---|
| `RESTRICT` | Từ chối xóa khi còn hàng con | Bắt buộc xử lý quan hệ rõ ràng trước khi xóa |
| `NO ACTION` | Ràng buộc phải hợp lệ tại thời điểm được kiểm tra; một số DBMS cho phép hoãn kiểm tra | Quy trình nhiều thao tác trong giao dịch theo ngữ nghĩa DBMS |
| `SET NULL` | Cắt liên kết: con trực tiếp thành gốc/không có cha | Nghiệp vụ cho phép hàng con tồn tại độc lập |
| `CASCADE` | Xóa các hàng phụ thuộc theo chuỗi | Chỉ khi đúng nghiệp vụ xóa cả nhánh và đã đánh giá tác động |
| `SET DEFAULT` | Gán khóa ngoại về mặc định | Mặc định phải tương thích và tham chiếu hợp lệ, không tự giải quyết phân cấp |

Trong PostgreSQL, `RESTRICT` và `NO ACTION` gần nhau ở kết quả thường gặp, nhưng `NO ACTION` có thể được trì hoãn khi constraint được khai báo có khả năng hoãn, còn `RESTRICT` không cho trì hoãn kiểm tra theo cùng cách. Không nên thay thế chúng tùy tiện nếu quy trình có cập nhật nhiều nút trong một giao dịch.

### 8.4. Di chuyển một nhánh mà không xóa dữ liệu

Giả sử chuyển **An (4)** từ nhóm Minh sang báo cáo cho **Hoa (3)**:

```sql
UPDATE employees
SET manager_id = 3
WHERE employee_id = 4;
```

Do Chi (6) và Dung (7) vẫn có `manager_id = 4`, cả hai **đi theo nhánh của An** mà không cần cập nhật từng hàng hậu duệ. Sau thay đổi:

```text
Lan
├── Minh
│   └── Binh
└── Hoa
    ├── Giang
    └── An
        ├── Chi
        └── Dung
```

Việc cập nhật chỉ một cột mang lại ưu điểm lớn của mô hình adjacency list: **đổi cha trực tiếp đơn giản**. Nhưng trước khi thực hiện, phải kiểm tra cha mới có tồn tại, không phải chính nút đang di chuyển, và không nằm trong nhánh hậu duệ của nút đó.

> Để giữ dữ liệu ban đầu cho các truy vấn trong bài, hãy chạy ví dụ chuyển nhánh trong giao dịch rồi `ROLLBACK`, hoặc tự nạp lại tập dữ liệu mẫu trước khi làm các ví dụ khác.

```sql
BEGIN;
UPDATE employees SET manager_id = 3 WHERE employee_id = 4;
-- Quan sát cây sau khi đổi cha ở đây.
ROLLBACK;
```

## 9. Các mô hình lưu cây phổ biến

Khóa ngoại tự tham chiếu tạo nên **adjacency list**, nhưng không phải cách duy nhất để lưu dữ liệu phân cấp.

| Mô hình | Cách lưu | Ưu điểm chính | Đánh đổi thường gặp |
|---|---|---|---|
| **Adjacency list** | Mỗi hàng có `parent_id` tham chiếu khóa của chính bảng | Dễ hiểu, dễ thêm và đổi cha trực tiếp, dùng FK thông thường | Truy vấn nhiều cấp thường cần CTE đệ quy |
| **Materialized path** | Lưu đường đi như `/1/2/4/6/` hoặc kiểu chuyên dụng | Có thể lọc cả nhánh theo tiền tố/path | Đổi cha phải cập nhật đường đi của nhiều hậu duệ; cần kiểm soát định dạng |
| **Closure table** | Bảng riêng lưu mọi cặp tổ tiên–hậu duệ và độ sâu | Truy vấn tổ tiên/hậu duệ nhanh và trực tiếp | Số hàng quan hệ tăng; thêm/xóa/di chuyển nhánh cần cập nhật nhiều hàng |
| **Nested sets** | Mỗi nút lưu giới hạn trái/phải của miền cây | Truy vấn toàn bộ nhánh theo khoảng hiệu quả | Chèn và đổi nhánh phức tạp, thường tác động nhiều nút |

Trong PostgreSQL còn có extension như `ltree` để lưu và truy vấn đường đi phân cấp. Những lựa chọn này không thay thế hoàn toàn yêu cầu bảo đảm dữ liệu hợp lệ; chúng chỉ thay đổi cách lưu, truy vấn và chi phí cập nhật.

**Nên bắt đầu bằng adjacency list khi** dữ liệu có cha trực tiếp rõ ràng, việc thêm/chuyển nút diễn ra thường xuyên và nhu cầu duyệt nhiều cấp có thể phục vụ bằng recursive CTE cùng chỉ mục thích hợp. Khi hệ thống liên tục truy vấn các nhánh rất lớn, phân tích hiệu năng thực tế trước khi cân nhắc closure table hay materialized path.

### 9.1. Khi nào cấu trúc không còn là cây?

Một cây đơn giản cho phép mỗi nút **tối đa một cha**. Nếu một đối tượng được phép có **nhiều cha** (ví dụ một chủ đề thuộc nhiều danh mục), một cột `parent_id` không biểu diễn hết quan hệ. Khi ấy thường cần **bảng nối cạnh**:

```sql
CREATE TABLE topics (
    topic_id INTEGER PRIMARY KEY,
    topic_name VARCHAR(100) NOT NULL
);

CREATE TABLE topic_relations (
    parent_topic_id INTEGER NOT NULL REFERENCES topics(topic_id),
    child_topic_id INTEGER NOT NULL REFERENCES topics(topic_id),
    PRIMARY KEY (parent_topic_id, child_topic_id),
    CHECK (parent_topic_id <> child_topic_id)
);
```

Đây là mô hình đồ thị có hướng, có thể có nhiều cha. `CHECK` trên chỉ chặn một cạnh tự trỏ trực tiếp; vấn đề chu trình qua nhiều cạnh vẫn cần xử lý nếu đồ thị phải phi chu trình (*directed acyclic graph*, DAG). Không nên cố ép mô hình nhiều cha vào một `parent_id` duy nhất rồi làm mất quan hệ nghiệp vụ.

## 10. Hiệu năng và bảo đảm toàn vẹn khi cây lớn

### 10.1. Chỉ mục cho cạnh cha–con

Truy vấn lấy cấp dưới trực tiếp:

```sql
SELECT employee_id
FROM employees
WHERE manager_id = 2;
```

Và bước đệ quy:

```sql
JOIN employees AS child
    ON child.manager_id = parent.employee_id
```

đều có thể tận dụng chỉ mục trên `manager_id`. Ở PostgreSQL, tạo `FOREIGN KEY` không mặc nhiên tạo chỉ mục cho cột ở phía con, vì vậy cần cân nhắc riêng. Chỉ mục không bảo đảm mọi truy vấn sẽ dùng nó; bộ tối ưu có thể chọn quét bảng với dữ liệu nhỏ. Với cây lớn, hãy quan sát kế hoạch bằng `EXPLAIN`/`EXPLAIN ANALYZE` trong môi trường phù hợp.

### 10.2. Tránh duyệt cây không giới hạn vì lỗi dữ liệu

CTE đệ quy chạy lặp đến khi bước đệ quy không còn hàng. Nếu quan hệ có chu trình mà không có điều kiện phát hiện, kết quả có thể tăng không ngừng hoặc chạm giới hạn tài nguyên. Các ví dụ trong bài giữ `path` và kiểm tra `ANY(path)` để ngăn lặp trong cùng đường đi.

Với cây rất lớn hoặc sâu, việc lưu mảng đường đi ở mọi bước có chi phí bộ nhớ. Có thể thêm **giới hạn độ sâu có chủ đích** nếu nghiệp vụ có giới hạn, hoặc dùng chức năng `CYCLE` của những phiên bản DBMS hỗ trợ. Tuy nhiên, giới hạn độ sâu chỉ bảo vệ một truy vấn; **không thay thế việc kiểm tra tính hợp lệ của cây khi ghi**.

### 10.3. Phân biệt toàn vẹn tham chiếu và toàn vẹn cây

Khóa ngoại bảo đảm **ID cha tồn tại**, nhưng không đủ bảo đảm **cấu trúc phân cấp là một cây hợp lệ**. Nếu hệ thống bắt buộc các quy tắc như “không chu trình”, “mỗi công ty chỉ một gốc” hoặc “không quá bảy cấp”, cần mô tả và thực thi chúng riêng.

Khi nhiều giao dịch có thể đổi cha cùng lúc, cơ chế ghi phải bảo đảm hai thao tác không cùng tạo ra một chu trình; việc kiểm tra ở ứng dụng mà không phối hợp khóa/đồng bộ có thể có *race condition*. Một số hệ thống dùng trigger kiểm tra đệ quy trong giao dịch với chiến lược khóa phù hợp; những hệ thống khác dùng dịch vụ ghi duy nhất hoặc mô hình closure table được duy trì nhất quán. Mức bảo đảm phụ thuộc DBMS và kiến trúc xử lý đồng thời.

### 10.4. Xử lý xóa theo nghiệp vụ và dữ liệu lịch sử

Đối với cây danh mục, đôi khi được phép xóa cả nhánh. Với nhân sự, thông tin tổ chức có lịch sử, việc xóa nhân viên có thể làm mất khả năng đối chiếu các báo cáo cũ. Có thể cần:

- Trạng thái `active`/`inactive` thay vì xóa vật lý.
- Bảng lịch sử quản lý theo khoảng thời gian để biết “ai quản lý ai” tại một ngày trước đây.
- Quy trình chuyển cấp dưới trước khi ngưng sử dụng bản ghi cha.

Đây là quyết định nghiệp vụ; `ON DELETE` chỉ là cơ chế thực thi một phần của chính sách đó.

## 11. Các lỗi thường gặp

**“FOREIGN KEY chỉ được trỏ sang bảng khác.”** Không đúng. Cột `employees.manager_id` có thể tham chiếu ngay `employees.employee_id`.

**“Tạo FK tự động chặn mọi chu trình.”** Sai. FK chỉ kiểm tra sự tồn tại của ID được tham chiếu; chu trình ba nút vẫn có thể thỏa FK. `CHECK (manager_id <> employee_id)` chỉ ngăn tự trỏ trực tiếp.

**“Nút gốc phải có parent_id = 0.”** Không nhất thiết và thường không phù hợp: nếu ID 0 không có thật, FK sẽ từ chối. `NULL` là cách phổ biến diễn tả “không có cha” khi cột được phép thiếu giá trị.

**“INNER JOIN tự giữ mọi nút của cây.”** Không: nút gốc với `manager_id IS NULL` không có cặp quản lý để ghép. Dùng `LEFT JOIN` khi muốn hiển thị cả gốc.

**“COUNT(*) sau LEFT JOIN cho số con bằng 0 nếu không có con.”** Không. Hàng trái vẫn được giữ với các cột phải `NULL`; `COUNT(*)` đếm nó. Dùng `COUNT(child.employee_id)` hoặc cách đếm có điều kiện.

**“Tìm cấp dưới trực tiếp là đã tìm tất cả cấp dưới.”** Không: `WHERE manager_id = 2` chỉ thấy An và Binh, còn Chi và Dung thuộc tầng sâu hơn.

**“ON DELETE CASCADE chỉ xóa con trực tiếp.”** Trên quan hệ tự tham chiếu có nhiều tầng, tác động có thể lan theo chuỗi liên kết và xóa cả nhánh. Cần xác định rõ hậu quả trước khi chọn chính sách.

**“Chạy CTE từ gốc không thấy chu trình nghĩa là dữ liệu không có chu trình.”** Sai: một nhóm nút bị khóa trong chu trình không còn đường đi từ gốc có thể bị bỏ sót. Kiểm tra toàn vẹn cây nên xét mọi nút khi cần.

**“Dùng `NULL` trong manager_id khiến người đó mất khỏi hệ thống.”** Không. Nhân viên vẫn tồn tại; họ chỉ không có liên kết đến quản lý theo mô hình hiện tại.

## 12. Bài tập thực hành

### Bài 1 — Tìm quản lý trực tiếp

Với dữ liệu ở mục 4, viết truy vấn hiển thị `employee_name` và `manager_name` cho **mọi nhân viên**. Chỉ ra lý do phải dùng `LEFT JOIN` nếu muốn Lan xuất hiện.

Gợi ý: nối `employees AS e` với `employees AS m` theo `e.manager_id = m.employee_id`.

### Bài 2 — So sánh hai cấp và nhiều cấp

Viết hai câu:

1. Trả về cấp dưới **trực tiếp** của Minh (`employee_id = 2`).
2. Trả về **mọi hậu duệ** của Minh, không kể chính Minh, bằng `WITH RECURSIVE`.

Đáp án dự kiến: câu (1) có **An, Binh**; câu (2) có **An, Binh, Chi, Dung**. Hãy giải thích vì sao khác nhau.

### Bài 3 — Thiết kế cây danh mục sản phẩm

Tạo bảng `categories` với `category_id` là khóa chính, `category_name` là tên, `parent_category_id` là khóa ngoại tự tham chiếu có thể `NULL`.

```sql
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    parent_category_id INTEGER,
    FOREIGN KEY (parent_category_id)
        REFERENCES categories(category_id)
        ON DELETE RESTRICT,
    CHECK (
        parent_category_id IS NULL
        OR parent_category_id <> category_id
    )
);
```

Nạp các danh mục `Electronics` (gốc), `Computers` (con), `Laptops` (cháu), `Phones` (con). Viết truy vấn `WITH RECURSIVE` hiển thị đường phân cấp. Nếu đổi cha của `Computers` thành `Laptops`, dự đoán điều gì và giải thích vì sao phải chặn thao tác này dù các ID đều tồn tại.

### Bài 4 — Xử lý xóa nút trung gian

Giả sử phải thôi dùng bản ghi **An (4)** trong bảng nhân viên và vẫn giữ Chi (6), Dung (7). So sánh ba cách:

- Chuyển Chi và Dung sang một quản lý hợp lệ khác, sau đó xóa An khi không còn ai tham chiếu.
- Dùng mô hình `ON DELETE SET NULL` để hai người thành nút không có cha.
- Dùng `ON DELETE CASCADE` và phân tích vì sao nguy hiểm với dữ liệu nhân viên.

Với lược đồ mẫu dùng `RESTRICT`, cách thứ nhất phù hợp khi tổ chức cần giữ đầy đủ nhân viên và chỉ cập nhật quan hệ quản lý.

### Bài 5 — Kiểm tra tính hợp lệ của cây

Giải thích vì sao việc cập nhật `manager_id` của Minh (2) thành Chi (6) sẽ tạo vòng lặp. Viết một truy vấn đệ quy từ Minh để chứng minh Chi là hậu duệ của Minh trước khi cập nhật. Sau đó trả lời: vì sao kiểm tra trước cập nhật trong ứng dụng cần có cơ chế đồng bộ khi nhiều giao dịch cùng đổi cha?

### Bài 6 — Chọn mô hình dữ liệu

Một hệ thống có chủ đề học tập; mỗi chủ đề có thể thuộc **hai chuyên mục cha**. Một cột `parent_id` trong cùng bảng có đủ không? Nếu không, hãy phác thảo bảng `topic_relations(parent_topic_id, child_topic_id)` với hai khóa ngoại tham chiếu bảng `topics`. Nêu ràng buộc ngăn tự trỏ trực tiếp và nguyên nhân vẫn cần kiểm tra chu trình nếu yêu cầu dữ liệu là DAG.

## Kết luận

**Khóa ngoại tự tham chiếu** cho phép một hàng tham chiếu một hàng khác **trong cùng bảng**, từ đó biểu diễn quan hệ cha–con bằng cột như `manager_id` hoặc `parent_category_id`. Kết hợp `PRIMARY KEY`, `FOREIGN KEY`, `NULL` cho nút gốc, self JOIN và `WITH RECURSIVE`, ta có thể lưu và truy vấn phân cấp một hoặc nhiều tầng một cách rõ ràng.

Điểm cần nhớ là **toàn vẹn tham chiếu không đồng nghĩa toàn vẹn cây**. FK ngăn ID cha không tồn tại, nhưng việc không có chu trình, cách xóa nhánh, số gốc và các quy tắc phân cấp phải được thiết kế thêm theo nghiệp vụ. Với mô hình phù hợp, cơ chế kiểm soát cập nhật nhất quán và chỉ mục ở cột khóa ngoại, cơ sở dữ liệu quan hệ có thể quản lý hiệu quả nhiều cấu trúc phân cấp thường gặp trong hệ thống phần mềm.
