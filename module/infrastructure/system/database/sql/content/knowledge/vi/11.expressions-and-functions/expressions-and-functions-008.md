# CURRENT_DATE, CURRENT_TIMESTAMP và thời điểm đánh giá trong SQL

Hai biểu thức `CURRENT_DATE` và `CURRENT_TIMESTAMP` thường xuất hiện trong câu truy vấn, giá trị mặc định của cột, điều kiện lọc theo thời gian và quy tắc hết hạn. Chúng trông giống những hằng số “ngày hôm nay” và “thời điểm hiện tại”, nhưng thực chất là **biểu thức phụ thuộc ngữ cảnh thực thi**. Kết quả chịu ảnh hưởng của **thời điểm DBMS đánh giá**, **múi giờ** và **phương ngữ SQL**.

Chẳng hạn, một giao dịch mở lúc 23:59 và thực hiện thêm lệnh sau nửa đêm có thể vẫn nhận cùng `CURRENT_TIMESTAMP` trong PostgreSQL. Trong khi đó, nhiều hệ quản trị khác lấy mốc thời gian của từng câu lệnh hoặc đọc đồng hồ hệ thống theo quy tắc riêng. Nếu dùng “hiện tại” để kiểm tra hạn sử dụng, đo thời gian chạy hoặc phân nhóm đơn hàng theo ngày, khác biệt này có thể làm kết quả không như mong đợi.

Bài học giải thích ý nghĩa hai biểu thức, phân biệt **thời điểm bắt đầu giao dịch**, **thời điểm bắt đầu câu lệnh** và **đồng hồ thực tế**, đồng thời hướng dẫn áp dụng trong `SELECT`, `WHERE`, `INSERT` và các ràng buộc nghiệp vụ. Ví dụ chính dùng PostgreSQL; những điểm khác ở MySQL/MariaDB, SQL Server, Oracle và SQLite được trình bày riêng.

> Không giả định mọi DBMS triển khai `CURRENT_DATE` và `CURRENT_TIMESTAMP` theo cùng quy tắc. Kiểu dữ liệu trả về, độ chính xác, múi giờ mặc định và mốc đánh giá có thể khác giữa sản phẩm, phiên bản và cấu hình kết nối.

## 1. Hai câu hỏi: “Ngày nào?” và “Thời điểm nào?”

### 1.1. `CURRENT_DATE`: ngày hiện tại trong ngữ cảnh thời gian của DBMS

`CURRENT_DATE` diễn tả **ngày lịch hiện tại** theo quy tắc của hệ quản trị. Trên PostgreSQL, nó trả về giá trị kiểu `DATE` và được xác định từ **thời điểm bắt đầu giao dịch** trong **múi giờ của phiên làm việc**.

```sql
-- PostgreSQL
SELECT CURRENT_DATE AS today;
```

Ví dụ nếu phiên làm việc đang ở múi giờ `Asia/Ho_Chi_Minh` và thời điểm bắt đầu giao dịch nằm trong ngày 2026-11-14 tại múi giờ đó, kết quả sẽ là:

```text
today
----------
2026-11-14
```

Đây là ví dụ giả định để hiểu định dạng, không phải cam kết kết quả khi chạy bài học. Giá trị thực phụ thuộc thời điểm chạy.

`CURRENT_DATE` rất hữu ích cho những trường chỉ cần ngày, như ngày làm việc, ngày đến hạn, ngày sinh nhật hoặc ngày của một báo cáo. Nó **không chứa giờ, phút, giây hay thông tin múi giờ** trong chính giá trị `DATE`.

### 1.2. `CURRENT_TIMESTAMP`: giá trị ngày giờ hiện tại theo DBMS

`CURRENT_TIMESTAMP` diễn tả thông tin **ngày và giờ hiện tại**, thường có cả phần nhỏ của giây và ngữ nghĩa múi giờ tùy hệ quản trị.

```sql
-- PostgreSQL
SELECT CURRENT_TIMESTAMP AS current_instant;
```

Ví dụ kết quả khi phiên PostgreSQL đặt múi giờ `Asia/Ho_Chi_Minh`:

```text
current_instant
--------------------------------
2026-11-14 09:30:15.123456+07
```

Trên PostgreSQL, biểu thức này có kiểu `TIMESTAMP WITH TIME ZONE` (viết ngắn `TIMESTAMPTZ`), và giá trị thể hiện **một thời điểm tuyệt đối**. Phần `+07` là cách phiên hiện tại hiển thị theo múi giờ, không có nghĩa PostgreSQL lưu nguyên tên múi giờ gốc trong mỗi giá trị.

Không nên xem `CURRENT_TIMESTAMP` là “ngày giờ đang chạy thực tế ở mọi lần gọi”; trong PostgreSQL nó được cố định ở **đầu giao dịch**. Phân biệt này là trọng tâm của bài học.

### 1.3. So sánh nhanh

| Tiêu chí | `CURRENT_DATE` | `CURRENT_TIMESTAMP` |
|---|---|---|
| Ý nghĩa chính | Ngày lịch của ngữ cảnh hiện tại | Ngày giờ/thời điểm hiện tại theo DBMS |
| Thành phần biểu diễn | Năm, tháng, ngày | Ngày, giờ và thường có phần giây |
| Kiểu trong PostgreSQL | `DATE` | `TIMESTAMP WITH TIME ZONE` |
| Phụ thuộc múi giờ phiên? | Có thể, vì cùng một thời điểm rơi vào ngày khác nhau giữa các múi giờ | Có ở cách hiển thị/chuyển đổi; thời điểm tuyệt đối vẫn là một |
| Mốc đánh giá trong PostgreSQL | Bắt đầu giao dịch | Bắt đầu giao dịch |
| Ứng dụng điển hình | `due_on = CURRENT_DATE` | `created_at DEFAULT CURRENT_TIMESTAMP` |

**Ngày lịch** và **thời điểm tuyệt đối** không thay thế nhau. Một đơn hàng được tạo lúc 23:50 ở Việt Nam có thể thuộc ngày UTC khác; một công việc đến hạn ngày mai không nhất thiết có thời hạn chính xác lúc 00:00 UTC.

## 2. Thử trực tiếp trong PostgreSQL

Một câu truy vấn có thể hiển thị cả ngày, timestamp và độ chính xác:

```sql
SELECT
    CURRENT_DATE AS current_day,
    CURRENT_TIMESTAMP AS current_moment,
    CURRENT_TIMESTAMP(3) AS current_moment_ms,
    pg_typeof(CURRENT_DATE) AS date_type,
    pg_typeof(CURRENT_TIMESTAMP) AS timestamp_type;
```

Trong PostgreSQL, `CURRENT_TIMESTAMP(3)` yêu cầu độ chính xác ba chữ số sau dấu thập phân của phần giây; giá trị có thể được làm tròn cho phù hợp. **Độ chính xác hiển thị/lưu trữ không quyết định biểu thức lấy mốc thời gian vào lúc nào.** Chẳng hạn, timestamp có sáu chữ số microsecond vẫn có thể là mốc đầu giao dịch, không phải thời điểm gần nhất khi từng hàng được xử lý.

Các biểu thức theo chuẩn SQL như `CURRENT_DATE` và `CURRENT_TIMESTAMP` thường được viết **không có ngoặc gọi hàm**, nhưng không nên khái quát quy tắc cú pháp đó sang mọi hàm thời gian của các DBMS. Ví dụ PostgreSQL có hàm `now()` với ngoặc và alias `transaction_timestamp()`.

