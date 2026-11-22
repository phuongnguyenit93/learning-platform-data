# Đo độ trễ, thông lượng, CPU/I/O và tính đúng sau mỗi thay đổi trong Oracle

Tối ưu SQL không kết thúc ở việc câu lệnh chạy nhanh hơn một lần trên máy phát triển. Một thay đổi chỉ có giá trị khi nó cải thiện workload thực tế trong điều kiện có thể so sánh, không làm tăng chi phí tài nguyên ngoài dự kiến và vẫn trả về kết quả đúng. Vì vậy, mỗi lần thay đổi SQL, index, schema, statistics hoặc cấu hình phải được đánh giá bằng một quy trình đo lường có thể lặp lại.

Trong Oracle Database, cần nhìn đồng thời bốn nhóm kết quả:

- **Độ trễ (latency):** một request hoặc một lần thực thi mất bao lâu; theo dõi cả median và các percentile cao như p95/p99.
- **Thông lượng (throughput):** hệ thống hoàn thành được bao nhiêu request, transaction hoặc hàng mỗi giây trong một khoảng thời gian.
- **Tài nguyên (CPU/I/O):** lượng CPU, logical reads, physical reads, bytes đọc/ghi, redo, thời gian chờ và mức tranh chấp.
- **Tính đúng (correctness):** kết quả, số hàng, quy tắc nghiệp vụ, transaction behavior và khả năng xử lý đồng thời vẫn đúng sau thay đổi.

Một câu SQL có elapsed time thấp hơn trong một lần chạy đơn lẻ chưa chắc tốt hơn. Nó có thể dùng nhiều CPU hơn, tạo nhiều I/O hơn, giảm throughput khi concurrency tăng hoặc trả kết quả sai ở một trường hợp biên. Đo đúng cần workload đại diện, baseline, nhiều lần chạy, cùng điều kiện dữ liệu và môi trường, đồng thời kiểm tra kết quả độc lập với phép đo hiệu năng.

Bài học thuộc chủ đề **Tối ưu SQL** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Thiết kế baseline và thí nghiệm A/B có thể lặp lại.
- Đo latency, throughput và percentile.
- Đo CPU, logical/physical I/O, redo và wait events.
- Instrument SQL bằng SQL ID, module/action và bind values.
- Dùng V$SQL, DBMS_XPLAN, SQL Trace/TKPROF và các công cụ giám sát.
- Kiểm soát cache warm/cold, concurrency, bind peeking và workload.
- Xác minh kết quả bằng row counts, MINUS, checksum và quy tắc nghiệp vụ.
- Đánh giá transaction, lỗi, regression và trade-off sau mỗi thay đổi.
- Bài thực hành đo một truy vấn trước/sau khi tạo index và kiểm tra tính đúng.

## 1. Vì sao phải đo cả hiệu năng lẫn tính đúng?

Tối ưu SQL là thay đổi cách database truy xuất hoặc xử lý dữ liệu. Các thay đổi thường gặp gồm:

- Viết lại predicate hoặc join.
- Thêm, xóa hoặc thay đổi index.
- Thay đổi partitioning hoặc cách truy vấn partition.
- Cập nhật optimizer statistics/histogram.
- Dùng bind variables, hints hoặc SQL Plan Management.
- Thay đổi cách phân trang, aggregation hoặc xử lý hàng loạt.
- Thay đổi transaction scope, isolation hoặc locking.

Mỗi thay đổi có thể tác động nhiều khía cạnh. Ví dụ thêm index giúp một truy vấn SELECT nhanh hơn nhưng làm INSERT/UPDATE/DELETE tốn thêm công bảo trì index. Một truy vấn trả ít hàng nhanh hơn có thể khiến workload tổng thể chậm vì tăng random I/O. Một phép rewrite dùng DISTINCT hoặc đổi outer join thành inner join có thể chạy nhanh nhưng loại bỏ hàng hợp lệ.

Vì vậy, kết luận “tối ưu thành công” cần trả lời:

1. Kết quả có giống về mặt nghiệp vụ trước và sau không?
2. Latency có cải thiện trong workload đại diện không?
3. Throughput có tăng hoặc ít nhất không giảm ở concurrency mục tiêu không?
4. CPU, logical reads, physical I/O, redo và waits thay đổi ra sao?
5. Có phát sinh regression cho query khác, bind value khác hoặc thao tác ghi không?
6. Kết quả có ổn định qua nhiều lần chạy và sau khi cache/plan thay đổi không?

### Một ví dụ về kết luận sai

Giả sử phiên bản A chạy một lần mất 120 ms và phiên bản B mất 70 ms. Nếu B đọc gấp 4 lần block, dùng CPU gấp đôi và khi 50 session chạy đồng thời p99 tăng từ 300 ms lên 2 giây, B có thể làm hệ thống kém đi dù phép đo đơn lẻ tốt hơn.

Ngược lại, một thay đổi làm latency đơn lẻ từ 70 ms lên 80 ms nhưng giảm logical reads 80%, giảm CPU và cải thiện throughput ở tải cao có thể là lựa chọn tốt hơn.

## 2. Xây dựng baseline trước khi thay đổi

Baseline là bộ dữ liệu đo ban đầu dùng để so sánh với các phiên bản sau. Không có baseline, không thể biết thay đổi có cải thiện hay chỉ trùng với biến động của hệ thống.

### Ghi nhận ngữ cảnh thực thi

Trước khi chạy phép đo, lưu lại:

- Database version, edition, instance và service.
- Schema, object, partition và kích thước dữ liệu liên quan.
- Optimizer parameters quan trọng và optimizer statistics timestamp.
- SQL text, SQL ID, plan hash value, child cursor và bind values.
- Module/action/client identifier nếu có.
- Số session đồng thời, tỷ lệ đọc/ghi và phân bố request.
- Cache state, thời điểm chạy, maintenance/background jobs và tải nền.
- Thay đổi code, index, statistics hoặc cấu hình đang được đánh giá.

Nếu không ghi lại bind values và plan hash, hai lần đo có thể thực chất đang chạy những plan hoặc độ chọn lọc khác nhau.

### Chọn workload đại diện

Một workload đại diện cần bao gồm:

- Query phổ biến và query quan trọng về nghiệp vụ.
- Bind values phổ biến, hiếm và có độ chọn lọc khác nhau.
- Kích thước kết quả nhỏ và lớn.
- Thời điểm tải thấp và tải cao nếu có biến động theo giờ.
- Đường đọc và đường ghi nếu thay đổi có thể ảnh hưởng cả hai.
- Các transaction nhiều bước và trường hợp rollback/error.

Không chỉ chọn một câu SQL dễ tối ưu. Một thay đổi index có thể cải thiện query mục tiêu nhưng làm chậm nhiều DML khác trên cùng bảng.

### Giữ điều kiện trước/sau tương đương

Để so sánh công bằng:

- Dùng cùng tập dữ liệu hoặc snapshot dữ liệu tương đương.
- Dùng cùng bind values và kiểu dữ liệu bind.
- Dùng cùng số lần lặp và concurrency.
- Dùng cùng thời lượng warm-up.
- Không chạy A vào giờ tải thấp rồi B vào giờ tải cao.
- Ghi nhận cache warm/cold và không trộn hai loại phép đo.
- Giữ cấu hình database/hardware nhất quán hoặc ghi rõ khác biệt.

Nếu không thể giữ mọi điều kiện giống nhau, hãy đo đủ mẫu và ghi rõ biến số nào thay đổi.

