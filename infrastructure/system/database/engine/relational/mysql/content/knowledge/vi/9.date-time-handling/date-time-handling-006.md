# NOW, CURRENT_TIMESTAMP, UTC_TIMESTAMP và thời điểm lấy giá trị

MySQL cung cấp các hàm thời gian hiện tại để ghi nhận thời điểm tạo bản ghi, cập nhật dữ liệu và kiểm tra thời gian trong truy vấn. `NOW()` và `CURRENT_TIMESTAMP` trả về ngày giờ theo múi giờ của session; `UTC_TIMESTAMP()` trả về ngày giờ UTC. Một điểm quan trọng là các hàm này lấy giá trị tại thời điểm bắt đầu thực thi câu lệnh, nên những lần gọi trong cùng một statement dùng chung một mốc thời gian.

Hiểu rõ thời điểm đánh giá hàm và múi giờ của kết nối giúp ứng dụng lưu timestamp nhất quán, đặc biệt khi nhiều service, transaction hoặc client ở các múi giờ khác nhau cùng ghi dữ liệu. Đây là kiến thức nền cho module `DATABASE_MYSQL`: thiết kế cột ngày giờ, truy vấn theo khoảng thời gian, index, transaction và vận hành dữ liệu có tính lịch sử.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt `NOW()`, `CURRENT_TIMESTAMP` và `UTC_TIMESTAMP()`.
- Giải thích thời điểm các hàm lấy giá trị và phạm vi nhất quán trong một statement.
- Hiểu ảnh hưởng của `time_zone` ở cấp session và global.
- Chọn cách lưu thời điểm với `TIMESTAMP` và `DATETIME`.
- Khai báo default/on-update timestamp với độ chính xác microsecond.
- Tránh lỗi lệch giờ khi ghi UTC vào cột `TIMESTAMP` và khi dùng connection pool.

## 1. Ba hàm thời gian hiện tại

| Hàm | Giá trị trả về | Phụ thuộc `time_zone` của session? | Cách dùng phổ biến |
|---|---|---|---|
| `NOW()` | Ngày giờ hiện tại theo múi giờ session | Có | Ghi nhận thời gian hiện tại theo ngữ cảnh kết nối |
| `CURRENT_TIMESTAMP` | Đồng nghĩa với `NOW()` | Có | Dùng trong truy vấn, `DEFAULT` và `ON UPDATE` |
| `UTC_TIMESTAMP()` | Ngày giờ hiện tại theo UTC | Không | Lấy mốc UTC tường minh để so sánh hoặc xử lý |

`CURRENT_TIMESTAMP` có thể viết không có ngoặc hoặc có ngoặc `CURRENT_TIMESTAMP()`. `NOW()` và `UTC_TIMESTAMP()` cũng có thể gọi không tham số hoặc truyền độ chính xác phần giây, ví dụ `NOW(6)`, `UTC_TIMESTAMP(6)`. `LOCALTIME` và `LOCALTIMESTAMP` là các tên tương đương với `NOW()` trong MySQL.

Chạy truy vấn sau để xem các giá trị trong phiên hiện tại:

```sql
SELECT
    NOW() AS session_now,
    CURRENT_TIMESTAMP AS current_timestamp_value,
    UTC_TIMESTAMP() AS utc_now,
    @@SESSION.time_zone AS session_time_zone,
    @@SYSTEM_TIME_ZONE AS system_time_zone;
```

`NOW()` và `CURRENT_TIMESTAMP` có cùng giá trị vì là hai cách gọi tương đương. Nếu session đang ở múi giờ `+07:00`, giá trị của hai hàm này thường lệch UTC bảy giờ; `UTC_TIMESTAMP()` vẫn biểu diễn giờ UTC.

### 1.1. Giá trị trả về không mang nhãn múi giờ

Các hàm trả về giá trị ngày giờ, không đính kèm chuỗi offset như `+07:00` hoặc tên vùng như `Asia/Ho_Chi_Minh`. Ví dụ, kết quả `2026-11-19 10:30:00` tự nó không cho biết đây là giờ UTC hay giờ địa phương. Ngữ nghĩa của nó phụ thuộc hàm tạo giá trị và cách ứng dụng lưu/diễn giải.