### 2.1. Giá trị kiểu DATE không chứa giờ

```sql
-- PostgreSQL
SELECT
    CURRENT_DATE AS today,
    CURRENT_DATE + 1 AS tomorrow,
    CURRENT_DATE - 7 AS seven_days_ago;
```

Trong PostgreSQL, cộng hoặc trừ số nguyên với `DATE` dịch chuyển theo **số ngày lịch**. Nó không tự biểu diễn “24 giờ chính xác” với mọi múi giờ; ở nơi có thay đổi giờ mùa hè, hai thời điểm nửa đêm liên tiếp có thể cách nhau 23 hoặc 25 giờ.

### 2.2. Lấy phần ngày của CURRENT_TIMESTAMP

```sql
-- PostgreSQL; cả hai cùng dùng ngữ cảnh phiên/giao dịch hiện tại.
SELECT
    CURRENT_DATE AS current_day,
    CURRENT_TIMESTAMP::DATE AS date_from_timestamp;
```

Khi phiên và mốc đánh giá không thay đổi, hai biểu thức có cùng ngày. Tuy nhiên, điều này không có nghĩa nên lưu tất cả thời gian bằng `DATE`: ép `TIMESTAMP` về `DATE` làm mất thông tin giờ, phút, giây và có thể phụ thuộc múi giờ khi giá trị nguồn là `TIMESTAMPTZ`.

## 3. “Thời điểm đánh giá” thực sự là gì?

Cần phân biệt ba mốc:

1. **Bắt đầu giao dịch** (*transaction start*): thời điểm một giao dịch bắt đầu theo cơ chế DBMS. Một giao dịch có thể chứa nhiều câu SQL chạy cách nhau vài phút.
2. **Bắt đầu câu lệnh** (*statement start*): thời điểm một câu SQL được DBMS nhận/bắt đầu xử lý. Trong một giao dịch có thể có nhiều thời điểm bắt đầu câu lệnh.
3. **Đồng hồ tại lúc gọi** (*wall-clock time*): đọc đồng hồ thực tế khi hàm được đánh giá; hai lần gọi có thể khác nhau ngay trong một câu SQL.

Hình dung một giao dịch PostgreSQL mở ra rồi chạy hai câu SQL:

```text
T1: BEGIN;                ← giao dịch bắt đầu
T2: SELECT ...;           ← câu lệnh A bắt đầu
T3: một khoảng thời gian trôi qua
T4: SELECT ...;           ← câu lệnh B bắt đầu
T5: COMMIT;
                       thời gian →
```

Trong cùng một giao dịch PostgreSQL, `CURRENT_TIMESTAMP` tiếp tục biểu diễn mốc **T1**, dù câu lệnh B chạy ở T4. Nếu muốn quan sát mốc câu lệnh B, dùng `statement_timestamp()`; nếu muốn đọc đồng hồ khi hàm được thực thi, dùng `clock_timestamp()`.

**Không nên nhầm “mốc thời gian của giao dịch” với “thời gian CPU xử lý một hàng”.** Hai thứ phục vụ những yêu cầu khác nhau.

## 4. Ba nhóm đồng hồ trong PostgreSQL

PostgreSQL cung cấp các biểu thức/hàm để chọn mốc đánh giá phù hợp.

| Biểu thức/hàm | Ý nghĩa trong PostgreSQL | Có thay đổi giữa hai câu lệnh cùng giao dịch? |
|---|---|---|
| `CURRENT_TIMESTAMP` | Mốc thời gian bắt đầu giao dịch | Không |
| `now()` | Tương đương `transaction_timestamp()` | Không |
| `transaction_timestamp()` | Mốc bắt đầu giao dịch | Không |
| `CURRENT_DATE` | Ngày lịch lấy từ mốc đầu giao dịch theo múi giờ phiên | Thường không nếu múi giờ phiên không đổi |
| `statement_timestamp()` | Mốc bắt đầu câu lệnh hiện hành | Có thể |
| `clock_timestamp()` | Đồng hồ hệ thống tại lúc hàm chạy | Có thể, kể cả trong cùng câu lệnh |

### 4.1. `CURRENT_TIMESTAMP` và `now()` trong cùng giao dịch

```sql
-- PostgreSQL
BEGIN;

SELECT
    CURRENT_TIMESTAMP AS current_ts,
    now() AS now_function,
    transaction_timestamp() AS transaction_ts;

-- Sau một khoảng thời gian, trong cùng giao dịch:
SELECT
    CURRENT_TIMESTAMP AS still_transaction_start,
    statement_timestamp() AS this_statement_start,
    clock_timestamp() AS actual_clock;

COMMIT;
```

Cả `CURRENT_TIMESTAMP`, `now()` và `transaction_timestamp()` biểu diễn mốc bắt đầu giao dịch. Nếu có khoảng cách thời gian đáng kể giữa hai câu lệnh, `statement_timestamp()` và `clock_timestamp()` của câu lệnh sau có thể muộn hơn.

**Lưu ý về cách thử:** các câu trên phải chạy trong **cùng giao dịch trên cùng kết nối**; nếu công cụ SQL tự kết thúc giao dịch sau mỗi câu hoặc bạn chạy từng lệnh trên kết nối khác, sẽ không quan sát được đúng tình huống. Không cần cố ý giữ giao dịch lâu trên cơ sở dữ liệu đang phục vụ người dùng chỉ để thử minh họa.

### 4.2. Cùng một câu lệnh chèn nhiều hàng

```sql
-- PostgreSQL
CREATE TEMP TABLE event_log (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO event_log (event_type)
VALUES ('CREATED'), ('VALIDATED'), ('QUEUED');

SELECT event_id, event_type, created_at
FROM event_log
ORDER BY event_id;
```

Ba hàng được chèn qua cùng câu lệnh; `created_at` lấy mốc đầu giao dịch PostgreSQL, nên có thể **bằng nhau hoàn toàn**. Điều đó không có nghĩa ba sự kiện thực sự diễn ra đồng thời ở độ phân giải tuyệt đối; chúng chỉ dùng cùng **mốc thời gian đã chọn** để ghi dữ liệu.

Nếu chạy nhiều lệnh `INSERT` trong một giao dịch PostgreSQL, các hàng được chèn cũng có thể mang cùng `created_at` mặc dù các lệnh chạy vào thời điểm khác nhau. Đây là hành vi phù hợp với ý nghĩa **timestamp của giao dịch**.

### 4.3. Đầu câu lệnh và đồng hồ thực tế

```sql
-- PostgreSQL
SELECT
    transaction_timestamp() AS transaction_started_at,
    statement_timestamp() AS statement_started_at,
    clock_timestamp() AS observed_at;
```

Trong một truy vấn có nhiều hàng, `clock_timestamp()` có thể thay đổi giữa các lần đánh giá; `statement_timestamp()` giữ mốc của câu lệnh; `transaction_timestamp()` giữ mốc của giao dịch.

Các đồng hồ lấy từ hệ thống có thể bị điều chỉnh bởi đồng bộ thời gian. Vì vậy, nếu cần đo **thời lượng thực thi chính xác/đơn điệu**, việc trừ hai giá trị wall clock trong SQL không mặc nhiên là phương pháp đo tốt nhất; có thể dùng công cụ profiling, `EXPLAIN ANALYZE` hoặc đồng hồ monotonic của môi trường ứng dụng.

