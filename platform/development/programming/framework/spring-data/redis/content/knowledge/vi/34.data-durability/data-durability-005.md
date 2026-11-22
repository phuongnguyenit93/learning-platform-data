# Chi phí snapshot, ghi lại AOF và áp lực bộ nhớ trong Spring Data Redis

Redis thường được biết đến là hệ thống lưu trữ trong bộ nhớ có độ trễ thấp. Tuy nhiên, khi Redis chứa dữ liệu cần khôi phục sau khi tiến trình hoặc máy chủ bị lỗi, người vận hành phải cân nhắc **độ bền dữ liệu (durability)**. Hai cơ chế persistence quen thuộc là **RDB snapshot** và **AOF (Append Only File)**. Chúng giúp Redis ghi trạng thái ra đĩa, nhưng đồng thời tạo chi phí **CPU, bộ nhớ, disk I/O, độ trễ, thời gian khởi động lại và không gian lưu trữ**.

Trong Redis, tạo RDB snapshot nền thường dùng `BGSAVE`; viết lại AOF nền thường dùng `BGREWRITEAOF`. Cả hai công việc có thể dùng cơ chế **`fork()` và copy-on-write (COW)** trên hệ điều hành hỗ trợ. Redis tiếp tục phục vụ lệnh ở tiến trình cha trong khi tiến trình con tạo dữ liệu bền vững. Điều này giảm thời gian tạm dừng toàn bộ server so với snapshot đồng bộ, nhưng **không có nghĩa background persistence không tốn RAM hoặc không ảnh hưởng latency**.

Với Spring Data Redis, lập trình viên có thể không trực tiếp gọi `BGSAVE` hoặc `BGREWRITEAOF`, nhưng vẫn cảm nhận chi phí này qua:

- `GET`, `SET`, `INCR`, `HSET` tăng latency hoặc timeout.
- Redis container bị OOM-kill khi memory usage tăng trong lúc snapshot/rewrite.
- Các lệnh ghi bị từ chối khi persistence lỗi hoặc đĩa đầy, tùy cấu hình.
- Thời gian khôi phục sau restart kéo dài hơn dự kiến.
- Một số write được ứng dụng nhận là thành công nhưng chưa kịp bền vững trên đĩa.
- Cache miss và load database tăng sau khi Redis restart với tập dữ liệu không đầy đủ.

Bài này giải thích cơ chế chi phí của RDB/AOF, cách đọc metric liên quan đến fork/COW/RSS, phương pháp chọn cấu hình, cách đo trong Spring Data Redis và cách kiểm thử áp lực bộ nhớ trước khi triển khai.

## 1. Bối cảnh: Redis in-memory nhưng vẫn có persistence

Một lệnh Redis cơ bản:

```redis
SET order:1001:status PAID
```

thay đổi trạng thái dữ liệu trong bộ nhớ của Redis. **Phản hồi `OK` không tự động mang nghĩa dữ liệu đã được `fsync` xuống thiết bị lưu trữ**. Độ bền sau sự cố phụ thuộc chính sách persistence và cả storage/hạ tầng bên dưới.

Mô hình tổng quát:

```text
Spring Data Redis
    |
    | SET / INCR / HSET / XADD
    v
Redis main process (in-memory dataset)
    |
    +---------------------+
    |                     |
    v                     v
RDB snapshot           AOF logging
    |                     |
    | BGSAVE              | ghi command vào AOF
    |                     | fsync theo chính sách
    v                     v
RDB file              AOF files
    |                     |
    +----------+----------+
               |
               v
        Restart / recovery
```

RDB và AOF phục vụ những mục tiêu khác nhau:

| Tiêu chí | RDB snapshot | AOF |
|---|---|---|
| Dữ liệu ghi ra đĩa | Ảnh chụp dataset tại một mốc | Log các lệnh có tác dụng thay đổi trạng thái, với định dạng/phương thức tương ứng |
| Mốc bền vững | Theo lần snapshot thành công | Theo việc append và fsync theo policy |
| Mất dữ liệu khi crash | Có thể mất thay đổi từ snapshot gần nhất | Phụ thuộc `appendfsync` và điều kiện sự cố |
| Công việc nền lớn | `BGSAVE` | `BGREWRITEAOF` |
| Tài nguyên đáng chú ý | Fork/COW, CPU serialize/compress, disk I/O | Append/fsync, fork/COW khi rewrite, disk I/O và file management |
| Dung lượng file | Thường gọn cho ảnh chụp dữ liệu | Có thể tăng theo số command; rewrite giúp rút gọn |
| Khởi động lại | Đọc ảnh chụp dataset | Nạp lại trạng thái từ các AOF components theo phiên bản/cấu hình |
| Tác động khi tải ghi lớn | COW tăng khi child còn chạy | Append liên tục + rewrite dài và COW |

Không có phương án nào bảo đảm tuyệt đối **zero data loss** trong mọi điều kiện phần cứng, crash, failover hoặc cấu hình. Nếu ứng dụng cần giao dịch bền vững chặt, hãy xác định rõ yêu cầu RPO/RTO và cân nhắc nguồn dữ liệu thích hợp.

## 2. Phân biệt bốn loại “chi phí”

Khi nghe “snapshot Redis tốn bộ nhớ”, không nên chỉ nhìn một chỉ số RAM. Có ít nhất bốn nhóm chi phí:

1. **Độ trễ thời điểm fork:** tiến trình cha có thể tạm dừng ngắn để tạo tiến trình con và thiết lập cấu trúc quản lý bộ nhớ.
2. **Bộ nhớ COW:** các trang bộ nhớ bị sửa trong khi child vẫn tham chiếu ảnh chụp cũ có thể cần bản sao vật lý.
3. **CPU và disk I/O nền:** child duyệt, serialize, nén hoặc ghi file lớn; cạnh tranh tài nguyên với Redis và các ứng dụng khác.
4. **Chi phí liên tục của AOF:** append, writeback và `fsync` ở những thời điểm khác nhau có thể tăng disk latency ngay cả khi không có rewrite.

Ngoài ra còn có:

- Bộ nhớ của Redis allocator, client buffers, replication buffers.
- OS page cache phục vụ file đang được ghi/đọc.
- Thời gian đọc file persistence khi Redis khởi động.
- Dung lượng disk cần để tồn tại song song file cũ và file mới trong lúc rewrite/snapshot.
- Số request và connection đang chờ khi event-loop Redis bị ảnh hưởng.

Một phép đo migration hoặc capacity planning chỉ ghi `used_memory` trước/sau BGSAVE sẽ **không đủ** để kết luận an toàn bộ nhớ.

## 3. `BGSAVE` tạo RDB snapshot thế nào?

`BGSAVE` yêu cầu Redis tạo snapshot ở background. Trên những nền tảng Redis sử dụng `fork()`, quá trình thường là:

```text
Redis parent
    |
    | BGSAVE requested
    v
fork()
    |
    +--> Parent tiếp tục nhận GET/SET/INCR
    |
    +--> Child thấy trạng thái bộ nhớ tại mốc fork
             |
             | serialize dataset thành RDB
             | có thể nén và ghi ra disk
             v
        RDB file tạm
             |
             | hoàn thành, thay thế file snapshot theo cơ chế Redis
             v
        Snapshot RDB mới
```

Dữ liệu child nhìn thấy phản ánh trạng thái tại thời điểm snapshot bắt đầu. Những ghi phát sinh sau đó được parent xử lý và có thể làm thay đổi bộ nhớ của parent; chúng **không tự được thêm vào RDB snapshot đang tạo**.

### 3.1. Vì sao không dùng `SAVE` trong luồng vận hành thông thường?

Redis có lệnh:

```redis
SAVE
```

để tạo snapshot đồng bộ. Trong khi lệnh này chạy, server có thể bị chặn xử lý các lệnh bình thường cho tới khi công việc lưu hoàn tất.

Lệnh:

```redis
BGSAVE
```

cho phép Redis tiếp tục phục vụ nhiều công việc trong lúc child ghi snapshot. Nhưng `BGSAVE` **không hoàn toàn miễn phí**: vẫn có chi phí fork, COW và tranh chấp I/O.

Trong ứng dụng độ trễ thấp, nên ưu tiên cơ chế background phù hợp và cấu hình trigger snapshot thay vì gọi `SAVE` theo mỗi request. Không đưa `SAVE` vào một endpoint Spring Boot chỉ để “bảo đảm đã lưu dữ liệu”.

### 3.2. Những gì snapshot không bao gồm

Giả sử:

```text
12:00:00  BGSAVE fork thành công
12:00:02  SET order:1002:status PAID
12:00:08  Child tạo xong RDB snapshot
12:00:10  Redis crash
```

RDB snapshot tạo từ mốc `12:00:00` không mặc nhiên chứa thay đổi `12:00:02`. Nếu không có persistence khác bảo vệ thay đổi này, lệnh vừa trả thành công có thể không có sau restart.

**Thời điểm snapshot hoàn thành không phải thời điểm nội dung dữ liệu được “chụp”.** Snapshot đại diện cho trạng thái tại mốc bắt đầu.

## 4. `fork()` và copy-on-write: nguồn áp lực RAM quan trọng nhất

Khi Redis fork một child để tạo RDB hoặc rewrite AOF, cơ chế copy-on-write của hệ điều hành cho phép parent và child **ban đầu cùng tham chiếu nhiều trang bộ nhớ vật lý**.

```text
Ngay sau fork:

Parent page table ----+
                      +-- physical page P (old value)
Child page table -----+
```

Nếu parent thay đổi dữ liệu thuộc một trang mà child vẫn cần đọc theo snapshot cũ, hệ điều hành có thể tạo một trang mới cho parent:

```text
Sau khi parent ghi:

Child page table ----------> physical page P (old value)
Parent page table ---------> physical page P' (new value)
```

Bộ nhớ vật lý tăng vì cả **bản cũ** và **bản mới** tồn tại đồng thời cho đến khi child không còn cần bản cũ.

### 4.1. COW tính theo trang bộ nhớ, không tính theo vài byte payload