Vì vậy, khi truyền một giá trị ngày giờ qua API hoặc message queue, hãy quy định rõ đó là UTC instant hay local wall-clock time. Với timestamp dạng văn bản, ISO 8601 có offset như `2026-11-19T03:30:00Z` hoặc `2026-11-19T10:30:00+07:00` giúp thể hiện múi giờ rõ ràng hơn.

## 2. Khi nào MySQL lấy giá trị thời gian?

`NOW()`, `CURRENT_TIMESTAMP` và `UTC_TIMESTAMP()` trả về một giá trị ổn định trong phạm vi một câu lệnh. MySQL lấy thời gian tại lúc statement bắt đầu thực thi; những lần gọi hàm trong cùng statement sử dụng cùng mốc đó.

Ví dụ:

```sql
SELECT
    NOW(6) AS first_call,
    SLEEP(1) AS wait_result,
    NOW(6) AS second_call,
    CURRENT_TIMESTAMP(6) AS current_call;
```

Trong cùng câu `SELECT`, `first_call`, `second_call` và `current_call` có cùng giá trị thời gian dù `SLEEP(1)` làm câu lệnh kéo dài. Ví dụ dùng `SLEEP()` chỉ để minh họa thời điểm đánh giá; không đưa hàm này vào truy vấn ứng dụng thông thường.

### 2.1. Một statement nhiều dòng dùng cùng một mốc

Với câu lệnh ghi nhiều dòng, các dòng được ghi trong cùng statement nhận cùng giá trị `NOW()` nếu không truyền giá trị riêng:

```sql
INSERT INTO audit_event (event_type, created_at)
VALUES
    ('ORDER_CREATED', NOW(6)),
    ('PAYMENT_REQUESTED', NOW(6)),
    ('EMAIL_QUEUED', NOW(6));
```

Ba hàng được ghi bởi cùng một statement sẽ có cùng mốc `created_at`. Điều này hữu ích khi muốn tất cả bản ghi trong một batch thể hiện cùng thời điểm xử lý ở phía database.

### 2.2. NOW không phải thời điểm bắt đầu transaction

`NOW()` cố định theo statement, không cố định cho toàn bộ transaction. Hai câu lệnh khác nhau trong cùng một transaction có thể nhận các giá trị khác nhau:

```sql
START TRANSACTION;

INSERT INTO order_audit (order_id, action, occurred_at)
VALUES (1001, 'CREATED', NOW(6));

UPDATE orders
SET status = 'PROCESSING', updated_at = NOW(6)
WHERE order_id = 1001;

COMMIT;
```

Nếu hai statement chạy ở hai thời điểm khác nhau, `occurred_at` và `updated_at` có thể khác nhau dù chúng thuộc cùng transaction. Transaction bảo đảm tính nguyên tử của các thay đổi dữ liệu theo cơ chế InnoDB; nó không tự đóng băng đồng hồ ở thời điểm `START TRANSACTION`.

Nếu nhiều thao tác trong một transaction cần dùng chung một mốc nghiệp vụ, hãy lấy mốc một lần rồi truyền lại:

```sql
START TRANSACTION;
SET @operation_time = NOW(6);

INSERT INTO order_audit (order_id, action, occurred_at)
VALUES (1001, 'CREATED', @operation_time);

UPDATE orders
SET status = 'PROCESSING', updated_at = @operation_time
WHERE order_id = 1001;

COMMIT;
```

Trong ứng dụng thực tế, có thể lấy một `Instant` ở tầng service rồi bind cùng giá trị vào các statement. Nếu dùng biến session như `@operation_time`, cần nhớ biến tồn tại trên connection sau transaction; với connection pool, không để giá trị cũ vô tình được tái sử dụng ở request sau.

### 2.3. Phân biệt với SYSDATE()

`SYSDATE()` có ngữ nghĩa khác: nó trả về thời điểm hàm thực sự được thực thi, nên các lần gọi trong cùng statement có thể khác nhau. Điều này khác với `NOW()` vốn cố định tại đầu statement. `SYSDATE()` cũng có các lưu ý về tính xác định và replication; nếu không có nhu cầu rõ ràng, dùng `NOW()`/`CURRENT_TIMESTAMP` cho timestamp nghiệp vụ thường dễ dự đoán hơn.

## 3. Múi giờ của MySQL

