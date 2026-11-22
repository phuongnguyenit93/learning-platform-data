# Thiết lập mức hiệu năng cơ sở và kiểm thử trước/sau thay đổi

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Hiệu năng hệ thống  
> **Mục tiêu:** Xây dựng performance baseline có thể lặp lại; xác định workload và các chỉ số ở cấp hệ thống, dịch vụ, session, SQL và ứng dụng; thiết kế phép thử trước/sau thay đổi có kiểm soát; phân biệt latency, throughput, CPU, logical/physical I/O, waits và lỗi; thu thập bằng chứng bằng các công cụ Oracle phù hợp; đánh giá kết quả bằng phân bố và mức biến động; triển khai, theo dõi và rollback khi có regression.

## 1. Performance baseline là gì?

Performance baseline là tập hợp số liệu mô tả cách hệ thống hoạt động trong một khoảng thời gian và dưới một workload đã xác định. Baseline dùng làm mốc để đánh giá thay đổi sau này: nâng cấp database, thay SQL, tạo index, đổi statistics, thay cấu hình, tăng dữ liệu, thay application release hoặc thay hạ tầng.

Một baseline hữu ích phải trả lời được:

- Hệ thống xử lý bao nhiêu giao dịch hoặc request trong một đơn vị thời gian?
- Người dùng chờ bao lâu ở mức trung bình và ở các percentile cao?
- Database tiêu thụ bao nhiêu CPU, logical reads, physical reads và redo?
- Các session chờ chủ yếu ở đâu: I/O, lock, concurrency, network hay CPU?
- SQL nào chiếm phần lớn DB time, CPU hoặc buffer gets?
- Workload có biến động theo giờ, ngày, batch window hoặc tenant không?
- Sau thay đổi, hiệu năng tốt hơn ở chỉ số nào và có đánh đổi ở chỉ số nào?

Baseline không phải một con số duy nhất như “query chạy 2 giây”. Nó là một bộ đo có ngữ cảnh: phiên bản, cấu hình, dữ liệu, workload, concurrency, thời điểm, môi trường và cách thu thập.

### 1.1. Baseline không phải cam kết hiệu năng tuyệt đối

Một lần chạy nhanh không chứng minh hệ thống luôn nhanh. Kết quả có thể bị ảnh hưởng bởi:

- Buffer cache đang nóng hay lạnh.
- Storage latency tại thời điểm đo.
- Số session đồng thời.
- Background jobs và batch khác.
- Bind values và độ chọn lọc khác nhau.
- Statistics hoặc execution plan thay đổi.
- Network và tốc độ fetch của client.
- CPU scheduling, virtualization hoặc noisy neighbor.
- Dữ liệu và index khác với production.

Baseline phải mô tả điều kiện đo và phạm vi đại diện. Nếu workload production có giờ cao điểm và thấp điểm, cần có baseline riêng hoặc phân nhóm theo từng giai đoạn.

## 2. Xác định phạm vi đo trước khi chạy thử

Trước khi thu thập số liệu, xác định rõ đối tượng cần đánh giá.

| Phạm vi | Câu hỏi cần trả lời | Ví dụ chỉ số |
|---|---|---|
| Hệ thống/database | Toàn database đang tiêu thụ tài nguyên ra sao? | DB time, DB CPU, waits, I/O, redo |
| Service/application | Người dùng hoặc service trải nghiệm thế nào? | Request rate, latency, error rate |
| Workload/job | Một batch hoặc luồng nghiệp vụ mất bao lâu? | Rows/sec, job duration, retry count |
| SQL/cursor | Câu SQL nào tiêu tốn tài nguyên? | Executions, elapsed, CPU, buffer gets |
| Session | Một nhóm session đang làm gì? | Wait event, module/action, blocking |
| Operation | Một thay đổi cụ thể có cải thiện bước nào? | E-Rows, A-Rows, Starts, Buffers, A-Time |

Không dùng một chỉ số ở một phạm vi để đại diện cho phạm vi khác. Ví dụ SQL elapsed time thấp không đảm bảo API response nhanh nếu ứng dụng còn xử lý dữ liệu lâu hoặc fetch chậm. Ngược lại, API latency cao có thể do network hoặc application queue dù database không bận.

### 2.1. Chốt câu hỏi kiểm thử

Ví dụ câu hỏi tốt:

- Thay index mới có giảm buffer gets trên truy vấn tra cứu đơn hàng không?
- Thay cách phân trang OFFSET bằng keyset có giữ p95 latency ổn định ở trang sâu không?
- Thay đổi batch size có tăng rows/sec nhưng làm PGA tăng bao nhiêu?
- Nâng cấp database có làm tăng hard parse hoặc physical reads không?
- Thay đổi statistics có cải thiện workload tổng thể mà không làm SQL quan trọng khác chậm đi không?

Câu hỏi cần có metric chính, điều kiện thành công, giới hạn regression và phạm vi SQL/job bị ảnh hưởng.

### 2.2. Đặt giả thuyết trước khi thay đổi

Ví dụ:

> Giả thuyết: composite index trên CUSTOMER_ID, STATUS, CREATED_AT sẽ giảm logical reads của truy vấn lấy đơn mới nhất theo khách hàng.

Chuyển giả thuyết thành tiêu chí đo:

- SQL_ID hoặc SQL signature mục tiêu.
- Bind values đại diện.
- Buffer gets mỗi execution.
- Elapsed time p50/p95.
- Rows returned.
- DML overhead do index mới.
- Index size và redo tăng thêm.
- Ảnh hưởng đến các query khác trên bảng ORDERS.

Nếu chỉ đo query đọc mà bỏ qua chi phí INSERT/UPDATE/DELETE, kết luận có thể không phản ánh workload thật.

## 3. Chọn workload đại diện

Workload là tập hoạt động thực tế database phải xử lý. Một bài benchmark nhỏ chỉ gồm một SELECT đơn giản thường không đại diện cho hệ thống production.

Phân nhóm workload:

- OLTP: giao dịch ngắn, nhiều session, đọc/ghi đồng thời.
- Reporting: truy vấn đọc nhiều hàng, join và aggregate.
- Batch: xử lý số lượng lớn theo đợt, có thể tạo redo và I/O lớn.
- Mixed workload: OLTP và batch/reporting chạy đồng thời.
- Maintenance: gather statistics, index maintenance, backup, purge.

Một thay đổi có thể cải thiện một nhóm nhưng làm nhóm khác suy giảm. Ví dụ index mới giảm latency SELECT nhưng tăng thời gian ghi và redo.

### 3.1. Chọn giao dịch đại diện theo tỷ trọng

Có thể lập bảng workload:

| Nhóm | Tỷ trọng request | Tần suất | Mức quan trọng |
|---|---:|---:|---|
| Đăng nhập và tra cứu | 35% | Cao | Cao |
| Tạo đơn hàng | 25% | Cao | Rất cao |
| Cập nhật trạng thái | 20% | Cao | Cao |
| Báo cáo ngày | 10% | Theo giờ | Trung bình |
| Batch đối soát | 10% | Theo lịch | Cao |

Tỷ trọng cần dựa trên log/telemetry thật, không đoán theo cảm nhận. Ngoài tỷ trọng, xem thêm transaction nào quan trọng về nghiệp vụ hoặc có SLA riêng.

### 3.2. Phân bố bind values

Một SQL có thể chạy nhanh với bind hiếm nhưng chậm với bind phổ biến. Khi tạo bộ test, chọn các nhóm bind:

- Giá trị thường gặp.
- Giá trị hiếm.
- Giá trị biên.
- Tenant lớn và tenant nhỏ.
- Khoảng thời gian ngắn và dài.
- Trạng thái có data skew.

Ghi lại bind datatype và phân bố dữ liệu. Không so sánh hai lần chạy với bind values có selectivity rất khác nhau rồi quy toàn bộ chênh lệch cho thay đổi code.

### 3.3. Quy mô dữ liệu

Dữ liệu test cần gần với production về:

- Tổng số hàng và số block.
- Tỷ lệ NULL.
- Data skew và số distinct values.
- Kích thước LOB/JSON/XML.
- Độ sâu quan hệ và tỷ lệ join.
- Số partition và phân bố hàng theo partition.
- Index, constraint, trigger và statistics.

Một bảng lab có 10.000 hàng không thể xác nhận hiệu năng của truy vấn trên bảng production có 500 triệu hàng, đặc biệt khi access path và partition pruning khác nhau.

## 4. Chuẩn hóa điều kiện trước và sau

Để so sánh có ý nghĩa, giữ các điều kiện càng giống nhau càng tốt.

| Yếu tố | Điều cần giữ cố định hoặc ghi nhận |
|---|---|
| Oracle release | Version, RU/patch level |
| Cấu hình | SGA/PGA, parallel settings, optimizer parameters |
| Hạ tầng | CPU, memory, storage, network, VM/container limits |
| Schema | DDL, index, constraints, partitioning |
| Data | Cùng snapshot hoặc bản sao tương đương |
| Statistics | Ghi lại thời điểm và trạng thái statistics |
| SQL | Cùng text/logic, trừ thay đổi đang thử |
| Bind | Cùng datatype và phân bố giá trị |
| Concurrency | Cùng số session và mix request |
| Cache | Cùng quy trình warm-up hoặc cold-cache policy |
| Client | Cùng driver, fetch size và cách tiêu thụ kết quả |
| Background work | Ghi nhận batch, backup, stats job và maintenance |
| Measurement | Cùng cửa sổ đo, công cụ và đơn vị |

Không phải lúc nào cũng có thể cố định tất cả. Nếu không thể, ghi nhận sai khác và đánh giá mức ảnh hưởng thay vì giả vờ hai lần chạy hoàn toàn tương đương.

### 4.1. Cùng dữ liệu hoặc cùng snapshot

Lý tưởng là dùng clone/refresh từ cùng một snapshot để chạy trước và sau. Nếu test trực tiếp trên môi trường thay đổi liên tục, chênh lệch row count hoặc data skew có thể làm sai kết luận.

Đối với phép thử chỉ đọc, Flashback Query AS OF SCN có thể giúp cố định snapshot nếu UNDO còn khả dụng và quyền cho phép. Đối với test ghi, dùng bản sao dữ liệu riêng hoặc reset fixture giữa các lần chạy.

Không chạy destructive benchmark trên production chỉ để tạo lại dữ liệu.

### 4.2. Cache nóng và lạnh

Cache state có thể làm kết quả khác biệt đáng kể:

- Cold cache thường làm physical reads và storage latency tăng.
- Warm cache có thể giảm physical reads nhưng vẫn có logical buffer gets.
- Chạy query đầu tiên sau khi deploy không tương đương query chạy lặp nhiều lần.

Chọn một chính sách rõ:

- So sánh warm-cache với warm-cache.
- So sánh cold-cache với cold-cache chỉ trong môi trường kiểm thử được kiểm soát.
- Hoặc đo riêng cả hai tình huống.

Không flush shared pool hoặc buffer cache trên production chỉ để làm benchmark. Những thao tác này ảnh hưởng các session khác và có thể tạo tải bất thường.

### 4.3. Concurrency và load shape

Đo một session đơn lẻ giúp hiểu latency của một request, nhưng không cho biết throughput khi tải đồng thời.

Test theo các mức concurrency đại diện, ví dụ 1, 5, 20, 50 session tùy năng lực môi trường. Ghi lại:

- Request rate.
- Số session active.
- Queue/wait ở connection pool.
- Throughput.
- p50, p95, p99 latency.
- Error/timeout rate.
- CPU và wait profile.

Tăng concurrency từ từ để tìm điểm bão hòa. Không chỉ đo tại một mức tải nhẹ.

## 5. Các chỉ số hiệu năng cốt lõi

### 5.1. Latency

Latency là thời gian một request/giao dịch hoàn tất.

Nên đo phân bố:

- p50: một nửa request hoàn tất nhanh hơn hoặc bằng giá trị này.
- p90/p95: thể hiện nhóm request chậm hơn phần lớn.
- p99: giúp phát hiện tail latency.
- Maximum: hữu ích để điều tra outlier nhưng rất nhạy với một sự kiện bất thường.

Average có thể che giấu tail latency. Ví dụ 99 request mất 50 ms và một request mất 5 giây tạo average không quá lớn nhưng một người dùng đã chờ rất lâu.

### 5.2. Throughput

Throughput là số đơn vị công việc hoàn thành trong một đơn vị thời gian:

- Transactions/sec.
- Requests/sec.
- Rows/sec.
- Batch records/minute.
- Jobs/hour.

Phải định nghĩa đơn vị rõ ràng. Một transaction có thể gồm nhiều SQL statement; SQL executions/sec không đồng nghĩa business transactions/sec.

### 5.3. CPU time

CPU time phản ánh thời gian CPU database sử dụng để xử lý. CPU cao có thể đến từ:

- SQL xử lý quá nhiều hàng.
- Hàm PL/SQL hoặc biểu thức tốn CPU.
- Parse và optimize nhiều.
- Compression/encryption.
- Parallel execution.
- Concurrency làm tăng CPU scheduling.

CPU time thấp nhưng elapsed cao thường gợi ý có thời gian chờ; cần xem wait events.

### 5.4. DB time

DB time là tổng thời gian database foreground sessions dành cho CPU và non-idle waits theo định nghĩa Oracle. Nó thường được dùng để đánh giá tải database ở mức tổng thể.

DB time có thể lớn hơn thời gian đồng hồ thực tế trong cùng cửa sổ vì nhiều session hoạt động song song. Không lấy DB time chia trực tiếp cho elapsed window để suy ra latency người dùng.

### 5.5. Logical I/O và physical I/O

- Buffer gets/logical reads: số lượt truy cập block qua buffer cache.
- Physical reads: số block phải đọc từ storage vào database cache theo các thống kê liên quan.
- Direct path reads: một số thao tác đọc trực tiếp theo cơ chế direct path.
- Writes: số block hoặc byte được ghi tùy metric.

Logical reads cao có thể gây CPU và contention ngay cả khi physical reads thấp. Physical reads cao có thể tăng latency tùy storage throughput và latency.

### 5.6. Redo, undo và commit

Với workload ghi, đo thêm:

- Redo size.
- Undo generation/usage.
- User commits.
- Log file sync wait.
- Row lock waits.
- Index maintenance overhead.

Index mới có thể giảm SELECT buffers nhưng tăng redo và thời gian commit do mỗi DML phải duy trì thêm index.

### 5.7. Errors và retries

Một thay đổi không được xem là tốt nếu latency giảm nhưng lỗi hoặc retry tăng.

Đo:

- ORA errors.
- Application exceptions.
- Deadlocks.
- Timeouts.
- Connection pool wait/timeout.
- Retry count.
- Failed transactions.
- Partial batch failures.

## 6. Baseline ở cấp hệ thống bằng dynamic performance views

Oracle cung cấp các V$ views để quan sát hoạt động hiện tại và một số thống kê tích lũy.

### 6.1. Database version

~~~sql
SELECT banner
FROM v$version;
~~~

Ghi lại version/RU chính xác, vì optimizer behavior, feature và bug fix có thể khác giữa release.

### 6.2. Database time và CPU từ system statistics

Có thể đọc một số system statistics:

~~~sql
SELECT name, value
FROM v$sys_time_model
WHERE name IN (
    'DB time',
    'DB CPU',
    'background elapsed time',
    'background cpu time'
)
ORDER BY name;
~~~

V$SYS_TIME_MODEL chứa giá trị tích lũy kể từ startup hoặc thời điểm reset tương ứng, không phải số liệu của một khoảng đo tự động. Lấy snapshot đầu và cuối rồi tính delta.

Các giá trị time model thường có đơn vị microseconds. Xác nhận đơn vị theo Reference của release đang chạy trước khi quy đổi.

### 6.3. System statistics

~~~sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size',
    'user commits',
    'execute count',
    'parse count (total)',
    'parse count (hard)'
)
ORDER BY name;
~~~

Đây là các counter tích lũy. Tính delta giữa hai mốc:

\[
\Delta metric = value_{after} - value_{before}
\]

Nếu instance restart hoặc counter reset giữa hai lần snapshot, delta có thể âm hoặc không còn so sánh được. Ghi startup time và thời điểm snapshot.

### 6.4. Load profile theo cửa sổ

Ví dụ thu hai snapshot cách nhau 5 phút rồi tính delta:

| Metric | Trước | Sau | Delta |
|---|---:|---:|---:|
| DB time | 10.000 s | 10.600 s | 600 s |
| DB CPU | 7.000 s | 7.350 s | 350 s |
| Logical reads | 8.000.000 | 8.600.000 | 600.000 |
| Physical reads | 500.000 | 520.000 | 20.000 |
| Redo size | 4 GB | 4,2 GB | 0,2 GB |

Số liệu trên chỉ là ví dụ minh họa. Cửa sổ 5 phút có thể chứa nhiều session và workload; không gán toàn bộ delta cho một query nếu nhiều hoạt động cùng diễn ra.

### 6.5. V$INSTANCE và startup time

~~~sql
SELECT instance_name,
       host_name,
       startup_time,
       status
FROM v$instance;
~~~

Ghi lại startup_time để phát hiện restart giữa hai snapshot. Với RAC, mỗi instance có counters riêng; dùng GV$ views và INST_ID khi cần tổng hợp toàn cluster.

## 7. Baseline theo session và service

### 7.1. Session statistics

V$SESSTAT kết hợp V$STATNAME để xem counter theo session:

~~~sql
SELECT s.sid,
       s.serial#,
       n.name,
       ss.value
FROM v$sesstat ss
JOIN v$statname n
  ON n.statistic# = ss.statistic#