Giả sử OS dùng trang 4 KiB cho một vùng bộ nhớ. Một lệnh `SET` chỉ sửa vài byte trong cấu trúc dữ liệu vẫn có thể khiến **một hoặc nhiều page** được sao chép, vì các metadata/allocator structures liên quan cũng bị sửa.

Ví dụ thuần minh họa:

```text
Child đang giữ page cũ 4096 byte
Parent thay 10 byte ở page đó
COW có thể cần thêm một page 4096 byte
```

Điều đó không có nghĩa mỗi `SET` luôn tạo chính xác 4 KiB COW. Các lần ghi khác có thể dùng lại page đã được copy, nhiều đối tượng Redis có thể nằm trên cùng page, allocator có overhead và cơ chế cấp phát/giải phóng có thể chạm nhiều page.

**Lượng COW phụ thuộc những page thực sự bị sửa trong thời gian child sống**, chứ không tỉ lệ tuyến tính đơn giản với số byte của một Redis value vừa thay đổi.

### 4.2. Mẫu tải ghi làm COW lớn

COW thường đáng lo khi:

- Dataset đang lớn.
- Child mất nhiều thời gian tạo file.
- Parent tiếp tục ghi với tốc độ cao.
- Workload sửa **nhiều vùng bộ nhớ khác nhau**, thay vì vài key nóng cố định.
- Có nhiều cập nhật Hash/Set/List/ZSet, cấp phát hoặc giải phóng object.
- Bộ nhớ bị phân mảnh hoặc cấu trúc allocator làm nhiều page thay đổi.
- Máy/container gần giới hạn RAM.

Một snapshot được tạo nhanh có thể giải phóng child sớm; một snapshot kéo dài dưới tải ghi liên tục khiến nhiều page có cơ hội bị sửa, làm áp lực bộ nhớ tăng.

### 4.3. Không có công thức “BGSAVE luôn cần gấp đôi RAM”

Trong tình huống xấu, lượng memory tăng thêm có thể rất lớn so với dataset khi nhiều page bị sửa, nhưng nói “BGSAVE luôn nhân đôi toàn bộ RAM” là không chính xác.

Ví dụ với dataset nhiều GiB:

| Workload khi child chạy | Xu hướng COW |
|---|---|
| Chủ yếu `GET`, rất ít ghi | Có thể thấp hơn nhiều so với dataset |
| Ghi lặp lên vài key nhỏ | Tăng giới hạn ở những page bị đụng tới và overhead liên quan |
| Cập nhật nhiều key phân tán | Có thể tăng đáng kể |
| Ghi/xóa/cấp phát nhiều object trong lúc disk chậm | Có thể rất cao |
| Child hoàn thành nhanh | Khoảng thời gian phát sinh COW ngắn |
| Child kéo dài do I/O bị nghẽn | Khoảng thời gian tạo COW dài hơn |

Capacity planning nên dùng **đỉnh bộ nhớ đo được ở tải gần production** và chừa biên an toàn, không áp một hệ số duy nhất cho mọi deployment.

## 5. Phân biệt `used_memory`, RSS, COW và giới hạn container

Redis và hệ điều hành báo nhiều loại memory khác nhau:

```text
Redis logical allocations / allocator
    |
    v
used_memory
    |
    +-- allocator fragmentation / retained pages
    +-- process memory not represented by dataset alone
    |
    v
used_memory_rss (RSS của tiến trình Redis)
    |
    +-- trong khi fork:
        memory page có thể được shared hoặc COW
    |
    v
OS / container memory accounting
    |
    +-- Redis parent + child + OS page cache + buffers + runtime khác
```

Cần tránh những kết luận đơn giản như:

```text
used_memory < maxmemory
=> container chắc chắn không bị OOM
```

Kết luận đó **sai** vì `maxmemory` và memory limit của container không đo/kiểm soát hoàn toàn cùng một khái niệm.

### 5.1. Các metric Redis đáng quan sát

```redis
INFO memory
INFO persistence
INFO stats
```

Trong `INFO memory`, các trường thường gặp:

| Trường | Ý nghĩa vận hành |
|---|---|
| `used_memory` | Bộ nhớ Redis allocator ghi nhận |
| `used_memory_human` | Dạng dễ đọc của `used_memory` |
| `used_memory_rss` | RSS của tiến trình Redis theo OS |
| `used_memory_peak` | Đỉnh cấp phát mà Redis ghi nhận |
| `maxmemory` | Giới hạn eviction/ghi theo policy Redis |
| `mem_fragmentation_ratio` | Dấu hiệu chênh lệch giữa một số chỉ số RAM/RSS, cần đọc trong bối cảnh |
| `allocator_allocated` | Bộ nhớ allocator ghi nhận đã cấp cho ứng dụng |
| `allocator_active` | Bộ nhớ allocator đang chiếm các page active |
| `allocator_resident` | Bộ nhớ allocator đang resident, tùy allocator/version |
| `mem_not_counted_for_evict` | Một số phần memory overhead không tính vào kiểm tra eviction |

Tên trường và cách hiển thị có thể thay đổi giữa phiên bản Redis/allocator. Không phải mọi deployment đều có đầy đủ tất cả trường.

### 5.2. RSS không phải tổng memory mà container đang dùng

`used_memory_rss` thường phản ánh RSS của **tiến trình Redis parent**. Trong khi có child fork chạy, hệ điều hành có các page chia sẻ và page COW. Khi nhìn memory của container/cgroup, còn có thể tính các loại memory khác, ví dụ file page cache.

Vì vậy:

- Không cộng RSS parent + RSS child một cách máy móc như thể mọi shared page là bản sao vật lý.
- Không chỉ nhìn RSS parent rồi kết luận cả container không có nguy cơ OOM.
- Theo dõi **cgroup/container working set hoặc memory.current**, event OOM, page cache và các process trong container.
- Nếu Redis chạy cùng các process khác trên máy, cần xem memory pressure toàn host.

Trong Kubernetes, giới hạn memory của pod/container và hành vi OOM killer có thể khiến tiến trình bị dừng ngay cả khi Redis chưa đạt `maxmemory`.

## 6. Minh họa đỉnh memory trong lúc snapshot

Giả sử một hệ thống có:

```text
Redis used_memory ban đầu:      6.0 GiB
Redis parent RSS ban đầu:       7.0 GiB
Container memory limit:         9.0 GiB
```

Snapshot bắt đầu, child chạy trong nhiều giây. Trong lúc đó workload cập nhật lượng dữ liệu lớn, phát sinh thêm COW và I/O page cache. Có thể xuất hiện một đỉnh container memory vượt 9 GiB dù:

```text
Redis used_memory ≈ 6.0 GiB
Redis maxmemory   = 7.0 GiB
```

Kết quả là container có nguy cơ bị OOM-kill.

**Các số chỉ minh họa**, không phải quy tắc cứ dữ liệu 6 GiB thì cần thêm bao nhiêu GiB. Thực tế phải đo đỉnh RSS/cgroup và COW dưới đúng workload.

### 6.1. Công thức tư duy cho capacity planning

Không nên tính một công thức chính xác kiểu `maxmemory + 10% = đủ`. Thay vào đó, xây dựng ngân sách thành các thành phần:

```text
Host/container memory budget
    >= Redis parent resident memory
     + phần memory mới phát sinh do COW
     + OS buffers / file cache theo thực tế
     + client/replication/persistence buffers
     + tiến trình khác và dự phòng vận hành
```

Các thành phần có thể chồng lấp theo cách OS tính toán. Đây là **mô hình kiểm kê**, không phải biểu thức cộng thẳng các metric RSS có thể shared.

Thực hành hiệu quả:

1. Đo memory steady-state ở mức dữ liệu dự kiến.
2. Chạy `BGSAVE` hoặc rewrite trong lúc phát sinh write traffic.
3. Quan sát memory đỉnh của **cgroup/host**, không chỉ `used_memory`.
4. Lặp lại với dữ liệu gần giới hạn dự kiến và disk đang bận.
5. Đặt Redis `maxmemory`/container limit với khoảng dự phòng phù hợp.
6. Xác nhận không có OOM event và latency vẫn đạt SLO.

## 7. Chi phí thời điểm fork và độ trễ Redis

`fork()` cần tạo ngữ cảnh tiến trình con, gồm công việc quản lý address space/page tables theo cơ chế OS. Dataset/address space càng lớn, hoạt động fork càng có thể gây một khoảng dừng đáng kể.

Ngay khi child chưa ghi được nhiều byte ra đĩa, Redis đã có thể trải qua **fork latency**.

Một số metric hữu ích:

```redis
INFO stats
```

Tìm trường như:

```text
latest_fork_usec:...
```

Đây là thời lượng của lần fork gần đây theo đơn vị **microsecond**, khi Redis/version cung cấp metric đó.

Nếu `latest_fork_usec = 120000`, đó là khoảng 120 ms. Con số chỉ nhằm minh họa phép chuyển đơn vị; không phải số đo của một hệ thống cụ thể.

### 7.1. Vì sao fork latency ảnh hưởng API Java?

Giả sử một endpoint đang đọc Redis:

```java
String value = redis.opsForValue().get("cache:product:42");
```

Nếu Redis pause do fork đúng lúc request đến, command có thể phải chờ, làm latency phía ứng dụng tăng. Redis command có thể rất nhỏ nhưng request vẫn chậm vì **độ trễ hệ thống tại thời điểm scheduling/fork**.

Để phân tích nguyên nhân, nên so:

- p95/p99 latency API/WebFlux.
- Redis command latency từ client.
- `latest_fork_usec`.
- Thời điểm `rdb_bgsave_in_progress` hoặc `aof_rewrite_in_progress`.
- CPU saturation và host memory pressure.

Không suy luận từ một mẫu request duy nhất; cần timeline và nhiều lần đo.

### 7.2. Transparent Huge Pages và đặc điểm OS

Trên Linux, Transparent Huge Pages (THP) có thể làm COW và fork behavior khác với các page nhỏ. Redis truyền thống khuyến nghị xem xét/tắt THP cho workload latency thấp vì chi phí COW và memory bất ngờ trong một số môi trường.

Tuy nhiên, cách quản lý THP phụ thuộc kernel, Redis version, allocator, distro và policy hệ thống. Đây là **thay đổi cấu hình host**, cần được kiểm thử và phê duyệt, không phải điều ứng dụng Java tự thay đổi.

