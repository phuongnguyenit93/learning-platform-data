# Quy trình xử lý sự cố từ bằng chứng đến nguyên nhân và xác minh bản sửa

Sự cố concurrency thường xuất hiện dưới dạng triệu chứng dễ thấy nhưng nguyên nhân nằm sâu hơn trong cách ứng dụng và database phối hợp. Người dùng có thể báo đơn hàng bị từ chối ngẫu nhiên, API tăng độ trễ, tồn kho âm, transaction bị rollback hoặc worker xử lý một message nhiều lần. Một log lỗi đơn lẻ hiếm khi đủ để kết luận.

Quy trình điều tra đáng tin cậy phải đi từ **bằng chứng quan sát được** đến **chuỗi nguyên nhân có thể giải thích sự cố**, rồi kiểm chứng bản sửa bằng một thí nghiệm tái hiện và dữ liệu sau triển khai. Mục tiêu không chỉ là làm lỗi biến mất trong vài phút. Cần chứng minh thay đổi đã xử lý đúng cơ chế gây lỗi, vẫn bảo vệ bất biến nghiệp vụ và không tạo ra một vấn đề mới ở đường xử lý khác.

Bài này trình bày quy trình thực hành cho sự cố transaction, lock contention, deadlock, isolation anomaly, retry storm và các lỗi liên quan đến xử lý đồng thời.

## 1. Phân biệt triệu chứng, sự kiện kích hoạt và nguyên nhân

Một sự cố thường có nhiều lớp:

- **Triệu chứng (symptom)**: điều người dùng hoặc hệ thống nhìn thấy, ví dụ request timeout, lỗi 1205, số lượng tồn kho sai.
- **Sự kiện kích hoạt (trigger)**: điều xảy ra ngay trước khi sự cố xuất hiện, ví dụ một batch job bắt đầu chạy hoặc lượng request tăng đột ngột.
- **Cơ chế lỗi (failure mechanism)**: cách hệ thống đi đến trạng thái lỗi, ví dụ hai transaction khóa chéo, hai client ghi đè cùng giá trị cũ hoặc retry làm tăng tải.
- **Nguyên nhân trực tiếp (proximate cause)**: điều kiện cụ thể tạo ra lỗi trong lần xảy ra đó, ví dụ transaction A giữ key lock trên index X rồi chờ key lock trên index Y.
- **Nguyên nhân gốc (root cause)**: điểm thiết kế, cấu hình, quy trình hoặc thiếu kiểm soát khiến cơ chế lỗi có thể xảy ra, ví dụ hai luồng nghiệp vụ lấy khóa theo thứ tự ngược nhau và không có test concurrency bao phủ lịch này.
- **Yếu tố góp phần (contributing factor)**: điều làm sự cố nghiêm trọng hơn, ví dụ transaction giữ khóa trong lúc gọi HTTP hoặc index thiếu khiến phạm vi scan rộng.

Không nên gọi thông báo lỗi cuối cùng là root cause. Error 1205 cho biết SQL Server đã chọn transaction làm deadlock victim; nó chưa giải thích tại sao chu trình chờ hình thành. HTTP 504 cho biết caller không nhận được phản hồi đúng hạn; nó chưa chứng minh database là nguyên nhân. Một query chạy lâu có thể đang chờ khóa, chờ I/O hoặc tiêu tốn CPU.

### Ví dụ chuỗi nguyên nhân

~~~text
Batch đối soát bắt đầu
        |
        v
Batch khóa account theo thứ tự account_id giảm dần
        |
        +-------------------------------+
        |                               |
API chuyển tiền khóa account tăng dần   |
        |                               |
        v                               v
API giữ account 10, chờ 20       Batch giữ account 20, chờ 10
        |                               |
        +---------------+---------------+
                        |
                        v
                  Deadlock cycle
                        |
                        v
              DBMS chọn một victim
                        |
                        v
          Ứng dụng retry không có jitter
                        |
                        v
             Tải database tăng thêm
~~~

Trong ví dụ này, thứ tự khóa khác nhau là cơ chế trực tiếp tạo deadlock. Retry đồng loạt là yếu tố làm sự cố lan rộng. Chỉ tăng deadlock timeout hoặc connection pool không sửa được nguyên nhân.

## 2. Bắt đầu bằng phạm vi ảnh hưởng và mốc thời gian

Trước khi phân tích SQL, xác định sự cố đang ảnh hưởng đến đâu.

Các câu hỏi đầu tiên:

- Người dùng, tenant, endpoint hoặc loại giao dịch nào bị ảnh hưởng?
- Bắt đầu lúc nào và kéo dài bao lâu?
- Tỷ lệ lỗi tăng ở tất cả request hay chỉ một nhóm request?
- Sự cố chỉ xảy ra ở một database, một node, một partition hay một vùng triển khai?
- Có mất dữ liệu, sai dữ liệu, xử lý trùng hoặc chỉ tăng độ trễ?
- Có thay đổi gần thời điểm bắt đầu như deploy, migration, index, cấu hình isolation, lịch batch, traffic hoặc hạ tầng?
- Sự cố còn đang diễn ra hay đã tự hết?

Phân biệt phạm vi ảnh hưởng với số lượng log. Một service có thể ghi hàng nghìn lỗi retry cho một vài giao dịch nghiệp vụ; một lỗi invariant hiếm gặp có thể chỉ xuất hiện một lần nhưng có tác động rất lớn.

### Dựng timeline

Ghi các mốc có thể xác nhận:

| Thời điểm | Sự kiện | Nguồn bằng chứng |
|---|---|---|
| T0 | Bắt đầu deploy hoặc batch | Deployment log / scheduler |
| T1 | Request latency tăng | Metrics / tracing |
| T2 | Lock wait hoặc deadlock tăng | Database monitoring |
| T3 | Retry rate tăng | Application metrics |
| T4 | Bật mitigation hoặc giảm traffic | Incident log |
| T5 | Bản sửa được triển khai | Deployment record |
| T6 | Latency và lỗi trở về mức bình thường | Metrics sau triển khai |

Dùng timestamp từ các nguồn có thể lệch đồng hồ. Cần ghi rõ timezone, nguồn thời gian và sai lệch ước tính giữa app host, database và broker. Với trace trong cùng một process, thứ tự sự kiện hoặc span parent-child thường đáng tin hơn việc so sánh timestamp giữa hai máy chưa đồng bộ.

