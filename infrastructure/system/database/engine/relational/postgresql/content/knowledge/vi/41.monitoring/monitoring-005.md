# pg_stat_statements và truy vấn gây tốn tài nguyên trong PostgreSQL

`pg_stat_statements` là extension thống kê hiệu năng quan trọng của PostgreSQL. Nó tổng hợp các câu SQL có cùng cấu trúc đã chuẩn hóa và lưu các chỉ số như số lần chạy, tổng thời gian thực thi, thời gian trung bình, số hàng đọc/ghi, block cache hit/read, temporary blocks, WAL và JIT. Nhờ vậy, DBA có thể tìm ra nhóm truy vấn đang tiêu thụ nhiều tài nguyên nhất trong một khoảng thời gian quan sát.

Khác với `pg_stat_activity`, vốn cho biết các backend và truy vấn đang hoạt động ngay lúc xem, `pg_stat_statements` cung cấp thống kê tích lũy cho các statement đã được thực thi. Nó giúp trả lời các câu hỏi:

- Nhóm truy vấn nào tiêu tốn tổng thời gian database nhiều nhất?
- Truy vấn nào chạy ít nhưng mỗi lần rất chậm?
- Truy vấn nào được gọi hàng triệu lần và tạo ra chi phí cộng dồn lớn?
- Query nào đọc nhiều block, tạo temporary files hoặc phát sinh nhiều WAL?
- Planning có tốn thời gian đáng kể không?
- Câu lệnh nào cần được phân tích bằng EXPLAIN để tìm nguyên nhân?

```text
                    PostgreSQL server
              +---------------------------+
              | Client SQL statements     |
              +-------------+-------------+
                            |
                            v
              +---------------------------+
              | Parse / plan / execute    |
              +-------------+-------------+
                            |
             instrumentation hooks and queryid
                            |
                            v
              +---------------------------+
              | pg_stat_statements        |
              | normalized query entries  |
              | calls / time / blocks     |
              | WAL / temp / JIT metrics  |
              +-------------+-------------+
                            |
                            v
              +---------------------------+
              | DBA analysis queries      |
              | rank / compare / explain  |
              +---------------------------+
```

Bài thuộc chương **Giám sát** của module *Database Engine Relational PostgreSQL*. Trọng tâm là bật extension đúng cách, đọc các metrics có ý nghĩa, phân loại truy vấn gây tốn tài nguyên, kết hợp thống kê tích lũy với thông tin runtime và chọn bước tối ưu tiếp theo.

Sau bài học, bạn có thể:

1. Giải thích cách `pg_stat_statements` nhóm các câu SQL bằng query identifier.
2. Cài extension và cấu hình shared preload/query ID.
3. Đọc các chỉ số planning, execution, calls, rows, buffer, temp, WAL và JIT.
4. Xếp hạng truy vấn theo tổng chi phí, độ trễ trung bình, số lần gọi và I/O.
5. Phân biệt query chậm do CPU, disk, temporary spill, WAL, planning hoặc lock wait.
6. Theo dõi hiệu năng theo database, user và queryid.
7. Hiểu giới hạn của số liệu tích lũy, reset và eviction.
8. Kết hợp `pg_stat_statements` với `pg_stat_activity`, EXPLAIN và auto_explain.
9. Nhận biết các khác biệt quan trọng giữa PostgreSQL 13–18.
10. Xây dựng quy trình giám sát và tối ưu dựa trên số liệu.

> **Phạm vi thực hành:** Các lệnh cấu hình yêu cầu quyền quản trị và restart server được minh họa cho môi trường lab. Bật tracking có overhead nhất định; hãy đo tác động trước khi áp dụng trên production. Không reset toàn bộ statistics khi chưa lưu snapshot cần thiết để so sánh.

---

## 1. pg_stat_statements giải quyết vấn đề gì?

### 1.1. Một truy vấn chậm hay một nhóm truy vấn tốn kém?

Một câu SQL mất 8 giây mỗi lần có thể đáng chú ý. Nhưng một câu SQL mất 15 ms và chạy 500.000 lần có thể tiêu thụ tổng thời gian database lớn hơn rất nhiều.

Nếu chỉ xem log slow query, ta dễ bỏ qua các câu lệnh nhanh nhưng được gọi với tần suất cao. `pg_stat_statements` gom những câu SQL tương tự thành một entry để nhìn thấy chi phí cộng dồn.

Ví dụ:

```sql
SELECT * FROM orders WHERE customer_id = 1001;
SELECT * FROM orders WHERE customer_id = 1002;
SELECT * FROM orders WHERE customer_id = 1003;
```

Khi query identifier và normalization hoạt động, các câu trên thường được gom thành một mẫu:

```sql
SELECT * FROM orders WHERE customer_id = $1;
```

Một entry có thể ghi nhận hàng nghìn hoặc hàng triệu calls của cùng cấu trúc truy vấn.

### 1.2. Thống kê tích lũy

`pg_stat_statements` lưu các bộ đếm và thời gian tích lũy kể từ khi entry được tạo hoặc reset. Nó không phải trace từng request, không lưu mọi giá trị tham số và không thay thế log truy vấn.

### 1.3. Những gì extension cho biết

- Số lần statement được thực thi.
- Tổng, trung bình, nhỏ nhất, lớn nhất và độ lệch chuẩn của execution time.
- Planning time nếu bật tracking planning.
- Tổng số rows trả về hoặc bị tác động.
- Shared/local/temp blocks được hit, read, dirtied hoặc written.
- Thời gian I/O nếu bật `track_io_timing`.
- WAL records, full-page images và WAL bytes.
- JIT compilation metrics.
- Một số metrics parallel worker ở phiên bản mới.

### 1.4. Những gì extension không cho biết trực tiếp

`pg_stat_statements` không cung cấp:

- Execution plan đầy đủ của từng lần chạy.
- Giá trị bind parameter của mọi invocation.
- Thời điểm chính xác của từng lần thực thi.
- Wait event chi tiết của từng call đã hoàn tất.
- Lock graph của truy vấn.
- Độ trễ end-to-end ở application, network hoặc connection pool.

Muốn tìm nguyên nhân cụ thể, cần kết hợp các công cụ khác như EXPLAIN, `pg_stat_activity`, PostgreSQL logs và metrics ở tầng OS/application.

---

## 2. Cách pg_stat_statements ghi nhận truy vấn

### 2.1. Query identifier

PostgreSQL tính `queryid` từ biểu diễn truy vấn sau parse analysis. Các câu lệnh khác nhau ở literal constants thường có thể được xem là cùng cấu trúc.

Ví dụ:

```sql
SELECT * FROM products WHERE product_id = 10;
SELECT * FROM products WHERE product_id = 20;
```

Thường được gom vào cùng một entry:

```sql
SELECT * FROM products WHERE product_id = $1;
```

### 2.2. Một entry được xác định bởi những gì?

Trong các phiên bản hiện đại, một row của view được xác định theo tổ hợp:

- `userid`: OID của role thực thi.
- `dbid`: OID của database.
- `queryid`: hash của cấu trúc truy vấn.
- `toplevel`: truy vấn top-level hay nested statement.

Vì vậy, cùng một SQL chạy bởi hai user hoặc ở hai database có thể xuất hiện thành hai entries.

### 2.3. Query text là đại diện, không phải log từng câu lệnh

Cột `query` chứa text đại diện cho cấu trúc truy vấn. Literal constants thường được thay bằng tham số như `$1`, `$2`. Text hiển thị thường là câu đầu tiên được ghi nhận cho entry đó.

Do đó:

- Không dùng cột query để khôi phục chính xác input của từng request.
- Không suy ra mọi invocation dùng cùng một giá trị parameter.
- Không coi query text là lịch sử đầy đủ của SQL.

### 2.4. Queryid không phải ID ổn định vĩnh viễn

`queryid` hữu ích để nhận diện query trong một môi trường cụ thể, nhưng không được bảo đảm ổn định giữa major versions. Nó còn phụ thuộc parse tree, object identifiers, search_path, machine architecture và các yếu tố build/platform.

Khi so sánh nhiều server:

- Không mặc định queryid giống nhau trên các logical replicas.
- Không ghép thống kê qua các major versions chỉ bằng queryid.
- Có thể cần kết hợp database, user, query text đã chuẩn hóa và metadata ứng dụng.
- Hai truy vấn nhìn giống nhau vẫn có thể thành entries khác nếu parse semantics khác.

### 2.5. Hash collision

Có xác suất nhỏ hai cấu trúc truy vấn không liên quan bị hash collision và cùng entry. Đây là khả năng hiếm; queryid vẫn là cách nhóm truy vấn thực tế hữu ích, nhưng không phải khóa duy nhất có bảo đảm toán học tuyệt đối.

### 2.6. IN lists

Các truy vấn chỉ khác nhau về số phần tử trong danh sách constants có thể được gom vào một entry. Text đại diện có thể hiển thị dạng:

```sql
SELECT * FROM events
WHERE event_id IN ($1 /*, ... */);
```

Điều này giúp giảm số entries nhưng cũng có nghĩa một entry có thể đại diện cho nhiều kích thước danh sách khác nhau.

### 2.7. Nested statements

Tham số:

```conf
pg_stat_statements.track = top
```

`top` chỉ ghi statement do client gửi trực tiếp. Đặt thành `all` để ghi cả nested statements, ví dụ SQL được gọi bên trong function hoặc trigger.

