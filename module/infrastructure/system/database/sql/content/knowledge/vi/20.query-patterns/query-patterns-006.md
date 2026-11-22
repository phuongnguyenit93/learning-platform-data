# Ghép các sự kiện thành phiên theo khoảng thời gian

Trong hệ thống web, ứng dụng di động, IoT hoặc nhật ký nghiệp vụ, mỗi tương tác thường được ghi thành **một sự kiện** (*event*): mở trang, nhấn nút, xem sản phẩm, gửi yêu cầu, thanh toán, thay đổi trạng thái thiết bị… Tuy nhiên, báo cáo thường cần một đơn vị lớn hơn sự kiện: **phiên hoạt động** (*session*). Một phiên là một chuỗi sự kiện được xem là cùng một đợt hoạt động theo **quy tắc thời gian** và **chủ thể** đã xác định.

Ví dụ, nếu một người mở ứng dụng lúc 09:00, nhấn nút lúc 09:08, xem sản phẩm lúc 09:38 rồi quay lại lúc 10:09, ta có thể dùng quy tắc **“bắt đầu phiên mới khi khoảng cách giữa hai sự kiện liên tiếp vượt quá 30 phút”**. Khi đó:

- Từ 09:00 tới 09:08: cách 8 phút, **cùng phiên**.
- Từ 09:08 tới 09:38: cách **đúng 30 phút**, vẫn **cùng phiên** theo quy tắc **vượt quá 30 phút**.
- Từ 09:38 tới 10:09: cách 31 phút, **bắt đầu phiên mới**.

Để giải bài toán này bằng SQL, ta thường dùng mẫu **gaps and islands** (*khoảng cách và các dải liên tục*): sắp sự kiện theo thời gian, tìm sự kiện trước bằng **LAG**, đánh dấu điểm bắt đầu phiên bằng **CASE**, rồi cộng tích lũy các dấu bắt đầu bằng **SUM(...) OVER** để gán số phiên.

Bài học thuộc chương **Mẫu truy vấn** của module **Database SQL**. Thực hành chính trên **PostgreSQL 15 trở lên**, với dữ liệu tạm tự chứa; phần sau đối chiếu những khác biệt quan trọng của **MySQL 8.0, SQL Server, SQLite và Oracle Database**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa rõ **khóa chủ thể**, **ngưỡng không hoạt động**, **điều kiện tạo phiên mới** và cách xử lý giá trị đúng ranh giới.
2. Dùng **LAG(event_at)** trong từng nhóm người dùng/thiết bị để lấy thời gian của sự kiện trước.
3. Viết **CASE** xác định một sự kiện có phải điểm bắt đầu phiên hay không.
4. Gán **session_no** bằng tổng tích lũy với **SUM(...) OVER (PARTITION BY ... ORDER BY ... ROWS ...)**.
5. Tổng hợp thời điểm bắt đầu/kết thúc, số sự kiện, thời lượng quan sát và tỷ lệ phiên có hành động mục tiêu.
6. Xử lý các trường hợp **trùng timestamp, sự kiện đến muộn, qua nửa đêm, NULL, thay đổi thứ tự**.
7. Phân biệt ghép theo **khoảng cách giữa các sự kiện liên tiếp** với cửa sổ cố định tính từ lúc bắt đầu phiên.
8. Tránh các lỗi tạo phiên không ổn định do thiếu khóa phá hòa, phân vùng sai hoặc lọc nguồn ở sai thời điểm.
9. Hiểu chi phí sắp xếp, chỉ mục và sự thay đổi khi chuyển cú pháp sang một hệ quản trị khác.

## 2. Trước khi viết SQL: phiên là gì?

Không tồn tại một định nghĩa session duy nhất phù hợp mọi ứng dụng. Với bài thực hành, ta chọn một **quy tắc bất hoạt (inactivity timeout)**:

> Trong mỗi cặp **(user_id, device_id)**, sắp mọi sự kiện theo **event_at**, sau đó theo **event_id** để phá hòa. Sự kiện đầu tiên mở phiên 1. Mỗi sự kiện tiếp theo mở phiên mới **chỉ khi** thời gian tính từ sự kiện ngay trước đó **lớn hơn 30 phút**. Nếu khoảng cách bằng 30 phút, sự kiện vẫn thuộc phiên hiện tại.

Các quyết định trong định nghĩa này đều quan trọng:

| Thành phần | Quy tắc ví dụ | Nếu đổi quy tắc sẽ ra sao? |
| --- | --- | --- |
| Chủ thể hoạt động | Cặp **user_id, device_id** | Ghép chỉ theo user_id có thể trộn phiên từ nhiều thiết bị |
| Thời điểm | **event_at** theo thời gian sự kiện | Dùng thời điểm nhận log có thể đổi thứ tự và khoảng cách |
| Ngưỡng | **30 phút** | 15 hoặc 60 phút có thể chia phiên khác |
| Dấu so sánh | **gap > 30 phút** | Dùng **>=** sẽ bắt đầu phiên mới ngay tại đúng 30 phút |
| Trùng thời điểm | Phá hòa bằng **event_id** | Thiếu thứ tự xác định khiến đánh số hàng khó tái lập |
| Sự kiện khởi đầu | Đánh dấu **1** | Bắt đầu từ số 0 hay 1 ảnh hưởng session_no |
| Đầu ra | Mỗi sự kiện mang session_no; có thể tổng hợp tiếp | Chỉ đếm phiên khác với lưu mọi sự kiện theo phiên |

Một phiên được tạo bằng phép phân nhóm này là **kết quả dẫn xuất** từ dữ liệu và quy tắc. Nó không nhất thiết trùng với phiên đăng nhập của server, cookie session, JWT hay một session_id mà ứng dụng đã phát hành. Nếu sản phẩm có phiên đăng nhập chính thức, cần quyết định có nên ưu tiên định danh đó thay vì tự suy luận bằng khoảng thời gian.

### 2.1. Khoảng cách liên tiếp không phải giới hạn tổng thời lượng

Với ba sự kiện:

~~~text
09:00 ─── 25 phút ─── 09:25 ─── 25 phút ─── 09:50
~~~

Cả ba **cùng một phiên** theo quy tắc bất hoạt 30 phút, dù thời điểm cuối cách đầu **50 phút**. Lý do: mỗi khoảng cách giữa **hai sự kiện kề nhau** đều không vượt ngưỡng.

Ngược lại, nếu nghiệp vụ muốn “một phiên không thể dài quá 30 phút tính từ lần bắt đầu”, đó là **cửa sổ thời lượng cố định** và không thể thay bằng cùng một điều kiện LAG đơn giản. Cần thiết kế cơ chế giới hạn từ **session_start** hoặc xử lý theo khoảng thời gian cố định riêng.

## 3. Dữ liệu thực hành có chủ đích tạo các tình huống khó

Chúng ta tạo một bảng tạm PostgreSQL gồm **23 sự kiện** của bốn người dùng trên những thiết bị khác nhau.

~~~sql
CREATE TEMP TABLE session_demo_events (
    event_id    INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    device_id   TEXT NOT NULL,
    event_at    TIMESTAMPTZ NOT NULL,
    event_type  TEXT NOT NULL
);

INSERT INTO session_demo_events
    (event_id, user_id, device_id, event_at, event_type)
VALUES
    -- Người 101, thiết bị mobile: khoảng đúng 30 phút và 31 phút.
    ( 1, 101, 'mobile', '2026-07-01 09:00:00+00', 'view'),
    ( 2, 101, 'mobile', '2026-07-01 09:08:00+00', 'click'),
    ( 3, 101, 'mobile', '2026-07-01 09:38:00+00', 'view'),
    ( 4, 101, 'mobile', '2026-07-01 09:38:00+00', 'click'),
    ( 5, 101, 'mobile', '2026-07-01 10:09:00+00', 'view'),
    ( 6, 101, 'mobile', '2026-07-01 10:19:00+00', 'purchase'),
    ( 7, 101, 'mobile', '2026-07-01 12:00:00+00', 'view'),
    ( 8, 101, 'mobile', '2026-07-01 12:01:00+00', 'logout'),

    -- Cùng người 101 nhưng trên web: một chuỗi phiên độc lập.
    ( 9, 101, 'web',    '2026-07-01 09:05:00+00', 'view'),
    (10, 101, 'web',    '2026-07-01 09:50:00+00', 'view'),

    -- Người 202: đúng ngưỡng 30 phút ở hai vị trí.
    (11, 202, 'mobile', '2026-07-01 10:00:00+00', 'view'),
    (12, 202, 'mobile', '2026-07-01 10:30:00+00', 'scroll'),
    (13, 202, 'mobile', '2026-07-01 11:01:00+00', 'view'),
    (14, 202, 'mobile', '2026-07-01 11:31:00+00', 'click'),
    (15, 202, 'mobile', '2026-07-01 13:00:00+00', 'view'),

    -- Người 303: event_id không phản ánh đúng thứ tự thời gian.
    (16, 303, 'web',    '2026-07-01 20:05:00+00', 'click'),
    (17, 303, 'web',    '2026-07-01 20:00:00+00', 'view'),
    (18, 303, 'web',    '2026-07-01 20:42:00+00', 'view'),
    (19, 303, 'web',    '2026-07-01 20:42:00+00', 'click'),
    (20, 303, 'web',    '2026-07-01 21:12:00+00', 'purchase'),

    -- Người 404: một phiên đi qua mốc nửa đêm UTC.
    (21, 404, 'mobile', '2026-07-01 23:55:00+00', 'view'),
    (22, 404, 'mobile', '2026-07-02 00:10:00+00', 'click'),
    (23, 404, 'mobile', '2026-07-02 00:41:00+00', 'view');
~~~

