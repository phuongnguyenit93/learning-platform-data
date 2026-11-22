# Giới hạn tối ưu G1 và NUMA khi phần cứng hoặc kiểu tải không phù hợp

> **Module Java 14 — G1 và NUMA.** JEP 345 (*NUMA-Aware Memory Allocation for G1*) bổ sung khả năng cân nhắc vị trí NUMA khi G1 cấp phát bộ nhớ ở Java 14. Cơ chế này tiếp tục liên quan trong HotSpot/JDK hiện đại, nhưng **không phải công tắc “bật là nhanh hơn”**. Nếu máy chỉ có một NUMA node hữu dụng, heap nhỏ, thread di chuyển liên tục, bộ nhớ chia sẻ chéo node hoặc nghẽn nằm ở CPU/I/O, lợi ích có thể bằng không, thậm chí hiệu năng có thể kém hơn. Bài chỉ dùng kiến thức hiện còn áp dụng, với lệnh JVM được mô tả trong JDK 25 và mã Java 17+; không dùng cờ GC logging đã lỗi thời.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích NUMA, local/remote memory, node distance, heap region và mối liên hệ với **G1 Garbage Collector**.
2. Hiểu JEP 345 nhằm cải thiện cấp phát **Eden** và **Survivor** theo NUMA locality, không đảm bảo toàn bộ object graph luôn local.
3. Phân biệt **điều kiện phần cứng không thuận lợi** và **kiểu tải ứng dụng không nhạy NUMA**.
4. Nêu vì sao CPU-bound, I/O-bound, heap nhỏ, off-heap memory, sharing mạnh hoặc thread migration dễ làm NUMA tuning kém hiệu quả.
5. Kiểm tra CPU/memory nodes mà **tiến trình Java thật sự được phép sử dụng**, không chỉ topology vật lý host.
6. Dùng những option JVM hiện hành: `-XX:+UseG1GC`, `-XX:+UseNUMA`, `-XX:-UseNUMA`, `-XX:+PrintFlagsFinal` và unified logging `-Xlog`.
7. Đo A/B bằng cùng JDK, same workload, same heap, cùng CPU affinity và cùng logging; đọc throughput, p95/p99 latency, GC pause, memory placement và độ phân tán.
8. Viết ví dụ Java 17 chạy độc lập, biết đâu là stdout xác định và đâu là số đo không cố định.
9. Quyết định khi nào nên **giữ mặc định**, lúc nào mới ưu tiên tối ưu NUMA và cách rollback khi không có lợi.

## 2. NUMA giải quyết vấn đề gì?

**NUMA (Non-Uniform Memory Access)** có nghĩa chi phí truy cập RAM thay đổi theo quan hệ giữa CPU và node chứa trang nhớ. Trên một số server nhiều socket/NUMA nodes:

- Thread chạy trên CPU của node 0 thường truy cập RAM local của node 0 với latency thấp hơn.
- Nếu thread đọc/ghi trang nhớ thuộc node 1, truy cập có thể qua interconnect, sử dụng băng thông liên node và tốn thêm thời gian.
- Thực tế phụ thuộc CPU, DRAM, cache, topology, scheduler và chính sách OS. Không có một tỉ lệ chậm cố định cho mọi máy.

Sơ đồ khái niệm:

~~~text
NUMA node 0                    NUMA node 1
+------------------+           +------------------+
| CPU cores        |           | CPU cores        |
| Local memory 0   |           | Local memory 1   |
+--------+---------+           +---------+--------+
         |                               |
         +--------- interconnect --------+
                      |
              Remote access cost
~~~

**Đây chỉ là sơ đồ**, không phải cấu trúc bắt buộc của mọi máy có nhiều CPU. Trên một máy chỉ có một NUMA node hữu dụng, không có mục tiêu “giảm remote access sang node khác” trong phạm vi process.

### Các thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| NUMA node | Nhóm tài nguyên CPU và memory có quan hệ truy cập gần nhau. |
| Local memory | Trang nhớ ở node gần CPU đang thực thi thread. |
| Remote memory | Trang nhớ ở node khác, có thể tốn latency/bandwidth hơn. |
| CPU affinity | Danh sách CPU mà thread/process được phép chạy. |
| Memory policy | Những memory nodes được phép hoặc ưu tiên cấp phát page. |
| Node distance | Chỉ báo chi phí tương đối giữa các node do OS cung cấp. |
| UMA | Mô hình truy cập bộ nhớ tương đối đồng đều; giảm khả năng hưởng lợi từ NUMA placement. |
| Java heap | Vùng object memory do GC quản lý; **không phải toàn bộ RSS** của process. |
| G1 region | Đơn vị heap G1 quản lý, có thể được dùng làm Eden, Survivor hay Old. |
| Working set | Phần dữ liệu thực sự được truy cập thường xuyên khi ứng dụng chạy. |

**Nhiều CPU cores không đồng nghĩa nhiều NUMA nodes**. Một VM hoặc container có thể nhìn thấy số CPU lớn nhưng memory policy chỉ cho phép một node. Quyết định cần dựa trên topology tiến trình nhìn thấy, không suy đoán từ nhãn CPU.

