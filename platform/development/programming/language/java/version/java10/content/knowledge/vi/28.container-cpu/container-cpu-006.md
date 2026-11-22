# -XX:ActiveProcessorCount và phạm vi ghi đè CPU trong container — Java 10+

## 1. Tình huống: JVM trong container nên dựa vào số CPU nào?

Một host có thể có nhiều CPU logic, trong khi một container chỉ được cấp một phần tài nguyên. Ví dụ host có **28 CPU logic**, nhưng Docker container có CPU quota tương đương **2 CPU**. Nếu JVM dùng số CPU của host để tự chọn quy mô Garbage Collection (GC) workers hoặc các thread pools, nó có thể tạo mức song song quá cao so với CPU budget thực tế. Hệ quả có thể gồm overhead phối hợp, tranh chấp CPU, throttling, giảm throughput hoặc tăng tail latency.

Từ **Java 10**, HotSpot tăng cường nhận biết tài nguyên Docker/Linux container và cung cấp cờ:

```text
-XX:ActiveProcessorCount=N
```

Trong đó `N` là **số processors logic mà HotSpot được yêu cầu sử dụng cho một số phép tính tài nguyên/mức song song**. Đây là một tùy chọn **vẫn được tài liệu Oracle Java 25/27 công nhận** và vẫn có giá trị trên JVM hiện đại.

**Điểm cốt lõi:** `-XX:ActiveProcessorCount=2` **không giới hạn CPU vật lý, không sửa cgroup quota, không tạo hai CPU riêng và không cấm JVM tạo nhiều hơn hai thread**. Nó ghi đè **CPU view** mà JVM dùng cho các quyết định mặc định như kích thước GC workers hoặc ForkJoin common pool.

Ví dụ:

```text
Host:                    28 logical processors
Container CPU quota:      2 CPU-equivalents
-XX:ActiveProcessorCount: 2
HotSpot CPU view:         2 available processors

Kernel vẫn thực thi quota/cpuset độc lập.
```

Nếu JDK mới tự nhận biết đúng CPU quota rồi, **không bắt buộc** đặt cờ này. Hãy sử dụng override khi có mục tiêu cụ thể, được đo lường và ghi rõ trong deployment configuration.

### Mục tiêu

Bài này giúp bạn:

1. Hiểu chính xác ý nghĩa, giới hạn và phạm vi của `-XX:ActiveProcessorCount`.
2. Phân biệt CPU count của JVM với CPU host, CPU affinity/cpuset, quota, requests/limits của Kubernetes.
3. Biết tác động lên `Runtime.availableProcessors()`, `OperatingSystemMXBean`, GC workers và ForkJoinPool.
4. Hiểu vì sao các thread pools có kích thước cấu hình tường minh **không tự giảm xuống N**.
5. Phân biệt CPU override với Linux-only `UseContainerSupport`.
6. Đọc GC startup logs và container resource-detection logs.
7. Chạy ví dụ Java 17+ đã kiểm chứng ở các mức `N=1,2,4`.
8. Hiểu trường hợp cờ chuyên biệt `ParallelGCThreads` hoặc property ForkJoinPool thắng default sizing.
9. Xây dựng kế hoạch benchmark tránh CPU over-subscription và sai số liệu.
10. Chỉ dùng kiến thức **đang còn áp dụng**, không lấy quy tắc CPU shares của JDK 10 làm mặc định bất biến cho JDK hiện tại.

## 2. Định nghĩa đúng: ghi đè CPU view, không ghi đè kernel

Theo hướng dẫn lệnh `java` của Oracle, `-XX:ActiveProcessorCount=x`:

> Ghi đè số CPU mà VM dùng để tính kích thước thread pools cho những thao tác như Garbage Collection và ForkJoinPool.

HotSpot bình thường lấy số CPU khả dụng từ hệ điều hành/container-detection logic. Khi đặt flag, người dùng yêu cầu một con số **explicit** thay vì dựa hoàn toàn vào thuật toán phát hiện tự động.

```bash
java -XX:ActiveProcessorCount=2 -jar app.jar
```

Cờ JVM phải nằm **trước `-jar`** hoặc trước tên main class; nếu đặt phía sau `-jar app.jar`, nó có thể trở thành tham số của ứng dụng thay vì VM option.

### Những việc flag có thể làm

- Khi HotSpot dùng CPU view để tính default, quyết định đó có thể dựa trên N.
- `Runtime.getRuntime().availableProcessors()` trên HotSpot phản ánh CPU view.
- `ManagementFactory.getOperatingSystemMXBean().getAvailableProcessors()` tương đương CPU view của JVM.
- Mức song song mặc định của những library như ForkJoin common pool có thể thay đổi.
- Nhiều con số GC ergonomics (như số GC parallel workers) có thể thay đổi.
- Một số thành phần nội bộ VM và thư viện khác có thể dùng CPU view làm một đầu vào.

### Những việc flag không làm

- **Không thêm CPU** nếu container đã bị quota 2.
- **Không giới hạn affinity/cpuset** thành đúng N CPU IDs.
- **Không bảo đảm chỉ N threads tồn tại**.
- **Không thay** `Executors.newFixedThreadPool(6)` thành 2 khi N=2.
- **Không thay** CPU request/limit trong Kubernetes manifest.
- **Không tự chỉnh heap size** như `-Xmx` hoặc memory cgroup limits.
- **Không thắng tất cả cấu hình chuyên biệt** như `ParallelGCThreads`.
- **Không biến workload CPU-bound thành nhanh hơn** khi N lớn hơn CPU time được cấp.

