# Đo tải với dữ liệu đại diện, warm-up và kế hoạch thực thi

Kiểm thử hiệu năng Oracle Database chỉ có ý nghĩa khi tải thử phản ánh cách hệ thống được sử dụng thật. Một câu SQL chạy nhanh trên vài trăm dòng dữ liệu trong máy phát triển chưa chắc chạy nhanh khi bảng có hàng chục triệu dòng, dữ liệu bị lệch phân bố, nhiều session cùng truy cập và cache đã ở trạng thái khác. Ngược lại, một lần chạy đầu tiên chậm do cache lạnh hoặc connection pool chưa khởi tạo cũng chưa đủ để kết luận truy vấn luôn chậm.

Muốn đo đúng, cần chuẩn bị dữ liệu và workload đại diện, kiểm soát môi trường, làm nóng hệ thống theo mục tiêu kiểm thử, đo nhiều lần và đọc execution plan cùng thống kê thực tế. Ba câu hỏi phải được trả lời đồng thời là: **hệ thống nhận tải gì, mất bao lâu để xử lý tải đó, và Oracle đã thực hiện SQL bằng kế hoạch nào?**

## 1. Mục tiêu của kiểm thử tải

### 1.1. Phân biệt các loại kiểm thử hiệu năng

| Loại kiểm thử | Mục tiêu | Ví dụ |
|---|---|---|
| Load test | Đo hệ thống dưới mức tải dự kiến trong vận hành. | 200 người dùng đồng thời, 80 request/giây trong 30 phút. |
| Stress test | Tăng tải vượt mức thiết kế để tìm giới hạn và cách hệ thống suy giảm. | Tăng dần từ 100 lên 500 rồi 800 request/giây. |
| Spike test | Kiểm tra phản ứng khi tải tăng đột ngột. | Từ 20 lên 300 request/giây trong vài giây. |
| Endurance/soak test | Kiểm tra ổn định khi chạy lâu. | Giữ tải 60% công suất trong 8 giờ. |
| Scalability test | Đo khả năng tăng năng lực khi thêm tài nguyên hoặc instance. | So sánh 4 CPU với 8 CPU hoặc một node với hai node RAC. |
| Benchmark truy vấn | So sánh một SQL hoặc một nhóm SQL trong điều kiện có kiểm soát. | Đo query báo cáo trước và sau khi tạo index. |

Các loại kiểm thử có thể dùng chung công cụ nhưng phải có mục tiêu và tiêu chí thành công riêng. Một load test không tự chứng minh khả năng chịu spike hoặc hoạt động ổn định cả ngày.

### 1.2. Đặt mục tiêu định lượng

Trước khi chạy, hãy xác định chỉ số cần đo và ngưỡng chấp nhận:

- **Throughput:** số request hoặc transaction hoàn tất trong một đơn vị thời gian, ví dụ request/second hoặc transaction/second.
- **Latency:** thời gian xử lý một request/transaction. Nên ghi p50, p90, p95, p99 và maximum thay vì chỉ dùng trung bình.
- **Error rate:** tỷ lệ request thất bại, timeout, deadlock, lỗi SQL hoặc kết quả sai.
- **Concurrency:** số request/session đang hoạt động cùng lúc.
- **Resource utilization:** CPU, memory, I/O, network, connection pool và TEMP.
- **Database work:** logical reads, physical reads, redo, parse, executions, rows processed, wait time và số session.

Ví dụ tiêu chí cho một API tra cứu đơn hàng:

| Chỉ số | Mục tiêu minh họa |
|---|---:|
| Throughput | 150 request/giây |
| p95 latency | Dưới 300 ms |
| p99 latency | Dưới 700 ms |
| Error rate | Dưới 0,1% |
| CPU database | Không duy trì trên 80% trong steady state |
| Connection pool | Không cạn pool, thời gian chờ lấy connection nằm trong ngưỡng |

Các con số chỉ minh họa cách viết tiêu chí. Mục tiêu thật phải lấy từ SLA/SLO, hành vi người dùng, chi phí hạ tầng và mức độ quan trọng của nghiệp vụ.

### 1.3. Đo ở cả tầng ứng dụng và database

Latency của request có thể gồm thời gian chờ ở nhiều nơi:

```text
Client
  |
  v
Load balancer / API gateway
  |
  v
Application queue / worker
  |
  v
Connection pool wait
  |
  v
JDBC + network round trip
  |
  v
Oracle parse / execute / fetch
  |
  v
Application processing / serialization
  |
  v
Response
```

Nếu API p95 tăng nhưng thời gian SQL không tăng, nguyên nhân có thể nằm ở connection pool, thread pool, serialization hoặc network. Nếu thời gian SQL tăng cùng logical reads hoặc wait time, cần phân tích database. Không quy mọi vấn đề latency về Oracle chỉ vì ứng dụng dùng Oracle.

## 2. Chuẩn bị dữ liệu đại diện

### 2.1. Kích thước dữ liệu phải gần thực tế

Execution plan và hiệu năng phụ thuộc số dòng, kích thước row, số block, phân vùng, index, LOB và mức độ thay đổi dữ liệu. Một bảng test quá nhỏ có thể khiến Oracle chọn full table scan dù production dùng index range scan, hoặc ngược lại.

Khi chuẩn bị dataset, xem xét:

- Số dòng hiện tại và dự báo tăng trưởng trong kỳ kiểm thử.
- Số lượng distinct value (NDV) của các cột lọc và join.
- Phân bố giá trị: đều, lệch, nhiều giá trị hiếm hoặc một vài giá trị chiếm phần lớn dữ liệu.
- Tỷ lệ `NULL`, chuỗi rỗng, dữ liệu dài và giá trị biên.
- Tỷ lệ insert/update/delete so với truy vấn đọc.
- Phân bố theo ngày, tháng, trạng thái, tenant hoặc partition.
- Kích thước LOB và tỷ lệ request thực sự đọc LOB.
- Quan hệ một-nhiều, khóa ngoại và mức độ fan-out khi join.

