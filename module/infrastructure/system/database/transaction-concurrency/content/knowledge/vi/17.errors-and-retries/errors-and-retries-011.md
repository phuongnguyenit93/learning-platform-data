# Tránh bão thực thi lại khi nhiều yêu cầu tranh chấp cùng tài nguyên

Khi nhiều giao dịch cùng cập nhật một hàng, một tài khoản, một khóa duy nhất hoặc một tài nguyên nóng, một số giao dịch có thể bị chặn, deadlock hoặc thất bại do xung đột đồng thời. Ứng dụng thường thử lại những thao tác thất bại để hoàn thành công việc. Nhưng nếu mọi request đều retry ngay lập tức, chúng có thể quay lại cùng thời điểm, tiếp tục tranh chấp và tạo ra **retry storm** (bão thực thi lại).

Retry storm tạo thành vòng phản hồi tiêu cực: tải cao làm tăng xung đột; xung đột làm nhiều request thất bại; các request thất bại cùng retry làm tải tăng thêm; tải mới tiếp tục làm xung đột nhiều hơn. Database có thể nhận số lần thực thi lớn hơn nhiều so với số yêu cầu nghiệp vụ ban đầu, trong khi tỷ lệ commit thành công lại giảm.

Để tránh tình trạng này, cần phối hợp nhiều lớp: chỉ retry lỗi có thể phục hồi, retry toàn bộ đơn vị transaction phù hợp, dùng backoff có jitter, giới hạn số lần thử và tổng thời gian, kiểm soát concurrency, giảm tranh chấp trên tài nguyên nóng và bảo đảm thao tác có thể lặp an toàn. Retry là cơ chế phục hồi có giới hạn, không phải cách thay thế cho thiết kế transaction hoặc xử lý nguyên nhân gốc.

## 1. Retry storm hình thành như thế nào?

Giả sử một hàng `account` được nhiều request cập nhật số dư. Trong một khoảng thời gian ngắn, 100 request cùng đọc một phiên bản rồi thử cập nhật. Một số request thành công; các request còn lại gặp optimistic conflict, deadlock hoặc lock timeout.

Nếu tất cả request thất bại đều lập tức chạy lại, chúng tạo thêm các lượt đọc và ghi vào chính hàng đang nóng. Những request mới cũng tiếp tục đến trong lúc các request cũ retry. Hệ thống phải xử lý nhiều lần thử nhưng không tăng được lượng công việc hoàn tất tương ứng.

```text
Tải ban đầu cao
      |
      v
Nhiều transaction tranh chấp cùng hàng/khóa
      |
      v
Deadlock, lock timeout hoặc optimistic conflict
      |
      v
Các request retry gần như đồng thời
      |
      v
Số lượt truy vấn và ghi tăng đột biến
      |
      v
Tranh chấp tăng, latency tăng, thêm request timeout
      |
      +-------------------- quay lại retry --------------------+
```

Đây là một dạng **thundering herd**: nhiều client cùng thức dậy hoặc cùng phản ứng với một sự kiện rồi truy cập một tài nguyên trong cùng khoảng thời gian. Trong database, tài nguyên đó có thể là một hàng, một index key, một bảng, một connection pool hoặc chính database đang quá tải.

### 1.1. Ví dụ khuếch đại số lần thực thi

Giả sử 100 request ban đầu cùng gửi một thao tác cập nhật. Nếu 60 request thất bại và mỗi request retry tối đa ba lần, database có thể nhận thêm tối đa 180 lần thử cho cùng nhóm nghiệp vụ. Nếu các lần retry cũng tiếp tục thất bại, phần tải bổ sung không tạo ra kết quả hữu ích.

| Giai đoạn | Request nghiệp vụ còn cần hoàn tất | Lượt thử phát sinh |
|---|---:|---:|
| Ban đầu | 100 | 100 |
| Sau lần thử đầu | 60 thất bại | Tối đa 60 retry |
| Sau lần thử thứ hai | Giả sử 40 tiếp tục thất bại | Tối đa 40 retry |
| Sau lần thử thứ ba | Một phần vẫn thất bại | Tiếp tục tạo tải cho đến khi chạm giới hạn |

Đây chỉ là ví dụ minh họa. Mức khuếch đại thực tế phụ thuộc tỷ lệ xung đột, số lần retry, số tầng retry trong hệ thống và lượng request mới đến trong thời gian đó.

## 2. Không phải lỗi nào cũng nên retry

Retry chỉ hữu ích khi lỗi có khả năng biến mất nếu transaction được chạy lại sau một khoảng thời gian hoặc trên trạng thái dữ liệu mới. Retry một lỗi xác định sẽ thất bại lần nữa chỉ làm tăng tải và độ trễ.

Có thể chia lỗi thành các nhóm sau:

