# Parallel execution, degree of parallelism và nguy cơ dùng quá tài nguyên trong Oracle

## 1. Parallel execution giải quyết bài toán gì?

Parallel execution (PX) cho phép Oracle chia một số công việc của câu SQL thành nhiều phần và thực hiện đồng thời trên nhiều parallel execution server. Thay vì một process xử lý toàn bộ dữ liệu tuần tự, Query Coordinator (QC) điều phối các worker, phân công dữ liệu và tổng hợp kết quả.

PX hữu ích với workload xử lý lượng dữ liệu lớn:
- Quét và tổng hợp bảng fact rất lớn.
- Hash join giữa các tập dữ liệu lớn.
- CTAS, tạo index hoặc một số thao tác partition maintenance.
- Batch ETL, báo cáo và phân tích chạy theo cửa sổ thời gian.
- Một số truy vấn đọc dữ liệu phân vùng với lượng công việc đủ lớn.

Chạy song song không tự động làm SQL nhanh hơn. Mỗi worker cần CPU, memory, I/O và tài nguyên khác. Nhiều worker cùng hoạt động có thể làm hệ thống bão hòa CPU, tăng TEMP, tạo nhiều I/O, tranh chấp buffer cache hoặc chiếm hết parallel server pool khiến các câu SQL khác phải chờ.

Bài học thuộc chương **Hiệu năng hệ thống** trong module **Database Engine Relational Oracle**. Nội dung tập trung vào kiến trúc PX, **Degree of Parallelism (DOP)**, cách Oracle chọn DOP, giới hạn worker, statement queuing, Resource Manager, data distribution, parallel query, parallel DML và quy trình đo để tránh dùng quá tài nguyên.

## 2. Các thành phần trong kiến trúc parallel execution

### 2.1. Query Coordinator (QC)

QC là process điều khiển câu SQL chạy song song. QC:
- Nhận câu lệnh từ session người dùng.
- Xác định execution plan và DOP được chọn.
- Yêu cầu parallel execution servers.
- Phân chia và điều phối các operation.
- Trao đổi dữ liệu giữa các nhóm worker.
- Thu thập kết quả và trả về client.

QC vẫn là một phần của công việc. Một truy vấn song song không có nghĩa mọi công việc đều do worker làm; một số bước điều phối, xử lý kết quả cuối cùng hoặc operation không hỗ trợ PX vẫn có thể chạy ở QC.

### 2.2. Parallel execution servers

Parallel execution server (PX server) là process thực hiện một phần công việc được giao. Oracle lấy worker từ parallel execution server pool khi cần.

Một câu SQL có thể dùng một hoặc nhiều nhóm PX server ở các giai đoạn khác nhau. Worker có thể đọc dữ liệu, thực hiện join/aggregate hoặc gửi kết quả cho worker ở operation kế tiếp.

Không nên đồng nhất DOP với tổng số process mà câu SQL sẽ dùng trong mọi thời điểm. DOP mô tả mức song song của operation; một execution plan có thể dùng hai server set cho producer/consumer ở cùng một giai đoạn, nên số PX server được cấp phát có thể lớn hơn DOP. Số thực tế phụ thuộc plan, operation, pipeline và tài nguyên sẵn có.

### 2.3. Data Flow Operation (DFO)

Oracle chia execution plan song song thành các Data Flow Operation. Một DFO có thể gồm một hoặc nhiều operation và được thực hiện bởi một nhóm PX server.

Các DFO có thể trao đổi dữ liệu thông qua table queue. Ví dụ:
1. Một nhóm PX server đọc bảng orders.
2. Worker phân phối hàng theo khóa join.
3. Nhóm worker khác nhận hàng và thực hiện hash join.
4. Kết quả được gửi về QC để trả cho client.

### 2.4. Sơ đồ luồng xử lý

```text
Client session
     |
     v
Query Coordinator (QC)
     |
     +---- PX server set A: scan / producer
     |          |
     |          +---- table queue (PX SEND)
     |                         |
     +---- PX server set B: join / aggregate (consumer)
                |
                +---- kết quả gửi về QC
                             |
                             v
                           Client
```

Sơ đồ mô tả một pipeline phổ biến. Execution plan thực tế có thể có nhiều DFO, nhiều table queue, nhiều server set hoặc operation chạy tuần tự.

### 2.5. PX server pool

Oracle quản lý các PX server có thể được cấp phát cho statement. Các tham số như `PARALLEL_MAX_SERVERS`, `PARALLEL_MIN_SERVERS` và `PARALLEL_SERVERS_TARGET` ảnh hưởng khả năng cấp phát và quản lý pool.

Nếu statement yêu cầu nhiều worker hơn số lượng có thể cấp ngay, Oracle có thể giảm DOP, xếp hàng statement hoặc xử lý theo chính sách cấu hình. Hành vi cụ thể phụ thuộc `PARALLEL_DEGREE_POLICY`, Resource Manager và phiên bản.

## 3. Degree of Parallelism (DOP) là gì?

DOP là mức song song Oracle dùng cho một operation hoặc statement. DOP 1 tương ứng xử lý tuần tự; DOP lớn hơn 1 cho phép chia công việc cho nhiều PX server.

Ví dụ:

```sql
SELECT /*+ PARALLEL(o 4) */
       customer_id,
       SUM(order_amount)
FROM orders o
WHERE order_date >= DATE '2026-01-01'
GROUP BY customer_id;
```

Hint yêu cầu Oracle xem xét DOP 4 cho bảng `o`. Đây là yêu cầu/định hướng cho optimizer, không phải cam kết mọi operation luôn được cấp đúng bốn worker trong mọi tình huống.

### 3.1. DOP 4 không có nghĩa cả câu SQL chỉ dùng bốn process

Trong một DFO tree, Oracle có thể sử dụng producer và consumer server set. Với một số plan, mỗi set có thể có số worker bằng DOP. Do đó, một statement DOP 4 có thể cần tới khoảng tám PX server cho hai set hoạt động đồng thời; đây là cách ước lượng tài nguyên, không phải con số cố định cho mọi plan.

Nếu có nhiều statement chạy đồng thời, nhu cầu PX server cộng dồn. Bốn truy vấn DOP 8 cùng chạy có thể yêu cầu số worker lớn, tùy cấu trúc plan và số server set.

### 3.2. DOP không phải số CPU core được dành riêng

DOP không khóa một CPU core riêng cho mỗi worker. Nhiều worker cạnh tranh CPU trên cùng máy; hệ điều hành và Oracle scheduler phân phối thời gian CPU. Nếu DOP vượt năng lực CPU hữu ích, các worker có thể chỉ làm tăng context switching và contention.

### 3.3. DOP và kích thước dữ liệu