Không chỉ ghi giờ bắt đầu và kết thúc. Cần giữ các mốc transaction bắt đầu, câu lệnh gửi, thời điểm bắt đầu chờ, commit/rollback và retry.

## 3. Thu thập bằng chứng trước khi thay đổi trạng thái hệ thống

Khi incident đang diễn ra, các hành động như restart service, kill session, xóa queue, chạy lại batch hoặc thay isolation level có thể làm mất dấu vết quan trọng. Nếu cần mitigation ngay để bảo vệ dữ liệu hoặc khôi phục dịch vụ, hãy ghi nhận bằng chứng tối thiểu trước khi thực hiện khi điều kiện cho phép.

Bộ bằng chứng thường cần:

- Request ID, correlation ID, trace ID và tenant/resource ID đã được làm sạch dữ liệu nhạy cảm.
- Endpoint, operation hoặc message type.
- Application instance, worker ID và database session ID.
- SQLSTATE, vendor error code và exception chain.
- SQL statement hoặc query fingerprint, parameter metadata an toàn.
- Transaction start time, duration, isolation level và trạng thái commit/rollback.
- Blocking session, waiter, lock mode và lock resource.
- Deadlock graph hoặc deadlock report.
- Execution plan và thống kê truy vấn khi liên quan.
- Database CPU, I/O, memory, connection pool, tempdb/version store và queue depth.
- Deployment, schema migration, index/statistics change và cấu hình gần thời điểm sự cố.

### Bằng chứng trực tiếp và bằng chứng gián tiếp

| Bằng chứng | Có thể chứng minh | Không tự chứng minh |
|---|---|---|
| Deadlock graph | Các session, resource và cạnh chờ trong deadlock được ghi nhận | Vì sao ứng dụng chọn thứ tự truy cập đó |
| Blocking chain | Session nào đang chặn session nào tại thời điểm lấy mẫu | Toàn bộ nguyên nhân nếu blocker đã kết thúc |
| SQL error code | Loại lỗi DBMS trả về | Nguyên nhân thiết kế hoặc tác động dữ liệu cuối |
| Query plan | Access path, operator và ước lượng/actual rows tùy loại plan | Plan đó chắc chắn đã được dùng trong mọi lần lỗi |
| Application trace | Luồng gọi, thời gian và operation liên quan | Trạng thái lock chính xác nếu không có liên kết DB |
| Metrics CPU/I/O | Tải và xu hướng tài nguyên | Một query cụ thể gây tải nếu thiếu tương quan |
| Deployment diff | Thay đổi gần thời điểm xảy ra | Thay đổi đó là nguyên nhân nếu chưa có bằng chứng cơ chế |

Ghi lại nguồn, thời điểm thu thập, môi trường, phiên bản DBMS và query dùng để lấy dữ liệu. Nếu chỉ có ảnh chụp màn hình, giữ thêm dữ liệu gốc hoặc export có thể tìm kiếm được khi có thể.

Không thu thập payload, token, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết. Dùng query fingerprint, ID đã mã hóa/ẩn danh và metadata vừa đủ để điều tra.

## 4. Nhận diện đúng loại sự cố trước khi đặt giả thuyết

Các lỗi concurrency có thể có biểu hiện gần giống nhau nhưng cần cách xử lý khác nhau.

| Dấu hiệu | Nhóm vấn đề | Bằng chứng cần tìm |
|---|---|---|
| Một request chờ session khác rồi tiếp tục | Lock blocking | Blocking chain, lock holder, transaction age |
| Hai hoặc nhiều session tạo vòng chờ | Deadlock | Deadlock graph, lock mode, thứ tự resource |
| Transaction bị hủy do serialization | Serialization conflict | SQLSTATE/error code, isolation level, snapshot history |
| UPDATE không ảnh hưởng hàng nào | Optimistic conflict hoặc điều kiện không còn đúng | Version token, WHERE predicate, row count |
| Query chậm nhưng không có lock wait | CPU/I/O/plan issue | Actual plan, wait stats, reads, CPU |
| Connection pool cạn | Pool starvation hoặc connection bị giữ lâu | Active/idle/pending connection, transaction duration |
| Retry tăng theo cấp số nhân | Retry storm hoặc dependency failure | Attempt count, delay, retry budget, dependency errors |
| Dữ liệu bị áp dụng hai lần | Duplicate delivery hoặc operation không idempotent | Event ID, inbox/outbox, idempotency key, audit trail |

### Blocking không phải deadlock

Blocking là một session chờ khóa do session khác đang giữ. Nếu blocker commit hoặc rollback, waiter có thể tiếp tục.

Deadlock là chu trình chờ. DBMS thường phát hiện và phá chu trình bằng cách hủy một transaction. Vì vậy, một request nhận deadlock error có thể kết thúc nhanh; một request bị blocking có thể chờ rất lâu mà không có deadlock.

### Lock timeout không phải deadlock

Lock timeout xảy ra khi thời gian chờ vượt cấu hình. Nó không nhất thiết có chu trình chờ. Tăng timeout chỉ cho phép chờ lâu hơn và có thể làm request giữ tài nguyên lâu hơn. Cần tìm blocker, transaction age và lý do khóa được giữ.

### Serialization failure không nhất thiết có blocking

Một DBMS có thể hủy transaction vì lịch đọc/ghi không thể được xem như tuần tự hợp lệ. Transaction có thể nhận lỗi dù không có chuỗi lock wait dài. Cần đọc mã lỗi, isolation level và logic retry.

### Query chậm không đồng nghĩa lock contention

Nếu query tiêu tốn CPU hoặc I/O, tăng lock timeout hay thêm UPDLOCK không giải quyết vấn đề. Hãy phân tích execution plan, cardinality, index, logical reads và wait category.

## 5. Dựng blocking chain và wait-for graph

Khi thấy một request đang chờ, xác định:

1. Session nào là waiter?
2. Session nào đang block?
3. Lock resource nào bị tranh chấp?
4. Blocker đang chạy câu SQL nào?
5. Transaction của blocker bắt đầu từ lúc nào?
6. Blocker đang chờ một tài nguyên khác hay đang thực thi bình thường?
7. Chuỗi có kết thúc ở một root blocker hay tạo thành chu trình?

