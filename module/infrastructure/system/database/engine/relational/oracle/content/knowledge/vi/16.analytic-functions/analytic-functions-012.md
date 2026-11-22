# Tách bước lọc kết quả phân tích và kiểm tra cú pháp theo phiên bản

Trong Oracle Database, các hàm phân tích (*analytic functions*) như ROW_NUMBER, RANK, DENSE_RANK, SUM OVER, LAG và LEAD được tính trên tập hàng của một query block sau khi FROM, WHERE, GROUP BY và HAVING đã xử lý. Vì vậy, kết quả do analytic function tạo ra thường không thể được lọc trực tiếp bằng WHERE ở cùng query block.

Để lọc những hàng dựa trên kết quả phân tích, cần hiểu hai cách viết:

- **Cách tương thích với các phiên bản Oracle cũ:** tính analytic function trong inline view hoặc common table expression (CTE), sau đó lọc cột kết quả ở query block bên ngoài.
- **Cách viết ngắn với Oracle AI Database 26ai:** dùng mệnh đề **QUALIFY**, được xử lý sau analytic functions và trước ORDER BY/FETCH FIRST.

Điểm quan trọng của bài học là tách đúng các giai đoạn xử lý SQL, chọn cú pháp tương thích với database đích và xác minh phiên bản/RU trước khi đưa QUALIFY vào ứng dụng. Không thể suy ra cú pháp hỗ trợ chỉ từ phiên bản SQL Developer, JDBC driver hoặc IDE đang dùng; câu SQL được phân tích bởi database server mà kết nối thực tế đang trỏ tới.

## 1. Vì sao không thể lọc analytic result bằng WHERE cùng cấp?

Ví dụ muốn lấy nhân viên có lương cao nhất trong mỗi phòng ban:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
WHERE rn = 1;
~~~

Câu SQL trên không hợp lệ vì RN là alias được tạo từ analytic expression trong SELECT list. WHERE của cùng query block được xử lý trước khi analytic function tạo ra RN. Ở thời điểm WHERE chạy, RN chưa tồn tại trong phạm vi query block đó.

Cách hiểu thứ tự xử lý logic:

~~~text
FROM / JOIN
     |
WHERE                  -- lọc hàng nguồn
     |
GROUP BY               -- tạo nhóm nếu có
     |
HAVING                 -- lọc nhóm
     |
Analytic functions     -- tính ROW_NUMBER, RANK, SUM OVER...
     |
QUALIFY                -- nếu phiên bản hỗ trợ
     |
DISTINCT
     |
ORDER BY
     |
FETCH FIRST            -- giới hạn hàng cuối cùng
~~~

Đây là mô hình logic để hiểu ngữ nghĩa. Optimizer có thể biến đổi kế hoạch vật lý, nhưng kết quả truy vấn vẫn phải tuân theo thứ tự ngữ nghĩa của các mệnh đề.

### 1.1. WHERE và analytic function có hai nhiệm vụ khác nhau

WHERE chọn tập hàng **đầu vào** cho analytic function:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
WHERE active_flag = 'Y';
~~~

Chỉ nhân viên đang hoạt động tham gia đánh số. Nếu một phòng có nhân viên lương cao nhất đã nghỉ việc, nhân viên đang hoạt động đứng đầu sẽ nhận RN = 1.

Nếu muốn tính thứ hạng trên toàn bộ nhân viên rồi mới hiển thị những người đang hoạt động, cần tính ranking trước và lọc ACTIVE ở query block ngoài. Hai yêu cầu nghiệp vụ này khác nhau; đặt WHERE sai vị trí sẽ làm thay đổi kết quả.

### 1.2. Không thể thay WHERE bằng HAVING tùy tiện

HAVING lọc các nhóm do GROUP BY tạo ra. Nó không phải mệnh đề chung để lọc analytic result trong cùng query block.

Ví dụ hợp lệ:

~~~sql
SELECT department_id,
       AVG(salary) AS avg_salary
FROM employees
GROUP BY department_id
HAVING AVG(salary) > 20000000;
~~~

HAVING lọc theo aggregate của từng nhóm. Nếu muốn xếp hạng các nhóm theo AVG(SALARY) rồi chỉ lấy ba nhóm đầu, phải dùng query block ngoài hoặc QUALIFY trên phiên bản hỗ trợ.

## 2. Cách tương thích rộng: inline view

Inline view là một subquery trong FROM. Query block bên trong tính analytic function; query block bên ngoài xem kết quả analytic như một cột thông thường và lọc nó bằng WHERE.

~~~sql
SELECT employee_id,
       department_id,
       salary,
       rn
