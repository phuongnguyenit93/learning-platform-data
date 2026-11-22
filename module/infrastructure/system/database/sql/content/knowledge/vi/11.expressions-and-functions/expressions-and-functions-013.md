# Biểu thức có tính xác định và hàm phụ thuộc thời điểm

Khi chạy một câu SQL hai lần với cùng đầu vào, ta có luôn nhận được cùng kết quả không? Câu trả lời phụ thuộc vào **biểu thức**, **trạng thái dữ liệu**, **ngữ cảnh phiên làm việc** và **thời điểm truy vấn được đánh giá**.

Ví dụ, `quantity * unit_price` thường cho cùng kết quả khi hai giá trị đầu vào không đổi. Ngược lại, `CURRENT_TIMESTAMP` trả về một mốc thời gian do hệ quản trị xác định; `clock_timestamp()` trong PostgreSQL đọc đồng hồ hiện tại và có thể đổi ngay trong cùng một câu SQL. Nếu đưa hàm thời gian vào điều kiện `WHERE`, tập bản ghi sẽ thay đổi khi thời gian trôi qua, ngay cả khi bảng dữ liệu không có thêm hàng nào.

Khả năng phân biệt hai loại biểu thức này rất quan trọng khi thiết kế **cột mặc định**, **chỉ mục trên biểu thức**, **cột tính toán**, **báo cáo theo kỳ**, **cache**, **câu truy vấn chuẩn bị sẵn** và **kiểm thử có thể lặp lại**.

Bài học thuộc chương **Biểu thức và hàm** của Database SQL. Ví dụ thực hành chính sử dụng **PostgreSQL**. Các hệ quản trị khác có cách phân loại và thời điểm đánh giá hàm khác nhau; không nên giả định `NOW()`, `CURRENT_TIMESTAMP` hoặc tên hàm tương tự có cùng hành vi trên mọi nền tảng.

## 1. Hiểu “có tính xác định” là gì

Một **biểu thức có tính xác định** (*deterministic expression*) là biểu thức mà trong ngữ cảnh được định nghĩa rõ, cùng giá trị đầu vào luôn cho cùng giá trị đầu ra.

Ví dụ:

```sql
SELECT
    2 + 3                       AS addition_result,
    ABS(-12)                    AS absolute_result,
    ROUND(125.456::numeric, 2) AS rounded_result;
```

Các kết quả lần lượt là `5`, `12` và `125.46`. Không có phụ thuộc trực tiếp vào đồng hồ, số ngẫu nhiên hay một hàng dữ liệu khác.

Với bảng bán hàng:

```sql
SELECT
    quantity,
    unit_price,
    quantity * unit_price AS line_amount
FROM order_items;
```

`line_amount` được xác định từ hai giá trị của **chính hàng đang xét**. Nếu `quantity` và `unit_price` của hàng đó không đổi, phép nhân số học với kiểu phù hợp sẽ trả cùng kết quả.

Ngược lại:

```sql
SELECT
    CURRENT_TIMESTAMP AS observed_at,
    RANDOM()          AS random_value;
```

Giá trị thời gian và giá trị ngẫu nhiên phụ thuộc vào ngữ cảnh chạy, nên không thể lấy chúng làm ví dụ về phép tính cố định theo đầu vào hiển thị.

### 1.1. Ba lớp cần phân biệt

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Giá trị đầu vào** | Các cột, tham số và literal có giữ nguyên không? | `price = 100`, `rate = 0.10` |
| **Hành vi hàm** | Hàm có phụ thuộc đồng hồ, ngẫu nhiên, trạng thái phiên hoặc dữ liệu bên ngoài không? | `CURRENT_TIMESTAMP`, `RANDOM()` |
| **Ngữ cảnh truy vấn** | Bảng, transaction, múi giờ, collation, phiên bản hàm có giống nhau không? | `SELECT COUNT(*) FROM orders` thay đổi khi bảng có thêm đơn |

Một hàm có thể xác định theo đầu vào nhưng **câu truy vấn sử dụng nó vẫn thay đổi kết quả** khi dữ liệu bảng thay đổi. Ví dụ, `COUNT(*)` trên bảng đang được ghi liên tục có thể cho kết quả khác ở hai lần chạy; điều đó không có nghĩa phép đếm toán học tự nó ngẫu nhiên.

Cũng cần phân biệt:

- **Kết quả ổn định**: giá trị không đổi trong một phạm vi đã xác định, ví dụ trong một transaction.
- **Kết quả xác định theo đầu vào**: cùng đầu vào và ngữ cảnh phù hợp luôn cho cùng kết quả.
- **Giá trị được lưu**: kết quả đã tính một lần rồi ghi vào bảng; lần đọc sau có thể không chạy lại biểu thức.
- **Thứ tự đánh giá**: engine quyết định khi nào tính biểu thức. Độ ổn định của kết quả không cho phép suy đoán mọi hàm luôn được thực thi theo thứ tự viết.

### 1.2. Cùng giá trị nhưng khác cách đánh giá

Hai cách viết:

```sql
SELECT 100 * (1 - 0.15::numeric);

SELECT 100 * (1 - 0.15::numeric);
```

có cùng kết quả `85.00` nếu ngữ cảnh số học không đổi. Với:

```sql
SELECT CURRENT_TIMESTAMP;
```

hai lần chạy ở **hai transaction khác nhau** thường phản ánh hai mốc thời gian khác nhau trong PostgreSQL. Nhưng khi chạy nhiều lần **trong cùng một transaction**, giá trị `CURRENT_TIMESTAMP` lại không đổi, dù thời gian bên ngoài đã trôi qua.

Vì vậy, không thể chỉ nhìn tên “hàm thời gian” mà kết luận nó thay đổi mỗi lần được gọi.

## 2. PostgreSQL phân loại hàm: IMMUTABLE, STABLE, VOLATILE

PostgreSQL có hệ phân loại mức biến động (*function volatility*) dùng trong định nghĩa hàm và tối ưu truy vấn. Đây là cơ chế quan trọng để hiểu vì sao engine được phép tính trước, tái sử dụng hoặc hạn chế một số biểu thức.

| Phân loại | Cam kết của hàm theo PostgreSQL | Ví dụ thường gặp |
| --- | --- | --- |
| **`IMMUTABLE`** | Cùng đối số luôn cho cùng kết quả, không phụ thuộc ngữ cảnh thay đổi có liên quan | `ABS` trên số, nhiều phép toán số học |
| **`STABLE`** | Cùng đối số cho cùng kết quả trong phạm vi **một câu lệnh**; có thể khác giữa các câu lệnh | `CURRENT_TIMESTAMP`, `statement_timestamp()`, hàm chỉ đọc dữ liệu phù hợp |
| **`VOLATILE`** | Kết quả có thể thay đổi giữa các lần gọi, kể cả trong cùng một câu lệnh; hoặc hàm có tác dụng phụ | `RANDOM()`, `clock_timestamp()`, `nextval(...)` |

Đây là **cam kết ngữ nghĩa** mà người khai báo hàm cung cấp cho PostgreSQL, không đơn thuần là một nhãn trang trí. Bộ tối ưu hóa dựa trên nhãn này để lựa chọn cách đánh giá biểu thức.

### 2.1. IMMUTABLE

Ví dụ số học:

```sql
SELECT
    ABS(-5) AS magnitude,
    ROUND(42.357::numeric, 2) AS rounded;
```

`ABS(-5)` luôn cho `5` và phép làm tròn `NUMERIC` ở ví dụ cho `42.36`, khi kiểu và ngữ nghĩa hàm được giữ nguyên.

PostgreSQL có thể **tính trước** biểu thức sử dụng các hằng số với hàm được khai báo `IMMUTABLE`. Với các biểu thức có thể biến thành giá trị cố định, điều này giúp thực thi hiệu quả hơn.

Một hàm không nên bị khai báo `IMMUTABLE` nếu thực chất phụ thuộc vào:

- Thời gian hiện tại.
- Số ngẫu nhiên hoặc bộ đếm sequence.
- Dữ liệu trong bảng có thể thay đổi.
- Thiết lập phiên, múi giờ hoặc định dạng mà đầu vào hàm không thể hiện đầy đủ.
- Nguồn ngoài có thể thay đổi.

Khai báo sai có thể dẫn đến giá trị cũ được tính trước hoặc tái sử dụng trong execution plan, đặc biệt nguy hiểm khi ứng dụng dùng prepared statement và cache kế hoạch.

### 2.2. STABLE

Một hàm `STABLE` được cam kết trả cùng kết quả với cùng đối số **trong một câu lệnh SQL**. Nó có thể phụ thuộc trạng thái không bất biến mãi mãi, như mốc thời gian do PostgreSQL xác định hoặc dữ liệu quan sát theo snapshot của câu lệnh.

Ví dụ:

```sql
SELECT
    CURRENT_TIMESTAMP AS tx_timestamp,
    statement_timestamp() AS stmt_timestamp;
```

Trong PostgreSQL:

- `CURRENT_TIMESTAMP` đồng nghĩa về giá trị với `transaction_timestamp()` và `now()`.
- `statement_timestamp()` là thời điểm bắt đầu **câu lệnh hiện tại**.
- Các giá trị trên ổn định trong cùng câu lệnh, nhưng phạm vi thời gian mà chúng đại diện không giống nhau.