Khi dùng `all`, có thể nhìn thấy cả statement ngoài và các statement bên trong. Không cộng tổng thời gian của tất cả entries như thể chúng là những phần độc lập, vì chi phí có thể bị tính ở nhiều cấp lồng nhau.

### 2.8. Utility statements

`pg_stat_statements.track_utility` điều khiển việc theo dõi utility commands, ví dụ một số lệnh DDL, maintenance và lệnh quản trị. Mặc định là `on`.

Nếu tắt, view vẫn theo dõi các statement SQL thông thường nhưng không thu thập utility commands theo phạm vi của tham số này.

---

## 3. Cài đặt pg_stat_statements

### 3.1. Extension thường đi cùng PostgreSQL contrib

Trên nhiều hệ điều hành, `pg_stat_statements` được cung cấp trong gói contrib/additional modules của PostgreSQL. Cần cài package tương ứng với major version đang chạy.

Tên package khác nhau theo distro và cách cài PostgreSQL. Nếu server báo không tìm thấy control file hoặc shared library, kiểm tra gói extension cho đúng major version.

### 3.2. Thêm vào shared_preload_libraries

Mở `postgresql.conf` trên server:

```conf
shared_preload_libraries = 'pg_stat_statements'
```

Nếu đã có các module khác trong `shared_preload_libraries`, giữ lại và thêm extension mới vào danh sách, ví dụ:

```conf
shared_preload_libraries = 'pg_stat_statements,auto_explain'
```

Không ghi đè các preload modules đang được ứng dụng/hạ tầng sử dụng.

### 3.3. Bật query identifier

Trong PostgreSQL hiện đại:

```conf
compute_query_id = auto
```

Hoặc:

```conf
compute_query_id = on
```

`pg_stat_statements` cần query identifier để nhóm các câu SQL. Nếu dùng module bên thứ ba để tính queryid, phải theo hướng dẫn của module đó và tránh để nhiều thành phần cùng tính queryid không tương thích.

### 3.4. Cấu hình tracking cơ bản

Ví dụ:

```conf
pg_stat_statements.max = 10000
pg_stat_statements.track = top
pg_stat_statements.track_utility = on
pg_stat_statements.track_planning = off
pg_stat_statements.save = on
```

Ý nghĩa:

| Tham số | Mục đích |
|---|---|
| `max` | Số entries tối đa được theo dõi |
| `track` | Chọn top-level, all hoặc none |
| `track_utility` | Có ghi utility statements hay không |
| `track_planning` | Có ghi planning time hay không |
| `save` | Có lưu statistics qua shutdown/restart hay không |

### 3.5. Khởi động lại server

Vì extension cần shared memory được cấp lúc server start, thêm hoặc bỏ `pg_stat_statements` trong `shared_preload_libraries` yêu cầu restart PostgreSQL. Reload config không đủ.

Sau restart, xác nhận:

```sql
SHOW shared_preload_libraries;
SHOW compute_query_id;
SHOW pg_stat_statements.max;
SHOW pg_stat_statements.track;
```

### 3.6. CREATE EXTENSION trong database

Kết nối vào từng database nơi muốn truy vấn view:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Điểm cần phân biệt:

- Module được preload ở cấp server.
- Statistics được thu thập trên toàn server, qua các databases.
- View và các hàm SQL được cài vào từng database bằng `CREATE EXTENSION`.

Nếu DBA chỉ tạo extension trong database `postgres`, view không tự xuất hiện trong database `appdb`. Muốn query view tại `appdb`, cần tạo extension ở đó.

### 3.7. Xác nhận extension

```sql
SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname = 'pg_stat_statements';
```

Trong psql:

```text
\dx pg_stat_statements
\d+ pg_stat_statements
```

`extversion` cho biết SQL extension version đang cài trong database. Nó không phải PostgreSQL server major version.

### 3.8. Nâng cấp extension

Sau khi nâng package PostgreSQL hoặc cài extension version mới, kiểm tra extension version và update theo hướng dẫn:

```sql
ALTER EXTENSION pg_stat_statements UPDATE;
```

Không giả định nâng binary package tự động cập nhật metadata/schema của extension trong mọi database.

---

## 4. Các tham số cấu hình quan trọng

### 4.1. pg_stat_statements.max

`pg_stat_statements.max` đặt số lượng entries tối đa. Mặc định thường là 5000. Khi có nhiều query structures hơn giới hạn, extension loại bỏ các entries ít được thực thi nhất để dành chỗ cho entries mới.

Giá trị lớn hơn:

- Giữ được nhiều query patterns hơn.
- Giảm nguy cơ mất thống kê của statement ít gặp.
- Tăng nhu cầu shared memory.

Tham số này chỉ có hiệu lực khi server start, nên thay đổi cần restart.

### 4.2. Theo dõi deallocations

View `pg_stat_statements_info` có bộ đếm `dealloc`, cho biết số lần entries bị loại bỏ vì vượt giới hạn `pg_stat_statements.max`.

```sql
SELECT
    dealloc,
    stats_reset
FROM pg_stat_statements_info;
```

Nếu `dealloc` tăng nhanh trong một khoảng quan sát, có thể `max` quá nhỏ so với số query patterns. Trước khi tăng, xem xét lượng shared memory và tính cần thiết của `track = all`.

### 4.3. pg_stat_statements.track

Ba giá trị:

| Giá trị | Ý nghĩa |
|---|---|
| `top` | Chỉ câu lệnh top-level từ client; mặc định |
| `all` | Ghi cả nested statements trong functions/triggers |
| `none` | Tắt thu thập statement statistics |

`all` giúp tìm SQL nội bộ trong stored procedures nhưng có thể tạo nhiều entries và làm số liệu parent/child chồng lấp.

### 4.4. pg_stat_statements.track_utility

Mặc định `on`. Tắt khi chỉ quan tâm truy vấn SQL thông thường và muốn giảm lượng utility statements được ghi.

Utility commands không chỉ là DDL; tham số định nghĩa chúng là các lệnh ngoài nhóm SELECT, INSERT, UPDATE, DELETE và MERGE. Danh sách cụ thể phụ thuộc loại lệnh/version.

### 4.5. pg_stat_statements.track_planning

Mặc định `off`. Khi bật, extension ghi:

- Số lần planning.
- Tổng planning time.
- Min/max/mean/stddev planning time.

Planning tracking có thể tạo overhead đáng kể khi nhiều connections đồng thời chạy cùng query structure và cùng cập nhật một entry. Bật khi cần điều tra planning bottleneck, đo tác động và cân nhắc tắt sau khi thu thập đủ dữ liệu.

Tham số này được bổ sung từ PostgreSQL 13. Mặc định `off` được chọn để tránh regression hiệu năng trong workload concurrent.

### 4.6. pg_stat_statements.save

Mặc định `on`. Khi bật, statistics được lưu qua shutdown/restart theo cơ chế của extension. Nếu tắt, statistics không được lưu khi shutdown và không được nạp lại khi server khởi động.

Tham số này cấu hình trong `postgresql.conf` hoặc command line.

### 4.7. track_io_timing

Các cột I/O time trong `pg_stat_statements` chỉ có ý nghĩa khi `track_io_timing` được bật:

```conf
track_io_timing = on
```

Thời gian I/O giúp nhận biết truy vấn đang chờ đọc/ghi data blocks hay temp files. Đo timing có thể tạo overhead tùy OS/storage; hãy kiểm tra bằng `pg_test_timing` và đo trong môi trường tương tự production.

### 4.8. compute_query_id

Trong PostgreSQL hiện đại, `compute_query_id = auto` thường tự được kích hoạt khi module cần query identifier được preload. Có thể đặt `on` tường minh nếu muốn.

Nếu query ID bị tắt hoặc một module ngoài chịu trách nhiệm tính ID, hành vi sẽ phụ thuộc cấu hình và module đó. Xác nhận `queryid` có giá trị trong view.

### 4.9. Quyền thay đổi cấu hình

Nhiều tham số tracking chỉ superuser mới thay đổi được. Các tham số yêu cầu restart cần quyền sửa server config và quyền quản trị service. Trong managed PostgreSQL, có thể cần parameter group/extension allowlist và maintenance restart.

---

## 5. Đọc cấu trúc view pg_stat_statements

### 5.1. Nhóm cột định danh

| Cột | Ý nghĩa |
|---|---|
| userid | OID của role chạy statement |
| dbid | OID của database |
| queryid | Hash identifier của query structure |
| toplevel | Statement top-level hay nested, ở các version có cột này |
| query | Text đại diện đã chuẩn hóa |

Khi báo cáo cho nhiều database hoặc user, nên hiển thị tên thay vì chỉ OID:

```sql
SELECT
    d.datname,
    r.rolname,
    s.queryid,
    s.calls,
    s.total_exec_time,
    s.query
FROM pg_stat_statements AS s
LEFT JOIN pg_database AS d ON d.oid = s.dbid
LEFT JOIN pg_roles AS r ON r.oid = s.userid
ORDER BY s.total_exec_time DESC
LIMIT 20;
```

### 5.2. Planning metrics

| Cột | Ý nghĩa |
|---|---|
| plans | Số lần statement được plan |
| total_plan_time | Tổng thời gian planning, ms |
| mean_plan_time | Planning time trung bình, ms |
| min_plan_time / max_plan_time | Planning nhanh nhất/chậm nhất |
| stddev_plan_time | Độ lệch chuẩn planning time |

