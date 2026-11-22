# Tìm bản ghi mới nhất của từng đối tượng trong SQL

Một yêu cầu rất phổ biến trong hệ thống nghiệp vụ là: **“Với mỗi đối tượng, lấy đúng bản ghi mới nhất của nó.”** Chẳng hạn, lấy lần đăng nhập gần nhất của mỗi người dùng, lần cập nhật trạng thái mới nhất của mỗi đơn hàng, giao dịch gần đây nhất của mỗi tài khoản hoặc phiên bản mới nhất của mỗi tài liệu.

Điểm khó không nằm ở việc tìm `MAX(created_at)`, mà ở việc trả về **đúng toàn bộ bản ghi đi kèm mốc thời gian lớn nhất**. Ta còn phải trả lời những câu hỏi quan trọng: nếu hai bản ghi có cùng timestamp thì chọn bản nào; nếu timestamp là `NULL` thì xử lý ra sao; đối tượng chưa có bản ghi con có được hiển thị không; và điều kiện “mới nhất” được xác định **trước hay sau khi lọc trạng thái**?

Bài học trình bày những mẫu truy vấn thường dùng:

- `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)`: một hàng xác định cho mỗi đối tượng.
- `RANK()` hoặc `DENSE_RANK()`: giữ tất cả hàng đồng hạng mới nhất.
- `DISTINCT ON`: cú pháp gọn, riêng của PostgreSQL.
- `LEFT JOIN LATERAL ... LIMIT 1`: tìm hàng mới nhất theo từng đối tượng, kể cả đối tượng chưa có dữ liệu.
- `MAX(timestamp)` kết hợp `JOIN`: hữu ích nhưng phải hiểu vấn đề đồng hạng và `NULL`.
- Các biến thể trên SQL Server, MySQL/MariaDB, Oracle và SQLite.

Ví dụ chạy đầy đủ theo **PostgreSQL**, với dữ liệu cố ý chứa thời gian trùng nhau, thời gian thiếu, sự kiện đến muộn và đối tượng không có sự kiện.

## 1. Xác định chính xác “mới nhất”

Trước khi viết SQL, cần xác định **cột nào mang ý nghĩa thời gian**:

| Cột thời gian | Ý nghĩa thường gặp | Câu hỏi có thể trả lời |
|---|---|---|
| `occurred_at` | Khi sự kiện thực sự xảy ra | Sự kiện nào xảy ra sau cùng? |
| `created_at` | Khi bản ghi được tạo trong ứng dụng/DB | Bản ghi nào được tạo gần đây nhất? |
| `recorded_at` | Khi hệ thống ghi nhận sự kiện | Sự kiện nào vừa được ghi nhận gần nhất? |
| `updated_at` | Khi bản ghi được sửa gần nhất | Bản ghi nào được cập nhật gần nhất? |
| `effective_at` | Khi thay đổi bắt đầu có hiệu lực | Phiên bản nào có hiệu lực mới nhất? |
| `version_no` | Số phiên bản theo quy ước | Phiên bản nào được đánh số cao nhất? |

Các cột trên **không nhất thiết cùng thứ tự**. Một sự kiện xảy ra hôm qua có thể vừa được gửi đến hệ thống hôm nay. Nếu `ORDER BY recorded_at DESC`, bạn nhận **bản ghi mới được ghi nhận nhất**, không nhất thiết là **sự kiện xảy ra muộn nhất**.

Ngoài ra, phải xác định quy tắc khi có hai hàng cùng timestamp:

1. **Một hàng duy nhất:** bổ sung khóa phân định (*tie-breaker*) có thứ tự ổn định, ví dụ `event_id DESC`.
2. **Tất cả hàng mới nhất đồng hạng:** giữ tất cả hàng có cùng timestamp lớn nhất, ví dụ dùng `RANK() = 1`.
3. **Bản ghi mới nhất theo thứ tự nghiệp vụ thật:** cần cột đủ thông tin như số thứ tự sự kiện, phiên bản hoặc mốc nguồn tin cậy; không mặc định ID lớn hơn nghĩa là xảy ra sau.

Dùng `ORDER BY occurred_at DESC, event_id DESC` là một **quy ước chọn hàng khi đồng hạng**, không phải chứng cứ rằng ID lớn hơn luôn tương ứng với sự kiện thực sự xảy ra muộn hơn.

## 2. Dữ liệu thực hành: tài khoản và lịch sử sự kiện

Ta dùng hai bảng:

- `demo_accounts`: mỗi hàng là một đối tượng.
- `demo_account_events`: mỗi tài khoản có thể có nhiều sự kiện.

```sql
-- PostgreSQL
CREATE TEMP TABLE demo_accounts (
    account_id INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL
);

CREATE TEMP TABLE demo_account_events (
    event_id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL
        REFERENCES demo_accounts(account_id),
    occurred_at TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL,
    event_status TEXT NOT NULL
);

INSERT INTO demo_accounts (account_id, account_name)
VALUES
    (101, 'An'),
    (102, 'Bình'),
    (103, 'Chi'),
    (104, 'Dũng'),
    (105, 'Hà');

INSERT INTO demo_account_events
    (event_id, account_id, occurred_at, recorded_at, event_status)
VALUES
    (1001, 101,
        TIMESTAMPTZ '2026-11-10 09:00:00+00',
        TIMESTAMPTZ '2026-11-10 09:01:00+00', 'PENDING'),
    (1002, 101,
        TIMESTAMPTZ '2026-11-12 08:00:00+00',
        TIMESTAMPTZ '2026-11-12 08:01:00+00', 'PAID'),
    (1003, 101,
        TIMESTAMPTZ '2026-11-12 08:00:00+00',
        TIMESTAMPTZ '2026-11-12 08:02:00+00', 'CANCELLED'),
    (1004, 101,
        NULL,
        TIMESTAMPTZ '2026-11-13 00:00:00+00', 'DRAFT'),

    (2001, 102,
        TIMESTAMPTZ '2026-11-11 12:00:00+00',
        TIMESTAMPTZ '2026-11-11 12:01:00+00', 'PAID'),
    (2002, 102,
        TIMESTAMPTZ '2026-11-14 10:00:00+00',
        TIMESTAMPTZ '2026-11-14 10:01:00+00', 'PENDING'),
    (2003, 102,
        TIMESTAMPTZ '2026-11-13 18:00:00+00',
        TIMESTAMPTZ '2026-11-14 12:00:00+00', 'PAID'),

    (3001, 103,
        TIMESTAMPTZ '2026-11-09 07:00:00+00',
        TIMESTAMPTZ '2026-11-09 07:01:00+00', 'PAID'),
    (3002, 103,
        NULL,
        TIMESTAMPTZ '2026-11-15 07:00:00+00', 'PENDING'),

    (4001, 104,
        NULL,
        TIMESTAMPTZ '2026-11-12 00:00:00+00', 'PENDING'),
    (4002, 104,
        NULL,
        TIMESTAMPTZ '2026-11-13 00:00:00+00', 'PAID');
```

Tóm tắt dữ liệu:

| account_id | Sự kiện | Đặc điểm cần kiểm thử |
|---:|---|---|
| 101 | 1001, 1002, 1003, 1004 | 1002 và 1003 trùng `occurred_at`; 1004 có `NULL` |
| 102 | 2001, 2002, 2003 | 2003 được ghi nhận sau 2002, nhưng xảy ra trước 2002 |
| 103 | 3001, 3002 | 3002 không có `occurred_at` |
| 104 | 4001, 4002 | Cả hai sự kiện đều thiếu `occurred_at` |
| 105 | Không có | Tài khoản không có sự kiện con |

Ta định nghĩa yêu cầu chính:

> Mỗi tài khoản, chọn **một sự kiện mới nhất theo `occurred_at`**. Nếu hai sự kiện có cùng thời điểm, chọn `event_id` lớn hơn. Các thời điểm `NULL` xếp cuối. Nếu tài khoản không có sự kiện, vẫn giữ tài khoản và hiển thị cột sự kiện là `NULL`.

Với định nghĩa này, kết quả mong đợi là:

| account_id | account_name | event_id | event_status | Giải thích |
|---:|---|---:|---|---|
| 101 | An | 1003 | CANCELLED | Cùng thời gian với 1002, ID lớn hơn |
| 102 | Bình | 2002 | PENDING | `occurred_at` lớn nhất |
| 103 | Chi | 3001 | PAID | 3002 có `occurred_at NULL` |
| 104 | Dũng | 4002 | PAID | Mọi mốc đều `NULL`, dùng ID phân định |
| 105 | Hà | `NULL` | `NULL` | Không có sự kiện nào |

Ở tài khoản 104, chọn ID 4002 **không khẳng định đây là sự kiện xảy ra muộn hơn**; chỉ là kết quả của quy ước sắp thứ tự khi cả hai mốc đều không xác định. Nếu nghiệp vụ yêu cầu bắt buộc có thời điểm xảy ra, phải loại các sự kiện `occurred_at IS NULL` ngay trong tập được xếp hạng.

## 3. Vì sao MAX(timestamp) chưa giải quyết toàn bộ bài toán?

Một cách viết đơn giản:

```sql
SELECT
    account_id,
    MAX(occurred_at) AS latest_occurred_at
FROM demo_account_events
GROUP BY account_id
ORDER BY account_id;
```

