# UseContainerSupport và việc nhận diện giới hạn tài nguyên của Java trong container

## 1. Vấn đề thực tế: host mạnh nhưng container được cấp ít CPU

Một máy chủ vật lý có thể có 32 CPU logic và 128 GiB RAM, trong khi container chạy ứng dụng Java trên đó chỉ được cấu hình **1,5 CPU** và **512 MiB RAM**. Nếu JVM tính số worker và kích thước heap dựa vào toàn bộ tài nguyên của host, nó có thể tạo quá nhiều luồng, tăng tranh chấp CPU, bị **CPU throttling**, hoặc chọn heap không hợp lý so với memory limit.

**UseContainerSupport** là một tính năng HotSpot giúp JVM nhận biết tài nguyên container thông qua **Linux cgroups**. Từ **Java 10**, HotSpot cải tiến cách nhìn số CPU và bộ nhớ được cấp cho tiến trình Docker, thay vì chỉ dựa trên cấu hình của host. Cờ liên quan là **`-XX:+UseContainerSupport`**; trên những bản HotSpot Linux hiện đại có hỗ trợ, tính năng **mặc định được bật**.

Bài học tập trung vào đề mục **“UseContainerSupport và việc nhận diện giới hạn tài nguyên”** thuộc **“CPU trong container”**. Chúng ta cần phân biệt bốn lớp thông tin:

1. **Cấu hình orchestrator**: Docker `--cpus`, Kubernetes CPU `requests` và `limits`.
2. **Giới hạn do Linux kernel thực thi**: cgroup quota, period, cpuset và CPU affinity.
3. **Giá trị mà JVM nhận diện**: `Runtime.getRuntime().availableProcessors()`, các JVM ergonomic options.
4. **Hiệu năng thực tế**: CPU usage, throttling, worker count, throughput và response latency.

**Quan trọng:** JVM **đọc** giới hạn và điều chỉnh mặc định; `UseContainerSupport` **không tự cấp CPU, không thay CPU quota và không bảo đảm không có throttling**.

### Mục tiêu học tập

- Hiểu hành vi của `-XX:+UseContainerSupport` và `-XX:-UseContainerSupport` trên Linux HotSpot hiện đại.
- Biết các mốc Java 10, JDK 15, JDK 19 liên quan container awareness và vì sao thuật toán cũ không nên áp dụng nguyên xi.
- Phân biệt CPU **quota/period**, **cpuset/affinity** và **shares/weight**.
- Giải thích được vì sao CPU quota **1500m** có thể tương ứng với **2 active processors** trong JVM nhưng kernel vẫn giới hạn **1,5 CPU time**.
- Sử dụng `-XX:ActiveProcessorCount=N` một cách có chủ đích và hiểu phạm vi của nó.
- Kiểm tra giá trị JVM nhận diện bằng API Java, `-XshowSettings:system` và `-Xlog:os+container=trace`.
- Phân biệt CPU `request` và `limit` trong Kubernetes.
- Hiểu ảnh hưởng của effective processor count đến GC, JIT, ForkJoinPool và các thread pools ứng dụng.
- Biết tại sao memory limit của cgroup khác `Runtime.maxMemory()` và `-Xmx`.
- Thực hành chương trình Java 17+ với stdout đã kiểm chứng bằng OpenJDK 24.

## 2. Mốc Java 10 và những thay đổi vẫn cần biết ở JDK hiện đại

Oracle **JDK 10 Release Notes** giới thiệu nhóm cải tiến dành cho Docker. Chúng bao gồm:

| Tính năng | Vai trò | Trạng thái hiện nay |
| --- | --- | --- |
| **JDK-8146115** | Cải thiện nhận diện container và sử dụng cấu hình tài nguyên của Docker/Linux. | Ý tưởng nền tảng vẫn áp dụng. |
| **`-XX:+UseContainerSupport`** | Bật nhận diện CPU/memory dựa trên cgroup. | Được hỗ trợ và mặc định bật trên HotSpot Linux hiện đại. |
| **`-XX:-UseContainerSupport`** | Tắt nhận diện container. | Vẫn có, nhưng thường không nên tắt trong container production. |
| **`-XX:ActiveProcessorCount=N`** | Chỉ định số active processors mà JVM sử dụng trong ergonomic calculations. | Tiếp tục được hỗ trợ. |
| **`-XX:InitialRAMPercentage`, `MaxRAMPercentage`, `MinRAMPercentage`** | Kiểm soát một số phép tính mặc định về heap theo RAM mà JVM nhìn thấy. | Tiếp tục hữu ích, cần xét native-memory overhead. |

Nhưng một bài Java 10 **không được giả định các chi tiết triển khai năm 2018 vẫn y hệt năm 2026**:

- **JDK 15** bổ sung hỗ trợ **cgroups v2** cho HotSpot. Một số nhánh cũ nhận lại tính năng qua bản cập nhật backport; cần kiểm tra chính xác build.
- **JDK 19** thay đổi phép tính số active processors: HotSpot **mặc định bỏ qua CPU shares** khi xác định processor count, vì shares/weight thể hiện trọng số tranh chấp CPU chứ không phải hạn mức CPU cứng.
- **JDK 21, 25, 26** tiếp tục có container awareness trên Linux, cùng các cải tiến cho cgroup, affinity, quotas và lỗi môi trường cụ thể. Không coi các chi tiết/bug của một build JDK cũ là hợp đồng cho mọi bản JDK mới.

**Kết luận về phiên bản:** Học **mục đích** của Java 10, nhưng khi tính CPU trên JDK hiện đại, ưu tiên tài liệu đúng **JDK vendor và update build**. Đặc biệt, không dùng công thức cũ `cpu.shares / 1024` làm cách xác định effective CPU count của Java 25/26.

## 3. Tại sao phải tách kernel resource limit và JVM resource detection?

Sơ đồ cơ chế:

~~~text
HOST: nhiều logical CPUs và dung lượng RAM lớn
                      |
                 Linux kernel
                      |
         +------------+--------------+
         | cgroups / CPU scheduling   |
         | CPU quota + period         |
         | cpuset / affinity          |
         | memory limits              |
         +------------+--------------+
                      |
              Container / Pod
          cpu.limit = 1500m (1.5 CPU)
          memory.limit = 512 MiB
                      |
       HotSpot container detection
             UseContainerSupport
                      |
        +-------------+-------------+
        |                           |
   Effective CPU count        Effective memory basis
        |                           |
   Runtime.availableProcessors  Heap ergonomic sizing
   GC/JIT/ForkJoin defaults      MaxRAMPercentage
        |                           |
              Java application
~~~

