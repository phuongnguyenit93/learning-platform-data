# ROWS, RANGE và GROUPS theo khả năng hỗ trợ

Trong SQL, **hàm cửa sổ** (*window function*) cho phép tính toán trên các hàng có liên quan đến một hàng hiện tại mà không nhất thiết gom chúng thành một hàng như `GROUP BY`. Ví dụ, một danh sách giao dịch có thể vừa giữ từng giao dịch, vừa hiển thị **tổng lũy kế**, **trung bình trượt**, **tổng của các giao dịch gần thời điểm hiện tại** hoặc **tổng của các nhóm giá trị đồng hạng**.

Để xác định **những hàng nào được tính vào phép tổng hợp cửa sổ tại mỗi hàng hiện tại**, SQL có khái niệm **window frame** (*khung cửa sổ*). Ba chế độ xác định frame cần phân biệt là:

- **`ROWS`**: dịch ranh giới theo **số hàng trong thứ tự của cửa sổ**.
- **`RANGE`**: dịch ranh giới theo **giá trị của biểu thức sắp xếp**, hoặc xác định ranh giới theo **nhóm hàng có giá trị sắp xếp bằng nhau** (*peers*).
- **`GROUPS`**: dịch ranh giới theo **số nhóm peer**, không theo số hàng đơn lẻ và cũng không theo khoảng cách số học giữa các giá trị.

Ba chế độ này có thể cho cùng kết quả khi cột sắp xếp không có giá trị trùng và khoảng cách giữa các giá trị đều nhau, nhưng có thể khác rất lớn khi **nhiều hàng trùng khóa sắp xếp** hoặc **các khóa có khoảng trống**. Không chỉ ngữ nghĩa khác nhau: mức **hỗ trợ `ROWS`, `RANGE`, `GROUPS`, offset và `EXCLUDE`** cũng khác giữa PostgreSQL, SQL Server, MySQL, SQLite, Oracle, BigQuery và các hệ quản trị khác.

Bài học thuộc chương **Hàm cửa sổ** của **Database SQL**. Ví dụ chính dùng **PostgreSQL**, được tạo trong một phiên với bảng tạm độc lập. Những ví dụ cho hệ khác được ghi nhãn; không nên sao chép nguyên cú pháp của PostgreSQL sang mọi hệ mà chưa kiểm tra phiên bản và các ràng buộc của dialect.

## 1. Phân biệt PARTITION, ORDER BY và FRAME

Một hàm tổng hợp cửa sổ thường được viết:

```sql
SUM(amount) OVER (
    PARTITION BY channel
    ORDER BY score
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

Ba phần không có cùng vai trò:

| Thành phần | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| `PARTITION BY` | Những hàng nào thuộc **cùng vùng tính toán**? | Các sự kiện trong cùng `channel` |
| `ORDER BY` trong `OVER` | Những hàng đó được **sắp theo thứ tự nào**? | `score` tăng dần |
| Frame `ROWS` / `RANGE` / `GROUPS` | Với **mỗi hàng hiện tại**, phần nào của partition được tính vào hàm dùng frame? | Hai hàng trước và hàng hiện tại |

Nếu một partition có 100 hàng, **không có nghĩa frame tại một hàng luôn chứa cả 100 hàng**. Frame có thể chỉ chứa một hàng, một nhóm peer, vài nhóm liền trước hoặc toàn bộ partition, tùy ranh giới được chỉ định.

### 1.1. GROUP BY khác frame cửa sổ

```sql
SELECT channel, SUM(amount) AS channel_total
FROM events
GROUP BY channel;
```

Truy vấn tổng hợp thông thường này tạo **một hàng cho mỗi channel**. Trái lại:

```sql
SELECT
    event_id,
    channel,
    amount,
    SUM(amount) OVER (PARTITION BY channel) AS channel_total
