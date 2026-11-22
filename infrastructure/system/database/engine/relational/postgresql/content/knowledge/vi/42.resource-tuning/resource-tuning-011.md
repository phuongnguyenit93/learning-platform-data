# Huge pages, swap, filesystem và giới hạn container

PostgreSQL sử dụng bộ nhớ dùng chung, bộ nhớ riêng của từng backend, bộ nhớ cho query operators, vùng nhớ bảo trì, bộ nhớ của hệ điều hành và storage để lưu data/WAL. Khi PostgreSQL chạy trong VM hoặc container, các tài nguyên này còn chịu giới hạn từ hypervisor, cgroups, Docker hoặc Kubernetes. Vì vậy, tối ưu tài nguyên cần xem cả PostgreSQL lẫn host/runtime.

**Huge pages** có thể giảm overhead quản lý page tables cho vùng shared memory lớn. **Swap** là cơ chế của hệ điều hành để đưa memory pages ra storage khi thiếu RAM, nhưng swap pressure có thể làm latency database tăng mạnh. **Filesystem** quyết định cách data, WAL, temporary files và logs được lưu bền vững. **Container limits** đặt trần CPU/memory/storage và có thể gây throttling hoặc OOM kill nếu sizing không phù hợp.

Bài học này giải thích các cơ chế đó, cách cấu hình và xác minh trên Linux, các lưu ý khi chạy PostgreSQL trong Docker/Kubernetes, cách lập memory/storage budget, cùng monitoring và troubleshooting. Các ví dụ chủ yếu hướng tới Linux; tên file, quyền và hành vi có thể khác theo distribution, kernel, PostgreSQL major version và container runtime.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả memory layout của PostgreSQL và Linux.
2. Phân biệt shared memory với private memory của backend.
3. Giải thích tác dụng và giới hạn của explicit huge pages.
4. Phân biệt explicit huge pages với Transparent Huge Pages (THP).
5. Ước lượng số huge pages cần reserve và xác minh PostgreSQL đã dùng chúng.
6. Đánh giá swap, swappiness và nguy cơ OOM.
7. Lập memory budget từ shared_buffers, work_mem, maintenance memory và concurrency.
8. Đọc cgroup memory/CPU limits và hiểu tác động tới PostgreSQL.
9. Phân biệt container memory limit với /dev/shm capacity.
10. Cấu hình Docker/Kubernetes resources và persistent volumes phù hợp.
11. Hiểu filesystem durability, fsync, WAL và inode/capacity constraints.
12. Giám sát disk, I/O, memory, swap, huge pages và container throttling.
13. Xây dựng runbooks cho OOM, filesystem full và resource throttling.

## 2. Các lớp tài nguyên PostgreSQL sử dụng

Một PostgreSQL instance cần nhiều loại tài nguyên:

| Lớp | Ví dụ | Được quản lý bởi |
|---|---|---|
| Shared memory | shared_buffers, lock tables, WAL-related shared structures | PostgreSQL và kernel |
| Backend-private memory | executor state, sort/hash, expression contexts | Từng PostgreSQL process |
| Maintenance memory | VACUUM, CREATE INDEX, maintenance workers | PostgreSQL |
| OS page cache | File data/WAL đã đọc hoặc ghi | Linux kernel |
| Kernel memory | Page tables, sockets, filesystem metadata | Linux kernel |
| Container accounting | memory.current, memory.max, CPU quota | cgroups/runtime |
| Persistent storage | PGDATA, pg_wal, tablespaces | Filesystem/storage platform |
| Temporary storage | temp files, temporary tables, spill files | Filesystem và PostgreSQL |

Không thể tính memory budget bằng cách chỉ lấy shared_buffers cộng một phần trăm cố định. Workload concurrency, query plan, parallel workers, extensions, OS page cache và cgroup accounting đều ảnh hưởng tổng mức sử dụng.

## 3. PostgreSQL process model và memory

PostgreSQL thường dùng process-per-connection trên Unix-like systems. Mỗi client backend có private memory contexts và có thể cấp phát memory cho query execution. Ngoài ra có background processes như checkpointer, background writer, WAL writer, autovacuum workers, logical replication workers và parallel workers.

### Hai nhóm bộ nhớ quan trọng

- Shared memory được nhiều PostgreSQL processes cùng truy cập. Ví dụ shared buffers và các shared control structures.
- Private memory thuộc từng process/worker. Ví dụ sort/hash operations, executor state, PL runtime và một số buffers.

Shared memory không có nghĩa mọi process phải trả một bản sao đầy đủ trong RSS; các mappings có thể cùng tham chiếu một vùng vật lý. Khi đọc process RSS, cần tránh cộng RSS của tất cả processes một cách máy móc vì có thể đếm trùng shared pages.

### Vì sao concurrency quan trọng?

Một query có thể dùng nhiều memory operations. Nhiều queries chạy đồng thời và parallel workers có thể làm tổng private memory lớn hơn nhiều so với một connection đơn lẻ. Pooling giúp giới hạn concurrency, nhưng không tự bảo đảm mọi query dùng ít memory.

## 4. Các PostgreSQL memory settings

Một số settings ảnh hưởng lớn tới memory:

| Setting | Phạm vi/ý nghĩa |
|---|---|
| shared_buffers | Shared buffer cache của PostgreSQL |
| work_mem | Memory tối đa cho một số query operations trước khi spill |
| maintenance_work_mem | Memory cho maintenance operations |
| autovacuum_work_mem | Memory cho mỗi autovacuum worker nếu được đặt riêng |
| temp_buffers | Temporary-table buffers theo session |
| logical_decoding_work_mem | Memory cho logical decoding trước khi spill |
| max_connections | Số client connections tối đa, ảnh hưởng số backends |
| max_parallel_workers_per_gather | Giới hạn parallel workers cho một query |
| max_worker_processes | Tổng worker process capacity |

Kiểm tra:

```sql
SHOW shared_buffers;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW autovacuum_work_mem;
SHOW temp_buffers;
SHOW max_connections;
SHOW max_parallel_workers_per_gather;
```

Các settings có thể có giá trị mặc định khác theo version/distribution. Kiểm tra effective configuration trên instance thực tế.

## 5. work_mem không phải memory limit của connection

work_mem là mức memory tối đa mà một query operation như sort hoặc hash có thể sử dụng trước khi spill ra temporary files. Một query plan có thể có nhiều operations đồng thời; parallel query có thể tạo nhiều workers và mỗi worker có memory allocation riêng.

Ước lượng đơn giản:

\[
\text{query memory exposure}
\approx
\text{concurrent operations}
\times
\text{work\_mem}
\]

Đây chỉ là cách hình dung rủi ro, không phải công thức chính xác cho mọi plan. Hash operations có thể chịu thêm hệ số theo hash_mem_multiplier; query plan, executor lifetime và concurrency quyết định mức dùng thực tế.

### Ví dụ

Nếu work_mem là 64 MB, 20 queries đồng thời, mỗi query có 2 sort/hash operations đang sống và một phần dùng parallel workers, tổng memory exposure có thể lên tới hàng GB. Vì vậy, không tăng work_mem toàn cục chỉ để sửa một query sort chậm.

### Cách kiểm soát

- Dùng EXPLAIN (ANALYZE, BUFFERS) để xác định spill.
- Tối ưu query/index trước khi tăng work_mem.
- Dùng SET LOCAL work_mem cho transaction đặc biệt khi phù hợp.
- Giới hạn query concurrency và parallelism.
- Theo dõi temp files/temp_bytes.

## 6. shared_buffers và OS page cache

shared_buffers là cache page ở tầng PostgreSQL. Linux cũng giữ file pages trong page cache. Vì vậy, database có thể dùng RAM ngoài shared_buffers để cache data files.

