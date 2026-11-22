# Phối hợp thời gian chờ, hủy truy vấn, thử lại và giới hạn số yêu cầu

## Mục tiêu bài học

Một truy vấn cơ sở dữ liệu có thể chậm vì phải chờ lấy connection, chờ khóa, đọc dữ liệu, ghi WAL hoặc xử lý một kế hoạch tốn nhiều tài nguyên. Nếu ứng dụng chỉ đặt một timeout lớn ở HTTP client, request có thể hết hạn trong khi truy vấn vẫn chạy ở database. Nếu ứng dụng tự động retry mọi lỗi, tải có thể tăng đúng lúc database đang quá tải. Nếu connection pool cho phép quá nhiều request đồng thời, hàng đợi và số phiên hoạt động có thể vượt khả năng phục vụ của hệ thống.

Trong chương **Kết nối và mạng** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn phối hợp deadline, timeout, hủy truy vấn, retry và giới hạn số yêu cầu để kiểm soát tải từ ứng dụng tới database. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, các chính sách kết nối cần được đánh giá cùng thời gian thực thi SQL, lock wait, throughput, độ trễ và khả năng phục hồi khi có lỗi.

Sau bài học, bạn có thể:

- Phân biệt deadline của request với timeout chờ connection, timeout câu lệnh, timeout khóa và timeout mạng.
- Thiết kế thứ tự timeout nhất quán giữa client, connection pool và database.
- Hiểu cách hủy câu lệnh, trạng thái transaction sau khi bị hủy và cách trả connection về pool an toàn.
- Phân loại lỗi có thể retry và lỗi không nên retry tự động.
- Thiết kế retry có giới hạn, backoff, jitter và idempotency.
- Giới hạn concurrency bằng connection pool, semaphore, queue có giới hạn và backpressure.
- Theo dõi pool saturation, lock wait, query cancellation, retry storm và độ trễ p95/p99.
- Kiểm chứng chính sách dưới tải bình thường, tải đột biến và các tình huống lỗi.

## 1. Một request có nhiều khoảng thời gian chờ

Một request từ ứng dụng tới database thường đi qua nhiều giai đoạn. Mỗi giai đoạn có thể tiêu thụ thời gian và cần một giới hạn phù hợp.

```text
Client gửi request
      |
      v
Chờ vào hàng đợi ứng dụng / admission control
      |
      v
Chờ lấy connection từ pool
      |
      v
Gửi câu lệnh tới database
      |
      +--> Chờ khóa (lock wait)
      |
      +--> Đọc/ghi và thực thi kế hoạch SQL
      |
      +--> Chờ WAL, I/O hoặc tài nguyên khác
      |
      v
Nhận kết quả và trả connection về pool
      |
      v
Serialize response và gửi về client
```

Nếu chỉ đo tổng thời gian request, khó biết phần nào gây chậm. Cần đo riêng thời gian chờ pool, thời gian database, thời gian chờ khóa, thời gian mạng và thời gian xử lý ở ứng dụng.

### 1.1. Các loại timeout

| Timeout | Giới hạn điều gì? | Thường được thực thi ở đâu? |
|---|---|---|
| Request deadline | Tổng thời gian request được phép tồn tại | API gateway, framework hoặc application |
| Queue/admission timeout | Thời gian chờ được nhận vào xử lý | Application queue hoặc semaphore |
| Pool acquisition timeout | Thời gian chờ lấy connection rảnh | Connection pool |
| Connect timeout | Thời gian thiết lập kết nối TCP/TLS/database | Driver hoặc network client |
| Query/statement timeout | Thời gian câu lệnh được phép chạy | Driver và/hoặc database |
| Lock timeout | Thời gian chờ lấy khóa | Database |
| Socket/read timeout | Thời gian chờ dữ liệu mạng hoặc phản hồi | Driver/network client |
| Idle-in-transaction timeout | Thời gian session ở trạng thái idle nhưng vẫn giữ transaction mở | Database |

Các timeout này không thay thế cho nhau. Ví dụ, `connect_timeout` không giới hạn thời gian truy vấn; `lock_timeout` chỉ giới hạn thời gian chờ khóa, không giới hạn toàn bộ câu lệnh; pool acquisition timeout có thể xảy ra trước khi database nhận bất kỳ SQL nào.

### 1.2. Deadline khác timeout từng chặng

**Deadline** là thời điểm tuyệt đối mà request phải hoàn tất. Mỗi tầng sử dụng phần thời gian còn lại của deadline để quyết định có tiếp tục xử lý hay không.

Giả sử API có deadline 2,5 giây. Nếu ứng dụng đã dùng 400 ms để xác thực và chờ pool, database không còn toàn bộ 2,5 giây; nó chỉ còn phần ngân sách còn lại trừ đi thời gian cần để hủy, rollback và trả response.

Nếu mỗi tầng tự đặt timeout 2 giây mà không truyền deadline, request có thể mất nhiều giây hơn dự kiến do các tầng chờ nối tiếp hoặc retry nhiều lần. Vì vậy, nên truyền deadline hoặc thời gian còn lại qua các lời gọi nội bộ, thay vì khởi động lại một timeout đầy đủ ở mỗi tầng.

## 2. Xây dựng thứ tự timeout nhất quán

Các giới hạn nên tạo thành một hệ thống phân cấp. Tầng trong cần dừng đủ sớm để tầng ngoài nhận được lỗi, dọn transaction và trả phản hồi trước khi deadline tổng hết hạn.

Một thứ tự thường dùng:

