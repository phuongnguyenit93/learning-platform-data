# Lấy các hàng đầu và xử lý trường hợp đồng hạng

Khi một báo cáo yêu cầu “lấy 3 người có điểm cao nhất”, câu hỏi tưởng đơn giản nhưng có ít nhất ba cách hiểu:

1. Trả về **đúng 3 hàng**, kể cả khi một số người bằng điểm nhau.
2. Lấy **3 hàng đầu rồi giữ thêm mọi người đồng điểm với người ở vị trí thứ 3**.
3. Lấy tất cả người có điểm thuộc **3 mức điểm cao nhất**, bất kể có bao nhiêu người ở mỗi mức.

Ba yêu cầu này có thể trả về số hàng khác nhau. Vì vậy, trước khi viết `LIMIT`, `FETCH FIRST`, `TOP` hoặc hàm xếp hạng, phải xác định **khái niệm “hàng đầu” và “đồng hạng”** theo nghiệp vụ.

Bài học thuộc chương **Sắp xếp và phân trang** của Database SQL. Nội dung sử dụng PostgreSQL làm hệ quản trị thực hành chính; cuối bài có phần đối chiếu với SQL Server, Oracle, MySQL và SQLite. Những ví dụ theo phiên bản được nêu rõ khi cú pháp không phổ biến ở mọi hệ.

## 1. Đầu tiên phải xác định “đầu” là theo thứ tự nào

Trong SQL, bảng về mặt quan hệ **không có thứ tự hàng mặc định được bảo đảm**. Một câu truy vấn như:

```sql
SELECT member_id, display_name
FROM ranking_scores
LIMIT 3;
```

chỉ yêu cầu tối đa 3 hàng; **không có `ORDER BY`**, nên không có cơ sở để gọi đó là “3 người có điểm cao nhất”, “3 người được thêm sớm nhất” hoặc “3 người mới nhất”.

Để xác định “hàng đầu”, cần chọn một hoặc nhiều **khóa sắp xếp**:

```sql
ORDER BY points DESC
```

Khi đó điểm cao đứng trước điểm thấp. Tuy nhiên, nếu có hai người cùng `points`, thứ tự tương đối giữa họ vẫn chưa xác định.

Dấu hiệu cần phân biệt:

| Cách diễn đạt yêu cầu | Ý nghĩa có thể chọn | Kiểm tra trước khi viết SQL |
| --- | --- | --- |
| “Lấy 3 bản ghi đầu” | 3 hàng theo thứ tự quy định | Thứ tự nào, có cần ổn định không? |
| “3 người điểm cao nhất” | Có thể là đúng 3 người hoặc bao gồm đồng hạng | Có chấp nhận hơn 3 hàng không? |
| “Top 3 có đồng hạng” | Có thể giữ người đồng hạng ở ranh giới | Đồng hạng theo cột nào? |
| “3 mức điểm cao nhất” | 3 **giá trị điểm khác nhau** | Có dùng `DENSE_RANK` không? |
| “Top 2 trong mỗi phòng ban” | Xếp hạng riêng từng nhóm | Nhóm theo `department`/`team` nào? |
| “Trang đầu có 3 hàng” | Phân trang theo thứ tự đầy đủ | Cách phá hòa và dữ liệu thay đổi giữa các trang? |

**Điểm quan trọng:** Cần thống nhất “đồng hạng” dựa trên thuộc tính nào. Nếu điểm số bằng nhau nhưng có quy tắc ưu tiên theo thời điểm hoàn thành, thì hai người cùng điểm có thể không còn đồng hạng theo **thứ tự ưu tiên thực tế**.

## 2. Bộ dữ liệu mẫu: tạo đủ trường hợp đồng điểm

Dùng bảng tạm PostgreSQL để có thể thực hành trong một phiên kết nối mà không ảnh hưởng bảng ứng dụng.

```sql
CREATE TEMP TABLE ranking_scores (
    member_id    INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    team         TEXT NOT NULL,
    points       INTEGER CHECK (points >= 0)
);

INSERT INTO ranking_scores
    (member_id, display_name, team, points)
VALUES
    (1,  'An',    'Sales',   980),
    (2,  'Binh',  'Sales',   920),
    (3,  'Chi',   'Sales',   920),
    (4,  'Dung',  'Sales',   860),
    (5,  'Hanh',  'Sales',   860),
    (6,  'Giang', 'Sales',   790),
    (7,  'Khoa',  'Support', 950),
    (8,  'Lam',   'Support', 880),
    (9,  'Minh',  'Support', 880),
    (10, 'Nga',   'Support', 720),
    (11, 'Phuc',  'Support', NULL),
    (12, 'Quynh','Sales',   NULL);
```

Trong dữ liệu này, `member_id` xác định duy nhất mỗi người, `team` là nhóm để có thể thực hiện Top N theo nhóm, `points` là điểm dùng để xếp hạng. Hai người `Phuc` và `Quynh` chưa có điểm, được biểu diễn bằng `NULL`.

Một thứ tự **đầy đủ và ổn định với dữ liệu hiện tại** là:

```sql
SELECT member_id, display_name, team, points
FROM ranking_scores
ORDER BY points DESC NULLS LAST,
         member_id ASC;
```

Theo `points` giảm dần, nếu bằng điểm thì dùng `member_id` tăng dần để phân định. `NULLS LAST` chỉ rõ người chưa có điểm được đưa về cuối trong PostgreSQL.

| Vị trí khi có khóa phụ | Người | Team | Điểm |
| ---: | --- | --- | ---: |
| 1 | An | Sales | 980 |
| 2 | Khoa | Support | 950 |
| 3 | Binh | Sales | 920 |
| 4 | Chi | Sales | 920 |
| 5 | Lam | Support | 880 |
| 6 | Minh | Support | 880 |
| 7 | Dung | Sales | 860 |
| 8 | Hanh | Sales | 860 |
| 9 | Giang | Sales | 790 |
| 10 | Nga | Support | 720 |
| 11 | Phuc | Support | `NULL` |
| 12 | Quynh | Sales | `NULL` |

**Quy ước của bài học:** Trong bảng xếp hạng bằng điểm, người có `points IS NULL` là **chưa được chấm**, nên các truy vấn Top N theo điểm sẽ lọc `points IS NOT NULL` trước khi xếp hạng, trừ phần giải thích riêng về `NULL`. Lựa chọn này là quy tắc báo cáo, không phải bắt buộc của SQL.

## 3. Lấy chính xác N hàng với ORDER BY và LIMIT

Câu hỏi: **Trả về đúng 3 người đầu theo điểm giảm dần; khi bằng điểm thì người có `member_id` nhỏ hơn đứng trước.**

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
LIMIT 3;
```

Kết quả:

| `member_id` | `display_name` | `points` |
| ---: | --- | ---: |
| 1 | An | 980 |
| 7 | Khoa | 950 |
| 2 | Binh | 920 |

Đây là **3 hàng**, không phải 3 nhóm điểm. `Chi` cũng đạt 920 nhưng đứng sau `Binh` do khóa phụ `member_id ASC`, nên không xuất hiện.

### 3.1. Vì sao cần khóa phụ duy nhất?

Nếu chỉ viết:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC
LIMIT 3;
```

thì hai vị trí đầu là An và Khoa, nhưng ở vị trí thứ ba, PostgreSQL có thể chọn Binh hoặc Chi. Không có cam kết ổn định giữa các hàng **bằng nhau trên toàn bộ biểu thức `ORDER BY`**.