Có thể kiểm tra cấu hình host ở môi trường được cấp quyền, nhưng không áp dụng một lệnh sysctl/THP lên production chỉ dựa vào ví dụ chung.

## 8. Chi phí CPU và disk I/O khi tạo RDB

Sau fork, child phải:

1. Duyệt các cấu trúc dữ liệu đang được snapshot.
2. Chuyển chúng thành định dạng RDB.
3. Áp dụng compression nếu cấu hình.
4. Tính/ghi metadata, checksum theo cấu hình và phiên bản.
5. Ghi file tạm và hoàn tất thay thế snapshot.

Với dataset lớn, child tiêu thụ CPU và ghi lượng dữ liệu đáng kể ra disk. **Dù parent vẫn xử lý Redis commands, cả hai tiến trình cạnh tranh CPU, memory bandwidth và disk resources.**

Một ví dụ định tính:

```text
Không có BGSAVE:
  Redis parent CPU  -> xử lý lệnh
  Disk              -> tải nền

Khi BGSAVE:
  Redis parent CPU  -> xử lý lệnh
  Redis child CPU   -> serialize/compress RDB
  Disk              -> ghi snapshot lớn
  Parent memory     -> có thể tăng COW
```

Nếu Redis dùng ổ đĩa chung với database, log hoặc những tác vụ backup khác, I/O contention có thể ảnh hưởng **hệ thống ngoài Redis**.

### 8.1. Compression và dung lượng file

Cấu hình RDB thường có tùy chọn liên quan tới compression/checksum:

```conf
rdbcompression yes
rdbchecksum yes
```

Compression có thể giảm kích thước file nhưng tiêu thụ CPU. Với dữ liệu vốn đã nén hoặc ngẫu nhiên, lợi ích dung lượng có thể nhỏ. Không tắt compression/chế độ kiểm tra dữ liệu chỉ để tăng tốc một benchmark nếu điều đó thay đổi mức độ an toàn hoặc không phản ánh production.

### 8.2. File trên disk và thời điểm hoàn tất

Snapshot thường được ghi qua cơ chế file tạm rồi thay thế theo quy trình Redis. Khi disk chậm, full hoặc không thể ghi, snapshot có thể thất bại.

Cần phân biệt:

- `BGSAVE` được chấp nhận.
- Child đang chạy.
- Child ghi file xong.
- Redis báo `rdb_last_bgsave_status:ok`.

Chỉ nhận phản hồi lệnh `BGSAVE` không chứng minh snapshot đã hoàn thành thành công.

## 9. Cấu hình khi nào Redis tạo RDB snapshot

Redis cho phép thiết lập các điều kiện snapshot dựa trên **khoảng thời gian và số thay đổi**.

Ví dụ file config minh họa:

```conf
save 900 1
save 300 10
save 60 10000
```

Ý tưởng:

- Trong khoảng 900 giây, nếu có ít nhất một thay đổi theo cơ chế đếm của Redis, có thể tạo snapshot.
- Trong khoảng 300 giây, nếu có ít nhất 10 thay đổi, có thể tạo snapshot.
- Trong khoảng 60 giây, nếu có nhiều thay đổi theo điều kiện, có thể snapshot.

Đây là **điều kiện trigger**, không phải bảo đảm “mọi lần ghi được bền vững sau không quá 60 giây”. Snapshot cần thời gian thực thi và có thể thất bại hoặc bị trì hoãn.

### 9.1. Tắt snapshot tự động khi chủ động dùng AOF

Ví dụ:

```conf
save ""
```

thường được dùng để vô hiệu hóa các điều kiện snapshot RDB tự động trong cấu hình phù hợp. Nhưng:

- Điều này không có nghĩa Redis không bao giờ tạo file mang định dạng RDB: một số cơ chế rewrite/replication có thể dùng snapshot/RDB representation tùy version và configuration.
- Không đồng nghĩa tắt mọi background fork.
- Nếu AOF không được bật và không có persistence khác, dữ liệu có thể không khôi phục được sau crash/restart.

Quyết định tắt RDB phải đi cùng chiến lược AOF, backup, replication và kiểm thử restore.

### 9.2. `stop-writes-on-bgsave-error`

Một cấu hình có thể gặp:

```conf
stop-writes-on-bgsave-error yes
```

Khi RDB persistence đã được cấu hình và snapshot thất bại theo các điều kiện Redis áp dụng, server có thể **từ chối các lệnh thay đổi dữ liệu** thay vì tiếp tục nhận ghi mà không đạt mục tiêu persistence.

Điều này bảo vệ người vận hành khỏi việc vô tình chạy lâu trong trạng thái snapshot không hoạt động, nhưng có thể làm ứng dụng thấy lỗi ghi.

Không giải quyết bằng cách tắt tùy chọn này một cách máy móc. Trước tiên cần xác định vì sao snapshot lỗi: disk full, permissions, OOM, fork failure hoặc storage không đáp ứng.

## 10. AOF: lệnh ghi và chính sách `appendfsync`

AOF ghi lại những thao tác có tác dụng thay đổi trạng thái để Redis có thể tái dựng dữ liệu khi khởi động. Chính sách **`appendfsync`** quyết định cách Redis yêu cầu OS đẩy các ghi xuống storage.

Ví dụ:

```conf
appendonly yes
appendfsync everysec
```

Ba chế độ thường gặp:

| Chế độ | Ý nghĩa | Đánh đổi |
|---|---|---|
| `appendfsync always` | Yêu cầu fsync sau các nhóm ghi theo cơ chế Redis | Nỗ lực bền vững cao hơn, chi phí I/O/latency lớn hơn |
| `appendfsync everysec` | Thường yêu cầu fsync khoảng mỗi giây | Cân bằng hiệu năng và nguy cơ mất các ghi gần nhất |
| `appendfsync no` | Để OS quyết định thời điểm flush xuống storage | Throughput có thể cao hơn, thời gian dữ liệu chưa bền vững khó kiểm soát hơn |

Không được hiểu `everysec` là **cam kết tuyệt đối chỉ mất tối đa 1,000 ms**. Disk bị stall, scheduler, OS hoặc sự cố hệ thống có thể khiến thời gian và lượng dữ liệu có nguy cơ bị mất khác kỳ vọng.

### 10.1. Append vào file khác với fsync

Một thao tác ghi file có thể hoàn thành ở mức OS page cache trong khi dữ liệu chưa chắc đã bền vững qua mất điện. `fsync` yêu cầu OS/storage đồng bộ dữ liệu theo giao thức phù hợp, nhưng mức độ bảo đảm còn phụ thuộc filesystem, driver, storage cache và phần cứng.

Mô hình:

```text
Redis command accepted
        |
        v
Redis in-memory dataset updated
        |
        v
AOF data appended / queued for write
        |
        v
OS page cache
        |
        | fsync theo cấu hình
        v
Persistent storage
```

Những bước này **không nhất thiết hoàn tất đồng thời** với phản hồi trả về client.

### 10.2. Chi phí `appendfsync always`

Với workload rất nhiều lệnh ghi nhỏ, yêu cầu fsync thường xuyên có thể:

- Tăng disk I/O operations.
- Tăng write latency hoặc tail latency.
- Làm giảm throughput ghi nếu storage không đủ khả năng.
- Tạo contention với RDB snapshot, AOF rewrite và công việc khác.

Không chọn `always` chỉ vì tên nghe an toàn hơn. Cần chứng minh ứng dụng và storage đáp ứng SLO, đồng thời hiểu nó cũng không thay thế replication, backup hay hệ thống giao dịch bền vững toàn cục.

### 10.3. Chi phí `appendfsync everysec`

`everysec` là lựa chọn cân bằng thường gặp. Nhưng khi disk quá tải:

- Fsync có thể bị trễ.
- Redis có thể ghi cảnh báo liên quan đến AOF fsync.
- Có thể quan sát latency tăng và backlog I/O.
- Crash có thể làm mất các write chưa kịp durable.

Vì vậy, phải theo dõi thực tế `aof_delayed_fsync` và trạng thái AOF, không chỉ tin cấu hình `appendfsync everysec`.

## 11. Vì sao AOF cần rewrite?

Nếu mọi lần cập nhật đều được nối vào AOF, file tăng theo số thao tác, không nhất thiết theo kích thước trạng thái dữ liệu hiện tại.

Ví dụ:

```redis
SET counter 1
SET counter 2
SET counter 3
SET counter 4
...
SET counter 100000
```

Trạng thái cuối của `counter` chỉ là `100000`, nhưng log có thể chứa lịch sử nhiều thao tác. AOF rewrite giúp tạo biểu diễn ngắn gọn hơn để tái lập **trạng thái hiện tại** mà không cần giữ mọi lệnh cập nhật đã bị thay thế.

```text
AOF trước rewrite:
  SET counter 1
  SET counter 2
  ...
  SET counter 100000

AOF mới sau rewrite (ý tưởng):
  SET counter 100000
```

Tùy loại dữ liệu và phiên bản, representation thực tế có thể sử dụng nhiều command hoặc phần dữ liệu nền dạng RDB. Không nên kỳ vọng file AOF rewrite luôn là chuỗi text `SET` đơn giản.

### 11.1. `BGREWRITEAOF` không phải nén file “tại chỗ”

Redis dùng một quá trình background để tạo representation mới từ trạng thái dataset; tiến trình cha vẫn tiếp tục nhận lệnh. Redis phải bảo toàn các thay đổi mới phát sinh trong thời gian rewrite.

Vì vậy rewrite tốn:

- Fork và copy-on-write tương tự RDB background save.
- CPU dựng representation mới.
- Disk I/O ghi file mới.
- Dung lượng đĩa tạm thời cho file cũ và file mới cùng tồn tại.
- Công việc quản lý phần thay đổi trong lúc rewrite.
- Thời gian finalization/đổi active AOF files.

Nó không đơn giản là chạy một chương trình `gzip` trên file AOF cũ.

## 12. AOF rewrite trên Redis 7+: multi-part AOF

