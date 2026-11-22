# Query transformation: view merging, unnesting và predicate pushing

Oracle Cost-Based Optimizer (CBO) không chỉ chọn index hay join method cho câu SQL đúng như văn bản được viết. Trước khi tạo execution plan, optimizer có thể biến đổi cấu trúc truy vấn thành một dạng tương đương về ngữ nghĩa nhưng dễ tối ưu hơn. Nhóm thao tác này gọi là **query transformation**.

Ba kỹ thuật quan trọng là view merging, subquery unnesting và predicate pushing. View merging đưa query block của inline view vào query block bên ngoài để optimizer nhìn thấy nhiều bảng và điều kiện join cùng lúc. Unnesting chuyển một số subquery thành join hoặc semi/anti join. Predicate pushing đưa điều kiện lọc xuống gần nguồn dữ liệu hơn để giảm số hàng phải xử lý ở các bước sau.

Các phép biến đổi không phải lúc nào cũng hợp lệ hoặc có lợi. Optimizer phải bảo toàn semantics của SQL, xem xét NULL, aggregation, outer join, DISTINCT, set operator, analytic function và các ràng buộc khác; sau đó đánh giá cost của các phương án. Vì vậy, hiểu query transformation giúp đọc execution plan, giải thích vì sao plan khác với cách viết SQL và biết khi nào cần kiểm tra hint hoặc rewrite.

Sau bài học, bạn có thể:

- Nhận biết query block, inline view, subquery và view trong execution plan.
- Giải thích simple view merging và complex view merging.
- Hiểu điều kiện, lợi ích và hạn chế của view merging.
- Phân biệt view merging với materialization của WITH clause.
- Hiểu subquery unnesting cho IN, EXISTS, NOT IN và NOT EXISTS.
- Nhận diện semi join, anti join và null-aware anti join.
- Giải thích predicate pushing, predicate pushdown và join predicate pushdown.
- Phân biệt predicate được đẩy vào WHERE, HAVING, từng nhánh UNION ALL hoặc view tương quan.
- Đọc plan để nhận biết transformation đã xảy ra hay chưa.
- Dùng QB_NAME, MERGE, NO_MERGE, UNNEST, NO_UNNEST, PUSH_PRED và các hint liên quan một cách có kiểm soát.
- Chẩn đoán trường hợp transformation không hợp lệ, không được chọn hoặc làm plan chậm hơn.

> Query transformation thay đổi theo release, optimizer_features_enable, statistics, constraints, bind values và cấu hình hệ thống. Ví dụ trong bài minh họa nguyên tắc; cần kiểm tra execution plan thực tế trên đúng phiên bản Oracle và dữ liệu của bạn.

## 1. Query blocks và vai trò của optimizer

### 1.1. Query block là gì?

Một query block là một đơn vị SELECT trong câu SQL. Một câu SQL có thể chứa nhiều query block do inline view, subquery, CTE hoặc set operation tạo ra.

Ví dụ:

```sql
SELECT e.employee_id, e.last_name
FROM employees e
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments d
    WHERE d.location_id = 1700
);
```

Câu SQL có query block ngoài đọc EMPLOYEES và một query block con đọc DEPARTMENTS. Optimizer có thể giữ subquery riêng, unnest nó thành semi join, hoặc áp dụng các transformation khác nếu hợp lệ và có lợi.

Ví dụ inline view:

```sql
SELECT v.department_id, v.employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) v
WHERE v.department_id = 50;
```

SELECT bên trong dấu ngoặc là một query block riêng, thường được gọi là view query block hoặc inline view. Optimizer có thể giữ nó như một khối riêng, đẩy predicate vào trong hoặc áp dụng complex view merging tùy điều kiện.

### 1.2. Query transformation diễn ra ở đâu?

Ở mức khái quát, CBO thực hiện các công việc:

1. Parse SQL và xây dựng cây biểu thức/query blocks.
2. Kiểm tra semantics, object metadata, constraints và quyền.
3. Xem xét các transformation hợp lệ.
4. Tạo các phương án access path, join order, join method và các operation khác.
5. Ước lượng cost dựa trên statistics, cardinality và mô hình cost.
6. Chọn plan được đánh giá tốt nhất trong phạm vi optimizer đã xem xét.

Thứ tự nội bộ và tập transformation cụ thể có thể khác giữa các phiên bản. Không nên hiểu danh sách này là một pipeline cứng mà mọi câu SQL đều đi qua giống nhau.

### 1.3. Transformation phải bảo toàn semantics

Hai câu SQL có vẻ tương đương về ý định chưa chắc tương đương về ngữ nghĩa. Ví dụ:

- NOT IN có quy tắc ba giá trị TRUE/FALSE/UNKNOWN khi có NULL.
- Outer join tạo hàng null-extended.
- GROUP BY thay đổi grain của dữ liệu.
- DISTINCT loại duplicate.
- ROWNUM và FETCH FIRST có thể phụ thuộc thứ tự/ranh giới hàng.
- Analytic function phụ thuộc tập hàng và thứ tự cửa sổ.

Optimizer chỉ được áp dụng transformation nếu giữ được kết quả theo semantics SQL. Khi viết lại thủ công, người phát triển phải tự chịu trách nhiệm bảo toàn các quy tắc đó.

## 2. View merging

### 2.1. Khái niệm

View merging là transformation đưa query block của một view (inline view hoặc view được tham chiếu) vào query block bên ngoài. Sau khi merge, optimizer có thể tối ưu các bảng và điều kiện trong hai khối như một query block lớn hơn.

Trước transformation:

```sql
SELECT e.employee_id, v.department_name
FROM employees e
JOIN (
    SELECT department_id, department_name
    FROM departments
    WHERE status = 'ACTIVE'
) v
  ON v.department_id = e.department_id
WHERE e.salary > 10000;
```

View V chỉ là projection/filter trên DEPARTMENTS. Optimizer có thể merge view để thấy trực tiếp EMPLOYEES và DEPARTMENTS cùng điều kiện:

```sql
SELECT e.employee_id, d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE d.status = 'ACTIVE'
  AND e.salary > 10000;
```

Đây là dạng tương đương về ý tưởng trong ví dụ đơn giản. Không phải mọi inline view đều có thể được viết lại theo cách này.

### 2.2. Vì sao view merging hữu ích?

Nếu view không được merge, optimizer có thể phải tối ưu view như một khối riêng rồi mới kết hợp kết quả với query bên ngoài. Khi merge, optimizer có thể:

- Xem xét join order giữa bảng trong view và bảng bên ngoài.
- Chọn access path dựa trên predicate từ cả hai phía.
- Đẩy filter và join condition sâu hơn.
- Loại bỏ projection hoặc query layer không cần thiết.
- Khai thác transitive predicate và các transformation khác.

Lợi ích chính là mở rộng không gian tìm kiếm plan. View merging không tự động có nghĩa query nhanh hơn; optimizer vẫn phải chọn plan tốt dựa trên cost.

### 2.3. Simple view merging

Simple view merging thường áp dụng cho view có cấu trúc đơn giản như SELECT-PROJECT-JOIN (SPJ), tức chủ yếu là FROM, WHERE và danh sách biểu thức SELECT, không có các cấu trúc làm thay đổi grain/kết quả như GROUP BY hoặc DISTINCT.

Ví dụ:

```sql
SELECT *
FROM (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE salary > 5000
) v
WHERE v.department_id = 20;
```

View chỉ lọc và chiếu cột. Optimizer có thể gộp các predicate thành:

```sql
SELECT employee_id, department_id, salary
FROM employees
WHERE salary > 5000
  AND department_id = 20;
```

Simple view merging thường dễ áp dụng vì không phải xử lý các ranh giới aggregation hoặc duplicate elimination.

### 2.4. Complex view merging

Complex view merging xử lý một số view có cấu trúc phức tạp hơn, chẳng hạn GROUP BY hoặc DISTINCT. Việc merge phải bảo toàn ngữ nghĩa aggregation/duplicate và được optimizer cân nhắc theo tính hợp lệ cùng cost.

Ví dụ view tổng hợp:

```sql
SELECT d.department_name, v.total_salary
FROM departments d
JOIN (
    SELECT department_id, SUM(salary) AS total_salary
    FROM employees
    GROUP BY department_id
) v
  ON v.department_id = d.department_id
WHERE d.location_id = 1700;
```