```text
Request deadline
  > thời gian chờ pool + thời gian query + thời gian cleanup/response

Client query timeout
  > server statement_timeout một khoảng nhỏ để nhận lỗi và cleanup

Server statement_timeout
  > lock_timeout
```

Đây là quan hệ thiết kế, không phải công thức cứng cho mọi hệ thống. Timeout thực tế phải dựa trên SLA, phân bố latency và loại truy vấn.

### 2.1. Ví dụ ngân sách thời gian

Giả sử endpoint có deadline 2.500 ms:

| Giai đoạn | Ngân sách minh họa |
|---|---:|
| Chờ pool | Tối đa 200 ms |
| Database statement | Tối đa 1.700 ms |
| Hủy/rollback và trả connection | 200 ms |
| Xử lý kết quả và response | 300 ms |
| Dự phòng | 100 ms |
| Tổng | 2.500 ms |

Trong ví dụ, server `statement_timeout` có thể thấp hơn giới hạn query ở client một khoảng đủ để driver nhận lỗi, rollback và trả response. `lock_timeout` có thể là 250 ms nếu nghiệp vụ không chấp nhận chờ khóa lâu. Các con số chỉ minh họa; truy vấn báo cáo có thể cần ngân sách dài hơn API tương tác.

### 2.2. Timeout phải xét thời gian còn lại

Giả sử request đã tiêu thụ 1,2 giây trước khi gọi database và deadline tổng là 2,5 giây. Ứng dụng không nên cấp cho database timeout 2 giây nữa. Thời gian còn lại chỉ là 1,3 giây, trong đó cần chừa thời gian cleanup và gửi response.

Pseudocode:

```text
remaining = request.deadline - now()

if remaining <= cleanup_margin:
    return deadline_exceeded

pool_timeout = min(configured_pool_timeout,
                   remaining - query_and_cleanup_budget)

connection = pool.acquire(timeout = pool_timeout)

remaining = request.deadline - now()
query_timeout = min(configured_query_timeout,
                    remaining - cleanup_margin)

if query_timeout <= 0:
    release connection
    return deadline_exceeded

execute query with query_timeout
```

Tính thời gian còn lại ngay trước từng chặng. Không dùng một giá trị timeout được tính ở đầu request rồi tái sử dụng sau khi request đã chờ lâu.

### 2.3. Lock timeout ngắn hơn statement timeout

Một truy vấn có thể chờ khóa lâu trước khi bắt đầu xử lý dữ liệu. Nếu thời gian chờ khóa vượt mức nghiệp vụ cho phép, có thể dừng sớm để tránh giữ connection trong hàng đợi.

Trong PostgreSQL:

```sql
BEGIN;
SET LOCAL lock_timeout = '250ms';
SET LOCAL statement_timeout = '1700ms';

SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE;

COMMIT;
```

`lock_timeout` giới hạn mỗi lần chờ lấy khóa. `statement_timeout` giới hạn thời gian câu lệnh. Nếu `statement_timeout` ngắn hơn `lock_timeout`, statement timeout sẽ hết trước và lock timeout không còn nhiều ý nghĩa. Trong PostgreSQL, nên đặt `lock_timeout` thấp hơn `statement_timeout` nếu mục tiêu là giới hạn riêng thời gian chờ khóa.

`SET LOCAL` chỉ có hiệu lực trong transaction hiện tại. Cách này hữu ích khi dùng connection pool vì cấu hình được khôi phục khi transaction kết thúc. Nếu dùng autocommit, cần hiểu rằng một lệnh `SET LOCAL` riêng lẻ không tự áp dụng cho statement kế tiếp; hãy đặt trong cùng transaction với câu lệnh cần giới hạn.

## 3. Timeout ở phía database và phía client

### 3.1. PostgreSQL statement_timeout

`statement_timeout` hủy câu lệnh vượt quá thời gian được cấu hình. Có thể đặt theo session, role, database hoặc transaction tùy nhu cầu quản trị.

Ví dụ cấu hình theo transaction:

```sql
BEGIN;
SET LOCAL statement_timeout = '2s';

SELECT count(*)
FROM orders
WHERE created_at >= now() - interval '30 days';

COMMIT;
```

Với API có SLA ngắn, có thể dùng timeout riêng cho nhóm truy vấn tương tác. Truy vấn batch hoặc báo cáo dài nên có chính sách riêng, tránh đặt một timeout toàn cục quá ngắn làm hỏng công việc hợp lệ.

### 3.2. idle_in_transaction_session_timeout

Một session có thể mở transaction rồi không chạy SQL nhưng vẫn giữ transaction và snapshot. Điều này có thể giữ khóa, cản trở vacuum và làm tăng bloat.

PostgreSQL có `idle_in_transaction_session_timeout` để chấm dứt session idle trong transaction quá thời gian cho phép. Nó bảo vệ hệ thống khỏi transaction bị bỏ quên, nhưng khi hết hạn, kết nối bị đóng và ứng dụng phải xử lý lỗi. Đây không phải timeout cho một câu SQL đang chạy.

### 3.3. Client query timeout

Driver có thể cung cấp timeout cho câu lệnh hoặc socket. Ví dụ JDBC có `Statement.setQueryTimeout(...)` tính theo giây; một số driver cung cấp thêm socket timeout hoặc network timeout ở mức connection.

Client timeout có thể kích hoạt cơ chế gửi yêu cầu cancel tới server, nhưng hành vi chi tiết phụ thuộc driver và giao thức. Một socket/read timeout chỉ cho biết client không nhận được dữ liệu trong thời gian quy định; nó không luôn bảo đảm câu lệnh ở server đã dừng.

