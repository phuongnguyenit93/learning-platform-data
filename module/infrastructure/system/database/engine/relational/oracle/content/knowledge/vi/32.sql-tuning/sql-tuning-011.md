# Hint, query block và cách kiểm chứng hint được sử dụng

Oracle SQL Optimizer tự chọn execution plan dựa trên câu SQL, thống kê, bind values, cấu hình optimizer và nhiều yếu tố khác. Trong một số tình huống tuning, người phát triển hoặc DBA muốn hướng optimizer tới một lựa chọn cụ thể, chẳng hạn dùng index, chọn join method, thay đổi join order hoặc kiểm soát một query transformation. Oracle cung cấp **optimizer hints** để truyền những chỉ dẫn này ngay trong SQL.

Hint chỉ có ích khi được đặt đúng vị trí, tham chiếu đúng alias và query block, áp dụng được với cấu trúc câu SQL, đồng thời tạo ra một plan tốt hơn trong workload thực tế. Một hint xuất hiện trong source code không chứng minh Oracle đã sử dụng nó. Cần kiểm tra cursor thực tế và hint report.

Bài học tập trung vào bốn việc:

1. Viết hint đúng cú pháp và đúng query block.
2. Dùng alias và QB_NAME để chỉ rõ đối tượng được tác động.
3. Hiểu hint về access path, join order, join method và query transformation.
4. Kiểm chứng hint được dùng, bị bỏ qua hay không thể áp dụng bằng DBMS_XPLAN.

## 1. Optimizer hint là gì?

Optimizer hint là chỉ dẫn được đặt trong comment đặc biệt của câu SQL. Hint có thể hướng optimizer tới một access path, join method, join order, mức parallelism hoặc hành vi transformation.

Ví dụ:

~~~sql
SELECT /*+ FULL(e) */
       e.employee_id,
       e.employee_name
FROM employees e
WHERE e.department_id = 10;
~~~

FULL(e) yêu cầu optimizer xem xét full table scan cho row source có alias E trong query block tương ứng.

Một ví dụ khác:

~~~sql
SELECT /*+ USE_HASH(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

USE_HASH(d) hướng optimizer dùng hash join với row source D nếu hint hợp lệ và phương án đó có thể áp dụng.

Hint không thay đổi ý nghĩa nghiệp vụ của câu SQL. Kết quả truy vấn vẫn phải tuân theo ngữ nghĩa SQL. Hint điều khiển hoặc ảnh hưởng cách optimizer tìm execution plan.

### 1.1 Hint là comment đặc biệt

Comment thường:

~~~sql
SELECT /* query employee */ employee_id
FROM employees;
~~~

Hint comment:

~~~sql
SELECT /*+ FULL(e) */ e.employee_id
FROM employees e;
~~~

Dấu cộng phải đứng ngay sau dấu mở comment: /*+.

Các dạng sau không phải hint comment hợp lệ:

~~~sql
SELECT /* + FULL(e) */ e.employee_id FROM employees e;
SELECT --+ FULL(e)
       e.employee_id
FROM employees e;
~~~

Trong ví dụ đầu có khoảng trắng giữa dấu mở comment và dấu cộng. Trong ví dụ thứ hai, cú pháp line comment không phải dạng hint comment chuẩn. Hãy dùng comment dạng /*+ ... */.

### 1.2 Vị trí hint trong câu SQL

Hint thường được đặt ngay sau keyword mở đầu query block hoặc DML statement:

~~~sql
SELECT /*+ FULL(e) */ ...
INSERT /*+ APPEND */ INTO ...
UPDATE /*+ ... */ ...
DELETE /*+ ... */ ...
MERGE /*+ ... */ INTO ...
~~~

Với SELECT lồng nhau, mỗi query block có thể có hint comment riêng sau SELECT của block đó.

### 1.3 Gom các hint của một query block vào một comment

Nên viết:

~~~sql
SELECT /*+ LEADING(e d) USE_NL(d) INDEX(d pk_departments) */
       ...
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Không chia hint của cùng query block thành nhiều comment rời rạc sau cùng một SELECT. Oracle chỉ nhận diện hint comment ở vị trí quy định; comment hint đặt ở vị trí khác có thể bị bỏ qua.

## 2. Hint không phải lời bảo đảm plan

Hint có thể:

- Được nhận diện và sử dụng.
- Được nhận diện nhưng không áp dụng được trong ngữ cảnh hiện tại.
- Bị vô hiệu do xung đột với hint khác.
- Không tìm thấy alias hoặc query block được tham chiếu.
- Không còn áp dụng sau khi optimizer biến đổi query block.
- Có cú pháp sai hoặc tham số không hợp lệ.

Vì vậy, cần phân biệt:

| Điều quan sát | Có thể kết luận? |
|---|---|
| Hint có trong source SQL | Chỉ biết người viết đã yêu cầu hint |
| Execution plan có operation tương ứng | Plan có operation đó, nhưng chưa chắc hint là nguyên nhân |
| Hint report ghi hint Used | Oracle ghi nhận hint được sử dụng |
| Hint report ghi hint Unused/Unresolved | Cần xem lý do và phạm vi áp dụng |
| Plan hash thay đổi | Plan đã khác, chưa chứng minh plan mới nhanh hơn |

Một execution plan có INDEX RANGE SCAN không tự chứng minh INDEX hint đã được dùng; optimizer có thể tự chọn index đó ngay cả khi không có hint. Ngược lại, hint có thể được nhận diện nhưng kết quả cuối cùng vẫn không như người viết mong muốn do các điều kiện áp dụng khác.

## 3. Các nhóm hint thường gặp

### 3.1 Hint điều khiển mục tiêu tối ưu

ALL_ROWS:

~~~sql
SELECT /*+ ALL_ROWS */ ...
FROM orders o;
~~~

Hướng optimizer tối ưu throughput/tổng chi phí xử lý toàn bộ kết quả.

FIRST_ROWS(n):

~~~sql
SELECT /*+ FIRST_ROWS(20) */ ...
FROM orders o;
~~~

