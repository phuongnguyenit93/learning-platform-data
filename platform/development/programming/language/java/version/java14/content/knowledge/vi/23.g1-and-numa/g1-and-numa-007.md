# Ảnh hưởng của luồng, giới hạn CPU và cách đặt bộ nhớ đối với G1 và NUMA

> **Phạm vi:** Bài thuộc **Java 14 → G1 và NUMA**. JEP 345 đã bổ sung cấp phát bộ nhớ nhận biết NUMA cho **Garbage-First Garbage Collector (G1)** từ JDK 14; cơ chế G1, các thiết lập CPU/GC và `-XX:+UseNUMA` vẫn liên quan trong HotSpot JDK hiện hành. Nội dung dưới đây hướng tới **Java 17+ và JDK 21/25** đang được dùng phổ biến; không sử dụng công cụ/flag legacy. Cần đọc kết quả trên **đúng JDK, hệ điều hành, topology và cgroup** trước khi quyết định tối ưu.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt **CPU logic**, **Java application threads**, **G1 parallel pause workers**, **concurrent GC threads** và **NUMA nodes**.
2. Giải thích ảnh hưởng của giới hạn **CPU quota**, **CPU affinity/cpuset**, **memory limit**, **NUMA memory nodes** tới khả năng JVM cấp phát và thu hồi bộ nhớ.
3. Hiểu ý nghĩa của NUMA locality: truy cập RAM gần CPU thường có độ trễ thấp hơn truy cập RAM thuộc node khác; quan hệ này không phải bảo đảm từng thao tác luôn nhanh hơn.
4. Mô tả G1 phân chia Java heap thành **regions** và cơ chế cố gắng cấp phát **Eden/young regions** theo NUMA node của thread, trong phạm vi OS cho phép.
5. Biết khi nào nên thử `-XX:+UseNUMA` và khi nào nó có thể không đem lại lợi ích, bị vô hiệu hóa hoặc gây chi phí quản trị/di chuyển bộ nhớ.
6. Dùng `Runtime.getRuntime().availableProcessors()`, `-XX:ActiveProcessorCount`, `-XX:ParallelGCThreads` và `-XX:ConcGCThreads` đúng mục đích.
7. Kiểm tra `-XX:+UseContainerSupport`, CPU throttling, mức tiêu thụ **heap và non-heap** trong container.
8. Đo trạng thái thực tế qua **Unified Logging**, các công cụ Linux như `numactl`/`numastat` và lệnh chẩn đoán JVM phù hợp.
9. Thiết kế so sánh **NUMA bật/tắt**, số luồng, CPU pinning và memory policy mà không nhầm tương quan với nguyên nhân.
10. Viết/chạy ví dụ Java 17+ có giới hạn cấp phát để quan sát những khác biệt qua logs và số liệu, không đưa ra một stdout hiệu năng giả cố định.

**Nguyên tắc chính:** G1 và NUMA tối ưu **nơi đặt các trang bộ nhớ và việc CPU truy cập chúng**, còn số luồng và CPU quota quyết định **có bao nhiêu công việc có thể chạy song song**. Nếu hai phần không tương thích, việc bật một flag đơn lẻ có thể không mang lại hiệu quả.

## 2. G1 hoạt động thế nào trong bức tranh CPU và bộ nhớ?

**G1** là garbage collector phân thế hệ, chia Java heap thành các **region** có kích thước được điều chỉnh theo heap. G1 thực hiện một phần công việc **stop-the-world (STW)** bằng nhiều luồng song song và một phần **concurrent** trong khi ứng dụng vẫn chạy.

Các thành phần quan trọng:

| Thành phần | Vai trò | Liên quan tới CPU/NUMA |
| --- | --- | --- |
| **Mutator/application threads** | Chạy code ứng dụng, tạo object, dùng dữ liệu | CPU chạy thread thường truy cập trang bộ nhớ chứa object; nơi đặt trang có thể tạo local/remote accesses. |
| **G1 Eden regions** | Vùng young generation nơi đa số object mới được cấp phát | NUMA-aware allocation có thể liên kết Eden regions với node để tăng cơ hội object gần thread tạo ra nó. |
| **Survivor regions** | Vùng young generation chứa object sống sót sau GC | Việc copy/evacuation và lựa chọn node có thể ảnh hưởng locality qua các vòng GC. |
| **Old/humongous regions** | Chứa object sống lâu hoặc rất lớn | Có chính sách/phân bổ khác young regions; không mặc định mọi object old đều đi theo node của thread dùng nó. |
| **Parallel GC workers** | Xử lý collection work trong STW pauses | Có thể dùng nhiều CPU, ảnh hưởng pause time và CPU contention. |
| **Concurrent GC workers** | Làm các pha GC song song với mutator | Cạnh tranh CPU với ứng dụng khi CPU quota thấp. |
| **Concurrent refinement workers** | Xử lý remembered-set/card updates | Có thể tiêu thụ CPU khi ứng dụng đang chạy; khi không theo kịp, phần việc có thể dồn vào GC pause. |
| **NUMA node** | Nhóm CPU/physical memory với chi phí truy cập khác nhau | Locality phụ thuộc topology, affinity, memory policy, page placement và thread migration. |

Theo tài liệu Oracle Java SE 25, G1 được thiết kế để cân bằng **throughput** và **pause-time goal**; G1 không phải real-time collector. Giá trị `-XX:MaxGCPauseMillis` là **mục tiêu điều chỉnh**, không phải SLA đảm bảo mọi GC pause đều thấp hơn một con số.

**G1 regions không đồng nghĩa NUMA nodes.** Một máy có thể có 2 NUMA nodes nhưng heap chứa hàng nghìn G1 regions. Mỗi region là một đơn vị quản lý heap; các trang vật lý backing region được OS đặt trên node cụ thể theo chính sách/hint thực tế.

### 2.1. Vì sao đối tượng mới liên quan nhiều tới NUMA?

Một số ứng dụng có nhiều luồng thường xuyên tạo object ngắn sống: request buffers, DTOs, parsing intermediates hoặc batch messages. Nếu luồng đang chạy trên CPU thuộc node 0 nhưng trang bộ nhớ của object nằm ở node 1, access có thể đi qua interconnect và tốn hơn truy cập local.

JEP 345 cho phép G1 cố gắng **allocate và giữ các object young ở cùng NUMA node** qua nhiều lần GC để giảm truy cập remote. Cơ chế không hứa mọi object hoặc mọi allocation đều local. Nếu thread bị scheduler chuyển sang CPU thuộc node khác, locality của dữ liệu đã tồn tại có thể thay đổi tương đối với thread.

### 2.2. Dòng sự kiện khái niệm

```text
Ứng dụng có nhiều Java threads
      |
      +--> Thread A chạy trên CPU của node 0
      |        |
      |        +--> tạo object tại Eden region được gắn node 0 (khi khả thi)
      |
      +--> Thread B chạy trên CPU của node 1
               |
               +--> tạo object tại Eden region được gắn node 1 (khi khả thi)

G1 young GC:
      - Parallel workers evacuate/copy live objects
      - Cố gắng giữ cơ hội locality của young data
      - Old/humongous placement chịu các quy tắc khác

OS:
      - Điều khiển CPU affinity, allowed memory nodes và page placement
      - Có thể migrate thread/pages hoặc fallback sang node khác
```

Đây là sơ đồ **ý tưởng**, không phải mô tả mọi thuật toán G1 trong từng release. Thay đổi GC, OS kernel, thư viện NUMA và vùng nhớ được phép có thể làm thay đổi hành vi.

## 3. NUMA là gì, và «local memory» có nghĩa gì?

**Non-Uniform Memory Access (NUMA)** là kiến trúc trong đó CPU có khoảng cách/chi phí truy cập RAM khác nhau tùy bộ nhớ vật lý gắn với node nào.

