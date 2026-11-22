# Khóa kéo dài, deadlock và giao dịch bị treo

Trong PostgreSQL, một truy vấn có thể chạy chậm vì đang chờ khóa, một phiên có thể giữ khóa lâu dù không còn chạy câu lệnh, hoặc nhiều giao dịch có thể chờ lẫn nhau đến mức tạo thành deadlock. Các tình huống này nhìn bề ngoài khá giống nhau: ứng dụng phản hồi chậm, câu lệnh đứng lâu hoặc thao tác cập nhật không hoàn tất. Tuy nhiên, cách chẩn đoán và xử lý của từng trường hợp khác nhau.

Bài học này trình bày cách phân biệt khóa kéo dài, giao dịch bị treo và deadlock; cách tìm phiên đang chặn; cách xử lý có kiểm soát; và cách thiết kế ứng dụng để giảm khả năng sự cố tái diễn.

## 1. Phân biệt các tình huống thường gặp

Trước khi can thiệp, cần xác định phiên PostgreSQL đang ở trạng thái nào.

| Tình huống | Dấu hiệu chính | Ý nghĩa |
|---|---|---|
| Truy vấn chờ khóa (lock wait) | **wait_event_type = 'Lock'**; **pg_blocking_pids(pid)** trả về PID chặn | Truy vấn muốn lấy một khóa nhưng phiên khác đang giữ khóa xung đột |
| Giao dịch chạy lâu | **xact_start** đã cũ; phiên có thể đang **active** | Giao dịch chưa kết thúc, có thể tiếp tục giữ khóa và snapshot |
| Giao dịch nhàn rỗi nhưng chưa kết thúc | **state = 'idle in transaction'** | Ứng dụng đã gửi xong câu lệnh nhưng chưa **COMMIT** hoặc **ROLLBACK** |
| Truy vấn chạy lâu | **state = 'active'**, thời gian từ **query_start** lớn | Câu lệnh vẫn đang thực thi; có thể tốn CPU/I/O hoặc cũng có thể đang chờ một tài nguyên |
| Deadlock | PostgreSQL ghi lỗi **deadlock detected**; một giao dịch nhận SQLSTATE **40P01** | Có một chu trình chờ khóa; PostgreSQL tự hủy một giao dịch để phá chu trình |
| Phiên có vẻ bị treo | Ứng dụng không nhận được kết quả | Có thể là lock wait, truy vấn dài, giao dịch mở, chờ I/O hoặc vấn đề ở tầng ứng dụng |

**Lock wait không đồng nghĩa với deadlock.** Trong lock wait thông thường, phiên chờ có thể tiếp tục ngay khi phiên giữ khóa **COMMIT**, **ROLLBACK** hoặc nhả khóa. Deadlock xuất hiện khi các phiên tạo thành một vòng chờ mà không phiên nào có thể tự tiến lên.

**Giao dịch lâu không nhất thiết có truy vấn lâu.** Một phiên ở trạng thái **idle in transaction** không chạy câu SQL tại thời điểm quan sát, nhưng giao dịch vẫn mở. Nếu giao dịch đã sửa dữ liệu hoặc lấy khóa, các khóa đó có thể được giữ đến khi giao dịch kết thúc.

## 2. Cơ chế khóa liên quan trong PostgreSQL

PostgreSQL sử dụng MVCC (Multi-Version Concurrency Control) để cho phép nhiều giao dịch đọc và ghi đồng thời. Mỗi giao dịch nhìn thấy một phiên bản dữ liệu phù hợp với snapshot của nó. Vì vậy, một truy vấn **SELECT** thông thường thường không phải chờ một giao dịch **UPDATE** đang sửa cùng hàng, và thao tác ghi cũng không phải lúc nào chặn thao tác đọc.

Tuy nhiên, MVCC không loại bỏ mọi xung đột. PostgreSQL vẫn cần khóa để bảo vệ các thao tác thay đổi dữ liệu và cấu trúc:

- **Khóa cấp bảng:** được dùng cho các thao tác như **SELECT**, **INSERT**, **UPDATE**, **DELETE**, **TRUNCATE** và DDL. Mỗi câu lệnh lấy một mode khóa nhất định. Một số mode tương thích với nhau; một số mode xung đột.
- **Khóa cấp hàng:** được dùng cho các thao tác như **UPDATE**, **DELETE** và **SELECT ... FOR UPDATE**. Hai giao dịch muốn sửa hoặc khóa cùng một hàng theo cách xung đột có thể phải chờ nhau.
- **Khóa transaction ID:** một phiên có thể chờ giao dịch khác kết thúc. Đây là một biểu hiện phổ biến khi có xung đột khóa hàng.
- **Khóa advisory:** khóa do ứng dụng chủ động lấy bằng các hàm **pg_advisory_lock**, **pg_advisory_xact_lock** và các biến thể liên quan. PostgreSQL không tự gán ý nghĩa nghiệp vụ cho khóa này; ứng dụng phải thống nhất cách dùng và nhả khóa.
- **Khóa trên đối tượng khác:** ví dụ khóa virtual transaction hoặc khóa liên quan đến quan hệ và catalog nội bộ.

