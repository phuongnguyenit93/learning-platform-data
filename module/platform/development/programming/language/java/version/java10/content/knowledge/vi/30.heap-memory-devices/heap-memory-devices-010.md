# Đánh giá độ trễ, băng thông và độ ổn định trước khi áp dụng Java heap trên thiết bị bộ nhớ

> **Java 10 — Heap trên thiết bị bộ nhớ.** **JEP 316 — Heap Allocation on Alternative Memory Devices** cho phép HotSpot đặt **Java object heap** lên một thiết bị nhớ thay thế DRAM phù hợp, thông qua tùy chọn `-XX:AllocateHeapAt=<path>` và ánh xạ bộ nhớ. Tính năng này **vẫn được tài liệu Oracle JDK 25 mô tả**. Nhưng “có thể đặt heap lên thiết bị” **không đồng nghĩa ứng dụng chạy nhanh hơn, ổn định hơn hoặc dữ liệu Java tự phục hồi sau crash**. Trước khi triển khai, phải xác minh phần cứng/hệ điều hành/DAX tương thích, đo **độ trễ (đặc biệt tail latency)**, **băng thông đọc/ghi và throughput nghiệp vụ**, **GC**, **page faults**, **phân phối NUMA**, **độ tin cậy qua chạy dài và khởi động lại**, rồi ra quyết định có đối chứng. Chỉ sử dụng kiến thức còn áp dụng trên JDK hiện đại; không xem những sản phẩm phần cứng đã ngừng sản xuất là lựa chọn mua sắm mặc định.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích mục tiêu và giới hạn của **JEP 316** trong Java 10: đặt **object heap** ở bộ nhớ thay thế khi nó đáp ứng semantics phù hợp với DRAM, kể cả các atomic operations.
2. Hiểu `-XX:AllocateHeapAt` đang được tài liệu hóa trên **Oracle Java SE 25** nhưng phụ thuộc **HotSpot, hệ điều hành và thiết bị**, không phải một Java SE API portable cho mọi JVM.
3. Phân biệt **DRAM**, thiết bị nhớ truy cập như RAM, **DAX/fs-DAX** và một **SSD/filesystem thông thường**; không nhầm file-backed mapping nào cũng là persistent-memory direct access.
4. Hiểu heap trên non-DRAM **vẫn là heap do GC quản lý**, không phải database bền vững hay snapshot có thể mở lại sau JVM crash.
5. Đo riêng **memory-access latency**, **request/service latency p50/p95/p99/p99.9**, **bandwidth (GiB/s)**, **successful operations/second**, **GC pause** và **startup**, với công cụ phù hợp từng tầng.
6. Phân biệt đo **độ trễ random dependent load** với **băng thông truy cập tuần tự**, read vs write, cache hit vs working-set vượt cache, và local vs remote NUMA.
7. Thiết kế baseline DRAM và candidate alternative-memory trên **cùng JDK/GC/heap/CPU/workload**; kiểm tra heap thực sự được map đến đúng tier.
8. Biết dùng **JMH** cho microbenchmark memory-access có kiểm soát, đồng thời dùng **end-to-end load test** để đánh giá SLO nghiệp vụ.
9. Tránh các bẫy: JIT dead-code elimination, quá ít mẫu cho p99, coordinated omission, không warmup, benchmark bị cache che khuất, chỉ đo một run.
10. Thiết lập cổng chấp nhận có tính đến **tail latency, bandwidth, throughput, lỗi dữ liệu, ổn định restart và lợi ích capacity/cost**.
11. Chạy một lab **Java 17+** độc lập, dùng dữ liệu **giả định** với **29 dòng stdout chính xác**, minh họa cách quyết định “đủ điều kiện pilot” khác “có thể triển khai production”.
12. Xây ma trận kiểm tra **chạy dài/soak, lỗi thiết bị, GC under pressure, restart, permissions, bảo mật file-backed memory và khả năng rollback**.
13. Nhận biết giới hạn của dữ liệu từ **JFR, GC logs, Linux DAX, NUMA, perf, OS counters**, không tráo chúng cho số liệu nghiệp vụ.
14. Tránh khuyến nghị phần cứng đời cũ đã **EOL** hoặc các công cụ/flag không còn thích hợp khi JDK/OS thay đổi.

## 2. Điểm xuất phát: JEP 316 làm được gì và không làm được gì?

### 2.1. Mục tiêu của Heap Allocation on Alternative Memory Devices

Trong JEP 316 (JDK 10), HotSpot hỗ trợ đặt **Java object heap** tại một vùng bộ nhớ do người vận hành chỉ định, thay vì luôn để OS cấp qua cơ chế DRAM thông thường. Ví dụ thực tế lịch sử là một vùng **NV-DIMM** được OS xuất hiện như filesystem hỗ trợ memory mapping phù hợp.

Oracle JDK 25 `java` manpage vẫn mô tả `-XX:AllocateHeapAt=<path>`:
- JVM nhận một **đường dẫn filesystem**.
- VM dùng **memory mapping** để đưa **object heap** lên thiết bị memory thay thế.
- Thiết bị phải có **ngữ nghĩa tương thích DRAM**, gồm **atomic operations** cần thiết.
- **Code heap, metaspace và thread stacks** tiếp tục nằm ở **DRAM** theo mô tả cơ chế này.
- Các tùy chọn heap và GC như `-Xms`, `-Xmx` vẫn hoạt động theo hợp đồng tương ứng.

**Không được hiểu** rằng flag sẽ di chuyển **mọi byte memory của tiến trình** lên thiết bị. JVM còn stack, metaspace, JIT code cache, native buffers, GC/OS data structures và mapped libraries; profile bộ nhớ tổng thể vẫn gồm các thành phần riêng.

### 2.2. DAX là gì?

Linux **Direct Access (DAX)** giúp những filesystem và thiết bị có hỗ trợ có thể cung cấp **direct, memory-mapped access** đến vùng nhớ thích hợp **không phải qua bản sao page cache thông thường**. Kernel yêu cầu phần cứng/driver hỗ trợ địa chỉ hóa như bộ nhớ và có các điều kiện kỹ thuật về page size, file/inode DAX và thao tác mmap.

Sơ đồ khái niệm:

```text
Java object access
   |
   v
HotSpot-managed Java heap
   |
   +-- baseline: conventional heap backing / DRAM
   |
   +-- candidate: -XX:AllocateHeapAt=<compatible path>
            |
            v
        mmap-backed heap area
            |
            v
        supported memory-like device
        (appropriate filesystem/OS mapping semantics)
```

**Đường dẫn là điều kiện cần, không phải bằng chứng đủ.** File trên ext4/XFS thông thường có thể là page-cache-backed; `tmpfs` dùng RAM; network filesystem không tự biến thành media có load/store atomic DRAM semantics; SSD block I/O thông thường **không phải** một vùng heap memory-addressable thích hợp chỉ vì tên thiết bị “non-volatile”.

### 2.3. Không có bảo đảm Java object trở thành persistent

Dù một device có chữ “persistent”:
- Java object graph do GC quản lý, có references, headers và metadata.
- JVM có thể chuyển object, compact, cập nhật references, sử dụng GC/barriers theo thiết kế.
- Cấu trúc runtime và metadata khác nằm ngoài device, có trạng thái chỉ hợp lệ trong process đang chạy.
- JEP 316 **không cung cấp API phục hồi object graph sau khi JVM crash/restart**.
- Không thể mở lại một file mapped heap cũ như một database transaction log có tính nhất quán.
- Một số bytes có thể còn lại trên thiết bị sau crash; đó là **rủi ro bảo mật**, không phải hợp đồng persistence.

Nếu hệ thống cần dữ liệu bền vững hoặc crash consistency, phải sử dụng **database, log, filesystem, transactional storage hoặc API persistence** với các bảo đảm được thiết kế và kiểm thử riêng. Không dùng `AllocateHeapAt` thay cho hệ thống lưu trữ bền vững.

### 2.4. Hệ sinh thái phần cứng hiện nay không giống năm 2018

JEP 316 được thiết kế trong bối cảnh bộ nhớ khác DRAM như NV-DIMM được quan tâm mạnh. Tuy nhiên **Intel đã ngừng phát triển dòng Optane**, và nhiều sản phẩm Optane Persistent Memory đã tới thời hạn EOL/EOIS theo thông báo của Intel. Vì vậy:

- Có thể học về NV-DIMM như **ví dụ kiến trúc lịch sử** để hiểu JEP.
- **Không** xem Optane thế hệ cũ là phần cứng nên mua mới mặc định.
- Với nền tảng memory tier hiện đại (chẳng hạn một số hệ thống dùng CXL), phải kiểm tra **thiết bị được OS xuất hiện theo chế độ nào**, cơ chế NUMA/tiering nào được hỗ trợ và liệu **JDK flag nêu trên có thực sự tương thích**.
- **Không đồng nhất CXL memory mở rộng với một filesystem DAX**: một số CXL devices xuất hiện dưới dạng system RAM/NUMA nodes, một số cấu hình khác hẳn; `AllocateHeapAt` không tự đặt heap lên mọi dạng CXL.
- Khả năng hỗ trợ phần cứng, firmware, kernel, Java distribution và chính sách vận hành là tiêu chí của **năm triển khai thật**, không thể kế thừa vô điều kiện từ ví dụ JDK 10.

**Điểm còn áp dụng:** định lượng latency, bandwidth, tail SLO, GC stability và device lifecycle trước khi đổi memory placement.

## 3. Độ trễ: phải đo nhiều tầng và đuôi phân phối

### 3.1. Memory-access latency ở tầng phần cứng