Các cột này bằng 0 nếu track_planning tắt. plans không nhất thiết bằng calls: query có thể được plan nhưng execution thất bại, hoặc execution dùng cached plan nên không tạo planning event tương ứng.

### 5.3. Execution metrics

| Cột | Ý nghĩa |
|---|---|
| calls | Số lần statement thực thi |
| total_exec_time | Tổng execution time, ms |
| mean_exec_time | Thời gian trung bình, ms |
| min_exec_time / max_exec_time | Nhanh nhất/chậm nhất, ms |
| stddev_exec_time | Độ lệch chuẩn execution time |
| rows | Tổng số rows trả về hoặc bị tác động |

Thời gian là milliseconds. Tổng execution time là tổng chi phí của tất cả calls được ghi nhận; khi nhiều query chạy đồng thời, tổng này có thể lớn hơn thời gian đồng hồ thực tế đã trôi qua.

### 5.4. Shared blocks

| Cột | Ý nghĩa |
|---|---|
| shared_blks_hit | Block tìm thấy trong PostgreSQL shared buffers |
| shared_blks_read | Block phải đọc vào shared buffers |
| shared_blks_dirtied | Block được làm dirty bởi statement |
| shared_blks_written | Block được ghi ra bởi statement |

Block là đơn vị page của PostgreSQL; kích thước phổ biến là 8 KB nhưng cần kiểm tra block_size của cluster.

```sql
SHOW block_size;
```

shared_blks_read không có nghĩa chắc chắn là đọc từ đĩa vật lý: block có thể đã có trong OS page cache. Nó cho biết PostgreSQL phải nạp block vào shared buffers.

### 5.5. Local blocks

Các cột local_blks_hit, local_blks_read, local_blks_dirtied, local_blks_written phản ánh hoạt động trên local buffers, thường liên quan tới temporary tables.

Đây là nhóm khác với temp_blks_*, vốn phản ánh temporary files được tạo khi các thao tác như sort/hash spill ra disk.

### 5.6. Temporary blocks

| Cột | Ý nghĩa |
|---|---|
| temp_blks_read | Số temporary blocks đã đọc |
| temp_blks_written | Số temporary blocks đã ghi |
| temp_blk_read_time | Thời gian đọc temporary blocks nếu có I/O timing |
| temp_blk_write_time | Thời gian ghi temporary blocks nếu có I/O timing |

Temporary blocks cao có thể gợi ý sort/hash không vừa memory, query xử lý lượng dữ liệu lớn hoặc cấu hình work_mem chưa phù hợp. Không tăng work_mem toàn hệ thống ngay lập tức; một backend có thể dùng nhiều memory operations và nhiều sessions đồng thời có thể làm tổng memory tăng mạnh.

### 5.7. I/O timing

Trong các phiên bản cũ hơn, view dùng blk_read_time và blk_write_time. PostgreSQL 18 tách thời gian đọc/ghi thành shared, local và temp block times, ví dụ shared_blk_read_time, local_blk_read_time, temp_blk_read_time.

Các trường timing chỉ có ý nghĩa khi track_io_timing được bật. Nếu không bật, chúng trả 0 và không thể dùng để kết luận query không tốn thời gian I/O.

### 5.8. WAL metrics

| Cột | Ý nghĩa |
|---|---|
| wal_records | Số WAL records do statement tạo |
| wal_fpi | Số full-page images tạo ra |
| wal_bytes | Tổng bytes WAL |
| wal_buffers_full | Số lần WAL buffers bị đầy; có trong phiên bản mới |

WAL lớn có thể đến từ bulk UPDATE/DELETE/INSERT, index maintenance, full-page images hoặc các thao tác ghi lớn. Nó ảnh hưởng WAL volume, archiving, replication và recovery time.

### 5.9. JIT metrics

Các cột jit_* ghi số hàm được JIT compile và thời gian generation, inlining, optimization, emission hoặc deform.

Nếu query chạy ngắn nhưng tốn nhiều thời gian compile JIT, chi phí compilation có thể vượt lợi ích tối ưu execution. So sánh JIT metrics với total execution time và thử nghiệm SET jit = off trong session lab để đánh giá, không thay đổi global setting theo phỏng đoán.

### 5.10. Parallel worker metrics ở PostgreSQL 18

PostgreSQL 18 bổ sung:

- parallel_workers_to_launch: số worker được plan yêu cầu.
- parallel_workers_launched: số worker thực tế được khởi chạy.

Chênh lệch lớn có thể cho thấy worker không được cấp đủ do giới hạn tài nguyên hoặc cạnh tranh. Không phải query nào cũng dùng parallelism; kiểm tra execution plan.

### 5.11. Timestamps ở PostgreSQL 18

PostgreSQL 18 có stats_since và minmax_stats_since:

- stats_since: thời điểm bắt đầu thu thập stats cho entry.
- minmax_stats_since: thời điểm bắt đầu cửa sổ thống kê min/max.

Các cột này hữu ích khi đọc min/max sau một lần reset chọn lọc.

---

## 6. Phiên bản PostgreSQL và khác biệt schema

### 6.1. Không giả định view có cùng cột ở mọi major

Schema pg_stat_statements đã phát triển theo major releases. Một query monitoring viết cho PostgreSQL 18 có thể lỗi trên PostgreSQL 13/14 nếu tham chiếu cột chưa tồn tại.

Luôn kiểm tra view thật:

```sql
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'pg_stat_statements'
ORDER BY ordinal_position;
```

Tên schema của extension phụ thuộc nơi extension được cài; có thể dùng lệnh sau trong psql để xem trực tiếp:

```text
\d+ pg_stat_statements
```

### 6.2. Những mốc đáng chú ý

| Version | Điểm cần nhớ |
|---|---|
| PostgreSQL 13 | track_planning và planning metrics đã có; mặc định track_planning là off |
| PostgreSQL 14 | Có view pg_stat_statements_info và cột dealloc/stats_reset |
| PostgreSQL 15–17 | Có các execution, planning, block, I/O, WAL và JIT metrics theo schema từng version |
| PostgreSQL 18 | Bổ sung các trường parallel worker, stats_since, minmax_stats_since, tách I/O timing chi tiết hơn và thêm WAL buffer metric |

### 6.3. Thay đổi tên I/O timing

PostgreSQL 13–17 sử dụng blk_read_time và blk_write_time cho block I/O timing (cùng temp timing trong các version có hỗ trợ). PostgreSQL 18 phân tách shared/local/temp:

- shared_blk_read_time
- shared_blk_write_time
- local_blk_read_time
- local_blk_write_time
- temp_blk_read_time
- temp_blk_write_time

Nếu viết dashboard hỗ trợ nhiều major versions, dùng version-specific query hoặc kiểm tra schema trước khi tham chiếu cột.

### 6.4. pg_stat_statements_info

View này có từ PostgreSQL 14. PostgreSQL 13 không có view này trong extension version đi kèm server 13.

```sql
SELECT *
FROM pg_stat_statements_info;
```

Không chạy query trên view này trên PostgreSQL 13 nếu chưa kiểm tra version.

### 6.5. pg_stat_statements_reset signature

Các phiên bản cũ dùng overload nhận userid, dbid, queryid. Các phiên bản hiện đại bổ sung tham số minmax_only và trả timestamp reset. Cú pháp đơn giản:

```sql
SELECT pg_stat_statements_reset();
```

được hỗ trợ để reset toàn bộ stats ở các phiên bản hiện đại. Khi viết automation đa version, kiểm tra function signature bằng lệnh sau trong psql:

```text
\df pg_stat_statements_reset
```

### 6.6. Extension version và server version

PostgreSQL major version và extversion của extension là hai thông tin khác nhau. Sau khi nâng server, kiểm tra extension update scripts và cập nhật trong từng database theo hướng dẫn của package/version.

---

## 7. Tìm truy vấn tốn tổng thời gian nhiều nhất

### 7.1. Xếp hạng theo total_exec_time

Đây là truy vấn đầu tiên nên chạy khi muốn biết query groups nào chiếm nhiều execution time nhất:

```sql
SELECT
    d.datname,
    r.rolname,
    s.queryid,
    s.calls,
    round(s.total_exec_time::numeric, 2) AS total_exec_ms,
    round(s.mean_exec_time::numeric, 2) AS mean_exec_ms,
    s.rows,
    s.shared_blks_read,
    s.temp_blks_written,
    left(s.query, 500) AS query_sample
FROM pg_stat_statements AS s
LEFT JOIN pg_database AS d ON d.oid = s.dbid
LEFT JOIN pg_roles AS r ON r.oid = s.userid
WHERE s.toplevel
ORDER BY s.total_exec_time DESC
LIMIT 20;
```

Nếu phiên bản không có cột toplevel, bỏ điều kiện đó.

### 7.2. Chỉ xem một database

```sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    rows,
    left(query, 500) AS query_sample
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database
              WHERE datname = current_database())
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 7.3. Vì sao total time quan trọng?

Ví dụ:

| Query | Calls | Mean time | Total time |
|---|---:|---:|---:|
| A | 2.000.000 | 4 ms | 8.000.000 ms |
| B | 50 | 2.000 ms | 100.000 ms |

Query B chậm hơn nhiều trên từng call, nhưng query A tiêu thụ tổng execution time lớn hơn 80 lần. Nếu mục tiêu là giảm tổng tải database, query A có thể là nơi ưu tiên trước.

### 7.4. Tổng thời gian không phải wall-clock time của server

total_exec_time cộng thời gian của từng invocation. Nhiều query chạy song song/concurrent có thể làm tổng thời gian vượt thời gian đồng hồ. Không dùng tổng của mọi entries để suy ra server đã chạy lâu bao nhiêu phút.

### 7.5. Không chỉ nhìn top 1

Một query đứng đầu có thể là batch job hợp lệ. Xem top 20, so sánh calls, rows, user/database và thời gian quan sát để hiểu nguồn tải.

---

## 8. Tìm truy vấn có độ trễ trung bình cao

### 8.1. Xếp hạng mean execution time

```sql
SELECT
    queryid,
    calls,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    round(max_exec_time::numeric, 2) AS max_exec_ms,
    round(stddev_exec_time::numeric, 2) AS stddev_exec_ms,
    rows,
    left(query, 500) AS query_sample
FROM pg_stat_statements
WHERE calls >= 10
ORDER BY mean_exec_time DESC
LIMIT 20;
```

Ngưỡng calls giúp tránh xếp hạng một query mới chạy một lần rồi coi nó là đại diện cho workload dài hạn. Chọn ngưỡng theo hệ thống.

### 8.2. Mean cao và calls thấp

Có thể là:

- Báo cáo hiếm chạy nhưng xử lý dữ liệu lớn.
- Query chạy theo lịch.
- Truy vấn có plan xấu cho một số parameter.
- Truy vấn bị block hoặc phụ thuộc storage.

### 8.3. Mean thấp và calls rất cao

Một query 2 ms chạy 300.000 lần mỗi phút vẫn có thể tạo tải CPU và connection overhead đáng kể. Tối ưu giảm số lần gọi, batch requests hoặc cache ở application có thể hiệu quả hơn chỉ chỉnh execution plan.

### 8.4. Max và standard deviation

max_exec_time giúp phát hiện outlier; stddev_exec_time cho thấy độ biến động. Một query mean thấp nhưng max rất cao có thể phụ thuộc parameter, cache state, lock waits hoặc data skew.

### 8.5. Lưu ý min/max sau reset

Khi dùng reset chọn lọc minmax_only, min/max có thể bằng 0 cho tới khi query chạy lại. PostgreSQL 18 có minmax_stats_since để biết cửa sổ min/max bắt đầu lúc nào.

---

## 9. Tìm truy vấn đọc nhiều block và gây áp lực I/O

### 9.1. Xếp hạng theo shared blocks read

```sql
SELECT
    queryid,
    calls,
    shared_blks_hit,
    shared_blks_read,
    round(
        100.0 * shared_blks_hit /
        NULLIF(shared_blks_hit + shared_blks_read, 0),
        2
    ) AS shared_hit_pct,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    left(query, 400) AS query_sample
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 20;
```

### 9.2. Cache hit ratio không phải thước đo duy nhất

Một query có shared hit ratio 99.9% vẫn có thể gây tải lớn nếu nó scan hàng tỷ blocks từ shared buffers. Ngược lại, một query có hit ratio thấp nhưng chạy hiếm và đọc ít block có thể không đáng ưu tiên.

Đánh giá cùng lúc:

- Tổng blocks hit và read.
- Calls và mean execution time.
- Total execution time.
- I/O timing.
- Kích thước bảng/index và workload đồng thời.

### 9.3. Chuyển block thành bytes

```sql
SELECT
    queryid,
    calls,
    shared_blks_read,
    shared_blks_read *
        current_setting('block_size')::bigint AS shared_read_bytes,
    temp_blks_written,
    temp_blks_written *
        current_setting('block_size')::bigint AS temp_write_bytes,
    left(query, 300) AS query_sample
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 20;
```

Đây là bytes theo block accounting, không phải phép đo chính xác số bytes vật lý đi qua storage device. OS cache, read-ahead và storage layer có thể thay đổi lượng I/O vật lý.

### 9.4. Đọc và ghi block

Query có shared_blks_read lớn có thể scan nhiều dữ liệu hoặc truy cập working set không nằm trong shared buffers. shared_blks_dirtied/written cao thường liên quan tới workload ghi hoặc dirty buffers.

Không kết luận một query là disk bound chỉ từ shared_blks_read. Cần xem I/O time và OS storage metrics.

### 9.5. I/O timing theo query

Khi track_io_timing được bật, PostgreSQL ghi thời gian I/O. Trên PostgreSQL 13–17:

```sql
SELECT
    queryid,
    calls,
    round(blk_read_time::numeric, 2) AS read_ms,
    round(blk_write_time::numeric, 2) AS write_ms,
    round(total_exec_time::numeric, 2) AS exec_ms,
    left(query, 300) AS query_sample
FROM pg_stat_statements
ORDER BY blk_read_time + blk_write_time DESC
LIMIT 20;
```

Trên PostgreSQL 18, thay các cột block timing bằng shared/local/temp block time phù hợp, ví dụ shared_blk_read_time và temp_blk_write_time.

### 9.6. Đọc I/O time cẩn thận

I/O timing cộng thời gian chờ block I/O được đo bởi PostgreSQL. Nó không phải CPU time. Query có total_exec_time cao nhưng I/O time thấp có thể đang tiêu tốn CPU, planning, lock wait hoặc làm nhiều công việc trong memory.

### 9.7. Local buffers và temporary files

Local blocks thường liên quan temporary tables; temp blocks phản ánh temporary files được dùng bởi executor. Nếu temp blocks tăng mạnh, xem sort/hash nodes trong EXPLAIN và log_temp_files để xác định thao tác spill.

---

## 10. Tìm truy vấn tạo nhiều temporary blocks

### 10.1. Xếp hạng theo temp blocks

```sql
SELECT
    queryid,
    calls,
    temp_blks_read,
    temp_blks_written,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    left(query, 500) AS query_sample
FROM pg_stat_statements
WHERE temp_blks_read > 0
   OR temp_blks_written > 0
ORDER BY temp_blks_written + temp_blks_read DESC
LIMIT 20;
```

### 10.2. Nguyên nhân thường gặp

- ORDER BY hoặc DISTINCT sort lượng rows lớn.
- Hash join/hash aggregate vượt memory budget.
- Window functions xử lý partition lớn.
- Materialize/CTE hoặc intermediate results lớn.
- Query thiếu điều kiện lọc nên xử lý nhiều dữ liệu.
- work_mem quá thấp cho một operation cụ thể.

### 10.3. work_mem là giới hạn theo operation

work_mem không phải tổng memory cấp cho một backend. Một query có thể chạy nhiều sort/hash operations, và nhiều sessions chạy cùng lúc. Tăng work_mem toàn cục quá cao có thể làm memory consumption tăng theo số connections và operations.

### 10.4. Chọn cách xử lý

Trước khi tăng work_mem:

1. Xem EXPLAIN (ANALYZE, BUFFERS).
2. Kiểm tra estimate rows và actual rows.
3. Xác định node nào spill.
4. Xem query có thể giảm rows sớm hơn không.
5. Kiểm tra index, join order, sort keys và statistics.
6. Thử work_mem theo session/transaction trong lab.

### 10.5. Log temporary files

Có thể dùng:

```conf
log_temp_files = 0
```

Giá trị 0 ghi mọi temporary file; giá trị dương chỉ ghi file lớn hơn ngưỡng KB. Logging có thể tạo nhiều log, nên đặt ngưỡng hợp lý và giới hạn thời gian điều tra.

### 10.6. Temporary bytes ở database level

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

Đây là số liệu database-level, hữu ích để xác định database nào tạo temp files nhiều. Dùng pg_stat_statements để tìm query groups liên quan.

---

## 11. Tìm truy vấn tạo nhiều WAL

### 11.1. Xếp hạng theo wal_bytes

```sql
SELECT
    queryid,
    calls,
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_generated,
    round(
        wal_bytes / NULLIF(calls, 0) / 1024.0,
        2
    ) AS wal_kb_per_call,
    left(query, 400) AS query_sample
FROM pg_stat_statements
ORDER BY wal_bytes DESC
LIMIT 20;
```

### 11.2. Vì sao WAL lớn?

- INSERT/UPDATE/DELETE số lượng lớn.
- Cập nhật nhiều indexes.
- Bulk load hoặc maintenance.
- Full-page images sau checkpoint theo workload.
- Nhiều thay đổi trên các bảng/index lớn.

### 11.3. wal_records và wal_fpi

wal_records là số WAL records do statement tạo. wal_fpi là số full-page images. FPI giúp bảo vệ page sau checkpoint trong một số điều kiện; tỷ lệ FPI cao có thể làm WAL volume tăng.

### 11.4. Hệ quả của WAL volume

WAL lớn có thể làm:

- WAL archiving tốn băng thông/dung lượng.
- Replication lag tăng nếu standby không theo kịp.
- Backup/PITR cần nhiều storage hơn.
- Checkpoint và storage write pressure tăng.

### 11.5. Không dùng WAL bytes như số bytes ghi đĩa

wal_bytes đo WAL được tạo bởi statement, không phải số bytes ghi thực tế xuống storage. WAL compression, full-page writes, batching và storage behavior ảnh hưởng lượng I/O thực tế.

### 11.6. Chẩn đoán workload ghi

Kết hợp:

- Query groups có wal_bytes cao.
- Calls và rows.
- Indexes của bảng bị tác động.
- Autovacuum/dead tuples.
- Replication lag và archive throughput.
- Checkpoint/WAL metrics ở server.

Không tối ưu bằng cách bỏ index hoặc giảm durability setting khi chưa đánh giá correctness và recovery requirements.

---

## 12. Tìm planning overhead và JIT overhead

### 12.1. Planning time cao

Nếu track_planning đã bật, xếp hạng theo total_plan_time:

```sql
SELECT
    queryid,
    plans,
    calls,
    round(total_plan_time::numeric, 2) AS total_plan_ms,
    round(mean_plan_time::numeric, 2) AS mean_plan_ms,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    left(query, 400) AS query_sample
