# NTILE, CUME_DIST, PERCENT_RANK và phân bố dữ liệu

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Ba hàm cửa sổ NTILE(), CUME_DIST() và PERCENT_RANK() giúp phân tích vị trí tương đối của một hàng trong tập dữ liệu. Chúng thường được dùng để phân nhóm theo phân vị, đo tỷ lệ tích lũy và biểu diễn thứ hạng dưới dạng tỷ lệ.

Ba hàm đều cần OVER() và hoạt động trong phạm vi partition. Tuy cùng phục vụ phân tích phân bố, chúng trả lời những câu hỏi khác nhau: NTILE chia số hàng thành các nhóm gần bằng nhau; CUME_DIST cho biết tỷ lệ hàng đứng trước hoặc đồng hạng với hàng hiện tại; PERCENT_RANK chuẩn hóa rank về khoảng từ 0 đến 1. Kết quả còn phụ thuộc thứ tự sắp xếp, giá trị đồng hạng và cách xử lý NULL.

Các window function này được hỗ trợ trong MySQL 8.0; MySQL 5.7 không hỗ trợ cú pháp OVER() cho window function. Trong phần kiểm tra kế hoạch, EXPLAIN FORMAT=TREE có từ MySQL 8.0.16 và EXPLAIN ANALYZE có từ MySQL 8.0.18. Hãy kiểm tra phiên bản server bằng SELECT VERSION() trước khi chạy các ví dụ tương ứng.

## 1. Tổng quan ba hàm phân bố

| Hàm | Kết quả | Câu hỏi được trả lời |
|---|---|---|
| NTILE(N) | Số bucket từ 1 đến N | Hàng này thuộc nhóm thứ mấy nếu chia tập thành N nhóm gần bằng nhau? |
| CUME_DIST() | Số thập phân từ 0 đến 1 | Có bao nhiêu phần của partition có giá trị đứng trước hoặc đồng hạng với hàng hiện tại? |
| PERCENT_RANK() | Số thập phân từ 0 đến 1 | Rank của hàng hiện tại nằm ở vị trí tương đối nào giữa rank đầu và rank cuối? |

Cả ba hàm là window function, không gộp nhiều hàng thành một hàng như GROUP BY. Mỗi hàng đầu vào vẫn có một hàng kết quả, kèm thêm giá trị phân nhóm hoặc phân bố.

Ví dụ:

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (ORDER BY salary) AS salary_quartile,
       CUME_DIST() OVER (ORDER BY salary) AS salary_cume_dist,
       PERCENT_RANK() OVER (ORDER BY salary) AS salary_percent_rank
FROM employees;
~~~

Ví dụ trên tính phân bố lương trên toàn bộ tập nhân viên. Nếu muốn tính riêng từng phòng ban, thêm PARTITION BY department_id vào từng window specification.

## 2. Window specification và phạm vi tính toán

Một window specification thường gồm:

- PARTITION BY: chia dữ liệu thành các nhóm độc lập.
- ORDER BY: xác định thứ tự hàng trong mỗi nhóm.
- Frame clause: xác định khung hàng cho những window function có sử dụng frame.

Ví dụ:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_distribution
FROM employees;
~~~

Mỗi phòng ban là một partition riêng. CUME_DIST() bắt đầu tính lại trong từng phòng ban; nhân viên được so sánh với những nhân viên cùng phòng ban.

### 2.1. Không có PARTITION BY

Nếu bỏ PARTITION BY, toàn bộ tập hàng của truy vấn là một partition:

~~~sql
SELECT product_id,
       revenue,
       NTILE(10) OVER (ORDER BY revenue DESC) AS revenue_decile
FROM products;
~~~

Toàn bộ sản phẩm được chia thành 10 nhóm theo doanh thu. Bucket 1 chứa nhóm có doanh thu cao nhất vì thứ tự là DESC.

### 2.2. Window ORDER BY không bảo đảm thứ tự kết quả cuối

ORDER BY bên trong OVER() chỉ xác định thứ tự để tính hàm cửa sổ. Nó không bảo đảm các hàng được trả về theo thứ tự đó. Nếu cần kết quả hiển thị theo bucket hoặc giá trị, hãy có ORDER BY ở cuối câu SELECT:

~~~sql
SELECT product_id,
       revenue,
       NTILE(10) OVER (ORDER BY revenue DESC, product_id) AS revenue_decile
FROM products
ORDER BY revenue_decile, revenue DESC, product_id;
~~~

ORDER BY cuối cùng điều khiển thứ tự result set. Hai loại ORDER BY có mục đích riêng và có thể khác nhau.

## 3. NTILE(N): chia hàng thành các bucket gần bằng nhau

NTILE(N) chia các hàng trong mỗi partition thành N nhóm, càng cân bằng số hàng càng tốt. Hàm trả về số bucket bắt đầu từ 1.

Cú pháp:

~~~sql
NTILE(N) OVER (
    [PARTITION BY expression, ...]
    [ORDER BY expression [ASC | DESC], ...]
)
~~~

N phải là số nguyên dương. Bucket được đánh số theo thứ tự trong ORDER BY; nếu không có ORDER BY, không có cơ sở thứ tự ổn định để diễn giải nhóm.

### 3.1. Quy tắc chia nhóm

Nếu số hàng chia hết cho N, mỗi bucket có cùng số hàng. Nếu không chia hết, các bucket đầu tiên có thêm một hàng so với những bucket còn lại.

Ví dụ:

| Số hàng | NTILE(N) | Số hàng mỗi bucket |
|---:|---:|---|
| 12 | 4 | 3, 3, 3, 3 |
| 10 | 4 | 3, 3, 2, 2 |
| 7 | 3 | 3, 2, 2 |
| 5 | 4 | 2, 1, 1, 1 |

Nếu N lớn hơn số hàng trong partition, chỉ các bucket có hàng mới xuất hiện trong kết quả; những bucket còn lại không có hàng.

### 3.2. Chia thành quartile

Quartile chia dữ liệu thành bốn nhóm có số hàng gần bằng nhau:

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (
           ORDER BY salary ASC, employee_id
       ) AS salary_quartile
FROM employees
ORDER BY salary ASC, employee_id;
~~~

Bucket 1 chứa phần lương thấp nhất; bucket 4 chứa phần lương cao nhất. Nếu muốn bucket 1 là nhóm lương cao nhất, đổi thứ tự thành salary DESC.

### 3.3. Chia thành decile

Decile chia dữ liệu thành 10 nhóm:

~~~sql
SELECT customer_id,
       annual_spend,
       NTILE(10) OVER (
           ORDER BY annual_spend DESC, customer_id
       ) AS spend_decile
FROM customer_metrics;
~~~

Decile 1 là nhóm khách hàng có annual_spend cao nhất; decile 10 là nhóm thấp nhất. Cách đánh số này phụ thuộc ORDER BY DESC.

### 3.4. Bucket được chia theo số hàng, không theo khoảng giá trị

NTILE không bảo đảm các bucket có khoảng giá trị bằng nhau. Nếu doanh thu của phần lớn sản phẩm tập trung từ 0 đến 100 nhưng một vài sản phẩm có doanh thu hàng triệu, các bucket vẫn có số hàng gần bằng nhau; khoảng doanh thu của chúng có thể rất khác.

NTILE cũng không bảo đảm giữ các giá trị đồng hạng trong cùng bucket. Nếu một nhóm nhiều hàng có cùng score nằm đúng ranh giới hai bucket, các hàng đồng hạng có thể bị chia sang hai bucket. Đây là khác biệt quan trọng so với CUME_DIST và PERCENT_RANK.

### 3.5. Thứ tự ổn định khi chia bucket

Nếu ORDER BY không phân định được thứ tự giữa các hàng đồng giá trị, việc gán bucket cho từng hàng trong nhóm đồng hạng có thể không ổn định giữa các lần chạy hoặc kế hoạch thực thi.

Thêm khóa duy nhất làm tiêu chí phụ:

~~~sql
NTILE(4) OVER (
    PARTITION BY department_id
    ORDER BY salary ASC, employee_id ASC
)
~~~

employee_id giúp thứ tự từng hàng rõ ràng. Tuy nhiên, vì employee_id cũng là một phần ORDER BY, các hàng cùng salary nhưng khác employee_id không còn là peer theo toàn bộ window ordering. Đây là điều phù hợp với NTILE khi cần gán bucket ổn định; với CUME_DIST hoặc PERCENT_RANK, cần cân nhắc có muốn giữ các giá trị salary bằng nhau thành peers hay không.

## 4. CUME_DIST(): tỷ lệ tích lũy trong partition

CUME_DIST() trả về cumulative distribution của hàng hiện tại trong partition. Công thức:

\[
\operatorname{CUME\_DIST} =
\frac{\text{số hàng đứng trước hoặc đồng hạng với hàng hiện tại}}
{\text{tổng số hàng trong partition}}
\]

Tử số tính cả toàn bộ hàng thuộc peer group của hàng hiện tại. Giá trị nằm trong khoảng lớn hơn 0 và nhỏ hơn hoặc bằng 1.

Cú pháp:

~~~sql
CUME_DIST() OVER (
    [PARTITION BY expression, ...]
    [ORDER BY expression [ASC | DESC], ...]
)
~~~

### 4.1. Ví dụ tính tỷ lệ tích lũy

Giả sử có năm điểm số theo thứ tự tăng dần:

| Hàng | Điểm | Số hàng đứng trước hoặc đồng hạng | CUME_DIST |
|---:|---:|---:|---:|
| 1 | 10 | 1 | 1/5 = 0.20 |
| 2 | 20 | 3 | 3/5 = 0.60 |
| 3 | 20 | 3 | 3/5 = 0.60 |
| 4 | 40 | 4 | 4/5 = 0.80 |
| 5 | 50 | 5 | 5/5 = 1.00 |

Hai hàng có điểm 20 là peers. CUME_DIST của cả hai đều là 0.60 vì tử số tính đến cuối peer group, không chỉ tính đến vị trí của từng hàng riêng lẻ.

### 4.2. Đọc ý nghĩa khi ORDER BY ASC

Với ORDER BY score ASC, CUME_DIST cho biết tỷ lệ hàng có score nhỏ hơn hoặc bằng giá trị hiện tại (bao gồm toàn bộ peers bằng giá trị đó).

Nếu một sản phẩm có CUME_DIST = 0.90, có khoảng 90% số hàng trong partition có giá trị nhỏ hơn hoặc bằng giá trị của sản phẩm đó. Giá trị này có thể được dùng để xác định vùng phân bố cao của dữ liệu.

### 4.3. Đọc ý nghĩa khi ORDER BY DESC

Khi đổi sang ORDER BY score DESC, thứ tự được đảo ngược. CUME_DIST lúc này tính tỷ lệ hàng đứng trước hoặc đồng hạng trong thứ tự giảm dần, tương ứng với số hàng có score lớn hơn hoặc bằng giá trị hiện tại.