JOIN v$session s
  ON s.sid = ss.sid
WHERE s.sid = SYS_CONTEXT('USERENV', 'SID')
  AND n.name IN (
      'session logical reads',
      'physical reads',
      'CPU used by this session',
      'redo size',
      'execute count',
      'parse count (total)'
  )
ORDER BY n.name;
~~~

Lấy snapshot trước/sau cho session test sẽ giúp tách workload của session đó khỏi hoạt động của database khác. Với connection pool, session có thể được tái sử dụng; cần gắn đúng request bằng MODULE/ACTION và thời điểm.

### 7.2. Gắn nhãn module/action

Ứng dụng hoặc PL/SQL có thể dùng DBMS_APPLICATION_INFO để gắn thông tin module/action:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'SEARCH_RECENT_ORDERS'
    );
END;
/
~~~

Khi hoàn tất:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => NULL,
        action_name => NULL
    );
END;
/
~~~

Có thể xem qua V$SESSION:

~~~sql
SELECT sid,
       serial#,
       username,
       service_name,
       module,
       action,
       client_identifier,
       sql_id,
       event,
       state
FROM v$session
WHERE module = 'ORDER_API';
~~~

Module/action giúp DBA nhóm session theo chức năng ứng dụng. Với pool, bảo đảm reset context khi trả connection để request sau không mang nhãn của request trước.

### 7.3. Client identifier

Có thể gắn tenant hoặc user context không nhạy cảm bằng DBMS_SESSION.SET_IDENTIFIER theo chính sách tổ chức. Không ghi password, token, thông tin cá nhân nhạy cảm hoặc payload bí mật vào module/action/client identifier.

## 8. Baseline theo SQL và cursor

V$SQL lưu thống kê của các child cursor trong shared pool.

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       rows_processed,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       direct_reads,
       direct_writes,
       last_active_time
FROM v$sql
WHERE parsing_schema_name = 'APP'
ORDER BY elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Một số trường thời gian trong V$SQL được lưu bằng microseconds. Các counter thường là tích lũy cho child cursor; không coi chúng là số liệu của lần chạy cuối.

### 8.1. Tính metric mỗi execution

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS total_elapsed_seconds,
       ROUND(elapsed_time / 1e6 / NULLIF(executions, 0), 4)
           AS avg_elapsed_seconds,
       ROUND(cpu_time / 1e6 / NULLIF(executions, 0), 4)
           AS avg_cpu_seconds,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS avg_buffer_gets,
       ROUND(disk_reads / NULLIF(executions, 0), 1)
           AS avg_disk_reads
FROM v$sql
WHERE parsing_schema_name = 'APP'
  AND executions > 0
ORDER BY elapsed_time DESC;
~~~

Trung bình có thể che giấu outlier và các bind values khác nhau. Dùng nó để sàng lọc SQL tốn tài nguyên, không thay cho p95/p99 per-execution.

### 8.2. SQL_ID và PLAN_HASH_VALUE

Ghi SQL_ID, child number và plan hash value trước/sau. Cùng SQL_ID có thể có nhiều child cursor và plan khác nhau. Plan hash khác không tự động là regression; phải đo runtime.

Ngược lại, plan hash không đổi cũng không bảo đảm performance không đổi: data volume, cache, concurrency, I/O và bind distribution có thể khác.

### 8.3. V$SQLSTATS

V$SQLSTATS có thể cung cấp số liệu tổng hợp theo SQL_ID với retention và hiệu năng truy vấn metadata khác V$SQL. Dùng view này khi cần sàng lọc SQL workload, nhưng vẫn cần hiểu các counter là thống kê tích lũy.

## 9. Runtime execution plan và row-source statistics

Để biết operation nào gây tốn kém, thu thập runtime plan statistics.

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       customer_id,
       total_amount
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 50 ROWS ONLY;
~~~

Sau khi fetch kết quả:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

So sánh:

- E-Rows: số hàng ước lượng.
- A-Rows: số hàng thực tế.
- Starts: số lần operation chạy.
- Buffers: logical buffer gets.
- Reads: physical reads.
- A-Time: thời gian row source được ghi nhận.

Nếu Starts lớn hơn 1, cần cân nhắc A-Rows/Starts trước khi so sánh với E-Rows. Không cộng Buffers hoặc A-Time mọi dòng plan một cách máy móc vì operation cha/con có thể phản ánh công việc liên quan.

### 9.1. Ghi nhận actual rows

A-Rows yêu cầu runtime statistics. EXPLAIN PLAN chỉ cung cấp estimate, không thực thi SQL. GATHER_PLAN_STATISTICS hoặc STATISTICS_LEVEL = ALL trong session kiểm thử có thể thu thập runtime data.

Với SELECT, fetch hết kết quả nếu mục tiêu là đo toàn bộ execution. Cùng một query nhưng client fetch 10 hàng và client fetch toàn bộ hàng là hai workload khác nhau.

## 10. Wait events: biết database đang chờ gì

Khi elapsed time tăng nhưng CPU không tăng tương ứng, cần xem wait events.

Một số nhóm thường gặp:

| Nhóm wait | Ví dụ | Hướng điều tra |
|---|---|---|
| User I/O | db file sequential read, db file scattered read | Index/table I/O, storage latency |
| Commit | log file sync | Commit frequency, redo log latency |
| Concurrency | buffer busy waits, enq waits | Hot block, contention, locking |
| Application | enq: TX - row lock contention | Transaction giữ row lock, update conflict |
| Network | SQL*Net message to/from client | Client fetch, network, app processing |
| Configuration | log buffer space, free buffer waits | Redo/buffer pressure và cấu hình |
| CPU | Không phải wait event cụ thể | CPU saturation, run queue, SQL CPU |

Tên wait và mức độ liên quan phụ thuộc workload/version. Không kết luận chỉ từ top wait event: một wait có tổng thời gian cao có thể là idle hoặc bình thường theo ứng dụng.

### 10.1. V$SESSION

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       blocking_session,
       module,
       action
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY seconds_in_wait DESC;
~~~

