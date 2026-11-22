# Kiểu dữ liệu cột CTE đệ quy và nguy cơ cắt ngắn dữ liệu

Trong một truy vấn đệ quy, mỗi vòng lặp có thể tạo ra giá trị dài hơn hoặc lớn hơn vòng trước. Ví dụ, khi duyệt cây phòng ban, cột `path` có thể nối thêm tên của từng cấp; khi tính tổng tích lũy, cột số có thể tăng qua mỗi bước. Nếu kiểu dữ liệu của CTE được suy ra quá hẹp từ phần truy vấn khởi tạo, giá trị ở phần đệ quy có thể bị cắt ngắn hoặc gây lỗi.

Trong MySQL 8.0 trở lên, kiểu dữ liệu của các cột trong recursive CTE được xác định từ phần không đệ quy (anchor member). MySQL không tự mở rộng kiểu cột chỉ vì biểu thức ở recursive member tạo ra giá trị dài hơn. Vì vậy, cần thiết kế kiểu ngay trong anchor bằng `CAST()` với độ dài, precision và signedness đủ dùng. Bài học này thuộc module **DATABASE_MYSQL**, tập trung vào cách suy luận kiểu, rủi ro truncation/overflow và cách kiểm chứng trong các truy vấn cây.

## 1. Cấu trúc của recursive CTE

CTE đệ quy thường có hai phần:

- **Anchor member**: truy vấn khởi tạo, tạo ra các hàng ban đầu. Đây là phần không đệ quy.
- **Recursive member**: truy vấn tham chiếu lại chính CTE để sinh các hàng tiếp theo.

Ví dụ khung tổng quát:

```sql
WITH RECURSIVE hierarchy AS (
    -- Anchor member
    SELECT ...

    UNION ALL

    -- Recursive member
    SELECT ...
    FROM hierarchy AS h
    JOIN ...
)
SELECT *
FROM hierarchy;
```

MySQL bắt đầu với kết quả anchor, sau đó dùng các hàng của vòng trước để thực thi recursive member và bổ sung hàng mới. Quá trình tiếp tục cho đến khi recursive member không sinh thêm hàng hoặc chạm giới hạn đệ quy.

Điểm quan trọng về kiểu dữ liệu: **MySQL suy ra tên và kiểu các cột của CTE từ anchor member**. Các biểu thức tương ứng ở recursive member phải tương thích với kiểu đã được xác định đó. Nếu recursive member tạo ra chuỗi dài hơn hoặc số vượt miền kiểu anchor, kiểu CTE không tự nới rộng để chứa giá trị mới.

## 2. Kiểu dữ liệu được suy ra từ anchor member

Xét CTE có cột `path`:

```sql
WITH RECURSIVE paths AS (
    SELECT
        CAST(1 AS UNSIGNED) AS step_no,
        CAST('A' AS CHAR(1)) AS path

    UNION ALL

    SELECT step_no + 1, CONCAT(path, 'B')
    FROM paths
    WHERE step_no < 5
)
SELECT step_no, path
FROM paths;
```

Anchor tạo ra `path` có kiểu `CHAR(1)`. Recursive member nối thêm ký tự `B`, nhưng điều đó không làm cột CTE tự đổi thành `CHAR(2)`, `CHAR(3)` hoặc `VARCHAR` dài hơn. Với chế độ SQL phù hợp, truy vấn có thể báo lỗi về dữ liệu bị cắt; ở chế độ không strict, giá trị có thể bị cắt và phát warning.

Không nên dựa vào độ dài biểu thức ở recursive member để đoán kiểu cuối cùng. Hãy chủ động khai báo kiểu mong muốn ngay ở anchor:

```sql
WITH RECURSIVE paths AS (
    SELECT
        CAST(1 AS UNSIGNED) AS step_no,
        CAST('A' AS CHAR(20)) AS path

    UNION ALL

    SELECT step_no + 1, CONCAT(path, 'B')
    FROM paths
    WHERE step_no < 5
)
SELECT step_no, path
FROM paths;
```

Ở ví dụ này, anchor cấp dung lượng ký tự tối đa 20 cho cột `path`; recursive member có thể nối chuỗi trong giới hạn đó.

### Không phải kiểu dữ liệu được hợp nhất theo giá trị lớn nhất

Trong một số phép `UNION` thông thường, người viết có thể quan sát việc MySQL xác định kiểu chung cho các nhánh. Với recursive CTE, không nên suy luận rằng kiểu của anchor và recursive member sẽ được hợp nhất thành kiểu đủ rộng nhất. Quy tắc của MySQL là kiểu cột recursive CTE lấy từ phần anchor; recursive member không mở rộng kiểu đó.

