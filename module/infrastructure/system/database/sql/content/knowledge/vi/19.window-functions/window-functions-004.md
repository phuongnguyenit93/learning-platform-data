# NTILE, PERCENT_RANK và CUME_DIST

## 1. Ba hàm cửa sổ trả lời ba câu hỏi khác nhau

Trong báo cáo SQL, nhiều khi chỉ lấy điểm, doanh thu hay số lượng là chưa đủ. Ta còn muốn biết **một giá trị đang nằm ở đâu so với những giá trị khác**:

- “Chia toàn bộ nhân viên thành bốn nhóm doanh số có số người gần bằng nhau.”
- “Một học viên có vị trí xếp hạng tương đối bao nhiêu trong lớp?”
- “Tính đến mức điểm này, đã có bao nhiêu phần trăm học viên đạt điểm từ mức đó trở lên?”

Ba nhu cầu này dẫn tới ba hàm cửa sổ (*window functions*) thường gặp:

| Hàm | Câu hỏi chính | Giá trị trả về |
| --- | --- | --- |
| `NTILE(k)` | Nếu xếp hàng theo thứ tự rồi chia thành `k` nhóm có số hàng gần bằng nhau, hàng này thuộc nhóm mấy? | Số nguyên từ `1` tới tối đa `k` |
| `PERCENT_RANK()` | Vị trí **thứ hạng tương đối** của hàng trong phân vùng là bao nhiêu? | Số từ `0` đến `1` |
| `CUME_DIST()` | Tỷ lệ **tích lũy số hàng** có vị trí xếp trước hoặc ngang hàng này là bao nhiêu? | Số lớn hơn `0` và không quá `1` |

Cả ba dùng cú pháp `OVER (...)`. Chúng **không thu gọn** cả nhóm thành một hàng như `GROUP BY`, mà thường giữ nguyên từng hàng đầu vào và **bổ sung cột tính toán**.

Ví dụ chung:

~~~sql
SELECT
    student_id,
    score,
    NTILE(4) OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC, student_id
    ) AS score_quartile,
    PERCENT_RANK() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS percent_rank,
    CUME_DIST() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS cume_dist
FROM exam_scores;
~~~

Ba hàm nhìn giống nhau vì đều dựa trên thứ tự, nhưng **cách xử lý thứ hạng, số lượng hàng và giá trị bằng nhau rất khác**. Đặc biệt, `NTILE` có thể chia hai hàng **cùng điểm** vào **hai bucket khác nhau**, trong khi `PERCENT_RANK` và `CUME_DIST` thường trả **cùng giá trị cho các hàng đồng hạng** theo `ORDER BY` của chính chúng.

Trong bài này, `ORDER BY score DESC` nghĩa là **điểm cao đứng trước**. Vì vậy `NTILE(4) = 1` là nhóm điểm đứng đầu; còn giá trị `PERCENT_RANK` **nhỏ** hoặc `CUME_DIST` **nhỏ** lại chỉ ra vị trí gần đầu danh sách, không phải “phần trăm điểm cao”.

## 2. Chuẩn bị dữ liệu có đồng điểm và nhóm có kích thước khác nhau

Tạo bảng `exam_scores` lưu điểm của ba nhóm học viên: `A` có 8 người, `B` có 5 người và `C` có 1 người.

Các ví dụ chính dùng SQL có hỗ trợ hàm cửa sổ như PostgreSQL, MySQL 8+, SQL Server, Oracle hoặc SQLite phiên bản hỗ trợ window functions. Một số cú pháp DDL có thể cần điều chỉnh nhẹ theo DBMS.

~~~sql
CREATE TABLE exam_scores (
    student_id   INTEGER PRIMARY KEY,
    student_name VARCHAR(60) NOT NULL,
    cohort_code  VARCHAR(10) NOT NULL,
    score        INTEGER NOT NULL,
    CONSTRAINT chk_exam_score
        CHECK (score BETWEEN 0 AND 100)
);

INSERT INTO exam_scores (
    student_id, student_name, cohort_code, score
)
VALUES
    (101, 'An',    'A', 95),
    (102, 'Binh',  'A', 90),
    (103, 'Chi',   'A', 90),
    (104, 'Dung',  'A', 80),
    (105, 'Ha',    'A', 75),
    (106, 'Lan',   'A', 75),
    (107, 'Minh',  'A', 60),
    (108, 'Nam',   'A', 40),
    (201, 'Hoa',   'B', 88),
    (202, 'Khanh', 'B', 88),
    (203, 'Linh',  'B', 70),
    (204, 'Phong', 'B', 65),
    (205, 'Quynh', 'B', 50),
    (301, 'Trang', 'C', 77);
~~~

Một câu truy vấn chỉ để xem dữ liệu theo thứ tự:

~~~sql
SELECT
    cohort_code,
    student_id,
    student_name,
    score
FROM exam_scores
ORDER BY cohort_code, score DESC, student_id;
~~~

| Nhóm | Mã | Tên | Điểm |
| --- | ---: | --- | ---: |
| A | 101 | An | 95 |
| A | 102 | Binh | 90 |
| A | 103 | Chi | 90 |
| A | 104 | Dung | 80 |
| A | 105 | Ha | 75 |
| A | 106 | Lan | 75 |
| A | 107 | Minh | 60 |
| A | 108 | Nam | 40 |
| B | 201 | Hoa | 88 |
| B | 202 | Khanh | 88 |
| B | 203 | Linh | 70 |
| B | 204 | Phong | 65 |
| B | 205 | Quynh | 50 |
| C | 301 | Trang | 77 |

Bộ dữ liệu cố ý có các trường hợp:

1. **Điểm trùng:** Binh và Chi cùng 90, Ha và Lan cùng 75, Hoa và Khanh cùng 88.
2. **Nhóm không chia hết:** nhóm B có 5 người nhưng có thể phải chia 4 bucket.
3. **Nhóm ít hơn số bucket:** nhóm C chỉ có 1 người.
4. **Khác biệt giữa các phân vùng:** cùng một điểm có thể có vị trí khác nhau nếu đánh giá trong lớp riêng hoặc trên toàn bộ học viên.

Tất cả ví dụ bên dưới dùng **dữ liệu ban đầu này**, trừ khi một mục nói rõ đang xét dữ liệu giả định khác.

## 3. Ôn lại OVER, PARTITION BY và ORDER BY

Một hàm cửa sổ thường có dạng:

~~~sql
<ten_ham>(<tham_so_neu_co>) OVER (
    PARTITION BY <cot_chia_nhom>
    ORDER BY <cot_sap_xep> ASC|DESC
)
~~~

### PARTITION BY: so sánh trong phạm vi nào?

~~~sql
PARTITION BY cohort_code
~~~

chia các hàng thành những **phân vùng tính toán độc lập**:

~~~text
Cohort A: 8 học viên
Cohort B: 5 học viên
Cohort C: 1 học viên

Mỗi phân vùng tự tính NTILE / PERCENT_RANK / CUME_DIST.
~~~

`PARTITION BY` không giống `GROUP BY`:

- `GROUP BY` thường gom nhiều hàng thành **một hàng cho mỗi nhóm** khi tổng hợp.
- `PARTITION BY` trong `OVER` giữ **hàng học viên riêng lẻ**, chỉ xác định phạm vi để hàm cửa sổ tính trên các hàng liên quan.

Nếu bỏ `PARTITION BY`:

~~~sql
NTILE(4) OVER (ORDER BY score DESC, student_id)
~~~

thì toàn bộ **14 học viên** được xếp chung, không còn chia riêng từng nhóm. Kết quả sẽ có ý nghĩa “vị trí trên toàn bộ kỳ thi”, khác với “vị trí trong nhóm học”.

### ORDER BY trong OVER: xác định thứ tự nào?

Với:

~~~sql
ORDER BY score DESC
~~~

điểm **cao trước, thấp sau**. Khi đổi thành `ASC`, hàm sẽ xem **điểm thấp đứng trước**.

Ba hàm trong bài đều cần hiểu rõ thứ tự mà chúng đang sử dụng. Cùng một tập dữ liệu nhưng đổi `DESC` thành `ASC` có thể đảo hẳn ý nghĩa của bucket và tỷ lệ phân bố.

### ORDER BY trong OVER không thay ORDER BY cuối câu SELECT

Ví dụ:

~~~sql
SELECT
    student_id,
    score,
    NTILE(4) OVER (ORDER BY score DESC, student_id) AS bucket
FROM exam_scores;
~~~

Không có `ORDER BY` ở truy vấn **ngoài cùng**, DBMS **không cam kết** các hàng được hiển thị theo thứ tự điểm, dù hàm đã tính bucket theo điểm.

Muốn đầu ra ổn định, viết:

~~~sql
SELECT
    student_id,
    score,
    NTILE(4) OVER (ORDER BY score DESC, student_id) AS bucket
FROM exam_scores
ORDER BY score DESC, student_id;
~~~

Có hai ý nghĩa riêng:

- `ORDER BY` bên trong `OVER` quyết định **kết quả phân tích**.
- `ORDER BY` cuối câu quyết định **thứ tự hiển thị hàng**.

## 4. NTILE(k): chia danh sách đã sắp xếp thành k bucket

### 4.1. Cú pháp

~~~sql
NTILE(4) OVER (
    PARTITION BY cohort_code
    ORDER BY score DESC, student_id ASC
)
~~~

`NTILE(4)` cố gắng chia mỗi phân vùng thành **4 nhóm có số hàng gần bằng nhau**. Các nhóm được đánh số bắt đầu từ **1** theo thứ tự đã chọn.

Chẳng hạn, nhóm A có 8 người. Chia thành 4 bucket:

~~~text
Thứ tự giảm dần điểm — nhóm A:

Vị trí     1    2  |  3    4  |  5    6  |  7    8
Học viên   101  102 |  103  104 |  105  106 |  107  108
Điểm        95   90 |   90   80 |   75   75 |   60   40
Bucket       1    1 |    2    2 |    3    3 |    4    4
~~~

Ví dụ SQL:

~~~sql
SELECT
    student_id,
    student_name,
    score,
    NTILE(4) OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC, student_id ASC
    ) AS bucket4
FROM exam_scores
WHERE cohort_code = 'A'
ORDER BY score DESC, student_id;
~~~

| Mã | Tên | Điểm | bucket4 |
| ---: | --- | ---: | ---: |
| 101 | An | 95 | 1 |
| 102 | Binh | 90 | 1 |
| 103 | Chi | 90 | 2 |
| 104 | Dung | 80 | 2 |
| 105 | Ha | 75 | 3 |
| 106 | Lan | 75 | 3 |
| 107 | Minh | 60 | 4 |
| 108 | Nam | 40 | 4 |

**Điểm rất quan trọng:** Binh và Chi **cùng 90 điểm** nhưng thuộc **hai bucket khác nhau**. `NTILE` chia theo **vị trí của các hàng đã sắp**, không cam kết giữ nguyên nhóm đồng điểm.

Trong ví dụ, `student_id ASC` là **khóa phá hòa** để thứ tự giữa các học viên cùng điểm xác định được. Nếu bỏ `student_id` khỏi `ORDER BY` của `NTILE`, hệ có thể chọn thứ tự bất kỳ giữa Binh và Chi, dẫn đến người nằm ở bucket 1 hoặc 2 thay đổi khi kế hoạch thực thi đổi.

### 4.2. Số hàng ở các bucket khác nhau như thế nào?

Giả sử một phân vùng có `N` hàng và yêu cầu `k` bucket, với `k` là số nguyên dương.

Khi `N >= k`, đặt:

\[
q=\left\lfloor\frac{N}{k}\right\rfloor,\qquad r=N\bmod k
\]

Khi đó:

- `r` bucket **đầu tiên** có `q + 1` hàng.
- `k - r` bucket còn lại có `q` hàng.
- Chênh lệch kích thước giữa các bucket không vượt quá 1 hàng.

Ví dụ nhóm B có `N = 5`, `k = 4`:

~~~text
5 = 4 × 1 + 1

Bucket 1: 2 người
Bucket 2: 1 người
Bucket 3: 1 người
Bucket 4: 1 người
~~~

Truy vấn:

~~~sql
SELECT
    student_id,
    student_name,
    score,
    NTILE(4) OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC, student_id
    ) AS bucket4
FROM exam_scores
WHERE cohort_code = 'B'
ORDER BY score DESC, student_id;
~~~

| Mã | Tên | Điểm | bucket4 |
| ---: | --- | ---: | ---: |
| 201 | Hoa | 88 | 1 |
| 202 | Khanh | 88 | 1 |
| 203 | Linh | 70 | 2 |
| 204 | Phong | 65 | 3 |
| 205 | Quynh | 50 | 4 |

Bucket đầu có hai hàng, những bucket sau có một hàng. Không có chuyện bucket cuối phải chứa thêm hàng để “cân” khi dư một hàng: **phần dư được phân bổ từ bucket đầu**.

### 4.3. Khi số bucket lớn hơn số hàng

Nhóm C chỉ có một học viên. Với `NTILE(4)`:

~~~sql
SELECT
    student_id,
    score,
    NTILE(4) OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC, student_id
    ) AS bucket4
FROM exam_scores
WHERE cohort_code = 'C';
~~~

Kết quả: Trang, mã `301`, có `bucket4 = 1`.

Mặc dù yêu cầu 4 bucket, dữ liệu chỉ có một hàng nên **chỉ xuất hiện nhãn bucket 1** trong kết quả; không có hàng để mang nhãn 2, 3, 4. Tương tự, nếu một phân vùng có 3 hàng và `NTILE(10)`, các nhãn xuất hiện chỉ là `1, 2, 3`.

**`NTILE(k)` không tự tạo những hàng rỗng cho các bucket không có người.** Nếu một báo cáo cần hiện cả các bucket chưa có dữ liệu, phải tạo bảng danh mục bucket hoặc một tập số riêng, rồi nối với kết quả đã tính.

### 4.4. NTILE(3) và NTILE(4) chia khác nhau

Với nhóm A có 8 hàng:

| Bucket | `NTILE(3)` | `NTILE(4)` |
| --- | --- | --- |
| 1 | 3 hàng: 101, 102, 103 | 2 hàng: 101, 102 |
| 2 | 3 hàng: 104, 105, 106 | 2 hàng: 103, 104 |
| 3 | 2 hàng: 107, 108 | 2 hàng: 105, 106 |
| 4 | Không có vì chỉ có 3 bucket | 2 hàng: 107, 108 |

`NTILE(3)` thường được gọi là chia ba nhóm (terciles) theo thứ tự hàng; `NTILE(4)` thường là bốn nhóm (quartiles); `NTILE(10)` là mười nhóm (deciles). Những tên gọi này nói về **nhóm hàng có kích thước gần bằng nhau**, không phải phép tính giá trị phân vị nội suy của điểm số.

### 4.5. Tham số k phải hợp lệ

`NTILE(0)` hoặc `NTILE(-2)` không có ý nghĩa: số bucket phải là **số nguyên dương** theo quy tắc DBMS. Việc dùng biểu thức, tham số động, kiểu số lớn hoặc giá trị `NULL` làm `k` có thể bị giới hạn khác nhau giữa các hệ quản trị.

Khi client/API cho phép người dùng chọn `k`, hãy **xác thực k > 0**, đặt giới hạn tối đa hợp lý và truyền tham số theo cơ chế an toàn của driver. Không xây SQL bằng cách ghép chuỗi trực tiếp từ input không tin cậy.

## 5. PERCENT_RANK(): vị trí thứ hạng tương đối

### 5.1. Công thức

`PERCENT_RANK()` không nhận tham số trong dấu ngoặc. Nó tính từ **`RANK()` của hàng** trong cùng phân vùng:

\[
\operatorname{PERCENT\_RANK}
=\frac{\operatorname{RANK}-1}{N-1},\qquad N>1
\]

Trong đó:

- `N` là tổng số hàng của **phân vùng**.
- `RANK` là thứ hạng của hàng theo `ORDER BY` trong `OVER`.
- Khi một phân vùng chỉ có **một hàng** (`N = 1`), `PERCENT_RANK()` trả **0** thay vì thực hiện phép chia cho 0.

`RANK()` gán cùng thứ hạng cho các hàng **bằng nhau theo tất cả biểu thức `ORDER BY`** rồi để trống những vị trí mà đồng hạng đã chiếm. Ví dụ điểm A:

~~~text
Điểm:         95  90  90  80  75  75  60  40
RANK():        1   2   2   4   5   5   7   8
PERCENT_RANK:  0  1/7 1/7 3/7 4/7 4/7 6/7  1
~~~

Đây là lý do dùng `RANK()` chứ **không phải `ROW_NUMBER()` hoặc `DENSE_RANK()`** để suy ra `PERCENT_RANK()`.

### 5.2. Ví dụ tính chi tiết ở nhóm A

~~~sql
SELECT
    student_id,
    student_name,
    score,
    RANK() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS score_rank,
    PERCENT_RANK() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS percent_rank
FROM exam_scores
WHERE cohort_code = 'A'
ORDER BY score DESC, student_id;
~~~

Kết quả (làm tròn giá trị hiển thị đến 6 chữ số):

| Mã | Điểm | score_rank | percent_rank |
| ---: | ---: | ---: | ---: |
| 101 | 95 | 1 | 0.000000 |
| 102 | 90 | 2 | 0.142857 |
| 103 | 90 | 2 | 0.142857 |
| 104 | 80 | 4 | 0.428571 |
| 105 | 75 | 5 | 0.571429 |
| 106 | 75 | 5 | 0.571429 |
| 107 | 60 | 7 | 0.857143 |
| 108 | 40 | 8 | 1.000000 |

Nhóm A có `N = 8` nên mẫu số là `N - 1 = 7`. Với điểm 80:

\[
\frac{\operatorname{RANK}-1}{N-1}
=\frac{4-1}{8-1}
=\frac{3}{7}
\approx0.428571
\]

Với hai học viên 90 điểm, `RANK = 2` cho cả hai:

\[
\frac{2-1}{8-1}=\frac{1}{7}\approx0.142857
\]

**Không được diễn giải `0.142857` là “học viên được 14,29% số điểm”.** Đây là vị trí **thứ hạng tương đối** trong danh sách đã sắp giảm dần, tính theo công thức của `RANK`.

### 5.3. Ý nghĩa của số 0 và số 1

Với `ORDER BY score DESC`:

- Học viên ở vị trí hạng 1 có `PERCENT_RANK = 0`.
- Học viên có điểm thấp nhất **mà không đồng hạng ở đáy** có thể có `PERCENT_RANK = 1`.
- Các học viên đồng điểm nhận **cùng `PERCENT_RANK`**, vì có cùng `RANK`.
- Khi **tất cả hàng có cùng điểm**, mọi hàng có `RANK = 1` nên `PERCENT_RANK = 0`.
- Với **một hàng duy nhất**, kết quả cũng là `0`.

Điều ít trực giác: **PERCENT_RANK không bắt buộc có hàng đạt đúng 1** nếu các hàng điểm thấp nhất cùng hạng.

Ví dụ giả định có bốn điểm theo thứ tự giảm dần:

~~~text
Điểm:          90   80   70   70
RANK:           1    2    3    3
PERCENT_RANK:   0  1/3  2/3  2/3
~~~

Giá trị cao nhất trong cột percent_rank là `2/3`, không phải `1`. Nguyên nhân: hai hàng điểm thấp nhất có cùng `RANK = 3`, không có hàng nào có `RANK = 4`.

### 5.4. Đổi ASC làm đổi cách diễn giải

Nếu viết:

~~~sql
PERCENT_RANK() OVER (
    PARTITION BY cohort_code
    ORDER BY score ASC
)
~~~

thì điểm **thấp nhất** có `PERCENT_RANK = 0`, còn thứ hạng tương đối tăng dần theo mức điểm. Do đó câu hỏi “phần trăm xếp hạng của học viên” **chưa đủ rõ** nếu không nêu xếp **từ điểm thấp lên cao** hay **từ cao xuống thấp**.

Ví dụ một màn hình hiển thị “percentile score cao hơn là tốt hơn” có thể chọn `ORDER BY score ASC` và sau đó chú thích rõ giá trị là **vị trí thứ hạng tương đối**, không tự coi là “phần trăm học viên bị vượt qua” trong mọi tình huống có đồng điểm.

## 6. CUME_DIST(): phân phối tích lũy theo thứ tự

### 6.1. Công thức và ý nghĩa

`CUME_DIST()` là viết tắt của **cumulative distribution**. Với một hàng trong phân vùng `N` hàng:

\[
\operatorname{CUME\_DIST}
=\frac{\text{số hàng đứng trước hoặc đồng hạng với hàng hiện tại}}{N}
\]

Nếu `ORDER BY score DESC`, “đứng trước hoặc đồng hạng” là những hàng có điểm **lớn hơn hoặc bằng** điểm hiện tại. Do đó:

\[
\operatorname{CUME\_DIST}(x)
=\frac{\#\{\text{hàng có score}\ge x\}}{N}
\]

Với `ORDER BY score ASC`, chiều ngược lại:

\[
\operatorname{CUME\_DIST}(x)
=\frac{\#\{\text{hàng có score}\le x\}}{N}
\]

Hai công thức minh họa này giả định `score` là khóa `ORDER BY` duy nhất và không `NULL` như bảng mẫu. Nếu thứ tự có nhiều biểu thức hoặc có `NULL`, phải xét chính **quan hệ thứ tự và đồng hạng** của các hàng, không chỉ một phép so sánh trên điểm số.

### 6.2. Ví dụ nhóm A

~~~sql
SELECT
    student_id,
    student_name,
    score,
    CUME_DIST() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS cume_dist
FROM exam_scores
WHERE cohort_code = 'A'
ORDER BY score DESC, student_id;
~~~

Kết quả:

| Điểm | Hàng có điểm ≥ mức này | N | cume_dist |
| ---: | ---: | ---: | ---: |
| 95 | 1 | 8 | 0.125000 |
| 90 | 3 | 8 | 0.375000 |
| 90 | 3 | 8 | 0.375000 |
| 80 | 4 | 8 | 0.500000 |
| 75 | 6 | 8 | 0.750000 |
| 75 | 6 | 8 | 0.750000 |
| 60 | 7 | 8 | 0.875000 |
| 40 | 8 | 8 | 1.000000 |

Tính từng giá trị:

- Điểm `95`: chỉ có `1` người đạt ít nhất 95 → `1/8 = 0.125`.
- Điểm `90`: có `3` người đạt ít nhất 90 (95, 90, 90) → `3/8 = 0.375`.
- Điểm `75`: có `6` người đạt ít nhất 75 → `6/8 = 0.75`.
- Điểm `40`: cả `8` người đạt ít nhất 40 → `8/8 = 1`.

Hai người đồng điểm `90` cùng nhận `0.375`; hai người đồng điểm `75` cùng nhận `0.75`. Hàm sử dụng **điểm cuối của nhóm đồng hạng** trong thứ tự đã chọn.

### 6.3. Khác biệt so với PERCENT_RANK

Với học viên điểm `90` ở nhóm A:

- `PERCENT_RANK = (2-1)/(8-1) = 1/7 ≈ 0.142857`.
- `CUME_DIST = 3/8 = 0.375`.

`PERCENT_RANK` lấy **vị trí hạng đầu tiên của nhóm đồng điểm** rồi chuẩn hóa theo `N - 1`. `CUME_DIST` lấy **số hàng tính đến hết nhóm đồng điểm** chia cho `N`.

Đừng dùng hai hàm thay thế cho nhau rồi mô tả bằng một câu chung như “phần trăm đứng trên người khác”: **cách xử lý đồng điểm và mẫu số khác nhau**.

### 6.4. Các trường hợp biên

`CUME_DIST` có một số tính chất hữu ích:

- Trên phân vùng không rỗng, kết quả **lớn hơn 0** và **không quá 1**.
- Hàng cuối và mọi hàng cùng nhóm đồng hạng cuối có `CUME_DIST = 1`.
- Nếu cả phân vùng đều có cùng giá trị sắp xếp, mọi hàng có `CUME_DIST = 1`.
- Nếu phân vùng chỉ có một hàng, kết quả là `1`.
- Với nhóm đồng hạng ở vị trí đầu tiên, giá trị nhỏ nhất có thể là **lớn hơn `1/N`**, vì nhóm đầu có nhiều hàng.

Nhóm B có hai người cùng 88 điểm đứng đầu trong 5 người. Vì vậy `CUME_DIST` của **cả hai** là `2/5 = 0.4`, chứ không phải `1/5 = 0.2`.

## 7. Đặt cả ba hàm cạnh nhau

Giờ dùng một truy vấn để so sánh toàn bộ dữ liệu:

~~~sql
SELECT
    cohort_code,
    student_id,
    student_name,
    score,
    NTILE(4) OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC, student_id ASC
    ) AS bucket4,
    RANK() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS score_rank,
    PERCENT_RANK() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS percent_rank,
    CUME_DIST() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS cume_dist
FROM exam_scores
ORDER BY cohort_code, score DESC, student_id;
~~~

Đọc kết quả dưới đây theo **điểm cao trước**. Các số thập phân được hiển thị xấp xỉ đến 6 chữ số; giá trị thật do DBMS trả có thể có độ chính xác/kiểu dấu phẩy động khác nhau.

### Nhóm A — 8 học viên

| ID | Điểm | NTILE(4) | RANK | PERCENT_RANK | CUME_DIST |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 95 | 1 | 1 | 0.000000 | 0.125000 |
| 102 | 90 | 1 | 2 | 0.142857 | 0.375000 |
| 103 | 90 | 2 | 2 | 0.142857 | 0.375000 |
| 104 | 80 | 2 | 4 | 0.428571 | 0.500000 |
| 105 | 75 | 3 | 5 | 0.571429 | 0.750000 |
| 106 | 75 | 3 | 5 | 0.571429 | 0.750000 |
| 107 | 60 | 4 | 7 | 0.857143 | 0.875000 |
| 108 | 40 | 4 | 8 | 1.000000 | 1.000000 |

Quan sát:

- Binh và Chi đều 90 điểm, nên **`RANK`, `PERCENT_RANK` và `CUME_DIST` bằng nhau**.
- Nhưng Binh có `bucket4 = 1`, Chi có `bucket4 = 2` vì hai người nằm ở ranh giới bucket của `NTILE(4)`.
- Điểm 95 có `PERCENT_RANK = 0` nhưng `CUME_DIST = 0.125`.
- Điểm 40 có cả `PERCENT_RANK` và `CUME_DIST` bằng 1.

### Nhóm B — 5 học viên

| ID | Điểm | NTILE(4) | RANK | PERCENT_RANK | CUME_DIST |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 201 | 88 | 1 | 1 | 0.000000 | 0.400000 |
| 202 | 88 | 1 | 1 | 0.000000 | 0.400000 |
| 203 | 70 | 2 | 3 | 0.500000 | 0.600000 |
| 204 | 65 | 3 | 4 | 0.750000 | 0.800000 |
| 205 | 50 | 4 | 5 | 1.000000 | 1.000000 |

Quan sát:

- Hai học viên cao điểm nhất cùng hạng 1 → `PERCENT_RANK = 0`.
- Hai người đứng đầu chiếm `2/5 = 40%` số hàng → `CUME_DIST = 0.4` cho cả hai.
- `NTILE(4)` vẫn chia 5 hàng thành kích thước **2–1–1–1**.

### Nhóm C — 1 học viên

| ID | Điểm | NTILE(4) | RANK | PERCENT_RANK | CUME_DIST |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 301 | 77 | 1 | 1 | 0.000000 | 1.000000 |

Với phân vùng chỉ một hàng:

- `NTILE(4) = 1`.
- `PERCENT_RANK() = 0`.
- `CUME_DIST() = 1`.

Đây là bộ ba giá trị **không mâu thuẫn**: bucket đầu, thứ hạng tương đối đầu tiên và 100% số hàng của phân vùng đã được bao gồm trong phân phối tích lũy.

## 8. Đồng điểm: sự khác biệt quan trọng nhất khi phân loại

### 8.1. Khóa phá hòa trong NTILE

`NTILE` phải phân chia **các hàng riêng biệt** thành bucket. Nếu có hai học viên cùng 90 điểm và đúng ranh giới hai bucket, không thể vừa yêu cầu **mọi bucket có số hàng gần bằng nhau** vừa đảm bảo **mọi người đồng điểm cùng bucket** trong mọi trường hợp.

Với nhóm A, `NTILE(4)` sẽ chia 8 học viên thành 4 bucket, mỗi bucket 2 người. Thứ tự theo:

~~~sql
ORDER BY score DESC, student_id ASC
~~~

đặt Binh (ID 102) trước Chi (ID 103), nên Binh vào bucket 1, Chi vào bucket 2. Đổi khóa phụ thành `student_id DESC` có thể đổi người nằm ở mỗi bucket nhưng **không đổi điểm số hoặc việc hai người đồng hạng về điểm**.

Nếu quy tắc công bằng yêu cầu **hai người đồng điểm luôn cùng nhóm**, `NTILE` có thể **không phù hợp** làm tiêu chí duy nhất.

### 8.2. Khóa phá hòa cũng làm đổi peer group của PERCENT_RANK và CUME_DIST

Đây là lỗi thiết kế rất dễ mắc:

~~~sql
-- Câu này coi mọi student_id khác nhau là thứ tự phân biệt.
PERCENT_RANK() OVER (
    PARTITION BY cohort_code
    ORDER BY score DESC, student_id ASC
)
~~~

Vì `student_id` là duy nhất, **không còn hai hàng đồng hạng theo toàn bộ danh sách ORDER BY**. Hai người cùng 90 điểm có thể nhận percent rank **khác nhau**, dù điểm bằng nhau.

So sánh:

~~~sql
-- Giữ đồng điểm là một peer group:
PERCENT_RANK() OVER (
    PARTITION BY cohort_code
    ORDER BY score DESC
)

-- Phá đồng hạng bằng ID, làm thay đổi phép phân tích:
PERCENT_RANK() OVER (
    PARTITION BY cohort_code
    ORDER BY score DESC, student_id ASC
)
~~~

Trong nhiều bài toán:

- Dùng `ORDER BY score DESC, student_id` **chỉ cho `NTILE`** để bucket ổn định.
- Dùng `ORDER BY score DESC` **cho `PERCENT_RANK` và `CUME_DIST`** để những học viên cùng điểm nhận cùng giá trị.

Hai định nghĩa `ORDER BY` khác nhau là **có chủ đích**, không phải thiếu nhất quán. Chúng phục vụ hai tiêu chí khác nhau: chia hàng xác định và giữ đồng hạng theo điểm.

### 8.3. Phân nhóm không tách đồng điểm

Nếu mục tiêu là “cùng điểm phải nhận cùng nhãn phân loại”, có thể cân nhắc dựa trên một hàm tôn trọng peer group:

~~~sql
SELECT
    cohort_code,
    student_id,
    score,
    PERCENT_RANK() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS rank_position,
    CUME_DIST() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS cumulative_share
FROM exam_scores
ORDER BY cohort_code, score DESC, student_id;
~~~

Sau đó áp dụng ngưỡng nghiệp vụ ở một cấp truy vấn ngoài, chứ không ép buộc chính xác 25% số hàng vào mỗi nhóm bằng mọi giá.

Lưu ý: phương pháp dựa trên ngưỡng `PERCENT_RANK` hay `CUME_DIST` **không bảo đảm số người mỗi nhóm gần bằng nhau**. Đây là sự đánh đổi cần quyết định theo yêu cầu, không phải một lỗi tính toán.

## 9. “Top 25%” có thể có ba nghĩa khác nhau

Xét nhóm A gồm 8 học viên, điểm lần lượt là `95, 90, 90, 80, 75, 75, 60, 40`.

Ta có thể diễn giải “nhóm đầu 25%” theo ba chính sách:

### Cách A — NTILE(4) = 1: chọn đúng số hàng gần 25%

~~~sql
WITH ranked AS (
    SELECT
        student_id,
        student_name,
        cohort_code,
        score,
        NTILE(4) OVER (
            PARTITION BY cohort_code
            ORDER BY score DESC, student_id
        ) AS bucket4
    FROM exam_scores
)
SELECT student_id, student_name, score
FROM ranked
WHERE cohort_code = 'A'
  AND bucket4 = 1
ORDER BY score DESC, student_id;
~~~

Kết quả: **An (95), Binh (90)**.

Tổng `2/8 = 25%` học viên. Nhưng Chi cũng 90 điểm mà lại bị loại do ranh giới bucket. Nếu chính sách học bổng không cho phép tách những người cùng điểm, cách này có thể không đạt yêu cầu công bằng.

### Cách B — PERCENT_RANK() ≤ 0.25: giữ những người có thứ hạng tương đối thuộc ngưỡng

~~~sql
WITH ranked AS (
    SELECT
        student_id,
        student_name,
        cohort_code,
        score,
        PERCENT_RANK() OVER (
            PARTITION BY cohort_code
            ORDER BY score DESC
        ) AS pr
    FROM exam_scores
)
SELECT student_id, student_name, score, pr
FROM ranked
WHERE cohort_code = 'A'
  AND pr <= 0.25
ORDER BY score DESC, student_id;
~~~

Kết quả: **An (95), Binh (90), Chi (90)**.

Ba người được chọn, tức `3/8 = 37.5%` số hàng. Cách này **không chia đồng điểm**, nhưng số người có thể vượt ngưỡng 25%.

### Cách C — CUME_DIST() ≤ 0.25: chỉ lấy nhóm đồng điểm có tổng tỷ trọng tích lũy chưa vượt ngưỡng

~~~sql
WITH ranked AS (
    SELECT
        student_id,
        student_name,
        cohort_code,
        score,
        CUME_DIST() OVER (
            PARTITION BY cohort_code
            ORDER BY score DESC
        ) AS cd
    FROM exam_scores
)
SELECT student_id, student_name, score, cd
FROM ranked
WHERE cohort_code = 'A'
  AND cd <= 0.25
ORDER BY score DESC, student_id;
~~~

Kết quả: **chỉ An (95)**, vì:

- An có `CUME_DIST = 1/8 = 0.125`.
- Binh và Chi cùng 90 điểm, có `CUME_DIST = 3/8 = 0.375`, vượt 0.25.

Chỉ `1/8 = 12.5%` số hàng được chọn.

### So sánh ba chính sách

| Chính sách | Học viên A được chọn | Số người | Có tách người cùng điểm không? |
| --- | --- | ---: | --- |
| `NTILE(4) = 1` | An, Binh | 2 | **Có thể có** |
| `PERCENT_RANK() <= 0.25` | An, Binh, Chi | 3 | Không, nếu `ORDER BY score` |
| `CUME_DIST() <= 0.25` | An | 1 | Không, nếu `ORDER BY score` |

Cả ba kết quả đều có thể **đúng về mặt SQL**, nhưng trả lời **ba cách đặt chính sách khác nhau**.

Khi yêu cầu nghiệp vụ chỉ nói “top 25%”, cần làm rõ: ưu tiên **số lượng chính xác**, **không tách người đồng điểm**, hay **chỉ nhận toàn bộ nhóm đồng điểm khi không vượt hạn mức**. Nếu cần một **điểm số tại phân vị 25%, 50%, 75%**, có thể cần những hàm/tính toán phân vị khác như `PERCENTILE_CONT`/`PERCENTILE_DISC` ở hệ quản trị hỗ trợ — chúng **không đồng nghĩa với `NTILE`**.

## 10. Phân vị, thứ hạng và phân phối tích lũy không phải cùng một đại lượng

Một số tên thuật ngữ dễ gây nhầm:

- **Rank:** vị trí xếp hạng theo thứ tự.
- **Percent rank:** thứ hạng chuẩn hóa theo công thức `(rank - 1) / (N - 1)`.
- **Cumulative distribution:** tỷ lệ các hàng ở trước hoặc đồng hạng trong thứ tự đã định nghĩa.
- **Quantile / percentile threshold:** một giá trị làm mốc phân chia phân phối theo quy tắc nội suy hoặc lựa chọn điểm quan sát.
- **NTILE bucket:** nhãn nhóm từ 1 đến `k` bằng cách chia **số hàng đã sắp**, không trực tiếp trả điểm tại ranh giới phân vị.

### Ví dụ tại cùng một mức điểm

Trong nhóm A, xét điểm `90`:

~~~text
Điểm đã sắp DESC: 95 | 90 90 | 80 | 75 75 | 60 | 40

RANK(90) = 2
PERCENT_RANK(90) = (2 - 1) / (8 - 1) = 1/7
CUME_DIST(90) = 3 / 8
NTILE(4): hai hàng điểm 90 nằm ở bucket 1 và 2
~~~

Không thể diễn giải tất cả thành “90 điểm thuộc nhóm 14%” hoặc “90 điểm nằm ở phân vị 37.5%” mà không giải thích **chiều sắp xếp** và **định nghĩa chỉ số**.

Nếu khách hàng muốn một **biểu đồ phân phối điểm**, `CUME_DIST` theo `score ASC` thường dễ diễn giải thành “tỷ lệ học viên có điểm ≤ mức này”. Nếu muốn **phân nhóm số người** theo doanh số, `NTILE` có thể tiện hơn. Nếu cần **thứ hạng tương đối** theo bảng xếp hạng, `PERCENT_RANK` diễn đạt phù hợp.

## 11. Lọc đúng thời điểm: trước hay sau khi tính window function?

### 11.1. Không đặt hàm cửa sổ trực tiếp trong WHERE cùng cấp

Một câu SQL dạng:

~~~sql
-- Không hợp lệ trong SQL thông dụng:
SELECT student_id, score
FROM exam_scores
WHERE NTILE(4) OVER (
    PARTITION BY cohort_code
    ORDER BY score DESC
) = 1;
~~~

không phải cách dùng hợp lệ ở những DBMS phổ biến: `WHERE` được xử lý về mặt ngữ nghĩa trước giai đoạn hàm cửa sổ.

Cách đúng là tính cửa sổ trong `SELECT` của **CTE hoặc derived table**, rồi lọc ở truy vấn ngoài:

~~~sql
WITH ranked AS (
    SELECT
        student_id,
        student_name,
        cohort_code,
        score,
        NTILE(4) OVER (
            PARTITION BY cohort_code
            ORDER BY score DESC, student_id
        ) AS bucket4
    FROM exam_scores
)
SELECT
    student_id,
    student_name,
    cohort_code,
    score
FROM ranked
WHERE bucket4 = 1
ORDER BY cohort_code, score DESC, student_id;
~~~

Ở đây phân vùng A, B, C được tính đầy đủ trước khi lọc bucket trong **truy vấn ngoài**.

### 11.2. Lọc dữ liệu trước window làm thay đổi mẫu số và bucket

So sánh hai mục tiêu:

**Mục tiêu 1:** “Trong những học viên **đạt từ 70 điểm trở lên**, chia họ thành các bucket.”

~~~sql
SELECT
    cohort_code,
    student_id,
    score,
    NTILE(4) OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC, student_id
    ) AS bucket_among_passing