| Nhóm lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Xung đột đồng thời có thể phục hồi | Deadlock victim, serialization failure, optimistic version conflict | Rollback, đọc lại dữ liệu và retry toàn bộ transaction có giới hạn |
| Tài nguyên tạm thời bận | Lock timeout, giới hạn concurrency, pool tạm hết slot | Có thể retry sau backoff nếu còn deadline và lỗi thực sự tạm thời |
| Vi phạm quy tắc nghiệp vụ | Số dư không đủ, hết hàng, trạng thái không cho phép chuyển đổi | Trả kết quả nghiệp vụ; không retry vô điều kiện |
| Lỗi dữ liệu hoặc câu lệnh | Sai kiểu, vi phạm cú pháp, cột không tồn tại | Sửa ứng dụng hoặc dữ liệu; retry không giải quyết |
| Vi phạm constraint do giá trị xung đột | Unique key đã tồn tại, foreign key không hợp lệ | Xử lý theo nghiệp vụ; chỉ retry nếu thiết kế xác nhận đó là race có thể phục hồi |
| Lỗi kết nối hoặc kết quả commit không rõ | Mất kết nối khi gửi COMMIT hoặc trước khi nhận phản hồi | Xác định kết quả bằng idempotency key/trạng thái giao dịch trước khi gửi lại tác động |

Một unique violation có thể là lỗi nghiệp vụ thật, chẳng hạn người dùng đăng ký một email đã tồn tại. Trong một luồng “tạo bản ghi nếu chưa có”, cùng lỗi đó có thể phản ánh hai transaction chạy đua; ứng dụng cần đọc bản ghi đã tồn tại và quyết định theo nghiệp vụ. Không nên đưa mọi lỗi constraint vào danh sách retry chung.

### 2.1. Một số mã lỗi thường gặp

Mã lỗi phụ thuộc DBMS và driver. Ví dụ:

| DBMS | Lỗi | Mã thường gặp | Gợi ý xử lý |
|---|---|---|---|
| PostgreSQL | Serialization failure | SQLSTATE `40001` | Rollback và retry toàn bộ transaction với snapshot mới |
| PostgreSQL | Deadlock detected | SQLSTATE `40P01` | Transaction bị hủy; retry toàn bộ nếu thao tác an toàn |
| PostgreSQL | Lock not available | SQLSTATE `55P03` | Có thể là `NOWAIT`/lock timeout; chỉ retry nếu chính sách cho phép và còn deadline |
| MySQL InnoDB | Deadlock found | Error 1213 | Transaction bị rollback; retry toàn bộ transaction có giới hạn |
| MySQL InnoDB | Lock wait timeout exceeded | Error 1205 | Xem cấu hình và phạm vi rollback; không giả định mọi câu lệnh trước đó đã được rollback theo cùng cách |
| SQL Server | Deadlock victim | Error 1205 | Retry transaction victim sau backoff |
| SQL Server | Lock request timeout | Error 1222 | Kiểm tra blocker và timeout; retry có giới hạn nếu phù hợp |
| Oracle | Deadlock detected | ORA-00060 | Xử lý transaction và retry đơn vị công việc phù hợp |
| Oracle | Cannot serialize access | ORA-08177 | Retry transaction theo quy tắc Serializable |

Đây là các ví dụ phổ biến, không phải bảng phân loại đầy đủ cho mọi phiên bản và driver. Ứng dụng nên phân loại bằng mã lỗi có cấu trúc (SQLSTATE/vendor code), không dựa vào việc tìm một đoạn văn bản trong thông báo lỗi.

## 3. Retry đúng đơn vị: toàn bộ transaction

Khi một transaction bị deadlock victim hoặc serialization failure, các quyết định trước đó có thể dựa trên snapshot hoặc trạng thái đã không còn hợp lệ. Chạy lại riêng câu lệnh cuối thường không đúng.

Ví dụ:

```sql
BEGIN;

SELECT balance
FROM account
WHERE account_id = 42;

-- Ứng dụng tính số dư mới dựa trên giá trị vừa đọc.

UPDATE account
SET balance = :new_balance
WHERE account_id = 42;

COMMIT;
```

Nếu transaction thất bại do serialization conflict, ứng dụng cần rollback rồi bắt đầu transaction mới, đọc lại số dư và tính lại quyết định. Chỉ retry `UPDATE` với `new_balance` đã tính từ lần đọc cũ có thể ghi một kết quả không còn đúng với trạng thái mới.

```text
Một lần thử:
  BEGIN
    Đọc trạng thái
    Kiểm tra quy tắc nghiệp vụ
    Tính kết quả
    Ghi dữ liệu
  COMMIT

Nếu lỗi retryable:
  ROLLBACK transaction cũ
  Chờ backoff
  Bắt đầu transaction mới
  Đọc lại, kiểm tra lại, tính lại và ghi lại
```

Phải bảo đảm transaction cũ đã được rollback hoặc connection đã được đưa về trạng thái sạch trước khi bắt đầu lần thử tiếp theo. Không tái sử dụng một transaction đang ở trạng thái aborted.

### 3.1. Phân biệt retry transaction với retry request

Một request HTTP có thể chứa nhiều thao tác: ghi database, gửi email, gọi dịch vụ thanh toán và phát sự kiện. Không phải toàn bộ request đều có thể chạy lại tùy ý.

Thông thường, chỉ phần công việc database có thể được chạy lại trong transaction mới. Các tác động bên ngoài cần idempotency hoặc một giao thức riêng để tránh thực hiện hai lần. Nếu ứng dụng retry cả request mà không có bảo vệ, một email hoặc lệnh thanh toán có thể bị gửi lặp dù transaction database trước đó đã commit.

## 4. Exponential backoff: tạo khoảng nghỉ tăng dần