Không chỉ nhân bản một dòng mẫu thành hàng triệu dòng. Dữ liệu lặp lại quá nhiều làm sai NDV, histogram, selectivity và khả năng nén; optimizer có thể chọn kế hoạch không giống production.

### 2.2. Dữ liệu phải có skew và cardinality thực tế

Giả sử cột `STATUS` có ba giá trị:

| STATUS | Tỷ lệ thực tế |
|---|---:|
| `CLOSED` | 92% |
| `OPEN` | 7% |
| `ESCALATED` | 1% |

Truy vấn `WHERE status = 'CLOSED'` có selectivity rất khác `WHERE status = 'ESCALATED'`. Nếu dataset test chia đều ba trạng thái, optimizer có thể ước tính số dòng khác xa production. Kế hoạch của hai bind value cũng có thể khác nhau.

Với cột ngày, dữ liệu có thể tập trung ở 30 ngày gần nhất; với `CUSTOMER_ID`, một vài khách hàng có rất nhiều đơn hơn phần còn lại. Cần giữ những đặc điểm này vì chúng ảnh hưởng đến index access, join order, join method và lượng dữ liệu trung gian.

### 2.3. Dữ liệu quan hệ và tính toàn vẹn

Dataset cần giữ:

- Tỷ lệ bản ghi cha/con thực tế.
- Số dòng trung bình và phân vị của mỗi nhóm.
- Các trường hợp không có bản ghi liên quan nếu nghiệp vụ cho phép.
- Constraint, unique key, foreign key và trạng thái enable/validate.
- Các trạng thái nghiệp vụ hiếm nhưng quan trọng.
- Dữ liệu có thể gây lock contention, ví dụ nhiều request cập nhật cùng một tài khoản hoặc hàng tồn kho.

Một bài test chỉ dùng customer có một đơn hàng không phản ánh truy vấn join khi khách hàng lớn có hàng nghìn đơn. Một bài test không có cập nhật cùng khóa cũng không phát hiện contention trong luồng ghi.

### 2.4. Dữ liệu nhạy cảm và masking

Không lấy dữ liệu production có thông tin cá nhân rồi đưa vào môi trường test mà không có phê duyệt và biện pháp bảo vệ. Dùng data masking hoặc synthetic data để giữ phân bố và quan hệ cần thiết mà không để lộ dữ liệu thật.

Khi mask, cố gắng bảo toàn các đặc điểm ảnh hưởng hiệu năng:

- Độ dài chuỗi và phân bố độ dài.
- Số lượng distinct value.
- Tỷ lệ `NULL` và tỷ lệ giá trị phổ biến.
- Phân bố theo partition và thời gian.
- Quan hệ khóa giữa các bảng.
- Tỷ lệ LOB và kích thước LOB.

Mask mọi giá trị thành một chuỗi cố định có thể làm giảm NDV hoặc thay đổi compression. Với dữ liệu cần kiểm thử index, optimizer hoặc join, cách masking phải giữ đặc tính thống kê phù hợp.

### 2.5. Dữ liệu đại diện cho workload ghi

Nếu hệ thống có insert/update/delete, dữ liệu test cần phản ánh:

- Tần suất commit và kích thước transaction.
- Mức độ tranh chấp trên cùng row hoặc index leaf block.
- Tỷ lệ cập nhật cột có index.
- Mức độ tăng trưởng của sequence/identity.
- Redo generation và archive log volume.
- Trigger, cascade, audit và job phát sinh thêm thao tác.

Chỉ benchmark SELECT sẽ không cho biết index mới làm tăng chi phí DML ra sao hoặc bảng có bị nóng ở một vài block hay không.

## 3. Chuẩn bị môi trường đo

### 3.1. Môi trường phải có thể so sánh

Ghi lại và cố định càng nhiều yếu tố càng tốt:

- Oracle Database version, Release Update, edition và cấu hình instance.
- Số CPU, memory, SGA/PGA, storage type, IOPS và network.
- Cấu hình RAC, service, connection pool và số instance.
- `optimizer_features_enable`, optimizer parameters và `statistics_level`.
- Character set, timezone, NLS settings và database compatibility.
- Schema, index, partition, constraint và statistics.
- Ứng dụng, JDK, JDBC driver, Hibernate version và cấu hình pool.
- Các job nền, backup, ETL, monitoring hoặc workload khác đang chạy.

Nếu môi trường test nhỏ hơn production, ghi rõ khác biệt và không ngoại suy tuyến tính khi chưa có bằng chứng. Một database có CPU gấp đôi không nhất thiết xử lý gấp đôi request; bottleneck có thể nằm ở I/O, lock, network hoặc license/configuration.

### 3.2. Tránh workload cạnh tranh không được kiểm soát

Một phép đo có thể sai lệch nếu trong lúc test có backup, gather statistics, batch ETL, purge hoặc workload của nhóm khác. Ghi lại những hoạt động này và chọn cửa sổ đo phù hợp.

Nếu mục tiêu là kiểm tra hệ thống trong giờ cao điểm thực tế, workload nền có thể là một phần của bài test. Khi đó cần tái tạo có chủ đích và ghi rõ tỷ lệ tải từng thành phần, thay vì để hoạt động ngẫu nhiên làm nhiễu kết quả.

### 3.3. Chuẩn bị statistics

Optimizer dùng statistics để ước tính cardinality và chi phí. Dataset mới nạp hoặc thay đổi mạnh nhưng statistics cũ có thể khiến execution plan không đại diện.

Ví dụ thu thập statistics cho schema test:

```sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname          => 'APP_TEST',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
```

`AUTO_SAMPLE_SIZE` và `SIZE AUTO` để Oracle chọn cách thu thập phù hợp theo statistics và workload. Đây là ví dụ cho môi trường test; không tự động chạy gather toàn schema trên production trong giờ cao điểm. Cần đánh giá thời gian, lock/resource và chính sách statistics của hệ thống.

Kiểm tra thời điểm statistics:

```sql
SELECT table_name, num_rows, blocks, last_analyzed
FROM dba_tables
WHERE owner = 'APP_TEST'
ORDER BY table_name;
```

Với cột quan trọng:

```sql
SELECT table_name, column_name, num_distinct,
       num_nulls, histogram, last_analyzed
FROM dba_tab_col_statistics
WHERE owner = 'APP_TEST'
  AND table_name IN ('ORDERS', 'CUSTOMERS')
ORDER BY table_name, column_name;
```

Các giá trị thống kê có thể là ước tính; `NUM_ROWS` không nhất thiết là số dòng chính xác tại thời điểm truy vấn. Khi cần so sánh dữ liệu, dùng truy vấn đếm hoặc phương pháp đối soát riêng.

### 3.4. Kiểm tra index và partition

Trước khi chạy, ghi lại:

```sql
SELECT index_name, table_name, status, visibility,
       uniqueness, blevel, leaf_blocks, clustering_factor
FROM dba_indexes
WHERE owner = 'APP_TEST'
ORDER BY table_name, index_name;
```

Với bảng partition:

```sql
SELECT table_name, partitioning_type, partition_count,
       subpartitioning_type
FROM dba_part_tables
WHERE owner = 'APP_TEST';
```

Kiểm tra partition key, số partition, kích thước và dữ liệu phân bố theo partition. Một predicate không dùng được partition key hoặc áp dụng hàm không phù hợp lên cột phân vùng có thể ngăn partition pruning.

## 4. Mô hình tải và cách tạo concurrency

### 4.1. Closed workload và open workload

Hai mô hình tải thường gặp:

- **Closed model:** số virtual user cố định; mỗi user gửi request, chờ response, nghỉ theo think time rồi gửi request tiếp theo. Khi hệ thống chậm, tốc độ phát request tự giảm.
- **Open model:** request đến theo tốc độ định trước, không phụ thuộc response trước đã hoàn tất hay chưa. Khi hệ thống chậm, hàng đợi có thể tăng và thể hiện rõ khả năng xử lý arrival rate.

Closed model phù hợp mô phỏng một nhóm người dùng tương tác có think time. Open model phù hợp kiểm tra API hoặc luồng sự kiện có arrival rate gần cố định. Chọn sai mô hình có thể che giấu saturation: closed model đôi khi tạo coordinated omission vì hệ thống chậm khiến generator cũng gửi ít request hơn.

### 4.2. Ramp-up, steady state và ramp-down

Không nên đưa toàn bộ tải cực đại vào ngay từ giây đầu nếu mục tiêu là đo trạng thái ổn định. Một kịch bản thường gồm:

1. **Ramp-up:** tăng số user hoặc arrival rate theo từng bước.
2. **Warm-up:** cho cache, pool và runtime đạt trạng thái ổn định; dữ liệu giai đoạn này có thể không đưa vào thống kê chính.
3. **Steady state:** giữ tải mục tiêu đủ lâu để thu thập số liệu.
4. **Ramp-down:** giảm tải có kiểm soát và quan sát hệ thống hồi phục.

Ví dụ:

```text
Thời gian     0       5       10       40       45 phút
              |-------|-------|--------|--------|
Pha           ramp-up warm-up steady   ramp-down
Tải           0 -> 100% 100%   100%     100% -> 0
```

Thời lượng phải đủ để cache, connection pool và các chu kỳ batch/commit thể hiện hành vi ổn định. Một bài test 30 giây có thể bỏ qua checkpoint, log switch, background cleanup hoặc memory pressure chỉ xuất hiện khi chạy lâu.

### 4.3. Think time và transaction mix

Người dùng thực không gửi một request ngay sau request trước trong mọi trường hợp. Họ đọc màn hình, suy nghĩ, nhập liệu hoặc chuyển trang. Think time làm thay đổi concurrency và throughput.

Một workload tổng hợp nên có transaction mix, ví dụ:

| Loại giao dịch | Tỷ lệ minh họa |
|---|---:|
| Tra cứu đơn hàng | 55% |
| Tra cứu khách hàng | 20% |
| Tạo đơn hàng | 10% |
| Cập nhật trạng thái | 10% |
| Báo cáo tổng hợp | 5% |

Tỷ lệ thật cần lấy từ access log, APM, audit hoặc yêu cầu nghiệp vụ. Không để một query benchmark đơn lẻ đại diện cho cả ứng dụng nếu production có nhiều loại transaction.

### 4.4. Công cụ tạo tải

Các công cụ phổ biến gồm JMeter, Gatling, k6 hoặc công cụ nội bộ. Dù chọn công cụ nào, cần bảo đảm:

- Generator đủ CPU/network để không trở thành bottleneck.
- Có thể điều khiển concurrency hoặc arrival rate rõ ràng.
- Ghi latency theo percentile và error rate.
- Dùng dữ liệu đầu vào phân bố phù hợp, không gửi cùng một khóa cho mọi user nếu production không như vậy.
- Ghi timestamp đồng bộ với ứng dụng và database.
- Không lưu password, token hoặc dữ liệu cá nhân vào test script/log.

Nếu load generator chạy trên cùng host với Oracle, nó có thể cạnh tranh CPU, memory và network. Với bài test hệ thống end-to-end, đặt generator ở máy riêng thường giúp kết quả dễ diễn giải hơn.

## 5. Warm-up: làm nóng hệ thống trước khi đo

### 5.1. Vì sao lần chạy đầu có thể khác?

Lần chạy đầu có thể chậm hơn do nhiều thành phần chưa sẵn sàng:

- Database block chưa nằm trong buffer cache, cần physical read từ storage.
- Shared pool chưa có cursor/metadata phù hợp, cần hard parse.
- Data dictionary cache và library cache chưa nóng.
- Connection pool cần mở physical connection mới và thực hiện authentication/session setup.
- JVM cần load class, JIT compile method và ổn định heap/GC.
- DNS, TLS handshake, network route hoặc application cache chưa được thiết lập.
- Storage cache và OS page cache chưa có dữ liệu liên quan.

