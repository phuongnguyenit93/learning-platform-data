# NTILE, CUME_DIST, PERCENT_RANK và phân bố dữ liệu trong Oracle Database

Khi phân tích dữ liệu, ngoài việc sắp xếp hoặc đánh số từng dòng, ta thường cần biết một bản ghi đang nằm ở vị trí nào trong phân bố của cả nhóm. Ví dụ:

- Chia nhân viên thành bốn nhóm lương có số lượng gần bằng nhau.
- Xác định doanh thu của một cửa hàng nằm ở đâu trong phân bố doanh thu của các cửa hàng.
- Tìm các sản phẩm thuộc nhóm 10% có doanh số cao nhất.
- So sánh điểm thi của một học viên với toàn bộ lớp.
- Xếp hạng khách hàng theo mức chi tiêu trong từng khu vực.

Oracle cung cấp ba analytic functions thường dùng cho các yêu cầu này:

- **NTILE(n)** chia các dòng đã sắp xếp thành n bucket (nhóm phân vị) có số lượng dòng gần bằng nhau và trả về số bucket của từng dòng.
- **CUME_DIST()** tính phân bố tích lũy của dòng trong partition, tức tỷ lệ dòng có giá trị sắp xếp nhỏ hơn hoặc bằng giá trị của dòng hiện tại theo thứ tự đã khai báo.
- **PERCENT_RANK()** tính vị trí xếp hạng tương đối của dòng, dựa trên RANK, chuẩn hóa về khoảng từ 0 đến 1.

Ba hàm đều cần một thứ tự xác định trong mệnh đề OVER, nhưng chúng trả lời những câu hỏi khác nhau. NTILE chia số lượng dòng thành các nhóm; CUME_DIST và PERCENT_RANK mô tả vị trí tương đối trong phân bố. Hiểu rõ ties (các dòng đồng hạng), NULL, PARTITION BY và cách đọc phần trăm sẽ giúp tránh diễn giải sai báo cáo.

## 1. Ba khái niệm và câu hỏi mà chúng trả lời

Giả sử có danh sách điểm của năm học viên, sắp xếp tăng dần:

| Học viên | Điểm |
|---|---:|
| An | 10 |
| Binh | 20 |
| Chi | 20 |
| Dung | 30 |
| Ha | 40 |

Có ba câu hỏi khác nhau:

1. **NTILE(4):** nếu chia năm học viên thành bốn nhóm có số người gần bằng nhau, mỗi học viên thuộc nhóm nào?
2. **CUME_DIST():** tỷ lệ học viên có điểm nhỏ hơn hoặc bằng điểm của học viên hiện tại là bao nhiêu?
3. **PERCENT_RANK():** vị trí rank của học viên hiện tại nằm ở đâu trên thang 0–1, dựa trên thứ hạng thấp nhất của nhóm đồng điểm?

Không nên gọi cả ba là “phần trăm xếp hạng” rồi dùng thay thế nhau. Chúng có quy tắc khác nhau, đặc biệt khi nhiều dòng có cùng giá trị.

## 2. NTILE: chia dòng thành các bucket gần bằng nhau

### 2.1 Cú pháp

~~~sql
NTILE(expr)
OVER (
    [PARTITION BY expr [, expr] ...]
    ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
)
~~~

Trong đó:

- expr là số bucket cần chia, phải là số nguyên dương hợp lệ.
- ORDER BY xác định thứ tự các dòng trước khi phân chia.
- PARTITION BY chia dữ liệu thành các nhóm độc lập; mỗi partition được chia bucket riêng.
- NTILE trả về số bucket bắt đầu từ 1.

Ví dụ:

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (
           ORDER BY salary, employee_id
       ) AS salary_quartile
FROM employees
ORDER BY salary, employee_id;
~~~

Truy vấn chia toàn bộ nhân viên thành bốn nhóm theo lương tăng dần. Nhóm 1 chứa các dòng có lương thấp hơn, nhóm 4 chứa các dòng có lương cao hơn theo thứ tự đã khai báo.

### 2.2 Cách phân phối số dòng

NTILE cố gắng tạo các bucket có số dòng gần bằng nhau. Nếu tổng số dòng không chia hết cho số bucket, phần dư được phân bổ lần lượt cho các bucket có số thứ tự thấp hơn.

Ví dụ có 10 dòng và NTILE(4):

| Bucket | Số dòng |
|---:|---:|
| 1 | 3 |
| 2 | 3 |
| 3 | 2 |
| 4 | 2 |

Sáu dòng đầu được phân thành hai bucket đầu, mỗi bucket có ba dòng; hai bucket còn lại có hai dòng.

Với 7 dòng và NTILE(3):

| Bucket | Số dòng |
|---:|---:|
| 1 | 3 |
| 2 | 2 |
| 3 | 2 |

Không phải mỗi bucket có cùng số dòng tuyệt đối trong mọi trường hợp. Mục tiêu là chênh lệch số dòng giữa các bucket không quá một.

### 2.3 Ví dụ NTILE với DUAL

Để quan sát cách chia nhóm, có thể tạo một tập dữ liệu nhỏ bằng UNION ALL:

~~~sql
WITH scores AS (
    SELECT 1 AS student_id, 10 AS score FROM dual
    UNION ALL SELECT 2, 20 FROM dual
    UNION ALL SELECT 3, 20 FROM dual
    UNION ALL SELECT 4, 30 FROM dual
    UNION ALL SELECT 5, 40 FROM dual
)
SELECT student_id,
       score,
       NTILE(4) OVER (
           ORDER BY score, student_id
       ) AS bucket_no
FROM scores
ORDER BY score, student_id;
~~~

Với năm dòng và bốn bucket, các bucket đầu nhận thêm dòng khi phân phối phần dư. Vì vậy kết quả có thể là:

| STUDENT_ID | SCORE | BUCKET_NO |
|---:|---:|---:|
| 1 | 10 | 1 |
| 2 | 20 | 1 |
| 3 | 20 | 2 |
| 4 | 30 | 3 |
| 5 | 40 | 4 |

Hai học viên cùng điểm 20 có thể bị đưa vào hai bucket khác nhau. NTILE chia **dòng theo vị trí**, không bảo đảm các giá trị bằng nhau luôn nằm cùng bucket.

### 2.4 Vì sao cần tie-breaker?

Nếu viết:

~~~sql
NTILE(4) OVER (ORDER BY score)
~~~

