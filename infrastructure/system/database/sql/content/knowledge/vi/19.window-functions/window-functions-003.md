# ROW_NUMBER, RANK, DENSE_RANK và cách xử lý đồng hạng

Một bảng xếp hạng tưởng như chỉ cần `ORDER BY score DESC`, nhưng khi **hai hoặc nhiều dòng có cùng điểm**, hệ thống phải trả lời các câu hỏi khó hơn: “Hai người bằng điểm có cùng hạng không?”, “Sau hai người đồng hạng nhì, người tiếp theo là hạng ba hay hạng tư?”, “Nếu giao diện chỉ có ba vị trí thì chọn đúng ba dòng bằng cách nào?”, và “Nếu cần lấy tất cả người đồng hạng tại vị trí cuối cùng thì sao?”.

SQL cung cấp ba hàm cửa sổ (*window functions*) rất hữu ích:

- **`ROW_NUMBER()`**: cấp số thứ tự **riêng cho từng dòng**, không để hai dòng có cùng số.
- **`RANK()`**: những dòng **đồng hạng** nhận cùng số hạng và **để khoảng trống** cho các vị trí đã bị chiếm.
- **`DENSE_RANK()`**: những dòng **đồng hạng** nhận cùng số hạng nhưng **không để khoảng trống** giữa các mức hạng.

Cả ba thường xuất hiện trong `OVER (PARTITION BY ... ORDER BY ...)`. Chúng không đơn thuần là ba cách viết cho cùng kết quả: **mỗi hàm phản ánh một quy tắc nghiệp vụ khác nhau**.

Bài học thuộc chương **Hàm cửa sổ** của module **Database SQL**, lấy **PostgreSQL** làm môi trường thực hành chính. Ngoài cách viết cú pháp, bài sẽ làm rõ khái niệm *đồng hạng* (*ties/peers*), cách đặt khóa phân xử, lấy top-N theo **số dòng** hay **mức hạng**, lọc theo kết quả hàm cửa sổ và những trường hợp dễ làm báo cáo sai dù SQL vẫn chạy.

## 1. Bắt đầu từ một bảng điểm có đồng hạng

Giả sử một cuộc thi có hai khu vực `North` và `South`. Mỗi người dự thi có đúng một dòng trong bảng `rank_lab_scores`, được nhận diện bởi `participant_id`.

| participant_id | full_name | region | score |
|---:|---|---|---:|
| 101 | An | North | 100 |
| 102 | Bình | North | 90 |
| 103 | Chi | North | 90 |
| 104 | Dũng | North | 80 |
| 105 | Hà | North | 80 |
| 106 | Hòa | North | 80 |
| 107 | Lan | North | 70 |
| 201 | Mai | South | 95 |
| 202 | Nam | South | 95 |
| 203 | Oanh | South | 85 |
| 204 | Phúc | South | 70 |
| 205 | Quỳnh | South | 70 |
| 206 | Sơn | South | 60 |

Mục tiêu đầu tiên: **xếp hạng người dự thi trong từng khu vực, điểm cao đứng trước**.

Ở khu vực `North`, các điểm theo thứ tự giảm dần là:

```text
100, 90, 90, 80, 80, 80, 70
```

Trong đó có **hai người bằng 90** và **ba người bằng 80**. Một kết quả bảng xếp hạng đúng phải thể hiện quy tắc xử lý những nhóm đồng điểm này.

### 1.1. Ba cách đánh số cho cùng một dãy điểm

| Người | Điểm | `ROW_NUMBER` | `RANK` | `DENSE_RANK` |
|---|---:|---:|---:|---:|
| An | 100 | 1 | 1 | 1 |
| Bình | 90 | 2 | 2 | 2 |
| Chi | 90 | 3 | 2 | 2 |
| Dũng | 80 | 4 | 4 | 3 |
| Hà | 80 | 5 | 4 | 3 |
| Hòa | 80 | 6 | 4 | 3 |
| Lan | 70 | 7 | 7 | 4 |

Ở đây cột `ROW_NUMBER` giả định thêm `participant_id ASC` để phân xử những người đồng điểm. Nếu chỉ sắp theo `score DESC`, hai người có cùng điểm có thể nhận số dòng theo thứ tự khác.

Quan sát ba quy tắc:

```text
Điểm:        100    90    90    80    80    80    70
ROW_NUMBER:    1     2     3     4     5     6     7
RANK:          1     2     2     4     4     4     7
DENSE_RANK:    1     2     2     3     3     3     4
```

**`ROW_NUMBER`** không lặp số; **`RANK`** lặp hạng và bỏ qua một số hạng; **`DENSE_RANK`** lặp hạng nhưng đánh các mức điểm liên tiếp.

Nếu bạn chỉ nhớ một hình minh họa của bài, hãy nhớ ba dãy số này.

## 2. Tạo bảng thực hành trong PostgreSQL

Chạy đoạn SQL sau trên một **database thử nghiệm**. `CREATE TEMP TABLE` tạo bảng tạm, tự hết hiệu lực khi kết thúc phiên kết nối PostgreSQL.

```sql
CREATE TEMP TABLE rank_lab_scores (
    participant_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    region TEXT NOT NULL,
    score NUMERIC(8, 2) NOT NULL,
    achieved_at TIMESTAMP NOT NULL
);

INSERT INTO rank_lab_scores
    (participant_id, full_name, region, score, achieved_at)
VALUES
    (101, 'An',     'North', 100, TIMESTAMP '2026-06-01 09:00:00'),
    (102, 'Bình',   'North',  90, TIMESTAMP '2026-06-02 11:00:00'),
    (103, 'Chi',    'North',  90, TIMESTAMP '2026-06-02 10:00:00'),
    (104, 'Dũng',   'North',  80, TIMESTAMP '2026-06-03 08:00:00'),
    (105, 'Hà',     'North',  80, TIMESTAMP '2026-06-03 08:00:00'),
    (106, 'Hòa',    'North',  80, TIMESTAMP '2026-06-04 10:00:00'),
    (107, 'Lan',    'North',  70, TIMESTAMP '2026-06-05 09:00:00'),
    (201, 'Mai',    'South',  95, TIMESTAMP '2026-06-01 09:00:00'),
    (202, 'Nam',    'South',  95, TIMESTAMP '2026-06-02 09:00:00'),
    (203, 'Oanh',   'South',  85, TIMESTAMP '2026-06-03 09:00:00'),
    (204, 'Phúc',   'South',  70, TIMESTAMP '2026-06-04 09:00:00'),
    (205, 'Quỳnh',  'South',  70, TIMESTAMP '2026-06-04 09:00:00'),
    (206, 'Sơn',    'South',  60, TIMESTAMP '2026-06-06 09:00:00');

SELECT participant_id, full_name, region, score, achieved_at
FROM rank_lab_scores
ORDER BY region, score DESC, participant_id ASC;
```

`participant_id` là **khóa chính**, vì vậy có thể dùng làm khóa phân xử duy nhất khi cần tạo thứ tự xác định. `achieved_at` ghi thời điểm đạt điểm, phục vụ ví dụ quy tắc phân xử khác. Việc lưu `TIMESTAMP` không kèm múi giờ chỉ là mô hình thời gian đơn giản cho dữ liệu mẫu; hệ thống lưu thời điểm thật ở nhiều khu vực thường nên cân nhắc `TIMESTAMPTZ` và quy tắc múi giờ phù hợp.

Nếu trong phiên hiện tại đã có một bảng tạm cùng tên, hãy dùng phiên thực hành mới hoặc đổi tên bảng. Không chạy script này lên bảng sản xuất.

## 3. Cú pháp chung của ba hàm cửa sổ

Hàm cửa sổ có dạng:

```sql
window_function() OVER (
    PARTITION BY group_expression
    ORDER BY sort_expression
)
```

Trong bài này:

```sql
SELECT
    participant_id,
    full_name,
    region,
    score,
    ROW_NUMBER() OVER (
        PARTITION BY region
        ORDER BY score DESC, participant_id ASC
    ) AS row_no,
    RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS rank_no,
    DENSE_RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS dense_rank_no
FROM rank_lab_scores
ORDER BY region, score DESC, participant_id ASC;
```

Cả ba hàm không nhận đối số trong dấu ngoặc `()`. Quy tắc phân chia và thứ tự nằm trong mệnh đề **`OVER`**.

| Thành phần | Vai trò |
|---|---|
| `PARTITION BY region` | Chia các dòng thành những **phân vùng** độc lập theo khu vực |
| `ORDER BY score DESC` | Xác định ai có điểm cao hơn, và những dòng nào **đồng hạng theo điểm** |
| `ORDER BY score DESC, participant_id ASC` | Xác định thứ tự riêng cho từng dòng, kể cả khi điểm bằng nhau |
| `ROW_NUMBER()` | Đánh số lần lượt 1, 2, 3… trong phân vùng |
| `RANK()` | Cho các dòng đồng hạng cùng hạng, có khoảng trống |
| `DENSE_RANK()` | Cho các dòng đồng hạng cùng hạng, không có khoảng trống |

### 3.1. `PARTITION BY` là tùy chọn

Không có `PARTITION BY`, toàn bộ kết quả đầu vào của cửa sổ được xem như **một phân vùng**:

```sql
SELECT
    participant_id,
    region,
    score,
    RANK() OVER (ORDER BY score DESC) AS global_rank
FROM rank_lab_scores
ORDER BY score DESC, participant_id;
```

Ở đây Mai và Nam (95 điểm) đứng **sau An (100 điểm)** trong bảng xếp hạng toàn cuộc thi. Nhưng khi `PARTITION BY region`, Mai và Nam cùng **hạng 1 của South**, còn An **hạng 1 của North**. Cùng một hàm `RANK()` nhưng **phạm vi so sánh** đã khác.

### 3.2. `ORDER BY` trong `OVER` và `ORDER BY` ngoài có hai nhiệm vụ

```sql
SELECT
    participant_id,
    score,
    RANK() OVER (ORDER BY score DESC) AS rank_no
FROM rank_lab_scores
ORDER BY participant_id ASC;
```

Trong truy vấn này:

- `ORDER BY score DESC` **trong `OVER`** quyết định hạng theo điểm.
- `ORDER BY participant_id ASC` **ở cuối truy vấn** quyết định **thứ tự dòng được hiển thị**.

Kết quả có thể được in từ `participant_id` nhỏ tới lớn dù số hạng không xuất hiện lần lượt 1, 2, 3. Đó không phải lỗi: hàm cửa sổ đã tính hạng theo **một** quy tắc, còn kết quả được hiển thị theo **quy tắc khác**.

Nếu muốn bảng được trình bày theo thứ tự xếp hạng, hãy thêm `ORDER BY` phù hợp ở cấp `SELECT` ngoài:

```sql
ORDER BY region, score DESC, participant_id ASC
```

**Đừng mặc định `ORDER BY` bên trong `OVER` tự bảo đảm thứ tự hiển thị của kết quả cuối.**

## 4. `ROW_NUMBER()`: số thứ tự duy nhất cho từng dòng

`ROW_NUMBER()` gán một số nguyên liên tiếp, bắt đầu từ **1 trong mỗi phân vùng**:

```sql
SELECT
    participant_id,
    full_name,
    region,
    score,
    ROW_NUMBER() OVER (
        PARTITION BY region
        ORDER BY score DESC, participant_id ASC
    ) AS row_no
FROM rank_lab_scores
ORDER BY region, row_no;
```

Trong `North`, kết quả `row_no` từ 1 đến 7. Trong `South`, nó **bắt đầu lại từ 1** đến 6.

| North | Điểm | `row_no` |
|---|---:|---:|
| An | 100 | 1 |
| Bình | 90 | 2 |
| Chi | 90 | 3 |
| Dũng | 80 | 4 |
| Hà | 80 | 5 |
| Hòa | 80 | 6 |
| Lan | 70 | 7 |

### 4.1. Đồng điểm vẫn phải nhận hai số khác nhau

Vì Bình và Chi đều có 90 điểm, một hàm `ROW_NUMBER()` **phải** cho một người số 2 và người kia số 3. Chọn ai đứng trước phụ thuộc **tất cả các biểu thức trong `ORDER BY` của cửa sổ**.

Nếu chỉ viết:

```sql
ROW_NUMBER() OVER (
    PARTITION BY region
    ORDER BY score DESC
)
```

thì SQL chưa quy định thứ tự giữa Bình và Chi; họ có thể nhận `row_no` 2 hoặc 3 theo thứ tự không được bảo đảm. Cách máy lưu bản ghi, thứ tự chèn hay kết quả một lần chạy trước **không thay thế khóa phân xử**.

Trong bảng có khóa chính duy nhất `participant_id`, ta thêm:

```sql
ORDER BY score DESC, participant_id ASC
```

Khi cùng điểm, ID nhỏ hơn đứng trước: Bình (102) có `row_no=2`, Chi (103) có `row_no=3`.

### 4.2. `ROW_NUMBER` phù hợp khi nào?

- Chọn **đúng một dòng** đại diện cho mỗi nhóm theo quy tắc ưu tiên.
- Lấy **tối đa N dòng** của từng nhóm.
- Đánh số thứ tự hiển thị trong danh sách đã được sắp xác định.
- Xử lý nhiều phiên bản của một bản ghi và giữ một dòng mới nhất (khi đã định nghĩa cách xử lý timestamp đồng hạng).

Nếu nghiệp vụ muốn hai người đồng điểm **được công nhận cùng hạng**, `ROW_NUMBER()` không phải thước đo hạng thi đấu phù hợp; nó chỉ cho biết **vị trí sau khi đã phân xử**.

### 4.3. `ROW_NUMBER` không phải khóa chính lâu dài

`row_no` được tính lại **theo tập dòng và thứ tự của truy vấn hiện tại**. Nếu có người mới tham gia, điểm thay đổi hoặc điều kiện `WHERE` khác, số của một người có thể đổi. Không lưu `row_no` như mã nhận diện ổn định thay thế `participant_id`.

## 5. `RANK()`: đồng hạng kiểu thi đấu, có khoảng trống

`RANK()` cấp cùng một hạng cho những dòng có **cùng các giá trị sắp xếp trong `ORDER BY` của chính cửa sổ đó**.

```sql
SELECT
    participant_id,
    full_name,
    region,
    score,
    RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS rank_no
FROM rank_lab_scores
ORDER BY region, score DESC, participant_id;
```

Ở `North`:

```text
An            100 điểm → hạng 1
Bình, Chi      90 điểm → đồng hạng 2
Dũng, Hà, Hòa  80 điểm → đồng hạng 4
Lan            70 điểm → hạng 7
```

Tại sao sau hai người đồng hạng 2 lại là **hạng 4**? Vì:

- Hạng 1 đã có 1 người.
- Vị trí thứ 2 và thứ 3 thuộc về **hai người đồng hạng 2**.
- Người tiếp theo ở vị trí thứ 4, nên nhận `RANK=4`.

Tương tự, ba người đồng hạng 4 chiếm các vị trí 4, 5, 6; người tiếp theo là hạng 7.

### 5.1. Cách hiểu bằng số dòng đứng trước

Với thứ tự điểm giảm dần:

\[
\operatorname{RANK}(x)
=1+\#\{\text{dòng trong cùng phân vùng có điểm lớn hơn điểm của }x\}.
\]

Trong bảng `North`, trước các người 80 điểm có ba người đạt điểm lớn hơn (100, 90, 90), nên hạng của họ là **1+3=4**.

Công thức này diễn tả trường hợp **chỉ xếp theo điểm**. Nếu `ORDER BY` gồm nhiều biểu thức, “đứng trước” phải xét **toàn bộ bộ khóa sắp xếp**, không riêng điểm.

### 5.2. `RANK` phù hợp khi nào?

- Bảng xếp hạng thi đấu: hai người đồng thành tích có cùng hạng.
- Báo cáo muốn các số hạng phản ánh **số người đã chiếm các vị trí trước đó**.
- Lấy các người thuộc **N vị trí thi đấu đầu**, chấp nhận đồng hạng làm số dòng kết quả thay đổi.

**Không nên** dùng `RANK()` nếu báo cáo cần mức hạng liên tục 1, 2, 3 bất kể có bao nhiêu người đồng điểm; trường hợp đó là `DENSE_RANK()`.

## 6. `DENSE_RANK()`: đồng hạng nhưng không bỏ số hạng

`DENSE_RANK()` cũng cho cùng hạng khi các khóa sắp xếp bằng nhau, nhưng số hạng **tăng đúng 1 khi chuyển sang mức khóa mới**.

```sql
SELECT
    participant_id,
    full_name,
    region,
    score,
    DENSE_RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS dense_rank_no
FROM rank_lab_scores
ORDER BY region, score DESC, participant_id;
```

Ở `North`:

```text
Điểm khác nhau: 100 → 90 → 80 → 70
DENSE_RANK:      1 →  2 →  3 →  4
```

Mọi người 90 điểm cùng hạng 2. Mọi người 80 điểm cùng hạng 3. Lan 70 điểm hạng 4, không phải hạng 7 như `RANK`.

### 6.1. Cách hiểu bằng số mức điểm khác nhau

Với xếp theo điểm giảm dần:

\[
\operatorname{DENSE\_RANK}(x)
=1+\#\{\text{mức điểm phân biệt lớn hơn điểm của }x\}.
\]

Trước mức 80 có **hai mức điểm khác nhau** là 100 và 90, vì vậy mức 80 có `DENSE_RANK=3`, mặc dù có **ba người** đạt điểm cao hơn 80.

### 6.2. `DENSE_RANK` phù hợp khi nào?

- Muốn liệt kê **ba mức điểm cao nhất** và lấy mọi người ở các mức đó.
- Báo cáo muốn phân nhóm thứ hạng liên tiếp không bỏ số: mức 1, mức 2, mức 3…
- Phân loại theo thứ tự các giá trị riêng biệt, không cần số hạng phản ánh số người phía trước.

Không nên coi `DENSE_RANK=3` luôn có nghĩa “người đứng thứ ba”: ở `North`, hạng dày 3 bao gồm **ba người 80 điểm**, đứng ở vị trí 4–6 trong thứ tự dòng.

## 7. So sánh ba hàm trên cả hai khu vực

Câu truy vấn tổng hợp:

```sql
SELECT
    region,
    participant_id,
    full_name,
    score,
    ROW_NUMBER() OVER (
        PARTITION BY region
        ORDER BY score DESC, participant_id ASC
    ) AS row_no,
    RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS competition_rank,
    DENSE_RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS dense_rank_no
FROM rank_lab_scores
ORDER BY region, score DESC, participant_id ASC;
```

Kết quả dự kiến:

| Region | ID | Điểm | `row_no` | `competition_rank` | `dense_rank_no` |
|---|---:|---:|---:|---:|---:|
| North | 101 | 100 | 1 | 1 | 1 |
| North | 102 | 90 | 2 | 2 | 2 |
| North | 103 | 90 | 3 | 2 | 2 |
| North | 104 | 80 | 4 | 4 | 3 |
| North | 105 | 80 | 5 | 4 | 3 |
| North | 106 | 80 | 6 | 4 | 3 |
| North | 107 | 70 | 7 | 7 | 4 |
| South | 201 | 95 | 1 | 1 | 1 |
| South | 202 | 95 | 2 | 1 | 1 |
| South | 203 | 85 | 3 | 3 | 2 |
| South | 204 | 70 | 4 | 4 | 3 |
| South | 205 | 70 | 5 | 4 | 3 |
| South | 206 | 60 | 6 | 6 | 4 |

`South` là ví dụ bổ sung: **hai người đồng hạng nhất** nên người 85 điểm nhận `RANK=3` chứ không phải 2. `DENSE_RANK` coi 95 là mức 1, 85 là mức 2, 70 là mức 3 và 60 là mức 4.

### 7.1. Quan hệ giữa các giá trị

Trong một phân vùng có thứ tự xác định cho mọi dòng:

- `ROW_NUMBER()` tăng **một đơn vị cho mỗi dòng**.
- `RANK()` tăng theo **số dòng của nhóm đồng hạng trước đó**.
- `DENSE_RANK()` tăng **một đơn vị cho mỗi nhóm đồng hạng khác nhau**.