Việc đôi lúc nhìn thấy đúng cùng một kết quả qua nhiều lần chạy không phải bằng chứng về thứ tự được bảo đảm. Index, kế hoạch thực thi, dữ liệu mới và phiên bản hệ quản trị đều có thể làm thứ tự giữa các hàng đồng điểm thay đổi.

Nếu yêu cầu là **chọn chính xác N hàng có thể tái lập**, hãy kết thúc `ORDER BY` bằng một cột hoặc tổ hợp cột **duy nhất**, ví dụ khóa chính:

```sql
ORDER BY points DESC, member_id ASC
```

Thứ tự này là cách **phá hòa để chọn N hàng**; nó **không có nghĩa** người có `member_id` nhỏ thực sự giỏi hơn nếu điểm bằng nhau.

### 3.2. SQL chuẩn với FETCH FIRST ... ONLY

Một cách diễn đạt tương đương trong PostgreSQL và các hệ hỗ trợ cú pháp row limiting chuẩn là:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
FETCH FIRST 3 ROWS ONLY;
```

`FETCH FIRST 3 ROWS ONLY` lấy tối đa 3 hàng sau khi sắp xếp. Trên nhiều hệ, `FETCH NEXT 3 ROWS ONLY` cũng được dùng trong ngữ cảnh phân trang.

Nếu toàn bộ tập kết quả chỉ có hai hàng phù hợp, yêu cầu `LIMIT 3` hoặc `FETCH FIRST 3 ROWS ONLY` trả **hai hàng**, không thêm một hàng giả để đủ ba. Nếu `N = 0` với cú pháp hỗ trợ, kết quả không có hàng; ở tầng ứng dụng nên kiểm tra yêu cầu phân trang để tránh giá trị âm hoặc kích thước trang không hợp lý.

## 4. “Lấy 3 hàng kèm đồng hạng ở ranh giới” là yêu cầu khác

Bây giờ yêu cầu là:

> Chọn 3 vị trí đầu theo điểm; nếu vị trí cuối có người đồng điểm thì **giữ tất cả người đồng điểm đó**.

Những người ở vị trí thứ 3 và 4 đều có 920 điểm: Binh và Chi. Vì vậy, kết quả đúng phải gồm **4 người**: An, Khoa, Binh, Chi.

PostgreSQL từ phiên bản 13 hỗ trợ `FETCH FIRST ... WITH TIES`:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC
FETCH FIRST 3 ROWS WITH TIES;
```

Kết quả có bốn hàng. Tuy nhiên, trong hai hàng 920 điểm, thứ tự hiển thị không được xác định bởi `ORDER BY points DESC`. Nếu cần **hiển thị ổn định mà vẫn giữ đồng hạng theo điểm**, dùng một lớp truy vấn ngoài:

```sql
SELECT member_id, display_name, points
FROM (
    SELECT member_id, display_name, points
    FROM ranking_scores
    WHERE points IS NOT NULL
    ORDER BY points DESC
    FETCH FIRST 3 ROWS WITH TIES
) AS selected
ORDER BY points DESC, member_id ASC;
```

Bảng kết quả:

| Người | Điểm | Lý do được chọn |
| --- | ---: | --- |
| An | 980 | Vị trí 1 |
| Khoa | 950 | Vị trí 2 |
| Binh | 920 | Vị trí 3 |
| Chi | 920 | Đồng điểm với vị trí 3 |

Sơ đồ chọn hàng:

```text
Điểm giảm dần      Vị trí theo một thứ tự phụ
980  An             1   ┐
950  Khoa           2   │  Ba vị trí đầu
920  Binh           3   ┘
920  Chi            4   ← Giữ thêm vì cùng điểm ranh giới
880  Lam            5
880  Minh           6
...
```

**Lưu ý đặc biệt:** `WITH TIES` xác định đồng hạng bằng **toàn bộ biểu thức `ORDER BY` của chính truy vấn có `FETCH`**, không bằng cách nhìn một cột mà người viết tùy ý coi là điểm.

### 4.1. Sai lầm: thêm member_id trong ORDER BY của WITH TIES

