# Ảnh hưởng tới số luồng GC và các bộ thực thi dùng cấu hình mặc định

*Chủ đề Java 10 — CPU trong container. Bài học giải thích cách HotSpot xác định **CPU hiệu dụng** khi chạy trong Linux container, tại sao con số đó ảnh hưởng tới số worker garbage collection (GC), `ForkJoinPool`, parallel streams và một số `Executor` mặc định; cách kiểm tra, cấu hình có chủ đích và đo độ trễ dưới hạn mức CPU. Các kiến thức được trình bày theo hành vi còn áp dụng trên Java 17+, đồng thời lưu ý thay đổi quan trọng ở JDK 19 và JDK 25.*

## 1. Tình huống: container có 2 vCPU nhưng host có 32 CPU

Một dịch vụ Java chạy trong Linux container trên máy 32 CPU vật lý/logic. Deployment áp đặt CPU limit tương đương **2 vCPU**. Hãy xem hai trường hợp:

- JVM nhận diện **32 CPU** như host và tự tạo nhiều GC workers, compiler workers, work-stealing workers.
- JVM nhận diện **2 CPU hiệu dụng** theo quota/affinity và chọn quy mô pool phù hợp hơn.

Đây không chỉ là khác biệt trong dòng thông báo:

~~~java
int cpus = Runtime.getRuntime().availableProcessors();
~~~

Số CPU mà JVM nhìn thấy có thể **chi phối nhiều quyết định tự động khi khởi động**:

~~~text
CPU quota / cpuset / OS affinity / HotSpot overrides
                       │
                       ▼
       active processor count của HotSpot
                       │
       ┌───────────────┼──────────────────┬───────────────────┐
       ▼               ▼                  ▼                   ▼
 availableProcessors  GC worker sizing   ForkJoinPool       Các heuristic
    trong Java        (theo collector)   common/default     JVM/framework
                       │                  │                   │
                       ▼                  ▼                   ▼
              GC pause/CPU usage    parallel streams       Mức cạnh tranh CPU
                                     async work             và tail latency
~~~

Nếu số worker quá lớn so với CPU quota, các thread cạnh tranh nhau và có thể làm tăng **CFS throttling**, context switching, độ trễ request hoặc GC pauses. Nếu quá nhỏ, CPU nhàn rỗi dù ứng dụng có công việc song song.

**Kết luận trước:** số CPU hiệu dụng là **đầu vào cho các heuristic**, **không phải** một quy tắc bảo đảm “container 2 CPU thì toàn bộ tiến trình chỉ có đúng 2 thread” hay “mọi executor đều có kích thước 2”.

## 2. Java 10 thay đổi điều gì?

Từ **JDK 10**, HotSpot bổ sung hỗ trợ nhận diện tài nguyên CPU/memory của Linux containers, với option `-XX:+UseContainerSupport` bật mặc định trên các HotSpot tương ứng. Điều này cho phép JVM sử dụng thông tin cgroup/quota/cpuset thay vì chỉ nhìn số CPU host.

API Java quan trọng vẫn là:

~~~java
Runtime.getRuntime().availableProcessors()
~~~

Đây là **số bộ xử lý JVM cho là khả dụng**, không nhất thiết là số lõi vật lý của máy. Cách xác định chính xác phụ thuộc OS, CPU affinity, cgroup version, container runtime, JDK build và VM flags.

Những cờ tiếp tục có ý nghĩa trên HotSpot hiện hành:

~~~text
-XX:+UseContainerSupport
-XX:-UseContainerSupport
-XX:ActiveProcessorCount=N
-Xlog:os+container=trace
~~~

Trong đó:

- `UseContainerSupport` là cơ chế hỗ trợ Linux containers, bật mặc định khi HotSpot hỗ trợ.
- `-XX:ActiveProcessorCount=N` **ghi đè số CPU mà VM sử dụng cho việc tính quy mô worker pools và các API tương ứng**. Nó còn có hiệu lực ngay cả khi `UseContainerSupport` bị tắt, theo tài liệu launcher Java 25.
- `-Xlog:os+container=trace` cho phép xem chẩn đoán container detection trên Linux HotSpot; không dùng log này làm API business.
- Những flag của HotSpot không phải hợp đồng Java SE cho mọi JVM implementation. Cần xác định distribution và runtime thực tế.

**Lưu ý rất quan trọng:** `UseContainerSupport` là **Linux-only** theo tài liệu HotSpot. Trong bài thực nghiệm Windows bên dưới, `ActiveProcessorCount` hoạt động, nhưng `-XX:-UseContainerSupport` **không được JVM Windows thử nghiệm nhận diện**. Vì vậy không dùng thử nghiệm Windows để tuyên bố đã kiểm chứng cách đọc cgroup của Linux container.

### 2.1. Container CPU detection không phải hạn mức vật lý do JVM tự áp

`-XX:ActiveProcessorCount=2` làm HotSpot tính toán như có 2 CPU hiệu dụng. Nó **không** buộc kernel giới hạn tiến trình vào đúng 2 CPU vật lý, không đặt Linux cgroup quota và không tự cấm mọi executor tạo hơn 2 thread.

Muốn giới hạn CPU time thực sự cho container, cấu hình giới hạn tại container orchestrator/kernel. VM option chủ yếu kiểm soát **heuristic về tài nguyên**.

### 2.2. Không dùng các flag CPU shares lịch sử làm giải pháp hiện đại

Từ JDK 19, HotSpot **mặc định bỏ qua CPU shares** khi tính active processor count; các bản update của nhánh LTS có thể nhận backport tùy nhà cung cấp. Trước đây dùng CPU shares như giới hạn cứng có thể khiến JVM nhận ít CPU hơn thực tế, làm dưới tải.

Không dùng hướng dẫn cũ đòi bật `-XX:+UseContainerCpuShares` để “chỉnh cho đúng CPU” trên JDK hiện nay; cờ đó đã bị loại khỏi JDK 21. Cần dựa trên CPU **quota, cpuset/affinity** hoặc một `-XX:ActiveProcessorCount` được xác định rõ theo ngân sách vận hành.

## 3. CPU quota, cpuset, shares/weight và requests khác nhau

### 3.1. CPU quota — giới hạn thời gian CPU

Trên Linux cgroup v2, file `cpu.max` có dạng:

~~~text
150000 100000
~~~

Hai giá trị lần lượt là **quota** và **period** theo microseconds. Ở ví dụ này, container có thể dùng tổng cộng 150.000 μs CPU trong mỗi khoảng 100.000 μs, tương đương **1,5 CPU**.

JVM hiện hành trên Linux có thể lấy giới hạn đó để tính **active processors**; quota lẻ được **làm tròn lên** khi biểu diễn bằng số nguyên CPU hiệu dụng, nhưng còn chịu giới hạn affinity/cpuset. Vì vậy quota 1,5 CPU thường cho kết quả **2**, không phải phép đo năng lực xử lý chắc chắn bằng đúng 2 CPU ở mọi thời điểm.

~~~text
quota/period = 150000 / 100000 = 1.5
active CPU heuristic: ceil(1.5) = 2 (nếu affinity/cpuset không thấp hơn)
~~~

Đừng suy rằng JVM “có thể chạy 2 CPU đầy đủ liên tục” từ kết quả trên. Kernel vẫn áp dụng quota **1,5 CPU thời gian trung bình theo period**. Khi các worker cùng chạy hết công suất, container có thể bị throttle.

### 3.2. CPU set và affinity

Linux cgroup v2 `cpuset.cpus.effective` cho biết những CPU ID mà tác vụ có thể sử dụng. Chẳng hạn:

~~~text
0-1
~~~

biểu thị hai CPU ID khả dụng; một `cpuset.cpus.effective` khác có thể có dải không liên tiếp.

CPU affinity hoặc cpuset có thể làm số CPU thực sự phù hợp với container **nhỏ hơn quota**. Cách HotSpot kết hợp chúng phụ thuộc JDK/implementation, nên phải đối chiếu số CPU JVM thấy bằng `availableProcessors()` và chẩn đoán VM trên môi trường triển khai.

### 3.3. CPU shares/weight không phải quota

