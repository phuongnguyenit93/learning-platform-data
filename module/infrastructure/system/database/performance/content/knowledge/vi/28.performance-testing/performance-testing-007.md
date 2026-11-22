# Dùng pgbench, sysbench hoặc bộ phát tải phù hợp với hệ quản trị

Một bài kiểm thử hiệu năng cơ sở dữ liệu chỉ có ý nghĩa khi công cụ tạo ra tải gần với câu hỏi cần trả lời. `pgbench` phù hợp để kiểm tra PostgreSQL bằng workload giao dịch chuẩn bị sẵn hoặc script SQL tùy chỉnh; `sysbench` thường được dùng để tạo workload OLTP tổng hợp trên các hệ quản trị mà bản build hỗ trợ; HammerDB, YCSB hoặc bộ phát tải riêng có thể phù hợp hơn với hệ quản trị, kiểu dữ liệu và hành vi ứng dụng khác. Chọn sai công cụ hoặc dùng workload không đại diện có thể tạo ra con số TPS đẹp nhưng không phản ánh khả năng phục vụ hệ thống thật.

Bài học thuộc chương **Kiểm thử hiệu năng** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, việc dùng `pgbench`, `sysbench` hoặc bộ phát tải phù hợp cần gắn với mục tiêu đo cụ thể, workload mix, dữ liệu, concurrency, latency percentiles, tài nguyên DB và khả năng lặp lại kết quả.

## 1. Chọn công cụ theo câu hỏi cần trả lời

Trước khi cài hoặc chạy công cụ, hãy xác định mình cần biết điều gì:

- Database xử lý được bao nhiêu transaction mỗi giây với một workload OLTP cơ bản?
- Thay đổi index hoặc cấu hình có cải thiện truy vấn cụ thể không?
- Throughput và p95/p99 thay đổi thế nào khi tăng số client đồng thời?
- Hệ thống có chịu được một tỷ lệ đọc/ghi, phân bố khóa nóng và transaction mix cụ thể không?
- Connection setup, connection pool hay SQL execution mới là phần gây chậm?
- Một query engine phân tích xử lý scan, join và aggregate lớn ra sao?
- Toàn bộ ứng dụng có đáp ứng SLO khi người dùng gửi request thật không?

Không có một công cụ duy nhất trả lời tốt tất cả câu hỏi. Công cụ benchmark database-level có thể cô lập phần lớn thời gian ở DB, nhưng không nhất thiết mô phỏng logic ứng dụng, connection pool, serialization hoặc think time. Bộ phát tải ở tầng API phản ánh đường đi end-to-end, nhưng nếu không có telemetry thì khó xác định DB là bottleneck hay tầng khác.

| Công cụ/nhóm công cụ | Hệ sinh thái và workload phù hợp | Điểm mạnh | Giới hạn cần nhớ |
|---|---|---|---|
| `pgbench` | PostgreSQL; OLTP đơn giản, read-only, read-write và script SQL tùy chỉnh | Có sẵn trong bộ công cụ PostgreSQL, dễ điều khiển client/thread, thời lượng, rate và ghi log | Workload mặc định không đại diện mọi ứng dụng; không tự mô phỏng connection pool của application |
| `sysbench` | Chủ yếu dùng cho benchmark OLTP tổng hợp với database driver được bản build hỗ trợ, thường gặp là MySQL | Nhiều workload Lua có sẵn, dễ thay đổi thread, thời lượng, kích thước dữ liệu và phân bố truy cập | Phải kiểm tra driver và phiên bản; workload mặc định có thể khác schema/query thật |
| HammerDB | SQL Server, Oracle, PostgreSQL, MySQL/MariaDB và các nền tảng được phiên bản hỗ trợ | Workload OLTP và warehouse theo mô hình TPROC, có thể tạo tải nhiều client | Cần hiểu schema, cấu hình và cách diễn giải kết quả; kết quả không tự động là kết quả TPC được chứng nhận |
| YCSB | Key-value/NoSQL và một số database có binding tương ứng | Dễ mô tả tỷ lệ read/update/insert, phân bố key và workload nhiều client | Không thay thế benchmark SQL join/transaction đặc thù nếu binding không mô phỏng được |
| Bộ phát tải JDBC/ứng dụng riêng | Java service, driver, connection pool và transaction logic thực tế | Có thể tái hiện đúng query, tham số, pool, retry và business flow | Phải tự xây dựng tính đúng đắn, điều phối tải, percentile và báo cáo; dễ tạo benchmark sai nếu thiết kế kém |
| Bộ phát tải HTTP/API | Kiểm tra end-to-end qua ứng dụng | Đo được latency người dùng, queue, serialization và các tầng phụ thuộc | Cần tracing/metrics để tách thời gian DB khỏi application, network và service khác |

### 1.1. Phân biệt benchmark database và benchmark ứng dụng

**Database benchmark** gửi truy vấn trực tiếp đến database để đo khả năng xử lý SQL, transaction, I/O và concurrency của DB. Nó thường bỏ qua một phần logic service và có thể dùng connection trực tiếp.

**Application benchmark** gửi request qua API hoặc chạy luồng nghiệp vụ hoàn chỉnh. Nó bao gồm application thread pool, connection pool, validation, serialization, cache, network và database. Đây là cách kiểm tra SLO end-to-end, nhưng cần tracing để biết thời gian nằm ở đâu.

Một quy trình đánh giá tốt thường dùng cả hai theo thứ tự: benchmark database để hiểu giới hạn của DB, sau đó benchmark ứng dụng để xác nhận toàn bộ hệ thống đáp ứng tải thực tế.

## 2. Xác định mục tiêu và giả thuyết trước khi chạy

Một benchmark cần trả lời một câu hỏi có thể kiểm chứng. Ví dụ:

> Khi tăng `max_connections` từ 200 lên 300, throughput có tăng mà p99 và lock wait vẫn nằm trong giới hạn không?

Hoặc:

> Index ghép `(customer_id, created_at)` có giảm logical reads và p95 của truy vấn tra cứu lịch sử đơn hàng không?

Ghi rõ:

- **Metric mục tiêu:** throughput, p95/p99, error rate, CPU, I/O hoặc query latency.
- **Workload:** tỷ lệ SELECT/INSERT/UPDATE/DELETE, loại transaction và query mix.
- **Tải đầu vào:** số client, concurrency hoặc offered rate.
- **Dữ liệu:** số hàng, kích thước bảng/index, phân bố khóa và working set.
- **Phạm vi đo:** database trực tiếp, proxy/pooler hay API end-to-end.
- **Giả thuyết:** thay đổi nào được kỳ vọng tác động đến metric nào và vì sao.
- **Điều kiện thành công:** ngưỡng latency, throughput, lỗi và giới hạn tài nguyên.

Không nên chạy công cụ với mặc định rồi chỉ lưu dòng TPS cuối cùng. Con số đó không cho biết workload nào được chạy, dữ liệu có vừa RAM hay không, có lỗi hay không và hệ thống đã bão hòa chưa.

## 3. Thiết kế workload đại diện

Workload là phần quyết định chất lượng benchmark. Công cụ có thể tạo hàng nghìn request mỗi giây, nhưng nếu request không giống hành vi thật thì kết quả ít giá trị.

### 3.1. Xác định transaction mix

Một workload OLTP có thể gồm:

- Point lookup theo primary key.
- Range scan theo thời gian hoặc trạng thái.
- INSERT bản ghi mới.
- UPDATE một hàng hoặc một nhóm hàng.
- DELETE/cleanup.
- Transaction nhiều câu lệnh có đọc rồi cập nhật.
- Truy vấn tổng hợp hoặc báo cáo chạy song song với OLTP.

Ví dụ tỷ lệ giả định:

| Nhóm thao tác | Tỷ lệ |
|---|---:|
| Point SELECT | 55% |
| Range SELECT | 20% |
| INSERT | 10% |
| UPDATE | 12% |
| DELETE | 3% |

Đây chỉ là ví dụ. Hãy lấy query statistics, application trace hoặc access log để ước lượng mix thật. Nếu hệ thống có một transaction quan trọng nhưng hiếm, vẫn có thể cần đưa nó vào bài kiểm thử riêng.

### 3.2. Phân bố dữ liệu và hot keys

Truy cập ngẫu nhiên đều (uniform) có thể khác xa dữ liệu thật. Trong thực tế, một số khách hàng, tenant hoặc sản phẩm có thể nhận phần lớn request. Hot keys làm tăng contention trên cùng row/index page hoặc shard.

Các phân bố thường gặp:

- Uniform: các key có xác suất gần bằng nhau.
- Zipfian: một số ít key được truy cập rất thường xuyên.
- Gaussian/normal: giá trị tập trung quanh một vùng.
- Pareto hoặc skewed: một phần nhỏ key chiếm phần lớn lượt truy cập.

Hãy chọn phân bố phù hợp với dữ liệu quan sát. Nếu chỉ benchmark uniform trong khi production có hot tenant, kết quả có thể đánh giá thấp lock contention và hotspot.

### 3.3. Kích thước dữ liệu và working set

Ghi rõ:

- Số hàng của từng bảng.
- Tổng kích thước data và index.
- Working set nóng dự kiến.
- Dữ liệu có vừa buffer pool/OS cache hay không.
- Tỷ lệ dữ liệu cũ và mới.
- Kích thước payload và độ rộng hàng.

Dataset quá nhỏ có thể nằm hoàn toàn trong RAM, làm benchmark đo chủ yếu CPU và lock. Dataset quá lớn so với storage capacity có thể khiến I/O chi phối. Cả hai đều hợp lệ nếu đó là câu hỏi cần đo, nhưng phải ghi rõ để không so sánh sai.

### 3.4. Transaction phải giữ đúng semantics

Benchmark cần thực hiện cùng số câu lệnh, isolation level, commit frequency và logic cập nhật như workload mục tiêu. Một test chỉ SELECT không thể dùng để kết luận hệ thống chịu được read-write transaction. Một test update một hàng không đại diện transaction gồm đọc số dư, kiểm tra điều kiện và cập nhật nhiều bảng.

Đảm bảo dữ liệu đầu vào hợp lệ và các phép ghi không làm dữ liệu phình vô hạn ngoài dự kiến. Nếu test lặp lại cùng một key hoặc cùng một row, contention có thể cao hơn hoặc thấp hơn production tùy mục tiêu.

## 4. Các khái niệm tải cần nắm

### 4.1. Concurrency và số client

Concurrency là số thao tác/transaction đang hoạt động đồng thời. Số client do công cụ cấu hình không nhất thiết bằng số transaction đang chạy: client có thể chờ response, ngủ theo think time hoặc đợi connection.

Tăng concurrency thường làm throughput tăng lúc đầu, nhưng sau một điểm hệ thống bão hòa. Khi đó throughput có thể đi ngang trong khi latency và queueing tiếp tục tăng.

### 4.2. Closed-loop và open-loop

**Closed-loop load:** mỗi client gửi request tiếp theo sau khi request trước hoàn thành. Khi hệ thống chậm, tốc độ phát request tự giảm. Cách này dễ tạo tải theo số client cố định nhưng có thể che khuất nhu cầu đầu vào khi latency tăng.

**Open-loop load:** bộ phát tải lên lịch request theo offered rate đã định, độc lập hơn với thời gian hoàn thành request trước. Cách này phù hợp để xem hệ thống phản ứng ra sao trước một mức nhu cầu cố định, nhưng cần quản lý queue và giới hạn backlog.

| Đặc điểm | Closed-loop | Open-loop/rate-controlled |
|---|---|---|
| Điều khiển | Số client đồng thời | Tốc độ request được đưa vào |
| Khi DB chậm | Tốc độ phát thường tự giảm | Offered rate vẫn được duy trì cho đến khi generator/queue bị giới hạn |
| Câu hỏi phù hợp | Throughput tại mức concurrency cụ thể | Khả năng phục vụ một mức tải đầu vào/SLO |
| Rủi ro | Có thể che giấu queueing và nhu cầu chưa được đáp ứng | Có thể tạo backlog hoặc coordinated omission nếu generator không theo kịp |

### 4.3. Offered load và completed throughput

- **Offered load:** số transaction/request mà generator cố gắng đưa vào mỗi giây.
- **Completed throughput:** số transaction/request hoàn tất thành công mỗi giây.
- **Error/timeout rate:** phần request thất bại hoặc không hoàn thành trong giới hạn.

