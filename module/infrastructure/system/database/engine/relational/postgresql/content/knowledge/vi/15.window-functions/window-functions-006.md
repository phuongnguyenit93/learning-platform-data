# ROWS, RANGE, GROUPS và ranh giới khung cửa sổ trong PostgreSQL

Hàm cửa sổ (*window functions*) cho phép tính tổng lũy kế, trung bình trượt, xếp hạng, tỷ lệ đóng góp và so sánh với những hàng lân cận mà **không làm mất từng hàng chi tiết** như `GROUP BY` thông thường. Tuy nhiên, khi viết `SUM(...) OVER (...)` hoặc `LAST_VALUE(...) OVER (...)`, kết quả không chỉ phụ thuộc vào cách chia `PARTITION BY` và sắp xếp `ORDER BY`. Một thành phần rất quan trọng khác là **khung cửa sổ — *window frame***.

Hãy tưởng tượng bạn có các sự kiện bán hàng:

```text
Ngày tương đối | Sự kiện | Doanh số
---------------+---------+---------
1              | A       | 10
2              | B       | 20
2              | C       | 30
4              | D       | 40
4              | E       |  5
8              | F       | 50
```

Nếu đang đứng ở sự kiện D (ngày 4), cụm “hai đơn vị gần nhất” có ít nhất ba cách hiểu:

- **Hai hàng gần nhất:** hàng C và D, cho tổng 30 + 40 = **70**, nếu quy định một thứ tự hàng xác định.
- **Những sự kiện trong hai ngày gần nhất:** có thể bao gồm ngày 2, 3, 4, tức các hàng B, C, D, E với tổng **95**, tùy khoảng giá trị được chỉ định.
- **Hai nhóm ngày gần nhất:** nhóm ngày 2 và nhóm ngày 4, cũng gồm B, C, D, E trong dữ liệu này, tổng **95**; nhưng khác với khoảng hai ngày khi khoảng cách giữa các ngày có lỗ hổng.

Trong PostgreSQL, ba mô hình đó được diễn đạt lần lượt bằng `ROWS`, `RANGE` và `GROUPS`. Sự khác nhau đặc biệt rõ khi `ORDER BY` có **nhiều hàng cùng giá trị** hoặc khi các mốc thời gian/số có **khoảng cách không đều**.

Bài học giải thích cú pháp frame, ranh giới `UNBOUNDED PRECEDING`, `CURRENT ROW`, `n PRECEDING`, `n FOLLOWING`, `UNBOUNDED FOLLOWING`, các tùy chọn `EXCLUDE`, khung mặc định, tác động tới `LAST_VALUE` và cách thiết kế truy vấn ổn định, có thể kiểm chứng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **partition**, **thứ tự hàng** và **frame** trong một lời gọi window function.
2. Hiểu khái niệm **peer group** — nhóm hàng đồng hạng theo các biểu thức `ORDER BY`.
3. Dùng `ROWS` cho khung dựa trên **số hàng**.
4. Dùng `RANGE` cho khung dựa trên **giá trị của khóa sắp xếp**, bao gồm offset số và `INTERVAL`.
5. Dùng `GROUPS` cho khung dựa trên **số nhóm đồng hạng**.
6. Viết khung bắt đầu/kết thúc bằng `UNBOUNDED PRECEDING`, `CURRENT ROW`, offset trước/sau, `UNBOUNDED FOLLOWING`.
7. Giải thích hành vi khi không viết frame: khung mặc định, peer và kết quả tổng lũy kế.
8. Sử dụng `EXCLUDE CURRENT ROW`, `EXCLUDE GROUP`, `EXCLUDE TIES` và `EXCLUDE NO OTHERS`.
9. Phân biệt hàm **nhạy cảm với frame** như `SUM`, `AVG`, `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` với những hàm chủ yếu theo partition và thứ tự như `ROW_NUMBER`, `RANK`, `LAG`, `LEAD`.
10. Xử lý khung rỗng, `NULL`, thứ tự không ổn định khi hòa điểm, giá trị ngày giờ và múi giờ.
11. Viết truy vấn lũy kế, trung bình trượt, cửa sổ hai phía và tổng theo các peer group.
12. Đọc `EXPLAIN` để nhận diện những bước sort/window và cân nhắc index đúng cách.

**Phạm vi:** Cú pháp và ví dụ dùng PostgreSQL hiện đại có hỗ trợ `GROUPS` và `EXCLUDE`; khi vận hành trên phiên bản cũ cần kiểm tra tính năng phiên bản đó. Các lệnh tạo/xóa dữ liệu trong bài chỉ chạy ở **database thực hành**.

---

## 2. Ôn nhanh: window function giữ nguyên từng hàng

Cú pháp tổng quát:

```sql
SELECT
    column_name,
    window_function(...) OVER (
        PARTITION BY partition_columns
        ORDER BY sort_columns
        frame_clause
    ) AS metric
FROM some_table;
```

Các bộ phận:

- **`PARTITION BY`**: chia các hàng đầu vào thành những tập độc lập. Ví dụ các hàng của mỗi tài khoản.
- **`ORDER BY` trong `OVER`**: xác định thứ tự logic **bên trong mỗi partition**.
- **Frame clause**: chọn một phần của partition, dựa vào hàng hiện tại, để hàm nhạy cảm với frame tính toán.
- **Hàm cửa sổ**: dùng frame hoặc partition/thứ tự để tạo kết quả **cho từng hàng**.

Ví dụ ý tưởng:

```sql
SELECT
    account_id,
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
    ) AS account_total
FROM events;
```

Từng sự kiện vẫn xuất hiện, nhưng cùng một `account_id` sẽ có thêm tổng của toàn bộ account.

Khác với:

```sql
SELECT account_id, SUM(amount)
FROM events
GROUP BY account_id;
```

vì `GROUP BY` gộp các hàng thành **một hàng mỗi account**, trong khi window function **không tự gộp** những hàng chi tiết.

### 2.1. Partition khác frame

Giả sử account A có sáu hàng và account B có bốn hàng.

`PARTITION BY account_id` tạo hai partition: A và B. Sau đó, đối với **mỗi hàng** trong A, một frame có thể chứa một hàng, ba hàng, các hàng cùng ngày hoặc toàn bộ A tùy khai báo.

Nói cách khác:

```text
Bảng sau WHERE/GROUP BY/HAVING
              |
       PARTITION BY
              |
    +---------+---------+
    |                   |
 Account A            Account B
    |                   |
 ORDER BY             ORDER BY
    |                   |
 Với mỗi hàng         Với mỗi hàng
 lấy FRAME            lấy FRAME
    |                   |
 Tính window          Tính window
 function             function
              |
       Trả hàng kết quả
```

Một frame **không vượt qua ranh giới partition**; offset trước/sau chỉ xét các hàng trong partition tương ứng.