Vì thế một câu chẩn đoán chuẩn là: “JVM đang dùng CPU view N để chọn một số defaults”, **không phải** “container đã được cấp N core nhờ cờ này”.

## 3. Nền tảng Java 10 và kiến thức hiện hành

Oracle JDK 10 Release Notes ghi nhận **JDK-8146115 — Improve docker container detection and resource configuration usage**: HotSpot học cách xem các giới hạn CPU và memory của Linux/Docker container thay vì chỉ nhìn host.

Cải tiến này đưa vào khả năng tự phát hiện tài nguyên container và flag:

```text
-XX:ActiveProcessorCount=count
```

Oracle mô tả flag này **ghi đè các cơ chế CPU-count detection tự động**.

**Điều vẫn đúng với JDK hiện đại:**

- `ActiveProcessorCount` được tài liệu hóa ở JDK 25/27.
- `UseContainerSupport` xử lý container-aware resource detection trên Linux được hỗ trợ.
- Explicit CPU override được honor ngay cả khi container support không bật.
- VM CPU count ảnh hưởng một số default thread-pool sizing/ergonomics.
- VM option không phải là kernel resource limit.

**Điều không được lấy nguyên từ tài liệu lịch sử:**

- Thuật toán ưu tiên **CPU shares, quota, cpuset** trong một JDK năm 2018 không nhất thiết giống JDK 25/27.
- Khả năng nhận biết **cgroups v1/v2** đã phát triển theo JDK releases/backports.
- Các câu lệnh gắn cờ experimental hoặc runtime JDK 10 đã hết hỗ trợ không phải best practice production mới.
- Kết quả CPU view trên một OS/JDK có thể khác host khác, ngay khi container config thoạt nhìn tương tự.

Nếu đang quản lý ứng dụng ngày nay, hãy xác nhận **vendor, JDK feature/update/build**, OS và container runtime rồi dùng tài liệu đúng phiên bản. Không dùng con số mặc định của JDK cũ làm bằng chứng current behavior.

## 4. CPU quota, cpuset và shares/weights là những thứ khác nhau

Một container Linux có thể được cấu hình tài nguyên theo nhiều cơ chế.

| Cơ chế | Điều nó mô tả | ActiveProcessorCount thay được không? |
| --- | --- | --- |
| Host logical CPUs | Số processors của host | **Không** |
| CPU affinity | Những CPUs tiến trình được OS cho phép chạy | **Không** |
| Cgroup cpuset | Tập CPU IDs được phép sử dụng | **Không** |
| Cgroup quota/period | CPU time tối đa trong các period | **Không** |
| CPU shares/weights | Tỷ trọng tương đối khi tranh chấp | **Không** |
| JVM effective CPU count | CPU view phục vụ sizing/heuristics | **Có**, với HotSpot flag |
| Java thread-pool size tường minh | Số worker do code/config quyết định | **Không bắt buộc** |

Ví dụ trên Docker/Linux:

```bash
docker run --rm --cpus=2 eclipse-temurin:25-jdk java -version
```

`--cpus=2` thường đưa ra quota tương đương hai CPU time units thông qua cgroup scheduling. Điều này **không nhất thiết pin container vào đúng hai CPU logic cụ thể**.

Ngược lại:

```bash
docker run --rm --cpuset-cpus=0-1 eclipse-temurin:25-jdk java -version
```

Chỉ chọn tập CPU IDs 0 và 1. Đây là **affinity restriction**, không phải biểu thức quota giống hệt `--cpus=2`. Hai lệnh trên **minh họa Linux Docker config**, không phải bài test đã chạy ở máy Windows của ví dụ Java.

### CPU shares không phải quota cứng

CPU shares hoặc cgroups v2 weight biểu diễn cơ chế phân chia tương đối dưới cạnh tranh. Nếu các container khác idle, một container có shares thấp vẫn có thể tận dụng CPU thời gian rảnh tùy OS/policy. Ngược lại, một quota cố định tạo ceiling CPU time riêng.

**Không áp đặt công thức** “quota, shares, cpuset luôn lấy min của ba giá trị” cho mọi JDK. Heuristics container detection đã được sửa đổi qua nhiều phiên bản. Khi cần biết máy thực tế tính bao nhiêu CPU, dùng runtime API và log.

## 5. Nếu không đặt flag thì JVM làm gì?

Với một HotSpot JDK mới trên Linux, khi `UseContainerSupport` được hỗ trợ và bật, VM có thể đọc tài nguyên từ cgroups để đưa ra CPU count và memory information. Khi không nằm trong container hoặc không có hỗ trợ, VM lấy thông tin từ hệ điều hành/affinity theo khả năng.

Nếu container có quota 2 và:

```java
System.out.println(Runtime.getRuntime().availableProcessors());
```

in ra **2**, đó có thể đã là auto-detection phù hợp. Không cần mặc định thêm override N=2 chỉ để “bật hỗ trợ container”.

### Trường hợp JVM thấy nhiều CPU hơn CPU budget hữu ích

Nếu benchmark/log chỉ ra VM đang dùng số CPUs quá cao so với resource budget được cấp, có thể cân nhắc:

1. Kiểm tra flag inherited trong base image.
2. Kiểm tra JDK update/container support và cgroups version.
3. Bật logging container detection.
4. Xem CPU quotas, cpuset và weights thực tế.
5. So CPU view với GC/ForkJoin defaults.
6. Chỉ sau đó thử `ActiveProcessorCount=N` theo một giả thuyết cụ thể.

Ưu tiên nâng JDK/distribution được hỗ trợ khi nguyên nhân nằm ở container detection cũ/không hỗ trợ cgroups mới.

## 6. Runtime.availableProcessors() có phản ánh override không?

Java SE cung cấp:

```java
int n = Runtime.getRuntime().availableProcessors();
```

Javadoc mô tả đây là số processors **available to the Java virtual machine**, không nhỏ hơn 1. Giá trị **có thể thay đổi trong một JVM invocation** khi số processors khả dụng thay đổi.

Trên HotSpot, khi đặt `ActiveProcessorCount=N`, trong ví dụ đã chạy:

```text
-XX:ActiveProcessorCount=1 -> availableProcessors() = 1
-XX:ActiveProcessorCount=2 -> availableProcessors() = 2
-XX:ActiveProcessorCount=4 -> availableProcessors() = 4
```

Đây là CPU view, **không phải số CPU vật lý của host**.

Một API quản trị liên quan:

```java
java.lang.management.OperatingSystemMXBean bean =
        java.lang.management.ManagementFactory.getOperatingSystemMXBean();

int n = bean.getAvailableProcessors();
```

Theo Javadoc, `OperatingSystemMXBean.getAvailableProcessors()` tương đương `Runtime.availableProcessors()`; trong thử nghiệm chúng bằng nhau.

### Nếu cgroups thay đổi khi đang chạy thì sao?

API nói CPU availability có thể thay đổi trong đời JVM, nhưng **khi bạn đặt một override số N cố định**, không nên giả định JVM sẽ tự phản ánh quota mới từ cgroup ở mọi lần gọi.

Nếu container có autoscaling/resizing CPU trong lúc chạy, hãy xác nhận behavior trên JDK mục tiêu và cập nhật/redeploy cấu hình nếu cần. Giá trị CPU view cố định có thể trở nên quá thấp hoặc quá cao so với budget mới.

## 7. GC ergonomics: ActiveProcessorCount ảnh hưởng mức mặc định

HotSpot thường dùng CPU count để tính số worker mặc định của GC hoặc những thành phần runtime khác. Nhưng không phải mọi collector/pha đều dùng công thức bằng N.

Một cách kiểm tra trên HotSpot G1:

```bash
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 -Xms64m -Xmx64m -Xlog:gc+init=info -version
```

**Trích đoạn log đã được kiểm chứng với Zulu OpenJDK 24.0.2 chạy trên Windows:**

```text
[info][gc,init] CPUs: 28 total, 2 available
[info][gc,init] Heap Region Size: 1M
[info][gc,init] Parallel Workers: 2
[info][gc,init] Concurrent Workers: 1
```

Kết quả có ý nghĩa:

- Host được báo là **28 total CPUs**.
- CPU view HotSpot sử dụng là **2 available**.
- G1 chọn **2 Parallel Workers** và **1 Concurrent Worker** theo thông số thử.

**Không lấy các giá trị worker này làm định luật** “ParallelGCThreads luôn bằng ActiveProcessorCount”, vì HotSpot áp heuristic/capping theo collector, tài nguyên và các VM flags khác.

### Cấu hình chuyên biệt có thể thắng số CPU làm mặc định

Chạy:

```bash
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 -XX:ParallelGCThreads=4 -Xms64m -Xmx64m -Xlog:gc+init=info -version
```

**Trích đoạn thực nghiệm:**

```text
[info][gc,init] CPUs: 28 total, 2 available
[info][gc,init] Parallel Workers: 4
[info][gc,init] Concurrent Workers: 1
```

Tức **CPU view vẫn là 2, nhưng số Parallel GC Workers là 4** do flag riêng. Đây là bằng chứng trực tiếp rằng `ActiveProcessorCount` **không phải hard cap cho mọi subsystem threads**.

### Hệ quả khi sizing sai

- Worker quá nhiều so với CPU quota: có thể gây contention, context switching, memory bandwidth pressure và CPU throttling.
- Worker quá ít so với CPU budget: có thể kéo dài GC pauses hoặc làm giảm throughput.
- Tăng worker không bảo đảm pause giảm tuyến tính.
- G1 có thể dùng concurrent marking và nhiều pha khác với worker counts không giống Parallel Workers.

Do đó cần đo **GC pause real time**, không chỉ số workers. Đặc biệt, CPU time tổng của nhiều GC worker có thể lớn hơn wall-clock pause.

## 8. ForkJoinPool và những tác vụ Java dùng default parallelism

Trong Java:

```java
int commonParallelism =
        java.util.concurrent.ForkJoinPool.getCommonPoolParallelism();
```

Common pool có một mặc định parallelism chịu ảnh hưởng của CPU availability trên HotSpot JDK thông dụng. Trong thí nghiệm:

| `ActiveProcessorCount` | `Runtime.availableProcessors()` | `ForkJoinPool.getCommonPoolParallelism()` |
| ---: | ---: | ---: |
| 1 | 1 | 1 |
| 2 | 2 | 1 |
| 4 | 4 | 3 |

**Cảnh báo:** Không coi `ForkJoinPool=ActiveProcessorCount-1` là công thức vĩnh viễn. Common pool có heuristics, properties và implementation riêng; tối thiểu cũng có những edge cases khi CPU view nhỏ.

Một số thư viện Java như parallel streams và asynchronous tasks có thể dùng common pool khi không chọn executor khác. Nhưng **không hứa** rằng toàn bộ tác vụ `CompletableFuture`/`parallelStream` chỉ chạy đúng N threads. Có thể có fallback hoặc executor chuyên biệt và số task không phải số worker sống.

### Property riêng có thể ghi đè mức default

Dùng:

```bash
java -XX:ActiveProcessorCount=4 -Djava.util.concurrent.ForkJoinPool.common.parallelism=1 ActiveProcessorCountDemo
```

Đo được:

```text
runtimeAvailable=4
mxBeanAvailable=4
sameJvmCpuView=true
commonPoolParallelism=1
fixedPoolCoreSize=6
fixedPoolUnaffected=true
```

Nghĩa là:

- HotSpot vẫn báo **4 CPUs available**.
- ForkJoin common pool parallelism **1**, vì property riêng.
- Fixed thread pool **6**, vì code tự cấu hình.

**ActiveProcessorCount ảnh hưởng mặc định của những nơi tham chiếu CPU view, không ghi đè các thiết lập mức song song được cung cấp trực tiếp.**

## 9. Fixed thread pool không bị ActiveProcessorCount ép lại

Ví dụ:

```java
java.util.concurrent.ThreadPoolExecutor pool =
    (java.util.concurrent.ThreadPoolExecutor)
        java.util.concurrent.Executors.newFixedThreadPool(6);
```

Nếu JVM chạy với `ActiveProcessorCount=2`, `pool.getCorePoolSize()` vẫn là **6**. Trong chương trình minh họa ta không submit task, vì vậy kết quả này **chỉ đo core pool size được cấu hình**, không tuyên bố đã tạo sẵn sáu OS threads.

Tương tự:

- `Executors.newFixedThreadPool(32)` không tự thu về 2.
- HTTP server/application framework executor có cấu hình tường minh vẫn có thể tạo nhiều workers.
- Một số framework tính **mặc định** từ `availableProcessors()`, nên có thể chịu ảnh hưởng gián tiếp.
- Connection pools/semaphores/request concurrency không được tự chỉnh chỉ do ActiveProcessorCount.
- JVM có thể có số lượng VM/GC/compiler threads khác nhau theo cờ riêng.

Với Java 21+ virtual threads, số virtual threads không đồng nghĩa số carrier/platform threads. ActiveProcessorCount có thể tác động tới một số default trong scheduler tùy JDK, **không có nghĩa chỉ N virtual threads được phép tồn tại**.

## 10. UseContainerSupport là một tính năng khác — chủ yếu trên Linux

HotSpot có flag:

```text
-XX:+UseContainerSupport
-XX:-UseContainerSupport
```

Theo tài liệu Oracle **Linux-only**, tính năng này giúp phát hiện giới hạn CPU và memory của container. Mặc định thường bật khi được hỗ trợ.

`-XX:ActiveProcessorCount=N` là **một override CPU count riêng**. Oracle nêu rõ nó vẫn được honor ngay cả khi `UseContainerSupport` không được bật.

Trên **Linux JVM được hỗ trợ**, có thể minh họa:

```bash
java -XX:-UseContainerSupport -XX:ActiveProcessorCount=2 -jar app.jar
```

CPU view vẫn là 2 theo tài liệu, nhưng **không nên tùy tiện tắt UseContainerSupport trong production** vì JVM có thể mất cơ chế nhận biết memory limits của container.

### Điều kiện rất quan trọng trên Windows

Trong môi trường thử với **Zulu OpenJDK 24.0.2 Windows**, JVM chạy bình thường với `-XX:ActiveProcessorCount=1/2/4`. Nhưng khi thử:

```text
-XX:-UseContainerSupport
```

JVM từ chối:

```text
Unrecognized VM option 'UseContainerSupport'
Could not create the Java Virtual Machine.
```

Đó là vì tài liệu Oracle ghi container-support detection option có phạm vi **Linux-only**. Nếu chạy Docker Desktop trên Windows nhưng container chứa **Linux JVM**, chính JVM Linux bên trong image là bên xử lý `UseContainerSupport`, không phải Java Windows native của host.

**Không copy cờ Linux-only vào mọi lệnh Java đa nền tảng**. Kiểm tra docs và `java -XX:+PrintFlagsFinal -version` trên chính runtime.

## 11. Chương trình Java 17+ chạy được: kiểm chứng phạm vi ghi đè

Tạo file **`ActiveProcessorCountDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ThreadPoolExecutor;

public final class ActiveProcessorCountDemo {
    public static void main(String[] args) {
        int jvmCpus = Runtime.getRuntime().availableProcessors();
        int mxCpus = ManagementFactory
                .getOperatingSystemMXBean().getAvailableProcessors();
        int common = ForkJoinPool.getCommonPoolParallelism();

        ThreadPoolExecutor manuallySized =
                (ThreadPoolExecutor) Executors.newFixedThreadPool(6);
        try {
            System.out.println("runtimeAvailable=" + jvmCpus);
            System.out.println("mxBeanAvailable=" + mxCpus);
            System.out.println("sameJvmCpuView=" + (jvmCpus == mxCpus));
            System.out.println("commonPoolParallelism=" + common);
            System.out.println("fixedPoolCoreSize=" + manuallySized.getCorePoolSize());
            System.out.println("fixedPoolUnaffected=" +
                    (manuallySized.getCorePoolSize() == 6));
        } finally {
            manuallySized.shutdown();
        }
    }
}
```

Biên dịch với JDK có thể target Java 17:

```bash
javac --release 17 ActiveProcessorCountDemo.java
```

Chạy ba mức CPU view:

```bash
java -XX:ActiveProcessorCount=1 ActiveProcessorCountDemo
java -XX:ActiveProcessorCount=2 ActiveProcessorCountDemo
java -XX:ActiveProcessorCount=4 ActiveProcessorCountDemo
```

### Stdout chính xác đã chạy trên Zulu OpenJDK 24.0.2

**N=1**

```text
runtimeAvailable=1
mxBeanAvailable=1
sameJvmCpuView=true
commonPoolParallelism=1
fixedPoolCoreSize=6
fixedPoolUnaffected=true
```

**N=2**

