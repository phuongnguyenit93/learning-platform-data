# Đếm tích lũy số đối tượng duy nhất theo thời gian

Một hệ thống có thể ghi nhiều sự kiện từ cùng một người dùng: xem trang, đăng ký, mua hàng, mở ứng dụng, quay lại trong ngày hôm sau. Khi làm báo cáo, hai chỉ số rất dễ bị nhầm lẫn:

- **Số đối tượng duy nhất trong ngày** (*daily distinct*, ví dụ DAU): ngày đó có bao nhiêu `user_id` khác nhau hoạt động?
- **Số đối tượng duy nhất tích lũy đến ngày đó** (*cumulative distinct*, *ever-seen unique*): kể từ mốc bắt đầu đo lường đến hết ngày đó, hệ thống đã từng thấy bao nhiêu `user_id` khác nhau?

Người dùng hoạt động cả ngày thứ Hai và thứ Ba được tính **một lần ở mỗi ngày** khi tính DAU, nhưng **chỉ một lần trong toàn bộ số tích lũy**. Do đó, **không thể lấy `SUM(số người dùng duy nhất theo ngày)` làm số người dùng duy nhất tích lũy**. Phép cộng ấy đếm lại những người quay trở lại.

Trong SQL, một mẫu truy vấn chính xác, dễ hiểu và có tính di động là:

1. Xác định **định danh đối tượng** cần đếm và quy tắc một sự kiện được tính.
2. Tìm **ngày xuất hiện đầu tiên** của từng đối tượng (`MIN(event_day)` sau `GROUP BY user_id`).
3. Đếm **số đối tượng mới lần đầu xuất hiện theo ngày**.
4. Tạo dãy ngày đầy đủ nếu báo cáo cần cả ngày không có sự kiện.
5. Dùng `SUM(new_users) OVER (ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` để cộng dồn số đối tượng **mới**.

Mỗi người chỉ đóng góp đúng **một đơn vị tại ngày đầu tiên**, nên các lần hoạt động sau không làm số tích lũy tăng thêm. Mẫu còn dùng được cho khách mua lần đầu, thiết bị duy nhất đã xuất hiện, mã hồ sơ từng được xử lý và nhiều loại **đối tượng duy nhất** khác, miễn là định danh được xác lập rõ.

Bài thuộc chương **Mẫu truy vấn** của **Database SQL**. Các ví dụ chính dùng **PostgreSQL**, với dữ liệu tạm tự tạo và ngày nghiệp vụ theo `Asia/Ho_Chi_Minh`. Phần cuối so sánh kỹ thuật theo SQL Server, MySQL 8+, BigQuery và các DBMS khác. Các đoạn được ghi nhãn riêng khi phụ thuộc phương ngữ.

## 1. Xác định chính xác chỉ số cần đo

Giả sử ứng dụng có lịch sử sự kiện:

```text
Ngày 1: user A, user B
Ngày 2: user A, user C
Ngày 3: user B, user D
```

| Ngày | Đối tượng xuất hiện trong ngày | Distinct trong ngày | Distinct mới lần đầu | Distinct tích lũy |
| --- | --- | ---: | ---: | ---: |
| 1 | A, B | 2 | 2 | 2 |
| 2 | A, C | 2 | 1 | 3 |
| 3 | B, D | 2 | 1 | 4 |

**Tổng distinct theo ngày** là `2 + 2 + 2 = 6`, nhưng tập đối tượng từng xuất hiện chỉ là `{A, B, C, D}`, có **4** đối tượng.

Ký hiệu:

- \(U_d\): tập định danh xuất hiện trong ngày \(d\).
- \(A_d\): tập định danh đã xuất hiện **ít nhất một lần** từ đầu giai đoạn đến hết ngày \(d\).
- \(N_d\): tập định danh có **lần xuất hiện đầu tiên** vào ngày \(d\).

Ta có:

\[
A_d = \bigcup_{t \le d} U_t
\]

và:

\[
N_d = U_d \setminus \bigcup_{t < d} U_t
\]

Do các tập \(N_d\) **không giao nhau**, số distinct tích lũy đúng bằng:

\[
|A_d| = \sum_{t \le d} |N_t|
\]

Từ đây rút ra nguyên tắc SQL quan trọng: **phải biến sự kiện lặp thành đúng một lần xuất hiện đầu tiên trên mỗi định danh trước khi dùng SUM lũy kế**.

### 1.1. “Tích lũy duy nhất” khác “đang hoạt động”

Số người **đã từng xuất hiện** thông thường **không giảm** theo ngày, miễn là cùng một tập lịch sử và định nghĩa chỉ số không đổi. Người không hoạt động hôm nay vẫn nằm trong tập đã từng thấy.

Ngược lại:

- **DAU**: số người hoạt động trong từng ngày, có thể tăng hoặc giảm.
- **MAU**: số người duy nhất hoạt động trong một tháng, không phải tổng DAU.
- **Rolling 7-day active**: số người có ít nhất một sự kiện trong **bảy ngày gần nhất**, có thể giảm khi người cũ rơi ra ngoài cửa sổ.
- **Cumulative unique**: số người đã từng xuất hiện kể từ **mốc bắt đầu tích lũy** đến thời điểm đang xét.

Trước khi viết SQL, cần thống nhất **đang đo đại lượng nào**; các từ “người dùng lũy kế”, “người dùng mới”, “người dùng hoạt động” không thay thế cho nhau.

## 2. Định danh đối tượng và grain của dữ liệu nguồn

Giả sử bảng sự kiện có:

```text
event_id | actor_id | occurred_at | event_type | channel
```

Mỗi hàng là **một sự kiện**, không phải một người. Một người có thể tạo nhiều hàng:

```text
user u01:
  01/10: VIEW
  02/10: PURCHASE
  06/10: SIGNUP
```

Nếu mục tiêu là đếm **người duy nhất**, `event_id` không phải khóa đếm; `actor_id` mới là khóa khái niệm. Nếu mục tiêu là **thiết bị duy nhất**, cần một `device_id` được định nghĩa phù hợp, không tự thay bằng user_id.

| Loại định danh | Câu hỏi cần làm rõ |
| --- | --- |
| `user_id` | Một tài khoản có tương ứng một người thực không? Có tài khoản khách/ẩn danh không? |
| `customer_id` | Có một khách lưu ở nhiều hệ thống với các ID khác nhau không? |
| `device_id` | Thay thiết bị hoặc xóa cookie có tạo ID mới không? |
| `order_id` | ID có duy nhất toàn hệ thống hay chỉ duy nhất trong từng nguồn/tenant? |
| `email` | Có chuẩn hóa chữ hoa, khoảng trắng, email đổi hoặc người dùng chia sẻ email không? |

**COUNT DISTINCT chỉ chính xác theo khóa và quy tắc đầu vào đã chọn.** Nó không tự suy ra hai thiết bị thuộc cùng một người hay hai mã khác nhau thực chất là một khách.

### 2.1. NULL và chuỗi rỗng

Trong SQL, `COUNT(DISTINCT actor_id)` bỏ qua **NULL**. Nếu hệ thống ghi sự kiện ẩn danh với actor_id NULL, các sự kiện đó **không được tính là một người duy nhất**. Đây thường là chính sách hợp lý vì NULL không định danh một đối tượng cụ thể.

Nhưng chuỗi rỗng `''` và chuỗi toàn khoảng trắng có thể là giá trị **khác NULL**, và có thể bị đếm như một định danh. Tùy hợp đồng dữ liệu, nên chuẩn hóa ở bước nguồn, ví dụ PostgreSQL:

```sql
NULLIF(BTRIM(actor_id), '')
```

Điều này chuyển giá trị rỗng sau khi cắt khoảng trắng thành NULL. **Không tự chuẩn hóa** bằng cách viết thường, loại ký tự hoặc gộp nhiều định danh nếu nghiệp vụ chưa xác nhận quy tắc; thay đổi khóa có thể thay đổi toàn bộ số distinct lịch sử.

## 3. Bộ dữ liệu PostgreSQL có lặp người và ngày rỗng

Tạo bảng tạm trong một phiên PostgreSQL:

```sql
CREATE TEMP TABLE demo_unique_events (
    event_id INTEGER PRIMARY KEY,
    actor_id TEXT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    channel TEXT NOT NULL
);

INSERT INTO demo_unique_events
    (event_id, actor_id, occurred_at, event_type, channel)
VALUES
    ( 1, 'u01', TIMESTAMPTZ '2026-10-01 00:30:00+07', 'VIEW',     'WEB'),
    ( 2, 'u02', TIMESTAMPTZ '2026-10-01 10:00:00+07', 'SIGNUP',   'WEB'),
    ( 3, 'u01', TIMESTAMPTZ '2026-10-02 09:00:00+07', 'PURCHASE', 'STORE'),
    ( 4, 'u03', TIMESTAMPTZ '2026-10-02 11:00:00+07', 'VIEW',     'WEB'),
    ( 5, 'u02', TIMESTAMPTZ '2026-10-04 08:00:00+07', 'VIEW',     'APP'),
    ( 6, 'u04', TIMESTAMPTZ '2026-10-04 12:00:00+07', 'SIGNUP',   'APP'),
    ( 7, 'u03', TIMESTAMPTZ '2026-10-04 15:00:00+07', 'SIGNUP',   'WEB'),
    ( 8, 'u05', TIMESTAMPTZ '2026-10-06 09:00:00+07', 'VIEW',     'STORE'),
    ( 9, NULL,  TIMESTAMPTZ '2026-10-06 10:00:00+07', 'VIEW',     'WEB'),
    (10, 'u01', TIMESTAMPTZ '2026-10-06 11:00:00+07', 'SIGNUP',   'APP'),
    (11, 'u06', TIMESTAMPTZ '2026-10-07 20:00:00+07', 'PURCHASE', 'APP'),
    (12, 'u07', TIMESTAMPTZ '2026-10-08 10:00:00+07', 'VIEW',     'WEB'),
    (13, 'u04', TIMESTAMPTZ '2026-10-08 12:00:00+07', 'PURCHASE', 'STORE'),
    (14, 'u07', TIMESTAMPTZ '2026-10-08 14:00:00+07', 'VIEW',     'APP'),
    (15, 'u06', TIMESTAMPTZ '2026-10-08 15:00:00+07', 'SIGNUP',   'STORE'),
    (16, 'u08', TIMESTAMPTZ '2026-10-09 01:00:00+07', 'VIEW',     'WEB');
```

