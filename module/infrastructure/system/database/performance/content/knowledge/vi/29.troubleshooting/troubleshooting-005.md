# Độ trễ tăng do khóa, giao dịch dài và chuỗi phiên chặn nhau

## 1. Vì sao một truy vấn nhanh vẫn có thể trả kết quả rất chậm?

Một truy vấn có thể chỉ cần vài mili giây CPU và I/O nhưng phải chờ hàng giây trước khi được phép tiếp tục. Nguyên nhân thường là một transaction khác đang giữ khóa mà truy vấn cần. Khi đó, thời gian phản hồi tăng không phải vì truy vấn tự thực hiện nhiều công việc, mà vì nó phải đợi một phiên khác nhả tài nguyên.

Trong hệ thống nhiều người dùng, các transaction đồng thời đọc và ghi cùng bảng, hàng, trang hoặc metadata. Database dùng cơ chế khóa (locking), versioning hoặc kết hợp cả hai để bảo vệ tính đúng đắn. Nếu transaction giữ khóa quá lâu, các transaction khác phải chờ. Một phiên chặn có thể khiến nhiều phiên khác xếp hàng phía sau, tạo thành **blocking chain** (chuỗi chặn). Khi hàng đợi kéo dài, connection pool cạn, request timeout và latency tăng lan rộng.

Module DATABASE_PERFORMANCE rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Khi độ trễ tăng do khóa, cần nối thời gian chờ với transaction, lock owner, truy vấn đang chạy, access path và mẫu tải. Bài học này hướng dẫn phân biệt blocking với deadlock, đọc chuỗi blocker/waiter, nhận diện transaction dài, tìm nguyên nhân gốc và xử lý an toàn.

## 2. Khóa là gì và database dùng khóa để làm gì?

Khóa là cơ chế điều phối quyền truy cập đồng thời vào tài nguyên dữ liệu. Một transaction có thể cần khóa để đọc, cập nhật, xóa hoặc thay đổi cấu trúc. Database chỉ cho phép các tổ hợp khóa tương thích cùng tồn tại; nếu hai thao tác xung đột, một thao tác phải chờ hoặc bị hủy theo chính sách của engine.

Khóa giúp bảo vệ:

- Tính toàn vẹn khi nhiều transaction sửa cùng dữ liệu.
- Thứ tự quan sát dữ liệu theo isolation level.
- Cấu trúc và metadata trong lúc DDL hoặc truy cập object.
- Các thao tác phạm vi lớn như cập nhật nhiều hàng hoặc bảo trì chỉ mục.

Không phải mọi lần đọc đều khóa hàng theo cùng cách. Một số engine dùng MVCC để reader đọc phiên bản cũ trong khi writer cập nhật phiên bản mới; nhưng vẫn có khóa metadata, khóa ghi, khóa bảo vệ cấu trúc và các xung đột nhất định giữa reader/writer. Cách hoạt động cụ thể phụ thuộc engine, isolation level và cấu hình.

### 2.1. Granularity — phạm vi khóa

Khóa có thể áp dụng ở nhiều mức:

- **Row/key lock:** khóa một hàng hoặc khóa chỉ mục đại diện cho hàng.
- **Page lock:** khóa một trang chứa nhiều hàng.
- **Table lock:** khóa toàn bảng.
- **Partition lock:** khóa một partition hoặc phần dữ liệu được phân vùng, nếu engine hỗ trợ.
- **Metadata/schema lock:** bảo vệ định nghĩa object, schema hoặc cấu trúc trong lúc DDL.
- **Database/object lock:** các khóa cấp cao hơn dùng cho thao tác quản trị hoặc nội bộ.

Granularity nhỏ giúp các transaction ít ảnh hưởng lẫn nhau nhưng cần quản lý nhiều lock hơn. Granularity lớn giảm số lượng lock nhưng có thể chặn nhiều công việc không liên quan. Một số engine có lock escalation để chuyển nhiều khóa nhỏ thành khóa lớn khi đạt điều kiện nhất định.

### 2.2. Shared lock và exclusive lock

Tên gọi và ma trận tương thích khác nhau giữa các hệ quản trị, nhưng ý tưởng phổ biến là:

- Shared/read lock cho phép nhiều reader tương thích cùng đọc một tài nguyên.
- Exclusive/write lock dành cho transaction sửa tài nguyên và thường xung đột với các lock khác.
- Update lock hoặc intent lock là các chế độ trung gian/đánh dấu ý định, giúp engine điều phối thao tác phức tạp.

Không nên tự suy ra chính xác một session sẽ lấy loại lock nào chỉ từ câu SQL. Query plan, index, isolation level, engine và các hint có thể làm thay đổi lock footprint.

### 2.3. Lock duration — thời gian giữ khóa

Khóa thường được giữ cho tới một mốc xác định như kết thúc statement, commit/rollback hoặc kết thúc một pha DDL. Với transaction tường minh, lock có thể tồn tại lâu hơn thời gian chạy câu SQL đã lấy nó.

Ví dụ, ứng dụng mở transaction, cập nhật một hàng rồi gọi dịch vụ thanh toán trong khi vẫn chưa commit. Câu UPDATE có thể hoàn tất nhanh, nhưng khóa vẫn được giữ trong suốt thời gian gọi mạng. Transaction khác cập nhật cùng hàng sẽ phải chờ.

## 3. Blocking và deadlock khác nhau thế nào?

### 3.1. Blocking — một phiên chờ phiên khác

Blocking xảy ra khi một transaction không thể tiếp tục vì tài nguyên nó cần đang bị transaction khác giữ. Phiên đang giữ khóa được gọi là **blocker**; phiên phải chờ là **waiter** hoặc blocked session.

Blocking tự nó không nhất thiết là lỗi. Một transaction cập nhật cùng hàng phải đợi transaction trước commit là hành vi bảo vệ tính đúng đắn. Vấn đề hiệu năng xuất hiện khi thời gian chờ quá dài, số waiter tăng hoặc một blocker giữ tài nguyên lâu bất thường.

### 3.2. Deadlock — vòng chờ không thể tự tháo gỡ

Deadlock xảy ra khi các transaction tạo thành một chu trình chờ nhau. Ví dụ:

1. Transaction A giữ khóa hàng X và chờ hàng Y.
2. Transaction B giữ khóa hàng Y và chờ hàng X.
3. A không thể tiếp tục nếu B chưa nhả Y; B không thể tiếp tục nếu A chưa nhả X.

Database phát hiện chu trình và chọn một transaction làm deadlock victim, rollback transaction đó để giải phóng khóa. Client nhận lỗi và có thể retry nếu thao tác được thiết kế an toàn.

### 3.3. So sánh

| Đặc điểm | Blocking | Deadlock |
|---|---|---|
| Quan hệ chờ | Một phiên hoặc nhiều phiên chờ blocker | Có chu trình chờ khép kín |
| Có thể tự kết thúc? | Có, khi blocker commit/rollback hoặc nhả khóa | Không thể tự tiến triển nếu không phá chu trình |
| Database xử lý | Thường để waiter chờ hoặc áp timeout | Phát hiện và chọn victim |
| Triệu chứng | Wait time tăng, blocked sessions tăng | Deadlock error/event, transaction bị rollback |
| Cách điều tra | Tìm blocker gốc và thời gian giữ khóa | Thu thập deadlock graph, thứ tự lock và access path |

Một hệ thống có thể có nhiều blocking chain mà không có deadlock. Ngược lại, deadlock có thể xảy ra nhanh và không tạo ra hàng đợi dài trước khi victim được chọn. Cần theo dõi cả hai.

## 4. Blocking chain — chuỗi phiên chặn nhau

Một blocker gốc có thể chặn một waiter; waiter đó lại đang giữ khóa khác và chặn thêm phiên tiếp theo. Ví dụ:

~~~text
Transaction A
  giữ khóa hàng Customer(42)
       |
       v
Transaction B
  chờ Customer(42), đồng thời giữ khóa Order(900)
       |
       v
Transaction C
  chờ Order(900)
       |
       v
Transaction D
  chờ tài nguyên do C giữ
~~~

Trong chuỗi này, B, C và D có thể đều hiện là blocked. Chỉ xử lý D không giải quyết nguyên nhân. Cần lần ngược quan hệ blocker tới phiên gốc A. Khi A commit hoặc rollback, B có thể tiếp tục, sau đó C và D lần lượt được giải phóng.

### 4.1. Head blocker

Head blocker là phiên ở đầu chuỗi, không bị một phiên khác chặn nhưng đang giữ tài nguyên khiến các phiên khác chờ. Nó có thể là:

- Một câu UPDATE/DELETE đang chạy lâu.
- Transaction mở lâu nhưng session hiện idle.
- Batch xử lý nhiều hàng trong một transaction lớn.
- DDL đang chờ hoặc giữ schema/metadata lock.
- Một phiên bị treo ở ứng dụng sau khi đã thực hiện câu SQL nhưng chưa commit.

Head blocker không nhất thiết là truy vấn tiêu thụ CPU cao nhất. Một session idle in transaction có thể dùng gần như không CPU nhưng vẫn giữ khóa.

### 4.2. Vì sao chain làm latency lan rộng?

Các request chờ khóa vẫn chiếm connection, bộ nhớ và slot thực thi. Khi nhiều request xếp hàng:

- Connection pool có thể hết connection rảnh.
- Pending borrower tăng và request timeout trước khi chạy SQL.
- Retry từ ứng dụng làm tải tăng thêm.
- Transaction giữ khóa phía sau có thể kéo dài chuỗi chặn.
- Throughput giảm dù CPU database không cao.

Vì vậy, khi latency tăng nhưng CPU thấp, lock wait và blocking chain là hướng điều tra quan trọng.

## 5. Transaction dài và vì sao thời gian giữ khóa quan trọng

### 5.1. Transaction dài không đồng nghĩa query dài

Transaction có thể gồm nhiều câu SQL ngắn nhưng kéo dài do:

- Ứng dụng gọi HTTP hoặc message broker giữa các câu SQL.
- Chờ người dùng xác nhận hoặc nhập dữ liệu.
- Xử lý file, tính toán CPU hoặc gọi dịch vụ khác trong transaction.
- Batch quá lớn và commit quá ít lần.
- Một statement chờ lock hoặc I/O trong khi transaction đã giữ các khóa trước đó.
- Connection bị giữ trong pool nhưng code không commit/rollback.

Đo riêng query duration và transaction age. Một statement chạy 20 ms trong transaction mở 40 giây vẫn có thể để khóa tồn tại gần 40 giây.

### 5.2. Idle in transaction

Idle in transaction là session đã bắt đầu transaction nhưng hiện không chạy statement, trong khi chưa commit hoặc rollback. Session có thể đang chờ ứng dụng, thread khác hoặc một thao tác ngoài database.

Tác động tùy engine và câu lệnh đã chạy:

- Có thể giữ row/table lock.
- Có thể giữ snapshot cũ và cản trở cleanup phiên bản MVCC.
- Có thể làm vacuum/purge chậm, tăng bloat hoặc undo history.
- Có thể giữ metadata lock hoặc ảnh hưởng DDL.
- Có thể ngăn log truncate/reuse trong một số tình huống.

Không phải mọi idle transaction đều giữ cùng loại khóa. Phải kiểm tra transaction age, lock list, snapshot và câu SQL trước đó.

### 5.3. Transaction read-only vẫn có thể gây ảnh hưởng

Trong MVCC, một transaction chỉ đọc có thể không giữ row lock ngăn writer cập nhật. Tuy vậy, snapshot cũ có thể khiến engine phải giữ lại phiên bản dữ liệu mà transaction đó có thể cần. Điều này có thể làm vacuum/purge không dọn được dữ liệu cũ, tăng dung lượng và chi phí đọc.

Do đó, khi thấy transaction read-only lâu, không kết luận nó vô hại chỉ vì không có row lock. Xem snapshot age, xmin hoặc version store theo engine.

## 6. Isolation level và ảnh hưởng tới khóa

Isolation level quy định các transaction được phép quan sát thay đổi đồng thời như thế nào. Nó ảnh hưởng tới loại khóa, thời gian giữ khóa hoặc việc sử dụng row versioning.

