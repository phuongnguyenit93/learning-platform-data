# Ảnh hưởng của giới hạn bộ nhớ và CPU trong container đến GC độ trễ thấp (Java 15+)

## 1. Vấn đề thực tế

Một dịch vụ Java có thể chạy với **ZGC** hoặc **Shenandoah** để giảm thời gian **stop-the-world (STW)**, nhưng vẫn gặp **p99/p99.9 latency cao** sau khi triển khai vào Docker hoặc Kubernetes. Nguyên nhân có thể không nằm ở thời gian dừng GC: CPU của container bị **throttling**, chu kỳ thu gom chạy đồng thời không được cấp đủ CPU, bộ nhớ bị giới hạn quá thấp, hệ điều hành phải cấp/thu hồi trang bộ nhớ, hoặc cả tiến trình bị **OOM kill**.

Bài học thuộc nhóm **GC độ trễ thấp** của module **Java 15**. Hai cột mốc liên quan là **JEP 377** (ZGC trở thành tính năng production trong Java 15) và **JEP 379** (Shenandoah trở thành tính năng production). Những API và cơ chế điều chỉnh **heap**, **container awareness**, **GC logging** và **CPU quota** vẫn được áp dụng trên JDK hiện đại. Tuy nhiên, cách triển khai GC đã tiến hóa: trên **JDK 24+**, **ZGC chỉ còn biến thể generational**; không dùng các cờ chọn non-generational ZGC cũ trong hướng dẫn triển khai mới.

**Câu hỏi mà bài này giải đáp:**

1. Giới hạn RAM của container khác `-Xmx` như thế nào và vì sao container bị kill dù heap chưa đầy?
2. CPU quota và throttling ảnh hưởng đến **concurrent GC** và độ trễ đầu cuối ra sao?
3. Chọn và cấu hình G1, ZGC, Shenandoah thế nào trong môi trường tài nguyên bị giới hạn?
4. Đo những gì để phân biệt **GC pause**, **allocation stall**, **CPU throttling** và **OOMKilled**?
5. Làm thế nào kiểm chứng các thông số JVM bằng một chương trình Java 17+ chạy được?

Các ví dụ có số liệu như `512Mi` hoặc `2 CPU` đều là **cấu hình minh họa**; không phải giá trị phù hợp mặc định cho mọi ứng dụng. Luôn đo trên tải và container thật.

## 2. Ba lớp giới hạn tài nguyên không được nhầm lẫn

### 2.1. Giới hạn container và giới hạn Java heap

Trên Linux, Docker/Kubernetes thường dùng **cgroups** để giới hạn CPU và bộ nhớ. Đây là tài nguyên của **tiến trình/container**, không chỉ phần heap quản lý bởi Java GC.

| Lớp kiểm soát | Ví dụ cấu hình | Bao gồm hoặc ảnh hưởng đến gì? |
| --- | --- | --- |
| **Container memory limit** | Docker `--memory=512m`; Kubernetes `limits.memory: 512Mi` | Giới hạn tài nguyên bộ nhớ của cgroup; có thể khiến kernel kill tiến trình khi vượt giới hạn. Tính toán phụ thuộc bộ nhớ tiến trình và accounting của cgroup, không chỉ Java heap. |
| **Java maximum heap** | `-Xmx192m` hoặc cấu hình theo `-XX:MaxRAMPercentage` | Trần heap chứa các object Java; **không** phải trần tổng RSS/native memory của JVM. |
| **Java initial/minimum heap** | `-Xms64m` | Kích thước heap ban đầu/tối thiểu mà GC sử dụng; có ảnh hưởng đến khởi động, footprint và quá trình mở rộng heap tùy collector. |
| **Container CPU limit** | Docker `--cpus=2`; Kubernetes `limits.cpu: "2"` | CPU time có thể dùng trên một khoảng thời gian; khi hết quota, kernel có thể **throttle** các thread của ứng dụng và GC. |
| **CPU request** | Kubernetes `requests.cpu: "1"` | Chủ yếu phục vụ scheduling và phân chia nguồn lực trong môi trường tranh chấp; **không** đồng nghĩa một CPU limit cứng như `limits.cpu`. |
| **JVM active processor count** | `-XX:ActiveProcessorCount=2` | Số CPU mà HotSpot dùng cho các phép tính ergonomics như kích thước GC thread pools và `ForkJoinPool`. Nó **không tự tạo hoặc áp đặt giới hạn CPU ở kernel**. |

**Phân biệt hai loại sự cố bộ nhớ:**