```text
runtimeAvailable=2
mxBeanAvailable=2
sameJvmCpuView=true
commonPoolParallelism=1
fixedPoolCoreSize=6
fixedPoolUnaffected=true
```

**N=4**

```text
runtimeAvailable=4
mxBeanAvailable=4
sameJvmCpuView=true
commonPoolParallelism=3
fixedPoolCoreSize=6
fixedPoolUnaffected=true
```

**Giải thích:**

1. `Runtime.availableProcessors()` đúng bằng CPU override.
2. `OperatingSystemMXBean.getAvailableProcessors()` trả cùng CPU view.
3. ForkJoin common pool thay đổi parallelism mặc định khi tăng CPU view từ 2 lên 4.
4. ThreadPoolExecutor có core size **6** ở cả ba lần chạy vì app tự chọn kích thước.
5. Chương trình không submit task vào fixed pool, nên nó **không đếm số OS threads được tạo thực tế**.
6. Demo chạy trên Windows native, **không cần container**, vì mục tiêu là chứng minh cách HotSpot xử lý ActiveProcessorCount.
7. Dữ liệu ForkJoin/GC workers là **kết quả quan sát**, có thể khác nếu property/cờ riêng hoặc bản JDK khác được dùng.

## 12. Kiểm tra trong Linux Docker/container

Lệnh minh họa sau yêu cầu Docker có image JDK phù hợp; **chưa được thực thi ở môi trường thử Windows của bài**:

```bash
docker run --rm --cpus=2 --memory=512m \
  eclipse-temurin:25-jdk \
  java -XX:ActiveProcessorCount=2 -Xlog:os+container=info -version
```

Mục đích:

- Docker có CPU quota hai CPU-equivalents.
- Docker có memory ceiling 512 MiB.
- HotSpot được chỉ định CPU view bằng 2.
- JVM có thể ghi log container detection nếu OS, runtime và log level hỗ trợ.

Muốn kiểm tra **auto-detection thay vì ép N**:

```bash
docker run --rm --cpus=2 --memory=512m \
  eclipse-temurin:25-jdk \
  java -Xlog:os+container=trace -version
```

Oracle khuyên `-Xlog:os+container=trace` khi cần chẩn đoán sâu; các nội dung log phụ thuộc build. Cần đối chiếu với `Runtime.availableProcessors()` chạy **bên trong container**, không chỉ chạy Java trên host rồi suy ra.

### Ba lựa chọn trên cùng quota 2 CPU

| Trường hợp | `ActiveProcessorCount` | Ý nghĩa |
| --- | --- | --- |
| A | Không đặt | JVM tự phát hiện resources |
| B | 2 | JVM được yêu cầu dùng CPU view 2 |
| C | 4 | JVM dùng CPU view 4 nhưng quota OS vẫn 2 |

Trong C, VM có thể tạo nhiều workers hơn budget hiệu quả, dẫn đến contention/throttling; **không có thêm CPU thực**. Ngược lại, N thấp hơn quota có thể khiến một số pool không khai thác hết tài nguyên. Không có cấu hình tối ưu cố định cho mọi workload.

## 13. Kubernetes: request, limit và JAVA_TOOL_OPTIONS

Trong Kubernetes:

- `resources.requests.cpu` là mức CPU được dùng cho scheduling/relative resource allocation.
- `resources.limits.cpu` áp một giới hạn tài nguyên CPU phù hợp với cơ chế OS/container runtime.
- `ActiveProcessorCount` quyết định **VM CPU view** cho một số heuristics; không thay requests/limits.

Ví dụ một fragment định nghĩa container:

```yaml
resources:
  requests:
    cpu: "1"
  limits:
    cpu: "2"
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-XX:ActiveProcessorCount=2"
```

Đây là **fragment YAML**, chưa phải Pod/Deployment hoàn chỉnh. JVM có thể nhận JVM options từ `JAVA_TOOL_OPTIONS`. Tuy nhiên phải kiểm tra launcher/buildpack/entrypoint cụ thể để tránh cấu hình trùng hoặc thứ tự options không như mong đợi.

**Không suy rằng requests.cpu=1 bắt buộc JVM báo 1 CPU.** Khi container có quota 2, cpuset, shares/weights và quy tắc JDK hiện hành quyết định auto-detection. Chỉ các phép đo thực mới cho CPU view cuối cùng.

### Nhiều JVM cùng nằm trong một cgroup

Nếu hai JVM cùng chia cgroup quota 4 CPU, cả hai có thể mỗi JVM **nhìn thấy CPU budget 4**, dù tổng budget vẫn là 4. Có thể thử gán N=2 cho mỗi JVM để giảm default oversubscription. Nhưng đây chỉ là **tuning JVM**, không phải chia quota OS cứng cho từng process; nếu cần isolation thực, hãy thiết kế cgroup/container placement riêng.

## 14. Cấu hình tường minh của subsystem có thể thắng CPU-based defaults

Một sơ đồ tư duy:

```text
OS/affinity/cgroup quota
          |
          v
HotSpot auto CPU detection
          |
          +-- -XX:ActiveProcessorCount=N ?
          |         |
          |         +--> JVM CPU view = N
          |
          v
Defaults/ergonomics cho GC, ForkJoin và một số thành phần
          |
          +-- subsystem-specific override ?
          |       |- ParallelGCThreads=...
          |       |- ForkJoin common.parallelism=...
          |       |- Thread pool size trong app...
          |       +--> giá trị chuyên biệt được dùng
          |
          v
OS scheduler thực thi CPU quota/cpuset độc lập
```

Đây là sơ đồ khái niệm, không phải các bước C++ nội bộ của mọi bản HotSpot.