Khi hệ thống bão hòa, offered load có thể cao hơn completed throughput. Khoảng chênh thể hiện backlog, từ chối tải hoặc request bị timeout. Chỉ báo cáo completed TPS mà không ghi offered rate và error rate có thể che giấu tình trạng quá tải.

### 4.4. Coordinated omission

Coordinated omission xảy ra khi load generator chỉ gửi request mới sau khi request trước hoàn tất, nên trong lúc hệ thống bị treo hoặc chậm, generator cũng ngừng tạo mẫu đo. Kết quả latency histogram có thể thiếu những khoảng thời gian mà request lẽ ra đã được gửi và phải chờ.

Để giảm vấn đề này, dùng rate-controlled/open-loop test khi cần đo ở offered load cố định, ghi lại schedule delay và backlog, hoặc chọn công cụ có cơ chế hiệu chỉnh coordinated omission được mô tả rõ. Không tự động so sánh percentile giữa hai công cụ nếu cách ghi latency khác nhau.

## 5. Quy trình benchmark có thể lặp lại

Một lần benchmark nên tuân theo trình tự:

1. **Chuẩn bị môi trường:** ghi phiên bản DB, driver, OS, CPU/RAM, storage, network, cấu hình DB và topology.
2. **Tạo dữ liệu:** dùng dataset có quy mô, phân bố và index phù hợp với câu hỏi.
3. **Xác minh correctness:** chạy một số giao dịch mẫu, kiểm tra kết quả và constraint.
4. **Ổn định hệ thống:** kiểm tra background jobs, replication lag, vacuum/checkpoint, backup và workload ngoài dự kiến.
5. **Warm-up:** chạy tải khởi động để nạp code path, connection và cache theo kịch bản đã định.
6. **Ramp-up:** tăng dần client hoặc offered rate để tránh tạo tải đột ngột không đại diện.
7. **Measurement window:** đo trong khoảng thời gian đủ dài để có nhiều mẫu và trạng thái ổn định.
8. **Cool-down:** dừng phát tải, đợi queue/transaction kết thúc và thu thập số liệu cuối.
9. **Lặp lại:** chạy nhiều lần với cùng điều kiện, ghi median và độ biến động.
10. **So sánh:** chỉ thay một yếu tố chính trong mỗi thử nghiệm và giữ lại raw output.

### 5.1. Warm-up và cache state

Warm-up có thể làm nóng buffer pool, OS page cache, plan cache, connection pool và JIT/code path. Nếu mục tiêu là steady-state workload, warm-up là cần thiết. Nếu mục tiêu là startup/cold-cache behavior, phải đo riêng và mô tả cache nào được làm lạnh.

Restart database không bảo đảm làm lạnh OS page cache hoặc storage controller cache. Không xóa cache toàn hệ thống production chỉ để tạo benchmark cold-cache.

### 5.2. Ramp-up và steady state

Ramp-up tăng tải từng bước, ví dụ 8, 16, 32, 48, 64 clients. Mỗi mức cần đủ thời gian để queue, cache và resource ổn định. Khi đã bão hòa, không nhất thiết tiếp tục tăng concurrency rất cao; các điểm sau saturation thường chỉ làm latency tăng mà không cung cấp thêm thông tin hữu ích.

### 5.3. Số lần lặp và độ tin cậy

Chạy ít nhất vài lần độc lập cho mỗi cấu hình quan trọng, đặc biệt khi môi trường có nhiễu. Báo cáo median, p95/p99 và độ phân tán giữa các lần chạy. Một lần chạy tốt bất thường không đủ để kết luận.

## 6. Dùng pgbench để kiểm thử PostgreSQL

`pgbench` là công cụ benchmark đi kèm PostgreSQL client utilities. Nó tạo workload transaction và cho phép điều chỉnh số client, số thread, thời lượng, offered rate, query script và cách kết nối.

### 6.1. Kiểm tra công cụ và kết nối

Kiểm tra phiên bản:

```bash
pgbench --version
pgbench --help
```

Đảm bảo client có thể kết nối đến database thử nghiệm bằng đúng host, port, user, TLS và authentication mode dự kiến. Dùng một database riêng cho benchmark, không khởi tạo dữ liệu benchmark trên database nghiệp vụ đang chứa dữ liệu thật.

Ví dụ connection parameters:

```bash
export PGHOST=127.0.0.1
export PGPORT=5432
export PGUSER=bench_user
export PGDATABASE=pgbench_test
```

Trên Windows có thể đặt biến môi trường theo PowerShell hoặc truyền trực tiếp các tham số `-h`, `-p`, `-U` vào `pgbench`. Không đưa password thật vào shell history hoặc tài liệu chia sẻ; dùng cơ chế credential an toàn của môi trường.

### 6.2. Khởi tạo dataset mẫu

Tạo database thử nghiệm trước, sau đó khởi tạo schema chuẩn của pgbench:

```bash
createdb pgbench_test
pgbench -i -s 50 pgbench_test
```

`-i` khởi tạo các bảng benchmark; `-s 50` đặt scale factor 50. Bảng `pgbench_accounts` có khoảng 100.000 hàng cho mỗi đơn vị scale factor, nên scale 50 tạo khoảng 5 triệu tài khoản. Các bảng benchmark khác có kích thước theo quy tắc riêng của pgbench.

Scale factor cần đủ lớn cho câu hỏi đang đo. Nếu dataset nhỏ hơn working set production nhiều lần, cache hit có thể cao hơn thực tế. Nếu dataset lớn hơn RAM, cần xem storage và I/O. Khởi tạo và nạp dữ liệu là bước chuẩn bị, không tính vào measurement window của benchmark.

### 6.3. Chạy workload mặc định

Ví dụ chạy 16 client, 4 worker thread trong 5 phút và in tiến độ mỗi 10 giây:

```bash
pgbench -c 16 -j 4 -T 300 -P 10 pgbench_test
```

Các tùy chọn:

- `-c 16`: số client đồng thời.
- `-j 4`: số worker thread phía pgbench.
- `-T 300`: thời lượng chạy 300 giây.
- `-P 10`: in tiến độ theo khoảng 10 giây.

Workload mặc định mô phỏng một transaction kiểu TPC-B-like gồm đọc và cập nhật tài khoản cùng một số thao tác liên quan. Nó có thể tạo contention trên các bảng/counter benchmark. Đây là workload tổng hợp, không phải mô hình đầy đủ cho mọi ứng dụng.