- **`java.lang.OutOfMemoryError: Java heap space`:** Java không cấp phát được object trong heap theo giới hạn/điều kiện JVM. Đây là **lỗi JVM báo được**; không nhất thiết làm container bị kernel kill ngay.
- **Container bị OOMKilled:** kernel/container runtime chấm dứt tiến trình vì áp lực vượt giới hạn bộ nhớ của cgroup. Khi đó có thể **không có Java stack trace** và Java không có cơ hội ném `OutOfMemoryError` hoặc chạy shutdown hook.

Không kết luận “không thấy `OutOfMemoryError` nên không phải vấn đề bộ nhớ”. Kiểm tra **trạng thái/exit reason của container**, cgroup và biểu đồ RSS/working set song song với heap.

### 2.2. Tổng bộ nhớ thực dùng không chỉ có heap

Một JVM còn cần:

- **Metaspace** cho metadata của class;
- **Code cache** của JIT compiler;
- **Thread stacks** (số thread lớn có thể làm footprint tăng);
- **DirectByteBuffer**, NIO và native allocations;
- JNI/native library allocations, GC/JVM internal structures, symbol tables và các bộ đệm;
- vùng memory-mapped, page cache hoặc accounting khác tùy cách kernel/cgroup ghi nhận.

Vì vậy, với `memory limit = 512Mi` và `-Xmx=512m`, container **rất dễ không còn ngân sách** cho các thành phần khác. Không nên đặt `-Xmx` bằng đúng toàn bộ memory limit rồi coi thế là an toàn.

Một ngân sách khởi đầu minh họa:

~~~text
Container memory limit:        768 MiB
Java maximum heap (-Xmx):      384 MiB
Khoảng còn lại trên giấy:      384 MiB
Dùng cho: metaspace, native/direct memory,
          thread stacks, JIT/code cache,
          GC structures, page cache và biên an toàn
~~~

Con số `384 MiB` còn lại **không phải một pool được bảo đảm sẵn** hay giới hạn tự động cho từng thành phần. Ứng dụng có nhiều direct buffers, hàng trăm thread hoặc tải native nặng có thể cần tỷ lệ heap thấp hơn. Ngược lại, workload thuần heap với ít native memory có thể tận dụng tỷ lệ heap cao hơn sau khi đo.

**Quan trọng đối với GC độ trễ thấp:** ZGC có công việc diễn ra **đồng thời** với ứng dụng và cần **headroom heap** để ứng dụng tiếp tục cấp phát trong lúc GC đang thu gom. Một heap vừa đủ chứa live set nhưng thiếu chỗ cho tốc độ allocation đang diễn ra có thể dẫn đến **allocation stalls**, tăng latency hoặc tiến gần lỗi thiếu bộ nhớ. Nên kiểm tra **live set, allocation rate, peak demand và CPU GC** cùng lúc.

## 3. CPU quota có thể phá hỏng p99 dù GC pause ngắn

### 3.1. CPU throttling không phải GC stop-the-world

Ví dụ container có `cpu limit = 1` nhưng workload đồng thời cần:

- các thread xử lý request;
- JIT compiler threads;
- thread của GC thực hiện marking/relocation đồng thời;
- các thread hệ thống, logging và networking.

Nếu tổng nhu cầu CPU vượt **CPU quota**, Linux có thể **throttle** tất cả những thread này trong một khoảng thời gian. Ngay cả khi GC ghi một pause STW rất ngắn, một request có thể phải chờ CPU trước/sau pause và bị kéo dài tới hàng chục/hàng trăm millisecond.

**Phải đo hai nhóm latency khác nhau:**

| Nhóm đo | Ví dụ metric | Được dùng để trả lời gì? |
| --- | --- | --- |
| **GC pause** | Thời gian pause trong `-Xlog:gc*`, JFR GC pause events | JVM đã dừng các application threads bao lâu vì pha GC? |
| **Application latency** | p50, p95, **p99**, p99.9 HTTP/RPC/job completion | Người dùng thực sự chờ bao lâu? |
| **CPU throttling** | cgroup `cpu.stat` (`nr_throttled`, `throttled_usec`) hoặc metric container | Tiến trình bị quota chặn CPU thường xuyên và trong bao lâu? |
| **GC concurrency / allocation stalls** | GC logs/JFR, concurrent cycle duration, allocation stall events | GC có thu gom đủ nhanh trong khi ứng dụng tiếp tục cấp phát không? |
| **Memory pressure** | Heap used/committed, RSS, cgroup `memory.current`, OOM events | Có thiếu heap headroom hay container memory headroom không? |

Một `p99` cao không đồng nghĩa GC pause p99 cao. Nó còn có thể bắt nguồn từ CPU throttling, lock contention, thread pool starvation, I/O, scheduler, network hoặc ứng dụng đang ở vùng safepoint khác.

### 3.2. Vì sao GC concurrent vẫn cần CPU?

GC low latency không “miễn phí CPU”. Ví dụ ZGC và Shenandoah thực hiện nhiều việc **concurrent**, tức thread thu gom cạnh tranh CPU với thread xử lý request. Khi CPU quota quá chặt:

1. GC chạy chậm hơn vì thiếu thời gian CPU.
2. Ứng dụng vẫn tạo object và tăng lượng rác.
3. Khoảng trống heap có thể giảm trước khi GC thu hồi đủ.
4. Có thể xuất hiện **allocation stall**, throughput giảm, hoặc áp lực thiếu heap.
5. Các request tăng tail latency dù tổng số/độ dài STW pauses có thể vẫn nhỏ.

**Không tăng `ConcGCThreads` vô điều kiện** khi CPU container đang bị quota chặn: thêm concurrent GC threads có thể lấy CPU từ ứng dụng mà không làm tăng CPU quota của cgroup. Trước tiên đo CPU thực, throttling, heap headroom và tốc độ cấp phát. Các GC hiện đại tự chọn nhiều tham số ergonomics; chỉ override khi profiling chỉ ra nhu cầu.

### 3.3. CPU quota và ActiveProcessorCount không phải một

~~~bash
java -XX:ActiveProcessorCount=2 -version
~~~

Cờ trên **báo cho JVM** rằng nó nên coi có hai CPU để tính toán ergonomics, nhưng **không** giới hạn ứng dụng vào chính xác hai CPU ở cấp hệ điều hành. Chỉ container/cgroup/cpuset/scheduler mới kiểm soát quota/affinity thực.

Trên Linux với container awareness, HotSpot nhận diện các giới hạn CPU/memory phù hợp từ cgroups để chọn heap và số CPU hiệu dụng. `-XX:+UseContainerSupport` thường **được bật mặc định**; đừng dùng `-XX:-UseContainerSupport` như một “tối ưu” nếu ứng dụng phụ thuộc giới hạn container.

Nếu một workload cần số CPU cho JVM được chọn riêng với cách CPU quota được tính, có thể cấu hình `-XX:ActiveProcessorCount=N`; nhưng phải xác minh thread count và performance, không mặc định số này chính là giới hạn kernel.

## 4. Chọn GC khi CPU/memory bị giới hạn

Ba collector hữu ích trong bối cảnh này có **cân bằng khác nhau**, và đều phải được kiểm chứng trên **JDK/vendor/build thật**.

| GC | Chọn bằng | Điểm mạnh | Điểm cần đánh giá trong container |
| --- | --- | --- | --- |
| **G1** | `-XX:+UseG1GC` (thường là lựa chọn mặc định của server HotSpot) | Cân bằng throughput và pause time; theo dõi mục tiêu pause dựa trên heuristics. | Pause STW không bị loại bỏ; heap nhỏ/CPU ít có thể khiến mục tiêu khó đạt. |
| **ZGC** | `-XX:+UseZGC` | Ưu tiên **độ trễ pause rất thấp** nhờ GC chủ yếu concurrent. | Cần heap headroom và CPU cho concurrent cycle; container CPU quota có thể gây allocation stalls và p99 cao. |
| **Shenandoah** | `-XX:+UseShenandoahGC` nếu JDK build hỗ trợ | Concurrent marking/evacuation, hướng tới giảm pause. | Khả dụng tùy phân phối JDK; cần đo native/heap footprint, concurrent CPU và hiệu quả thực tế. |

**Mốc phiên bản cần nhớ:**

- Java 15: ZGC (**JEP 377**) và Shenandoah (**JEP 379**) chính thức sẵn sàng production trong các cấu hình phù hợp.
- JDK 24+: ZGC chỉ còn phiên bản **generational**; cờ chọn giữa generational/non-generational ZGC đời trước đã bị loại bỏ. Chỉ dùng `-XX:+UseZGC` với các JDK hiện hành; không đưa cấu hình lỗi thời vào manifest mới.
- G1 vẫn là lựa chọn baseline rất đáng kiểm tra, thay vì mặc định cho rằng collector có chữ “low latency” sẽ luôn nhanh hơn trong mọi giới hạn CPU/RAM.
- Một số bản phân phối/JDK build không đóng gói Shenandoah. Nếu `-XX:+UseShenandoahGC` không khả dụng thì đó là **đặc tính runtime**, không tự suy ra lỗi ứng dụng.

`-XX:MaxGCPauseMillis=...` là **mục tiêu mềm** (đặc biệt hữu ích với G1), **không phải SLA tuyệt đối** hay cam kết p99 request latency. Đặt giá trị rất thấp không tự tạo thêm CPU hoặc RAM. Khi CPU limit nhỏ, điều chỉnh mục tiêu pause quá tham vọng còn có thể làm tăng GC frequency và giảm throughput.

### Chọn theo tình huống