Một bảng rất lớn không tự động cần DOP cao. Hãy xét:
- Số block cần đọc.
- Predicate selectivity.
- Partition pruning.
- Chi phí join và aggregate.
- Storage throughput.
- CPU còn trống.
- Memory và TEMP.
- Số statement song song khác.
- Thời hạn hoàn thành workload.

Nếu predicate chỉ trả vài hàng từ một index unique scan, parallel query thường không đem lại lợi ích đáng kể.

## 4. Cách Oracle quyết định DOP

DOP có thể đến từ nhiều nguồn:
- Hint trong SQL.
- Thuộc tính `PARALLEL` của table hoặc index.
- Chính sách Auto DOP.
- Lệnh `ALTER SESSION FORCE PARALLEL QUERY`.
- Resource Manager và các giới hạn hệ thống.
- Quyết định của optimizer theo phiên bản và cấu hình.

### 4.1. DOP được chỉ định trong object attribute

```sql
ALTER TABLE sales PARALLEL 8;
```

Bảng được khai báo với degree 8. Những câu SQL truy cập bảng có thể được optimizer xem xét thực thi song song theo cấu hình và chính sách hiện hành.

Đưa bảng về mặc định tuần tự:

```sql
ALTER TABLE sales NOPARALLEL;
```

Thuộc tính object là một đầu vào cho quyết định optimizer, không bảo đảm mọi câu SQL trên bảng đều chạy DOP 8. Optimizer vẫn xem xét chi phí, loại statement và chính sách parallel execution.

### 4.2. DOP bằng SQL hint

```sql
SELECT /*+ PARALLEL(s 8) */
       region_id,
       SUM(amount)
FROM sales s
GROUP BY region_id;
```

Có thể chỉ định hint cho từng table alias. Alias trong hint phải khớp alias ở FROM clause.

Một số hint liên quan:

```sql
SELECT /*+ NO_PARALLEL(s) */ ...
FROM sales s;
```

`PARALLEL` và `NO_PARALLEL` là công cụ điều khiển có phạm vi câu SQL. Hãy dùng hint khi đã hiểu plan và cần kiểm soát một workload cụ thể; không thêm hàng loạt hint để thay thế việc đo lường.

### 4.3. FORCE PARALLEL QUERY ở session

Trong môi trường thử nghiệm:

```sql
ALTER SESSION FORCE PARALLEL QUERY PARALLEL 4;
```

Lệnh này yêu cầu session xem xét thực hiện query song song với mức được chỉ định theo semantics Oracle. Nó có phạm vi session và có thể ảnh hưởng nhiều câu truy vấn chạy sau đó.

Tắt chế độ ép:

```sql
ALTER SESSION DISABLE PARALLEL QUERY;
```

Không bật FORCE PARALLEL QUERY cho session ứng dụng dùng chung hoặc connection pool nếu chưa có chính sách rõ ràng. Một request có thể dùng cùng session với request tiếp theo.

### 4.4. PARALLEL_DEGREE_POLICY

Tham số `PARALLEL_DEGREE_POLICY` điều khiển chính sách Auto DOP và một số hành vi quản lý statement parallel. Các giá trị và chi tiết có thể thay đổi theo phiên bản Oracle; cần kiểm tra tài liệu đúng release.

Các chế độ thường gặp:

| Giá trị | Ý nghĩa khái quát |
|---|---|
| `MANUAL` | Không tự động quyết định DOP theo Auto DOP; dùng hint, object attribute hoặc cấu hình explicit |
| `LIMITED` | Cho phép một số hành vi Auto DOP trong phạm vi được xác định bởi object attribute/chính sách phiên bản |
| `AUTO` | Bật Auto DOP và các cơ chế quản lý parallel như statement queuing theo cấu hình hỗ trợ |
| `ADAPTIVE` | Chế độ có trong một số release cũ; kiểm tra trạng thái hỗ trợ/deprecation theo phiên bản |

Không thay tham số này toàn database chỉ để tối ưu một truy vấn. Thay đổi chính sách có thể tác động đến nhiều workload và cần đánh giá trên môi trường staging.

### 4.5. Auto DOP

Khi Auto DOP được bật, Oracle ước lượng chi phí/thời gian thực thi của câu SQL và quyết định có nên chạy song song, đồng thời chọn mức DOP trong giới hạn cấu hình.

Một truy vấn ước lượng chạy nhanh có thể vẫn chạy tuần tự; truy vấn lớn có thể được gán DOP lớn hơn nếu chính sách và tài nguyên cho phép.

Tham số `PARALLEL_MIN_TIME_THRESHOLD` là một trong các yếu tố liên quan ngưỡng thời gian ước lượng để Auto DOP cân nhắc parallel execution. Giá trị mặc định và semantics phụ thuộc release. Không hạ ngưỡng tùy tiện vì điều đó có thể làm nhiều câu SQL nhỏ chuyển sang chạy song song.

### 4.6. Giới hạn DOP

`PARALLEL_DEGREE_LIMIT` và các giới hạn liên quan có thể giới hạn DOP Auto DOP. Resource Manager cũng có thể áp dụng giới hạn theo consumer group.

Giới hạn DOP bảo vệ database khỏi một câu SQL yêu cầu mức song song quá lớn, nhưng không thay thế việc kiểm soát số câu SQL đồng thời.

## 5. Các tham số quản lý PX server quan trọng

Tên tham số và giá trị mặc định phụ thuộc phiên bản, edition, cấu hình instance và số CPU được Oracle nhận diện. Kiểm tra giá trị thực tế trước khi thay đổi.

### 5.1. PARALLEL_MAX_SERVERS

Giới hạn tối đa số PX server mà instance có thể sử dụng theo cấu hình.

```sql
SHOW PARAMETER parallel_max_servers;
```

Giới hạn quá thấp có thể khiến statement phải chờ hoặc không đạt DOP mong muốn. Giới hạn quá cao có thể làm hệ thống khởi tạo quá nhiều process và tiêu thụ tài nguyên đáng kể khi nhiều statement đồng thời.

### 5.2. PARALLEL_MIN_SERVERS

Số PX server tối thiểu Oracle giữ sẵn theo chính sách pool. Giữ một số process có thể giảm thời gian khởi tạo cho workload thường xuyên dùng PX, nhưng cũng tiêu tốn tài nguyên nền.

```sql
SHOW PARAMETER parallel_min_servers;
```

### 5.3. PARALLEL_SERVERS_TARGET

Đây là ngưỡng quan trọng cho quản lý parallel server và statement queuing trong các cấu hình hỗ trợ. Khi nhu cầu PX vượt target, Oracle có thể đưa statement vào hàng đợi thay vì cấp phát vô hạn ngay lập tức.

```sql
SHOW PARAMETER parallel_servers_target;
```