Kết quả cho mỗi tài khoản có sự kiện là **mốc thời gian mới nhất**, nhưng không có `event_id` hay `event_status` của hàng tương ứng. `MAX` tính một giá trị tổng hợp; nó không tự “mang theo” các cột còn lại của bản ghi.

Trong PostgreSQL, câu sau không hợp lệ:

```sql
-- SAI: event_id không được GROUP BY hay tổng hợp.
SELECT account_id, MAX(occurred_at), event_id
FROM demo_account_events
GROUP BY account_id;
```

PostgreSQL sẽ từ chối vì `event_id` không được nhóm/tổng hợp đúng quy tắc. Một số cấu hình DBMS có thể chấp nhận cách viết thiếu ràng buộc và chọn cột ngoài nhóm không đáng tin cậy; không dùng hành vi đó để tìm “toàn bộ bản ghi mới nhất”.

### 3.1. MAX kèm JOIN có thể trả nhiều hàng đồng hạng

```sql
WITH latest_time AS (
    SELECT account_id,
           MAX(occurred_at) AS max_occurred_at
    FROM demo_account_events
    GROUP BY account_id
)
SELECT e.account_id, e.event_id, e.occurred_at
FROM demo_account_events AS e
JOIN latest_time AS m
  ON m.account_id = e.account_id
 AND e.occurred_at = m.max_occurred_at
ORDER BY e.account_id, e.event_id;
```

Kết quả:

| account_id | event_id | Vì sao khớp? |
|---:|---:|---|
| 101 | 1002 | Cùng thời điểm lớn nhất |
| 101 | 1003 | Cùng thời điểm lớn nhất |
| 102 | 2002 | Thời điểm lớn nhất |
| 103 | 3001 | Thời điểm lớn nhất |

Có **hai hàng cho tài khoản 101**, không phải một. Tài khoản 104 không xuất hiện vì `MAX(occurred_at)` trên toàn `NULL` trả SQL `NULL`, và `NULL = NULL` không cho `TRUE`. Tài khoản 105 không có bản ghi để nhóm.

Đây không hẳn là lỗi của `MAX`: nếu yêu cầu là **giữ tất cả bản ghi ở thời điểm tối đa**, việc trả 1002 và 1003 là hợp lý. Nhưng nếu yêu cầu là **chính xác một hàng cho mỗi đối tượng**, cần quy tắc tie-break và một kỹ thuật khác.

### 3.2. MAX(event_id) không tự chứng minh sự kiện mới nhất

Một mẹo thường gặp:

```sql
SELECT account_id, MAX(event_id) AS latest_event_id
FROM demo_account_events
GROUP BY account_id;
```

Trong dữ liệu này, ID 2003 lớn hơn 2002, nhưng `occurred_at` của 2003 **sớm hơn**. Vì vậy `MAX(event_id)` chọn 2003 cho tài khoản 102, không đúng định nghĩa “sự kiện xảy ra mới nhất”.

Chỉ có thể dùng `MAX(id)` thay timestamp khi hệ thống **bảo đảm bằng hợp đồng dữ liệu** rằng ID phản ánh chính xác thứ tự nghiệp vụ cần chọn. ID sinh tự tăng không mặc nhiên là commit time, event time hay một thứ tự toàn cục giữa các nguồn.

## 4. Mẫu chính: ROW_NUMBER() và PARTITION BY

`ROW_NUMBER()` là một **hàm cửa sổ** (*window function*) đánh số hàng trong từng nhóm do `PARTITION BY` tạo ra.

Cú pháp trọng tâm:

```sql
ROW_NUMBER() OVER (
    PARTITION BY group_key
    ORDER BY sort_expression DESC, tie_breaker DESC
)
```

- `PARTITION BY account_id`: mỗi tài khoản có một nhóm riêng.
- `ORDER BY occurred_at DESC NULLS LAST`: sự kiện có thời điểm gần nhất đứng đầu; `NULL` nằm cuối.
- `event_id DESC`: xác định thứ tự giữa các sự kiện có cùng thời điểm.
- `ROW_NUMBER() = 1`: chỉ chọn **một hàng đứng đầu mỗi nhóm**.

### 4.1. Truy vấn hoàn chỉnh PostgreSQL

```sql
WITH ranked_events AS (
    SELECT
        e.event_id,
        e.account_id,
        e.occurred_at,
        e.recorded_at,
        e.event_status,
        ROW_NUMBER() OVER (
            PARTITION BY e.account_id
            ORDER BY
                e.occurred_at DESC NULLS LAST,
                e.event_id DESC
        ) AS rn
    FROM demo_account_events AS e
)
SELECT
    a.account_id,
    a.account_name,
    r.event_id,
    r.occurred_at,
    r.event_status
FROM demo_accounts AS a
LEFT JOIN ranked_events AS r
  ON r.account_id = a.account_id
 AND r.rn = 1
ORDER BY a.account_id;
```

Kết quả đúng như bảng mục 2: **101→1003, 102→2002, 103→3001, 104→4002, 105→NULL**.

Đây là mẫu rất phổ biến vì nó tách bạch:

1. **Xếp hạng trong từng nhóm** bằng cửa sổ.
2. **Chọn hàng hạng nhất**.
3. **Ghép với bảng đối tượng** nếu muốn giữ cả đối tượng chưa có lịch sử.

### 4.2. Tại sao không dùng ROW_NUMBER trong WHERE cùng tầng SELECT?

Một cú pháp sai thường gặp:

```sql
-- SAI theo cấu trúc SQL thông thường:
SELECT event_id, account_id
FROM demo_account_events
WHERE ROW_NUMBER() OVER (
    PARTITION BY account_id
    ORDER BY occurred_at DESC
) = 1;
```

Hàm cửa sổ không được dùng trực tiếp ở `WHERE` cùng cấp trong các DBMS thông dụng vì nó được tính ở giai đoạn logic khác với lọc hàng trước cửa sổ.

Cách đúng và portable rộng rãi là đặt kết quả hàm cửa sổ vào **CTE** hoặc truy vấn con, rồi dùng `WHERE rn = 1` ở tầng ngoài:

```sql
SELECT event_id, account_id, occurred_at
FROM (
    SELECT
        event_id, account_id, occurred_at,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY occurred_at DESC NULLS LAST,
                     event_id DESC
        ) AS rn
    FROM demo_account_events
) AS ranked
WHERE rn = 1
ORDER BY account_id;
```

Truy vấn này chỉ có **bốn tài khoản có sự kiện** (101–104). Muốn thêm 105, dùng `LEFT JOIN` với `demo_accounts` như ví dụ đầu.

Một số phương ngữ có `QUALIFY` để lọc theo kết quả window function trực tiếp ở một tầng truy vấn; **không được suy ra PostgreSQL, MySQL hay SQL Server đều hỗ trợ `QUALIFY`**. CTE/truy vấn con thường là cách ít phụ thuộc dialect hơn.

### 4.3. Có cần ORDER BY event_id không?

Có, nếu mục tiêu là **chọn một hàng xác định**. Nếu chỉ viết:

```sql
ROW_NUMBER() OVER (
    PARTITION BY account_id
    ORDER BY occurred_at DESC NULLS LAST
)
```

thì 1002 và 1003 của tài khoản 101 có cùng `occurred_at`. DBMS không có quy tắc thứ tự giữa hai hàng đồng hạng này; hàng nào nhận `rn = 1` có thể thay đổi theo kế hoạch thực thi.

Thêm `event_id DESC` (với `event_id` là khóa duy nhất) giúp tạo thứ tự toàn phần trong nhóm. Tuy nhiên, **quy tắc ID lớn hơn thắng khi cùng thời gian phải được chấp nhận về nghiệp vụ**, không phải một kết luận từ khái niệm “mới nhất”.

## 5. Giữ toàn bộ bản ghi mới nhất đồng hạng

Đôi khi yêu cầu không phải “mỗi khách đúng một dòng”, mà là **“mọi sự kiện có mốc thời gian mới nhất”**. Khi có hai bản ghi cùng `occurred_at`, cả hai đều hợp lệ.

Lúc đó dùng `RANK()` hoặc `DENSE_RANK()`, với **chỉ mốc thời gian trong `ORDER BY`**:

```sql
WITH ranked AS (
    SELECT
        e.event_id,
        e.account_id,
        e.occurred_at,
        RANK() OVER (
            PARTITION BY e.account_id
            ORDER BY e.occurred_at DESC NULLS LAST
        ) AS time_rank
    FROM demo_account_events AS e
)
SELECT account_id, event_id, occurred_at
FROM ranked
WHERE time_rank = 1
ORDER BY account_id, event_id;
```

Kết quả:

| account_id | event_id |
|---:|---|
| 101 | 1002 |
| 101 | 1003 |
| 102 | 2002 |
| 103 | 3001 |
| 104 | 4001 |
| 104 | 4002 |

Với tài khoản 104, **hai thời điểm đều `NULL`** và cùng hạng cuối/đầu tùy sắp; vì toàn bộ nhóm đều `NULL`, cả hai ở hạng 1. Nếu `NULL` mang nghĩa “không có thời điểm đủ tin cậy”, có thể loại nhóm này bằng `WHERE occurred_at IS NOT NULL` trước khi xếp hạng.

