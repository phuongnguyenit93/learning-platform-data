# shared_buffers và quan hệ với cache hệ điều hành trong PostgreSQL

PostgreSQL có thể giữ các trang dữ liệu trong bộ nhớ ở nhiều tầng. Tầng do PostgreSQL quản lý là **shared_buffers**; tầng do kernel và hệ điều hành quản lý thường là **filesystem page cache**. Khi query đọc một block, PostgreSQL kiểm tra shared_buffers trước. Nếu block chưa có ở đó, PostgreSQL yêu cầu hệ điều hành đọc file relation; dữ liệu có thể đã nằm trong page cache của OS hoặc phải được đọc từ storage.

Vì vậy, một lần đọc bị tính là cache miss ở PostgreSQL chưa chắc đã tạo ra một lần đọc vật lý từ disk. Block có thể được lấy rất nhanh từ OS page cache. Ngược lại, shared_buffers lớn hơn không phải lúc nào cũng làm query nhanh hơn: nó cạnh tranh RAM với page cache, backend processes, sort/hash operations, autovacuum và các thành phần khác.

Cần phân biệt rõ các vùng nhớ:

- **shared_buffers:** cache các database pages được PostgreSQL dùng chung giữa các backend.
- **OS page cache:** cache file contents do kernel quản lý, bao gồm các file relation PostgreSQL truy cập qua filesystem.
- **work_mem:** bộ nhớ cho một số sort/hash operations; có thể được cấp nhiều lần trong một query và nhiều session.
- **temp_buffers:** buffer riêng cho temporary tables của mỗi session.
- **wal_buffers:** vùng đệm WAL, khác với cache của table/index pages.
- **effective_cache_size:** ước lượng cho planner về lượng cache có thể dùng; không cấp phát RAM.

~~~text
               Query đọc một table/index block
                            |
                            v
                 PostgreSQL shared_buffers
                       /          \
                  cache hit      cache miss
                     |               |
                     v               v
                Dùng page       Kernel đọc file
                trong RAM           |
                                    v
                          OS filesystem page cache
                              /             \
                         cache hit        cache miss
                            |                 |
                            v                 v
                       RAM của OS        Storage device
                            \                 /
                             \               /
                              v             v
                          Block trả về PostgreSQL
                                    |
                                    v
                              shared_buffers

Hai tầng cache có mục đích và chính sách quản lý khác nhau.
~~~

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Tối ưu tài nguyên**, với đề tài **“shared_buffers và quan hệ với cache hệ điều hành”**. Nội dung tập trung vào đường đi đọc/ghi, cách hai tầng cache phối hợp, lựa chọn kích thước, cách đo cache behavior và phương pháp kiểm thử tuning có kiểm soát.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của shared_buffers trong PostgreSQL.
2. Phân biệt PostgreSQL shared buffer cache với OS filesystem page cache.
3. Mô tả đường đi của một block khi shared buffer hit, OS cache hit và storage read.
4. Giải thích vì sao PostgreSQL cache miss không đồng nghĩa physical disk read.
5. Mô tả cách PostgreSQL quản lý buffer pages và dirty buffers.
6. Phân biệt data buffers với work_mem, temp_buffers và wal_buffers.
7. Hiểu cách read, write, checkpoint và WAL tương tác với hai tầng cache.
8. Giải thích ý nghĩa và giới hạn của cache hit ratio.
9. Sử dụng pg_stat_database, pg_statio_* và pg_stat_io để quan sát I/O.
10. Dùng EXPLAIN (ANALYZE, BUFFERS) để xem shared/local/temp buffer activity.
11. Biết khi nào pg_buffercache và pg_prewarm có ích.
12. Hiểu effective_cache_size và vì sao nó không cấp phát bộ nhớ.
13. Chọn shared_buffers ban đầu theo RAM, workload và operating system.
14. Tính ngân sách memory cho shared_buffers, backend và OS cache.
15. Nhận biết memory pressure, swap và OOM risk.
16. Đánh giá tác động của shared_buffers lên checkpoint và writeback.
17. Thay đổi shared_buffers an toàn và biết khi nào cần restart.
18. Thiết kế benchmark nóng/lạnh và so sánh trước/sau tuning.
19. Tránh các lỗi phổ biến khi diễn giải cache metrics.
20. Xây dựng checklist tuning và monitoring cho production.

**Phạm vi:** PostgreSQL hiện đại trên Linux, Windows và các môi trường cloud/container. PostgreSQL thường dùng filesystem cache của OS cùng shared_buffers. Chi tiết thống kê I/O thay đổi theo major version; pg_stat_io có từ PostgreSQL 16. Các giá trị sizing trong bài là điểm bắt đầu để thử nghiệm, không phải cấu hình bắt buộc cho mọi workload.

---

## 2. shared_buffers là gì?

shared_buffers là vùng bộ nhớ shared memory mà PostgreSQL dành để cache các pages của relation files. Các backend cùng truy cập vùng buffer này thay vì mỗi session tự giữ một bản sao page riêng.

### 2.1. Một buffer thường chứa một database page

PostgreSQL thường được build với block size 8 KB. Một shared buffer giữ một block dữ liệu tương ứng với page của table, index hoặc relation khác. Block size được xác định khi build PostgreSQL và có thể kiểm tra bằng:

~~~sql
SHOW block_size;
~~~

Kích thước thực tế của shared_buffers được cấu hình bằng tham số cùng tên:

~~~sql
SHOW shared_buffers;
~~~

### 2.2. Đây là cache ở mức database

shared_buffers chứa page đã đọc từ relation hoặc page được thay đổi bởi database. Nó không phải cache kết quả SELECT, không phải cache execution plan và không lưu toàn bộ object như một bản copy độc lập.

Một query có thể đọc nhiều pages; một page có thể được dùng bởi nhiều queries và sessions.

### 2.3. Chia sẻ giữa các backend

Các PostgreSQL backend phối hợp truy cập shared buffer pool bằng cơ chế đồng bộ nội bộ. Khi một backend cần page, nó tra cứu buffer mapping, pin buffer để page không bị thay thế trong lúc đang sử dụng và cập nhật metadata liên quan.

### 2.4. Buffer pool có giới hạn

Nếu cần một page mới mà buffer pool đã đầy, PostgreSQL phải tìm buffer có thể tái sử dụng. Nếu buffer được chọn đang dirty, page phải được ghi ra trước hoặc xử lý theo cơ chế writeback/checkpoint phù hợp.

### 2.5. shared_buffers không phải tổng RAM PostgreSQL

PostgreSQL còn sử dụng memory cho backend processes, query execution, maintenance, WAL, shared memory structures, extensions và các hoạt động khác. Không thể lấy shared_buffers làm đại diện cho toàn bộ memory footprint.

---

## 3. OS filesystem page cache là gì?

Filesystem page cache là bộ nhớ do kernel quản lý để giữ nội dung file đã được đọc hoặc ghi gần đây. PostgreSQL lưu table/index data trong relation files trên filesystem; khi PostgreSQL đọc các file này qua OS, kernel có thể trả dữ liệu từ page cache.

### 3.1. OS cache độc lập với shared_buffers

PostgreSQL không trực tiếp điều khiển toàn bộ page cache của OS. Kernel quyết định pages nào được giữ, thu hồi hoặc ghi xuống storage dựa trên memory pressure, access pattern và chính sách của hệ điều hành.

### 3.2. Một block có thể xuất hiện ở hai tầng

Khi PostgreSQL đọc một page từ file vào shared_buffers, dữ liệu có thể đồng thời được giữ trong OS page cache. Do đó, cùng nội dung có thể chiếm bộ nhớ ở cả hai tầng.

### 3.3. OS cache có thể giúp sau shared buffer miss

Nếu page bị loại khỏi shared_buffers nhưng còn trong OS page cache, PostgreSQL vẫn phải thực hiện thao tác đọc file, nhưng kernel có thể trả dữ liệu từ RAM mà không cần đọc storage device.

### 3.4. Kernel quản lý page cache theo toàn hệ thống

OS page cache có thể được dùng bởi PostgreSQL, backup tools, file scanners, monitoring agents và các process khác. Một process khác đọc file có thể làm nóng OS cache; memory pressure từ process khác có thể làm cache bị thu hồi.

