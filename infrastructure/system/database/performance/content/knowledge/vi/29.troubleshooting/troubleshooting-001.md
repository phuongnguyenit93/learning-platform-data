# Quy trình khoanh vùng từ triệu chứng đến truy vấn và tài nguyên

Khi ứng dụng báo chậm, database timeout hoặc số request lỗi tăng, nguyên nhân chưa chắc nằm ở câu SQL vừa được triển khai. Hàng đợi có thể tăng ở connection pool, một truy vấn khác có thể chiếm CPU, storage có thể bị bão hòa, transaction có thể giữ lock lâu, hoặc replica và mạng có thể không theo kịp. Nếu chỉ nhìn một biểu đồ CPU hay một câu query riêng lẻ, rất dễ sửa nhầm tầng và làm sự cố nặng hơn.

Chẩn đoán hiệu năng cơ sở dữ liệu cần đi theo một chuỗi bằng chứng: **triệu chứng và phạm vi ảnh hưởng → thời điểm và thay đổi liên quan → request/transaction → truy vấn cụ thể → execution plan và wait → tài nguyên đang bị giới hạn**. Mỗi bước thu hẹp tập giả thuyết. Sau khi xử lý, phải đo lại cùng loại workload và xác nhận cả latency, throughput, lỗi lẫn tác động đến các dịch vụ khác.

Bài học này xây dựng quy trình khoanh vùng có thể dùng trong vận hành và tối ưu DATABASE_PERFORMANCE. Nội dung bao gồm cách xác định phạm vi sự cố, nối trace ứng dụng với session và SQL, tìm top query, đọc execution plan, phân biệt CPU/I/O/memory/lock/network bottleneck, dùng công cụ của PostgreSQL, MySQL, SQL Server và Oracle, chọn biện pháp giảm tác động, rồi xác minh và lưu lại kết quả.

## 1. Bắt đầu từ triệu chứng có thể đo được

Một báo cáo như “database chậm” chưa đủ để chẩn đoán. Hãy chuyển nó thành những biểu hiện có thể kiểm tra:

- Request latency p50, p95 hoặc p99 tăng bao nhiêu?
- Throughput request hoặc transaction giảm hay vẫn giữ nguyên?
- Lỗi timeout, connection refused, deadlock hoặc query cancellation tăng từ lúc nào?
- Chỉ một API, một tenant, một truy vấn hay toàn bộ ứng dụng bị ảnh hưởng?
- Chỉ đọc chậm, ghi chậm, commit chậm hay cả hai?
- Sự cố xảy ra liên tục, theo chu kỳ, trong giờ cao điểm hay sau một job?
- Database primary, replica, một node cluster hay toàn bộ topology bị ảnh hưởng?

### 1.1. Phân biệt latency và throughput

Latency là thời gian một request hoặc query hoàn tất. Throughput là số công việc hoàn tất trong một đơn vị thời gian. Hai chỉ số cần được đọc cùng nhau.

Ví dụ:

| Tình huống | Latency | Throughput | Gợi ý |
|---|---|---|---|
| Request chậm hơn nhưng số request/giây giữ nguyên | Tăng | Ổn định | Có thể xuất hiện wait hoặc queue mới |
| Request chậm hơn và số transaction/giây giảm | Tăng | Giảm | Có thể đã chạm giới hạn tài nguyên hoặc contention |
| p99 tăng, p50 gần như giữ nguyên | Đuôi phân phối xấu | Có thể ổn định | Một nhóm query/key/tenant bị ảnh hưởng |
| Pool acquire wait tăng, DB query time ổn định | Tăng ở ứng dụng | Có thể giảm | Connection bị giữ lâu hoặc pool thiếu |

Không dùng average latency làm chỉ số duy nhất. Một số ít truy vấn rất chậm có thể làm p99 tăng mạnh dù trung bình thay đổi ít.

### 1.2. Xác định phạm vi

Ghi lại:

- Dịch vụ, endpoint, tenant hoặc nhóm người dùng bị ảnh hưởng.
- Query type: point lookup, range scan, join, aggregate, insert, update hoặc batch.
- Database, node, schema, bảng và partition liên quan nếu đã biết.
- Tỷ lệ request lỗi và số người dùng bị ảnh hưởng.
- Thời điểm bắt đầu, thời điểm đạt đỉnh và trạng thái hiện tại.

Phạm vi càng rõ thì càng dễ chọn dữ liệu cần xem. Nếu chỉ một tenant bị chậm, cần kiểm tra skew hoặc hot key. Nếu mọi tenant đều chậm cùng thời điểm, cần xem tài nguyên chung, deploy, backup, checkpoint hoặc hạ tầng.

## 2. Lập timeline và lấy baseline

Trước khi thay đổi cấu hình hoặc kill session, hãy dựng timeline:

1. Thời điểm cuối cùng hệ thống hoạt động bình thường.
2. Thời điểm latency hoặc lỗi bắt đầu tăng.
3. Các deploy, migration, thay đổi index, cấu hình, secret hoặc connection pool gần thời điểm đó.
4. Các job batch, report, backup, vacuum, index maintenance hoặc import chạy cùng thời gian.
5. Sự kiện hạ tầng như failover, storage latency, CPU quota, network change hoặc autoscaling.
6. Thời điểm áp dụng biện pháp giảm tác động và kết quả quan sát được.

Baseline là trạng thái bình thường có thể so sánh: throughput, p50/p95/p99, active sessions, CPU, I/O, lock wait, pool usage và replication lag. Nếu có baseline theo giờ/ngày trong tuần, hãy so với cùng khung thời gian để tránh nhầm tải theo mùa vụ với sự cố.

### 2.1. So sánh cùng cửa sổ thời gian