### 5.1. ROW_NUMBER, RANK và DENSE_RANK khác gì?

Giả sử một nhóm có thời điểm giảm dần: `T3, T3, T2, T1`.

| Thời điểm | `ROW_NUMBER()` | `RANK()` | `DENSE_RANK()` |
|---|---:|---:|---:|
| T3 | 1 | 1 | 1 |
| T3 | 2 | 1 | 1 |
| T2 | 3 | 3 | 2 |
| T1 | 4 | 4 | 3 |

- `ROW_NUMBER()`: mỗi hàng có số khác nhau, nhưng giữa hàng đồng hạng cần khóa phụ để xác định hàng nào trước.
- `RANK()`: cùng thứ hạng cho hàng đồng hạng và **để trống** hạng tiếp theo.
- `DENSE_RANK()`: cùng thứ hạng nhưng **không có khoảng trống**.

Để tìm tất cả bản ghi mới nhất, `RANK() = 1` và `DENSE_RANK() = 1` cho cùng kết quả khi có cùng biểu thức sắp xếp. Nếu thêm `event_id DESC` vào biểu thức sắp của `RANK()`, hai hàng trùng timestamp sẽ không còn đồng hạng; **điều đó biến “giữ tất cả cùng thời điểm” thành “chọn một theo ID”**.

### 5.2. FETCH FIRST ... WITH TIES

Một số DBMS hỗ trợ `FETCH FIRST 1 ROW WITH TIES` hoặc cú pháp tương ứng. Trong PostgreSQL 13+ có thể áp dụng bên trong một truy vấn cho từng tài khoản khi dùng `LATERAL`:

```sql
SELECT a.account_id, e.event_id, e.occurred_at
FROM demo_accounts AS a
LEFT JOIN LATERAL (
    SELECT event_id, occurred_at
    FROM demo_account_events AS e
    WHERE e.account_id = a.account_id
    ORDER BY occurred_at DESC NULLS LAST
    FETCH FIRST 1 ROW WITH TIES
) AS e ON TRUE
ORDER BY a.account_id, e.event_id;
```

Khi 101 có hai sự kiện cùng thời điểm mới nhất, cả hai được lấy. Với 104 có hai `NULL`, cả hai cũng khớp hạng. Nếu chỉ muốn một hàng, dùng `FETCH FIRST 1 ROW ONLY` cùng khóa phân định hoặc `LIMIT 1`.

## 6. PostgreSQL DISTINCT ON: mẫu gọn cho một hàng mỗi đối tượng

PostgreSQL có cú pháp riêng `DISTINCT ON (columns)`. Nó giữ **hàng đầu tiên của mỗi nhóm giá trị trên các cột chỉ định**, theo `ORDER BY` của truy vấn.

```sql
SELECT DISTINCT ON (e.account_id)
    e.account_id,
    e.event_id,
    e.occurred_at,
    e.event_status
FROM demo_account_events AS e
ORDER BY
    e.account_id,
    e.occurred_at DESC NULLS LAST,
    e.event_id DESC;
```

Kết quả cho các tài khoản có sự kiện là **101→1003, 102→2002, 103→3001, 104→4002**.

Cách đọc:

1. `DISTINCT ON (e.account_id)`: chỉ giữ **một hàng cho mỗi account_id**.
2. `ORDER BY e.account_id`: sắp nhóm theo khóa phân biệt.
3. Sau đó `occurred_at DESC NULLS LAST`: trong nhóm, thời điểm lớn hơn đi trước.
4. `event_id DESC`: phân định nếu thời điểm bằng nhau.

Trong PostgreSQL, biểu thức ở `DISTINCT ON` cần phù hợp với **các biểu thức đầu của `ORDER BY`** theo quy tắc cú pháp. Không thể tùy ý `ORDER BY occurred_at DESC` trước `account_id` khi đang `DISTINCT ON(account_id)` mà không xử lý lại cấu trúc truy vấn.

### 6.1. Muốn sắp toàn bộ kết quả theo thời gian mới nhất?

Với `DISTINCT ON`, phần `ORDER BY` đầu phải phục vụ chọn hàng theo account. Muốn cuối cùng xếp **các tài khoản theo thời điểm gần nhất toàn cục**, bọc thêm tầng ngoài:

```sql
WITH latest_events AS (
    SELECT DISTINCT ON (account_id)
        account_id, event_id, occurred_at, event_status
    FROM demo_account_events
    ORDER BY account_id,
             occurred_at DESC NULLS LAST,
             event_id DESC
)
SELECT account_id, event_id, occurred_at, event_status
FROM latest_events
ORDER BY occurred_at DESC NULLS LAST,
         event_id DESC;
```

Kết quả là một hàng mỗi tài khoản có sự kiện, sau đó được sắp **giữa các tài khoản** theo mốc mới nhất. Nếu cần mọi tài khoản, `LEFT JOIN` kết quả này với `demo_accounts`.

### 6.2. DISTINCT ON không phải cú pháp portable

`DISTINCT ON` là tính năng đặc thù của PostgreSQL; không nên sao chép vào MySQL, SQL Server, Oracle hoặc SQLite. Khi muốn một mẫu rộng rãi giữa nhiều DBMS có hỗ trợ window functions, dùng `ROW_NUMBER()`.

## 7. LATERAL: tìm một bản ghi mới nhất theo từng hàng cha

`LEFT JOIN LATERAL` trong PostgreSQL cho phép truy vấn con ở phía phải tham chiếu giá trị của **từng hàng bảng cha**. Đây là mẫu tự nhiên khi đã có một danh sách tài khoản và muốn tìm sự kiện mới nhất cho mỗi tài khoản.

```sql
SELECT
    a.account_id,
    a.account_name,
    latest.event_id,
    latest.occurred_at,
    latest.event_status
FROM demo_accounts AS a
LEFT JOIN LATERAL (
    SELECT
        e.event_id,
        e.occurred_at,
        e.event_status
    FROM demo_account_events AS e
    WHERE e.account_id = a.account_id
    ORDER BY
        e.occurred_at DESC NULLS LAST,
        e.event_id DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY a.account_id;
```

Kết quả: **101→1003, 102→2002, 103→3001, 104→4002, 105→NULL**.

Giải thích:

- `e.account_id = a.account_id` kết nối truy vấn con với tài khoản hiện tại.
- `ORDER BY ... LIMIT 1` chỉ chọn **một hàng đứng đầu** theo quy tắc đã nêu.
- `LEFT JOIN LATERAL ... ON TRUE` vẫn giữ tài khoản 105, với các cột `latest` là `NULL`.
- Nếu thay `LEFT JOIN LATERAL` bằng `JOIN LATERAL` (inner), tài khoản không có sự kiện sẽ bị loại.

### 7.1. Khi nào LATERAL thuận tiện?

Nó đặc biệt có ích khi:

- Truy vấn chính đã **lọc một số ít đối tượng**.
- Mỗi đối tượng có nhiều hàng lịch sử, nhưng chỉ cần một hàng đầu.
- Có chỉ mục theo `(account_id, occurred_at DESC, event_id DESC)` phục vụ tìm đầu danh sách.
- Muốn lấy **nhiều cột từ cùng một bản ghi mới nhất** mà không lặp nhiều scalar subquery.

Nhưng nếu phải xử lý **toàn bộ tài khoản** với số lượng rất lớn, `ROW_NUMBER()` hay một kế hoạch khác có thể hiệu quả hơn. Hiệu năng phụ thuộc số cha, phân bố sự kiện, chỉ mục và optimizer; không có quy tắc LATERAL luôn nhanh hơn window function.

### 7.2. LATERAL không chỉ là LIMIT

Không có `ORDER BY`:

```sql
-- KHÔNG diễn tả "mới nhất" theo nghĩa xác định.
LEFT JOIN LATERAL (
    SELECT *
    FROM demo_account_events e
    WHERE e.account_id = a.account_id
    LIMIT 1
) latest ON TRUE
```

`LIMIT 1` chỉ đảm bảo **tối đa một hàng**, không chọn bản ghi mới nhất. Hệ quản trị có thể lấy hàng khác khi kế hoạch thay đổi. Luôn chỉ rõ cột thời gian và khóa phân định.

### 7.3. Correlated scalar subquery khi chỉ cần một cột

Nếu chỉ cần mã sự kiện:

```sql
SELECT
    a.account_id,
    (
        SELECT e.event_id
        FROM demo_account_events AS e
        WHERE e.account_id = a.account_id
        ORDER BY e.occurred_at DESC NULLS LAST,
                 e.event_id DESC
        LIMIT 1
    ) AS latest_event_id
FROM demo_accounts AS a
ORDER BY a.account_id;
```

Đây là **truy vấn con vô hướng có tương quan**, vì truy vấn trong dùng `a.account_id`. Nếu không có sự kiện, kết quả scalar là `NULL`. Khi cần thêm trạng thái, thời gian, người tạo... từ **cùng một hàng**, `LATERAL` thường dễ đọc hơn việc sao chép scalar subquery nhiều lần.

## 8. Đối tượng chưa có bản ghi con: LEFT JOIN là quyết định nghiệp vụ

Có hai câu hỏi khác nhau:

- “Liệt kê **mọi tài khoản**, kèm sự kiện mới nhất nếu có.”
- “Liệt kê **những tài khoản đã có sự kiện**, kèm sự kiện mới nhất.”

Với câu đầu, nên bắt đầu từ bảng cha `demo_accounts` và dùng `LEFT JOIN`. Với câu sau, có thể truy vấn trực tiếp từ bảng sự kiện đã xếp hạng, chỉ lấy `rn = 1`.

### 8.1. Sai lầm: lọc ở WHERE làm mất hàng cha

Xét truy vấn:

```sql
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.account_id
            ORDER BY e.occurred_at DESC NULLS LAST, e.event_id DESC
        ) AS rn
    FROM demo_account_events AS e
)
SELECT a.account_id, r.event_id
FROM demo_accounts AS a
LEFT JOIN ranked AS r
  ON r.account_id = a.account_id
WHERE r.rn = 1;
```

Dù đã dùng `LEFT JOIN`, `WHERE r.rn = 1` loại hàng của tài khoản 105 vì `r.rn` là `NULL` trên hàng không khớp, nên điều kiện không `TRUE`.

Sửa bằng cách đưa `r.rn = 1` vào `ON`:

```sql
LEFT JOIN ranked AS r
  ON r.account_id = a.account_id
 AND r.rn = 1
```

Hoặc lọc `rn = 1` trong CTE thứ hai trước khi `LEFT JOIN`:

```sql
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY occurred_at DESC NULLS LAST, event_id DESC
        ) AS rn
    FROM demo_account_events e
),
latest AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)
SELECT a.account_id, l.event_id
FROM demo_accounts a
LEFT JOIN latest l ON l.account_id = a.account_id
ORDER BY a.account_id;
```

Cả hai đều giữ tài khoản 105.

### 8.2. Không có timestamp khác không có sự kiện

Trong dữ liệu mẫu:

- Tài khoản **104** có hai sự kiện, nhưng `occurred_at` đều `NULL`.
- Tài khoản **105** không có sự kiện nào.

Nếu màn hình muốn phân biệt hai trạng thái này, không nên chỉ xem `latest.occurred_at IS NULL`. Cần kiểm tra **khóa của hàng con**, ví dụ `latest.event_id IS NULL`, hoặc trả thêm số sự kiện:

```sql
SELECT
    a.account_id,
    COUNT(e.event_id) AS event_count,
    MAX(e.occurred_at) AS latest_known_time
FROM demo_accounts AS a
LEFT JOIN demo_account_events AS e
  ON e.account_id = a.account_id
GROUP BY a.account_id
ORDER BY a.account_id;
```

Kết quả `event_count` cho 104 là 2 và cho 105 là 0; nhưng `latest_known_time` của cả hai là `NULL`. Một API có thể xuất riêng `has_events`/`event_count` để không đánh đồng các tình huống này.

## 9. Xử lý NULL trong cột thời gian

Một số DBMS đặt `NULL` **đầu** khi `ORDER BY timestamp DESC`, trong khi một số khác đặt **cuối**. Cụ thể, PostgreSQL mặc định `DESC` đưa `NULL` lên đầu; MySQL/SQL Server/SQLite thường đưa `NULL` xuống cuối khi `DESC`. Vì thế không nên viết thiếu chính sách `NULL` khi truy vấn cần kết quả ổn định giữa các phương ngữ.

### 9.1. PostgreSQL: DESC NULLS LAST

```sql
ORDER BY occurred_at DESC NULLS LAST, event_id DESC
```

Dạng này có nghĩa:

1. Thời điểm đã biết và lớn hơn đứng trước.
2. Các hàng có `occurred_at NULL` đứng sau những thời điểm đã biết.
3. Hàng có cùng thời điểm được phân định bằng `event_id DESC`.

### 9.2. Cách portable bằng CASE

Khi DBMS không hỗ trợ cú pháp `NULLS LAST` trực tiếp, dùng khóa sắp xếp phụ:

```sql
ORDER BY
    CASE WHEN occurred_at IS NULL THEN 1 ELSE 0 END ASC,
    occurred_at DESC,
    event_id DESC
```

Nhóm có thời điểm đã biết có khóa 0, nhóm `NULL` có khóa 1, nên `NULL` chắc chắn nằm cuối. Cách này có thể sử dụng trong `ORDER BY` của window function:

```sql
ROW_NUMBER() OVER (
    PARTITION BY account_id
    ORDER BY
        CASE WHEN occurred_at IS NULL THEN 1 ELSE 0 END,
        occurred_at DESC,
        event_id DESC
)
```

Trong SQL Server, MySQL/MariaDB và SQLite, cách viết bằng `CASE` giúp ý định rõ ràng. Hãy kiểm tra phiên bản khi muốn dùng cú pháp `NULLS FIRST/LAST` nguyên bản; SQLite hỗ trợ từ 3.30.0, còn SQL Server/MySQL thông dụng thường dùng biểu thức thay thế.

### 9.3. Chỉ chấp nhận bản ghi có timestamp hợp lệ

Nếu yêu cầu là “lấy sự kiện gần nhất **có thời điểm xảy ra xác định**”, phải lọc **trước khi xếp hạng**:

```sql
WITH ranked_valid AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.account_id
            ORDER BY e.occurred_at DESC, e.event_id DESC
        ) AS rn
    FROM demo_account_events AS e
    WHERE e.occurred_at IS NOT NULL
)
SELECT a.account_id, r.event_id, r.occurred_at
FROM demo_accounts AS a
LEFT JOIN ranked_valid AS r
  ON r.account_id = a.account_id
 AND r.rn = 1
ORDER BY a.account_id;
```

Kết quả:

| account_id | event_id |
|---:|---:|
| 101 | 1003 |
| 102 | 2002 |
| 103 | 3001 |
| 104 | `NULL` |
| 105 | `NULL` |

**Tài khoản 104 vẫn có sự kiện**, nhưng không có sự kiện nào đủ điều kiện về timestamp. Nếu cần phân biệt 104 với 105, trả thêm `event_count` hoặc cờ có dữ liệu. Đừng biến cả hai thành “không có sự kiện” chỉ vì kết quả latest valid là `NULL`.

## 10. Lọc trạng thái trước hay sau khi tìm bản ghi mới nhất?

Đây là một trong những khác biệt quan trọng nhất về **ý nghĩa nghiệp vụ**.

Có hai yêu cầu nghe gần giống:

**A. “Mỗi tài khoản, tìm sự kiện mới nhất trong số những sự kiện có trạng thái `PAID`.”**

**B. “Mỗi tài khoản, tìm sự kiện mới nhất bất kể trạng thái; sau đó chỉ hiển thị nếu bản ghi mới nhất đang là `PAID`.”**

Hai câu không tương đương.

### 10.1. Lấy sự kiện PAID mới nhất (lọc trước)

```sql
WITH ranked_paid AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY occurred_at DESC NULLS LAST, event_id DESC
        ) AS rn
    FROM demo_account_events AS e
    WHERE event_status = 'PAID'
)
SELECT a.account_id, r.event_id AS latest_paid_event
FROM demo_accounts AS a
LEFT JOIN ranked_paid AS r
  ON r.account_id = a.account_id
 AND r.rn = 1
ORDER BY a.account_id;
```

Kết quả:

| account_id | latest_paid_event |
|---:|---:|
| 101 | 1002 |
| 102 | 2003 |
| 103 | 3001 |
| 104 | 4002 |
| 105 | `NULL` |

Ở tài khoản 101, sự kiện 1003 mới nhất theo quy tắc chung là `CANCELLED`, nhưng khi **chỉ xét PAID**, sự kiện mới nhất là 1002. Ở tài khoản 102, sự kiện `PAID` mới nhất là 2003, dù sự kiện tổng thể mới nhất theo `occurred_at` là 2002 với trạng thái `PENDING`.

### 10.2. Chỉ chọn tài khoản mà sự kiện mới nhất là PAID (lọc sau)

```sql
WITH ranked_all AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY occurred_at DESC NULLS LAST, event_id DESC
        ) AS rn
    FROM demo_account_events AS e
)
SELECT account_id, event_id, event_status
FROM ranked_all
WHERE rn = 1
  AND event_status = 'PAID'
ORDER BY account_id;
```

Kết quả: **103→3001** và **104→4002**.

- 101 bị loại vì sự kiện mới nhất là 1003 `CANCELLED`.
- 102 bị loại vì sự kiện mới nhất là 2002 `PENDING`.
- 103 có sự kiện mới nhất là `PAID`.
- 104 theo quy tắc tie-break ID lớn hơn có 4002 `PAID`.
- 105 không có sự kiện.

Nếu yêu cầu vẫn phải **hiển thị mọi tài khoản** với trạng thái “mới nhất có phải PAID không”, hãy giữ bảng cha và xuất một cột đánh giá:

```sql
WITH ranked_all AS (
    SELECT e.*,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY occurred_at DESC NULLS LAST, event_id DESC
           ) AS rn
    FROM demo_account_events e
)
SELECT
    a.account_id,
    r.event_id AS latest_event_id,
    r.event_status AS latest_status,
    CASE
        WHEN r.event_id IS NULL THEN 'NO_EVENT'
        WHEN r.event_status = 'PAID' THEN 'LATEST_IS_PAID'
        ELSE 'LATEST_NOT_PAID'
    END AS latest_paid_flag
FROM demo_accounts a
LEFT JOIN ranked_all r
  ON r.account_id = a.account_id
 AND r.rn = 1
ORDER BY a.account_id;
```