Ví dụ một server hai socket:

```text
        NUMA node 0                        NUMA node 1
  CPU cores 0...N                   CPU cores N+1...M
      |                                    |
    RAM 0                                 RAM 1
      \                                  /
       \--- interconnect giữa các node--/
```

Đường **CPU node 0 → RAM node 0** thường là local; đường **CPU node 0 → RAM node 1** là remote. Số node, CPU IDs, dung lượng, khoảng cách và latency thực tế phụ thuộc phần cứng/firmware/OS.

**Không được giả định** CPU 0–7 luôn là node 0 hoặc node 1 luôn có cùng dung lượng RAM. Với Linux, kiểm tra trực tiếp:

```bash
numactl --hardware
numactl --show
lscpu -e=CPU,NODE,SOCKET,CORE,ONLINE
```

Các công cụ `numactl`/`lscpu` là công cụ của Linux; chúng phải được cài và process phải có quyền xem topology. Trong VM/container, topology quan sát được có thể đã bị ảo hóa hoặc giới hạn.

### 3.1. CPU placement và memory placement là hai chính sách khác nhau

| Điều khiển | Ví dụ | Tác động |
| --- | --- | --- |
| CPU affinity | `taskset`, `numactl --cpunodebind=...` | Giới hạn CPU mà process/thread được scheduler đặt lên. |
| Memory nodes allowed | Linux cpuset `mems`, `numactl --membind=...` | Giới hạn node RAM được cấp phát. |
| Local/preferred allocation | `numactl --localalloc`, `--preferred=...` | Ưu tiên node cụ thể, nhưng có thể fallback theo chính sách. |
| Interleaving | `numactl --interleave=...` | Trải allocation trên các nodes để phân tải, không nhất thiết tối đa locality. |
| JDK NUMA awareness | `-XX:+UseNUMA` với collector/hardware hỗ trợ | Cho JVM khả năng tận dụng thông tin NUMA; hiệu lực thực tế phụ thuộc OS/process constraints. |
| Cgroup CPU quota | `cpu.max` (v2) | Hạn chế tổng thời gian chạy CPU theo period; không trực tiếp chọn node RAM. |
| Cgroup memory limit | `memory.max` (v2) | Hạn chế tổng bộ nhớ container được phép dùng; không phải chỉ heap. |

**Một process có thể chạy trên 2 logical CPUs nhưng được phép dùng memory ở nhiều nodes**, hoặc ngược lại. Giới hạn CPU và memory nodes có thể không cùng topology.

### 3.2. Cẩn thận với một node hoặc cpuset bị thu hẹp

Nếu process chỉ được phép dùng **một NUMA node**, không có lợi thế cross-node để G1 tối ưu young-region placement. Nếu CPU được phép chạy trên node A nhưng memory chỉ được phép cấp ở node B, mục tiêu local allocation cũng khó đạt.

Trong những bản HotSpot hiện hành, các trường hợp một node hay cấu hình CPU/memory nodes không khớp có thể khiến NUMA optimization **không được áp dụng** dù người dùng đã truyền `-XX:+UseNUMA`. **Đừng chỉ đọc command-line flag rồi khẳng định NUMA đang hiệu lực.** Xem startup logs và topology thực tế của đúng runtime.

Đặc biệt, Linux memory policy và cpuset được OS áp dụng trước các hint của JVM. `--membind` nghiêm ngặt có thể gây thất bại allocation khi node được chọn hết RAM, dù node khác còn RAM.

## 4. Tính năng NUMA-aware của G1 từ JDK 14 còn liên quan gì hiện nay?

**JEP 345 — NUMA-Aware Memory Allocation for G1** đưa cơ chế NUMA awareness cho G1. Theo mô tả thiết kế và release notes:

1. G1 cố gắng cấp phát vùng trẻ gần **NUMA node của thread đang allocate**.
2. G1 cố gắng giữ dữ liệu ở node hợp lý khi di chuyển object qua các lần young collection.
3. Các vùng **old** và **humongous** có cách phân bố riêng; đừng cho rằng locality của chúng tương đương Eden.
4. Cơ chế được kích hoạt/thử nghiệm bằng `-XX:+UseNUMA` trên nền tảng hỗ trợ; không bảo đảm hiệu quả như nhau ở mọi topology.
5. Kết quả phụ thuộc allocation rate, object lifetime, thread migration và policy của OS.

### 4.1. `-XX:+UseNUMA` không phải nút tăng tốc toàn cục

Câu lệnh có thể dùng trên môi trường HotSpot/Linux đủ điều kiện:

```bash
java -XX:+UseG1GC -XX:+UseNUMA -Xms2g -Xmx2g -jar app.jar
```

Đây là **lệnh mẫu** khi đã có `app.jar`, server đủ RAM và hai hoặc nhiều NUMA nodes khả dụng. Nó không phải khuyến nghị copy vào production ngay lập tức.

Để so sánh với cấu hình tắt:

```bash
java -XX:+UseG1GC -XX:-UseNUMA -Xms2g -Xmx2g -jar app.jar
```

Sự khác biệt chỉ có ý nghĩa khi **cùng JDK, workload, CPU quota/affinity, memory policy, heap settings** và điều kiện đo đại diện. Nếu chỉ có một node, heap nhỏ hoặc producer liên tục migrate giữa nodes, `UseNUMA` có thể không tạo lợi thế đo được.

**Không khẳng định mặc định UseNUMA luôn bật hay luôn tắt** trên mọi JDK/collector. Theo tài liệu `java` của Oracle, default phụ thuộc GC; một số kết hợp nền tảng không thực thi NUMA optimization. Kiểm tra cờ hiệu lực và logs của bản JDK đang vận hành.

### 4.2. Vì sao tăng số NUMA nodes không tự tạo throughput lớn hơn?

Server có thêm socket/node có thể cung cấp CPU và memory bandwidth cao hơn, nhưng cũng làm tăng không đồng nhất của truy cập RAM. Nếu workload ít luồng hoặc heap rất nhỏ so với dung lượng local memory, phân phối heap đa node có thể không cần thiết. Ngược lại, với heap rất lớn và nhiều threads trên các nodes, remote memory access/NUMA imbalance có thể trở thành bottleneck.

**Tối ưu NUMA không thay thế việc giảm allocation rate hoặc nâng hiệu quả algorithm của ứng dụng.** Khi dữ liệu bị chia sẻ mạnh giữa nhiều nodes, chưa chắc chiến lược giữ object gần thread tạo ra nó tối ưu cho thread dùng về sau.

## 5. Số luồng của ứng dụng ảnh hưởng G1 và locality ra sao?

Một ứng dụng có nhiều threads có thể phát sinh:

- **Allocation rate cao hơn:** Nhiều tasks tạo object cùng lúc → Eden đầy nhanh hơn → G1 young GC xảy ra thường xuyên hơn.
- **Nhiều thread-local allocation buffers (TLABs):** HotSpot dùng TLAB để cấp phát nhanh; chúng liên quan đến nơi thread lấy vùng nhớ, nhưng không phải mỗi TLAB là một NUMA node độc lập.
- **Remote accesses:** Thread chạy tại node khác nơi trang bộ nhớ của object được đặt, đặc biệt nếu scheduler chuyển thread hoặc dữ liệu được truyền giữa các worker.
- **Native memory tăng:** Mỗi platform thread cần stack và metadata; số luồng cao có thể gây áp lực bộ nhớ ngay cả khi Java heap còn trống.
- **Contended CPUs:** Threads ứng dụng, GC workers, JIT compiler và OS tasks phải chia sẻ các CPU thực sự sẵn có.

