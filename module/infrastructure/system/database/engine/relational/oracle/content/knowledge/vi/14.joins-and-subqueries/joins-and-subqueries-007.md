# Single-row, multi-row và correlated subquery

Trong Oracle Database, **subquery** là một câu truy vấn được đặt bên trong một câu SQL khác. Subquery có thể cung cấp một giá trị để so sánh, một danh sách giá trị, kiểm tra sự tồn tại của hàng, hoặc tạo một tập dữ liệu trung gian cho truy vấn bên ngoài. Tùy mục đích và số hàng mà ngữ cảnh bên ngoài cho phép, ta thường phân biệt **single-row subquery**, **multi-row subquery** và **correlated subquery**.

Ba khái niệm này không hoàn toàn cùng một trục phân loại:

- **Single-row subquery** mô tả subquery được dùng như một giá trị đơn: nó phải trả về tối đa một hàng và một cột trong ngữ cảnh scalar.
- **Multi-row subquery** mô tả subquery có thể trả về nhiều hàng, thường được dùng với IN, ANY, ALL hoặc EXISTS.
- **Correlated subquery** mô tả subquery tham chiếu cột của query block bên ngoài. Nó có thể là scalar hoặc multi-row; correlation là quan hệ phạm vi, không phải cam kết rằng Oracle sẽ thực thi subquery đúng một lần cho mỗi hàng.

Hiểu sự khác nhau giúp chọn đúng toán tử, tránh lỗi ORA-01427, xử lý NULL chính xác và đọc execution plan tốt hơn. Bài học cũng trình bày cách dùng subquery trong SELECT, WHERE, HAVING, FROM và DML, cùng ví dụ SQL có thể chạy trong schema thực hành.

## 1. Subquery và query block

Một subquery là một câu SELECT nằm trong câu SQL khác. Query block bên ngoài sử dụng kết quả của subquery theo một trong nhiều cách.

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
);
~~~

Trong ví dụ:
- SELECT bên trong là **subquery**.
- SELECT bên ngoài là **outer query**.
- Subquery tính mức lương trung bình.
- Outer query so sánh lương từng nhân viên với giá trị trung bình.

Subquery không phải lúc nào cũng nằm trong WHERE. Nó có thể xuất hiện ở nhiều vị trí:

| Vị trí | Vai trò | Ví dụ |
| --- | --- | --- |
| WHERE | So sánh một giá trị hoặc kiểm tra tập hàng | salary > (SELECT AVG(...)) |
| HAVING | So sánh kết quả nhóm với một kết quả truy vấn khác | AVG(salary) > (SELECT AVG(...)) |
| SELECT list | Lấy một giá trị cho mỗi hàng ngoài | (SELECT COUNT(*) ...) AS employee_count |
| FROM | Tạo tập dữ liệu trung gian, còn gọi là inline view | FROM (SELECT ...) d |
| DML | Tính giá trị UPDATE hoặc kiểm tra hàng cho DELETE/UPDATE | SET col = (SELECT ...) |

### 1.1. Phân biệt số cột và số hàng

Khi dùng subquery như một giá trị scalar, Oracle cần một cột và tối đa một hàng. Khi dùng với IN, ANY hoặc ALL, subquery thông thường cung cấp một cột nhưng có thể nhiều hàng. EXISTS chỉ kiểm tra có hàng hay không nên không cần lấy một giá trị cụ thể từ select list.

Hai câu hỏi phải được tách riêng:

1. **Subquery trả về bao nhiêu cột?** Một scalar expression chỉ có một giá trị; IN/ANY/ALL trong dạng cơ bản cũng so sánh một biểu thức với một cột từ subquery.
2. **Subquery trả về bao nhiêu hàng?** Scalar subquery chấp nhận 0 hoặc 1 hàng; multi-row operator cho phép nhiều hàng.

Một subquery có thể trả một cột và nhiều hàng; đó là trường hợp điển hình của IN. Một inline view trong FROM có thể trả nhiều cột và nhiều hàng vì nó được dùng như một nguồn dữ liệu.

## 2. Single-row subquery: subquery trả về một giá trị

Single-row subquery, trong ngữ cảnh so sánh scalar, trả về **một cột và không quá một hàng**. Kết quả có thể được so sánh bằng các toán tử thông thường:

- = 
- <> hoặc !=
- >
- >=
- <
- <=

Ví dụ:

~~~sql
SELECT employee_id,
       full_name,
       salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
);
~~~

Subquery trả một giá trị trung bình; mỗi hàng ngoài được so sánh với giá trị đó.

### 2.1. So sánh với một giá trị đơn

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary = (
    SELECT MAX(salary)
    FROM employees
);
~~~

Subquery MAX trả một hàng, một cột khi không có GROUP BY. Truy vấn ngoài lấy tất cả nhân viên có lương bằng mức cao nhất. Nếu nhiều nhân viên đồng lương cao nhất, subquery vẫn chỉ trả **một giá trị**; outer query có thể trả nhiều hàng.

Đây là điểm quan trọng: **single-row mô tả số hàng của subquery, không phải số hàng của toàn bộ câu SELECT bên ngoài.**

### 2.2. Subquery trả về 0 hàng

Một scalar subquery không tìm thấy hàng nào sẽ được xem như giá trị **NULL**:

~~~sql
SELECT (
    SELECT department_name
    FROM departments
    WHERE department_id = 999
) AS department_name
FROM dual;
~~~

Nếu không có phòng ban 999, kết quả scalar là NULL. Câu truy vấn ngoài vẫn có thể trả một hàng từ DUAL.

Trong biểu thức so sánh:

~~~sql
SELECT employee_id, full_name
FROM employees
WHERE salary = (
    SELECT salary
    FROM employees
    WHERE employee_id = 999
);
~~~

nếu employee 999 không tồn tại, scalar subquery là NULL; phép so sánh SALARY = NULL là UNKNOWN, nên không có hàng nào được chọn.

Đừng nhầm trường hợp này với subquery trả nhiều hàng. **Không có hàng** dẫn tới NULL trong ngữ cảnh scalar; **nhiều hơn một hàng** gây lỗi.

### 2.3. Subquery trả nhiều hơn một hàng: ORA-01427

~~~sql
-- Cố ý minh họa lỗi nếu phòng ban 20 có nhiều nhân viên.
SELECT employee_id, full_name
FROM employees
WHERE salary = (
    SELECT salary
    FROM employees
    WHERE department_id = 20
);
~~~

Nếu phòng ban 20 có hai nhân viên, subquery trả hai mức lương. Oracle không thể dùng hai giá trị đó như một scalar value cho toán tử bằng, và thường báo:

~~~text
ORA-01427: single-row subquery returns more than one row
~~~

Cách sửa phụ thuộc vào ý định:

- Nếu muốn khớp bất kỳ giá trị nào trong danh sách, dùng IN.
- Nếu muốn so sánh với giá trị lớn nhất/nhỏ nhất/trung bình, dùng hàm aggregate phù hợp.
- Nếu thực sự chỉ cần một hàng, định nghĩa thứ tự xác định rồi giới hạn hàng bằng row-limiting clause.
- Nếu subquery lẽ ra duy nhất, kiểm tra khóa/constraint và điều kiện WHERE.

Ví dụ dùng IN:

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary IN (
    SELECT salary
    FROM employees
    WHERE department_id = 20
);
~~~

### 2.4. Dùng aggregate để bảo đảm một giá trị

Các aggregate không có GROUP BY như COUNT, MAX, MIN, AVG, SUM trả về một hàng kết quả ngay cả khi tập đầu vào rỗng:

~~~sql
SELECT COUNT(*) AS employee_count,
       MAX(salary) AS max_salary,
       AVG(salary) AS avg_salary
FROM employees
WHERE department_id = 999;
~~~

Kết quả:
- COUNT(*) trả 0.
- MAX, MIN, AVG và SUM trả NULL nếu không có giá trị phù hợp để tổng hợp.

