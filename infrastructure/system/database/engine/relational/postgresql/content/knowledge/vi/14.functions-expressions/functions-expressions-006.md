# Thời điểm giao dịch, câu lệnh và đồng hồ thực trong PostgreSQL

Khi ghi thời gian tạo đơn hàng, kiểm tra một token đã hết hạn hay đo một truy vấn chạy bao lâu, chúng ta thường nghĩ chỉ cần gọi “thời gian hiện tại”. Nhưng trong PostgreSQL có **nhiều khái niệm thời điểm hiện tại**, tùy theo mốc muốn quan sát:

- **Bắt đầu giao dịch** (*transaction start time*).
- **Bắt đầu câu lệnh SQL** (*statement start time*).
- **Thời điểm đồng hồ thực được đọc ngay lúc gọi hàm** (*wall-clock time*).

Ba mốc này có thể gần như trùng nhau khi một `SELECT` rất nhanh chạy ở chế độ autocommit. Chúng trở nên khác biệt khi một transaction tồn tại lâu, có nhiều câu SQL, chờ khóa, thực hiện phép tính tốn thời gian hoặc gọi các hàm nhiều lần.

Ví dụ, một ứng dụng mở transaction, dành 10 giây kiểm tra dữ liệu, rồi chèn đơn hàng. Nếu cột `created_at` có `DEFAULT now()`, dấu thời gian ghi vào cột phản ánh **lúc transaction bắt đầu**, không phải nhất thiết là giây thực tế mà `INSERT` được thực hiện. Điều này đúng theo thiết kế của PostgreSQL, nhưng dễ khiến người mới tưởng database ghi sai giờ.

Bài học phân biệt những hàm thời gian liên quan, cách chúng hoạt động với MVCC/transaction, ảnh hưởng của kiểu `timestamp` và múi giờ, cũng như cách chọn đúng mốc cho log, audit, thời hạn, báo cáo và ứng dụng Java.

## 1. Ba chiếc đồng hồ: ý nghĩa trước cú pháp

Hãy tưởng tượng một transaction gồm nhiều câu lệnh:

```text
Trục thời gian thực

10:00:00       10:00:03       10:00:07       10:00:09
    |              |              |              |
   BEGIN          SELECT          INSERT         COMMIT
    |              |              |              |
    +------------ transaction -------------------+
                   ^              ^
             statement 1     statement 2

transaction_timestamp()  -> khoảng mốc 10:00:00 xuyên transaction
statement_timestamp()    -> khoảng 10:00:03 ở SELECT,
                            khoảng 10:00:07 ở INSERT
clock_timestamp()        -> giờ tường minh tại mỗi lần gọi hàm
```

Đây là sơ đồ minh họa: “10:00:00” đại diện thời điểm bắt đầu transaction, còn thời điểm giao dịch thực tế của PostgreSQL phụ thuộc lúc server nhận/làm việc với thông điệp lệnh. Không dùng các số trong sơ đồ làm kết quả dự đoán chính xác từng microsecond.

### 1.1. Transaction timestamp

Hàm `transaction_timestamp()` trả thời điểm **bắt đầu transaction hiện hành**. Nó giữ cùng một giá trị từ khi transaction bắt đầu cho đến khi kết thúc, bất kể bên trong có bao nhiêu statement.

Các cách viết thông dụng tương đương ở khía cạnh mốc thời gian này:

```sql
SELECT
    transaction_timestamp() AS transaction_started,
    now()                  AS now_value,
    CURRENT_TIMESTAMP      AS current_timestamp_value;
```

Đối với một transaction, ba giá trị phản ánh cùng mốc transaction start. `CURRENT_TIMESTAMP` là cú pháp chuẩn SQL, `now()` là hàm quen thuộc trong PostgreSQL.

### 1.2. Statement timestamp

`statement_timestamp()` trả thời điểm bắt đầu **câu lệnh SQL hiện tại**. Tài liệu PostgreSQL mô tả chính xác hơn là thời điểm server nhận thông điệp lệnh mới nhất từ client.

Trong một transaction có ba câu lệnh được gửi vào những thời điểm khác nhau, `statement_timestamp()` có thể khác giữa ba câu lệnh, nhưng giữ mốc của chính câu lệnh trong lúc câu lệnh chạy.

### 1.3. Clock timestamp

`clock_timestamp()` đọc **thời gian đồng hồ thực tại thời điểm thực thi lời gọi**. Giá trị có thể thay đổi ngay **trong cùng một statement**, thậm chí giữa những hàng của một truy vấn dài.

Đây là khác biệt lớn nhất với hai hàm trên: PostgreSQL không “đóng băng” `clock_timestamp()` theo transaction hoặc statement.

### 1.4. Bảng so sánh nhanh

| Biểu thức | Mốc thời gian | Thay đổi trong cùng statement? | Thay đổi giữa các statement của cùng transaction? | Kiểu trả về |
| --- | --- | --- | --- | --- |
| `transaction_timestamp()` | Bắt đầu transaction | Không | Không | `timestamp with time zone` (`timestamptz`) |
| `now()` | Bắt đầu transaction | Không | Không | `timestamptz` |
| `CURRENT_TIMESTAMP` | Bắt đầu transaction | Không | Không | `timestamptz` |
| `statement_timestamp()` | Bắt đầu statement | Không, cùng mốc của statement | Có thể có | `timestamptz` |
| `clock_timestamp()` | Đồng hồ thực khi gọi | Có thể có | Có thể có | `timestamptz` |
| `timeofday()` | Đồng hồ thực khi gọi | Có thể có | Có thể có | `text` |

“Có thể thay đổi” không bảo đảm **mọi lời gọi** có giá trị khác nhau: hai lời gọi rất sát nhau có thể cùng giá trị theo độ phân giải đồng hồ; đồng hồ hệ thống cũng có thể được điều chỉnh. Vì vậy không dùng `clock_timestamp()` làm nguồn tạo ID duy nhất.

## 2. Ví dụ mở đầu: cùng một SELECT

Chạy:

```sql
SELECT
    transaction_timestamp() AS tx_time,
    now() AS now_time,
    CURRENT_TIMESTAMP AS sql_current_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_time;
```

Trong một câu `SELECT` đơn giản, năm giá trị có thể chỉ lệch nhau rất ít; `transaction_timestamp()`, `now()` và `CURRENT_TIMESTAMP` phải phản ánh cùng mốc transaction. Nếu server đang xử lý transaction đã mở từ trước, `statement_timestamp()` có thể mới hơn đáng kể so với `transaction_timestamp()`.

Không nên dựa vào sự chênh lệch nhỏ ở bài thử này để kết luận các hàm là một. Phải thử **nhiều statement trong cùng transaction** hoặc làm cho thời gian trôi qua trong một statement.

### 2.1. Kiểm tra kiểu dữ liệu

```sql
SELECT
    pg_typeof(now()) AS now_type,
    pg_typeof(statement_timestamp()) AS statement_type,
    pg_typeof(clock_timestamp()) AS clock_type,
    pg_typeof(timeofday()) AS legacy_text_type;
```

Ba hàm timestamp đầu trả `timestamp with time zone`. `timeofday()` trả `text`: nó được giữ cho khả năng tương thích lịch sử và không thuận tiện bằng các giá trị thời gian có kiểu để tính toán hoặc so sánh.

### 2.2. Quan hệ giữa các giá trị

`now()` và `CURRENT_TIMESTAMP` không phải hai lần “đọc giờ máy” độc lập. Khi đứng trong cùng một transaction, chúng sử dụng cùng giá trị transaction start. Nếu chúng hiển thị khác nhau ở hai lần thử, trước hết kiểm tra bạn có đang so **hai transaction khác nhau** hoặc có thay đổi múi giờ/định dạng hay không.

## 3. Thí nghiệm 1: nhiều statement trong một transaction

Hãy chạy **tuần tự trong cùng một kết nối PostgreSQL**, chẳng hạn một cửa sổ `psql`. Đừng gửi mỗi dòng vào các kết nối khác nhau qua một tool tự mở session mới.

```sql
BEGIN;

SELECT
    transaction_timestamp() AS tx_at_step_1,
    statement_timestamp() AS stmt_at_step_1,
    clock_timestamp() AS wall_at_step_1;

SELECT pg_sleep(1.5);

SELECT
    transaction_timestamp() AS tx_at_step_2,
    statement_timestamp() AS stmt_at_step_2,
    clock_timestamp() AS wall_at_step_2;

COMMIT;
```

`pg_sleep(1.5)` được PostgreSQL thực hiện để chờ khoảng 1,5 giây. Khi chạy trên lab, độ chờ thực có thể dài hơn mức yêu cầu do hệ thống và scheduler.

**Điều cần quan sát:**

- `tx_at_step_1` và `tx_at_step_2` bằng nhau vì cả hai `SELECT` thuộc cùng transaction.
- `stmt_at_step_2` muộn hơn `stmt_at_step_1` vì câu `SELECT` thứ hai được gửi sau khi đã chờ.
- `wall_at_step_2` muộn hơn `wall_at_step_1` trong điều kiện đồng hồ hệ thống không bị chỉnh ngược đáng kể.
- Trong mỗi `SELECT`, `statement_timestamp()` là một mốc cố định, không phải đồng hồ được cập nhật sau từng biểu thức.

### 3.1. Một SELECT cuối transaction không trả “thời điểm commit”

`transaction_timestamp()` vẫn là thời điểm **bắt đầu** transaction ngay trước `COMMIT`. `clock_timestamp()` ở câu `SELECT` cuối là lúc đọc đồng hồ trong statement đó, **không phải** thời điểm commit cuối cùng.

Nếu một ứng dụng cần biết thời điểm commit thực để đối soát giao dịch, đừng tùy tiện gọi `now()` là “committed_at”. Dấu thời gian do transaction ghi thường được tính **trước** khi commit thành công; transaction còn có thể rollback.

### 3.2. Ranh giới BEGIN và thời gian server nhận câu lệnh

Trong explicit transaction, lệnh `BEGIN` mở transaction trước những `SELECT` tiếp theo. Vì vậy transaction timestamp có thể sớm hơn statement timestamp ngay ở câu `SELECT` đầu nếu có một khoảng chờ giữa `BEGIN` và `SELECT`.

Điều đó không trái với nguyên tắc: transaction start là một mốc, statement start của mỗi câu lệnh là mốc khác.

## 4. Thí nghiệm 2: đồng hồ thay đổi trong cùng một statement