Ví dụ blocking chain:

~~~text
Session C chờ B
       |
       v
Session B chờ A
       |
       v
Session A đang giữ X lock
       |
       v
Root blocker: transaction A
~~~

Root blocker là session ở đầu chuỗi hiện tại đang giữ tài nguyên khiến những session khác chờ. Nó chưa chắc là root cause của incident. Ví dụ A có thể là một batch hợp lệ nhưng giữ transaction lâu do gọi dịch vụ ngoài; thiết kế transaction rộng mới là nguyên nhân hệ thống.

Wait-for graph có chu trình:

~~~text
A -> B -> C
^         |
|_________|
~~~

Đây là deadlock. Nếu không có chu trình, điều tra blocking và transaction duration thay vì gọi nó là deadlock.

### Quan sát PostgreSQL

Truy vấn sau cho biết các session đang chờ lock và session chặn chúng:

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.application_name AS waiting_app,
    a.state AS waiting_state,
    a.wait_event_type,
    a.wait_event,
    a.query AS waiting_query,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.xact_start AS waiting_xact_start
FROM pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock';
~~~

Để xem thông tin lock cụ thể, có thể kết hợp pg_locks với pg_stat_activity. Việc ghép các lock cần cẩn thận vì một lock có thể là relation, tuple, transaction ID hoặc loại tài nguyên khác. Không nên giả định mọi lock đều có một row id trực tiếp.

### Quan sát SQL Server

Ví dụ xem request, thời gian chờ và blocker:

~~~sql
SELECT
    session_id,
    status,
    command,
    wait_type,
    wait_time,
    blocking_session_id,
    transaction_isolation_level
FROM sys.dm_exec_requests
WHERE session_id <> @@SPID;
~~~

Có thể ghép với sys.dm_tran_locks, sys.dm_exec_sessions và sys.dm_exec_sql_text để biết lock resource, login/application và câu lệnh. Deadlock graph từ Extended Events thường hữu ích hơn một snapshot blocking đơn lẻ.

### Quan sát MySQL InnoDB

Trên các phiên bản hỗ trợ Performance Schema data lock tables, có thể xem waiter và blocker qua data_lock_waits:

~~~sql
SELECT
    waiting.ENGINE_TRANSACTION_ID AS waiting_trx,
    waiting.THREAD_ID AS waiting_thread,
    waiting.OBJECT_SCHEMA,
    waiting.OBJECT_NAME,
    waiting.INDEX_NAME,
    waiting.LOCK_TYPE AS waiting_lock_type,
    waiting.LOCK_MODE AS waiting_lock_mode,
    blocking.ENGINE_TRANSACTION_ID AS blocking_trx,
    blocking.THREAD_ID AS blocking_thread,
    blocking.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS waiting
  ON waits.REQUESTING_ENGINE_LOCK_ID = waiting.ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON waits.BLOCKING_ENGINE_LOCK_ID = blocking.ENGINE_LOCK_ID;
~~~

Tên cột và quyền xem phụ thuộc phiên bản MySQL. Có thể dùng thêm information_schema.innodb_trx hoặc sys schema view phù hợp để liên kết transaction với thread/query.

Các truy vấn trên là công cụ điều tra, không phải bằng chứng lịch sử. Nếu blocker đã commit trước khi truy vấn chạy, snapshot hiện tại không còn thấy nó. Cần bật log/sampling phù hợp để giữ bằng chứng khi sự cố tái diễn.

## 6. Đọc deadlock graph thay vì chỉ nhìn error code

Deadlock report thường chứa:

- Danh sách process/session tham gia.
- Transaction và câu lệnh đang chạy.
- Resource bị tranh chấp.
- Lock mode đang giữ và lock mode đang yêu cầu.
- Wait-for relationship.
- Transaction được chọn làm victim.
- Một số thông tin về execution context và index.

Cách đọc:

1. Xác định victim và các transaction còn lại.
2. Với mỗi process, đọc câu lệnh đang chạy và resource đang giữ.
3. Đọc lock mode đang yêu cầu.
4. Nối cạnh chờ để thấy chu trình.
5. Xác định thứ tự truy cập resource của từng transaction.
6. Kiểm tra trigger, foreign key, index maintenance hoặc stored procedure có tạo thêm thao tác khóa gián tiếp không.
7. So sánh các câu lệnh trong graph với code path và trace ứng dụng.

Ví dụ:

~~~text
Transaction A:
  giữ X trên key Account(10)
  yêu cầu X trên key Account(20)

Transaction B:
  giữ X trên key Account(20)
  yêu cầu X trên key Account(10)
~~~

Điều này hỗ trợ giả thuyết về thứ tự khóa ngược nhau. Để xác nhận root cause, cần tìm code path của A/B và chứng minh chúng có thể chạy đồng thời với thứ tự đó.

Deadlock graph chỉ ghi một lần xảy ra. Nếu nhiều graph có cùng resource và cùng pattern, bằng chứng cho một cơ chế lặp lại mạnh hơn. Nếu graph khác nhau, có thể có nhiều nguyên nhân đồng thời.

## 7. Điều tra transaction giữ khóa quá lâu

Một transaction có thể là root blocker dù câu SQL đang chạy đã kết thúc. Ví dụ, ứng dụng đọc một hàng, cập nhật một hàng rồi gọi HTTP trước khi commit. DBMS vẫn giữ transaction và lock trong lúc ứng dụng chờ mạng.

Tìm:

- Transaction start time và transaction age.
- Session đang active, sleeping hoặc idle in transaction.
- Câu SQL gần nhất và câu SQL đang chạy.
- Application name, worker ID, request ID.
- Thời gian connection được mượn từ pool.
- Span HTTP/message/queue nằm giữa begin và commit.
- Các exception bị bắt khiến transaction không kết thúc như dự kiến.

Phân biệt query duration với transaction duration. Một câu UPDATE có thể mất 10 ms, nhưng transaction giữ khóa 15 giây vì ứng dụng thực hiện thêm công việc sau đó.

### Dấu hiệu transaction quá rộng

~~~text
BEGIN
  SELECT/UPDATE dữ liệu
  Gọi payment provider (3 giây)
  Chờ message broker (2 giây)
  Tạo audit record
