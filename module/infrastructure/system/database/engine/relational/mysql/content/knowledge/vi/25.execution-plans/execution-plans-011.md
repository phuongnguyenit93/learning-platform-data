# Đọc kế hoạch cho CTE, derived table, subquery và UNION

Khi một câu SQL có CTE, derived table, subquery hoặc UNION, EXPLAIN cần được đọc theo từng query block và mối quan hệ giữa chúng. Một query block có thể được optimizer gộp vào query block bên ngoài (merge), chạy riêng rồi lưu kết quả tạm (materialize), biến đổi thành semijoin/antijoin hoặc thực thi như một nhánh của UNION.

Vì vậy, không nên chỉ nhìn một dòng EXPLAIN rồi kết luận toàn bộ truy vấn đang chạy theo một cách duy nhất. Hãy xác định từng query block, xem nó còn tồn tại riêng trong execution plan hay đã được merge, kiểm tra nơi materialization xảy ra, rồi theo dõi số hàng và số vòng lặp ở các iterator.

Bài viết hướng dẫn cách đọc kế hoạch của:

- CTE được khai báo bằng WITH, gồm CTE được tham chiếu một lần hoặc nhiều lần.
- Derived table được đặt trong mệnh đề FROM.
- Subquery trong WHERE, SELECT hoặc điều kiện JOIN, gồm correlated subquery, EXISTS và IN.
- UNION và UNION ALL, gồm khử trùng lặp và sắp xếp kết quả.

Các ví dụ dùng MySQL 8.0. Một số cách hiển thị và khả năng tối ưu phụ thuộc phiên bản cụ thể; luôn kiểm tra kế hoạch trên server đang chạy.

## 1. Query block là gì?

Query block là một đơn vị SELECT trong câu SQL. Một câu lệnh có thể có một query block hoặc nhiều query block lồng nhau.

Ví dụ chỉ có một query block:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE active = 1;
~~~

Ví dụ có hai query block: query bên trong là subquery, query bên ngoài sử dụng kết quả của nó.

~~~sql
SELECT employee_id, salary
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE enabled = 1
);
~~~

Ví dụ có CTE:

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = 1
)
SELECT employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

CTE tạo một query block có tên active_employees. Optimizer có thể merge query block này vào query bên ngoài, hoặc materialize kết quả thành một bảng tạm nội bộ.

Trong EXPLAIN dạng truyền thống, cột id và select_type cung cấp dấu hiệu về query block. Trong EXPLAIN FORMAT=JSON, cấu trúc query_block và các nút con giúp nhìn rõ quan hệ lồng nhau. EXPLAIN FORMAT=TREE trình bày các iterator theo cấu trúc cây.

## 2. Chuẩn bị schema minh họa

Các ví dụ sau dùng hai bảng nhân viên và phòng ban, cùng một bảng đơn hàng:

~~~sql
CREATE TABLE departments (
    department_id INT NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (department_id)
) ENGINE = InnoDB;

CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    department_id INT NOT NULL,
    employee_name VARCHAR(120) NOT NULL,
    salary DECIMAL(12, 2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (employee_id),
    KEY idx_employees_department_active
        (department_id, active),
    KEY idx_employees_salary (salary)
) ENGINE = InnoDB;

CREATE TABLE sales_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    employee_id BIGINT UNSIGNED NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_employee_total (employee_id, total),
    KEY idx_orders_total (total)
) ENGINE = InnoDB;
~~~

Trong phần giải thích kế hoạch, tên index chỉ là cấu trúc có sẵn để optimizer cân nhắc. EXPLAIN thực tế vẫn phụ thuộc số lượng hàng, phân bố dữ liệu, thống kê, tham số và phiên bản MySQL.

## 3. Đọc CTE được merge vào query bên ngoài

CTE giúp đặt tên cho một query block để câu SQL dễ đọc và tái sử dụng:

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
)
SELECT employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

CTE này không có GROUP BY, DISTINCT, LIMIT, UNION hoặc các cấu trúc thường ngăn merge. Optimizer có thể merge query block vào query bên ngoài, tương đương về ý nghĩa với:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE active = TRUE
  AND department_id = 10;
~~~

Khi merge thành công:

- CTE không nhất thiết xuất hiện như một bảng tạm riêng trong kế hoạch.
- Điều kiện department_id có thể được kết hợp với active trong cùng query block.
- Optimizer có thể dùng index phù hợp trên employees.
- Không có chi phí tạo và đọc một bảng tạm cho CTE này.

### 3.1. Dấu hiệu trong EXPLAIN

Chạy:

~~~sql
EXPLAIN
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
)
SELECT employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

Nếu CTE được merge, kế hoạch thường chỉ còn access path của bảng employees thay vì một bước đọc bảng tạm mang tên CTE. Trong JSON/TREE, query block có thể được biểu diễn như một phần của query block ngoài sau khi tối ưu.

Đừng yêu cầu EXPLAIN phải luôn có dòng tên CTE. Việc không thấy tên CTE riêng có thể là dấu hiệu nó đã được merge.

## 4. Đọc CTE được materialize

Một CTE có phép tổng hợp thường không thể merge theo quy tắc derived table merge. Ví dụ:

~~~sql
WITH department_summary AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        AVG(salary) AS average_salary
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT
    d.department_name,
    s.employee_count,
    s.average_salary
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

CTE department_summary phải tạo kết quả tổng hợp trước khi query bên ngoài dùng nó. Optimizer có thể materialize CTE vào bảng tạm nội bộ.