Aggregate có GROUP BY có thể trả nhiều hàng:

~~~sql
SELECT AVG(salary)
FROM employees
GROUP BY department_id;
~~~

Nếu có nhiều phòng ban, subquery này có thể trả nhiều giá trị. Không chỉ nhìn thấy hàm AVG/MAX/COUNT rồi mặc định subquery luôn scalar; cần xét GROUP BY và số nhóm được tạo.

### 2.5. Scalar subquery trong SELECT list

Một scalar subquery có thể tạo một cột tính cho mỗi hàng ngoài:

~~~sql
SELECT d.department_id,
       d.department_name,
       (
           SELECT COUNT(*)
           FROM employees e
           WHERE e.department_id = d.department_id
       ) AS employee_count
FROM departments d
ORDER BY d.department_id;
~~~

Subquery trong ví dụ này có tham chiếu d.department_id, nên đồng thời là **correlated subquery**. COUNT(*) bảo đảm trả một hàng; phòng ban không có nhân viên nhận số 0.

Nếu scalar subquery trả 0 hàng, cột kết quả sẽ là NULL. Nếu trả nhiều hơn một hàng, Oracle báo ORA-01427.

## 3. Multi-row subquery: làm việc với một tập giá trị

Multi-row subquery có thể trả nhiều hàng. Vì vậy, toán tử bên ngoài phải thể hiện rõ cách so sánh với **tập kết quả**, thay vì coi tập đó là một giá trị đơn.

Các toán tử thường dùng:

| Toán tử | Ý nghĩa |
| --- | --- |
| IN | Giá trị ngoài khớp ít nhất một giá trị trong tập |
| NOT IN | Giá trị ngoài không khớp bất kỳ giá trị nào trong tập, có lưu ý NULL |
| ANY / SOME | Phép so sánh đúng với ít nhất một hàng của tập |
| ALL | Phép so sánh đúng với mọi hàng của tập |
| EXISTS | Subquery có ít nhất một hàng |
| NOT EXISTS | Subquery không có hàng nào |

### 3.1. IN: khớp một trong các giá trị

~~~sql
SELECT employee_id, full_name, department_id
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE department_name IN ('Sales', 'Engineering')
);
~~~

Subquery có thể trả nhiều department_id. Outer query lấy nhân viên thuộc một trong các phòng ban đó.

IN phù hợp khi muốn diễn đạt membership: giá trị thuộc một tập. Có thể dùng danh sách literal:

~~~sql
WHERE department_id IN (10, 20, 30)
~~~

hoặc một subquery.

Với subquery trả tập rỗng, điều kiện IN không đúng cho hàng nào; không có giá trị nào để khớp.

### 3.2. NOT IN và bẫy NULL

~~~sql
SELECT department_id, department_name
FROM departments
WHERE department_id NOT IN (
    SELECT department_id
    FROM employees
);
~~~

Thoạt nhìn, truy vấn có vẻ tìm các phòng ban không có nhân viên. Nhưng nếu subquery trả về ít nhất một NULL, phép NOT IN có thể trở thành UNKNOWN đối với các giá trị không khớp. Trong thực tế, chỉ cần danh sách chứa NULL và không có giá trị khớp, điều kiện không trở thành TRUE, nên truy vấn có thể không trả kết quả mong đợi.

Nguyên nhân: NOT IN tương đương về ý nghĩa với phép so sánh khác tất cả giá trị trong tập. Ví dụ:

~~~sql
department_id NOT IN (10, 20, NULL)
~~~

được hiểu gần như:

~~~sql
department_id <> 10
AND department_id <> 20
AND department_id <> NULL
~~~

Phần department_id <> NULL là UNKNOWN. TRUE AND UNKNOWN là UNKNOWN, và WHERE không giữ hàng đó.

Nếu vẫn muốn dùng NOT IN, cần lọc NULL trong subquery khi phù hợp:

~~~sql
SELECT department_id, department_name
FROM departments
WHERE department_id NOT IN (
    SELECT department_id
    FROM employees
    WHERE department_id IS NOT NULL
);
~~~

Trong nhiều bài toán anti-match, NOT EXISTS rõ nghĩa và tránh bẫy NULL ở tập con:

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Không nên tuyên bố NOT EXISTS và NOT IN luôn tương đương trong mọi tình huống. Nếu giá trị bên ngoài có thể NULL hoặc nghiệp vụ có quy tắc so khớp NULL đặc biệt, cần viết điều kiện tường minh.

### 3.3. ANY và SOME: đúng với ít nhất một giá trị

ANY (còn có từ đồng nghĩa SOME) kết hợp với toán tử so sánh:

~~~sql
salary > ANY (
    SELECT salary
    FROM employees
    WHERE department_id = 10
)
~~~

Điều kiện có nghĩa: lương của nhân viên bên ngoài lớn hơn **ít nhất một** mức lương trong phòng ban 10.

Các ví dụ:

~~~sql
-- Lớn hơn ít nhất một mức lương của phòng ban 10.
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > ANY (
    SELECT salary
    FROM employees
    WHERE department_id = 10
);

-- Bằng ít nhất một giá trị: tương tự IN trong trường hợp scalar.
SELECT employee_id, full_name
FROM employees
WHERE department_id = ANY (
    SELECT department_id
    FROM departments
    WHERE department_id IN (10, 20)
);
~~~

Có thể nhớ:
- > ANY: lớn hơn giá trị nhỏ nhất theo nghĩa có ít nhất một phép so sánh đúng.
- < ANY: nhỏ hơn ít nhất một giá trị, tương đương nhỏ hơn giá trị lớn nhất khi tập không rỗng và không có ảnh hưởng NULL.
- = ANY: tương tự IN.
- <> ANY: khác ít nhất một giá trị; không đồng nghĩa NOT IN.

ANY trả FALSE khi subquery rỗng. Nếu không có phép so sánh nào TRUE nhưng có phép so sánh UNKNOWN do NULL, kết quả có thể UNKNOWN.

### 3.4. ALL: đúng với mọi giá trị

~~~sql
salary > ALL (
    SELECT salary
    FROM employees
    WHERE department_id = 10
)
~~~

Điều kiện có nghĩa lương ngoài phải lớn hơn **tất cả** mức lương trong phòng ban 10.

Các ví dụ:

~~~sql
-- Lương cao hơn mọi nhân viên phòng ban 10.
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > ALL (
    SELECT salary
    FROM employees
    WHERE department_id = 10
);

-- Lương không lớn hơn bất kỳ mức lương nào trong phòng ban 10.
SELECT employee_id, full_name, salary
FROM employees
WHERE salary <= ALL (
    SELECT salary
    FROM employees
    WHERE department_id = 10
);
~~~

Có thể nhớ:
- > ALL: lớn hơn giá trị lớn nhất khi tập có giá trị và không có NULL ảnh hưởng.
- < ALL: nhỏ hơn giá trị nhỏ nhất.
- = ALL: chỉ đúng khi bằng mọi giá trị; với tập có nhiều giá trị khác nhau thường không đúng.
- <> ALL: tương tự NOT IN, bao gồm các vấn đề NULL tương tự.

ALL trả TRUE với tập rỗng theo logic lượng từ phổ quát: không có phần tử nào vi phạm điều kiện “đúng với mọi phần tử”. Điều này đôi khi gây ngạc nhiên, nên hãy kiểm tra điều kiện lọc bên trong subquery để chắc tập có đúng những hàng nghiệp vụ mong muốn.

### 3.5. ANY và ALL có NULL

NULL có thể làm kết quả so sánh trở thành UNKNOWN. Ví dụ:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE salary > ANY (
    SELECT salary
    FROM employees
    WHERE department_id = 30
);
~~~