**Cgroup** là cơ chế của Linux kernel quản lý resource. Docker/Kubernetes đặt cấu hình; kernel thực thi giới hạn. JVM quan sát những ràng buộc được phép thấy và chọn cấu hình.

Một ví dụ:

~~~text
CPU quota = 150000 microseconds
CPU period = 100000 microseconds
Average CPU budget = 1.5 CPUs
~~~

Những luồng của container có thể cùng chạy trên hai hoặc nhiều logical CPUs trong một phần của period, rồi bị kernel **throttle** khi đã dùng hết CPU time trước khi period kết thúc. Đó là giới hạn **CPU time**, không phải một “core 1,5” được đặt riêng trong phần cứng.

JVM có thể báo `availableProcessors=2` vì API trả **số nguyên** và quy tắc sizing có thể làm tròn quota lên. Điều đó **không nâng quota lên 2 CPUs**.

### 3.1. Có bốn số khác nhau

| Đại lượng | Ví dụ | Cách dùng |
| --- | --- | --- |
| Host CPU topology | 32 logical CPUs | Mô tả host, không phải quyền dùng của container. |
| CPU quota trung bình | 1,5 CPU time | Kernel dùng để throttle khi chạm quota. |
| Active processors JVM báo | 2 | Đầu vào cho heuristic sizing và API ứng dụng. |
| CPU usage hiện tại | 0,8 CPU hoặc tỷ lệ theo dashboard | Chỉ đo bằng metrics trong một khoảng thời gian. |

Đừng đồng nhất **quota**, **processor count** và **usage**. Cả ba đều có thể đúng đồng thời nhưng mang ý nghĩa khác nhau.

## 4. CPU quota và period: đọc đúng giới hạn cứng

Cgroups v2 dùng file `cpu.max` với hai giá trị:

~~~text
150000 100000
~~~

Ở cấu hình minh họa này:

- Số đầu là **CPU quota = 150000 microseconds**.
- Số sau là **CPU period = 100000 microseconds**.
- Tỷ lệ quota/period bằng **1,5 CPUs**.

Trong cgroups v1, các thông tin tương tự thường xuất hiện trong:

~~~text
cpu.cfs_quota_us
cpu.cfs_period_us
~~~

**Không** nhầm `150000` microseconds CPU time với 150000 microseconds **thời gian chạy thực của một thread cụ thể**. Khi nhiều threads dùng CPU song song, tổng CPU time được tiêu thụ nhanh hơn elapsed wall-clock time.

### 4.1. Trường hợp quota không giới hạn

Một file cgroups v2 có thể ghi:

~~~text
max 100000
~~~

`max` nghĩa là **không có CPU quota do cấu hình ở cấp cgroup đó**. Nó **không** chứng minh process có quyền dùng toàn bộ CPUs của host, vì vẫn có:

- CPU affinity/cpuset.
- Quota của parent cgroup (hierarchy).
- Chính sách runtime và giới hạn từ host.
- Cạnh tranh CPU với workload khác.

Nếu bạn muốn biết số CPUs JVM coi là available, hỏi chính JVM, **không chỉ đọc cpu.max**.

### 4.2. CPU throttling là gì?

Cgroups v2 có file `cpu.stat` với những trường thường gặp:

~~~text
nr_periods
nr_throttled
throttled_usec
~~~

`nr_throttled` phản ánh số kỳ có throttling, `throttled_usec` phản ánh thời lượng được ghi nhận, tùy hệ thống/kernel. Để phân tích, **đo chênh lệch counter theo khoảng thời gian**, thay vì lấy một giá trị tích lũy rồi suy ra latency của một request.

Cgroup limit **không** ngăn ứng dụng tạo nhiều threads; nó giới hạn CPU time thực được phép sử dụng. Bởi thế việc đặt quá nhiều CPU-bound workers có thể làm nghẽn CPU quota và tăng latency.

## 5. Cpuset và CPU affinity: giới hạn nơi process được chạy

Một cơ chế khác là chỉ cho process chạy trên một tập logical CPU xác định, ví dụ:

~~~text
cpuset.cpus.effective = 2-3
~~~

Ở đây, process chỉ được phép chạy trên logical CPUs 2 và 3 theo cpuset hiệu dụng, nếu không còn ràng buộc khác. Đó là **2 logical CPUs được phép lập lịch**, nhưng không nhất thiết là **2 CPUs được bảo đảm độc quyền**.

Phân biệt:

- **Cpuset/affinity**: giới hạn **vị trí CPUs** process có thể chạy.
- **Quota/period**: giới hạn **tổng CPU time** được dùng trong từng period.
- **CPU weight/shares**: ảnh hưởng **tỷ trọng cạnh tranh** khi các cgroups cùng tranh CPU.

Một container có thể vừa có `cpu.max` giới hạn 1 CPU, vừa được phép chạy trên 8 logical CPUs bởi cpuset. Ngược lại, cpuset chỉ 2 logical CPUs có thể giới hạn số processors hữu dụng ngay cả khi quota cho 4 CPUs.

**Ghi nhớ:** Giá trị JVM tính thường bị ràng buộc bởi **CPU affinity và quota**, nhưng thứ tự ưu tiên và chi tiết xử lý các giới hạn là **chi tiết HotSpot/JDK**, không phải một công thức Java SE phải giống nhau trên mọi nền tảng.

## 6. CPU shares/weight: không còn là đầu vào mặc định như Java 10

Một nhầm lẫn tồn tại trong nhiều tài liệu cũ là xem CPU shares như số CPU được cấp.

**Cgroups v1:** `cpu.shares` là trọng số tương đối.

**Cgroups v2:** `cpu.weight` có vai trò tương tự trong lập lịch.

Một container có weight thấp hơn có thể nhận tỷ lệ CPU time nhỏ hơn khi tranh tài nguyên, nhưng nếu CPU rảnh, nó **không nhất thiết bị giới hạn ở một số cores cố định**. Vì vậy weight/shares **không phải CPU quota**.

Theo Oracle **JDK 19 release notes**, HotSpot không còn mặc định dùng CPU shares để tính số active processors. Lý do là diễn giải trước đây có thể khiến JVM dùng **ít threads hơn số CPU thực tế khả dụng**, gây underutilization.

### 6.1. Hệ quả đối với Kubernetes request

Một deployment có:

~~~yaml
resources:
  requests:
    cpu: "500m"
~~~

mà **không có CPU limit** không đồng nghĩa container luôn bị giới hạn 0,5 CPU. Request được scheduler dùng để xếp chỗ và ảnh hưởng tỷ trọng tài nguyên theo runtime, nhưng không tự đặt hard quota. Trên JDK 19+, HotSpot không mặc định coi request/weight này là một CPU limit để suy ra `availableProcessors()`.