| Tình huống | Lợi ích tiềm năng | Rủi ro |
| --- | --- | --- |
| Ít luồng, heap nhỏ, một socket | Đơn giản, chi phí chuyển node thấp | Không có nhiều lợi ích từ NUMA-aware G1. |
| Nhiều luồng phân bổ hợp lý ở hai socket | Nhiều CPU và bandwidth; locality hữu ích khi dữ liệu gần worker | Nếu allocation và data-sharing không cân, một node có thể bị quá tải. |
| Nhiều luồng hơn CPU quota | Có thể giữ nhiều tác vụ chờ I/O | CPU-bound work và GC tranh CPU, nhiều context switches, throttling. |
| Thread thường migrate giữa nodes | Scheduler linh hoạt cân tải | Memory đang local có thể trở thành remote sau migration. |
| Pin threads/process chặt vào một node | Có thể ổn định locality và cache | Mất tính linh hoạt, thiếu local memory/CPU, NUMA optimization đa node không còn tác dụng. |

**Luồng Java không phải CPU.** `Executors.newFixedThreadPool(32)` tạo tối đa 32 worker threads của pool, không tạo 32 CPU cores. `Runtime.availableProcessors()` phản ánh số processor mà JVM xem là available, không phải số threads ứng dụng hoặc số socket NUMA.

Đối với Java 21+ có **virtual threads**, số lượng virtual threads càng không thể dùng làm thước đo CPU vật lý hoặc số carrier threads. Dù ứng dụng dùng virtual threads, việc G1/NUMA vẫn phụ thuộc các OS threads thực sự chạy, allocation và page placement.

### 5.1. Số threads cao có thể khiến GC xấu hơn

Ví dụ một container chỉ có quota tương đương 2 CPU nhưng application thread pool có 64 threads xử lý CPU-intensive jobs:

- Producer tạo nhiều object, gây áp lực heap/GC.
- G1 concurrent marking phải chia CPU với các job.
- STW GC workers không thể có 64 CPU cores chỉ vì ứng dụng có 64 threads.
- OS có thể throttling khi quota hết trong cgroup period.
- Tail latency của request có thể tăng dù tổng lượng RAM chưa đầy.

Hãy kiểm tra **CPU saturation, context switches, GC logs, allocation rate, throughput và p95/p99 latency** trước khi tăng số luồng. Số tối ưu phụ thuộc tác vụ CPU-bound hay I/O-bound, không có công thức cố định cho mọi ứng dụng.

## 6. Số GC worker threads: parallel và concurrent khác nhau

G1 dùng nhiều loại worker. Hai tùy chọn JVM cần biết:

| Tùy chọn | Ý nghĩa | Tác động |
| --- | --- | --- |
| `-XX:ParallelGCThreads=N` | **Giới hạn/định hướng số threads cho các pha GC song song khi dừng ứng dụng** | Quá ít: STW GC work kéo dài; quá nhiều so với CPU hữu dụng: overhead, scheduling và contention. |
| `-XX:ConcGCThreads=N` | **Số threads dành cho concurrent GC marking** | Quá ít: marking có thể không theo kịp allocation/promotion; quá nhiều: chiếm CPU của application threads. |
| `-XX:G1ConcRefinementThreads=N` | Giới hạn concurrent remembered-set refinement threads của G1 | Thay đổi phân bố công việc refinement và phần có thể dồn vào pauses. |
| `-XX:ActiveProcessorCount=N` | Ghi đè số active processors HotSpot dùng cho heuristics | Ảnh hưởng kích thước GC thread pools và các cơ chế JVM khác, không tạo CPU thật. |

Theo hướng dẫn G1 của Oracle JDK 25, `ParallelGCThreads` được tính theo số CPU hữu dụng và các heuristics liên quan; số **workers thực sự sử dụng trong từng pause** có thể thấp hơn mức tối đa vì workload/heap size. `ConcGCThreads` được chọn ergonomically gần một phần của parallel worker count, nhưng không nên viết thành công thức bắt buộc trên mọi JDK.

**Đừng nhầm:** G1 concurrent worker threads chạy trong lúc application threads chạy; parallel workers STW chạy khi ứng dụng tạm dừng ở các GC pause. Hai loại ảnh hưởng latency theo cách khác nhau.

### 6.1. Ví dụ số threads không phải khuyến nghị mặc định

```bash
java -XX:+UseG1GC \
  -XX:ActiveProcessorCount=4 \
  -XX:ParallelGCThreads=4 \
  -XX:ConcGCThreads=1 \
  -Xms512m -Xmx512m \
  -jar app.jar
```

Đây là **cấu hình thí nghiệm** cho một JVM HotSpot, không phải bộ flags tối ưu sẵn. Cần đủ RAM cho heap và native memory; phải có ứng dụng `app.jar`; `-XX:ActiveProcessorCount=4` không làm container được phép chạy trên bốn CPU nếu quota/affinity thấp hơn.

Cách tiếp cận tốt hơn khi chưa có dữ liệu là **để mặc định G1 ergonomics**, đo vấn đề, rồi thay đổi **một biến mỗi lần**. Tài liệu Oracle khuyên bắt đầu từ mặc định, cân nhắc `-Xmx` và pause target trước khi điều chỉnh sâu.

### 6.2. Khi nào nên xem xét `ConcGCThreads`?

Nếu log cho thấy **concurrent marking quá chậm** so với tốc độ cấp phát/promote, old occupancy tăng và ứng dụng tiến gần Full GC, số concurrent workers có thể là một yếu tố cần thử. Nhưng tăng `ConcGCThreads` đồng nghĩa lấy thêm CPU từ app và có thể làm **throughput** hoặc **tail latency** xấu hơn trong CPU-constrained container.

Nếu vấn đề là **STW evacuation phase** kéo dài, hãy phân tích pause phase/log và `ParallelGCThreads`, heap/region/young sizing, allocation pattern, reference processing, NUMA locality. Không mặc định tăng concurrent workers sẽ rút mọi STW pause.

## 7. CPU quota, cpuset và `ActiveProcessorCount`

Trong môi trường container Linux, có **ba khái niệm riêng**:

1. **CPU affinity/cpuset:** Tập logical CPUs mà process được phép chạy.
2. **CPU quota:** Ngân sách CPU time mỗi cgroup period, ví dụ 200.000 µs CPU time trong period 100.000 µs tương đương quota 2 CPUs trung bình.
3. **HotSpot active processor count:** Giá trị JVM dùng cho nhiều heuristics, có thể được suy từ OS/container hoặc **ghi đè** bằng `-XX:ActiveProcessorCount`.

`Runtime.getRuntime().availableProcessors()` trả active processors **theo quan sát của JVM**. Nó có thể phản ánh giới hạn container hoặc flags JVM, nhưng **không chứng minh số cores vật lý hay CPU quota thực tế đang còn trống**.

### 7.1. `-XX:+UseContainerSupport`

HotSpot JDK hiện hành trên Linux có **container detection** mặc định bật theo tài liệu Java SE 25. VM dùng CPU/memory limits quan sát được để đặt heuristics. Không cần copy `-XX:+UseContainerSupport` vào mọi lệnh chỉ để «bật» nó; trước tiên kiểm tra mặc định runtime.

Dùng:

```bash
java -XshowSettings:system -version
java -Xlog:os+container=trace -version
```

Các kết quả chẩn đoán phụ thuộc container, cgroup version, OS, quyền truy cập và JDK. `-Xlog:os+container=trace` đặc biệt hữu ích khi cần hiểu **HotSpot đã nhìn thấy CPU/memory limits nào**. Không coi stdout của hai lệnh này cố định giữa các máy.

### 7.2. `-XX:ActiveProcessorCount` là override logic, không phải OS pinning

Ví dụ:

```bash
java -XX:ActiveProcessorCount=2 \
  -XX:+UseG1GC \
  G1ResourceProbe
```

Flag yêu cầu HotSpot dùng giá trị **2** cho các heuristics liên quan. Nó **không**:

- Thêm hai CPU cores vào cgroup;
- Thay `taskset`/`numactl` để pin thread;
- Tăng CPU quota được OS cấp;
- Chuyển dữ liệu heap sang NUMA node khác;
- Đảm bảo mọi GC pause sẽ có đúng 2 workers.

Dùng override khi số CPU được JVM tự nhận diện **không phù hợp với budget thực tế** hoặc khi cần thử nghiệm có kiểm soát. Nếu đặt `ActiveProcessorCount=16` nhưng cgroup chỉ cho 2 CPU, JVM có thể tạo nhiều worker hơn mức CPU time hữu ích, làm contention/trễ nặng hơn.

### 7.3. CPU limit 2 vCPU không có nghĩa «2 NUMA nodes»

Container có thể bị giới hạn quota 2 vCPU nhưng chạy trên host có 2 socket, 4 NUMA nodes, hoặc topology chỉ expose 1 virtual node. **CPU quota và node count là hai trục độc lập**; cần đọc cả thông tin scheduler/cgroup và NUMA topology.

Ví dụ trong Linux cgroup v2:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpuset.mems.effective
```

Các đường dẫn là **ví dụ cho process có cgroup v2 mount theo bố cục phổ biến**; trong container cụ thể chúng có thể ở cgroup mount/path khác, không tồn tại nếu hệ thống dùng cgroup v1 hoặc quyền truy cập hạn chế.

- `cpu.max` có hai trường quota/period, hoặc `max` nếu không giới hạn.
- `cpu.stat` cung cấp counters liên quan sử dụng/throttling theo kernel.
- `cpuset.cpus.effective` mô tả CPUs được phép.
- `cpuset.mems.effective` mô tả memory nodes được phép.

**Giới hạn theo quota** tạo tình trạng bị throttle khi nhóm threads tiêu hết thời gian CPU, trong khi **affinity** quyết định nơi chúng có thể chạy. Chỉ đọc một trong hai là chưa đủ để chẩn đoán.

## 8. Memory limit, Java heap và native memory

Một sai lầm hay gặp là đặt `-Xmx` bằng đúng container memory limit rồi cho rằng JVM có thể chạy ổn định.

**Java process dùng nhiều bộ nhớ ngoài heap:**

- Thread stacks của platform threads;
- Metaspace/class metadata;
- JIT code cache;
- JVM/native runtime structures;
- Direct buffers/mapped memory;
- Native libraries, TLS/network buffers;
- GC/JFR/monitoring overhead và các phần khác.

Do đó:

```text
Total process/container memory
  ≈ Java heap committed/used
  + thread stacks
  + metaspace/code cache
  + direct/native memory
  + runtime/GC overhead
  + các chi phí OS/container liên quan
```

Đây là **sơ đồ thành phần**, không phải công thức kế toán RSS tuyệt đối: các loại memory accounting có thể dùng định nghĩa khác nhau, và cgroup còn ghi nhận page cache hoặc tiến trình khác tùy cấu hình.

Ví dụ container limit **4 GiB**: đặt `-Xmx4g` có thể khiến native overhead đẩy container vượt limit và bị **OOM kill** bởi OS, mặc dù Java heap chưa ném `OutOfMemoryError`. Một lựa chọn như `-Xmx2g` có thể để lại headroom, nhưng giá trị hợp lý phụ thuộc workload, số threads, framework/native libraries và mục tiêu GC; **không có tỷ lệ Xmx/container-limit cố định cho mọi app**.

### 8.1. `-Xms`, `-Xmx` và physical page placement

- `-Xmx` quy định **kích thước heap tối đa**, không phải yêu cầu OS cấp phát ngay toàn bộ số trang vật lý.
- `-Xms` định hướng initial heap size/commit tại startup.
- `-XX:+AlwaysPreTouch` khiến JVM chạm các trang bộ nhớ heap đã được commit ở startup, chuyển một phần công việc page fault sang lúc khởi động; có thể làm startup chậm và tăng memory footprint sớm.
- Với NUMA, **lúc trang vật lý thực sự được cấp phát/chạm** và policy của OS có thể ảnh hưởng nơi nó nằm. `AlwaysPreTouch` không phải bảo đảm mọi trang đều local với worker sẽ dùng sau này.

Tài liệu Oracle G1 có đề cập kết hợp `-Xms` bằng `-Xmx` với `-XX:+AlwaysPreTouch` như một cách **giảm variability do heap resizing/page backing** trong một số workload. Nhưng trước khi áp dụng trong container chặt bộ nhớ, phải đo startup, RSS/peak memory, cgroup OOM risk và NUMA placement.

**Không nhầm `-Xmx` với `-XX:MaxRAMPercentage`:** `MaxRAMPercentage` là heuristic tỷ lệ dựa trên memory mà JVM nhận diện; `-Xmx` đặt giới hạn cụ thể. Cả hai **không** biến non-heap memory thành miễn phí.

## 9. Chọn vị trí CPU và RAM: ví dụ Linux `numactl`

Các lệnh sau chỉ nên dùng trên **Linux host có numactl và các nodes được phép**, không chạy mù trên máy/container khác.

### 9.1. Kiểm tra topology và policy trước

```bash
numactl --hardware
numactl --show
lscpu -e=CPU,NODE,SOCKET,CORE
```

Giả sử topology thực tế cho biết process được phép dùng **node 0 và 1**, một thí nghiệm có thể là:

```bash
numactl --cpunodebind=0,1 --membind=0,1 \
  java -XX:+UseG1GC -XX:+UseNUMA \
       -Xms512m -Xmx512m G1AllocationDemo
```

- `--cpunodebind=0,1` giới hạn CPU nodes chạy process;
- `--membind=0,1` giới hạn memory nodes được cấp phát;
- `-XX:+UseNUMA` cho G1 cơ hội áp dụng heuristic NUMA nếu thực tế đủ điều kiện;
- `-Xms/-Xmx` cố định heap tối đa/ban đầu cho phép so sánh;
- `G1AllocationDemo` là chương trình hoàn chỉnh ở phần sau.

Nếu muốn thử chạy **chỉ trên node 0**:

```bash
numactl --cpunodebind=0 --membind=0 \
  java -XX:+UseG1GC -XX:+UseNUMA \
       -Xms512m -Xmx512m G1AllocationDemo
