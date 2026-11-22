# ntile, percent_rank, cume_dist và phân bố dữ liệu trong PostgreSQL

Một báo cáo chỉ có `AVG(score)` hoặc `MAX(score)` thường chưa đủ để hiểu **phân bố dữ liệu**. Hai nhóm khách hàng có cùng doanh số trung bình vẫn có thể rất khác nhau: nhóm thứ nhất gồm đa số khách có mức chi tiêu gần nhau; nhóm thứ hai chỉ có vài khách chi tiêu cực cao và rất nhiều khách chi tiêu thấp. Để nhìn thấy sự khác biệt này, ta thường cần xếp hạng, chia nhóm theo vị trí và xác định một quan sát nằm ở đâu trong phân bố.

PostgreSQL cung cấp các hàm cửa sổ (*window functions*) đặc biệt hữu ích cho bài toán này:

- **`NTILE(n)`:** chia các hàng đã được sắp xếp trong một partition thành tối đa `n` nhóm gần đều nhau về **số hàng**.
- **`PERCENT_RANK()`:** đo vị trí xếp hạng tương đối từ 0 đến 1, dựa trên `RANK()` và tổng số hàng.
- **`CUME_DIST()`:** tính tỷ lệ tích lũy các hàng nằm trước hoặc ngang giá trị hiện tại trong thứ tự đã chọn, có tính đến toàn bộ nhóm bằng nhau (*peers*).

Ba hàm nhìn có vẻ đều liên quan phần trăm, nhưng **không trả về cùng một khái niệm**. `NTILE(4)` không tính “giá trị phân vị 25%, 50%, 75%”; `PERCENT_RANK()` không phải tỷ lệ hàng nhỏ hơn hoặc bằng giá trị hiện tại; và `CUME_DIST()` không tự chia dữ liệu thành bốn nhóm có số người bằng nhau.

Bài học này sử dụng dữ liệu có điểm số trùng nhau, nhiều phân khúc và một phân khúc chỉ có một quan sát để làm rõ khác biệt. Cuối bài, bạn có thể áp dụng vào phân nhóm khách hàng, đánh giá điểm thi, phân tích doanh số và xác minh ranh giới các nhóm khi dữ liệu có nhiều giá trị bằng nhau.

## 1. Kiến thức cần có: hàm cửa sổ và OVER

Khác với `GROUP BY` thông thường, hàm cửa sổ thường **giữ lại từng hàng nguồn** và thêm các cột tính toán theo tập hàng liên quan.

Ví dụ cú pháp chung:

```sql
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score ASC, measure_id ASC
    ) AS bucket
FROM distribution_lab.measurements;
```

Ý nghĩa:

| Thành phần | Vai trò |
| --- | --- |
| `NTILE(4)` | Yêu cầu chia thành tối đa 4 nhóm theo thứ tự. |
| `OVER (...)` | Xác định cửa sổ của hàm. |
| `PARTITION BY segment` | Tính **riêng trong từng phân khúc**; sang phân khúc khác bắt đầu lại. |
| `ORDER BY score ASC` | Điểm thấp đứng trước điểm cao. |
| `measure_id ASC` | Tiêu chí phụ cho thứ tự ổn định khi các điểm bằng nhau. |
| `AS bucket` | Đặt tên cột kết quả, không tạo cột vật lý trong bảng. |

`PARTITION BY` là tùy chọn. Nếu bỏ nó, toàn bộ hàng đầu vào được coi là một partition cho hàm cửa sổ. `ORDER BY` của cửa sổ cũng có cú pháp riêng và phải được thiết kế có chủ đích.

### 1.1. PARTITION khác GROUP BY

Với:

```sql
SELECT segment, AVG(score) AS average_score
FROM distribution_lab.measurements
GROUP BY segment;
```

mỗi `segment` chỉ còn một hàng kết quả.

Với:

```sql
SELECT
    measure_id,
    segment,
    score,
    AVG(score) OVER (PARTITION BY segment) AS segment_average
FROM distribution_lab.measurements;
```

mỗi quan sát vẫn có một hàng; giá trị trung bình của phân khúc được lặp tương ứng trên các hàng của phân khúc đó.

Các hàm `NTILE`, `PERCENT_RANK` và `CUME_DIST` thuộc nhóm hàm cửa sổ, nên mục tiêu của chúng là **gắn thông tin vị trí/phân bố vào từng hàng**, không phải gom toàn bộ hàng thành một kết quả duy nhất.

### 1.2. ORDER BY trong OVER khác ORDER BY của kết quả

```sql
SELECT
    measure_id,
    score,
    PERCENT_RANK() OVER (ORDER BY score) AS relative_rank
FROM distribution_lab.measurements
ORDER BY measure_id DESC;
```

`ORDER BY score` bên trong `OVER` quyết định cách tính thứ hạng. `ORDER BY measure_id DESC` ở cuối quyết định thứ tự **hiển thị các hàng sau khi tính**. Không nên xem hai mệnh đề này là cùng một thứ.

Nếu câu SQL không có `ORDER BY` cuối cùng, thứ tự hàng trả về không được PostgreSQL bảo đảm, ngay cả khi cửa sổ đã có `ORDER BY`.

## 2. Dữ liệu thực hành: có điểm trùng và phân khúc nhỏ

Ta tạo một bảng điểm đại diện cho một quan sát của một đối tượng ở mỗi thời điểm. Ví dụ chỉ nhằm giải thích thống kê, không phản ánh thang đo đánh giá nhân sự hay khách hàng cụ thể.

### 2.1. Tạo schema và bảng

Chạy trong database thực hành:

```sql
CREATE SCHEMA IF NOT EXISTS distribution_lab;

CREATE TABLE distribution_lab.measurements (
    measure_id bigint PRIMARY KEY,
    segment text NOT NULL,
    score numeric(10, 2),
    observed_on date NOT NULL
);
```

Chèn 14 quan sát:

```sql
INSERT INTO distribution_lab.measurements
    (measure_id, segment, score, observed_on)
VALUES
    (101, 'north',  50.00, DATE '2026-10-01'),
    (102, 'north',  50.00, DATE '2026-10-02'),
    (103, 'north',  70.00, DATE '2026-10-03'),
    (104, 'north',  90.00, DATE '2026-10-04'),
    (105, 'north',  90.00, DATE '2026-10-05'),
    (106, 'north',  90.00, DATE '2026-10-06'),
    (107, 'north', 110.00, DATE '2026-10-07'),
    (108, 'north', 140.00, DATE '2026-10-08'),

    (201, 'south',  30.00, DATE '2026-10-01'),
    (202, 'south',  30.00, DATE '2026-10-02'),
    (203, 'south',  40.00, DATE '2026-10-03'),
    (204, 'south',  80.00, DATE '2026-10-04'),
    (205, 'south', 100.00, DATE '2026-10-05'),

    (301, 'pilot',  95.00, DATE '2026-10-01');
```

Đọc dữ liệu:

```sql
SELECT measure_id, segment, score
FROM distribution_lab.measurements
ORDER BY segment, score, measure_id;
```

Danh sách điểm theo thứ tự tăng:

| Phân khúc | Số hàng | Giá trị điểm theo thứ tự tăng |
| --- | ---: | --- |
| north | 8 | 50, 50, 70, 90, 90, 90, 110, 140 |
| south | 5 | 30, 30, 40, 80, 100 |
| pilot | 1 | 95 |

Điều đáng chú ý:

- `north` có hai lần 50 và ba lần 90; đây là các **peer groups** nếu sắp xếp chỉ theo `score`.
- `south` có hai lần 30.
- `pilot` chỉ có một quan sát; một số công thức xếp hạng cần xử lý mẫu số bằng 0.

Nếu chạy lại toàn bộ `INSERT`, PostgreSQL sẽ báo khóa chính trùng. Để thực hành lại, dùng schema lab mới hoặc dọn dữ liệu có kiểm soát; không xóa schema production.

## 3. Peer group: các hàng bằng nhau theo ORDER BY cửa sổ

Đối với các hàm xếp hạng, **peers** là các hàng không phân biệt được theo **toàn bộ biểu thức `ORDER BY` của cửa sổ**.

Xét dữ liệu north:

```text
ID       Score
101       50  ┐
102       50  ┘ cùng peer group khi ORDER BY score
103       70
104       90  ┐
105       90  ├ cùng peer group
106       90  ┘
107      110
108      140
```

Nếu dùng:

```sql
PERCENT_RANK() OVER (PARTITION BY segment ORDER BY score)
```

thì các hàng có điểm 90 của north nhận **cùng percent_rank**.

Nhưng nếu dùng:

```sql
PERCENT_RANK() OVER (
    PARTITION BY segment
    ORDER BY score, measure_id
)
```

thì các điểm 90 không còn là peers do `measure_id` khác nhau. Khi này mỗi hàng có thứ tự duy nhất và các kết quả percentile sẽ khác.

**Cảnh báo quan trọng:** thêm primary key vào `ORDER BY` của `PERCENT_RANK` hoặc `CUME_DIST` không chỉ để ổn định hiển thị; nó **thay đổi chính nhóm peers và công thức thống kê**. Có thể thêm khóa phụ cho `NTILE` để quyết định hàng nào vào bucket ranh giới, nhưng nên giữ `ORDER BY score` riêng cho các chỉ số cần coi các điểm bằng nhau là cùng vị trí.

## 4. NTILE(n): chia hàng thành các nhóm gần đều

`NTILE(n)` gán cho mỗi hàng một số bucket từ 1 đến `n` dựa trên thứ tự sắp xếp trong partition.

```sql
SELECT
    measure_id,
    score,
    NTILE(4) OVER (
        ORDER BY score ASC, measure_id ASC
    ) AS quartile_bucket
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Kết quả:

| measure_id | score | quartile_bucket |
| ---: | ---: | ---: |
| 101 | 50 | 1 |
| 102 | 50 | 1 |
| 103 | 70 | 2 |
| 104 | 90 | 2 |
| 105 | 90 | 3 |
| 106 | 90 | 3 |
| 107 | 110 | 4 |
| 108 | 140 | 4 |

Tám hàng được chia thành bốn bucket, mỗi bucket hai hàng. Vì sắp xếp `ASC`, **bucket 1 chứa các hàng điểm thấp**, bucket 4 chứa hàng điểm cao.

### 4.1. Quy tắc kích thước bucket

Với `N` hàng và `B` bucket yêu cầu:

- Mỗi bucket được tạo có kích thước gần bằng `N/B`.
- Số hàng giữa các bucket không chênh nhau quá một hàng.
- Nếu phép chia có dư, những bucket đầu nhận thêm một hàng.
- Nếu `N < B`, chỉ có tối đa `N` bucket chứa hàng; một số số bucket phía sau không xuất hiện trong kết quả.

Ví dụ:

| Số hàng N | `NTILE(B)` | Kích thước các bucket có hàng |
| ---: | --- | --- |
| 8 | `NTILE(4)` | 2, 2, 2, 2 |
| 8 | `NTILE(3)` | 3, 3, 2 |
| 5 | `NTILE(4)` | 2, 1, 1, 1 |
| 5 | `NTILE(2)` | 3, 2 |
| 3 | `NTILE(5)` | 1, 1, 1; bucket 4 và 5 không có hàng |
| 1 | `NTILE(4)` | 1; chỉ bucket 1 xuất hiện |

Giá trị `n` phải là số bucket hợp lệ, lớn hơn 0. `NTILE(0)` hoặc bucket count âm không có ý nghĩa và bị PostgreSQL từ chối.

### 4.2. Chia thành ba nhóm

```sql
SELECT
    measure_id,
    score,
    NTILE(3) OVER (ORDER BY score, measure_id) AS tercile
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Với 8 hàng, bucket lần lượt có 3, 3, 2 hàng:

```text
bucket 1: 50, 50, 70
bucket 2: 90, 90, 90
bucket 3: 110, 140
```