- **Rất ít CPU / heap nhỏ / throughput là ưu tiên:** đo G1 (và collector mặc định) trước; đừng mặc định ZGC sẽ giúp latency đầu-cuối tốt hơn.
- **Heap tương đối lớn, độ trễ nhạy cảm, CPU đủ cho GC concurrent:** thử ZGC với headroom hợp lý, đánh giá p99 request và allocation stalls thay vì chỉ đọc GC pause.
- **Workload tương tự nhưng JDK có Shenandoah:** benchmark Shenandoah với cùng cấu hình tải, heap, CPU quota và memory limit.
- **Container OOMKilled:** điều chỉnh **tổng ngân sách bộ nhớ** trước khi đổi GC. Collector không thể làm các native allocations vượt cgroup limit biến mất.
- **CPU throttling nghiêm trọng:** tăng CPU quota hoặc điều chỉnh chiến lược phân phối CPU/request/worker pool có thể hữu ích hơn việc ép GC pause target thấp hơn.

## 5. Các tùy chọn JVM còn áp dụng và cách dùng đúng

### 5.1. Giới hạn heap

~~~bash
java -Xms64m -Xmx384m -XX:+UseZGC -jar app.jar
~~~

Ví dụ `-Xmx384m` đặt trần heap Java; `-Xms64m` cho phép bắt đầu với heap nhỏ hơn. Đây là **ví dụ minh họa**, không phải kích thước được khuyến nghị cho mọi app.

Nếu **không chỉ định `-Xmx`**, có thể sử dụng:

~~~bash
java -XX:MaxRAMPercentage=50 -XX:+UseZGC -jar app.jar
~~~

Cờ này cho phép HotSpot tính heap tối đa theo tỷ lệ phần trăm của memory mà JVM xác định là có thể sử dụng (có xét container limits trên nền tảng có container support). Tuy nhiên, giá trị thực còn chịu các ergonomic rules và cấu hình khác. **Nếu đã đặt `-Xmx` tường minh, hãy coi `-Xmx` là giới hạn heap bạn chủ động chọn**, không cộng gộp hai cách tính để đoán kết quả.

Ví dụ: container `768Mi` và `MaxRAMPercentage=50` có thể gợi ý heap tối đa cỡ **384MiB**, nhưng phải **xác nhận tại runtime** vì các yếu tố thiết lập/ergonomics khác. Không đặt tỷ lệ 100% rồi coi cgroup limit đã được dành hoàn toàn cho Java heap.

### 5.2. SoftMaxHeapSize không phải hard memory limit

Với ZGC:

~~~bash
java -Xms128m -Xmx512m -XX:SoftMaxHeapSize=384m -XX:+UseZGC -jar app.jar
~~~

`-XX:SoftMaxHeapSize` là **mục tiêu mềm** ZGC cố gắng duy trì, nhưng vẫn **được phép vượt đến `-Xmx`** khi cần để ứng dụng không phải chờ GC thu hồi bộ nhớ. Nó **không thay thế** `-Xmx`, không giới hạn native memory và không ngăn OOMKilled. Đừng dùng soft max để chứng minh container sẽ không vượt memory limit.

### 5.3. GC logging và container logging

~~~bash
java -Xms64m -Xmx384m -XX:+UseZGC -Xlog:gc* -jar app.jar
~~~

`-Xlog:gc*` ghi các sự kiện GC và pha liên quan để phân tích. Trong môi trường Linux container có hỗ trợ thông tin cgroups, thêm:

~~~bash
java -Xlog:os+container=debug -XshowSettings:system -version
~~~

Cách này hữu ích để xác minh **JVM thực sự nhận biết CPU/memory limit nào**. `-XshowSettings:system` chủ yếu hữu ích trên Linux; trên Windows/macOS không nên kỳ vọng báo cgroup Linux.

Có thể xem các option hiệu lực:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Đầu ra có nhiều dòng, nên lọc/kiểm tra cụ thể các flag như `MaxHeapSize`, `ActiveProcessorCount`, `UseContainerSupport` và collector đã bật. Đừng dùng giá trị mặc định trên máy phát triển để suy đoán cấu hình đang áp dụng trong một Pod production.

**Lưu ý quan sát:** không phải mọi tag GC log đều phản ánh “thời gian request bị chờ”. Dùng latency histogram của dịch vụ, dấu thời gian GC/safepoint và CPU throttling để khớp các spike theo thời gian.

## 6. Minh họa Kubernetes: requests khác limits

Đây là **một phần manifest của container**, không phải file Pod/Deployment hoàn chỉnh. Nó chỉ minh họa các trường `resources` và `env` trong định nghĩa container:

~~~yaml
containers:
  - name: java-service
    image: your-registry/java-service:tested
    resources:
      requests:
        cpu: "1"
        memory: "512Mi"
      limits:
        cpu: "2"
        memory: "768Mi"
    env:
      - name: JAVA_TOOL_OPTIONS
        value: "-Xms128m -Xmx384m -XX:+UseZGC -Xlog:gc*"
