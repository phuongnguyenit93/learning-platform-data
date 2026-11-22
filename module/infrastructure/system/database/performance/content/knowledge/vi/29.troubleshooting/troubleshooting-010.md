# Giảm tải tạm thời, thu thập bằng chứng và xác minh phục hồi

## Mục tiêu bài học

Khi database đột ngột chậm, số request chờ tăng nhanh hoặc nhiều truy vấn bắt đầu timeout, đội vận hành cần đưa hệ thống về trạng thái kiểm soát được. Trong lúc sự cố diễn ra, tải tiếp tục đổ vào có thể làm hàng đợi dài hơn, connection pool cạn, retry tăng và tài nguyên database bị tiêu thụ bởi những công việc không còn khả năng hoàn tất đúng hạn. Tuy nhiên, nếu thay đổi cấu hình hoặc kết thúc session một cách vội vàng, đội xử lý có thể làm mất bằng chứng, gây thêm gián đoạn hoặc khiến việc xác định nguyên nhân khó hơn.

Trong chương **Chẩn đoán sự cố** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn cách giảm tải tạm thời, thu thập bằng chứng và xác minh phục hồi. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, xử lý sự cố cần dựa trên số liệu về workload, execution plan, transaction, I/O và tài nguyên, đồng thời ghi nhận tác động của từng biện pháp giảm tải.

Sau bài học, bạn có thể:

- Nhận diện dấu hiệu quá tải và phân biệt triệu chứng với nguyên nhân.
- Ưu tiên ổn định dịch vụ bằng các biện pháp giảm tải có phạm vi và thời hạn rõ ràng.
- Kiểm soát concurrency, hàng đợi, retry và workload không thiết yếu.
- Thu thập snapshot về session, truy vấn, lock, WAL, I/O và tài nguyên trước/sau can thiệp.
- Chọn bằng chứng phù hợp để phân biệt CPU, I/O, memory, lock contention và connection saturation.
- Khôi phục traffic theo từng giai đoạn và xác nhận hệ thống đã ổn định.
- Ghi lại timeline, quyết định, tác động và hành động phòng ngừa sau sự cố.

## 1. Hiểu đúng mục tiêu khi đang có sự cố

Sự cố hiệu năng thường có biểu hiện ở nhiều tầng cùng lúc. Ví dụ, API timeout có thể làm connection pool tăng số connection đang chờ; ứng dụng retry khiến request rate tăng; database phải xử lý thêm query và càng chậm hơn. Nếu chỉ nhìn một metric như CPU hoặc số connection, đội vận hành có thể chọn sai biện pháp.

**Giảm tải tạm thời** là hành động giới hạn hoặc trì hoãn một phần công việc để database có đủ tài nguyên xử lý các giao dịch quan trọng. Mục tiêu trước mắt là giảm tốc độ tích lũy hàng đợi, đưa latency và error rate về vùng có thể kiểm soát, bảo vệ tính đúng đắn của dữ liệu và tạo thời gian điều tra.

Giảm tải không tự động sửa được nguyên nhân gốc. Nếu một truy vấn có plan kém, một transaction giữ khóa lâu hoặc storage bị lỗi, việc từ chối bớt request chỉ giúp hệ thống không tiếp tục suy sụp trong lúc đội kỹ thuật xử lý.

### 1.1. Phân biệt triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần tìm |
|---|---|---|
| API p95/p99 tăng, pool pending tăng | Query chậm, connection bị giữ lâu, pool quá nhỏ hoặc database bão hòa | Pool metrics, query duration, active sessions, wait events |
| CPU database gần 100% | Query scan/join nặng, quá nhiều concurrency, plan regression hoặc background job | CPU theo process, top query, execution plan, concurrency |
| CPU thấp nhưng query chậm | Storage latency, lock wait, network hoặc session chờ tài nguyên | Wait events, blocking chain, I/O latency, network metrics |
| Nhiều session chờ khóa | Transaction dài, hot row, thứ tự khóa không nhất quán | `pg_stat_activity`, `pg_locks`, blocking PID, transaction age |
| Read/write latency cùng tăng | Storage bão hòa, checkpoint, bulk load, backup hoặc temp spill | IOPS, throughput, queue depth, checkpoint/WAL, temp usage |
| Connection count tăng nhanh | Pool mở quá nhiều, connection leak, retry storm hoặc query bị treo | Pool active/pending, connection source, session state, retry rate |
| WAL hoặc log tăng nhanh | Write burst, index maintenance, replication/archive bị chậm | WAL rate, slot, archive status, write workload |
| Một endpoint tăng lỗi sau release | SQL, schema, index, config hoặc application behavior thay đổi | Release timeline, query fingerprint, plan trước/sau |

### 1.2. Các mục tiêu theo thứ tự ưu tiên

Trong phần lớn sự cố hiệu năng database, đội xử lý nên hướng tới:

1. Bảo vệ các giao dịch quan trọng và tính nhất quán dữ liệu.
2. Ngăn hàng đợi, concurrency và retry tiếp tục tăng ngoài khả năng phục vụ.
3. Giảm công việc không thiết yếu đang chiếm CPU, I/O, memory hoặc connection.
4. Ghi lại bằng chứng đủ để xác định bottleneck và đánh giá tác động của can thiệp.
5. Khôi phục traffic có kiểm soát, theo dõi backlog và xác nhận SLA.
6. Chuyển kết quả xử lý thành hành động khắc phục lâu dài.

Không phải sự cố nào cũng cần thực hiện mọi bước theo đúng thứ tự tuyến tính. Nếu database sắp hết dung lượng WAL hoặc không thể commit, bảo vệ khả năng ghi log có thể trở thành ưu tiên tức thời. Nếu hệ thống đang phục vụ sai dữ liệu, tính đúng đắn phải được ưu tiên hơn throughput.

