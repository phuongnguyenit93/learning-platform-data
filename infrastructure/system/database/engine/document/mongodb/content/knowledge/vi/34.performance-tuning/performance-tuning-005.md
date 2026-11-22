# Tập dữ liệu thường dùng, bộ nhớ đệm và tác động của đọc từ đĩa trong MongoDB

## 1. Bài toán: vì sao cùng một truy vấn có lúc nhanh, có lúc chậm?

Giả sử một ứng dụng đặt hàng có 40 triệu document trong collection `orders`. Một truy vấn tìm đơn hàng mới nhất của khách đôi khi mất 8 ms, nhưng vào giờ cao điểm lại mất 250 ms hoặc hơn, dù query text và dữ liệu trả về gần như giống nhau.

Có thể xảy ra một trong những tình huống:

- Dữ liệu hoặc trang chỉ mục cần đọc đã có sẵn trong bộ nhớ.
- Query phải nạp các trang từ ổ đĩa do trước đó chưa được truy cập.
- Một báo cáo nền đã quét rất nhiều documents và đẩy dữ liệu nóng khỏi cache.
- Dữ liệu cần đọc nằm trên nhiều trang rải rác, tạo nhiều thao tác I/O ngẫu nhiên.
- Storage throughput/IOPS hoặc hàng đợi I/O đang bão hòa.
- Truy vấn không dùng chỉ mục phù hợp nên đọc nhiều dữ liệu hơn cần thiết.
- Cache bị tranh chấp giữa nhiều truy vấn, công việc ghi, checkpoints và background tasks.

Để hiểu và giải quyết những vấn đề này, cần học ba khái niệm:

1. **Working set (tập dữ liệu thường dùng)**: những trang dữ liệu/chỉ mục mà workload thường xuyên cần trong một khoảng thời gian.
2. **Cache (bộ nhớ đệm)**: nơi giữ các trang đã đọc hoặc đang sửa để giảm nhu cầu đọc lại từ lưu trữ chậm hơn.
3. **Disk read (đọc từ đĩa)**: quá trình phải lấy dữ liệu không có trong các tầng cache; độ trễ có thể tăng đáng kể khi xảy ra thường xuyên hoặc bị bão hòa.

> **Ý chính:** Để MongoDB nhanh, không nhất thiết phải đưa **toàn bộ database** vào RAM. Điều quan trọng là những **trang dữ liệu và chỉ mục được truy cập thường xuyên nhất** có đủ chỗ trong hệ thống cache và query có đọc đúng lượng dữ liệu cần thiết hay không.

---

## 2. Working set không đồng nghĩa kích thước database

Một database trên disk có thể chứa:

```text
orders:      600 GiB
customers:    80 GiB
products:     30 GiB
indexes:     120 GiB
--------------------
Total:       830 GiB
```

Nhưng traffic thực tế chỉ tập trung vào:

- Đơn hàng trong 7 ngày gần đây.
- 100.000 khách đang hoạt động.
- Các sản phẩm còn bán.
- Những trang index dùng cho filter/sort phổ biến.

Khi đó **working set** có thể nhỏ hơn nhiều so với 830 GiB. Ngược lại, một dashboard tự động chạy truy vấn toàn bộ lịch sử mỗi vài phút có thể làm working set tăng vọt.

### 2.1. Định nghĩa mang tính vận hành

Working set là tập các **trang dữ liệu, trang chỉ mục và cấu trúc liên quan cần được giữ nóng** để phục vụ workload trong một cửa sổ thời gian xác định.

Không có một giá trị working set đúng cho mọi thời điểm:

```text
Buổi sáng:
  Ứng dụng đọc đơn hàng hôm nay.
  Working set ~ tập đơn mới + index.

Ban đêm:
  Báo cáo đọc lịch sử 2 năm.
  Working set ~ nhiều trang lịch sử.

Ngày sale:
  Nhiều người xem cùng nhóm sản phẩm.
  Working set thay đổi theo traffic và concurrency.
```

**Một thống kê dung lượng collection không tự nói được working set.** Cần kết hợp access pattern, cache counters, I/O và latency.

### 2.2. Working set gồm cả chỉ mục

Nếu ứng dụng có chỉ mục:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1
});
```

thì query theo khách và thời gian sẽ đọc **các trang B-tree của index**; có thể thêm trang document nếu cần các field không nằm trong index.

Index là một phần của working set và **cạnh tranh bộ nhớ** với các trang document. Tạo quá nhiều indexes có thể tăng chi phí cache dù từng index riêng giúp một vài query.

---

## 3. Ba tầng cần phân biệt: WiredTiger cache, OS page cache, ổ đĩa

MongoDB dùng **WiredTiger** làm storage engine mặc định trên các phiên bản hiện đại. Một cách hình dung đơn giản:

```text
                  Query / aggregation / update
                              |
                              v
                  WiredTiger internal cache
                 (các trang/cấu trúc in-memory)
                              |
                        cache miss / eviction
                              |
                              v
                    Filesystem / OS page cache
                     (file blocks do OS giữ)
                              |
                         cache miss
                              |
                              v
                       SSD / NVMe / EBS
                    (persistent storage)
```

Sơ đồ là mô hình giải thích, không phải mỗi truy vấn luôn thực hiện đúng một lượt qua tất cả tầng.

### 3.1. WiredTiger internal cache

- Giữ các trang dữ liệu và index phục vụ truy vấn.
- Quản lý memory cho đọc/ghi, dirty pages và eviction.
- Có các counters liên quan bytes cached, pages read, pages written, evictions.
- Dữ liệu trong internal cache thường ở biểu diễn được WiredTiger xử lý, khác với bytes trong file nén trên disk.

### 3.2. OS filesystem page cache

- Hệ điều hành giữ các trang file đã đọc từ storage.
- MongoDB có thể hưởng lợi khi block cần thiết còn trong page cache của OS dù không còn trong WiredTiger internal cache.
- Hệ điều hành tự quản lý phần lớn việc dùng RAM còn trống cho cache.
- Linux hiển thị `buff/cache` không có nghĩa “RAM bị lãng phí”; nhiều phần có thể được thu hồi khi workload cần.

### 3.3. Persistent storage

- Ổ SSD/NVMe hoặc cloud block storage.
- Có độ trễ cao hơn memory, đặc biệt với random I/O và queue saturation.
- Tối ưu bằng loại storage, IOPS/throughput, access pattern và khả năng phục vụ đồng thời.

**Đừng cộng dung lượng WiredTiger cache + page cache như hai bộ memory độc lập không tương tác** mà không xét OS/process overhead. Cả hai dùng tài nguyên RAM của cùng host; sizing cần tính toàn bộ hệ thống.

---

## 4. Con đường đọc một document

Giả sử:

```javascript
db.orders.findOne({
  _id: "ORD-1001"
});
```

Có index mặc định `_id_`. Server cần tìm key trong index rồi lấy document.

### 4.1. Trường hợp dữ liệu nóng

```text
Query
  |
  v
Index page đã trong WiredTiger cache
  |
  v
Document page đã trong WiredTiger cache
  |
  v
Trả dữ liệu (không cần disk read cho pages này)
```

### 4.2. Trường hợp chỉ mục nóng, document lạnh

```text
Query
  |
  v
Index page trong cache
  |
  v
Document page không ở internal cache
  |
  +--> OS page cache còn block: đọc từ memory OS
  |
  +--> OS page cache thiếu: cần storage I/O
  |
  v
Materialize document và trả kết quả
```

### 4.3. Trường hợp cả index và document đều lạnh

Truy vấn có thể cần nhiều trang từ storage, bao gồm các cấp của cấu trúc index và trang chứa document. Nếu storage bận hoặc những trang nằm rải rác, latency có thể tăng.

**Đừng giải thích mỗi `FETCH` trong `explain` là một disk read.** `FETCH` cho thấy query cần lấy document sau truy cập index, nhưng document có thể đã nằm trong bộ nhớ.

---

## 5. WiredTiger cache mặc định được cấp bao nhiêu RAM?

MongoDB mặc định tính kích thước WiredTiger internal cache theo công thức được tài liệu mô tả:

```text
max(50% × (RAM - 1 GiB), 256 MiB)
```

Ví dụ máy có 16 GiB RAM:

```text
RAM:                  16 GiB
RAM - 1 GiB:          15 GiB
50% of remainder:     7.5 GiB

WiredTiger cache mặc định xấp xỉ 7.5 GiB.
```

Đây là **ví dụ theo công thức**, không khẳng định mọi container/platform sẽ báo đúng 7.5 GiB; cần kiểm tra effective runtime configuration, tài nguyên được cấp và phiên bản MongoDB.

### 5.1. Vì sao không dùng toàn bộ RAM?

WiredTiger không phải thành phần duy nhất cần RAM:

- OS page cache.
- MongoDB process code và các cấu trúc ngoài WiredTiger cache.
- Connections và network buffers.
- Query/aggregation intermediate memory.
- Index build memory.
- Journaling/background operations.
- Hệ điều hành và monitoring agents.
- Những tiến trình khác trên cùng host.

Nếu ép internal cache quá lớn, hệ thống có thể thiếu chỗ cho OS page cache hoặc bị memory pressure.

### 5.2. Cấu hình cacheSizeGB

Trên MongoDB self-managed:

```yaml
storage:
  wiredTiger:
    engineConfig:
      cacheSizeGB: 8
```

Hoặc tùy chọn khởi động tương ứng:

```bash
mongod --wiredTigerCacheSizeGB 8
```

**Lưu ý:** các ví dụ chỉ nhằm mô tả option; không khởi động một mongod mới trên production dbPath khi chưa biết topology, service configuration và policy. Việc đổi cache sizing thường liên quan khởi động lại instance và cần kiểm chứng phiên bản.

### 5.3. Khi nào không nên chỉnh tay?

- Chưa biết working set thực.
- Chưa đo eviction/cache metrics.
- Không thấy I/O là bottleneck.
- Host còn nhiều process cạnh tranh RAM.
- MongoDB đang chạy trên managed tier có sizing riêng.
- Chỉ vì thấy cache “đầy 90%”.

Cache được thiết kế để **được sử dụng**; tỷ lệ chiếm cao không tự là lỗi.

---

## 6. Không nhầm cache “đầy” với cache “quá tải”

Một cache ở mức 90–95% có thể hoạt động bình thường nếu:

- Các trang nóng được giữ ổn định.
- Eviction có thể giải phóng trang ít dùng mà không ảnh hưởng nhiều tới truy vấn.
- I/O đọc từ disk thấp.
- p95/p99 query latency tốt.
- Không có queue eviction kéo dài.

Ngược lại, cache chỉ 70% vẫn có thể có query latency cao do:

- Query scan những trang chưa từng đọc.
- Index thiếu hoặc thứ tự index không phù hợp.
- Random disk I/O cao.
- Dataset nằm ngoài cache và thay đổi liên tục.
- Aggregation spill ra disk.
- IOPS của volume đã đạt giới hạn.

**Chẩn đoán từ nhiều tín hiệu**, không dùng một threshold cache usage làm kết luận duy nhất.

---

## 7. Trang dữ liệu, trang index và compression

WiredTiger lưu dữ liệu trên disk ở cấu trúc pages/blocks, có khả năng nén dữ liệu.

Các ý cần phân biệt:

- **Logical document size**: độ dài BSON của document.
- **Storage size**: dung lượng vật lý của các files/blocks liên quan, chịu tác động compression/overhead.
- **In-memory cache footprint**: dung lượng trang và cấu trúc mà WiredTiger quản lý trong RAM.
- **Index size**: dung lượng chỉ mục, không phải số trang index chắc chắn resident trong cache.

### 7.1. Không lấy storageSize làm working set

Ví dụ:

```text
Collection logical documents: 100 GiB
On-disk compressed storage:   40 GiB
Indexes on disk:             15 GiB