### 4.4. Lựa chọn mốc nào cho từng yêu cầu?

| Yêu cầu | Lựa chọn có thể phù hợp trong PostgreSQL | Ý nghĩa |
|---|---|---|
| Gắn cùng mốc tạo cho toàn bộ thay đổi của giao dịch | `CURRENT_TIMESTAMP` | Tất cả dùng transaction time |
| Ghi thời điểm câu lệnh cụ thể được nhận | `statement_timestamp()` | Tách mốc của các câu lệnh trong cùng giao dịch |
| Quan sát đồng hồ hiện tại khi thực hiện logic | `clock_timestamp()` | Có thể thay đổi trong cùng câu lệnh |
| Chọn ngày của giao dịch trong múi giờ phiên | `CURRENT_DATE` | Ngày lịch theo transaction time |
| Kiểm tra “đã hết hạn tính đến lúc thật sự xử lý” trong giao dịch dài | Cân nhắc `clock_timestamp()` hoặc mốc được ứng dụng truyền vào | Tránh nhầm mốc giao dịch với mốc kiểm tra thực tế |

Lựa chọn cuối cùng phụ thuộc vào **định nghĩa nghiệp vụ của “bây giờ”**: “khi giao dịch bắt đầu”, “khi lệnh bắt đầu”, “khi xử lý sự kiện” hay “khi người dùng gửi yêu cầu”. Những mốc này có thể khác nhau ngay trong một hệ thống.

## 5. Múi giờ: một thời điểm có thể thuộc hai ngày khác nhau

Giả sử một thời điểm tuyệt đối là `2026-11-14 18:30:00+00` (UTC). Khi nhìn theo múi giờ Việt Nam (UTC+07) nó trở thành `2026-11-15 01:30:00+07`. Vì vậy, “hôm nay” theo UTC và theo Việt Nam có thể khác nhau.

### 5.1. PostgreSQL: múi giờ phiên làm việc

```sql
-- PostgreSQL: đặt múi giờ cho phiên hiện tại.
SET TIME ZONE 'UTC';

SELECT
    CURRENT_TIMESTAMP AS instant_displayed_in_utc,
    CURRENT_DATE AS date_in_utc;

SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT
    CURRENT_TIMESTAMP AS same_instant_displayed_in_hcm,
    CURRENT_DATE AS date_in_hcm;
```

Nếu hai câu lệnh được thực hiện gần nhau trong cùng giao dịch, `CURRENT_TIMESTAMP` là **cùng mốc thời gian tuyệt đối**, nhưng cách hiển thị thay đổi theo `TimeZone`. `CURRENT_DATE` được xác định theo **ngày lịch của mốc đó trong múi giờ phiên**, nên có thể khác nhau khi mốc nằm gần ranh giới ngày.

Nếu các câu lệnh chạy trong những giao dịch riêng, mốc đánh giá cũng có thể khác. Muốn minh họa cùng một mốc hoàn toàn độc lập với thời điểm thực thi, hãy dùng một giá trị `TIMESTAMPTZ` cố định:

```sql
-- PostgreSQL: cùng một thời điểm, hai cách nhìn.
SELECT
    TIMESTAMPTZ '2026-11-14 18:30:00+00'
        AT TIME ZONE 'UTC' AS utc_local_time,
    TIMESTAMPTZ '2026-11-14 18:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS hcm_local_time;
```

Kết quả biểu diễn ngày giờ lần lượt là **2026-11-14 18:30:00** và **2026-11-15 01:30:00**, đều bắt nguồn từ một thời điểm tuyệt đối. Trong PostgreSQL, khi dùng `AT TIME ZONE` với giá trị `TIMESTAMPTZ`, kết quả là `TIMESTAMP WITHOUT TIME ZONE` biểu diễn giờ địa phương được chỉ định.

### 5.2. Múi giờ của database server không luôn là múi giờ của người dùng

Ứng dụng có thể đặt server tại UTC, người dùng tại Việt Nam, còn khách hàng quốc tế có nhiều múi giờ khác nhau. Nếu màn hình báo cáo hỏi “đơn hàng hôm nay” mà SQL chỉ dùng `CURRENT_DATE` của kết nối, kết quả theo **múi giờ kết nối**, chưa chắc theo ngày của người dùng.

Cần làm rõ một trong những quy tắc:

- “Hôm nay theo UTC”: ngày UTC.
- “Hôm nay theo múi giờ của tổ chức”: ngày địa phương theo một tên múi giờ đã lưu.
- “Hôm nay theo người đang đăng nhập”: ngày theo múi giờ được người đó chọn, sau khi xác thực chính sách ứng dụng.
- “Ngày nghiệp vụ”: có thể bắt đầu lúc 06:00 hoặc thời điểm chốt ca thay vì đúng nửa đêm.

Không nên trộn các định nghĩa trên rồi gọi chung là “ngày hiện tại”.

### 5.3. Tên múi giờ quan trọng hơn offset cố định

Một offset như `+07:00` mô tả chênh lệch tại một thời điểm, trong khi tên IANA như `Asia/Ho_Chi_Minh` mô tả quy tắc vùng thời gian. Ở những nơi có giờ mùa hè, cùng một vùng có thể thay đổi offset theo ngày. Nếu cần xử lý lịch địa phương trong thời gian dài hoặc chuyển giờ mùa hè, hãy dùng **tên múi giờ** phù hợp thay vì mã hóa cố định `+02:00` hay `-05:00` cho toàn bộ năm.

## 6. Lọc dữ liệu “hôm nay”: không đánh đồng DATE với TIMESTAMP

Một yêu cầu rất phổ biến:

> Lấy tất cả đơn hàng được tạo trong ngày hiện tại theo múi giờ của hệ thống.

Giả sử `orders.created_at` là `TIMESTAMPTZ` trong PostgreSQL.

### 6.1. Vì sao so sánh bằng CURRENT_DATE có thể sai ý định?

```sql
-- Không phù hợp để diễn tả "mọi thời điểm trong ngày":
SELECT order_id
FROM orders
WHERE created_at = CURRENT_DATE;
```

`CURRENT_DATE` là một ngày; khi so sánh với timestamp, DBMS có thể ép về thời điểm **nửa đêm** theo quy tắc kiểu và múi giờ. Vì vậy câu trên không chọn tất cả các đơn hàng được tạo lúc 08:00, 12:30 hay 23:59 của cùng ngày.

Có thể viết:

```sql
-- PostgreSQL: đúng về ý nghĩa "ngày hiển thị theo múi giờ phiên",
-- nhưng áp dụng ép kiểu trên từng giá trị cột.
SELECT order_id
FROM orders
WHERE created_at::DATE = CURRENT_DATE;
```

Cách này đọc dễ hiểu, song ép kiểu trên cột có thể khiến chỉ mục B-tree thông thường trên `created_at` khó được sử dụng trực tiếp cho điều kiện đó. Với bảng lớn, nên dùng **khoảng thời gian nửa mở**.

### 6.2. Khoảng `[đầu ngày, đầu ngày kế tiếp)`

```sql
-- PostgreSQL, tính theo múi giờ của phiên.
SELECT order_id, created_at
FROM orders
WHERE created_at >= CURRENT_DATE::TIMESTAMPTZ
  AND created_at <  (CURRENT_DATE + 1)::TIMESTAMPTZ
ORDER BY created_at, order_id;
```