Khóa thường được giữ đến cuối giao dịch, tùy loại khóa và thao tác. Vì vậy, một câu **UPDATE** chạy rất nhanh vẫn có thể khiến phiên khác chờ lâu nếu giao dịch chứa câu lệnh đó không được kết thúc.

### 2.1 Khóa hàng không phải lúc nào cũng hiện thành một dòng tuple lock

Khi kiểm tra **pg_locks**, không nên kỳ vọng mọi khóa hàng đang được giữ đều xuất hiện như một dòng có **locktype = 'tuple'**. PostgreSQL thường ghi thông tin khóa hàng trực tiếp trên tuple; phiên khác muốn sửa cùng hàng có thể phải chờ transaction ID của giao dịch đang giữ khóa. Do đó, truy vấn đang chờ có thể hiển thị **wait_event_type = 'Lock'** và **wait_event = 'transactionid'**.

Đây là lý do nên dùng **pg_blocking_pids()** để xác định quan hệ chặn trực tiếp. **pg_locks** vẫn hữu ích để xem mode, loại khóa, đối tượng và trạng thái **granted**, nhưng tự ghép các dòng khóa để suy ra toàn bộ chuỗi chặn thường phức tạp và dễ sai.

### 2.2 Khóa bảng và DDL

Các thao tác DDL có thể yêu cầu khóa bảng mạnh. Chẳng hạn, **ALTER TABLE** thường cần **ACCESS EXCLUSIVE**, mode này xung đột với hầu hết các khóa bảng khác. Một lệnh thay đổi schema có thể phải đợi các truy vấn đang dùng bảng kết thúc; ngược lại, khi DDL đã xếp hàng chờ, các truy vấn mới cũng có thể bị ảnh hưởng tùy quan hệ tương thích khóa.

Một **SELECT** dài thường không chặn **UPDATE** chỉ vì đọc cùng dữ liệu, nhưng nó giữ **ACCESS SHARE** trên bảng trong thời gian câu lệnh chạy. Khóa này có thể chặn DDL cần **ACCESS EXCLUSIVE**. Vì vậy, khi một migration bị đứng, cần kiểm tra cả truy vấn đọc dài và giao dịch đang mở, không chỉ các lệnh ghi.

## 3. Những nguyên nhân phổ biến

### 3.1 Ứng dụng quên kết thúc giao dịch

Một luồng ứng dụng thực hiện:

```sql
BEGIN;
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;
-- Ứng dụng tiếp tục xử lý nhưng quên COMMIT hoặc ROLLBACK.
```

Giao dịch vẫn mở và khóa cần thiết vẫn có thể được giữ. Phiên khác muốn cập nhật cùng hàng sẽ phải chờ. Nếu connection được trả về pool khi giao dịch vẫn mở, một phiên khác có thể nhận lại connection trong trạng thái không mong muốn.

Nguyên nhân thường gặp là nhánh lỗi không gọi **ROLLBACK**, exception bị bắt nhưng không đóng giao dịch, hoặc logic ứng dụng thực hiện công việc bên ngoài cơ sở dữ liệu trong khi vẫn giữ transaction.

### 3.2 Chờ người dùng hoặc dịch vụ bên ngoài trong transaction

Một giao dịch cập nhật dữ liệu, sau đó gọi API thanh toán, gửi email hoặc chờ người dùng xác nhận rồi mới **COMMIT**. Thời gian mạng có thể kéo dài nhiều giây hoặc nhiều phút, trong khi khóa cơ sở dữ liệu vẫn được giữ.

Nên giới hạn phần công việc nằm trong transaction. Hãy đọc hoặc xác thực dữ liệu trước khi mở transaction khi có thể; sau đó thực hiện các thay đổi cần tính nguyên tử và kết thúc transaction sớm. Với quy trình cần phối hợp dịch vụ ngoài, cân nhắc mô hình outbox, saga hoặc trạng thái xử lý trung gian thay vì giữ transaction mở trong lúc chờ mạng.

### 3.3 Các giao dịch khóa nhiều hàng theo thứ tự khác nhau

Đây là nguyên nhân kinh điển tạo deadlock. Giao dịch A khóa hàng 1 rồi muốn khóa hàng 2; giao dịch B khóa hàng 2 rồi muốn khóa hàng 1. Mỗi giao dịch đang giữ tài nguyên mà giao dịch kia cần.

### 3.4 Truy vấn hoặc thao tác DDL kéo dài