## 3. G1 NUMA-aware thực sự thay đổi gì?

G1 chia heap thành các **regions**; object mới thường được cấp phát ở **Eden**, object sống qua young collection được copy sang Survivor hoặc promote vào Old generation. G1 kết hợp hoạt động parallel/concurrent với các pause có mục tiêu, nhưng không phải real-time collector và không bảo đảm mọi pause đều dưới một ngưỡng.

**JEP 345**, xuất hiện ở Java 14, tập trung vào **locality của cấp phát G1**:

- Mutator thread cấp phát object mới có thể được ưu tiên sử dụng Eden region gắn với NUMA node gần thread đó.
- Trong young evacuation, GC workers có thể cấp phát Survivor regions cân nhắc NUMA node để giảm chi phí memory remote.
- G1/OS vẫn phải đáp ứng memory availability, heap balancing, garbage collection, region selection và các mục tiêu khác.
- Khi cần, allocator có thể lấy region không ở node ưu tiên; tính gần CPU là **ưu tiên**, không phải một ràng buộc tuyệt đối.

Ví dụ luồng dữ liệu:

~~~text
Worker trên CPU node 0
       |
       v
Tạo object -> Eden ưu tiên locality node 0
       |
       v
Young GC -> Survivor/Old regions
       |
       v
Thread khác trên node 1 dùng cùng object
       |
       v
Vẫn có thể phát sinh remote memory access
~~~

**Đừng suy diễn quá mức:** cải tiến gốc chủ yếu hướng tới đường cấp phát **young generation**. Nó không tuyên bố toàn bộ Old generation, every cache line, native allocations hoặc đồ thị object được tự động đặt đúng nơi tất cả thread truy cập. Theo mô tả của người triển khai JEP 345, G1 Old region allocation trong phiên bản đầu không được điều khiển bởi NUMA node như Eden/Survivor. Các JDK có thể cải tiến implementation về sau, nhưng **không có bảo đảm mọi object trở nên local**.

## 4. Phần cứng không phù hợp: dấu hiệu cần kiểm tra trước

### 4.1. Chỉ một NUMA node usable

Một máy nhỏ, laptop, cloud VM hoặc container bị ràng buộc một node không có cross-node memory path đáng kể để cải thiện. Trên hệ thống này:

- `-XX:+UseNUMA` có thể không tạo hiệu quả hoặc bị giới hạn bởi nền tảng.
- Chênh lệch một vài phần trăm khi chạy một lượt rất có thể là benchmark noise.
- Cần ưu tiên GC, thuật toán, allocation reduction hoặc I/O nếu chúng là bottleneck.

Không cần cố cấu hình NUMA để đạt một “tối ưu” không có cơ sở phần cứng.

### 4.2. Server nhiều node nhưng JVM bị giới hạn vào một node

Ví dụ server 4 nodes, song container chỉ được cấp CPUs thuộc node 2 và memory policy `cpuset.mems.effective=2`. Host có bốn nodes **không đồng nghĩa Java process có thể phân phối bộ nhớ sang cả bốn**.

**Quy tắc:** kiểm tra cả *host topology* lẫn CPU/memory nodes **được phép** của process. Container/cgroup, hypervisor, `numactl` và scheduler có thể giới hạn mạnh phạm vi thực tế.

### 4.3. Heap và working set nhỏ hơn nhiều so với memory của một node

Giả sử mỗi node có 64 GiB RAM trong khi heap Java chỉ 1 GiB, dữ liệu nóng ít, allocations thấp. Nhiều dữ liệu có thể nằm gọn ở một node/cache; số remote memory accesses không lớn để việc bố trí page khác đi tạo cải thiện đáng kể.

**Không biến ví dụ này thành ngưỡng cứng.** Heap 1 GiB đôi khi vẫn có workload rất memory-sensitive; heap 64 GiB vẫn có thể không hưởng lợi nếu bố trí dữ liệu/CPU không phù hợp. Phải đo.

### 4.4. Remote/local memory gap nhỏ

Một nền tảng có interconnect nhanh, ứng dụng cache-hit cao hoặc dữ liệu gần như được truy cập tuần tự có thể thấy remote penalty không đáng kể so với các thành phần khác.

`numactl --hardware` cho thấy **node distances tương đối**, không phải phép đo trực tiếp latency ứng dụng bằng nanosecond. Nếu khoảng cách hiệu năng nhỏ hơn độ nhiễu chạy thử, không có căn cứ để tuyên bố NUMA tuning hiệu quả.

### 4.5. Memory node có áp lực lớn hoặc không cân bằng

Nếu node gần thread đã gần cạn RAM, việc ưu tiên local có thể dẫn đến fallback, reclaim, swap hoặc bố trí không đều:

- Một node thiếu headroom nhưng các node khác còn nhiều RAM.
- Dữ liệu chuyển qua interconnect vẫn xảy ra.
- Page migration hoặc reclaim gây thêm chi phí.
- Một tiến trình khác tranh memory bandwidth cùng node.
- p99 latency xấu đi dù GC pause không tăng.