FROM events;
```

có thể giữ **mỗi sự kiện một hàng** và lặp tổng của channel trên từng sự kiện. Thêm frame theo ORDER BY sẽ khiến tổng của từng hàng chỉ xét một **phần** của channel.

### 1.2. ORDER BY của window khác ORDER BY kết quả cuối

```sql
SELECT
    event_id,
    score,
    SUM(amount) OVER (
        ORDER BY score, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount
FROM events
ORDER BY event_id DESC;
```

`ORDER BY score, event_id` **trong `OVER`** quyết định thứ tự lũy kế. `ORDER BY event_id DESC` **ngoài SELECT** chỉ quyết định thứ tự hiển thị các hàng đã có chỉ số. Không thể thay ORDER BY trong OVER bằng ORDER BY cuối câu rồi mong phép tính giữ nguyên.

## 2. Tạo dữ liệu với giá trị trùng và khoảng trống

Để thấy rõ khác biệt, dùng bảng tạm PostgreSQL có hai kênh **A** và **B**. Mỗi hàng là một sự kiện, cột `score` là khóa sắp xếp dạng số nguyên, còn `amount` là giá trị cần tính tổng:

```sql
CREATE TEMP TABLE demo_frame_events (
    event_id INTEGER PRIMARY KEY,
    channel TEXT NOT NULL,
    score INTEGER NOT NULL,
    event_day DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO demo_frame_events
    (event_id, channel, score, event_day, amount)
VALUES
    (101, 'A', 1, DATE '2026-10-01', 10.00),
    (102, 'A', 1, DATE '2026-10-01', 20.00),
    (103, 'A', 2, DATE '2026-10-02', 30.00),
    (104, 'A', 4, DATE '2026-10-04', 40.00),
    (105, 'A', 4, DATE '2026-10-04', 50.00),
    (106, 'A', 7, DATE '2026-10-07', 60.00),
    (201, 'B', 1, DATE '2026-10-01',  5.00),
    (202, 'B', 3, DATE '2026-10-03', 15.00),
    (203, 'B', 3, DATE '2026-10-03', 25.00),
    (204, 'B', 6, DATE '2026-10-06', 35.00);
```

Kiểm tra dữ liệu kênh A:

```sql
SELECT event_id, channel, score, event_day, amount
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

| Vị trí khi sắp theo `(score, event_id)` | event_id | score | event_day | amount |
| ---: | ---: | ---: | --- | ---: |
| 1 | 101 | 1 | 2026-10-01 | 10.00 |
| 2 | 102 | 1 | 2026-10-01 | 20.00 |
| 3 | 103 | 2 | 2026-10-02 | 30.00 |
| 4 | 104 | 4 | 2026-10-04 | 40.00 |
| 5 | 105 | 4 | 2026-10-04 | 50.00 |
| 6 | 106 | 7 | 2026-10-07 | 60.00 |

Tổng `amount` của kênh A là **210.00**. Các giá trị score phân biệt là **1, 2, 4, 7**; score 1 có **hai hàng**, score 4 có **hai hàng**. Không có score 3, 5 hoặc 6 trong kênh A.

Đối với kênh B, các score là **1, 3, 3, 6**, tổng amount là **80.00**. Hai kênh sẽ hỗ trợ minh họa `PARTITION BY`.

## 3. Peer group: nền tảng để hiểu RANGE và GROUPS

**Peer** là những hàng có **toàn bộ giá trị trong danh sách `ORDER BY` của window bằng nhau** theo quy tắc so sánh tương ứng. Các peer tạo thành một **peer group**.

Nếu window chỉ sắp:

```sql
ORDER BY score
```

kênh A có bốn nhóm:

```text
Nhóm G1          Nhóm G2        Nhóm G3          Nhóm G4
score = 1        score = 2      score = 4        score = 7
 101: 10           103: 30        104: 40          106: 60
 102: 20                          105: 50
 --------         --------       --------         --------
 tổng: 30         tổng: 30       tổng: 90         tổng: 60
```

Giữa các nhóm có khoảng trống về **giá trị số**: từ score 2 tới 4 chênh 2; từ 4 tới 7 chênh 3. Những khoảng trống này **quan trọng đối với RANGE có offset**, nhưng **không làm tăng số nhóm đối với GROUPS**.

Nếu window sắp theo:

```sql
ORDER BY score, event_id
```

thì mỗi hàng trong dữ liệu mẫu có khóa sắp xếp khác nhau, vì `event_id` duy nhất. Các hàng score 1 **không còn là peer của nhau theo toàn bộ ORDER BY** trong window đó.

**Khi muốn nhóm đồng hạng theo score, đừng vô tình thêm event_id vào ORDER BY của RANGE/GROUPS rồi kỳ vọng nhóm peer vẫn gồm mọi hàng cùng score.** Khóa phụ hữu ích để làm `ROWS` xác định, nhưng nó cũng thay đổi định nghĩa peer nếu được dùng trong các cửa sổ khác.

## 4. Cú pháp frame và ý nghĩa các ranh giới

Dạng thông dụng:

```sql
aggregate_function(...) OVER (
    PARTITION BY ...
    ORDER BY ...
    ROWS BETWEEN frame_start AND frame_end
)
```

Thay `ROWS` bằng `RANGE` hoặc `GROUPS` nếu DBMS hỗ trợ dạng frame và các ranh giới tương ứng.

Các ký hiệu thường gặp:

| Ranh giới | Ý nghĩa khái quát |
| --- | --- |
| `UNBOUNDED PRECEDING` | Từ điểm đầu phù hợp của partition |
| `n PRECEDING` | Đi lùi `n` hàng / đơn vị giá trị / nhóm, tùy chế độ |
| `CURRENT ROW` | Tại hàng hiện tại với ROWS; tại nhóm peer hiện tại với RANGE/GROUPS |
| `n FOLLOWING` | Đi tới `n` hàng / đơn vị giá trị / nhóm, tùy chế độ |
| `UNBOUNDED FOLLOWING` | Tới điểm cuối phù hợp của partition |

Ví dụ:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

là tổng lũy kế đến **hàng hiện tại** theo thứ tự ROWS.

```sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
```

lấy **tối đa ba hàng**: hai hàng trước cùng hàng hiện tại.

```sql
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

với khóa ORDER BY dạng số tăng dần, lấy những hàng có khóa trong khoảng **từ giá trị hiện tại trừ 2 đến giá trị hiện tại**.

```sql
GROUPS BETWEEN 2 PRECEDING AND CURRENT ROW
```

lấy **nhóm peer hiện tại cùng tối đa hai nhóm peer đứng trước**, dù trong mỗi nhóm có một hay nhiều hàng.

### 4.1. Không phải cặp ranh giới nào cũng hợp lệ

Frame phải có thứ tự ranh giới hợp lý và tuân theo cú pháp DBMS. Ví dụ không thể tùy tiện yêu cầu bắt đầu ở `UNBOUNDED FOLLOWING` rồi kết thúc ở `CURRENT ROW`. Giá trị offset cần có kiểu và phạm vi hợp lệ; các hệ thường yêu cầu offset không âm và không NULL cho các chế độ tương ứng.

Nếu bỏ phần `AND ...` của `BETWEEN`, một số cú pháp có dạng rút gọn:

```sql
ROWS UNBOUNDED PRECEDING
```

thường tương ứng với:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Trong bài học, ưu tiên dùng `BETWEEN` đầy đủ để ranh giới rõ ràng.

## 5. ROWS: dịch frame theo số hàng thật trong thứ tự

`ROWS` không hỏi score hiện tại cách score trước **bao nhiêu đơn vị**. Nó chỉ nhìn **vị trí các hàng** sau khi sắp trong partition.

Ví dụ PostgreSQL:

```sql
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS sum_last_2_rows
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Kết quả:

| event_id | score | amount | sum_last_2_rows |
| ---: | ---: | ---: | ---: |
| 101 | 1 | 10.00 | **10.00** |
| 102 | 1 | 20.00 | **30.00** |
| 103 | 2 | 30.00 | **50.00** |
| 104 | 4 | 40.00 | **70.00** |
| 105 | 4 | 50.00 | **90.00** |
| 106 | 7 | 60.00 | **110.00** |

Diễn giải:

- Tại event 101, chưa có hàng trước, chỉ lấy 10.
- Tại event 102, lấy 10 của event 101 cộng 20 của 102.
- Tại event 103, lấy **20 của 102 + 30 của 103 = 50**; event 101 đã nằm ngoài frame.
- Tại event 104, lấy **30 của 103 + 40 của 104 = 70** dù score nhảy từ 2 lên 4.
- Tại event 106, lấy **50 của 105 + 60 của 106 = 110** dù score nhảy từ 4 lên 7.

Điểm chính: `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW` luôn tham chiếu **hàng liền trước theo ORDER BY**, không phải score trước một đơn vị.

### 5.1. Vì sao cần khóa phụ khi có giá trị trùng?

Nếu chỉ:

```sql
ORDER BY score
ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
```

thứ tự giữa event 101 và 102 (cùng score 1), hoặc giữa 104 và 105 (cùng score 4), **không được xác định** bởi ORDER BY. Khi đó việc hàng nào được xem là đứng trước có thể thay đổi theo kế hoạch thực thi. Với một frame tính theo hàng như ROWS, kết quả trên từng event có thể không ổn định.

Thêm khóa phụ duy nhất:

```sql
ORDER BY score, event_id
```

để tạo thứ tự xác định. Đây thường là thói quen quan trọng trong running total theo **sự kiện**.

### 5.2. ROWS với hai phía của hàng hiện tại

```sql
SELECT
    event_id,
    amount,
    AVG(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS avg_neighbors
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Frame gồm **tối đa ba hàng**: hàng trước, hiện tại và hàng sau. Ở đầu/cuối partition, số hàng thực tế có thể nhỏ hơn ba; AVG chia cho số giá trị khác NULL thực có mặt, không tự bổ sung số 0 cho vị trí ngoài partition.

### 5.3. ROWS phù hợp với mục tiêu nào?

- Trung bình **ba giao dịch gần nhất**.
- Tổng giá trị của **năm dòng log liền trước**.
- Tổng lũy kế theo một thứ tự **duy nhất** của sự kiện.
- Tính số liệu trên một **số bản ghi cố định**, bất kể khoảng cách thời gian hoặc giá trị score giữa chúng.

Nếu nghiệp vụ nói **“trong vòng hai ngày trước”**, ROWS 2 PRECEDING **không trực tiếp diễn đạt** điều đó, vì hai hàng trước có thể cách nhau nhiều ngày.

## 6. RANGE: dịch theo giá trị khóa ORDER BY

`RANGE` đặc biệt hữu ích khi **khoảng cách giá trị** có ý nghĩa: score trong khoảng ±n, thời điểm trong một khoảng ngày/giờ, hoặc lũy kế theo giá trị sắp xếp. Với offset hữu hạn, các DBMS thường ràng buộc kiểu của ORDER BY và offset, và nhiều hệ yêu cầu **đúng một biểu thức ORDER BY**.

Ví dụ PostgreSQL:

```sql
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS sum_score_range_1
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Ở đây `RANGE 1 PRECEDING` với score tăng dần nghĩa là xét các hàng có:

```text
current_score - 1 <= score <= current_score
```

Kết quả:

| event_id | score | amount | sum_score_range_1 | Các score được tính |
| ---: | ---: | ---: | ---: | --- |
| 101 | 1 | 10.00 | **30.00** | Score 1: 10 + 20 |
| 102 | 1 | 20.00 | **30.00** | Score 1: 10 + 20 |
| 103 | 2 | 30.00 | **60.00** | Score 1 và 2: 10 + 20 + 30 |
| 104 | 4 | 40.00 | **90.00** | Score 3–4: 40 + 50 |
| 105 | 4 | 50.00 | **90.00** | Score 3–4: 40 + 50 |
| 106 | 7 | 60.00 | **60.00** | Score 6–7: chỉ 60 |

Tại score 4, score 2 **không nằm trong khoảng [3,4]**, nên bị loại mặc dù đó là **nhóm score đứng ngay trước**. Tại score 7, không có score 6, vì vậy frame chỉ chứa event 106.

### 6.1. RANGE bao gồm các peer cùng khóa

Event 101 và 102 cùng score 1, nên frame RANGE tại hai event có cùng ranh giới và thường chứa **cả hai**. Tương tự, event 104 và 105 cùng score 4 có cùng kết quả 90.00.

Đây không phải ngẫu nhiên: đối với `RANGE` với ORDER BY score, những hàng peer có cùng score được xử lý cùng theo ranh giới giá trị. Người viết không cần một bước ROW_NUMBER để chọn thứ tự giữa các peer chỉ nhằm tính tổng theo khoảng score.

### 6.2. Không được coi RANGE là “ROWS theo cách viết khác”

Đặt hai biểu thức cạnh nhau:

```sql
-- Đếm vị trí: một hàng trước.
SUM(amount) OVER (
    PARTITION BY channel
    ORDER BY score, event_id
    ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
)

-- Đếm khoảng cách score: một đơn vị trước.
SUM(amount) OVER (
    PARTITION BY channel
    ORDER BY score
    RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
)
```

Tại event 106, ROWS cho **110** (event 105 + 106), RANGE cho **60** (không có score 6). Hai kết quả đúng theo **hai định nghĩa frame khác nhau**.

### 6.3. RANGE với ngày hoặc timestamp trong PostgreSQL

Nếu cột ORDER BY là thời điểm hoặc ngày, có thể dùng offset khoảng thời gian phù hợp kiểu:

```sql
SELECT
    event_id,
    event_day,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY event_day
        RANGE BETWEEN INTERVAL '2 days' PRECEDING
                  AND CURRENT ROW
    ) AS amount_in_recent_2_day_range
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY event_day, event_id;
```

Trên PostgreSQL và bộ dữ liệu mẫu:

- Ở **ngày 2026-10-04**, frame lấy các hàng từ **2026-10-02 đến 2026-10-04**, gồm 30 + 40 + 50 = **120.00**.
- Ở **ngày 2026-10-07**, frame lấy ngày **2026-10-05 đến 2026-10-07**, chỉ có event 106 = **60.00**.
- Ở **ngày 2026-10-01**, cả hai event cùng ngày được tính trong frame, tổng **30.00**.

Cú pháp và kiểu offset ngày/giờ **khác nhau giữa các hệ**. Không dùng `INTERVAL '2 days'` nguyên văn trên mọi DBMS. Với `TIMESTAMPTZ`, ranh giới khoảng thời gian và cách diễn giải ngày lịch theo múi giờ cần được xác định theo yêu cầu nghiệp vụ.

### 6.4. Hạn chế của RANGE khi có offset

Trong PostgreSQL và nhiều hệ hỗ trợ `RANGE ... n PRECEDING/FOLLOWING`, frame theo khoảng cách giá trị thường yêu cầu **một** biểu thức ORDER BY. Ví dụ:

```sql
-- PostgreSQL: RANGE với offset 1 không dùng hai khóa ORDER BY.
SUM(amount) OVER (
    ORDER BY score, event_id
    RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
)
```

không phải cấu trúc hợp lệ cho yêu cầu khoảng cách score bằng 1, vì không rõ offset 1 phải tác động lên toàn bộ **cặp** `(score,event_id)` ra sao. Dùng `ORDER BY score` nếu khoảng cách được định nghĩa theo score, hoặc chọn cách mô hình hóa khác.

**Phân biệt:** một số dạng RANGE **không có offset hữu hạn** như `RANGE UNBOUNDED PRECEDING ... CURRENT ROW` có thể cho phép nhiều khóa ORDER BY tùy DBMS, vì frame dựa trên thứ tự và peer groups chứ không cần phép cộng/trừ offset trên cả bộ khóa.

### 6.5. Hướng DESC làm đổi ý nghĩa PRECEDING

`PRECEDING` và `FOLLOWING` nói về **vị trí trong thứ tự của window**, không đơn giản là giá trị số nhỏ hơn/lớn hơn:

```sql
ORDER BY score DESC
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

Với score giảm dần, những giá trị **đứng trước** score hiện tại có thể là **giá trị lớn hơn**; một khoảng RANGE hữu hạn phải được hiểu theo chiều sắp xếp. Đừng sao chép công thức `score - 2 <= ... <= score` của ASC sang DESC. Khi thiết kế báo cáo, nêu rõ đang xét **giá trị cao hơn, thấp hơn** hay **nằm trước/sau theo thứ tự**.

## 7. GROUPS: dịch theo số nhóm peer

`GROUPS` giải quyết một kiểu câu hỏi khác: **“tính nhóm hạng hiện tại và n nhóm hạng đứng trước/sau”**, trong đó mỗi nhóm có thể có nhiều hàng. Khoảng cách số học giữa hai khóa sắp xếp **không ảnh hưởng số nhóm**.

Ví dụ PostgreSQL phiên bản có hỗ trợ GROUPS:

```sql
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS sum_current_and_previous_score_group
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Kết quả:

| event_id | score | amount | sum_current_and_previous_score_group | Nhóm được tính |
| ---: | ---: | ---: | ---: | --- |
| 101 | 1 | 10.00 | **30.00** | Nhóm score 1 |
| 102 | 1 | 20.00 | **30.00** | Nhóm score 1 |
| 103 | 2 | 30.00 | **60.00** | Nhóm score 1 + 2 |
| 104 | 4 | 40.00 | **120.00** | Nhóm score 2 + 4 |
| 105 | 4 | 50.00 | **120.00** | Nhóm score 2 + 4 |
| 106 | 7 | 60.00 | **150.00** | Nhóm score 4 + 7 |

Ở score 4, nhóm trước là **score 2** (tổng 30), dù không có score 3; cộng nhóm hiện tại score 4 (90) được **120**. Ở score 7, nhóm trước là score 4 (90) nên tổng **150**. Đây là điểm khác `RANGE 1 PRECEDING`, vốn chỉ nhìn khoảng giá trị `[score - 1, score]`.

### 7.1. GROUPS không phải GROUP BY

- `GROUP BY score` sẽ gom các sự kiện có score giống nhau thành **một hàng mỗi score**.
- `GROUPS BETWEEN ...` trong window frame vẫn giữ **mỗi sự kiện một hàng**, nhưng frame mở rộng/lùi theo **nhóm peer**.

Tên gần giống nhau không có nghĩa hai chức năng giống nhau. Một truy vấn có thể dùng GROUP BY trong CTE rồi dùng `GROUPS` ở bước window tiếp theo, nhưng các nhóm GROUPS khi ấy được định nghĩa trên **những hàng đầu vào của bước window**, không tự truy lại các hàng nguồn trước CTE.

### 7.2. GROUPS có thể dùng nhiều biểu thức ORDER BY

Khác với `RANGE` có offset hữu hạn thường yêu cầu một khóa sắp xếp, `GROUPS` trên PostgreSQL có thể xác định peer bằng **nhiều biểu thức ORDER BY**:

```sql
SUM(amount) OVER (
    PARTITION BY channel
    ORDER BY score, event_day
    GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
)
```

Khi đó peer phải có cùng **score và event_day**. Nếu thêm `event_id` duy nhất vào ORDER BY thì mỗi peer group chỉ còn một hàng, và GROUPS sẽ có hành vi giống việc đếm theo hàng cho dữ liệu ấy. Vì vậy, danh sách ORDER BY phải theo **định nghĩa đồng hạng của nghiệp vụ**, không chỉ theo nhu cầu có thứ tự duy nhất.

### 7.3. Khi nào GROUPS phù hợp?

- Tổng của **nhóm điểm hiện tại và nhóm điểm ngay trước**.
- Trung bình của **ba mức giá phân biệt gần nhất**, mỗi mức có nhiều giao dịch.
- Phân tích hàng đồng hạng theo **một hoặc nhiều khóa sắp xếp**.
- Tổng theo những **nhóm peer liền kề**, không bị ảnh hưởng bởi khoảng trống giữa các giá trị số.

GROUPS không phải lúc nào cũng là “nhóm thời gian” theo lịch. Nếu dữ liệu chỉ có ngày 1, 4 và 7, GROUPS 1 PRECEDING xét **ngày có dữ liệu đứng trước**, không nhất thiết là **ngày lịch hôm qua**.

## 8. So sánh ba chế độ trên cùng một bộ dữ liệu

Đây là ví dụ trung tâm của bài. Ta đặt ba frame cạnh nhau với cùng `PARTITION BY channel`; phần ORDER BY của ROWS thêm khóa phụ `event_id` để kết quả theo hàng ổn định, còn RANGE/GROUPS chỉ ORDER BY score vì mục tiêu là **giá trị và nhóm đồng score**.

```sql
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS by_rows,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS by_range,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS by_groups
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

| event_id | score | amount | **ROWS** 1 trước | **RANGE** 1 trước | **GROUPS** 1 trước |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 10.00 | 10.00 | 30.00 | 30.00 |
| 102 | 1 | 20.00 | 30.00 | 30.00 | 30.00 |
| 103 | 2 | 30.00 | 50.00 | 60.00 | 60.00 |
| 104 | 4 | 40.00 | 70.00 | 90.00 | 120.00 |
| 105 | 4 | 50.00 | 90.00 | 90.00 | 120.00 |
| 106 | 7 | 60.00 | 110.00 | 60.00 | 150.00 |

Tại event 106:

```text
ROWS 1 PRECEDING:
    một HÀNG đứng trước: event 105 (50) + event 106 (60) = 110

RANGE 1 PRECEDING:
    khoảng SCORE [6,7]: chỉ event 106 (60) = 60

GROUPS 1 PRECEDING:
    một NHÓM PEER trước: nhóm score 4 (40+50)
    cộng nhóm hiện tại score 7 (60) = 150
```

**Không có một chế độ nào “đúng hơn” một cách tuyệt đối.** `ROWS` đúng khi nghiệp vụ đếm số giao dịch, `RANGE` đúng khi nghiệp vụ đếm khoảng giá trị score, và `GROUPS` đúng khi nghiệp vụ đếm số mức score phân biệt.

### 8.1. Bảng quy đổi ý nghĩa

| Frame | “1 PRECEDING” nghĩa là gì? | Khi có hai hàng cùng score | Khi thiếu score ở giữa |
| --- | --- | --- | --- |
| `ROWS` | Một hàng trong thứ tự | Chỉ lấy đúng số hàng quy định; cần thứ tự ổn định | Không ảnh hưởng bước đếm |
| `RANGE` | Một đơn vị giá trị theo ORDER BY số | Thường đưa toàn bộ peers cùng score vào frame | Khoảng trống có thể làm frame không chứa hàng trước |
| `GROUPS` | Một nhóm peer đứng trước | Lấy cả peer group | Vẫn lấy nhóm đứng trước, dù cách xa về giá trị |

## 9. CURRENT ROW có ba ý nghĩa cần chú ý

Một bẫy quan trọng là `CURRENT ROW` không có cùng phạm vi trong mọi chế độ.

### 9.1. ROWS CURRENT ROW chỉ chứa hàng hiện tại

```sql
SUM(amount) OVER (
    PARTITION BY channel
    ORDER BY score, event_id
    ROWS BETWEEN CURRENT ROW AND CURRENT ROW
)
```

Vì mỗi frame chỉ gồm hàng hiện tại, kết quả bằng `amount` của hàng đó (nếu amount không NULL).

### 9.2. RANGE CURRENT ROW lấy cả peer group

```sql
SUM(amount) OVER (
    PARTITION BY channel
    ORDER BY score
    RANGE BETWEEN CURRENT ROW AND CURRENT ROW
)
```

Tại event 101 và 102, frame của mỗi hàng chứa **cả hai** event score 1 nên trả **30**. Tại event 104 và 105, mỗi frame trả **90**.

### 9.3. GROUPS CURRENT ROW cũng lấy cả peer group

```sql
SUM(amount) OVER (
    PARTITION BY channel
    ORDER BY score
    GROUPS BETWEEN CURRENT ROW AND CURRENT ROW
)
```

Với cùng ORDER BY score, kết quả của frame này giống ví dụ RANGE CURRENT ROW ở trên vì cả hai đều chọn nhóm peer hiện tại.

| event_id | score | ROWS CURRENT ROW | RANGE CURRENT ROW | GROUPS CURRENT ROW |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 10.00 | 30.00 | 30.00 |
| 102 | 1 | 20.00 | 30.00 | 30.00 |
| 103 | 2 | 30.00 | 30.00 | 30.00 |
| 104 | 4 | 40.00 | 90.00 | 90.00 |
| 105 | 4 | 50.00 | 90.00 | 90.00 |
| 106 | 7 | 60.00 | 60.00 | 60.00 |

**Hàng hiện tại** và **nhóm peer hiện tại** là hai khái niệm khác nhau. Khi kết quả RANGE/GROUPS ở một hàng có vẻ “tính luôn hàng bên cạnh”, hãy kiểm tra xem hàng bên cạnh có cùng khóa ORDER BY hay không.

## 10. Frame mặc định: nguyên nhân thường gặp của kết quả bất ngờ

Trong PostgreSQL, đối với một hàm tổng hợp dùng window frame:

- Có `ORDER BY` trong OVER nhưng **không chỉ rõ frame**: hành vi mặc định tương ứng với `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, bao gồm các peer của hàng hiện tại.
- Không có ORDER BY trong OVER: frame mặc định bao phủ **toàn bộ partition**.

Ví dụ:

```sql
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
    ) AS default_running_sum
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Với kênh A, kết quả:

| event_id | score | default_running_sum |
| ---: | ---: | ---: |
| 101 | 1 | 30.00 |
| 102 | 1 | 30.00 |
| 103 | 2 | 60.00 |
| 104 | 4 | 150.00 |
| 105 | 4 | 150.00 |
| 106 | 7 | 210.00 |

Ở score 1, cả hai hàng cùng nhận **30**, không phải 10 rồi 30 như `ROWS` lũy kế theo từng event. Ở score 4, hai hàng cùng nhận **150**.

### 10.1. Ghi rõ ROWS nếu muốn tổng lũy kế từng sự kiện

```sql
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_by_event
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Kết quả **10, 30, 60, 100, 150, 210** theo event_id 101–106.

### 10.2. Không có ORDER BY: tổng toàn partition

```sql
SELECT
    event_id,
    channel,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
    ) AS full_channel_amount
FROM demo_frame_events
ORDER BY channel, event_id;
```

Mỗi hàng kênh A nhận **210**, mỗi hàng kênh B nhận **80**. Không có thứ tự để tạo “tới hiện tại”, nên phép tổng hợp với OVER chỉ PARTITION BY lấy tổng của cả partition.

### 10.3. Quy ước tốt khi cần độ chính xác

Với running total, moving average, FIRST_VALUE/LAST_VALUE hoặc các tính toán nhạy với frame, **viết ranh giới tường minh** thay vì mặc định người đọc nhớ chi tiết frame của DBMS.

Ở các dialect, quy tắc default frame và hạn chế cú pháp có thể khác. Hãy kiểm tra tài liệu của phiên bản DBMS trước khi dựa vào một default nhằm đảm bảo hành vi quan trọng.

## 11. So sánh lũy kế ROWS, RANGE và GROUPS

Nếu dùng ranh giới từ đầu partition đến CURRENT ROW:

```sql
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_rows,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_range,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_groups
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

| event_id | score | cumulative_rows | cumulative_range | cumulative_groups |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 10.00 | 30.00 | 30.00 |
| 102 | 1 | 30.00 | 30.00 | 30.00 |
| 103 | 2 | 60.00 | 60.00 | 60.00 |
| 104 | 4 | 100.00 | 150.00 | 150.00 |
| 105 | 4 | 150.00 | 150.00 | 150.00 |
| 106 | 7 | 210.00 | 210.00 | 210.00 |

Khi ranh giới là **UNBOUNDED PRECEDING đến CURRENT ROW**, RANGE và GROUPS có thể cho kết quả **giống nhau** với cùng ORDER BY vì cả hai đều lấy từ đầu tới **hết peer group hiện tại**. Nhưng khi có **offset hữu hạn** (`1 PRECEDING`, `2 FOLLOWING`), RANGE đếm **khoảng giá trị** còn GROUPS đếm **số nhóm** nên kết quả có thể khác.

**Không suy luận từ một ví dụ lũy kế trùng kết quả rằng RANGE và GROUPS luôn tương đương.**

## 12. FOLLOWING: cửa sổ nhìn về phía sau và phía trước

Không phải frame nào cũng kết thúc ở CURRENT ROW. Khi nghiên cứu tác động **trước/sau sự kiện**, có thể dùng FOLLOWING.

### 12.1. ROWS một hàng trước và một hàng sau

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS sum_3_neighboring_rows
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Tại event 103, frame gồm event 102 (20), 103 (30), 104 (40), tổng **90**. Không quan tâm score 2 tới 4 có khoảng trống; ROWS tính ba hàng lân cận.

### 12.2. RANGE từ score hiện tại tới cao hơn một đơn vị

```sql
SELECT
    event_id,
    score,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        RANGE BETWEEN CURRENT ROW AND 1 FOLLOWING
    ) AS sum_score_current_plus_one
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Ở score 1, frame gồm **score 1 và score 2**, tổng 10 + 20 + 30 = **60**. Ở score 2, không có score 3 nên chỉ có amount 30. Ở score 4, không có score 5, frame gồm hai hàng score 4, tổng 90.

### 12.3. GROUPS từ nhóm hiện tại tới nhóm kế tiếp

```sql
SELECT
    event_id,
    score,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN CURRENT ROW AND 1 FOLLOWING
    ) AS sum_this_and_next_peer_group
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Ở score 2, nhóm kế tiếp là score **4**, nên kết quả là **30 + 90 = 120** dù không có score 3. Ở score 4, nhóm kế tiếp là score **7**, tổng **90 + 60 = 150**.

FOLLOWING mở rộng sự phân biệt giữa **số hàng**, **khoảng cách giá trị** và **số nhóm** theo hướng đi sau hàng hiện tại.

## 13. Frame rỗng, NULL và COUNT khác SUM

Một frame có thể không chứa hàng nào. Ví dụ ở hàng đầu tiên:

```sql
SELECT
    event_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING
    ) AS previous_row_count,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING
    ) AS previous_row_amount
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Tại event 101, không có hàng trước:

- `COUNT(*)` trên frame rỗng trả **0**.
- `SUM(amount)` trên frame rỗng trả **NULL**, không phải số 0.

Tại event 102, frame là event 101 nên `previous_row_count = 1`, `previous_row_amount = 10.00`.

### 13.1. Amount NULL và frame không có hàng là hai tình huống khác

Trong dữ liệu mẫu, `amount NOT NULL`. Nhưng nếu một hệ thống thực cho phép amount NULL:

- `COUNT(*)` đếm số hàng trong frame, kể cả hàng có amount NULL.
- `COUNT(amount)` chỉ đếm hàng có amount **khác NULL**.
- `SUM(amount)` và `AVG(amount)` bỏ qua amount NULL, và trả NULL khi không có giá trị khác NULL.

`COALESCE(SUM(amount) OVER (...), 0)` có thể phù hợp khi không có sự kiện thì tổng bằng 0 theo nghiệp vụ. Nhưng nếu có sự kiện mà amount chưa biết, việc tự chuyển NULL thành 0 có thể che lấp vấn đề chất lượng dữ liệu. Có thể đi kèm một phép đếm số lượng amount thiếu.

### 13.2. Không dùng COUNT(*) sau JOIN để đếm bản ghi con

Nếu dữ liệu nguồn được LEFT JOIN và tạo hàng bù NULL, frame tính trên **những hàng đầu ra của JOIN**. `COUNT(*)` vẫn đếm hàng bù; `COUNT(child_id)` mới loại được hàng không có bản ghi con. Các chế độ ROWS/RANGE/GROUPS **không tự sửa bội số hoặc hàng bù do JOIN**.