Khi materialize:

1. MySQL thực thi query block tạo CTE.
2. Kết quả được ghi vào internal temporary table.
3. Query bên ngoài đọc bảng tạm như một nguồn dữ liệu.
4. Optimizer có thể tạo index nội bộ trên bảng tạm nếu điều đó giúp join hoặc tra cứu.

### 4.1. Dấu hiệu trong EXPLAIN

~~~sql
EXPLAIN FORMAT=JSON
WITH department_summary AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        AVG(salary) AS average_salary
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT
    d.department_name,
    s.employee_count,
    s.average_salary
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

Trong JSON plan, tìm phần thể hiện materialization hoặc materialized_from_subquery. Trong EXPLAIN dạng truyền thống, tùy hình dạng kế hoạch và phiên bản, query block tạo CTE có thể có select_type như DERIVED hoặc MATERIALIZED; query ngoài có thể đọc một tên bảng tạm nội bộ như <derivedN>.

Trong TREE, materialization thường được thể hiện bằng một iterator materialize và một iterator đọc kết quả đã materialize. Hãy đọc node con để biết query block nào tạo bảng tạm và node cha nào tiêu thụ nó.

### 4.2. Materialize không nhất thiết là lỗi

Materialization có chi phí ghi/đọc bảng tạm, nhưng đôi khi giảm lượng công việc tổng thể:

- Kết quả tổng hợp nhỏ hơn đáng kể so với bảng nguồn.
- Query block chỉ cần tính một lần.
- Có nhiều nơi cần đọc cùng kết quả CTE.
- Bảng tạm được tạo index nội bộ để phục vụ phép join hoặc lookup.

Điều cần đo là số hàng tạo ra, kích thước dữ liệu tạm, số lần đọc và số vòng lặp của iterator, không phải chỉ sự xuất hiện của từ materialize.

## 5. CTE được tham chiếu nhiều lần

Một CTE có thể được tham chiếu nhiều lần trong cùng câu lệnh:

~~~sql
WITH department_summary AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        AVG(salary) AS average_salary
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT
    current_summary.department_id,
    current_summary.average_salary,
    previous_summary.department_id AS lower_salary_department
FROM department_summary AS current_summary
JOIN department_summary AS previous_summary
  ON previous_summary.average_salary < current_summary.average_salary
 AND previous_summary.department_id <> current_summary.department_id;
~~~

Khi CTE được materialize và được tham chiếu nhiều lần, MySQL materialize kết quả một lần trong câu lệnh rồi có thể đọc lại kết quả đó ở các vị trí tham chiếu. Optimizer có thể tạo các index khác nhau trên bảng tạm để hỗ trợ từng cách truy cập.

Trong kế hoạch, hãy tìm:

- Một query block tạo kết quả CTE.
- Các node đọc kết quả materialized tương ứng với từng tham chiếu.
- Index hoặc access method được dùng khi đọc bảng tạm.
- Số vòng lặp và số hàng ở từng node đọc.

Không suy ra rằng CTE luôn được thực thi lại từ đầu cho mỗi lần tham chiếu. Cũng không giả định mọi CTE luôn materialize; CTE có thể được merge khi đủ điều kiện.

## 6. Khi nào CTE hoặc derived table không thể merge?

MySQL có thể merge một derived table, view hoặc CTE vào query block ngoài, nhưng một số cấu trúc ngăn việc merge. Các trường hợp thường gặp gồm:

- Có aggregate function như COUNT(), SUM(), AVG(), MIN() hoặc MAX().
- Có window function.
- Có DISTINCT.
- Có GROUP BY.
- Có HAVING.
- Có LIMIT.
- Có UNION hoặc UNION ALL.
- Có subquery trong select list của query block.
- Có phép gán user variable.
- Query block chỉ chứa literal, không đọc bảng.

Ngoài các cấu trúc trên, merge cũng có thể bị giới hạn nếu việc merge làm query block ngoài vượt giới hạn số bảng được phép tham gia.

Khi không thể merge, MySQL thường cân nhắc materialization. Điều này không có nghĩa mọi derived table đều luôn materialize trong mọi phiên bản hoặc mọi trường hợp; cần xem execution plan thực tế.

### 6.1. Ví dụ GROUP BY buộc phải giữ query block

~~~sql
EXPLAIN
SELECT summary.department_id, summary.employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) AS summary
WHERE summary.employee_count > 5;
~~~

Query block bên trong thực hiện GROUP BY. Optimizer không thể đơn giản thay nó bằng một phép lọc trên hàng employees mà bỏ qua ngữ nghĩa tổng hợp. Kế hoạch thường có một bước tạo kết quả trung gian rồi query ngoài đọc kết quả đó.

### 6.2. Derived table đơn giản có thể merge

~~~sql
EXPLAIN
SELECT e.employee_id, e.salary
FROM (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
) AS e
WHERE e.department_id = 10;
~~~

Derived table không có cấu trúc ngăn merge. Nếu merge, điều kiện của query ngoài có thể được kết hợp với điều kiện bên trong và index trên employees được cân nhắc trực tiếp.

## 7. Điều kiện lọc có thể được đẩy vào derived table

Khi derived table không thể merge, optimizer vẫn có thể đẩy một số điều kiện từ query ngoài vào query block bên trong. Đây là derived condition pushdown.

Ví dụ:

~~~sql
SELECT summary.department_id, summary.employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) AS summary
WHERE summary.department_id = 10;
~~~