Độ trễ khi một load phụ thuộc vào địa chỉ vừa đọc thường được đo bằng **nanoseconds trên mỗi truy cập** hoặc **CPU cycles trên mỗi truy cập**. Khi dữ liệu ở L1/L2/L3 cache, nó có thể được phục vụ từ cache, không phải tới memory device.

Bởi vậy một phép đo muốn so **DRAM và memory-like device** cần:
- working set đủ lớn để đi qua các cache cần đánh giá;
- chuỗi truy cập **phụ thuộc dữ liệu** (dependent pointer chasing) để hạn chế memory-level parallelism;
- warmup page mappings và kiểm soát page faults nếu đang đo latency steady;
- phân biệt local/remote NUMA;
- báo kích thước working set (MiB/GiB), độ dài chuỗi và topology.

**Không lấy thời gian đọc một biến Java duy nhất trong vòng lặp rồi gọi đó là “memory latency của NVDIMM”**. JIT có thể giữ giá trị trong register, loại bỏ lệnh, hoặc dữ liệu đã ở cache.

### 3.2. Độ trễ request của ứng dụng mới là mục tiêu SLO

Một request/service call đi qua nhiều giai đoạn:

```text
client -> load balancer -> network -> queue -> Java app
                                           |
                                           +-> CPU/heap object accesses
                                           +-> DB/cache/external services
                                           +-> locks/GC pauses
                                           +-> allocation/JIT
                                           |
                             response <- result
```

Thay memory tier của heap có thể ảnh hưởng CPU stalls và GC, **nhưng không quyết định toàn bộ latency**. Nếu phần lớn request chờ DB/network, memory-device latency khác nhau có thể khó thấy ở end-to-end. Ngược lại, workload có nhiều truy cập random heap data lớn vượt LLC có thể nhạy đáng kể.

Cần đo:
- `p50`: trải nghiệm phổ biến;
- `p95` và `p99`: phần đuôi quan trọng với dịch vụ;
- `p99.9` hoặc maximum: sự kiện hiếm hơn, tùy mẫu và mục tiêu;
- error/timeout rate, queueing và retry;
- latency theo **loại request**, không chỉ trung bình toàn dịch vụ.

**Không lấy mean latency làm cổng chấp nhận duy nhất.** Mean có thể giữ nguyên khi p99 tệ đi đáng kể.

### 3.3. P99 là phân vị, không phải “tệ nhất”

Với `N` observations, percentile 99 theo phương pháp nearest-rank thường chọn observation tại vị trí `ceil(0.99*N)` sau khi sắp tăng. Nhưng các hệ thống có thể dùng interpolation hoặc streaming approximation; báo thuật toán/tolerance.

Nếu có đúng 100 mẫu, `p99` nearest-rank là mẫu thứ 99, còn mẫu thứ 100 có thể cực kỳ chậm. Với 10 mẫu, `p99` nearest-rank lại thường chính là maximum. Hai trường hợp đều **không đủ** để tuyên bố rằng hệ thống hiếm khi có sự cố ở tỷ lệ 0,01%.

Để đánh giá p99.9 có ý nghĩa, cần **rất nhiều mẫu** ở nhiều trial và bảo đảm generator/harness không che request bị queue/timeout.

### 3.4. Coordinated omission: bẫy của load generator

Nếu client chờ request trước hoàn tất rồi mới gửi request kế tiếp, các pause dài ở server có thể giảm số request mới được tạo. Tập quan sát có thể bỏ sót chính **thời gian chờ** mà người dùng thực sự chịu khi có spike.

Với service cần SLO:
- sử dụng generator có chính sách **arrival rate** rõ;
- lưu queue wait, timeout và failed responses;
- nếu cần, dùng workload mô phỏng open-loop hoặc cơ chế sửa coordinated omission phù hợp;
- không tự loại 5xx/timeouts khỏi phân phối rồi báo p99 đẹp;
- ghi cách thống kê latency cho request bị timeout.

**Một candidate có 0 request 5xx nhưng p99 20 ms** và một candidate có 3% timeout không thể so chỉ bằng p99 của các request thành công.

### 3.5. Read vs write, sequential vs random

| Loại truy cập | Đặc điểm | Thiết kế đo |
| --- | --- | --- |
| Random dependent read | Nhạy memory latency, khó che bằng prefetch | Pointer chasing trên working set lớn |
| Sequential read | Dễ prefetch, đo sustained bandwidth hơn là latency đơn lẻ | Duyệt buffer/array đủ lớn, đếm bytes/time |
| Sequential write | Nhạy write bandwidth, cache eviction, dirty pages | Ghi dữ liệu mới và xác nhận kết quả |
| Random write | Có thể nhạy write combining, atomicity, locality | Phân phối địa chỉ và concurrency đại diện |
| Mixed read/write | Gần workload dịch vụ | Tỷ lệ read/write theo telemetry |
| Object graph traversal | Cache miss, pointer chasing và layout object thực | Benchmark nghiệp vụ hoặc JMH mô phỏng dữ liệu thật |
| GC object copy/scan | Đọc/ghi heap dưới các pha GC | JFR/GC logs, heap footprint và pause |
| Initialization/cold mapping | Page faults, map/populate, first-touch | Đo startup/cold access riêng steady state |

Đừng chỉ đo **sequential bandwidth cao** rồi kết luận một application dùng map/tree/graph với nhiều random reads cũng nhanh.

## 4. Băng thông: khác độ trễ và khác thông lượng nghiệp vụ

### 4.1. Định nghĩa và đơn vị

Băng thông memory được diễn tả:

\[
\mathrm{Bandwidth}=\frac{\mathrm{bytes\ đã\ đọc/ghi}}{\mathrm{elapsed\ seconds}}
\]

Thường dùng **GiB/s** (2³⁰ bytes/s) hoặc **GB/s** (10⁹ bytes/s), phải ghi rõ. Ví dụ 26 **GiB/s** không bằng 26 **GB/s**.

Thông lượng ứng dụng lại là:

\[
\mathrm{Application\ throughput}=
\frac{\mathrm{successful\ operations}}{\mathrm{seconds}}
\]

Hai metric không đồng nhất:
- Memory bandwidth có thể tăng do làm **nhiều thao tác bộ nhớ hơn** nhưng ứng dụng xử lý ít request hơn.
- Workload CPU-bound có thể không hưởng lợi từ bandwidth cao.
- Service có thể đạt request/second tốt dù cần ít bandwidth và phần lớn chờ I/O.
- GC có thể tiêu thụ memory bandwidth nhưng không tạo thêm successful business operations.

### 4.2. Băng thông “peak” và “sustained under load”

Một thiết bị có bandwidth lý thuyết 50 GiB/s không đồng nghĩa ứng dụng nhận được 50 GiB/s:
- NUMA placement và interconnect có giới hạn.
- Read/write mix khác nhau.
- CPU/cache coherence tranh chấp băng thông.
- GC threads, JIT và application threads cùng truy cập memory.
- Thermal/power throttling, firmware error handling.
- Memory-device wear/health, OS/kernel scheduling và tài nguyên dùng chung.

Báo cả:
- read GiB/s và write GiB/s nếu tách được;
- bandwidth ở một thread, nhiều threads, và mức saturation;
- sustained bandwidth trong cửa sổ đủ dài;
- throughput/p99 khi băng thông gần bão hòa;
- thermal/power/error counters nếu có nguồn đáng tin.

### 4.3. Tránh cache che đặc tính thiết bị

Nếu benchmark dùng một `int[1024]` lặp đi lặp lại, toàn bộ có thể ở cache. Việc chạy trên DRAM hay alternative-memory có thể cho kết quả gần giống vì các access **không chạm memory tier** thường xuyên.

Dùng nhiều kích thước working set, ví dụ:
- nhỏ hơn L3;
- xấp xỉ L3;
- lớn hơn L3 đáng kể;
- gần footprint live-set của production.

Đặt memory pressure và concurrency khác nhau để thấy ranh giới mà device bắt đầu ảnh hưởng. **Không ép tạo mảng quá lớn trong container sản xuất chỉ để stress test**, và không chạy load phá device ngoài môi trường thử nghiệm được phép.

### 4.4. Đơn vị so sánh xuyên tầng

| Câu hỏi | Metric phù hợp | Không thay bằng |
| --- | --- | --- |
| Mỗi random dependent load tốn bao lâu? | ns/access, cycles/access | GB/s tối đa trên datasheet |
| Copy/scan buffer lớn nhanh thế nào? | GiB/s sustained | p99 HTTP latency |
| Code hot path xử lý được bao nhiêu công việc? | successful ops/s, CPU utilization | Một điểm băng thông read |
| Người dùng có bị chậm đột biến? | p95/p99/p99.9 + timeout | Mean ns/access |
| Heap đã bị page faults/cold misses? | major/minor faults, mapping stats | Bandwidth synthetic |
| GC trên device có tốt không? | pause p99, cycles, allocation/stall rates | Chỉ một phép đọc ngẫu nhiên |

## 5. Kiểm tra điều kiện nền tảng trước benchmark

### 5.1. Bốn lớp tương thích

Một cấu hình “dùng heap trên memory device” chỉ hợp lệ khi kiểm chứng:

1. **Hardware/firmware:** thiết bị là memory-like, có CPU-addressable load/store semantics và atomic operations được JVM yêu cầu; có đủ capacity, ECC/error handling, nguồn hỗ trợ và khả năng bảo trì.
2. **OS/kernel/filesystem:** driver và cơ chế memory mapping/DAX đúng; filesystem và inode hỗ trợ, không chỉ mount một thư mục bất kỳ rồi đặt flag.
3. **JVM:** bản HotSpot/JDK phân phối thật sự hỗ trợ `AllocateHeapAt` trên OS/platform/GC đang dùng, không có cảnh báo bị ignore/fallback.
4. **Application/workload:** heap size, live-set, classloading/native memory, GC, security, latency SLO và fallback đáp ứng.