Warm-up đưa hệ thống tới trạng thái gần với vận hành ổn định trước khi đo steady-state. Tuy nhiên, cần xác định bài test muốn đo cold start, warm steady-state hay cả hai; không phải lúc nào cũng bỏ qua lần chạy đầu.

### 5.2. Phân biệt cold run và warm run

| Kiểu đo | Trạng thái | Câu hỏi trả lời |
|---|---|---|
| Cold run | Cache/pool/runtime chưa được làm nóng theo kịch bản. | Người dùng đầu tiên sau restart hoặc cache eviction chịu latency thế nào? |
| Warm run | Chạy workload trước để cache/pool/runtime đạt trạng thái ổn định. | Hiệu năng khi hệ thống hoạt động bình thường là bao nhiêu? |
| Mixed/realistic run | Có cold path, hot path và key distribution giống thực tế. | Hệ thống phản ứng thế nào với tỷ lệ người dùng mới, dữ liệu nóng và dữ liệu lạnh? |

Nên đo riêng cold-start và warm steady-state nếu cả hai đều quan trọng. Không gộp chúng thành một con số trung bình vì sẽ che mất hành vi của người dùng đầu tiên hoặc hiệu năng ổn định.

### 5.3. Warm-up ở tầng ứng dụng

Trước steady-state, có thể:

- Khởi tạo connection pool và kiểm tra kết nối.
- Gọi các endpoint quan trọng với dữ liệu đại diện.
- Nạp class và để JVM JIT compile các đường code thường dùng.
- Khởi tạo cache ứng dụng có TTL và key distribution tương tự production.
- Chạy một số transaction để Hibernate tạo metadata, chuẩn bị query và khởi tạo proxy cần thiết.

Warm-up phải sử dụng cùng loại request và phân bố khóa gần với bài đo. Nếu chỉ gọi một endpoint đơn giản, các đường code khác vẫn lạnh. Nếu cache ứng dụng chỉ có một key, nó không phản ánh hit ratio khi nhiều người dùng truy cập.

### 5.4. Warm-up ở tầng Oracle

Oracle có thể cần thời gian để buffer cache, shared pool, library cache và các cấu trúc nội bộ trở nên nóng theo workload. Chạy trước các truy vấn đại diện có thể làm nóng các block và cursor thường dùng.

Không dùng các lệnh flush như `ALTER SYSTEM FLUSH BUFFER_CACHE` hoặc `ALTER SYSTEM FLUSH SHARED_POOL` trên production chỉ để tạo một phép đo cold/warm. Đây là thao tác toàn hệ thống, có thể làm tăng I/O/hard parse và ảnh hưởng người dùng khác. Nếu cần đo cold-cache, hãy dùng môi trường test cô lập, có quyền và runbook rõ ràng.

Warm-up không có nghĩa là đọc toàn bộ bảng bằng một truy vấn duy nhất. Cần chạy transaction mix và key distribution đại diện. Nếu production có working set lớn hơn buffer cache, hệ thống sẽ vẫn có physical reads trong steady state; cố làm nóng toàn bộ bảng có thể tạo trạng thái không thực tế.

### 5.5. Connection pool warm-up

Nếu pool có minimum idle hoặc khởi tạo lazy, request đầu tiên có thể phải tạo connection mới. Để phân biệt latency kết nối với latency SQL:

- Đo thời gian lấy connection từ pool riêng.
- Ghi nhận số active/idle/pending connection.
- Chạy warm-up để tạo số connection gần mức concurrency mục tiêu.
- Xác nhận pool không tăng kích thước liên tục do leak hoặc cấu hình không phù hợp.

Không tăng `maximumPoolSize` chỉ để giảm thời gian chờ mà không đo năng lực Oracle. Quá nhiều connection đồng thời có thể tăng context switching, memory, lock contention và làm database chậm hơn.

### 5.6. Xác định warm-up đã ổn định

Không chọn một số vòng lặp cố định cho mọi hệ thống. Có thể theo dõi:

- p50/p95 latency theo từng khoảng thời gian.
- Throughput và error rate.
- Số connection active/idle và pool wait.
- Physical reads so với logical reads.
- Hard parse/parse count và shared pool activity.
- CPU, I/O latency, TEMP và wait event.
- JVM compilation/GC và heap occupancy.

Khi các chỉ số chính ổn định trong một khoảng liên tục và không còn xu hướng tăng/giảm mạnh, có thể bắt đầu steady-state measurement. Ghi rõ warm-up duration và quy tắc loại bỏ dữ liệu warm-up trong báo cáo.

## 6. Execution plan trong Oracle

### 6.1. Execution plan là gì?

Execution plan mô tả cách Oracle dự kiến hoặc đã dùng để thực thi SQL: truy cập bảng qua index hay full scan, thứ tự join, join method, cách lọc, nhóm, sắp xếp và phân vùng được truy cập.

Một plan thường gồm các operation như:

| Operation | Ý nghĩa khái quát |
|---|---|
| `TABLE ACCESS FULL` | Đọc các block của bảng theo full scan. Không mặc định là xấu; có thể phù hợp khi cần nhiều dòng. |
| `INDEX UNIQUE SCAN` | Tìm một key duy nhất trong unique index. |
| `INDEX RANGE SCAN` | Đọc một khoảng key trong index. |
| `TABLE ACCESS BY INDEX ROWID` | Dùng ROWID từ index để đọc row trong table. |
| `NESTED LOOPS` | Với mỗi dòng của một đầu vào, tìm dòng tương ứng ở đầu vào còn lại. |
| `HASH JOIN` | Xây dựng/tra cứu hash table để nối hai tập dữ liệu. |
| `MERGE JOIN` | Nối hai tập đã được sắp xếp theo khóa. |
| `HASH GROUP BY` | Nhóm bằng cấu trúc hash. |
| `SORT GROUP BY` | Sắp xếp rồi nhóm dữ liệu. |
| `SORT ORDER BY` | Sắp xếp kết quả theo thứ tự yêu cầu. |
| `WINDOW SORT` | Sắp xếp dữ liệu phục vụ analytic/window function. |
| `PARTITION RANGE ITERATOR` | Lặp qua các partition phù hợp. |