Một hàm đọc dữ liệu trong bảng có thể được khai báo `STABLE` nếu đáp ứng các yêu cầu của PostgreSQL và không thay đổi dữ liệu. Không tự động coi mọi hàm dùng `SELECT` đều `IMMUTABLE`: kết quả của truy vấn đọc bảng có thể thay đổi giữa các statement/transaction.

### 2.3. VOLATILE

Một hàm `VOLATILE` có thể thay đổi kết quả ở từng lần gọi hoặc có tác dụng phụ, ví dụ cấp số từ sequence.

```sql
SELECT
    RANDOM() AS random_1,
    RANDOM() AS random_2,
    clock_timestamp() AS wall_clock;
```

`RANDOM()` trả số giả ngẫu nhiên; hai cột có thể khác nhau. `clock_timestamp()` đọc thời gian thực ở thời điểm đánh giá và có thể thay đổi ngay trong một câu lệnh dài.

Một sequence trong PostgreSQL:

```sql
CREATE TEMP SEQUENCE demo_seq START WITH 100;

SELECT
    nextval('demo_seq'::regclass) AS first_number,
    nextval('demo_seq'::regclass) AS second_number;
```

Thông thường kết quả là `100` và `101`. `nextval` có tác dụng thay đổi trạng thái sequence, nên không thể xem nó là hàm xác định chỉ từ cùng tên sequence. Những số đã cấp có thể tạo khoảng trống ngay cả khi transaction liên quan bị rollback.

**Lưu ý:** `VOLATILE` không có nghĩa hàm **bắt buộc** phải trả giá trị khác mỗi lần; nó có nghĩa PostgreSQL không được giả định kết quả luôn giống nhau. Hai lần `RANDOM()` vẫn có thể tình cờ trả giá trị gần nhau, và hai lần đọc đồng hồ rất sát nhau có thể có cùng giá trị hiển thị ở độ chính xác nhất định.

## 3. Mốc thời gian trong PostgreSQL: transaction, statement, đồng hồ thực

Hãy tưởng tượng một transaction kéo dài qua nhiều câu lệnh. Có ba câu hỏi khác nhau:

1. **Transaction bắt đầu lúc nào?**
2. **Câu lệnh SQL hiện tại bắt đầu lúc nào?**
3. **Đồng hồ hệ thống hiển thị bao nhiêu tại chính thời điểm hàm được gọi?**

PostgreSQL cung cấp ba nhóm hàm tương ứng:

| Cú pháp PostgreSQL | Mốc thời gian biểu diễn | Hành vi trong transaction dài |
| --- | --- | --- |
| `CURRENT_TIMESTAMP` | Thời điểm bắt đầu transaction hiện tại | Giữ nguyên |
| `now()` | Tương đương `transaction_timestamp()` | Giữ nguyên |
| `transaction_timestamp()` | Thời điểm bắt đầu transaction hiện tại | Giữ nguyên |
| `statement_timestamp()` | Thời điểm bắt đầu câu lệnh SQL hiện tại | Có thể đổi qua từng câu lệnh |
| `clock_timestamp()` | Đồng hồ thực tại lúc đánh giá | Có thể đổi ngay trong cùng câu lệnh |
| `CURRENT_DATE` | Ngày tương ứng thời điểm transaction bắt đầu theo múi giờ phiên | Ổn định trong transaction |
| `LOCALTIME` / `LOCALTIMESTAMP` | Giờ/ngày giờ địa phương không mang thông tin múi giờ, dựa trên thời điểm transaction | Ổn định trong transaction |
| `timeofday()` | Chuỗi văn bản mô tả đồng hồ thực tại lúc gọi | Có thể đổi và không phải kiểu timestamp |

Mấu chốt là **`now()` trong PostgreSQL không đọc “thời gian hiện tại” mới nhất mỗi lần gọi** theo nghĩa đồng hồ thực. Nó trả **thời điểm transaction bắt đầu**.

### 3.1. Minh họa trong một transaction

Chạy từng câu lệnh trong cùng một phiên PostgreSQL:

```sql
BEGIN;

SELECT
    transaction_timestamp() AS transaction_start,
    statement_timestamp() AS statement_start,
    clock_timestamp() AS actual_clock;

-- Có thể thực hiện các công việc khác giữa hai SELECT.

SELECT
    transaction_timestamp() AS transaction_start_again,
    statement_timestamp() AS statement_start_again,
    clock_timestamp() AS actual_clock_again;

COMMIT;
```

Dự kiến:

- `transaction_start` và `transaction_start_again` bằng nhau.
- `statement_start` và `statement_start_again` phản ánh thời điểm bắt đầu hai câu lệnh khác nhau; thông thường chúng khác nhau.
- `actual_clock` và `actual_clock_again` phản ánh lúc thực sự gọi hàm.

Nếu hai `SELECT` chạy rất nhanh, thời gian hiển thị có thể gần nhau; không nên dùng một lần quan sát giá trị làm bằng chứng tuyệt đối cho thời điểm engine tính mỗi phần.

### 3.2. Một câu lệnh với nhiều hàng

```sql
SELECT
    n,
    transaction_timestamp() AS tx_time,
    statement_timestamp() AS stmt_time,
    clock_timestamp() AS wall_time
FROM generate_series(1, 5) AS g(n);
```

`transaction_timestamp()` và `statement_timestamp()` được thiết kế ổn định trong cùng câu lệnh. `clock_timestamp()` có thể đổi giữa các lần được đánh giá cho các hàng khác nhau.

Trên tập năm hàng rất nhỏ, `wall_time` có thể **hiển thị bằng nhau** nếu các lần gọi gần nhau ở độ phân giải đầu ra. Điểm cần hiểu là nó **không có cam kết ổn định** như hai hàm còn lại.

### 3.3. Sơ đồ thời điểm

```text
t0                 t1                    t2              t3
|------------------|---------------------|---------------|
BEGIN             SELECT A              SELECT B         COMMIT

transaction_timestamp()  ─────── t0 trong cả A và B ───────
statement_timestamp()            t1 ở A; t2 ở B
clock_timestamp()                đọc đồng hồ tại từng lần gọi
```

Khi một transaction dài vài phút, `CURRENT_TIMESTAMP` trong các câu lệnh cuối vẫn có thể chỉ thời điểm vài phút trước. Điều này có ý nghĩa lớn đối với tính toán hạn xử lý, log thời gian và quy tắc “gần đây”.

## 4. Dữ liệu mẫu để đối chiếu biểu thức thời gian

Để bài tập có kết quả cố định, không dùng thời gian máy đang chạy làm mốc kiểm chứng. Ta tạo bảng chứa sự kiện và một **mốc thời gian tham chiếu** do bài học quy định.

```sql
CREATE TEMP TABLE demo_activity (
    event_id    INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    status      TEXT NOT NULL
        CHECK (status IN ('success', 'pending', 'failed'))
);

INSERT INTO demo_activity
    (event_id, user_id, occurred_at, status)
VALUES
    (1, 10, TIMESTAMPTZ '2025-05-10 10:45:00+00', 'success'),
    (2, 10, TIMESTAMPTZ '2025-05-10 11:20:00+00', 'success'),
    (3, 11, TIMESTAMPTZ '2025-05-10 11:59:00+00', 'pending'),
    (4, 12, TIMESTAMPTZ '2025-05-10 12:00:00+00', 'success'),
    (5, 12, TIMESTAMPTZ '2025-05-10 12:15:00+00', 'success'),
    (6, 13, TIMESTAMPTZ '2025-05-09 11:30:00+00', 'success'),
    (7, 14, TIMESTAMPTZ '2025-05-10 09:30:00+00', 'failed');
```

Quy ước mốc tham chiếu:

```sql
SELECT TIMESTAMPTZ '2025-05-10 12:00:00+00' AS as_of;
```

**`as_of` không phải thời gian hiện tại của hệ thống**. Đây là giá trị cố định giúp người học tự tính kết quả trên giấy và nhận cùng đáp án dù chạy bài hôm nay, ngày mai hoặc ở máy khác.

Dữ liệu:

| Sự kiện | Thời gian UTC | Trạng thái | Ý nghĩa so với `as_of` |
| ---: | --- | --- | --- |
| 1 | 2025-05-10 10:45 | success | Trước mốc 75 phút |
| 2 | 2025-05-10 11:20 | success | Trước mốc 40 phút |
| 3 | 2025-05-10 11:59 | pending | Trước mốc 1 phút |
| 4 | 2025-05-10 12:00 | success | Bằng mốc |
| 5 | 2025-05-10 12:15 | success | Sau mốc 15 phút |
| 6 | 2025-05-09 11:30 | success | Trước mốc 24 giờ 30 phút |
| 7 | 2025-05-10 09:30 | failed | Trước mốc 150 phút |

Trong PostgreSQL, `TIMESTAMPTZ` lưu thời điểm tuyệt đối; khi `SELECT`, cách hiển thị ngày giờ phụ thuộc múi giờ của phiên kết nối. Các mốc ở bảng trên được viết theo UTC để dễ đối chiếu.

## 5. Biểu thức có thời gian cố định: kiểm chứng được kết quả

Câu hỏi: “Tính tới 12:00 UTC ngày 10/5/2025, những sự kiện nào xảy ra trong **một giờ ngay trước mốc đó**?”