Một điểm bắt đầu phổ biến trên dedicated database server là shared_buffers khoảng 25% RAM, nhưng đây không phải công thức bắt buộc. Cần xét:

- RAM host/container limit.
- Workload working set.
- OS page cache needs.
- Query concurrency và work_mem.
- Autovacuum/maintenance workload.
- Extensions và background processes.
- Huge page reservation và memory headroom.

Không tăng shared_buffers tới gần toàn bộ RAM. Hệ điều hành vẫn cần memory cho page cache, filesystem, network, kernel và các processes khác.

## 7. Page size và huge pages

Memory được quản lý theo pages. Page size thông thường trên Linux x86-64 thường là 4 KiB, nhưng phụ thuộc kiến trúc/kernel. Huge pages có kích thước lớn hơn, thường là 2 MiB hoặc 1 GiB trên một số hệ thống.

| Page type | Kích thước thường gặp |
|---|---:|
| Base page | 4 KiB |
| Huge page | 2 MiB |
| Huge page lớn | 1 GiB trên phần cứng/kernel hỗ trợ |

Huge pages giảm số lượng page table entries cần quản lý khi map vùng memory lớn. Điều này có thể giảm page table overhead và TLB pressure cho shared memory lớn.

### Huge pages không làm RAM tăng lên

Huge pages thay đổi cách memory pages được cấp phát/ánh xạ. Chúng không tạo thêm RAM và không thay thế memory sizing. Reserve quá nhiều huge pages có thể làm RAM còn lại cho các nhu cầu khác bị giảm.

## 8. Explicit huge pages trong PostgreSQL

PostgreSQL có setting huge_pages. Kiểm tra:

```sql
SHOW huge_pages;
```

Các mode thường gặp:

| Giá trị | Hành vi |
|---|---|
| try | Thử dùng huge pages; nếu không thể thì có thể fallback sang normal pages |
| on | Yêu cầu huge pages; startup thất bại nếu không cấp phát được |
| off | Không dùng explicit huge pages |

Trên Linux, explicit huge pages thường cần kernel reserve trước và PostgreSQL service user phải có quyền sử dụng chúng.

### Khi nào có ích?

Lợi ích thường đáng xem xét với instance có shared memory lớn, đặc biệt shared_buffers lớn. Mức cải thiện workload phụ thuộc hardware, memory topology và workload; cần benchmark thay vì mặc định huge pages luôn tăng throughput.

### Huge pages áp dụng cho vùng nào?

PostgreSQL sử dụng huge pages cho main shared memory region khi được hỗ trợ/cấu hình. Không có nghĩa mọi private allocations, work_mem, temp files hoặc OS page cache đều trở thành huge pages.

## 9. Kiểm tra huge page support trên Linux

Trên host:

```sh
grep -E 'HugePages|Hugepagesize|Hugetlb' /proc/meminfo
getconf PAGE_SIZE
```

Thông tin thường gồm:

- HugePages_Total: tổng số huge pages được reserve.
- HugePages_Free: số page chưa được sử dụng.
- HugePages_Rsvd: số page đã được reserve cho mappings nhưng chưa fault-in.
- HugePages_Surp: số surplus pages.
- Hugepagesize: kích thước mỗi page.

Ví dụ nếu Hugepagesize là 2048 kB và HugePages_Total là 512, vùng huge page được reserve xấp xỉ 1 GiB.

Kiểm tra cấu hình kernel:

```sh
sysctl vm.nr_hugepages
```

Các path và kích thước page có thể khác theo architecture.

## 10. Ước lượng số huge pages cần thiết

Số huge pages tối thiểu có thể ước lượng từ shared memory region mà PostgreSQL cần map chia cho huge page size, làm tròn lên:

\[
\text{huge pages}
\approx
\left\lceil
\frac{\text{PostgreSQL shared memory bytes}}
{\text{huge page size bytes}}
\right\rceil
\]

Không chỉ lấy shared_buffers rồi coi đó là toàn bộ shared memory. PostgreSQL còn có shared control structures, WAL buffers, lock tables và các vùng khác.

Trên các PostgreSQL versions có hỗ trợ, có thể kiểm tra:

```sql
SHOW shared_memory_size;
SHOW shared_memory_size_in_huge_pages;
SHOW huge_page_size;
```

Availability của các parameters này phụ thuộc major version. Nếu không có, dùng startup logs và tài liệu version tương ứng để xác định shared memory requirement.

### Ví dụ ước lượng

Giả sử shared memory region khoảng 8 GiB và huge page size là 2 MiB:

\[
8 \times 1024 \div 2 = 4096\ \text{huge pages}
\]

Đây là phép ước lượng minh họa. Reserve cần dựa trên actual shared memory requirement và có headroom hợp lý.

## 11. Reserve huge pages bằng sysctl

Ví dụ reserve 4096 pages:

```sh
sudo sysctl -w vm.nr_hugepages=4096
```

Để giữ cấu hình sau reboot, có thể đặt trong file sysctl config theo distribution, ví dụ:

```ini
vm.nr_hugepages = 4096
```

Sau khi cập nhật, xác minh:

```sh
sysctl vm.nr_hugepages
grep -E 'HugePages_Total|HugePages_Free|Hugepagesize' /proc/meminfo
```

### Reserve khi hệ thống đang chạy

Kernel có thể không cấp đủ huge pages nếu RAM bị phân mảnh hoặc không còn đủ vùng liên tục phù hợp. Với page size lớn, reserve sớm sau boot hoặc qua boot-time configuration có thể đáng tin cậy hơn. Luôn kiểm tra số page thực tế được cấp, không chỉ giá trị sysctl đã yêu cầu.

## 12. Quyền sử dụng huge pages

PostgreSQL service user cần quyền phù hợp để map huge pages. Linux có thể kiểm soát qua group ownership/permissions của hugetlbfs hoặc capability/rlimit tùy cách triển khai.

Kiểm tra service account và cấu hình kernel/runtime. Không cấp quyền rộng cho mọi user chỉ để PostgreSQL startup thành công.

### systemd

Một số môi trường có thể cần cấu hình service limits/capabilities hoặc group access. Tên unit và cách quản lý khác nhau theo package/distribution. Xem unit file thực tế và log của systemd thay vì áp dụng một override chung.

## 13. Bật huge_pages trong PostgreSQL

Trong postgresql.conf:

```ini
huge_pages = on
```

Hoặc dùng try trong giai đoạn thử nghiệm:

```ini
huge_pages = try
```

huge_pages là startup setting; cần restart PostgreSQL để áp dụng. Với on, nếu kernel không cấp đủ huge pages hoặc quyền không phù hợp, server có thể không khởi động. Với try, PostgreSQL có thể fallback sang normal pages.

### Quy trình rollout

1. Đo RAM và shared memory hiện tại.
2. Ước lượng huge page requirement.
3. Reserve pages trên host.
4. Xác nhận service user có quyền.
5. Đặt huge_pages=try ở môi trường thử hoặc maintenance window.
6. Restart và đọc startup logs.
7. Xác nhận huge pages được dùng.
8. Benchmark workload trước/sau.
9. Chuyển on nếu policy yêu cầu fail-fast và vận hành đã ổn định.

## 14. Xác minh PostgreSQL dùng huge pages

Kiểm tra:

```sql
SHOW huge_pages;
SHOW huge_page_size;
```

Giá trị huge_pages thể hiện cấu hình, không nhất thiết chứng minh mapping thực tế thành công. Kiểm tra thêm startup logs và thông tin kernel/process mapping phù hợp với version.

Trên Linux:

```sh
grep -E 'HugePages|Hugepagesize' /proc/meminfo
grep -i huge /proc/<postgres_pid>/smaps
```

Đường dẫn smaps có thể chứa thông tin mapping theo process; quyền đọc phụ thuộc OS policy. Dùng đúng PID của postmaster/backend phù hợp.