### 3.5. OS cache không phải vùng memory dành riêng cho PostgreSQL

Không cấu hình page cache bằng cách đặt một tham số PostgreSQL. Theo dõi memory availability và cache behavior qua công cụ hệ điều hành hoặc cloud platform.

---

## 4. Hai tầng cache phối hợp ra sao?

Để hiểu performance, hãy lần theo một block khi PostgreSQL cần đọc.

### 4.1. Trường hợp A: shared buffer hit

1. Backend cần block của table/index.
2. PostgreSQL tìm thấy block trong shared_buffers.
3. Backend pin buffer và đọc page từ shared memory.
4. Không cần gọi OS để đọc relation file cho block đó.

Đây là đường đọc nhanh nhất trong hai tầng cache.

### 4.2. Trường hợp B: shared buffer miss, OS page cache hit

1. Backend không tìm thấy block trong shared_buffers.
2. PostgreSQL cần đưa block vào buffer pool.
3. PostgreSQL yêu cầu kernel đọc file relation.
4. Kernel tìm thấy file page trong page cache.
5. Kernel copy/ánh xạ dữ liệu vào buffer PostgreSQL.
6. PostgreSQL dùng block và cập nhật buffer metadata.

Trong trường hợp này pg_stat_database.blks_read có thể tăng, nhưng storage device có thể không thực hiện physical read.

### 4.3. Trường hợp C: miss ở cả hai tầng

1. Backend không tìm thấy block trong shared_buffers.
2. Kernel cũng không có page tương ứng trong page cache.
3. OS gửi I/O request tới storage device.
4. Storage trả dữ liệu.
5. Kernel và PostgreSQL nhận block.
6. Page có thể được giữ trong cả OS page cache và shared_buffers.

Đây thường là đường đọc tốn thời gian hơn, nhưng latency còn phụ thuộc SSD/HDD, network storage, queue, block size và concurrency.

### 4.4. Bảng so sánh

| Trạng thái | PostgreSQL shared_buffers | OS page cache | Storage device read |
| --- | --- | --- | --- |
| Shared hit | Có page | Không cần truy cập | Không |
| Shared miss, OS hit | Không có page | Có page | Thường không |
| Miss cả hai | Không có page | Không có page | Có, trừ khi storage layer có cache khác |

### 4.5. Nhiều lớp cache có thể tồn tại hơn

Cloud storage, storage controller, RAID controller, NVMe controller và SAN có thể có cache riêng. Một OS read không nhất thiết đi tới media vật lý. Khi cần xác định physical I/O, phải xem metrics ở đúng tầng storage.

---

## 5. Vì sao shared_buffers không thay OS page cache?

Hai tầng cache có vai trò bổ sung.

### 5.1. PostgreSQL biết semantics của database pages

PostgreSQL quản lý page usage, buffer pins, dirty pages, WAL ordering, checkpoints và các hoạt động database-specific. OS page cache không hiểu transaction hay relation semantics.

### 5.2. OS cache giúp giữ file pages ngoài shared_buffers

OS page cache có thể lưu data pages đã bị PostgreSQL đẩy khỏi shared_buffers. Điều này giúp giảm physical I/O khi workload quay lại đọc page.

### 5.3. PostgreSQL vẫn cần cache riêng

Nếu chỉ dựa vào OS page cache, PostgreSQL mất khả năng quản lý buffer pool theo nhu cầu của database engine. shared_buffers cho phép PostgreSQL phối hợp page pinning, dirty page tracking và background writing.

### 5.4. Không nên cố gắng loại bỏ OS cache theo mặc định

PostgreSQL thông thường được thiết kế để hoạt động cùng filesystem cache. Việc cố ép OS cache xuống thấp hoặc chọn I/O mode đặc biệt phải dựa trên version, workload và benchmark cụ thể.

### 5.5. Double caching là một trade-off

Cùng page có thể chiếm RAM ở cả shared_buffers và OS page cache. Đổi lại, hai tầng có thể giảm đọc storage và hỗ trợ access patterns khác nhau. Mục tiêu tuning là cân bằng memory, latency và throughput, không phải tối đa hóa một cache đơn lẻ.

---

## 6. Đường đi của thao tác ghi

Đọc và ghi có semantics khác nhau. Đặc biệt, commit không có nghĩa mọi data page đã được ghi ngay xuống storage.

### 6.1. UPDATE tạo dirty buffer

Khi transaction cập nhật row, PostgreSQL sửa page trong shared_buffers và đánh dấu buffer là dirty. WAL records mô tả thay đổi được tạo theo write-ahead logging rules.

### 6.2. WAL phải đi trước data page

WAL phải được ghi/flush theo durability requirements trước khi data page tương ứng được ghi bền vững. Đây là nguyên tắc write-ahead logging.

### 6.3. COMMIT thường chờ WAL flush

Với cấu hình durability thông thường, PostgreSQL flush WAL tới commit record trước khi báo commit thành công. Data pages thay đổi có thể vẫn nằm trong shared_buffers ở trạng thái dirty.

### 6.4. Dirty page được ghi sau đó

Background writer, checkpointer hoặc backend có thể ghi dirty pages ra file. Khi ghi file, dữ liệu đi qua OS và có thể nằm trong page cache trước khi được sync xuống storage theo quy trình durability.

### 6.5. Checkpoint

Checkpoint đảm bảo dirty pages và WAL đã đạt các điều kiện cần thiết để recovery bắt đầu từ checkpoint phù hợp. Checkpoint có thể tạo I/O burst nếu lượng dirty data lớn hoặc storage không đủ throughput.

### 6.6. Sơ đồ write path

~~~text
UPDATE row
   |
   +--> Sửa page trong shared_buffers (dirty)
   |
   +--> Tạo WAL record
           |
           v
       WAL buffers
           |
           v
       WAL file / flush theo commit policy
           |
           v
       COMMIT được xác nhận
           |
           | Data page có thể vẫn dirty
           v
   Background writer / checkpointer / backend
           |
           v
       Ghi relation file qua OS
           |
           v
       OS page cache / filesystem
           |
           v
       fsync và storage durability theo checkpoint
~~~

### 6.7. shared_buffers không phải write-through cache

Một transaction không cần ghi toàn bộ modified data pages ra disk ngay tại COMMIT. WAL cho phép PostgreSQL redo thay đổi sau crash. Đây là lý do commit latency thường gắn trực tiếp với WAL flush hơn là thời gian ghi toàn bộ table pages.

### 6.8. OS page cache cũng liên quan durability

Write vào file có thể chỉ cập nhật kernel page cache. PostgreSQL dùng fsync hoặc cơ chế đồng bộ tương ứng để bảo đảm dữ liệu cần thiết đã tới storage theo semantics mà hệ thống hỗ trợ. Storage phải thực hiện flush/barrier đúng hợp đồng.

---

## 7. Các vùng memory khác không nên nhầm với shared_buffers

### 7.1. work_mem

work_mem được dùng cho một số sort, hash join, hash aggregation và operations tương tự. Một query có thể dùng nhiều work_mem allocations; nhiều sessions chạy đồng thời có thể làm memory usage tăng mạnh.

### 7.2. temp_buffers

temp_buffers là buffer pool riêng cho temporary tables của từng session. Nó không phải shared_buffers và thường được cấp phát khi session cần dùng.

### 7.3. wal_buffers

wal_buffers giữ WAL records trước khi ghi WAL files. Đây không phải cache table/index pages. Nó liên quan write path và WAL throughput.

### 7.4. maintenance_work_mem

Được dùng cho một số maintenance tasks như VACUUM và CREATE INDEX. Autovacuum có thể có budget riêng qua autovacuum_work_mem.

### 7.5. Backend-local memory

Mỗi backend còn có memory contexts, executor state, tuple slots, sort/hash state và allocations khác. Tổng memory phụ thuộc query complexity và concurrency.

### 7.6. effective_cache_size

Đây là ước lượng planner về lượng memory có thể dùng để cache data, thường gồm shared_buffers và phần OS cache có thể truy cập, sau khi cân nhắc cạnh tranh. Nó không cấp phát RAM và không tạo cache.

### 7.7. Tóm tắt