## 2. Quy trình phản ứng sự cố

Một quy trình nhất quán giúp nhiều người phối hợp mà không thực hiện các thay đổi mâu thuẫn.

```text
Phát hiện và xác nhận ảnh hưởng
          |
          v
Chọn người điều phối và ghi timeline
          |
          v
Thu thập snapshot ban đầu có chi phí thấp
          |
          v
Giảm tải có phạm vi và thời hạn
          |
          v
Phân loại bottleneck bằng metric và log
          |
          v
Áp dụng một thay đổi có giả thuyết
          |
          v
Theo dõi tác động và quyết định giữ/hoàn tác
          |
          v
Khôi phục traffic theo từng giai đoạn
          |
          v
Xác minh phục hồi và ghi nhận bài học
```

### 2.1. Xác nhận phạm vi ảnh hưởng

Trước tiên xác định:

- Database hoặc cluster nào bị ảnh hưởng.
- Ứng dụng, endpoint, tenant hoặc nhóm người dùng nào bị ảnh hưởng.
- Đọc, ghi hay cả hai đang chậm.
- Sự cố bắt đầu lúc nào và có trùng release, batch job, backup, migration hoặc thay đổi hạ tầng không.
- Dữ liệu có dấu hiệu sai lệch, mất kết nối hoặc lỗi commit không rõ trạng thái hay không.
- Có replica, queue hoặc cache nào đang nhận tải thay thế không.

So sánh với baseline cùng khung giờ hoặc ngày tương tự nếu có. Một mức CPU cao có thể là bình thường vào giờ cao điểm; điều quan trọng là mức tăng so với thông lượng, latency và năng lực đã biết.

### 2.2. Thiết lập điều phối và timeline

Trong sự cố kéo dài, nên có một người điều phối quyết định thứ tự hành động và một nơi ghi timeline. Mỗi mục ghi:

- Thời điểm phát hiện và phạm vi ảnh hưởng.
- Metric hoặc log dẫn tới quyết định.
- Hành động đã thực hiện, người thực hiện và phạm vi tác động.
- Giá trị cấu hình trước/sau nếu có thay đổi.
- Kết quả quan sát sau hành động.
- Quyết định tiếp theo: giữ, điều chỉnh hay rollback.

Timeline giúp phân biệt sự cải thiện do hành động nào với thay đổi tự nhiên của traffic. Không thực hiện nhiều thay đổi lớn cùng lúc nếu chưa có lý do khẩn cấp, vì khi đó khó biết biện pháp nào có tác dụng hoặc gây tác dụng phụ.

## 3. Thu thập bằng chứng ban đầu

Khi hệ thống còn hoạt động, hãy lấy những snapshot có chi phí thấp và không làm tăng tải đáng kể. Không cần đợi thu thập đầy đủ mọi metric mới giảm tải nếu hàng đợi đang tăng nhanh. Trong trường hợp khẩn cấp, lấy các bằng chứng tối thiểu có thể thực hiện an toàn rồi ổn định dịch vụ.

### 3.1. Snapshot ở tầng ứng dụng

Ghi nhận:

- Request rate, success rate, timeout và error rate theo endpoint.
- p50/p95/p99 và thời gian chờ ở từng dependency.
- Connection pool active, idle, pending, acquisition timeout và connection leak.
- Số lần retry, attempt trung bình và thời gian backoff.
- Queue depth, tuổi của message cũ nhất và tốc độ consumer.
- Số request bị hủy, bị từ chối hoặc đang chờ admission control.
- Phiên bản ứng dụng, thời điểm release và feature flag đang bật.

Nếu chỉ nhìn tổng thời gian API, không thể biết request chậm vì chờ pool hay vì SQL chạy lâu. Hãy tách thời gian queue, pool acquisition, database execution, network và xử lý kết quả.

### 3.2. Snapshot session trong PostgreSQL

`pg_stat_activity` cho biết trạng thái backend, thời điểm bắt đầu query/transaction và wait event. Ví dụ:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    query_start,
    xact_start,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xmin,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
```

Lưu ý:

- `state = 'active'` chỉ cho biết backend đang thực thi một query; nó có thể đang chờ lock hoặc I/O.
- `wait_event_type` và `wait_event` giúp xác định backend đang chờ loại sự kiện nào.
- `idle in transaction` có thể giữ snapshot và khóa dù không chạy query.
- `query_age` và `transaction_age` có ý nghĩa khác nhau. Một transaction lâu có thể gồm nhiều câu SQL ngắn.
- Query text có thể chứa literal nhạy cảm. Khi lưu snapshot, hãy giới hạn quyền truy cập và che dữ liệu theo chính sách.

### 3.3. Xác định blocking chain

Trong PostgreSQL, `pg_blocking_pids(pid)` trả về PID của các backend đang chặn một backend. Có thể dùng truy vấn sau để tìm session bị chặn và session chặn:

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    blocked.wait_event_type,
    blocked.wait_event,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 250) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS b(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = b.blocker_pid
ORDER BY blocker.xact_start NULLS LAST;
```

Một blocker có thể chặn nhiều session và tạo thành blocking chain. Ưu tiên tìm root blocker, xem transaction age, ứng dụng sở hữu và công việc đang thực hiện. Không kết thúc backend chỉ vì nó có nhiều session chờ; phải xác định tác động rollback và tính đúng đắn nghiệp vụ.

### 3.4. Snapshot query statistics