Cgroup `cpu.weight` (v2) hoặc khái niệm CPU shares từ các runtime trước là **trọng số chia sẻ CPU khi cạnh tranh**, không phải một mức trần CPU time tuyệt đối như `cpu.max`. Khi host rảnh, container có thể dùng nhiều CPU hơn mức “weight tương đối” gợi ý.

Vì JDK mới không mặc nhiên dùng CPU shares để tính số worker, một container **chỉ có CPU request/weight nhưng không có hard CPU limit** có thể thấy số CPU lớn hơn kỳ vọng của người triển khai. Ứng dụng có thể tạo nhiều worker dựa trên số CPU host/affinity. Trường hợp này đặc biệt quan trọng nếu deploy lên platform cấp CPU thông qua shares/weight mà không đặt CFS quota.

### 3.4. Kubernetes `requests.cpu` khác `limits.cpu`

Ví dụ:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-cpu-demo
spec:
  containers:
    - name: app
      image: example/java-cpu-demo:1.0
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
        limits:
          cpu: "1500m"
          memory: "512Mi"
~~~

Ví dụ YAML minh họa một cấu hình có cú pháp Kubernetes hợp lệ; tên image chỉ là ví dụ triển khai nội bộ, **không khẳng định image đó tồn tại trong registry công khai**.

- `requests.cpu: 500m` phục vụ scheduling/đảm bảo chia sẻ tài nguyên theo chính sách cluster, **không đồng nghĩa** VM chắc chắn thấy 0,5 CPU.
- `limits.cpu: 1500m` thường được ánh xạ thành quota CFS với giá trị 1,5 CPU.
- JVM có thể báo `availableProcessors() == 2` nếu quota 1,5 và affinity cho phép, nhưng **không phải bảo đảm** với mọi cgroup/JDK/host.
- Nếu không có `limits.cpu`, JVM có thể thấy nhiều CPU hơn request; quota đã không còn là hard cap.
- Việc tăng CPU limit có thể cải thiện throughput nhưng nếu thêm nhiều worker cùng lúc, bộ nhớ/CPU cạnh tranh và GC lại cần đo lại.

Khi gặp trường hợp khác kỳ vọng, đọc `cpu.max`, `cpuset.cpus.effective`, `cpu.stat` và log container-detection trong đúng container.

## 4. Đường đi từ CPU hiệu dụng đến GC

HotSpot có các quyết định **ergonomic** về số worker GC dựa trên CPU hiệu dụng, collector và cấu hình heap.

Hai option điển hình:

~~~text
-XX:ParallelGCThreads=N
-XX:ConcGCThreads=N
~~~

### 4.1. `ParallelGCThreads`

Đây là mức số worker được cấu hình cho một số công việc **GC song song**, đặc biệt tại những giai đoạn stop-the-world tùy collector. Tài liệu Java 25 mô tả số mặc định **phụ thuộc số CPU khả dụng và collector được chọn**.

Ví dụ với G1:

~~~bash
java -XX:+UseG1GC -XX:ParallelGCThreads=2 -Xmx256m MyApp
~~~

Cờ này đặt số worker song song của GC có liên quan theo implementation. Nó **không** có nghĩa ứng dụng chỉ có hai thread, cũng không có nghĩa mọi lần pause sẽ sử dụng tối đa hai worker thực tế. Collector có thể linh hoạt chọn số worker đang hoạt động theo kích thước vùng công việc và tình trạng heap.

**Không coi `ParallelGCThreads` bằng `Runtime.availableProcessors()` như một luật cố định**. Một số collector/phiên bản dùng công thức và giới hạn khác, nhất là khi nhiều chục CPU.

### 4.2. `ConcGCThreads`

Một số collector hỗ trợ **GC công việc đồng thời** khi Java mutator vẫn chạy. `ConcGCThreads` là cấu hình số worker cho những pha đó.

Ví dụ:

~~~bash
java -XX:+UseG1GC -XX:ConcGCThreads=2 -Xmx256m MyApp
~~~

Số mặc định của `ConcGCThreads` được HotSpot tính từ worker song song/CPU; hướng dẫn JDK hiện hành nêu mức ước lượng quanh **một phần tư số Parallel GC threads** đối với cấu hình liên quan. Nhưng nó vẫn tùy collector, heuristic, giới hạn và phiên bản.

**Phân biệt:**

- STW parallel GC workers tăng có thể rút ngắn một phần pause khi CPU đủ, nhưng cũng làm tăng CPU burst.
- Concurrent GC workers tăng có thể cải thiện tốc độ làm sạch heap ở pha concurrent, nhưng **tranh CPU với application threads** và có thể làm request latency lớn hơn.
- Quota thấp + quá nhiều GC workers có thể gây CPU throttling, làm hiệu năng giảm dù “nhiều thread” nghe có vẻ nhanh.

Không có một giá trị `ParallelGCThreads`/`ConcGCThreads` tối ưu cho mọi workload. Cần đo GC pause, throughput, CPU utilization và throttling cùng nhau.

### 4.3. Các collector khác nhau không có cùng mô hình worker

- **G1**: có STW worker và concurrent worker, ảnh hưởng bởi CPU count.
- **Parallel GC**: chủ yếu tối ưu throughput bằng các worker GC song song, có quy tắc sizing riêng.
- **ZGC/Shenandoah**: có nhiều phần công việc đồng thời; policy/flag có thể khác, đặc biệt giữa các JDK releases.
- **Serial GC**: bản chất sử dụng một số tác vụ đơn luồng; không áp dụng công thức ParallelGCThreads của G1 như thể giống nhau.

Vì vậy bài này dùng **G1 trong thử nghiệm** để tạo một ví dụ có thể kiểm chứng, nhưng không tổng quát hóa các số worker đó thành chuẩn cho mọi collector.

### 4.4. Số worker GC không phải tổng số native threads

Dòng log:

~~~text
Parallel Workers: 4
Concurrent Workers: 1
~~~

nêu worker configuration của GC ở lúc khởi tạo, **không** có nghĩa tiến trình Java chỉ có 5 OS threads, và cũng không bảo đảm đúng 4 worker bận việc ở mọi lần pause.

Một JVM có Java application threads, JIT compiler threads, reference handlers, signal/service threads, GC workers và các thread nội bộ khác. Không suy tổng OS thread count bằng tổng hai con số GC này.

## 5. GC worker count thay đổi thế nào khi CPU hiệu dụng thay đổi?

Để tách tác động CPU heuristic khỏi container runtime, thử nghiệm dùng HotSpot **JDK 24 trên Windows** với `-XX:ActiveProcessorCount=N`. Cờ này hoạt động trên HotSpot Windows và làm `availableProcessors()`/GC sizing thay đổi. Đây **không phải thử nghiệm Linux cgroup**, mà là phép kiểm tra đường tính CPU count của VM.

Lệnh minh họa cho N=4:

~~~bash
java -XX:ActiveProcessorCount=4 \
     -XX:+UseG1GC -Xms128m -Xmx128m \
     -Xlog:gc+init=info \
     -cp . ContainerCpuPoolDemo
~~~

Trong thực nghiệm, `-Xlog:gc+init=info` có thể báo:

~~~text
CPUs: 28 total, 4 available
Parallel Workers: 4
Concurrent Workers: 1
Concurrent Refinement Workers: 4
~~~

`28 total` là đặc điểm máy đã kiểm thử; **không phải CPU count mặc định của người đọc**. `4 available` là CPU count được override. Tên và số các loại GC workers phụ thuộc JDK/collector.

### 5.1. Bảng kết quả thử nghiệm thực

| `ActiveProcessorCount` | `availableProcessors()` | G1 Parallel Workers | G1 Concurrent Workers | G1 Concurrent Refinement Workers |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 1 | 1 |
| 2 | 2 | 2 | 1 | 2 |
| 4 | 4 | 4 | 1 | 4 |
| 8 | 8 | 8 | 2 | 8 |

Đây là **số liệu thực tế trên một JDK 24 G1** với heap cố định 128 MiB và flag CPU override. Chúng chứng minh hướng ảnh hưởng, nhưng **không phải quy tắc bất biến** kiểu “mọi JVM 8 CPU đều có Concurrent Workers=2”.

### 5.2. Cách đọc các flag ergonomics