### Ghi baseline vào bảng kết quả

Một bảng nhỏ có thể bắt đầu như sau:

| Phiên bản | Bind case | Concurrency | Runs | Median | p95 | p99 | Throughput | CPU | Buffer gets | Physical reads |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | phổ biến | 1 | 100 | ... | ... | ... | ... | ... | ... | ... |
| A | phổ biến | 20 | 500 | ... | ... | ... | ... | ... | ... | ... |
| A | chọn lọc thấp | 20 | 500 | ... | ... | ... | ... | ... | ... | ... |

Điền đơn vị rõ ràng, chẳng hạn ms, requests/s, CPU seconds, buffer gets/request và bytes/request. Không gộp số liệu từ nhiều lần chạy vào một con số không có phân bố.

## 3. Đo độ trễ (latency)

Latency là thời gian từ lúc một thao tác bắt đầu đến lúc nó hoàn tất theo ranh giới đo đã chọn. Ranh giới đó có thể là:

- Một lần thực thi SQL trong database.
- Một transaction gồm nhiều câu SQL.
- Một request ứng dụng từ lúc nhận đến lúc trả response.
- Một batch gồm nhiều hàng hoặc nhiều tác vụ.

Hai phép đo có ranh giới khác nhau không thể so sánh trực tiếp.

### Elapsed time

Elapsed time là thời gian trôi qua theo đồng hồ, bao gồm thời gian CPU thực thi và thời gian chờ tài nguyên. Một query có elapsed time cao có thể đang chờ I/O, lock, network, CPU scheduling hoặc tài nguyên khác.

Trong SQL*Plus/SQLcl có thể dùng:

~~~sql
SET TIMING ON;

SELECT COUNT(*)
FROM orders
WHERE customer_id = 1001;
~~~

TIMING là phép đo thuận tiện để quan sát thủ công. Nó bao gồm chi phí client/server round trip và hiển thị kết quả theo cách của tool; không thay thế phép đo có kiểm soát trong benchmark.

### Đo thời gian trong PL/SQL

Có thể dùng SYSTIMESTAMP để ghi mốc bắt đầu/kết thúc:

~~~sql
DECLARE
    l_start TIMESTAMP WITH TIME ZONE;
    l_end   TIMESTAMP WITH TIME ZONE;
    l_elapsed INTERVAL DAY TO SECOND;
    l_count NUMBER;
BEGIN
    l_start := SYSTIMESTAMP;

    SELECT COUNT(*)
    INTO l_count
    FROM orders
    WHERE customer_id = 1001;

    l_end := SYSTIMESTAMP;
    l_elapsed := l_end - l_start;

    DBMS_OUTPUT.PUT_LINE('Rows counted = ' || l_count);
    DBMS_OUTPUT.PUT_LINE('Elapsed = ' || l_elapsed);
END;
/
~~~

Đây là phép đo thô trong một session. Nó không tự tách CPU time, wait time hoặc network latency; DBMS_OUTPUT cũng có chi phí riêng. Dùng nó để minh họa, không làm benchmark production duy nhất.

### Median và percentile

Latency thường có phân bố lệch: đa số request nhanh nhưng một số request chậm do I/O, lock, parse, checkpoint hoặc tải nền. Average có thể che giấu tail latency.

- **p50/median:** 50% request hoàn tất trong hoặc dưới thời gian này.
- **p90:** 90% request hoàn tất trong hoặc dưới thời gian này.
- **p95:** 95% request hoàn tất trong hoặc dưới thời gian này.
- **p99:** 99% request hoàn tất trong hoặc dưới thời gian này.
- **max:** lần chậm nhất trong mẫu; nhạy với outlier.

Ví dụ:

| Phiên bản | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| A | 40 ms | 180 ms | 700 ms |
| B | 45 ms | 90 ms | 150 ms |

B có median cao hơn một chút nhưng tail latency tốt hơn nhiều. Nếu ứng dụng nhạy với timeout hoặc SLA p99, B có thể là lựa chọn phù hợp hơn.

### Tính percentile từ tập số liệu

Nếu lưu thời gian chạy trong bảng benchmark:

~~~sql
SELECT version_name,
       PERCENTILE_CONT(0.50)
           WITHIN GROUP (ORDER BY elapsed_ms) AS p50_ms,
       PERCENTILE_CONT(0.95)
           WITHIN GROUP (ORDER BY elapsed_ms) AS p95_ms,
       PERCENTILE_CONT(0.99)
           WITHIN GROUP (ORDER BY elapsed_ms) AS p99_ms,
       AVG(elapsed_ms) AS avg_ms,
       MAX(elapsed_ms) AS max_ms
FROM benchmark_runs
GROUP BY version_name
ORDER BY version_name;
~~~

Percentile chỉ có ý nghĩa khi mẫu đủ lớn và được thu thập cùng một loại request. Đừng tính p99 từ vài lần chạy rồi coi đó là SLA.

## 4. Đo thông lượng (throughput)

Throughput là số đơn vị công việc hoàn thành trong một đơn vị thời gian. Tùy ứng dụng, đơn vị có thể là:

- Requests/second.
- Transactions/second (TPS).
- SQL executions/second.
- Rows processed/second.
- Messages hoặc jobs completed/second.

Định nghĩa đơn vị trước khi đo. Một request có thể chạy một query hoặc hàng chục query; vì vậy requests/second và SQL executions/second không đồng nghĩa.

### Công thức cơ bản

\[
\text{Throughput} =
\frac{\text{Số đơn vị hoàn thành}}{\text{Thời gian đo}}
\]

Ví dụ 12.000 request hoàn thành trong 60 giây:

\[
\text{Throughput} = 12.000 / 60 = 200\ \text{requests/s}
\]

Đo throughput ở nhiều mức concurrency để thấy điểm bão hòa. Khi tăng session, throughput có thể tăng lúc đầu, sau đó đi ngang hoặc giảm vì CPU, I/O, lock, latch hoặc connection pool trở thành nút thắt.

### Throughput và latency có quan hệ nhưng không thay thế nhau

Theo định luật Little trong trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số request trung bình đang ở trong hệ thống (concurrency trung bình).
- \(\lambda\): throughput (request/second).
- \(W\): latency trung bình (second).

Ví dụ nếu throughput là 100 requests/s và latency trung bình là 0,2 giây, hệ thống có khoảng 20 request đang xử lý/chờ trung bình. Đây là quan hệ đo workload, không phải công thức dự báo hiệu năng nếu hệ thống chưa ổn định.

### Đo throughput trong bài test

Ghi nhận thời điểm bắt đầu/kết thúc và số request thành công:

~~~text
start_time = 10:00:00
end_time   = 10:01:00
completed_successfully = 12,000
failed = 3
duration_seconds = 60

throughput_success = 12,000 / 60 = 200 requests/s
error_rate = 3 / 12,003
~~~

Không tính request lỗi là request thành công. Ghi riêng throughput thành công, error rate, timeout và retry; một hệ thống có throughput cao nhờ trả lỗi nhanh không phải hệ thống tốt.

### Kiểm tra throughput ở concurrency khác nhau

| Concurrent sessions | Throughput | Median | p95 | Error rate |
| ---: | ---: | ---: | ---: | ---: |
| 1 | ... | ... | ... | ... |
| 5 | ... | ... | ... | ... |
| 20 | ... | ... | ... | ... |
| 50 | ... | ... | ... | ... |
| 100 | ... | ... | ... | ... |