Điều kiện department_id = 10 chỉ liên quan đến key dùng để nhóm. Optimizer có thể đẩy điều kiện này vào query block bên trong, giảm số nhóm cần tạo.

Với điều kiện trên kết quả tổng hợp:

~~~sql
SELECT summary.department_id, summary.employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) AS summary
WHERE summary.employee_count > 5;
~~~

Điều kiện employee_count > 5 phụ thuộc kết quả COUNT(). Nó có thể được chuyển thành điều kiện HAVING trong query block bên trong, giữ nguyên ý nghĩa lọc sau tổng hợp.

Derived condition pushdown có điều kiện và giới hạn riêng. Ví dụ, LIMIT trong derived table ngăn một số kiểu pushdown vì lọc sớm có thể làm thay đổi tập hàng được giữ. Với UNION, điều kiện phù hợp có thể được đẩy xuống từng nhánh SELECT.

Tính năng derived condition pushdown được bổ sung trong MySQL 8.0.22. Nếu hệ thống chạy bản cũ hơn, đừng kỳ vọng cùng một kế hoạch. Hãy kiểm tra phiên bản, optimizer_switch và EXPLAIN.

## 8. Đọc derived table trong EXPLAIN

Derived table là SELECT nằm trong FROM:

~~~sql
SELECT e.employee_id, totals.order_count
FROM employees AS e
JOIN (
    SELECT employee_id, COUNT(*) AS order_count
    FROM sales_orders
    GROUP BY employee_id
) AS totals
  ON totals.employee_id = e.employee_id;
~~~

Khi derived table được materialize, EXPLAIN truyền thống có thể hiển thị một dòng có select_type = DERIVED cho query block bên trong và một bảng có tên như <derivedN> ở query block ngoài.

Trong JSON, có thể thấy materialized_from_subquery cùng query block tạo kết quả. Trong TREE, thường có node materialize và node đọc derived table.

Nếu derived table được merge, không còn một bước đọc <derivedN> riêng; các bảng gốc của derived query xuất hiện trực tiếp trong kế hoạch query ngoài.

Khi đọc, hãy trả lời:

1. Query block bên trong có được giữ riêng hay đã merge?
2. Nếu materialize, nó đọc bao nhiêu hàng nguồn?
3. Nó tạo bao nhiêu hàng kết quả?
4. Query ngoài đọc bảng tạm bằng scan, index lookup hay access method nào?
5. Có điều kiện nào được push down vào query block bên trong?
6. Có sort, aggregate hoặc temporary table nào khác ngoài materialization không?

## 9. Dùng MERGE và NO_MERGE để thử nghiệm

MySQL hỗ trợ optimizer hint để đề nghị merge hoặc không merge một derived table/CTE trong các trường hợp có thể áp dụng:

~~~sql
EXPLAIN
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
)
SELECT /*+ MERGE(active_employees) */
    employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

Có thể thử yêu cầu không merge:

~~~sql
EXPLAIN
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
)
SELECT /*+ NO_MERGE(active_employees) */
    employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

Hint chỉ có tác dụng nếu query block đủ điều kiện và tên đối tượng được tham chiếu đúng. Hint không thể làm cho một query block vốn không đủ điều kiện merge trở thành mergeable.

Dùng hint để so sánh kế hoạch và đo chi phí, không mặc định đưa hint vào production. Nếu cần cố định chiến lược, hãy ghi nhận lý do, phiên bản và kết quả benchmark để đánh giá lại khi schema hoặc dữ liệu thay đổi.

## 10. Đọc subquery trong WHERE: IN và EXISTS

Subquery trong WHERE thường biểu diễn điều kiện tồn tại hoặc thuộc tập giá trị.

Ví dụ IN:

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE enabled = TRUE
);
~~~

Ví dụ EXISTS:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE EXISTS (
    SELECT 1
    FROM sales_orders AS so
    WHERE so.employee_id = e.employee_id
      AND so.total > 1000
);
~~~

Subquery EXISTS tham chiếu e.employee_id từ query ngoài, vì vậy đây là correlated subquery theo cách viết ban đầu.

Optimizer có thể biến một số subquery IN/EXISTS đủ điều kiện thành semijoin. Semijoin chỉ cần xác định có ít nhất một hàng khớp; nó không nhân bản hàng bên ngoài khi có nhiều hàng khớp ở bảng trong.

Khi chuyển đổi được áp dụng, kế hoạch có thể thể hiện các chiến lược như FirstMatch, LooseScan, Duplicate Weedout, table pullout hoặc materialization. Tên và cách hiển thị phụ thuộc dạng EXPLAIN và phiên bản.

### 10.1. Điều kiện để semijoin transformation được áp dụng

Semijoin transformation thường dành cho subquery dạng IN/EXISTS ở vị trí phù hợp trong WHERE hoặc ON, thường là một điều kiện ở đầu hoặc nằm trong chuỗi điều kiện AND.

Một số cấu trúc có thể ngăn chuyển đổi gồm:

- Subquery chứa UNION.
- Subquery có aggregate hoặc GROUP BY.
- Subquery có HAVING.
- Subquery có LIMIT.
- Subquery có window function.
- Hình dạng subquery không thỏa quy tắc vị trí hoặc tương quan mà optimizer hỗ trợ.

Danh sách điều kiện chính xác phụ thuộc phiên bản và dạng subquery. Nếu không chuyển đổi, subquery có thể còn lại như một query block riêng hoặc được materialize.

### 10.2. Dấu hiệu trong EXPLAIN