## 14. LAST_VALUE và FIRST_VALUE: bẫy frame mặc định

Một lỗi rất thường gặp khi học window là:

```sql
SELECT
    event_id,
    score,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
    ) AS last_value_default_frame
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Người mới có thể kỳ vọng mọi hàng trả **60** (amount của event cuối kênh A), nhưng với ORDER BY duy nhất và frame mặc định kết thúc tại CURRENT ROW, `LAST_VALUE` thấy **hàng cuối của frame đến hiện tại**, chứ không phải hàng cuối của toàn partition. Kết quả mặc định trong ví dụ này thường bằng **amount của chính hàng hiện tại**.

Muốn lấy amount của hàng **cuối cùng trong toàn partition** theo thứ tự xác định:

```sql
SELECT
    event_id,
    score,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_amount_of_channel
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Mọi hàng A nhận **60.00**. Frame bao phủ toàn bộ partition, nên LAST_VALUE được phép nhìn tới event 106 dù đang tính ở event 101.

### 14.1. Những hàm nào thực sự nhạy với frame?

| Nhóm hàm | Frame ảnh hưởng như thế nào? |
| --- | --- |
| `SUM`, `AVG`, `MIN`, `MAX`, `COUNT` với `OVER` | Tính trên tập hàng thuộc frame |
| `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` | Thường nhạy với điểm đầu/cuối và phạm vi frame |
| `ROW_NUMBER`, `RANK`, `DENSE_RANK` | Thứ tự và peer groups quyết định kết quả; **không dùng frame theo cách của SUM** |
| `LAG`, `LEAD` | Lấy hàng trước/sau theo thứ tự partition; không đơn giản bị giới hạn bởi ROWS/RANGE/GROUPS frame như SUM |

Một số DBMS hạn chế việc chỉ định frame bên cạnh những hàm xếp hạng/điều hướng nhất định. Đừng thêm `GROUPS BETWEEN ...` vào ROW_NUMBER và mong nó sẽ đánh số theo nhóm: để đánh số nhóm đồng hạng, dùng `DENSE_RANK()` theo ORDER BY nghiệp vụ.

## 15. EXCLUDE: loại một phần của frame khi DBMS hỗ trợ

Một số hệ hỗ trợ cú pháp `EXCLUDE` để loại hàng cụ thể ra khỏi frame **sau khi đã xác định ranh giới**. Đây là tính năng thêm, **không đồng nghĩa với việc hệ có ROWS/RANGE/GROUPS thì tự có EXCLUDE**.

Trong PostgreSQL 11+:

```sql
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN CURRENT ROW AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS peer_amount_without_this_row
FROM demo_frame_events
WHERE channel = 'A'
ORDER BY score, event_id;
```

Frame ban đầu là **nhóm peer hiện tại**. `EXCLUDE CURRENT ROW` bỏ chính hàng đang tính nhưng vẫn giữ các peer khác:

- Event 101 có peer event 102: kết quả **20**.
- Event 102 có peer event 101: kết quả **10**.
- Event 103 không có peer khác: SUM trên frame rỗng là **NULL**.
- Event 104 còn event 105: kết quả **50**.
- Event 105 còn event 104: kết quả **40**.

Những lựa chọn EXCLUDE thường gặp:

| Tùy chọn | Ý nghĩa ở mức tổng quát |
| --- | --- |
| `EXCLUDE NO OTHERS` | Không loại hàng bổ sung khỏi frame |
| `EXCLUDE CURRENT ROW` | Loại hàng hiện tại |
| `EXCLUDE GROUP` | Loại **toàn bộ nhóm peer của hàng hiện tại**, kể cả hàng hiện tại |
| `EXCLUDE TIES` | Loại các peer **khác** nhưng vẫn giữ hàng hiện tại |

Ví dụ cùng frame peer hiện tại, `EXCLUDE GROUP` để lại frame rỗng; `EXCLUDE TIES` thường chỉ giữ amount của hàng hiện tại. Khái niệm “peer” vẫn dựa trên các biểu thức ORDER BY.

**Tính tương thích:** SQL Server và MySQL không cung cấp cùng cú pháp EXCLUDE kiểu PostgreSQL trong những phiên bản thông dụng. Nếu cần “tổng nhóm trừ hàng hiện tại” ở một hệ thiếu EXCLUDE, có thể tính tổng nhóm rồi trừ amount hiện tại **chỉ khi** phép trừ có ngữ nghĩa phù hợp và đã xử lý NULL/kiểu dữ liệu; hoặc dùng truy vấn con có điều kiện trên khóa định danh.

## 16. Khi không có GROUPS: mô phỏng bằng GROUP BY trước rồi ROWS

Không phải DBMS nào cũng hỗ trợ `GROUPS`. Một cách tiếp cận có tính di động tốt hơn là:

1. Tạo **một hàng trên mỗi peer group**.
2. Dùng **ROWS trên tập các nhóm** vì lúc này mỗi nhóm được biểu diễn bằng đúng một hàng.
3. Nếu cần kết quả **một hàng mỗi sự kiện**, JOIN lại bằng khóa nhóm.

Ví dụ PostgreSQL dưới đây cố ý chỉ dùng ROWS cho phần frame, để minh họa nguyên lý có thể chuyển sang SQL Server/MySQL:

```sql
WITH score_groups AS (
    SELECT
        channel,
        score,
        SUM(amount) AS score_group_amount
    FROM demo_frame_events
    GROUP BY channel, score
),
group_windows AS (
    SELECT
        channel,
        score,
        SUM(score_group_amount) OVER (
            PARTITION BY channel
            ORDER BY score
            ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
        ) AS current_and_previous_group_amount
    FROM score_groups
)
SELECT
    e.event_id,
    e.channel,
    e.score,
    e.amount,
    g.current_and_previous_group_amount
FROM demo_frame_events AS e
JOIN group_windows AS g
    ON g.channel = e.channel
   AND g.score = e.score
WHERE e.channel = 'A'
ORDER BY e.score, e.event_id;
```

`score_groups` chỉ có **một hàng cho mỗi cặp `(channel, score)`**, vì vậy ROWS 1 PRECEDING trên CTE nhóm nghĩa là **nhóm peer trước và nhóm hiện tại**. Kết quả trên kênh A là **30, 30, 60, 120, 120, 150**, tương ứng ví dụ `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW`.

### 16.1. Điều kiện để mô phỏng đúng

- CTE nhóm phải dùng **đầy đủ các biểu thức xác định peers**, không bỏ sót một khóa ORDER BY.
- Trong CTE nhóm, mỗi tổ hợp khóa phải có **đúng một hàng**, để ROWS thực sự đếm nhóm.
- Nếu JOIN lại khi khóa nhóm có thể NULL, điều kiện `=` không nối NULL với NULL; cần xử lý bằng so sánh NULL-safe phù hợp DBMS.
- Nếu measure có NULL, phải bảo toàn ngữ nghĩa SUM/COUNT; không tự coi mọi NULL bằng 0.
- Nếu dùng `GROUPS` trên nhiều biểu thức sắp xếp, ORDER BY trên CTE nhóm phải dùng cùng cấu trúc và chiều ASC/DESC.

**Mô phỏng không có nghĩa cùng hiệu năng:** CTE GROUP BY, window ROWS và JOIN trở lại có thể tốn thêm bước. Trong DBMS có GROUPS gốc, nên đánh giá cách viết trực tiếp; trong hệ thiếu GROUPS, cách tổ chức theo nhóm giúp giữ ngữ nghĩa rõ ràng.

### 16.2. Chỉ cần một hàng trên mỗi nhóm thì không phải JOIN lại

Nếu mục tiêu là biểu đồ **mỗi score một hàng** chứ không phải mỗi sự kiện:

```sql
WITH score_groups AS (
    SELECT
        channel,
        score,
        SUM(amount) AS score_group_amount
    FROM demo_frame_events
    GROUP BY channel, score
)
SELECT
    channel,
    score,
    score_group_amount,
    SUM(score_group_amount) OVER (
        PARTITION BY channel
        ORDER BY score
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS current_and_previous_group_amount
FROM score_groups
WHERE channel = 'A'
ORDER BY score;
```

Kết quả chỉ có **4 hàng score** (1, 2, 4, 7). Đó là một **grain khác** với truy vấn GROUPS trực tiếp trên các sự kiện, dù phần tổng theo nhóm có ý nghĩa liên quan.

## 17. Khi RANGE offset không được hỗ trợ: mẫu điều kiện khoảng giá trị

Ví dụ **SQL Server** có `RANGE` nhưng không hỗ trợ offset hữu hạn như `RANGE BETWEEN 1 PRECEDING AND CURRENT ROW` theo cú pháp phổ thông của T-SQL. Muốn tính tổng các hàng có score trong `[score hiện tại - 1, score hiện tại]`, một mẫu SQL dễ hiểu là correlated subquery:

```sql
-- Mẫu áp dụng theo cú pháp SELECT phổ biến trong SQL Server,
-- giả định dbo.events có cột channel, score, amount, event_id.
SELECT
    e.event_id,
    e.channel,
    e.score,
    e.amount,
    (
        SELECT SUM(x.amount)
        FROM dbo.events AS x
        WHERE x.channel = e.channel
          AND x.score >= e.score - 1
          AND x.score <= e.score
    ) AS sum_score_range_1
FROM dbo.events AS e
ORDER BY e.channel, e.score, e.event_id;
```

Với score kiểu số nguyên không NULL và sắp tăng dần, điều kiện trên diễn đạt cùng tập hàng như ví dụ RANGE 1 PRECEDING. **Không dùng điều kiện ấy nguyên xi** nếu score có NULL, kiểu thời gian, sắp DESC, hoặc quy tắc so sánh đặc biệt; phải diễn đạt đúng miền giá trị và ranh giới nghiệp vụ.

Correlated subquery có thể phải thực hiện nhiều lần và có chi phí cao với dữ liệu lớn. Tùy hệ, có thể dùng chỉ mục `(channel,score)`, JOIN theo khoảng giá trị rồi GROUP BY **khóa event** hoặc các chiến lược tổng hợp đã thiết kế, nhưng cần đo kế hoạch để tránh phép JOIN khoảng làm nhân hàng ngoài chủ đích.

**Điểm cốt lõi:** thiếu cú pháp RANGE offset không có nghĩa không thể tính chỉ số; nó có nghĩa phải **tự biểu diễn tập hàng thuộc khoảng giá trị**, và cần cân nhắc chi phí thực thi.

## 18. Dữ liệu ngày, timestamp và khoảng thời gian

Một yêu cầu như **“tổng số tiền trong bảy ngày tính tới ngày giao dịch”** phải phân biệt:

- Bảy **hàng giao dịch** gần nhất: ROWS (ví dụ `6 PRECEDING`).
- Khoảng **bảy ngày lịch** theo giá trị ngày/timestamp: RANGE với offset thời gian hoặc truy vấn theo khoảng ngày.
- Bảy **ngày có giao dịch phân biệt** gần nhất: GROUPS nếu peers được định nghĩa bởi ngày và DBMS hỗ trợ.

Giả sử giao dịch chỉ có trong các ngày 1, 2, 4, 7 của tháng:

```text
Ngày lịch:          01 02 03 04 05 06 07
Có giao dịch:        x  x  .  x  .  .  x

ROWS:   đếm số hàng sự kiện, có thể nhiều hàng trong một ngày.
RANGE:  đếm giá trị thời gian nằm trong khoảng được chỉ định.
GROUPS: đếm các ngày có giao dịch (nhóm peer) nếu ORDER BY chỉ theo ngày.
```

Đừng nhầm `GROUPS BETWEEN 2 PRECEDING AND CURRENT ROW` với “ba ngày lịch”: nếu các ngày có giao dịch là 1, 2, 4, 7, tại ngày 7 nó có thể lấy nhóm ngày **2, 4, 7** — một khoảng lịch kéo dài sáu ngày, chứ không nhất thiết ba ngày liên tiếp.

### 18.1. PostgreSQL RANGE theo thời gian và timezone

```sql
-- Giả định occurred_at là TIMESTAMPTZ.
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY occurred_at
    RANGE BETWEEN INTERVAL '24 hours' PRECEDING
              AND CURRENT ROW
)
```

Đây là cửa sổ 24 giờ theo mốc thời gian, không nhất thiết là “ngày lịch hôm qua và hôm nay”. Nếu nghiệp vụ tính theo ngày tại `Asia/Ho_Chi_Minh`, cần xác định cách chuyển timestamp thành ngày nghiệp vụ và ranh giới thời gian.

Ở các vùng có giờ mùa hè, **24 giờ** và **một ngày lịch** không luôn có cùng khoảng UTC. Khi báo cáo theo lịch, nên tạo hoặc chuẩn hóa ngày nghiệp vụ trước khi GROUPS/ROWS trên dãy ngày.

### 18.2. Ngày không có sự kiện

`RANGE` với khoảng ngày không tự tạo hàng cho một ngày **không có giao dịch**. Nó chỉ tính trên các hàng thực trong partition. Tương tự GROUPS không tự sinh peer group cho một ngày vắng dữ liệu.

Nếu cần biểu đồ doanh thu có đủ **mọi ngày**, hãy tạo một bảng/dãy lịch, LEFT JOIN tổng theo ngày, và sử dụng `COALESCE` theo quy tắc ngày không bán có doanh thu 0. Sau đó ROWS theo từng hàng ngày đã được làm đầy có thể diễn đạt **trung bình trượt trên số ngày lịch** một cách rõ ràng.

Trong PostgreSQL:

```sql
WITH calendar_days AS (
    SELECT d::DATE AS event_day
    FROM generate_series(
        DATE '2026-10-01',
        DATE '2026-10-07',
        INTERVAL '1 day'
    ) AS g(d)
),
daily_amount AS (
    SELECT
        event_day,
        SUM(amount) AS daily_total
    FROM demo_frame_events
    WHERE channel = 'A'
    GROUP BY event_day
),
complete_daily AS (
    SELECT
        c.event_day,
        COALESCE(d.daily_total, 0) AS daily_total
    FROM calendar_days AS c
    LEFT JOIN daily_amount AS d
        ON d.event_day = c.event_day
)
SELECT
    event_day,
    daily_total,
    SUM(daily_total) OVER (
        ORDER BY event_day
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_calendar_days_total
FROM complete_daily
ORDER BY event_day;
```

Trong kết quả một hàng mỗi ngày, ngày 05/10 và 06/10 có tổng 0; tại ngày 07/10, cửa sổ ba ngày (05, 06, 07) có tổng **60.00**. Không cần GROUPS chỉ để xử lý khoảng ngày khi nguồn đã được đưa về một hàng mỗi ngày đầy đủ.

## 19. Frame và PARTITION BY: giới hạn không vượt qua partition

Những frame trên áp dụng **riêng cho mỗi channel** nếu viết:

```sql
PARTITION BY channel
```

Ví dụ:

```sql
SELECT
    event_id,
    channel,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS grouped_sum
FROM demo_frame_events
ORDER BY channel, score, event_id;
```

Khi chuyển từ kênh A sang kênh B, frame **bắt đầu trên partition B**, không lấy nhóm score 7 của kênh A làm nhóm trước score 1 của B.

Ở kênh B:

| event_id | score | amount | GROUPS 1 PRECEDING đến CURRENT |
| ---: | ---: | ---: | ---: |
| 201 | 1 | 5.00 | 5.00 |
| 202 | 3 | 15.00 | 45.00 |
| 203 | 3 | 25.00 | 45.00 |
| 204 | 6 | 35.00 | 75.00 |

