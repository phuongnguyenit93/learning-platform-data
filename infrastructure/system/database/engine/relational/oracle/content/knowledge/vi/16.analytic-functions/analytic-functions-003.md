# ROW_NUMBER, RANK và DENSE_RANK

Trong Oracle Database, các hàm phân tích **ROW_NUMBER**, **RANK** và **DENSE_RANK** dùng để đánh số hoặc xếp hạng hàng theo một thứ tự được xác định trong cửa sổ phân tích. Chúng thường xuất hiện trong báo cáo bảng xếp hạng, chọn N hàng tốt nhất, tìm bản ghi mới nhất cho mỗi nhóm, phân trang và loại bản ghi trùng theo quy tắc nghiệp vụ.

Ba hàm có vẻ gần giống nhau, nhưng cách xử lý các hàng có cùng giá trị sắp xếp rất khác:

- **ROW_NUMBER** cấp một số thứ tự duy nhất cho từng hàng trong mỗi partition.
- **RANK** cho các hàng đồng hạng cùng một thứ hạng và để khoảng trống ở thứ hạng tiếp theo.
- **DENSE_RANK** cũng cho các hàng đồng hạng cùng thứ hạng, nhưng thứ hạng tiếp theo không bị bỏ số.

Muốn chọn đúng hàm, trước hết phải xác định nghiệp vụ muốn **đếm từng hàng**, **xếp hạng kiểu cuộc thi**, hay **xếp hạng các mức giá trị phân biệt**. Sau đó cần xác định phạm vi PARTITION BY, khóa ORDER BY, vị trí NULL và cách xử lý trường hợp hòa điểm.

## 1. Hàm phân tích và mệnh đề OVER

Cú pháp tổng quát:

~~~sql
function_name(expression)
OVER (
    [PARTITION BY partition_expression, ...]
    ORDER BY sort_expression [ASC | DESC]
             [NULLS FIRST | NULLS LAST]
)
~~~

Với ba hàm xếp hạng:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
)
~~~

~~~sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

~~~sql
DENSE_RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

Ý nghĩa các thành phần:

- **function_name** chọn quy tắc đánh số/xếp hạng.
- **PARTITION BY** chia tập hàng thành các nhóm độc lập. Mỗi nhóm bắt đầu đánh số hoặc xếp hạng lại từ 1.
- **ORDER BY** xác định thứ tự dùng để cấp số hoặc xếp hạng bên trong từng nhóm.
- **ASC/DESC** xác định chiều sắp xếp.
- **NULLS FIRST/LAST** xác định vị trí của giá trị NULL trong khóa sắp xếp.

Nếu bỏ PARTITION BY, toàn bộ tập hàng sau các bước xử lý trước analytic function được xem là một partition duy nhất.

Nếu bỏ ORDER BY, ba hàm này không có cơ sở để xác định thứ tự xếp hạng; khi dùng các hàm xếp hạng, hãy khai báo thứ tự rõ ràng.

### 1.1. Ví dụ đơn giản không chia partition

~~~sql
SELECT employee_id,
       full_name,
       salary,
       ROW_NUMBER() OVER (
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS row_no
FROM employees
ORDER BY row_no;
~~~

Tất cả nhân viên nằm trong cùng một partition. Nhân viên có lương cao hơn nhận số thứ tự nhỏ hơn. Nếu lương bằng nhau, EMPLOYEE_ID được dùng làm khóa phụ để quyết định hàng nào nhận số trước.

### 1.2. Ví dụ chia partition theo phòng ban

~~~sql
SELECT employee_id,
       full_name,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS row_no
FROM employees
ORDER BY department_id NULLS LAST, row_no;
~~~

Mỗi phòng ban có dãy ROW_NUMBER riêng bắt đầu từ 1. Nhân viên đứng đầu phòng 10 và nhân viên đứng đầu phòng 20 đều có thể mang ROW_NO = 1.

PARTITION BY không làm giảm số hàng như GROUP BY. Nó chỉ chia các hàng thành những nhóm để hàm phân tích tính toán độc lập.

## 2. ROW_NUMBER: số thứ tự duy nhất cho từng hàng

**ROW_NUMBER()** gán số 1, 2, 3, ... cho các hàng theo thứ tự trong analytic ORDER BY. Mỗi hàng trong một partition nhận một số khác nhau, kể cả khi các giá trị sort key bằng nhau.

Ví dụ:

~~~sql
SELECT employee_id,
       full_name,
       salary,
       ROW_NUMBER() OVER (
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS row_no
FROM employees
ORDER BY row_no;
~~~

Nếu ba nhân viên cùng lương 20 triệu, họ vẫn nhận ba số khác nhau, chẳng hạn 2, 3 và 4. Thứ tự giữa họ phải được xác định bằng một khóa phụ nếu ứng dụng cần kết quả lặp lại ổn định.

### 2.1. ROW_NUMBER cần thứ tự xác định

Nếu chỉ viết:

~~~sql
ROW_NUMBER() OVER (ORDER BY salary DESC)
~~~

và nhiều hàng có cùng SALARY, Oracle không cam kết hàng nào nhận số nhỏ hơn trong nhóm đồng lương. Thứ tự có thể thay đổi theo execution plan, index, dữ liệu hoặc cách xử lý của hệ thống.

Muốn cấp số ổn định, thêm một hoặc nhiều khóa phụ sao cho tổ hợp ORDER BY phân biệt được từng hàng:

~~~sql
ROW_NUMBER() OVER (
    ORDER BY salary DESC NULLS LAST,
             employee_id ASC
)
~~~

Nếu EMPLOYEE_ID là primary key, tổ hợp khóa này tạo thứ tự duy nhất trên tập nhân viên.

**ROW_NUMBER luôn cấp số duy nhất, nhưng nếu ORDER BY không phân biệt được các hàng hòa nhau thì việc gán số cho từng hàng trong nhóm hòa không được xác định.** Đây là khác biệt giữa “số được cấp là duy nhất” và “hàng nào nhận số nào được xác định”.

### 2.2. Chọn N hàng đầu

Muốn lấy đúng tối đa 10 nhân viên có lương cao nhất:

~~~sql
SELECT employee_id, full_name, salary
FROM (
    SELECT employee_id,
           full_name,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST,
                        employee_id
           ) AS rn
    FROM employees
)
WHERE rn <= 10
ORDER BY rn;
~~~

ROW_NUMBER phù hợp khi nghiệp vụ yêu cầu **tối đa N hàng**, không cần giữ tất cả hàng đồng hạng ở vị trí cuối. Nếu có ít hơn N hàng, kết quả trả về ít hơn N.

Nếu dữ liệu có 20 nhân viên cùng lương ở ranh giới thứ 10, truy vấn vẫn chọn đúng 10 hàng theo khóa phụ đã định nghĩa.

### 2.3. Chọn N hàng đầu trong từng nhóm

Ví dụ lấy ba nhân viên lương cao nhất của mỗi phòng ban:

~~~sql
SELECT department_id,
       employee_id,
       full_name,
       salary
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

Mỗi phòng ban có số thứ tự riêng. Điều kiện RN <= 3 được áp dụng ở query block bên ngoài vì analytic function được tính sau WHERE của query block chứa nó.

Đây là mẫu **top-N per group** rất phổ biến.

### 2.4. Chọn bản ghi mới nhất cho mỗi khóa nghiệp vụ

Một bảng lịch sử có thể chứa nhiều phiên bản của cùng một đối tượng. Muốn lấy phiên bản mới nhất cho từng CUSTOMER_ID:

~~~sql
SELECT customer_id,
       address_id,
       address_text,
       updated_at
FROM (
    SELECT a.customer_id,
           a.address_id,
           a.address_text,
           a.updated_at,
           ROW_NUMBER() OVER (
               PARTITION BY a.customer_id
               ORDER BY a.updated_at DESC NULLS LAST,
                        a.address_id DESC
           ) AS rn
    FROM customer_address_history a
)
WHERE rn = 1
ORDER BY customer_id;
~~~

ROW_NUMBER = 1 chọn một bản ghi mới nhất cho mỗi khách hàng. ADDRESS_ID là khóa phụ giúp chọn kết quả xác định khi hai phiên bản có cùng UPDATED_AT.

Nếu nghiệp vụ cần giữ **tất cả phiên bản đồng thời mới nhất** khi timestamp bằng nhau, ROW_NUMBER không phải lựa chọn phù hợp; cân nhắc RANK hoặc DENSE_RANK theo đúng khóa thời gian.

### 2.5. Loại trùng theo quy tắc ưu tiên

Giả sử dữ liệu import có nhiều hàng cho cùng mã khách hàng và muốn giữ hàng mới nhất, có nguồn ưu tiên cao hơn khi cùng thời điểm:

~~~sql
SELECT customer_id,
       source_code,
       imported_at,
       payload
FROM (
    SELECT s.*,
           ROW_NUMBER() OVER (
               PARTITION BY s.customer_id
               ORDER BY s.imported_at DESC NULLS LAST,
                        CASE s.source_code
                            WHEN 'MASTER' THEN 1
                            WHEN 'CRM' THEN 2
                            ELSE 3
                        END,
                        s.import_id DESC
           ) AS rn
    FROM staging_customer s
)
WHERE rn = 1;
~~~

ORDER BY bên trong ROW_NUMBER biểu diễn chính sách chọn bản ghi:
1. Thời điểm import mới hơn đứng trước.
2. Nếu cùng thời điểm, nguồn MASTER được ưu tiên.
3. Nếu vẫn hòa, IMPORT_ID phá hòa.

Đây không chỉ là kỹ thuật SQL; nó là quy tắc nghiệp vụ quyết định bản ghi nào thắng. Cần ghi rõ chính sách để kết quả không phụ thuộc dữ liệu vật lý.

## 3. RANK: xếp hạng có khoảng trống

**RANK()** cho các hàng có cùng toàn bộ giá trị sort key cùng thứ hạng. Thứ hạng kế tiếp tăng theo số hàng đứng trước, nên có thể xuất hiện khoảng trống.

Ví dụ điểm số giảm dần:

| Điểm | Số hàng | RANK |
| ---: | ---: | --- |
| 100 | 2 | 1, 1 |
| 90 | 1 | 3 |
| 80 | 1 | 4 |
| 70 | 2 | 5, 5 |

Hai người cùng điểm 100 đồng hạng 1. Vì đã có hai hàng đứng ở hạng đầu, điểm 90 nhận hạng 3 chứ không phải 2.

Cú pháp:

~~~sql
RANK() OVER (
    [PARTITION BY ...]
    ORDER BY score DESC
)
~~~

### 3.1. RANK theo điểm trong một cuộc thi

~~~sql
SELECT candidate_id,
       candidate_name,
       score,
       RANK() OVER (
           ORDER BY score DESC NULLS LAST
       ) AS competition_rank
FROM exam_result
ORDER BY score DESC NULLS LAST, candidate_id;
~~~

Nếu hai thí sinh cùng điểm, họ có cùng COMPETITION_RANK. Khóa CANDIDATE_ID chỉ được dùng trong ORDER BY ngoài cùng để hiển thị ổn định; nó không tham gia xác định đồng hạng.

Đây là cách biểu diễn bảng xếp hạng kiểu cuộc thi: hai người đồng hạng nhất thì người tiếp theo đứng hạng ba.

### 3.2. RANK theo từng partition

~~~sql
SELECT department_id,
       employee_id,
       full_name,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST
       ) AS salary_rank
