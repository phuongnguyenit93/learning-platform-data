# Độ dài giao dịch và thời gian giữ khóa ảnh hưởng lẫn nhau

Một transaction càng kéo dài thì càng có nhiều cơ hội giữ tài nguyên database trong thời gian dài. Khi transaction đã lấy khóa trên một hàng hoặc một phạm vi dữ liệu, khóa thường được giữ cho đến khi transaction commit hoặc rollback. Nếu transaction còn tiếp tục gọi HTTP, chờ người dùng, xử lý tệp hoặc đợi một câu SQL khác, các transaction cần cùng tài nguyên phải chờ theo. Ngược lại, khi transaction phải chờ khóa ở một bước sau, nó có thể tiếp tục giữ những khóa đã lấy trước đó, khiến nhiều giao dịch khác bị chặn lâu hơn.

Vì vậy, **transaction duration** (thời gian sống của transaction) và **lock hold time** (thời gian giữ khóa) có quan hệ chặt chẽ nhưng không phải lúc nào cũng bằng nhau. Transaction có thể tồn tại lâu mà không giữ row lock, chẳng hạn một transaction chỉ đọc bằng MVCC. Một transaction ngắn vẫn có thể gây blocking đáng kể nếu nó lấy khóa độc quyền trên một hàng nóng. Muốn tối ưu concurrency, phải đo cả hai khoảng thời gian và hiểu loại tài nguyên mà transaction đang giữ.

Mục tiêu không phải rút ngắn transaction bằng mọi giá. Những thay đổi cần cùng thành công hoặc cùng thất bại vẫn phải nằm trong một transaction nguyên tử. Cần tìm phần công việc nào thực sự phải nằm trong ranh giới đó, giảm thời gian từ lúc lấy khóa đến lúc giải phóng khóa, và giữ nguyên các bất biến nghiệp vụ.

## 1. Transaction duration và lock hold time là hai khoảng thời gian khác nhau

**Transaction duration** là khoảng từ lúc transaction bắt đầu đến khi kết thúc bằng commit hoặc rollback. Trong khoảng này, transaction có thể đọc dữ liệu, ghi dữ liệu, đợi khóa, đợi I/O hoặc thậm chí không làm gì vì ứng dụng đang tạm dừng.

**Lock hold time** là khoảng từ khi một lock được cấp cho transaction đến khi lock đó được giải phóng. Mỗi lock có thời điểm bắt đầu và kết thúc riêng. Một transaction có thể lấy nhiều khóa ở những thời điểm khác nhau; các khóa có thể có thời gian giữ khác nhau tùy loại khóa và DBMS.

```text
Thời gian ------------------------------------------------------------>

Transaction T1:
BEGIN       đọc dữ liệu    lấy X(A)       gọi dịch vụ ngoài       COMMIT
  |-------------|-------------|--------------------|------------------|
  <---------------- transaction duration --------------------------->
                              <--------- lock hold time ------------->

Transaction T2:
                  cần cập nhật A ----------------------> được cấp khóa
                  |<------------- lock wait ---------->| xử lý, COMMIT
```

T1 bắt đầu trước khi lấy khóa A. T1 chỉ giữ X(A) từ thời điểm lock được cấp đến khi commit, nhưng phần gọi dịch vụ ngoài nằm trong khoảng giữ khóa và kéo dài thời gian T2 phải chờ.

### 1.1. Transaction dài nhưng không nhất thiết giữ row lock

Một transaction đọc dữ liệu bằng MVCC có thể giữ snapshot lâu mà không khóa các hàng để ngăn writer. Ví dụ, PostgreSQL và Oracle cho phép consistent read mà reader thường không chặn writer theo cách shared row lock truyền thống. Tuy nhiên, transaction dài vẫn có thể giữ snapshot cũ, làm chậm việc thu hồi phiên bản cũ hoặc khiến ứng dụng đọc dữ liệu đã lỗi thời.

Ở PostgreSQL, transaction dài có thể giữ xmin/snapshot cũ, khiến VACUUM không thể thu hồi một số tuple version đã hết hiệu lực. Điều này góp phần làm table/index bloat và tăng chi phí đọc. Ở InnoDB, read view lâu sống có thể giữ các undo version cần thiết cho consistent read, làm purge bị chậm. Ở SQL Server khi row versioning được bật, transaction dài có thể giữ phiên bản cần cho snapshot và làm version store tăng. Chi tiết phụ thuộc engine và cấu hình.

### 1.2. Transaction ngắn vẫn có thể giữ khóa quan trọng lâu

Một transaction có thể chỉ chạy một câu `UPDATE` nhưng câu lệnh đó khóa một hàng nóng. Nếu hàng được nhiều request cập nhật, các transaction khác phải xếp hàng. Thời gian giữ khóa ngắn ở từng transaction vẫn có thể tạo hàng đợi lớn khi tần suất đến cao.

Ngược lại, một transaction kéo dài vài giây chỉ đọc bằng snapshot có thể không tạo lock wait trên hàng dữ liệu, nhưng vẫn giữ connection, snapshot và tài nguyên khác. Vì thế, không thể dùng riêng transaction duration để kết luận mức blocking.

## 2. Khóa thường được giữ đến khi nào?

Thời gian giữ khóa phụ thuộc loại khóa, isolation level và DBMS. Một số khóa chỉ cần trong lúc thực hiện statement; một số khóa tồn tại đến hết transaction.