FROM (
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
WHERE rn = 1
ORDER BY department_id NULLS LAST;
~~~

Cấu trúc có hai giai đoạn:

1. Query block trong tính RN cho từng nhân viên.
2. Query block ngoài giữ những hàng có RN = 1.

Đây là cách dùng được trên nhiều thế hệ Oracle, gồm các hệ thống 19c và 21c, và vẫn dùng được trên các phiên bản mới. Khi viết ứng dụng phải chạy trên nhiều phiên bản database, inline view là một lựa chọn tương thích tốt.

### 2.1. Inline view có thể lọc top-N trong từng partition

~~~sql
SELECT department_id,
       employee_id,
       full_name,
       salary,
       rn
FROM (
    SELECT e.department_id,
           e.employee_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
WHERE rn <= 3
ORDER BY department_id NULLS LAST, rn;
~~~

Mỗi phòng ban trả tối đa ba nhân viên. Vì ROW_NUMBER được tính trong query block trong, điều kiện RN <= 3 được áp dụng ở query block ngoài.

Nếu cần giữ tất cả nhân viên đồng hạng tại ranh giới, thay ROW_NUMBER bằng RANK. Nếu muốn lấy N mức lương phân biệt, dùng DENSE_RANK. Cách tách query block không thay đổi ý nghĩa của hàm ranking.

### 2.2. Lọc analytic result bằng alias ở query block ngoài

Alias RN chỉ có phạm vi trong SELECT của query block bên trong. Query block ngoài có thể tham chiếu nó như một cột của inline view:

~~~sql
SELECT ranked.employee_id,
       ranked.salary,
       ranked.rn
FROM (
    SELECT employee_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
) ranked
WHERE ranked.rn <= 10;
~~~

Nên đặt alias cho inline view và qualify tên cột khi câu truy vấn có nhiều nguồn dữ liệu. Điều này giúp tránh nhầm cột RN hoặc tên cột trùng nhau.

## 3. Dùng CTE để tách bước rõ ràng

CTE được khai báo trong mệnh đề WITH, cho phép đặt tên query block trung gian. Về ngữ nghĩa lọc analytic, CTE thực hiện cùng vai trò với inline view.

~~~sql
WITH ranked_employees AS (
    SELECT e.employee_id,
           e.department_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
SELECT employee_id,
       department_id,
       full_name,
       salary,
       rn
FROM ranked_employees
WHERE rn <= 3
ORDER BY department_id NULLS LAST, rn;
~~~

CTE hữu ích khi:
- Truy vấn có nhiều bước biến đổi.
- Cùng một tập dữ liệu trung gian được tham chiếu nhiều lần.
- Muốn đặt tên có ý nghĩa cho kết quả đã xếp hạng.
- Cần tách lọc dữ liệu nguồn khỏi lọc kết quả analytic.
- Câu SQL dài cần dễ đọc và bảo trì.

### 3.1. CTE không có nghĩa chắc chắn tạo bảng tạm

CTE là cách tổ chức query block. Oracle optimizer có thể inline/merge hoặc materialize tùy truy vấn, hint và chi phí. Không mặc định mỗi CTE đều được ghi ra TEMP như một bảng vật lý.

Nếu hiệu năng quan trọng, xem execution plan và runtime statistics thay vì suy luận từ cách viết WITH.

### 3.2. Nhiều giai đoạn analytic có thể dùng nhiều CTE

Ví dụ đầu tiên tính thứ hạng trong từng phòng ban, sau đó đếm số người được chọn theo phòng:

~~~sql
WITH ranked AS (
    SELECT e.department_id,
           e.employee_id,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST, e.employee_id
           ) AS rn
    FROM employees e
),
top_people AS (
    SELECT department_id,
           employee_id,
           salary
    FROM ranked
    WHERE rn <= 3
)
SELECT department_id,
       COUNT(*) AS selected_count,
       AVG(salary) AS selected_avg_salary
FROM top_people
GROUP BY department_id
ORDER BY department_id;
~~~

Query block đầu tính ranking; query block thứ hai lọc top ba; query block cuối tổng hợp kết quả đã lọc. Cách viết này thể hiện rõ ranh giới giữa analytic calculation và aggregate calculation.

## 4. QUALIFY trong Oracle AI Database 26ai

Oracle AI Database 26ai hỗ trợ mệnh đề **QUALIFY** để lọc kết quả của analytic function trong cùng một SELECT query block. Về vai trò, QUALIFY đối với analytic function tương tự HAVING đối với GROUP BY.

Ví dụ top một nhân viên mỗi phòng ban:

~~~sql
SELECT employee_id,
       department_id,
       full_name,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn = 1
ORDER BY department_id NULLS LAST;
~~~

QUALIFY được xử lý sau analytic functions. Vì vậy RN đã được tính khi điều kiện RN = 1 được đánh giá.

Có thể viết analytic function ngay trong predicate:

~~~sql
SELECT employee_id,
       department_id,
       salary
FROM employees
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC NULLS LAST, employee_id
) <= 3
ORDER BY department_id NULLS LAST, salary DESC NULLS LAST;
~~~

Cách viết này không cần inline view chỉ để lọc kết quả ROW_NUMBER.

### 4.1. Vị trí của QUALIFY trong SELECT

Trong Oracle AI Database 26ai, QUALIFY nằm sau WINDOW (nếu có) và trước ORDER BY và FETCH FIRST.

Mô hình thứ tự:

~~~text
SELECT
FROM / JOIN
WHERE
GROUP BY
HAVING
WINDOW
QUALIFY
DISTINCT
ORDER BY
FETCH FIRST
~~~

Nếu không dùng WINDOW clause đặt tên, QUALIFY vẫn nằm sau HAVING và trước ORDER BY.

Ví dụ:

~~~sql
SELECT employee_id,
       salary,
       RANK() OVER (ORDER BY salary DESC NULLS LAST) AS salary_rank
FROM employees
QUALIFY salary_rank <= 5
ORDER BY salary_rank, employee_id
FETCH FIRST 20 ROWS ONLY;
~~~

Câu truy vấn:
1. Tính SALARY_RANK.
2. Giữ hàng có hạng không vượt quá 5.
3. Sắp xếp kết quả.
4. Giới hạn tối đa 20 hàng cuối cùng.

FETCH FIRST ở cuối có thể cắt một phần các hàng đồng hạng đã được QUALIFY giữ lại. Nếu yêu cầu là giữ mọi hàng đồng hạng, cần xem lại row limiting cuối cùng.

### 4.2. QUALIFY có thể tham chiếu alias analytic

Ví dụ:

~~~sql
SELECT employee_id,
       salary,
       ROW_NUMBER() OVER (
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 10;
~~~

Trong Oracle AI Database 26ai, QUALIFY có thể lọc alias của biểu thức analytic trong SELECT list hoặc dùng analytic expression trực tiếp trong predicate.

Dùng alias giúp không phải viết lặp analytic expression. Nếu alias trùng với tên cột nguồn hoặc tên được quote/case-sensitive, nên chọn alias rõ ràng, không gây nhập nhằng.

### 4.3. QUALIFY không thay thế WHERE

WHERE lọc hàng nguồn trước khi analytic function tính toán. QUALIFY lọc hàng sau analytic function.

Ví dụ chỉ xếp hạng nhân viên ACTIVE:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
WHERE active_flag = 'Y'
QUALIFY rn = 1;
~~~

Những nhân viên không ACTIVE không tham gia ranking.

Nếu muốn xếp hạng mọi nhân viên rồi chỉ hiển thị nhân viên ACTIVE có thứ hạng đầu, điều kiện ACTIVE phải được áp dụng ở query block ngoài:

~~~sql
WITH ranked AS (
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           e.active_flag,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST, e.employee_id
           ) AS rn
    FROM employees e
)
SELECT employee_id, department_id, salary
FROM ranked
WHERE active_flag = 'Y'
  AND rn = 1;
~~~

Trong truy vấn thứ hai, RN được tính trên toàn bộ nhân viên trước khi lọc ACTIVE. Nếu người có lương cao nhất đã nghỉ việc, phòng đó có thể không trả hàng nào. Đây là khác biệt nghiệp vụ rất quan trọng.

### 4.4. QUALIFY không thay thế HAVING

HAVING lọc các nhóm đã tổng hợp; QUALIFY lọc kết quả analytic sau khi GROUP BY/HAVING đã xử lý.

Ví dụ xếp hạng phòng ban theo tổng lương:

~~~sql
SELECT department_id,
       SUM(salary) AS total_salary,
       DENSE_RANK() OVER (
           ORDER BY SUM(salary) DESC NULLS LAST
       ) AS salary_level
FROM employees
GROUP BY department_id
HAVING COUNT(*) >= 5
QUALIFY salary_level <= 3
ORDER BY salary_level, department_id;
~~~

Các bước:
- GROUP BY tạo một hàng cho mỗi phòng ban.
- HAVING giữ phòng có ít nhất năm nhân viên.
- DENSE_RANK xếp hạng các phòng còn lại theo tổng lương.
- QUALIFY giữ ba mức tổng lương phân biệt cao nhất.

Trên phiên bản không hỗ trợ QUALIFY, bọc query block đã GROUP BY và tính DENSE_RANK trong inline view rồi lọc SALARY_LEVEL ở ngoài.

## 5. Bảng tương thích cú pháp theo phiên bản Oracle

Mốc quan trọng cần ghi nhớ: **QUALIFY được Oracle giới thiệu trong Oracle AI Database 26ai**, không phải cú pháp có thể mặc định dùng trên mọi database mang tên 23ai.

| Database release | Lọc analytic result trong cùng query block bằng QUALIFY | Cách nên dùng |
| --- | --- | --- |
| Oracle Database 19c | Không hỗ trợ | Inline view hoặc CTE |
| Oracle Database 21c | Không hỗ trợ | Inline view hoặc CTE |
| Oracle Database 23ai trước RU 23.26.0 | Không hỗ trợ | Inline view hoặc CTE |
| Oracle AI Database 26ai, nhánh RU 23.26.0 trở lên | Có hỗ trợ | QUALIFY hoặc inline view/CTE |

Oracle công bố QUALIFY trong tài liệu tính năng mới của Oracle AI Database 26ai. Oracle Database 21c SQL Language Reference mô tả cách lọc analytic result bằng cách lồng query vào subquery rồi lọc ở parent query. Vì vậy, không lấy ví dụ QUALIFY từ tài liệu 26ai rồi chạy nguyên văn trên database 19c, 21c hoặc bản 23ai trước mốc hỗ trợ.

### 5.1. Tên release và số RU có thể gây nhầm lẫn

Oracle đã đổi tên nhánh 23ai thành Oracle AI Database 26ai từ RU 23.26.0. Vì thế có thể gặp:
- Tên sản phẩm hiển thị là 26ai.
- Số phiên bản/RU có dạng 23.26.0...
- Tài liệu cũ nói 23ai, tài liệu mới nói 26ai.

Khi xác định hỗ trợ cú pháp, cần đọc cả release name và version/RU thực tế. Không suy luận chỉ từ con số major ở một giao diện quản trị.

### 5.2. Phiên bản client không quyết định cú pháp server

Một ứng dụng có thể dùng:
- SQL Developer phiên bản mới.
- JDBC driver 23.x hoặc 26.x.
- IDE có syntax highlighting mới.
- Framework ORM mới.

Nhưng nếu kết nối tới database 19c, parser của database 19c vẫn không chấp nhận QUALIFY. Ngược lại, client cũ có thể không tô màu đúng một cú pháp mà database mới hỗ trợ, dù server vẫn có thể phân tích câu SQL.

Hãy xác định database service/instance mà ứng dụng đang kết nối, không chỉ kiểm tra phiên bản công cụ.

## 6. Kiểm tra phiên bản và Release Update

Trước khi sử dụng cú pháp mới, hãy kiểm tra database đích.

### 6.1. Xem banner phiên bản

~~~sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
~~~

V$VERSION thường cung cấp thông tin tên sản phẩm và release. Quyền đọc dynamic performance views phụ thuộc cấu hình và quyền được cấp cho user.

Một truy vấn khác:

~~~sql
SELECT product,
       version,
       status
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

PRODUCT_COMPONENT_VERSION có thể dùng trong môi trường mà tài khoản ứng dụng được phép đọc view này.

### 6.2. Xem phiên bản instance và RU khi có cột tương ứng

Trên các phiên bản hỗ trợ VERSION_FULL:

~~~sql
SELECT version,
       version_full
FROM v$instance;
~~~

VERSION thường cho biết release chính; VERSION_FULL có thêm thông tin đầy đủ hơn, hữu ích để nhận diện RU. Nếu phiên bản cũ không có cột VERSION_FULL, câu SELECT đó có thể báo invalid identifier; khi đó dùng V$VERSION hoặc view phù hợp với release đang chạy.

### 6.3. Xem COMPATIBLE

~~~sql
SELECT value
FROM v$parameter
WHERE name = 'compatible';
~~~

COMPATIBLE là tham số điều khiển mức tương thích định dạng/hành vi database theo quy tắc Oracle. Không dùng giá trị COMPATIBLE thay cho thông tin release/RU để kết luận một cú pháp mới có tồn tại hay không. Hãy xác định database binary/RU thực tế và kiểm tra tài liệu tương ứng.

### 6.4. Kiểm tra trong đúng service mà ứng dụng sử dụng

Trong hệ thống có nhiều database, PDB hoặc service:
- Kết nối đúng service mà ứng dụng production sẽ dùng.
- Chạy câu truy vấn version trong chính session đó.
- Nếu môi trường RAC hoặc rolling update, xác minh các instance/service đích đồng nhất theo kế hoạch vận hành.
- Nếu development, test và production khác RU, chạy thử câu SQL trên từng môi trường.

Một câu QUALIFY chạy được ở local 26ai không chứng minh production 19c có thể chạy.

## 7. Kiểm tra cú pháp QUALIFY an toàn

Nếu đã biết server là Oracle AI Database 26ai, có thể thử một SELECT không ghi dữ liệu:

~~~sql
SELECT dummy,
       ROW_NUMBER() OVER (ORDER BY dummy) AS rn
FROM dual
QUALIFY rn = 1;
~~~

Câu truy vấn đọc DUAL và lọc kết quả analytic. Nếu parser chấp nhận QUALIFY, đây là tín hiệu cú pháp được hỗ trợ trên database session hiện tại.

Nếu server cũ không hỗ trợ, parser sẽ báo lỗi cú pháp, thường là lỗi SQL syntax/ORA-00933 hoặc thông báo tương ứng của phiên bản. Không bắt lỗi rồi mặc định rằng mọi lỗi đều do thiếu QUALIFY; có thể câu SQL còn lỗi khác.

### 7.1. Không dùng câu UPDATE/DELETE để thử cú pháp

Kiểm tra khả năng hỗ trợ cú pháp bằng SELECT trên DUAL hoặc bảng sandbox. Không tạo một DML có khả năng thay đổi dữ liệu chỉ để xem parser có nhận từ khóa hay không.

### 7.2. Syntax test không thay thế kiểm thử nghiệp vụ

Một SELECT thử QUALIFY thành công chỉ xác nhận parser chấp nhận cú pháp cơ bản. Vẫn phải kiểm tra:
- Alias trong QUALIFY.
- Analytic expression phức tạp.
- GROUP BY/HAVING kết hợp.
- DISTINCT và FETCH FIRST.
- NULL semantics.
- Kết quả tie/ranking.
- Query plan và hiệu năng.
- Hành vi của ORM/JDBC khi gửi SQL.

## 8. Viết một truy vấn chạy được trên nhiều phiên bản

Nếu cùng một ứng dụng hỗ trợ Oracle 19c, 21c, 23ai và 26ai, có hai chiến lược.

### 8.1. Dùng inline view/CTE làm cú pháp chung

~~~sql
WITH ranked_orders AS (
    SELECT o.order_id,
           o.customer_id,
           o.created_at,
           o.status,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.created_at DESC NULLS LAST,
                        o.order_id DESC
           ) AS rn
    FROM orders o
    WHERE o.created_at >= :from_date
)
SELECT order_id,
       customer_id,
       created_at,
       status
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
~~~

