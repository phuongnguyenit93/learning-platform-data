# JVM heap, GC và nguy cơ tranh chấp bộ nhớ với page cache

Kafka broker dùng bộ nhớ ở nhiều lớp. Java heap chứa object do JVM quản lý; native memory chứa direct buffer, thread stack, metaspace và các vùng runtime khác; còn hệ điều hành dùng RAM làm page cache để giữ các log segment và index vừa đọc hoặc ghi. Các vùng này cùng tiêu thụ RAM vật lý của host hoặc memory limit của container.

Vì vậy, tăng heap không tự động làm broker nhanh hơn. Heap quá nhỏ có thể khiến garbage collection (GC) chạy liên tục và tạo pause; heap quá lớn có thể làm giảm RAM còn lại cho page cache, khiến các lần đọc log phải xuống disk thường xuyên hơn. Bài học này tập trung vào cách cân bằng hai nhu cầu đó, đo đúng từng loại memory và điều chỉnh theo workload thực tế.

Trong hệ thống KAFKA, các topic được chia thành partition và lưu record theo offset; producer ghi dữ liệu, consumer group đọc dữ liệu, còn replication giữ bản sao giữa các broker. KRaft quản lý metadata của cluster. Dù ứng dụng Java/Spring Kafka, Kafka Connect hay Kafka Streams tạo ra workload, broker vẫn phải xử lý request, lưu log và phục vụ replica. Heap, GC và page cache vì thế ảnh hưởng trực tiếp đến latency, throughput và khả năng theo kịp dữ liệu của toàn hệ thống.

## 1. Bức tranh bộ nhớ của Kafka broker

Kafka được viết bằng Java nhưng dữ liệu log không được giữ toàn bộ trong Java heap. Broker ghi log vào file của hệ điều hành. Linux dùng page cache để cache các trang file, nhờ đó lần đọc sau có thể lấy dữ liệu từ RAM thay vì storage.

Một broker thường tiêu thụ bộ nhớ qua các nhóm sau:

| Nhóm | Nội dung | Được quản lý bởi |
|---|---|---|
| Java heap | Object, request state, metadata và object tạm của broker | JVM garbage collector |
| JVM non-heap | Metaspace, code cache và dữ liệu runtime | JVM |
| Native memory | Direct buffer, thread stack, native library, TLS/compression và vùng cấp phát ngoài heap | JVM, thư viện native và OS |
| File-backed page cache | Nội dung log segment, index và file được truy cập gần đây | Linux kernel |
| Kernel memory | Socket buffer, slab, page table và cấu trúc kernel | Linux kernel |

Không nên đồng nhất Java heap với tổng RAM của process. Cũng không nên cộng toàn bộ kích thước file log với heap để ra memory cần cấp: page cache là cache động, không phải bản sao cố định của toàn bộ dữ liệu lưu trữ.

### 1.1. Mối quan hệ giữa heap và page cache

~~~mermaid
flowchart TB
    RAM[RAM vật lý / memory limit]
    RAM --> JVM[JVM process]
    RAM --> OS[Linux kernel]
    JVM --> HEAP[Java heap]
    JVM --> NATIVE[Native và non-heap memory]
    OS --> CACHE[File page cache]
    OS --> KERNEL[Kernel memory và socket buffers]
    CACHE --> LOG[Kafka log segments và indexes]
    HEAP --> GC[GC quản lý object và thu hồi heap]
    GC --> PAUSE[GC pause / CPU cost]
    CACHE --> HIT[Page-cache hit: đọc từ RAM]
    CACHE --> MISS[Page-cache miss: đọc từ storage]
    MISS --> IO[Disk I/O và read latency]
~~~

Heap và page cache không chia sẻ cùng một bộ cấp phát, nhưng cùng cạnh tranh RAM vật lý. Khi process commit và chạm nhiều trang heap hơn, lượng anonymous memory tăng. Nếu host hoặc cgroup chịu áp lực memory, kernel có thể reclaim file cache. Nếu phần dữ liệu bị reclaim lại là working set nóng của Kafka, broker sẽ phải đọc lại từ storage.

Ở chiều ngược lại, nếu heap quá nhỏ, broker có thể tạo nhiều object ngắn hạn, tăng allocation rate, GC CPU và pause. GC pause làm request handler tạm ngừng, khiến Produce/Fetch latency và request queue tăng.

### 1.2. Page cache không phải cache riêng của Kafka

Page cache do Linux quản lý và được dùng chung với các process khác. Kafka không cần tự nạp toàn bộ log vào Java object để phục vụ consumer. Khi đọc log segment, kernel có thể trả dữ liệu từ page cache; nếu page chưa có trong RAM thì phải đọc từ storage.

Page cache có thể được reclaim khi hệ điều hành cần RAM. Việc RAM trống thấp không nhất thiết là dấu hiệu thiếu memory: Linux thường dùng RAM nhàn rỗi để cache file. Cần quan sát MemAvailable, memory pressure, swap, page-cache hit/miss gián tiếp qua I/O latency và tình trạng cgroup thay vì chỉ nhìn cột free.

### 1.3. Vì sao page cache quan trọng với Kafka?

Kafka là hệ thống log append-only. Việc ghi dữ liệu tuần tự vào file, kết hợp với page cache và cơ chế flush của OS, giúp tận dụng hiệu quả storage. Với consumer đọc dữ liệu gần đây, log segment thường còn trong page cache. Với consumer đọc lại dữ liệu cũ hoặc workload replay, cache miss có thể khiến storage trở thành nút thắt.

Page cache hỗ trợ:
- Giữ lại các block log được truy cập thường xuyên.
- Gộp các thao tác ghi nhỏ thành I/O lớn hơn.
- Cho phép kernel sắp xếp và flush ghi theo chính sách của hệ điều hành.
- Hỗ trợ đọc file hiệu quả mà không cần giữ toàn bộ payload trong Java heap.