| Isolation level | Đặc điểm khái quát | Tác động cần chú ý |
|---|---|---|
| READ UNCOMMITTED | Có thể đọc dữ liệu chưa commit ở engine hỗ trợ semantics này | Giảm một số read lock nhưng có dirty read; không phải giải pháp chung cho blocking |
| READ COMMITTED | Không đọc dữ liệu chưa commit; cách lấy lock/version tùy engine | Có thể giảm thời gian shared lock hoặc dùng statement snapshot trong một số cấu hình |
| REPEATABLE READ | Dữ liệu đã đọc giữ tính ổn định trong transaction theo semantics engine | Có thể giữ lock lâu hoặc snapshot lâu hơn |
| SERIALIZABLE | Mức cô lập mạnh, ngăn thêm các anomaly như phantom theo cách engine triển khai | Có thể tăng lock contention hoặc serialization failure |
| Snapshot isolation | Đọc từ snapshot nhất quán theo transaction | Giảm một số reader-writer blocking nhưng có thể phát sinh update conflict và giữ phiên bản cũ |

Không được coi tên isolation level là một mô hình thực thi giống hệt giữa PostgreSQL, MySQL/InnoDB và SQL Server. Ví dụ, SQL Server có READ_COMMITTED_SNAPSHOT để READ COMMITTED dùng row versioning; PostgreSQL dùng MVCC cho các mức mặc định; InnoDB có consistent read và locking read với hành vi riêng.

### 6.1. Row versioning giảm một số xung đột, không xóa mọi lock

MVCC cho phép reader nhìn thấy phiên bản phù hợp với snapshot thay vì chờ writer nhả khóa trong nhiều tình huống. Nhưng writer-writer vẫn có thể xung đột; DDL vẫn cần metadata lock; locking read như SELECT FOR UPDATE vẫn chủ động lấy khóa; và transaction dài có thể giữ phiên bản cũ.

Bật row versioning không có nghĩa không còn blocking. Cần xem wait type, lock mode và version-store pressure.

### 6.2. Tăng isolation có thể làm transaction chậm hơn

Chọn isolation mạnh hơn chỉ để “an toàn” mà không hiểu workload có thể làm thời gian giữ khóa và xác suất conflict tăng. Ngược lại, hạ isolation để giảm wait có thể làm nghiệp vụ sai. Hãy mô tả invariant cần bảo vệ, chọn mức phù hợp và dùng constraint, optimistic concurrency hoặc locking có chủ đích.

## 7. Các nguyên nhân phổ biến tạo blocking

### 7.1. Cập nhật cùng một hàng nóng

Nhiều request cùng cập nhật một hàng như số lượng tồn kho, bộ đếm hoặc trạng thái tổng hợp. Dù mỗi UPDATE rất nhanh, chúng vẫn phải tuần tự hóa trên hàng đó.

Giải pháp có thể là giảm tần suất cập nhật, gom batch, chia counter theo bucket rồi tổng hợp, hoặc thay đổi mô hình dữ liệu. Không phân tán khóa nếu nghiệp vụ yêu cầu một giá trị duy nhất được cập nhật nguyên tử.

### 7.2. Thiếu index làm transaction giữ khóa lâu

UPDATE hoặc DELETE với predicate không có index phù hợp có thể quét nhiều hàng/trang. Tùy engine và isolation, phạm vi khóa có thể rộng hơn dự kiến; thời gian chạy lâu cũng kéo dài thời gian giữ khóa.

Ví dụ:

~~~sql
UPDATE orders
SET status = 'EXPIRED'
WHERE tenant_id = 17
  AND status = 'PENDING'
  AND expires_at < CURRENT_TIMESTAMP;
~~~

Nếu không có access path phù hợp, engine có thể đọc nhiều trang để tìm hàng cần cập nhật. Một index như (tenant_id, status, expires_at) có thể giảm lượng dữ liệu cần quét nếu phù hợp selectivity và workload, nhưng cũng làm tăng chi phí ghi và kích thước index. Hãy kiểm tra execution plan và actual rows trước khi thêm index.

### 7.3. Transaction bao quanh công việc ngoài database

Một transaction cập nhật hàng rồi gọi payment service hoặc gửi email trước khi commit. Khóa được giữ trong lúc chờ network, làm transaction khác phải đợi. Hãy thu hẹp transaction scope; dùng outbox hoặc workflow nếu cần phối hợp database với hệ thống ngoài.

### 7.4. Batch quá lớn

Một câu UPDATE hàng triệu bản ghi trong một transaction có thể giữ nhiều khóa, tạo log lớn và chặn truy vấn khác. Chia thành batch có kích thước hợp lý, commit theo lô và thiết kế checkpoint/idempotency để có thể tiếp tục an toàn.

Batch quá nhỏ cũng có overhead commit và round trip; cần đo để chọn kích thước cân bằng.

### 7.5. Thứ tự truy cập tài nguyên không nhất quán

Transaction A cập nhật bảng Customer rồi Order, còn transaction B cập nhật Order rồi Customer. Khi chạy đồng thời, chúng có thể tạo deadlock. Chuẩn hóa thứ tự truy cập tài nguyên giúp giảm khả năng hình thành chu trình.

### 7.6. DDL và metadata lock

ALTER TABLE, CREATE INDEX, DROP INDEX hoặc migration có thể cần schema/metadata lock. DDL có thể chờ transaction đang dùng bảng; khi DDL xếp hàng, request mới cũng có thể bị ảnh hưởng tùy engine và lock queue policy.

Trước khi chạy migration trên production, kiểm tra transaction dài, thời gian lock, online DDL support và chính sách timeout.

### 7.7. Truy vấn đọc dài và lock behavior

Ở engine dùng locking read, một truy vấn báo cáo có thể giữ shared lock trong suốt transaction và chặn writer. Ở engine dùng MVCC, truy vấn đọc dài có thể không chặn writer trực tiếp nhưng giữ snapshot cũ, tăng version retention hoặc tạo conflict với cleanup/DDL.

Xác định engine, isolation level, transaction boundary và loại wait thay vì áp dụng một kết luận chung cho mọi truy vấn đọc.

## 8. Đọc execution plan để tìm nguồn khóa rộng