Dùng khoảng thời gian **đóng trái, mở phải**:

```sql
WITH params AS (
    SELECT TIMESTAMPTZ '2025-05-10 12:00:00+00' AS as_of
)
SELECT
    e.event_id,
    e.status,
    e.occurred_at
FROM demo_activity AS e
CROSS JOIN params AS p
WHERE e.occurred_at >= p.as_of - INTERVAL '1 hour'
  AND e.occurred_at <  p.as_of
ORDER BY e.occurred_at, e.event_id;
```

Khoảng kiểm tra là:

```text
[2025-05-10 11:00:00 UTC, 2025-05-10 12:00:00 UTC)
```

Kết quả chỉ có `event_id = 2` và `event_id = 3`:

- Sự kiện `2` tại `11:20` thuộc một giờ trước mốc.
- Sự kiện `3` tại `11:59` cũng thuộc khoảng.
- Sự kiện `4` đúng `12:00` bị loại vì dấu `< p.as_of`.
- Những sự kiện còn lại nằm ngoài khoảng.

Nếu thêm điều kiện `status = 'success'`, chỉ còn sự kiện `2`:

```sql
WITH params AS (
    SELECT TIMESTAMPTZ '2025-05-10 12:00:00+00' AS as_of
)
SELECT e.event_id
FROM demo_activity AS e
CROSS JOIN params AS p
WHERE e.status = 'success'
  AND e.occurred_at >= p.as_of - INTERVAL '1 hour'
  AND e.occurred_at <  p.as_of
ORDER BY e.event_id;
```

Cách này **lặp lại được**, vì mốc `as_of` được khai báo tường minh. Dữ liệu mẫu và đầu vào không đổi thì tập ID dự kiến không đổi.

### 5.1. Thay mốc cố định bằng thời điểm hiện hành

Trong ứng dụng thực, yêu cầu có thể là “sự kiện một giờ gần nhất”:

```sql
SELECT event_id, status, occurred_at
FROM demo_activity
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
  AND occurred_at <  CURRENT_TIMESTAMP
ORDER BY occurred_at, event_id;
```

Truy vấn này hợp lệ với PostgreSQL, nhưng kết quả **không thể đối chiếu với bảng dữ liệu cố định như trên** nếu không biết chính xác transaction bắt đầu lúc nào. Theo thời gian thực, tập sự kiện phù hợp sẽ thay đổi.

Hơn nữa, khi transaction kéo dài, `CURRENT_TIMESTAMP` vẫn là thời điểm bắt đầu transaction. Vì vậy, “một giờ gần nhất” ở đây có nghĩa là **một giờ trước thời điểm bắt đầu transaction**, không nhất thiết là một giờ trước khi câu `SELECT` được gửi đến database.

Nếu muốn thời điểm bắt đầu **câu lệnh**, có thể dùng:

```sql
SELECT event_id
FROM demo_activity
WHERE occurred_at >= statement_timestamp() - INTERVAL '1 hour'
  AND occurred_at <  statement_timestamp();
```

`statement_timestamp()` ổn định trong câu lệnh và phản ánh mốc câu lệnh chính xác hơn khi transaction dài. Việc chọn mốc nào là **quy tắc nghiệp vụ**, không chỉ là sở thích cú pháp.

### 5.2. Dùng một tham số `as_of` trong ứng dụng

Một cách thiết kế linh hoạt là để application, scheduler hoặc job báo cáo gửi **một mốc thời gian** làm tham số vào SQL. Câu lệnh sẽ dùng **cùng mốc** ở tất cả điều kiện.

Ví dụ PostgreSQL `PREPARE`:

```sql
PREPARE events_in_last_hour(timestamptz) AS
SELECT event_id, occurred_at
FROM demo_activity
WHERE occurred_at >= $1 - INTERVAL '1 hour'
  AND occurred_at <  $1
ORDER BY occurred_at, event_id;

EXECUTE events_in_last_hour(
    TIMESTAMPTZ '2025-05-10 12:00:00+00'
);

DEALLOCATE events_in_last_hour;
```

Kết quả có sự kiện `2` và `3`, giống ví dụ CTE. Trong code ứng dụng, tham số phải được bind bằng API truy vấn có tham số, thay vì nối chuỗi SQL từ đầu vào người dùng.

Ưu điểm: có thể tái chạy báo cáo với đúng mốc cũ, so sánh kết quả, viết test với thời gian giả lập và giải thích kỳ báo cáo cho người sử dụng.

## 6. CURRENT_DATE, CURRENT_TIME, CURRENT_TIMESTAMP và múi giờ

Những tên hàm thời gian rất dễ gây nhầm giữa **ngày**, **giờ địa phương**, **thời điểm tuyệt đối** và **cách hiển thị theo múi giờ**.

Trong PostgreSQL:

| Biểu thức | Kiểu kết quả | Ghi chú |
| --- | --- | --- |
| `CURRENT_DATE` | `DATE` | Ngày tại mốc transaction, theo múi giờ phiên |
| `CURRENT_TIME` | `TIME WITH TIME ZONE` | Giờ kèm offset, dựa trên mốc transaction |
| `LOCALTIME` | `TIME WITHOUT TIME ZONE` | Giờ địa phương không mang timezone |
| `CURRENT_TIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Thời điểm transaction bắt đầu |
| `LOCALTIMESTAMP` | `TIMESTAMP WITHOUT TIME ZONE` | Ngày giờ địa phương tại mốc transaction, không kèm múi giờ |

Hai phiên ở hai múi giờ có thể biểu diễn **cùng một thời điểm** bằng hai chuỗi ngày giờ khác nhau.

Ví dụ với thời điểm cố định:

```sql
SELECT
    TIMESTAMPTZ '2025-05-09 18:30:00+00'
        AT TIME ZONE 'UTC' AS utc_local_time,
    TIMESTAMPTZ '2025-05-09 18:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vietnam_local_time;
```

Kết quả về mặt lịch:

| Múi giờ biểu diễn | Ngày giờ hiển thị |
| --- | --- |
| UTC | 2025-05-09 18:30:00 |
| Asia/Ho_Chi_Minh | 2025-05-10 01:30:00 |

Hai cách hiển thị là **cùng một thời điểm thực tế**. `AT TIME ZONE` với đầu vào `TIMESTAMPTZ` trả ngày giờ địa phương kiểu `TIMESTAMP WITHOUT TIME ZONE` trong ví dụ này.

### 6.1. “Hôm nay” phải có múi giờ nghiệp vụ

Với một ứng dụng tại Việt Nam, “các sự kiện trong ngày 10/5/2025” thường là khoảng thời gian theo **Asia/Ho_Chi_Minh**, không nhất thiết là ngày UTC.

Giới hạn ngày được chuyển về thời điểm tuyệt đối:

```sql
SELECT
    TIMESTAMP '2025-05-10 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS day_start,
    TIMESTAMP '2025-05-11 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS next_day_start;