Cách này tránh phụ thuộc QUALIFY. Nó phù hợp khi:
- Ứng dụng triển khai ở nhiều release.
- SQL được đóng gói trong thư viện dùng chung.
- Không muốn duy trì hai phiên bản câu truy vấn.
- Cần hỗ trợ database cũ lâu dài.

### 8.2. Dùng QUALIFY khi môi trường đích được xác định

~~~sql
SELECT o.order_id,
       o.customer_id,
       o.created_at,
       o.status,
       ROW_NUMBER() OVER (
           PARTITION BY o.customer_id
           ORDER BY o.created_at DESC NULLS LAST,
                    o.order_id DESC
       ) AS rn
FROM orders o
WHERE o.created_at >= :from_date
QUALIFY rn = 1
ORDER BY customer_id;
~~~

Cách này ngắn hơn trong Oracle AI Database 26ai. Nó không tự động tương thích với 19c, 21c hoặc các RU 23ai trước mốc hỗ trợ.

### 8.3. Chọn SQL theo cấu hình, không theo chuỗi version tự đoán

Nếu ứng dụng thực sự cần hai câu SQL:
- Kiểm tra database version/RU ở giai đoạn khởi tạo kết nối hoặc cấu hình môi trường.
- Ánh xạ vào một capability flag như SUPPORTS_QUALIFY.
- Chọn câu SQL tương ứng từ một danh sách câu đã được kiểm soát.
- Không ghép từ khóa hoặc tên cột từ input người dùng.
- Ghi log release/capability để chẩn đoán khi deploy.