Vì thế, trong các bảng xếp hạng như ví dụ:

```text
DENSE_RANK <= RANK <= ROW_NUMBER
```

Khi không có bất kỳ đồng hạng nào theo khóa sắp xếp dùng cho `RANK` và `DENSE_RANK`, cả ba có thể cho cùng dãy số 1,2,3,… nếu chúng dùng **cùng một thứ tự toàn phần**.

### 7.2. Tên gọi không quyết định quy tắc nghiệp vụ

Một sản phẩm có thể gọi “Top 3” là **ba người**, một cuộc thi có thể gọi “Top 3” là **ba vị trí hạng theo kiểu thi đấu**, còn một thống kê có thể gọi “Top 3” là **ba mức điểm khác nhau**. Ba yêu cầu tạo số dòng khác nhau. Cần chốt ý nghĩa trước khi chọn `ROW_NUMBER`, `RANK` hoặc `DENSE_RANK`.

## 8. Đồng hạng thực sự được xác định bởi biểu thức nào?

Trong `RANK()` và `DENSE_RANK()`, hai dòng được coi là **đồng hạng** khi chúng thuộc **cùng phân vùng** và các giá trị của **mọi biểu thức `ORDER BY` bên trong `OVER`** bằng nhau theo quy tắc sắp xếp của hệ quản trị.

Ví dụ:

```sql
RANK() OVER (
    PARTITION BY region
    ORDER BY score DESC
)
```

Chỉ xét điểm. Bình và Chi cùng 90 điểm nên đồng hạng.

Nhưng nếu thêm thời điểm đạt điểm:

```sql
RANK() OVER (
    PARTITION BY region
    ORDER BY score DESC, achieved_at ASC
)
```

quy tắc mới trở thành **“điểm cao hơn đứng trước; cùng điểm thì người đạt sớm hơn đứng trước”**. Chi đạt 90 lúc `2026-06-02 10:00`, Bình đạt 90 lúc `11:00`; họ **không còn đồng hạng theo bộ khóa mới**.

Trong khi đó Dũng và Hà cùng 80 điểm, cùng thời điểm `2026-06-03 08:00`, nên vẫn đồng hạng nếu chỉ dùng hai khóa `score` và `achieved_at`.

### 8.1. Ba mức quyết định khác nhau

Hãy phân biệt:

1. **Định nghĩa thành tích:** dùng `score` để xếp hạng, mọi người bằng điểm được công nhận đồng hạng.
2. **Quy tắc phân xử thành tích:** thêm `achieved_at` để quyết định ai hạng cao hơn khi bằng điểm; trường hợp này **đã thay đổi định nghĩa đồng hạng**.
3. **Thứ tự trình bày trong nhóm đồng hạng:** giữ `RANK() OVER (ORDER BY score DESC)` nhưng trình bày theo `score DESC, achieved_at ASC, participant_id ASC` ở `ORDER BY` **ngoài cùng**. Lúc này đồng hạng vẫn được giữ, nhưng thứ tự hiển thị giữa người đồng điểm trở nên rõ ràng.

Ví dụ đáp ứng trường hợp thứ ba:

```sql
SELECT
    participant_id,
    full_name,
    region,
    score,
    achieved_at,
    RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS official_rank
FROM rank_lab_scores
ORDER BY region, score DESC, achieved_at ASC, participant_id ASC;
```

**Điểm mấu chốt:** không tự thêm `participant_id` vào `RANK() OVER (ORDER BY ...)` chỉ với mục đích làm thứ tự ổn định, nếu chính sách yêu cầu **giữ đồng hạng theo điểm**.

### 8.2. Vì sao `RANK` biến thành thứ tự từng dòng nếu thêm ID duy nhất?

```sql
RANK() OVER (
    PARTITION BY region
    ORDER BY score DESC, participant_id ASC
)
```

Vì `participant_id` là **duy nhất** trên từng dòng, không còn hai dòng nào bằng nhau trên **toàn bộ bộ khóa** `(score, participant_id)`. Mọi nhóm đồng hạng trở thành nhóm chỉ có **một dòng**. Trong bảng mẫu, `RANK()` này tạo các số `1,2,3,...` giống `ROW_NUMBER()` theo cùng bộ khóa.

Đó có thể là ý định đúng nếu cuộc thi thực sự dùng ID làm **tiêu chí xếp hạng chính thức**, nhưng thường là sai nếu hai người bằng điểm cần được công nhận đồng hạng.

## 9. Lấy Top-N: theo số dòng, hạng thi đấu hay mức điểm?

Đây là ứng dụng quan trọng nhất của ba hàm.

### 9.1. Top 3 **người** của mỗi khu vực — `ROW_NUMBER()`

Yêu cầu: “Mỗi khu vực chọn **không quá ba người**. Nếu bằng điểm thì ID nhỏ hơn đứng trước.”

```sql
WITH numbered AS (
    SELECT
        participant_id,
        full_name,
        region,
        score,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY score DESC, participant_id ASC
        ) AS row_no
    FROM rank_lab_scores
)
SELECT participant_id, full_name, region, score, row_no
FROM numbered
WHERE row_no <= 3
ORDER BY region, row_no;
```

Kết quả:

```text
North: 101 (An), 102 (Bình), 103 (Chi)
South: 201 (Mai), 202 (Nam), 203 (Oanh)
```

Mỗi khu vực có **đúng ba dòng** vì cả hai đều có ít nhất ba người. Nếu khu vực chỉ có hai người, điều kiện `row_no <= 3` trả hai dòng, không tự tạo dòng trống.

### 9.2. Top 3 **vị trí thi đấu** — `RANK()`

Yêu cầu: “Lấy mọi người có **hạng thi đấu từ 1 đến 3** theo điểm, kể cả đồng hạng.”

```sql
WITH ranked AS (
    SELECT
        participant_id,
        full_name,
        region,
        score,
        RANK() OVER (
            PARTITION BY region
            ORDER BY score DESC
        ) AS rank_no
    FROM rank_lab_scores
)
SELECT participant_id, full_name, region, score, rank_no
FROM ranked
WHERE rank_no <= 3
ORDER BY region, score DESC, participant_id;
```

Trong bảng mẫu:

- `North`: An hạng 1; Bình và Chi đồng hạng 2. **Không có hạng 3**, nên lấy **3 người**.
- `South`: Mai và Nam đồng hạng 1; Oanh hạng 3. Lấy **3 người**.

Nếu lọc `rank_no <= 2`, `North` trả **3 người** (1,2,2), còn `South` trả **2 người** (1,1). **Số dòng không nhất thiết bằng N**.

### 9.3. Top 3 **mức điểm** — `DENSE_RANK()`

Yêu cầu: “Lấy tất cả người thuộc **ba mức điểm cao nhất** của mỗi khu vực.”

```sql
WITH ranked AS (
    SELECT
        participant_id,
        full_name,
        region,
        score,
        DENSE_RANK() OVER (
            PARTITION BY region
            ORDER BY score DESC
        ) AS dense_no
    FROM rank_lab_scores
)
SELECT participant_id, full_name, region, score, dense_no
FROM ranked
WHERE dense_no <= 3
ORDER BY region, score DESC, participant_id;
```

Kết quả:

```text
North: 101, 102, 103, 104, 105, 106
       (các mức điểm 100, 90, 80 → 6 người)

South: 201, 202, 203, 204, 205
       (các mức điểm 95, 85, 70 → 5 người)
```

Vì mỗi mức điểm có thể chứa nhiều người, số dòng thường **lớn hơn ba**.

### 9.4. Bảng lựa chọn nhanh

| Yêu cầu thật | Hàm | Có đồng hạng? | Số dòng có thể vượt N? |
|---|---|---|---|
| “Tối đa 3 người mỗi vùng” | `ROW_NUMBER() <= 3` | Phân xử để chọn các dòng | Không |
| “Mọi người có hạng thi đấu ≤ 3” | `RANK() <= 3` | Có, bỏ số hạng khi cần | Có |
| “Mọi người ở 3 mức điểm cao nhất” | `DENSE_RANK() <= 3` | Có, không bỏ mức hạng | Có |

**Không dùng tên “Top 3” trong yêu cầu API mà thiếu định nghĩa**. Cần làm rõ đó là ba dòng, ba vị trí xếp hạng hay ba mức giá trị.

## 10. `FETCH FIRST ... WITH TIES` và quan hệ với xếp hạng

PostgreSQL hỗ trợ dạng:

```sql
SELECT participant_id, full_name, score
FROM rank_lab_scores
WHERE region = 'North'
ORDER BY score DESC
FETCH FIRST 2 ROWS WITH TIES;
```

Ý nghĩa: lấy hai **dòng** đứng đầu theo sắp xếp, **đồng thời lấy thêm những dòng có khóa `ORDER BY` bằng với dòng cuối cùng được chọn**.

Với `North`, hai dòng đầu có mức điểm 100 và 90; người còn lại cũng có 90 nên kết quả là:

```text
An (100), Bình (90), Chi (90)
```

Ba người được chọn dù giới hạn ghi **2 ROWS**, vì `WITH TIES` mở rộng nhóm đồng điểm ở **ranh giới lấy dòng**.

### 10.1. `WITH TIES` không đồng nghĩa `DENSE_RANK <= N`

Với `North`, `FETCH FIRST 2 ROWS WITH TIES` trả điểm 100 và 90. `DENSE_RANK <= 2` cũng trả các điểm đó **trong ví dụ này**, nhưng hai cơ chế không hoàn toàn giống nhau.

Ví dụ lấy 3 dòng đầu của `North`: ba dòng đó có điểm 100, 90, 90, nên `FETCH FIRST 3 ROWS WITH TIES` vẫn chỉ trả **ba người**. Trong khi `DENSE_RANK <= 3` trả đến mức điểm 80 và lấy **sáu người**.

`WITH TIES` mở rộng **nhóm của dòng thứ N**, còn `DENSE_RANK <= N` chọn **N nhóm giá trị phân biệt**.

### 10.2. Cẩn thận với khóa phân xử

