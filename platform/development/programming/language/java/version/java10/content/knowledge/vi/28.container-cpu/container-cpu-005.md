# Runtime.availableProcessors() và cấu hình tự động của thư viện khi Java chạy trong container

**Chủ đề:** CPU trong container — Java 10 và các JDK hiện đại.

Một container có thể chạy trên máy chủ có rất nhiều logical CPU nhưng được cấp **CPU quota**, **CPU affinity/cpuset** và các điều kiện scheduling riêng. Vì vậy, khi chương trình Java gọi `Runtime.getRuntime().availableProcessors()`, câu hỏi thực chất là: **JVM hiện thấy bao nhiêu processor có thể sử dụng theo điều kiện của runtime?** Câu trả lời không nhất thiết bằng tổng logical CPU của host, không phải số core vật lý, và cũng không phải một phép đo tức thời về phần trăm CPU đang bận.

Từ **JDK 10**, HotSpot cải thiện **container awareness trên Linux**: JVM có thể xem giới hạn tài nguyên container để xác định số CPU khả dụng và tự cấu hình một số thành phần JVM. Cờ `-XX:+UseContainerSupport` mặc định được bật trên Linux. API `Runtime.availableProcessors()` đã tồn tại từ trước; **điểm liên quan Java 10 là cách HotSpot xác định tài nguyên trong container, không phải một phương thức Java mới được thêm vào ở Java 10**.

Con số CPU JVM báo cáo có thể ảnh hưởng **`ForkJoinPool`, work-stealing pool, parallel streams, `CompletableFuture` và một số quyết định ergonomics của GC/JIT**. Nhưng **không có quy tắc “mọi thư viện Java tự động dùng đúng N threads”**: mỗi thư viện/framework có mặc định và giới hạn riêng; pool được tạo tường minh có thể không đổi khi CPU count đổi.

Bài này chỉ dùng **kiến thức hiện còn áp dụng**: giải thích Linux cgroups v1/v2 và giới hạn CPU, cách HotSpot hiện đại dùng quota/affinity, vì sao **CPU shares không còn mặc định được dùng để tính số processor từ JDK 19**, cách kiểm tra `-XX:ActiveProcessorCount`, cấu hình thread pool, xử lý CPU phân số, các bẫy Kubernetes và kiểm thử thực tế. **Năm chương trình Java độc lập** đã được biên dịch bằng `javac --release 10`, chạy trên **OpenJDK HotSpot 24.0.2 (Windows)** với các giá trị CPU override 1/2/4. Các lệnh kiểm tra **cgroup trong Linux container** được hướng dẫn riêng theo tài liệu Oracle; không mạo nhận đã chạy Docker/Linux trên môi trường kiểm thử Windows này.

## 1. `availableProcessors()` thật sự trả về gì?

API chuẩn:

~~~java
int processors = Runtime.getRuntime().availableProcessors();
~~~

Đây là **đoạn Java bên trong một phương thức**, không phải chương trình đầy đủ.

Theo Oracle Javadoc, `availableProcessors()` trả **số processor khả dụng đối với Java Virtual Machine** và **không bao giờ nhỏ hơn 1**. Giá trị có thể thay đổi trong thời gian một JVM chạy. Ứng dụng nhạy với số processor nên có chiến lược đánh giá và điều chỉnh tài nguyên khi điều kiện vận hành thay đổi.

### Những điều không thể suy ra chỉ từ số nguyên này

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| JVM thấy 2 processors | **Đúng nếu method trả 2** | Đây là con số JVM báo cáo trong lần gọi |
| Host vật lý chỉ có 2 core | **Không suy ra được** | Host có thể có nhiều CPU, nhưng container bị giới hạn |
| Container có đúng 2 core vật lý dành riêng | **Không suy ra được** | CPU quota là giới hạn **thời lượng CPU**, không nhất thiết pin vào hai core |
| CPU đang sử dụng 200% | **Không suy ra được** | CPU count không phải CPU utilization |
| Có thể chạy tối đa 2 Java threads | **Sai** | JVM có thể có nhiều thread; scheduler chia thời gian CPU |
| Mọi thread pool đều có size 2 | **Sai** | Kích thước pool tùy constructor, framework, configuration và thời điểm tạo |
| Tất cả tác vụ CPU-bound sẽ chạy nhanh gấp đôi khi trả 2 thay vì 1 | **Sai** | Hiệu năng còn phụ thuộc quota/throttling, GC, contention, workload |
| Giá trị nhất định không đổi đến khi JVM kết thúc | **Không bảo đảm bởi API** | Javadoc cho biết giá trị **có thể thay đổi** trong một lần chạy |

**Logical CPU / processor trong ngữ cảnh JVM** khác **core vật lý**, **CPU quota phân số** và **CPU usage thực tế**. Hãy dùng con số này như một **tín hiệu cấu hình** chứ không như một quota scheduler hay service-level agreement.

### API liên quan

`ManagementFactory.getOperatingSystemMXBean().getAvailableProcessors()` trong `java.lang.management` cũng báo số processor khả dụng theo hợp đồng Java Management API. Nó tương đương về mục đích với `Runtime.availableProcessors()`; đây **không phải phép đọc CPU utilization độc lập**. Trong JDK kiểm thử khi ép `-XX:ActiveProcessorCount`, hai API trả cùng một số.

## 2. JVM làm thế nào biết CPU của container?

Trong Linux, container thường dùng **cgroups** và **CPU affinity** để hạn chế, phân bổ tài nguyên. Các nguồn thông tin quan trọng là:

- **CPU quota/period:** giới hạn tổng CPU time được dùng trong một khoảng thời gian lập lịch. Với cgroups v2, thường được mô tả ở `cpu.max`.
- **Cpuset / CPU affinity:** giới hạn tập logical CPU mà process/thread có thể chạy. Với cgroups v2, file như `cpuset.cpus.effective` thể hiện tập CPU hiệu lực.
- **CPU shares/weight:** điều chỉnh **tỷ trọng cạnh tranh** khi CPU bận; không tương đương một hard cap. Cgroups v1 dùng `cpu.shares`, v2 dùng `cpu.weight`.
- **Giới hạn từ parent cgroup / scheduler / OS:** một container con có thể chịu hạn chế từ cấp trên hoặc cpuset/affinity khác.
- **JVM flags:** `-XX:ActiveProcessorCount=N` có thể ghi đè số processor HotSpot dùng, không phải chính sách thực thi quota của Linux.

### Cgroups v1 và v2

| Hạng mục | Cgroups v1 | Cgroups v2 | Ý nghĩa |
| --- | --- | --- | --- |
| Quota | `cpu.cfs_quota_us` và `cpu.cfs_period_us` | `cpu.max` | Lượng CPU time tối đa theo period, nếu áp giới hạn |
| Cpuset | `cpuset.cpus` (và trạng thái effective tùy môi trường) | `cpuset.cpus.effective` | Những logical CPU được phép sử dụng |
| Trọng số | `cpu.shares` | `cpu.weight` | Tỷ trọng cạnh tranh CPU; **không phải hard quota** |
| Bối cảnh HotSpot | JDK 10 có container awareness cho cấu hình Linux tương ứng | Hỗ trợ cgroups v2 được bổ sung từ **JDK 15**, có backport vào các update release khác | Dùng JDK đủ mới cho loại cgroups đang triển khai |