V$SESSION là ảnh chụp trạng thái hiện tại, không phải lịch sử đầy đủ. Một query chạy ngắn có thể kết thúc trước khi DBA quan sát.

### 10.2. V$SYSTEM_EVENT và V$SESSION_EVENT

Các view event statistics thường chứa counter tích lũy. Lấy snapshot trước/sau để tính delta. Phân biệt foreground/background, idle/non-idle và workload khác nhau trong cửa sổ đo.

Không cộng tất cả wait events rồi coi là user latency. Nhiều session chờ đồng thời nên tổng wait time có thể lớn hơn thời gian đồng hồ.

### 10.3. Blocking session và row lock

Nếu request bị chặn:

~~~sql
SELECT sid,
       serial#,
       blocking_session,
       event,
       wait_class,
       sql_id,
       module,
       action
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

Tìm session giữ lock, SQL đang chạy và transaction age. Không kill session chỉ dựa vào một snapshot nếu chưa xác định owner, transaction và tác động nghiệp vụ.

## 11. Đo workload ở tầng ứng dụng

Database metrics không thay thế application metrics.

Nên ghi:

- Request rate theo endpoint.
- p50/p95/p99 latency.
- Error rate và timeout.
- Connection pool wait time.
- Số connection active/idle.
- Thời gian chờ queue.
- Thời gian database call và thời gian xử lý ngoài database.
- Payload size và số hàng trả về.
- Retry count.

Ví dụ một API có latency 2 giây nhưng SQL chỉ chiếm 100 ms; phần còn lại có thể do network, serialization, gọi service khác hoặc chờ connection pool.

### 11.1. Correlation ID và tracing

Gắn request ID ở tầng ứng dụng và truyền context phù hợp vào database session. Dùng module/action/client identifier để liên kết database activity với endpoint hoặc job.

Không ghi thông tin bí mật vào SQL comment hoặc application context. Chọn mã định danh không nhạy cảm và giới hạn retention của telemetry.

### 11.2. Đo fetch behavior

Đối với query trả nhiều hàng, thời gian database execution có thể nhỏ nhưng client fetch toàn bộ result set mất lâu. Ghi rõ:

- Số hàng trả về.
- Fetch size của driver.
- Số round-trip.
- Kích thước payload.
- Thời gian đến first row.
- Thời gian đến last row.

Đây là những chỉ số quan trọng cho API báo cáo và màn hình phân trang.

## 12. Công cụ thu thập số liệu Oracle

### 12.1. DBMS_XPLAN

Dùng để xem estimated và actual execution plan khi runtime statistics có sẵn:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_HERE',
        0,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
~~~

PEEKED_BINDS có thể hiển thị bind values được peeked khi parse nếu có và nếu được hỗ trợ/quyền cho phép. Cẩn thận không đưa dữ liệu nhạy cảm từ bind vào báo cáo chia sẻ.

### 12.2. SQL Trace và TKPROF

SQL Trace thu thập parse, execute, fetch, CPU, elapsed, logical/physical I/O và wait information theo phạm vi tracing được bật. TKPROF định dạng trace file thành báo cáo dễ đọc.

Bật trace cho session hiện tại trong môi trường test:

~~~sql
ALTER SESSION SET sql_trace = TRUE;
~~~

Tắt:

~~~sql
ALTER SESSION SET sql_trace = FALSE;
~~~

Trong môi trường cần kiểm soát chính xác hơn, DBMS_MONITOR có API tracing theo session/client/service/module tùy trường hợp. Cần cân nhắc kích thước trace và overhead; không bật tracing diện rộng không giới hạn trên production.

### 12.3. AWR và ASH

Automatic Workload Repository (AWR) lưu snapshot workload và nhiều thống kê phục vụ so sánh theo thời gian. Active Session History (ASH) lấy mẫu hoạt động session để hỗ trợ phân tích wait, SQL và blocking.

AWR/ASH và một số chức năng liên quan có yêu cầu license Oracle Diagnostics Pack/Tuning Pack theo điều khoản sản phẩm. Trước khi dùng trong production, xác nhận license entitlement và chính sách tổ chức. Không giả định quyền truy cập view đồng nghĩa có quyền sử dụng tính năng theo license.

Nếu không có license phù hợp, dùng dynamic performance views, SQL Trace/TKPROF, công cụ telemetry ứng dụng và quy trình snapshot/delta được phép.

### 12.4. SQL Monitor

Real-Time SQL Monitoring giúp quan sát execution cụ thể, đặc biệt với SQL dài hoặc parallel. SQL Monitor có yêu cầu licensing tương ứng; xác nhận trước khi sử dụng.

### 12.5. OS metrics

Oracle performance phải được đối chiếu với hệ điều hành:

- CPU utilization và run queue.
- Memory pressure, paging/swap.
- Disk latency, IOPS và throughput.
- Network throughput/latency.
- VM/container CPU throttling.
- Storage queue depth.

Database có thể báo physical reads tăng vì storage chậm, nhưng nguyên nhân thực sự nằm ở hạ tầng. Cần đồng bộ timestamp giữa OS telemetry và database snapshots.

## 13. Thiết kế phép thử trước/sau

Một phép thử tốt có baseline, thay đổi đơn lẻ, kết quả đo và tiêu chí quyết định.

### 13.1. Chuẩn bị

Ghi lại:

- Mục tiêu và giả thuyết.
- SQL/job/API bị ảnh hưởng.
- SQL_ID/plan hash nếu có.
- Dữ liệu và bind values.
- Schema/index/statistics.
- Oracle version và cấu hình.
- Concurrency và workload mix.
- Metric chính và metric bảo vệ.
- Ngưỡng regression chấp nhận.
- Cách khôi phục trạng thái ban đầu.

### 13.2. Chạy baseline trước thay đổi