Điểm cần tìm không chỉ là throughput tối đa mà còn là vùng hoạt động ổn định với latency và error rate chấp nhận được.

## 5. Đo CPU và DB time trong Oracle

Oracle cung cấp nhiều lớp số liệu. Cần hiểu đúng phạm vi và đơn vị để tránh so sánh nhầm.

### CPU time

CPU time là thời gian CPU thực sự dùng để thực thi công việc. Query có CPU time cao thường tiêu tốn xử lý trong database như join, sort, function, PL/SQL hoặc xử lý nhiều row.

### DB time

DB time là tổng thời gian foreground session dành cho database calls, bao gồm CPU time và thời gian chờ non-idle wait events. Khi nhiều session chạy đồng thời, DB time có thể lớn hơn elapsed wall-clock time của khoảng quan sát vì được cộng trên nhiều session.

### Elapsed time và DB time không phải một

- Elapsed time của một request là thời gian trôi qua từ đầu đến cuối theo ranh giới đo.
- DB time của một SQL/session phản ánh tổng thời gian xử lý database, có thể bao gồm nhiều loại wait.
- CPU time là phần thời gian CPU, không bao gồm thời gian chờ.

Nếu elapsed time tăng nhưng CPU time gần như không đổi, hãy xem waits, network và resource contention. Nếu CPU time và buffer gets cùng tăng, xem lại số hàng xử lý, join, predicate và plan.

### V$SQL: số liệu tích lũy theo cursor

View V$SQL chứa thống kê cho các child cursor đang có trong shared pool:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed,
       parse_calls,
       last_active_time
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

Các cột thời gian như ELAPSED_TIME và CPU_TIME trong V$SQL thường được tính bằng microseconds và là tổng tích lũy cho cursor, không phải latency của một execution. BUFFER_GETS và DISK_READS cũng là tổng tích lũy. Để so sánh mỗi execution, chia cho EXECUTIONS khi số liệu cùng thời điểm và executions > 0; để đo thay đổi trong một cửa sổ, lấy snapshot trước/sau và tính delta.

Ví dụ tính trung bình tích lũy:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS total_elapsed_seconds,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1e3, 3)
           AS avg_elapsed_ms,
       ROUND(cpu_time / NULLIF(executions, 0) / 1e3, 3)
           AS avg_cpu_ms,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS avg_buffer_gets,
       ROUND(disk_reads / NULLIF(executions, 0), 1)
           AS avg_disk_reads
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

Đây là average kể từ khi cursor được tạo/reset, không phải p95/p99. Một child cursor có thể chứa nhiều execution với bind values khác nhau; cần phân tích child number và bind behavior.

### V$SQLSTATS

V$SQLSTATS cung cấp thống kê tổng hợp theo SQL statement và thường có retention/hiệu năng truy vấn tốt hơn V$SQL cho một số tác vụ giám sát:

~~~sql
SELECT sql_id,
       plan_hash_value,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed
FROM v$sqlstats
WHERE sql_id = :sql_id;
~~~

Kiểm tra tài liệu đúng phiên bản để hiểu đơn vị và phạm vi từng metric. Không cộng số liệu của V$SQL và V$SQLSTATS với nhau vì chúng phản ánh cùng hoạt động ở các góc nhìn khác nhau.

### V$SESSTAT và V$STATNAME

Để đo statistic của một session, kết hợp V$SESSTAT với V$STATNAME:

~~~sql
SELECT n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE s.sid = :sid
  AND n.name IN (
      'CPU used by this session',
      'session logical reads',
      'physical reads',
      'physical read total bytes',
      'physical writes',
      'physical write total bytes',
      'redo size',
      'user commits',
      'user rollbacks'
  )
ORDER BY n.name;
~~~

Chụp hai snapshot trước/sau cùng session rồi lấy delta. Các statistic là số tích lũy của session; một snapshot đơn lẻ không nói riêng query nào đã tạo ra chúng nếu session chạy nhiều việc.

## 6. Đo logical I/O, physical I/O và redo

Không phải mọi lần đọc block đều đi ra storage. Oracle có thể phục vụ block từ buffer cache; vì vậy cần phân biệt logical reads với physical reads.

### Buffer gets / logical reads

Buffer gets là số lần session yêu cầu truy cập block trong buffer cache. Nó phản ánh lượng công việc đọc logic mà SQL thực hiện, bất kể block có phải đọc từ storage hay không.

Một query có buffer gets rất cao có thể:

- Quét nhiều block.
- Thực hiện nested loops với nhiều lần lookup.
- Đọc lại cùng block nhiều lần.
- Dùng predicate kém chọn lọc.
- Join hoặc aggregate trên tập dữ liệu lớn hơn cần thiết.

Buffer gets thường là chỉ số hữu ích để so sánh lượng công việc SQL, đặc biệt khi cache state khác nhau. Nhưng ít buffer gets hơn không tự động có nghĩa query nhanh hơn nếu có lock/wait khác.

### Physical reads

Physical reads là số block phải đọc từ storage vào database buffer cache. Cần phân biệt các counter cụ thể, chẳng hạn DISK_READS trong V$SQL với physical read requests/bytes ở session/system stats. Một physical read request có thể đọc nhiều block; đừng nhầm số request với số block hoặc bytes.

### Direct path reads

Một số thao tác có thể đọc trực tiếp từ datafile vào vùng bộ nhớ riêng thay vì qua buffer cache thông thường. Theo dõi wait events như direct path read và các statistic tương ứng khi query scan lớn hoặc parallel execution.

### Physical writes và redo

Thay đổi DML có thể tạo:

- Physical writes từ dirty buffers được ghi ra datafiles.
- Redo để phục hồi thay đổi.
- Undo để hỗ trợ rollback và read consistency.
- I/O trên TEMP khi sort/hash operation vượt PGA memory.

Khi thêm index, đọc SELECT có thể giảm nhưng INSERT/UPDATE/DELETE phải cập nhật thêm index entries và tạo thêm redo/undo. Benchmark chỉ SELECT sẽ bỏ qua chi phí này.

### Một số metric nên lưu

| Metric | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| Buffer gets | Block access logic | SQL có đọc ít block hơn không? |
| Physical reads | Block đọc từ storage | Có giảm I/O thực tế hay chỉ warm cache? |
| Physical read bytes | Dung lượng đọc | Có chuyển từ nhiều request nhỏ sang ít bytes lớn hơn không? |
| Physical writes/bytes | Ghi datafile | Index hoặc rewrite có tăng chi phí ghi không? |
| Redo size | Bytes redo sinh ra | DML có tạo thêm redo đáng kể không? |
| Sorts (memory/disk) | Sort dùng memory hay spill ra TEMP | Có giảm spill không? |
| Temp space | Dung lượng TEMP sử dụng | Hash/sort có làm tăng TEMP pressure không? |

## 7. Wait events và xác định nút thắt

Một session có thể mất thời gian chờ nhiều tài nguyên khác nhau. Wait events giúp phân loại nguyên nhân elapsed time cao.

### Một số nhóm wait phổ biến