Không được tự suy ra:
  Working set = 55 GiB
```

Working set có thể nhỏ hơn nhiều nếu chỉ đọc 5% dữ liệu, hoặc lớn hơn các ước lượng đơn giản nếu queries, update patterns, memory representations và concurrency đòi hỏi nhiều RAM.

### 7.2. Compression có cả lợi và chi phí

- Giảm bytes đọc từ disk và sử dụng storage.
- Có thể làm tăng CPU cho nén/giải nén.
- Không bảo đảm kích thước trang trong internal cache giảm tỷ lệ giống on-disk.
- Với workload I/O-bound, compression có thể giúp nhờ giảm physical bytes.
- Với workload CPU-bound, compression cost có thể trở thành yếu tố cần benchmark.

Đừng tắt compression để “cache nhanh hơn” nếu chưa đo throughput, CPU, disk latency và volume size.

---

## 8. Hot set, warm set và cold set

Một mô hình thực hành:

| Nhóm | Đặc điểm | Cách xử lý |
| --- | --- | --- |
| **Hot** | Truy cập lặp lại với tần suất cao | Ưu tiên index/query tối ưu và cache residence |
| **Warm** | Truy cập không thường xuyên nhưng định kỳ | Cân nhắc OS page cache, lịch background jobs |
| **Cold** | Lịch sử rất ít truy vấn | Archive/tier storage hoặc query riêng |

Ví dụ ứng dụng:

```text
Hot:
  orders last 24 hours
  active customers
  current product catalog

Warm:
  last month's invoices
  support case history

Cold:
  orders older than 5 years
  deactivated users' historical metadata
```

Dữ liệu cold không có nghĩa có thể xóa. Chính sách archive/retention phải giữ tính toàn vẹn nghiệp vụ và yêu cầu pháp lý.

### 8.1. Truy vấn hot có thể đọc cold pages

Một query nhìn có vẻ nóng nhưng thiếu index:

```javascript
db.orders.find({
  status: "PENDING"
});
```

Nếu chỉ 1% đơn hàng còn PENDING nhưng không có index thích hợp, query có thể scan gần như toàn bộ collection, lôi trang cold vào cache.

Vì vậy **tối ưu working set phải bắt đầu từ access paths**, không chỉ phân loại dữ liệu theo tuổi.

---

## 9. Đo tập dữ liệu nóng bằng hành vi đọc, không chỉ dung lượng

Một phương pháp thực tế:

1. Thu thập top queries theo request count và latency.
2. Xác định fields filter/sort/projection.
3. Xem index/query plans cho các query patterns đó.
4. Xác định phạm vi dữ liệu hay được truy cập (thời gian, tenant, category).
5. Quan sát WiredTiger pages read/evicted theo thời gian.
6. Quan sát disk read IOPS, throughput và latency.
7. So sánh p50/p95/p99 latency giữa giờ bình thường và cao điểm.
8. Thử tải mô phỏng trên staging tương tự dữ liệu thật.
9. Đánh giá phần trăm request được phục vụ khi các pages nóng đã resident.

MongoDB không có một lệnh phổ quát “hiển thị chính xác tổng working set bytes của mọi query trong 7 ngày”. Các phép tính thường là **ước lượng và suy luận từ nhiều metrics**.

### 9.1. Quan sát thay đổi theo giờ

```text
09:00–11:00  Web traffic lớn, working set tập trung.
12:00–12:30  Import products batch.
13:00–16:00  Web traffic trở lại.
01:00–04:00  Analytics quét toàn bộ lịch sử.
```

Nếu analytics làm tăng cache evictions và sau đó web traffic chậm dù batch đã xong, đó là tín hiệu **cache pollution** có thể đáng điều tra.

---

## 10. Cache hit và cache miss thực sự nghĩa là gì?

**Cache hit**: dữ liệu cần đọc đã có trong cache ở cấp được xét.

**Cache miss**: dữ liệu không có ở cấp cache đó và phải lấy từ cấp dưới.

### 10.1. Miss ở WiredTiger không đồng nghĩa disk read

```text
WiredTiger cache miss
       |
       +--> OS page cache hit
       |      vẫn đọc bằng memory, không phải physical disk I/O
       |
       +--> OS page cache miss
              -> persistent storage read
```

Một counter “pages read into WiredTiger cache” **không đủ** chứng minh từng page gây disk I/O. Có thể các block được OS page cache phục vụ.

### 10.2. Page fault của OS cũng phải đọc đúng nghĩa

- **Minor page fault** thường không yêu cầu physical disk I/O.
- **Major page fault** có thể liên quan đọc từ storage.
- Các counters page fault không trực tiếp đại diện toàn bộ số logical reads của MongoDB.
- Một số platform/cgroup/filesystem không phơi cùng metrics hoặc có interpretation khác.

Đừng thấy page faults tăng rồi ngay lập tức kết luận “MongoDB đọc đĩa quá nhiều” nếu không đối chiếu disk read IOPS/latency.

### 10.3. Cache hit rate không phải metric duy nhất

Có thể giữ hit rate 99% nhưng 1% misses nằm trên một endpoint quan trọng và gây p99 latency xấu. Ngược lại 90% hit rate trong workload batch tuần tự có thể chấp nhận được.

Quan trọng là **chi phí thực của misses và workload business**.

---

## 11. Eviction: khi WiredTiger cần lấy chỗ cho trang khác

**Eviction** là quá trình đưa trang ít cần thiết ra khỏi internal cache để lấy chỗ cho các trang khác.

```text
WT cache:
  hot A | hot B | cold C | cold D

Query mới cần E:
  evict cold C
  load E

WT cache:
  hot A | hot B | new E  | cold D
```

Đây là hành vi bình thường.

### 11.1. Khi eviction trở thành vấn đề

- Cache không đủ chỗ cho tập trang được truy cập lặp lại.
- Query scan lượng dữ liệu lớn làm trang vừa nạp đã bị đẩy ra.
- Nhiều dirty pages cần xử lý trước khi có thể evict.
- Application threads phải tham gia eviction, ảnh hưởng latency.
- Disk writes/checkpoint không theo kịp.
- Cache churn tăng cùng p95/p99 latency.

### 11.2. Dirty pages

Một page đã sửa trong memory nhưng thay đổi chưa được ghi xuống storage data files tương ứng có thể là **dirty page**.

Đừng nhầm dirty page với “write đã mất durability”:

- MongoDB/WiredTiger dùng journaling, write concern, replication và checkpoint theo cơ chế riêng.
- Durability của một write không chỉ xác định bằng việc data page đã được checkpoint ra collection file hay chưa.
- Majority write concern và journal policy vẫn cần hiểu riêng.

### 11.3. Cache dirty pressure và background writes

Khi dirty pages tích tụ, checkpoint và eviction có thể tạo burst disk writes. Trên volume dùng chung read/write IOPS, write burst có thể khiến read latency tăng dù query read volume không đổi.

---

## 12. Checkpoint, journal và disk I/O

WiredTiger có nhiều nguồn I/O:

| Nguồn | Tại sao phát sinh |
| --- | --- |
| Read cache miss | Cần trang dữ liệu/index chưa resident |
| Eviction/writeback | Đẩy những trang đã thay đổi ra storage |
| Checkpoint | Tạo một trạng thái bền vững trên disk |
| Journal | Ghi log thay đổi cho crash recovery/durability |
| Index build | Đọc dữ liệu, tạo cấu trúc chỉ mục |
| Aggregation spill | Ghi/đọc tệp tạm |
| Backup/restore | Đọc/ghi lượng dữ liệu lớn |
| Compaction | Sắp xếp/tái cấu trúc storage theo thao tác |
| Initial sync | Sao chép dữ liệu và indexes |

### 12.1. Đọc tăng có thể do một hoạt động không phải request người dùng

Ví dụ:

- Backup agent quét nhiều dữ liệu.
- Index build quét collection.
- Analytics/reporting batch đọc documents lạnh.
- Scan kiểm tra integrity.
- Restore/initial sync đọc từ source.

Vì vậy, khi thấy Disk Read IOPS tăng, cần xem **timeline của background operations** chứ không chỉ xem ứng dụng web.

### 12.2. Không tắt journal hoặc giảm write concern để “cứu cache”

Những thao tác đó thay đổi bảo đảm durability/consistency và có thể gây mất dữ liệu khi failure. Chúng không phải hướng giải quyết trực tiếp cho truy vấn đọc quá nhiều trang.

---

## 13. Disk đọc ngẫu nhiên và đọc tuần tự

Hai query cùng đọc 1 GiB nhưng có thể tốn thời gian khác nhau.

### 13.1. Sequential scan

Truy vấn đọc tương đối tuần tự nhiều blocks:

```text
Block 1 -> Block 2 -> Block 3 -> ... -> Block N
```

Storage và OS có thể tận dụng throughput/read-ahead trong một số trường hợp.

### 13.2. Random reads

Truy vấn cần nhiều documents rải rác:

```text
Block 1023 -> Block 7 -> Block 90051 -> Block 231 -> ...
```

Random reads có thể bị giới hạn bởi IOPS và latency hơn là throughput MB/s.

### 13.3. Ảnh hưởng của index

Một index hiệu quả có thể giảm số document pages cần đọc, nhưng một query lấy hàng trăm nghìn documents qua index có thể gây random fetches nhiều hơn một scan tuần tự. Query planner có thể chọn `COLLSCAN` khi đó có lợi cho workload.

Do vậy **có IXSCAN không đồng nghĩa query chắc nhanh hơn COLLSCAN**. Cần xem selectivity và thực nghiệm.

---

## 14. Disk IOPS, throughput, latency và queue depth

Bốn thông số thường được nhắc cùng nhau nhưng khác ý nghĩa:

| Metric | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| **IOPS** | Operations/s | Số I/O đã xử lý mỗi giây |
| **Throughput** | MiB/s | Lượng bytes đọc/ghi mỗi giây |
| **Latency** | ms/op | Thời gian xử lý mỗi I/O |
| **Queue depth** | Số operations chờ | Số yêu cầu I/O đang xếp hàng hoặc in-flight |

### 14.1. Công thức minh họa

Nếu volume xử lý 10.000 reads/s và mỗi read trung bình 4 KiB:

```text
Throughput ≈ 10000 × 4 KiB/s
           ≈ 39.1 MiB/s