Ý nghĩa:

- Cận dưới `>=` lấy từ **nửa đêm đầu ngày hiện tại**.
- Cận trên `<` loại **nửa đêm đầu ngày kế tiếp**.
- Không bỏ sót các giá trị 23:59:59.999... chỉ vì giới hạn độ phân giải của timestamp.
- Có cơ hội dùng chỉ mục theo khoảng trên `created_at`, tùy kế hoạch DBMS.
- Hai cận được chuyển từ **ngày lịch** sang `TIMESTAMPTZ` trong múi giờ phiên.

Không nên viết `BETWEEN midnight AND next_midnight` nếu mục tiêu là **một ngày duy nhất**, vì `BETWEEN` bao gồm cả hai cận và sẽ tính thêm đúng thời điểm 00:00 của ngày kế tiếp.

### 6.3. Khi người dùng chọn múi giờ riêng

Nếu cần “hôm nay theo Asia/Ho_Chi_Minh” nhưng phiên PostgreSQL ở UTC, nên xác định hai cận bằng múi giờ đích và so sánh trên timestamp tuyệt đối:

```sql
-- PostgreSQL: ngày địa phương của cùng mốc giao dịch tại Việt Nam.
WITH local_day AS (
    SELECT
        (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS business_date
),
bounds AS (
    SELECT
        business_date::TIMESTAMP
            AT TIME ZONE 'Asia/Ho_Chi_Minh' AS start_at,
        (business_date + 1)::TIMESTAMP
            AT TIME ZONE 'Asia/Ho_Chi_Minh' AS end_at
    FROM local_day
)
SELECT o.order_id, o.created_at
FROM orders AS o
CROSS JOIN bounds AS b
WHERE o.created_at >= b.start_at
  AND o.created_at <  b.end_at
ORDER BY o.created_at, o.order_id;
```

Ở đây, `business_date` được lấy theo ngày Việt Nam; hai cận được chuyển từ **nửa đêm địa phương** sang các thời điểm tuyệt đối để so sánh với `TIMESTAMPTZ`. Ngay cả ở vùng có đổi giờ mùa hè, chuyển riêng từng nửa đêm theo tên múi giờ giúp thể hiện đúng khoảng ngày lịch hơn cách lấy thời điểm bắt đầu rồi cộng cố định 24 giờ.

**Lưu ý:** `CURRENT_TIMESTAMP` của PostgreSQL vẫn lấy mốc đầu giao dịch. Nếu giao dịch đã mở trước khi ngày mới bắt đầu, “ngày hiện tại” trong truy vấn có thể là **ngày ở đầu giao dịch**. Nếu nghiệp vụ thật sự cần ngày ở lúc câu lệnh chạy, cân nhắc dùng `statement_timestamp()` hoặc mốc khác đã được định nghĩa rõ.

## 7. `CURRENT_DATE` trong kiểm tra hạn và lịch định kỳ

Giá trị kiểu `DATE` rất phù hợp khi nghiệp vụ dùng **ngày lịch**, không yêu cầu chính xác đến giây.

### 7.1. Công việc đến hạn hôm nay hoặc đã quá hạn

```sql
-- PostgreSQL: giả sử tasks có due_on kiểu DATE.
SELECT task_id, title, due_on
FROM tasks
WHERE due_on <= CURRENT_DATE
ORDER BY due_on, task_id;
```

Truy vấn lấy công việc có hạn **trước hoặc trong ngày hiện tại**. Nó không phân biệt đã quá hạn bao nhiêu giờ vì `due_on` không chứa giờ.

Nếu muốn phân loại:

```sql
SELECT
    task_id,
    title,
    due_on,
    CASE
        WHEN due_on IS NULL THEN 'NO_DEADLINE'
        WHEN due_on < CURRENT_DATE THEN 'OVERDUE'
        WHEN due_on = CURRENT_DATE THEN 'DUE_TODAY'
        ELSE 'UPCOMING'
    END AS due_status
FROM tasks;
```

`due_on IS NULL` phải được xử lý riêng nếu nghiệp vụ xem đây là trường hợp chưa có hạn. `NULL` không bằng bất kỳ ngày nào, kể cả `CURRENT_DATE`.

### 7.2. “Hết hạn trong ngày” khác “hết hạn tại một thời điểm”

Xét hai định nghĩa:

- **Ngày hết hạn**: một phiếu ưu đãi hợp lệ tới **hết ngày 2026-11-14** ở múi giờ quy định. Có thể lưu `expires_on DATE` và quy tắc `expires_on >= CURRENT_DATE`.
- **Thời điểm hết hạn**: phiên đăng nhập hết hiệu lực chính xác lúc `2026-11-14 10:30:00+07`. Nên lưu timestamp biểu diễn một thời điểm và so sánh với mốc thời gian được lựa chọn, ví dụ `expires_at > CURRENT_TIMESTAMP`.

```sql
-- Chỉ phù hợp khi expires_at là thời điểm tuyệt đối.
SELECT session_id
FROM user_sessions
WHERE expires_at > CURRENT_TIMESTAMP;
```

Với PostgreSQL, giá trị “bây giờ” này là **đầu giao dịch**. Giao dịch kéo dài có thể xem một phiên chưa hết hạn ở mốc đầu giao dịch dù đồng hồ hiện tại đã vượt hạn. Trong nghiệp vụ xác thực/hết hạn thời gian thực, phải xác định chính xác thời điểm cần kiểm tra và có thể lấy mốc từ ứng dụng hoặc `clock_timestamp()` theo thiết kế.

## 8. Dùng trong `DEFAULT` của cột

Một ứng dụng thường muốn tự ghi ngày giờ tạo bản ghi nếu người gọi không gửi giá trị.

```sql
-- PostgreSQL
CREATE TABLE audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_date DATE NOT NULL DEFAULT CURRENT_DATE
);
```

Khi chèn:

```sql
INSERT INTO audit_events (event_name)
VALUES ('ORDER_SUBMITTED');

SELECT event_id, event_name, created_at, event_date
FROM audit_events;
```

DBMS áp dụng mặc định tại thao tác ghi theo ngữ nghĩa riêng của biểu thức. Trong PostgreSQL, các giá trị thời gian trên dùng mốc giao dịch hiện tại. Điều này hữu ích khi muốn các hàng phát sinh trong một giao dịch chia sẻ cùng thời điểm ghi nhận.

**Không đặt `CURRENT_TIMESTAMP` trong dấu nháy như chuỗi**:

```sql
-- ĐÚNG: biểu thức SQL thời gian.
created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP

-- SAI ý định: chuỗi literal, không phải biểu thức thời gian.
created_at TIMESTAMPTZ DEFAULT 'CURRENT_TIMESTAMP'
```

Đoạn trên là mảnh khai báo cột để so sánh, không phải hai lệnh SQL độc lập chạy được. Chuỗi literal có thể bị DBMS từ chối khi ép sang timestamp hoặc mang nghĩa khác tùy hệ; không nên dùng thay cho biểu thức.

### 8.1. Mặc định tạo bản ghi không tự cập nhật khi sửa

`DEFAULT CURRENT_TIMESTAMP` thường được áp dụng khi **`INSERT` không truyền giá trị cho cột**, không có nghĩa cột sẽ tự đổi mỗi lần chạy `UPDATE`.

```sql
-- PostgreSQL
CREATE TABLE notes (
    note_id BIGINT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

UPDATE notes
SET content = 'Revised content'
WHERE note_id = 1;
```