Có thể dùng `NTILE(10)` cho decile hoặc `NTILE(100)` cho nhóm xấp xỉ phần trăm theo số hàng, nhưng dữ liệu phải đủ lớn để các nhóm có ý nghĩa thống kê.

### 4.3. NTILE có thể chia tách các giá trị bằng nhau

Ở kết quả `NTILE(4)`, ba hàng điểm 90 không cùng bucket: ID 104 ở bucket 2, ID 105 và 106 ở bucket 3.

Đó **không phải lỗi**. `NTILE` ưu tiên phân chia gần đều về số hàng; nó không hứa giữ những điểm bằng nhau trong một bucket.

Nếu business rule yêu cầu “cùng điểm luôn cùng nhóm”, không thể mặc nhiên dùng `NTILE` trên từng hàng rồi coi kết quả công bằng. Phần sau sẽ trình bày cách chia theo **giá trị điểm distinct** hoặc dùng ngưỡng có tính tới peers.

### 4.4. NTILE không phải ngưỡng giá trị có khoảng cách bằng nhau

Với north, bucket 1 gồm 50–50, bucket 2 gồm 70–90, bucket 3 gồm 90–90, bucket 4 gồm 110–140. Khoảng điểm của từng bucket rất khác nhau.

NTILE chia theo **số quan sát**, không theo độ rộng khoảng điểm. Nếu muốn chia thang điểm [0, 160) thành các khoảng độ rộng bằng nhau, có thể dùng `width_bucket` hoặc `CASE` theo ranh giới — đó là bài toán khác.

## 5. PERCENT_RANK(): vị trí tương đối của thứ hạng

`PERCENT_RANK()` phản ánh thứ hạng của một hàng **so với số hàng trong partition**, theo công thức:

\[
\operatorname{percent\_rank}(x)=
\begin{cases}
0, & N=1 \\\\
\dfrac{\operatorname{rank}(x)-1}{N-1}, & N>1
\end{cases}
\]

Ở đây:

- `N`: số hàng trong partition.
- `RANK()`: thứ hạng của hàng theo `ORDER BY`, bắt đầu từ 1.
- Những hàng bằng nhau theo ORDER BY là **peers**, có cùng `RANK()` và `PERCENT_RANK()`.

### 5.1. Tính bằng tay trên north

Điểm tăng dần: `50, 50, 70, 90, 90, 90, 110, 140`. Có 8 hàng nên mẫu số là 7.

| Điểm | Hàng có điểm này | RANK | PERCENT_RANK theo công thức |
| ---: | ---: | ---: | ---: |
| 50 | 2 | 1 | `(1-1)/7 = 0` |
| 70 | 1 | 3 | `(3-1)/7 ≈ 0.285714` |
| 90 | 3 | 4 | `(4-1)/7 ≈ 0.428571` |
| 110 | 1 | 7 | `(7-1)/7 ≈ 0.857143` |
| 140 | 1 | 8 | `(8-1)/7 = 1` |

Vì 50 xuất hiện hai lần, thứ hạng tiếp theo của 70 là **3**, không phải 2. Vì 90 xuất hiện ba lần, thứ hạng tiếp theo của 110 là **7**, không phải 5.

### 5.2. Truy vấn PERCENT_RANK

```sql
SELECT
    measure_id,
    score,
    RANK() OVER (ORDER BY score) AS score_rank,
    ROUND(
        (PERCENT_RANK() OVER (ORDER BY score))::numeric,
        6
    ) AS percent_rank_value
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Kết quả dự kiến:

| measure_id | score | score_rank | percent_rank_value |
| ---: | ---: | ---: | ---: |
| 101 | 50 | 1 | 0.000000 |
| 102 | 50 | 1 | 0.000000 |
| 103 | 70 | 3 | 0.285714 |
| 104 | 90 | 4 | 0.428571 |
| 105 | 90 | 4 | 0.428571 |
| 106 | 90 | 4 | 0.428571 |
| 107 | 110 | 7 | 0.857143 |
| 108 | 140 | 8 | 1.000000 |

Hàm trả kiểu `double precision`; ví dụ ép qua `numeric` để dùng `ROUND(..., 6)` cho hiển thị. Kết quả phần thập phân cần được hiểu theo độ chính xác số học dấu chấm động và cách format.

### 5.3. PERCENT_RANK không nhất thiết có giá trị 1

Hãy thử ba hàng:

```sql
WITH sample(score) AS (
    VALUES (10), (20), (20)
)
SELECT
    score,
    RANK() OVER (ORDER BY score) AS rnk,
    PERCENT_RANK() OVER (ORDER BY score) AS pr
FROM sample
ORDER BY score;
```

Kết quả:

```text
score  rank  percent_rank
10      1        0.0
20      2        0.5
20      2        0.5
```

Hàng có điểm cao nhất là 20 nhưng `PERCENT_RANK` chỉ bằng 0.5, không bằng 1, vì nhóm điểm cao nhất có **hai peers**, bắt đầu ở vị trí rank 2 trong ba hàng.

Do đó không nên kiểm tra “điểm cao nhất phải có percent_rank = 1”. Chỉ khi rank cuối bằng N (ví dụ điểm cao nhất là duy nhất) thì công thức mới cho 1.

### 5.4. Partition chỉ có một hàng

Khi `N=1`, công thức thông thường có mẫu số 0. PostgreSQL định nghĩa `PERCENT_RANK() = 0` cho partition một hàng.

```sql
SELECT
    segment,
    score,
    PERCENT_RANK() OVER (PARTITION BY segment ORDER BY score) AS pr
FROM distribution_lab.measurements
WHERE segment = 'pilot';
```

Kết quả `pr = 0`. Không suy diễn rằng đối tượng này “thuộc 0% kém nhất”; nó đơn giản là **trường hợp một quan sát không có thứ hạng tương đối có ý nghĩa**.

## 6. CUME_DIST(): phân phối tích lũy

`CUME_DIST()` viết tắt của *cumulative distribution*. Với thứ tự tăng theo điểm, nó trả **tỷ lệ số hàng có điểm nhỏ hơn hoặc bằng điểm hiện tại**, tính theo toàn bộ partition.

Nếu sắp xếp theo thứ tự tùy chọn, cách diễn đạt chính xác hơn là **số hàng đứng trước hoặc thuộc nhóm peers hiện tại theo thứ tự ấy**, chia cho tổng hàng.

Với một nhóm điểm bằng nhau, tất cả peers có cùng kết quả và đều được tính vào tử số:

\[
\operatorname{cume\_dist}(x)
= \frac{\text{số hàng đứng trước hoặc thuộc peer group của }x}{N}
\]

### 6.1. Tính bằng tay trên north

| Điểm | Số hàng nhỏ hơn hoặc bằng điểm này | CUME_DIST |
| ---: | ---: | ---: |
| 50 | 2 / 8 | 0.250 |
| 70 | 3 / 8 | 0.375 |
| 90 | 6 / 8 | 0.750 |
| 110 | 7 / 8 | 0.875 |
| 140 | 8 / 8 | 1.000 |

Ba hàng điểm 90 cùng nhận **0.75**, vì đã có 6 trong 8 hàng có điểm nhỏ hơn hoặc bằng 90.

### 6.2. Truy vấn

```sql
SELECT
    measure_id,
    score,
    ROUND(
        (CUME_DIST() OVER (ORDER BY score))::numeric,
        4
    ) AS cumulative_share
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Kết quả:

| measure_id | score | cumulative_share |
| ---: | ---: | ---: |
| 101 | 50 | 0.2500 |
| 102 | 50 | 0.2500 |
| 103 | 70 | 0.3750 |
| 104 | 90 | 0.7500 |
| 105 | 90 | 0.7500 |
| 106 | 90 | 0.7500 |
| 107 | 110 | 0.8750 |
| 108 | 140 | 1.0000 |

### 6.3. Miền giá trị

Với một partition có N hàng, `CUME_DIST()` luôn lớn hơn 0 và không vượt 1. Giá trị nhỏ nhất ít nhất là `1/N`; nếu nhóm điểm đầu có nhiều peers, giá trị đầu còn lớn hơn.

Khác `PERCENT_RANK()`, **nhóm peers cuối luôn có `CUME_DIST() = 1`**, vì tất cả hàng đều nằm trước hoặc thuộc nhóm cuối.

### 6.4. Một partition chỉ có một hàng

```sql
SELECT
    segment,
    score,
    CUME_DIST() OVER (PARTITION BY segment ORDER BY score) AS cd
FROM distribution_lab.measurements
WHERE segment = 'pilot';
```

Kết quả là **1**, vì một hàng đó chiếm toàn bộ partition. Điều này khác `PERCENT_RANK() = 0` trong cùng trường hợp.

## 7. Đặt ba hàm cạnh nhau trên cùng dữ liệu

Đây là truy vấn tổng hợp quan trọng nhất của bài:

```sql
SELECT
    measure_id,
    score,
    RANK() OVER (ORDER BY score) AS rnk,
    NTILE(4) OVER (
        ORDER BY score, measure_id
    ) AS ntile_4,
    ROUND(
        (PERCENT_RANK() OVER (ORDER BY score))::numeric,
        4
    ) AS percent_rank,
    ROUND(
        (CUME_DIST() OVER (ORDER BY score))::numeric,
        4
    ) AS cume_dist
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

| measure_id | score | rnk | ntile_4 | percent_rank | cume_dist |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 50 | 1 | 1 | 0.0000 | 0.2500 |
| 102 | 50 | 1 | 1 | 0.0000 | 0.2500 |
| 103 | 70 | 3 | 2 | 0.2857 | 0.3750 |
| 104 | 90 | 4 | 2 | 0.4286 | 0.7500 |
| 105 | 90 | 4 | 3 | 0.4286 | 0.7500 |
| 106 | 90 | 4 | 3 | 0.4286 | 0.7500 |
| 107 | 110 | 7 | 4 | 0.8571 | 0.8750 |
| 108 | 140 | 8 | 4 | 1.0000 | 1.0000 |

Ba kết luận quan trọng:

1. **NTILE:** mục tiêu là số hàng trong mỗi bucket gần bằng nhau, nên các điểm 90 có thể bị chia ra.
2. **PERCENT_RANK:** dùng vị trí **bắt đầu** của nhóm điểm bằng nhau thông qua `RANK`, nên ba điểm 90 cùng 0.4286.
3. **CUME_DIST:** dùng vị trí **kết thúc** của nhóm điểm bằng nhau, nên ba điểm 90 cùng 0.75.

### 7.1. Sơ đồ trực giác

```text
North, thứ tự score tăng dần:

Vị trí:       1    2    3    4    5    6    7    8
Điểm:        50   50   70   90   90   90  110  140
NTILE(4):     1    1    2    2    3    3    4    4

Nhóm 90 chiếm các vị trí 4,5,6:
  RANK bắt đầu tại vị trí 4.
  PERCENT_RANK = (4 - 1) / (8 - 1) = 3/7
  CUME_DIST    = 6 / 8 = 0.75
```

Đây là hình ảnh hữu ích khi giải thích kết quả với product owner hoặc data analyst: điểm giống nhau nhưng bucket NTILE khác nhau không phải do PostgreSQL tính sai, mà do **định nghĩa metric khác nhau**.

## 8. Kiểm chứng công thức bằng RANK, COUNT và peer count

Ta có thể tự dựng `PERCENT_RANK` và `CUME_DIST` theo công thức để học cách chúng hoạt động:

```sql
WITH positions AS (
    SELECT
        measure_id,
        segment,
        score,
        RANK() OVER (
            PARTITION BY segment ORDER BY score
        ) AS rank_position,
        COUNT(*) OVER (
            PARTITION BY segment
        ) AS n,
        COUNT(*) OVER (
            PARTITION BY segment, score
        ) AS peer_count
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
)
SELECT
    measure_id,
    segment,
    score,
    rank_position,
    n,
    peer_count,
    CASE
        WHEN n = 1 THEN 0::numeric
        ELSE (rank_position - 1)::numeric / (n - 1)
    END AS manual_percent_rank,
    (rank_position + peer_count - 1)::numeric / n
        AS manual_cume_dist