Các thống kê tích lũy từ lúc database khởi động có thể che khuất sự cố mới. Khi dùng counter tổng, cần lấy hai snapshot và tính delta trong cùng cửa sổ:

\[
\Delta metric = value_{t2} - value_{t1}
\]

Tốc độ gần đúng:

\[
rate = \frac{\Delta metric}{t2-t1}
\]

Nếu counter bị reset do restart hoặc failover, delta có thể âm hoặc sai. Ghi nhận thời điểm reset và không so sánh trực tiếp các khoảng không tương đương.

### 2.2. Tránh kết luận từ một snapshot

Một lần xem process list chỉ cho biết trạng thái tại một thời điểm. Query có thể đã kết thúc trước khi lấy snapshot hoặc chỉ chậm theo burst. Thu thập mẫu lặp theo khoảng ngắn phù hợp, nhưng tránh polling quá dày làm tăng tải hệ thống.

## 3. Theo dấu từ request đến database

Một request có thể đi qua nhiều tầng:

~~~text
Client
  -> API gateway
  -> Application queue / executor
  -> Connection pool acquire
  -> Network to database
  -> Database session / transaction
  -> SQL execution and resource waits
  -> Result transfer
  -> Application processing
  -> Response
~~~

Tổng thời gian request không đồng nghĩa với thời gian SQL chạy. Cần chia thời gian thành:

- Thời gian chờ ứng dụng hoặc executor.
- Thời gian chờ lấy connection.
- Thời gian thiết lập hoặc chờ mạng.
- Thời gian database thực thi và chờ tài nguyên.
- Thời gian truyền kết quả.
- Thời gian ứng dụng xử lý dữ liệu sau khi nhận.

### 3.1. Dùng correlation ID và trace

Mỗi request nên có correlation ID hoặc trace ID. Khi có thể, ghi cùng ID vào log ứng dụng, span database và thông tin session/query ở mức an toàn.

Các trường hữu ích:

- Request/trace ID.
- Service và instance.
- Tenant hoặc workload class ở dạng không nhạy cảm.
- Query fingerprint hoặc statement name.
- Database host/role.
- Transaction start/end.
- Connection checkout/check-in.
- Query start/end và timeout.

Không ghi toàn bộ bind parameter chứa thông tin nhạy cảm vào log chỉ để chẩn đoán. Có thể dùng query fingerprint, kiểu tham số, bucket giá trị hoặc dữ liệu đã che.

### 3.2. Phân biệt pool wait và database wait

Nếu request mất 2 giây nhưng query thực thi chỉ 30 ms, cần tìm 1,97 giây còn lại nằm ở đâu. Ví dụ:

- Pool acquire wait: 1,2 giây.
- Network round trip: 20 ms.
- Database execution: 30 ms.
- Application processing: 750 ms.

Tăng index hoặc viết lại SQL không giải quyết được phần lớn thời gian này. Cần điều tra pool capacity, connection hold time và ứng dụng.

Ngược lại, nếu pool acquire gần 0 nhưng database execution tăng từ 30 ms lên 1,5 giây, cần xem query plan và wait events.

## 4. Xác định query nào đang gây ảnh hưởng

Không nhất thiết query đang chạy lâu nhất tại thời điểm lấy mẫu là nguyên nhân lớn nhất. Cần xem query theo nhiều góc:

- Tổng thời gian tiêu thụ trong cửa sổ.
- Số lần gọi.
- Thời gian trung bình và percentile.
- CPU time.
- Logical/physical reads.
- Số hàng trả về và số hàng đọc.
- Số lần sort/hash spill.
- Lock wait hoặc blocking time.
- Tần suất lỗi và timeout.

### 4.1. Tổng thời gian và thời gian trung bình

Một query mất 2 giây nhưng chỉ chạy một lần có thể ít gây tải hơn query mất 20 ms nhưng chạy 20.000 lần mỗi phút.

Hai cách xếp hạng hữu ích:

- **Total cost in window:** tìm nhóm query tiêu thụ tài nguyên tổng cộng lớn.
- **Per-call latency:** tìm query chậm đối với từng request.

Nên xem thêm calls/second để nhận diện query nhỏ nhưng tần suất rất cao.

### 4.2. Query fingerprint

Query fingerprint chuẩn hóa literal để nhóm các câu có cùng cấu trúc:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 123;

SELECT *
FROM orders
WHERE customer_id = 456;
~~~

Hai câu trên có thể được gom thành cùng một fingerprint. Điều này giúp tìm mẫu query thay vì phải đọc từng literal. Tuy nhiên, cùng fingerprint vẫn có thể có latency khác nhau do parameter skew, cache, plan hoặc tenant size.

### 4.3. Query mới và query bị regression

Đối chiếu query fingerprint trước và sau deploy:

- Query mới xuất hiện?
- Số lần gọi tăng đột biến?
- Một query cũ có execution time tăng?
- Plan hash hoặc operator thay đổi?
- Tham số mới làm selectivity khác?
- ORM tạo N+1 query?
- Một endpoint gọi query lặp trong vòng lặp?

Nếu sự cố bắt đầu ngay sau deploy, so sánh version ứng dụng, SQL fingerprint và plan là hướng khoanh vùng có giá trị cao.

## 5. Đọc execution plan theo bằng chứng

Execution plan mô tả cách optimizer dự kiến hoặc thực tế thực thi truy vấn. Khi điều tra, ưu tiên actual execution plan hoặc runtime statistics nếu có thể lấy an toàn.

Các thành phần cần đọc:

- Scan type: table scan, sequential scan, index scan, index seek hoặc range scan.
- Join algorithm: nested loop, hash join, merge join.
- Estimated rows so với actual rows.
- Predicate và residual filter.
- Sort, aggregate, spool, materialize.
- Memory grant, spill và temp I/O.
- Partition pruning hoặc số partition được truy cập.
- Parallel workers và mức phân phối công việc.
- Buffer reads, physical reads và elapsed/CPU time.

### 5.1. Sai lệch cardinality estimate

Nếu optimizer ước lượng 100 hàng nhưng thực tế trả về 2 triệu, plan có thể chọn join order, index hoặc memory grant không phù hợp.

Nguyên nhân có thể:

- Statistics cũ hoặc không đại diện.
- Skew và heavy hitters.
- Tương quan giữa các cột không được mô hình hóa.
- Parameter-sensitive query.
- Predicate có hàm hoặc implicit conversion.
- Dữ liệu thay đổi nhanh sau lần analyze.

Hãy tìm operator đầu tiên có chênh lệch lớn giữa estimated rows và actual rows. Sai số ở một operator sớm có thể lan sang toàn bộ phần còn lại của plan.

### 5.2. Đừng suy luận từ tên operator

Table scan không tự động là xấu. Với bảng nhỏ hoặc truy vấn đọc phần lớn hàng, scan có thể rẻ hơn index lookup. Index seek cũng không bảo đảm nhanh nếu phải thực hiện hàng triệu lần hoặc truy cập nhiều page rời rạc.

Đánh giá theo số hàng thực tế, bytes đọc, số lần lặp, cache, CPU và I/O.

### 5.3. Actual plan có thể thực thi truy vấn

Một số lệnh như EXPLAIN ANALYZE thực sự chạy statement. Với SELECT thường ít rủi ro hơn, nhưng vẫn tiêu thụ tài nguyên và có thể gọi function có side effect. Với UPDATE/DELETE/INSERT, việc đo có thể thay đổi dữ liệu.

Chỉ dùng actual plan cho DML khi đã có transaction/rollback hoặc môi trường kiểm thử phù hợp và hiểu rõ side effect. Không chạy một câu DML production chỉ để “xem plan”.

## 6. Phân biệt các nhóm bottleneck

Một quy trình khoanh vùng hiệu quả cần xác định tài nguyên nào đang giới hạn tiến độ.

| Nhóm | Dấu hiệu thường gặp | Bằng chứng cần lấy |
|---|---|---|
| CPU | CPU/runnable queue cao, query CPU time lớn | Top CPU query, per-core utilization, throttling |
| Data I/O | Physical read cao, storage latency/queue tăng | Read latency, IOPS, throughput, buffer misses |
| Log I/O | Commit chậm, log flush wait tăng | WAL/redo/log bytes, flush latency, log device |
| Memory | Sort/hash spill, memory grant wait, swap | Memory grant, temp usage, buffer/cache pressure |
| Lock | Blocked sessions, lock wait, deadlock | Blocking chain, blocker age, lock type/resource |
| Latch/internal contention | CPU có thể cao nhưng tiến độ thấp | Wait events/latches, hot page/key |
| Network | Round trip, packet loss hoặc result transfer tăng | Network RTT, retransmit, bytes/result size |
| Connection/pool | Acquire wait và pending request tăng | Active/idle/pending pool, checkout duration |
| Worker/scheduler | Worker queue, parallel imbalance, thread shortage | Runnable tasks, worker availability, actual DOP |

Không phải mọi wait đều là lỗi. Wait có thể là hệ thống đang phối hợp bình thường. Cần tìm wait chiếm thời gian đáng kể, tăng so với baseline và liên quan tới request bị ảnh hưởng.

## 7. Khoanh vùng CPU bottleneck

Dấu hiệu:

- CPU utilization cao kéo dài ở host/container.
- Run queue hoặc runnable task tăng.
- Query CPU time cao và throughput không tăng tương ứng.
- Nhiều truy vấn hash, sort, expression hoặc scan tiêu thụ CPU.
- CPU quota throttling hoặc VM CPU ready tăng.

Các câu hỏi:

- Một query có chiếm phần lớn CPU hay nhiều query nhỏ cộng lại?
- CPU có dồn vào một core hoặc NUMA node không?
- Có tăng parallel worker hoặc connection concurrency gần đây không?
- Có job statistics, index build, compression hoặc ETL chạy cùng lúc?
- CPU usage cao do DB hay process khác trên host?

Hướng điều tra:

1. Xếp hạng query theo CPU trong cửa sổ sự cố.
2. Xem actual plan và số hàng xử lý.
3. Kiểm tra DOP, worker imbalance và oversubscription.
4. Kiểm tra CPU quota, throttling và VM scheduling.
5. So sánh CPU time với elapsed time để nhận biết phần chờ.

Biện pháp giảm tác động có thể gồm giới hạn concurrency, tạm hoãn job nặng, giảm DOP cho workload phân tích, tối ưu query hoặc thêm CPU capacity sau khi chứng minh CPU là giới hạn. Không tăng DOP tự động khi CPU đã bão hòa.

## 8. Khoanh vùng data I/O và log I/O

### 8.1. Data I/O

Dấu hiệu:

- CPU không quá cao nhưng query elapsed time lớn.
- Physical read hoặc storage queue tăng.
- Read latency cao hơn baseline.
- Buffer cache hit giảm hoặc working set vượt bộ nhớ.
- Nhiều query cùng đọc bảng/index lớn.

Kiểm tra:

- Số logical reads và physical reads theo query.
- Bytes read, IOPS và throughput storage.
- Latency theo volume/device.
- Buffer pool/cache pressure.
- Scan lớn hoặc index lookup ngẫu nhiên.
- Backup, scan hoặc ETL cạnh tranh storage.