Không chọn plan chỉ dựa trên tên operation. Full scan có thể tốt hơn index nếu truy vấn đọc phần lớn bảng; hash join có thể phù hợp với tập dữ liệu lớn; nested loops có thể rất nhanh khi outer rows nhỏ và inner lookup có index tốt.

### 6.2. Xem plan ước tính bằng EXPLAIN PLAN

Ví dụ:

```sql
EXPLAIN PLAN FOR
SELECT order_id, order_date, total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date < :to_date;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` không thực thi câu SQL. Nó yêu cầu optimizer tạo một plan ước tính với bind và môi trường parse tại thời điểm explain. Plan này có thể khác plan của cursor thực tế do bind value, bind peeking, adaptive cursor sharing, session setting, statistics hoặc child cursor.

Vì vậy, dùng `EXPLAIN PLAN` để xem cấu trúc dự kiến, nhưng khi phân tích hiệu năng một lần chạy thật, hãy xem cursor đã thực thi.

### 6.3. Thu thập runtime statistics

Có thể yêu cầu thu thập thống kê thực thi cho câu SQL bằng hint `GATHER_PLAN_STATISTICS`:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date < :to_date;
```

Sau khi câu SQL hoàn tất trong cùng session, xem cursor gần nhất:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
```

`ALLSTATS LAST` hiển thị runtime statistics của lần thực thi cuối cùng có thu thập số liệu. Hint có overhead nhỏ; chỉ bật khi cần đo và so sánh với lần chạy không thu thập nếu overhead có ý nghĩa. Một cách khác là cấu hình `STATISTICS_LEVEL = ALL` trong phạm vi phù hợp, nhưng cần đánh giá tác động.

Nếu chạy qua ứng dụng/pool, câu SQL có thể được thực thi ở session khác với session DBA đang dùng để gọi `DISPLAY_CURSOR`. Khi đó, cần xác định SQL_ID, child number và session phù hợp; `NULL, NULL` chỉ tìm cursor gần nhất trong session hiện tại theo cách gọi tương ứng.

### 6.4. Các cột cần đọc trong DBMS_XPLAN

| Cột | Ý nghĩa |
|---|---|
| `E-Rows` | Số dòng optimizer ước tính cho operation. |
| `A-Rows` | Số dòng thực tế operation trả ra trong lần thực thi được ghi nhận. |
| `Starts` | Số lần operation được khởi chạy. Cần đọc cùng `A-Rows`, nhất là dưới nested loops. |
| `Buffers` | Logical reads/buffer gets được ghi nhận. |
| `Reads` | Physical reads được ghi nhận. |
| `A-Time` | Thời gian thực thi được ghi nhận ở operation theo cách hiển thị của plan. |
| `OMem`, `1Mem`, `Used-Mem` | Thông tin bộ nhớ cho operation có dùng work area. |
| `TempSpc` | Ước tính/ghi nhận không gian TEMP liên quan operation tùy format và phiên bản. |
| `Predicate Information` | Điều kiện access/filter được áp dụng ở bước nào. |
| `Partition Information` | Partition được truy cập hoặc cách pruning. |

Không cộng thời gian `A-Time` của mọi operation như các khoảng độc lập; thời gian ở node cha có thể bao gồm công việc của node con. Dùng số liệu để tìm vùng tốn thời gian, không coi mỗi dòng plan là một đoạn thời gian không chồng lấp.

### 6.5. Phân tích chênh lệch E-Rows và A-Rows

Nếu `E-Rows` khác rất xa `A-Rows`, optimizer ước tính cardinality không chính xác. Điều này có thể làm thay đổi join order, join method, index access và kích thước work area.

Ví dụ:

| Operation | E-Rows | A-Rows | Nhận xét |
|---|---:|---:|---|
| Filter `STATUS='OPEN'` | 100 | 80.000 | Ước tính thấp nhiều; kiểm tra histogram, skew và bind. |
| Join customers/orders | 5.000 | 4.800 | Ước tính khá sát. |
| Nested loops inner lookup | 1 | 1, Starts=80.000 | Một lookup lặp nhiều lần; kiểm tra tổng logical reads và index. |

Các con số chỉ minh họa. Khi `Starts` lớn, `A-Rows` ở operation con có thể là tổng qua nhiều lần khởi chạy; cần hiểu cách DBMS_XPLAN hiển thị trước khi kết luận số dòng mỗi lần.

Nguyên nhân estimate sai có thể gồm:

- Statistics cũ hoặc thiếu.
- Dữ liệu skew nhưng không có histogram phù hợp.
- Correlation giữa nhiều cột mà optimizer chưa mô hình hóa.
- Predicate dùng hàm hoặc implicit conversion.
- Bind variable có độ chọn lọc khác nhau.
- Function expression hoặc user-defined function khiến optimizer khó ước tính.
- Partition statistics/global statistics không phù hợp.

Không tạo histogram hoặc extended statistics theo phản xạ. Trước tiên xác định cột và workload bị ảnh hưởng, sau đó chọn cách thu thập statistics phù hợp và kiểm tra plan trên nhiều bind value.

### 6.6. SQL_ID, child cursor và plan hash

Một câu SQL có thể có nhiều child cursor và nhiều execution plan do bind sensitivity, session environment, object changes hoặc các lý do khác. Chỉ nhìn một SQL_ID chưa chắc đã đủ.