1. Chuẩn bị dữ liệu tương đương production.
2. Xác nhận statistics và execution plan.
3. Warm-up theo quy trình đã chọn.
4. Chạy workload ở concurrency mục tiêu.
5. Thu application metrics và database metrics.
6. Ghi p50/p95/p99, throughput, errors, CPU, I/O, waits và redo.
7. Lặp lại đủ số lần để thấy biến động.

### 13.3. Thay đổi một yếu tố

Ví dụ tạo index mới, đổi SQL hoặc thay batch size. Ghi rõ DDL/config/code version và timestamp. Tránh thay đồng thời index, statistics, optimizer parameter và application code nếu muốn xác định nguyên nhân cải thiện.

Nếu cần thay nhiều thứ để đạt mục tiêu, chia thành các bước có thể đo riêng hoặc ghi rõ không thể tách biệt tác động.

### 13.4. Chạy cùng workload sau thay đổi

Giữ:

- Cùng data snapshot/fixture.
- Cùng bind distribution.
- Cùng request mix.
- Cùng concurrency.
- Cùng thời gian warm-up.
- Cùng duration và cách fetch.
- Cùng measurement tooling.

Thu lại cùng bộ metric. Nếu môi trường hoặc workload khác, ghi nhận rõ và tránh so sánh trực tiếp mà không điều chỉnh.

### 13.5. Chạy xen kẽ khi có thể

Nếu môi trường test ổn định, có thể chạy baseline và candidate theo thứ tự xen kẽ (A/B/A/B) để giảm ảnh hưởng drift theo thời gian. Mỗi lần phải reset state phù hợp và giữ cùng data snapshot.

Nếu chạy A rồi B duy nhất, một thay đổi tải hệ thống hoặc cache có thể bị hiểu nhầm là hiệu quả của candidate.

## 14. Đánh giá kết quả bằng phân bố

Không kết luận từ một execution. Chạy nhiều lần và so sánh phân bố.

Ví dụ:

| Metric | Baseline | Candidate | Nhận xét |
|---|---:|---:|---|
| p50 latency | 80 ms | 65 ms | Cải thiện |
| p95 latency | 240 ms | 170 ms | Cải thiện rõ |
| p99 latency | 900 ms | 1.100 ms | Tail regression |
| Throughput | 1.000 req/s | 1.080 req/s | Tăng |
| DB CPU | 70% | 78% | Tốn CPU hơn |
| Buffer gets/req | 12.000 | 7.000 | Giảm |
| Redo/req | 8 KB | 12 KB | Tăng |
| Error rate | 0,1% | 0,1% | Không đổi |

Số liệu là ví dụ. Candidate có thể cải thiện p50/p95 nhưng làm p99 xấu đi; cần xác định SLA và tác động của tail latency.

### 14.1. Tỷ lệ cải thiện

Với metric càng thấp càng tốt, tỷ lệ giảm:

\[
\text{Improvement \%} =
\frac{\text{Baseline} - \text{Candidate}}
{\text{Baseline}} \times 100
\]

Ví dụ p95 giảm từ 200 ms xuống 160 ms:

\[
\frac{200 - 160}{200} \times 100 = 20\%
\]

Với throughput càng cao càng tốt:

\[
\text{Throughput Gain \%} =
\frac{\text{Candidate} - \text{Baseline}}
{\text{Baseline}} \times 100
\]

Không dùng công thức “cải thiện” cho metric có hướng tốt/xấu khác nhau mà không ghi rõ.

### 14.2. Dùng percentile thay vì chỉ average

p50 phản ánh trải nghiệm điển hình; p95/p99 phản ánh request chậm. Average hữu ích cho tổng thể nhưng có thể bị chi phối bởi outlier hoặc che giấu tail.

Cần dùng cùng cách tính percentile và cùng số mẫu. Với mẫu nhỏ, p99 không ổn định; tăng số request hoặc dùng cửa sổ đo dài hơn.

### 14.3. Biến động và mức tin cậy

Khi hai kết quả chỉ khác nhau vài phần trăm, biến động tự nhiên có thể lớn hơn mức cải thiện. Ghi:

- Số lần lặp.
- Số request mỗi lần.
- Median và percentile.
- Min/max hoặc độ lệch chuẩn khi phù hợp.
- Điều kiện tải và cache.
- Mức chênh giữa các lần chạy.

Không tuyên bố cải thiện 2% nếu các lần chạy dao động 10%. Khi cần kết luận thống kê, dùng phương pháp phân tích phù hợp với phân bố latency thay vì chỉ nhìn một trung bình.

### 14.4. Normalize theo đơn vị công việc

Nếu throughput khác nhau, tổng CPU hoặc total buffers có thể tăng chỉ vì candidate xử lý nhiều request hơn.

So sánh thêm:

- CPU per transaction.
- Buffer gets per request.
- Redo per row.
- Physical reads per report.
- Elapsed time per batch.
- Errors per 10.000 requests.

Metric normalized giúp tách hiệu quả trên mỗi đơn vị công việc khỏi thay đổi tổng khối lượng.

## 15. Đánh giá trade-off và regression

Một thay đổi hiếm khi cải thiện mọi metric cùng lúc.

Ví dụ:

- Index mới giảm SELECT latency nhưng tăng DML latency và redo.
- Parallelism tăng throughput nhưng tăng CPU và memory pressure.
- Batch lớn tăng rows/sec nhưng tăng PGA và thời gian transaction.
- Compression giảm storage/I/O nhưng tăng CPU.
- Cache tăng hit rate nhưng tăng memory footprint.
- SQL rewrite giảm buffer gets nhưng tăng parse complexity.

Đánh giá theo business objective và SLO, không tối ưu một metric riêng lẻ.

### 15.1. Định nghĩa guardrail

Ví dụ guardrail:

- p95 API latency không tăng quá 5%.
- p99 không vượt SLA.
- Error rate không tăng.
- CPU peak không vượt ngưỡng vận hành.
- DML throughput không giảm quá 3%.
- Redo volume không vượt năng lực log/storage.
- Batch hoàn tất trước deadline.
- Không phát sinh deadlock hoặc timeout mới.