và nhiều học viên cùng điểm ở ranh giới bucket, Oracle không có thêm tiêu chí để xác định dòng nào đứng trước trong nhóm đồng điểm. Phân bổ bucket giữa các dòng hòa có thể không ổn định.

Nếu có khóa duy nhất STUDENT_ID, viết:

~~~sql
NTILE(4) OVER (
    ORDER BY score, student_id
)
~~~

Điều này tạo thứ tự xác định. Tuy nhiên, việc thêm khóa phụ cũng có nghĩa các dòng cùng điểm vẫn có thể bị tách sang bucket khác. Nếu yêu cầu nghiệp vụ là **mọi dòng cùng giá trị phải thuộc cùng nhóm**, NTILE có thể không phù hợp; hãy cân nhắc phân nhóm theo ngưỡng giá trị hoặc dùng rank/cumulative distribution.

### 2.5 NTILE với PARTITION BY

Chia nhân viên thành bốn nhóm lương riêng trong từng phòng ban:

~~~sql
SELECT department_id,
       employee_id,
       salary,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY salary, employee_id
       ) AS salary_quartile
FROM employees
ORDER BY department_id, salary, employee_id;
~~~

Mỗi DEPARTMENT_ID có cách đánh bucket bắt đầu lại từ 1. Nhân viên ở phòng ban A không ảnh hưởng số lượng hoặc thứ tự bucket của phòng ban B.

Nếu một phòng ban có ít hơn bốn nhân viên, một số số bucket sẽ không xuất hiện trong kết quả của phòng ban đó. NTILE không tự sinh dòng rỗng để lấp đầy bucket.

### 2.6 NTILE không chia theo độ rộng giá trị

Giả sử lương có các giá trị 5, 6, 7, 100, 200, 300. NTILE(3) chia số dòng gần bằng nhau, chứ không tạo các khoảng số học có cùng độ rộng như 0–100, 100–200, 200–300.

Do đó:

- NTILE(4) là chia thành bốn nhóm theo số lượng dòng.
- Chia khoảng giá trị cố định là một bài toán khác, thường dùng CASE hoặc bảng ngưỡng.
- Nếu cần ngưỡng phân vị thống kê, xem thêm PERCENTILE_CONT hoặc PERCENTILE_DISC.

## 3. CUME_DIST: phân bố tích lũy

### 3.1 Cú pháp

~~~sql
CUME_DIST()
OVER (
    [PARTITION BY expr [, expr] ...]
    ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
)
~~~

CUME_DIST không nhận đối số trong dấu ngoặc. Hàm trả về một số trong khoảng lớn hơn 0 và nhỏ hơn hoặc bằng 1.

Với một dòng r trong partition, có thể hiểu:

\[
\operatorname{CUME\_DIST}(r)
=
\frac{\text{số dòng có giá trị sort nhỏ hơn hoặc bằng giá trị của r}}
{\text{tổng số dòng trong partition}}
\]

“Nhỏ hơn hoặc bằng” được hiểu theo thứ tự của toàn bộ biểu thức ORDER BY, không chỉ một cột nếu có nhiều cột sắp xếp.

Các dòng có cùng giá trị trên tất cả biểu thức ORDER BY là peers (cùng nhóm đồng hạng) và nhận cùng CUME_DIST. Giá trị cumulative được tính đến cuối nhóm peers đó.

### 3.2 Ví dụ với điểm 10, 20, 20, 30, 40

~~~sql
WITH scores AS (
    SELECT 1 AS student_id, 10 AS score FROM dual
    UNION ALL SELECT 2, 20 FROM dual
    UNION ALL SELECT 3, 20 FROM dual
    UNION ALL SELECT 4, 30 FROM dual
    UNION ALL SELECT 5, 40 FROM dual
)
SELECT student_id,
       score,
       CUME_DIST() OVER (
           ORDER BY score
       ) AS cumulative_distribution
FROM scores
ORDER BY score, student_id;
~~~

Kết quả:

| STUDENT_ID | SCORE | CUME_DIST |
|---:|---:|---:|
| 1 | 10 | 0.20 |
| 2 | 20 | 0.60 |
| 3 | 20 | 0.60 |
| 4 | 30 | 0.80 |
| 5 | 40 | 1.00 |

Giải thích:

- Với điểm 10: có 1/5 dòng có điểm nhỏ hơn hoặc bằng 10, nên 0.20.
- Với điểm 20: có 3/5 dòng có điểm nhỏ hơn hoặc bằng 20, nên cả hai dòng điểm 20 nhận 0.60.
- Với điểm 30: có 4/5 dòng có điểm nhỏ hơn hoặc bằng 30, nên 0.80.
- Với điểm 40: có 5/5 dòng có điểm nhỏ hơn hoặc bằng 40, nên 1.00.

### 3.3 CUME_DIST biểu diễn tỷ lệ tích lũy đến nhóm hiện tại

Nếu CUME_DIST của một nhân viên là 0.80 với ORDER BY salary ASC, có nghĩa 80% số dòng trong partition có mức lương nhỏ hơn hoặc bằng mức lương của nhân viên đó. Không có nghĩa nhân viên nằm ở “top 80% lương cao nhất”.

Muốn diễn giải phía cao/thấp, phải xác định chiều ORDER BY:

- ORDER BY salary ASC: tích lũy từ lương thấp đến lương cao.
- ORDER BY salary DESC: tích lũy từ lương cao đến lương thấp.

Đổi ASC thành DESC làm thay đổi ý nghĩa của phân bố tích lũy.

### 3.4 CUME_DIST với PARTITION BY

Tính vị trí tích lũy của lương trong từng phòng ban:

~~~sql
SELECT department_id,
       employee_id,
       salary,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_cume_dist
FROM employees
ORDER BY department_id, salary, employee_id;
~~~

Mẫu số là tổng số dòng trong partition của từng phòng ban. Một nhân viên có thể có CUME_DIST 0.90 trong phòng ban nhỏ nhưng không thể so trực tiếp với 0.90 ở một phòng ban có cơ cấu nhân sự khác nếu mục tiêu là so sánh toàn công ty.

### 3.5 CUME_DIST và ties

Giá trị đồng hạng nhận cùng CUME_DIST vì hàm tính đến cuối nhóm peers. Đây là đặc điểm hữu ích khi không muốn chia một nhóm giá trị bằng nhau thành các vị trí phân bố khác nhau.

Nếu thêm khóa duy nhất vào ORDER BY:

~~~sql
CUME_DIST() OVER (
    ORDER BY score, student_id
)
~~~

thì các dòng cùng SCORE không còn peers nếu STUDENT_ID khác nhau. CUME_DIST sẽ được tính trên thứ tự chi tiết đó và có thể khác kết quả khi chỉ ORDER BY SCORE.

Chỉ thêm tie-breaker nếu việc phân biệt từng dòng là ý định nghiệp vụ. Nếu muốn giữ các giá trị bằng nhau cùng phân vị, chỉ sắp xếp theo biểu thức giá trị cần phân tích.

## 4. PERCENT_RANK: thứ hạng tương đối

### 4.1 Cú pháp và công thức

~~~sql
PERCENT_RANK()
OVER (
    [PARTITION BY expr [, expr] ...]
    ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
)
~~~

PERCENT_RANK trả về giá trị từ 0 đến 1. Công thức:

\[
\operatorname{PERCENT\_RANK}
=
\frac{\operatorname{RANK}-1}{N-1}
\]

Trong đó:

- RANK là thứ hạng của dòng theo ORDER BY, sử dụng quy tắc đồng hạng của hàm RANK.
- N là tổng số dòng trong partition.
- Nếu partition chỉ có một dòng, PERCENT_RANK trả về 0.

Với các dòng có cùng giá trị ORDER BY, RANK và PERCENT_RANK giống nhau. Sau một nhóm đồng hạng, RANK bỏ qua các vị trí tương ứng với số dòng đã hòa.

### 4.2 Ví dụ với dữ liệu điểm

~~~sql
WITH scores AS (
    SELECT 1 AS student_id, 10 AS score FROM dual
    UNION ALL SELECT 2, 20 FROM dual
    UNION ALL SELECT 3, 20 FROM dual
    UNION ALL SELECT 4, 30 FROM dual
    UNION ALL SELECT 5, 40 FROM dual
)
SELECT student_id,
       score,
       RANK() OVER (ORDER BY score) AS score_rank,
       PERCENT_RANK() OVER (
           ORDER BY score
       ) AS score_percent_rank
FROM scores
ORDER BY score, student_id;
~~~

Kết quả:

| STUDENT_ID | SCORE | SCORE_RANK | PERCENT_RANK |
|---:|---:|---:|---:|
| 1 | 10 | 1 | 0.00 |
| 2 | 20 | 2 | 0.25 |
| 3 | 20 | 2 | 0.25 |
| 4 | 30 | 4 | 0.75 |
| 5 | 40 | 5 | 1.00 |

Giải thích:

- Điểm 10 có rank 1: (1 - 1) / (5 - 1) = 0.
- Điểm 20 có rank 2: (2 - 1) / 4 = 0.25.
- Điểm 30 có rank 4 vì hai dòng điểm 20 cùng rank 2, làm vị trí rank 3 bị bỏ qua: (4 - 1) / 4 = 0.75.
- Điểm 40 có rank 5: (5 - 1) / 4 = 1.

PERCENT_RANK không phải tỷ lệ dòng có giá trị nhỏ hơn hoặc bằng dòng hiện tại. Nó chuẩn hóa thứ hạng thấp nhất của nhóm peers.

### 4.3 PERCENT_RANK với PARTITION BY

~~~sql
SELECT department_id,
       employee_id,
       salary,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees
ORDER BY department_id, salary, employee_id;
~~~

Thứ hạng được tính độc lập trong từng phòng ban. Nhân viên có mức lương thấp nhất trong mỗi partition có PERCENT_RANK bằng 0; người có rank cao nhất thường bằng 1 nếu partition có ít nhất hai dòng. Với partition chỉ có một dòng, kết quả là 0 theo quy tắc đặc biệt của hàm.

## 5. So sánh NTILE, CUME_DIST và PERCENT_RANK

Với dữ liệu 10, 20, 20, 30, 40 và thứ tự tăng dần:

| SCORE | NTILE(4) với tie-breaker | CUME_DIST | PERCENT_RANK |
|---:|---:|---:|---:|
| 10 | 1 | 0.20 | 0.00 |
| 20 | 1 | 0.60 | 0.25 |
| 20 | 2 | 0.60 | 0.25 |
| 30 | 3 | 0.80 | 0.75 |
| 40 | 4 | 1.00 | 1.00 |

Ba hàm trả lời ba câu hỏi:

| Hàm | Câu hỏi | Cách tính cốt lõi |
|---|---|---|
| NTILE(n) | Dòng thuộc bucket nào nếu chia số dòng gần đều? | Vị trí dòng sau khi sắp xếp và số bucket |
| CUME_DIST() | Bao nhiêu phần của partition có giá trị nhỏ hơn hoặc bằng giá trị hiện tại? | Số dòng đến cuối peer group / N |
| PERCENT_RANK() | Rank thấp nhất của dòng nằm ở vị trí tương đối nào từ 0 đến 1? | (RANK - 1) / (N - 1), với N=1 trả 0 |

### 5.1 NTILE có thể chia các giá trị bằng nhau

Hai dòng score 20 ở ví dụ nằm trong bucket 1 và bucket 2 do NTILE chia dòng theo vị trí. CUME_DIST và PERCENT_RANK giữ chúng cùng giá trị vì chúng là peers theo ORDER BY SCORE.

### 5.2 CUME_DIST thường lớn hơn PERCENT_RANK ở điểm giữa

Với điểm 20:

- CUME_DIST = 0.60 vì ba trên năm dòng có điểm nhỏ hơn hoặc bằng 20.
- PERCENT_RANK = 0.25 vì rank thấp nhất là 2 trong năm dòng.

Không có mâu thuẫn: hai công thức đo hai khía cạnh khác nhau.

### 5.3 Không đồng nhất NTILE(4) với tứ phân vị thống kê

NTILE(4) chia số dòng thành bốn bucket gần bằng nhau. Nó không tính ra các ngưỡng giá trị Q1, median, Q3 theo một phương pháp percentile thống kê cụ thể.

Nếu cần ngưỡng phân vị của một đại lượng, hãy xem:

- PERCENTILE_CONT: tính percentile liên tục, có thể nội suy giữa các giá trị.
- PERCENTILE_DISC: chọn một giá trị thực tế theo quy tắc phân vị rời rạc.

NTILE hữu ích cho phân nhóm tương đối đều về số dòng; PERCENTILE_CONT/DISC hữu ích khi cần ngưỡng giá trị. Chọn đúng công cụ theo câu hỏi báo cáo.