### Kiểm tra log

PostgreSQL thường ghi thông báo về việc sử dụng huge pages hoặc fallback. Log wording thay đổi theo version. Nếu cấu hình on nhưng startup thất bại, xem lỗi đầu tiên liên quan shared memory/huge pages và kernel allocation.

## 15. Transparent Huge Pages (THP)

Transparent Huge Pages là cơ chế kernel tự động gộp/cấp phát page lớn cho memory mappings mà ứng dụng không cần yêu cầu explicit huge pages. THP khác với explicit hugetlb pages mà PostgreSQL điều khiển qua huge_pages.

### Vì sao cần phân biệt?

- Explicit huge pages được reserve và quản lý rõ ràng.
- THP được kernel quản lý động.
- THP có thể kích hoạt compaction/defragmentation ở thời điểm cấp phát.
- Một số workload database nhạy với latency có thể bị ảnh hưởng bởi THP stalls.

PostgreSQL documentation và platform guidance thường khuyến nghị cân nhắc tắt THP trên Linux cho database workload, trong khi có thể dùng explicit huge pages đã reserve. Hãy kiểm tra guidance của kernel/distribution và benchmark trên hardware thực tế.

## 16. Kiểm tra trạng thái THP

Trên Linux:

```sh
cat /sys/kernel/mm/transparent_hugepage/enabled
cat /sys/kernel/mm/transparent_hugepage/defrag
```

Giá trị trong dấu ngoặc vuông thường là lựa chọn đang hoạt động. Ví dụ [always] madvise never cho biết always đang được chọn.

Một số kernel dùng path khác hoặc hỗ trợ nhiều chế độ hơn. Nếu file không tồn tại, kiểm tra kernel configuration/distribution documentation.

## 17. Tắt THP khi policy yêu cầu

Có thể đặt runtime:

```sh
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/enabled
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/defrag
```

Đây là thay đổi runtime và có thể mất sau reboot. Cách persist phụ thuộc bootloader, systemd service hoặc distribution. Kiểm tra trạng thái sau reboot và sau kernel update.

### Không tắt nhầm explicit huge pages

THP và hugetlb explicit là hai cơ chế khác nhau. Tắt THP không có nghĩa vm.nr_hugepages bị xóa hoặc huge_pages=on không thể hoạt động.

## 18. NUMA và huge pages

Server nhiều socket thường có NUMA nodes, mỗi node có local memory. Shared memory lớn có thể được phân bổ trên một hoặc nhiều NUMA nodes tùy kernel policy, first-touch behavior và process affinity.

### Tại sao quan tâm?

- Remote memory access có thể chậm hơn local access.
- Huge pages cần đủ contiguous memory trên node phù hợp.
- CPU pinning và memory policy có thể ảnh hưởng locality.
- Một node có thể thiếu huge pages dù tổng free memory toàn host còn nhiều.

### Kiểm tra

```sh
numactl --hardware
numastat
```

Không áp dụng numactl interleave hoặc CPU pinning theo công thức chung. Đo memory locality, CPU utilization và workload latency trước khi thay đổi NUMA policy.

## 19. Huge page allocation failure

Các nguyên nhân thường gặp:

- vm.nr_hugepages quá thấp.
- RAM bị phân mảnh, kernel không reserve đủ page.
- Page size không khớp.
- Service user thiếu quyền.
- Container không được cấp huge page resources.
- Shared memory requirement tăng sau thay đổi shared_buffers/max_connections/workers.

### Quy trình xử lý

1. Đọc PostgreSQL startup log.
2. Kiểm tra HugePages_Total, HugePages_Free, Hugepagesize.
3. Kiểm tra shared memory requirement.
4. Kiểm tra service account permissions.
5. Kiểm tra cgroup/container hugepage limits.
6. Reserve đủ pages trong maintenance window hoặc boot configuration.
7. Thử huge_pages=try nếu policy cho phép fallback.
8. Restart và xác minh.

Không giảm shared_buffers hoặc cấp quyền rộng ngay khi chưa biết nguyên nhân.

## 20. Swap là gì?

Swap là vùng storage mà Linux có thể dùng để lưu memory pages khi cần giải phóng RAM cho pages khác. Swap có thể là partition hoặc file. Nó là cơ chế của kernel, không phải bộ nhớ riêng mà PostgreSQL tự quản lý.

### Swap có thể hữu ích

- Tạo một vùng đệm nhỏ khi memory pressure ngắn hạn.
- Giữ các pages ít được dùng để nhường RAM cho working set.
- Giảm nguy cơ OOM trong một số tình huống.

### Swap có thể gây hại

- Database pages bị swap out có thể phải đọc lại từ storage, làm query latency tăng mạnh.
- Swap I/O cạnh tranh với database data/WAL I/O.
- Memory pressure có thể dẫn tới reclaim/thrashing.
- Latency có thể tăng khó dự đoán.

Mục tiêu là tránh sustained swap-in/swap-out pressure, không phải khẳng định mọi host database phải có hoặc không có swap trong mọi môi trường.

## 21. Kiểm tra swap trên Linux

```sh
free -h
swapon --show
cat /proc/swaps
vmstat 1
```

free cho biết tổng/free/available memory và swap usage. vmstat có các cột si (swap in) và so (swap out) theo chu kỳ. Swap used khác zero chưa đủ chứng minh đang có pressure; điều quan trọng là hoạt động swap-in/out và latency.

### Theo dõi xu hướng

Quan sát si/so liên tục trong giờ cao điểm, cùng memory available, major page faults, disk latency và PostgreSQL query latency. Một lượng swap cũ không hoạt động có thể ít đáng lo hơn swap churn liên tục.

## 22. vm.swappiness

vm.swappiness là tham số kernel ảnh hưởng xu hướng reclaim anonymous memory so với page cache. Nó không phải phần trăm RAM sẽ swap và không trực tiếp đặt một giới hạn swap cho PostgreSQL.

Kiểm tra:

```sh
sysctl vm.swappiness
```

Giá trị phù hợp phụ thuộc kernel version, workload, memory pressure và policy. Không sao chép một giá trị như 1 hoặc 10 mà không hiểu behavior của kernel hiện tại.

### Thay đổi

Có thể thử runtime trong môi trường kiểm soát:

```sh
sudo sysctl -w vm.swappiness=10
```

Nếu persist, dùng sysctl configuration theo distribution và xác minh sau reboot. Đo swap activity và page cache behavior trước/sau.

## 23. Swap policy cho PostgreSQL host

Không có một policy swap đúng cho mọi môi trường:

- Một số đội giữ swap nhỏ làm safety buffer nhưng alert ngay khi có sustained swap activity.
- Một số platform/database appliances đặt swap policy theo vendor support.
- Container có thể có swap limit riêng hoặc bị cấm swap.
- Kubernetes node behavior khác với container-level memory enforcement.

Điều quan trọng là hiểu memory limit thực tế, OOM policy, swap accounting và response khi memory pressure xảy ra.

### Không dùng swap để che memory overcommit

Nếu PostgreSQL thường xuyên cần swap để hoạt động, hãy kiểm tra memory budget, query concurrency, work_mem, shared_buffers, connection pools và container limits. Thêm swap có thể kéo dài thời gian trước OOM nhưng không giải quyết nguyên nhân.

## 24. OOM killer và PostgreSQL

Khi Linux không thể đáp ứng memory allocations, OOM killer có thể chọn process để kill. Trong container, cgroup memory limit có thể kích hoạt cgroup OOM dù host vẫn còn RAM.

Hậu quả có thể gồm:

- PostgreSQL backend bị kill và transaction rollback.
- Postmaster hoặc critical process bị kill, khiến database restart/crash recovery.
- Container bị restart bởi orchestrator.
- Nhiều pods bị ảnh hưởng nếu node memory pressure nghiêm trọng.