Một truy vấn quét bảng lớn, một lệnh cập nhật nhiều hàng, thao tác tạo chỉ mục hoặc migration có thể làm thời gian giữ khóa tăng lên. DDL cần khóa mạnh còn có thể chờ các phiên đang truy cập bảng.

Cần phân biệt thời gian thực thi của câu lệnh với thời gian của transaction. Một câu lệnh đã hoàn tất nhưng transaction chưa **COMMIT** vẫn có thể tiếp tục giữ khóa.

### 3.5 Thiếu chỉ mục hoặc điều kiện cập nhật quá rộng

Một câu lệnh **UPDATE** hoặc **DELETE** phải tìm quá nhiều hàng có thể chạy lâu và khóa nhiều hàng hơn dự kiến. Chỉ mục phù hợp cho điều kiện lọc, khóa ngoại và đường truy cập thường giúp rút ngắn thời gian xử lý. Tuy nhiên, thêm chỉ mục cũng làm tăng chi phí ghi; hãy dựa vào kế hoạch thực thi và tải thực tế để quyết định.

### 3.6 Khóa ngoại và ràng buộc duy nhất

Khi thêm hoặc xóa dữ liệu ở bảng có quan hệ khóa ngoại, PostgreSQL có thể phải kiểm tra hàng liên quan ở bảng tham chiếu. Các thao tác đồng thời trên hai bảng có thể tạo thêm xung đột khóa. Chỉ mục trên cột khóa ngoại thường giúp các thao tác kiểm tra và cập nhật liên quan hiệu quả hơn.

Các ràng buộc **UNIQUE** cũng có thể khiến một giao dịch phải chờ giao dịch khác xác nhận kết quả ghi một giá trị khóa duy nhất. Khi thấy chờ **transactionid**, hãy xem câu lệnh đang ghi vào bảng và các ràng buộc liên quan.

## 4. Chẩn đoán bằng các view và hàm hệ thống

Các ví dụ dưới đây dành cho phiên bản PostgreSQL hiện đại. Cần quyền quan sát thống kê phù hợp để xem thông tin của các phiên khác. Vai trò **pg_monitor** hoặc **pg_read_all_stats** có thể được cấp cho tài khoản vận hành theo chính sách bảo mật của hệ thống. Nếu không có quyền, một số trường như nội dung truy vấn của phiên khác có thể bị ẩn.

### 4.1 Xem các phiên đang hoạt động và trạng thái chờ

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    query_start,
    clock_timestamp() - query_start AS query_age,
    state_change,
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
```

Các cột cần chú ý:

- **pid**: mã tiến trình backend của PostgreSQL. Đây là giá trị truyền vào các hàm **pg_cancel_backend()** và **pg_terminate_backend()**.
- **application_name**: tên ứng dụng hoặc connection pool đã kết nối. Nên cấu hình trường này ở ứng dụng để dễ nhận diện nguồn kết nối.
- **state**: trạng thái như **active**, **idle**, **idle in transaction** hoặc **idle in transaction (aborted)**.
- **wait_event_type**, **wait_event**: loại tài nguyên đang chờ và sự kiện cụ thể. **Lock** cho biết phiên đang chờ khóa.
- **xact_start**: thời điểm transaction hiện tại bắt đầu. Nếu cột này cũ, transaction đã mở lâu.
- **query_start**: thời điểm câu lệnh hiện tại bắt đầu khi phiên **active**; với phiên không active, đây là thời điểm câu lệnh gần nhất bắt đầu.
- **state_change**: thời điểm trạng thái phiên thay đổi gần nhất.
- **query**: câu lệnh hiện tại hoặc câu lệnh gần nhất, tùy trạng thái phiên.

Không nên kết luận một phiên bị khóa chỉ vì **query_age** lớn. Hãy kiểm tra **wait_event_type** và quan hệ chặn. Một truy vấn có thể chạy lâu do CPU, I/O, kế hoạch truy vấn hoặc chờ một tài nguyên khác.

### 4.2 Tìm phiên bị chặn và phiên đang chặn nó

**pg_blocking_pids(pid)** trả về PID của các phiên đang chặn backend được truyền vào. Hàm này xử lý cả quan hệ chặn trực tiếp do khóa đang giữ và một số trường hợp chặn do phiên khác đang xếp hàng trước.

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    blocked.client_addr AS blocked_client,
    clock_timestamp() - blocked.query_start AS waiting_duration,
    blocked.wait_event_type,
    blocked.wait_event,
    left(blocked.query, 1000) AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 1000) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS bp(pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = bp.pid
WHERE blocked.datname = current_database()
ORDER BY blocked.query_start NULLS LAST;
```

Cách đọc kết quả:

1. **blocked_pid** là phiên đang chờ. Xem **waiting_duration**, **blocked_query** và **wait_event** để biết mức ảnh hưởng.
2. **blocker_pid** là phiên đang chặn. Xem **blocker_state**, **blocker_xact_age** và **blocker_query**.
3. Nếu **blocker_state = 'idle in transaction'**, ứng dụng có thể đã chạy xong câu lệnh cuối nhưng chưa kết thúc transaction.
4. Nếu blocker cũng đang chờ một phiên khác, có thể tồn tại chuỗi chặn nhiều tầng. Tiếp tục tra **pg_blocking_pids(blocker_pid)** để lần theo chuỗi.

**blocker_query** của một phiên idle thường là câu lệnh gần nhất, không phải câu lệnh đang chạy. Hãy kết hợp **xact_start**, log ứng dụng và thông tin connection để xác định transaction đó đã làm gì.

Nếu muốn chỉ xem các phiên đang chờ khóa, có thể thêm điều kiện:

```sql
AND blocked.wait_event_type = 'Lock'
```

Điều kiện này hữu ích khi tập trung vào lock wait. Khi điều tra rộng hơn, nên bỏ điều kiện để không bỏ sót các loại chờ khác.

### 4.3 Tìm transaction nhàn rỗi nhưng chưa kết thúc

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    state_change,
    wait_event_type,
    wait_event,
    left(query, 1000) AS last_query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state IN ('idle in transaction', 'idle in transaction (aborted)')
ORDER BY xact_start NULLS LAST;
```

Phiên **idle in transaction** đáng chú ý vì transaction vẫn mở dù không chạy câu lệnh. Nếu trạng thái là **idle in transaction (aborted)**, một câu lệnh trước đó đã lỗi và transaction đang ở trạng thái lỗi; ứng dụng cần **ROLLBACK** trước khi tiếp tục sử dụng connection.

Một transaction nhàn rỗi có thể giữ khóa đã lấy trước đó. Nó cũng có thể giữ snapshot cũ, làm chậm việc dọn các phiên bản hàng cũ của VACUUM. Vì vậy, cần quan sát cả thời gian transaction và trạng thái phiên.

### 4.4 Xem các khóa trong pg_locks

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    CASE
        WHEN l.relation IS NOT NULL THEN l.relation::regclass::text
        ELSE NULL
    END AS relation_name,
    l.mode,
    l.granted,
    l.transactionid,
    l.virtualxid,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 500) AS query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE a.datname = current_database()
ORDER BY l.granted, a.pid NULLS LAST, l.locktype, l.mode;
```

Ý nghĩa của một số cột:

- **locktype**: loại đối tượng đang bị khóa, ví dụ **relation**, **transactionid**, **virtualxid** hoặc **advisory**.
- **relation_name**: tên bảng hoặc quan hệ khi khóa gắn với một relation.
- **mode**: mode khóa, ví dụ **AccessShareLock**, **RowExclusiveLock** hoặc **AccessExclusiveLock**.
- **granted**: **true** nghĩa là khóa đã được cấp; **false** nghĩa là backend đang chờ khóa đó.
- **transactionid**: transaction ID liên quan khi khóa thuộc loại transaction ID.

**pg_locks** là view chẩn đoán mức thấp. Một khóa có **granted = false** là manh mối về phiên đang chờ, nhưng cần đối chiếu với **pg_stat_activity** và **pg_blocking_pids()** để xác định phiên chặn và câu lệnh gây ra vấn đề.

### 4.5 Theo dõi số deadlock

```sql
SELECT
    datname,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

**deadlocks** là số deadlock được ghi nhận kể từ lần reset thống kê gần nhất. Giá trị này cho biết xu hướng trong khoảng thời gian quan sát, không chỉ ra PID gây ra deadlock trước đó. Muốn biết câu lệnh và giao dịch liên quan, cần xem log PostgreSQL tại thời điểm xảy ra lỗi.

## 5. Phân tích và xử lý deadlock

### 5.1 Một ví dụ deadlock giữa hai giao dịch

Giả sử bảng tài khoản có hai hàng với **id = 1** và **id = 2**.

**Session A:**

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

-- Tạm dừng để Session B cập nhật hàng id = 2.

UPDATE accounts
SET balance = balance + 100
WHERE id = 2;

COMMIT;
```

**Session B:**

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 50
WHERE id = 2;

-- Tạm dừng để Session A yêu cầu hàng id = 2.

UPDATE accounts
SET balance = balance + 50
WHERE id = 1;