Hướng optimizer ưu tiên trả về một số hàng đầu sớm hơn trong một số workload tương tác. Nó không bảo đảm chỉ đọc đúng N hàng hoặc mọi operation đều dừng sau N hàng.

### 3.2 Hint access path

FULL(alias):

~~~sql
SELECT /*+ FULL(e) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

INDEX(alias index_name):

~~~sql
SELECT /*+ INDEX(e ix_employees_department) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

INDEX_FFS(alias index_name):

~~~sql
SELECT /*+ INDEX_FFS(e ix_employees_department) */
       e.department_id
FROM employees e;
~~~

INDEX hint hướng optimizer tới index được chỉ định. Nó không có nghĩa index luôn rẻ hơn full scan; nếu hint làm tăng I/O hoặc phải truy cập nhiều rowid, query có thể chậm hơn.

### 3.3 Hint join method

USE_NL(alias):

~~~sql
SELECT /*+ USE_NL(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

USE_HASH(alias):

~~~sql
SELECT /*+ USE_HASH(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

USE_MERGE(alias):

~~~sql
SELECT /*+ USE_MERGE(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Các hint này định hướng phương pháp join với row source được chỉ định. Chúng không tự quyết định toàn bộ join order.

### 3.4 Hint join order

LEADING:

~~~sql
SELECT /*+ LEADING(e d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

LEADING(e d) hướng optimizer bắt đầu join theo thứ tự row source được chỉ định trong query block. Với query nhiều bảng, danh sách alias cần phản ánh thứ tự join mong muốn.

ORDERED:

~~~sql
SELECT /*+ ORDERED */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

ORDERED hướng optimizer sử dụng thứ tự row source trong FROM clause. Khi ORDERED được chỉ định, LEADING bị bỏ qua theo quy tắc của Oracle; không nên đặt hai hint này với kỳ vọng chúng cùng điều khiển join order.

### 3.5 Hint query transformation

Một số hint thường gặp:

- MERGE(view_alias): cho phép/hướng tới view merging trong ngữ cảnh phù hợp.
- NO_MERGE(view_alias): ngăn view merging cho inline view được chỉ định.
- UNNEST: hướng optimizer unnest subquery.
- NO_UNNEST: ngăn unnesting trong ngữ cảnh phù hợp.
- PUSH_PRED: hướng predicate pushing vào view.
- NO_PUSH_PRED: ngăn predicate pushing.

Query transformation có thể làm thay đổi cấu trúc query block trước khi chọn access path/join. Khi hint không có hiệu lực như mong muốn, cần xem query block đã được merge, unnest hoặc biến đổi ra sao.

### 3.6 Hint parallel

Ví dụ:

~~~sql
SELECT /*+ PARALLEL(e, 4) */
       COUNT(*)
FROM employees e;
~~~

PARALLEL hướng optimizer dùng parallel execution với degree được chỉ định nếu môi trường và đối tượng hỗ trợ. Parallel có thể tăng throughput nhưng cũng tiêu thụ CPU, PGA, I/O và parallel server resources. Không dùng hint parallel chỉ vì query chạy lâu mà chưa đo bottleneck.

### 3.7 Hint phục vụ kiểm tra

GATHER_PLAN_STATISTICS:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

Hint này yêu cầu thu thập runtime plan statistics cho cursor để có thể xem E-Rows/A-Rows và các thông tin liên quan qua DBMS_XPLAN. Nó phục vụ đo/điều tra, không phải hint chọn access path hay join method.

## 4. Alias là một phần quan trọng của hint

Nếu câu SQL khai báo alias:

~~~sql
SELECT /*+ INDEX(e ix_employees_department) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

Hint cần tham chiếu alias E. Không dùng tên bảng EMPLOYEES thay cho E trong trường hợp này:

~~~sql
SELECT /*+ INDEX(employees ix_employees_department) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

Ví dụ sau có thể khiến hint không resolve đúng đối tượng do query đã khai báo alias.

Quy tắc thực hành:

- Dùng alias đúng như trong FROM.
- Không thêm schema owner vào alias.
- Nếu alias được đặt trong dấu nháy kép và có chữ hoa/thường đặc biệt, phải chú ý identifier semantics.
- Không nhầm alias của inline view ở query block ngoài với alias bảng bên trong inline view.

### 4.1 Cùng bảng xuất hiện hai lần

Ví dụ self join:

~~~sql
SELECT /*+ USE_NL(m) */
       e.employee_id,
       m.employee_name AS manager_name
FROM employees e
JOIN employees m
  ON m.employee_id = e.manager_id;
~~~

EMPLOYEES xuất hiện hai lần với alias E và M. Hint phải chỉ rõ occurrence cần tác động. Dùng tên bảng EMPLOYEES sẽ không phân biệt được hai row source.

### 4.2 Alias của inline view

~~~sql
SELECT /*+ NO_MERGE(q) */
       q.order_id,
       q.customer_id
FROM (
    SELECT o.order_id,
           o.customer_id
    FROM orders o
    WHERE o.status = 'OPEN'
) q;
~~~

Trong query block ngoài, inline view có alias Q. Hint NO_MERGE(q) tham chiếu Q ở block ngoài. Bên trong inline view, bảng ORDERS có alias O và thuộc query block khác.

## 5. Query block là gì?

Query block là một đơn vị query được optimizer phân tích và biến đổi riêng. Một câu SQL có thể chứa nhiều query block do:

- SELECT chính.
- Inline view trong FROM.
- Scalar subquery.
- EXISTS/IN subquery.
- Set query như UNION/UNION ALL.
- Subquery trong biểu thức.

Ví dụ:

~~~sql
SELECT c.customer_id,
       (
           SELECT MAX(o.order_date)
           FROM orders o
           WHERE o.customer_id = c.customer_id
       ) AS last_order_date
FROM customers c;
~~~

Có query block ngoài đọc CUSTOMERS và query block con tính MAX(ORDER_DATE) từ ORDERS.

Hint đặt ở SELECT ngoài mặc định áp dụng cho query block ngoài. Hint đặt ngay sau SELECT của subquery áp dụng cho query block con đó.

### 5.1 Mỗi query block có phạm vi riêng

Ví dụ:

~~~sql
SELECT /*+ QB_NAME(q_main) */
       c.customer_id,
       q.order_count
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_orders) */
           o.customer_id,
           COUNT(*) AS order_count
    FROM orders o
    GROUP BY o.customer_id
) q
  ON q.customer_id = c.customer_id;
~~~

Ở đây:

- q_main là tên query block ngoài.
- q_orders là tên query block bên trong inline view.
- Alias C và Q thuộc block ngoài.
- Alias O thuộc block q_orders.

Không dùng alias O ở block ngoài nếu alias đó chỉ tồn tại bên trong query block con.

## 6. QB_NAME: đặt tên query block

QB_NAME là hint đặt tên một query block để các hint khác có thể tham chiếu chính xác hơn.

Ví dụ:

~~~sql
SELECT /*+ QB_NAME(q_main) */
       c.customer_id,
       q.order_count
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_orders) */
           o.customer_id,
           COUNT(*) AS order_count
    FROM orders o
    GROUP BY o.customer_id
) q
  ON q.customer_id = c.customer_id;
~~~

Tên q_main và q_orders giúp người đọc nhận biết phạm vi. Khi câu SQL phức tạp, tên rõ ràng dễ bảo trì hơn tên query block tự sinh như SEL$1 hoặc SEL$2.

### 6.1 Vì sao không nên dựa lâu dài vào SEL$1?

Optimizer tạo tên nội bộ cho query block. Tên tự sinh có thể thay đổi khi câu SQL thay đổi, query transformation hoặc cấu trúc subquery khác đi.

Nếu hint tham chiếu SEL$1 và một lần sửa query làm thứ tự query block thay đổi, hint có thể trỏ nhầm hoặc không còn resolve.

Đặt QB_NAME rõ ràng giúp hint dễ hiểu và ít phụ thuộc tên nội bộ.

### 6.2 Query block name phải duy nhất trong câu SQL

Nên đặt tên ngắn, có ý nghĩa và không trùng:

- q_main
- q_orders
- q_customer_filter
- q_item_aggregation

Giữ tên nhất quán khi tham chiếu bằng query-block-qualified hint.

### 6.3 QB_NAME không phải alias bảng

QB_NAME đặt tên query block, còn alias đặt tên row source/table occurrence. Hai loại identifier có vai trò khác nhau:

| Identifier | Ví dụ | Dùng để |
|---|---|---|
| Query block name | q_orders | Xác định phạm vi query |
| Table alias | o | Xác định row source trong query block |
| Index name | ix_orders_status | Xác định index |

Một hint tham chiếu query block và alias thường cần cả hai thông tin.

## 7. Hint tham chiếu query block khác

Oracle hỗ trợ cú pháp query-block-qualified hint bằng cách dùng ký hiệu @ trước query block name trong phần tham chiếu của hint.

Ví dụ:

~~~sql
SELECT /*+
          QB_NAME(q_main)
          NO_MERGE(q)
          INDEX(@q_orders o ix_orders_status)
       */
       q.order_id,
       c.customer_name
FROM (
    SELECT /*+ QB_NAME(q_orders) */
           o.order_id,
           o.customer_id
    FROM orders o
    WHERE o.status = :status
) q
JOIN customers c
  ON c.customer_id = q.customer_id;
~~~

Giải thích:

- QB_NAME(q_main) đặt tên block ngoài.
- QB_NAME(q_orders) đặt tên block trong inline view.
- NO_MERGE(q) hướng optimizer không merge inline view Q vào block ngoài.
- INDEX(@q_orders o ix_orders_status) tham chiếu alias O trong block q_orders để hướng access path.

Đây là cú pháp nâng cao. Khi sử dụng, phải xác nhận query block name và alias đúng với query sau phân tích, đồng thời kiểm tra Hint Report. Nếu view được merge hoặc query transformation làm thay đổi cấu trúc, cần đánh giá lại hint scope.

### 7.1 Không lạm dụng hint xuyên query block

Hint xuyên block hữu ích khi cần điều khiển một row source nằm sâu trong query. Tuy nhiên, nó làm SQL khó đọc và dễ gãy khi cấu trúc query thay đổi.

Ưu tiên:

1. Đặt hint ngay trong query block chứa row source nếu có thể.
2. Dùng QB_NAME khi cần tham chiếu từ block khác.
3. Giữ query block name ổn định và dễ hiểu.
4. Kiểm tra hint report sau mỗi lần sửa cấu trúc SQL.

## 8. Ví dụ hint ở từng query block

~~~sql
SELECT /*+ QB_NAME(q_main) LEADING(c q) USE_NL(q) */
       c.customer_id,
       q.order_id
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_orders) INDEX(o ix_orders_status) */
           o.order_id,
           o.customer_id
    FROM orders o
    WHERE o.status = :status
) q
  ON q.customer_id = c.customer_id;
~~~

Trong ví dụ:

- Block q_main có hint LEADING và USE_NL.
- Block q_orders có hint INDEX trên O.
- Alias Q ở ngoài khác alias O ở trong.
- Hai nhóm hint được đặt trong hint comment của đúng query block.

Optimizer vẫn có thể biến đổi query theo các quy tắc khác. Kiểm tra plan và hint report để biết hint được áp dụng như thế nào.

## 9. LEADING, ORDERED và USE_NL phối hợp ra sao?

Một lỗi phổ biến là chỉ thêm USE_NL rồi mong Oracle dùng đúng bảng driving.

Ví dụ:

~~~sql
SELECT /*+ USE_NL(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id BETWEEN 1000 AND 1010;
~~~

USE_NL(d) hướng D làm inner row source của nested loops, nhưng join order vẫn là quyết định riêng. Nếu cần chỉ rõ thứ tự, có thể kết hợp:

~~~sql
SELECT /*+ LEADING(e d) USE_NL(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id BETWEEN 1000 AND 1010;
~~~

LEADING(e d) định hướng join order bắt đầu từ E rồi tới D; USE_NL(d) định hướng join method với D là inner. Vẫn phải xác nhận optimizer đã nhận các hint.

### 9.1 LEADING so với ORDERED

LEADING chỉ định thứ tự theo alias. ORDERED lấy thứ tự theo FROM clause. Không nên dùng đồng thời để cố điều khiển cùng một quyết định; ORDERED có thể khiến LEADING bị bỏ qua.

LEADING thường rõ ràng hơn khi muốn giữ FROM clause theo cấu trúc logic mà vẫn nêu thứ tự join.

### 9.2 USE_NL không tự tạo index

Nếu inner row source không có access path phù hợp, nested loops có thể phải scan nhiều dữ liệu cho mỗi outer row. Hint USE_NL không tự tạo index và không làm inner lookup rẻ hơn.

## 10. Điều khiển access path

### 10.1 FULL

~~~sql
SELECT /*+ FULL(o) */
       o.order_id,
       o.order_date
FROM orders o
WHERE o.status = 'OPEN';
~~~

FULL hướng optimizer đọc table bằng full table scan cho alias O. Nó có thể hợp lý khi cần đọc phần lớn bảng hoặc index không hiệu quả.

### 10.2 INDEX

~~~sql
SELECT /*+ INDEX(o ix_orders_status) */
       o.order_id
FROM orders o
WHERE o.status = 'CANCELLED';
~~~

INDEX hướng optimizer sử dụng index chỉ định nếu có thể. Nếu predicate trả phần lớn hàng và cần nhiều cột không nằm trong index, table access by rowid có thể tốn kém.

### 10.3 INDEX_DESC

~~~sql
SELECT /*+ INDEX_DESC(o ix_orders_date) */
       o.order_id,
       o.order_date
FROM orders o
WHERE o.customer_id = :customer_id;
~~~

INDEX_DESC hướng scan index theo chiều giảm dần trong phạm vi áp dụng. Cần kiểm tra index key order và predicate; hint không tự bảo đảm kết quả SQL có thứ tự nếu query không có ORDER BY.

### 10.4 NO_INDEX

NO_INDEX hướng optimizer không sử dụng index được chỉ định trong access path phù hợp. Đây là hint cần thận trọng vì có thể loại bỏ access path hữu ích cho các giá trị hoặc workload khác.

### 10.5 Hint không thay thế index design

Nếu một query cần lọc theo CUSTOMER_ID và ORDER_DATE, index composite có thể phù hợp hơn index đơn trên một cột. Hint INDEX không khắc phục được thứ tự cột index không phù hợp, clustering factor xấu hoặc predicate không sargable.

## 11. Điều khiển query transformation

Optimizer có thể biến đổi SQL để tạo plan tốt hơn. Các transformation thường gặp:

- View merging.
- Predicate pushing.
- Subquery unnesting.
- OR expansion.
- Query rewrite.
- Join elimination trong trường hợp đủ điều kiện.

Hint có thể tác động tới một số transformation.

### 11.1 MERGE và NO_MERGE

Inline view:

~~~sql
SELECT q.customer_id,
       q.order_count
FROM (
    SELECT o.customer_id,
           COUNT(*) AS order_count
    FROM orders o
    GROUP BY o.customer_id
) q;
~~~

NO_MERGE:

~~~sql
SELECT /*+ NO_MERGE(q) */
       q.customer_id,
       q.order_count
FROM (
    SELECT o.customer_id,
           COUNT(*) AS order_count
    FROM orders o
    GROUP BY o.customer_id
) q;
~~~

Hint NO_MERGE hướng optimizer giữ inline view như một query block riêng trong phạm vi có thể áp dụng. Điều này có thể giúp giữ ranh giới aggregation hoặc phục vụ tuning cụ thể, nhưng cũng có thể ngăn optimizer đẩy predicate hoặc kết hợp các phép toán hiệu quả hơn.

### 11.2 UNNEST và NO_UNNEST

Subquery EXISTS:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Optimizer có thể unnest subquery thành semijoin. Hint UNNEST hoặc NO_UNNEST có thể ảnh hưởng transformation trong trường hợp phù hợp.

Không mặc định unnest luôn tốt hoặc luôn xấu. Kiểm tra query block, cardinality và join method sau transformation.

### 11.3 Predicate pushing

Predicate pushing có thể đẩy điều kiện từ query block ngoài vào view/subquery để giảm số hàng cần xử lý sớm. Hint PUSH_PRED/NO_PUSH_PRED có thể tác động trong một số trường hợp.

Không ngăn predicate pushing nếu chưa đo. Một inline view giữ nguyên có thể khiến nhiều hàng phải xử lý hơn.

## 12. Hint cho DML

Hint có thể xuất hiện trong INSERT, UPDATE, DELETE và MERGE.

Ví dụ direct-path insert:

~~~sql
INSERT /*+ APPEND */
INTO order_archive
SELECT *
FROM orders
WHERE order_date < DATE '2025-01-01';
~~~

APPEND hướng tới direct-path insert trong ngữ cảnh hỗ trợ. Direct-path insert có các quy tắc về segment, locking và transaction khác conventional insert; cần kiểm tra tác động tới concurrent access và commit.

Có thể đặt hint cho query block SELECT của INSERT:

~~~sql
INSERT INTO order_archive
SELECT /*+ FULL(o) */
       o.*
FROM orders o
WHERE o.order_date < DATE '2025-01-01';
~~~

Hint sau SELECT tác động query block đọc dữ liệu. Hint sau INSERT tác động phần INSERT. Không nhầm phạm vi hai vị trí.

## 13. Hint trong subquery và correlated subquery

Ví dụ:

~~~sql
SELECT /*+ QB_NAME(q_main) */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT /*+ QB_NAME(q_exists) INDEX(o ix_orders_customer) */
           1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Hint INDEX nằm trong query block q_exists và tham chiếu alias O của block đó. Optimizer có thể unnest subquery; khi đó cần kiểm tra transformation và hint report để biết hint còn áp dụng theo cách mong muốn hay không.

Nếu muốn thử giữ subquery riêng, có thể thử NO_UNNEST trong query block con, nhưng phải benchmark vì việc ngăn transformation có thể làm plan kém hơn.

## 14. Hint conflict và hint bị bỏ qua