**Phân cấp ý tưởng:**

- Cgroup quy định **resource envelope thực**.
- ActiveProcessorCount ghi đè **CPU estimate của VM**.
- Subsystem có thể dùng estimate để sizing default.
- Một giá trị **cấu hình riêng** có thể ưu tiên hơn default của subsystem.
- OS vẫn thực thi quota/affinity khi threads thật sự được chạy.

Vì vậy, nếu bạn thấy `availableProcessors()==2` nhưng G1 dùng 4 workers, không nhất thiết có lỗi: hãy xem có `ParallelGCThreads=4` hay không.

## 15. Cách xác minh JVM đang sử dụng giá trị nào

**Xem phiên bản và flags:**

```bash
java --version
java -XX:ActiveProcessorCount=2 -XX:+PrintFlagsFinal -version
```

Với HotSpot, dùng output để kiểm tra những flag được nhận diện/effective. Không suy từ docs của một JDK khác rằng mọi JVM đều hỗ trợ y hệt.

**Xem CPU count từ Java:**

```java
System.out.println(Runtime.getRuntime().availableProcessors());
```

**Xem GC init workers:**

```bash
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 -Xlog:gc+init=info -version
```

Xem `CPUs: ... available`, `Parallel Workers`, `Concurrent Workers` trên JVM/collector cụ thể.

**Xem cgroups trên Linux:**

```bash
java -Xlog:os+container=trace -version
```

Phân tích quota, cpuset và memory limits tương ứng; đường dẫn file cgroups khác giữa v1/v2. Đừng dựa vào log Windows native để kiểm tra Linux cgroups.

**Xem application pools:** Kiểm tra effective config của Tomcat/Netty/Spring/Executors/ForkJoin, thay vì suy mọi executor tự điều chỉnh theo ActiveProcessorCount.

## 16. Khi nào nên override và khi nào nên để mặc định?

### Nên cân nhắc override khi

- JDK auto-detection cho CPU view không phù hợp với **resource budget thực** hoặc mục tiêu isolation mềm của nhiều JVM.
- Muốn kiểm chứng một giả thuyết performance về GC/ForkJoin default sizing.
- Framework tự xây executor dựa vào `availableProcessors()` và cần một giá trị nhất quán.
- Có nhiều JVM chung cgroup và cần phân chia mức song song **theo logic**, đồng thời hiểu OS quota không thay đổi.
- Cần tái lập một phép thử trên các máy có số CPU host khác nhau mà vẫn giữ CPU view như nhau.

### Không nên override theo phản xạ khi

- Container auto-detection của JDK mới đã đúng.
- Chưa quan sát vấn đề throughput, latency hoặc thread oversubscription.
- Muốn thay OS CPU limit/affinity.
- Muốn sửa memory leak, OutOfMemoryError hoặc GC pause do heap pressure mà chưa chẩn đoán.
- Muốn sửa pool size đã hard-code mà không thay cấu hình pool.
- Đang chọn N dựa vào số CPU host thay vì quota thật hoặc benchmark.
- N bị giữ cố định trong cấu hình nhưng CPU budget của pod thường xuyên thay đổi.

**Nguyên tắc:** Bắt đầu với default của JDK còn được hỗ trợ; đặt flag sau khi có bằng chứng, đo lại và ghi lý do.

## 17. N thấp, bằng hoặc cao hơn budget: tradeoff

| CPU budget cgroup | N | Lợi ích/rủi ro có thể có |
| ---: | ---: | --- |
| 2 | 1 | Ít default workers hơn; có thể giảm overhead nhưng cũng giảm throughput |
| 2 | 2 | CPU view sát budget, thường là baseline hợp lý |
| 2 | 4 | Có thể oversubscribe CPU, tăng throttling hoặc overhead |
| 4 | 2 | Có thể giảm GC/parallel compute concurrency, không tận dụng hết CPU |
| 4 | 4 | CPU view và budget tương ứng |
| 4 | 8 | Có thể dư workers; một số workload blocking có lợi nhưng CPU-bound dễ cạnh tranh |

**Không có định lý “N bằng quota là tối ưu”**. CPU budget là một số đại diện về CPU time, còn thread scheduling, blocking I/O và workload shape vẫn rất khác nhau. Kể cả hai ứng dụng cùng 2 CPU quota, một có allocation rate cao và một chủ yếu chờ I/O có thể cần cấu hình khác.

Khi N lớn hơn budget, kiểm tra:

- Cgroup throttling time/count.
- JVM CPU user/system time và host scheduling.
- Request queueing, p95/p99 response latency.
- GC pauses và số parallel/concurrent workers.
- ForkJoin task throughput và backlog.

Khi N nhỏ hơn budget, kiểm tra CPU idle, throughput và thời gian hoàn thành các tác vụ CPU-bound để tránh làm chậm ứng dụng không cần thiết.

## 18. Benchmark có trách nhiệm

Một quy trình thử nghiệm tốt:

1. Cố định JDK feature/update/build và distribution.
2. Cố định CPU quota, cpuset, memory limit và heap sizing.
3. Chạy baseline **không override**, ghi CPU view/worker sizes.
4. Chạy các giá trị N hợp lý, ví dụ 1/2/4, với workload đại diện.
5. Không đồng thời thay collector, `-Xmx` và thread-pool settings.
6. Warmup theo đúng đặc tính ứng dụng; chạy đủ nhiều lần.
7. Đo throughput, request p95/p99/p99.9, CPU utilization, throttling, GC wall-clock pauses và queue sizes.
8. Xác nhận JVM đã nhận flag qua runtime API/GC logs.
9. Đánh giá tradeoff CPU, memory, latency và cost.
10. Nếu override không tạo lợi ích nhất quán, cân nhắc quay lại auto-detection.