### 2.2. ORDER BY trong OVER khác ORDER BY ở cuối SELECT

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        ORDER BY event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount
FROM some_table
ORDER BY amount DESC;
```

`ORDER BY event_id` bên trong `OVER` điều khiển thứ tự **tính tổng lũy kế**. `ORDER BY amount DESC` ở ngoài cùng chỉ sắp kết quả hiển thị. Một thứ tự không thay thế cho thứ tự còn lại.

Nếu cần kết quả hiển thị nhất quán, nên có `ORDER BY` ở cấp SELECT ngoài cùng, ngay cả khi đã có `ORDER BY` trong window.

---

## 3. Cú pháp đầy đủ của khung cửa sổ

Một khung cửa sổ có dạng:

```sql
OVER (
    PARTITION BY ...
    ORDER BY ...
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

Ba đơn vị khung chính:

```sql
ROWS
RANGE
GROUPS
```

Cú pháp tổng quát:

```sql
{ ROWS | RANGE | GROUPS }
BETWEEN frame_start AND frame_end
[ frame_exclusion ]
```

Hoặc dạng rút gọn:

```sql
{ ROWS | RANGE | GROUPS } frame_start
[ frame_exclusion ]
```

Ví dụ:

```sql
ROWS UNBOUNDED PRECEDING
```

tương đương với:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Khi không khai báo `frame_end` trong cách viết ngắn thông thường, điểm kết thúc mặc định là `CURRENT ROW`.

### 3.1. Những kiểu ranh giới thường gặp

| Ranh giới | Ý nghĩa định hướng |
| --- | --- |
| `UNBOUNDED PRECEDING` | Bắt đầu từ đầu partition |
| `n PRECEDING` | Lùi về trước n hàng / nhóm / đơn vị giá trị tùy loại frame |
| `CURRENT ROW` | Hàng hiện tại hoặc nhóm peer hiện tại tùy loại frame |
| `n FOLLOWING` | Tiến về sau n hàng / nhóm / đơn vị giá trị |
| `UNBOUNDED FOLLOWING` | Kết thúc tại cuối partition |

Trong cú pháp với `BETWEEN`, PostgreSQL yêu cầu ranh giới đầu và cuối theo trật tự hợp lệ. Chẳng hạn không được đặt `UNBOUNDED FOLLOWING` làm điểm bắt đầu, hay `UNBOUNDED PRECEDING` làm điểm kết thúc.

### 3.2. Những mẫu quan trọng

| Frame | Ý tưởng |
| --- | --- |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Lũy kế từng hàng từ đầu partition |
| `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | Tối đa ba hàng: hai trước và hàng hiện tại |
| `ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING` | Hàng trước, hiện tại và hàng sau |
| `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | Từ hàng hiện tại đến cuối partition |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Toàn bộ partition |
| `RANGE BETWEEN 5 PRECEDING AND CURRENT ROW` | Khóa sắp xếp trong phạm vi giá trị được xác định |
| `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` | Nhóm peer trước và nhóm peer hiện tại |

**Không được đọc “2 PRECEDING” như nhau trong cả ba loại frame.** Chính từ khóa `ROWS`, `RANGE` hay `GROUPS` quyết định “2” đếm thứ gì.

---

## 4. Bộ dữ liệu thực hành có peer và khoảng trống

Để thấy sự khác nhau, chúng ta cố ý tạo **nhiều sự kiện cùng mốc ngày** và **những ngày không có sự kiện**.

> Các câu `DROP TABLE IF EXISTS` ở dưới xóa bảng thực hành cùng tên. Chỉ chạy trong database test riêng, không dùng để reset dữ liệu production.

### 4.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS window_frame_lab;

DROP TABLE IF EXISTS window_frame_lab.events;

CREATE TABLE window_frame_lab.events (
    event_id INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    day_no INTEGER NOT NULL CHECK (day_no > 0),
    event_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    note TEXT NOT NULL
);
```

Ở đây:

- `event_id` là khóa duy nhất để tạo tie-breaker cho thứ tự theo **từng hàng**.
- `day_no` là khóa số có **giá trị trùng nhau**, phù hợp cho ví dụ `RANGE` với offset số.
- `event_at` giúp minh họa khoảng thời gian theo `INTERVAL`.
- `account_id` giúp quan sát `PARTITION BY`.
- `amount` là đại lượng được tổng hợp.

### 4.2. Nạp dữ liệu

```sql
INSERT INTO window_frame_lab.events (
    event_id, account_id, day_no, event_at, amount, note
)
VALUES
    (101, 'A', 1, '2026-01-01 09:00:00+00', 10.00, 'A ngày 1'),
    (102, 'A', 2, '2026-01-02 09:00:00+00', 20.00, 'A ngày 2 / 1'),
    (103, 'A', 2, '2026-01-02 09:00:00+00', 30.00, 'A ngày 2 / 2'),
    (104, 'A', 4, '2026-01-04 09:00:00+00', 40.00, 'A ngày 4 / 1'),
    (105, 'A', 4, '2026-01-04 09:00:00+00',  5.00, 'A ngày 4 / 2'),
    (106, 'A', 8, '2026-01-08 09:00:00+00', 50.00, 'A ngày 8'),
    (201, 'B', 1, '2026-01-01 09:00:00+00',  7.00, 'B ngày 1'),
    (202, 'B', 3, '2026-01-03 09:00:00+00',  8.00, 'B ngày 3 / 1'),
    (203, 'B', 3, '2026-01-03 09:00:00+00',  9.00, 'B ngày 3 / 2'),
    (204, 'B',10, '2026-01-10 09:00:00+00', 10.00, 'B ngày 10');
```

Kiểm tra:

```sql
SELECT event_id, account_id, day_no, amount
FROM window_frame_lab.events
ORDER BY account_id, day_no, event_id;
```

Kết quả logic:

| Account | Ngày | Event | Amount |
| --- | ---: | ---: | ---: |
| A | 1 | 101 | 10 |
| A | 2 | 102 | 20 |
| A | 2 | 103 | 30 |
| A | 4 | 104 | 40 |
| A | 4 | 105 | 5 |
| A | 8 | 106 | 50 |
| B | 1 | 201 | 7 |
| B | 3 | 202 | 8 |
| B | 3 | 203 | 9 |
| B | 10 | 204 | 10 |

Tổng account A = **155**, tổng account B = **34**.

### 4.3. Các nhóm peer

Khi viết:

```sql
ORDER BY day_no
```

các sự kiện có cùng `day_no` trong cùng partition là **peer** — hàng đồng hạng:

```text
Account A, ORDER BY day_no:

Peer group #1: day_no = 1 -> [101]           tổng 10
Peer group #2: day_no = 2 -> [102, 103]      tổng 50
Peer group #3: day_no = 4 -> [104, 105]      tổng 45
Peer group #4: day_no = 8 -> [106]           tổng 50
```

Ngược lại, nếu viết:

```sql
ORDER BY day_no, event_id
```

mỗi hàng có cặp khóa sắp xếp khác nhau trong bộ dữ liệu này. Vì vậy **mỗi peer group chỉ còn một hàng**.

Đây là nguyên tắc lớn: **peer group được quyết định bởi toàn bộ biểu thức `ORDER BY` của window**, chứ không phải bởi cột có tên “group”, thứ tự INSERT hay khóa chính của bảng.

---

## 5. ROWS: đếm từng hàng

`ROWS` dùng **vị trí hàng** trong thứ tự của partition để xác định frame.

Ví dụ:

```sql
SELECT
    event_id,
    account_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS sum_last_two_rows
FROM window_frame_lab.events
ORDER BY account_id, day_no, event_id;
```

Frame gồm **hàng hiện tại và tối đa một hàng ngay trước** trong cùng account.

Với account A:

| Event | Amount | Frame theo thứ tự (day_no,event_id) | SUM |
| ---: | ---: | --- | ---: |
| 101 | 10 | [101] | 10 |
| 102 | 20 | [101,102] | 30 |
| 103 | 30 | [102,103] | 50 |
| 104 | 40 | [103,104] | 70 |
| 105 | 5 | [104,105] | 45 |
| 106 | 50 | [105,106] | 55 |

Lưu ý ngày 2 và ngày 4 có nhiều sự kiện; `ROWS` vẫn chỉ đếm **hàng**, không tự gom những hàng có cùng ngày.

### 5.1. Vì sao nên dùng tie-breaker?

Nếu chỉ:

```sql
ORDER BY day_no
ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
```

thứ tự giữa event 102 và 103, cũng như giữa 104 và 105, **chưa được xác định duy nhất**.

Một truy vấn có thể đưa 102 đứng trước 103; một kế hoạch/hoàn cảnh khác có thể đưa 103 đứng trước 102. Với `ROWS`, điều này ảnh hưởng hàng nào là “1 PRECEDING”, từ đó ảnh hưởng SUM/AVG.

Để tính **kết quả lặp lại được**, thêm một khóa giải quyết hòa điểm:

```sql
ORDER BY day_no ASC, event_id ASC
```

Nếu nghiệp vụ có trình tự sự kiện thật, nên chọn tie-breaker **có ý nghĩa nghiệp vụ** (thời gian tạo độ phân giải cao, sequence hoặc ID ổn định) chứ không mặc định ID ngẫu nhiên phản ánh thứ tự thời gian.

### 5.2. ROWS cho tổng lũy kế từng hàng

```sql
SELECT
    event_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Kết quả account A:

| Event | Amount | Running SUM |
| ---: | ---: | ---: |
| 101 | 10 | 10 |
| 102 | 20 | 30 |
| 103 | 30 | 60 |
| 104 | 40 | 100 |
| 105 | 5 | 105 |
| 106 | 50 | 155 |

Ở đây không có “bước nhảy” cùng một giá trị cho toàn bộ peer group: khi đến mỗi hàng tiếp theo, frame thêm đúng hàng đó.

### 5.3. ROWS cho trung bình trượt N hàng

Tính trung bình **tối đa ba giao dịch gần nhất**, tính cả giao dịch hiện tại:

```sql
SELECT
    event_id, day_no, amount,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS average_last_three_events,
    COUNT(*) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS observations_in_frame
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Ở hai hàng đầu, frame không đủ ba hàng, nên `AVG` chia cho **số hàng hiện có**. Nó không tự thêm các hàng giả có giá trị 0.

Với event 104, ba hàng trong frame là 102,103,104: trung bình `(20+30+40)/3 = 30`.

**Khi nào dùng ROWS?** Khi nghiệp vụ nói về **N bản ghi**, **N lần giao dịch**, **N phép đo** hoặc một thứ tự sự kiện được xác định, không nhất thiết là N ngày thực tế.

---

## 6. RANGE: khoảng giá trị trong ORDER BY

`RANGE` xác định frame theo **giá trị của biểu thức sắp xếp**, không phải số hàng. Khi dùng `RANGE BETWEEN n PRECEDING AND CURRENT ROW`, `n` là **khoảng cách trên miền giá trị của khóa**, chứ không phải số hàng.

Ví dụ dùng cột số `day_no`:

```sql
SELECT
    event_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS sum_recent_day_range
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Tại event 104 (ngày 4), `RANGE BETWEEN 2 PRECEDING AND CURRENT ROW` lấy những hàng có `day_no` trong phạm vi **[2,4]**, gồm 102,103,104,105; tổng **95**.

Tại event 106 (ngày 8), khung là **[6,8]**, chỉ có event 106, tổng **50**. Nó **không đi lùi hai nhóm ngày có dữ liệu** để lấy ngày 4 và ngày 2.

### 6.1. RANGE bao gồm toàn bộ peer tại CURRENT ROW

Khi có:

```sql
ORDER BY day_no
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

điểm cuối `CURRENT ROW` ở dạng RANGE không nhất thiết dừng ngay tại **hàng vật lý hiện tại**. Nó bao gồm **toàn bộ các peer có cùng giá trị sắp xếp với hàng hiện tại**.

Ví dụ account A:

- Ở event 102 (ngày 2), frame gồm event 101,102,103; tổng **60**.
- Ở event 103 (cũng ngày 2), frame vẫn gồm 101,102,103; tổng **60**.
- Ở event 104 (ngày 4), frame gồm 101..105; tổng **105**.
- Ở event 105 (ngày 4), tổng vẫn **105**.

Vì vậy `RANGE` với `CURRENT ROW` có thể tạo **kết quả giống nhau cho toàn bộ peer group**.

### 6.2. RANGE cần cẩn thận với kiểu offset

Khi khung RANGE có offset như `2 PRECEDING` hoặc `1 FOLLOWING`, PostgreSQL yêu cầu cấu trúc `ORDER BY` phù hợp: **một biểu thức sắp xếp**, với offset có kiểu thích hợp cho phép toán khoảng cách của biểu thức đó.

Ví dụ hợp lệ theo ý tưởng:

```sql
ORDER BY day_no
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

hoặc với timestamp:

```sql
ORDER BY event_at
RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
```

Không viết `RANGE ... 2 PRECEDING` trên một khóa timestamp rồi mặc định `2` là hai ngày. PostgreSQL cần kiểu `INTERVAL` thích hợp.

### 6.3. Không dùng nhiều ORDER BY khi RANGE có offset

Một ràng buộc cú pháp quan trọng trong PostgreSQL: `RANGE` với `offset PRECEDING/FOLLOWING` yêu cầu chỉ một expression `ORDER BY`.

Ví dụ ý tưởng sai:

```sql
-- KHÔNG PHÙ HỢP: RANGE offset với hai khóa ORDER BY.
SUM(amount) OVER (
    ORDER BY day_no, event_id
    RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

Vì “lùi hai đơn vị” không có một nghĩa scalar rõ ràng khi khóa sắp xếp là bộ hai thành phần.

Muốn giữ nhóm theo ngày và khoảng cách ngày, dùng:

```sql
ORDER BY day_no
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

Nếu nghiệp vụ cần thứ tự từng event chính xác, cân nhắc `ROWS` với khóa phụ.

### 6.4. RANGE với thứ tự DESC

Từ `PRECEDING`/`FOLLOWING` chỉ hướng **trong thứ tự ORDER BY**, không phải hướng tăng/giảm số học tuyệt đối.

Ví dụ:

```sql
ORDER BY day_no DESC
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

Trong sắp xếp giảm dần, các giá trị đứng trước ngày hiện tại có thể là **ngày lớn hơn**, không phải nhỏ hơn. Vì thế “2 PRECEDING” có thể là các giá trị ở phía cao hơn của trục số.

Khi viết rolling time-series, nên đặt `ORDER BY event_at ASC` tường minh nếu ý định là “những mốc trước thời điểm hiện tại”.

---

## 7. GROUPS: đếm nhóm đồng hạng

`GROUPS` xác định frame bằng **số peer group**, mỗi group chứa những hàng có các giá trị `ORDER BY` giống nhau.

Ví dụ:

```sql
SELECT
    event_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS sum_current_and_previous_day_group
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Peer group của A:

```text
G1: ngày 1 -> [101]      sum=10
G2: ngày 2 -> [102,103]  sum=50
G3: ngày 4 -> [104,105]  sum=45
G4: ngày 8 -> [106]      sum=50
```

`GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW`:

- Ở G1: chỉ G1 → **10**.
- Ở G2: G1 + G2 → **60**.
- Ở G3: G2 + G3 → **95**.
- Ở G4: G3 + G4 → **95**.

Tất cả hàng trong cùng peer group nhận **cùng frame** trong ví dụ không có `EXCLUDE`.

### 7.1. Điểm khác quan trọng so với RANGE

Tại ngày 8:

- `RANGE BETWEEN 2 PRECEDING AND CURRENT ROW` → xét ngày 6..8, chỉ có ngày 8 → **50**.
- `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` → xét **hai nhóm ngày có dữ liệu gần nhất**: ngày 4 và 8 → **45 + 50 = 95**.

Đây là hai câu hỏi nghiệp vụ khác nhau:

- “Doanh số trong **ba ngày gần đây**” → khung RANGE theo ngày hoặc thời gian.
- “Doanh số của **hai ngày giao dịch gần nhất có bản ghi**” → GROUPS theo những nhóm ngày thực sự xuất hiện.

Không chọn GROUPS chỉ vì dữ liệu có cột ngày. Hãy xác định đơn vị mà nghiệp vụ cần đếm.

### 7.2. GROUPS yêu cầu ORDER BY

Để biết nhóm nào “trước” hay “sau”, phải có thứ tự cho các peer group. Vì thế, PostgreSQL yêu cầu `ORDER BY` khi dùng GROUPS.

Ví dụ phù hợp:

```sql
GROUPS BETWEEN 1 PRECEDING AND 1 FOLLOWING
```

đi cùng:

```sql
ORDER BY day_no
```

Nếu dữ liệu cần gom theo tháng, một cách là tổng hợp theo tháng trước, hoặc đặt biểu thức tháng trong `ORDER BY`. Cần hiểu việc tính offset theo **nhóm biểu thức đã sắp xếp**, không tự nhận biết lịch kinh doanh.

### 7.3. GROUPS có thể gom nhiều cột sắp xếp

Khác `RANGE` có offset, `GROUPS` có thể dùng nhiều biểu thức `ORDER BY`; peer group được định nghĩa bằng **toàn bộ bộ giá trị đó**.

Ví dụ:

```sql
ORDER BY day_no, event_id
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
```

Vì `event_id` là duy nhất trong lab, các group đều chỉ còn một hàng. Trong trường hợp này `GROUPS 1 PRECEDING` sẽ cho phạm vi giống `ROWS 1 PRECEDING` theo thứ tự đã định, nhưng chính việc **bổ sung khóa thứ hai** đã làm thay đổi peer group.

Nếu mục tiêu là nhóm theo ngày, hãy dùng `ORDER BY day_no` riêng cho frame GROUPS.

---

## 8. So sánh ROWS, RANGE và GROUPS trên cùng bộ dữ liệu

Đây là câu truy vấn quan trọng nhất của bài:

```sql
SELECT
    event_id,
    day_no,
    amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS last_two_rows,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_two_value_units,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS last_two_peer_groups

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Kết quả dự kiến:

| Event | Ngày | Amount | ROWS: 1 trước | RANGE: 2 đơn vị trước | GROUPS: 1 nhóm trước |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 10 | 10 | 10 | 10 |
| 102 | 2 | 20 | 30 | 60 | 60 |
| 103 | 2 | 30 | 50 | 60 | 60 |
| 104 | 4 | 40 | 70 | 95 | 95 |
| 105 | 4 | 5 | 45 | 95 | 95 |
| 106 | 8 | 50 | 55 | 50 | 95 |

Giải thích nhanh:

- Ở event **102**: ROWS nhìn 101,102 → 30; RANGE ngày [0,2] nhìn 101,102,103 → 60; GROUPS nhìn ngày 1 và 2 → 60.
- Ở event **104**: ROWS nhìn 103,104 → 70; RANGE ngày [2,4] nhìn cả bốn hàng của ngày 2 và 4 → 95; GROUPS nhìn hai peer group ngày 2 và 4 → 95.
- Ở event **106**: ROWS nhìn 105,106 → 55; RANGE ngày [6,8] nhìn 106 → 50; GROUPS nhìn ngày 4 và 8 → 95.

**Lưu ý về ORDER BY:** ở cột ROWS có `event_id` để tạo thứ tự từng hàng xác định; ở RANGE/GROUPS chỉ dùng `day_no` để giữ peer group theo ngày. Cả ba cửa sổ vì thế **được định nghĩa có chủ đích khác nhau**. Nếu thêm `event_id` vào RANGE/GROUPS, ý nghĩa peer group sẽ thay đổi và RANGE có offset còn không cho phép nhiều khóa ORDER BY.

---

## 9. Ranh giới CURRENT ROW không luôn nghĩa cùng một thứ

Một sai lầm thường gặp là đọc:

```sql
... BETWEEN CURRENT ROW AND CURRENT ROW
```

như “chỉ hàng hiện tại” trong mọi trường hợp.

Thực tế:

| Loại frame | `CURRENT ROW` khi là điểm bắt đầu/kết thúc |
| --- | --- |
| `ROWS` | Chính vị trí của **hàng hiện tại** |
| `RANGE` | Cạnh đầu/cuối của **peer group hiện tại** |
| `GROUPS` | Cạnh đầu/cuối của **peer group hiện tại** |

Thử:

```sql
SELECT
    event_id, day_no, amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS current_row_amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS current_range_peer_amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS current_group_amount

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Ở event 102:

- ROWS current/current → chỉ event 102 → **20**.
- RANGE current/current → cả nhóm ngày 2: event 102 + 103 → **50**.
- GROUPS current/current → cả nhóm ngày 2 → **50**.

Ở event 104:

- ROWS → **40**.
- RANGE và GROUPS → nhóm ngày 4: 40 + 5 = **45**.

### 9.1. Khung bắt đầu tại CURRENT ROW

Ví dụ:

```sql
ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
```

nghĩa là từ hàng hiện tại đến cuối partition.

Trong:

```sql
RANGE BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
```

điểm bắt đầu là **peer đầu tiên của hàng hiện tại**, nên những hàng peer ở phía trước hàng hiện tại theo một thứ tự vật lý có thể vẫn được đưa vào frame. Khi cần “từ event hiện tại tới cuối” theo từng sự kiện, dùng `ROWS` với thứ tự có tie-breaker.

---

## 10. Khung mặc định: một nguyên nhân kết quả bất ngờ

Nếu có `ORDER BY` trong `OVER` nhưng **không khai báo frame**, PostgreSQL dùng khung mặc định có ngữ nghĩa tương đương:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Nó đi từ đầu partition tới **peer cuối cùng của hàng hiện tại**.

Ví dụ:

```sql
SELECT
    event_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
    ) AS default_running_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Kết quả:

| Event | Ngày | Amount | SUM theo frame mặc định |
| ---: | ---: | ---: | ---: |
| 101 | 1 | 10 | 10 |
| 102 | 2 | 20 | 60 |
| 103 | 2 | 30 | 60 |
| 104 | 4 | 40 | 105 |
| 105 | 4 | 5 | 105 |
| 106 | 8 | 50 | 155 |

Nó khác tổng lũy kế từng hàng, vì các peer **được cộng cùng một thời điểm logic**.

### 10.1. Không có ORDER BY thì frame mặc định là gì?

Nếu không viết `ORDER BY` trong `OVER`, tất cả hàng của partition được xem là peer của nhau trong ngữ cảnh mặc định, nên frame bao gồm **toàn bộ partition**.

Ví dụ:

```sql
SELECT
    event_id,
    account_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
    ) AS full_account_sum