Các bản Redis 7 trở về sau sử dụng cơ chế **multi-part AOF** với các thành phần và manifest, thay vì dựa hoàn toàn trên một file AOF đơn lẻ như các phiên bản cũ.

Một mô hình khái niệm:

```text
AOF directory
   |
   +-- base AOF (biểu diễn trạng thái nền)
   +-- incremental AOF (những thay đổi sau mốc nền)
   +-- manifest (mô tả các file đang thuộc tập AOF hợp lệ)
```

Trong lúc rewrite:

```text
Parent tiếp tục xử lý command
    |
    +--> ghi thay đổi mới vào incremental AOF
    |
    +--> Fork child xây base AOF mới
              |
              v
       File base AOF mới
              |
              v
       Cập nhật manifest / chuyển bộ file hợp lệ
              |
              v
       Dọn những file cũ theo cơ chế Redis
```

Tên file thực tế và quy tắc manifest tùy Redis version/cấu hình. Không viết scripts vận hành dựa vào một filename cố định như `appendonly.aof` mà không kiểm tra cấu trúc multi-part AOF thực tế.

### 12.1. Khác biệt với phiên bản cũ

Ở những phiên bản Redis trước cơ chế multi-part AOF, thuật toán rewrite có thể dùng một **rewrite buffer trong bộ nhớ** cho các write phát sinh trong lúc child xây AOF mới. Buffer này có thể tăng theo tải ghi và là nguồn áp lực memory đáng kể.

Với multi-part AOF, nhiều thay đổi được ghi vào incremental AOF theo cơ chế mới, giúp thay đổi cách sử dụng buffer và việc finalization. Tuy nhiên **fork/COW, disk I/O và file growth vẫn tồn tại**. Không suy diễn rằng nâng cấp lên Redis 7 loại bỏ hoàn toàn áp lực memory do rewrite.

Khi đọc tài liệu, metric hay runbook về `aof_rewrite_buffer_length`, phải xác định nó đang mô tả phiên bản Redis nào; không áp dụng trực tiếp mọi nhận định của Redis 6 cho Redis 7+.

### 12.2. `aof-use-rdb-preamble`

Một cấu hình có thể gặp:

```conf
aof-use-rdb-preamble yes
```

Khi được hỗ trợ và bật, phần **base AOF** có thể sử dụng biểu diễn RDB để nạp lại trạng thái hiệu quả hơn, trong khi incremental AOF tiếp tục lưu các thay đổi.

Điều này giải thích vì sao file thuộc AOF **không nhất thiết hoàn toàn là chuỗi lệnh Redis dạng text**. Đừng mở file rồi cố tự xóa “một vài dòng lệnh sai” theo kinh nghiệm với AOF đơn lẻ cũ; việc sửa file persistence cần đúng công cụ, version và backup.

## 13. Trigger tự động và ngưỡng AOF rewrite

Redis có tùy chọn rewrite tự động dựa trên mức tăng kích thước AOF so với lần base/rewrite trước.

Ví dụ:

```conf
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
```

Ý tưởng: khi AOF đã đủ lớn và tăng theo tỷ lệ cấu hình so với baseline, Redis có thể kích hoạt rewrite nền theo điều kiện phù hợp.

Các giá trị trên là **ví dụ thường gặp**, không phải khuyến nghị cố định cho mọi dataset. Hệ thống ghi nhiều nhưng dataset ổn định sẽ có tốc độ tăng AOF khác với hệ thống chủ yếu tạo key mới.

Nếu đặt rewrite quá thường xuyên:

- Fork và COW xảy ra nhiều hơn.
- Disk phải viết file base lặp lại.
- Có thể gây đỉnh latency/memory liên tiếp.

Nếu rewrite quá thưa:

- AOF tăng lớn.
- Cần nhiều disk space.
- Thời gian restart/đọc log tăng theo file và cấu trúc thực tế.
- Một lần rewrite sau đó có thể rất nặng.

### 13.1. Kiểm tra kích thước và trạng thái AOF

```redis
INFO persistence
```

Các trường thường cần nhìn:

```text
aof_enabled
aof_rewrite_in_progress
aof_rewrite_scheduled
aof_last_rewrite_time_sec
aof_last_bgrewrite_status
aof_current_size
aof_base_size
aof_last_cow_size
aof_delayed_fsync
```

Sự có mặt và ý nghĩa chi tiết của từng trường phụ thuộc Redis version. Khi vẽ biểu đồ, ghi version và dùng đúng đơn vị của field.

Ví dụ `aof_current_size` tăng nhanh trong khi `aof_base_size` giữ nguyên có thể cho thấy log lớn dần so với baseline. Nhưng **không kết luận rewrite chắc chắn đang lỗi** nếu chưa kiểm tra trigger, in-progress/scheduled và cấu hình hiện tại.

## 14. COW trong AOF rewrite có thể cạnh tranh với RDB snapshot

Cả `BGSAVE` và `BGREWRITEAOF` đều là background persistence jobs sử dụng tài nguyên đáng kể. Redis có logic điều phối để tránh một số kiểu background fork job chồng lấp không phù hợp, nhưng điều đó **không bảo đảm tải persistence không gây áp lực liên tục**.

Một chuỗi hoạt động có thể là:

```text
t0: BGSAVE bắt đầu
t1: workload ghi lớn -> COW tăng
t2: BGSAVE kết thúc
t3: AOF rewrite bắt đầu hoặc tiếp tục theo lịch
t4: workload ghi lớn -> COW và disk I/O tăng tiếp
t5: rewrite hoàn tất
```

Khi cả RDB và AOF cùng bật, cần quan sát **cửa sổ công việc nền trong cả chu kỳ**, không chỉ một lần snapshot riêng lẻ.

### 14.1. Replication full resync cũng có thể gây công việc nền

Một replica kết nối lại hoặc replica mới tham gia có thể cần full resynchronization. Tùy Redis configuration và version, Redis có thể tạo RDB phục vụ replication, phát sinh thêm chi phí fork/COW/CPU/I/O hoặc cơ chế truyền dữ liệu tương ứng.

Vì vậy, việc thấy một background save không nhất thiết luôn do lịch `save` tự động. Khi đo, ghi lại cả:

```redis
INFO replication
INFO persistence
```

để nhận biết replication sync và background persistence.

### 14.2. Tác động của disk chậm

Nếu child ghi file lâu vì disk throughput thấp:

1. Child tồn tại lâu hơn.
2. Parent tiếp tục sửa nhiều page trong khoảng thời gian đó.
3. COW có thể tăng.
4. File I/O và page cache tiếp tục tạo áp lực.
5. Memory pressure có thể lớn hơn dù tốc độ ghi nghiệp vụ không đổi.

Đây là **mối liên hệ gián tiếp giữa disk throughput và RAM peak**. Đầu tư vào storage thích hợp có thể giúp giảm duration background job, từ đó giảm cửa sổ phát sinh COW.

## 15. `no-appendfsync-on-rewrite`: đổi latency lấy rủi ro durability

Redis có cấu hình:

```conf
no-appendfsync-on-rewrite no
```

Khi bật tùy chọn này ở môi trường/phiên bản hỗ trợ, Redis có thể tránh một số thao tác fsync AOF trong thời gian background RDB/AOF rewrite đang chạy, nhằm giảm tranh chấp I/O.

**Đánh đổi:** dữ liệu mới trong AOF có thể chưa được fsync theo nhịp bình thường, làm **mở rộng cửa sổ có nguy cơ mất write khi máy chủ bị lỗi**. Không bật chỉ để làm benchmark p99 đẹp hơn mà không xét RPO.

Lựa chọn cần dựa trên:

- Storage có đủ IOPS/fsync throughput không.
- Thời gian rewrite thực tế.
- Mức chấp nhận mất dữ liệu của ứng dụng.
- Độ trễ p95/p99.
- Khả năng backup/replication và chiến lược restore.

Thay một tham số persistence có thể làm thay đổi bảo đảm dữ liệu, không chỉ hiệu năng.

## 16. Các cấu hình Redis persistence điển hình

Đoạn cấu hình dưới đây là **mẫu so sánh**, không phải file production hoàn chỉnh. Cần thêm network ACL/TLS, log, file directory, persistence permission, replication, memory policy và backup.

### 16.1. RDB chủ đạo

```conf
appendonly no

save 900 1
save 300 10
save 60 10000

rdbcompression yes
rdbchecksum yes
stop-writes-on-bgsave-error yes
```

Ưu điểm:

- Snapshot thường gọn và thuận tiện cho backup.
- Có thể khởi động nhanh với snapshot thích hợp.
- Không có chi phí append/fsync AOF liên tục.

Đánh đổi:

- Có thể mất thay đổi kể từ lần snapshot gần nhất khi crash.
- `BGSAVE` vẫn dùng fork/COW và disk I/O.
- Nếu snapshot lỗi, các write có thể bị từ chối theo policy.
- Không phù hợp nếu ứng dụng cần RPO rất nhỏ mà không có cơ chế bổ sung.

### 16.2. AOF chủ đạo

```conf
appendonly yes
appendfsync everysec

save ""

auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
aof-use-rdb-preamble yes
```

Ưu điểm:

- Theo mô hình append log, có thể có RPO nhỏ hơn cấu hình RDB-only thông thường.
- Dữ liệu được tái tạo từ bộ AOF còn hợp lệ.
- Rewrite giúp hạn chế tăng file vô hạn so với việc giữ toàn bộ lịch sử cập nhật.

Đánh đổi:

- Có chi phí append/fsync.
- Rewrite vẫn fork/COW và tốn disk.
- Phải quản lý các thành phần AOF/manifest đúng phiên bản.
- `everysec` không cam kết mất tối đa đúng một giây trong mọi sự cố.

### 16.3. Kết hợp RDB và AOF

```conf
appendonly yes
appendfsync everysec

save 900 1
save 300 10
save 60 10000
```

Phương án này có cả các snapshot và cơ chế AOF. Cần đo:

- Mức tranh chấp disk.
- Tần suất hai loại background job.
- Fork/COW peak theo chu kỳ.
- Khả năng phục hồi từ file persistence thực tế.
- Backup/restore process.