Kiểm tra dữ liệu:

~~~sql
SELECT event_id, user_id, device_id, event_at, event_type
FROM session_demo_events
ORDER BY user_id, device_id, event_at, event_id;
~~~

**event_at** được lưu bằng kiểu **TIMESTAMPTZ** với offset **+00** (UTC). PostgreSQL có thể **hiển thị** TIMESTAMPTZ theo múi giờ của phiên kết nối; các mốc giờ được nhắc trong bài đều là **UTC**. Việc so sánh khoảng thời gian giữa các TIMESTAMPTZ dùng các thời điểm thực, không phụ thuộc việc màn hình đang hiển thị theo múi giờ nào.

Các trường hợp đáng chú ý:

- Sự kiện **3 và 4** của người 101/mobile có **cùng timestamp**.
- Sự kiện **12** cách sự kiện 11 **đúng 30 phút**; sự kiện **13** cách 12 **31 phút**.
- Người **101** có đồng thời thiết bị **mobile** và **web**.
- Người **303** có sự kiện 17 lúc 20:00 nhưng **event_id lớn hơn** sự kiện 16 lúc 20:05; không thể dùng event_id làm thứ tự thời gian.
- Sự kiện **21 và 22** cách nhau 15 phút nhưng thuộc **hai ngày UTC khác nhau**.

> Bảng tạm chỉ tồn tại trong phiên PostgreSQL hiện tại. Nếu chạy lại trong cùng phiên, bảng có thể đã tồn tại; hãy mở phiên mới hoặc xóa riêng bảng tạm của bài trước khi tạo lại.

## 4. Bước 1: sắp đúng luồng sự kiện và tìm sự kiện ngay trước

Hàm cửa sổ **LAG** lấy giá trị của hàng đứng trước trong cùng một phân vùng theo thứ tự được chỉ định.

~~~sql
SELECT
    event_id,
    user_id,
    device_id,
    event_at,
    LAG(event_at) OVER (
        PARTITION BY user_id, device_id
        ORDER BY event_at, event_id
    ) AS prev_event_at
FROM session_demo_events
ORDER BY user_id, device_id, event_at, event_id;
~~~

Đọc cấu trúc:

- **PARTITION BY user_id, device_id:** tính riêng từng luồng người dùng/thiết bị.
- **ORDER BY event_at, event_id:** xác định sự kiện trước theo thời gian, phá hòa khi trùng thời gian.
- **LAG(event_at):** cho timestamp của sự kiện ngay trước trong cùng luồng.
- Với sự kiện **đầu tiên của một luồng**, LAG trả **NULL** vì không có hàng trước đó.

### 4.1. Kết quả người 101/mobile

| event_id | event_at (UTC) | prev_event_at (UTC) | Khoảng cách |
| ---: | --- | --- | --- |
| 1 | 09:00 | NULL | Bắt đầu luồng |
| 2 | 09:08 | 09:00 | 8 phút |
| 3 | 09:38 | 09:08 | **30 phút** |
| 4 | 09:38 | 09:38 | 0 phút |
| 5 | 10:09 | 09:38 | **31 phút** |
| 6 | 10:19 | 10:09 | 10 phút |
| 7 | 12:00 | 10:19 | 101 phút |
| 8 | 12:01 | 12:00 | 1 phút |

Hai sự kiện trùng event_at vẫn có thứ tự **theo event_id**, vì vậy sự kiện 4 nhìn thấy thời gian của sự kiện 3. Trong bài toán phân phiên chỉ dựa vào thời điểm, khoảng cách giữa chúng bằng 0 và không cần tạo phiên mới.

### 4.2. Tại sao không ORDER BY event_id?

Trong dữ liệu người 303/web:

~~~text
event_id 17: 20:00
event_id 16: 20:05
event_id 18: 20:42
event_id 19: 20:42
event_id 20: 21:12
~~~

Nếu ORDER BY event_id, thứ tự hai sự kiện đầu sẽ thành **20:05 → 20:00**. Khoảng thời gian âm và sự kiện trước bị xác định sai. ID ghi log hoặc thứ tự nhận dữ liệu không nhất thiết phản ánh đúng **thứ tự sự kiện xảy ra**.

**LAG chỉ đáng tin khi thứ tự trong OVER diễn đạt đúng thời gian nghiệp vụ.** Nếu một nguồn chỉ có timestamp với độ phân giải theo giây, nhiều sự kiện có thể trùng timestamp; bổ sung một cột định danh hoặc số thứ tự có ý nghĩa để phá hòa.

## 5. Bước 2: tính khoảng cách và đánh dấu phiên mới

Trên PostgreSQL, phép trừ hai giá trị TIMESTAMPTZ trả **INTERVAL**:

~~~sql
event_at - prev_event_at
~~~

Để đánh dấu điểm bắt đầu phiên:

~~~sql
CASE
    WHEN prev_event_at IS NULL THEN 1
    WHEN event_at - prev_event_at > INTERVAL '30 minutes' THEN 1
    ELSE 0
END AS new_session
~~~

Theo quy ước đã chọn:

- **1**: sự kiện này là điểm bắt đầu một phiên mới.
- **0**: sự kiện này tiếp tục phiên của sự kiện trước.

Viết thành một truy vấn hai bước:

~~~sql
WITH ordered_events AS (
    SELECT
        e.*,
        LAG(event_at) OVER (
            PARTITION BY user_id, device_id
            ORDER BY event_at, event_id
        ) AS prev_event_at
    FROM session_demo_events AS e
),
marked_events AS (
    SELECT
        *,
        event_at - prev_event_at AS idle_gap,
        CASE
            WHEN prev_event_at IS NULL THEN 1
            WHEN event_at - prev_event_at > INTERVAL '30 minutes' THEN 1
            ELSE 0
        END AS new_session
    FROM ordered_events
)
SELECT
    event_id,
    user_id,
    device_id,
    event_at,
    prev_event_at,
    idle_gap,
    new_session
FROM marked_events
ORDER BY user_id, device_id, event_at, event_id;
~~~

### 5.1. Điểm bắt đầu phiên của người 101/mobile

| event_id | gap | new_session | Giải thích |
| ---: | --- | ---: | --- |
| 1 | NULL | **1** | Sự kiện đầu tiên |
| 2 | 8 phút | 0 | Chưa vượt ngưỡng |
| 3 | **30 phút** | **0** | Bằng ngưỡng, quy tắc là **>** |
| 4 | 0 phút | 0 | Cùng timestamp |
| 5 | **31 phút** | **1** | Vượt ngưỡng |
| 6 | 10 phút | 0 | Tiếp tục phiên |
| 7 | 101 phút | **1** | Bắt đầu phiên khác |
| 8 | 1 phút | 0 | Tiếp tục phiên |

Ở đây **new_session** mới chỉ là một cờ 0/1 trên từng sự kiện, chưa phải **số thứ tự phiên**.

### 5.2. Dấu > khác dấu >=

Nếu đổi điều kiện thành:

~~~sql
WHEN event_at - prev_event_at >= INTERVAL '30 minutes' THEN 1
~~~

thì một sự kiện đến **đúng 30 phút** sau sự kiện trước cũng mở phiên mới. Điều này làm thay đổi cách phân nhóm của sự kiện **3**, **12**, **14**, **20** trong bộ dữ liệu mẫu.

Không có dấu nào “đúng hơn” trong mọi sản phẩm. Nếu quy tắc nói **“quá 30 phút không hoạt động”**, thông thường chọn **>**; nếu nói **“từ 30 phút trở lên”**, chọn **>=**. Việc định nghĩa bằng lời và code phải thống nhất.

### 5.3. Viết bằng phép cộng thời gian

Một cách tương đương trong PostgreSQL khi event_at và prev_event_at đều không NULL:

~~~sql
event_at > prev_event_at + INTERVAL '30 minutes'
~~~

Cách này có lợi khi chuyển sang một số phương ngữ SQL dùng **DATEADD** hoặc **DATE_ADD** thay cho phép trừ hai timestamp dạng INTERVAL.

## 6. Bước 3: tổng tích lũy để gán session_no

Khi mỗi điểm bắt đầu phiên có new_session = 1, ta chỉ cần **cộng tích lũy** các cờ theo thứ tự thời gian. Cứ gặp một số 1 mới, tổng tăng thêm 1, tức chuyển sang phiên kế tiếp.

~~~text
event_id:       1   2   3   4   5   6   7   8
new_session:    1   0   0   0   1   0   1   0
session_no:     1   1   1   1   2   2   3   3
~~~

Trong PostgreSQL:

~~~sql
SUM(new_session) OVER (
    PARTITION BY user_id, device_id
    ORDER BY event_at, event_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS session_no
~~~

**SUM(new_session)** là tổng tích lũy; **PARTITION BY** đặt lại bộ đếm cho mỗi cặp (user_id, device_id); **ORDER BY** giữ trình tự sự kiện; **ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW** yêu cầu tính tổng từ hàng đầu tiên của luồng tới **hàng đang xét**.

### 6.1. Truy vấn hoàn chỉnh gán số phiên cho từng sự kiện

~~~sql
WITH
    ordered_events AS (
        SELECT
            e.*,
            LAG(e.event_at) OVER (
                PARTITION BY e.user_id, e.device_id
                ORDER BY e.event_at, e.event_id
            ) AS prev_event_at
        FROM session_demo_events AS e
    ),
    marked_events AS (
        SELECT
            *,
            CASE
                WHEN prev_event_at IS NULL THEN 1
                WHEN event_at - prev_event_at > INTERVAL '30 minutes'
                    THEN 1
                ELSE 0
            END AS new_session
        FROM ordered_events
    ),
    sessionized_events AS (
        SELECT
            *,
            SUM(new_session) OVER (
                PARTITION BY user_id, device_id
                ORDER BY event_at, event_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS session_no
        FROM marked_events
    )
SELECT
    event_id,
    user_id,
    device_id,
    event_at,
    event_type,
    new_session,
    session_no
FROM sessionized_events
ORDER BY user_id, device_id, event_at, event_id;
~~~

Mỗi sự kiện giờ có **session_no**. Tuy nhiên, số **1** có thể xuất hiện ở nhiều người dùng hoặc thiết bị khác nhau: session_no chỉ có ý nghĩa **bên trong phân vùng**. Một khóa phiên ở báo cáo phải bao gồm cả **user_id, device_id, session_no**.

### 6.2. Vì sao chia thành nhiều CTE?

Trong PostgreSQL, không thể tùy tiện **lồng một hàm cửa sổ bên trong một hàm cửa sổ khác tại cùng cấp SELECT**, chẳng hạn đưa trực tiếp LAG(...) vào SUM(...) OVER(...). Ta tách:

~~~text
ordered_events       → LAG để biết sự kiện trước
marked_events        → CASE để có cờ bắt đầu
sessionized_events   → SUM tích lũy để có session_no
~~~

Tách bước giúp câu SQL dễ kiểm tra và thể hiện rõ trách nhiệm. Bộ tối ưu có thể sắp xếp kế hoạch thực thi phù hợp; CTE không có nghĩa mọi bước luôn được lưu vật lý thành một bảng trung gian.

### 6.3. Vì sao nên khai báo khung ROWS tường minh?

Nếu chỉ viết:

~~~sql
SUM(new_session) OVER (
    PARTITION BY user_id, device_id
    ORDER BY event_at
)
~~~

thì một số hệ quản trị, bao gồm PostgreSQL, dùng mặc định một khung **RANGE** có xử lý các hàng **cùng giá trị ORDER BY** như cùng một nhóm đồng hạng (*peers*). Trong bài có những sự kiện trùng event_at, kiểu khung mặc định có thể không diễn đạt chính xác yêu cầu “cộng tới **từng hàng hiện tại**”.

Vì vậy, mẫu sử dụng:

~~~sql
ORDER BY event_at, event_id
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Với khóa event_id duy nhất, thứ tự của từng hàng được xác định; **ROWS** nói rõ rằng đây là **tổng theo vị trí hàng**, không phải theo nhóm timestamp bằng nhau.

## 7. Bước 4: tổng hợp thành một hàng cho mỗi phiên

Khi session_no đã được gắn vào từng sự kiện, ta có thể nhóm theo **(user_id, device_id, session_no)** để tạo báo cáo một dòng/phiên.

~~~sql
WITH
    ordered_events AS (
        SELECT e.*,
               LAG(event_at) OVER (
                   PARTITION BY user_id, device_id
                   ORDER BY event_at, event_id
               ) AS prev_event_at
        FROM session_demo_events AS e
    ),
    marked_events AS (
        SELECT *,
               CASE
                   WHEN prev_event_at IS NULL THEN 1
                   WHEN event_at - prev_event_at > INTERVAL '30 minutes'
                       THEN 1
                   ELSE 0
               END AS new_session
        FROM ordered_events
    ),
    sessionized_events AS (
        SELECT *,
               SUM(new_session) OVER (
                   PARTITION BY user_id, device_id
                   ORDER BY event_at, event_id
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS session_no
        FROM marked_events
    )
SELECT
    user_id,
    device_id,
    session_no,
    MIN(event_at) AS session_start,
    MAX(event_at) AS session_end,
    COUNT(*) AS event_count,
    COUNT(*) FILTER (
        WHERE event_type = 'purchase'
    ) AS purchase_events,
    MAX(event_at) - MIN(event_at) AS observed_duration
FROM sessionized_events
GROUP BY user_id, device_id, session_no
ORDER BY user_id, device_id, session_no;
~~~

**Grain của kết quả:** một hàng cho mỗi phiên thuộc một cặp user_id/device_id.

Trong ví dụ:

- **MIN(event_at)** là thời điểm sự kiện đầu tiên của phiên.
- **MAX(event_at)** là thời điểm sự kiện cuối cùng của phiên.
- **COUNT(*)** đếm số sự kiện trong phiên.
- **purchase_events** đếm số sự kiện được gắn event_type = 'purchase'.
- **observed_duration** là **khoảng thời gian giữa sự kiện đầu và cuối**, không đồng nghĩa “thời gian người dùng nhìn màn hình”.

### 7.1. Kết quả dự kiến toàn bộ 12 phiên

Các giờ dưới đây tính theo **UTC** ngày 01/07/2026, trừ hàng ghi rõ 02/07.

| user_id | device | session_no | Bắt đầu | Kết thúc | event_count | purchase_events |
| ---: | --- | ---: | --- | --- | ---: | ---: |
| 101 | mobile | 1 | 01/07 09:00 | 01/07 09:38 | 4 | 0 |
| 101 | mobile | 2 | 01/07 10:09 | 01/07 10:19 | 2 | 1 |
| 101 | mobile | 3 | 01/07 12:00 | 01/07 12:01 | 2 | 0 |
| 101 | web | 1 | 01/07 09:05 | 01/07 09:05 | 1 | 0 |
| 101 | web | 2 | 01/07 09:50 | 01/07 09:50 | 1 | 0 |
| 202 | mobile | 1 | 01/07 10:00 | 01/07 10:30 | 2 | 0 |
| 202 | mobile | 2 | 01/07 11:01 | 01/07 11:31 | 2 | 0 |
| 202 | mobile | 3 | 01/07 13:00 | 01/07 13:00 | 1 | 0 |
| 303 | web | 1 | 01/07 20:00 | 01/07 20:05 | 2 | 0 |
| 303 | web | 2 | 01/07 20:42 | 01/07 21:12 | 3 | 1 |
| 404 | mobile | 1 | 01/07 23:55 | 02/07 00:10 | 2 | 0 |
| 404 | mobile | 2 | 02/07 00:41 | 02/07 00:41 | 1 | 0 |

Tổng số sự kiện của 12 phiên là **23**. Có **2 phiên chứa sự kiện purchase**: phiên thứ 2 của 101/mobile và phiên thứ 2 của 303/web.

### 7.2. Độ dài một phiên chỉ có một sự kiện

Nếu session_start = session_end, **observed_duration = 0**. Điều đó không có nghĩa người dùng không dành thời gian sử dụng sản phẩm: chỉ là **không quan sát được thêm sự kiện nào** để ước lượng khoảng hoạt động.

Để đo thời gian tương tác thực tế, thường cần sự kiện **heartbeat**, **page_visible**, **app_background**, hoặc một quy tắc gán thời lượng cho sự kiện cuối. “Thời gian từ sự kiện đầu tới sự kiện cuối” là một chỉ tiêu rõ ràng, nhưng không phải lúc nào cũng là “thời gian sử dụng”.

### 7.3. Đổi INTERVAL thành số phút

Trong PostgreSQL:

~~~sql
EXTRACT(EPOCH FROM (MAX(event_at) - MIN(event_at))) / 60.0
    AS observed_minutes
~~~

Biểu thức tính số giây của khoảng thời gian rồi chia cho 60. Ví dụ:

- 101/mobile phiên 1: **38 phút**.
- 202/mobile phiên 1: **30 phút**.
- 404/mobile phiên 1: **15 phút**, dù qua nửa đêm.

Nếu báo cáo cần cố định số chữ số thập phân, có thể ép sang NUMERIC và dùng ROUND theo cú pháp PostgreSQL.

## 8. Một truy vấn báo cáo tổng hợp có thể chạy trực tiếp

Đây là bản đầy đủ từ sự kiện đến **số phiên, số sự kiện và số phiên có mua hàng** theo người dùng/thiết bị:

~~~sql
WITH
    event_order AS (
        SELECT
            e.event_id,
            e.user_id,
            e.device_id,
            e.event_at,
            e.event_type,
            LAG(e.event_at) OVER (
                PARTITION BY e.user_id, e.device_id
                ORDER BY e.event_at, e.event_id
            ) AS previous_at
        FROM session_demo_events AS e
    ),
    session_boundaries AS (
        SELECT
            *,
            CASE
                WHEN previous_at IS NULL
                  OR event_at - previous_at > INTERVAL '30 minutes'
                THEN 1 ELSE 0
            END AS starts_new
        FROM event_order
    ),
    events_with_session AS (
        SELECT
            *,
            SUM(starts_new) OVER (
                PARTITION BY user_id, device_id
                ORDER BY event_at, event_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS session_no
        FROM session_boundaries
    ),
    sessions AS (
        SELECT
            user_id,
            device_id,
            session_no,
            MIN(event_at) AS session_start,
            MAX(event_at) AS session_end,
            COUNT(*) AS events_in_session,
            COUNT(*) FILTER (WHERE event_type = 'purchase')
                AS purchase_events
        FROM events_with_session
        GROUP BY user_id, device_id, session_no
    )
SELECT
    user_id,
    device_id,
    COUNT(*) AS session_count,
    SUM(events_in_session) AS event_count,
    COUNT(*) FILTER (WHERE purchase_events > 0)
        AS sessions_with_purchase,
    ROUND(AVG(events_in_session::NUMERIC), 2)
        AS avg_events_per_session
FROM sessions
GROUP BY user_id, device_id
ORDER BY user_id, device_id;
~~~

Kết quả:

| user_id | device_id | session_count | event_count | sessions_with_purchase | avg_events_per_session |
| ---: | --- | ---: | ---: | ---: | ---: |
| 101 | mobile | 3 | 8 | 1 | 2.67 |
| 101 | web | 2 | 2 | 0 | 1.00 |
| 202 | mobile | 3 | 5 | 0 | 1.67 |
| 303 | web | 2 | 5 | 1 | 2.50 |
| 404 | mobile | 2 | 3 | 0 | 1.50 |
| **Tổng** | | **12** | **23** | **2** | |

**Điểm quan trọng khi đếm:** session_no = 1 **không phải một ID toàn cục**, vì mỗi nhóm user_id/device_id có một phiên số 1. Muốn đếm tổng số phiên toàn dữ liệu, hãy **đếm các hàng từ CTE sessions**, không đếm DISTINCT(session_no) toàn bảng.

## 9. Mẫu gaps and islands: vì sao tổng cờ tạo thành nhóm?

Bài toán **gaps and islands** là tìm những chuỗi phần tử liên tiếp (*islands*) được ngăn cách bởi những khoảng trống (*gaps*). Với sessionization:

- **Gap:** thời gian giữa hai sự kiện liền nhau vượt ngưỡng không hoạt động.
- **Island:** mọi sự kiện nằm giữa hai lần xuất hiện gap, gồm một phiên.

Ví dụ người 202/mobile:

~~~text
10:00 ─30m─ 10:30 ─31m─ 11:01 ─30m─ 11:31 ─89m─ 13:00
   │           │          │           │          │
   └─ Phiên 1 ─┘          └─ Phiên 2 ─┘          Phiên 3

starts_new:   1           0          1           0          1
running SUM:  1           1          2           2          3
~~~

Tổng tích lũy của các cờ 0/1 tạo ra cùng một số liên tiếp cho những sự kiện cùng phiên. Khác với một phép GROUP BY thông thường, ta không thể biết session_no của sự kiện chỉ từ riêng event_at: **nó phụ thuộc vị trí của các gap trước đó**.

### 9.1. LAG và SUM giải quyết hai nhiệm vụ khác nhau

**LAG** trả lời: “Sự kiện trước của người/thiết bị này xảy ra lúc nào?”.

**CASE** trả lời: “Khoảng cách tới sự kiện trước có vượt ngưỡng không?”.

**SUM cửa sổ** trả lời: “Tính tới sự kiện hiện tại đã có bao nhiêu lần bắt đầu phiên?”.

Tách ba nhiệm vụ như vậy giúp dễ thay quy tắc ngưỡng hoặc thêm điều kiện tạo phiên mới, trong khi vẫn giữ nguyên mẫu đánh số bằng tổng tích lũy.

### 9.2. Không dùng GROUP BY theo từng ô 30 phút để thay thế

Một cách dễ nhầm là gom các timestamp thành các khoảng cố định **09:00–09:30, 09:30–10:00...**. Đó là **time bucketing**, không phải **inactivity sessionization**.

Ví dụ:

~~~text
09:25 ─ 10 phút ─ 09:35
~~~

Hai sự kiện chỉ cách nhau 10 phút nên cùng phiên theo quy tắc bất hoạt 30 phút. Nhưng chúng nằm ở hai ô thời gian nửa giờ khác nhau. Ngược lại, hai sự kiện thuộc cùng ô cố định cũng chưa chắc cùng phiên theo những quy tắc khác của sản phẩm.

**Sessionization là phân nhóm dựa trên mối quan hệ giữa các sự kiện liên tiếp**, không chỉ là chia trục thời gian thành các ô cố định.

## 10. Tại sao PARTITION BY phải chứa đúng khóa chủ thể?

Trong bài, định nghĩa phiên áp dụng riêng cho **(user_id, device_id)**.

~~~sql
PARTITION BY user_id, device_id
~~~

Nếu bỏ device_id:

~~~sql
PARTITION BY user_id
~~~

sự kiện của người 101 trên **mobile** và **web** sẽ xen kẽ theo thời gian. Một sự kiện web lúc 09:05 có thể trở thành “sự kiện trước” của mobile lúc 09:08. Điều này làm thay đổi các khoảng cách và gắn phiên không đúng quy tắc ban đầu.

### 10.1. Khi nào chỉ PARTITION BY user_id là hợp lý?

Nếu doanh nghiệp định nghĩa một phiên **xuyên thiết bị**, tức sự kiện trên laptop và điện thoại của cùng người được phép nối vào một luồng hoạt động, thì chỉ user_id có thể là chủ thể đúng. Tuy nhiên, cần quan tâm đến:

- Tài khoản dùng chung bởi nhiều người.
- Sự kiện từ các thiết bị có đồng hồ không đồng bộ.
- Thiết bị ngoại tuyến gửi sự kiện đến muộn.
- Nhiều cửa sổ ứng dụng song song.
- Quy tắc xác định người dùng khi chưa đăng nhập.

Không nên vô tình gộp các thiết bị chỉ vì “cùng user_id” xuất hiện trong dữ liệu.

### 10.2. Người dùng ẩn danh và NULL

Trong bảng thực hành, user_id được khai báo **NOT NULL**. Ở dữ liệu thực, nhiều sự kiện có thể chưa xác định người dùng.

Nếu **PARTITION BY user_id** và user_id NULL, mọi sự kiện NULL có thể nằm trong **cùng một phân vùng** và bị ghép thành phiên chung của nhiều người không liên quan.

Giải pháp là xác định **khóa chủ thể ổn định trong phạm vi cần thiết** như anonymous_id, device_install_id hoặc một định danh phiên gốc, và có quy tắc rõ ràng khi chuyển từ anonymous sang tài khoản đã đăng nhập. **COALESCE(user_id, 0)** cho mọi người ẩn danh thường không đủ để phân biệt các cá nhân.

## 11. Event trùng timestamp và thứ tự xác định

Cả người 101/mobile và người 303/web có **hai sự kiện cùng event_at**. Nếu cửa sổ chỉ sắp theo event_at, các sự kiện đồng thời không có vị trí thứ tự duy nhất được bảo đảm.

Do đó, bài dùng:

~~~sql
ORDER BY event_at, event_id
~~~

Ở đây event_id là PRIMARY KEY, giúp tạo **thứ tự toàn phần** bên trong từng phân vùng. Điều này quan trọng nếu sau này ngoài thời gian ta còn kiểm tra **event_type của sự kiện ngay trước** để tạo phiên mới.

### 11.1. Hai sự kiện cùng timestamp có nhất thiết là bản sao?

**Không.** Một người có thể phát sinh **view** và **click** trong cùng giây. Hai bản ghi có timestamp giống nhau vẫn có thể đại diện cho hai hành động khác nhau.

Ngược lại, một pipeline có thể gửi lại cùng một sự kiện khi retry. Khi đó cần **khử trùng lặp sự kiện** (*deduplication*) dựa trên một khóa sự kiện nguồn tin cậy, ví dụ source_event_id, trước khi sessionize.

Không nên xóa mọi hàng trùng **(user_id, event_at)**, vì cách này có thể xóa những hành động có thật.

### 11.2. Nếu nguồn không có event_id duy nhất?

Có thể dùng một bộ khóa sắp xếp khác, chẳng hạn:

~~~text
event_at, source_sequence, source_event_id
~~~

Điều kiện là tổ hợp đó **đủ xác định thứ tự giữa các sự kiện**. Không nên lấy số thứ tự ROW_NUMBER từ một tập không có ORDER BY ổn định rồi coi nó là định danh sự kiện lâu dài.

## 12. Sự kiện đến muộn có thể thay đổi toàn bộ cách chia phiên

Trong hệ thống thực, **event_at** là thời điểm hành động xảy ra, còn thời điểm nhận sự kiện có thể muộn hơn vì mạng, chế độ ngoại tuyến hoặc truyền lại.

Hãy xét luồng 101/web ban đầu:

~~~text
09:05 ─────── 45 phút ─────── 09:50
              > 30 phút

Kết quả: 2 phiên.
~~~

Giả sử hệ thống sau đó nhận một sự kiện **đã xảy ra lúc 09:30**:

~~~text
09:05 ─25 phút─ 09:30 ─20 phút─ 09:50
          ≤30 phút        ≤30 phút

Kết quả sau khi backfill: 1 phiên.
~~~

Một sự kiện đến muộn có thể **nối hai phiên cũ thành một phiên**. Đây không chỉ là việc thêm một hàng vào phiên có sẵn: số phiên, thời điểm kết thúc, số sự kiện và các chỉ tiêu theo phiên đều có thể thay đổi.

### 12.1. Thí nghiệm không sửa bảng gốc

Ta thêm sự kiện ảo vào một CTE bằng UNION ALL:

~~~sql
WITH
    events_with_late_arrival AS (
        SELECT
            event_id, user_id, device_id, event_at, event_type
        FROM session_demo_events
        WHERE user_id = 101 AND device_id = 'web'

        UNION ALL

        SELECT
            1001,
            101,
            'web'::TEXT,
            TIMESTAMPTZ '2026-07-01 09:30:00+00',
            'view'::TEXT
    ),
    ordered AS (
        SELECT
            *,
            LAG(event_at) OVER (
                PARTITION BY user_id, device_id
                ORDER BY event_at, event_id
            ) AS previous_at
        FROM events_with_late_arrival
    ),
    marked AS (
        SELECT
            *,
            CASE
                WHEN previous_at IS NULL
                  OR event_at - previous_at > INTERVAL '30 minutes'
                THEN 1 ELSE 0
            END AS starts_new
        FROM ordered
    ),
    numbered AS (
        SELECT
            *,
            SUM(starts_new) OVER (
                PARTITION BY user_id, device_id
                ORDER BY event_at, event_id
                ROWS UNBOUNDED PRECEDING
            ) AS session_no
        FROM marked
    )
SELECT event_id, event_at, previous_at, starts_new, session_no
FROM numbered
ORDER BY event_at, event_id;
~~~

Cả ba sự kiện 09:05, 09:30, 09:50 sẽ có **session_no = 1**. Không cần thay đổi ngưỡng hoặc thuật toán; chỉ bổ sung một sự kiện đúng thời gian đã làm lại ranh giới phiên.

### 12.2. Hệ quả khi lưu session_id vào database

Một nhãn tạo bằng:

~~~text
user_id + device_id + session_no
~~~

chỉ ổn định **trong một kết quả đã phân phiên tại thời điểm đó**. Khi có dữ liệu đến muộn, một phiên mới được chèn vào trước những phiên cũ hoặc hai phiên được hợp nhất, **session_no có thể đổi**. Không nên coi số phiên tích lũy là khóa định danh bền vững, bất biến qua mọi lần nạp lại dữ liệu.

Hệ thống lưu phiên lâu dài có thể cần:

- Một **session_id do dịch vụ quản lý phiên phát hành**, nếu có.
- Quy tắc **watermark/grace period** trước khi coi phiên đã hoàn tất.
- Cơ chế **tính lại các phiên bị ảnh hưởng** khi backfill sự kiện.
- Một bảng ánh xạ hoặc lịch sử thay đổi khi cần duy trì tham chiếu ổn định.
- Giám sát event_at và received_at để phát hiện độ trễ hoặc dữ liệu từ thiết bị lệch đồng hồ.

**SQL cửa sổ tính đúng trên tập đầu vào hiện có**; nó không tự giải quyết bài toán quản trị dữ liệu đến muộn qua nhiều lần cập nhật.

## 13. Tránh cắt luồng theo ngày trước khi phân phiên

Người 404 có:

~~~text
2026-07-01 23:55 ──15 phút──► 2026-07-02 00:10
                                      │
                                     31 phút
                                      ▼
                              2026-07-02 00:41
~~~

Theo quy tắc bất hoạt 30 phút, hai sự kiện đầu **cùng phiên**, dù nằm ở hai ngày UTC khác nhau. Sự kiện 00:41 mở phiên mới.

### 13.1. Cách sai: phân vùng theo ngày ngay trong LAG

~~~sql
-- Không đúng cho phiên có thể đi qua nửa đêm:
LAG(event_at) OVER (
    PARTITION BY user_id, device_id, event_at::DATE
    ORDER BY event_at, event_id
)
~~~

Cách này đặt lại chuỗi sự kiện khi ngày thay đổi, khiến 00:10 bị xem là **sự kiện đầu tiên của một phân vùng mới** dù chỉ cách 23:55 có 15 phút. Nó tạo thêm phiên không có trong định nghĩa nghiệp vụ.

### 13.2. Cách đúng: phân phiên trước, gắn ngày báo cáo sau

Sau khi có bảng **sessions**, có thể chọn một ngày quy ước cho phiên, chẳng hạn **ngày bắt đầu phiên**:

~~~sql
-- Đặt sau CTE sessions trong một truy vấn hoàn chỉnh.
SELECT
    (session_start AT TIME ZONE 'UTC')::DATE AS session_start_day_utc,
    COUNT(*) AS sessions_started
FROM sessions
GROUP BY (session_start AT TIME ZONE 'UTC')::DATE
ORDER BY session_start_day_utc;
~~~

Đoạn trên là **phần SELECT cuối** và cần chạy sau các CTE đã tạo ra **sessions**. Với dữ liệu ví dụ, phiên 404/mobile số 1 được tính vào **ngày 01/07**, vì bắt đầu lúc 23:55 UTC; phiên số 2 vào **ngày 02/07**.

Nếu báo cáo theo ngày tại Việt Nam, dùng múi giờ nghiệp vụ rõ ràng, ví dụ:

~~~sql
(session_start AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
~~~

Không âm thầm lấy **event_at::DATE** trên TIMESTAMPTZ rồi cho rằng mọi phiên và mọi máy đều dùng UTC: phép ép kiểu này có thể phụ thuộc **múi giờ của phiên kết nối**.

### 13.3. Lọc theo ngày cũng có thể cắt phiên

Nếu **WHERE event_at >= '2026-07-02'** được đặt **trước LAG**, sự kiện 23:55 của ngày trước bị mất. Khi đó 00:10 trở thành sự kiện đầu tiên trong dữ liệu đang xét và bị gắn phiên mới không đúng so với lịch sử đầy đủ.

Các chiến lược:

- **Tính phiên trên luồng đủ ngữ cảnh**, rồi lọc các phiên theo ngày bắt đầu hoặc theo điều kiện giao cắt thời gian.
- Nếu chỉ truy vấn một khoảng gần đây, **đọc thêm dữ liệu ngữ cảnh trước khoảng đầu** theo một quy tắc có thể chứng minh đủ cho yêu cầu.
- Với luồng kéo dài và cần cập nhật liên tục, **lưu trạng thái phiên** hoặc sử dụng hệ xử lý tăng dần có cơ chế quản lý late events.

Chỉ lấy thêm **30 phút trước mốc lọc** có thể đủ để biết có sự kiện ngay trước mốc hay không, nhưng **không luôn đủ để tìm điểm bắt đầu gốc của một phiên kéo dài nhiều giờ nhờ những sự kiện liên tiếp**. Khi cần session_start thật, phải xét đủ phần lịch sử liên quan hoặc dùng trạng thái phiên đã lưu.

## 14. Không lọc sai loại sự kiện trước khi tìm gap

Giả sử mục tiêu là **đếm số lượt page_view trong mỗi phiên**, nhưng quy tắc bất hoạt coi **mọi tương tác** là hoạt động.

Dữ liệu:

~~~text
09:00  view
09:20  click
09:40  view
~~~

Nếu chỉ giữ **view** trước khi chạy LAG, khoảng giữa hai view là **40 phút**, và ta tạo **hai phiên**. Nhưng khi tính trên mọi sự kiện:

~~~text
09:00 ─20 phút─ 09:20 ─20 phút─ 09:40
~~~

thì cả ba sự kiện cùng một phiên. **Click lúc 09:20 đã nối khoảng thời gian giữa hai view.**

Do đó:

1. Xác định **loại sự kiện nào được tính là hoạt động** để chia phiên.
2. Chạy sessionization trên đúng tập sự kiện ấy.
3. Chỉ sau khi gắn phiên, mới tính số view/click/purchase theo phiên, hoặc lọc các loại event dùng cho báo cáo.

Ví dụ mẫu trong CTE sessions đã dùng:

~~~sql
COUNT(*) FILTER (WHERE event_type = 'purchase')
~~~

để **đếm purchase sau khi các sự kiện đã được phân phiên**. Không phải lọc chỉ giữ purchase trước LAG, vì như vậy sẽ tạo ra những “phiên mua hàng” có ngữ nghĩa khác.

## 15. Quy tắc kết thúc bằng logout hoặc một sự kiện nghiệp vụ

Trong một số sản phẩm, phiên phải kết thúc ngay khi người dùng **logout**, dù sự kiện sau đó xảy ra chỉ vài phút sau. Lúc này chỉ dựa vào khoảng cách thời gian là không đủ.

Có thể lấy thêm loại sự kiện trước bằng LAG:

~~~sql
WITH ordered AS (
    SELECT
        e.*,
        LAG(event_at) OVER (
            PARTITION BY user_id, device_id
            ORDER BY event_at, event_id
        ) AS previous_at,
        LAG(event_type) OVER (
            PARTITION BY user_id, device_id
            ORDER BY event_at, event_id
        ) AS previous_type
    FROM session_demo_events AS e
)
SELECT
    *,
    CASE
        WHEN previous_at IS NULL THEN 1
        WHEN previous_type = 'logout' THEN 1
        WHEN event_at - previous_at > INTERVAL '30 minutes' THEN 1
        ELSE 0
    END AS starts_new
FROM ordered
ORDER BY user_id, device_id, event_at, event_id;
~~~

Nếu một sự kiện đứng ngay sau logout trong thứ tự thời gian, nó mở phiên mới. Điều này có nghĩa **logout thuộc phiên trước**, còn sự kiện kế tiếp thuộc phiên mới.

**Chú ý:** mẫu này chỉ cho thấy cách tính cờ bắt đầu theo hai điều kiện; muốn gắn session_no, tiếp tục dùng SUM tích lũy như phần 6.

Khi có nhiều điều kiện như session cookie đổi, đăng nhập tài khoản khác, app restart, logout, sự kiện hệ thống, hãy viết rõ **điều kiện nào được ưu tiên**, rồi quyết định một phiên có thể bị tách ngay cả khi gap nhỏ.

## 16. Ngưỡng phiên thay đổi theo thiết bị hoặc chính sách

Không phải mọi luồng đều cần một ngưỡng 30 phút. Ví dụ giả định:

- Thiết bị mobile: 20 phút không hoạt động thì phiên kết thúc.
- Thiết bị web: 30 phút.

Có thể tính ngưỡng cho từng sự kiện:

~~~sql
WITH
    ordered AS (
        SELECT
            e.*,
            LAG(event_at) OVER (
                PARTITION BY user_id, device_id
                ORDER BY event_at, event_id
            ) AS previous_at
        FROM session_demo_events AS e
    ),
    policy_events AS (
        SELECT
            *,
            CASE
                WHEN device_id = 'mobile' THEN INTERVAL '20 minutes'
                ELSE INTERVAL '30 minutes'
            END AS idle_threshold
        FROM ordered
    )
SELECT
    event_id,
    user_id,
    device_id,
    event_at,
    idle_threshold,
    CASE
        WHEN previous_at IS NULL THEN 1
        WHEN event_at > previous_at + idle_threshold THEN 1
        ELSE 0
    END AS starts_new
FROM policy_events
ORDER BY user_id, device_id, event_at, event_id;
~~~

**Đây là quy tắc giả định mới**, không phải cùng định nghĩa với bộ kết quả 12 phiên ở phần trước: vì mobile dùng 20 phút, số phiên sẽ tăng ở những khoảng 30 phút trước đây chưa tách.

Với hệ thống thực, có thể lưu **session_policy_id** hoặc bảng cấu hình ngưỡng để thay CASE cố định. Tuy nhiên, một chính sách thay đổi theo thời gian cần được gắn với **phiên bản hiệu lực**: nếu áp ngưỡng hiện tại lên mọi sự kiện quá khứ, các phiên lịch sử có thể bị chia lại.

## 17. Phân phiên và tính chỉ tiêu theo phiên

Sau khi có CTE **sessions**, ta có thể tính nhiều chỉ tiêu ở cấp phiên:

| Chỉ tiêu | Công thức từ bảng sessions | Ý nghĩa |
| --- | --- | --- |
| Tổng số phiên | COUNT(*) | Mỗi hàng là một phiên |
| Tổng sự kiện | SUM(events_in_session) | Số event đã được gắn phiên |
| Số phiên có mua hàng | COUNT(*) FILTER (WHERE purchase_events > 0) | Đếm phiên có ít nhất một purchase |
| Trung bình sự kiện/phiên | AVG(events_in_session) | Mức hoạt động đo bằng số sự kiện |
| Tỷ lệ phiên có purchase | Số phiên có purchase / tổng phiên | Chỉ tiêu chuyển đổi ở cấp phiên |
| Thời lượng quan sát TB | AVG(session_end - session_start) | Khoảng đầu–cuối, không phải thời gian nhìn màn hình |
| Số người dùng hoạt động | COUNT(DISTINCT user_id) | Số định danh user có sự kiện |

### 17.1. Tỷ lệ phiên có purchase

Giả sử đã có CTE sessions của phần 8, có thể dùng SELECT:

~~~sql
SELECT
    COUNT(*) AS total_sessions,
    COUNT(*) FILTER (WHERE purchase_events > 0)
        AS purchased_sessions,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE purchase_events > 0)
        / NULLIF(COUNT(*), 0),
        2
    ) AS session_purchase_rate_pct
FROM sessions;
~~~

Với 12 phiên và 2 phiên có purchase, tỷ lệ là khoảng **16,67%**.

**NULLIF(COUNT(*), 0)** tránh phép chia cho 0 trong trường hợp không có phiên nào. Với COUNT(*) = 0, phép chia cho NULL trả NULL, thể hiện rằng không có mẫu để tính tỷ lệ.

### 17.2. Session count khác event count và user count

Trong dữ liệu:

- Có **23 sự kiện**.
- Có **12 phiên** theo khóa (user_id, device_id).
- Có **4 user_id** khác nhau.
- Có **5 cặp (user_id, device_id)**.

Một người có thể có nhiều thiết bị và nhiều phiên. Vì vậy **COUNT(DISTINCT user_id)** không phải số phiên, và **COUNT(*) trên bảng sự kiện** không phải số phiên.

## 18. Kết quả phiên là các “dải” liên tục, không phải session_id bất biến

Trong dữ liệu thực tế có thể cần lưu session_id để nối sang bảng conversion, error hoặc order. Tuy nhiên, số thứ tự tích lũy **session_no** phụ thuộc:

- Tập sự kiện hiện có.
- Khóa chủ thể.
- Cách sắp thứ tự event_at/event_id.
- Ngưỡng thời gian.
- Điều kiện đặc biệt như logout hoặc đổi tài khoản.
- Quy tắc khử trùng lặp và xử lý late events.

Ví dụ thêm sự kiện 09:30 của 101/web đã **gộp hai phiên trước thành một**. Nếu bảng downstream đã tham chiếu chuỗi **101/web/2**, mã này có thể không còn đại diện cho cùng một phiên sau khi tính lại.

### 18.1. Tạo nhãn phiên cho báo cáo tạm thời

Trong PostgreSQL, từ kết quả event đã có session_no:

~~~sql
SELECT
    user_id,
    device_id,
    session_no,
    CONCAT_WS('/', user_id::TEXT, device_id, session_no::TEXT)
        AS session_label
FROM sessions
ORDER BY user_id, device_id, session_no;
~~~

Đoạn SELECT này cần chạy khi đã có một CTE **sessions** chứa ba khóa tương ứng. Các nhãn như **101/mobile/1**, **101/mobile/2** thuận tiện để **hiển thị hoặc gỡ lỗi**, nhưng không nên coi chúng là định danh vĩnh viễn nếu dữ liệu có thể bị nạp lại hoặc quy tắc phiên thay đổi.

Đối với hệ thống có yêu cầu lưu session_id lâu dài, nên có **cơ chế gán khóa bền vững được quản lý rõ** và chính sách xử lý việc gộp/tách phiên khi dữ liệu bổ sung đến.

### 18.2. Không dùng MIN(event_id) làm sự kiện đầu tiên khi ID không theo thời gian

Trong dữ liệu người 303/web, event_id **17** xảy ra lúc 20:00, trước event_id **16** lúc 20:05. Nếu muốn xác định **event_id của sự kiện mở phiên**, dùng thứ tự **event_at, event_id**, không mặc định **MIN(event_id)** là hàng đầu tiên.

Có thể dùng một CTE lấy ROW_NUMBER theo từng phiên sau khi đã gắn session_no:

~~~sql
-- Chạy sau khi đã định nghĩa events_with_session.
WITH session_event_order AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, device_id, session_no
            ORDER BY event_at, event_id
        ) AS event_order_in_session
    FROM events_with_session
)
SELECT
    user_id,
    device_id,
    session_no,
    event_id AS first_event_id
FROM session_event_order
WHERE event_order_in_session = 1;
~~~

Trong ví dụ, **events_with_session** là tên CTE từ phần 8; đoạn này minh họa **bước bổ sung** vào cùng danh sách WITH, không thể chạy độc lập nếu chưa định nghĩa nguồn.

## 19. Hiệu năng với hàng triệu sự kiện

Mẫu LAG + SUM cửa sổ thường yêu cầu xử lý các luồng theo **thứ tự sự kiện**. Với bảng lớn, chi phí có thể gồm:

- Đọc các sự kiện thuộc khoảng/đối tượng cần phân tích.
- Sắp xếp theo **(user_id, device_id, event_at, event_id)**.
- Tính LAG và SUM với phân vùng cửa sổ.
- Nhóm lại theo session_no để tạo báo cáo.
- Ghi hoặc truyền lượng kết quả lớn nếu xuất từng sự kiện đã gắn phiên.

### 19.1. Chỉ mục phù hợp với thứ tự cửa sổ

Trong PostgreSQL, chỉ mục B-tree có thể hữu ích:

~~~sql
CREATE INDEX idx_session_demo_actor_time
ON session_demo_events (
    user_id,
    device_id,
    event_at,
    event_id
);
~~~

Thứ tự khóa chỉ mục tương ứng các cột **PARTITION BY** và **ORDER BY** của cửa sổ. Tuy nhiên, PostgreSQL **không được bảo đảm sẽ luôn dùng chỉ mục**: với bảng vài chục hàng, quét tuần tự và sắp xếp có thể rẻ hơn; trên bảng lớn, các điều kiện lọc và thống kê ảnh hưởng lựa chọn kế hoạch.

### 19.2. Lọc đúng trước và sau sessionization

**Lọc trước** theo một actor được yêu cầu thường an toàn, vì các actor khác không tham gia tính khoảng cách của actor đó:

~~~sql
WHERE user_id = 101
  AND device_id = 'mobile'
~~~

Nhưng **lọc trước theo ngày bắt đầu hoặc loại sự kiện** có thể cắt mất sự kiện làm cầu nối giữa các khoảng, tạo phiên giả. Vì vậy, câu hỏi không chỉ là “lọc sớm có nhanh không?” mà là **“bộ lọc có làm thay đổi luồng cần phân phiên theo định nghĩa không?”**

Nếu một kỳ báo cáo lớn cần phiên theo tháng, có thể duy trì **bảng phiên đã chuẩn hóa** hoặc cơ chế tính tăng dần, thay vì tính lại toàn bộ lịch sử ở mỗi truy vấn.

### 19.3. EXPLAIN

~~~sql
EXPLAIN
SELECT
    event_id,
    user_id,
    device_id,
    event_at,
    LAG(event_at) OVER (
        PARTITION BY user_id, device_id
        ORDER BY event_at, event_id
    ) AS previous_at
FROM session_demo_events;
~~~

Kế hoạch PostgreSQL có thể có **WindowAgg**, **Sort**, **Index Scan** hoặc **Seq Scan** tùy dữ liệu/chỉ mục. Dùng **EXPLAIN (ANALYZE, BUFFERS)** khi thực sự cần đo đạc và có thể chấp nhận chi phí chạy truy vấn.

Không có quy tắc “LAG luôn nhanh hơn truy vấn con” hay “CTE luôn chậm”. Mục tiêu đầu tiên là tính đúng ranh giới phiên; hiệu năng được đánh giá trên dữ liệu và hệ quản trị thật.

### 19.4. Khi dữ liệu cực lớn

Đối với sự kiện nhiều tỷ hàng, bài toán thường được triển khai bằng **ETL theo lô**, **stream processing** với watermark và state, hoặc bảng tổng hợp session. SQL cửa sổ vẫn có thể là công cụ chính để tính hoặc đối soát, nhưng cần quản lý:

- Phân vùng dữ liệu và phân phối theo user/device.
- Độ trễ của log và sự kiện đến muộn.
- Kích thước tập phải sắp xếp.
- Độ ổn định của session_id qua các lần nạp.
- Giới hạn bộ nhớ, tài nguyên tạm và thời gian chạy.

Không nên mặc định một truy vấn tính từ đầu trên toàn bộ lịch sử là lựa chọn phù hợp cho báo cáo cần phản hồi tức thời.

## 20. Khác biệt theo phương ngữ SQL

Mẫu **LAG → CASE → SUM cửa sổ → GROUP BY** tương đối di động giữa các RDBMS có window functions. Điểm khác biệt thường nằm ở **kiểu timestamp, phép cộng/trừ thời gian, cú pháp khoảng thời gian và hàm tổng hợp điều kiện**.

| Chủ đề | PostgreSQL 15+ | MySQL 8.0 | SQL Server | SQLite hiện đại | Oracle Database |
| --- | --- | --- | --- | --- | --- |
| LAG | Có | Có | Có | Có từ hỗ trợ window functions | Có |
| SUM(...) OVER | Có | Có | Có | Có | Có |
| CTE WITH | Có | Có | Có | Có | Có |
| Khoảng thời gian 30 phút | INTERVAL '30 minutes' | INTERVAL 30 MINUTE với DATE_ADD | DATEADD(MINUTE, 30, ...) | Hàm datetime/julianday/strftime | INTERVAL '30' MINUTE |
| Timestamp có múi giờ | TIMESTAMPTZ | Cơ chế TIMESTAMP/DATETIME và time zone riêng | DATETIMEOFFSET hoặc kiểu thời gian phù hợp | Thường lưu TEXT/REAL/INTEGER và chuẩn hóa thời gian | TIMESTAMP WITH TIME ZONE |
| Đếm có FILTER | COUNT(*) FILTER (WHERE ...) | Thường dùng SUM(CASE ...) | Thường dùng SUM(CASE ...) | Có FILTER ở các phiên bản hỗ trợ | Cân nhắc CASE theo phiên bản |

### 20.1. PostgreSQL

So sánh thời gian có thể viết:

~~~sql
event_at - previous_at > INTERVAL '30 minutes'
~~~

hoặc:

~~~sql
event_at > previous_at + INTERVAL '30 minutes'
~~~

Nên dùng **TIMESTAMPTZ** khi dữ liệu là thời điểm thực đến từ nhiều múi giờ, đồng thời có quy tắc rõ ràng khi chuyển đổi sang ngày địa phương của báo cáo.

### 20.2. MySQL 8.0

MySQL hỗ trợ LAG, SUM cửa sổ và CTE. Điều kiện tạo phiên mới có thể viết:

~~~sql
CASE
    WHEN previous_at IS NULL THEN 1
    WHEN event_at > DATE_ADD(previous_at, INTERVAL 30 MINUTE)
        THEN 1
    ELSE 0
END
~~~

Lưu ý: một cách viết như **TIMESTAMPDIFF(MINUTE, previous_at, event_at) > 30** có thể gây nhầm ở ranh giới có **giây hoặc phần lẻ giây**, do hàm trả số đơn vị phút nguyên theo quy tắc của hệ. So sánh **event_at > previous_at + 30 phút** thể hiện trực tiếp hơn yêu cầu “vượt quá đúng 30 phút”.

MySQL không dùng nguyên văn cú pháp PostgreSQL **INTERVAL '30 minutes'** hay **COUNT(*) FILTER (WHERE ...)**. Đếm purchase theo phiên có thể dùng:

~~~sql
SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END)
~~~