Target là cơ chế điều phối tải. Nó không phải tổng số worker tuyệt đối mà mọi workload có thể dùng trong mọi trường hợp; cần hiểu cùng `PARALLEL_MAX_SERVERS`, Resource Manager và policy.

### 5.4. CPU_COUNT và PARALLEL_THREADS_PER_CPU

Các tham số này ảnh hưởng cách Oracle nhận diện năng lực CPU và ước lượng mức song song mặc định trong một số chính sách.

```sql
SHOW PARAMETER cpu_count;
SHOW PARAMETER parallel_threads_per_cpu;
```

Không tự đặt `CPU_COUNT` cao hơn CPU mà instance được phép sử dụng. Cấu hình sai có thể khiến optimizer và parallel execution đánh giá quá cao năng lực xử lý.

### 5.5. Kiểm tra tham số cùng lúc

```sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'parallel_degree_policy',
    'parallel_degree_limit',
    'parallel_min_time_threshold',
    'parallel_max_servers',
    'parallel_min_servers',
    'parallel_servers_target',
    'parallel_threads_per_cpu',
    'cpu_count'
)
ORDER BY name;
```

Cần quyền đọc `V$PARAMETER`. Không sao chép giá trị của môi trường khác làm chuẩn; hãy đánh giá theo CPU, storage, concurrency và workload của chính hệ thống.

## 6. Statement queuing: xếp hàng để bảo vệ tài nguyên

Khi nhiều câu SQL cùng yêu cầu PX, cấp worker ngay cho tất cả có thể làm database quá tải. Statement queuing cho phép Oracle xếp câu SQL vào hàng đợi và chỉ bắt đầu khi đủ tài nguyên theo chính sách.

### 6.1. Vì sao queue tốt hơn oversubscription?

Giả sử một database có khả năng phục vụ một số lượng PX worker nhất định. Nếu mười báo cáo cùng yêu cầu DOP lớn, cấp phát đồng thời có thể:
- Làm CPU bị oversubscribe.
- Tăng context switching.
- Làm mỗi báo cáo chậm hơn.
- Tăng I/O queue và TEMP.
- Làm OLTP bị ảnh hưởng.

Nếu xếp một số statement vào hàng đợi, các statement đang chạy có thể hoàn thành nhanh hơn và throughput của workload có thể tốt hơn.

### 6.2. Cấu hình liên quan

Statement queuing thường gắn với chính sách parallel degree và ngưỡng `PARALLEL_SERVERS_TARGET`. Cấu hình cụ thể phụ thuộc phiên bản và Resource Manager.

Không bật `AUTO` chỉ để có queue mà chưa đo thời gian chờ và số statement đồng thời. Queue giúp kiểm soát tải, nhưng có thể làm latency của một request tăng nếu ứng dụng không tính đến thời gian chờ.

### 6.3. Theo dõi statement bị queue

Các view về session và PX có thể giúp xác định statement đang chạy song song và số worker được yêu cầu/cấp. Một số thông tin queue và Resource Manager nằm trong các view hiệu năng tương ứng với phiên bản.

Khi điều tra, ghi lại:
- Thời gian statement ở queue.
- DOP yêu cầu.
- DOP được cấp.
- Số PX server đang dùng.
- Số statement cạnh tranh.
- CPU, I/O và Resource Manager consumer group.

### 6.4. Queue timeout và ứng dụng

Nếu ứng dụng có timeout ngắn, statement chờ queue có thể bị client timeout trước khi được chạy. Cần đồng bộ:
- SLA của request.
- Timeout JDBC/OCI/client.
- Thời gian chờ queue.
- Cửa sổ batch.
- Chính sách retry.

Retry ngay lập tức một statement bị queue có thể làm tải tăng thêm. Nếu cần retry, dùng backoff và giới hạn số lần thử.

## 7. Resource Manager và kiểm soát parallel workload

Database Resource Manager giúp phân bổ tài nguyên theo consumer group, ưu tiên và giới hạn. Đây là công cụ quan trọng khi OLTP, báo cáo và batch cùng chạy trên một database.

### 7.1. Tách workload theo consumer group

Ví dụ phân loại:
- `OLTP_CRITICAL`: giao dịch tương tác quan trọng.
- `REPORTING`: báo cáo đọc dữ liệu lớn.
- `BATCH_ETL`: batch theo lịch.
- `ADHOC_ANALYTICS`: truy vấn tùy biến.

Mỗi nhóm có thể có mức ưu tiên, giới hạn CPU, parallel server usage hoặc giới hạn DOP khác nhau theo khả năng phiên bản và cấu hình Resource Manager.

### 7.2. Giới hạn parallel server theo nhóm

Resource Manager có các thuộc tính điều khiển việc sử dụng parallel server và DOP cho consumer group, chẳng hạn giới hạn tỷ lệ parallel servers hoặc mức DOP. Tên thuộc tính và cấu hình cụ thể cần theo tài liệu Oracle đúng release.

Mục tiêu:
- Báo cáo không chiếm hết PX server.
- OLTP không bị ảnh hưởng bởi truy vấn ad hoc.
- Batch có thể dùng nhiều tài nguyên hơn trong cửa sổ đã định.
- Các nhóm có hành vi dự đoán được dưới tải cao.

### 7.3. Không dùng DOP thay thế workload governance

Ngay cả khi mọi SQL chỉ được gán DOP 4, hàng trăm statement đồng thời vẫn có thể làm database quá tải. Cần kiểm soát cả:
- Số session đồng thời.
- DOP mỗi statement.
- Số worker mỗi DFO.
- Consumer group.
- CPU và I/O.
- TEMP và PGA.
- Queueing và timeout.

## 8. Parallel execution phân chia công việc như thế nào?

### 8.1. Granules

Oracle chia dữ liệu thành các đơn vị công việc gọi là granule để PX server xử lý. Tùy operation và cấu trúc bảng, granule có thể dựa trên:
- Block range.
- Partition hoặc subpartition.
- Các đơn vị công việc khác do execution engine quản lý.

Mỗi worker nhận phần công việc và xử lý độc lập trong phạm vi operation. Khi granule được phân phối hợp lý, các worker có thể làm việc gần cân bằng.

### 8.2. Partition granules

Với bảng partition, Oracle có thể phân chia công việc theo partition/subpartition. Partition-wise join có thể giảm trao đổi dữ liệu nếu hai bảng được partition tương thích theo join key.

Nếu số partition ít hơn DOP hoặc dữ liệu tập trung ở một vài partition, mức song song thực tế có thể bị giới hạn hoặc mất cân bằng.

### 8.3. Block-range granules

Đối với một số scan, Oracle có thể chia phạm vi block thành nhiều granule để worker lấy việc. Cách này cho phép khai thác song song ngay cả khi bảng không được partition theo nhiều đơn vị phù hợp.