Nếu query đọc quá nhiều hàng, xem predicate, index và partition pruning. Nếu truy vấn cần đọc phần lớn bảng, một scan tuần tự có thể hợp lý; khi đó tối ưu có thể nằm ở storage throughput, partitioning hoặc thời điểm chạy.

### 8.2. Log I/O

Dấu hiệu:

- COMMIT latency tăng.
- Wait liên quan log flush/fsync tăng.
- Write throughput trên log volume cao.
- Transaction ghi nhỏ nhưng commit thường xuyên.
- WAL/redo/log generation tăng nhanh.

Kiểm tra số transaction/s, log bytes/s, log flush latency, batch size, synchronous replication và log device. Không giảm durability hoặc tắt logging như biện pháp chữa cháy nếu chưa đánh giá yêu cầu phục hồi và độ bền dữ liệu.

## 9. Khoanh vùng memory pressure và spill

Sort, hash join, hash aggregate và một số operator cần bộ nhớ làm việc. Nếu memory grant không đủ, DBMS có thể spill dữ liệu trung gian xuống temp storage.

Dấu hiệu:

- Sort/hash warning hoặc spill level xuất hiện.
- Temp file/tempdb usage tăng.
- Query latency tăng mạnh khi cardinality lớn.
- Memory grant wait hoặc memory pressure tăng.
- Một số query song song tiêu thụ nhiều memory cùng lúc.

Kiểm tra:

- Estimated rows so với actual rows.
- Memory grant yêu cầu và thực tế.
- Dung lượng spill và số lần spill.
- Số query đồng thời dùng memory workspace.
- Statistics và skew.
- Temp storage latency.

Không tăng memory grant toàn cục ngay khi thấy spill. Estimate sai có thể cấp quá ít hoặc quá nhiều; tăng grant có thể làm giảm số query chạy đồng thời. Trước tiên sửa statistics, query shape hoặc concurrency nếu có bằng chứng.

## 10. Khoanh vùng lock, blocking và deadlock

### 10.1. Blocking chain

Một query chờ lock có thể bị chặn bởi transaction khác. Transaction blocker có thể đang chạy query, đang chờ remote service hoặc idle in transaction.

Hãy dựng blocking chain:

~~~text
Request A waits for row/page/key
    |
    v
Transaction B holds the resource
    |
    v
Session B may be running SQL or idle in transaction
~~~

Thông tin cần thu thập:

- Blocking session ID và waiting session ID.
- Lock resource, mode và object.
- Thời điểm transaction bắt đầu.
- SQL hiện tại và câu lệnh gần nhất của blocker.
- Ứng dụng/instance/trace ID nếu có.
- Số session bị chặn và thời gian chờ.

### 10.2. Deadlock

Deadlock xảy ra khi các transaction chờ lẫn nhau tạo thành chu trình. DBMS thường chọn một transaction làm victim để rollback.

Điều tra deadlock:

- Thu thập deadlock graph hoặc log tương ứng.
- Xác định bảng, index, key và lock mode.
- So sánh thứ tự truy cập tài nguyên giữa các transaction.
- Kiểm tra transaction duration và batch size.
- Xem retry có làm tăng tải hay không.

Biện pháp có thể là thống nhất thứ tự cập nhật, rút ngắn transaction, thêm index giúp giảm phạm vi lock, chia batch hoặc điều chỉnh isolation theo yêu cầu. Không hạ isolation level chỉ để làm biến mất wait mà không kiểm tra correctness.

### 10.3. Khi nào nên kết thúc blocker?

Kết thúc session có thể giải phóng lock nhưng cũng có thể kích hoạt rollback lớn, làm tăng I/O và gây mất công việc chưa commit. Chỉ làm khi đã xác định blocker, hiểu tác động rollback và có quyền vận hành. Nếu blocker là migration hoặc giao dịch nghiệp vụ quan trọng, phối hợp với chủ sở hữu workload và dùng quy trình incident của hệ thống.

## 11. Khoanh vùng network và connection pool

Nếu thời gian request cao nhưng query execution thấp, kiểm tra:

- Pool acquire wait và số connection active.
- Connection checkout duration.
- Connection creation rate và lỗi reconnect.
- Network round-trip time giữa app và DB.
- Packet loss/retransmission.
- Kích thước result set và thời gian truyền.
- Client fetch size và streaming behavior.
- DNS, TLS handshake hoặc proxy latency.

Một truy vấn trả về hàng triệu hàng có thể hoàn tất phía server tương đối nhanh nhưng truyền kết quả và deserialize ở ứng dụng mất nhiều thời gian. Hãy đo bytes trả về, số hàng và thời gian fetch, không chỉ thời gian server-side execution.

Nếu pool pending tăng nhưng database active session thấp, kiểm tra connection leak, transaction giữ connection lâu, thread bị treo hoặc pool max quá nhỏ. Nếu database active session và CPU/IO đều cao, tăng pool có thể đẩy thêm concurrency xuống database và làm sự cố nặng hơn.

## 12. Các nguồn quan sát phổ biến theo DBMS

Tên view, trường, quyền và mức chi tiết thay đổi theo phiên bản. Dùng các nguồn sau như điểm bắt đầu, sau đó đối chiếu tài liệu của phiên bản đang vận hành.

### 12.1. PostgreSQL

Các nguồn thường dùng:

- pg_stat_activity: session, state, query, transaction age và wait event.
- pg_stat_statements: calls, total/mean execution time, rows và block statistics theo query fingerprint.
- pg_locks: lock đang giữ/chờ.
- pg_stat_database và pg_stat_io (phiên bản hỗ trợ): I/O và hoạt động ở mức database.
- pg_stat_replication: vị trí WAL và lag gửi/flush/replay.
- EXPLAIN (ANALYZE, BUFFERS): actual rows, thời gian và buffer usage; lệnh thực thi query.
- auto_explain: ghi plan của query chậm khi đã cấu hình phù hợp.

