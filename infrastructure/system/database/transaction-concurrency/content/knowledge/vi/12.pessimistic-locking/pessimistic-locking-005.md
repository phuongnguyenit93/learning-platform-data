# Chờ khóa, NOWAIT và thời hạn chờ

Khi nhiều giao dịch cùng truy cập một tài nguyên, hệ quản trị cơ sở dữ liệu phải quyết định giao dịch nào được cấp khóa trước. Nếu một giao dịch đang giữ khóa xung đột, giao dịch tiếp theo thường phải **chờ khóa** (*lock wait*). Chờ là hành vi bình thường trong điều khiển đồng thời, nhưng nếu thời gian chờ quá dài, ứng dụng có thể phản hồi chậm, giữ nhiều tài nguyên trong lúc chờ và làm giảm thông lượng.

Có ba chính sách thường gặp khi một thao tác yêu cầu khóa đang bị chặn:

- **Chờ theo mặc định:** tiếp tục chờ cho đến khi khóa được cấp, giao dịch bị hủy, deadlock được phát hiện hoặc một giới hạn khác kết thúc yêu cầu.
- **NOWAIT:** nếu không thể cấp khóa ngay, trả lỗi ngay lập tức thay vì xếp hàng chờ.
- **Thời hạn chờ (lock timeout):** chỉ chờ trong một khoảng thời gian đã cấu hình; nếu hết hạn mà khóa vẫn chưa được cấp, thao tác nhận lỗi timeout.

Các chính sách này giúp ứng dụng lựa chọn cách phản ứng phù hợp với nghiệp vụ: chờ để hoàn tất, thử lại sau, báo tài nguyên đang bận, hoặc chuyển sang xử lý công việc khác.

## 1. Vì sao giao dịch phải chờ khóa?

Giả sử T1 đang cập nhật hàng tài khoản có `id = 10` và giữ khóa độc quyền (`X`). T2 cũng muốn cập nhật cùng hàng nên phải yêu cầu khóa `X`. Hai khóa `X` trên cùng tài nguyên không tương thích, vì vậy T2 phải chờ T1 kết thúc hoặc nhả khóa.

```text
Thời điểm     Giao dịch T1                     Giao dịch T2
----------------------------------------------------------------
1             BEGIN
2             UPDATE account(10), giữ X
3                                               BEGIN
4                                               UPDATE account(10), yêu cầu X
5                                               Chờ T1
6             COMMIT, giải phóng X
7                                               Được cấp X
8                                               UPDATE tiếp tục, COMMIT
```

T2 không nhất thiết đang gặp lỗi. Nó chỉ chưa thể tiếp tục vì một giao dịch khác đang giữ khóa xung đột. Khi T1 commit hoặc rollback và khóa được giải phóng, hệ quản trị có thể cấp khóa cho T2.

Khóa gây chờ có thể nằm ở nhiều phạm vi: hàng, trang, bảng, khóa chỉ mục, khoảng khóa hoặc tài nguyên metadata. Loại tài nguyên bị chặn phụ thuộc câu lệnh, chỉ mục, mức cô lập và hệ quản trị. Một câu lệnh tưởng như chỉ cập nhật một hàng cũng có thể cần thêm khóa để duy trì chỉ mục, ràng buộc khóa ngoại hoặc cấu trúc nội bộ.

## 2. Chờ khóa mặc định

Nếu câu lệnh không yêu cầu chính sách khác, hệ quản trị thường dùng chính sách chờ mặc định của nó. Câu lệnh có thể tiếp tục khi khóa xung đột được giải phóng.

Ví dụ minh họa với hai phiên SQL:

```sql
-- Phiên T1
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

-- T1 chưa commit nên vẫn giữ khóa cần thiết.
```

```sql
-- Phiên T2
BEGIN;

UPDATE account
SET balance = balance + 100
WHERE id = 10;

-- Câu UPDATE có thể chờ T1 giải phóng khóa.
```

Khi T1 chạy `COMMIT` hoặc `ROLLBACK`, T2 có thể tiếp tục. Nếu T1 giữ giao dịch mở quá lâu, T2 và các giao dịch khác cần tài nguyên liên quan có thể tích lũy thời gian chờ.

Chờ mặc định phù hợp khi thao tác cần hoàn tất và thời gian tranh chấp thường ngắn. Tuy nhiên, không nên để giao dịch giữ khóa trong khi chờ người dùng, gọi dịch vụ HTTP hoặc thực hiện công việc lâu ngoài cơ sở dữ liệu.

## 3. NOWAIT: từ chối chờ ngay lập tức