COMMIT;
```

Trình tự có thể diễn ra như sau:

1. Session A khóa hàng **id = 1**.
2. Session B khóa hàng **id = 2**.
3. Session A yêu cầu hàng **id = 2** và phải chờ Session B.
4. Session B yêu cầu hàng **id = 1** và phải chờ Session A.
5. A chờ B, đồng thời B chờ A. Hai giao dịch tạo thành một chu trình chờ.

PostgreSQL phát hiện chu trình bằng cơ chế phát hiện deadlock. Sau khi phát hiện, PostgreSQL hủy một giao dịch làm nạn nhân và trả lỗi **deadlock detected**. Giao dịch còn lại có thể tiếp tục khi khóa được giải phóng.

Ứng dụng cần xử lý lỗi này bằng cách rollback và có thể thử lại toàn bộ transaction. Không nên chỉ thử lại câu lệnh cuối vì các thay đổi trước đó thuộc cùng transaction đã bị hủy.

### 5.2 Cách đọc lỗi deadlock

Lỗi thường có dạng:

```text
ERROR: deadlock detected
DETAIL: Process ... waits for ...; blocked by process ...
HINT: See server log for query details.
SQLSTATE: 40P01
```

Log có thể cho biết các process, loại khóa, đối tượng liên quan và câu lệnh của từng bên. Khi phân tích, hãy ghép các thông tin sau:

- PID và thời điểm trong log.
- Câu lệnh của từng transaction.
- Bảng hoặc hàng liên quan.
- Thứ tự mà mỗi transaction lấy khóa.
- Luồng nghiệp vụ hoặc endpoint tạo ra các câu lệnh.

Một deadlock là sự kiện đã được PostgreSQL phát hiện và xử lý bằng cách hủy một transaction. Nếu ứng dụng vẫn thấy truy vấn chờ kéo dài, hãy kiểm tra xem đó có phải lock wait khác đang tiếp diễn hay không.

### 5.3 Giữ thứ tự lấy khóa nhất quán

Biện pháp phòng ngừa quan trọng nhất là yêu cầu các luồng nghiệp vụ lấy khóa theo cùng một thứ tự. Với ví dụ trên, nếu mọi transaction luôn khóa tài khoản theo thứ tự tăng dần của **id**, chúng sẽ không tạo chu trình chỉ vì thứ tự cập nhật hai hàng bị đảo ngược.

```sql
BEGIN;

SELECT id
FROM accounts
WHERE id IN (1, 2)
ORDER BY id
FOR UPDATE;

-- Thực hiện các thay đổi sau khi đã khóa theo thứ tự thống nhất.
UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE id = 2;

COMMIT;
```

Khi cập nhật nhiều hàng, cần xác định thứ tự khóa thống nhất cho tất cả đường đi trong ứng dụng. Một luồng khác vẫn có thể tạo deadlock nếu nó lấy các khóa theo thứ tự ngược lại.

## 6. Xử lý phiên đang chặn

Khi đã xác định được blocker, hãy đánh giá transaction trước khi kết thúc backend:

1. Xác định ứng dụng, người dùng, client và câu lệnh qua **application_name**, **usename**, **client_addr**, **query** và log ứng dụng.
2. Kiểm tra **state**, **xact_start**, **query_start** và các phiên đang chờ blocker đó.
3. Xác định đây là transaction hợp lệ đang xử lý, transaction bị bỏ quên hay truy vấn bất thường.
4. Nếu có thể, yêu cầu ứng dụng hoàn tất hoặc rollback transaction theo luồng vận hành đã thống nhất.
5. Chỉ hủy truy vấn hoặc kết thúc session khi đã hiểu tác động và có quyền phù hợp.
6. Chạy lại truy vấn chẩn đoán để xác nhận blocker đã biến mất và các phiên chờ đã tiếp tục.

### 6.1 Hủy câu lệnh đang chạy

```sql
SELECT pg_cancel_backend(12345);
```

Thay **12345** bằng PID đã xác minh. **pg_cancel_backend()** gửi yêu cầu hủy câu lệnh hiện tại của backend. Hàm này không chủ động đóng connection.

Nếu câu lệnh đang chạy trong transaction tường minh, lỗi hủy câu lệnh thường khiến transaction chuyển sang trạng thái lỗi. Ứng dụng phải **ROLLBACK** trước khi sử dụng transaction tiếp theo. Nếu phiên đang **idle in transaction**, không có câu lệnh đang chạy để hủy; **pg_cancel_backend()** không giải quyết được transaction đang mở đó.

### 6.2 Kết thúc session

```sql
SELECT pg_terminate_backend(12345);
```

**pg_terminate_backend()** kết thúc connection của backend. Transaction chưa commit trên connection đó sẽ bị rollback khi backend kết thúc. Đây là biện pháp mạnh hơn hủy câu lệnh: ứng dụng có thể nhận lỗi mất kết nối, phải tạo connection mới và xử lý lại công việc đang dang dở.

Chỉ dùng khi đã xác minh đúng PID và chấp nhận tác động tới ứng dụng. Không kết thúc session chỉ vì nó có thời gian chạy lâu; có thể đó là một tác vụ hợp lệ. Quyền thực thi các hàm này phụ thuộc quyền sở hữu session và quyền quản trị được cấp.

### 6.3 Kiểm tra sau khi xử lý

Sau khi hủy hoặc kết thúc backend:

- Chạy lại truy vấn dùng **pg_blocking_pids()** để xác nhận quan hệ chặn đã hết.
- Kiểm tra các truy vấn trước đó có tiếp tục hoặc thất bại theo dự kiến không.
- Theo dõi log ứng dụng để tìm lỗi hủy truy vấn, mất kết nối hoặc retry.
- Xác nhận dữ liệu nghiệp vụ nhất quán, đặc biệt khi ứng dụng có cơ chế thử lại.
- Ghi lại PID, thời điểm, nguyên nhân và hành động vận hành để đối chiếu nếu sự cố lặp lại.

## 7. Giới hạn thời gian chờ và thời gian transaction

PostgreSQL cung cấp một số tham số để giới hạn việc chờ và tránh transaction bị bỏ quên.

### 7.1 lock_timeout

**lock_timeout** giới hạn thời gian một câu lệnh chờ để lấy từng khóa. Nếu vượt ngưỡng, PostgreSQL hủy câu lệnh và trả lỗi.

Có thể đặt giới hạn theo transaction:

```sql
BEGIN;
SET LOCAL lock_timeout = '3s';

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;