**Nguyên tắc:** Đặt điều kiện trong tập đầu vào của window function nếu muốn “**mới nhất trong số các bản ghi thỏa điều kiện**”. Đặt điều kiện sau khi đã chọn `rn = 1` nếu muốn “**bản ghi mới nhất có thỏa điều kiện không**”.

## 11. Sự kiện xảy ra mới nhất khác sự kiện được ghi nhận mới nhất

Trong dữ liệu mẫu, tài khoản 102 có:

| event_id | occurred_at (UTC) | recorded_at (UTC) |
|---:|---|---|
| 2001 | 2026-11-11 12:00 | 2026-11-11 12:01 |
| 2002 | 2026-11-14 10:00 | 2026-11-14 10:01 |
| 2003 | 2026-11-13 18:00 | 2026-11-14 12:00 |

Theo `occurred_at`, bản ghi mới nhất là **2002**. Theo `recorded_at`, bản ghi mới nhất là **2003**.

Chạy để thấy kết quả:

```sql
SELECT
    (SELECT event_id
     FROM demo_account_events
     WHERE account_id = 102
     ORDER BY occurred_at DESC NULLS LAST, event_id DESC
     LIMIT 1) AS latest_by_occurrence,

    (SELECT event_id
     FROM demo_account_events
     WHERE account_id = 102
     ORDER BY recorded_at DESC, event_id DESC
     LIMIT 1) AS latest_by_recording;
-- latest_by_occurrence = 2002
-- latest_by_recording  = 2003
```

Với hệ thống xử lý thông điệp từ hàng đợi, sự kiện có thể **đến muộn**, bị gửi lại hoặc chứa timestamp của nguồn khác. Cần quy định rõ loại “mới nhất” phục vụ UI, kiểm toán, trạng thái hiện tại hay đồng bộ.

Đặc biệt, việc chọn **trạng thái hiện tại** của một đối tượng từ nhật ký sự kiện còn có thể cần **thứ tự phiên bản bảo đảm bởi nguồn** hoặc quy tắc áp dụng sự kiện. Chỉ dùng timestamp từ các máy khác nhau có nguy cơ đồng hồ lệch, cùng timestamp hoặc dữ liệu đến không theo thứ tự.

## 12. Mẫu chống JOIN sai: so sánh max timestamp và hàng trùng

Một truy vấn thường thấy:

```sql
SELECT a.account_id, e.event_id
FROM demo_accounts a
JOIN demo_account_events e
  ON e.account_id = a.account_id
WHERE e.occurred_at = (
    SELECT MAX(x.occurred_at)
    FROM demo_account_events x
    WHERE x.account_id = a.account_id
);
```

Truy vấn trả những hàng **đạt mốc lớn nhất**. Nó không đảm bảo chỉ một hàng cho mỗi tài khoản nếu có đồng hạng, và loại những tài khoản mà tất cả mốc là `NULL`.

Tránh “chữa” bằng `DISTINCT` trên toàn bộ các cột:

```sql
-- DISTINCT không biến hai event_id khác nhau thành một hàng.
SELECT DISTINCT a.account_id, e.event_id
...
```

Hai sự kiện 1002, 1003 có ID khác nhau nên vẫn là hai hàng. Nếu chỉ `SELECT DISTINCT a.account_id` thì mất chi tiết bản ghi mới nhất mà bài toán đang cần.

### 12.1. Dùng NOT EXISTS để diễn đạt “không có bản ghi đứng sau”

Một mẫu khác là **anti-semi join**: giữ sự kiện `e` nếu **không tồn tại sự kiện nào đứng sau `e` trong cùng tài khoản**.

Với định nghĩa timestamp `NULL` cuối và ID lớn hơn thắng khi đồng hạng, PostgreSQL:

```sql
SELECT
    e.account_id,
    e.event_id,
    e.occurred_at
FROM demo_account_events AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_account_events AS newer
    WHERE newer.account_id = e.account_id
      AND (
          (e.occurred_at IS NULL
           AND newer.occurred_at IS NOT NULL)
          OR
          (e.occurred_at IS NOT NULL
           AND newer.occurred_at > e.occurred_at)
          OR
          (
              newer.occurred_at IS NOT DISTINCT FROM e.occurred_at
              AND newer.event_id > e.event_id
          )
      )
)
ORDER BY e.account_id;
```

Theo dữ liệu mẫu, kết quả cũng là **101→1003, 102→2002, 103→3001, 104→4002**.

Vì sao điều kiện dài?

- Nếu `e` có timestamp `NULL`, mọi bản ghi có timestamp đã biết đứng trước nó.
- Nếu `e` có timestamp đã biết, bản ghi với timestamp lớn hơn sẽ thắng.
- Nếu hai timestamp bằng nhau, **kể cả cùng `NULL`**, ID lớn hơn thắng. PostgreSQL dùng `IS NOT DISTINCT FROM` để coi hai `NULL` là bằng nhau trong phép so sánh an toàn với `NULL`.

Đây là mẫu mang tính **giải thích quan hệ “không có bản ghi đứng sau”**. Nó có thể có ích khi cần một điều kiện phức tạp hoặc trên DBMS không hỗ trợ window function. Nhưng nó dễ sai ở `NULL`, nhiều nhánh và điều kiện đồng hạng, nên thường ưu tiên `ROW_NUMBER()`/`LATERAL` khi có sẵn.

### 12.2. Phạm vi khóa phải nhất quán

Trong hệ đa tenant, quan hệ “cùng một đối tượng” có thể là **cặp `(tenant_id, account_id)`**, không phải chỉ `account_id`. Mọi phần `PARTITION BY`, `JOIN` hoặc `NOT EXISTS` phải mang đầy đủ phạm vi khóa để tránh lấy sự kiện của tenant khác.

## 13. Lấy hàng mới nhất theo nhiều khóa

Không phải lúc nào nhóm cũng chỉ gồm một cột. Ví dụ “với mỗi **khách hàng và loại sự kiện**, lấy sự kiện gần nhất”.

```sql
SELECT account_id, event_status, event_id, occurred_at
FROM (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY account_id, event_status
            ORDER BY occurred_at DESC NULLS LAST, event_id DESC
        ) AS rn
    FROM demo_account_events e
) ranked
WHERE rn = 1
ORDER BY account_id, event_status;
```

Vì `PARTITION BY account_id, event_status`, mỗi tổ hợp **(tài khoản, trạng thái)** có tối đa một hàng kết quả. Đây không còn là “một sự kiện mới nhất của mỗi tài khoản” mà là “một sự kiện mới nhất của **mỗi loại trạng thái trong mỗi tài khoản**”.

Tương tự, một ứng dụng nhiều tổ chức có thể cần:

```sql
ROW_NUMBER() OVER (
    PARTITION BY tenant_id, account_id
    ORDER BY occurred_at DESC NULLS LAST, event_id DESC
)
```

**Thiếu `tenant_id`** trong `PARTITION BY` hoặc `JOIN` có thể khiến các tài khoản trùng ID ở hai tenant bị trộn lịch sử, gây sai dữ liệu hoặc rủi ro truy cập. Đảm bảo các tham số tenant thực sự gắn với người dùng được phép, không chỉ được truyền tùy ý từ client.

## 14. SQL Server: ROW_NUMBER và OUTER APPLY

SQL Server hỗ trợ hàm cửa sổ `ROW_NUMBER()`. Dạng CTE phổ biến:

```sql
-- SQL Server / T-SQL, giả sử dbo.account_events tồn tại.
WITH ranked AS (
    SELECT
        e.event_id,
        e.account_id,
        e.occurred_at,
        e.event_status,
        ROW_NUMBER() OVER (
            PARTITION BY e.account_id
            ORDER BY
                CASE WHEN e.occurred_at IS NULL THEN 1 ELSE 0 END,
                e.occurred_at DESC,
                e.event_id DESC
        ) AS rn
    FROM dbo.account_events AS e
)
SELECT account_id, event_id, occurred_at, event_status
FROM ranked
WHERE rn = 1;
```

Dùng `CASE` giúp nói rõ `NULL` ở cuối, dù SQL Server thông thường đã đặt `NULL` cuối với `DESC`.

### 14.1. OUTER APPLY tương tự LEFT JOIN LATERAL

Trong T-SQL, `OUTER APPLY` thường diễn đạt “với mỗi tài khoản, chọn một hàng con gần nhất”:

```sql
SELECT
    a.account_id,
    a.account_name,
    e.event_id,
    e.occurred_at,
    e.event_status
FROM dbo.accounts AS a
OUTER APPLY (
    SELECT TOP (1)
        x.event_id,
        x.occurred_at,
        x.event_status
    FROM dbo.account_events AS x
    WHERE x.account_id = a.account_id
    ORDER BY
        CASE WHEN x.occurred_at IS NULL THEN 1 ELSE 0 END,
        x.occurred_at DESC,
        x.event_id DESC
) AS e
ORDER BY a.account_id;
```