Nếu một lớp không đạt thì **dừng trước khi benchmarking hiệu năng**, vì số liệu có thể đang đo nhầm DRAM/page cache hoặc cấu hình không được JVM hỗ trợ.

### 5.2. DAX phải được xác minh thật

Trên Linux:
- Xác định đúng device, namespace, mountpoint và filesystem bằng công cụ OS như `findmnt` và `lsblk` (trong môi trường được phép).
- Kiểm tra driver hỗ trợ DAX; có thể cần `ndctl`/`daxctl` hoặc công cụ platform tương ứng **khi thiết bị thực sự yêu cầu**, không mặc định mọi memory tier đều cần.
- Với file-based DAX, xác minh trạng thái **S_DAX/STATX_ATTR_DAX** của file/inode theo Linux kernel docs, không chỉ xem tên thư mục.
- Dùng OS mapping/NUMA diagnostics để xác nhận pages được thực sự đặt trên memory tier mong muốn.
- Đảm bảo đủ dung lượng, đúng quyền đọc/ghi, ulimit/process resource và chính sách cleanup.

**Không phải cứ mount XFS/ext4 thì DAX tự bật.** Kernel DAX có điều kiện từ filesystem, driver, inode và mount options. Một SSD NVMe thông thường không tự cho CPU load/store byte-addressable qua ánh xạ DAX heap.

### 5.3. Kịch bản launch có điều kiện rõ ràng

**Template chỉ dùng sau khi phần cứng/OS/JDK đã được xác minh**, giả sử có ứng dụng `service.jar` và mount DAX phù hợp `/mnt/memory-tier`:

```bash
# Baseline trên heap mặc định của runtime:
java -Xms2g -Xmx2g -jar service.jar

# Candidate: cùng JDK, GC, heap, workload; thay CHỈ backing heap:
java -Xms2g -Xmx2g \
     -XX:AllocateHeapAt=/mnt/memory-tier \
     -jar service.jar
```

Đây là cú pháp **POSIX shell**; nối dòng bằng `\` không hoạt động như Bash trong Windows PowerShell. Những lệnh này **không chạy độc lập** vì cần `service.jar` thật, tài nguyên device phù hợp và OS/JVM hỗ trợ.

Không dùng đường dẫn thực tế `/mnt/memory-tier` nếu nó là một thư mục trên SSD/file cache bình thường rồi coi kết quả là non-DRAM heap. Phải xác nhận mapping.

### 5.4. Kiểm tra flag và JVM thật

Trên HotSpot JDK có hỗ trợ:

```bash
java -version
java -XX:+PrintFlagsFinal -version
java -Xlog:help
```

Tìm giá trị `AllocateHeapAt` cùng flags heap/GC liên quan trong `PrintFlagsFinal` hoặc lệnh tương ứng trên JDK đang chạy. Cú pháp JDK 25 chính thức có `-XX:AllocateHeapAt=<path>`, nhưng **Java SE specification không bắt mọi JVM vendor phải hỗ trợ**.

Ngoài ra, cần xem log startup của **candidate với path thật** để xác nhận:
- VM không cảnh báo flag unsupported/ignored;
- quá trình map thành công;
- không fallback âm thầm sang DRAM;
- GC tương thích;
- process khởi động và hoạt động đúng.

**Không chỉ dùng việc JVM thoát với code 0** làm bằng chứng heap thực sự nằm trên device; kiểm tra process mappings/device tiers bằng OS diagnostics, vì mục tiêu benchmark là **memory placement thực**.

### 5.5. Không được bỏ qua các vùng DRAM còn lại

Mô tả chính thức của `AllocateHeapAt` nói **code heap, metaspace và thread stacks** vẫn ở DRAM. Ứng dụng còn:
- direct buffers/native allocations;
- mapped files khác;
- kernel/page cache;
- GC/compiler working memory;
- thread-local buffers và runtime structures.

Nếu thiết bị thay thế có capacity lớn hơn nhưng DRAM host quá ít cho phần còn lại, JVM vẫn có thể lỗi hoặc latency xấu. Đánh giá **tổng memory footprint** và không coi “heap đã được chuyển đi” là giải pháp tự động cho mọi OOM.

## 6. Baseline/candidate: đổi một yếu tố, giữ các yếu tố còn lại

### 6.1. Ma trận thí nghiệm tối thiểu

| Run | Heap backing | Các điều kiện còn lại | Mục tiêu |
| --- | --- | --- | --- |
| A | DRAM/default heap | JDK/GC/Xms/Xmx/CPU/workload cố định | Baseline |
| B | Thiết bị nhớ alternative đã xác minh | **Giữ như A**, chỉ thêm `AllocateHeapAt` | Tác động của memory placement |
| C | Alternative nhưng khác NUMA placement (nếu hợp lệ) | Ghi rõ thay đổi topology | Điều tra locality, **không gộp vào so A/B** |
| D | Thiết bị alternative với GC khác | Chỉ khi cần nghiên cứu tuning riêng | Không quy toàn bộ chênh lệch cho device |

**Một điều kiện phải đặc biệt thống nhất:** nếu candidate chứa live-set lớn gấp đôi baseline vì có thêm capacity thì bạn đã thay **cả kích thước dữ liệu**. So sánh ấy có thể hữu ích cho nghiệp vụ, nhưng không cô lập tác động hiệu năng của device. Cần hai vòng:
1. **Same-footprint comparison:** dataset, heap size và request mix giống nhau.
2. **Capacity-benefit comparison:** để candidate chạy workload lớn hơn (và ghi rõ baseline không đáp ứng quy mô ấy), đo value/cost/SLO tổng thể.

### 6.2. Các biến phải khóa

- JDK distribution, update/build, architecture, JVM flags, GC.
- `-Xms`/`-Xmx` và heap region sizing nếu đã được cấu hình riêng.
- Startup/classpath/application artifact, library versions.
- CPU cores/quota/affinity, NUMA locality và mức nhiệt độ.
- OS/kernel, drivers, firmware, filesystem flags.
- Workload input, dataset size, hot/cold proportions.
- Load generator, arrival rate, concurrency và retry policy.
- Chính sách page cache/page faults/warmup.
- Số lần chạy, độ dài mỗi run và thời điểm lấy mẫu.
- Cách định nghĩa successful operations/timeout/latency.

Nếu B chạy trên JDK 25 nhưng A chạy JDK 17, kết quả không đủ để kết luận lợi ích do memory device. Nếu A dùng G1 và B dùng ZGC, cũng không cô lập được memory tier.

### 6.3. Random hóa/đảo thứ tự và nhiều runs

Chạy A rồi B đúng một lần có thể tạo **thứ tự bias**:
- page cache/file mappings của run sau đã nóng;
- GC/JIT đã warm ở trạng thái khác;
- host CPU contention thay đổi;
- device temperature/power state biến đổi;
- NUMA placement của run sau may mắn hơn.

Nên lặp theo thứ tự xen kẽ/random như `A-B-B-A` qua nhiều trials, có reset/warmup policy được mô tả. Báo **median, p95 hoặc confidence interval** của từng chỉ số phù hợp, kèm số lượng samples/trials và số lần fail.

**Không nên** coi “candidate tốt hơn 1,5% trong một run” là bằng chứng chắc chắn nếu độ nhiễu là ±5%.

### 6.4. Workload phải chạm heap thật

Những workload quan trọng:
- large object graph traversal, pointer-heavy structures;
- in-memory indices, search, map/tree/graph;
- write-intensive mutation và queues;
- GC-intensive allocation/copy;
- mixed read/write với concurrency production;
- startup loading large dataset;
- scan/batch với working set lớn hơn cache;
- dịch vụ đầu cuối gồm DB/network để đánh giá lợi ích thật.

**Tránh chỉ benchmark phép cộng integer trong một vòng lặp**, vì không buộc VM truy cập memory tier. Tương tự, throughput của tệp SSD qua `fio` **không** thể thay cho heap memory-access latency; đó là một loại benchmark storage khác.

## 7. Microbenchmark JMH: hiểu sức mạnh và giới hạn

### 7.1. Tại sao không dùng một vòng lặp `nanoTime` tùy tiện?

Microbenchmark Java dễ sai vì:
- JIT loại bỏ dead code.
- Loop invariant bị chuyển ra ngoài vòng lặp.
- Dữ liệu nằm trong CPU cache.
- Escape analysis chuyển allocation ra khỏi heap.
- Warmup chưa đủ nên đo interpreter/JIT compilation.
- GC pause hoặc safepoint trộn vào mẫu.
- Timer overhead quá lớn khi mỗi operation chỉ vài ns.
- Không có process forks và trạng thái CPU/NUMA ổn định.

**JMH (Java Microbenchmark Harness)** là bộ công cụ của OpenJDK giúp quản lý forks, warmup, measurement modes, threading, result consumption và thống kê. **Nên dùng một project JMH được build riêng**, thay vì chép một benchmark vào `main` ứng dụng production.

### 7.2. JMH ví dụ: dependent array reads

Đây là **class JMH**, cần các dependencies và annotation processing của JMH (ví dụ project Maven archetype theo README chính thức), **không** chạy được chỉ bằng `javac HeapPointerChase.java` trên JDK trống.

```java
package bench;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 2)
@Measurement(iterations = 8, time = 2)
@Fork(3)
public class HeapPointerChase {
    // 4 MiB hoặc 128 MiB cho int[]; 128 MiB có thể vượt LLC
    // nhưng phải kiểm tra cache thực của máy.
    @Param({"1048576", "33554432"})
    public int elements;