Câu sau có vẻ “vừa ổn định vừa bao gồm đồng hạng”:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
FETCH FIRST 3 ROWS WITH TIES;
```

Nhưng nó **chỉ trả 3 hàng** trong dữ liệu mẫu, vì hai người Binh và Chi có `member_id` khác nhau. Các tổ hợp khóa sắp xếp:

```text
(920, 2)
(920, 3)
```

không đồng hạng trên **cả `points` và `member_id`**.

Muốn đồng hạng chỉ theo `points`, hãy:

1. Chọn bằng `ORDER BY points DESC FETCH ... WITH TIES` ở truy vấn trong.
2. Sắp xếp lại bằng `points DESC, member_id ASC` ở truy vấn ngoài để có thứ tự hiển thị ổn định.

Đây là điểm rất dễ sai: **khóa phụ để phá hòa và tiêu chí để công nhận đồng hạng có thể là hai tập cột khác nhau**.

### 4.2. WITH TIES không bảo đảm có đúng N hàng

`FETCH FIRST N ROWS WITH TIES` có thể trả nhiều hơn N hàng; nếu vị trí N nằm trong một nhóm điểm lớn thì có thể trả rất nhiều hàng. Ví dụ một kỳ thi có 10.000 người cùng điểm, `WITH TIES` có thể mở rộng kết quả đáng kể khi nhóm điểm đó nằm tại ranh giới.

Vì thế, API phải công bố rõ:

- “`pageSize = 3` nghĩa là **tối đa 3 hàng**” → không dùng WITH TIES cho trang cố định.
- “`topN = 3` nghĩa là **giữ thêm tất cả đồng hạng ở ranh giới**” → số hàng trả về có thể vượt 3.

Không mặc định rằng `WITH TIES` là cách phân trang có số hàng cố định.

## 5. Ba hàm cửa sổ: ROW_NUMBER, RANK và DENSE_RANK

Khi bài toán yêu cầu xử lý đồng hạng có kiểm soát, **window function** là công cụ quan trọng. Chúng gán thứ tự hoặc hạng cho mỗi hàng trong tập mà không gộp hàng như `GROUP BY`.

Cú pháp cơ bản:

```sql
FUNCTION_NAME() OVER (
    PARTITION BY ...
    ORDER BY ...
)
```

- `ORDER BY` **bên trong `OVER`** quyết định thứ tự để đánh số/xếp hạng.
- `PARTITION BY` chia dữ liệu thành những nhóm xếp hạng độc lập; có thể bỏ khi muốn xếp hạng toàn bộ.
- `ROW_NUMBER()` gán số thứ tự duy nhất cho mỗi hàng trong phạm vi cửa sổ.
- `RANK()` cho cùng hạng với các hàng đồng điểm nhưng **bỏ số hạng** sau nhóm đồng hạng.
- `DENSE_RANK()` cho cùng hạng và **không bỏ số hạng**.

### 5.1. Quan sát cả ba cột hạng trên cùng dữ liệu

```sql
SELECT
    member_id,
    display_name,
    points,
    ROW_NUMBER() OVER (
        ORDER BY points DESC, member_id ASC
    ) AS row_num,
    RANK() OVER (
        ORDER BY points DESC
    ) AS competition_rank,
    DENSE_RANK() OVER (
        ORDER BY points DESC
    ) AS dense_rank
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC;
```

Kết quả:

| Người | Điểm | `ROW_NUMBER` | `RANK` | `DENSE_RANK` |
| --- | ---: | ---: | ---: | ---: |
| An | 980 | 1 | 1 | 1 |
| Khoa | 950 | 2 | 2 | 2 |
| Binh | 920 | 3 | 3 | 3 |
| Chi | 920 | 4 | 3 | 3 |
| Lam | 880 | 5 | 5 | 4 |
| Minh | 880 | 6 | 5 | 4 |
| Dung | 860 | 7 | 7 | 5 |
| Hanh | 860 | 8 | 7 | 5 |
| Giang | 790 | 9 | 9 | 6 |
| Nga | 720 | 10 | 10 | 7 |

Kết quả cho thấy sự khác biệt:

```text
Điểm       980  950  920  920  880  880  860  860  790  720
ROW_NUMBER   1    2    3    4    5    6    7    8    9   10
RANK         1    2    3    3    5    5    7    7    9   10
DENSE_RANK   1    2    3    3    4    4    5    5    6    7
```

Hai người có 920 điểm được xếp hạng `3` theo `RANK`; hạng tiếp theo là `5` vì có 4 người ở trước nhóm 880. Trong `DENSE_RANK`, mức điểm 880 tiếp tục hạng `4`.

**Lưu ý:** Trong câu trên, `ROW_NUMBER` có thêm `member_id` để đánh số ổn định, còn `RANK` và `DENSE_RANK` chỉ dùng `points` nhằm **giữ quan hệ đồng điểm**. Nếu thêm `member_id` vào `RANK() OVER (ORDER BY ...)` thì có thể không còn người đồng hạng vì khóa chính là duy nhất.

### 5.2. Lọc theo window function phải dùng truy vấn ngoài hoặc CTE

Trong PostgreSQL, không dùng trực tiếp một window function trong `WHERE` của cùng cấp truy vấn như sau:

```sql
-- Sai cú pháp/ngữ cảnh trong PostgreSQL:
SELECT member_id, points
FROM ranking_scores
WHERE RANK() OVER (ORDER BY points DESC) <= 3;
```

Window function được tính sau giai đoạn lọc `WHERE` về mặt logic. Vì vậy, hãy dùng CTE:

```sql
WITH ranked AS (
    SELECT
        member_id,
        display_name,
        points,
        RANK() OVER (ORDER BY points DESC) AS score_rank
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT member_id, display_name, points, score_rank
FROM ranked
WHERE score_rank <= 3
ORDER BY points DESC, member_id ASC;
```

Kết quả là An, Khoa, Binh và Chi.

Một số hệ quản trị hỗ trợ mệnh đề `QUALIFY` để lọc kết quả window function, nhưng PostgreSQL không có `QUALIFY` chuẩn trong truy vấn thông thường; CTE hoặc subquery là cách dễ hiểu và linh hoạt khi cần viết SQL trên nhiều nền tảng.

## 6. Phân biệt chính xác “N hàng có ties” với “N mức hạng”

Có một khác biệt rất quan trọng:

- `FETCH FIRST N ROWS WITH TIES`: bắt đầu từ **N hàng đầu**, sau đó mở rộng nếu hàng tại ranh giới có đồng hạng.
- `RANK() <= N`: chọn những người có **hạng thi đấu không lớn hơn N**; với cùng biểu thức sắp xếp và cùng tập dữ liệu, ý nghĩa tương ứng với lấy N hàng rồi mở rộng đồng hạng.
- `DENSE_RANK() <= N`: chọn **N mức giá trị xếp hạng khác nhau** đầu tiên, có thể nhận nhiều hơn cách lấy N hàng kèm ties.

Với dữ liệu mẫu, xét `N = 4`:

| Cách chọn | Những người được lấy | Số hàng |
| --- | --- | ---: |
| `ROW_NUMBER <= 4` | An, Khoa, Binh, Chi | 4 |
| `FETCH FIRST 4 ROWS WITH TIES` theo điểm | An, Khoa, Binh, Chi | 4 |
| `RANK <= 4` theo điểm | An, Khoa, Binh, Chi | 4 |
| `DENSE_RANK <= 4` theo điểm | An, Khoa, Binh, Chi, Lam, Minh | 6 |

Giải thích: sau nhóm 920 điểm, mức điểm 880 là **mức thứ 4**, nên `DENSE_RANK <= 4` lấy cả Lam và Minh. Nhưng theo quy tắc thứ hạng thi đấu, nhóm 880 bắt đầu tại vị trí/hạng **5**, vì đã có 4 người ở các điểm cao hơn; do đó `RANK <= 4` không lấy nhóm này.

### 6.1. Lấy 4 người đầu, có phá hòa

```sql
WITH ranked AS (
    SELECT
        member_id,
        display_name,
        points,
        ROW_NUMBER() OVER (
            ORDER BY points DESC, member_id ASC
        ) AS rn
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT member_id, display_name, points
FROM ranked
WHERE rn <= 4
ORDER BY points DESC, member_id ASC;
```

Đúng 4 người: An, Khoa, Binh, Chi. Nếu đổi N thành 3, người ở ranh giới 920 sẽ được chọn theo `member_id` nhỏ nhất.

### 6.2. Lấy 4 vị trí đầu và giữ đồng hạng theo điểm

```sql
WITH ranked AS (
    SELECT
        member_id,
        display_name,
        points,
        RANK() OVER (
            ORDER BY points DESC
        ) AS score_rank
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT member_id, display_name, points
FROM ranked
WHERE score_rank <= 4
ORDER BY points DESC, member_id ASC;
```

Kết quả cũng là 4 người trong dữ liệu mẫu vì vị trí thứ 4 vẫn thuộc nhóm 920. Nếu đổi N thành 5, kết quả sẽ là 6 người: thêm Lam và Minh cùng điểm 880.

### 6.3. Lấy 4 mức điểm cao nhất

```sql
WITH ranked AS (
    SELECT
        member_id,
        display_name,
        points,
        DENSE_RANK() OVER (
            ORDER BY points DESC
        ) AS score_level
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT member_id, display_name, points, score_level
FROM ranked
WHERE score_level <= 4
ORDER BY points DESC, member_id ASC;
```

Kết quả có 6 người: 980, 950, 920, 920, 880, 880. Đây là **top 4 mức điểm**, không phải “4 vị trí đầu bao gồm đồng hạng” theo định nghĩa thông thường của `WITH TIES`.

## 7. Giữ đồng hạng theo thứ tự tổng hợp nhiều cột

Không phải mọi cuộc thi chỉ có một cột điểm. Giả sử doanh nghiệp quy định:

1. Ưu tiên điểm `points` cao nhất.
2. Nếu bằng điểm, ưu tiên số lần hoàn thành mục tiêu `completed_tasks` cao hơn.
3. Nếu vẫn bằng cả hai chỉ số, coi là đồng hạng thực sự.

Khi đó tiêu chí đồng hạng có thể được xác định bởi **cặp `(points, completed_tasks)`**:

```sql
-- Ví dụ cấu trúc, giả sử bảng có thêm completed_tasks:
SELECT member_id, display_name, points, completed_tasks
FROM ranking_with_tasks
ORDER BY points DESC, completed_tasks DESC
FETCH FIRST 3 ROWS WITH TIES;
```

Bảng `ranking_with_tasks` là ví dụ khái niệm, không nằm trong bộ dữ liệu tạm đầu bài. Người dùng cần tạo thêm cột và dữ liệu nếu muốn thực thi.

Những người **chỉ bằng điểm nhưng khác số task** không được xem là đồng hạng trong quy tắc này. Ngược lại, nếu `completed_tasks` chỉ để **phân định ai được hiển thị trước**, không được coi là tiêu chí thành tích, thì không nên đưa nó vào `ORDER BY` của truy vấn có `WITH TIES`. Khi đó nên chọn ties theo điểm trong truy vấn con và sắp xếp kết quả ngoài.

Một cách đặt câu hỏi trước khi lập trình:

> “Hai người được coi là đồng hạng nếu bằng nhau trên những cột nào?”

Câu trả lời quyết định `ORDER BY` của `RANK`, `DENSE_RANK` hoặc `WITH TIES`. Thêm một cột duy nhất vào điều kiện xếp hạng có thể khiến **mọi tie biến mất**; thêm cột riêng cho **thứ tự trình bày** thì không cần làm thay đổi tập được chọn.

## 8. Top N trong từng nhóm: PARTITION BY

Yêu cầu: **Mỗi team chọn 2 người có điểm cao nhất, giữ thêm những người đồng điểm tại vị trí thứ 2**.

Không thể dùng một `LIMIT 2` ở cuối truy vấn chung, vì nó chỉ giới hạn **toàn bộ kết quả**, không giới hạn **mỗi nhóm**. Cần xếp hạng riêng trong từng team bằng `PARTITION BY`.

```sql
WITH team_ranked AS (
    SELECT
        member_id,
        display_name,
        team,
        points,
        RANK() OVER (
            PARTITION BY team
            ORDER BY points DESC
        ) AS team_rank
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT member_id, display_name, team, points, team_rank
FROM team_ranked
WHERE team_rank <= 2
ORDER BY team, team_rank, member_id;
```

Kết quả:

| Team | Người | Điểm | Hạng trong team |
| --- | --- | ---: | ---: |
| Sales | An | 980 | 1 |
| Sales | Binh | 920 | 2 |
| Sales | Chi | 920 | 2 |
| Support | Khoa | 950 | 1 |
| Support | Lam | 880 | 2 |
| Support | Minh | 880 | 2 |

Mỗi team có 3 người được chọn dù yêu cầu bắt đầu từ **2 vị trí đầu**, bởi người ở hạng 2 đồng điểm.

### 8.1. Chính xác 2 người mỗi team

Nếu doanh nghiệp muốn đúng hai người, dùng `ROW_NUMBER` với khóa phụ:

```sql
WITH team_numbered AS (
    SELECT
        member_id,
        display_name,
        team,
        points,
        ROW_NUMBER() OVER (
            PARTITION BY team
            ORDER BY points DESC, member_id ASC
        ) AS team_row
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT member_id, display_name, team, points
FROM team_numbered
WHERE team_row <= 2
ORDER BY team, team_row;
```

Kết quả:

- Sales: An, Binh.
- Support: Khoa, Lam.

Chi và Minh có cùng điểm với người thứ 2 trong team nhưng không được chọn, vì quy tắc `member_id ASC` đã phân định.

### 8.2. Ba mức điểm cao nhất của mỗi team

Nếu yêu cầu là “lấy **3 mức điểm** của mỗi team”, sử dụng `DENSE_RANK`:

```sql
WITH team_levels AS (
    SELECT
        member_id,
        display_name,
        team,
        points,
        DENSE_RANK() OVER (
            PARTITION BY team
            ORDER BY points DESC
        ) AS level_no
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT team, display_name, points, level_no
FROM team_levels
WHERE level_no <= 3
ORDER BY team, level_no, member_id;
```

Kết quả Sales: An (980), Binh và Chi (920), Dung và Hanh (860). Support: Khoa (950), Lam và Minh (880), Nga (720). Số hàng trên mỗi team khác nhau vì mỗi mức điểm có thể chứa nhiều người.

**Quan sát:** Với Sales, `RANK <= 3` sẽ **không** lấy nhóm 860 vì hạng của họ là 4, còn `DENSE_RANK <= 3` thì có. Đây là lý do phải phân biệt “3 vị trí đầu có đồng hạng” và “3 mức điểm đầu”.

## 9. Lấy Top N sau GROUP BY và phép tổng hợp

Trong báo cáo kinh doanh, “top 3 khách hàng theo doanh thu” yêu cầu **tính doanh thu theo khách hàng trước**, rồi mới chọn top. Nếu giới hạn các dòng giao dịch trước khi tổng hợp, số liệu có thể sai.

Giả sử có bảng giao dịch:

```sql
CREATE TEMP TABLE demo_sales (
    sale_id     INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount      NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    status      TEXT NOT NULL CHECK (status IN ('paid', 'cancelled'))
);

INSERT INTO demo_sales (sale_id, customer_id, amount, status) VALUES
    (1, 101, 150.00, 'paid'),
    (2, 101,  50.00, 'paid'),
    (3, 102, 200.00, 'paid'),
    (4, 103, 180.00, 'paid'),
    (5, 104,  40.00, 'paid'),
    (6, 104, 160.00, 'paid'),
    (7, 105, 300.00, 'cancelled');
```

Quy tắc doanh thu ở đây chỉ tính `status = 'paid'`:

| Khách | Doanh thu paid |
| ---: | ---: |
| 101 | 200.00 |
| 102 | 200.00 |
| 103 | 180.00 |
| 104 | 200.00 |
| 105 | 0.00 (không có giao dịch paid) |

Yêu cầu: **Lấy 2 vị trí doanh thu cao nhất và giữ người đồng hạng**.

```sql
WITH customer_revenue AS (
    SELECT
        customer_id,
        SUM(amount) AS revenue
    FROM demo_sales
    WHERE status = 'paid'
    GROUP BY customer_id
)
SELECT customer_id, revenue
FROM customer_revenue
ORDER BY revenue DESC
FETCH FIRST 2 ROWS WITH TIES;
```

Kết quả có **3 khách 101, 102, 104**, mỗi khách có doanh thu 200. Bởi người ở vị trí 2 có doanh thu 200, những khách khác cùng mức doanh thu cũng được giữ. Với một cột điểm ngang bằng, thứ tự ba khách có thể không cố định; nếu cần hiển thị ổn định, bọc truy vấn trong một lớp và sắp tiếp theo `customer_id ASC`.

Cũng có thể dùng `RANK`:

```sql
WITH customer_revenue AS (
    SELECT customer_id, SUM(amount) AS revenue
    FROM demo_sales
    WHERE status = 'paid'
    GROUP BY customer_id
),
ranked AS (
    SELECT
        customer_id,
        revenue,
        RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
    FROM customer_revenue
)
SELECT customer_id, revenue, revenue_rank
FROM ranked
WHERE revenue_rank <= 2
ORDER BY revenue DESC, customer_id;
```

### Sai lầm: LIMIT trước SUM

```sql
-- Sai ý nghĩa nếu yêu cầu là khách hàng có tổng doanh thu cao nhất:
SELECT customer_id, SUM(amount) AS revenue
FROM (
    SELECT customer_id, amount
    FROM demo_sales
    WHERE status = 'paid'
    ORDER BY amount DESC
    LIMIT 2
) AS two_largest_transactions
GROUP BY customer_id;
```

Truy vấn này chỉ chọn **2 giao dịch có số tiền lớn nhất**, rồi mới cộng theo khách. Nó không xét tất cả giao dịch của mỗi khách nên không trả lời được câu hỏi “khách có tổng doanh thu cao nhất”.

**Grain** (cấp độ mỗi hàng) quyết định đúng sai:

```text
Mỗi hàng giao dịch
     ↓ lọc paid
Mỗi hàng giao dịch paid
     ↓ GROUP BY customer_id
Mỗi hàng khách hàng + tổng doanh thu
     ↓ xếp hạng doanh thu
Top khách hàng
```

Chỉ áp dụng Top N sau khi tập đầu vào đã đạt **đúng cấp độ mà nghiệp vụ muốn xếp hạng**.

## 10. NULL ảnh hưởng đến hàng đầu và đồng hạng ra sao?

Bảng `ranking_scores` có hai người chưa có điểm. Trong PostgreSQL, mặc định của `ORDER BY` là:

- `ASC`: giá trị `NULL` thường đứng **cuối**.
- `DESC`: giá trị `NULL` thường đứng **đầu**.

Vì vậy, lệnh:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
ORDER BY points DESC
LIMIT 3;
```

có thể chọn **Phuc và Quynh chưa có điểm** vào những hàng đầu thay vì chọn người có điểm cao nhất. Đây là lý do cần xác định rõ chính sách `NULL`.

### 10.1. Ba cách xử lý với ba ý nghĩa khác nhau

**Cách A — Chỉ xếp hạng người đã có điểm:**

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id
LIMIT 3;
```

Đây là chính sách đang dùng ở hầu hết các ví dụ trong bài.

**Cách B — Hiển thị người chưa có điểm ở cuối:**

```sql
SELECT member_id, display_name, points
FROM ranking_scores
ORDER BY points DESC NULLS LAST, member_id
LIMIT 3;
```

Nếu một giới hạn N lớn đến mức bao gồm các hàng `NULL`, chúng vẫn có thể xuất hiện. Với `WITH TIES` chỉ theo `points`, các hàng `NULL` còn có thể được coi cùng một nhóm ngang nhau về khóa sắp xếp; hãy định nghĩa liệu chúng có được xếp hạng hay không.

**Cách C — Coi chưa có điểm là 0:**

```sql
SELECT member_id, display_name, points
FROM ranking_scores
ORDER BY COALESCE(points, 0) DESC, member_id
LIMIT 3;
```

Cách này thay đổi **ý nghĩa dữ liệu**: điểm chưa biết trở thành tương đương 0 để sắp xếp. Nó chỉ phù hợp nếu nghiệp vụ thật sự xác nhận quy ước đó. Nếu 0 nghĩa là đã chấm và đạt 0 điểm, `NULL` là chưa chấm, thì không nên đánh đồng.

### 10.2. Cú pháp sắp xếp NULL khác nhau theo DBMS

Không nên dựa vào mặc định `NULL` của một hệ quản trị khi chuyển ứng dụng sang hệ khác. PostgreSQL và Oracle hỗ trợ `NULLS FIRST`/`NULLS LAST`; một số hệ quản trị dùng quy tắc khác hoặc không hỗ trợ cùng cú pháp.

Một kỹ thuật diễn đạt thứ tự theo trạng thái có thể dùng trong nhiều hệ:

```sql
ORDER BY
    CASE WHEN points IS NULL THEN 1 ELSE 0 END ASC,
    points DESC,
    member_id ASC
```

Biểu thức `CASE` tạo khóa `0` cho người có điểm và `1` cho người thiếu, đưa người thiếu xuống cuối. Tuy nhiên, khi định nghĩa **đồng hạng theo điểm**, tránh vô tình thêm `member_id` vào tập khóa xếp hạng của `WITH TIES` hoặc `RANK`.

## 11. Phân trang: cố định số hàng hay không cắt nhóm đồng hạng?

Lấy Top N và phân trang có liên quan nhưng không hoàn toàn giống nhau.

### 11.1. Phân trang với LIMIT/OFFSET

Yêu cầu: mỗi trang đúng tối đa 3 người đã có điểm, sắp theo điểm rồi ID.

Trang 1:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
LIMIT 3 OFFSET 0;
```

Kết quả: An, Khoa, Binh.

Trang 2:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
LIMIT 3 OFFSET 3;
```

Kết quả: Chi, Lam, Minh.

**Điểm đáng chú ý:** Binh ở trang 1 và Chi ở trang 2 **bằng điểm 920**. Điều đó hợp lý khi yêu cầu là **trang có tối đa 3 hàng**; trang cố định có thể chia cắt một nhóm đồng hạng.

Nếu sản phẩm yêu cầu “không được chia người đồng hạng qua hai trang”, phải thay đổi hợp đồng phân trang; số hàng mỗi trang có thể không còn cố định.

### 11.2. Phân trang theo nhóm điểm

Một cách thiết kế là chọn **tối đa N người rồi mở rộng toàn bộ nhóm đồng hạng ở ranh giới** cho mỗi lần tải:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC
FETCH FIRST 3 ROWS WITH TIES;
```

Trang đầu có 4 người: An, Khoa, Binh, Chi. Điểm cuối cùng của trang là `920`.

Trang tiếp theo có thể bắt đầu từ **những mức điểm thấp hơn 920**:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
  AND points < 920
ORDER BY points DESC
FETCH FIRST 3 ROWS WITH TIES;
```

Kết quả trang tiếp: Lam, Minh (880), Dung, Hanh (860), tức 4 người. Khóa tiếp tục là điểm `860`. Cách này bảo đảm không tách một nhóm điểm bằng nhau giữa các trang **khi tiêu chí nhóm chỉ là `points` và dữ liệu không thay đổi trong phiên phân trang**.

Đổi lại, trang có thể dài ngắn khác nhau; cách này không trả lời yêu cầu “mỗi trang luôn đúng 3 người”. Với dữ liệu thường xuyên cập nhật điểm, cần quy định snapshot/phiên bản báo cáo nếu muốn một tập kết quả nhất quán.

### 11.3. Keyset pagination cho thứ tự có khóa phụ

Khi cần **trang có số hàng cố định** và tập dữ liệu lớn, keyset pagination tránh một số vấn đề của `OFFSET`. Giả sử trang đầu đã lấy 3 hàng theo:

```sql
ORDER BY points DESC, member_id ASC
```

Hàng cuối trang là `(points = 920, member_id = 2)`. Trang tiếp theo tìm các hàng nằm **sau khóa đó**:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
  AND (
      points < 920
      OR (points = 920 AND member_id > 2)
  )
ORDER BY points DESC, member_id ASC
LIMIT 3;
```

Kết quả là Chi, Lam, Minh. Biểu thức phải theo đúng **chiều của từng cột trong ORDER BY**: `points DESC` nghĩa là các điểm thấp hơn đi sau; `member_id ASC` nghĩa là ID cao hơn đi sau khi cùng điểm.

Keyset có những ưu điểm:

- Không phải bỏ qua một lượng hàng ngày càng lớn như `OFFSET` khi đi sâu vào danh sách.
- Hạn chế lặp/bỏ sót do các hàng mới được chèn **trước vị trí con trỏ** khi chỉ lật trang tiếp.
- Cung cấp điểm bắt đầu rõ ràng dựa trên khóa sắp xếp đã trả.

Nhưng keyset **không tự đảm bảo snapshot nhất quán** nếu các hàng hiện có bị cập nhật điểm, bị xóa, hoặc có các thay đổi làm chúng dịch chuyển qua con trỏ. Khi cần một bảng xếp hạng cố định trong toàn bộ phiên duyệt, ứng dụng có thể cần snapshot transaction, mốc phiên bản báo cáo hoặc bảng kết quả được chốt trước.

### 11.4. Hạn chế của OFFSET dù có thứ tự đầy đủ

Giả sử trang 1 đã trả An, Khoa, Binh. Giữa hai lần đọc, có một người mới xuất hiện ở điểm 970 và được chèn lên gần đầu danh sách. Câu `OFFSET 3` ở trang 2 có thể trả lại Binh, bởi vị trí các hàng đã dịch chuyển. Việc thêm khóa phụ duy nhất giúp thứ tự **xác định trong một trạng thái dữ liệu**, nhưng không ngăn sự dịch chuyển do dữ liệu thay đổi giữa các lần truy vấn.

Vì vậy, cần phân biệt hai yêu cầu:

- **Thứ tự ổn định trong mỗi lần truy vấn:** dùng `ORDER BY` đủ khóa phân định.
- **Dữ liệu nhất quán qua nhiều lần truy vấn:** cần cơ chế phiên bản hoặc snapshot phù hợp.

## 12. Quy tắc nghiệp vụ cho đồng hạng trong báo cáo

Một hệ thống thực tế nên mô tả cụ thể thế nào là đồng hạng. Một số ví dụ:

| Bài toán | “Đồng hạng” là gì? | Cách làm SQL thường phù hợp |
| --- | --- | --- |
| 3 người có điểm cao nhất, chọn đúng 3 | Không cần giữ tất cả người cùng điểm | `ORDER BY points DESC, member_id ASC LIMIT 3` |
| 3 vị trí đầu, giữ mọi người cùng điểm tại ranh giới | Bằng `points` | `FETCH FIRST 3 ROWS WITH TIES` hoặc `RANK <= 3` |
| 3 mức điểm khác nhau cao nhất | Cùng một mức điểm là một hạng dày đặc | `DENSE_RANK <= 3` |
| 2 người mỗi phòng ban, đúng 2 | Thứ tự trong từng phòng ban có khóa phá hòa | `ROW_NUMBER OVER (PARTITION BY team ...) <= 2` |
| 2 vị trí mỗi phòng ban, giữ đồng điểm | Bằng điểm trong cùng team | `RANK OVER (PARTITION BY team ORDER BY points DESC) <= 2` |
| Danh sách phân trang cố định 20 hàng | Cho phép nhóm điểm nằm ở hai trang | `LIMIT/OFFSET` hoặc keyset trên thứ tự đầy đủ |
| Trang không cắt nhóm đồng điểm | Toàn bộ nhóm điểm ranh giới ở cùng trang | `WITH TIES` theo điểm, cursor sang mức điểm thấp hơn |

Khi được yêu cầu “top N”, không nên tự quyết định xử lý hòa theo cảm giác; ngay cả khi SQL có cú pháp rất ngắn, lựa chọn sai sẽ ảnh hưởng số người nhận thưởng, số bản ghi xuất file, kích thước trang hoặc tổng số bản ghi mà API báo cho client.

## 13. Khác biệt cú pháp giữa các hệ quản trị

Các hệ quản trị SQL hỗ trợ giới hạn số hàng và đồng hạng qua nhiều cú pháp. Hãy kiểm tra phiên bản cụ thể trước khi sao chép đoạn SQL.

### 13.1. PostgreSQL

PostgreSQL hỗ trợ `LIMIT`/`OFFSET` và cú pháp `FETCH FIRST ...`. Từ PostgreSQL 13 có `WITH TIES`:

```sql
-- Chính xác tối đa 3 hàng, phá hòa bằng ID:
SELECT member_id, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
LIMIT 3;

-- 3 vị trí đầu, giữ đồng điểm ranh giới:
SELECT member_id, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC
FETCH FIRST 3 ROWS WITH TIES;
```

`ROW_NUMBER`, `RANK`, `DENSE_RANK` cũng được hỗ trợ; chúng đặc biệt phù hợp khi xếp hạng **mỗi nhóm**.

### 13.2. SQL Server

SQL Server dùng `TOP` cho giới hạn hàng đầu, và hỗ trợ `TOP (...) WITH TIES` khi có `ORDER BY`:

```sql
-- SQL Server: lấy đúng 3 hàng đầu có thứ tự phân định.
SELECT TOP (3) member_id, points
FROM dbo.ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC;

-- SQL Server: có thể trả hơn 3 hàng nếu đồng điểm ranh giới.
SELECT TOP (3) WITH TIES member_id, points
FROM dbo.ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC;
```

Tên bảng `dbo.ranking_scores` là giả định bảng đã được tạo trong SQL Server; đây không phải bảng tạm PostgreSQL của phần thực hành.

Trong SQL Server, `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` là cú pháp thường dùng cho phân trang, nhưng **không có `WITH TIES` trong cấu trúc OFFSET/FETCH đó** theo cùng cách `TOP ... WITH TIES`. Khi cần xếp hạng theo nhóm, dùng window function và CTE/subquery.

### 13.3. Oracle Database

Oracle Database (12c trở lên) có `FETCH FIRST ... ROWS ONLY` và `FETCH FIRST ... ROWS WITH TIES`:

```sql
-- Oracle:
SELECT member_id, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC
FETCH FIRST 3 ROWS WITH TIES;
```

Với các phiên bản Oracle cũ hơn, người viết thường gặp `ROWNUM`. Tuy nhiên, áp dụng `ROWNUM` trực tiếp trước khi sắp xếp có thể sai ý nghĩa “top sau ORDER BY”; cần đặt `ORDER BY` ở truy vấn con rồi giới hạn ở truy vấn ngoài theo cơ chế tương ứng. Khi có thể, dùng cú pháp row limiting phù hợp phiên bản để rõ nghĩa.

### 13.4. MySQL

MySQL thường dùng `LIMIT`:

```sql
-- MySQL:
SELECT member_id, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
LIMIT 3;
```

Trong MySQL 8.0, các window function như `ROW_NUMBER`, `RANK` và `DENSE_RANK` được hỗ trợ, nên có thể diễn đạt “giữ mọi người đồng điểm ranh giới” bằng `RANK`:

```sql
WITH ranked AS (
    SELECT member_id, points,
           RANK() OVER (ORDER BY points DESC) AS score_rank
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT member_id, points
FROM ranked
WHERE score_rank <= 3
ORDER BY points DESC, member_id;
```

Không mặc định rằng MySQL có `FETCH FIRST N ROWS WITH TIES` tương đương PostgreSQL/Oracle trong môi trường thông dụng. Cú pháp `LIMIT` tự nó **không có tùy chọn giữ đồng hạng**.

### 13.5. SQLite

SQLite hỗ trợ `LIMIT`/`OFFSET` và window function trong các phiên bản hiện đại (window function từ SQLite 3.25.0):

```sql
-- SQLite:
WITH ranked AS (
    SELECT member_id, points,
           RANK() OVER (ORDER BY points DESC) AS score_rank
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT member_id, points
FROM ranked
WHERE score_rank <= 3
ORDER BY points DESC, member_id;
```

SQLite không có cú pháp `FETCH FIRST ... WITH TIES` tương ứng như PostgreSQL 13+. Ngoài cú pháp, các hệ quản trị có quy tắc xử lý `NULL` khác nhau; khi chuyển hệ cần kiểm tra rõ thứ tự các giá trị thiếu.

### 13.6. Đối chiếu nhanh

| Hệ quản trị | Lấy chính xác N hàng | Giữ đồng hạng ở ranh giới |
| --- | --- | --- |
| PostgreSQL | `LIMIT N` hoặc `FETCH FIRST N ROWS ONLY` | `FETCH FIRST N ROWS WITH TIES` (13+) hoặc `RANK` |
| SQL Server | `TOP (N)` hoặc `OFFSET/FETCH` | `TOP (N) WITH TIES` hoặc `RANK` |
| Oracle | `FETCH FIRST N ROWS ONLY` (12c+) | `FETCH FIRST N ROWS WITH TIES` (12c+) hoặc `RANK` |
| MySQL | `LIMIT N` | `RANK` qua CTE/subquery (MySQL 8.0+) |
| SQLite | `LIMIT N` | `RANK` qua CTE/subquery (SQLite 3.25.0+) |

Nói “hỗ trợ RANK” không tự bảo đảm mọi đoạn SQL giống hệt nhau: kiểu dữ liệu, tên bảng, vị trí `WITH`, khả năng dùng tham số và cách đặt alias vẫn phụ thuộc hệ quản trị/driver.

## 14. Vấn đề hiệu năng khi chọn hàng đầu

Truy vấn:

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
LIMIT 3;
```

có thể được tối ưu tốt nếu có index phù hợp với bộ lọc và thứ tự sắp xếp. Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_ranking_scores_points_id
    ON ranking_scores (points DESC NULLS LAST, member_id ASC);
```

Index có thể giúp database đọc các hàng đầu mà không phải sắp xếp toàn bộ dữ liệu trong một số kế hoạch thực thi. Nhưng việc chọn index còn phụ thuộc độ lớn bảng, thống kê, bộ lọc, loại truy vấn và tần suất cập nhật điểm. Với bảng nhỏ 12 hàng, quét tuần tự rồi sắp xếp có thể nhanh hơn dùng index.

Xem kế hoạch của câu truy vấn trong PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
LIMIT 3;
```

`EXPLAIN ANALYZE` thực sự chạy câu truy vấn; ở đây là `SELECT` đọc dữ liệu. Các chỉ số nên quan sát gồm số hàng đầu vào, loại bước sắp xếp, số hàng được lấy và chi phí truy cập.

### 14.1. WITH TIES và RANK có thể phải đọc thêm nhiều hàng

Nếu yêu cầu giữ mọi người đồng điểm ở ranh giới, database cần biết nhóm đó kết thúc ở đâu. Do đó, `WITH TIES` không mặc nhiên có chi phí y hệt `LIMIT N`.

Truy vấn dùng `RANK` hoặc `DENSE_RANK` có thể phải sắp xếp/phân vùng một tập lớn trước khi lọc rank. Những bảng lớn và bài toán Top N mỗi nhóm cần thiết kế index phù hợp, có thể cân nhắc bảng tổng hợp/chốt dữ liệu định kỳ hoặc cách truy vấn được kiểm nghiệm theo yêu cầu ứng dụng. Không có bảo đảm một cách viết luôn nhanh nhất ở mọi engine.

### 14.2. Top N mỗi nhóm và index

Với truy vấn Top N mỗi team theo điểm, một index như:

```sql
CREATE INDEX idx_ranking_scores_team_points
    ON ranking_scores (team, points DESC NULLS LAST, member_id ASC);
```

có thể hữu ích với một số kế hoạch trên dữ liệu lớn, nhưng không bảo đảm loại bỏ mọi bước sắp xếp hay xử lý cửa sổ. Cần đo truy vấn thật, bởi index cũng tốn dung lượng và công cập nhật khi `points` thay đổi.

### 14.3. Phân trang sâu với OFFSET

`LIMIT 20 OFFSET 100000` có thể cần duyệt/loại bỏ rất nhiều hàng trước khi trả 20 hàng, tùy kế hoạch và index. Nếu ứng dụng duyệt tuần tự danh sách dài, keyset pagination thường là một hướng đáng cân nhắc; nếu ứng dụng cần “nhảy đến trang số 500”, lại có những yêu cầu thiết kế khác. Lựa chọn luôn phụ thuộc cách người dùng duyệt dữ liệu.

## 15. Những lỗi thường gặp với Top N và đồng hạng

| Cách viết hoặc giả định | Điều có thể sai | Cách xử lý |
| --- | --- | --- |
| `LIMIT 3` không `ORDER BY` | Không xác định “3 hàng đầu” theo tiêu chí nào | Luôn định nghĩa thứ tự nghiệp vụ |
| `ORDER BY score DESC LIMIT 3` với score trùng | Không xác định người nào ở ranh giới | Thêm khóa phụ duy nhất nếu cần đúng 3 người |
| `ORDER BY score DESC, id FETCH FIRST 3 ROWS WITH TIES` | ID duy nhất làm mất đồng hạng theo score | Chọn ties trong truy vấn trong theo score; sắp ID ở ngoài |
| Dùng `DENSE_RANK <= 3` cho “3 vị trí đầu bao gồm ties” | Có thể lấy quá nhiều mức điểm | Dùng `RANK <= 3` hoặc `WITH TIES` |
| Dùng `RANK <= 3` cho “3 mức điểm” | Có thể thiếu mức điểm thứ 3 nếu hạng bị nhảy | Dùng `DENSE_RANK <= 3` |
| `LIMIT 2` cuối cùng cho top 2 mỗi team | Chỉ lấy 2 hàng toàn bảng | Dùng window function với `PARTITION BY team` |
| Chưa tính `SUM` theo khách đã `LIMIT` giao dịch | Xếp hạng giao dịch thay vì khách | Tổng hợp về đúng grain trước khi xếp hạng |
| Bỏ qua `NULL` trong PostgreSQL `DESC` | Người chưa có điểm có thể đứng đầu | Lọc `IS NOT NULL` hoặc ghi rõ `NULLS LAST` |
| `OFFSET` khi dữ liệu thay đổi giữa các trang | Có thể lặp hoặc bỏ sót hàng | Thứ tự đầy đủ, keyset hoặc snapshot theo mục tiêu |
| Dùng `ROW_NUMBER` không có khóa phân định trong ties | Người được đánh số 1/2 giữa các tie có thể thay đổi | Thêm khóa phụ duy nhất trong `OVER ORDER BY` |
| Dùng WITH TIES như trang luôn có N hàng | Kết quả có thể vượt N rất nhiều | Công bố số hàng biến thiên hoặc chọn pagination cố định |
| Giả định ID lớn nhất là người mới nhất | ID không nhất thiết đại diện thời điểm nghiệp vụ | Dùng cột thời gian/kỳ phù hợp và khóa phá hòa |

## 16. Bài tập thực hành có đáp án

Các bài dưới đây dùng bảng `ranking_scores` ở phần 2, trừ khi ghi rõ dùng `demo_sales`.

### Bài 1 — Lấy đúng 3 người điểm cao nhất

Yêu cầu: nếu bằng điểm, chọn `member_id` nhỏ hơn trước.

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
LIMIT 3;
```

**Đáp án:** An (980), Khoa (950), Binh (920). Chi có 920 điểm nhưng ở vị trí thứ tư theo ID.

### Bài 2 — Lấy 3 vị trí đầu, giữ đồng điểm

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC
FETCH FIRST 3 ROWS WITH TIES;
```

**Đáp án:** An, Khoa, Binh, Chi — **4 hàng**. Hai người cùng 920 điểm được giữ vì nằm tại ranh giới thứ ba.

### Bài 3 — Nếu thêm member_id vào FETCH WITH TIES thì sao?

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
FETCH FIRST 3 ROWS WITH TIES;
```

**Đáp án:** Chỉ có An, Khoa, Binh — **3 hàng**. Chi không đồng hạng với Binh trên **toàn bộ cặp (points, member_id)**. Nếu nghiệp vụ chỉ định đồng điểm theo `points`, đây là cách viết sai yêu cầu.

### Bài 4 — Khác nhau giữa RANK và DENSE_RANK ở N = 4

Hãy dự đoán số người được lấy bởi:

```sql
WITH ranked AS (
    SELECT member_id, display_name, points,
           RANK() OVER (ORDER BY points DESC) AS r,
           DENSE_RANK() OVER (ORDER BY points DESC) AS dr
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT
    COUNT(*) FILTER (WHERE r <= 4) AS rank_count,
    COUNT(*) FILTER (WHERE dr <= 4) AS dense_count
FROM ranked;
```

**Đáp án PostgreSQL:** `rank_count = 4`; `dense_count = 6`. Mức điểm 880 là hạng 5 theo `RANK` nhưng mức thứ 4 theo `DENSE_RANK`. `FILTER` trên aggregate là cú pháp được PostgreSQL hỗ trợ; nếu hệ không hỗ trợ, có thể dùng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.

### Bài 5 — Top 2 mỗi team có đồng hạng

```sql
WITH ranked AS (
    SELECT team, display_name, points, member_id,
           RANK() OVER (
               PARTITION BY team ORDER BY points DESC
           ) AS team_rank
    FROM ranking_scores
    WHERE points IS NOT NULL
)
SELECT team, display_name, points
FROM ranked
WHERE team_rank <= 2
ORDER BY team, points DESC, member_id;
```

**Đáp án:** Sales gồm An, Binh, Chi; Support gồm Khoa, Lam, Minh. Mỗi team trả 3 hàng vì có hai người cùng điểm ở hạng 2.

### Bài 6 — Top 3 mức điểm mỗi team

Thay `RANK` của bài 5 bằng `DENSE_RANK` và lọc `<= 3`. Những người nào được chọn?

**Đáp án:** Sales gồm An (980), Binh và Chi (920), Dung và Hanh (860); Support gồm Khoa (950), Lam và Minh (880), Nga (720). Đây là **ba mức điểm khác nhau** của từng team.

### Bài 7 — Phân trang chính xác 3 hàng

Trang đầu theo `points DESC, member_id ASC` là An, Khoa, Binh. Hãy viết câu lấy trang tiếp bằng `OFFSET`.

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
ORDER BY points DESC, member_id ASC
LIMIT 3 OFFSET 3;
```

**Đáp án:** Chi, Lam, Minh. Việc Binh và Chi thuộc hai trang khác nhau **không phải lỗi** khi hợp đồng là trang cố định 3 hàng.

### Bài 8 — Phân trang bằng keyset

Trang đầu kết thúc ở `(points = 920, member_id = 2)`. Hãy lấy ba hàng tiếp theo mà không dùng `OFFSET`.

```sql
SELECT member_id, display_name, points
FROM ranking_scores
WHERE points IS NOT NULL
  AND (
      points < 920
      OR (points = 920 AND member_id > 2)
  )
ORDER BY points DESC, member_id ASC
LIMIT 3;
```

**Đáp án:** Chi, Lam, Minh. Tham số con trỏ trong ứng dụng thực tế nên được lấy từ hàng cuối trang, không cố định thành 920 và 2.

### Bài 9 — Nhóm doanh thu

Trong bảng `demo_sales`, khách 101, 102, 104 đều có tổng giao dịch paid bằng 200; khách 103 có 180; giao dịch 300 của khách 105 bị hủy. `FETCH FIRST 2 ROWS WITH TIES` sau `GROUP BY customer_id` trả những khách nào?

**Đáp án:** 101, 102, 104 — ba khách đồng hạng 200. Nếu chọn `LIMIT 2` có khóa phụ `customer_id ASC` thì chỉ lấy 101 và 102.

### Bài 10 — Nếu không loại điểm NULL?

Trong PostgreSQL:

```sql
SELECT display_name, points
FROM ranking_scores
ORDER BY points DESC, member_id ASC
LIMIT 2;
```

**Đáp án:** Các hàng có `points IS NULL` đứng đầu khi sắp `DESC` mặc định; với khóa phụ `member_id ASC`, Phuc (11) rồi Quynh (12) sẽ được lấy. Để chọn người có điểm cao nhất, thêm `WHERE points IS NOT NULL` hoặc `ORDER BY points DESC NULLS LAST`, tùy yêu cầu xử lý thiếu dữ liệu.

### Bài 11 — Yêu cầu mâu thuẫn

Bộ dữ liệu có 100 người cùng điểm cao nhất. Sản phẩm yêu cầu “mỗi trang **đúng 20 người** và **không được tách bất kỳ nhóm đồng điểm nào giữa các trang**”. Có thể đáp ứng đồng thời trong mọi dữ liệu không?

**Đáp án:** Không. Một nhóm đồng hạng 100 người đã vượt kích thước trang 20. Phải làm rõ ưu tiên: trang cố định 20 hàng có thể tách tie, hoặc giữ nguyên tie và cho phép kích thước trang biến đổi (có thể vượt rất xa 20), hoặc thay đổi chính sách chia/hiển thị nhóm.

## 17. Quy trình chọn giải pháp cho một yêu cầu Top N

Khi nhận câu hỏi “lấy các hàng đầu”, hãy đi theo thứ tự:

1. **Định nghĩa đối tượng xếp hạng:** một hàng gốc, một khách hàng sau `GROUP BY`, một đơn hàng hay một nhóm?
2. **Định nghĩa tiêu chí xếp hạng:** điểm cao, thời điểm mới nhất, doanh thu nhiều nhất, số lượng lớn nhất… và chiều `ASC`/`DESC`.
3. **Quy định `NULL`:** không xếp hạng, xếp cuối, hay được biến đổi theo quy tắc nghiệp vụ?
4. **Xác định chính sách hòa:** đúng N hàng, N vị trí có ties, hay N mức giá trị?
5. **Xác định phạm vi:** toàn bộ bảng hay riêng từng team/nhóm?
6. **Chọn công cụ:** `LIMIT/FETCH ... ONLY` cho N hàng; `WITH TIES` hoặc `RANK` cho N vị trí có ties; `DENSE_RANK` cho N mức giá trị; `PARTITION BY` cho mỗi nhóm.
7. **Xác định thứ tự trình bày:** nếu cần kết quả đúng N hàng có thể tái lập, dùng khóa phụ duy nhất; nếu giữ ties theo điểm, chỉ dùng khóa phụ ở lớp sắp xếp ngoài.
8. **Nếu phân trang:** xác định trang cố định hay trang theo nhóm đồng điểm, dùng `OFFSET` hoặc keyset phù hợp và quy định nhất quán dữ liệu qua các trang.
9. **Đối chiếu bằng dữ liệu có đồng hạng ở ranh giới:** kiểm tra số hàng, tên/ID được chọn và trường hợp thiếu điểm trước khi tối ưu.
10. **Đo hiệu năng trên hệ quản trị thật:** quan sát `EXPLAIN`, thứ tự index và kích thước nhóm tie khi dữ liệu lớn.

Cốt lõi của bài học là **“top N” không phải một định nghĩa duy nhất**. `LIMIT` và `ROW_NUMBER` giải quyết bài toán lấy số hàng xác định; `WITH TIES` và `RANK` bảo vệ đồng hạng ở ranh giới số vị trí; `DENSE_RANK` chọn số mức hạng khác nhau. Khi tách rõ tiêu chí xếp hạng, tiêu chí đồng hạng và thứ tự hiển thị, truy vấn sẽ diễn đạt chính xác yêu cầu và người sử dụng sẽ hiểu vì sao kết quả đôi khi có nhiều hơn N hàng.