Optimizer có thể xem xét complex view merging trong những trường hợp được hỗ trợ. Tuy nhiên, không được suy luận rằng mọi GROUP BY view đều merge được hoặc luôn nên merge. Có thể giữ view riêng để aggregate trước rồi join, nếu cách đó có cost thấp hơn hoặc cần thiết để giữ semantics.

### 2.5. GROUP BY và ranh giới ngữ nghĩa

Giả sử view tính tổng lương theo department. Sau GROUP BY, mỗi department có tối đa một hàng. Nếu merge hoặc đẩy predicate không đúng, có thể làm thay đổi tập hàng đầu vào aggregation hoặc cách tính tổng.

Predicate trên grouping key có thể được đưa xuống trước GROUP BY trong nhiều trường hợp vì nó chọn các nhóm theo key. Predicate trên aggregate như SUM(salary) > 100000 thuộc HAVING semantics; không thể tùy tiện chuyển thành WHERE trên từng employee.

Ví dụ:

```sql
SELECT department_id, SUM(salary) AS total_salary
FROM employees
WHERE department_id = 50
GROUP BY department_id
HAVING SUM(salary) > 100000;
```

WHERE department_id = 50 lọc hàng trước aggregation. HAVING lọc nhóm sau aggregation. Hai vị trí này không thể thay thế nhau tùy ý.

## 3. Điều kiện và giới hạn của view merging

### 3.1. Không phải view nào cũng merge được

Transformation có thể bị hạn chế bởi:

- GROUP BY, DISTINCT và aggregate.
- Set operators như UNION, UNION ALL, INTERSECT, MINUS.
- CONNECT BY/hierarchical query.
- MODEL clause.
- Một số trường hợp ROWNUM, row limiting, analytic function.
- Outer join và các quan hệ null-preserving.
- Các biểu thức hoặc cấu trúc mà việc merge làm thay đổi semantics.
- Query block có đặc tính đặc biệt như một số trường hợp remote object hoặc security barrier.

Danh sách này không phải quy tắc “có keyword là cấm merge” cho mọi release. Oracle có thể hỗ trợ một số complex transformation trong điều kiện cụ thể. Hãy đọc plan và tài liệu phiên bản thay vì dựa vào một danh sách cấm tuyệt đối.

### 3.2. View có DISTINCT

DISTINCT loại duplicate. Nếu merge view vào query ngoài, optimizer phải giữ được semantics loại trùng. Trong một số trường hợp, complex view merging có thể thực hiện được; trong trường hợp khác, view được giữ riêng hoặc dùng transformation khác.

Ví dụ:

```sql
SELECT c.customer_id
FROM customers c
JOIN (
    SELECT DISTINCT customer_id
    FROM orders
) o
  ON o.customer_id = c.customer_id;
```

View tạo tập customer_id duy nhất. Nếu bỏ DISTINCT mà không bảo toàn semantics, số hàng kết quả có thể tăng do một customer có nhiều order.

### 3.3. View có set operator

View dùng UNION ALL hoặc UNION tạo ranh giới set operation. Optimizer có thể áp dụng các transformation như predicate pushing vào từng nhánh, nhưng không đồng nghĩa luôn merge toàn bộ view thành một query block thông thường.

```sql
SELECT *
FROM (
    SELECT customer_id, status FROM current_customers
    UNION ALL
    SELECT customer_id, status FROM archived_customers
) all_customers
WHERE status = 'ACTIVE';
```

Predicate status = 'ACTIVE' có thể được push vào cả hai nhánh nếu hợp lệ. Đây là predicate pushing qua UNION ALL; cần phân biệt với view merging.

### 3.4. Outer join và null-preserving semantics

Outer join giữ lại hàng của phía preserved side ngay cả khi phía còn lại không match. Đẩy predicate từ WHERE vào ON hoặc vào view có thể thay đổi việc hàng không match được giữ lại hay bị loại.

Ví dụ:

```sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
```

Predicate e.status = 'ACTIVE' trong WHERE loại các hàng mà e là NULL, khiến kết quả có semantics gần với inner join đối với predicate đó. Nếu chuyển predicate sang ON:

```sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
```

Departments không có employee ACTIVE vẫn được giữ lại với cột employee NULL. Hai câu không tương đương. Optimizer phải bảo toàn khác biệt này khi biến đổi.

### 3.5. ROWNUM, row limiting và analytic functions

Các cấu trúc giới hạn/sắp xếp hàng có thể tạo ranh giới semantics. Ví dụ, lọc bên ngoài một inline view có ROWNUM không nhất thiết tương đương với đưa predicate vào trước khi ROWNUM được gán.

Tương tự, analytic function tính trên tập hàng và window. Predicate pushdown/merge chỉ được áp dụng khi không làm thay đổi tập hàng mà analytic function nhìn thấy hoặc khi optimizer có transformation bảo toàn semantics.

Không rewrite query có ROWNUM, FETCH FIRST hoặc analytic function chỉ dựa trên hình thức. Kiểm tra thứ tự xử lý và kết quả thực tế.

## 4. MERGE và NO_MERGE hints

### 4.1. MERGE hint

MERGE hint yêu cầu optimizer xem xét merge một view:

```sql
SELECT /*+ MERGE(v) */
       e.employee_id, v.department_name
FROM employees e
JOIN (
    SELECT department_id, department_name
    FROM departments
    WHERE status = 'ACTIVE'
) v
  ON v.department_id = e.department_id;
```

Hint có thể được đặt trong query block ngoài để tham chiếu view alias hoặc dùng dạng có query block tùy ngữ cảnh. Cú pháp hint cụ thể và khả năng áp dụng cần xác nhận theo release.

### 4.2. NO_MERGE hint

NO_MERGE yêu cầu optimizer giữ view như một query block riêng:

```sql
SELECT /*+ NO_MERGE(v) */
       e.employee_id, v.department_name
FROM employees e
JOIN (
    SELECT department_id, department_name
    FROM departments
    WHERE status = 'ACTIVE'
) v
  ON v.department_id = e.department_id;
```

Có thể hữu ích khi muốn giữ ranh giới view để tránh một transformation gây plan xấu, hoặc khi cần kiểm soát cấu trúc query block trong thử nghiệm. Không dùng NO_MERGE như cách mặc định để tối ưu query.

### 4.3. Hint không thay thế bằng chứng

Hint có thể bị bỏ qua nếu sai alias/query block, không hợp lệ với cấu trúc SQL, xung đột hint khác hoặc transformation không thể thực hiện. Sau khi thêm hint, kiểm tra execution plan và hint report (nếu phiên bản hỗ trợ) để biết hint có được sử dụng không.

### 4.4. Query block naming

QB_NAME gán tên cho query block để tham chiếu chính xác:

```sql
SELECT /*+ QB_NAME(main_qb) */
       e.employee_id, v.department_name
FROM employees e
JOIN (
    SELECT /*+ QB_NAME(dept_v) */
           department_id, department_name
    FROM departments
    WHERE status = 'ACTIVE'
) v
  ON v.department_id = e.department_id;
```

Tên query block giúp hint ít phụ thuộc vào alias tự sinh và dễ đọc hơn khi SQL có nhiều subquery/inline view. Cú pháp tham chiếu query block trong hint tùy loại hint và phiên bản.

## 5. Subquery unnesting

### 5.1. Khái niệm

Subquery unnesting là transformation chuyển một subquery thành join hoặc cấu trúc quan hệ tương đương trong query block bên ngoài. Mục tiêu là giúp optimizer xem xét join order, join method và access path rộng hơn.

Ví dụ IN subquery:

```sql
SELECT e.employee_id, e.last_name
FROM employees e
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments d
    WHERE d.location_id = 1700
);
```

Optimizer có thể unnest thành semi join giữa EMPLOYEES và DEPARTMENTS, thay vì thực thi subquery như một đơn vị tách biệt cho từng hàng outer.

### 5.2. Correlated subquery

Subquery correlated tham chiếu cột từ query block bên ngoài:

```sql
SELECT e.employee_id, e.last_name
FROM employees e
WHERE EXISTS (
    SELECT 1
    FROM departments d
    WHERE d.department_id = e.department_id
      AND d.location_id = 1700
);
```