Câu `UPDATE` trên **không tự đổi `updated_at`** chỉ vì có `DEFAULT`. Có thể cập nhật rõ:

```sql
UPDATE notes
SET content = 'Revised content',
    updated_at = CURRENT_TIMESTAMP
WHERE note_id = 1;
```

Nếu muốn `updated_at` tự đổi ở mọi cập nhật, có thể dùng trigger hoặc cơ chế riêng của DBMS/ORM. Chọn mốc `CURRENT_TIMESTAMP`, `statement_timestamp()` hay `clock_timestamp()` dựa trên ý nghĩa muốn ghi: thời điểm giao dịch, câu lệnh hay đồng hồ thực tế.

MySQL còn có khả năng khai báo tự động cập nhật timestamp theo cú pháp `ON UPDATE CURRENT_TIMESTAMP` cho kiểu cột được hỗ trợ; đây **không phải cú pháp PostgreSQL tương đương trực tiếp**.

### 8.2. Thời điểm của sự kiện và thời điểm ghi cơ sở dữ liệu

Giả sử dịch vụ nhận một sự kiện lúc 09:00, hàng đợi xử lý đến 09:10 mới ghi DB. Nếu cột `occurred_at` dùng `DEFAULT CURRENT_TIMESTAMP`, nó có thể biểu diễn **lúc ghi DB** thay vì **lúc sự kiện xảy ra**.

Một thiết kế rõ ràng có thể dùng hai cột:

```sql
-- PostgreSQL
CREATE TABLE incoming_events (
    event_id BIGINT PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload TEXT NOT NULL
);
```

`occurred_at` được nguồn sự kiện/ứng dụng truyền vào theo hợp đồng thời gian; `recorded_at` biểu diễn mốc ghi nhận phía DB. Hai cột phục vụ hai câu hỏi khác nhau và không nên bị gộp chỉ vì cùng mang kiểu timestamp.

## 9. Thời gian trong giao dịch dài: một tình huống dễ gây bất ngờ

Giả sử PostgreSQL bắt đầu giao dịch vào 23:59:50 theo múi giờ phiên. Đến 00:00:10 hôm sau, cùng giao dịch chạy:

```sql
SELECT
    CURRENT_DATE,
    CURRENT_TIMESTAMP,
    statement_timestamp(),
    clock_timestamp();
```

Trong trường hợp này:

- `CURRENT_TIMESTAMP` tiếp tục lấy mốc 23:59:50 của **ngày trước**.
- `CURRENT_DATE` tiếp tục là **ngày của mốc giao dịch** khi múi giờ phiên giữ nguyên.
- `statement_timestamp()` gần mốc câu lệnh sau nửa đêm.
- `clock_timestamp()` lấy đồng hồ lúc được gọi, cũng có thể sau nửa đêm.

Nếu một tác vụ ban đêm dùng `CURRENT_DATE` để chọn “công việc hôm nay” trong giao dịch dài, nó có thể tiếp tục chọn **ngày hôm qua** sau khi đồng hồ đã qua nửa đêm.

Đây không phải lỗi của `CURRENT_DATE`: biểu thức thực hiện đúng hợp đồng về thời điểm đánh giá. Cần xác định lại yêu cầu: muốn **ngày ở đầu giao dịch** hay **ngày ở lúc kiểm tra**? Cách giải quyết có thể là dùng giao dịch ngắn hơn, mốc câu lệnh, truyền mốc thời gian từ ứng dụng, hoặc tách xử lý theo kỳ lịch rõ ràng.

**Lưu ý:** “snapshot dữ liệu theo mức cô lập” và “mốc thời gian của CURRENT_TIMESTAMP” là hai khái niệm khác nhau. Không nên suy từ cùng timestamp rằng tất cả truy vấn trong một giao dịch chắc chắn nhìn thấy cùng tập bản ghi; khả năng nhìn thấy dữ liệu còn tùy mức cô lập của giao dịch.

## 10. Khác biệt giữa các hệ quản trị cơ sở dữ liệu

Các tên hàm có thể giống nhau nhưng thời điểm đánh giá, múi giờ và kiểu trả về khác nhau. Bảng sau giúp nhận diện điểm cần tra cứu khi chuyển phương ngữ:

| Hệ quản trị | Ngày hiện tại | Ngày giờ hiện tại | Điểm khác biệt đáng lưu ý |
|---|---|---|---|
| **PostgreSQL** | `CURRENT_DATE` | `CURRENT_TIMESTAMP`, `now()` | Dựa vào **đầu giao dịch**; có `statement_timestamp()` và `clock_timestamp()` để chọn mốc khác. `CURRENT_TIMESTAMP` là `TIMESTAMPTZ`. |
| **MySQL/MariaDB** | `CURRENT_DATE`, `CURDATE()` | `CURRENT_TIMESTAMP`, `NOW()` | `NOW()` và các tên tương đương thường được cố định theo **mốc bắt đầu câu lệnh**, không giữ chung mốc đầu giao dịch như PostgreSQL; múi giờ phiên ảnh hưởng hiển thị. |
| **SQL Server** | Thường lấy ngày bằng `CAST(GETDATE() AS date)` hoặc biểu thức ngày tương đương theo phiên bản | `CURRENT_TIMESTAMP`, `GETDATE()` | `CURRENT_TIMESTAMP` là tương đương với `GETDATE()`, dựa trên đồng hồ hệ thống và không có ngữ nghĩa cố định đầu giao dịch như PostgreSQL; `SYSDATETIME()`/`SYSUTCDATETIME()` có độ chính xác cao hơn và ngữ cảnh khác. |
| **Oracle Database** | `CURRENT_DATE` | `CURRENT_TIMESTAMP` | `CURRENT_DATE` trả về kiểu `DATE` của Oracle (có cả thành phần giờ) theo **múi giờ phiên**; `CURRENT_TIMESTAMP` có thông tin múi giờ phiên. `SYSDATE`/`SYSTIMESTAMP` dùng đồng hồ của môi trường DB. |
| **SQLite** | `CURRENT_DATE` | `CURRENT_TIMESTAMP` | Các giá trị hiện tại thường được cung cấp như **chuỗi ngày/giờ UTC**; không có cùng hệ kiểu ngày/giờ bản địa như PostgreSQL. Các lời gọi thời gian “now” được đảm bảo ổn định trong một lần `sqlite3_step()`, không nên suy thành hợp đồng transaction timestamp. |

Bảng này trình bày **khác biệt thực dụng** chứ không áp đặt một quy tắc ISO duy nhất cho mọi hệ. Đặc biệt, phiên bản mới có thể bổ sung biểu thức/hàm hoặc cú pháp. Khi thiết kế ứng dụng có hỗ trợ nhiều DBMS, hãy xác nhận tài liệu theo **đúng phiên bản**, đặc biệt với độ chính xác phần giây, xử lý múi giờ và cơ chế transaction/statement evaluation.

### 10.1. PostgreSQL: các mốc thời gian được đặt tên rõ

```sql
SELECT
    CURRENT_DATE,
    CURRENT_TIMESTAMP,
    now(),
    transaction_timestamp(),
    statement_timestamp(),
    clock_timestamp();
```

Đây là phương ngữ dễ quan sát sự khác nhau giữa ba mốc. Trong ứng dụng cần nhất quán một thời điểm, việc dùng cùng `CURRENT_TIMESTAMP` trong giao dịch có thể là lợi thế; trong yêu cầu đọc thời gian thực, phải xem lại mốc đó có đủ mới không.