~~~bash
java -XX:ActiveProcessorCount=4 \
     -XX:+UseG1GC -Xms128m -Xmx128m \
     -XX:+PrintFlagsFinal -cp . ContainerCpuPoolDemo
~~~

Tìm hai dòng:

~~~text
ParallelGCThreads
ConcGCThreads
~~~

Ở lần thử CPU=4, giá trị lần lượt là **4** và **1**. Trên PowerShell:

~~~powershell
java -XX:ActiveProcessorCount=4 -XX:+UseG1GC -Xms128m -Xmx128m -XX:+PrintFlagsFinal -cp . ContainerCpuPoolDemo | Select-String 'ParallelGCThreads|ConcGCThreads'
~~~

**Lưu ý:** `PrintFlagsFinal` cho biết giá trị cấu hình/ergonomic của VM. Không chỉ lấy giá trị này rồi kết luận độ trễ GC sẽ giảm; cần đo pause durations trong production workload.

## 6. CPU hiệu dụng ảnh hưởng `ForkJoinPool.commonPool()` ra sao?

`ForkJoinPool` là hạ tầng chạy nhiều tác vụ song song và work stealing trong Java. **Common pool** là pool toàn JVM được nhiều API dùng, gồm `parallelStream()` ở bối cảnh phù hợp và nhiều dạng `CompletableFuture` async.

Ví dụ:

~~~java
int cpus = Runtime.getRuntime().availableProcessors();

int commonParallelism =
        ForkJoinPool.commonPool().getParallelism();
~~~

Trên JDK 24 thử nghiệm, nếu không override riêng common pool, mức song song common pool là:

~~~text
CPU hiệu dụng 1 -> commonPool parallelism 1
CPU hiệu dụng 2 -> commonPool parallelism 1
CPU hiệu dụng 4 -> commonPool parallelism 3
CPU hiệu dụng 8 -> commonPool parallelism 7
~~~

Trong cấu hình thông thường có thể hiểu heuristic theo `max(1, availableProcessors - 1)`, nhưng **đừng coi đó là công thức bất biến** trước các JVM flags, security/custom thread factory và thay đổi implementation. Muốn biết giá trị thật, hỏi `ForkJoinPool.commonPool().getParallelism()`.

**Lưu ý quan trọng:** `getParallelism()` là **mức song song mục tiêu**, không phải số thread đã được tạo tức thời và không phải số thread đang bận. `ForkJoinPool` có thể sinh worker khi có việc, và một caller thread có thể tham gia chạy tác vụ theo cơ chế sử dụng.

### 6.1. Parallel streams dùng chung tài nguyên

~~~java
long count = java.util.stream.IntStream.range(0, 1000)
        .parallel()
        .filter(i -> (i & 1) == 0)
        .count();
~~~

Bản chất `parallel()` cho phép chia workload, nhưng:

- Nó **không** bảo đảm tạo 1.000 thread, và không bảo đảm nhanh hơn sequential.
- Trong đường gọi thông thường, công việc có thể được thực hiện qua ForkJoin common pool; nếu gọi bên trong một pool khác, chi tiết execution có thể chịu ảnh hưởng ngữ cảnh.
- Nếu chạy nhiều parallel streams và `CompletableFuture` trên common pool, chúng có thể tranh worker.
- Với container CPU quota thấp, tăng parallelism mà không xét throttling có thể làm tăng độ trễ.

**Không dùng `parallelStream()` vô điều kiện cho I/O blocking:** common pool được thiết kế tốt cho nhiều workload chia nhỏ CPU-bound, nhưng block DB/network có thể chiếm worker và gây starvation/độ trễ cho tác vụ khác.

### 6.2. `new ForkJoinPool()` khác common pool

~~~java
ForkJoinPool pool = new ForkJoinPool();
System.out.println(pool.getParallelism());
pool.shutdown();
~~~

Một `new ForkJoinPool()` mặc định dùng số processors mà runtime nhận diện làm mức song song mục tiêu. Trong thử nghiệm:

~~~text
1 CPU -> new ForkJoinPool parallelism 1
2 CPU -> new ForkJoinPool parallelism 2
4 CPU -> new ForkJoinPool parallelism 4
8 CPU -> new ForkJoinPool parallelism 8
~~~

Đây là **pool riêng**, không phải alias với common pool. Sau khi sử dụng, nên gọi `shutdown()`/quản lý lifecycle phù hợp để tránh rò rỉ thread/resource.

### 6.3. Điều chỉnh riêng common pool không làm đổi CPU count

HotSpot/JDK còn hỗ trợ thuộc tính:

~~~text
-Djava.util.concurrent.ForkJoinPool.common.parallelism=N
~~~

Ví dụ:

~~~bash
java -XX:ActiveProcessorCount=1 \
     -Djava.util.concurrent.ForkJoinPool.common.parallelism=4 \
     -cp . CpuOverrideMini
~~~

Trong thử nghiệm JDK 24:

~~~text
processors=1
common=4
own=1
~~~

Nghĩa là common pool được cấu hình riêng mức 4, trong khi `availableProcessors()` vẫn là 1 và một `new ForkJoinPool()` khác mặc định mức 1.

**Đừng tưởng rằng đặt common.parallelism=4 sẽ mở rộng CPU quota kernel hoặc tự đổi số GC workers.** Nó chỉ thay common pool; oversubscription có thể khiến nghẽn CPU ở container chỉ được cấp 1 CPU. Property nên được đặt **ngay lúc JVM khởi động**, trước khi common pool được khởi tạo.

## 7. Các bộ thực thi mặc định: không phải Executor nào cũng lấy CPU count

Đây là phần dễ hiểu sai nhất trong chủ đề “các bộ thực thi dùng cấu hình mặc định”.

| API | Số CPU ảnh hưởng? | Cách hiểu đúng |
| --- | --- | --- |
| `ForkJoinPool.commonPool()` | **Có** trong heuristic mặc định | Mức parallelism phụ thuộc CPU, có thể override riêng |
| `new ForkJoinPool()` | **Có** | Mặc định target parallelism bằng số processors |
| `Executors.newWorkStealingPool()` | **Có** | Mặc định target parallelism bằng processors |
| `parallelStream()` | **Gián tiếp** | Thường dựa trên common pool/đường gọi |
| `CompletableFuture.supplyAsync(...)` không truyền executor | **Gián tiếp**, phụ thuộc JDK | JDK 25+ dùng common pool; ở JDK cũ có trường hợp fallback |
| `Executors.newFixedThreadPool(3)` | **Không tự đổi** | 3 là số do người gọi chọn tường minh |
| `Executors.newSingleThreadExecutor()` | **Không** | Một executor đơn luồng |
| `Executors.newScheduledThreadPool(3)` | **Không tự đổi** | `corePoolSize=3` được người gọi định rõ |
| `Executors.newCachedThreadPool()` | **Không theo một count CPU cố định** | Tạo thêm thread khi cần, nguy cơ quá nhiều thread nếu workload tăng |
| `new ThreadPoolExecutor(...)` | **Theo tham số bạn đưa** | `corePoolSize/maxPoolSize/queue` quyết định, không tự suy đủ từ cgroup |
| `Executors.newVirtualThreadPerTaskExecutor()` (JDK 21+) | **Không giới hạn số virtual threads bằng CPU** | Mỗi task có virtual thread; scheduler/carrier concurrency có quan hệ CPU và cấu hình riêng |
| Pool của framework/application server | **Tùy phiên bản và cấu hình** | Không giả định tất cả đều đọc availableProcessors |

### 7.1. `Executors.newWorkStealingPool()`

~~~java
ExecutorService executor = Executors.newWorkStealingPool();
try {
    // submit/invoke công việc
} finally {
    executor.shutdown();
}
~~~

Javadoc nói rõ factory không tham số dùng **số processors khả dụng** làm **target parallelism**. Nó có thể tạo các worker theo nhu cầu, không nhất thiết khởi tạo ngay toàn bộ worker hoặc duy trì đúng một lượng thread bất biến.

Khi CPU hiệu dụng đổi từ 8 xuống 2, một pool mới tạo theo default có thể chọn target 2 thay vì 8. Với service có nhiều tác vụ CPU-bound, đây là lợi ích container awareness trực tiếp.