~~~

**Giải thích:**

- `requests.cpu: "1"` giúp Kubernetes scheduler cân nhắc tài nguyên và ảnh hưởng ưu tiên/phân chia CPU trong môi trường tranh chấp; nó **không chặn** container ở đúng một CPU.
- `limits.cpu: "2"` áp đặt **trần CPU** tương ứng, có thể dẫn tới throttling nếu ứng dụng và GC cùng vượt quota.
- `requests.memory: "512Mi"` dùng cho việc đặt Pod và các cơ chế quản lý tài nguyên thích hợp; **không** đồng nghĩa Java có heap 512MiB.
- `limits.memory: "768Mi"` là trần memory cgroup; khi vượt và áp lực xuất hiện, tiến trình có thể bị **OOM kill**.
- `-Xmx384m` dành tối đa 384MiB cho heap, để lại khoảng trống trên giấy cho metaspace, direct buffers, code cache, stacks và các chi phí khác. **Không có bảo đảm** chi phí đó luôn nằm dưới phần còn lại.
- `JAVA_TOOL_OPTIONS` là cách truyền option JVM qua môi trường; phải kiểm tra runtime/image không có thêm tùy chọn xung đột từ entrypoint hoặc các biến môi trường khác.

**Không áp dụng thẳng bản mẫu lên production** trước khi tính toán số thread, direct memory, native libraries, live set và peak RSS của ứng dụng. Nếu CPU throttling làm p99 tăng, thay đổi `limits.cpu` hoặc chính sách limit có thể cần được đánh giá cùng yêu cầu cô lập tài nguyên, thay vì coi limit 2 CPU luôn là tốt nhất.

### Một kiểm thử Docker minh họa

Trên máy có Docker, bash/Linux shell và thư mục chứa `ContainerGcProbe.java` từ mục 7:

~~~bash
docker run --rm --cpus=2 --memory=512m \
  -v "$PWD:/work" -w /work eclipse-temurin:25-jdk \
  sh -c 'javac --release 17 ContainerGcProbe.java && java -Xms64m -Xmx192m -XX:ActiveProcessorCount=2 -XX:+UseZGC -Xlog:gc=info -Xlog:os+container=debug ContainerGcProbe'
~~~

Đoạn này **chỉ là công thức triển khai để người học chạy trong môi trường Linux Docker**; việc kiểm thử trong phiên soạn bài được thực hiện trên JVM cục bộ, **không giả vờ đã đo cgroup/container thực**. Ví dụ đặt cả `--cpus=2` và `ActiveProcessorCount=2` nhằm nhận kết quả có tính lặp lại; nó **không độc lập chứng minh tính năng autodetect CPU limit**.

Muốn kiểm chứng tự động phát hiện cgroup, thử **một lượt khác không đặt `-XX:ActiveProcessorCount`**, sau đó xem `-XshowSettings:system`, `-Xlog:os+container=debug` và `Runtime.availableProcessors()`, so sánh với container limit thực tế.

## 7. Ví dụ Java 17+ chạy độc lập để kiểm tra JVM ergonomics

Chương trình `ContainerGcProbe` kiểm tra **số CPU hiệu dụng**, **heap maximum**, sự tồn tại GC MXBeans và một vòng cấp phát giữ một số object trong memory. Nó cố ý **không in số millisecond GC pause tưởng tượng**. Thời gian GC thực phải đọc từ GC log/JFR và đo p99 request ở workload thật.

Tạo file **`ContainerGcProbe.java`**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;

public class ContainerGcProbe {
    private static final long MIB = 1024L * 1024L;
    private static volatile long checksum;
    private static int passed;

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        passed++;
        System.out.println(name + "=PASS");
    }

    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        long maxHeap = runtime.maxMemory();
        int cpus = runtime.availableProcessors();

        check("activeProcessorOverride", cpus == 2);
        check("heapLimitApplied", maxHeap >= 64L * MIB && maxHeap <= 192L * MIB);

        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();
        check("gcBeansPresent", !collectors.isEmpty());

        Deque<byte[]> retained = new ArrayDeque<>();
        for (int i = 0; i < 128; i++) {
            byte[] block = new byte[512 * 1024];
            block[0] = (byte) i;
            retained.addLast(block);
            if (retained.size() > 16) retained.removeFirst();
            checksum += block[0] & 0xff;
        }

        check("retainedBlocks", retained.size() == 16);
        check("checksum", checksum == 8128L);
        System.out.println("ALL_CHECKS_PASS=" + passed);
    }
}
~~~

Biên dịch bằng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ContainerGcProbe.java
~~~

Chạy với G1:

~~~bash
java -Xms64m -Xmx192m -XX:ActiveProcessorCount=2 -XX:+UseG1GC ContainerGcProbe
~~~

Chạy với ZGC:

~~~bash
java -Xms64m -Xmx192m -XX:ActiveProcessorCount=2 -XX:+UseZGC ContainerGcProbe
~~~

Nếu bản JDK có Shenandoah:

~~~bash
java -Xms64m -Xmx192m -XX:ActiveProcessorCount=2 -XX:+UseShenandoahGC ContainerGcProbe
~~~

**Stdout chính xác trên JDK 24 được kiểm thử:** cả G1, ZGC và Shenandoah đều tạo cùng kết quả sau:

~~~text
activeProcessorOverride=PASS
heapLimitApplied=PASS
gcBeansPresent=PASS
retainedBlocks=PASS
checksum=PASS
ALL_CHECKS_PASS=5
~~~

Các kiểm tra có ý nghĩa:

1. `activeProcessorOverride`: `Runtime.availableProcessors() == 2` vì launcher được cấp `-XX:ActiveProcessorCount=2`. Đây là minh chứng cờ JVM hoạt động, **không phải** một phép đo quota cgroup Linux.
2. `heapLimitApplied`: `Runtime.maxMemory()` nằm trong khoảng kiểm tra khi JVM được cấp `-Xmx192m`. Số byte hiệu lực có thể khác giữa collector/JDK do cách căn chỉnh/ergonomics, nên code không so bằng số byte tuyệt đối.
3. `gcBeansPresent`: JVM cung cấp GC management beans. Tên bean và cách một collector thống kê count/time **không nhất thiết giống nhau giữa G1, ZGC và Shenandoah**; không dùng bean count đơn lẻ để kết luận độ trễ GC.
4. `retainedBlocks`: chỉ giữ lại 16 khối byte gần nhất, giúp tạo allocation workload mà không duy trì toàn bộ dữ liệu đã cấp phát.
5. `checksum`: kiểm tra chương trình thực sự đi qua 128 vòng, giữ một kết quả tích lũy ổn định (`8128` là tổng `0 + 1 + ... + 127`).

**Đừng biến chương trình này thành benchmark p99:** nó phân bổ một lượng bộ nhớ nhỏ, không mô phỏng request rate, I/O, dữ liệu sống của dịch vụ hay các pha tải lớn. Một lần `PASS` chỉ chứng minh **cờ cơ bản và mã chạy được**, không chứng minh GC nào có p99 tốt nhất.

Ví dụ đặt tham số cố định nên nếu chạy **không có `-XX:ActiveProcessorCount=2`**, kiểm tra `activeProcessorOverride` có thể fail; điều đó là chủ đích để chỉ rõ tác dụng của tham số. Tương tự, đổi `-Xmx` mà không sửa ngưỡng assert có thể làm `heapLimitApplied` fail.

## 8. Kiểm tra container thật bằng cgroups, logs và công cụ JVM

### 8.1. Linux cgroups v2

Trên một Linux host/container có cgroup v2 được mount ở vị trí thông thường, các file chẩn đoán điển hình là:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
~~~

Ý nghĩa:

- `cpu.max`: quota CPU và thời gian chu kỳ; giá trị như `max 100000` biểu thị **không có quota cứng** theo file đó.
- `cpu.stat`: có các chỉ số như `nr_throttled` và `throttled_usec` để quan sát throttling khi controller tương ứng được bật.
- `memory.max`: trần memory của cgroup; `max` nghĩa là không có giới hạn do cấp này áp đặt.
- `memory.current`: lượng memory cgroup đang hạch toán, không đồng nhất với `Runtime.maxMemory()`.
- `memory.events`: các sự kiện memory high/max/oom/oom_kill phục vụ chẩn đoán.

**Các đường dẫn có thể khác** nếu cgroup mount hoặc namespace được triển khai khác; các file trên dành cho **cgroups v2**, không áp dụng nguyên xi cho cgroups v1 hay Windows containers. Nếu runtime không cung cấp quyền đọc các file, dùng telemetry của nền tảng triển khai thay vì tự suy đoán.

### 8.2. Ghi nhận đầy đủ để tìm nguyên nhân p99

Với một sự cố latency, nên cùng lúc xem:

- Histogram **end-to-end p95/p99/p99.9** theo endpoint và phiên bản triển khai.
- `-Xlog:gc*` hoặc JFR để đo pause duration, concurrent cycle và **allocation stalls** khi collector có thông tin này.
- `-Xlog:safepoint` nếu cần tách những safepoint khác với các pha GC.
- CPU usage, **CPU throttling rate/time**, runnable threads và số vCPU JVM nhận biết.
- Heap used/committed/max, allocation rate, live set sau GC, direct/native memory và RSS/container `memory.current`.
- Container restarts, trạng thái **OOMKilled**, `memory.events`, exit reason và dữ liệu thu thập trước khi tiến trình chết.