FROM employees
ORDER BY department_id NULLS LAST,
         salary_rank,
         employee_id;
~~~

Thứ hạng bắt đầu lại từ 1 trong từng phòng ban. Các nhân viên cùng lương trong một phòng có cùng SALARY_RANK.

### 3.3. RANK <= N để giữ các hàng đồng hạng ở ranh giới

~~~sql
SELECT employee_id, full_name, salary, salary_rank
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           RANK() OVER (
               ORDER BY e.salary DESC NULLS LAST
           ) AS salary_rank
    FROM employees e
)
WHERE salary_rank <= 3
ORDER BY salary_rank, salary DESC NULLS LAST, employee_id;
~~~

Điều kiện RANK <= 3 giữ mọi hàng có thứ hạng 1, 2 hoặc 3. Nếu nhiều hàng đồng hạng ở vị trí thứ ba, tất cả được giữ.

Tuy nhiên, nếu hai hàng cùng hạng 1 thì hàng tiếp theo có hạng 3. RANK <= 2 chỉ trả nhóm hạng 1, không trả nhóm hạng 3. Đây là hành vi đúng của ranking kiểu cuộc thi, không phải lỗi.

### 3.4. Không thêm khóa duy nhất vào analytic ORDER BY nếu muốn giữ đồng hạng

Giả sử muốn hai nhân viên có cùng lương được xếp đồng hạng:

~~~sql
RANK() OVER (
    ORDER BY salary DESC
)
~~~

Nếu viết:

~~~sql
RANK() OVER (
    ORDER BY salary DESC, employee_id
)
~~~

và EMPLOYEE_ID là duy nhất, mọi hàng sẽ có tổ hợp sort key khác nhau; không còn hàng nào đồng hạng. RANK khi đó gần như ROW_NUMBER về kết quả thứ hạng.

Vì vậy:
- **Khóa dùng để định nghĩa đồng hạng** phải nằm trong analytic ORDER BY.
- **Khóa chỉ dùng để sắp xếp cách hiển thị các hàng đồng hạng** nên đặt ở ORDER BY ngoài cùng.

Ví dụ:

~~~sql
SELECT employee_id,
       full_name,
       salary,
       RANK() OVER (ORDER BY salary DESC NULLS LAST) AS salary_rank
FROM employees
ORDER BY salary_rank, employee_id;
~~~

Hai người cùng lương vẫn có cùng SALARY_RANK, nhưng kết quả hiển thị theo EMPLOYEE_ID tăng dần trong nhóm hòa.

## 4. DENSE_RANK: xếp hạng không có khoảng trống

**DENSE_RANK()** cũng cho các hàng có cùng sort key cùng hạng, nhưng hạng tiếp theo tăng đúng một đơn vị. Không bỏ số sau nhóm hòa.

Ví dụ:

| Điểm | Số hàng | DENSE_RANK |
| ---: | ---: | --- |
| 100 | 2 | 1, 1 |
| 90 | 1 | 2 |
| 80 | 1 | 3 |
| 70 | 2 | 4, 4 |

Cú pháp:

~~~sql
DENSE_RANK() OVER (
    [PARTITION BY ...]
    ORDER BY score DESC
)
~~~

### 4.1. Xếp hạng các mức lương phân biệt

~~~sql
SELECT employee_id,
       full_name,
       salary,
       DENSE_RANK() OVER (
           ORDER BY salary DESC NULLS LAST
       ) AS salary_level
FROM employees
ORDER BY salary_level, employee_id;
~~~