Khi một DML bị chậm hoặc chặn, xem execution plan để biết engine phải tìm và sửa bao nhiêu hàng:

- Có Index Seek hay phải Table/Index Scan?
- Predicate nào được dùng để seek, predicate nào là residual filter?
- Estimated rows có lệch xa actual rows không?
- Có implicit conversion hoặc biểu thức làm predicate kém sargable không?
- Join order có tạo nhiều hàng trung gian trước khi UPDATE/DELETE không?
- Có key lookup lặp hoặc scan partition không cần thiết không?
- Statistics có phản ánh phân bố dữ liệu hiện tại không?

Một kế hoạch quét 10 triệu hàng để cập nhật 20 hàng có thể kéo dài transaction và làm lock footprint lớn. Index phù hợp, predicate sargable và statistics tốt có thể giảm thời gian thực thi cũng như thời gian giữ khóa.

Tuy nhiên, index mới có thể làm DML phải cập nhật thêm cấu trúc và làm write amplification tăng. Cần đánh giá cả read benefit lẫn write cost, không thêm index chỉ để chữa một lần blocking mà không đo workload tổng thể.

## 9. Chẩn đoán từ số liệu trước khi can thiệp

### 9.1. Xác định latency nằm ở đâu

Phân rã thời gian request:

- Chờ lấy connection từ pool.
- Thời gian gửi/nhận qua network.
- Thời gian chờ lock.
- CPU time trong database.
- I/O wait và storage latency.
- Thời gian thực thi thực tế.
- Thời gian ứng dụng xử lý sau truy vấn.

Nếu pool acquisition latency tăng nhưng database không có query tương ứng, connection có thể đang bị giữ bởi transaction lâu hoặc leak. Nếu query đã tới database và wait event là lock, cần tìm blocker. Nếu CPU cao nhưng lock wait thấp, điều tra plan, cardinality, parallelism và CPU saturation.

### 9.2. Metric nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| Lock wait count/time | Số lần và tổng thời gian chờ khóa |
| Blocked sessions | Số session đang bị chặn |
| Blocking duration | Thời gian một waiter đã chờ |
| Head blocker age | Tuổi transaction hoặc thời gian blocker giữ tài nguyên |
| Transaction age | Thời gian từ khi transaction bắt đầu |
| Deadlock count/rate | Số deadlock trong cửa sổ đo |
| Lock timeout count | Số thao tác hết thời gian chờ khóa |
| Connection pool active/pending | Mức cạn connection và hàng đợi ứng dụng |
| Query p95/p99 | Độ trễ phần đuôi của truy vấn |
| Log/undo/version store | Áp lực do transaction dài và ghi |

Theo dõi theo database, application, user, host và query fingerprint. Không chỉ xem trung bình toàn cụm; một bảng nóng hoặc một tenant có thể tạo blocker cục bộ.

### 9.3. Chụp snapshot theo thời gian

Blocking là trạng thái động. Một câu truy vấn chẩn đoán chạy sau khi blocker đã commit có thể không còn thấy nguyên nhân. Hãy ghi timestamp, session ID, transaction age, blocker relationship, SQL text phù hợp và wait duration trong lúc sự cố xảy ra.

Khi lấy hai snapshot liên tiếp, có thể xác định phiên nào tồn tại lâu, phiên nào thay đổi và queue có tăng không. Tránh ghi toàn bộ parameter chứa dữ liệu nhạy cảm vào log chẩn đoán.

## 10. PostgreSQL: tìm blocker và waiter

### 10.1. Xem session, transaction age và wait event

pg_stat_activity cho biết trạng thái backend, transaction start, query start, state change và wait event. Ví dụ:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;
~~~

Một session có state = 'idle in transaction' nhưng transaction_age lớn là ứng viên cần điều tra. wait_event_type = 'Lock' thường cho biết backend đang chờ lock; các wait khác có thể chỉ ra I/O, client hoặc hoạt động nội bộ.

### 10.2. Tìm blocker trực tiếp

PostgreSQL cung cấp pg_blocking_pids(pid) để lấy PID đang chặn một backend:

~~~sql
SELECT
    a.pid AS blocked_pid,
    a.application_name AS blocked_app,
    now() - a.query_start AS blocked_query_age,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 160) AS blocked_query
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;
~~~

Sau đó truy vấn pg_stat_activity theo các PID trong blocking_pids để xem application, transaction age, state và query gần nhất. Một blocker có thể không có query đang chạy vì nó idle in transaction.

### 10.3. Xem lock đang được giữ hoặc chờ

pg_locks hiển thị lock theo PID, lock type, mode và trạng thái granted. Có thể kết hợp với pg_stat_activity để xác định object và session:

~~~sql
SELECT
    l.pid,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    now() - a.xact_start AS transaction_age
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE l.pid IS NOT NULL
ORDER BY l.granted, a.xact_start NULLS LAST;
~~~

Không phải mọi lock row đều là row lock; PostgreSQL thường dùng tuple-level lock có thông tin liên quan trong tuple và heavyweight lock trong pg_locks. Hãy đọc tài liệu đúng phiên bản và kết hợp pg_blocking_pids thay vì diễn giải một dòng lock đơn lẻ.

### 10.4. Xử lý

Trước khi gọi pg_cancel_backend hoặc pg_terminate_backend, xác minh PID, owner, transaction age và tác động. Cancel thường yêu cầu hủy query hiện tại; terminate kết thúc session và rollback transaction. Rollback lớn có thể mất thời gian. Không kill hàng loạt session chỉ dựa vào trạng thái idle.

## 11. MySQL/InnoDB: data lock và metadata lock

### 11.1. Xem transaction đang hoạt động

information_schema.innodb_trx cung cấp thông tin transaction InnoDB:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_mysql_thread_id,
    trx_wait_started,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Transaction lâu có thể là blocker dù process list hiển thị thread đang Sleep. Hãy ánh xạ trx_mysql_thread_id với connection ID, user, host và application.

### 11.2. Xem lock wait trong Performance Schema

Trên MySQL 8, các bảng performance_schema.data_lock_waits, data_locks và threads giúp nối requesting transaction với blocking transaction. Ví dụ khái quát:

~~~sql
SELECT
    req.THREAD_ID AS waiting_thread,
    req.ENGINE_TRANSACTION_ID AS waiting_trx,
    blk.THREAD_ID AS blocking_thread,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_TYPE,
    req.LOCK_MODE AS waiting_lock_mode,
    blk.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE = w.ENGINE
 AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE = w.ENGINE
 AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Tên cột và khả năng truy cập phụ thuộc phiên bản. Các phiên bản cũ có thể dùng INFORMATION_SCHEMA.INNODB_LOCK_WAITS và INNODB_LOCKS; hãy kiểm tra đúng phiên bản.

### 11.3. Metadata lock

DDL có thể bị chặn bởi transaction đang sử dụng bảng. performance_schema.metadata_locks giúp xem metadata lock đã được cấp hoặc đang chờ nếu instrumentation phù hợp được bật. Kiểm tra DDL đang chờ, session giữ lock, tuổi transaction và object liên quan.

### 11.4. Deadlock

InnoDB có thể ghi deadlock gần nhất vào SHOW ENGINE INNODB STATUS; tùy cấu hình, deadlock information cũng có thể được ghi vào error log. Dùng thông tin này để xem hai transaction, index record, lock mode và thứ tự truy cập.

## 12. SQL Server: blocking session và lock wait

### 12.1. Tìm request đang bị chặn

sys.dm_exec_requests cung cấp blocking_session_id, wait type và thời gian chờ. Kết hợp session để tìm ứng dụng và transaction:

~~~sql
SELECT
    r.session_id,
    r.blocking_session_id,
    r.status,
    r.wait_type,
    r.wait_time,
    r.wait_resource,
    r.command,
    s.login_name,
    s.host_name,
    s.program_name,
    s.open_transaction_count,
    DB_NAME(r.database_id) AS database_name
FROM sys.dm_exec_requests AS r
JOIN sys.dm_exec_sessions AS s
  ON s.session_id = r.session_id
WHERE r.blocking_session_id <> 0
ORDER BY r.wait_time DESC;
~~~

Một số blocker có thể không còn request hoạt động và không xuất hiện trong sys.dm_exec_requests. Khi đó cần xem session sleeping nhưng có open transaction.

### 12.2. Tìm session giữ transaction mở

~~~sql
SELECT
    s.session_id,
    s.status,
    s.login_name,
    s.host_name,
    s.program_name,
    s.open_transaction_count,
    at.transaction_begin_time,
    DATEDIFF(SECOND, at.transaction_begin_time, SYSDATETIME())
        AS transaction_age_seconds
FROM sys.dm_exec_sessions AS s
LEFT JOIN sys.dm_tran_session_transactions AS st
  ON st.session_id = s.session_id
LEFT JOIN sys.dm_tran_active_transactions AS at
  ON at.transaction_id = st.transaction_id
WHERE s.is_user_process = 1
  AND s.open_transaction_count > 0
ORDER BY at.transaction_begin_time;
~~~

Session sleeping với open_transaction_count > 0 có thể đang giữ khóa. Xác định host/program/login và trao đổi với owner trước khi kết thúc session.

### 12.3. Xem lock resource

sys.dm_tran_locks hiển thị resource type, request mode, request status và owner. Kết hợp request_session_id với session/request để xem lock thuộc phiên nào. Có thể dùng sys.dm_os_waiting_tasks để nối waiter với blocker và wait resource.

### 12.4. Deadlock graph

Extended Events có thể thu thập xml_deadlock_report, chứa process list, resource list và victim. Deadlock graph cho biết transaction nào giữ resource nào và đang chờ resource nào. Dùng graph để sửa thứ tự truy cập, index và transaction scope; không chỉ tăng deadlock priority hoặc retry vô hạn.

Quyền truy cập DMV phụ thuộc phiên bản SQL Server và role, ví dụ VIEW SERVER STATE hoặc quyền tương ứng ở phiên bản mới.

## 13. Đọc wait event và wait statistics

Wait là thời gian một session chờ một sự kiện để tiếp tục. Wait type giúp phân biệt khóa với I/O, network, memory, worker hoặc scheduler. Một vài nhóm thường gặp:

- Lock waits: session chờ khóa hoặc resource synchronization.
- I/O waits: chờ đọc/ghi page hoặc log.
- Latch waits: chờ đồng bộ cấu trúc bộ nhớ nội bộ; khác với transaction lock.
- Network/client waits: server chờ client nhận hoặc gửi dữ liệu.
- Memory grant waits: truy vấn chờ cấp bộ nhớ.
- Worker/scheduler waits: thiếu worker hoặc CPU scheduler bận.

Đừng kết luận chỉ từ tên wait. Ví dụ, SQL Server LCK_M_* gợi ý lock wait; PAGEIOLATCH_* liên quan chờ page I/O; WRITELOG liên quan log flush. PostgreSQL có wait_event_type = 'Lock' cùng wait event cụ thể. MySQL Performance Schema có instrument cho lock và stage.

Wait statistics thường tích lũy từ khi server khởi động hoặc reset. Lấy delta theo cửa sổ thời gian, chuẩn hóa theo số transaction hoặc request và so sánh với baseline. Một wait có tổng thời gian lớn do hệ thống chạy lâu chưa chắc là nguyên nhân của sự cố hiện tại.

## 14. Xử lý blocker an toàn

### 14.1. Thu thập thông tin trước khi kết thúc session

Trước khi cancel/kill blocker, xác định:

1. Session ID, user, application, host và database.
2. Transaction bắt đầu lúc nào và đã giữ khóa bao lâu.
3. Query hiện tại hoặc câu lệnh gần nhất.
4. Lock/resource đang giữ và các waiter phía sau.
5. Transaction có đang ghi nhiều dữ liệu hoặc chạy batch quan trọng không.
6. Nếu rollback, ước lượng lượng công việc phải hoàn tác và tác động log/I/O.
7. Owner nghiệp vụ và khả năng retry/idempotency.

Không dùng CPU thấp làm lý do kết luận blocker vô hại; session idle có thể giữ khóa.

### 14.2. Cancel query và terminate session

Cancel query thường yêu cầu database dừng statement đang chạy; transaction có thể vẫn còn mở tùy engine và trạng thái lỗi. Ứng dụng cần rollback hoặc kết thúc transaction đúng cách.