| Wait/event group | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| db file sequential read | Thường là single-block read, hay gặp với index/table lookup | Số lần lookup, index selectivity, physical I/O latency. |
| db file scattered read | Thường là multiblock read, hay gặp full scan | Số block scan, filter selectivity, cache/storage throughput. |
| direct path read | Đọc trực tiếp, có thể từ scan lớn hoặc parallel query | I/O bandwidth, parallelism, volume dữ liệu. |
| direct path write temp | Ghi dữ liệu tạm khi sort/hash spill | PGA, sort/hash size, join cardinality. |
| direct path read temp | Đọc dữ liệu tạm từ TEMP | Spill volume và TEMP I/O. |
| enq: TX - row lock contention | Chờ transaction khác giữ row lock | Transaction duration, hot rows, update order. |
| buffer busy waits | Cạnh tranh buffer block | Hot blocks, segment/index contention. |
| latch: cache buffers chains | Cạnh tranh latch bảo vệ buffer cache chains | Hot blocks hoặc truy cập lặp tập trung. |
| log file sync | Foreground chờ commit redo được flush | Commit frequency, redo write latency. |
| log file parallel write | LGWR chờ ghi redo | Redo storage latency. |
| SQL*Net message from client | Session idle chờ client gửi thêm dữ liệu | Thường là idle; không coi là database bottleneck. |

Tên wait event và cách diễn giải chi tiết phụ thuộc release và context. Không kết luận chỉ từ tên event; xem wait time, count, session state, SQL và workload.

### V$SESSION_WAIT và V$SESSION

Để quan sát session đang chờ:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait
FROM v$session
WHERE username IS NOT NULL
  AND state = 'WAITING'
ORDER BY seconds_in_wait DESC;
~~~

Đây là snapshot hiện tại. Một query có thể đã chờ event trước đó nhưng hiện tại đang chạy CPU; cần lấy mẫu nhiều lần hoặc dùng công cụ lịch sử phù hợp.

### Session wait statistics

~~~sql
SELECT sid,
       event,
       total_waits,
       time_waited,
       average_wait
FROM v$session_event
WHERE sid = :sid
  AND wait_class <> 'Idle'
ORDER BY time_waited DESC;
~~~

Các số liệu là tích lũy theo session từ khi session bắt đầu. Lấy snapshot trước/sau và tính delta trong khoảng thực nghiệm. TIME_WAITED/AVERAGE_WAIT dùng đơn vị theo view/release; kiểm tra tài liệu dictionary.

### System wait events

~~~sql
SELECT event,
       total_waits,
       time_waited_micro,
       average_wait
FROM v$system_event
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

System-wide waits trộn hoạt động của mọi session; không dùng để quy kết một SQL cụ thể nếu không lọc theo thời gian/session hoặc kết hợp SQL monitoring.

### CPU-bound hay I/O-bound?

Gợi ý chẩn đoán:

- CPU time cao, waits thấp, buffer gets cao: xem plan, số hàng, join, predicate, PL/SQL function và parallelism.
- Elapsed cao, CPU thấp, physical read wait cao: xem storage latency, scan volume và cache.
- Elapsed cao, CPU thấp, TX lock wait cao: xem transaction giữ lock, hot rows và thứ tự cập nhật.
- Sort/hash spill vào TEMP: xem cardinality estimate, PGA/workarea và kích thước trung gian.
- Log file sync cao: xem commit frequency và redo storage; không tự động bỏ COMMIT vì điều đó có thể thay đổi semantics transaction.

Một query có thể vừa CPU-bound vừa I/O-bound theo từng giai đoạn. Hãy đọc execution plan và waits cùng nhau.

## 8. Xem execution plan và row-source statistics

Execution plan cho biết Oracle dự định hoặc đã thực hiện các operation nào: table access, index range scan, join, sort, filter, partition pruning, parallel operations và thứ tự thực hiện.

### EXPLAIN PLAN

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM orders
WHERE customer_id = 1001;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN tạo plan ước lượng cho câu SQL trong ngữ cảnh explain. Nó không nhất thiết là plan thực tế mà cursor đang chạy, vì bind values, session settings, adaptive plan, child cursor hoặc môi trường parse có thể khác.

### DISPLAY_CURSOR

Sau khi query thực thi, xem cursor thực tế:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id => :sql_id,
        cursor_child_no => :child_no,
        format => 'ALLSTATS LAST +PEEKED_BINDS +OUTLINE'
    )
);
~~~

Nếu truyền NULL cho SQL_ID/child number, DISPLAY_CURSOR thường lấy cursor gần nhất trong session; để điều tra chính xác, dùng SQL_ID và child number đã xác định.

### Thu thập actual row-source statistics

Có thể bật statistics cho query:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM orders
WHERE customer_id = 1001;
~~~

Sau đó xem:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

ALLSTATS LAST hiển thị số hàng thực tế (A-Rows), số lần chạy operation (Starts), logical I/O (Buffers) và các số liệu row-source khi đã được thu thập. So sánh E-Rows với A-Rows để tìm estimate sai lớn.

### Những cột quan trọng

- E-Rows: số hàng optimizer ước lượng.
- A-Rows: số hàng thực tế operation trả ra.
- Starts: số lần operation được khởi chạy.
- Buffers: buffer gets của operation.
- Reads: physical reads được ghi nhận cho operation nếu có.
- A-Time: thời gian thực thi operation tích lũy/hiển thị theo plan format.
- TEMP: thông tin sử dụng temporary space nếu có.

Không cộng A-Time của mọi operation để ra elapsed của query vì thời gian có thể lồng nhau giữa các operation. Đọc plan theo cây operation và dùng số liệu cấp cursor để đối chiếu.

### Plan hash value

PLAN_HASH_VALUE là fingerprint để nhận diện cấu trúc plan. Nó hữu ích khi so sánh trước/sau nhưng không chứa toàn bộ thông tin như bind values, outline, predicate, adaptive behavior hoặc runtime. Cùng plan hash không bảo đảm mọi điều kiện thực thi giống nhau; plan hash khác không tự chứng minh plan mới tệ hơn.

## 9. SQL Trace và TKPROF

SQL Trace ghi lại hoạt động SQL của session hoặc một phần workload, bao gồm parse/execute/fetch, CPU/elapsed time, số lần đọc logic/physical, waits và bind values tùy thiết lập. TKPROF định dạng trace file thành báo cáo dễ đọc hơn.

### Bật trace cho session hiện tại

~~~sql
ALTER SESSION SET tracefile_identifier = 'ROW438_TEST';
ALTER SESSION SET sql_trace = TRUE;

-- Chạy workload cần đo ở đây.
SELECT COUNT(*)
FROM orders
WHERE customer_id = 1001;

ALTER SESSION SET sql_trace = FALSE;
~~~

Trace file được ghi ở server-side diagnostic destination, không nằm trên máy client. DBA có thể dùng ADRCI hoặc truy vấn V$DIAG_INFO để xác định vị trí trace:

~~~sql
SELECT name, value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Default Trace File');
~~~

### DBMS_SESSION và DBMS_MONITOR

DBMS_MONITOR cung cấp API bật/tắt tracing theo session, client identifier, service/module/action hoặc các phạm vi khác tùy phiên bản:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        waits => TRUE,
        binds => TRUE
    );
END;
/

-- Thực hiện workload cần trace.

BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
~~~

Tracing bind values có thể ghi dữ liệu nhạy cảm vào trace. Chỉ bật binds khi cần và được phép; giới hạn thời gian, session và nơi lưu trace.

### Đọc TKPROF

DBA/engineer có thể chạy TKPROF trên trace file:

~~~text
tkprof input_trace.trc output_report.txt
~~~

TKPROF tổng hợp số lần parse/execute/fetch, CPU, elapsed, disk reads, query/current gets và rows processed theo SQL. Kiểm tra cách report phân tách recursive SQL, waits và bind data; không chỉ nhìn tổng elapsed.