### 8.4. Data skew

Skew xảy ra khi công việc hoặc dữ liệu phân bố không đều giữa các worker. Ví dụ một giá trị `region_id` chiếm 80% hàng; hash distribution theo region có thể khiến một worker nhận phần lớn dữ liệu.

Hệ quả:
- Một vài worker kết thúc sớm.
- Worker chậm nhất quyết định thời gian hoàn thành toàn operation.
- DOP cao nhưng throughput không tăng tương ứng.
- Một worker có thể dùng nhiều memory/TEMP hơn.
- Table queue có thể bị nghẽn.

Tăng DOP không tự sửa data skew. Cần hiểu distribution key, cardinality, dữ liệu lệch và chiến lược phân phối.

## 9. PX data distribution và table queue

Khi hai nhóm worker cần trao đổi hàng, Oracle dùng các operation PX SEND và PX RECEIVE.

### 9.1. HASH distribution

Dữ liệu được phân phối dựa trên hash của một hoặc nhiều key. Cách này thường dùng để đưa các hàng có cùng join key về cùng worker cho hash join hoặc group by.

Nếu key có skew mạnh, một số worker có thể nhận nhiều hàng hơn.

### 9.2. BROADCAST distribution

Một tập dữ liệu nhỏ có thể được gửi đến nhiều worker để join với các tập lớn hơn. Broadcast hữu ích khi một phía nhỏ, nhưng có thể nhân bản dữ liệu qua nhiều worker và tăng memory/network traffic nếu phía broadcast không nhỏ như ước lượng.

### 9.3. RANGE distribution

Dữ liệu được chia theo khoảng giá trị, có thể hỗ trợ một số sort hoặc range-oriented operation. Cân bằng phụ thuộc phân bố dữ liệu.

### 9.4. RANDOM distribution

Dữ liệu được phân phối tương đối ngẫu nhiên giữa các worker trong những operation phù hợp. Nó có thể giúp cân bằng số hàng nhưng không bảo đảm cân bằng kích thước/chi phí xử lý từng hàng.

### 9.5. Đọc operation trong execution plan

Các operation thường gặp:
- `PX COORDINATOR`: QC điều khiển parallel execution.
- `PX SEND`: gửi dữ liệu qua table queue.
- `PX RECEIVE`: nhận dữ liệu từ table queue.
- `PX BLOCK ITERATOR`: phân phối block-range granule.
- `PX SEND HASH`: gửi theo hash key.
- `PX SEND BROADCAST`: broadcast dữ liệu.
- `PX SEND RANGE`: gửi theo range.
- `PX PARTITION`: operation liên quan partition-wise processing.

Không đánh giá plan chỉ dựa trên tên operation. Cần xem row count, bytes, starts, waits, skew và thời gian từng stage.

## 10. Parallel Query và Parallel DML

### 10.1. Parallel Query

Parallel Query chủ yếu tăng tốc đọc và xử lý truy vấn. Ví dụ:

```sql
SELECT /*+ PARALLEL(s 8) */
       product_id,
       SUM(quantity_sold)
FROM sales s
WHERE sale_date >= DATE '2026-01-01'
GROUP BY product_id;
```

Truy vấn phù hợp khi cần scan/aggregate lượng dữ liệu lớn, đủ CPU/I/O và có SLA cho phép.

### 10.2. Parallel DML cần được bật

Parallel DML không đơn giản tự động bật chỉ vì bảng có thuộc tính PARALLEL. Session hoặc statement cần bật PDML theo cơ chế Oracle hỗ trợ.

Ví dụ trong session lab:

```sql
ALTER SESSION ENABLE PARALLEL DML;
```

Hoặc hint ở statement theo phiên bản:

```sql
INSERT /*+ ENABLE_PARALLEL_DML PARALLEL(target_table 4) */
INTO target_table (id, amount)
SELECT id, amount
FROM source_table;
```

Cú pháp hint cần dùng đúng alias và phiên bản. Có thể tắt:

```sql
ALTER SESSION DISABLE PARALLEL DML;
```

### 10.3. Ví dụ parallel INSERT

```sql
ALTER SESSION ENABLE PARALLEL DML;

INSERT /*+ PARALLEL(t 4) */
INTO sales_archive t
SELECT /*+ PARALLEL(s 4) */
       s.sale_id,
       s.product_id,
       s.quantity,
       s.sale_date
FROM sales s
WHERE s.sale_date < DATE '2025-01-01';

COMMIT;
```

Đây là ví dụ minh họa. Cần kiểm tra table definition, partitioning, constraints, trigger, logging, transaction và giới hạn PDML trước khi chạy.

### 10.4. Parallel UPDATE và DELETE

Một số workload cập nhật hoặc xóa lượng lớn hàng có thể hưởng lợi từ PDML:

```sql
ALTER SESSION ENABLE PARALLEL DML;

UPDATE /*+ PARALLEL(s 4) */
       sales s
SET s.archive_flag = 'Y'
WHERE s.sale_date < DATE '2025-01-01';

COMMIT;
```

PDML có thể tạo nhiều undo/redo và I/O đồng thời. Nếu update phần lớn bảng, cần so sánh với cách batch theo partition hoặc chia phạm vi có kiểm soát.

### 10.5. ORA-12838 sau parallel DML

Sau khi một bảng đã được sửa bằng parallel DML trong transaction, một số thao tác tiếp theo truy cập lại cùng bảng trước COMMIT/ROLLBACK có thể gặp `ORA-12838` theo các điều kiện Oracle quy định.

```sql
ALTER SESSION ENABLE PARALLEL DML;

UPDATE /*+ PARALLEL(t 4) */
       target_table t
SET status = 'DONE'
WHERE batch_id = 100;

-- Không giả định có thể đọc lại bảng này ngay trong cùng transaction.
COMMIT;

SELECT COUNT(*)
FROM target_table
WHERE batch_id = 100;
```

COMMIT tạo ranh giới transaction rõ ràng. Không thêm COMMIT vào stored procedure chỉ để né lỗi nếu transaction thuộc quyền kiểm soát của caller.

### 10.6. PDML restrictions

Parallel DML có nhiều giới hạn phụ thuộc loại bảng, index, trigger, constraint, partitioning, distributed transaction và phiên bản Oracle. Một số thao tác có thể bị chuyển về serial hoặc không được hỗ trợ ở dạng song song.

Trước khi thiết kế PDML, kiểm tra tài liệu SQL Language Reference và Data Warehousing Guide đúng release. Kiểm tra execution plan/runtime để xác nhận Oracle thực sự chạy parallel DML.

## 11. Khi nào parallel execution có lợi?