**Chú ý Special Note:** Không dạy rằng Java 10 ban đầu tự nhận diện mọi hệ thống cgroups v2 như JVM hiện đại. Cgroups v2 được hỗ trợ trong OpenJDK từ **JDK 15** (với backport vào những dòng update được bảo trì). Với container hiện tại, hãy kiểm tra **JDK build và cgroups version thực tế**, không chỉ nhìn số feature Java trên nhãn.

### Tại sao shares không được coi là “CPU count” mặc định nữa?

Trước kia, một số JDK suy diễn số processor từ `cpu.shares`, dẫn tới việc JVM tưởng có ít CPU hơn thực tế trong những cấu hình chỉ dùng **relative CPU shares** mà không có hard quota. Từ **JDK 19**, HotSpot **mặc định không dùng CPU shares** để quyết định active processor count (JDK-8281181). Một cờ tương thích cũ đã tồn tại ở các bản chuyển tiếp, nhưng **không phải cách cấu hình được khuyến nghị hiện nay**, và đã bị loại bỏ khỏi các JDK mới hơn.

**Kết luận vận hành:** Kubernetes `requests.cpu` hoặc CPU weight/shares **không nên được hiểu là “JVM chắc chắn thấy bấy nhiêu processors”**. Trong nhiều môi trường, **`limits.cpu`** tạo hard quota, còn CPU request ảnh hưởng scheduling/resource allocation. Nhưng chi tiết phụ thuộc container runtime và nền tảng: không phải mọi nền tảng đều áp hard quota bằng cùng cơ chế.

## 3. CPU quota phân số: 1.5 CPU không có nghĩa `availableProcessors()==1.5`

`Runtime.availableProcessors()` trả **`int`**, còn quota CPU có thể là số phân số. Ví dụ cgroups v2:

~~~text
cpu.max:
150000 100000

quota / period = 150000 / 100000 = 1.5 CPU-time
~~~

Đó là khoảng **1,5 CPU worth of runtime** trong mỗi period, không có nghĩa JVM được sở hữu cố định một lõi rưỡi vật lý. Linux có thể chạy thread trên nhiều logical CPU nhưng áp tổng quota/throttling theo period.

Trong HotSpot Linux hiện đại, thuật toán xác định **active processor count** xét dữ liệu cgroup quota và CPU affinity/cpuset; phần quota phân số có thể được **làm tròn lên** khi đổi thành số processor nguyên. Vì thế, với cấu hình phù hợp và không bị ràng buộc khác, quota 1,5 CPU có thể làm JVM báo **2 processors**, chứ không trả 1,5 hay mặc nhiên xuống 1.

| Cấu hình minh họa | CPU quota theo thời gian | Gợi ý CPU nguyên khi làm tròn lên | Điều cần lưu ý |
| --- | --- | --- | --- |
| Quota 0,5 CPU | 0,5 | 1 | Một thread CPU-bound vẫn có thể bị throttling |
| Quota 1,0 CPU | 1,0 | 1 | Không phải bảo đảm độc quyền một CPU vật lý |
| Quota 1,5 CPU | 1,5 | 2 | Hai worker CPU-bound có thể tranh quota tổng |
| Quota 2,5 CPU | 2,5 | 3 | Không suy ra throughput đúng 3 CPU đầy đủ |
| Không có hard quota nhưng affinity chỉ cho 2 CPU | Không xác định bằng quota | Có thể là 2 | Affinity/cpuset vẫn giới hạn tài nguyên |
| Quota 3,0 CPU nhưng affinity chỉ cho 2 CPU | 3,0 | Có thể là 2 | Điều kiện hạn chế chặt hơn chi phối |

**Đây là ví dụ mô hình**, không phải bảng cam kết kết quả cho mọi JDK/vendor. HotSpot còn xét OS affinity, parent cgroup, các flag và dữ liệu thực. Đặc biệt, **`-XX:ActiveProcessorCount` luôn là trường hợp override tường minh** nếu được thiết lập hợp lệ trong HotSpot. Hãy đo giá trị trong container thực tế.

### Vì sao làm tròn lên có thể gây ngạc nhiên?

Nếu Java nhìn thấy `2` từ quota 1,5 CPU rồi tạo hai worker CPU-bound, hai worker có thể chạy song song một lúc nhưng **tổng thời lượng CPU** vẫn bị giới hạn theo quota. Khi tiêu hết ngân sách CPU trong period, cgroup có thể bị **throttled**. Điều đó làm tăng thời gian phản hồi dù có hai worker.

Vì vậy, **CPU count là hint để sizing**, không phải một công thức tiên đoán throughput. Với tải thực tế, xem thêm CPU throttling metrics, hàng đợi, request latency, GC và utilization.

## 4. Cờ HotSpot hiện hành: `UseContainerSupport` và `ActiveProcessorCount`

### Container awareness tự động — Linux HotSpot

~~~bash
java -XshowSettings:system -version
~~~

Theo tài liệu `java` hiện hành, tùy chọn `-XshowSettings:system` trên **Linux** cho phép hiển thị thông tin host/container và tiếp tục chạy. Tùy JVM/build/cgroups, có thể thấy provider, CPU quota, CPU set và các thông tin liên quan. Không hard-code một khối stdout cho mọi distro hoặc release.

Với logging container chi tiết trên HotSpot có hỗ trợ:

~~~bash
java -Xlog:os+container=trace -version
~~~

Dùng trong chẩn đoán, vì trace có thể dài và khác theo implementation. Hãy kiểm tra `java -Xlog:help` nếu một log tag không được nhận diện ở phiên bản đang dùng.

**Mặc định**, HotSpot Linux có `UseContainerSupport` bật. Chỉ khi thực sự cần cô lập nguyên nhân trong bài test mới cân nhắc cờ tắt:

~~~bash
java -XX:-UseContainerSupport -cp . CpuRuntimeProbe
~~~

**Không khuyến nghị tắt container awareness để “tăng CPU”.** Tắt nó có thể làm JVM nhìn tài nguyên host/affinity và cấu hình quá lớn so với quota container, dẫn đến oversubscription hoặc memory/CPU pressure.

**Lưu ý nền tảng:** `-XX:-UseContainerSupport` là tùy chọn **Linux-only** theo Oracle. Trên môi trường OpenJDK HotSpot 24.0.2 **Windows** kiểm thử bài, cờ này **không được nhận diện**. Đừng nhét nó vào một command chung chạy trên mọi OS. Tính năng container-awareness dựa trên Linux cgroups không đồng nghĩa với việc JVM trên host Windows/macOS đọc cgroups của một container Linux đang chạy ở nơi khác.

### Override số CPU mà HotSpot dùng để tự cấu hình

~~~bash
java -XX:ActiveProcessorCount=2 -cp . CpuRuntimeProbe
~~~

Cờ **`-XX:ActiveProcessorCount=N`** làm HotSpot dùng số CPU `N` trong các quyết định active processor, ảnh hưởng `Runtime.availableProcessors()` và các quyết định JVM/thread pool liên quan. **N phải là số dương có ý nghĩa.**