**Sai:** “request 500m nên HotSpot bắt buộc báo 1 processor”.

**Đúng:** Kiểm tra **CPU limit/quota**, **cpuset**, **affinity**, JVM flags và dữ liệu thực tế; nếu không có hard limit, JVM có thể nhìn thấy nhiều processors.

### 6.2. Không kích hoạt lại cách tính legacy để sửa mọi vấn đề

Một tùy chọn lịch sử từng được cung cấp để khôi phục việc dùng CPU shares đã bị đánh dấu deprecated. Với hệ thống mới, **không khuyến nghị dùng nó làm chính sách mặc định**; hãy dựa vào CPU limits, thread-pool tuning và `ActiveProcessorCount` khi thật sự có nhu cầu.

## 7. `-XX:+UseContainerSupport`: HotSpot làm gì?

Trong HotSpot Linux được hỗ trợ, flag **`UseContainerSupport` mặc định true** và cho JVM lấy số CPU và memory phù hợp từ môi trường container.

~~~text
-XX:+UseContainerSupport     bật container awareness (Linux HotSpot)
-XX:-UseContainerSupport     tắt container awareness
~~~

**Tác động thực tế có thể gồm:**

- `Runtime.getRuntime().availableProcessors()` phản ánh effective processor count thay vì đơn thuần host count.
- Ergonomic sizes của một số GC/JIT/ForkJoin thread pools phản ánh giá trị CPU JVM nhận diện.
- Heap ergonomic calculations có thể dựa trên memory limit container.
- Java diagnostic commands có thể hiển thị container/cgroup information.

**Không bảo đảm:**

- Mọi JVM implementation đều hỗ trợ cờ này.
- JVM tự tăng/giảm chính xác mọi thread pool mà ứng dụng đã tạo.
- Mọi JDK update đều xử lý cgroups v1/v2 và hierarchy giống nhau.
- Bật flag làm biến mất CPU throttling.
- Bật flag khiến `Runtime.maxMemory()` bằng memory cgroup limit.
- Kernel tự chuyển requests thành CPU quota khi chỉ có requests.
- App có thể truy cập mọi thông số cgroup qua API Java SE portable.

### 7.1. Nền tảng hỗ trợ

**Oracle JDK 25 java command docs ghi rõ `UseContainerSupport` là Linux-only.** Trên môi trường Windows JDK 24.0.2 đã thử nghiệm, `-XX:-UseContainerSupport` bị báo `Unrecognized VM option`.

Vì vậy:

- Trên **Linux container**, kiểm tra flag và log cgroup.
- Trên **Windows/macOS**, không coi việc thiếu flag là lỗi Java language; cơ chế Linux cgroups không tồn tại ở OS đó.
- Dù Windows có thể chạy Docker Desktop, JVM **chạy trực tiếp trên Windows host** khác một JVM **chạy bên trong Linux container**.

### 7.2. Có nên tắt `UseContainerSupport` để tăng tốc?

Thông thường **không**. Trên Linux container, việc tắt có thể khiến JVM dùng thông tin host thay vì container khi tính worker/heap defaults, làm tình trạng oversubscription hoặc memory pressure nghiêm trọng hơn.

Chỉ tắt nếu bạn đã hiểu:

1. JDK cụ thể có bug/behavior nào cần né.
2. CPU/memory limits thực tế là gì.
3. Bạn định tự cấu hình CPU/heap như thế nào.
4. Benchmarks và rollback plan.
5. Ảnh hưởng của flag tới workload thật.

**Đừng làm thử trên production mà không có kế hoạch**, đặc biệt khi container có memory limit thấp.

## 8. `-XX:ActiveProcessorCount=N`: ghi đè số CPUs JVM nhìn thấy

Flag:

~~~text
-XX:ActiveProcessorCount=2
~~~

cho HotSpot biết dùng số active processors **2** trong các tính toán nội bộ liên quan. Nó tiếp tục được Oracle mô tả trong JDK hiện đại, và được chấp nhận **ngay cả khi UseContainerSupport bị tắt** trên một nền tảng hỗ trợ.

Nhưng flag này **không đổi**:

- CPU cgroup quota/period.
- Cpuset/CPU affinity do kernel quản lý.
- CPU request/limit của Kubernetes.
- CPU frequency hoặc số physical cores.
- Số threads tuyệt đối của mọi thư viện/framework.
- Khả năng bị CPU throttling.

Nếu container bị quota **1 CPU**, đặt `-XX:ActiveProcessorCount=8` **không cho nó 8 CPUs**. Trái lại, JVM/ứng dụng có thể lập kế hoạch nhiều workers hơn và bị tranh CPU/throttling.

### 8.1. Trường hợp hữu ích

Có thể dùng override khi:

- Cần giảm mức parallelism mặc định trong service có giới hạn tài nguyên cụ thể.
- Chạy nhiều JVM trên cùng môi trường và cần chia ngân sách CPU cho từng process.
- Đo benchmark cần controlled CPU ergonomic count.
- JVM trên hệ thống đặc thù nhận CPU affinity/quota chưa phù hợp và có giải pháp cấu hình được kiểm chứng.

Không dùng một con số cố định cho mọi image/deployment nếu CPU limits thay đổi theo môi trường. Một cấu hình cứng có thể trở nên lỗi thời khi Kubernetes resources được cập nhật.

## 9. Vì sao CPU quota 1,5 có thể khiến JVM báo 2 processors?

Giả sử:

~~~text
cpu.max = 150000 100000
cpuset allows at least 2 logical CPUs
ActiveProcessorCount not explicitly set
~~~

Quy tắc phổ biến để quy đổi quota sang số processor là **làm tròn lên**:

~~~text
CPU budget = 150000 / 100000 = 1.5
Effective integer quota count = ceil(1.5) = 2
~~~

Vì `Runtime.availableProcessors()` trả kiểu `int`, JVM có thể báo **2**. Nhưng OS vẫn enforce quota **1,5 CPU time**. Trong cùng period, các threads CPU-bound chạy hết quota sẽ bị throttled nếu không có CPU budget bổ sung.

Bảng ví dụ khái niệm (giả định affinity đủ rộng và không có override):

| CPU quota/period | CPU budget | Integer quota estimate |
| --- | --- | --- |
| `50000 / 100000` | 0,5 CPU | 1 |
| `100000 / 100000` | 1 CPU | 1 |
| `150000 / 100000` | 1,5 CPUs | 2 |
| `200000 / 100000` | 2 CPUs | 2 |
| `350000 / 100000` | 3,5 CPUs | 4 |