    private int[] next;
    private int cursor;

    @Setup(Level.Trial)
    public void init() {
        next = new int[elements];
        int mask = elements - 1;
        for (int i = 0; i < elements; i++) {
            next[i] = (i + 8191) & mask;
        }
        cursor = 0;
    }

    @Benchmark
    public int dependentReads() {
        int x = cursor;
        for (int i = 0; i < 4096; i++) {
            x = next[x]; // Mỗi index phụ thuộc load trước.
        }
        cursor = x;
        return x;        // Dùng kết quả, hạn chế bị loại bỏ.
    }
}
```

**Cách diễn giải đúng:**
- Mỗi benchmark invocation chạy **4096 dependent array loads**, không phải một load.
- JMH `ns/op` ở đây tính theo **một invocation**, không tự động là `ns/load`. Muốn ước tính `ns/load`, chia `ns/op` cho 4096, ghi đây là **ước lượng**, chưa trừ loop/benchmark overhead.
- Dữ liệu 4 MiB có thể vừa vào cache, 128 MiB có thể vượt LLC; mức cache thực phải xem trên host.
- Stride 8191 trên mảng lũy thừa hai tạo chu kỳ qua nhiều phần tử và tránh chỉ đọc một phần tử cố định. Nhưng working-set access/memory-tier coverage vẫn phải xác minh với profiler.
- `@Fork(3)` là **ba JVM fork** dùng cờ JVM của cấu hình benchmark. Khi chạy candidate, cần truyền cờ `AllocateHeapAt` tới **JVM forks** của JMH, không chỉ đến launcher parent.
- Benchmark này không đo write bandwidth hay service SLO; cần thêm test khác cho những yếu tố ấy.

Để khởi tạo môi trường đúng, dùng hướng dẫn **OpenJDK JMH README** (Maven archetype) và build benchmark jar; truyền các VM flags qua cơ chế `jvmArgs`/CLI mà JMH bản đang dùng hỗ trợ. **Không ghi số kết quả cố định** vì giá trị hoàn toàn tùy CPU, memory tier, GC và dữ liệu.

### 7.3. Benchmark băng thông cần thêm một bài khác

Một bài JMH bandwidth hợp lý thường:
- dùng arrays/buffers rất lớn so với cache mục tiêu;
- thực hiện sequential read, sequential write và mixed copy riêng;
- đếm **bytes thực sự đọc/ghi**, không tự nhân đôi khi JVM cache/write-combining tác động;
- dùng state/object tránh bị tối ưu biến mất, và verify kết quả;
- test nhiều thread counts để thấy saturation;
- trả `GiB/s` ở cùng kích thước/iteration;
- theo dõi GC allocation/timing, không biến benchmark thành phép đo object creation nếu mục tiêu là memory bandwidth.

**Không** khẳng định `System.arraycopy`, một câu lệnh Java hay `fio` có thể đo chính xác băng thông của **mọi** memory-like devices. Native/OS profilers hoặc hardware counters có thể hữu ích để kiểm tra các kết luận ở lớp vật lý.

## 8. End-to-end load test: cổng chấp nhận nằm ở SLO ứng dụng

### 8.1. SLO phải định nghĩa trước

Ví dụ một service có:
- `p99 request latency <= 10 ms` ở mức tải mục tiêu;
- throughput **ít nhất 90%** baseline DRAM;
- error rate không vượt ngưỡng dự án;
- p99 GC pause không vượt giới hạn;
- không có crash, dữ liệu sai hoặc restart failure trong soak test;
- lợi ích capacity/cost đủ lớn để bù chi phí vận hành.

Các ngưỡng này chỉ là **minh họa cách đặt policy**, không phải tiêu chuẩn Java hoặc SLA chung của mọi ứng dụng.

### 8.2. Đo nhiều mức tải

Không chỉ chọn một tải thấp. Hãy đo:
1. Load thấp để quan sát baseline overhead.
2. Load đại diện production.
3. Load sát ngưỡng saturation.
4. Burst/peak để quan sát queueing và GC.
5. Soak workload có working set đầy, concurrency và read/write mix thực.

Nếu mọi request chờ external DB trong test, khác biệt memory tier có thể bị che. Nhưng vẫn cần end-to-end test bởi SLO là trải nghiệm người dùng. Kết hợp microbenchmark và service-level metrics để hiểu nguyên nhân.

### 8.3. Latency và throughput phải đi cùng tỷ lệ lỗi

Giả sử candidate trả 39.000 successful ops/s nhưng bỏ qua 5% request do lỗi: số requests được **gửi** có thể cao nhưng chất lượng dịch vụ giảm. Báo:
- offered requests/s;
- successful completed requests/s;
- non-2xx/error/timeout counts;
- latency distributions của cả request thành công và thất bại theo quy ước;
- queue wait và concurrency;
- retry storm/backpressure.

Không tự bỏ failed requests khỏi mẫu để khiến candidate “nhanh hơn”.

### 8.4. GC là đường truy cập heap quan trọng

GC có thể **đọc/ghi/quét/di chuyển object** ở những pattern khác mã nghiệp vụ. Vì vậy candidate memory tier có thể ảnh hưởng:
- thời gian pause (p95/p99/p99.9);
- concurrent marking/scanning overhead;
- heap evacuation/copy bandwidth;
- allocation stalls hoặc GC cycle duration;
- CPU utilization và memory bandwidth consumed bởi GC;
- process footprint và native memory.

**Giữ cùng GC/heap/flags** ở vòng A/B đầu. Dùng GC khác là thí nghiệm tuning thứ hai, có báo riêng. Không áp một GC tối ưu cho DRAM vào device khác rồi kết luận mọi collector đều tệ như nhau; cũng không tùy tiện đổi GC trên candidate trong lúc đo “tác động device”.

### 8.5. JFR và GC logs: dùng đúng phạm vi

Trên HotSpot JDK 25, có thể dùng Java Flight Recorder và unified logging để khảo sát hành vi JVM:

```bash
# Mẫu khởi động với GC log, yêu cầu service.jar thật:
java -Xms2g -Xmx2g \
     -Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags \
     -jar service.jar