### Xác minh

```sh
dmesg -T | grep -i -E 'oom|killed process'
journalctl -k --since '1 hour ago' | grep -i oom
```

Trong container/cgroup v2, kiểm tra memory.events và orchestrator termination reason. Log path và quyền truy cập phụ thuộc platform.

## 25. Lập memory budget cho PostgreSQL

Memory budget cần tính:

1. Shared memory: shared_buffers và các cấu trúc shared khác.
2. Backend private memory: query execution, expressions, functions, extensions.
3. Concurrent query operations: work_mem/hash memory.
4. Maintenance/autovacuum workers.
5. Parallel workers.
6. OS/kernel/page cache.
7. Monitoring, backup agents, sidecars.
8. Safety headroom cho spikes và failover.

Một cách lập budget:

```text
Container/host memory limit
  - PostgreSQL shared memory
  - Estimated concurrent backend/query memory
  - Maintenance/parallel worker allowance
  - OS/kernel/sidecar overhead
  - Safety headroom
  = Remaining operational margin
```

### Không nhân work_mem với max_connections một cách máy móc

Không phải mọi connection đều chạy một sort/hash cùng lúc. Nhưng cũng không được giả định chỉ có một operation mỗi connection. Dùng workload concurrency, EXPLAIN plans và measured memory to calibrate estimate.

## 26. shared_buffers và huge pages trong memory budget

Nếu explicit huge pages được reserve, các pages này vẫn tiêu thụ RAM của host. Không cộng huge page reservation như một phần memory miễn phí ngoài shared_buffers.

Khi tính:

- Ước lượng shared memory PostgreSQL.
- Reserve huge pages đủ dùng.
- Tính phần RAM còn lại cho private memory và OS.
- Kiểm tra host/cgroup memory accounting.
- Đảm bảo huge page reservation không làm các processes khác thiếu RAM.

Trên một số hệ thống, hugetlb pages có accounting riêng so với ordinary cgroup memory; phải kiểm tra cgroup hugetlb controller và runtime policy.

## 27. Cgroups: resource control của container

Cgroups là cơ chế Linux kernel dùng để nhóm processes và giới hạn/đo tài nguyên. Container runtime thường dùng cgroups để thực thi CPU/memory constraints.

Các resource chính:

- Memory limit và usage.
- CPU shares/weight hoặc quota.
- Memory pressure/events.
- HugeTLB page limits trên hệ thống hỗ trợ.
- I/O controls.

### Cgroups v1 và v2

Linux có cgroups v1 và unified hierarchy v2. Tên file và semantics khác nhau. Không giả định mọi container đều dùng cùng path hoặc mọi metric tồn tại.

Kiểm tra:

```sh
stat -fc %T /sys/fs/cgroup
cat /proc/self/cgroup
```

Trên cgroup v2, filesystem thường có type cgroup2fs.

## 28. Cgroup v2 memory files

Một số file thường gặp:

| File | Ý nghĩa |
|---|---|
| memory.current | Memory hiện đang được tính cho cgroup |
| memory.max | Hard memory limit |
| memory.high | Ngưỡng pressure/throttling/reclaim |
| memory.events | Counters cho high/max/oom/oom_kill |
| memory.stat | Breakdown memory usage |
| memory.swap.current | Swap usage |
| memory.swap.max | Swap limit |
| memory.pressure | PSI memory pressure |

Kiểm tra path cgroup của process/container; không đọc /sys/fs/cgroup root rồi kết luận đó là limit của container nếu process nằm trong child cgroup.

Ví dụ:

```sh
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.swap.current
```

Giá trị max trong memory.max thường biểu thị không có hard limit ở cgroup đó. Parent cgroup vẫn có thể áp dụng giới hạn.

## 29. Cgroup memory pressure và OOM

Trong cgroup v2:

- memory.high có thể khiến reclaim/throttling khi usage vượt ngưỡng.
- memory.max là hard cap; vượt limit có thể dẫn đến OOM trong cgroup.
- memory.events tăng high, max, oom, oom_kill giúp xác định áp lực.
- memory.pressure cung cấp PSI để đánh giá thời gian tasks bị stall vì memory pressure.

### Container OOM khác host OOM

Host có thể còn RAM nhưng container đã chạm memory.max. PostgreSQL process trong container vẫn có thể bị kill. Vì vậy, free -h bên trong container hoặc trên host cần được đọc cùng cgroup limits/events.

## 30. CPU limits và PostgreSQL

Cgroup CPU quota có thể giới hạn thời gian CPU mà container được sử dụng trong mỗi period. Khi workload vượt quota, processes bị throttled dù host còn CPU idle.

Hệ quả:

- Query latency tăng.
- WAL replay/autovacuum chậm.
- Checkpoint/background tasks bị trì hoãn.
- Connection queues tăng.
- Health checks timeout.

Kiểm tra cgroup v2:

```sh
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
```

cpu.max thường biểu diễn quota và period; cpu.stat có throttling counters/time. Cgroup v1 dùng các files khác như cpu.cfs_quota_us/cpu.cfs_period_us.

### CPU request và limit

Trong Kubernetes, CPU request chủ yếu phục vụ scheduling/relative allocation; CPU limit có thể được thực thi bằng quota/throttling. Một PostgreSQL pod với limit quá thấp có thể bị throttle mạnh trong workload bursts.

## 31. /dev/shm và dynamic shared memory

Trên Linux, PostgreSQL có thể dùng POSIX shared memory cho dynamic shared memory segments, ví dụ một số hoạt động parallel query. Các segments này thường được tạo dưới /dev/shm khi dynamic_shared_memory_type là posix.

Kiểm tra:

```sql
SHOW dynamic_shared_memory_type;
SHOW min_dynamic_shared_memory;
```

Trên host/container:

```sh
df -h /dev/shm
mount | grep /dev/shm
```

### /dev/shm không phải shared_buffers

Main shared memory region của PostgreSQL và dynamic shared memory segments là các khái niệm khác nhau. Việc tăng /dev/shm không tự động tăng shared_buffers. Ngược lại, container có /dev/shm nhỏ có thể gặp lỗi khi workload cần dynamic shared memory dù memory limit tổng còn dư.

### Khi gặp lỗi

- Kiểm tra dung lượng và inode của /dev/shm.
- Xem PostgreSQL log có lỗi tạo shared memory segment không.
- Kiểm tra dynamic_shared_memory_type.
- Xác định parallel query/workload gây allocation.
- Tăng /dev/shm capacity hoặc điều chỉnh parallelism theo thiết kế runtime.

Không tắt parallel query như phản xạ đầu tiên nếu chưa xác định /dev/shm là nguyên nhân.

## 32. Docker memory và swap limits

Docker có thể đặt memory limit và swap limit cho container. Cú pháp và semantics phụ thuộc Docker Engine, kernel và cgroup version.

Ví dụ minh họa:

```sh
docker run \
  --memory=8g \
  --memory-swap=10g \
  --shm-size=1g \
  postgres:17
```

Ví dụ này minh họa ba giới hạn khác nhau:

- memory: giới hạn memory của container.
- memory-swap: tổng memory + swap limit theo semantics Docker; không phải lúc nào cũng có nghĩa là thêm đúng số swap ghi trong tên option.
- shm-size: kích thước tmpfs /dev/shm.

### Kiểm tra runtime thực tế

Không chỉ đọc command line. Kiểm tra docker inspect, cgroup files, container stats và host configuration. Docker có thể chạy trên cgroup v1/v2 với cách biểu diễn limits khác nhau.

### Swap policy

Nếu container không được phép dùng swap, memory pressure có thể dẫn tới OOM sớm hơn. Nếu cho phép swap, sustained swap I/O vẫn có thể làm PostgreSQL latency xấu. Chọn theo latency objective và platform policy.