Một câu SQL có thể chứa các hint mâu thuẫn:

~~~sql
SELECT /*+ FULL(e) INDEX(e ix_employees_department) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

FULL(e) và INDEX(e ...) cùng hướng tới access path khác nhau cho cùng row source. Không nên dựa vào thứ tự viết hint để dự đoán Oracle sẽ chọn cái nào. Hint conflict có thể khiến một hoặc nhiều hint không được áp dụng.

Các nguyên nhân thường gặp:

- Hint syntax sai.
- Alias không tồn tại hoặc sai phạm vi.
- Query block name không đúng.
- Hint không phù hợp loại join/predicate.
- Hai hint mâu thuẫn.
- Query transformation thay đổi đối tượng được hint.
- Hint không thể áp dụng do cấu trúc câu SQL hoặc giới hạn phiên bản.
- Hint đặt sai vị trí.

### 14.1 Không dùng nhiều hint để thử ngẫu nhiên

Thêm hàng loạt hint khiến khó xác định hint nào ảnh hưởng plan. Hãy thử từng nhóm:

1. Xác nhận baseline.
2. Thêm một hint có mục tiêu.
3. Xem hint report.
4. So sánh plan và runtime.
5. Giữ hoặc bỏ hint dựa trên số liệu.

## 15. Kiểm chứng hint bằng DBMS_XPLAN

Đây là bước quan trọng nhất của bài học. Cần xem cursor đã thực thi thay vì chỉ xem source SQL.

### 15.1 Thu thập runtime statistics

Gắn GATHER_PLAN_STATISTICS vào query:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS USE_NL(d) LEADING(e d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id BETWEEN 1000 AND 1010;
~~~

Fetch hết kết quả để runtime statistics của cursor được ghi nhận đầy đủ.

### 15.2 Xem cursor hiện tại

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +ALIAS +OUTLINE +HINT_REPORT'
    )
);
~~~

Ý nghĩa format:

- ALLSTATS LAST: hiển thị runtime statistics của lần thực thi gần nhất khi có dữ liệu thống kê.
- ALIAS: hiển thị thông tin alias/query block liên quan operation.
- OUTLINE: hiển thị outline hints có thể dùng để tái tạo plan.
- HINT_REPORT: hiển thị trạng thái hint mà Oracle nhận diện trong cursor, ở các phiên bản hỗ trợ.

Hỗ trợ format HINT_REPORT phụ thuộc phiên bản Oracle. Nếu môi trường chưa hỗ trợ, dùng DBMS_XPLAN format options có sẵn và kiểm tra phiên bản/tài liệu tương ứng.

### 15.3 Xem SQL_ID và child cursor cụ thể

Khi session chạy nhiều câu SQL, NULL/NULL có thể không trỏ tới cursor mà bạn muốn kiểm tra. Có thể tìm SQL_ID:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       sql_text
FROM v$sql
WHERE sql_text LIKE '%ORDERS%'
ORDER BY last_active_time DESC;
~~~

Sau đó:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => :sql_id,
        cursor_child_no => :child_number,
        format          => 'ALLSTATS LAST +ALIAS +OUTLINE +HINT_REPORT'
    )
);
~~~

V$SQL chứa các cursor hiện còn trong shared pool; dữ liệu có thể biến mất khi cursor bị aged out hoặc shared pool thay đổi. Cần quyền truy cập view hiệu năng.

### 15.4 Hint Report cho biết điều gì?

Hint report có thể giúp phân biệt:

- Hint được sử dụng.
- Hint không được sử dụng.
- Hint không resolve được alias/query block.
- Hint có lỗi cú pháp hoặc không hợp lệ.
- Hint bị thay thế/xung đột trong ngữ cảnh cụ thể.

Nội dung và mã trạng thái chi tiết phụ thuộc phiên bản. Đọc phần report trong output thay vì tự suy luận từ việc plan có operation tương tự.

### 15.5 Plan có operation tương ứng chưa đủ để chứng minh hint

Ví dụ source có INDEX(e ix_emp_dept) và plan có INDEX RANGE SCAN. Optimizer có thể đã tự chọn index mà không cần hint.

Ngược lại, nếu plan có FULL SCAN trong khi source có INDEX hint, hint có thể không resolve, không áp dụng hoặc có nguyên nhân khác. Hãy đọc hint report, alias, query block và outline.

## 16. OUTLINE khác HINT_REPORT

Hai phần này thường bị nhầm:

**HINT_REPORT** trả lời câu hỏi: các hint được cung cấp trong SQL đã được nhận diện và sử dụng như thế nào?

**OUTLINE** hiển thị tập hint/định hướng optimizer có thể dùng để tái tạo execution plan hiện tại. Outline không đơn giản là bản sao nguyên văn comment hint do người viết đặt trong source.

Một plan có thể được tạo ra bởi optimizer mà không cần user hint, nhưng outline vẫn chứa các hint nội bộ tương ứng với quyết định plan.

Do đó:

- Dùng HINT_REPORT để điều tra hint trong SQL.
- Dùng OUTLINE để nghiên cứu cách tái tạo plan.
- Dùng ALLSTATS LAST để xem runtime rows và resource.
- Dùng SQL_ID/child number để đảm bảo đang xem đúng cursor.

## 17. ALIAS và query block trong DBMS_XPLAN

Format ALIAS có thể cho biết table alias và query block gắn với operation. Đây là dữ liệu quan trọng khi hint tham chiếu nhiều block.

Khi hint không được dùng, kiểm tra:

1. Alias trong source có đúng với alias trong plan?
2. Query block name có đúng không?
3. Query block có bị merge/unnest không?
4. Hint đặt trong đúng comment của query block?
5. Hint xuyên block có cú pháp tham chiếu @query_block chính xác?

Nếu query phức tạp, có thể đặt QB_NAME rõ ràng trong các block quan trọng để việc đọc plan và hint report dễ hơn.

## 18. EXPLAIN PLAN không phải bằng chứng cuối cùng

EXPLAIN PLAN:

~~~sql
EXPLAIN PLAN FOR
SELECT /*+ USE_HASH(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN tạo plan ước lượng trong ngữ cảnh explain. Nó không cung cấp runtime A-Rows, actual buffers hoặc toàn bộ thông tin của cursor production đã thực thi.

Plan thực tế có thể khác do:

- Bind peeking.
- Child cursor.
- Optimizer environment.
- Statistics khác nhau.
- Session settings.
- Adaptive cursor behavior.
- SQL text hoặc schema khác.

Khi cần xác minh hint đã được áp dụng cho SQL chạy thực tế, hãy lấy SQL_ID/child cursor và dùng DISPLAY_CURSOR.

## 19. Bind variables và hint

Hint cố định access path hoặc join method có thể không phù hợp cho mọi bind value.

Ví dụ:

~~~sql
SELECT /*+ USE_NL(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

Nếu STATUS = 'CANCELLED' chỉ có 0,1% hàng, nested loops có thể hợp lý. Nếu STATUS = 'OPEN' có 95% hàng, cùng hint có thể khiến inner lookup lặp rất nhiều lần.

Khi đánh giá hint với bind:

- Thử giá trị phổ biến và hiếm.
- Kiểm tra child cursor.
- Xem IS_BIND_SENSITIVE và IS_BIND_AWARE trong V$SQL khi có quyền.
- Kiểm tra peeked binds trong plan nếu có.
- Đo elapsed, CPU, buffers và A-Rows.

PEEKED_BINDS hiển thị giá trị bind được peek trong quá trình hard parse theo cursor, không phải nhật ký mọi bind value của mọi lần execute.

Không thêm hint cố định dựa trên một bind value duy nhất nếu SQL được dùng cho nhiều vùng selectivity.

## 20. Hint và adaptive behavior

Optimizer có thể dùng các cơ chế adaptive tùy phiên bản và cấu hình, chẳng hạn adaptive plans hoặc adaptive cursor sharing. Một số quyết định có thể được điều chỉnh dựa trên thông tin runtime hoặc bind selectivity.

Khi điều tra:

- Xác định phiên bản Oracle.
- Xem plan thực tế và child cursor.
- Xem hint report.
- Kiểm tra adaptive plan details nếu có.
- Không giả định một plan hiển thị ban đầu luôn là toàn bộ hành vi runtime.

Hint có thể giới hạn không gian lựa chọn của optimizer. Nếu hint xung đột với mục tiêu adaptive hoặc transformation, kết quả phải được xác minh trong môi trường đang chạy.

## 21. Hướng dẫn chọn hint có mục tiêu

Trước khi thêm hint, hãy xác định vấn đề:

| Vấn đề quan sát | Nhóm hint có thể thử | Điều cần kiểm chứng |
|---|---|---|
| Access path không phù hợp | FULL, INDEX, INDEX_FFS | Buffers, reads, rows và thời gian |
| Join method không phù hợp | USE_NL, USE_HASH, USE_MERGE | Cardinality, Starts, TEMP, CPU |
| Join order không phù hợp | LEADING hoặc ORDERED | Row source trung gian và join order |
| Inline view bị merge ngoài ý muốn | NO_MERGE | Predicate pushdown và cardinality |
| Subquery transformation ảnh hưởng plan | UNNEST/NO_UNNEST | Semijoin/anti join và số hàng |
| Cần kiểm tra runtime | GATHER_PLAN_STATISTICS | A-Rows, Starts, buffers |
| Cần thử parallel | PARALLEL | Throughput, CPU, PGA, TEMP và concurrency |

Bảng này chỉ gợi ý nơi bắt đầu. Hint phù hợp còn phụ thuộc SQL cụ thể và phiên bản.

## 22. Quy trình kiểm chứng hint từ đầu đến cuối

Một quy trình tuning có thể lặp lại:

### Bước 1: Lưu baseline

Ghi lại:

- SQL text nguyên bản.
- SQL_ID và child number nếu đã chạy.
- Bind values đại diện.
- Plan hiện tại.
- E-Rows/A-Rows.
- Buffers, reads, CPU và elapsed.
- Optimizer environment và thống kê liên quan.

### Bước 2: Nêu giả thuyết

Ví dụ:

- Outer row source thực tế chỉ có 20 hàng.
- Optimizer chọn hash join nhưng hash build tốn nhiều hơn lookup.
- Một index trên inner join key có thể làm nested loops rẻ hơn.

Giả thuyết phải dựa trên plan/runtime data.

### Bước 3: Thêm một nhóm hint tối thiểu

Ví dụ:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS LEADING(o c) USE_NL(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

Không thêm FULL, INDEX, PARALLEL và nhiều transformation hints cùng lúc nếu chưa có lý do.

### Bước 4: Kiểm tra hint report

Dùng DISPLAY_CURSOR với +HINT_REPORT và +ALIAS. Xác nhận:

- Hint được nhận diện.
- Alias đúng.
- Query block đúng.
- Hint được dùng hay không.
- Có conflict hoặc unresolved target không.

### Bước 5: Kiểm tra plan thực tế

Xem operation:

- NESTED LOOPS/HASH JOIN/MERGE JOIN.
- Access path của từng row source.
- Join order.
- E-Rows/A-Rows.
- Starts.
- Buffers và TEMP.

### Bước 6: Đo nhiều lần

Chạy với:

- Bind value phổ biến.
- Bind value hiếm.
- Input nhỏ/vừa/lớn.
- Mức concurrency đại diện.

So sánh median/p95 nếu phù hợp, không kết luận từ một lần chạy.

### Bước 7: Regression test

Xác nhận:

- Kết quả SQL không đổi.
- Không bỏ sót hoặc nhân bản hàng.
- NULL semantics không đổi.
- Transaction và locking không đổi.
- Workload liên quan không bị regression.

### Bước 8: Quyết định giữ hoặc bỏ

Chỉ giữ hint khi có lợi ích đo được, ổn định, có phạm vi rõ và có người chịu trách nhiệm theo dõi sau khi dữ liệu/thống kê thay đổi.

## 23. Ví dụ hoàn chỉnh: kiểm chứng hint trên query nhiều bảng

Giả sử ứng dụng lấy đơn hàng theo trạng thái rồi join khách hàng:

~~~sql
SELECT /*+ QB_NAME(q_main)
           GATHER_PLAN_STATISTICS
           LEADING(o c)
           USE_NL(c)
           INDEX(o ix_orders_status)
           INDEX(c pk_customers)
       */
       o.order_id,
       o.order_date,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