### 10.2. MySQL/MariaDB: `NOW()` thường là mốc đầu câu lệnh

```sql
-- MySQL / MariaDB
SELECT
    CURRENT_DATE AS today,
    CURDATE() AS today_via_function,
    CURRENT_TIMESTAMP AS current_datetime,
    NOW() AS now_value,
    UTC_TIMESTAMP() AS utc_datetime;
```

Các biểu thức `CURRENT_TIMESTAMP` và `NOW()` thường trả ngày giờ theo múi giờ phiên và có mốc nhất quán trong cùng câu lệnh. `UTC_TIMESTAMP()` biểu diễn ngày giờ UTC theo hợp đồng hàm của MySQL, phù hợp khi thực sự muốn lấy UTC thay vì ngày giờ phiên.

MySQL cũng có `SYSDATE()` với hành vi lấy thời gian thực thi khác `NOW()`; một số cấu hình như tùy chọn liên quan đến `SYSDATE` có thể ảnh hưởng hành vi. Không xem mọi hàm tên “current” là đồng nghĩa nếu yêu cầu độ chính xác thời gian đánh giá cao.

### 10.3. SQL Server: `CURRENT_TIMESTAMP` là alias của `GETDATE()`

```sql
-- SQL Server / T-SQL
SELECT
    CURRENT_TIMESTAMP AS current_server_datetime,
    GETDATE() AS getdate_value,
    SYSDATETIME() AS high_precision_datetime,
    SYSUTCDATETIME() AS high_precision_utc,
    CAST(GETDATE() AS date) AS today_from_server_clock;
```

Trong SQL Server, `CURRENT_TIMESTAMP`/`GETDATE()` sử dụng kiểu `datetime` với độ chính xác hữu hạn; `SYSDATETIME()` và `SYSUTCDATETIME()` trả kiểu `datetime2` có độ chính xác cao hơn. **Độ chính xác khai báo không đồng nghĩa độ chính xác thực của nguồn đồng hồ.**

Không lấy ví dụ `CURRENT_DATE` của PostgreSQL chạy nguyên xi trên mọi phiên bản T-SQL. Khi cần ngày theo múi giờ khác múi giờ máy chủ, phải thiết kế chuyển đổi rõ ràng, không chỉ dùng `CAST(GETDATE() AS date)`.

### 10.4. Oracle: chú ý kiểu `DATE` chứa cả giờ

```sql
-- Oracle Database
SELECT
    CURRENT_DATE AS session_date_time,
    CURRENT_TIMESTAMP AS session_timestamp,
    SYSDATE AS database_system_date_time,
    SYSTIMESTAMP AS database_system_timestamp
FROM dual;
```

Trong Oracle, kiểu `DATE` có cả giờ, phút, giây. Vì vậy `CURRENT_DATE` **không chỉ chứa ngày** theo nghĩa kiểu `DATE` của PostgreSQL; khi muốn loại phần giờ để so sánh ngày lịch, thường dùng `TRUNC(CURRENT_DATE)` cùng quy tắc nghiệp vụ và cách áp dụng cho cột.

`CURRENT_DATE` và `CURRENT_TIMESTAMP` dựa trên **múi giờ phiên**, trong khi `SYSDATE`/`SYSTIMESTAMP` được gắn với đồng hồ môi trường hệ quản trị. Không nên nghĩ các hàm luôn có cùng múi giờ hoặc kiểu kết quả.

### 10.5. SQLite: các biểu thức CURRENT thường có dạng văn bản UTC

```sql
-- SQLite
SELECT
    CURRENT_DATE AS utc_date_text,
    CURRENT_TIMESTAMP AS utc_timestamp_text,
    date('now') AS date_now_utc,
    datetime('now') AS datetime_now_utc;
```

SQLite thường trả `CURRENT_DATE` dưới dạng chuỗi `YYYY-MM-DD` và `CURRENT_TIMESTAMP` dưới dạng `YYYY-MM-DD HH:MM:SS` theo UTC. Cơ chế lưu ngày/giờ của SQLite phụ thuộc cách biểu diễn (TEXT/REAL/INTEGER) mà ứng dụng lựa chọn. Không diễn giải kết quả chuỗi không có hậu tố múi giờ là “giờ địa phương” chỉ vì nhìn giống timestamp.

Nếu dùng modifier `'localtime'`, kết quả dựa trên môi trường xử lý và cần kiểm soát cẩn thận trong triển khai đa khu vực. Đối với ứng dụng có yêu cầu thời điểm tuyệt đối, nên thống nhất biểu diễn và quy tắc chuyển đổi ngay từ lớp truy cập dữ liệu.

## 11. Biểu thức thời gian và các phép tính khoảng

### 11.1. PostgreSQL: tính khoảng bằng `INTERVAL`

```sql
SELECT
    CURRENT_TIMESTAMP AS now_txn,
    CURRENT_TIMESTAMP + INTERVAL '30 minutes' AS plus_30_minutes,
    CURRENT_TIMESTAMP + INTERVAL '7 days' AS plus_7_days;
```

`INTERVAL` thể hiện khoảng thời gian. Tuy nhiên, **cộng theo ngày lịch và cộng theo số giờ tuyệt đối có thể khác nhau** ở vùng có chuyển giờ mùa hè. Khi tính lịch hẹn vào cùng giờ địa phương của ngày hôm sau, cần mô hình múi giờ và quy tắc lịch, không mặc định cộng đúng 24 giờ là tương đương.

### 11.2. Thời gian hết hạn sau một khoảng

```sql
-- PostgreSQL, ví dụ thời hạn phiên bằng một giờ từ mốc đầu giao dịch.
INSERT INTO user_sessions (session_id, expires_at)
VALUES (1001, CURRENT_TIMESTAMP + INTERVAL '1 hour');
```

Câu trên chỉ hợp lý khi nghiệp vụ xác định “hạn một giờ kể từ mốc giao dịch”. Nếu sự kiện cần bắt đầu tính từ lúc API nhận yêu cầu hoặc lúc đơn hàng thật sự hoàn tất, nên truyền mốc cụ thể hoặc chọn hàm khác đúng ý nghĩa.

### 11.3. Không tự chuyển đổi thời gian qua chuỗi

Việc lưu timestamp dưới dạng văn bản tùy ý như `'14/11/2026 09:30'` có thể gây lỗi định dạng, múi giờ và sắp xếp. Hãy dùng cột kiểu ngày/giờ phù hợp của DBMS mục tiêu (hoặc quy ước lưu có kiểm soát trên hệ như SQLite) và truyền tham số đúng kiểu từ ứng dụng.

Khi so sánh, tránh trộn `DATE`, `TIMESTAMP WITHOUT TIME ZONE` và `TIMESTAMP WITH TIME ZONE` khi chưa hiểu quy tắc ép kiểu. Ví dụ, PostgreSQL có thể diễn giải một timestamp không múi giờ theo múi giờ phiên khi so sánh với `TIMESTAMPTZ`.

## 12. Ảnh hưởng của thời điểm đánh giá đến tính nhất quán dữ liệu

### 12.1. Hai hàng khác nhau có thể có cùng timestamp

Nhiều chương trình dùng `created_at` làm thứ tự sự kiện:

```sql
SELECT event_id, event_name, created_at
FROM audit_events
ORDER BY created_at;
```