Nếu `pg_stat_statements` đã được bật, lưu các query fingerprint đang tiêu thụ nhiều thời gian:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    left(query, 250) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Các cột và tên trường phụ thuộc phiên bản PostgreSQL/extension. Hãy xác nhận schema view trong môi trường đang chạy. Bộ đếm thường tích lũy; lấy snapshot trước/sau hoặc tính delta theo cửa sổ thời gian. Không reset thống kê giữa sự cố chỉ để làm dashboard dễ đọc, vì hành động đó làm mất ngữ cảnh so sánh.

### 3.5. Snapshot I/O, WAL và checkpoint

Tùy phiên bản PostgreSQL, có thể dùng:

```sql
-- PostgreSQL 16 trở lên có pg_stat_io
SELECT * FROM pg_stat_io;

-- PostgreSQL 17 trở lên có pg_stat_checkpointer
SELECT * FROM pg_stat_checkpointer;

-- Thống kê background writer; trường checkpoint thay đổi theo phiên bản
SELECT * FROM pg_stat_bgwriter;

-- Thống kê WAL trên các phiên bản hỗ trợ
SELECT * FROM pg_stat_wal;
```

Không giả định mọi view hoặc cột đều có ở mọi phiên bản. Lưu số liệu phù hợp với phiên bản hiện tại, sau đó đối chiếu với metric storage của hệ điều hành hoặc cloud: read/write latency, IOPS, throughput, queue depth và utilization.

### 3.6. Snapshot database và tiến trình nền

Có thể ghi lại một số chỉ số:

```sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    deadlocks,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
```

Đồng thời xem:

- Autovacuum đang chạy và bảng nào có backlog.
- Checkpoint gần nhất, số buffer ghi và thời gian sync.
- Replication lag, slot giữ WAL và archive failure.
- Số transaction lâu, prepared transaction và session idle in transaction.
- Disk free space, inode, quota và tốc độ tăng WAL/temp/data.

Snapshot phải có timestamp và đơn vị. Với bộ đếm tích lũy, ghi thời điểm reset và lấy delta; với gauge như số session đang active, giữ giá trị tại thời điểm lấy mẫu.

## 4. Giảm tải tạm thời ở tầng ứng dụng

Ứng dụng là nơi có thể ngăn request mới tiếp tục tạo thêm công việc khi database đã quá tải. Các biện pháp nên có phạm vi rõ, dễ bật/tắt và được ghi vào timeline.

### 4.1. Giới hạn concurrency

Giới hạn số truy vấn đồng thời giúp database không phải xử lý nhiều công việc hơn khả năng phục vụ. Có thể dùng:

- Semaphore hoặc bulkhead theo nhóm endpoint.
- Giới hạn số worker của batch/consumer.
- Giới hạn số connection trong pool.
- Hàng đợi hữu hạn với thời gian chờ tối đa.
- Admission control dựa trên mức tải hoặc latency.

Nếu pool đã có hàng đợi dài, tăng pool size có thể làm database nhận thêm concurrency và nặng hơn. Trước khi tăng giới hạn, xác định active sessions đang chạy gì, số session chờ và năng lực CPU/I/O còn lại.

### 4.2. Từ chối sớm request không còn đủ thời gian

Request đã chờ lâu và gần hết deadline có thể không còn đủ thời gian để hoàn thành SQL, rollback và trả response. Tiếp tục đưa request đó vào database chỉ làm tăng tải.

Ứng dụng có thể từ chối sớm bằng `429 Too Many Requests` khi client/tenant vượt quota hoặc `503 Service Unavailable` khi dịch vụ tạm thời không đủ năng lực. Nếu có thể, trả `Retry-After` và hướng dẫn client dùng backoff có jitter.

Không để client retry ngay lập tức. Nếu tất cả client cùng retry sau một khoảng cố định, hệ thống có thể tạo retry storm ngay sau khi vừa giảm tải.

### 4.3. Tắt hoặc giảm workload không thiết yếu

Tùy mức độ ảnh hưởng, có thể tạm dừng:

- Báo cáo dài hoặc dashboard không thiết yếu.
- Batch export, import, backfill hoặc đồng bộ lịch sử.
- Consumer xử lý queue có thể trì hoãn.
- Job tạo dữ liệu tổng hợp hoặc refresh materialized view.
- Tác vụ migration hoặc index build chưa khẩn cấp.
- Truy vấn ad hoc không thuộc luồng nghiệp vụ quan trọng.

Trước khi dừng, kiểm tra checkpoint/offset và tính idempotent để có thể tiếp tục sau đó. Dừng consumer có thể làm queue backlog tăng; cần bảo đảm queue còn đủ dung lượng và có kế hoạch xử lý sau sự cố.

Không tắt autovacuum toàn cục như một biện pháp giảm tải mặc định. Autovacuum giữ vai trò duy trì khả năng tái sử dụng tuple và freeze; tắt lâu có thể làm bloat và nguy cơ transaction ID wraparound tăng. Nếu một tác vụ vacuum cụ thể đang ảnh hưởng nghiêm trọng, cần đánh giá relation, tiến độ, XID age và quyết định có kiểm soát.

### 4.4. Giảm chi phí request

Các biện pháp có thể bật tạm thời:

- Giảm page size hoặc giới hạn số dòng trả về cho endpoint nặng nếu semantics cho phép.
- Tạm ẩn chức năng tìm kiếm/report không thiết yếu.
- Dùng cache cho dữ liệu có thể chấp nhận độ cũ rõ ràng.
- Gom truy vấn lặp thành batch hoặc tạm ngăn N+1 ở một luồng cụ thể.
- Giảm số lần refresh dashboard.
- Trì hoãn công việc nền và xử lý theo micro-batch sau khi hệ thống ổn định.