### 20.3. SQL Server

Trên SQL Server, có thể dùng:

~~~sql
CASE
    WHEN previous_at IS NULL THEN 1
    WHEN event_at > DATEADD(MINUTE, 30, previous_at) THEN 1
    ELSE 0
END
~~~

SQL Server có **LAG** và window aggregate SUM. CTE được khai báo bằng **WITH** (hoặc **;WITH** khi cần kết thúc một câu lệnh trước). Tránh dùng **DATEDIFF(MINUTE, previous_at, event_at) > 30** như một cách thay thế vô điều kiện cho khoảng cách thực lớn hơn 30 phút: **DATEDIFF đếm số ranh giới đơn vị thời gian đã vượt qua**, không phải luôn là số phút đã trôi qua chính xác theo phần giây.

Để lưu một thời điểm tuyệt đối có offset, cân nhắc **DATETIMEOFFSET** hoặc quy ước UTC rõ ràng. Dùng DATETIME/DATETIME2 cần có chính sách múi giờ phù hợp với dữ liệu đầu vào.

### 20.4. SQLite

SQLite hỗ trợ window functions từ **3.25.0**. SQLite không có một kiểu TIMESTAMPTZ tương tự PostgreSQL; thời gian thường được lưu bằng chuỗi ISO-8601, số Julian day hoặc Unix epoch.