FROM pg_stat_statements
WHERE plans > 0
ORDER BY total_plan_time DESC
LIMIT 20;
```

### 12.2. Vì sao planning tốn thời gian?

- Query có nhiều joins/tables và nhiều phương án join order.
- Partitioned table có rất nhiều partitions.
- Query dynamic tạo cấu trúc phức tạp.
- Statistics không tốt khiến planner phải đánh giá nhiều phương án hoặc chọn plan không phù hợp.
- Prepared statements/custom plans tạo pattern planning khác nhau.

### 12.3. Plans không bằng calls

Planning và execution counters được cập nhật ở các giai đoạn khác nhau:

- Statement plan thành công nhưng execution lỗi: plans có thể tăng mà calls không tăng tương ứng.
- Cached plan được dùng: calls có thể tăng nhưng plans không tăng.
- Một số statement chỉ được parse/plan theo cách đặc thù.

Không coi chênh lệch plans/calls là bug.

### 12.4. JIT

Nếu JIT metrics lớn so với total execution time, compilation có thể là một phần đáng kể của latency. Dùng EXPLAIN để xem JIT details và thử bật/tắt JIT ở session lab để so sánh cùng query/parameter/data.

### 12.5. Không bật track_planning vô điều kiện

Vì planning tracking có thể gây contention trên entries khi workload concurrent, chỉ bật khi cần tìm planning bottleneck. Thu thập đủ dữ liệu rồi đánh giá tác động và quyết định giữ hay tắt.

---

## 13. Kết hợp pg_stat_statements với pg_stat_activity

### 13.1. Hai view phục vụ hai câu hỏi khác nhau

| View | Trả lời câu hỏi |
|---|---|
| pg_stat_statements | Nhóm query nào đã tiêu tốn tài nguyên tích lũy? |
| pg_stat_activity | Backend nào đang chạy/chờ ngay lúc này? |

Một query đang chạy lâu có thể chưa cập nhật execution statistics cho tới khi invocation kết thúc. Vì vậy, khi điều tra sự cố đang xảy ra, hãy xem pg_stat_activity trước.

### 13.2. Xem các truy vấn đang hoạt động

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    now() - query_start AS query_age,
    query_id,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start NULLS LAST;
```

Trường query_id có trên các phiên bản hiện đại khi query identifier được tính. Nếu version không có cột này, bỏ nó khỏi truy vấn.