**NUMA flag không thay thế capacity planning**. Hãy xem free memory từng node, RSS, heap, native memory và tải trên host.

### 4.6. JVM/OS không hỗ trợ cùng một đường mã

Cải tiến G1 NUMA-aware ban đầu được triển khai cho Linux; đừng giả định mọi OS/JDK vendor/collector có hành vi giống nhau. Oracle JDK 25 vẫn mô tả `-XX:+UseNUMA` nhưng nêu **giá trị mặc định phụ thuộc garbage collector**. Cần kiểm tra flags/log trên đúng runtime đang triển khai.

**Đừng sao chép tài liệu JVM rất cũ** để khẳng định cờ chỉ dùng cho Parallel GC hoặc mặc định luôn off. Ngược lại, cũng đừng khẳng định “G1 mặc định thì NUMA luôn on”. Kiểm chứng bằng runtime thật.

## 5. Kiểu tải không phù hợp: NUMA không phải bottleneck

### 5.1. Tính toán CPU-bound

Vòng lặp số học, nén hoặc xử lý dữ liệu nhỏ nằm chủ yếu trong CPU cache có thể bị giới hạn bởi số instruction/CPU, không phải DRAM locality. Bật `UseNUMA` sẽ không tự giảm số phép tính.

**Nên đo:** CPU profiler, cycles/instructions, lock contention và cache-miss rate. Nếu bottleneck là compute, tối ưu thuật toán, concurrency và dữ liệu trước.

### 5.2. I/O-bound hoặc độ trễ phía ngoài JVM

Một API gọi database, HTTP service hoặc disk nhiều và chờ I/O thường có request latency bị quyết định bởi downstream. Nếu GC chiếm rất ít CPU/tổng thời gian, giảm remote heap memory access cũng có thể không làm p99 request giảm thấy rõ.

**Nên đo:** tracing thời gian DB/network, connection pools, queueing, timeouts, retry và backpressure.

### 5.3. Ít allocation hoặc phần lớn dữ liệu đã sống lâu

G1 NUMA-aware young allocation có thể ít tác dụng với ứng dụng có ít object mới, chủ yếu đọc các object lâu đời hoặc dữ liệu immutable lớn. Những object này có thể nằm trong Old generation, native memory hoặc memory-mapped files.

**Nên đo:** allocation rate, GC pauses, heap occupancy theo generation, local/remote access. Đừng mặc định mọi old object đều được định vị tối ưu chỉ nhờ cờ JVM.

### 5.4. Cùng một object được chia sẻ bởi threads ở nhiều nodes

Nếu threads node 0 và node 1 thường xuyên sửa **cùng counter/hash map/queue**, cấp phát object gần một node không thể khiến nó trở thành local cho tất cả CPU. Cache-line ownership và cache coherence cũng gây overhead.

**Nên cân nhắc:** sharding theo node, per-thread/per-shard aggregators, giảm shared mutable writes, kiểm tra data ownership. Mặc dù vậy pin hoặc shard có thể làm mất cân bằng workload; không phải giải pháp áp dụng mù quáng.

### 5.5. Thread migration liên tục

Thread lúc cấp phát chạy node 0, nhưng sau đó OS scheduler chuyển sang node 1. Page đã cấp phát theo locality cũ có thể thành remote ở lần đọc sau. Một thread pool có worker di chuyển liên tục giữa nodes có thể làm locality kém ổn định.

**Không tự động khóa toàn bộ thread vào một node**: pinning cứng có thể giảm khả năng scheduler cân bằng tải. Chỉ dùng CPU affinity khi có số đo và kiến trúc worker/data phù hợp.

### 5.6. Bottleneck nằm ở off-heap/native memory

`-XX:+UseNUMA` của G1 **không quản lý tất cả memory traffic** của process:

- `ByteBuffer.allocateDirect` và buffers của native libraries.
- JNI, malloc, memory-mapped files hoặc cache của hệ điều hành.
- Thread stacks, code cache, metadata và driver/GPU memory.
- OS page cache phục vụ I/O.

Nếu phần lớn memory bandwidth nằm ngoài Java heap, thay G1 region allocation có thể không tác động đủ nhiều. Đừng chỉ nhìn `-Xmx` rồi cho rằng đó là toàn bộ memory footprint; đo RSS và nguồn cấp phát phù hợp.

### 5.7. Tải quá ngắn hoặc thay đổi liên tục

Một benchmark chỉ chạy dưới một giây có thể bị ảnh hưởng startup, class loading, JIT compilation, CPU frequency, background jobs và page fault nhiều hơn chênh lệch NUMA. Workload sản xuất có burst ngắn cũng có thể không đạt trạng thái ổn định để hưởng lợi.

**Nên đo:** thời gian warm-up và steady-state riêng, nhiều lần lặp, phân phối kết quả và mức chênh lệch lớn hơn noise.

## 6. Khi nào **có thể** đáng thử NUMA?