| DBMS/cơ chế | Hành vi thường gặp | Điều cần lưu ý |
|---|---|---|
| PostgreSQL row lock | Khóa hàng do `UPDATE`, `DELETE` hoặc locking read được giữ đến khi transaction kết thúc | `SELECT` MVCC thông thường không lấy row lock; table-level lock đi kèm vẫn có thể tồn tại |
| PostgreSQL Serializable SSI | SIREAD predicate lock ghi nhận vùng đã đọc, thường không chặn writer | Có thể giữ thông tin đến khi transaction liên quan kết thúc và dẫn đến serialization failure |
| MySQL InnoDB | Record/gap/next-key lock của locking read và DML thường được giữ đến commit/rollback | Consistent read thông thường dùng read view, không lấy cùng loại row lock |
| SQL Server | Shared lock ở Read Committed truyền thống thường được nhả sau statement; exclusive/update lock thường giữ đến transaction kết thúc | `REPEATABLE READ`, `SERIALIZABLE`, hints và RCSI làm thay đổi thời gian/phạm vi giữ khóa |
| Oracle | Row lock do DML được giữ đến commit/rollback | Consistent read thông thường dùng undo và không chặn writer theo kiểu row lock |

Đây là mô tả khái quát. Lock escalation, lock hints, cursor, isolation setting và phiên bản có thể thay đổi chi tiết. Khi cần biết chính xác, phải quan sát lock diagnostics trên DBMS thực tế.

### 2.1. Thời điểm lấy khóa có ý nghĩa lớn

Giả sử transaction bắt đầu, đọc một số dữ liệu, thực hiện tính toán và chỉ sau đó mới cập nhật hàng. Nếu không cần khóa trong lúc tính toán, việc lấy khóa sát thời điểm ghi sẽ giảm lock hold time.

Nhưng không được trì hoãn khóa nếu quyết định phụ thuộc vào dữ liệu có thể thay đổi trước khi khóa được lấy. Khi đó, cần đọc lại sau khi khóa, dùng version check hoặc diễn đạt điều kiện thành một atomic update.

Ví dụ, không nên đọc tồn kho ở ngoài transaction rồi dùng giá trị đó để quyết định trừ kho mà không kiểm tra lại. Có thể chuẩn bị payload và tính toán độc lập trước, nhưng phép trừ phải có điều kiện:

```sql
UPDATE inventory
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND quantity >= :requested;
```

Row count xác nhận phép trừ có được chấp nhận hay không. Cách này vừa giảm khoảng đọc-tính-ghi ở ứng dụng, vừa giữ điều kiện tồn kho trong database.

## 3. Transaction dài làm hàng đợi khóa dài hơn

Khi nhiều transaction cần cùng một khóa, DBMS phải sắp xếp chúng theo khả năng tương thích của lock. Một transaction giữ khóa lâu làm các transaction đến sau phải chờ lâu hơn.

Ví dụ một hàng `inventory` được nhiều request cập nhật:

```text
T1: BEGIN
T1: UPDATE inventory WHERE product_id = 42  -> giữ X(A)
T1: gọi HTTP mất 3 giây

T2: UPDATE inventory WHERE product_id = 42  -> chờ X(A)
T3: UPDATE inventory WHERE product_id = 42  -> chờ X(A)
T4: UPDATE inventory WHERE product_id = 42  -> chờ X(A)

T1: COMMIT sau 3 giây
T2, T3, T4 lần lượt có cơ hội tiếp tục
```

T1 có thể chỉ cần vài mili giây để cập nhật hàng, nhưng vì nó gọi dịch vụ ngoài trước commit nên giữ khóa thêm vài giây. T2, T3 và T4 không thể hoàn tất cập nhật cho đến khi khóa được nhả.

### 3.1. Hiệu ứng dây chuyền

Một transaction chờ khóa không nhất thiết chỉ chờ. Nó có thể đã lấy khóa khác trước đó. Khi T2 chờ A nhưng vẫn giữ B, các transaction cần B lại phải chờ T2. Một blocker có thể tạo thành chuỗi blocking nhiều tầng.

```text
T1 giữ X(A)
T2 giữ X(B), chờ X(A)
T3 giữ X(C), chờ X(B)
T4 chờ X(C)

T1 commit
  -> T2 tiếp tục rồi commit
     -> T3 tiếp tục rồi commit
        -> T4 mới được tiếp tục
```

Nếu T1 hoặc T2 bị chậm bởi I/O, network hoặc xử lý ứng dụng, toàn bộ chuỗi bị kéo dài. Đây là lý do một transaction dài có thể gây ảnh hưởng vượt xa số hàng nó trực tiếp cập nhật.

### 3.2. Transaction chờ khóa cũng làm transaction duration tăng

Quan hệ tác động theo cả hai chiều. Transaction dài làm lock hold time tăng khi nó giữ khóa đến commit; ngược lại, lock wait kéo dài làm transaction duration của waiter tăng. Nếu waiter đã giữ khóa khác, nó còn làm tăng lock hold time của các tài nguyên đó.

Do đó, chỉ đo thời gian chạy câu SQL có thể bỏ sót nguyên nhân. Cần tách thời gian thực thi CPU/I/O, thời gian chờ khóa, thời gian ứng dụng nằm giữa các statement và thời gian từ BEGIN đến COMMIT.

## 4. Vì sao throughput giảm mạnh khi mức sử dụng khóa gần bão hòa?

Một tài nguyên bị tuần tự hóa, chẳng hạn một hàng counter hoặc một khóa độc quyền, chỉ có thể cấp quyền cho một transaction tại một thời điểm. Nếu yêu cầu đến gần bằng năng lực phục vụ của tài nguyên đó, thời gian chờ có thể tăng rất nhanh.

Gọi:

- \(\lambda\): tốc độ transaction cần cùng tài nguyên, tính theo yêu cầu/giây.
- \(S\): thời gian trung bình giữ khóa cho mỗi yêu cầu.
- \(\mu = 1/S\): năng lực phục vụ lý tưởng của tài nguyên đơn.
- \(\rho = \lambda/\mu = \lambda S\): mức sử dụng của tài nguyên.

Khi \(\rho\) tiến gần 1, tài nguyên gần như luôn bận. Một request đến trong lúc tài nguyên đang được giữ phải xếp hàng. Biến động thời gian giữ khóa làm đuôi hàng đợi dài hơn nữa.

Trong mô hình M/M/1 lý tưởng, thời gian chờ hàng đợi có dạng:

\[
W_q = \frac{\lambda}{\mu(\mu-\lambda)}
\]

Mô hình này giả định arrival/service đơn giản và một server; database thực tế phức tạp hơn, có nhiều lock mode, nhiều tài nguyên và lịch lập lịch riêng. Công thức chỉ minh họa một ý quan trọng: khi utilization tiến sát 100%, chờ đợi tăng phi tuyến. Giảm thời gian giữ khóa từ 100 ms xuống 50 ms có thể làm thay đổi năng lực phục vụ của một hot row đáng kể; tăng số worker trong khi giữ khóa vẫn 100 ms không làm hàng đó xử lý song song hơn.

### 4.1. Một transaction chậm có thể làm p99 tăng mạnh

Giả sử 99% transaction giữ khóa 5 ms, nhưng 1% giữ khóa 2 giây vì gọi dịch vụ ngoài. Những transaction chậm hiếm hoi vẫn có thể khiến nhiều request đến sau bị dồn hàng. p50 có thể vẫn thấp, trong khi p95/p99 tăng mạnh.

Thời gian giữ khóa có phân phối đuôi dài thường gây vấn đề lớn hơn chỉ nhìn giá trị trung bình. Hãy theo dõi histogram và percentiles, không chỉ average lock duration.

## 5. Deadlock và transaction dài

Transaction dài làm cửa sổ tồn tại của các lock chồng lấn lớn hơn. Khi các transaction lấy nhiều khóa theo thứ tự khác nhau, xác suất tạo chu trình chờ tăng.

Ví dụ:

```text
T1: BEGIN
T1: khóa A
T1: gọi dịch vụ ngoài, vẫn giữ A

T2: BEGIN
T2: khóa B
T2: yêu cầu A -> chờ T1

T1: yêu cầu B -> chờ T2

T1 -> T2 -> T1  (deadlock)
```

Nếu T1 không giữ A trong lúc gọi dịch vụ ngoài, khoảng thời gian hai transaction giữ các khóa giao nhau có thể ngắn hơn. Tuy nhiên, cách sửa căn bản là lấy khóa theo thứ tự thống nhất và giữ transaction ngắn; không chỉ tăng deadlock timeout hoặc retry limit.

### 5.1. Thứ tự khóa ổn định

Nếu nhiều transaction cần khóa A và B, hãy khóa theo cùng một thứ tự, chẳng hạn `account_id` tăng dần. Điều này giảm khả năng T1 giữ A chờ B trong khi T2 giữ B chờ A.

```sql
SELECT account_id, balance
FROM account
WHERE account_id IN (:id1, :id2)
ORDER BY account_id
FOR UPDATE;
```

Thứ tự thực tế cần được xác nhận với DBMS và execution plan; `ORDER BY` trong query là một phần của cách diễn đạt, nhưng không thay thế việc kiểm tra access path và lock order thực tế khi có nhiều bảng.

### 5.2. Retry không làm transaction dài trở nên vô hại

Sau deadlock victim hoặc serialization failure, ứng dụng thường retry toàn bộ transaction. Nếu transaction gốc dài và xung đột thường xuyên, mỗi lần retry lặp lại cùng công việc và tạo thêm tải. Dùng backoff có jitter, giới hạn attempt, rút ngắn transaction và sửa lock order để giảm xác suất lặp lại.

Không retry câu lệnh cuối dựa trên giá trị đã đọc trong transaction cũ. Phải rollback, bắt đầu transaction mới, đọc lại dữ liệu và tính lại quyết định.

## 6. Các nguyên nhân vô tình kéo dài lock hold time

Một transaction thường giữ khóa lâu vì có công việc nằm giữa thời điểm acquire lock và commit mà không thực sự cần nằm trong khoảng đó.

### 6.1. Gọi HTTP, RPC hoặc message broker trong transaction

```text
BEGIN
UPDATE order SET status = 'CONFIRMING' ...
Gọi payment service (chờ 1.5 giây)
INSERT payment_audit ...
COMMIT
```

Nếu `UPDATE order` đã lấy khóa, transaction giữ khóa trong suốt thời gian chờ payment service. Network timeout hoặc retry ở dịch vụ ngoài có thể kéo dài thêm.

Một cách thiết kế thường tốt hơn là ghi trạng thái và outbox trong transaction ngắn, commit, rồi worker xử lý tác động bên ngoài. Cần thiết kế state machine và idempotency để xử lý trường hợp payment thất bại hoặc response không rõ.

### 6.2. Chờ người dùng trong lúc transaction mở

Không mở transaction, khóa hàng rồi chờ người dùng xác nhận trên giao diện. Người dùng có thể đọc màn hình vài phút trước khi bấm nút; trong thời gian đó, các transaction khác bị chặn.

Thay vào đó, đọc dữ liệu để hiển thị, gửi version/token cho client, rồi khi người dùng xác nhận hãy mở transaction mới và cập nhật có điều kiện theo version. Nếu dữ liệu đã thay đổi, trả conflict để người dùng xem lại.