- `TOP (1)` là cú pháp giới hạn một hàng của SQL Server.
- `OUTER APPLY` giữ tài khoản không có sự kiện.
- `CROSS APPLY` sẽ loại tài khoản không có hàng con phù hợp.
- Khi muốn giữ **mọi hàng đồng hạng**, SQL Server có `TOP (1) WITH TIES`, nhưng nếu `ORDER BY` có khóa phụ duy nhất thì sẽ không còn đồng hạng. Cần xác định chính xác tiêu chí buộc các hàng được xem là đồng hạng.

Không sao chép `LIMIT 1` của PostgreSQL vào T-SQL hoặc dùng `DISTINCT ON` trong SQL Server; đó là khác biệt phương ngữ.

## 15. MySQL và MariaDB: window function từ các phiên bản hỗ trợ

MySQL **8.0+** và MariaDB từ những phiên bản có hỗ trợ window functions có thể dùng `ROW_NUMBER()`:

```sql
-- MySQL 8.0+ / MariaDB phiên bản có window functions.
WITH ranked AS (
    SELECT
        e.event_id,
        e.account_id,
        e.occurred_at,
        e.event_status,
        ROW_NUMBER() OVER (
            PARTITION BY e.account_id
            ORDER BY
                CASE WHEN e.occurred_at IS NULL THEN 1 ELSE 0 END,
                e.occurred_at DESC,
                e.event_id DESC
        ) AS rn
    FROM account_events AS e
)
SELECT account_id, event_id, occurred_at, event_status
FROM ranked
WHERE rn = 1
ORDER BY account_id;
```

MySQL/MariaDB còn cho phép các truy vấn con tương quan với `ORDER BY ... LIMIT 1` khi chỉ cần một giá trị. Khi cần nhiều cột của hàng thắng cuộc, có thể dùng window function và `JOIN`, hoặc tính năng/phương pháp tương ứng với phiên bản.

**Chú ý MySQL cũ hơn 8.0:** không thể giả định có `ROW_NUMBER()`; có thể phải dùng `NOT EXISTS`, truy vấn tương quan hoặc phương án khác, với xử lý `NULL`/đồng hạng cẩn thận.

### 15.1. Cẩn trọng với timestamp và múi giờ

MySQL có kiểu `TIMESTAMP` và `DATETIME` với ngữ nghĩa chuyển đổi múi giờ khác nhau. PostgreSQL `TIMESTAMPTZ` không được sao chép nguyên thành kiểu tên giống hệt trong MySQL. Khi trộn dữ liệu nhiều múi giờ, hãy xác định cột lưu **thời điểm tuyệt đối** hay **giờ địa phương**, rồi sắp xếp trên dữ liệu được chuẩn hóa đúng nghĩa.

## 16. Oracle Database: analytic ROW_NUMBER và FETCH FIRST

Oracle dùng analytic function `ROW_NUMBER() OVER (...)`. Ví dụ:

```sql
-- Oracle: giả sử ACCOUNT_EVENTS có cột tương ứng.
SELECT account_id, event_id, occurred_at, event_status
FROM (
    SELECT
        e.account_id,
        e.event_id,
        e.occurred_at,
        e.event_status,
        ROW_NUMBER() OVER (
            PARTITION BY e.account_id
            ORDER BY e.occurred_at DESC NULLS LAST,
                     e.event_id DESC
        ) AS rn
    FROM account_events e
)
WHERE rn = 1;
```

Oracle hỗ trợ `NULLS FIRST/LAST` và có mặc định vị trí `NULL` cần được kiểm soát rõ khi đổi chiều sort. Với Oracle phiên bản hỗ trợ `FETCH FIRST`, có thể chọn một hàng theo `ORDER BY ... FETCH FIRST 1 ROW ONLY` trong truy vấn tương quan hoặc `APPLY` phù hợp.

Không mặc định Oracle hỗ trợ `LIMIT 1` hoặc `DISTINCT ON` như PostgreSQL. Khi làm việc với Oracle `DATE`, nhớ rằng kiểu `DATE` của Oracle chứa cả phần giờ, trong khi kiểu `DATE` của PostgreSQL chỉ có ngày.

## 17. SQLite: ROW_NUMBER và xử lý NULL

SQLite từ **3.25.0** hỗ trợ window functions, trong đó có `ROW_NUMBER()`. Mẫu dùng truy vấn con:

```sql
-- SQLite 3.25.0 trở lên, giả sử account_events tồn tại.
SELECT account_id, event_id, occurred_at
FROM (
    SELECT
        account_id,
        event_id,
        occurred_at,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY
                CASE WHEN occurred_at IS NULL THEN 1 ELSE 0 END,
                occurred_at DESC,
                event_id DESC
        ) AS rn
    FROM account_events
) ranked
WHERE rn = 1;
```

SQLite có cách lưu thời gian thường dùng chuỗi ISO-8601, Unix epoch hoặc số Julian day, không có đúng kiểu `TIMESTAMPTZ` như PostgreSQL. Nếu các bản ghi dùng **định dạng chuỗi không thống nhất** hoặc offset khác nhau, sắp xếp theo văn bản có thể không phản ánh thứ tự thời điểm tuyệt đối. Cần chuẩn hóa biểu diễn trước khi áp dụng mẫu “latest per group”.

Ngoài ra, SQLite scalar subquery có thể tự lấy một hàng đầu nếu nhiều hàng, nhưng **không nên dựa vào hành vi ấy** như giải pháp tìm mới nhất khi thiếu `ORDER BY`.

## 18. So sánh các mẫu truy vấn

| Mẫu | Trả một hàng mỗi nhóm? | Giữ mọi đồng hạng? | Điểm mạnh | Cần cẩn thận |
|---|---|---|---|---|
| `ROW_NUMBER() = 1` | Có, với khóa sắp đủ xác định | Không | Rộng rãi giữa các DBMS hiện đại, dễ mở rộng | Đặt filter đúng thời điểm; tie-breaker |
| `RANK() = 1` | Không nhất thiết | Có | Giữ tất cả sự kiện cùng mốc lớn nhất | Có thể nhiều hàng mỗi đối tượng |
| PostgreSQL `DISTINCT ON` | Có | Không | Ngắn, thuận tiện | Riêng PostgreSQL; quy tắc `ORDER BY` đầu |
| `LEFT JOIN LATERAL ... LIMIT 1` | Có | Không | Thuận tiện với danh sách cha, chỉ mục top-N | Phụ thuộc dialect, số lượng cha, chỉ mục |
| SQL Server `OUTER APPLY TOP (1)` | Có | Không | Tương tự lateral, giữ cha rỗng | Cú pháp T-SQL; tie-breaker |
| `MAX(timestamp) + JOIN` | Không nếu có đồng hạng | Có, với timestamp khác `NULL` | Dễ hiểu khi muốn các hàng đạt max | Hàng trùng, `NULL` và không có hàng con |
| `NOT EXISTS` (không có hàng sau) | Có nếu quy tắc so sánh tạo thứ tự toàn phần | Có thể, nếu bỏ tie-break | Không đòi window function | Dễ viết sai logic `NULL` và hiệu năng |
| `MAX(event_id)` | Chỉ trả một giá trị ID theo nhóm | Không | Rất gọn khi ID chính là khóa thứ tự hợp lệ | Không tương đương mới nhất theo thời gian nếu ID không bảo đảm |

Lựa chọn thường thực tế là **`ROW_NUMBER()` cho SQL đa DBMS** và **`DISTINCT ON`/`LATERAL` khi sử dụng PostgreSQL và có lý do phù hợp**. Không có một lựa chọn tốt nhất cho mọi dữ liệu.

## 19. Chỉ mục và hiệu năng của “latest per group”

Khi bảng lịch sử lớn, việc tìm hàng mới nhất cho từng đối tượng có thể tốn chi phí sắp xếp hoặc quét nhiều dòng.

Với PostgreSQL và quy tắc:

```sql
WHERE account_id = :account_id
ORDER BY occurred_at DESC NULLS LAST,
         event_id DESC
LIMIT 1
```

có thể cân nhắc chỉ mục B-tree ghép:

```sql
CREATE INDEX idx_demo_events_latest
ON demo_account_events (
    account_id,
    occurred_at DESC NULLS LAST,
    event_id DESC
);
```

Chỉ mục này có thứ tự cột tương thích với việc tìm lịch sử của **một tài khoản** theo mốc mới nhất, rồi ID. Với `LATERAL ... LIMIT 1`, cơ sở dữ liệu có thể dùng chỉ mục để lấy nhanh những hàng đứng đầu của từng tài khoản thay vì sắp toàn bộ lịch sử. Nhưng **không được khẳng định chắc chắn dùng index**, vì optimizer cân nhắc kích thước bảng, thống kê, tỷ lệ hàng khớp và chi phí.

### 19.1. Chỉ mục có giúp ROW_NUMBER không?

Có thể, tùy kế hoạch. Khi `ROW_NUMBER` phân vùng theo `account_id` và sắp theo `occurred_at DESC NULLS LAST, event_id DESC`, một chỉ mục ghép đúng thứ tự có thể giúp giảm hoặc tránh một số công đoạn sort. Nhưng truy vấn vẫn có thể cần xét nhiều bản ghi để phân vùng và tính hạng; không phải cứ có index là tự biến thành “đọc đúng một sự kiện mỗi khách”.

### 19.2. Chỉ mục cho những sự kiện có timestamp hợp lệ