### 7.2. `newFixedThreadPool(n)`

~~~java
ExecutorService fixed = Executors.newFixedThreadPool(3);
try {
    // 3 worker được dùng khi cần theo contract factory.
} finally {
    fixed.shutdown();
}
~~~

`3` là lựa chọn tường minh của developer. Nếu container chỉ có 1 CPU, Java **không tự sửa 3 thành 1** chỉ vì cgroup quota nhỏ. Nếu ứng dụng dùng `n = Runtime.getRuntime().availableProcessors()` trước khi gọi factory, **chính code ứng dụng** đã tạo liên hệ CPU, chứ factory `newFixedThreadPool(int)` không tự đọc CPU count.

### 7.3. `newCachedThreadPool()`

Một cached pool không có “default size = số CPU”. Nó có thể tạo nhiều thread theo lượng task đợi thực thi, dẫn tới oversubscription và memory pressure dưới CPU quota nhỏ.

Với workloads blocking, thread count có thể lớn hơn CPU count là bình thường, nhưng vẫn phải có giới hạn tổng task/connections và backpressure phù hợp. Không gán một quy tắc “CPU=2 thì chỉ có 2 I/O threads” cho mọi loại công việc.

### 7.4. Thread pool của frameworks

Framework HTTP, scheduling, reactive/event loop, servlet hoặc application server có **đường định cỡ riêng**: có framework dùng số CPU, có framework dùng một hằng số, có framework dùng tham số config, có framework chia event loop và blocking workers.

Sau khi thay CPU limit của pod, phải xem **cấu hình thực tế** của executor framework đang dùng: thread dumps, metrics của queue/active threads và tài liệu đúng phiên bản. Không kết luận tất cả cùng giảm xuống `availableProcessors()`.

## 8. Điểm cập nhật quan trọng JDK 25: `CompletableFuture` khi CPU ít

Trước JDK 25, `CompletableFuture.supplyAsync(...)`/`runAsync(...)` **không có explicit executor** dùng common pool **nếu common pool có parallelism từ 2 trở lên**; khi mức song song common pool thấp hơn 2, implementation có thể dùng **một thread mới cho mỗi async task**.

Từ **JDK 25**, theo release notes **JDK-8319447**, `CompletableFuture` và `SubmissionPublisher` đổi hành vi: **các async methods không truyền executor đều dùng ForkJoin common pool**, **kể cả khi pool parallelism=1**.

Đây là điểm dễ làm ứng dụng container ít CPU thay đổi behavior sau nâng JDK.

### 8.1. Ví dụ khác biệt khi `ActiveProcessorCount=1`

~~~java
String workerName = CompletableFuture.supplyAsync(
        () -> Thread.currentThread().getName()
).join();
~~~

Trong thử nghiệm JDK 24, `commonPool().getParallelism()==1`, nhưng tác vụ được thực thi trên một thread được tạo riêng; kiểm tra tên `ForkJoinPool.commonPool-worker` trả false.

Trên JDK 25+, không thể dựa vào fallback cũ; nhiệm vụ đi qua common pool kể cả parallelism 1. **Không dùng tên thread như tiêu chí production correctness** vì nó là chi tiết implementation, và không xem một lần submit là phép benchmark.

### 8.2. Vì sao thay đổi này quan trọng cho I/O blocking?

Nếu code có hàng nghìn `CompletableFuture.supplyAsync(() -> blockingDatabaseCall())` không truyền `Executor`, thì trên JDK 25 với common pool parallelism 1, các tác vụ có thể chờ nhau trong pool nhỏ, gây queueing và latency. Điều ngược lại ở JDK trước (tạo thread mới) cũng không hẳn tốt, vì có thể gây thread explosion.

**Khuyến nghị hiện hành:** chọn executor đúng loại công việc và truyền rõ:

~~~java
ExecutorService blockingPool = Executors.newFixedThreadPool(16);
try {
    CompletableFuture<String> f =
            CompletableFuture.supplyAsync(
                    () -> loadFromRemoteService(), blockingPool);
    String result = f.join();
} finally {
    blockingPool.shutdown();
}
~~~

Đây là **đoạn minh họa trong một method**, với `loadFromRemoteService()` là hàm của ứng dụng, không phải file Java độc lập. Số `16` chỉ minh họa một lựa chọn đã cấu hình: **không** phải “16 threads là tối ưu cho container 2 CPU”. Cần xét latency I/O, giới hạn connection, queue, memory, timeout và backpressure.

Đối với ứng dụng JDK 21+ có thể cân nhắc virtual threads cho blocking I/O phù hợp, nhưng **virtual threads không xóa giới hạn CPU**, không tự tăng connection pool hoặc capacity của downstream service.

### 8.3. Đừng nhầm behavior JDK 24 và JDK 25

Khi xây test, đừng assert `CompletableFuture` luôn tạo thread mới nếu common pool parallelism nhỏ hơn 2. Đó là mô tả **trước JDK 25**. Đừng assert một task nhất định luôn chạy trên cùng thread với tên cố định trong mọi VM/JDK. Dựa trên contract của runtime đang triển khai, đo pool/task metrics và dùng explicit executor khi cần bảo đảm isolation.

## 9. Chương trình Java 17+ hoàn chỉnh, đã kiểm thử

Chương trình sau in trực tiếp CPU hiệu dụng, mức song song common pool, private `ForkJoinPool`, work-stealing pool, thử fixed pool và quan sát `CompletableFuture`. Các giá trị có thể so sánh dễ dàng bằng `-XX:ActiveProcessorCount`.

### 9.1. Mã nguồn

~~~java
// File: ContainerCpuPoolDemo.java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;

public final class ContainerCpuPoolDemo {
    public static void main(String[] args) {
        int cpus = Runtime.getRuntime().availableProcessors();
        System.out.println("available processors = " + cpus);
        System.out.println("common pool parallelism = "
                + ForkJoinPool.commonPool().getParallelism());

        ForkJoinPool custom = new ForkJoinPool();
        ExecutorService workStealing = Executors.newWorkStealingPool();
        ExecutorService fixed = Executors.newFixedThreadPool(3);
        try {
            System.out.println("new ForkJoinPool parallelism = "
                    + custom.getParallelism());
            System.out.println("work stealing is ForkJoinPool = "
                    + (workStealing instanceof ForkJoinPool));
            if (workStealing instanceof ForkJoinPool pool) {
                System.out.println("work stealing parallelism = "
                        + pool.getParallelism());
            }
            System.out.println("fixed tasks complete = "
                    + (fixed.submit(() -> "ok").get().equals("ok")));
            String thread = CompletableFuture.supplyAsync(
                    () -> Thread.currentThread().getName()).join();
            System.out.println("CompletableFuture on common worker = "
                    + thread.startsWith("ForkJoinPool.commonPool-worker"));
        } catch (Exception e) {
            throw new RuntimeException(e);
        } finally {
            fixed.shutdown();
            workStealing.shutdown();
            custom.shutdown();
        }
    }
}
~~~

Mã **biên dịch Java 17 trở lên**. `instanceof ForkJoinPool pool` dùng pattern matching có sẵn trong Java 17. Trong JDK 24, `Executors.newWorkStealingPool()` trả một `ForkJoinPool` và code in mức song song của nó. Factory được định nghĩa bằng interface `ExecutorService`, nên nếu chạy một implementation khác không phải `ForkJoinPool`, chương trình chỉ in boolean false và bỏ qua dòng mức song song; đó không phải lỗi nguồn.

### 9.2. Biên dịch và chạy

~~~bash
javac --release 17 ContainerCpuPoolDemo.java
java -XX:ActiveProcessorCount=4 \
     -XX:+UseG1GC -Xms128m -Xmx128m \
     -Xlog:gc+init=info \
     ContainerCpuPoolDemo
~~~

Trên PowerShell:

~~~powershell
javac --release 17 ContainerCpuPoolDemo.java
java '-XX:ActiveProcessorCount=4' '-XX:+UseG1GC' '-Xms128m' '-Xmx128m' '-Xlog:gc+init=info' ContainerCpuPoolDemo
~~~