`NOWAIT` yêu cầu hệ quản trị thử cấp khóa ngay. Nếu khóa đang bị một giao dịch khác giữ theo cách gây xung đột, câu lệnh trả lỗi thay vì chờ.

Ví dụ, một tác vụ muốn lấy quyền xử lý đơn hàng ngay lúc này. Nếu đơn hàng đang được giao dịch khác khóa, ứng dụng có thể báo “đang được xử lý” hoặc đưa yêu cầu vào hàng đợi ở tầng ứng dụng.

Với PostgreSQL:

```sql
BEGIN;

SELECT id, status
FROM orders
WHERE id = 5001
FOR UPDATE NOWAIT;

-- Nếu hàng đang bị khóa xung đột, câu lệnh lỗi ngay.
-- Nếu lấy được khóa, giao dịch có thể xử lý đơn hàng.

COMMIT;
```

Với Oracle Database, locking read có thể dùng cùng chính sách:

```sql
SELECT id, status
FROM orders
WHERE id = 5001
FOR UPDATE NOWAIT;
```

Với MySQL InnoDB (các phiên bản hỗ trợ cú pháp này):

```sql
START TRANSACTION;

SELECT id, status
FROM orders
WHERE id = 5001
FOR UPDATE NOWAIT;

COMMIT;
```

Các ví dụ trên dùng cú pháp gần giống nhau nhưng hành vi chi tiết sau lỗi phụ thuộc hệ quản trị. Trong PostgreSQL, lỗi câu lệnh thường làm transaction chuyển sang trạng thái lỗi; ứng dụng phải rollback transaction hoặc rollback về savepoint trước khi tiếp tục. Với MySQL InnoDB, lỗi NOWAIT làm câu lệnh thất bại; ứng dụng vẫn cần xử lý transaction theo đúng luồng nghiệp vụ và kiểm tra trạng thái sau lỗi.

### Khi nào NOWAIT hữu ích?

- Một API cần phản hồi nhanh nếu tài nguyên đang bận.
- Một thao tác quản trị không nên xếp hàng chờ trên bản ghi đang được xử lý.
- Một worker có thể thử lấy công việc khác khi một bản ghi đã bị worker khác khóa.
- Ứng dụng muốn tự quyết định chính sách retry thay vì giữ kết nối và transaction trong lúc chờ.

NOWAIT không có nghĩa “bỏ qua hàng đang khóa và lấy hàng khác”. Nó có nghĩa yêu cầu khóa thất bại ngay khi gặp xung đột. Nếu mục tiêu là lấy những hàng chưa bị khóa trong một tập kết quả, hãy tìm hiểu `SKIP LOCKED` ở phần sau.

## 4. Thời hạn chờ khóa (lock timeout)

Thời hạn chờ cho phép giao dịch đợi trong một khoảng giới hạn. Nếu khóa chưa được cấp khi hết thời gian, hệ quản trị trả lỗi timeout.

Ví dụ, một yêu cầu nghiệp vụ chấp nhận đợi tối đa hai giây để lấy khóa. Nếu giao dịch khác vẫn giữ khóa sau khoảng đó, ứng dụng có thể trả lỗi tạm thời, thử lại sau một khoảng backoff hoặc yêu cầu người dùng thực hiện lại.

```text
T2 yêu cầu khóa tại thời điểm 0
       |
       +---- khóa được nhả trước hạn ----> tiếp tục
       |
       +---- hết thời hạn, vẫn bị chặn --> lock timeout
```

Thời hạn chờ khóa khác với thời hạn thực thi câu lệnh:

- **Lock timeout** giới hạn thời gian chờ để lấy một khóa cụ thể hoặc một lần chờ khóa, tùy hệ quản trị.
- **Statement/query timeout** giới hạn thời gian thực thi của cả câu lệnh. Câu lệnh có thể hết hạn vì truy vấn chậm, I/O, CPU hoặc chờ tài nguyên khác, dù không có lock wait dài.
- **Request deadline** là giới hạn tổng thời gian mà ứng dụng dành cho một yêu cầu. Nó có thể bao gồm thời gian kết nối, chờ pool, nhiều câu SQL, lock wait và xử lý ứng dụng.

Một câu lệnh có thể trải qua nhiều lần chờ khóa. Vì vậy, một cấu hình timeout cho từng lần chờ không nhất thiết bảo đảm tổng thời gian của câu lệnh hoặc yêu cầu nằm trong cùng giới hạn. Ứng dụng nên phối hợp timeout ở database, JDBC/driver, connection pool và HTTP request theo một ngân sách thời gian thống nhất.