Subquery dùng e.department_id từ outer query. Nếu không unnest, subquery có thể được đánh giá theo từng outer row hoặc được xử lý bằng cơ chế khác. Nếu unnest được, optimizer có thể biến nó thành semi join.

### 5.3. Uncorrelated subquery

Subquery không tham chiếu outer query:

```sql
SELECT employee_id, last_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
);
```

Subquery có thể được thực hiện như một tập giá trị độc lập, hoặc optimizer biến đổi thành join. Không nhất thiết phải có correlation mới có unnesting.

### 5.4. Lợi ích

Unnesting có thể:

- Cho phép optimizer chọn join order giữa bảng outer và bảng subquery.
- Dùng hash join, nested loops hoặc merge join/semi join phù hợp.
- Tránh lặp lại việc đánh giá subquery theo từng outer row trong một số trường hợp.
- Kết hợp predicate từ nhiều query block.
- Khai thác index và statistics trên các bảng tham gia.

Unnesting không luôn nhanh hơn. Nếu subquery rất chọn lọc và outer query chỉ có vài hàng, giữ subquery hoặc dùng nested loops có thể rẻ hơn.

## 6. Semi join và EXISTS/IN

### 6.1. Semi join

Semi join trả hàng từ phía outer nếu có ít nhất một hàng match ở phía inner. Nó không nhân bản hàng outer khi inner có nhiều hàng match.

Ví dụ:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Ý nghĩa: trả mỗi customer có ít nhất một order. Dù customer có 20 order, query vẫn trả một hàng customer (trừ khi outer source tự có duplicate).

Nếu viết INNER JOIN trực tiếp:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
```

Customer có nhiều order sẽ xuất hiện nhiều lần. Hai câu không tương đương về cardinality nếu không thêm DISTINCT hoặc aggregation. Semi join là phép toán phù hợp với semantics EXISTS.

### 6.2. IN subquery

IN kiểm tra giá trị outer có thuộc tập giá trị subquery:

```sql
SELECT employee_id
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
);
```

Optimizer có thể chuyển thành semi join. Duplicate department_id ở subquery không làm hàng outer xuất hiện lặp lại, vì IN chỉ kiểm tra membership.

### 6.3. EXISTS subquery

EXISTS chỉ quan tâm có ít nhất một hàng thỏa điều kiện:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

SELECT 1 chỉ là biểu thức đại diện; EXISTS không cần lấy giá trị cột cụ thể. Optimizer có thể dừng tìm kiếm khi đã xác định tồn tại match, tùy plan.

### 6.4. Semi join trong execution plan

Trong plan, có thể gặp operation như:

- NESTED LOOPS SEMI
- HASH JOIN SEMI
- MERGE JOIN SEMI

Tên operation cho biết plan thực hiện semantics semi join. Không phải mọi EXISTS/IN đều xuất hiện đúng một trong các operation này; plan có thể giữ FILTER hoặc dùng cấu trúc khác tùy query và release.

### 6.5. Khi nào semi join có lợi?

Semi join phù hợp khi chỉ cần kiểm tra existence, không cần cột từ inner table. Nó tránh nhân bản hàng outer và thường cho phép optimizer chọn access path dựa trên join condition.

Nếu cần cột của bảng inner, EXISTS không cung cấp chúng; dùng join hoặc scalar subquery theo semantics mong muốn.

## 7. Anti join và NOT EXISTS/NOT IN

### 7.1. Anti join

Anti join trả hàng outer không có hàng match ở inner. Ví dụ khách hàng chưa từng đặt hàng:

```sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Optimizer có thể biến đổi thành anti join.

### 7.2. NOT EXISTS

NOT EXISTS kiểm tra không có hàng thỏa điều kiện tương quan. Nếu subquery không tìm thấy hàng, predicate TRUE.

Ví dụ:

```sql
SELECT p.product_id
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items i
    WHERE i.product_id = p.product_id
);
```

Nếu PRODUCT_ID trong ORDER_ITEMS có NULL, điều kiện equality không match NULL với product_id thông thường; NULL trong inner không làm NOT EXISTS trở thành UNKNOWN theo cách của NOT IN. Vì vậy NOT EXISTS thường dễ kiểm soát semantics hơn khi inner key có thể NULL.

### 7.3. NOT IN và NULL

NOT IN có semantics ba giá trị. Ví dụ:

```sql
SELECT 10
FROM dual
WHERE 10 NOT IN (20, 30, NULL);
```

Kết quả không trả hàng. Vì tập bên phải có NULL, phép so sánh tương đương:

```text
10 <> 20 AND 10 <> 30 AND 10 <> NULL
TRUE AND TRUE AND UNKNOWN = UNKNOWN
```

WHERE chỉ giữ predicate TRUE; UNKNOWN không được giữ. Đây là lý do NOT IN có thể cho kết quả rỗng bất ngờ nếu subquery trả NULL.

### 7.4. So sánh NOT IN và NOT EXISTS

```sql
-- Có thể bị ảnh hưởng bởi NULL trong subquery:
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);

-- Kiểm tra không có hàng match theo equality:
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Nếu ORDERS.CUSTOMER_ID có NULL, hai câu có thể trả kết quả khác nhau. Nếu c.customer_id cũng NULL, NOT EXISTS với phép equality không match NULL và có thể trả hàng outer NULL; cần quyết định nghiệp vụ có muốn giữ hàng đó không.

### 7.5. Viết NOT IN an toàn khi inner key nullable

Nếu nghiệp vụ yêu cầu NOT IN semantics nhưng muốn loại NULL khỏi tập inner, có thể lọc rõ:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
```

Nếu outer key có thể NULL, quyết định rõ có loại nó:

```sql
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (...)
```

Không thêm IS NOT NULL theo thói quen nếu NULL có ý nghĩa nghiệp vụ khác.

### 7.6. Null-aware anti join

Oracle có thể dùng null-aware anti join cho một số NOT IN query để bảo toàn semantics khi inner expression có thể chứa NULL. Trong execution plan có thể thấy operation như HASH JOIN ANTI NA hoặc HASH JOIN ANTI SNA (tùy release/plan notation).

Null-aware anti join không phải lỗi hay dấu hiệu plan xấu tự thân. Nó phản ánh optimizer phải xử lý NULL đúng theo NOT IN. Nếu constraint NOT NULL chứng minh inner expression không thể NULL, optimizer có thể có thêm lựa chọn transformation.

## 8. Điều kiện và hạn chế của subquery unnesting

### 8.1. Subquery không phải lúc nào cũng unnest được

Unnesting có thể bị hạn chế bởi:

- Aggregate hoặc GROUP BY trong subquery.
- ROWNUM và một số row-limiting construct.
- Set operator hoặc cấu trúc query phức tạp.
- Hierarchical query.
- Analytic function trong ngữ cảnh không bảo toàn được semantics.
- Một số subquery chứa outer join hoặc biểu thức đặc biệt.
- Correlation phức tạp, nhiều query block hoặc tham chiếu không thể decorrelate.
- Các điều kiện có thể thay đổi kết quả khi chuyển thành join.

Oracle hỗ trợ nhiều trường hợp unnesting có điều kiện, kể cả một số aggregate/complex subquery. Vì vậy, coi đây là nhóm yếu tố cần kiểm tra chứ không phải danh sách cấm tuyệt đối.

### 8.2. Aggregate trong correlated subquery

Ví dụ:

```sql
SELECT e.employee_id
FROM employees e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees e2
    WHERE e2.department_id = e.department_id
);
```

Subquery tính average theo department của từng employee. Optimizer có thể áp dụng transformation phức tạp như aggregate decorrelation hoặc giữ subquery tùy điều kiện/cost. Không được thay trực tiếp bằng join raw EMPLOYEES vì có thể nhân bản hàng hoặc tính sai average.

Một rewrite thủ công có thể aggregate trước rồi join:

```sql
SELECT e.employee_id
FROM employees e
JOIN (
    SELECT department_id, AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
) a
  ON a.department_id = e.department_id
WHERE e.salary > a.avg_salary;
```

Rewrite này cần xem xét trường hợp department_id NULL: phép equality join không match NULL trong khi correlated predicate cũng không match NULL; nếu subquery không có hàng, AVG trả NULL và điều kiện salary > NULL là UNKNOWN, nên outer row bị loại. Ví dụ vẫn cần kiểm tra semantics khi có các điều kiện khác, aggregate/filter và NULL.