Kafka có thể tận dụng sendfile/zero-copy trong đường truyền file tới socket ở các trường hợp phù hợp. Điều này giảm một số lần copy qua user space, nhưng không làm mất nhu cầu RAM cho page cache, socket buffer và các cấu trúc request.

## 2. Heap, non-heap và native memory trong JVM

### 2.1. Java heap

Java heap là vùng chứa object được tạo bởi ứng dụng và thư viện Java. Garbage collector theo dõi object còn reachable và thu hồi vùng nhớ của object không còn được sử dụng.

Ở mức cấu hình:
- **-Xms** đặt kích thước heap ban đầu.
- **-Xmx** đặt giới hạn heap tối đa.
- **Heap used** là phần heap đang được object sử dụng.
- **Heap committed** là phần heap JVM đã cam kết với hệ điều hành.
- **Heap max** là giới hạn tối đa JVM có thể sử dụng.

Các số liệu used, committed và max không giống nhau. Ví dụ, một JVM có Xmx 8 GiB nhưng tại thời điểm đo chỉ dùng 3 GiB heap. RSS của process vẫn có thể cao hơn nhiều do non-heap, native memory, mapped pages và các vùng khác.

### 2.2. Non-heap memory

Non-heap memory thường gồm:
- Metaspace: metadata của class.
- Compressed class space trên các cấu hình JVM sử dụng compressed class pointers.
- Code cache: mã máy do JIT compiler sinh ra.
- Một số cấu trúc runtime và GC.

Metaspace không nằm trong Java heap. Nếu classloader tạo class liên tục hoặc classloader không được giải phóng, metaspace có thể tăng dù heap used không tăng tương ứng.

### 2.3. Native memory và direct buffer

Native memory là vùng cấp phát ngoài Java heap. Các thành phần có thể tiêu thụ native memory gồm:
- Direct ByteBuffer và network buffer.
- Thread stack của từng thread.
- JVM compiler, GC metadata và internal structures.
- TLS, compression và các thư viện native.
- Memory mapping và một số vùng phục vụ I/O.

Direct buffer giúp một số thao tác I/O tránh copy dữ liệu qua heap, nhưng bộ nhớ direct vẫn tiêu thụ RAM và phải được tính vào memory budget. Giới hạn direct memory có thể được điều khiển bằng -XX:MaxDirectMemorySize; chỉ đặt giới hạn sau khi đã đo nhu cầu thực tế và hiểu cách các client/library cấp buffer.

Thread stack cũng quan trọng. Nếu broker có nhiều thread và mỗi thread có stack lớn, tổng native memory có thể đáng kể. Tăng số network/request/replica threads có thể làm tăng memory footprint dù heap không đổi.

### 2.4. RSS không bằng Xmx

RSS (Resident Set Size) là số trang của process đang cư trú trong RAM. RSS có thể bao gồm:
- Trang heap đã được chạm.
- Metaspace, code cache và native allocations.
- Thread stacks.
- Một số file-backed mapped pages.

RSS không phải tổng page cache của toàn bộ Kafka log directory. Page cache có thể được tính ở cấp host/cgroup và chia sẻ bởi nhiều process. Vì vậy, một broker có Xmx 8 GiB không có nghĩa process chỉ dùng 8 GiB RAM; và một node có page cache lớn không có nghĩa toàn bộ cache đó thuộc riêng JVM process.

## 3. Garbage collection và tác động tới broker

GC thu hồi object không còn reachable để tái sử dụng heap. Quá trình này tiêu tốn CPU và đôi khi tạm dừng application threads.

### 3.1. Allocation rate và object lifetime

Mỗi request Produce/Fetch có thể tạo object cho header, request metadata, record batch, buffer wrapper, callback, metrics và các cấu trúc tạm khác. Phần lớn object ngắn hạn được thu hồi trong young generation.

Hai yếu tố cần quan sát:
- **Allocation rate:** tốc độ JVM tạo object mới.
- **Live set:** lượng object vẫn còn reachable sau khi GC.

Allocation rate cao không nhất thiết là memory leak. Nếu object sống ngắn và GC thu hồi nhanh, broker vẫn có thể hoạt động tốt. Nếu nhiều object tồn tại lâu, chúng được promote sang old generation và làm tăng chi phí thu hồi.

### 3.2. Young GC, mixed GC và Full GC

Với G1:
- Young collection thu hồi các vùng young generation.
- Concurrent marking đánh dấu object sống trong old generation trong khi ứng dụng vẫn chạy ở nhiều giai đoạn.
- Mixed collection thu hồi một số vùng young và old.
- Full GC là tình huống nghiêm trọng hơn, thường cần nhiều công việc stop-the-world và có thể gây pause dài.

Full GC thường xuất hiện khi heap quá đầy, concurrent marking không kịp hoàn thành, có nhiều allocation lớn hoặc heap bị phân mảnh. Cần xem GC log để xác định nguyên nhân thay vì chỉ tăng Xmx.

### 3.3. GC pause ảnh hưởng Kafka thế nào?

Trong stop-the-world pause, các Java application threads bị dừng. Đối với broker, điều này có thể làm:
- Request handler không xử lý request trong khoảng pause.
- Produce/Fetch latency tăng đột biến.
- Request queue và thời gian chờ tăng.
- Replica fetch chậm, làm replication lag tăng.
- Consumer quan sát thấy throughput giảm hoặc lag tăng.
- Broker phản hồi chậm với một số hoạt động điều phối và quản lý.

GC không phải nguyên nhân duy nhất gây latency. CPU throttling, disk saturation, network congestion, page-cache miss và request overload cũng có thể tạo biểu hiện tương tự. Luôn đối chiếu thời điểm GC pause với request latency, CPU, disk I/O và replica lag.

### 3.4. GC dùng CPU ngay cả khi không pause