Nếu nghiệp vụ **luôn bỏ qua `occurred_at NULL`**, PostgreSQL có thể cân nhắc một chỉ mục partial:

```sql
CREATE INDEX idx_demo_events_latest_known
ON demo_account_events (
    account_id,
    occurred_at DESC,
    event_id DESC
)
WHERE occurred_at IS NOT NULL;
```

Chỉ mục này hữu ích nhất khi truy vấn cũng nêu điều kiện `occurred_at IS NOT NULL` và optimizer nhận ra có thể áp dụng chỉ mục. Nếu truy vấn cần chọn hàng `NULL` khi tài khoản không có mốc đã biết, partial index ấy **không chứa** những hàng đó và không tự thay thế cho chỉ mục đầy đủ.

### 19.3. Mốc thời gian không duy nhất và index

Chỉ mục `(account_id, occurred_at DESC)` không đảm bảo thứ tự **giữa hai hàng cùng timestamp**. Nếu cần thứ tự xác định, thêm một khóa riêng như `event_id DESC` trong cả câu truy vấn và chỉ mục (nếu phù hợp ngân sách chỉ mục).

Không nên tạo quá nhiều chỉ mục cho mọi biến thể sắp xếp. Chúng tăng chi phí ghi, dung lượng lưu trữ và bảo trì; hãy chọn dựa trên workload và đo bằng kế hoạch thực tế.

### 19.4. Đọc execution plan

```sql
-- PostgreSQL
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    a.account_id,
    latest.event_id
FROM demo_accounts a
LEFT JOIN LATERAL (
    SELECT e.event_id
    FROM demo_account_events e
    WHERE e.account_id = a.account_id
    ORDER BY e.occurred_at DESC NULLS LAST,
             e.event_id DESC
    LIMIT 1
) latest ON TRUE;
```

Quan sát các yếu tố:

- `Index Scan`/`Index Only Scan` hay `Seq Scan`?
- `Sort` có xuất hiện không?
- `LIMIT` được thực hiện trong nhánh tìm hàng con ra sao?
- `actual rows`, `loops` và `Buffers` cho thấy truy vấn thực sự làm gì?
- Có bao nhiêu tài khoản cha, mỗi tài khoản có bao nhiêu sự kiện?

Bảng demo chỉ 11 sự kiện nên `Seq Scan` có thể là kế hoạch hợp lý. Không suy từ một thử nghiệm nhỏ rằng window luôn chậm hơn lateral hay ngược lại.

## 20. Không dùng LIMIT sau toàn bộ truy vấn để thay “mỗi nhóm một”

Sai lầm phổ biến:

```sql
SELECT account_id, event_id, occurred_at
FROM demo_account_events
ORDER BY occurred_at DESC NULLS LAST, event_id DESC
LIMIT 5;
```

Câu trên lấy **5 sự kiện mới nhất của toàn bảng**, không lấy **sự kiện mới nhất của 5 tài khoản**. Một tài khoản có thể chiếm nhiều vị trí trong top 5, trong khi một tài khoản khác không xuất hiện.

Tương tự:

```sql
SELECT account_id, MAX(occurred_at)
FROM demo_account_events
GROUP BY account_id
ORDER BY MAX(occurred_at) DESC
LIMIT 5;
```

cho **5 nhóm có mốc tối đa gần nhất**, nhưng không trả về mọi thuộc tính của **hàng** đạt mốc đó. Nếu cần toàn bộ bản ghi, phải kết hợp với một mẫu chọn hàng như `ROW_NUMBER()` hoặc `DISTINCT ON`.

### 20.1. Lấy mới nhất rồi phân trang theo tài khoản

Giả sử UI cần các tài khoản sắp theo ID và hiển thị sự kiện mới nhất:

```sql
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY occurred_at DESC NULLS LAST, event_id DESC
        ) AS rn
    FROM demo_account_events e
)
SELECT a.account_id, a.account_name, r.event_id
FROM demo_accounts a
LEFT JOIN ranked r
  ON r.account_id = a.account_id AND r.rn = 1
ORDER BY a.account_id
LIMIT 3 OFFSET 0;
```

Với dữ liệu mẫu, trang đầu là tài khoản **101, 102, 103** và một sự kiện tương ứng cho mỗi tài khoản. Nhưng không có nghĩa mọi kế hoạch đều cần xếp hạng toàn bộ bảng trước khi áp `LIMIT`; optimizer có thể biến đổi nếu giữ đúng ngữ nghĩa. Mục tiêu nghiệp vụ là **phân trang đối tượng** sau khi đã xác định một hàng đại diện cho từng đối tượng.

Nếu dùng phân trang offset và dữ liệu thay đổi giữa hai lần tải, kết quả vẫn có thể bị dịch. Với giao diện quy mô lớn, cân nhắc keyset pagination và snapshot/phiên bản dữ liệu khi cần nhất quán.

## 21. Cẩn trọng với tính nhất quán khi có cập nhật đồng thời

Một bản ghi có thể được tạo ngay sau khi truy vấn đọc dữ liệu. Kết quả “mới nhất” của SQL thường chỉ mô tả dữ liệu **nhìn thấy trong ngữ cảnh giao dịch/snapshot của câu truy vấn**, không phải lời hứa rằng kết quả sẽ còn mới nhất ở mọi thời điểm về sau.

Nếu ứng dụng dùng hai câu riêng:

1. `SELECT MAX(occurred_at)` để tìm mốc gần nhất.
2. `SELECT ... WHERE occurred_at = :max_time` để lấy chi tiết.

thì dữ liệu có thể thay đổi **giữa hai câu lệnh**, gây kết quả không khớp hoặc đồng hạng. Một truy vấn duy nhất với `ROW_NUMBER()` hoặc `LATERAL` thường giúp tránh sự tách rời không cần thiết, dù mức nhất quán chính xác vẫn tùy giao dịch/DBMS.

Đối với yêu cầu “mới nhất và phải cập nhật trạng thái”, còn phải xem khóa, isolation level, các cập nhật song song và khả năng phát sinh sự kiện sau lúc đọc. Truy vấn chọn đúng hàng mới nhất **không thay thế** chính sách xử lý cạnh tranh ghi.

### 21.1. Không đồng nhất latest event và current state

Một chuỗi sự kiện có thể gồm:

```text
PENDING → PAID → CANCELLED → RESTORED
```

Trạng thái hiện tại có thể phụ thuộc **quy tắc áp dụng sự kiện**, không đơn giản là chọn một hàng theo timestamp, nhất là khi sự kiện được gửi muộn hoặc có phiên bản. Với nhật ký dạng event sourcing, có thể phải xử lý theo sequence/revision và tính ra trạng thái, thay vì xem `event_status` của hàng mới nhất là trạng thái có hiệu lực.

### 21.2. Khi không nên dùng timestamp làm khóa phân định

Nếu nhiều server có đồng hồ khác nhau hoặc timestamp chỉ lưu đến giây, các sự kiện dễ trùng hoặc đảo thứ tự. Hệ thống cần sắp thứ tự nghiệp vụ mạnh có thể dùng:

- `version_no` được tăng dưới kiểm soát giao dịch theo đối tượng.
- Số thứ tự từ nguồn sự kiện.
- Cặp `(effective_at, revision_no)`.
- Mã sự kiện riêng chỉ dùng làm tie-break khi đã có thứ tự thời gian đáng tin.

**Một `BIGSERIAL`/`IDENTITY` đơn lẻ không bảo đảm thứ tự commit tuyệt đối** khi các giao dịch đồng thời hay rollback, tùy cơ chế DBMS. Hãy chọn khóa phù hợp với câu hỏi “mới nhất” thực tế.

## 22. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ lấy `MAX(timestamp)` khi cần cả ID/trạng thái | Không biết các cột kia thuộc hàng nào | Dùng `ROW_NUMBER()`, `LATERAL` hoặc JOIN theo quy tắc đúng |
| `MAX(timestamp) JOIN` mà quên đồng hạng | Một đối tượng có thể ra nhiều hàng | Thêm tie-break nếu cần một hàng; giữ RANK nếu cần mọi hàng |
| Dùng `MAX(event_id)` như mốc mới nhất | ID có thể tăng không cùng event time | Xác định cột thời gian/phiên bản nghiệp vụ |
| `ORDER BY timestamp DESC` không xử lý `NULL` | PostgreSQL có thể đặt `NULL` lên đầu | `DESC NULLS LAST` hoặc `CASE` |
| `ROW_NUMBER` thiếu khóa phụ | Hàng cùng timestamp không có thứ tự xác định | Thêm khóa unique làm tie-breaker |
| Dùng `RANK()` kèm ID duy nhất nhưng muốn giữ đồng hạng theo thời gian | Hàng cùng timestamp mất đồng hạng | Xếp hạng chỉ theo thời gian, không theo ID |
| Đặt `event_status='PAID'` sai tầng | Nhầm “PAID mới nhất” với “mới nhất là PAID” | Quyết định lọc trước hay sau khi xếp hạng |
| `WHERE ranked.rn=1` sau `LEFT JOIN` | Loại tài khoản không có sự kiện | Đưa `rn = 1` vào `ON` hoặc CTE latest |
| Lọc `occurred_at IS NOT NULL` bên ngoài `LEFT JOIN` | Có thể loại cả tài khoản không có mốc hợp lệ | Lọc trong tập con trước khi chọn latest |
| `LIMIT 1` không có `ORDER BY` | Chọn bản ghi tùy kế hoạch | Chỉ rõ cột sắp và tie-breaker |
| `LIMIT 10` toàn bảng khi muốn mỗi đối tượng một hàng | Chỉ lấy top 10 toàn cục | Phân nhóm trước hoặc dùng per-parent top 1 |
| `DISTINCT` để che JOIN tạo bản sao | Có thể mất hàng hợp lệ mà không chọn đúng latest | Xác định nguyên nhân nhân hàng và quy tắc chọn |
| `DISTINCT ON` sao chép vào SQL Server/MySQL | Lỗi cú pháp | Dùng `ROW_NUMBER` hoặc cú pháp DBMS |
| Dùng `MAX(recorded_at)` thay `MAX(occurred_at)` mà không xác định ý nghĩa | Sự kiện đến muộn thắng sai tiêu chí | Chọn đúng mốc thời gian nghiệp vụ |
| Thiếu tenant trong `PARTITION BY`/`JOIN` | Trộn dữ liệu các đối tượng có cùng ID ở tenant khác | Dùng đầy đủ khóa phạm vi |
| Cho rằng bảng có index thì latest query tự nhanh | Bộ tối ưu có thể vẫn quét/sort | Kiểm tra `EXPLAIN` với dữ liệu thực tế |