Một môi trường có nhiều NUMA nodes thực sự usable, heap/working set lớn, nhiều allocation, các threads xử lý dữ liệu có locality tự nhiên và remote memory traffic chiếm tỷ trọng đáng kể **có khả năng** hưởng lợi.

Dấu hiệu thuận lợi:

- Các node có khác biệt local/remote latency hoặc bandwidth đáng kể.
- Dịch vụ có tải đủ lớn để bộ nhớ và GC là yếu tố hiệu năng.
- Thread-to-data affinity tương đối ổn định.
- Không có memory pressure nghiêm trọng gây fallback giữa nodes.
- Có công cụ đo CPU/memory/GC và có thể chạy A/B an toàn.

**Có khả năng không phải chắc chắn.** Các thuật toán phân bổ G1, OS memory policy, huge pages và GC pause/throughput trade-off vẫn tác động kết quả.

### Ma trận quyết định

| Tình huống | Ưu tiên NUMA | Hành động |
| --- | --- | --- |
| 1 node usable | Rất thấp | Không tuning theo NUMA; kiểm tra bottleneck khác. |
| Host nhiều node nhưng container chỉ dùng 1 | Thấp | Xác minh cpuset trước. |
| 2–4 nodes, heap lớn, nhiều allocation | Đáng thử | So A/B cùng JDK/heap/workload. |
| Data sharing chéo nodes mạnh | Không chỉ bằng GC | Giảm contention/partition data trước. |
| CPU-bound, cache-hit cao | Thấp | Dùng CPU profiler. |
| DB/network chiếm latency | Thấp | Tối ưu I/O và tracing. |
| Off-heap dominate | Tùy memory allocator khác | Đo native memory/counters. |
| Một node gần hết RAM | Có rủi ro | Capacity planning, memory policy. |
| Chênh 1% trong noise 5% | Chưa chứng minh | Chạy nhiều lượt, thống kê. |
| Throughput tốt nhưng p99/SLO xấu | Có thể không phù hợp | Quyết định theo SLO. |

## 7. Xem topology trên Linux, không đoán từ CPU core

Những lệnh sau dành cho Linux có `lscpu` và `numactl`, không phải cú pháp Java:

~~~bash
lscpu
lscpu -e=CPU,NODE
numactl --hardware
~~~

`numactl --hardware` thường hiển thị nodes, CPUs, dung lượng RAM từng node và **node distances**. Stdout là thông tin tùy máy, không có giá trị cố định để so.

### Cgroup v2 và container

Xem các node đang online và tài nguyên effective nếu hệ thống có cpuset controller trong cgroup v2:

~~~bash
cat /sys/devices/system/node/online
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpuset.mems.effective
~~~

- `cpuset.cpus.effective`: logical CPUs thực sự được phép dùng.
- `cpuset.mems.effective`: memory nodes được phép cấp phát.
- Những đường dẫn này **có thể không tồn tại** ở cgroup v1 hoặc cấu hình khác. Khi đó phải xác định mount/cgroup process thực tế, không kết luận không có NUMA.
- Một giá trị như `cpuset.mems.effective=1` có thể nghĩa là container chỉ được dùng node 1 dù host có nhiều nodes.

Để xem memory distribution của process đã chạy trên Linux:

~~~bash
numastat -p 12345
~~~

`12345` là **PID minh họa**, thay bằng PID Java thật. Công cụ cần quyền phù hợp. Kết quả chỉ mô tả phân bố page theo node, **không trực tiếp đo local/remote access của ứng dụng**; để đánh giá memory bandwidth/latency cần profiler hoặc hardware counters phù hợp CPU/kernel.

### CPU/memory binding là một biến của benchmark

Ví dụ dùng node 0 khi tồn tại và policy cho phép:

~~~bash
numactl --cpunodebind=0 --membind=0 java -version
~~~

Đây chỉ là cách minh họa affinity/policy. Nếu A/B có một run bind vào node 0 còn run kia được toàn bộ nodes, so sánh không cô lập tác động của `UseNUMA`. Giữ **cùng affinity và memory policy** giữa hai cấu hình.

## 8. Xem JVM thực sự cấu hình GC và NUMA ra sao

### 8.1. Xác định phiên bản và logging tags

~~~bash
java -version
java -Xlog:help
~~~

Dùng JDK có hỗ trợ Java 17+ và G1; thống nhất vendor/build giữa các phép thử. `java -Xlog:help` cho biết tags của **Unified JVM Logging** trên runtime cụ thể, tránh sao chép flag lỗi thời từ tài liệu Java cũ.

### 8.2. Xem flag hiện hành thay vì suy đoán

Trên Linux/Unix có `grep`:

~~~bash
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'UseG1GC|UseNUMA'
~~~

Thử bật rõ:

~~~bash
java -XX:+UseG1GC -XX:+UseNUMA -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'UseG1GC|UseNUMA'
~~~

Thử tắt rõ:

~~~bash
java -XX:+UseG1GC -XX:-UseNUMA -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'UseG1GC|UseNUMA'
~~~

Trên PowerShell thay `grep` bằng `Select-String`. Đọc cả warning và exit code; một option được ghi true **chưa chứng minh** JVM có nhiều memory nodes usable hoặc heap pages được đặt local như mong muốn.