COMMIT;
```

**SET LOCAL** chỉ có hiệu lực trong transaction hiện tại. Nếu câu lệnh vượt thời gian chờ, ứng dụng cần xử lý lỗi và rollback transaction trước khi tiếp tục.

### 7.2 statement_timeout

**statement_timeout** giới hạn tổng thời gian thực thi của một câu lệnh, bao gồm thời gian chờ khóa. Tham số này hữu ích để ngăn một truy vấn chạy quá lâu, nhưng cần chọn ngưỡng theo đặc điểm workload. Đặt quá thấp có thể hủy các báo cáo hoặc tác vụ hợp lệ.

```sql
SET statement_timeout = '30s';
```

Có thể đặt ở cấp session, role hoặc database tùy chính sách. Với một thao tác cụ thể, cân nhắc **SET LOCAL** bên trong transaction để giới hạn phạm vi ảnh hưởng.

### 7.3 idle_in_transaction_session_timeout

Tham số này giới hạn thời gian một session được phép ở trạng thái idle trong khi transaction vẫn mở. Khi vượt ngưỡng, PostgreSQL tự kết thúc session.

Ví dụ cấu hình cho một role ứng dụng:

```sql
ALTER ROLE app_user
SET idle_in_transaction_session_timeout = '60s';
```

Đây là biện pháp bảo vệ hữu ích với ứng dụng có nguy cơ quên commit hoặc rollback. Tuy nhiên, hãy chọn ngưỡng dựa trên thời gian xử lý hợp lệ của ứng dụng; session bị kết thúc sẽ làm công việc đang dang dở thất bại.

### 7.4 Phân biệt ba giới hạn

| Tham số | Giới hạn điều gì? | Khi vượt ngưỡng |
|---|---|---|
| **lock_timeout** | Thời gian chờ lấy một khóa | Câu lệnh lỗi do hết thời gian chờ khóa |
| **statement_timeout** | Tổng thời gian một câu lệnh | Câu lệnh bị hủy |
| **idle_in_transaction_session_timeout** | Thời gian session nhàn rỗi trong transaction đang mở | Session bị kết thúc |

Không nên đặt các giá trị quá nhỏ một cách đồng loạt. Hãy xem thời gian xử lý bình thường, SLA, kiểu truy vấn và mức độ ảnh hưởng trước khi cấu hình ở cấp role hoặc database.

## 8. Ghi log để điều tra sự cố

Khi sự cố chỉ xuất hiện thoáng qua, log thường là nguồn bằng chứng quan trọng nhất. Có thể cân nhắc các cấu hình sau trong **postgresql.conf**:

```conf
log_lock_waits = on
deadlock_timeout = '1s'
log_line_prefix = '%m [%p] user=%u db=%d app=%a txid=%x '
```

- **log_lock_waits = on**: ghi log các lần chờ khóa kéo dài hơn ngưỡng **deadlock_timeout**.
- **deadlock_timeout**: khoảng thời gian PostgreSQL chờ trước khi thực hiện kiểm tra deadlock cho một lần chờ khóa. Khi bật **log_lock_waits**, ngưỡng này cũng ảnh hưởng thời điểm ghi log lock wait.
- **log_line_prefix**: bổ sung thời gian, PID, user, database, application name và transaction ID vào mỗi dòng log để dễ ghép các sự kiện.

Sau khi thay đổi cấu hình, reload cấu hình theo quy trình quản trị của hệ thống. Một số tham số cần quyền quản trị; thay đổi cấu hình cần được đánh giá về lượng log và tác động vận hành.

Nên cấu hình **application_name** có ý nghĩa ở phía ứng dụng hoặc connection pool. Khi log ghi nhận **app=inventory-worker**, người vận hành có thể nhanh chóng liên hệ phiên database với dịch vụ tạo ra nó.

Khi có deadlock, hãy tìm thông báo **deadlock detected** trong log cùng PID và timestamp. PostgreSQL thường ghi chi tiết về các process chờ và khóa liên quan. Kết hợp log này với log ứng dụng để tái dựng thứ tự câu lệnh trong mỗi transaction.

## 9. Biện pháp phòng ngừa trong thiết kế ứng dụng

### 9.1 Giữ transaction ngắn

Chỉ đưa các thao tác cần tính nguyên tử vào transaction. Tránh chờ người dùng, gọi HTTP, gửi email, tải tệp hoặc thực hiện công việc tốn thời gian khi transaction đang mở.

Một luồng xử lý phù hợp thường có dạng:

1. Thực hiện xác thực và chuẩn bị dữ liệu không cần khóa trước transaction.
2. Mở transaction.
3. Đọc hoặc khóa dữ liệu cần thiết.
4. Thực hiện các thay đổi liên quan.
5. **COMMIT** ngay khi hoàn thành.
6. Thực hiện các tác vụ ngoài database sau commit hoặc qua hàng đợi/outbox.

### 9.2 Luôn kết thúc transaction trên mọi nhánh

Trong ứng dụng, cần bảo đảm cả đường chạy thành công lẫn đường lỗi đều kết thúc transaction. Với connection pool, không trả connection về pool khi transaction vẫn mở hoặc đang ở trạng thái lỗi.

Mẫu xử lý phụ thuộc framework, nhưng nguyên tắc chung là:

- Thành công: commit.
- Có lỗi trước commit: rollback.
- Rollback thất bại hoặc connection không còn đáng tin cậy: loại connection khỏi pool theo cơ chế của driver/pool.
- Không nuốt exception rồi tiếp tục dùng một transaction đã bị đánh dấu lỗi.

### 9.3 Thống nhất thứ tự khóa

Nếu nhiều luồng cập nhật cùng tập tài nguyên, hãy định nghĩa thứ tự khóa nhất quán, ví dụ theo **account_id**, **product_id** hoặc loại tài nguyên. Áp dụng quy tắc này ở mọi service, batch job và tác vụ quản trị.

### 9.4 Khóa đúng phạm vi

Chỉ dùng **SELECT ... FOR UPDATE** khi cần ngăn giao dịch khác sửa hàng trong lúc xử lý. Tránh khóa trước một tập hàng lớn nếu nghiệp vụ chỉ cần một phần nhỏ. Điều kiện lọc và chỉ mục phù hợp giúp giảm số hàng phải kiểm tra và thời gian giữ khóa.

### 9.5 Xử lý retry đúng cách

Deadlock và một số lỗi cạnh tranh là lỗi tạm thời có thể thử lại. Với PostgreSQL, các SQLSTATE thường gặp gồm:

| SQLSTATE | Ý nghĩa | Cách xử lý thường dùng |
|---|---|---|
| **40P01** | **deadlock_detected** | Rollback toàn transaction, sau đó có thể retry |
| **40001** | **serialization_failure** | Rollback toàn transaction và retry theo chính sách |
| **55P03** | **lock_not_available** | Kiểm tra timeout hoặc thao tác lấy khóa không chờ |
| **57014** | **query_canceled** | Xác định câu lệnh bị timeout hay bị hủy chủ động |

Khi retry:

- Thử lại toàn bộ transaction từ đầu, không chỉ câu lệnh cuối.
- Giới hạn số lần retry.
- Dùng khoảng chờ tăng dần và jitter để tránh nhiều client cùng retry tại một thời điểm.
- Bảo đảm thao tác có tính idempotent hoặc có cơ chế chống xử lý trùng.
- Ghi log số lần retry, SQLSTATE và ngữ cảnh nghiệp vụ.

Không retry vô hạn. Nếu nguyên nhân là thứ tự khóa sai hoặc transaction giữ khóa quá lâu, retry chỉ làm tăng tải và khiến sự cố lặp lại.

### 9.6 Thực hiện DDL có kiểm soát

Trước khi chạy migration trên bảng đang có tải:

- Ước lượng thời gian và mode khóa mà lệnh DDL yêu cầu.
- Tránh để migration nằm trong transaction dài nếu không cần thiết.
- Dùng **lock_timeout** để migration thất bại sớm khi không lấy được khóa trong khoảng thời gian cho phép.
- Chạy migration trong thời điểm phù hợp và theo dõi các session bị chặn.
- Với chỉ mục trên bảng đang hoạt động, cân nhắc **CREATE INDEX CONCURRENTLY** khi phù hợp. Lệnh này có quy tắc riêng và không được chạy bên trong transaction block tường minh.

Ví dụ giới hạn thời gian chờ trước một thao tác DDL:

```sql
SET lock_timeout = '5s';
ALTER TABLE orders ADD COLUMN source_code text;
```

Nếu không lấy được khóa trong 5 giây, lệnh thất bại để migration có thể được lên lịch hoặc thử lại theo quy trình. Việc chọn timeout cần phù hợp với mức độ quan trọng và thời gian bảo trì cho phép.

## 10. Quy trình điều tra thực tế

Khi nhận được báo cáo “database bị treo” hoặc “API cập nhật không trả kết quả”, có thể thực hiện theo thứ tự sau:

**Bước 1 — Xác định phạm vi ảnh hưởng.** Hỏi thao tác nào bị chậm, bắt đầu từ thời điểm nào, ảnh hưởng một endpoint hay toàn hệ thống, và có thay đổi triển khai hoặc migration gần thời điểm đó không.

**Bước 2 — Xem trạng thái backend.** Dùng **pg_stat_activity** để tìm phiên **active**, **idle in transaction**, thời gian transaction và **wait_event**.

**Bước 3 — Tìm quan hệ chặn.** Dùng **pg_blocking_pids()** để xác định phiên chờ và blocker. Nếu có nhiều tầng, lần theo từng PID để tìm blocker gốc.

**Bước 4 — Xác định nguồn gốc blocker.** Đối chiếu **application_name**, user, client, **xact_start**, trạng thái và câu lệnh gần nhất với log ứng dụng. Chú ý phiên idle trong transaction.

**Bước 5 — Phân biệt lock wait và deadlock.** Nếu PostgreSQL ghi **deadlock detected**, tìm log và SQLSTATE **40P01**. Nếu chỉ có lock wait, kiểm tra transaction đang giữ khóa và điều kiện để nó kết thúc.

**Bước 6 — Chọn biện pháp ít ảnh hưởng nhất.** Nếu transaction hợp lệ sắp hoàn tất, có thể chờ hoặc phối hợp với ứng dụng. Nếu truy vấn bất thường, cân nhắc cancel. Nếu session bỏ quên transaction và đang gây ảnh hưởng, cân nhắc terminate sau khi xác minh tác động.

**Bước 7 — Xác nhận phục hồi.** Chạy lại truy vấn blocker, theo dõi độ trễ endpoint, số connection và log lỗi. Xác nhận các transaction liên quan đã kết thúc.

**Bước 8 — Khắc phục nguyên nhân gốc.** Sửa đường đi quên commit/rollback, rút ngắn transaction, thống nhất thứ tự khóa, tối ưu truy vấn hoặc điều chỉnh migration và timeout.

## 11. Các sai lầm cần tránh

- **Chỉ nhìn thời gian truy vấn:** truy vấn lâu có thể do CPU/I/O, còn phiên chặn có thể đang idle trong transaction. Luôn xem cả **state**, **wait_event** và **xact_start**.
- **Kết luận mọi lock wait đều là deadlock:** lock wait có thể tự hết khi blocker commit hoặc rollback. Deadlock là chu trình chờ và được PostgreSQL phát hiện riêng.
- **Chỉ tìm tuple lock trong pg_locks:** khóa hàng có thể không hiển thị theo cách mong đợi; hãy dùng **pg_blocking_pids()**.
- **Terminate session đầu tiên có thời gian lâu nhất:** PID đó có thể là tác vụ hợp lệ hoặc thậm chí là phiên đang chờ. Xác định blocker trước khi hành động.
- **Chỉ retry câu lệnh bị lỗi:** khi transaction đã bị hủy do deadlock, cần rollback và chạy lại toàn bộ đơn vị công việc.
- **Đặt timeout quá thấp trên toàn hệ thống:** có thể làm hỏng báo cáo, batch job hoặc migration hợp lệ. Chọn phạm vi cấu hình và ngưỡng dựa trên workload.
- **Bỏ qua idle in transaction:** trạng thái này có thể giữ khóa và snapshot lâu dù không có câu SQL đang chạy.
- **Không ghi application_name:** thiếu định danh ứng dụng khiến việc truy vết PID về service hoặc job khó hơn.

## 12. Ghi nhớ

- Lock wait là một phiên đang chờ khóa; deadlock là một chu trình chờ giữa các giao dịch.
- Transaction có thể giữ khóa sau khi câu lệnh cuối cùng đã hoàn tất, cho đến khi **COMMIT** hoặc **ROLLBACK**.
- **idle in transaction** là trạng thái cần chú ý vì session không chạy truy vấn nhưng transaction vẫn mở.
- **pg_stat_activity** cho biết trạng thái và thời gian; **pg_blocking_pids()** chỉ ra blocker trực tiếp; **pg_locks** cung cấp chi tiết về khóa.
- PostgreSQL tự phát hiện deadlock và hủy một transaction; ứng dụng cần rollback và retry toàn transaction theo chính sách có giới hạn.
- Transaction ngắn, thứ tự khóa nhất quán, timeout phù hợp và log có **application_name** giúp giảm thời gian điều tra cũng như nguy cơ tái diễn.