PX thường đáng đánh giá khi:
- Truy vấn xử lý lượng dữ liệu lớn.
- Công việc có thể chia thành các phần độc lập.
- Có CPU và I/O còn dư.
- Có đủ PX server.
- Dữ liệu phân bố tương đối cân bằng.
- Kết quả cần hoàn tất nhanh hơn một câu SQL tuần tự.
- Workload có thể chịu chi phí khởi tạo và trao đổi dữ liệu.

Ví dụ: scan và aggregate bảng fact lớn, hash join giữa các bảng lớn, tạo index trên bảng lớn trong cửa sổ bảo trì, CTAS hoặc batch archive, báo cáo phân tích ngoài giờ OLTP cao điểm.

## 12. Khi nào không nên dùng DOP cao?

### 12.1. Truy vấn nhỏ hoặc trả rất ít hàng

Overhead tạo worker, điều phối và trao đổi dữ liệu có thể lớn hơn phần việc thực tế. Một index unique lookup thường không cần DOP cao.

### 12.2. OLTP latency-sensitive

Các giao dịch OLTP thường xử lý ít hàng và cần latency ổn định. Nhiều session OLTP cùng dùng PX có thể chiếm tài nguyên dành cho request tương tác.

### 12.3. CPU đã bão hòa

Nếu CPU đã gần bão hòa, tăng DOP thường làm worker cạnh tranh nhiều hơn. Elapsed time của từng statement có thể tăng và throughput tổng giảm.

### 12.4. Storage đã đạt giới hạn

Parallel scan có thể đẩy storage lên mức throughput tối đa, làm workload khác chậm lại. Thêm worker không làm storage nhanh hơn khi thiết bị đã bão hòa.

### 12.5. Data skew

Nếu một worker nhận phần lớn dữ liệu, DOP cao vẫn có một worker chậm kéo dài cả statement. Hãy xem số hàng/bytes theo worker và table queue.

### 12.6. Thiếu PGA hoặc TEMP

Hash join và sort song song có thể tạo nhiều workarea đồng thời. Nếu memory không đủ, operation spill ra TEMP, làm I/O tăng mạnh. Tăng DOP có thể nhân số workarea cạnh tranh và khiến tình trạng nặng hơn.

### 12.7. Nhiều statement song song đồng thời

Một truy vấn DOP 16 có thể hoạt động tốt khi chạy một mình nhưng gây quá tải khi hàng chục báo cáo cùng chạy. Cần đo dưới concurrency thực tế và kiểm soát bằng queue/Resource Manager.

## 13. Nguy cơ dùng quá tài nguyên

### 13.1. Oversubscription CPU

Nhiều PX server cùng chạy có thể khiến số runnable process vượt năng lực CPU. Hệ quả:
- Context switching tăng.
- CPU time và elapsed time tăng.
- OLTP latency xấu đi.
- Throughput không tăng dù DOP tăng.

### 13.2. Áp lực PGA và TEMP

Mỗi worker có thể cần workarea riêng. Với hash join hoặc sort, nhiều worker đồng thời làm tổng nhu cầu memory tăng. Khi không đủ PGA, Oracle có thể spill ra TEMP.

Theo dõi:
- PGA allocated/used.
- Workarea executions optimal/one-pass/multipass.
- TEMP usage.
- Direct path read/write temp.
- Hash/sort operation và số worker.

### 13.3. I/O amplification

PX scan làm nhiều process đọc đồng thời. Điều này có thể tăng throughput nếu storage còn khả năng, nhưng cũng có thể:
- Đẩy latency storage lên cao.
- Làm queue I/O dài.
- Cạnh tranh với redo, archive và workload khác.
- Tăng physical reads và bandwidth sử dụng.

### 13.4. RAC interconnect

Trong RAC, PX worker có thể chạy trên nhiều instance. Khi dữ liệu phải trao đổi giữa instance, interconnect traffic có thể tăng. Cần cân nhắc phân phối PX theo instance, locality của dữ liệu và cấu hình cluster.

### 13.5. Parallel server pool exhaustion

Nếu nhiều statement yêu cầu PX, pool có thể không còn worker rảnh. Hệ quả là statement phải queue, giảm DOP hoặc không được cấp phát như yêu cầu tùy policy. Một workload ad hoc có thể ảnh hưởng báo cáo hoặc batch quan trọng nếu không có resource governance.

### 13.6. DML side effects

PDML có thể tăng:
- Undo và redo.
- I/O ghi.
- Locking và contention ở các cấu trúc liên quan.
- Áp lực index maintenance.
- Thời gian recovery hoặc replication apply.
- Yêu cầu dung lượng tạm thời.

Không chỉ đo SELECT khi triển khai PDML.

## 14. Theo dõi parallel execution trong Oracle

### 14.1. V$PX_SESSION

`V$PX_SESSION` hiển thị thông tin session liên quan parallel execution. Có thể xem QC và worker:

```sql
SELECT sid,
       serial#,
       qcsid,
       qcinst_id,
       server_group,
       server_set,
       server#,
       degree,
       req_degree
FROM v$px_session
ORDER BY qcinst_id, qcsid, server_group, server_set, server#;
```

Các cột:
- `QCSID`: SID của Query Coordinator.
- `QCINST_ID`: instance của QC trong RAC.
- `SERVER_GROUP` và `SERVER_SET`: nhóm PX server.
- `SERVER#`: số thứ tự worker trong set.
- `DEGREE`: DOP được cấp theo view.
- `REQ_DEGREE`: DOP yêu cầu.

Có thể lọc theo QC SID của câu SQL đang điều tra. Cần quyền đọc dynamic performance view.

### 14.2. V$PX_PROCESS

```sql
SELECT server_name,
       status,
       pid,
       spid,
       sosid
FROM v$px_process
ORDER BY status, server_name;
```

View này cho biết trạng thái process PX theo phiên bản và quyền. Nó giúp nhận diện số worker đang hoạt động hoặc khả dụng.

### 14.3. V$PX_PROCESS_SYSSTAT

```sql
SELECT statistic,
       value
FROM v$px_process_sysstat
WHERE statistic IN (
    'Servers In Use',
    'Servers Available',
    'Servers Highwater',
    'Servers Started',
    'Servers Shutdown'
)
ORDER BY statistic;
```

Đây là các thống kê hệ thống theo semantics của view. Ghi snapshot trước/sau nếu muốn tính delta; không coi highwater là tải hiện tại.

### 14.4. V$PQ_TQSTAT

`V$PQ_TQSTAT` cung cấp thống kê table queue cho parallel query trong session phù hợp sau khi thực thi. Có thể dùng để quan sát lượng hàng/bytes đi qua các table queue và mức độ mất cân bằng giữa worker.

```sql
SELECT dfo_number,
       tq_id,
       server_type,
       instance,
       num_rows,
       bytes
FROM v$pq_tqstat
ORDER BY dfo_number, tq_id, server_type, instance;
```