## 23. Bài tập tự luyện có đáp án

### Bài 1. Truy vấn một hàng mới nhất theo timestamp

**Yêu cầu:** mỗi `account_id` có sự kiện, lấy đúng một `event_id` theo `occurred_at` mới nhất, `NULL` cuối, cùng thời điểm thì ID lớn hơn thắng.

**Đáp án:**

```sql
WITH ranked AS (
    SELECT
        account_id, event_id, occurred_at,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY occurred_at DESC NULLS LAST, event_id DESC
        ) AS rn
    FROM demo_account_events
)
SELECT account_id, event_id
FROM ranked
WHERE rn = 1
ORDER BY account_id;
```

Kết quả: `(101,1003)`, `(102,2002)`, `(103,3001)`, `(104,4002)`. Tài khoản 105 không có sự kiện nên không xuất hiện.

### Bài 2. Giữ cả tài khoản không có sự kiện

**Yêu cầu:** sửa bài 1 để tài khoản 105 vẫn xuất hiện.

**Đáp án:**

```sql
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY occurred_at DESC NULLS LAST, event_id DESC
        ) AS rn
    FROM demo_account_events e
)
SELECT a.account_id, r.event_id
FROM demo_accounts a
LEFT JOIN ranked r
  ON r.account_id = a.account_id AND r.rn = 1
ORDER BY a.account_id;
```

Kết quả thêm `(105,NULL)`. Đặt `rn = 1` trong `ON`, không đặt ở `WHERE`.

### Bài 3. Những sự kiện cùng thời điểm mới nhất

**Yêu cầu:** với mỗi tài khoản, giữ toàn bộ hàng có cùng `occurred_at` lớn nhất.

**Đáp án:**

```sql
WITH ranked AS (
    SELECT
        account_id, event_id, occurred_at,
        RANK() OVER (
            PARTITION BY account_id
            ORDER BY occurred_at DESC NULLS LAST
        ) AS rnk
    FROM demo_account_events
)
SELECT account_id, event_id
FROM ranked
WHERE rnk = 1
ORDER BY account_id, event_id;
```

Tài khoản 101 có hai dòng: 1002 và 1003. Tài khoản 104 có hai dòng `occurred_at NULL`: 4001 và 4002. Nếu chỉ muốn thời điểm **được xác định**, thêm `WHERE occurred_at IS NOT NULL` ở tầng đầu vào trước khi xếp hạng.

### Bài 4. PAID mới nhất khác mới nhất là PAID

**Yêu cầu:** nêu kết quả cho tài khoản 101 ở hai truy vấn “sự kiện `PAID` mới nhất” và “sự kiện mới nhất có là `PAID` không”.

**Đáp án:** `PAID` mới nhất là **1002**. Sự kiện mới nhất tổng thể là **1003 (CANCELLED)**, nên câu “mới nhất là PAID” cho **FALSE** hoặc loại tài khoản 101 nếu lọc theo trạng thái sau khi chọn latest.

### Bài 5. Phân biệt occurred_at và recorded_at

**Câu hỏi:** với tài khoản 102, mã mới nhất theo hai cột là gì?

**Đáp án:** theo `occurred_at` là **2002**; theo `recorded_at` là **2003**. Sự kiện 2003 xảy ra sớm hơn nhưng được ghi nhận muộn hơn.

### Bài 6. PostgreSQL DISTINCT ON

**Yêu cầu:** dùng một câu `DISTINCT ON` lấy sự kiện gần nhất theo `account_id`.

**Đáp án:**

```sql
SELECT DISTINCT ON (account_id)
    account_id, event_id, occurred_at
FROM demo_account_events
ORDER BY account_id,
         occurred_at DESC NULLS LAST,
         event_id DESC;
```

Kết quả một hàng mỗi tài khoản có sự kiện. Đây là cú pháp riêng PostgreSQL.

### Bài 7. PostgreSQL LATERAL

**Yêu cầu:** dùng `LEFT JOIN LATERAL` trả một hàng cho mọi tài khoản, bao gồm tài khoản không có sự kiện.

**Đáp án:**

```sql
SELECT a.account_id, latest.event_id
FROM demo_accounts a
LEFT JOIN LATERAL (
    SELECT event_id
    FROM demo_account_events e
    WHERE e.account_id = a.account_id
    ORDER BY e.occurred_at DESC NULLS LAST, e.event_id DESC
    LIMIT 1
) latest ON TRUE
ORDER BY a.account_id;
```

ID 105 có `event_id NULL`.

### Bài 8. Nhận diện lỗi với MAX + JOIN

**Câu hỏi:** tại sao tìm `MAX(occurred_at)` rồi JOIN về bảng sự kiện có thể trả hai hàng cho tài khoản 101?

**Đáp án:** cả 1002 và 1003 có cùng timestamp lớn nhất. `MAX` trả **một giá trị mốc thời gian**, không đảm bảo chỉ **một bản ghi có mốc đó**. Nếu cần mọi hàng đồng hạng thì đúng; nếu cần một hàng phải bổ sung chính sách chọn.

### Bài 9. Không có thời gian hợp lệ

**Yêu cầu:** khi `occurred_at` bắt buộc phải khác `NULL`, tài khoản nào không có bản ghi hợp lệ trong bộ dữ liệu?

**Đáp án:** tài khoản **104** (có sự kiện nhưng tất cả `occurred_at NULL`) và **105** (không có sự kiện). Khi dùng `LEFT JOIN` với tập đã lọc `occurred_at IS NOT NULL`, cả hai có `latest_event_id NULL`; nếu muốn phân biệt, đếm sự kiện nguồn.

### Bài 10. Đề xuất chỉ mục

**Yêu cầu:** PostgreSQL thường lấy `LIMIT 1` theo `account_id`, `occurred_at DESC NULLS LAST` và `event_id DESC`. Nêu chỉ mục có thể cân nhắc.

**Đáp án:**

```sql
CREATE INDEX idx_demo_latest
ON demo_account_events (
    account_id,
    occurred_at DESC NULLS LAST,
    event_id DESC
);
```

Chỉ mục có thể hỗ trợ truy xuất các hàng của một tài khoản theo thứ tự cần thiết. Cần kiểm tra kế hoạch thực tế, tần suất ghi và kích thước bảng trước khi áp dụng trên dữ liệu sản xuất.

## Kết luận

“Tìm bản ghi mới nhất của từng đối tượng” là bài toán **chọn toàn bộ một hàng trong mỗi nhóm theo thứ tự xác định**, không chỉ tính `MAX(timestamp)`. Khi cần **một hàng cho mỗi nhóm**, `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` là mẫu rõ ràng và rộng rãi giữa các DBMS. Trên PostgreSQL, `DISTINCT ON` rất gọn và `LEFT JOIN LATERAL ... LIMIT 1` thuận tiện khi cần giữ mọi đối tượng cha. Khi muốn **tất cả hàng cùng thời điểm mới nhất**, dùng `RANK() = 1` hoặc kỹ thuật giữ đồng hạng phù hợp.

Một truy vấn đúng phải xác định rõ **cột thời gian**, **quy tắc đồng hạng**, **vị trí `NULL`**, **bộ lọc áp dụng trước hay sau việc chọn latest**, và **có giữ đối tượng không có bản ghi con hay không**. Đừng dùng ID lớn nhất làm thời gian nếu không có bảo đảm nghiệp vụ; đừng dùng `LIMIT 1` thiếu `ORDER BY`; và kiểm tra đầy đủ khóa tenant/phạm vi nếu nhóm có định danh ghép. Với dữ liệu lớn, chọn chỉ mục theo khóa nhóm và thứ tự sắp, đo bằng execution plan thay vì suy từ cú pháp. Những nguyên tắc ấy giúp mẫu “latest record per entity” chính xác, ổn định và dễ chuyển giữa các hệ quản trị.