Nếu tập phòng ban 30 chứa một salary NULL:
- Chỉ cần một phép so sánh TRUE, điều kiện ANY là TRUE.
- Nếu không có phép so sánh TRUE nhưng có ít nhất một UNKNOWN, kết quả có thể UNKNOWN.
- Nếu tất cả phép so sánh đều FALSE, kết quả FALSE.

Với ALL:
- Chỉ cần một phép so sánh FALSE, kết quả ALL là FALSE.
- Nếu tất cả phép so sánh đều TRUE, kết quả TRUE.
- Nếu không có FALSE nhưng có UNKNOWN, kết quả UNKNOWN.

Khi nghiệp vụ muốn so sánh trên những giá trị thực có dữ liệu, có thể lọc NULL trong subquery:

~~~sql
WHERE salary > ALL (
    SELECT salary
    FROM employees
    WHERE department_id = 30
      AND salary IS NOT NULL
)
~~~

Chỉ thêm IS NOT NULL khi ý nghĩa nghiệp vụ là bỏ qua những mức lương chưa biết. Không lọc NULL máy móc nếu sự tồn tại của NULL phải khiến kết quả được xem là chưa xác định.

## 4. EXISTS và NOT EXISTS

EXISTS kiểm tra xem subquery có trả về **ít nhất một hàng** hay không. Nó không quan tâm giá trị cụ thể trong select list.

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Kết quả là các phòng ban có ít nhất một nhân viên.

Thông thường dùng SELECT 1 trong EXISTS để nhấn mạnh rằng chỉ cần sự tồn tại của hàng. SELECT * cũng có thể biểu diễn ý nghĩa tồn tại; Oracle không cần lấy toàn bộ cột để quyết định EXISTS là TRUE.

### 4.1. EXISTS không phải IN

Hai cách có thể diễn đạt những bài toán tương tự:

~~~sql
-- Dùng IN.
SELECT d.department_id, d.department_name
FROM departments d
WHERE d.department_id IN (
    SELECT e.department_id
    FROM employees e
);

-- Dùng EXISTS.
SELECT d.department_id, d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Tuy nhiên, EXISTS diễn đạt trực tiếp quan hệ giữa hàng ngoài và sự tồn tại của hàng con. IN diễn đạt membership trong tập giá trị. Với NULL, duplicate và cấu trúc dữ liệu cụ thể, không nên thay thế qua lại mà không xem ngữ nghĩa.

### 4.2. NOT EXISTS: tìm hàng không có đối tác

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Truy vấn tìm phòng ban không có nhân viên. Đây là dạng anti-existence phổ biến, thường an toàn hơn NOT IN khi cột phía trong có thể NULL.

### 4.3. EXISTS có thể trả lời câu hỏi mà không cần đếm

Nếu chỉ muốn biết phòng ban có nhân viên hay không, không cần:

~~~sql
WHERE (
    SELECT COUNT(*)
    FROM employees e
    WHERE e.department_id = d.department_id
) > 0
~~~

Có thể viết rõ hơn:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
)
~~~

COUNT(*) phải biểu diễn số lượng; EXISTS chỉ cần biết có hàng. Optimizer có thể biến đổi hai câu theo những cách khác nhau, nhưng EXISTS thể hiện đúng mục tiêu và không yêu cầu ứng dụng xử lý một con số đếm không cần thiết.

### 4.4. NOT EXISTS và NULL ở outer row

~~~sql
SELECT e.employee_id, e.full_name
FROM employees e
WHERE NOT EXISTS (
    SELECT 1
    FROM departments d
    WHERE d.department_id = e.department_id
);
~~~

Nếu EMPLOYEE.DEPARTMENT_ID là NULL, phép so sánh d.department_id = e.department_id không TRUE cho hàng nào, nên NOT EXISTS có thể TRUE và nhân viên đó được trả về.

Đây có thể là kết quả đúng nếu mục tiêu là “không tìm thấy phòng ban khớp”. Nhưng nếu nghiệp vụ muốn chỉ tìm nhân viên có mã phòng không NULL mà phòng ban không tồn tại, hãy thêm:

~~~sql
WHERE e.department_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM departments d
      WHERE d.department_id = e.department_id
  )
~~~

Khi có khóa ngoại được ENABLE và VALIDATE, dữ liệu tham chiếu không hợp lệ thường không tồn tại, nhưng NULL vẫn có thể được phép nếu cột không NOT NULL.

## 5. Correlated subquery: subquery tham chiếu query block bên ngoài

Một correlated subquery sử dụng cột từ query block bên ngoài. Alias ngoài tạo phạm vi để subquery tham chiếu.

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.salary
FROM employees e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees e2
    WHERE e2.department_id = e.department_id
);
~~~

Subquery tham chiếu e.department_id của hàng ngoài. Với mỗi nhân viên, logic so sánh dùng mức lương trung bình của phòng ban tương ứng.

### 5.1. Correlated không đồng nghĩa luôn thực thi vật lý từng lần cho mỗi hàng

Về **ngữ nghĩa**, kết quả của subquery phụ thuộc vào giá trị của hàng ngoài. Ta có thể tư duy rằng subquery được áp dụng cho từng hàng ngoài để hiểu logic.

Nhưng không nên kết luận Oracle bắt buộc chạy lại subquery vật lý đúng một lần cho mỗi hàng. Optimizer có thể biến đổi correlated subquery thành:
- Semi-join hoặc anti-join.
- Join với inline view đã tổng hợp.
- Một dạng access path khác phù hợp.
- Cơ chế thực thi hoặc caching thích hợp cho scalar subquery.

Vì vậy, correlation là đặc điểm **phụ thuộc phạm vi dữ liệu**, không phải lời mô tả chính xác về số lần truy cập vật lý. Muốn biết Oracle thực thi thế nào, xem execution plan và runtime statistics.

### 5.2. Correlated scalar subquery trong SELECT

~~~sql
SELECT d.department_id,
       d.department_name,
       (
           SELECT COUNT(*)
           FROM employees e
           WHERE e.department_id = d.department_id
       ) AS employee_count
FROM departments d
ORDER BY d.department_id;
~~~

Mỗi hàng phòng ban có một số đếm tương ứng. Phòng ban không có nhân viên trả 0 vì COUNT(*) trên tập rỗng trả 0.

Nếu thay COUNT bằng MAX:

~~~sql
SELECT d.department_id,
       (
           SELECT MAX(e.salary)
           FROM employees e
           WHERE e.department_id = d.department_id
       ) AS max_salary
FROM departments d;
~~~

phòng ban không có nhân viên trả NULL, vì MAX trên tập rỗng trả NULL.

### 5.3. Correlated subquery với EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
      AND e.salary >= 20000000
);
~~~

Truy vấn chọn phòng ban có ít nhất một nhân viên lương từ 20 triệu trở lên. Điều kiện e.department_id = d.department_id tạo correlation; điều kiện lương giới hạn hàng được xem là tồn tại.

### 5.4. Correlated subquery với NOT EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
      AND e.salary >= 20000000
);
~~~

Truy vấn chọn phòng ban không có nhân viên nào lương từ 20 triệu trở lên. Nó không nhất thiết chỉ chọn phòng ban không có nhân viên; phòng ban có nhân viên nhưng tất cả lương thấp hơn hoặc NULL cũng thỏa điều kiện.

Cần viết điều kiện theo đúng câu hỏi nghiệp vụ:
- Không có nhân viên khác với
- Không có nhân viên đạt mức lương và khác với
- Tất cả nhân viên đều có lương dưới ngưỡng.

### 5.5. Correlated subquery trong HAVING

~~~sql
SELECT e.department_id,
       AVG(e.salary) AS department_avg
FROM employees e
GROUP BY e.department_id
HAVING AVG(e.salary) > (
    SELECT AVG(salary)
    FROM employees
);
~~~