### Khi nào dùng trace?

- Query phức tạp cần biết parse/execute/fetch thực tế.
- Cần xác định SQL nào trong transaction tạo nhiều I/O.
- Cần xem bind values hoặc số lần execute lặp.
- V$SQL/plan view chưa đủ để giải thích behavior.

Không bật trace rộng cho toàn database trong thời gian dài nếu chưa tính dung lượng và overhead. Trace có thể tạo nhiều file và chứa thông tin nhạy cảm.

## 10. SQL Monitor và báo cáo thời gian thực

SQL Monitor cung cấp theo dõi chi tiết cho các SQL execution đủ điều kiện, đặc biệt query dài hoặc parallel execution. Có thể dùng DBMS_SQL_MONITOR và DBMS_SQLTUNE_REPORT, hoặc xem các V$SQL_MONITOR/V$SQL_PLAN_MONITOR views tùy quyền và phiên bản.

Ví dụ truy vấn execution đang/đã được monitor:

~~~sql
SELECT sql_id,
       sql_exec_id,
       sql_exec_start,
       status,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       px_servers_requested,
       px_servers_allocated
FROM v$sql_monitor
WHERE sql_id = :sql_id
ORDER BY sql_exec_start DESC;
~~~

SQL Monitor có thể cho biết thời gian và số hàng theo từng operation, đặc biệt hữu ích cho parallel query. Điều kiện tự động monitor và cách xem report phụ thuộc phiên bản/cấu hình.

### SQL Monitor và licensing

Real-Time SQL Monitoring/SQL Monitoring report thuộc nhóm tính năng gắn với Oracle Tuning Pack trong nhiều phiên bản thương mại. Việc sử dụng có thể yêu cầu Diagnostic Pack/Tuning Pack và quyền tương ứng theo edition, release, contract và chính sách license của tổ chức. Trước khi bật hoặc xuất report trong production, DBA cần xác nhận quyền sử dụng; không giả định mọi Oracle installation đều được phép dùng.

### AWR và ASH

AWR (Automatic Workload Repository) lưu snapshot hiệu năng theo thời gian; ASH (Active Session History) lấy mẫu hoạt động session. Chúng giúp xem workload lịch sử, top SQL, waits và thay đổi theo thời gian. Các tính năng AWR/ASH thường thuộc Oracle Diagnostics Pack trong nhiều bản thương mại; cần xác nhận licensing trước khi sử dụng.

Nếu không có license phù hợp, có thể dùng các dynamic performance views được phép, SQL Trace/TKPROF, DBMS_XPLAN và instrumentation trong ứng dụng; kiểm tra hợp đồng/chính sách trước khi chọn công cụ.

### Không dùng report lịch sử thay cho thí nghiệm kiểm soát

AWR/ASH rất hữu ích để tìm workload và thời điểm có vấn đề, nhưng so sánh hai khoảng thời gian có thể bị ảnh hưởng bởi tải khác, dữ liệu khác, cache, job nền và concurrency. Dùng chúng để định hướng; sau đó thực hiện benchmark có kiểm soát để xác nhận.

## 11. Instrumentation: gắn SQL với workload

Để đo đúng, cần biết SQL thuộc request, module, action hoặc client nào. Oracle cung cấp DBMS_APPLICATION_INFO và DBMS_SESSION để gắn nhãn session.

### MODULE và ACTION

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'SEARCH_ORDERS'
    );
END;
/
~~~

Sau khi xử lý xong action:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
END;
/
~~~

Module/action có thể xuất hiện trong V$SESSION và nhiều công cụ giám sát. Dùng tên ổn định, có ý nghĩa và tránh nhét dữ liệu người dùng nhạy cảm vào nhãn.

### CLIENT_IDENTIFIER

~~~sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('request-2026-000123');
END;
/
~~~

CLIENT_IDENTIFIER giúp liên kết session với request/user logic của ứng dụng. Nếu connection pool tái sử dụng session, phải reset identifier khi trả connection về pool để tránh gán nhầm request sau.

### Ghi SQL ID và plan hash

~~~sql
SELECT sid,
       serial#,
       username,
       module,
       action,
       client_identifier,
       sql_id,
       sql_child_number,
       prev_sql_id
FROM v$session
WHERE sid = :sid;
~~~

Kết hợp module/action/client identifier với SQL_ID để xác định câu SQL của một request. Khi query hoàn tất, V$SESSION có thể chuyển sang SQL khác; muốn theo dõi execution lịch sử, dùng V$SQL, SQL Monitor hoặc trace trong phạm vi quyền.

### Instrumentation không nên làm thay đổi kết quả

Gắn module/action/identifier là metadata quan sát, nhưng code phải reset đúng lúc và không dùng giá trị này làm logic bảo mật nếu caller có thể tự đặt. Không ghi token, email đầy đủ hoặc dữ liệu nhạy cảm vào client identifier.

## 12. Xác minh tính đúng sau mỗi thay đổi

Hiệu năng chỉ có ý nghĩa nếu kết quả đúng. Khi rewrite SQL hoặc thay đổi schema/index, hãy so sánh kết quả trước/sau trên cùng snapshot dữ liệu và cùng đầu vào.

### Kiểm tra số hàng không đủ

Hai truy vấn có thể trả cùng số hàng nhưng khác nội dung. Ví dụ query A trả 100 hàng đúng, query B cũng trả 100 hàng nhưng thiếu một hàng và lặp một hàng khác. COUNT(*) không phát hiện được khác biệt đó.

### So sánh hai tập kết quả bằng MINUS

Giả sử query cũ và query mới được materialize vào hai bảng tạm hoặc staging table có cùng cấu trúc:

~~~sql
SELECT col1, col2, col3
FROM result_before
MINUS
SELECT col1, col2, col3
FROM result_after;
~~~

Truy vấn này tìm các hàng có trong BEFORE nhưng không có trong AFTER. Kiểm tra chiều ngược lại:

~~~sql
SELECT col1, col2, col3
FROM result_after
MINUS
SELECT col1, col2, col3
FROM result_before;
~~~

Nếu cả hai chiều đều không có hàng, hai tập giá trị phân biệt tương đương theo semantics của MINUS. Tuy nhiên, MINUS loại duplicate; nếu multiplicity/duplicate rows là một phần kết quả, phải so sánh số lần xuất hiện từng tổ hợp cột bằng GROUP BY và COUNT.

### So sánh duplicate-aware

~~~sql
SELECT col1, col2, col3, COUNT(*) AS occurrences
FROM result_before
GROUP BY col1, col2, col3
MINUS
SELECT col1, col2, col3, COUNT(*) AS occurrences
FROM result_after
GROUP BY col1, col2, col3;
~~~

Chạy chiều ngược lại để kiểm tra cả hàng thừa ở AFTER. Với datatype LOB, LONG hoặc kiểu không hỗ trợ GROUP BY/MINUS theo cách này, cần so sánh bằng phương pháp phù hợp như hash từng chunk hoặc ứng dụng đọc stream và so sánh nội dung.

### NULL và phép so sánh

SQL có three-valued logic. Predicate `a = b` không trả TRUE khi cả hai giá trị đều NULL; nó trả UNKNOWN. Khi so sánh kết quả, cần xác định NULL có ý nghĩa gì và dùng biểu thức null-safe thích hợp.

Ví dụ kiểm tra khác biệt null-safe:

~~~sql
SELECT *
FROM result_before b
JOIN result_after a
  ON a.key_id = b.key_id
WHERE (a.value <> b.value)
   OR (a.value IS NULL AND b.value IS NOT NULL)
   OR (a.value IS NOT NULL AND b.value IS NULL);
~~~

Ví dụ này giả định KEY_ID duy nhất và không NULL. Nếu key có thể NULL hoặc duplicate, cần khóa so sánh đầy đủ phù hợp.

### ORDER BY và thứ tự kết quả

Quan hệ trong SQL không có thứ tự bảo đảm nếu không có ORDER BY. Hai query có thể trả cùng tập hàng nhưng thứ tự hiển thị khác. Nếu thứ tự là yêu cầu nghiệp vụ hoặc API contract, phải có ORDER BY đầy đủ, bao gồm tie-breaker ổn định khi nhiều hàng có cùng sort key.

### Kiểm tra giá trị tổng hợp

Với query tính tổng/đếm/average, so sánh:

- Số nhóm và key nhóm.
- COUNT(*) và COUNT(column).
- SUM/AVG/MIN/MAX.
- Xử lý NULL.
- Độ chính xác số và rounding.
- Time zone/date boundary.

Không chỉ so sánh một grand total; sai lệch ở hai nhóm có thể triệt tiêu nhau.

## 13. Xác minh DML và transaction semantics

Khi thay đổi INSERT/UPDATE/DELETE/MERGE, cần kiểm tra cả số hàng và trạng thái cuối của dữ liệu.

### So sánh số hàng tác động

Trong PL/SQL, SQL%ROWCOUNT cho biết số hàng bị câu DML gần nhất tác động:

~~~sql
UPDATE orders
SET status = 'EXPIRED'
WHERE expires_at < SYSTIMESTAMP;

DBMS_OUTPUT.PUT_LINE('Rows updated = ' || SQL%ROWCOUNT);
~~~

Ghi nhận số hàng trước/sau và đối chiếu với kỳ vọng nghiệp vụ. SQL%ROWCOUNT phải được đọc ngay sau câu DML liên quan, trước khi chạy SQL khác làm thay đổi implicit cursor attributes.

### So sánh dữ liệu trước/sau

Với DML, tạo snapshot/staging hoặc chạy trong môi trường clone để so sánh:

- Khóa bị thêm/xóa/thay đổi.
- Các cột thay đổi và giá trị cũ/mới.
- Số hàng con và quan hệ FK.
- Audit records và side effects.
- Tổng tiền, số dư, số lượng hoặc các invariant.

### Transaction boundary

Một rewrite có thể thay đổi số câu SQL, thời điểm lock hoặc transaction scope. Xác minh:

- COMMIT có còn ở đúng ranh giới nghiệp vụ không?
- ROLLBACK có hoàn tác toàn bộ thay đổi cần hoàn tác không?
- Có savepoint hoặc autonomous transaction bị ảnh hưởng không?
- Row locks được giữ trong bao lâu?
- Có thay đổi isolation hoặc read consistency không?
- Lỗi giữa chừng có để lại dữ liệu một phần không?

Không chuyển nhiều transaction nhỏ thành một transaction lớn chỉ để giảm round trips nếu điều đó làm tăng lock duration, undo usage hoặc thay đổi tính nguyên tử nghiệp vụ.

### Idempotency và retry

Nếu ứng dụng retry khi timeout, câu lệnh phải được đánh giá với khả năng đã commit nhưng response bị mất. Đảm bảo request có idempotency key hoặc logic chống duplicate nếu nghiệp vụ yêu cầu. Một query nhanh hơn nhưng tạo duplicate khi retry là thay đổi sai.

### Constraint và trigger

Sau thay đổi DML, kiểm tra constraint violations, trigger execution, audit rows và side effects. Nếu thêm index/constraint, kiểm tra cả đường ghi hợp lệ và trường hợp bị từ chối.

## 14. Kiểm tra correctness dưới concurrency

Kết quả đúng trong một session chưa đủ cho hệ thống nhiều session. Nhiều lỗi chỉ xuất hiện khi hai transaction cùng đọc/ghi dữ liệu.

Các tình huống cần thử:

- Hai session cập nhật cùng một hàng.
- Hai session cùng tạo một khóa duy nhất.
- Một session đọc trong lúc session khác UPDATE/COMMIT.
- Hai transaction cập nhật nhiều hàng theo thứ tự khác nhau.
- Retry request sau timeout.
- Bulk load chạy cùng query/report.
- Query phân trang khi có INSERT/DELETE đồng thời.

### Unique race

Nếu ứng dụng kiểm tra key chưa tồn tại rồi INSERT, hai session có thể cùng vượt qua pre-check. UNIQUE constraint phải là lớp bảo vệ cuối cùng. Đo cả latency thành công và latency conflict; ghi nhận error rate và số lần retry.

### Lost update và locking

Nếu rewrite đổi cách đọc rồi cập nhật, kiểm tra lost update. Có thể cần SELECT FOR UPDATE, optimistic version column hoặc điều kiện UPDATE có version:

~~~sql
UPDATE accounts
SET balance = :new_balance,
    version_no = version_no + 1
WHERE account_id = :account_id
  AND version_no = :old_version;
~~~

Nếu SQL%ROWCOUNT = 0, dữ liệu đã thay đổi bởi transaction khác hoặc hàng không tồn tại; ứng dụng phải xử lý conflict. Đây là semantics nghiệp vụ, không chỉ là vấn đề hiệu năng.

### Deadlock và thứ tự lock

Nếu transaction A khóa row 1 rồi row 2, transaction B khóa row 2 rồi row 1, có thể xảy ra deadlock. Sau khi rewrite DML hoặc thêm bước update, kiểm tra thứ tự truy cập/khóa và test concurrency. Oracle sẽ chọn một statement làm deadlock victim; ứng dụng cần xử lý lỗi và retry có kiểm soát.

### Phân trang ổn định

Nếu dùng OFFSET/FETCH hoặc keyset pagination, kiểm tra:

- Thứ tự có deterministic không?
- Có bỏ sót/lặp hàng khi dữ liệu thay đổi giữa các trang không?
- Predicate phân trang có dùng cùng sort key/index không?
- Tie-breaker có duy nhất không?

Một query phân trang nhanh nhưng trả duplicate hoặc bỏ sót bản ghi dưới concurrency không đạt yêu cầu.

## 15. Thiết kế benchmark có thể lặp lại

Một benchmark tốt cần tách các giai đoạn:

1. **Setup:** tạo/restore dữ liệu, statistics và môi trường.
2. **Warm-up:** chạy để nạp code, parse và cache theo kịch bản xác định.
3. **Measurement:** chạy số lần/thời lượng đủ lớn, thu latency, throughput và resource counters.
4. **Correctness:** đối chiếu kết quả và side effects.
5. **Cleanup:** rollback/dọn dữ liệu thử nghiệm, đóng session và lưu log.

### Warm cache và cold cache

Warm-cache test đo workload sau khi data blocks có thể đã ở buffer cache. Cold-cache test đo tình huống ít cache hơn nhưng rất khó tái tạo trong production; không flush buffer cache/shared pool tùy tiện trên hệ thống dùng chung.

Ghi rõ đang đo cold hay warm. So sánh A warm với B cold là không công bằng.

### Parse và execute