Để làm rõ `clock_timestamp()`, dùng một khối PL/pgSQL `DO` có hai lệnh `RAISE NOTICE` và một lần chờ ở giữa:

```sql
DO $$
BEGIN
    RAISE NOTICE 'Lúc đầu: tx=%, stmt=%, wall=%',
        transaction_timestamp(),
        statement_timestamp(),
        clock_timestamp();

    PERFORM pg_sleep(1.5);

    RAISE NOTICE 'Sau khi chờ: tx=%, stmt=%, wall=%',
        transaction_timestamp(),
        statement_timestamp(),
        clock_timestamp();
END;
$$;
```

`DO ...` là một statement do client gửi, dù bên trong thực hiện nhiều câu lệnh PL/pgSQL. Vì thế:

- `transaction_timestamp()` giữ nguyên trong khối.
- `statement_timestamp()` giữ nguyên vì vẫn thuộc một statement từ phía client.
- `clock_timestamp()` được đọc lại sau khoảng chờ, nên thông thường muộn hơn khoảng 1,5 giây.

**Ưu điểm của ví dụ này:** thứ tự `RAISE NOTICE → pg_sleep → RAISE NOTICE` được quy định bởi các câu lệnh trong PL/pgSQL. Nó tránh việc suy luận sai rằng PostgreSQL nhất thiết đánh giá các biểu thức trong một select list theo thứ tự từ trái sang phải.

### 4.1. Vì sao không dùng SELECT clock_timestamp(), pg_sleep(), clock_timestamp() để khẳng định thứ tự?

Một câu:

```sql
SELECT
    clock_timestamp() AS first_clock,
    pg_sleep(1) AS pause,
    clock_timestamp() AS second_clock;
```

có thể trông rất trực quan. Tuy nhiên, SQL nói chung không dùng **thứ tự xuất hiện các biểu thức độc lập trong select list** làm hợp đồng bắt buộc để điều khiển side effect. Khi cần minh chứng thứ tự thời gian chắc chắn, hãy sử dụng các statement PL/pgSQL nối tiếp như ở trên, hoặc đo từ phía client theo cơ chế phù hợp.

## 5. Autocommit: vì sao các hàm đôi khi có vẻ giống nhau?

Trong nhiều công cụ PostgreSQL, mỗi câu SQL độc lập được thực hiện trong transaction riêng nếu người dùng không mở transaction tường minh.

Ví dụ:

```sql
SELECT transaction_timestamp(), statement_timestamp(), clock_timestamp();

SELECT pg_sleep(2);

SELECT transaction_timestamp(), statement_timestamp(), clock_timestamp();
```

Khi mỗi `SELECT` là một transaction tự động riêng:

- Lời gọi `transaction_timestamp()` ở câu đầu khác lời gọi ở câu cuối, vì đã chuyển sang transaction khác.
- `statement_timestamp()` cũng khác do nhận câu lệnh mới.
- `clock_timestamp()` đọc giờ thực ở mỗi câu.

Thấy cả ba đều tăng **không chứng minh** chúng hoạt động giống nhau. Muốn so sánh ranh giới, phải mở `BEGIN ... COMMIT` trong cùng session hoặc dùng khối `DO`.

### 5.1. Tương tác với connection pooling

Một ứng dụng Java có HikariCP hoặc pool khác có thể lấy các connection khác nhau cho hai request hoặc hai transaction. Nếu truy vấn thời gian nằm ở các session khác nhau, đừng mặc định chúng thuộc cùng transaction chỉ vì chúng được gọi từ cùng một phương thức ứng dụng.

Ngược lại, khi service mở transaction trong cùng connection, nhiều truy vấn có thể chia sẻ cùng `transaction_timestamp()` dù được gọi ở nhiều method Java.

## 6. CURRENT_TIMESTAMP và các biểu thức thời gian chuẩn SQL

PostgreSQL hỗ trợ nhiều biểu thức SQL cung cấp thời gian:

| Biểu thức | Kiểu kết quả | Mốc thời gian trong PostgreSQL |
| --- | --- | --- |
| `CURRENT_TIMESTAMP` | `timestamp with time zone` | Bắt đầu transaction. |
| `CURRENT_TIMESTAMP(3)` | `timestamp(3) with time zone` | Bắt đầu transaction với độ chính xác hiển thị/biểu diễn quy định. |
| `CURRENT_DATE` | `date` | Ngày tương ứng thời điểm bắt đầu transaction theo múi giờ session. |
| `CURRENT_TIME` | `time with time zone` | Thời gian trong ngày theo mốc transaction và timezone. |
| `CURRENT_TIME(3)` | `time(3) with time zone` | Như trên với độ chính xác phần giây quy định. |
| `LOCALTIME` | `time without time zone` | Giờ địa phương theo mốc transaction. |
| `LOCALTIMESTAMP` | `timestamp without time zone` | Ngày giờ địa phương theo mốc transaction. |

Thử:

```sql
SELECT
    CURRENT_DATE AS today_in_session_zone,
    CURRENT_TIME AS local_clock_with_offset,
    LOCALTIME AS local_clock_without_zone,
    CURRENT_TIMESTAMP AS current_timestamp_with_zone,
    LOCALTIMESTAMP AS local_timestamp_without_zone;
```

### 6.1. “CURRENT” không nhất thiết là giờ tại lúc đang đọc

Tên `CURRENT_TIMESTAMP` nghe như “đồng hồ thực ngay bây giờ”, nhưng trong PostgreSQL nó **đóng băng theo transaction start**.

Điều này đặc biệt quan trọng nếu transaction đi qua nửa đêm. `CURRENT_DATE` có thể vẫn là ngày bắt đầu transaction dù đồng hồ thực đã sang ngày mới trong cùng một cấu hình múi giờ.

### 6.2. Độ chính xác của phần giây

`CURRENT_TIMESTAMP(0)`, `CURRENT_TIMESTAMP(3)` và `CURRENT_TIMESTAMP(6)` biểu diễn độ chính xác phần giây khác nhau, trong đó mức `3` thường tương đương đến mili giây. PostgreSQL hỗ trợ độ chính xác dấu thời gian đến mức phụ giây phụ thuộc kiểu/khả năng hệ thống; tăng số chữ số không làm đồng hồ máy thực tế chính xác hơn.

```sql
SELECT
    CURRENT_TIMESTAMP(0) AS seconds_precision,
    CURRENT_TIMESTAMP(3) AS milliseconds_precision,
    CURRENT_TIMESTAMP(6) AS microseconds_precision;
```

Độ chính xác khai báo còn ảnh hưởng cách làm tròn/lưu giá trị. Một cột `timestamptz(0)` không phù hợp nếu cần giữ phần mili giây hoặc microsecond cho audit.

## 7. now(), transaction_timestamp() và các cách viết dễ nhầm

Trong PostgreSQL:

```sql
SELECT
    now() = transaction_timestamp() AS same_tx_time,
    now() = CURRENT_TIMESTAMP AS same_sql_current_time;
```

Kết quả mong đợi là hai cột boolean `true`.

### 7.1. Một lỗi với literal 'now' trong DEFAULT

PostgreSQL hiểu một số chuỗi ngày giờ đặc biệt như `'now'` khi chuyển kiểu. Nhưng **literal được chuyển kiểu tại thời điểm parse** có thể bị cố định sớm hơn thời điểm mà bạn muốn đánh giá.

Ví dụ **không nên dùng** làm default động:

```sql
-- Không khuyến nghị:
-- CREATE TABLE bad_time_defaults (
--     id bigint PRIMARY KEY,
--     created_at timestamptz DEFAULT 'now'::timestamptz
-- );
```

Hình thức literal `'now'::timestamptz` có thể được chuyển thành một hằng timestamp khi PostgreSQL phân tích cú pháp định nghĩa, khiến default giữ một mốc đã cố định. Để PostgreSQL đánh giá tại lúc statement/transaction thực thi theo chính sách muốn có, dùng hàm:

```sql
CREATE TABLE IF NOT EXISTS clock_lab_example (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Đây là bảng ví dụ độc lập. `DEFAULT now()` **không phải giờ đồng hồ thực của thao tác INSERT nếu transaction đã bắt đầu từ lâu**; nó trả transaction start. Nếu cần thời điểm nhận statement hoặc giờ thực, chọn hàm tương ứng.

### 7.2. now() không phải thời điểm commit

Tên `now()` chỉ là một alias quen thuộc cho mốc transaction. Nó không đại diện cho:

- Thời điểm transaction được commit thành công.
- Thời điểm hàng đã nhìn thấy với mọi session.
- Thời điểm thông điệp được ứng dụng bên ngoài nhận.
- Thời điểm sự kiện được gửi ra message broker.

Nếu nghiệp vụ cần các mốc này, phải xác định luồng ghi/commit/phát sự kiện phù hợp, chứ không đổi tên `now()` thành `committed_at` rồi coi như đã giải bài toán.

## 8. timeofday(): hàm lịch sử trả text

PostgreSQL có hàm:

```sql
SELECT
    timeofday() AS formatted_wall_clock,
    pg_typeof(timeofday()) AS result_type;
```

Hàm `timeofday()` lấy thời gian đồng hồ thực giống mục đích của `clock_timestamp()`, nhưng trả về **chuỗi văn bản được định dạng**, không phải một giá trị kiểu `timestamptz`.

Vì thế:

- Không nên dùng `timeofday()` làm mặc định cho cột thời gian có kiểu chính xác.
- Không nên so sánh/sắp xếp theo chuỗi `timeofday()` như thể nó là timestamp.
- Để tính khoảng thời gian, dùng `clock_timestamp()` và phép trừ giữa các timestamp.
- Hàm được giữ chủ yếu vì tương thích lịch sử; các hệ thống mới thường không cần dùng.

Ví dụ:

```sql
SELECT
    clock_timestamp() AS wall_as_timestamptz,
    timeofday() AS wall_as_text;