**Lưu ý phiên bản:** Oracle JDK 25 vẫn nêu `-XX:+UseNUMA` nhưng mặc định **tùy collector**. Không tuyên bố mặc định cụ thể nếu chưa kiểm tra runtime.

### 8.3. Unified Logging cho G1/NUMA

Ví dụ trên HotSpot có tag tương ứng, sau khi đã biên dịch class `NumaAllocationDemo` ở phần 10:

~~~bash
java -XX:+UseG1GC -XX:+UseNUMA -Xms512m -Xmx512m -Xlog:gc*,numa*=debug:file=gc-numa.log:uptime,level,tags NumaAllocationDemo
~~~

Một lựa chọn log chuyên sâu về heap NUMA trên các runtime có tổ hợp tag này:

~~~bash
java -XX:+UseG1GC -XX:+UseNUMA -Xms512m -Xmx512m -Xlog:gc+heap+numa=debug:file=gc-numa-regions.log:uptime,level,tags NumaAllocationDemo
~~~

Đây là **cú pháp phục vụ chẩn đoán**, cần kiểm tra `java -Xlog:help` trên chính runtime. Nếu tag không được JVM hỗ trợ, cần sửa cấu hình log phù hợp vendor/version. **Không suy ra rằng log im lặng là tối ưu đã thành công.**

Để benchmark hiệu năng, tránh bật debug log dày ở một run nhưng không bật ở run còn lại; logging có overhead riêng.

## 9. Các biến gây nhiễu nên quản lý

| Biến | Tác động có thể gây hiểu sai |
| --- | --- |
| JDK build khác nhau | GC/JIT/runtime cải tiến qua phiên bản, không thể quy hết cho NUMA. |
| `-Xms`/`-Xmx` khác nhau | Thay memory pressure và GC frequency. |
| CPU quota/cpuset khác nhau | Thay số workers và quyền dùng CPU. |
| Memory policy khác nhau | Một run được phép dùng nhiều nodes, run khác bị buộc một node. |
| `-XX:+AlwaysPreTouch` | Có thể thay thời điểm commit/touch pages và startup. |
| Large pages/THP policy khác nhau | Tác động TLB, page placement, fragmentation. |
| GC logging mức debug chỉ ở một run | Log overhead làm sai chênh lệch throughput. |
| Workload input/concurrency khác nhau | Không còn là A/B cùng điều kiện. |
| Node memory pressure từ process khác | Gây fallback/remote allocation, noise. |
| CPU frequency/thermal/JIT warm-up | Đặc biệt lớn với benchmark ngắn. |

**Đừng thay nhiều knobs một lúc.** Mục đích so `UseNUMA` yêu cầu nhóm A và B chỉ khác **NUMA flag**, những điều kiện còn lại giữ tương đương.

## 10. Ví dụ Java 17 độc lập: tải allocation có checksum kiểm soát