## 33. Kubernetes memory requests và limits

Trong Kubernetes:

- memory request giúp scheduler đặt pod lên node có capacity phù hợp.
- memory limit đặt giới hạn cgroup cho container.
- Nếu container vượt memory limit, kernel có thể OOM-kill process trong container.
- Pod có thể bị restart tùy restart policy và workload controller.

Ví dụ:

```yaml
resources:
  requests:
    cpu: "2"
    memory: "8Gi"
  limits:
    cpu: "4"
    memory: "8Gi"
```

Đây chỉ là ví dụ cấu hình. PostgreSQL memory budget cần tính theo container limit và mọi sidecars/agents nếu chúng cùng bị giới hạn hoặc cạnh tranh node memory.

### QoS class

Kubernetes QoS class phụ thuộc requests/limits của containers trong pod. Guaranteed QoS thường yêu cầu CPU và memory requests bằng limits cho từng container; Burstable/BestEffort có behavior khác khi node pressure. Hiểu QoS và eviction policy của cluster trước khi chọn cấu hình.

## 34. Kubernetes huge pages

Kubernetes có thể expose pre-allocated huge pages như resources có kích thước cụ thể, ví dụ hugepages-2Mi hoặc hugepages-1Gi trên node hỗ trợ.

Các điều kiện thường cần:

1. Kernel node hỗ trợ page size đó.
2. Huge pages đã được reserve trên node trước khi pod được schedule.
3. Kubelet/runtime nhận diện resource.
4. Pod request/limit huge pages phù hợp.
5. Container có mapping/permissions tương thích với PostgreSQL.

Ví dụ resource request minh họa:

```yaml
resources:
  requests:
    hugepages-2Mi: "1Gi"
  limits:
    hugepages-2Mi: "1Gi"
```

Pod có thể cần volume mount với medium HugePages-2Mi theo thiết kế Kubernetes/runtime. Cấu hình chính xác phụ thuộc cluster version và page-size support.

### Huge pages không được overcommit như RAM thường

Huge page resources là tài nguyên node hữu hạn. Nếu node không reserve đủ, pod không schedule được. Đừng khai báo request huge pages trước khi xác nhận node capacity và PostgreSQL mapping behavior.

## 35. Kubernetes CPU limits và throttling

CPU request ảnh hưởng scheduling và relative CPU weight. CPU limit có thể được thực thi bằng CFS quota. Một PostgreSQL process chạy nhiều workers có thể bị throttle khi tổng CPU time vượt quota.

Kiểm tra pod/container metrics:

- CPU usage.
- CPU throttled periods.
- CPU throttled seconds.
- Run queue/CPU pressure ở node.
- Query latency, WAL replay lag và autovacuum duration.

### Khi nào nên tránh CPU limit quá thấp?

Database workload có bursty queries, checkpoint, vacuum và parallel execution. CPU limit quá thấp có thể làm những background tasks chậm, dẫn đến lag hoặc storage pressure. Chọn requests/limits theo capacity planning và platform policy, rồi benchmark.

## 36. Persistent volumes cho PostgreSQL

PostgreSQL data directory phải nằm trên storage có durability và lifecycle phù hợp. Trong container orchestration, dùng persistent volume/claim hoặc storage service được hỗ trợ thay cho container writable layer.

### Phân biệt storage

| Loại | Dùng cho | Rủi ro |
|---|---|---|
| Container writable layer | Runtime files tạm | Có thể mất khi container bị recreate |
| Persistent volume | PGDATA/WAL/tablespaces | Cần kiểm tra durability/latency/attachment semantics |
| Ephemeral volume | Temp/cache/log staging | Không phù hợp làm nguồn dữ liệu bền vững |
| Backup object storage | Backup/archive repository | Cần restore/consistency workflow |

Không đặt PGDATA chỉ trong container layer rồi kỳ vọng dữ liệu tồn tại qua reschedule/recreate.

## 37. Filesystem và yêu cầu durability

PostgreSQL dựa vào filesystem/storage semantics để đảm bảo WAL và data được ghi bền vững theo cấu hình durability. Filesystem cần hỗ trợ locking, fsync và semantics được PostgreSQL/platform hỗ trợ.

Các filesystem Linux thường gặp như ext4 và XFS có thể dùng cho PostgreSQL khi được cấu hình đúng. Không có một filesystem duy nhất tốt nhất cho mọi workload; benchmark và vendor/storage guidance rất quan trọng.

### Điều cần kiểm tra

- Filesystem có được hỗ trợ bởi OS/storage vendor không?
- Mount options có giữ durability semantics không?
- Storage có flush/barrier semantics đúng không?
- Latency fsync ổn định không?
- Snapshot/backup process có phối hợp với PostgreSQL không?
- Có đủ free space và inode không?

## 38. fsync và full_page_writes

PostgreSQL dùng WAL để bảo vệ data changes. Hai settings quan trọng:

```sql
SHOW fsync;
SHOW full_page_writes;
SHOW synchronous_commit;
```

- fsync=on yêu cầu PostgreSQL đảm bảo writes được flush theo cơ chế hệ thống.
- full_page_writes=on ghi full page image vào WAL ở lần thay đổi đầu tiên sau checkpoint để bảo vệ khỏi torn page trong một số failure modes.
- synchronous_commit điều khiển mức commit acknowledgment, không thay thế fsync.

### Không tắt durability để sửa I/O chậm

Tắt fsync hoặc full_page_writes có thể làm mất/corrupt dữ liệu sau crash/power loss. Chỉ thay đổi khi hiểu đầy đủ rủi ro và có use case được phê duyệt, ví dụ disposable benchmark/test environment. Production cần giữ durability policy phù hợp.

## 39. Mount options và storage semantics

Không áp dụng mount options từ blog mà không kiểm tra filesystem/kernel/storage. Một số options ảnh hưởng atime, barriers, journaling, write cache và durability.

### Những câu hỏi cần trả lời

- Storage có write cache được bảo vệ bằng battery/flash không?
- fsync có thực sự flush tới stable storage không?
- Snapshot có crash-consistent hay application-consistent?
- Volume có giới hạn IOPS/throughput không?
- Có burst credits và throttling sau khi dùng hết không?
- Có multi-attach hoặc fencing behavior phù hợp không?

### NFS và network storage

Không mặc định mọi NFS/export đều phù hợp cho PGDATA. Chỉ dùng network storage khi PostgreSQL version, OS, NFS protocol, locking, fsync và vendor support đáp ứng yêu cầu. Kiểm tra latency, failure semantics và fencing; một mount hoạt động không đồng nghĩa đã có durability đúng.

## 40. Tổ chức PGDATA, pg_wal và tablespaces

PostgreSQL có thể đặt PGDATA, WAL và tablespaces trên các filesystems/volumes khác nhau, nhưng tách riêng chỉ hữu ích khi có lý do về capacity, I/O isolation hoặc operational policy.

### PGDATA

Chứa cluster metadata, relation files, catalogs và các file cấu hình/trạng thái theo layout. Cần backup/restore và permission policy đúng.

### pg_wal

Chứa WAL segments cần cho crash recovery, replication và archiving. Nếu filesystem đầy, PostgreSQL có thể không tiếp tục ghi transaction.

### Tablespaces

Cho phép đặt relation data ở locations khác nhau. Mỗi tablespace cần storage, mount và backup/restore mapping rõ.

### Không tách WAL một cách tùy tiện

Đặt pg_wal trên volume chậm hoặc volume hết dung lượng độc lập có thể làm cluster dừng ghi. Nếu tách, phải có monitoring riêng, capacity reserve và recovery plan.

## 41. Dung lượng filesystem và inode

Filesystem có hai giới hạn khác nhau:

- Block capacity: dung lượng bytes còn lại.
- Inode capacity: số lượng filesystem objects còn có thể tạo.

Một filesystem có thể còn GB free nhưng hết inode, khiến PostgreSQL hoặc exporter không tạo được file mới.

Kiểm tra:

```sh
df -h
df -i
findmnt
```

### Theo dõi mountpoint cụ thể

Alert từng filesystem chứa PGDATA, pg_wal, tablespaces, logs, temp files và backup staging. Tổng free disk của host có thể che giấu một mount riêng đã đầy.

### Không xóa file database thủ công

Không xóa file trong base, global hoặc pg_wal để giải phóng dung lượng. Xác định đúng nguồn tăng trưởng và dùng PostgreSQL-aware cleanup/retention procedure.

## 42. WAL growth và replication slots

WAL có thể tăng vì write workload, checkpoint/full-page writes, replication lag, archive failure hoặc replication slots giữ segments cần thiết.

Kiểm tra slot:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots;
```

Một số columns phụ thuộc PostgreSQL version. Kiểm tra schema view trên instance thực tế.

### Kiểm tra WAL directory

```sql
SELECT *
FROM pg_catalog.pg_ls_waldir()
ORDER BY modification DESC
LIMIT 20;
```

Function này yêu cầu quyền phù hợp. Dùng số liệu từ filesystem/exporter và slot metrics để hiểu retention; đừng chỉ dựa vào số file trong directory.

### Không xóa WAL thủ công

Không dùng rm trong pg_wal. PostgreSQL quản lý WAL recycling/removal theo checkpoint, replication slots, archive và recovery state. Xóa thủ công có thể làm cluster không thể recover hoặc replica không thể bắt kịp.

## 43. WAL archiving và filesystem pressure

Nếu archive command thất bại, WAL có thể tích tụ trong pg_wal. Kiểm tra:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_catalog.pg_stat_archiver;
```

### Alert nên có

- Archive failures tăng.
- Thời gian từ lần archive thành công gần nhất vượt policy.
- WAL directory tăng liên tục.
- Disk free/time-to-full giảm.
- Replication slot giữ WAL vượt budget.

Không giải quyết bằng cách xóa archive backlog trước khi hiểu backup/PITR chain.

## 44. Temporary files và temp_tablespaces

Sort/hash operations vượt memory budget có thể spill ra temporary files. Temporary tables cũng có thể tạo I/O và dùng filesystem.

Kiểm tra:

```sql
SHOW temp_file_limit;
SHOW temp_tablespaces;
```