### 6.4. Chọn workload read-only hoặc biến thể

Ví dụ chỉ đọc:

```bash
pgbench -S -c 32 -j 8 -T 300 -P 10 pgbench_test
```

`-S` chọn workload select-only. Có thể dùng các script built-in khác như simple update hoặc script SQL tự định nghĩa. Đọc `pgbench --help` của đúng phiên bản để biết tùy chọn được hỗ trợ.

Không so sánh TPS của read-only với read-write rồi kết luận một cấu hình nhanh hơn nếu mục tiêu workload khác nhau. Read-only không tạo cùng WAL, lock, index maintenance hoặc commit work như write workload.

### 6.5. Điều khiển offered rate

Có thể dùng `-R` để giới hạn tốc độ transaction được lên lịch:

```bash
pgbench -c 32 -j 8 -T 300 -R 500 -P 10 pgbench_test
```

Ở ví dụ này, pgbench cố gắng đưa vào khoảng 500 transaction mỗi giây. Nếu database không theo kịp, schedule lag và latency có thể tăng. Khi dùng rate limit, hãy đọc phần báo cáo latency/schedule delay theo tài liệu phiên bản; đừng chỉ nhìn completed TPS.

### 6.6. Đo thời gian từng lệnh và ghi log

```bash
pgbench -c 16 -j 4 -T 180 -r -l pgbench_test
```

- `-r`: báo cáo latency trung bình theo từng command trong script.
- `-l`: ghi log transaction để phân tích sau.

Log có thể lớn khi tải cao. Chỉ bật chi tiết cần thiết và lưu ở filesystem đủ dung lượng. Log transaction giúp phân tích phân bố thời gian nhưng cần ghép với metrics của DB để hiểu CPU, I/O, lock và checkpoint.

### 6.7. Đo chi phí tạo kết nối mới

Mặc định pgbench giữ kết nối client trong quá trình chạy. Tùy chọn `-C` yêu cầu tạo kết nối mới cho mỗi transaction:

```bash
pgbench -C -c 16 -j 4 -T 120 pgbench_test
```

So sánh chạy có và không có `-C` có thể giúp ước lượng ảnh hưởng của connection setup trong môi trường test. Tuy nhiên, đây không phải mô phỏng chính xác connection pool của ứng dụng; driver, TLS, authentication và pool lifecycle của application có thể khác. Đo riêng connection creation, pool acquisition và SQL execution nếu cần đánh giá ứng dụng.

### 6.8. Script SQL tùy chỉnh

Tạo file `lookup.sql`:

```sql
\set aid random(1, 5000000)
SELECT abalance
FROM pgbench_accounts
WHERE aid = :aid;
```

Chạy:

```bash
pgbench -f lookup.sql -c 32 -j 8 -T 300 -M prepared pgbench_test
```

`-f` chỉ định script. `-M prepared` dùng chế độ prepared query của pgbench theo khả năng phiên bản. Có thể thêm nhiều script với trọng số để mô phỏng mix, nhưng cần bảo đảm tỷ lệ và semantics tương ứng workload mục tiêu.

Với script tùy chỉnh, hãy kiểm tra transaction boundary, dữ liệu tham số, xác suất key, số hàng trả về và hành vi lỗi. Một script chỉ SELECT primary key không đại diện truy vấn join nhiều bảng hoặc transaction có nhiều lần cập nhật.

### 6.9. Diễn giải kết quả pgbench

Các dòng thường gặp gồm:

- `tps`: transaction per second, thường có báo cáo bao gồm hoặc loại trừ connection time tùy chế độ.
- `latency average`: thời gian trung bình của transaction.
- `initial connection time`: thông tin thời gian tạo kết nối ban đầu trong một số chế độ/báo cáo.
- `latency stddev`: độ lệch chuẩn latency.
- `number of failed transactions`: số transaction thất bại.
- `skipped`: transaction bị bỏ qua trong một số kịch bản rate scheduling/latency limit.

Tên trường và cách tính có thể thay đổi theo phiên bản và tùy chọn. Đọc phần mô tả trong output và tài liệu đúng phiên bản. Không coi TPS cao là thành công nếu failed transactions, skipped hoặc latency vượt SLO.

## 7. Dùng sysbench cho workload OLTP tổng hợp

`sysbench` là framework benchmark đa mục đích với các workload Lua. Nó thường được dùng để đo CPU, memory, file I/O và OLTP database. Với database, phải xác nhận driver được build hỗ trợ và cú pháp tương ứng phiên bản.

### 7.1. Xác minh driver

```bash
sysbench --version
sysbench --help
sysbench --db-driver=help
```

Không giả định mọi bản sysbench đều hỗ trợ mọi hệ quản trị. Các bản phổ biến thường dùng driver MySQL; driver khác có thể cần build hoặc plugin tương ứng. Nếu hệ quản trị không được hỗ trợ trực tiếp, chọn công cụ có binding phù hợp hoặc viết generator qua JDBC/driver chính thức.

### 7.2. Chuẩn bị kết nối MySQL-compatible

Ví dụ dùng workload OLTP của sysbench với MySQL:

```bash
sysbench oltp_read_write \
  --db-driver=mysql \
  --mysql-host=127.0.0.1 \
  --mysql-port=3306 \
  --mysql-user=bench_user \
  --mysql-db=bench_db \
  --tables=8 \
  --table-size=100000 \
  prepare
```

`prepare` tạo các bảng và dữ liệu cần cho workload. Cần tạo database thử nghiệm trước, cấp quyền tối thiểu cần thiết và dùng credential an toàn. Các tên option và yêu cầu của script cần xác nhận theo bản sysbench cài đặt.

### 7.3. Chạy workload read-write

```bash
sysbench oltp_read_write \
  --db-driver=mysql \
  --mysql-host=127.0.0.1 \
  --mysql-port=3306 \
  --mysql-user=bench_user \
  --mysql-db=bench_db \
  --tables=8 \
  --table-size=100000 \
  --threads=16 \
  --time=300 \
  --warmup-time=60 \
  --report-interval=10 \
  --percentile=95 \
  run
```

Các tham số chính:

- `--threads=16`: số worker thread tạo tải.
- `--time=300`: thời gian đo sau warm-up theo cách script/phiên bản xử lý.
- `--warmup-time=60`: thời gian warm-up.
- `--report-interval=10`: báo cáo tiến độ mỗi 10 giây.
- `--percentile=95`: percentile latency được báo cáo.
- `--tables` và `--table-size`: quy mô dataset.

Sysbench có thể báo events/s, transactions/s, latency trung bình, percentile, số lỗi và thống kê thread fairness. Hãy lưu output đầy đủ và so sánh cùng cấu hình, không chỉ chép một dòng transactions per second.

### 7.4. Chọn workload phù hợp

Các script OLTP thường gặp:

| Workload | Mục tiêu tổng quát |
|---|---|
| `oltp_read_only` | Transaction thiên về đọc |
| `oltp_read_write` | Hỗn hợp đọc và ghi |
| `oltp_write_only` | Transaction thiên về ghi |
| `oltp_point_select` | Tra cứu theo khóa |
| `oltp_update_index` | Cập nhật cột có index |
| `oltp_update_non_index` | Cập nhật cột không có index |
| `oltp_insert` | Thêm bản ghi |
| `oltp_delete` | Xóa bản ghi |

Danh sách script phụ thuộc bản sysbench và bộ script đi kèm. Kiểm tra các script có sẵn trên máy thay vì giả định mọi tên đều tồn tại.

### 7.5. Thay đổi phân bố truy cập

Sysbench hỗ trợ các kiểu phân bố ngẫu nhiên như uniform và một số kiểu skewed tùy script/version. Thay đổi phân bố có thể làm thay đổi cache locality, index page contention và hot-row contention. Hãy chạy ít nhất một phân bố gần dữ liệu thật nếu đã có thống kê về tần suất truy cập key.

### 7.6. Cleanup sau thử nghiệm

```bash
sysbench oltp_read_write \
  --db-driver=mysql \
  --mysql-host=127.0.0.1 \
  --mysql-port=3306 \
  --mysql-user=bench_user \
  --mysql-db=bench_db \
  --tables=8 \
  --table-size=100000 \
  cleanup
```

Chỉ chạy `cleanup` trong database benchmark được tạo riêng cho bài thử. Xác minh database/schema đích trước khi xóa dữ liệu benchmark.

## 8. Khi nào nên dùng HammerDB, YCSB hoặc generator riêng?

### 8.1. HammerDB

HammerDB cung cấp workload mô phỏng OLTP và data warehouse cho nhiều hệ quản trị. Các workload TPROC-C và TPROC-H được xây dựng theo kiểu workload chuẩn hóa để so sánh một số đặc điểm hệ thống. Tuy nhiên, chạy HammerDB không tự động tạo ra kết quả TPC-C/TPC-H chính thức được chứng nhận. Kết quả công bố theo chuẩn chính thức cần tuân thủ quy tắc benchmark, cấu hình và quy trình audit tương ứng.

Chọn HammerDB khi cần workload đa dạng hơn một script đơn giản hoặc cần so sánh hệ quản trị được hỗ trợ trong cùng kiểu bài thử. Vẫn phải điều chỉnh schema, scale, virtual users và think time theo mục tiêu.

### 8.2. YCSB

YCSB thường được dùng để so sánh hệ thống lưu trữ/NoSQL theo workload key-value, với tỷ lệ read/update/insert/scan và phân bố key có thể điều chỉnh. Nó hữu ích khi hệ thống cung cấp binding tương ứng và câu hỏi xoay quanh truy cập key-value.

YCSB không mặc nhiên đại diện cho workload SQL nhiều join, foreign key, transaction đa câu lệnh hoặc analytical query. Chọn binding và workload phù hợp với semantics của database.

### 8.3. Bộ phát tải JDBC hoặc generator riêng

Khi cần tái hiện đúng ứng dụng Java, có thể viết generator dùng JDBC và connection pool tương tự production. Generator nên có:

- Bộ dữ liệu tham số và phân bố truy cập có kiểm soát.
- Transaction mix và tần suất request rõ ràng.
- Số worker/concurrency hoặc rate scheduler.
- Đo pool acquisition, connection creation, statement execution và commit riêng.
- Histogram latency với p50/p95/p99.
- Đếm lỗi, timeout, retry và kết quả sai.
- Warm-up, ramp-up, measurement window và cooldown.
- Cấu hình có thể lưu và tái chạy.

Nếu dùng HTTP load generator như k6, Gatling hoặc JMeter để gọi API, hãy đo cả end-to-end latency và trace DB. Đừng dùng kết quả API để kết luận database throughput nếu chưa tách application CPU, cache, network và các service phụ thuộc.

## 9. Chọn mức concurrency và tìm điểm bão hòa

Không chỉ chạy một mức client. Hãy tăng tải theo bậc:

| Bước | Clients/threads minh họa | Câu hỏi |
|---|---:|---|
| 1 | 1–4 | Độ trễ cơ sở và chi phí một transaction là bao nhiêu? |
| 2 | 8 | Throughput tăng gần tuyến tính không? |
| 3 | 16 | CPU, I/O, lock và latency bắt đầu tăng ở đâu? |
| 4 | 32 | Throughput còn tăng hay đã đi ngang? |
| 5 | 64 | Queueing, p95/p99 và lỗi có tăng mạnh không? |
| 6 | 128 | Có còn giá trị đo sau saturation hay chỉ tạo quá tải? |

Các con số chỉ là ví dụ; chọn theo CPU, DB connection limit, workload và capacity thực tế. Dừng tăng khi hệ thống đã vượt SLO, lỗi tăng hoặc tài nguyên bị quá tải kéo dài.

### 9.1. Đường cong throughput và latency

Ở vùng tải thấp, tăng concurrency thường làm throughput tăng. Khi một resource bão hòa, throughput tăng chậm hoặc đi ngang; latency tăng do queueing. Nếu tiếp tục tăng tải, error/timeout có thể tăng và completed throughput thậm chí giảm.

