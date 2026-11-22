# Áp lực bộ nhớ, hoán đổi và nguy cơ hết bộ nhớ

Bộ nhớ là tài nguyên nền tảng của hệ quản trị cơ sở dữ liệu. Database dùng RAM để giữ page dữ liệu thường truy cập, cache metadata và kế hoạch thực thi, đồng thời cấp vùng làm việc cho sort, hash join, aggregate, tạo chỉ mục và các thao tác bảo trì. Mỗi kết nối hoặc tiến trình cũng có thể cần bộ nhớ riêng. Khi tổng nhu cầu vượt ngân sách RAM, hệ điều hành phải thu hồi cache, chuyển page sang swap hoặc từ chối cấp phát. Hệ quả có thể là truy vấn chậm, I/O tăng, timeout, tiến trình database bị hệ điều hành kết thúc hoặc toàn bộ dịch vụ mất khả năng phục vụ.

**Áp lực bộ nhớ** (*memory pressure*) xuất hiện khi working set và các vùng cấp phát đang hoạt động cạnh tranh vượt quá dung lượng RAM có thể sử dụng an toàn. **Hoán đổi** (*swapping*) là việc hệ điều hành chuyển các page bộ nhớ ít hoạt động ra thiết bị lưu trữ để giải phóng RAM. **Hết bộ nhớ** (*out of memory*, OOM) xảy ra khi hệ điều hành hoặc tiến trình không thể đáp ứng yêu cầu cấp phát theo giới hạn hiện hành. Ba trạng thái này liên quan nhưng không đồng nghĩa: một máy có swap đã dùng chưa chắc đang thrashing, còn một tiến trình có thể chạm giới hạn cấp phát dù máy chủ vẫn còn RAM ở nơi khác.

Trong module **DATABASE_PERFORMANCE**, cần lập ngân sách bộ nhớ cho cả database và hệ điều hành, hiểu ảnh hưởng của concurrency và query work area, nhận diện swap thrashing và OOM, rồi điều chỉnh cache, kết nối, truy vấn và giới hạn container theo số liệu. Mục tiêu là duy trì working set ổn định, tránh cấp phát vượt giới hạn và giữ độ trễ có thể dự đoán khi tải tăng.

## 1. Bộ nhớ được sử dụng ở những đâu?

Không nên xem toàn bộ RAM của máy chủ là bộ nhớ có thể giao cho buffer cache. Trên một máy chạy database, bộ nhớ thường được chia cho nhiều nhóm:

| Nhóm | Ví dụ | Vai trò |
|---|---|---|
| Hệ điều hành | Kernel, service nền, filesystem cache, agent giám sát và bảo mật | Điều phối tiến trình, I/O, mạng và quản lý page |
| Bộ nhớ dùng chung của database | Buffer pool, shared buffers, SGA, plan cache | Giữ page dữ liệu, metadata, cấu trúc dùng chung và kế hoạch |
| Bộ nhớ riêng của session/process | Stack, session state, cursor, private memory | Trạng thái của kết nối hoặc tiến trình xử lý |
| Query work area | Sort, hash join, hash aggregate, bitmap hoặc workfile | Xử lý dữ liệu trung gian trong truy vấn |
| Bảo trì | Build/rebuild index, vacuum, purge, backup, statistics | Các tác vụ nền và quản trị |
| Ứng dụng đi kèm | Connection pool, proxy, sidecar, exporter, log agent | Các thành phần cùng dùng RAM trên máy hoặc trong container |

Một cấu hình chỉ tính `buffer_pool_size` hoặc `shared_buffers` mà bỏ qua session memory và query work area có thể vượt giới hạn máy chủ khi concurrency tăng. Tương tự, database chạy trong container cần tính theo memory limit của container, không phải tổng RAM vật lý của host.

### Bộ nhớ dùng chung và bộ nhớ riêng

Bộ nhớ dùng chung thường được cấp một lần hoặc quản lý theo pool để nhiều session cùng hưởng lợi. Ví dụ, nhiều truy vấn đọc cùng một page có thể dùng chung page đang nằm trong buffer cache.

Bộ nhớ riêng được cấp theo session, worker hoặc thao tác. Khi số kết nối và số truy vấn đồng thời tăng, phần này có thể tăng theo. Một tham số tưởng như nhỏ trên mỗi session có thể trở thành khoản tiêu thụ lớn khi nhân với hàng trăm hoặc hàng nghìn kết nối.

### Query work area có thể nhân lên trong một truy vấn

Một truy vấn phức tạp có thể có nhiều thao tác sort hoặc hash. Mỗi thao tác có thể cần work area riêng; một số hệ quản trị còn cho phép hash sử dụng hệ số lớn hơn giới hạn cơ sở. Vì vậy, không thể lấy một giá trị bộ nhớ mỗi truy vấn rồi nhân đơn giản với số kết nối mà bỏ qua số operator đồng thời trong plan.

## 2. Working set, cache và bộ nhớ còn trống