## 5. Cấu hình timeout trong các hệ quản trị phổ biến

Cú pháp và đơn vị timeout không giống nhau giữa các sản phẩm. Không sao chép nguyên một lệnh cấu hình từ hệ quản trị này sang hệ quản trị khác.

### PostgreSQL: `lock_timeout`

PostgreSQL cung cấp tham số `lock_timeout`, xác định thời gian một câu lệnh được phép chờ để lấy khóa. Có thể giới hạn phạm vi trong một transaction bằng `SET LOCAL`:

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';

SELECT id, status
FROM orders
WHERE id = 5001
FOR UPDATE;

COMMIT;
```

Nếu phải chờ khóa quá thời hạn, PostgreSQL báo lỗi lock timeout. Lỗi làm transaction hiện tại ở trạng thái cần rollback; `SET LOCAL` cũng chỉ có hiệu lực trong transaction hiện tại. Giá trị `lock_timeout = 0` có nghĩa là tắt giới hạn chờ khóa, tức chờ không giới hạn theo tham số này; nó không tương đương NOWAIT.

Nếu muốn không chờ cho một locking read cụ thể, có thể dùng `NOWAIT` ngay trong câu lệnh:

```sql
SELECT id, status
FROM orders
WHERE id = 5001
FOR UPDATE NOWAIT;
```

### Oracle Database: `NOWAIT` và `WAIT n`

Oracle hỗ trợ quy định thời gian chờ ngay trong locking read:

```sql
-- Không chờ nếu không lấy được khóa ngay
SELECT id, status
FROM orders
WHERE id = 5001
FOR UPDATE NOWAIT;

-- Chờ tối đa 3 giây
SELECT id, status
FROM orders
WHERE id = 5001
FOR UPDATE WAIT 3;
```

`WAIT 3` biểu thị số giây theo cú pháp Oracle. Nếu hết thời gian mà khóa vẫn chưa sẵn sàng, câu lệnh trả lỗi. Đây là cú pháp đặc thù của Oracle.

### MySQL InnoDB: `innodb_lock_wait_timeout`

InnoDB cung cấp biến `innodb_lock_wait_timeout` để cấu hình thời gian chờ khóa hàng. Có thể đặt theo session:

```sql
SET SESSION innodb_lock_wait_timeout = 3;

START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE id = 5001;

COMMIT;
```

Biến này dùng đơn vị giây và áp dụng cho chờ khóa InnoDB. Nó không phải timeout tổng quát cho mọi loại khóa; ví dụ, chờ metadata lock có cơ chế cấu hình riêng như `lock_wait_timeout`. MySQL InnoDB cũng hỗ trợ `NOWAIT` trong locking read ở các phiên bản phù hợp.

Khi InnoDB gặp lock wait timeout, mặc định thường chỉ câu lệnh hiện tại bị rollback; cấu hình `innodb_rollback_on_timeout` có thể thay đổi hành vi rollback transaction. Các khóa mà transaction đã lấy trước đó có thể vẫn còn được giữ nếu transaction vẫn mở. Ứng dụng cần chủ động rollback transaction khi không thể tiếp tục nghiệp vụ một cách nhất quán.

### SQL Server: `SET LOCK_TIMEOUT`

SQL Server dùng `SET LOCK_TIMEOUT` với đơn vị mili giây:

```sql
-- Chờ khóa tối đa 2 giây trong session hiện tại
SET LOCK_TIMEOUT 2000;

BEGIN TRANSACTION;

UPDATE dbo.Orders
SET Status = 'PROCESSING'
WHERE Id = 5001;