G1 có các pha concurrent chạy song song với ứng dụng. Chúng giúp rút ngắn một số pause nhưng tiêu thụ CPU trong thời gian broker đang phục vụ request. Nếu CPU quota của container thấp, GC thread và Kafka worker có thể tranh chấp CPU.

Khi thấy latency tăng nhưng stop-the-world pause ngắn, hãy kiểm tra CPU utilization, throttling và thời gian concurrent GC. Chỉ nhìn tổng GC pause có thể bỏ sót chi phí GC chạy đồng thời.

## 4. Chọn garbage collector và các JVM flags

### 4.1. Bắt đầu từ G1

G1 là lựa chọn mặc định phổ biến trên HotSpot server JVM hiện đại và được Apache Kafka sử dụng trong ví dụ cấu hình JVM. G1 hướng tới cân bằng throughput và pause time. Nên bắt đầu từ mặc định của JDK được Kafka hỗ trợ, sau đó thay đổi từng tham số dựa trên log và benchmark.

Tài liệu Kafka 4.4 ghi nhận Java 17, 21 và 25 được hỗ trợ đầy đủ; Java 11 chỉ được hỗ trợ cho một tập module nhất định. Ma trận hỗ trợ thay đổi theo Kafka release, vì vậy hãy kiểm tra đúng trang Java Version của phiên bản cluster trước khi nâng JDK. Dùng bản patch JDK mới nhất phù hợp với Kafka release và chính sách vận hành.

Không nên chuyển collector chỉ vì thấy một bài benchmark khác nhanh hơn. Kết quả phụ thuộc JDK build, heap size, allocation pattern, live set, CPU quota và latency objective.

### 4.2. Heap sizing

Ví dụ một broker có ngân sách heap 6 GiB:

~~~bash
export KAFKA_HEAP_OPTS="-Xms6g -Xmx6g"
~~~

Đặt Xms bằng Xmx có thể làm kích thước heap ổn định hơn, tránh việc JVM liên tục tăng/giảm heap trong runtime. Tuy nhiên, cấu hình này làm JVM cam kết heap lớn ngay từ đầu; nếu dùng AlwaysPreTouch, các trang heap còn được chạm trước lúc phục vụ traffic. Vì vậy phải tính phần RAM đó vào budget của node/container.

Nếu Xms thấp hơn Xmx, JVM có thể mở rộng heap theo nhu cầu. Cách này có thể giảm footprint ban đầu nhưng cần quan sát quá trình resize và độ ổn định của latency.

Không chọn heap chỉ dựa trên số lượng partition. Hãy đo heap used sau GC, live set, allocation rate, request load, metadata footprint và số thread trên broker thực tế.

### 4.3. Một số flag G1 thường gặp

| Flag | Ý nghĩa | Cách dùng |
|---|---|---|
| -XX:+UseG1GC | Chọn G1 collector | Thường không cần nếu đã là default của JDK |
| -Xms / -Xmx | Heap ban đầu và heap tối đa | Chọn theo memory budget |
| -XX:MaxGCPauseMillis | Mục tiêu pause time của G1 | Là mục tiêu gợi ý, không phải giới hạn cứng |
| -XX:InitiatingHeapOccupancyPercent | Ngưỡng occupancy khởi đầu cho marking trong một số chế độ | Chỉ điều chỉnh khi log cho thấy marking bắt đầu quá muộn |
| -XX:G1HeapRegionSize | Kích thước region của G1 | Thường giữ default; đánh giá nếu có nhiều humongous object |
| -XX:+AlwaysPreTouch | Chạm trước các trang heap được commit | Có thể làm startup lâu hơn nhưng giảm một số chi phí page fault lúc chạy |
| -XX:+ExplicitGCInvokesConcurrent | Với G1, yêu cầu explicit GC chạy theo chế độ concurrent khi phù hợp | Cần đánh giá tác động của System.gc và thư viện gọi nó |

Một số cấu hình Kafka 4.4 minh họa heap 6 GiB, G1 và các flag như MaxGCPauseMillis, InitiatingHeapOccupancyPercent, G1HeapRegionSize. Đây là ví dụ vận hành của một cluster có tải lớn, không phải bộ tham số áp dụng cho mọi broker.

### 4.4. Đừng khóa cứng young generation quá sớm

Với G1, young generation là một trong các cơ chế chính để điều chỉnh pause time. Các flag như -Xmn hoặc đặt cứng NewSize/MaxNewSize có thể làm giảm khả năng tự điều chỉnh của G1.

Nếu young GC pause quá dài, trước tiên kiểm tra số object sống phải copy, kích thước collection set, CPU contention và allocation pattern. Chỉ thay đổi giới hạn young generation khi log chứng minh đây là điểm nghẽn và đã benchmark.

### 4.5. MaxGCPauseMillis không phải SLA

MaxGCPauseMillis là mục tiêu để G1 điều chỉnh hoạt động. JVM có thể không đạt mục tiêu nếu heap quá nhỏ, live set quá lớn, CPU thiếu, allocation tăng đột ngột hoặc môi trường bị throttling.

Đặt mục tiêu pause quá thấp có thể làm G1 thu nhỏ young generation và chạy GC thường xuyên hơn, làm giảm throughput. Chọn pause objective dựa trên latency budget của ứng dụng, sau đó đo p95/p99 và tổng thời gian GC.

### 4.6. Ví dụ cấu hình và log GC

Ví dụ khởi chạy broker với heap 6 GiB và bật unified GC logging trên JDK hiện đại:

~~~bash
export KAFKA_HEAP_OPTS="-Xms6g -Xmx6g"
export KAFKA_JVM_PERFORMANCE_OPTS="-XX:+UseG1GC -Xlog:gc*:file=/var/log/kafka/gc.log:time,uptime,level,tags:filecount=10,filesize=100M"
~~~

Tên biến môi trường và cách script khởi chạy áp dụng JVM flags có thể khác giữa package, container image và systemd unit. Kiểm tra command line thực tế của process sau khi deploy.