Nếu mức lương là 30 triệu, 30 triệu, 20 triệu, 15 triệu:
- Hai người 30 triệu nhận DENSE_RANK = 1.
- Người 20 triệu nhận 2.
- Người 15 triệu nhận 3.

DENSE_RANK phù hợp khi muốn xếp hạng **các mức giá trị khác nhau**, thay vì vị trí của từng hàng trong danh sách.

### 4.2. Lấy N mức lương cao nhất

~~~sql
SELECT employee_id,
       full_name,
       salary,
       salary_level
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           DENSE_RANK() OVER (
               ORDER BY e.salary DESC NULLS LAST
           ) AS salary_level
    FROM employees e
)
WHERE salary_level <= 3
ORDER BY salary_level, employee_id;
~~~

Truy vấn trả tất cả nhân viên thuộc ba mức lương phân biệt cao nhất. Nếu mức lương cao nhất có 20 người, tất cả 20 người vẫn được trả; mức thứ hai và thứ ba cũng được giữ.

Đây là điểm khác với ROW_NUMBER <= 3, vốn chỉ trả tối đa ba hàng.

### 4.3. DENSE_RANK theo từng nhóm

~~~sql
SELECT department_id,
       employee_id,
       full_name,
       salary,
       DENSE_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST
       ) AS salary_level
FROM employees
ORDER BY department_id NULLS LAST,
         salary_level,
         employee_id;
~~~

Mỗi phòng ban có các mức lương phân biệt riêng. Hai nhân viên có cùng lương trong cùng phòng ban nhận cùng một DENSE_RANK.

## 5. So sánh bằng một tập dữ liệu nhỏ

Giả sử có sáu hàng theo điểm giảm dần:

| Mã | Tên | Điểm |
| ---: | --- | ---: |
| 101 | An | 100 |
| 102 | Binh | 100 |
| 103 | Chi | 90 |
| 104 | Dung | 80 |
| 105 | Giang | 80 |
| 106 | Hanh | 70 |

Truy vấn:

~~~sql
SELECT candidate_id,
       candidate_name,
       score,
       ROW_NUMBER() OVER (
           ORDER BY score DESC, candidate_id
       ) AS rn,
       RANK() OVER (
           ORDER BY score DESC
       ) AS rnk,
       DENSE_RANK() OVER (
           ORDER BY score DESC
       ) AS drnk
FROM exam_result
ORDER BY score DESC, candidate_id;
~~~

Kết quả:

| Mã | Điểm | ROW_NUMBER | RANK | DENSE_RANK |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 100 | 1 | 1 | 1 |
| 102 | 100 | 2 | 1 | 1 |
| 103 | 90 | 3 | 3 | 2 |
| 104 | 80 | 4 | 4 | 3 |
| 105 | 80 | 5 | 4 | 3 |
| 106 | 70 | 6 | 6 | 4 |

Quan sát:
- ROW_NUMBER phân biệt mọi hàng: 1 đến 6.
- RANK đồng hạng 100 và 80, nhưng bỏ số 2 và 5.
- DENSE_RANK đồng hạng như RANK nhưng thứ hạng các mức điểm liên tiếp 1, 2, 3, 4.

### 5.1. Top 3 hàng khác với top 3 mức điểm

Với dữ liệu trên:

| Điều kiện | Các hàng được chọn | Số hàng |
| --- | --- | ---: |
| ROW_NUMBER <= 3 | 100, 100, 90 | 3 |
| RANK <= 3 | 100, 100, 90 | 3 |
| DENSE_RANK <= 3 | 100, 100, 90, 80, 80 | 5 |

Trong ví dụ này ROW_NUMBER <= 3 và RANK <= 3 tình cờ trả cùng ba hàng. Nhưng nếu có nhiều người đồng hạng tại vị trí thứ ba, RANK <= 3 sẽ giữ toàn bộ nhóm đồng hạng đó; ROW_NUMBER vẫn cắt ở đúng ba hàng.

DENSE_RANK <= 3 lấy ba mức điểm khác nhau cao nhất, do đó gồm cả hai hàng điểm 80.

## 6. PARTITION BY: xếp hạng độc lập theo nhóm

PARTITION BY chia tập dữ liệu thành các partition. Mỗi partition được đánh số/xếp hạng riêng, không gộp các partition lại.

~~~sql
SELECT department_id,
       employee_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees;
~~~

Nếu có phòng 10, 20 và 30, mỗi phòng bắt đầu lại ở RN = 1.

### 6.1. Có thể phân vùng theo nhiều cột

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY region, product
    ORDER BY sale_date DESC, sale_id DESC
)
~~~

Mỗi cặp REGION/PRODUCT là một partition độc lập. Bên trong cặp đó, giao dịch mới nhất đứng trước; SALE_ID phá hòa.

### 6.2. Partition không nhất thiết là khóa duy nhất

PARTITION BY định nghĩa nhóm logic, không yêu cầu các cột partition phải duy nhất. Nhiều hàng có cùng giá trị partition được xử lý trong cùng cửa sổ.

Nếu một cột partition là NULL, các hàng có cùng giá trị NULL của khóa phân vùng được gom vào cùng partition theo ngữ nghĩa phân tích. Điều này khác với việc dùng NULL như một giá trị có thể so sánh bằng dấu bằng trong WHERE.

### 6.3. Không có PARTITION BY nghĩa là một partition

~~~sql
RANK() OVER (ORDER BY score DESC)
~~~

xếp hạng toàn bộ tập kết quả. Nếu thêm:

~~~sql
RANK() OVER (PARTITION BY class_id ORDER BY score DESC)
~~~

thì hạng bắt đầu lại theo từng lớp. Chỉ thêm PARTITION BY đã thay đổi ý nghĩa bảng xếp hạng.

## 7. ORDER BY trong OVER và ORDER BY cuối câu SELECT

Một câu SQL có thể có hai mệnh đề ORDER BY với hai mục đích khác nhau:

1. **ORDER BY bên trong OVER** quyết định thứ tự cấp ROW_NUMBER/RANK/DENSE_RANK.
2. **ORDER BY ngoài cùng** quyết định thứ tự các hàng được trả về client.

Ví dụ:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
ORDER BY salary ASC NULLS LAST;
~~~

ROW_NUMBER vẫn được cấp theo lương giảm dần trong từng phòng ban, nhưng kết quả hiển thị cuối cùng lại theo lương tăng dần trên toàn bộ tập.

Nếu không có ORDER BY ngoài cùng, thứ tự hiển thị không được bảo đảm, dù analytic function đã có ORDER BY.

### 7.1. Tie-breaker trong analytic và tie-breaker trong output

Ví dụ muốn xếp hạng đồng lương nhưng hiển thị theo mã:

~~~sql
SELECT employee_id,
       salary,
       RANK() OVER (
           ORDER BY salary DESC NULLS LAST
       ) AS salary_rank
FROM employees
ORDER BY salary_rank, employee_id;
~~~

EMPLOYEE_ID chỉ sắp xếp hàng trong kết quả; nó không làm thay đổi nhóm đồng hạng.

Nếu dùng ROW_NUMBER, khóa phụ phải nằm trong analytic ORDER BY để việc gán số ổn định:

~~~sql
ROW_NUMBER() OVER (
    ORDER BY salary DESC NULLS LAST, employee_id
)
~~~

Đừng đặt nhầm khóa duy nhất vào RANK/DENSE_RANK nếu mục tiêu là giữ đồng hạng.