Nếu hai hàng có cùng `created_at`, **thứ tự tương đối không được bảo đảm**. Với PostgreSQL, các hàng tạo trong cùng giao dịch thường có timestamp mặc định bằng nhau. Nên thêm khóa phân định nếu cần thứ tự kết quả ổn định:

```sql
SELECT event_id, event_name, created_at
FROM audit_events
ORDER BY created_at, event_id;
```

Điều này chỉ giúp **sắp xếp kết quả có tính xác định** theo khóa. Nó không tự chứng minh thứ tự sự kiện ngoài đời thực khi đồng hồ không đủ độ phân giải hoặc sự kiện đến từ nhiều nguồn. Nếu cần thứ tự xử lý mạnh hơn, có thể cần số thứ tự sự kiện, cơ chế hàng đợi hoặc nguồn thứ tự riêng.

### 12.2. Thời điểm đánh giá và transaction isolation

`CURRENT_TIMESTAMP` của PostgreSQL ổn định trong giao dịch ngay cả khi bạn chạy nhiều câu lệnh; nhưng **tập dữ liệu nhìn thấy được** còn phụ thuộc mức cô lập như `READ COMMITTED` hoặc `REPEATABLE READ`. Không suy ra “cùng timestamp” đồng nghĩa “cùng snapshot” cho mọi mức cô lập.

Tương tự, các timestamp được sinh ở nhiều giao dịch song song không đủ để tạo một thứ tự tuần tự tuyệt đối cho mọi thay đổi, nhất là khi có độ trễ, rollback hoặc đồng hồ giữa nhiều hệ thống không đồng bộ.

### 12.3. Timestamp không tự là bằng chứng thời điểm commit

Ví dụ, giao dịch A mở lúc 09:00, tạo hàng lúc 09:05 và commit lúc 09:10. Với `DEFAULT CURRENT_TIMESTAMP` trong PostgreSQL, giá trị thường là **09:00**, không phải 09:05 hay 09:10.

Nếu hệ thống cần ghi **thời điểm commit** chính xác, cần cơ chế phù hợp với DBMS và hạ tầng theo dõi giao dịch. Không sử dụng mặc định `CURRENT_TIMESTAMP` rồi gọi đó là “commit timestamp” khi chưa kiểm chứng. Trong tài liệu nghiệp vụ nên dùng tên như `created_at`/`recorded_at` phù hợp với hợp đồng thực tế.

## 13. Java và JDBC: chuyển đúng kiểu và múi giờ

Trong ứng dụng Java, cách ánh xạ thường gặp:

| Dữ liệu SQL cần lưu | Kiểu Java thường phù hợp | Ý nghĩa |
|---|---|---|
| Ngày lịch `DATE` | `java.time.LocalDate` | Chỉ ngày, không gắn thời điểm tuyệt đối |
| Thời điểm tuyệt đối với ngữ nghĩa rõ ràng | `java.time.Instant` hoặc `OffsetDateTime` tùy driver/ORM | Một mốc trên trục thời gian |
| Ngày giờ địa phương không múi giờ | `java.time.LocalDateTime` | Chưa đủ để xác định một thời điểm toàn cầu |
| Tên vùng múi giờ | `java.time.ZoneId` trong logic ứng dụng, lưu ID múi giờ ở trường riêng | Phục vụ chuyển đổi giờ địa phương và quy tắc DST |

Ví dụ một thời điểm do ứng dụng cung cấp:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Instant eventTime = Instant.now();
LocalDate localDay = eventTime
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate();
```

`Instant.now()` lấy đồng hồ của **ứng dụng**, trong khi `CURRENT_TIMESTAMP` lấy mốc do **DBMS** định nghĩa. Hai nguồn có thể chênh nhau do đồng bộ đồng hồ, độ trễ truyền dữ liệu hoặc cách chọn mốc đầu giao dịch. Hệ thống phải chủ động chọn **nguồn thời gian đáng tin cậy** cho từng quy tắc.

Driver/JPA có các chi tiết ánh xạ riêng cho PostgreSQL, MySQL, SQL Server...; không mặc định rằng mọi DBMS trả cùng kiểu JDBC chỉ vì dùng từ khóa `CURRENT_TIMESTAMP`. Đặc biệt, cách lưu `LocalDateTime` khác với cách lưu `Instant` khi cần xử lý múi giờ.

## 14. Lựa chọn theo tình huống thực tế

| Tình huống | Biểu thức/thiết kế gợi ý | Lý do |
|---|---|---|
| Ngày tạo phiếu công việc chỉ phục vụ phân nhóm theo ngày | `CURRENT_DATE` với `DATE` và múi giờ nghiệp vụ được xác định | Không cần phần giờ |
| Ghi mốc tạo hàng trong một giao dịch PostgreSQL | `DEFAULT CURRENT_TIMESTAMP` | Cùng timestamp đầu giao dịch |
| Ghi mốc bắt đầu từng câu lệnh trong PostgreSQL | `statement_timestamp()` | Không bị giữ ở đầu giao dịch dài |
| Lấy thời gian hệ thống ngay tại lúc kiểm tra trong PostgreSQL | `clock_timestamp()` khi nghiệp vụ thực sự cần | Đọc đồng hồ lúc đánh giá |
| Đơn hàng trong ngày hiện tại | Khoảng `>= start_of_day` và `< next_start_of_day` | Bao phủ ngày mà không phụ thuộc chính xác phần giây |
| Hạn phiên đăng nhập đến chính xác một mốc | Cột timestamp biểu diễn thời điểm và phép so sánh theo mốc đã chọn | Không gộp ngày lịch với thời điểm |
| Lịch lặp lại 09:00 tại một vùng | Lưu ngày/giờ địa phương cộng `ZoneId` hoặc quy tắc vùng phù hợp | Xử lý DST và tính kỳ lặp |
| Trật tự các sự kiện | Timestamp cộng khóa/số thứ tự thích hợp | Timestamp có thể trùng, không tự là số thứ tự |
| Sự kiện đến muộn qua hàng đợi | Tách `occurred_at` và `recorded_at` | Phân biệt lúc xảy ra và lúc ghi DB |

Nhìn chung, cần đặt câu hỏi trước khi viết SQL: **“Bây giờ” theo múi giờ nào, tại mốc nào và dùng cho quyết định nghiệp vụ gì?** Sau đó mới chọn `CURRENT_DATE`, `CURRENT_TIMESTAMP` hay một hàm/mốc thời gian khác.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng `CURRENT_TIMESTAMP` luôn thay đổi mỗi lần gọi | Hiểu sai thời điểm ghi trong PostgreSQL | Phân biệt transaction, statement và wall clock |
| Cho rằng `CURRENT_DATE` luôn bằng “ngày hôm nay” của người dùng | Báo cáo sai ngày gần nửa đêm hoặc khi khác múi giờ | Chọn múi giờ nghiệp vụ rõ ràng |
| Dùng `created_at = CURRENT_DATE` để lấy cả ngày | Có thể chỉ khớp đúng nửa đêm | Dùng khoảng ngày nửa mở |
| Dùng `BETWEEN start AND next_midnight` cho một ngày | Lấy cả thời điểm đầu ngày kế tiếp | Dùng `>= start AND < next_start` |
| Coi `TIMESTAMPTZ` là kiểu giữ nguyên tên múi giờ nhập | Mất thông tin vùng múi giờ gốc | Lưu `ZoneId` riêng khi nghiệp vụ cần |
| Dùng `CURRENT_TIMESTAMP` để đo thời lượng câu SQL trong PostgreSQL | Hai lần đọc trong giao dịch có thể bằng nhau | Dùng công cụ profiling/đồng hồ phù hợp |
| Dùng `DEFAULT CURRENT_TIMESTAMP` rồi kỳ vọng `updated_at` tự đổi | Không tự cập nhật khi `UPDATE` | Cập nhật tường minh, trigger hoặc chức năng DBMS |
| Dùng timestamp làm khóa thứ tự duy nhất | Các hàng có cùng thời điểm không có thứ tự xác định | Bổ sung khóa phụ/số thứ tự |
| Nghĩ `CURRENT_DATE` của Oracle giống `DATE` của PostgreSQL | Bỏ sót phần giờ trong Oracle `DATE` | Kiểm tra kiểu và dùng phép chuyển đổi đúng |
| Nghĩ SQLite CURRENT_TIMESTAMP trả timestamp có múi giờ kiểu PostgreSQL | Sai kiểu và giả định hiển thị | Hiểu chuỗi UTC/biểu diễn thời gian của SQLite |
| Viết hàm thời gian của một phương ngữ cho mọi hệ | Lỗi cú pháp hoặc hành vi khác | Tách SQL theo DBMS/phiên bản hoặc dùng API hỗ trợ |
| Coi thời điểm tạo hàng là thời điểm sự kiện/commit | Sai dòng thời gian khi có hàng đợi/giao dịch dài | Định nghĩa và lưu các mốc riêng khi cần |

## 16. Bài tập tự luyện

### Bài 1. Nhận diện kiểu và ý nghĩa

**Câu hỏi:** Trong PostgreSQL, `CURRENT_DATE` khác `CURRENT_TIMESTAMP` ở những điểm nào?

**Đáp án:** `CURRENT_DATE` là `DATE`, chỉ giữ ngày lịch; `CURRENT_TIMESTAMP` là `TIMESTAMPTZ`, biểu diễn ngày giờ của một thời điểm tuyệt đối. Cả hai dựa trên mốc bắt đầu giao dịch trong PostgreSQL, nhưng `CURRENT_DATE` là cách xác định ngày lịch của mốc đó trong múi giờ phiên.

### Bài 2. Dự đoán giao dịch dài

**Câu hỏi:** PostgreSQL mở giao dịch lúc 10:00; đến 10:05 chạy `SELECT CURRENT_TIMESTAMP, statement_timestamp(), clock_timestamp()`. Giá trị nào chắc chắn tiếp tục là mốc 10:00 theo quy tắc nêu trong bài?

**Đáp án:** `CURRENT_TIMESTAMP`. `statement_timestamp()` lấy mốc câu lệnh khoảng 10:05; `clock_timestamp()` lấy đồng hồ lúc gọi. Trong thực tế giá trị hiển thị còn phụ thuộc độ phân giải và múi giờ, nhưng ý nghĩa mốc không thay đổi.

### Bài 3. Lấy đơn hàng trong ngày

**Yêu cầu:** PostgreSQL có `orders(created_at TIMESTAMPTZ)`. Viết bộ lọc lấy tất cả đơn hàng trong ngày hiện tại theo múi giờ của phiên, không bao gồm nửa đêm ngày sau.

**Đáp án:**

```sql
SELECT *
FROM orders
WHERE created_at >= CURRENT_DATE::TIMESTAMPTZ
  AND created_at <  (CURRENT_DATE + 1)::TIMESTAMPTZ;