## 6. Ties và thứ tự xác định

### 6.1 Peer group được xác định bởi toàn bộ ORDER BY

Trong CUME_DIST và PERCENT_RANK, các dòng là peers khi có cùng giá trị trên tất cả biểu thức ORDER BY.

Ví dụ:

~~~sql
CUME_DIST() OVER (
    ORDER BY salary
)
~~~

Hai nhân viên cùng lương là peers.

Nhưng:

~~~sql
CUME_DIST() OVER (
    ORDER BY salary, employee_id
)
~~~

nếu EMPLOYEE_ID khác nhau thì hai nhân viên không còn peers.

Điều này có thể làm thay đổi CUME_DIST và PERCENT_RANK, không chỉ thay đổi thứ tự hiển thị.

### 6.2 Khi nào thêm khóa phụ?

Với NTILE, nếu muốn bucket assignment ổn định ở ranh giới, nên thêm khóa phụ duy nhất. Với CUME_DIST/PERCENT_RANK, chỉ thêm khóa phụ nếu muốn coi từng dòng là một thứ tự riêng, thay vì coi các giá trị bằng nhau là đồng hạng.

Một thiết kế có thể dùng hai analytic clause:

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (
           ORDER BY salary, employee_id
       ) AS stable_bucket,
       CUME_DIST() OVER (
           ORDER BY salary
       ) AS salary_cume_dist,
       PERCENT_RANK() OVER (
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees;
~~~

NTILE có tie-breaker để phân phối từng dòng ổn định; hai hàm phân bố giữ peer group theo mức lương. Đây là lựa chọn hợp lý khi hai mục tiêu khác nhau.

### 6.3 ORDER BY cuối truy vấn không thay analytic ORDER BY

~~~sql
SELECT employee_id,
       salary,
       PERCENT_RANK() OVER (
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees
ORDER BY employee_id;
~~~

PERCENT_RANK được tính theo salary. Kết quả được trình bày theo employee_id. Hai thứ tự có mục đích riêng.

## 7. NULL trong phân bố dữ liệu

### 7.1 NULL được sắp xếp theo NULLS FIRST/LAST

Oracle coi NULL là một giá trị trong quá trình sắp xếp analytic. Vị trí mặc định:

- ORDER BY ASC: NULLS LAST.
- ORDER BY DESC: NULLS FIRST.

Nên khai báo tường minh khi NULL có thể xuất hiện:

~~~sql
CUME_DIST() OVER (
    ORDER BY score ASC NULLS LAST
)
~~~

~~~sql
PERCENT_RANK() OVER (
    ORDER BY score ASC NULLS LAST
)
~~~

Với ASC NULLS LAST, các dòng score NULL nằm cuối thứ tự và tạo peer group. CUME_DIST của nhóm NULL có thể bằng 1 vì toàn bộ dòng trong partition đứng trước hoặc đồng hạng với NULL theo thứ tự đó.

### 7.2 NULL có phải là 0?

Không. NULL là giá trị thiếu/không xác định theo semantics dữ liệu, còn 0 là một số cụ thể. Nếu thay:

~~~sql
ORDER BY NVL(score, 0)
~~~

thì ta đã thay đổi thứ tự phân bố và có thể làm NULL cùng nhóm với các điểm 0. Chỉ làm vậy khi nghiệp vụ xác nhận điểm chưa có phải được coi là 0.

### 7.3 Loại NULL trước khi tính phân bố

Nếu báo cáo chỉ phân tích những bản ghi có điểm:

~~~sql
SELECT student_id,
       score,
       CUME_DIST() OVER (
           ORDER BY score
       ) AS score_cume_dist
FROM student_scores
WHERE score IS NOT NULL;
~~~

WHERE lọc NULL khỏi tập đầu vào analytic, vì vậy mẫu số N cũng chỉ tính các dòng có score không NULL.

Nếu vẫn muốn hiển thị học viên chưa có điểm nhưng không đưa họ vào phân bố, có thể tính analytic trên tập có điểm rồi LEFT JOIN kết quả về danh sách học viên đầy đủ.

### 7.4 NULL trong PARTITION BY

Các dòng có PARTITION BY key NULL được xếp chung một partition NULL theo quy tắc grouping/analytic của Oracle. Nếu dữ liệu có nhiều bản ghi thiếu DEPARTMENT_ID, các hàm phân bố theo DEPARTMENT_ID sẽ tính chúng cùng một nhóm NULL.

Nếu NULL không nên tạo thành một nhóm nghiệp vụ, lọc hoặc phân loại rõ trong nguồn dữ liệu trước khi tính analytic.

## 8. Đọc kết quả phân bố theo ASC và DESC

### 8.1 Phân bố từ thấp lên cao

~~~sql
SELECT employee_id,
       salary,
       CUME_DIST() OVER (
           ORDER BY salary ASC
       ) AS cumulative_from_low,
       PERCENT_RANK() OVER (
           ORDER BY salary ASC
       ) AS rank_from_low
FROM employees
ORDER BY salary, employee_id;
~~~

Giá trị phân bố tăng dần từ mức lương thấp đến cao. CUME_DIST cho biết tỷ lệ nhân viên có lương không vượt quá lương hiện tại.

### 8.2 Phân bố từ cao xuống thấp

~~~sql
SELECT employee_id,
       salary,
       CUME_DIST() OVER (
           ORDER BY salary DESC
       ) AS cumulative_from_high,
       PERCENT_RANK() OVER (
           ORDER BY salary DESC
       ) AS rank_from_high
FROM employees
ORDER BY salary DESC, employee_id;
~~~

Giá trị tích lũy được tính từ mức lương cao xuống thấp. Nếu cần tỷ lệ nhân viên có lương cao hơn hoặc bằng mức hiện tại, CUME_DIST với DESC có thể giúp diễn đạt mục tiêu này, nhưng phải chú ý ties và NULL ordering.

### 8.3 Không đọc nhầm 0.9

Với CUME_DIST và ORDER BY salary ASC, 0.9 nghĩa là khoảng 90% dòng có salary nhỏ hơn hoặc bằng giá trị hiện tại. Với ORDER BY salary DESC, 0.9 là tỷ lệ tích lũy theo chiều từ cao xuống thấp.

PERCENT_RANK bằng 0.9 nghĩa là rank tương đối gần cuối thứ tự đã khai báo, không trực tiếp có nghĩa 90% dòng có giá trị nhỏ hơn hoặc bằng.

Hãy ghi rõ chiều sort trong tên alias hoặc tài liệu báo cáo, ví dụ SALARY_CUME_DIST_ASC, để người đọc không phải suy đoán.

## 9. Lọc theo NTILE, CUME_DIST và PERCENT_RANK

Analytic functions được tính sau WHERE trong cùng query block. Vì vậy không thể đặt trực tiếp NTILE/CUME_DIST/PERCENT_RANK trong WHERE của chính query block đó. Hãy dùng CTE hoặc inline view.

### 9.1 Lọc nhóm bucket cao nhất

~~~sql
WITH bucketed AS (
    SELECT employee_id,
           department_id,
           salary,
           NTILE(4) OVER (
               PARTITION BY department_id
               ORDER BY salary, employee_id
           ) AS salary_bucket
    FROM employees
)
SELECT employee_id,
       department_id,
       salary,
       salary_bucket
FROM bucketed
WHERE salary_bucket = 4
ORDER BY department_id, salary DESC, employee_id;
~~~

Truy vấn lấy bucket 4 của mỗi phòng ban. Với ORDER BY salary ASC trong NTILE, bucket 4 chứa nhóm lương cao nhất theo số lượng dòng gần bằng nhau.

### 9.2 Lấy các dòng có CUME_DIST trên 0.9

~~~sql
WITH distributed AS (
    SELECT employee_id,
           salary,
           CUME_DIST() OVER (
               ORDER BY salary
           ) AS salary_cume_dist
    FROM employees
)
SELECT employee_id,
       salary,
       salary_cume_dist
FROM distributed
WHERE salary_cume_dist > 0.90
ORDER BY salary DESC, employee_id;
~~~

Với ORDER BY salary ASC, điều kiện trên lấy các peer group mà tỷ lệ tích lũy vượt 90%. Đây không nhất thiết đúng 10% số nhân viên: ties có thể làm tỷ lệ nhảy qua ngưỡng.

### 9.3 Lấy các dòng có PERCENT_RANK từ 0.9

~~~sql
WITH ranked AS (
    SELECT employee_id,
           salary,
           PERCENT_RANK() OVER (
               ORDER BY salary
           ) AS salary_percent_rank
    FROM employees
)
SELECT employee_id,
       salary,
       salary_percent_rank
FROM ranked
WHERE salary_percent_rank >= 0.90
ORDER BY salary DESC, employee_id;
~~~

Điều kiện lấy những dòng có rank tương đối ít nhất 0.90 theo thứ tự tăng dần. Do công thức dựa trên RANK và ties, số dòng thực tế có thể không đúng chính xác 10%.

### 9.4 Muốn đúng một số lượng dòng cao nhất

Nếu yêu cầu là lấy đúng 10 nhân viên có lương cao nhất, dùng ROW_NUMBER với thứ tự xác định:

~~~sql
WITH numbered AS (
    SELECT employee_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC, employee_id
           ) AS rn
    FROM employees
)
SELECT employee_id,
       salary
FROM numbered
WHERE rn <= 10
ORDER BY salary DESC, employee_id;
~~~

Nếu yêu cầu là lấy tất cả người đồng hạng ở vị trí thứ 10, cân nhắc RANK hoặc DENSE_RANK thay vì ROW_NUMBER. Đừng dùng CUME_DIST hoặc PERCENT_RANK chỉ vì muốn lấy “top 10” nếu điều kiện thực sự là một số lượng dòng chính xác.

## 10. NTILE, CUME_DIST và PERCENT_RANK sau khi tổng hợp

Các hàm có thể áp dụng trên tập dữ liệu đã GROUP BY, ví dụ xếp hạng doanh thu theo khu vực:

~~~sql
WITH regional_sales AS (
    SELECT region,
           SUM(amount) AS total_revenue
    FROM sales
    GROUP BY region
)
SELECT region,
       total_revenue,
       NTILE(4) OVER (
           ORDER BY total_revenue, region
       ) AS revenue_quartile,
       CUME_DIST() OVER (
           ORDER BY total_revenue
       ) AS revenue_cume_dist,
       PERCENT_RANK() OVER (
           ORDER BY total_revenue
       ) AS revenue_percent_rank
FROM regional_sales
ORDER BY total_revenue, region;
~~~

Trình tự logic:

1. CTE regional_sales tạo một dòng cho mỗi REGION.
2. SUM tính doanh thu từng khu vực.
3. Các analytic functions phân tích phân bố của các tổng doanh thu.

Ở đây N là số khu vực có dòng trong regional_sales, không phải số giao dịch nguồn.

### 10.1 PARTITION BY theo một chiều khác

~~~sql
WITH product_sales AS (
    SELECT region,
           product_id,
           SUM(amount) AS revenue
    FROM sales
    GROUP BY region, product_id
)
SELECT region,
       product_id,
       revenue,
       NTILE(4) OVER (
           PARTITION BY region
           ORDER BY revenue, product_id
       ) AS product_bucket,
       CUME_DIST() OVER (
           PARTITION BY region
           ORDER BY revenue
       ) AS revenue_cume_dist
FROM product_sales
ORDER BY region, revenue, product_id;
~~~

Mỗi khu vực được chia bucket và tính phân bố riêng trên các sản phẩm của chính khu vực đó.

### 10.2 Dữ liệu thiếu kỳ không tự được bổ sung

Nếu tổng hợp theo tháng, những tháng không có giao dịch có thể không xuất hiện. NTILE, CUME_DIST và PERCENT_RANK chỉ phân tích các dòng hiện có trong partition. Muốn phân bố trên mọi tháng trong một lịch đầy đủ, cần tạo/join calendar dimension trước khi tính analytic.

## 11. So sánh với RANK và DENSE_RANK

Để hiểu PERCENT_RANK, cần phân biệt RANK và DENSE_RANK:

| Hàm | Quy tắc khi có ties | Ví dụ rank cho điểm 10, 20, 20, 30 |
|---|---|---|
| ROW_NUMBER | Mỗi dòng một số thứ tự riêng | 1, 2, 3, 4 (cần tie-breaker để ổn định) |
| RANK | Cùng giá trị nhận cùng hạng; bỏ qua vị trí tiếp theo | 1, 2, 2, 4 |
| DENSE_RANK | Cùng giá trị nhận cùng hạng; không bỏ số hạng | 1, 2, 2, 3 |
| PERCENT_RANK | Chuẩn hóa RANK theo N | 0, 1/(N-1), 1/(N-1), 3/(N-1) |

PERCENT_RANK dựa trên RANK, không dựa trên DENSE_RANK. Vì vậy khoảng cách giữa các giá trị phân vị có thể tăng sau một nhóm ties.

Ví dụ với N=4:

| SCORE | RANK | DENSE_RANK | PERCENT_RANK |
|---:|---:|---:|---:|
| 10 | 1 | 1 | 0.0000 |
| 20 | 2 | 2 | 0.3333 |
| 20 | 2 | 2 | 0.3333 |
| 30 | 4 | 3 | 1.0000 |

## 12. So sánh phân vị theo số dòng và phân vị theo giá trị

Một lỗi diễn giải thường gặp là coi NTILE(4) chính là các ngưỡng Q1, median và Q3. Thực tế:

- NTILE(4) chia dòng thành bốn nhóm có kích thước gần bằng nhau.
- PERCENT_RANK/CUME_DIST mô tả vị trí tương đối của từng dòng trong phân bố đã sắp xếp.
- PERCENTILE_CONT/PERCENTILE_DISC trả về một giá trị ngưỡng phân vị theo quy tắc riêng.

Ví dụ cần ngưỡng lương phân vị thứ 90:

~~~sql
SELECT PERCENTILE_CONT(0.90)
       WITHIN GROUP (ORDER BY salary) AS p90_salary
FROM employees;
~~~

PERCENTILE_CONT có thể nội suy để trả về giá trị không nhất thiết tồn tại trong dữ liệu gốc.

~~~sql
SELECT PERCENTILE_DISC(0.90)
       WITHIN GROUP (ORDER BY salary) AS p90_salary
FROM employees;
~~~

PERCENTILE_DISC chọn một giá trị có trong tập dữ liệu theo định nghĩa phân vị rời rạc.

Hai hàm percentile này là ordered-set aggregate/hypothetical-set style syntax trong Oracle, không phải cách thay thế trực tiếp cho NTILE. Chọn:

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Chia nhân sự thành bốn nhóm gần bằng số người | NTILE(4) |
| Biết tỷ lệ tích lũy đến giá trị hiện tại | CUME_DIST |
| Biết rank tương đối theo công thức RANK | PERCENT_RANK |
| Tính ngưỡng giá trị tại phân vị 90 | PERCENTILE_CONT hoặc PERCENTILE_DISC |
| Lấy đúng 20 dòng cao nhất | ROW_NUMBER |
| Lấy tất cả dòng đồng hạng ở một vị trí | RANK hoặc DENSE_RANK tùy semantics |

## 13. NULL, ties và tính xác định trong thiết kế báo cáo

### 13.1 Xác định tập dòng trước khi tính

WHERE lọc dòng đầu vào trước analytic functions. Nếu loại nhân viên chưa có lương, mẫu số N của CUME_DIST và PERCENT_RANK giảm. Nếu giữ họ với NULLS LAST, họ tham gia partition và có thể ảnh hưởng phân bố.

Hãy quyết định rõ báo cáo đang đo:

- Tất cả nhân viên, kể cả người chưa có lương.
- Chỉ nhân viên có lương xác định.
- Nhân viên có lương, nhưng nhóm NULL được trình bày riêng.

### 13.2 Ties ở ranh giới NTILE

Nếu nhiều giá trị bằng nhau nằm ngay ranh giới bucket, NTILE có thể chia nhóm đồng giá trị. Điều này không sai theo định nghĩa chia dòng gần đều. Nếu báo cáo cần giữ ties, chọn cách phân nhóm khác.

### 13.3 CUME_DIST/PERCENT_RANK cần cùng định nghĩa peer group

Không thêm cột không liên quan vào analytic ORDER BY. Nếu thêm EMPLOYEE_ID vào PERCENT_RANK, những nhân viên cùng lương có thể bị tách thành peers khác nhau, làm thay đổi kết quả phân bố.

### 13.4 Kết quả analytic không tự đảm bảo thứ tự hiển thị

Luôn viết ORDER BY cuối câu truy vấn nếu báo cáo cần thứ tự. ORDER BY trong OVER chỉ phục vụ tính analytic function.

## 14. Hiệu năng và execution plan

### 14.1 Các hàm cần xử lý thứ tự

NTILE, CUME_DIST và PERCENT_RANK đều dựa trên thứ tự trong partition. Với dữ liệu lớn, Oracle có thể cần sắp xếp dữ liệu theo các biểu thức PARTITION BY và ORDER BY. Sort có thể sử dụng PGA hoặc TEMP tùy kích thước dữ liệu và kế hoạch.

### 14.2 Dùng cùng analytic clause khi có thể

Ví dụ:

~~~sql
SELECT employee_id,
       salary,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS cume_dist_value,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS percent_rank_value
FROM employees;
~~~

Hai hàm có cùng partition/order definition. Optimizer có thể tận dụng cùng thứ tự xử lý, nhưng không nên coi đây là cam kết plan cụ thể. Tránh thay đổi thứ tự chỉ để hy vọng dùng chung sort nếu làm đổi semantics.

### 14.3 Index có thể hỗ trợ nhưng không bảo đảm loại bỏ sort

Một index theo:

~~~sql
(department_id, salary, employee_id)
~~~

có thể hữu ích cho truy cập theo department và thứ tự lương, nhưng Oracle còn cân nhắc filter, cardinality, clustering factor, join, partitioning và chi phí đọc. Analytic functions không tự động khiến index trên các cột ORDER BY được dùng.

Không tạo index mới chỉ vì một ví dụ. Xem workload, execution plan và actual runtime trước.

### 14.4 Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id,
       department_id,
       salary,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY salary, employee_id
       ) AS salary_bucket,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_cume_dist,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN cho biết kế hoạch dự kiến, không phải phép đo runtime. Khi tuning cần xem actual cursor plan, số dòng thực tế, sort/window operations, CPU, I/O và TEMP.