FROM window_frame_lab.events
ORDER BY account_id, day_no, event_id;
```

Mọi hàng account A có `full_account_sum = 155`; mọi hàng B có `full_account_sum = 34`.

Đừng chỉ nhìn tên `SUM OVER(...)` rồi nghĩ nó luôn là tổng lũy kế. **Có ORDER BY hay không** và **frame được khai báo ra sao** quyết định phép tính.

### 10.2. Nên khai báo frame tường minh khi nghiệp vụ nhạy cảm

Với tổng lũy kế theo **từng hàng**, viết rõ:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no, event_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Với tổng toàn partition:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

hoặc đơn giản hơn:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
)
```

Với lũy kế theo **ngày/peer**, frame RANGE mặc định có thể chính là điều bạn muốn, nhưng nên ghi rõ ý định trong tài liệu truy vấn.

---

## 11. Khung toàn partition và CURRENT ROW đến cuối

### 11.1. Toàn bộ partition

```sql
SELECT
    event_id,
    account_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS account_total
FROM window_frame_lab.events
ORDER BY account_id, day_no, event_id;
```

Mọi hàng A nhận 155; mọi hàng B nhận 34.

Điểm khác với `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`: frame không mở rộng dần theo từng hàng; nó đã gồm **đầu tới cuối partition** ở mọi vị trí.