**Working set** là tập page và dữ liệu mà workload đang hoạt động cần truy cập thường xuyên trong một khoảng thời gian. Nếu working set vừa với RAM có thể dùng, database thường phục vụ nhiều lần đọc từ cache. Nếu working set lớn hơn dung lượng khả dụng, page bị đẩy ra rồi lại phải đọc vào, làm tăng I/O và độ trễ.

### Cache lớn không đồng nghĩa luôn tốt

Buffer cache lớn có thể giảm physical read, nhưng lấy quá nhiều RAM cho cache sẽ làm giảm bộ nhớ dành cho query work area, session, hệ điều hành và các dịch vụ khác. Nếu phần còn lại thiếu, hệ thống có thể swap hoặc OOM trước khi cache mang lại lợi ích tương xứng.

### RAM còn trống thấp không tự động là lỗi

Hệ điều hành thường tận dụng RAM nhàn rỗi làm filesystem cache. Vì vậy, con số “free memory” thấp không đủ để kết luận máy đang thiếu RAM. Cần xem available memory, tốc độ reclaim, swap-in/swap-out, major page fault, memory pressure, I/O latency và độ trễ database.

Ngược lại, cache hit ratio cao cũng không chứng minh hệ thống không bị áp lực bộ nhớ. Một workload có thể có hit ratio tốt nhưng query memory grant chờ lâu, process bị giới hạn bởi cgroup hoặc OOM killer đã kết thúc một tiến trình khác.

### Ví dụ về working set vượt RAM

Giả sử database có 200 GB dữ liệu nóng được truy cập luân phiên, nhưng buffer pool chỉ có thể giữ 40 GB sau khi dành RAM cho query và hệ điều hành. Nếu workload liên tục chuyển giữa các vùng dữ liệu khác nhau, page bị đẩy ra rồi đọc lại. Tăng buffer pool có thể giúp nếu còn RAM dự phòng; nếu máy đã gần giới hạn, tăng cache có thể làm query spill hoặc hệ điều hành swap nhiều hơn.

## 3. Ngân sách bộ nhớ cho database

Hãy lập ngân sách theo tải đỉnh, không chỉ theo mức dùng trung bình lúc nhàn rỗi. Một mô hình khái quát:

\[
M_{total} = M_{OS} + M_{shared} + M_{sessions} + M_{queries} + M_{maintenance} + M_{other}
\]

Trong đó:

- `M_OS`: kernel, service hệ điều hành và phần dự phòng vận hành.
- `M_shared`: buffer cache, shared memory, SGA hoặc pool dùng chung.
- `M_sessions`: bộ nhớ riêng của kết nối, worker và tiến trình.
- `M_queries`: sort, hash, aggregate và các work area đồng thời.
- `M_maintenance`: index build, vacuum, purge, backup và tác vụ nền.
- `M_other`: ứng dụng phụ trợ, agent, proxy và phần chưa phân loại.

Ngân sách phải thỏa giới hạn RAM thực tế và để lại headroom cho biến động, spike, hoạt động failover và tác vụ bảo trì. Không nên đặt tổng các giới hạn cấu hình bằng đúng dung lượng RAM vật lý; nhiều giới hạn có thể được sử dụng đồng thời hoặc vượt dự kiến.

### Ước lượng theo concurrency

Giả sử mỗi session hoạt động có thể dùng thêm một lượng bộ nhớ riêng, mỗi truy vấn có một hoặc nhiều work area, và có một nhóm tác vụ bảo trì chạy song song. Nhu cầu đỉnh có thể tăng nhanh hơn số kết nối đang mở vì không phải mọi kết nối đều chạy truy vấn, nhưng một truy vấn có thể có nhiều operator cấp phát bộ nhớ.

Hãy phân biệt:

- Kết nối mở nhưng idle.
- Session đang thực thi câu lệnh.
- Worker song song của một câu truy vấn.
- Work area được cấp phát hoặc đang chờ grant.
- Tác vụ bảo trì có thể chạy đồng thời với workload ứng dụng.

Sử dụng số liệu runtime để ước lượng từng nhóm. Không dùng một hệ số cố định cho mọi database hoặc mọi phiên bản.

### Dự phòng cho failover và bảo trì

Một node standby khi được promote có thể nhận toàn bộ workload. Nếu cấu hình chỉ vừa đủ cho mức tải bình thường của primary nhưng không đủ cho đợt tải sau failover, hệ thống có thể OOM ngay trong tình huống khẩn cấp. Tương tự, index rebuild, backup, vacuum hoặc báo cáo lớn có thể làm memory peak tăng đáng kể.

## 4. Áp lực bộ nhớ biểu hiện như thế nào?

Không có một metric đơn lẻ đủ để chẩn đoán. Hãy ghép tín hiệu từ hệ điều hành, database và ứng dụng.