Terminate session buộc đóng connection và thường làm transaction rollback. Rollback có thể mất thời gian tương đương hoặc lâu hơn phần công việc đã làm; trong lúc rollback, một số khóa vẫn có thể được giữ. Theo dõi trạng thái rollback thay vì cho rằng kill xong là hết blocking ngay.

### 14.3. Không kill waiter thay vì head blocker

Kill các waiter chỉ làm hủy request đang chờ và có thể khiến client retry, nhưng head blocker vẫn giữ khóa. Nếu cần giải phóng chuỗi, xử lý root blocker theo quy trình và đánh giá transaction outcome.

### 14.4. Ghi nhận và khắc phục nguyên nhân gốc

Sau khi xử lý sự cố, lưu lại blocking tree, query fingerprint, transaction age, lock resource, wait duration và thời điểm. Tìm call site ứng dụng hoặc query pattern gây transaction kéo dài. Nếu chỉ kill session mà không sửa nguyên nhân, sự cố sẽ lặp lại.

## 15. Giảm thời gian giữ khóa

### 15.1. Thu hẹp transaction scope

Chỉ đưa các thao tác cần atomicity vào transaction. Tránh giữ transaction trong khi:

- Gọi HTTP, payment gateway hoặc message broker.
- Chờ người dùng hoặc queue.
- Đọc/ghi file, object storage hoặc stream chậm.
- Thực hiện tính toán CPU dài không cần database.
- Chờ một task bất đồng bộ không có deadline.

Nếu cần phát sự kiện sau commit, transactional outbox có thể ghi event record trong cùng transaction; worker publish sau đó. Nếu workflow qua nhiều hệ thống, dùng saga/state machine hoặc cơ chế bù trừ thay vì giữ transaction database xuyên suốt.

### 15.2. Commit theo batch hợp lý

Với thao tác cập nhật hàng loạt, chia thành batch theo khóa ổn định:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE id > :last_id
  AND id <= :next_id
  AND status = 'COMPLETED';
~~~

Mỗi batch có thể commit riêng, cập nhật checkpoint last_id và chạy lại an toàn. Cần xác định điều kiện để không bỏ sót hàng thay đổi đồng thời, dùng keyset/range phù hợp và idempotent. Kích thước batch phải được benchmark vì batch quá lớn giữ khóa lâu, batch quá nhỏ tăng round trip và commit overhead.

### 15.3. Tối ưu access path cho DML

Index phù hợp có thể giúp UPDATE/DELETE tìm đúng hàng nhanh hơn, giảm số trang đọc và thời gian giữ khóa. Predicate nên sargable, tránh chuyển kiểu ngầm hoặc áp hàm lên cột nếu làm mất khả năng seek.

Trước khi thêm index:

- Xem execution plan và actual rows.
- Kiểm tra selectivity và thứ tự cột index.
- Xem index hiện có có thể đáp ứng predicate không.
- Đánh giá write amplification và dung lượng.
- Đo lock wait, logical reads và elapsed time trước/sau.

### 15.4. Chuẩn hóa thứ tự truy cập

Nếu nhiều transaction cập nhật cùng tập bảng/hàng, truy cập chúng theo thứ tự nhất quán giúp giảm deadlock. Ví dụ, tất cả transaction cập nhật Customer trước Order, thay vì mỗi code path chọn thứ tự khác nhau.

Khi cập nhật nhiều hàng, sắp xếp theo khóa ổn định có thể giảm xác suất hai transaction lấy khóa theo thứ tự ngược. Tuy nhiên, execution plan và engine có thể thay đổi thứ tự thực thi; xác minh bằng deadlock graph và workload thực.

### 15.5. Optimistic concurrency

Với dữ liệu ít xung đột, có thể dùng version column để phát hiện cập nhật đồng thời:

~~~sql
UPDATE products
SET price = :new_price,
    version = version + 1
WHERE product_id = :id
  AND version = :expected_version;
~~~

Nếu số hàng cập nhật bằng 0, version đã thay đổi hoặc bản ghi không còn tồn tại; ứng dụng cần đọc lại và xử lý conflict. Cách này giảm nhu cầu giữ lock qua nhiều bước ở tầng ứng dụng, nhưng câu UPDATE vẫn cần khóa trong lúc thực thi. Nó không thay thế transaction cho invariant nhiều hàng.

### 15.6. Pessimistic locking có chủ đích

Với thao tác cần độc quyền, dùng locking read như SELECT ... FOR UPDATE hoặc cú pháp tương đương có thể giúp bảo vệ invariant. Nhưng khóa phải được giữ trong transaction ngắn, chỉ khóa hàng cần thiết và có timeout phù hợp.

Không dùng FOR UPDATE cho mọi truy vấn đọc. Chỉ dùng khi nghiệp vụ cần khóa trước khi quyết định cập nhật và đã hiểu lock scope, index access path và thứ tự truy cập.

## 16. Timeout và retry

### 16.1. Lock timeout

Lock timeout giới hạn thời gian một thao tác chờ khóa. Nó giúp request không chờ vô hạn, nhưng không tự giải quyết blocker. Khi timeout, transaction có thể ở trạng thái cần rollback tùy engine; ứng dụng phải xử lý rõ.

### 16.2. Statement timeout và transaction deadline

Statement timeout giới hạn thời gian câu lệnh chạy; transaction deadline giới hạn tổng thời gian transaction. Hai giới hạn này khác lock timeout. Một statement có thể chạy lâu do CPU/I/O mà không chờ lock; ngược lại, statement có thể chờ lock gần hết thời gian dù công việc thực tế rất nhỏ.

### 16.3. Retry có kiểm soát

Retry có thể phù hợp với deadlock victim hoặc transient lock timeout nếu thao tác có thể chạy lại an toàn. Dùng:

- Giới hạn số lần retry.
- Exponential backoff và jitter.
- Idempotency key hoặc optimistic version check.
- Deadline tổng của request.
- Metric retry count và retry success.

Không retry ngay lập tức với tốc độ cao; các transaction có thể tiếp tục va chạm và tạo retry storm. Không retry thao tác không idempotent nếu chưa xác định transaction trước đã commit hay rollback.

