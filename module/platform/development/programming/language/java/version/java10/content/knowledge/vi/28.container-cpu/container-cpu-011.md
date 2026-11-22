# Đánh giá giới hạn CPU cùng độ trễ, thông lượng và hàng đợi trong container Java (Java 10+)

## 1. Mục tiêu và kết luận chính

Khi chạy một ứng dụng Java trong Docker, Kubernetes hoặc môi trường container Linux dùng **cgroups**, số CPU mà JVM **nhìn thấy**, lượng **CPU time được Linux cho phép sử dụng**, tốc độ **request đi vào ứng dụng**, khả năng **xử lý request** và độ dài **hàng đợi** là những đại lượng **khác nhau**.

Từ **Java 10**, HotSpot hỗ trợ nhận biết giới hạn tài nguyên container (JDK-8146115). Các JDK hiện hành tiếp tục có **`-XX:+UseContainerSupport`**, `Runtime.getRuntime().availableProcessors()` và công cụ logging để quan sát cấu hình này. Nhưng **container awareness không có nghĩa Java tự đảm bảo latency thấp hoặc tự giới hạn hàng đợi đúng với năng lực CPU**.

Một chuỗi nhân quả thường gặp khi workload bị CPU giới hạn:

~~~text
CPU quota / CPU affinity / CPU contention
                |
                v
CPU time thực sự có thể dùng cho container
                |
                v
Năng lực phục vụ request (service capacity)
                |
         arrival rate tăng
                |
                v
CPU saturation / throttling / scheduling wait
                |
                v
Thời gian thực thi + thời gian chờ tăng
                |
                v
Hàng đợi, in-flight requests, timeouts tăng
                |
                v
p95/p99 latency xấu đi, goodput không tăng tương ứng
~~~

**Đừng dùng một số duy nhất, ví dụ `availableProcessors() == 2` hoặc CPU utilization 70%, để kết luận hệ thống xử lý được bao nhiêu request/giây.** Cần kết hợp **quota thực tế, demand CPU trên một request, throttling, throughput, latency phân vị và queue depth** qua phép đo có tải.

## 2. Bốn thứ rất dễ nhầm: requests, limits, cpuset và active processors

### 2.1. CPU request trong Kubernetes

Ví dụ một container:

~~~yaml
resources:
  requests:
    cpu: "500m"
  limits:
    cpu: "1500m"
~~~

- `500m` = **0,5 CPU** được khai báo dưới dạng **CPU request** phục vụ scheduler và cơ chế phân chia trọng số khi có tranh chấp.
- `1500m` = **1,5 CPU** là **CPU limit** nếu cluster/runtime thực thi bằng CFS bandwidth quota.
- Các giá trị này tính theo **CPU core-equivalent**, không phải số Java threads.
- CPU request **không bảo đảm container có riêng 0,5 core vật lý mọi thời điểm**; CPU limit **không tự khóa container vào đúng 1,5 core cố định**.

Ở Kubernetes Linux cấu hình thông thường, CPU limits được kubelet thực thi qua **CFS quota**. Một workload có thể chạy trên nhiều logical CPUs trong một khoảng ngắn rồi bị hạn chế CPU time trong chu kỳ quota.

### 2.2. CPU quota trong cgroups v2

Trên Linux cgroups v2, file `cpu.max` biểu diễn giới hạn CPU bandwidth theo hai giá trị:

~~~text
$MAX $PERIOD
~~~

Ví dụ:

~~~text
150000 100000
~~~

Nghĩa là nhóm được sử dụng tối đa **150.000 microseconds CPU time** trong mỗi chu kỳ **100.000 microseconds**. Đây là **1,5 CPU-equivalent** trung bình theo quota/period, không phải “một CPU rưỡi vật lý được đặt riêng”.

Công thức:

\[
\text{quota cores} = \frac{\text{quota time}}{\text{period time}}
\]

Với `150000/100000`, kết quả là **1,5**.

Nếu là:

~~~text
max 100000
~~~

thì **cgroup này không đặt CPU bandwidth cap tại `cpu.max`**, nhưng vẫn có thể bị giới hạn bởi cpuset, node contention hoặc **cgroup cha**. “Không có limit ở file này” **không bảo đảm CPU vô hạn**.

### 2.3. CPU affinity / cpuset

`cpuset.cpus.effective` và Linux CPU affinity quyết định **những logical CPUs nào** tiến trình được phép chạy trên đó. Ví dụ:

~~~text
0-3
~~~

biểu thị bốn logical CPU IDs được phép, nhưng nếu `cpu.max` đặt quota 1,5 thì **long-term CPU budget vẫn là 1,5 CPU-equivalent**, không phải 4 CPU-equivalent.

Phân biệt:

- **cpuset/affinity**: được phép chạy **ở đâu**.
- **quota/period**: có bao nhiêu **CPU time** trước khi phải chờ cấp tiếp.
- **request/weight**: ưu tiên tương đối khi **tranh chấp tài nguyên**.
- **CPU utilization**: thực tế dùng bao nhiêu, theo **định nghĩa mẫu số** của công cụ quan sát.

### 2.4. `Runtime.availableProcessors()`

Trong Java:

~~~java
int processors = Runtime.getRuntime().availableProcessors();
System.out.println(processors);
~~~

Đây là **số nguyên báo cáo cho JVM**, được dùng bởi một số heuristics khi chọn kích thước GC workers, ForkJoinPool hoặc thread pools mặc định. Nó **không trực tiếp biểu thị độ dài quota cgroup dưới dạng số thực**.

Ví dụ container có quota **1,5 CPU**: một HotSpot hiện hành có thể báo **2 active processors** do làm tròn và áp dụng affinity/cgroup rules. Con số 2 **không có nghĩa container được đảm bảo 2 CPU time liên tục**.

Bạn cũng có thể ép một giá trị cho JVM:

~~~bash
java -XX:ActiveProcessorCount=2 -jar app.jar
~~~

**`-XX:ActiveProcessorCount=2` không cấp thêm CPU cho container và cũng không áp quota cho Linux.** Nó chỉ override số processors mà HotSpot dùng/đưa ra cho những quyết định liên quan. Nếu container bị giới hạn 1,5 CPU, đặt flag bằng 4 cũng **không nâng limit** thành 4 CPU.

## 3. Điều gì còn áp dụng ở JDK hiện hành?

Bài này học trong bối cảnh **Java 10**, nhưng phải dùng những hiểu biết **vẫn đúng hiện nay**:

- Java 10 đưa container-awareness vào HotSpot, để lựa chọn tài nguyên phù hợp thay vì luôn dùng thông số host.
- Trên HotSpot Linux hiện đại, container support **được bật mặc định** nếu được hỗ trợ; `-XX:-UseContainerSupport` là cách tắt khi có chủ đích, **không nên dùng như cấu hình mặc định**.
- Trên hệ thống cgroups v2, đọc `cpu.max`, `cpu.stat`, `cpuset.cpus.effective` và `cpu.pressure` khi file/cgroup controller hỗ trợ.
- **Từ JDK 19**, HotSpot **không dùng `cpu.shares` mặc định để tính active processor count** nữa; CPU shares/weights là chỉ báo ưu tiên tương đối, **không phải hard CPU quota**. Không dựa vào hướng dẫn Java 10/11 cũ nói rằng CPU shares luôn biến thành giới hạn số CPU của JVM.
- JVM versions, cách đọc container metrics và các tunables có thể thay đổi giữa HotSpot releases và Linux cgroup versions; **kiểm tra JDK thực tế** trước khi giải thích số đo.

**Không gợi ý dùng flags deprecated để khôi phục cách diễn giải CPU shares cũ** chỉ nhằm “tương thích” nếu kiến trúc hiện tại không yêu cầu. Hãy định nghĩa rõ CPU request, limit và loại workload.

## 4. Ba phép đo trọng tâm: throughput, latency và queue

### 4.1. Throughput — tốc độ hoàn thành

**Throughput** là số công việc được xử lý xong trong một khoảng thời gian, ví dụ **request/giây (RPS)**, **message/giây** hoặc **batch/giây**.

\[
\text{throughput} = \frac{\text{số request hoàn thành}}{\text{thời gian đo (giây)}}
\]

Cần phân biệt:

- **Arrivals / offered load**: số request **đi vào**.
- **Completions**: số request xử lý **xong**.
- **Goodput**: số request **thành công, hợp lệ, đáp ứng tiêu chí nghiệp vụ** trong mỗi giây.
- **Rejected / failed / timed out**: có thể không được tính vào goodput dù vẫn xuất hiện trong các counters HTTP.

Một hệ thống có thể tiếp nhận **100 RPS**, thực sự hoàn thành **60 RPS**, còn **40 RPS đang đợi, thất bại hoặc bị từ chối**. Báo cáo “throughput 100 RPS” lúc ấy là dễ gây hiểu lầm nếu công cụ đang đo **arrivals**.

### 4.2. Latency — thời gian một request phải chờ

Một request có thể trải qua:

~~~text
queue wait → scheduling wait → service/CPU work → I/O wait → response
~~~

Đo các phân vị từ **phía client/load generator**:

- **p50**: độ trễ trung vị.
- **p95**: 95% quan sát không lớn hơn ngưỡng p95.
- **p99**: 99% quan sát không lớn hơn ngưỡng p99.

**p99 = 500 ms không có nghĩa mọi request đều dưới 500 ms.** Một số request vẫn có thể chậm hơn; các phân vị chỉ mô tả phân phối quan sát tại một cửa sổ đo nhất định.

Thông thường **p95/p99 tăng rất sớm khi queueing hoặc throttling xảy ra**, ngay cả khi p50 vẫn tương đối tốt.

### 4.3. Queue depth và queue wait

- **Queue depth**: có bao nhiêu công việc đang đợi trong executor, broker, socket accept queue hoặc hàng đợi nghiệp vụ.
- **Queue wait time**: thời gian từ lúc công việc vào queue đến lúc thực sự được worker bắt đầu xử lý.
- **In-flight**: số request đang ở trong hệ thống (bao gồm queue + đang xử lý, theo định nghĩa metric).
- **Queue capacity**: giới hạn số task đợi nếu queue có bound.

**Queue depth = 0 không tự chứng minh hệ thống đủ CPU**, vì request có thể đang xếp hàng **ở upstream**, chờ ở kernel, trong client hoặc đã bị từ chối trước khi vào queue.

Muốn đánh giá đúng, phải biết **queue nào** được đo và ranh giới công việc của nó.

## 5. Mô hình công suất CPU: giới hạn trên, không phải benchmark

Giả sử mỗi request CPU-bound thực sự cần trung bình `S_CPU` milliseconds CPU time và container có ngân sách `C` CPU-equivalent.

Một **giới hạn lý tưởng để tính nháp**:

\[
\text{capacity RPS (ideal)} \approx \frac{C \times 1000}{S_{\mathrm{CPU,ms}}}
\]

Ví dụ:

- CPU quota: **1,5 CPU**.
- CPU time cần cho một request: **30 ms**.
- Công suất lý tưởng: **1,5 × 1000 / 30 = 50 request/giây**.

Đây là **mô hình đơn giản**, giả định CPU time/request tương đối ổn định, không có nhiều overhead GC/JIT/context switching và đủ parallelism. **Không công bố “50 RPS” như SLA thực tế** nếu chưa load test.

### Trường hợp A — arrivals 40 RPS

\[
\rho = \frac{\lambda}{\mu} = \frac{40}{50} = 0.8
\]

- Nhu cầu tương đương **80% công suất lý tưởng**.
- Về mặt công suất trung bình, hệ thống có thể ổn định nếu phân phối tải và overhead cho phép.
- Nhưng vẫn có bursts, queueing và p99 spikes; **80% không đảm bảo p99 tốt**.

### Trường hợp B — arrivals 70 RPS

\[
\rho = \frac{70}{50} = 1.4
\]

- Nhu cầu là **140% công suất lý tưởng**.
- Nếu arrivals liên tục 70 RPS, công suất tối đa khoảng 50 RPS và **không drop/reject**, backlog có xu hướng tăng:
  
\[
\Delta Q \approx (70 - 50) \times t
\]

- Sau **10 giây**, backlog **xấp xỉ 200 requests** theo mô hình lý tưởng.
- Nếu queue có bound, hệ thống sẽ bắt đầu **từ chối, timeout hoặc áp backpressure** thay vì tăng hàng đợi vô hạn.

**Lưu ý kỹ thuật:** ở trường hợp quá tải kéo dài, hệ thống **không ở steady state**. Không dùng các công thức steady-state như Little's Law một cách vô điều kiện để đoán latency khi queue đang tăng mãi.

## 6. Little's Law và mối liên hệ giữa concurrency, latency và throughput

**Little's Law** là công cụ hữu ích để liên hệ số lượng công việc trung bình trong hệ thống, tốc độ hoàn thành và thời gian trung bình:

\[
L = \lambda W
\]

Ở điều kiện ổn định và cùng ranh giới đo:

- `L`: trung bình số request **in-flight**.
- `λ`: tốc độ request **đi qua hệ thống** (request/giây).
- `W`: **thời gian trung bình** một request ở trong hệ thống (giây).

Ví dụ tại trạng thái ổn định:

- Throughput: **40 RPS**.
- Mean response time: **0,1 giây (100 ms)**.

Khi đó:

\[
L = 40 \times 0.1 = 4
\]

Trung bình khoảng **4 request đang trong hệ thống**.

**Không thay W bằng p95 hoặc p99** rồi gọi đó là Little's Law chuẩn: công thức dùng **mean**, không phải phân vị. Cũng không dùng offered load 70 RPS như throughput ổn định khi server chỉ hoàn thành 50 RPS và queue ngày càng tăng.

### Vì sao hàng đợi làm latency xấu?

Khi arrivals gần bằng service capacity, những dao động ngắn trong thời gian phục vụ và bursts có thể khiến nhiều request phải đợi. Với workload thực, khi `ρ` tiến tới 1, **queue wait có thể tăng phi tuyến**; p95/p99 thường tăng mạnh trước khi throughput suy giảm rõ ràng.

Điều này giải thích hiện tượng thường gặp:

~~~text
Tăng offered load từ 30 → 40 → 50 → 70 RPS

Throughput completed: tăng dần rồi bắt đầu phẳng
Queue depth:         nhỏ rồi tăng nhanh
p95/p99 latency:     tăng rõ
Timeouts/rejections: có thể xuất hiện khi vượt năng lực
~~~

Đây là **mẫu hành vi định tính**, không phải số đo thực tế của một ứng dụng cụ thể.

## 7. CPU throttling: tại sao CPU chưa 100% vẫn có p99 tệ?

Trên Linux CFS, khi một cgroup đã dùng hết **quota CPU time** được cấp cho một **period**, kernel có thể **throttle** việc chạy thêm cho đến khi quota được làm mới.

Ví dụ với `cpu.max = 150000 100000`:

- Trong một chu kỳ 100 ms, container có tổng ngân sách 150 ms CPU time tính trên các CPUs đang chạy.
- Nhiều worker có thể tiêu dùng quota **đồng thời trên nhiều logical CPUs**, hết ngân sách sớm trong chu kỳ.
- Sau đó, các tasks có thể phải chờ quota tiếp theo. Với request latency-sensitive, phần chờ này làm tăng **scheduler wait** và **tail latency**.

**Điều này không giống CPU pinning.** Container có thể chạy ngắn hạn trên một số logical CPUs lớn hơn quota cores rồi bị throttled.

### Số liệu cần quan sát

Trên cgroups v2:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.pressure
~~~

**Các đường dẫn giả định** tiến trình nhìn thấy cgroup v2 files ở mount root thông thường. Trong namespace/container khác, mount path hoặc file hiện diện có thể khác; có thể xem thêm `/proc/self/cgroup` và mount configuration khi cần. **Không mở đường dẫn này trên Windows như thể đó là cgroup của một Linux container**.

Ví dụ nội dung `cpu.stat`:

~~~text
usage_usec 125000000
user_usec 100000000
system_usec 25000000
nr_periods 10000
nr_throttled 1500
throttled_usec 8000000
~~~

**Đây là số ví dụ giả định, không phải mẫu đo từ một cluster.**

Giải thích:

- `usage_usec`: CPU time đã sử dụng theo định nghĩa file.
- `user_usec` và `system_usec`: phân chia CPU user/kernel.
- `nr_periods`: số periods của bộ điều khiển CPU bandwidth.
- `nr_throttled`: số periods xảy ra throttling.
- `throttled_usec`: thời gian throttle tích lũy theo cơ chế kernel; đọc bằng **độ chênh theo khoảng đo**.

### Tính tỷ lệ periods bị throttled

Đo tại hai thời điểm `t0, t1`:

\[
\mathrm{throttledPeriodRatio}
=\frac{\Delta \mathrm{nr\_throttled}}
{\Delta \mathrm{nr\_periods}}
\]

Ví dụ trong 60 giây có **600 periods** và **120 periods bị throttled**:

~~~text
throttled-period ratio = 120 / 600 = 20%
~~~

**Không được báo “CPU throttled 20% thời gian”** chỉ từ phép chia này. Đây là tỷ lệ **periods có xảy ra throttling**, không phải phần trăm thời gian CPU bị ngừng hoặc phần trăm request chậm.

Tương tự, đừng đọc `throttled_usec` như thời gian chờ của **một request cụ thể**. Cần xem đặc tính kernel/cgroup, có thể có ảnh hưởng từ cgroup cha, và tương quan với latency metrics.

### CPU usage percentage cần mẫu số đúng

Một metric kiểu:

~~~text
rate(container_cpu_usage_seconds_total[5m])
~~~

thường thể hiện **CPU cores đang sử dụng** (CPU-seconds/second), không tự là phần trăm của quota. Để chuẩn hóa theo CPU limit, phải lấy CPU usage cores **chia cho quota cores**; với CPU request lại là mẫu số khác.

Không so trực tiếp “70% CPU” giữa hai dashboard nếu một bên là **% node**, bên kia là **% container limit**, bên khác là **% CPU request**.

## 8. Requests, limits và CPU pressure trong Kubernetes

Kubernetes thường dùng:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cpu-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: cpu-demo
  template:
    metadata:
      labels:
        app: cpu-demo
    spec:
      containers:
        - name: app
          image: example.invalid/java-app:demo
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1500m"
              memory: "1Gi"
~~~

**Đây là cấu hình minh họa**, sử dụng **image placeholder không có thật**; không áp dụng nguyên file để deploy. Những giá trị CPU chỉ minh họa:

- **Request 500m** giúp scheduler tính tài nguyên và định hướng weight/shares.
- **Limit 1500m** tạo giới hạn CPU bandwidth nếu được enforcement.
- **Replica count 2** có thể phân phối tổng lưu lượng, nhưng cân bằng tải và năng lực backend vẫn quyết định hiệu quả.

Khi node có tranh chấp CPU, request có thể ảnh hưởng **ưu tiên tương đối**, còn limit là **trần**. CPU usage thấp hơn limit nhưng latency cao **cũng có thể do I/O, locks, GC, upstream, network hoặc queueing**, không phải lúc nào cũng do CPU throttling.

### Kiểm tra cấu hình trên cluster

~~~bash
kubectl describe pod POD_NAME
kubectl top pod POD_NAME --containers
~~~

Thay `POD_NAME` bằng pod cần kiểm tra. `kubectl top` cho metrics tại một thời điểm (nếu có Metrics Server), **không thay thế** time-series từ Prometheus/JFR/tracing.