GC log giúp trả lời:
- Collection xảy ra khi nào và vì lý do gì?
- Young, mixed hay Full GC?
- Pause kéo dài bao lâu?
- Heap trước và sau GC còn bao nhiêu?
- Có evacuation failure hoặc humongous allocation không?
- Concurrent marking có kịp hoàn tất không?

Không bật log không giới hạn dung lượng. Dùng rotation, dung lượng đủ lớn để giữ thời gian quan sát và ổ đĩa phù hợp để log không gây thêm I/O contention.

## 5. Page cache, log segment và storage

### 5.1. Đường đi của dữ liệu

Khi producer gửi record, broker xác thực request, xử lý batch và append dữ liệu vào log segment. Ghi file thường đi qua page cache. Kernel flush các dirty pages xuống storage theo chính sách của OS và cấu hình durability của Kafka.

Khi consumer fetch record, broker đọc log segment. Nếu các page cần đọc còn trong page cache, dữ liệu có thể được phục vụ từ RAM. Nếu cache miss, kernel phải đọc từ storage.

Điều này giải thích vì sao cùng một throughput, broker có thể có latency khác nhau khi:
- Working set vừa nằm trong page cache.
- Consumer replay một khoảng dữ liệu cũ, ít được cache.
- Nhiều broker hoặc process khác tranh chấp RAM.
- Storage bị quá tải do page-cache miss hoặc flush backlog.

### 5.2. Working set quan trọng hơn tổng retention

Giả sử cluster giữ 4 TiB log trên disk nhưng consumer chủ yếu đọc dữ liệu của 20 phút gần nhất. Không nhất thiết phải có 4 TiB RAM. Mục tiêu là giữ phần working set nóng đủ lớn để giảm cache miss, đồng thời vẫn để OS có RAM cho hoạt động khác.

Working set phụ thuộc:
- Tốc độ producer và consumer.
- Số consumer đọc lại dữ liệu cũ.
- Retention và kích thước segment.
- Mức độ phân tán partition trên broker.
- Tỷ lệ replication traffic.
- Pattern đọc ngẫu nhiên hay tuần tự.

Tài liệu Hardware and OS của Kafka đưa ra một heuristic ước lượng ban đầu: giả sử muốn buffer khoảng 30 giây hoạt động, rồi lấy write throughput nhân 30 để ước lượng bộ nhớ. Ví dụ, 200 MiB/s tương ứng khoảng 6.000 MiB dữ liệu ghi trong 30 giây. Đây chỉ là phép ước lượng thô cho active readers/writers, không phải cam kết page cache cần đúng bằng con số đó; phải benchmark với tốc độ đọc, replication, retention và pattern thực tế.

### 5.3. Page cache bị thu hẹp gây ra điều gì?

Khi heap và native memory tăng mạnh trong một memory limit cố định, kernel có ít không gian hơn cho file cache. Nếu page cache của log segment nóng bị reclaim:
1. Consumer đọc lại record cũ sẽ gặp cache miss.
2. Storage phải phục vụ nhiều read hơn.
3. Disk utilization và I/O wait có thể tăng.
4. Fetch latency tăng và consumer lag có thể tăng.
5. Replica fetch cũng có thể chậm nếu replica phải đọc dữ liệu chưa có trong cache.

Đây là quan hệ thường thấy, nhưng không phải mọi cache miss đều là lỗi. Nếu workload vốn đọc dữ liệu lạnh, storage throughput có thể là giới hạn thiết kế. Hãy so sánh cache behavior với disk latency, queue depth và consumer access pattern.

### 5.4. Dirty page và writeback

Page cache có thể chứa dirty pages: dữ liệu đã được ghi vào cache nhưng chưa hoàn tất writeback xuống storage. Nếu tốc độ ghi vượt khả năng flush của storage trong thời gian dài, kernel có thể throttle writer hoặc tạo write latency.

Các dấu hiệu nên kiểm tra:
- Dirty và Writeback trong /proc/meminfo.
- file_dirty và file_writeback trong cgroup memory.stat.
- Disk await, utilization và queue depth.
- Produce request latency và local time.
- I/O wait và writeback activity.

Không nên dùng lệnh drop_caches trên production để giải quyết memory pressure. Xóa page cache làm mất lợi ích cache và có thể khiến disk I/O tăng đột ngột.

## 6. Lập ngân sách memory cho broker

### 6.1. Công thức thực tế

Khi chạy trên host hoặc container, cần tính tổng nhu cầu:

~~~text
Memory budget
  = Java heap resident/committed
  + JVM non-heap
  + native memory
  + thread stacks and direct buffers
  + file page cache working set
  + kernel memory and socket buffers
  + other processes / agents
  + safety headroom
~~~

Nếu muốn tính bảo thủ cho container, dùng Xmx như một giới hạn heap có thể đạt tới, rồi cộng phần native/non-heap, page cache, kernel và headroom. Với heap chưa commit hết, mức sử dụng tức thời có thể thấp hơn Xmx; nhưng không nên dựa vào điều đó để đặt memory.max quá sát.

### 6.2. Ví dụ ngân sách cho node 64 GiB

Đây là ví dụ minh họa, không phải công thức sizing chuẩn cho mọi workload:

| Thành phần | Ngân sách minh họa |
|---|---:|
| Java heap resident | 8 GiB |
| JVM non-heap, direct/native, thread stack | 6 GiB |
| Page cache mục tiêu cho working set nóng | 36 GiB |
| OS, kernel, agent và safety reserve | 14 GiB |
| Tổng | 64 GiB |

Nếu đặt Xmx tăng từ 8 GiB lên 20 GiB trong cùng node, phần RAM dành cho page cache và headroom sẽ bị thu hẹp nếu các nhu cầu khác không đổi. Nếu heap cũ vốn thường chỉ dùng 4 GiB và không có GC pressure, tăng heap có thể không đem lại lợi ích.