Backoff là khoảng chờ trước khi thử lại. Với exponential backoff, khoảng chờ tăng theo số lần thất bại để client không liên tục đập vào tài nguyên đang bận.

Một công thức capped exponential backoff:

\[
cap_n = \min(maxDelay, baseDelay \times 2^{n-1})
\]

Trong đó:

- `baseDelay` là khoảng chờ ban đầu.
- `n` là số thứ tự lần retry, bắt đầu từ 1.
- `maxDelay` giới hạn thời gian chờ tối đa.

Ví dụ với `baseDelay = 100 ms` và `maxDelay = 2 s`:

| Lần retry | Khoảng chờ tối đa trước khi thêm jitter |
|---:|---:|
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.600 ms |
| 6 trở đi | 2.000 ms |

Backoff giúp giảm tốc độ retry khi lỗi lặp lại. Tuy nhiên, nếu mọi client đều dùng cùng một lịch chờ xác định, chúng vẫn có thể retry cùng lúc sau 100 ms, rồi cùng lúc sau 200 ms. Vì vậy, backoff thường cần kết hợp jitter.

## 5. Jitter: phá đồng bộ giữa các client

Jitter thêm biến thiên vào khoảng chờ để các client không cùng thức dậy ở một thời điểm.

### 5.1. Full jitter

Với full jitter, chọn ngẫu nhiên một khoảng từ 0 đến giới hạn backoff hiện tại:

\[
delay_n \sim Uniform(0, cap_n)
\]

Ví dụ pseudocode:

```text
cap = min(max_delay, base_delay * 2^(attempt - 1))
delay = random(0, cap)
wait(delay)
```

Full jitter phân tán thời điểm retry khá tốt và thường là lựa chọn mặc định phù hợp khi có nhiều client tranh chấp cùng tài nguyên.

### 5.2. Equal jitter

Equal jitter giữ một phần thời gian chờ cố định và ngẫu nhiên phần còn lại:

```text
cap = min(max_delay, base_delay * 2^(attempt - 1))
delay = cap / 2 + random(0, cap / 2)
```

Cách này tránh trường hợp một số client retry gần như ngay lập tức, nhưng phân tán thời điểm hẹp hơn full jitter.

### 5.3. Decorrelated jitter

Decorrelated jitter tính thời gian chờ mới dựa trên thời gian chờ trước đó:

```text
delay = min(max_delay, random(base_delay, previous_delay * 3))
```

Cần khởi tạo `previous_delay` hợp lý và bảo đảm cận trên không nhỏ hơn cận dưới. Cách này tạo chuỗi delay ít đồng bộ hơn và có thể phù hợp với client tồn tại lâu.

### 5.4. Minh họa thời điểm retry

```text
Không jitter:
Client A: 100 ms ---- 200 ms -------- 400 ms
Client B: 100 ms ---- 200 ms -------- 400 ms
Client C: 100 ms ---- 200 ms -------- 400 ms
          ^ cùng retry tại các mốc ^

Có full jitter:
Client A:  35 ms -------- 170 ms ------------ 290 ms
Client B:  82 ms ----- 110 ms -------------------- 360 ms
Client C:  12 ms ------------ 245 ms -------- 315 ms
          các lượt thử được phân tán theo thời gian
```

Các con số chỉ minh họa. Bộ sinh số ngẫu nhiên nên đủ tốt để phân tán các client; không dùng cùng một seed cố định cho tất cả tiến trình nếu điều đó khiến lịch retry lặp lại giống nhau.

## 6. Giới hạn số lần thử và tổng thời gian retry

Retry vô hạn có thể khiến request chiếm tài nguyên lâu, giữ connection hoặc tiếp tục tạo tải sau khi người dùng đã bỏ chờ. Cần giới hạn cả số lần thử lẫn tổng thời gian.

Ví dụ chính sách:

- Tối đa 3 lần retry sau lần thử đầu tiên.
- Tổng thời gian retry không vượt quá deadline còn lại của request.
- Backoff tối đa 2 giây.
- Không bắt đầu một lần thử mới nếu thời gian còn lại không đủ cho một transaction hợp lý.
- Khi hết ngân sách, trả lỗi có thể thử lại hoặc trạng thái chưa xác định theo hợp đồng API.

Một thuật toán tổng quát:

```text
deadline = request_deadline
attempt = 0

while true:
    if now() >= deadline:
        return deadline_exceeded

    try:
        return run_one_transaction_attempt()
    catch error:
        if not is_retryable(error):
            throw error

        if attempt >= MAX_RETRIES:
            return retry_exhausted

        cap = min(MAX_DELAY, BASE_DELAY * 2^attempt)
        delay = random(0, cap)

        if now() + delay >= deadline:
            return deadline_exceeded

        rollback_if_needed()
        wait(delay)
        attempt += 1
```

Trong code thực tế, `run_one_transaction_attempt()` cần tự quản lý begin/commit/rollback và giải phóng connection. Không được ngủ trong khi vẫn giữ transaction hoặc lock. `deadline` phải dùng đồng hồ monotonic để đo thời lượng, tránh sai lệch khi đồng hồ hệ thống thay đổi.

## 7. Retry budget: giới hạn tổng tải do retry tạo ra