Khi cả hai cùng tồn tại, hành vi Redis chọn nguồn khôi phục khi startup phụ thuộc cấu hình và version; thường AOF được ưu tiên khi bật, vì có thể chứa nhiều thay đổi gần đây hơn RDB. Cần kiểm thử chứ không chỉ dựa vào tên file.

### 16.4. Chỉ dùng cache có thể tái tạo

Một Redis chỉ giữ cache có thể tái tạo toàn bộ từ database có thể chủ động không dùng persistence trong một số kiến trúc:

```conf
appendonly no
save ""
```

Nhưng **đây không phải lựa chọn mặc định** cho session bắt buộc giữ, queue, token quan trọng hoặc trạng thái nghiệp vụ không có nguồn khác.

Cần tính:

- Sau restart, cache cold có thể gây cache stampede và tăng tải DB.
- Redis failover có thể khiến dữ liệu cache thay đổi.
- Dữ liệu lưu trong Redis có thật sự hoàn toàn tái tạo được không?
- TTL, invalidation và bộ nhớ eviction có phù hợp không?

Không tắt durability chỉ vì Redis được gọi là “cache” nếu thực tế hệ thống đang dựa vào nó như nguồn dữ liệu.

## 17. Quan hệ giữa `maxmemory`, eviction và persistence

Redis có thể cấu hình:

```conf
maxmemory 6gb
maxmemory-policy allkeys-lru
```

`maxmemory` hỗ trợ giới hạn memory theo logic Redis áp dụng, với chính sách eviction cho key khi cần. Nhưng persistence còn liên quan tới:

- COW pages của tiến trình child/parent.
- Client output buffers.
- Replication buffers.
- AOF overhead và page cache.
- Memory fragmentation.
- Container/cgroup accounting.

Do đó:

```text
maxmemory = 6 GiB
container memory limit = 6 GiB
```

**không phải cấu hình an toàn** chỉ vì hai con số bằng nhau. Redis có thể cần RAM vượt giá trị `maxmemory` để thực hiện persistence và các công việc khác.

### 17.1. `noeviction` và dữ liệu nghiệp vụ

Nếu policy là:

```conf
maxmemory-policy noeviction
```

Redis có thể từ chối những lệnh cần tăng bộ nhớ khi vượt ngưỡng, thay vì loại key theo policy. Với dữ liệu nghiệp vụ, đây có thể là lựa chọn bảo vệ dữ liệu khỏi eviction không mong muốn nhưng chuyển rủi ro thành **lỗi ghi**.

Cần chọn `maxmemory-policy` theo semantics của dữ liệu:

- Cache có thể tái tạo: có thể chấp nhận eviction.
- Stream/queue hoặc dữ liệu nghiệp vụ: không được xóa tùy tiện chỉ vì thiếu bộ nhớ.
- Mixed workload: đặt chung cache và trạng thái quan trọng làm policy phức tạp; cân nhắc tách instance.

### 17.2. Eviction không giải quyết mọi đỉnh COW

Ngay cả khi Redis evict key để duy trì `used_memory` dưới `maxmemory`, việc xóa/cập nhật cấu trúc có thể sửa page và **làm phát sinh thêm COW** trong khi child đang giữ snapshot cũ.

Do đó, eviction lúc memory pressure không bảo đảm OS RSS sẽ giảm ngay. Nếu allocator giữ page hoặc child còn tham chiếu bản cũ, container vẫn có nguy cơ OOM.

Đây là một trong những lý do phải đo memory của host/container thay vì chỉ tin Redis đã “tuân thủ maxmemory”.

## 18. Tác động lên Spring Data Redis: latency và timeout

Ứng dụng Spring Boot thường dùng:

```java
StringRedisTemplate redis;
```

với cấu hình:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

Khi Redis background persistence tạo áp lực CPU/disk/fork, các thao tác Java có thể thấy latency tăng hoặc ngoại lệ như:

```text
RedisConnectionFailureException
RedisCommandTimeoutException
RedisSystemException
```

Các loại exception được Spring Data Redis dịch từ Redis driver theo phiên bản và nguyên nhân; không nên kết luận mọi timeout đều do BGSAVE/AOF rewrite.

### 18.1. Vì sao command timeout không thay đổi durability?

Giả sử:

```java
redis.opsForValue().increment("metrics:orders");
```

Redis có thể đã thực thi `INCR`, nhưng phản hồi chưa tới client trước deadline do mạng hoặc hệ thống chậm. Nếu Spring Data Redis ném timeout:

- Ứng dụng **không thể mặc định rằng `INCR` chưa chạy**.
- Retry không idempotent có thể làm tăng lần nữa.
- Persistence vẫn theo chính sách Redis, không theo thời gian chờ của Java.
- Chuyển sang `ReactiveRedisTemplate` không biến lệnh thành durable transaction.

Phải phân biệt **request outcome phía client**, **Redis đã cập nhật in-memory**, **AOF/RDB đã bền vững** và **replica đã nhận dữ liệu**.

### 18.2. Không gọi `BGSAVE` hoặc rewrite theo request HTTP

Một anti-pattern:

```java
@PostMapping("/orders")
public ResponseEntity<?> saveOrder(...) {
    storeOrder(...);
    redis.execute(connection -> {
        // gọi BGSAVE sau mỗi request?
        return null;
    });
    return ResponseEntity.ok().build();
}
```

Gọi persistence command theo từng request không phải cách tạo commit bền vững từng thao tác. Nó có thể gây job nền liên tục, contention và lỗi điều phối.

RDB/AOF được cấu hình ở tầng Redis server. Ứng dụng nghiệp vụ cần dùng command đúng nghĩa và chọn durability strategy toàn hệ thống, không biến endpoint thành công cụ điều hành snapshot.

## 19. Đo latency thực tế từ Spring Data Redis

Có thể dùng Micrometer để đo **thời gian thao tác nhìn từ ứng dụng**. Ví dụ service minh họa:

```java
package com.example.orders;

import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusCache {

    private final StringRedisTemplate redis;
    private final Timer writeTimer;
    private final Timer readTimer;

    public OrderStatusCache(
            StringRedisTemplate redis,
            MeterRegistry meterRegistry
    ) {
        this.redis = redis;

        this.writeTimer = Timer.builder("redis.order_status.write")
                .description("Redis SET duration from application")
                .register(meterRegistry);

        this.readTimer = Timer.builder("redis.order_status.read")
                .description("Redis GET duration from application")
                .register(meterRegistry);
    }

    public void put(String orderId, String status) {
        String key = "cache:order:status:" + orderId;

        writeTimer.record(() ->
            redis.opsForValue().set(
                key,
                status,
                Duration.ofMinutes(5)
            )
        );
    }

    public String get(String orderId) {
        String key = "cache:order:status:" + orderId;

        return readTimer.record(
            () -> redis.opsForValue().get(key)
        );
    }
}
```

Ví dụ sử dụng API Micrometer và Spring Data Redis phổ biến; ứng dụng thật cần có dependency Micrometer/Actuator và hệ thống metric registry phù hợp.

`Timer` ở đây đo **thời gian end-to-end** từ ứng dụng, gồm:

```text
Client / connection management
+ serialization
+ network
+ Redis server wait + execution
+ response
+ deserialization
```

Không phải chỉ CPU time của lệnh Redis.

### 19.1. Đo p95/p99 thay vì chỉ trung bình

Trong lúc `BGSAVE` hoặc rewrite, phần lớn lệnh có thể vẫn nhanh nhưng một nhóm request trúng thời điểm fork/fsync contention bị chậm đáng kể.

Nên đo:

- p50/p95/p99 latency theo thao tác GET/SET.
- Throughput và số error/timeout.
- Redis `latest_fork_usec`.
- COW peak và thời gian background job.
- Disk IOPS, fsync latency, utilization/queue.
- CPU host/container.
- Memory peak của cgroup và OOM events.

Một vài điểm benchmark không đủ để khẳng định SLO được đáp ứng dưới tải thật.

### 19.2. Tránh high-cardinality metric

Không gắn mọi `orderId`/Redis key làm tag metric, vì mỗi key có thể sinh một time series mới.

Phù hợp:

```text
operation = get|set
result = success|timeout|error
workload = cache|counter|stream
```

Không phù hợp:

```text
key = cache:order:status:100000001
key = cache:order:status:100000002
...
```

Khi cần điều tra một request, dùng correlation ID trong log có kiểm soát, không dùng làm label metric.

## 20. Dùng `INFO persistence` theo dõi background save/rewrite

Lệnh đầu tiên nên xem:

```redis
INFO persistence
```

Một số trường có ý nghĩa:

| Trường | Cách hiểu |
|---|---|
| `rdb_bgsave_in_progress` | Có BGSAVE đang chạy hay không |
| `rdb_last_save_time` | Mốc thời gian snapshot thành công theo cách Redis ghi nhận |
| `rdb_last_bgsave_status` | Kết quả background save gần nhất |
| `rdb_last_bgsave_time_sec` | Thời gian job BGSAVE gần nhất |
| `rdb_current_bgsave_time_sec` | Thời gian BGSAVE hiện tại khi đang chạy |
| `rdb_changes_since_last_save` | Số thay đổi được Redis đếm kể từ mốc save |
| `rdb_last_cow_size` | Thống kê COW liên quan đến lần RDB background job gần đây, thường tính byte |
| `aof_enabled` | AOF đang bật hay không |
| `aof_rewrite_in_progress` | Rewrite AOF đang chạy hay không |
| `aof_rewrite_scheduled` | Rewrite đã được lên lịch/đợi theo cơ chế Redis |
| `aof_last_bgrewrite_status` | Trạng thái rewrite AOF gần nhất |
| `aof_last_rewrite_time_sec` | Thời gian rewrite gần nhất |
| `aof_current_size` | Kích thước AOF theo cách Redis thống kê |
| `aof_base_size` | Kích thước baseline/base để xem mức tăng |
| `aof_last_cow_size` | Thống kê COW liên quan đến AOF rewrite |
| `aof_delayed_fsync` | Bộ đếm các tình huống fsync AOF bị trễ theo semantics Redis |

Các field chính xác có thể khác với phiên bản Redis; nếu metric không xuất hiện, cần kiểm tra version/config, không tự gán giá trị `0`.