```sql
-- Mỗi bộ (score, participant_id) là duy nhất,
-- nên không còn đồng hạng theo ORDER BY này.
SELECT participant_id, full_name, score
FROM rank_lab_scores
WHERE region = 'North'
ORDER BY score DESC, participant_id ASC
FETCH FIRST 2 ROWS WITH TIES;
```

Truy vấn trên chỉ trả hai người An, Bình, **không kèm Chi**, bởi Chi khác Bình ở `participant_id`. Dù điểm bằng nhau, hai dòng **không có cùng toàn bộ bộ khóa `ORDER BY`**.

Đây là lý do cần phân biệt **đồng hạng nghiệp vụ theo điểm** và **khóa phân xử trình bày**. Muốn giữ đồng điểm tại ranh giới, có thể dùng `RANK()` tính theo điểm, lọc trong CTE, rồi `ORDER BY score DESC, participant_id ASC` bên ngoài.

`FETCH FIRST ... WITH TIES` hữu ích cho **toàn bộ kết quả sau `WHERE`**. Nếu cần “top-N của **từng khu vực**”, các hàm cửa sổ với `PARTITION BY` thường thuận tiện hơn.

## 11. Vì sao không viết hàm cửa sổ trực tiếp trong `WHERE`?

Người mới học thường thử:

```sql
-- Không hợp lệ trong PostgreSQL:
SELECT participant_id, region, score
FROM rank_lab_scores
WHERE ROW_NUMBER() OVER (
    PARTITION BY region
    ORDER BY score DESC
) <= 3;
```

Trong SQL, `WHERE` lọc **dòng nguồn** trước giai đoạn tính các hàm cửa sổ của cùng cấp truy vấn. Vì vậy, PostgreSQL không cho đặt hàm cửa sổ trực tiếp trong `WHERE`; tương tự, không đưa nó trực tiếp vào `HAVING` của cùng cấp.

Cách thường dùng là **tính trong một cấp truy vấn, lọc ở cấp ngoài**:

```sql
WITH numbered AS (
    SELECT
        participant_id,
        region,
        score,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY score DESC, participant_id ASC
        ) AS row_no
    FROM rank_lab_scores
)
SELECT *
FROM numbered
WHERE row_no <= 3
ORDER BY region, row_no;
```

Hoặc dùng truy vấn con trong `FROM`:

```sql
SELECT x.participant_id, x.region, x.score, x.row_no
FROM (
    SELECT
        participant_id,
        region,
        score,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY score DESC, participant_id ASC
        ) AS row_no
    FROM rank_lab_scores
) AS x
WHERE x.row_no <= 3
ORDER BY x.region, x.row_no;
```

Hai cách trên cùng mô tả một quy tắc: **tính số thứ tự trước trong kết quả trung gian, rồi lọc theo số đó ở truy vấn ngoài**.

Một số hệ quản trị khác có mệnh đề `QUALIFY` để lọc theo hàm cửa sổ trong cùng câu truy vấn, nhưng **PostgreSQL không dùng `QUALIFY`** theo cú pháp thông thường. Khi cần SQL di động, CTE hoặc truy vấn con là cách trình bày quen thuộc.

## 12. Lọc trước và lọc sau khi xếp hạng có thể cho kết quả khác

Đây là điểm quan trọng về ngữ nghĩa.

### 12.1. Lọc trước khi tính hạng

Yêu cầu: “Chỉ xét những người **dưới 95 điểm**, rồi xếp hạng lại họ trong từng khu vực.”

```sql
SELECT
    participant_id,
    region,
    score,
    RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS rank_within_filtered_people
FROM rank_lab_scores
WHERE score < 95
ORDER BY region, score DESC, participant_id;
```

`WHERE score < 95` chạy trước khi cửa sổ nhận dữ liệu:

- `North`: An 100 bị loại; Bình và Chi 90 trở thành **đồng hạng 1**.
- `South`: Mai và Nam 95 bị loại; Oanh 85 trở thành **hạng 1**.

### 12.2. Xếp hạng toàn bộ trước, rồi mới lọc

Yêu cầu khác: “Xếp hạng tất cả người trong khu vực, sau đó chỉ **hiển thị** những người dưới 95 điểm nhưng giữ **hạng gốc**.”

```sql
WITH complete_ranking AS (
    SELECT
        participant_id,
        region,
        score,
        RANK() OVER (
            PARTITION BY region
            ORDER BY score DESC
        ) AS original_rank
    FROM rank_lab_scores
)
SELECT participant_id, region, score, original_rank
FROM complete_ranking
WHERE score < 95
ORDER BY region, score DESC, participant_id;
```

Lúc này:

- Bình và Chi vẫn **đồng hạng 2** của North, vì An vẫn tham gia vào lúc tính hạng.
- Oanh vẫn **hạng 3** của South, vì Mai và Nam cùng hạng 1 đã được tính.

**Hai truy vấn dùng cùng điều kiện `score < 95`, nhưng câu hỏi khác nhau**: “xếp hạng trong nhóm đã lọc” hay “lọc hiển thị trong bảng xếp hạng gốc”.

Nếu ứng dụng có bộ lọc “chỉ người đang hoạt động”, phải quyết định người bị vô hiệu hóa có được tính vào thứ hạng của người còn lại hay không. Vị trí đặt `WHERE` sẽ thể hiện quyết định đó.

## 13. `PARTITION BY` không phải `GROUP BY`

Hai cú pháp đều có thể nhắc tới “nhóm”, nhưng kết quả khác nhau về **độ hạt** (*grain*).

### 13.1. `GROUP BY`: gộp thành một dòng mỗi nhóm

```sql
SELECT
    region,
    COUNT(*) AS participant_count,
    MAX(score) AS highest_score
FROM rank_lab_scores
GROUP BY region
ORDER BY region;
```

Kết quả chỉ có **hai dòng**, một dòng cho `North`, một dòng cho `South`.

### 13.2. `PARTITION BY` trong hàm cửa sổ: vẫn giữ mỗi người một dòng

```sql
SELECT
    participant_id,
    region,
    score,
    COUNT(*) OVER (
        PARTITION BY region
    ) AS people_in_region,
    MAX(score) OVER (
        PARTITION BY region
    ) AS highest_score_in_region,
    RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS region_rank
FROM rank_lab_scores
ORDER BY region, score DESC, participant_id;
```

Kết quả vẫn có **13 dòng**, vì mỗi người còn xuất hiện. `people_in_region` là 7 đối với North và 6 đối với South, lặp lại ở mỗi dòng của phân vùng tương ứng.

```text
GROUP BY region:
    13 dòng đầu vào → 2 dòng tổng hợp

Window PARTITION BY region:
    13 dòng đầu vào → 13 dòng + các giá trị phân tích theo vùng
```

Do đó, `RANK()` hữu ích khi cần xếp **từng người** trong nhóm mà không muốn gộp mọi người thành một dòng.

### 13.3. Khi cần xếp hạng các nhóm sau tổng hợp

Ví dụ muốn xếp hạng **khu vực** theo số người tham gia, trước tiên tổng hợp theo khu vực rồi dùng hàm cửa sổ trên kết quả tổng hợp:

```sql
WITH region_counts AS (
    SELECT
        region,
        COUNT(*) AS participant_count
    FROM rank_lab_scores
    GROUP BY region
)
SELECT
    region,
    participant_count,
    RANK() OVER (
        ORDER BY participant_count DESC
    ) AS region_rank
FROM region_counts
ORDER BY region_rank, region;
```

Kết quả: North có 7 người, hạng 1; South có 6 người, hạng 2. Khi xếp hạng trên các nhóm, **mỗi dòng đầu vào của cửa sổ bây giờ là một vùng**, không phải một người.

## 14. Đồng hạng theo nhiều tiêu chí

Trong một số bảng điểm, thành tích được quyết định bởi **nhiều tiêu chí**, chẳng hạn:

1. Điểm cao hơn trước.
2. Nếu cùng điểm, người đạt điểm sớm hơn trước.
3. Nếu cả điểm lẫn thời điểm bằng nhau, hai người vẫn đồng hạng theo luật.

Lúc đó:

```sql
SELECT
    participant_id,
    full_name,
    region,
    score,
    achieved_at,
    RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC, achieved_at ASC
    ) AS official_rank,
    DENSE_RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC, achieved_at ASC
    ) AS official_dense_rank
FROM rank_lab_scores
ORDER BY region, score DESC, achieved_at ASC, participant_id ASC;
```

Với North:

- An 100 điểm xếp trước.
- Chi đạt 90 lúc 10:00, trước Bình đạt 90 lúc 11:00, nên **không đồng hạng** khi thời gian là tiêu chí xếp hạng.
- Dũng và Hà cùng 80 điểm, cùng thời điểm 08:00 ngày 3/6, nên **vẫn đồng hạng**.
- Hòa 80 điểm nhưng đạt sau một ngày nên không đồng hạng với hai người trước, nếu thời gian là một phần của luật xếp hạng.

### 14.1. Thứ tự hiển thị cuối vẫn nên xác định

Nếu có hai người bằng nhau cả điểm và thời gian, `RANK` vẫn trả cùng hạng. Nhưng để danh sách không tráo vị trí ngẫu nhiên khi hiển thị, có thể thêm ID duy nhất **vào `ORDER BY` ngoài cùng**:

```sql
ORDER BY region, score DESC, achieved_at ASC, participant_id ASC
```

Đây là bước ổn định **thứ tự trình bày**, không thay đổi tiêu chí đồng hạng bên trong `RANK() OVER (...)`.

### 14.2. Định nghĩa đồng hạng phải được công bố

Câu “đồng điểm” chưa đủ nếu luật còn xét thời gian, số bài đúng, số lỗi, lượt làm lại hoặc các tiêu chí phụ. Trong hệ thống báo cáo thực:

- Ghi rõ các biểu thức `ORDER BY` dùng để **phân biệt hạng chính thức**.
- Chỉ thêm các tiêu chí phụ thực sự thuộc **luật xếp hạng**.
- Dùng khóa duy nhất ở **thứ tự ngoài** khi cần hiển thị ổn định nhưng vẫn giữ đồng hạng.

## 15. `NULL` trong điểm xếp hạng