Đây là **quy tắc giải thích behavior thường gặp của HotSpot**, không phải kết quả đo trên một container cụ thể hay hợp đồng Java SE buộc mọi JVM trả đúng bảng. Giá trị cuối còn chịu tác động của cpuset/affinity, cgroup hierarchy, runtime flags và bản JDK.

### 9.1. Quota bằng 0,5 không có nghĩa JVM trả 0

JVM cần một số processor **dương** cho sizing. Với quota 0,5 CPU, nó có thể chọn 1 active processor, nhưng container vẫn bị giới hạn CPU time tương ứng. Đây là lý do `availableProcessors()` **không phải API trả số fractional CPU entitlement**.

### 9.2. Nếu quota lớn hơn cpuset

Giả sử quota cho 4 CPUs, nhưng CPU affinity chỉ cho process chạy trên 2 logical CPUs. Số processors thực sự có thể dùng không vượt quá tập CPUs được phép theo affinity. Vì vậy không thể chỉ đọc quota rồi báo “JVM có 4 CPUs”.

## 10. API Java để kiểm tra số processor JVM nhận diện

API công khai:

~~~java
int processors = Runtime.getRuntime().availableProcessors();
~~~

Một API liên quan qua `java.lang.management`:

~~~java
int processorsFromMxBean =
        java.lang.management.ManagementFactory
                .getOperatingSystemMXBean()
                .getAvailableProcessors();
~~~

Trong HotSpot, hai số thường đồng nhất vì cùng mô tả processors JVM xem là available. Nhưng việc **hai API đồng ý** không phải bằng chứng cgroup đã được đọc thành công — nếu JVM đang chạy trên host không có container, chúng vẫn trả một giá trị.

**Không dùng** `jdk.internal.platform.Metrics` như một API ứng dụng Java SE ổn định. Nó là internal API, có thể thay đổi và thường bị module encapsulation chặn. Trong ứng dụng portable, dùng API công khai; để chẩn đoán cgroup, dùng JVM diagnostic tools và OS metrics.

## 11. Ví dụ Java 17+ chạy độc lập, stdout đã được kiểm chứng

Tạo file **`ContainerCpuProbe.java`**:

~~~java
import java.lang.management.ManagementFactory;
import java.util.concurrent.ForkJoinPool;

public class ContainerCpuProbe {
    public static void main(String[] args) {
        int cpus = Runtime.getRuntime().availableProcessors();
        int mxBeanCpus =
                ManagementFactory.getOperatingSystemMXBean()
                        .getAvailableProcessors();
        int workers = Math.max(1, Math.min(8, cpus));

        System.out.println("availableProcessors=" + cpus);
        System.out.println("mxBeanProcessors=" + mxBeanCpus);
        System.out.println("workerBudget=" + workers);
        System.out.println("commonPoolParallelism=" +
                ForkJoinPool.getCommonPoolParallelism());
    }
}
~~~

**Mô tả:**

- `availableProcessors`: số CPUs JVM báo.
- `mxBeanProcessors`: số CPUs tương ứng từ OperatingSystemMXBean.
- `workerBudget`: heuristic **tự đặt trong ứng dụng demo**, chọn ít nhất 1, tối đa 8; không phải hard limit do JVM áp vào mọi code.
- `commonPoolParallelism`: mức parallelism hiện có của ForkJoinPool common pool. Trong môi trường thử nghiệm, mức mặc định là `max(1, cpus - 1)`; có thể khác khi JVM/system property được cấu hình riêng.

### 11.1. Biên dịch

~~~bash
javac -encoding UTF-8 ContainerCpuProbe.java
~~~

Chương trình chỉ dùng Java SE public APIs, không cần Maven/Gradle hay dependency.

### 11.2. Chạy với 2 active processors

~~~bash
java -XX:ActiveProcessorCount=2 ContainerCpuProbe
~~~

**Stdout thực tế, kiểm chứng bằng OpenJDK 24.0.2 trên Windows:**

~~~text
availableProcessors=2
mxBeanProcessors=2
workerBudget=2
commonPoolParallelism=1
~~~

### 11.3. Chạy với 4 active processors

~~~bash
java -XX:ActiveProcessorCount=4 ContainerCpuProbe
~~~

**Stdout thực tế:**

~~~text
availableProcessors=4
mxBeanProcessors=4
workerBudget=4
commonPoolParallelism=3
~~~

### 11.4. Chạy không có override

~~~bash
java ContainerCpuProbe
~~~

Kết quả **phụ thuộc môi trường**, không được sao chép cố định. Máy Windows JDK24 thử nghiệm báo `28` available processors, `28` cho MXBean, `workerBudget=8` và `commonPoolParallelism=27`. Trên Linux container, các giá trị có thể thấp hơn tùy quota/cpuset.

**Điểm QA quan trọng:** Hai phép thử override đã compile và chạy exit code 0. Chúng **xác minh cờ ActiveProcessorCount**, không phải thử nghiệm nhận diện cgroups Linux. Phần kiểm chứng cgroup bên dưới là quy trình riêng, cần chạy ở Linux container thật.

## 12. Chẩn đoán JVM container trên Linux bằng công cụ hiện hành

### 12.1. Xem JDK build và flags

~~~bash
java -version
java -XX:+PrintFlagsFinal -version | grep UseContainerSupport
java -XX:+PrintFlagsFinal -version | grep ActiveProcessorCount
~~~

Dòng `UseContainerSupport = true` trên HotSpot Linux có nghĩa tính năng **được bật**. Chưa đủ kết luận JVM đã thấy đúng quota. Có thể có `-XX:ActiveProcessorCount` trong entrypoint hoặc `JAVA_TOOL_OPTIONS` khiến kết quả JVM khác con số do cgroup.

### 12.2. In thông tin OS/container

~~~bash
java -XshowSettings:system -version
~~~

Trên HotSpot Linux có container metrics, đầu ra thường chứa phần **Operating System Metrics** với cgroup information, CPU quota/period, effective processors, cpuset, memory limit và các trường khác theo JDK.

Nếu thấy `No metrics available for this platform`, hãy xem:

- JVM đang chạy **trên Linux hay Windows/macOS**?
- Bản JDK có hỗ trợ cgroups version này không?
- Procfs/sysfs/cgroup mounts có khả dụng không?
- Quyền truy cập và namespace của process ra sao?
- Có chạy một JVM khác implementation với HotSpot không?

Không tự gán “JVM bug” khi không có metrics trên một OS không hỗ trợ cơ chế Linux cgroup.

### 12.3. Bật Unified Logging cho container detection

~~~bash
java -Xlog:os+container=trace -version
~~~