### 20.1. Không kết luận từ một lần đọc

Ví dụ một lệnh:

```redis
INFO persistence
```

trả:

```text
rdb_bgsave_in_progress:0
rdb_last_bgsave_status:ok
```

chỉ cho biết **tại thời điểm quan sát** không có BGSAVE chạy và lần trước có kết quả OK. Nó không cho biết memory peak của job trước, latency p99 khi job chạy, hay AOF có an toàn không.

Để đánh giá persistence overhead, cần thu theo thời gian với chu kỳ phù hợp và kết hợp OS metrics.

### 20.2. `rdb_last_cow_size` và `aof_last_cow_size`

Các số liệu COW có thể là dấu hiệu quan trọng để nhận biết write workload đã làm bao nhiêu page bị copy trong một job.

Tuy nhiên:

- Đây là metric của **một job**, không phải tổng bộ nhớ hiện đang dùng tại mọi thời điểm.
- Không cộng trực tiếp với `used_memory_rss` để suy ra cgroup usage.
- Không tự dùng để dự đoán max memory chính xác nếu workload khác đi.
- Cần so cùng version Redis, allocator, OS và tải khi đánh giá xu hướng.

## 21. Quan sát fork latency và Redis latency events

Thêm:

```redis
INFO stats
LATENCY LATEST
LATENCY DOCTOR
SLOWLOG GET 20
```

Redis latency monitor có thể yêu cầu cấu hình ngưỡng thích hợp trước khi ghi nhận events:

```redis
CONFIG GET latency-monitor-threshold
```

Trong **lab** có quyền cấu hình, có thể dùng ngưỡng minh họa:

```redis
CONFIG SET latency-monitor-threshold 10
```

Đơn vị của `latency-monitor-threshold` là **mili giây**. Không tự thay đổi setting production để chạy benchmark nếu chưa xét tải ghi metric và quy trình vận hành.

### 21.1. `SLOWLOG` và fork latency không hoàn toàn giống nhau

`SLOWLOG` thường đo thời gian thực thi command tại Redis server, không bao gồm mạng. Fork latency hoặc việc một command phải chờ vì server đang bận có thể phản ánh khác với số đo `SLOWLOG` của từng command.

Do đó:

```text
Application p99 tăng
SLOWLOG không xuất hiện GET chậm
```

không đủ để kết luận Redis không phải nguồn latency. Hãy nhìn fork latency, disk, CPU, network và client connection pool.

### 21.2. Hệ điều hành và container metrics

Bên cạnh Redis INFO, nên thu:

- `memory.current`/cgroup memory metrics và OOM event.
- RSS của Redis parent và child, có tính đến shared memory.
- Disk write throughput, latency và queue depth.
- Free disk space/inode.
- CPU user/system và mức CPU throttling trong container.
- Page faults, swap in/out nếu hệ thống sử dụng swap.
- Storage fsync latency.
- Container restart reason và OOMKilled status.

Việc tập trung riêng vào Redis CLI mà bỏ qua cgroup rất dễ bỏ sót failure do fork/COW gây ra.

## 22. Kịch bản benchmark RDB snapshot

Một bài thử có ý nghĩa phải dùng **dữ liệu và write workload gần thực tế**, không chỉ chạy `BGSAVE` khi Redis rảnh.

Quy trình đề xuất trên lab:

### Bước 1 — Chuẩn bị dataset

Nạp một tập key đủ lớn để mô phỏng production:

```text
small strings:      nhiều key nhỏ
hash entities:      Hash có số field tương tự thực tế
lists/zsets:        các collection với độ lớn sát kỳ vọng
TTL distribution:   các thời hạn khác nhau
```

Không tạo dữ liệu bằng cách dùng cùng một key liên tục nếu production có hàng triệu key thay đổi phân tán; điều đó làm COW pattern khác hẳn.

### Bước 2 — Đo baseline

Chạy workload đọc/ghi ổn định trong một cửa sổ đo:

```text
GET/SET/INCR
Tốc độ ghi mục tiêu
Số client đồng thời
p50/p95/p99 latency
RSS/cgroup memory
CPU và disk throughput
```

Ghi nhận cả thời gian ổn định và memory sử dụng ban đầu.

### Bước 3 — Bắt đầu BGSAVE

Trên **môi trường thử nghiệm được cấp quyền**:

```redis
BGSAVE
```

Không dừng workload. Thu:

```redis
INFO persistence
INFO stats
INFO memory
```

đồng thời đọc hệ thống monitoring.

### Bước 4 — Đo trong lúc child chạy

Quan sát:

- Độ trễ thời điểm fork.
- Thời gian BGSAVE kéo dài.
- Mức tăng cgroup memory và RSS.
- COW bytes.
- Disk write throughput/latency.
- p95/p99 GET/SET.
- Timeout, error, OOM events.

### Bước 5 — Đo sau khi child kết thúc

Xác nhận `rdb_last_bgsave_status:ok` rồi tiếp tục quan sát vài chu kỳ latency/memory. Đỉnh memory có thể hạ xuống sau khi child thoát nhưng RSS của allocator không nhất thiết lập tức quay về giá trị trước.

### Bước 6 — Lặp lại với tải khác

Tối thiểu so sánh:

- Chủ yếu đọc.
- Tốc độ ghi thấp.
- Tốc độ ghi trung bình.
- Ghi cao và chạm nhiều key.
- Disk đang bị workload khác cạnh tranh.

Kết quả cần thể hiện **đường cong RAM peak và latency theo workload**, không chỉ một con số “BGSAVE mất 5 giây”.

## 23. Kịch bản benchmark AOF và rewrite

Nên tách **chi phí AOF append bình thường** khỏi **chi phí BGREWRITEAOF**.

### 23.1. So sánh chính sách fsync

Trong các run độc lập với dataset và tải tương đương, thử:

```conf
appendfsync no
```

```conf
appendfsync everysec
```

```conf
appendfsync always
```

Ghi:

- Throughput ghi.
- p95/p99 latency.
- Disk IOPS/write throughput/fsync.
- Số lần fsync delay và error.
- Storage utilization.
- Khả năng phục hồi dữ liệu sau crash test có kiểm soát.

Không thay đổi `appendfsync` của Redis đang lưu dữ liệu production để chạy một benchmark tùy hứng. Một số môi trường managed Redis còn không cho phép thay setting.

### 23.2. Thử BGREWRITEAOF

Ở Redis lab có AOF đang bật:

```redis
BGREWRITEAOF
```

Sau đó theo dõi:

```redis
INFO persistence
```

và metric OS. Kết quả cần ghi:

- Trạng thái rewrite bắt đầu/kết thúc.
- Thời gian rewrite.
- COW bytes.
- Kích thước AOF trước và sau rewrite.
- Disk space peak trong lúc file cũ và file mới cùng tồn tại.
- Latency và timeout của command đang chạy.
- Cgroup memory peak và OOM.
- `aof_delayed_fsync` có tăng không.

Một rewrite hoàn tất thành công nhưng làm API p99 vượt SLA vẫn cần được xem là rủi ro vận hành.

### 23.3. Vì sao phải thử rewrite khi AOF đã lớn?

Nếu AOF chỉ vài MB, rewrite có thể kết thúc quá nhanh để bộc lộ chi phí fork/COW, disk và file management. Production có thể có AOF lớn nhiều GiB và workload ghi cao.

Không nên tạo dataset giả quá nhỏ rồi suy luận rewrite sẽ luôn vô hại. Cần có scale tương xứng với dữ liệu và storage thật.

## 24. Minh họa kết quả và cách đọc đúng

Giả sử một phép thử trong staging cho ra bảng:

| Trạng thái | p99 SET (ms) | Container memory peak | Disk write | Nhận xét |
|---|---:|---:|---:|---|
| Baseline không có job nền | 4 | 7.2 GiB | 20 MB/s | Ổn định |
| BGSAVE dưới tải đọc | 8 | 7.4 GiB | 160 MB/s | COW tương đối thấp |
| BGSAVE dưới tải ghi lớn | 55 | 8.8 GiB | 180 MB/s | COW tăng |
| BGREWRITEAOF dưới tải ghi lớn | 80 | 9.0 GiB | 210 MB/s | Disk/fsync contention |
| Rewrite với disk nghẽn | 200 | 9.5 GiB | 90 MB/s | Job kéo dài và RAM cao |

**Toàn bộ số liệu chỉ minh họa cách trình bày**, không phải benchmark đã thực hiện hay ngưỡng tiêu chuẩn của Redis.

Một số cách diễn giải:

1. Baseline tốt không có nghĩa persistence job sẽ tốt.
2. BGSAVE cùng kích thước dataset nhưng write load khác nhau có COW khác nhau.
3. Disk chậm có thể làm rewrite kéo dài, từ đó tăng cửa sổ COW.
4. Container memory peak sát limit là rủi ro, dù `used_memory` vẫn dưới `maxmemory`.
5. p99 xấu cần xem cùng SLA API và tải cụ thể; không chỉ so một lần đọc INFO.

Không dùng một bảng ước lượng để chọn `maxmemory` production; phải thay bằng số đo thật trong môi trường có đặc điểm gần thực tế.

## 25. Kiểm tra dữ liệu bền vững: không chỉ đọc lại trong cùng tiến trình

Một phép `SET` rồi `GET`:

```redis
SET durability:test 1
GET durability:test
```

cho thấy Redis in-memory state đang chứa giá trị. Nó **không chứng minh RDB/AOF đã ghi bền vững**.

Để kiểm thử durability, cần:

1. Tạo các write có ID riêng.
2. Ghi nhận những write được ứng dụng xác nhận thành công **ở nơi độc lập với Redis**.
3. Gây sự cố theo kịch bản được phê duyệt trên lab/staging.
4. Khởi động/khôi phục Redis từ persistence artifacts.
5. Đọc lại những ID đã được xác nhận.
6. Đếm missing/mismatch và các thao tác có outcome không chắc chắn.

### 25.1. Mô hình write log ngoài Redis