| Tín hiệu | Ý nghĩa có thể có | Cần kiểm tra thêm |
|---|---|---|
| Available memory giảm kéo dài | Working set hoặc cấp phát tăng | Process RSS, cache, cgroup, xu hướng theo thời gian |
| Swap-in/swap-out liên tục | Page hoạt động bị chuyển qua lại giữa RAM và swap | Swap I/O, major faults, latency và tiến trình gây áp lực |
| Major page faults tăng | Tiến trình phải đọc page từ storage thay vì RAM | Có phải swap hay memory-mapped file, I/O latency |
| Query spill tăng | Sort/hash không đủ memory grant hoặc cấu hình work area thấp | Query plan, cardinality, concurrency, temp I/O |
| Memory grant pending/wait | Query đang chờ được cấp workspace | Grant requested/used, grant queue và query gây tiêu thụ |
| OOM event hoặc process bị kill | Chạm giới hạn OS/cgroup hoặc cấp phát thất bại | Kernel log, container event, database error log |
| Cache hit giảm cùng I/O tăng | Working set không còn nằm trong cache hoặc workload đổi | Page reads, cache churn, query mix |
| Latency tăng khi concurrency tăng | Tranh chấp bộ nhớ, I/O hoặc queueing | CPU, locks, storage, network và số session thực thi |

### Phân biệt memory pressure với CPU hoặc I/O bottleneck

Một query chậm khi CPU cao có thể bị giới hạn bởi tính toán, không phải RAM. Một query spill ra temp file có thể làm I/O tăng dù nguyên nhân gốc là thiếu memory grant. Một máy swap nhiều có thể đồng thời có storage latency cao. Hãy nối metric với query fingerprint, wait event, execution plan và thời điểm xảy ra.

## 5. Hoán đổi và swap thrashing

Swap là vùng lưu trữ được hệ điều hành dùng để giữ một số page bộ nhớ không nằm trong RAM. Trên Linux, swap có thể là partition hoặc file; trên Windows, pagefile có vai trò tương tự trong quản lý bộ nhớ ảo. Cơ chế chi tiết khác nhau nhưng rủi ro chung là truy cập page đã bị đẩy ra sẽ cần I/O lưu trữ.

### Swap đã dùng và swap đang hoạt động

Một hệ thống có thể còn lượng swap đã dùng từ trước nhưng hiện không có hoạt động swap đáng kể. Điều cần quan tâm là tốc độ swap-in và swap-out, major page fault, thời gian I/O và ảnh hưởng đến latency.

Swap hoạt động mạnh khi hệ điều hành liên tục đẩy page ra rồi lại phải đọc chúng vào vì workload vẫn cần. Hiện tượng này gọi là **thrashing**. CPU có thể không cao, nhưng tiến trình mất nhiều thời gian chờ I/O bộ nhớ; database có thể tăng độ trễ đột ngột và throughput giảm mạnh.

### Vì sao database nhạy với swap?

Database thường giữ working set trong buffer cache và cần truy cập page với độ trễ thấp. Nếu page cache hoặc vùng nhớ quan trọng bị swap, một lần truy cập vốn là RAM access có thể biến thành storage I/O. Một số vùng shared memory hoặc memory lock có quy tắc riêng, nhưng không nên dựa vào giả định rằng toàn bộ bộ nhớ database luôn được bảo vệ khỏi swap.

### Có nên tắt swap?

Không có một câu trả lời đúng cho mọi môi trường. Tắt swap có thể tránh một số tình huống swap thrashing nhưng làm hệ điều hành mất vùng đệm khi có spike; khi đó OOM có thể xảy ra sớm hơn. Giữ swap nhưng để database liên tục swap cũng có thể gây latency rất xấu.

Chính sách cần dựa trên hướng dẫn của hệ quản trị, loại workload, cách triển khai và khả năng giám sát. Điều quan trọng là không dùng swap làm phần mở rộng RAM cho working set thường xuyên; phải duy trì headroom và phát hiện sớm hoạt động swap bất thường.

### Quan sát trên Linux

Các lệnh đọc trạng thái phổ biến:

```bash
free -h
vmstat 1
swapon --show
cat /proc/meminfo
```

Trong `vmstat`, chú ý `si` (swap in) và `so` (swap out) theo thời gian, cùng `wa` (I/O wait), runnable queue và các page fault. `free` cung cấp `available` hữu ích hơn việc chỉ nhìn `free`. Các lệnh này là ví dụ quan sát; tên và cách trình bày có thể khác giữa bản phân phối.

Không kết luận thrashing chỉ từ `SwapUsed` khác 0. Hãy lấy chuỗi số liệu đủ dài, so với thời điểm query latency tăng và xác định tiến trình/container gây áp lực.

## 6. OOM và nguy cơ tiến trình database bị kết thúc

OOM xảy ra khi không thể đáp ứng yêu cầu cấp phát theo giới hạn hiện hành. Nguyên nhân có thể là máy chủ hết RAM, container chạm memory limit, giới hạn commit của hệ điều hành, database chạm giới hạn nội bộ hoặc một thao tác đòi vùng nhớ quá lớn.

### OOM killer trên Linux

Khi hệ thống Linux không thể thu hồi đủ bộ nhớ, kernel có thể kích hoạt OOM killer để chọn và kết thúc một tiến trình. Tiến trình bị chọn phụ thuộc chính sách và điểm đánh giá của kernel; không nên giả định luôn là tiến trình dùng RAM nhiều nhất. Nếu tiến trình database chính bị kết thúc, dịch vụ có thể dừng đột ngột và cần crash recovery khi khởi động lại.