COMMIT TRANSACTION;
```

Các giá trị thường gặp:

| Giá trị | Ý nghĩa |
|---:|---|
| `-1` | Chờ vô thời hạn (giá trị mặc định phổ biến) |
| `0` | Không chờ; nếu khóa không sẵn sàng thì trả lỗi ngay |
| Số dương | Số mili giây tối đa chờ khóa |

`SET LOCK_TIMEOUT` có phạm vi session và tiếp tục có hiệu lực cho đến khi session thay đổi giá trị. Nếu dùng connection pool, cần khôi phục cấu hình session phù hợp để tránh ảnh hưởng request tiếp theo sử dụng lại connection.

## 6. NOWAIT, timeout và deadlock khác nhau thế nào?

Ba trường hợp đều có thể khiến câu lệnh không hoàn tất, nhưng nguyên nhân và cách xử lý khác nhau.

| Tình huống | Điều kiện xảy ra | Hành vi | Hướng xử lý thường gặp |
|---|---|---|---|
| Chờ khóa bình thường | Có khóa xung đột nhưng có thể được nhả | Câu lệnh tiếp tục chờ | Giữ transaction ngắn, theo dõi thời gian chờ |
| NOWAIT | Khóa không thể cấp ngay | Trả lỗi ngay | Báo bận, thử công việc khác hoặc retry có backoff |
| Lock timeout | Đã chờ quá giới hạn cấu hình | Trả lỗi timeout | Rollback phù hợp, retry có giới hạn hoặc báo lỗi tạm thời |
| Deadlock | Các giao dịch tạo thành chu trình chờ lẫn nhau | Hệ quản trị chọn giao dịch nạn nhân và hủy/rollback theo sản phẩm | Retry toàn bộ transaction nạn nhân |

Deadlock không đơn thuần là “đợi quá lâu”. Ví dụ:

```text
T1 giữ khóa A, chờ khóa B
T2 giữ khóa B, chờ khóa A

T1 không thể tiếp tục nếu T2 không nhả B.
T2 không thể tiếp tục nếu T1 không nhả A.
       => tạo chu trình chờ (deadlock)
```

Hệ quản trị có thể phát hiện chu trình trong đồ thị chờ và chọn một giao dịch làm nạn nhân. Điều này có thể xảy ra trước khi lock timeout hết hạn. Ngược lại, một giao dịch chỉ chờ một khóa lâu nhưng không tạo chu trình có thể kết thúc bằng lock timeout thay vì deadlock.

Không nên dùng timeout lớn để “sửa” deadlock. Cần xem thứ tự lấy khóa, giảm thời gian giữ khóa và xử lý retry cho lỗi deadlock.

## 7. `SKIP LOCKED`: bỏ qua hàng đang bị khóa

`SKIP LOCKED` giải quyết một nhu cầu khác với NOWAIT. Khi truy vấn chọn nhiều hàng để xử lý, hệ quản trị có thể bỏ qua những hàng hiện đang bị khóa xung đột và trả về những hàng còn lại có thể khóa được.

Mẫu này hữu ích cho bảng hàng đợi công việc. Nhiều worker có thể cùng lấy các công việc khác nhau mà không phải chờ nhau trên một hàng đang được worker khác xử lý.

Ví dụ với PostgreSQL:

```sql
BEGIN;

SELECT id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at
LIMIT 10
FOR UPDATE SKIP LOCKED;

-- Đánh dấu các job vừa lấy là đang xử lý trong cùng transaction.

COMMIT;
```

Với MySQL InnoDB, cú pháp locking read `FOR UPDATE SKIP LOCKED` cũng được hỗ trợ trong các phiên bản phù hợp. Cần kiểm tra tài liệu phiên bản đang dùng.

Điểm cần nhớ:

- `NOWAIT` làm cả yêu cầu khóa thất bại khi gặp xung đột.
- `SKIP LOCKED` bỏ qua hàng đang bị khóa và tiếp tục tìm hàng khác.
- Kết quả `SKIP LOCKED` không phải ảnh chụp đầy đủ của mọi hàng thỏa điều kiện. Nó phù hợp với worker queue, không phù hợp cho báo cáo cần đọc toàn bộ dữ liệu hoặc kiểm tra bất biến nghiệp vụ.
- Một hàng bị khóa lâu có thể liên tục bị bỏ qua và bị trì hoãn xử lý. Hệ thống hàng đợi cần có cơ chế giám sát, lease/recovery hoặc phát hiện công việc bị kẹt.

## 8. Thiết kế timeout cho ứng dụng

Một timeout hữu ích cần gắn với mục tiêu phản hồi và khả năng phục hồi của nghiệp vụ. Cấu hình quá ngắn có thể tạo nhiều lỗi và retry không cần thiết; cấu hình quá dài có thể giữ connection và transaction trong lúc ứng dụng không còn đủ thời gian trả lời người dùng.

Một số nguyên tắc thực tế:

1. **Đặt ngân sách thời gian từ request:** nếu API chỉ có một khoảng thời gian ngắn để trả lời, lock timeout phải nhỏ hơn phần ngân sách còn lại sau kết nối và xử lý.
2. **Giữ transaction ngắn:** không thực hiện gọi HTTP, chờ nhập liệu hoặc công việc tính toán dài trong khi đang giữ khóa.
3. **Phân loại lỗi:** phân biệt lock timeout, NOWAIT conflict, deadlock, statement timeout và lỗi kết nối. Mỗi loại có chính sách phục hồi khác nhau.
4. **Retry toàn bộ transaction:** khi lỗi làm transaction bị hủy hoặc snapshot không còn phù hợp, bắt đầu transaction mới và đọc lại dữ liệu. Không chỉ chạy lại riêng câu `UPDATE` cuối cùng nếu quyết định trước đó dựa trên dữ liệu cũ.
5. **Dùng backoff và giới hạn lần thử:** tránh cho nhiều request đồng loạt retry liên tục và tạo thêm tải khi tài nguyên vẫn đang bận.
6. **Không retry vô điều kiện:** nếu nghiệp vụ không thể tự động lặp an toàn, trả lỗi phù hợp hoặc yêu cầu người dùng xác nhận lại.
7. **Theo dõi thời gian chờ:** ghi nhận loại khóa, câu lệnh, thời gian chờ và giao dịch giữ khóa lâu; tránh ghi dữ liệu nhạy cảm vào log.
8. **Kiểm tra session khi dùng connection pool:** các thiết lập theo session như `SET LOCK_TIMEOUT` hoặc biến session của MySQL có thể tồn tại khi connection được tái sử dụng qua pool.

Ví dụ chính sách retry ở tầng ứng dụng:

```text
Thử transaction
    |
    +-- Thành công ----------------------> trả kết quả
    |
    +-- NOWAIT / lock timeout / deadlock
           |
           +-- Lỗi có thể thử lại và còn ngân sách?
                  |
                  +-- Có --> rollback, backoff ngắn, chạy lại toàn transaction
                  |
                  +-- Không --> trả lỗi tạm thời hoặc trạng thái bận