Không cắt bớt dữ liệu một cách âm thầm nếu ứng dụng cần kết quả đầy đủ. Mọi chế độ degraded cần có semantics rõ và thông báo phù hợp.

### 4.5. Giảm retry và timeout amplification

Kiểm tra retry ở gateway, service, driver và job worker. Nếu nhiều tầng đều retry độc lập, một request có thể tạo ra nhiều lần thực thi database.

Trong sự cố:

- Tắt retry tự động cho lỗi không retry an toàn.
- Giới hạn attempt và tổng retry budget.
- Dùng exponential backoff và jitter.
- Không retry request đã hết deadline.
- Dùng idempotency key cho thao tác có tác dụng phụ.
- Phân biệt lỗi trước commit với kết quả commit không rõ do mất kết nối.

Không tăng timeout hàng loạt để làm giảm số lỗi hiển thị. Timeout dài hơn có thể giữ connection lâu hơn và khiến hàng đợi tăng. Hãy điều chỉnh theo giai đoạn đang chờ và SLA.

## 5. Giảm tải ở tầng database

Một số biện pháp có thể thực hiện trực tiếp ở database, nhưng cần hiểu phạm vi và tác động của chúng.

### 5.1. Hủy query có mục tiêu

Trong PostgreSQL:

- `pg_cancel_backend(pid)` yêu cầu hủy câu lệnh đang chạy của backend.
- `pg_terminate_backend(pid)` chấm dứt session backend và transaction chưa commit sẽ bị rollback.

Ví dụ yêu cầu hủy một query đã xác định:

```sql
SELECT pg_cancel_backend(12345);
```

Chỉ dùng PID sau khi đã xác minh ứng dụng, user, query, transaction age và tác động. Ưu tiên cancel statement trước terminate session nếu mục tiêu là dừng một câu lệnh. Kết thúc session có thể giải phóng lock nhưng cũng có thể làm rollback transaction lớn, tạo thêm I/O và thời gian phục hồi.

### 5.2. Cẩn trọng với query dài nhưng hợp lệ

Một truy vấn báo cáo có thể chạy lâu nhưng không phải nguyên nhân làm hệ thống quá tải nếu nó dùng tài nguyên thấp và chạy trong thời gian dự kiến. Ngược lại, một truy vấn ngắn chạy hàng nghìn lần mỗi giây có thể chiếm phần lớn CPU.

Đừng chỉ hủy query có `query_age` lớn nhất. Hãy xem tổng thời gian, CPU, I/O, wait event, số lần gọi và mức độ quan trọng của workload.

### 5.3. Giới hạn statement và lock wait có mục tiêu

Có thể áp dụng `statement_timeout` hoặc `lock_timeout` cho role, database hoặc transaction cụ thể để ngăn một nhóm query chờ quá lâu. Trong PostgreSQL, `SET LOCAL` trong transaction giới hạn phạm vi cấu hình:

```sql
BEGIN;
SET LOCAL lock_timeout = '300ms';
SET LOCAL statement_timeout = '3s';

-- Thực hiện thao tác nghiệp vụ đã xác định

COMMIT;
```

Giá trị chỉ là ví dụ. Timeout quá ngắn có thể hủy cả giao dịch hợp lệ; timeout quá dài có thể giữ connection và lock lâu. Nếu statement bị cancel trong explicit transaction, ứng dụng phải rollback trước khi tái sử dụng connection.

### 5.4. Tránh thay đổi cấu hình diện rộng khi chưa có giả thuyết

Trong sự cố, thay đổi đồng thời `work_mem`, `max_connections`, parallelism, checkpoint và autovacuum có thể tạo thêm biến số. Một số tham số áp dụng theo session hoặc operation; tăng chúng có thể nhân mức sử dụng tài nguyên theo concurrency.

Trước khi thay đổi:

1. Ghi giá trị hiện tại và nguồn cấu hình.
2. Xác định metric nào cho thấy tham số liên quan tới bottleneck.
3. Chọn phạm vi nhỏ nhất có thể: query, role, database hoặc instance.
4. Ghi giá trị mới và thời điểm áp dụng.
5. Theo dõi metric dự kiến cùng metric bảo vệ.
6. Hoàn tác nếu tác động không như giả thuyết hoặc làm xấu chỉ số khác.

## 6. Giảm tải theo loại bottleneck

Biện pháp giảm tải phải khớp với tài nguyên đang bão hòa.

### 6.1. CPU-bound

Dấu hiệu thường gặp:

- CPU database cao liên tục và run queue tăng.
- Query latency tăng cùng số lượng query/giây.
- Wait event không cho thấy phần lớn session đang chờ storage hoặc lock.
- Một vài fingerprint có tổng thời gian CPU lớn.

Biện pháp tạm thời:

- Tạm dừng report, export hoặc batch CPU-intensive.
- Giới hạn concurrency của query nặng.
- Giảm tần suất refresh hoặc xử lý theo lô nhỏ hơn.
- Hủy query có plan bất thường và tác động lớn sau khi xác minh.
- Tạm giảm traffic tới endpoint không thiết yếu.

Không dùng `LIMIT` hoặc cắt dữ liệu nếu làm thay đổi kết quả nghiệp vụ. Sau khi ổn định, kiểm tra execution plan, join, sort, aggregate, hàm/UDF và khả năng song song.

### 6.2. I/O-bound

Dấu hiệu:

- Read/write latency tăng, queue depth cao hoặc storage utilization gần giới hạn.
- Nhiều buffer read hoặc temp read/write tăng.
- CPU có thể thấp vì backend đang chờ I/O.
- Checkpoint, backup, bulk load hoặc index build trùng thời điểm.

Biện pháp tạm thời:

- Tạm dừng backup, export, bulk load hoặc index build không khẩn cấp nếu an toàn.
- Giảm concurrency của báo cáo scan lớn.
- Giảm số lần đọc lặp bằng cache hoặc kết quả tổng hợp có thể chấp nhận độ cũ.
- Tránh chạy đồng thời nhiều maintenance job trên cùng volume.
- Kiểm tra free space và tình trạng thiết bị lưu trữ.

Không xóa WAL hoặc file database thủ công để giải phóng dung lượng. Nếu storage có lỗi phần cứng hoặc volume hết dung lượng, chuyển sang quy trình hạ tầng/DBA tương ứng.

### 6.3. Lock contention

Dấu hiệu:

- Nhiều backend có `wait_event_type = 'Lock'`.
- Một hoặc vài PID xuất hiện trong nhiều blocking chain.
- Transaction age của blocker lớn.
- Query duration cao nhưng CPU của các backend chờ thấp.

Biện pháp tạm thời:

- Tạm giảm concurrency trên endpoint ghi vào cùng tài nguyên nóng.
- Dừng producer hoặc batch đang tạo tranh chấp nếu có thể tiếp tục sau.
- Cancel blocker chỉ khi đã xác định chủ sở hữu và tác động rollback.
- Không mở thêm worker để “xử lý nhanh hơn” khi tất cả cùng chờ một khóa.

Sau sự cố, sửa transaction dài, thứ tự khóa, hot row, index hỗ trợ điều kiện cập nhật và chiến lược phân lô.

### 6.4. Memory pressure và temp spill

Dấu hiệu:

- Swap hoặc memory pressure tăng.
- Sort/hash spill và temp bytes tăng.
- Query báo cáo dùng nhiều memory đồng thời.
- Hệ điều hành bắt đầu reclaim mạnh hoặc OOM kill.

Biện pháp tạm thời:

- Giới hạn số truy vấn sort/hash lớn chạy đồng thời.
- Tạm hoãn báo cáo không khẩn cấp.
- Giảm batch size hoặc giới hạn kích thước kết quả nếu semantics cho phép.
- Chuyển workload sang thời điểm ít tải hoặc môi trường phân tích riêng.
- Theo dõi temp volume và free space.

Không tăng `work_mem` trên toàn instance chỉ vì một query spill. Trong PostgreSQL, `work_mem` có thể được dùng cho nhiều operation trong một query và nhiều session đồng thời; tăng nó có thể làm memory pressure nặng hơn.

### 6.5. Connection saturation

Dấu hiệu:

- Pool pending và acquisition timeout tăng.
- Nhiều backend idle hoặc idle in transaction.
- Query duration và transaction age tăng.
- Số connection gần giới hạn nhưng throughput không tăng tương ứng.

Biện pháp tạm thời:

- Giới hạn số request mới và concurrency theo endpoint.
- Xử lý connection leak và transaction bị giữ lâu.
- Tạm giảm worker hoặc pool của batch client.
- Không tăng `max_connections` khi chưa đánh giá memory/backend overhead.
- Dành connection reserve cho health check, quản trị và tác vụ cần thiết.

## 7. Thu thập bằng chứng từ hệ điều hành và hạ tầng

Database view cho biết trạng thái nội bộ, nhưng không thay thế metric storage, host và network.

### 7.1. CPU và memory

Thu thập CPU utilization theo process, run queue, load average, RSS, page cache, swap, major page fault và OOM event. Xác định CPU cao nằm ở database backend, background process hay ứng dụng chạy cùng host.

Nếu database chạy trong container, cần xem cả giới hạn CPU/memory của container, throttling và trạng thái node. CPU utilization thấp ở host không loại trừ container bị CPU quota throttling.

### 7.2. Storage

Thu thập theo từng volume:

- Read/write latency.
- IOPS và throughput.
- Queue depth hoặc outstanding I/O.
- Utilization và giới hạn burst/credit nếu dùng storage cloud.
- Free bytes, inode, quota và dung lượng thin-provisioned pool.
- Lỗi thiết bị, retry hoặc trạng thái degraded.

Tách volume data, WAL, temp, backup và archive nếu chúng nằm ở các mount khác nhau. Một volume đầy hoặc chậm có thể ảnh hưởng toàn bộ database dù các volume khác bình thường.

### 7.3. Network

Đo latency, packet loss, retransmission, throughput và số connection reset giữa ứng dụng, proxy, database và replica. Network chậm có thể làm client giữ connection lâu dù server đã hoàn tất một phần công việc.

Đối với replication, đo sender/receiver lag và thời gian replay. Đối với client, kiểm tra DNS, TLS handshake, load balancer và connection pool behavior.

### 7.4. Log và sự kiện hệ thống

Đối chiếu timestamp giữa:

- PostgreSQL log: statement timeout, deadlock, checkpoint, autovacuum, connection và recovery.
- Application log: request ID, endpoint, query fingerprint, timeout và retry attempt.
- Storage/OS log: I/O error, filesystem warning, OOM và volume resize.
- Deployment log: release, migration, config change và feature flag.
- Scheduler: backup, ETL, report, maintenance và batch job.

Đồng bộ thời gian giữa các máy giúp dựng timeline chính xác. Nếu clock lệch, một sự kiện ở database có thể bị ghép sai với request ở ứng dụng.

## 8. Bảo toàn bằng chứng trong khi giảm tải

Can thiệp càng mạnh thì càng cần ghi rõ trạng thái trước và sau. Một số dữ liệu thống kê chỉ tồn tại dưới dạng bộ đếm tích lũy hoặc log quay vòng; nếu không lưu kịp, cơ hội tìm nguyên nhân có thể mất.

### 8.1. Snapshot trước can thiệp khi có thể