Các hint:

- QB_NAME(q_main): đặt tên query block.
- GATHER_PLAN_STATISTICS: thu thập runtime statistics.
- LEADING(o c): định hướng join order.
- USE_NL(c): định hướng nested loops với C là inner row source.
- INDEX(o ix_orders_status): hướng access path của ORDERS.
- INDEX(c pk_customers): hướng access path của CUSTOMERS.

Sau khi execute và fetch hết:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +ALIAS +OUTLINE +PEEKED_BINDS +HINT_REPORT'
    )
);
~~~

Đọc kết quả:

1. Hint report xác nhận các hint được nhận diện/áp dụng thế nào.
2. ALIAS xác nhận query block và alias.
3. Operation tree xác nhận join method và access path.
4. E-Rows/A-Rows xác nhận ước lượng có sát thực tế.
5. Starts và Buffers cho biết chi phí lặp inner lookup.
6. PEEKED_BINDS giúp xem bind được peek khi hard parse nếu có.

Nếu STATUS phổ biến tạo hàng trăm nghìn order, plan nested loops có thể kém. Khi đó cần thử giá trị khác hoặc bỏ hint để optimizer chọn phương án phù hợp.

## 24. Query block phức tạp: inline view và subquery

Ví dụ query:

~~~sql
SELECT /*+ QB_NAME(q_main) */
       c.customer_id,
       q.total_amount
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_order_totals) */
           o.customer_id,
           SUM(o.order_amount) AS total_amount
    FROM orders o
    WHERE o.order_date >= DATE '2026-01-01'
    GROUP BY o.customer_id
) q
  ON q.customer_id = c.customer_id