| Thành phần | Phạm vi | Mục đích |
| --- | --- | --- |
| shared_buffers | Shared giữa PostgreSQL backends | Cache relation pages |
| OS page cache | Toàn OS | Cache file pages |
| work_mem | Theo operation/backend | Sort/hash execution |
| temp_buffers | Theo session | Temporary table buffers |
| wal_buffers | Shared WAL buffer area | Buffer WAL records |
| maintenance_work_mem | Maintenance operation | VACUUM/index maintenance |
| effective_cache_size | Planner estimate | Ước lượng cache có thể dùng |

---

## 8. shared_buffers ảnh hưởng performance thế nào?

### 8.1. Có thể giảm đọc từ OS

Nếu workload thường xuyên truy cập cùng một tập pages và tập đó vừa shared_buffers, cache hit có thể cao hơn và latency ổn định hơn.

### 8.2. Có thể giảm storage reads

Một page được giữ trong shared_buffers không cần đọc lại từ file. Điều này giảm calls tới OS và có thể giảm I/O load.

### 8.3. Có thể tăng writeback pressure

shared_buffers lớn cho phép nhiều dirty pages tồn tại. Checkpoint phải xử lý lượng dirty data tương ứng. Nếu storage throughput không đủ, checkpoint có thể kéo dài hoặc tạo latency spikes.

### 8.4. Có thể làm giảm OS page cache

Nếu shared_buffers chiếm quá nhiều RAM, kernel còn ít memory hơn để cache file pages của PostgreSQL và các ứng dụng khác. Một shared buffer miss khi đó có thể dễ đi tới storage hơn.

### 8.5. Có thể giảm memory cho query execution

Nếu dành quá nhiều RAM cho shared_buffers, backend operations, autovacuum, OS và monitoring agents có thể bị thiếu memory.

### 8.6. Lợi ích có diminishing returns

Tăng shared_buffers từ rất nhỏ lên mức hợp lý có thể cải thiện workload cache-sensitive. Tăng tiếp có thể đem lại ít lợi ích, thậm chí làm xấu tổng thể nếu memory pressure tăng.

### 8.7. Không phải mọi workload đều cache-friendly

- Sequential scan lớn có thể đọc nhiều dữ liệu một lần.
- Workload analytics có working set lớn hơn RAM.
- Workload random OLTP có thể hưởng lợi khi hot set nằm trong cache.
- Index-heavy workload có thể liên tục truy cập một tập index pages.
- Batch jobs có thể làm thay đổi cache residency của workload tương tác.

Cần xác định working set và access pattern trước khi sizing.

---

## 9. Chọn kích thước shared_buffers ban đầu

Tài liệu PostgreSQL thường nêu khoảng **25% RAM** là điểm khởi đầu hợp lý trên dedicated database server. Mức lớn hơn khoảng **40% RAM** thường không đem lại lợi ích tương ứng vì PostgreSQL vẫn dựa vào OS cache. Đây là hướng dẫn ban đầu, không phải quy tắc cố định.

### 9.1. Ví dụ sizing sơ bộ

| RAM vật lý | 25% RAM làm điểm bắt đầu | Ghi chú |
| ---: | ---: | --- |
| 8 GB | 2 GB | Kiểm tra memory headroom kỹ |
| 16 GB | 4 GB | Cân bằng backend và OS cache |
| 32 GB | 8 GB | Đo working set và I/O |
| 64 GB | 16 GB | Không tự động tăng lên 32 GB |
| 128 GB | 32 GB | Cần benchmark workload thực tế |

Các con số chỉ minh họa phép tính 25%. Chúng không tính container memory limits, OS services, connection concurrency, query memory hoặc các process khác.

### 9.2. Dedicated server

Nếu máy chỉ chạy PostgreSQL, có thể dành tỷ lệ RAM lớn hơn cho PostgreSQL so với host chạy nhiều ứng dụng. Tuy vậy, OS vẫn cần RAM cho page cache và kernel.

### 9.3. Shared host

Nếu host chạy PostgreSQL cùng application, agents, backup processes hoặc nhiều database instances, hãy tính tổng memory của tất cả workloads trước khi đặt shared_buffers.

### 9.4. Container

Giới hạn cgroup/container có thể thấp hơn RAM vật lý host. Sizing phải theo memory limit thực tế mà PostgreSQL process nhìn thấy và được phép dùng, đồng thời chừa headroom cho sidecars và kernel accounting theo môi trường.

### 9.5. Managed database

Cloud provider có thể tự đặt shared_buffers theo instance class và giới hạn service. Kiểm tra tham số hiệu lực và policy của provider trước khi tuning.

### 9.6. Hệ điều hành

Windows và một số môi trường có đặc tính memory/shared memory khác Linux. Không bê nguyên sizing từ một OS sang OS khác mà không đo.

---

## 10. Ngân sách RAM tổng thể

Đặt shared_buffers cần tính cả các memory consumers khác.

### 10.1. Các thành phần cần dự trù

- shared_buffers.
- WAL buffers và các shared memory structures.
- Backend process memory.
- work_mem cho sort/hash operations đồng thời.
- temp_buffers cho sessions dùng temporary tables.
- maintenance_work_mem.
- autovacuum workers và parallel workers.
- Extensions và background workers.
- OS kernel, filesystem page cache và monitoring agents.
- Backup/compression tools chạy cùng host.
- Container sidecars nếu có.

### 10.2. work_mem có thể nhân lên

work_mem không phải một pool duy nhất được chia đều. Một query có thể có nhiều sort/hash nodes và nhiều parallel workers. Nhiều sessions chạy đồng thời có thể cấp phát nhiều lần.

### 10.3. Công thức ngân sách khái niệm

~~~text
RAM cần có
  >= shared_buffers
   + shared/WAL/process overhead
   + peak concurrent query memory
   + maintenance/autovacuum memory
   + OS/kernel/page cache headroom
   + các process ngoài PostgreSQL
~~~

Đây là cách phân nhóm để lập ngân sách, không phải công thức cộng chính xác mọi giá trị cấu hình tối đa. Cần dùng concurrency thực tế và đo peak memory.

### 10.4. Tránh swap như cơ chế mở rộng RAM

Swap-in/out nhiều có thể làm latency tăng mạnh và tạo hiệu ứng dây chuyền. Một server database thiếu RAM nên được xử lý qua workload/concurrency/configuration/capacity, không dựa vào swap để duy trì throughput.

### 10.5. OOM risk

Nếu kernel/container OOM killer dừng PostgreSQL backend hoặc process quan trọng, có thể xảy ra query failure hoặc server restart. Theo dõi OOM events cùng memory pressure.

---

## 11. effective_cache_size: planner estimate, không phải allocation

effective_cache_size là tham số planner dùng để ước lượng lượng cache có sẵn cho một query. Planner dùng estimate này khi cân nhắc chi phí index scan so với sequential scan và các lựa chọn plan khác.

### 11.1. Không chiếm RAM

Đặt effective_cache_size = 24GB không cấp phát 24GB và không làm OS cache tăng lên.

### 11.2. Bao gồm nhiều tầng cache

Ước lượng thường tính phần shared_buffers cộng với phần OS page cache có thể dùng cho database, trừ đi memory bị các workloads khác chiếm.

### 11.3. Estimate quá thấp

Planner có thể đánh giá thấp khả năng giữ pages trong cache và chọn plan không tối ưu trong một số workload.

### 11.4. Estimate quá cao

Planner có thể giả định index access rẻ hơn thực tế, chọn plan dựa trên giả định cache không đạt được khi memory pressure cao.

### 11.5. Không đồng nhất với shared_buffers

shared_buffers là allocation thực tế; effective_cache_size là planner hint. Hai tham số phục vụ hai mục đích khác nhau.

### 11.6. Xem giá trị hiện tại

~~~sql
SHOW effective_cache_size;
SHOW shared_buffers;
~~~

Đặt estimate dựa trên RAM, shared_buffers, OS cache, workload cạnh tranh và observed memory behavior.

---

## 12. Buffer replacement và dirty pages

shared_buffers là pool hữu hạn. PostgreSQL phải quyết định page nào tiếp tục ở trong pool và page nào có thể bị thay thế.

### 12.1. Buffer mapping

PostgreSQL tra cứu block theo relation/fork/block identity để tìm buffer đang chứa page đó.