Bảng thực hành khai báo `score NOT NULL`, nên các ví dụ chính không có điểm thiếu. Nhưng dữ liệu thực có thể có người chưa hoàn tất bài thi, được ghi `NULL`.

Trong PostgreSQL, quy tắc sắp xếp mặc định thường là:

- `ASC`: `NULL` ở cuối nếu không ghi ngược lại.
- `DESC`: `NULL` ở đầu nếu không ghi ngược lại.

Nếu người có điểm chưa xác định **không được xếp cao hơn người có điểm thực**, hãy viết tường minh:

```sql
ORDER BY score DESC NULLS LAST
```

### 15.1. Ví dụ điểm `NULL` với CTE `VALUES`

```sql
WITH sample(participant_id, score) AS (
    VALUES
        (1, 100::INTEGER),
        (2, NULL::INTEGER),
        (3, NULL::INTEGER),
        (4, 80::INTEGER)
)
SELECT
    participant_id,
    score,
    ROW_NUMBER() OVER (
        ORDER BY score DESC NULLS LAST, participant_id ASC
    ) AS row_no,
    RANK() OVER (
        ORDER BY score DESC NULLS LAST
    ) AS rank_no,
    DENSE_RANK() OVER (
        ORDER BY score DESC NULLS LAST
    ) AS dense_no
FROM sample
ORDER BY score DESC NULLS LAST, participant_id;
```

Kết quả:

| participant_id | score | `row_no` | `rank_no` | `dense_no` |
|---:|---:|---:|---:|---:|
| 1 | 100 | 1 | 1 | 1 |
| 4 | 80 | 2 | 2 | 2 |
| 2 | `NULL` | 3 | 3 | 3 |
| 3 | `NULL` | 4 | 3 | 3 |

Hai dòng có điểm `NULL` cùng một nhóm **đồng hạng theo khóa sắp xếp** của `RANK`/`DENSE_RANK`, dù trong phép so sánh thông thường `NULL = NULL` không trả `TRUE`.

### 15.2. Chính sách với điểm thiếu là quyết định nghiệp vụ

Có ít nhất ba cách:

1. **Loại người chưa có điểm trước khi xếp hạng:** `WHERE score IS NOT NULL`.
2. **Giữ và xếp cuối:** `ORDER BY score DESC NULLS LAST`.
3. **Tách nhóm trạng thái:** tạo phân loại `CASE` hoặc dùng quy tắc hiển thị riêng cho người chưa đủ điều kiện.

Không nên dùng `COALESCE(score, 0)` một cách tùy tiện nếu **0 điểm hợp lệ** khác với **chưa có điểm**. Nếu dùng quy tắc quy đổi, phải được nghiệp vụ xác nhận.

### 15.3. Khả chuyển hệ quản trị

`NULLS FIRST`/`NULLS LAST` không có cùng mức hỗ trợ cú pháp ở mọi hệ quản trị. Có thể dùng biểu thức `CASE` khi cần chủ động đặt nhóm `NULL`:

```sql
ORDER BY
    CASE WHEN score IS NULL THEN 1 ELSE 0 END ASC,
    score DESC
```

Nếu dùng biểu thức này **trong `RANK`**, nó trở thành một phần của khóa xác định nhóm đồng hạng. Nếu chỉ dùng để hiển thị, đặt ở `ORDER BY` ngoài cùng theo đúng mục đích.

## 16. Khác nhau giữa “đồng hạng” và “trùng dữ liệu”

Giả sử hai người có `score = 90`. Họ **đồng hạng** nếu luật chỉ xét điểm. Nhưng họ vẫn là **hai bản ghi khác nhau** vì `participant_id` khác.

Đừng nhầm với:

- `DISTINCT`: loại các dòng trùng nhau theo bộ cột được chọn.
- `GROUP BY`: gom nhiều dòng thành một dòng cho mỗi nhóm.
- `RANK`: **giữ nguyên mọi dòng**, chỉ gán cùng giá trị hạng cho các dòng đồng hạng.

Ví dụ:

```sql
SELECT DISTINCT region, score
FROM rank_lab_scores
ORDER BY region, score DESC;
```

Truy vấn này chỉ giữ **mỗi mức điểm một dòng trong mỗi khu vực**. Ở North có 4 mức điểm; các cá nhân đồng điểm bị gộp khỏi đầu ra.

Ngược lại:

```sql
SELECT
    participant_id,
    region,
    score,
    DENSE_RANK() OVER (
        PARTITION BY region ORDER BY score DESC
    ) AS dense_no
FROM rank_lab_scores
ORDER BY region, score DESC, participant_id;
```

vẫn trả **đủ 13 người**, mỗi người có giá trị hạng tương ứng.

### 16.1. Trường hợp `GROUP BY` làm thay đổi quy tắc hạng

```sql
WITH score_levels AS (
    SELECT
        region,
        score,
        COUNT(*) AS people_at_score
    FROM rank_lab_scores
    GROUP BY region, score
)
SELECT
    region,
    score,
    people_at_score,
    RANK() OVER (
        PARTITION BY region ORDER BY score DESC
    ) AS level_rank
FROM score_levels
ORDER BY region, score DESC;
```

Trong `score_levels`, **mỗi mức điểm chỉ còn một dòng**, nên `RANK()` tính trên kết quả này sẽ đánh các **mức điểm** liên tục 1, 2, 3, 4. Nó không còn là bảng hạng thi đấu của 13 người. Việc tổng hợp trước đã **thay đổi độ hạt** đầu vào của hàm cửa sổ.

Đó là lý do cần xác định một dòng đầu vào của `RANK()` đại diện cho **một người**, **một đơn hàng** hay **một nhóm tổng hợp** trước khi diễn giải số hạng.

## 17. Chọn bản ghi đại diện mới nhất với `ROW_NUMBER()`

Ba hàm không chỉ dành cho cuộc thi. Trong hệ thống nghiệp vụ, một thực thể có thể có nhiều bản ghi lịch sử và ta cần lấy **một bản ghi mới nhất cho mỗi thực thể**.

Giả sử bảng:

```text
customer_status_history(
    history_id      -- khóa chính, duy nhất
    customer_id
    status
    changed_at      -- thời điểm thay đổi
)
```

Muốn chọn **một trạng thái mới nhất của mỗi khách**:

```sql
WITH latest_status AS (
    SELECT
        history_id,
        customer_id,
        status,
        changed_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY changed_at DESC, history_id DESC
        ) AS rn
    FROM customer_status_history
)
SELECT customer_id, status, changed_at, history_id
FROM latest_status
WHERE rn = 1
ORDER BY customer_id;
```

- `PARTITION BY customer_id`: xét mỗi khách riêng.
- `changed_at DESC`: bản ghi mới nhất đứng trước.
- `history_id DESC`: nếu hai bản ghi cùng timestamp, ID lớn hơn được chọn theo quy tắc của ví dụ.
- `WHERE rn = 1`: chỉ giữ **một bản ghi** của mỗi khách.

### 17.1. Nếu dùng `RANK() = 1` thì có thể có nhiều dòng mỗi khách

```sql
RANK() OVER (
    PARTITION BY customer_id
    ORDER BY changed_at DESC
)
```

Khi hai lịch sử của một khách có cùng `changed_at` mới nhất, cả hai nhận hạng 1; `WHERE rank_no = 1` trả **hai dòng** cho khách đó. Đó là lựa chọn đúng nếu nghiệp vụ muốn **giữ mọi bản ghi đồng thời điểm mới nhất**, nhưng sai nếu API đòi **đúng một bản ghi**.

### 17.2. ID là khóa phân xử, không nhất thiết là thời điểm nghiệp vụ

Một `history_id` lớn hơn không mặc nhiên chứng minh sự kiện xảy ra muộn hơn nếu dữ liệu nhập lại hoặc ID được cấp theo cơ chế khác. Quy tắc `changed_at DESC, history_id DESC` chỉ cho một **lựa chọn xác định khi thời điểm bằng nhau**. Nếu sản phẩm cần phân xử theo thứ tự nguồn sự kiện, phải lưu và sử dụng khóa thứ tự nghiệp vụ phù hợp.

## 18. Xếp hạng theo tổng hợp: ví dụ doanh thu nhân viên

Một yêu cầu rất phổ biến: “Xếp hạng nhân viên bán hàng theo **tổng doanh thu đã thanh toán** trong từng vùng.”

Giả sử có bảng:

```text
sales_orders(
    order_id,
    salesperson_id,
    region,
    total_amount,
    status
)
```

Vì mỗi nhân viên có nhiều đơn, phải **tổng hợp đúng một dòng trên mỗi nhân viên–vùng trước khi xếp hạng**:

```sql
WITH salesperson_totals AS (
    SELECT
        region,
        salesperson_id,
        SUM(total_amount) AS paid_revenue
    FROM sales_orders
    WHERE status = 'PAID'
    GROUP BY region, salesperson_id
),
ranked_salespeople AS (
    SELECT
        region,
        salesperson_id,
        paid_revenue,
        RANK() OVER (
            PARTITION BY region
            ORDER BY paid_revenue DESC
        ) AS revenue_rank,
        DENSE_RANK() OVER (
            PARTITION BY region
            ORDER BY paid_revenue DESC
        ) AS revenue_dense_rank
    FROM salesperson_totals
)
SELECT *
FROM ranked_salespeople
ORDER BY region, paid_revenue DESC, salesperson_id ASC;
```

`RANK` bây giờ xếp **nhân viên theo doanh thu**, không xếp từng **đơn hàng**. Nếu có hai nhân viên cùng tổng doanh thu, họ đồng hạng nếu luật chỉ xét tổng tiền.

### 18.1. Sai lầm khi xếp hạng đơn rồi tưởng là hạng nhân viên

```sql
-- Sai độ hạt nếu đề bài muốn hạng theo doanh thu tổng của mỗi nhân viên:
SELECT
    salesperson_id,
    total_amount,
    RANK() OVER (ORDER BY total_amount DESC) AS rank_no
FROM sales_orders;
```

Truy vấn trên xếp **từng dòng đơn** theo giá trị đơn, không phải nhân viên theo tổng doanh thu. Câu SQL hợp lệ nhưng trả lời **một câu hỏi khác**.

### 18.2. Nếu cần xếp các nhân viên theo nhiều chỉ tiêu