Lưu các dữ liệu tối thiểu:

- Thời điểm và phạm vi sự cố.
- Request rate, p95/p99, error rate và queue depth.
- Pool active/pending và số connection database.
- `pg_stat_activity` và blocking chain.
- Top query fingerprint và thống kê I/O/WAL.
- CPU, memory, storage latency và free space.
- Log gần thời điểm bắt đầu sự cố.
- Cấu hình và release gần nhất.

Nếu hệ thống đang ở trạng thái nguy hiểm, không trì hoãn biện pháp bảo vệ chỉ để thu thập một bộ snapshot hoàn hảo. Ghi những gì có thể lấy an toàn rồi giảm tải.

### 8.2. Không reset số liệu tùy tiện

Không chạy `pg_stat_reset()` hoặc reset extension statistics giữa sự cố khi chưa lưu snapshot và chưa hiểu tác động. Reset làm mất baseline tích lũy, gây khó so sánh trước/sau và có thể ảnh hưởng dashboard khác.

Thay vào đó, lấy hai snapshot theo timestamp và tính delta. Với log, sao lưu đoạn liên quan trước khi rotation hoặc retention xóa.

### 8.3. Bảo vệ dữ liệu nhạy cảm

Query text, bind parameters, log và trace có thể chứa email, token, thông tin khách hàng hoặc dữ liệu giao dịch. Giới hạn quyền đọc, che literal khi lưu vào báo cáo và tuân thủ retention của tổ chức. Không sao chép toàn bộ payload nhạy cảm vào kênh trao đổi sự cố nếu query fingerprint và correlation ID đã đủ để điều tra.

### 8.4. Ghi lại mọi thay đổi

Với mỗi hành động giảm tải, ghi:

| Trường | Ví dụ |
|---|---|
| Thời điểm | 14:05:20 UTC+7 |
| Lý do | Pool pending tăng và report scan chiếm I/O |
| Thay đổi | Giảm report worker từ 12 xuống 3 |
| Phạm vi | Nhóm job báo cáo |
| Thời hạn | Tạm áp dụng 30 phút rồi đánh giá |
| Kết quả | Storage queue giảm, API p95 trở lại vùng mục tiêu |
| Hoàn tác | Khôi phục worker theo từng nấc sau khi backlog ổn định |

Giá trị trong bảng chỉ minh họa. Ghi cả hành động không có tác dụng hoặc làm xấu hệ thống để tránh lặp lại.

## 9. Khôi phục traffic theo từng giai đoạn

Khi metric bắt đầu cải thiện, không nên lập tức mở toàn bộ concurrency hoặc chạy lại tất cả batch job. Queue có thể còn backlog, cache chưa ổn định, replica còn lag và vacuum chưa theo kịp.

### 9.1. Điều kiện bắt đầu khôi phục

Trước khi tăng tải, xác nhận:

- Latency và error rate đã ổn định trong một khoảng quan sát phù hợp.
- CPU, memory và I/O còn headroom ở tải hiện tại.
- Connection pool không còn hàng đợi tăng liên tục.
- Lock wait và blocking chain đã giảm.
- WAL/archive/replication không tiếp tục tích lũy ngoài kiểm soát.
- Free space đủ cho workload và các tác vụ nền sắp chạy.
- Không còn transaction ở trạng thái không rõ hoặc connection lỗi được trả về pool.
- Tác vụ đã tạm dừng có checkpoint/offset và có thể tiếp tục an toàn.

### 9.2. Tăng tải từng nấc

Có thể dùng các nấc minh họa như 10%, 25%, 50%, 75% rồi 100% concurrency mục tiêu. Tỷ lệ cụ thể tùy hệ thống. Mỗi nấc cần có khoảng quan sát đủ dài để thấy p95/p99, queue, I/O và backlog.

Ở mỗi nấc:

1. Tăng một nhóm traffic hoặc worker.
2. Chờ hệ thống đạt trạng thái ổn định.
3. So sánh metric với ngưỡng đã định nghĩa.
4. Kiểm tra query mix và số lỗi.
5. Tiếp tục nếu ổn định; giảm lại nếu latency, queue hoặc error tăng bất thường.

Không tăng traffic chỉ dựa trên CPU thấp. Hệ thống có thể bị giới hạn bởi I/O, lock hoặc connection pool dù CPU chưa cao.

### 9.3. Xử lý backlog

Sau khi khôi phục request tương tác, backlog của queue hoặc batch cần được xử lý theo tốc độ mà database chịu được.

- Đo tốc độ tạo backlog và tốc độ tiêu thụ.
- Ưu tiên dữ liệu theo SLA và tuổi message.
- Giới hạn consumer concurrency để tránh tạo burst mới.
- Dùng idempotency và checkpoint để xử lý lại an toàn.
- Theo dõi WAL, replication lag, temp và I/O trong lúc catch-up.
- Không chạy đồng thời mọi job bị hoãn nếu chúng cùng ghi vào một bảng hoặc volume.

Nếu tốc độ consumer thấp hơn tốc độ dữ liệu mới đến, backlog sẽ tiếp tục tăng. Cần điều chỉnh admission control, năng lực xử lý hoặc lịch chạy, không chỉ tăng worker vô hạn.

### 9.4. Hoàn tác biện pháp giảm tải

Các biện pháp tạm thời phải có chủ sở hữu và điều kiện kết thúc. Khi ổn định:

- Khôi phục feature flag theo từng nhóm.
- Mở lại report và batch theo lịch có kiểm soát.
- Trả concurrency/pool limit về giá trị đã xác nhận.
- Gỡ timeout tạm thời nếu chúng không còn phù hợp.
- Xác nhận không còn client retry theo cấu hình cũ.
- Giữ lại metric và timeline để đánh giá hiệu quả.