Ngưỡng phải được nhóm sản phẩm/DBA thống nhất theo workload. Không có một ngưỡng phần trăm chung cho mọi hệ thống.

### 15.2. Regression ở SQL khác

Index mới có thể khiến optimizer chọn plan khác cho SQL khác. Sau thay đổi schema hoặc statistics, kiểm tra top SQL theo elapsed, CPU và buffer gets, không chỉ SQL mục tiêu.

Nếu có SQL Plan Management, SQL Profiles hoặc baselines, ghi nhận trạng thái và cách chúng ảnh hưởng plan. Không xóa baseline hoặc profile trong khi benchmark nếu không có mục tiêu rõ.

## 16. Lập kế hoạch rollout và rollback

Trước khi triển khai production, xác định cách quay lại.

| Loại thay đổi | Phương án rollback cần chuẩn bị |
|---|---|
| SQL/application release | Rollback artifact hoặc feature flag |
| Index mới | DROP/INVISIBLE index theo kế hoạch; xem tác động dependency |
| Statistics | Export stats, pending stats, stats history/restore |
| Parameter | Ghi giá trị cũ, scope và persistence |
| Partition operation | Kiểm tra khả năng phục hồi dữ liệu và index |
| Schema migration | Script rollback hoặc forward-fix đã thử |
| Batch/job config | Khôi phục config và checkpoint/retry state |

Rollback code không tự khôi phục dữ liệu đã ghi. Rollback statistics không rollback DML. DROP index không đảo ngược những thay đổi nghiệp vụ. Mỗi loại thay đổi cần kế hoạch tương ứng.

### 16.1. Canary hoặc staged rollout

Nếu ứng dụng hỗ trợ, triển khai candidate cho một phần traffic/tenant trước. Theo dõi latency, error, DB CPU, SQL plan và resource usage. Tăng dần tỷ lệ khi guardrail đạt.

Không dùng canary nếu hai nhóm dùng chung tài nguyên theo cách khiến kết quả không thể phân biệt hoặc dữ liệu/traffic không tương đương; trong trường hợp đó, cần thiết kế test riêng.

### 16.2. Stop conditions

Dừng rollout nếu:

- Error rate vượt ngưỡng.
- p95/p99 tăng vượt guardrail.
- DB CPU hoặc I/O tiến tới saturation.
- Lock wait/deadlock tăng mạnh.
- Connection pool timeout tăng.
- Batch không hoàn tất trong cửa sổ.
- Data correctness hoặc transaction behavior sai.

Khi dừng, giữ lại metrics, SQL_ID, plan hash, timestamp và deployment version để điều tra.

## 17. Runbook thực tế: baseline một SQL quan trọng

### Bước 1 — Xác định SQL

Ghi SQL_ID, child number, plan hash, bind datatypes và query purpose.

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       last_active_time,
       parsing_schema_name
FROM v$sql
WHERE sql_id = 'SQL_ID_HERE';
~~~

### Bước 2 — Lấy runtime plan

Chạy statement với GATHER_PLAN_STATISTICS trong session test, fetch đủ dữ liệu, rồi:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_HERE',
        0,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

### Bước 3 — Chụp session statistics

Lấy V$SESSTAT/V$STATNAME trước và sau lần chạy. Tính delta cho logical reads, physical reads, CPU used by this session, redo size và execute count.

### Bước 4 — Đo phía ứng dụng

Ghi start/end timestamp, row count, fetch duration, p50/p95/p99, request ID và error code. Đồng bộ clock giữa app và database host.

### Bước 5 — Chạy nhiều lần

Warm-up theo chính sách đã định, sau đó lặp nhiều lần với bind values đại diện. Không chỉ ghi lần chạy nhanh nhất.

### Bước 6 — Thử candidate

Thay đúng một yếu tố, chạy lại cùng protocol. Ghi plan hash và runtime stats mới.

### Bước 7 — So sánh

So sánh latency distribution, throughput, buffers/request, CPU/request, reads, redo, waits và errors. Ghi cả lợi ích lẫn regression.

### Bước 8 — Lưu bằng chứng

Lưu:

- SQL text đã loại dữ liệu nhạy cảm.
- SQL_ID, child number, plan hash.
- DB version/RU và test environment.
- DDL/index/statistics thay đổi.
- Bind profile.
- Workload concurrency và duration.
- Metrics trước/sau.
- Kết luận và rollback command đã kiểm thử.

## 18. Một số SQL mẫu để snapshot số liệu

### 18.1. System counters

~~~sql
SELECT SYSTIMESTAMP AS captured_at,
       name,
       value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size',
    'user commits',
    'execute count',
    'parse count (total)',
    'parse count (hard)'
)
ORDER BY name;
~~~

Lưu kết quả ở hai thời điểm trong cùng instance và tính delta bên ngoài hoặc trong bảng lab.

### 18.2. Time model

~~~sql
SELECT SYSTIMESTAMP AS captured_at,
       stat_name,
       value
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU')
ORDER BY stat_name;
~~~

Các giá trị time model tích lũy. Với RAC, dùng GV$SYS_TIME_MODEL và nhóm theo INST_ID.

### 18.3. Session đang active

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       module,
       action,
       client_identifier
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE';
~~~

Đây là snapshot tại thời điểm query; không thay thế lịch sử sampled activity.

### 18.4. Top SQL theo buffer gets

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       buffer_gets,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS buffers_per_exec,
       elapsed_time,
       cpu_time
FROM v$sql
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Top SQL theo tổng buffer gets tìm workload tiêu thụ tổng tài nguyên lớn. Nếu cần tìm query kém hiệu quả trên mỗi lần chạy, sắp xếp theo buffers per execution nhưng cần loại execution count quá thấp và xem số hàng trả về.