### Vì sao CPU throttling có thể làm p99 xấu?

Trong cgroup có quota, khi CPU time của period cạn, các runnable threads bị throttle chờ period mới. Số workers lớn không tự đem thêm CPU, có thể làm CPU budget cạn nhanh hơn. Nếu p99 tăng, cần đối chiếu throttling với thread pools và tracing.

**Nhưng không quy mọi throttling cho ActiveProcessorCount.** Công việc CPU-bound thực sự quá tải cũng sẽ throttle dù N đặt đúng. Có thể phải tối ưu thuật toán, giảm work per request, phân bổ thêm CPU hoặc hạn chế concurrency.

## 19. Những sai lầm phổ biến

**Sai 1 — “N=2 nghĩa là tiến trình bị OS ép chỉ dùng 2 core.”** Không. OS CPU limit/cpuset được cấu hình độc lập.

**Sai 2 — “Container quota 2, N=8 sẽ tăng capacity lên 8.”** Không; kernel vẫn cấp CPU time theo quota thực.

**Sai 3 — “N=2 cấm JVM tạo hơn 2 threads.”** Không; pool và runtime có thể có nhiều threads.

**Sai 4 — “N=2 làm Executors.newFixedThreadPool(6) thành 2.”** Không; thread-pool size cấu hình tường minh vẫn là 6.

**Sai 5 — “ParallelGCThreads luôn bằng N.”** Không; collector heuristics và cờ chuyên biệt có thể thay đổi.

**Sai 6 — “ParallelGCThreads=4 bị ActiveProcessorCount=2 ghi đè.”** Sai. Log thử có CPU view 2 nhưng G1 Parallel Workers 4.

**Sai 7 — “ForkJoin common parallelism bằng N tuyệt đối.”** Sai; default heuristic/property riêng có thể khác.

**Sai 8 — “availableProcessors() chính là số CPU vật lý của host.”** Không; nó là số CPU JVM xem khả dụng.

**Sai 9 — “Không bật UseContainerSupport thì ActiveProcessorCount không có hiệu lực.”** Sai trên Linux HotSpot theo tài liệu Oracle; override vẫn được honor.

**Sai 10 — “UseContainerSupport flag luôn có trên Java Windows.”** Không; JVM Windows native của demo đã từ chối flag này.

**Sai 11 — “CPU request trong Kubernetes luôn giới hạn CPU time.”** Không; request chủ yếu phục vụ scheduling, khác CPU limit.

**Sai 12 — “CPU shares của Java 10 được xử lý y hệt trên JDK 27.”** Không thể khẳng định; container-detection heuristics đã thay đổi.

**Sai 13 — “Đặt N sẽ sửa được -Xmx hoặc RAM quota.”** Không; CPU và memory là những giới hạn riêng.

**Sai 14 — “N càng thấp luôn càng nhanh vì ít tranh CPU.”** Không; có thể thiếu song song và giảm throughput.

**Sai 15 — “N càng cao luôn càng nhanh vì có nhiều workers.”** Không; oversubscription có thể làm giảm hiệu quả.

**Sai 16 — “Chỉ xem Runtime.availableProcessors là đủ biết mọi pool.”** Không; phải xem config/framework worker sizes riêng.

**Sai 17 — “JDK hỗ trợ ActiveProcessorCount nghĩa là mọi JVM vendor đều nhận cờ.”** Đây là option của HotSpot; VM khác cần kiểm chứng.

**Sai 18 — “Auto-detection đúng nhưng vẫn bắt buộc set N trong mọi container.”** Không cần; override nên có lý do đo lường.

## 20. Checklist trước khi đưa vào production

- [ ] Xác định JDK vendor, version, build và OS của JVM đang chạy.
- [ ] Dùng HotSpot và kiểm tra flag ActiveProcessorCount được hỗ trợ.
- [ ] Biết ActiveProcessorCount chỉ ghi đè **JVM CPU view**.
- [ ] CPU quota/cpuset được cấu hình tại OS/Docker/Kubernetes nếu cần hard limit.
- [ ] Đã kiểm tra cgroups version và `UseContainerSupport` trên Linux.
- [ ] Không sao chép các quy tắc CPU shares cũ vào JDK mới.
- [ ] Đọc `Runtime.availableProcessors()` thực tế.
- [ ] Đọc GC init log về CPUs/Parallel Workers.
- [ ] Biết `ParallelGCThreads` hay cờ GC riêng có được đặt không.
- [ ] Biết ForkJoin common pool có property riêng không.
- [ ] Đã kiểm tra pool thủ công/framework có kích thước không phụ thuộc CPU view.
- [ ] Không dùng flag CPU để cố sửa memory/heap limits.
- [ ] Nếu dùng virtual threads, phân biệt virtual thread count với carrier scheduling.
- [ ] So sánh baseline auto-detection và override cùng workload.
- [ ] Đo CPU utilization/throttling, GC pause, p99/p99.9, throughput.
- [ ] Tránh giữ một N cứng qua nhiều môi trường không có cùng quota.
- [ ] Nếu nhiều JVM dùng chung cgroup, xem tổng concurrency chứ không nhìn riêng từng JVM.
- [ ] Khi quota CPU thay đổi, đánh giá lại override và thread-pool defaults.
- [ ] Không tắt Linux container support chỉ để thử nếu việc tắt làm memory sizing sai.
- [ ] Ghi lại kết quả benchmark và lý do tồn tại của flag trong deployment config.

## 21. Câu hỏi tự kiểm tra và đáp án