Trong container, cgroup memory limit có thể bị chạm dù host còn RAM. Kernel hoặc runtime có thể ghi nhận container bị OOM-killed. Vì vậy, cần kiểm tra cả memory của host và giới hạn container.

### OOM ở cấp tiến trình hoặc database

Database cũng có thể từ chối cấp phát dù hệ điều hành chưa OOM. Ví dụ, SQL Server có thể báo lỗi cấp phát memory, Oracle có thể phát sinh lỗi vùng PGA/SGA, PostgreSQL có thể báo lỗi allocation hoặc bị hệ điều hành kết thúc, MySQL có thể báo lỗi cấp phát hoặc tiến trình bị kill. Phải đọc error log để phân biệt lỗi nội bộ với OOM killer.

### Hậu quả vận hành

- Kết nối đang xử lý có thể bị ngắt.
- Transaction chưa commit bị rollback khi recovery.
- Database service có thể restart và thực hiện crash recovery.
- Replica hoặc consumer có thể bị lag trong thời gian khôi phục.
- Connection pool có thể tạo đợt reconnect đồng loạt, làm tăng tải khi dịch vụ trở lại.
- Một workload quá nặng có thể lặp lại OOM sau mỗi lần restart nếu nguyên nhân chưa được xử lý.

Không nên chỉ tăng RAM hoặc restart lặp lại mà không thu thập bằng chứng. Cần xác định process, query, cgroup, memory grant, cache hoặc tác vụ nền tạo peak.

## 7. Nguyên nhân thường tạo áp lực bộ nhớ

### Quá nhiều kết nối và worker

Mỗi session có thể giữ stack, session state, buffer riêng và các cấu trúc phục vụ truy vấn. Nếu `max_connections` hoặc pool size quá lớn, tổng bộ nhớ tiềm năng tăng. Worker song song cũng có thể làm một truy vấn sử dụng nhiều tài nguyên hơn.

Giải pháp thường là giới hạn connection pool, dùng connection proxy/pooler khi phù hợp, giới hạn concurrency ở tầng ứng dụng và đặt hàng đợi có kiểm soát. Tăng số kết nối không tự động làm tăng throughput nếu database đã bão hòa CPU, I/O hoặc lock.

### Query plan cần work area quá lớn

Hash join, hash aggregate, sort và window function có thể cần nhiều RAM. Cardinality estimate sai khiến optimizer chọn hash table lớn hoặc cấp memory grant không phù hợp. Nhiều query cùng chạy có thể cạnh tranh bộ nhớ, gây grant wait hoặc spill.

Hướng xử lý:

- Kiểm tra estimated rows và actual rows.
- Giảm dữ liệu đầu vào trước sort/hash bằng predicate và projection phù hợp.
- Kiểm tra index có thể tránh sort hoặc giảm phạm vi join không.
- Chia báo cáo lớn thành batch nếu nghiệp vụ cho phép.
- Giới hạn concurrency của workload phân tích.
- Cập nhật thống kê khi có bằng chứng estimate sai.

### Truy vấn trả quá nhiều dữ liệu

`SELECT *`, tải LOB, lấy toàn bộ lịch sử hoặc materialize tập lớn trong ứng dụng có thể làm tăng RAM ở cả database lẫn application server. Chỉ lấy cột cần thiết, phân trang, streaming và xử lý theo batch giúp giới hạn working set.

### Cache được cấu hình quá lớn

Buffer pool/shared cache/SGA quá lớn có thể chiếm RAM dành cho session, query work area, OS và agent. Cache lớn chỉ có lợi khi working set thực sự được hưởng lợi và hệ thống vẫn đủ headroom cho các vùng khác.

### Tác vụ bảo trì đồng thời

Index build, sort lớn, vacuum, purge, backup, statistics collection và báo cáo có thể tạo peak. Lập lịch hoặc giới hạn concurrency của tác vụ nền có thể giảm cạnh tranh với workload trực tuyến.

### Memory leak hoặc tăng trưởng bất thường

Nếu RSS của một process tăng liên tục mà không giảm theo workload, cần xem memory clerk/allocator, extension, driver, plugin, query cache hoặc lỗi phiên bản. Phân biệt leak với cache tăng có chủ đích hoặc workload tăng; không tự động restart định kỳ như biện pháp thay thế việc chẩn đoán.

## 8. PostgreSQL: shared_buffers, work_mem và backend memory

PostgreSQL sử dụng shared memory cho `shared_buffers` và các cấu trúc dùng chung. Mỗi backend/process có bộ nhớ riêng; các thao tác sort và hash có thể cấp phát work memory riêng.

### shared_buffers

`shared_buffers` xác định kích thước shared buffer cache chính. Tăng tham số này có thể cải thiện cache hit nếu working set phù hợp, nhưng phải để RAM cho backend, hệ điều hành, filesystem cache, maintenance và các dịch vụ khác. Không đặt theo tỷ lệ máy móc mà không đo workload và cấu hình OS.

### work_mem