Nếu sự kiện được chuẩn hóa thành chuỗi UTC có thể xử lý bằng datetime(), một điều kiện khái niệm là:

~~~sql
CASE
    WHEN previous_at IS NULL THEN 1
    WHEN datetime(event_at) > datetime(previous_at, '+30 minutes')
        THEN 1
    ELSE 0
END
~~~

**datetime() mặc định có độ chính xác thường tới giây** với định dạng trả về thông dụng; nếu hệ thống lưu mili-giây, cần bảo toàn độ chính xác phù hợp và không vô tình làm tròn ranh giới phiên. Hàm **julianday()** có thể so sánh chênh lệch ngày, nhưng dùng số thực cần thận trọng quanh thời điểm đúng ngưỡng.

Để sessionize đáng tin, hãy chuẩn hóa định dạng và múi giờ timestamp trước khi tính LAG, thay vì so sánh trực tiếp các chuỗi ngày ở nhiều định dạng khác nhau.

### 20.5. Oracle Database

Với kiểu timestamp tương thích, có thể biểu diễn ngưỡng bằng:

~~~sql
event_at > previous_at + INTERVAL '30' MINUTE
~~~

Oracle hỗ trợ các hàm phân tích như **LAG** và SUM OVER, nhưng quy tắc về kiểu timestamp, xử lý múi giờ và tên/cú pháp một số hàm khác PostgreSQL. Khi chuyển truy vấn, kiểm tra độ chính xác của thời điểm và các điều kiện ranh giới trong đúng phiên bản đang chạy.