```

Hai lời gọi được thực hiện ở những thời điểm rất gần nhau chứ không nhất thiết có cùng giá trị từng chữ số cuối. `timeofday()` không phải cách xuất/nhập datetime có cấu trúc được khuyến nghị.

## 9. Phân biệt timestamptz và timestamp without time zone

Ba hàm chính đều trả `timestamptz` — viết đầy đủ là `timestamp with time zone`.

### 9.1. timestamptz biểu diễn một thời điểm tuyệt đối

PostgreSQL lưu `timestamptz` theo ý tưởng một **instant** trên trục thời gian. Khi hiển thị, PostgreSQL chuyển giá trị đó sang múi giờ của session. Nó **không lưu tên múi giờ gốc** đã dùng khi nhập (ví dụ `Asia/Ho_Chi_Minh`) như một thuộc tính riêng của từng giá trị.

```sql
SHOW TIME ZONE;

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS actual_wall_time;
```

Hai session có `TimeZone` khác nhau có thể hiển thị **hai chuỗi ngày giờ khác nhau** cho cùng một instant.

### 9.2. timestamp without time zone không tự nói đây là giờ của nơi nào

`timestamp without time zone` lưu ngày giờ theo lịch nhưng không mang thông tin offset/timezone để xác định một instant tuyệt đối.

Ví dụ:

```sql
SELECT
    TIMESTAMP '2026-07-01 19:00:00'
        AS local_datetime_without_zone,
    TIMESTAMPTZ '2026-07-01 12:00:00+00'
        AS instant_with_zone;
```

Hai giá trị có thể mô tả cùng một khoảnh khắc **nếu** timestamp không zone được hiểu là giờ Việt Nam (UTC+7). Nhưng PostgreSQL không tự biết một giá trị `timestamp without time zone` luôn thuộc múi giờ nào.

### 9.3. Đổi cách hiển thị bằng SET TIME ZONE

Chạy trong một session:

```sql
SET TIME ZONE 'UTC';

SELECT TIMESTAMPTZ '2026-07-01 12:00:00+00' AS visible_time;

SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-07-01 12:00:00+00' AS visible_time;
```

Kết quả về ý nghĩa:

```text
TimeZone = UTC:
  2026-07-01 12:00:00+00

TimeZone = Asia/Ho_Chi_Minh:
  2026-07-01 19:00:00+07
```

Đây là **cùng một instant**, chỉ khác cách thể hiện. Lệnh `SET TIME ZONE` thay đổi cấu hình session; khi thử xong có thể `RESET TIME ZONE;` nếu muốn trở về cấu hình trước.

### 9.4. AT TIME ZONE: hai hướng chuyển đổi

Với một `timestamptz`, `AT TIME ZONE` tạo giá trị giờ địa phương ở kiểu `timestamp without time zone`:

```sql
SELECT
    TIMESTAMPTZ '2026-07-01 12:00:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_local_time;
```

Kết quả là `2026-07-01 19:00:00` (không kèm offset vì kiểu đầu ra không mang timezone).

Ngược lại, với một `timestamp without time zone`, `AT TIME ZONE` có thể diễn giải ngày giờ đó là thuộc múi giờ xác định để tạo `timestamptz`:

```sql
SELECT
    TIMESTAMP '2026-07-01 19:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS interpreted_instant;