Nếu phiên bản database được quản lý bởi deployment configuration, có thể cấu hình capability rõ ràng theo môi trường. Không nên parse chuỗi banner tùy tiện ở mỗi request.

## 9. Phân biệt WHERE, HAVING, QUALIFY và outer WHERE

Bốn vị trí lọc có mục đích khác nhau:

| Mệnh đề | Lọc trên | Thời điểm logic | Ví dụ |
| --- | --- | --- | --- |
| WHERE | Hàng nguồn | Trước GROUP BY và analytic | STATUS = 'ACTIVE' |
| HAVING | Nhóm đã tổng hợp | Sau GROUP BY | COUNT(*) >= 5 |
| QUALIFY | Kết quả analytic | Sau analytic functions, trên 26ai | RN = 1 |
| WHERE ở query block ngoài | Cột kết quả của query block trong | Sau khi query block trong hoàn thành | ranked.rn = 1 |

Ví dụ có đủ các bước trên Oracle AI Database 26ai:

~~~sql
SELECT department_id,
       employee_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
WHERE active_flag = 'Y'
QUALIFY rn <= 3
ORDER BY department_id, rn;
~~~

WHERE lọc ACTIVE trước; analytic function xếp hạng nhân viên ACTIVE; QUALIFY giữ top ba; ORDER BY quyết định thứ tự hiển thị.

Trên Oracle 19c/21c/23ai trước mốc hỗ trợ, có thể diễn đạt bằng inline view:

~~~sql
SELECT department_id, employee_id, salary, rn
FROM (
    SELECT department_id,
           employee_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
    WHERE active_flag = 'Y'
)
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

## 10. Kết hợp nhiều analytic condition

QUALIFY có thể chứa nhiều điều kiện logic:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_avg
FROM employees
QUALIFY rn <= 3
    AND salary > department_avg
ORDER BY department_id, rn;
~~~

Truy vấn giữ top ba nhân viên trong mỗi phòng ban và yêu cầu lương của họ lớn hơn trung bình phòng ban.

Trên phiên bản không hỗ trợ QUALIFY, tính RN và DEPARTMENT_AVG trong inline view rồi đặt cả hai điều kiện ở WHERE bên ngoài:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       rn,
       department_avg