Một lần đầu có thể chịu hard parse, load PL/SQL, library cache lookup hoặc cache miss. Nếu production gọi SQL lặp lại với cursor reuse, benchmark chỉ đo lần đầu không đại diện.

Đo riêng:

- Hard parse/soft parse.
- Execute/fetch.
- Warm-up và steady state.
- Query với bind values phổ biến và hiếm.

### Lặp lại và thứ tự A/B

Chạy nhiều vòng và đổi thứ tự phiên bản, ví dụ A-B-B-A hoặc random order trong môi trường test, để giảm bias do tải nền và cache. Không chạy toàn bộ A rồi vài giờ sau mới chạy B nếu môi trường có biến động theo thời gian.

### Cùng mức concurrency

Một session giúp hiểu latency đơn lẻ; nhiều session mới thể hiện contention. Chạy concurrency theo các mức đại diện, tránh tăng tải tới mức gây ảnh hưởng hệ thống khác. Ghi throughput, p95/p99, error rate, CPU và I/O ở từng mức.

### Không dùng DBMS_OUTPUT trong benchmark

DBMS_OUTPUT và việc in từng row có thể làm phép đo chậm vì format, buffer và client fetch. Benchmark query nên tiêu thụ kết quả theo cách tương đương ứng dụng, nhưng không thêm công việc hiển thị không cần thiết.

### Dữ liệu benchmark phải đại diện

Đảm bảo data skew, NULL ratio, số distinct values, độ dài row, partition sizes và số lượng hàng tương tự production. Một bảng lab nhỏ có thể khiến optimizer chọn plan khác hoàn toàn.

## 16. Phân tích kết quả trước/sau

Sau benchmark, không chỉ báo “nhanh hơn X%”. Hãy giải thích thay đổi dựa trên metric và kiểm tra xem lợi ích có đánh đổi tài nguyên nào không.

### Tính phần trăm cải thiện latency

Nếu latency giảm từ \(T_{before}\) xuống \(T_{after}\):

\[
\text{Latency improvement} =
\frac{T_{before} - T_{after}}{T_{before}} \times 100\%
\]

Ví dụ median giảm từ 100 ms xuống 75 ms:

\[
\frac{100-75}{100}\times 100\% = 25\%
\]

Với throughput tăng từ \(R_{before}\) lên \(R_{after}\):

\[
\text{Throughput increase} =
\frac{R_{after} - R_{before}}{R_{before}} \times 100\%
\]

Luôn ghi rõ metric là median, p95, p99 hay average. Không dùng một tỷ lệ improvement chung cho tất cả.

### Ma trận trade-off

| Kết quả đo | Diễn giải có thể | Việc cần kiểm tra |
| --- | --- | --- |
| Latency giảm, CPU giảm, buffer gets giảm | Có thể giảm lượng công việc thực sự | Xác nhận correctness và concurrency. |
| Latency giảm, physical reads tăng | Cache/warm state hoặc access path thay đổi | Lặp lại warm/cold test, đo bytes và storage latency. |
| Latency đơn lẻ giảm, throughput giảm | Có thể tăng contention hoặc tiêu thụ tài nguyên mỗi request | Test concurrency và session waits. |
| CPU giảm, elapsed không đổi | Query có thể đang chờ I/O/lock/network | Xem wait events và transaction. |
| Buffer gets giảm, redo tăng | Read path tốt hơn nhưng write maintenance tăng | Benchmark DML và tổng workload. |
| p50 tốt hơn, p99 xấu hơn | Một nhóm request bị ảnh hưởng hoặc contention tăng | Phân nhóm bind values và request class. |
| Plan hash đổi, runtime tốt hơn | Optimizer chọn plan khác có lợi cho mẫu workload | Test nhiều bind values và workload khác. |
| Plan hash không đổi, runtime tốt hơn | Cache, tải nền hoặc runtime conditions khác | Kiểm soát điều kiện và đo lại. |

### Đánh giá tác động lên workload tổng thể

Một thay đổi SQL không nên được đánh giá chỉ bằng query mục tiêu. Ví dụ index mới có thể giảm latency SELECT nhưng tăng:

- Thời gian INSERT/UPDATE/DELETE.
- Redo generation và archive log volume.
- Storage footprint và backup duration.
- Latch/buffer contention trên index hot block.
- Chi phí optimizer statistics và maintenance.

Đo cả read/write mix theo tỷ lệ production. Nếu một query chỉ chiếm 1% DB time nhưng index làm tất cả DML chậm hơn, thay đổi có thể không đáng.

### Dùng ngưỡng chấp nhận trước khi thử

Định nghĩa tiêu chí trước khi chạy, ví dụ:

- Correctness: không có khác biệt kết quả hoặc invariant.
- Error rate: không tăng vượt ngưỡng.
- p95: giảm ít nhất 15%.
- p99: không xấu hơn quá 5%.
- Throughput: không giảm ở concurrency mục tiêu.
- CPU/request và buffer gets/request: không tăng quá mức cho phép.
- DML latency: không tăng vượt ngân sách.

Ngưỡng là ví dụ; hệ thống cần chọn SLA/SLO và ngân sách tài nguyên phù hợp.

## 17. Bài thực hành: đo query trước và sau khi thêm index

Bài lab tạo bảng riêng, nạp dữ liệu giả lập, đo query tổng hợp, kiểm tra plan, thêm index rồi so sánh cả kết quả và metric. Thực hiện trong schema học tập có quyền CREATE TABLE và CREATE INDEX. DDL có implicit commit trong Oracle.

### Bước 1: tạo bảng mẫu

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_status VARCHAR2(10) NOT NULL,
    order_amount NUMBER(12,2) NOT NULL,
    created_at DATE NOT NULL
);
~~~

### Bước 2: nạp dữ liệu đại diện

~~~sql
INSERT INTO lab_orders (
    order_id,
    customer_id,
    order_status,
    order_amount,
    created_at
)
SELECT level,
       MOD(level, 1000),
       CASE WHEN MOD(level, 100) = 0 THEN 'OPEN' ELSE 'CLOSED' END,
       MOD(level * 17, 100000) / 100,
       DATE '2025-01-01' + MOD(level, 365)
FROM dual
CONNECT BY level <= 200000;

COMMIT;
~~~

Dữ liệu này có status skew và nhiều order theo customer. Quy mô lab chỉ phục vụ quan sát; không đại diện mọi phân bố production.

### Bước 3: gather stats ban đầu

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => TRUE
    );
END;
/
~~~

### Bước 4: đo phiên bản A chưa có index phụ

Bật timing ở SQL*Plus/SQLcl:

~~~sql
SET TIMING ON;

SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_status = 'OPEN'
GROUP BY customer_id;
~~~

Ngay sau query, xem plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Ghi elapsed time ở client, E-Rows/A-Rows, Starts, Buffers, Reads và plan hash. Chạy warm-up rồi đo nhiều lần, không lấy một execution làm kết luận.

### Bước 5: lưu kết quả phiên bản A

~~~sql
CREATE TABLE lab_result_before AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_status = 'OPEN'
GROUP BY customer_id;
~~~

Bảng snapshot lưu kết quả để so sánh. CTAS là DDL và commit ngầm; dùng trong schema lab.

### Bước 6: thêm index

~~~sql
CREATE INDEX ix_lab_orders_customer_status
ON lab_orders(customer_id, order_status);
~~~

Index này có thể hỗ trợ predicate equality trên CUSTOMER_ID và ORDER_STATUS. Không giả định optimizer chắc chắn chọn index; quyết định phụ thuộc cost, statistics và phiên bản.