FROM positions
ORDER BY segment, score, measure_id;
```

Giải thích:

- `rank_position - 1` là số vị trí trước vị trí bắt đầu của peer group.
- `rank_position + peer_count - 1` là vị trí kết thúc của peer group theo cách đếm hàng.
- `n` là số quan sát được so sánh trong cùng phân khúc.
- `CASE WHEN n = 1 THEN 0` xử lý đúng trường hợp một quan sát, tránh phép chia cho 0.

Với north, peer group điểm 90 có `rank_position=4`, `peer_count=3`, `n=8`. Do đó:

```text
manual_percent_rank = (4 - 1) / (8 - 1) = 3/7
manual_cume_dist    = (4 + 3 - 1) / 8 = 6/8
```

Nhớ rằng biểu thức `COUNT(*) OVER (PARTITION BY segment, score)` chỉ thực sự đại diện peer group vì hàm xếp hạng trong ví dụ cũng dùng **duy nhất score** để sắp xếp trong từng segment. Nếu đổi `ORDER BY` của hàm xếp hạng, công thức peer count phải đổi theo.

## 9. PARTITION BY: tính phân bố riêng từng nhóm

Khi muốn đánh giá điểm của một người **so với những người cùng khu vực** thay vì toàn bộ công ty, sử dụng `PARTITION BY segment`.

```sql
SELECT
    measure_id,
    segment,
    score,
    COUNT(*) OVER (
        PARTITION BY segment
    ) AS segment_size,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score ASC, measure_id ASC
    ) AS score_bucket,
    ROUND(
        (PERCENT_RANK() OVER (
            PARTITION BY segment
            ORDER BY score ASC
        ))::numeric,
        4
    ) AS relative_position,
    ROUND(
        (CUME_DIST() OVER (
            PARTITION BY segment
            ORDER BY score ASC
        ))::numeric,
        4
    ) AS cumulative_share
FROM distribution_lab.measurements
ORDER BY segment, score, measure_id;
```

Mỗi `segment` được tính độc lập. Đặc biệt:

- **north (8 hàng):** `NTILE(4)` có bốn bucket, mỗi bucket hai hàng.
- **south (5 hàng):** các bucket có kích thước 2, 1, 1, 1.
- **pilot (1 hàng):** `score_bucket=1`, `relative_position=0`, `cumulative_share=1`.

### 9.1. Kết quả south tính bằng tay

South có điểm `30, 30, 40, 80, 100`:

| measure_id | score | ntile_4 | percent_rank | cume_dist |
| ---: | ---: | ---: | ---: | ---: |
| 201 | 30 | 1 | 0.0000 | 0.4000 |
| 202 | 30 | 1 | 0.0000 | 0.4000 |
| 203 | 40 | 2 | 0.5000 | 0.6000 |
| 204 | 80 | 3 | 0.7500 | 0.8000 |
| 205 | 100 | 4 | 1.0000 | 1.0000 |

Điểm 40 có `rank=3`, nên `percent_rank=(3-1)/(5-1)=0.5`; ba trong năm quan sát có điểm không vượt 40, nên `cume_dist=3/5=0.6`.

### 9.2. So sánh theo nhóm khác với so sánh toàn bộ

Một điểm 95 ở pilot có thể là điểm cao hơn khá nhiều người ở north/south. Nhưng do pilot có một hàng, `PERCENT_RANK() OVER (PARTITION BY segment)` của nó bằng 0.

Đây không phải mâu thuẫn: một chỉ số đo vị trí **trong nhóm pilot**, còn so toàn bảng là một bài toán khác. Khi công bố percentiles, luôn nói rõ **quần thể tham chiếu**.

### 9.3. PARTITION BY không yêu cầu bảng được phân vùng vật lý

`PARTITION BY` của window function chỉ chia tập hàng **logic cho phép tính**. Nó không đồng nghĩa PostgreSQL table partitioning, cũng không tự tạo bảng con hoặc index.

Không nên nhầm “chia nhóm tính toán theo segment” với cơ chế partitioned table dùng cho quản lý lưu trữ và partition pruning.

## 10. ORDER BY ASC và DESC: chiều xếp hạng đổi ý nghĩa

Với `ORDER BY score ASC`:

- Điểm thấp đứng đầu.
- `NTILE(4)=1` là nhóm điểm thấp.
- `PERCENT_RANK=0` gắn với nhóm điểm thấp nhất.
- `CUME_DIST` tương ứng tỷ lệ điểm nhỏ hơn hoặc bằng điểm hiện tại.

Với `ORDER BY score DESC`:

- Điểm cao đứng đầu.
- `NTILE(4)=1` là nhóm điểm cao.
- `PERCENT_RANK=0` gắn với **nhóm điểm cao nhất**.
- `CUME_DIST` tương ứng tỷ lệ hàng đứng trước hoặc cùng nhóm theo thứ tự giảm, tức thường là tỷ lệ điểm **lớn hơn hoặc bằng** điểm hiện tại.

Ví dụ:

```sql
SELECT
    measure_id,
    score,
    NTILE(4) OVER (
        ORDER BY score DESC, measure_id
    ) AS high_first_bucket,
    ROUND(
        (PERCENT_RANK() OVER (ORDER BY score DESC))::numeric,
        4
    ) AS high_first_percent_rank,
    ROUND(
        (CUME_DIST() OVER (ORDER BY score DESC))::numeric,
        4
    ) AS high_first_cume_dist
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score DESC, measure_id;
```

Trong north, điểm 140 đứng đầu: `high_first_bucket=1`, `high_first_percent_rank=0` và `high_first_cume_dist=1/8=0.125`.

**Không ghi nhãn chung “percentile càng cao càng tốt” nếu câu SQL đang ORDER BY DESC.** Hãy nêu rõ chiều đo: thứ hạng tương đối tính từ phía thấp nhất hay phía cao nhất.

## 11. Khi điểm trùng nhau: NTILE và công bằng phân nhóm

Một hệ thống khen thưởng quy định:

> Những người có cùng điểm phải thuộc cùng nhóm thưởng.

Nếu dùng:

```sql
NTILE(4) OVER (ORDER BY score DESC, measure_id)
```

thì khi nhóm các điểm 90 đi qua ranh giới bucket, những người có cùng điểm có thể rơi vào các nhóm khác nhau. Việc thêm `measure_id` giúp **ổn định quyết định chia**, nhưng không đáp ứng điều kiện **cùng điểm cùng nhóm**.

### 11.1. Phương án A: NTILE trên các giá trị điểm DISTINCT

Ta có thể chia **các mức điểm khác nhau** thành bốn bucket rồi nối về từng hàng:

```sql
WITH distinct_scores AS (
    SELECT DISTINCT segment, score
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
),
score_buckets AS (
    SELECT
        segment,
        score,
        NTILE(4) OVER (
            PARTITION BY segment
            ORDER BY score ASC
        ) AS bucket_by_distinct_score
    FROM distinct_scores
)
SELECT
    m.measure_id,
    m.segment,
    m.score,
    b.bucket_by_distinct_score
FROM distribution_lab.measurements AS m
JOIN score_buckets AS b
    ON b.segment = m.segment
   AND b.score = m.score
ORDER BY m.segment, m.score, m.measure_id;
```

Lúc này **mọi hàng cùng score trong một segment đều nhận cùng bucket**. Đổi lại, số người trong mỗi bucket có thể **chênh lệch lớn**, bởi NTILE cân bằng số **mức điểm distinct**, không cân bằng số người.

Trên north có các mức `50, 70, 90, 110, 140`. Chia bốn bucket theo mức distinct sẽ có:

```text
bucket 1: mức 50, 70   -> 3 người
bucket 2: mức 90       -> 3 người
bucket 3: mức 110      -> 1 người
bucket 4: mức 140      -> 1 người
```

Quy tắc này đáp ứng yêu cầu giữ peers nhưng không phải cách duy nhất hợp lý. Việc chọn quy tắc nhóm nên dựa vào chính sách nghiệp vụ.

### 11.2. Phương án B: dùng ngưỡng percentiles và chấp nhận nhóm không đều

Nếu cần “mọi người có điểm từ một ngưỡng trở lên đều cùng được chọn”, tính ngưỡng điểm rồi áp dụng điều kiện so sánh trên **điểm**, không chia từng hàng bằng NTILE.

Ví dụ chọn mọi người có `score >= 110`:

```sql
SELECT measure_id, score
FROM distribution_lab.measurements
WHERE segment = 'north'
  AND score >= 110
ORDER BY score DESC, measure_id;
```

Kết quả ID 107 và 108. Nếu nhiều người cùng đạt 110, tất cả đều được nhận theo cùng quy tắc, kể cả khi số người được chọn lớn hơn chỉ tiêu kỳ vọng.

Với một ngưỡng được xác định bằng `percentile_cont` hoặc `percentile_disc`, cũng cần tuyên bố rõ dùng `>` hay `>=`, và định nghĩa lựa chọn có thể vượt quota khi có ties.

### 11.3. Phương án C: cần đúng quota dù có hòa điểm

Nếu chính sách **bắt buộc chọn đúng K hàng**, cần tiêu chí phụ công khai để phá hòa: thời điểm đạt điểm, kết quả đánh giá khác, hoặc một cơ chế bốc thăm minh bạch. Khi đó `ROW_NUMBER()` hoặc `NTILE` với `ORDER BY` đầy đủ có thể thực hiện lựa chọn ổn định.

Nhưng phải thừa nhận đây là một **quy tắc xếp hạng bổ sung**, không còn “chỉ căn cứ score”. Dùng ID kỹ thuật âm thầm để phá hòa trong quyết định nhân sự/tài chính có thể gây bất công.

## 12. PERCENT_RANK và CUME_DIST có phải “phần trăm đạt được” không?

Không. `0.8571` do `PERCENT_RANK()` trả về **không có nghĩa điểm đạt 85.71% thang điểm tối đa**.

Ví dụ trên north:

- Điểm 110: `PERCENT_RANK≈0.8571`.
- Điểm 110: `CUME_DIST=0.875`.

Hai giá trị phản ánh **vị trí của quan sát trong tập 8 hàng**, không phản ánh tỉ lệ 110/140, 110/100 hoặc thang điểm tối đa nào.

Nếu điểm là doanh thu tuyệt đối, các metric này phản ánh **thứ hạng phân bố doanh thu**, không phải tỷ lệ đóng góp vào tổng doanh thu. Muốn “khách chiếm bao nhiêu phần trăm tổng doanh thu”, dùng `SUM(score)` trên tổng nhóm và phép chia phù hợp.

### 12.1. CUME_DIST so với empirical CDF

Khi `ORDER BY score ASC` và không có NULL trong dữ liệu điểm, `CUME_DIST(score)` tương ứng hàm phân phối tích lũy thực nghiệm tại chính mức điểm đó:

\[
\widehat F(s) = \frac{\#\{x_i \le s\}}{N}
\]

Với điểm 90, `F(90) = 6/8 = 0.75`. Điều này hữu ích khi hỏi: **“Bao nhiêu phần trăm các quan sát có điểm không vượt mức này?”**

`PERCENT_RANK` lại dựa trên **RANK bắt đầu của peer group** nên với 90 chỉ khoảng 0.4286. Nó không trả đúng `F(90)` khi có nhiều giá trị bằng nhau.

### 12.2. Điểm cực trị

`PERCENT_RANK` của nhóm đầu luôn 0. `CUME_DIST` của nhóm cuối luôn 1. Với nhiều peers ở điểm thấp nhất, `CUME_DIST` của mức thấp nhất có thể khá lớn; điều đó chỉ cho thấy **nhiều quan sát cùng có mức thấp nhất**.

Ví dụ south có hai điểm 30 trong 5 hàng, nên `CUME_DIST(30)=2/5=0.4` chứ không phải 0.2.

## 13. Lọc theo percent_rank hoặc cume_dist

Các hàm cửa sổ không dùng trực tiếp ở `WHERE` của cùng cấp truy vấn như:

```sql
-- Không hợp lệ:
-- SELECT measure_id, score
-- FROM distribution_lab.measurements
-- WHERE PERCENT_RANK() OVER (ORDER BY score) >= 0.75;
```

Lý do: `WHERE` của cấp truy vấn đó được xử lý trước các phép tính cửa sổ theo ngữ nghĩa SQL. Nếu muốn **tính phân bố toàn nhóm rồi lọc kết quả**, dùng CTE hoặc subquery.

### 13.1. Chỉ lấy quan sát thuộc phía điểm cao

```sql
WITH ranked AS (
    SELECT
        measure_id,
        segment,
        score,
        PERCENT_RANK() OVER (
            PARTITION BY segment
            ORDER BY score ASC
        ) AS pr
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
)
SELECT measure_id, segment, score, pr
FROM ranked
WHERE segment = 'north'
  AND pr >= 0.75