<table>
  <thead>
    <tr><th>Vùng tải</th><th>Throughput</th><th>Latency</th><th>Diễn giải</th></tr>
  </thead>
  <tbody>
    <tr><td>Underloaded</td><td>Tăng theo tải</td><td>Thấp và ổn định</td><td>Còn capacity</td></tr>
    <tr><td>Near saturation</td><td>Tăng chậm</td><td>Bắt đầu tăng nhanh</td><td>Queueing/resource contention xuất hiện</td></tr>
    <tr><td>Saturated</td><td>Đi ngang</td><td>Cao, tail dài</td><td>Resource giới hạn throughput</td></tr>
    <tr><td>Overloaded</td><td>Đi ngang hoặc giảm</td><td>Rất cao, nhiều timeout</td><td>Backlog và lỗi làm giảm hiệu quả</td></tr>
  </tbody>
</table>

### 9.2. Pool size và database concurrency

Số client của pgbench/sysbench không nhất thiết bằng số session active tại DB trong mọi thời điểm. Hãy theo dõi actual connections, active sessions, waiting sessions và pool queue. Tăng client có thể làm tăng lock contention hoặc memory grants trước khi CPU đạt 100%.

## 10. Thu thập metrics ở database và hệ điều hành

Benchmark chỉ có TPS/latency sẽ không cho biết bottleneck. Thu thập các nhóm chỉ số cùng timestamp.

| Nhóm | Chỉ số |
|---|---|
| Workload | Offered rate, completed TPS/QPS, transaction mix, errors, timeouts |
| Latency | p50, p95, p99, max, schedule delay và pool wait nếu có |
| CPU | User/system CPU, run queue, DB worker utilization |
| Memory | RAM available, DB memory, buffer/cache usage, swap, memory grants |
| Storage | Read/write IOPS, throughput, latency, queue depth, temp spill |
| Database | Active sessions, connections, logical/physical reads, buffer hits, WAL/redo, checkpoint |
| Concurrency | Lock waits, deadlocks, latch/buffer waits, transaction age |
| Replication | Replica lag, commit wait/quorum nếu có |
| Network | RTT, bytes, retransmission, connection failures |

Lấy snapshot trước, trong và sau bài thử. Dùng delta counter trong measurement window; counter tích lũy từ khi DB khởi động không thể so sánh trực tiếp giữa hai lần chạy có thời gian khác nhau.

### 10.1. PostgreSQL metrics

Với PostgreSQL, có thể kết hợp:

- `pg_stat_database`: transaction, block hit/read và các thống kê theo database.
- `pg_stat_statements`: query calls, execution time, rows và block activity theo query fingerprint nếu extension được bật.
- `pg_stat_activity`: session, state, wait event và query đang chạy.
- `pg_locks`: lock đang được giữ hoặc chờ.
- `EXPLAIN (ANALYZE, BUFFERS)`: actual plan, rows và buffer activity cho truy vấn được chọn.
- OS tools: CPU, memory, swap và storage I/O.

`EXPLAIN ANALYZE` thực thi câu SQL. Với DML, nó có thể thay đổi dữ liệu; chỉ chạy trên dữ liệu test hoặc dùng transaction/rollback khi phù hợp và hiểu các side effect. Không chạy query benchmark nặng tùy tiện trên production.

### 10.2. MySQL/InnoDB metrics

Với MySQL/InnoDB, có thể kết hợp:

- Performance Schema và `sys` schema để xem statement digest, waits và I/O.
- `SHOW GLOBAL STATUS` để lấy counter như query, transaction, buffer pool và connection.
- `SHOW ENGINE INNODB STATUS` để xem lock, transaction, buffer pool và I/O.
- Slow query log hoặc statement instrumentation theo cấu hình.
- OS metrics cho CPU, memory, disk và network.

Counter cần lấy delta và diễn giải theo đúng phiên bản. Không chỉ dựa vào một buffer pool hit ratio để kết luận storage không phải bottleneck.

### 10.3. Metrics ở hệ quản trị khác

SQL Server có thể dùng Query Store, DMVs, wait statistics và actual execution plan; Oracle có thể dùng AWR/ASH khi license/quyền cho phép, dynamic performance views và SQL Monitor theo môi trường. Chọn công cụ quan sát phù hợp phiên bản và chính sách license. Query history hoặc plan cache không thay thế runtime metrics trong measurement window.

## 11. Đọc output và tính toán các chỉ số

### 11.1. TPS và QPS

- **TPS:** số transaction hoàn tất mỗi giây.
- **QPS:** số câu truy vấn/statement hoàn tất mỗi giây.

Một transaction có thể chứa nhiều statement. Không so TPS của một công cụ với QPS của công cụ khác nếu không quy đổi workload.

### 11.2. Latency percentiles

- p50: một nửa request hoàn thành trong thời gian này hoặc nhanh hơn.
- p95: 95% request hoàn thành trong thời gian này hoặc nhanh hơn.
- p99: 99% request hoàn thành trong thời gian này hoặc nhanh hơn.

Average latency có thể thấp dù một nhóm request rất chậm. Với hệ thống có SLO, p95/p99 thường quan trọng hơn average. Ghi rõ percentile được tính trên transaction thành công hay cả lỗi/timeout, vì hai cách có thể cho kết quả khác nhau.

### 11.3. Throughput hiệu dụng

Nếu generator gửi 1.000 transaction/giây nhưng chỉ 850 hoàn tất thành công, 100 timeout và 50 lỗi, không thể báo cáo “1.000 TPS” như năng lực phục vụ thành công. Báo cáo cả offered rate, completed successful TPS và error/timeout rate.

### 11.4. Resource efficiency

Có thể xem throughput trên mỗi core, mỗi GB RAM hoặc mỗi đơn vị chi phí cloud để so sánh hiệu quả, nhưng phải giữ cùng workload, latency target và correctness. Một cấu hình đạt TPS cao hơn bằng cách dùng gấp đôi CPU không nhất thiết hiệu quả hơn.

## 12. Các yếu tố làm benchmark sai lệch

- Dataset quá nhỏ, vừa cache hoàn toàn trong RAM.
- Dataset hoặc index không tương tự production.
- Statistics chưa được cập nhật sau nạp dữ liệu.
- Warm-up không đủ hoặc cache state khác nhau giữa các lần chạy.
- Background vacuum, checkpoint, backup hoặc compaction chạy ở một lần nhưng không chạy ở lần khác.
- Generator chạy trên cùng máy DB và tranh CPU/network.
- Số client quá ít hoặc quá nhiều so với câu hỏi.
- Offered rate không được duy trì do generator bị giới hạn.
- Connection reuse khác với production.
- Query mix, tham số và key distribution không đại diện.
- Một lần chạy duy nhất hoặc thời gian đo quá ngắn.
- Không đếm lỗi, timeout, retry hoặc transaction bị bỏ.
- So sánh hai phiên bản khác nhau về schema, index, data volume hoặc hardware.
- Chỉ nhìn TPS, bỏ qua p95/p99, lock, I/O và correctness.