### 6.3. Không nhầm retention size với page-cache target

Disk retention trả lời câu hỏi cần giữ dữ liệu bao lâu. Page-cache target trả lời câu hỏi cần giữ bao nhiêu dữ liệu nóng trong RAM để đạt latency/throughput mục tiêu.

Hai con số này khác nhau. Một topic retention 7 ngày có thể có working set chỉ vài chục GiB nếu consumer chỉ đọc dữ liệu gần đây. Một workload replay toàn bộ lịch sử lại có working set lớn hơn nhiều.

### 6.4. Memory limit của container

Trong container, memory limit có thể tính cả anonymous memory, file cache và một số kernel memory thuộc cgroup. Do đó, container có thể bị memory pressure hoặc OOM kill dù heap used vẫn thấp hơn Xmx.

Cần phân biệt:
- **Xmx:** giới hạn heap của JVM.
- **RSS:** trang process đang ở RAM.
- **memory.current:** tổng memory đang được cgroup sử dụng.
- **memory.max:** giới hạn cứng của cgroup.
- **memory.high:** ngưỡng tạo reclaim/throttling pressure trong cgroup v2.

Đặt memory.max chỉ vừa bằng Xmx là sai vì process còn cần native memory, page cache và kernel resources. Nếu broker container có memory limit 16 GiB và Xmx 12 GiB, chỉ còn 4 GiB cho mọi thành phần khác; cấu hình đó có thể bị OOM khi workload hoặc page cache tăng.

## 7. Container và cgroup v2: quan sát đúng memory

Linux cgroup v2 cung cấp các file hữu ích trong thư mục cgroup của process/container. Đường dẫn thực tế phụ thuộc runtime, systemd và namespace; hãy xác định đúng cgroup trước khi đọc.

### 7.1. Các file cần biết

| File | Ý nghĩa |
|---|---|
| memory.current | Tổng memory hiện tại của cgroup và descendants |
| memory.max | Hard limit |
| memory.high | Ngưỡng memory pressure/throttling |
| memory.stat | Phân rã anonymous, file cache, socket và kernel usage |
| memory.events | Bộ đếm sự kiện high, max, oom, oom_kill |
| memory.swap.current | Swap đang sử dụng |
| memory.pressure | PSI pressure nếu kernel/cgroup hỗ trợ |

Trong memory.stat:
- **anon:** anonymous memory, thường gồm heap và nhiều native allocations.
- **file:** file cache, bao gồm page cache và một số loại file-backed memory.
- **file_mapped:** phần file cache đang được mmap.
- **file_dirty / file_writeback:** file cache dirty hoặc đang writeback.
- **sock:** memory dùng cho network transmission buffers.
- **kernel:** một số kernel memory được cgroup theo dõi.

Các field có thể thay đổi theo kernel version. Đọc theo tên field, không dựa vào thứ tự dòng.

### 7.2. Lệnh kiểm tra cgroup v2

Sau khi xác định đúng thư mục cgroup của broker:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.high
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.stat
~~~

Nếu container không mount cgroup tại /sys/fs/cgroup hoặc process nằm trong nested cgroup, đường dẫn ví dụ trên sẽ khác. Không mặc định file ở root cgroup đại diện đúng container.

### 7.3. Đọc memory.stat

Ví dụ một phần output:

~~~text
anon 8589934592
file 25769803776
file_mapped 1073741824
file_dirty 134217728
file_writeback 67108864
sock 268435456
kernel 536870912
~~~

Trong ví dụ, file cache lớn hơn anon memory. Đây có thể là dấu hiệu tốt nếu đó là log working set đang được đọc thường xuyên và cgroup còn headroom. Cần so sánh với memory.current, memory.max, memory.events, storage latency và workload; không kết luận chỉ từ một snapshot.

### 7.4. Khi cgroup bắt đầu reclaim

Nếu memory.current thường xuyên tiến gần memory.high hoặc memory.max:
- Kernel có thể reclaim file cache.
- Process có thể bị throttle khi vượt memory.high.
- Allocation có thể chậm do reclaim.
- Nếu không reclaim đủ trước hard limit, cgroup có thể OOM kill process.

Đọc memory.events theo thời gian để xem bộ đếm high, max, oom và oom_kill có tăng không. Một lần chụp snapshot không cho biết áp lực đang tăng hay giảm.

## 8. Đo heap, GC và native memory

### 8.1. JMX MemoryMXBean

JVM cung cấp MemoryMXBean để quan sát:
- HeapMemoryUsage: init, used, committed và max.
- NonHeapMemoryUsage: phần non-heap.
- MemoryPoolMXBean: từng memory pool như G1 Eden, Survivor, Old Gen, Metaspace và Code Cache tùy JDK/collector.

Theo dõi các giá trị theo thời gian:
- Heap used trước GC và sau GC.
- Heap committed so với max.
- Old generation occupancy sau mixed/major collection.
- Metaspace và code cache.
- Tốc độ tăng live set sau GC.

Heap used cao trước GC nhưng giảm mạnh sau GC có thể là allocation pressure. Heap used sau GC tăng dần qua nhiều chu kỳ có thể là live set tăng, cache giữ object lâu hoặc memory leak; cần phân tích heap dump/class histogram trước khi kết luận.

### 8.2. GarbageCollectorMXBean và GC log

GarbageCollectorMXBean cung cấp collection count và collection time tích lũy. Dùng delta theo thời gian để ước lượng GC activity. Tuy nhiên, các giá trị tổng không thay thế pause histogram và phase breakdown trong GC log.

Đặt dashboard có:
- GC count theo collector.
- GC time rate.
- Pause duration p50/p95/p99/max.
- Full GC count.
- Allocation rate nếu có metric hỗ trợ.
- Heap used/committed/max.
- Old generation occupancy sau GC.

### 8.3. Native Memory Tracking