ORDER BY score DESC, measure_id;
```

Kết quả north gồm ID 107 (110) và 108 (140). Nhưng **đây không phải hợp đồng “luôn lấy đúng 25% số hàng”**. Với ties hoặc phân khúc nhỏ, số hàng qua ngưỡng có thể khác.

### 13.2. Chọn nhóm đầu từ NTILE

```sql
WITH bucketed AS (
    SELECT
        measure_id,
        segment,
        score,
        NTILE(4) OVER (
            PARTITION BY segment
            ORDER BY score DESC, measure_id ASC
        ) AS high_to_low_bucket
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
)
SELECT measure_id, segment, score
FROM bucketed
WHERE segment = 'north'
  AND high_to_low_bucket = 1
ORDER BY score DESC, measure_id;
```

Với north có tám hàng, nhóm đầu gồm hai điểm cao nhất 140 và 110. Với south năm hàng, bucket 1 của `NTILE(4)` chứa **hai hàng**, tức 40%, không phải chính xác 25%.

### 13.3. Chọn theo cumulative share

```sql
WITH ranked AS (
    SELECT
        measure_id,
        segment,
        score,
        CUME_DIST() OVER (
            PARTITION BY segment
            ORDER BY score DESC
        ) AS top_cumulative_share
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
)
SELECT measure_id, segment, score, top_cumulative_share
FROM ranked
WHERE segment = 'north'
  AND top_cumulative_share <= 0.25
ORDER BY score DESC, measure_id;
```

Truy vấn chọn những **peer groups có tổng tỷ lệ tích lũy không vượt 25%** tính từ điểm cao xuống. Với north, đây là 140 và 110.

Nếu một peer group có kích thước lớn khiến tỷ lệ tích lũy nhảy từ dưới 25% lên trên 25%, toàn bộ nhóm ấy **không được chọn** bởi điều kiện `<= 0.25`. Do đó kết quả có thể chứa **ít hơn** quota mong muốn, chứ không phải NTILE đúng 25%.

## 14. Lọc trước hay sau hàm cửa sổ?

Khi áp dụng `WHERE` **trong cùng SELECT có window function**, PostgreSQL tính cửa sổ trên **những hàng còn lại sau lọc**.

Ví dụ:

```sql
SELECT
    measure_id,
    score,
    PERCENT_RANK() OVER (ORDER BY score) AS pr_among_high_scores
FROM distribution_lab.measurements
WHERE segment = 'north'
  AND score >= 90
ORDER BY score, measure_id;
```

Lúc này phân bố chỉ còn **năm hàng**: 90, 90, 90, 110, 140. Nhóm 90 nhận `pr=0` vì là nhóm thấp nhất trong tập đã lọc.

Truy vấn khác:

```sql
WITH ranked_north AS (
    SELECT
        measure_id,
        score,
        PERCENT_RANK() OVER (ORDER BY score) AS pr_in_full_north
    FROM distribution_lab.measurements
    WHERE segment = 'north'
)
SELECT measure_id, score, pr_in_full_north
FROM ranked_north
WHERE score >= 90
ORDER BY score, measure_id;
```

Ở đây nhóm 90 vẫn có `pr≈0.428571` vì percent rank được tính **trên toàn bộ tám hàng north trước khi lọc ra để hiển thị**.

Hai truy vấn trả các hàng điểm ≥90 giống nhau nhưng **giá trị percent_rank khác nhau**. Khi viết báo cáo, luôn định nghĩa rõ tập tham chiếu: tất cả khách, chỉ khách còn hoạt động, chỉ giao dịch đã thanh toán, hay chỉ các bản ghi trong một khoảng ngày?

### 14.1. Dữ liệu có thể bị nhân bởi JOIN trước cửa sổ

Nếu bạn JOIN mỗi khách với ba giao dịch rồi chạy `PERCENT_RANK()` trên hàng kết quả, người có nhiều giao dịch có thể xuất hiện nhiều lần và **tác động lên mẫu phân bố**.

Nếu muốn so sánh **một hàng mỗi khách** theo tổng chi tiêu, cần tổng hợp doanh thu thành một hàng mỗi khách trước, rồi mới tính hàm cửa sổ. Không dùng `DISTINCT` như cách chữa ngẫu nhiên cho mô hình grain sai.

## 15. NULL ảnh hưởng đến phân bố ra sao?

Trong lab, cột `score` cho phép NULL nhưng các hàng mẫu đều có điểm. Điều này giúp thử một trường hợp thường xuất hiện trong dữ liệu nhập chưa hoàn chỉnh.

### 15.1. PostgreSQL vẫn sắp xếp NULL

PostgreSQL mặc định:

- `ORDER BY score ASC`: NULL được xem đứng **cuối** (mặc định `NULLS LAST`).
- `ORDER BY score DESC`: NULL được xem đứng **đầu** (mặc định `NULLS FIRST`).

Bạn có thể viết rõ:

```sql
SELECT measure_id, segment, score
FROM distribution_lab.measurements
ORDER BY score DESC NULLS LAST, measure_id;
```

Nếu xem `NULL` là “chưa có điểm” chứ không phải điểm rất cao, hãy chỉ định `NULLS LAST` hoặc loại hàng thiếu điểm trước khi tính phân bố theo yêu cầu nghiệp vụ.

### 15.2. Ranking functions không tự loại NULL

Thử dữ liệu tạm:

```sql
WITH sample(id, score) AS (
    VALUES
        (1, 10::numeric),
        (2, NULL::numeric),
        (3, NULL::numeric)
)
SELECT
    id,
    score,
    RANK() OVER (
        ORDER BY score ASC NULLS LAST
    ) AS rnk,
    PERCENT_RANK() OVER (
        ORDER BY score ASC NULLS LAST
    ) AS pr,
    CUME_DIST() OVER (
        ORDER BY score ASC NULLS LAST
    ) AS cd
FROM sample
ORDER BY score ASC NULLS LAST, id;
```

Theo thứ tự này:

| id | score | rnk | pr | cd |
| ---: | --- | ---: | ---: | ---: |
| 1 | 10 | 1 | 0 | 1/3 |
| 2 | NULL | 2 | 0.5 | 1 |
| 3 | NULL | 2 | 0.5 | 1 |

Hai NULL là peers ở cuối vì `ORDER BY` của cửa sổ coi chúng cùng khóa sắp xếp. Nhưng điều này **không mang nghĩa hai đối tượng có cùng điểm thực sự**; chúng chỉ đều thiếu dữ liệu.

### 15.3. Khuyến nghị xử lý dữ liệu thiếu

Nếu percentile chỉ có nghĩa với điểm đã biết:

```sql
SELECT
    measure_id,
    segment,
    score,
    PERCENT_RANK() OVER (
        PARTITION BY segment ORDER BY score
    ) AS pr
FROM distribution_lab.measurements
WHERE score IS NOT NULL;
```

Nếu cần giữ các đối tượng thiếu điểm trong báo cáo, có thể tính phân bố trên tập có điểm rồi `LEFT JOIN` kết quả trở lại danh sách đầy đủ; kết quả percentile của người thiếu điểm là SQL NULL hoặc một trạng thái riêng, **không tự biến thành 0**.

Quy tắc “NULL là điểm 0” chỉ được dùng nếu đó thực sự là định nghĩa nghiệp vụ. Đừng thay NULL bằng 0 bằng `COALESCE` một cách máy móc trước khi xếp hạng.

## 16. So sánh với ROW_NUMBER, RANK và DENSE_RANK

Các hàm khác trong họ ranking thường được học cùng:

| Hàm | Ý nghĩa | Có xử lý ties giống nhau? |
| --- | --- | --- |
| `ROW_NUMBER()` | Gán số thứ tự 1,2,3,... cho từng hàng. | Mỗi hàng một số riêng; cần ORDER BY đủ rõ để ổn định ties. |
| `RANK()` | Cùng điểm cùng hạng, sau peers có thể **nhảy hạng**. | Có. |
| `DENSE_RANK()` | Cùng điểm cùng hạng, hạng tiếp theo **không nhảy số**. | Có. |
| `NTILE(n)` | Chia hàng thành nhóm gần đều theo số lượng. | Có thể chia những hàng cùng điểm qua nhiều bucket. |
| `PERCENT_RANK()` | Vị trí tương đối dựa trên RANK. | Cùng peers cùng giá trị. |
| `CUME_DIST()` | Phần hàng tích lũy tới cuối peer group. | Cùng peers cùng giá trị. |

Ví dụ:

```sql
SELECT
    measure_id,
    score,
    ROW_NUMBER() OVER (
        ORDER BY score, measure_id
    ) AS row_no,
    RANK() OVER (
        ORDER BY score
    ) AS rank_no,
    DENSE_RANK() OVER (
        ORDER BY score
    ) AS dense_rank_no
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Với điểm 90 của north:

- Các hàng có `ROW_NUMBER` 4, 5, 6.
- Tất cả có `RANK=4`.
- Tất cả có `DENSE_RANK=3` vì mức điểm distinct thứ ba là 90.

Điểm 110 có `RANK=7` nhưng `DENSE_RANK=4`.

### 16.1. Vì sao PERCENT_RANK dựa trên RANK chứ không phải DENSE_RANK?

`PERCENT_RANK` đo vị trí của **hàng** trong tổng số hàng, không đo chỉ số của mức giá trị distinct. Ties gây nhảy `RANK`, và chính điều đó làm công thức `(rank - 1)/(N - 1)` phản ánh vị trí bắt đầu của mỗi peer group trong toàn bộ quan sát.

Nếu nghiệp vụ muốn đánh giá dựa trên **số mức điểm khác nhau**, cần mô hình riêng, chẳng hạn xếp hạng tập distinct scores trước rồi mới nối về các quan sát.

## 17. Khác nhau giữa NTILE và ngưỡng phân vị thật

Từ “quartile” đôi khi được dùng lẫn cho:

1. **Bốn nhóm người/hàng có số lượng gần bằng nhau**.
2. **Ba giá trị ngưỡng Q1, Q2, Q3** chia thang giá trị theo phân bố.

`NTILE(4)` giải bài toán thứ nhất. PostgreSQL có các ordered-set aggregate như `percentile_cont` và `percentile_disc` cho bài toán thứ hai.

### 17.1. percentile_cont: phân vị có nội suy

```sql
SELECT
    percentile_cont(0.25)
        WITHIN GROUP (ORDER BY score::double precision) AS p25,
    percentile_cont(0.50)
        WITHIN GROUP (ORDER BY score::double precision) AS median,
    percentile_cont(0.75)
        WITHIN GROUP (ORDER BY score::double precision) AS p75
FROM distribution_lab.measurements
WHERE segment = 'north';
```

Trên north, với điểm sắp tăng `50,50,70,90,90,90,110,140`:

- Median có nội suy `p50 = 90`.
- `p75` có nội suy giữa vị trí 6 (90) và 7 (110), nên theo quy tắc percentile_cont của PostgreSQL là **95**.