### 12.1. Generator cũng có thể là bottleneck

Load generator có thể hết CPU, socket, ephemeral ports, file descriptors hoặc network bandwidth trước DB. Khi đó offered rate thực tế thấp hơn cấu hình và database có vẻ nhàn rỗi. Đặt generator trên máy riêng nếu có thể, theo dõi CPU/network của generator và xác nhận số request thật sự được phát.

### 12.2. Clock và đồng bộ thời gian

Khi thu thập metrics từ nhiều máy, đồng bộ clock bằng NTP/PTP hoặc dùng timestamp/monotonic clock phù hợp. Clock lệch có thể làm timeline sai và khiến latency tính từ hai máy không đáng tin. Với thời gian đo trong một process, ưu tiên monotonic clock thay vì wall clock có thể bị điều chỉnh.

## 13. Quy trình benchmark một thay đổi index hoặc cấu hình

Ví dụ cần kiểm tra index mới có cải thiện truy vấn tra cứu đơn hàng không:

1. Ghi lại schema, row count, index hiện tại và statistics.
2. Lưu query, tham số đại diện và execution plan baseline.
3. Chạy workload có cùng transaction mix, concurrency và thời lượng.
4. Ghi TPS, p95/p99, logical/physical reads, CPU, I/O và lock waits.
5. Tạo index trong môi trường benchmark theo kế hoạch thử nghiệm.
6. Cập nhật statistics nếu hệ quản trị yêu cầu hoặc quy trình test cần.
7. Chạy lại cùng workload và cùng điều kiện warm-up.
8. So sánh plan, rows estimate/actual, reads, latency và write overhead.
9. Kiểm tra workload ghi: index mới có làm INSERT/UPDATE/DELETE chậm hơn không?
10. Lặp lại và ghi kết quả, bao gồm tác động phụ.

Không chỉ chạy riêng query mục tiêu nếu index mới ảnh hưởng toàn workload. Index có thể giảm read latency nhưng tăng write amplification, storage và maintenance.

## 14. Kịch bản kiểm thử theo mục tiêu

| Mục tiêu | Công cụ/kịch bản gợi ý | Chỉ số chính |
|---|---|---|
| PostgreSQL OLTP cơ bản | pgbench mặc định, read-only và custom script | TPS, latency, failures, CPU, WAL, locks |
| PostgreSQL query cụ thể | pgbench custom script hoặc generator SQL | Plan, buffers, rows, p95/p99, query mix |
| MySQL OLTP | sysbench `oltp_read_write`, `oltp_read_only` | transactions/s, latency, InnoDB waits, buffer pool, redo |
| SQL Server/Oracle đa transaction | HammerDB hoặc workload riêng | Transaction rate, latency, waits, CPU, I/O |
| Key-value/NoSQL | YCSB binding phù hợp | Throughput, latency, read/update mix, key skew |
| Java service qua pool | JDBC generator hoặc API load test | Pool wait, connection creation, SQL time, end-to-end p95/p99 |
| Analytics/warehouse | HammerDB TPROC-H, query suite hoặc workload thật | Bytes scanned, stage time, spill, concurrency, queue |

## 15. Ví dụ báo cáo benchmark

Một báo cáo có thể dùng cấu trúc sau:

```text
Benchmark: PostgreSQL OLTP read-write
Environment: 8 vCPU, 32 GB RAM, SSD, same-region client
Database version: recorded version
Dataset: scale factor 50, indexes and statistics recorded
Tool: pgbench version recorded
Workload: default read-write, 16 clients, 4 threads
Warm-up: 60 seconds
Measurement: 300 seconds
Runs: 3

Run 1: successful TPS, p50, p95, p99, errors
Run 2: successful TPS, p50, p95, p99, errors
Run 3: successful TPS, p50, p95, p99, errors

DB metrics: CPU, buffer reads/hits, WAL, checkpoints, locks
OS metrics: CPU, memory, swap, disk latency, IOPS
Conclusion: bottleneck hypothesis and evidence
Trade-offs: write cost, storage, correctness, operational impact
```

Không điền số liệu giả định vào báo cáo như thể đã đo. Nếu dùng ví dụ minh họa, ghi rõ là số liệu giả định. Lưu command line, config, script, tool version và raw output để người khác có thể lặp lại.

## 16. An toàn và tính đúng đắn khi chạy benchmark

Benchmark tạo tải có chủ đích và có thể làm cạn connection, CPU, I/O hoặc storage. Dùng database riêng, dữ liệu test và tài khoản có quyền tối thiểu. Nếu phải kiểm tra trên hệ thống dùng chung, cần giới hạn tải, cửa sổ chạy và điều kiện dừng theo quy trình vận hành đã thống nhất.

Các điểm cần kiểm tra:

- Không chạy `prepare`, `cleanup` hoặc khởi tạo schema trên database production.
- Không dùng dữ liệu cá nhân/nhạy cảm trong script hoặc output không được bảo vệ.
- Không lưu password trong shell history, repository hoặc báo cáo.
- Không để benchmark ghi dữ liệu vô hạn hoặc làm đầy storage/log.
- Đặt giới hạn concurrency, duration, rate và timeout.
- Có tiêu chí dừng nếu error rate, latency hoặc resource vượt ngưỡng.
- Xác nhận dữ liệu đúng sau workload ghi, kể cả duplicate, lost update và constraint.
- Dọn dữ liệu test đúng database/schema sau khi hoàn tất.

## 17. Những sai lầm thường gặp