## 15. Bài lab: phân bố lương nhân viên

Các lệnh trong phần này dành cho schema thực hành riêng có quyền tạo bảng và quota phù hợp. Không chạy DDL/DML thử nghiệm trên schema production. Oracle DDL như CREATE TABLE có implicit commit.

### 15.1 Tạo bảng

~~~sql
CREATE TABLE lab_employee_scores (
    employee_id   NUMBER PRIMARY KEY,
    department_id NUMBER NOT NULL,
    employee_name VARCHAR2(60) NOT NULL,
    score         NUMBER(6,2)
);
~~~

### 15.2 Nạp dữ liệu

~~~sql
INSERT INTO lab_employee_scores VALUES (1, 10, 'An', 10);
INSERT INTO lab_employee_scores VALUES (2, 10, 'Binh', 20);
INSERT INTO lab_employee_scores VALUES (3, 10, 'Chi', 20);
INSERT INTO lab_employee_scores VALUES (4, 10, 'Dung', 30);
INSERT INTO lab_employee_scores VALUES (5, 10, 'Ha', 40);
INSERT INTO lab_employee_scores VALUES (6, 20, 'Lan', 50);
INSERT INTO lab_employee_scores VALUES (7, 20, 'Minh', 60);
INSERT INTO lab_employee_scores VALUES (8, 20, 'Nam', 60);
INSERT INTO lab_employee_scores VALUES (9, 20, 'Oanh', 80);
INSERT INTO lab_employee_scores VALUES (10, 20, 'Phuc', NULL);
COMMIT;
~~~