Theo Oracle Java SE 25 docs, đây là cách lấy container information **chi tiết nhất** trong HotSpot Linux.

Có thể thử mức ít ồn hơn:

~~~bash
java -Xlog:os+container=debug -cp . ContainerCpuProbe
~~~

Hãy đối chiếu log với cgroup files và `availableProcessors()`. Thông điệp cụ thể của `os+container` **không phải format API bất biến**; tránh hard-code toàn bộ một dòng log qua nhiều JDK versions.

### 12.4. Cgroups v2: các file thường cần đọc

Trong nhiều Linux containers dùng unified cgroup hierarchy:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.max
~~~

Ý nghĩa:

| File | Mục đích |
| --- | --- |
| `cpu.max` | Quota và period; `max` nghĩa không giới hạn quota ở cấp đó. |
| `cpuset.cpus.effective` | Logical CPUs thực sự được phép dùng theo cpuset hierarchy. |
| `cpu.stat` | CPU time và thông tin throttle/period theo kernel hỗ trợ. |
| `memory.max` | Memory limit hoặc `max` nếu không đặt hard limit ở cấp đó. |

**Đường dẫn ở trên là ví dụ mount phổ biến**, không phải mọi hệ thống có cùng đường dẫn. Khi process nằm trong cgroup subtree hoặc namespace khác, có thể cần xem `/proc/self/cgroup` và `/proc/self/mountinfo` để tìm đúng vị trí. Parent cgroup cũng có thể đặt giới hạn.

### 12.5. Cgroups v1: giao diện cũ nhưng vẫn gặp trong hệ thống còn vận hành

Cgroups v1 sử dụng nhiều controllers và đường dẫn mount khác nhau, với những tên file như:

~~~text
cpu.cfs_quota_us
cpu.cfs_period_us
cpu.shares
cpuset.cpus
memory.limit_in_bytes
~~~

Trên JDK hiện đại, **đừng lấy cpu.shares làm hard CPU limit**. Nó là trọng số scheduler. Cần đọc quota/period và cpuset/affinity, đối chiếu với Java container logs.

## 13. Kịch bản Docker trên Linux để kiểm tra thật

Giả sử Linux host đã cài Docker và bạn có class file `ContainerCpuProbe.class` được biên dịch với phiên bản JDK không mới hơn runtime trong image, có thể thực hiện:

~~~bash
docker run --rm --cpus=1.5 --memory=512m \
  --mount type=bind,src="$(pwd)",dst=/work \
  -w /work eclipse-temurin:25-jdk \
  java -XshowSettings:system -Xlog:os+container=debug \
       -cp /work ContainerCpuProbe
~~~

**Lệnh trên là hướng dẫn Linux/Docker, không phải lệnh đã được chạy trong môi trường Windows thử nghiệm.** Cần Docker, image phù hợp, quyền bind mount và class file trên host. Đối với CI/production, nên pin image digest hoặc build rõ ràng để có kết quả tái hiện.

Thứ cần quan sát:

1. Container có CPU quota tương ứng 1,5 và memory limit 512 MiB?
2. JVM ghi nhận cgroups v1/v2 và giới hạn hiện hành?
3. `availableProcessors()` và MXBean report bao nhiêu?
4. Có `ActiveProcessorCount` override không?
5. Cpuset/affinity có giới hạn nhỏ hơn 2 CPUs không?
6. `cpu.stat` có throttling dưới workload CPU-bound không?

Ở tình huống quota 1,5, cpuset đủ rộng, không override, HotSpot hiện đại **có thể báo 2 active processors**. Kết quả cuối phải được xác nhận trong container thật; không được khẳng định mọi vendor/JDK/kube-node đều trả cùng một số.

### 13.1. Tại sao `lscpu` hoặc `nproc` không thay thế JVM metrics?

`lscpu` mô tả CPU topology của hệ thống; có thể phản ánh host nhiều hơn giới hạn của container. `nproc` thường dựa trên available processing units/affinity, nhưng không nhất thiết dùng cùng cách quy đổi CPU quota như HotSpot.

Vì vậy so sánh ba nguồn:

- **OS/cgroup**: quota, period, cpuset, hierarchy, throttle.
- **JVM**: `Runtime.availableProcessors()` và `-XshowSettings:system`.
- **Monitoring**: CPU usage, throttling, p95/p99 latency.

Một nguồn đơn lẻ thường **không đủ** để kết luận JVM có sử dụng tài nguyên phù hợp hay không.

## 14. Kubernetes: requests và limits tác động khác nhau

Ví dụ phần cấu hình tài nguyên trong Kubernetes:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "1500m"
    memory: "512Mi"
~~~

| Trường | Ý nghĩa |
| --- | --- |
| `requests.cpu: 500m` | Yêu cầu tài nguyên cho scheduler; có thể ảnh hưởng mức ưu tiên chia CPU khi tranh chấp. |
| `limits.cpu: 1500m` | Giới hạn CPU time trung bình ~1,5 CPU qua cgroup CFS quota trong cấu hình thông thường. |
| `requests.memory: 256Mi` | Mức memory được scheduler tính khi xếp pod. |
| `limits.memory: 512Mi` | Giới hạn memory cgroup, có nguy cơ OOM kill khi vượt mức. |

**Không suy luận Java 25 sẽ dùng `500m request` như một quota 0,5 CPU.** Từ JDK 19, CPU shares/weight không mặc định quyết định active processor count. Với limit 1500m và cpuset đủ rộng, JVM có thể chọn 2.

### 14.1. Khi không có CPU limit

Nếu chỉ cấu hình `requests.cpu`, kernel thường không đặt quota cứng từ request đó. JVM có thể báo nhiều processors theo affinity/cpuset, vì thực tế container có thể sử dụng CPU khi host không bị cạnh tranh.

Nếu service cần cố định mức parallelism cho một SLA hoặc fairness policy, có thể chọn cấu hình thread pools riêng hoặc `ActiveProcessorCount` phù hợp, nhưng **không phải vì request tự động là CPU limit**.

### 14.2. Khi CPU limit 1500m nhưng JVM báo 2

Không mâu thuẫn:

- **CPU limit 1,5** là tài nguyên dưới dạng **CPU time budget**.
- **2 active processors** là con số integer cho JVM ergonomics.
- **CPU throttling** có thể xảy ra nếu workload muốn dùng CPU time cao hơn quota.

Trên Kubernetes, nên quan sát `container_cpu_cfs_throttled_periods_total` hoặc metrics tương đương do hệ thống monitoring cung cấp (tùy cgroup version/collector), bên cạnh application latency.

### 14.3. CPU Manager và cpuset