```

Khoảng backoff có thể dùng exponential backoff kèm jitter để giảm việc nhiều request thử lại cùng lúc. Cần giới hạn tổng thời gian và số lần thử để retry không biến thành vòng lặp vô hạn.

## 9. Chọn chính sách theo loại nghiệp vụ

| Nhu cầu | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Cập nhật cần hoàn tất, tranh chấp ngắn | Chờ mặc định với timeout hợp lý | Cho giao dịch trước hoàn tất rồi tiếp tục |
| API cần phản hồi ngay nếu bản ghi đang bận | NOWAIT | Không giữ request và connection trong lúc chờ |
| Tác vụ có thể đợi ngắn để hoàn tất | Lock timeout | Cân bằng giữa chờ và giới hạn độ trễ |
| Worker lấy công việc từ hàng đợi | SKIP LOCKED | Nhiều worker lấy các hàng khác nhau |
| Bảo vệ bất biến nghiệp vụ | Khóa/serialization phù hợp với retry | Không được bỏ qua hàng đang khóa nếu điều đó làm sai quyết định |

Không có một giá trị timeout phù hợp cho mọi câu lệnh. Thời hạn cần dựa trên SLA, thời gian giao dịch bình thường, độ trễ database, mức độ tranh chấp và ngân sách thời gian của request. Nên đo dữ liệu thực tế trước khi điều chỉnh.

## 10. Những điểm cần nhớ

- Chờ khóa xảy ra khi một yêu cầu khóa xung đột với khóa đang được giao dịch khác giữ trên cùng tài nguyên.
- Chờ mặc định cho phép câu lệnh tiếp tục khi khóa được giải phóng.
- `NOWAIT` trả lỗi ngay nếu không thể cấp khóa lập tức.
- Lock timeout giới hạn thời gian chờ khóa; đơn vị, phạm vi và hành vi rollback phụ thuộc hệ quản trị.
- Lock timeout khác statement timeout và request deadline.
- Deadlock là chu trình chờ; hệ quản trị có thể chọn nạn nhân trước khi timeout hết hạn.
- `SKIP LOCKED` bỏ qua hàng đang khóa, hữu ích cho worker queue nhưng tạo kết quả không đầy đủ.
- Sau lỗi khóa, ứng dụng phải xử lý transaction đúng trạng thái và chỉ retry toàn bộ giao dịch khi nghiệp vụ cho phép.
- Timeout theo session cần được quản lý cẩn thận khi connection được tái sử dụng qua pool.

Khi thiết kế một thao tác có thể tranh chấp khóa, hãy quyết định rõ liệu nghiệp vụ cần chờ, từ chối ngay hay bỏ qua tài nguyên đang bận. Sau đó chọn cú pháp và timeout theo đúng hệ quản trị, đặt giới hạn phù hợp với thời gian phản hồi của ứng dụng, và xử lý lỗi ở cấp transaction để dữ liệu luôn nhất quán.