### 11.2. Tổng từ hàng hiện tại tới cuối

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
    ) AS remaining_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Với A:

| Event | remaining_sum |
| ---: | ---: |
| 101 | 155 |
| 102 | 145 |
| 103 | 125 |
| 104 | 95 |
| 105 | 55 |
| 106 | 50 |

Điều này có thể dùng để tính tổng giá trị còn lại **tính từ sự kiện hiện tại**, không phải tổng giá trị trước sự kiện.

### 11.3. Loại hàng hiện tại để tính quá khứ thuần túy

Nếu chỉ muốn tổng của **những hàng trước sự kiện hiện tại**:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND 1 PRECEDING
    ) AS sum_before_current
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Ở event 101, frame rỗng → `SUM` trả **NULL**, không phải 0; ở event 102, tổng quá khứ là 10.

Nếu nghiệp vụ muốn hiển thị 0 cho tổng quá khứ chưa có dữ liệu:

```sql
COALESCE(
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND 1 PRECEDING
    ),
    0::NUMERIC
)
```

Việc đổi NULL thành 0 cần là quyết định trình bày có chủ đích.

---

## 12. FOLLOWING: cửa sổ nhìn về phía trước

Các offset `FOLLOWING` cho phép xem những hàng, nhóm hoặc giá trị **đứng sau** hàng hiện tại.

Ví dụ ROWS:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 FOLLOWING AND 2 FOLLOWING
    ) AS sum_next_two_rows
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Ở event 101: hai hàng tiếp theo là 102 và 103, tổng **50**.

Ở event 105: chỉ còn event 106, tổng **50**.

Ở event 106: không còn hàng nào, frame rỗng và `SUM` trả **NULL**.

### 12.1. Trung bình đối xứng quanh sự kiện

```sql
SELECT
    event_id,
    amount,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS centered_three_row_avg
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Đây là một trung bình trượt **có nhìn vào tương lai**. Trong báo cáo hồi cứu, điều đó có thể phù hợp; trong hệ thống dự báo ở thời điểm hiện tại, sử dụng hàng tương lai có thể gây **data leakage** nếu những sự kiện đó chưa được biết.

### 12.2. Không đồng nghĩa FOLLOWING với tương lai theo thời gian

`FOLLOWING` chỉ là “đứng phía sau trong ORDER BY”. Nếu `ORDER BY event_at DESC`, những hàng FOLLOWING có thể là sự kiện **cũ hơn**. Hãy xác định chiều sắp xếp trước khi dùng khung dựa trên PRECEDING/FOLLOWING.

---

## 13. EXCLUDE: loại một phần của frame

PostgreSQL hỗ trợ tùy chọn frame exclusion:

```sql
EXCLUDE NO OTHERS
EXCLUDE CURRENT ROW
EXCLUDE GROUP
EXCLUDE TIES
```

Exclusion được áp dụng **sau khi xác định frame gốc**; nó không thay đổi định nghĩa partition hay thứ tự window.

| Tùy chọn | Ảnh hưởng |
| --- | --- |
| `EXCLUDE NO OTHERS` | Không loại thêm hàng nào; mặc định |
| `EXCLUDE CURRENT ROW` | Loại **hàng hiện tại**, nhưng giữ các peer khác nếu chúng thuộc frame |
| `EXCLUDE GROUP` | Loại **toàn bộ peer group của hàng hiện tại**, kể cả hàng hiện tại |
| `EXCLUDE TIES` | Loại **những peer khác**, nhưng giữ chính hàng hiện tại |
 
### 13.1. Lab với RANGE và các peer ngày 2

Xét event 102, account A:

```text
Khung RANGE:
UNBOUNDED PRECEDING ... CURRENT ROW

Những hàng ban đầu thuộc frame:
event 101, amount 10 (ngày 1)
event 102, amount 20 (ngày 2) <- CURRENT ROW
event 103, amount 30 (ngày 2) <- PEER của 102
Tổng gốc = 60
```

Các tùy chọn sẽ cho:

| Exclusion | Hàng còn lại với event 102 | SUM |
| --- | --- | ---: |
| NO OTHERS | 101,102,103 | 60 |
| CURRENT ROW | 101,103 | 40 |
| GROUP | 101 | 10 |
| TIES | 101,102 | 30 |

Với event 103:

- `EXCLUDE CURRENT ROW` giữ 101 và 102 → 10+20=30.
- `EXCLUDE TIES` giữ 101 và chính 103 → 10+30=40.
- `EXCLUDE GROUP` chỉ giữ 101 → 10.

Điều này cho thấy **CURRENT ROW và TIES khác nhau**, ngay cả khi các hàng cùng giá trị sắp xếp.

### 13.2. Câu SQL minh họa cả bốn tùy chọn

```sql
SELECT
    event_id, day_no, amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE NO OTHERS
    ) AS sum_default,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS sum_without_current,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE GROUP
    ) AS sum_before_peer_group,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE TIES
    ) AS sum_without_other_peers

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

### 13.3. Khung rỗng sau exclusion

Ở event 101, nó thuộc peer group đầu tiên của A. Với:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
EXCLUDE GROUP
```

frame gốc chỉ có event 101, rồi exclusion loại cả group ngày 1. Frame còn **0 hàng**.

Khi đó:

- `SUM(amount)` → **NULL**.
- `AVG(amount)` → **NULL**.
- `COUNT(*)` → **0**.

Không đồng nhất “không có hàng trong frame” với “các hàng có amount bằng 0”.

### 13.4. EXCLUDE GROUP có cả trường hợp ROWS

`EXCLUDE GROUP` vẫn dựa vào **peer theo ORDER BY** ngay cả khi frame gốc dùng `ROWS`. Ví dụ ROWS có frame ba hàng nhưng hiện tại có nhiều peer theo ORDER BY: exclusion có thể loại các peer đang hiện diện trong frame.

Nếu không có `ORDER BY`, tất cả hàng trong partition được xem là peers trong các ngữ cảnh cần xác định peer. Đừng dùng `EXCLUDE GROUP` mà không kiểm tra nó có thể loại **cả frame**.

### 13.5. Không nhầm EXCLUDE với WHERE

`EXCLUDE CURRENT ROW` không xóa hàng hiện tại khỏi **kết quả truy vấn**. Hàng vẫn được trả về; chỉ có phép tổng hợp/window value tại hàng đó được tính trên frame đã loại bớt.

Ngược lại, điều kiện `WHERE` có thể xóa một hàng khỏi dữ liệu đầu vào của tất cả window functions.

---

## 14. LAST_VALUE: bẫy khung mặc định

`LAST_VALUE(expression)` trả giá trị ở **hàng cuối cùng của frame hiện tại**, không mặc định là hàng cuối cùng của toàn bộ partition.

Đây là điểm rất dễ sai.

### 14.1. Tại sao LAST_VALUE thường giống giá trị hiện tại?

Thử:

```sql
SELECT
    event_id,
    day_no,
    LAST_VALUE(day_no) OVER (
        PARTITION BY account_id
        ORDER BY day_no
    ) AS last_day_in_default_frame
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Vì frame mặc định kết thúc ở **peer cuối của ngày hiện tại**, nên `LAST_VALUE(day_no)` trả ngày hiện tại (1,2,2,4,4,8), **không phải ngày 8 cho mọi hàng**.

### 14.2. Muốn hàng cuối của partition: khai báo full frame

```sql
SELECT
    event_id,
    day_no,
    LAST_VALUE(day_no) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS final_day_in_account
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Khi đó mọi hàng A nhận ngày **8**.

Nếu muốn `LAST_VALUE(amount)` là amount của **event cuối cùng**, phải có thứ tự duy nhất:

```sql
SELECT
    event_id, day_no, amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS final_event_amount
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Mọi hàng A nhận **50**, là amount của event 106.

### 14.3. FIRST_VALUE cũng phụ thuộc frame

`FIRST_VALUE` lấy giá trị của **hàng đầu tiên trong frame**. Với frame từ đầu partition tới CURRENT ROW, nó thường là giá trị đầu tiên của partition. Nhưng với khung trượt:

```sql
SELECT
    event_id, amount,
    FIRST_VALUE(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS first_amount_in_last_three
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

giá trị FIRST_VALUE thay đổi khi điểm bắt đầu của frame di chuyển.

### 14.4. NTH_VALUE và frame chưa đủ hàng

`NTH_VALUE(expression, n)` trả giá trị của **hàng thứ n trong frame** (n tính từ 1). Nếu frame chưa có đủ n hàng, kết quả là NULL.

Ví dụ:

```sql
SELECT
    event_id, amount,
    NTH_VALUE(amount, 3) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS third_amount_so_far
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Ở hai hàng đầu, frame có ít hơn ba hàng nên kết quả NULL; từ event 103 trở đi, phần tử thứ ba của frame là **30**.

Không dùng NTH_VALUE mà không xác định rõ thứ tự và frame, nhất là khi có peer.

---

## 15. Hàm nào thực sự bị frame ảnh hưởng?

Không phải hàm nào đi cùng `OVER` cũng đọc frame theo cách như SUM.