Ví dụ xem session và wait:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

Ví dụ xem top statement từ pg_stat_statements:

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_ms,
    round(mean_exec_time::numeric, 2) AS mean_ms,
    rows,
    shared_blks_read,
    shared_blks_hit,
    left(query, 250) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Các thống kê pg_stat_statements thường là số liệu tích lũy kể từ lần reset hoặc restart liên quan. Để tìm top query trong một cửa sổ, hãy chụp hai snapshot và lấy delta, hoặc dùng hệ thống monitoring lưu chuỗi thời gian. Không xếp hạng sự cố chỉ bằng tổng tích lũy nhiều ngày.

Để xem plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 9001
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00';
~~~

EXPLAIN ANALYZE thực thi truy vấn. Chạy trên dữ liệu và môi trường phù hợp, với tham số đại diện; không dùng tùy tiện cho statement có side effect.

### 12.2. MySQL

Các nguồn thường dùng:

- Performance Schema: statement digest, wait, stage, lock và file I/O.
- sys schema: view tổng hợp dễ đọc hơn cho nhiều loại hoạt động.
- SHOW PROCESSLIST hoặc performance_schema.threads: session và statement đang chạy.
- EXPLAIN và EXPLAIN ANALYZE: plan và runtime iterator statistics ở phiên bản hỗ trợ.
- SHOW ENGINE INNODB STATUS: deadlock, transaction và trạng thái InnoDB.
- Replication status và Performance Schema replication tables: applier/relay progress.

Ví dụ xem statement theo digest:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Các timer trong Performance Schema dùng đơn vị nội bộ được tài liệu hóa; phép quy đổi cần đúng với phiên bản và timer source. Bảng summary có thể tích lũy từ lúc reset Performance Schema. Dùng snapshot delta để đánh giá đúng cửa sổ sự cố.

EXPLAIN ANALYZE thực thi câu SELECT được phân tích. Kiểm tra tính năng và cú pháp theo phiên bản MySQL; không giả định mọi phiên bản hỗ trợ cùng output.

### 12.3. SQL Server

Các nguồn thường dùng:

- Query Store: lịch sử query, plan và runtime statistics theo khoảng thời gian.
- Actual Execution Plan: actual rows, operator runtime, memory grant và spill.
- sys.dm_exec_requests: request đang chạy và wait.
- sys.dm_exec_sessions: session và trạng thái.
- sys.dm_os_wait_stats: wait tích lũy ở mức instance.
- sys.dm_tran_locks và blocking DMVs: lock và blocker.
- Extended Events: deadlock, timeout hoặc sự kiện cần điều tra.

Ví dụ xem request và wait:

~~~sql
SELECT
    r.session_id,
    r.status,
    r.command,
    r.cpu_time,
    r.total_elapsed_time,
    r.logical_reads,
    r.reads,
    r.writes,
    r.wait_type,
    r.wait_time,
    r.blocking_session_id,
    SUBSTRING(
        t.text,
        (r.statement_start_offset / 2) + 1,
        ((CASE r.statement_end_offset
            WHEN -1 THEN DATALENGTH(t.text)
            ELSE r.statement_end_offset
          END - r.statement_start_offset) / 2) + 1
    ) AS running_statement
FROM sys.dm_exec_requests AS r
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) AS t
WHERE r.session_id <> @@SPID;
~~~

Wait stats ở mức instance là tích lũy. Cần so sánh delta theo thời gian và xem query-level waits nếu có. Một wait type có tổng thời gian cao trong nhiều ngày không nhất thiết là nguyên nhân của sự cố hiện tại.

### 12.4. Oracle Database

Các nguồn thường dùng:

- V$SESSION: session, trạng thái, event và blocking session.
- V$SQL: SQL text, executions, elapsed time, CPU time, buffer gets và disk reads.
- V$SQL_PLAN hoặc DBMS_XPLAN: execution plan và runtime statistics nếu đã thu thập.
- V$SYSTEM_EVENT/V$SESSION_EVENT: wait events.
- ASH/AWR hoặc SQL Monitor: phân tích lịch sử và hoạt động chi tiết tùy phiên bản, quyền và điều kiện cấp phép.
- Data Guard views: transport/apply lag khi sự cố liên quan standby.

Ví dụ xem session đang chờ:

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    sql_id,
    event,
    wait_class,
    seconds_in_wait,
    blocking_session
FROM v$session
WHERE type = 'USER'
ORDER BY seconds_in_wait DESC;
~~~

Ví dụ xem SQL có elapsed time tích lũy lớn:

~~~sql
SELECT
    sql_id,
    executions,
    elapsed_time,
    cpu_time,
    buffer_gets,
    disk_reads,
    rows_processed
FROM v$sql
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

V$SQL counters có thể đại diện nhiều child cursor và thời gian sống của cursor. Cần xem delta, child cursor, plan hash và số executions để tránh kết luận sai từ tổng tích lũy.

## 13. Đọc wait event mà không quy chụp

Wait event mô tả một session hoặc worker đang chờ điều gì. Nó là tín hiệu để đặt câu hỏi tiếp theo, không phải nhãn kết luận.

Ví dụ:

- Wait log flush có thể chỉ ra log device, commit frequency hoặc synchronous replication.
- Wait data file read có thể chỉ ra I/O, cache miss hoặc truy vấn đọc quá nhiều page.
- Lock wait có thể chỉ ra transaction dài hoặc truy cập cùng key.
- Network wait có thể chỉ ra client chậm nhận dữ liệu hoặc mạng.
- Worker/thread wait có thể chỉ ra scheduler, worker limit hoặc parallel plan.