### Khác biệt lớn nhất không phải tên hàm

Ngay cả khi hai hệ đều hỗ trợ LAG, kết quả vẫn có thể lệch nếu:

- Một hệ lưu timestamp theo UTC, hệ kia theo giờ địa phương.
- Một hệ mất mili-giây khi chuyển kiểu.
- ORDER BY thiếu khóa phá hòa cho sự kiện đồng thời.
- So sánh “30 phút” được triển khai bằng phép cắt về phút nguyên.
- Quy tắc **>** bị vô tình đổi thành **>=**.
- Kỳ báo cáo được lọc trước khi sessionize ở một hệ, sau khi sessionize ở hệ còn lại.

Vì vậy, hãy kiểm tra **ngữ nghĩa phiên** và **bộ dữ liệu ranh giới**, không chỉ kiểm tra câu SQL có chạy được hay không.

## 21. Lỗi thường gặp

| Hiện tượng hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Sự kiện đúng 30 phút bị tách sai | Dùng >= khi nghiệp vụ yêu cầu > | Xác định rõ dấu so sánh và kiểm thử ranh giới |
| Tất cả sự kiện trùng timestamp có thứ tự không ổn định | ORDER BY chỉ có event_at | Thêm khóa phá hòa như event_id |
| Phân phiên sai khi event_id không theo thời gian | ORDER BY event_id | ORDER BY event_at, event_id |
| Một người có nhiều thiết bị bị trộn phiên | PARTITION BY thiếu device_id | Dùng khóa chủ thể theo định nghĩa sản phẩm |
| Người dùng ẩn danh khác nhau bị gộp | Cùng user_id NULL hoặc giá trị giả 0 | Dùng anonymous/device identity phù hợp |
| Phiên bị cắt ở nửa đêm | PARTITION BY thêm DATE(event_at) | Sessionize xuyên ngày rồi gắn ngày báo cáo |
| Lọc theo ngày làm sự kiện đầu thành phiên mới giả | Bỏ các sự kiện ngay trước khoảng lọc | Giữ đủ ngữ cảnh hoặc tính phiên trên dữ liệu lịch sử |
| Hai phiên bất ngờ gộp sau backfill | Sự kiện đến muộn lấp một gap lớn | Có chiến lược tính lại phiên/watermark |
| Nhãn session_no không bền vững | Session_no thay đổi khi thêm sự kiện trước đó | Không dùng làm ID lâu dài nếu không quản lý phiên bản |
| Đếm DISTINCT(session_no) toàn bảng ra số nhỏ | Mỗi actor bắt đầu lại từ phiên 1 | Đếm hàng trong bảng sessions hoặc dùng khóa ghép |
| Sự kiện view cách xa bị tách sai | Lọc bỏ click trước LAG | Chia phiên trên tập event được coi là hoạt động |
| Dùng nhóm ô thời gian 30 phút thay cho session | Time bucketing không xét khoảng giữa sự kiện kề nhau | Dùng LAG và cờ new_session |
| Phiên chỉ có một sự kiện có duration 0 | MIN(event_at) = MAX(event_at) | Gọi là thời lượng quan sát, không suy ra không tương tác |
| ROWS/RANGE cho kết quả khó hiểu | Khung cửa sổ và timestamp đồng hạng | Khai báo ROWS và khóa sắp xếp xác định |
| Chia phút bằng phép tính làm tròn | DATEDIFF/TIMESTAMPDIFF cắt độ chính xác | So sánh trực tiếp timestamp với timestamp cộng threshold |
| Số phiên tính theo thời gian nhận log thay vì event time | Sự kiện offline/retry tới muộn | Phân biệt event_at với received_at |
| Báo cáo nhiều phiên bất thường khi thử trên dữ liệu mới | Dữ liệu trùng, sai múi giờ hoặc missing events | Kiểm tra chất lượng dữ liệu nguồn trước khi phân phiên |
| Hiệu năng giảm mạnh khi bảng log lớn | Sắp xếp và cửa sổ trên nhiều hàng | Lọc actor hợp lệ, chỉ mục, tính theo lô/trạng thái khi cần |