Khả năng hiển thị và thời điểm đọc view phụ thuộc phiên bản/cách thực thi. Dùng số liệu để tìm queue có lượng dữ liệu lớn hoặc worker phân phối không đều.

### 14.5. V$SQL và runtime plan

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       px_servers_executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads
FROM v$sql
WHERE sql_id = :sql_id;
```

Cột và semantics có thể thay đổi theo release. Kết hợp với runtime plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PARALLEL +PREDICATE'
    )
);
```

Plan giúp nhận diện PX operations; runtime statistics giúp so sánh ước lượng và thực tế.

### 14.6. SQL Monitor

SQL Monitor có thể hiển thị tiến độ từng operation và worker của câu SQL dài hoặc parallel execution trong các cấu hình hỗ trợ. Đây là công cụ hữu ích để xem worker nào chậm, thời gian ở operation nào và lượng I/O.

Real-Time SQL Monitoring thường thuộc Oracle Tuning Pack theo mô hình cấp phép phổ biến. Kiểm tra quyền sử dụng trong Licensing Information User Manual và hợp đồng trước khi dùng report hoặc view liên quan.

## 15. Đọc parallel execution plan

### 15.1. Xem DOP và PX operation

Chạy truy vấn thử nghiệm rồi:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARALLEL +PREDICATE'
    )
);
```

Trong plan, chú ý:
- PX COORDINATOR.
- PX SEND/RECEIVE.
- PX BLOCK ITERATOR.
- PX PARTITION.
- Các operation scan, join, aggregate nằm trước/sau table queue.

### 15.2. Kiểm tra số worker được cấp

DOP yêu cầu có thể khác DOP thực tế. Xem `V$PX_SESSION` trong lúc statement chạy hoặc dùng SQL Monitor nếu được cấp phép. Nếu chỉ xem plan ước lượng, không kết luận đã có đủ worker.

### 15.3. Kiểm tra skew

Nếu có thống kê theo worker/table queue, so sánh:
- Số hàng mỗi worker.
- Bytes mỗi worker.
- Thời gian hoàn thành từng server set.
- Worker có lượng dữ liệu vượt trội.
- Một operation có thời gian chờ dài hơn phần còn lại.

Skew lớn thường khiến một worker trở thành điểm nghẽn.

### 15.4. Đừng chỉ nhìn DOP trong plan

Một plan có DOP 16 không chứng minh truy vấn nhanh gấp bốn lần DOP 4. Cần xem elapsed, CPU, I/O, queue time, actual rows và concurrency. DOP cao có thể làm tăng tổng tài nguyên mà không tăng tốc tương ứng.

## 16. Quy trình chọn DOP an toàn

### Bước 1. Xác định mục tiêu workload

Làm rõ mục tiêu là giảm latency một báo cáo, tăng throughput batch hay giữ OLTP ổn định. Xác định SLA và thời điểm chạy.

### Bước 2. Đo baseline serial

Chạy DOP 1 hoặc workload hiện tại trong điều kiện đại diện. Ghi:
- Elapsed time.
- CPU time.
- Buffer gets.
- Physical reads.
- Rows processed.
- TEMP/PGA.
- Wait events.
- Throughput tổng.

### Bước 3. Kiểm tra tài nguyên còn dư

Đánh giá CPU, storage, PGA, TEMP, PX server pool và workload đồng thời. Nếu tài nguyên đã bão hòa, tăng DOP thường không phải bước đầu tiên.

### Bước 4. Thử DOP tăng dần

Trong môi trường staging hoặc cửa sổ thử nghiệm có kiểm soát, thử các mức phù hợp như 2, 4, 8. Không nhảy thẳng lên DOP rất cao.

### Bước 5. Đo cùng workload

Giữ nguyên dữ liệu, bind values, concurrency và cache conditions. Ghi DOP yêu cầu và DOP thực tế.

### Bước 6. Tìm điểm lợi ích giảm dần

Nếu từ DOP 4 lên DOP 8 chỉ giảm elapsed 5% nhưng CPU gần gấp đôi, mức 8 có thể không đáng. Tìm mức đạt SLA với tổng tài nguyên thấp nhất.

### Bước 7. Thử dưới tải đồng thời

Chạy cùng số session và workload khác tương tự production. Kiểm tra p95/p99 của OLTP, queue time, PX server usage và storage latency.

### Bước 8. Đặt giới hạn và theo dõi

Đặt DOP cap, consumer group hoặc statement queue phù hợp. Theo dõi sau khi triển khai và có ngưỡng quay lui.

## 17. Ví dụ so sánh DOP

Giả sử một báo cáo scan và aggregate dữ liệu lớn. Kết quả minh họa:

| DOP | Elapsed | CPU tổng | Buffer gets | TEMP | Nhận xét |
|---:|---:|---:|---:|---:|---|
| 1 | 240 s | 210 s | 12 triệu | 2 GB | Serial, chậm |
| 2 | 135 s | 235 s | 12 triệu | 2,5 GB | Cải thiện tốt |
| 4 | 78 s | 270 s | 12,5 triệu | 3 GB | Hiệu quả |
| 8 | 52 s | 390 s | 14 triệu | 6 GB | Nhanh hơn nhưng tốn nhiều CPU/TEMP |
| 16 | 49 s | 700 s | 16 triệu | 13 GB | Lợi ích nhỏ, tài nguyên tăng mạnh |

Các con số chỉ minh họa, không phải benchmark Oracle phổ quát. Trong ví dụ này DOP 8 hoặc 16 có thể làm báo cáo riêng nhanh hơn, nhưng DOP 16 chỉ giảm thêm 3 giây so với DOP 8 trong khi CPU và TEMP tăng mạnh. Nếu hệ thống còn OLTP, DOP 8 hoặc 4 có thể là lựa chọn tổng thể tốt hơn tùy SLA.

### 17.1. Tính speedup và efficiency

Speedup:

\[
\text{Speedup}(D) = \frac{T_1}{T_D}
\]

Parallel efficiency:

\[
\text{Efficiency}(D) = \frac{T_1}{D \times T_D}
\]

Trong đó:
- \(T_1\): thời gian serial.
- \(T_D\): thời gian ở DOP \(D\).

Nếu DOP 1 mất 240 giây và DOP 8 mất 52 giây:

\[
\text{Speedup}(8) \approx 4.62
\]

\[
\text{Efficiency}(8) \approx 57.7\%
\]

Efficiency giảm khi overhead, skew, I/O hoặc contention tăng. Đây là cách mô tả hiệu quả tương đối; không phải chỉ số duy nhất để quyết định.

## 18. Thiết kế DOP theo loại workload

### 18.1. OLTP

- Ưu tiên latency ổn định.
- Giữ phần lớn truy vấn ngắn ở serial.
- Hạn chế DOP cao trong giờ cao điểm.
- Phân nhóm báo cáo nặng vào consumer group riêng.
- Giám sát queue và CPU.

### 18.2. Reporting

- Có thể dùng DOP vừa phải khi scan/aggregate lớn.
- Đo cùng workload đồng thời.
- Kiểm tra partition pruning và data skew.
- Tránh để một báo cáo chiếm hết PX server pool.

### 18.3. Batch ETL

- Xác định cửa sổ batch và dependency.
- Đo throughput toàn pipeline, không chỉ một statement.
- Kiểm tra redo/undo, TEMP, staging tables và index maintenance.
- Có thể dùng DOP cao hơn ngoài giờ OLTP nếu tài nguyên và policy cho phép.

### 18.4. Ad hoc analytics

- Giới hạn consumer group.
- Dùng statement queuing.
- Áp dụng DOP cap.
- Theo dõi truy vấn dài và query fan-out.
- Cân nhắc workload management hoặc hệ thống phân tích riêng khi nhu cầu tăng.

## 19. Các anti-pattern cần tránh

| Anti-pattern | Hệ quả | Cách xử lý |
|---|---|---|
| Đặt PARALLEL rất cao cho mọi bảng | Nhiều SQL không cần PX vẫn xin worker | Chỉ đặt attribute/hint theo workload |
| FORCE PARALLEL QUERY cho connection pool | Request ngắn cũng bị ảnh hưởng | Dùng phạm vi statement hoặc session chuyên biệt |
| Tăng PARALLEL_MAX_SERVERS để hết queue | Có thể làm oversubscribe CPU/PGA/I/O | Xác định bottleneck và kiểm soát concurrency |
| Dùng DOP cao khi CPU đã bão hòa | Context switching và latency tăng | Giảm DOP hoặc giới hạn workload |
| Chỉ benchmark một session | Bỏ qua tranh chấp khi đồng thời | Test concurrency thực tế |
| Không theo dõi TEMP/PGA | Hash/sort spill có thể làm truy vấn chậm mạnh | Đo workarea, TEMP và memory |
| Không kiểm tra data skew | Một worker kéo dài cả statement | Phân tích distribution và partition |
| Dùng PX cho truy vấn trả vài hàng | Overhead lớn hơn lợi ích | Dùng serial/index lookup |
| Chỉ so sánh elapsed | Có thể tăng CPU và giảm throughput hệ thống | So sánh tài nguyên và SLA tổng |
| Không kiểm soát queue timeout | Request có thể timeout trước khi chạy | Đồng bộ SLA, queue và client timeout |
| Bật PDML mà không hiểu transaction | Có thể gặp ORA-12838 và thay đổi semantics | Lập transaction boundary rõ |
| Bỏ qua RAC interconnect | PX cross-instance có thể tạo traffic lớn | Đo locality và network |
| Thay policy toàn DB để sửa một SQL | Tác động nhiều workload | Thử statement/session/consumer group trước |

## 20. Checklist trước khi bật parallel execution

### Trước khi thử
- Đã xác định SQL hoặc batch thực sự cần tăng tốc.
- Có baseline serial hoặc cấu hình hiện tại.
- Đã xem plan và số hàng thực tế.
- Đã xác định CPU, storage, PGA, TEMP còn dư.
- Đã kiểm tra các statement PX đang chạy.
- Đã xác định phiên bản và policy DOP.

### Trong khi thử
- Thử DOP tăng dần.
- Ghi DOP yêu cầu và DOP thực tế.
- Đo elapsed, CPU, I/O, TEMP và queue time.
- Kiểm tra số worker theo server set.
- Kiểm tra data skew.
- Chạy với concurrency gần production.
- Xác nhận kết quả SQL đúng.

### Trước khi triển khai
- Có DOP cap và Resource Manager policy phù hợp.
- Có kế hoạch rollback.
- Đã kiểm tra PDML restrictions nếu có DML.
- Đã thống nhất timeout/queue với ứng dụng.
- Đã xác định ngưỡng cảnh báo CPU, PX server, TEMP và latency.

### Sau khi triển khai
- Theo dõi throughput tổng.
- Theo dõi OLTP p95/p99.
- Theo dõi PX servers in use và highwater.
- Theo dõi TEMP, PGA, I/O và wait events.
- Kiểm tra statement queue.
- Đánh giá regression của workload khác.

## 21. Bài thực hành tổng hợp

Các ví dụ dùng schema lab và bảng lớn đã có dữ liệu. Cần quyền đọc dynamic performance views để xem một số thống kê. Không chạy thử DOP cao hoặc PDML trên production.

### Bước 1. Kiểm tra cấu hình PX

```sql
SELECT name, value
FROM v$parameter
WHERE name LIKE 'parallel%'
   OR name IN ('cpu_count')