```

Phép so sánh dùng khoảng nửa mở và chuyển hai cận ngày thành timestamp trong múi giờ phiên.

### Bài 4. Giá trị mặc định không tự cập nhật

**Câu hỏi:** Có cột `updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP`. Sau khi chạy `UPDATE table_name SET name = 'X' ...`, `updated_at` có tự thay đổi không?

**Đáp án:** không mặc định. `DEFAULT` dùng khi cần điền giá trị ở thao tác ghi ban đầu (hoặc khi dùng `DEFAULT` tường minh tùy cú pháp), không phải cơ chế tự động sửa trên mọi `UPDATE`. Cần cập nhật cột rõ ràng, trigger hoặc cơ chế chuyên biệt của DBMS.

### Bài 5. Hai múi giờ, hai ngày

**Câu hỏi:** Một sự kiện xảy ra lúc `2026-11-14 18:30 UTC`. Sự kiện thuộc ngày nào theo `Asia/Ho_Chi_Minh`?

**Đáp án:** `2026-11-15` vì giờ địa phương lúc đó là `01:30` ngày kế tiếp. Nếu báo cáo nhóm “hôm nay” theo Việt Nam thì phải dùng ranh giới ngày Việt Nam; không thể lấy ngày UTC và coi nó là ngày Việt Nam.

### Bài 6. Chọn mốc thời gian đúng

**Tình huống:** Dịch vụ nhận thông báo lúc 09:00 nhưng đến 09:12 mới ghi xuống DB. Cần thống kê độ trễ xử lý.

**Đáp án:** lưu hai mốc riêng: `occurred_at` từ nguồn sự kiện (09:00) và `recorded_at` lúc ghi nhận (09:12 theo mốc DB/ứng dụng được quy định). Chỉ một cột `DEFAULT CURRENT_TIMESTAMP` không đủ để biết sự kiện thực sự xảy ra lúc nào.

### Bài 7. Đọc SQL giữa các hệ

**Câu hỏi:** Có thể giả định `CURRENT_TIMESTAMP` trong PostgreSQL và `CURRENT_TIMESTAMP` của SQL Server luôn là cùng một kiểu và cùng mốc thời gian không?

**Đáp án:** không. Trong PostgreSQL nó là `TIMESTAMPTZ` và ổn định ở đầu giao dịch. Trong SQL Server nó tương đương `GETDATE()`, trả kiểu `datetime` theo ngữ nghĩa đồng hồ hệ thống của SQL Server. Cần lựa chọn và ánh xạ kiểu/mốc theo DBMS cụ thể.

## Kết luận

`CURRENT_DATE` giải quyết câu hỏi **ngày lịch nào**, còn `CURRENT_TIMESTAMP` diễn đạt **ngày giờ/thời điểm nào** theo ngữ nghĩa của DBMS. Độ chính xác phần giây không đủ để định nghĩa “hiện tại”: cần biết **múi giờ** và đặc biệt là **mốc đánh giá** (đầu giao dịch, đầu câu lệnh hay lúc đọc đồng hồ).

Trong PostgreSQL, `CURRENT_DATE`, `CURRENT_TIMESTAMP` và `now()` gắn với mốc đầu giao dịch; `statement_timestamp()` và `clock_timestamp()` đáp ứng nhu cầu khác. Khi chuyển sang MySQL, SQL Server, Oracle hay SQLite, phải kiểm tra lại kiểu dữ liệu, múi giờ và ngữ nghĩa thời gian. Với báo cáo trong ngày, hãy dùng khoảng nửa mở; với hạn đến từng giây, chọn kiểu timestamp và mốc kiểm tra phù hợp; với dữ liệu nghiệp vụ, phân biệt rõ lúc sự kiện xảy ra, lúc ghi DB và lúc commit. Những quyết định này giúp truy vấn thời gian chính xác và dễ dự đoán trong ứng dụng thực tế.