Vì vậy, với truy vấn quan trọng nên có cả giới hạn phía server lẫn client:

- Server timeout bảo vệ database ngay cả khi client bị mất kết nối hoặc không gửi được cancel.
- Client deadline bảo vệ request và connection pool khỏi chờ vô hạn.
- Driver phải có cách xử lý trạng thái giao thức sau khi timeout hoặc cancel.
- Ứng dụng phải rollback hoặc loại bỏ connection nếu không xác định được trạng thái transaction.

### 3.4. Connect timeout và pool acquisition timeout

`connect_timeout` giới hạn thời gian mở kết nối mới. Pool acquisition timeout giới hạn thời gian chờ một connection đang được pool quản lý trở nên rảnh.

Hai trường hợp khác nhau:

- **Không kết nối được:** DNS, TCP, TLS, firewall, database restart hoặc giới hạn kết nối có thể làm connect timeout.
- **Pool cạn:** các connection hiện có đều bận hoặc bị giữ lâu; request phải chờ connection rảnh dù database có thể vẫn hoạt động.

Nếu pool acquisition timeout thường xuyên xảy ra, tăng pool size ngay có thể làm database nhận nhiều truy vấn đồng thời hơn và trở nên quá tải. Trước tiên cần xác định connection bị giữ bởi query dài, transaction mở lâu, lock wait hay ứng dụng không trả connection về pool.

## 4. Hủy truy vấn đúng cách

Hủy truy vấn (query cancellation) là yêu cầu dừng một câu lệnh đang chạy. Cần phân biệt hủy statement với đóng session và với việc client chỉ ngừng chờ.

### 4.1. Statement cancel và session terminate

Trong PostgreSQL:

- `pg_cancel_backend(pid)` yêu cầu hủy câu lệnh hiện tại của backend, nếu có quyền phù hợp.
- `pg_terminate_backend(pid)` chấm dứt session backend; các transaction đang mở của session bị rollback khi session kết thúc.

Ví dụ:

```sql
-- Yêu cầu hủy câu lệnh đang chạy
SELECT pg_cancel_backend(12345);

-- Chỉ dùng khi cần kết thúc session sau khi đánh giá tác động
SELECT pg_terminate_backend(12345);
```

Hủy câu lệnh thường là lựa chọn ít tác động hơn terminate session. Không tự động terminate mọi backend vượt ngưỡng query age; hãy xác định chủ sở hữu, transaction, khóa đang giữ và tác động rollback trước.

### 4.2. Cancel có thể đến muộn

Client và server giao tiếp qua mạng. Khi client hết deadline, yêu cầu cancel cần được gửi và xử lý. Có thể xảy ra race:

- Câu lệnh hoàn tất ngay trước khi cancel tới.
- Cancel tới server nhưng backend chưa xử lý tại đúng thời điểm đó.
- Kết nối mạng đã hỏng nên cancel không tới được server.
- Client đã timeout nhưng backend vẫn tiếp tục chạy cho tới khi nhận cancel hoặc server timeout.

Do đó, cancellation là cơ chế phối hợp, không phải bảo đảm tức thời rằng tài nguyên đã được giải phóng đúng thời điểm client timeout. Server-side `statement_timeout` là lớp bảo vệ bổ sung.

### 4.3. Hủy khi client ngắt kết nối

Khi người dùng đóng trang hoặc gateway ngắt request, ứng dụng nên truyền tín hiệu cancellation tới tác vụ database nếu framework và driver hỗ trợ. Nếu bỏ qua tín hiệu, truy vấn có thể tiếp tục tiêu thụ CPU, I/O và connection dù không còn ai nhận kết quả.

Luồng xử lý nên:

1. Nhận tín hiệu request bị hủy hoặc deadline hết hạn.
2. Yêu cầu driver cancel statement đang chạy.
3. Chờ trong một khoảng cleanup có giới hạn để driver xử lý phản hồi.
4. Rollback transaction nếu đang ở trong transaction lỗi hoặc chưa hoàn tất.
5. Chỉ trả connection về pool khi protocol và transaction state an toàn.
6. Nếu không thể xác nhận connection sạch, loại bỏ connection khỏi pool theo cơ chế của pool/driver.

Không trả một connection có transaction đang ở trạng thái aborted hoặc giao thức chưa đồng bộ về pool để request khác sử dụng.

### 4.4. Trạng thái transaction sau cancel trong PostgreSQL

Nếu một câu lệnh bị hủy trong explicit transaction, transaction thường chuyển sang trạng thái lỗi. Các câu lệnh tiếp theo sẽ báo lỗi cho tới khi ứng dụng thực hiện `ROLLBACK` hoặc rollback về savepoint phù hợp.

Ví dụ:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

-- Một statement sau đó bị statement_timeout hoặc cancel.