`work_mem` là giới hạn cơ sở cho mỗi thao tác sort hoặc hash trước khi cần dùng file tạm, không phải một ngân sách duy nhất cho toàn database hoặc mỗi connection. Một truy vấn có nhiều operator có thể dùng nhiều vùng work memory; nhiều truy vấn đồng thời làm tổng nhu cầu tăng mạnh. Hash operation có thể dùng thêm hệ số `hash_mem_multiplier` tùy phiên bản.

Ví dụ, đặt `work_mem` ở mức 64 MB không có nghĩa tổng bộ nhớ sort/hash của database tối đa 64 MB. Một truy vấn có nhiều sort/hash và nhiều session chạy song song có thể tiêu thụ nhiều lần mức đó.

### maintenance_work_mem và autovacuum

`maintenance_work_mem` ảnh hưởng một số thao tác bảo trì như tạo index và vacuum. Autovacuum worker có thể dùng `autovacuum_work_mem` hoặc giá trị kế thừa theo cấu hình. Nhiều worker chạy đồng thời làm tổng bộ nhớ bảo trì tăng.

### Quan sát

- `pg_stat_activity` giúp xem session và query đang chạy.
- `pg_stat_database` có các bộ đếm file tạm như `temp_files` và `temp_bytes`.
- `EXPLAIN (ANALYZE, BUFFERS)` giúp xác định sort/hash, số hàng và I/O.
- Log có thể ghi nhận temporary file theo cấu hình phù hợp.
- `pg_stat_statements` hỗ trợ liên kết chi phí với query fingerprint nếu extension được bật.

Khi điều chỉnh `work_mem`, nên thử ở phạm vi session hoặc transaction cho một workload đã xác định trước khi tăng toàn cục. Cần theo dõi số truy vấn đồng thời, temp bytes, memory pressure và OOM.

## 9. SQL Server: buffer pool, memory grant và max server memory

SQL Server dùng memory manager và các memory clerk cho buffer pool, plan cache, query execution và nhiều cấu trúc nội bộ. `max server memory` là giới hạn quan trọng để điều tiết bộ nhớ SQL Server, nhưng không đại diện hoàn hảo cho mọi khoản tiêu thụ ngoài tiến trình hoặc mọi vùng native; vẫn phải để RAM cho Windows, driver, backup agent và phần mềm khác.

### Memory grant

Các thao tác sort và hash có thể yêu cầu memory grant khi bắt đầu thực thi. Nếu không cấp đủ grant, truy vấn có thể phải chờ, thường được quan sát qua wait `RESOURCE_SEMAPHORE`, hoặc spill dữ liệu ra tempdb khi grant không đủ.

Các DMV hữu ích tùy phiên bản và quyền:

```sql
SELECT *
FROM sys.dm_exec_query_memory_grants;

SELECT *
FROM sys.dm_os_memory_clerks;
```

Hãy xem requested/required/granted/used memory, số grant đang chờ và query plan. Một query được cấp grant lớn nhưng dùng ít có thể giữ tài nguyên cần thiết cho query khác; grant quá nhỏ lại làm spill.

### max server memory

Đặt `max server memory` quá cao có thể làm Windows thiếu headroom; đặt quá thấp có thể khiến buffer pool co lại và tăng physical reads. Cần tính cả bộ nhớ ngoài phần được giới hạn, các instance SQL Server khác và dịch vụ cùng host.

### Spill và tempdb

Sort/hash spill ra tempdb thường là dấu hiệu work area không đủ hoặc query xử lý quá nhiều dữ liệu. Tempdb I/O tăng có thể khiến truy vấn chậm hơn và làm tăng tải storage. Trước khi tăng grant hoặc cấu hình, kiểm tra cardinality estimate, index, projection và concurrency.

## 10. MySQL/InnoDB: buffer pool và bộ nhớ theo kết nối

InnoDB dùng `innodb_buffer_pool_size` cho cache page dữ liệu và index. Đây thường là vùng bộ nhớ lớn của instance, nhưng `mysqld` còn cần bộ nhớ cho connection, thread, Performance Schema, internal temporary table và các cấu trúc khác.

### Bộ nhớ theo kết nối

Một số buffer như sort buffer, join buffer, read buffer hoặc buffer cho thao tác khác có thể được cấp phát khi cần cho từng thread/operation. Đặt chúng quá lớn cùng với `max_connections` cao làm tăng rủi ro peak memory. Không nên nhân mọi tham số với số connection rồi coi đó là mức dùng chắc chắn, vì cấp phát phụ thuộc đường truy vấn; nhưng phải dùng concurrency đỉnh để đánh giá kịch bản xấu.

### Internal temporary table

Một số truy vấn cần bảng tạm nội bộ cho sort, group, distinct hoặc xử lý trung gian. Tùy phiên bản và cấu hình, bảng tạm có thể ở RAM rồi chuyển sang disk khi vượt giới hạn hoặc không phù hợp kiểu dữ liệu. Theo dõi số bảng tạm trên disk, query plan và I/O liên quan.

### Quan sát