MySQL có múi giờ ở cấp server và session. Giá trị `time_zone` của session quyết định cách các hàm như `NOW()` thể hiện thời gian và cách MySQL chuyển đổi giá trị khi đọc/ghi cột `TIMESTAMP`.

Kiểm tra các biến liên quan:

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@SYSTEM_TIME_ZONE AS system_time_zone;
```

- `@@GLOBAL.time_zone`: múi giờ mặc định server cấp cho kết nối mới.
- `@@SESSION.time_zone`: múi giờ đang áp dụng cho connection hiện tại.
- `@@SYSTEM_TIME_ZONE`: tên/giá trị múi giờ hệ điều hành mà server nhận diện khi khởi động; đây không phải biến để đặt múi giờ riêng cho từng session.

`time_zone` có thể là `SYSTEM`, một offset như `+00:00`, `+07:00`, hoặc tên vùng như `Asia/Ho_Chi_Minh` nếu bảng múi giờ của MySQL đã được nạp.

### 3.1. Đặt múi giờ cho session

Đặt múi giờ UTC cho connection hiện tại:

```sql
SET time_zone = '+00:00';
```

Hoặc dùng tên vùng nếu timezone tables đã có:

```sql
SET time_zone = 'Asia/Ho_Chi_Minh';
```

Lệnh `SET time_zone` không có từ khóa `GLOBAL` sẽ áp dụng cho session hiện tại. Các connection khác không bị thay đổi. Đây là lựa chọn thường dùng khi ứng dụng lấy connection từ pool: cấu hình pool để mỗi connection có session timezone nhất quán ngay khi được tạo hoặc checkout.

### 3.2. Đặt múi giờ mặc định cho kết nối mới

Quản trị viên có thể thay đổi giá trị global:

```sql
SET GLOBAL time_zone = '+00:00';
```

Thay đổi này ảnh hưởng tới các session mới sau đó; những session đang mở vẫn giữ `@@SESSION.time_zone` hiện tại. Cấu hình global runtime có thể mất sau khi MySQL restart. Nếu muốn duy trì, đặt `default-time-zone` trong phần `[mysqld]` của tệp cấu hình và khởi động lại theo quy trình vận hành:

```ini
[mysqld]
default-time-zone = '+00:00'
```

Việc thay đổi global timezone cần quyền quản trị phù hợp và phải xem xét ứng dụng hiện hữu. Không đổi múi giờ server đang chạy chỉ để sửa một vài giá trị bị lệch mà chưa xác định cách các client lưu dữ liệu.

### 3.3. Offset cố định và tên vùng

Offset `+07:00` luôn có độ lệch bảy giờ so với UTC; nó không mang quy tắc lịch sử hoặc daylight saving time (DST). Tên vùng như `America/New_York` chứa quy tắc đổi giờ theo lịch sử và thời điểm. Với khu vực có DST, tên vùng thường phù hợp hơn offset cố định khi chuyển đổi giờ địa phương.

MySQL cần timezone tables được nạp để nhận diện tên vùng. Nếu `SET time_zone = 'Asia/Ho_Chi_Minh'` báo lỗi múi giờ không hợp lệ, kiểm tra dữ liệu timezone của server và quy trình cập nhật theo hệ điều hành. Offset dạng `+00:00` không cần tra bảng tên vùng.

## 4. NOW và UTC_TIMESTAMP dưới các session timezone khác nhau

Ví dụ, thay đổi session sang UTC rồi đọc hai hàm:

```sql
SET time_zone = '+00:00';
SELECT NOW(6), CURRENT_TIMESTAMP(6), UTC_TIMESTAMP(6);
```

Trong session UTC, ba giá trị gần như trùng nhau vì `NOW()`/`CURRENT_TIMESTAMP` đang dùng UTC và `UTC_TIMESTAMP()` cũng trả UTC.

Chuyển session sang offset `+07:00`:

```sql
SET time_zone = '+07:00';
SELECT NOW(6), CURRENT_TIMESTAMP(6), UTC_TIMESTAMP(6);
```

`NOW()` và `CURRENT_TIMESTAMP` thể hiện giờ theo `+07:00`; `UTC_TIMESTAMP()` vẫn là giờ UTC. Các giá trị đại diện cùng một thời điểm thực tế, chỉ khác cách biểu diễn theo múi giờ.

Không dùng `UTC_TIMESTAMP()` để suy ra timezone của client. Hàm này luôn trả UTC, không biết người dùng đang ở đâu. Nếu cần hiển thị giờ địa phương, ứng dụng phải biết timezone của người dùng hoặc nhận timezone từ cấu hình nghiệp vụ.

## 5. NOW, CURRENT_TIMESTAMP và cột TIMESTAMP/DATETIME

Hai kiểu cột `TIMESTAMP` và `DATETIME` có cách xử lý múi giờ khác nhau:

| Đặc điểm | `TIMESTAMP` | `DATETIME` |
|---|---|---|
| Ý nghĩa lưu trữ | Thời điểm được chuyển đổi giữa session timezone và UTC | Giá trị ngày giờ theo lịch, không tự gắn timezone |
| Khi ghi | MySQL diễn giải giá trị theo session timezone rồi chuyển sang UTC để lưu | Lưu các thành phần ngày giờ được gửi vào, không tự chuyển timezone |
| Khi đọc | Chuyển từ UTC sang session timezone của connection | Trả lại giá trị đã lưu, không chuyển timezone |
| Miền giá trị của MySQL 8.0 | Xấp xỉ 1970-01-01 UTC đến 2038-01-19 UTC | 1000-01-01 đến 9999-12-31 |
| Dùng khi | Cần biểu diễn một instant và muốn MySQL chuyển đổi theo session timezone | Lưu giờ lịch, ngày hẹn, giờ mở cửa hoặc giá trị mà timezone được quản lý riêng |

`TIMESTAMP` không lưu tên vùng hoặc offset gốc của người gửi. Nếu cần biết người dùng nhập giờ ở vùng nào, hãy lưu timezone ID riêng, ví dụ `Asia/Ho_Chi_Minh`, bên cạnh thời điểm hoặc giá trị lịch.

### 5.1. Ví dụ ghi và đọc TIMESTAMP

Giả sử session timezone là `+07:00`:

```sql
SET time_zone = '+07:00';