~~~sql
SELECT product_id,
       revenue,
       CUME_DIST() OVER (
           ORDER BY revenue DESC
       ) AS high_to_low_cume_dist
FROM products;
~~~

Không diễn giải CUME_DIST là tỷ lệ giá trị nhỏ hơn hoặc bằng khi window dùng DESC. Luôn đọc cùng hướng ORDER BY.

### 4.4. Peer group ảnh hưởng đến bước nhảy

CUME_DIST có thể nhảy qua nhiều giá trị thay vì tăng đều từng hàng. Nếu một giá trị xuất hiện ở nhiều hàng, tất cả peers có cùng CUME_DIST và tỷ lệ nhảy đến vị trí cuối của nhóm đó.

Ví dụ, nếu 40% hàng có cùng một giá trị ở đầu partition, CUME_DIST của peer group đó có thể là 0.40. Hàm không gán 0.10, 0.20, 0.30, 0.40 riêng cho từng hàng đồng giá trị.

## 5. PERCENT_RANK(): chuẩn hóa rank về khoảng 0 đến 1

PERCENT_RANK() trả về thứ hạng tương đối của một hàng dựa trên hàm RANK(). Công thức:

\[
\operatorname{PERCENT\_RANK} =
\frac{\operatorname{RANK} - 1}
{\text{tổng số hàng trong partition} - 1}
\]

Nếu partition chỉ có một hàng, PERCENT_RANK trả 0 để tránh phép chia cho 0. Giá trị thường nằm trong khoảng từ 0 đến 1.

Cú pháp:

~~~sql
PERCENT_RANK() OVER (
    [PARTITION BY expression, ...]
    [ORDER BY expression [ASC | DESC], ...]
)
~~~

### 5.1. Ví dụ có giá trị đồng hạng

Với điểm số 10, 20, 20, 40, 50:

| Điểm | RANK | Tổng hàng | PERCENT_RANK |
|---:|---:|---:|---:|
| 10 | 1 | 5 | (1 - 1)/(5 - 1) = 0.00 |
| 20 | 2 | 5 | (2 - 1)/(5 - 1) = 0.25 |
| 20 | 2 | 5 | (2 - 1)/(5 - 1) = 0.25 |
| 40 | 4 | 5 | (4 - 1)/(5 - 1) = 0.75 |
| 50 | 5 | 5 | (5 - 1)/(5 - 1) = 1.00 |

Hai hàng có điểm 20 dùng cùng rank 2, vì vậy có cùng PERCENT_RANK 0.25. RANK để lại khoảng trống sau peer group: điểm 40 có rank 4.

### 5.2. Ý nghĩa của 0 và 1

Trong partition có ít nhất hai hàng và có ORDER BY:

- Hàng thuộc peer group đầu tiên có rank 1, PERCENT_RANK = 0.
- Hàng thuộc peer group cuối cùng có rank bằng vị trí đầu của nhóm cuối; nếu nhóm cuối chỉ có một hàng cuối thì PERCENT_RANK = 1.
- Các giá trị ở giữa được chuẩn hóa theo rank và tổng số hàng.

Nếu nhóm cuối có nhiều hàng đồng hạng, tất cả peers vẫn có cùng rank của hàng đầu nhóm; do đó PERCENT_RANK của nhóm cuối có thể nhỏ hơn 1. CUME_DIST của nhóm cuối luôn là 1 vì nó tính đến cuối peer group.

### 5.3. PERCENT_RANK không phải phần trăm hàng nhỏ hơn hoặc bằng

PERCENT_RANK dựa trên rank của đầu peer group, không dựa trên số hàng đứng trước hoặc đồng hạng như CUME_DIST. Vì thế hai hàm có thể trả kết quả khác đáng kể khi có nhiều giá trị trùng.

Đừng đọc PERCENT_RANK = 0.25 như khẳng định chính xác 25% hàng có giá trị nhỏ hơn hoặc bằng hàng hiện tại. Muốn diễn giải tỷ lệ tích lũy bao gồm peers, dùng CUME_DIST với hướng ORDER BY phù hợp.

## 6. So sánh NTILE, CUME_DIST và PERCENT_RANK

Ba hàm có thể được đặt cạnh nhau để thấy cách mỗi hàm biểu diễn cùng một tập dữ liệu:

| Đặc điểm | NTILE(N) | CUME_DIST() | PERCENT_RANK() |
|---|---|---|---|
| Kết quả | Số bucket nguyên | Tỷ lệ từ 0 đến 1 | Tỷ lệ từ 0 đến 1 |
| Cơ sở | Số hàng và vị trí sắp xếp | Vị trí cuối của peer group | RANK của đầu peer group |
| Đồng hạng | Có thể bị tách bucket | Cùng giá trị kết quả | Cùng giá trị kết quả |
| Phân chia đều số hàng | Có, gần bằng nhau | Không | Không |
| Tập một hàng | Bucket 1 | 1 | 0 |
| Phù hợp | Quartile, decile, phân nhóm khách hàng | Tỷ lệ tích lũy, vị trí theo phân phối | Rank chuẩn hóa, vị trí tương đối theo rank |

### 6.1. Kết quả mẫu với cùng dữ liệu

Với năm hàng có điểm 10, 20, 20, 40, 50, giả sử NTILE(4) sắp theo score rồi student_id để có thứ tự từng hàng ổn định:

| student_id | score | NTILE(4) | CUME_DIST theo score | PERCENT_RANK theo score |
|---:|---:|---:|---:|---:|
| 1 | 10 | 1 | 0.20 | 0.00 |
| 2 | 20 | 1 | 0.60 | 0.25 |
| 3 | 20 | 2 | 0.60 | 0.25 |
| 4 | 40 | 3 | 0.80 | 0.75 |
| 5 | 50 | 4 | 1.00 | 1.00 |

Trong bảng này, NTILE có ORDER BY score, student_id nên hai hàng score 20 có thứ tự riêng và có thể bị tách qua bucket 1 và 2. CUME_DIST và PERCENT_RANK chỉ ORDER BY score nên hai hàng score 20 là peers và có cùng kết quả.

Đây là lý do không nên dùng cùng một window ordering một cách máy móc cho cả ba hàm nếu yêu cầu xử lý ties khác nhau.

## 7. Dùng nhiều hàm phân bố trong một truy vấn

Ví dụ xếp nhóm khách hàng theo chi tiêu trong từng khu vực:

~~~sql
SELECT
    customer_id,
    region_id,
    annual_spend,
    NTILE(4) OVER (
        PARTITION BY region_id
        ORDER BY annual_spend DESC, customer_id
    ) AS spend_quartile,
    CUME_DIST() OVER (
        PARTITION BY region_id
        ORDER BY annual_spend DESC
    ) AS spend_cume_dist,
    PERCENT_RANK() OVER (
        PARTITION BY region_id
        ORDER BY annual_spend DESC
    ) AS spend_percent_rank
FROM customer_metrics
ORDER BY region_id, annual_spend DESC, customer_id;
~~~

Ý nghĩa:

- spend_quartile = 1 là nhóm chi tiêu cao nhất trong từng khu vực.
- spend_cume_dist đo tỷ lệ khách hàng đứng trước hoặc đồng hạng trong thứ tự giảm dần, tức tỷ lệ có chi tiêu lớn hơn hoặc bằng giá trị hiện tại.
- spend_percent_rank chuẩn hóa rank của nhóm đồng hạng theo số hàng của khu vực.

NTILE có thêm customer_id để thứ tự bucket ổn định. Hai hàm còn lại chỉ sắp theo annual_spend để giữ các mức chi tiêu bằng nhau trong cùng peer group.

### 7.1. Dùng named window khi cùng định nghĩa

Nếu nhiều hàm dùng cùng partition và order:

~~~sql
SELECT
    employee_id,
    department_id,
    salary,
    CUME_DIST() OVER w AS cume_dist_value,
    PERCENT_RANK() OVER w AS percent_rank_value
FROM employees
WINDOW w AS (
    PARTITION BY department_id
    ORDER BY salary
);
~~~

Named window giúp tránh lặp định nghĩa và giảm nguy cơ hai hàm vô tình dùng partition hoặc order khác nhau. Chỉ dùng chung khi ngữ nghĩa peer group thực sự giống nhau.

### 7.2. Thêm bucket và giữ peer semantics

Nếu NTILE cần khóa phụ để ổn định nhưng CUME_DIST/PERCENT_RANK cần giữ ties, hãy khai báo các OVER riêng như ví dụ trước. Không thêm khóa phụ vào window của hai hàm phân bố chỉ vì muốn sắp xếp đầu ra; hãy đặt thứ tự hiển thị ở ORDER BY cuối câu truy vấn.

## 8. Dùng kết quả window function để lọc dữ liệu

MySQL chỉ cho phép window function trong danh sách SELECT và ORDER BY của query block tương ứng; không thể đặt trực tiếp trong WHERE, GROUP BY hoặc HAVING của cùng query block.

Không viết:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE NTILE(4) OVER (ORDER BY salary) = 1;
~~~

Hãy tính window function trong CTE hoặc derived table rồi lọc ở query block ngoài:

~~~sql
WITH ranked_employees AS (
    SELECT employee_id,
           department_id,
           salary,
           NTILE(4) OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
           ) AS salary_quartile
    FROM employees
)
SELECT employee_id, department_id, salary
FROM ranked_employees
WHERE salary_quartile = 1;
~~~

Truy vấn lấy nhóm 25% nhân viên đầu theo số hàng trong từng phòng ban, nếu cách chia bucket và số hàng tạo ra đúng nhóm mong muốn. Do bucket có thể lệch một hàng khi không chia hết, đây là phân nhóm theo số lượng gần bằng nhau, không phải điều kiện ngưỡng lương cố định.

### 8.1. Lọc theo CUME_DIST

Muốn lấy nhóm có tỷ lệ tích lũy ít nhất 0.90 theo thứ tự tăng dần:

~~~sql
WITH distribution AS (
    SELECT product_id,
           price,
           CUME_DIST() OVER (ORDER BY price ASC) AS price_cume_dist
    FROM products
    WHERE price IS NOT NULL
)
SELECT product_id, price, price_cume_dist
FROM distribution
WHERE price_cume_dist >= 0.90
ORDER BY price, product_id;
~~~

Đây là vùng giá trị cao theo phân phối tích lũy tăng dần. Do peer group được giữ nguyên, số hàng được chọn có thể khác chính xác 10% nếu nhiều hàng có cùng giá tại ngưỡng.

### 8.2. Lọc theo PERCENT_RANK

~~~sql
WITH distribution AS (
    SELECT product_id,
           revenue,
           PERCENT_RANK() OVER (ORDER BY revenue DESC) AS revenue_percent_rank
    FROM products
    WHERE revenue IS NOT NULL
)
SELECT product_id, revenue, revenue_percent_rank
FROM distribution
WHERE revenue_percent_rank <= 0.10
ORDER BY revenue DESC, product_id;
~~~