Có thể bật **Native Memory Tracking** khi cần khảo sát phần native:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Sau đó, nếu môi trường cho phép attach công cụ, chạy:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

`<pid>` là **PID thực** của tiến trình; đây là placeholder trong lệnh giải thích, không phải một ví dụ hoàn chỉnh có thể copy chạy ngay. Native Memory Tracking có overhead và phạm vi riêng, không thay thế hoàn toàn OS RSS/cgroup metrics và không khẳng định mọi native allocation đều được tính. Với container có giới hạn chặt, cân nhắc overhead của việc bật telemetry.

### 8.3. Một ma trận thí nghiệm so sánh GC

Khi benchmarking, giữ **cùng phiên bản ứng dụng, dữ liệu, tỉ lệ request, profile CPU/RAM và network**; thay từng yếu tố một:

| Kịch bản | Giới hạn CPU | Limit memory | GC/heap | Điều cần so |
| --- | --- | --- | --- | --- |
| Baseline | 2 vCPU | 768Mi | G1, `-Xmx384m` | p99, GC pause, CPU throttling, RSS |
| Thử ZGC | 2 vCPU | 768Mi | ZGC, `-Xmx384m` | p99, allocation stall, GC concurrent CPU |
| Thử Shenandoah | 2 vCPU | 768Mi | Shenandoah nếu có, cùng heap | p99, GC cycles, CPU/RSS |
| Kiểm thử CPU chặt | 1 vCPU | 768Mi | cùng GC và heap | thay đổi throttling, throughput, p99 |
| Kiểm thử heap chặt | 2 vCPU | 512Mi | điều chỉnh heap cho native headroom | pause/alloc stall/OOM, RSS, live set |

**Không chạy các thử nghiệm phá OOM trên production.** Dùng staging/benchmark riêng; tăng tải có giới hạn, thu telemetry và có giới hạn an toàn. Nếu máy không có Shenandoah, ghi nhận **unsupported/skipped** thay vì coi nó đã qua benchmark.

## 9. Tình huống lỗi và cách phân biệt

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| **p99 cao nhưng GC pause ngắn** | CPU throttling, queueing, I/O, lock contention, application thread starvation | Đối chiếu throttle metrics với application latency, kiểm tra thread pools và CPU request/limit. |
| **ZGC allocation stalls tăng** | Heap thiếu headroom so với live set/allocation rate, hoặc GC không có đủ CPU concurrent | Kiểm tra allocation rate, concurrent cycle, CPU quota; tăng heap hoặc CPU hợp lý trước khi ép GC thread count. |
| **Pod OOMKilled nhưng không có Java OOME** | Tổng memory cgroup (heap + native/direct/stacks/...) vượt limit | Xem container exit reason và `memory.events`/RSS; hạ heap/nội dung native hoặc tăng container limit có kiểm soát. |
| **`OutOfMemoryError: Java heap space`** | Heap giới hạn không đủ cho live set, leak hoặc allocation spike | Heap dump/profiling trong môi trường phù hợp; xem `-Xmx`, retention và leak; không chỉ tăng memory limit cgroup. |
| **GC chạy thường xuyên với heap nhỏ** | Live set gần max heap hoặc allocation rate cao | Đo heap occupancy sau GC, giảm allocations/retention, điều chỉnh heap theo ngân sách container. |
| **Startup chậm/đụng memory limit ngay** | `-Xms` gần `-Xmx`, pre-touch hoặc native allocations sớm | Đánh giá `-Xms` và `-XX:+AlwaysPreTouch`; không áp dụng tối ưu pre-touch máy chủ lớn một cách mù quáng trong Pod nhỏ. |
| **JVM nhìn thấy quá nhiều CPU so với container** | Version/runtime/container detection hoặc cấu hình bị tắt, giới hạn cgroup khác dự kiến | Xem `-XshowSettings:system`, `-Xlog:os+container=debug`, `Runtime.availableProcessors()` và cgroup files. |
| **Shenandoah flag không được hỗ trợ** | JDK build/provider chưa có collector | Kiểm tra bản phân phối/JDK; không tự dựa vào Shenandoah như điều kiện bắt buộc khi xây image. |
| **Heap dưới soft max nhưng memory cgroup vẫn cao** | Native memory, direct buffers, code cache, page cache hoặc RSS khác với heap committed | So sánh heap metrics, NMT và container memory; `SoftMaxHeapSize` không phải trần container. |
| **G1 `MaxGCPauseMillis` không đạt** | Mục tiêu chỉ là hint và workload/CPU/heap không đủ đáp ứng | Kiểm tra GC pauses, live set, heap size, CPU throttle, throughput; điều chỉnh theo benchmark. |