## 17. Deadlock: thu thập graph và sửa thứ tự khóa

### 17.1. Đọc deadlock graph

Deadlock graph thường cho biết:

- Các transaction/process tham gia.
- Resource mà mỗi transaction đang giữ.
- Resource mỗi transaction đang chờ.
- Lock mode và index/table liên quan.
- Câu SQL hoặc execution stack tại thời điểm deadlock.
- Transaction được chọn làm victim.

Từ graph, dựng lại thứ tự truy cập. Nếu A giữ Customer rồi chờ Order, B giữ Order rồi chờ Customer, cần chuẩn hóa thứ tự hoặc giảm phạm vi transaction.

### 17.2. Deadlock retry không phải cách chữa duy nhất

Retry victim giúp request phục hồi tạm thời nhưng không làm deadlock biến mất. Nếu tần suất cao, cần sửa query/index/transaction order. Theo dõi deadlock rate theo query fingerprint và thời gian, không chỉ tổng số từ lúc server khởi động.

### 17.3. Phân biệt deadlock với lock timeout

Deadlock detector tìm chu trình và chủ động chọn victim. Lock timeout xảy ra khi waiter vượt ngưỡng chờ; không nhất thiết có chu trình. Hai lỗi có cách điều tra khác nhau và không nên gom thành một metric chung.

## 18. Ví dụ tình huống: một transaction idle chặn nhiều request

Một API cập nhật trạng thái đơn hàng và ghi lịch sử trong transaction. Sau khi cập nhật hàng orders, code gọi dịch vụ vận chuyển để lấy mã vận đơn rồi mới insert lịch sử và commit. Dịch vụ ngoài đôi lúc mất 8 giây.

Trong lúc đó:

- Transaction A giữ khóa hàng orders trong khoảng gọi mạng.
- Request B muốn cập nhật cùng đơn hàng nên chờ A.
- Request C muốn đọc bằng locking read hoặc cập nhật trạng thái liên quan nên chờ B hoặc A.
- Connection pool tăng active và pending.
- P99 API tăng dù CPU database không cao.

### 18.1. Cách xác minh

1. Lấy snapshot blocker/waiter và transaction age.
2. Xác định session gốc thuộc API nào qua application name/host.
3. Kiểm tra câu SQL gần nhất và lock resource.
4. Đối chiếu trace ứng dụng để thấy thời gian gọi dịch vụ vận chuyển.
5. So sánh query duration với transaction duration.

### 18.2. Cách sửa

Tách thao tác lấy mã vận đơn ra khỏi transaction giữ khóa. Có thể commit đơn hàng ở trạng thái PENDING_SHIPMENT cùng outbox event; worker gọi dịch vụ vận chuyển rồi cập nhật trạng thái trong transaction ngắn khác. Thiết kế cần idempotency và trạng thái nghiệp vụ để xử lý retry hoặc lỗi ngoài hệ thống.

Sau sửa, đo lại transaction age, lock wait, blocked sessions, pool pending và p99. Nếu lock wait giảm nhưng query CPU tăng, cần tiếp tục xem execution plan; một thay đổi có thể chuyển nút thắt sang tài nguyên khác.

## 19. Ví dụ tình huống: UPDATE quét quá nhiều hàng

Một job đánh dấu bản ghi hết hạn chạy:

~~~sql
UPDATE sessions
SET state = 'EXPIRED'
WHERE state = 'ACTIVE'
  AND expires_at < CURRENT_TIMESTAMP;
~~~

Nếu bảng lớn và thiếu index phù hợp, database có thể scan nhiều trang, cập nhật nhiều hàng trong một transaction. Các request tạo hoặc gia hạn session bị chặn ở những hàng/trang liên quan; log tăng và transaction kéo dài.

Quy trình:

1. Xem actual execution plan, số hàng đọc và số hàng cập nhật.
2. Xem tỷ lệ ACTIVE và phân bố expires_at.
3. Đánh giá index phù hợp, ví dụ index có cột state và expires_at theo selectivity.
4. Thử batch theo khóa hoặc theo partition/time range.
5. Commit từng batch và ghi checkpoint để tiếp tục sau lỗi.
6. Giám sát lock wait, log generation, I/O và latency của request trực tuyến.

Index có thể giảm số hàng phải đọc nhưng tăng chi phí cho INSERT/UPDATE trên bảng. Chạy thử trên dữ liệu gần production và đo workload đọc/ghi tổng thể trước khi triển khai.

## 20. Quy trình điều tra độ trễ do khóa

1. **Xác nhận triệu chứng:** latency p95/p99, timeout, pool wait, blocked session hoặc deadlock tăng ở thời điểm nào.
2. **Phân loại wait:** lock, I/O, CPU, memory, latch hay network/client.
3. **Lấy blocking tree:** xác định waiter, blocker trực tiếp và head blocker.
4. **Đo tuổi transaction:** so sánh transaction age, query age và thời gian giữ khóa.
5. **Nhận diện owner:** application, user, host, job hoặc migration nào tạo blocker.
6. **Đọc SQL và plan:** predicate, index, actual rows, scan, lookup và lock scope.
7. **Đánh giá isolation:** locking read, MVCC snapshot, metadata lock và row versioning.
8. **Đánh giá tác động:** số waiter, connection pool, log/undo/version store, replication và SLO.
9. **Xử lý có kiểm soát:** chờ, cancel, rollback hoặc terminate theo owner và runbook; theo dõi rollback.
10. **Sửa nguyên nhân:** thu hẹp transaction, tối ưu access path, batch, thứ tự truy cập, timeout hoặc concurrency.
11. **Kiểm thử lại:** tải đồng thời, deadlock, timeout, exception và retry.
12. **Xác nhận:** lock wait p95/p99, transaction age, blocked sessions, throughput và latency trở về mục tiêu.

## 21. Các lỗi thường gặp khi xử lý blocking