# Chẩn đoán một JVM đang chạy (đúng PID/quyền attach):
jcmd <PID> JFR.start name=memorytest settings=profile duration=60s filename=memorytest.jfr
jcmd <PID> GC.heap_info
```

Đây là **template cho môi trường có JVM tương thích**, không phải lệnh chạy độc lập; `<PID>` phải thay bằng PID thật. Không chạy lệnh phá hủy workload khi đang đo production. JFR giúp xem GC, allocation, CPU, thread stalls; **nó không tự chứng minh memory tier của mỗi heap page**. Cần kết hợp OS/NUMA/DAX mapping.

Với latency microsecond/nanosecond, độ chi tiết logging/profiling cũng có overhead. Nên có hai pha:
- **Benchmark chính:** cùng mức instrumentation, càng cân bằng càng tốt.
- **Diagnostic run:** JFR/profiler/log chi tiết có thể dùng để giải thích, không dùng số liệu trộn lẫn vào A/B chính nếu overhead khác nhau.

Oracle JDK 25 troubleshooting guide lưu ý bật **JFR Heap Statistics** có thể tạo old collections và ảnh hưởng pause. Đừng bật tính năng đó trong run chính nếu đang đánh giá tail GC latency.

## 9. Page faults, NUMA và device placement: kiểm tra thực sự có thử đúng thứ cần thử không

### 9.1. First-touch và fault có thể ảnh hưởng thời gian ban đầu

Một `mmap` chưa chắc đã làm mọi page có physical backing và resident ngay. Truy cập lần đầu có thể phát sinh page faults/làm công việc mapping. Nếu chỉ đo một đợt rất ngắn, candidate có thể tệ do **cold faulting** chứ không đại diện steady-state memory latency.

Báo **hai loại kết quả**:
- **Cold start/first-touch:** từ launch hoặc mapping tới khi working set đã được chạm.
- **Warm steady access:** sau warmup/memory residency phù hợp.

Không tráo chúng cho nhau. Với dịch vụ scale-to-zero hoặc batch ngắn, cold behavior là KPI rất quan trọng; với service chạy nhiều ngày, steady behavior cũng cần đo.

### 9.2. Major vs minor faults

Linux/OS có thể báo major/minor page faults, nhưng cách phân loại phụ thuộc mapping/file/device và kernel. Một **minor fault** vẫn có chi phí page-table/mapping; một **major fault** có thể chờ I/O. DAX có semantics riêng nên không nên suy từ một counter duy nhất rằng “heap đã hoàn toàn trong DRAM” hay “DAX không hoạt động”.

Cần xem `/proc/<PID>/stat` hoặc công cụ OS được cho phép, đồng thời kết hợp:
- map file/device thật;
- DAX inode/mount state;
- tier/NUMA page placement khi có số liệu;
- OS fault/latency counters;
- JVM logs và application performance.

### 9.3. Local vs remote NUMA

Một heap được map trên một NUMA node xa CPU có thể chậm vì **interconnect latency**, dù memory type giống DRAM. Ngược lại, CPU affinity khác nhau có thể che tác động một device chậm hơn.

A/B phải ghi:
- CPU affinity/cpuset;
- NUMA topology;
- memory tier/node placement;
- thread pinning nếu dùng;
- OS automatic NUMA balancing/tiering/migration policy;
- CPU frequency/power và node contention.

Các công cụ Linux như `numactl --hardware`, `numastat -p <PID>` và `/proc/<PID>/numa_maps` có thể hỗ trợ, nhưng **không phải mọi loại DAX/devices đều được các công cụ đó hạch toán giống DRAM**. Không đặt quy tắc “numastat có số X => heap chắc chắn trên tier Y” mà không đối chiếu mapping/driver.

### 9.4. Device health và thermal state

Một thí nghiệm 30 giây có thể bỏ sót:
- thermal throttling sau nhiều phút;
- hiệu ứng khi device gần đầy;
- corrected/uncorrectable media errors;
- degraded mode sau số lỗi tăng;
- capacity/firmware wear và recoverability;
- downtime do maintenance;
- host memory pressure/hotplug events.

Nếu thiết bị chỉ đạt p99 tốt khi rảnh/mát, nhưng tệ ở tải kéo dài, phải dùng **soak và stress tests có kiểm soát** trước khi triển khai production.

## 10. Độ ổn định: kiểm thử như một nền tảng hạ tầng, không chỉ như một benchmark

### 10.1. Các nhóm rủi ro và bài test

| Nhóm | Kịch bản cần thử | Tiêu chí quan sát |
| --- | --- | --- |
| Startup/mount | Device path không tồn tại, sai quyền, filesystem không DAX | JVM fail rõ; không chạy nhầm backing khác |
| Capacity | Không đủ vùng memory cho `-Xmx` và các allocations | Lỗi/limit rõ; không ảnh hưởng các process khác |
| Long-running | 24h/72h hoặc thời lượng theo SLO, workload thực | Không crash, memory leak, error spike, latency drift |
| High occupancy | Live set lớn gần capacity vận hành | Tail latency và GC vẫn đạt SLO |
| Concurrency | Nhiều threads, nhiều JVM/containers cùng dùng tier | Bandwidth contention, fairness, throttling |
| Restart | Khởi động/tắt service lặp lại bằng automation | Mọi lần restart thành công, cleanup và permission đúng |
| Failure injection | Mất device hoặc lỗi I/O **trong môi trường staging chuyên dụng** | Hành vi lỗi/failover theo thiết kế; không mất dữ liệu nghiệp vụ |
| Security | Residual bytes, ownership, access control, key management | Không lộ secrets, dọn artifact theo policy |
| Observability | JVM log, OS metrics, device health counters | Có thể phát hiện/map lỗi nhanh |
| Rollback | Khởi động lại trên DRAM baseline khi feature flag tắt | Service phục hồi và data source bền vững vẫn đúng |

**Không thực hiện tháo thiết bị, format filesystem, mô phỏng lỗi điện hoặc gây fault trên production** để chứng minh tính ổn định. Dùng staging, test hosts và công cụ fault-injection được đội hạ tầng phê duyệt.

### 10.2. Soak test cần định nghĩa thời lượng và mẫu

Một job chạy 72 giờ mà chỉ ghi “không thấy lỗi” là **thông tin chưa đầy đủ**. Báo:
- thời điểm bắt đầu/kết thúc;
- successful operations, errors, timeouts;
- p99/p99.9 theo **từng cửa sổ thời gian**, không chỉ một percentile tổng;
- throughput, GC pauses, page fault rates, CPU stalls;
- device temperature/health/firmware errors;
- số restarts được thử, số thất bại;
- mức dữ liệu/working set và read/write mix;
- workload drift và trạng thái OS.

**0 lỗi trong 100.000 requests không chứng minh xác suất lỗi thật bằng 0**. Đây là một quan sát với độ bất định; yêu cầu xác suất lỗi rất nhỏ cần tập mẫu lớn và/hoặc thử nghiệm mạnh hơn, tùy rủi ro.

### 10.3. Nguồn gốc/cleanup của mapped heap

Một filesystem-backed heap trên thiết bị persistent có thể để lại **residual data** hoặc tệp runtime tạm sau khi process crash tùy implementation/OS. Đây là chủ đề **bảo mật, compliance và disk hygiene**.

Cần:
- mountpoint/device permissions đúng;
- filesystem owner và access policy tối thiểu;
- không cho users không tin cậy đọc/sửa nội dung mapped area;
- mã hóa/secure erase hoặc lifecycle cleanup theo policy bảo mật, **không hứa rằng việc kill JVM đã xóa hết bytes vật lý**;
- inventory nơi data có thể tồn tại, key rotation và kiểm tra hậu crash khi phù hợp;
- tách business durability vào database/log được quản lý, không dựa vào memory image.

**Lưu ý:** đây không phải hướng dẫn dùng heap file như một storage format có thể phục hồi; đó chính là điều JEP 316 **không bảo đảm**.

### 10.4. Availability và fallback

Nếu service production phụ thuộc một mountpoint/device và nó không sẵn sàng, ứng dụng có thể không start. Thiết kế:
- kiểm tra device health trước deploy;
- readiness/health fail đúng khi JVM không dùng đúng memory tier;
- có cấu hình rollback tới DRAM và runbook;
- autoscaling/capacity planning nếu cluster thiếu node có device;
- tránh fallback âm thầm làm tài nguyên DRAM thiếu chỗ hoặc che lỗi thiết bị;
- ghi nguồn error, đường dẫn thiết bị, JDK build và trạng thái mapping để điều tra.

Một lựa chọn được phép là **fail-fast** khi memory tier không đáp ứng yêu cầu compliance/performance; lựa chọn khác là **explicit fallback to DRAM** khi có headroom và chính sách chấp thuận. **Không** cho rằng JVM tự fallback theo cùng một cách trên mọi bản JDK.

## 11. Cổng quyết định trước pilot

### 11.1. Tách điều kiện bắt buộc và mục tiêu kinh tế

Đặt hai lớp kiểm tra:

**Lớp A — Điều kiện tối thiểu để thử pilot:**
- Hardware/driver/DAX/JDK flags được xác minh.
- GC/heap workload chạy đúng, không data corruption.
- p99 request latency không vượt ngưỡng.
- Throughput nghiệp vụ không giảm quá mức cho phép.
- Memory bandwidth đáp ứng yêu cầu hot-path.
- Error/restart/soak tests đạt điều kiện đã định trước.
- Có observability, security policy và DRAM rollback.

**Lớp B — Lợi ích để cân nhắc đầu tư:**
- capacity nhiều hơn hoặc TCO/GiB thấp hơn ở SLO tương đương;
- số node/replica hoặc in-memory live set tăng có giá trị;
- tiết kiệm điện/DRAM footprint được đo sau khi tính device/OS cost;
- giảm cước cloud/hạ tầng mà không tăng rủi ro vận hành không chấp nhận.

**Không dùng capacity lớn làm lý do bỏ qua lỗi dữ liệu hoặc tail latency vượt SLO.**

### 11.2. Mẫu policy giả định minh họa

Giả sử baseline DRAM và hai candidates thử nghiệm với dữ liệu **giả lập**:

| Metric | DRAM baseline | Device A | Device B |
| --- | ---: | ---: | ---: |
| p99 service latency | 4,0 ms | 4,8 ms | 8,5 ms |
| Sustained bandwidth | 30 GiB/s | 26 GiB/s | 21 GiB/s |
| Successful throughput | 42.000 ops/s | 39.000 ops/s | 32.000 ops/s |
| Errors / 100.000 requests | 0 | 0 | 5 |
| Successful restarts / 100 | 100 | 100 | 96 |
| Capacity | 256 GiB | 512 GiB | 1.024 GiB |

**Policy minh họa**:
- Candidate p99 ≤ baseline × **1,25** (≤ 5,0 ms).
- Candidate bandwidth ≥ baseline × **0,80** (≥ 24,0 GiB/s).
- Candidate successful throughput ≥ baseline × **0,90** (≥ 37.800 ops/s).
- Candidate errors ≤ 1 trong ít nhất 100.000 requests.
- Có ít nhất 100 restarts và **tất cả** thành công.
- Capacity ≥ 2 × baseline.
- Hardware/DAX/JVM validation, cost, security và rollback phải được **kiểm tra riêng** trước production.

Kết luận từ bộ số **giả lập**:
- **Device A đạt** các cổng định lượng nêu trên → **đủ điều kiện cân nhắc pilot có kiểm soát**.
- **Device B không đạt** p99, bandwidth, throughput, reliability và restart dù có dung lượng gấp bốn → **không đạt pilot gate**.
- **Cả hai đều chưa được “phê duyệt production”** chỉ vì một bảng số liệu chưa đo thật.

Ngưỡng `25% p99 increase`, `20% bandwidth drop` hay `10% throughput drop` được chọn **chỉ để luyện thiết kế chính sách**. Dịch vụ có SLO chặt có thể không chấp nhận bất kỳ sự suy giảm nào, và một hệ thống batch có thể coi capacity quan trọng hơn p99 request.

### 11.3. Đừng chờ tới sau benchmark mới chọn ngưỡng

Nếu ngưỡng được lựa chọn **sau khi đã xem kết quả**, đánh giá dễ bị thiên lệch: bạn có thể nới SLO để candidate qua cổng. Nên:
1. Xác định SLO/guardrails với chủ hệ thống.
2. Định nghĩa các metric/measurement windows.
3. Xác định số samples/trials/soak duration, failure policy.
4. Khóa baseline và test setup.
5. Chạy và thu thập data.
6. Áp policy bằng mã/automation.
7. Tổ chức review về security/cost/fallback trước rollout.

## 12. Java 17+ lab hoàn chỉnh: áp dụng cổng quyết định bằng dữ liệu giả lập

### 12.1. Mục tiêu

`MemoryDeviceDecisionLab` **không** đo băng thông DRAM hoặc DAX thật, **không** khởi chạy với `AllocateHeapAt`, không đọc thiết bị và không chứng minh một candidate ngoài đời đạt SLO. Nó lấy **ba bản ghi synthetic** theo bảng trên rồi tính các điều kiện pass/fail một cách xác định.

Điều này rất hữu ích để:
- phân biệt **p99 threshold** với **mean latency**;
- nhìn thấy vì sao bandwidth/throughput cần cả hai;
- buộc kiểm tra reliability, restart và capacity;
- không tự đưa một candidate vào production chỉ vì có capacity lớn.

Chương trình chạy **Java 17+**, không cần thư viện, có **29 dòng stdout chính xác**.

### 12.2. Mã `MemoryDeviceDecisionLab.java`

```java
import java.util.Locale;