```

Nếu mỗi I/O là 256 KiB:

```text
Throughput ≈ 10000 × 256 KiB/s
           ≈ 2500 MiB/s
```

Hai con số là minh họa lý thuyết. Volume thật có giới hạn IOPS/throughput và kích thước I/O khác nhau.

### 14.2. Vì sao latency tăng phi tuyến khi bão hòa?

Khi tốc độ yêu cầu I/O gần hoặc vượt khả năng phục vụ, hàng đợi tăng. Một lệnh đọc vốn mất khoảng 1 ms lúc ít tải có thể mất nhiều ms khi bị xếp hàng.

Độ trễ ứng dụng chịu cả:

```text
Request latency
  ≈ query planning/execution CPU
  + cache misses / storage wait
  + lock/resource contention
  + server-to-client transfer
  + application/network overhead
```

Không thể lấy Disk I/O latency và gán toàn bộ cho query một cách 1:1.

---

## 15. Vì sao SSD/NVMe thường quan trọng với MongoDB?

MongoDB document/index workloads có thể phát sinh random I/O đáng kể.

So với ổ cứng cơ học HDD, SSD/NVMe thường có:

- Random read latency thấp hơn.
- Khả năng xử lý nhiều I/O concurrent tốt hơn.
- IOPS cao hơn.
- Ít bị ảnh hưởng bởi seek time cơ học.

Trong cloud, SSD-backed volume vẫn có thể bị giới hạn bởi:

- Provisioned IOPS.
- Provisioned throughput.
- Burst credits.
- Network attach bandwidth.
- Instance-level limits.
- Shared infrastructure contention.

### 15.1. Nâng cấp disk không sửa query sai

Nếu query phải scan 10 triệu documents vì thiếu index, chuyển từ HDD sang NVMe có thể cải thiện một phần nhưng vẫn đọc quá nhiều dữ liệu.

Thứ tự ưu tiên thường là:

1. Sửa access pattern/query.
2. Tạo index phù hợp.
3. Giảm số dữ liệu không cần đọc.
4. Đo working set và cache.
5. Nâng storage/memory khi đã biết bottleneck.

---

## 16. Ví dụ: query không dùng index kéo dữ liệu lạnh vào cache

Giả sử:

```javascript
db.orders.insertMany([
  {
    _id: "O1",
    tenantId: "T1",
    status: "PAID",
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    totalMinor: 120000
  },
  {
    _id: "O2",
    tenantId: "T1",
    status: "PAID",
    createdAt: ISODate("2026-11-03T09:00:00Z"),
    totalMinor: 80000
  },
  {
    _id: "O3",
    tenantId: "T1",
    status: "PENDING",
    createdAt: ISODate("2026-11-13T11:00:00Z"),
    totalMinor: 60000
  }
]);
```

Đây là ví dụ tạo dữ liệu minh họa trong **database test**, không chạy insert trùng IDs trên production.

Query nghiệp vụ:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({
  createdAt: -1
}).limit(20);
```

Nếu collection thật có hàng triệu orders mà thiếu index, query có thể:

- Duyệt nhiều documents không khớp tenant/status.
- Đọc nhiều data pages lạnh.
- Tiêu thụ CPU cho filter.
- Sort nhiều records.
- Đẩy pages phục vụ online traffic ra khỏi cache.

### 16.1. Thử compound index

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Lúc này query planner có thể định vị các entries theo tenant/status, sau đó đọc phần thời gian mong muốn theo thứ tự index.

**Đây là index gợi ý cho query shape cụ thể, không phải luôn tối ưu cho mọi workload.** Cần xem distribution dữ liệu và `explain`.

### 16.2. Tác động lên working set

Trước khi có index: request có thể liên tục chạm nhiều data pages.

Sau khi có index: một phần hot index pages và ít document pages tương ứng có thể đủ cho request.

Chỉ mục phù hợp **giảm tổng lượng dữ liệu phải đưa qua cache**, chứ không chỉ giảm số phép so sánh CPU.

---

## 17. Explain: nhìn đúng những gì nó cho biết

Chạy trên môi trường phù hợp:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({
  createdAt: -1
}).limit(20)
  .explain("executionStats");
```

Quan sát:

| Trường/hiện tượng | Ý nghĩa gợi ý |
| --- | --- |
| `nReturned` | Số document trả ra trong execution |
| `totalKeysExamined` | Số index keys được scan |
| `totalDocsExamined` | Số document được kiểm tra |
| `IXSCAN` | Có truy cập index |
| `COLLSCAN` | Duyệt collection |
| `FETCH` | Phải đọc/fetch document từ dữ liệu |
| `SORT` | Có bước sort riêng trong plan |
| `executionTimeMillis` | Thời gian server ghi nhận trong explain, không phải toàn bộ latency của app |

### 17.1. Tỷ lệ docs examined/nReturned

Nếu:

```text
nReturned:          20
totalDocsExamined:  500000
```

thì có thể query đang đọc quá nhiều documents so với kết quả cần. Tuy nhiên cần xem mục tiêu thật, aggregation sau query, filter cardinality và index plan.

Nếu:

```text
nReturned:          20
totalDocsExamined:  20
```

thì query có thể đã rất chọn lọc. Nhưng **không chứng minh nó không đọc disk**, vì các document pages có thể lạnh.

### 17.2. Explain không hiển thị “20 disk reads” cho 20 FETCH

`FETCH` nghĩa là lấy data documents; chúng có thể đã trong WiredTiger cache hoặc OS page cache. Phải kết hợp disk I/O metrics khi muốn kết luận chi phí physical read.

### 17.3. Execution stats có thể thay đổi cache state

Chạy một query để explain cũng có thể thực sự đọc dữ liệu và làm nóng cache. Không lặp `explain("executionStats")` hàng nghìn lần trên production chỉ để đo mà không đánh giá overhead.

---

## 18. Covered query: bỏ qua document fetch khi có thể

Một **covered query** có thể được đáp ứng chỉ từ index keys, không cần đọc document data pages, nếu filter/projection và các điều kiện khác phù hợp.

Giả sử:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  totalMinor: 1
});
```

Query:

```javascript
db.orders.find(
  {
    tenantId: "T1",
    status: "PAID"
  },
  {
    _id: 0,
    createdAt: 1,
    totalMinor: 1,
    tenantId: 1,
    status: 1
  }
).sort({
  createdAt: -1
}).limit(20);
```

Trong điều kiện phù hợp, index trên có thể phục vụ filter/sort/projection mà không cần fetch đầy đủ documents.

### 18.1. Vì sao cần _id:0?

MongoDB mặc định trả `_id`. Nếu `_id` không có trong compound index, projection tự động gồm `_id` có thể khiến query không được cover. Do đó ví dụ chủ động loại `_id`.

### 18.2. Không cố cover mọi query

Thêm nhiều fields vào index làm index lớn:

- Tăng disk/index storage.
- Tăng cache footprint.
- Tăng cost insert/update/delete.
- Có thể giảm throughput ghi.

Chỉ nên cố tạo covered index cho những query thực sự quan trọng và projection ổn định.

### 18.3. Limitations

Multikey index, null/missing semantics, collation, array projection và query engine/version có thể ảnh hưởng khả năng covered. Dựa vào `explain` để xác nhận, không chỉ đoán từ index definition.

---

## 19. Projection có giảm disk I/O không?

Xét hai queries:

```javascript
// A: trả toàn bộ document
db.orders.find({
  tenantId: "T1"
});

// B: trả ít fields hơn
db.orders.find(
  { tenantId: "T1" },
  { _id: 1, status: 1 }
);
```

Projection B có thể giảm:

- Kích thước response truyền qua network.
- BSON serialization.
- Application memory.
- Một số CPU xử lý fields.

Nhưng nếu server vẫn phải fetch document page, projection **không bảo đảm giảm physical disk reads tỷ lệ với số bytes giảm trong response**.

Projection giảm đáng kể data reads khi kết hợp với **index-covered query** hoặc các access patterns/columnar features thích hợp, tùy phiên bản và cấu hình.

### 19.1. Tài liệu lớn/BinData

Nếu một document có field nhị phân lớn và request list chỉ cần tên/trạng thái, thiết kế schema tách metadata khỏi binary (hoặc dùng GridFS/object storage theo use case) có thể tránh đọc và trả payload không cần thiết.

Không tự coi “chỉ projection vài fields” là phương án xử lý mọi document quá lớn.

---

## 20. Index lớn: lợi ích truy vấn và chi phí bộ nhớ

Một index tốt có thể loại bỏ collection scan. Nhưng có thể xảy ra trường hợp:

```text
Collection storage:   40 GiB
Index A:               8 GiB
Index B:              10 GiB
Index C:              12 GiB
Index D:              15 GiB
-----------------------------
Total indexes:        45 GiB
```

Nếu chỉ một số index được dùng thường xuyên, phần index còn lại vừa tốn storage, vừa tăng update overhead.

### 20.1. Không xóa index chỉ vì nhìn lớn

Cần kiểm tra:

- Query nào dùng index?
- Index có hỗ trợ sort hoặc uniqueness không?
- Có phục vụ batch/maintenance queries định kỳ không?
- Có index prefix trùng lặp không?
- Có cần nhiều index vì các query shapes khác nhau không?
- Đã test ẩn index bằng hidden index trên staging hoặc quy trình được hỗ trợ chưa?

### 20.2. Index selectivity ảnh hưởng cache

Một index trên field có rất ít giá trị khác nhau, như `status` chỉ có 3 giá trị, đôi khi không đủ chọn lọc.

```javascript
db.orders.createIndex({
  status: 1
});
```

Nếu 95% orders có `status: "PAID"`, truy vấn PAID vẫn phải đọc rất nhiều documents và có thể gây nhiều data page fetches.

Compound index kết hợp tenant/time và query pattern thực tế thường đáng xem xét.

---

## 21. Thao tác đọc theo thời gian và tính locality