Một số cluster dùng chính sách CPU Manager có thể gán tập exclusive logical CPUs cho pod đủ điều kiện. Lúc ấy cpuset hiệu dụng cũng quan trọng. Không giả định mọi pod có cùng QoS, CPU Manager policy hoặc cpuset layout.

Chỉ phân tích **cgroup của đúng container đang chạy**, không lấy một pod khác trong cluster làm đại diện.

## 15. JVM worker counts: GC, JIT, ForkJoinPool và ứng dụng

Giá trị processor count JVM nhìn thấy có thể ảnh hưởng:

| Thành phần | Cách dùng thường gặp | Giới hạn suy luận |
| --- | --- | --- |
| G1/GC | Tính một số GC parallel worker counts. | Worker thực tế vẫn do VM heuristics và flags quyết định. |
| Concurrent GC | Số workers cho một số pha concurrent. | Không đồng nhất với parallel STW workers. |
| JIT compilation | Thread sizing/parallel work trong compiler theo VM. | Tùy compiler tier, cờ cấu hình và workload. |
| `ForkJoinPool.commonPool()` | Parallelism mặc định. | Có thể bị system property override; không luôn bằng activeProcessors. |
| Parallel streams | Có thể chạy trên ForkJoin common pool. | Không đảm bảo speedup tuyến tính khi quota thấp. |
| Thread pools của framework | Một số lấy `availableProcessors` làm input. | Còn phụ thuộc cấu hình framework, workload I/O và application policy. |

### 15.1. Ví dụ worker budget do ứng dụng tự chọn

~~~java
int cpus = Runtime.getRuntime().availableProcessors();
int workerBudget = Math.max(1, Math.min(8, cpus));
~~~

Đây là **heuristic của ứng dụng**, không phải nguyên tắc Java bắt buộc mọi service dùng 8 làm maximum. Với CPU-bound tasks, mức parallelism thường cần được benchmark dưới quota thật. Với I/O-bound tasks, có thể dùng concurrency lớn hơn số CPU mà vẫn hợp lý, nhưng phải xét blocking, memory, queues và downstream dependencies.

### 15.2. Vì sao `ActiveProcessorCount=8` có thể làm một service chậm hơn?

Nếu CPU limit chỉ 1 CPU nhưng JVM tin có 8 active processors, một số GC/JIT/ForkJoin operations có thể khởi tạo nhiều workers hơn. Trong thời gian các luồng chạy CPU-bound, container nhanh chóng tiêu hết quota, bị kernel throttle và tăng latency.

**Không kết luận luôn phải đặt `ActiveProcessorCount=1`**. Workload khác nhau có chi phí parallelism, I/O và GC khác nhau. Dùng CPU quota, throttling metrics, p99 và throughput để chọn thông số.

## 16. Memory container: phần liên quan nhưng phải đo khác CPU

`UseContainerSupport` còn giúp HotSpot tính toán mặc định dựa trên **memory limit** được cgroup cung cấp. Ví dụ container có memory limit 512 MiB, JVM có thể chọn heap maximum theo cấu hình `-XX:MaxRAMPercentage`.

Đừng nhầm:

| Đại lượng | Ý nghĩa |
| --- | --- |
| `memory.max` / memory cgroup limit | Giới hạn memory mà kernel thực thi cho container/cgroup. |
| `-Xmx` | Maximum Java heap size. |
| `-XX:MaxRAMPercentage` | Tỷ lệ dùng trong JVM heap ergonomic calculation. |
| `Runtime.getRuntime().maxMemory()` | Maximum Java heap JVM báo, **không phải tổng RAM của container**. |
| Metaspace/code cache/threads/direct buffers | Bộ nhớ ngoài heap, vẫn góp vào container footprint. |

Ví dụ cấu hình minh họa:

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

Không khẳng định 60% là lựa chọn tối ưu hoặc an toàn cho mọi container. Ứng dụng còn dùng native memory; đặt heap quá gần memory limit có thể khiến pod bị **OOM kill** dù Java heap chưa đầy.

Nếu đặt:

~~~bash
java -Xmx256m -jar app.jar
~~~

`-Xmx` được cấu hình trực tiếp. `UseContainerSupport` vẫn có vai trò nhận diện CPU và những quyết định ergonomic khác; nó không ghi đè mọi JVM option tường minh.

### 16.1. CPU count không chẩn đoán được OOM

Container có `availableProcessors=2` nhưng bị OOM kill hoàn toàn có thể xảy ra. CPU quota và memory limit là hai resource controllers khác nhau. Khi OOM, cần xem heap/native memory, cgroup memory counters và application allocations, không chỉ `Runtime.availableProcessors()`.

## 17. Quy trình chẩn đoán khi ứng dụng nhận sai CPU

### Bước 1: xác định JDK và OS thật

~~~bash
java -version
~~~

Ghi lại vendor, feature/update build, Linux kernel, cgroup version, image, entrypoint, JVM implementation.

### Bước 2: xem giới hạn container được cấu hình

Xác nhận Kubernetes `resources.requests/limits` hoặc Docker flags thật, không chỉ file values template. Kiểm tra có CPU limit, cpuset hay không.

### Bước 3: xem cgroup mà **process đang chịu**

Với cgroups v2:

~~~bash
cat /proc/self/cgroup
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.stat
~~~

Nếu cgroup nằm trong subtree/hierarchy khác, xác định mount/path theo `/proc/self/mountinfo` và runtime configuration.

### Bước 4: xem JVM flags và metrics

~~~bash
java -XX:+PrintFlagsFinal -version | grep ActiveProcessorCount
java -XX:+PrintFlagsFinal -version | grep UseContainerSupport
java -XshowSettings:system -version
java -Xlog:os+container=trace -version
~~~

Chỉ chạy các câu lệnh container-specific trên nền tảng HotSpot Linux có hỗ trợ.

### Bước 5: hỏi ứng dụng

~~~java
System.out.println(
        Runtime.getRuntime().availableProcessors());
~~~

Nếu giá trị khác mong đợi, kiểm tra override, affinity/cpuset, quota, hierarchy và JDK version. Đừng vội giả định bug.

### Bước 6: xem throttling và performance

Ghi nhận CPU usage theo quota, `cpu.stat` counters, p95/p99 latency, GC/JIT thread counts và executor queue size. Một giá trị availableProcessors hợp lý **không loại trừ** throttling.

### Bước 7: thử thay đổi có kiểm chứng

Có thể cần thay Kubernetes CPU limits, điều chỉnh worker budgets, cập nhật JDK hoặc dùng `ActiveProcessorCount`. Lặp lại benchmark dưới workload tương tự, có so sánh trước/sau và rollback. Không thay nhiều biến cùng lúc nếu muốn tìm nguyên nhân.