## 22. Bài tập thực hành

Dùng bảng **session_demo_events** đã tạo ở phần 3. Mọi câu hỏi mặc định áp dụng ngưỡng **gap > 30 phút** và khóa chủ thể **(user_id, device_id)**, trừ khi đề bài thay đổi.

1. Viết LAG(event_at) để tìm previous_at của mỗi sự kiện trong từng user_id/device_id. Tại sao event_id 17 của người 303 phải đứng trước event_id 16?
2. Tạo CTE marked_events đánh dấu starts_new = 1 cho sự kiện đầu tiên của một luồng hoặc khi gap vượt 30 phút.
3. Viết SUM(starts_new) OVER với PARTITION BY, ORDER BY và khung ROWS để gán session_no cho từng event.
4. Với người 101/mobile, ghi lại session_no của tám event_id 1–8; giải thích vì sao event_id 3 không mở phiên mới.
5. Với người 202/mobile, chỉ ra những gap đúng 30 phút và những gap vượt 30 phút.
6. Đổi điều kiện thành **gap >= 30 phút**. So sánh số phiên thay đổi ở những luồng có event cách đúng 30 phút.
7. GROUP BY user_id, device_id, session_no để tính session_start, session_end, event_count và observed_duration.
8. Đếm tổng số phiên theo user_id/device_id; kiểm tra vì sao toàn bộ dữ liệu có **12 phiên và 23 sự kiện**.
9. Tính số phiên có ít nhất một purchase và tỷ lệ phiên có purchase trên tổng số phiên.
10. Tính **AVG(event_count)** của mỗi user_id/device_id và giải thích sự khác nhau giữa “số phiên”, “số sự kiện” và “số người”.
11. Thử bỏ device_id khỏi PARTITION BY đối với user_id = 101. Giải thích việc xen kẽ mobile/web ảnh hưởng gap.
12. Thử ORDER BY event_id thay vì ORDER BY event_at, event_id cho user_id = 303. Chỉ ra thứ tự thời gian bị sai.
13. Tạo một bản sao luồng 101/web trong CTE, thêm sự kiện lúc 09:30 rồi phân phiên lại. Tại sao hai phiên gốc trở thành một?
14. Chỉ xét các sự kiện của ngày 02/07 trước khi chạy LAG. Quan sát vì sao sự kiện 00:10 của người 404 bị xem là đầu phiên mới.
15. Viết báo cáo số phiên theo **ngày bắt đầu phiên UTC**, sau đó theo **ngày bắt đầu phiên ở Asia/Ho_Chi_Minh**. Có thể đổi ngày với những phiên gần nửa đêm không?
16. Dùng LAG(event_type) thêm quy tắc “sự kiện ngay sau logout phải mở phiên mới”, bất kể gap.
17. Thay ngưỡng 30 phút bằng chính sách **mobile 20 phút, web 30 phút** và phân tích tại sao số phiên của mobile thay đổi.
18. Thử tạo CTE chỉ giữ **event_type = 'view'** trước khi chạy LAG. Thảo luận vì sao điều này không còn cùng định nghĩa phiên hoạt động nếu click/scroll cũng được coi là hoạt động.
19. Tạo kết quả session_no rồi viết ROW_NUMBER theo từng phiên để tìm **event_id thực sự xảy ra đầu tiên**. Tại sao MIN(event_id) không luôn đúng?
20. Tạo chỉ mục trên (user_id, device_id, event_at, event_id); dùng EXPLAIN quan sát kế hoạch tính LAG.
21. Chuyển điều kiện ngưỡng sang MySQL bằng **DATE_ADD**, sang SQL Server bằng **DATEADD**, rồi giải thích lý do không dùng số phút đã bị làm tròn.
22. Nếu hệ thống cho phép event_at NULL ở bảng staging, đề xuất quy tắc xử lý trước sessionization: loại có kiểm soát, sửa dữ liệu hay đánh dấu lỗi? Tại sao không nên đưa NULL vào thứ tự thời gian mà không quy định?
23. Giả sử một luồng có các sự kiện 09:00, 09:25, 09:50. Theo inactivity 30 phút chúng thuộc bao nhiêu phiên? Nếu yêu cầu “phiên tối đa 30 phút tính từ lúc bắt đầu” thì kết quả có khác không?
24. Thiết kế quy tắc kiểm thử với bốn trường hợp: gap = 0, gap = 30 phút, gap = 30 phút 1 giây, và một sự kiện đến muộn lấp gap 45 phút. Cho biết starts_new mong đợi của từng trường hợp.