## 8. NULL trong khóa xếp hạng

Oracle có thứ tự NULL mặc định:
- ASC mặc định là NULLS LAST.
- DESC mặc định là NULLS FIRST.

Với bảng xếp hạng điểm/lương, thường muốn NULL nằm cuối:

~~~sql
RANK() OVER (
    ORDER BY score DESC NULLS LAST
)
~~~

Nếu bỏ NULLS LAST trong DESC, những hàng có điểm NULL có thể đứng đầu theo mặc định Oracle.

### 8.1. Nhiều hàng NULL có đồng hạng không?

Nếu analytic ORDER BY chỉ dùng SCORE và nhiều hàng SCORE NULL, chúng có cùng sort key NULL nên có thể nhận cùng RANK hoặc DENSE_RANK. Với ROW_NUMBER, mỗi hàng vẫn nhận số khác nhau; thứ tự giữa các hàng NULL cần khóa phụ nếu muốn xác định.

~~~sql
SELECT employee_id,
       score,
       ROW_NUMBER() OVER (
           ORDER BY score DESC NULLS LAST, employee_id
       ) AS rn,
       RANK() OVER (
           ORDER BY score DESC NULLS LAST
       ) AS rnk,
       DENSE_RANK() OVER (
           ORDER BY score DESC NULLS LAST
       ) AS drnk
FROM exam_result
ORDER BY rn;
~~~

Nếu NULL có nghĩa “chưa chấm”, có thể nghiệp vụ muốn loại các hàng này khỏi bảng xếp hạng:

~~~sql
SELECT employee_id,
       score,
       RANK() OVER (ORDER BY score DESC) AS score_rank
FROM exam_result
WHERE score IS NOT NULL;
~~~

WHERE được áp dụng trước analytic function trong query block, nên hàng SCORE NULL không tham gia xếp hạng. Nếu vẫn cần hiển thị người chưa chấm cùng trạng thái riêng, có thể tính ranking trong inline view rồi xử lý ở ngoài.

### 8.2. NULL và giá trị thay thế

Không dùng NVL(score, 0) chỉ để đẩy NULL xuống cuối nếu điểm 0 là giá trị hợp lệ hoặc cần phân biệt “chưa chấm” với “điểm 0”. Cách rõ hơn:

~~~sql
ORDER BY score DESC NULLS LAST
~~~

Nếu chính sách thật sự coi NULL là 0, có thể dùng NVL, nhưng khi đó hàng NULL và hàng điểm 0 có thể trở thành đồng hạng vì cùng sort key.

## 9. Lọc kết quả ranking bằng inline view hoặc CTE

Analytic function được tính sau WHERE, GROUP BY và HAVING trong cùng query block. Vì vậy không thể tham chiếu alias RN trong WHERE cùng cấp:

~~~sql
-- Không hợp lệ trong cùng query block.
SELECT employee_id,
       ROW_NUMBER() OVER (ORDER BY salary DESC) AS rn
FROM employees
WHERE rn <= 5;
~~~

Dùng inline view:

~~~sql
SELECT employee_id, salary, rn
FROM (
    SELECT employee_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
WHERE rn <= 5
ORDER BY rn;
~~~

Hoặc CTE:

~~~sql
WITH ranked_employees AS (
    SELECT employee_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
SELECT employee_id, salary, rn
FROM ranked_employees
WHERE rn <= 5
ORDER BY rn;
~~~

Inline view và CTE giúp tách hai bước:
1. Tính thứ hạng trên tập hàng.
2. Lọc theo thứ hạng ở query block bên ngoài.

Tên alias RN chỉ có phạm vi trong query block nơi nó được khai báo; query block ngoài có thể tham chiếu nó như một cột của inline view/CTE.

## 10. Xếp hạng kết quả GROUP BY

Các hàm phân tích có thể xếp hạng kết quả đã tổng hợp. Ví dụ xếp hạng phòng ban theo tổng quỹ lương:

~~~sql
SELECT department_id,
       SUM(salary) AS total_salary,
       RANK() OVER (
           ORDER BY SUM(salary) DESC NULLS LAST
       ) AS department_rank
FROM employees
GROUP BY department_id
ORDER BY department_rank, department_id NULLS LAST;
~~~

GROUP BY tạo một hàng cho mỗi phòng ban; RANK sau đó xếp hạng những hàng nhóm này. Có thể dùng SUM(salary) trực tiếp trong analytic ORDER BY vì nó là aggregate của query block.

### 10.1. Xếp hạng doanh thu theo khu vực

~~~sql
SELECT region,
       SUM(amount) AS revenue,
       DENSE_RANK() OVER (
           ORDER BY SUM(amount) DESC
       ) AS revenue_level
FROM sales
GROUP BY region
ORDER BY revenue_level, region;
~~~

Hai khu vực có cùng doanh thu nhận cùng DENSE_RANK. Nếu có ba mức doanh thu khác nhau, hạng là 1, 2, 3 không có khoảng trống.

### 10.2. Xếp hạng trong từng vùng sau tổng hợp

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue,
       RANK() OVER (
           PARTITION BY region
           ORDER BY SUM(amount) DESC
       ) AS product_rank
FROM sales
GROUP BY region, product
ORDER BY region, product_rank, product;
~~~

Mỗi REGION có bảng xếp hạng sản phẩm riêng. Các sản phẩm đồng doanh thu nhận cùng hạng. PRODUCT ở ORDER BY cuối chỉ ổn định cách hiển thị trong nhóm hòa.

## 11. Chọn hàm nào cho top-N?

Ba hàm thường được dùng để lọc top-N, nhưng N có thể mang ba ý nghĩa khác nhau.

| Nhu cầu nghiệp vụ | Hàm | Điều kiện lọc |
| --- | --- | --- |
| Lấy đúng tối đa N hàng theo một thứ tự xác định | ROW_NUMBER | rn <= N |
| Lấy các hàng có thứ hạng kiểu cuộc thi không vượt quá N | RANK | rnk <= N |
| Lấy các hàng thuộc N mức giá trị phân biệt đầu tiên | DENSE_RANK | drnk <= N |

### 11.1. Lấy đúng 5 hàng

~~~sql
SELECT *
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
WHERE rn <= 5;
~~~

Tối đa năm hàng được trả về. Nếu có hòa lương, khóa EMPLOYEE_ID quyết định thứ tự chọn.

### 11.2. Lấy tất cả người thuộc top 5 thứ hạng

~~~sql
SELECT *
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           RANK() OVER (
               ORDER BY e.salary DESC NULLS LAST
           ) AS rnk
    FROM employees e
)
WHERE rnk <= 5
ORDER BY rnk, employee_id;
~~~

Nếu có nhiều người đồng hạng 5, tất cả đều được giữ. Nhưng nếu một nhóm hòa ở hạng 1 có ba người, hạng tiếp theo là 4; điều kiện RANK <= 5 giữ các nhóm hạng 1 và 4, cùng mọi nhóm có hạng 5 nếu có.

### 11.3. Lấy top 5 mức lương phân biệt

~~~sql
SELECT *
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           DENSE_RANK() OVER (
               ORDER BY e.salary DESC NULLS LAST
           ) AS salary_level
    FROM employees e
)
WHERE salary_level <= 5
ORDER BY salary_level, employee_id;
~~~

Nếu có 100 nhân viên nhưng chỉ 3 mức lương khác nhau, truy vấn chỉ có ba cấp salary_level; tất cả nhân viên ở ba cấp này được trả về.