Có **16 sự kiện**, trong đó một sự kiện có actor_id NULL. Các định danh xác định là **u01 đến u08**, tổng **8 đối tượng duy nhất**. Những ngày **03/10** và **05/10** không có sự kiện; chúng giúp kiểm tra việc báo cáo có hiển thị những ngày có số mới bằng 0 hay không.

### 3.1. Bảng ngày và đối tượng xuất hiện

| Ngày tại Việt Nam | Đối tượng có hoạt động (không tính NULL) | Số distinct trong ngày | Đối tượng mới lần đầu |
| --- | --- | ---: | --- |
| 2026-10-01 | u01, u02 | 2 | u01, u02 |
| 2026-10-02 | u01, u03 | 2 | u03 |
| 2026-10-03 | — | 0 | — |
| 2026-10-04 | u02, u03, u04 | 3 | u04 |
| 2026-10-05 | — | 0 | — |
| 2026-10-06 | u05, u01 | 2 | u05 |
| 2026-10-07 | u06 | 1 | u06 |
| 2026-10-08 | u07, u04, u06 | 3 | u07 |
| 2026-10-09 | u08 | 1 | u08 |

Ngày 06/10 còn có một sự kiện với actor_id **NULL**; sự kiện đó không thêm một định danh duy nhất mới.

Tổng distinct theo ngày là **14 lượt người-ngày** (`2+2+3+2+1+3+1`), trong khi tổng người khác nhau trong cả kỳ là **8**. Hai con số cùng đúng nhưng trả lời **hai câu hỏi khác nhau**.

## 4. Chuyển timestamp thành ngày theo múi giờ báo cáo

Dữ liệu sự kiện lưu dưới dạng `TIMESTAMPTZ`: nó biểu diễn một **mốc thời gian**, nhưng báo cáo theo **ngày địa phương** cần xác định múi giờ. Trong PostgreSQL:

```sql
SELECT
    event_id,
    actor_id,
    occurred_at,
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE AS event_day
FROM demo_unique_events
ORDER BY occurred_at, event_id;
```

`AT TIME ZONE 'Asia/Ho_Chi_Minh'` chuyển mốc thời gian thành giờ trên đồng hồ Việt Nam, sau đó `::DATE` lấy ngày. Cách này không phụ thuộc vào timezone mặc định của session khi xác định `event_day`.

**Đặc biệt:** event 1 xảy ra lúc **00:30 ngày 01/10 ở Việt Nam**, tương ứng **17:30 ngày 30/09 UTC**. Nếu lấy `occurred_at::DATE` theo một session đặt timezone UTC, event đó có thể bị đưa vào **30/09**, làm thay đổi ngày first-seen của u01 và số tích lũy ở ranh giới kỳ.

### 4.1. Định nghĩa ngày phải nhất quán trong toàn truy vấn