Native Memory Tracking (NMT) có thể bật lúc JVM startup:

~~~bash
export KAFKA_JVM_PERFORMANCE_OPTS="-XX:NativeMemoryTracking=summary"
~~~

Sau khi broker chạy, lấy baseline:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory summary.diff
~~~

NMT giúp phân tích các nhóm Java Heap, Class, Thread, Code, GC, Compiler và Internal. NMT có overhead và không phải bảng kế toán đầy đủ cho mọi native allocation bên ngoài JVM hoặc kernel page cache. Dùng cùng process RSS, cgroup memory.stat và host metrics để hiểu tổng footprint.

### 8.4. Heap dump và class histogram

Có thể dùng:

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

Heap dump có thể rất lớn, tốn I/O và làm ảnh hưởng broker. Chỉ tạo khi có kế hoạch lưu trữ, bảo vệ dữ liệu và thời gian thực hiện phù hợp. Không tự động dump heap trên mọi broker trong lúc production đang chịu tải cao.

## 9. Quan sát host và storage

### 9.1. RAM và page cache

~~~bash
free -h
grep -E 'MemAvailable|Cached|Buffers|Dirty|Writeback|Swap' /proc/meminfo
vmstat 1
~~~

Ý nghĩa:
- MemAvailable giúp ước lượng RAM có thể cấp mà không swap.
- Cached/Active(file)/Inactive(file) giúp quan sát file cache.
- Dirty và Writeback cho biết dữ liệu đang chờ hoặc đang được ghi xuống storage.
- vmstat cho thấy swap-in/swap-out, runnable processes, blocked processes và CPU wait.

Không kết luận memory pressure chỉ vì free gần bằng 0. Linux chủ động dùng RAM nhàn rỗi làm cache. Hãy xem MemAvailable, PSI, swap activity, cgroup counters và latency.

### 9.2. Process memory và CPU

~~~bash
ps -o pid,rss,vsz,comm -p <pid>
cat /proc/<pid>/smaps_rollup
pidstat -r -u -d -p <pid> 1
~~~

RSS và smaps_rollup giúp quan sát footprint của process. Chúng không thay thế cgroup memory usage vì page cache và kernel memory có thể được tính ở phạm vi cgroup.

### 9.3. Disk I/O

~~~bash
iostat -xz 1
pidstat -d -p <pid> 1
~~~

Theo dõi:
- Device utilization.
- Read/write throughput.
- Average request latency (await).
- Queue depth.
- I/O wait.
- Writeback và flush activity.

Khi page-cache hit giảm, disk read có thể tăng. Nhưng disk saturation cũng có thể do replication, compaction, recovery, retention delete hoặc flush backlog. Cần ghép timeline với Kafka request metrics.

## 10. Liên kết JVM metrics với Kafka metrics

Một dashboard hữu ích cần đặt các tín hiệu cạnh nhau thay vì tách thành các trang không liên quan.

| Nhóm | Chỉ số nên theo dõi | Câu hỏi |
|---|---|---|
| JVM heap | Used, committed, max, old-gen after GC | Heap có thiếu hay live set đang tăng? |
| GC | Pause p95/p99/max, Full GC, GC time | Broker có bị dừng hoặc mất CPU vì GC? |
| Native | NMT categories, direct buffer, thread count | Heap ổn nhưng process memory có tăng không? |
| OS memory | MemAvailable, swap, PSI, page cache | Kernel có đang reclaim hoặc swap? |
| cgroup | memory.current, file, anon, high/max/oom events | Container có tiến sát limit không? |
| Disk | Read/write latency, queue, utilization | Cache miss hoặc writeback có gây I/O bottleneck? |
| Kafka request | Produce/Fetch latency, request queue, handler idle | Request đang chờ GC, CPU, disk hay network? |
| Replication | Replica lag, ISR, fetch rate | Broker chậm có ảnh hưởng replication? |
| Consumer | Max lag, fetch rate | Consumer có bị chậm theo broker latency? |

Apache Kafka khuyến nghị theo dõi GC time cùng CPU utilization, I/O service time và các chỉ số server/client. Cần theo dõi cả throughput và latency; chỉ nhìn CPU hoặc heap một mình sẽ bỏ lỡ nhiều dạng bottleneck.

### 10.1. Ví dụ tương quan

Giả sử cùng thời điểm:
- GC pause p99 tăng lên 800 ms.
- Produce request latency tăng.
- Request queue tăng.
- Disk await ổn định.
- memory.current còn nhiều headroom.

Khả năng cao cần điều tra GC/heap/allocation hoặc CPU contention trước khi thay storage.

Một tình huống khác:
- Heap after-GC ổn định.
- GC pause thấp.
- cgroup memory.current tiến gần memory.high.
- memory.stat file giảm.
- Disk read latency và consumer lag tăng.

Tình huống này gợi ý page cache bị reclaim hoặc cgroup đang chịu áp lực memory. Tăng Xmx có thể làm tình hình xấu hơn.

## 11. Phân biệt các dạng sự cố memory

### 11.1. Heap pressure

Dấu hiệu:
- Heap used thường xuyên tiến sát Xmx.
- Old generation sau GC vẫn cao.
- GC chạy dày hoặc có Full GC.
- Allocation failure/evacuation failure trong log.

Hướng xử lý:
1. Xác định allocation rate và live set.
2. Kiểm tra heap histogram để tìm object chiếm nhiều.
3. Kiểm tra cache hoặc object retention trong broker/plugin.
4. Đo lại heap cần thiết với tải đại diện.
5. Chỉ tăng Xmx khi node còn đủ RAM cho native, page cache và headroom.

### 11.2. Native memory pressure

Dấu hiệu:
- Heap used thấp nhưng RSS hoặc memory.current cao.
- NMT cho thấy Thread, Class, Code hoặc Internal tăng.
- Số thread/direct buffer tăng.
- Container có thể OOM dù heap chưa đầy.