ORDER BY name;
```

Ghi lại policy, giới hạn server và target.

### Bước 2. Kiểm tra bảng và thuộc tính parallel

```sql
SELECT table_name,
       degree,
       instances,
       temporary
FROM user_tables
WHERE table_name IN ('SALES', 'CUSTOMERS');
```

### Bước 3. Chạy baseline serial

```sql
SELECT /*+ NO_PARALLEL(s) */
       product_id,
       SUM(amount_sold)
FROM sales s
WHERE sale_date >= DATE '2026-01-01'
GROUP BY product_id;
```

Ghi elapsed, CPU, buffers, reads và số hàng.

### Bước 4. Thử DOP 2

```sql
SELECT /*+ PARALLEL(s 2) */
       product_id,
       SUM(amount_sold)
FROM sales s
WHERE sale_date >= DATE '2026-01-01'
GROUP BY product_id;
```

### Bước 5. Thử DOP 4 và 8

Lặp lại với DOP 4 và 8 trong điều kiện giống nhau. Không chạy các mức đồng thời nếu mục tiêu là đo từng mức riêng.

### Bước 6. Xem execution plan

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARALLEL +PREDICATE'
    )
);
```

### Bước 7. Quan sát PX session khi query đang chạy

Trong một session DBA khác, xác định QC SID rồi:

```sql
SELECT sid,
       serial#,
       qcsid,
       qcinst_id,
       server_group,
       server_set,
       server#,
       degree,
       req_degree
FROM v$px_session
ORDER BY qcinst_id, qcsid, server_group, server_set, server#;
```

### Bước 8. Kiểm tra PX process usage

```sql
SELECT statistic, value
FROM v$px_process_sysstat
WHERE statistic IN (
    'Servers In Use',
    'Servers Available',
    'Servers Highwater'
);
```

Chụp trước/sau để thấy delta và highwater.

### Bước 9. So sánh kết quả