Hãy xem:

1. Wait có tăng trong đúng cửa sổ sự cố không?
2. Wait tập trung ở query, session hoặc workload nào?
3. Wait là nguyên nhân hay hệ quả của một blocker khác?
4. Tổng thời gian wait có lớn so với elapsed time không?
5. Sau khi xử lý nguyên nhân gốc, wait có giảm cùng latency không?

Không tối ưu chỉ để giảm một wait type nếu throughput và latency không cải thiện. Một số wait là hoạt động bình thường của DBMS.

## 14. Một quy trình khoanh vùng theo tầng

Sử dụng thứ tự sau để không bỏ qua hàng đợi ở tầng trên:

### Tầng 1: Ứng dụng và pool

- Request latency, queue, executor saturation.
- Pool active/idle/pending, acquire wait và timeout.
- Connection checkout duration và leak.
- HTTP/RPC dependency latency.

Nếu thời gian chờ pool chiếm phần lớn request, tìm lý do connection chưa được trả về. Nếu query đã gửi tới DB và đang chạy, chuyển xuống tầng database.

### Tầng 2: Session và transaction

- Active, idle, idle in transaction.
- Query age và transaction age.
- Blocking chain, lock wait và deadlock.
- Session nào thuộc service/instance/tenant nào.

Nếu nhiều session chờ cùng một blocker, ưu tiên điều tra transaction giữ lock. Nếu session không bị block nhưng CPU/I/O cao, tìm query tiêu thụ tài nguyên.

### Tầng 3: Query và execution plan

- Top query theo total time, CPU, reads và calls.
- Query mới hoặc query regression.
- Estimated rows/actual rows.
- Scan, join, sort, aggregate, spill và partition pruning.
- Parameter skew và plan variation.

Nếu một query chiếm phần lớn tài nguyên, điều tra plan và predicate. Nếu không có query đơn lẻ nổi bật, có thể là tổng concurrency, workload tăng hoặc tài nguyên chung.

### Tầng 4: Tài nguyên và hạ tầng

- CPU, run queue, throttling và VM scheduling.
- Memory pressure, grant và temp spill.
- Data/log I/O latency và queue depth.
- Network RTT, packet loss và result transfer.
- Disk capacity, log growth, checkpoint và replication.

Nếu DB không có wait bất thường nhưng request vẫn chậm, quay lại application, network và client processing. Không mặc định mọi latency đều nằm trong database engine.

## 15. Ví dụ 1: API chậm nhưng query không chậm

Triệu chứng:

- API p95 tăng từ 120 ms lên 1,8 giây.
- Database CPU vẫn khoảng 35%.
- Query duration trung vị không đổi.
- Connection pool pending tăng.

Phép đo trace:

| Thành phần | Trước sự cố | Trong sự cố |
|---|---:|---:|
| Pool acquire | 2 ms | 1.250 ms |
| SQL execution | 28 ms | 31 ms |
| Application processing | 45 ms | 48 ms |
| Remote service | 20 ms | 260 ms |

Hướng điều tra:

1. Kiểm tra connection checkout duration và transaction boundary.
2. Tìm request giữ connection trong lúc gọi remote service.
3. Xem số connection active và idle in transaction.
4. Kiểm tra retry hoặc remote latency tăng có làm connection giữ lâu hơn không.
5. Tách phần chờ remote ra khỏi transaction nếu nghiệp vụ cho phép, hoặc điều chỉnh pool/admission theo năng lực database.

Không cần bắt đầu bằng việc tạo index vì SQL execution gần như không đổi.

## 16. Ví dụ 2: một truy vấn báo cáo làm chậm nhiều request

Triệu chứng:

- p95 của nhiều endpoint cùng tăng.
- CPU database gần 100%.
- Một query aggregate chạy theo lịch bắt đầu đúng thời điểm sự cố.
- Query dùng hash aggregate và hash join trên bảng lớn.

Hướng điều tra:

1. Xếp hạng query theo CPU trong cửa sổ.
2. Xác nhận report query chiếm tỷ lệ CPU đáng kể.
3. Đọc actual plan, estimated/actual rows và spill.
4. Kiểm tra statistics, filter theo thời gian, partition pruning và index.
5. Xem report có chạy song song quá mức hoặc nhiều bản cùng chạy không.
6. Giảm concurrency hoặc chuyển lịch chạy để giảm tác động ngay.
7. Tối ưu query/summary table và benchmark lại với workload OLTP đồng thời.

Nếu report query đọc phần lớn dữ liệu, một table scan có thể là lựa chọn hợp lý. Nút thắt có thể nằm ở lượng dữ liệu phải aggregate, thiếu summary hoặc chạy sai thời điểm chứ không phải thiếu index.

## 17. Ví dụ 3: ghi chậm do blocking

Triệu chứng:

- Update đơn hàng timeout.
- CPU database thấp.
- Nhiều session chờ lock trên cùng bảng.
- Một transaction bắt đầu từ nhiều phút trước vẫn mở.

Hướng điều tra:

1. Dựng blocking chain và xác định blocker gốc.
2. Xem transaction age, SQL hiện tại và câu lệnh trước đó.
3. Kiểm tra blocker có đang gọi HTTP, chờ người dùng hoặc giữ transaction trong job dài không.
4. Xác định số request bị chặn và tài nguyên đang khóa.
5. Phối hợp chủ sở hữu workload trước khi kết thúc session.
6. Sau khi giải phóng, xem rollback time và lượng backlog.
7. Sửa ranh giới transaction, thứ tự cập nhật hoặc batch size nếu có bằng chứng.