```text
Test harness
    |
    +-- write key=durability:run-1:seq:101
    |        |
    |        +-- Redis trả OK
    |        |
    |        +-- ghi seq=101 vào durable ACK log bên ngoài
    |
    +-- write key=durability:run-1:seq:102
             |
             +-- Redis trả timeout
             |
             +-- ghi trạng thái UNKNOWN, không coi là ACK thành công
```

Sau restart:

```text
Redis hiện tại
    |
    +-- đối chiếu toàn bộ seq thuộc ACK log
    |
    +-- ghi số missing và mismatch
```

Những write có timeout phải được phân loại **UNKNOWN** vì Redis có thể đã xử lý nhưng client không nhận được response.

### 25.2. Phân biệt process crash, OS crash và power loss

Ba cách gây sự cố có thể mang độ rủi ro dữ liệu khác nhau:

| Kịch bản | Ý nghĩa |
|---|---|
| Restart có kiểm soát | Redis có thể hoàn tất tác vụ lưu/flush trước khi dừng |
| Kill tiến trình | Process mất đột ngột nhưng OS vẫn sống và page cache có thể còn |
| Mất điện/OS crash | Rủi ro dữ liệu chưa durable xuống storage rõ hơn |

Không suy luận “không mất dữ liệu khi kill process” đồng nghĩa dữ liệu sẽ không mất khi mất điện. Cần hiểu ranh giới OS cache, filesystem và storage.

Chỉ thực hiện crash/power tests ở môi trường cô lập được cấp phép; không làm hỏng storage production để thử RPO.

## 26. Đo thời gian khôi phục (RTO) và mất dữ liệu (RPO)

Hai chỉ tiêu thường được xác định:

- **RTO (Recovery Time Objective):** thời gian mục tiêu để hệ thống phục hồi hoạt động sau sự cố.
- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa chấp nhận được theo thời gian hoặc khối lượng công việc.

Với Redis persistence, một lần benchmark phải xác định rõ:

```text
t0: bắt đầu sự cố / tiến trình mất
t1: Redis tiến trình được khởi động lại
t2: Redis hoàn tất nạp persistence
t3: Spring Data Redis gửi GET/SET thành công ổn định
```

Có thể đo:

```text
Observed server load duration = t2 - t1
Observed app recovery duration = t3 - t0
```

RDB/AOF file lớn có thể khiến Redis cần nhiều thời gian nạp lại, nên **dung lượng persistence không chỉ ảnh hưởng disk trong lúc chạy mà còn ảnh hưởng RTO**.

### 26.1. RPO phải đối chiếu với dữ liệu thực

Không thể chỉ nhìn:

```conf
appendfsync everysec
```

rồi ghi “RPO = 1 giây” trong báo cáo. Cần đo số write đã được xác nhận nhưng mất sau loại sự cố cụ thể, với storage/config tương ứng.

Ngay cả khi AOF tồn tại, Redis failover qua replica còn chịu rủi ro **replication bất đồng bộ**, là một đường mất dữ liệu khác với crash local filesystem.

## 27. Khi Redis hết đĩa hoặc snapshot/AOF lỗi

Persistence tạo nhu cầu disk space liên tục và theo đỉnh:

```text
Disk sử dụng trước rewrite:
  Active AOF files
  RDB snapshot
  Backup khác

Trong rewrite:
  Active AOF cũ
  Base AOF mới đang xây
  Incremental AOF
  Temporary files / metadata
```

Nếu không còn đủ disk space hoặc inode:

- `BGSAVE` có thể thất bại.
- `BGREWRITEAOF` có thể thất bại và phải giữ bộ AOF hợp lệ trước đó.
- AOF append/fsync có thể gặp I/O error.
- Redis có thể từ chối write hoặc log lỗi theo policy và phiên bản.
- Latency có thể tăng trước khi failure lộ rõ.

Cần theo dõi **free bytes, free inodes và disk latency**. Không chỉ giám sát tổng dung lượng file AOF.

### 27.1. Vì sao không xóa file AOF đang dùng bằng tay?

Khi Redis 7+ sử dụng multi-part AOF, active files và manifest có quan hệ với nhau. Xóa một file vì nhìn thấy nó “to” có thể làm bộ persistence không thể khôi phục.

Quy trình an toàn:

1. Xác định Redis version và đường dẫn cấu hình persistence.
2. Kiểm tra trạng thái Redis hiện tại.
3. Tạo backup/copy thích hợp.
4. Dùng cơ chế rewrite/retention được Redis hỗ trợ.
5. Với file hỏng, chỉ dùng công cụ sửa/kiểm tra theo quy trình recovery trên **bản sao** trước khi thay file thật.

Không sửa manifest hoặc cắt AOF bằng text editor trong hệ thống đang chạy.

## 28. Phục hồi khi file persistence hỏng

Redis có các công cụ kiểm tra file phù hợp, ví dụ:

```bash
redis-check-rdb /path/to/dump.rdb
```

và các chức năng kiểm tra AOF tương ứng theo Redis version, chẳng hạn:

```bash
redis-check-aof --check /path/to/appendonly.aof
```

Đường dẫn và cú pháp chính xác phải được điều chỉnh theo **cấu trúc file thực tế**: Redis 7+ có thể dùng manifest và nhiều AOF components thay vì một file đơn.

Những nguyên tắc cần tuân thủ:

- Không chạy chế độ sửa trên file persistence production đang được Redis sử dụng.
- Luôn tạo bản sao trước khi cố sửa dữ liệu.
- Kiểm tra Redis version tương thích với định dạng file.
- Xác nhận backup có thể restore thực sự, không chỉ tồn tại trên disk.
- Sau restore, đối chiếu dữ liệu quan trọng và kiểm tra ứng dụng.
- Ghi lại khoảng mất dữ liệu quan sát được, không lặng lẽ tuyên bố khôi phục hoàn toàn.

Các tùy chọn như xử lý AOF bị truncate khi load phụ thuộc version/config và có thể làm mất phần cuối log. Không nên bật “tự sửa” mà không biết phần dữ liệu sẽ bị loại.

## 29. Replication, Sentinel và Cluster không thay thế persistence

Một Redis primary có replica:

```text
Primary (P) ---> Replica (R)
```

giúp một phần dữ liệu có thể tồn tại trên node khác và hỗ trợ failover. Nhưng replication thường bất đồng bộ:

```text
Client SET -> P trả OK
                   |
                   | dữ liệu chưa tới R
                   v
              P chết
                   |
                   v
              R được promote
```

Một số write đã được client xác nhận có thể không còn trên primary mới.

Persistence là một phần của khả năng khôi phục trên từng node; replication/failover là một phần khác. Không có sự thay thế tuyệt đối:

| Cơ chế | Giúp gì? | Không tự bảo đảm |
|---|---|---|
| RDB | Snapshot trên storage | Ghi ngay sau snapshot đã bền vững |
| AOF | Log thay đổi theo chính sách fsync | Không mất write trong mọi crash |
| Replica | Dữ liệu trên node khác | Mọi write đã ACK đều replicate |
| Sentinel | Tự động tìm/thăng primary thay thế | Zero-data-loss failover |
| Redis Cluster | Phân mảnh dữ liệu và HA theo slot/node | Transaction/commit toàn Cluster |
| Backup ngoài Redis | Khôi phục khi dữ liệu/file bị lỗi | RPO bằng 0 nếu backup không liên tục |

Nếu Redis Cluster có nhiều primary, **mỗi primary chứa một phần dữ liệu khác nhau**; phải đánh giá persistence và disk/memory headroom **theo từng node**, không chỉ một tổng memory toàn cluster.

### 29.1. Snapshot có thể làm lệch replication lag

Một job RDB/AOF rewrite dùng CPU/disk mạnh có thể cạnh tranh với replication traffic, khiến replica lag tăng ở một số điều kiện. Nếu primary chết đúng lúc replica còn lag, RPO qua failover có thể xấu hơn.

Vì vậy khi benchmark persistence ở cụm có replication, thu cả:

```redis
INFO replication
```

và số liệu replication offsets/lag, thay vì chỉ tập trung vào `rdb_last_cow_size`.

## 30. Những sai lầm phổ biến

**“`BGSAVE` chạy background nên không ảnh hưởng request.”** Sai. Fork, COW, CPU và disk I/O đều có thể tăng latency.

**“Redis fork là copy toàn bộ 6 GiB RAM ngay tức thì.”** Sai. COW cho phép chia sẻ nhiều page ban đầu, nhưng page bị sửa trong khi child sống có thể bị sao chép.

**“Một lần `SET` sửa 100 byte chỉ cần thêm 100 byte COW.”** Sai. COW thường làm việc theo page và cấu trúc allocator, không theo byte payload logic.

**“`used_memory < maxmemory` nghĩa là không thể OOM.”** Sai. RSS, COW, buffers, page cache và giới hạn cgroup có thể cao hơn.

**“Redis `maxmemory` bằng memory limit container là hợp lý.”** Rủi ro cao nếu không có headroom cho fork, fragmentation và các công việc nền.

**“`appendfsync everysec` cam kết mất tối đa đúng 1 giây.”** Không có bảo đảm tuyệt đối như vậy trong mọi tình huống storage/OS/crash.

**“`appendfsync always` biến Redis thành transaction database zero-loss.”** Không. Còn các giới hạn hardware, network, replication và business workflow.

**“AOF rewrite chỉ nén file log đang có.”** Sai. Redis tạo representation mới của trạng thái và quản lý những thay đổi trong thời gian rewrite.

**“Redis 7 dùng multi-part AOF nên không còn COW.”** Sai. Fork/COW vẫn là chi phí đáng quan tâm.

**“RDB snapshot hoàn tất lúc 12:10 thì chứa mọi write trước 12:10.”** Không đúng nếu snapshot được chụp từ mốc fork sớm hơn.

**“Bật `no-appendfsync-on-rewrite` là tối ưu miễn phí.”** Sai. Nó có thể mở rộng rủi ro mất ghi trong thời gian background rewrite.

**“Redis replica đủ để không cần backup.”** Sai. Replica có thể sao chép cả thao tác xóa nhầm hoặc dữ liệu lỗi, và replication có thể lag.

**“Một lệnh GET sau SET chứng minh dữ liệu đã trên disk.”** Không. Nó thường chỉ xác nhận trạng thái in-memory.