FROM (
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST, e.employee_id
           ) AS rn,
           AVG(e.salary) OVER (
               PARTITION BY e.department_id
           ) AS department_avg
    FROM employees e
)
WHERE rn <= 3
  AND salary > department_avg
ORDER BY department_id, rn;
~~~

Không thể dùng một alias analytic chưa được tạo trong WHERE cùng query block. Inline view đưa các kết quả đó thành cột đầu vào hợp lệ cho WHERE ngoài.

### 10.1. QUALIFY với RANK để giữ đồng hạng

~~~sql
SELECT employee_id,
       department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST
       ) AS salary_rank
FROM employees
QUALIFY salary_rank <= 3
ORDER BY department_id, salary_rank, employee_id;
~~~

Nếu nhiều người đồng lương ở ranh giới hạng 3, tất cả cùng hạng 3 được giữ. Không thêm EMPLOYEE_ID vào analytic ORDER BY nếu muốn giữ đồng hạng theo SALARY; ID chỉ nên nằm ở ORDER BY ngoài để ổn định hiển thị.

### 10.2. QUALIFY sau aggregate và analytic

~~~sql
SELECT department_id,
       SUM(salary) AS total_salary,
       RANK() OVER (
           ORDER BY SUM(salary) DESC NULLS LAST
       ) AS dept_rank
FROM employees
GROUP BY department_id
HAVING COUNT(*) > 1
QUALIFY dept_rank <= 5
ORDER BY dept_rank;
~~~

HAVING loại các nhóm có một nhân viên hoặc ít hơn trước khi RANK xếp hạng. QUALIFY giữ năm hạng đầu trên tập nhóm còn lại.

Nếu muốn xếp hạng toàn bộ phòng ban trước rồi mới chỉ hiển thị phòng có hơn một nhân viên, phải chuyển điều kiện lọc nhóm ra query block ngoài; vị trí HAVING hiện tại làm thay đổi tập tham gia ranking.

## 11. Lọc analytic result và DISTINCT

Trong Oracle AI Database 26ai, thứ tự logic tài liệu hóa đặt QUALIFY trước DISTINCT. Điều này có thể ảnh hưởng kết quả khi DISTINCT loại các hàng trùng sau khi analytic function đã tính và QUALIFY đã lọc.

Ví dụ:

~~~sql
SELECT DISTINCT department_id,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 2
ORDER BY department_id, rn;
~~~

Vì RN khác nhau giữa các hàng trong cùng phòng ban, DISTINCT thường không loại các hàng này. Nếu bỏ RN khỏi select list, hãy xem chính xác analytic expression nào được dùng trong QUALIFY và tập cột DISTINCT đang giữ.

Khi dùng inline view trên bản cũ, DISTINCT ở query block ngoài có thể diễn ra sau khi query block trong đã tính analytic; cần giữ nguyên thứ tự logic nếu chuyển đổi câu truy vấn giữa hai kiểu cú pháp.

## 12. QUALIFY và FETCH FIRST

QUALIFY lọc kết quả analytic; FETCH FIRST giới hạn số hàng của kết quả cuối cùng sau ORDER BY.

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 3
ORDER BY department_id, rn
FETCH FIRST 20 ROWS ONLY;
~~~

Truy vấn lấy tối đa ba người mỗi phòng ban, rồi giới hạn toàn bộ kết quả còn tối đa 20 hàng. Nếu có nhiều phòng ban và tổng số hàng sau QUALIFY lớn hơn 20, FETCH FIRST cắt bớt các hàng cuối theo ORDER BY.

Nếu mục tiêu là tối đa 20 hàng **cho mỗi phòng ban**, hãy đặt điều kiện RN <= 20 trong QUALIFY, không dùng FETCH FIRST 20 ROWS ONLY toàn truy vấn.

## 13. Kiểm thử kết quả và ngữ nghĩa trước khi tối ưu

Khi chuyển một truy vấn từ inline view sang QUALIFY, hãy so sánh trên cùng một tập dữ liệu:

~~~sql
-- Cách inline view.
SELECT employee_id, department_id, salary
FROM (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

~~~sql
-- Cách QUALIFY trên Oracle AI Database 26ai.
SELECT employee_id, department_id, salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 3
ORDER BY department_id, rn;
~~~

Hai câu trên được thiết kế để giữ cùng ý nghĩa. Khi so sánh, hãy kiểm tra:
- Cùng tập hàng nguồn và điều kiện WHERE.
- Cùng PARTITION BY.
- Cùng analytic ORDER BY, bao gồm NULLS FIRST/LAST.
- Cùng tie-breaker.
- Cùng điều kiện lọc ranking.
- Cùng ORDER BY cuối.
- Cùng cách xử lý NULL và duplicate.
- Cùng giới hạn FETCH FIRST nếu có.

Không kết luận hai truy vấn tương đương chỉ vì một tập dữ liệu nhỏ tình cờ cho kết quả giống nhau.

### 13.1. Kiểm tra tie ở ranh giới

Tạo dữ liệu có ít nhất:
- Hai hàng cùng giá trị cao nhất.
- Nhiều hàng cùng giá trị ở ranh giới top-N.
- Một hàng có sort key NULL.
- Nhiều partition.
- Một partition không có hàng sau WHERE.

Sau đó so sánh ROW_NUMBER, RANK và DENSE_RANK. Nếu thay analytic ORDER BY bằng một tổ hợp khác, kết quả tie có thể thay đổi dù câu SQL vẫn chạy.

### 13.2. Kiểm tra trường hợp partition không có hàng

Nếu WHERE loại toàn bộ nhân viên của một phòng ban, analytic function không tạo RN cho phòng đó. QUALIFY không thể khôi phục hàng đã bị WHERE loại.

Nếu báo cáo cần mọi phòng ban kể cả phòng không có nhân viên phù hợp, bắt đầu từ bảng DEPARTMENTS và LEFT JOIN với tập nhân viên đã xếp hạng, hoặc dùng query block phù hợp để giữ hàng cha.

## 14. Hiệu năng: QUALIFY không tự động nhanh hơn inline view

QUALIFY giúp viết câu SQL ngắn hơn và thể hiện rõ mục đích lọc analytic result. Tuy nhiên, không nên suy ra QUALIFY luôn nhanh hơn inline view hoặc CTE.

Optimizer có thể biến đổi các cấu trúc truy vấn tương đương. Hiệu năng phụ thuộc:
- Số hàng nguồn sau WHERE.
- Số partition và cardinality mỗi partition.
- Analytic ORDER BY có cần sort lớn không.
- Index và access path.
- Điều kiện lọc có thể đẩy xuống trước analytic hay không mà vẫn giữ ngữ nghĩa.
- PGA/TEMP và mức độ spill của sort.
- Thống kê optimizer và phiên bản/RU.

### 14.1. Không chuyển điều kiện QUALIFY xuống WHERE nếu làm đổi tập ranking

Ví dụ:

~~~sql
SELECT employee_id,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS rn
FROM employees
QUALIFY rn = 1;
~~~

Không thể tự ý viết lại thành WHERE RN = 1 trong cùng query block. Cũng không thể chuyển một điều kiện lọc hàng từ ngoài vào WHERE nếu điều đó khiến analytic function xếp hạng trên tập hàng nhỏ hơn.

Optimizer chỉ được phép thực hiện các biến đổi bảo toàn kết quả. Khi viết lại thủ công, phải giữ đúng thứ tự ngữ nghĩa.

### 14.2. Xem execution plan

Có thể xem plan ước lượng:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 3;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Trên database hỗ trợ QUALIFY, plan có thể thể hiện WINDOW SORT hoặc operation liên quan analytic, cùng các bước lọc. Trên phiên bản cũ, dùng truy vấn inline view tương đương để kiểm tra plan.

EXPLAIN PLAN là plan ước lượng. Với production, xem cursor plan và runtime statistics khi có quyền, chẳng hạn DBMS_XPLAN.DISPLAY_CURSOR với tùy chọn phù hợp. Không khẳng định một operation cụ thể phải xuất hiện cho mọi truy vấn hoặc mọi RU.

## 15. Java JDBC và SQL theo phiên bản

JDBC gửi câu SQL tới database server. Nếu ứng dụng dùng QUALIFY nhưng server không hỗ trợ, câu lệnh sẽ thất bại khi parse/execute dù driver có phiên bản mới.

### 15.1. Cấu hình capability theo môi trường

Một thiết kế ứng dụng có thể:
- Đọc database product/version từ DatabaseMetaData hoặc truy vấn thông tin release.
- Xác định server có hỗ trợ QUALIFY hay không.
- Chọn SQL template phù hợp.
- Dùng PreparedStatement để bind giá trị.
- Kiểm thử câu SQL trên đúng database release/RU trong CI.

Ví dụ lấy metadata:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public final class DatabaseInfo {
    public static void printVersion(Connection connection)
            throws SQLException {
        DatabaseMetaData metadata = connection.getMetaData();

        System.out.println(metadata.getDatabaseProductName());
        System.out.println(metadata.getDatabaseProductVersion());
        System.out.println(metadata.getDriverName());
        System.out.println(metadata.getDriverVersion());
    }
}
~~~

DATABASEPRODUCTVERSION cho biết phiên bản database server mà connection đang sử dụng; DRIVER VERSION chỉ là phiên bản driver. Không dùng DRIVER VERSION thay cho DATABASE PRODUCT VERSION khi quyết định cú pháp.

### 15.2. Hai SQL template

SQL dùng cho server cũ:

~~~java
String legacySql = """
    SELECT employee_id, department_id, salary
    FROM (
        SELECT e.employee_id,
               e.department_id,
               e.salary,
               ROW_NUMBER() OVER (
                   PARTITION BY e.department_id
                   ORDER BY e.salary DESC NULLS LAST,
                            e.employee_id
               ) AS rn
        FROM employees e
        WHERE e.active_flag = ?
    )
    WHERE rn <= ?
    ORDER BY department_id, rn
    """;
~~~

SQL dùng cho Oracle AI Database 26ai:

~~~java
String modernSql = """
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
    WHERE e.active_flag = ?
    QUALIFY rn <= ?
    ORDER BY department_id, rn
    """;
~~~

Cả hai dùng bind variable cho ACTIVE_FLAG và N. Chỉ khác vị trí lọc analytic result.

### 15.3. Không dò version bằng cách cố chạy QUALIFY trên mỗi request

Không nên gửi thử một câu QUALIFY ở mỗi lần gọi API rồi bắt lỗi để chuyển sang SQL cũ. Cách này:
- Tăng round trip và chi phí parse.
- Làm log lỗi nhiễu.
- Có thể che lỗi SQL thực sự.
- Khiến đường thực thi khó dự đoán.
- Có thể tạo khác biệt hành vi giữa các connection trong pool.

Xác định capability khi khởi tạo datasource hoặc trong cấu hình deployment. Nếu kết nối pool có thể trỏ tới nhiều database/service khác nhau, capability phải tương ứng đúng nhóm connection.

## 16. Quy trình kiểm tra cú pháp theo phiên bản

Trước khi dùng QUALIFY trong dự án:

1. Xác định database service mà ứng dụng thực sự kết nối.
2. Đọc banner/version của server.
3. Xác định RU đầy đủ, đặc biệt nếu đang ở nhánh 23ai/26ai.
4. Đối chiếu tài liệu SQL Language Reference của đúng release.
5. Nếu là 19c, 21c hoặc 23ai trước RU 23.26.0, dùng inline view/CTE.
6. Nếu là Oracle AI Database 26ai, thử SELECT QUALIFY nhỏ trên đúng database.
7. Chạy bộ kiểm thử có tie, NULL, nhiều partition và partition rỗng.
8. So sánh kết quả với phiên bản inline view tương đương.
9. Xem execution plan và runtime statistics.
10. Cập nhật SQL template/capability config và kiểm thử lại trong CI.

### 16.1. Kiểm tra cú pháp trong SQL Developer/SQLcl

Công cụ client có thể cung cấp syntax highlighting hoặc completion theo phiên bản riêng. Điều đó không chứng minh database server hỗ trợ cú pháp. Chạy câu SELECT trên đúng connection mới xác nhận parser server chấp nhận.

Nếu tool báo lỗi, ghi lại:
- Database product version.
- RU đầy đủ.
- SQL text tối thiểu tái hiện.
- Error code/message.
- Service/PDB mà session kết nối.

### 16.2. Không suy luận từ COMPATIBLE một mình

COMPATIBLE không phải bảng liệt kê tất cả từ khóa SQL được parser hỗ trợ. Một database có thể có giá trị COMPATIBLE khác với release mới nhất được cài đặt. Hãy dùng release/RU thực tế và tài liệu tính năng tương ứng để quyết định.

## 17. Bộ dữ liệu thực hành

Tạo bảng sandbox để so sánh inline view và QUALIFY. Các câu DDL/DML dưới đây chỉ dành cho schema thực hành.

### 17.1. Tạo bảng

~~~sql
CREATE TABLE employee_filter_demo (
    employee_id   NUMBER(6)
        CONSTRAINT pk_employee_filter_demo PRIMARY KEY,
    department_id NUMBER(4) NOT NULL,
    full_name     VARCHAR2(80 CHAR) NOT NULL,
    salary        NUMBER(12,2),
    active_flag   CHAR(1) NOT NULL
);
~~~

### 17.2. Nạp dữ liệu

~~~sql
INSERT INTO employee_filter_demo VALUES (101, 10, 'An',    20000000, 'Y');
INSERT INTO employee_filter_demo VALUES (102, 10, 'Binh',  20000000, 'Y');
INSERT INTO employee_filter_demo VALUES (103, 10, 'Chi',   15000000, 'Y');
INSERT INTO employee_filter_demo VALUES (104, 10, 'Dung',  25000000, 'N');

INSERT INTO employee_filter_demo VALUES (201, 20, 'Giang', 30000000, 'Y');
INSERT INTO employee_filter_demo VALUES (202, 20, 'Hanh',  18000000, 'Y');
INSERT INTO employee_filter_demo VALUES (203, 20, 'Khanh', NULL,      'Y');
INSERT INTO employee_filter_demo VALUES (204, 20, 'Lan',   30000000, 'N');

INSERT INTO employee_filter_demo VALUES (301, 30, 'Minh',  12000000, 'Y');

COMMIT;
~~~

Dữ liệu có:
- Phòng 10 có hai nhân viên ACTIVE cùng lương 20 triệu và một người ACTIVE lương 15 triệu.
- Phòng 10 còn một người INACTIVE lương 25 triệu.
- Phòng 20 có hai người ACTIVE cùng lương 30 triệu, một người ACTIVE lương NULL và một người INACTIVE lương 30 triệu.
- Phòng 30 có một người ACTIVE.

### 17.3. Tính ranking cho ACTIVE trước, sau đó lấy top hai

Cách inline view:

~~~sql
SELECT employee_id,
       department_id,
       full_name,
       salary,
       rn
FROM (
    SELECT e.employee_id,
           e.department_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employee_filter_demo e
    WHERE e.active_flag = 'Y'
)
WHERE rn <= 2
ORDER BY department_id, rn;
~~~

Trên Oracle AI Database 26ai, viết tương đương bằng QUALIFY:

~~~sql
SELECT e.employee_id,
       e.department_id,
       e.full_name,
       e.salary,
       ROW_NUMBER() OVER (
           PARTITION BY e.department_id
           ORDER BY e.salary DESC NULLS LAST,
                    e.employee_id
       ) AS rn
FROM employee_filter_demo e
WHERE e.active_flag = 'Y'
QUALIFY rn <= 2
ORDER BY department_id, rn;
~~~

Kết quả dự kiến:
- Phòng 10: An, Binh.
- Phòng 20: Giang, Hanh.
- Phòng 30: Minh.

Ở phòng 20, hai người lương 30 triệu cùng giá trị; EMPLOYEE_ID quyết định thứ tự ROW_NUMBER. Hàng NULL lương nằm sau.

### 17.4. Xếp hạng mọi người trước, sau đó chỉ hiển thị ACTIVE

~~~sql
WITH ranked AS (
    SELECT e.employee_id,
           e.department_id,
           e.full_name,
           e.salary,
           e.active_flag,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employee_filter_demo e
)
SELECT employee_id, department_id, full_name, salary
FROM ranked
WHERE active_flag = 'Y'
  AND rn = 1
ORDER BY department_id;
~~~

Kết quả:
- Phòng 10 không có hàng vì Dung là người có lương cao nhất nhưng INACTIVE; sau khi ranking toàn bộ, Dung nhận RN = 1 rồi bị lọc.
- Phòng 20 không có hàng vì Giang hoặc Lan có lương 30 triệu; Giang đứng RN = 1 do ID nhỏ hơn và ACTIVE, nên Giang được giữ.
- Phòng 30 có Minh.

Ví dụ này cho thấy vị trí WHERE có thể làm thay đổi ý nghĩa của ranking.

### 17.5. So sánh ROW_NUMBER và RANK tại ranh giới

~~~sql
SELECT employee_id,
       department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST
       ) AS salary_rank