CREATE TABLE event_time_demo (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    occurred_at TIMESTAMP(6) NOT NULL,
    wall_clock_at DATETIME(6) NOT NULL,
    PRIMARY KEY (event_id)
);

INSERT INTO event_time_demo (occurred_at, wall_clock_at)
VALUES (NOW(6), NOW(6));

SELECT occurred_at, wall_clock_at
FROM event_time_demo;
```

`NOW(6)` trả về giờ của session `+07:00`. Khi gán cho `TIMESTAMP`, MySQL chuyển giá trị đó sang UTC để lưu; khi đọc trong cùng session, MySQL chuyển lại về `+07:00`. Với `DATETIME`, MySQL lưu nguyên các thành phần giờ địa phương như đã gửi, không chuyển đổi.

Nếu đọc cùng hàng trong session UTC:

```sql
SET time_zone = '+00:00';

SELECT occurred_at, wall_clock_at
FROM event_time_demo;
```

`occurred_at` sẽ được hiển thị theo UTC, còn `wall_clock_at` vẫn giữ nguyên giờ đã lưu. Đây là lý do cần thống nhất ngữ nghĩa cột trước khi cho nhiều ứng dụng ở múi giờ khác nhau cùng ghi/đọc.

### 5.2. Cẩn thận khi ghi UTC_TIMESTAMP vào TIMESTAMP

`UTC_TIMESTAMP()` trả về giá trị ngày giờ UTC, nhưng khi gán vào cột `TIMESTAMP`, MySQL vẫn diễn giải giá trị đầu vào theo `@@SESSION.time_zone` rồi chuyển sang UTC để lưu. Nếu session đang là `+07:00`, đưa trực tiếp kết quả UTC của `UTC_TIMESTAMP()` vào `TIMESTAMP` có thể khiến thời điểm bị lệch bảy giờ.

Ví dụ không an toàn khi session đang `+07:00`:

```sql
SET time_zone = '+07:00';