Tạo tệp **`NumaAllocationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class NumaAllocationDemo {
    private static volatile Object retained;

    public static void main(String[] args) throws Exception {
        int workers = args.length > 0 ? Integer.parseInt(args[0]) : 4;
        int iterations = args.length > 1
                ? Integer.parseInt(args[1]) : 20_000;
        if (workers < 1 || workers > 16 || iterations < 256) {
            throw new IllegalArgumentException(
                    "workers must be 1..16 and iterations >= 256");
        }

        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Long>> results = new ArrayList<>();

        long begin = System.nanoTime();
        try {
            for (int worker = 1; worker <= workers; worker++) {
                final int id = worker;
                results.add(pool.submit(() -> {
                    start.await();
                    byte[][] window = new byte[256][];
                    long local = 0;

                    for (int i = 0; i < iterations; i++) {
                        byte[] block = new byte[4_096];
                        block[0] = (byte) id;
                        window[i & 255] = block;
                        local += block[0] & 255;
                    }

                    for (byte[] block : window) {
                        local += block[0] & 255;
                    }
                    retained = window;
                    return local;
                }));
            }

            start.countDown();
            long checksum = 0;
            for (Future<Long> result : results) {
                checksum += result.get();
            }

            long elapsedMs = (System.nanoTime() - begin)
                    / 1_000_000;
            System.out.println("workers=" + workers);
            System.out.println("iterations=" + iterations);
            System.out.println("checksum=" + checksum);
            System.out.println("elapsedMs=" + elapsedMs);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 NumaAllocationDemo.java
java -XX:+UseG1GC -Xms512m -Xmx512m NumaAllocationDemo
~~~

**Ba dòng stdout xác định với tham số mặc định:**

~~~text
workers=4
iterations=20000
checksum=202560
~~~

Sau đó có `elapsedMs=<số đo>`; số này **khác nhau theo máy và lần chạy**, không dùng một giá trị cố định.

Giải thích checksum: bốn workers mang id 1,2,3,4; mỗi worker cộng `20_000` lần giá trị id và cộng thêm 256 phần tử cuối trong window. Tổng id là 10 nên checksum = `(20_000 + 256) * 10 = 202560`.

**Lưu ý:** đây là ví dụ tạo nhiều byte arrays để quan sát GC/flags, **không phải benchmark NUMA đại diện cho sản phẩm**. Thay `iterations`, thread count và cấu hình heap có thể thay tải rõ rệt. JIT, escape analysis, scheduler, cache và memory node usable đều ảnh hưởng kết quả.

## 11. Ví dụ Java 17 độc lập: CPU-bound không phải bài test NUMA tốt

Tạo tệp **`CpuBoundNoAllocationDemo.java`**:

~~~java
public class CpuBoundNoAllocationDemo {
    private static volatile long result;

    public static void main(String[] args) {
        long sum = 0;
        for (long i = 1; i <= 1_000_000L; i++) {
            sum = (sum + i) % 1_000_000_007L;
        }
        result = sum;
        System.out.println("sumMod=" + result);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CpuBoundNoAllocationDemo.java
java -XX:+UseG1GC CpuBoundNoAllocationDemo
~~~

**Stdout chính xác:**

~~~text
sumMod=496500
~~~

Ví dụ này không tạo allocation pressure đáng kể trong vòng lặp, và diễn ra rất nhanh. Do đó nó **không đủ để kiểm chứng locality memory**. Không kết luận rằng NUMA luôn không giúp tác vụ CPU-bound nào; chỉ kết luận phép thử này không đo đúng cơ chế ta đang quan tâm.

## 12. Ví dụ Java 17: tài nguyên JVM không phải số NUMA nodes

Tạo tệp **`RuntimeResourcesDemo.java`**:

~~~java
public class RuntimeResourcesDemo {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        long mib = 1024L * 1024L;

        System.out.println("os=" + System.getProperty("os.name"));
        System.out.println("cpus=" + runtime.availableProcessors());
        System.out.println("maxHeapMiB=" + runtime.maxMemory() / mib);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RuntimeResourcesDemo.java
java RuntimeResourcesDemo
~~~

Đầu ra **phụ thuộc môi trường**:

~~~text
os=<tên hệ điều hành thực tế>
cpus=<logical processors JVM thấy>
maxHeapMiB=<giới hạn heap JVM nhìn thấy>
~~~

Đây là **mô tả định dạng đầu ra**, không phải stdout nguyên văn. `availableProcessors()` và `maxMemory()` không cho bạn số NUMA nodes hoặc remote DRAM latency. Muốn biết topology cần công cụ OS và memory policy đã nêu.

## 13. Benchmark A/B đúng cách

Sau khi compile `NumaAllocationDemo`, trên Linux/HotSpot có G1 và đủ memory, ví dụ hai lệnh chỉ khác NUMA flag:

**A — không bật NUMA-aware:**

~~~bash
java -XX:+UseG1GC -XX:-UseNUMA -Xms512m -Xmx512m -Xlog:gc*:file=gc-off.log:uptime,level,tags NumaAllocationDemo 4 20000
~~~

**B — bật NUMA-aware:**

~~~bash
java -XX:+UseG1GC -XX:+UseNUMA -Xms512m -Xmx512m -Xlog:gc*:file=gc-on.log:uptime,level,tags NumaAllocationDemo 4 20000
~~~

Hai lệnh có cùng `-Xms`/`-Xmx`, collector, logger level, class và input. Chạy **nhiều lần** theo thứ tự đảo A/B; không kết luận từ một lần chạy. Trên server nhiều NUMA nodes, demo nhỏ có thể chưa đủ mạnh/đại diện; nên dùng **workload production-like** với request rate và allocation profile thật.

### Những điều phải giữ nguyên

1. Cùng JDK vendor/build và JVM version.
2. Cùng GC collector và mọi GC option khác.
3. Cùng heap size, memory node policy và CPU affinity.
4. Cùng cgroup CPU/memory quota.
5. Cùng inputs, số workers, thời lượng, warm-up và background load.
6. Cùng kernel/THP/huge pages, nếu có thể.
7. Cùng mức logging và công cụ đo.
8. Cùng cách tính throughput/latency.

Nếu cần logging NUMA debug để kiểm tra feature, chạy **lượt chẩn đoán riêng**. Bật debug logs ở B nhưng không bật ở A khiến so sánh throughput có thêm biến nhiễu.

### Metric nên thu thập

| Metric | Tại sao quan trọng |
| --- | --- |
| Throughput (req/s, ops/s) | Đo hiệu năng nghiệp vụ, không chỉ GC. |
| p50/p95/p99 latency | Phát hiện tail latency xấu đi dù trung bình tốt hơn. |
| GC pause count/duration | Biết NUMA có ảnh hưởng hành vi GC không. |
| CPU utilization / GC CPU | Xem thêm overhead của GC/concurrency. |
| Java heap & RSS | Phát hiện memory footprint và áp lực native. |
| Per-node memory usage | Phát hiện mất cân bằng node. |
| Local/remote memory access | Kiểm chứng có thay đổi locality thật không khi phần cứng hỗ trợ counters. |
| Page faults / reclaim / swap | Phát hiện memory pressure gây slowdown. |
| Độ phân tán qua nhiều runs | Phân biệt cải thiện thật với benchmark noise. |

**Bài demo không đủ để khẳng định cải thiện phần trăm.** Muốn quyết định production, dùng workload đại diện, có warm-up, chạy nhiều lượt, đối chiếu SLO và báo cả variance.

## 14. Diễn giải kết quả: quan sát nào đủ và chưa đủ?

| Quan sát | Điều có thể nói | Điều không thể tự kết luận |
| --- | --- | --- |
| `UseNUMA=true` | Flag trong VM có giá trị true | Mọi page đều local hoặc throughput sẽ tăng. |
| Một memory node usable | Không có nhiều node được cấp quyền | Host không có nhiều socket vật lý. |
| `numastat -p` thấy heap trải nhiều nodes | Process dùng RAM nhiều nodes | Remote access thấp hoặc cao. |
| G1 NUMA logs có thông tin | VM có hoạt động liên quan NUMA | Lợi ích ứng dụng đã có. |
| GC pause giảm | GC metric có thể cải thiện | Request p99 chắc chắn cải thiện. |
| Throughput hơn 1%, noise 5% | Cần thêm dữ liệu | NUMA mang lại cải thiện đáng tin. |
| Throughput tăng, p99 tăng | Có trade-off | Thay đổi luôn tốt cho SLO. |
| CPU-bound demo không đổi | Demo đó không nhạy memory locality | Không ứng dụng Java nào hưởng lợi. |
| NUMA on mà remote accesses vẫn cao | Locality chưa hoàn hảo | VM chắc chắn có bug. |

Hãy báo số đo cùng **version JDK, topology, allowed nodes, affinity, heap, load và số lượt chạy**. Benchmark lịch sử từ một máy có heap rất lớn chỉ minh họa khả năng có lợi, **không phải dự báo chắc chắn cho ứng dụng khác**.

## 15. Huge pages và tuning GC không nên trộn với NUMA

`-XX:+UseLargePages` và `-XX:+UseTransparentHugePages` là lựa chọn khác, có thể tác động TLB, fragmentation và placement. Oracle lưu ý large pages đôi khi làm thiếu regular pages hoặc làm OS khó cấp phát khi fragment. Không thay đồng thời `UseNUMA` và THP/large-page settings khi đang cô lập tác động NUMA.

Với G1, tài liệu Oracle khuyến nghị **bắt đầu từ defaults**, đặt `-Xmx` và pause-time goal khi có lý do. Không cố định young generation với `-Xmn` một cách tùy tiện: G1 dùng sự linh hoạt về young size để đáp ứng mục tiêu pause. `-XX:MaxGCPauseMillis` là mục tiêu **mềm**, không phải hard SLA cho mọi pause.

Các yếu tố thường có tác động lớn hơn NUMA trong nhiều ứng dụng: heap quá nhỏ, Full GC, humongous allocations, allocation rate cao, shared locks, DB queries, network tail latency và contention.

## 16. Quy trình troubleshooting

Khi “bật NUMA nhưng app không nhanh hơn”:

1. **Kiểm tra JDK và flags:** cùng HotSpot build? `UseG1GC` và `UseNUMA` có giá trị thực thế nào?
2. **Kiểm tra topology usable:** có ít nhất hai nodes? cpuset/cgroup có giới hạn process không?
3. **Kiểm tra memory policy và node headroom:** có memory pressure/fallback/reclaim không?
4. **Xác định bottleneck:** DRAM remote hay CPU/I/O/lock?
5. **Kiểm tra allocation profile:** young allocations có đủ lớn để locality G1 hữu ích?
6. **Kiểm tra worker/data mapping:** threads có bị migrate mạnh hoặc chia sẻ object graph rộng không?
7. **Kiểm tra các knobs khác:** heap, huge pages, THP, affinity, logging có đổi giữa A/B không?
8. **Warm-up và lặp lại:** có lặp đủ số lần, loại bỏ runs không đại diện?
9. **Kiểm tra cả p99 và throughput:** có đổi lợi ích trung bình lấy tail latency xấu hơn không?
10. **Quyết định/rollback:** nếu không có cải thiện ổn định và phù hợp SLO, giữ cấu hình đơn giản hoặc tắt có kiểm soát.

Tối ưu có trách nhiệm là **tìm bottleneck và chứng minh thay đổi giải quyết nó**, không phải ép JVM bật một option vì nghe có vẻ “hiệu năng cao”.

## 17. Bài tập và đáp án

### Bài 1 — Single-node

Một container chỉ được `cpuset.mems.effective=0`. Bật `UseNUMA` có chắc nhanh hơn không?

**Đáp án:** không. Không có nhiều memory nodes usable để tối ưu cross-node; cần kiểm tra giới hạn container và bottleneck thực.

### Bài 2 — Workload I/O-bound

Một API mất 200 ms vì DB, GC chiếm rất ít thời gian. Tăng NUMA locality có thể chắc chắn giảm p99 còn 100 ms?

**Đáp án:** không. Tối ưu truy vấn, network, queueing hoặc caching trước.

### Bài 3 — Dữ liệu chia sẻ chéo nodes

Threads node 0 và 1 cập nhật một shared map liên tục. G1 có tự chuyển object đến gần cả hai không?

**Đáp án:** không. Tìm phương án sharding/partition hoặc giảm shared mutable contention nếu khả thi.

### Bài 4 — A/B sai

A: `-XX:-UseNUMA -Xmx512m`, 4 workers. B: `-XX:+UseNUMA -Xmx8g`, 32 workers. Có kết luận về NUMA không?

**Đáp án:** không; thay quá nhiều biến. So cùng heap, JDK, thread count, affinity, input và measurement.

### Bài 5 — Kiểm thử mã Java 17

~~~bash
javac --release 17 NumaAllocationDemo.java
java -XX:+UseG1GC -Xms512m -Xmx512m NumaAllocationDemo

javac --release 17 CpuBoundNoAllocationDemo.java
java CpuBoundNoAllocationDemo

javac --release 17 RuntimeResourcesDemo.java
java RuntimeResourcesDemo
~~~

- `NumaAllocationDemo`: kiểm tra checksum `202560`, nhưng **không hardcode `elapsedMs`**.
- `CpuBoundNoAllocationDemo`: `sumMod=496500`.
- `RuntimeResourcesDemo`: ba giá trị phụ thuộc OS/JVM, không suy ra NUMA từ chúng.

### Bài 6 — Giới hạn mục tiêu

NUMA on tăng throughput trung bình 2% nhưng p99 vi phạm SLO. Nên chọn thế nào?

**Đáp án:** nếu p99 SLO bắt buộc, không chọn cấu hình chỉ vì throughput. Quyết định theo kết quả toàn bộ và độ ổn định.

### Bài 7 — Heap nhỏ

Trên máy hai nodes mỗi node 64 GiB, ứng dụng có heap 1 GiB, ít allocations. Vì sao NUMA on/off gần giống nhau?

**Đáp án:** có thể working set vừa một node/cache, remote traffic thấp, overhead/measurement noise lấn át. Đừng coi 1 GiB là ngưỡng phổ quát.

## 18. Checklist triển khai

- [ ] Đã xác định JDK version/vendor và G1/NUMA flag thực tế?
- [ ] Có hơn một NUMA node **usable cho process**?
- [ ] Đã xem CPU affinity, memory nodes effective và giới hạn container?
- [ ] Có chứng cứ workload bị remote DRAM/memory locality ảnh hưởng?
- [ ] Đã xem heap allocation profile, Old/young ratio, native/off-heap memory?
- [ ] Đã kiểm tra memory headroom và contention từng node?
- [ ] Đã giữ nguyên JDK/GC/heap/threads/affinity/logging trong A/B?
- [ ] Đã chạy warm-up và nhiều runs thay vì một lần đo?
- [ ] Đã thu p95/p99, throughput, GC pauses, CPU và memory metrics?
- [ ] Có lợi ích lặp lại **vượt noise** và không vi phạm SLO?
- [ ] Có rollback plan nếu NUMA on không phù hợp?
- [ ] Có ghi lại môi trường và kết quả để đội vận hành kiểm chứng?

## 19. Nguồn kỹ thuật hiện hành

1. [OpenJDK JEP 345 — NUMA-Aware Memory Allocation for G1](https://openjdk.org/jeps/345): mục tiêu đưa NUMA-aware G1 allocation vào Java 14; đây là bối cảnh thiết kế, không phải bảo đảm hiệu năng.
2. [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `UseG1GC`, `UseNUMA`, `PrintFlagsFinal`, logging và quản lý heap/large pages.
3. [Oracle Java SE 25 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): region, young/old, GC pauses, throughput và G1 ergonomics.
4. [Oracle Java SE 25 — G1 Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): khuyến nghị dùng defaults, tránh cố định young size và đánh giá pause/throughput.
5. [Linux kernel — Control Group v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html): ý nghĩa của `cpuset.cpus.effective` và `cpuset.mems.effective`.
6. [Sangheon Kim — NUMA-Aware Memory Allocation for G1 GC](https://sangheon.github.io/2020/11/03/g1-numa.html): giải thích implementation Eden/Survivor, giới hạn ban đầu với Old region và ví dụ workload; dùng làm bối cảnh kỹ thuật lịch sử, kiểm tra JDK mục tiêu khi đi sâu nội bộ.
7. [Oracle Java SE 25 — GC Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html): căn cứ lựa chọn GC và tối ưu dựa vào workload.

**Ghi nhớ:** G1 NUMA-aware hỗ trợ cải thiện locality trong những điều kiện nhất định, **không phải luôn có lợi**. Với một node, heap nhỏ, workload CPU/I/O-bound, dữ liệu chung chéo node, native memory hay container bị giới hạn, tác dụng có thể không đáng kể hoặc âm. Đừng kết luận từ số CPU, một flag true hoặc một benchmark ngắn: kiểm tra topology, chạy A/B công bằng và quyết định bằng SLO cùng bằng chứng đo lường.