### 12.2. Pinning

Backend pin buffer khi đang sử dụng để page không bị tái sử dụng trong lúc operation cần nó. Một buffer được pin không thể bị thay thế tùy tiện.

### 12.3. Usage count

PostgreSQL dùng metadata usage count để ước lượng page nào có khả năng còn được truy cập. Cơ chế clock-sweep đi qua buffer pool để tìm candidate phù hợp.

### 12.4. Dirty buffer

Page bị sửa trong memory và chưa được ghi ra relation file được gọi là dirty. Dirty buffer cần được xử lý trước khi buffer storage có thể tái sử dụng an toàn.

### 12.5. Background writer

Background writer có thể ghi một số dirty buffers trước khi backend cần buffer mới, giúp giảm tình huống backend tự ghi page trong foreground.

### 12.6. Checkpointer

Checkpointer đảm bảo dirty pages và WAL đạt checkpoint requirements. Checkpoint có thể ghi lượng lớn buffers, nên cần theo dõi write/sync time và storage throughput.

### 12.7. Không nên diễn giải replacement như LRU thuần

PostgreSQL sử dụng cơ chế buffer management riêng, có pinning và usage count. Nó không đơn giản loại bỏ page ít dùng nhất theo một danh sách LRU thuần túy.

---

## 13. Read path chi tiết

### 13.1. Query cần block

Executor cần một page của heap hoặc index. PostgreSQL xác định relation và block number.

### 13.2. Kiểm tra shared_buffers

Nếu block có sẵn, backend sử dụng page. Nếu không, buffer manager cần một buffer mới hoặc buffer có thể tái sử dụng.

### 13.3. Đọc qua filesystem

PostgreSQL thực hiện I/O với relation file theo I/O path của version/build. Trên đường thông thường, OS page cache có thể trả dữ liệu.

### 13.4. OS cache hit

Không có physical storage read ở thời điểm đó, nhưng vẫn có syscall/OS work và copy vào shared buffer.

### 13.5. OS cache miss

Kernel gửi request tới storage. Thời gian chờ có thể phụ thuộc queue, latency, network storage và device cache.

### 13.6. Page được đưa vào shared_buffers

Sau khi đọc xong, PostgreSQL cập nhật buffer metadata và query tiếp tục xử lý page.

### 13.7. Read-ahead và sequential access

OS/storage có thể prefetch data khi phát hiện sequential access. PostgreSQL cũng có các cơ chế I/O phù hợp cho một số access patterns. Do đó, một số sequential scans có thể hoạt động tốt dù cache hit ratio thấp.

---

## 14. Write path chi tiết

### 14.1. Page được sửa trong shared_buffers

UPDATE/INSERT/DELETE có thể làm thay đổi heap/index pages trong buffer pool.

### 14.2. WAL record được tạo

WAL mô tả các thay đổi cần thiết cho crash recovery và replication.

### 14.3. Commit và durability

Với synchronous_commit mặc định thông thường, PostgreSQL đợi local WAL flush theo durability policy trước khi xác nhận commit. Có các thiết lập khác có thể thay đổi thời điểm xác nhận.

### 14.4. Data page chưa nhất thiết được flush

Transaction có thể commit trong khi data pages vẫn dirty trong shared_buffers. Crash recovery sẽ dùng WAL để redo những thay đổi cần thiết.

### 14.5. Writeback

Background writer/checkpointer/backend ghi dirty pages ra file. OS có thể giữ các file pages trong page cache và thực hiện writeback xuống storage.

### 14.6. Checkpoint sync

Checkpoint cần đảm bảo các writes cần thiết được đồng bộ theo durability contract. Storage controller/device phải tuân thủ flush semantics.

### 14.7. Cache không loại bỏ durability requirements

Không tắt fsync hoặc full_page_writes chỉ để tăng benchmark. Các setting đó liên quan tới an toàn dữ liệu và recovery.

---

## 15. Checkpoint và kích thước shared_buffers

Tăng shared_buffers có thể làm thay đổi lượng dirty data và cách checkpoint tạo I/O.

### 15.1. Nhiều buffer hơn

Một pool lớn có thể giữ nhiều pages hơn, nhưng cũng có thể tích lũy nhiều dirty pages tùy workload.

### 15.2. Checkpoint pressure

Checkpoint phải xử lý dirty pages trong giới hạn thời gian/chu kỳ. Nếu lượng dirty data lớn, storage chậm hoặc checkpoint settings không phù hợp, latency có thể tăng.

### 15.3. Checkpoint completion target

checkpoint_completion_target điều tiết phân bố checkpoint writes trong khoảng checkpoint. Đây là tham số liên quan write behavior, không phải cách trực tiếp tăng cache hit ratio.

### 15.4. max_wal_size

max_wal_size ảnh hưởng checkpoint scheduling/pressure nhưng không phải hard limit cho mọi WAL retention và không thay replication slot/archive planning.

### 15.5. Theo dõi checkpoint stats

Tùy PostgreSQL version, xem pg_stat_bgwriter và/hoặc pg_stat_checkpointer. Từ PostgreSQL 17, checkpoint statistics được tách rõ hơn so với các phiên bản trước.

### 15.6. Không tăng shared_buffers để chữa checkpoint chậm

Nếu checkpoint chậm do storage throughput thấp, tăng buffer pool có thể làm tình hình tệ hơn. Xem write/sync time, dirty buffers, disk latency và WAL rate.

---

## 16. Đo cache hit ratio và hiểu đúng ý nghĩa

Một chỉ số phổ biến là buffer cache hit ratio ở mức database.