COMMIT
~~~

Các thao tác network không thuộc transaction database. Chúng làm connection và lock bị giữ lâu. Tách external side effect qua outbox/worker thường giảm thời gian giữ khóa.

## 8. Điều tra query plan và index khi phạm vi khóa lớn

Một truy vấn tưởng như cập nhật một vài hàng có thể quét rất nhiều key hoặc row nếu thiếu index phù hợp hoặc cardinality estimate sai.

Thu thập:

- Actual execution plan khi có thể.
- Estimated vs actual rows.
- Seek/scan, join algorithm, sort và lookup.
- Logical reads, CPU time, elapsed time.
- Parameter values đã được làm sạch.
- Index definition và statistics gần thời điểm incident.
- Số hàng thực sự bị cập nhật.
- Lock resource trong deadlock/blocking evidence.

Một scan lớn có thể tăng thời gian transaction và số resource bị chạm. Index phù hợp có thể giảm phạm vi truy cập và thời gian giữ khóa. Nhưng thêm index cũng tăng chi phí ghi và có thể tạo thêm lock trên index record khi cập nhật.

Không kết luận “thiếu index” chỉ vì thấy scan. Scan có thể là lựa chọn đúng nếu truy vấn cần phần lớn bảng. So sánh actual rows, selectivity, I/O và plan với workload thật.

### Khi nào plan là bằng chứng đủ mạnh?

Plan cần được liên kết với đúng câu lệnh, tham số, thời điểm và database state. Một plan lấy hôm nay có thể khác plan lúc incident do statistics, parameter sniffing, schema hoặc cache thay đổi. Ghi nhận plan hash, query id và actual plan nếu khả thi.

## 9. Phân tích dữ liệu nghiệp vụ, không chỉ hạ tầng

Sự cố concurrency quan trọng thường phá vỡ một invariant hoặc làm operation được áp dụng sai số lần.

Ví dụ:

- Tồn kho không được âm.
- Số reservation không vượt capacity.
- Chuyển tiền phải bảo toàn tổng số dư.
- Một payment idempotency key chỉ tạo một payment.
- Một message event chỉ làm tăng projection một lần.
- Trạng thái order không được chuyển từ CANCELLED về CONFIRMED do retry cũ.
- Số chứng từ duy nhất trong phạm vi tenant/kỳ.

Hãy xác định invariant trước khi chọn bản sửa. Nếu chỉ làm giảm deadlock nhưng cho phép oversell, bản sửa chưa thành công.

### Bằng chứng nghiệp vụ cần đối chiếu

- Dữ liệu trước và sau sự cố.
- Audit/event log.
- Idempotency key và event ID.
- Số lần request/message được gửi và xử lý.
- Row count của các câu UPDATE.
- Constraint violation.
- Các bản ghi duplicate hoặc thiếu.
- Thời điểm commit và kết quả trả về caller.

Nếu dữ liệu sai, cần xác định phạm vi bản ghi bị ảnh hưởng và quy trình đối soát riêng. Không tự sửa dữ liệu production bằng câu UPDATE thử nghiệm khi chưa xác định rõ nguồn chuẩn và quy trình phê duyệt của hệ thống.

## 10. Tạo giả thuyết và kiểm tra từng giả thuyết

Sau khi thu thập bằng chứng, lập danh sách giả thuyết có thể kiểm chứng. Mỗi giả thuyết cần nêu:

- Cơ chế dự kiến.
- Bằng chứng ủng hộ.
- Bằng chứng phản bác hoặc còn thiếu.
- Thí nghiệm phân biệt.
- Kết quả nào sẽ khiến giả thuyết bị bác bỏ.

Ví dụ:

| Giả thuyết | Bằng chứng ủng hộ | Thí nghiệm phân biệt |
|---|---|---|
| Hai luồng khóa theo thứ tự ngược nhau | Deadlock graph cho thấy A giữ key 1 chờ key 2; B giữ key 2 chờ key 1 | Chạy hai session theo đúng thứ tự; đổi cả hai sang thứ tự khóa thống nhất |
| Transaction giữ khóa do network call | Transaction age dài hơn query duration; trace có HTTP span trước commit | Tách HTTP khỏi transaction và so sánh lock duration |
| Query scan mở rộng lock footprint | Actual plan scan nhiều hàng; lock wait tăng cùng batch | Thử index/plan phù hợp trên dữ liệu đại diện |
| Retry storm làm quá tải | Attempt rate tăng sau timeout; nhiều client retry cùng nhịp | Thêm jitter/budget trong test tải và so sánh retry burst |
| Snapshot conflict bị xử lý sai | SQLSTATE/error code phù hợp; app retry riêng câu cuối | Retry toàn bộ transaction trên snapshot mới và kiểm tra invariant |
| Duplicate message tạo hiệu ứng lặp | Cùng event ID xuất hiện nhiều lần; thiếu inbox unique key | Gửi lại đồng thời cùng event ID và xác nhận một business effect |

Không chọn giả thuyết chỉ vì nó dễ sửa. Cần kiểm tra trên đúng DBMS, isolation level, query shape và data distribution.

### Dùng bằng chứng để bác bỏ

Nếu nghi thiếu index nhưng actual plan cho thấy index seek trên một hàng và thời gian query thấp, giả thuyết đó yếu. Nếu nghi deadlock nhưng không có deadlock graph và request chỉ chờ một blocker duy nhất, điều tra blocking thay vì sửa thứ tự khóa ngay.

Một giả thuyết không được hỗ trợ phải được ghi là chưa xác nhận hoặc bị bác bỏ. Không biến suy đoán thành kết luận trong incident report.

## 11. Dựng causal chain và xác định root cause

Khi đã có bằng chứng, nối chúng thành một chuỗi có thể giải thích:

1. Điều kiện hệ thống trước sự cố.
2. Trigger khiến đường xử lý liên quan chạy.
3. Các thao tác transaction cụ thể.
4. Resource/condition gây xung đột.
5. DBMS hoặc ứng dụng phản ứng thế nào.
6. Triệu chứng người dùng nhìn thấy.
7. Yếu tố góp phần làm phạm vi hoặc mức độ tăng.
8. Vì sao kiểm soát hiện có không phát hiện/ngăn được vấn đề.

Ví dụ:

~~~text
Batch và API chạy đồng thời
        |
        v
Hai code path khóa account theo thứ tự ngược
        |
        v
Deadlock cycle trên hai key
        |
        v
DBMS hủy một transaction
        |
        v
Ứng dụng retry ngay, nhiều instance đồng bộ
        |
        v
Request rate và lock contention tăng
        |
        v
Latency p99 vượt deadline, API trả lỗi
~~~

Root cause có thể là thiếu quy ước thứ tự khóa toàn cục. Trigger là batch bắt đầu trong giờ cao điểm. Yếu tố góp phần là retry không jitter. Symptom là API timeout.

### Câu hỏi “vì sao” cần dừng ở cơ chế có thể hành động

Hỏi “vì sao” nhiều lần có ích nếu mỗi câu trả lời có bằng chứng. Nhưng không nên dừng ở câu trả lời chung như “database quá tải”, “code có race condition” hoặc “người dùng gửi quá nhiều request”.

Một root cause tốt chỉ ra điều có thể thay đổi: thứ tự khóa, transaction boundary, invariant chưa được bảo vệ, retry policy, index/access path, giới hạn concurrency hoặc thiếu observability.

## 12. Chọn mitigation và bản sửa lâu dài

Trong incident đang diễn ra, có thể cần mitigation trước khi hoàn thiện root cause. Phân biệt rõ hai loại.

### Mitigation ngắn hạn

Mục tiêu là giảm tác động trong khi vẫn bảo vệ dữ liệu:

- Giảm tốc độ hoặc tạm dừng batch gây contention nếu có thể.
- Giới hạn concurrency của worker.
- Tắt tạm một tính năng không thiết yếu theo quy trình vận hành.
- Hạ kích thước batch để giảm lock footprint.
- Tạm chuyển traffic sang instance/database khỏe nếu kiến trúc hỗ trợ.
- Dùng retry budget và backoff để tránh retry storm.
- Tăng capacity chỉ khi bằng chứng cho thấy thiếu tài nguyên là yếu tố chính.

Mitigation có thể làm giảm throughput hoặc trì hoãn công việc. Ghi rõ tác động, thời điểm bật/tắt và điều kiện gỡ bỏ.

Không kill session, xóa message hoặc đổi isolation level một cách tùy tiện. Rollback transaction có thể mất công việc đang xử lý và tạo retry; kill session có thể gây rollback dài; thay đổi isolation/config có thể tác động toàn workload. Cần dựa trên runbook và quyền vận hành của hệ thống.

### Bản sửa lâu dài

Chọn thay đổi xử lý đúng cơ chế:

| Nguyên nhân | Hướng sửa có thể phù hợp |
|---|---|
| Thứ tự khóa không nhất quán | Quy định thứ tự tài nguyên và áp dụng ở mọi code path |
| Lost update | Atomic UPDATE, optimistic version check hoặc lock phù hợp |
| Write skew | SERIALIZABLE, guard row, constraint hoặc mô hình dữ liệu mới |
| Transaction giữ khóa lâu | Tách network call, rút ngắn transaction, dùng outbox |
| Scan quá rộng | Index phù hợp, query rewrite, batch theo nghiệp vụ |
| Retry storm | Exponential backoff, jitter, deadline, retry budget |
| Duplicate delivery | Inbox/deduplication, idempotency key và ACK sau commit |
| Hot row | Phân vùng counter, striped aggregate hoặc queue nếu invariant cho phép |
| Lock escalation | Giảm batch/transaction scope, cải thiện access path, partition phù hợp |

Không chọn hint như UPDLOCK, ROWLOCK, NOLOCK hoặc tăng lock timeout chỉ vì tên nghe có vẻ giải quyết lỗi. Mỗi hint thay đổi semantics và có trade-off. Phải biết resource nào đang tranh chấp và invariant cần bảo vệ.

## 13. Xác định tiêu chí thành công trước khi triển khai

Một bản sửa không nên được đánh giá bằng việc “test không còn đỏ” hoặc “log ít lỗi hơn” trong một lần chạy.

Định nghĩa tiêu chí trước:

- Invariant nghiệp vụ luôn đúng trong mọi test đã xác định.
- Lịch concurrency trước đây gây lỗi giờ cho kết quả đúng hoặc một transaction bị từ chối/retry theo hợp đồng.
- Không phát sinh duplicate side effect.
- Deadlock/serialization retry không tạo dữ liệu nửa chừng.
- Lock wait duration và transaction duration nằm trong mục tiêu.
- p95/p99 latency và throughput không xấu đi ngoài giới hạn chấp nhận.
- Retry rate, connection pool usage và database CPU không tăng bất thường.
- Không tạo thêm lỗi ở code path khác dùng chung bảng/tài nguyên.
- Có thể rollback bản sửa nếu metric sau deploy xấu đi.

Tiêu chí phải đo được và gắn với workload thực tế. Nếu sự cố hiếm, cần kiểm thử nhiều lịch hoặc stress test có seed và điều kiện tái hiện rõ.

## 14. Tái hiện sự cố bằng thí nghiệm có kiểm soát

Dùng hai hoặc nhiều session độc lập để tái hiện lịch đã tìm thấy. Không dựa vào sleep cố định để hy vọng scheduler tạo đúng thứ tự.

Quy trình:

1. Tạo fixture với dữ liệu ban đầu xác định.
2. Dùng hai connection riêng và ghi session ID.
3. Đặt isolation level giống môi trường incident.
4. Điều khiển mốc đọc, ghi, giữ khóa và commit bằng latch/barrier hoặc thao tác thủ công.
5. Ghi lại SQL, lock resource và kết quả từng transaction.
6. Xác nhận lịch lỗi xảy ra trước bản sửa.
7. Áp dụng bản sửa trên môi trường thử nghiệm.
8. Chạy lại cùng lịch.
9. Đọc dữ liệu cuối bằng connection mới và kiểm tra invariant.

### Ví dụ: tái hiện deadlock do thứ tự khóa

Trước bản sửa:

~~~text
Session A:
  BEGIN
  UPDATE account 10
  giữ khóa
  chờ account 20

Session B:
  BEGIN
  UPDATE account 20
  giữ khóa
  chờ account 10

DBMS:
  phát hiện chu trình
  chọn deadlock victim
~~~