### 17.1. Không mặc định `availableProcessors()` cập nhật mọi lúc

Một số thông tin về tài nguyên có thể thay đổi khi giới hạn container được cập nhật trong lúc JVM đang chạy. Khả năng JVM nhận ra thay đổi và cập nhật những cấu hình ergonomic đã khởi tạo phụ thuộc runtime/version và loại thông số.

**Không cam kết** mọi thread pool sẽ tự co giãn nếu người vận hành đổi CPU limit của một container đang chạy. Hãy kiểm tra runtime thật và có chính sách restart/reconfigure phù hợp khi thay resources.

## 18. Những sai lầm thường gặp

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| `UseContainerSupport` cấp thêm CPU. | Nó chỉ giúp HotSpot đọc thông tin từ kernel. | Resource limits do cgroup/Docker/Kubernetes quản lý. |
| CPU request 500m luôn là limit 0,5 CPU. | Request không phải hard quota. | Đọc `limits.cpu` và cgroup. |
| CPU quota 1500m bắt JVM báo 1,5 processors. | API trả số nguyên. | Có thể báo 2, kernel vẫn enforce 1,5 CPU. |
| `availableProcessors=2` chứng minh pod có 2 cores độc quyền. | Nó không phải CPU entitlement. | Xem quota, cpuset, affinity. |
| `cpu.shares/1024` dùng được trên Java 25. | JDK 19 đã bỏ CPU shares khỏi default active count. | Dựa trên quota/cpuset/affinity. |
| Bật `UseContainerSupport` nghĩa cgroup v2 chắc chắn được đọc đúng. | Tùy JDK/update, mounts/permissions và hierarchy. | Xem logs và system metrics. |
| Tắt `UseContainerSupport` sẽ làm mọi ứng dụng nhanh hơn. | Có thể tạo sai CPU/heap defaults. | Chỉ thay khi có chứng cứ và benchmark. |
| `ActiveProcessorCount=8` tạo 8 cores cho pod. | Không thay quota của kernel. | Chỉ chỉnh JVM ergonomic count. |
| Mọi OS nhận `UseContainerSupport`. | Oracle docs giới hạn cơ chế này cho Linux. | Trên Windows thử override CPU riêng. |
| `lscpu` trên host thay được `Runtime.availableProcessors()`. | CPU topology khác quota/cpuset. | Hỏi JVM trong container thật. |
| `nproc` luôn tính CPU quota như HotSpot. | Nó có thể chỉ phản ánh affinity. | Đối chiếu cả cgroups. |
| CPU request thấp luôn buộc JVM dùng ít workers. | Shares không mặc định là hard CPU limit. | Đo concurrency và throttling. |
| CPU throttling không thể xảy ra khi JVM báo 2 processors. | Quota 1,5 vẫn có thể throttle. | Xem `cpu.stat`. |
| ForkJoin common pool luôn đúng bằng activeProcessorCount. | Có heuristic và system properties. | Kiểm tra pool thực tế. |
| Mọi framework auto-size threads theo `ActiveProcessorCount`. | Có thư viện dùng config riêng. | Kiểm tra framework/executor docs. |
| `Runtime.maxMemory()` là cgroup memory limit. | Là max Java heap. | Đọc container memory metrics. |
| `MaxRAMPercentage=60` luôn an toàn. | Native allocations vẫn tiêu thụ RAM. | Dự phòng metaspace/stacks/direct buffers. |
| Thí nghiệm override trên Windows chứng minh cgroups detection. | Windows không dùng Linux cgroup trong JVM host. | Kiểm chứng trong Linux container. |
| Sửa Java version không cần đo lại. | Cgroup/JVM ergonomics thay đổi theo build. | Đo và lưu JDK metadata. |
| `availableProcessors` là CPU usage. | Nó không đo CPU đang bận. | Dùng process/cgroup monitoring. |

## 19. Bài tập có đáp án

**Câu 1.** `UseContainerSupport` là cơ chế gì?

**Đáp án:** Là cơ chế HotSpot Linux nhận diện các giới hạn CPU/memory của cgroup để điều chỉnh resource ergonomics. Nó không tự cấp CPU hay sửa quota.

**Câu 2.** Kubernetes đặt `requests.cpu=500m` và không đặt CPU limit. JVM Java 25 có bắt buộc báo 1 processor không?

**Đáp án:** Không. Request là nhu cầu scheduling/trọng số chia sẻ, không phải hard quota. Từ JDK 19, CPU shares không mặc định quyết định active processor count.

**Câu 3.** `cpu.max` là `150000 100000`. CPU budget trung bình là bao nhiêu?

**Đáp án:** 1,5 CPU. Nếu cpuset đủ rộng, HotSpot có thể ước lượng 2 active processors, nhưng vẫn có throttling nếu workload dùng quá 1,5 CPU time trung bình.

**Câu 4.** `cpuset.cpus.effective=0-1` còn quota cho 4 CPUs. JVM có thể chạy trên 4 logical CPUs riêng biệt không?

**Đáp án:** Không, cpuset chỉ cho CPUs 0 và 1 theo cấu hình đó. Quota không mở rộng CPU affinity.

**Câu 5.** `-XX:ActiveProcessorCount=8` có làm tăng CPU limit 1000m thành 8000m không?

**Đáp án:** Không. Cgroup limit không đổi; flag chỉ ghi đè số active processors JVM dùng cho heuristic sizing.

**Câu 6.** Vì sao `Runtime.availableProcessors()` không trả 0,5?

**Đáp án:** API trả `int`; đây là processor count cho JVM sizing, không phải fractional CPU entitlement.

**Câu 7.** Cờ nào giúp chẩn đoán cgroup detection chi tiết nhất trong HotSpot Linux?

**Đáp án:** `-Xlog:os+container=trace`, kết hợp `-XshowSettings:system` và đọc cgroup files.

**Câu 8.** Lệnh Java nào cho output `availableProcessors=2` theo ví dụ đã chạy?

**Đáp án:** `java -XX:ActiveProcessorCount=2 ContainerCpuProbe` trên JDK24 thử nghiệm. Đó là thử nghiệm override, không phải cgroups.

**Câu 9.** Khi nào `UseContainerSupport` không được nhận diện trên một JDK hiện đại?

**Đáp án:** Có thể trên JVM/OS ngoài phạm vi được hỗ trợ. Ví dụ OpenJDK24 Windows thử nghiệm đã từ chối flag, phù hợp Oracle docs Linux-only.

**Câu 10.** CPU shares/weight và CPU quota khác nhau thế nào?

