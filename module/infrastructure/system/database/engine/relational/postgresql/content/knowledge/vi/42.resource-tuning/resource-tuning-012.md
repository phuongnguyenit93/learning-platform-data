# Benchmark bằng pgbench, kịch bản thực tế và kiểm soát sai lệch

`pgbench` là công cụ benchmark đi kèm PostgreSQL. Nó mô phỏng nhiều client database chạy lặp lại một hoặc nhiều transaction scripts, sau đó báo throughput (transactions per second — TPS), latency, số transaction lỗi và các thống kê liên quan. Công cụ có sẵn workload TPC-B-like để tạo baseline nhanh, đồng thời cho phép viết script riêng để mô phỏng hành vi ứng dụng.

Một con số TPS cao không tự động chứng minh database tốt hơn. Kết quả chỉ có ý nghĩa khi workload đại diện cho hệ thống thật, dataset có quy mô phù hợp, concurrency được chọn có chủ đích, trạng thái cache và vacuum được kiểm soát, máy phát tải không trở thành bottleneck, và các lần chạy có thể so sánh công bằng.

```text
  Ứng dụng / workload thực tế
              |
              v
  +--------------------------+
  | pgbench clients          |
  | scripts, rate, concurrency|
  +------------+-------------+
               |
               v
  +--------------------------+
  | PostgreSQL server        |
  | CPU / memory / locks     |
  | buffers / WAL / storage  |
  +------------+-------------+
               |
       +-------+--------+
       |                |
       v                v
  pgbench results   server/OS metrics
       |                |
       +-------+--------+
               |
               v
  Compare repeated runs and explain variance
```

Bài thuộc chương **Tối ưu tài nguyên** của module *Database Engine Relational PostgreSQL*. Nội dung tập trung vào cách thiết kế một thí nghiệm benchmark có thể giải thích và tái lập: bắt đầu bằng baseline, tạo workload sát nghiệp vụ, tăng tải theo bậc, đo latency cùng throughput, kiểm soát cache/data drift và đối chiếu metrics phía server.

Sau bài học, bạn có thể:

1. Phân biệt baseline pgbench với benchmark mô phỏng ứng dụng thật.
2. Khởi tạo dataset và chọn scale factor hợp lý.
3. Viết custom transaction scripts với phân phối truy cập phù hợp.
4. Chọn số clients, threads, duration, protocol và target rate.
5. Đọc TPS, latency, standard deviation, failures, retries và schedule lag.
6. Thu thập transaction logs, per-command metrics và server-side telemetry.
7. Kiểm soát cache state, autovacuum, dead tuples, checkpoint và data growth.
8. Lặp lại thí nghiệm, ghi nhận biến động và tránh chọn kết quả tốt nhất.
9. Phát hiện khi pgbench client hoặc network trở thành giới hạn.
10. So sánh hai cấu hình bằng cùng một workload và điều kiện thử nghiệm.

> **Phạm vi an toàn:** Chạy benchmark ghi dữ liệu trên database lab hoặc môi trường staging được phép. `pgbench -i` xóa và tạo lại các bảng có tên `pgbench_*`; không chạy trên database có dữ liệu thật trùng tên. Workload tải cao có thể làm tăng CPU, I/O, WAL, replication lag và latency của các dịch vụ dùng chung.

---

## 1. Benchmark là một thí nghiệm có kiểm soát

### 1.1. Benchmark đo điều gì?

Benchmark tạo tải có chủ đích để đo cách hệ thống phản ứng. Với PostgreSQL, ta thường quan tâm:

- **Throughput:** số transaction hoàn thành mỗi giây.
- **Latency:** thời gian client chờ một transaction hoàn tất.
- **Concurrency:** số session/client đồng thời.
- **Failure rate:** tỷ lệ transaction lỗi, deadlock hoặc serialization failure.
- **Resource usage:** CPU, memory, storage I/O, network, WAL và locks.
- **Scalability:** throughput và latency thay đổi ra sao khi tăng số clients hoặc lượng dữ liệu.

Không có một chỉ số đơn lẻ mô tả toàn bộ hiệu năng. TPS cao nhưng p99 latency rất lớn có thể không phù hợp với ứng dụng tương tác; latency thấp ở một client cũng không chứng minh hệ thống chịu được hàng trăm sessions.

### 1.2. Câu hỏi phải xác định trước

Trước khi chạy pgbench, hãy viết rõ câu hỏi benchmark:

- Máy chủ mới có tăng TPS so với máy cũ không?
- Index mới có giảm latency của truy vấn đọc không?
- `work_mem` mới có giảm temporary I/O trong workload báo cáo không?
- Storage mới có cải thiện throughput khi dữ liệu lớn hơn RAM không?
- Connection pooling có giảm overhead khi tạo kết nối liên tục không?
- Cấu hình có giữ p95/p99 trong ngưỡng khi có 100 clients không?

Mỗi thí nghiệm nên thay đổi một yếu tố chính. Nếu cùng lúc đổi CPU, storage, PostgreSQL version, schema, index và script, kết quả không chỉ ra được nguyên nhân.

### 1.3. Workload quyết định kết quả

Một database có thể chạy tốt với SELECT point lookup nhưng chậm với nhiều UPDATE cùng khóa. Nó cũng có thể nhanh với dữ liệu nằm trong RAM nhưng chậm khi working set vượt memory.

Vì vậy, workload phải mô tả được:

- Tỷ lệ đọc/ghi.
- Kích thước transaction và số SQL statements mỗi transaction.
- Phân phối khóa truy cập: đều hay tập trung vào một số bản ghi.
- Kích thước dữ liệu và working set.
- Mức độ đồng thời.
- Tỷ lệ kết nối mới so với kết nối được tái sử dụng.
- Mức độ yêu cầu nhất quán/locking.
- Các thao tác nền như vacuum, checkpoint và replication.

### 1.4. Benchmark không phải production traffic replay

pgbench là công cụ tạo tải theo script. Nó không tự động tái hiện đầy đủ hành vi của ứng dụng như connection pool, cache tầng application, ORM, network hops, payload serialization, retry policy hoặc thời gian người dùng suy nghĩ.

Nếu cần mô phỏng gần production hơn, xây dựng transaction scripts từ các luồng nghiệp vụ quan trọng và bổ sung công cụ load test ở tầng ứng dụng khi cần đo end-to-end.

### 1.5. Benchmark đúng mục tiêu

| Mục tiêu | Workload phù hợp |
|---|---|
| Throughput OLTP | Transaction ngắn, hỗn hợp SELECT/INSERT/UPDATE |
| Read-heavy | Point lookup, range scan, list/search, join |
| Write-heavy | INSERT/UPDATE theo phân phối khóa thực tế |
| Hot-row contention | Nhiều clients cập nhật cùng một số khóa |
| Reporting | Aggregate, sort, join và scan dữ liệu lớn |
| Connection overhead | Kết nối mới mỗi transaction hoặc chạy qua pool |
| I/O capacity | Dataset/working set lớn hơn cache, access pattern đại diện |

---

## 2. Hiểu đúng workload mặc định của pgbench

### 2.1. TPC-B-like built-in script

Lệnh mặc định của pgbench chạy một transaction kiểu TPC-B-like. Nó gồm các thao tác:

1. Cập nhật số dư một account.
2. Đọc lại số dư account.
3. Cập nhật teller balance.
4. Cập nhật branch balance.
5. Thêm một dòng vào history.

Đây là workload hỗn hợp đọc/ghi, có transaction và có tranh chấp trên một số bảng. Nó được mô tả là **TPC-B-like**, không phải benchmark TPC-B chính thức và không phải kết quả chứng nhận TPC.

### 2.2. Các bảng pgbench tạo ra

`pgbench -i` tạo bốn bảng:

| Bảng | Vai trò |
|---|---|
| `pgbench_accounts` | Account rows, bảng lớn nhất |
| `pgbench_branches` | Branch balance |
| `pgbench_tellers` | Teller balance |
| `pgbench_history` | Lịch sử transaction, tăng dần khi chạy |

Ở scale factor 1, `pgbench_accounts` có 100.000 rows, `pgbench_branches` có 1 row và `pgbench_tellers` có 10 rows. Scale factor tăng số rows theo tỷ lệ.

### 2.3. Khởi tạo dữ liệu

Trước hết tạo một database benchmark riêng. Sau đó chạy:

```bash
createdb benchdb
pgbench -i -s 10 -h db-host -p 5432 -U bench_user benchdb
```

`-i` bật initialization mode; `-s 10` tạo dataset scale 10. Chọn scale factor theo RAM, storage và số clients dự kiến. Lệnh initialization có thể xóa các bảng pgbench cùng tên trước khi tạo lại.

### 2.4. Cảnh báo destructive của -i

Không chạy `pgbench -i` trong database ứng dụng nếu database đó đã có bảng `pgbench_accounts`, `pgbench_branches`, `pgbench_history` hoặc `pgbench_tellers` cần giữ. Tạo database benchmark riêng là lựa chọn an toàn và dễ lặp lại hơn.

### 2.5. Scale factor và hot branch contention

Trong workload mặc định, mỗi transaction cập nhật một branch row và một teller row. Số branch rows chỉ bằng scale factor. Nếu `-c` lớn hơn nhiều so với `-s`, nhiều clients tranh chấp trên cùng một số rows; benchmark có thể chủ yếu đo lock contention.

Với built-in TPC-B-like, tài liệu PostgreSQL khuyến nghị scale factor ít nhất bằng số clients lớn nhất dự định thử. Đây là hướng dẫn tránh contention do dataset quá nhỏ, không phải quy tắc chọn scale cho mọi custom workload.

### 2.6. Các built-in scripts

pgbench cung cấp:

- `tpcb-like`: workload mặc định, có SELECT/UPDATE/INSERT.
- `simple-update`: bỏ hai thao tác update teller/branch, giảm contention trên hai bảng đó.
- `select-only`: chỉ chạy SELECT account.

Ví dụ:

```bash
pgbench -b tpcb-like -c 16 -j 4 -T 180 benchdb
pgbench -b simple-update -c 16 -j 4 -T 180 benchdb
pgbench -b select-only -c 16 -j 4 -T 180 benchdb
```

`-N` tương đương simple-update; `-S` tương đương select-only.

### 2.7. Vì sao built-in không đủ cho mọi hệ thống?

Workload mặc định không có business schema, join pattern, JSON processing, search, tenant skew, transaction boundaries hay tỷ lệ nghiệp vụ của ứng dụng. Nó hữu ích để:

- Kiểm tra baseline PostgreSQL và hạ tầng.
- So sánh nhanh hai máy chủ trong cùng điều kiện.
- Quan sát tác động của concurrency và storage.
- Phát hiện giới hạn tổng quát của server.

Không dùng một kết quả built-in để dự đoán trực tiếp số request/second mà ứng dụng thực tế có thể phục vụ.

---

## 3. Chuẩn bị môi trường benchmark

### 3.1. Tách database benchmark

Dùng database lab/staging riêng để:

- Tránh ghi đè bảng ứng dụng.
- Chủ động tạo và reset dataset.
- Cho phép chạy initialization/vacuum.
- Dễ ghi lại trạng thái dữ liệu giữa các lần thử.
- Giảm rủi ro ảnh hưởng người dùng thật.

### 3.2. Kiểm tra phiên bản pgbench và server

Trên máy chạy client:

```bash
pgbench --version
psql --version
```

Kết nối server:

```sql
SELECT version();
SHOW server_version;
SHOW block_size;
```

Ghi riêng phiên bản client utility và server. Không giả định chỉ cần cùng major version; các tùy chọn pgbench mới có thể không tồn tại trong binary client cũ.

### 3.3. Xác nhận kết nối

```bash
pgbench -h db-host -p 5432 -U bench_user -d benchdb --client=1 --time=10
```

Chạy thử ngắn để xác nhận DNS, port, authentication, quyền và đường dẫn network. Đây là smoke test, không phải số liệu hiệu năng.

### 3.4. Quyền và schema an toàn

Role benchmark cần quyền trên các bảng và sequences của dataset thử nghiệm. Dùng role riêng, giới hạn quyền vào database/schema lab.

pgbench dùng tên bảng không schema-qualified trong built-in scripts và không tự thay đổi `search_path`. Không chạy pgbench trong database có schema usage không an toàn cho người dùng không tin cậy. Với custom scripts, nên schema-qualify tên bảng để giảm phụ thuộc vào `search_path`.

### 3.5. Chạy pgbench ở đâu?

Nếu chạy pgbench ngay trên database server, client process cạnh tranh CPU, memory và network với PostgreSQL. Khi test nhiều clients, pgbench có thể trở thành bottleneck và làm kết quả thấp hơn năng lực server.

Đối với phép đo server throughput:

- Chạy pgbench trên host riêng trong cùng vùng mạng/VPC hoặc LAN có latency thấp.
- Theo dõi CPU và network của máy client.
- Đảm bảo client có đủ CPU/thread để phát tải.
- Nếu cần, dùng nhiều máy phát tải và tổng hợp kết quả.

Nếu mục tiêu là đo end-to-end từ laptop/địa điểm người dùng, giữ network path đó và ghi rõ RTT; kết quả khi ấy bao gồm latency mạng.

### 3.6. Ghi lại cấu hình trước khi chạy

Thu thập:

- CPU model, số cores/vCPU và memory.
- Storage type, IOPS/throughput/latency và filesystem.
- OS/kernel, container/cgroup limits.
- PostgreSQL version/build và extension.
- Các tham số memory, WAL, checkpoint, autovacuum, parallelism.
- Dataset size, row counts, indexes và statistics.
- pgbench version, command line, script files và random seed.
- Vị trí máy client và network path.

Không so sánh hai kết quả nếu một bên chạy trên storage/network khác mà không ghi nhận.

---

## 4. Các tùy chọn pgbench quan trọng

### 4.1. Số clients và threads

| Tùy chọn | Ý nghĩa |
|---|---|
| `-c N` | Số client sessions đồng thời |
| `-j N` | Số worker threads của pgbench |

Ví dụ `-c 64 -j 8` tạo 64 client sessions do 8 pgbench threads điều phối. `-j` không phải số PostgreSQL parallel workers; nó điều khiển thread phía công cụ benchmark.

### 4.2. Duration hoặc số transaction

| Tùy chọn | Ý nghĩa |
|---|---|
| `-T 180` | Chạy trong 180 giây |
| `-t 1000` | Mỗi client chạy 1000 transactions |

`-T` và `-t` loại trừ lẫn nhau. Với benchmark so sánh tải ổn định, dùng `-T` giúp mỗi cấu hình chạy trong cùng khoảng thời gian.

### 4.3. Progress

`-P 10` in báo cáo tiến độ mỗi 10 giây, gồm TPS và latency trung bình/độ lệch chuẩn trong interval gần nhất. Progress hữu ích để thấy throughput/latency thay đổi theo thời gian, chẳng hạn sau khi cache nóng hoặc khi autovacuum bắt đầu.

### 4.4. Protocol mode

```bash
pgbench -M simple -c 16 -T 120 benchdb
pgbench -M extended -c 16 -T 120 benchdb
pgbench -M prepared -c 16 -T 120 benchdb
```

Các mode:

- `simple`: simple query protocol.
- `extended`: extended query protocol.
- `prepared`: extended protocol với prepared statements.

Prepared mode có thể nhanh hơn vì tái sử dụng parse analysis result sau lần đầu. Chọn mode gần với driver/application thực tế. Không so sánh hai cấu hình nếu một bên dùng simple còn bên kia dùng prepared mà không chủ ý đo khác biệt protocol.

### 4.5. Kết nối mới cho mỗi transaction

`-C` mở connection mới cho mỗi transaction thay vì giữ một connection cho mỗi client session:

```bash
pgbench -C -c 32 -j 4 -T 120 benchdb
```

Điều này hữu ích khi đo connection/authentication overhead. Nếu ứng dụng dùng connection pool và tái sử dụng connection, không dùng `-C` làm workload duy nhất.

### 4.6. Rate control

`-R rate` yêu cầu pgbench khởi chạy transaction theo target transactions/second:

```bash
pgbench -R 500 -c 64 -j 8 -T 180 benchdb
```

Không có `-R`, clients chạy transaction tiếp theo ngay khi transaction trước hoàn tất; đây là closed-loop load. Có `-R`, pgbench tạo lịch bắt đầu transaction theo phân phối Poisson để kiểm soát offered load.

### 4.7. Latency limit

`-L milliseconds` đánh dấu transactions vượt ngưỡng latency là late. Khi kết hợp `-R`, các transactions đã trễ quá ngưỡng ngay trước lúc được gửi có thể bị skipped và không chạy trên server.

Không dùng `-L` để làm đẹp số liệu. Luôn báo số late/skipped cùng TPS và latency để người đọc hiểu lượng tải thực sự đã được xử lý.

### 4.8. Logging

- `-l`: ghi thông tin từng transaction.
- `--aggregate-interval=seconds`: ghi thống kê gộp theo interval khi dùng `-l`.
- `--sampling-rate=0.05`: chỉ log một phần mẫu transaction.
- `-r`: báo latency trung bình theo từng command/statement sau benchmark.

Logging có thể tạo overhead và disk I/O. Đo một lượt có logging và một lượt không logging để biết mức ảnh hưởng; dùng sampling khi log transaction quá lớn.

### 4.9. Retry và failures

Mặc định `--max-tries=1`, tức serialization/deadlock errors không được retry. Có thể cấu hình số lần retry, nhưng phải báo số transactions retried, số retries và failures. Latency của transaction thành công có retry bao gồm thời gian của các lần thử trước đó.

Không tăng retries chỉ để benchmark báo ít failures hơn; cần phản ánh retry policy thực tế của ứng dụng.

---

## 5. Đọc kết quả pgbench

### 5.1. Output cơ bản

Một lần chạy thường hiển thị:

- Transaction type/script.
- Scale factor.
- Query protocol mode.
- Number of clients và threads.
- Số transaction dự kiến và thực tế.
- Số transaction failed.
- Latency average và standard deviation.
- Initial connection time.
- TPS.

Ghi lại toàn bộ output cùng command line; không chỉ chép con số TPS cuối.

### 5.2. Transactions per second

TPS là throughput mà pgbench quan sát được trong lần chạy. Với workload hỗn hợp, một transaction có thể gồm nhiều SQL statements; TPS không đồng nghĩa số SQL statements/second hay HTTP requests/second.

Khi so sánh hai kết quả, bảo đảm transaction script và transaction boundaries giống nhau. Nếu một script có 2 statements còn script kia có 12 statements, TPS không thể so sánh trực tiếp như cùng đơn vị công việc.

### 5.3. Latency average

Latency average là thời gian trung bình của transaction từ góc nhìn client. Nó bao gồm network round trips và thời gian chờ theo cách benchmark được cấu hình. Với rate limiting, latency được tính từ scheduled start time nên bao gồm schedule lag.

### 5.4. Standard deviation

Độ lệch chuẩn cho thấy mức biến động latency. Mean thấp nhưng standard deviation lớn có thể phản ánh workload không ổn định, outliers, lock contention, background I/O hoặc cache effects.

### 5.5. p95 và p99

Output tổng hợp thông thường của pgbench chủ yếu báo average và standard deviation; không nên suy ra p95/p99 từ hai giá trị này.

Để phân tích tail latency:

- Ghi transaction logs bằng `-l`.
- Chọn sampling rate phù hợp nếu log lớn.
- Phân tích trường transaction time từ log bằng công cụ ngoài.
- Hoặc dùng `--aggregate-interval` để xem latency biến động theo từng khoảng thời gian, lưu ý aggregate log không giữ phân phối từng transaction.

Khi báo p95/p99, nêu cách tính, số samples và cách xử lý failed/skipped transactions.

### 5.6. Initial connection time

Initial connection time là thời gian tạo các kết nối client ban đầu. Nếu mỗi client giữ kết nối trong suốt test, chi phí này thường được tách khỏi TPS cuối. Nếu mục tiêu là connection churn, dùng `-C` và phân tích riêng.

### 5.7. Failures và retries

Luôn kiểm tra:

- Số transactions thực tế.
- Failed transactions và failure percentage.
- Serialization failures.
- Deadlocks.
- Retries và số lần retry.
- Skipped transactions khi dùng rate/latency limit.

TPS cao nhưng nhiều transaction thất bại không phải benchmark thành công.

### 5.8. Per-command latency

`-r` báo latency trung bình theo từng statement/command. Nó giúp nhận ra câu UPDATE hoặc SELECT nào chiếm nhiều thời gian trong script.

Thu thập per-command timing có overhead. Đo tác động của `-r` bằng cách so sánh một lượt có và một lượt không bật option; không dùng kết quả per-command như thể không có chi phí instrumentation.

### 5.9. Đọc kết quả rate-controlled

Khi dùng `-R`, xem thêm:

- Average/max schedule lag.
- Transactions late.
- Transactions skipped.
- Actual transactions completed.
- Latency theo scheduled start.

Schedule lag tăng liên tục cho thấy hệ thống không xử lý kịp target rate với số clients/threads hiện tại. Giảm target rate hoặc tăng capacity; đừng coi latency được báo là chỉ riêng execution time.

---

## 6. Thiết kế custom scripts sát nghiệp vụ

### 6.1. Khi nào cần custom script?

Dùng custom scripts khi built-in workload không phản ánh:

- Schema và indexes thực tế.
- Tỷ lệ SELECT/INSERT/UPDATE/DELETE.
- Transaction nhiều bước.
- Join và aggregate.
- Phân phối tenant/customer.
- Các khóa thường xuyên được truy cập.
- Query parameter và payload có kích thước khác nhau.

Custom script nên xuất phát từ luồng nghiệp vụ có tần suất cao hoặc tác động lớn tới người dùng.

### 6.2. Cấu trúc script

Một pgbench script là file văn bản gồm các SQL statements kết thúc bằng dấu chấm phẩy và có thể chứa meta-commands bắt đầu bằng dấu backslash. Mỗi lần chạy một script file được tính là một transaction trong pgbench; script cần hoàn thành transaction block hợp lệ.

Biến được đặt bằng meta-command `\set` hoặc option `-D` và tham chiếu trong SQL bằng `:variable_name`.

### 6.3. Ví dụ workload đọc tài khoản

File `read_account.sql`:

```sql
\set account_id random(1, 1000000)
SELECT account_id, balance, updated_at
FROM bench.accounts
WHERE account_id = :account_id;
```

Script mô phỏng point lookup với khóa phân bố đều. Bảng cần có primary key/index trên `account_id`.

### 6.4. Ví dụ workload ghi tài khoản

File `update_account.sql`:

```sql
\set account_id random_zipfian(1, 1000000, 1.07)
\set delta random(1, 100)
UPDATE bench.accounts
SET balance = balance + :delta,
    updated_at = clock_timestamp()
WHERE account_id = :account_id;
```

Script dùng Zipfian distribution để tạo một số account hot hơn phần còn lại. Điều này thường sát workload có một nhóm khách hàng hoặc tài khoản hoạt động vượt trội.

### 6.5. Ví dụ workload đọc danh sách đơn hàng

File `list_orders.sql`:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
SELECT order_id, status, total_amount, created_at
FROM bench.orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 20;
```

Index phù hợp có thể là `(customer_id, created_at DESC)`. Hãy dùng cùng schema/index policy khi so sánh cấu hình.

### 6.6. Ví dụ tạo đơn hàng

File `create_order.sql`:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
\set total_amount random(100, 100000)
INSERT INTO bench.orders
    (customer_id, status, total_amount, created_at)
VALUES
    (:customer_id, 'created', :total_amount, clock_timestamp());
```

Transaction này tạo dữ liệu mới. Mỗi lần benchmark sẽ làm bảng lớn lên, vì vậy cần reset/restore dataset hoặc kiểm soát data growth giữa các lần chạy.

### 6.7. Chạy nhiều scripts với weight

Có thể trộn các scripts và đặt trọng số:

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -f update_account.sql@1 -c 32 -j 8 -T 300 benchdb
```

Trọng số 7:2:1 tạo xác suất chọn script tương ứng khoảng 70% đọc danh sách, 20% tạo đơn và 10% cập nhật tài khoản. Đây là xác suất chọn script, không phải đảm bảo chính xác tỷ lệ trong một khoảng ngắn.

### 6.8. Transaction nhiều câu lệnh

Nếu nghiệp vụ cần nhiều thao tác nguyên tử, đặt các câu lệnh trong cùng một script transaction. Ví dụ:

```sql
\set account_id random(1, 1000000)
\set amount random(1, 500)
WITH changed AS (
    UPDATE bench.accounts
    SET balance = balance - :amount
    WHERE account_id = :account_id
      AND balance >= :amount
    RETURNING account_id
)
INSERT INTO bench.account_events(account_id, amount, created_at)
SELECT account_id, :amount, clock_timestamp()
FROM changed;
```

CTE bảo đảm event chỉ được thêm nếu UPDATE trả về account row đã thay đổi. Đây là một SQL statement nguyên tử và giữ business invariant trong ví dụ. Không đơn giản hóa logic rồi gọi kết quả là workload tương đương ứng dụng.

### 6.9. SQL và meta-command

Một số meta-command hữu ích:

- `\set`: gán biến bằng biểu thức pgbench.
- `\if` / `\elif` / `\else` / `\endif`: điều kiện trong script.
- `\gset`: lưu cột của kết quả query vào biến.
- `\sleep`: mô phỏng think time giữa các thao tác.
- `\startpipeline` / `\endpipeline`: gửi các statement qua extended protocol pipeline.

Không dùng shell meta-commands để tạo side effects ngoài database trong transaction có retry; các side effects ngoài transaction không được rollback như SQL.

### 6.10. Kiểm tra script trước benchmark

Chạy một client, thời gian ngắn, sau đó kiểm tra:

- SQL syntax và schema-qualified names.
- Row counts và dữ liệu sau transaction.
- Constraints và foreign keys.
- Tỷ lệ query thành công.
- Transaction boundaries.
- Script không tạo data growth ngoài dự kiến.

Chỉ tăng concurrency sau khi script đơn client hoạt động đúng.

---

## 7. Phân phối dữ liệu và access pattern

### 7.1. Uniform distribution

`random(min, max)` chọn giá trị đồng đều trong khoảng. Nó phù hợp khi mọi record có xác suất truy cập gần như nhau.

Ví dụ:

```sql
\set account_id random(1, 1000000)
SELECT balance
FROM bench.accounts
WHERE account_id = :account_id;
```

### 7.2. Zipfian distribution

Trong hệ thống thực tế, một số sản phẩm, tài khoản hoặc tenant có thể được truy cập nhiều hơn phần còn lại. Zipfian distribution mô phỏng độ lệch đó:

```sql
\set customer_id random_zipfian(1, 1000000, 1.10)
SELECT customer_id, profile
FROM bench.customers
WHERE customer_id = :customer_id;
```

Tham số skew càng lớn thì các giá trị gần đầu dải càng được chọn thường xuyên. Chọn tham số dựa trên dữ liệu thực tế nếu có, thay vì tùy ý tạo hot keys quá mạnh.

### 7.3. Gaussian và exponential distributions

pgbench cũng có `random_gaussian` và `random_exponential`. Chúng hữu ích khi muốn mô phỏng:

- Truy cập tập trung quanh một nhóm giá trị phổ biến.
- Một phân phối giảm nhanh từ nhóm key hot tới key hiếm.
- Dải truy cập không đồng đều nhưng không theo uniform.

### 7.4. Correlation giữa key và physical row order

Khi dùng non-uniform distribution, key được chọn thường xuyên có thể tương quan với sequence IDs hoặc thứ tự vật lý của rows. Điều đó có thể làm benchmark quá thuận lợi hoặc quá bất lợi do locality.

Dùng `permute` hoặc bước shuffle phù hợp để phân tán các key được chọn thường xuyên, nếu muốn loại bỏ tương quan không chủ ý. pgbench có hàm `permute` tạo phép hoán vị không trùng và không bỏ sót giá trị trong dải.

### 7.5. Working set

Working set là phần dữ liệu mà workload thường xuyên truy cập. Dataset tổng có thể lớn nhưng nếu chỉ một nhóm nhỏ rows được truy cập, working set vẫn nằm trong RAM.

Thiết kế dataset cần phân biệt:

- Tổng database size.
- Kích thước table/index.
- Working set thường xuyên.
- Shared buffers.
- OS page cache.
- RAM dành cho PostgreSQL và các tiến trình khác.

### 7.6. Dataset nhỏ hơn RAM

Nếu dataset và indexes nằm vừa trong memory, benchmark sau warm-up chủ yếu đo CPU, locking, executor, network và memory access. Kết quả có thể cao hơn nhiều so với workload production có working set lớn hơn RAM.

### 7.7. Dataset lớn hơn RAM

Nếu muốn đo storage/I/O behavior, tạo dataset và working set vượt khả năng cache dự kiến. Nhưng đừng chỉ làm table lớn mà vẫn truy cập một vài key lặp đi lặp lại; cần tạo access pattern khiến nhiều pages thực sự được truy cập.

### 7.8. Data skew và tenant skew

Với SaaS/multi-tenant, có thể mô phỏng:

- Nhiều tenant nhỏ và một số tenant lớn.
- Một tenant chiếm phần lớn writes.
- Tenant lớn có nhiều secondary indexes/rows hơn.
- Query fan-out tới nhiều tenants.

Một workload phân bố đều tenant có thể che giấu hotspot hoặc lock contention của production.

### 7.9. Kích thước transaction

Transaction có 1 statement khác đáng kể transaction gồm 10 statements và nhiều index updates. Hãy đo cả:

- Transaction nhỏ, thường xuyên.
- Transaction trung bình với vài bước đọc/ghi.
- Batch transaction có nhiều rows.
- Long-running reports.

Nếu ứng dụng commit theo batch, script benchmark cũng nên giữ transaction boundary tương tự.

### 7.10. Data growth và churn

Workload UPDATE/DELETE tạo dead tuples và index churn. Workload INSERT liên tục làm bảng lớn dần và có thể thay đổi phân phối page. Nếu mỗi lần benchmark dùng dataset khác kích thước, kết quả không còn so sánh công bằng.

Hãy quyết định rõ:

- Test steady-state trên một dataset có kích thước ổn định.
- Hay test growth/ingest trong một khoảng thời gian.
- Có reset dataset giữa các lần chạy hay không.
- Vacuum/autovacuum được phép chạy như production hay bị loại khỏi thí nghiệm.

---

## 8. Tăng concurrency theo bậc

### 8.1. Không bắt đầu ở mức clients tối đa

Bắt đầu từ concurrency thấp để xác định baseline, sau đó tăng dần. Một dãy thử nghiệm minh họa:

| Run | Clients |
|---|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 4 |
| 4 | 8 |
| 5 | 16 |
| 6 | 32 |
| 7 | 64 |
| 8 | 96 |

Đây không phải dãy bắt buộc; chọn theo số cores, connection limits và tải production. Có thể tăng theo bậc nhỏ quanh điểm throughput bắt đầu bão hòa.

### 8.2. Đường cong throughput

Ở concurrency thấp, thêm clients thường làm TPS tăng vì CPU/storage chưa được sử dụng hết. Khi tới điểm bão hòa, TPS tăng chậm hoặc đứng yên; nếu thêm clients nữa, latency thường tăng và failures/lock waits có thể xuất hiện.

```text
TPS
 ^
 |                         ________
 |                    ____/
 |               ____/
 |          ____/
 |     ____/
 |____/
 +---------------------------------> Clients
       rising      saturation