Không khôi phục một cấu hình cũ nếu chính nó là nguyên nhân đã được xác nhận. Khi đó cần thay bằng cấu hình mục tiêu mới và ghi rõ quyết định.

## 10. Xác minh phục hồi

Một hệ thống không được coi là phục hồi chỉ vì dashboard hết màu đỏ hoặc một truy vấn thử chạy nhanh. Cần xác nhận cả trải nghiệm người dùng, database, backlog và tính đúng đắn dữ liệu.

### 10.1. Xác minh ở tầng ứng dụng

- Request rate trở lại mức dự kiến.
- p50/p95/p99 nằm trong SLA hoặc vùng baseline chấp nhận được.
- Error, timeout và retry rate giảm về ngưỡng bình thường.
- Pool pending gần bằng 0 trong điều kiện tải ổn định.
- Queue backlog giảm theo tốc độ dự kiến.
- Không còn endpoint bị degraded ngoài kế hoạch.

### 10.2. Xác minh ở tầng database

- Active sessions và số connection phù hợp với throughput.
- Không còn blocking chain bất thường hoặc transaction quá lâu.
- Top query trở lại mức thời gian và số lần gọi dự kiến.
- Buffer read, temp spill, CPU và I/O không tiếp tục tăng bất thường.
- WAL generation, checkpoint và commit latency ổn định.
- Autovacuum bắt kịp và XID age vẫn trong ngưỡng an toàn.
- Replication lag và archive backlog giảm hoặc nằm trong mục tiêu.

### 10.3. Xác minh tính đúng đắn dữ liệu

Đối chiếu các nghiệp vụ bị ảnh hưởng:

- Số request thành công và số giao dịch commit.
- Số bản ghi được tạo/cập nhật so với message đã xử lý.
- Duplicate hoặc event bị xử lý lặp.
- Transaction có kết quả commit không rõ do timeout/mất kết nối.
- Tổng số tiền, số lượng hoặc aggregate quan trọng theo nghiệp vụ.
- Trạng thái dữ liệu giữa primary, replica và read model.

Nếu client timeout trong lúc commit, không mặc định transaction thất bại. Tra cứu bằng idempotency key, transaction ID nghiệp vụ hoặc bảng kết quả trước khi gửi lại thao tác có tác dụng phụ.

### 10.4. Quan sát đủ lâu

Một số vấn đề chỉ xuất hiện khi checkpoint, autovacuum, backup hoặc batch job chạy lại. Duy trì thời gian quan sát sau khi mở traffic và bao phủ ít nhất một chu kỳ của công việc nền có ảnh hưởng. Ghi rõ khoảng thời gian đã quan sát và những job chưa được chạy lại.

## 11. Ví dụ xử lý sự cố: API ghi đơn hàng chậm do lock và retry

Giả sử API cập nhật trạng thái đơn hàng có p99 tăng từ 180 ms lên 4 giây. Pool pending tăng, số session chờ lock nhiều và retry rate tăng sau một lần phát hành.

### Bước 1 — Xác nhận ảnh hưởng

Trace cho thấy request chờ database. `pg_stat_activity` có nhiều backend với `wait_event_type = 'Lock'`; một backend có transaction age 3 phút và đang giữ khóa trên bảng trạng thái đơn hàng. Application log cho thấy client retry khi timeout.

### Bước 2 — Thu thập bằng chứng

Lưu snapshot activity, blocking chain, query fingerprint, transaction age, pool pending, retry rate và thời điểm release. Xác định ứng dụng sở hữu blocker và câu lệnh đã chạy trong transaction.

### Bước 3 — Giảm tải

- Giảm concurrency của endpoint cập nhật trạng thái.
- Tạm hoãn batch đồng bộ trạng thái không thiết yếu.
- Giảm retry tự động cho timeout chưa xác định trạng thái commit.
- Từ chối sớm request mới nếu deadline không còn đủ.

Sau khi xác định blocker, người điều phối phối hợp với chủ sở hữu ứng dụng để quyết định cancel hoặc terminate session. Nếu transaction có thể rollback lớn, phải cân nhắc thời gian và tác động trước khi hành động.

### Bước 4 — Quan sát sau can thiệp

Sau khi blocker kết thúc, theo dõi lock wait, rollback duration, pool pending, p99 và throughput. Không lập tức mở lại toàn bộ concurrency nếu queue vẫn còn lớn.

### Bước 5 — Khôi phục và kiểm tra dữ liệu

Mở traffic theo từng nấc. Tra cứu các request có kết quả commit không rõ bằng idempotency key, kiểm tra duplicate và đối chiếu số trạng thái đơn hàng đã cập nhật. Chỉ chạy lại batch sau khi xác nhận checkpoint và khả năng deduplication.

### Bước 6 — Khắc phục lâu dài

Điều tra transaction dài trong release, rút ngắn thời gian giữ khóa, chuẩn hóa thứ tự cập nhật, sửa retry policy và thêm metric cho transaction age, blocking chain cùng pool pending. Chạy load test với cùng workload để xác nhận regression đã được xử lý.

## 12. Những sai lầm thường gặp khi xử lý sự cố