**Đáp án:** Shares/weight là trọng số tương đối khi tranh chấp; quota là giới hạn CPU time có thể gây throttling.

**Câu 11.** Pod có memory limit 512 MiB và `Runtime.maxMemory()=256 MiB`. Có phải JVM đọc sai?

**Đáp án:** Chưa thể kết luận. `maxMemory` là Java heap maximum, không phải toàn bộ memory limit của container.

**Câu 12.** Vì sao log `No metrics available for this platform` không luôn có nghĩa JVM lỗi?

**Đáp án:** Có thể chạy Windows/macOS hoặc một runtime không hỗ trợ Linux cgroup metrics, thiếu mounts/permissions, hoặc bản JDK cũ chưa hỗ trợ cgroups version.

**Câu 13.** Container báo 2 active processors nhưng `cpu.stat` cho thấy throttled periods tăng. Mâu thuẫn?

**Đáp án:** Không. Số active processors là integer ergonomic count, còn quota/throttling do kernel thực thi.

**Câu 14.** Nếu GC worker count thấp hơn `availableProcessors`, chắc chắn JVM tính sai?

**Đáp án:** Không. GC chọn worker count còn dựa trên heap, collector, task size, flags và heuristic.

**Câu 15.** Có nên dùng `-XX:-UseContainerSupport` trong production chỉ vì host có nhiều CPUs hơn container?

**Đáp án:** Không. Nó có thể làm heuristic CPU/heap lệch resource limit. Cần lý do, kiểm chứng và rollback.

**Câu 16.** Đổi CPU limit khi JVM đang chạy có bảo đảm mọi executor tự chỉnh số worker?

**Đáp án:** Không. Có những cấu hình/giá trị được chọn lúc startup, còn hành vi cập nhật runtime phụ thuộc JVM/version/framework.

## 20. Checklist dùng trong deployment

- [ ] Tôi xác nhận **JDK vendor/build**, Linux kernel và cgroup v1/v2 của container.
- [ ] Tôi biết `UseContainerSupport` mặc định bật trên HotSpot Linux có hỗ trợ.
- [ ] Tôi không dùng flag này như một công cụ cấp quota hoặc tạo CPU.
- [ ] Tôi phân biệt **CPU request**, **CPU limit**, **shares/weight**, **quota** và **cpuset**.
- [ ] Tôi không dùng cách suy CPU shares kiểu Java 10 trên JDK hiện đại.
- [ ] Tôi hiểu số processors JVM báo là integer, có thể làm tròn quota 1,5 thành 2.
- [ ] Tôi không suy ra CPU usage hoặc số physical cores độc quyền từ `availableProcessors()`.
- [ ] Tôi kiểm tra `-XX:ActiveProcessorCount` có bị set trong startup flags không.
- [ ] Tôi dùng `Runtime.availableProcessors()` để đọc số processors JVM thực sự báo.
- [ ] Tôi xem `-XshowSettings:system` và `-Xlog:os+container=trace` **trong Linux container thật**.
- [ ] Tôi đối chiếu `cpu.max`/`cpu.cfs_quota_us`, `cpuset.cpus.effective` và cgroup hierarchy.
- [ ] Tôi đọc throttling metrics theo thời gian, không chỉ CPU count.
- [ ] Tôi biết GC/JIT/ForkJoin/ứng dụng có thể có thread heuristics khác nhau.
- [ ] Tôi không coi `Runtime.maxMemory()` là cgroup memory limit.
- [ ] Tôi dự phòng native memory khi điều chỉnh `MaxRAMPercentage` hay `-Xmx`.
- [ ] Tôi không kết luận cgroup behavior từ thí nghiệm Windows JDK.
- [ ] Tôi benchmark p95/p99 latency, throughput, GC pauses và CPU throttling khi tuning.
- [ ] Tôi lưu đủ JVM arguments và resource configuration để so sánh trước/sau.
- [ ] Tôi không giả định một JDK cũ đã có cùng hỗ trợ cgroups v2 và bug fixes của JDK mới.
- [ ] Tôi chỉ đổi resource/thread limits dựa trên bằng chứng, có kế hoạch kiểm thử và rollback.

## 21. Tài liệu tham khảo chính thức còn áp dụng

1. [Oracle — JDK 10 Release Notes, Java Improvements for Docker Containers](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): `UseContainerSupport`, `ActiveProcessorCount` và các RAM percentage options.
2. [Oracle Java SE 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:-UseContainerSupport` Linux-only, mặc định bật, `-XX:ActiveProcessorCount` và `-Xlog:os+container=trace`.
3. [Oracle Java SE 25 — Runtime.availableProcessors()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): số processors Java runtime báo khả dụng.
4. [Oracle Java SE 25 — OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): Java management processor count.
5. [Oracle JDK 19 Release Notes — JDK-8281181](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html): CPU shares ignored by default when computing active processor count.
6. [OpenJDK JDK-8230305 — cgroups v2 support](https://bugs.openjdk.org/browse/JDK-8230305): support cgroup version 2 trên Linux HotSpot.
7. [Linux Kernel — Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.weight`, `cpu.stat`, `cpuset.cpus.effective` và `memory.max`.
8. [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): semantics resource requests, limits và CPU throttling.
9. [Docker — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): CPU quota, cpuset và memory constraints.
10. [Oracle Java SE 25 — ForkJoinPool](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool parallelism và cấu hình.
11. [AWS Containers — JVM memory, CPU and classpath best practices (2026)](https://aws.amazon.com/blogs/containers/jvm-memory-cpu-and-classpath-best-practices-for-java-containers-on-aws/): những lưu ý hiện hành về JVM/cgroup trong Docker/Kubernetes.

**Kết luận:** **`-XX:+UseContainerSupport`** cho HotSpot Linux nhận diện giới hạn CPU/memory của container để chọn những giá trị JVM phù hợp. Tính năng được cải thiện từ **Java 10** và vẫn quan trọng trong Java hiện đại, nhưng **JDK 19+ không mặc định dùng CPU shares/weight làm số processor được cấp**. Cần phân biệt **quota/period**, **cpuset/affinity**, **CPU requests** và **hard limits**. Một quota **1,5 CPU** vẫn có thể khiến `availableProcessors()` trả **2** do phép làm tròn integer, nhưng quota 1,5 vẫn được kernel thực thi. `-XX:ActiveProcessorCount=N` chỉ ghi đè cách JVM tính CPU, không tạo quota. Khi điều tra hoặc tuning, hãy đọc `-XshowSettings:system`, `-Xlog:os+container=trace`, các cgroup files và CPU-throttling metrics **trong container Linux thật**, thay vì dựa vào host CPU topology hoặc số liệu từ một máy phát triển khác.