Giới hạn số lần retry trên từng request là cần thiết nhưng chưa đủ. Nếu có hàng triệu request đồng thời, mỗi request được retry ba lần vẫn có thể tạo ra lượng tải rất lớn.

**Retry budget** giới hạn tổng số lần thử lại mà một service hoặc nhóm client được phép tạo ra trong một khoảng thời gian. Ví dụ, cho phép tối đa 10 retry trên mỗi 100 request ban đầu trong một cửa sổ quan sát, hoặc giới hạn tỷ lệ retry so với request mới.

Các cách triển khai thường gặp:

- Token bucket cấp token cho retry; retry chỉ được thực hiện khi còn token.
- Giới hạn số retry đồng thời trên mỗi service hoặc partition.
- Khi tỷ lệ lỗi vượt ngưỡng, giảm hoặc tạm dừng retry không thiết yếu.
- Dành ngân sách retry riêng cho thao tác quan trọng và có deadline ngắn.
- Theo dõi tỷ lệ retry/request gốc để phát hiện khuếch đại.

Retry budget nên được phối hợp giữa các tầng. Nếu API gateway, service nghiệp vụ, repository và driver đều tự retry ba lần, một request có thể tạo ra nhiều lần thực thi ở tầng database hơn dự kiến.

## 8. Tránh retry lồng nhau và nhân số lần thử

Một lỗi thiết kế phổ biến là nhiều lớp cùng sở hữu chính sách retry:

```text
HTTP client: retry tối đa 3 lần
  Service: retry transaction tối đa 3 lần
    Repository: retry câu lệnh tối đa 3 lần
      Driver: retry kết nối hoặc thao tác nội bộ
```

Nếu mỗi lớp thử độc lập, số lần thực thi có thể nhân lên. Ba lớp, mỗi lớp ba lần thử, có thể tạo tối đa 27 lần gọi xuống lớp dưới cho một thao tác logic, chưa kể retry nội bộ của driver.

Nên xác định một tầng sở hữu retry cho từng loại lỗi. Ví dụ, tầng transaction biết toàn bộ đơn vị công việc và có thể retry an toàn sau deadlock/serialization failure; tầng HTTP chỉ xử lý lỗi kết nối hoặc lỗi dịch vụ theo hợp đồng; driver xử lý những lỗi transport mà nó có thể xác định chắc chắn.

Các lớp khác nên truyền lỗi có cấu trúc lên tầng sở hữu retry thay vì tự retry lại cùng thao tác. Nếu buộc phải có retry ở nhiều tầng, hãy tính ngân sách chung và giới hạn tổng số lần thử end-to-end.

## 9. Deadline và timeout phải phối hợp với nhau

Timeout của câu lệnh, lock wait timeout, connection timeout và deadline của request là các giới hạn khác nhau. Nếu không phối hợp, một request có thể tiếp tục retry sau khi client đã hết thời gian chờ.

Ví dụ:

| Giới hạn | Mục đích |
|---|---|
| Connection timeout | Giới hạn thời gian lấy hoặc thiết lập kết nối |
| Lock timeout | Giới hạn thời gian chờ một khóa |
| Statement timeout | Giới hạn thời gian chạy câu lệnh |
| Transaction timeout (nếu DBMS hỗ trợ) | Giới hạn vòng đời transaction |
| Request deadline | Giới hạn tổng thời gian người gọi chờ kết quả |
| Retry budget/deadline | Giới hạn thời gian và số lần thử lại |

Các giới hạn cần nhất quán. Nếu request còn 300 ms nhưng lock timeout của mỗi lần thử là 5 giây, lần thử có thể vượt xa deadline. Ứng dụng cần truyền thời gian còn lại xuống tầng database và đặt timeout phù hợp.

Khi hết deadline, cần dừng tạo công việc mới, hủy hoặc rollback transaction đang chạy theo cách an toàn và giải phóng connection. Hủy request ở tầng HTTP không tự động bảo đảm câu lệnh database đã dừng; cần xác nhận cơ chế cancellation của driver và DBMS.

## 10. Không ngủ trong transaction hoặc giữ connection khi backoff

Backoff phải xảy ra sau khi transaction thất bại đã được rollback và connection được trả về pool nếu không còn cần thiết.

Sai lầm:

```text
BEGIN
UPDATE ...
Nhận lỗi xung đột
SLEEP 1 giây
Retry câu lệnh trong cùng transaction
```

Transaction có thể đang ở trạng thái aborted hoặc vẫn giữ lock/tài nguyên. Ngủ trong transaction làm tăng thời gian giữ connection, snapshot và lock, khiến tranh chấp nghiêm trọng hơn.

Luồng đúng ở mức khái quát:

```text
BEGIN
  Thực hiện toàn bộ đơn vị công việc
COMMIT

Nếu lỗi retryable:
  ROLLBACK
  Trả connection về pool
  Chờ backoff bên ngoài transaction
  Lấy connection sạch
  Bắt đầu transaction mới
```

Nếu driver tự động quản lý transaction, hãy hiểu rõ trạng thái connection sau lỗi. Một số DBMS đánh dấu toàn bộ transaction là aborted; một số lỗi chỉ rollback statement hoặc savepoint tùy chế độ. Chính sách retry phải phù hợp với semantics thực tế.

## 11. Giới hạn concurrency trước khi request chạm database