Chỉ nhìn session đang chờ mà không tìm blocker gốc sẽ dẫn tới việc xử lý nhầm nạn nhân thay vì nguyên nhân.

## 18. Chọn biện pháp giảm tác động và sửa nguyên nhân

Trong sự cố đang diễn ra, thường có hai lớp hành động:

### 18.1. Giảm tác động trước

- Tạm hoãn hoặc giới hạn batch/report đang tiêu thụ tài nguyên lớn.
- Giảm concurrency hoặc DOP của workload phân tích.
- Dừng retry storm và đặt backoff.
- Điều tiết request ở application pool/admission control.
- Chuyển workload đọc sang replica nếu freshness và replica health cho phép.
- Rollback một deploy đã được chứng minh gây regression.
- Tăng capacity tạm thời nếu đã xác định rõ resource bottleneck và có thể thực hiện an toàn.

Biện pháp giảm tác động phải có người chịu trách nhiệm, thời điểm áp dụng và cách quay lại. Không thay đổi nhiều tham số cùng lúc vì sẽ mất khả năng xác định yếu tố tạo cải thiện.

### 18.2. Sửa nguyên nhân gốc

Tùy bằng chứng:

- Sửa query shape, predicate hoặc N+1 query.
- Tạo hoặc điều chỉnh index dựa trên access pattern.
- Cập nhật statistics hoặc xử lý skew/parameter sensitivity.
- Giảm transaction duration và lock scope.
- Điều chỉnh batch size, worker count hoặc refresh schedule.
- Sửa pool sizing và connection leak.
- Tăng memory/I/O/CPU capacity khi tài nguyên thực sự thiếu.
- Tách summary/analytical workload khỏi OLTP.
- Sửa network path hoặc client fetch behavior.

Không dùng một biện pháp chung cho mọi loại bottleneck. Tăng RAM không giải quyết deadlock; thêm index không sửa pool acquire wait; tăng max_connections không giải quyết CPU saturation.

## 19. Thứ tự ưu tiên khi có nhiều giả thuyết

Có thể xếp ưu tiên theo:

1. Phạm vi ảnh hưởng và mức độ tác động tới người dùng.
2. Mối liên hệ thời gian với deploy/job/hạ tầng.
3. Bằng chứng định lượng từ trace, query stats và wait.
4. Khả năng tái hiện bằng một request/query đại diện.
5. Mức độ dễ kiểm chứng hoặc loại trừ giả thuyết.
6. Rủi ro và khả năng rollback của biện pháp thử.

Ghi rõ mỗi giả thuyết:

| Giả thuyết | Bằng chứng ủng hộ | Bằng chứng phản bác | Phép kiểm tra tiếp |
|---|---|---|---|
| Pool cạn do transaction dài | Pool active gần max, acquire wait cao | DB active thấp hoặc không có transaction dài | Trace checkout/checkin và transaction age |
| CPU bão hòa bởi report | CPU cao, report top CPU | CPU thấp ở node bị ảnh hưởng | So sánh query CPU và host metrics |
| Lock contention | Blocking chain và lock wait tăng | Không có blocker, wait chủ yếu I/O | Thu deadlock graph/lock sample |
| I/O bão hòa | Storage latency và physical reads tăng | Cache hit cao, I/O queue bình thường | Đo volume latency và query reads |

Không cần chứng minh tất cả giả thuyết sai. Chọn phép kiểm tra có thể phân biệt các nguyên nhân có xác suất cao nhất.

## 20. Xác minh sau khi thay đổi

Một biện pháp chỉ được coi là cải thiện khi kết quả sau thay đổi tốt hơn trên cùng workload và không gây tác động phụ không chấp nhận được.

So sánh trước/sau:

- Request/query throughput.
- p50, p95, p99 latency.
- Error/timeout rate.
- Pool active/pending và acquire wait.
- Active sessions và transaction duration.
- CPU, I/O, memory và temp spill.
- Lock wait, deadlock và blocking duration.
- Log generation và replication lag.
- Kết quả nghiệp vụ và tính toàn vẹn dữ liệu.

Giữ nguyên điều kiện đo càng nhiều càng tốt: dữ liệu, tham số, concurrency, cache state, thời gian chạy và tải nền. Nếu có thay đổi đồng thời, ghi rõ để tránh quy kết nhầm.

### 20.1. Kiểm tra correctness

Sau khi thay đổi SQL, index, isolation, batch hoặc refresh:

- Đối chiếu số hàng và kết quả nghiệp vụ.
- Kiểm tra transaction commit/rollback.
- Kiểm tra duplicate, missing row và foreign key.
- Kiểm tra kết quả với key phổ biến và hiếm.
- Kiểm tra read-after-write hoặc freshness nếu đọc từ replica.
- Kiểm tra retry và xử lý lỗi.

Một query nhanh hơn nhưng trả sai kết quả không phải là tối ưu thành công.

### 20.2. Theo dõi đủ lâu

Một cải thiện trong 5 phút đầu có thể mất đi khi cache, queue, checkpoint hoặc replication ổn định ở trạng thái khác. Theo dõi qua một chu kỳ workload đại diện và cả giờ cao điểm nếu có thể.

## 21. Những sai lầm thường gặp khi troubleshooting