~~~sql
SELECT
    datname,
    blks_hit,
    blks_read,
    round(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_pct,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
~~~

### 16.1. blks_hit

Số block được tìm thấy trong PostgreSQL shared buffer cache theo thống kê database.

### 16.2. blks_read

Số block PostgreSQL phải đọc vào shared buffer. Nó không đồng nghĩa số physical reads từ storage device.

### 16.3. Hit ratio là aggregate

Một database có nhiều queries nhanh và một query rất chậm vẫn có thể có hit ratio tổng cao. Cần drill down tới table/query và latency.

### 16.4. Hit ratio thấp có thể bình thường

Một sequential scan lớn trên dữ liệu không cache-friendly có thể tạo nhiều block reads nhưng vẫn hiệu quả. Workload analytics thường có pattern khác OLTP.

### 16.5. Hit ratio cao không đảm bảo performance tốt

Query có thể chậm vì CPU, lock waits, bad plan, memory spills, network, serialization hoặc application pool waits dù mọi page đều được tìm thấy trong shared_buffers.

### 16.6. Không có ngưỡng thần kỳ

Không đặt mục tiêu 99% hoặc 99.9% cho mọi hệ thống. Đánh giá theo latency SLO, physical I/O, workload pattern và capacity.

### 16.7. Counter cần được đọc theo thời gian

blks_hit và blks_read là counters tích lũy. Lấy delta giữa các snapshots và xét stats_reset để xem behavior trong cửa sổ quan sát.

---

## 17. pg_statio views

Các views pg_statio_* cung cấp thống kê block I/O ở mức table/index/database.

### 17.1. Table statistics

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit
FROM pg_catalog.pg_statio_user_tables
ORDER BY heap_blks_read DESC
LIMIT 20;
~~~

### 17.2. Index statistics

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_blks_read,
    idx_blks_hit
FROM pg_catalog.pg_statio_user_indexes
ORDER BY idx_blks_read DESC
LIMIT 20;
~~~

### 17.3. Diễn giải

- heap_blks_hit: heap blocks được tìm thấy trong PostgreSQL shared buffers.
- heap_blks_read: heap blocks được đọc vào shared buffers.
- idx_blks_hit/idx_blks_read: tương tự cho index blocks.
- toast fields: thống kê liên quan TOAST storage.

### 17.4. Giới hạn

Các counters không cho biết chắc chắn physical device đã được đọc. Một PostgreSQL block read có thể được phục vụ từ OS cache.

### 17.5. Dùng để tìm hot objects

So sánh hit/read deltas theo table/index giúp tìm objects có nhiều reads. Kết hợp query stats và latency để xác định objects thực sự ảnh hưởng performance.

---

## 18. pg_stat_io trên PostgreSQL 16 trở lên

pg_stat_io bổ sung thống kê I/O theo backend type, object và context trên PostgreSQL 16 trở lên.

~~~sql
SELECT *
FROM pg_catalog.pg_stat_io;
~~~

### 18.1. Backend type

Cho biết nhóm backend thực hiện I/O, ví dụ client backend, background writer, checkpointer hoặc các loại backend khác theo version.

### 18.2. Object/context

Phân biệt loại object và context I/O được thống kê. Cách phân nhóm cụ thể cần xem schema trên server.

### 18.3. Counters

View có thể cung cấp số read/write, bytes, writebacks, extends, hits, evictions, reuses và fsyncs tùy cột/version.

### 18.4. Timing

Các cột read_time/write_time/extend_time/fsync_time cần được diễn giải cùng cấu hình timing collection như track_io_timing. Xem pg_settings và tài liệu version.

### 18.5. Không phải physical device telemetry

pg_stat_io mô tả I/O do PostgreSQL thực hiện theo góc nhìn database. Nó không thay thế OS/cloud metrics về device latency, queue, throttling hoặc physical cache.

### 18.6. Version compatibility

Không chạy query tham chiếu pg_stat_io trên PostgreSQL trước 16. Exporter nên kiểm tra server version và chỉ bật collector phù hợp.

---

## 19. EXPLAIN (ANALYZE, BUFFERS)

EXPLAIN với BUFFERS giúp xem hoạt động buffer của một query cụ thể.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM public.orders
WHERE customer_id = 42;
~~~

### 19.1. shared hit

Số shared buffers được tìm thấy trong PostgreSQL buffer pool.

### 19.2. shared read

Số shared buffers được đọc vào pool. Không khẳng định mọi block đó được đọc từ physical disk.

### 19.3. shared dirtied

Số shared buffers bị đánh dấu dirty bởi query.

### 19.4. shared written

Số shared buffers được ghi trong lúc query chạy theo semantics của EXPLAIN/version. Không nên xem đây là tổng I/O của query nếu có background activity.

### 19.5. local/temp buffers

Local buffers liên quan temporary tables; temp buffers trong EXPLAIN có thể chỉ hoạt động temporary buffer files/blocks theo loại operation. Đọc output đúng ngữ cảnh version.

### 19.6. EXPLAIN ANALYZE thực thi query

Với SELECT, query thực sự chạy và tiêu thụ tài nguyên. Với DML, side effects có thể xảy ra. Chỉ chạy trên môi trường phù hợp; có thể dùng transaction và rollback trong trường hợp an toàn, nhưng không giả định rollback loại bỏ mọi external side effect.

### 19.7. So sánh cùng điều kiện

Lấy nhiều lần chạy, giữ workload tương đương và ghi rõ cache state. Lần đầu cold-ish và lần sau warm-cache có thể có kết quả khác nhau.

---

## 20. pg_buffercache để xem shared buffer contents

Extension pg_buffercache cho phép quan sát pages hiện đang ở shared_buffers.

### 20.1. Cài extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_buffercache;
~~~

Extension cần được cài đặt/cho phép theo môi trường. Quyền truy cập view/function có thể bị giới hạn.

### 20.2. Xem phân bố buffer theo database

~~~sql
SELECT
    CASE
        WHEN relforknumber = 0 THEN 'main'
        WHEN relforknumber = 1 THEN 'fsm'
        WHEN relforknumber = 2 THEN 'vm'
        WHEN relforknumber = 3 THEN 'init'
        ELSE 'other'
    END AS fork_name,
    count(*) AS buffers
FROM pg_catalog.pg_buffercache
WHERE reldatabase = (
    SELECT oid
    FROM pg_catalog.pg_database
    WHERE datname = current_database()
)
GROUP BY relforknumber
ORDER BY buffers DESC;
~~~

### 20.3. Đếm buffers theo relation

Có thể join pg_buffercache với pg_class/pg_namespace để xem relation nào đang chiếm buffer pages. Cần xử lý relation mapping cẩn thận và chỉ xem như snapshot.

### 20.4. Đây là snapshot, không phải lịch sử

pg_buffercache cho biết nội dung buffer pool tại thời điểm query. Muốn trend cần scrape có giới hạn và cân nhắc overhead.

### 20.5. Không dùng để pin thủ công mọi table

Việc một relation có nhiều pages trong cache không tự nói nó cần được giữ. Buffer replacement vẫn cần quản lý pool cho workload toàn hệ thống.

---

## 21. pg_prewarm và warm-up cache

pg_prewarm có thể đọc relation blocks vào cache trước khi workload chính bắt đầu.

### 21.1. Cài extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_prewarm;
~~~

### 21.2. Prewarm vào shared buffers

~~~sql
SELECT pg_prewarm('public.orders', 'buffer');
~~~

### 21.3. Đọc qua OS cache

Các mode như read hoặc prefetch có semantics khác nhau và phụ thuộc version/platform. Đọc tài liệu extension của version đang dùng trước khi chạy.

### 21.4. Khi nào hữu ích?

- Sau restart, làm nóng một số hot relations.
- Trước một batch window đã biết.
- Benchmark cần warm cache có chủ đích.
- Giảm latency spike sau maintenance/restart nếu có kế hoạch.

### 21.5. Rủi ro

Prewarm một table lớn có thể đẩy pages hữu ích khác khỏi cache, tạo I/O burst và làm tăng startup load. Không prewarm toàn bộ database một cách máy móc.

### 21.6. Warm cache không phải tính bền vững

Cache contents có thể mất khi restart hoặc bị thay thế. Không dùng prewarm thay backup, WAL hoặc durability.

---

## 22. Các yếu tố quyết định working set

Working set là tập dữ liệu mà workload thường xuyên truy cập trong một khoảng thời gian.

### 22.1. Database size không bằng working set

Một database 2 TB có thể có hot set 20 GB; một database 100 GB có thể truy cập ngẫu nhiên gần như toàn bộ dữ liệu.

### 22.2. Access frequency

Pages được truy cập nhiều có giá trị giữ trong cache hơn pages chỉ đọc một lần, nhưng scan lớn có thể ảnh hưởng buffer residency.

### 22.3. Index working set

Index root/upper pages và các index leaf pages hot có thể được truy cập liên tục. Index size và access pattern ảnh hưởng cache requirements.

### 22.4. Data skew

Một vài tenant hoặc account có thể tạo phần lớn traffic. Average workload không thể hiện hot keys.

### 22.5. Time-of-day

Batch jobs, reports và business peak có thể thay đổi working set theo giờ.

### 22.6. Churn

Nếu workload liên tục truy cập pages mới, cache turnover cao. Tăng shared_buffers có thể giúp nếu working set chỉ hơi lớn hơn pool, nhưng không cứu được scan liên tục trên dữ liệu lớn hơn RAM nhiều lần.

---

## 23. Sequential scans và cache behavior

Sequential scans có thể làm nhiều pages được đọc trong thời gian ngắn.

### 23.1. Scan lớn không tự động là lỗi

Nếu query cần phần lớn table, sequential scan có thể rẻ hơn index scan. Một lần đọc tuần tự hiệu quả có thể tận dụng read-ahead và storage throughput.

### 23.2. Buffer ring strategy

PostgreSQL có các chiến lược buffer access cho một số large scans để tránh đẩy toàn bộ hot working set khỏi shared_buffers. Chi tiết implementation thay đổi theo version.

### 23.3. Hit ratio có thể giảm sau batch scan

Batch scan có thể làm blks_read tăng, khiến aggregate hit ratio giảm. Điều đó không nhất thiết làm interactive workload chậm nếu hot pages vẫn còn.

### 23.4. Đo theo query/table

Dùng pg_stat_statements, pg_statio_user_tables và EXPLAIN (BUFFERS) để xác định scan nào tạo nhiều reads.

### 23.5. Không sửa shared_buffers để chữa query plan kém

Nếu planner chọn sequential scan do statistics/index/selectivity, tăng cache size có thể không giải quyết gốc rễ. Xem plan và cardinality estimates.

---

## 24. Sizing theo workload

### 24.1. OLTP với hot set

Workload giao dịch thường truy cập lặp lại một tập table/index pages. shared_buffers đủ lớn để giữ phần hot set có thể giảm latency và I/O.

### 24.2. Analytics

Workload analytics có thể đọc nhiều dữ liệu lớn, thường xuyên vượt cache. Storage throughput, parallelism và query plan có thể quan trọng hơn việc tăng buffer pool vô hạn.

### 24.3. Mixed workload

Một số query tương tác cần latency thấp, trong khi batch/report đọc dữ liệu lớn. Cần xem buffer churn, query scheduling, resource groups (nếu có) và storage capacity.

### 24.4. Read-heavy workload

Cache hit có thể cao nếu hot set ổn định. Tuy vậy, OS page cache cũng có thể phục vụ các pages bị đẩy khỏi shared_buffers.

### 24.5. Write-heavy workload

Quan tâm dirty buffer pressure, WAL throughput, checkpoint behavior, storage write latency và replication. shared_buffers lớn hơn không nhất thiết cải thiện commit latency.

### 24.6. Nhiều PostgreSQL instances trên một host

Mỗi instance có shared_buffers riêng. Cộng tổng allocation của tất cả instances và chừa RAM cho OS, page cache và services khác.

---

## 25. Tuning shared_buffers theo quy trình

Không thay đổi shared_buffers chỉ dựa trên một cache hit ratio.

### Bước 1: Ghi nhận baseline

Thu thập:
- shared_buffers hiện tại.
- RAM và memory limit.
- Application latency p50/p95/p99.
- Throughput và concurrency.
- blks_hit/blks_read deltas.
- pg_stat_io hoặc OS I/O metrics.
- CPU, memory, swap và disk latency.
- Checkpoint write/sync behavior.
- Query mix và top statements.

### Bước 2: Xác định bottleneck

Nếu latency chủ yếu do lock wait hoặc pool wait, shared_buffers có thể không giúp. Nếu storage reads tăng cùng query latency và working set có thể cache, thử nghiệm có cơ sở hơn.

### Bước 3: Chọn một mức thay đổi

Tăng/giảm theo bước có kiểm soát. Không đồng thời thay shared_buffers, work_mem, effective_cache_size, checkpoint settings và query plans nếu muốn biết thay đổi nào tạo kết quả.

### Bước 4: Kiểm tra memory headroom

Ước lượng peak backend/query memory, maintenance, OS cache và các services khác. Không để host tiến gần OOM.

### Bước 5: Áp dụng cấu hình

shared_buffers là tham số cần restart PostgreSQL để có hiệu lực. Lập maintenance plan và xác nhận restart/rollback procedure.

### Bước 6: Warm-up theo cách nhất quán

Sau restart, cache thường lạnh hơn. Đừng so số liệu ngay sau restart với một hệ thống đã chạy ổn định nhiều giờ mà không ghi rõ cache state.

### Bước 7: Chạy workload tương đương

Dùng cùng dataset, concurrency, request mix và thời gian đo. Tốt nhất có nhiều vòng thử và đủ thời gian để cache ổn định.

### Bước 8: So sánh kết quả

So p95/p99, throughput, OS physical I/O, pg buffer reads, CPU, memory pressure, swap, checkpoint và storage latency.

### Bước 9: Chọn mức tốt nhất cho toàn hệ thống

Chọn cấu hình cân bằng user latency, throughput, durability, OS headroom và cost; không chỉ tối đa cache hit ratio.

### Bước 10: Ghi lại quyết định

Lưu cấu hình, version, hardware, workload, test method, results và rollback value để lần sau có baseline đáng tin.

---

## 26. Cấu hình shared_buffers

### 26.1. Xem giá trị hiện tại

~~~sql
SHOW shared_buffers;

SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'shared_buffers',
    'effective_cache_size',
    'work_mem',
    'maintenance_work_mem',
    'temp_buffers',
    'wal_buffers'
)
ORDER BY name;
~~~