Có thể tra cursor trong `V$SQL`:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed
FROM v$sql
WHERE sql_text LIKE 'SELECT%FROM APP.ORDERS%'
ORDER BY last_active_time DESC;
```

Trong production, `SQL_TEXT LIKE` có thể không đủ chính xác và có thể lộ nội dung SQL; dùng SQL_ID đã lấy từ APM, trace hoặc view phù hợp. `V$SQL` là thống kê tích lũy của child cursor trong shared pool, không phải percentile latency của từng request.

`PLAN_HASH_VALUE` giúp nhận diện cấu trúc plan ở mức tổng quát. Cùng plan hash không bảo đảm thời gian chạy giống nhau vì bind value, cache, concurrency, I/O và dữ liệu có thể khác.

## 7. Đọc execution plan theo một trình tự có hệ thống

Khi phân tích SQL chậm, có thể đi theo thứ tự sau:

### Bước 1: Xác định đúng SQL và lần chạy

Ghi SQL_ID, child number, module/action, service, bind value đại diện, thời điểm chạy và transaction context. Nếu ứng dụng dùng connection pool, bật module/action qua `DBMS_APPLICATION_INFO` hoặc cơ chế tracing để liên hệ SQL với request.

### Bước 2: Đọc operation từ dưới lên

Plan tree thường thể hiện operation con tạo dữ liệu cho operation cha. Xác định bước truy cập bảng/index đầu tiên, predicate được áp dụng, join order và số dòng đi qua mỗi node.

### Bước 3: So E-Rows với A-Rows

Tìm chênh lệch lớn đầu tiên trong plan. Một sai lệch sớm có thể làm các operation phía trên nhận nhiều dòng hơn dự kiến và chọn join method không phù hợp.

### Bước 4: Xem logical reads và physical reads

`Buffers` cao cho thấy database phải xử lý nhiều block logic. `Reads` cao cho thấy có physical I/O được ghi nhận, nhưng cache và read-ahead có thể ảnh hưởng. Một query có physical reads thấp vẫn có thể chậm do CPU, latch, lock hoặc network.

### Bước 5: Kiểm tra sort/hash và TEMP

Xem `SORT ORDER BY`, `HASH JOIN`, `HASH GROUP BY`, `WINDOW SORT` có nhận quá nhiều dòng hoặc dùng TEMP hay không. Nếu work area thiếu memory, operation có thể spill ra TEMP và tăng I/O.

### Bước 6: Kiểm tra partition pruning và predicate

Xác nhận điều kiện lọc được áp dụng gần nguồn dữ liệu, partition liên quan được loại bỏ và cột không bị chuyển đổi kiểu/hàm theo cách cản trở access path.

### Bước 7: Đối chiếu nhiều bind value

Chạy với giá trị phổ biến, hiếm và giá trị biên. Một plan tốt cho khách hàng nhỏ có thể kém cho khách hàng rất lớn. Kiểm tra child cursor/adaptive cursor sharing nếu plan thay đổi.

## 8. Đo thời gian và tài nguyên một cách lặp lại

### 8.1. Không dựa vào một lần chạy

Một lần đo chịu ảnh hưởng của scheduler, cache, network, GC, background process và workload cạnh tranh. Với mỗi kịch bản:

1. Chạy warm-up theo quy tắc đã định.
2. Đo steady state trong khoảng thời gian đủ dài.
3. Lặp lại nhiều lượt độc lập.
4. Ghi p50/p95/p99, throughput và error rate.
5. So sánh phân bố và độ biến động giữa các lượt, không chỉ so sánh trung bình.

Nếu kết quả giữa các lượt dao động lớn, hãy tìm nguồn biến động trước khi kết luận một thay đổi cải thiện hiệu năng.

### 8.2. Tách latency của các tầng

Ứng dụng nên ghi ít nhất:

- Thời gian chờ lấy connection.
- Thời gian thực thi SQL.
- Thời gian fetch/đọc ResultSet.
- Thời gian xử lý Java và serialize response.
- Tổng latency từ lúc nhận request đến lúc trả response.

Một truy vấn có `execute()` nhanh nhưng `ResultSet` fetch chậm vẫn làm request chậm. Nếu ứng dụng chỉ đo thời gian gọi `executeQuery()` mà không đo vòng lặp `rs.next()` và đọc cột, số đo SQL sẽ thiếu phần fetch.

### 8.3. Thống kê database

Các view như `V$SQL`, `V$SQLSTATS`, `V$SESSION`, `V$SESSION_EVENT`, `V$SYSTEM_EVENT` và `V$SYSSTAT` có thể giúp theo dõi workload. Cần lấy snapshot trước/sau hoặc dùng công cụ giám sát để tính delta; các bộ đếm tích lũy không phải số liệu riêng của một request.

Ví dụ xem wait event của session hiện tại:

```sql
SELECT event, total_waits, time_waited
FROM v$session_event
WHERE sid = SYS_CONTEXT('USERENV', 'SID')
ORDER BY time_waited DESC;
```

Đây là thống kê tích lũy theo session và đơn vị thời gian phụ thuộc view/cột. Cần đối chiếu với khoảng đo và không kết luận chỉ từ tổng thời gian tích lũy nếu session đã chạy lâu.

### 8.4. SQL Trace và TKPROF

Khi cần chi tiết parse/execute/fetch, CPU, elapsed, reads và waits, có thể thu thập SQL trace cho session hoặc module cụ thể bằng `DBMS_MONITOR` hay cơ chế phù hợp. Sau đó xử lý trace bằng TKPROF.

Trace có thể chứa SQL text, bind value và thông tin nhạy cảm; đồng thời có overhead và tạo file. Chỉ bật trong phạm vi nhỏ, thời gian ngắn, có quyền và kế hoạch dọn dữ liệu. Không bật trace toàn hệ thống trên production để thay cho một thiết kế đo lường có mục tiêu.

### 8.5. AWR, ASH và SQL Monitor

Trong môi trường có license phù hợp, AWR/ASH và SQL Monitor có thể cung cấp thông tin workload lịch sử, active session, wait và tiến độ SQL dài. Một số tính năng thuộc Oracle Diagnostics Pack hoặc Tuning Pack; quyền sử dụng phụ thuộc edition, contract và license của tổ chức. Không giả định các view/report này được phép dùng trong mọi môi trường. Nếu không có license, dùng các view và công cụ được phép như `V$SQL`, `DBMS_XPLAN`, SQL trace và monitoring hiện có.

## 9. Bind variables và plan stability trong phép đo

### 9.1. Dùng bind value giống ứng dụng

Benchmark bằng literal có thể tạo cursor và plan khác với ứng dụng dùng bind variable. Khi muốn đo workload thật, dùng cùng kiểu bind, độ dài, datatype và cách prepare statement như JDBC/Hibernate.

Ví dụ:

```sql
SELECT order_id, total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND status = :status;
```

Chạy với nhiều bind value đại diện: customer có ít đơn, customer lớn, status phổ biến và status hiếm. Không chỉ dùng một giá trị thuận lợi.

### 9.2. Bind peeking và adaptive cursor sharing

Optimizer có thể xem bind value trong quá trình hard parse (bind peeking) và chọn plan dựa trên selectivity ước tính. Với dữ liệu skew, plan được chọn cho một bind value có thể không tốt cho giá trị khác. Oracle có adaptive cursor sharing để hỗ trợ nhiều child cursor cho các nhóm bind khác nhau trong những điều kiện phù hợp.

Khi test, ghi nhận SQL_ID, child cursor, plan hash và bind value. Nếu chạy cùng SQL text nhưng mỗi lần dùng literal khác, kết quả không còn đại diện cho hành vi bind của ứng dụng.

### 9.3. Không ép plan bằng hint trước khi hiểu nguyên nhân

Hint như `INDEX`, `FULL`, `LEADING`, `USE_NL` hoặc `USE_HASH` có thể thay đổi plan. Dùng hint chỉ sau khi có bằng chứng, hiểu tác động với nhiều bind value và có quy trình theo dõi khi dữ liệu thay đổi.

Nếu plan thay đổi bất thường sau deploy hoặc gather statistics, cần so sánh plan, statistics, bind, optimizer environment và child cursor trước khi ép plan. SQL Plan Management/baseline có thể là công cụ quản trị plan trong môi trường phù hợp, nhưng không thay thế việc đo tải thực tế.

## 10. Ví dụ quy trình benchmark một truy vấn Oracle

Giả sử endpoint tìm 20 đơn hàng mới nhất của một khách hàng. Mục tiêu là so sánh trước và sau thay đổi index.

### 10.1. Ghi nhận workload

- Tỷ lệ request endpoint trong tổng traffic.
- Phân bố số đơn theo customer: median, p95 và nhóm customer lớn.
- Tỷ lệ trạng thái và khoảng ngày truy vấn.
- Concurrency dự kiến và think time.
- Số dòng trả về và tỷ lệ request đọc LOB nếu có.

### 10.2. SQL dùng trong benchmark

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND status = :status
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Bind đúng kiểu `customer_id` và `status` như ứng dụng. Chọn nhiều customer và trạng thái theo phân bố thực tế.

### 10.3. Thu execution plan thực tế

Sau khi thực thi:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +ALIAS'
    )
);
```