```

Đường cong thực tế có thể giảm sau saturation nếu contention, context switching hoặc resource pressure tăng mạnh.

### 8.3. Đường cong latency

Latency thường tăng khi concurrency vượt khả năng xử lý của hệ thống. Theo dõi cả average và tail latency; average có thể vẫn ổn trong khi một phần nhỏ requests rất chậm.

### 8.4. Tìm điểm bão hòa

Điểm bão hòa có thể nhận biết khi:

- TPS tăng rất ít dù clients tăng.
- Latency bắt đầu tăng nhanh.
- CPU đạt gần capacity hoặc I/O wait tăng.
- Lock waits, queueing hoặc connection waits tăng.
- Schedule lag tăng trong rate-controlled test.

Đừng chọn số clients chỉ vì đó là số lớn nhất pgbench chạy được. Chọn mức tải phản ánh peak concurrency và mức headroom mong muốn.

### 8.5. Phân biệt clients và threads

`-c` là số client sessions; `-j` là số pgbench worker threads. Có thể tăng threads khi máy load generator có nhiều CPU cores và client scheduling trở thành giới hạn. Thay đổi cả clients lẫn threads cùng lúc khiến khó biết yếu tố nào gây khác biệt.

### 8.6. Connection limits

Số clients không nên vượt xa giới hạn kết nối thực tế của server/pool. Nếu benchmark dùng 500 sessions trực tiếp nhưng production dùng pool 40 connections, đó là hai workload khác nhau.

Kiểm tra:

```sql
SHOW max_connections;