- **Chỉ tăng connection pool:** có thể đẩy thêm concurrency vào database đang bão hòa và làm tình hình xấu hơn.
- **Tăng `max_connections` ngay:** tăng số backend có thể làm memory và scheduling pressure lớn hơn.
- **Tăng timeout toàn cục:** request giữ connection lâu hơn và hàng đợi có thể tích lũy nhanh hơn.
- **Retry ngay khi timeout:** tạo retry storm và có thể thực hiện lặp nghiệp vụ nếu commit đã thành công.
- **Kill session lâu nhất mà không xem blocker:** session lâu có thể là công việc hợp lệ; terminate có thể rollback lớn.
- **Reset thống kê trước khi chụp snapshot:** làm mất dữ liệu so sánh và bối cảnh sự cố.
- **Chạy `EXPLAIN ANALYZE` cho mọi query trên production:** lệnh thực thi query và có thể làm tăng tải hoặc tạo tác dụng phụ.
- **Dừng autovacuum toàn cục:** giảm tải trước mắt nhưng có thể tạo bloat và rủi ro XID wraparound.
- **Chạy nhiều maintenance cùng lúc:** backup, reindex, vacuum và batch có thể cạnh tranh cùng storage.
- **Khôi phục toàn bộ traffic ngay khi CPU giảm:** backlog, lock, I/O hoặc replication lag có thể chưa hồi phục.
- **Chỉ nhìn dashboard xanh:** chưa chứng minh dữ liệu đúng hoặc backlog đã được xử lý.
- **Không ghi timeline:** khó xác định biện pháp nào giúp hoặc gây tác động phụ.
- **Không hoàn tác giới hạn tạm thời:** cấu hình giảm tải có thể vô tình trở thành giới hạn năng lực lâu dài.

## 13. Checklist giảm tải, thu thập bằng chứng và phục hồi

- [ ] Đã xác nhận phạm vi ảnh hưởng, thời điểm bắt đầu và workload bị ảnh hưởng.
- [ ] Đã chỉ định người điều phối và ghi timeline hành động.
- [ ] Đã lấy snapshot an toàn của request rate, p95/p99, error, pool và queue.
- [ ] Đã lưu `pg_stat_activity`, wait events và transaction age.
- [ ] Đã xác định blocking chain/root blocker nếu có lock contention.
- [ ] Đã lưu top query fingerprint và thống kê tích lũy trước khi reset bất kỳ số liệu nào.
- [ ] Đã đối chiếu CPU, memory, I/O, WAL, checkpoint, temp và free space.
- [ ] Đã chọn biện pháp giảm tải theo bottleneck và mức độ quan trọng của workload.
- [ ] Mọi giới hạn tạm thời có phạm vi, chủ sở hữu, thời hạn và cách hoàn tác.
- [ ] Retry có giới hạn, backoff, jitter và xử lý idempotency phù hợp.
- [ ] Query/session bị hủy đã được xác minh về transaction state và tác động rollback.
- [ ] Traffic được mở lại theo từng nấc và có khoảng quan sát.
- [ ] Queue backlog, WAL/archive và replication lag đã được xử lý hoặc có kế hoạch rõ.
- [ ] Đã đối chiếu giao dịch commit, duplicate và kết quả nghiệp vụ.
- [ ] Đã xác nhận p95/p99, throughput, error rate và tài nguyên ổn định qua chu kỳ nền liên quan.
- [ ] Đã ghi nguyên nhân, yếu tố góp phần, hành động lâu dài và bài học vận hành.

## 14. Mẫu ghi nhận sự cố

Có thể dùng cấu trúc sau để giữ báo cáo ngắn gọn nhưng đủ dữ liệu điều tra:

| Mục | Nội dung |
|---|---|
| Incident ID | Mã sự cố theo hệ thống vận hành |
| Thời gian | Phát hiện, bắt đầu ảnh hưởng, ổn định và kết thúc |
| Phạm vi | Database, endpoint, tenant, read/write và người dùng ảnh hưởng |
| Triệu chứng | p95/p99, error rate, throughput, pool, queue |
| Bằng chứng | Query fingerprint, plan, wait event, blocking chain, I/O, WAL |
| Giả thuyết | Bottleneck và dữ liệu hỗ trợ |
| Giảm tải | Hành động, phạm vi, giá trị trước/sau, thời hạn |
| Kết quả | Metric thay đổi sau từng hành động |
| Phục hồi | Các nấc mở traffic, backlog và consistency checks |
| Nguyên nhân | Nguyên nhân gốc và yếu tố góp phần đã xác nhận |
| Hành động tiếp theo | Owner, thời hạn, metric/cảnh báo và test cần bổ sung |

Phân biệt rõ **nguyên nhân đã xác nhận**, **giả thuyết còn mở** và **điều chưa biết**. Không ghi một tương quan thời gian thành nguyên nhân gốc nếu chưa có bằng chứng.

## Kết luận

Giảm tải tạm thời giúp database thoát khỏi trạng thái hàng đợi và concurrency vượt khả năng phục vụ. Biện pháp cần khớp với bottleneck: giới hạn request và worker, dừng workload không thiết yếu, giảm retry, hủy query có mục tiêu hoặc cô lập nhóm truy vấn nặng. Trước và sau mỗi can thiệp, thu thập bằng chứng từ ứng dụng, `pg_stat_activity`, query statistics, lock, WAL, I/O và hệ điều hành; ghi rõ thời điểm, phạm vi và tác động.

Khi hệ thống bắt đầu ổn định, khôi phục traffic theo từng nấc, xử lý backlog có kiểm soát và xác minh cả latency, throughput, tài nguyên lẫn tính đúng đắn dữ liệu. Chỉ coi sự cố đã phục hồi khi request quan trọng đáp ứng SLA, hàng đợi không tiếp tục tăng, replication và tiến trình nền nằm trong giới hạn, giao dịch có kết quả rõ ràng và các biện pháp tạm thời đã được hoàn tác hoặc thay bằng cấu hình mục tiêu. Bằng chứng và timeline thu thập được là cơ sở để sửa nguyên nhân gốc và ngăn sự cố tái diễn.