| DOP | Elapsed | CPU | Buffer gets | Physical reads | TEMP | Rows |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | Đo | Đo | Đo | Đo | Đo | Đối chiếu |
| 2 | Đo | Đo | Đo | Đo | Đo | Đối chiếu |
| 4 | Đo | Đo | Đo | Đo | Đo | Đối chiếu |
| 8 | Đo | Đo | Đo | Đo | Đo | Đối chiếu |

### Bước 10. Thử statement queuing trong môi trường cấu hình riêng

Tạo workload đồng thời đủ để chạm ngưỡng PX server target, sau đó quan sát thời gian queue và số worker được cấp. Không cố tình gây quá tải trên môi trường dùng chung.

### Bước 11. Dọn trạng thái session

Nếu session đã force parallel query hoặc enable PDML, khôi phục trạng thái theo chính sách session:

```sql
ALTER SESSION DISABLE PARALLEL QUERY;
ALTER SESSION DISABLE PARALLEL DML;
```

Các lệnh này chỉ điều chỉnh trạng thái session hiện tại. Không thay đổi tham số hệ thống trong bài lab nếu không có quyền và kế hoạch DBA.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Parallel execution là gì?

**Trả lời:** Cơ chế chia một số operation của SQL thành các phần và thực hiện đồng thời bằng nhiều PX server dưới sự điều phối của Query Coordinator.

**Câu 2.** DOP là gì?

**Trả lời:** Degree of Parallelism là mức song song được dùng cho operation/statement, thể hiện số worker tham gia ở một mức xử lý song song.

**Câu 3.** DOP 8 có luôn chỉ dùng tám PX process không?

**Trả lời:** Không. Một execution plan có thể dùng producer và consumer server set; số process thực tế có thể lớn hơn DOP tùy plan.

**Câu 4.** Query Coordinator làm gì?

**Trả lời:** Điều phối statement, yêu cầu PX server, quản lý luồng dữ liệu và tổng hợp kết quả.

**Câu 5.** PARALLEL_DEGREE_POLICY điều khiển gì?

**Trả lời:** Chính sách chọn DOP và một số hành vi parallel execution như Auto DOP/statement queuing theo phiên bản.

**Câu 6.** Auto DOP có nghĩa mọi SQL đều chạy song song không?

**Trả lời:** Không. Oracle ước lượng chi phí và chỉ chọn PX khi phù hợp với ngưỡng và giới hạn.

**Câu 7.** PARALLEL_MAX_SERVERS và PARALLEL_SERVERS_TARGET khác nhau thế nào?

**Trả lời:** MAX đặt giới hạn tối đa PX server; TARGET là ngưỡng quản lý/queuing trong các cấu hình hỗ trợ.

**Câu 8.** Statement queuing giúp gì?

**Trả lời:** Xếp statement chờ tài nguyên thay vì cấp worker cho mọi câu SQL cùng lúc, giúp kiểm soát oversubscription.

**Câu 9.** Vì sao tăng DOP có thể làm SQL chậm hơn?

**Trả lời:** Worker cạnh tranh CPU, I/O, PGA, TEMP và có thể tạo skew hoặc contention.

**Câu 10.** Data skew là gì?

**Trả lời:** Dữ liệu/công việc phân bố không đều giữa worker, khiến một vài worker nhận phần lớn công việc và kéo dài toàn statement.

**Câu 11.** HASH distribution dùng khi nào?

**Trả lời:** Phân phối hàng theo hash key, thường để đưa cùng join/group key đến cùng worker.

**Câu 12.** BROADCAST distribution có rủi ro gì?

**Trả lời:** Dữ liệu được nhân bản đến nhiều worker; nếu tập broadcast lớn, memory và network traffic có thể tăng mạnh.

**Câu 13.** Parallel Query khác Parallel DML thế nào?

**Trả lời:** Parallel Query chủ yếu đọc/xử lý truy vấn; Parallel DML thực hiện INSERT/UPDATE/DELETE song song và cần bật PDML theo cơ chế hỗ trợ.

**Câu 14.** Vì sao có thể gặp ORA-12838 sau PDML?

**Trả lời:** Một số thao tác truy cập lại bảng đã bị sửa bằng PDML trong cùng transaction không được phép trước COMMIT/ROLLBACK theo quy tắc Oracle.

**Câu 15.** Vì sao cần theo dõi TEMP và PGA?

**Trả lời:** Nhiều worker có thể tạo nhiều workarea đồng thời; thiếu memory dẫn đến spill TEMP và I/O tăng.

**Câu 16.** Resource Manager giúp gì cho parallel workload?

**Trả lời:** Phân bổ và giới hạn tài nguyên theo consumer group, giúp báo cáo/batch không chiếm hết tài nguyên dành cho workload quan trọng.

**Câu 17.** DOP cao nhất có phải lựa chọn tốt nhất không?

**Trả lời:** Không. Chọn DOP đạt SLA với tổng CPU, I/O, memory và tác động workload khác ở mức chấp nhận được.

**Câu 18.** Sau khi đổi DOP cần so sánh những gì?

**Trả lời:** Elapsed, CPU, throughput, buffer gets, physical reads, TEMP, queue time, DOP thực tế, worker skew và latency của workload khác.

## 23. Kết luận

Parallel execution giúp Oracle xử lý truy vấn và thao tác dữ liệu lớn bằng nhiều PX server, nhưng DOP chỉ là một phần của bài toán. Query Coordinator, các server set, DFO, granule và table queue phối hợp để chia việc và trao đổi dữ liệu. DOP cao có thể giảm elapsed time cho một statement, đồng thời tăng CPU, PGA, TEMP, I/O, redo và nhu cầu parallel server. Khi nhiều câu SQL chạy đồng thời, tổng nhu cầu worker có thể vượt xa năng lực hệ thống.

Hãy chọn DOP dựa trên workload và số liệu. Bắt đầu từ baseline serial, thử DOP tăng dần, đo cả latency lẫn throughput, kiểm tra DOP thực tế, queue time, worker skew, CPU, I/O, PGA/TEMP và tác động đến OLTP. Dùng Auto DOP, `PARALLEL_SERVERS_TARGET`, `PARALLEL_MAX_SERVERS`, statement queuing và Resource Manager để kiểm soát cạnh tranh tài nguyên theo chính sách của database.

Parallel Query và Parallel DML có semantics và giới hạn riêng. PDML cần được bật đúng cách, có thể tạo nhiều redo/undo và có transaction restriction như ORA-12838. Không dùng hint hoặc thuộc tính PARALLEL cao cho mọi bảng, không tăng server pool chỉ để hết queue và không coi một truy vấn chạy nhanh hơn khi cô lập là bằng chứng hệ thống tốt hơn. Chỉ triển khai khi benchmark đại diện cho thấy SLA được cải thiện mà tổng workload vẫn nằm trong giới hạn tài nguyên đã định.