Quy tắc có thể là:

1. Tổng doanh thu giảm dần.
2. Khi doanh thu bằng nhau, số đơn tăng dần hoặc giảm dần theo luật.
3. Khi hai chỉ tiêu bằng nhau, hai nhân viên vẫn đồng hạng.

Khi đó, đưa **các chỉ tiêu thực sự thuộc luật** vào `RANK() OVER (ORDER BY ...)`. Chỉ thêm `salesperson_id` vào `ORDER BY` ngoài cùng để hiển thị ổn định nếu vẫn muốn giữ đồng hạng theo các chỉ tiêu nghiệp vụ.

## 19. Đồng hạng khi xếp theo chuỗi, ngày giờ hoặc số thực

### 19.1. Điểm số có phần thập phân

Với cột `NUMERIC(8,2)`, hai điểm `90.00` và `90.00` là bằng nhau. Nhưng nếu nguồn đo là `DOUBLE PRECISION`, hai giá trị hiển thị đều “90.00” vẫn có thể khác nhau ở các chữ số ẩn. `RANK` chỉ xem đồng hạng khi **giá trị biểu thức sắp xếp thực sự bằng nhau** theo cách so sánh của database.

Nếu luật chấm điểm quy định làm tròn đến hai chữ số trước khi xếp, có thể chọn biểu thức phù hợp:

```sql
RANK() OVER (
    PARTITION BY region
    ORDER BY ROUND(score, 2) DESC
)
```

Trong PostgreSQL, ví dụ này phù hợp với kiểu `NUMERIC`. Với kiểu dấu phẩy động, khả năng và chữ ký `ROUND` có thể cần ép kiểu có chủ đích. **Làm tròn là thay đổi định nghĩa đồng điểm**: chỉ áp dụng khi quy tắc chấm yêu cầu, không phải để che dữ liệu sai số tùy ý.

### 19.2. Xếp hạng theo thời gian

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY created_at DESC, event_id DESC
)
```

Ở đây hai sự kiện có cùng `created_at` vẫn cần khóa phân xử nếu muốn một bản ghi đại diện xác định. Timestamp dù có microsecond cũng **không tự được đảm bảo duy nhất**.

Nếu yêu cầu công nhận **mọi sự kiện cùng thời điểm là đồng hạng**, dùng `RANK() OVER (ORDER BY created_at DESC)` rồi sắp ID ở bên ngoài để hiển thị.

### 19.3. Xếp hạng theo chuỗi và collation

```sql
RANK() OVER (
    PARTITION BY department
    ORDER BY full_name ASC
)
```

Thứ tự văn bản có thể chịu ảnh hưởng của **collation**: chữ hoa/thường, dấu tiếng Việt và quy tắc so sánh ngôn ngữ. Nếu tên hoặc mã được sắp theo các quy tắc khác nhau giữa môi trường, kết quả đồng hạng hoặc vị trí trình bày có thể khác. Nên dùng cột khóa nghiệp vụ, collation và chính sách chuẩn hóa rõ ràng khi độ chính xác giữa hệ thống là quan trọng.

## 20. Ranh giới nhóm đồng hạng và số dòng đầu ra

Tính chất tổng quát của ba hàm có thể nhìn qua nhóm đồng hạng kích thước khác nhau.

Giả sử trong một phân vùng có bốn mức điểm:

```text
Mức 1: 1 người
Mức 2: 2 người
Mức 3: 3 người
Mức 4: 1 người
```

Các hạng `RANK` của từng mức:

```text
Mức 1: RANK = 1
Mức 2: RANK = 1 + 1 = 2
Mức 3: RANK = 1 + 1 + 2 = 4
Mức 4: RANK = 1 + 1 + 2 + 3 = 7
```

Còn `DENSE_RANK` luôn là 1, 2, 3, 4 cho bốn mức.

### 20.1. `RANK <= N` có thể không có hạng đúng bằng N

Ở North, có hạng `1`, `2`, `4`, `7` nhưng **không có hạng `3`, `5`, `6`**. Điều kiện:

```sql
WHERE rank_no <= 3
```

vẫn hoàn toàn hợp lệ dù không ai có hạng 3. Nó lấy các **vị trí thi đấu đầu** đang tồn tại.

### 20.2. `DENSE_RANK <= N` không giới hạn số người

Nếu một mức điểm có hàng nghìn người, `DENSE_RANK <= 3` có thể trả hàng nghìn dòng. Không dùng nó để bảo đảm tối đa N bản ghi trong API hoặc giao diện.

### 20.3. `ROW_NUMBER <= N` cần quy tắc chọn người khi đồng điểm

Với giới hạn cứng N dòng, nếu dòng N và N+1 bằng điểm, một người sẽ được chọn, người còn lại bị loại. Khi có giá trị pháp lý hoặc giải thưởng, điều đó có thể không công bằng nếu luật không có tiêu chí phân xử. **Cần xác định quy tắc chọn trước**, thay vì để database chọn tùy kế hoạch.

## 21. Phân trang và thứ tự xác định

Các hàm cửa sổ có thể đánh số thứ tự để tạo trang:

```sql
WITH numbered AS (
    SELECT
        participant_id,
        region,
        score,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY score DESC, participant_id ASC
        ) AS row_no
    FROM rank_lab_scores
)
SELECT participant_id, region, score, row_no
FROM numbered
WHERE region = 'North'
  AND row_no BETWEEN 4 AND 6
ORDER BY row_no;
```

Kết quả là Dũng (4), Hà (5), Hòa (6), tức **dòng 4 đến dòng 6 trong bảng xếp theo North**.

Tuy vậy, `ROW_NUMBER` không tự bảo đảm người dùng sẽ không gặp dòng lặp hoặc bỏ sót khi tải nhiều trang **ở những thời điểm khác nhau** nếu dữ liệu có thêm người hoặc điểm bị thay đổi giữa hai lần truy vấn.

- Bộ `ORDER BY` có **khóa phân xử duy nhất** giúp thứ tự **xác định trên một trạng thái dữ liệu**.
- Dữ liệu thay đổi có thể khiến số thứ tự của người cũ thay đổi khi chạy lại.
- Nếu cần duyệt bảng lớn biến động liên tục, có thể cần chiến lược **keyset pagination**, snapshot hoặc ràng buộc phiên bản dữ liệu phù hợp.

Không nên coi `ROW_NUMBER` là một con trỏ lâu dài độc lập với dữ liệu.

## 22. Hiệu năng và cách đọc kế hoạch

Các hàm `ROW_NUMBER`, `RANK`, `DENSE_RANK` thường đòi hỏi dữ liệu được xử lý theo các khóa phân vùng và khóa sắp xếp. Với dữ liệu lớn, chi phí có thể đáng kể.

### 22.1. Sắp xếp theo khóa phù hợp

Ví dụ:

```sql
SELECT
    participant_id,
    region,
    score,
    ROW_NUMBER() OVER (
        PARTITION BY region
        ORDER BY score DESC, participant_id ASC
    ) AS rn
FROM rank_lab_scores;
```

Trên một bảng lớn thường xuyên truy vấn theo mô hình này, có thể xem xét chỉ mục:

```sql
CREATE INDEX idx_rank_lab_region_score_id
ON rank_lab_scores (region, score DESC, participant_id ASC);
```

Chỉ mục có thể giúp bộ tối ưu khi điều kiện lọc và thứ tự phù hợp, nhưng **không bảo đảm** mọi truy vấn window đều không cần sắp xếp hoặc luôn dùng chỉ mục. Đánh giá theo kích thước bảng, thống kê, mức chọn lọc và kế hoạch thực thi.

### 22.2. Nhiều cửa sổ có khóa khác nhau

Trong ví dụ đầy đủ, `ROW_NUMBER()` sử dụng `(score DESC, participant_id ASC)` còn `RANK()` dùng `(score DESC)`. Bộ tối ưu có thể cần xử lý các khóa sắp xếp khác nhau; cách thực thi tùy phiên bản PostgreSQL và kế hoạch thực tế.

Không nên đổi `RANK() OVER (ORDER BY score DESC)` thành `RANK() OVER (ORDER BY score DESC, participant_id ASC)` chỉ với mong muốn dùng chung sort nếu thao tác đó **phá đồng hạng nghiệp vụ**. Đúng ngữ nghĩa trước, tối ưu sau.

### 22.3. Xem `EXPLAIN`

```sql
EXPLAIN
SELECT
    participant_id,
    RANK() OVER (
        PARTITION BY region
        ORDER BY score DESC
    ) AS rank_no