ROLLBACK;
```

Nếu ứng dụng bỏ qua rollback và trả connection về pool, request tiếp theo có thể nhận connection trong trạng thái transaction aborted. Hãy dùng transaction manager của framework và kiểm tra hành vi reset/rollback của pool.

## 5. Phân loại lỗi trước khi retry

Retry chỉ phù hợp khi lỗi có khả năng tạm thời, thao tác có thể thực hiện lại an toàn và request còn đủ deadline. Retry mọi lỗi sẽ che lỗi nghiệp vụ, nhân tải hoặc thực hiện tác dụng phụ nhiều lần.

### 5.1. Nhóm lỗi thường có thể retry có điều kiện

| Nhóm lỗi | Ví dụ PostgreSQL | Hướng xử lý |
|---|---|---|
| Serialization failure | SQLSTATE `40001` | Retry toàn bộ transaction với snapshot mới, số lần giới hạn |
| Deadlock victim | SQLSTATE `40P01` | Rollback và retry toàn transaction có backoff; đồng thời sửa thứ tự khóa |
| Từ chối lấy khóa có chủ đích | SQLSTATE `55P03` như `NOWAIT` hoặc lock timeout | Chỉ retry nếu nghiệp vụ chấp nhận chờ và còn deadline; tránh lặp ngay |
| Lỗi kết nối tạm thời | SQLSTATE class `08` hoặc lỗi driver tương ứng | Có thể mở connection mới và retry thao tác idempotent; xác định trạng thái commit nếu không rõ |
| Failover/restart tạm thời | Lỗi kết nối hoặc server shutdown | Chờ endpoint ổn định, dùng retry budget và idempotency |

Các ví dụ SQLSTATE giúp phân loại trong PostgreSQL; driver hoặc proxy có thể biểu diễn lỗi bằng exception khác. Cần phân loại theo mã SQLSTATE và nguyên nhân, không chỉ dựa vào chuỗi thông báo.

### 5.2. Nhóm lỗi không nên retry tự động một cách mù quáng

- Lỗi cú pháp hoặc tên bảng/cột không tồn tại.
- Vi phạm `CHECK`, `FOREIGN KEY` hoặc quy tắc nghiệp vụ.
- Vi phạm unique constraint (`23505`) khi đó là xung đột dữ liệu thực sự.
- Sai kiểu dữ liệu hoặc dữ liệu đầu vào không hợp lệ.
- Query bị hủy do `statement_timeout` vì kế hoạch hoặc dữ liệu quá nặng; lặp lại cùng truy vấn thường gây cùng vấn đề.
- Request đã hết deadline tổng.
- Lỗi quyền hoặc cấu hình cố định.

Một số trường hợp unique violation có thể là race khi tạo tài nguyên có khóa idempotency; khi đó cần đọc lại kết quả theo khóa nghiệp vụ và xác định request trước đã hoàn tất hay chưa. Không biến mọi `23505` thành retry.

### 5.3. Timeout không đồng nghĩa lỗi tạm thời

Timeout có thể do:

- Lock contention tạm thời.
- Truy vấn thiếu index hoặc kế hoạch xấu.
- Database quá tải kéo dài.
- Pool quá nhỏ hoặc connection bị rò rỉ.
- Storage chậm hoặc hết dung lượng.
- Network partition.

Nếu nguyên nhân là truy vấn vốn vượt SLA, retry chỉ lặp lại công việc tốn tài nguyên. Nếu nguyên nhân là pool cạn, retry có thể làm hàng đợi dài hơn. Trước khi retry, hãy phân loại timeout theo giai đoạn: chờ pool, connect, lock, statement hay network.

## 6. Retry có giới hạn và backoff

### 6.1. Exponential backoff

Retry ngay lập tức khiến nhiều request lỗi cùng lúc tiếp tục gửi tải vào database. Exponential backoff tăng thời gian chờ giữa các lần thử:

\[
delay_n = min(maxDelay, baseDelay \times 2^n)
\]

Ví dụ với `baseDelay = 50 ms`, thời gian chờ cơ sở có thể tăng 50, 100, 200, 400 ms cho các lần thử tiếp theo, tới khi chạm giới hạn. Đây là ví dụ đơn giản; hệ thống thực tế nên thêm jitter.

### 6.2. Jitter để tránh retry đồng loạt

Nếu hàng nghìn request cùng retry sau đúng 200 ms, chúng có thể tạo một đợt tải mới. Jitter thêm độ ngẫu nhiên để phân tán thời điểm retry.

Một công thức full jitter phổ biến:

```text
cap = min(max_delay, base_delay * 2^attempt)
delay = random(0, cap)
```

Có thể dùng equal jitter hoặc decorrelated jitter tùy thư viện. Điều quan trọng là có giới hạn tối đa, có deadline tổng và không để retry tiếp tục sau khi request đã hết thời gian.

### 6.3. Giới hạn số lần thử và retry budget

Chính sách retry nên xác định:

- Số lần thử tối đa (bao gồm lần đầu hay chỉ số lần retry, phải thống nhất cách đếm).
- Tổng thời gian tối đa dành cho retry.
- Các mã lỗi được phép retry.
- Backoff và jitter.
- Điều kiện hủy khi deadline hết hạn.
- Giới hạn tỷ lệ retry trên tổng request để tránh retry storm.

Ví dụ, một request có thể có tối đa hai lần retry và chỉ retry khi còn đủ thời gian. Không nên áp dụng ba lần retry ở gateway, ba lần ở service và ba lần ở repository vì một request có thể nhân thành nhiều chục lần gọi database.

### 6.4. Retry toàn transaction khi cần

Với lỗi serialization hoặc deadlock, chỉ chạy lại câu lệnh cuối thường không đủ vì các quyết định trước đó dựa trên snapshot hoặc trạng thái đã thay đổi. Cần rollback và chạy lại toàn bộ transaction logic từ đầu.

```text
for attempt in 0..max_attempts:
    begin transaction
    try:
        đọc dữ liệu cần thiết
        kiểm tra quy tắc nghiệp vụ
        ghi các thay đổi
        commit
        return success
    catch retryable_transaction_error:
        rollback
        if attempts_exhausted or deadline_expired:
            return failure
        wait(backoff_with_jitter)