### Khi dùng HPA

CPU-based HPA thường tính utilization dựa trên **CPU requests**, không phải giới hạn CPU limit. Nếu CPU request cấu hình thấp bất thường, HPA có thể thấy utilization cao; nếu thiếu request ở container liên quan, phép tính scaling theo CPU có thể không hoạt động như mong đợi. Vì vậy không dùng HPA target như chứng cứ duy nhất rằng container còn đủ năng lực phục vụ latency SLO.

**Scale-out** có thể tăng tổng capacity khi workload phân tán và phụ thuộc downstream cho phép. Nhưng nếu bottleneck nằm ở **một database chung**, tăng replicas không đảm bảo giảm latency.

## 9. JVM container awareness và kích thước thread pools

JVM có thể sử dụng số processors hiệu dụng để chọn:

- Số worker GC theo mặc định.
- Một số heuristics của JIT compiler.
- `ForkJoinPool.commonPool()` parallelism.
- Thread pool hoặc thư viện tự thiết kế theo `availableProcessors()`.

Ví dụ:

~~~java
int cpuCount = Runtime.getRuntime().availableProcessors();
int workers = Math.max(1, cpuCount);
~~~

Đây là **mảnh mã minh họa**, không nên áp dụng mù quáng để tạo pool cho mọi workload.

### `ActiveProcessorCount` không thay CPU quota

~~~bash
java -XX:ActiveProcessorCount=2 -jar app.jar
~~~

Flag có thể làm `Runtime.availableProcessors()` in ra 2 và thay đổi cách HotSpot chọn thread counts. Nhưng nó **không sửa `cpu.max`**, không cấp thêm CPU time từ kernel, không bảo đảm có hai physical cores riêng.

Ngược lại, nếu container có quota 1,5 CPU và HotSpot báo 2, điều đó **không chắc là bug**. JVM báo **một số nguyên dùng cho heuristics**; quota là ngân sách **số thực theo thời gian**.

### CPU-bound pool

Với tác vụ gần như chỉ tính toán CPU, quá nhiều platform threads thường **không tăng throughput** qua mức CPU quota, thậm chí tăng context switches, bộ nhớ stack và scheduler overhead.

### I/O-bound pool

Nếu task chủ yếu đợi I/O, số concurrency phù hợp có thể **lớn hơn CPU count**. Nhưng vẫn phải giới hạn nguồn lực downstream (DB connections, sockets), và đặc biệt phải theo dõi **queueing và backpressure**.

### Virtual threads

Java 21 có **virtual threads**, hữu ích với nhiều tác vụ chờ I/O. Nhưng **virtual threads không tạo thêm CPU quota** và không thay đổi công suất CPU-bound tối đa. Nếu hàng nghìn virtual threads cùng chạy tính toán CPU-bound dưới quota nhỏ, contention và latency vẫn có thể xấu.

## 10. Hàng đợi: nơi CPU bottleneck biến thành độ trễ

Một sơ đồ request pipeline:

~~~text
Client → Load Balancer → HTTP server → Executor queue → Worker CPU
                               |                 |
                             timeout           throttle
                               |                 |
                               +----> response / error
~~~

Trong nhiều hệ thống Java, **executor queue** là nơi có thể quan sát rõ áp lực.

Với `ThreadPoolExecutor`:

- `corePoolSize`: số worker lõi.
- `maximumPoolSize`: trần worker theo chính sách pool.
- `BlockingQueue<Runnable>`: nơi giữ những tasks đang chờ.
- `RejectedExecutionHandler`: xử lý khi bị từ chối do pool shutdown hoặc bão hòa.
- `getQueue().size()`: độ dài queue hiện tại, **snapshot** chứ không phải lịch sử/percentile.

### Unbounded queue dễ giấu quá tải

`new LinkedBlockingQueue<>()` không có capacity cụ thể có thể nhận rất nhiều tasks. Với core threads bận, queue tăng thay vì tự mở rộng tới `maximumPoolSize` theo cách nhiều người tưởng.

Javadoc `ThreadPoolExecutor` nêu rõ: **unbounded queue khiến `maximumPoolSize` gần như không có tác dụng** khi các core workers luôn bận.

Hệ quả:

- Thông lượng xử lý không tự tăng.
- Latency tăng vì tasks chờ.
- Heap retention tăng theo độ dài queue.
- Những request đã timeout phía client có thể vẫn tiêu tốn tài nguyên để xử lý về sau nếu không cancel đúng.

### Bounded queue + rejection + backpressure

Một `ArrayBlockingQueue<>(N)` tạo giới hạn cho số tasks đợi. Khi đầy và pool không thể thêm worker:

- `AbortPolicy` ném `RejectedExecutionException`.
- `CallerRunsPolicy` có thể cho caller thực thi task, tạo hiệu ứng làm chậm nguồn phát; nhưng cần cân nhắc nếu caller là event loop hoặc latency-sensitive.
- Các chính sách drop khác có thể gây mất công việc, **không được dùng vô điều kiện cho nhiệm vụ nghiệp vụ quan trọng**.

**Không có một queue size đúng cho mọi hệ thống.** Phải chọn theo arrival bursts, service-time variance, latency budget và khả năng làm lại/retry của client.

## 11. Chương trình Java 17+ minh họa mô hình công suất và hàng đợi có giới hạn

Chương trình này có **hai phần độc lập về mục đích**:

1. **Capacity model lý tưởng**: lấy quota 1,5 CPU, CPU time 30 ms/request để tính throughput và backlog dự kiến. Nó **không phải benchmark CPU thực tế**.
2. **Bounded queue test**: dùng một `ThreadPoolExecutor` có một worker và queue capacity hai tasks. Một `CountDownLatch` cố ý giữ worker để kiểm tra chắc chắn hàng đợi đầy và một request bị từ chối.

**Đặc biệt:** `-XX:ActiveProcessorCount=2` trong lệnh chạy chỉ giúp output CPU count **ổn định khi test trên JDK 24**; nó **không giả lập cgroup quota 1,5 CPU**. Quota 1,5 ở phần model là **input giả định**, không phải quota thật của máy.

Lưu thành **`CpuQuotaQueueDemo.java`**:

~~~java
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CpuQuotaQueueDemo {

    public static void main(String[] args)
            throws InterruptedException {

        System.out.println("activeProcessors="
                + Runtime.getRuntime().availableProcessors());

        // Mô hình công suất giả định; không đo CPU quota thực.
        double quotaCores = 1.5;
        double cpuMillisPerRequest = 30.0;
        double idealCapacity =
                quotaCores * 1000.0 / cpuMillisPerRequest;

        double lowArrival = 40.0;
        double highArrival = 70.0;

        System.out.printf(Locale.ROOT,
                "idealCapacityRps=%.1f%n", idealCapacity);
        System.out.printf(Locale.ROOT,
                "lowDemandRatio=%.0f%%%n",
                lowArrival / idealCapacity * 100.0);
        System.out.printf(Locale.ROOT,
                "highDemandRatio=%.0f%%%n",
                highArrival / idealCapacity * 100.0);
        System.out.printf(Locale.ROOT,
                "backlogGrowthRps=%.1f%n",
                highArrival - idealCapacity);
        System.out.printf(Locale.ROOT,
                "backlogAfter10s=%.0f%n",
                (highArrival - idealCapacity) * 10.0);
        System.out.printf(Locale.ROOT,
                "littleLawL=%.1f%n", lowArrival * 0.1);

        // Bài test queue độc lập với mô hình CPU ở trên.
        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy()
        );

        try {
            // Task đầu giữ worker bận cho đến khi main giải phóng.
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                    completed.incrementAndGet();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            workerStarted.await();

            // Worker đã bận; hai task tiếp theo nằm trong queue.
            pool.execute(completed::incrementAndGet);
            pool.execute(completed::incrementAndGet);

            System.out.println("queuedBeforeRelease="
                    + pool.getQueue().size());

            int rejected = 0;
            try {
                pool.execute(completed::incrementAndGet);
            } catch (RejectedExecutionException ex) {
                rejected++;
            }
            System.out.println("rejected=" + rejected);

            releaseWorker.countDown();
            pool.shutdown();

            boolean terminated =
                    pool.awaitTermination(10, TimeUnit.SECONDS);
            System.out.println("terminated=" + terminated);
            System.out.println("completed=" + completed.get());
        } finally {
            releaseWorker.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac CpuQuotaQueueDemo.java
java -XX:ActiveProcessorCount=2 CpuQuotaQueueDemo
~~~

**`stdout` đã được kiểm thử hai lần trên HotSpot JDK 24:**

~~~text
activeProcessors=2
idealCapacityRps=50.0
lowDemandRatio=80%
highDemandRatio=140%
backlogGrowthRps=20.0
backlogAfter10s=200
littleLawL=4.0
queuedBeforeRelease=2
rejected=1
terminated=true
completed=3
~~~

Giải thích:

1. `activeProcessors=2` đến từ flag JVM; **không phải bằng chứng container có hard quota 2 CPUs**.
2. `idealCapacityRps=50.0` = 1,5 × 1000 / 30, là **giới hạn lý tưởng CPU**.
3. `lowDemandRatio=80%` và `highDemandRatio=140%` so arrivals với công suất giả định.
4. `backlogGrowthRps=20.0` và `backlogAfter10s=200` chỉ đúng theo **mô hình overload liên tục, không drop/reject, capacity không đổi**.
5. `littleLawL=4.0` dùng 40 RPS và **mean latency 100 ms** trong **một ví dụ steady state riêng**.
6. `queuedBeforeRelease=2`: worker bị giữ bởi latch, hai tasks đợi trong queue có capacity 2.
7. `rejected=1`: lần gửi task thứ tư bị `AbortPolicy` từ chối.
8. `terminated=true`, `completed=3`: sau khi giải phóng worker, ba task đã được nhận chạy xong và pool tắt trong thời hạn của thí nghiệm.

**Không được diễn giải phần queue test như phép đo CPU throttling.** Ở đây task đầu chờ latch để tạo trạng thái queue xác định, không phải “đang tiêu thụ CPU thật”. Muốn đo CPU giới hạn và tail latency thực tế cần load generator, container cấu hình quota và metrics theo thời gian.

### Nếu không có `ActiveProcessorCount`

Chạy:

~~~bash
java CpuQuotaQueueDemo
~~~

Dòng `activeProcessors=...` sẽ phụ thuộc JVM, OS affinity/cgroup và runtime configuration. Các dòng khác của model/queue test vẫn nhằm có kết quả xác định, nhưng không dùng số active processor đó làm phép đo quota thật.

## 12. Load test đúng để thấy tác động quota lên latency/throughput

Một thí nghiệm hiệu quả cần **nhiều mức offered load** và **nhiều mức CPU limit**.

### Giữ những gì cố định?

- **Cùng JDK build**, GC và các thông số quan trọng.
- Cùng version ứng dụng, classpath, dependency.
- Cùng máy/node class, network route và downstream.
- Cùng payload mix, tỷ lệ read/write, dữ liệu và tỷ lệ cache hit.
- Cùng cách warm-up để JIT, caches và connection pools đã vào trạng thái đại diện.
- Dùng load generator độc lập, đủ mạnh để nó **không** là bottleneck.

### Thay đổi tham số nào?

Một ma trận thí nghiệm gợi ý:

| Nhóm thử | CPU limit (ví dụ) | Offered load | Quan sát |
| --- | --- | --- | --- |
| A | 500m | Tăng dần từ thấp lên cao | Ngưỡng throughput phẳng và bắt đầu throttling |
| B | 1000m | Cùng pattern tải | Chênh lệch throughput/p95/p99/queue |
| C | 1500m | Cùng pattern tải | Có cải thiện tuyến tính hoặc giới hạn khác? |
| D | 2000m | Cùng pattern tải | CPU không còn là bottleneck? |

**Đây là kế hoạch minh họa, không phải báo cáo kết quả đo.** Tại mỗi cấu hình, nên chạy đủ lâu để ghi nhận giai đoạn ổn định và giai đoạn overload, lặp lại thí nghiệm để tránh kết luận từ một lần chạy.

### Các bước nên thực hiện

1. **Baseline**: kiểm tra CPU requests/limits, JVM active processors, container cgroup, memory và GC.
2. **Warm-up**: chạy một khoảng đủ để giảm nhiễu class loading/JIT chưa ổn định.
3. **Load step**: tăng offered load theo nấc, giữ mỗi nấc đủ lâu.
4. **Measure**: ghi arrivals, completions, goodput, errors, timeouts, p50/p95/p99, queue depth/wait, in-flight, active threads, CPU usage, throttling và GC.
5. **Find knee**: điểm throughput bắt đầu phẳng trong khi tail latency/queue tăng.
6. **Overload short test**: kiểm tra queue bounds, 429/503, timeout, retry, circuit breaker; không để hệ thống mất dữ liệu hay sập database.
7. **Recovery**: giảm tải và quan sát queue có rút, latency có phục hồi trong SLO hay không.
8. **Compare**: lặp với các CPU limits và worker settings khác, giữ môi trường tương đương.

**Không nhất thiết phải đẩy production tới khi sập** để tìm saturation. Dùng staging hoặc load test có kiểm soát; giới hạn mức quá tải và đặt điều kiện dừng.

## 13. Open-loop, closed-loop và coordinated omission

Hai cách sinh tải thường thấy:

**Closed-loop**: một client gửi request mới **sau khi request trước hoàn thành**, với một lượng client threads/concurrency cố định.

- Dễ thực hiện.
- Nhưng khi server chậm, tốc độ gửi **tự giảm**.
- Có thể **che giấu độ trễ tail** vì load generator ngừng gửi khi đang đợi.

**Open-loop / constant arrival rate**: phát request theo một lịch arrivals tương đối độc lập với thời gian trả lời server.

- Hữu ích để thấy chuyện gì xảy ra khi người dùng vẫn tiếp tục gửi **70 RPS** trong khi server chỉ xử lý được khoảng **50 RPS**.
- Cần đủ concurrency phía client để không tự nghẽn.
- Đo timeout, queueing và **coordinated omission** cẩn thận.

**Coordinated omission** xảy ra khi công cụ đo bỏ sót những khoảng thời gian hệ thống chậm vì nó không phát thêm công việc trong lúc đang đợi. Kết quả latency có thể đẹp hơn thực tế của offered load.

Khi đánh giá **p95/p99 dưới CPU throttling**, cần ghi rõ load generation model và đo từ phía client/edge để không bỏ sót tác động của backpressure, timeout và queue trước server.

## 14. Đo CPU time/request: vì sao quan trọng?

Công thức công suất CPU ở phần 5 chỉ có ích khi biết `S_CPU`.

Cần phân biệt:

- **Wall-clock response time**: ví dụ 100 ms, có thể gồm 30 ms CPU và 70 ms chờ I/O/queue.
- **CPU time**: số mili giây CPU thực tế mà hệ thống tiêu thụ cho request.
- **CPU utilization**: tổng CPU time được dùng trên một khoảng thời gian.

Nếu lấy 100 ms wall-clock để thay vào `S_CPU` cho workload I/O-bound, công suất dự đoán có thể **bị đánh giá thấp nghiêm trọng**. Ngược lại, nếu bỏ qua CPU GC, logging, encryption, serialization hoặc downstream processing trong chính container, ước tính công suất có thể quá lạc quan.

### Cách đo thực tế

- APM distributed tracing để phân tách thời gian ở queue, app và downstream.
- JFR / profiler theo khả năng môi trường để tìm CPU hotspots, allocation và GC.
- Process/container CPU usage theo thời gian, chia theo số request hoàn thành làm **ước lượng CPU seconds/request** khi steady state và không có nhiều background jobs.
- CPU profiles cho code paths quan trọng, đo cả serialize/parse, TLS hoặc compression nếu làm trong process.

**Không dùng một sample ngắn để kết luận chính xác CPU time/request** khi hệ thống đang warm up, có background jobs hoặc nhiều class công việc với demand rất khác nhau.

## 15. Throttling, queueing và GC: tách nguyên nhân

Khi p99 tăng, có thể có nhiều đường nguyên nhân:

~~~text
(a) CPU quota → throttling → worker chờ CPU → queue wait ↑
(b) Request surge → queue depth ↑ → timeout ↑ dù không throttle
(c) GC pause → worker bị dừng → latency ↑
(d) DB/network slowdown → I/O wait ↑ → queue/in-flight ↑
(e) Lock contention → blocked threads ↑ → throughput giảm
(f) Retries storm → offered load tăng → hệ thống càng quá tải
~~~

**Cách đối chiếu metrics:**

| Tín hiệu | Hướng giải thích |
| --- | --- |
| CPU usage gần quota + throttling tăng + p99 tăng | CPU budget/parallel bursts có thể là bottleneck |
| CPU thấp + queue tăng + DB latency cao | Có thể bị nghẽn downstream/connection pool |
| GC pause trùng p99 spikes | Điều tra allocation/heap/GC |
| Queue tăng và throughput phẳng | Service capacity đã tiệm cận trần hoặc worker bị kẹt |
| Requests được nhận vẫn tăng nhưng goodput giảm | Overload/retries/errors, cần backpressure |
| Rejections tăng, queue bounded | Hệ thống đã áp chính sách overload; kiểm tra client retry và SLO |
| CPU count JVM thay đổi sau flag nhưng throttling không giảm | Flag thay heuristics, không thay kernel quota |

**Không dùng tương quan đơn giản để khẳng định nguyên nhân duy nhất.** Ví dụ p99 cao và throttling tăng có thể cùng xuất hiện vì một đợt burst; cần xem timeline, CPU demand, queue và các dấu hiệu khác.

## 16. Thiết kế backpressure và timeouts

Khi arrivals vượt capacity, **hàng đợi vô hạn chỉ chuyển overload thành latency và memory pressure**.

Một hướng thiết kế có kiểm soát:

1. **Bounded concurrency**: giới hạn số work items đang thực thi song song theo CPU/IO budget và downstream capacity.
2. **Bounded queue**: giới hạn số request có thể đợi, tính theo latency budget.
3. **Request deadline**: không tiếp tục làm công việc đã hết giá trị sau timeout/cancellation.
4. **Rejection semantics**: trả 429/503 hoặc tín hiệu retry phù hợp, thay vì để client đợi vô hạn.
5. **Retry budgets**: tránh retry storm tự tạo arrivals mới khi service đang bão hòa.
6. **Load shedding**: ưu tiên công việc quan trọng nếu nghiệp vụ có phân loại.
7. **Autoscaling**: bổ sung capacity trước khi queue đã tăng quá lớn, nhưng đánh giá thời gian startup và giới hạn backend.

### Chọn kích thước queue theo latency budget

Giả sử server tối đa hoàn thành `µ = 50 RPS` và bạn muốn **thời gian đợi queue lý tưởng** không quá 200 ms. Một ước lượng thô:

\[
Q_\text{max} \approx \mu \times W_\text{queue,target}
= 50 \times 0.2 = 10
\]

Con số **10 tasks** là điểm khởi đầu để thảo luận, **không phải bảo đảm p99 dưới 200 ms**. Queue scheduling, nhiều worker, service-time distribution, prioritized tasks và bursts đều ảnh hưởng latency. Cần load test và đặt deadline thực.

Một queue lớn đôi khi giúp hấp thụ burst ngắn, nhưng nếu mức arrivals cao hơn capacity **liên tục**, queue lớn chỉ kéo dài thời gian trước khi failure và tăng response time.

## 17. HPA, scale-up và scale-out dưới CPU quota

**Scale-up CPU limit** có thể giảm throttling và tăng capacity CPU-bound khi node có tài nguyên, nhưng:

- Không vượt được bottleneck ở database/cache/network.
- Không tự sửa queue unbounded hoặc retry storm.
- Tăng limit có thể thay đổi JVM heuristics và GC thread counts trên một lần khởi động mới.
- Kết quả có thể không tuyến tính do memory bandwidth, lock contention và cache behavior.

**Scale-out replicas** có thể tăng tổng capacity nếu requests được phân phối và workloads phần lớn độc lập. Nhưng cần xem:

- Thời gian pod startup/warmup.
- Readiness checks và traffic routing.
- Downstream connection quotas.
- Shared database bottlenecks.
- Autoscaler cooldown và metric lag.
- HPA CPU target dựa trên requests; nên cân nhắc scale theo **queue length, in-flight, RPS per pod** hoặc latency có SLO phù hợp khi CPU không đại diện cho bottleneck.

**Cảnh báo:** P99 là metric đích quan trọng nhưng không phải lúc nào là tín hiệu trực tiếp lý tưởng để HPA scale nhanh. Sử dụng các chỉ báo dẫn đường ổn định hơn kết hợp đánh giá SLO có thể hữu ích.

## 18. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Container limit 1,5 CPU nghĩa là có riêng 1,5 core vật lý.” | Đó là CPU-time budget theo CFS period, không phải pinning. |
| “`availableProcessors()=2` nghĩa là được sử dụng đủ 2 CPUs liên tục.” | Đây là số nguyên JVM dùng cho heuristics, có thể làm tròn từ quota 1,5. |
| “`ActiveProcessorCount` tăng CPU quota.” | Flag chỉ override active processor count, không chỉnh cgroup. |
| “Request 500m và limit 1500m giống nhau.” | Request ảnh hưởng scheduling/weight; limit là hard cap khi được áp. |
| “CPU shares luôn là hard limit và luôn quyết định processor count trên JDK mới.” | Từ JDK 19 không còn mặc định tính active CPUs từ shares; weight không phải quota. |
| “CPU usage dưới 100% nghĩa là p99 chắc chắn tốt.” | Mẫu số có thể sai; bursts/throttling/IO/GC/queue vẫn gây latency. |
| “Throttle periods 20% nghĩa là 20% request bị chậm.” | Đó là tỷ lệ periods có throttling, không phải request percentile. |
| “Throughput bằng arrivals.” | Nếu backlog/rejections, completed goodput có thể thấp hơn. |
| “Tăng thread pool gấp đôi thì RPS gấp đôi.” | CPU quota không tăng; context-switching có thể làm xấu hơn. |
| “Unbounded queue giải quyết overload.” | Nó thường chỉ tích lũy latency và memory pressure. |
| “Khi `maximumPoolSize` lớn, ThreadPoolExecutor sẽ luôn tạo thêm threads.” | Với unbounded queue, khi core threads bận, task có thể được queue thay vì mở rộng. |
| “Little's Law dùng p99 latency.” | Công thức chuẩn dùng **mean W** ở steady state. |
| “Lambda > service capacity nhưng vẫn có steady state nếu queue vô hạn.” | Queue tăng không giới hạn; không ổn định nếu overload kéo dài. |
| “Virtual threads làm CPU quota biến mất.” | Chúng không tạo thêm CPU time. |
| “CPU cao là lỗi JVM.” | Có thể là workload bình thường; cần phân tích demand, SLO và pressure. |
| “Tăng CPU limit luôn cải thiện nếu DB là bottleneck.” | Không giải quyết được bottleneck downstream. |
| “Một benchmark 30 giây với cold JIT đủ cho mọi quyết định.” | Cần warm-up, tải đại diện, lặp lại và đo percentiles. |
| “Quá tải cứ tăng HPA là xong.” | Startup lag, requests/limits, queues và bottlenecks chung có thể cản trở. |

## 19. Bài tập tự kiểm tra

### Bài 1 — quota cores

`cpu.max` có giá trị `150000 100000`. Quota tương đương bao nhiêu CPU?

**Đáp án:** `150000 / 100000 = 1.5` CPU-equivalent.

### Bài 2 — cpuset và quota

Container được phép chạy trên logical CPUs `0-3` nhưng quota chỉ 1,5 CPU. Có được tiêu thụ liên tục 4 CPU-equivalent không?

**Đáp án:** Không theo quota; cpuset cho biết nơi chạy, quota giới hạn CPU time tổng.

### Bài 3 — CPU request

`requests.cpu = 500m`, `limits.cpu = 1500m`. Request có phải trần CPU 0,5 không?

**Đáp án:** Không. Request và limit phục vụ các mục đích khác nhau; limit mới đặt trần CPU khi được enforcement.

### Bài 4 — active processors

JVM báo 2 active processors nhưng quota thật là 1,5 CPU. Hai số này có mâu thuẫn không?

**Đáp án:** Không bắt buộc. JVM phải báo số nguyên cho heuristics, trong khi quota là CPU-time budget số thực.

### Bài 5 — capacity model

CPU quota 1,5, CPU time/request 30 ms. Ideal capacity?

**Đáp án:** `1.5 * 1000 / 30 = 50 RPS`, trước overhead và không phải SLA.

### Bài 6 — overload

Offered load 70 RPS, ideal throughput 50 RPS, không drop. Backlog tăng xấp xỉ bao nhiêu sau 10 giây?

**Đáp án:** `(70 - 50) * 10 = 200 requests` trong mô hình giả định liên tục.

### Bài 7 — Little's Law

Steady-state throughput 40 RPS, **mean response time** 100 ms. Trung bình số in-flight?

**Đáp án:** `L = 40 * 0.1 = 4` requests.

### Bài 8 — phân vị

Vì sao không thay W bằng p99 trong Little's Law?

**Đáp án:** Công thức dùng **thời gian trung bình**, còn p99 là phân vị, không phải mean.

### Bài 9 — throttling ratio

Trong một khoảng có 600 CPU periods và 120 periods bị throttled. Có thể kết luận gì?

**Đáp án:** 20% periods có throttling; không được suy 20% CPU time hay 20% requests bị ảnh hưởng.

### Bài 10 — queue bounded

Một `ThreadPoolExecutor` có một worker đang bận, queue capacity 2, `AbortPolicy`. Gửi thêm 2 tasks, rồi task thứ ba khi worker chưa giải phóng sẽ ra sao?

**Đáp án:** Hai tasks đợi trong queue; task tiếp theo bị `RejectedExecutionException` khi pool saturated.

### Bài 11 — CPU throttling và p99

Server có p99 tăng và `nr_throttled` tăng; có thể khẳng định nguyên nhân chỉ là CPU limit không?

**Đáp án:** Chưa. Cần đối chiếu CPU usage/quota, queue wait, GC, I/O, lock contention và timeline.

### Bài 12 — sizing threads

Có nên tạo 100 platform threads CPU-bound trong container 1 CPU để mong throughput tăng 100 lần?

**Đáp án:** Không. CPU quota vẫn giới hạn; có thể tăng context switching và latency.

### Bài 13 — unbounded queue

Tại sao `LinkedBlockingQueue<>()` mặc định có thể nguy hiểm khi load liên tục cao hơn capacity?

**Đáp án:** Tasks tiếp tục được xếp hàng, làm queue wait và memory retention tăng. `maximumPoolSize` cũng có thể không mở rộng như mong đợi với unbounded queue.

### Bài 14 — HPA

HPA dựa trên CPU requests hay CPU limits khi tính CPU utilization mục tiêu?

**Đáp án:** Thông thường sử dụng **CPU requests** làm mẫu số cho CPU utilization; phải kiểm tra cấu hình HPA/metrics thực tế.

### Bài 15 — kiểm thử đúng

Cần ghi metric nào tối thiểu khi đổi CPU limit từ 500m lên 1500m?

**Đáp án:** Offered load, completions/goodput, errors/timeouts, p50/p95/p99 latency, queue depth/wait, CPU usage, throttle deltas và GC. Giữ payload/môi trường tương đương.

## 20. Checklist chẩn đoán ứng dụng Java trong container

1. **Xác định môi trường**: JDK build, container runtime, Kubernetes version, Linux cgroups mode.
2. **Đọc resources.requests/limits** từ pod/container specification, không suy từ Java processor count.
3. **Xác nhận JVM container support** với `-XshowSettings:system`/`-Xlog:os+container` trên HotSpot Linux.
4. **Đọc quota/period** ở `cpu.max` hoặc endpoint phù hợp; xác định quota cores.
5. **Đọc cpuset/affinity** và kiểm tra có parent cgroup constraints không.
6. **Đo CPU usage theo cores**, không trộn với phần trăm host/limit/request.
7. **Đo throttle deltas**: `nr_periods`, `nr_throttled`, `throttled_usec`.
8. **Đo offered load, completed goodput, error/timeout/retry rate**.
9. **Đo p50/p95/p99 latency** từ phía client và từng stage trong trace.
10. **Đo queue length, queue wait, in-flight và active worker counts**.
11. **Đo CPU time/request** nếu muốn ước lượng upper bound capacity.
12. **Đối chiếu GC/JFR/tracing** để tách GC, lock, I/O và CPU throttling.
13. **Load test nhiều nấc** để tìm điểm throughput phẳng và p99 tăng nhanh.
14. **Kiểm tra queue bounds và rejection policy**; không mặc định queue vô hạn.
15. **Kiểm soát retry storm, deadline và load shedding**.
16. **Đánh giá scaling** sau khi biết bottleneck nằm ở CPU hay downstream.
17. **Kiểm tra hiệu ứng `ActiveProcessorCount`**, nhưng không nhầm với thay đổi CPU limit của Linux.
18. **Lặp lại đo và theo dõi SLO** sau mỗi thay đổi.

## 21. Tổng kết

- **Java 10+ HotSpot container-aware** giúp JVM nhận biết các giới hạn tài nguyên Linux phù hợp, nhưng **không tự giải quyết mọi vấn đề hiệu năng**.
- **Quota, cpuset, requests, JVM active processor count, CPU utilization** là **năm khái niệm cần đo/diễn giải riêng**.
- Với CPU-bound workload, công suất lý tưởng có thể ước lượng bằng **quota CPU-equivalent / CPU time per request**; cần benchmark để biết capacity thật.
- Khi **arrival rate vượt service capacity**, **queue sẽ tăng** nếu không có bound/rejection; throughput hoàn thành không thể tiếp tục tăng vô hạn.
- **Latency p95/p99, queue wait và throttling** có thể xấu đi ngay khi throughput bắt đầu phẳng. Không dùng mỗi CPU%.
- **Little's Law** giúp liên hệ **mean concurrency = throughput × mean latency** ở steady state, không dùng p99 thay mean.
- **ThreadPoolExecutor bounded queues, deadlines, rejection/backpressure** giúp hệ thống xử lý overload có kiểm soát.
- **Tăng số Java threads hoặc `-XX:ActiveProcessorCount` không tăng CPU quota**. Virtual threads cũng không tạo thêm năng lực CPU-bound.
- **Đánh giá bằng tải thực tế**, nhiều mức CPU limit và nhiều mức offered load, đồng thời kiểm soát GC, I/O và downstream.

### Tài liệu chính thức và hiện hành

1. [Oracle Java SE 26 — Java launcher, `-XX:ActiveProcessorCount`, `-XX:-UseContainerSupport`, `-XshowSettings:system` và `-Xlog:os+container`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — khả năng nhận biết container và cờ quan sát/tuning.
2. [OpenJDK — JDK-8146115: Docker container resource configuration](https://bugs.openjdk.org/browse/JDK-8146115) — bối cảnh phát triển container awareness có từ Java 10.
3. [Oracle JDK 19 Release Notes — CPU Shares Ignored When Computing Active Processor Count](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html) — thay đổi quan trọng để không lấy cpu.shares làm hard CPU count ở JDK hiện đại.
4. [Linux Kernel — Control Group v2 CPU interface](https://docs.kernel.org/admin-guide/cgroup-v2.html) — `cpu.max`, `cpu.stat`, `cpu.weight`, `cpu.pressure` và quota/period.
5. [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) — CPU requests và limits.
6. [Kubernetes — Control CPU Management Policies on the Node](https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/) — quota enforcement và CPU affinity/pinning.
7. [Java SE 26 — `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — unbounded/bounded queues, maximumPoolSize, rejection handlers.
8. [Java SE 26 — `Runtime.availableProcessors()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html#availableProcessors()) — số processors JVM báo cho ứng dụng.
9. [OpenJDK — Current Linux active_processor_count implementation](https://github.com/openjdk/jdk/blob/master/src/hotspot/os/linux/os_linux.cpp) — cách HotSpot xét explicit override, affinity và cgroup quota.