Stdout **do chương trình in** ở JDK 24 với `ActiveProcessorCount=4`:

~~~text
available processors = 4
common pool parallelism = 3
new ForkJoinPool parallelism = 4
work stealing is ForkJoinPool = true
work stealing parallelism = 4
fixed tasks complete = true
CompletableFuture on common worker = true
~~~

Ngoài các dòng trên, JVM còn in GC initialization logs. Trong thử nghiệm với `ActiveProcessorCount=4` có:

~~~text
CPUs: 28 total, 4 available
Parallel Workers: 4
Concurrent Workers: 1
Concurrent Refinement Workers: 4
~~~

### 9.3. Kết quả với bốn mức CPU

Chạy lần lượt:

~~~bash
java -XX:ActiveProcessorCount=1 -XX:+UseG1GC -Xms128m -Xmx128m ContainerCpuPoolDemo
java -XX:ActiveProcessorCount=2 -XX:+UseG1GC -Xms128m -Xmx128m ContainerCpuPoolDemo
java -XX:ActiveProcessorCount=4 -XX:+UseG1GC -Xms128m -Xmx128m ContainerCpuPoolDemo
java -XX:ActiveProcessorCount=8 -XX:+UseG1GC -Xms128m -Xmx128m ContainerCpuPoolDemo
~~~

Các dòng liên quan đến pool từ **một lần thử nghiệm thực trên JDK 24**:

| CPU giả lập | `availableProcessors` | Common pool parallelism | `new ForkJoinPool` | `newWorkStealingPool` | `CompletableFuture` trên common worker |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | 1 | 1 | 1 | false |
| 2 | 2 | 1 | 2 | 2 | false |
| 4 | 4 | 3 | 4 | 4 | true |
| 8 | 8 | 7 | 8 | 8 | true |

Trong **tất cả bốn lượt**:

~~~text
work stealing is ForkJoinPool = true
fixed tasks complete = true
~~~

**Không chuyển bảng thành kết quả cố định trên mọi JDK**: cột `CompletableFuture` đặc biệt khác kể từ JDK 25, tên thread không phải contract, và common pool có thể bị cấu hình riêng.

### 9.4. Giải thích cách đọc bảng

1. `availableProcessors` đi theo CPU override, xác nhận HotSpot nhận số CPU hiệu dụng tương ứng.
2. Common pool dùng một heuristic riêng, không giống mặc định của `new ForkJoinPool()`.
3. Work-stealing pool mặc định nhận processors làm target parallelism theo Javadoc.
4. Fixed pool 3 thread vẫn chạy task thành công dù CPU=1, vì số thread là tham số người viết code chọn.
5. `CompletableFuture` trước JDK 25 có fallback khi common pool parallelism=1; đó là lý do hai hàng CPU=1/2 in false. JDK 25+ đổi sang common pool luôn, phải chú ý khi nâng cấp.
6. Không phải mọi thread pool đều phải có đúng CPU count; số worker là **mức cấu hình** và thời điểm tạo pool/lượng việc ảnh hưởng số thread đang chạy.

### 9.5. Cách thử thêm mức common pool độc lập

Một file Java ngắn khác:

~~~java
// File: CpuOverrideMini.java
import java.util.concurrent.ForkJoinPool;