### 8.3. Scalar subquery

Scalar subquery trả một giá trị scalar cho mỗi outer row:

```sql
SELECT
    e.employee_id,
    (
        SELECT d.department_name
        FROM departments d
        WHERE d.department_id = e.department_id
    ) AS department_name
FROM employees e;
```

Scalar subquery có semantics quan trọng: 0 hàng trả NULL; 1 hàng trả giá trị; hơn 1 hàng gây ORA-01427. Không thể rewrite thành join thông thường nếu không bảo toàn hành vi này, nhất là uniqueness và duplicate. Oracle có thể thực hiện scalar subquery caching hoặc các transformation khác; không giả định mỗi outer row luôn gây một lần physical lookup.

### 8.4. Correlation và số lần thực thi

Plan có operation FILTER hoặc SUBQUERY không tự chứng minh subquery chạy một lần cho mỗi outer row. Oracle có thể cache scalar result, dùng nested loops, unnest hoặc chọn cách khác. Xem Starts, A-Rows và buffers trong actual plan để đánh giá thực tế.

## 9. UNNEST và NO_UNNEST hints

### 9.1. UNNEST hint

UNNEST yêu cầu optimizer xem xét unnest một subquery:

```sql
SELECT e.employee_id
FROM employees e
WHERE e.department_id IN (
    SELECT /*+ UNNEST */
           d.department_id
    FROM departments d
    WHERE d.location_id = 1700
);
```

Hint thường được đặt trong subquery cần unnest. Cú pháp chính xác và khả năng áp dụng tùy query/release.

### 9.2. NO_UNNEST hint

NO_UNNEST yêu cầu giữ subquery ở dạng nested subquery thay vì unnest:

```sql
SELECT e.employee_id
FROM employees e
WHERE e.department_id IN (
    SELECT /*+ NO_UNNEST */
           d.department_id
    FROM departments d
    WHERE d.location_id = 1700
);
```

Có thể dùng để kiểm tra plan thay thế hoặc tránh một transformation cụ thể khi có bằng chứng nó làm tăng cost. Không nên dùng NO_UNNEST chỉ vì muốn giữ SQL đúng như viết.

### 9.3. Hints và query block

Khi query nhiều tầng, đặt QB_NAME cho các query block và dùng hint đúng block. Hints không đúng vị trí hoặc tham chiếu sai query block có thể không được sử dụng.

### 9.4. So sánh bằng plan

Chạy query không hint, với UNNEST và NO_UNNEST trong môi trường thử nghiệm. So sánh:

- Join operation và join order.
- Estimated rows và actual rows.
- Starts của subquery.
- Buffer gets, reads, elapsed time và CPU.
- Tác động của bind values và statistics.

Không chọn hint chỉ dựa vào việc plan nhìn có vẻ đơn giản hơn.

## 10. Predicate pushing

### 10.1. Khái niệm

Predicate pushing (predicate pushdown) là transformation đưa điều kiện lọc xuống query block hoặc row source thấp hơn để loại hàng sớm hơn. Điều này có thể giảm số hàng được materialize, join, sort, aggregate hoặc truyền qua các bước kế tiếp.

Ví dụ:

```sql
SELECT *
FROM (
    SELECT employee_id, department_id, salary
    FROM employees
) v
WHERE v.department_id = 50;
```

Predicate department_id = 50 có thể được đẩy vào query block của view:

```sql
SELECT employee_id, department_id, salary
FROM employees
WHERE department_id = 50;
```

Nếu view không merge được, predicate pushing vẫn có thể giúp lọc hàng bên trong view trước khi kết quả được kết hợp với query ngoài.

### 10.2. Predicate pushing khác view merging

- View merging gộp query block.
- Predicate pushing giữ ranh giới query block nhưng chuyển điều kiện lọc xuống bên trong nếu hợp lệ.

Hai transformation có thể bổ trợ nhau. Một view không merge được vẫn có thể nhận predicate từ query ngoài. Ngược lại, sau khi merge, predicate có thể trở thành một điều kiện trong cùng query block.

### 10.3. Filter sớm có thể giảm công việc

Nếu bảng có 10 triệu hàng nhưng predicate chỉ giữ 100 hàng, đẩy predicate xuống table access có thể giảm dữ liệu đi qua join/sort. Tuy nhiên, predicate không nhất thiết được đẩy nếu:

- Không thể đánh giá ở query block thấp hơn.
- Đẩy xuống làm thay đổi semantics.
- Biểu thức không an toàn hoặc không thể di chuyển.
- Cost model đánh giá phương án khác tốt hơn.

### 10.4. Predicate pushdown qua UNION ALL

Ví dụ:

```sql
SELECT customer_id, status
FROM (
    SELECT customer_id, status
    FROM current_customers
    UNION ALL
    SELECT customer_id, status
    FROM archived_customers
) all_customers
WHERE status = 'ACTIVE';
```

Predicate status = 'ACTIVE' có thể được đẩy vào từng nhánh:

```sql
SELECT customer_id, status
FROM current_customers
WHERE status = 'ACTIVE'
UNION ALL
SELECT customer_id, status
FROM archived_customers
WHERE status = 'ACTIVE';
```

Vì UNION ALL giữ tất cả hàng từ cả hai nhánh, phân phối một predicate áp dụng cho kết quả chung xuống từng nhánh là hợp lệ nếu biểu thức/kiểu dữ liệu tương thích. Với UNION (distinct), transformation vẫn có thể được xem xét nhưng phải bảo toàn duplicate elimination.

### 10.5. Predicate trên grouping key

View:

```sql
SELECT department_id, SUM(salary) AS total_salary
FROM employees
GROUP BY department_id;
```

Query ngoài:

```sql
SELECT *
FROM (
    SELECT department_id, SUM(salary) AS total_salary
    FROM employees
    GROUP BY department_id
) v
WHERE v.department_id = 50;
```

Predicate trên department_id là grouping key và có thể được đẩy thành WHERE department_id = 50 trước aggregation trong trường hợp này. Điều đó cho phép Oracle chỉ đọc/aggregate dữ liệu department 50.

### 10.6. Predicate trên aggregate

Nếu query ngoài lọc:

```sql
WHERE v.total_salary > 100000
```

Điều kiện tương ứng là HAVING SUM(salary) > 100000 sau aggregation, không thể đưa thành WHERE salary > 100000. Đưa predicate aggregate xuống trước GROUP BY sẽ thay đổi các hàng đóng góp vào tổng.

### 10.7. Predicate trên outer join

Với outer join, predicate từ phía null-generated side có thể làm thay đổi preserved rows nếu chuyển sai từ WHERE sang ON hoặc ngược lại. Optimizer chỉ push khi có thể giữ đúng null-preserving semantics.

Ví dụ cần phân biệt:

```sql
-- Loại department không có employee ACTIVE:
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';

-- Giữ mọi department, chỉ match employee ACTIVE:
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
```

Không tự chuyển predicate qua outer join chỉ để query trông gọn.

## 11. Join predicate pushdown (JPPD)

### 11.1. Khái niệm

Join predicate pushdown là transformation đẩy join predicate từ query block bên ngoài vào một view chưa merge được. View có thể trở thành correlated với hàng từ outer query; Oracle có thể thực thi view cho từng giá trị join key bằng nested loops hoặc một plan phù hợp khác.

Ví dụ:

```sql
SELECT d.department_id, v.max_salary
FROM departments d
JOIN (
    SELECT department_id, MAX(salary) AS max_salary
    FROM employees
    GROUP BY department_id
) v
  ON v.department_id = d.department_id
WHERE d.location_id = 1700;
```

Nếu view không merge, optimizer vẫn có thể đẩy điều kiện nối department_id từ DEPARTMENTS vào view để chỉ tính/đọc phần cần thiết cho từng department thay vì tạo toàn bộ kết quả aggregate rồi join. Khả năng và lợi ích phụ thuộc cấu trúc query, cardinality, index và cost.

### 11.2. View trở thành correlated

Sau JPPD, view có thể tham chiếu giá trị từ outer row. Điều này có thể tạo một correlated view. Execution plan thường thể hiện nested loops hoặc operation truy cập view lặp theo outer rows, nhưng chi tiết plan thay đổi theo release.