```

Cấu hình một node **không phải thí nghiệm đo lợi ích NUMA-aware multi-node**; việc pin một node có thể khiến cơ chế NUMA trong JVM không còn cần thiết hoặc bị tắt. Nó có thể cải thiện/tệ đi do thay đổi số CPU hữu dụng hoặc memory capacity, nên không được so sánh thiếu điều kiện với cấu hình hai nodes.

### 9.2. `--membind` khác `--localalloc`

- `--membind=N`: chỉ cấp phát trên những memory nodes được phép; nếu không đủ RAM có thể gặp lỗi allocation.
- `--localalloc`: cố gắng cấp phát gần CPU hiện tại, có thể fallback sang node khác nếu thiếu memory.
- `--interleave=...`: trải allocation qua nodes; hữu ích để cân tải nhưng không tương đương locality tối đa.
- `--cpunodebind` chỉ hạn chế CPU nodes; không đồng nghĩa nó tự chọn đúng memory policy cho mọi pages.

Khi container/OS giới hạn `cpuset.mems`, các memory policies không thể vượt qua tập node thực sự được phép. Nếu quota CPU chỉ có 2 CPUs nhưng pin vào nhiều node, quá nhiều threads vẫn tranh một CPU budget nhỏ.

### 9.3. CPU node và memory node bị lệch

Ví dụ process chỉ được chạy CPU thuộc node 0 nhưng memory bị buộc chỉ node 1: hầu hết truy cập RAM của threads chạy tại node 0 phải đi remote. **Bật UseNUMA không thể tạo local RAM trên node đã bị OS cấm cấp phát**.

Một số bản HotSpot mới kiểm tra cấu hình CPU/memory nodes và vô hiệu hóa NUMA optimization khi thấy lệch; điều này tránh áp dụng chiến lược không phù hợp. Đó là lý do phải kiểm tra **trạng thái NUMA qua log** thay vì tin chỉ flag đầu vào.

**Cảnh báo vận hành:** `numactl`/affinity quá chặt có thể làm ứng dụng fail vì thiếu RAM trên node hoặc giảm throughput vì ít CPU. Hãy test với workload có kiểm soát, ghi lại policy, không thử trên JVM production mà chưa có phương án rollback.

## 10. Ví dụ Java 17+ 1: kiểm tra CPU và GC mà JVM nhìn thấy

Lưu file **`G1ResourceProbe.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public class G1ResourceProbe {
    public static void main(String[] args) {
        int processors = Runtime.getRuntime().availableProcessors();
        long maxHeapBytes = Runtime.getRuntime().maxMemory();

        boolean g1Selected = ManagementFactory
                .getGarbageCollectorMXBeans().stream()
                .map(GarbageCollectorMXBean::getName)
                .anyMatch(name -> name.startsWith("G1 "));

        System.out.println("active-processors=" + processors);
        System.out.println("g1-selected=" + g1Selected);
        System.out.println("max-heap-positive=" + (maxHeapBytes > 0));
    }
}
```

Biên dịch bằng **JDK 17+**:

```bash
javac --release 17 G1ResourceProbe.java
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 \
     -Xms64m -Xmx128m G1ResourceProbe
```

**Stdout mong đợi trên HotSpot hỗ trợ các flags:**

```text
active-processors=2
g1-selected=true
max-heap-positive=true
```

**Giải thích:**

1. `availableProcessors()` cho giá trị mà JVM công bố, **không** đếm NUMA nodes.
2. Vì lệnh truyền `-XX:ActiveProcessorCount=2`, HotSpot hiển thị 2 CPUs cho heuristics ứng dụng/GC, dù máy vật lý có thể nhiều cores hơn.
3. `ManagementFactory.getGarbageCollectorMXBeans()` cho tên collectors đang dùng; các tên G1 điển hình là `G1 Young Generation` và `G1 Old Generation` trên HotSpot. Code chỉ kiểm tra có collector tên bắt đầu bằng `"G1 "`.
4. `maxMemory()` không phải RSS/current physical memory và không cho biết trang heap nằm ở node nào. Code chỉ assert giá trị positive để stdout không phụ thuộc cách HotSpot làm tròn heap.
5. Cả ba dòng **không kiểm chứng UseNUMA đang hiệu lực**. Muốn vậy, phải kiểm tra `-XX:+UseNUMA` cùng OS topology/logs và memory placement.

**Giới hạn ví dụ:** Code dùng `java.management` chuẩn. Một runtime thu gọn không gồm module `java.management` sẽ cần bổ sung nó; với JDK đầy đủ Java 17+ không phải vấn đề.

### 10.1. Chạy thêm các cấu hình để so sánh

```bash
java -XX:+UseG1GC -XX:ActiveProcessorCount=1 \
     -Xms64m -Xmx128m G1ResourceProbe

java -XX:+UseG1GC -XX:ActiveProcessorCount=4 \
     -Xms64m -Xmx128m G1ResourceProbe