Subquery không tham chiếu cột nhóm bên ngoài nên đây là subquery không correlated, nhưng được dùng trong HAVING. Nếu cần một so sánh phụ thuộc vào từng nhóm, có thể tham chiếu khóa nhóm ngoài trong subquery theo cú pháp phù hợp.

## 6. Subquery trong FROM: inline view

Subquery đặt trong FROM được gọi là **inline view**. Nó tạo một nguồn dữ liệu trung gian có thể được query block ngoài lọc, join hoặc sắp xếp.

~~~sql
SELECT d.department_id,
       d.avg_salary
FROM (
    SELECT department_id,
           AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
) d
WHERE d.avg_salary > 20000000
ORDER BY d.department_id;
~~~

Inline view có thể trả nhiều hàng và nhiều cột; nó không bị ràng buộc phải là scalar. Ví dụ này tổng hợp lương theo phòng ban trước, rồi lọc những phòng có mức trung bình trên 20 triệu.

### 6.1. Inline view không mặc nhiên là correlated

~~~sql
SELECT d.department_id, x.avg_salary
FROM departments d
JOIN (
    SELECT department_id,
           AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
) x
  ON x.department_id = d.department_id;
~~~

Inline view X không tham chiếu D. Đây là nguồn dữ liệu độc lập được join với DEPARTMENTS.

Oracle có các cơ chế như view merging và query transformation; không nên cho rằng inline view luôn được vật hóa thành bảng tạm. Cách thực thi tùy optimizer và cấu trúc truy vấn.

## 7. So sánh single-row và multi-row operators

| Nhu cầu | Cách viết thường dùng | Kỳ vọng subquery |
| --- | --- | --- |
| Bằng đúng một giá trị | = (subquery) | Một cột, tối đa một hàng |
| Lớn hơn một giá trị đơn | > (subquery) | Một cột, tối đa một hàng |
| Khớp một trong nhiều giá trị | IN (subquery) | Một cột, có thể nhiều hàng |
| Lớn hơn ít nhất một giá trị | > ANY (subquery) | Một cột, có thể nhiều hàng |
| Lớn hơn mọi giá trị | > ALL (subquery) | Một cột, có thể nhiều hàng |
| Có ít nhất một hàng phù hợp | EXISTS (subquery) | Có thể nhiều hàng; select list không quyết định giá trị |
| Không có hàng phù hợp | NOT EXISTS (subquery) | Kiểm tra tập rỗng |

Không cố sửa ORA-01427 bằng cách thêm MAX một cách máy móc. Nếu nghiệp vụ là “thuộc một trong nhiều phòng ban”, dùng IN. Nếu là “cao hơn mọi người trong phòng ban”, dùng > ALL. Nếu là “có ít nhất một nhân viên đạt điều kiện”, dùng EXISTS.

## 8. NULL trong IN, NOT IN, ANY, ALL và EXISTS

NULL là nguyên nhân của nhiều lỗi logic tinh vi khi làm việc với multi-row subquery.

### 8.1. IN có NULL trong tập

Giả sử tập con là (10, 20, NULL):

| Biểu thức | Kết quả |
| --- | --- |
| 10 IN (10,20,NULL) | TRUE |
| 30 IN (10,20,NULL) | UNKNOWN |
| NULL IN (10,20,NULL) | UNKNOWN |

Nếu có một giá trị khớp, IN là TRUE. Nếu không có giá trị khớp nhưng có NULL trong tập, kết quả có thể UNKNOWN.

### 8.2. NOT IN có NULL trong tập

| Biểu thức | Kết quả |
| --- | --- |
| 10 NOT IN (10,20,NULL) | FALSE |
| 30 NOT IN (10,20,NULL) | UNKNOWN |
| NULL NOT IN (10,20) | UNKNOWN |

Vì WHERE chỉ chọn TRUE, trường hợp 30 không được trả về dù không bằng 10 hay 20. Đây là lý do NOT IN thường gây bất ngờ.

### 8.3. EXISTS không bị ảnh hưởng bởi giá trị select list là NULL