Sau bản sửa, cả hai code path khóa account theo ID tăng dần:

~~~text
Session A: lock account 10 -> account 20 -> COMMIT
Session B: chờ account 10 -> lock account 20 -> COMMIT
~~~

Kết quả mong đợi là một transaction chờ trước khi giữ khóa thứ hai, không tạo chu trình chỉ vì thứ tự hai account bị đảo. Cần mở rộng test sang các resource khác mà transaction có thể khóa, như ledger, reservation, foreign key hoặc trigger.

### Kiểm tra cả đường lỗi

Không chỉ test happy path. Cần thử:

- Transaction bị deadlock victim.
- Serialization failure.
- Connection mất trước và trong commit.
- Retry hết budget.
- Request bị cancel.
- Một bước nghiệp vụ thất bại sau khi đã cập nhật vài hàng.
- Message được giao lặp.
- Worker chết sau khi claim nhưng trước khi hoàn tất.
- Hai request cùng cập nhật một resource nóng.

Mục tiêu là chứng minh bản sửa bảo vệ invariant ở cả đường thành công và thất bại.

## 15. Kiểm thử hồi quy ở nhiều tầng

### Unit test

Kiểm tra logic thuần như:

- Tạo thứ tự khóa từ tập resource.
- Tính backoff/jitter.
- Phân loại mã lỗi.
- Quyết định retry theo deadline và budget.
- Xử lý version token hoặc idempotency key.

Unit test không chứng minh được lock behavior thực tế của DBMS.

### Integration test với DBMS thật

Dùng đúng engine và phiên bản gần môi trường triển khai:

- Hai connection độc lập.
- Isolation level và database options tương ứng.
- Schema, index, constraint, trigger và foreign key thật.
- Kiểm tra commit/rollback.
- Xác nhận lock wait, deadlock hoặc serialization failure theo kịch bản.

Database giả lập trong bộ nhớ có thể không tái hiện semantics lock/versioning của SQL Server, PostgreSQL hoặc InnoDB.

### Load/stress test

Dùng dữ liệu và phân phối tải gần thực tế:

- Hot key và long-tail distribution.
- Số worker/client đồng thời.
- Batch size.
- Tỷ lệ read/write.
- Thời gian transaction.
- Retry và timeout policy.
- Connection pool và database capacity.

Đo throughput, p50/p95/p99, lock wait, deadlock, retry rate, CPU/I/O và invariant sau khi test kết thúc.

### Test dài hạn và phục hồi

Nếu lỗi xuất hiện theo chu kỳ hoặc khi queue backlog lớn, chạy soak test đủ lâu để bao gồm:

- Cleanup/version store.
- Batch định kỳ.
- Retry sau outage.
- Worker restart.
- Connection pool recovery.
- Failover hoặc reconnect nếu thuộc phạm vi hệ thống.

## 16. So sánh trước và sau bản sửa

Dùng cùng một workload, cùng dataset, cùng cấu hình quan trọng và cùng cách thu thập metric.

| Chỉ số | Trước sửa | Sau sửa | Cách diễn giải |
|---|---:|---:|---|
| Deadlock/minute | Giá trị baseline | Giá trị sau deploy | Phải giảm với cơ chế deadlock đang sửa |
| Lock wait p95 | Baseline | Sau sửa | Cho biết contention còn lại |
| Transaction duration p95 | Baseline | Sau sửa | Phát hiện transaction giữ khóa lâu |
| API latency p99 | Baseline | Sau sửa | Đo trải nghiệm caller |
| Retry attempts/request | Baseline | Sau sửa | Phát hiện retry amplification |
| Throughput | Baseline | Sau sửa | Bảo đảm giảm lỗi không làm mất năng lực |
| Invariant violations | Baseline | Sau sửa | Mục tiêu là không có vi phạm |
| Connection pool wait | Baseline | Sau sửa | Phát hiện connection starvation |
| Database CPU/I/O | Baseline | Sau sửa | Phát hiện chuyển tải sang tài nguyên khác |

Không so sánh hai giai đoạn có traffic hoặc dữ liệu hoàn toàn khác mà không chuẩn hóa. Nếu deploy cùng lúc nhiều thay đổi, khó xác định thay đổi nào tạo ra kết quả. Khi có thể, thay một yếu tố mỗi lần hoặc dùng canary/controlled rollout.

Một metric giảm chưa chắc là bản sửa tốt: deadlock giảm nhưng transaction timeout tăng; retry giảm nhưng request bị từ chối nhiều hơn; lock wait giảm nhưng CPU tăng mạnh do scan. Cần đọc cả correctness và performance.

## 17. Triển khai có kiểm soát và kế hoạch rollback

Trước deploy:

- Xác nhận test tái hiện lỗi đã pass sau bản sửa.
- Kiểm tra migration/index/configuration liên quan.
- Ghi rõ phạm vi service, database, tenant hoặc traffic được rollout.
- Chọn metric và ngưỡng dừng rollout.
- Xác định người chịu trách nhiệm quan sát.
- Chuẩn bị cách rollback code và cấu hình.
- Xác định có cần xử lý dữ liệu sai đã tồn tại hay không.

Trong rollout:

1. Deploy canary hoặc một phạm vi nhỏ nếu kiến trúc hỗ trợ.
2. Theo dõi error rate, deadlock, lock wait, latency, retry và invariant.
3. Mở rộng dần khi metric ổn định.
4. Dừng rollout nếu có dấu hiệu regression.
5. Ghi nhận phiên bản và thời điểm mỗi bước.

Sau deploy:

- Kiểm tra request và transaction mới.
- Kiểm tra queue/outbox backlog.
- Kiểm tra duplicate hoặc dữ liệu thiếu.
- So sánh metric với baseline.
- Theo dõi qua ít nhất một chu kỳ workload có liên quan.

Rollback code không nhất thiết đảo ngược dữ liệu đã commit. Nếu bản sửa bao gồm thay đổi schema, index hoặc dữ liệu, cần kế hoạch rollback tương ứng. Với migration không thể đảo ngược, có thể cần forward-fix hoặc compatibility window.

## 18. Xác minh dữ liệu và đối soát sau incident

Nếu sự cố có thể đã làm sai dữ liệu, sửa code không tự khôi phục các bản ghi đã sai trước đó.