### 6.3. Xử lý tệp, tính toán lớn hoặc serialize payload

Nén tệp, tạo PDF, gọi thuật toán tính toán dài hoặc serialize một payload lớn thường không cần giữ row lock. Chuẩn bị trước transaction nếu dữ liệu đầu vào không cần khóa; hoặc ghi trạng thái công việc rồi xử lý bất đồng bộ.

Nếu kết quả tính toán phụ thuộc vào dữ liệu có thể thay đổi, hãy dùng version check hoặc đọc lại/khóa ở giai đoạn commit để xác nhận đầu vào vẫn hợp lệ.

### 6.4. ORM flush quá sớm hoặc giữ transaction quanh toàn request

Một số framework mở transaction ở đầu request và commit khi response hoàn tất. Nếu code thực hiện validation, gọi API, tải file hoặc chờ người dùng sau khi đã flush entity, row lock có thể được giữ suốt phần còn lại của request.

Hãy kiểm tra transaction boundary do framework quản lý, thời điểm ORM flush, lazy loading trong transaction và các interceptor/aspect tự động mở transaction. Không giả định `save()` luôn commit ngay; nhiều ORM chỉ flush khi cần hoặc lúc commit.

### 6.5. Cursor/streaming query và batch xử lý dài

Một cursor có thể giữ transaction/snapshot trong suốt quá trình client đọc từng phần. Nếu code vừa stream dữ liệu vừa thực hiện xử lý chậm, connection và snapshot có thể tồn tại lâu. Với locking cursor hoặc update cursor, khóa có thể được giữ trong thời gian dài.

Nếu chỉ cần export dữ liệu, cân nhắc snapshot/read-only transaction riêng, keyset pagination hoặc chia trang theo một watermark ổn định. Nhưng pagination nhiều transaction có thể nhìn thấy dữ liệu thay đổi giữa các trang; phải xác định yêu cầu nhất quán của export trước khi chia nhỏ.

## 7. Transaction dài gây áp lực ngoài lock manager

Ngay cả khi transaction không giữ row lock chặn writer, transaction dài vẫn tiêu thụ tài nguyên và làm thay đổi khả năng dọn dẹp phiên bản.

### 7.1. Snapshot cũ và MVCC cleanup

MVCC giữ nhiều phiên bản hàng để transaction đọc đúng snapshot. Một transaction lâu sống có thể cần các phiên bản cũ trong thời gian dài, làm vacuum/purge/version cleanup chưa thể loại bỏ chúng.

Hệ quả có thể gồm:

- PostgreSQL table/index bloat tăng và VACUUM phải làm việc nhiều hơn.
- InnoDB undo history tăng, purge bị chậm và history list length cao.
- SQL Server version store tăng khi row versioning được sử dụng.
- Tăng I/O, dung lượng lưu trữ và chi phí truy vấn do nhiều phiên bản tồn tại.

Các chỉ số và cơ chế cụ thể khác nhau theo DBMS. Nhưng nguyên tắc chung là transaction/snapshot quá dài làm tăng thời gian một phiên bản cũ phải được giữ lại.

### 7.2. Connection pool bị chiếm dụng

Transaction dài thường giữ connection trong suốt thời gian tồn tại. Nếu nhiều request cùng chờ bên ngoài database trong transaction, pool có thể cạn connection dù database không thực hiện nhiều công việc hữu ích.

Request mới phải chờ lấy connection; sau đó khi có connection, nó mới bắt đầu truy vấn. Đây là một hàng đợi ở tầng ứng dụng chồng lên hàng đợi lock trong database.

Tăng pool size có thể chỉ chuyển hàng đợi từ ứng dụng vào database, làm active session và contention tăng. Cần đo pool wait, số connection đang dùng, active transaction và lock wait cùng lúc.

### 7.3. Log, replication và recovery

Transaction ghi nhiều dữ liệu hoặc kéo dài có thể tạo log lớn, giữ log record cần thiết cho rollback/recovery và ảnh hưởng replication. Với một số engine, transaction dài có thể làm replica apply hoặc log truncation chậm hơn tùy kiến trúc. Cần theo dõi transaction log/WAL, replication lag và thời gian rollback.

Không phải mọi transaction dài đều tạo log lớn; transaction read-only vẫn có thể giữ snapshot lâu. Hãy phân biệt áp lực do write volume với áp lực do transaction lifetime.

## 8. Đo transaction duration và lock hold time

Để điều tra đúng, cần có ít nhất ba mốc thời gian:

1. Transaction bắt đầu.
2. Lock được cấp hoặc bắt đầu chờ.
3. Transaction commit/rollback và lock được giải phóng.

Với một transaction, có thể ghi nhận:

```text
transaction_duration = commit_time - begin_time
lock_hold_time       = release_time - acquire_time
lock_wait_time       = grant_time - request_time
```

Các đại lượng này trả lời các câu hỏi khác nhau:

- Transaction duration cho biết transaction sống bao lâu.
- Lock hold time cho biết tài nguyên bị giữ bao lâu.
- Lock wait time cho biết transaction phải chờ bao lâu để lấy tài nguyên.

Không cộng hoặc so sánh các chỉ số như thể chúng luôn bằng nhau. Một transaction có thể giữ nhiều lock; cần phân tích theo lock/resource và theo transaction.