### 26.2. Sửa trong postgresql.conf

Ví dụ:

~~~conf
shared_buffers = 4GB
effective_cache_size = 12GB
~~~

Giá trị chỉ minh họa cho một host có RAM phù hợp. Không copy nguyên vào production.

### 26.3. Kiểm tra context

~~~sql
SELECT name, setting, context, pending_restart
FROM pg_catalog.pg_settings
WHERE name = 'shared_buffers';
~~~

Context thường cho biết tham số cần restart hay có thể reload/set ở runtime.

### 26.4. Restart

Sau khi thay đổi shared_buffers, cần restart PostgreSQL. Dùng service manager hoặc quy trình vận hành của môi trường. Sau restart, xác nhận giá trị hiệu lực bằng SHOW.

### 26.5. Không nhầm reload với restart

Reload đọc lại một số cấu hình có thể thay đổi runtime. Nó không tái tạo shared memory allocation của shared_buffers.

### 26.6. Kiểm tra logs và memory

Sau restart, kiểm tra PostgreSQL logs, startup success, shared memory allocation và OS/container memory headroom.

---

## 27. Quan sát OS page cache và memory pressure

PostgreSQL metrics không thể mô tả toàn bộ page cache.

### 27.1. Linux

Các nguồn thường dùng:
- /proc/meminfo: MemAvailable, Cached, Buffers, SReclaimable.
- vmstat: memory, paging, swap và run queue.
- free: snapshot memory.
- iostat: device utilization, throughput, queue và latency.
- cgroup memory files: giới hạn và usage trong container.
- Cloud metrics: volume IOPS, throughput, latency và throttling.

Ví dụ:

~~~bash
free -h
vmstat 1
iostat -xz 1
~~~

Các lệnh cần chạy trên host và theo quyền vận hành.

### 27.2. MemAvailable quan trọng hơn chỉ nhìn free

Linux có thể dùng RAM trống làm cache. Free memory thấp không nhất thiết là memory pressure nếu MemAvailable vẫn đủ và reclaim hoạt động bình thường.

### 27.3. Swap activity

Swap-in/swap-out liên tục cùng latency tăng là dấu hiệu cần điều tra. Swap used không phải lúc nào cũng có nghĩa đang thrash; xem activity theo thời gian.

### 27.4. Windows

Có thể dùng Performance Monitor/Resource Monitor để quan sát available memory, cache bytes, page faults, disk reads/writes, latency và process memory.

### 27.5. Containers

Xem cgroup memory usage/limit, memory events và OOM counters. Host có thể còn nhiều RAM trong khi container đã chạm limit.

### 27.6. Đừng cộng RSS đơn giản

Nhiều PostgreSQL processes map cùng shared memory. Cộng RSS của mọi process có thể đếm cùng vùng shared pages nhiều lần. Dùng PSS/cgroup/container metrics phù hợp.

---

## 28. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| shared_buffers là toàn bộ RAM PostgreSQL | Còn backend, work_mem, maintenance, WAL và nhiều vùng khác |
| OS page cache không cần khi có shared_buffers | PostgreSQL thường dựa vào cả hai tầng |
| blks_read luôn là physical disk read | Có thể được phục vụ từ OS page cache |
| Cache hit ratio 99% luôn là tốt | Không phản ánh đầy đủ latency, tail hoặc workload |
| Cache hit ratio thấp luôn là xấu | Sequential scans và analytics có thể tạo nhiều reads hợp lý |
| Tăng shared_buffers luôn làm query nhanh hơn | Có diminishing returns và memory pressure |
| shared_buffers lớn thay thế OS cache | Hai tầng có chính sách và phạm vi khác nhau |
| effective_cache_size cấp phát RAM | Đây là planner estimate |
| work_mem là memory pool toàn server | Nó có thể được cấp nhiều lần theo operation/session |
| COMMIT ghi mọi table page xuống disk | Commit thường chờ WAL flush; data pages có thể còn dirty |
| OS cache hit không tốn chi phí | Vẫn có syscall, copy và kernel work |
| shared buffer miss nghĩa phải đọc storage | OS page cache có thể phục vụ |
| Database size là working set | Working set phụ thuộc access pattern |
| Prewarm giữ cache vĩnh viễn | Pages có thể bị thay thế hoặc mất khi restart |
| Restart/reload có tác dụng giống nhau | shared_buffers cần restart |
| Cache hit ratio tăng chứng minh tuning thành công | Cần so latency, throughput, physical I/O và memory |
| Disk còn nhiều thì I/O không thể chậm | Latency/queue/IOPS có thể bão hòa trước capacity |
| Cộng RSS cho biết chính xác memory PostgreSQL | Shared mappings có thể bị đếm lặp |
| Tắt fsync giúp cache nhanh hơn an toàn | Có thể làm mất durability |
| shared_buffers lớn luôn giảm checkpoint work | Dirty page volume và writeback pressure vẫn phải đo |