Quy trình đối soát:

1. Xác định khoảng thời gian và nhóm operation có thể bị ảnh hưởng.
2. Dùng audit log, event log, request ID và database history để lập tập bản ghi cần kiểm tra.
3. Xác định nguồn dữ liệu chuẩn.
4. Tính lại invariant hoặc aggregate từ nguồn chuẩn.
5. Phân loại bản ghi đúng, thiếu, trùng hoặc không thể kết luận.
6. Tạo kế hoạch sửa dữ liệu có review và backup phù hợp.
7. Thực hiện sửa theo batch có checkpoint nếu phạm vi lớn.
8. Xác minh lại bằng truy vấn độc lập.
9. Ghi lại số lượng bản ghi và kết quả đối soát.

Ví dụ với inventory, so sánh quantity lưu sẵn với tổng reservation/order line theo trạng thái nghiệp vụ. Không đơn giản đặt quantity về một con số tính từ bảng phụ nếu bảng phụ có duplicate hoặc trạng thái hủy chưa được tính đúng.

Với outbox/inbox, đối chiếu event ID, consumer processed record và hiệu ứng nghiệp vụ. Với payment, cần đối chiếu provider transaction ID và trạng thái phía provider; database nội bộ có thể không biết chắc một request timeout đã được provider thực hiện hay chưa.

## 19. Ghi incident report dựa trên bằng chứng

Một incident report tốt giúp người khác hiểu điều gì đã xảy ra, tại sao kết luận đó đáng tin và bản sửa được xác minh ra sao.

Nội dung nên gồm:

### Tác động

- Thời gian bắt đầu/kết thúc.
- Người dùng/tenant/operation bị ảnh hưởng.
- Tỷ lệ lỗi, độ trễ hoặc số bản ghi bị ảnh hưởng.
- Tác động tới dữ liệu và quy trình nghiệp vụ.

### Timeline

- Trigger.
- Các triệu chứng và thời điểm phát hiện.
- Mitigation.
- Bản sửa và rollout.
- Thời điểm xác nhận phục hồi.

### Bằng chứng

- Error code và trace ID.
- Deadlock graph/blocking chain.
- Transaction age và lock resource.
- Query plan/metrics nếu liên quan.
- Deployment/configuration diff.
- Kết quả test tái hiện.

### Nguyên nhân

- Cơ chế trực tiếp.
- Root cause có thể hành động.
- Yếu tố góp phần.
- Giả thuyết đã bị bác bỏ hoặc còn chưa xác nhận.

### Bản sửa và xác minh

- Thay đổi cụ thể.
- Test trước/sau.
- Invariant đã kiểm tra.
- Metric trước/sau.
- Kết quả rollout và rollback criteria.

### Hành động tiếp theo

- Người sở hữu.
- Việc cần làm.
- Mức ưu tiên.
- Hạn hoàn thành.
- Cách xác nhận hoàn tất.

Không viết “do database quá tải” nếu bằng chứng thực tế là transaction giữ khóa lâu vì gọi HTTP. Không viết “đã hết deadlock” chỉ vì trong vài phút không có lỗi. Ghi phạm vi thời gian quan sát và metric đã dùng.

## 20. Ví dụ điều tra hoàn chỉnh: API giữ tồn kho bị timeout

Giả sử API đặt hàng thỉnh thoảng timeout trong giờ cao điểm. Một số request trả lỗi deadlock; số lượng worker retry tăng. Người dùng báo có đơn thất bại nhưng tồn kho vẫn giảm.

### Bước 1: Phạm vi và timeline

Metrics cho thấy p99 tăng từ 300 ms lên 4 giây lúc batch đồng bộ kho bắt đầu. Deadlock log tăng cùng thời điểm. Tỷ lệ retry tăng sau khi API bắt đầu trả lỗi.

### Bước 2: Thu thập bằng chứng

- Trace API cho thấy order service gọi inventory repository rồi gọi một service khác trước commit.
- Deadlock graph cho thấy API giữ key của inventory item A và chờ item B.
- Batch giữ item B và chờ item A.
- Transaction duration của API cao hơn thời gian SQL thực thi.
- Một số request retry dùng cùng operation nhưng không có idempotency key ổn định.

### Bước 3: Giả thuyết

Giả thuyết chính: API và batch khóa danh sách item theo thứ tự khác nhau. Bằng chứng graph cho thấy đúng hai resource và hai cạnh chờ ngược nhau.

Yếu tố góp phần: transaction API giữ khóa qua external call và retry không có jitter.

### Bước 4: Tái hiện

Dùng hai session:

~~~text
A: lock item 10
B: lock item 20
A: request item 20 -> waits
B: request item 10 -> deadlock
~~~

Chạy lại sau khi cả hai luồng khóa item theo ID tăng dần. Một session chờ ở item đầu tiên; chu trình do thứ tự ngược nhau không còn xuất hiện.

### Bước 5: Bản sửa

- Chuẩn hóa thứ tự khóa item theo ID ở API và batch.
- Giữ transaction chỉ quanh thao tác giữ tồn kho và ghi outbox.
- Chuyển external call sang worker sau commit.
- Dùng idempotency key ổn định cho operation đặt hàng.
- Retry deadlock toàn bộ transaction với giới hạn và jitter.

### Bước 6: Xác minh

- Integration test hai session tái hiện lịch cũ.
- Stress test với nhiều item và batch đồng thời.
- Kiểm tra quantity không âm và không giữ vượt số lượng.
- Kiểm tra một operation ID không tạo hai reservation.
- So sánh deadlock/minute, lock wait p95, transaction duration, retry rate và API p99 trước/sau.
- Rollout canary rồi mở rộng sau khi metric ổn định.

Kết luận dựa trên deadlock graph, trace, lịch tái hiện và kết quả test sau sửa. Không chỉ dựa trên việc API hết timeout trong một lần deploy.

## 21. Những cách điều tra dễ dẫn tới kết luận sai

### Chỉ nhìn log lỗi cuối cùng

Error code mô tả cách request kết thúc, không luôn mô tả nguyên nhân đầu tiên. Hãy nối log với transaction, lock và code path.

### Chỉ xem một snapshot hiện tại

Blocking có thể biến mất trước khi người điều tra mở dashboard. Dùng deadlock capture, sampling và trace có retention phù hợp.