### 8.1. Các chỉ số nên theo dõi

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Transaction duration p50/p95/p99 | Thời gian từ begin đến kết thúc | p99 cao, transaction idle hoặc chờ ngoài database |
| Lock wait duration | Thời gian chờ được cấp khóa | Một resource có waiter lâu hoặc hàng đợi tăng |
| Lock hold duration | Thời gian từ acquire đến release | Một blocker giữ khóa lâu bất thường |
| Longest active transaction | Transaction đang mở lâu nhất | `idle in transaction`, cursor hoặc request bị treo |
| Blocking chain depth | Số tầng transaction chờ lẫn nhau | Một blocker gây ảnh hưởng nhiều session |
| Deadlock count | Số chu trình chờ bị phát hiện | Thứ tự khóa không ổn định hoặc transaction overlap dài |
| Connection pool wait | Thời gian chờ connection | Transaction giữ connection quá lâu hoặc pool quá nhỏ |
| MVCC cleanup pressure | Bloat, undo/history hoặc version store | Snapshot/transaction tồn tại quá lâu |
| Commit latency | Thời gian hoàn tất commit | Log flush, replication acknowledgment hoặc I/O chậm |

Theo dõi percentiles và max cùng với average. Một số ít transaction cực dài có thể chi phối p99 và làm hàng đợi khóa tăng mạnh.

## 9. Quan sát transaction và lock trên PostgreSQL

PostgreSQL cung cấp `pg_stat_activity` để xem transaction đang chạy, thời điểm bắt đầu và trạng thái chờ.

```sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    query_start,
    clock_timestamp() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Tìm session bị block và blocker:

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.xact_start AS blocked_xact_start,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocked.wait_event_type,
    blocked.wait_event,
    blocker.pid AS blocker_pid,
    blocker.xact_start AS blocker_xact_start,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    blocker.state AS blocker_state,
    blocker.query AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid;
```

Một blocker ở trạng thái `idle in transaction` là dấu hiệu đáng chú ý: transaction đang mở nhưng backend không chạy statement. Có thể ứng dụng đã thực hiện DML rồi chờ network hoặc logic bên ngoài trước khi commit.

Để xem lock:

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple,
    a.state,
    a.xact_start,
    a.query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
ORDER BY l.pid, l.granted, l.locktype;
```

`pg_locks` hiển thị lock hiện có và trạng thái granted; không phải mọi lock đều tương ứng với một hàng. Đọc kết hợp `pg_stat_activity`, `pg_blocking_pids`, query plan và transaction timeline.

## 10. Quan sát InnoDB transaction và lock wait

MySQL 8.0 có thể xem transaction đang mở qua `information_schema.innodb_trx`:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
    trx_wait_started,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Quan sát lock và quan hệ chờ qua Performance Schema:

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks;
```

```sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_MODE AS waiting_lock_mode,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx,
    blk.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

Tên cột và quyền truy cập phụ thuộc phiên bản. `SHOW ENGINE INNODB STATUS` cũng hữu ích để xem deadlock gần nhất và thông tin transaction đang giữ/chờ khóa.

## 11. Quan sát lock và transaction trên SQL Server

SQL Server có `sys.dm_tran_locks` để xem lock request và `sys.dm_exec_requests` để xem request đang chờ.

```sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status,
    resource_description
FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID()
ORDER BY request_session_id, resource_type;
```

```sql
SELECT
    session_id,
    status,
    command,
    start_time,
    wait_type,
    wait_time,
    blocking_session_id,
    total_elapsed_time,
    cpu_time,
    reads,
    writes
FROM sys.dm_exec_requests
WHERE session_id <> @@SPID;
```

Có thể kết hợp `sys.dm_tran_session_transactions`, `sys.dm_exec_sessions` và `sys.dm_exec_sql_text` để xác định transaction và câu lệnh liên quan. Quyền DMV phụ thuộc phiên bản và quyền server/database.

Đừng suy ra lock hold time chỉ từ `total_elapsed_time` của request. Một request có thể đang chờ khóa; cần phân biệt wait time, execution time và thời điểm lock được cấp/nhả.

## 12. Quan sát session và blocker trên Oracle

Oracle cung cấp các view như `V$SESSION`, `V$LOCK`, `V$TRANSACTION` và `V$SQL`.

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    logon_time,
    sql_id,
    event,
    blocking_session,
    seconds_in_wait,
    last_call_et
FROM v$session
WHERE type = 'USER'
ORDER BY last_call_et DESC;
```

Transaction đang hoạt động có thể được nối với `V$TRANSACTION` qua địa chỉ transaction tương ứng. Quyền truy cập view phụ thuộc quyền DBA hoặc catalog grant. `LAST_CALL_ET` không phải lock hold time; cần diễn giải cùng `EVENT`, `BLOCKING_SESSION` và transaction state.

## 13. Rút ngắn transaction mà vẫn giữ atomicity

Nguyên tắc thực tế là **mở transaction càng muộn càng tốt, commit càng sớm càng tốt**, nhưng không được tách những thay đổi cần nguyên tử thành các transaction không liên quan.

Một transaction nghiệp vụ thường có thể được chia thành ba phần:

1. Công việc chuẩn bị không cần khóa và không cần transaction.
2. Phần database ngắn cần đọc/ghi nguyên tử và bảo vệ bất biến.
3. Tác động ngoài database được thực hiện sau commit qua outbox hoặc một quy trình bù trừ.

Ví dụ luồng xác nhận đơn hàng:

```text
Trước transaction:
  validate định dạng request
  tính payload/giá trị không phụ thuộc trạng thái thay đổi

Transaction ngắn:
  kiểm tra trạng thái đơn hàng hiện tại
  cập nhật đơn hàng
  cập nhật tồn kho có điều kiện
  ghi outbox event
  COMMIT

Sau commit:
  worker gửi event/gọi dịch vụ ngoài
  consumer xử lý idempotent
```