```

Hai mốc tương đương `2025-05-09 17:00 UTC` và `2025-05-10 17:00 UTC`.

Lọc theo hai mốc:

```sql
SELECT event_id, occurred_at
FROM demo_activity
WHERE occurred_at >= (
        TIMESTAMP '2025-05-10 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        TIMESTAMP '2025-05-11 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY occurred_at, event_id;
```

Với bộ dữ liệu mẫu, các ID thuộc ngày 10/5 theo giờ Việt Nam là `1, 2, 3, 4, 5, 7`; sự kiện `6` ở ngày 9/5 theo giờ Việt Nam nên bị loại.

### 6.2. Điều gì xảy ra nếu chỉ dùng `CURRENT_DATE`?

```sql
SELECT CURRENT_DATE;
```

Giá trị `CURRENT_DATE` phụ thuộc **thời điểm bắt đầu transaction** và múi giờ phiên PostgreSQL. Nếu transaction bắt đầu trước nửa đêm và kéo dài qua ngày hôm sau, `CURRENT_DATE` trong transaction đó có thể vẫn chỉ ngày bắt đầu.

Không nên giả định “ngày của transaction”, “ngày của câu SQL” và “ngày theo múi giờ của người dùng” luôn giống nhau. Quy tắc báo cáo cần xác định rõ **mốc thời gian** và **múi giờ**.

### 6.3. INTERVAL '1 day' và '24 hours' có thể khác nhau

Với thời điểm có múi giờ và những khu vực có **giờ mùa hè (DST)**, “cùng giờ địa phương vào ngày hôm sau” có thể cách thời điểm ban đầu **23 hoặc 25 giờ thực**, không phải lúc nào cũng đúng 24 giờ.

Trong PostgreSQL, các phép cộng `INTERVAL '1 day'` và `INTERVAL '24 hours'` với `TIMESTAMPTZ` có thể khác nhau khi đi qua chuyển đổi DST, tùy múi giờ phiên.

Do đó phải làm rõ yêu cầu:

- “24 giờ gần nhất” là một **khoảng thời gian thực** có độ dài 24 giờ.
- “Ngày địa phương hiện tại” là một **khoảng theo lịch**, có thể không bằng 24 giờ ở khu vực có DST.

`Asia/Ho_Chi_Minh` không có chuyển đổi DST hiện đại, nhưng hệ thống toàn cầu không thể bỏ qua vấn đề này.

## 7. Cột DEFAULT: hàm thời gian được tính khi nào?

Một cách dùng phổ biến của thời gian hệ quản trị là gán mặc định khi thêm hàng:

```sql
CREATE TEMP TABLE demo_jobs (
    job_id      INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ
);

INSERT INTO demo_jobs (job_id, description)
VALUES (1, 'Import file A');

SELECT job_id, description, created_at, updated_at
FROM demo_jobs;
```

Trong PostgreSQL, `DEFAULT CURRENT_TIMESTAMP` tạo **một giá trị thời gian được ghi vào hàng lúc `INSERT`**, dựa trên transaction hiện tại. Mỗi lần đọc `created_at` sau này sẽ thấy giá trị đã lưu, không chạy lại `CURRENT_TIMESTAMP` như một cột tính toán ảo.

Nếu chèn thêm hàng ở một transaction khác, mốc mặc định có thể khác.

### 7.1. Nhiều INSERT trong cùng transaction có thể chung created_at

```sql
BEGIN;

INSERT INTO demo_jobs (job_id, description)
VALUES (2, 'Import file B');

INSERT INTO demo_jobs (job_id, description)
VALUES (3, 'Import file C');

SELECT job_id, created_at
FROM demo_jobs
WHERE job_id IN (2, 3)
ORDER BY job_id;

COMMIT;
```

Với `DEFAULT CURRENT_TIMESTAMP`, hai hàng `2` và `3` có thể nhận **cùng một mốc transaction** ngay cả khi hai câu lệnh thực hiện cách nhau một khoảng thời gian.

Đây không phải lỗi tự động: nó phản ánh cách PostgreSQL định nghĩa `CURRENT_TIMESTAMP`. Nếu nghiệp vụ cần thời điểm bắt đầu mỗi statement, có thể xem `DEFAULT statement_timestamp()`; nếu cần đồng hồ tại lúc hàm được đánh giá, có thể xem `DEFAULT clock_timestamp()`. Lựa chọn cần thống nhất với yêu cầu kiểm toán và độ chính xác.

### 7.2. DEFAULT không tự cập nhật khi UPDATE

```sql
UPDATE demo_jobs
SET description = 'Import file A - completed'
WHERE job_id = 1;
```

Lệnh trên **không tự thay đổi** `updated_at`. Nếu muốn theo dõi lần cập nhật, cần một cơ chế chủ động:

```sql
UPDATE demo_jobs
SET description = 'Import file A - completed',
    updated_at = statement_timestamp()
WHERE job_id = 1;
```

Hoặc dùng trigger được thiết kế và quản lý rõ ràng ở database. Không nên nhầm `DEFAULT` với “tự động cập nhật ở mỗi lần sửa hàng”.

### 7.3. Thời gian sự kiện và thời gian lưu vào database

Một hệ thống tiếp nhận log hoặc giao dịch có thể cần ít nhất hai cột:

```sql
CREATE TEMP TABLE imported_events (
    event_id     INTEGER PRIMARY KEY,
    occurred_at  TIMESTAMPTZ NOT NULL,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp()
);
```

- `occurred_at`: lúc sự kiện **thật sự xảy ra**, theo nguồn phát sinh.
- `received_at`: lúc cơ sở dữ liệu tiếp nhận/bắt đầu xử lý câu lệnh nhập.

Khi hệ thống nhận dữ liệu trễ, hai thời điểm có thể cách nhau hàng phút hoặc hàng ngày. Không dùng `DEFAULT CURRENT_TIMESTAMP` thay cho `occurred_at` nếu nguồn đã cung cấp thời điểm sự kiện thực tế.

## 8. Vì sao CURRENT_TIMESTAMP không phù hợp với mọi loại biểu thức?

Không phải chỗ nào sử dụng biểu thức SQL cũng cho phép hàm phụ thuộc thời gian.

### 8.1. DEFAULT cho phép ghi giá trị tại thời điểm INSERT

Ví dụ hợp lệ trong PostgreSQL:

```sql
CREATE TEMP TABLE audit_rows (
    audit_id INTEGER PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Biểu thức mặc định được đánh giá khi thêm hàng; giá trị được **lưu** vào cột.

### 8.2. Generated column yêu cầu biểu thức có tính bất biến phù hợp

PostgreSQL yêu cầu biểu thức của **stored generated column** dùng các hàm `IMMUTABLE`. Ví dụ sau được viết để minh họa lỗi:

```sql
-- CỐ Ý KHÔNG HỢP LỆ trong PostgreSQL:
CREATE TABLE bad_generated_example (
    id INTEGER PRIMARY KEY,
    expires_at TIMESTAMPTZ
        GENERATED ALWAYS AS (
            CURRENT_TIMESTAMP + INTERVAL '7 days'
        ) STORED
);
```

`CURRENT_TIMESTAMP` phụ thuộc transaction, nên không phù hợp làm biểu thức generated `IMMUTABLE`. Nếu muốn lưu hạn hết hiệu lực của từng hàng, có thể:

- Ghi `created_at` khi thêm hàng.
- Tính `expires_at` một lần ở thao tác ghi theo quy tắc nghiệp vụ.
- Hoặc dùng một truy vấn đọc so sánh `created_at` với thời điểm kiểm tra.

Ví dụ hợp lệ về mặt thiết kế khi chọn ghi thời điểm ở lúc tạo hàng:

```sql
CREATE TEMP TABLE expiring_tokens (
    token_id INTEGER PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL
        DEFAULT (CURRENT_TIMESTAMP + INTERVAL '7 days')
);
```

Hai giá trị mặc định được xác định tại lần `INSERT` trong transaction; chúng không tự tăng khi thời gian trôi qua. Ứng dụng cần hiểu rằng hạn `expires_at` được **ghi một lần**, không phải “bây giờ cộng bảy ngày” mỗi khi đọc.

### 8.3. Index expression và partial index không chấp nhận đồng hồ động

Một index phải bảo toàn ý nghĩa từ giá trị cột và biểu thức được index. Nếu giá trị index tự thay đổi chỉ vì đồng hồ tiến lên, database không thể duy trì nó đúng nếu không cập nhật các hàng.

Ví dụ sau **cố ý gây lỗi** trong PostgreSQL:

```sql
-- CỐ Ý KHÔNG HỢP LỆ:
CREATE INDEX bad_recent_events_idx
ON demo_activity (event_id)
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '7 days';
```

PostgreSQL yêu cầu các hàm trong **biểu thức index và điều kiện partial index** là `IMMUTABLE`. `CURRENT_TIMESTAMP` chỉ `STABLE`, nên không phù hợp.

Cách tiếp cận thông thường là index trên cột thời gian, rồi dùng mốc thời gian động tại lúc truy vấn:

```sql
CREATE INDEX idx_demo_activity_occurred_at
    ON demo_activity (occurred_at);

SELECT event_id
FROM demo_activity
WHERE occurred_at >= statement_timestamp() - INTERVAL '7 days'
  AND occurred_at <  statement_timestamp()
ORDER BY occurred_at;
```

Index chứa các giá trị `occurred_at` đã lưu. Câu truy vấn tính **ranh giới thời gian tại lúc đọc**, giúp bộ tối ưu hóa có thể xem xét index phù hợp. Có dùng index thực tế hay không còn tùy kích thước bảng, thống kê và kế hoạch truy vấn.

### 8.4. Phép biến đổi thời gian cũng có thể phụ thuộc ngữ cảnh

Hai biểu thức trông tương tự nhưng có mức phụ thuộc khác nhau:

```sql
-- Timestamp KHÔNG kèm múi giờ: trích tháng theo giá trị lịch đã cho.
SELECT DATE_TRUNC(
    'month',
    TIMESTAMP '2025-05-10 12:30:00'
);

-- Timestamptz: tháng/ngày địa phương phụ thuộc cách diễn giải múi giờ.
SELECT DATE_TRUNC(
    'month',
    TIMESTAMPTZ '2025-05-10 12:30:00+00'
);
```

Trong PostgreSQL, nhiều phép xử lý `TIMESTAMPTZ` dùng múi giờ phiên; một số hàm/biến thể vì thế không được phân loại `IMMUTABLE`. Đừng tự cho rằng “`DATE_TRUNC` luôn xác định” mà bỏ qua kiểu đầu vào và timezone.

Nếu cần lưu ngày địa phương cho báo cáo, nên xác định **múi giờ nghiệp vụ** và cách cập nhật khi quy tắc thay đổi. Nếu dùng cột tính toán hoặc index biểu thức, cần kiểm tra tính chất thật của biểu thức theo PostgreSQL và kiểu dữ liệu đầu vào.

## 9. Dữ liệu không thay đổi nhưng kết quả truy vấn vẫn thay đổi

Xét một bảng `demo_activity` giữ nguyên hoàn toàn. Tại thời điểm A, sự kiện `2` còn nằm trong “một giờ gần nhất”; sau khi đủ thời gian trôi qua, sự kiện đó sẽ ra khỏi cửa sổ.

```sql
SELECT COUNT(*) AS recent_count
FROM demo_activity
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
  AND occurred_at <  CURRENT_TIMESTAMP;
```

Kết quả phụ thuộc vào thời gian chạy và thời điểm bắt đầu transaction. Database không cần có thêm hay xóa hàng để `recent_count` thay đổi.

Có thể phân loại truy vấn theo sự phụ thuộc:

| Truy vấn | Phụ thuộc vào | Có thể thay đổi khi |
| --- | --- | --- |
| `SELECT 2 * 3` | Literal và phép toán số học | Thông thường không đổi |
| `SELECT quantity * unit_price FROM items` | Giá trị bảng | Hàng dữ liệu thay đổi |
| `SELECT COUNT(*) FROM orders` | Trạng thái bảng và snapshot | Có transaction khác ghi và thay đổi dữ liệu nhìn thấy |
| `SELECT CURRENT_TIMESTAMP` | Mốc bắt đầu transaction | Sang transaction khác |
| `SELECT statement_timestamp()` | Mốc bắt đầu statement | Sang câu lệnh khác |
| `SELECT clock_timestamp()` | Đồng hồ tại lần gọi | Thời gian trôi qua |
| `SELECT RANDOM()` | Bộ sinh số giả ngẫu nhiên | Có lần gọi khác |
| `SELECT nextval('seq')` | Trạng thái sequence | Mỗi lần cấp giá trị |

Đây là cách giải thích kết quả trong PostgreSQL, không phải phân loại một truy vấn tổng thể theo cùng chuẩn metadata của các hàm.

### 9.1. Ảnh hưởng đến cache

Nếu ứng dụng cache:

```sql
SELECT COUNT(*)
FROM demo_activity
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours';
```

thì kết quả cache có thể **hết đúng về mặt thời gian** dù bảng không nhận thêm hàng nào. Một cache chỉ bị vô hiệu hóa khi có `INSERT`/`UPDATE`/`DELETE` sẽ không xử lý đầy đủ sự phụ thuộc vào đồng hồ.

Các hướng thiết kế:

- Chỉ rõ `as_of` rồi cache theo **mốc báo cáo** và phiên bản dữ liệu.
- Dùng thời hạn cache (*TTL*) phù hợp với độ mới mà người dùng chấp nhận.
- Tính toán theo các khoảng cố định (ví dụ báo cáo ngày đã chốt) nếu nghiệp vụ cho phép.
- Nêu rõ thời điểm dữ liệu được tính, chẳng hạn “số liệu tính đến 12:00 UTC”.

Không có một TTL đúng chung cho mọi truy vấn; báo cáo theo phút và báo cáo theo tháng có yêu cầu khác nhau.

### 9.2. View và materialized view

Một **view thông thường** là câu truy vấn được dùng lại. Khi truy vấn view có `CURRENT_TIMESTAMP`, thời điểm phụ thuộc vào transaction đọc view.

Một **materialized view** lưu kết quả đã được tính vào lúc tạo hoặc refresh, nên biểu thức thời gian trong định nghĩa không tự cập nhật ở mỗi lần `SELECT` từ materialized view.

Ví dụ về ý tưởng:

```sql
-- PostgreSQL: câu SELECT này là biểu thức thời gian động.
CREATE VIEW demo_recent_activity AS
SELECT event_id, occurred_at
FROM demo_activity
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '1 day';
```

Lưu ý: `demo_activity` là bảng tạm, nên ví dụ `CREATE VIEW` thường chỉ phù hợp để minh họa trong cùng phiên; trong dự án thật, view/materialized view nên tham chiếu bảng dữ liệu tồn tại lâu dài theo chính sách schema của hệ thống.

Materialized view sẽ giữ **ảnh chụp kết quả ở thời điểm refresh**. Nếu yêu cầu là “24 giờ hiện tại” trên mỗi lần xem, cần thiết kế lịch refresh hoặc truy vấn trực tiếp; không thể mặc định một materialized view có đồng hồ tự chạy bên trong dữ liệu đã vật chất hóa.

## 10. Lựa chọn mốc thời gian đúng cho nghiệp vụ

Hàm thời gian “đúng” phải dựa trên **thời điểm nào cần được ghi nhận**.

| Nhu cầu | Mốc thường phù hợp trong PostgreSQL | Lý do |
| --- | --- | --- |
| Mọi bản ghi trong transaction có cùng mốc thời gian | `transaction_timestamp()` / `CURRENT_TIMESTAMP` | Đại diện điểm bắt đầu transaction |
| Lấy mốc bắt đầu mỗi câu lệnh SQL | `statement_timestamp()` | Không bị cố định ở transaction bắt đầu lâu trước đó |
| Ghi đồng hồ tại lần thực thi biểu thức | `clock_timestamp()` | Có thể thay đổi trong cùng statement |
| Báo cáo có thể chạy lại đúng kết quả | Tham số `as_of` cố định | Không phụ thuộc thời điểm chạy lại |
| Ngày làm việc theo một quốc gia/múi giờ | Mốc `as_of` cùng timezone nghiệp vụ | Tránh phụ thuộc timezone của phiên |
| Thời điểm sự kiện xảy ra tại nguồn | Timestamp do nguồn gửi, được xác thực | Phân biệt event time với ingestion time |
| Thời điểm nhận dữ liệu vào database | `statement_timestamp()` hoặc mốc được ứng dụng thống nhất | Mô tả điểm bắt đầu xử lý lần ghi |
| Đo khoảng thời gian trôi trong quá trình xử lý SQL | `clock_timestamp()` tại những điểm đo | Giá trị transaction timestamp không đổi nên không phù hợp tính khoảng chờ |

### 10.1. Ví dụ đo khoảng thời gian

Trong PostgreSQL, hai lần đọc `clock_timestamp()` ở hai thời điểm xử lý có thể dùng để tính chênh lệch:

```sql
DO $$
DECLARE
    started_at TIMESTAMPTZ;
    finished_at TIMESTAMPTZ;
BEGIN
    started_at := clock_timestamp();

    PERFORM pg_sleep(0.1);

    finished_at := clock_timestamp();

    RAISE NOTICE 'Elapsed: %', finished_at - started_at;
END;
$$;
```

Đây chỉ là ví dụ đo khoảng thời gian trong một phiên thử nghiệm. `clock_timestamp()` đọc đồng hồ hệ thống thực, vốn có thể bị điều chỉnh, nên nó **không phải một API đồng hồ đơn điệu được cam kết** cho mọi trường hợp đo thời lượng chính xác. Với đo hiệu năng production, thường nên dùng công cụ tracing/metrics hoặc đồng hồ monotonic phù hợp trong ứng dụng.

Nếu dùng `transaction_timestamp()` thay cho hai mốc ở trên trong cùng transaction, hiệu số có thể là `0` dù mã đã chờ, vì hai lần đọc trả cùng mốc transaction.

### 10.2. Ngày giờ mặc định không phải bằng chứng thứ tự commit

Hai transaction đồng thời:

```text
Transaction A: BEGIN lúc 10:00; INSERT lúc 10:02; COMMIT lúc 10:05
Transaction B: BEGIN lúc 10:01; INSERT lúc 10:01; COMMIT lúc 10:03
```

Nếu cả hai bảng dùng `created_at DEFAULT CURRENT_TIMESTAMP` trong PostgreSQL, hàng A có `created_at = 10:00`, hàng B có `created_at = 10:01`, dù B commit **trước** A.

Một timestamp mặc định theo transaction không phải log thứ tự commit. Nếu nghiệp vụ cần thứ tự kết thúc giao dịch, phải nghiên cứu cơ chế log, đánh số, hoặc ghi nhận sự kiện ở mức tương ứng; không suy ra thứ tự commit chỉ từ `created_at`.

## 11. Hàm tự định nghĩa: không được khai báo volatility tùy ý

Trong PostgreSQL, người viết hàm có thể chỉ định `IMMUTABLE`, `STABLE` hoặc `VOLATILE` trong `CREATE FUNCTION`. Việc chọn đúng nhãn là trách nhiệm của người phát triển.

### 11.1. Hàm tính toán thuần

Ví dụ hàm tính số tiền sau giảm giá:

```sql
CREATE OR REPLACE FUNCTION demo_discounted_amount(
    price NUMERIC,
    discount_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT ROUND(price * (1 - discount_rate), 2);
$$;
```

`IMMUTABLE` phù hợp vì hàm chỉ phụ thuộc hai đối số số học và phép tính rõ ràng trong ngữ cảnh này. `STRICT` nghĩa là nếu bất kỳ đối số nào là `NULL` thì kết quả là `NULL` mà hàm không cần thực thi nội dung.

```sql
SELECT
    demo_discounted_amount(100, 0.10) AS discounted,
    demo_discounted_amount(100, NULL) AS unknown_discount;
```

Kết quả là `90.00` và `NULL`.

Nếu nghiệp vụ không cho phép tỷ lệ giảm âm hoặc lớn hơn 1, cần ràng buộc đầu vào hoặc xác thực riêng; `IMMUTABLE` chỉ mô tả tính chất hàm, không tự xác nhận tham số hợp lệ về nghiệp vụ.

### 11.2. Hàm đọc dữ liệu thay đổi theo thời gian

Một hàm tra cứu thông tin trong bảng có thể trả kết quả khác giữa các transaction khi bảng được cập nhật. Vì vậy, không nên đánh dấu `IMMUTABLE` chỉ vì hàm nhận tham số rõ ràng và không ghi dữ liệu.

Với hàm chỉ đọc dữ liệu cần snapshot ổn định, `STABLE` có thể phù hợp tùy hành vi hàm và thiết kế transaction. Với hàm có tác dụng thay đổi dữ liệu, gọi sequence hoặc cần thấy các thay đổi giữa những lần gọi, `VOLATILE` là lựa chọn phù hợp.

### 11.3. Khai báo IMMUTABLE sai tạo lỗi khó phát hiện

Một lỗi thiết kế nguy hiểm là viết hàm trả `CURRENT_DATE` rồi đánh dấu `IMMUTABLE` để cố dùng trong generated column hoặc index. PostgreSQL có thể tin vào nhãn khai báo và tính trước kết quả, nhưng **giá trị thực tế thay đổi theo ngày**.

Không được “nâng cấp” hàm `STABLE` hoặc `VOLATILE` lên `IMMUTABLE` chỉ nhằm tránh lỗi DDL. Cần sửa thiết kế biểu thức, truyền thời điểm như đối số hoặc dùng một cột dữ liệu đã lưu, thay vì đưa ra cam kết bất biến sai.

### 11.4. Trạng thái phiên và cấu hình cũng là đầu vào ngầm

Một hàm không cần đọc đồng hồ vẫn có thể phụ thuộc vào timezone, collation, locale, `DateStyle` hoặc các cấu hình khác. Ví dụ chuyển `TIMESTAMPTZ` thành ngày địa phương phụ thuộc múi giờ áp dụng.

Nếu hàm phụ thuộc một giá trị cấu hình mà không nhận nó làm đối số, không thể mặc định hàm bất biến tuyệt đối theo các đối số nhìn thấy. Khi thiết kế hàm dùng lâu dài, nên **truyền múi giờ/định dạng cần thiết thành đầu vào rõ ràng** và kiểm tra tính chất thật theo DBMS.

## 12. CASE, COALESCE và việc “đánh giá theo thứ tự” có giới hạn

Người học đôi khi cố dùng điều kiện logic để buộc engine đánh giá một hàm chỉ sau một hàm khác:

```sql
WHERE denominator <> 0
  AND numerator / denominator > 10
```

Không nên dựa vào thứ tự viết các vế `AND` để bảo vệ phép chia. SQL là ngôn ngữ khai báo; optimizer có thể sắp xếp lại các điều kiện khi giữ ngữ nghĩa.

Viết phép chia an toàn theo dữ liệu:

```sql
SELECT
    numerator / NULLIF(denominator, 0) AS safe_ratio
FROM (
    VALUES
        (100.0, 0.0),
        (100.0, 4.0)
) AS values_table(numerator, denominator);
```

Với mẫu số 0, `NULLIF` trả `NULL` và phép chia ra `NULL`. Đây là một cách tránh lỗi chia cho 0 phù hợp hơn giả định thứ tự thực thi.

### 12.1. CASE giúp diễn đạt nhánh, nhưng không phải rào chắn tuyệt đối

`CASE` thường được dùng để chọn kết quả theo điều kiện:

```sql
SELECT
    CASE
        WHEN status = 'success' THEN 'Hoan thanh'
        WHEN status = 'failed' THEN 'That bai'
        ELSE 'Dang xu ly'
    END AS status_label
FROM demo_activity;
```

Cần phân biệt **quy tắc chọn nhánh** với **thời điểm engine tính mọi biểu thức**. PostgreSQL có thể tính trước các biểu thức hằng ở giai đoạn lập kế hoạch, nên một `CASE` không phải bảo đảm tuyệt đối chống mọi lỗi do biểu thức có thể được tối ưu/tính sớm.

Nếu một phép tính có thể lỗi, thiết kế phép tính an toàn theo đúng kiểu dữ liệu và hàm bảo vệ phù hợp. Với biểu thức phụ thuộc thời gian, hãy chọn một mốc `as_of` ổn định để mọi nhánh đều dùng chung khi nghiệp vụ yêu cầu cùng thời điểm.

### 12.2. COALESCE không biến thời gian động thành bất biến

```sql
SELECT COALESCE(NULL::timestamptz, CURRENT_TIMESTAMP);
```

Trong ví dụ này, `COALESCE` chọn thời gian transaction vì đối số đầu `NULL`. Nhưng biểu thức kết quả vẫn phụ thuộc vào transaction; nó không trở thành `IMMUTABLE` chỉ vì một hàm bao ngoài được sử dụng.

Tính biến động của biểu thức tổng thể phải xét cả **những thành phần bên trong**.

## 13. Prepared statement, constant folding và kết quả bị “đóng băng”

Ứng dụng thường chuẩn bị truy vấn trước rồi thực thi nhiều lần:

```sql
PREPARE recent_count(timestamptz) AS
SELECT COUNT(*)
FROM demo_activity
WHERE occurred_at >= $1 - INTERVAL '1 hour'
  AND occurred_at < $1;
```

Mỗi lần gọi với cùng `as_of` và cùng snapshot dữ liệu, tập kết quả cần đối chiếu được rõ ràng:

```sql
EXECUTE recent_count(
    TIMESTAMPTZ '2025-05-10 12:00:00+00'
);
-- 2 sự kiện

DEALLOCATE recent_count;
```

Nếu prepared statement dùng `CURRENT_TIMESTAMP` trong điều kiện, PostgreSQL sẽ áp dụng ngữ nghĩa `STABLE` của hàm tại các lần thực thi theo transaction tương ứng. **Đừng tự giả định thời gian bị đóng băng vĩnh viễn từ lúc PREPARE.**

Vấn đề nguy hiểm thường xuất hiện khi lập trình viên **khai báo sai một hàm phụ thuộc thời gian là `IMMUTABLE`**. Optimizer có thể tính trước hàm với đối số hằng và lưu giá trị trong kế hoạch, khiến câu truy vấn lâu ngày trả kết quả lệch kỳ vọng.

Khi thấy thời gian “không chịu cập nhật” trong một truy vấn tái sử dụng, cần phân biệt:

1. Transaction có đang kéo dài nên `CURRENT_TIMESTAMP` hợp lệ nhưng cũ không?
2. Ứng dụng có truyền một `as_of` cố định mà không cập nhật không?
3. Kết quả có bị cache ở ứng dụng/materialized view không?
4. Hàm tự định nghĩa có bị gắn nhãn `IMMUTABLE` sai không?
5. Dữ liệu sự kiện hay timezone của phiên có khác mong đợi không?

Không nên sửa bằng cách thay mọi `CURRENT_TIMESTAMP` thành `clock_timestamp()`: cách đó có thể làm ranh giới thời gian thay đổi **giữa các hàng**, mất tính nhất quán của một truy vấn.

## 14. Hành vi giữa các hệ quản trị SQL

Các khái niệm “deterministic” và “current time” xuất hiện trên nhiều nền tảng, nhưng không có một bộ hàm và quy tắc thực thi giống hệt nhau.

| Hệ quản trị | Cách phân loại/tư duy | Các hàm thời gian đáng chú ý |
| --- | --- | --- |
| **PostgreSQL** | `IMMUTABLE`, `STABLE`, `VOLATILE` cho hàm; ảnh hưởng đến tối ưu, index và generated columns | `CURRENT_TIMESTAMP`/`now()` theo transaction; `statement_timestamp()` theo statement; `clock_timestamp()` theo lần gọi |
| **SQL Server** | Phân biệt hàm deterministic/nondeterministic; liên quan indexed view, indexed computed column và các giới hạn khác | `GETDATE()`, `SYSDATETIME()`, `SYSUTCDATETIME()` là hàm thời gian phụ thuộc lúc thực thi |
| **MySQL** | Phân biệt hàm có tính xác định trong các ngữ cảnh như stored routine, generated column và index | `NOW()`/`CURRENT_TIMESTAMP` thường cố định tại mốc bắt đầu statement; `SYSDATE()` có hành vi đọc đồng hồ theo cấu hình |
| **Oracle Database** | Có thể khai báo `DETERMINISTIC` cho hàm người dùng; lập trình viên phải bảo đảm cam kết chính xác | `SYSDATE` theo đồng hồ máy chủ; `SYSTIMESTAMP` trả timestamp với timezone; `CURRENT_TIMESTAMP` theo múi giờ phiên |
| **SQLite** | Có phân loại deterministic function phục vụ expression index, generated column và một số ngữ cảnh DDL | `datetime('now')`, `CURRENT_TIMESTAMP` và các hàm ngày giờ phụ thuộc thời điểm; có quy tắc đặc biệt trong từng ngữ cảnh |

### 14.1. SQL Server: hàm ngày giờ không phải deterministic

Một ví dụ SQL Server:

```sql
-- SQL Server, không chạy trong PostgreSQL:
SELECT
    GETDATE()        AS local_server_time,
    SYSUTCDATETIME() AS utc_time;
```

`GETDATE()` trả mốc thời gian theo đồng hồ hệ thống của môi trường SQL Server; `SYSUTCDATETIME()` cho thời gian UTC với kiểu độ chính xác cao hơn. Đây là các hàm không có tính xác định theo cách SQL Server phân loại.

Vì vậy, một computed column muốn được index trong SQL Server phải đáp ứng các quy tắc về tính xác định và những điều kiện khác. Không được áp dụng nguyên danh sách `IMMUTABLE`/`STABLE`/`VOLATILE` của PostgreSQL cho SQL Server.

### 14.2. MySQL: NOW() và SYSDATE() khác nhau

Trong MySQL:

```sql
-- MySQL, không chạy trong PostgreSQL:
SELECT
    NOW()      AS statement_time,
    SYSDATE()  AS execution_clock;
```

`NOW()` thường đại diện thời điểm bắt đầu câu lệnh và ổn định trong câu lệnh đó; `SYSDATE()` có thể đọc đồng hồ tại thời điểm gọi. MySQL có cấu hình đặc biệt như `--sysdate-is-now` có thể điều chỉnh hành vi `SYSDATE()`, nên cần kiểm tra cấu hình đang dùng.

Không nên suy ra rằng `NOW()` của MySQL có nghĩa **đầu transaction** như `now()` của PostgreSQL chỉ vì trùng tên.

### 14.3. Oracle: SYSDATE và CURRENT_TIMESTAMP

Ví dụ Oracle Database:

```sql
-- Oracle, không chạy trong PostgreSQL:
SELECT
    SYSDATE,
    SYSTIMESTAMP,
    CURRENT_TIMESTAMP
FROM dual;
```

`SYSDATE` trả kiểu ngày giờ theo đồng hồ máy chủ; `SYSTIMESTAMP` chứa thông tin timezone và phần lẻ giây; `CURRENT_TIMESTAMP` dựa theo múi giờ của phiên. Cú pháp chuyển đổi và độ chính xác cần xem theo phiên bản Oracle.

Oracle cho phép khai báo hàm tự định nghĩa `DETERMINISTIC` nhưng không thể mặc định database tự kiểm tra lời hứa này. Một hàm đọc bảng thay đổi hay thời gian hiện hành không trở thành xác định chỉ nhờ từ khóa.

### 14.4. SQLite: hàm ngày giờ phụ thuộc thời điểm

Ví dụ SQLite:

```sql
-- SQLite:
SELECT CURRENT_TIMESTAMP, datetime('now');
```

Giá trị hiện hành phụ thuộc đồng hồ và các quy tắc thời gian của SQLite. SQLite đặt giới hạn việc dùng hàm không xác định trong các ngữ cảnh như expression index, partial index và generated column.

Một chi tiết: các lần đọc `'now'` trong cùng một lệnh gọi `sqlite3_step()` có thể nhận cùng mốc thời gian theo ngữ nghĩa của SQLite, nhưng điều đó không biến biểu thức thành hàm xác định vĩnh viễn theo đầu vào. Cần đọc tài liệu SQLite nếu tạo hàm C mở rộng và gắn cờ deterministic.

### 14.5. Khác biệt về độ chính xác

Ngay cả khi hai engine đều có `CURRENT_TIMESTAMP`, độ chính xác của kiểu trả về, cách lấy thời điểm và cách làm tròn phần lẻ giây có thể khác. Khi so sánh giữa các hệ, nên truyền dữ liệu thời gian bằng kiểu chuẩn của driver/protocol và khai báo rõ độ chính xác, thay vì dựa vào chuỗi hiển thị.

## 15. Thiết kế kiểm thử với thời gian có thể điều khiển

Kiểm thử một truy vấn phụ thuộc đồng hồ thực thường tạo lỗi không ổn định (*flaky test*). Một test chạy trước nửa đêm có thể qua, chạy sau nửa đêm có thể thất bại dù mã nguồn không đổi.

Ví dụ test kiểu này khó tái lập:

```sql
SELECT event_id
FROM demo_activity
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour';
```

Vì mốc `CURRENT_TIMESTAMP` thay đổi theo transaction, tập dữ liệu cố định sẽ không mãi đáp ứng cùng điều kiện.

### 15.1. Truyền as_of vào câu truy vấn

```sql
WITH p AS (
    SELECT TIMESTAMPTZ '2025-05-10 12:00:00+00' AS as_of
)
SELECT event_id
FROM demo_activity
CROSS JOIN p
WHERE occurred_at >= p.as_of - INTERVAL '1 hour'
  AND occurred_at < p.as_of
ORDER BY event_id;
```

**Expected IDs:** `2, 3`.

Nếu thay mốc tham chiếu bằng `2025-05-10 11:30:00+00`, khoảng kiểm tra trở thành `[10:30, 11:30)`, chỉ có các sự kiện `1` và `2` (không có `3`). Dùng những mốc đã biết giúp thử trường hợp biên như **bằng đầu khoảng**, **bằng cuối khoảng**, **trước/sau nửa đêm**, **NULL** và **chuyển ngày theo timezone**.

### 15.2. Truyền mốc ở tầng Java

Nếu ứng dụng Java xây dựng truy vấn từ `Instant.now()` rải rác ở nhiều hàm, các phần xử lý có thể dùng các mốc khác nhau. Có thể tách nguồn thời gian qua `java.time.Clock`:

```java
import java.time.Clock;
import java.time.Instant;

public final class ReportContext {
    private final Clock clock;

    public ReportContext(Clock clock) {
        this.clock = clock;
    }

    public Instant asOf() {
        return Instant.now(clock);
    }
}
```

Trong production, `Clock.systemUTC()` thường là lựa chọn để lấy thời điểm theo UTC. Trong test, dùng mốc cố định:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
    Instant.parse("2025-05-10T12:00:00Z"),
    ZoneOffset.UTC
);

ReportContext context = new ReportContext(fixed);
System.out.println(context.asOf());
// 2025-05-10T12:00:00Z
```

Ứng dụng có thể bind `context.asOf()` thành tham số `TIMESTAMPTZ` qua driver JDBC phù hợp. Điều này giúp cùng một test có đầu vào thời gian giống nhau trong mọi lần chạy. Nếu dùng nhiều dịch vụ, nên thống nhất mốc kiểm tra trong request/job để tránh mỗi thành phần tự lấy đồng hồ tại thời điểm khác nhau.

## 16. Những nhầm lẫn thường gặp

| Nhận định | Vì sao không chính xác | Cách suy luận đúng |
| --- | --- | --- |
| “`now()` lúc nào cũng trả thời điểm gọi mới nhất.” | Trong PostgreSQL, `now()` cố định tại đầu transaction | Chọn `statement_timestamp()` hoặc `clock_timestamp()` nếu cần mốc khác |
| “Hàm nào có cùng kết quả trong một câu SQL là IMMUTABLE.” | `STABLE` cũng ổn định trong statement nhưng không bất biến giữa các statement | Xét hợp đồng của hàm theo nhiều lần gọi/ngữ cảnh |
| “Cùng SQL chạy hai lần phải ra cùng kết quả.” | Bảng và đồng hồ có thể thay đổi | Cố định input, snapshot và `as_of` khi cần lặp lại |
| “`CURRENT_DATE` không phụ thuộc timezone.” | Ngày được diễn giải theo múi giờ phiên | Định nghĩa múi giờ nghiệp vụ |
| “DEFAULT CURRENT_TIMESTAMP tự cập nhật khi UPDATE.” | DEFAULT thường áp dụng khi chèn hoặc chỉ định DEFAULT | Thiết kế cập nhật `updated_at` riêng |
| “Index WHERE thời gian trong 7 ngày sẽ tự trượt theo đồng hồ.” | Partial index không nhận điều kiện `CURRENT_TIMESTAMP` vì không immutable | Index cột thời gian, lọc bằng ranh giới runtime |
| “Đánh dấu UDF là IMMUTABLE sẽ làm nó đúng hơn.” | Nhãn sai có thể gây tối ưu tái dùng kết quả lỗi | Khai báo đúng mức biến động thực tế |
| “Hai lần clock_timestamp luôn cho hai số khác nhau.” | Có thể trùng ở độ phân giải quan sát | Không có bảo đảm bằng nhau hoặc khác nhau |
| “Hàm SQL được tính theo thứ tự viết.” | Optimizer có quyền thay đổi cách đánh giá khi giữ ngữ nghĩa | Không dùng thứ tự `AND`/`OR` làm cơ chế bảo vệ lỗi |
| “Múi giờ chỉ ảnh hưởng định dạng đẹp.” | Nó ảnh hưởng việc xác định ngày/kỳ và một số phép chuyển kiểu | Là một phần quy tắc báo cáo |
| “`created_at` lớn nhất luôn commit cuối.” | Mốc tạo và mốc commit khác nhau | Định nghĩa riêng thứ tự sự kiện/commit |
| “Cache kết quả truy vấn thời gian chỉ cần invalid khi bảng đổi.” | Kết quả có thể già đi chỉ do đồng hồ chạy | Dùng TTL, `as_of` hoặc dữ liệu theo kỳ đã chốt |

## 17. Bài tập có đáp án gợi ý

Các bài PostgreSQL dưới đây dùng bảng `demo_activity` trong phần 4, trừ khi ghi chú khác.

### Bài 1 — Xác định biểu thức nào phụ thuộc thời gian

Phân loại:

```sql
SELECT 10 * 12;
SELECT CURRENT_TIMESTAMP;
SELECT statement_timestamp();
SELECT clock_timestamp();
SELECT RANDOM();
```

**Đáp án:** `10 * 12` là phép tính xác định với đầu vào literal. Trong PostgreSQL, `CURRENT_TIMESTAMP` và `statement_timestamp()` thuộc nhóm hàm thời gian `STABLE` theo phạm vi câu lệnh (dù mốc của chúng khác nhau); `clock_timestamp()` và `RANDOM()` là `VOLATILE`.

### Bài 2 — Dự đoán cùng transaction

Giả sử transaction bắt đầu lúc 10:00, câu `SELECT` đầu chạy lúc 10:03, câu thứ hai chạy lúc 10:08. `CURRENT_TIMESTAMP`, `statement_timestamp()` và `clock_timestamp()` của hai câu cho ý nghĩa gì?

**Đáp án:** `CURRENT_TIMESTAMP` vẫn biểu diễn khoảng 10:00 ở cả hai câu. `statement_timestamp()` biểu diễn mốc 10:03 và 10:08 tương ứng. `clock_timestamp()` biểu diễn thời điểm thực sự đánh giá từng lời gọi, thường gần thời điểm câu SQL đang chạy.

### Bài 3 — Một giờ trước mốc cố định

Với `as_of = 2025-05-10 12:00 UTC`, tìm sự kiện thuộc `[11:00, 12:00)`.

```sql
WITH p AS (
    SELECT TIMESTAMPTZ '2025-05-10 12:00:00+00' AS as_of
)
SELECT e.event_id
FROM demo_activity AS e
CROSS JOIN p
WHERE e.occurred_at >= p.as_of - INTERVAL '1 hour'
  AND e.occurred_at < p.as_of
ORDER BY e.event_id;
```

**Đáp án:** `2, 3`. Sự kiện `4` đúng 12:00 nên bị loại theo quy tắc khoảng mở bên phải.

### Bài 4 — Chỉ tính sự kiện success

Thêm điều kiện `status = 'success'` vào bài 3.

**Đáp án:** Chỉ sự kiện `2`. Sự kiện `3` thuộc khoảng thời gian nhưng có trạng thái `pending`.

### Bài 5 — Ngày theo giờ Việt Nam

Sự kiện xảy ra lúc `2025-05-09 18:30 UTC` thuộc ngày nào theo `Asia/Ho_Chi_Minh`?

```sql
SELECT (
    TIMESTAMPTZ '2025-05-09 18:30:00+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)::date AS vietnam_date;
```

**Đáp án:** `2025-05-10`, vì thời gian địa phương là 01:30 ngày 10/5.

### Bài 6 — Có được dùng CURRENT_TIMESTAMP trong generated column?

```sql
CREATE TABLE bad_generated (
    created_at TIMESTAMPTZ,
    age_seconds DOUBLE PRECISION GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - created_at)
    ) STORED
);
```

**Đáp án:** Không trong PostgreSQL, vì biểu thức generated stored phải immutable nhưng `CURRENT_TIMESTAMP` phụ thuộc transaction. Nếu cần “tuổi hiện tại”, tính `CURRENT_TIMESTAMP - created_at` khi truy vấn hoặc tính từ một `as_of` được truyền vào; nếu cần tuổi tại một sự kiện cụ thể, lưu mốc sự kiện đó.

### Bài 7 — Vì sao không tạo partial index “7 ngày gần nhất”?

```sql
CREATE INDEX bad_idx
ON demo_activity (event_id)
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '7 days';
```

**Đáp án:** PostgreSQL không chấp nhận hàm không immutable trong predicate của index. Index không thể tự thay đổi tập thành viên chỉ vì đồng hồ tiến lên. Hãy index `occurred_at` rồi sử dụng điều kiện thời gian tại lúc truy vấn.

### Bài 8 — Số liệu có thể thay đổi mà bảng không đổi không?

```sql
SELECT COUNT(*)
FROM demo_activity
WHERE occurred_at >= statement_timestamp() - INTERVAL '24 hours';
```

**Đáp án:** Có. Các sự kiện có thể trôi ra ngoài cửa sổ 24 giờ khi thời gian trôi, ngay cả khi bảng giữ nguyên. Kết quả được xác định tại mốc statement; muốn kiểm chứng lặp lại, truyền `as_of`.

### Bài 9 — Phân biệt ba thời gian của một đơn hàng

Một đơn được tạo ở ứng dụng lúc 09:00, gửi lên server 09:05, bắt đầu transaction nhập lúc 09:06 và commit lúc 09:10. Nếu cột `created_at DEFAULT CURRENT_TIMESTAMP` được gán trong transaction PostgreSQL, nó biểu diễn mốc nào?

**Đáp án:** Khoảng **09:06**, thời điểm transaction bắt đầu, không tự động là 09:00, 09:05 hoặc 09:10. Nếu nghiệp vụ cần cả thời điểm phát sinh và thời điểm tiếp nhận, thiết kế các cột riêng; `created_at` không tự làm được cả ba vai trò.

### Bài 10 — Chuyển truy vấn phụ thuộc đồng hồ thành truy vấn có thể test

Yêu cầu viết lại:

```sql
SELECT event_id
FROM demo_activity
WHERE occurred_at >= NOW() - INTERVAL '1 hour'
  AND occurred_at < NOW();