`percentile_cont` trả **một giá trị ngưỡng** (hoặc tập giá trị nếu cung cấp array fractions), không trả một hàng cho mỗi người như `PERCENT_RANK`.

Kiểu dữ liệu và phương pháp nội suy cần được hiểu đúng. Ở ví dụ ta cast sang `double precision` để khớp overload ordered-set aggregate thông dụng; nếu cần kết quả tiền tệ chính xác theo decimal, hãy cân nhắc cách biểu diễn/định nghĩa làm tròn của hệ thống.

### 17.2. percentile_disc: phân vị rời rạc

```sql
SELECT
    percentile_disc(0.25)
        WITHIN GROUP (ORDER BY score) AS p25_discrete,
    percentile_disc(0.50)
        WITHIN GROUP (ORDER BY score) AS median_discrete,
    percentile_disc(0.75)
        WITHIN GROUP (ORDER BY score) AS p75_discrete
FROM distribution_lab.measurements
WHERE segment = 'north';
```

`percentile_disc` chọn một **giá trị thực có trong dữ liệu** dựa trên ngưỡng tích lũy. Với north:

```text
p25_discrete = 50
median_discrete = 90
p75_discrete = 90
```

So với `percentile_cont(0.75)=95`, `percentile_disc(0.75)=90`. Hai kết quả khác nhau nhưng đều đúng theo **hai định nghĩa phân vị**.

### 17.3. Aggregate theo phân khúc

```sql
SELECT
    segment,
    COUNT(score) AS scored_rows,
    percentile_disc(0.5)
        WITHIN GROUP (ORDER BY score) AS median_score
FROM distribution_lab.measurements
GROUP BY segment
ORDER BY segment;
```

Kết quả theo dữ liệu mẫu:

| segment | scored_rows | median_score |
| --- | ---: | ---: |
| north | 8 | 90 |
| pilot | 1 | 95 |
| south | 5 | 40 |

Không nên đánh đồng kết quả `median_score` với giá trị `PERCENT_RANK=0.5` của một hàng. Một bên là **điểm tại phân vị**, một bên là **vị trí tương đối của điểm**.

### 17.4. percentile_cont và percentile_disc không có OVER như NTILE?

Trong PostgreSQL, `percentile_cont` và `percentile_disc` ở dạng ordered-set aggregate được viết với `WITHIN GROUP (ORDER BY ...)` để tính ngưỡng trên tập dữ liệu tổng hợp. Cách dùng chuẩn của chúng **khác nhóm ranking window** `NTILE`, `PERCENT_RANK` và `CUME_DIST`.

Nếu muốn gắn một ngưỡng phân vị tính theo segment vào từng quan sát, có thể tính ngưỡng ở CTE tổng hợp rồi `JOIN` lại:

```sql
WITH limits AS (
    SELECT
        segment,
        percentile_disc(0.75)
            WITHIN GROUP (ORDER BY score) AS p75_score
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
    GROUP BY segment
)
SELECT
    m.measure_id,
    m.segment,
    m.score,
    l.p75_score,
    m.score >= l.p75_score AS meets_p75_threshold
FROM distribution_lab.measurements AS m
JOIN limits AS l
    ON l.segment = m.segment
WHERE m.score IS NOT NULL
ORDER BY m.segment, m.score, m.measure_id;
```

Khi dùng `>= p75_score`, ties ở đúng ngưỡng có thể khiến nhiều hơn 25% người được chọn. Đây là hệ quả tự nhiên của chính sách **giữ những người cùng điểm**.

## 18. NTILE khác WIDTH_BUCKET và histogram

Một histogram thường dùng các khoảng **giá trị** cố định, trong khi `NTILE` dùng các bucket theo **vị trí hàng**.

Ví dụ chia thang điểm `[0,160)` thành bốn khoảng có độ rộng 40:

```sql
SELECT
    measure_id,
    score,
    width_bucket(score, 0::numeric, 160::numeric, 4)
        AS fixed_width_bucket,
    NTILE(4) OVER (
        ORDER BY score, measure_id
    ) AS equal_count_bucket
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Các khoảng cố định:

```text
width_bucket = 1: [  0,  40)
width_bucket = 2: [ 40,  80)
width_bucket = 3: [ 80, 120)
width_bucket = 4: [120, 160)
```

Với north:

- Bucket độ rộng cố định 1: 0 người.
- Bucket độ rộng cố định 2: 3 người (50,50,70).
- Bucket độ rộng cố định 3: 4 người (90,90,90,110).
- Bucket độ rộng cố định 4: 1 người (140).

Trong khi `NTILE(4)` chia thành 2–2–2–2 người. Hai cách giải hai bài toán thống kê khác nhau.

### 18.1. width_bucket với điểm ngoài khoảng

Với dạng `width_bucket(value, lower, upper, count)` và `lower < upper`, PostgreSQL trả bucket **0** khi giá trị nhỏ hơn ranh giới thấp và **count + 1** khi lớn hơn hoặc bằng ranh giới trên.

Thử:

```sql
SELECT
    width_bucket(-1::numeric, 0::numeric, 160::numeric, 4) AS below,
    width_bucket(50::numeric, 0::numeric, 160::numeric, 4) AS inside,
    width_bucket(160::numeric, 0::numeric, 160::numeric, 4) AS at_upper;
```

Kết quả tương ứng `0`, `2` và `5`. Khi dựng histogram, phải quyết định có lọc các giá trị ngoài phạm vi, tạo bucket overflow hay hiển thị chúng riêng.

### 18.2. Thống kê số người theo khoảng cố định

```sql
WITH histogram AS (
    SELECT
        width_bucket(score, 0::numeric, 160::numeric, 4) AS bucket,
        COUNT(*) AS observations
    FROM distribution_lab.measurements
    WHERE segment = 'north'
      AND score >= 0
      AND score < 160
    GROUP BY 1
)
SELECT
    b.bucket,
    COALESCE(h.observations, 0) AS observations
FROM generate_series(1, 4) AS b(bucket)
LEFT JOIN histogram AS h
    ON h.bucket = b.bucket
ORDER BY b.bucket;
```

Kết quả: `0, 3, 4, 1` quan sát tương ứng bốn khoảng. `generate_series` giúp tạo cả bucket không có dữ liệu, thuận tiện cho báo cáo.

## 19. Tạo nhóm khách hàng theo tổng chi tiêu

Ứng dụng phổ biến của `NTILE` là chia khách thành các nhóm theo **lifetime spending** hoặc doanh thu một kỳ:

```text
orders -----------+
                  |
              SUM(amount)
                  |
                  v
           customer_spending
                  |
                  v
             NTILE(4)
                  |
                  v
       nhóm giá trị thấp → cao
```

Điều quan trọng là đầu vào phải có **một hàng mỗi khách**. Nếu tính NTILE trực tiếp trên bảng orders, khách có nhiều đơn sẽ xuất hiện nhiều lần và làm sai phân bố **khách hàng**.

### 19.1. Bộ dữ liệu mô phỏng độc lập

Không cần tạo bảng mới, dùng CTE `VALUES`:

```sql
WITH customer_spending(customer_id, segment, total_spent) AS (
    VALUES
        (1, 'retail',  120::numeric),
        (2, 'retail',  450::numeric),
        (3, 'retail',  450::numeric),
        (4, 'retail',  900::numeric),
        (5, 'retail', 1100::numeric),
        (6, 'retail', 1400::numeric),
        (7, 'retail', 1900::numeric),
        (8, 'retail', 2500::numeric)
),
segmented AS (
    SELECT
        customer_id,
        segment,
        total_spent,
        NTILE(4) OVER (
            PARTITION BY segment
            ORDER BY total_spent DESC, customer_id
        ) AS spending_tier,
        CUME_DIST() OVER (
            PARTITION BY segment
            ORDER BY total_spent DESC
        ) AS top_share
    FROM customer_spending
)
SELECT
    customer_id,
    total_spent,
    spending_tier,
    top_share
FROM segmented
ORDER BY spending_tier, total_spent DESC, customer_id;
```

Trong trường hợp tám khách:

- Tier 1: chi tiêu cao nhất, hai khách 2500 và 1900.
- Tier 2: hai khách tiếp theo 1400 và 1100.
- Tier 3: 900 và một trong hai khách 450, tùy tiêu chí phá hòa đã khai báo.
- Tier 4: khách 450 còn lại và khách 120.

Vì `ORDER BY total_spent DESC, customer_id`, giữa hai khách chi tiêu 450, khách có `customer_id=2` đứng trước khách 3. Đó là một **tiêu chí phụ kỹ thuật**, không nhất thiết đủ công bằng nếu tier ảnh hưởng quyền lợi.

### 19.2. Nếu có khách chưa phát sinh đơn

Phải xác định “khách không có đơn” có được tính chi tiêu bằng 0 hay bị loại khỏi cohort. Một mô hình ví dụ:

```sql
WITH customers(customer_id) AS (
    VALUES (1), (2), (3), (4)
),
orders(order_id, customer_id, amount) AS (
    VALUES
        (11, 1, 100::numeric),
        (12, 1, 200::numeric),
        (13, 3,  50::numeric)
),
spending AS (
    SELECT
        c.customer_id,
        COALESCE(SUM(o.amount), 0) AS total_spent
    FROM customers AS c
    LEFT JOIN orders AS o
        ON o.customer_id = c.customer_id
    GROUP BY c.customer_id
)
SELECT
    customer_id,
    total_spent,
    NTILE(4) OVER (
        ORDER BY total_spent DESC, customer_id
    ) AS tier
FROM spending
ORDER BY tier;
```

Đây là cách giữ cả khách 2 và 4 không có đơn với `total_spent=0`. Nếu chỉ JOIN kiểu INNER trước khi tổng hợp, họ sẽ bị loại khỏi quần thể phân nhóm.

### 19.3. Khách có nhiều loại giao dịch

Trong hệ thống thực tế cần quy định rõ:

- Đơn pending có được tính không?
- Hoàn tiền và hủy đơn làm giảm tổng như thế nào?
- Tổng là doanh thu trước hay sau thuế?
- Phân nhóm theo tháng/quý hay toàn bộ lịch sử?
- Tiền tệ khác nhau có cần chuyển đổi về cùng đơn vị không?
- Một khách có nhiều tài khoản có được hợp nhất không?

`NTILE` chỉ xử lý **thứ tự và số lượng hàng của metric đầu vào**. Nếu metric đầu vào chưa có nghĩa nghiệp vụ đúng, kết quả tier không thể tự sửa lỗi đó.

## 20. Phân tích đánh giá, điểm thi và SLA

### 20.1. Điểm cao là tốt

Nếu điểm cao biểu thị thành tích tốt:

```sql
SELECT
    measure_id,
    score,
    NTILE(4) OVER (
        ORDER BY score DESC, measure_id
    ) AS performance_tier
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY performance_tier, score DESC, measure_id;
```

Tier 1 là nhóm thành tích cao nhất. Nếu muốn “tỷ lệ bài thi không vượt điểm X”, lại dùng `CUME_DIST() OVER (ORDER BY score ASC)`.

### 20.2. Độ trễ thấp là tốt

Nếu `score` là latency tính bằng mili giây thì **thấp hơn tốt hơn**. Cùng một metric:

```sql
SELECT
    measure_id,
    score AS latency_ms,
    NTILE(4) OVER (
        ORDER BY score ASC, measure_id
    ) AS best_latency_tier,
    CUME_DIST() OVER (
        ORDER BY score ASC
    ) AS latency_cdf
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY latency_ms, measure_id;
```

Tier 1 lúc này là nhóm latency thấp nhất. `latency_cdf` cho tỷ lệ quan sát có latency không lớn hơn mức hiện tại. Khi xây SLO p95 latency, người ta thường cần **giá trị ngưỡng latency ở phân vị 95%**, có thể tính bằng `percentile_cont(0.95)` hoặc phương pháp histogram/metrics tương ứng, không phải lấy `PERCENT_RANK()=0.95` rồi coi là mili giây.

### 20.3. Quần thể nhỏ gây kết quả khó diễn giải

Một phân khúc có một người luôn nhận `PERCENT_RANK=0` và `CUME_DIST=1`, nhưng thông tin này **không thể hiện thành tích tương đối đáng tin**. Với phân khúc có hai người, các giá trị có bước nhảy rất lớn.

Khi xây dashboard, cân nhắc hiển thị thêm `COUNT(*) OVER (PARTITION BY segment)`, và đặt ngưỡng cỡ mẫu tối thiểu trước khi công bố percentile so sánh.

## 21. Đặt tên WINDOW khi lặp cùng định nghĩa

PostgreSQL cho phép dùng mệnh đề `WINDOW` để đặt tên một cửa sổ thường được dùng nhiều lần:

```sql
SELECT
    measure_id,
    segment,
    score,
    RANK() OVER w AS rnk,
    PERCENT_RANK() OVER w AS pr,
    CUME_DIST() OVER w AS cd