Với EXPLAIN truyền thống, subquery chưa được chuyển đổi có thể xuất hiện dưới dạng SUBQUERY hoặc DEPENDENT SUBQUERY. Subquery được materialize có thể xuất hiện dưới dạng MATERIALIZED cùng một bảng nội bộ như <subqueryN>.

Nếu semijoin transformation được áp dụng, subquery có thể không còn là một dòng subquery độc lập. Các bảng liên quan được đưa vào join plan của query ngoài. TREE/JSON thường giúp nhìn rõ hơn cấu trúc join sau biến đổi.

Đừng coi việc không còn dòng SUBQUERY là subquery đã bị bỏ qua. Nó có thể đã được chuyển thành một phần của join plan.

## 11. Correlated subquery và dependent subquery

Correlated subquery tham chiếu một cột từ query block bên ngoài:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    (
        SELECT MAX(so.total)
        FROM sales_orders AS so
        WHERE so.employee_id = e.employee_id
    ) AS largest_order
FROM employees AS e
WHERE e.active = TRUE;
~~~

Subquery dùng e.employee_id, vì vậy kết quả phụ thuộc hàng hiện tại của employees.

Nếu subquery vẫn được giữ như một query block riêng, EXPLAIN truyền thống có thể ghi select_type = DEPENDENT SUBQUERY. Dòng này cho biết query block phụ thuộc dữ liệu từ query block ngoài. Subquery có thể được thực hiện lại theo các giá trị tương quan; số lần thực thi thực tế cần xem loops trong EXPLAIN ANALYZE.

Với index idx_orders_employee_total (employee_id, total), MySQL có thể tìm các đơn theo employee_id. Tuy nhiên, việc dùng index và khả năng tối ưu MAX phụ thuộc dữ liệu, thống kê và phiên bản.

### 11.1. Đọc loops trong EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT
    e.employee_id,
    (
        SELECT MAX(so.total)
        FROM sales_orders AS so
        WHERE so.employee_id = e.employee_id
    ) AS largest_order
FROM employees AS e
WHERE e.active = TRUE;
~~~

Trong TREE output, chú ý:

- Iterator đọc employees và số hàng thực tế trả ra.
- Iterator thực hiện lookup trong sales_orders.
- Số loops của iterator subquery.
- Số hàng trung bình mỗi loop và thời gian thực tế.

Nếu query ngoài trả về nhiều nhân viên và subquery chạy nhiều vòng, chi phí lặp có thể đáng kể. Nhưng không nên chỉ nhìn loops lớn rồi kết luận cần rewrite; một lookup index rất rẻ có thể vẫn tốt hơn materialize hoặc join trên toàn bộ bảng.

### 11.2. Uncorrelated subquery

Subquery không tham chiếu query block ngoài:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
    WHERE active = TRUE
);
~~~

Đây là scalar subquery độc lập. Nếu được giữ riêng, EXPLAIN có thể hiển thị select_type = SUBQUERY. Nó có thể được tính một lần và tái sử dụng kết quả trong câu lệnh, thay vì chạy lại cho từng nhân viên.

Trong JSON plan, các thuộc tính như dependent và cacheable giúp hiểu subquery có phụ thuộc query ngoài hoặc có thể được cache hay không. Hãy đọc cùng iterator và loops thay vì suy đoán chỉ từ câu SQL.

## 12. NOT EXISTS, NOT IN và antijoin

NOT EXISTS diễn đạt rằng không có hàng phù hợp ở bảng con:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_orders AS so
    WHERE so.employee_id = e.employee_id
);
~~~

Đây là điều kiện antijoin về mặt ngữ nghĩa: giữ hàng ngoài khi không có hàng trong khớp.

MySQL 8.0.17 bổ sung khả năng chuyển đổi một số điều kiện NOT IN, NOT EXISTS và các dạng tương đương thành antijoin. Nếu biến đổi được áp dụng, subquery có thể được tích hợp vào join plan và không còn hiển thị như một dependent subquery riêng.

### 12.1. Cẩn thận với NULL trong NOT IN

NOT IN có quy tắc logic ba giá trị của SQL. Nếu tập kết quả bên trong có NULL, phép so sánh có thể trở thành UNKNOWN và loại hàng ngoài khỏi WHERE.

Ví dụ:

~~~sql
SELECT 10
WHERE 10 NOT IN (20, NULL);
~~~

Truy vấn không trả về hàng vì biểu thức không thể được xác định là TRUE.

NOT EXISTS không có cùng hành vi này:

~~~sql
SELECT e.employee_id
FROM employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_orders AS so
    WHERE so.employee_id = e.employee_id
);
~~~

Khi đổi NOT IN thành NOT EXISTS hoặc ngược lại, hãy xác định rõ khả năng NULL ở cả hai phía. Hai biểu thức chỉ tương đương khi các điều kiện về NULL và so sánh được bảo đảm.

### 12.2. Khi antijoin transformation không áp dụng

Khả năng biến đổi phụ thuộc hình dạng subquery, vị trí predicate, kiểu dữ liệu và nullability. Với biểu thức nullable, MySQL thường không áp dụng antijoin transformation thông thường vì cần giữ chính xác ngữ nghĩa UNKNOWN. Một số cách viết biểu diễn rõ kết quả FALSE/UNKNOWN, như NOT IN (...) IS NOT FALSE hoặc IN (...) IS NOT TRUE, có thể cho phép biến đổi trong những điều kiện nhất định.