SELECT count(*) AS current_connections
FROM pg_stat_activity;
```

Với PgBouncer hoặc managed pool, chạy benchmark qua endpoint mà ứng dụng sử dụng nếu mục tiêu là đo toàn bộ đường kết nối.

### 8.7. Queueing và saturation

Khi service rate đạt giới hạn, requests mới phải chờ. Tăng concurrency lúc này có thể làm latency tăng nhiều mà TPS không tăng. Điều này là behavior cần đo để biết capacity limit, không phải lý do tự động tăng max_connections.

---

## 9. Closed-loop và rate-controlled workload

### 9.1. Closed-loop mặc định

Không dùng `-R`, mỗi pgbench client chạy transaction tiếp theo sau khi transaction hiện tại hoàn tất. Nếu latency tăng, tốc độ phát transaction của client tự giảm.

Đây là mô hình closed-loop. Nó phù hợp để đo throughput tối đa dưới một số lượng clients cố định, nhưng có thể che giấu queueing mà hệ thống nhận từ một nguồn request độc lập.

### 9.2. Rate-controlled workload

`-R` thiết lập target transactions/second. pgbench lên lịch thời điểm bắt đầu theo Poisson process. Mô hình này gần với workload có arrival rate độc lập hơn.

Ví dụ:

```bash
pgbench -R 300 -c 48 -j 8 -T 300 -P 10 benchdb
```

Nếu target 300 TPS cao hơn khả năng hệ thống, schedule lag tăng và transaction latency tính từ scheduled start sẽ bao gồm cả thời gian chờ đến lượt chạy.

### 9.3. Schedule lag

Schedule lag là chênh lệch giữa thời điểm transaction được lên lịch và thời điểm client thực sự bắt đầu nó. Đây là tín hiệu quan trọng để biết load generator/client không thể giữ đúng offered rate.

Khi schedule lag cao:

- Server có thể đã bão hòa.
- Số clients không đủ để duy trì target rate.
- pgbench worker threads hoặc máy client có thể là giới hạn.
- Transaction duration có thể lớn hơn khoảng cách giữa các scheduled starts.

### 9.4. Chọn rate để kiểm tra SLO

Nếu ứng dụng có mục tiêu 250 TPS với p95 latency dưới 100 ms, hãy chạy rate-controlled test quanh mức tải đó và đo tail latency. Sau đó tăng dần target để xác định mức mà latency/failure vượt ngưỡng.

Không chọn target quá thấp rồi kết luận hệ thống có headroom lớn; cũng không chọn target cao hơn rất nhiều so với thực tế mà không giải thích mục đích stress test.

### 9.5. Late và skipped transactions

Kết hợp `-L` với `-R` có thể đánh dấu transaction late và bỏ qua transaction đã trễ quá giới hạn trước khi gửi tới server. Report số skipped; chúng không được xử lý bởi database nên không được tính như completed work.

### 9.6. Arrival rate không phải concurrency

TPS target là tốc độ bắt đầu transaction; số clients là số session có thể chạy đồng thời. Cùng một target rate có thể cần số clients khác nhau tùy latency. Không đồng nhất 300 TPS với 300 clients.

### 9.7. Khi nào dùng từng mô hình?

| Mục tiêu | Mô hình |
|---|---|
| Tìm throughput tối đa với N clients | Closed-loop |
| Kiểm tra SLO ở offered load xác định | Rate-controlled |
| Mô phỏng burst/arrival behavior | Rate-controlled và scripts phù hợp |
| Đo chi phí tạo kết nối | Kết hợp `-C` |
| Đo giới hạn concurrency/lock | Closed-loop sweep clients |

---

## 10. Warm-up, cache state và cold-start bias

### 10.1. Shared buffers và OS page cache

PostgreSQL đọc pages qua shared buffers, trong khi OS cũng có page cache. Một query lần đầu có thể phải nạp pages từ storage; các lần sau có thể đọc từ shared buffers hoặc OS cache.

Do đó, lần chạy đầu tiên và các lần chạy sau có thể có hiệu năng rất khác nhau dù SQL và dataset không đổi.

### 10.2. Warm-up phase

Đối với steady-state benchmark:

1. Khởi tạo/restore dataset.
2. Chạy workload warm-up.
3. Bỏ kết quả warm-up.
4. Chạy measured interval đủ dài.
5. Ghi nhận cache hit, I/O và latency theo thời gian.

Warm-up nên đại diện cùng workload với measured phase để nạp đúng working set.

### 10.3. Không mặc định lần chạy đầu là cold cache

Restart PostgreSQL làm shared buffers trống, nhưng không nhất thiết xóa OS page cache. Vì vậy, restart server không tự động tạo ra một cold-storage benchmark có thể so sánh.

Cold-cache test cần môi trường chuyên dụng và quy trình kiểm soát cache ở cả PostgreSQL lẫn OS/storage. Không dùng thao tác drop OS caches trên production; nó ảnh hưởng các tiến trình khác và có thể gây outage/performance regression.

### 10.4. Dataset vượt RAM

Để đo storage-bound workload, có thể dùng dataset lớn hơn khả năng cache và truy cập trên một working set đủ rộng. Nếu chỉ tạo table lớn nhưng query luôn truy cập một nhóm nhỏ pages, cache vẫn có thể che giấu storage latency.

### 10.5. Warm cache và cold cache trả lời câu hỏi khác nhau

| Loại test | Câu hỏi |
|---|---|
| Warm cache | Hệ thống hoạt động ra sao sau khi working set đã được cache? |
| Cold/first-touch | Hệ thống phản ứng thế nào khi dữ liệu chưa nằm trong cache? |
| Mixed cache | Hệ thống hoạt động ra sao với hit/miss ratio gần production? |

Không gộp ba kết quả thành một số trung bình duy nhất nếu chúng đại diện cho các tình huống vận hành khác nhau.

### 10.6. Cache state giữa A/B

Khi so sánh cấu hình A và B, nếu A được chạy sau warm-up còn B chạy ngay sau restart, kết quả bị lệch. Dùng cùng warm-up protocol và cùng cache-state target cho cả hai.

### 10.7. Đo cache hit và read I/O

Có thể đối chiếu pg_stat_database:

```sql
SELECT
    datname,
    blks_hit,
    blks_read,
    round(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS cache_hit_pct,
    temp_files,
    temp_bytes
FROM pg_stat_database
WHERE datname = current_database();
```

Đây là counters tích lũy. Lấy snapshot trước và sau benchmark để tính delta; không so sánh trực tiếp counters từ hai lần chạy nếu chúng chưa được reset hoặc trừ baseline.

---

## 11. Vacuum, dead tuples và trạng thái dữ liệu

### 11.1. Update tạo dead tuples

PostgreSQL dùng MVCC. UPDATE/DELETE thường tạo phiên bản row mới hoặc đánh dấu phiên bản cũ không còn visible với các transaction mới. Dead tuples và dead index entries có thể tích lũy cho tới khi vacuum xử lý.

Vì vậy, cùng một benchmark chạy trên table mới và table đã trải qua hàng triệu updates có thể cho kết quả khác nhau.

### 11.2. Autovacuum ảnh hưởng kết quả

Autovacuum có thể bắt đầu trong measured interval và cạnh tranh CPU/I/O với workload. Đây không nhất thiết là nhiễu cần loại bỏ: trong production, autovacuum là một phần của hệ thống. Cần quyết định mục tiêu:

- **Production-like:** để autovacuum hoạt động như cấu hình thực tế và ghi nhận lúc nó chạy.
- **Isolated microbenchmark:** có thể kiểm soát vacuum state để cô lập một yếu tố, nhưng không dùng kết quả đó làm đại diện production.

### 11.3. Ghi nhận thời điểm vacuum

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Đối chiếu trước/sau benchmark để biết table nào tăng dead tuples hoặc được vacuum trong khoảng đo.

### 11.4. Không dùng VACUUM FULL như bước warm-up

VACUUM FULL rewrite table, cần lock mạnh và thay đổi physical layout. Nó không phải bước chuẩn để “làm sạch” trước mọi benchmark. Dùng VACUUM/ANALYZE theo mục tiêu và giữ quy trình giống nhau giữa các lần thử.

### 11.5. Analyze và planner statistics

Nếu dataset thay đổi đáng kể, chạy ANALYZE trước benchmark để planner có statistics phù hợp:

```sql
ANALYZE bench.accounts;
ANALYZE bench.orders;
```

Không để một cấu hình dùng statistics mới và cấu hình còn lại dùng statistics cũ. Với workload có skew/correlation, xem xét extended statistics nếu ứng dụng thực tế dùng chúng.

### 11.6. Index bloat và table bloat

Workload update-heavy lâu dài có thể làm tăng bloat. Nếu một run bắt đầu trên index gọn còn run khác bắt đầu sau nhiều churn, so sánh sẽ sai lệch. Dùng snapshot/restore hoặc quy trình chuẩn hóa dataset giữa các lần thử.

### 11.7. History tables tăng liên tục

Trong built-in pgbench, pgbench_history tăng theo số transactions. Nếu không reset/khởi tạo lại theo quy trình giống nhau, table/index size và cache footprint sẽ khác qua các runs.

### 11.8. Autovacuum không phải nhiễu luôn phải tắt

Tắt autovacuum để benchmark có thể tạo kết quả tốt trong thời gian ngắn nhưng che giấu vấn đề vận hành lâu dài. Nếu mục tiêu là capacity production, hãy giữ autovacuum và quan sát tác động của nó.

---

## 12. Lặp lại và kiểm soát sai lệch

### 12.1. Không tin một lần chạy ngắn

Các run chỉ vài giây rất nhạy với scheduler, cache, checkpoint, background tasks và trạng thái kết nối. Tài liệu PostgreSQL khuyến nghị chạy ít nhất vài phút và lặp lại; một số hệ thống cần thời gian dài hơn để có kết quả ổn định.

### 12.2. Warm-up không tính vào measured run

Tách riêng:

- Initialization/setup.
- Warm-up.
- Measurement.
- Cool-down/restore.

Ghi rõ duration của từng phase. Không âm thầm cộng warm-up vào số liệu throughput chính.

### 12.3. Lặp nhiều lần

Chạy mỗi cấu hình nhiều lần trong cùng điều kiện. Báo median, range hoặc interquartile range cùng số lần chạy. Nếu kết quả phân tán lớn, điều tra nguyên nhân thay vì chọn run tốt nhất.

### 12.4. Randomize thứ tự A/B

Nếu luôn chạy A trước B, B có thể được hưởng cache nóng hơn hoặc chịu tải background khác. Có thể luân phiên A/B, B/A hoặc randomize thứ tự qua các vòng để giảm time-order bias.

### 12.5. Paired runs

Nếu có thể khôi phục cùng snapshot dataset, chạy A và B trên cùng trạng thái dữ liệu. So sánh từng cặp runs gần nhau về thời gian, thay vì so một run A với một run B rất xa nhau.

### 12.6. Thay đổi một yếu tố chính

Ví dụ khi đánh giá index:

1. Giữ nguyên hardware, PostgreSQL config, dataset và script.
2. Chạy baseline không index mới.
3. Tạo index.
4. ANALYZE theo cùng quy trình.
5. Warm-up tương tự.
6. Chạy measured workload.
7. Lặp lại và so sánh latency, TPS, buffers, write cost và storage size.

Không đồng thời thay work_mem, shared_buffers, index và client count.

### 12.7. Giữ nguyên transaction mix

Khi A dùng 80% SELECT/20% UPDATE còn B dùng 95% SELECT/5% UPDATE, TPS có thể khác vì lượng công việc khác nhau. Dùng cùng script weights và cùng parameter distribution.

### 12.8. Random seed

`--random-seed` cho phép tái lập chuỗi random numbers trong các điều kiện phù hợp. Dùng seed cố định hữu ích để debug một case cụ thể hoặc so sánh cùng access sequence.

Tuy nhiên, lặp đi lặp lại đúng một seed có thể che giấu biến động workload hoặc tạo lợi thế cache cho cùng một tập pages. Với đánh giá variability, dùng các seeds khác nhau và ghi lại seed; dùng seed cố định cho paired diagnostic khi cần.

### 12.9. Tránh thay đổi hệ thống ngoài ý muốn

Trong mỗi measured interval, ghi nhận:

- Backup, replication, autovacuum, checkpoint.
- Deploy/application traffic khác.
- Cloud noisy neighbor hoặc CPU throttling.
- Storage burst credits/throttling.
- Network congestion.
- Autoscaling hoặc VM migration.

Nếu có event lớn, đánh dấu run không comparable hoặc chạy lại theo protocol.

### 12.10. Chênh lệch nhỏ có thể chỉ là noise

Nếu A nhanh hơn B 2% nhưng run-to-run variation là 8%, chưa đủ bằng chứng kết luận A tốt hơn. Cần tăng số lần lặp, tăng duration hoặc giảm nguồn nhiễu.

---

## 13. Thu thập metrics phía PostgreSQL

### 13.1. pg_stat_database

Lấy snapshot trước/sau:

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

Các counters tích lũy giúp đối chiếu lượng công việc thực sự đã xảy ra. Tính delta giữa hai snapshots để có số liệu của measured interval.

### 13.2. pg_stat_activity và wait events

Trong lúc benchmark:

```sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS backends
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY backends DESC;
```

Nếu nhiều backends chờ Lock, benchmark có thể bị contention. Nếu chờ IO, cần xem storage; nếu active nhưng không wait, CPU hoặc executor có thể đang làm việc.

### 13.3. pg_stat_statements

Nếu extension đã được bật, snapshot query stats trước/sau benchmark để tìm query groups có:

- Total execution time cao.
- Calls tăng nhiều.
- Shared blocks read cao.
- Temporary blocks cao.
- WAL bytes cao.
- Planning time cao nếu tracking được bật.

Kết hợp queryid và query text để nhận diện câu SQL; không dùng queryid như khóa ổn định giữa major versions.

### 13.4. pg_stat_io

PostgreSQL 16 trở lên có `pg_stat_io` để xem I/O activity theo backend type, object và context:

```sql
SELECT
    backend_type,
    object,
    context,
    reads,
    read_time,
    writes,
    write_time,
    fsyncs,
    fsync_time
FROM pg_stat_io
ORDER BY backend_type, object, context;
```

Kiểm tra schema view của major version trước khi dùng dashboard đa version. pg_stat_io là server-level view, không gán mọi I/O trực tiếp cho một query duy nhất.

### 13.5. WAL và checkpoints

Theo dõi:

- WAL bytes/records được tạo.
- Archive backlog và replication lag.
- Checkpoint frequency và write pressure.
- WAL buffers/checkpoint writes.
- Disk free space của pg_wal.

Một benchmark write-heavy có thể bị giới hạn bởi WAL flush hoặc checkpoint, dù query plan rất đơn giản.

### 13.6. Lock statistics

```sql
SELECT
    locktype,
    mode,
    granted,
    count(*) AS lock_count
FROM pg_locks
GROUP BY locktype, mode, granted
ORDER BY lock_count DESC;
```

Nếu cần xác định blocker, dùng `pg_blocking_pids()` cùng `pg_stat_activity`. Đừng chỉ nhìn số lock; cần xem thời gian chờ và object đang bị tranh chấp.

### 13.7. Autovacuum và dead tuples

Đối chiếu `pg_stat_user_tables`, logs và activity để biết vacuum/analyze có chạy trong measured interval không. Nếu benchmark production-like, giữ behavior autovacuum như production.

### 13.8. Reset counters có kiểm soát

Không reset mọi statistics trong cluster chỉ để benchmark có số đẹp. Ưu tiên snapshot trước/sau. Nếu buộc phải reset, chỉ làm trong lab và ghi rõ reset timestamp, view/function đã reset và ảnh hưởng tới monitoring khác.

---

## 14. Thu thập metrics phía OS và load generator

### 14.1. CPU

Theo dõi:

- CPU utilization tổng và theo core.
- User/system/iowait/steal time.
- Run queue/load average.
- Context switches.
- CPU throttling trong container/cgroup.

CPU toàn máy 70% không có nghĩa mọi core đều còn headroom; một thread nóng có thể là bottleneck dù average utilization thấp.

### 14.2. Memory

Ghi nhận:

- RAM available/free.
- Swap activity.
- Page faults.
- PostgreSQL RSS/shared memory.
- Memory của pgbench client.
- Cgroup memory limit/pressure.

Nếu hệ thống swap trong measured interval, kết quả có thể không đại diện steady-state bình thường.

### 14.3. Storage

Theo dõi:

- IOPS và throughput đọc/ghi.
- Read/write latency.
- Queue depth.
- Utilization và throttling.
- Filesystem free space.
- WAL/data/temp volume.

Nếu storage service có burst credits hoặc giới hạn throughput, ghi trạng thái đó trước và sau test.

### 14.4. Network

Ghi RTT giữa pgbench host và database host, throughput, retransmits, packet drops và interface utilization. Với cloud database, chạy client cùng region/VPC khi đo server capacity; nếu chạy từ xa, kết quả bao gồm WAN latency.

### 14.5. Load generator

Trên máy pgbench, theo dõi CPU, memory, network và số threads. Nếu client host bão hòa trước database, TPS đo được là giới hạn của load generator.

### 14.6. Đồng bộ thời gian

Đồng bộ clock trên client, database và monitoring host để đối chiếu logs, snapshots và metrics theo timestamp. Ghi timezone và thời điểm bắt đầu/kết thúc từng run.

### 14.7. Correlate theo timeline

Vẽ/ghi cùng timeline:

- TPS và latency mỗi interval.
- CPU và I/O utilization.
- Active sessions/wait events.
- Checkpoint/autovacuum.
- WAL rate và replication lag.

Một spike latency đúng lúc checkpoint hoặc storage throttling thường giải thích được vì sao average cuối run thay đổi.

---

## 15. Chuẩn bị custom dataset có thể tái lập

### 15.1. Tạo schema benchmark

Ví dụ schema cho workload tài khoản và đơn hàng:

```sql
CREATE SCHEMA IF NOT EXISTS bench;

CREATE TABLE bench.accounts (
    account_id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE bench.account_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE bench.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    total_amount INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
```

Đây là schema lab tối giản. Nếu production có foreign keys, triggers, partitioning, RLS hoặc nhiều indexes, hãy thêm chúng vào custom benchmark để mô phỏng chi phí thật.

### 15.2. Sinh accounts

```sql
INSERT INTO bench.accounts(account_id, balance, updated_at)
SELECT
    g,
    100000,
    clock_timestamp()
FROM generate_series(1, 1000000) AS g;
```

### 15.3. Sinh orders

```sql
INSERT INTO bench.orders
    (customer_id, status, total_amount, created_at)
SELECT
    (g % 100000) + 1,
    CASE WHEN g % 5 = 0 THEN 'paid' ELSE 'created' END,
    100 + (g % 100000),
    clock_timestamp() - (g % 365) * interval '1 day'
FROM generate_series(1, 2000000) AS g;
```

### 15.4. Tạo index và statistics

```sql
CREATE INDEX orders_customer_created_idx
ON bench.orders (customer_id, created_at DESC);

ANALYZE bench.accounts;
ANALYZE bench.orders;
ANALYZE bench.account_events;
```

Để so sánh hai index strategies, tạo từng trạng thái từ cùng một base snapshot. Không để một run có index còn run kia thiếu index ngoài mục tiêu thí nghiệm.

### 15.5. Kiểm tra kích thước và row counts

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
WHERE schemaname = 'bench'
ORDER BY relname;
```

Ghi lại kích thước tables/indexes và row counts để so sánh giữa các lần chạy.

### 15.6. Tái tạo trạng thái ban đầu

Các lựa chọn:

- Restore cùng database snapshot/backup.
- Recreate schema và regenerate data bằng script cố định.
- Dùng clone/snapshot của storage/database nếu nền tảng hỗ trợ.
- Thiết kế workload không làm thay đổi phân phối dữ liệu nếu mục tiêu là đo read-only.

Không dùng cùng một database đã bị write-heavy churn cho tất cả các runs mà không ghi nhận data drift.

### 15.7. Không để setup lẫn vào measurement

CREATE INDEX, bulk INSERT, ANALYZE và initial vacuum là setup. Chạy xong, ghi nhận thời gian setup, kiểm tra data state rồi mới bắt đầu warm-up/measured phases.

---

## 16. Các kịch bản workload thực tế

### 16.1. Read-heavy application

Đặc điểm:

- Nhiều point lookups và list/search.
- Ít ghi.
- Working set có thể tập trung vào hot customers/products.
- Index và cache hit có ảnh hưởng lớn.

Có thể dùng `list_orders.sql` và `read_account.sql` với weight cao cho SELECT. Đo cả warm-cache và dataset lớn hơn cache nếu production có yêu cầu I/O.

### 16.2. Mixed OLTP

Ví dụ mix:

| Transaction | Weight | Tỷ lệ dự kiến |
|---|---:|---:|
| Đọc danh sách đơn | 7 | 70% |
| Tạo đơn | 2 | 20% |
| Cập nhật tài khoản | 1 | 10% |

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -f update_account.sql@1 -c 48 -j 8 -T 300 -P 10 benchdb
```

Tỷ lệ này chỉ là ví dụ. Dùng transaction mix được đo từ application telemetry hoặc access logs nếu có.

### 16.3. Write-heavy ingestion

Đặc điểm:

- Nhiều INSERT.
- WAL rate cao.
- Index maintenance và checkpoint quan trọng.
- Table growth và autovacuum có thể ảnh hưởng theo thời gian.

Tạo script insert batch/row theo transaction boundary của ứng dụng. Đo WAL bytes, commit latency, storage throughput và replication lag nếu có standby.

### 16.4. Hot-row contention

Để mô phỏng nhiều clients cập nhật cùng account:

```sql
\set account_id 1
\set delta random(1, 10)
UPDATE bench.accounts
SET balance = balance + :delta,
    updated_at = clock_timestamp()
WHERE account_id = :account_id;
```

Kịch bản này cố ý tạo hotspot. Dùng để đo lock contention hoặc kiểm tra thiết kế counter/hot key; không dùng làm đại diện cho phân phối truy cập đều.

### 16.5. Skewed customer workload

Dùng Zipfian để một nhóm customer phổ biến được truy cập thường xuyên:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
SELECT order_id, status, total_amount
FROM bench.orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 20;
```

So sánh với uniform distribution để thấy tác động của cache locality, hot indexes và contention.

### 16.6. Reporting workload

Ví dụ:

```sql
SELECT
    customer_id,
    status,
    count(*) AS order_count,
    sum(total_amount) AS total_amount
FROM bench.orders
WHERE created_at >= current_date - interval '30 days'
GROUP BY customer_id, status
ORDER BY total_amount DESC
LIMIT 100;
```

Đây là workload nặng aggregate/sort. Đo temp blocks, memory spills, actual rows, I/O và plan. Đừng trộn quá nhiều report queries vào OLTP test nếu mục tiêu là đo riêng OLTP.

### 16.7. Connection churn

So sánh giữ kết nối và tạo connection mới mỗi transaction:

```bash
pgbench -c 32 -j 8 -T 180 benchdb
pgbench -C -c 32 -j 8 -T 180 benchdb
```

Chênh lệch giúp ước lượng chi phí connection setup/authentication trong test. Nếu production dùng PgBouncer, chạy thêm test qua pool với pool mode, pool size và client concurrency tương ứng.

### 16.8. Mixed workload với think time

Nếu người dùng có khoảng nghỉ giữa các thao tác, có thể dùng `\sleep` để mô phỏng think time. Tuy nhiên, think time làm giảm số transaction/second mỗi client và thay đổi concurrency thực tế; ghi rõ thời gian sleep và lý do.

### 16.9. Read-after-write

Một flow có thể tạo đơn rồi đọc lại đơn vừa tạo. Điều này kiểm tra transaction boundaries, index visibility và consistency assumptions của ứng dụng. Script cần truyền ID vừa tạo sang query kế tiếp bằng `RETURNING`/`\gset` hoặc cách tương đương.

### 16.10. Chọn một bộ workload đại diện

Không cần đưa mọi query của ứng dụng vào một script khổng lồ. Chọn một số luồng quan trọng và báo kết quả theo từng script. Nếu dùng weights, ghi lại cách xác định tỷ lệ và tổng workload mix.

---

## 17. So sánh cấu hình A/B công bằng

### 17.1. Định nghĩa baseline

Baseline là cấu hình và workload tham chiếu trước khi thay đổi. Ghi rõ:

- PostgreSQL version/build.
- Hardware/storage/network.
- Server parameters.
- Dataset snapshot/size/indexes.
- pgbench client version.
- Script và weights.
- Clients/threads/protocol/rate/duration.
- Warm-up và measured interval.
- Cache/vacuum state.

### 17.2. Thay một biến chính

Ví dụ so sánh hai giá trị work_mem:

1. Giữ nguyên dataset, indexes, script và client settings.
2. Chạy baseline với work_mem hiện tại.
3. Chỉ đổi work_mem.
4. Chạy cùng warm-up và measured phases.
5. Lặp lại nhiều lần.
6. So sánh TPS, latency, temp blocks, memory và CPU.

Nếu đồng thời tăng work_mem, đổi index và tăng clients, không thể quy kết cải thiện cho một thay đổi cụ thể.

### 17.3. So sánh index strategies

Index có thể tăng tốc SELECT nhưng làm INSERT/UPDATE chậm hơn do index maintenance và tăng storage. Đánh giá cả workload mix:

- Read latency.
- Write TPS/latency.
- WAL bytes.
- Index size.
- Vacuum overhead.

Không benchmark riêng SELECT rồi kết luận index tốt cho toàn bộ OLTP workload.

### 17.4. So sánh PostgreSQL settings

Khi thay đổi shared_buffers, work_mem, effective_cache_size, checkpoint settings hoặc parallelism:

- Xác định setting có yêu cầu restart/reload không.
- Chờ server ở trạng thái ổn định sau restart.
- Dùng cùng cache/warm-up policy.
- Ghi các giá trị thực tế bằng SHOW.
- Đo cả workload mục tiêu và workload phụ có thể bị ảnh hưởng.

### 17.5. So sánh storage

Giữ nguyên PostgreSQL build/config, dataset, script, client placement và concurrency. Theo dõi IOPS, throughput, latency và queue depth của cả hai storage systems. Nếu volume size hoặc burst credits khác nhau, ghi rõ.

### 17.6. So sánh network/client location

Nếu đổi vị trí load generator, đó là thay đổi network path. Đo RTT và throughput riêng. Muốn đánh giá server capacity, giữ client ở cùng vùng mạng; muốn đo user experience, giữ đường đi tương tự người dùng.

### 17.7. Bảng kết quả A/B

| Metric | Baseline A | Variant B | Delta |
|---|---:|---:|---:|
| TPS |  |  |  |
| Mean latency |  |  |  |
| p95 latency |  |  |  |
| p99 latency |  |  |  |
| Failed transactions |  |  |  |
| Schedule lag |  |  |  |
| CPU utilization |  |  |  |
| Read/write IOPS |  |  |  |
| WAL bytes/s |  |  |  |
| Temp bytes |  |  |  |

Điền giá trị từ nhiều lần chạy; dùng median và độ phân tán. Nếu p95/p99 không được đo, để trống thay vì ước lượng từ average.

### 17.8. Kết luận có điều kiện

Một cấu hình có thể tăng throughput nhưng làm tail latency xấu hơn. Kết luận cần gắn với mục tiêu:

- Nếu ưu tiên maximum throughput, xem TPS tại saturation.
- Nếu ưu tiên interactive SLO, xem p95/p99 ở offered load mục tiêu.
- Nếu ưu tiên write durability, không loại bỏ fsync/commit semantics để lấy TPS cao.
- Nếu ưu tiên chi phí, xem throughput/latency trên cùng budget tài nguyên.

---

## 18. Diễn giải kết quả và tìm bottleneck

### 18.1. TPS tăng, latency ổn định

Đây thường là dấu hiệu tốt khi tăng concurrency hoặc cải thiện cấu hình. Xác nhận failure rate không tăng và resource headroom còn phù hợp.

### 18.2. TPS đứng yên, latency tăng

Hệ thống có thể đã tới saturation. Kiểm tra CPU, I/O, locks, connection queue, WAL flush và load generator. Thêm clients không nhất thiết tăng throughput.

### 18.3. CPU cao, I/O thấp

Có thể workload CPU-bound hoặc bị giới hạn bởi executor, expressions, joins, aggregation, serialization hoặc context switching. Xem EXPLAIN ANALYZE, pg_stat_statements và CPU theo core.

### 18.4. I/O wait cao

Đối chiếu storage latency/IOPS/queue depth, shared blocks read và I/O timing. Kiểm tra working set, index access pattern, sequential scans, checkpoints và storage throttling.

### 18.5. Lock waits cao

Xem pg_stat_activity.wait_event_type, pg_blocking_pids(), pg_locks và transaction age. Hot rows hoặc cập nhật chung một parent row có thể tạo contention.

### 18.6. Temporary blocks cao

Xem sort/hash nodes trong EXPLAIN, actual rows, work_mem và concurrency. Đánh giá query rewrite/index/statistics trước khi tăng memory toàn cục.

### 18.7. WAL rate cao

Xem write workload, index maintenance, full-page images, checkpoints và replication/archive throughput. Tăng WAL generation có thể làm downstream replication lag hoặc archive backlog.

### 18.8. CPU client cao, server còn rảnh

Load generator có thể không tạo đủ request. Tăng pgbench worker threads, chuyển client sang host mạnh hơn hoặc dùng nhiều client hosts. Đừng kết luận PostgreSQL chỉ đạt mức TPS hiện tại.

### 18.9. Latency cao nhưng server metrics thấp

Kiểm tra network RTT, DNS, TLS/authentication, connection pool queue, client scheduling và application serialization. pgbench latency là end-to-end từ client; không chỉ là server execution time.

### 18.10. Throughput giảm sau một thời gian

Các nguyên nhân có thể:

- Autovacuum/checkpoint bắt đầu.
- Dataset/history table tăng.
- Cache working set thay đổi.
- Dead tuples/index bloat tăng.
- Storage burst credits cạn.
- Client/server thermal or CPU throttling.
- Network congestion.

Dùng progress logs và server telemetry theo timeline để tìm thời điểm bắt đầu thay đổi.

---

## 19. Các nguồn sai lệch thường gặp

### 19.1. Run quá ngắn

Một run 5–10 giây có thể chỉ đo startup/cache effects. Chạy đủ vài phút, lặp lại và tách warm-up.

### 19.2. Dataset không đại diện

Dataset quá nhỏ khiến cache hit cao bất thường; dataset quá lớn hoặc access distribution khác production cũng làm kết quả lệch.

### 19.3. Scale factor quá nhỏ

Với built-in TPC-B-like, scale thấp hơn client count có thể tạo hot branch contention. Khi đó benchmark đo contention do thiết lập chứ không đo năng lực tổng thể.

### 19.4. Client và server cùng host

pgbench tranh CPU/network với PostgreSQL. Nếu client bị bão hòa, throughput đo được thấp giả tạo.

### 19.5. Autovacuum không nhất quán

Một run bị vacuum trong measured interval còn run khác thì không sẽ khó so sánh. Hoặc kiểm soát giống nhau, hoặc giữ production-like và ghi nhận event.

### 19.6. Cache state khác nhau

Run đầu cold-ish, run sau warm có thể cho kết quả khác nhiều. Áp dụng cùng warm-up protocol hoặc đo riêng từng cache scenario.

### 19.7. Transaction mix khác nhau

Khác script, weights, query parameters, payload size hoặc transaction boundary làm số TPS không còn cùng ý nghĩa.

### 19.8. Protocol mode khác nhau

Simple, extended và prepared protocol có overhead/plan behavior khác nhau. Giữ giống nhau nếu không phải biến cần đo.

### 19.9. Bật logging ở một run

`-l`, `-r` và sampling/logging có thể làm client/server overhead tăng. Đừng so run có logging với run không logging mà không ghi nhận.

### 19.10. Chọn kết quả tốt nhất

Chỉ lấy run nhanh nhất tạo bias. Báo median và variability; nếu run-to-run variance lớn, tăng số lần lặp hoặc kiểm soát môi trường tốt hơn.

### 19.11. Random seed lặp lại mãi

Cùng một seed có thể lặp lại cùng access pattern và cache footprint. Dùng seed cố định cho debugging/paired comparison, nhiều seeds cho đánh giá variability.

### 19.12. Background traffic

Backup, batch jobs, replication, ETL, monitoring queries và user traffic khác có thể chiếm tài nguyên. Dừng chúng trong lab hoặc giữ chúng ổn định và ghi nhận.

### 19.13. Thay nhiều tham số cùng lúc

Không thể biết yếu tố nào cải thiện/giảm hiệu năng. Dùng từng thí nghiệm có giả thuyết rõ ràng.

### 19.14. So sánh máy không tương đương

CPU, memory, storage, kernel, filesystem, virtualization, cgroup, network và firmware đều có thể ảnh hưởng. Chuẩn hóa hoặc ghi rõ khác biệt trước khi kết luận.

---

## 20. Troubleshooting benchmark

### 20.1. pgbench không kết nối được

Kiểm tra:

- Hostname, port và route.
- Firewall/security group.
- PostgreSQL đang listen.
- pg_hba.conf và authentication.
- Database/user tồn tại và có quyền.
- SSL mode/certificate nếu dùng TLS.
- Connection limit và pool.

Chạy psql với cùng host/user/database để tách lỗi kết nối khỏi lỗi benchmark.

### 20.2. Relation does not exist

Với custom scripts, xác nhận schema/table đã tạo và tên được schema-qualify. Với built-in script, xác nhận đã chạy initialization mode trong đúng database.

### 20.3. Duplicate key hoặc constraint violation

Workload có thể tạo ID trùng, dữ liệu ban đầu không phù hợp hoặc script retry làm thao tác không idempotent. Kiểm tra transaction logic và retry policy; không bỏ constraint chỉ để benchmark chạy qua.

### 20.4. Deadlocks/serialization failures

Kiểm tra thứ tự lock, hot rows, transaction duration và isolation level. Ghi failures/retries và xem pg_stat_activity/pg_locks. Retry chỉ khi ứng dụng thực tế cũng có retry semantics phù hợp.

### 20.5. TPS thấp hơn dự kiến

Kiểm tra:

- Có phải pgbench client bị CPU-bound?
- Có network RTT cao?
- Có lock waits hoặc connection queue?
- Dataset có working set lớn hơn cache?
- Storage đang throttling?
- Autovacuum/checkpoint có chạy?
- Có quá nhiều clients so với capacity?
- Script có query nặng hơn dự kiến?

### 20.6. Latency tăng liên tục

Xem schedule lag, active sessions, wait events, CPU run queue, I/O latency và checkpoint/vacuum timeline. Nếu dùng `-R`, giảm target rate để xác định mức tải ổn định.

### 20.7. Run có nhiều skipped transactions

Khi dùng rate control và latency limit, skipped transaction không được gửi tới server. Kiểm tra target rate, client count, latency limit và schedule lag. Báo skipped count trong kết quả; không tính chúng như completed transactions.

### 20.8. Logs quá lớn

Giảm sampling rate, dùng aggregate interval nếu phù hợp, hoặc giới hạn measured duration. Ghi lại sampling rate và hiệu chỉnh cách tính nếu phân tích TPS từ sampled logs.

### 20.9. Per-command latency làm TPS giảm

Option `-r` thu thập timing từng statement và có overhead. So sánh một lượt không có `-r` với một lượt có `-r` để ước lượng tác động.

### 20.10. Không tái hiện được kết quả

Ghi lại exact command, script hashes, random seeds, data snapshot, PostgreSQL settings, cache state, host placement và metrics timeline. Thử lặp lại với seed cố định để debug, rồi dùng nhiều seeds để đo variability.

---

## 21. Quy trình benchmark end-to-end trong lab

### 21.1. Bước 1 — Xác định câu hỏi

Ví dụ: kiểm tra index `(customer_id, created_at DESC)` có cải thiện list-orders workload mà không làm write workload chậm quá mức không.

### 21.2. Bước 2 — Chuẩn bị database

Tạo database lab riêng, kết nối bằng role benchmark và xác nhận PostgreSQL/pgbench versions. Không dùng database production.

### 21.3. Bước 3 — Tạo dataset

Chạy DDL và data generation ở mục 15. Ghi row counts, table/index sizes và server settings. Tạo một snapshot để có thể khôi phục cùng trạng thái giữa A/B.

### 21.4. Bước 4 — Chuẩn bị script

File `list_orders.sql`:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
SELECT order_id, status, total_amount, created_at
FROM bench.orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 20;
```

File `create_order.sql`:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
\set total_amount random(100, 100000)
INSERT INTO bench.orders
    (customer_id, status, total_amount, created_at)
VALUES
    (:customer_id, 'created', :total_amount, clock_timestamp());
```

### 21.5. Bước 5 — Smoke test

```bash
pgbench -f list_orders.sql -c 1 -j 1 -T 10 -P 2 benchdb
```

Xác nhận script chạy thành công, không lỗi SQL và truy vấn trả dữ liệu hợp lý.

### 21.6. Bước 6 — Warm-up

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -c 16 -j 4 -T 60 benchdb
```

Đây là warm-up, không đưa kết quả vào measured baseline. Nếu workload ghi làm thay đổi data size đáng kể, khôi phục snapshot trước measured run hoặc định nghĩa steady-state growth policy.

### 21.7. Bước 7 — Measured run

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -c 16 -j 4 -T 300 -P 10 -l --log-prefix=run_a benchdb
```

Ghi lại output và transaction logs. Thu thập CPU, storage, network và PostgreSQL metrics cùng timestamp.

### 21.8. Bước 8 — Sweep concurrency

Chạy cùng workload và duration với 1, 2, 4, 8, 16, 32 clients. Không thay đổi các yếu tố khác. Tạo bảng TPS/latency/failure theo concurrency để tìm điểm bão hòa.

### 21.9. Bước 9 — Rate-controlled run

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -R 250 -c 32 -j 8 -T 300 -P 10 -L 100 benchdb
```

Kiểm tra schedule lag, late/skipped transactions và latency. Chỉ dùng `-L` nếu có SLO/latency target cụ thể; nếu không, bỏ option này và báo latency đầy đủ.

### 21.10. Bước 10 — A/B index

Baseline A: giữ trạng thái không có index mới, chạy warm-up và measured test. Restore dataset. Variant B: tạo index, ANALYZE, warm-up và chạy đúng command. So sánh read latency, write TPS, WAL, storage size và temp/I/O metrics.

### 21.11. Bước 11 — Lặp lại

Lặp lại mỗi cấu hình nhiều lần; đổi thứ tự A/B qua các vòng nếu có thể. Báo median và spread, không chọn run nhanh nhất.

### 21.12. Bước 12 — Lưu report

Report cần có:

- Mục tiêu và giả thuyết.
- Mô tả server/client/hardware/network.
- Dataset snapshot, row counts, sizes và indexes.
- Script content/hash, weights, random seeds.
- Command line chính xác.
- Warm-up/duration/repetitions.
- TPS, average/stddev, p95/p99 nếu đã đo, failures/retries/skipped.
- CPU, memory, storage, network, WAL, waits và vacuum/checkpoint events.
- Phân tích bottleneck, kết luận và giới hạn.

### 21.13. Bước 13 — Dọn lab

Sau khi lưu report, dừng load generators, kiểm tra sessions còn lại và xóa database/schema lab theo quy trình. Không để benchmark jobs tiếp tục chạy hoặc để test data chiếm storage ngoài dự kiến.

---

## 22. Bài tập thực hành và đáp án

### Bài 1 — TPC-B-like

**Câu hỏi:** Workload mặc định của pgbench có phải TPC-B chính thức không?

**Đáp án:** Không. Đây là workload TPC-B-like, lấy cảm hứng từ TPC-B nhưng không phải benchmark/certification TPC-B.

### Bài 2 — Initialization

**Câu hỏi:** Vì sao cần database riêng khi chạy pgbench -i?

**Đáp án:** Initialization drop/recreate các bảng pgbench có tên cố định và có thể phá dữ liệu trùng tên.

### Bài 3 — Scale factor

**Câu hỏi:** Vì sao scale factor của built-in TPC-B-like nên ít nhất bằng số clients lớn nhất?

**Đáp án:** Vì branch table chỉ có scale rows và mọi transaction cập nhật một branch row; scale quá nhỏ tạo hot-row contention.

### Bài 4 — Clients và threads

**Câu hỏi:** -c 64 -j 8 có nghĩa gì?

**Đáp án:** 64 client sessions được điều phối bởi 8 pgbench worker threads.

### Bài 5 — Duration

**Câu hỏi:** -T và -t khác nhau thế nào?

**Đáp án:** -T giới hạn thời gian toàn run; -t đặt số transactions mỗi client. Hai option không dùng đồng thời.

### Bài 6 — Protocol

**Câu hỏi:** Ba giá trị của -M là gì?

**Đáp án:** simple, extended và prepared.

### Bài 7 — Connection churn

**Câu hỏi:** -C dùng để đo điều gì?

**Đáp án:** Tạo kết nối mới cho mỗi transaction để đo connection overhead.

### Bài 8 — Rate control

**Câu hỏi:** -R 300 có ý nghĩa gì?

**Đáp án:** Yêu cầu pgbench nhắm tới 300 transactions/second theo lịch start rate-controlled.

### Bài 9 — Schedule lag

**Câu hỏi:** Schedule lag tăng liên tục gợi ý điều gì?

**Đáp án:** Hệ thống hoặc load generator không giữ được target arrival rate với clients/threads hiện tại.

### Bài 10 — Latency limit

**Câu hỏi:** Transaction skipped trong rate-controlled test có được gửi tới PostgreSQL không?

**Đáp án:** Không. Nó đã quá trễ theo latency limit trước khi được gửi.

### Bài 11 — TPC-B-like và SELECT-only

**Câu hỏi:** -S chạy workload nào?

**Đáp án:** Built-in select-only.

### Bài 12 — Script weight

**Câu hỏi:** Hai scripts có weights 7 và 3 có xác suất chọn tương ứng bao nhiêu?

**Đáp án:** Xấp xỉ 70% và 30% theo xác suất lựa chọn.

### Bài 13 — Uniform

**Câu hỏi:** random(1, 100) mô phỏng phân phối nào?

**Đáp án:** Uniform distribution trong khoảng từ 1 đến 100.

### Bài 14 — Zipfian

**Câu hỏi:** Khi nào nên dùng random_zipfian?

**Đáp án:** Khi một số keys/hot customers được truy cập thường xuyên hơn phần còn lại.

### Bài 15 — Working set

**Câu hỏi:** Dataset lớn hơn RAM có bảo đảm benchmark đo storage không?

**Đáp án:** Không. Access pattern phải truy cập working set rộng đủ để gây cache misses; chỉ tăng tổng table size là chưa đủ.

### Bài 16 — Warm-up

**Câu hỏi:** Vì sao cần warm-up trước measured run?

**Đáp án:** Để tách startup/cache loading khỏi steady-state performance.

### Bài 17 — Cold cache

**Câu hỏi:** Restart PostgreSQL có bảo đảm OS page cache trống không?

**Đáp án:** Không. Restart làm shared buffers trống nhưng OS page cache có thể vẫn giữ data pages.

### Bài 18 — Vacuum

**Câu hỏi:** Vì sao autovacuum có thể làm các runs khác nhau?

**Đáp án:** Nó cạnh tranh CPU/I/O và thay đổi dead tuples, bloat và cache footprint trong measured interval.

### Bài 19 — Repetition

**Câu hỏi:** Vì sao không chọn run có TPS cao nhất?

**Đáp án:** Nó có thể là outlier; báo median và độ phân tán của nhiều lần chạy.

### Bài 20 — Random seed

**Câu hỏi:** Có nên luôn dùng cùng random seed trong mọi run?

**Đáp án:** Không. Seed cố định hữu ích cho debugging/paired test, nhưng nhiều seeds cần thiết để đo variability.

### Bài 21 — Load generator

**Câu hỏi:** Server CPU thấp nhưng TPS không tăng khi thêm clients. Nên kiểm tra gì?

**Đáp án:** CPU/network/thread saturation ở máy pgbench, network RTT, connection limits và waits.

### Bài 22 — Latency

**Câu hỏi:** pgbench latency có phải chỉ là server execution time không?

**Đáp án:** Không. Nó là latency từ client, có thể bao gồm network, scheduling lag và các overhead khác.

### Bài 23 — p95/p99

**Câu hỏi:** Có thể suy ra p95/p99 từ average và standard deviation không?

**Đáp án:** Không. Cần transaction-level logs hoặc công cụ đo tail latency phù hợp.

### Bài 24 — Server metrics

**Câu hỏi:** View nào dùng để xem active sessions và wait events?

**Đáp án:** pg_stat_activity.

### Bài 25 — A/B

**Câu hỏi:** Khi so sánh index A và B, cần giữ những yếu tố nào không đổi?

**Đáp án:** Dataset, workload scripts/weights, clients/threads, protocol, duration, cache/warm-up, server/client placement và các settings ngoài index đang thử.

---

## 23. Checklist benchmark đáng tin cậy

### Trước khi chạy

1. Xác định câu hỏi và metric thành công.
2. Chọn workload sát nghiệp vụ.
3. Tạo database benchmark riêng.
4. Kiểm tra pgbench và PostgreSQL versions.
5. Ghi hardware, OS, storage, network và server settings.
6. Chọn dataset size/working set đại diện.
7. Chọn schema, indexes, constraints và data distribution phù hợp.
8. Xác nhận transaction scripts và business invariants.
9. Chọn clients, threads, protocol, rate và duration.
10. Quyết định warm-cache hay cold/first-touch test.

### Trong khi chạy

11. Chạy smoke test một client.
12. Tách setup, warm-up và measured interval.
13. Chạy ít nhất vài phút cho measured phase.
14. Lặp lại mỗi cấu hình nhiều lần.
15. Theo dõi TPS, latency, failures, retries và schedule lag.
16. Theo dõi CPU, memory, I/O, network và load generator.
17. Theo dõi waits, locks, WAL, checkpoint và autovacuum.
18. Ghi lại background events trong measured interval.
19. Không đổi nhiều biến cùng lúc.
20. Không chọn kết quả tốt nhất làm đại diện.

### Sau khi chạy

21. Lưu command line, scripts và random seeds.
22. Lưu logs và server metrics theo timestamp.
23. Tính median/range hoặc spread giữa các runs.
24. Báo p95/p99 chỉ khi đã đo từ đủ samples.
25. Đối chiếu pg_stat_statements và pg_stat_database deltas.
26. Xác định bottleneck bằng evidence từ server và OS.
27. So sánh đúng cùng workload/cache/data state.
28. Ghi rõ giới hạn và các yếu tố chưa kiểm soát được.
29. Restore/reset dataset trước vòng benchmark tiếp theo nếu workload làm data drift.
30. Dừng load generators và dọn lab sau khi hoàn tất.

---

## 24. Tổng kết

pgbench là công cụ hữu ích để đo PostgreSQL throughput, latency và behavior dưới concurrency. Built-in TPC-B-like tạo baseline nhanh, nhưng benchmark có giá trị nhất khi transaction scripts, data size, key distribution, read/write mix và connection behavior phản ánh hệ thống cần đánh giá.

Các điểm cần nhớ:

- pgbench mặc định chạy workload TPC-B-like, không phải TPC-B chính thức.
- `pgbench -i` tạo và có thể xóa các bảng pgbench có tên cố định; dùng database benchmark riêng.
- Scale factor của built-in TPC-B-like cần đủ lớn để tránh hot branch contention.
- `-c` là client sessions, `-j` là worker threads phía pgbench.
- `-T` đo theo thời gian; `-t` đo số transaction mỗi client.
- `-M` chọn simple/extended/prepared protocol; `-C` tạo connection mới cho mỗi transaction.
- `-R` điều khiển offered rate và latency báo cáo bao gồm schedule lag; `-L` có thể tạo late/skipped transactions.
- `-l` và `-r` có overhead; log/sampling cần được ghi nhận.
- Custom scripts nên mô phỏng transaction boundaries, business rules, data skew và tỷ lệ read/write thực tế.
- Warm-up, cache state, autovacuum, dead tuples, checkpoint và data growth ảnh hưởng kết quả.
- Chạy nhiều phút, lặp nhiều lần, randomize A/B order và báo median/variability.
- Theo dõi cả PostgreSQL, OS, storage, network và load generator.
- TPS cao không đủ; phải đọc latency, failures, retries, schedule lag và resource headroom.
- Dùng pg_stat_activity, pg_stat_statements, pg_stat_io và logs để giải thích bottleneck.
- So sánh A/B chỉ có ý nghĩa khi workload và điều kiện thử nghiệm tương đương.

**Câu hỏi tự kiểm tra:** Một cấu hình mới tăng TPS 12% trong run 30 giây, nhưng chỉ chạy một lần và được đo ngay sau warm-up trong khi baseline chạy từ cache lạnh. Có thể kết luận cấu hình mới tốt hơn không? Chưa. Cần lặp lại đủ dài, dùng cùng cache protocol, giữ workload/dataset/client settings như nhau, thu thập latency/failure/resource metrics và so sánh median cùng độ biến động.

### Tài liệu PostgreSQL chính thức

- [pgbench — PostgreSQL 18](https://www.postgresql.org/docs/18/pgbench.html).
- [pgbench — PostgreSQL 17](https://www.postgresql.org/docs/17/pgbench.html).
- [pgbench — PostgreSQL 16](https://www.postgresql.org/docs/16/pgbench.html).
- [pgbench — PostgreSQL 15](https://www.postgresql.org/docs/15/pgbench.html).
- [pgbench — PostgreSQL 14](https://www.postgresql.org/docs/14/pgbench.html).
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [Runtime Statistics Configuration](https://www.postgresql.org/docs/current/runtime-config-statistics.html).
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html).
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html).