**“AOF current size lớn là đủ kết luận rewrite thất bại.”** Không. Cần kiểm tra ngưỡng trigger, trạng thái job, baseline và Redis version.

**“Chỉ xem RSS tiến trình cha là đủ đo RAM trong lúc fork.”** Không. Phải xem shared/COW/cgroup accounting.

**“Tăng timeout Java giải quyết fork OOM.”** Không. Timeout chỉ thay đổi hành vi chờ của client; không cấp thêm memory cho Redis.

**“Có thể retry `INCR` vô hạn khi timeout lúc rewrite.”** Sai. Lệnh đầu có thể đã thực thi; retry có thể tăng lần hai.

**“Redis chỉ là cache nên tắt persistence không có ảnh hưởng gì.”** Không chắc. Cache cold có thể gây quá tải nguồn, và một số ứng dụng dùng Redis làm nơi giữ state quan trọng.

## 31. Bảng chọn chiến lược theo yêu cầu nghiệp vụ

| Workload | Hướng cân nhắc | Điều cần kiểm chứng |
|---|---|---|
| Cache có thể tái tạo | Có thể giảm/tắt persistence tùy kiến trúc | Cold start, database surge, eviction |
| Session có yêu cầu khôi phục | RDB/AOF phù hợp hoặc lưu ở nguồn bền vững khác | RPO, restart, security |
| Bộ đếm thống kê không tuyệt đối | AOF everysec hoặc cơ chế batch ngoài Redis | Mức mất dữ liệu được chấp nhận |
| Stream sự kiện phải replay | Persistence/replication và idempotency đủ mạnh | RPO, pending/ACK, trimming |
| Dữ liệu đơn hàng/thanh toán là nguồn sự thật | Cân nhắc DB có transaction/durability phù hợp | Exactly-once side effect và recovery |
| Dataset rất lớn, tốc độ ghi cao | Đặc biệt đo COW, fork latency và disk throughput | Memory peak và p99 dưới BGSAVE/rewrite |
| Container memory limit chặt | Dự phòng COW/page cache, tránh overcommit RAM | Cgroup memory và OOM event |
| Multi-node Sentinel/Cluster | Test từng node và failover | Replication loss, RTO/RPO |
| Disk chậm hoặc chia sẻ | Lập lịch và quản lý I/O | Rewrite duration, fsync delays |
| Managed Redis | Theo chính sách của nhà cung cấp | Cấu hình được phép, backup và metric được hỗ trợ |

Không phải workload nào cũng cần bật cả RDB và AOF. Quyết định phải dựa trên **ý nghĩa dữ liệu**, yêu cầu mất dữ liệu được phép và chi phí vận hành đo được.

## 32. Quy trình kiểm thử có thể lặp lại trước production

Một kế hoạch thử nghiệm thực tế gồm:

### Giai đoạn A — Định nghĩa mục tiêu

Ghi lại:

```text
Dataset dự kiến:        <GiB, số key, cơ cấu data types>
Ghi/giây:               <steady và peak>
Redis/OS/container:     <versions, RAM, cgroup limit>
Storage:                <type, throughput, IOPS>
Độ trễ API p99 mục tiêu: <ms>
RPO tối đa:             <seconds / acknowledged writes>
RTO tối đa:             <seconds>
```

### Giai đoạn B — Thu baseline

Đo `INFO memory`, `INFO persistence`, CPU, disk, cgroup memory và Spring Data Redis latency khi **không có job background**.

### Giai đoạn C — Tạo RDB snapshot

Ở lab, chạy `BGSAVE`, duy trì workload tương đương production. Ghi thời gian fork, thời gian hoàn tất, COW, memory peak, p99 và disk.

### Giai đoạn D — Tạo AOF rewrite

Bật AOF trong môi trường thử nghiệm, làm log đủ lớn, chạy `BGREWRITEAOF`, đo các chỉ số tương tự cùng `aof_delayed_fsync` và disk space peak.

### Giai đoạn E — Tăng áp lực

Thử tải ghi cao, cập nhật nhiều key phân tán, disk bị cạnh tranh, cgroup limit gần thực tế. Không chỉ kiểm tra happy path.

### Giai đoạn F — Test crash/restore

Dùng ACK log ngoài Redis, gây crash trong lab theo các kịch bản đã định nghĩa, restart/restore và đối chiếu những write thành công. Không thực hiện phá dữ liệu ở production.

### Giai đoạn G — Chạy với replica/failover

Đo replication lag, failover RPO và ứng dụng reconnect. Phân biệt mất dữ liệu vì crash trên một node với mất dữ liệu do replica chưa đồng bộ.

### Giai đoạn H — Báo cáo và quyết định

Tổng hợp:

- Peak memory và headroom.
- Mức p99 tăng khi BGSAVE/rewrite.
- Thời gian background jobs.
- Disk/fsync pressure.
- Tần suất lỗi/timeout.
- RPO/RTO quan sát.
- Cấu hình được chọn và lý do.
- Giới hạn thí nghiệm và kịch bản chưa kiểm tra.

Chỉ chấp nhận cấu hình nếu kết quả trong điều kiện gần production phù hợp với yêu cầu vận hành.

## 33. Checklist vận hành và cảnh báo

### 33.1. Bộ nhớ

- [ ] Theo dõi `used_memory`, `used_memory_rss`, `used_memory_peak`.
- [ ] Theo dõi `maxmemory`, eviction và `mem_not_counted_for_evict`.
- [ ] Theo dõi cgroup/host memory, OOM events và swap.
- [ ] Đo `rdb_last_cow_size`, `aof_last_cow_size` khi có persistence job.
- [ ] Có headroom cho fork/COW theo load test thực tế.
- [ ] Hiểu workload ghi phân tán có thể tạo COW khác workload chỉ sửa key nóng.

### 33.2. Snapshot

- [ ] Biết `save` rules đang áp dụng.
- [ ] Biết lần snapshot thành công gần nhất.
- [ ] Alert khi `rdb_last_bgsave_status` thất bại.
- [ ] Theo dõi duration của BGSAVE và fork latency.
- [ ] Đảm bảo disk space/permissions và backup.
- [ ] Biết behavior khi `stop-writes-on-bgsave-error` kích hoạt.

### 33.3. AOF

- [ ] Biết `appendonly`, `appendfsync` policy.
- [ ] Theo dõi kích thước AOF và rewrite frequency.
- [ ] Alert khi `aof_last_bgrewrite_status` không thành công.
- [ ] Theo dõi `aof_delayed_fsync` và disk latency.
- [ ] Hiểu cấu trúc multi-part AOF theo Redis version.
- [ ] Đã kiểm thử restart/restore thực tế từ AOF.
- [ ] Không dọn file active AOF/manifest bằng tay.

### 33.4. Ứng dụng Spring Data Redis

- [ ] Đo GET/SET/INCR latency và error rate theo loại thao tác.
- [ ] Phân biệt cache miss, timeout và connection failure.
- [ ] Không retry mù những lệnh không idempotent.
- [ ] Biết Redis đóng vai trò cache hay nguồn sự thật đối với từng data type.
- [ ] Có cách giảm cache stampede khi Redis restart.
- [ ] Có quy trình fallback/giới hạn tải khi Redis unavailable.

### 33.5. Khôi phục

- [ ] Xác định RTO/RPO được chấp nhận trước test.
- [ ] Có backup nằm ngoài Redis instance.
- [ ] Có bài kiểm tra restore định kỳ.
- [ ] Có ACK log/nguồn đối chiếu cho workload quan trọng.
- [ ] Kiểm thử cả crash đơn node và failover qua replica.
- [ ] Ghi rõ giới hạn của replication bất đồng bộ.

## 34. Kết luận

Chi phí của **RDB snapshot** và **AOF rewrite** không chỉ là dung lượng file persistence. Với Redis lưu dữ liệu trong RAM, cơ chế fork và **copy-on-write** khiến lượng bộ nhớ vật lý cần dùng có thể tăng mạnh khi workload ghi tiếp tục trong lúc child tạo snapshot hoặc AOF base mới. CPU, disk throughput, fsync latency và file management có thể làm p95/p99 của Spring Data Redis xấu đi ngay cả khi Redis vẫn đang phục vụ lệnh.

Các nguyên tắc cần nhớ:

1. **BGSAVE tạo ảnh chụp tại mốc fork**, không bao gồm mọi ghi phát sinh cho tới lúc file hoàn tất.
2. **COW là chi phí theo memory pages bị thay đổi khi child chạy**, không bằng số byte vừa ghi và cũng không luôn bằng toàn bộ kích thước dataset.
3. **`used_memory` và `maxmemory` không đủ để dự đoán OOM**; cần đo RSS/cgroup memory, buffers, fragmentation và COW peak.
4. **AOF `appendfsync` tạo đánh đổi giữa performance và durability**; `everysec` không phải cam kết mất dữ liệu tối đa đúng một giây.
5. **BGREWRITEAOF rút gọn trạng thái để giảm AOF growth**, nhưng vẫn có fork/COW và chi phí disk; Redis 7+ có multi-part AOF cần được quản trị đúng cách.
6. **Một `SET` thành công hoặc một GET readback không chứng minh dữ liệu đã durable trên disk**. Muốn đánh giá RPO cần crash/recovery test với ACK log ngoài Redis.
7. **Replication và failover không thay thế persistence**, vì replica có thể lag và những ghi đã được client xác nhận vẫn có rủi ro mất.
8. **Trong Spring Data Redis**, quan sát lỗi/timeout, p95/p99 và chính sách retry theo bản chất idempotent của từng lệnh; tăng timeout không sửa được fork/OOM/disk bottleneck.
9. **Định cấu hình qua số đo**, không qua giả định “background thì không tốn tài nguyên” hoặc một hệ số RAM cố định.

Một hệ thống Redis có độ bền và hiệu năng tốt là hệ thống đã kiểm thử cả **snapshot, rewrite, đỉnh bộ nhớ, áp lực lưu trữ và khả năng khôi phục**, với cấu hình phù hợp giá trị dữ liệu và mức rủi ro mà ứng dụng thực sự chấp nhận.