- **Chỉ nhìn CPU tổng.** Có thể bỏ qua pool wait, I/O, lock, quota hoặc một core bão hòa.
- **Chỉ xem query đang chạy lâu nhất.** Query tần suất cao hoặc tổng CPU lớn có thể gây ảnh hưởng hơn.
- **Dùng số liệu tích lũy để kết luận sự cố hiện tại.** Cần delta trong đúng cửa sổ thời gian.
- **Coi wait event là nguyên nhân cuối cùng.** Wait thường chỉ ra nơi session đang chờ, cần tìm blocker hoặc tài nguyên gốc.
- **Cho rằng table scan luôn xấu.** Scan có thể đúng khi cần phần lớn dữ liệu.
- **Chạy EXPLAIN ANALYZE trên DML production mà không kiểm soát.** Lệnh có thể thực sự thay đổi dữ liệu.
- **Tăng pool khi database đã bão hòa.** Có thể tăng concurrency và làm latency tệ hơn.
- **Kill session chờ mà không tìm blocker.** Nạn nhân có thể không phải nguyên nhân.
- **Tăng memory grant toàn cục khi thấy spill.** Có thể làm giảm concurrency và tạo memory pressure.
- **Thay nhiều cấu hình cùng lúc.** Không biết thay đổi nào tạo tác động.
- **Bỏ qua ứng dụng và mạng.** Request latency có thể chủ yếu nằm ngoài database.
- **Không kiểm tra correctness sau khi tối ưu.** Hiệu năng tốt hơn không bảo đảm dữ liệu đúng.
- **Kết thúc điều tra khi biểu đồ trở lại bình thường.** Cần ghi lại nguyên nhân, bằng chứng và biện pháp ngăn tái diễn.

## 22. Runbook khoanh vùng nhanh

Khi nhận cảnh báo database performance, có thể đi theo chuỗi ngắn sau:

1. Xác định endpoint/query/tenant bị ảnh hưởng và mốc thời gian.
2. Xem request latency, throughput và error rate.
3. Tách pool acquire, network, database execution và application processing.
4. Kiểm tra pool pending, active sessions, transaction age và blocker.
5. Lấy top query theo delta CPU/elapsed/reads trong cửa sổ.
6. Đọc actual plan và estimated-versus-actual rows của query liên quan.
7. Phân loại CPU, data I/O, log I/O, memory, lock, network hoặc worker bottleneck.
8. Áp dụng một biện pháp giảm tác động có kiểm soát.
9. Đo lại cùng workload và kiểm tra correctness.
10. Ghi nguyên nhân, timeline, bằng chứng, thay đổi và follow-up.

Nếu chưa có đủ bằng chứng, ghi rõ điều chưa biết và phép đo tiếp theo. Không cần đưa ra nguyên nhân chắc chắn khi dữ liệu chỉ hỗ trợ một giả thuyết.

## 23. Mẫu ghi nhận sự cố

~~~text
Incident:
  started_at:
  detected_at:
  recovered_at:

Impact:
  affected_services:
  affected_endpoints:
  affected_tenants_or_workloads:
  request_error_rate:
  p95_before / p95_during / p95_after:
  throughput_before / during / after:

Timeline:
  deploys:
  jobs:
  infrastructure_events:
  mitigations:

Evidence:
  pool_active_pending_wait:
  active_sessions_and_transaction_age:
  top_query_fingerprints:
  execution_plan_changes:
  cpu_io_memory_lock_network:
  replication_and_log:

Root_cause:
  confirmed_or_hypothesis:
  supporting_evidence:
  remaining_unknowns:

Resolution:
  mitigation:
  permanent_fix:
  correctness_checks:
  before_after_measurements:
  rollback_plan:

Follow_up:
  owner:
  action:
  due_date:
~~~

Mẫu này giúp nhóm khác có thể kiểm tra lại kết luận và biết phần nào đã xác nhận, phần nào vẫn là giả thuyết.

## 24. Checklist hoàn tất chẩn đoán

- [ ] Triệu chứng được diễn đạt bằng latency, throughput và error rate.
- [ ] Phạm vi ảnh hưởng theo service, endpoint, tenant và node đã rõ.
- [ ] Có timeline với deploy, job và sự kiện hạ tầng liên quan.
- [ ] Có baseline cùng cửa sổ thời gian để so sánh.
- [ ] Đã phân biệt pool wait, network, database execution và application processing.
- [ ] Đã nối request/trace với session, transaction và query fingerprint khi có thể.
- [ ] Đã xếp hạng query theo delta total time, CPU, reads và calls.
- [ ] Đã đọc execution plan cùng estimated/actual rows.
- [ ] Đã xác định bottleneck chính: CPU, data/log I/O, memory, lock, network, pool hoặc worker.
- [ ] Đã dựng blocking chain nếu có lock wait.
- [ ] Đã kiểm tra skew, parameter sensitivity và statistics khi estimate sai.
- [ ] Đã chọn biện pháp giảm tác động có kiểm soát và có đường quay lại.
- [ ] Đã đo lại throughput, p95/p99, errors và tài nguyên sau thay đổi.
- [ ] Đã kiểm tra correctness, transaction semantics và tính toàn vẹn dữ liệu.
- [ ] Đã theo dõi đủ một chu kỳ workload đại diện.
- [ ] Đã lưu timeline, bằng chứng, nguyên nhân, thay đổi và hành động phòng ngừa.

Quy trình khoanh vùng tốt đi từ triệu chứng có thể đo được tới request, connection, transaction, query, execution plan và tài nguyên đang giới hạn tiến độ. Hãy tách thời gian chờ ở ứng dụng khỏi thời gian database thực thi, dùng số liệu theo đúng cửa sổ thay vì counter tích lũy, và đọc wait event cùng blocker hoặc operator liên quan. CPU, I/O, memory, lock, network và pool có thể tạo triệu chứng giống nhau nhưng cần cách xử lý khác nhau. Chỉ kết luận khi có bằng chứng, thay đổi từng yếu tố có kiểm soát, rồi xác minh cả throughput, tail latency, lỗi và correctness trên workload đại diện.