FROM exam_scores
WHERE score >= 70
ORDER BY cohort_code, score DESC, student_id;
~~~

`WHERE score >= 70` loại các hàng thấp điểm **trước khi NTILE được tính**. Nhóm A còn 6 người; B còn 3; C còn 1. Bucket phản ánh **những học viên đạt ngưỡng**, không phải toàn bộ nhóm ban đầu.

**Mục tiêu 2:** “Tính bucket trên **toàn bộ nhóm**, sau đó chỉ hiển thị học viên đạt từ 70.”

~~~sql
WITH all_ranked AS (
    SELECT
        cohort_code,
        student_id,
        score,
        NTILE(4) OVER (
            PARTITION BY cohort_code
            ORDER BY score DESC, student_id
        ) AS bucket_among_all
    FROM exam_scores
)
SELECT *
FROM all_ranked
WHERE score >= 70
ORDER BY cohort_code, score DESC, student_id;
~~~

Ở đây các bucket được tính trên đủ 8/5/1 học viên rồi mới lọc đầu ra. Ví dụ học viên điểm 75 ở nhóm A vẫn có `bucket4 = 3` ở mục tiêu 2, nhưng khi lọc còn 6 người rồi tính lại theo `NTILE(4)`, các bucket có thể thay đổi.

**Quy tắc:** điều kiện `WHERE` trong cùng `SELECT` với hàm cửa sổ **thay đổi dân số dùng để tính**, còn điều kiện ở truy vấn ngoài **chỉ lọc kết quả đã tính**. Điều này cũng áp dụng cho mẫu số `N` của `PERCENT_RANK` và `CUME_DIST`.

### 11.3. HAVING, GROUP BY và hàm cửa sổ

Hàm cửa sổ được tính trên **các hàng còn lại ở giai đoạn phân tích**, có thể là hàng đã được tổng hợp nếu truy vấn có `GROUP BY`. Ví dụ, nếu muốn chia **doanh thu của phòng ban** thành bốn nhóm, cần tổng hợp ở cấp phòng trước rồi áp dụng hàm cửa sổ trên **một hàng cho mỗi phòng**.

Mẫu khái niệm:

~~~sql
WITH revenue_by_team AS (
    SELECT
        team_id,
        SUM(amount) AS total_revenue
    FROM sales
    GROUP BY team_id
)
SELECT
    team_id,
    total_revenue,
    NTILE(4) OVER (
        ORDER BY total_revenue DESC, team_id
    ) AS revenue_bucket
FROM revenue_by_team;
~~~

`sales` chỉ là **tên bảng ví dụ giả định** trong đoạn này; nó không thuộc schema `exam_scores` đã tạo. Mục đích là minh họa đúng **mức hạt (grain)**: một hàng đại diện cho một phòng ban ở thời điểm xếp bucket. Nếu áp dụng `NTILE` trực tiếp cho mọi giao dịch bán hàng thì bucket phản ánh **giao dịch**, không phải phòng ban.

## 12. Trường hợp có NULL trong khóa ORDER BY

Bảng mẫu khai báo `score NOT NULL`, nên các phép phân tích ở trên không bị ảnh hưởng bởi điểm thiếu. Trong dữ liệu thực, đôi khi chưa chấm điểm và cột `score` có thể `NULL`.

### 12.1. NULL xuất hiện ở đầu hay cuối phụ thuộc DBMS

Khi viết:

~~~sql
ORDER BY score DESC
~~~

vị trí của các giá trị `NULL` **không giống nhau trong mọi DBMS**. Ví dụ PostgreSQL mặc định đưa `NULL` lên trước khi sắp `DESC`, trong khi những hệ khác có quy tắc khác. Nếu không kiểm soát điều này, học viên **chưa có điểm** có thể bị xem như thuộc bucket điểm cao nhất trên một DBMS.

Trong PostgreSQL, có thể viết tường minh:

~~~sql
ORDER BY score DESC NULLS LAST
~~~

Nhưng `NULLS LAST` không có cú pháp hỗ trợ đồng nhất trong mọi hệ SQL. Một cách tương đối khả chuyển để đặt điểm thiếu ở cuối là:

~~~sql
ORDER BY
    CASE WHEN score IS NULL THEN 1 ELSE 0 END ASC,
    score DESC
~~~

Khi tính `NTILE` và muốn phá hòa giữa các hàng cùng điểm:

~~~sql
NTILE(4) OVER (
    PARTITION BY cohort_code
    ORDER BY
        CASE WHEN score IS NULL THEN 1 ELSE 0 END,
        score DESC,
        student_id
)
~~~

Để `PERCENT_RANK` và `CUME_DIST` vẫn coi các hàng cùng điểm (gồm cùng `NULL` nếu đó là chính sách) là đồng hạng, **không thêm `student_id`** vào thứ tự của hai hàm đó:

~~~sql
CUME_DIST() OVER (
    PARTITION BY cohort_code
    ORDER BY
        CASE WHEN score IS NULL THEN 1 ELSE 0 END,
        score DESC
)
~~~

Trong các hàm phân phối cửa sổ, hàng đồng hạng được xác định theo **biểu thức sắp xếp**, không dựa vào việc `NULL = NULL` trả `TRUE` trong `WHERE`.

### 12.2. Có nên tính học viên chưa có điểm không?

Đây là quyết định nghiệp vụ:

- Nếu `NULL` nghĩa là **chưa chấm**, có thể nên **loại khỏi quần thể tính phân vị**.
- Nếu `NULL` là **thiếu dữ liệu cần hiển thị riêng**, có thể giữ hàng trong báo cáo nhưng không tính vào phân phối.
- Nếu quy ước `NULL` là **0 điểm**, phải có quyết định rõ ràng trước khi dùng `COALESCE(score, 0)`, vì điều đó coi dữ liệu chưa biết là giá trị thực 0.

Muốn xếp hạng **chỉ những hàng đã có điểm** và vẫn hiển thị cả học viên chưa có điểm, có thể tách CTE tính toán trên `score IS NOT NULL` rồi `LEFT JOIN` theo `student_id`. Không nên tự biến tất cả điểm thiếu thành 0 chỉ để tránh xử lý `NULL`.

## 13. Phân vùng một hàng, tất cả đồng hạng và tập dữ liệu quá nhỏ

Ba trường hợp biên cần hiểu trước khi đưa báo cáo vào ứng dụng:

### 13.1. Một hàng duy nhất trong phân vùng

Nhóm C đã minh họa:

~~~text
N = 1
NTILE(4) = 1
PERCENT_RANK() = 0
CUME_DIST() = 1
~~~

Việc một học viên có `PERCENT_RANK = 0` **không nói học viên kém**; nó chỉ nói rằng trong phân vùng chỉ có một vị trí thứ hạng đầu tiên.

### 13.2. Mọi người cùng điểm

Giả sử một nhóm khác có bốn học viên, đều 80 điểm:

~~~text
Điểm:         80  80  80  80
RANK:          1   1   1   1
PERCENT_RANK:  0   0   0   0
CUME_DIST:     1   1   1   1
NTILE(4):      1   2   3   4
~~~

Với `NTILE(4)`, thứ tự các học viên cùng điểm phải có khóa phụ xác định nếu muốn biết chính xác ai vào bucket nào. Còn với `PERCENT_RANK` và `CUME_DIST` chỉ theo `score`, tất cả đồng hạng.

### 13.3. Số học viên nhỏ hơn số bucket

Nếu chỉ có hai học viên mà gọi `NTILE(10)`, hai hàng có thể nhận bucket 1 và 2; không có hàng nào trong bucket 3–10. Vì vậy không nên hiển thị “top decile” như một nhóm có đúng 10% người ở những phân vùng quá nhỏ. Với `N = 2`, một người đã chiếm 50% phân vùng.

### 13.4. Phân vùng rỗng không tạo hàng

Nếu không có học viên nào của nhóm `D` trong bảng:

~~~sql
SELECT
    student_id,
    NTILE(4) OVER (
        ORDER BY score DESC, student_id
    ) AS bucket4
FROM exam_scores
WHERE cohort_code = 'D';
~~~

kết quả là **0 hàng**. Hàm cửa sổ không tạo sẵn một hàng tổng hợp hay bucket rỗng. Nếu báo cáo cần hiện “nhóm D — 0 học viên”, phải xuất phát từ một bảng danh sách nhóm rồi nối dữ liệu thích hợp.

## 14. So với ROW_NUMBER, RANK và DENSE_RANK

Các hàm này cùng là window functions nhưng có mục đích khác nhau:

| Hàm | Cách tính | Ứng xử với đồng điểm |
| --- | --- | --- |
| `ROW_NUMBER()` | Đánh số từng hàng theo thứ tự, `1, 2, 3...` | Mỗi hàng một số; cần khóa phá hòa nếu muốn ổn định |
| `RANK()` | Hạng của nhóm đồng điểm; có bước nhảy sau đồng hạng | Hai người 90 cùng hạng 2, người kế sau hạng 4 |
| `DENSE_RANK()` | Hạng của các **mức điểm phân biệt**, không bỏ số hạng | Hai người 90 cùng hạng 2, người kế sau hạng 3 |
| `NTILE(k)` | Chia hàng đã xếp thành `k` bucket gần bằng kích thước | Có thể chia người đồng điểm sang hai bucket |
| `PERCENT_RANK()` | `(RANK - 1)/(N - 1)` | Giữ cùng giá trị với cùng peer group |
| `CUME_DIST()` | Số hàng đến **hết nhóm đồng hạng** / `N` | Giữ cùng giá trị với cùng peer group |

Với nhóm A:

~~~text
Điểm       95  90  90  80  75  75  60  40
ROW_NUMBER  1   2   3   4   5   6   7   8
RANK        1   2   2   4   5   5   7   8
DENSE_RANK  1   2   2   3   4   4   5   6
~~~

**Không tính PERCENT_RANK từ DENSE_RANK**. Hàm `PERCENT_RANK` theo định nghĩa dựa trên `RANK`, vì vậy mẫu số `N-1` và các khoảng trống sau đồng điểm đều có ý nghĩa.

Nếu nghiệp vụ quan tâm **số mức điểm khác nhau**, `DENSE_RANK` có thể phù hợp hơn. Nếu quan tâm **chia số người**, `NTILE` thường phù hợp hơn. Nếu quan tâm **tỷ lệ tích lũy số người**, `CUME_DIST` là ứng viên chính.

## 15. Bài toán ứng dụng: báo cáo kết quả và phân nhóm

### 15.1. Báo cáo đầy đủ theo nhóm với nhãn bucket

~~~sql
WITH scored AS (
    SELECT
        cohort_code,
        student_id,
        student_name,
        score,
        NTILE(4) OVER (
            PARTITION BY cohort_code
            ORDER BY score DESC, student_id
        ) AS bucket4
    FROM exam_scores
)
SELECT
    cohort_code,
    student_id,
    student_name,
    score,
    bucket4,
    CASE bucket4
        WHEN 1 THEN 'NHOM_1'
        WHEN 2 THEN 'NHOM_2'
        WHEN 3 THEN 'NHOM_3'
        ELSE 'NHOM_4'
    END AS bucket_code
FROM scored
ORDER BY cohort_code, score DESC, student_id;
~~~

Ở đây `CASE` chỉ **đặt nhãn nghiệp vụ** cho bucket đã tính. Không nên tự gắn nhãn “xuất sắc / yếu” nếu chưa có quy định tiêu chí: `NTILE(4)` là **xếp tương đối trong từng nhóm**, có thể phân một người 70 điểm vào bucket đầu nếu tất cả những người khác trong nhóm điểm thấp hơn.

### 15.2. Đếm số học viên trong mỗi bucket

~~~sql
WITH bucketed AS (
    SELECT
        cohort_code,
        student_id,
        NTILE(4) OVER (
            PARTITION BY cohort_code
            ORDER BY score DESC, student_id
        ) AS bucket4
    FROM exam_scores
)
SELECT
    cohort_code,
    bucket4,
    COUNT(*) AS student_count
FROM bucketed
GROUP BY cohort_code, bucket4
ORDER BY cohort_code, bucket4;
~~~

Với dữ liệu mẫu:

| Nhóm | Bucket | student_count |
| --- | ---: | ---: |
| A | 1 | 2 |
| A | 2 | 2 |
| A | 3 | 2 |
| A | 4 | 2 |
| B | 1 | 2 |
| B | 2 | 1 |
| B | 3 | 1 |
| B | 4 | 1 |
| C | 1 | 1 |

Ở nhóm C, không có hàng bucket 2, 3, 4; truy vấn `GROUP BY` không tự sinh các hàng 0.

### 15.3. Gắn ngưỡng theo CUME_DIST

Giả sử nhóm muốn đánh dấu **các điểm mà tỷ lệ số người ở trên hoặc bằng chưa vượt 50%**:

~~~sql
WITH measured AS (
    SELECT
        cohort_code,
        student_id,
        student_name,
        score,
        CUME_DIST() OVER (
            PARTITION BY cohort_code
            ORDER BY score DESC
        ) AS cd
    FROM exam_scores
)
SELECT
    cohort_code,
    student_id,
    student_name,
    score,
    cd
FROM measured
WHERE cd <= 0.5
ORDER BY cohort_code, score DESC, student_id;
~~~

Trong nhóm A, các học viên được chọn có điểm `95, 90, 90, 80`: đủ `4/8 = 50%`. Trong nhóm B, hai người 88 điểm có `cd = 0.4`; người 70 điểm có `cd = 0.6` nên không được chọn. Nhóm C có `cd = 1` nên không có người được chọn.

Đây là một chính sách **giữ nguyên peer group và không vượt ngưỡng tích lũy**. Nó **không** đảm bảo mỗi nhóm chắc chắn có người được chọn.

### 15.4. So sánh thứ hạng toàn kỳ thi với thứ hạng trong nhóm

~~~sql
SELECT
    cohort_code,
    student_id,
    score,
    PERCENT_RANK() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS within_cohort,
    PERCENT_RANK() OVER (
        ORDER BY score DESC
    ) AS across_all_cohorts
FROM exam_scores
ORDER BY cohort_code, score DESC, student_id;
~~~

- `within_cohort` dùng `N` của từng nhóm `A/B/C`.
- `across_all_cohorts` dùng toàn bộ `14` hàng.
- Một điểm số có thể có vị trí tương đối khác nhau khi so với **người cùng nhóm** và khi so với **toàn bộ học viên**.

Khi hiển thị hai chỉ số cạnh nhau, phải ghi rõ **tập so sánh** để người dùng không nhầm lẫn.

## 16. Sai số số thực, hiển thị phần trăm và kiểu dữ liệu

`PERCENT_RANK()` và `CUME_DIST()` thường trả giá trị **tỷ lệ từ 0 đến 1**, không phải `0%` đến `100%` dưới dạng chuỗi.

Ví dụ:

~~~sql
SELECT
    student_id,
    score,
    PERCENT_RANK() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS pr,
    CUME_DIST() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS cd
FROM exam_scores;
~~~

Nếu một giá trị `cd = 0.375`, đó là **37.5%** khi biểu diễn dưới dạng phần trăm. Cách thông thường là:

- Giữ `cd` dạng số trong SQL/API.
- Chuyển thành chuỗi “37,5%” ở tầng báo cáo hoặc giao diện phù hợp với locale.

Nếu muốn xuất trực tiếp số phần trăm từ SQL, có thể nhân 100:

~~~sql
SELECT
    student_id,
    100.0 * CUME_DIST() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS cume_percent
FROM exam_scores;
~~~

Kết quả là **giá trị số** biểu diễn phần trăm, ví dụ `37.5`, không tự có ký hiệu `%`.

Các phân số như `1/7` không biểu diễn chính xác với số chữ số thập phân hữu hạn. Vì vậy:

- Không kỳ vọng kết quả lưu dạng dấu phẩy động có đúng **6 chữ số** như bảng minh họa.
- Khi so sánh với ngưỡng như `0.25`, hiểu quy tắc làm tròn và độ chính xác số của DBMS nếu yêu cầu nghiệp vụ nhạy cảm tại ranh giới.
- Nếu cần hiển thị, làm tròn ở **lớp trình bày** hoặc dùng `ROUND` theo cú pháp/kiểu của hệ quản trị; đừng làm tròn trước rồi lọc nếu điều đó làm đổi tập được chọn.

Ví dụ khi một giá trị lý thuyết rất gần ngưỡng phân loại, làm tròn thành `0.25` rồi so với `<= 0.25` có thể đưa ra kết quả khác so với so giá trị gốc. Hãy giữ ranh giới và quy tắc tính rõ ràng.

## 17. Hiệu năng và kế hoạch thực thi

### 17.1. Các hàm cần một thứ tự có ý nghĩa

Để tính `NTILE`, `PERCENT_RANK` và `CUME_DIST`, hệ quản trị phải xử lý các hàng theo phân vùng và thứ tự:

~~~sql
PARTITION BY cohort_code
ORDER BY score DESC
~~~

Ở dữ liệu lớn, quá trình này có thể cần **sort**, bộ nhớ, bộ đệm và một bước xử lý cửa sổ (*WindowAgg* hoặc thuật ngữ tương ứng theo DBMS). Chi phí phụ thuộc kích thước phân vùng, số cột, số hàm, số lượt sắp xếp và chỉ mục sẵn có.

Không phải mọi cửa sổ trong cùng truy vấn đều có thể dùng chung một thứ tự vật lý. Ví dụ:

~~~sql
NTILE(4) OVER (
    PARTITION BY cohort_code
    ORDER BY score DESC, student_id
)

CUME_DIST() OVER (
    PARTITION BY cohort_code
    ORDER BY score DESC
)
~~~

có các danh sách `ORDER BY` khác nhau. Bộ tối ưu có thể chia sẻ công việc trong một số kế hoạch, nhưng không nên tự khẳng định chỉ có một lượt sort hoặc thứ tự thực thi cố định.

### 17.2. Chỉ mục có thể hỗ trợ

Với bảng lớn thường xuyên xếp điểm theo nhóm:

~~~sql
CREATE INDEX idx_exam_scores_cohort_score
ON exam_scores (
    cohort_code,
    score DESC,
    student_id
);
~~~