`+PEEKED_BINDS` có thể hiển thị bind value được optimizer peek tại hard parse nếu thông tin còn có sẵn và phiên bản hỗ trợ. Không dùng output chứa bind nhạy cảm trong báo cáo chia sẻ rộng.

### 10.4. Đo ở mức ứng dụng

Dùng JMeter/Gatling/k6 hoặc công cụ tương đương để phát transaction mix. Tạo ramp-up, warm-up, steady state và ramp-down. Ghi p50/p95/p99, throughput, error rate, pool wait, SQL duration và fetch duration.

### 10.5. So sánh hai phương án

| Chỉ số | Trước thay đổi | Sau thay đổi |
|---|---:|---:|
| p95 API latency | 420 ms | 260 ms |
| p99 API latency | 900 ms | 520 ms |
| Throughput | 110 req/s | 155 req/s |
| Error rate | 0,08% | 0,05% |
| Buffers/query | 18.000 | 5.200 |
| Physical reads/query | 120 | 25 |

Đây là số liệu minh họa, không phải kết quả thực tế. Khi đánh giá thật, giữ cùng dataset, workload, bind distribution, môi trường và warm-up. Đồng thời kiểm tra chi phí DML và dung lượng index mới; index giúp SELECT có thể làm INSERT/UPDATE/DELETE chậm hơn.

## 11. Cách tránh sai lệch trong kết quả

### 11.1. Coordinated omission

Nếu load generator chỉ gửi request tiếp theo sau khi request trước hoàn tất, hệ thống chậm sẽ khiến generator tự giảm tốc độ gửi. Báo cáo có thể cho thấy latency tốt hơn cảm nhận thực tế vì các request lẽ ra phải đến trong lúc hệ thống bị nghẽn đã không được phát.

Với workload arrival-rate cố định, dùng open model hoặc công cụ có khả năng ghi nhận scheduled time và actual start time. Báo cáo cả queueing delay và response latency nếu công cụ hỗ trợ.

### 11.2. Cache không nhất quán giữa các lượt

Nếu lượt đầu là cold cache và lượt sau là warm cache, so sánh trực tiếp sẽ sai. Quy định rõ:

- Mỗi lượt đều bắt đầu từ cold state được tái tạo có kiểm soát; hoặc
- Mỗi lượt đều có warm-up giống nhau trước khi đo; hoặc
- Đo riêng cold và warm để phục vụ hai mục tiêu khác nhau.

Không flush cache trên production để ép trạng thái giống nhau. Dùng môi trường test có thể khôi phục trạng thái và ghi lại cách chuẩn bị cache.

### 11.3. Dataset hoặc bind distribution khác nhau

Nếu lượt A dùng customer nhỏ và lượt B dùng customer lớn, chênh lệch latency không thể quy cho thay đổi index. Dùng seed hoặc bộ dữ liệu đầu vào có thể tái lập; ghi tỷ lệ bind theo nhóm.

### 11.4. Không kiểm soát background workload