Nếu bước cập nhật tồn kho thất bại, transaction rollback cả trạng thái đơn hàng và outbox. Nếu transaction commit, worker có thể gửi event sau đó. Cần có idempotency cho consumer và quy tắc retry/compensation cho dịch vụ ngoài.

### 13.1. Chuẩn bị trước, xác nhận lại trong transaction

Có thể tính giá, dựng payload hoặc tải thông tin tham khảo trước khi mở transaction. Nhưng dữ liệu có thể thay đổi như số dư, tồn kho, quota hoặc trạng thái order phải được xác nhận lại bên trong transaction bằng atomic predicate, version check hoặc lock.

Không dùng một giá trị đọc từ cache trước transaction làm căn cứ cuối cùng cho một giới hạn quan trọng mà không kiểm tra lại trong database.

### 13.2. Dùng atomic update để giảm số lần round trip

Thay vì `SELECT`, tính toán trong ứng dụng, rồi `UPDATE`, có thể dùng một câu lệnh:

```sql
UPDATE inventory
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND quantity >= :requested;
```

Điều kiện và thay đổi được đánh giá cùng thao tác ghi. Điều này giảm khoảng thời gian giữa đọc và ghi, đồng thời giúp DBMS tuần tự hóa cập nhật trên cùng hàng. Ứng dụng vẫn phải kiểm tra row count và giữ transaction với các thay đổi nghiệp vụ liên quan.

### 13.3. Optimistic locking cho thao tác có thể conflict

Với dữ liệu ít tranh chấp, dùng version column để tránh giữ khóa bi quan trong thời gian người dùng suy nghĩ hoặc tính toán. Khi flush, update có điều kiện theo version. Nếu version đã đổi, trả conflict và yêu cầu đọc lại/hợp nhất.

Optimistic locking giảm lock hold time nhưng không miễn phí: xung đột gây rollback/retry và có thể tạo retry storm nếu cùng một hàng nóng. Chọn theo tần suất conflict thực tế.

## 14. Tách tác động ngoài database bằng outbox

Một transaction không thể rollback email đã gửi hoặc payment đã được dịch vụ ngoài chấp nhận. Gọi các dịch vụ đó trong lúc giữ lock vừa kéo dài transaction vừa tạo bài toán phân tán khó xử lý.

Transactional outbox ghi ý định phát sự kiện trong cùng transaction với thay đổi nghiệp vụ:

```sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id
  AND status = 'PENDING';

INSERT INTO outbox(event_id, aggregate_id, event_type, payload)
VALUES (:event_id, :order_id, 'OrderConfirmed', :payload);

COMMIT;
```

Worker đọc outbox và gửi message sau commit. Nếu worker crash sau khi gửi nhưng trước khi đánh dấu event đã gửi, message có thể được gửi lại; consumer phải deduplicate bằng event ID/idempotency key.

Outbox rút ngắn thời gian giữ khóa trong transaction nghiệp vụ và giữ atomicity giữa thay đổi dữ liệu với ý định phát event. Nó không tạo exactly-once delivery qua mạng.

## 15. Chia batch có thể giảm lock duration nhưng thay đổi semantics

Một transaction cập nhật 100.000 hàng có thể giữ nhiều khóa và tạo log lớn. Chia thành batch 500 hàng giúp mỗi transaction ngắn hơn, nhưng giữa các batch, dữ liệu có thể ở trạng thái một phần đã cập nhật.

Trước khi chia batch, xác định nghiệp vụ cần một trong ba mô hình:

- **All-or-nothing:** toàn bộ dữ liệu phải commit cùng nhau. Không được chia transaction nếu không có giao thức đảm bảo tương đương.
- **Progressive:** có thể chấp nhận từng phần hoàn tất. Cần checkpoint, trạng thái tiến độ và idempotency.
- **Eventually complete:** job có thể tiếp tục sau crash. Cần lease, retry và cơ chế đối soát.

Ví dụ batch update theo keyset:

```sql
UPDATE large_table
SET normalized_value = :value
WHERE id > :last_id
  AND id <= :next_id;
```

Sau mỗi batch, lưu checkpoint trong cùng transaction với dữ liệu batch đó. Khi chạy lại, bắt đầu từ checkpoint đã commit. Không dùng `OFFSET` trên tập dữ liệu đang thay đổi nếu có thể làm bỏ sót hoặc xử lý lặp hàng.

Batch nhỏ giảm thời gian giữ lock từng đợt nhưng tăng số lần commit và có thể giảm throughput nếu overhead commit lớn. Hãy benchmark cả lock wait lẫn chi phí commit.

## 16. Vì sao không nên chỉ tăng lock timeout?

Tăng lock timeout không làm blocker nhả khóa sớm hơn. Nó chỉ cho waiter chờ lâu hơn trước khi báo lỗi.

Nếu transaction giữ khóa 30 giây, tăng timeout từ 5 lên 60 giây có thể làm nhiều request nằm chờ lâu hơn, giữ connection lâu hơn và làm pool cạn. Nó có thể giảm số lỗi timeout nhìn thấy nhưng tăng p99 latency và lượng công việc đang chờ.

Timeout có ích như một giới hạn bảo vệ tài nguyên và deadline. Nhưng cần điều tra blocker, lock hold time, execution plan và transaction boundary trước khi thay đổi.

Một chính sách hợp lý thường phối hợp:

- Lock timeout đủ ngắn để request không chờ vượt deadline.
- Retry có giới hạn với backoff/jitter cho lỗi có thể phục hồi.
- Transaction ngắn và thứ tự khóa nhất quán.
- Admission control để không đưa quá nhiều request vào tài nguyên nóng.
- Cảnh báo blocker/transaction lâu sống.

## 17. Transaction dài và `idle in transaction`

Trạng thái idle-in-transaction xuất hiện khi transaction đang mở nhưng session không thực hiện statement. Điều này thường do ứng dụng đã đọc/ghi xong một bước rồi chờ code khác trước khi commit.

Ví dụ:

```text
BEGIN
SELECT ... FOR UPDATE
Ứng dụng chờ user confirmation
Ứng dụng chờ HTTP response
Ứng dụng serialize response
COMMIT
```

Trong lúc session idle, transaction có thể vẫn giữ row/table lock, snapshot và connection. Đây là một nguyên nhân phổ biến của blocking kéo dài.

PostgreSQL có `idle_in_transaction_session_timeout` để kết thúc session idle trong transaction quá lâu. Cấu hình này là lớp bảo vệ, không thay thế việc sửa transaction boundary. Khi bị timeout, ứng dụng phải xử lý connection bị đóng và transaction rollback.

Các DBMS khác có cấu hình timeout/session/resource governor riêng. Không giả định một tham số timeout có cùng tên hoặc cùng phạm vi trên mọi engine.

## 18. Các thao tác không giải phóng lock như nhiều người nghĩ

- **Savepoint:** rollback về savepoint không nhất thiết giải phóng mọi lock đã lấy sau savepoint theo cùng cách ở mọi DBMS. Không dùng savepoint như cơ chế thay thế commit để nhả khóa.
- **Flush của ORM:** flush gửi DML xuống database nhưng không commit; lock thường vẫn được giữ cho đến khi transaction kết thúc.
- **Đọc lại dữ liệu:** một `SELECT` mới không tự giải phóng khóa ghi đang giữ.
- **Trả object về controller:** không có nghĩa transaction đã commit nếu framework mở transaction bao quanh request.
- **Ngủ giữa hai statement:** transaction vẫn mở và các lock đã lấy vẫn có thể được giữ.
- **Tạo thêm connection:** không giải phóng khóa của transaction cũ; có thể làm số session tranh chấp tăng lên.

Muốn nhả khóa transaction-level, thông thường phải commit/rollback transaction hoặc kết thúc session theo quy tắc DBMS. Nếu cần chia nhỏ transaction, phải đánh giá lại atomicity và trạng thái trung gian.

## 19. Thí nghiệm hai session: thời gian giữ khóa kéo dài waiter

Thí nghiệm sau dùng PostgreSQL. Tạo bảng:

```sql
CREATE TABLE lock_duration_lab (
    id    integer PRIMARY KEY,
    value integer NOT NULL
);

INSERT INTO lock_duration_lab(id, value)
VALUES (1, 100);
```

### Session A — lấy khóa rồi để transaction mở

```sql
BEGIN;

UPDATE lock_duration_lab
SET value = value + 1
WHERE id = 1;

-- Chưa COMMIT. Giữ transaction mở.
```

### Session B — yêu cầu cùng hàng

```sql
BEGIN;

UPDATE lock_duration_lab
SET value = value + 10
WHERE id = 1;

-- Statement chờ khóa do A đang giữ.
```

Trong khi B đang chờ, kiểm tra `pg_stat_activity` và `pg_blocking_pids` bằng session thứ ba hoặc công cụ quan sát khác. Ghi lại thời điểm bắt đầu wait.

### Quay lại Session A

```sql
COMMIT;
```

B tiếp tục, sau đó:

```sql
COMMIT;
```

Kiểm tra giá trị cuối:

```sql
SELECT * FROM lock_duration_lab WHERE id = 1;
```

Giá trị phải là 111 nếu cả hai transaction commit. Thí nghiệm chứng minh B chờ từ lúc yêu cầu khóa đến khi A commit; thời gian A giữ transaction sau câu `UPDATE` chính là phần làm tăng lock hold time.

### 19.1. Lặp lại với transaction A commit ngay

Chạy lại từ giá trị ban đầu. Cho A thực hiện `UPDATE` rồi commit ngay, không chèn khoảng chờ. B sẽ có cơ hội tiếp tục nhanh hơn. So sánh lock wait của B giữa hai lượt.

Không cần dùng `pg_sleep` trong production. Trong lab có thể giữ A mở thủ công để quan sát; nếu dùng sleep để tự động hóa, chỉ dùng trên bảng thử nghiệm và rollback/commit có kiểm soát.

## 20. Thí nghiệm: transaction duration dài nhưng không chặn writer bằng MVCC

Thí nghiệm này cho thấy transaction duration không bằng lock hold time. Dùng PostgreSQL Read Committed hoặc Repeatable Read.

### Session A — đọc bằng MVCC

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT value
FROM lock_duration_lab
WHERE id = 1;

-- Giữ transaction mở nhưng không lấy FOR UPDATE.
```

### Session B — cập nhật cùng hàng

```sql
BEGIN;

UPDATE lock_duration_lab
SET value = value + 5
WHERE id = 1;