Không nên dùng ngày Việt Nam ở bước GROUP BY nhưng dùng ngày UTC ở bước lọc hoặc tạo calendar. Điều kiện thời gian cho ngày địa phương 01/10 có thể dùng khoảng **nửa mở**:

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-02 00:00:00+07'
```

Cách viết này chọn các mốc thuộc ngày lịch 01/10 theo offset +07 và không phải đoán phần giây cuối ngày. Với vùng có DST, cần tính ranh giới theo múi giờ nghiệp vụ chứ không mặc định luôn cộng đúng 24 giờ UTC.

### 4.2. Event time khác thời gian dữ liệu được nhận

`occurred_at` là **thời điểm sự kiện thật sự diễn ra**, trong khi một hệ thống streaming thường có thêm `ingested_at` là thời điểm pipeline ghi nhận. Một sự kiện ngày 01/10 có thể tới kho dữ liệu ngày 05/10. Nếu KPI là số người từng xuất hiện **theo ngày xảy ra sự kiện**, phải dựa trên `occurred_at`, đồng thời có chính sách xử lý dữ liệu tới trễ.

Nếu dùng `ingested_at` thay thế, đó là một **chỉ số khác**: số người được hệ thống nhận biết lần đầu theo ngày nhận dữ liệu. Không nên trộn hai khái niệm trong một chuỗi thời gian mà không ghi rõ.

## 5. Bước cơ bản: tìm ngày xuất hiện đầu tiên của mỗi đối tượng

Với mỗi actor, cần giữ **một ngày đầu tiên duy nhất**. PostgreSQL:

```sql
WITH normalized_events AS (
    SELECT
        actor_id,
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS event_day
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
),
first_seen AS (
    SELECT
        actor_id,
        MIN(event_day) AS first_day
    FROM normalized_events
    GROUP BY actor_id
)
SELECT actor_id, first_day
FROM first_seen
ORDER BY first_day, actor_id;
```

Kết quả:

| actor_id | first_day |
| --- | --- |
| u01 | 2026-10-01 |
| u02 | 2026-10-01 |
| u03 | 2026-10-02 |
| u04 | 2026-10-04 |
| u05 | 2026-10-06 |
| u06 | 2026-10-07 |
| u07 | 2026-10-08 |
| u08 | 2026-10-09 |

Cấu trúc `GROUP BY actor_id` bảo đảm một hàng cho mỗi ID xác định. `MIN(event_day)` chọn ngày có ít nhất một sự kiện sớm nhất theo quy ước timezone.

### 5.1. Vì sao không lấy MIN trên mỗi ngày?

Nếu nhóm theo:

```sql
GROUP BY event_day, actor_id
```

một người quay lại ngày sau sẽ tạo **một hàng khác**. Muốn một **ngày duy nhất cho cả lịch sử của actor**, GROUP BY chỉ theo khóa định danh (và những khóa phạm vi thực sự xác định một đối tượng khác như tenant) rồi MIN ngày.

### 5.2. Thay ngày bằng thời điểm đầu tiên khi cần thêm thuộc tính

Nếu chỉ cần ngày first-seen, `MIN(event_day)` là cách đơn giản. Nếu cần biết **sự kiện đầu tiên thuộc channel nào**, hoặc muốn chọn `event_type` của bản ghi đầu, cần xác định **một hàng sự kiện đầu tiên**, ví dụ bằng `ROW_NUMBER()` và khóa phụ khi timestamp trùng. Chỉ lấy `MIN(occurred_at)` rồi chọn tùy tiện channel từ một bản ghi khác có thể dẫn tới thông tin không nhất quán.

## 6. Đếm đối tượng mới lần đầu theo ngày

Sau khi mỗi actor chỉ còn một hàng trong `first_seen`, ta có thể đếm **số đối tượng mới**:

```sql
WITH first_seen AS (
    SELECT
        actor_id,
        MIN(
            (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        ) AS first_day
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
    GROUP BY actor_id
)
SELECT
    first_day,
    COUNT(*) AS new_actors
FROM first_seen
GROUP BY first_day
ORDER BY first_day;
```

Kết quả:

| first_day | new_actors |
| --- | ---: |
| 2026-10-01 | 2 |
| 2026-10-02 | 1 |
| 2026-10-04 | 1 |
| 2026-10-06 | 1 |
| 2026-10-07 | 1 |
| 2026-10-08 | 1 |
| 2026-10-09 | 1 |

Không có hàng cho ngày 03/10 và 05/10, vì **không có actor nào xuất hiện lần đầu** ở hai ngày đó. Mỗi actor đóng góp chính xác **một lần** vào một ngày, nên tổng `new_actors` trên toàn kỳ bằng 8.

**Quan trọng:** `new_actors` ở đây là *newly observed actors* — đối tượng **lần đầu có sự kiện trong nguồn đang xét**. Nó không nhất thiết là **người vừa đăng ký tài khoản**. Một người có VIEW từ lâu nhưng đến hôm nay mới SIGNUP là “mới đăng ký hôm nay”, nhưng **không mới xuất hiện** trong dữ liệu sự kiện.

## 7. Dùng SUM OVER để tính số duy nhất tích lũy

Bây giờ phép cộng theo ngày là **đúng**, vì ta không cộng DAU, mà cộng **đối tượng lần đầu xuất hiện**:

```sql
WITH first_seen AS (
    SELECT
        actor_id,
        MIN(
            (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        ) AS first_day
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
    GROUP BY actor_id
),
new_by_day AS (
    SELECT
        first_day,
        COUNT(*) AS new_actors
    FROM first_seen
    GROUP BY first_day
)
SELECT
    first_day,
    new_actors,
    SUM(new_actors) OVER (
        ORDER BY first_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_unique_actors
FROM new_by_day
ORDER BY first_day;
```

Kết quả:

| first_day | new_actors | cumulative_unique_actors |
| --- | ---: | ---: |
| 2026-10-01 | 2 | 2 |
| 2026-10-02 | 1 | 3 |
| 2026-10-04 | 1 | 4 |
| 2026-10-06 | 1 | 5 |
| 2026-10-07 | 1 | 6 |
| 2026-10-08 | 1 | 7 |
| 2026-10-09 | 1 | 8 |

`SUM(new_actors) OVER (...)` là phép **cộng dồn số đối tượng mới**, không phải đếm distinct trực tiếp trên mỗi frame sự kiện. Window không làm mất hàng ngày: mỗi dòng `new_by_day` vẫn được giữ, với thêm một cột lũy kế.

### 7.1. Vì sao chỉ rõ ROWS?

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

nghĩa là cộng từ hàng ngày đầu tiên tới hàng ngày hiện tại theo thứ tự `first_day`. Với `new_by_day`, mỗi `first_day` có đúng **một hàng**, nên không có vấn đề hàng đồng ngày.

Nếu dữ liệu đầu vào cửa sổ chưa được GROUP BY và còn nhiều hàng cùng ngày, frame mặc định kiểu RANGE có thể cộng cùng lúc các hàng đồng ngày; còn ROWS không có khóa phụ duy nhất có thể cho lũy kế **khác nhau trên từng sự kiện trong cùng ngày**. Cách dễ hiểu nhất cho một biểu đồ **một điểm mỗi ngày** là **tổng hợp theo ngày trước**, rồi mới chạy window.

### 7.2. Cumulative unique thường không giảm

Trong kết quả trên, số tích lũy tiến từ 2 lên 8. Nếu cùng một tập sự kiện và cùng một định danh, số distinct từng xuất hiện **không giảm** khi tiến về tương lai. Nếu biểu đồ “cumulative unique” có ngày giảm, hãy kiểm tra liệu chỉ số thực chất là rolling active, dữ liệu lịch sử bị sửa/xóa, cửa sổ tính lại đã đổi phạm vi, hoặc định danh/logic lọc đã thay đổi.

## 8. Làm đầy các ngày không có đối tượng mới

Biểu đồ theo ngày thường cần hiển thị cả ngày 03/10 và 05/10 với **new_actors = 0** và số tích lũy **không đổi**. Vì GROUP BY trên sự kiện không tự sinh ngày rỗng, ta tạo **calendar spine** (dãy ngày chuẩn) bằng `generate_series` của PostgreSQL.

```sql
WITH normalized_events AS (
    SELECT
        actor_id,
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS event_day
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
),
first_seen AS (
    SELECT
        actor_id,
        MIN(event_day) AS first_day
    FROM normalized_events
    GROUP BY actor_id
),
new_by_day AS (
    SELECT
        first_day,
        COUNT(*) AS new_actors
    FROM first_seen
    GROUP BY first_day
),
calendar_days AS (
    SELECT d::DATE AS report_day
    FROM generate_series(
        DATE '2026-10-01',
        DATE '2026-10-09',
        INTERVAL '1 day'
    ) AS g(d)
),
daily_series AS (
    SELECT
        c.report_day,
        COALESCE(n.new_actors, 0) AS new_actors
    FROM calendar_days AS c
    LEFT JOIN new_by_day AS n
        ON n.first_day = c.report_day
)
SELECT
    report_day,
    new_actors,
    SUM(new_actors) OVER (
        ORDER BY report_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_unique_actors
FROM daily_series
ORDER BY report_day;
```

Kết quả đầy đủ:

| report_day | new_actors | cumulative_unique_actors |
| --- | ---: | ---: |
| 2026-10-01 | 2 | 2 |
| 2026-10-02 | 1 | 3 |
| 2026-10-03 | 0 | 3 |
| 2026-10-04 | 1 | 4 |
| 2026-10-05 | 0 | 4 |
| 2026-10-06 | 1 | 5 |
| 2026-10-07 | 1 | 6 |
| 2026-10-08 | 1 | 7 |
| 2026-10-09 | 1 | 8 |

**Điểm quan trọng:** calendar ở đây chỉ quyết định **những ngày được hiển thị**. Việc tìm first-seen vẫn dựa trên **lịch sử sự kiện cần được tính**, không nên cắt bỏ sự kiện trước ngày 01/10 nếu một đối tượng đã tồn tại từ trước giai đoạn hiển thị.

### 8.1. Nếu ngày chưa có sự kiện, vì sao không lấy NULL?

`LEFT JOIN` tạo giá trị `n.new_actors = NULL` khi không có nhóm new_by_day tương ứng. `COALESCE(..., 0)` biến trường hợp **không có actor mới** thành 0 theo định nghĩa chỉ số. Điều này khác với một trường dữ liệu nghiệp vụ chưa được xác minh; ở đây `COUNT(*)` đã xác định số đối tượng mới, nên ngày không có đối tượng mới đúng là **0**.

### 8.2. Calendar có thể đến từ đâu?

- PostgreSQL: `generate_series`.
- SQL Server: bảng lịch, recursive CTE hoặc hàm sinh dãy phù hợp phiên bản.
- MySQL 8+: recursive CTE hoặc bảng lịch.
- BigQuery: `GENERATE_DATE_ARRAY` kết hợp `UNNEST`.
- Oracle: bảng lịch hoặc phương pháp sinh dòng phù hợp.
- Một data warehouse: bảng **calendar dimension** quản lý ngày, kỳ tài chính, tuần, ngày nghỉ.

Hàm `generate_series` không phải cú pháp chung của mọi DBMS. Điều quan trọng là **tạo một hàng cho mỗi ngày cần hiển thị**, sau đó LEFT JOIN số đối tượng mới.

## 9. Sai lầm phổ biến: cộng dồn COUNT DISTINCT theo ngày

Một truy vấn nhìn có vẻ hợp lý:

```sql
WITH daily_active AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS event_day,
        COUNT(DISTINCT actor_id) AS daily_unique
    FROM demo_unique_events
    GROUP BY 1
)
SELECT
    event_day,
    daily_unique,
    SUM(daily_unique) OVER (
        ORDER BY event_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS wrong_cumulative_unique
FROM daily_active
ORDER BY event_day;
```

Kết quả `wrong_cumulative_unique` có thể tăng tới **14**, dù chỉ có **8 actor** khác nhau. Vì cùng một actor hoạt động nhiều ngày, họ đóng góp vào `daily_unique` **nhiều lần**.

| Ngày | Daily unique | Tổng DAU cộng dồn (sai nếu gọi cumulative unique) | Cumulative unique đúng |
| --- | ---: | ---: | ---: |
| 01/10 | 2 | 2 | 2 |
| 02/10 | 2 | 4 | 3 |
| 03/10 | 0 | 4 | 3 |
| 04/10 | 3 | 7 | 4 |
| 05/10 | 0 | 7 | 4 |
| 06/10 | 2 | 9 | 5 |
| 07/10 | 1 | 10 | 6 |
| 08/10 | 3 | 13 | 7 |
| 09/10 | 1 | 14 | 8 |

Hai cột khác nhau vì **đơn vị được cộng** khác nhau:

- Tổng DAU cộng dồn đếm **lượt đối tượng-ngày**.
- Cumulative unique đếm **định danh duy nhất đã từng xuất hiện**.

Nếu báo cáo cần “tổng số lượt người-ngày hoạt động”, phép cộng DAU hoàn toàn có thể đúng. Nhưng nó **không phải** số người duy nhất tích lũy.

### 9.1. Vì sao COUNT DISTINCT với OVER không phải câu trả lời chung?

Người học có thể thử:

```sql
-- PostgreSQL: không hỗ trợ DISTINCT trong window aggregate kiểu này.
SELECT
    actor_id,
    COUNT(DISTINCT actor_id) OVER (
        ORDER BY occurred_at
    )
FROM demo_unique_events;
```

PostgreSQL không triển khai cú pháp DISTINCT trực tiếp trong window aggregate. Một số hệ khác có những khả năng hay giới hạn riêng; không thể giả định `COUNT(DISTINCT ...) OVER (ORDER BY ...)` chạy được và cho đúng KPI trên mọi hệ.

Ngay cả khi một DBMS hỗ trợ, kết quả ở grain **mỗi sự kiện** có thể khác yêu cầu **một hàng mỗi ngày**. Mẫu **first-seen → new_by_day → cumulative SUM** rõ ý nghĩa và thường dễ mang sang nhiều dialect hơn.

## 10. Kiểm chứng độc lập bằng COUNT DISTINCT tới từng mốc ngày

Đối với dữ liệu nhỏ hoặc khi muốn kiểm tra độ đúng, có thể tính trực tiếp số ID khác nhau đã xuất hiện **trước ngày tiếp theo**:

```sql
WITH calendar_days AS (
    SELECT d::DATE AS report_day
    FROM generate_series(
        DATE '2026-10-01',
        DATE '2026-10-09',
        INTERVAL '1 day'
    ) AS g(d)
)
SELECT
    c.report_day,
    (
        SELECT COUNT(DISTINCT e.actor_id)
        FROM demo_unique_events AS e
        WHERE e.actor_id IS NOT NULL
          AND e.occurred_at < (
              (c.report_day + 1)::TIMESTAMP
              AT TIME ZONE 'Asia/Ho_Chi_Minh'
          )
    ) AS cumulative_unique_actors
FROM calendar_days AS c
ORDER BY c.report_day;
```

Điều kiện:

```sql
e.occurred_at < start_of_next_local_day
```

bao gồm **mọi sự kiện trước hết ngày report_day** (kể cả lịch sử trước ngày hiển thị). Tại 09/10 kết quả là 8. Truy vấn tương quan này có thể cần tính DISTINCT cho mỗi ngày nên **đắt trên dãy dài và dữ liệu lớn**. Nó hữu ích như một cách **đối chiếu kỹ thuật/giải thích logic**, không nhất thiết là cách tối ưu để dựng dashboard sản xuất.

### 10.1. Vì sao so sánh “trước ngày hôm sau” thường tốt hơn “tới cuối hôm nay”?

Không cần tự tạo giá trị `23:59:59.999999` rồi lo thiếu precision hoặc timestamp có phần thập phân dài hơn. Ranh giới:

```text
[đầu lịch sử, đầu ngày kế tiếp)
```

là khoảng **nửa mở**, giúp bao trọn mọi thời điểm của ngày đang xét.

### 10.2. Đếm trực tiếp distinct cho toàn kỳ

Một phép kiểm tra đơn giản:

```sql
SELECT COUNT(DISTINCT actor_id) AS unique_actors
FROM demo_unique_events;
-- 8
```

Nếu dữ liệu đầu vào và phạm vi phù hợp, **giá trị cumulative cuối kỳ** phải bằng distinct trực tiếp của toàn bộ sự kiện tới cuối kỳ. Nếu không bằng, hãy kiểm tra logic first_seen, bộ lọc, timezone, ID NULL và dữ liệu trước mốc hiển thị.

## 11. Trường hợp khoảng báo cáo bắt đầu giữa lịch sử

Giả sử hệ thống đã hoạt động từ tháng 9 nhưng dashboard chỉ muốn hiển thị **01/10–09/10**. Nếu ta lọc bảng sự kiện:

```sql
-- Có thể làm sai định nghĩa "từng xuất hiện trong lịch sử":
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
```

**trước bước MIN first-seen**, những người đã hoạt động trong tháng 9 và quay lại tháng 10 sẽ bị coi là “người xuất hiện lần đầu trong tháng 10”. Chỉ số này thực chất đo **người lần đầu xuất hiện trong khoảng quan sát đã bị cắt**, không phải người mới của toàn hệ thống.

Cách đúng phụ thuộc yêu cầu:

1. Nếu KPI là **đã từng xuất hiện từ lúc hệ thống bắt đầu**, tìm first-seen trên **toàn lịch sử đủ điều kiện**, rồi chỉ cắt **ngày hiển thị** ở kết quả cuối.
2. Nếu KPI là **distinct trong khoảng bắt đầu từ ngày 01/10**, coi 01/10 là ranh giới đo; người đã từng xuất hiện trước đó nhưng có hoạt động trong kỳ sẽ được tính trong tập distinct của kỳ. Khi đó phải tính first-seen **trong phạm vi kỳ**, vì định nghĩa đã khác.

### 11.1. Mẫu có baseline trước ngày bắt đầu

Với KPI **lịch sử tích lũy toàn hệ thống**, số người đã xuất hiện **trước ngày bắt đầu hiển thị** phải trở thành một **baseline**. Ví dụ PostgreSQL:

```sql
WITH first_seen AS (
    SELECT
        actor_id,
        MIN(
            (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        ) AS first_day
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
    GROUP BY actor_id
),
baseline AS (
    SELECT COUNT(*) AS users_before_period
    FROM first_seen
    WHERE first_day < DATE '2026-10-01'
),
new_by_day AS (
    SELECT first_day, COUNT(*) AS new_users
    FROM first_seen
    WHERE first_day >= DATE '2026-10-01'
      AND first_day <= DATE '2026-10-09'
    GROUP BY first_day
),
calendar_days AS (
    SELECT d::DATE AS report_day
    FROM generate_series(
        DATE '2026-10-01',
        DATE '2026-10-09',
        INTERVAL '1 day'
    ) AS g(d)
),
daily_series AS (
    SELECT
        c.report_day,
        COALESCE(n.new_users, 0) AS new_users
    FROM calendar_days AS c
    LEFT JOIN new_by_day AS n
        ON n.first_day = c.report_day
)
SELECT
    d.report_day,
    d.new_users,
    b.users_before_period
      + SUM(d.new_users) OVER (
            ORDER BY d.report_day
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_unique_all_history
FROM daily_series AS d
CROSS JOIN baseline AS b
ORDER BY d.report_day;
```

Trong dữ liệu mẫu, `users_before_period = 0`, nên kết quả giống mục 8. Nếu có **100 actor** xuất hiện trước 01/10, giá trị tích lũy của 01/10 sẽ là **102** thay vì 2, với điều kiện hai actor mới ngày 01/10 chưa có trong baseline.

**Không chỉ thêm baseline vào cuối một danh sách `daily_new` đã bị lọc sai.** Bước `first_seen` phải dựa trên toàn lịch sử mà KPI định nghĩa.

### 11.2. Khi nào được tính “mới trong giai đoạn”?

Đôi khi doanh nghiệp cố ý muốn một số **distinct tính lại từ đầu kỳ**, ví dụ “từ ngày bắt đầu chiến dịch, đã có bao nhiêu ID khác nhau tương tác với chiến dịch”. Người đã hoạt động trước chiến dịch vẫn được tính **mới trong tập tương tác của chiến dịch** khi họ tương tác lần đầu trong kỳ. Khi đó lọc **sự kiện chiến dịch** trước khi tìm MIN là đúng.

Tên và mô tả chỉ số nên thể hiện rõ: **“ever seen all-time”**, **“first interaction in campaign”**, hay **“unique since selected date”**.

## 12. Đếm đối tượng duy nhất theo một hành vi cụ thể

Giả sử muốn số actor **đã từng có sự kiện SIGNUP**, tích lũy theo ngày SIGNUP đầu tiên. Ta phải **lọc loại sự kiện trước khi tính first-seen cho KPI SIGNUP**:

```sql
WITH first_signup AS (
    SELECT
        actor_id,
        MIN(
            (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        ) AS first_signup_day
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
      AND event_type = 'SIGNUP'
    GROUP BY actor_id
),
new_signup_actors AS (
    SELECT
        first_signup_day,
        COUNT(*) AS new_signup_actors
    FROM first_signup
    GROUP BY first_signup_day
)
SELECT
    first_signup_day,
    new_signup_actors,
    SUM(new_signup_actors) OVER (
        ORDER BY first_signup_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_signup_actors
FROM new_signup_actors
ORDER BY first_signup_day;
```

Kết quả:

| first_signup_day | new_signup_actors | cumulative_signup_actors |
| --- | ---: | ---: |
| 2026-10-01 | 1 | 1 |
| 2026-10-04 | 2 | 3 |
| 2026-10-06 | 1 | 4 |
| 2026-10-08 | 1 | 5 |

Các actor có SIGNUP trong mẫu là **u02, u03, u04, u01, u06**. Ví dụ u01 lần đầu có VIEW ngày 01/10 nhưng SIGNUP ngày 06/10; u01 **không phải actor mới ngày 06/10** trong KPI “ever seen”, nhưng là **actor lần đầu SIGNUP ngày 06/10** trong KPI SIGNUP.

### 12.1. Một người có thể SIGNUP nhiều lần?

Nếu nguồn sự kiện có các bản ghi SIGNUP trùng do retry, lỗi gửi lặp hoặc tài khoản được phục hồi, mẫu `MIN(first_signup_day)` vẫn chỉ giữ ngày SIGNUP đầu tiên **theo actor_id**. Tuy nhiên, nếu sản phẩm xác định một lần đăng ký bằng khóa nghiệp vụ khác (ví dụ account_id hoặc registration_id), phải xác nhận khóa đo cho phù hợp. Một người có hai tài khoản không nhất thiết là hai người thực.

### 12.2. “Mua hàng lần đầu” theo khách

Tương tự, nếu sự kiện PURCHASE xác định **đã phát sinh giao dịch hợp lệ**, lọc `event_type = 'PURCHASE'` trước khi tìm first-purchase day. Với hệ đơn hàng thật, trạng thái thanh toán, hủy và hoàn tiền có thể khiến một sự kiện “PURCHASE” không đủ làm tiêu chí ghi nhận doanh thu. SQL phải phản ánh quy tắc nghiệp vụ thực tế, không dựa đơn thuần vào tên sự kiện.

## 13. Phân nhóm theo kênh: hai định nghĩa khác nhau

Một bài toán hay gây tranh luận: “cumulative unique users theo channel”. Có ít nhất **hai cách hiểu**:

**A. Đối tượng đã từng xuất hiện trong từng kênh:** u01 có WEB, STORE, APP thì được tính **một lần ở mỗi kênh** nơi họ từng hoạt động.

**B. Đối tượng phân bổ vào kênh đầu tiên:** mỗi actor được gán **một kênh tiếp nhận ban đầu**, nên chỉ được tính **một lần trong một kênh duy nhất**.

Hai chỉ số có thể đều hữu ích, nhưng **không được dùng tên giống nhau rồi cộng các nhóm như thể chúng tương đương**.

### 13.1. Định nghĩa A — First seen trong từng channel

Để đếm “từng xuất hiện ở kênh này”:

```sql
WITH first_seen_per_channel AS (
    SELECT
        channel,
        actor_id,
        MIN(
            (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        ) AS first_day_in_channel
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
    GROUP BY channel, actor_id
),
daily_new AS (
    SELECT
        channel,
        first_day_in_channel,
        COUNT(*) AS new_to_channel
    FROM first_seen_per_channel
    GROUP BY channel, first_day_in_channel
)
SELECT
    channel,
    first_day_in_channel,
    new_to_channel,
    SUM(new_to_channel) OVER (
        PARTITION BY channel
        ORDER BY first_day_in_channel
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_unique_in_channel
FROM daily_new
ORDER BY channel, first_day_in_channel;
```

Ở cuối kỳ, số distinct **trong từng kênh**:

| Channel | Các actor đã xuất hiện trong kênh | Distinct cuối kỳ |
| --- | --- | ---: |
| WEB | u01, u02, u03, u07, u08 | 5 |
| APP | u01, u02, u04, u06, u07 | 5 |
| STORE | u01, u04, u05, u06 | 4 |

Tổng `5+5+4 = 14` **không bằng** distinct toàn hệ thống 8, vì một số actor xuất hiện ở nhiều kênh. Đây là ví dụ của **distinct không cộng gộp được qua các nhóm giao nhau**.

### 13.2. Định nghĩa B — Gán mỗi actor cho một kênh đầu tiên

Muốn phân bổ mỗi actor vào **kênh của sự kiện sớm nhất trên toàn lịch sử**, chọn một hàng đầu tiên bằng `ROW_NUMBER`:

```sql
WITH first_event_ranked AS (
    SELECT
        actor_id,
        channel,
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS first_day,
        ROW_NUMBER() OVER (
            PARTITION BY actor_id
            ORDER BY occurred_at, event_id
        ) AS rn
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
),
first_attribution AS (
    SELECT actor_id, channel, first_day
    FROM first_event_ranked
    WHERE rn = 1
)
SELECT
    channel AS acquisition_channel,
    COUNT(*) AS actors_first_seen_here
FROM first_attribution
GROUP BY channel
ORDER BY channel;
```

Kết quả:

| acquisition_channel | actors_first_seen_here |
| --- | ---: |
| APP | 2 |
| STORE | 1 |
| WEB | 5 |

Tổng = **8**, đúng bằng distinct toàn hệ thống, bởi mỗi actor được phân bổ vào **đúng một kênh đầu tiên**. u01 lần đầu là WEB dù sau đó có cả STORE/APP.

**Cảnh báo nghiệp vụ:** “kênh sự kiện đầu tiên ghi nhận” không luôn giống “kênh marketing đã thu hút khách”. Nếu muốn **first-touch attribution** thật sự, phải xác định sự kiện và quy tắc ghi nhận nguồn marketing; ví dụ này chỉ minh họa cách phân bổ định danh theo sự kiện sớm nhất.

### 13.3. Tại sao cần ORDER BY event_id khi timestamp bằng nhau?

Hai sự kiện của cùng actor có thể được ghi cùng `occurred_at`. Nếu chỉ:

```sql
ROW_NUMBER() OVER (PARTITION BY actor_id ORDER BY occurred_at)
```

DBMS không có quy tắc xác định chắc chắn sự kiện nào là đầu khi timestamp đồng hạng. `event_id` làm khóa phụ **duy nhất trong bảng mẫu**. Trong hệ thống đa nguồn, cần một khóa phụ toàn cục hoặc chính sách ưu tiên có tính ổn định để tránh thay đổi kênh đầu tiên giữa các lần chạy.

## 14. Tích lũy theo tháng và đặt lại số đếm mỗi tháng

Có hai KPI khác nhau:

1. **Cumulative unique toàn thời gian, hiển thị mỗi tháng:** số actor từng xuất hiện từ đầu lịch sử đến hết từng tháng. Dùng **first_day toàn lịch sử**, gộp theo tháng đầu tiên, rồi SUM lũy kế theo tháng.
2. **Distinct tích lũy lại từ đầu mỗi tháng:** trong mỗi tháng, từ ngày 1 đến ngày hiện tại, có bao nhiêu actor **đã xuất hiện ít nhất một lần trong tháng đó**. Một người quay lại tháng sau được tính lại ở tháng sau; phải tìm first-seen **theo cặp `(tháng, actor_id)`**.

Nếu chỉ gắn `PARTITION BY month` vào SUM lũy kế của **người mới toàn lịch sử**, kết quả sẽ thành “số actor xuất hiện lần đầu trong lịch sử kể từ đầu tháng” chứ **không phải** “distinct đã hoạt động trong tháng”. Hai khái niệm khác nhau rõ rệt.

### 14.1. Distinct tích lũy trong từng tháng

Ví dụ PostgreSQL:

```sql
WITH normalized AS (
    SELECT
        actor_id,
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS event_day
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
),
first_in_month AS (
    SELECT
        DATE_TRUNC('month', event_day)::DATE AS month_start,
        actor_id,
        MIN(event_day) AS first_day_in_month
    FROM normalized
    GROUP BY DATE_TRUNC('month', event_day)::DATE, actor_id
),
new_to_month_by_day AS (
    SELECT
        month_start,
        first_day_in_month,
        COUNT(*) AS first_active_in_month
    FROM first_in_month
    GROUP BY month_start, first_day_in_month
)
SELECT
    month_start,
    first_day_in_month,
    first_active_in_month,
    SUM(first_active_in_month) OVER (
        PARTITION BY month_start
        ORDER BY first_day_in_month
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS month_to_date_unique
FROM new_to_month_by_day
ORDER BY month_start, first_day_in_month;
```

Trong dữ liệu mẫu chỉ có tháng 10/2026, nên kết quả tới ngày 09/10 trùng với ever-seen unique. Khi thêm tháng 11, người đã hoạt động trong tháng 10 nhưng quay lại tháng 11 sẽ được tính **một lần trong tháng 11**, đúng định nghĩa MTD unique.

### 14.2. Tổng theo tháng không cộng gộp qua tháng

Nếu October có 8 actor và November có 7 actor, không thể kết luận hai tháng hợp lại có 15 actor duy nhất. Một actor có thể hoạt động trong cả hai tháng. Muốn distinct trên cả hai tháng, cần **khử trùng trên tập hợp hai tháng** hoặc dùng first-seen đúng phạm vi.

## 15. Rolling 7-day distinct không phải cumulative unique

**Rolling 7-day unique** tại ngày \(d\) là số actor có **ít nhất một sự kiện từ ngày \(d-6\) đến hết ngày \(d\)**. Người không còn hoạt động trong cửa sổ bảy ngày sẽ rơi khỏi tập; vì thế chỉ số có thể giảm.

Truy vấn PostgreSQL minh họa trên dữ liệu mẫu:

```sql
WITH normalized AS (
    SELECT
        actor_id,
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS event_day
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
),
calendar_days AS (
    SELECT d::DATE AS report_day
    FROM generate_series(
        DATE '2026-10-01',
        DATE '2026-10-12',
        INTERVAL '1 day'
    ) AS g(d)
)
SELECT
    c.report_day,
    COUNT(DISTINCT e.actor_id) AS rolling_7day_unique
FROM calendar_days AS c
LEFT JOIN normalized AS e
    ON e.event_day >= c.report_day - 6
   AND e.event_day <= c.report_day
GROUP BY c.report_day
ORDER BY c.report_day;
```

Ở ngày 09/10, cửa sổ từ 03/10 đến 09/10 vẫn có đủ cả **8 actor**, vì u01/u02/u03 đã quay lại sau ngày 03/10. Đến ngày **11/10**, cửa sổ từ 05/10 đến 11/10 không còn hoạt động của **u02 và u03**, do sự kiện mới nhất của họ đều ở ngày 04/10; rolling 7-day distinct giảm còn **6**, trong khi cumulative ever-seen vẫn là **8**.

### 15.1. Vì sao không lấy SUM của DAU trong bảy ngày?

Một actor hoạt động ngày 06 và 08 vẫn chỉ được tính **một lần** trong rolling 7-day distinct, nhưng nếu cộng DAU của bảy ngày sẽ tính người đó hai lần. Rolling distinct là số lượng của **hợp các tập người theo ngày**, không phải tổng các lực lượng của từng tập.

### 15.2. Vì sao ROWS 6 PRECEDING không có nghĩa bảy ngày?

Nếu window chạy trên **hàng sự kiện**, `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` là bảy **sự kiện** tối đa, có thể cùng một ngày và từ cùng actor. Nếu chạy trên bảng `daily_unique`, ROWS bảy ngày chỉ cộng số daily distinct, vẫn **đếm lại người ở nhiều ngày**.

Muốn rolling distinct chính xác, phải xét **các ID trong toàn khoảng ngày** rồi khử trùng, hoặc triển khai cấu trúc dữ liệu chuyên dụng có thể hợp nhất tập ID/bitmap theo cửa sổ.

### 15.3. Chi phí của phép JOIN khoảng

Truy vấn mẫu `calendar LEFT JOIN events ... BETWEEN` có thể ghép **mỗi sự kiện với tối đa bảy ngày báo cáo**, tạo tập trung gian lớn. Khi dữ liệu khổng lồ, cần cân nhắc partition theo thời gian, index, bảng tổng hợp, cấu trúc bitmap hoặc hệ phân tích chuyên dụng. **Không tối ưu bằng cách thay rolling distinct bằng SUM DAU**, vì như vậy đổi hẳn nghĩa KPI.

## 16. Cách thay thế: đánh dấu sự kiện đầu tiên bằng ROW_NUMBER

Thay vì GROUP BY actor_id để lấy MIN ngày, có thể dùng:

```sql
WITH ranked_events AS (
    SELECT
        event_id,
        actor_id,
        occurred_at,
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS event_day,
        ROW_NUMBER() OVER (
            PARTITION BY actor_id
            ORDER BY occurred_at, event_id
        ) AS first_event_position
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
),
first_events AS (
    SELECT
        actor_id,
        event_day AS first_day
    FROM ranked_events
    WHERE first_event_position = 1
),
new_by_day AS (
    SELECT first_day, COUNT(*) AS new_users
    FROM first_events
    GROUP BY first_day
)
SELECT
    first_day,
    new_users,
    SUM(new_users) OVER (
        ORDER BY first_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_unique
FROM new_by_day
ORDER BY first_day;
```

Kết quả giống mẫu `MIN(event_day)` khi dữ liệu và thứ tự được định nghĩa nhất quán. Cách này hữu ích khi cần mang theo **thuộc tính của sự kiện đầu tiên** như channel, event_type, campaign, version.

### 16.1. Không đưa actor_id NULL vào partition rồi đếm một “người NULL”

Nếu bỏ `WHERE actor_id IS NOT NULL`, tất cả sự kiện actor_id NULL có thể cùng thuộc một partition NULL. `ROW_NUMBER() = 1` sẽ giữ **một hàng NULL**, và nếu tiếp tục `COUNT(*)` trên first_events, hàng ấy có thể bị đếm là **một đối tượng mới giả**. Vì vậy, với KPI distinct actor xác định, phải loại NULL **trước ROW_NUMBER**, hoặc xử lý chúng bằng chính sách định danh riêng.

### 16.2. MIN thường đơn giản hơn khi chỉ cần ngày

Chọn MIN/GROUP BY nếu chỉ muốn **ngày đầu** và cần kết quả một hàng trên mỗi ID. Chọn ROW_NUMBER khi cần **đúng bản ghi đầu** với các cột đi kèm. Hai cách có thể khác về kế hoạch sort/hash, memory và hiệu năng; hãy đo trên cơ sở dữ liệu thật, không khẳng định một cách luôn nhanh hơn.

## 17. Một hàng sự kiện có thể bị nhân trước khi đếm

Một bảng sự kiện có thể được JOIN với bảng `event_tags`, trong đó mỗi event có nhiều nhãn. Nếu:

```sql
SELECT e.actor_id, e.occurred_at
FROM events AS e
JOIN event_tags AS t
    ON t.event_id = e.event_id;
```

một event có ba tag sẽ tạo **ba hàng**. Với `MIN(event_day) GROUP BY actor_id`, ngày đầu có thể vẫn đúng nếu JOIN chỉ nhân bản mà không thêm/loại sự kiện, nhưng nếu tiếp tục `COUNT(*)` trực tiếp trên tập JOIN theo ngày, tổng số sự kiện sẽ bị nhân. JOIN **cũng có thể loại mất event** nếu dùng INNER JOIN đến bảng con không có bản ghi; khi ấy first-seen có thể dịch muộn đi.

**Không xem GROUP BY actor_id như một cách tự động sửa mọi JOIN sai.** Trước khi tính chỉ số, phải xác định tập sự kiện đủ điều kiện và JOIN nào có thể làm mất hay nhân hàng.

### 17.1. Khi chỉ cần điều kiện có tag, dùng EXISTS

Giả sử muốn tính actor từng có event gắn tag hợp lệ:

```sql
-- Ví dụ khái niệm trên bảng nghiệp vụ giả định.
SELECT e.actor_id, e.occurred_at
FROM events AS e
WHERE e.actor_id IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM event_tags AS t
      WHERE t.event_id = e.event_id
        AND t.tag_name = 'QUALIFIED'
  );
```

`EXISTS` không đưa mọi tag ra nhân hàng. Sau khi chọn tập event hợp lệ, mới thực hiện first-seen. Tuy nhiên, nếu dữ liệu nguồn có nhiều event cùng actor, đó là **lặp hoạt động hợp lệ**, không cần loại sự kiện trước MIN khi chỉ cần ngày đầu.

### 17.2. Nếu định danh chỉ duy nhất trong tenant

Nếu hai tổ chức cùng có `actor_id = 'u01'` nhưng là **hai người khác nhau**, phải dùng khóa ghép `(tenant_id, actor_id)`:

```sql
SELECT
    tenant_id,
    actor_id,
    MIN(event_day) AS first_day
FROM normalized_events
GROUP BY tenant_id, actor_id;
```

Nếu truy vấn toàn hệ thống và actor_id chỉ duy nhất trong tenant, GROUP BY một mình actor_id sẽ **gộp nhầm đối tượng của hai tenant**. Ngược lại, nếu doanh nghiệp dùng định danh toàn cục để hợp nhất nhiều tenant theo chính sách rõ ràng, khóa đếm phải phản ánh quy tắc đó. Không được tự bỏ tenant khi không có cam kết định danh chung.

## 18. Phương ngữ: chuyển mẫu first-seen và window

Cấu trúc logic của cách **first-seen → count new → running SUM** hoạt động trên nhiều DBMS hiện đại. Khác biệt chủ yếu ở cách chuyển timestamp sang ngày, cách sinh calendar, tên kiểu và cú pháp hàm thời gian.

### 18.1. PostgreSQL

Các thành phần trọng tâm:

```sql
MIN((occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE)
```

```sql
generate_series(
    DATE '2026-10-01',
    DATE '2026-10-09',
    INTERVAL '1 day'
)
```

```sql
SUM(new_users) OVER (
    ORDER BY report_day
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

PostgreSQL không triển khai DISTINCT trực tiếp trong window aggregate. Vì thế first-seen là phương án vừa rõ ý nghĩa vừa hữu ích khi cần phân nhóm ngày.

### 18.2. SQL Server

Nếu event timestamp trong hệ thống SQL Server đã được **chuẩn hóa thành ngày nghiệp vụ** `event_day` kiểu `date`, đoạn cốt lõi trong T-SQL là:

```sql
WITH first_seen AS (
    SELECT
        actor_id,
        MIN(event_day) AS first_day
    FROM dbo.events
    WHERE actor_id IS NOT NULL
    GROUP BY actor_id
),
new_by_day AS (
    SELECT
        first_day,
        COUNT_BIG(*) AS new_users
    FROM first_seen
    GROUP BY first_day
)
SELECT
    first_day,
    new_users,
    SUM(new_users) OVER (
        ORDER BY first_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_unique
FROM new_by_day
ORDER BY first_day;
```

`dbo.events` là bảng ví dụ giả định, không phải bảng tạm PostgreSQL của mục 3. `COUNT_BIG` dùng kiểu số nguyên rộng. Nếu `event_day` chưa có, cần quy tắc chuyển `datetimeoffset`/UTC sang múi giờ nghiệp vụ, có thể liên quan `AT TIME ZONE` của SQL Server và các yêu cầu phiên bản. **Không giả định `CAST(occurred_at AS date)` luôn cho đúng ngày địa phương khi nguồn lưu UTC**.

Trong SQL Server, `COUNT(DISTINCT ...) OVER (ORDER BY ...)` không phải dạng window aggregate DISTINCT có thể dùng như một giải pháp trực tiếp. CTE first-seen và SUM lũy kế là cách dễ hiểu và di động hơn.

### 18.3. MySQL 8.0+

Giả sử cột `event_day` DATE đã được xác định nhất quán trong MySQL:

```sql
WITH first_seen AS (
    SELECT
        actor_id,
        MIN(event_day) AS first_day
    FROM events
    WHERE actor_id IS NOT NULL
    GROUP BY actor_id
),
new_by_day AS (
    SELECT
        first_day,
        COUNT(*) AS new_users
    FROM first_seen
    GROUP BY first_day
)
SELECT
    first_day,
    new_users,
    SUM(new_users) OVER (
        ORDER BY first_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_unique
FROM new_by_day
ORDER BY first_day;
```

MySQL 8.0+ hỗ trợ CTE và window; các phiên bản cũ hơn có khác biệt đáng kể. Khi chuyển timestamp UTC sang ngày địa phương, có thể cần `CONVERT_TZ` và cấu hình bảng timezone phù hợp. Câu SQL trên cố ý dùng cột ngày đã chuẩn hóa để không che lấp khác biệt miền thời gian.

### 18.4. BigQuery (GoogleSQL)

Trong BigQuery, `DATE(timestamp_expression, 'Asia/Ho_Chi_Minh')` giúp tính ngày theo timezone chỉ định khi đầu vào là TIMESTAMP:

```sql
WITH first_seen AS (
    SELECT
        actor_id,
        MIN(DATE(occurred_at, 'Asia/Ho_Chi_Minh')) AS first_day
    FROM `project.dataset.events`
    WHERE actor_id IS NOT NULL
    GROUP BY actor_id
),
new_by_day AS (
    SELECT
        first_day,
        COUNT(*) AS new_users
    FROM first_seen
    GROUP BY first_day
)
SELECT
    first_day,
    new_users,
    SUM(new_users) OVER (
        ORDER BY first_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_unique
FROM new_by_day
ORDER BY first_day;
```

Tên bảng phải thay bằng project/dataset/table thật. Khi cần ngày không có actor mới, BigQuery có thể dùng:

```sql
SELECT report_day
FROM UNNEST(
    GENERATE_DATE_ARRAY(DATE '2026-10-01', DATE '2026-10-09')
) AS report_day;
```

Cần JOIN ngày này với bảng new_by_day và dùng COALESCE như ví dụ PostgreSQL.

### 18.5. Oracle, SQLite và các hệ khác

Với Oracle và SQLite, phần logic `GROUP BY actor_id`, `MIN(event_day)`, GROUP BY ngày đầu và `SUM(new_users) OVER (ORDER BY day ROWS ...)` vẫn là nền tảng. Nhưng:

- Oracle có kiểu DATE/TIMESTAMP và quy tắc timezone riêng; phương pháp tạo dãy ngày có thể dùng bảng lịch hoặc cách sinh hàng của Oracle.
- SQLite lưu ngày giờ theo cơ chế kiểu linh hoạt hơn; cần chuẩn hóa ngày và định danh trước, không dựa mù quáng vào CAST kiểu ngày giống PostgreSQL.
- Khả năng CTE/window và các lựa chọn frame phụ thuộc phiên bản engine thực tế.

Không nên gọi một hàm là “SQL chuẩn” chỉ vì nhiều DBMS cùng có hàm tên giống nhau; **chuẩn hóa event_day** là bước có thể tách khỏi logic distinct tích lũy để chuyển hệ dễ hơn.

## 19. Quy mô dữ liệu lớn và tối ưu hóa

Với hàng tỷ sự kiện, tính `GROUP BY actor_id` trên toàn bộ lịch sử mỗi lần mở dashboard có thể tốn nhiều tài nguyên. Truy vấn mẫu là **cách diễn đạt đúng ngữ nghĩa**, còn phương án vận hành cần chọn theo khối lượng, tần suất cập nhật và khả năng của hệ quản trị.

### 19.1. Bảng lưu first-seen đã chuẩn hóa

Có thể duy trì một bảng:

```text
actor_first_seen(
    tenant_id,
    actor_id,
    first_seen_at,
    first_day,
    first_channel,
    updated_at
)
```

Với một hàng duy nhất theo **khóa định danh nghiệp vụ**, bảng này giúp:

- Tránh quét mọi event để lấy MIN mỗi lần báo cáo.
- Đếm actor mới theo ngày trực tiếp từ `first_day`.
- Ghi nhận thuộc tính gắn với sự kiện đầu tiên theo quy tắc được xác nhận.
- Phục vụ báo cáo cumulative theo nhiều kỳ hiển thị.

Phải có cơ chế cập nhật đúng khi sự kiện tới trễ, định danh bị hợp nhất/tách, hoặc chính sách lọc thay đổi. **Bảng first-seen là dữ liệu dẫn xuất**, không tự luôn đúng nếu pipeline chỉ INSERT và không xử lý thay đổi quá khứ.

### 19.2. Chỉ mục và phân vùng

Trong PostgreSQL, một index có thể hỗ trợ truy vấn lấy sự kiện theo actor và thời gian:

```sql
CREATE INDEX idx_demo_unique_events_actor_time
ON demo_unique_events (actor_id, occurred_at);
```

Hoặc nếu thường lọc thời gian:

```sql
CREATE INDEX idx_demo_unique_events_time_actor
ON demo_unique_events (occurred_at, actor_id);
```

Hai index phục vụ các kiểu truy vấn khác nhau; không mặc định nên tạo cả hai trên hệ sản xuất. Index tăng chi phí ghi và dung lượng; truy vấn first-seen toàn lịch sử có thể vẫn phải đọc phần lớn dữ liệu. Trên bảng lớn, partition theo thời gian, clustering, phân phối dữ liệu và bảng tổng hợp có thể quan trọng hơn một index đơn lẻ.

### 19.3. Kiểm tra kế hoạch bằng EXPLAIN

```sql
EXPLAIN
SELECT
    actor_id,
    MIN(occurred_at) AS first_seen_at
FROM demo_unique_events
WHERE actor_id IS NOT NULL
GROUP BY actor_id;
```

Trong PostgreSQL, kế hoạch có thể dùng scan, aggregate/hash aggregate, sort hoặc chiến lược khác. Với môi trường thử nghiệm thích hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    actor_id,
    MIN(occurred_at) AS first_seen_at
FROM demo_unique_events
WHERE actor_id IS NOT NULL
GROUP BY actor_id;
```

`EXPLAIN (ANALYZE, BUFFERS)` **thực sự chạy truy vấn SELECT** và cho thông tin số hàng/thời gian/buffer. Dữ liệu demo 16 sự kiện chỉ để học, không kết luận được hiệu năng trên bảng hàng trăm triệu hàng.

### 19.4. Exact distinct và approximate distinct

Một số hệ phân tích có thuật toán **distinct xấp xỉ** như HyperLogLog để giảm bộ nhớ/chi phí trên quy mô rất lớn. Tuy nhiên:

- Kết quả **xấp xỉ**, có sai số, không phải đáp án exact từ COUNT DISTINCT.
- Không phải mọi dạng sketch đều hỗ trợ **hợp nhất hay trừ** các tập theo cách trực tiếp cho rolling window.
- Cần phân biệt **union của các tập ID** với tổng các **ước lượng số lượng**; cộng các estimate từng ngày vẫn có thể đếm lặp người.
- Với một chỉ số pháp lý, thanh toán hay đối soát cần số chính xác, approximate distinct có thể không đáp ứng yêu cầu.

Khi dùng sketch hoặc bitmap để tích lũy, phải bảo đảm phép **gộp tập đối tượng** đúng quy tắc của cấu trúc, thay vì SUM các số cardinality của từng ngày.

## 20. Dữ liệu tới trễ và cách sửa ngày first-seen

Một event của actor u09 xảy ra **ngày 01/10** nhưng tới database **ngày 10/10**, khi báo cáo 01/10–09/10 đã được tính. Nếu u09 chưa có sự kiện nào trước đó, dãy cumulative trước đây thiếu một actor từ ngày 01/10 trở đi.

Một trường hợp tinh vi hơn:

```text
Ngày hệ thống nhận:
  08/10: thấy user u10, event_time = 08/10
  11/10: nhận muộn event của u10, event_time = 02/10
```

Trong bảng first-seen theo **event_time**, ngày đầu của u10 phải **chuyển từ 08/10 về 02/10**. Khi cập nhật bảng `new_users`:

- **Giảm 1** ở 08/10.
- **Tăng 1** ở 02/10.
- Tính lại các mốc cumulative bị ảnh hưởng theo chính sách pipeline.

Tổng distinct cuối kỳ có thể không đổi, nhưng **đường biểu diễn theo ngày** thay đổi. Một pipeline chỉ cộng các sự kiện mới nhận vào số lũy kế mà không xử lý event đến trễ sẽ tạo lịch sử sai.

### 20.1. Chính sách dữ liệu có thể được quyết định theo watermark

Một hệ thống streaming có thể chấp nhận dữ liệu muộn trong một khoảng **grace period** hoặc dùng **watermark** để xác định ngày nào coi là đã chốt. Nếu sự kiện còn tới sau ngày chốt, cần chính sách:

1. Cho phép backfill và cập nhật lại chỉ số lịch sử.
2. Đánh dấu báo cáo lịch sử đã chốt, theo dõi sai lệch riêng.
3. Từ chối hoặc chuyển sự kiện quá trễ sang luồng xử lý đặc biệt.

Tùy yêu cầu nghiệp vụ, các cách đều có thể được sử dụng; điều quan trọng là dashboard phải **nói rõ khi nào dữ liệu ổn định** và có khả năng đối chiếu lại.

### 20.2. Thay đổi quy tắc định danh

Khi hai tài khoản được hợp nhất thành một người, tổng distinct theo `account_id` và tổng distinct theo **person_id sau hợp nhất** khác nhau. Nếu ID được sửa hồi tố, số tích lũy có thể giảm so với báo cáo cũ. Sự giảm ấy không nhất thiết là lỗi SQL, mà có thể là thay đổi **khái niệm đối tượng đang được đếm**.

Vì vậy, cần lưu phiên bản chính sách định danh hoặc ghi nhận lịch sử mapping khi doanh nghiệp yêu cầu tính lại số liệu chính xác theo một định nghĩa cố định.

## 21. Độ nhất quán khi có dữ liệu cập nhật đồng thời

Một dashboard có thể chạy nhiều câu truy vấn: một câu lấy `COUNT(DISTINCT actor_id)` toàn kỳ, câu khác tính chuỗi cumulative từ sự kiện. Nếu dữ liệu mới được ghi **giữa hai lần đọc**, hai kết quả có thể không bằng nhau chỉ vì chúng không cùng một trạng thái dữ liệu.

Khi yêu cầu đối soát chặt:

- Tính các chỉ số trong **cùng một truy vấn** nếu phù hợp.
- Hoặc dùng một snapshot/transaction isolation thích hợp để các phép đọc nhìn cùng phiên bản dữ liệu.
- Ghi rõ thời điểm hoặc phiên bản batch dữ liệu phục vụ dashboard.
- Với kho dữ liệu phân tán, cân nhắc tính nhất quán và thời điểm dữ liệu sẵn sàng của các bảng dẫn xuất.

Nếu chỉ số cumulative được precompute theo batch, không nên so sánh trực tiếp với bảng sự kiện raw đã cập nhật mới hơn mà không xét **data freshness**.

## 22. Kiểm tra kỹ thuật và các bất biến của chỉ số

Một số **tính chất ngữ nghĩa** hữu ích khi xây dựng pipeline:

1. `new_users` theo ngày không âm.
2. Mỗi actor đủ điều kiện có **đúng một** `first_day`.
3. Tổng `new_users` trên toàn lịch sử bằng `COUNT(DISTINCT actor_id)` của nguồn với cùng điều kiện định danh.
4. Dãy cumulative không giảm trên một snapshot cố định với cùng phạm vi và chính sách.
5. Ngày không có actor mới giữ nguyên cumulative.
6. Cumulative cuối kỳ bằng distinct trực tiếp tới hết ngày đó.
7. Nếu phân nhóm theo channel có thể giao nhau, **không cộng distinct kênh để kết luận distinct toàn hệ thống**.
8. Nếu chỉ lấy dữ liệu từ giữa lịch sử, phải quyết định baseline hoặc đổi định nghĩa thành distinct trong khoảng.

Một câu SQL đối chiếu số actor ở `first_seen` với distinct nguồn:

```sql
WITH first_seen AS (
    SELECT actor_id, MIN(occurred_at) AS first_at
    FROM demo_unique_events
    WHERE actor_id IS NOT NULL
    GROUP BY actor_id
)
SELECT
    (SELECT COUNT(*) FROM first_seen) AS actors_in_first_seen,
    (
        SELECT COUNT(DISTINCT actor_id)
        FROM demo_unique_events
    ) AS actors_in_source;
-- 8 và 8.
```

Hai số phải bằng nhau trên cùng nguồn và bộ lọc. Đây là một cách kiểm tra **logic mô hình đếm** trong thực hành SQL; trong quy trình xuất bản tài liệu, việc đánh giá nội dung và chạy thử sâu vẫn là bước riêng.

## 23. Những lỗi thường gặp

| Ngộ nhận hoặc cách viết | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `SUM(daily_distinct)` là cumulative distinct | Một actor quay lại ở nhiều ngày bị cộng nhiều lần | First-seen per actor rồi đếm new theo ngày |
| `COUNT(DISTINCT actor_id)` theo ngày cho biết “người mới” | Nó đếm cả người đã từng hoạt động trước đó | MIN ngày trên toàn lịch sử phù hợp |
| `COUNT(DISTINCT ...) OVER(ORDER BY ...)` chạy ở mọi DBMS | PostgreSQL không triển khai DISTINCT window aggregate trực tiếp | First-seen + SUM window |
| Cứ lọc tháng đang xem trước MIN first-seen | Người cũ quay lại bị ghi nhận thành mới | Tìm first-seen toàn lịch sử, hoặc xác định lại KPI |
| Calendar rỗng nghĩa là lỗi | Không có người mới cũng là một ngày hợp lệ | Calendar spine + LEFT JOIN + COALESCE 0 |
| `COUNT(DISTINCT actor_id)` tính NULL là một người | COUNT DISTINCT bỏ qua NULL | Quyết định chính sách anonymous ID |
| Actor_id chuỗi rỗng luôn bị bỏ qua như NULL | Nhiều DBMS phân biệt `''` với NULL | Chuẩn hóa theo chính sách |
| `occurred_at::DATE` luôn là ngày nghiệp vụ đúng | Với timestamptz có thể phụ thuộc session timezone | Chỉ rõ timezone khi lấy event_day |
| Tìm ngày đầu bằng thời gian nhận dữ liệu | Sự kiện tới trễ có thể thay đổi ngày đầu theo event_time | Phân biệt occurred_at và ingested_at |
| GROUP BY actor_id toàn hệ thống khi ID chỉ unique trong tenant | Có thể gộp hai người khác tổ chức | Khóa `(tenant_id, actor_id)` |
| Cộng distinct theo từng channel để ra toàn hệ thống | Người dùng nhiều kênh được đếm nhiều lần | Distinct toàn bộ hoặc attribution độc quyền |
| GROUP BY month rồi SUM distinct từng ngày | Người hoạt động nhiều ngày bị cộng lặp | First-seen trong tháng theo `(month, actor)` |
| Rolling 7-day distinct là cumulative ever-seen | Rolling có thể giảm, cumulative thường không | Định nghĩa tập hàng theo cửa sổ khác nhau |
| `ROWS 6 PRECEDING` luôn là bảy ngày lịch | ROWS đếm hàng, không đếm ngày | Calendar + ROWS hoặc truy vấn khoảng ngày |
| JOIN tags rồi COUNT(*) là số event | JOIN 1:N nhân hàng | Đếm đúng khóa hoặc dùng EXISTS |
| ROW_NUMBER trên actor NULL rồi COUNT(*) | Có thể đếm một “actor NULL” giả | Loại NULL trước partition |
| Một bảng first-seen chỉ cần INSERT mãi | Dữ liệu muộn có thể khiến ngày đầu dịch về quá khứ | UPSERT/backfill và tính lại ảnh hưởng |
| Approximate distinct là phép đếm chính xác | Sketch có sai số và khả năng merge riêng | Chọn exact/approx phù hợp KPI |
| Cumulative luôn không giảm dù dữ liệu thay đổi | Sửa ID, xóa dữ liệu hoặc đổi định nghĩa làm số lịch sử đổi | Ghi rõ snapshot và chính sách dữ liệu |

## 24. Bài tập thực hành

Các bài dưới đây dùng bảng tạm `demo_unique_events` ở mục 3. Hãy dự đoán **tập actor** và số đếm trước khi chạy, để phân biệt lượt hoạt động, distinct trong kỳ và distinct lần đầu.

### Bài 1 — Daily distinct

Tính số actor duy nhất trong từng ngày theo `Asia/Ho_Chi_Minh` bằng `COUNT(DISTINCT actor_id)`. Dùng calendar từ ngày 01/10 đến 09/10 để hiển thị cả hai ngày không có sự kiện. Dự đoán dãy số: **2, 2, 0, 3, 0, 2, 1, 3, 1**.

### Bài 2 — Vì sao cộng DAU sai?

Lấy kết quả bài 1 rồi dùng SUM window để cộng dồn. Giá trị ở 09/10 là bao nhiêu? Vì sao nó bằng **14**, không phải **8 người**? Hãy lấy một actor có nhiều ngày hoạt động và chỉ rõ các lần bị đếm lại.

### Bài 3 — Ngày xuất hiện đầu tiên

Viết `GROUP BY actor_id` kết hợp `MIN(event_day)` để lấy một hàng mỗi actor. `u01`, `u03`, `u06` có ngày đầu lần lượt nào? Vì sao phải loại NULL?

### Bài 4 — New actor theo ngày

Từ first_seen, nhóm theo `first_day` và COUNT(*). Tại ngày 04/10 có ba actor hoạt động (u02, u03, u04) nhưng chỉ có bao nhiêu actor mới? Giải thích vì sao ngày đó chỉ có **1** actor mới.

### Bài 5 — Cumulative unique đầy đủ

Viết một truy vấn `WITH first_seen, new_by_day, calendar_days, daily_series` rồi SUM window. Kiểm tra dãy **2, 3, 3, 4, 4, 5, 6, 7, 8**. Đối chiếu giá trị cuối với COUNT(DISTINCT actor_id) trên toàn bảng.

### Bài 6 — Timezone thay đổi kết quả

Event 1 diễn ra lúc **00:30 ngày 01/10 tại Việt Nam**. Nó là ngày nào theo UTC? Nếu lấy ngày bằng timezone UTC thay vì Việt Nam, ngày xuất hiện đầu tiên của u01 thay đổi thế nào? Điều đó ảnh hưởng số tích lũy ở ranh giới 30/09–01/10 như thế nào?

### Bài 7 — SIGNUP khác lần đầu xuất hiện

Chỉ tính actor có ít nhất một `event_type = 'SIGNUP'`. Tìm ngày SIGNUP đầu và số signup actor tích lũy. Dự đoán các ngày tăng là 01/10, 04/10, 06/10, 08/10 và giá trị cuối **5**. Vì sao u01 được tính mới cho KPI SIGNUP ở 06/10 nhưng không mới cho KPI ever-seen ở 06/10?

### Bài 8 — Cumulative theo từng channel

GROUP BY `(channel, actor_id)` để tìm lần đầu của actor trong từng channel, đếm số mới vào channel rồi SUM window `PARTITION BY channel`. Kết quả distinct cuối kỳ từng kênh WEB, APP, STORE là bao nhiêu? Vì sao **5 + 5 + 4 ≠ 8**?

### Bài 9 — Attribution kênh đầu

Dùng ROW_NUMBER theo actor để chọn event đầu tiên bằng `(occurred_at, event_id)`. Nhóm actor theo channel của event ấy. Dự đoán APP **2**, STORE **1**, WEB **5**. Vì sao tổng nhóm ở đây bằng distinct toàn hệ thống?

### Bài 10 — Mốc hiển thị giữa lịch sử

Giả sử thêm một sự kiện của actor u09 ở **29/09**, rồi u09 quay lại ngày 02/10. Nếu dashboard “all-time unique” chỉ hiển thị 01/10–09/10, có được lọc bỏ 29/09 trước MIN first-seen không? Thiết kế baseline và dãy new_user đúng.

### Bài 11 — Rolling 7-day

Tính distinct actor trong khoảng `[report_day - 6, report_day]`. Khi kéo dài ngày báo cáo đến 11/10, vì sao rolling 7-day unique có thể giảm còn **6**, trong khi all-time cumulative vẫn là **8**?

### Bài 12 — First event bằng ROW_NUMBER

Viết lại first_seen bằng `ROW_NUMBER() OVER (PARTITION BY actor_id ORDER BY occurred_at, event_id)` rồi `WHERE rn = 1`. So sánh với MIN ngày. Khi nào ROW_NUMBER hữu ích hơn để lấy thêm `channel`?

### Bài 13 — Dữ liệu NULL và định danh rỗng

Thêm một sự kiện actor_id `''` hoặc `'  '`. Với PostgreSQL, COUNT DISTINCT có thể coi đây là những giá trị nào? Nếu chính sách quy định chuỗi rỗng/blank là không định danh, dùng `NULLIF(BTRIM(actor_id),'')` ở bước nào để thống nhất toàn pipeline?

### Bài 14 — MTD unique

Thêm sự kiện của u01 vào tháng 11. Giải thích vì sao u01 **không mới toàn lịch sử** trong tháng 11 nhưng là **một actor duy nhất hoạt động trong tháng 11**. Viết GROUP BY `(month_start, actor_id)` lấy first_day_in_month rồi SUM window PARTITION BY tháng.

### Bài 15 — Multi-tenant

Hai tenant có cùng actor_id `'u01'` nhưng là hai khách khác nhau. Khi báo cáo distinct toàn hệ thống, phải dùng khóa nào? Hãy viết CTE `first_seen` group theo `(tenant_id, actor_id)` rồi đếm số đối tượng mới theo ngày. Có nên dùng `COUNT(DISTINCT actor_id)` toàn hệ thống khi ID không unique xuyên tenant không?

### Bài 16 — Late arriving event

Ban đầu nhận event của u10 ngày 08/10, sau đó nhận trễ event ngày 02/10. First-seen của u10 thay đổi ra sao? Cần điều chỉnh `new_users` của hai ngày nào và những mốc cumulative nào có thể đổi? Vì sao chỉ append thêm một “người mới” vào 02/10 mà không giảm ngày 08/10 là sai?

### Bài 17 — Exact và approximate

Nếu có hàng tỷ sự kiện, dùng COUNT DISTINCT trực tiếp mỗi ngày sẽ tốn tài nguyên. Hãy đề xuất bảng `actor_first_seen` có khóa duy nhất và cách xây dựng `daily_new`. Khi nào có thể chấp nhận distinct xấp xỉ? Vì sao không được SUM những ước lượng distinct theo ngày để suy ra distinct của toàn kỳ?

### Bài 18 — Báo cáo đối chiếu

Viết một truy vấn cuối kỳ so sánh:

1. `COUNT(DISTINCT actor_id)` từ bảng raw;
2. `COUNT(*)` trên CTE first_seen;
3. Tổng `new_users` theo ngày;
4. Giá trị cumulative tại ngày cuối.

Với cùng phạm vi và chính sách, cả bốn phải cùng bằng **8** trong bộ dữ liệu mẫu. Nếu khác nhau, hãy trình bày thứ tự tìm nguyên nhân: timezone, bộ lọc, ID NULL, lịch sử trước kỳ, JOIN và data freshness.

## 25. Sơ đồ tư duy truy vấn chuẩn

```text
             RAW EVENTS
      (nhiều sự kiện / actor)
                  |
                  v
      Chuẩn hóa actor_id, event_day
      theo timezone & chính sách lọc
                  |
                  v
       GROUP BY actor_id
       MIN(event_day) AS first_day
                  |
                  v
       FIRST-SEEN: 1 hàng / actor
                  |
                  v
       GROUP BY first_day
       COUNT(*) AS new_users
                  |
                  +----------------------+
                  |                      |
                  v                      v
       Calendar spine             Baseline trước kỳ
       đủ các ngày báo cáo        (nếu all-time từ giữa lịch sử)
                  |                      |
                  v                      |
       LEFT JOIN new_users             |
       COALESCE ngày rỗng = 0          |
                  |                      |
                  +----------+-----------+
                             |
                             v
                   SUM(new_users) OVER (
                       ORDER BY report_day
                       ROWS BETWEEN
                         UNBOUNDED PRECEDING
                         AND CURRENT ROW
                   ) + baseline
                             |
                             v
                  CUMULATIVE UNIQUE USERS
```

## 26. Kết luận

**Đếm tích lũy số đối tượng duy nhất theo thời gian** không phải là phép cộng đơn giản các số `COUNT(DISTINCT ...)` từng ngày. Mỗi ngày có thể chứa người đã xuất hiện ở ngày khác, nên cộng các số distinct theo ngày sẽ **đếm lặp**. Mẫu SQL rõ nghĩa là **xác định ngày xuất hiện đầu tiên của mỗi ID**, đếm số ID mới ở từng ngày và **cộng dồn các ID mới** bằng window SUM.

Để kết quả đáng tin, hãy xác định rõ **đối tượng cần đếm, khóa định danh, sự kiện đủ điều kiện, mốc bắt đầu tích lũy và múi giờ báo cáo**. Dùng calendar khi cần hiển thị ngày không có người mới; dùng baseline nếu chỉ trình bày một phần của lịch sử all-time; phân biệt ever-seen, MTD unique, DAU và rolling 7-day distinct. Khi phân nhóm theo kênh hoặc tenant, không cộng distinct của các nhóm giao nhau như thể đó là distinct toàn hệ thống.

Ở hệ thống lớn, có thể duy trì bảng first-seen và cập nhật số mới theo ngày, nhưng cần xử lý **dữ liệu tới trễ, thay đổi định danh và phiên bản dữ liệu**. Truy vấn lũy kế chỉ đúng khi tập ID đầu vào và ngày đầu tiên đúng. Khi đó, mỗi đối tượng đóng góp **một lần duy nhất**, và đường tích lũy thực sự phản ánh số đối tượng mà hệ thống đã từng ghi nhận đến từng mốc thời gian.