~~~sql
SELECT d.department_id
FROM departments d
WHERE EXISTS (
    SELECT NULL
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

EXISTS chỉ quan tâm subquery có hàng hay không. Một hàng có select list NULL vẫn là một hàng, nên EXISTS là TRUE. Thực tế nên dùng SELECT 1 để câu lệnh thể hiện rõ mục tiêu.

### 8.4. NOT EXISTS và NULL ở outer row

NOT EXISTS kiểm tra không có hàng nào thỏa toàn bộ điều kiện WHERE trong subquery. Nếu phép so sánh giữa hai cột gặp NULL và trở thành UNKNOWN, hàng đó không thỏa WHERE; điều này có thể khiến NOT EXISTS trả TRUE.

Nếu muốn coi hai NULL là khớp nhau, cần viết quy tắc null-safe rõ ràng:

~~~sql
WHERE e.department_id = d.department_id
   OR (e.department_id IS NULL AND d.department_id IS NULL)
~~~

Chỉ thêm nhánh này khi nghiệp vụ thật sự định nghĩa NULL ở hai phía là cùng một nhóm. Với khóa ngoại, NULL thường có nghĩa chưa gán quan hệ, không nhất thiết là một khóa chung để join.

## 9. Subquery tương quan với JOIN: chọn cách biểu diễn phù hợp

Nhiều subquery có thể được viết lại bằng JOIN, nhưng hai cách không phải lúc nào cũng trả cùng số hàng.

### 9.1. EXISTS và semi-join

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Một cách dùng JOIN:

~~~sql
SELECT DISTINCT d.department_id, d.department_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id;
~~~

Nếu một phòng ban có nhiều nhân viên, JOIN tạo nhiều hàng phòng ban rồi DISTINCT loại trùng. EXISTS diễn đạt trực tiếp “giữ phòng ban nếu có ít nhất một nhân viên”, không làm nhân bản hàng ngoài do nhiều hàng con.

Optimizer có thể biến EXISTS thành **semi-join**. Tùy plan có thể thấy HASH JOIN SEMI hoặc NESTED LOOPS SEMI.

### 9.2. NOT EXISTS và anti-join

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Oracle có thể thực thi logic này bằng **anti-join**, ví dụ HASH JOIN ANTI hoặc NESTED LOOPS ANTI, tùy dữ liệu và plan.

### 9.3. Scalar aggregate và JOIN với inline view

Subquery:

~~~sql
SELECT d.department_id,
       (
           SELECT AVG(e.salary)
           FROM employees e
           WHERE e.department_id = d.department_id
       ) AS avg_salary
FROM departments d;
~~~

Có thể biểu diễn bằng inline view:

~~~sql
SELECT d.department_id,
       x.avg_salary
FROM departments d
LEFT JOIN (
    SELECT department_id,
           AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
) x
  ON x.department_id = d.department_id;
~~~

LEFT JOIN giữ phòng ban không có nhân viên; AVG khi không có nhóm tương ứng trả NULL ở phía X. Nếu dùng INNER JOIN, các phòng ban không có nhân viên sẽ bị loại, làm thay đổi kết quả.

### 9.4. Không rewrite máy móc

Trước khi đổi subquery thành JOIN hoặc ngược lại, kiểm tra:
- Một hàng ngoài có thể khớp nhiều hàng con không?
- Có cần giữ một hàng ngoài duy nhất không?
- NULL có thay đổi kết quả không?
- Subquery aggregate có trả NULL hay 0?
- Điều kiện correlation có đầy đủ khóa không?
- Có điều kiện lọc nào cần ở ON, WHERE hoặc HAVING?
- Query có DISTINCT hoặc row limiting không?

Mục tiêu là giữ nguyên ngữ nghĩa trước khi so sánh hiệu năng.

## 10. Subquery trong UPDATE và DELETE

Subquery không chỉ phục vụ SELECT. Nó có thể tính giá trị cập nhật hoặc xác định hàng cần thay đổi.

### 10.1. UPDATE với scalar subquery

Giả sử bảng DEPARTMENTS có cột AVG_SALARY:

~~~sql
UPDATE departments d
SET avg_salary = (
    SELECT AVG(e.salary)
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Đây là correlated scalar subquery. Với phòng ban không có nhân viên, AVG trả NULL và AVG_SALARY được đặt NULL. Nếu nghiệp vụ muốn 0, có thể dùng NVL quanh subquery, nhưng phải xác định NULL thật sự có nghĩa gì.

### 10.2. UPDATE có điều kiện EXISTS

~~~sql
UPDATE departments d
SET department_name = department_name || ' - ACTIVE'
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Chỉ cập nhật phòng ban có nhân viên. Trong thực tế cần bảo đảm không nối hậu tố lặp lại mỗi lần chạy; ví dụ tập trung minh họa correlation.

### 10.3. DELETE với NOT EXISTS

~~~sql
DELETE FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Câu lệnh xóa phòng ban không có nhân viên. Chỉ chạy trên dữ liệu thực hành và cần xét khóa ngoại, quyền, trigger và chính sách nghiệp vụ trước khi dùng trong hệ thống thật. Ví dụ này cho thấy NOT EXISTS có thể dùng trong DML; nó không phải chỉ dành cho SELECT.

## 11. Bộ dữ liệu mẫu để thực hành

Các ví dụ sau dùng hai bảng sandbox. Chạy trong schema riêng có quyền CREATE TABLE, INSERT và SELECT. Dữ liệu có:
- Phòng ban không có nhân viên.
- Nhân viên có department_id NULL.
- Nhân viên có salary NULL.
- Hai nhân viên cùng mức lương cao nhất để kiểm tra subquery scalar và kết quả outer query.

### 11.1. Tạo bảng phòng ban

~~~sql
CREATE TABLE departments_subq (
    department_id   NUMBER(4)
        CONSTRAINT pk_departments_subq PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);
~~~

### 11.2. Tạo bảng nhân viên

~~~sql
CREATE TABLE employees_subq (
    employee_id   NUMBER(6)
        CONSTRAINT pk_employees_subq PRIMARY KEY,
    full_name     VARCHAR2(100 CHAR) NOT NULL,
    department_id NUMBER(4),
    salary        NUMBER(12,2),
    CONSTRAINT fk_emp_dept_subq
        FOREIGN KEY (department_id)
        REFERENCES departments_subq (department_id)
);
~~~

Khóa ngoại cho phép DEPARTMENT_ID NULL vì cột không khai báo NOT NULL. Hàng nhân viên có mã phòng NULL không vi phạm khóa ngoại.

### 11.3. Nạp phòng ban

~~~sql
INSERT INTO departments_subq VALUES (10, 'Sales');
INSERT INTO departments_subq VALUES (20, 'Engineering');
INSERT INTO departments_subq VALUES (30, 'Human Resources');
INSERT INTO departments_subq VALUES (40, 'Research');

COMMIT;
~~~

Phòng ban 40 được cố ý để không có nhân viên.

### 11.4. Nạp nhân viên

~~~sql
INSERT INTO employees_subq VALUES
    (101, 'An', 10, 20000000);

INSERT INTO employees_subq VALUES
    (102, 'Binh', 10, 15000000);

INSERT INTO employees_subq VALUES
    (103, 'Chi', 20, 30000000);

INSERT INTO employees_subq VALUES
    (104, 'Dung', 20, 30000000);

INSERT INTO employees_subq VALUES
    (105, 'Giang', 30, 12000000);

INSERT INTO employees_subq VALUES
    (106, 'Hanh', 30, NULL);

INSERT INTO employees_subq VALUES
    (107, 'Khanh', NULL, 18000000);

COMMIT;
~~~

Tổng cộng 7 nhân viên. Phòng 10 có hai người; phòng 20 có hai người; phòng 30 có hai người, một người chưa có lương; phòng 40 không có người. Nhân viên 107 chưa được gán phòng.

## 12. Thực hành single-row subquery

### 12.1. Tìm nhân viên có lương cao nhất

~~~sql
SELECT employee_id, full_name, salary
FROM employees_subq
WHERE salary = (
    SELECT MAX(salary)
    FROM employees_subq
)
ORDER BY employee_id;
~~~

Subquery trả một giá trị là 30.000.000. Outer query trả hai hàng: Chi và Dung. Đây là minh họa single-row subquery có thể dẫn tới nhiều hàng kết quả ngoài.

### 12.2. Tìm nhân viên có lương cao hơn trung bình toàn công ty

~~~sql
SELECT employee_id, full_name, salary
FROM employees_subq
WHERE salary > (
    SELECT AVG(salary)
    FROM employees_subq
)
ORDER BY salary DESC, employee_id;
~~~

AVG bỏ qua SALARY NULL. Trung bình trên sáu mức lương có giá trị là:

\[
\frac{20 + 15 + 30 + 30 + 12 + 18}{6}
= 20.833333\ldots \text{ triệu}
\]

Hai nhân viên Chi và Dung có lương 30 triệu nên được chọn.

### 12.3. Scalar subquery trả NULL khi không tìm thấy

~~~sql
SELECT (
    SELECT department_name
    FROM departments_subq
    WHERE department_id = 999
) AS missing_department
FROM dual;
~~~

Kết quả một hàng với MISSING_DEPARTMENT = NULL. Đây không phải lỗi ORA-01427.

### 12.4. Cố ý gây ORA-01427

~~~sql
-- Subquery có thể trả hai hàng của phòng ban 20.
SELECT employee_id, full_name
FROM employees_subq
WHERE salary = (
    SELECT salary
    FROM employees_subq
    WHERE department_id = 20
);
~~~

Câu truy vấn có thể lỗi vì subquery trả lương của cả Chi và Dung. Nếu muốn lấy nhân viên có lương thuộc tập lương của phòng 20, thay dấu bằng scalar bằng IN.

### 12.5. Aggregate có và không có GROUP BY

~~~sql
-- Một hàng dù không có nhân viên phòng 40.
SELECT COUNT(*) AS employee_count,
       AVG(salary) AS avg_salary
FROM employees_subq
WHERE department_id = 40;
~~~

Kết quả COUNT(*) = 0 và AVG(SALARY) = NULL.

~~~sql
-- Có thể nhiều hàng, mỗi phòng ban là một nhóm.
SELECT department_id,
       AVG(salary) AS avg_salary
FROM employees_subq
GROUP BY department_id
ORDER BY department_id NULLS LAST;
~~~

Câu thứ hai trả nhiều nhóm, bao gồm một nhóm DEPARTMENT_ID NULL. Không dùng nó như scalar subquery nếu không có điều kiện giới hạn hoặc aggregate bên ngoài.

## 13. Thực hành multi-row subquery

### 13.1. IN: nhân viên thuộc Sales hoặc Engineering

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id
FROM employees_subq e
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments_subq d
    WHERE d.department_name IN ('Sales', 'Engineering')
)
ORDER BY e.department_id, e.employee_id;
~~~

Kết quả gồm nhân viên 101, 102, 103 và 104.

### 13.2. ANY: lương cao hơn ít nhất một nhân viên Sales

~~~sql
SELECT employee_id, full_name, salary
FROM employees_subq
WHERE salary > ANY (
    SELECT salary
    FROM employees_subq
    WHERE department_id = 10
)
ORDER BY salary DESC, employee_id;
~~~

Sales có mức lương 20 triệu và 15 triệu. Một nhân viên chỉ cần lương cao hơn ít nhất một trong hai mức để thỏa điều kiện; do đó lương 18 triệu cũng thỏa vì lớn hơn 15 triệu. Hai nhân viên Engineering lương 30 triệu cũng thỏa.

### 13.3. ALL: lương cao hơn mọi nhân viên Sales

~~~sql
SELECT employee_id, full_name, salary
FROM employees_subq
WHERE salary > ALL (
    SELECT salary
    FROM employees_subq
    WHERE department_id = 10
)
ORDER BY salary DESC, employee_id;
~~~

Muốn lớn hơn tất cả lương Sales, giá trị phải lớn hơn 20 triệu. Chi và Dung lương 30 triệu thỏa.

### 13.4. EXISTS: phòng ban có nhân viên

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
~~~

Kết quả là phòng ban 10, 20 và 30. Phòng ban 40 không xuất hiện.

### 13.5. NOT EXISTS: phòng ban không có nhân viên

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
~~~

Kết quả là phòng ban 40.

### 13.6. Minh họa bẫy NOT IN

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE d.department_id NOT IN (
    SELECT e.department_id
    FROM employees_subq e
);
~~~

Subquery trả 10, 20, 30 và NULL (từ nhân viên 107). Vì có NULL, truy vấn có thể không trả phòng ban 40 như mong muốn.

Sửa bằng lọc NULL:

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE d.department_id NOT IN (
    SELECT e.department_id
    FROM employees_subq e
    WHERE e.department_id IS NOT NULL
)
ORDER BY d.department_id;
~~~

Hoặc dùng NOT EXISTS như phần trước. Với anti-match theo quan hệ giữa hai bảng, NOT EXISTS thường thể hiện ý định rõ ràng hơn.

## 14. Thực hành correlated subquery

### 14.1. Nhân viên có lương cao hơn trung bình phòng ban của chính họ

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       e.salary
FROM employees_subq e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees_subq e2
    WHERE e2.department_id = e.department_id
)
ORDER BY e.department_id, e.employee_id;
~~~