## 19. Các lỗi thường gặp khi benchmark

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chạy mỗi phương án một lần | Kết quả bị ảnh hưởng bởi cache/tải ngẫu nhiên | Warm-up và lặp nhiều lần |
| So sánh hai tập dữ liệu khác nhau | Chênh lệch không chỉ do thay đổi | Cùng snapshot hoặc fixture |
| Bind values khác nhau | Selectivity và plan có thể khác | Dùng cùng bind profile |
| Chỉ đo average | Che giấu tail latency | Ghi p50/p95/p99 |
| Chỉ đo SELECT | Bỏ qua chi phí ghi và redo | Đo workload mix |
| Chỉ đo một SQL | Không thấy regression ở SQL khác | Theo dõi top workload |
| Chỉ nhìn cost/plan hash | Không phản ánh runtime đầy đủ | Đo actual rows, buffers và elapsed |
| Dùng V$SQL cumulative như một lần chạy | Gán sai thời gian/IO cho execution | Dùng delta, trace hoặc SQL Monitor |
| Không fetch hết result | So sánh hai workload khác nhau | Cùng fetch behavior |
| Flush cache production để benchmark | Ảnh hưởng hệ thống khác | Test riêng, chính sách cache cố định |
| Tăng concurrency không kiểm soát | Gây nhiễu và saturation | Load profile có kiểm soát |
| Bỏ qua error/retry | Hiệu năng có vẻ tốt nhưng độ tin cậy giảm | Đo correctness và error rate |
| Bỏ qua license | Dùng tính năng không có entitlement | Xác nhận license trước AWR/ASH/Monitor |
| Không có rollback plan | Khó khôi phục khi regression | Chuẩn bị trước và thử trong lab |

## 20. Checklist trước/sau thay đổi

### Trước thay đổi

- [ ] Xác định câu hỏi và giả thuyết kiểm thử.
- [ ] Chọn workload đại diện và SQL/job/API mục tiêu.
- [ ] Ghi Oracle version, RU, cấu hình và hạ tầng.
- [ ] Ghi schema, index, partition và statistics.
- [ ] Dùng dữ liệu và bind values đại diện.
- [ ] Chốt concurrency, warm-up, thời lượng và fetch behavior.
- [ ] Ghi baseline latency p50/p95/p99 và throughput.
- [ ] Ghi CPU, DB time, buffers, physical reads, redo và waits.
- [ ] Ghi error rate, timeout, retries và correctness.
- [ ] Xác định metric chính, guardrail và điều kiện dừng.
- [ ] Chuẩn bị rollback và cách khôi phục dữ liệu/config.

### Sau thay đổi

- [ ] Chạy cùng workload và protocol.
- [ ] Lặp đủ số lần, không chọn riêng lần tốt nhất.
- [ ] So sánh percentile, throughput và metric normalized.
- [ ] So sánh SQL_ID/child/plan hash và runtime plan.
- [ ] Kiểm tra SQL khác có regression hay không.
- [ ] Đánh giá CPU, I/O, redo, waits và connection pool.
- [ ] Xác nhận correctness, lỗi và retry không tăng ngoài ngưỡng.
- [ ] Lưu bằng chứng, thay đổi và kết luận.
- [ ] Rollout dần nếu có thể.
- [ ] Theo dõi production sau triển khai và rollback nếu guardrail bị vi phạm.

## 21. Ghi nhớ cốt lõi

- Performance baseline là bộ số liệu có ngữ cảnh, không phải một con số latency đơn lẻ.
- Workload, dữ liệu, bind values, concurrency, cache và client fetch behavior phải được kiểm soát hoặc ghi nhận.
- Đo cả latency distribution và throughput; p95/p99 thường quan trọng hơn average cho trải nghiệm người dùng.
- DB time là tổng thời gian database foreground sessions, có thể lớn hơn elapsed window do nhiều session đồng thời.
- Buffer gets là logical I/O; physical reads và storage latency là một phần khác của bức tranh.
- Đo CPU, redo, undo, commits, waits, errors và retries cùng với SQL latency.
- V$SYSSTAT, V$SYS_TIME_MODEL, V$SESSTAT và V$SQL chứa counter tích lũy; lấy snapshot trước/sau và tính delta.
- V$SQL metrics không mặc nhiên là số liệu của lần execution cuối; child cursor có thể phục vụ nhiều session.
- DBMS_XPLAN với GATHER_PLAN_STATISTICS giúp so sánh E-Rows, A-Rows, Starts, Buffers và A-Time.
- SQL Trace/TKPROF hỗ trợ phân tích parse/execute/fetch và wait trong phạm vi tracing.
- AWR, ASH, SQL Monitor và một số tính năng tuning có yêu cầu license; xác nhận entitlement trước khi dùng.
- DBMS_APPLICATION_INFO giúp gắn module/action để liên kết database work với chức năng ứng dụng.
- Một thay đổi nên được kiểm thử với cùng workload, data snapshot, bind profile, concurrency và cách đo.
- Chạy nhiều lần và đánh giá phân bố; không kết luận từ một lần chạy hoặc chênh lệch nhỏ hơn mức biến động.
- Chuẩn hóa metric theo request/transaction/row để tách hiệu quả khỏi thay đổi throughput.
- Đánh giá trade-off giữa read, write, CPU, memory, I/O, redo và tail latency.
- Chuẩn bị guardrail, staged rollout, stop conditions và rollback trước khi triển khai.
- Rollback statistics, code, schema và dữ liệu là các việc khác nhau; cần kế hoạch riêng cho từng loại thay đổi.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — Performance methodology, wait events, statistics and tuning workflow.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$SYSSTAT, V$SYS_TIME_MODEL, V$SESSTAT, V$SQL, V$SESSION and dynamic performance views.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html) — MODULE, ACTION and application instrumentation.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html) — DISPLAY_CURSOR and runtime plan statistics.
- [Oracle Database Performance Tuning Guide — SQL Trace and TKPROF](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — SQL trace collection and report interpretation.
- [Oracle Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — Diagnostics Pack and Tuning Pack feature licensing.

V$ view columns, instrumentation APIs, SQL Monitor behavior and performance features can vary by Oracle release and license. Confirm the deployed version, privileges and entitlement; test with a representative workload and preserve a rollback path before changing production.