Department 10 có năm học viên/nhân viên với hai dòng cùng điểm 20. Department 20 có năm dòng, trong đó hai dòng cùng điểm 60 và một điểm NULL.

### 15.3 So sánh ba hàm trong cùng truy vấn

~~~sql
SELECT department_id,
       employee_id,
       employee_name,
       score,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY score ASC NULLS LAST, employee_id
       ) AS score_bucket,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY score ASC NULLS LAST
       ) AS score_cume_dist,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY score ASC NULLS LAST
       ) AS score_percent_rank
FROM lab_employee_scores
ORDER BY department_id, score ASC NULLS LAST, employee_id;
~~~

Quan sát:

- Bucket bắt đầu lại từ 1 trong từng department.
- Hai dòng cùng score có thể được NTILE phân vào bucket khác nhau do có employee_id tie-breaker.
- CUME_DIST và PERCENT_RANK giữ cùng kết quả cho các dòng đồng điểm vì analytic ORDER BY của chúng chỉ dùng SCORE.
- Điểm NULL nằm cuối partition theo NULLS LAST và tham gia phân bố.

### 15.4 So sánh có và không có tie-breaker

~~~sql
SELECT employee_id,
       score,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY score
       ) AS bucket_without_tiebreaker,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY score, employee_id
       ) AS bucket_with_tiebreaker,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY score
       ) AS cume_dist_by_score,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY score, employee_id
       ) AS cume_dist_by_score_and_id