```

Không giữ transaction mở trong thời gian backoff. Rollback trước, trả connection về pool khi sạch, chờ bên ngoài transaction rồi mới bắt đầu lần thử mới.

### 6.5. Tránh retry lồng nhau

Nếu driver, repository, service và gateway đều có retry riêng, tổng số lần thực thi có thể tăng theo cấp số nhân. Hãy chọn một tầng sở hữu chính sách retry cho một thao tác nghiệp vụ, hoặc phân chia rõ retry kết nối với retry transaction mà không chồng lặp.

Mỗi tầng phải tôn trọng deadline còn lại và retry budget của request. Ghi metric `attempt` để quan sát số lần thực thi thực tế.

## 7. Idempotency và kết quả commit không rõ ràng

Một tình huống nguy hiểm là client gửi transaction, database commit thành công nhưng phản hồi bị mất trên mạng. Client chỉ thấy timeout và không biết transaction đã commit hay chưa. Nếu gửi lại thao tác tạo đơn hoặc trừ tiền, nghiệp vụ có thể được thực hiện hai lần.

Đây là **ambiguous outcome** (kết quả không xác định từ phía client). Retry an toàn cần một cơ chế nhận diện thao tác đã được xử lý.

### 7.1. Idempotency key

Client gửi một khóa duy nhất cho mỗi thao tác nghiệp vụ, ví dụ `request_id`. Database lưu khóa này cùng kết quả trong transaction. Nếu cùng request được gửi lại, ứng dụng đọc kết quả đã lưu thay vì thực hiện nghiệp vụ lần nữa.

Ví dụ cấu trúc:

```sql
CREATE TABLE idempotency_records (
    idempotency_key text PRIMARY KEY,
    operation_type text NOT NULL,
    request_hash text NOT NULL,
    response_payload jsonb,
    completed_at timestamptz
);
```

Luồng xử lý khái quát:

1. Nhận idempotency key và hash của payload nghiệp vụ.
2. Trong transaction, tạo record theo key bằng unique constraint.
3. Nếu key mới, thực hiện thay đổi nghiệp vụ và lưu kết quả.
4. Commit thay đổi nghiệp vụ và idempotency record trong cùng transaction.
5. Nếu key đã tồn tại, xác minh request hash giống nhau và trả kết quả đã lưu.
6. Nếu cùng key nhưng payload khác, từ chối vì client đang tái sử dụng khóa sai mục đích.

Mã SQL cụ thể phụ thuộc cách xử lý cạnh tranh giữa hai request đồng thời cùng key. Unique constraint là điểm phối hợp; transaction thua cuộc cần đọc lại record đã commit hoặc retry theo luồng có kiểm soát.

### 7.2. Idempotency không có nghĩa mọi câu SQL đều tự an toàn

`UPDATE counter SET value = value + 1` không idempotent: chạy hai lần làm giá trị tăng hai lần. `SET status = 'PAID'` có thể idempotent về giá trị cuối nhưng các trigger, audit event hoặc gửi thông báo đi kèm vẫn có thể xảy ra hai lần.

Hãy xác định toàn bộ tác dụng phụ của nghiệp vụ, bao gồm email, thanh toán ngoài, message publish và audit. Transactional outbox có thể giúp ghi sự kiện cùng transaction database; consumer vẫn cần xử lý lặp bằng idempotency.

### 7.3. Phân biệt retry trước và sau commit

- Nếu lỗi xảy ra trước khi transaction bắt đầu hoặc trước khi câu lệnh được gửi, thao tác thường có thể thử lại sau khi xác nhận điều kiện.
- Nếu server trả lỗi transaction rõ ràng và transaction đã rollback, có thể retry theo phân loại lỗi.
- Nếu mất kết nối trong lúc commit hoặc sau khi gửi commit nhưng chưa nhận phản hồi, kết quả có thể không rõ. Cần tra cứu bằng idempotency key hoặc mã giao dịch nghiệp vụ trước khi quyết định gửi lại.

Không suy luận rằng “client timeout nghĩa là database chưa commit”.

## 8. Giới hạn số yêu cầu đồng thời

Timeout và retry kiểm soát thời gian một request chiếm tài nguyên. Concurrency limit kiểm soát số request được phép cùng hoạt động. Hai cơ chế cần phối hợp: timeout mà không giới hạn concurrency có thể vẫn để quá nhiều request cùng chờ; giới hạn concurrency mà không có deadline có thể tạo hàng đợi vô hạn.

### 8.1. Connection pool

Connection pool tái sử dụng kết nối database để tránh chi phí thiết lập kết nối cho từng request. Pool thường có:

- Maximum pool size: số connection tối đa của pool.
- Minimum/idle connections: số kết nối giữ sẵn.
- Acquisition timeout: thời gian chờ connection rảnh.
- Idle timeout và max lifetime: thời gian giữ connection không hoạt động hoặc tuổi tối đa.
- Validation/health check: kiểm tra connection trước khi dùng theo chính sách driver.

Pool size không nên được chọn chỉ theo số request của ứng dụng. Tổng số connection từ tất cả replica, worker, batch job, migration và công cụ quản trị phải nằm trong khả năng database.

### 8.2. Tính tổng connection trên toàn hệ thống

Ví dụ có 8 application instance, mỗi instance pool tối đa 20 connection:

\[
8 \times 20 = 160\ connections
\]

Con số này chưa tính worker, scheduler, dashboard, migration và phiên quản trị. Nếu database chỉ có ngân sách 180 connection cho ứng dụng, cấu hình trên gần như không còn reserve cho các thành phần khác.

Hãy lập ngân sách:

```text
Database connection budget
  = application pools
  + background workers
  + batch/reporting clients
  + monitoring/admin reserve
  + replication/maintenance connections (nếu áp dụng)