WHERE c.status = 'ACTIVE';
~~~

Khi tuning:

- Hint trên C thuộc q_main.
- Hint trên O thuộc q_order_totals.
- Alias Q là row source inline view ở q_main.
- Query transformation có thể merge hoặc xử lý view theo cách khác nếu được phép.

Để thử giữ ranh giới inline view:

~~~sql
SELECT /*+ QB_NAME(q_main) NO_MERGE(q) */
       c.customer_id,
       q.total_amount
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_order_totals) */
           o.customer_id,
           SUM(o.order_amount) AS total_amount
    FROM orders o
    WHERE o.order_date >= DATE '2026-01-01'
    GROUP BY o.customer_id
) q
  ON q.customer_id = c.customer_id
WHERE c.status = 'ACTIVE';
~~~

So sánh plan có và không NO_MERGE. Giữ view không phải lúc nào cũng tốt; optimizer có thể mất cơ hội đẩy predicate hoặc sắp xếp lại phép toán.

## 25. Outline data và SQL Plan Management

Outline data là tập chỉ dẫn mô tả cách tái tạo plan hiện tại. Nó có thể giúp DBA hiểu plan phụ thuộc vào lựa chọn optimizer nào.

SQL Plan Management (SPM) là cơ chế quản lý SQL plan baseline. Nó khác với việc đặt hint trực tiếp trong SQL:

- Hint trực tiếp được viết trong SQL text.
- Outline trong DBMS_XPLAN mô tả cách tái tạo plan.
- SQL plan baseline quản lý plan được chấp nhận cho SQL statement theo cơ chế SPM.

Không dùng outline output như thể nó là danh sách hint đã viết trong source. Nếu cần ổn định plan lâu dài, hãy đánh giá SPM và quy trình quản lý plan phù hợp.

## 26. Quyền và công cụ kiểm tra

DBMS_XPLAN.DISPLAY_CURSOR và các view V$SQL_PLAN/V$SQL có thể yêu cầu quyền đọc các view hiệu năng. Trong môi trường ứng dụng, user thường không được cấp quyền rộng chỉ để debug.

Có thể nhờ DBA:

- Cấp quyền đọc tối thiểu phù hợp.
- Trích plan cho SQL_ID/child cursor.
- Bật thống kê theo session/test environment.
- Cung cấp Hint Report và runtime metrics.

Không cấp quyền DBA hoặc SELECT ANY DICTIONARY cho ứng dụng chỉ để đọc execution plan.

## 27. Những lỗi thường gặp với hint và query block

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Viết /* + HINT */ | Không phải hint comment đúng dạng | Viết /*+ HINT */ |
| Đặt hint sau FROM | Có thể bị bỏ qua vì sai vị trí | Đặt sau keyword mở query block |
| Dùng tên bảng thay alias | Hint không resolve đúng row source | Dùng alias trong FROM |
| Dùng alias của block khác | Hint không tìm thấy đối tượng | Xác định query block và alias |
| Dựa vào SEL$1 lâu dài | Tên nội bộ có thể đổi | Đặt QB_NAME |
| Dùng USE_NL mà không kiểm soát join order | Inner/driving role không như mong đợi | Kết hợp LEADING khi có cơ sở |
| Dùng LEADING và ORDERED cùng lúc | Hint join order có thể xung đột; ORDERED làm LEADING bị bỏ qua | Chọn một cách điều khiển |
| Nghĩ INDEX hint bảo đảm query nhanh | Index lookup có thể tốn nhiều rowid I/O | Đo buffers/elapsed |
| Thêm nhiều hint một lúc | Khó biết hint nào tạo khác biệt | Thử từng nhóm nhỏ |
| Chỉ nhìn plan operation để xác nhận hint | Optimizer có thể tự chọn cùng plan | Xem HINT_REPORT |
| Chỉ xem EXPLAIN PLAN | Không thấy runtime cursor đầy đủ | Dùng DISPLAY_CURSOR |
| Nhầm OUTLINE với HINT_REPORT | Hiểu sai hint source và plan reproduction | Đọc hai phần theo mục đích riêng |
| Chỉ test một bind value | Plan có thể kém cho giá trị khác | Test bind phổ biến và hiếm |
| Giữ hint mãi sau khi dữ liệu đổi | Hint cũ có thể làm plan regression | Theo dõi và đánh giá định kỳ |
| Ngăn mọi query transformation | Mất cơ hội tối ưu | Chỉ dùng khi có giả thuyết và số liệu |