Working set không chỉ do “bao nhiêu documents” mà còn do **locality**.

### 21.1. Time-range queries

Một ứng dụng thường đọc:

```javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
});
```

Nếu data được truy cập chủ yếu theo thời gian, index phù hợp giúp server tập trung vào khoảng mới thay vì quét toàn bộ lịch sử.

### 21.2. Tenant locality

Một hệ SaaS đọc theo:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "OPEN"
});
```

Đặt `tenantId` ở đầu index compound có thể giúp access locality cho filter equality, nhưng điều này phải được kiểm chứng với sort/range và cardinality.

### 21.3. Hot key

Một document nhận hàng nghìn requests mỗi giây:

```javascript
db.config.findOne({
  _id: "global-feature-flags"
});
```

Câu query có thể được cache rất tốt, nhưng workload ghi cạnh tranh lên cùng document có thể tạo contention ở lớp khác. Không quy mọi latency của hot key thành disk I/O.

---

## 22. Aggregation có thể làm cache bị nhiễu

Ví dụ batch báo cáo:

```javascript
db.orders.aggregate([
  {
    $match: {
      createdAt: {
        $gte: ISODate("2024-01-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      total: { $sum: "$totalMinor" }
    }
  }
]);
```

Nếu dữ liệu lịch sử rất lớn, aggregation có thể đọc nhiều pages không nằm trong hot set của web application.

### 22.1. Ba loại chi phí

1. **Source reads**: đọc document/index pages từ collection.
2. **Intermediate memory**: dùng RAM cho `$group`, `$sort` hoặc các stages khác.
3. **Disk spill**: ghi/đọc tệp tạm nếu stage được phép spill khi vượt memory limit.

Ba loại này khác nhau, nhưng cùng gây pressure lên disk/memory.

### 22.2. allowDiskUse không phải cách làm query nhanh hơn

```javascript
db.orders.aggregate(
  [
    {
      $group: {
        _id: "$tenantId",
        count: { $sum: 1 }
      }
    }
  ],
  {
    allowDiskUse: true
  }
);
```

`allowDiskUse` cho phép một số stages ghi dữ liệu tạm ra disk khi cần, theo MongoDB version/server settings. Nó tránh lỗi memory limit trong những trường hợp được hỗ trợ nhưng **có thể tăng I/O và latency**.

Dấu hiệu disk spill trong explain/profiler có thể gồm `usedDisk`, `spills` hoặc fields tương đương tùy version/stage.

### 22.3. Chiến lược giảm tác động

- Dùng index để lọc dữ liệu sớm.
- Thu hẹp khoảng thời gian báo cáo.
- Giảm fields/data cần xử lý.
- Dùng pre-aggregated/materialized views nếu phù hợp.
- Chuyển batch scan nặng sang thời gian ít traffic hoặc deployment/secondary riêng, có xét replication impact.
- Giới hạn concurrency của các jobs lớn.

---

## 23. Scan định kỳ và cache pollution

Một công việc gọi:

```javascript
db.events.find({}).batchSize(1000);
```

trên collection có 500 triệu events có thể đọc rất nhiều cold pages. Nếu lặp lại nhiều lần, nó có thể làm trang hot của ứng dụng bị evict.

### 23.1. Cache pollution biểu hiện thế nào?

Timeline giả định:

```text
08:50  Query web p95 = 20 ms
09:00  Analytics scan bắt đầu
09:05  Disk read IOPS tăng mạnh
09:07  WT pages read/evicted tăng
09:10  Query web p95 = 250 ms
09:20  Analytics scan kết thúc
09:25  Query web dần nhanh trở lại
```

Đây là mẫu điều tra, không chứng minh nhân quả nếu thiếu metrics tương quan.

### 23.2. Giảm nhiễu theo cách nào?

- Tách analytics read workload nếu kiến trúc cho phép.
- Chuyển một số truy vấn lớn sang secondary chuyên dụng, nhưng tránh gây oplog lag.
- Dùng precomputed summaries.
- Thêm index/filter theo thời gian.
- Giảm batch scan frequency/concurrency.
- Archive lịch sử sang nơi phù hợp.

**Không** đẩy mọi analytics lên secondary rồi quên rằng secondary cũng cần disk, memory và replication capacity.

---

## 24. Tác động của đọc từ đĩa lên p50, p95, p99 latency

Giả sử có 1.000 requests:

```text
950 requests: pages hot, mất 5 ms
 40 requests: một vài page misses, mất 30 ms
 10 requests: nhiều disk reads, mất 250 ms
```

Kết quả:

- p50 có thể vẫn gần 5 ms.
- p95 có thể ở khoảng nhóm cache miss.
- p99 hoặc tail latency chịu ảnh hưởng mạnh của các requests cần nhiều I/O.

Một thay đổi khiến cache misses tăng có thể **làm p99 xấu đi rất nhiều** trong khi p50 gần như không đổi.

### 24.1. Vì sao p99 quan trọng?

Người dùng thường thấy những request chậm nhất khi:

- Mở trang đầu sau giờ nghỉ.
- Truy vấn tenant ít hoạt động.
- Lấy dữ liệu cũ chưa nóng.
- Workload tăng đồng thời.
- Cache vừa bị một batch job làm nhiễu.

Nếu SLA nhắm p99, cần benchmark cả **warm state** và **cold-ish state**, không chỉ query lặp lại 100 lần trên cùng document.

---

## 25. Đọc từ cache vẫn có CPU cost

Cache hit không đồng nghĩa query miễn phí:

- B-tree traversal cần CPU.
- BSON decode/materialization cần xử lý.
- Predicate evaluation vẫn chạy.
- Aggregation expressions vẫn tính toán.
- Sort/hashing cần memory/CPU.
- Network serialization tốn thời gian.
- Lock/ticket/worker scheduling có thể gây chờ.

Một query mất 100 ms dù Disk Read IOPS gần 0 có thể là CPU-bound hoặc resource contention, không phải “cần thêm RAM”.

### 25.1. Chẩn đoán bốn nhóm chính

```text
High CPU + low disk reads?
  -> query CPU, aggregation, document size, concurrency

High read IOPS + read latency?
  -> cache misses, index, storage saturation

High disk writes + read latency?
  -> checkpoint/dirty eviction, write contention

Low CPU/disk but high app latency?
  -> network, connection pool, locks, remote service
```

Đây chỉ là gợi ý phân loại, không thay trace/profiler đầy đủ.

---

## 26. Đọc metrics WiredTiger từ serverStatus

Với quyền phù hợp:

```javascript
const status = db.serverStatus();

printjson({
  wiredTigerCache: status.wiredTiger
    ? status.wiredTiger.cache
    : null
});
```

Một số counters/fields thường gặp trong phần `wiredTiger.cache`:

- `maximum bytes configured`.
- `bytes currently in the cache`.
- `tracked dirty bytes in the cache`.
- `pages read into cache`.
- `pages written from cache`.
- `pages evicted by application threads`.
- Các counters liên quan eviction queues, eviction progress và application waiting.

**Tên fields có thể khác nhau theo version/storage engine/platform.** Đọc tên keys thực tế trong `db.serverStatus().wiredTiger.cache` của môi trường đang chạy, không giả định mọi version có tất cả counters.

### 26.1. Lấy một số metric phổ biến

```javascript
const cache = db.serverStatus().wiredTiger.cache;

printjson({
  maximumBytes: cache["maximum bytes configured"],
  currentBytes: cache["bytes currently in the cache"],
  dirtyBytes: cache["tracked dirty bytes in the cache"],
  pagesRead: cache["pages read into cache"],
  pagesWritten: cache["pages written from cache"]
});
```

Không lấy các giá trị `undefined` làm bằng chứng server không có cache. Có thể tên metric thay đổi, bị ẩn hoặc command không trả đủ do permission/platform.

### 26.2. Cumulative counters cần tính delta

Nếu:

```text
pages read into cache tại 10:00 = 1,000,000
pages read into cache tại 10:01 = 1,006,000

Delta = 6,000 pages trong 60 giây
Rate  = 100 pages/giây
```

Không kết luận từ số 1.006.000 “MongoDB đang chậm” vì đó có thể là tổng tích lũy từ lúc server khởi động.

### 26.3. Counter reset

Các cumulative counters thường reset khi process restart. Khi tính delta, nếu số sau nhỏ hơn số trước, phải xét restart/reconfiguration thay vì coi là I/O âm.

---

## 27. Script mongosh lấy snapshot cache metrics

Ví dụ lệnh **đọc-only**:

```javascript
function getCacheSnapshot() {
  const s = db.serverStatus();
  const c = s.wiredTiger && s.wiredTiger.cache
    ? s.wiredTiger.cache
    : {};

  return {
    at: new Date(),
    host: s.host,
    uptimeSeconds: s.uptime,
    maximumBytes: c["maximum bytes configured"],
    currentBytes: c["bytes currently in the cache"],
    dirtyBytes: c["tracked dirty bytes in the cache"],
    pagesRead: c["pages read into cache"],
    pagesWritten: c["pages written from cache"],
    pagesEvictedByApp:
      c["pages evicted by application threads"]
  };
}

printjson(getCacheSnapshot());
```

Nếu script chạy định kỳ, có thể lưu các snapshots vào monitoring metrics store; không ghi lại vào cùng MongoDB production bằng một job quá thường xuyên nếu không xét overhead.

### 27.1. Không tính cache hit rate từ một counter duy nhất

Công thức kiểu:

```text
hitRate = 1 - pagesRead / totalQueries
```

**Không hợp lệ** nếu `pagesRead` là pages, `totalQueries` là queries. Một query có thể đọc 0, 1 hoặc nhiều pages; các counters thuộc đơn vị khác nhau.

Dùng metrics có định nghĩa chính thức cho cache hit rate nếu nền tảng có, hoặc phân tích read/eviction rates cùng workload và disk I/O.

---

## 28. Theo dõi OS và disk trên self-managed Linux

Các lệnh chẩn đoán thường dùng:

```bash
# Tình trạng RAM, OS page cache và memory available
free -h

# Paging, run queue, CPU wait
vmstat 1

# Disk latency/IOPS/queue (cần sysstat/iostat)
iostat -xz 1

# Process-level CPU/memory
pidstat -r -u -p ALL 1
```

Các lệnh chỉ đọc metrics. Trên container hoặc cloud managed deployment, chúng có thể cần quyền host hoặc không phản ánh toàn bộ storage path.

### 28.1. Free memory thấp chưa chắc thiếu RAM

Linux dùng bộ nhớ rảnh cho file cache. Khi `free -h` hiển thị:

```text
free:        thấp
buff/cache:  cao
available:   vẫn tốt
```

đó có thể là tình huống lành mạnh. Quan sát `available`, swap activity, OOM events, memory pressure và hiệu năng thay vì chỉ số `free`.

### 28.2. iostat cần đọc đúng volume

Nếu data files nằm trên `/dev/nvme1n1` nhưng bạn xem `/dev/nvme0n1`, kết luận disk sẽ sai. Trên cloud, đọc thêm provider volume metrics như IOPS/throughput/burst credits.

### 28.3. CPU iowait không phải “MongoDB đang chờ I/O” chắc chắn

`iowait` là một thống kê CPU tại OS level. Nhiều processes cùng sử dụng disk; cần correlate với process workload, disk metrics, WiredTiger counters và query latency.

---

## 29. Metrics và công cụ trong MongoDB Atlas

Với Atlas, phần metrics/chart được quản lý qua UI/API theo edition/tier. Các nhóm cần quan sát:

- WiredTiger cache usage và dirty pages.
- Disk Read IOPS.
- Disk Write IOPS.
- Disk I/O latency nếu được exposed.
- Disk queue depth/throughput.
- System memory/cache.
- CPU utilization.
- Connections và operation queues.
- Query targeting, scans/returned, slow queries.
- Replication lag và background activity.
- Backup/initial sync/index build activity.
- Search workload nếu dùng MongoDB Search.

### 29.1. Không lấy một chart làm nguyên nhân

Ví dụ tăng Disk Read IOPS cùng p99 latency không chứng minh cache là nguyên nhân duy nhất. Có thể có index build, backup hoặc batch scan chung thời điểm.

Cần xây timeline giữa **query shape**, **cache**, **storage** và **application latency**.

---

## 30. Đo dung lượng collection/index để lập giả thuyết

Trên collection có dữ liệu thật và với quyền phù hợp:

```javascript
db.orders.stats({
  scale: 1024 * 1024
});
```

Các fields đáng quan tâm:

- `count`.
- `size`.
- `storageSize`.
- `totalIndexSize`.
- `indexSizes`.

Hoặc dùng aggregation:

```javascript
db.orders.aggregate([
  {
    $collStats: {
      storageStats: {
        scale: 1024 * 1024
      }
    }
  }
]);
```

Field availability và cách diễn giải có thể khác theo version/topology. Kích thước trả về chỉ cho biết **dung lượng**, chưa cho biết **tần suất truy cập**.

### 30.1. Ước lượng sơ bộ

Giả sử:

```text
Recent 7-day order data:    12 GiB on disk
Relevant hot indexes:        6 GiB on disk
Cold history:              300 GiB on disk
```

Không suy ra hot memory cần đúng 18 GiB, nhưng có thể dùng đây là **giả thuyết đầu tiên** để so với actual cache residence, pages-read rates và traffic latency.

---

## 31. Query profiler và slow query logs

MongoDB profiler và logs có thể giúp tìm những query đọc nhiều dữ liệu:

- `docsExamined`.
- `keysExamined`.
- `nreturned`.
- `planSummary`.
- `millis`.
- `numYields`.
- Disk spill/temporary storage fields nếu được hỗ trợ.
- Lock/resource wait metrics theo phiên bản.

### 31.1. Không bật profiling quá mức trên production

Full profiling mọi query có overhead và có thể ghi dữ liệu nhạy cảm trong query parameters. Nên dùng các công cụ/query insights phù hợp deployment, sampling và retention policy.

### 31.2. Phân biệt query shape và instance

Một `find` cụ thể có thể có latency khác nhau khi:

- Cache ấm/lạnh.
- Tenant dữ liệu nhiều/ít.
- Query predicate selectivity khác.
- Storage vừa bị backup load.
- Index plan thay đổi.

Do đó cần phân nhóm theo query shape **và** parameters/data distribution quan trọng.

---

## 32. Thí nghiệm: warm cache và cold cache

Một cách kiểm chứng tốt hơn là benchmark trên **staging với dữ liệu có phân bố tương tự production**.

### 32.1. Thí nghiệm A — warm repeated reads

1. Chọn query shape đại diện.
2. Gọi query lặp lại sau khi hệ ổn định.
3. Đo p50/p95/p99, CPU và disk read rates.
4. Đảm bảo không có background scan lớn gây nhiễu.
5. Ghi index plan.

Ví dụ:

```javascript
for (let i = 0; i < 20; i++) {
  const started = Date.now();

  db.orders.find({
    tenantId: "T1",
    status: "PAID"
  }).sort({
    createdAt: -1
  }).limit(20).toArray();

  print("elapsedMs=", Date.now() - started);
}
```

Đây là đo đơn giản bằng wall clock để minh họa, **không phải framework benchmark chính xác**. JavaScript runtime, network và client parsing cũng góp phần vào số đo.

### 32.2. Thí nghiệm B — đổi tập dữ liệu đọc

1. Dùng nhiều tenant/IDs khác nhau.
2. Chọn cả hot time range và cold history range.
3. Chạy dưới concurrency tương ứng workload.
4. Quan sát page reads và disk latency.
5. So sánh với warm repeated reads.

### 32.3. Không xóa OS page cache trên production

Những lệnh như `sync; echo 3 > /proc/sys/vm/drop_caches` thay đổi cache của toàn hệ thống và có thể gây latency spike nghiêm trọng. **Không dùng trên production** chỉ để đo cold cache. Với staging, vẫn phải được phép và hiểu tác động tới các processes khác.

### 32.4. Dữ liệu 100 documents không chứng minh performance ở 100 triệu documents

Một dataset nhỏ luôn vừa cache không tạo điều kiện để thấy disk reads/eviction của workload thật. Benchmark phải có quy mô và distribution có ý nghĩa.

---

## 33. Java Sync Driver: giảm số dữ liệu phải đọc

Ví dụ query tìm 20 đơn mới nhất của một tenant:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Date;

public final class OrderQueryRepository {

    public static void listRecentPaidOrders(
            MongoCollection<Document> orders,
            String tenantId,
            Date from
    ) {
        Bson filter = Filters.and(
            Filters.eq("tenantId", tenantId),
            Filters.eq("status", "PAID"),
            Filters.gte("createdAt", from)
        );

        orders.find(filter)
            .sort(Sorts.descending("createdAt"))
            .projection(
                Projections.fields(
                    Projections.include(
                        "tenantId",
                        "status",
                        "createdAt",
                        "totalMinor"
                    ),
                    Projections.excludeId()
                )
            )
            .limit(20)
            .maxTime(2, java.util.concurrent.TimeUnit.SECONDS)
            .forEach(doc ->
                System.out.println(doc.toJson())
            );
    }
}
```

### 33.1. Những điều code này làm được

- Giới hạn phạm vi theo tenant/status/time.
- Trả 20 documents thay vì mọi matches.
- Chỉ trả những fields cần thiết.
- Có server-side execution timeout giới hạn thời gian lệnh theo API phù hợp.

### 33.2. Những điều code này không tự làm được

- Không tạo index nếu index chưa có.
- Không đảm bảo query được covered.
- Không đảm bảo mọi lần chạy đều không đọc disk.
- Không biến query thành I/O-free khi pages lạnh.
- Không thay thế client-side timeout, connection pool và cancellation policy.

Cần có compound index phù hợp ở layer schema/migration và dùng `explain` để xác nhận execution plan.

---

## 34. Java: thực thi explain cho truy vấn

Ví dụ có thể chạy `explain()` trên FindIterable trong Java Sync Driver:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import com.mongodb.ExplainVerbosity;
import org.bson.Document;

public final class ExplainOrderQuery {

    public static void explain(
            MongoCollection<Document> orders,
            String tenantId
    ) {
        Document result = orders.find(
                Filters.eq("tenantId", tenantId)
            )
            .sort(Sorts.descending("createdAt"))
            .limit(20)
            .explain(ExplainVerbosity.EXECUTION_STATS);

        System.out.println(
            result.toJson()
        );
    }
}
```

`EXECUTION_STATS` cho biết metrics execution của query trên server. Đừng biến đoạn explain thành code chạy cho từng HTTP request: explain có overhead và số đo thay đổi theo load.

---

## 35. Java: phân biệt server latency với end-to-end latency

Một request có thể gồm:

```text
HTTP request
    |
    +-- authentication
    +-- application validation
    +-- connection pool wait
    +-- network to MongoDB
    +-- server query execution
    +-- MongoDB network response
    +-- BSON deserialization
    +-- business transformations
    +-- HTTP serialization
    v
HTTP response
```

Nếu `explain.executionTimeMillis` thấp nhưng HTTP p99 cao, nguyên nhân có thể ở connection pool, network, application CPU hoặc downstream services.

### 35.1. Một phép đo ứng dụng

```java
long started = System.nanoTime();

var results = orders.find(
        Filters.eq("tenantId", tenantId)
    )
    .limit(20)
    .into(new java.util.ArrayList<>());

long elapsedNanos =
    System.nanoTime() - started;

System.out.println(
    "DB call elapsedMs="
        + elapsedNanos / 1_000_000.0
);
```

Cách này bao gồm thời gian client-side cho lần gọi đó; không tự phân tách cache miss và disk I/O. Kết hợp tracing/driver metrics/serverStatus.

### 35.2. Chú ý connection pool wait

Nhiều requests có thể xếp hàng đợi connection pool dù server có cache khỏe. Khi đó thêm RAM cho MongoDB không xử lý được bottleneck ứng dụng.

---

## 36. Sizing RAM cho MongoDB: đừng lấy databaseSize rồi nhân đôi

Một kế hoạch sizing có thể bắt đầu bằng:

1. Dung lượng hiện tại của collections/indexes.
2. Tỷ lệ dữ liệu truy cập trong những cửa sổ thời gian.
3. Query patterns gây page reads.
4. Concurrency peak và intermediate memory.
5. WiredTiger cache configured size.
6. OS page cache và memory available.
7. Disk IO performance khi cache miss.
8. Dự báo tăng trưởng 6–12 tháng.
9. Yêu cầu p95/p99 latency.
10. Chi phí tăng RAM so với index/schema/archiving.

### 36.1. Ví dụ kiến trúc

```text
Physical RAM:             64 GiB
WT cache default:       ~31.5 GiB
OS/process headroom:      phần còn lại
Estimated hot pages:     ~22 GiB
Cold data:               500 GiB
```

Đây là workload **có thể chạy tốt** nếu hot pages thực sự gần 22 GiB và index/query tốt, dù cold data lớn hơn RAM nhiều.

Tình huống khác:

```text
Physical RAM:             64 GiB
Hot pages:                75 GiB
WT cache default:       ~31.5 GiB
Daily reports:            scans 300 GiB
```

Ở đây có thể có cache churn và disk reads; cần tối ưu access pattern/batch separation trước khi kết luận chỉ tăng RAM là đủ.

### 36.2. Memory sizing trên containers

Nếu MongoDB chạy trong container, cần kiểm tra:

- Cgroup memory limits được server nhận diện.
- WiredTiger cache default/effective config.
- OS page cache charge theo cgroup.
- Sidecars/agents cùng chia memory budget.
- OOM events.
- Kubernetes resource requests/limits và eviction policy.

Không đặt cache bằng toàn bộ container memory limit; MongoDB còn cần RAM ngoài WiredTiger cache.

---

## 37. Dung lượng dữ liệu tăng, nhưng working set có nhất thiết tăng?

Không.

Một ứng dụng lưu lịch sử đơn hàng tăng từ 100 GiB lên 1 TiB trong 3 năm, nhưng người dùng vẫn chủ yếu truy vấn 30 ngày gần đây; working set có thể tăng chậm hơn nhiều.

Ngược lại, một mô hình mới cho phép search mọi đơn hàng 5 năm và một dashboard bật auto-refresh có thể làm working set tăng đột ngột mà **database size không đổi**.

### 37.1. Những thay đổi thường làm working set tăng

- Thêm endpoint quét lịch sử.
- Thêm dashboard không filter thời gian.
- Tăng số tenants hoạt động đồng thời.
- Thêm indexes nhiều trang hot.
- Chuyển query sang lấy full documents.
- Bật nhiều report/batch jobs.
- Dùng regex không chọn lọc hoặc sort không có index.
- Tăng số records trong time window nóng.
- Chuyển từ truy cập theo nhóm sang random IDs trên toàn bộ data.

---

## 38. Archive cold data để giảm Working Set

Một phương án:

```text
orders_hot
  Last 90 days

orders_archive
  Older than 90 days
```

Hoặc giữ chung collection nhưng thiết kế partition/sharding/query patterns phù hợp.

### 38.1. Archive không chỉ là move documents

Cần đảm bảo:

- Chính sách retention và khả năng tra cứu lịch sử.
- Consistency của references.
- Indexes ở archive.
- Thời gian truy xuất chấp nhận được.
- Backup/restore của archive.
- Quyền truy cập và bảo vệ dữ liệu.
- Tránh mất dữ liệu trong quá trình move/delete.
- Audit và rollback.

### 38.2. Đừng áp TTL bừa bãi

TTL index có thể tự xóa dữ liệu cũ; đây là **data deletion**, không phải archive. Dữ liệu có yêu cầu giữ lâu không nên bị TTL xóa chỉ để giảm cache pressure.

### 38.3. Archiving chưa chắc giảm I/O nếu query vẫn quét archive

Nếu báo cáo mỗi giờ đọc cả `orders_hot` và `orders_archive` thì disk read vẫn xảy ra. Để giảm hot-path latency, cần **tách workloads hoặc thay data access strategy**, không chỉ đổi tên collection.

---

## 39. Sharding và Working Set

Sharding có thể giúp chia dữ liệu/traffic giữa nhiều shards:

```text
Application
    |
    v
  mongos
    |
    +--> shard A: local data/index/cache
    +--> shard B: local data/index/cache
    +--> shard C: local data/index/cache
```

Nếu queries được target tốt bằng shard key, mỗi shard xử lý tập dữ liệu nhỏ hơn, có tài nguyên riêng.

### 39.1. Không tự động giảm tổng I/O

Nếu query không có shard key và phải scatter-gather, nhiều shards có thể cùng đọc disk.

Một sharded cluster còn có:

- Shard key distribution.
- Hot chunks/uneven load.
- Cross-shard joins/aggregations.
- Balancer operations.
- Replication overhead.
- More operational cost.

Không shard chỉ để “mỗi index nhỏ hơn” khi có thể sửa query/index trong single replica set.

### 39.2. Hot shard

Nếu shard key khiến hầu hết writes/reads vào một shard, các shards khác có nhiều RAM rảnh cũng không giúp shard nóng. Chọn shard key theo workload và đo per-shard cache/disk metrics.

---

## 40. Read preference và secondaries

Một hệ có nhiều đọc có thể cấu hình một số queries sang secondary:

```javascript
db.orders.find({
  tenantId: "T1"
}).readPref("secondaryPreferred");
```

Đây là ví dụ syntax mongosh; chiến lược production phải xét semantics của driver/read preference đang dùng.

### 40.1. Lợi ích

- Có thể phân tải đọc.
- Có thêm WiredTiger cache và OS page cache của secondary.
- Giảm pressure lên primary cho các báo cáo phù hợp.

### 40.2. Đánh đổi

- Secondary có thể chậm replication.
- Stale reads có thể xảy ra.
- Báo cáo nặng làm secondary đọc disk nhiều, tăng lag.
- Query vẫn cần index phù hợp trên secondary.
- Một secondary quá tải có thể ảnh hưởng khả năng duy trì replication/availability.

Không tự chuyển các reads cần consistency ngay sau write sang secondary.

---

## 41. Cache warm-up sau restart/failover

Sau khi MongoDB restart, internal cache của process bắt đầu ở trạng thái chưa có đầy đủ hot pages; OS page cache có thể giữ hoặc mất dữ liệu tùy host/restart type.

### 41.1. Những tình huống

| Sự kiện | Có thể xảy ra |
| --- | --- |
| Restart `mongod` trên cùng host | WT cache mất; OS page cache có thể còn |
| Reboot cả máy | WT cache mất và OS page cache phải được nạp lại |
| Primary failover sang secondary đã có traffic | Secondary có thể có cache nóng khác primary |
| Failover sang node ít được đọc | Cần warm-up theo hot query patterns |
| Restore cluster mới | Cache thường lạnh; indexes/data cần được nạp khi có traffic |
| Initial sync hoàn tất | Không mặc định toàn bộ working set nóng |

### 41.2. Warm-up an toàn

- Đảm bảo indexes đã sẵn sàng.
- Dùng gradual traffic ramp-up nếu kiến trúc hỗ trợ.
- Pre-warm có chọn lọc bằng các **read-only queries đại diện**, khi đã benchmark.
- Hạn chế batch scans cùng lúc với failover.
- Theo dõi disk read IOPS và p95/p99.

### 41.3. Đừng quét toàn bộ database để “nạp cache”

Nếu hot working set chỉ 20 GiB nhưng database 1 TiB, full scan sẽ nạp nhiều cold pages và có thể đẩy hot pages ra; rất dễ phản tác dụng.

---

## 42. Disk I/O sau khi tạo index

Tạo index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1
});
```

là một hoạt động có thể:

- Quét collection.
- Đọc nhiều data pages lạnh.
- Dùng memory/CPU cho index build.
- Ghi index pages.
- Tạo I/O và latency pressure trong quá trình build.

### 42.1. Hiệu ứng dài hạn

Sau index build, query tương ứng có thể đọc ít dữ liệu hơn, giảm cache churn lâu dài.

Nhưng **during build** có thể xuất hiện disk read/write spikes. Lên lịch và theo dõi khi tạo index lớn trên production.

### 42.2. Không dùng reIndex như một “cache reset”

Xây lại index tốn tài nguyên, làm I/O lớn và không tự tối ưu query shape sai. Chỉ thực hiện theo maintenance/repair requirements được hỗ trợ, không như mẹo tăng tốc thường xuyên.

---

## 43. Disk spills khác với đọc từ collection

Một truy vấn:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T1" } },
  { $sort: { totalMinor: -1 } },
  { $limit: 100 }
], {
  allowDiskUse: true
});
```

có thể phát sinh:

- Data/index page reads.
- Intermediate sort memory.
- Disk spill nếu sort không dùng index và memory vượt giới hạn theo cơ chế server.

### 43.1. Vì sao phải phân biệt?

Nếu Disk Write IOPS tăng do sort spill, việc tăng WiredTiger cache có thể không giải quyết nguyên nhân. Cần:

- Tạo index hỗ trợ sort.
- Lọc data trước khi sort.
- Giảm cardinality.
- Xem xét precomputed ranking hoặc pagination.
- Điều chỉnh aggregation pattern.

### 43.2. Temporary files vẫn dùng storage

Disk spills có thể nằm trên đường storage của MongoDB và cạnh tranh tài nguyên với page reads/checkpoints. Không giả định temp disk I/O tách hoàn toàn khỏi database storage nếu chưa kiểm tra deployment.

---

## 44. Đọc nhiều dữ liệu nhỏ: N+1 query problem

Một backend:

```text
1 request lấy 100 orders
  -> query 100 orders
  -> với mỗi order, query thêm customer
  -> với mỗi order, query thêm shipping info