```

Trong PostgreSQL, `max_connections` là giới hạn backend connection, không phải mục tiêu để mọi application pool cộng lại bằng đúng giá trị đó. Mỗi backend có chi phí bộ nhớ và tài nguyên; tăng `max_connections` có thể làm tăng áp lực RAM và scheduling.

### 8.3. Pool quá lớn và pool quá nhỏ

| Cấu hình | Hệ quả có thể xảy ra |
|---|---|
| Pool quá lớn | Quá nhiều truy vấn đồng thời, cạnh tranh CPU/I/O/lock, tăng memory và context switching |
| Pool quá nhỏ | Request chờ pool dù database còn khả năng xử lý; throughput bị giới hạn ở tầng ứng dụng |
| Pool queue không giới hạn | Request tích tụ, thời gian chờ tăng và có thể hết deadline trước khi chạy SQL |
| Không có acquisition timeout | Request giữ tài nguyên ứng dụng trong khi chờ connection quá lâu |
| Không trả connection đúng cách | Pool cạn do leak hoặc transaction mở lâu |

Pool tối ưu là pool tạo concurrency vừa với năng lực phục vụ của database và workload, có hàng đợi hữu hạn cùng timeout rõ ràng.

### 8.4. Semaphore và giới hạn theo nhóm truy vấn

Một ứng dụng có thể dùng semaphore để giới hạn số truy vấn cùng loại. Ví dụ:

- API tương tác: concurrency cao hơn nhưng query timeout ngắn.
- Báo cáo nặng: concurrency thấp để tránh chiếm hết I/O và bộ nhớ.
- Batch import: chạy theo lô có kích thước và tốc độ kiểm soát.
- Tác vụ quản trị: có ngân sách riêng và không dùng hết connection dành cho ứng dụng.

Đây là mô hình bulkhead: một nhóm workload không được phép làm cạn toàn bộ tài nguyên của nhóm khác. Cần theo dõi cả queue time và utilization; giới hạn quá thấp có thể tạo bottleneck giả ở ứng dụng.

## 9. Backpressure, load shedding và circuit breaker

### 9.1. Backpressure

Backpressure là cơ chế giảm tốc độ nhận công việc khi tầng phía sau không thể xử lý kịp. Thay vì để request tích tụ vô hạn, hệ thống có thể:

- Giới hạn kích thước queue.
- Giảm tốc độ consumer.
- Giảm batch size hoặc số worker.
- Trì hoãn công việc không khẩn cấp.
- Từ chối sớm request vượt khả năng phục vụ.

Hàng đợi cần có giới hạn cả về số phần tử và thời gian chờ. Một request đã gần hết deadline không nên tiếp tục nằm trong queue chỉ để sau đó timeout.

### 9.2. Load shedding

Khi hệ thống quá tải, load shedding chủ động từ chối một phần yêu cầu để bảo vệ phần còn lại. API có thể trả `429 Too Many Requests` khi giới hạn theo client/tenant bị vượt hoặc `503 Service Unavailable` khi dịch vụ tạm thời không đủ năng lực. Có thể kèm `Retry-After` nếu hệ thống biết thời điểm hợp lý để thử lại.

Không yêu cầu client retry ngay lập tức sau `429` hoặc `503`. Client cần tôn trọng hướng dẫn retry, backoff và deadline; server cũng cần giới hạn retry từ các client để tránh vòng lặp quá tải.

### 9.3. Circuit breaker

Circuit breaker theo dõi tỷ lệ lỗi hoặc timeout của một dependency. Khi vượt ngưỡng, nó tạm ngừng gửi request mới trong một khoảng thời gian, sau đó cho một số request thử để xác định dependency đã phục hồi chưa.

Circuit breaker hữu ích khi một dịch vụ phụ thuộc bị lỗi kéo dài. Với database, cần thận trọng: một circuit breaker quá nhạy có thể mở khi có một đợt spike ngắn, làm gián đoạn request hợp lệ. Cần phân biệt lỗi nghiệp vụ, timeout query riêng lẻ, lỗi kết nối và database thực sự không khả dụng.

Circuit breaker không thay thế pool limit, timeout hay retry budget. Khi breaker đóng lại, phải tránh cho toàn bộ request dồn vào cùng lúc; giới hạn concurrency và jitter vẫn cần thiết.

## 10. Ví dụ phối hợp timeout, cancel và retry trong ứng dụng Java

Ví dụ dưới đây mô tả cấu trúc xử lý JDBC ở mức khái quát. Cách gọi transaction, timeout và cancel cụ thể phụ thuộc driver, framework và pool.

```java
Connection connection = null;
boolean transactionStarted = false;