Đây là một **ứng viên chỉ mục**:

- `cohort_code` tương ứng với phân vùng.
- `score DESC` tương ứng với thứ tự điểm.
- `student_id` làm khóa ổn định cho những truy vấn cần phá hòa.

Tuy nhiên không có bảo đảm rằng DBMS luôn dùng index đó cho tất cả các hàm, vì kế hoạch còn phụ thuộc mức chọn lọc, dữ liệu cần đọc thêm và chi phí sắp xếp. Chỉ mục cũng tăng chi phí ghi và dung lượng.

### 17.3. Đo bằng EXPLAIN

Ví dụ trên PostgreSQL:

~~~sql
EXPLAIN
SELECT
    cohort_code,
    student_id,
    score,
    NTILE(4) OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC, student_id
    ) AS bucket4
FROM exam_scores;
~~~

Có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    cohort_code,
    student_id,
    score,
    CUME_DIST() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS cd
FROM exam_scores;
~~~

`ANALYZE` **thực sự chạy câu truy vấn**. Với `SELECT` minh họa, nó chỉ đọc dữ liệu; cần thận trọng nếu áp dụng cho câu lệnh thay đổi dữ liệu. Bộ dữ liệu 14 hàng rất nhỏ nên PostgreSQL có thể chọn quét toàn bảng và sắp xếp; đây không đủ cơ sở để kết luận hiệu năng trên hàng triệu hàng.

### 17.4. Phân vùng quá lớn và phân vùng nhỏ

Nếu `PARTITION BY cohort_code` nhưng 99% dữ liệu nằm trong một cohort, phân vùng đó vẫn rất lớn. Truy vấn có thể tốn bộ nhớ và tạo spill xuống đĩa tùy engine. Ngược lại, nếu mỗi cohort có 1–2 hàng, `NTILE(10)` tạo bucket khó diễn giải như “đầu 10%”.

Do đó tối ưu và thiết kế báo cáo phải xét **phân bố số hàng theo phân vùng**, không chỉ tổng số hàng toàn bảng.

## 18. Khả năng hỗ trợ và khác biệt giữa các hệ quản trị

Các hàm `NTILE`, `PERCENT_RANK` và `CUME_DIST` có mặt ở nhiều hệ SQL hiện đại, nhưng cần kiểm tra **phiên bản và chi tiết cú pháp**.

| Hệ quản trị | Tình trạng phổ biến | Điểm lưu ý |
| --- | --- | --- |
| PostgreSQL | Hỗ trợ cả ba hàm cửa sổ | Hỗ trợ `PARTITION BY`, `ORDER BY`, cú pháp `NULLS FIRST/LAST`; kiểu tỷ lệ thường là `double precision` |
| SQL Server | Hỗ trợ cả ba trong các phiên bản hiện đại | Dùng `OVER` với `ORDER BY`; nhiều hàm xếp hạng không cho khai báo `ROWS/RANGE`; `NULL` có quy tắc thứ tự riêng |
| MySQL 8.0+ | Hỗ trợ cả ba | Cần MySQL phiên bản có window functions; không giả định MySQL 5.7 có chúng |
| MariaDB | Hỗ trợ trên các phiên bản có window functions | Kiểm tra phiên bản, cú pháp và hành vi theo tài liệu MariaDB, không tự đồng nhất với MySQL |
| SQLite 3.25.0+ | Hỗ trợ window functions gồm các hàm này | Phạm vi hỗ trợ từ phiên bản có window functions; một số cú pháp cửa sổ có quy tắc riêng |
| Oracle Database | Hỗ trợ các hàm phân tích tương ứng | Có quy tắc kiểu dữ liệu, thứ tự `NULL` và hạn chế của analytic functions theo Oracle |

Ví dụ tương thích về cấu trúc ở hầu hết các hệ có hỗ trợ:

~~~sql
SELECT
    cohort_code,
    student_id,
    score,
    NTILE(4) OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC, student_id
    ) AS quartile_id,
    PERCENT_RANK() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS pr,
    CUME_DIST() OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC
    ) AS cd
FROM exam_scores
ORDER BY cohort_code, score DESC, student_id;
~~~

Điểm cần kiểm tra khi chuyển SQL:

1. **Phiên bản có hỗ trợ window functions không?** Đặc biệt với các phiên bản MySQL/SQLite cũ.
2. **Kiểu tham số của `NTILE(k)`:** chỉ nhận những giá trị nguyên dương hợp lệ và có thể có hạn chế về biểu thức được dùng.
3. **Kiểu kết quả của `PERCENT_RANK`/`CUME_DIST`:** không suy từ cách client in số rằng SQL trả decimal có độ chính xác tùy ý.
4. **Thứ tự `NULL` mặc định:** khác biệt có thể khiến bucket bị đảo với dữ liệu thiếu.
5. **Đồng hạng xác định theo tất cả biểu thức ORDER BY:** thêm ID có thể đổi `PERCENT_RANK` và `CUME_DIST`.
6. **Window frame:** ba hàm này không sử dụng frame kiểu sliding aggregate theo cách `SUM`/`AVG` có thể dùng. Một số DBMS cấm chỉ định `ROWS`/`RANGE` với chúng; không tự thêm frame cho cả ba theo cùng một mẫu.
7. **Tên cột và alias:** để lọc theo kết quả hàm cửa sổ, dùng CTE/subquery hoặc cú pháp chuyên biệt của DBMS nếu có; không suy rằng alias kết quả luôn dùng được ngay trong `WHERE` cùng cấp.

## 19. Các lỗi thường gặp

| Cách viết/hiểu | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| “`NTILE(4)` là 4 mức **điểm** bằng nhau.” | Hàm chia **số hàng**, không chia độ rộng khoảng điểm | Dùng ngưỡng điểm hoặc phép phân vị phù hợp nếu muốn chia theo giá trị |
| “Hai người cùng điểm chắc cùng bucket.” | `NTILE` có thể cắt qua nhóm đồng điểm | Xác định chính sách tie, cân nhắc `PERCENT_RANK`/`CUME_DIST` |
| `NTILE(4) OVER (ORDER BY score DESC)` với nhiều đồng điểm và không có khóa phụ | Người nằm ở ranh giới bucket có thể thay đổi | Thêm khóa phá hòa cho `NTILE` khi cần ổn định |
| Thêm `student_id` vào `ORDER BY` của `PERCENT_RANK` chỉ để kết quả ổn định | Phá nhóm đồng điểm, thay đổi giá trị phân phối | Chỉ sắp theo những tiêu chí thực sự định nghĩa đồng hạng |
| Đọc `PERCENT_RANK = 0` là “0% điểm” | Đây là thứ hạng tương đối, không phải tỷ lệ số điểm | Ghi rõ công thức và chiều sắp |
| Đọc `CUME_DIST = 0.375` là “37.5% học viên có điểm thấp hơn” khi dùng `DESC` | Với DESC nó đếm hàng có điểm **≥** điểm hiện tại | Xác định chiều `ASC/DESC` và định nghĩa tích lũy |
| Mong `CUME_DIST` của người cao điểm nhất luôn là `1/N` | Nếu nhiều người đồng hạng đầu, giá trị là số người đồng hạng / N | Tính đến hết peer group |
| Mong `PERCENT_RANK` luôn có hàng bằng `1` | Nếu nhóm thấp nhất đồng hạng, hạng cuối có thể nhỏ hơn N | Dùng công thức `(RANK-1)/(N-1)` |
| Chia 10 bucket với nhóm chỉ 3 hàng rồi báo đủ 10 nhóm | `NTILE` không sinh hàng cho bucket rỗng | Nếu cần, tạo danh mục bucket riêng |
| Dùng hàm cửa sổ trực tiếp trong `WHERE` | Không hợp lệ ở cùng cấp truy vấn | Tính trong CTE/derived table rồi lọc ngoài |
| Lọc `WHERE score >= 70` trước cửa sổ nhưng muốn rank toàn nhóm | Dân số và mẫu số đã thay đổi | Tính rank trước, lọc sau ở outer query |
| Không dùng `PARTITION BY` nhưng lại gọi đó là rank theo nhóm | Hàm tính trên toàn bộ hàng | Ghi rõ phân vùng theo cohort/đơn vị |
| Không có `ORDER BY` cuối truy vấn nhưng kỳ vọng hàng trả theo điểm | Thứ tự output không được bảo đảm | Thêm `ORDER BY` ngoài cùng |
| Coi `NULL` là điểm cao nhất trên mọi DBMS | Default NULL ordering khác nhau | Sắp `NULL` tường minh hoặc tách dữ liệu chưa có điểm |
| Format/ROUND tỷ lệ trước khi so ngưỡng | Có thể đổi kết quả tại ranh giới | Dùng tỷ lệ gốc để lọc, format sau |
| Tin chỉ mục luôn tránh mọi sort của window functions | Kế hoạch còn phụ thuộc nhiều yếu tố | Dùng `EXPLAIN` và đo trên dữ liệu thật |

## 20. Bài tập thực hành

Sử dụng bảng `exam_scores` ban đầu. Các bài yêu cầu dự đoán kết quả đều dựa trên **14 hàng** ở mục 2. Nếu đã sửa dữ liệu khi thực hành, hãy phục hồi trước khi đối chiếu.

### Bài 1 — Viết NTILE(4) theo từng nhóm

Hãy viết truy vấn trả mã học viên, nhóm, điểm và bucket bốn phần; học viên điểm cao trước và mã nhỏ trước khi đồng điểm.

**Đáp án:**

~~~sql
SELECT
    cohort_code,
    student_id,
    score,
    NTILE(4) OVER (
        PARTITION BY cohort_code
        ORDER BY score DESC, student_id ASC
    ) AS bucket4