### 11.4. So sánh với FETCH FIRST ... WITH TIES

Oracle hỗ trợ row-limiting clause trong các phiên bản hiện đại:

~~~sql
SELECT employee_id, full_name, salary
FROM employees
ORDER BY salary DESC NULLS LAST
FETCH FIRST 5 ROWS WITH TIES;
~~~

WITH TIES giữ các hàng có cùng giá trị của toàn bộ khóa ORDER BY với hàng ở ranh giới. Nếu thêm EMPLOYEE_ID duy nhất vào ORDER BY, các hàng thường không còn cùng toàn bộ sort key, nên hiệu ứng giữ đồng hạng theo SALARY có thể mất.

Có thể dùng:
- ROW_NUMBER khi cần đúng số hàng và có tie-breaker.
- RANK khi muốn hạng kiểu cuộc thi.
- DENSE_RANK khi muốn N giá trị phân biệt.
- FETCH FIRST ... WITH TIES khi muốn row limiting theo khóa ORDER BY và giữ hàng đồng khóa ở ranh giới.

## 12. Tìm hàng đầu tiên, cuối cùng và bản ghi mới nhất

ROW_NUMBER thường được dùng để chọn một hàng đại diện trong từng nhóm. Tuy nhiên, phải xác định cách xử lý hòa và NULL.

### 12.1. Bản ghi mới nhất theo từng khách hàng

~~~sql
WITH ranked_history AS (
    SELECT h.customer_id,
           h.history_id,
           h.changed_at,
           h.status,
           ROW_NUMBER() OVER (
               PARTITION BY h.customer_id
               ORDER BY h.changed_at DESC NULLS LAST,
                        h.history_id DESC
           ) AS rn
    FROM customer_status_history h
)
SELECT customer_id, history_id, changed_at, status
FROM ranked_history
WHERE rn = 1
ORDER BY customer_id;
~~~

Đây là mẫu chọn một bản ghi. Nếu CUSTOMER_ID có lịch sử nhưng tất cả CHANGED_AT đều NULL, hàng có HISTORY_ID lớn nhất sẽ được chọn do khóa phụ; cần xác định chính sách này có phù hợp không.

### 12.2. Giữ tất cả bản ghi ở thời điểm mới nhất

Nếu cần giữ mọi hàng có thời điểm mới nhất bằng nhau:

~~~sql
WITH ranked_history AS (
    SELECT h.customer_id,
           h.history_id,
           h.changed_at,
           h.status,
           RANK() OVER (
               PARTITION BY h.customer_id
               ORDER BY h.changed_at DESC NULLS LAST
           ) AS rnk
    FROM customer_status_history h
)
SELECT customer_id, history_id, changed_at, status
FROM ranked_history
WHERE rnk = 1
ORDER BY customer_id, history_id;
~~~

Không đưa HISTORY_ID vào analytic ORDER BY nếu muốn các hàng cùng CHANGED_AT đồng hạng. HISTORY_ID chỉ nằm trong ORDER BY ngoài để hiển thị ổn định.

### 12.3. Lấy mức giá trị mới nhất phân biệt

DENSE_RANK = 1 cũng lấy nhóm mới nhất; DENSE_RANK hữu ích hơn khi muốn lấy nhiều mức timestamp phân biệt:

~~~sql
DENSE_RANK() OVER (
    PARTITION BY customer_id
    ORDER BY changed_at DESC NULLS LAST
)
~~~

Điều kiện DRNK <= 3 lấy ba mốc CHANGED_AT khác nhau gần nhất cho từng khách hàng, giữ tất cả hàng có cùng timestamp.

## 13. DEDUPLICATION với ROW_NUMBER

Một tình huống phổ biến là dữ liệu staging có nhiều bản ghi cho cùng khóa nghiệp vụ. ROW_NUMBER có thể đánh dấu bản ghi ưu tiên để chọn một hàng.

~~~sql
WITH marked_rows AS (
    SELECT s.*,
           ROW_NUMBER() OVER (
               PARTITION BY s.external_key
               ORDER BY s.received_at DESC NULLS LAST,
                        s.source_priority ASC,
                        s.staging_id DESC
           ) AS rn
    FROM staging_data s
)
SELECT *
FROM marked_rows
WHERE rn = 1;
~~~

Quy tắc:
- Chia theo EXTERNAL_KEY.
- Bản ghi nhận gần nhất đứng trước.
- Nếu cùng thời điểm, SOURCE_PRIORITY nhỏ hơn đứng trước.
- Nếu vẫn hòa, STAGING_ID lớn hơn đứng trước.

### 13.1. Không xóa dữ liệu chỉ dựa vào ROW_NUMBER khi chưa xác định khóa

Nếu EXTERNAL_KEY có thể NULL, tất cả hàng NULL sẽ cùng một partition. ROW_NUMBER = 1 sẽ giữ một hàng trong toàn bộ nhóm khóa NULL và loại các hàng khác nếu dùng kết quả để xóa. Điều này có thể không đúng nghiệp vụ.

Cần quyết định:
- NULL có phải một khóa chung không?
- Mỗi hàng NULL có phải được giữ riêng?
- Có cần thêm một khóa nguồn để phân biệt?

### 13.2. Xóa duplicate trong bảng

Có thể dùng ROWID để xác định hàng vật lý trong thao tác dọn dữ liệu có kiểm soát:

~~~sql
DELETE FROM staging_data
WHERE ROWID IN (
    SELECT rid
    FROM (
        SELECT ROWID AS rid,
               ROW_NUMBER() OVER (
                   PARTITION BY external_key
                   ORDER BY received_at DESC NULLS LAST,
                            staging_id DESC
               ) AS rn
        FROM staging_data
    )
    WHERE rn > 1
);
~~~

Ví dụ này giữ một hàng ưu tiên trong mỗi EXTERNAL_KEY và xóa những hàng còn lại. **Không chạy trên bảng nghiệp vụ nếu chưa xác định đầy đủ khóa, quy tắc NULL, tie-breaker, backup và transaction/rollback plan.** ROWID là định danh vật lý của hàng trong ngữ cảnh hiện tại, không phải khóa nghiệp vụ lâu dài để lưu ra ngoài.

## 14. ROW_NUMBER, RANK, DENSE_RANK và GROUP BY

GROUP BY làm giảm số hàng bằng cách tạo một hàng cho mỗi nhóm; ranking analytic giữ nguyên số hàng đầu vào của query block và thêm một cột phân tích.

Ví dụ:

~~~sql
SELECT department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank
FROM employees;
~~~

Mỗi nhân viên vẫn xuất hiện riêng.

Trong khi đó:

~~~sql
SELECT department_id,
       MAX(salary) AS max_salary
FROM employees
GROUP BY department_id;
~~~

trả một hàng cho mỗi phòng ban. GROUP BY không giữ lại từng nhân viên để tạo thứ hạng.

Có thể kết hợp GROUP BY và analytic function:
- GROUP BY tạo số liệu theo phòng ban/sản phẩm.
- RANK hoặc DENSE_RANK xếp hạng những nhóm đó.

Nếu muốn giữ toàn bộ nhân viên và thêm tổng phòng ban, có thể cân nhắc SUM(...) OVER (PARTITION BY ...), nhưng đó là hàm tổng hợp phân tích khác, không phải ROW_NUMBER/RANK/DENSE_RANK.

## 15. Vị trí của analytic function trong thứ tự xử lý SQL

Về mặt logic, analytic function được tính sau các bước FROM, WHERE, GROUP BY và HAVING của query block, nhưng trước ORDER BY cuối cùng.