Subquery dùng alias E2 để đọc cùng bảng, nhưng tham chiếu e.department_id từ hàng ngoài. Kết quả theo dữ liệu mẫu:
- An: 20 triệu, cao hơn trung bình phòng 10 là 17,5 triệu.
- Nhân viên thuộc phòng 20 có lương bằng trung bình 30 triệu nên không cao hơn.
- Giang bằng trung bình phòng 30 là 12 triệu.
- Hanh có lương NULL nên phép so sánh UNKNOWN.
- Khanh có department_id NULL; điều kiện bằng NULL không TRUE nên subquery aggregate không có hàng, AVG trả NULL và hàng không được chọn.

### 14.2. Đếm nhân viên cho mỗi phòng ban

~~~sql
SELECT d.department_id,
       d.department_name,
       (
           SELECT COUNT(*)
           FROM employees_subq e
           WHERE e.department_id = d.department_id
       ) AS employee_count
FROM departments_subq d
ORDER BY d.department_id;
~~~

Kết quả:
- Sales: 2.
- Engineering: 2.
- Human Resources: 2.
- Research: 0.

Đây là correlated scalar subquery trong SELECT list. COUNT(*) trả một giá trị ngay cả khi không có hàng khớp.

### 14.3. Tìm phòng ban có ít nhất một nhân viên lương từ 20 triệu

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
      AND e.salary >= 20000000
)
ORDER BY d.department_id;
~~~

Kết quả là Sales và Engineering. Human Resources không có nhân viên đạt ngưỡng.

### 14.4. Tìm phòng ban không có nhân viên đạt ngưỡng

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
      AND e.salary >= 20000000
)
ORDER BY d.department_id;
~~~

Kết quả gồm Human Resources và Research. Research không có nhân viên; Human Resources có nhân viên nhưng không ai đạt ngưỡng. Điều kiện EXISTS đang hỏi “có người đạt ngưỡng hay không”, không phải “có nhân viên hay không”.

### 14.5. Correlated subquery so với inline view aggregate

Có thể viết lại truy vấn đếm phòng ban bằng LEFT JOIN:

~~~sql
SELECT d.department_id,
       d.department_name,
       COUNT(e.employee_id) AS employee_count
FROM departments_subq d
LEFT JOIN employees_subq e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
~~~

Hoặc join với inline view đã tổng hợp:

~~~sql
SELECT d.department_id,
       d.department_name,
       NVL(x.employee_count, 0) AS employee_count
FROM departments_subq d
LEFT JOIN (
    SELECT department_id,
           COUNT(*) AS employee_count
    FROM employees_subq
    GROUP BY department_id
) x
  ON x.department_id = d.department_id
ORDER BY d.department_id;
~~~

Cả hai cách có thể diễn đạt cùng kết quả cho dữ liệu mẫu, nhưng phải cẩn thận:
- COUNT(e.employee_id) trong LEFT JOIN đếm cột không NULL, không dùng COUNT(*) nếu muốn phòng không nhân viên trả 0.
- LEFT JOIN giữ phòng ban không có hàng con; INNER JOIN sẽ loại chúng.
- Correlated scalar subquery có thể được optimizer biến đổi; không mặc định nó chậm hơn JOIN.

## 15. Subquery lồng nhau

Một subquery có thể chứa subquery khác. Ví dụ tìm nhân viên thuộc phòng có mức lương trung bình cao hơn trung bình toàn công ty:

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       e.salary
FROM employees_subq e
WHERE e.department_id IN (
    SELECT x.department_id
    FROM employees_subq x
    GROUP BY x.department_id
    HAVING AVG(x.salary) > (
        SELECT AVG(salary)
        FROM employees_subq
    )
)
ORDER BY e.department_id, e.employee_id;
~~~

Trong ví dụ:
- Subquery trong cùng tính trung bình toàn công ty, là non-correlated.
- Subquery giữa nhóm nhân viên theo phòng và dùng HAVING so với trung bình toàn công ty.
- Query ngoài chọn nhân viên thuộc các phòng có trung bình cao hơn toàn công ty.

Khi lồng nhiều cấp, dùng alias rõ ràng và tránh tái sử dụng tên alias gây nhầm phạm vi. Mỗi query block nên có một mục tiêu cụ thể: lọc nhóm, tính aggregate hoặc chọn hàng ngoài.

### 15.1. Không dùng alias ngoài một cách mơ hồ

~~~sql
SELECT e.employee_id
FROM employees_subq e
WHERE EXISTS (
    SELECT 1
    FROM employees_subq e2
    WHERE e2.department_id = e.department_id
      AND e2.salary > e.salary
);
~~~

Alias E và E2 làm rõ bảng ngoài và bảng bên trong dù cùng nguồn vật lý. Nếu không phân biệt rõ, câu SQL dễ sai hoặc khó đọc.

## 16. Lỗi thường gặp và cách xử lý

| Lỗi/tình huống | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| ORA-01427 | Scalar subquery trả nhiều hơn một hàng | Dùng IN/ANY/ALL/EXISTS, aggregate hoặc giới hạn hàng có thứ tự xác định |
| Subquery trả NULL và outer query không có hàng | Scalar subquery không tìm thấy dữ liệu; phép so sánh với NULL là UNKNOWN | Kiểm tra điều kiện, xử lý NULL theo nghiệp vụ |
| NOT IN trả 0 hàng ngoài mong đợi | Tập con chứa NULL | Dùng NOT EXISTS hoặc lọc NULL trong subquery |
| Correlated subquery trả kết quả thiếu | Điều kiện correlation không đầy đủ hoặc dùng nhầm alias | Kiểm tra khóa nối và phạm vi alias |
| Phòng ban không có nhân viên trả NULL thay vì 0 | Dùng COUNT/aggregate khác hoặc scalar subquery không phù hợp | COUNT(*) trả 0; dùng NVL nếu aggregate có thể NULL |
| EXISTS bị viết thành COUNT(*) > 0 | Tính số lượng khi chỉ cần biết có hàng | Dùng EXISTS/NOT EXISTS |
| Thay subquery bằng JOIN làm nhân bản hàng | Một hàng ngoài khớp nhiều hàng con | Dùng EXISTS, DISTINCT có chủ đích hoặc aggregate trước khi JOIN |
| ANY/ALL có kết quả UNKNOWN | Giá trị so sánh hoặc tập con chứa NULL | Xác định chính sách NULL, lọc hoặc giữ UNKNOWN theo nghiệp vụ |
| Subquery aggregate có GROUP BY trả nhiều hàng | Có nhiều nhóm | Thêm điều kiện nhóm, dùng IN/ANY/ALL hoặc tổng hợp cấp ngoài |
| Correlated query chậm | Tập ngoài lớn, thiếu index hoặc plan chưa phù hợp | Xem plan/runtime, kiểm tra khả năng unnest và access path |