- `SHOW GLOBAL STATUS` cung cấp nhiều bộ đếm về kết nối và temporary table.
- Performance Schema có instrumentation cho memory và statement nếu được bật.
- `SHOW ENGINE INNODB STATUS` giúp xem trạng thái InnoDB, không thay thế đo memory tổng thể.
- `EXPLAIN ANALYZE` ở phiên bản hỗ trợ giúp đánh giá số hàng và chi phí truy vấn.

Tăng buffer pool có thể giúp khi working set lớn và host còn headroom. Trước khi tăng, tính cả connection buffers, internal temp tables, replication, backup và memory của hệ điều hành.

## 11. Oracle Database: SGA, PGA và work area

Oracle phân biệt bộ nhớ dùng chung trong SGA và bộ nhớ riêng của process/session trong PGA. SGA chứa các thành phần như buffer cache, shared pool và redo log buffer. PGA giữ vùng làm việc riêng của process, gồm sort/hash work area và các cấu trúc riêng khác.

### SGA và PGA

ASMM hoặc AMM có thể tự điều chỉnh một số thành phần theo cấu hình và phiên bản. `PGA_AGGREGATE_TARGET` là mục tiêu tổng thể cho PGA work area trong chế độ phù hợp; `PGA_AGGREGATE_LIMIT` là giới hạn có thể khiến một số thao tác/session bị kết thúc khi vượt mức. Cần hiểu chế độ quản lý bộ nhớ đang dùng trước khi thay đổi tham số.

### Work area và TEMP

Sort hoặc hash join có thể chạy trong PGA nếu đủ bộ nhớ; nếu thiếu, thao tác có thể chuyển sang TEMP tablespace. Theo dõi số work area optimal/one-pass/multipass và lượng TEMP sử dụng. Multipass hoặc spill nhiều có thể làm I/O tăng đáng kể.

### Quan sát

- `V$PGASTAT` cung cấp thống kê PGA.
- `V$SQL_WORKAREA` và view liên quan giúp quan sát work area của câu SQL.
- `V$PROCESS` và `V$SGASTAT` hỗ trợ xem phân bổ bộ nhớ process/SGA.
- AWR/ASH có thể hỗ trợ phân tích lịch sử khi môi trường có quyền sử dụng phù hợp.

Các lỗi như `ORA-04030` thường liên quan cấp phát process memory; `ORA-04031` thường liên quan không cấp phát được vùng shared pool. Cần đọc thông báo chi tiết và trace để xác định thành phần thiếu, thay vì chỉ tăng một tham số tổng thể.

## 12. Database trong container và giới hạn cgroup

Khi database chạy trong Docker hoặc Kubernetes, giới hạn bộ nhớ của container có thể thấp hơn RAM host. Một tiến trình nhìn thấy RAM host nhưng bị cgroup giới hạn có thể bị OOM-kill khi vượt `memory.max` hoặc giới hạn tương đương.

### Tính theo giới hạn thực tế

Ngân sách database phải dựa trên giới hạn cgroup áp dụng cho container/pod, đồng thời tính sidecar nếu chúng chia sẻ cùng giới hạn pod. Không cấu hình buffer pool hoặc shared memory theo toàn bộ RAM host nếu container chỉ được cấp một phần.

### Requests và limits

Trong Kubernetes, memory request ảnh hưởng đến lập lịch và mức tài nguyên được bảo đảm theo chính sách cluster; memory limit là giới hạn cứng của container trong cách triển khai thông thường. Một pod có request thấp nhưng limit cao có thể hoạt động trong điều kiện node còn tài nguyên rồi bị ảnh hưởng khi node chịu áp lực. Cần đặt request/limit phù hợp và theo dõi eviction/OOM events.

### Quan sát cgroup