Với DESC, rank 1 thuộc nhóm doanh thu cao nhất. Điều kiện lấy các hàng có percent_rank không vượt 0.10. Do rank có khoảng trống và ties, số hàng trả về không nhất thiết đúng 10% tổng số hàng.

## 9. Xử lý ties và dữ liệu NULL

### 9.1. Peer group được xác định bởi toàn bộ ORDER BY

Hai hàng là peers nếu tất cả biểu thức trong ORDER BY của window có giá trị tương đương theo quy tắc so sánh. Nếu ORDER BY score, các hàng có score bằng nhau là peers. Nếu ORDER BY score, student_id, các hàng khác student_id không còn peers dù score bằng nhau.

Điều này ảnh hưởng trực tiếp đến CUME_DIST và PERCENT_RANK. Khi muốn cùng điểm có cùng phân bố, chỉ đưa các cột định nghĩa giá trị xếp hạng vào ORDER BY của hai hàm.

### 9.2. NULL vẫn là hàng trong partition

Window function không tự loại hàng có giá trị xếp hạng NULL. Trong MySQL, khi sắp xếp ASC, NULL đứng trước các giá trị không NULL; khi DESC, NULL đứng sau.

Nếu NULL có nghĩa là chưa có dữ liệu và không nên tham gia phân bố, lọc nó trong nguồn trước khi tính:

~~~sql
WITH valid_scores AS (
    SELECT student_id, class_id, score
    FROM exam_results
    WHERE score IS NOT NULL
)
SELECT student_id,
       class_id,
       score,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS score_cume_dist
FROM valid_scores;
~~~

Nếu cần giữ hàng NULL nhưng muốn chúng đứng cuối trong thứ tự tăng dần:

~~~sql
CUME_DIST() OVER (
    PARTITION BY class_id
    ORDER BY (score IS NULL), score
)
~~~

Biểu thức score IS NULL có giá trị 0 với score có dữ liệu và 1 với score NULL. Các hàng NULL vẫn được tính vào tổng số hàng của partition; chúng chỉ được đặt sau các giá trị có dữ liệu.

### 9.3. Khi mọi giá trị trong partition đều NULL

Nếu tất cả giá trị score đều NULL và window ordering chỉ dựa trên score, tất cả hàng là peers. CUME_DIST của các hàng là 1 vì toàn bộ partition đứng trước hoặc đồng hạng với mỗi hàng. PERCENT_RANK của chúng là 0 vì rank của peer group là 1. NTILE vẫn chia hàng theo số lượng và thứ tự hàng; nếu không có tiêu chí phân định, việc gán từng hàng vào bucket không có ý nghĩa ổn định.

Hãy quyết định trước liệu nhóm toàn NULL nên được loại khỏi phân tích, giữ thành một nhóm riêng hay hiển thị như dữ liệu chưa xác định.

## 10. Window frame có ảnh hưởng đến ba hàm này không?

NTILE, CUME_DIST và PERCENT_RANK là các ranking/distribution function. Chúng tính dựa trên partition và window ordering, không phải aggregate theo một frame trượt như SUM() OVER (ROWS ...). Trong MySQL, frame clause không điều khiển phạm vi tính của các hàm này.

Ví dụ:

~~~sql
SELECT score,
       CUME_DIST() OVER (
           ORDER BY score
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS cume_dist_value
FROM exam_results;
~~~

Không diễn giải frame ROWS ở đây như một giới hạn khiến CUME_DIST chỉ tính đến hàng hiện tại theo thứ tự vật lý. CUME_DIST vẫn sử dụng định nghĩa cumulative distribution trên toàn partition và peer group. Để người đọc không hiểu nhầm, thường nên bỏ frame clause khỏi các hàm phân bố này.

## 11. Phân biệt với RANK, DENSE_RANK và ROW_NUMBER

Các hàm xếp hạng có liên quan nhưng không thay thế trực tiếp cho nhau:

| Hàm | Cách đánh số | Xử lý ties |
|---|---|---|
| ROW_NUMBER() | 1, 2, 3, 4, ... | Mỗi hàng có số riêng |
| RANK() | 1, 2, 2, 4, ... | Đồng hạng cùng rank, để lại khoảng trống |
| DENSE_RANK() | 1, 2, 2, 3, ... | Đồng hạng cùng rank, không để khoảng trống |
| NTILE(N) | 1 đến N | Chia theo số hàng, có thể tách peers |
| CUME_DIST() | Tỷ lệ 0 đến 1 | Cùng peer group có cùng tỷ lệ tích lũy |
| PERCENT_RANK() | Tỷ lệ 0 đến 1 | Cùng peer group có cùng rank chuẩn hóa |

Ví dụ:

~~~sql
SELECT student_id,
       score,
       ROW_NUMBER() OVER (ORDER BY score) AS row_num,
       RANK() OVER (ORDER BY score) AS rank_value,
       DENSE_RANK() OVER (ORDER BY score) AS dense_rank_value,
       CUME_DIST() OVER (ORDER BY score) AS cume_dist_value,
       PERCENT_RANK() OVER (ORDER BY score) AS percent_rank_value
FROM exam_results;
~~~

ROW_NUMBER phù hợp khi cần số thứ tự duy nhất; RANK và DENSE_RANK thể hiện thứ hạng có ties; CUME_DIST và PERCENT_RANK chuẩn hóa vị trí theo phân phối; NTILE tạo nhóm theo số lượng hàng.

## 12. Ứng dụng trong phân tích dữ liệu

### 12.1. Phân nhóm khách hàng

Chia khách hàng thành 5 nhóm theo tổng chi tiêu trong từng khu vực:

~~~sql
WITH customer_spend AS (
    SELECT customer_id,
           region_id,
           SUM(total_amount) AS total_spend
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id, region_id
),
segmented AS (
    SELECT customer_id,
           region_id,
           total_spend,
           NTILE(5) OVER (
               PARTITION BY region_id
               ORDER BY total_spend DESC, customer_id
           ) AS spend_group
    FROM customer_spend
)
SELECT *
FROM segmented
ORDER BY region_id, spend_group, total_spend DESC;
~~~

Nhóm 1 là khách có tổng chi tiêu cao nhất trong khu vực. Việc tổng hợp trước window function bảo đảm mỗi khách chỉ có một hàng đầu vào cho NTILE.

### 12.2. Xác định ngưỡng phân bố doanh thu

~~~sql
SELECT product_id,
       revenue,
       CUME_DIST() OVER (
           PARTITION BY category_id
           ORDER BY revenue
       ) AS revenue_distribution
FROM product_metrics;
~~~

Với ORDER BY tăng dần, revenue_distribution cho biết tỷ lệ sản phẩm trong danh mục có doanh thu nhỏ hơn hoặc bằng mức hiện tại. Có thể dùng để tìm sản phẩm ở vùng doanh thu cao hoặc thấp, đồng thời cần lưu ý ties ở ngưỡng.

### 12.3. So sánh vị trí tương đối giữa phòng ban

~~~sql
SELECT employee_id,
       department_id,
       salary,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees;
~~~

Percent rank bằng 0.8 cho biết rank của nhân viên nằm ở vùng cao của phân bố lương trong phòng ban. Đây là vị trí tương đối theo rank, không phải lương cao hơn chính xác 80% nhân viên nếu có nhiều ties.

### 12.4. Xây dựng báo cáo theo bucket

~~~sql
WITH bucketed AS (
    SELECT order_id,
           customer_id,
           total_amount,
           NTILE(4) OVER (
               ORDER BY total_amount DESC, order_id
           ) AS amount_quartile
    FROM orders
    WHERE status = 'PAID'
)
SELECT amount_quartile,
       COUNT(*) AS order_count,
       MIN(total_amount) AS min_amount,
       MAX(total_amount) AS max_amount,
       AVG(total_amount) AS average_amount
FROM bucketed
GROUP BY amount_quartile
ORDER BY amount_quartile;
~~~

Truy vấn đầu chia đơn thành bốn bucket theo số hàng; truy vấn ngoài tổng hợp đặc điểm mỗi bucket. MIN/MAX ở đây là aggregate trên các hàng đã được gán bucket, khác với window function phân bố ở query block trong.

## 13. Hiệu năng và EXPLAIN

Window function có thể cần sắp xếp dữ liệu theo PARTITION BY và ORDER BY. Trên tập dữ liệu lớn, sort, buffer và internal temporary table có thể chiếm CPU, bộ nhớ và I/O.

### 13.1. Index hỗ trợ partition và order

Ví dụ:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees;
~~~

Index bắt đầu bằng department_id rồi salary có thể hữu ích cho truy cập theo thứ tự:

~~~sql
CREATE INDEX ix_employees_department_salary
ON employees (department_id, salary);
~~~

Index này không bảo đảm MySQL loại bỏ hoàn toàn sort cho window function. Khả năng sử dụng phụ thuộc query plan, cột được chọn, điều kiện lọc, thứ tự index và phiên bản. Kiểm tra index hiện có trước khi tạo mới.

### 13.2. Nhiều window ordering có thể cần nhiều lần sắp xếp

Nếu NTILE dùng ORDER BY score, student_id còn CUME_DIST dùng ORDER BY score, MySQL có thể cần xử lý các thứ tự window khác nhau. Dù các định nghĩa có chung PARTITION BY, việc thêm cột vào ORDER BY có thể tạo một window ordering khác.

Chỉ gộp các window definition khi cùng semantics. Nếu cần ties cho CUME_DIST và thứ tự xác định cho NTILE, giữ các window riêng và đo kế hoạch thực tế.

### 13.3. Đọc EXPLAIN

~~~sql
EXPLAIN FORMAT=TREE
SELECT employee_id,
       department_id,
       salary,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY salary, employee_id
       ) AS salary_quartile,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_cume_dist
FROM employees;
~~~

Quan sát:

- Các bước sort và window aggregate/evaluation.
- Số hàng đầu vào mỗi partition.
- Index được chọn cho bảng nguồn.
- Bảng tạm hoặc bước materialize nếu có.
- Ước lượng số hàng và chi phí của các query block.

### 13.4. EXPLAIN ANALYZE

MySQL 8.0.18+ hỗ trợ EXPLAIN ANALYZE cho câu SELECT tương thích. Lệnh này thực thi truy vấn và cho biết thời gian, số hàng thực tế và số vòng lặp của iterator:

~~~sql
EXPLAIN ANALYZE
SELECT employee_id,
       department_id,
       salary,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_cume_dist
FROM employees;
~~~

Chỉ chạy khi đã đánh giá tải; EXPLAIN ANALYZE thực thi truy vấn thật. Dùng lab hoặc staging có dữ liệu đại diện để so sánh plan và số liệu.

### 13.5. Giảm dữ liệu trước khi tính window

Nếu chỉ phân tích một khoảng thời gian, lọc dữ liệu ở query block đầu vào khi điều kiện đó đúng với yêu cầu:

~~~sql
WITH monthly_sales AS (
    SELECT customer_id,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
      AND created_at >= '2026-01-01'
      AND created_at < '2027-01-01'
    GROUP BY customer_id
)
SELECT customer_id,
       total_amount,
       NTILE(10) OVER (ORDER BY total_amount DESC, customer_id) AS spend_decile
FROM monthly_sales;
~~~

Window function chỉ xử lý tập kết quả của monthly_sales. Không đẩy điều kiện xuống trước hoặc sau phép tổng hợp nếu điều đó làm thay đổi tập dữ liệu cần phân tích.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| NTILE tạo bucket có khoảng giá trị rất khác nhau | NTILE cân bằng số hàng, không cân bằng độ rộng giá trị | Dùng hàm phù hợp với mục tiêu; xem phân phối dữ liệu |
| Hai hàng cùng điểm vào hai bucket khác nhau | NTILE chia theo từng hàng và có thể tách peers | Chấp nhận quy tắc đó hoặc phân nhóm theo giá trị distinct trước |
| Bucket thay đổi giữa các lần chạy | ORDER BY không có tiêu chí phân định hàng đồng hạng | Thêm khóa duy nhất vào ORDER BY của NTILE |
| CUME_DIST nhảy qua một khoảng lớn | Nhiều hàng thuộc cùng peer group | Đây là hành vi đúng; hàm tính đến cuối peer group |
| PERCENT_RANK khác tỷ lệ tích lũy mong đợi | Hàm dựa trên RANK, không phải số hàng <= giá trị hiện tại | Dùng CUME_DIST nếu cần cumulative proportion |
| PERCENT_RANK của partition một hàng là 0 | Công thức được xử lý riêng để tránh chia cho 0 | Đây là kết quả đúng |
| CUME_DIST trả 1 cho tất cả hàng | Có thể window không có ORDER BY nên mọi hàng là peers, hoặc partition chỉ có một peer group | Xác định ORDER BY có phản ánh thứ tự nghiệp vụ không |
| Hàng NULL làm thay đổi bucket hoặc phân bố | NULL vẫn thuộc partition và được sắp xếp theo quy tắc MySQL | Lọc NULL hoặc đặt chúng vào vị trí mong muốn một cách tường minh |
| Không lọc trực tiếp được theo alias window trong WHERE | Window function được tính sau giai đoạn WHERE của query block | Dùng CTE hoặc derived table rồi lọc ở query block ngoài |
| Truy vấn window chậm trên bảng lớn | Sort, partition lớn hoặc nhiều window ordering | Đọc EXPLAIN, xem index và giảm dữ liệu đầu vào hợp lý |

## 15. Bài thực hành: phân nhóm và đo phân bố điểm

Thực hiện trong database lab MySQL 8.0. Bài thực hành tạo bảng riêng và dùng một tập điểm nhỏ để dễ kiểm tra kết quả bằng tay.

### 15.1. Tạo bảng và nạp dữ liệu

~~~sql
CREATE TABLE lab_scores (
    student_id INT NOT NULL,
    class_id INT NOT NULL,
    score DECIMAL(5,2) NULL,
    PRIMARY KEY (student_id),
    KEY ix_lab_scores_class_score (class_id, score)
) ENGINE=InnoDB;

INSERT INTO lab_scores (student_id, class_id, score)
VALUES
    (1, 1, 10.00),
    (2, 1, 20.00),
    (3, 1, 20.00),
    (4, 1, 40.00),
    (5, 1, 50.00),
    (6, 2, 30.00),
    (7, 2, 60.00),
    (8, 2, 90.00),
    (9, 2, NULL);
~~~

Lớp 1 có năm hàng, trong đó hai học viên đồng điểm 20. Lớp 2 có ba điểm hợp lệ và một hàng NULL.

### 15.2. Bước 1 — Tính ba hàm trên cùng partition

~~~sql
SELECT
    student_id,
    score,
    NTILE(4) OVER (
        PARTITION BY class_id
        ORDER BY score, student_id
    ) AS score_bucket,
    CUME_DIST() OVER (
        PARTITION BY class_id
        ORDER BY score
    ) AS score_cume_dist,
    PERCENT_RANK() OVER (
        PARTITION BY class_id
        ORDER BY score
    ) AS score_percent_rank
FROM lab_scores
WHERE class_id = 1
ORDER BY score, student_id;
~~~

Kết quả dự kiến cho lớp 1:

| student_id | score | score_bucket | score_cume_dist | score_percent_rank |
|---:|---:|---:|---:|---:|
| 1 | 10.00 | 1 | 0.20 | 0.00 |
| 2 | 20.00 | 1 | 0.60 | 0.25 |
| 3 | 20.00 | 2 | 0.60 | 0.25 |
| 4 | 40.00 | 3 | 0.80 | 0.75 |
| 5 | 50.00 | 4 | 1.00 | 1.00 |

Giải thích vì sao hai hàng điểm 20 cùng CUME_DIST và PERCENT_RANK nhưng có thể thuộc hai bucket NTILE khác nhau.

### 15.3. Bước 2 — Đổi hướng sắp xếp

~~~sql
SELECT student_id,
       score,
       NTILE(4) OVER (
           PARTITION BY class_id
           ORDER BY score DESC, student_id
       ) AS highest_first_bucket,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score DESC
       ) AS high_to_low_cume_dist,
       PERCENT_RANK() OVER (
           PARTITION BY class_id
           ORDER BY score DESC
       ) AS high_to_low_percent_rank
FROM lab_scores
WHERE class_id = 1
ORDER BY score DESC, student_id;
~~~