Mô hình đơn giản:

~~~text
FROM / JOIN
    |
WHERE
    |
GROUP BY
    |
HAVING
    |
Analytic functions
    |
ORDER BY cuối cùng
~~~

Hệ quả:
- WHERE lọc hàng trước khi xếp hạng.
- GROUP BY có thể làm thay đổi tập hàng mà ranking nhìn thấy.
- HAVING loại nhóm trước khi analytic function được tính.
- Muốn lọc RN/RANK/DENSE_RANK phải dùng query block ngoài.
- ORDER BY trong OVER và ORDER BY cuối cùng có mục đích riêng.

Ví dụ WHERE trước ranking:

~~~sql
SELECT employee_id,
       salary,
       ROW_NUMBER() OVER (ORDER BY salary DESC) AS rn
FROM employees
WHERE department_id = 10;
~~~

Chỉ nhân viên phòng 10 tham gia đánh số.

Nếu muốn đánh số toàn bộ công ty trước rồi mới hiển thị những người thuộc phòng 10, phải tính ranking ở inline view trước:

~~~sql
SELECT employee_id, department_id, salary, rn
FROM (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
WHERE department_id = 10;
~~~

Hai câu có ý nghĩa khác nhau vì vị trí WHERE thay đổi tập hàng đầu vào của analytic function.

## 16. ROW_NUMBER và ROWNUM không giống nhau

Oracle có pseudocolumn **ROWNUM**, nhưng nó không phải analytic function ROW_NUMBER.

- ROWNUM là số thứ tự được gán khi Oracle chọn hàng trong một query block theo cách thực thi.
- ROW_NUMBER() OVER (ORDER BY ...) là hàm phân tích xếp hàng theo thứ tự được khai báo.
- ROWNUM không có PARTITION BY.
- ROW_NUMBER có thể xếp hạng độc lập theo nhóm.

Mẫu ROWNUM top-N truyền thống cần đặt ORDER BY trong inline view:

~~~sql
SELECT *
FROM (
    SELECT employee_id, salary
    FROM employees
    ORDER BY salary DESC NULLS LAST, employee_id
)
WHERE ROWNUM <= 5;
~~~

Nếu đặt ROWNUM và ORDER BY cùng query block:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE ROWNUM <= 5
ORDER BY salary DESC;
~~~

Oracle có thể chọn năm hàng trước rồi mới sắp xếp năm hàng đó; kết quả không nhất thiết là năm mức lương cao nhất toàn bảng.

Trong mã mới, ROW_NUMBER hoặc FETCH FIRST thường diễn đạt rõ hơn khi cần top-N có thứ tự xác định. Với top-N theo từng partition, ROW_NUMBER là lựa chọn phù hợp hơn ROWNUM.

## 17. Hiệu năng và execution plan

Các hàm ranking có thể cần Oracle sắp xếp hàng theo PARTITION BY và ORDER BY. Với tập dữ liệu lớn, thao tác có thể sử dụng bộ nhớ PGA hoặc ghi tạm ra TEMP nếu workarea không đủ.

### 17.1. Giảm tập hàng trước khi ranking khi ngữ nghĩa cho phép

~~~sql
SELECT employee_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank
FROM employees
WHERE active_flag = 'Y';
~~~

Chỉ nhân viên ACTIVE tham gia xếp hạng. Nếu nghiệp vụ muốn xếp hạng toàn bộ rồi lọc trạng thái sau, phải đặt filter ở query block ngoài; hai cách có kết quả khác nhau.

### 17.2. Index có thể hỗ trợ nhưng không bảo đảm bỏ được sort

Index theo partition key và sort key có thể hỗ trợ một số access path:

~~~sql
CREATE INDEX ix_emp_dept_salary
ON employees (department_id, salary DESC, employee_id);
~~~

Nhưng optimizer có thể vẫn chọn scan và WINDOW SORT/HASH hoặc một plan khác tùy dữ liệu, điều kiện lọc và chi phí ước lượng. Không tạo index chỉ vì một truy vấn có ROW_NUMBER.

Cân nhắc:
- PARTITION BY có những cột nào?
- ORDER BY có những cột nào và chiều nào?
- Tập dữ liệu sau WHERE lớn đến đâu?
- Có bao nhiêu partition và mỗi partition lớn thế nào?
- Truy vấn có cần trả tất cả cột không?
- Index làm tăng chi phí ghi dữ liệu bao nhiêu?

### 17.3. Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Plan có thể xuất hiện operation như WINDOW SORT, WINDOW NOSORT hoặc các operation liên quan đến xử lý analytic tùy phiên bản và access path. Tên operation cụ thể không phải hợp đồng cố định.

EXPLAIN PLAN cung cấp plan ước lượng, không phải số đo thời gian chạy thực tế. Với production, xem cursor plan và runtime statistics khi có quyền, chẳng hạn DBMS_XPLAN.DISPLAY_CURSOR với tùy chọn phù hợp.

### 17.4. Tránh SELECT * trong truy vấn ranking lớn

Khi tính ROW_NUMBER trên bảng có payload lớn như CLOB/BLOB, hãy chỉ lấy các cột cần thiết trong query block xếp hạng nếu có thể. Tập dữ liệu hẹp hơn có thể giảm chi phí sort và bộ nhớ. Nếu cần payload sau khi đã chọn ID, có thể xếp hạng khóa trước rồi join lấy chi tiết ở bước ngoài.

Ví dụ:

~~~sql
WITH ranked_ids AS (
    SELECT employee_id,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
SELECT e.employee_id,
       e.full_name,
       e.salary
FROM ranked_ids r
JOIN employees e
  ON e.employee_id = r.employee_id
WHERE r.rn <= 3
ORDER BY e.department_id, r.rn;
~~~

Chỉ áp dụng khi kế hoạch và cardinality phù hợp; join thêm có thể tạo chi phí khác. Đo trên dữ liệu thực tế.

## 18. Phân trang với ROW_NUMBER

Có thể đánh số toàn bộ kết quả rồi lấy một khoảng số thứ tự:

~~~sql
SELECT employee_id,
       full_name,
       salary,
       rn
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
WHERE rn BETWEEN 21 AND 30
ORDER BY rn;
~~~

Đây là trang thứ ba nếu mỗi trang có 10 hàng. Khóa EMPLOYEE_ID giúp thứ tự duy nhất trong cùng một tập dữ liệu.

### 18.1. Thứ tự xác định không tự bảo đảm snapshot qua nhiều request

Ngay cả khi ORDER BY có khóa duy nhất, nếu dữ liệu thay đổi giữa request trang 1 và trang 2, một hàng mới có thể chen vào đầu danh sách hoặc một hàng cũ bị xóa. OFFSET/ROW_NUMBER pagination có thể khiến người dùng thấy lặp hoặc bỏ sót hàng giữa các trang.

Nếu cần tính nhất quán qua nhiều request, phải xét:
- Giữ cùng một snapshot/transaction nếu mô hình cho phép.
- Chụp mốc dữ liệu hoặc SCN phù hợp.
- Dùng keyset pagination theo khóa cuối trang trước.
- Chấp nhận rõ ràng rằng danh sách phản ánh dữ liệu mới tại mỗi request.

ROW_NUMBER giải quyết thứ tự trong một lần truy vấn; nó không tự khóa dữ liệu giữa nhiều request.

### 18.2. Keyset pagination với khóa sắp xếp duy nhất

Nếu danh sách sắp theo CREATED_AT DESC và ID DESC, trang kế tiếp có thể dùng khóa cuối trang trước:

~~~sql
SELECT id, created_at, title
FROM articles
WHERE created_at < :last_created_at
   OR (
       created_at = :last_created_at
       AND id < :last_id
   )
ORDER BY created_at DESC, id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Cách này không cần đánh số và bỏ qua hàng của các trang trước. Nó giả định CREATED_AT không NULL và ID là khóa duy nhất. Nếu CREATED_AT cho phép NULL, phải bổ sung logic predicate tương ứng với NULLS FIRST/LAST.

## 19. Bộ dữ liệu mẫu để thực hành

Tạo bảng sandbox với điểm số có hòa, nhiều partition và giá trị NULL. Dữ liệu cho phép quan sát khác biệt của ba hàm.

### 19.1. Tạo bảng

~~~sql
CREATE TABLE exam_rank_demo (
    candidate_id   NUMBER(6)
        CONSTRAINT pk_exam_rank_demo PRIMARY KEY,
    candidate_name VARCHAR2(80 CHAR) NOT NULL,
    class_id       NUMBER(4) NOT NULL,
    score          NUMBER(5,2)
);
~~~

### 19.2. Nạp dữ liệu

~~~sql
INSERT INTO exam_rank_demo VALUES (101, 'An',    10, 100);
INSERT INTO exam_rank_demo VALUES (102, 'Binh',  10, 100);
INSERT INTO exam_rank_demo VALUES (103, 'Chi',   10, 90);
INSERT INTO exam_rank_demo VALUES (104, 'Dung',  10, 80);
INSERT INTO exam_rank_demo VALUES (105, 'Giang', 10, 80);
INSERT INTO exam_rank_demo VALUES (106, 'Hanh',  10, 70);

INSERT INTO exam_rank_demo VALUES (201, 'Khanh', 20, 95);
INSERT INTO exam_rank_demo VALUES (202, 'Lan',   20, 95);
INSERT INTO exam_rank_demo VALUES (203, 'Minh',  20, 70);
INSERT INTO exam_rank_demo VALUES (204, 'Nga',   20, NULL);

COMMIT;
~~~

Lớp 10 có sáu người, lớp 20 có bốn người. Điểm 100, 95 và 80 có tie; hàng Nga có điểm NULL.

### 19.3. Tính cả ba kiểu thứ hạng trong từng lớp

~~~sql
SELECT candidate_id,
       candidate_name,
       class_id,
       score,
       ROW_NUMBER() OVER (
           PARTITION BY class_id
           ORDER BY score DESC NULLS LAST, candidate_id
       ) AS rn,
       RANK() OVER (
           PARTITION BY class_id
           ORDER BY score DESC NULLS LAST
       ) AS rnk,
       DENSE_RANK() OVER (
           PARTITION BY class_id
           ORDER BY score DESC NULLS LAST
       ) AS drnk
FROM exam_rank_demo
ORDER BY class_id, rn;
~~~

Kết quả dự kiến:

| Lớp | Mã | Điểm | ROW_NUMBER | RANK | DENSE_RANK |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 101 | 100 | 1 | 1 | 1 |
| 10 | 102 | 100 | 2 | 1 | 1 |
| 10 | 103 | 90 | 3 | 3 | 2 |
| 10 | 104 | 80 | 4 | 4 | 3 |
| 10 | 105 | 80 | 5 | 4 | 3 |
| 10 | 106 | 70 | 6 | 6 | 4 |
| 20 | 201 | 95 | 1 | 1 | 1 |
| 20 | 202 | 95 | 2 | 1 | 1 |
| 20 | 203 | 70 | 3 | 3 | 2 |
| 20 | 204 | NULL | 4 | 4 | 3 |

Trong mỗi lớp, ROW_NUMBER bắt đầu lại từ 1. Hai người cùng điểm nhận cùng RANK và DENSE_RANK. Điểm NULL nằm cuối do khai báo DESC NULLS LAST.

### 19.4. Top hai hàng mỗi lớp

~~~sql
SELECT candidate_id, candidate_name, class_id, score
FROM (
    SELECT e.*,
           ROW_NUMBER() OVER (
               PARTITION BY class_id
               ORDER BY score DESC NULLS LAST, candidate_id
           ) AS rn
    FROM exam_rank_demo e
)
WHERE rn <= 2
ORDER BY class_id, rn;
~~~

Kết quả tối đa hai hàng cho mỗi lớp:
- Lớp 10: An và Binh.
- Lớp 20: Khanh và Lan.

Dù hai người cùng điểm, ROW_NUMBER chọn đúng hai hàng nhờ candidate_id làm tie-breaker.

### 19.5. Top hai thứ hạng mỗi lớp

~~~sql
SELECT candidate_id, candidate_name, class_id, score, rnk
FROM (
    SELECT e.*,
           RANK() OVER (
               PARTITION BY class_id
               ORDER BY score DESC NULLS LAST
           ) AS rnk
    FROM exam_rank_demo e
)
WHERE rnk <= 2
ORDER BY class_id, rnk, candidate_id;
~~~

Cả An và Binh (hạng 1) được giữ; hạng kế tiếp là 3 nên không có hàng nào ở hạng 2. Kết quả cho mỗi lớp chỉ có hai người đồng hạng nhất. Đây là cách RANK xử lý khoảng trống.

### 19.6. Top hai mức điểm phân biệt mỗi lớp

~~~sql
SELECT candidate_id, candidate_name, class_id, score, drnk
FROM (
    SELECT e.*,
           DENSE_RANK() OVER (
               PARTITION BY class_id
               ORDER BY score DESC NULLS LAST
           ) AS drnk
    FROM exam_rank_demo e
)
WHERE drnk <= 2
ORDER BY class_id, drnk, candidate_id;
~~~

Kết quả:
- Lớp 10: hai người điểm 100 và một người điểm 90.
- Lớp 20: hai người điểm 95 và một người điểm 70.

DENSE_RANK <= 2 lấy hai mức điểm phân biệt cao nhất, không phải hai hàng.

### 19.7. Lọc bỏ điểm NULL trước khi xếp hạng

~~~sql
SELECT candidate_id,
       candidate_name,
       score,
       RANK() OVER (
           ORDER BY score DESC
       ) AS rnk
FROM exam_rank_demo
WHERE score IS NOT NULL
ORDER BY rnk, candidate_id;
~~~

Hàng Nga không tham gia bảng xếp hạng. Nếu muốn vẫn hiển thị Nga với trạng thái CHUA CHAM, có thể tính ranking trong inline view trên tập điểm có dữ liệu rồi LEFT JOIN hoặc dùng CASE ở query ngoài.

### 19.8. Dọn bảng sandbox

~~~sql
DROP TABLE exam_rank_demo PURGE;
~~~

Chỉ xóa bảng sandbox do bài học tạo khi chắc chắn không cần dữ liệu. DROP TABLE là DDL có quy tắc implicit commit; PURGE bỏ qua recycle bin theo hành vi thông thường.

## 20. Những lỗi và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| ROW_NUMBER thay đổi giữa các lần chạy | ORDER BY có hàng hòa nhưng không có tie-breaker | Thêm khóa phụ duy nhất vào analytic ORDER BY |
| RANK bỏ mất số thứ hạng | Có nhiều hàng đồng hạng | Đây là hành vi đúng; dùng DENSE_RANK nếu không muốn khoảng trống |
| DENSE_RANK <= 3 trả nhiều hơn 3 hàng | Lấy ba mức sort key phân biệt, giữ mọi hàng đồng hạng | Dùng ROW_NUMBER nếu cần tối đa ba hàng |
| RANK không giữ tất cả hàng ở top N như mong đợi | Hạng bị nhảy qua do tie ở nhóm trước | Xác định cần N thứ hạng kiểu cuộc thi hay N mức phân biệt |
| Hai người cùng điểm không còn đồng hạng | Đã thêm ID duy nhất vào analytic ORDER BY | Chỉ dùng điểm trong RANK/DENSE_RANK; thêm ID ở ORDER BY ngoài |
| NULL đứng đầu khi DESC | Mặc định Oracle là NULLS FIRST | Viết DESC NULLS LAST nếu NULL phải ở cuối |
| Không lọc được RN trong WHERE cùng cấp | Analytic function được tính sau WHERE | Bọc truy vấn bằng inline view hoặc CTE |
| ORDER BY trong OVER không sắp xếp output | Window order và final order là hai mục đích khác nhau | Thêm ORDER BY ở query block cuối |
| Top-N mỗi nhóm bị lấy sai số | Thiếu PARTITION BY hoặc partition key không đúng | Xác định lại nhóm nghiệp vụ |
| ROW_NUMBER chọn nhầm bản ghi mới nhất | Thứ tự ưu tiên hoặc tie-breaker chưa đúng | Viết đầy đủ quy tắc chọn bản ghi |
| Phân trang lặp/mất hàng giữa request | Dữ liệu thay đổi hoặc thứ tự không duy nhất | Total order, keyset pagination hoặc snapshot |
| Sort lớn tốn TEMP | Tập dữ liệu lớn hoặc sort key rộng | Lọc đúng ngữ nghĩa, giảm cột, xem plan và workload |

## 21. Quy trình chọn hàm ranking

Trước khi viết truy vấn, hãy xác định:

1. **Đơn vị được xếp hạng** là từng hàng, nhân viên, sản phẩm hay nhóm đã tổng hợp?
2. **Phạm vi** là toàn công ty hay độc lập theo phòng ban/khu vực/lớp?
3. **Khóa xếp hạng** gồm những cột nào? Các cột đó định nghĩa đồng hạng ra sao?
4. **Tie-breaker** có chỉ dùng để chọn một hàng hay được phép làm thay đổi định nghĩa đồng hạng?
5. **NULL** phải ở đầu, cuối hay bị loại khỏi tập xếp hạng?
6. Nghiệp vụ cần **đúng N hàng**, **N hạng kiểu cuộc thi**, hay **N giá trị phân biệt**?
7. Nếu lọc theo thứ hạng, đã đặt analytic function trong inline view/CTE chưa?
8. Có ORDER BY cuối cùng để xác định thứ tự trả về không?
9. Tập dữ liệu có thay đổi giữa các trang/request không?
10. Execution plan có sort lớn, TEMP usage hoặc access path cần tối ưu không?

Gợi ý lựa chọn:

| Yêu cầu | Lựa chọn |
| --- | --- |
| Đánh số mọi hàng theo thứ tự | ROW_NUMBER |
| Chọn một bản ghi tốt nhất cho mỗi khóa | ROW_NUMBER với PARTITION BY và tie-breaker |
| Bảng xếp hạng kiểu cuộc thi, đồng hạng và có khoảng trống | RANK |
| Xếp hạng các mức giá trị khác nhau, không bỏ số | DENSE_RANK |
| Top N hàng chính xác | ROW_NUMBER <= N |
| Top N thứ hạng có giữ tie | RANK <= N |
| Top N giá trị phân biệt | DENSE_RANK <= N |

## 22. Bài tập tự luyện

1. Với điểm 100, 100, 90, 80, hãy tính ROW_NUMBER, RANK và DENSE_RANK theo điểm giảm dần.
2. Giải thích vì sao RANK của giá trị 90 là 3 trong khi DENSE_RANK là 2.
3. Viết truy vấn lấy năm nhân viên lương cao nhất, bảo đảm kết quả xác định khi có đồng lương.
4. Viết truy vấn lấy tất cả nhân viên thuộc ba mức lương phân biệt cao nhất.
5. Viết truy vấn lấy top ba nhân viên trong từng phòng ban bằng ROW_NUMBER.
6. Thay ROW_NUMBER bằng RANK và giải thích sự thay đổi số hàng trả về khi có hòa ở vị trí thứ ba.
7. Viết DENSE_RANK theo điểm cho từng lớp và lấy hai mức điểm cao nhất.
8. Vì sao không thêm EMPLOYEE_ID vào analytic ORDER BY của RANK nếu muốn giữ đồng hạng theo SALARY?
9. Làm thế nào để sắp xếp output theo EMPLOYEE_ID trong nhóm hòa mà không thay đổi hạng?
10. Khi SALARY NULL và ORDER BY SALARY DESC, Oracle đặt NULL ở đâu theo mặc định? Viết cú pháp đưa NULL xuống cuối.
11. Viết truy vấn chọn địa chỉ mới nhất của mỗi khách hàng, dùng ID để phá hòa.
12. Nếu cần giữ tất cả địa chỉ có cùng thời điểm mới nhất, nên dùng ROW_NUMBER hay RANK? Vì sao?
13. Một partition có hai hàng có EXTERNAL_KEY NULL. Khi PARTITION BY EXTERNAL_KEY, chúng được xử lý thế nào?
14. Vì sao không thể dùng alias RN trong WHERE của cùng query block?
15. Viết lại truy vấn lọc RN = 1 bằng CTE.
16. So sánh WHERE được đặt trước analytic function với WHERE lọc RN ở query block ngoài.
17. Xếp hạng các phòng ban theo SUM(SALARY) sau GROUP BY.
18. Phân biệt ORDER BY trong OVER với ORDER BY cuối câu SELECT.
19. Vì sao ROWNUM <= 5 cùng query block với ORDER BY không phải lúc nào cũng trả năm hàng cao nhất?
20. So sánh ROW_NUMBER <= 5, RANK <= 5 và DENSE_RANK <= 5 bằng một tập dữ liệu có tie ở ranh giới.
21. Một truy vấn phân trang bằng ROW_NUMBER có thứ tự duy nhất. Vì sao dữ liệu thay đổi giữa hai request vẫn có thể làm người dùng thấy lặp hoặc mất hàng?
22. Khi nào keyset pagination phù hợp hơn OFFSET/ROW_NUMBER pagination?
23. Xem execution plan của truy vấn ROW_NUMBER theo DEPARTMENT_ID và SALARY. Tìm operation sort/window nếu xuất hiện.
24. Một bảng staging có nhiều bản ghi cùng khóa nghiệp vụ. Hãy định nghĩa thứ tự ưu tiên và viết truy vấn giữ lại đúng một bản ghi.

**ROW_NUMBER đánh số từng hàng, RANK xếp hạng đồng hạng có khoảng trống, còn DENSE_RANK xếp hạng đồng hạng không có khoảng trống.** PARTITION BY xác định phạm vi xếp hạng; ORDER BY trong OVER định nghĩa thứ tự và đồng hạng; ORDER BY ngoài cùng kiểm soát cách hiển thị. Khi chọn đúng hàm, xử lý NULL rõ ràng và bổ sung tie-breaker đúng chỗ, truy vấn top-N, bảng xếp hạng và chọn bản ghi mới nhất sẽ có kết quả phù hợp với nghiệp vụ và ổn định trên cùng một tập dữ liệu.