INSERT INTO event_time_demo (occurred_at, wall_clock_at)
VALUES (UTC_TIMESTAMP(6), UTC_TIMESTAMP(6));
```

Với `occurred_at`, giá trị UTC được hiểu nhầm là giờ địa phương `+07:00` trước khi chuyển sang UTC để lưu. `wall_clock_at` giữ nguyên chuỗi thành phần UTC; nó không tự biết đây là giờ UTC.

Hai cách rõ ràng để tránh nhầm:

1. Đặt session timezone của ứng dụng là UTC và dùng `NOW(6)`/`CURRENT_TIMESTAMP(6)` cho cột `TIMESTAMP`.
2. Nếu chủ động truyền giá trị UTC vào `TIMESTAMP`, bảo đảm session timezone cũng là `+00:00` trong lúc ghi.

Đối với cột `DATETIME` được quy ước lưu UTC, `UTC_TIMESTAMP(6)` có thể được lưu nguyên giá trị UTC, nhưng phải ghi rõ quy ước đó trong schema và ứng dụng vì MySQL không tự chuyển đổi khi đọc.

## 6. DEFAULT CURRENT_TIMESTAMP và ON UPDATE

MySQL cho phép tự động gán thời điểm hiện tại khi insert hoặc cập nhật bằng `DEFAULT CURRENT_TIMESTAMP` và `ON UPDATE CURRENT_TIMESTAMP`.

Ví dụ bảng audit:

```sql
CREATE TABLE task (
    task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (task_id)
) ENGINE=InnoDB;
```

- `created_at` tự nhận thời điểm insert nếu câu lệnh không cung cấp giá trị.
- `updated_at` nhận thời điểm insert và tự cập nhật khi một cột khác của hàng thực sự thay đổi giá trị.
- Nếu câu `UPDATE` gán lại đúng các giá trị hiện tại, MySQL không nhất thiết tự thay đổi `updated_at`.
- Ứng dụng có thể gán tường minh `updated_at = CURRENT_TIMESTAMP(6)` nếu nghiệp vụ yêu cầu cập nhật mốc thời gian trong một thao tác cụ thể.

`CURRENT_TIMESTAMP` cũng có thể dùng với `DATETIME`. Chọn `TIMESTAMP` hay `DATETIME` theo semantics và miền giá trị, không chỉ vì cú pháp default giống nhau.

### 6.1. Độ chính xác phần giây

MySQL hỗ trợ fractional seconds precision (FSP) từ 0 đến 6:

| Khai báo | Độ chính xác |
|---|---|
| `NOW()` hoặc `NOW(0)` | Không có phần giây thập phân |
| `NOW(3)` | Millisecond, 3 chữ số |
| `NOW(6)` | Microsecond, 6 chữ số |
| `TIMESTAMP` / `DATETIME` | FSP mặc định là 0 |
| `TIMESTAMP(6)` / `DATETIME(6)` | Lưu phần giây tới microsecond |

Muốn lưu microsecond, cả hàm lấy thời gian và cột nên được khai báo với precision phù hợp:

```sql
CREATE TABLE request_log (
    request_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (request_id)
);

INSERT INTO request_log () VALUES ();
SELECT received_at FROM request_log;
```

Nếu hàm trả về precision 6 nhưng cột chỉ có precision 0 hoặc 3, phần thập phân sẽ được xử lý theo quy tắc chuyển đổi của MySQL. SQL mode `TIME_TRUNCATE_FRACTIONAL` điều khiển việc cắt phần dư thay vì làm tròn khi gán vào cột có FSP thấp hơn. Hãy chọn precision thống nhất trong schema, ứng dụng và API để tránh mất độ chính xác không mong muốn.

## 7. Sử dụng trong truy vấn và transaction

### 7.1. Lọc dữ liệu theo thời điểm hiện tại

Ví dụ lấy các đơn hàng được tạo trong 24 giờ gần đây:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= NOW() - INTERVAL 24 HOUR;
```

Nếu `created_at` là `TIMESTAMP`, hãy bảo đảm session timezone được thiết lập theo quy ước của ứng dụng. Nếu cột `DATETIME` lưu UTC, hãy so sánh với `UTC_TIMESTAMP()` thay vì `NOW()` trong session địa phương.

Ví dụ với cột `DATETIME` lưu UTC:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= UTC_TIMESTAMP() - INTERVAL 24 HOUR;
```

Tránh bọc cột được index trong hàm chuyển đổi ở điều kiện `WHERE` nếu có thể, vì điều đó có thể làm giảm khả năng dùng range index. Hãy chuẩn hóa biên thời gian trước rồi so sánh trực tiếp với cột.

### 7.2. Một mốc chung cho nhiều thao tác

Khi cần cùng một mốc cho audit row, bản ghi nghiệp vụ và outbox event, hãy tạo mốc một lần ở tầng ứng dụng hoặc session rồi bind lại:

```java
Instant operationTime = clock.instant();