JPPD có thể có lợi khi outer row source nhỏ và predicate join chọn lọc. Nếu outer có hàng triệu hàng, việc chạy inner view lặp lại có thể đắt hơn một hash join với view được tính một lần.

### 11.3. PUSH_PRED và NO_PUSH_PRED

PUSH_PRED yêu cầu optimizer xem xét đẩy join predicate vào view:

```sql
SELECT /*+ PUSH_PRED(v) */
       d.department_id, v.max_salary
FROM departments d
JOIN (
    SELECT department_id, MAX(salary) AS max_salary
    FROM employees
    GROUP BY department_id
) v
  ON v.department_id = d.department_id
WHERE d.location_id = 1700;
```

NO_PUSH_PRED yêu cầu không áp dụng join predicate pushdown cho view được chỉ định:

```sql
SELECT /*+ NO_PUSH_PRED(v) */
       d.department_id, v.max_salary
FROM departments d
JOIN (
    SELECT department_id, MAX(salary) AS max_salary
    FROM employees
    GROUP BY department_id
) v
  ON v.department_id = d.department_id
WHERE d.location_id = 1700;
```

Hint không bảo đảm plan nhanh hơn. Hãy kiểm tra alias, query block, hint report và actual runtime.

### 11.4. Phân biệt predicate pushing và JPPD

| Kỹ thuật | Predicate được đẩy | Mục tiêu |
| --- | --- | --- |
| Predicate pushing | Filter từ query ngoài vào view/subquery | Lọc dữ liệu sớm |
| Join predicate pushdown | Điều kiện join từ outer block vào view | Tạo view correlated, tận dụng outer key |
| View merging | Toàn bộ query block view được gộp | Mở rộng không gian join order/access path |

Ba kỹ thuật có liên quan nhưng không đồng nghĩa. Một view có thể không merge được nhưng vẫn nhận predicate pushdown hoặc JPPD.

## 12. Predicate pushdown và các ranh giới đặc biệt

### 12.1. DISTINCT

Predicate trên cột được chiếu qua DISTINCT có thể được push trong trường hợp bảo toàn tập distinct. Ví dụ lọc region_code sau khi distinct có thể tương đương lọc trước distinct nếu predicate chỉ tham chiếu cùng biểu thức cột:

```sql
SELECT *
FROM (
    SELECT DISTINCT region_code
    FROM customers
) v
WHERE v.region_code = 'VN';
```

Nhưng không được loại DISTINCT nếu join hoặc duplicate ở query ngoài khiến cardinality thay đổi. Transformation phải giữ semantics toàn statement.

### 12.2. Analytic functions

Analytic function tính trên tập hàng của query block. Đẩy predicate xuống trước khi analytic function chạy có thể thay đổi window và kết quả.

Ví dụ:

```sql
SELECT *
FROM (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC
           ) AS rn
    FROM employees
) v
WHERE v.department_id = 50
  AND v.rn <= 3;
```

Predicate department_id = 50 có thể được xử lý sớm trong nhiều trường hợp vì nó giới hạn một partition độc lập; predicate rn <= 3 phụ thuộc kết quả analytic function và không thể được đẩy như filter thông thường xuống trước khi ROW_NUMBER được tính. Oracle có các transformation chuyên biệt để xử lý một số top-N pattern, nhưng phải bảo toàn semantics.

### 12.3. ROWNUM và row limiting

ROWNUM được gán theo thứ tự hàng mà query block phát ra; việc đẩy predicate qua ranh giới ROWNUM có thể thay đổi tập hàng được chọn. Ví dụ:

```sql
SELECT *
FROM (
    SELECT *
    FROM employees
    WHERE department_id = 10
    ORDER BY salary DESC
)
WHERE ROWNUM <= 5;
```

Đây là pattern top-N với sắp xếp trong view rồi giới hạn ở ngoài. Không đưa ROWNUM vào query block bên trong trước ORDER BY vì có thể lấy 5 hàng trước khi sắp xếp, tạo kết quả khác.

### 12.4. CONNECT BY

Hierarchical query có semantics về parent/child và thứ tự traversal. Predicate có thể áp dụng trước hoặc sau khi hình thành cây; đẩy sai vị trí có thể làm mất ancestor cần thiết hoặc thay đổi nhánh kết quả. Không rewrite CONNECT BY chỉ dựa trên vị trí predicate mà không kiểm tra cây kết quả.

### 12.5. Functions trong predicate

Predicate chứa function user-defined, function phụ thuộc session hoặc function không deterministic có thể hạn chế khả năng di chuyển và tạo chi phí đánh giá. Không dùng side-effecting function trong predicate. Nếu biểu thức có thể được viết bằng SQL built-in hoặc function-based index, cân nhắc cách đó.

### 12.6. Remote tables và database links

Với distributed query, predicate pushdown có thể chuyển filter tới remote database để giảm dữ liệu truyền qua database link. Khả năng push phụ thuộc loại biểu thức, datatype, remote version và tính tương thích. Kiểm tra plan có operation REMOTE và remote SQL thực tế; không giả định mọi predicate đều được gửi xuống remote.

## 13. View merging, unnesting và predicate pushing tương tác

### 13.1. Một query có thể dùng nhiều transformation

Ví dụ:

```sql
SELECT e.employee_id, e.last_name
FROM employees e
JOIN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
) d
  ON d.department_id = e.department_id
WHERE EXISTS (
    SELECT 1
    FROM job_history h
    WHERE h.employee_id = e.employee_id
);
```

Optimizer có thể:

- Merge inline view DEPARTMENTS nếu view đủ đơn giản.
- Unnest EXISTS thành semi join.
- Push predicate location_id xuống DEPARTMENTS.
- Dùng join order và join method tối ưu cho tập bảng sau transformation.

Plan cuối cùng không nhất thiết giữ các alias hoặc tầng SELECT như văn bản ban đầu.

### 13.2. Transformation có thể mở ra transformation khác

Merge view có thể làm lộ thêm join predicate và tạo điều kiện cho join elimination, predicate transitivity hoặc join reordering. Unnest subquery có thể đưa bảng inner vào cùng query block để optimizer push predicate hoặc chọn join method khác.

Đây là lý do không nên đánh giá một transformation tách biệt khỏi toàn plan. Một transformation có thể có lợi vì nó mở ra các lựa chọn tiếp theo.

### 13.3. Transformation cũng có thể làm không gian tìm kiếm lớn hơn

Thêm query block, view merge hoặc unnest nhiều subquery làm tăng số phương án optimizer có thể cân nhắc. Oracle có giới hạn và chiến lược search để kiểm soát thời gian parse/optimization. Với query rất phức tạp, optimizer không nhất thiết thử mọi permutation có thể.

### 13.4. Hints có thể tạo tương tác ngoài dự kiến

MERGE, NO_MERGE, UNNEST, NO_UNNEST và PUSH_PRED có thể tác động đến query block và cơ hội áp dụng transformation khác. Một hint buộc giữ view có thể làm mất một join order; một hint unnest có thể làm tăng cardinality của intermediate row source nếu semantics/query structure không phù hợp.

Nếu phải dùng nhiều hint, ghi rõ mục tiêu của từng hint, tên query block và bằng chứng plan/runtime. Tránh chồng nhiều hint mâu thuẫn.

## 14. Đọc execution plan để nhận biết transformation

### 14.1. DBMS_XPLAN

Để xem plan:

```sql
EXPLAIN PLAN FOR
SELECT e.employee_id
FROM employees e
WHERE EXISTS (
    SELECT 1
    FROM departments d
    WHERE d.department_id = e.department_id
      AND d.location_id = 1700
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

EXPLAIN PLAN cho estimated plan, không nhất thiết phản ánh bind values, runtime row counts hoặc child cursor đang chạy trong ứng dụng.

### 14.2. Actual plan

Với query đã chạy và có statistics phù hợp, có thể xem:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +OUTLINE'
    )
);
```

ALLSTATS LAST cần runtime row-source statistics được thu thập, ví dụ bằng GATHER_PLAN_STATISTICS hint hoặc cấu hình phù hợp. DISPLAY_CURSOR đọc cursor trong shared pool; cần quyền truy cập các fixed views.

### 14.3. Dấu hiệu semi/anti join

Plan có thể hiện:

- HASH JOIN SEMI
- NESTED LOOPS SEMI
- HASH JOIN ANTI
- HASH JOIN ANTI NA / ANTI SNA

Các operation này là bằng chứng mạnh rằng existence/non-existence predicate đã được biểu diễn thành join dạng semi/anti.

### 14.4. Dấu hiệu view còn riêng

Plan có thể có VIEW operation, nhưng chỉ thấy VIEW không đủ để kết luận transformation nào đã/không xảy ra. Một view có thể được giữ lại, được push predicate hoặc được thực hiện như một row source riêng. Xem ALIAS, Predicate Information, Outline Data và query block mapping.

### 14.5. Predicate Information

Predicate Information cho biết predicate được dùng làm access predicate hoặc filter predicate ở operation nào. Điều này giúp nhận ra predicate có được đẩy xuống table access hay còn ở bước filter phía trên.

Ví dụ:

```text
access("E"."DEPARTMENT_ID"=50)
filter("E"."SALARY">5000)
```

ACCESS predicate thường tham gia xác định row source/index lookup; FILTER predicate lọc hàng sau khi được lấy. Ý nghĩa chính xác phụ thuộc operation; không phải mọi filter ở trên là xấu.

### 14.6. Query block name và outline

Với format +ALIAS và +OUTLINE, plan có thể hiển thị query block/alias và hint outline mà Oracle dùng để mô tả plan. Dùng thông tin này để hiểu view/subquery nào đã được merge hoặc unnest và hint nào có thể tái tạo plan.

Không copy outline hint vào production một cách mù quáng; outline có thể phụ thuộc object, release và statistics.

### 14.7. So sánh estimated và actual rows

Nếu E-Rows khác xa A-Rows, optimizer có thể chọn transformation/join method dựa trên cardinality sai. Kiểm tra:

- Statistics bảng và index có mới không?
- Data skew có cần histogram không?
- Correlation giữa các cột có cần extended statistics không?
- Predicate có bind variable và bind peeking/adaptive cursor sharing không?
- Cardinality sau view merge/unnest có được ước lượng đúng không?

Transformation đúng về semantics nhưng cost dựa trên ước lượng sai vẫn có thể dẫn tới plan kém.

## 15. WITH clause, inline view và materialization

### 15.1. CTE không mặc định là bảng tạm

WITH clause (subquery factoring) đặt tên cho một query block:

```sql
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE status = 'ACTIVE'
)
SELECT department_id, COUNT(*)
FROM active_employees
GROUP BY department_id;
```

CTE giúp tổ chức SQL và tái sử dụng logic. Nó không tự động có nghĩa Oracle phải tạo bảng tạm vật lý. Optimizer có thể inline/merge CTE vào query block sử dụng nó, hoặc chọn TEMP TABLE TRANSFORMATION/materialization trong những trường hợp phù hợp.

### 15.2. Inline/merge CTE

Nếu CTE đơn giản và chỉ dùng một lần, optimizer có thể inline nó để tối ưu toàn query. Khi đó CTE giống một inline view được merge; ranh giới đặt tên trong SQL không nhất thiết còn là ranh giới vật lý trong plan.

### 15.3. Materialize CTE

Trong một số query, materialize CTE có thể hữu ích khi kết quả trung gian được dùng nhiều lần hoặc việc tính lại đắt. Plan có thể xuất hiện TEMP TABLE TRANSFORMATION, LOAD AS SELECT và đọc từ temporary table nội bộ.

Materialization có chi phí:

- Ghi/đọc dữ liệu trung gian.
- Dùng TEMP space.
- Có thể mất cơ hội push predicate hoặc join reordering sâu hơn.
- Có thể có lợi nếu tránh tính lại một kết quả đắt và được tái sử dụng.

Không mặc định materialize luôn nhanh hơn inline.

### 15.4. NO_MERGE không đồng nghĩa materialize

NO_MERGE giữ một query block riêng theo transformation đó; nó không phải cam kết rằng Oracle sẽ ghi kết quả view ra temporary table. View có thể được thực thi như row source riêng, predicate có thể vẫn được push, và optimizer vẫn chọn cách triển khai khác.

Phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| View merging | Gộp query block |
| NO_MERGE | Ngăn merge view được chỉ định khi hint được áp dụng |
| CTE inline | CTE được mở rộng vào query sử dụng |
| Materialization | Tạo và đọc kết quả trung gian theo plan |
| TEMP TABLE TRANSFORMATION | Operation thể hiện chiến lược materialize trong plan |

### 15.5. MATERIALIZE và INLINE hints

Trong một số Oracle release, người dùng gặp các hint MATERIALIZE và INLINE để ảnh hưởng cách xử lý CTE. Mức độ documented/support và hành vi của chúng có thể thay đổi theo release. Không dựa vào hint không được tài liệu phiên bản bảo đảm như một API ổn định; ưu tiên xem plan, kiểm tra tính năng được hỗ trợ và dùng SQL Plan Management nếu cần ổn định plan ở production.

## 16. Các hint liên quan và cách dùng có kỷ luật

### 16.1. Nhóm hint transformation

| Hint | Mục đích tổng quát |
| --- | --- |
| MERGE | Yêu cầu xem xét view merging |
| NO_MERGE | Ngăn merge view được chỉ định |
| UNNEST | Yêu cầu xem xét subquery unnesting |
| NO_UNNEST | Ngăn unnest subquery được chỉ định |
| PUSH_PRED | Yêu cầu xem xét join predicate pushdown |
| NO_PUSH_PRED | Ngăn join predicate pushdown |
| PUSH_SUBQ | Yêu cầu đẩy subquery xuống sớm hơn trong plan khi áp dụng |
| NO_PUSH_SUBQ | Ngăn subquery pushing theo hint được chỉ định |
| QB_NAME | Đặt tên query block để tham chiếu |

Hint chỉ tác động khi đúng ngữ cảnh, cú pháp và transformation hợp lệ. Không coi đây là các nút bật/tắt toàn cục cho mọi transformation trong statement.

### 16.2. Đặt hint đúng query block

Ví dụ đặt tên:

```sql
SELECT /*+ QB_NAME(main) */
       e.employee_id
FROM employees e
WHERE EXISTS (
    SELECT /*+ QB_NAME(dept_exists) UNNEST */
           1
    FROM departments d
    WHERE d.department_id = e.department_id
      AND d.location_id = 1700
);
```

Khi SQL lớn, đặt QB_NAME có ý nghĩa giúp trace hint dễ hơn. Tên query block và alias phải nhất quán; kiểm tra plan alias/outline để xác nhận.

### 16.3. Hint conflict và ignored hints

Ví dụ, đặt MERGE và NO_MERGE cho cùng view hoặc UNNEST và NO_UNNEST cho cùng subquery tạo xung đột. Oracle có quy tắc ưu tiên/diễn giải hint theo vị trí và release; không nên dựa vào kết quả không rõ ràng.