public final class CpuOverrideMini {
    public static void main(String[] args) {
        System.out.println("processors="
                + Runtime.getRuntime().availableProcessors());
        System.out.println("common="
                + ForkJoinPool.commonPool().getParallelism());
        ForkJoinPool own = new ForkJoinPool();
        System.out.println("own=" + own.getParallelism());
        own.shutdown();
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 CpuOverrideMini.java
~~~

Chạy trên JDK 24:

~~~bash
java -XX:ActiveProcessorCount=1 CpuOverrideMini
java -XX:ActiveProcessorCount=1 \
     -Djava.util.concurrent.ForkJoinPool.common.parallelism=4 \
     CpuOverrideMini
~~~

Stdout lần thứ nhất:

~~~text
processors=1
common=1
own=1
~~~

Stdout lần thứ hai:

~~~text
processors=1
common=4
own=1
~~~

Kiểm thử này chứng minh **hai cơ chế điều chỉnh độc lập**: `ActiveProcessorCount` là số CPU VM nhìn thấy; `common.parallelism` là target của riêng common pool. Đặt common parallelism=4 trong container chỉ được cấp CPU=1 không tạo thêm CPU time từ kernel.

## 10. Số CPU ảnh hưởng đến độ trễ và throughput theo những đường nào?

### 10.1. Quá nhiều GC threads so với quota

Giả sử container quota 1 CPU nhưng JVM cho rằng có 16 CPU. Một pha GC sử dụng nhiều worker có thể chạy dồn và bị kernel cắt quota. Lúc ấy:

- GC pause có thể kéo dài qua nhiều CFS periods.
- Application thread không còn CPU time để xử lý request đúng deadline.
- CPU throttling count và thời gian throttle có thể tăng.
- Tăng số worker không giúp nếu tài nguyên là nút thắt.

Nhưng đây là **cơ chế có thể xảy ra**, không phải quy luật mọi công việc GC nhiều thread đều chậm hơn. Với CPU thật và quota đủ, tăng GC workers có thể giảm pause duration.

### 10.2. Quá ít GC threads

Nếu JVM mặc định nhận diện chỉ 1 CPU trong khi container được phép dùng 8 CPU, một số GC operation có thể bỏ lỡ khả năng song song, khiến pause dài hơn. Các parallel streams và work stealing cũng có thể dưới tải.

Do đó, **không nên giảm `ActiveProcessorCount` xuống 1 như một “mẹo tiết kiệm CPU” áp dụng vô điều kiện**. Việc “ít thread” có thể giảm tranh CPU, nhưng cũng giảm khả năng sử dụng tài nguyên có sẵn.

### 10.3. Quá nhiều application executors

Mỗi framework có thể tạo pool riêng, cộng với common pool, GC và JIT. Dưới quota nhỏ, tổng số *runnable* threads có thể lớn hơn số CPU một cách đáng kể.

Ảnh hưởng tiềm năng:

- Context switch và run queue tăng.
- Thời gian GC concurrent tranh CPU với request work.
- Tail latency, timeout/error rate tăng.
- Các task blocking có thể chiếm hết worker của pool quá nhỏ hoặc shared.
- Queue dài dần dù `availableProcessors` hiển thị “đúng”.

**Không kết luận số thread hệ điều hành phải nhỏ hơn hoặc bằng vCPU.** Nhiều thread chờ I/O là hợp lý, nhưng phải quản lý số task thực sự runnable và giới hạn downstream.

### 10.4. Hạn mức phân số: 1,5 vCPU nhưng heuristic chọn 2

Một quota 1,5 CPU được làm tròn lên 2 làm các pool có thể chọn mức phù hợp với 2 CPU. Điều này có thể hợp lý để tạo concurrency, nhưng nếu hai CPU-bound worker chạy liên tục, kernel vẫn phải throttle để giữ mức trung bình 1,5. Muốn hiểu latency, hãy xem **`cpu.stat` throttled periods** chứ không chỉ nhìn `availableProcessors()`.

### 10.5. GC không phải nguyên nhân duy nhất của request chậm

Một service có p99 xấu có thể do database, lock contention, network, CPU scheduling, JIT warmup, downstream rate limit, hoặc GC. Đo correlation với GC/safepoint và CPU throttling trước khi chỉnh `ParallelGCThreads` hay `ConcGCThreads`.

## 11. Cấu hình hợp lý: chọn CPU budget, không đoán số worker

### 11.1. Tình huống A — CPU limit thực, JVM đọc đúng

Nếu container CPU limit 2, HotSpot JDK phù hợp báo `availableProcessors()==2` và worker sizing hợp lý, hãy **giữ default trước**, benchmark theo tải thực. Đừng vội chỉnh cả GC lẫn common pool chỉ vì muốn “tối ưu”.

### 11.2. Tình huống B — Chỉ có CPU shares/requests

Nếu runtime cấp CPU qua shares/weight mà không có quota, JVM mới có thể thấy số CPU lớn. Có thể chọn:

~~~text
-XX:ActiveProcessorCount=2
~~~

nếu deployment có một ngân sách CPU rõ và thực sự muốn các heuristic JVM hoạt động ở mức 2. **Đây là lựa chọn policy ứng dụng**, không phải cách diễn giải tự động của CPU request trong mọi runtime.

Đừng dùng cờ cũ `UseContainerCpuShares`; hành vi đã thay đổi ở JDK hiện hành.

### 11.3. Tình huống C — Common pool bị dùng cho nhiều blocking tasks

Dù CPU hiệu dụng là 2 hay 8, common pool có thể không phù hợp cho blocking I/O. Tạo executor riêng cho loại task, có giới hạn queue/backpressure/timeout và gắn lifecycle theo ứng dụng.

Không nâng common pool lên hàng trăm workers chỉ để cứu một thành phần blocking nếu điều đó làm các parallel streams khác bị tranh tài nguyên.

### 11.4. Tình huống D — GC là bottleneck đã được đo

Nếu log GC cho thấy STW/concurrent phases gây latency và CPU throttling, thử một số cấu hình `ParallelGCThreads` và `ConcGCThreads` trong môi trường benchmark tương đương. Thay **một yếu tố mỗi lần**, giữ heap/collector/workload ổn định.

**Không đề xuất công thức kiểu “GC threads = CPU/2” như chuẩn cho mọi collector**, vì HotSpot đã có ergonomics và các collector được thiết kế khác nhau.

## 12. Quan sát container CPU từ trong ứng dụng và Linux

### 12.1. Tại lớp Java

~~~java
System.out.println("available processors = "
        + Runtime.getRuntime().availableProcessors());
~~~

Trong code có thêm logging/telemetry khi khởi động sẽ rất hữu ích để phát hiện “container được cấp 2 CPU nhưng JVM nghĩ 32 CPU”.

Nên ghi kèm:

- JDK vendor/build và runtime image.
- `availableProcessors()`.
- Flag `ActiveProcessorCount` nếu có override.
- GC collector, `ParallelGCThreads`/`ConcGCThreads` hiệu lực.
- Parallelism của các executor quan trọng.
- Cấu hình CPU request/limit của workload nếu có nguồn telemetry an toàn.

### 12.2. Tại Linux cgroup v2

Các lệnh minh họa khi hệ thống dùng hierarchy cgroup v2 ở đường dẫn thích hợp:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.stat
~~~

Không phải mọi container mount hierarchy vào đúng path này; có thể cần đọc mount/cgroup path thực của process. `cpu.max` giới hạn theo quota/period; `cpu.stat` có các thống kê như `nr_throttled` và `throttled_usec` để đánh giá throttling.

**Không đánh đồng `nr_throttled` với số request chậm**: đó là sự kiện quota của cgroup. Cần đặt nó trên cùng timeline với service latency, CPU utilization và GC events.

### 12.3. Log Container Support của HotSpot

~~~bash
java -Xlog:os+container=trace -jar app.jar
~~~

Trên Linux HotSpot hỗ trợ container detection, log giúp hiểu CPU quota, cgroup path, memory limits và các thông tin runtime đã quan sát. Mức `trace` khá chi tiết: dùng ở môi trường điều tra/test, không mặc định bật log nhiều trong production.

### 12.4. GC initialization logs

~~~bash
java -XX:+UseG1GC -Xlog:gc+init=info -jar app.jar
~~~

Kiểm tra:

~~~text
CPUs: ... total, ... available
Parallel Workers: ...
Concurrent Workers: ...
~~~

Log này cho biết cách GC cấu hình từ lúc khởi tạo. Để xem **thời lượng pause**, cần thêm GC logs theo workload, chẳng hạn `-Xlog:gc*=info` khi phù hợp.

### 12.5. JVM flags

~~~bash
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
~~~

Trên máy dùng HotSpot, có thể lọc các flag có tên `ActiveProcessorCount`, `UseContainerSupport` (Linux), `ParallelGCThreads`, `ConcGCThreads`. Các flag có thể có origin `default`, `ergonomic` hoặc `command line`. **Không coi origin=default là bằng chứng đã có bao nhiêu worker thực sự chạy trong từng pause**.

## 13. Cấu hình đang chạy có thể thay đổi động không?

CPU quota/cpuset có thể bị orchestrator điều chỉnh trong vòng đời container. `Runtime.availableProcessors()` có thể phản ánh thay đổi theo runtime/OS, nhưng các thread pool đã được khởi tạo **không nhất thiết tái tính parallelism** chỉ vì CPU limit đổi.

Ví dụ:

- `ForkJoinPool.commonPool()` là singleton, được cấu hình khi khởi tạo. Đừng mong thay `-D...common.parallelism` sau đó hay đổi quota sẽ tái cấu hình pool đã tạo.
- GC worker ergonomics thường được quyết định ở startup/khởi tạo collector, không thể giả định mọi tham số được auto-resize liên tục.
- Một số framework pool tạo ra lúc ứng dụng startup và giữ nguyên config cho đến khi restart hoặc cấu hình lại có chủ đích.
- Một pool được **tạo mới** sau khi CPU count thay đổi có thể nhìn thấy khác, nhưng không nên dùng điều này làm hợp đồng chung cho mọi JVM.

**Khuyến nghị vận hành:** nếu thay CPU limits đáng kể và ứng dụng phụ thuộc default executor sizing, **khởi động lại có kiểm soát** hoặc điều chỉnh pools qua cơ chế supported của framework, rồi xác minh metrics. Không suy rằng thay Kubernetes `limits.cpu` sẽ lập tức đổi tất cả thread counts.

## 14. Cách benchmark đúng cho GC và executors dưới CPU limit

Một phép đo có ý nghĩa cần cả ba lớp: **JVM config**, **cgroup enforcement**, **application latency**.

### 14.1. Thiết kế benchmark

1. Chọn workload đại diện: CPU-bound, request I/O hay hỗn hợp; không lẫn mục tiêu.
2. Chốt JDK build, GC, heap, CPU/memory limits, số container replicas và container runtime.
3. Ghi lại `availableProcessors`, Parallel/Concurrent GC worker counts và executor parallelism tại startup.
4. Chạy một baseline không override nếu JVM nhận diện đúng quota.
5. Thử các mức `ActiveProcessorCount` hoặc explicit pool size **có chủ đích**, từng thay đổi một.
6. Có thời gian warmup đủ để tránh chỉ đo compilation/startup.
7. Thu throughput, request latency p50/p95/p99, error rate, timeout và queue metrics.
8. Thu GC pause time/frequency, allocation rate, concurrent GC CPU, CPU throttling stats.
9. Lặp nhiều lần hoặc đổi thứ tự profile để giảm nhiễu cache/host scheduling.
10. Chỉ chọn config mới nếu cả hiệu năng lẫn tính ổn định dưới tải thật được cải thiện.

### 14.2. Vì sao chỉ nhìn CPU utilization là chưa đủ?

CPU 100% có thể do công việc hữu ích hoặc do oversubscription/throttling. Một container “CPU ít được dùng” cũng có thể đang nghẽn network hoặc lock. Muốn chứng minh sizing hiệu quả phải xem throughput và tail latency kết hợp CPU stats.

### 14.3. Đừng biến số đo chạy trên Windows thành kết luận Linux quota

Bảng trong bài từ JDK24 trên Windows với `ActiveProcessorCount` chứng minh **đường heuristic**. Nó không đo Linux CFS throttling, `cpu.max` hay throughput của một pod Kubernetes thật. Nếu mục tiêu là capacity planning, chạy benchmark **trong đúng container runtime của sản phẩm**.

## 15. Giải pháp cho những triệu chứng thường gặp

| Triệu chứng | Điều có thể đang xảy ra | Hướng kiểm tra |
| --- | --- | --- |
| Container limit 2 CPU nhưng JVM in 32 | CPU detection chưa thấy quota, chỉ có shares hoặc cấu hình/JDK khác | Cgroup `cpu.max`, affinity, `-Xlog:os+container`, JDK build |
| Container quota 1,5 mà Java in 2 | Quota được làm tròn lên thành active count nguyên | Xác minh quota/affinity; không suy năng lực CPU đúng 2 |
| `Parallel Workers` quá nhiều và `cpu.stat` throttling tăng | GC parallelism tranh CPU quota | GC logs, CPU throttle, thử ergonomics/override phù hợp |
| `Concurrent Workers` tiêu thụ CPU khi request đang bận | Concurrent GC tranh tài nguyên với mutator | Xem collector/heap/allocations, đo GC CPU/latency |
| Common pool chỉ còn parallelism 1 | JVM nhìn CPU thấp hoặc property riêng | `availableProcessors`, common.pool parallelism, flags |
| `CompletableFuture` latency thay sau nâng JDK25 | JDK 25 bỏ fallback tạo thread riêng khi common pool nhỏ | Review no-executor async, dùng dedicated executor cho blocking work |
| `newFixedThreadPool(16)` vẫn có 16 thread ở container 2 CPU | Pool size do code cấu hình, không tự nhận diện CPU | Sửa config của pool hoặc code |
| CPU request thấp nhưng pool không thu nhỏ | Shares/weight không còn được tính như quota | Đặt hard limit nếu phù hợp hoặc `ActiveProcessorCount` rõ |
| Tăng CPU limit nhưng pool cũ không tăng | Pool tạo một lần ở startup | Restart/reconfigure pool rồi đo |
| p99 cao nhưng GC logs ổn | Blocking/queue/network/lock/downstream bottleneck | Thread dumps, tracing, queue metrics, JFR |
| CPU=1 mà có hàng trăm OS threads | Blocking pools/cached pools/framework, không chỉ ForkJoin | Đếm thread theo nhóm, thread dump, backpressure |
| `-XX:-UseContainerSupport` lỗi trên Windows | Cờ là Linux-only | Chỉ dùng trong Linux HotSpot tương ứng |

Không tự kết luận từ một symptom duy nhất. Thay đổi executor/GC không đúng có thể khiến độ trễ, footprint hoặc throughput **tệ hơn**.

## 16. Các hiểu nhầm phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Container 2 CPU thì tiến trình Java tối đa 2 threads.” | Không. CPU quota giới hạn CPU time; JVM có thể tạo nhiều Java/native threads. |
| “`availableProcessors()` là số lõi vật lý của host.” | Không nhất thiết; đây là số processors JVM xem là khả dụng. |
| “Tất cả executor mặc định đều có đúng CPU threads.” | Không; chỉ những API có chính sách dùng CPU count. |
| “GC `ParallelGCThreads` luôn bằng CPU count.” | Phụ thuộc collector/JDK/heuristic/override, không có công thức cố định. |
| “`ConcGCThreads` chính là số thread đồng thời của ứng dụng.” | Không; là GC worker setting khi collector hỗ trợ. |
| “GC workers = OS thread count.” | Không; còn rất nhiều thread khác. |
| “CPU requests trong Kubernetes chính là CPU limits.” | Không; request và hard quota khác nhau. |
| “CPU shares luôn được JDK25 dùng để quyết định active processors.” | Không; shares bị bỏ khỏi phép tính mặc định từ JDK19. |
| “`ActiveProcessorCount=8` cấp thêm 8 CPU kernel cho container.” | Không; chỉ override heuristic VM. |
| “Đặt common.parallelism=8 sẽ đổi GC workers lên 8.” | Không; đó là thuộc tính riêng của ForkJoin common pool. |
| “`newFixedThreadPool(3)` tự giảm thành 1 khi quota=1.” | Không; số 3 là tham số tường minh. |
| “`newCachedThreadPool()` có upper bound bằng CPU count.” | Không có quy tắc fixed upper bound như thế. |
| “Parallel streams luôn nhanh hơn sequential.” | Không; overhead, CPU pressure và task size quyết định. |
| “`CompletableFuture` luôn tạo thread mới khi common pool=1.” | Không còn đúng trên JDK25+, đã đổi sang common pool. |
| “Virtual threads nghĩa là CPU count không quan trọng nữa.” | CPU vẫn giới hạn runnable work và carrier scheduler. |
| “Chỉnh CPU limit runtime làm mọi pool tự resize.” | Không bảo đảm; nhiều pool được tạo một lần. |
| “Số Parallel Workers trong GC log là tổng thread active của tiến trình.” | Không; chỉ là thông tin worker GC. |
| “Tăng worker GC luôn giảm pause.” | Không trong container bị throttle hoặc workload quá nhỏ. |
| “Không thấy throttling thì GC chắc chắn không ảnh hưởng p99.” | Không; GC pause có thể xuất hiện dù không có CFS throttle. |
| “Chạy nhanh hơn ở máy local là đủ để quyết định production limits.” | Không; phải đo trong runtime/container thật. |

## 17. Bài tập có lời giải

### Bài 1 — Phân biệt host CPU và container CPU

**Hỏi:** Host có 32 CPU, pod có CPU quota 2. `Runtime.availableProcessors()` nên dùng 32 hay 2 trong HotSpot nhận diện cgroup đúng?

**Đáp án:** Thường là 2 CPU hiệu dụng (nếu affinity/cpuset không thấp hơn), không phải mặc nhiên 32 CPU host. Kiểm tra trên runtime thật.

### Bài 2 — Quota phân số

**Hỏi:** `cpu.max = 150000 100000` có ý nghĩa gì và CPU hiệu dụng thường bao nhiêu?

**Đáp án:** Quota là 1,5 CPU. HotSpot có thể làm tròn lên thành 2 active processors, còn quota kernel vẫn là 1,5 CPU theo trung bình period. Cần xem affinity và JDK.

### Bài 3 — GC worker sizing

**Hỏi:** `ParallelGCThreads` và `ConcGCThreads` có luôn bằng số CPU không?

**Đáp án:** Không. Chúng phụ thuộc collector, heuristic và override; phải đọc giá trị runtime. Trong **JDK24 G1 thử nghiệm**, 8 CPU cho ParallelWorkers 8 và ConcurrentWorkers 2, nhưng không khẳng định đúng ở mọi collector/JDK.

### Bài 4 — Common pool

**Hỏi:** Với `ActiveProcessorCount=4` và không custom common pool, common parallelism trên JDK24 thử nghiệm là bao nhiêu?

**Đáp án:** 3. Một `new ForkJoinPool()` riêng có parallelism 4.

### Bài 5 — Work stealing

**Hỏi:** `Executors.newWorkStealingPool()` không tham số dùng CPU count thế nào?

**Đáp án:** Nó dùng processors khả dụng làm target parallelism. Trong thử nghiệm 4 CPU, target là 4.

### Bài 6 — Fixed pool

**Hỏi:** Container 1 CPU, code gọi `Executors.newFixedThreadPool(3)`. Số 3 có tự giảm thành 1 không?

**Đáp án:** Không; số thread mục tiêu do code chỉ định, không tự theo VM processor count.

### Bài 7 — Cached pool

**Hỏi:** `Executors.newCachedThreadPool()` có tự chỉ tạo `N` thread khi CPU=N không?

**Đáp án:** Không. Nó có thể tạo nhiều thread theo nhu cầu task. Cần giới hạn công việc và quản lý queue/backpressure theo ứng dụng.

### Bài 8 — CPU shares

**Hỏi:** Một container chỉ có CPU shares tương ứng 2 CPU nhưng không có hard quota. Trên JDK25, JVM chắc chắn in `availableProcessors()==2` không?

**Đáp án:** Không. JDK mới không coi shares như quota khi tự tính CPU count; có thể thấy host/affinity count. Xác định policy rõ hoặc cấu hình `ActiveProcessorCount` khi cần.

### Bài 9 — Override CPU

**Hỏi:** `-XX:ActiveProcessorCount=2` có làm kernel cgroup tự đặt hard limit 2 CPU không?

**Đáp án:** Không. Nó điều chỉnh số CPU hiệu dụng mà VM dùng cho heuristics. Hạn mức kernel phải cấu hình riêng qua container runtime/orchestrator.

### Bài 10 — Common pool override

**Hỏi:** `ActiveProcessorCount=1` và `-Djava.util.concurrent.ForkJoinPool.common.parallelism=4` cho ra gì trên JDK24?

**Đáp án:** `availableProcessors=1`, `commonPool parallelism=4`, `new ForkJoinPool parallelism=1`. Common pool property khác với CPU VM override.

### Bài 11 — JDK25 async behavior

**Hỏi:** Vì sao async tasks trên container CPU1 có thể khác giữa JDK24 và JDK25?

**Đáp án:** JDK25 thay đổi `CompletableFuture` không executor: luôn dùng common pool kể cả parallelism nhỏ hơn 2, không còn fallback tạo thread mới như JDK trước. Nên cấp explicit executor cho các blocking tasks.

### Bài 12 — CPU quota khi có request

**Hỏi:** Pod có `requests.cpu=500m` và `limits.cpu=1500m`. Java có chắc in 0,5 không?

**Đáp án:** Không. JVM thường dựa hard quota 1,5 CPU (sau đó quy về integer count và chịu affinity) chứ không phải trực tiếp lấy request 0,5 làm processor count.

### Bài 13 — Thay CPU limit lúc runtime

**Hỏi:** Khi tăng limit từ 2 lên 8, common pool đã tạo sẽ tự từ parallelism 1 thành 7 không?

**Đáp án:** Không nên giả định. Common pool thường khởi tạo một lần và giữ config. Restart hoặc dùng cấu hình pool có lifecycle rõ rồi đo.

### Bài 14 — Multi-framework pools

**Hỏi:** Trong cùng JVM có Netty, DB pool, scheduler, ForkJoin và GC. CPU limit 2 có làm mọi thứ chỉ có 2 thread?

**Đáp án:** Không. Mỗi subsystem có policy khác; phải xem metrics/config thực tế và tổng số runnable tasks, không chỉ số thread tồn tại.

### Bài 15 — Throttling

**Hỏi:** Quota 1,5 CPU, JVM chọn 2 workers, `cpu.stat` tăng `nr_throttled`. Có thể làm gì?

**Đáp án:** Kiểm tra workload/CPU budget, benchmark GC/application workers, cân nhắc quota/size/ActiveProcessorCount nhưng không giảm bừa. Xem đồng thời throughput, p99, GC pauses và throttled time.

### Bài 16 — Benchmark

**Hỏi:** Một lần chạy local với `ActiveProcessorCount=4` nhanh hơn không flag thì đã đủ chứng minh production nên đặt 4 CPU chưa?

**Đáp án:** Không. Local test chỉ chứng minh một tình huống; cần benchmark trong container thật với quota/affinity, CPU contention, heap, GC và request workload.

### Bài 17 — Virtual threads

**Hỏi:** Dùng virtual threads JDK21+ có bỏ qua CPU quota không?

**Đáp án:** Không. Virtual threads giảm chi phí chờ I/O so với nhiều platform threads, nhưng runnable CPU-bound work vẫn bị giới hạn bởi CPU time và carrier scheduler.

### Bài 18 — JDK compatibility

**Hỏi:** Có nên dùng `-XX:-UseContainerSupport` trên Windows JDK24 trong hướng dẫn chạy thử?

**Đáp án:** Không; cờ này là Linux-only, và JVM Windows thử nghiệm đã báo không nhận diện option. `ActiveProcessorCount` vẫn hoạt động trên Windows và phù hợp để kiểm thử heuristic CPU.

## 18. Checklist code review và vận hành

- [ ] Biết chính xác JDK vendor/build, JVM implementation và container runtime đang dùng chưa?
- [ ] Đã kiểm tra `Runtime.getRuntime().availableProcessors()` **trong pod/container thật** chưa?
- [ ] Đã phân biệt CPU quota, cpuset/affinity và CPU shares/weight chưa?
- [ ] Có hiểu CPU requests và CPU limits không đồng nghĩa trong Kubernetes không?
- [ ] Có xem `cpu.max`, `cpuset.cpus.effective` và `cpu.stat` khi xử lý Linux cgroup v2 không?
- [ ] Có biết `UseContainerSupport` là Linux-only và mặc định enabled trên HotSpot hiện hành không?
- [ ] Có tránh cách tuning CPU shares legacy không phù hợp JDK19+/JDK21+ không?
- [ ] Có kiểm tra flag `-XX:ActiveProcessorCount` được truyền hay không không?
- [ ] Có hiểu `ActiveProcessorCount` chỉ đổi heuristic JVM, không tự đổi kernel quota không?
- [ ] Có đọc `-Xlog:gc+init=info` để biết G1 Parallel/Concurrent Workers thực sự không?
- [ ] Có tránh mặc định G1/Parallel/ZGC/Shenandoah dùng cùng công thức worker count không?
- [ ] Có phân biệt số worker GC cấu hình với số thread thực thi và số CPU vật lý không?
- [ ] Có đo GC pauses và CPU throttling đồng thời không?
- [ ] Có đo commonPool parallelism thay vì đoán bằng CPU count không?
- [ ] Có phân biệt commonPool, private ForkJoinPool và newWorkStealingPool không?
- [ ] Có biết fixed/cached/scheduled executors có sizing khác nhau không?
- [ ] Với `CompletableFuture` async, có biết thay đổi JDK25 khi common pool parallelism thấp không?
- [ ] Với I/O blocking, có dùng explicit executor/backpressure khi cần không?
- [ ] Với ứng dụng virtual-thread JDK21+, có phân biệt số task, carrier parallelism và CPU quota không?
- [ ] Có kiểm soát thread pool của HTTP/framework/database riêng, không áp đặt một công thức JVM chung không?
- [ ] Nếu đổi limits khi app đang chạy, có xác minh pool đã được cập nhật hoặc restart không?
- [ ] Có benchmark workload thật, p50/p95/p99, throughput, GC, CPU throttling, queue metrics không?
- [ ] Có tránh kết luận chỉ từ một CPU override demo chạy trên Windows không?
- [ ] Có giữ cấu hình thread pool như một quyết định có thể đo lường/rollback không?

## 19. Nguồn chính thức và tài liệu hiện hành

- [JDK 25 `java` launcher — `ActiveProcessorCount` và `UseContainerSupport`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): CPU override cho GC/ForkJoin, Linux container awareness enabled by default, unified log `os+container`.
- [JDK 25 `java` launcher — `ParallelGCThreads` và `ConcGCThreads`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): số GC worker mặc định dựa CPU/collector và các cờ được hỗ trợ.
- [Java SE 25 API — `Runtime.availableProcessors()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): lấy số processor mà JVM cho là khả dụng.
- [Java SE 25 API — `ForkJoinPool`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool, constructor không tham số, parallelism và thread-management.
- [Java SE 25 API — `Executors`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html): `newWorkStealingPool()` dùng processor count, so với fixed/cached/scheduled pools.
- [Java SE 25 API — `CompletableFuture`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html): async operations và default executor.
- [JDK 25 Release Notes — JDK-8319447](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): `CompletableFuture`/`SubmissionPublisher` async không executor luôn dùng common pool, kể cả parallelism thấp.
- [JDK 19 Release Notes — JDK-8281181](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html): thay đổi mặc định bỏ CPU shares khỏi phép tính CPU hiệu dụng.
- [Linux Kernel cgroup v2 Documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.stat`, `cpu.weight`, `cpuset.cpus.effective`.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): scheduler/carrier threads, phân biệt virtual task concurrency và CPU resources.
- [Java SE 17 API — `ForkJoinPool`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): các API demo tồn tại trong `--release 17`.
- [Java SE 17 API — `Executors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): factory APIs dùng trong demo Java 17.

**Kết luận:** Java container awareness thay đổi **CPU count mà HotSpot dùng làm đầu vào cho việc tự động định cỡ GC và các executor phù hợp**. Với CPU quota/affinity được nhận diện đúng, GC worker count và `ForkJoinPool` default thường thích ứng hơn với container; nhưng **không phải executor nào cũng tự co giãn**, và CPU shares không còn tương đương quota ở JDK mới. `ActiveProcessorCount` có thể ghi đè heuristic khi có lý do vận hành rõ, nhưng không tạo thêm CPU vật lý và không thay kernel quota. Khi nâng JDK, đặc biệt từ JDK24 lên JDK25, kiểm tra `CompletableFuture` no-executor async ở common pool thấp. **Đo CPU throttling, GC pauses, executor queues và p99 trong container thật** trước khi chọn số worker cuối cùng.