Trong EXPLAIN, nếu antijoin được chọn, TREE/JSON có thể thể hiện anti-join hoặc một chiến lược tương ứng. Nếu không, query block có thể còn là subquery riêng hoặc được materialize. Hãy kiểm tra execution plan thực tế.

## 13. Recursive CTE trong execution plan

Recursive CTE thường dùng để duyệt cây, đồ thị hoặc tạo dãy giá trị. CTE đệ quy gồm:

- Anchor member: truy vấn bắt đầu, không tham chiếu chính CTE.
- Recursive member: truy vấn tiếp tục tham chiếu CTE để tạo vòng kế tiếp.
- UNION ALL hoặc UNION kết hợp kết quả anchor và recursive member.

Ví dụ bảng nhân viên có quan hệ quản lý:

~~~sql
CREATE TABLE org_employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    manager_id BIGINT UNSIGNED NULL,
    employee_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_org_manager (manager_id)
) ENGINE = InnoDB;
~~~

Truy vấn tìm cấp dưới của một quản lý:

~~~sql
WITH RECURSIVE employee_tree AS (
    SELECT
        employee_id,
        manager_id,
        employee_name,
        0 AS depth
    FROM org_employees
    WHERE employee_id = 100

    UNION ALL

    SELECT
        child.employee_id,
        child.manager_id,
        child.employee_name,
        parent.depth + 1
    FROM org_employees AS child
    JOIN employee_tree AS parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id, manager_id, employee_name, depth
FROM employee_tree;
~~~

Recursive CTE được thực thi theo từng vòng: anchor tạo hàng ban đầu, recursive member đọc các hàng đã sinh để tìm tầng kế tiếp, rồi lặp cho đến khi không còn hàng mới hoặc đạt giới hạn đệ quy.

Recursive CTE được materialize; nó không được merge như CTE không đệ quy đơn giản. Khi đọc TREE/JSON, tìm node recursive, node materialization và iterator đọc bảng org_employees trong recursive member. Index trên manager_id rất quan trọng để tìm con theo từng quản lý.

### 13.1. Kiểm soát vòng lặp và giới hạn đệ quy

Nếu dữ liệu có chu trình, recursive CTE dùng UNION ALL có thể tiếp tục sinh lại các hàng. Thiết kế truy vấn cần cơ chế tránh lặp, ví dụ theo dõi đường đi hoặc bảo đảm dữ liệu không chứa chu trình.

MySQL có giới hạn cài đặt cho số vòng đệ quy thông qua cte_max_recursion_depth. Có thể kiểm tra:

~~~sql
SELECT @@cte_max_recursion_depth;
~~~

Tăng giới hạn không sửa được chu trình vô hạn hoặc truy vấn sinh quá nhiều hàng. Hãy xác định điều kiện dừng và kích thước kết quả trước khi thay đổi giới hạn.

## 14. Đọc kế hoạch của UNION và UNION ALL

UNION ghép kết quả của nhiều SELECT có cùng số cột tương thích về kiểu dữ liệu.

~~~sql
SELECT employee_id AS source_id, employee_name AS source_name
FROM employees
WHERE active = TRUE

UNION ALL

SELECT order_id AS source_id, CAST(total AS CHAR(40)) AS source_name
FROM sales_orders
WHERE total > 10000;
~~~

Ví dụ trên chỉ minh họa cấu trúc UNION ALL và việc các nhánh cần có kiểu kết quả tương thích. Trong ứng dụng thực tế, nên chọn kiểu cột thống nhất và có ý nghĩa rõ ràng cho cả hai nhánh.

UNION ALL giữ tất cả hàng từ các nhánh, kể cả hàng trùng. UNION (mặc định tương đương UNION DISTINCT) loại bỏ các hàng trùng trong kết quả kết hợp.

### 14.1. Khác biệt về chi phí

| Hình thức | Hành vi | Công việc bổ sung |
|---|---|---|
| UNION ALL | Giữ mọi hàng từ từng nhánh | Không cần khử trùng lặp giữa các nhánh |
| UNION DISTINCT hoặc UNION | Loại hàng trùng trên toàn bộ cột kết quả | Cần cơ chế so sánh/khử trùng lặp, thường dùng temporary table |

UNION DISTINCT có thể tốn thêm CPU, bộ nhớ và I/O do khử trùng lặp. UNION ALL thường ít công việc hơn, nhưng chỉ dùng khi nghiệp vụ chấp nhận giữ hàng trùng.

Nếu có ORDER BY toàn cục sau UNION, MySQL phải sắp xếp kết quả kết hợp theo yêu cầu. Điều này có thể tạo sort hoặc temporary table ngay cả khi dùng UNION ALL.

### 14.2. Dấu hiệu trong EXPLAIN

~~~sql
EXPLAIN
SELECT employee_id AS source_id
FROM employees
WHERE active = TRUE

UNION ALL

SELECT employee_id AS source_id
FROM sales_orders
WHERE total > 10000;
~~~

EXPLAIN truyền thống có thể hiển thị:

- Nhánh SELECT đầu tiên thường được hiển thị là PRIMARY.
- Nhánh tiếp theo có select_type = UNION.
- Kết quả kết hợp có thể có select_type = UNION RESULT và tên bảng như <union1,2>.

Nếu là UNION DISTINCT, kế hoạch có thể cho thấy công việc khử trùng lặp hoặc temporary table. UNION ALL có thể tránh bước khử trùng lặp và trong một số trường hợp không cần materialize toàn bộ kết quả; tuy nhiên, hình dạng thực tế còn phụ thuộc ORDER BY, LIMIT và các yếu tố khác.

Trong JSON/TREE, đọc từng query block của nhánh, index được chọn trong từng bảng và node hợp nhất kết quả. Không giả định hai nhánh dùng cùng một index hoặc có cùng số hàng.

### 14.3. ORDER BY và LIMIT với UNION

ORDER BY đặt ở cuối áp dụng cho toàn bộ kết quả UNION:

~~~sql
(SELECT employee_id AS id
 FROM employees
 WHERE active = TRUE)
UNION ALL
(SELECT employee_id AS id
 FROM sales_orders
 WHERE total > 10000)
ORDER BY id
LIMIT 50;
~~~

ORDER BY/LIMIT bên trong từng nhánh có phạm vi riêng và cần ngoặc khi muốn áp dụng rõ ràng cho từng SELECT. Một ORDER BY toàn cục có thể yêu cầu sắp xếp kết quả sau khi các nhánh đã chạy.

Khi phân tích, kiểm tra:

- Mỗi nhánh đọc bao nhiêu hàng.
- Index và access method của từng nhánh.
- Có khử trùng lặp không.
- Có sort toàn cục không.
- LIMIT có giảm được lượng dữ liệu phải xử lý ở từng nhánh hay chỉ giới hạn kết quả cuối.

## 15. Các select_type thường gặp khi đọc query block

EXPLAIN dạng truyền thống có cột select_type. Một số giá trị thường gặp trong truy vấn có query block lồng nhau:

| select_type | Ý nghĩa khái quát |
|---|---|
| SIMPLE | SELECT đơn giản, không có UNION hoặc subquery cần biểu diễn riêng |
| PRIMARY | Query block ngoài cùng trong truy vấn có cấu trúc phức tạp |
| SUBQUERY | Subquery độc lập được giữ thành query block riêng |
| DEPENDENT SUBQUERY | Subquery phụ thuộc giá trị từ query block ngoài |
| DERIVED | Query block trong FROM được giữ như derived table |
| MATERIALIZED | Subquery được materialize thành kết quả tạm |
| UNION | Một nhánh SELECT trong UNION, trừ nhánh đầu |
| DEPENDENT UNION | Nhánh UNION phụ thuộc query block bên ngoài |
| UNION RESULT | Bước hợp nhất kết quả UNION |

Các tên này là cách phân loại query block, không phải bảng xếp hạng tốc độ. Ví dụ, DEPENDENT SUBQUERY không tự động là xấu nếu query ngoài chỉ tạo ít hàng và mỗi lookup trong subquery rất rẻ.

Trong một câu SQL có nhiều tầng, id không nhất thiết được đọc như thứ tự thực thi từ trên xuống. Hãy kết hợp id, select_type, table, JSON/TREE và quan hệ phụ thuộc để hiểu query block.

## 16. Đọc EXPLAIN FORMAT=JSON

JSON giúp thấy cấu trúc query block và thông tin materialization rõ hơn dạng bảng.

Ví dụ:

~~~sql
EXPLAIN FORMAT=JSON
WITH department_summary AS (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT d.department_name, s.employee_count
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

Khi đọc JSON, tìm các phần sau nếu chúng xuất hiện:

- query_block: nội dung của một query block.
- nested_loop: các nhánh join và thứ tự truy cập.
- table: bảng được đọc, access type và index.
- materialized_from_subquery: query block tạo kết quả materialized.
- using_temporary_table: dấu hiệu dùng temporary table trong cấu trúc được mô tả.
- attached_subqueries: subquery gắn với một phần của query block.
- dependent và cacheable: thông tin phụ thuộc và khả năng cache của subquery.
- union_result: node đại diện kết quả UNION.

Không phải mọi trường đều xuất hiện trong mọi kế hoạch. Cấu trúc JSON thay đổi theo loại truy vấn và phiên bản MySQL.

### 16.1. Đọc materialized_from_subquery

Khi một query block được materialize, JSON có thể mô tả query block tạo dữ liệu bên trong phần materialized_from_subquery. Hãy mở rộng node này để đọc:

1. Bảng nguồn nào được quét.
2. Index nào được dùng.
3. Có aggregate, sort hoặc temporary table bên trong không.
4. Số hàng ước lượng được tạo ra.
5. Query ngoài đọc kết quả materialized theo cách nào.

Nếu chỉ xem node query ngoài, có thể bỏ sót phần chi phí lớn nhất nằm ở bước tạo bảng tạm.

## 17. Đọc EXPLAIN FORMAT=TREE

Trên MySQL 8.0.16 trở lên, EXPLAIN FORMAT=TREE hiển thị kế hoạch theo iterator tree:

~~~sql
EXPLAIN FORMAT=TREE
WITH department_summary AS (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT d.department_name, s.employee_count
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

TREE hữu ích vì thể hiện rõ:

- Iterator nào là con của iterator nào.
- Bảng hoặc query block nào được đọc trước.
- Materialize tạo dữ liệu tạm ở đâu.
- Join dùng nested loop, hash join hay chiến lược khác.
- Điều kiện lọc được áp dụng tại iterator nào.
- Có sort, aggregate hoặc duplicate removal hay không.

Khi đọc cây, bắt đầu từ iterator ngoài cùng trả kết quả cho client, sau đó đi xuống các iterator con để xác định dữ liệu được tạo ra từ đâu. Đừng nhầm thứ tự hiển thị node với số lần thực thi; dùng EXPLAIN ANALYZE để biết loops.

## 18. EXPLAIN ANALYZE: kiểm tra số liệu thực thi

EXPLAIN thông thường cho kế hoạch và ước lượng. EXPLAIN ANALYZE thực thi câu SELECT rồi bổ sung thời gian, số hàng thực tế và số vòng lặp cho các iterator. Tính năng này có từ MySQL 8.0.18.

~~~sql
EXPLAIN ANALYZE
WITH department_summary AS (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT d.department_name, s.employee_count
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

Các thông tin cần đọc:

- estimated rows: số hàng optimizer dự đoán.
- actual rows: số hàng iterator thực sự trả ra.
- loops: số lần iterator được gọi.
- actual time: thời gian thực thi được báo cho iterator.

Một iterator có actual rows nhỏ nhưng loops rất lớn vẫn có thể tạo tổng chi phí đáng kể. Ngược lại, một bước materialize có thể mất thời gian ban đầu nhưng chỉ chạy một lần và phục vụ nhiều lần đọc phía ngoài.

EXPLAIN ANALYZE chạy truy vấn thật. Với truy vấn lớn hoặc truy vấn có subquery tốn kém, hãy đánh giá tải và chọn môi trường phù hợp trước khi thực thi.

## 19. Cách so sánh hai cách viết SQL

Giả sử cần tìm nhân viên có ít nhất một đơn hàng lớn hơn 1.000:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE EXISTS (
    SELECT 1
    FROM sales_orders AS so
    WHERE so.employee_id = e.employee_id
      AND so.total > 1000
);
~~~

Có thể viết lại thành JOIN:

~~~sql
SELECT DISTINCT e.employee_id, e.employee_name
FROM employees AS e
JOIN sales_orders AS so
  ON so.employee_id = e.employee_id
WHERE so.total > 1000;
~~~

Hai cách có thể cho cùng tập kết quả nếu DISTINCT được áp dụng đúng, nhưng execution plan có thể khác:

- EXISTS có thể được chuyển thành semijoin.
- JOIN có thể tạo nhiều hàng trung gian cho một nhân viên có nhiều đơn, rồi phải loại trùng bằng DISTINCT.
- Optimizer có thể chọn thứ tự join khác nhau.
- Index và độ chọn lọc của total/employee_id ảnh hưởng đến kế hoạch.

Không chọn cách viết chỉ dựa vào việc SQL ngắn hơn. Hãy kiểm tra tính tương đương về kết quả, sau đó so sánh EXPLAIN ANALYZE trên dữ liệu đại diện.

### 19.1. Cách so sánh có kiểm soát

1. Giữ nguyên schema, index, dữ liệu và tham số.
2. Chạy EXPLAIN cho từng câu SQL.
3. So sánh query block, join order, materialization và access path.
4. Chạy EXPLAIN ANALYZE trong điều kiện tải tương đương.
5. So sánh actual rows, loops, thời gian và số hàng trung gian.
6. Kiểm tra kết quả trả về có giống nhau, đặc biệt với NULL và duplicate.
7. Lặp lại phép đo để tránh kết luận từ một lần chạy bất thường.

## 20. Materialization có thể được trì hoãn

Khi cần materialize derived table hoặc CTE, MySQL có thể trì hoãn việc tạo bảng tạm cho đến khi kết quả thực sự cần được đọc.

Ví dụ:

~~~sql
SELECT d.department_id, s.employee_count
FROM departments AS d
JOIN (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) AS s
  ON s.department_id = d.department_id
WHERE d.department_id = -1;
~~~

Nếu query block departments không trả về hàng nào, MySQL có thể không cần materialize derived table phía sau. Đây là một tối ưu hóa trì hoãn materialization; do đó, chỉ thấy node materialize trong kế hoạch chưa đủ để kết luận nó luôn được thực thi trong mọi lần chạy.

EXPLAIN mô tả kế hoạch dự kiến. EXPLAIN ANALYZE cho biết node thực sự chạy bao nhiêu lần trong lần thực thi được đo.

## 21. Kiểm tra các optimizer switch liên quan

Có thể xem trạng thái các cờ tối ưu hóa trong session:

~~~sql
SELECT @@optimizer_switch;
~~~

Một số cờ có thể liên quan đến chủ đề này, tùy phiên bản:

- derived_merge: cho phép merge derived table và view khi đủ điều kiện.
- derived_condition_pushdown: cho phép đẩy điều kiện vào derived table.
- semijoin: cho phép các chuyển đổi semijoin.
- materialization: cho phép chiến lược materialization cho subquery.
- subquery_materialization_cost_based: ảnh hưởng lựa chọn materialization theo chi phí trong các trường hợp áp dụng.

Không thay đổi optimizer_switch chỉ để làm cho một ví dụ có kế hoạch như mong muốn. Trước tiên, lưu giá trị hiện tại, xác định cờ liên quan và so sánh kế hoạch/benchmark trong session thử nghiệm. Cờ tối ưu hóa có thể ảnh hưởng nhiều truy vấn cùng lúc.

## 22. Những kết luận sai thường gặp

**“CTE luôn tạo bảng tạm.”** Không. CTE không đệ quy có thể được merge hoặc materialize tùy cấu trúc và quyết định của optimizer. Recursive CTE được materialize.

**“Không thấy tên CTE trong EXPLAIN nghĩa là MySQL bỏ qua CTE.”** Không. Query block có thể đã được merge vào query ngoài.

**“Mọi derived table đều phải materialize.”** Không. Derived table đơn giản có thể merge. Hãy tìm node <derivedN> hoặc dấu hiệu materialization trong JSON/TREE.

**“Materialization luôn chậm.”** Không. Nó có chi phí tạo kết quả tạm, nhưng có thể giảm số hàng, tính query block một lần hoặc hỗ trợ nhiều lần đọc bằng index nội bộ.

**“Một CTE được tham chiếu hai lần chắc chắn chạy hai lần.”** Không. Nếu materialize, kết quả CTE có thể được tạo một lần rồi dùng lại ở nhiều vị trí.

**“DEPENDENT SUBQUERY luôn là lỗi thiết kế.”** Không. Cần xem số hàng ngoài, loops, access path và chi phí của mỗi lần lookup.

**“EXISTS luôn nhanh hơn IN.”** Không. Optimizer có thể chuyển các dạng đủ điều kiện thành semijoin và chọn chiến lược theo chi phí.

**“NOT IN và NOT EXISTS luôn tương đương.”** Không. NULL có thể làm thay đổi kết quả của NOT IN.

**“UNION ALL và UNION giống nhau.”** Không. UNION loại trùng; UNION ALL giữ trùng. Việc loại trùng có thể tạo thêm công việc.

**“UNION ALL không bao giờ dùng temporary table.”** Không. ORDER BY toàn cục hoặc các yêu cầu thực thi khác vẫn có thể cần sort hoặc temporary table.

**“Thấy materialize trong EXPLAIN nghĩa bảng tạm chắc chắn luôn được tạo.”** Không. Materialization có thể được trì hoãn và chỉ xảy ra khi iterator được cần đến.

**“EXPLAIN ước lượng và EXPLAIN ANALYZE là cùng một loại kết quả.”** Không. EXPLAIN thường cho kế hoạch và ước lượng; EXPLAIN ANALYZE thực thi truy vấn để thu số hàng, loops và thời gian thực tế.

## 23. Quy trình đọc kế hoạch cho truy vấn nhiều query block

1. Xác định từng SELECT và query block: query ngoài, CTE, derived table, subquery và từng nhánh UNION.
2. Chạy EXPLAIN dạng bảng để nhận diện id, select_type, table, type, possible_keys, key, rows và Extra.
3. Xác định CTE/derived table đã merge hay materialize; tìm <derivedN> và dấu hiệu materialization.
4. Với CTE được tham chiếu nhiều lần, kiểm tra số lần đọc kết quả tạm và index nội bộ.
5. Với subquery, xác định correlated hay uncorrelated; xem có semijoin/antijoin, materialization hay dependent subquery.
6. Với recursive CTE, xác định anchor, recursive member, điều kiện dừng, index dùng trong mỗi vòng và số hàng được sinh.
7. Với UNION, đọc từng nhánh riêng, xác định UNION DISTINCT hay ALL, bước khử trùng lặp và sort toàn cục.
8. Dùng EXPLAIN FORMAT=JSON hoặc TREE để hiểu quan hệ iterator và node materialization.
9. Dùng EXPLAIN ANALYZE để so sánh estimated rows với actual rows, loops và thời gian.
10. Chỉ rewrite SQL, thêm index hoặc dùng hint sau khi xác định node gây chi phí và kiểm tra tính tương đương kết quả.

## 24. Checklist

- [ ] Đã xác định tất cả query block trong câu SQL.
- [ ] Đã hiểu CTE/derived table được merge hay materialize.
- [ ] Đã kiểm tra cấu trúc nào ngăn merge như GROUP BY, DISTINCT, LIMIT hoặc UNION.
- [ ] Đã xem xét derived condition pushdown nếu query block được materialize.
- [ ] Đã kiểm tra CTE được tham chiếu nhiều lần có được materialize một lần hay không.
- [ ] Đã phân biệt SUBQUERY với DEPENDENT SUBQUERY.
- [ ] Đã kiểm tra semijoin/antijoin transformation cho IN, EXISTS, NOT IN và NOT EXISTS.
- [ ] Đã kiểm tra ngữ nghĩa NULL trước khi thay NOT IN bằng NOT EXISTS.
- [ ] Đã đọc anchor và recursive member của recursive CTE.
- [ ] Đã xác nhận điều kiện dừng và giới hạn đệ quy.
- [ ] Đã phân biệt UNION DISTINCT với UNION ALL.
- [ ] Đã kiểm tra sort/temporary table cho UNION có ORDER BY.
- [ ] Đã đọc JSON/TREE để xác định node tạo và tiêu thụ kết quả tạm.
- [ ] Đã dùng EXPLAIN ANALYZE để xác nhận loops và actual rows khi phù hợp.
- [ ] Đã đo truy vấn trên dữ liệu đại diện và xác nhận kết quả tương đương sau rewrite.

## Kết luận

Execution plan của CTE, derived table, subquery và UNION phải được đọc theo query block và luồng dữ liệu giữa các block. CTE/derived table có thể được merge hoặc materialize; subquery có thể được giữ riêng, materialize hoặc chuyển thành semijoin/antijoin; UNION có thể cần khử trùng lặp và sắp xếp.

Hãy dùng EXPLAIN truyền thống để nhận diện query block, JSON/TREE để theo dõi cấu trúc và materialization, rồi EXPLAIN ANALYZE để xác nhận số hàng, loops và thời gian thực tế. Đánh giá dựa trên chi phí của từng iterator và tính đúng đắn của kết quả, không dựa vào một nhãn đơn lẻ như DERIVED, DEPENDENT SUBQUERY hay MATERIALIZED.