Kiểm tra hint report nếu phiên bản hỗ trợ:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALL +HINT_REPORT'
    )
);
```

Hint report giúp thấy hint được sử dụng, bị bỏ qua hay có lỗi cú pháp/đối tượng. Nếu format không được hỗ trợ trong release, dùng outline và các cách chẩn đoán tương ứng.

### 16.4. Không chỉnh hidden optimizer parameters để ép transformation

Các tham số có dấu gạch dưới như _optimizer_* là hidden parameters, không phải giao diện tuning thông thường. Không thay đổi chúng tùy tiện trong session hoặc system. Việc can thiệp có thể gây hành vi không được hỗ trợ và ảnh hưởng nhiều query. Nếu nghi ngờ bug optimizer, thu thập SQL, plan, version, trace và làm việc theo hướng dẫn Oracle Support.

### 16.5. OPTIMIZER_FEATURES_ENABLE

OPTIMIZER_FEATURES_ENABLE có thể dùng trong kiểm thử để mô phỏng tập hành vi optimizer của một release trước. Nó không phải cách chữa mặc định cho một query chậm và có thể làm nhiều quyết định optimizer khác thay đổi cùng lúc. Chỉ dùng có kiểm soát, đo workload và theo hướng dẫn migration/upgrade.

## 17. Quy trình điều tra transformation trong query chậm

### 17.1. Bắt đầu từ SQL và dữ liệu thực

Thu thập:

- SQL text thực tế và query binds.
- Oracle version, optimizer_features_enable và relevant session settings.
- Object definitions, constraints, indexes và partitioning.
- Statistics và histogram liên quan.
- SQL_ID, child cursor và execution plan thực tế.
- Runtime rows, elapsed time, CPU, buffer gets, physical reads và waits.

Không kết luận từ một câu SQL đã rút gọn nếu production dùng bind values hoặc dynamic predicates khác.

### 17.2. Xác định transformation nào đang được nghi ngờ

Đặt câu hỏi cụ thể:

- Inline view có bị giữ riêng làm mất join order tốt hơn không?
- EXISTS/IN có bị giữ như FILTER subquery và tạo nhiều Starts không?
- Predicate lọc có còn ở query block trên sau khi view đã tạo nhiều hàng không?
- JPPD có làm inner view chạy quá nhiều lần không?
- Complex view merge có làm tăng intermediate cardinality hoặc thay đổi aggregation strategy không?

Không dùng cụm “optimizer không tối ưu” khi chưa xác định được operation và bằng chứng.

### 17.3. So sánh plan có kiểm soát

Tạo các biến thể:

1. SQL gốc, không hint.
2. SQL gốc với hint transformation được nghi ngờ.
3. SQL rewrite thủ công có semantics tương đương.
4. Biến thể có/không có predicate hoặc CTE theo giả thuyết.

Chạy cùng dữ liệu/bind values, cùng môi trường và warm/cold cache có kiểm soát. Đo nhiều lần và dùng actual plan.

### 17.4. Kiểm tra cardinality trước khi ép transformation

Nếu estimated rows sai lớn, sửa statistics hoặc cung cấp thông tin tương quan phù hợp có thể giúp optimizer tự chọn transformation tốt hơn. Các lựa chọn gồm gather statistics, histogram khi skew có ý nghĩa, extended statistics cho column groups và kiểm tra dynamic sampling.

Không thêm histogram hoặc extended statistics hàng loạt mà không có bằng chứng; chúng có thể làm plan thay đổi ở nhiều query.

### 17.5. Kiểm tra bind peeking và adaptive cursor sharing

Một query có thể chạy với nhiều giá trị bind có selectivity rất khác nhau. Plan tối ưu cho location_id phổ biến có thể không tối ưu cho location_id hiếm. Kiểm tra child cursors, bind peeking và adaptive cursor sharing trước khi kết luận transformation là nguyên nhân duy nhất.

### 17.6. Dùng SQL Monitor/trace khi cần

SQL Monitor, SQL Trace/TKPROF và optimizer trace có thể cung cấp chi tiết runtime hoặc quyết định optimizer. Quyền sử dụng, licensing và overhead phụ thuộc môi trường. Thu thập theo phạm vi nhỏ, trên query cụ thể, và tắt trace sau khi hoàn tất.

## 18. 10053 optimizer trace

### 18.1. Mục đích

Event 10053 là optimizer trace chuyên sâu, ghi lại nhiều quyết định trong quá trình tối ưu SQL, bao gồm một số transformation được xem xét, lý do bị loại, cardinality/cost estimate và phương án plan.

Đây là công cụ chẩn đoán nâng cao, không phải trace bật thường xuyên trên production.

### 18.2. Thu thập có kiểm soát

Trong môi trường thử nghiệm hoặc theo hướng dẫn DBA/Oracle Support, có thể bật trace cho session/query cụ thể. Ví dụ minh họa một cách dùng event ở session:

```sql
ALTER SESSION SET EVENTS '10053 trace name context forever, level 1';

-- Parse/execute câu SQL cần điều tra.
SELECT ...

ALTER SESSION SET EVENTS '10053 trace name context off';
```

Cú pháp event và level phù hợp tùy release; thực hiện theo tài liệu/khuyến nghị hỗ trợ. Trace thường tập trung vào hard parse/optimization, không phải công cụ đo elapsed time thực thi.

### 18.3. Đọc trace

Trace có thể chứa:

- Query block transformations được thử.
- View merging/unnesting decisions.
- Predicate move-around.
- Join order alternatives.
- Estimated cardinality và cost.
- Lý do một transformation không được áp dụng.

Trace lớn và phức tạp. Chỉ đọc phần liên quan query block/transform đang điều tra; không chia sẻ file trace công khai nếu có SQL text, object names, bind values hoặc dữ liệu nhạy cảm.

## 19. Bài lab: view merging và predicate pushing

Các ví dụ dùng schema mẫu có EMPLOYEES và DEPARTMENTS. Nếu schema không có, tạo bảng lab riêng hoặc thay bằng bảng tương ứng; không chạy DDL trên schema production.

### 19.1. Query inline view đơn giản

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       v.employee_id, v.department_id
FROM (
    SELECT employee_id, department_id
    FROM employees
    WHERE salary > 5000
) v
WHERE v.department_id = 50;
```

Sau khi chạy, xem actual plan bằng DBMS_XPLAN.DISPLAY_CURSOR. Quan sát view có còn là operation riêng hay predicates đã xuất hiện tại table access.

### 19.2. So sánh MERGE và NO_MERGE

```sql
SELECT /*+ GATHER_PLAN_STATISTICS MERGE(v) */
       v.employee_id, d.department_name
FROM (
    SELECT employee_id, department_id
    FROM employees
    WHERE salary > 5000
) v
JOIN departments d
  ON d.department_id = v.department_id
WHERE d.location_id = 1700;
```

Chạy biến thể:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS NO_MERGE(v) */
       v.employee_id, d.department_name
FROM (
    SELECT employee_id, department_id
    FROM employees
    WHERE salary > 5000
) v
JOIN departments d
  ON d.department_id = v.department_id
WHERE d.location_id = 1700;
```

So sánh join order, view operation, E-Rows/A-Rows, buffer gets và elapsed time. Hint có thể không được áp dụng nếu view đã merge tự động hoặc không đủ điều kiện; xác nhận bằng plan/hint report.

### 19.3. Predicate pushing vào view có UNION ALL

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       x.customer_id
FROM (
    SELECT customer_id, status FROM current_customers
    UNION ALL
    SELECT customer_id, status FROM archived_customers
) x
WHERE x.status = 'ACTIVE';
```

Kiểm tra Predicate Information và table access của từng nhánh. Predicate có thể xuất hiện ở cả hai nhánh. Đây là ví dụ để quan sát predicate pushdown mà không cần view merging toàn bộ set operator.