```

Chỉ giá trị `active-processors` khác theo override; **không thể suy ra tốc độ G1 hay NUMA placement** từ ba dòng trên. CPU budget thật có thể thấp hơn giá trị ép.

## 11. Ví dụ Java 17+ 2: tạo tải cấp phát đa luồng có giới hạn

Để có hoạt động allocation/GC quan sát được, có thể chạy một workload giới hạn số tasks, dùng một heap vừa phải và **không** giữ toàn bộ arrays lâu dài.

Lưu file **`G1AllocationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class G1AllocationDemo {
    static long allocate(int workerId) {
        long checksum = 0L;

        for (int round = 0; round < 200; round++) {
            byte[][] blocks = new byte[64][];

            for (int i = 0; i < blocks.length; i++) {
                byte[] bytes = new byte[16 * 1024];
                bytes[0] = (byte) (workerId + i + 1);
                blocks[i] = bytes;
            }

            for (byte[] bytes : blocks) {
                checksum += bytes[0];
            }
        }
        return checksum;
    }

    public static void main(String[] args) throws Exception {
        int workers = Math.max(1, Math.min(
                4, Runtime.getRuntime().availableProcessors()));

        ExecutorService pool = Executors.newFixedThreadPool(workers);
        try {
            List<Future<Long>> futures = new ArrayList<>();

            for (int i = 0; i < workers; i++) {
                final int workerId = i;
                Callable<Long> job = () -> allocate(workerId);
                futures.add(pool.submit(job));
            }

            long total = 0L;
            for (Future<Long> future : futures) {
                total += future.get();
            }

            System.out.println("workers=" + workers);
            System.out.println("tasks-finished=" + futures.size());
            System.out.println("checksum-nonzero=" + (total != 0));
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch:

```bash
javac --release 17 G1AllocationDemo.java
```

Chạy với G1 và override 2 active CPUs:

```bash
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 \
     -Xms64m -Xmx128m G1AllocationDemo
```

**Stdout riêng của chương trình trong điều kiện chạy thành công:**

```text
workers=2
tasks-finished=2
checksum-nonzero=true
```

**Vì sao có thể dự đoán ba dòng?**

- `workers` được giới hạn tối đa 4 và lấy từ `availableProcessors()`, nên với `ActiveProcessorCount=2` bằng 2.
- Chương trình submit đúng `workers` tasks rồi chờ tất cả `Future.get()`; chỉ in kết quả sau khi tasks hoàn tất.
- Mỗi task cộng byte có giá trị dương với `workerId` 0–1 và `i` 0–63, nên `total` khác 0.
- Mỗi vòng có khoảng 1 MiB arrays được cấp phát rồi không còn được giữ khi sang vòng tiếp theo; workload có thể kích hoạt nhiều GC nhưng **số lần GC không cố định**.
- Không in elapsed time hay GC pause vì chúng phụ thuộc phần cứng, JIT, tải máy và cấu hình runtime.

**Đừng xem đây là benchmark NUMA chuẩn.** Khối lượng/độ phức tạp nhỏ và không kiểm soát page placement, affinity, JIT warm-up hoặc concurrency của host. Nó chỉ là **workload thực hành**, giúp kiểm tra flags, quan sát GC log và hiểu ảnh hưởng của số worker.

### 11.1. Bật GC logs để xem diễn biến

```bash
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 \
     -Xms64m -Xmx128m \
     -Xlog:gc*=info \
     G1AllocationDemo
```

Output sẽ có thêm các dòng GC logs **phụ thuộc lần chạy**, trong đó thường có thông tin pause/heap và collection type. Không hardcode số GC hoặc số mili-giây; hãy đo lại trên máy của bạn.

Có thể tăng độ chi tiết có mục đích:

```bash
java -XX:+UseG1GC \
     -XX:ActiveProcessorCount=2 \
     -Xms64m -Xmx128m \
     -Xlog:gc*=debug \
     G1AllocationDemo
```

Log `debug` có thể khá lớn; chỉ bật trong thí nghiệm hoặc với rotation/retention phù hợp.

## 12. Kiểm tra CPU/G1/NUMA settings hiệu lực

### 12.1. Các cờ HotSpot quan trọng

Trên JDK HotSpot đủ công cụ:

```bash
java -XX:+PrintFlagsFinal -version 2>&1 |
  grep -E 'UseG1GC|UseNUMA|ActiveProcessorCount|ParallelGCThreads|ConcGCThreads|G1ConcRefinementThreads'
```

`PrintFlagsFinal` liệt kê các flags và giá trị cuối JVM xác định (có thể có nguồn giá trị/kiểu). Đây là lệnh shell Linux/macOS với `grep`; Windows dùng PowerShell tương đương như `Select-String`.

Tuy nhiên **giá trị `UseNUMA=true` trong flags không chứng minh OS có hai nodes hữu dụng hoặc JVM đã dùng local pages theo kỳ vọng**. Một flag có thể được cấu hình nhưng tính năng bị giới hạn bởi topology/policy. Kết hợp logs và công cụ OS.

### 12.2. GC threads không nhất thiết chạy đồng thời đúng bằng flags

Ví dụ `ParallelGCThreads=8` biểu thị giới hạn/cấu hình tối đa cho G1 parallel workers trong nhiều pha. G1 có thể chọn số workers ít hơn trong một pause theo heap size và lượng việc; giá trị này không cho biết có 8 CPU thật đang chạy.

Kiểm tra GC phase/worker output bằng Unified Logging:

```bash
java -Xlog:gc+task=debug,gc+phases=debug \
     -XX:+UseG1GC -Xmx256m G1AllocationDemo
```

Cú pháp/tag cụ thể có thể khác mức độ chi tiết giữa các JDK. Dùng `java -Xlog:help` để xem tags hợp lệ; không giả định mọi bản HotSpot in cùng dòng và cùng số worker.

### 12.3. NUMA logs và vị trí trang nhớ

Thử trên Linux NUMA-capable:

```bash
java -XX:+UseG1GC -XX:+UseNUMA \
     -Xlog:numa*=debug \
     -Xms512m -Xmx512m G1AllocationDemo
```

`-Xlog:numa*=debug` là cấu hình Unified Logging để quan sát các log có tag `numa` nếu JVM/build phát hành chúng. Nó **không tự bảo đảm sẽ có một dòng NUMA**. Nếu `-Xlog:help` không liệt kê tag hoặc VM không có topology đủ điều kiện, đọc diagnostic thực tế và điều chỉnh thay vì khẳng định bật thành công.

Trên Linux có thể khảo sát process chạy lâu bằng:

```bash
numastat -p 12345
cat /proc/12345/numa_maps
```

**PID `12345` chỉ là ví dụ**, phải thay bằng PID thực sự của JVM do bạn quản lý. `numastat` hoặc `/proc/PID/numa_maps` hiển thị phân bổ memory theo node, nhưng **không tự nhận diện mọi trang là Java heap**. Chúng có thể gồm stacks, code cache, shared libs, mappings và các vùng khác. Muốn kết luận về G1 heap, cần kết hợp với JVM logs, cấu hình memory mappings/metrics và thí nghiệm cùng workload.

**Các lưu ý:**

- Cần quyền đọc process đó.
- Nếu chương trình kết thúc quá nhanh, chạy một workload/service đủ lâu để lấy snapshot.
- Với container, `/proc` và NUMA topology có thể bị che/ảo hóa.
- Thống kê node-level memory không phải trực tiếp latency hoặc throughput; muốn đo performance phải benchmark.

## 13. Vì sao ép `-XX:ParallelGCThreads` quá cao có thể phản tác dụng?

Giả sử JVM được scheduler cho quota 2 CPUs:

```text
Application: 2 CPU-bound workers
G1 concurrent mark: thêm GC worker
G1 refinement: có thể có nhiều worker khác
JIT / runtime / OS threads: tiếp tục cần CPU time
                       |
                       v
             Cgroup CPU quota = 2 vCPU
                       |
                       v
             CPU contention / throttling
```

Nếu cấu hình `-XX:ParallelGCThreads=16` mà CPU quota không đổi, G1 không nhận được 16 CPUs thực. Những pha GC cần phối hợp giữa nhiều workers có thể tăng overhead; application tail latency có thể xấu hơn.

Ngược lại, đặt `ParallelGCThreads=1` trên server nhiều cores với heap lớn và allocation rate cao có thể kéo dài STW work. **Không có giá trị số luồng đúng cho mọi workload**; đo pause distribution, GC CPU time, application throughput và scheduler throttling.

**GC logging hữu ích:**

- `-Xlog:gc=info`: loại collection và pause summary;
- `-Xlog:gc+phases=debug`: các pha chi tiết;
- `-Xlog:gc+cpu=info`: thời gian CPU liên quan GC theo định dạng runtime;
- `-Xlog:gc+task=debug`: thông tin task/worker khi có log;
- `-Xlog:os+container=trace`: CPU/memory limits HotSpot nhận diện trên Linux.

Không nên đọc `User/Sys/Real` của một GC pause như đơn vị tương đương số CPU đơn giản khi có nhiều workers; **User CPU time** có thể cộng thời gian của các threads, lớn hơn wall-clock time.

## 14. Sự tương tác giữa CPU quota và NUMA placement

Có bốn kịch bản quan trọng:

### 14.1. Multi-node host nhưng quota CPU nhỏ

Host có node 0 và node 1, nhưng container chỉ được 2 CPU time trung bình. Dù NUMA-aware allocation giúp locality phần nào, số parallel tasks có thể bị bó bởi quota. Đừng dựa vào số socket để đặt pool/GC workers lớn.

**Cần đo:** `availableProcessors()`, `cpu.max`, `cpu.stat` throttling, tổng runnable threads, throughput và GC timing.

### 14.2. cpuset chỉ dùng node 0

JVM có thể chỉ được chạy trên CPU của node 0. Nếu memory cũng chỉ node 0, phần lớn access có thể local mà không cần tối ưu đa node. Bật `UseNUMA` không đồng nghĩa có lợi ích từ nhiều node. Nếu bộ nhớ node 0 thiếu, `--membind=0` cứng có thể gây memory allocation failure/OOM.

### 14.3. CPU trên hai nodes, memory chỉ một node

CPU từ node 1 có thể phải truy cập bộ nhớ ở node 0, gây remote latency. Cấu hình này có thể phá kỳ vọng của G1 NUMA awareness. Thử thay đổi memory node allowance hoặc CPU pinning theo khả năng hệ thống, không kỳ vọng JVM vượt OS memory policy.

### 14.4. CPU và RAM trên nhiều nodes, workload đủ lớn

Đây là trường hợp đáng thử `-XX:+UseNUMA` nhất, khi:

- Multiple NUMA nodes thật sự khả dụng;
- Threads tạo/làm việc trên dữ liệu có xu hướng gắn với node nhất định;
- Heap và allocation pressure đủ lớn để locality có ý nghĩa;
- OS không buộc memory placement mâu thuẫn với CPU placement;
- CPU quota không làm workload bị bó quá chặt.

Ngay cả như vậy, cần benchmark **bật/tắt NUMA**. Số liệu throughput/pause trên một workload có thể tốt, workload khác có thể không đổi hoặc tệ hơn.

## 15. Cách làm thí nghiệm A/B đáng tin cậy

Để tránh suy luận sai, nên lập một bảng biến thể, chạy lặp nhiều vòng:

| Biến thể | G1 NUMA | CPU / GC settings | OS memory placement | Mục tiêu |
| --- | --- | --- | --- | --- |
| A — Baseline | Theo default JDK | Ergonomics mặc định | Theo OS policy hiện tại | Có mốc đo trước tối ưu. |
| B — NUMA off | `-XX:-UseNUMA` | Giữ như A | Giữ như A | Tách tác động của NUMA-aware heuristic. |
| C — NUMA on | `-XX:+UseNUMA` | Giữ như A | Giữ như A | Đo thay đổi locality/throughput/pause. |
| D — CPU tuning | Giống biến thể tốt hơn B/C | Thử `ActiveProcessorCount` hoặc GC threads **một biến mỗi lần** | Giữ ổn định | Xác định CPU contention/GC work balance. |
| E — Placement policy | Giữ như biến thể đã chọn | Giữ ổn định | So sánh pinning/interleave/local policy có kiểm soát | Kiểm tra tác động từ OS node placement. |

**Không thay đồng thời** JVM version, heap, số threads, allocator, OS affinity và workload, rồi quy hết thay đổi về `UseNUMA`. Các kết quả cần có:

1. Phiên bản JDK chính xác, VM vendor, OS/kernel, số NUMA nodes và CPUs mỗi node.
2. `-Xms/-Xmx`, collector, flags liên quan, page size/hugepages nếu có.
3. `cpu.max`/cpuset/mems, memory cgroup limit và hiện tượng throttling.
4. Throughput ứng dụng (requests/s, jobs/s), thời gian xử lý p50/p95/p99.
5. GC pause count, p95/p99 pause, GC CPU cost, concurrent cycle duration, Full GC/evacuation failure nếu có.
6. CPU usage và memory locality: `numastat`, local/remote accesses theo công cụ đo phù hợp (có quyền).
7. Startup time, memory commit/RSS/peak và OOM behavior.
8. Số lần chạy, warm-up, độ biến thiên và kết quả trung vị hoặc distribution, không chỉ 1 phép đo.

**Đo với ứng dụng thực**: Mẫu `G1AllocationDemo` chỉ tạo allocation, không đại diện topology hay production SLA. Để đo hiệu quả, dùng workload có nhiều threads thật, dữ liệu phân bố tương tự production, durations đủ dài và phân tách warm-up khỏi measurement.

### 15.1. Nhận diện kết quả tốt và xấu

| Quan sát | Có thể gợi ý | Việc cần kiểm tra |
| --- | --- | --- |
| Throughput tăng, remote memory giảm, GC pause giữ ổn định | NUMA locality hữu ích | Kiểm tra CPU quota/throttling, độ ổn định nhiều lần chạy. |
| CPU usage cao nhưng throughput không tăng | Quá nhiều threads/GC overhead | Xem contention, GC phase, concurrent marking, run queue. |
| Young GC dày hơn | Allocation rate tăng hoặc young generation nhỏ | Xem heap sizing/occupancy, object lifetime, STW logs. |
| Full GC/evacuation failure | Heap pressure, insufficient free regions, marking chưa theo kịp | Xem old occupancy, marking cycles, heap headroom và GC tuning. |
| UseNUMA on nhưng không khác biệt | Một node, nhỏ heap, OS hạn chế, workload ít nhạy locality | Xác minh logs và OS memory placement. |
| Bật `AlwaysPreTouch` làm startup chậm, RSS tăng sớm | Chạm nhiều trang ngay lúc startup | Đánh giá startup/SLA/memory cgroup thay vì chỉ steady-state. |
| Node 0 hết memory dù node 1 còn | `membind` quá chặt / cpuset.mems hạn chế | Xem OS policy, không tự tăng `-Xmx`. |

## 16. Sai lầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| «`UseNUMA=true` luôn cho performance tốt hơn». | Topology, OS constraints, thread migration và workload quyết định hiệu quả. | A/B test và quan sát NUMA thực tế. |
| «Java 14 G1 NUMA chỉ là preview và đã lỗi thời». | JEP 345 đưa khả năng này vào JDK và vẫn có cơ chế NUMA-related ở JDK hiện hành. | Dùng JDK ổn định hiện hành, xem flags/docs đúng version. |
| «N threads = N CPU cores». | Threads chia CPU time; có scheduling và blocking. | Dùng processor count/CPU quota/affinity và profile. |
| «`ActiveProcessorCount=8` cấp thêm 8 CPUs». | Nó thay heuristics JVM, không thay cgroup hay task affinity. | Căn chỉnh với CPU ngân sách thực. |
| «`ParallelGCThreads` là số threads luôn chạy». | Ergonomic/workload giới hạn workers thực sự mỗi pause. | Đọc GC task/phase logs. |
| «`ConcGCThreads` không ảnh hưởng app». | Chúng chạy đồng thời, cạnh tranh CPU với mutators. | Đo CPU saturation/throughput. |
| «CPU quota = số NUMA nodes». | Quota giới hạn CPU time, nodes mô tả topology memory. | Đọc `cpu.max` và `numactl --hardware` riêng. |
| «`-Xmx` bằng memory limit là an toàn». | JVM còn native memory, thread stacks, metaspace, buffers. | Chừa headroom và theo dõi cgroup/peak RSS. |
| «`-Xmx` là toàn bộ trang vật lý đã cấp». | Heap có reservation/commit và page faults khác nhau. | Đọc heap/OS mapping; phân biệt reserved vs committed. |
| «`AlwaysPreTouch` luôn tăng tốc». | Có thể tăng startup/RSS sớm, thay page placement. | Đo memory budget và startup. |
| «`--cpunodebind` tự pin heap RAM». | CPU pinning và memory binding là hai cơ chế khác. | Chọn memory policy có chủ đích. |
| «`--membind=0` luôn an toàn». | Khi node 0 hết RAM, allocation có thể fail dù node khác còn. | Kiểm tra node capacity và fallback policy. |
| «Một node đã đủ NUMA optimization». | Không có khác biệt local/remote giữa nhiều nodes để tận dụng. | Không ép UseNUMA nếu topology không phù hợp. |
| «`numastat -p` chỉ phản ánh Java heap». | Số liệu gồm nhiều memory mappings. | Kết hợp JVM logs/memory mappings và workload. |
| «G1 là real-time collector». | Pause goal không phải cam kết hard deadline. | Đo pause percentiles và SLA ứng dụng. |
| «Thấy throughput thay đổi một lần là do NUMA». | Nhiều biến nhiễu: JIT, GC, CPU throttling, scheduler. | Lặp test, giữ biến độc lập, dùng thống kê. |

## 17. Bài tập tự kiểm tra

### Bài 1 — Khác nhau giữa CPU quota và CPU affinity

Container có `cpu.max` biểu thị quota tương đương 2 CPUs, nhưng cpuset cho phép CPU 0–7. Điều này có nghĩa app có 8 CPU time trọn vẹn không?

**Đáp án:** Không. App có thể được scheduler chạy trên các CPUs trong cpuset, nhưng tổng CPU time vẫn bị giới hạn theo quota. `Runtime.availableProcessors()` cũng có thể áp dụng ergonomics/container heuristics; kiểm tra runtime thực tế.

### Bài 2 — `ActiveProcessorCount` và NUMA

Khi đặt `-XX:ActiveProcessorCount=4` trên server 2 NUMA nodes, điều gì thay đổi?

**Đáp án:** HotSpot xem như có 4 active processors cho nhiều heuristics, trong đó có GC threads; điều đó **không** chuyển RAM sang node khác hay tạo 4 cores thật. CPU/NUMA placement vẫn do OS/cgroup/flags khác quyết định.

### Bài 3 — Parallel vs concurrent GC threads

Một ứng dụng có p99 latency tăng vì GC pauses dài. Có thể chắc chắn cứ tăng `ConcGCThreads` thì giảm pause không?

**Đáp án:** Không. `ConcGCThreads` điều chỉnh concurrent marking; phải xem G1 logs để biết nguyên nhân. Pha STW cần phân tích `ParallelGCThreads`, heap/regions, evacuation và object profile; tăng concurrent workers còn có thể tranh CPU.

### Bài 4 — Chỉ một NUMA node

Process chỉ được phép sử dụng CPU và RAM trên node 0. `UseNUMA` có chắc cải thiện throughput so với off?

**Đáp án:** Không. Không có multi-node locality cần tối ưu; JVM có thể vô hiệu hóa cơ chế NUMA, còn policy một node đã bảo đảm không đi remote sang node khác trong giới hạn đó.

### Bài 5 — Thread migration

Thread A tạo nhiều objects khi chạy ở node 0, sau đó scheduler chuyển nó sang node 1. Truy cập các objects cũ có tự chuyển thành local ngay không?

**Đáp án:** Không. Object/page có thể vẫn nằm ở node 0; truy cập từ node 1 có thể remote cho tới khi có page migration/evacuation hoặc thay đổi placement phù hợp. Không giả định JVM tự đưa ngay mọi object sang node mới.

### Bài 6 — Dung lượng container

Một JVM có container memory limit 4 GiB và `-Xmx4g`, ứng dụng tạo nhiều threads/direct buffers. Nó có chắc không bị OOM kill khi heap chưa đầy?

**Đáp án:** Không. Native memory và các cấu phần ngoài heap cũng tốn ngân sách container; tổng memory vượt limit có thể bị OS kill.

### Bài 7 — `numactl`

Sự khác nhau giữa `--cpunodebind=0` và `--membind=0` là gì?

**Đáp án:** Lệnh đầu giới hạn CPU chạy process vào CPUs thuộc node 0; lệnh sau giới hạn memory allocation vào node 0. Hai cơ chế có thể áp dụng riêng; dùng một không tự tạo chính sách tương đương cơ chế kia.

### Bài 8 — UseNUMA không tăng tốc

Bạn bật `-XX:+UseNUMA` nhưng throughput không thay đổi. Kết luận cơ chế không hiệu quả ở mọi máy được không?

**Đáp án:** Không. Xem số NUMA nodes thực sự khả dụng, OS memory policy, CPU affinity, heap/workload size, thread migration, logs rồi A/B test. Một kết quả ở một topology không suy ra mọi topology.

### Bài 9 — Giá trị `ParallelGCThreads` từ flag

`PrintFlagsFinal` báo `ParallelGCThreads=8`, vậy mỗi GC pause dùng chính xác 8 workers?

**Đáp án:** Không chắc. Đây là số cấu hình/tối đa; G1 có thể dùng ít workers hơn do heap size, phase và lượng work thực tế. Cần log GC task/phase để xem.

### Bài 10 — `-Xms` và `AlwaysPreTouch`

Bạn đặt `-Xms` bằng `-Xmx` và bật `AlwaysPreTouch`. Tại sao startup chậm hoặc memory RSS tăng sớm?

**Đáp án:** JVM chạm nhiều trang đã commit tại startup, khiến hệ điều hành phải backing chúng sớm. Đó là trade-off của startup/memory footprint với khả năng ổn định memory backing; NUMA placement cũng cần đo lại.

### Bài 11 — Chọn thước đo

Bạn muốn chứng minh NUMA-aware G1 mang lại lợi ích cho service. Chỉ nhìn GC pause count có đủ không?

**Đáp án:** Không. Cần throughput, p95/p99 latency, CPU utilization/throttling, GC pause duration, memory locality, node balance, allocation rate và thống kê nhiều lần chạy với cùng điều kiện.

### Bài 12 — NUMA và old objects

G1 tạo object mới trên node 0 rồi object sống lâu/promote sang old. Có chắc object vẫn ở node 0 mãi không?

**Đáp án:** Không. JEP 345 tập trung locality cho young allocation/GC; old/humongous regions có chiến lược phân bổ khác. OS và GC có thể thay đổi placement; không hứa locality bất biến suốt vòng đời object.

## 18. Checklist áp dụng trong môi trường thật

1. **Xác nhận runtime:** JDK vendor/build và GC đang dùng; `-XX:+UseG1GC` nếu cần so sánh rõ.
2. **Ghi lại topology:** CPU/node/socket/memory capacities; `numactl --hardware`, `lscpu`.
3. **Ghi lại giới hạn:** Cgroup CPU quota, cpuset CPUs/mems, memory limit; các thay đổi do orchestrator áp dụng.
4. **Đọc JVM view:** `availableProcessors()`, `PrintFlagsFinal`, `-Xlog:os+container=trace`.
5. **Xác minh G1 settings:** `ParallelGCThreads`, `ConcGCThreads`, `UseNUMA`, heap size/pause goal.
6. **Phân biệt node/region/thread:** NUMA node không phải G1 region; worker count không phải số CPU thật.
7. **Kiểm tra GC logs:** STW phases, concurrent marking, CPU costs, Full GC/evacuation failure.
8. **Kiểm tra memory placement:** OS memory policy, `numastat`, mappings, node imbalance; không dùng duy nhất một log line làm bằng chứng.
9. **Giữ headroom:** Heap không chiếm hết container limit, kể cả khi nhiều threads/native buffers.
10. **Thử A/B công bằng:** Off/on NUMA và CPU/placement từng biến một, warm-up và nhiều lần lặp.
11. **Quan sát SLA:** Throughput cùng p95/p99 application latency; G1 pause goal không phải hard real-time.
12. **Triển khai an toàn:** Version-control JVM flags, có rollback, benchmark trên đúng JDK/OS/CPU topology.

## 19. Tài liệu tham khảo hiện hành

1. [JEP 345 — NUMA-Aware Memory Allocation for G1](https://openjdk.org/jeps/345): thiết kế chính thức đưa NUMA-aware young allocation vào G1 từ JDK 14; đọc để hiểu nguyên lý, không coi mọi chi tiết thực thi là bất biến.
2. [Oracle Java SE 25 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): regions, young/old, parallel/concurrent phases và ergonomic defaults.
3. [Oracle Java SE 25 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): cân bằng throughput/pause, `ConcGCThreads`, refinement workers, AlwaysPreTouch và diagnostic logs.
4. [Oracle Java SE 25 — `java` tool reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+UseNUMA`, `-XX:ActiveProcessorCount`, `-XX:+UseContainerSupport`, `-XX:ParallelGCThreads`, `-XX:ConcGCThreads`, `-Xlog`.
5. [Oracle Java SE 25 — `Runtime.availableProcessors()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): số processors JVM công bố, không phải số node NUMA.
6. [Oracle Java SE 25 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): thông tin collector dùng trong ví dụ `G1ResourceProbe`.
7. [Oracle Java SE 25 — Unified Logging hướng dẫn `java`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): log tags, levels và cú pháp `-Xlog`.
8. [Linux kernel — NUMA Memory Policy](https://www.kernel.org/doc/html/latest/admin-guide/mm/numa_memory_policy.html): memory policies, cpusets và mối quan hệ giữa policy và giới hạn OS.
9. [Linux `numactl(8)` manual](https://man7.org/linux/man-pages/man8/numactl.8.html): `--cpunodebind`, `--membind`, `--localalloc`, `--interleave` và kiểm tra NUMA topology.
10. [Oracle JDK 14 Release Notes — JEP 345](https://www.oracle.com/java/technologies/javase/14-relnote-issues.html): mốc ban đầu và cơ chế young/old/humongous được mô tả.
11. [JDK HotSpot source — Linux NUMA policy/validation](https://github.com/openjdk/jdk/blob/master/src/hotspot/os/linux/os_linux.cpp): kiểm tra điều kiện NUMA thực tế như single-node hoặc mismatch CPU/memory nodes trong những bản triển khai mới; source thay đổi theo release, hãy đối chiếu tag JDK đang chạy.

**Ghi nhớ:** G1 cố gắng tận dụng **CPU parallelism** cho GC và **NUMA memory locality** cho cấp phát young objects. CPU quotas, affinity và allowed memory nodes có thể hạn chế cả hai. `-XX:ActiveProcessorCount` điều chỉnh **heuristics**, `-XX:+UseNUMA` cung cấp **khả năng NUMA-aware** khi nền tảng cho phép, còn `numactl`/cgroups định hình ràng buộc thực từ OS. Hãy đo trên workload thực, không hứa một flag luôn làm ứng dụng nhanh hơn.