### Những phát biểu không nên đưa vào tài liệu vận hành

- “GC pause nhỏ thì p99 request chắc chắn nhỏ” — **sai**.
- “Container memory limit bằng Java `-Xmx`” — **sai**.
- “`MaxRAMPercentage=100` luôn tốt hơn dùng heap thấp hơn” — **sai**, không còn native headroom.
- “`SoftMaxHeapSize` bảo đảm không vượt memory limit” — **sai**, chỉ là mục tiêu mềm của ZGC.
- “Tăng `ConcGCThreads` luôn giúp ZGC khi CPU quota thấp” — **sai**, concurrent GC cạnh tranh CPU với ứng dụng.
- “CPU throttling sinh ra `OutOfMemoryError`” — **không phải cơ chế trực tiếp**; throttling làm chậm tiến trình, còn OOM là câu chuyện bộ nhớ.
- “`-XX:ActiveProcessorCount` giới hạn CPU vật lý” — **sai**, chỉ điều chỉnh CPU count mà JVM dùng trong ergonomics.
- “Dùng ZGC đồng nghĩa không bao giờ STW” — **sai**, GC low-pause không phải hard real-time guarantee.
- “Ứng dụng Java 15 hiện đại phải thêm cờ chọn non-generational ZGC” — **lỗi thời trên JDK 24+**.

## 10. Checklist triển khai có thể áp dụng ngay

1. **Phân loại SLO:** latency p99 cần bao nhiêu ms, throughput tối thiểu, memory/RSS budget và CPU budget là bao nhiêu?
2. **Chọn baseline GC:** đo G1 trước, thử ZGC/Shenandoah khi cần giảm GC pauses và JDK build hỗ trợ.
3. **Tính heap headroom:** `-Xmx` đủ cho live set + allocation khi GC chạy, nhưng **thấp hơn** container memory limit để dành ngân sách native.
4. **Kiểm tra cgroups thật:** xác nhận memory limit/quota, CPU throttling, số CPU mà JVM nhận diện trước khi điều chỉnh GC.
5. **Không lạm dụng CPU flags:** ưu tiên ergonomics mặc định; override `ActiveProcessorCount`/`ConcGCThreads` khi có đo đạc rõ.
6. **Xác minh JVM flags:** chạy `-XX:+PrintFlagsFinal` và `-XshowSettings:system` tại chính image/container triển khai.
7. **Theo dõi cả GC và hệ thống:** GC logs/JFR, RSS, native memory, cgroup events, p99 application.
8. **Dùng benchmark kiểm soát:** cùng workload ở 2 CPU và 1 CPU, rồi cùng heap ở hai memory limits; chạy nhiều lượt để tránh kết luận từ một mẫu nhiễu.
9. **Phân biệt lỗi:** Java heap OOME cần phân tích heap; OOMKilled cần phân tích giới hạn tổng memory; CPU throttling cần phân tích quota/contended CPU.
10. **Triển khai an toàn:** thay đổi một biến một lần, rollback được, không thử cấu hình sát OOM trong production, quan sát p99 và error rate sau khi đổi.

## 11. Nguồn chuẩn còn được áp dụng

- [Java SE 26 — HotSpot Garbage Collection Tuning Guide, Available Collectors](https://docs.oracle.com/en/java/javase/26/gctuning/available-collectors.html): chọn G1/ZGC theo latency/throughput và kích thước heap/CPU.
- [Java SE 25 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): GC pause goals, concurrent work và trade-off throughput.
- [Java SE 24 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): ZGC generational, heap headroom, `SoftMaxHeapSize` và concurrent collection.
- [Java SE 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): `-Xmx`, `-Xms`, `MaxRAMPercentage`, `ActiveProcessorCount`, `UseContainerSupport`, `-Xlog`.
- [JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector (Production)](https://openjdk.org/jeps/377): ZGC production từ Java 15.
- [JEP 379 — Shenandoah: A Low-Pause-Time Garbage Collector (Production)](https://openjdk.org/jeps/379): Shenandoah production từ Java 15.
- [JEP 490 — ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490): thay đổi hiện hành của ZGC ở JDK 24.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU requests/limits, throttling, memory limits và OOM kill.
- [Java SE 26 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): quan sát collector theo JVM management API.

**Kết luận:** GC độ trễ thấp không thể vượt qua giới hạn CPU/RAM của container. Cần cấp **heap và native headroom**, đủ **CPU cho GC concurrent**, đọc đúng số liệu **cgroups, RSS, GC pauses, allocation stalls và p99 ứng dụng**. Chọn GC theo **kết quả đo trên cấu hình container thực**, không chỉ theo tên collector hay mục tiêu pause được khai báo.