public class MemoryDeviceDecisionLab {
    // Dữ liệu báo cáo GIẢ LẬP: không phải phép đo phần cứng.
    record Metrics(
            String name,
            double p99Ms,
            double bandwidthGiBs,
            long successfulOpsPerSec,
            int errors,
            int requests,
            int restartSuccess,
            int restartAttempts,
            int capacityGiB) {

        Metrics {
            if (p99Ms <= 0 || bandwidthGiBs <= 0
                    || successfulOpsPerSec < 0
                    || errors < 0 || requests <= 0
                    || errors > requests
                    || restartSuccess < 0
                    || restartAttempts <= 0
                    || restartSuccess > restartAttempts
                    || capacityGiB <= 0) {
                throw new IllegalArgumentException(
                        "invalid metrics");
            }
        }
    }

    static boolean latencyOk(Metrics base, Metrics c) {
        return c.p99Ms() <= base.p99Ms() * 1.25;
    }

    static boolean bandwidthOk(Metrics base, Metrics c) {
        return c.bandwidthGiBs()
                >= base.bandwidthGiBs() * 0.80;
    }

    static boolean throughputOk(Metrics base, Metrics c) {
        return c.successfulOpsPerSec()
                >= base.successfulOpsPerSec() * 0.90;
    }

    static boolean reliabilityOk(Metrics c) {
        return c.errors() <= 1 && c.requests() >= 100_000;
    }

    static boolean restartsOk(Metrics c) {
        return c.restartAttempts() >= 100
                && c.restartSuccess() == c.restartAttempts();
    }

    static boolean capacityOk(Metrics base, Metrics c) {
        return (long) c.capacityGiB()
                >= 2L * base.capacityGiB();
    }

    static boolean eligible(Metrics base, Metrics c) {
        return latencyOk(base, c)
                && bandwidthOk(base, c)
                && throughputOk(base, c)
                && reliabilityOk(c)
                && restartsOk(c)
                && capacityOk(base, c);
    }