Trên Linux cgroup v2, có thể quan sát các file như:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
```

Đường dẫn có thể khác khi chạy trong namespace hoặc runtime khác. `memory.events` giúp phát hiện số lần chạm giới hạn/OOM theo cgroup. Hãy kết hợp số liệu container với process RSS và host memory; chỉ nhìn host `free -h` có thể bỏ sót giới hạn của container.

### Headroom cho sidecar và tiến trình phụ

Exporter, log shipper, service mesh sidecar, backup agent và init process cũng có thể dùng RAM trong pod. Nếu database được cấp gần hết limit, chỉ một spike nhỏ của sidecar cũng có thể khiến container bị kill.

## 13. Điều chỉnh bộ nhớ theo thứ tự an toàn

Khi thấy memory pressure, không nên đồng thời tăng cache, tăng work memory và tăng connection limit. Hãy xử lý theo thứ tự có thể đo và kiểm soát:

1. **Xác định phạm vi:** host, container, database process, session hay một query cụ thể?
2. **Xác định thời điểm:** áp lực liên tục hay chỉ xuất hiện khi batch, backup, report hoặc peak traffic?
3. **Tìm nhóm tiêu thụ:** shared cache, process memory, query grant/work area, temp, maintenance hay ứng dụng phụ trợ?
4. **Kiểm tra concurrency:** số session hoạt động, worker song song, query cùng chạy và tác vụ bảo trì.
5. **Tối ưu truy vấn:** giảm hàng/cột đầu vào, tránh sort/hash không cần, sửa estimate sai và dùng index phù hợp.
6. **Giới hạn tải:** pool connection, workload queue, batch size và số tác vụ nền đồng thời.
7. **Điều chỉnh cache/work area:** thay đổi từng tham số trong phạm vi nhỏ, dựa trên số liệu và tài liệu đúng phiên bản.
8. **Đặt headroom:** giữ RAM cho OS, failover, spike và tiến trình phụ.
9. **Kiểm thử dưới tải:** đo latency, throughput, spill, swap, OOM và cache behavior.
10. **Triển khai có giám sát:** đặt ngưỡng cảnh báo và kế hoạch rollback.

### Ưu tiên giảm nhu cầu trước khi tăng giới hạn

Nếu một truy vấn hash join xử lý 50 triệu hàng trong khi chỉ cần vài nghìn, giảm dữ liệu đầu vào có thể mang lại lợi ích lớn hơn tăng memory grant. Nếu ứng dụng mở 2.000 connection nhưng chỉ có 100 truy vấn hữu ích đồng thời, connection pool và giới hạn concurrency có thể giảm bộ nhớ đáng kể.

Tăng RAM hoặc cache phù hợp khi số liệu chứng minh working set thực sự cần lớn hơn và hệ thống có thể cấp thêm tài nguyên. Không dùng tăng RAM để che query plan sai, connection leak hoặc memory leak.

## 14. Quy trình xử lý khi swap tăng hoặc OOM xảy ra

Khi có cảnh báo, ưu tiên giữ lại bằng chứng trước khi thay đổi cấu hình hoặc restart.

### Khi swap-in/swap-out tăng

- Ghi nhận thời điểm, swap I/O, available memory, major faults và storage latency.
- Xác định process/container có RSS hoặc memory.current tăng nhanh.
- Kiểm tra database sessions, query đang chạy, work area, temp spill và tác vụ bảo trì.
- Kiểm tra connection pool, batch job và ứng dụng khác trên cùng host.
- Giảm concurrency hoặc tạm dừng workload không thiết yếu theo quy trình vận hành.
- Sau khi ổn định, tối ưu query và điều chỉnh ngân sách; không chỉ xóa swap hoặc reboot để che dấu nguyên nhân.

### Khi OOM killer hoặc container OOM-killed

- Thu thập kernel log, container event, cgroup memory events và database error log.
- Xác định process bị kill, thời điểm, memory limit và workload đang chạy.
- Kiểm tra database có crash recovery hay replica bị lag sau sự cố.
- Khôi phục dịch vụ theo runbook và giới hạn reconnect storm.
- Tìm query, session, tác vụ nền hoặc giới hạn cấu hình tạo peak.
- Thực hiện load test có kiểm soát trước khi đưa tải đầy đủ trở lại.

Ví dụ lệnh Linux để tìm thông tin kernel OOM:

```bash
dmesg -T | grep -i -E 'out of memory|killed process'
journalctl -k --since '30 minutes ago'
```

Quyền truy cập và tên log phụ thuộc hệ điều hành. Trên Kubernetes, kiểm tra trạng thái container như `OOMKilled`, sự kiện pod và log trước khi container bị khởi động lại. Không kết luận process bị OOM chỉ từ việc service restart; cần bằng chứng từ kernel/runtime hoặc error log.

## 15. Theo dõi bộ nhớ bằng dashboard

Một dashboard hữu ích nên có cả tín hiệu tổng thể và chi tiết theo database/query.

| Nhóm | Metric | Cách dùng |
|---|---|---|
| Host | Available RAM, memory pressure, page faults | Phát hiện headroom giảm và reclaim tăng |
| Host | Swap-in/out rate, swap I/O, major faults | Phân biệt swap cũ với swap đang hoạt động |
| Process | RSS, virtual size, private/shared memory | Xác định process tăng bộ nhớ |
| Container | memory.current, memory.max, memory.events | Phát hiện tiến gần limit và OOM |
| Database cache | Buffer/cache hit, page reads, cache churn | Đánh giá working set và hiệu quả cache |
| Query | Memory grant, work area, sort/hash spill, temp bytes | Tìm truy vấn tiêu thụ nhiều workspace |
| Concurrency | Active sessions, workers, queued requests | Liên kết memory peak với tải đồng thời |
| Sự cố | OOM events, allocation errors, restarts | Xác định sự kiện nghiêm trọng và xu hướng |

Nên đặt cảnh báo theo xu hướng và headroom thay vì chỉ dùng một ngưỡng phần trăm RAM. Ví dụ, available memory giảm liên tục cùng swap-in tăng và p99 latency tăng là tín hiệu mạnh hơn riêng việc RAM đã dùng 90%.

### Phân tích theo khoảng thời gian

Counter tích lũy cần lấy chênh lệch giữa hai thời điểm. Khi so sánh trước/sau, giữ cùng khoảng thời gian và tải tương đương. Gắn dashboard với query fingerprint, deploy, batch schedule và sự kiện failover để nhận diện thay đổi nguyên nhân.

## 16. Kiểm thử sức chịu tải bộ nhớ

Một cấu hình chỉ an toàn khi được thử ở mức tải và concurrency đại diện. Kịch bản kiểm thử nên gồm:

1. Workload đọc nóng để đánh giá buffer cache.
2. Workload sort/hash để đánh giá query work area và temp spill.
3. Tải kết nối đồng thời ở mức dự kiến cao điểm.
4. Tác vụ bảo trì hoặc báo cáo chạy cùng workload trực tuyến.
5. Một đợt tăng tải ngắn để đánh giá headroom.
6. Kịch bản container chạm ngưỡng gần limit trong môi trường kiểm thử để xác minh cảnh báo và runbook.

Theo dõi throughput, p95/p99, available memory, RSS, swap I/O, query spill, memory grant wait, temp I/O và OOM event. Không cố tình gây OOM trên production để kiểm tra phản ứng.

### Tiêu chí chấp nhận

- Không có swap thrashing trong workload bình thường.
- Có headroom cho tác vụ bảo trì và peak traffic đã xác định.
- Không có OOM hoặc allocation error ở mức concurrency mục tiêu.
- Query spill nằm trong mức chấp nhận được và không tạo temp I/O bất thường.
- p95/p99 ổn định khi tăng concurrency trong phạm vi dự kiến.
- Cache và work area không tranh giành RAM đến mức gây suy giảm lẫn nhau.
- Failover hoặc reconnect burst không làm vượt memory limit.

## 17. Những sai lầm thường gặp

1. **Dành gần hết RAM cho buffer cache:** không còn headroom cho session, query work area và OS.
2. **Xem swap đã dùng là bằng chứng thrashing:** cần xem swap-in/out và tác động latency theo thời gian.
3. **Tắt swap mà không có dự phòng:** có thể làm OOM xảy ra sớm hơn khi có spike.
4. **Tăng work memory toàn cục:** nhiều operator và nhiều query đồng thời có thể nhân nhu cầu lên rất lớn.
5. **Đặt max_connections quá cao:** session và worker có thể làm bộ nhớ đỉnh vượt ngân sách.
6. **Dựa vào RAM host khi chạy container:** database có thể bị cgroup kill dù host còn RAM.
7. **Chỉ xem cache hit ratio:** không phát hiện memory grant wait, swap hoặc OOM ở tiến trình khác.
8. **Tăng RAM để che query plan kém:** hash/sort xử lý quá nhiều dữ liệu vẫn có thể tiêu thụ hết bộ nhớ mới.
9. **Không tính tác vụ bảo trì:** index build, vacuum, backup và báo cáo có thể trùng giờ peak.
10. **Restart mà không thu thập log:** làm mất bằng chứng về process, query và giới hạn gây OOM.
11. **Đặt container limit bằng đúng memory của database cache:** không còn chỗ cho allocator, sidecar và kernel accounting.
12. **Dùng một ngưỡng cảnh báo cho mọi máy:** workload, hệ điều hành và engine có đặc tính khác nhau.

## 18. Danh sách kiểm tra trước khi điều chỉnh

- [ ] Đã xác định giới hạn RAM thực tế của host, VM hoặc container.
- [ ] Đã lập ngân sách cho OS, cache dùng chung, session, query work area, bảo trì và ứng dụng phụ trợ.
- [ ] Đã đo available memory, process RSS, cgroup usage và xu hướng theo thời gian.
- [ ] Đã phân biệt swap đã dùng với swap-in/swap-out đang hoạt động.
- [ ] Đã kiểm tra major page faults, memory pressure, storage latency và OOM events.
- [ ] Đã xác định query, session hoặc tác vụ nền tiêu thụ nhiều bộ nhớ.
- [ ] Đã kiểm tra sort/hash spill, memory grant wait và temp I/O.
- [ ] Đã đánh giá connection pool, max connections và parallel workers.
- [ ] Đã kiểm tra tham số cache/work area theo đúng hệ quản trị và phiên bản.
- [ ] Đã giữ headroom cho OS, sidecar, peak traffic, failover và bảo trì.
- [ ] Đã kiểm thử dưới tải đại diện và có cảnh báo/rollback.
- [ ] Đã chuẩn bị runbook thu thập bằng chứng và phục hồi khi swap/OOM xảy ra.

Áp lực bộ nhớ xuất hiện khi working set, cache, session, query work area và tác vụ nền cùng vượt ngân sách RAM an toàn. Swap chỉ là cơ chế hỗ trợ bộ nhớ ảo; hoạt động swap-in/swap-out liên tục có thể tạo thrashing và làm database chậm nghiêm trọng. OOM có thể khiến hệ điều hành hoặc container kết thúc tiến trình database, dẫn đến gián đoạn và crash recovery. Hãy lập ngân sách theo concurrency đỉnh, theo dõi cả host lẫn giới hạn container, tối ưu lượng dữ liệu và số truy vấn đồng thời trước khi tăng cache/work memory, rồi kiểm chứng bằng latency, spill, swap, OOM và khả năng phục hồi dưới tải đại diện.