FROM rank_lab_scores;
```

Trong PostgreSQL, kế hoạch có thể có các bước như `Sort`, `WindowAgg`, quét chỉ mục hoặc quét bảng tùy dữ liệu. Không nên suy luận “window function luôn chạy vòng lặp từng người” chỉ từ hình dung thuật toán; SQL mô tả phép tính, còn bộ tối ưu quyết định chiến lược.

### 22.4. Lọc đầu vào khi đúng nghiệp vụ

Nếu chỉ xếp hạng người dự thi hợp lệ, có thể lọc `WHERE is_eligible = TRUE` (nếu schema thật có cột này) trước khi window tính hạng. Nhưng như mục 12 đã chỉ ra, **lọc trước và lọc sau khi tính hạng có thể thay đổi số hạng**. Không dùng mẹo “lọc càng sớm càng tốt” nếu làm sai ý nghĩa báo cáo.

## 23. Những khác biệt khi chuyển sang hệ quản trị khác

`ROW_NUMBER()`, `RANK()`, `DENSE_RANK()` là các hàm cửa sổ phổ biến trong SQL hiện đại và được PostgreSQL, SQL Server, MySQL 8+, Oracle và nhiều hệ khác hỗ trợ. Dù vậy, cần chú ý:

| Vấn đề | Lưu ý khi chuyển hệ |
|---|---|
| `OVER (PARTITION BY ... ORDER BY ...)` | Phần cốt lõi dùng rộng rãi; tên kiểu và cú pháp phụ có thể khác |
| `NULLS FIRST` / `NULLS LAST` | Không phải hệ nào cũng hỗ trợ cú pháp như PostgreSQL |
| `FETCH ... WITH TIES` | Khả năng hỗ trợ và cú pháp top-N kèm đồng hạng khác nhau |
| `QUALIFY` | Có ở một số hệ; PostgreSQL thường dùng CTE/truy vấn con |
| `ORDER BY` có collation | Thứ tự văn bản và nhóm bằng nhau có thể khác |
| Chỉ mục và bộ tối ưu | Cùng câu SQL có thể có kế hoạch khác trên từng hệ |
| Kiểu số và làm tròn | So sánh điểm cần kiểu dữ liệu/độ chính xác phù hợp |

Ví dụ trong SQL Server, thường thấy `TOP (n) WITH TIES`; trong PostgreSQL có thể dùng `FETCH FIRST n ROWS WITH TIES`. Nhưng khi cần top-N **theo từng `region`**, giải pháp `ROW_NUMBER`/`RANK` cùng `PARTITION BY` vẫn là hướng tư duy chung.

**Không nên suy diễn phiên bản:** hệ quản trị đời cũ có thể chưa hỗ trợ đủ các chức năng cửa sổ. Khi triển khai, kiểm tra tính năng được tài liệu của phiên bản đang vận hành xác nhận.

## 24. Các lỗi thường gặp và cách sửa

| Hiểu nhầm hoặc truy vấn | Vì sao sai hoặc chưa đủ? | Hướng sửa |
|---|---|---|
| Dùng `ROW_NUMBER` để công nhận người đồng điểm là đồng hạng | `ROW_NUMBER` luôn gán số khác nhau cho từng dòng | Dùng `RANK` hoặc `DENSE_RANK` theo luật |
| Nghĩ `RANK` luôn tạo dãy 1,2,3 không gián đoạn | `RANK` bỏ số hạng khi có đồng hạng | Dùng `DENSE_RANK` nếu muốn mức hạng liên tục |
| Nghĩ `DENSE_RANK <= 3` trả nhiều nhất 3 dòng | Mỗi mức có thể có nhiều người | Dùng `ROW_NUMBER <= 3` nếu giới hạn cứng số dòng |
| Nghĩ `RANK <= 3` chắc có người hạng 3 | Đồng hạng có thể làm mất số hạng | Hiểu hạng thi đấu kiểu có khoảng trống |
| `ROW_NUMBER OVER (ORDER BY score DESC)` không có khóa phân xử | Thứ tự giữa người cùng điểm chưa xác định | Thêm ID duy nhất hoặc quy tắc nghiệp vụ trong `ROW_NUMBER` |
| Thêm ID vào `RANK OVER` chỉ để hiển thị ổn định | ID duy nhất phá đồng hạng theo điểm | Giữ `RANK` theo điểm; dùng ID ở `ORDER BY` ngoài |
| Không viết `PARTITION BY region` khi cần hạng mỗi khu vực | Tính hạng toàn bộ thay vì từng vùng | Thêm `PARTITION BY region` |
| Nghĩ `PARTITION BY` làm dữ liệu gộp như `GROUP BY` | Window vẫn giữ từng dòng | Dùng `GROUP BY` nếu muốn một dòng trên mỗi nhóm |
| Viết `WHERE RANK() OVER (...) <= 3` | Hàm cửa sổ không dùng trực tiếp trong `WHERE` cùng cấp PostgreSQL | Tính trong CTE hoặc subquery rồi lọc |
| Lọc người trước window khi muốn giữ hạng gốc | Thay đổi tập xếp hạng nên hạng có thể đổi | Tính hạng trước, lọc hiển thị sau |
| Quên `NULLS LAST` khi `ORDER BY score DESC` | PostgreSQL có thể đặt điểm `NULL` trước điểm thật | Xác định chính sách điểm thiếu và ghi rõ |
| Dùng `FETCH ... WITH TIES` cùng ID duy nhất trong `ORDER BY` | Không còn cùng khóa ở ranh giới, nên không mở rộng nhóm điểm | Xếp theo điểm khi cần tie theo điểm, hoặc dùng `RANK` |
| Xếp hạng từng đơn khi muốn hạng nhân viên | Sai độ hạt đầu vào | Tổng hợp theo nhân viên rồi xếp hạng |
| Số thứ tự thay đổi giữa các lần tải trang | Dữ liệu hoặc điểm xếp hạng thay đổi | Xác định snapshot/phân trang theo nhu cầu |
| Dùng điểm thực `FLOAT` rồi coi hai số hiển thị bằng là đồng hạng | Giá trị gốc có thể khác ở phần thập phân ẩn | Định nghĩa độ chính xác, kiểu hoặc làm tròn có chủ đích |
| Tin `ORDER BY` trong `OVER` quyết định thứ tự in ra | Hai cấp `ORDER BY` có vai trò khác nhau | Viết `ORDER BY` ngoài cùng |

## 25. Bài tập thực hành

Hãy sử dụng bảng `rank_lab_scores` ở mục 2. Trước khi chạy, thử **dự đoán bảng hạng bằng tay**: mỗi lần gặp một mức điểm mới, xem `ROW_NUMBER`, `RANK` và `DENSE_RANK` phải tăng như thế nào.

### Bài 1 — Tính ba loại thứ tự trong North

Viết một truy vấn hiển thị `participant_id`, `full_name`, `score`, `ROW_NUMBER`, `RANK` và `DENSE_RANK` cho khu vực North. Đảm bảo `ROW_NUMBER` có thứ tự xác định khi đồng điểm nhưng `RANK` và `DENSE_RANK` vẫn coi những người cùng điểm là đồng hạng.

### Bài 2 — Đọc bảng hạng của South

Với South có điểm `95,95,85,70,70,60`, hãy viết ba dãy số thứ tự tương ứng với ba hàm. Giải thích vì sao người 85 điểm có `RANK=3` và `DENSE_RANK=2`.

### Bài 3 — Top 2 người

Chọn đúng **hai người cao điểm nhất mỗi vùng**; khi đồng điểm, `participant_id` nhỏ hơn được ưu tiên. Dùng `ROW_NUMBER`. Dự đoán ID được chọn.

### Bài 4 — Top 2 hạng thi đấu

Lấy tất cả người có `RANK <= 2` trong từng khu vực. Có bao nhiêu người ở North và South? Vì sao số người có thể khác nhau?

### Bài 5 — Top 3 mức điểm

Lấy người thuộc ba mức điểm cao nhất mỗi khu vực bằng `DENSE_RANK`. Dự đoán ID của North và South.

### Bài 6 — Hạng 1 có thể nhiều hơn một người

Viết truy vấn lấy **mọi người đồng hạng nhất theo điểm** của từng khu vực. So sánh với `ROW_NUMBER() = 1`. South trả bao nhiêu dòng trong mỗi trường hợp?

### Bài 7 — Không phá đồng hạng khi hiển thị

Trình bày hạng thi đấu của North theo điểm giảm dần. Khi đồng điểm, hiển thị người đạt điểm sớm hơn trước, nếu vẫn bằng thì ID tăng dần. **Vẫn phải giữ đồng hạng theo điểm**. Viết `ORDER BY` của cửa sổ và `ORDER BY` ngoài cùng khác nhau đúng mục đích.

### Bài 8 — Thời gian có phải tiêu chí chính thức?

Nếu luật mới công bố “cùng điểm thì ai đạt điểm sớm hơn có hạng cao hơn”, hãy viết `RANK` với cả `score` và `achieved_at`. Ở North, Bình và Chi còn đồng hạng không? Dũng và Hà còn đồng hạng không?

### Bài 9 — Lọc trước hay sau?

Viết hai truy vấn:

1. Lọc những người `score < 95`, **sau đó** xếp hạng theo từng vùng.
2. Xếp hạng mọi người, **sau đó** chỉ hiển thị những người `score < 95`.

So sánh hạng của Bình và Oanh trong hai kết quả.

### Bài 10 — Bản ghi mới nhất trên mỗi khóa

Giả sử bảng `customer_status_history(history_id, customer_id, status, changed_at)` có nhiều bản ghi mỗi khách. Viết truy vấn lấy **đúng một bản ghi mới nhất mỗi khách**, kể cả khi nhiều bản ghi có cùng `changed_at`.

### Bài 11 — Điểm chưa xác định

Giả sử một bảng có các dòng `(id, score) = (1,100), (2,NULL), (3,NULL), (4,80)`. Với `ORDER BY score DESC NULLS LAST`, hai dòng `NULL` nhận hạng `RANK` nào? Muốn loại hoàn toàn người chưa có điểm, đặt điều kiện ở đâu?

### Bài 12 — `FETCH FIRST ... WITH TIES`

Ở North, so sánh:

```sql
ORDER BY score DESC FETCH FIRST 3 ROWS WITH TIES
```

và điều kiện `DENSE_RANK <= 3`. Chúng trả bao nhiêu người? Nếu thêm `participant_id ASC` vào `ORDER BY` của `WITH TIES`, điều gì xảy ra với khái niệm “đồng hạng”?

### Bài 13 — Sai độ hạt

Muốn xếp hạng nhân viên theo tổng doanh thu nhưng bảng nguồn có nhiều đơn trên một nhân viên. Vì sao dùng `RANK() OVER (ORDER BY total_amount DESC)` trực tiếp trên bảng đơn là sai? Hãy mô tả CTE cần dùng trước khi xếp.

### Bài 14 — Hạng toàn cuộc thi so với từng khu vực

Viết hai truy vấn xếp hạng:

- Theo **toàn bộ** người dự thi.
- Riêng **từng khu vực**.

Trong hai cách, An và Mai có nhận cùng hạng 1 không? Vì sao?

### Bài 15 — Nhóm đồng điểm và khóa hiển thị

Hai sản phẩm có cùng số lượng bán ra. Yêu cầu báo cáo là “**đồng hạng theo số lượng**, nhưng mã sản phẩm nhỏ hơn hiển thị trước”. Hãy chỉ ra phần nào của SQL nên có `product_id ASC` và phần nào **không nên** có nếu mục tiêu là giữ đồng hạng.

<details>
<summary>Gợi ý đáp án</summary>

**Bài 1:** Dùng khóa duy nhất ở `ROW_NUMBER`, nhưng không đưa nó vào hai hàm xét đồng hạng:

```sql
SELECT participant_id, full_name, score,
       ROW_NUMBER() OVER (
           ORDER BY score DESC, participant_id ASC
       ) AS row_no,
       RANK() OVER (ORDER BY score DESC) AS rank_no,
       DENSE_RANK() OVER (ORDER BY score DESC) AS dense_no