Backup, gather stats, ETL hoặc một test khác có thể làm tăng I/O và CPU. Ghi nhận các hoạt động đồng thời và lặp lại phép đo khi môi trường ổn định nếu cần.

### 11.5. Chỉ nhìn average

Average có thể che một nhóm request rất chậm. Ví dụ 99 request mất 50 ms và một request mất 5 giây có thể tạo average không quá lớn nhưng p99 cho thấy vấn đề rõ ràng. Luôn xem phân vị và phân bố latency.

## 12. Báo cáo kết quả kiểm thử

Một báo cáo có thể tái lập cần lưu:

| Nhóm | Nội dung |
|---|---|
| Mục tiêu | SLA/SLO, câu hỏi cần trả lời, tiêu chí pass/fail. |
| Môi trường | Oracle version, patch, CPU, memory, storage, RAC, JDK, JDBC, pool. |
| Dữ liệu | Row count, skew, NDV, partition, LOB, statistics timestamp, masking method. |
| Workload | Transaction mix, arrival model, concurrency, think time, ramp-up và thời lượng. |
| Warm-up | Thời gian, request mix, tiêu chí ổn định, cách loại bỏ sample warm-up. |
| Kết quả ứng dụng | Throughput, p50/p95/p99/max, error rate, queueing và pool wait. |
| Kết quả database | SQL_ID, child, plan hash, E-Rows/A-Rows, buffers, reads, CPU, waits, TEMP. |
| Sai lệch | Background job, cache state, test generator saturation, lỗi môi trường. |
| Thay đổi | Index, SQL, statistics, parameter hoặc cấu hình đã thay. |
| Kết luận | Kết quả so với ngưỡng, giới hạn ngoại suy và hành động tiếp theo. |

Đính kèm execution plan và log đã loại bỏ credential/bind nhạy cảm. Ghi rõ thời điểm và timezone để đối chiếu với APM, alert log và hệ thống monitoring.

## 13. Quy trình thực hành từ đầu đến cuối

1. **Xác định mục tiêu:** chọn load, stress, spike, endurance hoặc benchmark SQL; đặt SLA/SLO và tiêu chí pass/fail.
2. **Lập workload model:** transaction mix, arrival rate/concurrency, think time, ramp-up và thời gian steady state.
3. **Chuẩn bị dữ liệu:** đủ quy mô, skew, NDV, quan hệ, LOB và tỷ lệ DML; mask dữ liệu nhạy cảm nhưng giữ đặc tính thống kê.
4. **Cố định môi trường:** ghi version, patch, CPU, memory, storage, network, pool, statistics và workload nền.
5. **Chuẩn bị quan sát:** APM, metrics generator, Oracle session/SQL statistics, execution plan và timestamp đồng bộ.
6. **Chạy warm-up:** dùng cùng request mix và bind distribution; tách số liệu warm-up khỏi steady-state nếu mục tiêu là warm performance.
7. **Đo tải:** chạy theo arrival model đã chọn, thu percentile, throughput, error rate và tài nguyên.
8. **Đọc execution plan thực tế:** dùng `DBMS_XPLAN.DISPLAY_CURSOR` với runtime statistics; so E-Rows/A-Rows, buffers, reads, TEMP và predicates.
9. **Thay đổi từng yếu tố:** SQL, index, statistics hoặc cấu hình; không đổi nhiều thứ cùng lúc nếu cần xác định nguyên nhân.
10. **Lặp lại:** dùng cùng dataset, bind distribution, warm-up và tải; so sánh nhiều lượt.
11. **Đánh giá tác động phụ:** DML, dung lượng index, concurrency, lỗi, connection pool và workload khác.
12. **Lưu báo cáo:** giữ runbook, cấu hình, plan, số liệu và giới hạn để người khác có thể tái lập.

## 14. Các nguyên tắc cần nhớ

- Dữ liệu test phải phản ánh quy mô, skew, quan hệ và tỷ lệ đọc/ghi của production.
- Một dataset nhỏ hoặc quá đều có thể dẫn tới plan và hiệu năng không đại diện.
- Warm-up và cold run là hai mục tiêu đo khác nhau; cần ghi rõ đang đo loại nào.
- Không flush cache trên production để tạo cold run.
- Dùng workload mix và mô hình arrival phù hợp; tránh coordinated omission.
- Đo p50/p95/p99, throughput và error rate, không chỉ average.
- Phân biệt thời gian lấy connection, SQL execute, fetch và xử lý ứng dụng.
- `EXPLAIN PLAN` là ước tính; runtime plan nên xem bằng `DBMS_XPLAN.DISPLAY_CURSOR`.
- So sánh `E-Rows` với `A-Rows` và đọc cùng `Starts`, `Buffers`, `Reads`, `A-Time`, TEMP.
- Dùng bind value và datatype giống ứng dụng; thử cả giá trị phổ biến và hiếm.
- Không ép index hoặc plan bằng hint trước khi hiểu cardinality và workload.
- Kiểm soát statistics, background jobs, phiên bản và tài nguyên giữa các lượt đo.
- Bảo vệ bind value, trace, plan và log vì chúng có thể chứa thông tin nhạy cảm.

## Kết luận

Đo tải Oracle có giá trị khi dataset giữ được quy mô và phân bố gần production, workload mô phỏng đúng concurrency và transaction mix, còn môi trường cùng trạng thái warm-up được kiểm soát giữa các lượt. Cold run cần được đo riêng khi quan tâm tới trải nghiệm sau restart; warm steady-state cần có giai đoạn làm nóng rõ ràng trước khi thu số liệu. Execution plan cho biết Oracle xử lý SQL bằng cách nào, nhưng plan ước tính không thay thế runtime statistics. Kết hợp `DBMS_XPLAN.DISPLAY_CURSOR`, E-Rows/A-Rows, logical/physical reads, TEMP và số liệu p95/p99 ở tầng ứng dụng giúp xác định bottleneck có căn cứ và so sánh thay đổi một cách có thể tái lập.