### 19.4. Predicate trên grouping key

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       v.department_id, v.total_salary
FROM (
    SELECT department_id, SUM(salary) AS total_salary
    FROM employees
    GROUP BY department_id
) v
WHERE v.department_id = 50;
```

Quan sát predicate department_id được áp dụng ở đâu. Sau đó thử predicate trên total_salary và so sánh vì điều kiện aggregate phải được đánh giá sau GROUP BY.

## 20. Bài lab: subquery unnesting và NULL semantics

### 20.1. EXISTS

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

Xem plan có SEMI join hay FILTER. So sánh Starts, A-Rows và buffer gets.

### 20.2. Thử UNNEST và NO_UNNEST

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT /*+ UNNEST */ 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT /*+ NO_UNNEST */ 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

Không chỉ so sánh số operation; chạy cùng bind/data và xem actual statistics.

### 20.3. NOT IN có NULL

Tạo tập nhỏ:

```sql
WITH candidates (id) AS (
    SELECT 1 FROM dual
    UNION ALL
    SELECT 2 FROM dual
    UNION ALL
    SELECT 3 FROM dual
),
blocked_ids (id) AS (
    SELECT 2 FROM dual
    UNION ALL
    SELECT CAST(NULL AS NUMBER) FROM dual
)
SELECT id
FROM candidates
WHERE id NOT IN (SELECT id FROM blocked_ids);
```

Kết quả không trả hàng do inner set chứa NULL. Thử thay NOT IN bằng NOT EXISTS:

```sql
WITH candidates (id) AS (
    SELECT 1 FROM dual
    UNION ALL
    SELECT 2 FROM dual
    UNION ALL
    SELECT 3 FROM dual
),
blocked_ids (id) AS (
    SELECT 2 FROM dual
    UNION ALL
    SELECT CAST(NULL AS NUMBER) FROM dual
)
SELECT c.id
FROM candidates c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_ids b
    WHERE b.id = c.id
);
```

Kết quả có thể gồm 1 và 3. Khác biệt là semantics SQL có NULL, không phải optimizer làm sai. Bài lab này giúp xác định rewrite nào bảo toàn nghiệp vụ.

## 21. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Inline view vẫn có VIEW operation | View không merge, được giữ có chủ đích hoặc plan thể hiện row source riêng | Xem query block, alias, predicates và transformation eligibility |
| View merge làm query chậm | Join order/cardinality sau merge không phù hợp | So sánh actual plan, thử NO_MERGE trong test và kiểm tra statistics |
| EXISTS chạy với FILTER nhiều Starts | Subquery chưa unnest hoặc plan chọn cách đó | Xem Starts/A-Rows; thử UNNEST có kiểm soát |
| NOT IN không trả hàng | Inner subquery có NULL | Xác định semantics mong muốn; xem xét NOT EXISTS hoặc lọc NULL nếu đúng nghiệp vụ |
| NOT EXISTS và NOT IN trả khác nhau | NULL semantics khác nhau | Kiểm tra NULL ở cả outer và inner key |
| Predicate vẫn ở operation phía trên | Không push được, không hợp lệ hoặc cost không chọn | Kiểm tra query block boundary và Predicate Information |
| UNION ALL view đọc nhiều hàng | Predicate chưa được push vào nhánh hoặc thiếu access path | Kiểm tra plan từng branch, index và statistics |
| JPPD tạo nhiều Starts | Outer row source lớn, view bị chạy lặp | So sánh hash join/materialize với nested loops; kiểm tra cardinality |
| GROUP BY view tính quá nhiều hàng | Filter grouping key không được push hoặc stats sai | Kiểm tra predicate mapping, group cardinality và cost |
| Outer join mất hàng sau rewrite | Predicate chuyển sai giữa ON và WHERE | Kiểm tra null-preserving semantics và dữ liệu không match |
| Hint không có tác dụng | Sai alias/query block, hint conflict hoặc transformation không hợp lệ | Dùng QB_NAME, outline và hint report |
| Plan thay đổi giữa các bind | Selectivity khác nhau, child cursor/adaptive cursor sharing | Kiểm tra bind peeking, child cursors và actual rows |
| EXPLAIN PLAN khác runtime | Bind, environment hoặc child cursor khác | Dùng DISPLAY_CURSOR cho cursor thực tế |
| Query chậm dù transformation đúng | Cardinality/cost estimate sai hoặc access path không phù hợp | Kiểm tra statistics, E-Rows/A-Rows, waits và I/O |

## 22. Nguyên tắc thực hành tốt

1. **Hiểu semantics trước khi rewrite.** Đặc biệt chú ý NULL, duplicate, outer join, aggregation, ROWNUM và analytic functions.
2. **Đọc query theo query block.** Đặt tên block khi SQL nhiều tầng để theo dõi transformation.
3. **Để optimizer tự chọn trước.** Không thêm hint khi chưa có baseline plan và actual runtime.
4. **Phân biệt view merging với predicate pushing.** Một view không merge vẫn có thể nhận filter/join predicate.
5. **Dùng EXISTS/IN cho existence.** Đừng thay bằng join nếu không xử lý duplicate/cardinality.
6. **Cẩn thận NOT IN với NULL.** Kiểm tra nullability và semantics trước khi rewrite sang NOT EXISTS.
7. **Không đẩy aggregate predicate xuống WHERE.** Phân biệt filter hàng với filter nhóm.
8. **Giữ outer join semantics.** Predicate ở ON và WHERE có thể tạo kết quả khác.
9. **Dùng hints như công cụ thử nghiệm có bằng chứng.** MERGE/NO_MERGE/UNNEST/NO_UNNEST/PUSH_PRED không phải nút tăng tốc chung.
10. **Dùng QB_NAME và hint report.** Xác nhận hint tác động đúng query block.
11. **So sánh actual plan.** Dùng A-Rows, Starts, buffers và runtime; không chỉ nhìn EXPLAIN PLAN.
12. **Sửa cardinality estimate trước khi ép plan.** Statistics sai có thể là gốc vấn đề.
13. **Đo theo bind values thực tế.** Một plan không phù hợp mọi selectivity.
14. **Không sửa hidden optimizer parameters tùy tiện.** Thu thập bằng chứng và theo hướng dẫn Oracle Support khi nghi ngờ optimizer bug.
15. **Kiểm tra sau upgrade.** Transformation và cost model có thể đổi theo release/optimizer_features_enable.
16. **Giữ SQL dễ hiểu.** Query transformation là quyết định của optimizer; SQL vẫn nên mô tả rõ logic nghiệp vụ.

## 23. Câu hỏi tự kiểm tra

1. Query block là gì?
2. Query transformation giúp optimizer mở rộng không gian tìm kiếm như thế nào?
3. View merging khác predicate pushing ra sao?
4. Simple view merging thường áp dụng cho dạng view nào?
5. Complex view merging phải xử lý thêm các ranh giới semantics nào?
6. Vì sao DISTINCT có thể làm thay đổi cardinality khi bỏ qua?
7. Vì sao predicate trên grouping key có thể push trước GROUP BY nhưng predicate trên aggregate thì không?
8. Outer join khiến việc đẩy predicate phức tạp như thế nào?
9. MERGE và NO_MERGE hints dùng để làm gì?
10. QB_NAME hỗ trợ tuning query nhiều tầng ra sao?
11. Subquery unnesting là gì?
12. Semi join khác inner join thế nào khi inner có nhiều hàng match?
13. EXISTS và IN thường được biểu diễn bằng phép toán nào?
14. Anti join liên quan NOT EXISTS như thế nào?
15. Vì sao NOT IN bị ảnh hưởng bởi NULL?
16. Null-aware anti join có ý nghĩa gì trong execution plan?
17. Những cấu trúc nào có thể hạn chế subquery unnesting?
18. Scalar subquery khác join về semantics 0/1/nhiều hàng thế nào?
19. Join predicate pushdown làm view trở thành correlated như thế nào?
20. Khi nào JPPD có thể tốt và khi nào có thể làm tăng Starts?
21. Predicate pushing qua UNION ALL hoạt động ra sao?
22. Vì sao predicate trên analytic row_number không thể đẩy như filter thông thường?
23. CTE có mặc định materialize không?
24. NO_MERGE có đồng nghĩa materialization không?
25. DISPLAY_CURSOR khác EXPLAIN PLAN ở điểm nào?
26. E-Rows, A-Rows và Starts giúp chẩn đoán transformation thế nào?
27. Khi nào nên xem 10053 optimizer trace?
28. Vì sao không nên ép transformation bằng hidden parameters?

## 24. Mô hình ghi nhớ

```text
SQL CÓ NHIỀU QUERY BLOCK
        |
        v
  VIEW / INLINE VIEW / CTE
        |
        +-- VIEW MERGING
        |      Gộp query block để mở rộng join search
        |
        +-- PREDICATE PUSHING
        |      Đưa filter xuống nguồn dữ liệu
        |
        +-- JOIN PREDICATE PUSHING
               Đẩy join key vào view, có thể tạo correlated view
        |
        v
  SUBQUERY
        |
        +-- IN / EXISTS -> SEMI JOIN
        +-- NOT EXISTS -> ANTI JOIN
        +-- NOT IN -> NULL-aware semantics
        +-- UNNEST hoặc giữ subquery
        |
        v
  COST-BASED PLAN SEARCH
        |
        +-- Join order / access path / join method
        +-- Cardinality / statistics / bind values
        +-- Validity trước, cost sau
        |
        v
  KIỂM CHỨNG
        |
        +-- DISPLAY_CURSOR / ALLSTATS LAST
        +-- Predicate Information / Alias / Outline
        +-- A-Rows / E-Rows / Starts / Buffers
        +-- Hints chỉ dùng khi có bằng chứng
```

**Điểm cần nhớ:** view merging gộp query block, unnesting chuyển subquery thành join phù hợp, còn predicate pushing đưa điều kiện xuống gần nguồn dữ liệu. Optimizer chỉ được áp dụng transformation khi giữ nguyên semantics và cost model đánh giá có lợi. Khi tuning, đọc actual plan, kiểm tra NULL/cardinality/outer join và dùng hint như một phép thử có kiểm chứng, không phải giải pháp mặc định.