### 16.1. ORA-01427 không phải lúc nào cũng nên sửa bằng MAX

Nếu một scalar subquery bất ngờ trả nhiều hàng, dùng MAX để tránh lỗi có thể che mất vấn đề dữ liệu. Chỉ dùng MAX khi yêu cầu nghiệp vụ thật sự là “giá trị lớn nhất”. Nếu yêu cầu là “tất cả giá trị khớp”, dùng IN; nếu kỳ vọng khóa duy nhất, kiểm tra constraint và điều kiện truy vấn.

### 16.2. Subquery không có kết quả và subquery nhiều kết quả

| Ngữ cảnh | 0 hàng | Nhiều hàng |
| --- | --- | --- |
| Scalar subquery | NULL | ORA-01427 |
| IN | Không có giá trị khớp; thường FALSE nếu tập rỗng | Kiểm tra membership |
| ANY | FALSE với tập rỗng | TRUE nếu có ít nhất một phép so sánh TRUE |
| ALL | TRUE với tập rỗng | TRUE nếu mọi phép so sánh TRUE |
| EXISTS | FALSE | TRUE |
| NOT EXISTS | TRUE | FALSE |

Bảng trên mô tả logic cơ bản khi không có ảnh hưởng UNKNOWN do NULL. Với IN/ANY/ALL, NULL trong tập hoặc biểu thức ngoài có thể khiến kết quả UNKNOWN.

## 17. Hiệu năng và execution plan

Không có quy tắc rằng subquery luôn chậm hơn JOIN. Oracle optimizer có thể thực hiện các biến đổi để chọn plan phù hợp với thống kê và cấu trúc dữ liệu.

### 17.1. Subquery unnesting

Oracle có thể chuyển một số subquery trong WHERE thành join tương đương. Quá trình này thường được gọi là **subquery unnesting**. Ví dụ EXISTS có thể trở thành semi-join, NOT EXISTS có thể trở thành anti-join.

Việc unnest có được áp dụng hay không phụ thuộc:
- Cấu trúc subquery và các hàm/điều kiện bên trong.
- Aggregation, DISTINCT, GROUP BY hoặc row limiting.
- NULL semantics và ràng buộc dữ liệu.
- Phiên bản, optimizer settings và cost estimate.

Không cần rewrite mọi subquery thành JOIN trước khi đo. Viết câu SQL đúng ý nghĩa trước, sau đó xem plan.

### 17.2. Correlated subquery và index

Với điều kiện:

~~~sql
WHERE e.department_id = d.department_id
~~~

index trên EMPLOYEES_SUBQ(DEPARTMENT_ID) có thể hữu ích cho một số access path, đặc biệt khi outer query trả ít phòng ban. Nếu subquery còn lọc theo salary, index ghép có thể được xem xét theo workload, chẳng hạn (DEPARTMENT_ID, SALARY), nhưng không có index nào luôn tốt nhất.

Cần xét:
- Số phòng ban/hàng ngoài.
- Số nhân viên trong mỗi phòng.
- Selectivity của điều kiện.
- Tần suất INSERT/UPDATE/DELETE.
- Các truy vấn khác dùng cùng index.
- Chi phí đọc bảng so với đọc index.

### 17.3. Xem plan với DBMS_XPLAN

Trong môi trường thực hành:

~~~sql
EXPLAIN PLAN FOR
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Có thể thấy các operation như TABLE ACCESS, INDEX RANGE SCAN, HASH JOIN SEMI hoặc NESTED LOOPS SEMI tùy plan. Với correlated subquery scalar, có thể thấy FILTER hoặc dạng join sau biến đổi. Tên operation và hình thức plan phụ thuộc phiên bản, dữ liệu và optimizer.

EXPLAIN PLAN là plan được ước lượng; nó không chứng minh thời gian chạy thực tế. Với hệ thống thật, xem cursor plan và runtime statistics khi được cấp quyền, ví dụ DBMS_XPLAN.DISPLAY_CURSOR với tùy chọn phù hợp.

### 17.4. Đừng chỉ nhìn số lần xuất hiện trong SQL

Một subquery viết trong SELECT list không có nghĩa chắc chắn nó chạy riêng rẽ cho từng hàng. Optimizer có thể áp dụng scalar subquery caching hoặc biến đổi thích hợp. Ngược lại, một JOIN cũng có thể tốn kém nếu làm tăng cardinality hoặc cần sort/hash lớn.

Đo bằng dữ liệu đại diện, xem logical reads, elapsed time, rows, buffer gets và plan; không kết luận chỉ từ độ dài câu SQL.

## 18. Java JDBC: dùng subquery với bind variable