Backoff làm giảm tốc độ retry sau lỗi. **Admission control** và giới hạn concurrency giảm số request được phép cùng lúc đi vào vùng tranh chấp.

Ví dụ, nếu database chỉ xử lý hiệu quả 50 transaction cập nhật trên một nhóm tài nguyên nóng, việc cho 2.000 request đồng thời tranh chấp cùng hàng không làm throughput tăng 40 lần. Nó chỉ làm hàng đợi, lock wait và timeout dài hơn.

Có thể dùng:

- Semaphore hoặc bulkhead để giới hạn số transaction đồng thời trên một nhóm tài nguyên.
- Queue có giới hạn kích thước để hấp thụ burst ngắn.
- Rate limit theo tenant, account hoặc resource key.
- Giới hạn số worker cập nhật cùng một partition.
- Load shedding: từ chối sớm request không thiết yếu khi hệ thống đã quá tải.
- Connection pool có kích thước phù hợp, tránh tạo quá nhiều connection đồng thời.

Giới hạn concurrency cần đặt theo năng lực thực tế của database và mức tranh chấp. Một connection pool quá lớn có thể làm database phải lập lịch quá nhiều transaction cùng lúc; pool quá nhỏ có thể làm request chờ ở tầng ứng dụng. Cần đo queue wait, DB active sessions, lock wait và throughput để điều chỉnh.

### 11.1. Giới hạn theo khóa tài nguyên

Nếu tranh chấp tập trung vào `account_id = 42`, giới hạn concurrency toàn service có thể không đủ. Có thể tuần tự hóa các thao tác cùng khóa logic, trong khi vẫn cho phép các tài khoản khác chạy song song.

```text
Partition/queue theo account_id:

account 42:  request A -> request B -> request C
account 77:  request D || request E
account 91:  request F || request G
```

Đây là một dạng per-key serialization. Nó giảm số transaction cùng tranh chấp một hàng nóng, nhưng cần bảo đảm mọi đường cập nhật tài nguyên đó đi qua cùng cơ chế điều phối. Nếu có nhiều instance ứng dụng, semaphore trong bộ nhớ của một instance không đủ để phối hợp toàn hệ thống; cần queue/partition dùng chung hoặc cơ chế khóa phân tán phù hợp.

## 12. Giảm xung đột ở chính mô hình dữ liệu

Retry storm thường là dấu hiệu một tài nguyên đang có mức tranh chấp cao. Ngoài việc điều chỉnh retry, hãy xem có thể giảm số transaction cùng phải ghi vào một điểm nóng hay không.

### 12.1. Dùng atomic update thay cho read-modify-write

Thay vì đọc giá trị ở ứng dụng, tính rồi ghi lại, hãy để database thực hiện phép cập nhật nguyên tử:

```sql
-- Read-modify-write ở ứng dụng dễ tạo khoảng tranh chấp:
SELECT quantity FROM inventory WHERE product_id = 42;
-- Ứng dụng tính quantity - 1 rồi UPDATE.

-- Cập nhật nguyên tử có điều kiện:
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity > 0;
```

Ứng dụng kiểm tra số hàng được cập nhật. Nếu là 0, sản phẩm không tồn tại hoặc không còn hàng theo quy tắc. Cách này rút ngắn khoảng giữa đọc và ghi, đồng thời tránh retry do ứng dụng dùng một giá trị cũ. Các transaction vẫn phải tuần tự hóa cập nhật cùng hàng, nhưng mỗi lần giữ lock thường ngắn hơn.

### 12.2. Thứ tự khóa nhất quán

Nếu một transaction cần cập nhật nhiều tài khoản, hãy khóa theo thứ tự ID tăng dần ở mọi luồng xử lý. Quy tắc này giảm deadlock do các transaction lấy cùng tập khóa theo thứ tự ngược nhau.

### 12.3. Giảm kích thước transaction

Chỉ giữ transaction trong phần công việc cần nguyên tử. Không gọi HTTP, gửi email, chờ người dùng hoặc thực hiện xử lý tệp lâu trong lúc giữ khóa database. Transaction ngắn giúp giải phóng tài nguyên sớm và giảm số request bị kéo vào chuỗi chờ.

### 12.4. Chia tải hoặc phân vùng tài nguyên nóng

Một counter toàn cục có thể trở thành hot row. Nếu nghiệp vụ cho phép, có thể dùng nhiều counter theo shard rồi tổng hợp khi đọc, hoặc partition queue theo tenant/resource. Tuy nhiên, nếu cần giới hạn chính xác một tổng toàn cục, chia nhỏ counter có thể làm mất điểm đồng bộ cần thiết; phải thiết kế cơ chế bảo đảm bất biến trước khi phân mảnh.

### 12.5. Chọn optimistic hay pessimistic concurrency phù hợp

- Optimistic concurrency phù hợp khi xung đột hiếm; khi xung đột thường xuyên, nhiều lần đọc và retry có thể đắt hơn khóa trực tiếp.
- Pessimistic locking phù hợp khi xung đột thường xuyên và cần giữ quyền cập nhật; cần giới hạn thời gian giữ lock và kiểm soát thứ tự khóa.
- Một hàng guard/counter có thể biến bất biến nhiều hàng thành cập nhật nguyên tử trên tài nguyên chung; nó tạo điểm nóng nhưng cũng tạo nơi phân xử rõ ràng.
- `SERIALIZABLE` bảo vệ các phụ thuộc phức tạp nhưng có thể tạo serialization failure; ứng dụng cần retry toàn bộ transaction có giới hạn.