Hướng xử lý:
1. Bật NMT trong lần khởi động phù hợp.
2. So sánh NMT baseline và diff.
3. Kiểm tra số thread, stack size, direct buffer và thư viện native.
4. Kiểm tra socket buffers và cgroup memory.stat.
5. Không giảm Xmx một cách máy móc nếu native allocation mới là nguyên nhân.

### 11.3. Page-cache pressure

Dấu hiệu:
- Heap và GC tương đối ổn định.
- memory.stat file hoặc file_mapped giảm khi tải tăng.
- Disk read tăng, I/O latency tăng.
- Consumer replay hoặc fetch lag tăng.
- memory.current gần memory.high/max.

Hướng xử lý:
1. Xác định working set đọc thực tế.
2. Kiểm tra cgroup limit và memory events.
3. Xem có process khác dùng chung node/cgroup không.
4. Giảm heap nếu có bằng chứng heap dư thừa.
5. Cân nhắc tăng RAM hoặc điều chỉnh memory limit nếu workload cần cache lớn hơn.
6. Benchmark lại với read pattern đại diện.

### 11.4. OS writeback pressure

Dấu hiệu:
- Dirty/writeback tăng.
- Disk write latency và queue depth tăng.
- Produce latency tăng dù GC thấp.
- CPU có thể không cao nhưng I/O wait tăng.

Hướng xử lý:
1. Kiểm tra throughput và latency storage.
2. Kiểm tra flush policy, disk scheduler và volume limits.
3. Phân biệt writeback pressure với GC pause.
4. Kiểm tra replication và compaction đang chạy.
5. Không giảm page cache hoặc ép fsync liên tục khi chưa đánh giá tác động.

### 11.5. OOMKilled trong container

Dấu hiệu:
- Container restart với exit code hoặc trạng thái OOMKilled.
- memory.events tăng oom/oom_kill.
- Heap dump không nhất thiết có.
- JVM log có thể không ghi được OutOfMemoryError vì kernel kill process.

Hướng xử lý:
1. Kiểm tra memory.current và memory.max trước khi restart nếu còn dữ liệu.
2. Kiểm tra memory.events và runtime events.
3. So sánh Xmx, RSS, native memory, file cache và socket memory.
4. Tăng headroom hoặc giảm footprint sau khi xác định nguyên nhân.
5. Tránh chỉ tăng Xmx; điều đó có thể làm container OOM sớm hơn.

## 12. Quy trình tuning theo giả thuyết

Không thay đổi đồng thời heap, GC flags, thread count và memory limit. Nếu thay quá nhiều biến, rất khó xác định điều gì tạo ra cải thiện hoặc regression.

Quy trình gợi ý:

1. **Chụp baseline:** throughput, produce/fetch p95/p99, consumer lag, GC pause, heap after-GC, RSS, memory.current, page cache và disk latency.
2. **Xác định bottleneck:** heap pressure, GC CPU/pause, native memory, page-cache reclaim hay storage saturation.
3. **Đặt giả thuyết:** ví dụ old-gen pressure gây Full GC; hoặc Xmx dư thừa đang thu hẹp page cache.
4. **Thay một nhóm nhỏ:** chỉ điều chỉnh heap size hoặc một GC setting hoặc memory limit.
5. **Chạy workload đại diện:** cùng message size, partition count, replication factor, producer/consumer pattern và retention.
6. **So sánh:** latency percentiles, throughput, GC time, cache behavior, disk I/O và error/restart.
7. **Giữ hoặc rollback:** chỉ giữ cấu hình nếu cải thiện mục tiêu mà không tạo regression ở chỉ số khác.

### 12.1. Benchmark cần giữ cố định

Để so sánh heap 6 GiB và heap 10 GiB, giữ các yếu tố sau ổn định:
- Cùng phiên bản Kafka và JDK.
- Cùng số broker, partition và replication factor.
- Cùng producer acks, compression, batch size và message size.
- Cùng consumer concurrency và fetch pattern.
- Cùng retention và log segment configuration.
- Cùng storage class, filesystem và CPU quota.
- Cùng thời gian warm-up và thời gian đo.

Page cache cần thời gian warm-up. Benchmark chỉ chạy vài giây có thể phản ánh cold-cache startup thay vì steady-state.

### 12.2. Đọc kết quả theo mục tiêu

| Mục tiêu | Chỉ số ưu tiên |
|---|---|
| Throughput | MB/s, records/s, CPU, disk throughput |
| Produce latency | p95/p99, request queue, GC pauses, disk write latency |
| Fetch latency | p95/p99, page-cache behavior, disk read latency |
| Consumer freshness | Max lag, fetch rate, broker request latency |
| Stability | Full GC, OOM, memory.events, ISR/replica lag |
| Cost efficiency | Throughput trên mỗi GiB RAM/CPU và storage |

Một cấu hình có throughput cao hơn nhưng p99 latency xấu hơn hoặc dễ OOM hơn có thể không phù hợp production.

## 13. Kịch bản thực hành: heap tăng làm page cache giảm

Giả sử một broker chạy trên container 32 GiB. Ban đầu:
- Xmx = 6 GiB.
- Heap after-GC ổn định quanh 3 GiB.
- Native/non-heap khoảng 4 GiB.
- File cache khoảng 16 GiB.
- Kernel, socket và agent khoảng 3 GiB.
- Còn headroom khoảng 3 GiB.

Đội vận hành tăng Xmx lên 14 GiB vì thấy heap used trước GC có lúc lên 5 GiB. Sau rollout:
- Heap committed và resident tăng.
- File cache bị reclaim.
- Consumer replay đọc nhiều dữ liệu cũ.
- Disk read tăng.
- Fetch latency và consumer lag tăng.
- GC pause không cải thiện đáng kể vì heap after-GC vốn đã ổn định.