### 13.3. Tìm lock blockers

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.usename AS waiting_user,
    waiting.datname,
    waiting.wait_event_type,
    waiting.wait_event,
    now() - waiting.query_start AS waiting_age,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    left(blocker.query, 300) AS blocker_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS b(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = b.pid
ORDER BY waiting.query_start;
```

Nếu một query có mean execution time cao, nguyên nhân có thể là lock waits chứ không phải plan hoặc I/O. Kết hợp wait_event và blocker để phân loại.

### 13.4. Liên kết active query với thống kê tích lũy

Trên PostgreSQL có query_id và cột toplevel:

```sql
SELECT
    a.pid,
    a.usename,
    a.datname,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_id,
    s.calls,
    round(s.mean_exec_time::numeric, 2) AS mean_exec_ms,
    round(s.total_exec_time::numeric, 2) AS total_exec_ms,
    left(a.query, 300) AS active_query
FROM pg_stat_activity AS a
LEFT JOIN pg_stat_statements AS s
  ON s.queryid = a.query_id
 AND s.userid = a.usesysid
 AND s.dbid = (SELECT oid FROM pg_database
               WHERE datname = a.datname)
 AND s.toplevel
WHERE a.state = 'active'
ORDER BY a.query_start;
```

Join này mang tính chẩn đoán. Entry thống kê là số liệu tích lũy từ các lần chạy đã ghi nhận; nó không phải thời gian của invocation đang hoạt động hiện tại.

### 13.5. Query age không đồng nghĩa execution CPU time

now() - query_start là thời gian từ lúc query bắt đầu. Nó có thể bao gồm lock waits, I/O waits và thời gian chờ khác. Nếu backend ở idle in transaction, query_start cũng không phải thời gian transaction đang mở.

### 13.6. Xem transaction mở lâu

```sql
SELECT
    pid,
    usename,
    datname,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Transaction lâu có thể giữ locks, snapshot và dead tuples. Đây là một hướng điều tra khác với truy vấn có total_exec_time cao.

---

## 14. Dùng EXPLAIN để tìm nguyên nhân

### 14.1. pg_stat_statements tìm mục tiêu, EXPLAIN tìm nguyên nhân

`pg_stat_statements` cho biết query pattern nào đáng điều tra. EXPLAIN cho biết PostgreSQL dự định thực thi query bằng plan nào.

Ví dụ:

```sql
EXPLAIN
SELECT *
FROM sales.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

### 14.2. EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, VERBOSE)
SELECT *
FROM sales.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

EXPLAIN ANALYZE thực sự chạy statement. Với SELECT, nó thực thi truy vấn và báo actual rows/time. Với INSERT/UPDATE/DELETE, nó thực sự thay đổi dữ liệu.

### 14.3. DML và rollback trong lab

Trong lab, có thể bọc DML test trong transaction rồi rollback:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE sales.orders
SET status = 'archived'
WHERE created_at < DATE '2024-01-01';

ROLLBACK;
```

Rollback không hoàn tác mọi side effects bên ngoài transaction, ví dụ sequence values đã tiêu thụ hoặc tác động external từ trigger gọi hệ thống khác. Chỉ thử trên dữ liệu an toàn.

### 14.4. Đọc actual rows và estimated rows

So sánh estimated rows với actual rows:

- Estimate thấp hơn nhiều: planner có thể chọn nested loop hoặc plan không phù hợp.
- Estimate cao hơn nhiều: planner có thể chọn hash/merge strategy không cần thiết.
- Chênh lệch lớn có thể do statistics cũ, skew hoặc correlated columns.

### 14.5. BUFFERS

BUFFERS cho biết số shared/local/temp blocks hit/read/dirtied/written trong plan. Dùng nó để xác định node nào đọc nhiều block hoặc tạo temp I/O.

### 14.6. WAL

Tùy PostgreSQL version, EXPLAIN WAL có thể báo WAL records, full-page images và bytes cho statement được phân tích. Đây là số liệu hữu ích khi query update/insert lớn.

### 14.7. SETTINGS

EXPLAIN SETTINGS hiển thị một số non-default planner settings ảnh hưởng plan. Điều này giúp tái hiện môi trường khi điều tra.

### 14.8. So sánh plan với workload thực tế

Một plan trong lab có thể khác production do:

- Parameter values khác nhau.
- Data distribution và table size khác nhau.
- Cache state khác nhau.
- Statistics khác nhau.
- Concurrency và locks khác nhau.
- PostgreSQL version/config khác nhau.

Không tối ưu chỉ từ một lần EXPLAIN với parameter không đại diện.

---

## 15. Ghi execution plans tự động bằng auto_explain

### 15.1. Khi nào cần auto_explain?

`auto_explain` có thể ghi execution plans của các query vượt ngưỡng duration vào PostgreSQL log. Nó hữu ích khi query chậm xảy ra ngắt quãng và DBA không thể chạy EXPLAIN ANALYZE đúng thời điểm.

### 15.2. Preload module

Có thể preload cả hai module:

```conf
shared_preload_libraries = 'pg_stat_statements,auto_explain'
```

Thay đổi shared_preload_libraries yêu cầu restart.

### 15.3. Cấu hình ngưỡng log

Ví dụ:

```conf
auto_explain.log_min_duration = '500ms'
auto_explain.log_analyze = on
auto_explain.log_buffers = on
auto_explain.log_wal = on
auto_explain.log_timing = off
auto_explain.log_nested_statements = on
```

Đây là ví dụ cho môi trường điều tra; kiểm tra tham số được hỗ trợ trong major version đang chạy.

### 15.4. Overhead

ANALYZE và timing có thể tạo overhead. Nếu bật log_analyze, executor phải thu thập actual row counts; nếu bật timing, có thể đo thời gian cho từng node.

Để giảm overhead:

- Đặt log_min_duration phù hợp.
- Cân nhắc log_timing = off khi chỉ cần row counts/buffers.
- Dùng sample_rate nếu phù hợp.
- Giới hạn thời gian điều tra.
- Theo dõi log volume và disk capacity.

### 15.5. Dùng queryid để liên kết log và statistics

Có thể cấu hình log_line_prefix chứa query identifier nếu PostgreSQL version hỗ trợ, sau đó so sánh queryid trong log với pg_stat_statements. Queryid không được bảo đảm ổn định giữa major versions, nên không dùng như khóa vĩnh viễn cho kho dữ liệu lịch sử.

---

## 16. Phân loại truy vấn gây tốn tài nguyên

### 16.1. CPU-bound candidate

Dấu hiệu:

- Total/mean execution time cao.
- Shared I/O time thấp tương đối.
- Temp I/O không lớn.
- Query plan có nhiều joins, aggregates, expressions hoặc rows processed lớn.

Đây chỉ là dấu hiệu gợi ý; pg_stat_statements không cung cấp CPU time trực tiếp cho từng statement.

### 16.2. I/O-bound candidate

Dấu hiệu:

- Shared blocks read cao.
- I/O timing cao khi track_io_timing bật.
- Plan có sequential scans lớn hoặc index access ngẫu nhiên.
- Storage latency ở OS/cloud metrics tăng cùng thời điểm.

### 16.3. Memory/temp spill candidate

Dấu hiệu:

- temp_blks_read/written cao.
- EXPLAIN có sort/hash batches hoặc disk usage.
- Temporary file logs tăng.

Xem query plan và work_mem trước khi điều chỉnh.

### 16.4. WAL-heavy write workload

Dấu hiệu:

- wal_bytes, wal_records hoặc wal_fpi cao.
- Calls/rows của UPDATE/DELETE/INSERT lớn.
- Replication lag, archive backlog hoặc WAL disk usage tăng.

### 16.5. Planning-heavy workload

Dấu hiệu:

- total_plan_time/mean_plan_time cao khi track_planning bật.
- Query có nhiều joins/partitions hoặc statement dynamic.
- Planning time chiếm phần lớn plan+execution time.

### 16.6. Lock-wait candidate

pg_stat_statements không phân loại riêng lock wait. Đối chiếu pg_stat_activity.wait_event_type = 'Lock', pg_blocking_pids() và transaction age.

### 16.7. Network/application-bound

Database có thể hoàn thành query nhanh nhưng application vẫn chậm do:

- Network latency.
- Truyền quá nhiều rows.
- Serialization/deserialization.
- Connection pool queue.
- Application processing.

pg_stat_statements ghi rows và execution metrics nhưng không đo đầy đủ thời gian từ client request tới response.

---

## 17. Statistics reset và theo dõi theo thời gian

### 17.1. Statistics là bộ đếm tích lũy

Các giá trị calls, total_exec_time, blocks và WAL tăng dần trong khoảng thời gian entry được theo dõi. Nếu không biết lần reset gần nhất, không thể diễn giải số liệu như một khoảng thời gian cố định.

### 17.2. Xem thời điểm reset

Từ PostgreSQL 14:

```sql
SELECT
    dealloc,
    stats_reset
FROM pg_stat_statements_info;
```

PostgreSQL 13 không có view pg_stat_statements_info; dùng metadata monitoring riêng hoặc log thời điểm reset.

### 17.3. Reset toàn bộ statistics

```sql
SELECT pg_stat_statements_reset();
```

Đây là thao tác xóa thống kê tích lũy. Không chạy định kỳ mà không lưu snapshot trước, vì sẽ mất baseline để phân tích workload.

### 17.4. Reset một entry

Các overload của pg_stat_statements_reset thay đổi theo extension version. Trong các phiên bản hiện đại, có thể reset theo user/database/queryid và tùy chọn chỉ reset min/max:

```sql
SELECT pg_stat_statements_reset(
    userid := 0,
    dbid := 0,
    queryid := 123456789,
    minmax_only := false
);
```

Thay queryid bằng giá trị thực. Kiểm tra function signature của major version trước khi dùng trong automation; PostgreSQL 13 không có tham số minmax_only.

### 17.5. Chỉ reset min/max

Ở các phiên bản hỗ trợ, minmax_only = true chỉ reset các trường min/max planning/execution, giữ các counters tích lũy khác. Đây là cách mở cửa sổ min/max mới mà không xóa toàn bộ history counters.

### 17.6. Lưu snapshot trước khi reset

Một bảng history đơn giản:

```sql
CREATE SCHEMA IF NOT EXISTS monitoring;

CREATE TABLE IF NOT EXISTS monitoring.query_stats_history (
    captured_at TIMESTAMPTZ NOT NULL,
    dbid OID NOT NULL,
    userid OID NOT NULL,
    queryid BIGINT NOT NULL,
    calls BIGINT NOT NULL,
    total_exec_time DOUBLE PRECISION NOT NULL,
    total_plan_time DOUBLE PRECISION NOT NULL,
    rows BIGINT NOT NULL,
    shared_blks_read BIGINT NOT NULL,
    temp_blks_written BIGINT NOT NULL,
    wal_bytes NUMERIC NOT NULL,
    query_text TEXT
);
```

Ghi snapshot:

```sql
INSERT INTO monitoring.query_stats_history
SELECT
    clock_timestamp(),
    dbid,
    userid,
    queryid,
    calls,
    total_exec_time,
    total_plan_time,
    rows,
    shared_blks_read,
    temp_blks_written,
    wal_bytes,
    query
FROM pg_stat_statements;
```

Nếu dùng PostgreSQL 13–18, các cột được chọn ở ví dụ này có trong các version hiện đại được nêu; kiểm tra schema extension trước khi dùng cho hệ thống cũ hơn hoặc build khác.

### 17.7. Tính delta giữa hai snapshot

Có thể dùng LAG để tính số calls và execution time phát sinh giữa hai lần lấy mẫu:

```sql
WITH samples AS (
    SELECT
        captured_at,
        dbid,
        userid,
        queryid,
        calls,
        total_exec_time,
        LAG(calls) OVER (
            PARTITION BY dbid, userid, queryid
            ORDER BY captured_at
        ) AS previous_calls,
        LAG(total_exec_time) OVER (
            PARTITION BY dbid, userid, queryid
            ORDER BY captured_at
        ) AS previous_exec_time
    FROM monitoring.query_stats_history
)
SELECT
    captured_at,
    dbid,
    userid,
    queryid,
    calls - previous_calls AS calls_in_interval,
    total_exec_time - previous_exec_time AS exec_ms_in_interval
FROM samples
WHERE previous_calls IS NOT NULL
  AND calls >= previous_calls
  AND total_exec_time >= previous_exec_time
ORDER BY captured_at DESC, exec_ms_in_interval DESC;
```

Điều kiện delta không âm giúp loại các trường hợp reset counters giữa hai lần snapshot. Cũng cần xử lý entries bị deallocate, queryid thay đổi sau DDL/upgrade và entries mới chỉ xuất hiện ở snapshot sau.

### 17.8. Rate theo thời gian

Chia delta calls hoặc total_exec_time cho số giây giữa hai snapshots để có rate. Dùng captured_at thực tế, không giả định scheduler luôn chạy đúng chu kỳ.

### 17.9. Không reset để tạo time window nếu có thể snapshot

Snapshot định kỳ cho phép so sánh nhiều cửa sổ mà không xóa dữ liệu. Reset chỉ phù hợp khi có mục tiêu rõ ràng, quyền quản trị phù hợp và đã lưu baseline cần thiết.

### 17.10. Deallocation và query text file

dealloc tăng cho biết entries bị loại do giới hạn max. Mặt khác, query text được lưu trong file ngoài shared memory; nếu có quá nhiều query text dài, file có thể tăng lớn và extension có thể bỏ query text, khiến cột query trở thành NULL trong khi counters vẫn còn.

Theo dõi cả shared memory sizing, dealloc và disk footprint; không chỉ tăng max một cách tự động.

---

## 18. Quyền truy cập và bảo mật

### 18.1. View chứa thông tin nhạy cảm

Query text có thể tiết lộ:

- Tên bảng/schema nội bộ.
- Tên cột nghiệp vụ.
- Cấu trúc truy vấn.
- Literal values trong một số statement, đặc biệt utility commands hoặc trường hợp normalization không áp dụng.
- Chi tiết logic ứng dụng.

Không coi query text là dữ liệu vô hại.

### 18.2. Quyền xem query text của user khác

Chỉ superuser hoặc role có quyền của pg_read_all_stats mới được xem SQL text và queryid của truy vấn do user khác thực thi. Các role khác có thể xem statistics nhưng query text/queryid của user khác bị ẩn theo quy tắc bảo mật.

### 18.3. Cấp quyền monitoring

Có thể cấp predefined role:

```sql
GRANT pg_read_all_stats TO monitoring_reader;
```

Role này có phạm vi quyền đọc statistics rộng trên server. Chỉ cấp cho DBA/monitoring service cần thiết; không cấp mặc định cho application users.

### 18.4. Quyền reset

Mặc định, pg_stat_statements_reset chỉ superuser được gọi. Có thể GRANT EXECUTE cho role khác nếu cần, nhưng đây là quyền xóa số liệu dùng chung. Hãy kiểm soát qua role riêng và audit.

### 18.5. Extension cài trong từng database

View/hàm SQL chỉ xuất hiện trong database đã CREATE EXTENSION. Điều đó không có nghĩa mỗi database có bộ shared statistics độc lập; dữ liệu thống kê được thu thập ở cấp server và phân biệt bằng dbid.

### 18.6. Managed PostgreSQL

Trên dịch vụ cloud:

- Kiểm tra extension có nằm trong allowlist.
- Cấu hình shared_preload_libraries qua parameter group.
- Có thể cần restart instance/cluster.
- Cấp role monitoring theo cơ chế của nhà cung cấp.
- Kiểm tra query text visibility và reset permissions.

---

## 19. Những hiểu lầm thường gặp

**1. “pg_stat_statements ghi log từng lần query.”** Sai. Nó tổng hợp thống kê theo query entries.

**2. “Query text là câu SQL nguyên bản của mọi request.”** Sai. Text đại diện thường đã thay literals bằng tham số và không giữ từng invocation.

**3. “Queryid ổn định qua mọi major version.”** Sai. Không có bảo đảm ổn định qua major versions, architecture hoặc catalog changes.

**4. “Query có total_exec_time cao nhất là query có latency cao nhất.”** Sai. Tổng thời gian phụ thuộc cả số calls; dùng mean/max để xem latency từng lần.

**5. “Query mean thấp không đáng tối ưu.”** Sai. Tần suất rất cao có thể tạo tổng chi phí lớn.

**6. “shared_blks_read là bytes đọc từ ổ đĩa vật lý.”** Sai. Nó là số blocks PostgreSQL phải nạp vào shared buffers; OS cache có thể phục vụ đọc.

**7. “Hit ratio 100% nghĩa query tối ưu.”** Sai. Query vẫn có thể scan quá nhiều blocks hoặc tiêu tốn CPU.

**8. “I/O time bằng 0 nghĩa query không chờ I/O.”** Sai nếu track_io_timing đang tắt.

**9. “temp_blks_written cao luôn cần tăng work_mem.”** Sai. Trước hết xem plan, rows, sort/hash nodes, concurrency và memory budget.

**10. “track_planning nên luôn bật.”** Sai. Nó có overhead và mặc định off.

**11. “plans luôn bằng calls.”** Sai. Planning và execution cập nhật ở các giai đoạn khác nhau; cached plan và execution errors làm số đếm khác nhau.

**12. “pg_stat_statements cho biết query đang chạy ngay bây giờ.”** Không. Dùng pg_stat_activity để xem active backends.

**13. “total_exec_time là CPU time.”** Sai. Đây là execution time, có thể gồm thời gian chờ; không có CPU-time counter trực tiếp cho từng statement.

**14. “Một query chậm chắc chắn do execution plan.”** Không. Có thể do locks, I/O, network, parameter skew hoặc application behavior.

**15. “Tạo extension một lần trong database postgres là đủ cho mọi database.”** Không. View/hàm được cài trong từng database cần truy vấn.

**16. “Reload config đủ để preload extension.”** Không. Thay đổi shared_preload_libraries cần restart.

**17. “pg_stat_statements.max càng lớn càng tốt.”** Không. Shared memory tăng và query text file cũng có thể phình lớn.

**18. “dealloc cao không ảnh hưởng dữ liệu.”** Sai. Nó báo entries bị loại, lịch sử thống kê có thể không đầy đủ.

**19. “Reset statistics không có tác dụng phụ.”** Sai. Nó xóa baseline; lưu snapshot trước nếu cần so sánh.

**20. “Statistics tự động cho biết performance của một khoảng thời gian cố định.”** Sai. Đây là counters tích lũy từ lần reset/entry start; cần snapshot và delta để có time window.

**21. “Nested statements có thể cộng với parent mà không trùng.”** Sai. track=all có thể ghi cả statement ngoài và bên trong.

**22. “Queryid giống nhau trên logical replicas.”** Không được bảo đảm; logical replication không đảm bảo catalog metadata giống nhau.

**23. “pg_stat_statements thay thế EXPLAIN.”** Sai. Nó tìm query patterns; EXPLAIN giúp xem plan.

**24. “EXPLAIN ANALYZE chỉ ước lượng, không chạy query.”** Sai. Nó thực sự thực thi statement.

**25. “Column query luôn hiển thị với mọi user.”** Sai. Query text/queryid của user khác được bảo vệ theo quyền pg_read_all_stats/superuser.

---

## 20. Thực hành trong lab

### 20.1. Kiểm tra extension và reset lab statistics

Kết nối vào database lab:

```sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pg_stat_statements';

SELECT pg_stat_statements_reset();
```

Chỉ reset trong lab hoặc sau khi đã lưu snapshot baseline.

### 20.2. Tạo dữ liệu mẫu

```sql
CREATE SCHEMA IF NOT EXISTS lab;

DROP TABLE IF EXISTS lab.events;

CREATE TABLE lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    payload TEXT NOT NULL
);

INSERT INTO lab.events
    (tenant_id, event_type, event_time, payload)
SELECT
    (g % 100)::integer,
    CASE WHEN g % 5 = 0 THEN 'purchase' ELSE 'view' END,
    now() - (g % 100000) * interval '1 minute',
    repeat(md5(g::text), 4)
FROM generate_series(1, 300000) AS g;

ANALYZE lab.events;
```

### 20.3. Chạy query scan và aggregate

```sql
SELECT
    tenant_id,
    event_type,
    count(*) AS event_count
FROM lab.events
WHERE event_time >= now() - interval '30 days'
GROUP BY tenant_id, event_type
ORDER BY event_count DESC;
```

Chạy query vài lần trong lab để tạo calls. Không cần cố tạo benchmark số liệu cụ thể; mục tiêu là xem cách entry được ghi nhận.

### 20.4. Chạy query sort để quan sát temp blocks

Có thể giảm work_mem riêng trong session lab:

```sql
SET work_mem = '1MB';

SELECT event_id, payload
FROM lab.events
ORDER BY payload;

RESET work_mem;
```

Dataset và memory settings quyết định query có spill hay không. Kiểm tra temp_blks_written sau khi chạy; nếu không spill, tăng dataset trong lab hoặc giảm work_mem có kiểm soát.

### 20.5. Chạy workload update để tạo WAL

```sql
UPDATE lab.events
SET payload = payload || '-processed'
WHERE tenant_id = 42;
```

Chạy lại với một nhóm tenant khác để tăng calls/rows và quan sát WAL metrics.

### 20.6. Xem top queries theo total execution time

```sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    rows,
    shared_blks_read,
    temp_blks_written,
    wal_bytes,
    left(query, 300) AS query_sample
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database
              WHERE datname = current_database())
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 20.7. Xem top queries theo temp blocks

```sql
SELECT
    queryid,
    calls,
    temp_blks_read,
    temp_blks_written,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    left(query, 300) AS query_sample
FROM pg_stat_statements
WHERE temp_blks_read > 0
   OR temp_blks_written > 0
ORDER BY temp_blks_read + temp_blks_written DESC
LIMIT 20;
```

### 20.8. Xem top queries theo WAL

```sql
SELECT
    queryid,
    calls,
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_size,
    left(query, 300) AS query_sample
FROM pg_stat_statements
ORDER BY wal_bytes DESC
LIMIT 20;
```

### 20.9. Xem query đang chạy

Trong khi chạy query dài ở session khác:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    query_id,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
```

Nếu version không có query_id, bỏ cột này.

### 20.10. So sánh trước và sau khi tạo index

Trước tiên phân tích plan:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM lab.events
WHERE tenant_id = 42
  AND event_time >= now() - interval '7 days';
```

Tạo index trong lab:

```sql
CREATE INDEX events_tenant_time_idx
ON lab.events (tenant_id, event_time);

ANALYZE lab.events;
```

Chạy lại EXPLAIN ANALYZE với cùng điều kiện và so sánh actual time, buffers, plan nodes. Query text có thể được gom vào cùng entry dù execution plan thay đổi, vì vậy lưu snapshot hoặc reset entry có kiểm soát nếu muốn so sánh các cửa sổ riêng.

### 20.11. Quan sát planning metrics

Nếu muốn đo planning time:

1. Bật pg_stat_statements.track_planning trong cấu hình được phép.
2. Restart/reload theo context của tham số và version.
3. Chạy workload lab.
4. So sánh plans, total_plan_time và calls.
5. Đánh giá overhead; tắt lại nếu không cần.

### 20.12. Dọn lab

```sql
DROP TABLE IF EXISTS lab.events;
DROP SCHEMA IF EXISTS lab;
```

Không drop extension nếu database còn dashboard hoặc monitoring tools đang sử dụng view.

---

## 21. Bài tập thực hành và đáp án

### Bài 1 — Mục đích

**Câu hỏi:** pg_stat_statements giúp trả lời loại câu hỏi nào?

**Đáp án:** Query patterns nào tiêu tốn nhiều planning/execution time, blocks, temp files, WAL hoặc được gọi thường xuyên.

### Bài 2 — Cài đặt

**Câu hỏi:** Cần cấu hình module ở đâu trước khi CREATE EXTENSION?

**Đáp án:** Thêm pg_stat_statements vào shared_preload_libraries, bật query identifier phù hợp và restart server.

### Bài 3 — Extension database

**Câu hỏi:** Có cần CREATE EXTENSION trong từng database muốn truy vấn view không?

**Đáp án:** Có. Module preload ở server level nhưng view/hàm được cài vào từng database.

### Bài 4 — Query normalization

**Câu hỏi:** Hai query chỉ khác literal constants có thể được gom cùng entry không?

**Đáp án:** Có, nếu query identifier/normalization áp dụng và cấu trúc parse tương đương.

### Bài 5 — Queryid

**Câu hỏi:** Queryid có ổn định giữa major versions không?

**Đáp án:** Không được bảo đảm.

### Bài 6 — Calls

**Câu hỏi:** calls đo điều gì?

**Đáp án:** Số lần statement được thực thi.

### Bài 7 — Total và mean

**Câu hỏi:** Khi nào xem total_exec_time, khi nào xem mean_exec_time?

**Đáp án:** Total để tìm tổng chi phí workload; mean để tìm độ trễ trung bình mỗi lần.

### Bài 8 — Planning

**Câu hỏi:** Cần bật tham số nào để ghi planning metrics?

**Đáp án:** pg_stat_statements.track_planning.

### Bài 9 — Planning overhead

**Câu hỏi:** Vì sao không bật track_planning vô điều kiện?

**Đáp án:** Nó có thể tạo contention/overhead, đặc biệt khi nhiều connections chạy cùng query structure.

### Bài 10 — Block read

**Câu hỏi:** shared_blks_read có nghĩa chắc chắn đọc từ disk vật lý không?

**Đáp án:** Không. OS page cache có thể phục vụ đọc.

### Bài 11 — I/O timing

**Câu hỏi:** Cần bật gì để có I/O timing?

**Đáp án:** track_io_timing.

### Bài 12 — Temp blocks

**Câu hỏi:** temp_blks_written lớn có thể gợi ý điều gì?

**Đáp án:** Sort/hash hoặc intermediate operations spill ra temporary files.

### Bài 13 — work_mem

**Câu hỏi:** Vì sao không nên tăng work_mem global một cách tùy tiện?

**Đáp án:** Một query có nhiều operations và nhiều sessions đồng thời có thể tiêu thụ tổng memory rất lớn.

### Bài 14 — WAL

**Câu hỏi:** wal_bytes đo gì?

**Đáp án:** Tổng bytes WAL do statement tạo, không phải bytes thực tế ghi xuống disk.

### Bài 15 — pg_stat_statements_info

**Câu hỏi:** View này có từ PostgreSQL version nào?

**Đáp án:** PostgreSQL 14.

### Bài 16 — Dealloc

**Câu hỏi:** dealloc tăng nhanh gợi ý điều gì?

**Đáp án:** Nhiều entries bị loại do vượt pg_stat_statements.max; có thể cần xem xét tăng max và shared memory.

### Bài 17 — Reset

**Yêu cầu:** Reset toàn bộ statement statistics.

```sql
SELECT pg_stat_statements_reset();
```

### Bài 18 — Active query

**Câu hỏi:** View nào dùng để xem query đang chạy ngay lúc này?

**Đáp án:** pg_stat_activity.

### Bài 19 — Lock

**Yêu cầu:** Tìm blocker PID của active backends.

```sql
SELECT pid, pg_blocking_pids(pid)
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
```

### Bài 20 — Explain

**Câu hỏi:** EXPLAIN ANALYZE có thực sự chạy query không?

**Đáp án:** Có. Với DML, nó thực sự thay đổi dữ liệu trừ khi được rollback trong transaction; một số side effects ngoài transaction vẫn có thể tồn tại.

### Bài 21 — Auto explain

**Câu hỏi:** Extension nào ghi plan tự động cho query vượt ngưỡng?

**Đáp án:** auto_explain.

### Bài 22 — Nested statements

**Câu hỏi:** track=all có thể ghi cả parent và nested statements không?

**Đáp án:** Có. Không cộng các thời gian này như các phần độc lập vì có thể chồng lấp.

### Bài 23 — Security

**Câu hỏi:** Role nào cho phép xem query text/queryid của các user khác?

**Đáp án:** Superuser hoặc role có quyền pg_read_all_stats.

### Bài 24 — Version 18

**Câu hỏi:** PostgreSQL 18 bổ sung những nhóm metrics nào đáng chú ý?

**Đáp án:** Parallel worker counts, stats_since/minmax_stats_since, WAL buffer metric và I/O timing tách shared/local/temp.

### Bài 25 — Time window

**Câu hỏi:** Làm thế nào để có statistics theo từng 5 phút mà không reset liên tục?

**Đáp án:** Lưu snapshots định kỳ và tính delta counters giữa các lần lấy mẫu.

---

## 22. Checklist triển khai monitoring

### Cài đặt và cấu hình

1. Cài package pg_stat_statements phù hợp với PostgreSQL major version.
2. Thêm pg_stat_statements vào shared_preload_libraries, giữ các preload modules khác.
3. Xác nhận compute_query_id = auto/on hoặc module queryid tương thích.
4. Restart server khi thay đổi shared_preload_libraries.
5. CREATE EXTENSION trong từng database cần truy vấn view.
6. Kiểm tra extension version và view schema.
7. Chọn pg_stat_statements.max dựa trên query diversity và shared memory.
8. Chọn track=top hay all theo nhu cầu; bắt đầu bằng top.
9. Chỉ bật track_planning khi cần điều tra planning overhead.
10. Bật track_io_timing nếu cần I/O time và đã đo overhead.

### Phân tích truy vấn

11. Xếp hạng theo total_exec_time để tìm tổng workload cost.
12. Xếp hạng theo mean_exec_time/max_exec_time để tìm latency.
13. Xem calls để phát hiện query chạy quá thường xuyên.
14. Xem shared_blks_read/hit và I/O timing để tìm read pressure.
15. Xem temp_blks_read/written và log_temp_files để tìm spill.
16. Xem wal_bytes/wal_records/wal_fpi để tìm write-heavy statements.
17. Xem planning và JIT metrics khi phù hợp.
18. Kết hợp pg_stat_activity và pg_blocking_pids khi sự cố đang xảy ra.
19. Dùng EXPLAIN (ANALYZE, BUFFERS) để xác định plan và actual row counts.
20. Cân nhắc auto_explain cho query chậm không tái hiện được.

### Bảo trì và governance

21. Theo dõi pg_stat_statements_info.dealloc từ PostgreSQL 14+.
22. Lưu snapshots định kỳ nếu cần time-window analysis.
23. Lưu stats_reset và thời điểm restart/reset.
24. Không reset trước khi lưu baseline cần thiết.
25. Kiểm soát quyền pg_read_all_stats và quyền reset.
26. Bảo vệ query text và monitoring history.
27. Kiểm tra disk footprint của query text file.
28. Kiểm tra schema differences khi hỗ trợ nhiều major versions.
29. Đánh giá overhead sau khi bật thêm tracking.
30. Ghi lại thay đổi, thời gian quan sát và kết quả tối ưu để so sánh sau này.

---

## 23. Tổng kết

pg_stat_statements là công cụ thống kê query patterns ở cấp server. Nó giúp xác định các nhóm SQL tiêu tốn nhiều thời gian, I/O, temporary blocks, WAL hoặc planning effort. Query identifier và normalization gom các câu lệnh tương tự thành entries để DBA xếp hạng workload theo dữ liệu tích lũy.

Các điểm cần nhớ:

- Cần preload module trong shared_preload_libraries, restart server và tạo extension trong từng database muốn truy vấn view.
- Statistics được thu thập trên toàn server và phân biệt theo database/user/queryid.
- Query text là đại diện đã chuẩn hóa; không phải log từng request hay parameter values.
- Queryid không được bảo đảm ổn định giữa major versions hoặc logical replicas.
- total_exec_time cho biết tổng chi phí; mean/max cho biết latency mỗi lần; calls cho biết tần suất.
- Shared blocks, temp blocks, I/O timing, WAL và JIT giúp phân loại tài nguyên tiêu thụ.
- track_planning có overhead; chỉ bật khi cần đo planning.
- pg_stat_activity cho biết query đang chạy; pg_stat_statements cho biết thống kê tích lũy.
- EXPLAIN ANALYZE thực sự chạy statement; dùng cẩn thận với DML.
- auto_explain giúp ghi plan của query vượt ngưỡng.
- Statistics là counters tích lũy; snapshot và delta phù hợp để theo dõi theo thời gian.
- pg_stat_statements_reset xóa baseline; lưu snapshot trước khi reset.
- Query text và queryid của user khác được bảo vệ bởi quyền superuser/pg_read_all_stats.
- PostgreSQL 13–18 có khác biệt schema; đặc biệt pg_stat_statements_info từ PG14 và các metrics bổ sung ở PG18.

**Câu hỏi tự kiểm tra:** Một query có mean_exec_time chỉ 3 ms nhưng calls rất lớn và total_exec_time đứng đầu. Một query khác mean_exec_time 2 giây nhưng chỉ chạy 10 lần. Nếu mục tiêu là giảm tổng tải database, query nào cần ưu tiên? Cần xem total cost, calls, business criticality và tài nguyên cụ thể trước khi chọn; không xếp hạng chỉ bằng một con số.

### Tài liệu PostgreSQL chính thức

- [pg_stat_statements — PostgreSQL 18](https://www.postgresql.org/docs/18/pgstatstatements.html).
- [pg_stat_statements — PostgreSQL 17](https://www.postgresql.org/docs/17/pgstatstatements.html).
- [pg_stat_statements — PostgreSQL 16](https://www.postgresql.org/docs/16/pgstatstatements.html).
- [pg_stat_statements — PostgreSQL 14](https://www.postgresql.org/docs/14/pgstatstatements.html).
- [pg_stat_statements — PostgreSQL 13](https://www.postgresql.org/docs/13/pgstatstatements.html).
- [Run-time Statistics Configuration](https://www.postgresql.org/docs/current/runtime-config-statistics.html).
- [Monitoring Statistics and pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html).
- [auto_explain](https://www.postgresql.org/docs/current/auto-explain.html).
- [Query Planning Configuration](https://www.postgresql.org/docs/current/runtime-config-query.html).
- [Predefined Roles — pg_read_all_stats](https://www.postgresql.org/docs/current/predefined-roles.html).