Không có chiến lược concurrency nào miễn phí. Hãy đo workload thực tế và chọn chiến lược theo tần suất xung đột, phạm vi bất biến, latency và yêu cầu nhất quán.

## 13. Idempotency: retry không làm lặp tác động nghiệp vụ

Một request có thể đã commit thành công nhưng response bị mất trên đường về client. Client không biết kết quả và gửi lại. Đây là trường hợp **ambiguous outcome**: không thể chỉ nhìn lỗi kết nối để kết luận transaction chưa commit.

Để xử lý, ứng dụng có thể gắn một idempotency key ổn định cho thao tác nghiệp vụ. Database lưu kết quả theo key và dùng unique constraint để chỉ một lần xử lý được ghi nhận.

Ví dụ schema:

```sql
CREATE TABLE request_result (
    idempotency_key text PRIMARY KEY,
    status          text NOT NULL,
    response_body   jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);
```

Trong transaction, ứng dụng tạo hoặc chiếm idempotency key, thực hiện thay đổi nghiệp vụ và lưu kết quả. Nếu cùng key được gửi lại, ứng dụng đọc kết quả đã ghi nhận thay vì thực hiện tác động lần nữa.

Thiết kế thực tế cần xử lý trường hợp hai request cùng key đến đồng thời, trạng thái đang xử lý, thời hạn lưu key và kết quả khi transaction đầu thất bại. Unique constraint trên key là điểm đồng bộ hữu ích; ứng dụng phải xử lý xung đột theo giao thức đã chọn.

Idempotency đặc biệt quan trọng khi retry request có tác động ngoài database như thanh toán, gửi email hoặc phát sự kiện. Transaction database không thể tự rollback tác động đã được một hệ thống bên ngoài chấp nhận.

### 13.1. Transactional outbox

Nếu một transaction cần cập nhật database và phát sự kiện, có thể ghi sự kiện vào bảng outbox trong cùng transaction. Một worker đọc outbox và gửi sự kiện đến hệ thống khác. Worker có thể gửi lại khi mất phản hồi, nên consumer vẫn cần idempotency hoặc inbox/deduplication.

```text
Transaction nghiệp vụ:
  UPDATE account
  INSERT INTO outbox(event_id, payload)
  COMMIT

Worker:
  Đọc sự kiện chưa gửi
  Gửi tới broker/service
  Đánh dấu đã gửi
```

Outbox bảo đảm thay đổi nghiệp vụ và ý định phát sự kiện được commit cùng nhau. Nó không tự tạo exactly-once delivery qua mạng; gửi lặp vẫn có thể xảy ra và cần consumer xử lý an toàn.

## 14. Circuit breaker và load shedding

Khi database hoặc một tài nguyên nóng liên tục quá tải, tiếp tục retry mọi request có thể kéo dài sự cố. Circuit breaker là một cơ chế ở tầng ứng dụng để tạm ngừng gọi một dependency sau khi lỗi vượt ngưỡng.

Các trạng thái phổ biến:

- **Closed:** cho phép request đi qua và theo dõi lỗi.
- **Open:** từ chối nhanh hoặc trả lỗi tạm thời trong một khoảng thời gian.
- **Half-open:** cho một số ít request thử để xác định dependency đã phục hồi chưa.

Circuit breaker phù hợp khi lỗi có tính chất dependency-wide hoặc một nhóm tài nguyên đang quá tải. Nó không nên được dùng thay cho xử lý xung đột thông thường trên một hàng đơn lẻ; nếu mở breaker quá rộng, các request không liên quan cũng có thể bị từ chối.

Load shedding chủ động từ chối request không thiết yếu khi hệ thống vượt ngưỡng tải. Từ chối sớm thường tốt hơn nhận request rồi để chúng chờ hết deadline, chiếm connection và retry nhiều lần.

## 15. Một chính sách retry tổng thể

Một chính sách retry cho transaction tranh chấp nên xác định rõ:

1. Những mã lỗi nào được retry.
2. Transaction nào là đơn vị retry.
3. Số lần retry tối đa và tổng deadline.
4. Loại backoff và jitter.
5. Retry budget toàn service hoặc partition.
6. Giới hạn concurrency và queue size.
7. Cách xử lý idempotency và kết quả commit không rõ.
8. Cách ghi log, metric và trace để quan sát.

Ví dụ cấu hình minh họa:

```yaml
transactionRetry:
  maxRetries: 3
  baseDelay: 50ms
  maxDelay: 1s
  jitter: full
  requestDeadline: 3s
  retryableErrors:
    - postgres: "40001"  # serialization_failure
    - postgres: "40P01"  # deadlock_detected
  retryBudget:
    maxRetryRatio: 0.10
    window: 1m
  concurrency:
    maxInFlightPerHotKey: 1
```

Đây là cấu hình minh họa, không phải giá trị mặc định cho mọi hệ thống. `maxInFlightPerHotKey` cần cơ chế phối hợp đúng phạm vi; giới hạn trong một process không bảo vệ được tài nguyên khi có nhiều instance. `retryBudget` cũng cần định nghĩa rõ tỷ lệ tính trên request gốc hay tổng số attempt.