**1. ActiveProcessorCount là CPU limit hay JVM CPU-count override?**

**Đáp án:** Là **JVM CPU-count override** phục vụ một số quyết định sizing/ergonomics, không phải kernel CPU limit.

**2. Container có quota hai CPU, N=4 có giúp dùng bốn core như không có quota không?**

**Đáp án:** Không. Kernel vẫn thực thi quota; N=4 chỉ ảnh hưởng cách JVM chọn các defaults.

**3. `availableProcessors()` có phản ánh ActiveProcessorCount không?**

**Đáp án:** Có trên HotSpot, demo N=1/2/4 cho kết quả 1/2/4 tương ứng.

**4. OperatingSystemMXBean có nhất thiết báo CPU vật lý host không?**

**Đáp án:** Không; method getAvailableProcessors() tương đương CPU availability của JVM.

**5. Vì sao common pool báo parallelism=3 khi N=4 trong demo?**

**Đáp án:** Default ForkJoinPool có heuristic riêng dựa vào CPU view; không đồng nghĩa số CPU hoặc số tasks tối đa.

**6. Nếu đặt property common.parallelism=1 khi N=4, pool dùng gì?**

**Đáp án:** Demo xác nhận common parallelism=1, dù JVM CPU view vẫn 4.

**7. N=2 có đổi fixed thread pool 6 thành 2 không?**

**Đáp án:** Không. Pool được cấu hình 6 vẫn có core pool size 6.

**8. Có thể thấy Parallel GC Workers=4 khi CPU view=2 không?**

**Đáp án:** Có khi đặt thêm `-XX:ParallelGCThreads=4`; log đã kiểm chứng.

**9. `UseContainerSupport` dùng trên mọi Windows JVM không?**

**Đáp án:** Không. Oracle mô tả nó Linux-only; trong thí nghiệm JVM Windows không nhận cờ đó.

**10. ActiveProcessorCount còn hiệu lực trên Linux khi UseContainerSupport bị tắt không?**

**Đáp án:** Có theo tài liệu Oracle; explicit CPU override vẫn được honor.

**11. Quota khác cpuset như thế nào?**

**Đáp án:** Quota hạn chế CPU time; cpuset giới hạn tập CPU IDs được phép chạy. JVM CPU override không thay cả hai.

**12. CPU request Kubernetes có phải hard limit không?**

**Đáp án:** Không. CPU request chủ yếu phục vụ scheduler/resource allocation; CPU limit định nghĩa ceiling CPU phù hợp.

**13. Vì sao không lấy công thức CPU shares của Java 10 làm mặc định JDK 27?**

**Đáp án:** Hệ thống container detection và heuristic đã thay đổi, cần kiểm chứng phiên bản JDK đang chạy.

**14. Có cần đặt flag nếu JDK tự nhận quota chính xác và không có vấn đề hiệu năng?**

**Đáp án:** Không bắt buộc; chỉ override khi có mục tiêu được chứng minh.

**15. Hai JVM trong chung cgroup quota 4 có mặc nhiên mỗi JVM được 4 CPU riêng không?**

**Đáp án:** Không. Cả hai tranh cùng budget; CPU view không chia quota cứng.

**16. ActiveProcessorCount có sửa memory leak hoặc OutOfMemoryError không?**

**Đáp án:** Không. CPU-count override không tăng RAM, không thay `-Xmx` và không sửa lỗi giữ references.

**17. N=1 chắc chắn là tối ưu latency với một CPU quota không?**

**Đáp án:** Không. Phải đo CPU, blocking, GC, queueing, throughput và tail latency trên workload thực.

**18. Đo những gì trước khi quyết định giữ override?**

**Đáp án:** Runtime CPU view, cgroup quota/cpuset, GC/ForkJoin/default pool sizes, CPU throttling/utilization, throughput và p95/p99/p99.9 latency.

## 22. Tài liệu chính thức hiện còn áp dụng

1. [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): định nghĩa `-XX:ActiveProcessorCount`, `UseContainerSupport` và `-Xlog:os+container=trace`.
2. [Oracle Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): flag vẫn được hỗ trợ trong tài liệu JDK hiện đại.
3. [Oracle JDK 10 Release Notes — Java Improvements for Docker Containers](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): mốc Java 10 và JDK-8146115.
4. [Java SE 25 — Runtime.availableProcessors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): processors available to JVM, có thể thay đổi.
5. [Java SE 25 — OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): getAvailableProcessors tương đương số processors khả dụng đối với JVM.
6. [Java SE 25 — ForkJoinPool](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool parallelism và property được cấu hình.
7. [Java SE 25 — Executors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html): fixed thread pools có kích thước do ứng dụng chọn.
8. [Java SE 25 — G1 GC Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector-tuning.html): ảnh hưởng của GC workers và yêu cầu đo theo workload.
9. [dev.java — Java Application Launcher](https://dev.java/learn/jvm/tools/core/java/): VM options và cách launcher áp dụng cờ Java hiện hành.

**Kết luận:** Từ Java 10 đến các JDK hiện đại, `-XX:ActiveProcessorCount=N` là cơ chế HotSpot để **ghi đè số processors mà JVM dùng cho default sizing và resource ergonomics**. Nó có thể làm đổi `availableProcessors()`, GC workers, ForkJoin common pool; nhưng **không phải CPU quota**, **không tạo thêm CPU**, **không hạn chế số threads** và **không tự ghi đè các cấu hình chuyên biệt**. Trong container, trước hết xác minh auto-detection của JDK được hỗ trợ; chỉ đặt N khi có mục tiêu tuning rõ ràng, kiểm chứng qua GC/ForkJoin logs và số liệu hiệu năng thực.