---

## 29. Lab 1: quan sát shared_buffers và database counters

Lab dùng database riêng hoặc môi trường thử nghiệm.

### 29.1. Kiểm tra cấu hình

~~~sql
SHOW shared_buffers;
SHOW block_size;
SHOW effective_cache_size;
~~~

Ghi lại kết quả và server version.

### 29.2. Lấy snapshot counters

~~~sql
SELECT
    datname,
    blks_hit,
    blks_read,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
~~~

### 29.3. Tạo bảng đọc thử

~~~sql
CREATE TABLE IF NOT EXISTS public.cache_lab (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);

INSERT INTO public.cache_lab(id, payload)
SELECT g, repeat('x', 200)
FROM generate_series(1, 200000) AS g
ON CONFLICT (id) DO NOTHING;

ANALYZE public.cache_lab;
~~~

### 29.4. Chạy query đọc

~~~sql
SELECT sum(length(payload))
FROM public.cache_lab;
~~~

### 29.5. Lấy snapshot thứ hai

Chạy lại query counters. Tính delta blks_hit và blks_read. Query lặp lại có thể tạo nhiều hits hơn nếu pages còn trong shared_buffers.

### 29.6. Diễn giải

Không kết luận physical disk reads từ blks_read. Cần OS/storage metrics để biết thiết bị có thực sự đọc hay không.

---

## 30. Lab 2: phân biệt shared buffer miss và physical I/O

### 30.1. Chuẩn bị

Dùng một table lớn hơn shared_buffers trong lab nếu đủ dung lượng. Ghi rõ dataset size và host RAM.

### 30.2. Lấy PostgreSQL counters

Ghi pg_stat_database và pg_statio_user_tables trước khi chạy query.

### 30.3. Lấy OS metrics

Trên Linux, ghi device read bytes/operations/latency và page cache/memory metrics. Không xóa OS caches trên production.

### 30.4. Chạy workload

Đọc một tập pages lớn hơn buffer pool hoặc scan table theo cách có thể lặp lại.

### 30.5. So sánh

Nếu blks_read tăng nhưng physical device reads không tăng tương ứng, OS page cache có thể đã phục vụ phần lớn block reads.

### 30.6. Giới hạn

Storage controller, hypervisor và cloud provider có thể có cache riêng. Phân biệt OS cache hit với physical media access cần telemetry ở đúng tầng.

---

## 31. Lab 3: dùng EXPLAIN (ANALYZE, BUFFERS)

### 31.1. Chạy query có điều kiện

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM public.cache_lab
WHERE id BETWEEN 10000 AND 11000;
~~~

### 31.2. Ghi buffer counts

Ghi shared hit, shared read, dirtied và written nếu xuất hiện. Lưu query plan và execution time.

### 31.3. Chạy lại

Chạy lại cùng query trong điều kiện tương tự. So sánh hit/read counts và latency.

### 31.4. Thử sequential scan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sum(length(payload))
FROM public.cache_lab;
~~~

### 31.5. Diễn giải

Buffer read là page được đưa vào shared buffer. Nó không xác nhận physical storage read. Kết hợp OS metrics.

### 31.6. An toàn

Không dùng EXPLAIN ANALYZE cho DML production nếu chưa kiểm soát side effects và load.

---

## 32. Lab 4: pg_buffercache và pg_prewarm

### 32.1. Cài extension trong lab

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_buffercache;
CREATE EXTENSION IF NOT EXISTS pg_prewarm;
~~~

### 32.2. Quan sát buffer residency

~~~sql
SELECT
    count(*) AS buffers_for_cache_lab
FROM pg_catalog.pg_buffercache AS b
JOIN pg_catalog.pg_class AS c
    ON c.relfilenode = b.relfilenode
WHERE c.relname = 'cache_lab';
~~~

Query minh họa cần được điều chỉnh nếu schema, tablespace hoặc relation mapping phức tạp. Trong thực tế nên join đầy đủ database/tablespace/relation identity để tránh trùng filenode.

### 32.3. Prewarm table

~~~sql
SELECT pg_prewarm('public.cache_lab', 'buffer');
~~~

### 32.4. Chạy query sau prewarm

Lấy EXPLAIN BUFFERS và database counters để quan sát thay đổi.

### 32.5. Quan sát tác động tới workload khác

Prewarm table lớn có thể thay thế pages khác. So sánh hot query latency trước/sau nếu lab có nhiều relations.

### 32.6. Kết luận

pg_buffercache là snapshot về shared_buffers; pg_prewarm chủ động đọc relation pages. Cả hai không tạo cache bền vững và không thay thế backup.

---

## 33. Lab 5: thử sizing có kiểm soát

Lab cần host/database riêng và quyền restart. Không thay đổi production chỉ để thử.

### 33.1. Ghi baseline

Lưu shared_buffers, effective_cache_size, RAM, container limit, CPU, memory pressure, disk I/O, query mix và latency percentiles.

### 33.2. Chọn workload lặp lại

Dùng cùng dataset, concurrency, request mix và thời lượng. Xác định phần workload đại diện production.

### 33.3. Thay một tham số

Chọn một mức shared_buffers mới theo memory budget. Không thay đồng thời work_mem và checkpoint settings.

### 33.4. Restart và xác nhận

Restart PostgreSQL theo runbook. Kiểm tra SHOW shared_buffers và startup logs.

### 33.5. Warm-up

Chạy workload warm-up có kiểm soát. Ghi riêng giai đoạn cold cache và steady state.

### 33.6. Đo

So p50/p95/p99, throughput, blks_hit/read delta, physical I/O, CPU, MemAvailable, swap, checkpoint time và disk latency.

### 33.7. Đánh giá

Chỉ giữ thay đổi nếu lợi ích lặp lại và memory headroom vẫn an toàn. Nếu kết quả không tốt, rollback về giá trị cũ.

---

## 34. Bài tập thực hành

### Bài 1 — Định nghĩa

Giải thích shared_buffers bằng ngôn ngữ của database engine. Nó cache loại dữ liệu nào?

### Bài 2 — Hai tầng cache

Vẽ đường đọc qua shared_buffers, OS page cache và storage device.

### Bài 3 — Shared hit

Điều gì xảy ra khi PostgreSQL tìm thấy block trong shared_buffers?

### Bài 4 — OS cache hit

Vì sao blks_read có thể tăng mà physical disk reads không tăng?

### Bài 5 — Cache miss

Mô tả đường đi khi block không có trong cả hai tầng cache.

### Bài 6 — Double caching

Vì sao một page có thể chiếm RAM trong cả shared_buffers và OS page cache? Nêu trade-off.

### Bài 7 — Dirty buffers

Giải thích dirty page, buffer pin và vì sao buffer dirty không thể bị tái sử dụng ngay.

### Bài 8 — WAL ordering

Vì sao WAL phải được flush trước khi data page tương ứng được ghi bền vững?

### Bài 9 — Commit path

Một transaction commit nhưng data page còn dirty. Vì sao dữ liệu vẫn có thể được recovery sau crash?

### Bài 10 — Memory areas

Phân biệt shared_buffers, work_mem, temp_buffers, wal_buffers và maintenance_work_mem.

### Bài 11 — effective_cache_size

Vì sao đặt effective_cache_size = 32GB không cấp phát 32GB RAM?

### Bài 12 — Sizing

Một host dedicated có RAM 64GB. Tính điểm khởi đầu 25% và nêu các thành phần memory cần chừa.

### Bài 13 — Container

Host có 128GB RAM nhưng PostgreSQL container limit 16GB. Vì sao không sizing shared_buffers theo RAM host?

### Bài 14 — Cache hit ratio

Tính shared buffer hit ratio từ blks_hit=9.000.000 và blks_read=1.000.000. Nêu giới hạn của kết quả.

### Bài 15 — Hit ratio thấp

Một hệ thống analytics có hit ratio 65% nhưng latency đạt SLO. Vì sao không nhất thiết phải tăng shared_buffers?