## 16. Pseudocode triển khai retry có kiểm soát

Ví dụ dưới đây mô tả một tầng transaction duy nhất sở hữu retry:

```text
function executeBusinessOperation(command, deadline):
    attempt = 0

    while attempt <= MAX_RETRIES:
        if deadline.remaining() <= MIN_ATTEMPT_BUDGET:
            return deadlineExceeded()

        try:
            return runInFreshTransaction(() => {
                current = loadRequiredState(command)
                validateBusinessRules(current, command)
                result = applyChanges(current, command)
                persistIdempotencyResult(command.key, result)
                return result
            })

        catch error:
            if not isRetryableConcurrencyError(error):
                throw error

            if attempt == MAX_RETRIES:
                return retryExhausted(error)

            if not retryBudget.tryAcquire():
                return overloaded(error)

            cap = min(MAX_DELAY, BASE_DELAY * 2^attempt)
            delay = random(0, cap)

            if delay + MIN_ATTEMPT_BUDGET >= deadline.remaining():
                return deadlineExceeded()

            waitOutsideTransaction(delay)
            attempt += 1

    return retryExhausted()
```

`runInFreshTransaction` phải bảo đảm transaction thất bại được rollback và connection không còn ở trạng thái lỗi trước khi trả quyền điều khiển cho vòng retry. Nếu kết quả commit không rõ do mất kết nối, tầng này cần tra cứu idempotency key hoặc trạng thái thao tác trước khi quyết định gửi lại.

## 17. Những sai lầm thường tạo retry storm

- **Retry ngay lập tức:** các client đồng bộ lại và tiếp tục tranh chấp cùng tài nguyên.
- **Retry vô hạn:** request cũ tiếp tục tiêu thụ tài nguyên sau khi không còn khả năng hoàn thành trong deadline.
- **Retry mọi lỗi:** lỗi nghiệp vụ, constraint hoặc cú pháp vẫn thất bại và tạo tải thừa.
- **Retry câu lệnh cuối thay vì transaction:** quyết định dựa trên dữ liệu cũ có thể không còn đúng.
- **Ngủ trong transaction:** giữ connection, snapshot hoặc lock trong thời gian backoff.
- **Retry lồng nhau ở nhiều tầng:** số lần gọi database bị nhân lên ngoài dự kiến.
- **Không có jitter:** client cùng retry tại các mốc thời gian giống nhau.
- **Không có retry budget:** từng request có giới hạn nhưng tổng tải retry vẫn có thể vượt năng lực database.
- **Không có concurrency limit:** quá nhiều transaction cùng tranh chấp một hot row.
- **Không có idempotency:** request đã commit nhưng mất response có thể thực hiện tác động lần nữa.
- **Không quan sát attempt count:** hệ thống chỉ thấy latency cao mà không biết phần lớn tải đến từ retry.

## 18. Giám sát và chẩn đoán retry storm

Throughput tổng thể có thể che giấu việc hệ thống đang thực hiện rất nhiều lần thử thất bại. Cần theo dõi cả request gốc và attempt.

| Chỉ số | Cách hiểu | Dấu hiệu cảnh báo |
|---|---|---|
| Retry attempts / original requests | Số attempt trên mỗi request nghiệp vụ | Tăng nhanh trong khi request success không tăng |
| Retry success rate | Tỷ lệ attempt retry cuối cùng thành công | Thấp kéo dài; retry chỉ tạo thêm tải |
| Deadlock count | Số deadlock trong một khoảng thời gian | Tăng đồng thời với request rate hoặc thay đổi query |
| Serialization failure rate | Tỷ lệ transaction bị abort do Serializable | Tăng ở một loại transaction hoặc hot key |
| Lock wait p95/p99 | Phân phối thời gian chờ khóa | p99 tăng mạnh, nhiều request chạm deadline |
| Transaction duration | Thời gian transaction giữ tài nguyên | Transaction dài làm blocker tồn tại lâu |
| DB active sessions / pool wait | Mức sử dụng database và connection pool | Pool cạn, queue wait tăng, DB active sessions quá cao |
| Hot-key distribution | Tần suất request theo account/resource key | Một vài key chiếm phần lớn lưu lượng |
| Retry budget exhaustion | Số request bị từ chối retry vì hết ngân sách | Tăng liên tục, cần kiểm tra overload và lỗi gốc |
| Idempotency conflict/replay | Số request gửi lại cùng key | Tăng đột biến có thể chỉ ra timeout hoặc response loss |

Nên gắn correlation ID, idempotency key và attempt number vào log/trace. Không ghi payload nhạy cảm hoặc toàn bộ câu lệnh có dữ liệu riêng tư nếu không cần thiết. Có thể phân nhóm theo loại lỗi, transaction name và resource key đã được băm để tìm điểm nóng.

Khi thấy retry tăng, kiểm tra đồng thời:

- Transaction hoặc câu lệnh nào gây deadlock/timeout.
- Hàng, index key hoặc predicate nào bị tranh chấp.
- Có thay đổi execution plan hoặc index gần thời điểm bắt đầu sự cố không.
- Có request burst, deploy hoặc retry policy mới không.
- Connection pool và DB active sessions có vượt mức vận hành bình thường không.
- Các tầng gateway/service/repository/driver có đang retry lồng nhau không.