FROM lab_employee_scores
WHERE department_id = 10
ORDER BY score, employee_id;
~~~

Truy vấn giúp quan sát việc thêm EMPLOYEE_ID không chỉ quyết định dòng nào đứng trước trong NTILE mà còn làm thay đổi peer groups của CUME_DIST.

### 15.5 Chỉ phân tích người đã có điểm

~~~sql
SELECT department_id,
       employee_id,
       score,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY score
       ) AS cume_dist_known_scores,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY score
       ) AS percent_rank_known_scores
FROM lab_employee_scores
WHERE score IS NOT NULL
ORDER BY department_id, score, employee_id;
~~~

WHERE loại dòng NULL trước khi analytic được tính. Mẫu số của mỗi partition chỉ gồm nhân viên có điểm.

### 15.6 Lọc bucket cao nhất

~~~sql
WITH bucketed AS (
    SELECT department_id,
           employee_id,
           employee_name,
           score,
           NTILE(4) OVER (
               PARTITION BY department_id
               ORDER BY score, employee_id
           ) AS score_bucket
    FROM lab_employee_scores
    WHERE score IS NOT NULL
)
SELECT department_id,
       employee_id,
       employee_name,
       score
FROM bucketed
WHERE score_bucket = 4
ORDER BY department_id, score DESC, employee_id;
~~~

Truy vấn lấy bucket 4 theo từng department, bỏ điểm NULL trước khi chia nhóm.

### 15.7 Dọn bảng lab

Chỉ xóa bảng do bạn tạo trong schema thực hành nếu đã xác nhận không còn cần dữ liệu. Không đưa DROP TABLE vào script có thể chạy nhầm production; DDL có implicit commit và không thể trông chờ ROLLBACK để khôi phục.

## 16. Lỗi và ngộ nhận thường gặp

| Lỗi/ngộ nhận | Thực tế | Cách xử lý |
|---|---|---|
| NTILE(4) chia khoảng giá trị bằng nhau | NTILE chia số dòng gần bằng nhau | Dùng ngưỡng/percentile nếu cần khoảng giá trị |
| NTILE luôn giữ ties trong cùng bucket | Có thể tách giá trị bằng nhau ở ranh giới | Chọn cách phân nhóm theo giá trị nếu cần |
| Bucket luôn có số dòng bằng nhau | Khi N không chia hết, bucket đầu có thêm dòng | Tính trước kích thước bucket |
| CUME_DIST là rank/(N-1) | Đó là dạng công thức của PERCENT_RANK với RANK | Dùng đúng công thức từng hàm |
| PERCENT_RANK là tỷ lệ dòng <= giá trị | CUME_DIST mới mô tả tỷ lệ tích lũy đến peer group | Đọc công thức |
| PERCENT_RANK luôn lớn hơn 0 | Dòng có rank 1 trả 0; partition một dòng cũng trả 0 | Ghi nhớ biên 0 và 1 |
| CUME_DIST có thể bằng 0 | Giá trị luôn lớn hơn 0 và không vượt 1 | Kiểm tra mẫu số và peer group |
| Thêm khóa phụ không ảnh hưởng phân bố | Có thể phá peer group và đổi CUME_DIST/PERCENT_RANK | Chỉ thêm khi muốn phân biệt ties |
| ORDER BY ngoài điều khiển analytic | ORDER BY trong OVER mới quyết định tính toán | Phân biệt hai ORDER BY |
| NULL tự động bị bỏ qua | NULL được sắp xếp theo NULLS FIRST/LAST | Lọc rõ nếu không muốn tính NULL |
| NTILE/CUME_DIST dùng được trong WHERE cùng query block | Analytic được tính sau WHERE | Dùng CTE hoặc inline view |
| NTILE(4) là tứ phân vị thống kê | Nó là chia bốn nhóm gần đều theo số dòng | Dùng PERCENTILE_CONT/DISC khi cần ngưỡng |
| Gắn PARTITION BY không ảnh hưởng mẫu số | Mỗi partition có N riêng | Kiểm tra cấp phân tích |