```

để test dùng mốc `2025-05-10 12:00 UTC`.

**Đáp án:**

```sql
WITH params AS (
    SELECT TIMESTAMPTZ '2025-05-10 12:00:00+00' AS as_of
)
SELECT event_id
FROM demo_activity
CROSS JOIN params
WHERE occurred_at >= as_of - INTERVAL '1 hour'
  AND occurred_at < as_of
ORDER BY event_id;
```

Kết quả `2, 3`, và truy vấn có thể chạy lại với mốc giống nhau.

### Bài 11 — CURRENT_TIMESTAMP và thời điểm kết thúc

Nếu cần tính thời lượng chờ ngay trong một transaction dài, tại sao không lấy `CURRENT_TIMESTAMP` ở đầu và cuối?

**Đáp án:** Cả hai có thể trả **cùng thời điểm bắt đầu transaction**, nên hiệu số bằng 0 dù thời gian thực trôi qua. Trong PostgreSQL có thể dùng `clock_timestamp()` cho các mốc đo trong SQL; ở ứng dụng cần cân nhắc đồng hồ monotonic để đo thời lượng chính xác.

### Bài 12 — Có nên khai báo hàm đọc bảng là IMMUTABLE?

Một hàm nhận `customer_id` và đọc bảng `customers` để trả tên hiện tại. Nếu bảng có thể sửa tên khách, có được khai báo hàm `IMMUTABLE` không?

**Đáp án:** Không. Cùng `customer_id` có thể cho tên khác khi bảng thay đổi. Nếu mục tiêu là hàm chỉ đọc ổn định trong một statement theo snapshot, hãy nghiên cứu `STABLE`; nếu cần quan sát tác động giữa các lần gọi hoặc có sửa dữ liệu, xem `VOLATILE`. Nhãn phải phản ánh hành vi thật, không phụ thuộc mong muốn tối ưu.

## 18. Quy trình suy luận khi gặp hàm thời gian

Trước khi đặt `NOW()`, `CURRENT_TIMESTAMP` hoặc một biểu thức thời gian vào SQL, hãy tự hỏi:

1. **Mốc muốn lấy là gì?** Đầu transaction, đầu statement, đồng hồ tại lần gọi, thời gian sự kiện hay thời gian người dùng chọn?
2. **Biểu thức cần ổn định trong phạm vi nào?** Một hàng, một câu SQL, một transaction, một job báo cáo hay mọi lần chạy lại?
3. **Có cần chạy lại với kết quả cũ không?** Nếu có, truyền `as_of` rõ ràng và ghi lại mốc dùng cho báo cáo.
4. **Múi giờ nghiệp vụ nào được áp dụng?** UTC, múi giờ người dùng hay múi giờ tổ chức; đặc biệt khi tính “hôm nay”/“tháng này”.
5. **Giá trị được tính khi đọc hay lưu khi ghi?** `DEFAULT CURRENT_TIMESTAMP` ghi một giá trị; một biểu thức ở `SELECT` được xét khi truy vấn.
6. **Có dùng biểu thức trong index hoặc generated column không?** PostgreSQL yêu cầu tính bất biến phù hợp, không thể đặt hàm thời gian động tùy ý.
7. **Kết quả có được cache/materialize không?** Dữ liệu có thể trở nên cũ chỉ do thời gian trôi qua, không cần bảng thay đổi.
8. **Có ứng dụng nhiều DBMS không?** Kiểm tra định nghĩa và phạm vi của hàm ở từng engine; `NOW()` trùng tên không đồng nghĩa trùng hành vi.
9. **Hàm tự định nghĩa có mô tả đúng độ biến động không?** Không gắn nhãn `IMMUTABLE` cho hàm phụ thuộc đồng hồ, bảng thay đổi hay ngữ cảnh ẩn.
10. **Dữ liệu mẫu có đủ ranh giới để kiểm chứng không?** Thử đúng đầu kỳ, đúng cuối kỳ, sát nửa đêm, khác timezone, transaction dài và giá trị thiếu.

Khi hiểu rõ **biểu thức xác định theo đầu vào**, **hàm ổn định theo phạm vi câu lệnh**, và **hàm đọc trạng thái thay đổi theo thời gian**, bạn sẽ viết SQL có kết quả giải thích được, thiết kế chỉ mục hợp lệ, lưu thời điểm đúng ý nghĩa nghiệp vụ và tạo kiểm thử ít phụ thuộc đồng hồ thực hơn.