Cách xử lý hợp lý là xác minh heap profile và GC log. Nếu live set sau GC vẫn nhỏ, giảm Xmx về mức đủ cho allocation peak và dành lại headroom cho file cache. Sau đó chạy lại replay benchmark và so sánh disk read, fetch latency, consumer lag cùng GC metrics.

Điểm cần học: một lần heap used tăng cao trước GC không đủ để kết luận heap tối đa đang thiếu. Cần nhìn cả heap sau GC và tác động tới page cache.

## 14. Production checklist

| Hạng mục | Câu hỏi kiểm tra |
|---|---|
| JDK | Kafka version có hỗ trợ JDK đang chạy không? Đã dùng patch release mới chưa? |
| Heap | Xms/Xmx dựa trên live set và allocation peak chưa? |
| GC | Có GC log rotation và dashboard pause percentile chưa? |
| G1 | Có giữ adaptive behavior của G1 và tránh khóa young generation không cần thiết không? |
| Native | Đã tính direct buffer, thread stack, metaspace và native libraries chưa? |
| Page cache | Đã đo file cache và working set đọc chưa? |
| Container | Xmx có headroom so với memory.max không? |
| Cgroup | Có theo dõi memory.current, memory.stat và memory.events không? |
| OS | MemAvailable, swap, PSI, dirty/writeback có được giám sát không? |
| Storage | Có theo dõi disk latency, queue depth và utilization không? |
| Kafka | Có tương quan GC với Produce/Fetch latency, request queue và replica lag không? |
| Benchmark | Có warm-up page cache và workload đại diện không? |
| Recovery | Có quy trình điều tra OOMKilled và Full GC không? |
| Rollback | Có thể quay về heap/GC profile trước khi tuning không? |

## 15. Anti-pattern cần tránh

- **Đặt Xmx bằng toàn bộ memory limit:** không chừa chỗ cho native memory, page cache và kernel.
- **Tăng heap vì thấy heap used cao trước GC:** bỏ qua heap after-GC và live set.
- **Giảm heap chỉ để tăng page cache:** có thể tạo GC pressure và Full GC.
- **Chỉnh nhiều GC flags cùng lúc:** không xác định được tác động của từng thay đổi.
- **Khóa young generation quá sớm:** làm G1 mất khả năng tự điều chỉnh pause.
- **Xem MaxGCPauseMillis như giới hạn cứng:** JVM không bảo đảm luôn đạt giá trị đó.
- **Bỏ qua native memory:** heap ổn định nhưng process vẫn có thể bị OOM.
- **Dùng free memory làm tiêu chí duy nhất:** Linux chủ động dùng RAM cho page cache.
- **Chạy drop_caches trong production:** làm mất cache nóng và tăng I/O.
- **Bật heap dump không kiểm soát:** dump lớn có thể làm tăng I/O và ảnh hưởng broker.
- **Chỉ nhìn GC log:** bỏ qua page-cache reclaim, disk latency và cgroup throttling.
- **Chỉ nhìn RSS:** không phân biệt được anonymous memory, file cache và kernel memory.

## 16. Runbook chẩn đoán nhanh

Khi broker có latency spike hoặc bị OOM, thu thập các dữ liệu sau trong cùng một khoảng thời gian:

~~~bash
free -h
grep -E 'MemAvailable|Cached|Dirty|Writeback|Swap' /proc/meminfo
vmstat 1
iostat -xz 1
ps -o pid,rss,vsz,comm -p <pid>
cat /proc/<pid>/smaps_rollup
~~~

Với cgroup v2, đọc memory.current, memory.max, memory.high, memory.events và memory.stat tại đúng cgroup của broker.

Với JVM:

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> VM.flags
jcmd <pid> VM.native_memory summary
~~~

Lệnh VM.native_memory chỉ trả về số liệu hữu ích nếu NMT được bật khi JVM khởi động.

Sau đó đối chiếu:
- GC pause timestamp với Kafka request latency.
- Heap after-GC với Xmx.
- RSS và NMT với memory.current.
- File cache với disk read throughput/latency.
- Dirty/writeback với disk write latency.
- memory.events với thời điểm container bị throttle hoặc OOM.
- Replica lag và consumer lag với request latency.

Không tăng heap hoặc memory limit trước khi xác định loại memory đang chiếm phần lớn ngân sách.

## 17. Tóm tắt lựa chọn vận hành

| Quan sát | Hướng ưu tiên điều tra |
|---|---|
| Heap after-GC cao, Full GC tăng | Live set, allocation và heap sizing |
| Heap thấp, RSS cao | Native memory, thread stack, direct buffer, mapped memory |
| Heap ổn, file cache giảm, disk read tăng | Page-cache pressure và container memory limit |
| GC pause thấp nhưng latency cao, CPU throttled | CPU quota và concurrent GC |
| Dirty/writeback cao, disk await cao | Storage throughput và OS writeback |
| memory.events oom_kill tăng | Tổng memory budget của cgroup, không chỉ Xmx |

Kafka cần cả heap đủ dùng để broker xử lý request ổn định và page cache đủ lớn để đọc/ghi log hiệu quả. Cách tuning đúng bắt đầu từ việc đo từng nhóm memory, xác định bottleneck và thay đổi từng tham số có kiểm soát.

## Tài liệu tham khảo

- Apache Kafka 4.4 — Java Version: https://kafka.apache.org/44/operations/java-version/
- Apache Kafka 4.4 — Hardware and OS: https://kafka.apache.org/44/operations/hardware-and-os/
- Apache Kafka 4.4 — Monitoring: https://kafka.apache.org/44/operations/monitoring/
- Oracle Java 21 — Garbage-First Garbage Collector Tuning: https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector-tuning.html
- Oracle Java 21 — Garbage-First Garbage Collector: https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html
- Linux Kernel — Control Group v2: https://docs.kernel.org/admin-guide/cgroup-v2.html
- Oracle Java — Native Memory Tracking and diagnostic tools: https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html