// Dùng cùng operationTime làm tham số cho các câu INSERT/UPDATE
// trong cùng transaction JDBC.
```

Khi dùng JDBC, nên biểu diễn instant bằng `java.time.Instant` và chuyển đổi sang kiểu JDBC phù hợp với Connector/J và schema. Nếu dùng `LocalDateTime`, ứng dụng cần biết rõ timezone quy ước vì kiểu này không mang offset hoặc zone.

### 7.3. Lấy thời gian ở database hay ở ứng dụng?

| Nhu cầu | Cách thường phù hợp |
|---|---|
| Một statement ghi nhiều dòng cần chung thời điểm database | `NOW(6)` hoặc `CURRENT_TIMESTAMP(6)` |
| Nhiều statement trong một transaction cần cùng mốc | Lấy một lần ở ứng dụng hoặc lưu vào biến/session parameter rồi tái sử dụng |
| Cần UTC tường minh cho phép tính trong SQL | `UTC_TIMESTAMP(6)` |
| Cần đồng hồ thống nhất giữa nhiều service | Đồng bộ clock hệ thống và quy ước truyền instant UTC; có thể lấy từ một nguồn thời gian được quản lý |
| Cần đo thời lượng thực thi | Dùng monotonic clock ở ứng dụng thay vì lấy hiệu hai wall-clock timestamp |

MySQL lấy thời gian từ đồng hồ hệ thống của máy chủ. `NOW()` không phải đồng hồ monotonic; nếu đồng hồ hệ điều hành được điều chỉnh, giá trị wall-clock giữa các statement có thể thay đổi theo. Không dùng nó làm bộ đo thời lượng chính xác cho benchmark.

## 8. Connection pool và múi giờ session

Ứng dụng thường tái sử dụng kết nối thông qua HikariCP hoặc một connection pool khác. `time_zone` là thuộc tính session, vì vậy nếu một request thay đổi timezone rồi trả connection về pool, request tiếp theo có thể nhận lại connection với timezone đã bị thay đổi.

Các biện pháp thực tế:

- Cấu hình mọi connection dùng một timezone thống nhất, thường là UTC.
- Thiết lập timezone khi khởi tạo connection hoặc qua cơ chế connection initialization của pool.
- Nếu ứng dụng thay đổi timezone theo request, phải khôi phục trạng thái trước khi trả connection về pool; tốt hơn là tránh thay đổi theo request.
- Không giả định `SET GLOBAL time_zone` sẽ thay đổi các session đang tồn tại trong pool.
- Ghi rõ cột nào lưu instant UTC (`TIMESTAMP` hoặc `DATETIME` theo quy ước) và cột nào lưu local wall-clock time.

Ví dụ câu lệnh khởi tạo session:

```sql
SET time_zone = '+00:00';
```

Chạy câu này trên từng connection cần được cấu hình, không chỉ một connection bất kỳ trong pool.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `NOW()` lệch giờ so với máy người dùng | Session timezone khác timezone người dùng hoặc khác quy ước lưu trữ | Kiểm tra `@@SESSION.time_zone`, `@@GLOBAL.time_zone`; xác định cột là `TIMESTAMP` hay `DATETIME` |
| `NOW()` và `UTC_TIMESTAMP()` khác nhau | Session timezone không phải UTC | Đây là hành vi bình thường; kiểm tra offset và quy ước của session |
| Ghi `UTC_TIMESTAMP()` vào `TIMESTAMP` rồi đọc thấy lệch | MySQL diễn giải đầu vào theo session timezone trước khi lưu UTC | Đặt session timezone `+00:00` khi ghi hoặc dùng `NOW()` với session UTC |
| Một transaction có hai `NOW()` khác nhau | Hai lần gọi thuộc hai statement khác nhau | Lấy một mốc rồi tái sử dụng nếu nghiệp vụ cần cùng timestamp |
| Microsecond bị mất | Hàm hoặc cột dùng FSP thấp | Dùng `NOW(6)` và `TIMESTAMP(6)`/`DATETIME(6)`; kiểm tra `TIME_TRUNCATE_FRACTIONAL` |
| Connection pool trả giờ khác nhau giữa request | Session timezone bị thay đổi và không được reset | Chuẩn hóa timezone khi khởi tạo connection và khôi phục session state |
| `SET time_zone = 'Region/City'` báo timezone không hợp lệ | Timezone tables chưa được nạp hoặc thiếu tên vùng | Nạp/cập nhật timezone tables hoặc dùng offset cố định phù hợp |

Lệnh kiểm tra nhanh:

```sql
SELECT
    NOW(6) AS session_now,
    UTC_TIMESTAMP(6) AS utc_now,
    @@SESSION.time_zone AS session_tz,
    @@GLOBAL.time_zone AS global_tz,
    @@SYSTEM_TIME_ZONE AS system_tz;