### Bài 16 — Hit ratio cao

Một API p99 tăng dù hit ratio 99.8%. Liệt kê nguyên nhân khác ngoài cache miss.

### Bài 17 — pg_statio

Viết query tìm tables có heap_blks_read cao nhất và giải thích vì sao đây chưa phải physical I/O ranking.

### Bài 18 — pg_stat_io

Nêu vai trò pg_stat_io và phiên bản PostgreSQL bắt đầu hỗ trợ view này.

### Bài 19 — EXPLAIN BUFFERS

Giải thích shared hit, shared read, dirtied và written trong EXPLAIN.

### Bài 20 — pg_buffercache

Khi nào extension pg_buffercache hữu ích? Vì sao snapshot không thể thay time-series metrics?

### Bài 21 — pg_prewarm

Nêu một trường hợp dùng pg_prewarm có ích và một rủi ro khi prewarm relation lớn.

### Bài 22 — Sequential scan

Vì sao sequential scan có thể làm hit ratio giảm nhưng vẫn là query plan tốt?

### Bài 23 — Checkpoint

Giải thích quan hệ giữa dirty buffers, checkpoint và storage write throughput.

### Bài 24 — Tuning

Thiết kế benchmark so sánh shared_buffers 4GB và 8GB. Những điều kiện nào cần giữ giống nhau?

### Bài 25 — Restart

Vì sao thay đổi shared_buffers cần restart thay vì reload?

### Bài 26 — Memory pressure

Một host có MemAvailable thấp và swap-in tăng. Đề xuất các bước điều tra trước khi tăng shared_buffers.

### Bài 27 — Backend concurrency

Vì sao work_mem có thể tạo memory usage lớn hơn dự tính khi nhiều query/parallel workers chạy cùng lúc?

### Bài 28 — Multiple instances

Một host chạy ba PostgreSQL instances. Lập ngân sách shared_buffers tổng và OS cache headroom.

### Bài 29 — OS metrics

Liệt kê các chỉ số Linux/Windows cần xem để hiểu filesystem page cache và physical I/O.

### Bài 30 — Storage cache

Một cloud volume có read cache riêng. Vì sao OS read không chứng minh media đã được truy cập?

### Bài 31 — Working set

Database 1TB nhưng hot set 30GB. Điều này ảnh hưởng sizing như thế nào?

### Bài 32 — Write-heavy workload

shared_buffers tăng nhưng commit latency không giảm. Những metrics nào cần xem tiếp?

### Bài 33 — Checkpoint regression

Sau khi tăng shared_buffers, checkpoint duration tăng. Đề xuất cách xác định dirty page pressure và storage bottleneck.

### Bài 34 — Planner estimate

effective_cache_size quá cao có thể khiến planner chọn plan nào và vì sao?

### Bài 35 — Cache warm-up

Thiết kế cách đo cold-cache và warm-cache performance sau restart mà không xóa OS cache trên production.

### Bài 36 — Stats reset

Một exporter tính cache hit ratio sai sau stats reset. Nêu cách lưu snapshots và xử lý reset.

### Bài 37 — Buffer churn

Một batch sequential scan làm API hot queries chậm hơn. Đề xuất metrics và cách thử nghiệm.

### Bài 38 — Cache tuning không hiệu quả

Latency chủ yếu là lock wait. Vì sao tăng shared_buffers không giải quyết gốc rễ?

### Bài 39 — Capacity review

Một server 32GB RAM, 20GB shared_buffers, 400 connections, work_mem 64MB. Phân tích những rủi ro memory cần đánh giá.

### Bài 40 — End-to-end tuning

Một PostgreSQL OLTP có p99 800ms, hit ratio 99.5%, CPU 35%, disk read latency tăng, MemAvailable thấp và swap activity xuất hiện. Xây dựng trình tự điều tra hai tầng cache, working set, memory budget, I/O, query plans và đề xuất benchmark shared_buffers có kiểm soát.

---

## 35. Checklist vận hành shared_buffers và OS cache

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| PostgreSQL version | Major version và build block size |
| shared_buffers | Giá trị hiện tại và memory allocation |
| OS/container limit | RAM thực tế PostgreSQL được phép dùng |
| OS page cache | MemAvailable/cache behavior |
| effective_cache_size | Planner estimate hợp lý |
| work_mem | Peak concurrent sort/hash memory |
| temp_buffers | Temporary table usage |
| wal_buffers | WAL buffer configuration |
| Backend concurrency | Số session/parallel workers |
| Memory pressure | Swap, reclaim, OOM events |
| shared buffer hit/read | Deltas theo workload |
| Physical device reads | OS/cloud storage metrics |
| pg_statio | Hot tables/indexes |
| pg_stat_io | Có hỗ trợ theo version không |
| EXPLAIN BUFFERS | Query-level buffer activity |
| pg_buffercache | Snapshot khi cần điều tra |
| pg_prewarm | Có chủ đích và giới hạn workload |
| Dirty buffers | Writeback/checkpoint pressure |
| Checkpoint metrics | Write/sync time và frequency |
| WAL rate | Bytes/s và archive/replication load |
| Disk latency | Read/write latency và queue |
| Working set | Kích thước và access pattern |
| Sequential scans | Có scan lớn/churn không |
| Query latency | p50/p95/p99 |
| Throughput | Workload có tương đương không |
| Tuning experiment | Thay một biến mỗi lần |
| Restart plan | Có maintenance/rollback plan |
| Warm-up | Cold/warm phases được ghi rõ |
| Restore safety | Không tắt durability settings |
| Decision record | Lưu baseline, kết quả và cấu hình |

## Kết luận

shared_buffers là cache page do PostgreSQL quản lý, còn OS page cache là cache file do kernel quản lý. Khi PostgreSQL không tìm thấy block trong shared_buffers, hệ điều hành vẫn có thể trả block từ RAM. Vì vậy, PostgreSQL buffer read không đồng nghĩa physical disk read, và cache hit ratio không thể thay thế metrics về storage, latency và memory pressure.

Những nguyên tắc cần nhớ:

1. **shared_buffers cache database pages.** Nó được dùng chung giữa PostgreSQL backends và có cơ chế quản lý buffer, pinning, dirty pages và replacement.
2. **OS page cache là tầng độc lập.** Nó có thể phục vụ một PostgreSQL shared-buffer miss mà không cần đọc storage device.
3. **Một page có thể tồn tại ở hai tầng.** Double caching tiêu thụ RAM nhưng cho phép PostgreSQL và kernel quản lý cache theo mục đích riêng.
4. **blks_read không phải physical reads.** Kết hợp pg_stat_database/pg_statio với OS và storage telemetry.
5. **COMMIT thường chờ WAL flush.** Data pages có thể còn dirty trong shared_buffers và được ghi sau đó theo checkpoint/writeback.
6. **effective_cache_size chỉ là planner estimate.** Nó không cấp phát RAM và không thay đổi shared_buffers.
7. **25% RAM là điểm bắt đầu, không phải luật.** Đánh giá working set, OS, container limit, concurrency và workload.
8. **Memory budget phải bao gồm query memory.** work_mem có thể được dùng nhiều lần bởi một query và nhiều sessions.
9. **Hit ratio không phải SLO.** Một hệ thống hit ratio thấp vẫn có thể nhanh; hit ratio cao vẫn có thể chậm do lock, CPU hoặc I/O.
10. **Dùng nhiều góc nhìn để đo.** pg_stat_database, pg_statio, pg_stat_io, EXPLAIN BUFFERS, pg_buffercache và OS metrics bổ sung cho nhau.
11. **Tuning cần benchmark có kiểm soát.** Giữ workload tương đương, tách cold/warm cache và thay một tham số mỗi lần.
12. **Không đánh đổi durability để tăng tốc.** Giữ WAL, fsync và recovery settings phù hợp với yêu cầu dữ liệu.

Một cấu hình shared_buffers tốt không phải cấu hình chiếm phần RAM lớn nhất. Đó là cấu hình giữ được working set hữu ích, phối hợp tốt với OS page cache, để lại đủ memory cho query và maintenance, đồng thời cải thiện latency/throughput mà không tạo memory pressure hoặc checkpoint bottleneck.