Tổng ~201 queries / HTTP request
```

Ngay cả khi từng query dùng index, nhiều round trips và nhiều random page lookups có thể làm latency cao.

### 44.1. Hướng cải thiện

- Batch fetch bằng `$in` với bounds hợp lý.
- Thiết kế embedded documents cho dữ liệu thường đọc cùng nhau, nếu cập nhật/size semantics phù hợp.
- `$lookup` có index và data distribution hợp lý.
- Materialized read model nếu domain phù hợp.
- Connection pool và request parallelism có kiểm soát.

**Mục tiêu:** giảm số disk/index/document pages và network round trips cần thiết để phục vụ một tác vụ nghiệp vụ.

---

## 45. Đọc document lớn khi chỉ cần một field nhỏ

Giả sử document:

```javascript
{
  _id: "DOC-100",
  title: "Large contract",
  status: "READY",
  body: "very long text...",
  attachments: [ /* large embedded payloads */ ]
}
```

API list chỉ cần `title` và `status`. Nếu body/payload rất lớn nằm chung document, có thể tốn chi phí đọc và materialize nhiều dữ liệu.

### 45.1. Tách metadata và payload khi phù hợp

```javascript
// documents
{
  _id: "DOC-100",
  title: "Large contract",
  status: "READY",
  contentId: "CONT-100"
}