Oracle ghi rõ override này **vẫn được tôn trọng khi `UseContainerSupport` bị tắt** trên nền tảng hỗ trợ tính năng đó. Nhưng cờ này **không thay đổi CPU quota của kernel**, không tạo thêm core vật lý và không tự bảo đảm scheduler cấp đủ CPU time cho số worker đó.

**Nên dùng khi nào?** Khi đã xác định JVM nhận sai số CPU theo chính sách triển khai, muốn kiểm soát parallelism trong container có CPU shares không có hard quota, hoặc cần phép thử A/B có CPU-count ổn định. Trước khi đặt cứng, hãy kiểm tra lý do số CPU nhận sai, mô hình quota thực tế và tác động lên GC/JIT/pool.

## 5. Chương trình chạy được 1 — Đọc CPU và thread pool mặc định

Tạo file **`CpuRuntimeProbe.java`**:

~~~java
import java.lang.management.ManagementFactory;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;

public class CpuRuntimeProbe {
    public static void main(String[] args) {
        int cpus = Runtime.getRuntime().availableProcessors();
        int viaMxBean = ManagementFactory.getOperatingSystemMXBean()
                .getAvailableProcessors();
        ForkJoinPool privatePool = new ForkJoinPool();
        ExecutorService workStealing = Executors.newWorkStealingPool();

        try {
            int steal = workStealing instanceof ForkJoinPool
                    ? ((ForkJoinPool) workStealing).getParallelism()
                    : -1;

            System.out.println("runtime-cpus=" + cpus);
            System.out.println("mxbean-cpus=" + viaMxBean);
            System.out.println("same-cpu-report=" + (cpus == viaMxBean));
            System.out.println("private-forkjoin=" +
                    privatePool.getParallelism());
            System.out.println("work-stealing=" + steal);
            System.out.println("common-forkjoin=" +
                    ForkJoinPool.getCommonPoolParallelism());
        } finally {
            privatePool.shutdown();
            workStealing.shutdown();
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 10 CpuRuntimeProbe.java
~~~

Chạy ba tiến trình JVM **riêng biệt** với override khác nhau:

~~~bash
java -XX:ActiveProcessorCount=1 CpuRuntimeProbe
java -XX:ActiveProcessorCount=2 CpuRuntimeProbe
java -XX:ActiveProcessorCount=4 CpuRuntimeProbe
~~~

**Stdout đã kiểm chứng trên HotSpot 24.0.2** với `ActiveProcessorCount=1`:

~~~text
runtime-cpus=1
mxbean-cpus=1
same-cpu-report=true
private-forkjoin=1
work-stealing=1
common-forkjoin=1
~~~

Với `ActiveProcessorCount=2`:

~~~text
runtime-cpus=2
mxbean-cpus=2
same-cpu-report=true
private-forkjoin=2
work-stealing=2
common-forkjoin=1
~~~

Với `ActiveProcessorCount=4`:

~~~text
runtime-cpus=4
mxbean-cpus=4
same-cpu-report=true
private-forkjoin=4
work-stealing=4
common-forkjoin=3
~~~

### Vì sao `common-forkjoin` không luôn bằng `runtime-cpus`?

`new ForkJoinPool()` mặc định chọn target parallelism theo `Runtime.availableProcessors()`, trong khi **common pool** có chính sách tạo pool riêng. Ở HotSpot/OpenJDK kiểm thử khi không có override khác, `ForkJoinPool.getCommonPoolParallelism()` là **1** với CPU=1/2 và **3** với CPU=4.

**Không áp một công thức hard-code vào mọi framework**. Common pool có thể chịu cấu hình hệ thống hoặc hành vi triển khai cụ thể. Số parallelism **không bằng** số thread OS thực sự chạy đồng thời tại một thời điểm, và cũng không nhất thiết là số task sẽ hoàn thành trong một giây.

`Executors.newWorkStealingPool()` được Javadoc mô tả là chọn **target parallelism theo available processors**. Trên OpenJDK hiện tại, nó trả một `ForkJoinPool` nên ví dụ dùng `instanceof` để lấy parallelism. Nếu implementation khác, ví dụ in `-1` thay vì giả định ép kiểu luôn an toàn.

**Điểm cần thử lại trong app thật:** một process có `ActiveProcessorCount=4` có thể khiến một thư viện lấy con số `4` ở startup để tạo bốn worker. Nhưng nếu cấu hình thư viện đặt `pool.size=20`, con số explicit của thư viện có thể ghi đè heuristic mặc định.

## 6. Cấu hình tự động của Java và thư viện: những loại pool khác nhau

### A. `ForkJoinPool`

`ForkJoinPool` là executor dùng work-stealing, phù hợp với nhiều tác vụ có thể chia nhỏ. Constructor không truyền parallelism:

~~~java
ForkJoinPool pool = new ForkJoinPool();
try {
    // Gửi tác vụ vào pool khi cần.
} finally {
    pool.shutdown();
}
~~~

Đây là **đoạn code trong một method**, cần import `java.util.concurrent.ForkJoinPool`. Theo Javadoc, target parallelism mặc định của constructor này là `Runtime.availableProcessors()`.

### B. Common pool và parallel streams

`ForkJoinPool.commonPool()` là pool dùng chung cho nhiều công việc fork/join. **Parallel streams** thường sử dụng pool này trong các đường thực thi thông thường, nhưng chi tiết có thể thay đổi theo ngữ cảnh thread gọi stream và implementation.

~~~java
long count = java.util.stream.IntStream
        .range(0, 1_000)
        .parallel()
        .filter(n -> n % 2 == 0)
        .count();
~~~

Đoạn trên nằm trong method. Kết quả `count` là `500` bất kể JVM dùng bao nhiêu worker. Số CPU ảnh hưởng **chiến lược thực thi**, không được làm đổi kết quả logic của một phép tính thuần túy và đúng với parallel stream.

**Sai lầm:** thấy `availableProcessors()==2` rồi khẳng định `parallel()` luôn tạo đúng hai thread. Parallelism của common pool và luồng caller có thể khiến cách thực thi khác; số lượng worker hoặc scheduling không phải hợp đồng do `Stream.parallel()` cung cấp.

### C. `CompletableFuture.supplyAsync` mặc định

Nếu không truyền `Executor`, `CompletableFuture` thường dùng common pool; theo Javadoc, khi common pool **không hỗ trợ parallelism ít nhất 2**, implementation có thể dùng **một thread riêng cho mỗi async task**. Đây là một ngoại lệ rất đáng chú ý khi container/JVM báo CPU nhỏ.

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> "done");
String result = future.join();
~~~

Đây là **đoạn code trong method** với import `java.util.concurrent.CompletableFuture`. Kết quả logic là `done`, nhưng **loại thread chạy supplier** có thể khác giữa CPU=1 và CPU=4, như chương trình đầy đủ ở mục 9.

Nếu bạn cần giới hạn concurrency hoặc isolation của tác vụ async, **truyền `Executor` do ứng dụng quản lý** thay vì phụ thuộc hoàn toàn vào executor mặc định.

### D. `Executors.newFixedThreadPool`

~~~java
ExecutorService executor = Executors.newFixedThreadPool(6);
~~~

Đây là đoạn trong method, cần import `ExecutorService` và `Executors`. Pool này dùng **6** làm target kích thước cố định theo lời gọi explicit; nó **không tự đọc CPU để thay 6 thành `availableProcessors()`**. Ngay cả khi `Runtime.availableProcessors()==2`, `getCorePoolSize()==6` và `getMaximumPoolSize()==6` trong implementation `ThreadPoolExecutor` tiêu chuẩn.

Một pool có thể có nhiều thread hơn CPU, nhất là workload chờ I/O; điều đó **không tạo thêm CPU time**. Với tác vụ CPU-bound, overprovisioning thường tăng tranh chấp và context switching.

### E. GC/JIT và framework không phải tất cả dùng chung một công thức

HotSpot có quyết định **ergonomics** cho số luồng GC và compiler dựa một phần vào số processor, collector, heap, cấu hình và phiên bản JDK. Cờ `ActiveProcessorCount` có thể tác động những lựa chọn đó. **Không cam kết rằng mọi GC/JIT thread count luôn bằng chính `availableProcessors()`**.

Framework HTTP, event loop, message consumer, JDBC pool hay executor của ứng dụng thường có **cấu hình riêng**. Một số mặc định lấy `availableProcessors()` rồi nhân, trừ hoặc chặn min/max; một số dùng một hằng số; một số dựa vào số connection, latency I/O hoặc cấu hình YAML. **Phải đọc tài liệu phiên bản thư viện đang dùng** rồi kiểm tra cấu hình thực tế, không suy diễn từ tên thư viện.

## 7. Chương trình chạy được 2 — Sizing pool có giới hạn rõ ràng

Nếu workload CPU-bound được xử lý bằng thread pool chuyên trách, một chính sách khởi đầu có thể là lấy số CPU được JVM báo cáo, nhưng **giới hạn ngưỡng max** để tránh tạo pool quá lớn trên host mạnh:

~~~java
static int cpuWorkers(int cpus) {
    return Math.max(1, Math.min(8, cpus));
}
~~~

Đây là **đoạn method**, không phải quy tắc bắt buộc cho mọi ứng dụng. Việc dùng max=8 chỉ là **chính sách ví dụ**; ứng dụng production phải benchmark theo workload.

Với workload chờ I/O, có thể cần nhiều hơn CPU count, nhưng **không tồn tại công thức chung “I/O workers = 2 × CPUs”**. Chỉ để minh họa sự khác biệt giữa các heuristic, chương trình dưới đây tính một `ioHint` có chặn min/max. **Không tự áp `ioHint` vào production nếu chưa đo**.

Lưu **`CpuAwarePoolDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CpuAwarePoolDemo {
    static int cpuWorkers(int cpu) {
        return Math.max(1, Math.min(8, cpu));
    }

    static int ioHint(int cpu) {
        return (int) Math.min(16L, Math.max(2L, 2L * cpu));
    }

    public static void main(String[] args) throws Exception {
        int cpu = Runtime.getRuntime().availableProcessors();
        int workers = cpuWorkers(cpu);
        ExecutorService executor =
                Executors.newFixedThreadPool(workers);

        try {
            List<Future<Integer>> results = new ArrayList<>();
            for (int n = 1; n <= 8; n++) {
                final int value = n;
                results.add(executor.submit(() -> value * value));
            }

            int sum = 0;
            for (Future<Integer> future : results) {
                sum += future.get();
            }

            System.out.println("cpus=" + cpu);
            System.out.println("cpu-workers=" + workers);
            System.out.println("io-hint=" + ioHint(cpu));
            System.out.println("completed-tasks=" + results.size());
            System.out.println("sum-squares=" + sum);
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 10 CpuAwarePoolDemo.java
java -XX:ActiveProcessorCount=4 CpuAwarePoolDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
cpus=4
cpu-workers=4
io-hint=8
completed-tasks=8
sum-squares=204
~~~

**Giải thích:**

- JVM nhìn thấy `4` CPUs do cờ `ActiveProcessorCount=4`.
- Heuristic CPU-bound giới hạn giữa 1 và 8 nên tạo pool 4 workers.
- `ioHint=8` chỉ là ví dụ công thức ứng dụng, **không phải API Java tự quyết định số worker I/O**.
- Tám task tính bình phương từ 1 đến 8 có tổng `204`, độc lập với số worker và thứ tự scheduling.
- `Future.get()` đợi task hoàn thành để kết quả in ra xác định; `shutdown()` đóng pool.
- Một request server/độ trễ I/O thực tế cần tính throughput, backpressure, queue limits và tài nguyên bên ngoài trước khi chọn pool size.

**Lưu ý an toàn:** `Executors.newFixedThreadPool` dùng **unbounded queue** theo Javadoc. Nếu nguồn request có thể tăng vô hạn, điều này tạo nguy cơ tích hàng đợi và áp lực bộ nhớ dù worker count đã giới hạn. Với server cần backpressure, có thể dùng `ThreadPoolExecutor` với queue giới hạn và chính sách từ chối thích hợp.

## 8. Chương trình chạy được 3 — Pool explicit không tự thu nhỏ theo CPU

Lưu file **`ExplicitFixedPoolDemo.java`**:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadPoolExecutor;

public class ExplicitFixedPoolDemo {
    public static void main(String[] args) {
        int cpu = Runtime.getRuntime().availableProcessors();
        ThreadPoolExecutor executor =
                (ThreadPoolExecutor) Executors.newFixedThreadPool(6);

        try {
            System.out.println("available=" + cpu);
            System.out.println("fixed-core=" +
                    executor.getCorePoolSize());
            System.out.println("fixed-maximum=" +
                    executor.getMaximumPoolSize());
            System.out.println("hardcoded-differs=" +
                    (cpu != executor.getMaximumPoolSize()));
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 10 ExplicitFixedPoolDemo.java
java -XX:ActiveProcessorCount=2 ExplicitFixedPoolDemo
~~~

**Stdout đã kiểm chứng trên OpenJDK 24.0.2:**

~~~text
available=2
fixed-core=6
fixed-maximum=6
hardcoded-differs=true
~~~

**Ý nghĩa:** `newFixedThreadPool(6)` không tự chuyển thành pool 2 chỉ vì JVM báo có 2 CPUs. Những default cấu hình mà thư viện tính ở **thời điểm khởi tạo pool** không mặc nhiên thay đổi khi operator sửa Kubernetes CPU limit hoặc chỉnh biến môi trường.

Với pool dùng để xử lý công việc quan trọng, nên có **cấu hình rõ ràng, metrics và cơ chế resize** nếu chính sách vận hành cần đáp ứng thay đổi tài nguyên. Không được thay pool size tùy tiện trong lúc có task mà không xét lifecycle và queue.

## 9. Chương trình chạy được 4 — `CompletableFuture` và trường hợp CPU nhỏ

Một ngoại lệ nhiều người bỏ qua: khi common pool chỉ có parallelism 1, default executor của `CompletableFuture` **có thể dùng thread riêng** thay vì common-pool worker.

Lưu file **`AsyncDefaultsDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinWorkerThread;

public class AsyncDefaultsDemo {
    public static void main(String[] args) {
        int cpus = Runtime.getRuntime().availableProcessors();
        int common = ForkJoinPool.getCommonPoolParallelism();

        boolean onForkJoinWorker = CompletableFuture.supplyAsync(
                () -> Thread.currentThread()
                        instanceof ForkJoinWorkerThread)
                .join();

        System.out.println("cpus=" + cpus);
        System.out.println("common-parallelism=" + common);
        System.out.println("async-is-forkjoin-worker=" +
                onForkJoinWorker);
        System.out.println("async-fallback-when-small=" +
                (common <= 1 && !onForkJoinWorker));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 AsyncDefaultsDemo.java
java -XX:ActiveProcessorCount=1 AsyncDefaultsDemo
java -XX:ActiveProcessorCount=4 AsyncDefaultsDemo
~~~

**Stdout trên OpenJDK 24.0.2 khi CPU=1:**

~~~text
cpus=1
common-parallelism=1
async-is-forkjoin-worker=false
async-fallback-when-small=true
~~~

**Stdout khi CPU=4:**

~~~text
cpus=4
common-parallelism=3
async-is-forkjoin-worker=true
async-fallback-when-small=false
~~~

**Đừng suy ra rằng `CompletableFuture.supplyAsync` luôn có một fixed thread pool với size bằng available processors.** Runtime dùng common pool khi parallelism phù hợp, và có chính sách fallback khi quá nhỏ; Javadoc đã nêu điều này. Cấu hình của common pool, classloader/implementation và thời điểm initialize có thể ảnh hưởng kết quả.

Nếu ứng dụng có chính sách concurrency/backpressure cụ thể, dùng overload nhận `Executor`:

~~~java
ExecutorService custom = Executors.newFixedThreadPool(3);
try {
    CompletableFuture<String> task = CompletableFuture.supplyAsync(
            () -> "done", custom);
    String result = task.join();
} finally {
    custom.shutdown();
}
~~~

Đây là **đoạn code trong một method**, cần import `CompletableFuture`, `ExecutorService`, `Executors`. Nó không tự suy ra 3 từ CPU; `3` là policy do programmer đưa vào.

**Ghi chú Java hiện đại:** từ Java 21, virtual threads là API ổn định và scheduler của chúng cũng có quyết định parallelism dựa processor khả dụng, nhưng **số lượng virtual threads không bị giới hạn thành số CPU**. Không dùng tính năng này trong các chương trình `--release 10` của bài; nếu dự án Java 21+ dùng virtual threads, xem tài liệu riêng về carrier scheduler, pinning và backpressure.

## 10. Chương trình chạy được 5 — Mô hình CPU quota minh họa

Java standard library **không cung cấp một API portable để từ mọi OS đọc cgroup quota rồi tái tạo toàn bộ thuật toán HotSpot**. Bài có thể minh họa ý tưởng **làm tròn quota CPU** và **tôn trọng giới hạn affinity** bằng một hàm nhỏ, nhưng phải phân biệt **mô hình giải thích** với **implementation thực tế của JVM**.

Tệp **`QuotaModelDemo.java`**:

~~~java
public class QuotaModelDemo {
    static int exampleCpuHint(int affinity, long quota, long period) {
        if (affinity < 1 || period <= 0) {
            throw new IllegalArgumentException();
        }
        if (quota < 0) {
            return affinity;
        }
        long quotaCpus = Math.max(
                1L, (quota + period - 1) / period);
        return (int) Math.min((long) affinity, quotaCpus);
    }

    public static void main(String[] args) {
        System.out.println("quota-1.5-on-4=" +
                exampleCpuHint(4, 150000, 100000));
        System.out.println("quota-3-on-2=" +
                exampleCpuHint(2, 300000, 100000));
        System.out.println("quota-unlimited-on-4=" +
                exampleCpuHint(4, -1, 100000));
        System.out.println("quota-0.5-on-4=" +
                exampleCpuHint(4, 50000, 100000));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 QuotaModelDemo.java
java QuotaModelDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
quota-1.5-on-4=2
quota-3-on-2=2
quota-unlimited-on-4=4
quota-0.5-on-4=1
~~~

Chương trình chỉ minh họa **`ceil(quota / period)` rồi giới hạn bởi một số affinity truyền vào**. Nó **không** đọc cgroup thực, không biết parent cgroup, không quản lý CPU scheduling và **không được dùng thay thuật toán VM/container detection trong production**. Ở một môi trường thật, kernel và JVM còn có những ràng buộc khác. Đặc biệt, quota fractional không bảo đảm chương trình có thể tiêu thụ trọn vẹn từng processor mà kết quả nguyên gợi ý.

Nếu tính toán quota bằng số lớn ngoài miền ví dụ, phải kiểm tra overflow và tính hợp lệ; hàm này không phải parser cgroup hoàn chỉnh.

## 11. Thử nghiệm Linux Docker thật: để JVM tự phát hiện rồi đối chiếu

Bài thử trên Windows đã xác minh `-XX:ActiveProcessorCount` và auto-pool heuristics. Muốn **xác minh cgroup/container awareness**, cần chạy HotSpot **bên trong Linux container** với giới hạn tài nguyên thực, rồi đối chiếu `Runtime.availableProcessors()` và các thông số cgroup.

### Tạo image demo tối giản

Bước 1: tại thư mục có `CpuRuntimeProbe.java` từ mục 5, biên dịch:

~~~bash
javac --release 10 CpuRuntimeProbe.java
~~~

Bước 2: tạo file **`Dockerfile`** trong cùng thư mục:

~~~dockerfile
FROM eclipse-temurin:25-jre
WORKDIR /app
COPY CpuRuntimeProbe.class /app/CpuRuntimeProbe.class
ENTRYPOINT ["java", "-cp", "/app", "CpuRuntimeProbe"]
~~~

Bước 3: build image và chạy bằng Docker Engine chế độ Linux containers:

~~~bash
docker build -t cpu-probe .
docker run --rm --cpus=1.5 cpu-probe
~~~

**Không hard-code stdout** cho lần chạy container vì kết quả còn tùy JDK image, kernel, cpuset, parent cgroup và host. Với quota 1,5 CPU, một HotSpot Linux phù hợp thường có thể báo 2 processor do làm tròn quota, **nhưng phải đọc kết quả thật**.

### Tách container quota và JVM override

~~~bash
docker run --rm --cpus=1.5 --entrypoint java cpu-probe -XX:ActiveProcessorCount=1 -cp /app CpuRuntimeProbe
~~~

Lệnh thứ hai **vẫn giữ Docker quota 1,5 CPU**, nhưng yêu cầu HotSpot dùng **1 active processor** cho ergonomics. Nó **không đổi quota kernel từ 1,5 xuống 1,0 CPU**.

Chạy chẩn đoán Linux (ghi chú: `-XshowSettings:system` chỉ được tài liệu Oracle hỗ trợ trên Linux):

~~~bash
docker run --rm --cpus=1.5 --entrypoint java cpu-probe -XshowSettings:system -version
~~~

Nhìn thông tin container provider, CPU quota/period và cpuset nếu được hiển thị. Nếu cần chi tiết hơn:

~~~bash
docker run --rm --cpus=1.5 --entrypoint java cpu-probe -Xlog:os+container=trace -version
~~~

Lệnh log trace có thể rất nhiều và đầu ra khác nhau giữa VM; đây là **công cụ debug**, không phải benchmark thông thường.

**Tính tái lập:** JDK trong Dockerfile có thể khác JDK trên máy build nhưng bytecode được biên dịch với `--release 10` nên phù hợp mức API/bytecode Java 10; ví dụ chỉ dùng Java API có từ đó. Nếu cần chính sách reproducible build, pin image theo digest và giữ metadata artifact/JDK khi benchmark.

## 12. Với Kubernetes, `requests.cpu` và `limits.cpu` không cùng ý nghĩa

Một đoạn cấu hình resource của container:

~~~yaml
resources:
  requests:
    cpu: "500m"
  limits:
    cpu: "1500m"
~~~

Đây là **một fragment YAML nằm trong spec của container**, không phải manifest Deployment hoàn chỉnh.

- `requests.cpu: 500m` nghĩa là request **0,5 CPU** phục vụ scheduling/resource allocation. Trong cgroups, cơ chế weight/shares có thể phản ánh tài nguyên được yêu cầu, nhưng **không phải hard limit đồng nghĩa 0,5 processor**.
- `limits.cpu: 1500m` thường được thực thi dưới dạng **CPU bandwidth quota 1,5 CPU** trên Linux có cơ chế hạn mức cgroup. Container có thể bị throttling khi dùng hết CPU time.
- Với HotSpot hiện đại, JVM sẽ **không mặc định lấy CPU shares/weight làm CPU count** như một số phiên bản cũ. Nó có thể dựa vào quota và affinity/cpuset; kết quả từ 1,5 quota có thể làm tròn thành **2** active processors.
- Nếu **không** đặt CPU limit, chỉ có request/weight, JVM có thể thấy **nhiều CPU hơn request**, phụ thuộc affinity, cgroup thực và nền tảng. Điều đó không phải lỗi Java nếu request không phải hard cap.
- Một số môi trường CPU Manager có thể dùng cpuset cho các workload nhất định; phải kiểm tra CPU effective trong container, không phỏng đoán chỉ từ YAML.
- Đặt `-XX:ActiveProcessorCount` chỉ khi policy cần; **không** coi cờ này là thay thế Kubernetes resource limit.

**Thí dụ lỗi cấu hình:** một pod request 500m, không có CPU limit, chạy một framework nhân worker count theo 32 logical CPUs của node. JVM có thể tự nhìn thấy nhiều CPUs vì không có hard quota; pool của framework sinh quá nhiều worker cho throughput mong muốn, gây contention. Cách xử lý là xem chính sách resource, cấu hình framework/worker và đo thực tế — **không dùng lại cờ `UseContainerCpuShares` lỗi thời** từ các bài hướng dẫn cũ.

### Khi tài nguyên đổi sau khi JVM đã chạy

Oracle Javadoc nói `Runtime.availableProcessors()` **có thể thay đổi** trong một invocation. Nhưng nhiều thư viện tạo pool **một lần ở lúc startup** rồi giữ kích thước đó đến khi tái cấu hình/restart. Một thay đổi CPU limit không đảm bảo mọi pool và mọi subsystem JVM đều tự điều chỉnh tức thì.

Nếu hệ thống cần vertical autoscaling liên tục, thiết kế rõ **cơ chế quan sát lại processor count, cấu hình động của pool hoặc rolling restart**. Kiểm tra cả mức tương thích khi cgroups thay đổi và các metrics CPU throttling, pool queue và tail latency.

## 13. Cách điều tra nếu `availableProcessors()` không như mong đợi

### Bước 1 — Xác nhận JVM đang chạy ở đâu

~~~bash
java -version
~~~

Xem vendor, feature release và build. Container Linux có JVM riêng với host. Không lấy phiên bản `java` trên máy phát triển rồi áp cho JVM đang chạy trong pod.

### Bước 2 — Đọc con số từ chính JVM trong container

Chạy `CpuRuntimeProbe` bằng chính entrypoint/container cần điều tra. So sánh `Runtime.availableProcessors()` và `OperatingSystemMXBean.getAvailableProcessors()` (hai API có hợp đồng tương đương), đồng thời ghi số parallelism của các pool liên quan.

### Bước 3 — Kiểm tra cgroup và affinity

Dùng `-XshowSettings:system` trên Linux, `-Xlog:os+container=trace` khi cần, và dữ liệu cgroup do môi trường triển khai cung cấp. Với cgroups v2, xem `cpu.max`, `cpuset.cpus.effective` và các giới hạn từ parent cgroup; với cgroups v1, xem quota/period và cpuset tương ứng.

### Bước 4 — Kiểm tra flag và chính sách

- Có `-XX:ActiveProcessorCount=N` trong JVM arguments hoặc `JAVA_TOOL_OPTIONS` không?
- Có ai cố ý tắt `UseContainerSupport` trên **Linux** không?
- Image có JDK cũ thiếu hỗ trợ cgroups v2 không?
- Có loại CPU limit “shares/weight” nhưng không có hard quota không?
- CPU affinity hoặc cpuset thực tế là bao nhiêu?
- Đâu là cờ cấu hình thread pool riêng của thư viện, khác với JVM global CPU count?

### Bước 5 — Quan sát pool thực tế

`ForkJoinPool.getCommonPoolParallelism()`, `ThreadPoolExecutor.getCorePoolSize()/getMaximumPoolSize()` và metrics của framework cho thấy **size thật đang dùng**. Đừng chỉ nhìn availableProcessors và tưởng mọi pool đã khớp.

### Bước 6 — Benchmark đúng mục tiêu

Đo CPU-bound throughput, runnable tasks, queue time, context switches, cgroup throttling, GC pauses, CPU utilization và request latency. Nhiều workers **không luôn** tốt hơn; ít workers **không luôn** tốt hơn. Xem tải CPU/I/O và backpressure.

## 14. CPU count thay đổi các library defaults theo nhiều cách

| Thành phần | Quan hệ với `availableProcessors` | Bẫy cần nhớ |
| --- | --- | --- |
| `Runtime.availableProcessors()` | Trả số processors JVM thấy | Không phải CPU utilization hay physical cores |
| `OperatingSystemMXBean.getAvailableProcessors()` | Số processors khả dụng tương đương | Không phải phép đo quota độc lập |
| `new ForkJoinPool()` | Target parallelism mặc định theo CPUs | Không đồng nghĩa số thread đang thực chạy |
| `Executors.newWorkStealingPool()` | Target parallelism theo CPUs | Implementation có thể khác; không ép kiểu không kiểm tra |
| `ForkJoinPool.commonPool()` | Có policy riêng, thường liên quan CPUs | Có system property và quy tắc tối thiểu; không luôn bằng CPUs |
| `Stream.parallel()` | Thường tận dụng common FJP | Không hứa số worker cố định; workload quyết định lợi ích |
| `CompletableFuture.supplyAsync` | Thường common pool; fallback nếu parallelism quá nhỏ | Trong JVM thấy 1 CPU có thể tạo thread riêng cho mỗi async task |
| `Executors.newFixedThreadPool(6)` | **6 là cấu hình explicit**, không tự đọc CPUs | Pool 6 vẫn tồn tại khi JVM thấy 2 CPUs |
| `ThreadPoolExecutor` | Tùy tham số core/max/queue mà ứng dụng đặt | Cần capacity planning, backpressure |
| GC/JIT HotSpot | Có sử dụng CPU count trong ergonomics | Số thread cụ thể tùy GC/JDK/flags, không bằng CPUs một cách máy móc |
| HTTP/event-loop/JDBC/consumer frameworks | **Tùy chính sách riêng của phiên bản thư viện** | Phải đọc docs và đo; không suy ra cùng một multiplier |
| Virtual thread scheduler Java 21+ | Carrier scheduler mặc định liên quan processors khả dụng | Số virtual threads **không bằng** target parallelism của carrier |

### Về `ForkJoinPool.common.parallelism`

Một số ứng dụng cũ chỉnh system property `java.util.concurrent.ForkJoinPool.common.parallelism` để thay mức common pool. Javadoc JDK mới cảnh báo **không khuyến khích** dùng property này như cách tuning mặc định (có cơ chế cấu hình khác ở các JDK mới). Nếu ứng dụng cần executor độc lập, ưu tiên **tạo và quản lý một pool riêng** thay vì làm thay đổi hành vi common pool dùng chung của những thư viện khác.

Với một ứng dụng vẫn tương thích Java 10, `new ForkJoinPool(parallelism)` là lựa chọn explicit có từ lâu; **không đưa API chỉ có ở JDK 19+** vào code `--release 10` mà không thiết kế riêng compile target.

## 15. Những sai lầm và hệ quả thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| “Host có 32 CPU nên JVM luôn thấy 32” | Bỏ qua cgroup quota/cpuset | Đọc CPU từ **JVM trong container** |
| “`availableProcessors()` trả CPU load hiện tại” | Sizing sai, nhầm số CPUs với % CPU | Dùng CPU utilization metrics riêng |
| “CPU limit 1500m nghĩa JVM có đúng 1 thread rưỡi” | Hiểu sai số integer và scheduler | Phân biệt quota CPU time và active CPU count |
| “CPU request 500m bắt JVM thấy 1 CPU” | Shares/weight không phải hard quota | Hiểu `requests` vs `limits` |
| “CPU shares luôn dùng để tính processor count” | Trích dẫn cũ, sai JDK19+ | Theo dõi thay đổi container detection |
| “Mọi JDK 10 đều hỗ trợ cgroups v2” | Môi trường Linux hiện đại có thể bị báo host count | Chọn JDK có hỗ trợ cgroups v2 |
| “`-XX:ActiveProcessorCount=4` cấp thêm 4 cores thật” | Overprovisioning, throttling | Cờ chỉ override JVM count, không sửa quota |
| “`-XX:-UseContainerSupport` chạy trên mọi OS” | JDK Windows có thể báo unrecognized VM option | Chỉ dùng trên nền tảng được hỗ trợ (Linux) |
| “`availableProcessors()==4` thì common pool luôn 4” | Common FJP có chính sách riêng | Gọi `getCommonPoolParallelism()` |
| “`CompletableFuture` luôn dùng common worker” | Khi common parallelism <= 1 có thể dùng fallback thread | Xem Javadoc và thử với CPU=1 |
| “`newFixedThreadPool(20)` tự co xuống khi CPU count giảm” | Pool vẫn giữ max configured | Cần policy resize/restart/explicit config |
| “CPU-bound workers cứ gấp 10 lần CPU sẽ nhanh hơn” | Context switching và quota throttling | Benchmark, kiểm soát concurrency |
| “I/O pool luôn phải bằng 2 × CPUs” | Công thức không phù hợp mọi I/O/latency | Đo wait time, queue và remote capacity |
| “Càng nhiều worker thì throughput luôn cao” | Tài nguyên dùng chung trở thành bottleneck | Đo p95/p99, throttling, GC và backpressure |
| “Khi resource limit đổi, mọi pool tự resize” | Pool init một lần có thể giữ size cũ | Theo dõi và tái cấu hình có chủ đích |
| “Giảm `availableProcessors()` là thay thế CPU limit của K8s” | Không thực thi hard quota | CPU limit do cgroup/orchestrator quản lý |
| “CPU của JVM trên Windows đo được cgroups của Linux container” | Nhầm hai môi trường tách biệt | Chạy probe **bên trong Linux container** |
| “Một test trên laptop chứng minh container awareness” | Không có Linux cgroup để xác minh | Tách test JVM override và test Docker cgroup |
| “Một công thức mô hình là mã nguồn HotSpot đầy đủ” | Bỏ qua quota/affinity/parent cgroups/JDK changes | Tham chiếu HotSpot source và dữ liệu thực |

## 16. Checklist kiểm thử và cấu hình production

Trước khi triển khai Java service vào container, hãy xác nhận:

1. **JDK thật trong image**: vendor/build/version phù hợp với loại cgroups host sử dụng.
2. **Container awareness**: trên Linux, `UseContainerSupport` không bị tắt ngoài chủ đích.
3. **CPU quota/period**: có hard limit hay chỉ shares/weight? Giá trị thực cgroup là gì?
4. **Cpuset/affinity**: process thực tế được chạy trên những logical CPU nào?
5. **CPU override**: có `-XX:ActiveProcessorCount` trong flags hoặc environment không?
6. **Giá trị JVM báo cáo**: `Runtime.availableProcessors()` in ra bao nhiêu trong container?
7. **Parallelism mặc định**: `ForkJoinPool.commonPool`, `new ForkJoinPool` và work-stealing pool đang nhận số nào?
8. **Executor tường minh**: các `ThreadPoolExecutor`, server pool, event loop và consumer pool có cấu hình riêng không?
9. **Tác vụ async**: khi CPU nhỏ, chính sách `CompletableFuture`/common pool có thay đổi cách tạo worker không?
10. **CPU-bound vs I/O-bound**: pool size có được chọn theo đặc tính công việc thay vì nhân CPU máy móc không?
11. **Backpressure và queue**: có giới hạn hàng đợi, timeout, rejection và quan sát overload không?
12. **GC/JIT ergonomics**: có cờ GC/compiler tự động nào cần quan sát hoặc benchmark khi thay CPU count không?
13. **CPU throttling**: pod/container có bị throttled mạnh tại p95/p99 cao không?
14. **CPU resource thay đổi runtime**: library pool có refresh/reconfigure/restart không?
15. **Cross-platform**: lệnh `UseContainerSupport` và `-XshowSettings:system` chỉ được dùng ở nơi có hỗ trợ.
16. **Kiểm thử JDK mới**: chính sách cpu.shares mặc định đã đổi từ JDK19; không dùng cờ cũ đã bỏ.
17. **Cấu hình bắt buộc**: nếu service phải có giới hạn worker cụ thể, thể hiện trong app config và kiểm tra metrics, đừng chỉ dựa vào JVM flag.
18. **Khả năng tái lập**: pin image build, resource limits, JVM args và workload khi so hiệu năng.

**Ba nhóm test nên tách riêng:** (A) correctness của thuật toán Java bất kể CPUs, (B) JVM `availableProcessors` và worker sizing dưới `ActiveProcessorCount`, (C) Linux cgroup detection thật trong Docker/Kubernetes. Không dùng kết quả nhóm B để mạo nhận đã thử nhóm C.

## 17. Câu hỏi tự kiểm tra

1. `Runtime.availableProcessors()` là API mới chỉ có từ Java 10 hay đã có trước?
2. Java 10 có cải tiến gì liên quan container CPU?
3. Vì sao máy chủ 32 logical CPU có thể báo `availableProcessors()==2` bên trong container?
4. CPU quota `150000/100000` có nghĩa CPU count trả số thực 1,5 không?
5. CPU request 500m có tương đương hard limit 0,5 CPU không?
6. Từ JDK 19, HotSpot mặc định còn dùng `cpu.shares` để xác định active processor count không?
7. Vì sao JDK 10 đời đầu không nên được mặc định coi hỗ trợ cgroups v2?
8. `-XX:ActiveProcessorCount=4` có làm kernel cấp thêm 4 CPU thật không?
9. `-XX:-UseContainerSupport` có nên chạy trên JDK Windows không?
10. `new ForkJoinPool()` và `ForkJoinPool.commonPool()` có buộc luôn cùng target parallelism không?
11. Vì sao khi JVM nhìn thấy chỉ một CPU, `CompletableFuture.supplyAsync` có thể không chạy trên common pool worker?
12. `Executors.newFixedThreadPool(6)` tự chuyển thành 2 threads khi `availableProcessors()==2` không?
13. Vì sao một pool CPU-bound có 16 workers có thể chậm hơn pool 2 workers khi bị giới hạn 1,5 CPU?
14. `-XshowSettings:system` dùng để chẩn đoán những gì trên Linux?
15. Nếu CPU limit thay đổi khi JVM đang chạy, pool đã tạo trước đó chắc chắn resize không?
16. Cần kiểm chứng điều gì để phân biệt “JVM biết có mấy CPU” với “ứng dụng tận dụng CPU có hiệu quả”?
17. Virtual threads Java 21+ có nghĩa số virtual threads luôn bằng số active processors không?
18. Với một framework không rõ default pool size, đọc `availableProcessors()` thôi đã đủ khẳng định số worker không?

**Đáp án:**

1. Đã có từ **Java 1.4**; Java 10 cải thiện **HotSpot container awareness**, không phát minh API.
2. HotSpot dùng thông tin container resource trên Linux trong việc xác định processors và memory để cấu hình JVM.
3. JVM có thể xét cgroup quota, cpuset/affinity hoặc override `ActiveProcessorCount`.
4. Không. API trả `int`, mô hình quota phân số thường được làm tròn để tạo CPU hint nguyên.
5. Không. Request phục vụ scheduling/weight; hard limit là điều kiện riêng.
6. **Không theo mặc định trên JDK 19+**; cơ chế cũ dẫn tới underutilization đã được thay đổi.
7. Cgroups v2 được bổ sung từ **JDK 15** và backport vào các dòng cập nhật nhất định.
8. Không. Cờ override heuristic của JVM, không sửa quota kernel.
9. Không; tài liệu `UseContainerSupport` áp dụng Linux-only và JVM Windows kiểm thử không nhận cờ.
10. Không. Common pool có chính sách riêng và có thể được cấu hình độc lập.
11. Javadoc nói khi common pool parallelism không đủ 2, CompletableFuture có thể dùng thread riêng cho từng async task.
12. Không. `6` là giá trị explicit trong constructor.
13. Nhiều worker tranh CPU time bị quota/throttling; overhead scheduling/contending có thể tăng.
14. Hiển thị thông tin host/container và một số cấu hình cgroup mà JVM nhận diện.
15. Không đảm bảo; nhiều pool sizing tại initialization và cần cấu hình lại.
16. Đo actual throughput, latency, CPU utilization/throttling, queue/GC và worker states.
17. Không. Scheduler carriers có parallelism riêng, số virtual tasks/threads không bằng CPUs.
18. Không. Thư viện có mặc định, min/max, multiplier và override riêng; phải đọc docs/config/metrics.

## 18. Tài liệu chính thức và nguồn hiện hành

- **Oracle Java SE 25 `Runtime.availableProcessors()` — hợp đồng số processors JVM thấy và khả năng thay đổi:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html
- **Oracle Java SE 25 `OperatingSystemMXBean.getAvailableProcessors()`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html
- **Oracle JDK 25 `java` command — `ActiveProcessorCount`, `UseContainerSupport`, `-XshowSettings:system` và logging:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **Oracle JDK 27 `java` command — xác nhận container-awareness và CPU override vẫn hiện hành:** https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- **Oracle JDK 25 `ForkJoinPool` — common pool, parallelism và constructor mặc định:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- **Oracle JDK 25 `Executors` — newWorkStealingPool/newFixedThreadPool:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html
- **Oracle JDK 25 `CompletableFuture` — default async executor, trường hợp common pool parallelism nhỏ:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **OpenJDK mã nguồn HotSpot hiện hành — os_linux.cpp, active_processor_count/cgroup quota/affinity:** https://github.com/openjdk/jdk/blob/master/src/hotspot/os/linux/os_linux.cpp
- **Oracle JDK 19 Release Notes — CPU shares ignored khi tính active processor count (JDK-8281181):** https://www.oracle.com/java/technologies/javase/19-relnote-issues.html
- **OpenJDK JDK-8146115 — Java Improvements for Docker Containers (JDK 10):** https://bugs.openjdk.org/browse/JDK-8146115
- **OpenJDK JDK-8230305 — cgroups v2 resource detection:** https://bugs.openjdk.org/browse/JDK-8230305
- **Kubernetes — cgroups v2 và yêu cầu JDK hỗ trợ:** https://kubernetes.io/docs/concepts/architecture/cgroups/
- **Oracle JDK 25 VirtualThreadSchedulerMXBean — scheduler parallelism mặc định theo CPU khả dụng:** https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html

**Kết luận:** `Runtime.availableProcessors()` trả **số processors JVM nhìn thấy**, không trực tiếp đo CPU load, physical cores hay CPU quota phân số. Trong **Linux container**, HotSpot hiện đại dùng dữ liệu cgroup quota và affinity/cpuset để xác định số CPU, có thể làm tròn quota phân số thành số nguyên; từ **JDK 19** nó không còn mặc định lấy CPU shares làm CPU count. **`-XX:ActiveProcessorCount=N`** có thể override số CPU dùng cho ergonomics nhưng **không thay hard limit của kernel**. Một số công cụ Java như `ForkJoinPool` và `Executors.newWorkStealingPool` dùng thông tin này để sizing, trong khi common pool, `CompletableFuture`, server pools và các library khác có chính sách riêng. Hãy **đo bằng chính JVM trong container**, kiểm tra cgroups/flags/pool thực tế, chọn worker size theo workload và chỉ khẳng định hiệu năng sau benchmark có đối chứng.