SHOW CREATE TABLE orders\G
```

Luôn kiểm tra cùng một connection với câu lệnh đang gây lỗi. Chạy `SELECT @@SESSION.time_zone` trên một connection quản trị khác không cho biết timezone của session ứng dụng.

## 10. Bài thực hành

Thực hiện trong database lab riêng:

1. Chạy `SELECT NOW(6), CURRENT_TIMESTAMP(6), UTC_TIMESTAMP(6)` khi session ở `SYSTEM`, `+00:00` và `+07:00`; ghi lại cách các giá trị thay đổi.
2. Dùng một câu `SELECT` có hai lần gọi `NOW(6)` và một khoảng chờ ngắn để xác nhận các lần gọi trong cùng statement dùng chung mốc.
3. Thực hiện hai câu `INSERT` trong một transaction, mỗi câu gọi `NOW(6)`; so sánh timestamp và giải thích vì sao NOW không cố định theo transaction.
4. Tạo bảng có `TIMESTAMP(6)` và `DATETIME(6)`. Insert `NOW(6)` khi session ở `+07:00`, sau đó đọc lại từ session `+00:00` để quan sát khác biệt.
5. Trong lab, thử ghi `UTC_TIMESTAMP(6)` vào cột `TIMESTAMP` khi session là `+07:00`, sau đó đổi session sang UTC để kiểm tra lệch giờ. Lặp lại khi session là `+00:00`.
6. Tạo bảng có `DEFAULT CURRENT_TIMESTAMP(6)` và `ON UPDATE CURRENT_TIMESTAMP(6)`. Thử insert, update một cột khác, rồi update với cùng giá trị cũ để quan sát điều kiện tự cập nhật.
7. Tạo cột `DATETIME(3)` và `DATETIME(6)`, insert giá trị microsecond rồi kiểm tra độ chính xác sau khi lưu.
8. Viết một ví dụ JDBC dùng cùng `Instant` cho hai statement trong transaction và xác minh cả hai bản ghi có chung mốc.

Bạn hoàn thành bài khi có thể dự đoán kết quả của ba hàm theo session timezone, giải thích thời điểm đánh giá statement, chọn đúng kiểu cột và tránh lỗi lệch giờ khi ghi/đọc qua nhiều connection.

## 11. Nguyên tắc cần ghi nhớ

- `CURRENT_TIMESTAMP` là synonym của `NOW()`; cả hai dùng timezone của session.
- `UTC_TIMESTAMP()` trả ngày giờ UTC bất kể session timezone.
- Các hàm `NOW`/`CURRENT_TIMESTAMP`/`UTC_TIMESTAMP` ổn định trong một statement, không cố định suốt transaction.
- `TIMESTAMP` chuyển đổi theo session timezone khi ghi/đọc; `DATETIME` không tự chuyển timezone.
- Khi lưu instant, thống nhất session timezone UTC và quy ước UTC xuyên suốt ứng dụng.
- Cẩn thận khi gán `UTC_TIMESTAMP()` vào `TIMESTAMP` nếu session không ở UTC.
- Dùng FSP 3 hoặc 6 khi nghiệp vụ cần millisecond/microsecond; đồng bộ precision của hàm và cột.
- Chuẩn hóa session timezone trên connection pool; `SET GLOBAL` không thay đổi các session đã mở.
- Không dùng wall-clock timestamp để đo thời lượng; dùng monotonic clock ở ứng dụng.