```

Instant thu được tương ứng 12:00 UTC, dù cách hiển thị còn tùy `TimeZone` của session.

### 9.5. Current date phải được hiểu theo múi giờ

`CURRENT_DATE` phản ánh ngày từ transaction timestamp trong timezone session. Khi tổng hợp theo “ngày Việt Nam”, nên ghi rõ timezone:

```sql
SELECT
    (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS vietnam_wall_date,
    (statement_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS vietnam_statement_date,
    (transaction_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS vietnam_transaction_date;
```

Ba ngày có thể khác nhau khi transaction kéo dài qua nửa đêm hoặc khi mốc statement nằm gần ranh giới ngày.

Múi giờ có chuyển đổi DST (giờ mùa hè) còn làm một số giờ địa phương bị lặp hoặc không tồn tại. Nếu lưu sự kiện cần thời điểm tuyệt đối, ưu tiên `timestamptz` rồi chuyển múi giờ khi hiển thị, không tự “cộng 7 giờ” cho mọi khu vực.

## 10. Tạo bảng thử nghiệm: ba DEFAULT cho ba mốc

Để thấy tác động lên dữ liệu ghi thực, tạo schema và bảng riêng:

```sql
CREATE SCHEMA IF NOT EXISTS clock_lab;

CREATE TABLE clock_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    note text NOT NULL,
    tx_started_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    statement_started_at timestamptz NOT NULL
        DEFAULT statement_timestamp(),
    recorded_wall_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);
```

Bảng có ba cột thời gian để so sánh **mục đích**, không phải khuyến nghị rằng mọi bảng production đều cần lưu cả ba.

### 10.1. Chèn hai hàng ở hai statement trong cùng transaction

```sql
BEGIN;

INSERT INTO clock_lab.events (note)
VALUES ('first-in-transaction');

SELECT pg_sleep(1.5);

INSERT INTO clock_lab.events (note)
VALUES ('second-in-transaction');

SELECT
    event_id,
    note,
    tx_started_at,
    statement_started_at,
    recorded_wall_at
FROM clock_lab.events
ORDER BY event_id;

ROLLBACK;
```

Trong môi trường lab, hai hàng mới có:

- `tx_started_at` bằng nhau vì transaction chưa đổi.
- `statement_started_at` khác nhau theo hai lệnh `INSERT` cách nhau 1,5 giây.
- `recorded_wall_at` thường gần thời điểm thực hiện default của từng hàng; do đó thường cũng khác nhau.

`ROLLBACK` hủy hai hàng vừa chèn. Nếu đã có dữ liệu `clock_lab.events` từ trước, lệnh `SELECT` trên toàn bảng sẽ thấy cả dữ liệu cũ; có thể thêm điều kiện `WHERE note IN (...)` khi cần chỉ quan sát hai hàng thử.

**Lưu ý:** sequence/identity trong PostgreSQL có thể đã tăng dù transaction rollback. Đừng dùng việc các `event_id` có liên tục hay không để đánh giá tính đúng đắn của các timestamp.

### 10.2. Nếu hai câu INSERT cùng một transaction, default now() có “sai” không?

Không. Giá trị `tx_started_at` cố ý phản ánh **thời điểm giao dịch bắt đầu**. Nếu trường cần mô tả “mọi hành động trong cùng transaction có cùng batch time” thì đó là điều mong muốn.

Nếu cần “thời điểm statement được server nhận”, dùng `statement_timestamp()`. Nếu cần “lúc biểu thức được thực thi ở đồng hồ hệ thống”, dùng `clock_timestamp()`.

Không có một lựa chọn đúng cho mọi bảng; tên cột nên khớp với **ý nghĩa thời gian**.

## 11. Một INSERT nhiều hàng: giá trị nào đồng nhất?

Giả sử thêm nhiều hàng bằng một statement:

```sql
BEGIN;

INSERT INTO clock_lab.events (note)
SELECT 'bulk-' || g::text
FROM generate_series(1, 5) AS g;

SELECT
    event_id,
    note,
    tx_started_at,
    statement_started_at,
    recorded_wall_at
FROM clock_lab.events
WHERE note LIKE 'bulk-%'
ORDER BY event_id;

ROLLBACK;
```

Trong cùng một `INSERT`:

- `tx_started_at` giống nhau cho các hàng vì cùng transaction.
- `statement_started_at` giống nhau cho các hàng vì cùng statement.
- `recorded_wall_at` là kết quả `clock_timestamp()` có thể được lấy khi từng hàng xử lý; các giá trị **có thể** khác nhau, nhưng với thao tác rất nhanh chúng cũng có thể trùng nhau theo độ phân giải đồng hồ.

Nếu nghiệp vụ cần tất cả hàng của một batch có **một giá trị duy nhất**, nên chủ động chọn mốc transaction/statement hoặc truyền một giá trị batch timestamp duy nhất từ service. Đừng dựa vào việc đồng hồ thực tình cờ trả các số giống nhau.

### 11.1. Statement timestamp hữu ích cho batch

Nếu một câu `INSERT ... SELECT` xử lý 500.000 hàng trong vài giây, `statement_timestamp()` vẫn là mốc bắt đầu của cả statement. Điều đó thuận tiện nếu muốn đóng dấu thời điểm **bắt đầu xử lý batch**, không phải thời điểm từng hàng đã được xử lý xong.

Trường hợp cần mốc hoàn tất batch, phải xác định cách đo riêng, vì statement timestamp không phải end time.

## 12. Đo độ dài transaction và statement

Có thể đo khoảng thời gian từ mốc giao dịch hoặc statement đến đồng hồ thực:

```sql
SELECT
    clock_timestamp() - transaction_timestamp()
        AS elapsed_since_transaction_start,
    clock_timestamp() - statement_timestamp()
        AS elapsed_since_statement_start;
```

Kết quả là kiểu `interval`. Hai lời gọi `clock_timestamp()` có thể ở những thời điểm sát nhau nhưng không phải cùng một instant.

### 12.1. Lấy một mẫu đồng hồ để so sánh công bằng

Nếu muốn hai phép trừ dựa trên **cùng một mẫu wall clock**:

```sql
WITH sampled AS MATERIALIZED (
    SELECT clock_timestamp() AS observed_at
)
SELECT
    observed_at,
    observed_at - transaction_timestamp() AS tx_age,
    observed_at - statement_timestamp() AS statement_age
FROM sampled;
```

Từ PostgreSQL 12, `AS MATERIALIZED` có thể dùng để chỉ rõ mốc `observed_at` được tạo trong CTE phù hợp. Với một CTE một hàng chứa hàm volatile, PostgreSQL còn có những quy tắc tránh inline khác; ví dụ trên chủ yếu minh họa ý định dùng **một timestamp mẫu**.

Độ dài ước lượng vẫn bị ảnh hưởng nếu đồng hồ hệ điều hành thay đổi bất thường. Với metric latency cần độ tin cậy cao, dùng công cụ theo dõi chuyên dụng hoặc bộ đếm thời gian monotonic ở tầng ứng dụng khi thích hợp.

### 12.2. Chuyển interval sang số giây

```sql
WITH sample AS MATERIALIZED (
    SELECT clock_timestamp() AS observed_at
)
SELECT
    EXTRACT(EPOCH FROM
        (observed_at - transaction_timestamp())
    ) AS seconds_since_tx_start,
    EXTRACT(EPOCH FROM
        (observed_at - statement_timestamp())
    ) AS seconds_since_statement_start
FROM sample;
```

`EXTRACT(EPOCH FROM interval)` cho số giây tương ứng với khoảng thời gian; có thể chứa phần thập phân.

**Không nhầm hai thao tác:**

- `EXTRACT(EPOCH FROM some_timestamptz)` lấy thời điểm theo số giây epoch.
- `EXTRACT(EPOCH FROM some_interval)` lấy **độ dài khoảng thời gian** theo giây.

### 12.3. Đo một câu SQL dài

Trong một câu `SELECT pg_sleep(1.5)`, thời gian chờ phát sinh trong statement. Lời gọi `statement_timestamp()` ở **statement kế tiếp** sẽ phản ánh mốc của statement mới, không giúp lấy lại chính xác start time của statement trước. Để đo statement đã chạy, sử dụng công cụ ở client, logging/database monitoring hoặc các cột thống kê tương ứng.

Không gán chênh lệch `clock_timestamp() - statement_timestamp()` của một câu SELECT ngắn sau khi query dài đã xong thành thời gian query dài — đó là hai statement khác nhau.

## 13. Xem thời gian phiên và truy vấn đang chạy bằng pg_stat_activity

PostgreSQL có view hệ thống `pg_stat_activity`, thường chứa các trường:

- `backend_start`: thời điểm process backend bắt đầu.
- `xact_start`: thời điểm transaction hiện tại bắt đầu, hoặc NULL khi không có transaction.
- `query_start`: thời điểm query hiện tại bắt đầu khi backend active; khi không active có thể phản ánh query gần nhất theo trạng thái.
- `state_change`: thời điểm backend đổi trạng thái lần cuối.
- `state`: trạng thái như `active`, `idle` hoặc `idle in transaction`.

Quan sát chính session hiện tại:

```sql
SELECT
    pid,
    state,
    backend_start,
    xact_start,
    query_start,
    state_change,
    clock_timestamp() AS observed_at
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
```

Chú ý `pg_stat_activity` là một view giám sát hệ thống có quy tắc cấp quyền; xem đầy đủ thông tin của session khác có thể cần quyền phù hợp. Không cấp quyền giám sát rộng cho mọi tài khoản ứng dụng chỉ để chạy bài tập.

### 13.1. Tuổi transaction đang mở

```sql
SELECT
    pid,
    state,
    clock_timestamp() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY transaction_age DESC;
```

Truy vấn này giúp nhận diện transaction chạy lâu hoặc session `idle in transaction`, vốn có thể giữ snapshot và khóa, làm ảnh hưởng VACUUM hoặc các writer.

Một transaction lâu không tự đồng nghĩa sai: có thể là batch hợp lệ. Nhưng cần biết lý do, đặt giới hạn vận hành phù hợp và theo dõi khi duration vượt SLA.

### 13.2. Thời gian một query đang active

```sql
SELECT
    pid,
    state,
    clock_timestamp() - query_start AS query_age
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start IS NOT NULL
ORDER BY query_age DESC;
```

Với session active, `query_start` phù hợp để tính tuổi query tại thời điểm lấy mẫu. Đừng đọc `query_start` của session `idle` thành “query vẫn đang chạy từ lúc đó”.

### 13.3. Đồng hồ thật và MVCC không phải một

`transaction_timestamp()` cố định ở transaction start, còn snapshot MVCC quyết định **dữ liệu nào một query nhìn thấy** theo isolation level. Chúng liên quan tới transaction nhưng là hai khái niệm khác nhau:

- Ở `READ COMMITTED`, các statement có thể nhìn snapshot dữ liệu mới hơn trong cùng transaction.
- `transaction_timestamp()` vẫn giữ nguyên.
- Ở `REPEATABLE READ`, nhiều statement có thể dùng cùng snapshot giao dịch theo quy tắc isolation, nhưng điều đó không có nghĩa `clock_timestamp()` dừng chạy.

Không kết luận snapshot dữ liệu của query là “mốc now()” rồi dùng timestamp để xác định những bản ghi đã commit nhìn thấy được. MVCC quản lý tính hiển thị bằng cơ chế transaction/snapshot riêng.

## 14. Ứng dụng 1: created_at, updated_at và audit

Thường gặp các trường:

```text
created_at
updated_at
processed_at
statement_received_at
transaction_started_at
sent_at
committed_at
```

Tên cột khác nhau phản ánh những ngữ nghĩa có thể khác nhau. Trước khi chọn hàm, phải hỏi: **muốn thời điểm của sự kiện nào?**

### 14.1. created_at DEFAULT now()

Ví dụ phổ biến:

```sql
CREATE TABLE clock_lab.notes (
    note_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

Với một transaction ngắn, `now()` thường rất phù hợp làm timestamp nhất quán cho những hàng phát sinh trong cùng transaction. Nhưng nếu transaction bắt đầu từ lâu trước khi chèn hàng, `created_at` có thể sớm hơn đáng kể so với lúc database thực thi `INSERT`.

### 14.2. updated_at không tự thay đổi khi UPDATE

PostgreSQL không tự động gán lại một cột tùy ý tên `updated_at` mỗi khi có lệnh `UPDATE` chỉ vì nó có default lúc INSERT. Muốn cập nhật tự động phải:

- Viết `SET updated_at = ...` trong mỗi luồng cập nhật phù hợp; hoặc
- Dùng trigger; hoặc
- Sử dụng cơ chế application/ORM đã được xác định rõ.

Ví dụ DML:

```sql
UPDATE clock_lab.notes
SET
    body = 'Nội dung mới',
    updated_at = statement_timestamp()
WHERE note_id = 1;
```

Ví dụ dùng `statement_timestamp()` khi muốn cùng một mốc cho mọi hàng của một `UPDATE`. `WHERE` phải được xác định đúng để không sửa ngoài phạm vi nghiệp vụ.

### 14.3. Trigger updated_at với đồng hồ thực

```sql
CREATE OR REPLACE FUNCTION clock_lab.set_note_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_note_updated_at
BEFORE UPDATE ON clock_lab.notes
FOR EACH ROW
EXECUTE FUNCTION clock_lab.set_note_updated_at();
```

Ví dụ này chọn `clock_timestamp()` cho thời điểm thực tại lúc trigger xử lý từng hàng. Với lệnh `UPDATE` nhiều hàng, timestamps giữa các hàng **có thể khác nhau**, và PostgreSQL không bảo đảm chúng là định danh duy nhất.

Nếu chính sách yêu cầu **mọi hàng sửa bởi một statement mang cùng timestamp**, dùng `statement_timestamp()` trong trigger. Nếu muốn cùng mốc cho toàn transaction, dùng `transaction_timestamp()` hoặc `now()`.

### 14.4. Trigger không có nghĩa update đã commit

Trigger chạy trong transaction có thể bị rollback. Giá trị `updated_at` được tạo từ `clock_timestamp()` nhưng **không phải bằng chứng transaction đã commit**.

Trường hợp hệ thống cần audit mạnh, thường còn cần định danh giao dịch/sự kiện, actor, lý do thay đổi, trạng thái commit/rollback ở tầng ghi log phù hợp và cơ chế retention. Timestamp một mình không bảo đảm chuỗi sự kiện đã bền vững.

## 15. Ứng dụng 2: tính hết hạn và TTL

Ví dụ cột `expires_at timestamptz` chứa thời điểm hết hạn tuyệt đối:

```sql
CREATE TABLE clock_lab.tokens (
    token_id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL
);
```

Chèn token có tuổi thọ 15 phút tính từ **một timestamp thực được lấy một lần**:

```sql
WITH sampled AS MATERIALIZED (
    SELECT clock_timestamp() AS issued_at
)
INSERT INTO clock_lab.tokens (token_id, created_at, expires_at)
SELECT
    1001,
    issued_at,
    issued_at + INTERVAL '15 minutes'
FROM sampled;
```

Ưu điểm: `created_at` và `expires_at` sử dụng cùng một giá trị `issued_at` nên tránh lệch nhỏ do hai lần đọc đồng hồ riêng.

### 15.1. Kiểm tra token còn hiệu lực

Nếu cần đánh giá tại mốc bắt đầu statement:

```sql
SELECT token_id
FROM clock_lab.tokens
WHERE expires_at > statement_timestamp();
```

Nếu muốn kiểm tra thời điểm thực khi biểu thức được đánh giá:

```sql
SELECT token_id
FROM clock_lab.tokens
WHERE expires_at > clock_timestamp();
```

Trên bảng lớn, hai cách có **ngữ nghĩa và khả năng tối ưu khác nhau**. `statement_timestamp()` cho một ngưỡng ổn định trong statement, thường dễ phù hợp với điều kiện index; `clock_timestamp()` là hàm volatile nên ngưỡng có thể đổi khi quét và có thể hạn chế một số tối ưu.

### 15.2. Transaction lâu khiến TTL có thể được đánh giá theo mốc cũ

```sql
BEGIN;

SELECT pg_sleep(5);

SELECT token_id
FROM clock_lab.tokens
WHERE expires_at > now();

ROLLBACK;
```

Ở query cuối, `now()` là **mốc lúc transaction bắt đầu**, không phải mốc sau 5 giây. Một token đã hết hạn trong 5 giây chờ có thể vẫn vượt qua điều kiện `expires_at > now()`.

Điều này không có nghĩa PostgreSQL bị lỗi. Chỉ có nghĩa **ngữ nghĩa transaction timestamp không phù hợp** nếu yêu cầu kiểm tra hết hạn ở thời điểm statement bắt đầu hoặc thời điểm thực.

### 15.3. Chọn hàm theo chính sách sản phẩm

| Yêu cầu | Mốc thường phù hợp |
| --- | --- |
| Mọi phép kiểm tra trong một transaction dùng cùng thời điểm quy chiếu | `transaction_timestamp()` |
| Một statement xét toàn bộ token theo một thời điểm thống nhất | `statement_timestamp()` |
| Cần đọc thời gian thực trong một phép kiểm tra được thực thi ở thời điểm hiện tại | `clock_timestamp()` |

Với bảo mật token, chính sách hết hạn còn liên quan clock skew giữa các hệ thống, latency và thứ tự xác thực. Không chỉ chọn hàm rồi coi như đã xử lý mọi vấn đề.

## 16. Ứng dụng 3: dashboard và “hôm nay”

“Hôm nay” phụ thuộc **múi giờ và mốc quan sát**.

Ví dụ người dùng xem báo cáo theo ngày Việt Nam, trong khi `ordered_at` lưu `timestamptz`:

```sql
SELECT
    (transaction_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS transaction_local_date,
    (statement_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS statement_local_date,
    (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS wall_local_date;
```

Nếu transaction kéo dài qua nửa đêm, `transaction_local_date` có thể là ngày trước, trong khi `wall_local_date` là ngày mới.

### 16.1. Ví dụ lọc theo ngày nghiệp vụ

Giả sử một bảng thực tế có cột `occurred_at timestamptz`. Với một khoảng ngày cụ thể:

```sql
-- Ví dụ trên bảng clock_lab.events, lọc ngày 2026-11-14 ở Việt Nam.
SELECT
    event_id,
    note,
    recorded_wall_at
FROM clock_lab.events
WHERE recorded_wall_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND recorded_wall_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY recorded_wall_at, event_id;
```

Biểu thức dùng **khoảng nửa mở** `[đầu ngày, đầu ngày kế tiếp)`. Nó tránh nhiều lỗi ở cuối ngày so với cố gắng tạo mốc `23:59:59.999999`, và cho phép sử dụng B-tree index trên cột `recorded_wall_at` theo điều kiện phạm vi phù hợp.

Nếu báo cáo cần ngày động, có thể tính ngày địa phương từ `statement_timestamp()` trong một CTE rồi dựng hai mốc biên:

```sql
WITH report_day AS (
    SELECT
        (statement_timestamp()
            AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_date
)
SELECT
    e.event_id,
    e.recorded_wall_at
FROM clock_lab.events AS e
CROSS JOIN report_day AS d
WHERE e.recorded_wall_at >=
        (d.local_date::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh')
  AND e.recorded_wall_at <
        ((d.local_date + 1)::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh')
ORDER BY e.recorded_wall_at, e.event_id;
```

Ở những vùng có DST, hai mốc đầu ngày liên tiếp theo múi giờ có thể cách nhau 23, 24 hoặc 25 giờ thực tế. Do đó xây biên theo **ngày lịch địa phương và timezone** thường chính xác hơn việc luôn cộng 24 giờ vào instant đầu ngày.

## 17. Hàm STABLE và VOLATILE: vì sao optimizer quan tâm?

PostgreSQL phân loại hàm theo mức thay đổi giá trị/ảnh hưởng lập kế hoạch, thường gặp:

- `IMMUTABLE`: với cùng đầu vào, hàm hứa kết quả không thay đổi, không phụ thuộc trạng thái bên ngoài theo cách ảnh hưởng lời hứa ấy.
- `STABLE`: trong một statement, hàm được coi là ổn định cho các mục đích tối ưu tương ứng, nhưng có thể khác ở statement khác.
- `VOLATILE`: kết quả hoặc side effect có thể thay đổi trong cùng statement.

Trong các hàm thời điểm đang học:

- `now()` và `transaction_timestamp()` là những hàm cho mốc transaction ổn định.
- `statement_timestamp()` ổn định theo statement.
- `clock_timestamp()` là hàm **VOLATILE** vì giá trị có thể thay đổi giữa các lời gọi trong cùng statement.
- `timeofday()` mang ngữ nghĩa đồng hồ thực dạng text và không nên dùng như một biểu thức bất biến.

### 17.1. Khác nhau trong WHERE

So sánh:

```sql
-- Ranh giới thời gian cố định cho statement theo ngữ nghĩa hàm.
SELECT event_id
FROM clock_lab.events
WHERE recorded_wall_at >=
      statement_timestamp() - INTERVAL '1 hour';
```

Và:

```sql
-- Đồng hồ thực có thể đổi trong lúc quét các hàng.
SELECT event_id
FROM clock_lab.events
WHERE recorded_wall_at >=
      clock_timestamp() - INTERVAL '1 hour';
```

Truy vấn thứ hai có ngưỡng “một giờ trước” liên tục trôi theo thời gian được lấy mẫu, nên một hàng gần ranh giới có thể được đánh giá khác khi nó được xử lý muộn hơn.

Điều kiện chứa hàm volatile có thể khó được planner biến thành một **index scan bound cố định** theo cách tương tự hàm ổn định. Tuy nhiên, không kết luận PostgreSQL **luôn** quét toàn bảng; kế hoạch còn phụ thuộc cấu trúc truy vấn, chỉ mục, dữ liệu và cách viết biểu thức.

### 17.2. Chỉ mục cho cột thời gian

```sql
CREATE INDEX idx_clock_events_recorded_wall
ON clock_lab.events (recorded_wall_at);
```

Một truy vấn theo khoảng thời gian có thể tận dụng chỉ mục này khi bộ lọc đủ chọn lọc:

```sql
EXPLAIN
SELECT event_id, note
FROM clock_lab.events
WHERE recorded_wall_at >= statement_timestamp() - INTERVAL '1 day'
ORDER BY recorded_wall_at DESC
LIMIT 100;
```

Trong lab với rất ít hàng, PostgreSQL có thể vẫn chọn seq scan. Đây là quyết định chi phí hợp lý, không phải bằng chứng chỉ mục bị lỗi.

### 17.3. Không dùng clock_timestamp trong expression index

Một index expression phải đáp ứng các yêu cầu về tính bất biến theo PostgreSQL. Không thể tạo index có ý nghĩa ổn định dựa trên “đồng hồ thực đang chạy”:

```sql
-- Không hợp lệ về yêu cầu immutability của index expression:
-- CREATE INDEX idx_bad_clock
-- ON clock_lab.events ((clock_timestamp()));
```

Nếu muốn tìm bản ghi mới trong một giờ gần đây, hãy tạo index trên **cột thời gian đã lưu** rồi sử dụng biểu thức cutoff tại lúc query chạy, thay vì mong index tự thay đổi theo thời gian mỗi giây.

### 17.4. Generated column cũng không phải nơi đặt đồng hồ động

Một generated column phải tuân theo các hạn chế về biểu thức, trong đó các biểu thức lưu trữ theo cơ chế phổ biến không được dùng các hàm volatile như `clock_timestamp()` để tạo giá trị tự động.

Muốn lưu thời điểm tạo/cập nhật, dùng `DEFAULT` hoặc logic DML/trigger phù hợp, không coi generated column là một đồng hồ độc lập.

## 18. Thời điểm thực không đồng nghĩa bộ đếm monotonic

`clock_timestamp()` đọc đồng hồ thực (*wall clock*) mà hệ điều hành cung cấp. Đồng hồ thực có thể được điều chỉnh bởi dịch vụ đồng bộ giờ, thay đổi cấu hình hoặc các tình huống vận hành hiếm gặp.

Vì vậy:

- Không coi hai giá trị `clock_timestamp()` là bảo đảm tăng chặt theo thứ tự mọi lần gọi.
- Không dùng timestamp đơn độc để tạo ID duy nhất hay quyết định thứ tự toàn cục trong một hệ thống phân tán.
- Không xem chênh lệch wall-clock là thước đo độ dài tuyệt đối không chịu ảnh hưởng của việc chỉnh đồng hồ.

### 18.1. Đo duration phía Java

Khi ứng dụng Java cần đo latency của một method hoặc request, bộ đếm monotonic như `System.nanoTime()` thường phù hợp hơn việc lấy `LocalDateTime.now()` hai lần rồi trừ.

Ví dụ:

```java
long started = System.nanoTime();
try {
    callDatabase();
} finally {
    long elapsed = System.nanoTime() - started;
    double milliseconds = elapsed / 1_000_000.0;
    recordMetric(milliseconds);
}
```

`System.nanoTime()` phục vụ đo **khoảng thời gian trong một JVM/process context**, không phải đồng hồ tuyệt đối dùng để lưu ngày giờ vào database. `callDatabase()` và `recordMetric(...)` trong ví dụ đại diện những phương thức của ứng dụng, cần được định nghĩa riêng.

### 18.2. Thứ tự event trong hệ thống phân tán

Nếu hai service trên hai máy cùng ghi event, timestamp có thể bị ảnh hưởng bởi:

- Độ lệch đồng hồ giữa máy.
- Network latency.
- Thời điểm event được tạo, gửi, nhận và commit khác nhau.
- Độ phân giải timestamp và việc nhiều event cùng mang một giá trị.

Khi cần thứ tự nhân quả hoặc thứ tự sự kiện theo stream, hãy dùng thêm sequence, offset, version, ID có quy tắc, hoặc cơ chế transaction/message log thích hợp. Timestamp là một thuộc tính quan sát, không luôn là bằng chứng đủ cho thứ tự tuyệt đối.

## 19. Tính đúng đắn của thời gian trong transaction dài

Giả sử một công việc xử lý dữ liệu mở transaction lúc 09:00 và kết thúc 09:30.

Trong suốt transaction:

```sql
SELECT now();
```

vẫn trả transaction start khoảng 09:00. Điều này ảnh hưởng:

- Dấu thời gian `created_at DEFAULT now()` của hàng được chèn lúc 09:28.
- Điều kiện `expires_at > now()` của token được kiểm tra lúc 09:29.
- Điều kiện lọc “dữ liệu mới trong 5 phút” dùng `now() - interval '5 minutes'`.
- Các báo cáo dựa trên `CURRENT_DATE` nếu transaction đi qua nửa đêm.

### 19.1. Tại sao PostgreSQL chọn mốc giao dịch?

Một mốc transaction ổn định mang lại lợi ích:

1. Các câu SQL trong cùng transaction có **cùng thời gian tham chiếu** khi dùng `now()`.
2. Một batch ghi nhiều bảng có thể được đóng dấu thống nhất theo transaction.
3. Những phép so sánh thời gian lặp lại không bị trôi dần trong transaction do các lần đọc wall clock.

Đó là một lựa chọn có chủ đích, không phải lỗi PostgreSQL.

### 19.2. Khi nào cần đổi sang statement_timestamp?

Khi yêu cầu được xác định “tại lúc server bắt đầu xử lý câu lệnh này”, như:

- Một statement báo cáo xét một ngưỡng hết hạn chung.
- Một `UPDATE` nhiều hàng muốn đóng cùng mốc bắt đầu.
- Ghi thời điểm nhận câu lệnh nhằm phân tích nghiệp vụ.

`statement_timestamp()` vừa có mốc mới ở mỗi statement vừa có tính thống nhất bên trong statement.

### 19.3. Khi nào cần clock_timestamp?

Khi cần thời gian thực được đọc sau một bước xử lý cụ thể, ví dụ:

- Ghi nhận thời điểm một trigger thực sự được gọi.
- Quan sát wall clock trước và sau `pg_sleep` trong một block PL/pgSQL.
- Lấy thời điểm tức thời trong một logic kiểm tra có chủ đích.
- Đo khoảng thời gian trôi đi bên trong một statement/transaction theo wall clock.

Không dùng `clock_timestamp()` chỉ vì tên “thật” nghe hay hơn `now()`; volatility có thể gây thêm chi phí và thay đổi ngữ nghĩa truy vấn.

## 20. Ba mốc thời gian và snapshot MVCC

Ba khái niệm dễ bị đánh đồng:

| Khái niệm | Trả lời câu hỏi nào? |
| --- | --- |
| Transaction timestamp | Transaction bắt đầu khi nào? |
| Statement timestamp | Statement hiện tại bắt đầu khi nào? |
| MVCC snapshot | Statement/transaction đang **được thấy những phiên bản hàng nào**? |

Ở isolation `READ COMMITTED` (mặc định), mỗi statement thường lấy snapshot phù hợp tại lúc statement bắt đầu. Ở `REPEATABLE READ`, các statement đọc trong transaction có thể dùng cùng snapshot giao dịch theo quy tắc PostgreSQL.

Nhưng:

- `now()` không phải là ID snapshot.
- `statement_timestamp()` không chứng minh một hàng cụ thể đã visible.
- `clock_timestamp()` không thay đổi quyền nhìn thấy dữ liệu chưa commit của transaction khác.
- Dấu thời gian tạo hàng không phải “thứ tự commit” có thể suy ra từ MVCC.

Ví dụ hai transaction đồng thời có thể commit theo thứ tự ngược với thứ tự bắt đầu. Nếu lưu `created_at DEFAULT now()`, hàng của transaction bắt đầu sớm **có thể commit muộn hơn** hàng của transaction bắt đầu sau.

Do đó, không dùng `ORDER BY created_at` như một chứng cứ tuyệt đối về thứ tự commit khi nghiệp vụ đòi hỏi thứ tự giao dịch chính xác.

## 21. PostgreSQL có đo được commit timestamp không?

`transaction_timestamp()` **không phải** hàm commit timestamp. `clock_timestamp()` gọi trước `COMMIT` cũng không phải thời điểm commit thực.

PostgreSQL có một số cơ chế nội bộ/tuỳ chọn liên quan theo dõi commit, như cấu hình `track_commit_timestamp` và hàm hệ thống chuyên biệt khi được bật/hỗ trợ, nhưng đó là **một tính năng riêng có điều kiện, giới hạn retention/khả dụng và yêu cầu quản trị**. Không nên giả định mọi database có thể truy lại commit time chính xác của mọi transaction trong quá khứ.

Nếu hệ thống thực sự cần xác nhận mốc hoàn tất một workflow, hãy thiết kế sự kiện được phát sau khi commit thành công, trạng thái xác nhận ở tầng dịch vụ và cơ chế outbox/log đáng tin. Một cột `committed_at DEFAULT now()` không thể thay thế điều đó.

## 22. Lưu thời gian cùng timezone trong ứng dụng Java

Trong Java, bạn có thể gặp:

- `Instant`: một instant tuyệt đối trên trục thời gian.
- `OffsetDateTime`: ngày giờ kèm UTC offset.
- `ZonedDateTime`: ngày giờ trong timezone có quy tắc như `Asia/Ho_Chi_Minh`.
- `LocalDateTime`: ngày giờ địa phương **không có thông tin timezone**.
- `LocalDate`: ngày lịch.

Khi lưu một sự kiện tại một thời điểm thực, `timestamptz` của PostgreSQL thường phù hợp với mô hình instant. PostgreSQL JDBC driver có những mapping kiểu phù hợp, ví dụ `OffsetDateTime` với `timestamptz` trong các phiên bản driver hỗ trợ; nhiều ứng dụng cũng chuyển về `Instant` ở tầng domain.

### 22.1. Tránh mất timezone khi mapping

Nếu service lấy một `timestamptz` rồi ép thành `LocalDateTime` mà không chỉ định zone, giá trị có thể bị hiểu nhầm khi đưa sang máy ở múi giờ khác.

Ví dụ Java:

```java
Instant instant = Instant.parse("2026-07-01T12:00:00Z");
ZoneId vietnamZone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime vietnamTime = instant.atZone(vietnamZone);
// 2026-07-01T19:00+07:00[Asia/Ho_Chi_Minh]
```

Giá trị `Instant` vẫn là 12:00Z; `ZonedDateTime` chuyển cách biểu diễn sang giờ Việt Nam. Nguyên tắc này tương ứng với việc PostgreSQL hiển thị cùng `timestamptz` trong những timezone khác nhau.

### 22.2. Database clock hay application clock?

| Lựa chọn | Lợi ích | Đánh đổi |
| --- | --- | --- |
| Database dùng `now()`/`statement_timestamp()` | Có mốc thời gian của PostgreSQL theo transaction/statement. | Cần hiểu transaction length và timezone. |
| Database dùng `clock_timestamp()` | Mốc wall-clock tại lúc PostgreSQL đọc. | Volatile, không nhất thiết đồng nhất cả batch. |
| Java service truyền `Instant.now()` | Có thể thống nhất với event/domain logic trong service. | Phụ thuộc đồng hồ máy ứng dụng, có thể lệch so với database/service khác. |

Nếu nhiều service ở các máy khác nhau cùng ghi, cần quyết định **nguồn đồng hồ ưu tiên** và chính sách đồng bộ giờ. Không kết hợp ngẫu nhiên giá trị từ database và application rồi giả định chúng luôn có một thứ tự chính xác.

### 22.3. PreparedStatement không đổi ngữ nghĩa thời gian

Một câu SQL có `DEFAULT now()`, `statement_timestamp()` hay `clock_timestamp()` vẫn được PostgreSQL đánh giá khi statement được thực hiện theo ngữ nghĩa từng hàm. Việc Java dùng prepared statement không biến `now()` thành giá trị cố định tại thời điểm chuẩn bị câu truy vấn.

Tuy nhiên, tránh gửi các biểu thức ngày giờ bằng cách nối trực tiếp chuỗi không được xác thực. Với giá trị do client cung cấp, hãy bind các tham số timestamp phù hợp và quản lý timezone nhất quán.

## 23. Lựa chọn thời gian cho dữ liệu batch và ETL

Trong ETL có thể có nhiều mốc:

```text
source_event_time     -- lúc sự kiện xảy ra ở nguồn
source_created_at      -- lúc hệ thống nguồn lưu sự kiện
ingested_at            -- lúc pipeline nhận sự kiện
processed_at           -- lúc worker xử lý
loaded_at              -- lúc hàng được ghi vào PostgreSQL
batch_started_at       -- lúc batch bắt đầu
batch_completed_at     -- lúc batch thực sự hoàn tất
```

Những cột này **không thể thay thế bằng một `now()` chung** mà không đánh mất ý nghĩa.

### 23.1. Một transaction cho toàn batch

Nếu ETL dùng `BEGIN` rồi nhập nhiều triệu hàng trong 20 phút và đặt `loaded_at DEFAULT now()`, toàn bộ hàng có thể mang cùng mốc **batch transaction start**.

Đây có thể là điều mong muốn nếu `loaded_at` được định nghĩa là “bắt đầu batch”. Nhưng nếu mục tiêu là phân tích độ trễ tới thời điểm mỗi chunk được nạp, có thể cần `statement_timestamp()` hoặc thời điểm xử lý theo chunk.

### 23.2. Nhiều statement trong một transaction

`statement_timestamp()` phù hợp nếu mỗi `INSERT`/`COPY`/`UPDATE` được coi là một đơn vị xử lý riêng. Các statement có mốc khác nhau dù transaction chung.

Nếu cần một mốc cố định cho cả batch dù có nhiều transaction, đừng trông đợi `transaction_timestamp()` tự giống nhau; hãy tạo `batch_id` và `batch_started_at` một lần rồi truyền vào các thao tác theo logic pipeline.

### 23.3. Không lấy timestamp làm idempotency key

Hai event hợp lệ có thể cùng timestamp. Một event gửi lại có thể được xử lý lần thứ hai với timestamp khác. Vì vậy dùng timestamp đơn độc làm khóa “đã xử lý hay chưa” rất dễ đếm đôi hoặc bỏ sót.

Hãy dùng event ID, sequence hoặc khóa nghiệp vụ thích hợp, kèm transaction và constraint rõ ràng.

## 24. Thời gian trong DEFAULT, trigger và SELECT: so sánh use case

| Nhu cầu | Gợi ý | Giải thích |
| --- | --- | --- |
| Một transaction tạo nhiều hàng cần chung mốc | `DEFAULT now()` | Tất cả nhận transaction start. |
| Mỗi statement có mốc thống nhất | `DEFAULT statement_timestamp()` | Cùng statement dùng cùng timestamp. |
| Cần ghi giờ thực khi từng hàng được xử lý | `DEFAULT clock_timestamp()` | Giá trị có thể khác theo thời điểm đánh giá. |
| Audit mốc bắt đầu câu lệnh cập nhật | `updated_at = statement_timestamp()` | Phản ánh lúc statement bắt đầu. |
| Đo thời gian trôi giữa hai bước PL/pgSQL | `clock_timestamp()` hai lần, gọi nối tiếp | Thời gian thực khi từng bước được thực hiện. |
| Kiểm tra TTL tại mốc statement | `expires_at > statement_timestamp()` | Một ngưỡng ổn định cho toàn câu SQL. |
| Kiểm tra TTL theo transaction | `expires_at > now()` | Ngưỡng không đổi trong transaction, lưu ý transaction dài. |
| Báo cáo theo “ngày ở Việt Nam” | Timestamp có timezone + chuyển sang `Asia/Ho_Chi_Minh` | Tránh lệ thuộc timezone ngầm của session. |
| Log nguyên văn giờ hiện tại để debug cũ | `timeofday()` có thể hiện diện | Trả text, thường nên dùng `clock_timestamp()` khi viết code mới. |
| Cần chứng minh commit thành công | Transaction outcome + logging/event phù hợp | Không có một default timestamp tự bảo đảm ý nghĩa commit. |

Mỗi lựa chọn là một **quyết định ngữ nghĩa**. Đừng đổi toàn hệ thống từ `now()` sang `clock_timestamp()` theo tiêu chí “càng sát giờ thực càng tốt” mà chưa xác định yêu cầu.

## 25. Các lỗi hiểu nhầm thường gặp

### Lỗi 1. Nghĩ now() là giờ thực mới ở mọi lời gọi

Trong cùng transaction, `now()` luôn phản ánh transaction start. Thử bằng `BEGIN; ... pg_sleep(...) ... COMMIT;`, không chỉ hai SELECT autocommit.

### Lỗi 2. Nghĩ statement_timestamp() không thay đổi giữa các statement

Nó ổn định **trong một statement**, nhưng câu lệnh tiếp theo có mốc riêng, kể cả trong cùng transaction.

### Lỗi 3. Nghĩ clock_timestamp() luôn tăng

Đồng hồ hệ thống có thể bị điều chỉnh, độ phân giải hữu hạn. Không dùng wall timestamp thay cho sequence hoặc monotonic timer.

### Lỗi 4. Nhầm now() với thời điểm commit

`now()` là transaction start; kết quả có thể được tạo trong transaction mà sau đó rollback. Không dùng nó làm bằng chứng commit.

### Lỗi 5. Dùng CURRENT_DATE cho thời gian thực trong transaction dài

`CURRENT_DATE` dựa trên mốc transaction và timezone session. Qua nửa đêm, “ngày hiện tại ngoài đời” có thể đã khác.

### Lỗi 6. Bỏ timezone khi lưu sự kiện xuyên vùng

`timestamp without time zone` không xác định một instant tuyệt đối. Với event thực, cân nhắc `timestamptz` và chuyển timezone khi hiển thị.

### Lỗi 7. Coi timestamptz lưu tên timezone ban đầu

Nó lưu một instant, không lưu `Asia/Ho_Chi_Minh` như metadata của từng hàng. Nếu nghiệp vụ cần biết timezone người dùng đã chọn, lưu riêng zone ID.

### Lỗi 8. Dùng literal 'now' làm DEFAULT động

Literal được cast thành timestamp tại lúc parse/định nghĩa có thể bị cố định. Dùng `DEFAULT now()`, `DEFAULT CURRENT_TIMESTAMP` hoặc hàm mốc khác phù hợp.

### Lỗi 9. Nghĩ DEFAULT updated_at tự áp dụng ở UPDATE

Default thường áp dụng khi chèn giá trị mới hoặc dùng `DEFAULT` theo lệnh phù hợp; không tự đặt lại `updated_at` ở mọi UPDATE. Cần DML/trigger riêng.

### Lỗi 10. Dùng clock_timestamp() trong WHERE mà không nghĩ tới optimizer

Giá trị volatile có thể đổi trong quá trình scan; index bound và query semantics khác hàm stable. Nếu chỉ cần cutoff thống nhất, cân nhắc `statement_timestamp()`.

### Lỗi 11. Dùng timeofday() để tính toán giờ

`timeofday()` trả `text`. Trừ và so sánh timestamp bằng kiểu dữ liệu thời gian thật, không dựa vào định dạng chuỗi.

### Lỗi 12. Đặt toàn bộ logic thử thời gian trong một SELECT rồi suy ra thứ tự đánh giá

Không nên dùng vị trí các biểu thức trong select list làm cam kết thứ tự side effect. Dùng `DO` hoặc các statement tuần tự nếu cần đo giữa hai bước.

### Lỗi 13. Nhầm timestamp với MVCC snapshot

Đồng hồ và tính hiển thị dữ liệu theo transaction là hai cơ chế khác nhau. Transaction timestamp không phải commit sequence.

### Lỗi 14. Tạo ID từ timestamp

Hai bản ghi có thể cùng giá trị microsecond hoặc đồng hồ bị chỉnh. Dùng primary key, identity/sequence, UUID hoặc phương án định danh đã được thiết kế riêng.

### Lỗi 15. So sánh giờ ở hai máy không có chính sách đồng bộ

Ứng dụng và database có thể khác đồng hồ. Khi cần đối soát sự kiện, ghi nguồn timestamp và dùng chính sách clock/timezone rõ ràng.

### Lỗi 16. Đo request latency chỉ bằng hai wall timestamps

Wall clock có thể bị điều chỉnh. Ở Java, thường dùng `System.nanoTime()` cho duration trong một process; ở PostgreSQL, dùng công cụ theo dõi query thích hợp và hiểu giới hạn các timestamp đã chọn.

### Lỗi 17. Tin rằng giá trị clock_timestamp khác nhau luôn là sự kiện khác nhau

Độ phân giải và thời điểm lấy mẫu không bảo đảm uniqueness. Tách identity của sự kiện và timestamp của sự kiện.

### Lỗi 18. Ghi nhãn created_at trong thực tế nhưng dùng mốc giao dịch không phù hợp

Nếu cột thực sự muốn “thời điểm INSERT được thực thi”, `now()` trong transaction dài có thể không đúng nhu cầu. Hãy đổi tên chính sách hoặc đổi hàm một cách có chủ đích.

## 26. Bộ thí nghiệm tổng hợp trong một session

Đây là bài thực hành có thể chạy trong `psql` hoặc GUI giữ nguyên một connection. Những mốc thực tế phụ thuộc đồng hồ của PostgreSQL server.

### 26.1. Thử không mở transaction

```sql
SELECT
    now() AS tx,
    statement_timestamp() AS stmt,
    clock_timestamp() AS wall;

SELECT pg_sleep(1);

SELECT
    now() AS tx,
    statement_timestamp() AS stmt,
    clock_timestamp() AS wall;
```

Quan sát: trong chế độ autocommit, cả transaction lẫn statement đều thay đổi giữa các câu SQL.

### 26.2. Thử trong transaction explicit

```sql
BEGIN;

SELECT
    now() AS tx,
    statement_timestamp() AS stmt,
    clock_timestamp() AS wall;

SELECT pg_sleep(1);

SELECT
    now() AS tx,
    statement_timestamp() AS stmt,
    clock_timestamp() AS wall;

ROLLBACK;
```

Quan sát: transaction time giữ nguyên; statement và wall time thay đổi.

### 26.3. Thử trong một statement

```sql
DO $$
DECLARE
    tx_1 timestamptz;
    tx_2 timestamptz;
    stmt_1 timestamptz;
    stmt_2 timestamptz;
    wall_1 timestamptz;
    wall_2 timestamptz;
BEGIN
    tx_1 := transaction_timestamp();
    stmt_1 := statement_timestamp();
    wall_1 := clock_timestamp();

    PERFORM pg_sleep(1);

    tx_2 := transaction_timestamp();
    stmt_2 := statement_timestamp();
    wall_2 := clock_timestamp();

    RAISE NOTICE
        'transaction_same=%, statement_same=%, wall_diff_seconds=%',
        tx_1 = tx_2,
        stmt_1 = stmt_2,
        EXTRACT(EPOCH FROM wall_2 - wall_1);
END;
$$;
```

Trong điều kiện thường, kết quả notice cho:

```text
transaction_same = true
statement_same   = true
wall_diff_seconds khoảng >= 1
```

Con số thực tế có thể khác một chút do scheduler; đồng hồ wall-clock có thể bị điều chỉnh nên không hứa một khoảng chính xác tuyệt đối.

## 27. Bài tập thực hành

Các bài tập dùng những câu lệnh PostgreSQL đã học. Một số ví dụ thao tác trên `clock_lab` và `clock_lab_example`; hãy chạy trong môi trường thử nghiệm, không xóa dữ liệu production.

### Bài 1. Phân loại ba hàm

Điền mốc của các hàm `now()`, `statement_timestamp()`, `clock_timestamp()` và giải thích hàm nào có thể đổi trong một statement.

### Bài 2. Chọn thời gian cho INSERT

Ứng dụng muốn một batch `INSERT` 10.000 hàng có chung thời điểm bắt đầu statement, dù mất 5 giây để hoàn thành. Chọn default nào?

### Bài 3. Transaction dài

Trong transaction, `BEGIN` lúc 10:00, statement thứ hai chạy lúc 10:05. Dự đoán `now()` và `statement_timestamp()` lúc statement thứ hai.

### Bài 4. Đồng hồ trong DO

Viết `DO` gồm hai lời gọi `clock_timestamp()` và `pg_sleep(2)` ở giữa. So sánh với hai lần đọc `statement_timestamp()`.

### Bài 5. CURRENT_DATE qua nửa đêm

Giả sử transaction bắt đầu trước 00:00 theo giờ Việt Nam và kết thúc sau 00:00. Trong cấu hình timezone không đổi, `CURRENT_DATE` có nhất thiết đổi sang ngày mới không? Tại sao?

### Bài 6. Đồng nhất transaction

Viết truy vấn kiểm tra `now() = transaction_timestamp()` và `now() = CURRENT_TIMESTAMP`. Kết quả dự đoán?

### Bài 7. Time zone

Chuyển `TIMESTAMPTZ '2026-07-01 12:00:00+00'` sang giờ địa phương `Asia/Ho_Chi_Minh` bằng `AT TIME ZONE`.

### Bài 8. Ngày ở Việt Nam

Viết biểu thức lấy `date` theo giờ Việt Nam của `statement_timestamp()`, không phụ thuộc timezone session.

### Bài 9. Đo duration

Tính thời gian tính bằng giây từ transaction start tới một lần đọc `clock_timestamp()`. Nêu giới hạn của cách đo wall-clock.

### Bài 10. timeofday

`timeofday()` trả kiểu gì, và tại sao không nên dùng để tính khoảng thời gian?

### Bài 11. created_at ở transaction dài

Một bảng có `created_at timestamptz DEFAULT now()`. Transaction mở 09:00, INSERT chạy 09:10. `created_at` thông thường phản ánh mốc nào?

### Bài 12. TTL

Ứng dụng muốn cả một statement xét mọi token theo **một ngưỡng hết hạn chung tại lúc statement bắt đầu**. Chọn `now()`, `statement_timestamp()` hay `clock_timestamp()`? Vì sao?

### Bài 13. Index và volatility

Tại sao điều kiện `occurred_at >= statement_timestamp() - interval '1 hour'` có thể dễ tối ưu theo B-tree index hơn điều kiện tương tự dùng `clock_timestamp()`?

### Bài 14. updated_at

Viết trigger PostgreSQL cập nhật `updated_at` theo `statement_timestamp()` cho mỗi `UPDATE` của bảng `clock_lab.notes`. Phân biệt với trigger dùng `clock_timestamp()`.

### Bài 15. SQL NULL và timezone

Giải thích khác nhau giữa kiểu `timestamptz` và `timestamp without time zone`. Nếu nghiệp vụ cần biết **tên múi giờ khách chọn**, chỉ lưu `timestamptz` có đủ không?

### Bài 16. Commit timestamp

Tại sao không nên đặt tên cột `committed_at` rồi gán mặc định `now()` để tuyên bố đó là thời điểm commit?

### Bài 17. Tạo timestamp đồng nhất cho token

Viết một `INSERT` tạo token với `created_at` là wall clock và `expires_at = created_at + interval '15 minutes'`, sử dụng **một mẫu wall-clock**.

### Bài 18. So sánh mốc để theo dõi query

Trong `pg_stat_activity`, trường nào giúp xem transaction start, query start và thời điểm đổi trạng thái? Trường nào có thể dùng để tính age của query đang `active`?

### Bài 19. Hai máy có đồng hồ lệch

Service A ghi `2026-11-14T10:00:00Z`, service B ghi `2026-11-14T09:59:59Z`. Có thể kết luận event A xảy ra sau B không? Cần thêm bằng chứng gì?

### Bài 20. Lựa chọn mốc cho ETL

Một job ETL có transaction kéo dài 20 phút và ghi theo 50 statement. Muốn:

1. Một mốc chung cho toàn transaction.
2. Mốc riêng cho từng statement.
3. Giờ thực khi từng hàng xử lý.

Chọn các hàm tương ứng và nêu chi phí/ý nghĩa khác nhau.

## 28. Gợi ý đáp án

### Đáp án 1

`now()` là transaction start, `statement_timestamp()` là statement start, `clock_timestamp()` là giờ thực lúc gọi. Chỉ hàm đồng hồ thực có thể đổi trong cùng statement theo ngữ nghĩa đang so sánh.

### Đáp án 2

`DEFAULT statement_timestamp()`. Mọi hàng thuộc cùng statement nhận chung mốc bắt đầu statement; batch nhiều statement thì có những mốc khác nhau.

### Đáp án 3

`now()` phản ánh khoảng 10:00; `statement_timestamp()` phản ánh khoảng 10:05. Giá trị thực có phần giây/offset phụ thuộc session và server.

### Đáp án 4

```sql
DO $$
DECLARE
    before_clock timestamptz;
    after_clock timestamptz;
    before_stmt timestamptz;
    after_stmt timestamptz;
BEGIN
    before_stmt := statement_timestamp();
    before_clock := clock_timestamp();
    PERFORM pg_sleep(2);
    after_clock := clock_timestamp();
    after_stmt := statement_timestamp();

    RAISE NOTICE 'stmt_same=%, wall_elapsed=%',
        before_stmt = after_stmt,
        after_clock - before_clock;
END;
$$;
```

Statement timestamp giống nhau; wall-clock thường cách nhau ít nhất xấp xỉ 2 giây theo điều kiện hệ thống.

### Đáp án 5

Không. `CURRENT_DATE` phản ánh ngày từ transaction timestamp theo timezone session. Khi giữ timezone không đổi, mốc transaction không đổi qua nửa đêm nên ngày vẫn gắn với transaction start.

### Đáp án 6

```sql
SELECT
    now() = transaction_timestamp() AS same_tx,
    now() = CURRENT_TIMESTAMP AS same_current;
```

Hai biểu thức cho `true` trong cùng transaction.

### Đáp án 7

```sql
SELECT
    TIMESTAMPTZ '2026-07-01 12:00:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_local_time;
```

Kết quả `2026-07-01 19:00:00`, kiểu `timestamp without time zone`.

### Đáp án 8

```sql
SELECT
    (statement_timestamp()
        AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS statement_day_vietnam;
```

### Đáp án 9

```sql
SELECT
    EXTRACT(
        EPOCH FROM
        (clock_timestamp() - transaction_timestamp())
    ) AS elapsed_seconds;
```

Chênh lệch wall-clock có thể bị ảnh hưởng nếu đồng hồ hệ thống bị điều chỉnh; nó không phải bộ đếm monotonic tuyệt đối.

### Đáp án 10

`timeofday()` trả `text`. Muốn tính thời gian, nên dùng giá trị kiểu `timestamptz` hoặc `interval`; dùng chuỗi dễ mắc lỗi kiểu, định dạng và múi giờ.

### Đáp án 11

Trong transaction đó, `DEFAULT now()` phản ánh mốc transaction start khoảng 09:00, không mặc định là 09:10.

### Đáp án 12

`statement_timestamp()`, vì câu lệnh cần một ngưỡng thống nhất tính tại lúc statement bắt đầu. `now()` có thể cũ nếu transaction đã mở lâu; `clock_timestamp()` có thể đổi khi query quét các hàng.

### Đáp án 13

`statement_timestamp()` ổn định trong statement nên planner có thể dùng như một cutoff nhất quán cho phép truy vấn index range phù hợp. `clock_timestamp()` volatile, có thể đổi giữa các lần đánh giá và hạn chế việc dùng làm scan boundary cố định. Dù vậy, quyết định index cuối cùng vẫn do optimizer theo query/data.

### Đáp án 14

```sql
CREATE OR REPLACE FUNCTION clock_lab.set_note_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := statement_timestamp();
    RETURN NEW;
END;
$$;

-- Nếu trước đó đã có trigger từ bài học, tránh tạo thêm
-- một trigger thứ hai cùng cập nhật updated_at.
-- CREATE TRIGGER trg_note_updated_at
-- BEFORE UPDATE ON clock_lab.notes
-- FOR EACH ROW
-- EXECUTE FUNCTION clock_lab.set_note_updated_at();
```

Khi có một trigger trên `clock_lab.notes` gọi hàm vừa thay, các hàng của cùng UPDATE nhận cùng statement start. Nếu dùng `clock_timestamp()`, chúng có thể khác khi xử lý từng hàng.

### Đáp án 15

`timestamptz` biểu diễn instant, hiển thị theo timezone session; `timestamp without time zone` không có thông tin zone để xác định instant. Nếu cần tên múi giờ người dùng chọn, phải lưu riêng một cột như `user_timezone text` với giá trị IANA hợp lệ; `timestamptz` không lưu tên zone gốc cho từng hàng.

### Đáp án 16

`now()` là transaction start, transaction có thể commit sau nhiều giây hoặc rollback. Vì vậy nó không phải bằng chứng của mốc commit thực.

### Đáp án 17

```sql
WITH sampled AS MATERIALIZED (
    SELECT clock_timestamp() AS issued_at
)
INSERT INTO clock_lab.tokens (token_id, created_at, expires_at)
SELECT
    1002,
    issued_at,
    issued_at + INTERVAL '15 minutes'
FROM sampled;
```

Chạy khi token 1002 chưa có để không vi phạm primary key.

### Đáp án 18

`xact_start` là transaction start, `query_start` là query start, `state_change` là lúc trạng thái đổi gần nhất. Với query đang `active`, dùng `clock_timestamp() - query_start` để xem query age.

### Đáp án 19

Không. Đồng hồ hai máy có thể lệch và event được phát/nhận qua mạng. Cần thêm ID, sequence/offset, transaction/commit order hoặc quan hệ nhân quả phù hợp với hệ thống.

### Đáp án 20

1. `transaction_timestamp()` hoặc `now()`: chung cho transaction.
2. `statement_timestamp()`: chung trong statement nhưng khác giữa các statement.
3. `clock_timestamp()`: lấy giờ thực mỗi lần được đánh giá, có thể khác giữa các hàng và có chi phí/volatility tương ứng.

## 29. Checklist khi đưa hàm thời gian vào hệ thống

Trước khi chọn một biểu thức thời gian cho schema hoặc SQL, hãy trả lời:

1. **Mốc nghiệp vụ là gì?** Transaction start, statement start, lúc xử lý một hàng, lúc event xảy ra, hay lúc commit?
2. **Có transaction dài không?** Nếu có, liệu `now()` quá cũ cho TTL hoặc “hôm nay”?
3. **Có cần cùng timestamp cho nhiều hàng không?** Nếu có, chọn một mốc ổn định hoặc truyền batch timestamp rõ ràng.
4. **Có cần thứ tự tuyệt đối không?** Timestamp không tự bảo đảm uniqueness/commit order.
5. **Kiểu cột là gì?** `timestamptz` cho instant; `timestamp without time zone` cho local date-time có ngữ nghĩa riêng.
6. **Timezone báo cáo là gì?** Không phụ thuộc ngầm vào timezone session khi kết quả cần theo vùng cụ thể.
7. **Có chuyển qua Java không?** Chọn `Instant`, `OffsetDateTime`, `ZonedDateTime` hoặc `LocalDateTime` đúng ngữ nghĩa.
8. **Có điều kiện lọc theo thời gian không?** Tính ổn định/volatility có thể ảnh hưởng index và kế hoạch.
9. **Có log/monitor không?** Phân biệt `xact_start`, `query_start`, `statement_timestamp()` và wall clock.
10. **Có audit commit không?** Không dùng `now()` như bằng chứng commit.
11. **Có clock skew hoặc đồng hồ được điều chỉnh không?** Phân biệt wall-clock và monotonic duration.
12. **Có unit/integration test cho transaction dài và qua ngày mới không?** Những ca này phơi bày sự khác nhau giữa ba mốc.

## 30. Tổng kết

Trong PostgreSQL, “thời gian hiện tại” không phải một khái niệm duy nhất:

- **`transaction_timestamp()`, `now()` và `CURRENT_TIMESTAMP`** phản ánh **thời điểm bắt đầu transaction**, ổn định xuyên nhiều statement trong transaction.
- **`statement_timestamp()`** phản ánh **thời điểm bắt đầu statement hiện hành**, ổn định trong statement nhưng có thể khác giữa các statement cùng transaction.
- **`clock_timestamp()`** đọc **đồng hồ thực khi gọi**, có thể đổi ngay trong một statement và là hàm volatile.
- **`timeofday()`** cũng lấy giờ thực nhưng trả `text`; thường không phải lựa chọn tốt cho các phép tính hoặc lưu timestamp có kiểu.
- **`CURRENT_DATE`, `CURRENT_TIME`, `LOCALTIME` và `LOCALTIMESTAMP`** theo mốc transaction và việc hiển thị/tính toán theo múi giờ của session.
- **`timestamptz`** biểu diễn instant, còn `timestamp without time zone` là ngày giờ không gắn timezone. Tên timezone gốc nếu cần phải được lưu riêng.
- **DEFAULT, trigger, TTL, batch và audit** cần chọn mốc theo đúng sự kiện nghiệp vụ. Thời điểm ghi trong transaction chưa chắc là thời điểm commit.
- **Đo duration và tối ưu truy vấn** phải hiểu volatility và giới hạn wall clock; dùng `EXPLAIN`, view hệ thống hoặc công cụ đo monotonic thích hợp.

Một câu hỏi đơn giản giúp chọn đúng hàm: **“Tôi muốn một thời điểm chung cho toàn giao dịch, một thời điểm chung cho câu lệnh, hay giờ thực khi phép tính đang chạy?”** Khi trả lời rõ câu hỏi đó, bạn sẽ tránh nhiều lỗi khó phát hiện trong dữ liệu lịch sử, thời hạn, log và các báo cáo PostgreSQL.