Quan sát bucket 1 và giá trị phân bố khi điểm cao được xếp trước. Viết lại ý nghĩa của CUME_DIST theo thứ tự giảm dần.

### 15.4. Bước 3 — So sánh có và không có khóa phụ

~~~sql
SELECT student_id,
       score,
       NTILE(4) OVER (
           ORDER BY score
       ) AS bucket_without_tiebreaker,
       NTILE(4) OVER (
           ORDER BY score, student_id
       ) AS bucket_with_tiebreaker,
       CUME_DIST() OVER (
           ORDER BY score
       ) AS cume_dist_by_score
FROM lab_scores
WHERE class_id = 1
ORDER BY score, student_id;
~~~

So sánh tính ổn định của NTILE khi thêm khóa phụ. Trong dữ liệu mẫu, student_id xác định thứ tự hai hàng score 20; CUME_DIST vẫn xem chúng là peers vì window chỉ ORDER BY score.

### 15.5. Bước 4 — Quan sát NULL

~~~sql
SELECT student_id,
       score,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS cume_dist_with_null,
       PERCENT_RANK() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS percent_rank_with_null
FROM lab_scores
WHERE class_id = 2
ORDER BY score, student_id;
~~~

Quan sát NULL đứng đầu khi ORDER BY ASC và vẫn được tính trong tổng số hàng của partition. Sau đó loại NULL ở query block đầu vào:

~~~sql
SELECT student_id,
       score,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS cume_dist_without_null
FROM lab_scores
WHERE class_id = 2
  AND score IS NOT NULL
ORDER BY score, student_id;
~~~

So sánh mẫu số và kết quả giữa hai truy vấn.

### 15.6. Bước 5 — Lọc theo phân vị

~~~sql
WITH distribution AS (
    SELECT student_id,
           class_id,
           score,
           CUME_DIST() OVER (
               PARTITION BY class_id
               ORDER BY score
           ) AS score_cume_dist
    FROM lab_scores
    WHERE score IS NOT NULL
)
SELECT *
FROM distribution
WHERE score_cume_dist >= 0.75
ORDER BY class_id, score, student_id;
~~~

Giải thích vì sao cần CTE để lọc kết quả window và vì sao số hàng có thể không đúng chính xác 25% ở phần đuôi khi có peers.

### 15.7. Bước 6 — Đọc kế hoạch thực thi

~~~sql
EXPLAIN FORMAT=TREE
SELECT student_id,
       class_id,
       score,
       NTILE(4) OVER (
           PARTITION BY class_id
           ORDER BY score, student_id
       ) AS score_bucket,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS score_cume_dist
FROM lab_scores;
~~~

Quan sát bước sort, window evaluation và index được chọn. Thử EXPLAIN ANALYZE nếu server MySQL 8.0.18+ và giải thích số hàng thực tế. Tập lab nhỏ không đủ để kết luận hiệu năng trên dữ liệu lớn.

### 15.8. Bước 7 — Dọn bảng lab

~~~sql
DROP TABLE lab_scores;
~~~

Chỉ xóa bảng lab vừa tạo sau khi đã ghi nhận kết quả.

**Kết quả cần đạt:** tính được NTILE, CUME_DIST và PERCENT_RANK; giải thích ties và NULL; đổi hướng ORDER BY mà không nhầm ý nghĩa; lọc kết quả window qua CTE; đọc được plan cơ bản.

## 16. Nguyên tắc cần ghi nhớ

- NTILE(N) chia mỗi partition thành N bucket gần bằng nhau theo số hàng; bucket đầu có thêm hàng khi phép chia dư.
- NTILE không chia theo khoảng giá trị và có thể tách các hàng đồng hạng qua ranh giới bucket.
- Thêm khóa duy nhất vào ORDER BY của NTILE để có thứ tự gán bucket ổn định.
- CUME_DIST bằng số hàng đứng trước hoặc đồng hạng chia cho tổng số hàng trong partition.
- Với ORDER BY ASC, CUME_DIST thể hiện tỷ lệ giá trị nhỏ hơn hoặc bằng hiện tại; với DESC, diễn giải theo thứ tự giảm dần.
- PERCENT_RANK bằng (RANK - 1)/(số hàng - 1); partition một hàng trả 0.
- CUME_DIST tính đến cuối peer group; PERCENT_RANK dùng rank đầu peer group.
- Peer group được xác định bởi toàn bộ biểu thức ORDER BY của window; thêm khóa phụ có thể làm thay đổi ties.
- NULL vẫn tham gia partition và được sắp đầu khi ASC, cuối khi DESC trong MySQL; lọc hoặc sắp xếp riêng nếu nghiệp vụ yêu cầu.
- Window ORDER BY không quyết định thứ tự result set; dùng ORDER BY cuối câu truy vấn khi cần.
- Không lọc trực tiếp window function trong WHERE cùng query block; dùng CTE hoặc derived table.
- Các hàm này không dùng frame để giới hạn phạm vi như aggregate window function.
- Dùng EXPLAIN để kiểm tra sort, index và window evaluation; EXPLAIN ANALYZE thực thi truy vấn thật.

NTILE, CUME_DIST và PERCENT_RANK cùng mô tả phân bố nhưng phục vụ những cách nhìn khác nhau. Chọn NTILE khi cần nhóm có số hàng gần bằng nhau, CUME_DIST khi cần tỷ lệ tích lũy bao gồm peers và PERCENT_RANK khi cần chuẩn hóa thứ hạng. Luôn xác định partition, hướng sắp xếp, ties và NULL trước khi diễn giải kết quả.