### Câu hỏi tự kiểm tra

**Câu 1.** Với ngưỡng “vượt quá 30 phút”, hai sự kiện cách đúng 30 phút có cùng phiên không?

**Đáp án:** **Có.** Điều kiện tách là **gap > 30 phút**, không phải >=.

**Câu 2.** Dùng PARTITION BY user_id có luôn đúng khi người dùng hoạt động đồng thời trên web và mobile?

**Đáp án:** **Không.** Nó phụ thuộc định nghĩa phiên. Nếu phiên được theo dõi riêng từng thiết bị, phải phân vùng theo **user_id, device_id**.

**Câu 3.** Có thể dùng session_no = 1 làm định danh duy nhất trên toàn bảng không?

**Đáp án:** **Không.** Mỗi luồng user_id/device_id đều bắt đầu từ phiên 1. Phải có khóa chủ thể, và session_no cũng có thể đổi sau khi nhận sự kiện đến muộn.

**Câu 4.** Lọc chỉ giữ sự kiện purchase trước LAG rồi đếm phiên mua hàng có tương đương phân phiên trên toàn bộ tương tác không?

**Đáp án:** **Không.** Các sự kiện view/click/scroll có thể nối những khoảng thời gian giữa các purchase. Lọc trước LAG làm thay đổi chính định nghĩa gap.

**Câu 5.** Một phiên có sự kiện ở 23:55 và 00:10 hôm sau có bắt buộc tách tại nửa đêm không?

**Đáp án:** **Không.** Với inactivity 30 phút, gap 15 phút nên vẫn cùng phiên. Chỉ tách theo ngày nếu đó là quy tắc nghiệp vụ riêng.

**Câu 6.** Vì sao cần ROWS trong SUM tích lũy?

**Đáp án:** Để chỉ rõ tổng được cộng **từng hàng theo thứ tự**, tránh nhầm với khung RANGE và các hàng đồng hạng timestamp. Cũng cần ORDER BY có khóa phá hòa.

**Câu 7.** Một sự kiện mới lúc 09:30 chen vào giữa 09:05 và 09:50 có thể làm giảm số phiên không?

**Đáp án:** **Có.** Gap 45 phút ban đầu bị chia thành hai gap 25 và 20 phút, khiến hai phiên được nối thành một.

**Câu 8.** Session_end − session_start có phải luôn là thời gian hoạt động thực tế của người dùng không?

**Đáp án:** **Không.** Nó là độ dài khoảng thời gian quan sát được giữa sự kiện đầu và cuối. Một phiên chỉ có một sự kiện nhận giá trị 0 dù người dùng có thể vẫn ở lại màn hình.

**Câu 9.** Dùng TIMESTAMPDIFF(MINUTE) hoặc DATEDIFF(MINUTE) có luôn diễn đạt chính xác “hơn 30 phút” tới từng giây không?

**Đáp án:** **Không.** Quy tắc cắt hoặc đếm ranh giới phút có thể làm sai ngưỡng có giây/phần giây. Nên so sánh timestamp với timestamp cộng 30 phút bằng cú pháp tương ứng.

## 23. Ghi nhớ cốt lõi

**Ghép sự kiện thành phiên theo khoảng thời gian** là một mẫu **gaps and islands**. Trình tự cơ bản:

~~~text
Sự kiện có timestamp và khóa chủ thể
                 │
                 ▼
    LAG: lấy sự kiện trước
                 │
                 ▼
   CASE: gap vượt ngưỡng?
       1 = mở phiên mới
       0 = tiếp tục phiên
                 │
                 ▼
  SUM tích lũy: tạo session_no
                 │
                 ▼
 GROUP BY actor + session_no
  → thời gian, số event, chỉ tiêu phiên
~~~

**Đúng ngữ nghĩa quan trọng hơn cú pháp ngắn.** Hãy quyết định khóa người/thiết bị, ngưỡng và dấu so sánh, cách xử lý sự kiện đồng thời, thời điểm event thực so với thời điểm nhận log, và cách gộp phiên qua nửa đêm. **LAG theo event_at, event_id** cùng **SUM ... ROWS UNBOUNDED PRECEDING** tạo cơ sở để đánh số phiên có thứ tự xác định trên tập dữ liệu hiện tại.

Cuối cùng, kết quả phân phiên có thể **thay đổi khi sự kiện đến muộn**. Session_no là nhãn dẫn xuất, không tự trở thành session_id bền vững. Khi triển khai trên dữ liệu lớn, cần thiết kế chính sách backfill, xử lý múi giờ, deduplication, chỉ mục và cách tính theo lô hoặc tăng dần, đồng thời phân biệt rõ **sessionization theo bất hoạt** với **chia thời gian thành ô cố định**.