### Kill blocker ngay lập tức

Có thể giải phóng waiter nhưng cũng rollback công việc lớn, tạo tải rollback và làm mất bằng chứng. Xác định owner, tác động và runbook trước khi can thiệp.

### Tăng timeout để làm lỗi biến mất

Timeout dài hơn có thể làm request chờ lâu hơn, giữ connection lâu hơn và che giấu blocker. Nó không sửa deadlock cycle hay invariant.

### Thêm index/hint mà không đo

Index có chi phí ghi; hint có thể thay đổi lock behavior và plan. Dùng bằng chứng plan/resource để chọn thay đổi.

### Chỉ chạy test tuần tự

Test tuần tự không chứng minh được hành vi hai transaction đồng thời. Dùng connection độc lập và mốc đồng bộ.

### Chỉ kiểm tra throughput

Throughput cao không có nghĩa dữ liệu đúng. Luôn kiểm tra invariant, duplicate, missing records và trạng thái sau rollback.

### Không theo dõi sau deploy

Một bản sửa có thể giảm lỗi trong giờ thấp điểm nhưng gây contention ở giờ cao điểm. Theo dõi đủ chu kỳ tải có liên quan.

## 22. Quy trình xử lý sự cố từ bằng chứng đến xác minh

1. **Khoanh vùng tác động**: xác định operation, tenant, dữ liệu và thời gian bị ảnh hưởng.
2. **Lập timeline**: nối deploy, traffic, batch, error, lock wait và mitigation.
3. **Bảo toàn bằng chứng**: trace, SQL/error code, session, deadlock graph, plan và metrics.
4. **Phân loại cơ chế**: blocking, deadlock, timeout, serialization conflict, lost update, duplicate hoặc query performance.
5. **Dựng quan hệ nhân quả**: xác định waiter, blocker, resource, transaction boundary và code path.
6. **Đặt giả thuyết có thể bác bỏ**: nêu bằng chứng ủng hộ, thiếu và thí nghiệm phân biệt.
7. **Xác định root cause**: tìm điều kiện thiết kế/quy trình cho phép cơ chế lỗi xảy ra.
8. **Mitigate an toàn**: giảm tác động và ghi lại trade-off trong khi bảo vệ dữ liệu.
9. **Tái hiện**: tạo lịch đồng thời trên DBMS phù hợp với isolation và workload.
10. **Sửa đúng cơ chế**: thay thứ tự khóa, transaction scope, constraint, retry, index hoặc idempotency theo bằng chứng.
11. **Kiểm thử hồi quy**: unit, integration, concurrency, load và failure-path.
12. **Đặt tiêu chí thành công**: invariant, error rate, lock wait, latency, throughput và retry.
13. **Rollout có kiểm soát**: canary, quan sát, ngưỡng dừng và rollback plan.
14. **Đối soát dữ liệu**: sửa các bản ghi đã bị ảnh hưởng theo nguồn chuẩn.
15. **Ghi incident report**: evidence, causal chain, fix, validation và hành động phòng ngừa.

## 23. Mẫu ghi nhận điều tra

Có thể dùng mẫu sau để giữ cho kết luận luôn gắn với bằng chứng:

~~~text
INCIDENT:
- ID:
- Thời gian:
- Môi trường / DBMS / phiên bản:
- Operation bị ảnh hưởng:

IMPACT:
- Người dùng / tenant:
- Request lỗi / độ trễ:
- Dữ liệu có thể bị ảnh hưởng:
- Invariant liên quan:

TIMELINE:
- T0:
- T1:
- T2:
- Mitigation:
- Recovery:

EVIDENCE:
- Trace / correlation IDs:
- SQLSTATE / vendor error:
- Session / transaction IDs:
- Blocking chain / deadlock graph:
- Lock resource / mode:
- Query plan / query fingerprint:
- Metrics / deployment diff:

HYPOTHESES:
- H1:
  Evidence for:
  Evidence against / missing:
  Discriminating test:
  Result:
- H2:

ROOT CAUSE:
- Failure mechanism:
- Direct cause:
- Contributing factors:
- Why existing controls missed it:

FIX:
- Code / schema / configuration:
- Mitigation removed:
- Rollback plan:

VALIDATION:
- Reproduction before fix:
- Reproduction after fix:
- Invariants checked:
- Regression / load tests:
- Before/after metrics:
- Rollout observation window:

FOLLOW-UP:
- Action:
- Owner:
- Due date:
- Completion evidence:
~~~

## 24. Checklist xác minh bản sửa

- [ ] Sự cố đã được phân loại bằng error code và bằng chứng DBMS.
- [ ] Timeline liên kết được app trace, database session và deployment.
- [ ] Deadlock/blocking graph hoặc bằng chứng tương đương đã được lưu nếu có.
- [ ] Root cause giải thích được chuỗi sự kiện, không chỉ nhắc lại triệu chứng.
- [ ] Giả thuyết chính đã được kiểm tra bằng thí nghiệm phân biệt.
- [ ] Có test tái hiện trước sửa và kết quả sau sửa.
- [ ] Test dùng đúng DBMS/isolation/schema/index quan trọng.
- [ ] Bất biến nghiệp vụ được kiểm tra sau commit, rollback và retry.
- [ ] Duplicate, ambiguous commit và side effect được xử lý an toàn.
- [ ] Performance được so sánh bằng workload tương đương.
- [ ] Có canary/rollout criteria và rollback plan.
- [ ] Dữ liệu bị ảnh hưởng đã được đánh giá và đối soát.
- [ ] Có metric/alert để phát hiện tái diễn.
- [ ] Incident report phân biệt rõ fact, inference và điều chưa xác nhận.

Một quy trình xử lý sự cố tốt bắt đầu từ phạm vi và bằng chứng có thể kiểm tra, sau đó phân loại đúng cơ chế concurrency và dựng chuỗi nhân quả. Root cause phải giải thích được vì sao các transaction, query hoặc worker đi đến trạng thái lỗi; bản sửa phải thay đổi đúng cơ chế đó. Chỉ xác nhận thành công khi thí nghiệm tái hiện đã cho kết quả đúng, invariant vẫn được giữ, metric trước/sau đáp ứng mục tiêu và hệ thống đã được quan sát qua workload liên quan.