try {
    long remainingMs = deadline.remainingMillis();
    if (remainingMs <= cleanupMarginMs) {
        throw new DeadlineExceededException();
    }

    connection = dataSource.getConnection(); // pool có acquisition timeout
    connection.setAutoCommit(false);
    transactionStarted = true;

    try (Statement setup = connection.createStatement()) {
        setup.execute("SET LOCAL lock_timeout = '250ms'");
        setup.execute("SET LOCAL statement_timeout = '1500ms'");
    }

    try (PreparedStatement statement = connection.prepareStatement(
            "UPDATE inventory " +
            "SET available = available - 1 " +
            "WHERE sku = ? AND available >= 1")) {
        statement.setString(1, sku);
        statement.setQueryTimeout(2); // giây; cần đối chiếu server timeout

        int updated = statement.executeUpdate();
        if (updated == 0) {
            throw new InsufficientInventoryException();
        }
    }

    connection.commit();
    transactionStarted = false;
} catch (SQLException error) {
    if (connection != null && transactionStarted) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            // Đánh dấu connection không an toàn để pool loại bỏ.
        }
    }
    throw error;
} finally {
    if (connection != null) {
        connection.close(); // trả về pool nếu connection còn hợp lệ
    }
}
```

Đoạn code minh họa các bước chính, chưa phải một triển khai hoàn chỉnh cho mọi driver:

- Cần cấu hình acquisition timeout ở pool và kiểm tra deadline trước khi lấy connection.
- `Statement.setQueryTimeout` tính theo giây trong JDBC; không nên đặt nhỏ hơn server timeout nếu muốn server trả lỗi trước và có thời gian cleanup.
- `SET LOCAL` phải chạy trong cùng transaction với câu SQL cần giới hạn.
- Nếu rollback thất bại hoặc driver không xác định được trạng thái protocol, cần đánh dấu connection broken/evict theo API của pool thay vì trả lại connection như bình thường.
- Khi lỗi xảy ra trong hoặc sau `commit()`, không thể luôn biết transaction đã commit hay chưa. Với thao tác nghiệp vụ cần retry, phải có idempotency key và bước tra cứu kết quả.
- Không retry ngay trong `catch` này nếu chưa phân loại SQLSTATE, tính idempotent và deadline còn lại.

## 11. Quan sát timeout, retry và concurrency

Một chính sách tốt cần có metric để biết nó đang bảo vệ hệ thống hay tạo thêm hàng đợi.

### 11.1. Chỉ số ở tầng ứng dụng

- Request count, throughput và tỷ lệ lỗi theo endpoint/tenant.
- Deadline exceeded và client cancellation count.
- Thời gian chờ admission queue và connection pool.
- Pool active, idle, pending, acquisition timeout và connection leak.
- Query duration p50/p95/p99 theo query fingerprint.
- Số lần retry theo nguyên nhân, attempt count và tổng thời gian backoff.
- Số lần circuit breaker mở/đóng và số request bị load shed.
- Số connection bị loại khỏi pool do lỗi hoặc protocol không sạch.

### 11.2. Chỉ số ở tầng PostgreSQL

- `pg_stat_activity`: trạng thái backend, query age, `wait_event_type`, `wait_event` và transaction age.
- `pg_blocking_pids(pid)`: các backend đang chặn một backend khác.
- `pg_stat_database`: transaction commit/rollback, deadlock và temp usage theo database.
- Log statement timeout, lock timeout, deadlock và connection failure.
- `EXPLAIN (ANALYZE, BUFFERS)` cho truy vấn chậm đã được chọn để phân tích.

Không chạy `EXPLAIN ANALYZE` trên mọi truy vấn production vì nó thực thi câu lệnh và có thể làm tăng tải. Dùng query fingerprint, sampling và môi trường kiểm thử để phân tích phù hợp.

### 11.3. Tránh metric gây hiểu nhầm

- Query age không phải lock wait duration.
- Số retry cao có thể làm request cuối cùng thành công nhưng vẫn che một database đang quá tải.
- Pool active cao chưa chắc xấu nếu throughput và latency ổn định; pool pending tăng cùng acquisition latency mới là dấu hiệu đáng chú ý.
- Tổng thời gian chờ cộng dồn của nhiều request có thể lớn hơn thời gian thực tế trên đồng hồ.
- Một lỗi `57014` trong PostgreSQL cho biết query bị cancel, nhưng cần log context để phân biệt statement timeout, user cancel hoặc nguyên nhân khác.

Không ghi password, token, dữ liệu cá nhân hoặc payload nhạy cảm trong log truy vấn. Dùng query fingerprint và correlation ID để liên kết trace ứng dụng với database mà không làm lộ dữ liệu.

## 12. Quy trình thiết kế và kiểm chứng chính sách

**Bước 1 — Xác định SLA và deadline.** Ghi rõ tổng thời gian request, mức p95/p99, tỷ lệ lỗi chấp nhận được và thời gian cleanup.

**Bước 2 — Đo từng chặng.** Thu thập queue time, pool acquisition, connect, query, lock wait, network và response time để xác định phần chiếm ngân sách.

**Bước 3 — Đặt timeout theo tầng.** Thiết lập request deadline, pool acquisition timeout, connect timeout, server statement timeout, lock timeout và driver timeout sao cho tầng trong dừng đủ sớm.

**Bước 4 — Thiết kế cancellation.** Bảo đảm request bị hủy sẽ gửi cancel nếu có thể, rollback transaction và chỉ trả connection về pool khi trạng thái an toàn.

**Bước 5 — Phân loại lỗi.** Xác định SQLSTATE hoặc loại exception, phân biệt lỗi tạm thời, lỗi nghiệp vụ, timeout do truy vấn nặng và kết quả commit không rõ.

**Bước 6 — Thiết kế retry.** Chọn lỗi retry được, giới hạn attempt và tổng thời gian, dùng exponential backoff với jitter, rollback trước khi retry và không giữ connection trong lúc chờ.

**Bước 7 — Bảo vệ tác dụng phụ.** Dùng idempotency key, unique constraint, transactional outbox hoặc cơ chế tra cứu kết quả để xử lý retry sau lỗi mạng/commit không rõ.

**Bước 8 — Đặt concurrency limit.** Tính tổng pool size trên mọi instance, dành reserve cho tác vụ nền/quản trị, giới hạn queue và tách workload nặng khỏi API tương tác.

**Bước 9 — Thêm backpressure.** Giới hạn queue, giảm tốc độ consumer, load shed hoặc circuit breaker theo điều kiện rõ ràng; tránh retry đồng loạt.

**Bước 10 — Thử tải và sự cố.** Kiểm thử pool cạn, lock contention, query chậm, database restart, network interruption, cancel race, deadlock, lỗi commit không rõ và retry storm.

**Bước 11 — Đo lại và điều chỉnh.** So sánh p50/p95/p99, throughput, pool pending, lock wait, cancellation, retry, CPU, I/O và tỷ lệ lỗi. Thay đổi từng chính sách có kiểm soát.

## 13. Những nhầm lẫn thường gặp

- **“HTTP timeout hết thì database query tự dừng.”** Không phải lúc nào client timeout cũng gửi được cancel; server cần statement timeout và ứng dụng cần quản lý cancellation.
- **“Socket timeout giống query timeout.”** Socket timeout giới hạn chờ dữ liệu mạng; query timeout giới hạn câu lệnh theo cơ chế driver hoặc server.
- **“Lock timeout giới hạn toàn bộ truy vấn.”** Nó chỉ giới hạn thời gian chờ lấy khóa; statement timeout mới giới hạn câu lệnh.
- **“Cancel query đồng nghĩa đóng connection.”** Cancel thường dừng statement; terminate session đóng backend và có thể rollback transaction.
- **“Query bị cancel thì transaction tự sẵn sàng dùng tiếp.”** Explicit transaction trong PostgreSQL thường ở trạng thái lỗi cho tới khi rollback.
- **“Retry mọi timeout sẽ tăng khả năng thành công.”** Retry truy vấn vốn quá nặng hoặc database quá tải có thể làm tình hình xấu hơn.
- **“Có thể retry câu lệnh cuối sau serialization failure.”** Thường phải rollback và chạy lại toàn bộ transaction với snapshot mới.
- **“Client timeout nghĩa là transaction chưa commit.”** Phản hồi có thể bị mất sau khi commit; kết quả có thể không rõ.
- **“Retry ba lần ở mỗi tầng là an toàn.”** Retry lồng nhau có thể nhân số lần gọi theo cấp số nhân.
- **“Tăng pool size luôn tăng throughput.”** Concurrency quá cao có thể làm database bão hòa CPU, I/O, memory hoặc lock.
- **“Tăng max_connections là cách xử lý pool cạn.”** Cần xác định pool leak, query dài, contention và năng lực phục vụ trước.
- **“Queue càng lớn càng hấp thụ được tải.”** Queue vô hạn chỉ biến quá tải thành latency lớn và timeout hàng loạt.
- **“Idempotency chỉ cần kiểm tra ở ứng dụng.”** Cần cơ chế bền vững như unique key và lưu kết quả trong transaction để xử lý request đồng thời.

## 14. Checklist phối hợp timeout, retry và concurrency

- [ ] Đã xác định deadline tổng của request và ngân sách từng chặng.
- [ ] Pool acquisition timeout và connect timeout nằm trong deadline còn lại.
- [ ] Server `statement_timeout` thấp hơn client deadline đủ để cleanup.
- [ ] `lock_timeout` được đặt phù hợp và ngắn hơn `statement_timeout` khi cần giới hạn lock wait riêng.
- [ ] Có cơ chế cancel khi request hết hạn hoặc client ngắt kết nối.
- [ ] Transaction bị cancel được rollback trước khi connection quay lại pool.
- [ ] Connection có protocol/transaction state không rõ được loại khỏi pool.
- [ ] Lỗi được phân loại bằng SQLSTATE hoặc nguyên nhân cụ thể trước khi retry.
- [ ] Retry có giới hạn attempt, tổng thời gian, backoff, jitter và retry budget.
- [ ] Serialization failure/deadlock được xử lý bằng retry toàn transaction khi phù hợp.
- [ ] Thao tác có tác dụng phụ có idempotency key hoặc cơ chế deduplication bền vững.
- [ ] Có xử lý riêng cho kết quả commit không rõ sau lỗi mạng.
- [ ] Tổng connection từ mọi instance và worker nằm trong ngân sách database.
- [ ] Queue có giới hạn; có backpressure hoặc load shedding khi quá tải.
- [ ] Có metric cho pool pending, timeout, cancel, retry, lock wait, p95/p99 và throughput.
- [ ] Đã thử các tình huống quá tải, mất mạng, failover, deadlock và retry storm.

## Kết luận

Timeout, cancellation, retry và concurrency limit là các lớp bảo vệ liên quan chặt chẽ. Deadline giới hạn tổng thời gian request; pool timeout, connect timeout, lock timeout và statement timeout giới hạn từng chặng. Khi client hủy truy vấn, ứng dụng phải rollback transaction và chỉ trả connection về pool khi trạng thái an toàn. Retry cần dựa trên phân loại lỗi, có giới hạn, backoff, jitter và idempotency để tránh thực hiện nghiệp vụ lặp hoặc tạo retry storm.

Connection pool, semaphore và queue hữu hạn giúp kiểm soát số yêu cầu đồng thời. Backpressure và load shedding bảo vệ database khi năng lực phục vụ đã đạt giới hạn. Hãy đo riêng thời gian chờ pool, lock, query và network; theo dõi retry, cancellation, throughput cùng p95/p99; sau đó kiểm chứng chính sách bằng tải đại diện và các tình huống lỗi. Một thiết kế tốt phải giữ request trong deadline, bảo vệ tài nguyên database và duy trì đúng đắn giao dịch ngay cả khi kết nối bị gián đoạn.