Nhóm score 3 gồm hai hàng tổng 40; tại score 3, nhóm trước là score 1 có tổng 5, nên kết quả **45**. Tại score 6, nhóm trước là score 3, nên 40 + 35 = **75**.

Nếu bỏ PARTITION BY channel, các hàng kênh A và B cùng score có thể trở thành peer trong một window `ORDER BY score`, làm chỉ số **trộn kênh**. Không nhầm việc SELECT cuối `ORDER BY channel` với PARTITION BY channel: thứ tự hiển thị không tạo ranh giới tính toán.

## 20. Khả năng hỗ trợ theo phương ngữ SQL

Các DBMS không có một bộ frame giống hệt nhau. Bảng sau thể hiện hướng dùng thông dụng; với tính năng đặc biệt và hệ đang vận hành, phải kiểm tra **phiên bản, kiểu ORDER BY, offset và tài liệu dialect đích**.

| DBMS | ROWS | RANGE | GROUPS | Điều cần lưu ý |
| --- | --- | --- | --- | --- |
| **PostgreSQL** | Có | Có | Có từ PostgreSQL 11 | RANGE offset dùng kiểu phù hợp; GROUPS/EXCLUDE có ở các phiên bản hỗ trợ |
| **SQLite hiện đại** | Có | Có | Có | Hỗ trợ GROUPS và EXCLUDE trong các bản mới; RANGE offset chủ yếu diễn đạt trên ORDER BY số, chú ý cách lưu ngày/giờ |
| **DuckDB** | Có | Có | Có | Có các window frame nâng cao; kiểm tra giới hạn kiểu và phiên bản |
| **SQL Server** | Có | Có nhưng **RANGE offset hữu hạn** bị hạn chế | Không có GROUPS trong T-SQL thông dụng | Không dùng `RANGE 1 PRECEDING`; có thể tổng hợp theo nhóm rồi ROWS |
| **MySQL 8.0+** | Có | Có | Không hỗ trợ GROUPS trong cú pháp window thông dụng | RANGE offset có quy tắc riêng về kiểu số/ngày, `INTERVAL`; chú ý bản MySQL triển khai |
| **Oracle Database** | Có | Có | Có ở các phiên bản cung cấp GROUPS | Phải đối chiếu release và cú pháp windowing clause; offset RANGE có giới hạn khóa ORDER BY |
| **BigQuery (GoogleSQL)** | Có | Có | Không hỗ trợ GROUPS trong cú pháp window frame thông dụng | RANGE offset yêu cầu một biểu thức ORDER BY **kiểu số**; dùng UNIX_DATE/UNIX_SECONDS khi tính khoảng ngày/giây |

**Không kết luận rằng hệ có `OVER` thì chắc chắn có cả ba chế độ.** Có hệ hỗ trợ ranking và SUM OVER nhưng chỉ hỗ trợ ROWS/RANGE; có hệ hỗ trợ RANGE với ranh giới UNBOUNDED/CURRENT ROW nhưng không hỗ trợ `n PRECEDING`.

### 20.1. PostgreSQL: ba frame trong cùng SELECT

Truy vấn so sánh ở mục 8 dùng cả ROWS, RANGE, GROUPS và chạy trên PostgreSQL có hỗ trợ GROUPS:

```sql
SELECT
    event_id,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS rows_sum,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS range_sum,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS groups_sum
FROM demo_frame_events;
```

PostgreSQL 11 trở lên hỗ trợ `GROUPS` và các tùy chọn EXCLUDE tương ứng. Với PostgreSQL cũ hơn hoặc SQL code nhắm nhiều hệ, cân nhắc mẫu tổng hợp nhóm trước rồi ROWS.

### 20.2. SQL Server: ROWS và RANGE với giới hạn

T-SQL hỗ trợ một số frame như:

```sql
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS rows_sum,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS range_cumulative
FROM dbo.events;
```

`dbo.events` là bảng giả định trên SQL Server có các cột tương ứng. **Không dùng**:

```sql
-- Không phải cú pháp RANGE offset hỗ trợ thông dụng của SQL Server:
RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
```

Nếu muốn GROUPS 1 PRECEDING, dùng CTE gom một hàng mỗi score rồi ROWS trên nhóm như mục 16. Nếu muốn RANGE theo số/giờ có offset, diễn đạt bằng điều kiện khoảng phù hợp như mục 17.

### 20.3. MySQL 8.0+: dùng ROWS và RANGE, không giả định GROUPS

Trong MySQL 8.0+, một ví dụ ROWS:

```sql
SELECT
    event_id,
    channel,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score, event_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS last_two_rows_total
FROM events;
```

MySQL có RANGE theo cú pháp và giới hạn riêng về kiểu ORDER BY và khoảng; cần kiểm tra phần RANGE frame của phiên bản đích, nhất là khi dùng INTERVAL với ngày. Không copy `GROUPS ... PRECEDING` của PostgreSQL sang MySQL rồi kỳ vọng cú pháp được chấp nhận.

### 20.4. SQLite: GROUPS có ích nhưng phải xét phiên bản nhúng

SQLite hỗ trợ các frame nâng cao ở những phiên bản tương ứng:

```sql
SELECT
    event_id,
    channel,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS grouped_sum
FROM events;
```

Hệ thống mobile hoặc phần mềm nhúng có thể dùng bản SQLite đi kèm runtime, khác phiên bản SQLite người phát triển dùng để thử truy vấn. Cần xác minh engine chạy thực tế. Với thời gian lưu dưới dạng TEXT, RANGE theo offset số không tự hiểu `INTERVAL` như PostgreSQL; cần chuyển ngày về biểu diễn số hoặc chuẩn hóa trước.

### 20.5. BigQuery: RANGE theo khóa số

Trong GoogleSQL, frame RANGE với offset thường yêu cầu **một ORDER BY numeric**. Ví dụ với score:

```sql
-- BigQuery GoogleSQL: bảng events là nguồn dữ liệu minh họa.
SELECT
    event_id,
    score,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS range_sum
FROM `project.dataset.events`;
```

Với DATE, có thể chuyển ngày sang số ngày bằng **`UNIX_DATE(event_day)`** để xác định RANGE theo một đơn vị ngày:

```sql
SELECT
    event_id,
    event_day,
    amount,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY UNIX_DATE(event_day)
        RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS total_in_day_value_range
FROM `project.dataset.events`;
```

Tên bảng là minh họa, phải thay bằng nguồn thực tế. `UNIX_DATE` chỉ biểu diễn DATE dưới dạng số ngày; nếu dữ liệu gốc là TIMESTAMP, cần chọn phép chuyển thời gian và múi giờ phù hợp, không tự coi timestamp là ngày lịch địa phương.

### 20.6. Oracle: xem release và giới hạn khung

Oracle có các analytic/window function lâu đời với `ROWS` và `RANGE`, và có `GROUPS` trong những phiên bản hỗ trợ tính năng này. Ví dụ ý tưởng:

```sql
SELECT
    event_id,
    channel,
    score,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS grouped_sum
FROM events;
```

Không nên coi ví dụ này chạy trên mọi release Oracle. Khi hệ đích cũ hơn hoặc tổ chức có phiên bản cố định, tra phiên bản SQL Language Reference tương ứng để xem `GROUPS`, `RANGE` offset, loại dữ liệu và quy tắc ORDER BY có được hỗ trợ hay không.

## 21. Chọn frame dựa trên câu hỏi nghiệp vụ

Không nên chọn `ROWS` chỉ vì viết ngắn, hoặc `RANGE` vì “có vẻ giống khung thời gian”. Hãy chuyển yêu cầu thành một trong ba câu hỏi:

| Yêu cầu | Chế độ nên cân nhắc | Ví dụ |
| --- | --- | --- |
| Tổng của **5 giao dịch gần nhất** theo thứ tự sự kiện | `ROWS` | `ROWS BETWEEN 4 PRECEDING AND CURRENT ROW` |
| Trung bình của **3 dòng kết quả liền trước và hiện tại** | `ROWS` | `ROWS BETWEEN 3 PRECEDING AND CURRENT ROW` (4 hàng tối đa) |
| Tổng trong **2 đơn vị score trước đến score hiện tại** | `RANGE` | `RANGE BETWEEN 2 PRECEDING AND CURRENT ROW` |
| Tổng giao dịch trong **24 giờ trở lại đây** | `RANGE` trên timestamp với offset phù hợp hoặc điều kiện thời gian | `RANGE BETWEEN INTERVAL '24 hours' PRECEDING AND CURRENT ROW` trên PostgreSQL |
| Tổng của **3 mức giá phân biệt gần nhất** | `GROUPS` | `GROUPS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| Tổng theo **ngày lịch** có đủ cả ngày không giao dịch | Tạo lịch + `ROWS` trên tập một hàng mỗi ngày | Dùng calendar dimension / generate_series |
| Tổng của **nhóm đồng hạng hiện tại** | `RANGE CURRENT ROW` hoặc `GROUPS CURRENT ROW` | Cùng ORDER BY theo tiêu chí đồng hạng |
| Xếp hạng đơn/khách không cần tổng frame | Hàm ranking, chọn đúng ORDER BY | `RANK()`, `DENSE_RANK()`, `ROW_NUMBER()` |

Trong bảng trên, “3 dòng liền trước và hiện tại” gồm **4 hàng** tối đa, vì từ khóa `3 PRECEDING` tính ba hàng **trước** cộng một hàng hiện tại. Đây là lỗi lệch một đơn vị phổ biến khi thiết kế kích thước cửa sổ.

### 21.1. Nếu bài toán nói “7 ngày gần nhất”, hỏi rõ ngày lịch hay ngày quan sát

Một frame `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` trên bảng tổng doanh thu theo ngày **chỉ là bảy hàng ngày có dữ liệu**. Muốn đúng bảy **ngày lịch**:

- Hoặc làm đầy ngày không có dữ liệu trước rồi dùng ROWS trên một hàng mỗi ngày;
- Hoặc dùng RANGE theo DATE/timestamp với khoảng thời gian rõ ràng, nếu DBMS hỗ trợ và cách xử lý peer/ngày phù hợp.

Hai cách có thể khác nhau về việc hiển thị ngày trống và mẫu số trung bình. Phải xác định quy ước ngày có doanh thu 0 và ngày có amount NULL.

### 21.2. Nếu bài toán nói “nhóm hạng trước”, không dùng RANGE offset số một cách máy móc

Với score 2 rồi 4, **nhóm trước score 4** là score 2. `RANGE 1 PRECEDING` ở score 4 không lấy score 2 vì khoảng số chỉ từ 3 đến 4. `GROUPS 1 PRECEDING` mới trực tiếp diễn đạt “một nhóm peer đứng trước”.

## 22. Tương tác giữa frame, tổng hợp trước và JOIN

Frame chỉ được tính trên **các hàng mà bước window nhận được**. Nếu JOIN hoặc GROUP BY trước đó làm thay đổi bội số và độ hạt, ROWS/RANGE/GROUPS cũng sẽ cho kết quả dựa trên tập hàng đã thay đổi.

### 22.1. JOIN một-nhiều có thể khiến tổng bị nhân

Giả sử một giao dịch có hai dòng item và ba bản ghi payment. Nếu JOIN cả hai bảng con trước khi tính:

```sql
SUM(o.amount) OVER (
    PARTITION BY o.customer_id
    ORDER BY o.created_at, o.order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

thì một đơn có thể xuất hiện **2 × 3 = 6 lần** trong đầu vào window. SUM không biết những hàng ấy đến từ cùng một đơn gốc; nó chỉ cộng giá trị trên frame. Việc đổi ROWS thành RANGE hoặc GROUPS không tự khôi phục số tiền đúng.

### 22.2. Tổng hợp trước theo độ hạt yêu cầu

Nếu mục tiêu là **doanh thu theo từng ngày**, hãy tính:

```sql
WITH daily_amount AS (
    SELECT
        event_day,
        SUM(amount) AS daily_total
    FROM demo_frame_events
    WHERE channel = 'A'
    GROUP BY event_day
)
SELECT
    event_day,
    daily_total,
    SUM(daily_total) OVER (
        ORDER BY event_day
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS sum_last_3_observed_days
FROM daily_amount
ORDER BY event_day;
```

Mỗi hàng CTE giờ đại diện cho **một ngày có dữ liệu**, nên ROWS đếm ngày **quan sát**, không còn đếm sự kiện. Nếu mục tiêu là ba ngày **lịch**, vẫn cần làm đầy calendar như mục 18.

**CTE không đổi nghĩa của ROWS**; nó thay đổi **tập hàng đầu vào** của ROWS. Vì thế, xác định grain của từng bước quan trọng ngang với việc chọn frame mode.

## 23. Hiệu năng và kế hoạch thực thi

Window có thể cần sắp xếp theo `(PARTITION BY, ORDER BY)`, lưu trạng thái từng partition hoặc nhiều phần frame; chi phí phụ thuộc:

1. Số hàng đi vào window và độ rộng mỗi hàng.
2. Số partition và kích thước partition lớn nhất.
3. Số lượng peers có cùng khóa ORDER BY.
4. Kiểu frame: hàng, khoảng giá trị, nhóm peer; độ rộng frame và khả năng tối ưu của DBMS.
5. Chỉ mục, thứ tự sẵn có, thống kê, bộ nhớ và cách thực thi song song.
6. Có phải JOIN làm nhân hàng hoặc GROUP BY tạo quá nhiều hàng trước window không?

Không có quy tắc chắc chắn rằng **ROWS luôn nhanh hơn RANGE** hoặc **GROUPS luôn chậm hơn ROWS** trên mọi truy vấn. Một frame RANGE rất hẹp có thể chứa ít hàng; một frame ROWS không giới hạn có thể chứa nhiều; bộ tối ưu và thuật toán tăng dần của mỗi hệ quyết định phần lớn chi phí.

### 23.1. Index phục vụ PARTITION và ORDER BY

Trong PostgreSQL, có thể cân nhắc một chỉ mục:

```sql
CREATE INDEX idx_demo_frame_channel_score_id
ON demo_frame_events (channel, score, event_id);
```

Chỉ mục này có thể hữu ích khi lọc/đọc theo channel và score, nhất là với ROWS có thứ tự `(score,event_id)` phù hợp. Nhưng không tự bảo đảm DBMS dùng index; một bảng nhỏ có thể dùng sequential scan rồi sort rẻ hơn.

Với `RANGE`/`GROUPS` chỉ ORDER BY score, chỉ mục trên channel và score cũng có thể hữu ích để cung cấp thứ tự; tuy nhiên, chi phí phụ thuộc biểu thức, frame và kích thước partition.

### 23.2. Dùng EXPLAIN

```sql
EXPLAIN
SELECT
    event_id,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    )
FROM demo_frame_events;
```

Với môi trường thích hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    event_id,
    SUM(amount) OVER (
        PARTITION BY channel
        ORDER BY score
        RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
    )
FROM demo_frame_events;
```

Trong PostgreSQL, `EXPLAIN` cho kế hoạch **ước lượng**; `EXPLAIN (ANALYZE, BUFFERS)` **thực sự chạy câu SELECT** rồi trình bày số hàng, thời gian và buffer. Có thể gặp các node `Sort`, `WindowAgg`, `Index Scan` hay kế hoạch khác theo phiên bản và dữ liệu.

Nếu truy vấn GROUPS không hợp lệ ở DBMS đích, **không thể dùng EXPLAIN để thử đo chính câu ấy**; phải chuyển cú pháp hoặc mô phỏng đúng trước. Đừng tối ưu hóa một truy vấn mà ngữ nghĩa kết quả chưa được xác định.

### 23.3. So sánh sau khi đã giữ cùng yêu cầu nghiệp vụ

So sánh “ROWS 1 PRECEDING” với “RANGE 1 PRECEDING” về thời gian chạy **không phải benchmark hai cách viết của cùng một câu hỏi**, vì hai frame trả các tập hàng khác nhau. Muốn đánh giá việc thay GROUPS trực tiếp bằng CTE group + ROWS, trước hết cần đối chiếu **cùng tập kết quả** rồi mới đo chi phí trên dữ liệu đại diện.

## 24. Các lỗi và ngộ nhận thường gặp

| Ngộ nhận / lỗi | Vì sao không đúng? | Cách xử lý |
| --- | --- | --- |
| `ROWS 1 PRECEDING` nghĩa là score trừ 1 | ROWS đếm hàng, không đếm giá trị | Dùng RANGE nếu muốn khoảng score |
| `RANGE 1 PRECEDING` nghĩa là nhóm peer trước | RANGE đếm khoảng giá trị; score có thể có khoảng trống | Dùng GROUPS nếu muốn nhóm trước |
| `GROUPS 1 PRECEDING` nghĩa là một hàng trước | Một nhóm có thể nhiều hàng | Xác định peer group bằng ORDER BY |
| `CURRENT ROW` luôn chỉ đúng hàng hiện tại | Trong RANGE/GROUPS, ranh giới CURRENT ROW liên quan đến peer group | So sánh ba chế độ với giá trị trùng |
| Thêm event_id vào mọi ORDER BY không ảnh hưởng GROUPS | Peer được định nghĩa bằng toàn bộ ORDER BY | Chỉ thêm khóa phụ khi mục tiêu đồng hạng cho phép |
| `SUM(...) OVER (ORDER BY score)` luôn chạy từng hàng | Frame mặc định có thể bao gồm toàn bộ peers của score | Viết ROWS tường minh nếu cần cộng từng sự kiện |
| `ROWS 2 PRECEDING` là hai hàng tổng cộng | Có **hai hàng trước cộng hàng hiện tại** | Xác nhận kích thước frame có thể tới 3 |
| Window theo ngày luôn hiển thị ngày không có sự kiện | Window chỉ trả hàng nguồn hiện có | Tạo calendar và LEFT JOIN |
| GROUPS ba nhóm gần nhất là ba ngày lịch | Nhóm theo ngày có dữ liệu, không tự bù ngày rỗng | Làm đầy lịch nếu tính ngày lịch |
| ROWS theo score trùng sẽ ổn định dù không có khóa phụ | Thứ tự peers không xác định | Thêm khóa phụ duy nhất cho ROWS |
| RANGE offset dùng được với hai cột ORDER BY bất kỳ | Nhiều hệ, gồm PostgreSQL, giới hạn RANGE offset vào một khóa | Dùng một khóa hoặc thiết kế lại |
| DESC có PRECEDING luôn lấy giá trị nhỏ hơn | Chiều sắp xếp làm đổi hướng đi trước/sau | Diễn giải theo ORDER BY thực |
| ROW_NUMBER đổi kết quả theo GROUPS frame | Ranking không dùng frame như SUM | Dùng DENSE_RANK cho nhóm đồng hạng |
| LAST_VALUE luôn trả hàng cuối partition | Frame mặc định có thể chỉ đến CURRENT ROW | Chỉ rõ UNBOUNDED FOLLOWING |
| COUNT và SUM trên frame rỗng đều trả 0 | COUNT = 0, SUM = NULL | Chọn COALESCE theo nghiệp vụ |
| RANGE/GROUPS sửa được tiền bị nhân do JOIN | Frame hoạt động trên các hàng sau JOIN | Sửa grain/tiền ở bước JOIN và tổng hợp |
| Hệ có SUM OVER là chắc có GROUPS | Hỗ trợ frame mode khác nhau | Kiểm tra dialect và phiên bản |
| SQL Server có RANGE nên có `RANGE 1 PRECEDING` | T-SQL hạn chế RANGE offset hữu hạn | Mô phỏng khoảng bằng điều kiện |
| GROUPS luôn cần CTE GROUP BY | Một số DBMS hỗ trợ GROUPS trực tiếp | Dùng native khi có; CTE là fallback |
| EXCLUDE có ở mọi DBMS hỗ trợ ROWS | EXCLUDE là tính năng riêng | Kiểm tra và thiết kế giải pháp thay thế |
| Frame càng nhỏ thì mọi truy vấn càng nhanh | Hiệu năng phụ thuộc sort, partition, plan, index | EXPLAIN và đo dữ liệu thật |

## 25. Bài tập thực hành

Hãy dùng bảng `demo_frame_events` ở mục 2. Trước khi chạy truy vấn, hãy **xác định hàng/peer group thuộc từng frame**, rồi mới tính tổng để củng cố khác biệt giữa ROWS, RANGE và GROUPS.

### Bài 1 — Hai hàng gần nhất

Với kênh A, dùng `SUM(amount) OVER (ORDER BY score, event_id ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)`. Dự đoán kết quả cho các event 101–106: **10, 30, 50, 70, 90, 110**. Tại sao event 106 lấy amount của event 105 dù score chênh 3?

### Bài 2 — Khoảng score một đơn vị

Với kênh A, dùng `RANGE BETWEEN 1 PRECEDING AND CURRENT ROW` và ORDER BY score. Dự đoán: **30, 30, 60, 90, 90, 60**. Vì sao các event score 4 không tính score 2? Tại sao event 101 và 102 cùng có 30?

### Bài 3 — Một nhóm peer trước

Với kênh A, dùng `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW`. Kết quả: **30, 30, 60, 120, 120, 150**. Tại event 106, nhóm đứng trước score 7 là nhóm nào? Khoảng cách số học có ảnh hưởng không?

### Bài 4 — CURRENT ROW trong ba chế độ

Viết ba phép SUM với `BETWEEN CURRENT ROW AND CURRENT ROW`. So sánh event 101 và 102. Vì sao ROWS trả 10/20, còn RANGE/GROUPS theo score đều trả 30?

### Bài 5 — Frame mặc định

Chạy `SUM(amount) OVER (PARTITION BY channel ORDER BY score)` trên kênh A. Vì sao kết quả là **30, 30, 60, 150, 150, 210** thay vì **10, 30, 60, 100, 150, 210**? Viết lại bằng ROWS và khóa phụ để cộng từng sự kiện.

### Bài 6 — Hai khóa ORDER BY

So sánh peers khi dùng `ORDER BY score` và `ORDER BY score, event_id`. Vì sao GROUPS CURRENT ROW không còn gom hai event score 1 nếu thêm event_id? Tại sao `RANGE BETWEEN 1 PRECEDING` với hai khóa không phù hợp trong PostgreSQL?

### Bài 7 — FOLLOWING

Tính tổng bằng `RANGE BETWEEN CURRENT ROW AND 1 FOLLOWING` và bằng `GROUPS BETWEEN CURRENT ROW AND 1 FOLLOWING` cho score 2 và score 4 kênh A. Giải thích khi nào hai kết quả khác nhau. Gợi ý: ở score 2, RANGE ra **30**, GROUPS ra **120**.

### Bài 8 — Kênh B độc lập

Chạy GROUPS 1 PRECEDING theo score với `PARTITION BY channel` trên toàn bảng. Dự đoán kết quả kênh B: **5, 45, 45, 75**. Nếu bỏ PARTITION BY, tại sao kết quả không còn là tổng riêng theo kênh?

### Bài 9 — Khoảng ngày

Dùng PostgreSQL `RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW` với ORDER BY event_day. Tại ngày 04/10 của kênh A, những event nào được tính và tổng là bao nhiêu? So sánh với `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`: số hàng và ranh giới được xác định khác nhau thế nào?

### Bài 10 — Ngày lịch không có giao dịch

Tạo dãy ngày từ 01/10 đến 07/10 bằng `generate_series`, GROUP BY số tiền theo ngày, LEFT JOIN với lịch và tính `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`. Ngày 05/10 và 06/10 phải có tổng 0 theo quy ước; tại ngày 07/10, tổng ba ngày lịch là **60**. Vì sao GROUPS theo ngày có giao dịch không tự cho cùng bảy hàng biểu đồ?

### Bài 11 — Frame rỗng

Tính `COUNT(*)` và `SUM(amount)` trên `ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING` của kênh A. Hai biểu thức cho gì ở event 101? Nếu muốn hiển thị 0 thay vì NULL, khi nào có thể dùng `COALESCE`?

### Bài 12 — LAST_VALUE

Tính `LAST_VALUE(amount) OVER (PARTITION BY channel ORDER BY score,event_id)` và thêm phiên bản với `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`. Vì sao phiên bản thứ hai trả **60** trên mọi event kênh A?

### Bài 13 — GROUPS khi DBMS không hỗ trợ

Viết CTE `score_groups` GROUP BY `(channel,score)`, CTE dùng ROWS 1 PRECEDING trên mỗi hàng nhóm, rồi JOIN về từng event. Đối chiếu kết quả với GROUPS trực tiếp của PostgreSQL. Nêu lý do cần GROUP BY đủ các cột định nghĩa peer group.

### Bài 14 — RANGE khi DBMS không hỗ trợ offset

Giả sử dùng SQL Server và muốn tính tổng amount có score trong `[current_score - 1, current_score]`. Viết correlated subquery theo cùng channel, với score kiểu số không NULL. Vì sao không thể chép `RANGE BETWEEN 1 PRECEDING` từ PostgreSQL vào SQL Server? Với dữ liệu lớn, cần kiểm tra hiệu năng thế nào?

### Bài 15 — EXCLUDE

Trên PostgreSQL có hỗ trợ EXCLUDE, dùng GROUPS CURRENT ROW và `EXCLUDE CURRENT ROW`. Với event 101, 102, 104, 105, 103, hãy dự đoán tổng amount của **các peer khác**. Vì sao một event không có peer khác cho kết quả SUM NULL?

### Bài 16 — Thiết kế báo cáo nghiệp vụ

Một nhóm yêu cầu:

1. Tổng 5 giao dịch gần nhất.
2. Doanh thu trong vòng 24 giờ.
3. Tổng tiền ở ba mức score phân biệt gần nhất.
4. Doanh thu ba ngày lịch kể cả ngày không bán.

Hãy chọn ROWS/RANGE/GROUPS hoặc lịch + ROWS cho từng yêu cầu. Nêu rõ ORDER BY, PARTITION BY và cách xử lý NULL hoặc thiếu ngày.

### Bài 17 — Phát hiện lỗi do JOIN

Một event gốc có hai dòng chi tiết và ba nhãn phân loại. Nếu JOIN cả hai nhánh trước SUM window, event có thể xuất hiện bao nhiêu lần? Việc đổi ROWS sang GROUPS có sửa lỗi cộng lặp được không? Thiết kế cách tổng hợp theo khóa event trước khi chạy window.

### Bài 18 — Chọn phương ngữ phù hợp

Viết bảng ba cột mô tả cách giải quyết cùng bài toán “tổng nhóm score hiện tại và nhóm trước” trên PostgreSQL hiện đại, SQL Server và MySQL 8+. Hệ nào dùng GROUPS trực tiếp? Với hệ thiếu GROUPS, hãy dùng `GROUP BY score` rồi ROWS.

## 26. Quy trình chọn frame trong dự án thật

Khi đọc yêu cầu phân tích, có thể làm theo quy trình:

1. **Xác định grain của hàng đầu vào**: một giao dịch, một ngày, một khách hay một nhóm score? Cần GROUP BY trước không?
2. **Xác định partition**: mỗi khách, mỗi kênh, mỗi tài khoản hay toàn bộ bảng?
3. **Xác định tiêu chí sắp xếp** và ý nghĩa các hàng đồng hạng: score bằng nhau có thuộc cùng nhóm nghiệp vụ không?
4. **Chọn đơn vị dịch frame**:
   - Số **hàng** → ROWS.
   - Khoảng **giá trị số/thời gian** → RANGE.
   - Số **nhóm peer** → GROUPS.
5. **Viết ranh giới rõ**: CURRENT ROW, số PRECEDING/FOLLOWING, UNBOUNDED.
6. **Kiểm tra khả năng hỗ trợ** của DBMS thật, bao gồm kiểu ORDER BY, offset hữu hạn, GROUPS và EXCLUDE.
7. **Xem trường hợp khó**: trùng ORDER BY, khoảng trống, NULL, frame rỗng, ngày không có sự kiện, chiều DESC.
8. **Đảm bảo JOIN không nhân bản measure** trước window; tổng hợp trước khi cần.
9. **So sánh bằng ví dụ nhỏ**, sau đó đo kế hoạch và thời gian thực thi bằng công cụ DBMS phù hợp.

Nguyên tắc quan trọng nhất là **frame phải phản ánh chính xác đơn vị mà câu hỏi nghiệp vụ đang đếm**. Hai frame trả tổng khác nhau không nhất thiết là lỗi hệ quản trị: có thể một frame đang đếm số sự kiện, frame kia đang đếm khoảng giá trị, và frame cuối đang đếm số nhóm đồng hạng.

## 27. Kết luận

```text
                  Window PARTITION
                         |
                         v
              ORDER BY xác định thứ tự
                         |
            +------------+------------+
            |            |            |
            v            v            v
           ROWS         RANGE        GROUPS
            |            |            |
         HÀNG thứ n   KHOẢNG GIÁ TRỊ  NHÓM PEER thứ n
            |            |            |
            +------------+------------+
                         |
                         v
                  Frame tại mỗi hàng
                         |
                         v
               SUM / AVG / COUNT /
               FIRST_VALUE / LAST_VALUE ...
```

**`ROWS` đếm hàng, `RANGE` dựa vào giá trị sắp xếp, còn `GROUPS` đếm các nhóm peer liên tiếp.** `CURRENT ROW` trong ROWS chỉ hàng hiện tại, nhưng trong RANGE/GROUPS có thể mở rộng tới toàn bộ nhóm đồng hạng. Nếu không viết frame, mặc định của window có ORDER BY có thể khiến các hàng đồng score nhận cùng tổng lũy kế; nếu dùng `LAST_VALUE`, mặc định kết thúc ở hàng hiện tại có thể không phải điều mong đợi.

Hãy xác định **PARTITION BY, ORDER BY, peer group, frame boundary và độ hạt dữ liệu** trước khi chọn chế độ. Khi DBMS không hỗ trợ GROUPS, có thể gom thành một hàng mỗi nhóm rồi chạy ROWS; khi RANGE offset bị hạn chế, có thể diễn đạt điều kiện khoảng giá trị qua truy vấn khác. Những cách thay thế ấy cần giữ **đúng ngữ nghĩa và NULL**, sau đó mới đo hiệu năng.

Một câu SQL window đáng tin cậy không chỉ có `OVER (...)` hợp lệ, mà còn phải trả lời đúng: **“Ở hàng hiện tại, tôi muốn nhìn bao nhiêu hàng, khoảng giá trị nào, hay bao nhiêu nhóm đồng hạng?”**