Thu thập lại table/index stats:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => TRUE
    );
END;
/
~~~

### Bước 7: đo phiên bản B

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_status = 'OPEN'
GROUP BY customer_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Ghi cùng các metric như phiên bản A. Chạy nhiều lần và giữ cùng cache protocol. Có thể query vẫn dùng full scan nếu optimizer thấy phù hợp; hãy đọc plan thực tế.

### Bước 8: lưu kết quả phiên bản B

~~~sql
CREATE TABLE lab_result_after AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_status = 'OPEN'
GROUP BY customer_id;
~~~

### Bước 9: kiểm tra tính đúng hai chiều

~~~sql
SELECT customer_id, order_count, total_amount
FROM lab_result_before
MINUS
SELECT customer_id, order_count, total_amount
FROM lab_result_after;

SELECT customer_id, order_count, total_amount
FROM lab_result_after
MINUS
SELECT customer_id, order_count, total_amount
FROM lab_result_before;
~~~

Hai truy vấn phải không trả hàng. Vì kết quả đã GROUP BY CUSTOMER_ID, mỗi customer có tối đa một row trong tập kết quả. Nếu query thực tế có duplicate semantics, cần thêm kiểm tra multiplicity.

### Bước 10: kiểm tra chi phí ghi

Thử INSERT/UPDATE/DELETE trên LAB_ORDERS trước và sau index ở cùng số lượng hàng. Ghi elapsed, CPU, redo, buffer gets và throughput. Index mới có thể làm các thao tác ghi tốn thêm chi phí bảo trì.

### Bước 11: dọn lab

~~~sql
DROP TABLE lab_result_before PURGE;
DROP TABLE lab_result_after PURGE;
DROP TABLE lab_orders PURGE;
~~~

Chỉ dọn sau khi đã lưu số liệu. DROP là DDL và có implicit commit.

## 18. Lỗi thường gặp khi đo hiệu năng

| Sai lầm | Vì sao gây kết luận sai | Cách sửa |
| --- | --- | --- |
| Chỉ đo một lần | Bị ảnh hưởng hard parse, cache và tải nền | Warm-up, lặp nhiều lần và dùng percentile. |
| Chỉ so sánh average | Che giấu tail latency | Theo dõi p50/p95/p99 và max. |
| A chạy warm, B chạy cold | Cache state không tương đương | Quy định rõ warm/cold protocol. |
| Dùng bảng nhỏ hơn production nhiều | Optimizer chọn plan khác | Dùng data volume, skew và partition gần thực tế. |
| Chỉ đo SELECT | Bỏ qua chi phí index/DML/redo | Đo read/write mix và transaction. |
| Không giữ bind values giống nhau | Selectivity và child cursor khác | Ghi bind values và test nhiều nhóm bind. |
| Chỉ nhìn EXPLAIN PLAN | Không phải lúc nào cũng là cursor thực tế | Dùng DISPLAY_CURSOR và ALLSTATS LAST. |
| Coi V$SQL elapsed_time là một execution | Counter tích lũy nhiều executions | Lấy delta hoặc chia executions, hiểu child cursor. |
| So sánh system waits để kết luận một SQL | Số liệu trộn mọi session | Dùng session/SQL-level tracing và instrumentation. |
| Không kiểm tra correctness | Có thể nhanh hơn vì bỏ sót dữ liệu | So sánh result sets, duplicates, NULL và invariant. |
| Không test concurrency | Bỏ qua lock, deadlock và race | Test nhiều session và retry paths. |
| Chạy benchmark cùng job nền bất thường | Tải nền làm méo số liệu | Chọn cửa sổ ổn định và ghi nhận background load. |
| Flush shared pool/buffer cache trên production | Làm ảnh hưởng toàn hệ thống | Chỉ thử cold cache trong môi trường cô lập. |
| Bỏ qua licensing công cụ | Có thể sử dụng tính năng không được cấp phép | Xác nhận Diagnostics/Tuning Pack trước khi dùng. |

## 19. Câu hỏi tự kiểm tra

1. **Latency là gì?** Thời gian hoàn tất một đơn vị công việc theo ranh giới đo đã xác định.
2. **Throughput là gì?** Số đơn vị công việc hoàn thành trong một đơn vị thời gian.
3. **Vì sao phải đo p95/p99?** Để thấy tail latency mà average/median có thể che giấu.
4. **CPU time khác elapsed time thế nào?** CPU time là thời gian xử lý CPU; elapsed bao gồm cả thời gian chờ và các thành phần khác trong ranh giới đo.
5. **DB time là gì?** Tổng thời gian foreground session dành cho database calls, gồm CPU và non-idle waits.
6. **Buffer gets phản ánh điều gì?** Số lần truy cập block logic trong buffer cache.
7. **Physical reads khác buffer gets thế nào?** Physical reads cần lấy block từ storage; buffer gets có thể được phục vụ từ cache.
8. **V$SQL ELAPSED_TIME có phải latency một lần chạy?** Không; đó là counter tích lũy theo cursor/child.
9. **Làm sao xem actual rows?** Dùng GATHER_PLAN_STATISTICS và DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST.
10. **E-Rows và A-Rows khác nhau gì?** Số hàng optimizer ước lượng và số hàng thực tế của row source.
11. **Khi nào dùng SQL Trace/TKPROF?** Khi cần phân tích parse/execute/fetch, waits, bind và hoạt động SQL chi tiết.
12. **SQL Monitor/AWR/ASH có cần xem license không?** Có; nhiều tính năng thuộc Tuning Pack/Diagnostics Pack tùy release/contract.
13. **DBMS_APPLICATION_INFO dùng làm gì?** Gắn module/action để liên kết SQL với workload.
14. **MINUS hai chiều chứng minh điều gì?** Hai tập giá trị phân biệt bằng nhau, nhưng không chứng minh multiplicity duplicate bằng nhau.
15. **Vì sao phải kiểm tra NULL riêng?** SQL dùng three-valued logic; phép so sánh bằng thông thường không xem NULL bằng NULL.
16. **Vì sao cần test concurrency?** Để phát hiện lock contention, race, lost update, deadlock và lỗi retry.
17. **Tại sao index mới phải đo cả DML?** Vì INSERT/UPDATE/DELETE phải duy trì thêm index entries và redo.
18. **Vì sao không flush buffer cache trên production để benchmark cold?** Đây là thao tác ảnh hưởng toàn instance và workload khác.
19. **Plan hash value có đủ để kết luận plan giống nhau không?** Không; còn bind, predicates, child cursor, adaptive behavior và runtime.
20. **Một thay đổi được coi là thành công khi nào?** Khi correctness giữ nguyên và các mục tiêu latency/throughput/resource được cải thiện hoặc đáp ứng trade-off đã định trước.

Mỗi thay đổi SQL cần một baseline và workload đại diện. Đo latency bằng nhiều mẫu và percentile, đo throughput ở nhiều mức concurrency, đồng thời theo dõi CPU, buffer gets, physical I/O, redo và wait events. Dùng V$SQL, DBMS_XPLAN, trace hoặc công cụ giám sát phù hợp để giải thích nguyên nhân, không chỉ ghi nhận con số. So sánh kết quả hai chiều, duplicate, NULL, ordering, DML effects và transaction behavior. Chỉ chấp nhận thay đổi khi kết quả đúng và hiệu năng tốt hơn theo tiêu chí đã đặt ra trên workload thực tế.