Subquery được viết trong SQL text, còn giá trị đầu vào nên truyền bằng bind variable để tránh SQL injection và tránh ghép chuỗi.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class EmployeeSearchRepository {
    private final DataSource dataSource;

    public EmployeeSearchRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printEmployeesAboveDepartmentAverage(long departmentId)
            throws SQLException {

        String sql = """
            SELECT e.employee_id,
                   e.full_name,
                   e.salary
            FROM employees_subq e
            WHERE e.department_id = ?
              AND e.salary > (
                  SELECT AVG(e2.salary)
                  FROM employees_subq e2
                  WHERE e2.department_id = e.department_id
              )
            ORDER BY e.salary DESC NULLS LAST,
                     e.employee_id
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, departmentId);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    long employeeId = rs.getLong("EMPLOYEE_ID");
                    String fullName = rs.getString("FULL_NAME");
                    java.math.BigDecimal salary =
                        rs.getBigDecimal("SALARY");

                    System.out.println(
                        employeeId + " " + fullName + " " + salary
                    );
                }
            }
        }
    }
}
~~~

Subquery tương quan theo E.DEPARTMENT_ID; bind variable chỉ truyền mã phòng cho outer query. Alias và điều kiện correlation nằm cố định trong SQL text.

### 18.1. Bind list không phải nối chuỗi IN

Không thể truyền cả một danh sách tùy ý vào một dấu ? rồi mong JDBC tự mở rộng thành nhiều bind variable trong IN. Có thể:
- Tạo đúng số placeholder theo danh sách đã kiểm soát và bind từng giá trị.
- Dùng subquery lấy tập giá trị từ bảng.
- Dùng collection/table parameter theo cơ chế Oracle phù hợp nếu ứng dụng cần danh sách lớn.

Không nối trực tiếp các giá trị người dùng vào SQL. Tên bảng/cột cũng không thể bind; nếu query cần lựa chọn động, ánh xạ qua whitelist.

### 18.2. NULL khi đọc kết quả scalar

Một scalar subquery có thể trả NULL khi không có hàng phù hợp. Với JDBC:
- getString/getBigDecimal/getObject có thể trả Java null tùy kiểu.
- Getter primitive như getInt có thể trả 0; gọi wasNull() ngay sau getter để phân biệt SQL NULL.
- Nếu dùng NVL trong SQL, trạng thái NULL đã được thay bằng giá trị khác trước khi JDBC đọc.

Không dùng NVL chỉ để tránh xử lý Java null nếu NULL có ý nghĩa nghiệp vụ cần giữ.

## 19. Quy trình chọn loại subquery

Trước khi viết truy vấn, hãy xác định câu hỏi:

1. Subquery phải trả **một giá trị** hay một **tập giá trị**?
2. Có bảo đảm duy nhất từ primary key/unique constraint không?
3. Nếu không có hàng, kết quả cần là NULL, 0, FALSE hay không có hàng ngoài?
4. Nếu có nhiều hàng, cần IN, ANY, ALL hay EXISTS?
5. Subquery có cần tham chiếu alias của outer query không?
6. Nếu có NULL trong tập con, IN/NOT IN/ANY/ALL sẽ cho kết quả nào?
7. Có cần giữ hàng ngoài khi không có hàng con không?
8. JOIN rewrite có làm nhân bản hàng hoặc loại hàng không?
9. Optimizer có thể unnest subquery không, plan thực tế thể hiện operation nào?
10. Ứng dụng JDBC có giữ đúng kiểu và trạng thái NULL không?

Gợi ý nhanh:

| Câu hỏi nghiệp vụ | Cách biểu diễn thường phù hợp |
| --- | --- |
| Bằng mức lương cao nhất | Scalar subquery với MAX |
| Thuộc một trong các phòng ban | IN |
| Lớn hơn ít nhất một giá trị | ANY |
| Lớn hơn mọi giá trị | ALL |
| Có ít nhất một nhân viên thỏa điều kiện | EXISTS |
| Không có nhân viên thỏa điều kiện | NOT EXISTS |
| Mỗi phòng ban cần số nhân viên | Correlated COUNT hoặc aggregate + LEFT JOIN |
| Mỗi nhân viên so với trung bình phòng ban của mình | Correlated scalar AVG |
| Cần bảng trung gian đã tổng hợp | Inline view trong FROM |

## 20. Những nhầm lẫn thường gặp

**Single-row subquery nghĩa là outer query trả một hàng.** Không đúng. Subquery trả một giá trị; outer query có thể trả nhiều hàng khớp giá trị đó.

**Subquery không tìm thấy hàng sẽ luôn gây lỗi.** Không đúng. Scalar subquery không có hàng trả NULL; EXISTS trả FALSE; IN với tập rỗng không tìm thấy giá trị.

**Subquery trả nhiều hàng có thể dùng với dấu bằng thông thường.** Không đúng trong ngữ cảnh scalar; thường gây ORA-01427. Dùng IN/ANY/ALL/EXISTS theo mục tiêu.

**Có hàm MAX/AVG/COUNT thì subquery chắc chắn chỉ trả một hàng.** Không đúng nếu có GROUP BY tạo nhiều nhóm.

**NOT IN và NOT EXISTS luôn tương đương.** Không đúng khi có NULL hoặc khi outer key có thể NULL.

**EXISTS cần SELECT một cột cụ thể.** Không đúng. EXISTS kiểm tra sự tồn tại của hàng; SELECT 1 là quy ước dễ đọc.

**Correlated subquery luôn chạy vật lý một lần cho mỗi hàng ngoài.** Không đúng. Đó là cách hiểu logic; optimizer có thể unnest, dùng join hoặc biến đổi khác.

**JOIN luôn nhanh hơn subquery.** Không đúng. Optimizer có thể biến đổi subquery thành join; JOIN có thể nhân bản hàng và cần DISTINCT.

**COUNT(*) trong correlated subquery và EXISTS luôn thay thế cho nhau.** Không đúng. COUNT trả số lượng; EXISTS trả trạng thái tồn tại và diễn đạt mục tiêu khác.

**ANY và ALL chỉ khác tên.** Không đúng. ANY yêu cầu ít nhất một phép so sánh đúng; ALL yêu cầu mọi phép so sánh đúng.

**ALL với tập rỗng trả FALSE.** Không đúng theo logic lượng từ; ALL trên tập rỗng là TRUE, còn ANY trên tập rỗng là FALSE.

**Scalar subquery trong SELECT list không thể correlated.** Không đúng. Ví dụ đếm nhân viên theo từng phòng ban là scalar correlated subquery.

**Subquery trong FROM phải là scalar.** Không đúng. Inline view thường trả nhiều hàng và nhiều cột.

**EXPLAIN PLAN cho biết chính xác thời gian chạy.** Không đúng. Nó cho plan ước lượng; runtime cần quan sát cursor statistics phù hợp.

## 21. Bài tập tự luyện

1. Viết single-row subquery tìm tất cả nhân viên có lương bằng mức cao nhất toàn công ty. Vì sao kết quả ngoài có thể có nhiều hàng?
2. Viết subquery tìm nhân viên có lương lớn hơn trung bình toàn công ty.
3. Nếu subquery scalar trả 0 hàng, outer query nhận giá trị gì? Nếu trả 2 hàng thì lỗi gì?
4. Vì sao SELECT AVG(salary) không GROUP BY trả một hàng, còn SELECT department_id, AVG(salary) GROUP BY department_id có thể trả nhiều hàng?
5. Dùng IN tìm nhân viên thuộc phòng Sales hoặc Engineering.
6. Dùng ANY tìm nhân viên có lương lớn hơn ít nhất một nhân viên Sales.
7. Dùng ALL tìm nhân viên có lương lớn hơn tất cả nhân viên Sales.
8. Giải thích sự khác nhau giữa > ANY và > ALL bằng một tập gồm 10, 20, 30.
9. Vì sao NOT IN có thể không trả phòng ban 40 khi subquery chứa một department_id NULL?
10. Viết lại truy vấn phòng ban không có nhân viên bằng NOT EXISTS.
11. Nếu employee.department_id NULL, vì sao NOT EXISTS so sánh bằng có thể vẫn trả nhân viên đó?
12. Viết correlated scalar subquery đếm số nhân viên cho từng phòng ban, bao gồm phòng ban không có nhân viên.
13. Viết correlated subquery tìm nhân viên có lương cao hơn trung bình phòng ban của họ.
14. Giải thích vì sao correlation không chứng minh subquery vật lý chạy một lần cho mỗi hàng.
15. Viết EXISTS tìm phòng ban có ít nhất một nhân viên lương từ 20 triệu.
16. Viết NOT EXISTS tìm phòng ban không có nhân viên nào đạt 20 triệu; kết quả có khác truy vấn “không có nhân viên” không?
17. Rewrite correlated COUNT bằng LEFT JOIN và giải thích vì sao dùng COUNT(e.employee_id) thay vì COUNT(*).
18. Một scalar subquery dùng MAX nhưng có GROUP BY. Vì sao nó vẫn có thể trả nhiều hàng?
19. Dùng UPDATE với correlated subquery để cập nhật mức lương trung bình vào bảng phòng ban. Điều gì xảy ra với phòng không có nhân viên?
20. Xem execution plan của EXISTS và correlated AVG. Tìm operation semi-join, filter hoặc access path nếu xuất hiện.
21. Viết truy vấn lồng nhau tìm nhân viên thuộc phòng có trung bình lương lớn hơn trung bình toàn công ty.
22. Với Java JDBC, vì sao phải dùng PreparedStatement cho giá trị đầu vào và kiểm tra wasNull() sau getter primitive?
23. Một JOIN làm mỗi phòng ban xuất hiện nhiều lần vì có nhiều nhân viên. Khi nào EXISTS diễn đạt đúng mục tiêu hơn?
24. Thiết kế truy vấn anti-match khi outer key có thể NULL. Hãy nêu rõ NULL có được coi là một nhóm khớp hay không.

**Single-row subquery cung cấp một giá trị, multi-row subquery làm việc với một tập giá trị, còn correlated subquery tham chiếu dữ liệu của query block bên ngoài.** Chọn đúng IN, ANY, ALL, EXISTS hoặc NOT EXISTS giúp SQL thể hiện chính xác câu hỏi; hiểu NULL và số hàng tránh lỗi logic và ORA-01427. Cuối cùng, execution plan mới cho biết Oracle thực hiện truy vấn ra sao: correlated không mặc định là chạy lặp vật lý, và subquery không mặc định chậm hơn JOIN.