COMMIT;
```

Trong PostgreSQL, SELECT thông thường ở A dùng MVCC và không giữ row lock chặn update của B. B có thể commit trong lúc A vẫn mở transaction.

Nếu A chạy lại SELECT ở Read Committed, statement mới có thể thấy giá trị B vừa commit. Nếu A dùng Repeatable Read và đã xác lập snapshot, A có thể tiếp tục thấy giá trị cũ trong transaction đó.

Kết luận: A có transaction duration dài và snapshot tồn tại lâu, nhưng không nhất thiết có row lock khiến B chờ. Điều này không có nghĩa transaction dài vô hại; nó vẫn giữ connection và snapshot, có thể ảnh hưởng cleanup/version retention.

## 21. Chọn transaction boundary cho một thao tác nghiệp vụ

Khi thiết kế transaction, hãy trả lời các câu hỏi:

1. Những thay đổi nào phải cùng commit hoặc cùng rollback?
2. Những dữ liệu nào cần đọc nhất quán để đưa ra quyết định?
3. Có thể chuyển phần tính toán hoặc gọi dịch vụ ngoài ra trước/sau transaction không?
4. Có thể thay read-modify-write bằng atomic update không?
5. Có cần khóa bi quan, version check hoặc Serializable không?
6. Lock được lấy ở statement nào và giải phóng ở thời điểm nào?
7. Có đoạn code nào chờ network, user, queue hoặc file I/O khi transaction vẫn mở không?
8. Nếu chia batch, nghiệp vụ có chấp nhận trạng thái hoàn tất từng phần không?
9. Nếu commit thành công nhưng response mất, idempotency xử lý thế nào?

Một transaction tốt thường chỉ bao gồm phần cần bảo đảm nguyên tử. Nó không nhất thiết phải bao trùm toàn bộ vòng đời HTTP request hoặc toàn bộ quy trình nghiệp vụ nhiều phút.

## 22. Quy trình điều tra transaction giữ khóa quá lâu

Khi có blocking hoặc p99 tăng, điều tra theo thứ tự:

1. **Tìm waiter và blocker.** Xác định session nào đang chờ, session nào giữ khóa.
2. **Xác định resource và lock mode.** Hàng, index key, range, table hay tài nguyên khác?
3. **Đo transaction age của blocker.** Transaction bắt đầu lúc nào, đã idle bao lâu?
4. **Tìm statement đã lấy khóa.** Không chỉ xem query hiện tại; lock có thể được lấy ở statement trước.
5. **Xem ứng dụng đang làm gì giữa acquire và commit.** HTTP, user wait, serialization, file I/O, retry hay xử lý CPU?
6. **Kiểm tra execution plan và lock footprint.** Scan rộng, index thiếu hoặc predicate không sargable có thể làm phạm vi lock tăng.
7. **Kiểm tra blocking chain và deadlock.** Waiter có đang giữ lock khác không?
8. **Đo p95/p99 transaction/lock hold/wait.** Tìm tail transaction thay vì chỉ nhìn average.
9. **Đề xuất thay đổi transaction boundary hoặc atomic operation.** Giữ nguyên các bước cần atomicity.
10. **Chạy concurrency test và benchmark lại.** Xác nhận cả throughput lẫn bất biến.

Đừng kết luận transaction dài chỉ từ query duration. Một query chạy 10 ms có thể bắt đầu transaction rồi giữ khóa thêm 5 giây trước commit; một query chạy 2 giây bằng snapshot read có thể không chặn writer.

## 23. Những điểm cần ghi nhớ

- Transaction duration là thời gian từ BEGIN đến COMMIT/ROLLBACK; lock hold time là thời gian một khóa cụ thể được giữ. Hai khoảng liên quan nhưng không đồng nhất.
- Transaction dài có thể giữ khóa transaction-level lâu hơn, giữ connection và snapshot, đồng thời làm tăng áp lực MVCC cleanup.
- Lock wait có thể kéo dài transaction của waiter; nếu waiter đã giữ khóa khác, nó làm tăng blocking dây chuyền.
- Một transaction chờ HTTP, user, file hoặc queue sau khi lấy khóa có thể giữ tài nguyên database trong suốt thời gian chờ.
- Khi một hot resource gần bão hòa, thời gian chờ tăng nhanh; vài transaction đuôi dài có thể đẩy p99 lên cao.
- Transaction dài làm các lock chồng lấn lâu hơn và tăng cơ hội deadlock; thứ tự khóa nhất quán và transaction ngắn giúp giảm rủi ro.
- MVCC read có thể giữ transaction/snapshot lâu mà không chặn writer; vẫn có thể làm chậm vacuum/purge/version cleanup.
- ORM flush không phải commit; savepoint, sleep hoặc trả object khỏi controller không tự giải phóng transaction-level lock.
- Rút ngắn transaction bằng cách chuẩn bị trước, mở transaction sát thời điểm ghi, commit ngay sau phần nguyên tử và dùng outbox cho tác động ngoài.
- Atomic update, version column, constraint và guard row có thể giảm thời gian khóa mà vẫn giữ bất biến nếu dùng đúng phạm vi.
- Chia batch giảm lock duration nhưng có thể làm mất all-or-nothing; cần checkpoint/idempotency nếu nghiệp vụ chấp nhận commit từng phần.
- Đo riêng transaction duration, lock hold time, lock wait, connection pool wait và MVCC cleanup pressure; dùng p95/p99/max để tìm đuôi dài.

Tối ưu concurrency hiệu quả bắt đầu bằng việc biết transaction nào giữ tài nguyên nào và giữ trong bao lâu. Rút ngắn transaction giúp giảm thời gian sống của snapshot, connection và các lock transaction-level; rút ngắn lock hold time giúp giải phóng tài nguyên tranh chấp sớm hơn. Hãy đưa công việc không cần nguyên tử ra ngoài transaction, nhưng giữ các thay đổi cần cùng commit trong một ranh giới rõ ràng và kiểm chứng bất biến bằng tải đồng thời.