Stats theo database có thể cho biết temp_files/temp_bytes:

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes
FROM pg_catalog.pg_stat_database
ORDER BY temp_bytes DESC;
```

Stats là cumulative từ lần reset gần nhất; dùng delta/rate theo thời gian. Temp file spikes có thể chỉ ra query spill, work_mem thấp hoặc query plan không hiệu quả.

## 45. Backup và filesystem

Backup có thể tạo tải I/O lớn và cần staging space. Theo dõi riêng:

- Backup destination free space.
- Backup duration/throughput.
- WAL archive backlog.
- Temporary staging files.
- Snapshot retention.
- Restore workspace capacity.

Backup repository không nên phụ thuộc duy nhất vào cùng filesystem có thể bị đầy bởi PGDATA/WAL. Nếu dùng snapshots, xác định consistency protocol và retention.

### Restore capacity

Có đủ chỗ cho backup không đồng nghĩa có đủ chỗ restore. Cần tính data size, WAL replay, temporary expansion, indexes và growth headroom khi diễn tập restore.

## 46. Overlay filesystem trong container

Container writable layer thường được triển khai bằng overlay filesystem. Nó hữu ích cho application image layers, nhưng không nên mặc định là storage tối ưu cho PostgreSQL data.

Rủi ro:

- Data có thể mất khi container bị recreate nếu không có persistent volume.
- Copy-on-write overhead có thể ảnh hưởng I/O.
- Disk usage bị tính vào ephemeral storage/node capacity.
- Cleanup image/layer không giải quyết được volume đầy.

Đặt PGDATA trên persistent volume được hỗ trợ và kiểm tra mount path bên trong container.

## 47. Ephemeral storage và Kubernetes eviction

Kubernetes có thể theo dõi ephemeral storage usage của container/pod và node. Logs, writable layer và emptyDir có thể góp vào ephemeral storage consumption.

Nếu vượt limits hoặc node bị disk pressure, pod có thể bị eviction. Đây là failure mode khác với PostgreSQL memory OOM.

### Kiểm tra

- Pod requests/limits cho ephemeral-storage.
- Node condition DiskPressure.
- Container writable layer usage.
- emptyDir usage.
- Container logs rotation.
- Kubelet eviction events.

Không đặt backup staging hoặc PostgreSQL data bền vững vào emptyDir nếu không có policy phục hồi phù hợp.

## 48. Monitoring memory và huge pages

Thu thập trên host:

- MemAvailable.
- Swap used và swap-in/swap-out rate.
- Major page faults.
- HugePages_Total/Free/Rsvd/Surp.
- THP enabled/defrag state.
- NUMA memory distribution.
- OOM events và memory PSI.

Thu thập ở PostgreSQL:

- shared_buffers/work_mem/maintenance settings.
- max_connections và active backends.
- Parallel workers.
- Temp files/temp_bytes.
- Autovacuum workers và maintenance activity.
- Query latency và throughput.

Thu thập ở container:

- memory.current/max/high.
- memory.events và memory.pressure.
- memory.swap.current/max.
- CPU quota/throttling.
- Container restart/OOM reason.

## 49. Monitoring filesystem và storage I/O

Theo dõi theo từng mount:

- Used bytes/percent.
- Free bytes.
- Free inodes.
- Growth rate/time-to-full.
- Read/write throughput.
- IOPS và queue depth.
- Read/write latency.
- fsync latency nếu có instrumentation.
- Volume throttling/burst credits.

### PostgreSQL signals liên quan

- WAL bytes generated.
- Checkpoint frequency/duration.
- Buffers written.
- Temp bytes.
- Archive failures.
- Replication slot retention.
- Query latency.

Kết hợp storage metrics với database metrics để phân biệt disk saturation với query plan/lock issues.

## 50. Memory pressure trong container và host

Khi thấy PostgreSQL chậm, so sánh:

1. Host MemAvailable và swap activity.
2. Container memory.current so với memory.max.
3. memory.events, memory.pressure và OOM counters.
4. PostgreSQL shared/private workload signals.
5. Sidecar/agent memory usage.
6. CPU throttling và I/O pressure.

Nếu host còn RAM nhưng container chạm limit, tăng host RAM không tự giải quyết container cap. Nếu container usage thấp nhưng host memory pressure cao, cần xem node contention và page cache/kernel.

## 51. Quy trình sizing tài nguyên

Một quy trình thực tế:

1. Đo baseline workload theo giờ cao điểm và batch windows.
2. Ghi lại host RAM, CPU, storage IOPS/throughput/latency.
3. Xác định container requests/limits và cgroup version.
4. Đo shared_buffers và shared memory size.
5. Ước lượng concurrent work_mem/hash operations.
6. Tính maintenance/autovacuum/parallel worker allowance.
7. Dự trù OS page cache, kernel, monitoring và safety headroom.
8. Quyết định explicit huge pages sau benchmark.
9. Đặt swap/OOM policy theo platform.
10. Tính capacity PGDATA, pg_wal, tablespaces, temp và backup.
11. Kiểm tra /dev/shm và ephemeral storage riêng.
12. Load test, failover test và theo dõi sau rollout.

### Đặt headroom

Không sizing đúng bằng mức sử dụng trung bình. Cần headroom cho traffic spikes, maintenance, failover, catch-up replication và restore/upgrade tasks.

## 52. Troubleshooting: PostgreSQL không khởi động vì huge pages

1. Đọc log startup đầu tiên liên quan shared memory/huge pages.
2. Kiểm tra huge_pages setting.
3. Kiểm tra HugePages_Total/Free và Hugepagesize.
4. So sánh actual shared memory requirement.
5. Kiểm tra user/group/capabilities.
6. Kiểm tra container hugetlb resource limits.
7. Reserve pages đúng page size.
8. Thử huge_pages=try nếu fallback được policy cho phép.
9. Restart và xác nhận log.

Không giảm huge page reservation hoặc đổi shared_buffers một cách ngẫu nhiên; xác định chính xác thiếu pages, permission hay cgroup limit.

## 53. Troubleshooting: swap activity tăng

1. Xem vmstat si/so theo thời gian.
2. Kiểm tra MemAvailable và memory pressure.
3. Kiểm tra container memory.current/max nếu có.
4. Tìm processes/containers dùng memory lớn.
5. Kiểm tra work_mem, concurrency và parallel workers.
6. Kiểm tra connection pool và query workload.
7. Xem disk I/O latency và query latency.
8. Giảm concurrency hoặc memory exposure theo workload.
9. Điều chỉnh memory limits/sizing nếu cần.
10. Xác nhận swap-in/out giảm và latency phục hồi.

## 54. Troubleshooting: container OOMKilled

1. Xem pod/container termination reason và exit status.
2. Kiểm tra cgroup memory.events.
3. Kiểm tra memory.current/max/high trước sự cố nếu metrics có.
4. Kiểm tra node memory pressure và kernel logs.
5. Xác định PostgreSQL hay sidecar bị kill.
6. Kiểm tra shared_buffers, work_mem, concurrency và parallelism.
7. Kiểm tra restart/crash recovery logs.
8. Tăng limit hoặc giảm memory exposure dựa trên đo lường.
9. Đảm bảo request phù hợp để scheduler chọn node đủ capacity.
10. Load test lại dưới giới hạn mới.

## 55. Troubleshooting: PostgreSQL bị CPU throttling

1. Đọc cpu.stat/throttling metrics.
2. So sánh CPU request, limit và host capacity.
3. Kiểm tra query latency và run queue.
4. Kiểm tra autovacuum/WAL replay/checkpoint duration.
5. Kiểm tra parallel query worker count.
6. Tối ưu query và giới hạn concurrency nếu cần.
7. Điều chỉnh CPU request/limit theo workload và policy.
8. Đo throttling và throughput sau thay đổi.

## 56. Troubleshooting: filesystem đầy

1. Xác định đúng mountpoint bằng df -h.
2. Kiểm tra inode bằng df -i.
3. Xác định thư mục tăng bằng công cụ filesystem phù hợp.
4. Kiểm tra pg_wal, replication slots và archive failures.
5. Kiểm tra temp files, logs, backups và tablespaces.
6. Xác định retention/owner của files.
7. Dùng PostgreSQL-aware cleanup hoặc mở rộng volume theo runbook.
8. Không xóa files trong pg_wal/base/global thủ công.
9. Theo dõi free bytes/inodes và PostgreSQL write health.
10. Cập nhật alert headroom nếu phát hiện muộn.

## 57. Troubleshooting: hết inode

Nếu df -h còn dung lượng nhưng tạo file thất bại:

- Kiểm tra df -i.
- Xác định directory tạo nhiều files nhỏ.
- Kiểm tra logs, temp files, archive staging và backup metadata.
- Cleanup theo retention policy.
- Đánh giá filesystem inode density nếu tạo volume mới.

Không xóa data files theo tên hoặc tuổi file khi chưa xác nhận ownership.

## 58. Troubleshooting: /dev/shm hết dung lượng

1. Kiểm tra df -h và df -i cho /dev/shm.
2. Kiểm tra dynamic_shared_memory_type.
3. Xem PostgreSQL logs và query parallelism.
4. Kiểm tra các processes khác dùng tmpfs.
5. Tăng shm-size/volume capacity theo container policy hoặc điều chỉnh workload.
6. Restart/retry chỉ theo quy trình sau khi xác nhận resource đã đủ.

Phân biệt /dev/shm full với container memory.max reached; đây là hai giới hạn khác nhau.

## 59. Runbook: memory budget và OOM review

1. Ghi lại memory limit host/container.
2. Thu thập cgroup current/max/events/pressure.
3. Ghi nhận shared_buffers và shared memory.
4. Ước lượng work_mem operations × concurrency.
5. Tính maintenance/autovacuum/parallel workers.
6. Kiểm tra sidecars, exporters và backup agents.
7. Đối chiếu swap/OOM events với workload timeline.
8. Xác định bottleneck là PostgreSQL config, concurrency hay container limit.
9. Thay đổi một nhóm tham số có kiểm soát.
10. Load test và xác minh headroom.

## 60. Checklist triển khai huge pages, swap, filesystem và containers

### Huge pages

- Xác định kernel/page size support.
- Ước lượng shared memory requirement.
- Reserve đúng số huge pages trên host.
- Xác nhận permissions và cgroup/runtime support.
- Kiểm tra THP policy.
- Bật huge_pages theo rollout plan.
- Xác nhận logs và kernel mappings.
- Benchmark trước/sau.

### Swap và memory

- Memory budget có private/shared/OS/sidecar headroom.
- work_mem được tính theo operations và concurrency.
- Swap activity được theo dõi.
- OOM events/PSI được giám sát.
- Container memory limit không thấp hơn peak budget.
- Connection/query concurrency được giới hạn.

### Filesystem/storage

- PGDATA nằm trên persistent storage.
- fsync/full_page_writes policy được giữ phù hợp.
- PGDATA, pg_wal, tablespaces và backup có capacity monitoring.
- Free bytes và inodes được alert.
- WAL slots/archive retention có monitoring.
- IOPS/latency/throttling được theo dõi.
- Không xóa WAL/data files thủ công.

### Containers

- Cgroup version và effective limits được xác định.
- CPU requests/limits được benchmark.
- memory.current/max/events được theo dõi.
- /dev/shm capacity đủ cho workload.
- Persistent volume và ephemeral storage được phân biệt.
- Kubernetes OOM/eviction/restart events được alert.
- Huge page resources được reserve và schedule đúng.

## 61. Bài tập thực hành

### Bài 1 — Memory layout

Phân biệt shared memory, backend-private memory, OS page cache và kernel memory trong một PostgreSQL instance.

### Bài 2 — RSS accounting

Vì sao cộng RSS của tất cả PostgreSQL processes có thể đếm trùng shared memory? Nên dùng thêm những metrics nào?

### Bài 3 — work_mem

Một query có ba sort/hash operations và chạy với bốn parallel workers. Vì sao không thể coi work_mem là giới hạn memory của một connection?

### Bài 4 — shared_buffers

Vì sao shared_buffers khoảng 25% RAM chỉ là điểm bắt đầu? Liệt kê các yếu tố ảnh hưởng sizing.

### Bài 5 — Huge pages

Giải thích huge pages giảm page table/TLB overhead thế nào và vì sao chúng không làm RAM tăng lên.

### Bài 6 — Huge page calculation

Shared memory region cần 10 GiB, huge page size 2 MiB. Tính số pages tối thiểu theo phép chia đơn giản và nêu các overhead cần xét.

### Bài 7 — huge_pages modes

So sánh try, on và off. Trường hợp nào server có thể không khởi động?

### Bài 8 — Kernel reserve

Viết lệnh kiểm tra vm.nr_hugepages, HugePages_Total, HugePages_Free và Hugepagesize.

### Bài 9 — Permissions

Một PostgreSQL service không thể map huge pages dù kernel đã reserve đủ. Những quyền/capabilities nào cần điều tra?

### Bài 10 — THP

Phân biệt Transparent Huge Pages với explicit hugetlb pages. Vì sao database workload có thể quan tâm THP defrag?

### Bài 11 — NUMA

Một server hai socket có đủ huge pages tổng thể nhưng startup không reserve được trên node phù hợp. Giải thích NUMA locality và cách kiểm tra.

### Bài 12 — Swap

Swap used là 4 GB nhưng si/so bằng 0 trong thời gian dài. Vì sao chưa thể kết luận database đang thrashing?

### Bài 13 — swappiness

Giải thích vm.swappiness và vì sao giá trị 1 không có nghĩa Linux chỉ dùng 1% swap.

### Bài 14 — OOM

Phân biệt host OOM và cgroup/container OOM. Viết các nguồn log/metrics cần kiểm tra.

### Bài 15 — Memory budget

Thiết kế memory budget cho shared_buffers, work_mem operations, maintenance workers, OS page cache, sidecars và safety headroom.

### Bài 16 — Cgroup v2

Giải thích memory.current, memory.max, memory.high, memory.events và memory.pressure.

### Bài 17 — CPU throttling

Đọc cpu.max và cpu.stat. Throttling có thể làm WAL replay, autovacuum và query latency thay đổi thế nào?

### Bài 18 — Docker limits

Giải thích sự khác nhau giữa --memory, --memory-swap và --shm-size trong Docker.

### Bài 19 — /dev/shm

Vì sao /dev/shm full có thể làm parallel query gặp lỗi dù container memory limit chưa đạt?

### Bài 20 — Kubernetes requests/limits

Phân biệt CPU/memory requests và limits. Một pod PostgreSQL có memory limit thấp hơn peak memory sẽ gặp rủi ro gì?

### Bài 21 — Kubernetes huge pages

Nêu các điều kiện cần để pod yêu cầu hugepages-2Mi và PostgreSQL sử dụng được pages đó.

### Bài 22 — Persistent volume

Vì sao PGDATA không nên nằm trong container writable layer? Phân biệt persistent volume và ephemeral storage.

### Bài 23 — Filesystem durability

Giải thích vì sao PostgreSQL cần filesystem/storage có fsync semantics đáng tin cậy.

### Bài 24 — fsync và full_page_writes

Nêu vai trò của hai settings này. Tại sao không nên tắt chúng chỉ để tăng benchmark throughput?

### Bài 25 — PGDATA và pg_wal

Một cluster dùng hai filesystems riêng cho PGDATA và pg_wal. Những capacity, failure và monitoring concerns nào cần có?

### Bài 26 — Inodes

Filesystem còn 20 GB nhưng hết inode. PostgreSQL có thể gặp những lỗi gì? Dùng lệnh nào để kiểm tra?

### Bài 27 — Replication slots

Một logical slot inactive giữ WAL và làm pg_wal tăng. Viết query kiểm tra slot và mô tả cách điều tra owner/retention.

### Bài 28 — Archive failures

Viết query đọc pg_stat_archiver và nêu các alert cần thiết khi archive backlog tăng.

### Bài 29 — Temporary files

Dùng pg_stat_database để theo dõi temp_files/temp_bytes. Những nguyên nhân nào có thể làm temp I/O tăng?

### Bài 30 — Storage I/O

Liệt kê IOPS, throughput, queue depth, latency và volume throttling metrics cần theo dõi cho PostgreSQL.

### Bài 31 — Network storage

Vì sao một NFS mount hoạt động không đủ chứng minh storage phù hợp cho PGDATA? Nêu durability/locking/fencing concerns.

### Bài 32 — Overlay filesystem

Giải thích copy-on-write overhead và rủi ro mất dữ liệu khi lưu PGDATA trong container layer.

### Bài 33 — Ephemeral storage

Một pod bị eviction do DiskPressure dù persistent volume còn chỗ. Những loại ephemeral storage nào cần kiểm tra?

### Bài 34 — Monitoring

Thiết kế dashboard kết hợp host memory, swap, huge pages, cgroup memory, CPU throttling và PostgreSQL query metrics.

### Bài 35 — Huge page failure

PostgreSQL startup fail với huge_pages=on. Viết runbook xác định thiếu reservation, permission hay container hugetlb limit.

### Bài 36 — Swap pressure

Database latency tăng cùng swap-in/out. Mô tả quy trình điều tra memory budget, concurrency và cgroup limits.

### Bài 37 — Container OOMKilled

Một PostgreSQL pod restart với OOMKilled nhưng node vẫn còn RAM. Giải thích cách dùng memory.events và pod status để xác định nguyên nhân.

### Bài 38 — Filesystem full

pg_wal filesystem đầy. Liệt kê các nguồn tăng trưởng cần kiểm tra và giải thích vì sao không được rm WAL files thủ công.

### Bài 39 — CPU throttling

Sau khi đặt CPU limit, query latency và replication lag cùng tăng. Thiết kế phép đo trước/sau và cách điều chỉnh quota.

### Bài 40 — Thiết kế tài nguyên PostgreSQL trong Kubernetes

Một cluster có:

- PostgreSQL primary 512 GiB RAM trên node NUMA hai socket.
- shared_buffers 128 GiB.
- 200 application connections qua PgBouncer.
- Query workload có sort/hash operations và parallel workers.
- Hai physical standbys.
- PGDATA và pg_wal trên persistent volumes riêng.
- Pod memory limit 160 GiB.
- Node đã reserve một số huge pages 2 MiB.
- /dev/shm mặc định nhỏ.
- Backup staging dùng ephemeral storage.

Hãy thiết kế:

1. Memory budget gồm shared memory, work_mem exposure, workers, OS và headroom.
2. Huge page count estimate, host reservation và PostgreSQL huge_pages mode.
3. THP/NUMA policy và cách benchmark.
4. Swap/OOM policy và cgroup v2 metrics.
5. CPU requests/limits để tránh throttling quá mức.
6. /dev/shm size và dynamic shared memory configuration.
7. PGDATA/pg_wal persistent volume capacity và durability checks.
8. Inode, temp, archive và backup staging monitoring.
9. Kubernetes hugepages resources, scheduling và pod restart policy.
10. Runbooks cho OOM, disk full, WAL retention và huge page startup failure.

## Kết luận

**Tối ưu tài nguyên PostgreSQL cần tính cả shared memory, private memory, OS, storage và giới hạn runtime.** Explicit huge pages có thể giảm page-table overhead cho shared memory lớn, nhưng cần reserve đúng page size, quyền truy cập và xác minh mapping. THP là cơ chế khác và cần được đánh giá riêng. Swap có thể làm vùng đệm cho memory pressure, nhưng sustained swap-in/out thường là dấu hiệu sizing hoặc concurrency cần điều tra.

Filesystem phải cung cấp durability semantics đáng tin cậy cho WAL/data, đủ bytes và inodes, cùng I/O latency/throughput phù hợp. Theo dõi riêng PGDATA, pg_wal, tablespaces, temp, logs và backup staging. Giữ fsync/full_page_writes theo durability policy; không xóa WAL hoặc relation files thủ công để giải phóng disk.

Trong container, effective limits đến từ cgroups và orchestrator. Host còn RAM không bảo đảm container không OOM; CPU quota có thể throttle query/replay; /dev/shm và ephemeral storage là các giới hạn riêng. Persistent volumes cần được dùng cho dữ liệu bền vững, còn memory budget phải tính sidecars, query concurrency và headroom.

Cuối cùng, hãy đo baseline, load test dưới đúng container limits, theo dõi cgroup/host/PostgreSQL metrics và diễn tập OOM/disk/restore procedures trong môi trường kiểm soát. **Cấu hình tốt là cấu hình có headroom, durability rõ ràng và được xác minh dưới workload thực tế.**