// documentContents
{
  _id: "CONT-100",
  body: "very long text..."
}
```

Ưu điểm:

- List API không động đến content collection.
- Hot document pages nhỏ hơn nếu access paths phù hợp.
- Content chỉ đọc khi người dùng mở chi tiết.

Đánh đổi:

- Thêm query/lookup khi cần full content.
- Consistency giữa hai collections.
- Schema/migration complexity.
- Transaction hoặc application-level workflow cho updates.

Không tách mọi field thành collection riêng: có thể tạo N+1 queries và làm access locality tệ đi.

---

## 46. Những trường hợp tăng RAM có hiệu quả

Tăng RAM thường đáng cân nhắc nếu:

1. Hot working set vượt cache capacity và gây repeated evictions.
2. Query/index plans đã tối ưu.
3. Disk reads và latency tăng tương quan với cache pressure.
4. Không có memory leak/swap/OS pressure không liên quan.
5. Có budget và downtime/resize plan.
6. Sau khi tăng RAM, dự báo hit rate/IOPS/latency cải thiện đáng kể.

### 46.1. Tăng RAM có thể không giúp khi nào?

- Query CPU-bound.
- Storage latency cao do checkpoint/write load chứ không phải read misses.
- Network/connection pool bottleneck.
- Index thiếu, query scan gần toàn bộ data mỗi lần.
- Báo cáo quét tập lịch sử lớn hơn mọi mức cache thực tế.
- Hot shard phân bố không cân bằng.
- Query không được target nên quét nhiều shards.
- Dữ liệu được export/serialized quá lớn.

### 46.2. Tăng cacheSizeGB khác tăng RAM host

Đặt `cacheSizeGB` cao hơn trên cùng RAM có thể làm OS page cache và các components khác thiếu chỗ. Nâng RAM host mà vẫn để WiredTiger cache theo default có thể tăng cả internal cache lẫn headroom.

---

## 47. Quy trình điều tra khi latency tăng: một playbook

### Pha A — Đặt câu hỏi đúng

1. Endpoint nào chậm?
2. Chậm từ lúc nào?
3. p50 hay chỉ p99 tăng?
4. Chỉ một tenant hay nhiều tenant?
5. Chậm sau failover/restart hay sau một batch job?
6. Có deployment/index/data growth thay đổi gì gần đây?

### Pha B — Nhìn query

7. Tìm query shape trong profiler/slow query logs.
8. Xem `explain("executionStats")`.
9. Tìm `COLLSCAN`, `SORT`, lượng keys/docs examined.
10. Kiểm tra indexes và projection.
11. Xác định data range hot/cold.

### Pha C — Nhìn cache và disk

12. WiredTiger current/max bytes.
13. Dirty pages và eviction counters/rates.
14. Pages read into cache theo delta.
15. OS memory available/swap/page faults.
16. Disk read IOPS/throughput/latency.
17. Disk write IOPS/checkpoint/storage queue.
18. Background jobs/backup/index builds.

### Pha D — Chọn can thiệp theo giả thuyết

19. Query đọc quá rộng → sửa filter/index.
20. Query có nhiều FETCH → thử covered projection/index.
21. Batch scan đẩy hot pages → tách/giãn batch.
22. Hot working set quá lớn → tăng RAM/archive/tách workload.
23. Disk bão hòa dù query hợp lý → nâng IOPS/throughput/SSD.
24. Aggregation spill → index/sort/precompute.
25. Primary failover cache lạnh → traffic warm-up có kiểm soát.

### Pha E — Xác nhận kết quả

26. Đo cùng query/workload trước và sau.
27. So p50/p95/p99, docs examined, disk IOPS và eviction.
28. Kiểm tra write latency/replication lag không xấu đi.
29. Ghi lại thay đổi và rollback plan.
30. Theo dõi ít nhất qua một chu kỳ peak traffic.

---

## 48. Ví dụ tình huống A — index thiếu gây disk reads

**Hiện tượng:**

```text
Query p95:              450 ms
nReturned:                20
docsExamined:        800,000
Disk read IOPS:        15,000
WT pages read rate:     cao
```

**Giả thuyết:** query scan dữ liệu không cần thiết.

**Cách xử lý:**

- Xác định filter/sort.
- Tạo compound index phù hợp.
- Chạy explain lại.
- So sánh latency và disk read rates.

**Kết quả mong đợi:** giảm candidate documents/data pages, chưa cần tăng RAM.

**Không chắc chắn:** kết quả thực phụ thuộc selectivity, cache state và query plan.

---

## 49. Ví dụ tình huống B — cache pollution bởi báo cáo

**Hiện tượng:**

```text
07:00 Web p95:            18 ms
07:30 Analytics starts
07:35 Disk Read IOPS:      tăng
07:40 Eviction rate:       tăng
07:45 Web p95:           180 ms
08:15 Analytics ends
08:30 Web p95:            23 ms
```

**Giả thuyết:** scan lịch sử thay thế nhiều hot pages.

**Cách xử lý:**

- Schedule batch vào off-peak.
- Thêm filter/index theo range.
- Dùng pre-aggregate report.
- Cân nhắc secondary/reporting deployment phù hợp.
- Thử incremental processing.

**Không nên:** tăng cache vô hạn để chứa toàn bộ lịch sử khi các request web chỉ cần dữ liệu nóng.

---

## 50. Ví dụ tình huống C — slow disk sau resize

**Hiện tượng:**

```text
Query docsExamined: tương tự trước
WiredTiger cache usage: ổn định
Disk latency: tăng từ ~1ms lên ~20ms
Cloud burst credits: cạn
Request p99: tăng rõ
```

**Giả thuyết:** storage bị giới hạn IOPS/throughput hoặc credits.

**Cách xử lý:**

- Kiểm tra volume metrics/provisioning.
- Xác minh instance throughput cap.
- Điều chỉnh IOPS/throughput hoặc tier theo provider.
- Giảm bursty workloads.
- So sánh physical read sizes và queue depth.

**Không nên:** thêm một index không liên quan chỉ vì query chậm.

---

## 51. Ví dụ tình huống D — replica set failover

**Hiện tượng:**

```text
Primary A warm, p95 = 15 ms
Failover to B
New primary B, p95 = 140 ms for 5 minutes
Read IOPS spike rồi giảm
```

**Giả thuyết:** B không có cùng hot pages trong internal/OS cache; workload đang warm-up.

**Cách xử lý:**

- Đo cache/disk metrics trên từng node.
- Kiểm tra B có đủ RAM/disk giống A không.
- Có traffic ramp-up phù hợp.
- Kiểm tra failover health, replication history.
- Không tăng cache size dựa trên một spike ngắn duy nhất.

**Đánh đổi:** failover luôn cần đáp ứng availability trước, sau đó tối ưu tail latency.

---

## 52. Bài tập thực hành có lời giải

### Bài 1 — Total size và working set

Database 2 TiB nhưng hot traffic chỉ cần recent documents/index pages khoảng 20 GiB.

**Hỏi:** Có bắt buộc RAM hơn 2 TiB?

**Đáp án:** Không. Nếu working set và hệ thống cache đủ sức chứa hot pages, cold data vẫn có thể nằm trên disk.

### Bài 2 — Cache đầy

WiredTiger cache đang dùng 92%, nhưng p99 ổn định và disk read IOPS thấp.

**Hỏi:** Có nên tăng RAM ngay?

**Đáp án:** Không có bằng chứng đủ. Cache được thiết kế để sử dụng; phải xem eviction, page reads, latency và memory pressure.

### Bài 3 — Cache miss ở WiredTiger

Một page không có trong WT cache nhưng vẫn có trong OS page cache.

**Hỏi:** Có nhất thiết đọc SSD không?

**Đáp án:** Không. OS page cache có thể phục vụ từ RAM.

### Bài 4 — FETCH

Explain hiển thị `FETCH` sau `IXSCAN`.

**Hỏi:** Nó có bằng chứng một physical disk read không?

**Đáp án:** Không. `FETCH` nghĩa là lấy document, document có thể resident trong cache.

### Bài 5 — Disk read và projection

Một query trả 5 fields thay vì 50 fields nhưng vẫn phải fetch same pages.

**Hỏi:** Disk reads chắc chắn giảm 10 lần?

**Đáp án:** Không. Projection giảm response/serialization, không trực tiếp bảo đảm giảm physical I/O; covered query mới có thể tránh fetch.

### Bài 6 — Query targeting

`nReturned=20`, `docsExamined=1.000.000`.

**Hỏi:** Cần điều tra gì?

**Đáp án:** Filter selectivity, index, sort và truy vấn scan quá rộng.

### Bài 7 — Cumulative counter

Pages read vào cache tăng từ 20.000 lên 26.000 trong 60 giây.

**Hỏi:** Rate trung bình?

**Đáp án:** `(26000 - 20000)/60 = 100 pages/s`.

### Bài 8 — Page faults

OS report 50.000 minor page faults.

**Hỏi:** Có thể kết luận 50.000 SSD reads?

**Đáp án:** Không. Minor faults thường không yêu cầu physical disk I/O.

### Bài 9 — Disk throughput

Volume xử lý 10.000 IOPS với average 4 KiB/request.

**Hỏi:** Throughput xấp xỉ?

**Đáp án:** 39.1 MiB/s.

### Bài 10 — Random I/O

Query tìm 10.000 documents rải rác trong collection.

**Hỏi:** Vì sao SSD có thể quan trọng hơn HDD?

**Đáp án:** Random I/O latency/IOPS, tránh seek time cơ học.

### Bài 11 — Aggregation spill

`$sort` ghi dữ liệu tạm ra disk.

**Hỏi:** Tăng WiredTiger cache có chắc giải quyết?

**Đáp án:** Không. Cần tối ưu sort/index/aggregation memory và workload.

### Bài 12 — Dirty pages

Dirty bytes trong WT cache tăng cùng Disk Write IOPS.

**Hỏi:** Có nghĩa read misses là nguyên nhân duy nhất?

**Đáp án:** Không. Checkpoint/eviction/write workload cũng gây disk pressure.

### Bài 13 — Hot dataset và index

Collection 500 GiB nhưng hot queries dùng index 2 GiB và 5 GiB hot documents.

**Hỏi:** Vấn đề cần đo gì trước khi tăng RAM?

**Đáp án:** Resident pages, eviction, cache read rate, disk I/O và p95/p99.

### Bài 14 — Linux free

`free -h` cho thấy `free` gần 0 nhưng `available` cao và cache lớn.

**Đáp án:** Đây có thể bình thường; Linux tận dụng RAM cho page cache.

### Bài 15 — Covered query

Query có index chứa filter/projection nhưng mặc định vẫn trả `_id` không nằm trong index.

**Hỏi:** Vì sao có thể phải FETCH?

**Đáp án:** Projection bao gồm `_id`; có thể chủ động `_id:0` nếu không cần.

### Bài 16 — Tenant hotness

Chỉ tenant T1 chiếm 90% traffic, queries trên mọi shards.

**Hỏi:** Cần xem gì?

**Đáp án:** Shard key targeting, hot shard, query filters và per-shard cache/disk metrics.

### Bài 17 — Cache warm-up sau reboot

Disk Read IOPS tăng sau khi reboot rồi giảm.

**Đáp án:** OS page cache và WT internal cache đang được nạp lại; cần phân biệt spike warm-up với bottleneck kéo dài.

### Bài 18 — Full scan để warm cache

Một nhóm chạy full collection scan 1 TiB để warm cache 16 GiB.

**Đáp án:** Có thể phản tác dụng vì đẩy hot pages ra; nên dùng representative hot queries.

### Bài 19 — Tăng RAM trên cùng VM

Team tăng `cacheSizeGB` từ 8 lên 14 GiB trên VM có 16 GiB RAM.

**Đáp án:** Rủi ro thiếu OS/page cache và memory ngoài WiredTiger; cần sizing toàn host.

### Bài 20 — Lựa chọn tối ưu

Query `COLLSCAN` trên collection 10 documents mất 1 ms.

**Hỏi:** Có cần tạo index ngay?

**Đáp án:** Chưa chắc. Small collection scan có thể hợp lý; thêm index cũng có write/storage cost.

### Bài 21 — Slow after import

Một import 100 GiB hoàn tất, web queries chậm trong thời gian ngắn.

**Đáp án:** Có thể có cache churn, checkpoints, I/O backlog; đối chiếu metrics timeline.

### Bài 22 — Delete history

Team muốn TTL xóa lịch sử hợp đồng chỉ để tăng cache hit.

**Đáp án:** Không áp TTL nếu retention/legal requirements yêu cầu giữ. Cân nhắc archive và query separation.

### Bài 23 — Secondary reads

Chuyển báo cáo sang secondary, secondary replication lag tăng.

**Đáp án:** Reporting I/O có thể tranh tài nguyên với replication; cần giới hạn/tách workload hoặc tăng capacity.

### Bài 24 — Query faster after warm-up

Một query chạy 500 ms lần đầu, 20 ms lần hai.

**Đáp án:** Có thể do cache warm-up, cũng có CPU/query plan khác; kiểm tra I/O và cùng điều kiện benchmark.

---

## 53. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Tổng database lớn hơn RAM là MongoDB sẽ luôn chậm.” | Hot working set mới là yếu tố chính của cache locality. |
| “Working set = storageSize của toàn bộ collection.” | Working set phụ thuộc truy cập thực. |
| “Chỉ document pages mới chiếm cache.” | Index pages cũng cần cache. |
| “WiredTiger cache và OS page cache là một.” | Hai tầng khác nhau, cùng sử dụng RAM host. |
| “WT page read luôn là SSD read.” | OS page cache có thể phục vụ. |
| “Cache 95% là memory leak.” | Cache được thiết kế để dùng RAM, cần xét eviction/latency. |
| “RAM free thấp đồng nghĩa thiếu RAM.” | OS page cache có thể chiếm RAM có thể thu hồi. |
| “FETCH nghĩa là disk read.” | FETCH cần document, có thể đã ở memory. |
| “IXSCAN luôn nhanh hơn COLLSCAN.” | Phụ thuộc selectivity, access pattern và số documents. |
| “Có index là query không đọc document pages.” | Không nếu cần fetch ngoài index. |
| “Projection ít fields giảm disk reads theo tỷ lệ.” | Chỉ chắc chắn giảm response size; physical I/O cần kiểm chứng. |
| “Tạo càng nhiều index càng nhanh.” | Index tăng storage/cache/write cost. |
| “Tăng cacheSizeGB bằng toàn bộ RAM sẽ tốt.” | Có thể ép OS/queries vào memory pressure/OOM. |
| “Disk read cao luôn do ứng dụng web.” | Backup, index build, reports cũng gây I/O. |
| “Page fault đồng nghĩa storage I/O.” | Minor faults thường không. |
| “IOPS cao nghĩa disk chậm.” | Cần xem latency, queue và capacity. |
| “Throughput MB/s cao là random I/O tốt.” | IOPS/latency còn quan trọng. |
| “Tăng SSD sửa truy vấn quét quá nhiều documents.” | Chỉ giảm chi phí mỗi I/O, không sửa access path. |
| “allowDiskUse giúp aggregation nhanh hơn.” | Có thể phát sinh disk spill và chậm hơn. |
| “RTO restore không liên quan cache.” | Restored node có thể cache lạnh và cần warm-up. |
| “Thêm RAM luôn hạ p99.” | Không nếu bottleneck CPU, network hoặc query shape. |
| “Sharding tự giảm mọi query latency.” | Scatter-gather/hot shards có thể làm tệ hơn. |
| “Đọc secondary không ảnh hưởng replication.” | Reporting workload có thể cạnh tranh resources. |
| “Quét toàn bộ data là cách warm cache tốt.” | Có thể đẩy hot pages ra. |
| “Counter tích lũy lớn là lỗi đang xảy ra.” | Cần tính delta/rate và xét restart. |
| “Explain cho biết physical disk I/O của từng FETCH.” | Phải đối chiếu storage metrics. |
| “Một benchmark lặp cùng _id đủ kết luận production.” | Cần hot/cold, concurrency và distribution. |
| “Tắt journal/giảm write concern để xử lý read latency.” | Đánh đổi durability và không giải quyết access pattern. |
| “Archive là xóa dữ liệu cũ.” | Archive phải đảm bảo retention và khả năng truy xuất. |
| “TTL là công cụ tối ưu working set vô hại.” | TTL xóa dữ liệu thực, có nguy cơ nghiệp vụ. |

---

## 54. Checklist trước khi tối ưu hiệu năng đọc

1. [ ] Xác định query shape/endpoint gây latency.
2. [ ] Đã xem `explain("executionStats")`?
3. [ ] Có scan quá nhiều keys/docs không?
4. [ ] Chỉ mục có hỗ trợ filter/sort phù hợp?
5. [ ] Projection có thể được cover không?
6. [ ] Working set được ước lượng bằng access patterns chứ không chỉ database size?
7. [ ] Đã tính hot index pages?
8. [ ] WiredTiger cache max/current bytes đúng theo runtime?
9. [ ] Dirty pages/eviction có tăng bất thường?
10. [ ] Đã tính delta pages read into cache?
11. [ ] Đã xem OS page cache và memory available?
12. [ ] Có swap/OOM/memory pressure?
13. [ ] Disk Read IOPS và throughput có chạm giới hạn?
14. [ ] Disk read latency/queue có tăng lúc p99 tăng?
15. [ ] Write IOPS/checkpoint có tranh tài nguyên?
16. [ ] Có batch scan/index build/backup cùng thời điểm?
17. [ ] Có aggregation spill?
18. [ ] Query có dùng quá nhiều BSON bytes hoặc document fields?
19. [ ] Có N+1 queries hoặc network round trips quá nhiều?
20. [ ] Có khả năng phân tách analytics/reporting không?
21. [ ] Có data cold để archive nhưng vẫn đúng retention?
22. [ ] Sharded cluster có hot shard/scatter-gather không?
23. [ ] Read preference có chấp nhận stale reads và replication lag không?
24. [ ] Sau restart/failover có cache warm-up effect?
25. [ ] Tăng RAM có thực sự giảm repeated cold page reads?
26. [ ] Nâng storage có xử lý đúng IOPS/latency bottleneck?
27. [ ] Đã đo p50/p95/p99 ở tải đại diện?
28. [ ] Có benchmark trước/sau và rollback plan?
29. [ ] Có tránh thao tác phá cache trên production?
30. [ ] Có monitoring trends để phát hiện working set tăng theo sản phẩm/dữ liệu?

---

## 55. Tài liệu chính thức và nguồn học

- [MongoDB — WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/): kiến trúc storage engine, compression và concurrency.
- [MongoDB — WiredTiger Memory Use](https://www.mongodb.com/docs/manual/core/wiredtiger/#memory-use): cache sizing và interplay với OS cache.
- [MongoDB — Configuration Options](https://www.mongodb.com/docs/manual/reference/configuration-options/#mongodb-setting-storage.wiredTiger.engineConfig.cacheSizeGB): cấu hình WiredTiger cache.
- [MongoDB — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/): metrics cho cache/memory/storage engine.
- [MongoDB — Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/): query planner và index selection.
- [MongoDB — explain](https://www.mongodb.com/docs/manual/reference/explain-results/): executionStats, keys/docs examined và stage semantics.
- [MongoDB — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/#covered-queries): index-only retrieval và projection.
- [MongoDB — Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/): chọn index theo query.
- [MongoDB — Analyze Query Performance](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/): chạy và diễn giải explain.
- [MongoDB — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/): memory limits và disk spill.
- [MongoDB — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/): thu thập query execution metrics có overhead.
- [MongoDB Atlas — Review MongoDB Metrics](https://www.mongodb.com/docs/atlas/review-available-metrics/): chart cache, CPU, disk và operations.
- [MongoDB — Operational Factors and Data Access Patterns](https://www.mongodb.com/docs/manual/administration/production-notes/): filesystem/storage/production considerations.
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/): find, projection, sort và limit.
- [MongoDB Java Sync Driver — Explain](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/explain/): dùng explain để xem execution plan.

**Lưu ý phiên bản:** tên WiredTiger metrics, behavior query planner, aggregation spill defaults, Atlas monitoring charts và hỗ trợ container memory sizing có thể thay đổi theo MongoDB Server, FCV, driver và platform. Đối chiếu đúng phiên bản của hệ thống trước khi thay configuration production.

## 56. Kết luận

**Working set** là tập dữ liệu và chỉ mục được sử dụng lặp lại, không phải toàn bộ database. Với MongoDB WiredTiger, các trang được cache ở tầng **WiredTiger internal cache** và có thể tiếp tục được phục vụ bởi **OS page cache** trước khi cần đến SSD/cloud storage.

**Disk reads** thường tốn thời gian hơn memory accesses và có thể làm tăng **p95/p99 latency**, đặc biệt khi random I/O, queue depth và storage saturation tăng. Nhưng WiredTiger cache miss không luôn tương đương physical disk read, và `FETCH` trong explain cũng không tự chứng minh đã đọc disk.

Để tối ưu có cơ sở: **xem query plans và docs/keys examined, xác định hot data/index pages, theo dõi WiredTiger cache/evictions cùng disk I/O, rồi sửa access paths**. Tăng RAM, IOPS, SSD, sharding hoặc archive chỉ nên thực hiện khi metrics cho thấy chúng giải quyết đúng bottleneck.

Một hệ thống MongoDB có hàng terabytes dữ liệu vẫn có thể trả truy vấn rất nhanh nếu workload tập trung, chỉ mục tốt và working set nóng vừa cache. Ngược lại một collection nhỏ cũng có thể chậm nếu query thiết kế sai, storage bị bão hòa hoặc workload cạnh tranh tài nguyên.

**Không tối ưu chỉ để cache “đầy ít hơn” hay disk “đọc ít hơn” trên một chart; hãy tối ưu để các truy vấn quan trọng đọc đúng dữ liệu, tránh I/O không cần thiết và đáp ứng mục tiêu độ trễ thực tế.**