FROM employee_filter_demo
WHERE active_flag = 'Y'
QUALIFY salary_rank <= 1
ORDER BY department_id, employee_id;
~~~

Trên 26ai, RANK <= 1 giữ tất cả người đồng hạng đầu trong từng phòng. Phòng 10 có An và Binh; phòng 20 có Giang; phòng 30 có Minh.

Nếu thay RANK bằng ROW_NUMBER và điều kiện RN = 1, mỗi phòng chỉ giữ một hàng. Nếu thay bằng DENSE_RANK <= 1, kết quả cũng giữ mọi hàng ở mức lương phân biệt cao nhất.

### 17.6. Dọn bảng thực hành

~~~sql
DROP TABLE employee_filter_demo PURGE;
~~~

Chỉ xóa bảng sandbox do bài học tạo khi chắc chắn không cần dữ liệu. DROP TABLE là DDL có quy tắc implicit commit; PURGE bỏ qua recycle bin theo hành vi thông thường.

## 18. Lỗi và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ORA-00904 với alias RN trong WHERE | Alias analytic chưa tồn tại trong cùng query block | Dùng inline view/CTE hoặc QUALIFY trên 26ai |
| Lỗi cú pháp tại từ QUALIFY | Server release/RU chưa hỗ trợ | Kiểm tra version/RU, dùng query lồng |
| QUALIFY chạy local nhưng lỗi production | Local và production khác database release | Xác minh database service production |
| SQL Developer tô màu QUALIFY nhưng server báo lỗi | Client parser mới hơn server | Dựa vào server, không dựa syntax highlighting |
| Kết quả ranking thay đổi sau khi thêm WHERE | WHERE làm thay đổi tập hàng tham gia analytic | Xác định lọc trước hay sau ranking |
| QUALIFY trả nhiều hàng hơn dự kiến | Dùng RANK/DENSE_RANK nên giữ tie | Dùng ROW_NUMBER nếu cần đúng tối đa N hàng |
| QUALIFY chỉ giữ một người dù có hòa điểm | ROW_NUMBER cấp số duy nhất | Dùng RANK/DENSE_RANK nếu muốn đồng hạng |
| Inline view và QUALIFY cho kết quả khác | Khác WHERE, partition, order, NULL hoặc tie-breaker | Đối chiếu từng thành phần |
| QUALIFY và FETCH FIRST trả ít hàng hơn top-N mỗi nhóm | FETCH FIRST giới hạn toàn bộ kết quả | Dùng điều kiện ranking theo partition |
| CTE bị hiểu nhầm là bảng tạm | Nhầm cách tổ chức query với kế hoạch vật lý | Xem execution plan |
| Query không giữ phòng ban rỗng | Bắt đầu từ nhân viên hoặc dùng INNER JOIN | Bắt đầu từ bảng phòng ban và LEFT JOIN |
| Dùng COMPATIBLE để suy ra QUALIFY | Nhầm tham số tương thích với release/RU | Kiểm tra server version và tài liệu đúng release |