| Nhóm hàm | Ví dụ | Vai trò của frame |
| --- | --- | --- |
| Aggregate chạy như window | `SUM`, `AVG`, `COUNT`, `MIN`, `MAX` | **Sử dụng frame** |
| Hàm giá trị theo vị trí trong frame | `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` | **Sử dụng frame** |
| Hàm xếp hạng | `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `PERCENT_RANK`, `CUME_DIST` | Tính theo partition/ORDER BY, không bị frame thu hẹp theo cách aggregate |
| Hàm dịch chuyển | `LAG`, `LEAD` | Tham chiếu vị trí trong partition theo ORDER BY, không giới hạn vào frame aggregate đang khai báo |
| Hàm chia bucket | `NTILE` | Phân nhóm vị trí trên partition, không phụ thuộc frame theo kiểu SUM |

### 15.1. Ví dụ LAG không bị giới hạn bởi ROWS CURRENT ROW

```sql
SELECT
    event_id,
    amount,
    LAG(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS previous_amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS current_amount_sum

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Ở event 102:

- `LAG(amount)` vẫn trả **10** từ event 101 (hàng trước trong partition).
- `SUM(amount)` chỉ tính current row, trả **20**.

Nếu nhầm rằng `LAG` chỉ tìm trong frame CURRENT ROW, bạn sẽ dự đoán sai.

### 15.2. RANK và DENSE_RANK vẫn dựa vào peer

```sql
SELECT
    event_id, day_no,
    ROW_NUMBER() OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
    ) AS row_seq,

    RANK() OVER (
        PARTITION BY account_id
        ORDER BY day_no
    ) AS day_rank,

    DENSE_RANK() OVER (
        PARTITION BY account_id
        ORDER BY day_no
    ) AS day_dense_rank

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Với A:

| Event | Ngày | ROW_NUMBER | RANK theo ngày | DENSE_RANK theo ngày |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 1 | 1 | 1 |
| 102 | 2 | 2 | 2 | 2 |
| 103 | 2 | 3 | 2 | 2 |
| 104 | 4 | 4 | 4 | 3 |
| 105 | 4 | 5 | 4 | 3 |
| 106 | 8 | 6 | 6 | 4 |

RANK có khoảng trống sau nhóm đồng hạng, DENSE_RANK thì không. Sự đồng hạng do `ORDER BY day_no` tạo ra, không phải do frame.

---

## 16. RANGE với thời gian và INTERVAL

Cột `day_no INTEGER` giúp học ý nghĩa offset, nhưng hệ thống thực tế thường có `TIMESTAMP` hoặc `TIMESTAMPTZ`.

Với `event_at TIMESTAMPTZ`:

```sql
SELECT
    event_id,
    event_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY event_at
        RANGE BETWEEN INTERVAL '2 days' PRECEDING
                  AND CURRENT ROW
    ) AS amount_last_two_days
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY event_at, event_id;
```

Khi đứng tại 2026-01-04 09:00 UTC, frame gồm các sự kiện từ **2026-01-02 09:00 UTC** đến thời điểm hiện tại, bao gồm các peer cùng timestamp. Tổng là **20 + 30 + 40 + 5 = 95**.

Tại 2026-01-08 09:00 UTC, chỉ có event 106 trong khoảng hai ngày vừa qua, tổng 50.

### 16.1. Khác nhau giữa hai ngày và hai sự kiện

- `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW`: tối đa **hai sự kiện**.
- `RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW`: **mọi sự kiện có timestamp trong khoảng**, có thể là 0, 1 hoặc hàng nghìn sự kiện.
- `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` với `ORDER BY event_at`: **hai timestamp khác biệt gần nhất có sự kiện** (nếu các timestamp được nhóm đúng theo nghiệp vụ).

Nếu mỗi event có timestamp riêng tới microsecond, GROUPS theo `event_at` có thể trở thành gần giống đếm event. Nếu muốn nhóm theo **ngày lịch**, cần xác định khóa nhóm ngày phù hợp, thường qua bước tổng hợp theo ngày hoặc biểu thức ngày có timezone rõ.

### 16.2. Múi giờ và daylight saving time

`TIMESTAMPTZ` biểu diễn một thời điểm tuyệt đối, nhưng khi nói “ngày hôm qua”, “tháng này”, “một ngày lịch” còn cần **múi giờ nghiệp vụ**.

Ví dụ:

- “48 giờ vừa qua” là khoảng thời gian theo giờ.
- “Hai ngày lịch địa phương” có thể đi qua thời điểm đổi giờ mùa hè ở một số khu vực và không luôn đồng nghĩa 48 giờ.

Với PostgreSQL, kiểu `INTERVAL '1 day'` và `INTERVAL '24 hours'` có thể có tác động khác nhau khi cộng/trừ timestamp có timezone qua mốc daylight saving, tùy ngữ cảnh và vùng giờ. Vì thế cần kiểm tra hợp đồng thời gian trước khi chọn khung RANGE.

Dữ liệu lab dùng UTC nên ví dụ không có sự khác biệt DST.

### 16.3. Nếu muốn cửa sổ ngày lịch, hãy làm rõ mức hạt dữ liệu

Ví dụ báo cáo bán hàng theo ngày:

```sql
WITH day_totals AS (
    SELECT
        account_id,
        (event_at AT TIME ZONE 'UTC')::DATE AS event_day,
        SUM(amount) AS day_amount
    FROM window_frame_lab.events
    GROUP BY
        account_id,
        (event_at AT TIME ZONE 'UTC')::DATE
)
SELECT
    account_id,
    event_day,
    day_amount,
    SUM(day_amount) OVER (
        PARTITION BY account_id
        ORDER BY event_day
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_three_days_with_activity
FROM day_totals
ORDER BY account_id, event_day;
```

**Chú ý:** Sau khi gộp thành một hàng cho mỗi ngày có dữ liệu, `ROWS 2 PRECEDING` nghĩa là **ba ngày có phát sinh sự kiện gần nhất**, không phải ba ngày lịch liên tiếp nếu có ngày không có dữ liệu.

Nếu cần ba ngày lịch liên tiếp, phải xây calendar/series hoặc một RANGE theo khoảng thời gian với ngữ nghĩa thích hợp.

---

## 17. Khác biệt giữa GROUPS và bảng đã GROUP BY

Hai từ “group” dễ gây nhầm:

- `GROUP BY day_no` làm **gộp nhiều event thành một hàng mỗi ngày**.
- `GROUPS ...` trong window frame **không tự gộp hàng**, mà đếm các peer group của dữ liệu đầu vào và vẫn giữ từng hàng sự kiện.

Ví dụ GROUP BY:

```sql
SELECT
    account_id,
    day_no,
    SUM(amount) AS day_total
FROM window_frame_lab.events
GROUP BY account_id, day_no
ORDER BY account_id, day_no;
```

Account A lúc này chỉ còn bốn hàng (ngày 1,2,4,8).

Ngược lại, khi dùng:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no
    GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
)
```

account A vẫn có **sáu hàng sự kiện**. Hai sự kiện ngày 2 cùng nhận tổng 60 theo frame, nhưng không bị hợp thành một hàng duy nhất.

### 17.1. Khi nào tổng hợp trước rồi dùng ROWS?

Nếu bài toán cần kết quả **mỗi ngày một hàng** (ví dụ dashboard ngày), hãy GROUP BY ngày trước, rồi tính rolling theo những hàng ngày đã tổng hợp. Khi đó `ROWS` trên bảng day_totals có thể dễ hiểu hơn.

Nếu bài toán cần giữ **mỗi event chi tiết** nhưng tính bối cảnh theo các nhóm ngày, `GROUPS` trên dữ liệu chi tiết có thể rõ nghĩa hơn.

Đây là khác biệt về **mức hạt dữ liệu cần trả**, không chỉ khác cú pháp.

---

## 18. GROUPS nhìn một nhóm trước và một nhóm sau

Ví dụ:

```sql
SELECT
    event_id, day_no, amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS neighboring_group_total
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Dựa trên các nhóm A ngày 1,2,4,8:

| Peer group hiện tại | Nhóm trong frame | Tổng |
| --- | --- | ---: |
| Ngày 1 | Ngày 1, 2 | 10 + 50 = 60 |
| Ngày 2 | Ngày 1, 2, 4 | 10 + 50 + 45 = 105 |
| Ngày 4 | Ngày 2, 4, 8 | 50 + 45 + 50 = 145 |
| Ngày 8 | Ngày 4, 8 | 45 + 50 = 95 |

Với ngày 2, cả event 102 và 103 nhận 105. Với ngày 4, cả event 104 và 105 nhận 145.

Ứng dụng phù hợp:

- So sánh một kỳ báo cáo với kỳ liền trước/liền sau **có dữ liệu**.
- Tạo chỉ số xung quanh một nhóm giá trị xếp hạng.
- Đo doanh số của các cụm sự kiện đồng thời.

Nếu yêu cầu “một tuần trước và một tuần sau”, GROUPS thường **không tự hiểu lịch tuần**, trừ khi mỗi group được định nghĩa đúng theo tuần nghiệp vụ.

---

## 19. ROWS và thứ tự không ổn định của peer

Giả sử viết:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Một người có thể nhìn `ORDER BY day_no,event_id` ở cuối SELECT và tưởng ROWS cũng chắc chắn đi theo thứ tự đó. **Không đúng**: ROWS window chỉ ghi `ORDER BY day_no`; giữa hai peer cùng ngày, thứ tự nội bộ chưa được ràng buộc.

Để ổn định:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no, event_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Điểm này ảnh hưởng:

- Tổng lũy kế từng hàng.
- `LAG`/`LEAD`.
- `ROW_NUMBER`.
- `FIRST_VALUE`/`LAST_VALUE` theo hàng.
- `ROWS n PRECEDING/FOLLOWING`.

**Đừng trông chờ thứ tự vật lý trên đĩa, thứ tự INSERT hoặc thứ tự hiển thị ngoài cùng giải quyết peer của window.**

---

## 20. Ranh giới tại đầu/cuối partition và khung rỗng

Frame có thể bị **cắt ngắn** bởi biên partition. Ví dụ một `ROWS BETWEEN 4 PRECEDING AND CURRENT ROW` tại hàng đầu tiên chỉ có đúng một hàng trong frame, không phải năm.

### 20.1. COUNT giúp quan sát kích thước thực tế

```sql
SELECT
    event_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS frame_row_count,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS frame_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Kết quả frame_row_count là 1,2,3,3,3,3 cho A.

### 20.2. Khung không có hàng cho aggregate trả gì?

Ví dụ:

```sql
SELECT
    event_id,
    COUNT(*) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 FOLLOWING AND 2 FOLLOWING
    ) AS next_rows_count,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 FOLLOWING AND 2 FOLLOWING
    ) AS next_rows_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Ở event 106:

- `COUNT(*)` = 0.
- `SUM(amount)` = NULL.

Đây là hành vi aggregate trên **tập rỗng**. Không nhầm với một frame có một hàng `amount = 0`.

### 20.3. Offset 0 và khung điểm hiện tại

`ROWS 0 PRECEDING` biểu thị chính vị trí hàng hiện tại, tương tự `ROWS CURRENT ROW` trong ví dụ đơn giản. Với RANGE/GROUPS, offset bằng 0 có thể liên quan tới peer; không nên dùng 0 như một cách mặc định ép RANGE về **một hàng vật lý**.

Các offset phải là giá trị phù hợp theo cú pháp/kiểu, không âm và không NULL theo yêu cầu của PostgreSQL. Nếu ứng dụng cho người dùng nhập kích thước window, phải validate trước khi xây SQL.

---

## 21. FILTER kết hợp frame: tính có điều kiện trong một cửa sổ

PostgreSQL hỗ trợ `FILTER (WHERE ...)` cho những aggregate window phù hợp.

Giả sử chỉ tính tổng amount của các event có giá trị ít nhất 20, nhưng frame vẫn xác định theo **mọi event**:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) FILTER (WHERE amount >= 20) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS large_amount_in_last_three_rows
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Điểm quan trọng:

- Khung ROWS vẫn xét các hàng theo `ORDER BY day_no,event_id`.
- Aggregate chỉ **cộng những hàng trong frame** thỏa `amount >= 20`.
- Hàng amount nhỏ vẫn có thể chiếm một vị trí trong khung ba hàng.

Ngược lại, nếu lọc `WHERE amount >= 20` ở **truy vấn ngoài trước window**, các hàng nhỏ không còn là đầu vào của window và không còn chiếm vị trí, nên kết quả khác.

### 21.1. Minh họa sự khác biệt

Ở event 106 (amount 50), frame ba hàng gần nhất gồm:

```text
104: amount 40
105: amount  5
106: amount 50
```

`SUM(amount) FILTER (WHERE amount >= 20)` trên frame này → **40+50=90**.

Nếu trước tiên dùng `WHERE amount >= 20` để loại event 105, khung ba hàng lúc đó có thể gồm 103,104,106 → **30+40+50=120**.

**`FILTER` trên aggregate** và **`WHERE` của query** là hai bước khác nhau.

---

## 22. WHERE, GROUP BY, HAVING và vị trí tính window

Trong trình tự xử lý logic của SQL, window functions nhận dữ liệu sau khi các điều kiện lọc và tổng hợp ở query block tương ứng đã được áp dụng. Vì thế không thể trực tiếp dùng window function trong `WHERE` của cùng query block.

Ví dụ không hợp lệ:

```sql
-- KHÔNG HỢP LỆ: window function trong WHERE cùng cấp.
SELECT event_id, amount
FROM window_frame_lab.events
WHERE ROW_NUMBER() OVER (
    PARTITION BY account_id
    ORDER BY day_no, event_id
) <= 2;
```

Muốn giữ hai sự kiện đầu tiên mỗi account, dùng derived table/CTE:

```sql
WITH numbered AS (
    SELECT
        event_id,
        account_id,
        day_no,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY day_no, event_id
        ) AS rn
    FROM window_frame_lab.events
)
SELECT event_id, account_id, day_no, amount
FROM numbered
WHERE rn <= 2
ORDER BY account_id, rn;
```

### 22.1. Window nhìn thấy dữ liệu sau WHERE

```sql
SELECT
    event_id,
    day_no,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
  AND day_no >= 2