- **Chỉ nhìn query đang chạy:** blocker có thể idle in transaction và không có request active.
- **Kill waiter:** giải phóng một request nhưng head blocker vẫn còn.
- **Nhầm blocking với deadlock:** blocking có thể tự hết khi transaction kết thúc; deadlock cần phá chu trình.
- **Chỉ tăng lock timeout:** request chờ lâu hơn, làm connection bị giữ lâu hơn.
- **Hạ isolation tùy tiện:** giảm wait nhưng có thể gây dirty read hoặc lỗi nghiệp vụ.
- **Bật row versioning rồi cho rằng hết blocking:** writer, DDL, locking read và snapshot retention vẫn có thể gây vấn đề.
- **Thêm index không xem write cost:** đọc nhanh hơn nhưng ghi chậm hơn, log và storage tăng.
- **Chạy UPDATE lớn trong một transaction:** giữ nhiều khóa, log tăng và rollback đắt.
- **Gọi API ngoài trong transaction:** giữ lock trong thời gian network không xác định.
- **Retry không backoff:** tạo thêm tải và lặp lại xung đột.
- **Kill blocker mà không xem rollback:** rollback lớn có thể tiếp tục giữ tài nguyên và I/O.
- **Chỉ xem wait statistics tích lũy:** bỏ qua delta và cửa sổ xảy ra sự cố.
- **Không lưu deadlock graph:** mất bằng chứng về thứ tự lấy khóa.
- **Không kiểm tra metadata lock:** DDL có thể gây hàng đợi dù query DML không bất thường.
- **Không đo lại sau sửa:** không biết blocking đã giảm hay nút thắt chuyển sang CPU/I/O.

## 22. Checklist phòng ngừa và vận hành

### Thiết kế ứng dụng

- [ ] Transaction chỉ bao gồm các thao tác database cần atomicity.
- [ ] Không chờ HTTP, người dùng hoặc message broker trong transaction.
- [ ] Mọi đường code đều commit/rollback và đóng tài nguyên.
- [ ] Batch có kích thước phù hợp và checkpoint/idempotency.
- [ ] Các transaction cập nhật cùng tài nguyên có thứ tự truy cập nhất quán.
- [ ] Retry có giới hạn, backoff và xử lý transaction outcome rõ ràng.

### Thiết kế database

- [ ] UPDATE/DELETE có access path phù hợp với predicate.
- [ ] Statistics phản ánh phân bố dữ liệu và cardinality.
- [ ] Index mới được đánh giá cả read benefit lẫn write cost.
- [ ] Isolation level phù hợp invariant nghiệp vụ.
- [ ] Locking read chỉ dùng khi có yêu cầu rõ ràng.
- [ ] DDL có kế hoạch metadata lock và maintenance window.

### Giám sát

- [ ] Có metric lock wait, blocked sessions, blocker age và transaction age.
- [ ] Có deadlock graph/event và lock timeout count.
- [ ] Có pool active/idle/pending và acquisition latency.
- [ ] Có log/undo/version store và replication lag khi liên quan.
- [ ] Có query fingerprint và tracing để nối database session với code.
- [ ] Có cảnh báo theo SLO và cửa sổ đo, không chỉ dựa vào tổng tích lũy.

## 23. Bài tập tự kiểm tra

**Bài 1.** CPU database thấp nhưng API p99 tăng, pending connection tăng và nhiều query có lock wait. Bạn tìm thông tin nào trước?

*Gợi ý:* Blocking tree, head blocker, transaction age, query gần nhất, lock resource, application/host và số waiter. CPU thấp không loại trừ blocker idle.

**Bài 2.** Một session không chạy query trong 30 giây nhưng đang idle in transaction. Vì sao vẫn có thể chặn UPDATE khác?

*Gợi ý:* Nó có thể giữ khóa đã lấy từ statement trước và chưa commit/rollback. Kiểm tra lock list và transaction age.

**Bài 3.** Hai transaction lần lượt cập nhật Customer rồi Order và Order rồi Customer. Hiện tượng nào có thể xảy ra và cách giảm?

*Gợi ý:* Deadlock do thứ tự khóa ngược. Chuẩn hóa thứ tự truy cập, thu hẹp transaction và retry victim có backoff.

**Bài 4.** Một UPDATE quét 5 triệu hàng nhưng chỉ sửa 100 hàng. Điều gì có thể giúp giảm blocking?

*Gợi ý:* Xem actual plan và predicate; tạo index phù hợp nếu có lợi, cải thiện statistics, chia batch và giảm transaction scope.

**Bài 5.** Vì sao tăng lock timeout từ 5 giây lên 60 giây có thể làm sự cố nặng hơn?

*Gợi ý:* Waiter giữ connection lâu hơn, pool cạn nhanh hơn và request tích tụ. Timeout chỉ giới hạn chờ, không sửa blocker.

**Bài 6.** Sau khi terminate blocker, lock vẫn chưa được giải phóng ngay. Nguyên nhân có thể là gì?

*Gợi ý:* Database đang rollback transaction lớn; rollback có thể mất thời gian và vẫn cần tài nguyên/lock cho tới khi hoàn tất.

**Bài 7.** Khi dùng MVCC, transaction read-only lâu có thể gây ảnh hưởng gì dù không chặn writer trực tiếp?

*Gợi ý:* Snapshot cũ có thể giữ phiên bản dữ liệu, cản vacuum/purge hoặc làm version store tăng.

## 24. Ghi nhớ khi tối ưu

Blocking là một phiên phải chờ khóa do phiên khác giữ; deadlock là chu trình chờ không thể tự tiến triển và database thường chọn một transaction làm victim. Blocking chain có thể lan từ một head blocker tới nhiều request, làm connection pool cạn và p99 tăng dù CPU không cao.

Điều tra cần tìm waiter, blocker gốc, lock resource, transaction age, query age, application owner và execution plan. Transaction dài có thể đến từ query chậm, batch lớn, gọi dịch vụ ngoài hoặc session idle in transaction. MVCC giảm một số reader-writer blocking nhưng không loại bỏ writer conflict, metadata lock, snapshot retention hay mọi loại wait.

Giảm thời gian giữ khóa bằng transaction scope ngắn, access path phù hợp, batch có kiểm soát, thứ tự truy cập nhất quán và timeout/retry có giới hạn. Khi xử lý sự cố, xác minh blocker và tác động rollback trước khi cancel/terminate. Đo lại lock wait, transaction age, blocked sessions, throughput và latency để xác nhận nguyên nhân đã được khắc phục.