Do vậy, hãy coi anchor là nơi khai báo hợp đồng kiểu dữ liệu cho toàn bộ quá trình đệ quy.

## 3. Ví dụ thực tế: duyệt cây phòng ban và tạo đường dẫn

Giả sử có bảng nhân viên tự tham chiếu:

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    manager_id BIGINT UNSIGNED NULL,
    employee_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employees_manager (manager_id),
    CONSTRAINT fk_employees_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees (employee_id)
) ENGINE=InnoDB;
```

Mỗi nhân viên có thể có một quản lý; nhân viên không có quản lý có `manager_id IS NULL`. Ta muốn bắt đầu từ nhân viên gốc rồi lần theo các cấp dưới, đồng thời tạo chuỗi đường dẫn tên.

```sql
WITH RECURSIVE employee_tree (
    employee_id,
    manager_id,
    employee_name,
    path,
    depth
) AS (
    SELECT
        e.employee_id,
        e.manager_id,
        e.employee_name,
        CAST(e.employee_name AS CHAR(1000) CHARACTER SET utf8mb4) AS path,
        CAST(0 AS UNSIGNED) AS depth
    FROM employees AS e
    WHERE e.manager_id IS NULL

    UNION ALL

    SELECT
        child.employee_id,
        child.manager_id,
        child.employee_name,
        CONCAT(parent.path, ' / ', child.employee_name) AS path,
        parent.depth + 1 AS depth
    FROM employees AS child
    JOIN employee_tree AS parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id, manager_id, employee_name, path, depth
FROM employee_tree
ORDER BY path;
```

Trong anchor:

- `CAST(e.employee_name AS CHAR(1000) CHARACTER SET utf8mb4)` xác định `path` có độ dài và character set đủ lớn để nối nhiều cấp tên Unicode.
- `CAST(0 AS UNSIGNED)` xác định kiểu số không âm cho `depth`.

Trong recursive member:

- `CONCAT(parent.path, ' / ', child.employee_name)` nối thêm tên cấp dưới.
- `parent.depth + 1` tăng độ sâu mỗi cấp.

Nếu bỏ `CAST(... AS CHAR(1000))`, kiểu `path` có thể được suy ra từ độ dài `employee_name` ở anchor. Khi nối thêm tên ở các cấp sau, kết quả vượt độ dài đó và có nguy cơ bị cắt hoặc lỗi.

Độ dài 1000 chỉ là ví dụ. Hãy ước lượng độ sâu tối đa và độ dài tên theo nghiệp vụ; nếu đường dẫn có thể dài hơn, chọn giới hạn phù hợp hoặc dùng một mô hình lưu trữ khác. `CHAR(N)` trong ngữ cảnh này xác định độ rộng kiểu ký tự của biểu thức CTE, không phải lời bảo đảm rằng đường dẫn thực tế luôn có đúng N ký tự.

## 4. Cắt ngắn chuỗi và ảnh hưởng của SQL mode

Khi giá trị recursive member dài hơn kiểu cột đã xác định, MySQL có thể xử lý khác nhau tùy `sql_mode` và ngữ cảnh thực thi:

- Với strict mode, truy vấn thường báo lỗi khi giá trị bị cắt thay vì âm thầm chấp nhận.
- Khi không strict, giá trị có thể bị cắt về độ rộng cột và phát warning.

Kiểm tra SQL mode:

```sql
SELECT @@SESSION.sql_mode;
```

Sau một truy vấn thử nghiệm, có thể kiểm tra warning:

```sql
SHOW WARNINGS;
```

Không dùng việc tắt strict mode để làm truy vấn đệ quy chạy qua. Nếu dữ liệu bị cắt, kết quả đường dẫn hoặc giá trị tích lũy sẽ sai nhưng có thể khó nhận ra. Hãy sửa kiểu ở anchor để biểu diễn đủ miền giá trị.

Lưu ý: `SHOW WARNINGS` phải được chạy ngay sau câu lệnh cần kiểm tra; một câu lệnh khác có thể làm thay đổi danh sách warning được hiển thị.

## 5. Chọn độ dài CHAR/VARCHAR cho cột chuỗi đệ quy

Khi thiết kế cột chuỗi trong recursive CTE, cần xem xét:

1. Độ dài tối đa của giá trị ở anchor.
2. Số ký tự được nối thêm ở mỗi vòng.
3. Độ sâu tối đa của cây hoặc số vòng lặp.
4. Character set: `utf8mb4` có thể dùng tối đa 4 byte cho một ký tự.
5. Giới hạn kiểu dữ liệu và kích thước kết quả trung gian.

Ví dụ nếu tên mỗi nút tối đa 120 ký tự, đường dẫn tối đa 8 cấp và dấu phân cách dài 3 ký tự, có thể ước lượng độ dài cần thiết theo công thức:

\[
L_{max} = 8 \times 120 + 7 \times 3 = 981
\]

Có thể chọn `CHAR(1000)` hoặc một giới hạn khác có khoảng dự phòng. Nếu độ sâu không có giới hạn thực tế, không nên chọn một con số tùy ý rồi giả định sẽ luôn đủ.

Đối với dữ liệu Unicode, độ dài ký tự và số byte không giống nhau. `CHAR(N)`/`VARCHAR(N)` giới hạn theo số ký tự; dung lượng byte còn phụ thuộc character set. Một chuỗi 1000 ký tự `utf8mb4` có thể cần tới khoảng 4000 byte cho phần dữ liệu ký tự.

## 6. Nguy cơ tràn số và precision trong cột đệ quy

Không chỉ chuỗi mới có nguy cơ vượt kiểu. Các cột số cũng có thể vượt miền dữ liệu anchor:

- `TINYINT`/`SMALLINT` có miền nhỏ; tăng bộ đếm qua nhiều vòng có thể vượt giới hạn.
- `INT` có thể không đủ cho độ sâu, tổng tích lũy hoặc số lượng lớn.
- `DECIMAL(M,D)` có precision/scale hữu hạn; phép cộng hoặc nhân lặp lại có thể tạo giá trị vượt precision.
- `UNSIGNED` không lưu số âm; nếu phép đệ quy có thể giảm xuống dưới 0, kiểu này không phù hợp.

Ví dụ bộ đếm cần kiểu đủ lớn:

```sql
WITH RECURSIVE sequence_numbers (n) AS (
    SELECT CAST(1 AS UNSIGNED)

    UNION ALL

    SELECT n + 1
    FROM sequence_numbers
    WHERE n < 100
)
SELECT MAX(n) AS max_value
FROM sequence_numbers;
```

Anchor xác định `n` là số nguyên unsigned. Nếu bài toán có thể tạo giá trị âm, dùng kiểu signed phù hợp. Nếu tổng tích lũy có thể vượt `BIGINT`, hãy xem xét `DECIMAL` với precision đủ lớn hoặc thay đổi cách tính.

Ví dụ tổng tích lũy dạng thập phân:

```sql
WITH RECURSIVE running_totals (step_no, amount) AS (
    SELECT
        CAST(1 AS UNSIGNED),
        CAST(100.00 AS DECIMAL(20,2))

    UNION ALL

    SELECT
        step_no + 1,
        amount + CAST(25.50 AS DECIMAL(20,2))
    FROM running_totals
    WHERE step_no < 10
)
SELECT step_no, amount
FROM running_totals;
```

Anchor khai báo `amount` là `DECIMAL(20,2)` để có đủ precision cho các bước cộng. Chọn precision theo giá trị lớn nhất có thể phát sinh, không chỉ theo giá trị khởi tạo.

## 7. CAST ở anchor member là nơi kiểm soát kiểu

Khi cần kiểu cụ thể, hãy ép kiểu biểu thức trong anchor:

```sql
WITH RECURSIVE walk (node_id, label_path, total_weight) AS (
    SELECT
        root.node_id,
        CAST(root.label AS CHAR(2000)),
        CAST(root.weight AS DECIMAL(20,4))
    FROM graph_nodes AS root
    WHERE root.parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        CONCAT(w.label_path, '/', child.label),
        w.total_weight + child.weight
    FROM graph_nodes AS child
    JOIN walk AS w
      ON child.parent_id = w.node_id
)
SELECT node_id, label_path, total_weight
FROM walk;
```

Ở ví dụ này, anchor quyết định:

- `node_id` theo kiểu cột `root.node_id`.
- `label_path` là chuỗi có độ rộng 2000 ký tự.
- `total_weight` là `DECIMAL(20,4)`.

Recursive member cần trả biểu thức tương thích với ba kiểu đó. Nếu kiểu nguồn của `child.weight` khác, hãy chuẩn hóa kiểu trong schema hoặc ép biểu thức thích hợp. Không chỉ ép kiểu ở SELECT ngoài cùng vì khi đó phép tính đệ quy đã diễn ra với kiểu CTE được xác định từ anchor.

## 8. Tên cột và kiểu dữ liệu phải khớp giữa các thành viên

Nên khai báo danh sách tên cột CTE tường minh:

```sql
WITH RECURSIVE category_tree (
    category_id,
    parent_id,
    category_path,
    level_no
) AS (
    SELECT ...
    UNION ALL
    SELECT ...
)
SELECT * FROM category_tree;
```

Danh sách cột giúp xác định thứ tự và ý nghĩa của từng vị trí. Các nhánh anchor và recursive member phải trả về cùng số cột theo đúng thứ tự tương ứng. Nếu vô tình đảo vị trí `category_path` và `level_no`, MySQL sẽ cố ép kiểu theo vị trí và có thể báo lỗi hoặc tạo kết quả sai.

Ví dụ không nên làm:

```sql
WITH RECURSIVE bad_tree (node_id, node_path, depth) AS (
    SELECT id, CAST(name AS CHAR(500)), 0
    FROM nodes
    WHERE parent_id IS NULL

    UNION ALL

    -- Thứ tự biểu thức sai: depth đứng trước path
    SELECT child.id, parent.depth + 1,
           CONCAT(parent.node_path, '/', child.name)
    FROM nodes AS child
    JOIN bad_tree AS parent
      ON child.parent_id = parent.node_id
)
SELECT * FROM bad_tree;
```

Ở recursive member, cột thứ hai đang trả số thay cho chuỗi, cột thứ ba trả chuỗi thay cho số. Hãy đối chiếu thứ tự cột trong tất cả các thành viên trước khi kiểm tra nội dung.

## 9. Kiểm soát số vòng đệ quy và độ dài đường dẫn

Một recursive CTE cần điều kiện dừng rõ ràng. Nếu dữ liệu có chu trình hoặc điều kiện đệ quy không giảm về điểm dừng, truy vấn có thể chạy đến giới hạn đệ quy và thất bại.

MySQL cung cấp biến `cte_max_recursion_depth` để giới hạn độ sâu đệ quy. Giá trị mặc định phổ biến là 1000; có thể kiểm tra trong session:

```sql
SELECT @@SESSION.cte_max_recursion_depth;
```

Có thể tăng giới hạn cho session nếu bài toán hợp lệ cần độ sâu lớn hơn:

```sql
SET SESSION cte_max_recursion_depth = 2000;
```

Không tăng giới hạn chỉ để che một chu trình dữ liệu hoặc thiếu điều kiện dừng. Hãy xác minh dữ liệu cây, khóa cha/con và logic đệ quy trước.

Ngoài giới hạn số vòng, cần có giới hạn độ dài đường dẫn. Nếu mỗi vòng nối thêm một tên, độ dài tăng theo độ sâu. Một CTE có thể dừng đúng nhưng vẫn vượt độ rộng chuỗi nếu anchor khai báo quá nhỏ.

## 10. Tránh lặp vô hạn khi dữ liệu có chu trình

Một cấu trúc cây đúng phải không có chu trình. Tuy nhiên, dữ liệu tự tham chiếu có thể bị lỗi nếu ứng dụng cho phép tạo quan hệ vòng, ví dụ A là cha của B, B là cha của C và C lại là cha của A.

Khi duyệt đồ thị có khả năng có chu trình, cần theo dõi các node đã đi qua. Ví dụ đơn giản với ID số có thể nối đường dẫn ID và kiểm tra node tiếp theo chưa xuất hiện:

```sql
WITH RECURSIVE graph_walk (node_id, visited_path, depth) AS (
    SELECT
        node_id,
        CAST(CONCAT('/', node_id, '/') AS CHAR(4096)),
        CAST(0 AS UNSIGNED)
    FROM graph_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        edge.child_id,
        CONCAT(w.visited_path, edge.child_id, '/'),
        w.depth + 1
    FROM graph_edges AS edge
    JOIN graph_walk AS w
      ON edge.parent_id = w.node_id
    WHERE LOCATE(
        CONCAT('/', edge.child_id, '/'),
        w.visited_path
    ) = 0
      AND w.depth < 100
)
SELECT node_id, visited_path, depth
FROM graph_walk;
```

`visited_path` được ép sang `CHAR(4096)` ngay ở anchor để đủ chỗ lưu đường đi; `LOCATE()` kiểm tra ID con đã xuất hiện trong đường dẫn hay chưa; điều kiện `depth < 100` là giới hạn nghiệp vụ bổ sung. Ví dụ giả định ID số được phân cách bằng `/`, tránh nhầm ID `1` với `11`.

Đối với ID chuỗi, cách nối đường dẫn và tìm kiếm cần xử lý escaping/delimiter để không nhầm một ID là phần con của ID khác. Với đồ thị lớn hoặc đường dẫn dài, một chuỗi path có thể không phải cách lưu dấu vết hiệu quả; hãy cân nhắc thiết kế dữ liệu và thuật toán khác.

## 11. Kiểm tra kiểu dữ liệu thực tế của CTE

Có thể bọc CTE trong truy vấn ngoài và dùng các hàm kiểm tra kiểu/độ dài để xác minh kết quả:

```sql
WITH RECURSIVE paths AS (
    SELECT CAST('root' AS CHAR(100)) AS path

    UNION ALL

    SELECT CONCAT(path, '/child')
    FROM paths
    WHERE CHAR_LENGTH(path) < 30
)
SELECT
    path,
    CHAR_LENGTH(path) AS character_count,
    LENGTH(path) AS byte_count,
    CHARSET(path) AS character_set,
    COLLATION(path) AS collation_name
FROM paths;
```

Các hàm hữu ích:

- `CHAR_LENGTH(expr)`: số ký tự trong chuỗi.
- `LENGTH(expr)`: số byte của chuỗi.
- `CHARSET(expr)`: character set của biểu thức.
- `COLLATION(expr)`: collation của biểu thức.
- `SHOW WARNINGS`: xem warning phát sinh từ câu lệnh gần nhất.

Nếu cần xác minh kiểu SQL chính xác hơn, có thể tạo một view hoặc bảng thử nghiệm từ kết quả CTE rồi xem metadata bằng `DESCRIBE`/`INFORMATION_SCHEMA.COLUMNS`. Không nên suy luận độ rộng kiểu chỉ từ một vài giá trị dữ liệu đầu ra.

## 12. Checklist thiết kế kiểu dữ liệu cho recursive CTE

Trước khi triển khai truy vấn đệ quy, hãy kiểm tra:

1. Anchor member đã khai báo đúng số cột và đúng thứ tự chưa?
2. Kiểu dữ liệu của từng cột có phù hợp với giá trị lớn nhất có thể sinh ra không?
3. Cột chuỗi đã được `CAST` đủ dài ở anchor chưa?
4. Cột số đã chọn đúng signedness, integer width hoặc `DECIMAL` precision/scale chưa?
5. Character set/collation của chuỗi có phù hợp với dữ liệu được nối không?
6. Recursive member trả biểu thức tương thích với kiểu anchor không?
7. Có nguy cơ truncation, rounding hoặc overflow không?
8. SQL mode strict có đang bật để phát hiện dữ liệu vượt miền không?
9. Điều kiện dừng và `cte_max_recursion_depth` có phù hợp không?
10. Dữ liệu có thể chứa chu trình không; nếu có, đã có cơ chế phát hiện node đã thăm chưa?
11. Độ sâu tối đa có thể làm đường dẫn vượt giới hạn ký tự đã chọn không?
12. Truy vấn đã được thử với dữ liệu sâu và dài gần giới hạn thực tế chưa?

## 13. Bài tập thực hành

1. Tạo bảng `employees` tự tham chiếu và viết recursive CTE duyệt từ quản lý gốc xuống nhân viên cấp dưới.
2. Tạo cột `path` bằng `CAST(employee_name AS CHAR(20))`; dùng tên nhiều cấp để quan sát nguy cơ cắt ngắn.
3. Tăng độ rộng anchor lên `CHAR(1000)` và so sánh kết quả.
4. Bỏ CAST ở anchor, kiểm tra kết quả và `SHOW WARNINGS` dưới SQL mode hiện tại.
5. Viết CTE đếm cấp bằng `TINYINT`, sau đó thử kiểu lớn hơn; giải thích nguy cơ overflow.
6. Viết CTE tổng tích lũy bằng `DECIMAL(20,2)` và xác định precision cần thiết cho dữ liệu lớn nhất.
7. Thử đảo thứ tự cột giữa anchor và recursive member; đọc lỗi hoặc kết quả để hiểu việc ghép cột theo vị trí.
8. Tạo dữ liệu có chu trình trong bảng cạnh và bổ sung `visited_path` cùng điều kiện dừng để ngăn lặp.
9. Thử điều chỉnh `cte_max_recursion_depth` trong session; phân biệt giới hạn kỹ thuật với điều kiện dừng nghiệp vụ.

Bạn hoàn thành bài khi giải thích được vì sao kiểu dữ liệu recursive CTE được quyết định từ anchor member, biết ép kiểu chuỗi/số đủ rộng ngay từ phần khởi tạo, nhận diện nguy cơ cắt ngắn hoặc overflow và kiểm soát độ sâu/chu trình. Hãy thiết kế kiểu dữ liệu dựa trên giá trị tối đa có thể phát sinh trong toàn bộ quá trình đệ quy, không chỉ giá trị đầu tiên.