ORDER BY day_no, event_id;
```

Ở đây event 101 (ngày 1) **không tồn tại trong đầu vào của window**, nên lũy kế bắt đầu ở ngày 2, không cộng 10 từ ngày 1.

Nếu muốn tính lũy kế trên **toàn bộ account**, sau đó chỉ hiển thị từ ngày 2, cần đặt window trong subquery trước, rồi lọc ở query ngoài:

```sql
WITH calculated AS (
    SELECT
        event_id,
        account_id,
        day_no,
        amount,
        SUM(amount) OVER (
            PARTITION BY account_id
            ORDER BY day_no, event_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_sum
    FROM window_frame_lab.events
)
SELECT *
FROM calculated
WHERE account_id = 'A'
  AND day_no >= 2
ORDER BY day_no, event_id;
```

Lúc đó event 102 có running_sum = **30** vì event 101 đã được cộng trước khi lọc kết quả.

---

## 23. Khung cho tổng lũy kế theo hai cách nghiệp vụ

### 23.1. Tính lũy kế ngay sau từng event

```sql
SELECT
    event_id, day_no, amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS after_event_balance
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Kết quả thay đổi **sau mỗi event**.

### 23.2. Tính lũy kế sau khi đóng ngày

```sql
SELECT
    event_id, day_no, amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS after_day_total
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Kết quả giống nhau cho những event **cùng ngày**.

Đặt tên khác nhau như `after_event_balance` và `after_day_total` rất có ích. Một cột `running_total` mơ hồ có thể gây tranh cãi nếu người đọc không biết nó là lũy kế **từng sự kiện** hay **từng nhóm ngày**.

---

## 24. Khi nào RANGE và GROUPS vô tình cho cùng kết quả?

Trong dữ liệu A, nếu nhóm ngày phân bố cách nhau đúng 1 đơn vị, `RANGE 1 PRECEDING` và `GROUPS 1 PRECEDING` có thể tình cờ chọn cùng tập.

Nhưng ở đây có khoảng trống ngày 4 tới ngày 8, nên khác nhau.

Có thể dùng các ví dụ đối lập:

```sql
SELECT
    event_id,
    day_no,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS one_value_unit_back,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS one_peer_group_back
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Ở event 104 (ngày 4):

- RANGE xét [3,4] → chỉ nhóm ngày 4 → **45**.
- GROUPS xét nhóm ngày 2 và 4 → **95**.

Nếu ngày 3 có event, GROUPS vẫn chọn nhóm trước gần nhất là ngày 3; RANGE [3,4] cũng chọn ngày 3,4. **Kết quả giống nhau trong một dataset không chứng minh hai frame đồng nghĩa.**

---

## 25. Dữ liệu NULL và peer group

Khi `ORDER BY` là một biểu thức nullable, nhiều hàng có giá trị `NULL` ở khóa sắp xếp được xem là peer với nhau trong định nghĩa window ORDER BY tương ứng.

Ví dụ cấu trúc:

```sql
SELECT
    event_id,
    score,
    SUM(amount) OVER (
        ORDER BY score NULLS LAST
        GROUPS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS peer_total
FROM some_table;
```

Ở đây `some_table` là bảng minh họa, chưa được tạo trong lab. Nếu có nhiều hàng `score IS NULL`, chúng có thể nằm cùng peer group tại phần NULLS LAST.

Lưu ý:

- `NULLS FIRST` / `NULLS LAST` ảnh hưởng vị trí nhóm NULL.
- `ROWS` với nhiều hàng cùng score NULL cần tie-breaker nếu muốn thứ tự từng hàng ổn định.
- `RANGE` offset trên khóa có NULL có ngữ nghĩa giới hạn cần kiểm tra theo loại và ranh giới; không nên trông chờ phép trừ offset trên NULL như với số bình thường.
- Nếu NULL nghĩa là “chưa xác định ngày giao dịch”, hãy quyết định nó có thuộc báo cáo thời gian hay cần phân loại riêng.

Không tự dùng `COALESCE(score,0)` để thay toàn bộ NULL bằng 0, vì có thể tạo những peer group mới và gộp dữ liệu thiếu với giá trị số 0 hợp lệ.

---

## 26. Khung và thứ tự có nhiều biểu thức

Giả sử cần sort theo `day_no` rồi `event_id`.

### 26.1. ROWS

```sql
ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
```

có thể dùng:

```sql
ORDER BY day_no, event_id
```

để xác định từng hàng.

### 26.2. GROUPS

```sql
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
```

cũng cho phép thứ tự có nhiều biểu thức, nhưng peer group được quyết định bởi **cả day_no và event_id**. Nếu event_id duy nhất, các group sẽ là từng hàng.

### 26.3. RANGE

Với `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, PostgreSQL có thể dùng ORDER BY nhiều biểu thức vì không cần đo một khoảng offset đơn trị. Nhưng với `RANGE BETWEEN n PRECEDING AND CURRENT ROW`, phần offset yêu cầu **một khóa ORDER BY** có thể đo khoảng cách.

Đây là lý do khác biệt giữa:

```sql
-- Có thể có nhiều khóa khi không dùng offset giá trị.
ORDER BY day_no, event_id
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

và:

```sql
-- Với offset 2, dùng một khóa số.
ORDER BY day_no
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

Đừng thêm khóa phụ vào ORDER BY của một window RANGE chỉ để sắp xếp kết quả cuối. Nếu chỉ cần sắp kết quả, dùng `ORDER BY account_id, day_no, event_id` bên ngoài SELECT.

---

## 27. Dùng WINDOW để đặt tên cửa sổ

Khi nhiều phép tính có cùng partition và thứ tự, PostgreSQL hỗ trợ mệnh đề `WINDOW` để tái sử dụng định nghĩa.

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER w_rows AS sum_last_three,
    AVG(amount) OVER w_rows AS avg_last_three,
    COUNT(*) OVER w_rows AS count_last_three
FROM window_frame_lab.events
WHERE account_id = 'A'
WINDOW w_rows AS (
    PARTITION BY account_id
    ORDER BY day_no, event_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
ORDER BY day_no, event_id;
```

Lợi ích:

- Không lặp lại dài dòng cùng một frame.
- Các cột thống kê dùng **cùng tập hàng**.
- Dễ tránh tình trạng SUM dùng ROWS nhưng AVG vô tình dùng frame mặc định RANGE.

### 27.1. Kế thừa định nghĩa window

Có thể đặt một window nền không có frame, rồi bổ sung frame:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS row_running_sum,

    AVG(amount) OVER (
        w ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_average

FROM window_frame_lab.events
WHERE account_id = 'A'
WINDOW w AS (
    PARTITION BY account_id
    ORDER BY day_no, event_id
)
ORDER BY day_no, event_id;
```

Trong PostgreSQL, việc sao chép và mở rộng định nghĩa window có các quy tắc; **không thể tùy tiện chồng thêm frame lên một window đã có frame**. Nếu cần nhiều frame khác nhau, đặt window nền gồm partition/order như ví dụ rồi bổ sung từng frame, hoặc đặt tên nhiều window tách biệt.

---

## 28. Hiệu năng: Sort, WindowAgg và kích thước frame

Window functions có thể cần sắp xếp các hàng theo partition/order trước khi tính. Trên bảng lớn, đây có thể là phần tốn CPU, bộ nhớ hoặc I/O.

### 28.1. Xem EXPLAIN

```sql
EXPLAIN
SELECT
    event_id,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_sum
FROM window_frame_lab.events;
```

Để quan sát thực thi một câu SELECT:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    event_id,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg
FROM window_frame_lab.events;
```

`EXPLAIN ANALYZE` **thực thi câu lệnh**. Ở đây là SELECT thuần; không dùng nó tùy tiện trên DML production vì có thể thay đổi dữ liệu.

### 28.2. Những node cần quan sát

| Node / số liệu | Điều gợi ý |
| --- | --- |
| `Sort` | PostgreSQL đang sắp dữ liệu cho window hoặc kết quả |
| `Incremental Sort` | Có thể tận dụng một phần thứ tự đã có |
| `WindowAgg` | Node tính các biểu thức cửa sổ |
| `Index Scan` | Có thể tận dụng thứ tự từ index phù hợp |
| `Buffers` | Hoạt động bộ đệm/I/O |
| `Disk: ...` ở sort hoặc temporary I/O | Dấu hiệu cần chú ý dữ liệu tràn bộ nhớ |
| `actual rows` | Số hàng thực tế đi qua node |
| `Execution Time` | Thời gian thực thi được đo |
| `loops` | Số vòng thực thi node theo instrument |

Một kế hoạch thực thi phụ thuộc phiên bản PostgreSQL, dữ liệu, statistics, cấu hình và các window khác trong cùng truy vấn.

### 28.3. Index hỗ trợ thứ tự

Ví dụ index:

```sql
CREATE INDEX idx_events_account_day_event
ON window_frame_lab.events (
    account_id,
    day_no,
    event_id
);
```

Index này có thể hữu ích cho những truy vấn:

```sql
PARTITION BY account_id
ORDER BY day_no, event_id
```

đặc biệt khi có filter theo account. Nhưng nó **không bảo đảm** planner luôn tránh Sort hoặc luôn chọn Index Scan. Với 10 hàng trong lab, quét tuần tự rồi sort có thể rẻ hơn.

Nếu workload dùng `RANGE`/`GROUPS` với `ORDER BY day_no`, một index có tiền tố `(account_id, day_no)` cũng có thể đáng cân nhắc. Chọn index theo truy vấn thực tế, không tạo index cho mọi frame thử nghiệm.

### 28.4. Khung rộng và dữ liệu peer lớn

Một window với:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

có thể nhận một peer group gồm hàng triệu dòng nếu khóa ORDER BY có ít giá trị phân biệt.

Một window với:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

cũng yêu cầu kết quả phụ thuộc toàn partition.

Tùy loại hàm/frame, PostgreSQL có thể phải giữ thêm dữ liệu để truy cập lại các hàng của partition, đặc biệt với `LAST_VALUE`/`NTH_VALUE` hoặc frame nhìn xa về phía sau. Điều này có thể tác động bộ nhớ và spill ra tệp tạm.

Không kết luận chỉ dựa trên số offset rằng “ROWS 2 PRECEDING chắc chắn chỉ tốn ba hàng bộ nhớ” cho mọi plan. Trước tiên xem `EXPLAIN (ANALYZE, BUFFERS)` và tình trạng bộ nhớ thực tế.

### 28.5. Tương đương về ngữ nghĩa trước, tối ưu sau

Thay `RANGE` bằng `ROWS` chỉ vì thấy một plan nhanh hơn có thể **đổi câu hỏi nghiệp vụ**. Thay `ORDER BY day_no` bằng `ORDER BY day_no,event_id` có thể làm peer group biến mất.

Một tối ưu hợp lệ phải giữ nguyên:

- Định nghĩa partition.
- Ý nghĩa đơn vị frame.
- Chính sách peer/tie.
- Cách xử lý NULL và hàng biên.
- Số hàng đầu ra.
- Kết quả tính toán trong những trường hợp dữ liệu biên.

---

## 29. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / triệu chứng | Nguyên nhân | Cách hiểu hoặc sửa |
| --- | --- | --- |
| “ROWS 2 PRECEDING là hai ngày trước.” | ROWS đếm **hàng**, không đếm ngày | Dùng RANGE theo giá trị ngày/thời gian |
| “GROUPS 2 PRECEDING là hai hàng trước.” | GROUPS đếm **peer group** | Kiểm tra các nhóm do ORDER BY tạo |
| “RANGE 2 PRECEDING là hai nhóm trước.” | RANGE đo khoảng **giá trị** | Nếu muốn nhóm trước, chọn GROUPS |
| “CURRENT ROW luôn một hàng.” | RANGE/GROUPS CURRENT ROW gồm peers | Xem kiểu frame |
| “ORDER BY cuối SELECT quyết định ROWS.” | ORDER BY của window độc lập | Ghi ORDER BY trong OVER đủ tie-breaker |
| “Mặc định SUM OVER ORDER BY là lũy kế từng event.” | Frame mặc định là RANGE tới cuối peer | Dùng ROWS tường minh |
| “Không có ORDER BY thì SUM vẫn chạy theo từng hàng.” | Mặc định frame phủ toàn partition | Thêm ORDER BY và frame phù hợp |
| “LAST_VALUE là giá trị cuối toàn partition.” | LAST_VALUE đọc cuối **frame**, không phải luôn partition | Dùng UNBOUNDED FOLLOWING khi cần |
| “LAG bị chặn bởi frame CURRENT ROW.” | LAG đọc vị trí trong partition | Phân biệt hàm frame-sensitive |
| “GROUPS giống GROUP BY.” | GROUP BY làm mất hàng chi tiết; GROUPS không | Xác định grain của kết quả |
| “Thêm event_id vào GROUPS không đổi ý nghĩa.” | Peer group phụ thuộc tất cả khóa ORDER BY | Giữ đúng khóa nhóm |
| “RANGE offset với hai khóa ORDER BY là hợp lệ.” | PostgreSQL yêu cầu một khóa để đo khoảng offset | Chỉ dùng một khóa phù hợp |
| “RANGE timestamp offset số 2 là hai ngày.” | Offset cần kiểu tương thích | Dùng INTERVAL được xác định |
| “DESC PRECEDING luôn là giá trị nhỏ hơn.” | PRECEDING theo thứ tự sắp xếp | Kiểm tra hướng ASC/DESC |
| “Khung trượt luôn đủ N hàng.” | Bị giới hạn bởi đầu/cuối partition | Xem COUNT(*) OVER cùng frame |
| “SUM frame rỗng là 0.” | SUM trên frame không hàng là NULL | COALESCE khi nghiệp vụ phù hợp |
| “EXCLUDE TIES loại cả current row.” | TIES giữ current, loại peers khác | Phân biệt GROUP/TIES/CURRENT ROW |
| “EXCLUDE GROUP chỉ có tác dụng với GROUPS.” | Exclusion là tùy chọn của frame các dạng hỗ trợ | Hiểu peer theo ORDER BY |
| “WHERE ngoài cùng không tác động window.” | WHERE cùng query block lọc đầu vào trước window | Dùng CTE nếu muốn tính trước rồi lọc |
| “FILTER và WHERE luôn tương đương.” | FILTER giới hạn giá trị aggregate trong frame, WHERE xóa hàng nguồn | Xác định bước muốn lọc |
| “Hàng NULL trong ORDER BY không có peer.” | Các NULL sort-key có thể tạo một peer group | Quy định NULLS FIRST/LAST và chính sách NULL |
| “ROWS sẽ luôn nhanh hơn RANGE.” | Hiệu năng phụ thuộc plan, index và kích thước dữ liệu | Đo EXPLAIN thay vì đoán |
| “Một window tốt để dự báo luôn được dùng FOLLOWING.” | FOLLOWING có thể đưa dữ liệu tương lai vào mô hình | Tránh data leakage theo thời điểm quyết định |

---

## 30. Bài tập thực hành

### Bài 1 — Mặc định có ORDER BY

Trên bảng `window_frame_lab.events`, tính:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no
)
```

Dự đoán kết quả các event 102 và 103. Vì sao chúng cùng nhận giá trị 60?

### Bài 2 — ROWS lũy kế xác định

Viết tổng lũy kế **từng event** bằng:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Kết hợp `ORDER BY day_no,event_id`. Với A, kết quả lũy kế lần lượt phải là 10,30,60,100,105,155.

### Bài 3 — So sánh ba loại frame

Tính tổng cho A với:

1. `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW`.
2. `RANGE BETWEEN 2 PRECEDING AND CURRENT ROW`.
3. `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW`.

Giải thích vì sao ở event 106 kết quả lần lượt là **55**, **50**, **95**.

### Bài 4 — Peer group CURRENT ROW

Viết ba cột:

```sql
ROWS BETWEEN CURRENT ROW AND CURRENT ROW
RANGE BETWEEN CURRENT ROW AND CURRENT ROW
GROUPS BETWEEN CURRENT ROW AND CURRENT ROW
```

Vì sao ở event 102 kết quả có thể là 20,50,50 khi dùng ORDER BY phù hợp?

### Bài 5 — Trung bình ba event

Tính `AVG(amount)` trên tối đa ba event gần nhất, có tie-breaker event_id. Thêm `COUNT(*)` với cùng frame. Vì sao ở event đầu chỉ có một observation?

### Bài 6 — Hai ngày và hai nhóm có giao dịch

Tại day_no=8 của account A:

- `RANGE 2 PRECEDING` xét những ngày nào?
- `GROUPS 1 PRECEDING` xét những peer group nào?

Viết SQL và giải thích kết quả khác nhau dù cả hai đều “nhìn về trước”.

### Bài 7 — FOLLOWING

Tính tổng của **hai event tiếp theo**, không gồm current row:

```sql
ROWS BETWEEN 1 FOLLOWING AND 2 FOLLOWING
```

Dự đoán tổng ở event 101,105,106; giải thích `NULL` ở frame rỗng.

### Bài 8 — Khung đối xứng theo group

Dùng:

```sql
GROUPS BETWEEN 1 PRECEDING AND 1 FOLLOWING
```

Tính tổng ở peer group ngày 2 và ngày 4 của A. Vì sao ngày 2 có 105, còn ngày 4 có 145?

### Bài 9 — EXCLUDE CURRENT ROW

Tại event 102, tính SUM trong:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
EXCLUDE CURRENT ROW
```

Vì sao vẫn có amount của event 103 cùng ngày 2?

### Bài 10 — EXCLUDE GROUP và TIES

Dùng dữ liệu A ngày 2 để so sánh:

- `EXCLUDE GROUP`.
- `EXCLUDE TIES`.

Giải thích tại sao với event 102, tổng tương ứng là 10 và 30.

### Bài 11 — LAST_VALUE

Chạy:

```sql
LAST_VALUE(day_no) OVER (
    PARTITION BY account_id
    ORDER BY day_no
)
```

Sau đó dùng:

```sql
LAST_VALUE(day_no) OVER (
    PARTITION BY account_id
    ORDER BY day_no
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

Vì sao cách thứ nhất không trả ngày 8 cho mọi event A?

### Bài 12 — LAG với frame cực hẹp

Viết `LAG(amount)` và `SUM(amount)` cùng frame:

```sql
ROWS BETWEEN CURRENT ROW AND CURRENT ROW
```

Tại event 102, vì sao LAG vẫn tìm được amount 10 của event 101?

### Bài 13 — FILTER khác WHERE

Tính tổng những amount ≥20 trong ba event gần nhất, rồi so sánh với cách loại event amount <20 ở WHERE trước khi tính window.

Tại event 106, giải thích kết quả khác nhau giữa hai cách.

### Bài 14 — Timestamp và INTERVAL

Dùng `event_at` để tính SUM của các event trong hai ngày trở lại, theo:

```sql
ORDER BY event_at
RANGE BETWEEN INTERVAL '2 days' PRECEDING
          AND CURRENT ROW
```

Vì sao event ngày 8 không tính sự kiện ngày 4? Nếu timestamp có DST theo múi giờ địa phương, cần kiểm tra điều gì?

### Bài 15 — Nhóm theo ngày trước rồi window

Viết CTE `day_totals` dùng:

```sql
GROUP BY account_id, day_no
```

Sau đó tính rolling total bằng:

```sql
ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
```

ở bảng đã tổng hợp. Kết quả có giống `GROUPS 1 PRECEDING` trên dữ liệu chi tiết khi quy về mỗi ngày không? Giải thích **khác nhau về số hàng đầu ra**.

### Bài 16 — Tổng quá khứ loại current row

Tính:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no, event_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
)
```

Ở event 101, kết quả là gì? Khi nào nên dùng `COALESCE(...,0)`?

### Bài 17 — DESC đảo nghĩa PRECEDING/FOLLOWING

Viết hai truy vấn RANGE offset trên `day_no`:

1. `ORDER BY day_no ASC`.
2. `ORDER BY day_no DESC`.

Giải thích vì sao “1 PRECEDING” nằm ở hai phía số học khác nhau.

### Bài 18 — Khóa tie-breaker thay đổi peer group

So sánh:

```sql
ORDER BY day_no
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
```

với:

```sql
ORDER BY day_no, event_id
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
```

Vì sao cách thứ hai không còn gom các event 102 và 103 vào cùng peer group?

### Bài 19 — Tính trước rồi lọc kết quả

Tạo CTE tính tổng lũy kế mọi event account A, sau đó ở query ngoài chỉ giữ `day_no >= 2`.

So sánh với đặt `WHERE day_no >= 2` ở query đang tính window. Tại event 102, vì sao một cách có thể cho 30 và cách còn lại cho 20?

### Bài 20 — EXPLAIN và index

Tạo index:

```sql
CREATE INDEX idx_events_account_day_event
ON window_frame_lab.events(account_id, day_no, event_id);
```

Dùng `EXPLAIN (ANALYZE, BUFFERS)` với moving sum `ROWS 2 PRECEDING`. Vì sao planner vẫn có thể chọn sequential scan và sort trên bảng chỉ có 10 hàng?

### Bài 21 — NULL ở khóa sắp xếp

Giả sử có các hàng với `score IS NULL`. Thiết kế `GROUPS BETWEEN CURRENT ROW AND CURRENT ROW` trên `ORDER BY score NULLS LAST`.

Những hàng NULL được xếp như thế nào theo peer group? Có nên tự đổi NULL thành 0 nếu 0 cũng là giá trị điểm hợp lệ không?

### Bài 22 — Đặc tả một chỉ số nghiệp vụ

Một dashboard muốn:

> Với từng giao dịch, hiển thị tổng doanh số của **bảy ngày lịch gần nhất tính tới thời điểm giao dịch**, bao gồm mọi giao dịch cùng timestamp.

Bạn sẽ chọn ROWS, RANGE hay GROUPS? Giải thích cách diễn đạt offset thời gian, chính sách timezone, xử lý peer và kiểm thử tại ngày có nhiều giao dịch.

### Bài 23 — Đặc tả khác: ba phiên giao dịch gần nhất

Một công ty không giao dịch mỗi ngày. Yêu cầu:

> Với từng dòng chi tiết, hiển thị tổng doanh số của **ba ngày có phát sinh giao dịch gần nhất**, kể cả ngày hiện tại.

Nên chọn frame gì nếu muốn giữ từng giao dịch chi tiết? Trong trường hợp nào cần GROUP BY ngày trước rồi dùng ROWS?

### Bài 24 — Empty frame và EXCLUDE

Dùng `EXCLUDE GROUP` trên frame RANGE lũy kế của account A. Tại event đầu tiên:

- `SUM(amount)` trả gì?
- `COUNT(*)` trả gì?
- Có nên coi hai kết quả đó là lỗi SQL không?

---

## 31. Checklist thiết kế window frame đáng tin cậy

| Câu hỏi | Cách quyết định |
| --- | --- |
| Partition được chia theo gì? | `PARTITION BY` đúng khóa nghiệp vụ |
| Có cần thứ tự để tính không? | `ORDER BY` trong `OVER` |
| Đơn vị “N trước” là gì? | Hàng → ROWS; giá trị → RANGE; peer group → GROUPS |
| Các hàng có đồng hạng không? | Kiểm tra tất cả biểu thức ORDER BY |
| ROWS cần kết quả tái lập? | Có tie-breaker ổn định |
| GROUPS muốn nhóm theo ngày? | Chỉ ORDER BY khóa ngày/group đúng mục tiêu |
| RANGE offset dùng kiểu gì? | Numeric key hoặc INTERVAL cho thời gian |
| RANGE offset có nhiều khóa ORDER BY? | PostgreSQL yêu cầu một khóa phù hợp |
| Có dùng ASC/DESC? | PRECEDING/FOLLOWING theo hướng sort |
| CURRENT ROW là hàng hay peer group? | ROWS so với RANGE/GROUPS |
| Có khai báo frame chưa? | Nếu không, xem mặc định với ORDER BY |
| Cần tổng cả partition? | Frame toàn partition hoặc bỏ ORDER BY |
| Dùng LAST_VALUE? | Kiểm tra frame end; thường cần UNBOUNDED FOLLOWING |
| Dùng LAG/LEAD/RANK? | Không suy diễn chúng bị giới hạn như SUM |
| Có cần bỏ current/peer? | EXCLUDE CURRENT ROW/GROUP/TIES |
| Có thể frame rỗng? | COUNT=0, SUM/AVG có thể NULL |
| Có dùng FILTER? | Phân biệt lọc aggregate và WHERE input |
| Có lọc kết quả window? | Dùng CTE/derived table để tính trước |
| Có trộn ngày lịch và ngày hoạt động? | RANGE/calendar khác GROUPS/ROWS sau GROUP BY |
| Có timezone/DST? | Xác định thời gian tuyệt đối và kỳ nghiệp vụ |
| Có peer với khóa NULL? | Chính sách NULLS FIRST/LAST rõ ràng |
| Nhiều phép window dùng cùng frame? | Đặt tên WINDOW hoặc lặp định nghĩa chính xác |
| Query chậm? | EXPLAIN, Sort, WindowAgg, buffers, statistics |
| Có index phù hợp? | Index theo partition/order, đo plan thực tế |
| Có dùng FOLLOWING trong dự báo? | Kiểm tra nguy cơ nhìn dữ liệu tương lai |
| Có thử dữ liệu biên? | Peer, ngày trống, đầu/cuối partition, NULL, frame rỗng |

## Kết luận

Trong PostgreSQL, **frame là phần quyết định phạm vi dữ liệu mà một số window function thực sự tổng hợp hoặc đọc tại mỗi hàng**. Cùng một `SUM(amount) OVER (...)` có thể cho kết quả rất khác nếu bạn thay `ROWS`, `RANGE` hoặc `GROUPS`.

Những nguyên tắc cần nhớ:

- **`ROWS`** đếm hàng trong thứ tự window. Hãy có tie-breaker khi cần tổng lũy kế từng event hoặc moving average ổn định.
- **`RANGE`** xét giá trị khóa sắp xếp; với offset, nó cần khóa và loại offset phù hợp, đặc biệt `INTERVAL` cho thời gian. Nó có thể bao gồm nhiều hàng cùng timestamp hay ngày.
- **`GROUPS`** đếm nhóm peer dựa trên `ORDER BY`, không phải số hàng và cũng không phải khoảng thời gian tuyệt đối.
- **`CURRENT ROW`** của RANGE/GROUPS có thể là **cả peer group**, khác CURRENT ROW của ROWS.
- Khi có ORDER BY nhưng không có frame tường minh, PostgreSQL thường dùng **RANGE từ đầu partition đến cuối peer hiện tại**. Đây là lý do những hàng đồng hạng nhận cùng tổng và `LAST_VALUE` không mặc định trả giá trị cuối toàn partition.
- Các tùy chọn **`EXCLUDE CURRENT ROW`, `EXCLUDE GROUP` và `EXCLUDE TIES`** cho phép loại chính hàng hiện tại hoặc peer khỏi frame mà vẫn giữ hàng kết quả.
- `SUM`, `AVG`, `FIRST_VALUE`, `LAST_VALUE` và `NTH_VALUE` nhạy cảm với frame; còn `RANK`, `ROW_NUMBER`, `LAG` và `LEAD` chủ yếu dựa trên partition/thứ tự.
- **Đúng về cú pháp chưa đủ**: cần xác định đơn vị thời gian, chính sách đồng hạng, giá trị NULL, ranh giới đầu/cuối, và thứ tự xử lý WHERE trước window.

Nếu mô tả rõ “**mấy hàng, mấy đơn vị giá trị hay mấy nhóm đồng hạng?**”, bạn sẽ chọn được window frame phù hợp, giải thích được từng con số và viết truy vấn phân tích nhất quán ngay cả khi dữ liệu có ngày trống, sự kiện trùng mốc hoặc nhiều partition.