- **Chọn công cụ theo độ phổ biến:** công cụ không hỗ trợ đúng driver hoặc workload cần đo.
- **Dùng workload mặc định làm đại diện production:** transaction mix, dữ liệu và hot keys có thể khác.
- **So sánh TPS khác semantics:** một công cụ tính transaction, công cụ khác tính statement hoặc event.
- **Chỉ tăng client để tìm TPS cao nhất:** bỏ qua p95/p99 và saturation.
- **Không phân biệt closed-loop và open-loop:** không biết offered load có được duy trì không.
- **Bỏ qua coordinated omission:** percentile có thể đánh giá thấp tail latency.
- **Không warm-up hoặc warm-up khác nhau:** cache state làm kết quả không so sánh được.
- **Đặt generator cạnh DB mà không theo dõi tài nguyên generator:** load generator có thể giới hạn kết quả.
- **Chỉ đo query latency:** bỏ qua pool wait, connection setup và application overhead.
- **Không thu thập metrics DB/OS:** không xác định được bottleneck.
- **Không lặp lại:** kết luận dựa trên một lần chạy có thể bị nhiễu.
- **Không đếm errors/timeouts:** TPS cao có thể đi kèm nhiều request thất bại.
- **Không kiểm tra correctness:** benchmark nhanh nhưng cập nhật sai vẫn là kết quả thất bại.
- **Gọi kết quả HammerDB là chứng nhận TPC:** workload tương tự không đồng nghĩa benchmark chính thức được chứng nhận.

## 18. Bài tập tự kiểm tra

### Bài tập 1: Chọn công cụ

Một nhóm cần đo PostgreSQL với transaction mix gồm đọc tài khoản, cập nhật số dư và ghi lịch sử; sau đó muốn thay đổi tham số phân bố tài khoản nóng.

**Câu hỏi:** nên bắt đầu với công cụ nào và khi nào cần generator riêng?

**Gợi ý trả lời:** có thể bắt đầu với pgbench để có baseline và custom SQL script. Nếu cần mô phỏng chính xác business rules, key distribution, retry hoặc connection pool của ứng dụng, nên xây dựng workload riêng hoặc dùng bộ phát tải ứng dụng.

### Bài tập 2: Diễn giải TPS và latency

Một lần chạy có offered rate 1.000 transaction/s, completed throughput 780 TPS, p99 tăng lên 2 giây và timeout 8%.

**Câu hỏi:** có thể kết luận database xử lý 1.000 TPS không?

**Gợi ý trả lời:** không. 1.000 là offered rate; chỉ 780 transaction/s hoàn tất. Cần báo cáo timeout/error và p99. Hệ thống có thể đã bão hòa hoặc generator/queue không đáp ứng tải.

### Bài tập 3: Chọn dataset

Benchmark dùng 100.000 hàng nhưng production có 200 triệu hàng và working set lớn hơn RAM.

**Câu hỏi:** kết quả có thể sai lệch thế nào?

**Gợi ý trả lời:** dataset nhỏ có thể vừa cache, index nông và ít skew/partition. Benchmark có thể đánh giá quá cao cache hit và throughput, đồng thời bỏ qua I/O và data distribution của production. Cần scale dữ liệu và working set gần mục tiêu.

### Bài tập 4: Closed-loop che giấu tải

Generator có 20 client. Khi DB chậm, mỗi client chờ transaction trước hoàn tất rồi mới gửi tiếp. TPS giảm nhưng offered rate không được ghi.

**Câu hỏi:** điều gì khó quan sát và cần làm gì?

**Gợi ý trả lời:** generator tự giảm tốc độ khi DB chậm nên không biết nhu cầu đầu vào cố định sẽ tạo backlog/latency ra sao. Dùng rate-controlled/open-loop test khi cần, ghi offered rate, completed throughput, schedule delay và error rate.

### Bài tập 5: sysbench driver

Một máy cài sysbench nhưng `--db-driver=pgsql` báo không hỗ trợ.

**Câu hỏi:** có nên tự giả định cú pháp MySQL sẽ chạy với PostgreSQL không?

**Gợi ý trả lời:** không. Cần xác nhận driver được build hỗ trợ. Dùng pgbench cho PostgreSQL hoặc chọn driver/bộ phát tải có hỗ trợ tương ứng; nếu cần mô phỏng JDBC, dùng generator qua driver chính thức.

### Bài tập 6: Generator bottleneck

Database CPU chỉ 30%, throughput không tăng dù tăng số client. Máy phát tải CPU 100% và network gần bão hòa.

**Câu hỏi:** có thể kết luận database còn capacity không?

**Gợi ý trả lời:** chưa. Load generator có thể là bottleneck nên offered load không đến được DB. Chuyển generator sang máy riêng hoặc tăng năng lực phát tải, xác nhận số request thực tế và theo dõi network trước khi kết luận.

### Checklist chọn công cụ và chạy benchmark

- [ ] Đã xác định câu hỏi và metric mục tiêu.
- [ ] Đã chọn công cụ có driver/binding hỗ trợ hệ quản trị và workload.
- [ ] Đã phân biệt database-level benchmark với application-level benchmark.
- [ ] Đã mô tả transaction mix, tham số, hot keys và data distribution.
- [ ] Đã chọn dataset/working set phù hợp và ghi rõ kích thước data/index.
- [ ] Đã xác định closed-loop hay open-loop và offered rate.
- [ ] Đã có warm-up, ramp-up, measurement window và số lần lặp.
- [ ] Đã ghi tool version, DB version, command, config và script.
- [ ] Đã thu thập TPS/QPS, p50/p95/p99, errors và timeouts.
- [ ] Đã theo dõi CPU, memory, I/O, network, locks, WAL/redo và connection.
- [ ] Đã xác nhận load generator không phải bottleneck.
- [ ] Đã kiểm tra correctness của dữ liệu sau workload ghi.
- [ ] Đã so sánh trong cùng điều kiện và chỉ thay một yếu tố chính.
- [ ] Đã lưu raw output và ghi nhận trade-off cùng giới hạn của kết quả.

`pgbench`, `sysbench` và các bộ phát tải khác chỉ tạo ra phép đo hữu ích khi workload, dữ liệu và cách điều khiển tải phù hợp với câu hỏi. Hãy bắt đầu từ mục tiêu, chọn công cụ đúng hệ quản trị, mô tả transaction mix và data distribution, kiểm soát concurrency/offered rate, warm-up và measurement window, rồi thu thập cả latency percentiles, throughput, lỗi và tài nguyên ở DB lẫn hệ điều hành. Kết quả chỉ đáng tin khi có thể lặp lại, kiểm tra tính đúng đắn và giải thích được bottleneck cũng như giới hạn của phép thử.