FROM distribution_lab.measurements
WHERE score IS NOT NULL
WINDOW w AS (
    PARTITION BY segment
    ORDER BY score ASC
)
ORDER BY segment, score, measure_id;
```

Lợi ích:

- Giảm lặp các phần `PARTITION BY segment ORDER BY score ASC`.
- Giúp bảo đảm `RANK`, `PERCENT_RANK` và `CUME_DIST` dùng **cùng định nghĩa peer groups**.
- SQL dễ đọc khi nhiều metric dùng chung quần thể và thứ tự.

Nhưng nếu `NTILE` cần khóa phụ `measure_id` để phá hòa còn `PERCENT_RANK` cần giữ peers theo `score`, hãy dùng **hai cửa sổ khác nhau**:

```sql
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER w_bucket AS bucket,
    PERCENT_RANK() OVER w_peers AS pr,
    CUME_DIST() OVER w_peers AS cd
FROM distribution_lab.measurements
WHERE score IS NOT NULL
WINDOW
    w_bucket AS (
        PARTITION BY segment
        ORDER BY score, measure_id
    ),
    w_peers AS (
        PARTITION BY segment
        ORDER BY score
    )
ORDER BY segment, score, measure_id;
```

**Tên cửa sổ khác nhau phản ánh hai ý định khác nhau**, không phải sự lặp lại vô ích.

## 22. Window frame có ảnh hưởng đến ba hàm không?

Một `OVER` có thể chỉ định thêm *window frame*, ví dụ `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Frame rất quan trọng với những hàm như `SUM(...) OVER (...)`, `FIRST_VALUE` hoặc `LAST_VALUE`.

Tuy nhiên, với `NTILE`, `PERCENT_RANK` và `CUME_DIST`, bản chất tính toán dựa trên **toàn partition và peer groups theo ORDER BY**, không phải một frame đang thu hẹp kiểu rolling sum.

Thử hai metric khác nhau trong cùng một query:

```sql
SELECT
    measure_id,
    score,
    SUM(score) OVER (
        ORDER BY score, measure_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum,
    CUME_DIST() OVER (
        ORDER BY score
    ) AS cumulative_row_fraction
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

`running_sum` cộng **giá trị điểm** từ đầu tới hàng hiện tại theo frame. `cumulative_row_fraction` đếm **tỷ lệ số hàng** tới cuối peer group. Dù cả hai được gọi “cumulative” trong mô tả báo cáo, đơn vị đo và ngữ nghĩa hoàn toàn khác.

### 22.1. Mặc định frame và ties

Đối với nhiều aggregate window khi có `ORDER BY` mà không khai báo frame, PostgreSQL dùng frame mặc định có xét peers đến hàng hiện tại theo quy tắc của SQL. Vì vậy `SUM(score) OVER (ORDER BY score)` có thể nhảy theo cả nhóm điểm 90, không tăng từng hàng theo thứ tự ID.

Nếu muốn running sum từng hàng, khai báo `ROWS ...` với `ORDER BY` có khóa phá hòa. Đừng dùng một kết quả running sum bị ảnh hưởng frame làm bằng chứng rằng `CUME_DIST` tính sai.

## 23. Đọc EXPLAIN và tối ưu truy vấn phân bố

Window functions thường cần dữ liệu được sắp xếp theo partition và order keys, nên chi phí có thể đáng kể khi xử lý hàng triệu bản ghi.

```sql
EXPLAIN
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score, measure_id
    ) AS bucket
FROM distribution_lab.measurements
WHERE score IS NOT NULL;
```

Kế hoạch có thể chứa `WindowAgg`, `Sort`, index scan hoặc những thao tác khác tùy dữ liệu và phiên bản PostgreSQL.

### 23.1. Index phù hợp với partition/order

Ví dụ một chỉ mục có thể hữu ích cho workload thường xuyên phân bố theo segment và score:

```sql
CREATE INDEX idx_measurements_segment_score_id
ON distribution_lab.measurements (
    segment,
    score,
    measure_id
);
```

Index phù hợp có thể giúp cung cấp dữ liệu theo thứ tự hữu ích hoặc giảm một phần công việc sắp xếp. Nhưng **không có bảo đảm mỗi window query sẽ dùng index**, đặc biệt nếu bộ lọc trả phần lớn bảng, dữ liệu nhỏ hoặc nhiều định nghĩa window khác thứ tự.

Để đánh giá thực tế:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score, measure_id
    ) AS bucket
FROM distribution_lab.measurements
WHERE score IS NOT NULL;
```

`EXPLAIN ANALYZE` thực sự chạy SELECT, nên cân nhắc kích thước và tải production trước khi sử dụng. Bảng lab 14 hàng không đại diện cho hiệu năng trên bảng 100 triệu hàng.

### 23.2. Các điểm thường ảnh hưởng hiệu năng

1. **Kích thước quần thể:** số hàng đầu vào sau WHERE, JOIN và GROUP BY.
2. **Số partition:** rất nhiều partition nhỏ khác với một partition khổng lồ.
3. **Thứ tự window:** nhiều window với ORDER BY khác nhau có thể tăng công việc sắp xếp.
4. **Index và thống kê:** cấu trúc dữ liệu thực và planner quyết định phương án.
5. **work_mem và spill:** Sort/WindowAgg có thể cần bộ nhớ; workload lớn có thể sử dụng temporary files.
6. **Số hàng được trả:** đừng trả toàn bộ dữ liệu qua mạng khi chỉ cần nhóm top/tier.
7. **Chi phí JOIN trước window:** một quan hệ nhân hàng sẽ vừa làm metric sai vừa tăng chi phí.

### 23.3. LIMIT ngoài không tự rút nhỏ partition

```sql
SELECT
    measure_id,
    score,
    PERCENT_RANK() OVER (ORDER BY score) AS pr
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score
LIMIT 3;
```

Muốn biết percent rank của một hàng, PostgreSQL về mặt ngữ nghĩa phải xét **toàn bộ partition theo thứ tự đã định**, không phải chỉ ba hàng được hiển thị. `LIMIT 3` ở cuối không đổi mẫu số N của hàm cửa sổ.

Nếu chỉ cần ba người điểm thấp nhất mà **không cần percentile**, có thể bỏ window function và dùng `ORDER BY ... LIMIT 3` thông thường, đôi khi nhẹ hơn đáng kể.

## 24. Kiểm soát chất lượng dữ liệu trước phân bố

Trước khi tin vào metric percentile, cần kiểm tra:

| Câu hỏi | Hệ quả nếu bỏ qua |
| --- | --- |
| Một hàng đại diện cho ai/cái gì? | Phân bố theo giao dịch bị nhầm thành phân bố theo khách. |
| Có bản ghi trùng không? | Những đối tượng bị lặp có ảnh hưởng nhiều lần tới phân bố. |
| NULL nghĩa là gì? | NULL có thể bị xếp ở đầu/cuối như nhóm giá trị thật. |
| Điểm số có cùng thang đo không? | So sánh 100 USD với 100 VND hoặc latency khác loại là sai. |
| Cohort có đủ lớn không? | Percentile biến động mạnh và dễ bị diễn giải quá mức. |
| Ties cần xử lý thế nào? | NTILE có thể chia cùng điểm sang nhiều nhóm. |
| Metric có outlier không? | Bucket theo người và ngưỡng giá trị có thể khác rất lớn. |
| Partition theo kỳ nào? | Thứ hạng theo tháng có thể không đại diện thứ hạng cả năm. |
| Có chính sách hủy/hoàn tiền không? | Doanh số hoặc điểm dùng làm input có thể sai nghiệp vụ. |

Ví dụ xác minh số hàng và số mức điểm:

```sql
SELECT
    segment,
    COUNT(*) AS total_rows,
    COUNT(score) AS nonnull_scores,
    COUNT(DISTINCT score) AS distinct_score_levels,
    MIN(score) AS min_score,
    MAX(score) AS max_score
FROM distribution_lab.measurements
GROUP BY segment
ORDER BY segment;
```

Với north có 8 hàng nhưng chỉ **5 mức điểm khác nhau**. Đây là dấu hiệu cần xem xét chính sách xử lý ties khi chia nhóm khen thưởng.

### 24.1. Chẩn đoán nhóm điểm trùng

```sql
SELECT segment, score, COUNT(*) AS peer_size
FROM distribution_lab.measurements
WHERE score IS NOT NULL
GROUP BY segment, score
HAVING COUNT(*) > 1
ORDER BY segment, score;
```

Kết quả gồm north 50 (2), north 90 (3), south 30 (2). Điều này giải thích tại sao những bước nhảy `CUME_DIST` đôi khi lớn và tại sao NTILE có thể tách peers ở ranh giới.

## 25. Đọc kết quả từ ứng dụng Java

Trong JDBC, các cột hàm cửa sổ có kiểu SQL:

- `NTILE(n)`: bucket number, phù hợp đọc dưới dạng số nguyên.
- `PERCENT_RANK()` và `CUME_DIST()`: `double precision`, có thể map thành `double`/`Double` theo kiểu cần dùng.

Ví dụ SQL cho một repository:

```sql
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score DESC, measure_id
    ) AS performance_bucket,
    PERCENT_RANK() OVER (
        PARTITION BY segment
        ORDER BY score DESC
    ) AS relative_rank,
    CUME_DIST() OVER (
        PARTITION BY segment
        ORDER BY score DESC
    ) AS cumulative_share
FROM distribution_lab.measurements
WHERE score IS NOT NULL
ORDER BY segment, performance_bucket, score DESC, measure_id;
```

Nếu API trả percentage, việc nhân 100 và làm tròn nên có quy ước:

```sql
SELECT
    measure_id,
    ROUND(
        (
            100 * PERCENT_RANK() OVER (
                ORDER BY score
            )
        )::numeric,
        2
    ) AS percent_rank_percent
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Giá trị `85.71` ở đây là **điểm xếp hạng tương đối tính bằng phần trăm theo định nghĩa percent_rank**, không phải “đã đạt 85.71% mục tiêu kinh doanh”.

### 25.1. Đặt tên trường API theo đúng ngữ nghĩa

Nên dùng tên tường minh như:

- `score_quartile_bucket` cho `NTILE(4)`.
- `score_percent_rank` cho `PERCENT_RANK()`.
- `score_cumulative_fraction` cho `CUME_DIST()`.
- `sample_size` cho số quan sát trong partition.

Tránh một trường mơ hồ tên `percentile` mà không nói rõ dùng công thức nào, chiều sắp xếp, cohort nào, cách xử lý NULL và ties ra sao.

## 26. Những lỗi phổ biến và cách sửa

### Lỗi 1. Coi NTILE(4) là bốn khoảng điểm đều nhau

Sai: mỗi bucket trong NTILE phải có độ rộng điểm bằng nhau. Đúng: NTILE cân bằng **số hàng**, không phải độ rộng giá trị. Dùng `width_bucket`/histogram nếu cần khoảng điểm cố định.

### Lỗi 2. Tin NTILE không bao giờ tách điểm trùng

Sai: cả ba hàng điểm 90 của north sẽ luôn cùng bucket. Thực tế `NTILE(4)` tách một hàng vào bucket 2 và hai hàng vào bucket 3 trong thứ tự đã xác định. Nếu cần cùng điểm cùng tier, dùng chính sách theo ngưỡng điểm hoặc bucket trên distinct scores.

### Lỗi 3. Bỏ khóa phụ khỏi NTILE và đòi kết quả từng ID ổn định

`NTILE(4) OVER (ORDER BY score)` không xác định thứ tự tương đối của các hàng có cùng score. Khi peers nằm qua ranh giới bucket, một ID cụ thể có thể chuyển bucket giữa kế hoạch hoặc lần chạy. Thêm tiêu chí phụ có ý nghĩa nếu cần tái lập kết quả.

### Lỗi 4. Thêm ID vào PERCENT_RANK để “sửa ties”

Việc này làm mỗi hàng thành một peer riêng và **thay đổi statistic**. Nếu nghiệp vụ coi các điểm bằng nhau cùng mức, chỉ `ORDER BY score` trong `PERCENT_RANK`.

### Lỗi 5. Hiểu PERCENT_RANK là tỷ lệ hàng nhỏ hơn hoặc bằng điểm

Đó là ý nghĩa của `CUME_DIST` trong thứ tự tăng, không phải của `PERCENT_RANK`. Với north điểm 90, hai kết quả là khoảng 0.4286 và 0.75.

### Lỗi 6. Nghĩ PERCENT_RANK của điểm cao nhất luôn là 1

Nếu điểm cao nhất có nhiều peers, giá trị có thể nhỏ hơn 1. Hàm dùng rank của peer group chứ không phải vị trí cuối cùng.

### Lỗi 7. Nghĩ CUME_DIST có thể bằng 0

Trong partition không rỗng, `CUME_DIST` luôn lớn hơn 0; ngay nhóm đầu đã chiếm ít nhất một hàng.

### Lỗi 8. Quên partition một hàng

Khi N=1, `PERCENT_RANK=0` và `CUME_DIST=1`. Không diễn giải đây là chứng cứ xếp loại tuyệt đối trên quần thể quá nhỏ.

### Lỗi 9. Sắp DESC nhưng gắn nhãn “phần trăm người có điểm thấp hơn”

`CUME_DIST() OVER (ORDER BY score DESC)` xét tích lũy từ điểm cao xuống, không từ thấp lên. Phải ghi rõ chiều.

### Lỗi 10. Lọc trước khi tính window rồi gọi đó là phân bố toàn bộ

`WHERE score >= 90` trong query có window làm thay đổi quần thể tính N và rank. Muốn tính trên toàn cohort rồi lọc phần hiển thị, dùng CTE/subquery.

### Lỗi 11. Tính ranking trên bảng nhiều giao dịch mỗi khách

Nếu cần xếp hạng khách, hãy tổng hợp một hàng mỗi khách trước. Ranking trên mỗi đơn sẽ xếp **đơn** chứ không xếp **khách**.

### Lỗi 12. Quên NULLS FIRST/LAST

Trong PostgreSQL, `DESC` mặc định có thể đặt NULL lên đầu. Nếu NULL là dữ liệu chưa biết, nó không nên tự được coi là điểm cao nhất; lọc hoặc khai báo NULL semantics rõ.

### Lỗi 13. Nhầm percentile_cont với percent_rank

`percentile_cont(0.75)` trả **ngưỡng giá trị tại phân vị**. `PERCENT_RANK()` trả **vị trí tương đối của từng hàng**. Hai kết quả khác đơn vị.

### Lỗi 14. Coi percent_rank >= 0.75 luôn đúng 25% người

Với ties, nhỏ mẫu hoặc ranh giới peer group, số hàng qua điều kiện có thể khác xa 25%. Muốn quota chính xác dùng chiến lược lấy hàng có phá hòa, nhưng phải có chính sách công bằng rõ.

### Lỗi 15. Dùng DISTINCT trước window mà không rõ mục tiêu

`SELECT DISTINCT score` thay đổi quần thể từ **quan sát** sang **mức điểm riêng biệt**. Percentiles trên các mức distinct không còn là percentiles của tất cả cá nhân.

### Lỗi 16. Tin ORDER BY trong OVER bảo đảm thứ tự kết quả

`ORDER BY` cửa sổ định nghĩa thứ tự tính toán; muốn bảo đảm output phải có `ORDER BY` của câu query ngoài.

### Lỗi 17. Lẫn khái niệm frame với partition

`NTILE`, `PERCENT_RANK`, `CUME_DIST` không dùng frame theo cách running SUM. Đừng thay đổi frame rồi trông đợi chuyển mẫu số của percent_rank thành số hàng ở “5 dòng gần nhất”.

### Lỗi 18. Đọc metric mà không nói rõ cohort

`PERCENT_RANK` theo north khác `PERCENT_RANK` toàn công ty. Một giá trị thập phân không có ý nghĩa nếu thiếu quần thể và kỳ đo.

### Lỗi 19. Gán số percent_rank thành độ chính xác nghiệp vụ tuyệt đối

Với số mẫu nhỏ hoặc dữ liệu lệch, ranking có bước nhảy lớn. Không dùng một giá trị hai chữ số thập phân để đưa ra kết luận thiếu sai số/độ tin cậy.

### Lỗi 20. Tạo index nhưng không đo trên dữ liệu thực

Index có thể hỗ trợ `PARTITION BY/ORDER BY`, nhưng optimizer vẫn phải cân nhắc quét, sort, memory và kích thước dữ liệu. Dùng `EXPLAIN (ANALYZE, BUFFERS)` trên workload thích hợp.

## 27. Bài tập thực hành

Các bài dưới đây sử dụng bảng `distribution_lab.measurements` từ phần 2. Một số bài chỉ dùng `VALUES` nên có thể chạy độc lập. Hãy đối chiếu dự đoán bằng tay với kết quả PostgreSQL; các ví dụ chỉ đọc và không thay đổi bảng.

### Bài 1. NTILE cơ bản

Viết truy vấn chỉ lấy `north`, trả `measure_id`, `score` và `NTILE(4)` theo điểm tăng, phá hòa bằng ID tăng. Dự đoán bucket của 104, 105 và 106.

### Bài 2. NTILE với số hàng không chia hết

Thử `NTILE(3)` trên tám hàng north. Kích thước ba bucket theo thứ tự là bao nhiêu?

### Bài 3. NTILE với bucket nhiều hơn số hàng

Thử `NTILE(4)` trên partition `pilot` có một quan sát. Những số bucket nào xuất hiện?

### Bài 4. PERCENT_RANK bằng tay

Với north, tính `PERCENT_RANK` của score 70 và 110 bằng `RANK` và N.

### Bài 5. CUME_DIST bằng tay

Với north, tính `CUME_DIST` của score 50, 90 và 140. Giải thích tại sao score 90 nhảy từ 0.375 lên 0.75.

### Bài 6. Một partition một hàng

Viết truy vấn tính `NTILE(4)`, `PERCENT_RANK` và `CUME_DIST` trên pilot. Dự đoán ba kết quả.

### Bài 7. PARTITION BY

Viết truy vấn tính cả ba metric theo từng segment và sắp xếp theo `segment, score, measure_id`. Dự đoán score 40 của south.

### Bài 8. Thứ tự giảm dần

Trên north, dùng `ORDER BY score DESC`. Giá trị `PERCENT_RANK` và `CUME_DIST` của điểm cao nhất 140 là bao nhiêu?

### Bài 9. Tranh luận về tie

Tại sao NTILE(4) có thể xếp ba điểm 90 của north vào hai bucket? Có nên dùng ID làm tiêu chí phá hòa nếu bucket quyết định thưởng?

### Bài 10. Không tách điểm trùng

Viết CTE chọn `DISTINCT segment, score`, thực hiện NTILE(4) trên các mức điểm, sau đó JOIN lại `measurements`. Bucket của score 90 trong north có giống nhau giữa ba hàng không?

### Bài 11. Lọc sau window

Tính `PERCENT_RANK` trên toàn north rồi chỉ hiện các hàng có score ≥90. So sánh với cách đặt `score >=90` trong `WHERE` trước khi tính window.

### Bài 12. CUME_DIST và tỷ lệ ≤ ngưỡng

Viết truy vấn trả tỷ lệ tích lũy tại score 90 của north. Giải thích tại sao nó bằng 6/8.

### Bài 13. NULLS LAST

Dùng CTE `VALUES` có điểm `10, NULL, NULL` để so sánh `PERCENT_RANK` và `CUME_DIST` với `ORDER BY score ASC NULLS LAST`. Nếu thiếu điểm, bạn sẽ làm gì trước khi công bố ranking?

### Bài 14. Phân vị 75%

Tính `percentile_cont(0.75)` và `percentile_disc(0.75)` cho north. Giải thích vì sao hai giá trị khác nhau.

### Bài 15. So với WIDTH_BUCKET

Chia điểm north thành bốn khoảng [0,40), [40,80), [80,120), [120,160). Đếm số hàng từng khoảng; so với kích thước bucket của NTILE(4).

### Bài 16. Top 25% theo nhiều cách

Trên north, so sánh:

- `NTILE(4) OVER (ORDER BY score DESC, measure_id) = 1`.
- `CUME_DIST() OVER (ORDER BY score DESC) <= 0.25`.

Trong dữ liệu mẫu hai cách chọn hàng nào? Nếu xuất hiện một nhóm điểm 90 rất lớn ở ranh giới, hai cách có còn bảo đảm bằng nhau không?

### Bài 17. RANK và DENSE_RANK

Với north, tính `RANK` và `DENSE_RANK` cho score 90 và 110. Tại sao các giá trị của hai hàm không giống nhau?

### Bài 18. Kiểm tra cỡ mẫu

Viết truy vấn trả mỗi hàng cùng `COUNT(*) OVER (PARTITION BY segment)`. Vì sao cần hiển thị cỡ mẫu cạnh percentile?

### Bài 19. Metric theo grain khách

Một bảng đơn hàng có nhiều đơn mỗi khách. Viết phác thảo SQL dùng `GROUP BY customer_id` để tính `SUM(amount)` rồi `NTILE(4)` theo tổng tiền. Vì sao không đặt NTILE trực tiếp trên bảng orders?

### Bài 20. Viết truy vấn chung cho dashboard

Trả `measure_id`, `segment`, `score`, `bucket` theo thứ tự điểm giảm và ID, `percent_rank` theo điểm giảm **không thêm ID**, `cume_dist` theo điểm giảm và `segment_size`. Chỉ dùng điểm khác NULL.

## 28. Gợi ý lời giải

### Đáp án 1

```sql
SELECT
    measure_id,
    score,
    NTILE(4) OVER (ORDER BY score, measure_id) AS bucket
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

ID 104 có bucket 2, ID 105 và 106 có bucket 3.

### Đáp án 2

```sql
SELECT
    measure_id,
    score,
    NTILE(3) OVER (ORDER BY score, measure_id) AS bucket
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Tám hàng chia ba bucket có kích thước **3, 3, 2**.

### Đáp án 3

```sql
SELECT
    measure_id,
    NTILE(4) OVER (ORDER BY score, measure_id) AS bucket
FROM distribution_lab.measurements
WHERE segment = 'pilot';
```

Chỉ có bucket **1**.

### Đáp án 4

`score=70` có rank 3 nên `(3-1)/(8-1)=2/7≈0.285714`. `score=110` có rank 7 nên `(7-1)/7=6/7≈0.857143`.

### Đáp án 5

Theo số hàng ≤ điểm hiện tại: score 50 có `2/8=0.25`; score 90 có `6/8=0.75`; score 140 có `8/8=1`. Bước nhảy từ 0.375 lên 0.75 do có **ba hàng** cùng score 90.

### Đáp án 6

```sql
SELECT
    measure_id,
    NTILE(4) OVER (ORDER BY score) AS bucket,
    PERCENT_RANK() OVER (ORDER BY score) AS pr,
    CUME_DIST() OVER (ORDER BY score) AS cd