## 19. Kịch bản thực tế: nhiều request cập nhật cùng một tài khoản

Giả sử một tài khoản nhận 200 giao dịch cập nhật trong một giây. Mọi request đều ghi vào cùng hàng `account`. Nếu ứng dụng đọc số dư, tính số dư mới rồi ghi lại, các request có thể tạo nhiều xung đột. Nếu mỗi xung đột retry ngay, số attempt tăng lên nhưng hàng vẫn chỉ có thể được cập nhật theo thứ tự do database điều phối.

Một thiết kế tốt hơn có thể gồm:

1. Dùng câu `UPDATE` nguyên tử hoặc một transaction ngắn để cập nhật số dư theo điều kiện.
2. Phân loại lỗi: thiếu số dư là kết quả nghiệp vụ; deadlock/serialization conflict mới thuộc nhóm có thể retry.
3. Giới hạn số transaction cùng xử lý một `account_id` bằng queue/partition hoặc semaphore phân tán phù hợp.
4. Retry toàn bộ transaction sau rollback với full jitter và deadline.
5. Dùng idempotency key cho mỗi giao dịch nghiệp vụ để request gửi lại không trừ/cộng số dư hai lần.
6. Theo dõi lock wait, retry ratio và độ trễ theo account key để phát hiện tài khoản nóng.

Nếu một tài khoản thực sự nhận nhiều cập nhật hơn khả năng tuần tự hóa của một hàng, cần xem lại mô hình ghi: queue theo account, ledger append-only rồi tổng hợp, hoặc partition dữ liệu theo nghiệp vụ nếu vẫn giữ được quy tắc số dư. Chỉ tăng số lần retry sẽ không làm một hàng có thể xử lý nhiều cập nhật đồng thời hơn.

## 20. Quy trình xử lý khi retry storm đang diễn ra

Khi hệ thống bắt đầu có retry tăng đột biến, ưu tiên khôi phục ổn định và giảm tải khuếch đại:

1. **Xác định nguồn lỗi.** Phân nhóm deadlock, serialization failure, lock timeout, connection error và lỗi nghiệp vụ.
2. **Đo mức khuếch đại.** So sánh request gốc với tổng attempt và tỷ lệ retry thành công.
3. **Giảm retry không cần thiết.** Tắt retry cho lỗi không phục hồi; áp dụng giới hạn attempt, deadline và retry budget.
4. **Thêm backoff có jitter.** Tránh cho tất cả client retry cùng thời điểm.
5. **Giới hạn concurrency.** Giảm số request đồng thời đi vào hot key hoặc database đang quá tải.
6. **Rút ngắn transaction và giải phóng tài nguyên.** Xử lý blocker kéo dài, trả connection và không ngủ trong transaction.
7. **Giảm nguyên nhân tranh chấp.** Xem thứ tự khóa, atomic update, index, hàng guard và phân vùng queue.
8. **Bảo vệ tác động lặp.** Kiểm tra idempotency và kết quả commit không rõ trước khi gửi lại thao tác.
9. **Theo dõi phục hồi.** Chỉ tăng concurrency hoặc retry budget dần khi lock wait, error rate và DB load ổn định.

Không nên tăng retry limit chỉ vì tỷ lệ lỗi cao. Nếu lỗi do database đã quá tải hoặc một tài nguyên nóng bị tuần tự hóa, tăng số lần thử thường làm sự cố nặng hơn.

## 21. Những điểm cần ghi nhớ

- Retry storm xảy ra khi nhiều request thất bại rồi retry gần đồng thời, làm tăng tải và xung đột trên tài nguyên đang nóng.
- Chỉ retry lỗi có thể phục hồi; lỗi nghiệp vụ, cú pháp và constraint không phù hợp không nên retry vô điều kiện.
- Deadlock victim và serialization failure thường cần rollback rồi chạy lại toàn bộ transaction trên trạng thái mới.
- Exponential backoff giảm nhịp retry; jitter phân tán thời điểm retry để tránh thundering herd.
- Giới hạn số lần thử, deadline và retry budget để kiểm soát tổng tải retry.
- Tránh retry lồng nhau ở nhiều tầng và không ngủ khi transaction hoặc connection vẫn giữ tài nguyên không cần thiết.
- Admission control, bulkhead, queue có giới hạn và per-key concurrency giúp giảm số transaction cùng tranh chấp.
- Atomic update, thứ tự khóa nhất quán, transaction ngắn và mô hình dữ liệu phù hợp giúp giảm xung đột gốc.
- Idempotency key và transactional outbox giúp xử lý request lặp và kết quả commit không rõ; retry không tự bảo đảm exactly-once.
- Theo dõi retry ratio, retry success, lock wait, deadlock, transaction duration, hot key và retry budget exhaustion.

Một chính sách retry tốt giúp giao dịch phục hồi sau xung đột mà không làm database quá tải hơn. Hãy xem retry như một phần của kiểm soát tải và tính đúng đắn: giới hạn rõ ràng, phân tán thời điểm thử lại, chỉ chạy lại đơn vị công việc an toàn và giảm số request cùng tranh chấp một tài nguyên.