## 28. Bài thực hành tự kiểm tra

Các bài tập nên chạy trong schema thử nghiệm và dùng cùng một bộ dữ liệu khi so sánh.

### Bài 1 — Hint comment

Viết một SELECT có FULL hint và một SELECT có comment thường. Quan sát plan và giải thích cú pháp comment đặc biệt.

### Bài 2 — Alias

Viết self join EMPLOYEES với alias E và M. Dùng USE_NL(M) và kiểm tra hint report. Thử tham chiếu tên bảng thay alias và ghi nhận kết quả.

### Bài 3 — Access path

So sánh query không hint, FULL(E) và INDEX(E index_name). Đo buffers, reads và elapsed với predicate chọn lọc cao/thấp.

### Bài 4 — Join method

So sánh USE_NL, USE_HASH và USE_MERGE cho cùng equijoin. Kiểm tra join operation và hint report.

### Bài 5 — Join order

Tạo query ba bảng. Thử LEADING(a b c) và LEADING(c a b). Xem cây plan và cardinality ở các bước trung gian.

### Bài 6 — LEADING và ORDERED

Viết query với hai hint này. Xem hint report để nhận biết xung đột/ưu tiên. Sau đó bỏ một hint và so sánh.

### Bài 7 — QB_NAME

Tạo query có inline view và EXISTS subquery. Đặt tên mỗi block bằng QB_NAME và đọc phần ALIAS trong DBMS_XPLAN.

### Bài 8 — Hint xuyên query block

Dùng query-block-qualified hint để tham chiếu alias trong inline view. Kiểm tra đúng query block và alias trong hint report.

### Bài 9 — NO_MERGE

So sánh plan của inline view khi không hint và khi có NO_MERGE. Quan sát predicate pushdown, cardinality và số hàng trung gian.

### Bài 10 — HINT_REPORT và OUTLINE

Chạy query có hint hợp lệ, hint sai alias và hint xung đột. So sánh HINT_REPORT với OUTLINE.

### Bài 11 — Bind values

Chạy cùng SQL với bind hiếm và phổ biến. Quan sát child cursor, peeked binds, join method và runtime.

### Bài 12 — Kiểm chứng end-to-end

Chọn một SQL chậm, lưu baseline, nêu giả thuyết, thêm một hint, xác nhận hint report, so actual plan và benchmark nhiều lần. Ghi rõ lý do giữ hoặc bỏ hint.

## 29. Checklist trước khi đưa hint vào production

**Cú pháp và phạm vi**

- Hint comment có dạng /*+ ... */ và nằm đúng sau keyword?
- Các hint của cùng query block được gom đúng?
- Alias có khớp chính xác với FROM?
- Query block đã được đặt QB_NAME khi cần?
- Hint xuyên block tham chiếu đúng query block và alias?

**Tính áp dụng**

- Hint có tương thích query transformation?
- Có hint xung đột?
- LEADING và ORDERED có bị dùng lẫn?
- USE_NL/USE_HASH/USE_MERGE có chỉ định đúng row source?
- Hint report cho biết trạng thái gì?

**Kiểm chứng plan**

- Đang xem đúng SQL_ID và child cursor?
- Đã xem actual plan bằng DISPLAY_CURSOR?
- Có ALLSTATS LAST?
- Đã đọc ALIAS, OUTLINE và HINT_REPORT?
- E-Rows/A-Rows, Starts, Buffers và TEMP có hợp lý?

**Hiệu năng và tính ổn định**

- Đã thử bind value phổ biến và hiếm?
- Đã benchmark nhiều lần?
- Đã kiểm tra concurrency?
- Kết quả SQL có giữ nguyên?
- Có regression ở workload liên quan?
- Có người theo dõi khi dữ liệu/thống kê thay đổi?

## 30. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| Optimizer hint | Chỉ dẫn trong comment đặc biệt để tác động lựa chọn plan |
| Hint comment | Bắt đầu bằng /*+ và đặt sau keyword của query/DML block |
| Alias | Tên row source phải được dùng đúng trong hint |
| Query block | Đơn vị SELECT/subquery được optimizer phân tích |
| QB_NAME | Đặt tên query block để tham chiếu rõ ràng |
| @query_block | Cú pháp tham chiếu query block khác trong hint hỗ trợ |
| FULL/INDEX | Hướng access path |
| USE_NL/USE_HASH/USE_MERGE | Hướng join method |
| LEADING | Hướng join order theo alias |
| ORDERED | Hướng join order theo thứ tự FROM; xung đột với LEADING |
| NO_MERGE/MERGE | Tác động view merging |
| UNNEST/NO_UNNEST | Tác động subquery unnesting |
| GATHER_PLAN_STATISTICS | Thu thập runtime plan statistics |
| HINT_REPORT | Kiểm tra trạng thái hint được nhận diện |
| ALIAS | Xem alias và query block trong plan |
| OUTLINE | Xem chỉ dẫn có thể tái tạo plan, khác hint report |
| DISPLAY_CURSOR | Xem plan của cursor thực tế |
| EXPLAIN PLAN | Plan ước lượng, không thay thế runtime cursor |

Hint là công cụ tuning có mục tiêu. Hãy đặt hint đúng query block, dùng alias chính xác và đặt QB_NAME cho câu SQL phức tạp. LEADING điều khiển join order, USE_NL/USE_HASH/USE_MERGE hướng join method, còn FULL/INDEX hướng access path; các nhóm này không thay thế lẫn nhau. Quan trọng nhất, kiểm tra cursor thực tế bằng DBMS_XPLAN, đọc HINT_REPORT, ALIAS, OUTLINE và runtime statistics. Chỉ giữ hint khi benchmark chứng minh lợi ích trên các bind values và workload đại diện, đồng thời có kế hoạch theo dõi khi dữ liệu hoặc thống kê thay đổi.