FROM distribution_lab.measurements
WHERE segment = 'pilot';
```

Kết quả: `bucket=1`, `pr=0`, `cd=1`.

### Đáp án 7

```sql
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment ORDER BY score, measure_id
    ) AS bucket,
    PERCENT_RANK() OVER (
        PARTITION BY segment ORDER BY score
    ) AS pr,
    CUME_DIST() OVER (
        PARTITION BY segment ORDER BY score
    ) AS cd
FROM distribution_lab.measurements
ORDER BY segment, score, measure_id;
```

Với south score 40 (ID 203): `bucket=2`, `pr=0.5`, `cd=0.6`.

### Đáp án 8

`score=140` đứng đầu khi sắp DESC nên `PERCENT_RANK=0` và `CUME_DIST=1/8=0.125`. Đó là vị trí tính **từ phía điểm cao nhất**.

### Đáp án 9

NTILE cân bằng số hàng nên có thể tách peers ở ranh giới. Nếu bucket quyết định thưởng, không nên chọn ID kỹ thuật tùy tiện mà không có quy tắc phá hòa được công bố. Có thể chọn chính sách giữ ties theo điểm, chấp nhận quy mô nhóm không đều.

### Đáp án 10

```sql
WITH distinct_scores AS (
    SELECT DISTINCT segment, score
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
),
buckets AS (
    SELECT
        segment, score,
        NTILE(4) OVER (
            PARTITION BY segment ORDER BY score
        ) AS bucket
    FROM distinct_scores
)
SELECT m.measure_id, m.segment, m.score, b.bucket
FROM distribution_lab.measurements AS m
JOIN buckets AS b
    ON b.segment = m.segment
   AND b.score = m.score
ORDER BY m.segment, m.score, m.measure_id;
```

Mọi hàng score 90 ở north thuộc **cùng bucket 2** theo cách chia mức điểm distinct.

### Đáp án 11

```sql
WITH ranked AS (
    SELECT
        measure_id,
        score,
        PERCENT_RANK() OVER (ORDER BY score) AS pr
    FROM distribution_lab.measurements
    WHERE segment = 'north'
)
SELECT measure_id, score, pr
FROM ranked
WHERE score >= 90
ORDER BY score, measure_id;
```

Trên toàn north, score 90 có `pr=3/7`. Nếu lọc score ≥90 **trong query tính window**, nhóm 90 là nhóm đầu của tập năm hàng nên `pr=0`.

### Đáp án 12

```sql
WITH ranked AS (
    SELECT
        score,
        CUME_DIST() OVER (ORDER BY score) AS cd
    FROM distribution_lab.measurements
    WHERE segment = 'north'
)
SELECT DISTINCT score, cd
FROM ranked
WHERE score = 90;
```

Kết quả `0.75`, vì có sáu trên tám hàng điểm ≤90.

### Đáp án 13

```sql
WITH sample(id, score) AS (
    VALUES
        (1, 10::numeric),
        (2, NULL::numeric),
        (3, NULL::numeric)
)
SELECT
    id, score,
    PERCENT_RANK() OVER (
        ORDER BY score NULLS LAST
    ) AS pr,
    CUME_DIST() OVER (
        ORDER BY score NULLS LAST
    ) AS cd
FROM sample
ORDER BY score NULLS LAST, id;
```

NULL là nhóm cuối, có `pr=0.5` và `cd=1`. Nếu dữ liệu thiếu điểm không đủ điều kiện xếp hạng, loại `score IS NULL` khỏi quần thể trước khi tính và trình bày trạng thái “chưa có điểm” riêng.

### Đáp án 14

```sql
SELECT
    percentile_cont(0.75)
        WITHIN GROUP (ORDER BY score::double precision)
        AS continuous_p75,
    percentile_disc(0.75)
        WITHIN GROUP (ORDER BY score)
        AS discrete_p75
FROM distribution_lab.measurements
WHERE segment = 'north';
```

Kết quả **95** và **90**. `percentile_cont` nội suy giữa các vị trí, còn `percentile_disc` chọn giá trị có thật tại ngưỡng tích lũy phù hợp.

### Đáp án 15

```sql
WITH counts AS (
    SELECT
        width_bucket(score, 0::numeric, 160::numeric, 4) AS bucket,
        COUNT(*) AS n
    FROM distribution_lab.measurements
    WHERE segment = 'north'
      AND score >= 0
      AND score < 160
    GROUP BY 1
)
SELECT b.bucket, COALESCE(c.n, 0) AS n
FROM generate_series(1, 4) AS b(bucket)
LEFT JOIN counts AS c ON c.bucket = b.bucket
ORDER BY b.bucket;
```

Histogram theo độ rộng có kích thước `0,3,4,1`; `NTILE(4)` theo số hàng có `2,2,2,2`.

### Đáp án 16

```sql
WITH ranked AS (
    SELECT
        measure_id,
        score,
        NTILE(4) OVER (
            ORDER BY score DESC, measure_id
        ) AS tile,
        CUME_DIST() OVER (
            ORDER BY score DESC
        ) AS cd
    FROM distribution_lab.measurements
    WHERE segment = 'north'
)
SELECT measure_id, score, tile, cd
FROM ranked
WHERE tile = 1 OR cd <= 0.25
ORDER BY score DESC, measure_id;
```

Với north, cả hai cách chọn ID 108 và 107. Nhưng khi một nhóm peers chạm ranh giới, NTILE có thể tách nhóm để gần đúng quota, còn CUME_DIST dùng cả peer group nên có thể loại toàn bộ nhóm ở ngưỡng `<=`.

### Đáp án 17

```sql
SELECT
    score,
    RANK() OVER (ORDER BY score) AS rnk,
    DENSE_RANK() OVER (ORDER BY score) AS dense_rnk
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score;
```

Score 90 có `RANK=4` và `DENSE_RANK=3`. Score 110 có `RANK=7`, `DENSE_RANK=4`. `RANK` nhảy các vị trí bị peers chiếm; `DENSE_RANK` chỉ đếm các mức điểm distinct.

### Đáp án 18

```sql
SELECT
    measure_id,
    segment,
    score,
    COUNT(*) OVER (
        PARTITION BY segment
    ) AS sample_size
FROM distribution_lab.measurements
ORDER BY segment, measure_id;
```

Percentile trên pilot N=1 không có sức phân biệt; trên south N=5 cũng có bước nhảy lớn. Cỡ mẫu giúp người xem diễn giải hợp lý.

### Đáp án 19

```sql
WITH spending AS (
    SELECT
        customer_id,
        SUM(amount) AS total_spent
    FROM some_orders
    WHERE status = 'completed'
    GROUP BY customer_id
)
SELECT
    customer_id,
    total_spent,
    NTILE(4) OVER (
        ORDER BY total_spent DESC, customer_id
    ) AS spending_tier
FROM spending;
```

`some_orders` ở đây là **tên giả định cần thay bằng bảng thực tế có các cột tương ứng**, không phải một bảng đã tạo trong lab. CTE `spending` bảo đảm một hàng mỗi khách có đơn completed trước khi chia tier.

### Đáp án 20

```sql
SELECT
    measure_id,
    segment,
    score,
    COUNT(*) OVER (
        PARTITION BY segment
    ) AS segment_size,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score DESC, measure_id
    ) AS bucket,
    PERCENT_RANK() OVER (
        PARTITION BY segment
        ORDER BY score DESC
    ) AS percent_rank,
    CUME_DIST() OVER (
        PARTITION BY segment
        ORDER BY score DESC
    ) AS cume_dist
FROM distribution_lab.measurements
WHERE score IS NOT NULL
ORDER BY segment, bucket, score DESC, measure_id;
```

`bucket` có khóa phụ để chia ổn định khi điểm trùng; `percent_rank` và `cume_dist` chỉ sắp theo score để giữ peers.

## 29. Checklist chọn hàm phù hợp

Trước khi đưa metric phân bố lên dashboard hoặc vào logic quyết định:

1. **Xác định câu hỏi:** cần bucket gần đều số người, vị trí rank tương đối, hay tỷ lệ tích lũy?
2. **Định nghĩa quần thể:** toàn bộ, từng region, theo kỳ, hay theo nhóm vai trò?
3. **Định nghĩa grain:** mỗi người, mỗi đơn hàng, mỗi giao dịch hay mỗi phiên đo?
4. **Xác định chiều tốt/xấu:** điểm cao tốt hay latency thấp tốt?
5. **Quy định xử lý ties:** có thể chia cùng điểm giữa các nhóm hay phải giữ chung?
6. **Quy định NULL:** bỏ, đánh dấu chưa đủ điều kiện hay gán giá trị theo business rule?
7. **Kiểm tra kích thước partition:** N=1 và N rất nhỏ thường không cho phân vị có ý nghĩa mạnh.
8. **Kiểm tra ngưỡng:** ngưỡng theo score (`percentile_cont/disc`) khác bucket theo số hàng (`NTILE`).
9. **Lọc đúng cấp:** tính rank trên đúng quần thể trước rồi mới lọc hiển thị nếu cần.
10. **Giữ output có thứ tự:** `ORDER BY` của window và `ORDER BY` ngoài phục vụ hai mục đích riêng.
11. **Đo hiệu năng:** dữ liệu lớn cần xem `WindowAgg`, sort, index, số hàng input và chi phí JOIN.
12. **Đặt tên metric minh bạch:** kèm phương pháp, quần thể, kỳ đo, chiều và chính sách ties.

## 30. Tổng kết

Các hàm `NTILE`, `PERCENT_RANK` và `CUME_DIST` cùng hỗ trợ phân tích phân bố trong PostgreSQL, nhưng **khác mục tiêu và cách tính**:

- **`NTILE(n)`** chia số hàng trong từng partition thành tối đa `n` nhóm gần đều về số lượng; nếu có ties ở ranh giới, những hàng cùng điểm có thể bị chia sang các bucket khác nhau.
- **`PERCENT_RANK()`** trả vị trí tương đối từ `RANK` qua công thức `(rank-1)/(N-1)`, với trường hợp N=1 cho kết quả 0. Nó dùng **vị trí bắt đầu của peer group**.
- **`CUME_DIST()`** trả tỷ lệ tích lũy số hàng đứng trước hoặc thuộc peer group hiện tại, chia N. Nó dùng **vị trí kết thúc của peer group**; nhóm cuối luôn có kết quả 1.
- **`PARTITION BY`** tạo quần thể so sánh riêng; **`ORDER BY`** xác định chiều xếp hạng và các peers. Thêm ID vào ORDER BY có thể giúp NTILE ổn định nhưng đồng thời làm thay đổi kết quả PERCENT_RANK/CUME_DIST nếu dùng chung window.
- **`percentile_cont` và `percentile_disc`** dùng để tìm **ngưỡng điểm phân vị**, khác với metric vị trí trả về cho từng hàng. **`width_bucket`** chia theo độ rộng khoảng giá trị, không chia gần đều số lượng quan sát.
- **NULL, ties, cỡ mẫu, grain và WHERE** quyết định liệu kết quả có đúng ý nghĩa thống kê và nghiệp vụ hay không.

Nguyên tắc lựa chọn ngắn gọn: **muốn chia danh sách thành các nhóm người gần bằng nhau thì dùng `NTILE`; muốn biết vị trí xếp hạng tương đối theo `RANK` thì dùng `PERCENT_RANK`; muốn biết tỷ lệ quan sát nằm tới một mức điểm thì dùng `CUME_DIST`.** Nếu câu hỏi là “điểm ở phân vị 75% bằng bao nhiêu?”, hãy chuyển sang `percentile_cont` hoặc `percentile_disc` thay vì tìm một giá trị percent_rank gần 0.75 rồi coi đó là ngưỡng chính thức.