FROM rank_lab_scores
WHERE region = 'North'
ORDER BY score DESC, participant_id ASC;
```

Ba dãy số: `1,2,3,4,5,6,7`; `1,2,2,4,4,4,7`; `1,2,2,3,3,3,4`.

**Bài 2:** South có:

```text
ROW_NUMBER: 1,2,3,4,5,6
RANK:       1,1,3,4,4,6
DENSE_RANK: 1,1,2,3,3,4
```

Hai người 95 điểm chiếm vị trí 1 và 2; người 85 điểm đứng ở vị trí thi đấu 3, nhưng chỉ là **mức điểm thứ hai**.

**Bài 3:**

```sql
WITH x AS (
    SELECT participant_id, region, score,
           ROW_NUMBER() OVER (
               PARTITION BY region
               ORDER BY score DESC, participant_id ASC
           ) AS rn
    FROM rank_lab_scores
)
SELECT *
FROM x
WHERE rn <= 2
ORDER BY region, rn;
```

North: **101, 102**. South: **201, 202**.

**Bài 4:**

```sql
WITH x AS (
    SELECT participant_id, region, score,
           RANK() OVER (
               PARTITION BY region ORDER BY score DESC
           ) AS rk
    FROM rank_lab_scores
)
SELECT *
FROM x
WHERE rk <= 2
ORDER BY region, score DESC, participant_id;
```

North: 3 người **101, 102, 103**. South: 2 người **201, 202**.

**Bài 5:**

```sql
WITH x AS (
    SELECT participant_id, region, score,
           DENSE_RANK() OVER (
               PARTITION BY region ORDER BY score DESC
           ) AS dr
    FROM rank_lab_scores
)
SELECT *
FROM x
WHERE dr <= 3
ORDER BY region, score DESC, participant_id;
```

North: **101,102,103,104,105,106**. South: **201,202,203,204,205**.

**Bài 6:** Cả hai hàm được tính theo vùng:

```sql
WITH x AS (
    SELECT participant_id, region, score,
           RANK() OVER (
               PARTITION BY region ORDER BY score DESC
           ) AS rk,
           ROW_NUMBER() OVER (
               PARTITION BY region
               ORDER BY score DESC, participant_id ASC
           ) AS rn
    FROM rank_lab_scores
)
SELECT * FROM x WHERE rk = 1 ORDER BY region, participant_id;
```

`RANK=1` trả **An** ở North và **Mai, Nam** ở South (hai người). Nếu thay `WHERE rk=1` thành `WHERE rn=1`, mỗi vùng chỉ còn một người; ở South là Mai do ID 201 nhỏ hơn 202.

**Bài 7:** Hạng thi đấu giữ `ORDER BY score DESC` trong `OVER`; khóa `achieved_at, participant_id` chỉ để trình bày:

```sql
SELECT
    participant_id, full_name, score, achieved_at,
    RANK() OVER (ORDER BY score DESC) AS official_rank
FROM rank_lab_scores
WHERE region = 'North'
ORDER BY score DESC, achieved_at ASC, participant_id ASC;
```

Bình và Chi vẫn cùng **hạng 2**, dù Chi được hiển thị trước Bình vì đạt điểm sớm hơn.

**Bài 8:**

```sql
RANK() OVER (
    PARTITION BY region
    ORDER BY score DESC, achieved_at ASC
)
```

Chi đạt 90 sớm hơn Bình nên **không đồng hạng** theo luật mới; Dũng và Hà cùng 80 tại đúng thời điểm 08:00 ngày 3/6, nên **vẫn đồng hạng**.

**Bài 9:** Nếu lọc trước:

```sql
SELECT participant_id, region, score,
       RANK() OVER (
           PARTITION BY region ORDER BY score DESC
       ) AS rk
FROM rank_lab_scores
WHERE score < 95;
```

Bình **hạng 1** North, Oanh **hạng 1** South. Nếu tính hạng trong CTE trên toàn bảng rồi dùng `WHERE score < 95` ở ngoài, Bình vẫn **hạng 2** North và Oanh vẫn **hạng 3** South.

**Bài 10:**

```sql
WITH x AS (
    SELECT history_id, customer_id, status, changed_at,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY changed_at DESC, history_id DESC
           ) AS rn
    FROM customer_status_history
)
SELECT customer_id, status, changed_at, history_id
FROM x
WHERE rn = 1
ORDER BY customer_id;
```

`history_id` là khóa phân xử trong trường hợp hai bản ghi có cùng thời điểm.

**Bài 11:** Theo `score DESC NULLS LAST`, hai dòng `NULL` cùng **`RANK=3`** vì có hai người có điểm thật đứng trước. `ROW_NUMBER` vẫn cho chúng hai số riêng. Nếu muốn chỉ xếp những người có điểm, thêm `WHERE score IS NOT NULL` **trước khi tính hàm cửa sổ**.

**Bài 12:** `FETCH FIRST 3 ROWS WITH TIES` trả **3 người** North (100,90,90). `DENSE_RANK<=3` trả **6 người** (mức 100,90,80). Nếu đưa ID duy nhất vào `ORDER BY` của `WITH TIES`, những người đồng điểm không còn trùng toàn bộ khóa và không được tự động lấy thêm tại ranh giới.

**Bài 13:** Bảng đơn có độ hạt **một đơn**, còn yêu cầu có độ hạt **một nhân viên**. Cần `GROUP BY salesperson_id` (và vùng/kỳ nếu nghiệp vụ yêu cầu) để tính `SUM(total_amount)` cho từng người, rồi dùng `RANK() OVER (ORDER BY paid_revenue DESC)` trên kết quả tổng hợp.

**Bài 14:** Hạng toàn cuộc thi:

```sql
SELECT participant_id, region, score,
       RANK() OVER (ORDER BY score DESC) AS global_rank
FROM rank_lab_scores;
```

Hạng từng vùng:

```sql
SELECT participant_id, region, score,
       RANK() OVER (
           PARTITION BY region ORDER BY score DESC
       ) AS region_rank
FROM rank_lab_scores;
```

An 100 điểm là **hạng 1 toàn cuộc thi**, Mai 95 điểm là **hạng 2 toàn cuộc thi** (đồng hạng với Nam). Nhưng khi phân theo vùng, An và Mai đều là **hạng 1 của vùng mình**.

**Bài 15:** Số lượng bán ra là khóa xác định đồng hạng:

```sql
RANK() OVER (ORDER BY quantity_sold DESC)
```

Thứ tự hiển thị có thể dùng:

```sql
ORDER BY quantity_sold DESC, product_id ASC
```

Không thêm `product_id` duy nhất vào `ORDER BY` bên trong `RANK` nếu hai sản phẩm có cùng số lượng bán phải tiếp tục đồng hạng.

</details>

## 26. Những câu hỏi tự kiểm tra trước khi viết SQL

Trước mỗi bảng xếp hạng hoặc truy vấn chọn dòng đại diện, tự hỏi:

1. **Một dòng đầu vào là gì?** Một người, một sản phẩm, một đơn hay một nhóm đã tổng hợp?
2. **Phạm vi xếp hạng là gì?** Toàn bảng hay từng nhóm xác định bởi `PARTITION BY`?
3. **Thành tích chính thức được so trên những cột nào?** Chỉ điểm, hay điểm kèm thời điểm và tiêu chí phụ?
4. **Có công nhận đồng hạng không?** Nếu có, cần bỏ qua số hạng (`DENSE_RANK`) hay giữ hạng thi đấu có khoảng trống (`RANK`)?
5. **Có giới hạn cứng số dòng không?** Nếu cần đúng/tối đa N dòng, dùng `ROW_NUMBER` với quy tắc phân xử xác định.
6. **Khóa sắp xếp có phân biệt mọi dòng không?** Nếu `ROW_NUMBER` cần thứ tự ổn định, thêm khóa duy nhất ở phần `ORDER BY` của cửa sổ.
7. **Khóa phân xử có làm mất đồng hạng nghiệp vụ không?** Không thêm ID vào `RANK` nếu chỉ muốn ổn định thứ tự hiển thị.
8. **Lọc trước hay sau khi tính hạng?** Hai cách có thể tạo thứ hạng khác nhau.
9. **Có điểm `NULL`, số thực, thời gian trùng hoặc collation khác nhau không?** Định nghĩa cách xử lý trước khi triển khai.
10. **Có `ORDER BY` ở truy vấn ngoài cùng không?** Hạng đã được tính không đồng nghĩa các dòng được in đúng thứ tự mong muốn.

Ba mẫu PostgreSQL cần nhớ:

```sql
-- A. Số thứ tự riêng từng dòng, dùng khóa phân xử duy nhất.
ROW_NUMBER() OVER (
    PARTITION BY region
    ORDER BY score DESC, participant_id ASC
)

-- B. Đồng hạng kiểu thi đấu, có khoảng trống sau nhóm đồng điểm.
RANK() OVER (
    PARTITION BY region
    ORDER BY score DESC
)

-- C. Đồng hạng theo các mức điểm liên tục, không có khoảng trống.
DENSE_RANK() OVER (
    PARTITION BY region
    ORDER BY score DESC
)
```

**Nguyên tắc cuối cùng:** `ROW_NUMBER()` trả lời “dòng này ở **vị trí số mấy** sau khi đã phân xử?”, `RANK()` trả lời “dòng này ở **hạng thi đấu nào**, tính cả số người đồng hạng phía trước?”, còn `DENSE_RANK()` trả lời “dòng này thuộc **mức hạng thứ mấy** trong các giá trị phân biệt?”. Khi xác định đúng ý nghĩa đồng hạng, phạm vi phân vùng và bộ khóa sắp xếp, bạn có thể thiết kế bảng điểm, báo cáo top-N và truy vấn lấy bản ghi đại diện một cách rõ ràng, công bằng theo luật đã công bố và có thể kiểm chứng.