## 19. Nguyên tắc chọn cú pháp

Có thể áp dụng quy tắc sau:

- Nếu database đích là 19c hoặc 21c, dùng inline view hoặc CTE.
- Nếu là 23ai trước RU 23.26.0, dùng inline view hoặc CTE.
- Nếu là Oracle AI Database 26ai, có thể dùng QUALIFY để viết ngắn hơn.
- Nếu ứng dụng hỗ trợ nhiều release, ưu tiên cú pháp chung hoặc chọn SQL template theo capability đã xác minh.
- Dù dùng cách nào, vẫn phải xác định rõ WHERE lọc trước ranking hay filter ngoài/QUALIFY lọc sau ranking.
- Luôn đặt analytic ORDER BY đủ rõ; với ROW_NUMBER, thêm tie-breaker duy nhất nếu cần lựa chọn ổn định.
- Đặt ORDER BY cuối cùng nếu ứng dụng cần thứ tự hiển thị.
- Kiểm tra NULL, tie, partition rỗng và dữ liệu thay đổi.
- Đo execution plan trên database đích; không mặc định QUALIFY nhanh hơn inline view.

## 20. Bài tập tự luyện

1. Vì sao alias RN không thể dùng trong WHERE của cùng query block?
2. Viết lại truy vấn lọc ROW_NUMBER = 1 bằng inline view.
3. Viết lại cùng truy vấn bằng CTE.
4. Trên Oracle AI Database 26ai, viết truy vấn tương đương dùng QUALIFY.
5. Phân biệt vai trò WHERE, HAVING, QUALIFY và WHERE ở query block ngoài.
6. Một phòng ban có nhân viên ACTIVE và INACTIVE. So sánh kết quả khi lọc ACTIVE trước ranking và sau ranking.
7. Viết truy vấn lấy ba nhân viên lương cao nhất trong từng phòng bằng QUALIFY.
8. Viết truy vấn giữ mọi nhân viên đồng hạng đầu bằng RANK.
9. Vì sao thêm EMPLOYEE_ID vào analytic ORDER BY có thể làm mất tie trong RANK?
10. Viết truy vấn xếp hạng phòng ban theo SUM(SALARY), chỉ giữ nhóm có ít nhất năm nhân viên và ba hạng đầu.
11. Oracle 21c có hỗ trợ QUALIFY không? Cách viết tương thích là gì?
12. Oracle 23ai trước RU 23.26.0 có thể dùng QUALIFY không?
13. Vì sao không thể dùng phiên bản JDBC driver để kết luận database server hỗ trợ QUALIFY?
14. Viết truy vấn kiểm tra banner database bằng V$VERSION.
15. COMPATIBLE có thể thay thế việc kiểm tra database release/RU không? Giải thích.
16. Một câu QUALIFY chạy trên máy cá nhân nhưng lỗi trên production. Hãy liệt kê thông tin cần kiểm tra.
17. Vì sao FETCH FIRST 10 ROWS ONLY sau QUALIFY RN <= 3 không có nghĩa lấy 10 hàng cho mỗi partition?
18. So sánh inline view và QUALIFY về ngữ nghĩa và khả năng tương thích.
19. Vì sao CTE không mặc định là bảng tạm vật lý?
20. Xem execution plan của truy vấn analytic đã lọc. Xác định operation xử lý analytic và lọc nếu có.

## 21. Tài liệu Oracle tham khảo

- [Oracle AI Database 26ai SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/SELECT.html): cú pháp QUALIFY, vị trí mệnh đề, thứ tự xử lý và ví dụ.
- [Oracle AI Database 26ai SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Analytic-Functions.html): thứ tự xử lý analytic functions và quan hệ với QUALIFY.
- [Oracle Database 21c SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/Analytic-Functions.html): cách lọc analytic result bằng nested query trên phiên bản chưa có QUALIFY.
- [Oracle AI Database 26ai New Features Guide](https://docs.oracle.com/en/database/oracle/oracle-database/26/nfcoa/all-nfg.html): hỗ trợ QUALIFY trong 26ai.

**Lọc analytic result là một bước diễn ra sau khi hàm phân tích đã tính xong.** Trên Oracle 19c, 21c và 23ai trước mốc RU 23.26.0, hãy dùng inline view hoặc CTE để tách bước tính và bước lọc. Trên Oracle AI Database 26ai, QUALIFY cho phép viết hai bước đó trong cùng query block. Dù chọn cú pháp nào, hãy xác minh đúng release/RU của database đích và giữ nguyên thứ tự lọc, partition, tie-breaker cùng quy tắc NULL để kết quả không đổi.