    public static void main(String[] args) {
        Metrics base = new Metrics(
                "DRAM", 4.0, 30.0, 42_000,
                0, 100_000, 100, 100, 256);
        Metrics a = new Metrics(
                "A", 4.8, 26.0, 39_000,
                0, 100_000, 100, 100, 512);
        Metrics b = new Metrics(
                "B", 8.5, 21.0, 32_000,
                5, 100_000, 96, 100, 1024);

        System.out.printf(Locale.ROOT,
                "baseline p99 ms: %.1f%n", base.p99Ms());
        System.out.printf(Locale.ROOT,
                "policy max p99 ms: %.1f%n",
                base.p99Ms() * 1.25);
        System.out.printf(Locale.ROOT,
                "policy min bandwidth GiB/s: %.1f%n",
                base.bandwidthGiBs() * 0.80);
        System.out.printf(Locale.ROOT,
                "policy min successful ops/s: %.0f%n",
                base.successfulOpsPerSec() * 0.90);

        System.out.printf(Locale.ROOT,
                "candidate A p99 ms: %.1f%n", a.p99Ms());
        System.out.printf(Locale.ROOT,
                "candidate A bandwidth GiB/s: %.1f%n",
                a.bandwidthGiBs());
        System.out.println("candidate A successful ops/s: "
                + a.successfulOpsPerSec());
        System.out.printf(Locale.ROOT,
                "candidate A capacity ratio: %.1f%n",
                (double) a.capacityGiB()
                    / base.capacityGiB());

        System.out.println("candidate A p99 gate: "
                + latencyOk(base, a));
        System.out.println("candidate A bandwidth gate: "
                + bandwidthOk(base, a));
        System.out.println("candidate A throughput gate: "
                + throughputOk(base, a));
        System.out.println("candidate A errors gate: "
                + reliabilityOk(a));
        System.out.println("candidate A restart gate: "
                + restartsOk(a));
        System.out.println("candidate A pilot eligible: "
                + eligible(base, a));

        System.out.println("candidate B p99 gate: "
                + latencyOk(base, b));
        System.out.println("candidate B bandwidth gate: "
                + bandwidthOk(base, b));
        System.out.println("candidate B throughput gate: "
                + throughputOk(base, b));
        System.out.println("candidate B errors gate: "
                + reliabilityOk(b));
        System.out.println("candidate B restart gate: "
                + restartsOk(b));
        System.out.println("candidate B pilot eligible: "
                + eligible(base, b));
        System.out.println(
                "candidate B larger capacity alone enough: "
                        + eligible(base, b));

        System.out.printf(Locale.ROOT,
                "latency ratio A: %.2f%n",
                a.p99Ms() / base.p99Ms());
        System.out.printf(Locale.ROOT,
                "bandwidth relative A percent: %.1f%n",
                a.bandwidthGiBs() * 100.0
                    / base.bandwidthGiBs());
        System.out.printf(Locale.ROOT,
                "throughput relative A percent: %.1f%n",
                a.successfulOpsPerSec() * 100.0
                    / base.successfulOpsPerSec());

        System.out.println("candidate A incidents: "
                + a.errors() + "/" + a.requests());
        System.out.println("candidate B incidents: "
                + b.errors() + "/" + b.requests());
        System.out.println("candidate A restarts: "
                + a.restartSuccess()
                + "/" + a.restartAttempts());
        System.out.println("candidate B restarts: "
                + b.restartSuccess()
                + "/" + b.restartAttempts());
        System.out.println(
                "synthetic inputs, not benchmarks: true");
    }
}
```

### 12.3. Biên dịch và chạy

Dùng JDK 17+ đang được hỗ trợ:

```bash
javac MemoryDeviceDecisionLab.java
java MemoryDeviceDecisionLab
```

Lab không cần thiết bị đặc biệt; không cài `-XX:AllocateHeapAt` và không stress memory. Có thể chạy trên Windows/Linux/macOS theo contract Java 17+.

### 12.4. Stdout chính xác — 29 dòng

```text
baseline p99 ms: 4.0
policy max p99 ms: 5.0
policy min bandwidth GiB/s: 24.0
policy min successful ops/s: 37800
candidate A p99 ms: 4.8
candidate A bandwidth GiB/s: 26.0
candidate A successful ops/s: 39000
candidate A capacity ratio: 2.0
candidate A p99 gate: true
candidate A bandwidth gate: true
candidate A throughput gate: true
candidate A errors gate: true
candidate A restart gate: true
candidate A pilot eligible: true
candidate B p99 gate: false
candidate B bandwidth gate: false
candidate B throughput gate: false
candidate B errors gate: false
candidate B restart gate: false
candidate B pilot eligible: false
candidate B larger capacity alone enough: false
latency ratio A: 1.20
bandwidth relative A percent: 86.7
throughput relative A percent: 92.9
candidate A incidents: 0/100000
candidate B incidents: 5/100000
candidate A restarts: 100/100
candidate B restarts: 96/100
synthetic inputs, not benchmarks: true
```

Đã kiểm thử bộ tính toán bằng **JDK hiện đại** với các fixtures trên. `Locale.ROOT` giúp dấu thập phân ổn định khi in số. Kết quả “pilot eligible: true” nghĩa là **chỉ vượt các ngưỡng synthetic mà lab đặt ra**, **không** là quyết định vận hành thực tế hay phát biểu về hiệu năng một thiết bị nhớ cụ thể.

### 12.5. Phân tích kết quả

**Device A — p99:** `4.8/4.0=1.20`, tức tăng 20%, vẫn dưới ngưỡng tăng 25%. Tuy nhiên một ứng dụng có `p99 <=4.5ms` thì candidate A sẽ bị loại. SLO phải được chọn trước.

**Device A — bandwidth:** `26/30×100≈86.7%` baseline, cao hơn ngưỡng 80%. Không phải thiết bị A “nhanh hơn DRAM”; nó có thể **chậm hơn** về bandwidth nhưng đủ điều kiện cho một tradeoff capacity/cost.

**Device A — throughput:** `39000/42000×100≈92.9%`, đáp ứng ngưỡng ≥90% trong ví dụ.

**Device A — reliability:** 0 lỗi trên 100.000 requests và 100/100 restart thành công theo fixture. Đó là một **quan sát giả lập**; kể cả dữ liệu thật với 0 lỗi cũng **không chứng minh rủi ro bằng 0**. Phải tiếp tục soak, fault-recovery, health, backup và monitoring.

**Device A — capacity:** 512 GiB so với baseline 256 GiB, ratio 2.0. Lợi ích kinh tế thật còn cần giá, bảo trì, điện, procurement, availability và DRAM còn dùng cho phần non-heap.

**Device B:** capacity 1.024 GiB vượt gấp bốn, nhưng p99, bandwidth, throughput, errors, restart đều không đạt → không vào pilot theo policy đó. Đây là cách tránh đánh đổi **data correctness/availability** chỉ để có nhiều memory hơn.

**Kết quả này không so sánh mọi device có thật.** Nó là bài học về ra quyết định có nhiều guardrails, không phải bảng xếp hạng DRAM/NVDIMM/CXL.

## 13. Báo cáo thí nghiệm nên có cấu trúc nào?

### 13.1. Mẫu báo cáo

| Hạng mục | Cần ghi |
| --- | --- |
| Objective | Giảm chi phí/GiB hay tăng capacity mà không phá SLO |
| JDK/runtime | Distribution, major/update/build, HotSpot flags, GC |
| Device | Loại thiết bị, firmware, driver, DAX/NUMA mode, capacity, health |
| Mapping verification | Bằng chứng heap thật ở đúng memory tier |
| Platform | OS/kernel, CPU/NUMA topology, container/cgroup settings |
| Baseline | Heap DRAM, cùng `-Xms/-Xmx`, app artifact và workload |
| Candidate | `-XX:AllocateHeapAt`, device path, same setup |
| Workload | Dataset size, object graph, read/write ratio, concurrency |
| Measurement | JMH suite, service load test, GC logs/JFR, OS profiler |
| Latency | access ns/op, service p50/p95/p99/p99.9, timeout |
| Bandwidth | sustained read/write GiB/s và thread count |
| Throughput | successful ops/s và error rate |
| Memory/GC | resident footprint, heap usage, GC pause/cycle metrics |
| Stability | soak hours, failed requests, device errors, restarts, rollback |
| Statistics | number of runs, sample counts, variance/CI, A/B order |
| Cost & supply | price/usable GiB, warranty/firmware lifecycle, operations |
| Decision | GO to pilot / HOLD / NO-GO, reasons, owner, next steps |

Một báo cáo “heap trên device nhanh hơn DRAM 10%” nhưng không nói **metric nào**, dữ liệu nào, JDK/GC, sample size hay mapping verification thì **không đủ** để ra quyết định.

### 13.2. Dùng đúng mốc thời gian

Chỉ số startup:
- launch → JVM ready;
- launch → application ready;
- first successful request.

Chỉ số steady:
- warmup đủ để JIT/GC ổn định;
- đo continuous load 5–30 phút hoặc thời lượng phù hợp;
- latency/throughput/error theo cửa sổ;
- đo nhiều lần, không tính training/setup vào từng request.

Chỉ số stability:
- soak 24/72 giờ hoặc theo yêu cầu;
- memory occupancy thay đổi và device health;
- restart/loss-of-mount staging;
- failover và rollback.

Các mốc này **không thay thế nhau**. Candidate có startup chậm hơn nhưng throughput cao hơn vẫn phải được đánh giá theo SLO thật.

### 13.3. Tiêu chí về dữ liệu và tính toàn vẹn

Memory tier dùng cho Java heap phải duy trì **Java semantics** mà ứng dụng trông đợi:
- đọc/ghi đúng, atomicity cần thiết;
- không có silent corruption;
- GC heap vẫn nhất quán;
- sau lỗi phần cứng, service phát hiện và phản ứng đúng chính sách;
- dữ liệu nghiệp vụ bền vững lưu ở hệ thống có contract rõ;
- không leak residual secrets trong file/device.

**Không chọn thiết bị chỉ vì bảng bandwidth tốt**, nếu nó không thỏa điều kiện atomic operations hoặc error handling. Một Java application chạy pass unit tests vài phút chưa đủ xác nhận reliability trên hardware/mapping mới.

## 14. Các lỗi/hiểu nhầm thường gặp

| Nhận định sai | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “`-XX:AllocateHeapAt` làm Java heap tự bền vững” | Không có object-graph recovery/persistence contract | Dùng database/log cho dữ liệu bền vững |
| “Mọi SSD đều dùng làm mapped Java heap non-DRAM” | SSD block I/O ≠ memory-like DAX load/store semantics | Kiểm tra hardware, driver, inode DAX |
| “Chỉ cần path tồn tại là heap đã dùng device” | Có thể map không đúng tier/không support | Verify startup log, OS mappings và placement |
| “CXL memory luôn giống filesystem DAX” | CXL có nhiều mode memory topology khác nhau | Dựa vào OS exposure và JDK support |
| “JDK 10 flag đã chắc bị xóa nên không cần xem JDK mới” | `AllocateHeapAt` vẫn được Oracle JDK 25 tài liệu hóa | Kiểm tra runtime hiện hành |
| “Optane PMem là lựa chọn mua mới mặc định” | Dòng sản phẩm đã bị Intel ngừng phát triển/EOL | Xác minh hardware support/lifecycle hiện tại |
| “Object heap ở device nghĩa metaspace/stacks cũng ở đó” | JDK manpage nêu những vùng ấy vẫn ở DRAM | Đo toàn bộ process RAM/NUMA |
| “Sequential GiB/s cao nghĩa p99 tốt” | Bandwidth và random access latency khác | Đo cả hai và SLO end-to-end |
| “Một `int[1024]` đủ benchmark device latency” | Dữ liệu có thể ở CPU cache | Working set vượt cache, dependent loads |
| “Java `nanoTime` quanh một vòng lặp là benchmark chuẩn” | JIT/warmup/GC/timer overhead | Dùng JMH + profiler + service load test |
| “JMH ns/op là ns/array access” | Một invocation có thể thực hiện nhiều loads | Đếm operations thực và mô tả normalization |
| “Chạy B sau A một lần là đủ” | Cache, nhiệt độ, noise và thứ tự bias | Nhiều trials, đảo A/B |
| “Không đo GC cũng kết luận device an toàn” | GC quét/copy object và có tail pauses | JFR/GC logs/allocations |
| “Mean latency như nhau nên user experience không đổi” | Tail p99/p99.9 có thể xấu | Đo latency distribution |
| “Bỏ timeouts khỏi latency khiến báo cáo chính xác” | Survival bias/coordinated omission | Báo cả failure/timeout, offered load |
| “Tổng iostat throughput là Java heap bandwidth” | Block/file I/O counters khác load/store heap | Dùng memory benchmark và device-specific counters |
| “Một `numastat` output đủ chứng minh DAX placement” | DAX/accounting có thể khác conventional pages | Dùng mapping/driver/inode evidence |
| “DRAM cao hơn capacity nên candidate luôn tốt” | Tail latency, GC, lỗi và vận hành quan trọng | Predeclared gate và cost-benefit |
| “Chỉ cần 0 lỗi trong một giờ là production ready” | Rare events cần samples/soak và fault tests | Đo đủ reliability và rollback |
| “Kernel crash data còn đó nghĩa có thể restore Java heap” | Memory image không có Java persistence contract | Không dùng heap file như database |
| “Đổi GC/JDK đồng thời không sao” | Confounding variables | Tách riêng từng thí nghiệm |
| “Đưa tên path vào JDK command nghĩa flag cross-platform” | Flag là HotSpot/platform-dependent | Kiểm tra OS/JVM/GC support |

## 15. Bài tập có đáp án

### Bài 1 — Mục tiêu JEP 316

**Đề:** JEP 316 trong Java 10 được thiết kế để mọi object Java tự persist sau restart đúng không?

**Đáp án:** Không. JEP 316 cho phép **đặt object heap trên alternative memory device** với load/store semantics phù hợp. Không có contract phục hồi object graph và JVM state qua crash.

### Bài 2 — Tính phù hợp của filesystem

**Đề:** Bạn có một SSD NVMe chứa thư mục `/mnt/data`. Có thể gọi `java -XX:AllocateHeapAt=/mnt/data` và khẳng định đang đo non-DRAM memory-like device không?

**Đáp án:** Không. Directory path không chứng minh device memory-addressable/DAX. Phải kiểm tra hardware/driver/filesystem/inode DAX và VM mapping.

### Bài 3 — Phân biệt latency và bandwidth

**Đề:** Candidate có sequential bandwidth 30 GiB/s gần DRAM, nhưng random read latency gấp đôi. Có mâu thuẫn không?

**Đáp án:** Không. Bandwidth khi nhiều requests/prefetch có thể lớn, trong khi latency dependent load vẫn cao. Workload pointer chasing có thể chịu tác động mạnh.

### Bài 4 — Chọn working set

**Đề:** Vì sao benchmark dùng 4 KiB array không thể mô tả hiệu năng memory device có dung lượng 512 GiB?

**Đáp án:** Array có thể nằm hoàn toàn trong cache. Muốn nhìn memory tier cần working set đủ lớn và xác minh actual memory accesses.

### Bài 5 — Tỷ lệ latency candidate A

**Đề:** p99 DRAM 4,0 ms, candidate A 4,8 ms. Tăng bao nhiêu %?

**Đáp án:** `(4,8−4,0)/4,0×100=20%`. Với gate tối đa tăng 25%, candidate A qua gate **trong ví dụ giả định**.

### Bài 6 — Tỷ lệ bandwidth candidate A

**Đề:** DRAM 30 GiB/s, candidate A 26 GiB/s. Candidate còn bao nhiêu % baseline?

**Đáp án:** `26/30×100≈86,7%`, vượt gate ≥80% nhưng **không nhanh hơn DRAM** về metric này.

### Bài 7 — Throughput ứng dụng

**Đề:** Baseline 42.000 successful ops/s và candidate A 39.000. Tỷ lệ còn lại?

**Đáp án:** `39000/42000×100≈92,9%`, vượt gate ≥90%. Không gọi con số này là memory bandwidth.

### Bài 8 — Dung lượng candidate B

**Đề:** Candidate B có capacity gấp bốn DRAM nhưng p99 8,5 ms, throughput 32.000 ops/s, 5 lỗi và 4 restart thất bại. Có đủ để vào pilot theo policy trên không?

**Đáp án:** Không. Nó vượt capacity gate nhưng thất bại latency/bandwidth/throughput/reliability/restart. Không đánh đổi data correctness hoặc availability chỉ để có capacity.

### Bài 9 — JMH ns/op

**Đề:** JMH chạy 4096 dependent loads mỗi invocation. Nếu đo được 20.480 ns/op, có thể gọi đó là 20.480 ns cho mỗi load không?

**Đáp án:** Không. Ước lượng `20480/4096=5 ns/load`, chưa trừ overhead và ảnh hưởng cache/JIT; cần ghi số loads thực và cách chuẩn hóa.

### Bài 10 — Đo p99 bằng quá ít mẫu

**Đề:** 10 samples có một spike 100 ms. P99 tính ra 100 ms theo nearest-rank. Có đủ kết luận đây là p99 thực của service không?

**Đáp án:** Không. Quá ít mẫu để ước lượng tail dài hạn. Cần nhiều observations, trials, peak workload và failure accounting.

### Bài 11 — GC effects

**Đề:** Request p50 gần như không đổi nhưng GC pause p99 tăng mạnh. Có thể bỏ qua GC nếu throughput tốt hơn không?

**Đáp án:** Không nếu latency SLO nhạy với pause. Cần theo dõi p99/p99.9 service, GC logs/JFR và load mix tại peak.

### Bài 12 — CPU/NUMA confounding

**Đề:** Baseline chạy trên NUMA-local CPUs, candidate chạy trên NUMA-remote CPUs và khác CPU quota. Có thể quy chênh lệch cho memory device không?

**Đáp án:** Không. Cần kiểm soát CPU affinity/NUMA/cgroup hoặc tách thí nghiệm riêng.

### Bài 13 — 0 lỗi không phải xác suất lỗi 0

**Đề:** Trong 100.000 requests không thấy lỗi, có thể tuyên bố 100% không bao giờ lỗi không?

**Đáp án:** Không. Đó là một mẫu có độ bất định thống kê. Rare faults cần long-running tests, nhiều mẫu, fault injection an toàn và monitoring.

### Bài 14 — File heap và dữ liệu nhạy cảm

**Đề:** Process đã exit; có thể coi mọi bytes nhạy cảm trên memory-like persistent device tự biến mất không?

**Đáp án:** Không. Thiết bị có thể lưu residual bytes; cần access controls, data lifecycle và secure cleanup theo chính sách, không dựa vào process exit.

### Bài 15 — Phần còn ở DRAM

**Đề:** Dùng `-XX:AllocateHeapAt` có đưa thread stacks, metaspace và JIT code cache sang device không?

**Đáp án:** Theo mô tả Oracle JDK 25 của flag, **không**: những vùng ấy tiếp tục ở DRAM. Heap là thành phần được đặt lên memory device phù hợp.

### Bài 16 — Khi nào GO?

**Đề:** Candidate A qua 6 ngưỡng giả lập trong lab. Có nghĩa phải đưa production ngay không?

**Đáp án:** Không. Chỉ “đủ điều kiện cân nhắc pilot”. Trước production còn cần xác minh mapping, real benchmark, soak, error recovery, security, TCO, supply chain và rollback.

### Bài 17 — Lỗi thiết bị

**Đề:** Để chứng minh device recovery, có nên tháo nguồn bộ nhớ của một node production đang phục vụ user không?

**Đáp án:** Không. Fault injection phá hủy hoặc làm dữ liệu hỏng chỉ ở staging/test infrastructure có phép và runbook an toàn. Production cần chiến lược failover/rollback, không thao tác tùy tiện.

### Bài 18 — Dữ liệu JFR và placement

**Đề:** JFR cho thấy CPU/GC p99 tốt. Đã đủ chứng minh Java heap được map lên đúng memory tier chưa?

**Đáp án:** Chưa. JFR là JVM activity/latency evidence, không tự xác nhận placement. Phải xác minh DAX/file/device/NUMA mappings bên OS.

## 16. Checklist quyết định có nên áp dụng

- [ ] JDK/HotSpot distribution, update/build, OS và GC được xác minh hỗ trợ `AllocateHeapAt`.
- [ ] Kiểm tra hardware load/store semantics, atomic operations, driver và firmware.
- [ ] Device vẫn có nguồn hỗ trợ/maintenance; không mặc định mua hardware EOL.
- [ ] DAX/file mapping được xác minh **thực sự**; không lấy sự tồn tại của directory làm bằng chứng.
- [ ] Có bằng chứng heap nằm trên tier mong muốn, không fallback DRAM/page cache.
- [ ] Có baseline DRAM đúng cùng JDK/GC/`-Xms`/`-Xmx`/CPU/dataset.
- [ ] Phân biệt same-footprint và capacity-benefit workloads.
- [ ] Benchmark random dependent latency, sequential read/write bandwidth, object traversal và GC.
- [ ] Working set đủ lớn để không chỉ đo CPU cache.
- [ ] Dùng JMH với forks/warmup/measurement; không cho phép dead-code elimination hoặc benchmark vô nghĩa.
- [ ] Đếm đúng `ns/op` (per invocation) và bytes/s, không đổi đơn vị GiB/GB tùy ý.
- [ ] Đo end-to-end successful ops/s và p95/p99/p99.9 request latency ở các mức offered load.
- [ ] Báo timeouts/5xx, queue wait, retries; tránh coordinated omission và survival bias.
- [ ] Thu thập GC pause/cycle, allocation, CPU stalls, page faults, NUMA placement.
- [ ] Có cold-start/first-touch và warm steady-state kết quả riêng.
- [ ] Kiểm soát CPU quota, affinity, thermal/load, page cache và NUMA.
- [ ] Có nhiều trials, random/đảo A/B và báo độ biến thiên/confidence.
- [ ] Có soak test đủ lâu, báo lỗi per-window và device health.
- [ ] Có restart/failure-injection an toàn, không gây lỗi trên production.
- [ ] Có security policy cho mapped heap bytes và bảo vệ secrets.
- [ ] Không dùng memory heap như dữ liệu persistent có crash-recovery contract.
- [ ] Có rollback rõ ràng sang DRAM và đủ DRAM headroom khi cần fallback.
- [ ] Có cổng quyết định định trước gồm SLO + reliability + capacity/cost.
- [ ] Không đưa một candidate vào production chỉ vì capacity lớn hơn.
- [ ] Chạy `MemoryDeviceDecisionLab.java` và đối chiếu **29 dòng stdout giả lập**, không coi đó là benchmark thật.

## 17. Kết luận

**Đánh giá Java heap trên thiết bị bộ nhớ phải xuất phát từ tính tương thích và số liệu SLO, không chỉ từ khả năng cấu hình flag JVM.** JEP 316 từ Java 10 và `-XX:AllocateHeapAt=<path>` vẫn được mô tả trên Oracle JDK 25, nhưng cần **thiết bị memory-like đáp ứng semantics của DRAM**, OS/driver/DAX mapping phù hợp và xác minh heap placement thực tế.

Trước khi áp dụng:
1. **Đo memory-access latency và bandwidth theo nhiều kiểu truy cập**, tránh cache/JIT che mất device.
2. **Đo tail latency, successful throughput và GC của ứng dụng thật** với cùng baseline DRAM.
3. **Kiểm thử chạy dài, restart/failure recovery, bảo mật và rollback**, không xem số lỗi bằng 0 ở một run là bảo đảm tuyệt đối.
4. **Đặt ngưỡng GO/HOLD/NO-GO trước khi chạy benchmark** và cân nhắc capacity/cost cùng chất lượng dịch vụ.
5. **Không nhầm persistent device với persistent Java objects** và không dựa vào sản phẩm phần cứng đã EOL làm khuyến nghị mặc định.

Một candidate có thể có băng thông thấp hơn DRAM nhưng vẫn phù hợp một workload cần capacity lớn, **nếu** mọi SLO/reliability gate thực sự đạt. Một candidate có capacity vượt trội nhưng p99/GC/availability không đạt thì không nên triển khai. Đây là nguyên tắc vẫn đúng trên JDK hiện đại dù loại thiết bị và các cơ chế phân tầng bộ nhớ tiếp tục phát triển.

## 18. Tài liệu tham khảo chính thức

- [OpenJDK JEP 316 — Heap Allocation on Alternative Memory Devices](https://openjdk.org/jeps/316): động cơ và giới hạn cơ chế HotSpot từ Java 10.
- [Oracle Java SE 25 — The java Command, `-XX:AllocateHeapAt`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): tùy chọn heap allocation tới memory device, load/store semantics và những vùng vẫn ở DRAM.
- [Linux Kernel — Direct Access for files (DAX)](https://docs.kernel.org/filesystems/dax.html): bypass page cache, DAX filesystem/inode flag và yêu cầu driver/hardware.
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): cách thiết lập và chạy microbenchmark Java có forks/warmup/measurement.
- [Oracle Java SE 25 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): latency, GC, CPU, contention và lưu ý chi phí event recording.
- [Oracle Java SE 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): JFR, jcmd và một số kỹ thuật chẩn đoán hiệu năng.
- [Oracle Java SE 25 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/): cách đọc pause/throughput và cấu hình GC trên JDK hiện đại.
- [Linux Kernel — Cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): giới hạn CPU/memory và các counters có thể ảnh hưởng benchmark.
- [Intel Support — Customer Support Options for Discontinued Optane Products](https://www.intel.com/content/www/us/en/support/articles/000024320/technologies/memory-and-storage.html): trạng thái EOL/EOIS của nhiều dòng Optane, tránh khuyến nghị procurement đã lỗi thời.
- [Intel Support — Optane Business Update](https://www.intel.com/content/www/us/en/support/articles/000091826/memory-and-storage.html): kế hoạch ngừng phát triển Optane và chính sách hỗ trợ sản phẩm đang tồn tại.