## 17. Checklist diễn giải kết quả phân bố

Trước khi công bố một báo cáo dùng ba hàm này, hãy xác định:

1. Tập dòng nào được đưa vào analytic? WHERE có loại NULL hoặc trạng thái nào không?
2. Partition là toàn bộ dữ liệu hay từng phòng ban/khu vực/khách hàng?
3. ORDER BY tăng hay giảm? Phần trăm được tích lũy từ đầu nào?
4. Có ties không? Các dòng đồng giá trị có cần giữ cùng peer group không?
5. NTILE cần chia số lượng dòng gần đều hay nhóm theo ngưỡng giá trị?
6. Nếu dùng NTILE, phần dư sẽ làm bucket đầu có thêm dòng; điều này có phù hợp không?
7. CUME_DIST đang biểu diễn tỷ lệ dòng đến cuối peer group hay người đọc đang nhầm với percentile rank?
8. PERCENT_RANK đang dựa trên RANK; partition một dòng trả 0.
9. NULL được giữ, loại bỏ hay đặt đầu/cuối?
10. Có cần thêm khóa phụ cho thứ tự ổn định không, và việc đó có làm thay đổi peer groups không?
11. Nếu lọc kết quả analytic, đã dùng CTE/inline view chưa?
12. Nếu cần ngưỡng percentile, đã chọn PERCENTILE_CONT/DISC thay vì NTILE chưa?

## 18. Bài tập tự luyện

**Câu 1 — Chia bucket.** Có 11 dòng và NTILE(4). Số dòng trong bốn bucket lần lượt là bao nhiêu?

Gợi ý: Chia cơ sở 2 dòng mỗi bucket, phần dư 3 dòng được thêm lần lượt vào bucket 1, 2 và 3: 3, 3, 3, 2.

**Câu 2 — CUME_DIST.** Một partition có giá trị 10, 20, 20, 30, 40. CUME_DIST của giá trị 20 là bao nhiêu?

Gợi ý: Ba trên năm dòng có giá trị nhỏ hơn hoặc bằng 20, nên bằng 0.60.

**Câu 3 — PERCENT_RANK.** Với cùng dữ liệu, PERCENT_RANK của hai dòng điểm 20 là bao nhiêu?

Gợi ý: RANK=2 và N=5, nên (2-1)/(5-1)=0.25.

**Câu 4 — Ties.** Vì sao hai dòng cùng điểm có thể ở hai bucket NTILE khác nhau nhưng có cùng CUME_DIST?

Gợi ý: NTILE chia từng dòng theo vị trí; CUME_DIST trả cùng giá trị cho peer group.

**Câu 5 — Tie-breaker.** Nếu thêm STUDENT_ID vào ORDER BY của CUME_DIST, điều gì có thể thay đổi?

Gợi ý: Các dòng cùng điểm nhưng khác ID không còn peers; CUME_DIST được tính theo thứ tự chi tiết hơn.

**Câu 6 — Partition.** Tính CUME_DIST theo DEPARTMENT_ID khác gì tính trên toàn công ty?

Gợi ý: Mẫu số và tập dòng tích lũy được tính riêng trong từng phòng ban.

**Câu 7 — NULL.** Với ORDER BY SCORE ASC NULLS LAST, nhóm SCORE NULL nằm ở đâu trong phân bố?

Gợi ý: Cuối thứ tự; nhóm NULL có thể nhận CUME_DIST bằng 1 vì mọi dòng đều đứng trước hoặc đồng hạng với nó.

**Câu 8 — Lọc analytic.** Viết truy vấn lấy các dòng có PERCENT_RANK lớn hơn hoặc bằng 0.9.

Gợi ý: Tính PERCENT_RANK trong CTE rồi lọc ở query block ngoài.

**Câu 9 — Ngưỡng percentile.** Muốn biết mức lương P90 bằng một giá trị tiền cụ thể, nên dùng NTILE(10) hay PERCENTILE_CONT(0.90)?

Gợi ý: PERCENTILE_CONT phù hợp để tính ngưỡng giá trị liên tục; NTILE chia dòng thành nhóm gần đều.

**Câu 10 — Đúng 10 dòng.** Muốn lấy chính xác 10 nhân viên lương cao nhất, nên dùng hàm nào?

Gợi ý: ROW_NUMBER với ORDER BY salary DESC và khóa phụ duy nhất.

## 19. Tổng kết

NTILE, CUME_DIST và PERCENT_RANK đều là analytic functions dùng để phân tích vị trí tương đối của dòng trong một tập dữ liệu đã sắp xếp, nhưng ý nghĩa khác nhau:

- **NTILE(n)** chia số dòng thành n bucket gần bằng nhau. Bucket đầu nhận thêm dòng khi tổng số dòng không chia hết cho n. Các dòng đồng giá trị có thể bị tách ở ranh giới.
- **CUME_DIST()** trả tỷ lệ tích lũy đến cuối nhóm peers của dòng hiện tại: số dòng nhỏ hơn hoặc bằng theo thứ tự / tổng số dòng trong partition. Các peers nhận cùng kết quả.
- **PERCENT_RANK()** chuẩn hóa RANK theo công thức (RANK - 1) / (N - 1); dòng rank 1 nhận 0 và partition một dòng cũng nhận 0.

Để sử dụng chính xác:

- Dùng PARTITION BY khi cần phân bố riêng cho từng nhóm nghiệp vụ.
- Chọn ORDER BY đúng chiều; ASC và DESC thay đổi cách đọc phân bố.
- Chỉ thêm tie-breaker khi mục tiêu cần thứ tự từng dòng ổn định; với CUME_DIST/PERCENT_RANK, thêm cột có thể phá peer group.
- Xác định NULL có tham gia phân bố hay không và khai báo NULLS FIRST/LAST rõ ràng.
- Dùng CTE hoặc inline view để lọc kết quả analytic.
- Phân biệt chia bucket theo số dòng với tính ngưỡng percentile theo giá trị.

Khi hiểu rõ những khác biệt này, báo cáo có thể phân nhóm dữ liệu, mô tả phân bố và chọn các giá trị ở vùng cao/thấp mà không nhầm bucket với percentile hoặc thứ hạng tương đối.