FROM exam_scores
ORDER BY cohort_code, score DESC, student_id;
~~~

Trong nhóm A, bucket lần lượt là `1, 1, 2, 2, 3, 3, 4, 4`. Nhóm B là `1, 1, 2, 3, 4`. Nhóm C là `1`.

### Bài 2 — Vì sao hai người cùng 90 điểm có bucket khác nhau?

Nhóm A có tám hàng và `NTILE(4)`, với `ORDER BY score DESC, student_id ASC`. Binh ID 102 và Chi ID 103 cùng 90 điểm. Vì sao một người bucket 1 và người còn lại bucket 2?

**Đáp án:** bucket chứa hai **hàng theo thứ tự**, không phải hai **mức điểm**. Binh nằm ở vị trí 2 (cuối bucket 1), Chi ở vị trí 3 (đầu bucket 2); khóa phụ ID quyết định thứ tự khi điểm trùng.

### Bài 3 — Tính PERCENT_RANK thủ công

Trong nhóm A có `N = 8`, điểm 80 của Dung có `RANK = 4`. Tính `PERCENT_RANK`.

**Đáp án:**

\[
\frac{4-1}{8-1}=\frac37\approx0.428571
\]

Không phải `4/8 = 0.5`, vì `PERCENT_RANK` dùng mẫu `N-1` và tử `RANK-1`.

### Bài 4 — Tính CUME_DIST thủ công

Nhóm A có hai người được 75 điểm và tổng cộng sáu người đạt **ít nhất** 75 điểm. Tính `CUME_DIST` cho cả hai.

**Đáp án:**

\[
\frac68=0.75
\]

Cả Ha và Lan nhận `0.75` vì cùng một nhóm đồng hạng theo `ORDER BY score DESC`.

### Bài 5 — Phân vùng chỉ có một học viên

Với Trang thuộc nhóm C, hãy nêu `NTILE(4)`, `PERCENT_RANK()` và `CUME_DIST()`.

**Đáp án:** lần lượt **1**, **0**, **1**. `PERCENT_RANK` có quy tắc đặc biệt khi `N=1`; `CUME_DIST` đếm một hàng trên tổng một hàng.

### Bài 6 — Hai chính sách “top 25%”

Trong nhóm A, so sánh:

~~~sql
-- Chính sách A: top bucket.
NTILE(4) OVER (
    PARTITION BY cohort_code
    ORDER BY score DESC, student_id
)

-- Chính sách B: rank tương đối <= 0.25.
PERCENT_RANK() OVER (
    PARTITION BY cohort_code
    ORDER BY score DESC
)
~~~

**Đáp án:** Chính sách A chọn **An và Binh** (2 người); chính sách B chọn **An, Binh và Chi** (3 người). A có thể tách người đồng điểm, B không tách đồng điểm nếu thứ tự chỉ theo `score`.

### Bài 7 — CUME_DIST ≤ 0.25 chọn ai?

Với nhóm A, những học viên nào có `CUME_DIST() <= 0.25` theo `score DESC`?

**Đáp án:** **chỉ An (95)** có `CUME_DIST = 1/8 = 0.125`. Binh và Chi cùng 90 điểm có `CUME_DIST = 3/8 = 0.375` nên không được chọn.

### Bài 8 — Phân biệt ASC và DESC

Nếu đổi tất cả hàm từ:

~~~sql
ORDER BY score DESC
~~~

thành:

~~~sql
ORDER BY score ASC
~~~

thì `PERCENT_RANK() = 0` ứng với điểm cao nhất hay thấp nhất của nhóm?

**Đáp án:** điểm **thấp nhất**. `ASC` đặt điểm thấp đầu tiên; giá trị `PERCENT_RANK` của hạng 1 là 0. `CUME_DIST` theo ASC biểu thị tỷ lệ hàng có điểm **≤** giá trị hiện tại, nếu chỉ sắp theo `score` và không `NULL`.

### Bài 9 — Lọc top bucket đúng vị trí

Viết SQL lấy học viên bucket 1 của **từng nhóm**, tránh đặt `NTILE` trực tiếp trong `WHERE` cùng cấp.

**Đáp án:**

~~~sql
WITH bucketed AS (
    SELECT
        cohort_code,
        student_id,
        student_name,
        score,
        NTILE(4) OVER (
            PARTITION BY cohort_code
            ORDER BY score DESC, student_id
        ) AS bucket4
    FROM exam_scores
)
SELECT
    cohort_code,
    student_id,
    student_name,
    score
FROM bucketed
WHERE bucket4 = 1
ORDER BY cohort_code, score DESC, student_id;
~~~

Kết quả: nhóm A có `101, 102`; B có `201, 202`; C có `301`.

### Bài 10 — Đoán sự thay đổi khi lọc trước

Nhóm A có 8 người. Nếu thêm `WHERE score >= 70` ở cùng cấp với `NTILE(4)`, còn bao nhiêu người trong phân vùng A để chia bucket?

**Đáp án:** **6 người** (95, 90, 90, 80, 75, 75). Số bucket trên phân vùng mới sẽ có kích thước **2, 2, 1, 1**; không còn dùng kích thước 2–2–2–2 của toàn bộ nhóm A.

### Bài 11 — Phân vùng B có hai người đồng hạng đầu

Nhóm B có điểm `88, 88, 70, 65, 50`. Tính `PERCENT_RANK` và `CUME_DIST` của hai người điểm 88.

**Đáp án:** cả hai có `RANK = 1` nên `PERCENT_RANK = (1-1)/(5-1) = 0`; số hàng đạt ít nhất 88 là 2 nên `CUME_DIST = 2/5 = 0.4`.

### Bài 12 — Vì sao thêm ID thay đổi PERCENT_RANK?

So sánh:

~~~sql
PERCENT_RANK() OVER (ORDER BY score DESC)

PERCENT_RANK() OVER (ORDER BY score DESC, student_id ASC)
~~~

Nếu hai học viên cùng điểm nhưng mã khác nhau, tại sao kết quả có thể khác?

**Đáp án:** peer group được xác định bởi **toàn bộ các biểu thức `ORDER BY`**. Khi có `student_id` duy nhất, hai hàng không còn đồng hạng, nên `RANK` và `PERCENT_RANK` thay đổi. Để diễn giải “cùng điểm = cùng hạng”, chỉ dùng `score` cho hàm xếp hạng tương đối.

### Bài 13 — Nhóm tất cả học viên đều 80 điểm

Một nhóm mới có bốn học viên, tất cả cùng 80 điểm. Dự đoán ba hàm với `NTILE(4)`, `PERCENT_RANK` và `CUME_DIST`.

**Đáp án:** `NTILE(4)` có thể gán lần lượt `1,2,3,4` theo khóa phá hòa; `PERCENT_RANK = 0` cho mọi hàng; `CUME_DIST = 1` cho mọi hàng. Không được coi hai hàm phân phối bằng nhau chỉ vì mọi người đồng điểm.

### Bài 14 — Mô tả chính sách trước khi viết SQL

Một chương trình học bổng yêu cầu: “Không được tách hai học viên cùng điểm vào hai hạng học bổng, dù số người trong mỗi hạng không bằng nhau.” Nên dùng `NTILE(4)` thuần túy hay một cách dựa trên nhóm đồng điểm?

**Gợi ý đáp án:** `NTILE(4)` thuần túy **không đáp ứng chắc chắn** vì có thể cắt nhóm đồng điểm ở ranh giới. Có thể dùng `PERCENT_RANK`, `CUME_DIST` hoặc thứ hạng theo **các mức điểm phân biệt**, rồi đặt ngưỡng nghiệp vụ rõ ràng. Cần quyết định nên nhận toàn bộ nhóm đồng điểm ở ranh giới hay loại cả nhóm, và chấp nhận số lượng người có thể lệch mục tiêu.

## 21. Tổng kết

Ba hàm đều dựa vào `OVER (PARTITION BY ... ORDER BY ...)`, nhưng không thể dùng thay thế nhau:

- **`NTILE(k)`**: chia các **hàng đã sắp** thành `k` bucket có số lượng gần bằng nhau. Hữu ích để phân nhóm theo số người/giao dịch nhưng **có thể chia cắt hàng đồng hạng**.
- **`PERCENT_RANK()`**: chuẩn hóa vị trí `RANK` bằng công thức `(RANK - 1) / (N - 1)`; phân vùng một hàng cho kết quả `0`. Hữu ích để diễn giải **thứ hạng tương đối**, không phải phần trăm số điểm.
- **`CUME_DIST()`**: trả tỷ lệ hàng nằm **trước hoặc cùng nhóm đồng hạng** trong thứ tự. Với `score DESC`, đó là tỷ lệ hàng có điểm **≥ điểm hiện tại**; phân vùng một hàng cho kết quả `1`.

Khi sử dụng trong ứng dụng, hãy xác định **phân vùng so sánh**, **chiều sắp xếp**, **quy tắc đồng điểm**, **cách xử lý NULL**, **mức hạt dữ liệu** và **mục đích của ngưỡng phần trăm** trước khi chọn hàm. Với yêu cầu lọc kết quả cửa sổ, tính hàm trong CTE hoặc truy vấn con rồi lọc ở lớp ngoài. Với yêu cầu tối ưu, kiểm tra chỉ mục và kế hoạch trên dữ liệu thật.

**Câu hỏi quyết định là:** “Ta muốn chia **số hàng** thành những nhóm gần bằng nhau, đo **vị trí thứ hạng**, hay đo **tỷ lệ tích lũy**?” Trả lời đúng câu hỏi đó sẽ giúp chọn chính xác giữa `NTILE`, `PERCENT_RANK` và `CUME_DIST`.
