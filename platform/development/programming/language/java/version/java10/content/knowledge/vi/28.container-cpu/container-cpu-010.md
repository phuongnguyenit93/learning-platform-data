# Kiểm thử cùng ứng dụng Java với các mức cấp CPU khác nhau trong container

*Chủ đề cha: CPU trong container — Java 10. Bài Knowledge này hướng dẫn thiết kế, chạy, đo và diễn giải một thí nghiệm có kiểm soát: dùng **cùng mã Java, cùng JAR, cùng JDK và cùng workload**, lần lượt giới hạn container ở 0,5 CPU; 1 CPU; 2 CPU; 4 CPU, rồi so sánh số CPU mà HotSpot nhận biết, độ song song, thời gian hoàn thành, throughput, latency và CPU throttling. Mục tiêu là phân biệt **CPU được JVM báo cáo** với **CPU mà kernel thực sự cho tiến trình dùng**, tránh những kết luận sai về requests/limits, quota, cpuset và số luồng. Kiến thức vẫn áp dụng trên JDK hiện đại; chương trình chính biên dịch bằng Java 17+.*

## 1. Câu hỏi cần kiểm thử là gì?

Nếu thay mức CPU của container mà vẫn chạy **cùng ứng dụng**, có ít nhất bốn câu hỏi độc lập:

1. **JVM thấy bao nhiêu CPU?** Kiểm tra `Runtime.getRuntime().availableProcessors()` và các cấu hình liên quan.
2. **JVM/ứng dụng chọn bao nhiêu worker threads?** Có thể thay đổi theo CPU count, nhưng không phải mọi pool đều tự thay kích thước theo cùng một quy tắc.
3. **Kernel thật sự cho tiến trình dùng bao nhiêu thời gian CPU?** Cgroups CPU quota có thể buộc throttling dù tiến trình vẫn chạy các thread trên nhiều logical CPUs.
4. **Kết quả nghiệp vụ và hiệu năng thay đổi thế nào?** Kiểm tra checksum/output đúng và đo thời gian, throughput, latency, CPU usage, throttling trên từng scenario.

Bốn câu hỏi không đồng nghĩa. Ví dụ `availableProcessors()==2` **không bảo đảm** container đang được dành riêng hai CPU vật lý, không ngăn ứng dụng tạo 100 threads, và không làm kernel tự thay cgroup quota nếu bạn sửa JVM flag.

**Nguyên tắc thí nghiệm:** thay **một biến chính là mức CPU được cấp**, giữ những yếu tố khác cố định. Chạy nhiều lần, tránh lấy một số đo may mắn, và luôn ghi cả thông tin JDK + cgroup thực tế.

## 2. Vì sao đây là chủ đề Java 10 nhưng phải áp dụng kiến thức hiện đại?

Từ **JDK 10**, HotSpot cải thiện việc phát hiện CPU/bộ nhớ trong Docker/Linux container qua **JDK-8146115**: sử dụng thông tin cgroup thay vì luôn giả định JVM có toàn bộ tài nguyên của host. `-XX:+UseContainerSupport` được hỗ trợ và thông thường bật mặc định trên HotSpot/Linux, còn `-XX:ActiveProcessorCount=N` cho phép override số processors dùng trong các quyết định ergonomics. Những tính năng này vẫn cần thiết khi chạy Java 17/21/25.

Điểm phải cập nhật:

- Release notes của JDK 10 mô tả cơ chế ban đầu xét **CPU quota, cpuset và CPU shares**.
- Về sau, việc coi `cpu.shares`/CPU request tương đương một số CPU giới hạn được xác định là có thể làm JVM dùng ít CPU hơn mức thực tế cho phép.
- Theo **JDK-8281181**, mặc định từ **JDK 19** không dùng CPU shares để tính active processor count; thay đổi này cũng xuất hiện trong **JDK 17.0.4** và các nhánh backport tương ứng.
- Do đó, **không sử dụng quy tắc “đặt CPU request=500m thì Java chắc chắn báo 1 CPU”** như một chân lý chung cho mọi JDK hiện đại.

**Không khuyến khích dùng các cờ compatibility/deprecated để khôi phục hành vi CPU shares cũ** cho một bài mới. Để biết đúng runtime đang có, hãy kiểm tra `java -version`, `java -XshowSettings:system` và log container của chính JVM đó.

### 2.1. Những khái niệm cần tách

| Cơ chế | Tác dụng chính | Không nên suy ra |
| --- | --- | --- |
| CPU **quota** / hard limit | Giới hạn tổng CPU time trong từng accounting period; có thể throttle | Ghim tiến trình vào đúng N core vật lý |
| **cpuset** / CPU affinity | Giới hạn những logical CPUs được phép chạy | Luôn có N core CPU time trọn vẹn nếu quota nhỏ hơn |
| CPU **shares/weight** | Phân chia tương đối dưới tranh chấp tài nguyên | Hard limit hoặc số CPU chính xác mà JVM sẽ thấy |
| Kubernetes **requests.cpu** | Phục vụ lập lịch/cam kết tài nguyên và weight thích hợp | Giới hạn cứng ở đúng request |
| Kubernetes **limits.cpu** | Giới hạn CPU được kernel thực thi bằng quota/throttling | JVM chắc chắn có N threads hoặc N CPUs độc quyền |
| `availableProcessors()` | Con số nguyên JVM báo cho Java và nhiều bộ phận ergonomics | Tốc độ xử lý tuyệt đối, số CPU vật lý dành riêng |
| `-XX:ActiveProcessorCount=N` | Override con số active CPU mà HotSpot dùng cho tính toán | Đặt lại cgroup limit, thay affinity, cấp thêm core |
| Số thread của ứng dụng | Mức đồng thời do chương trình tạo/quản lý | Số core hoặc throughput thực tế luôn bằng nhau |

## 3. Nắm ba cơ chế Linux: quota, cpuset và shares/weight

### 3.1. CPU quota là giới hạn theo thời gian

Trên Linux cgroup v2, tệp `cpu.max` mô tả quota và period, đơn vị thường tính bằng microseconds. Ví dụ minh họa:

```text
cpu.max = 50000 100000    # 50ms CPU time / 100ms period ~ 0.5 CPU
cpu.max = 100000 100000   # 100ms / 100ms ~ 1 CPU
cpu.max = 200000 100000   # 200ms / 100ms ~ 2 CPU
cpu.max = max 100000      # không có quota riêng ở cgroup này
```

Đây là **các ví dụ tính toán**, không phải kết quả bắt buộc của mọi Docker/container runtime. Period có thể khác 100000; quota thực tế phải đọc từ cgroup mà process đang thuộc về, và giới hạn của các **ancestor cgroups** vẫn có thể ràng buộc process.

Một quota tương đương 2 CPU **không có nghĩa hai core được dành riêng**, vì kernel có thể lên lịch nhiều threads trên nhiều logical CPUs rồi throttle khi hết budget của period. Ngược lại, quota=0.5 CPU có thể cho tiến trình chạy khá nhanh trong phần đầu của period rồi phải chờ, làm ảnh hưởng p99 latency.

### 3.2. CPU cpuset / affinity ràng buộc vị trí chạy

Ví dụ:

```bash
docker run --rm --cpuset-cpus="0-1" cpu-scenario:21 3000000
```

Lệnh minh họa chỉ hợp lệ khi host/container runtime cho phép logical CPU IDs 0 và 1. Nếu workload bị pin vào hai CPU hợp lệ, dù host có 32 logical CPUs thì tiến trình chỉ được chạy trên phạm vi được gán. **Cpuset không tự đặt mức CPU time quota**; có thể dùng kèm `--cpus` để kiểm tra hai điều kiện cùng lúc.

Trong Linux có thể xem effective cpuset qua `cpuset.cpus.effective` (cgroup v2, khi tệp được expose), hoặc công cụ affinity thích hợp. Không suy CPU count bằng cách đếm ký tự trong chuỗi như `0-3,6`; đó là danh sách/range CPU IDs.

### 3.3. CPU shares/weight không phải hard limit

Kubernetes `resources.requests.cpu: 500m` không nhất thiết làm container chỉ dùng tối đa 0.5 CPU. Nếu node rảnh và không có CPU limit, nó có thể dùng thêm CPU. Under contention, relative weight ảnh hưởng cách chia nguồn lực.

Trong cgroup v1 có `cpu.shares`, trong cgroup v2 có `cpu.weight`; ý nghĩa và mapping cụ thể thuộc container runtime/kernel. **Không được nhầm request với limit**, cũng không gán một bộ đếm `availableProcessors` cố định cho mọi request trên các JDK hiện đại.

Trường hợp cần một hard limit 0.5 CPU, cấu hình `limits.cpu: 500m` trên Kubernetes hoặc `docker run --cpus=0.5` khi phù hợp, và xác minh quota thực sự.

## 4. Xây dựng ma trận kiểm thử

Dùng một ứng dụng CPU-bound có workload cố định, chạy ít nhất những scenario sau:

| Scenario | Mức cấp CPU | Mục đích |
| --- | --- | --- |
| A | `--cpus=0.5` | Thử fractional CPU; quan sát integer active count và throttling |
| B | `--cpus=1` | Mốc baseline một CPU |
| C | `--cpus=2` | Kiểm tra tốc độ khi tăng CPU quota |
| D | `--cpus=4` | Kiểm tra scaling/giới hạn host, JIT và concurrency |
| E | Cùng CPU quota nhưng `-XX:ActiveProcessorCount=1` | Tách ảnh hưởng của JVM ergonomics khỏi kernel quota |
| F | Cùng CPU quota nhưng `-XX:ActiveProcessorCount=4` | Xem oversubscription và tác động sizing |
| G | Có CPU request/weight nhưng không có CPU limit | Kiểm tra sự khác nhau giữa soft share và hard quota |
| H | Cùng quota nhưng cpuset giới hạn hơn | Phân biệt vị trí chạy và tổng budget |

**Không cần ép mọi dự án chạy đủ tám scenario ngay lần đầu**. A–D là lõi để học mức CPU khác nhau; E–H là mở rộng để tách nguyên nhân khi kết quả bất ngờ.

Giữ bất biến khi so sánh A–D:

- **Cùng mã Java/JAR/digest** và cùng số lượng task + số vòng lặp.
- **Cùng JDK vendor, build, JVM options, garbage collector, runtime image**.
- Cùng memory limit và heap flags, nếu mục tiêu chỉ khảo sát CPU.
- Cùng workload, dữ liệu đầu vào, loại test và policy concurrency.
- Cùng host hoặc các host có đặc tính tương đương; ghi nhận NUMA/CPU architecture nếu khác.
- Không thay CPU quota giữa một lần chạy rồi coi mọi JVM sẽ cập nhật ngay lập tức.
- Chạy mỗi scenario nhiều lượt sau warm-up và sắp thứ tự xen kẽ để giảm sai lệch nhiệt độ/caching/noise.

## 5. Chương trình Java 17+ làm workload kiểm thử

Bài thử cần **đúng đầu ra** và **có thể tăng/giảm song song**. Nếu chỉ chạy `System.out.println(availableProcessors())`, bạn chưa hề đo ảnh hưởng CPU tới hiệu năng ứng dụng.

Tạo tệp **`CpuScenario.java`** sau. Chương trình có tám tác vụ CPU-bound độc lập. Số worker được chọn bằng `min(availableProcessors, taskCount)` để quan sát cách phản ứng khi CPU count JVM báo thay đổi.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class CpuScenario {
    private static long compute(int taskId, int iterations) {
        long value = 0x9E3779B97F4A7C15L ^ taskId;
        for (int i = 0; i < iterations; i++) {
            value = Long.rotateLeft(
                    value ^ (i * 0xBF58476D1CE4E5B9L), 13)
                    * 0x94D049BB133111EBL;
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        int iterations = args.length > 0
                ? Integer.parseInt(args[0]) : 3_000_000;

        if (iterations <= 0) {
            throw new IllegalArgumentException(
                    "iterations must be positive");
        }

        int processors =
                Runtime.getRuntime().availableProcessors();
        int taskCount = 8;
        int workers = Math.min(processors, taskCount);

        System.out.println("processors=" + processors);
        System.out.println("commonPoolParallelism="
                + ForkJoinPool.getCommonPoolParallelism());
        System.out.println("workers=" + workers);
        System.out.println("tasks=" + taskCount);

        var executor = Executors.newFixedThreadPool(workers);
        long started = System.nanoTime();
        long checksum = 0;

        try {
            List<Callable<Long>> jobs = new ArrayList<>();
            for (int task = 0; task < taskCount; task++) {
                final int taskId = task;
                jobs.add(() -> compute(taskId, iterations));
            }

            List<Future<Long>> results = executor.invokeAll(jobs);
            for (Future<Long> future : results) {
                checksum = checksum * 31 + future.get();
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(
                    30, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);
        System.out.println("checksum="
                + Long.toUnsignedString(checksum));
        System.out.println("elapsedMs=" + elapsedMillis);
    }
}
```

### 5.1. Biên dịch và chạy

```bash
javac --release 17 CpuScenario.java
java CpuScenario 3000000
```

Output có các dòng:

```text
processors=<số CPU JVM báo>
commonPoolParallelism=<giá trị của ForkJoinPool>
workers=<số worker đã chọn>
tasks=8
checksum=15991552347922611062
elapsedMs=<thời gian thực đo bằng milliseconds>
```

Các dấu `<...>` trong khối output trên là **ký hiệu diễn giải**, không phải stdout literal. Với đúng source và `3000000` iterations, **checksum có giá trị cố định** như trên theo phép toán `long` của Java; còn số processors, pool parallelism và elapsed time phụ thuộc runtime và cấu hình. Khi thay iterations (ví dụ lên `30000000`), checksum cũng thay.

### 5.2. Vì sao checksum quan trọng?

Nếu ở scenario A (0.5 CPU) ứng dụng trả output khác scenario D (4 CPU) cho cùng task IDs và iterations, đó là **lỗi logic/kết quả**, không thể chấp nhận như một “đánh đổi hiệu năng”. Chương trình thu các `Future` theo thứ tự task đầu vào rồi gộp checksum với phép toán long xác định, giúp kết quả không phụ thuộc thứ tự worker thực thi.

Không kiểm tra hiệu năng mà bỏ kiểm tra correctness. Tăng CPU chỉ nên thay tốc độ/cách phân bổ công việc; dữ liệu đầu ra nghiệp vụ phải giữ đúng hợp đồng.

### 5.3. Những giới hạn của workload minh họa

- Đây là **CPU-bound**: phần chính thực hiện tính toán, rất ít I/O.
- Có đúng tám tác vụ; sau khi workers đạt tám, ứng dụng không tự có thêm khả năng tăng độ song song tác vụ.
- Công việc mỗi tác vụ độc lập; một ứng dụng có lock contention hay phụ thuộc I/O sẽ scale khác.
- `elapsedMs` bao gồm tạo pool, scheduling, JIT/warmup và completion overhead. **Không xem một lần in elapsedMs như benchmark khoa học**.
- Với bài thử performance thật, tăng iterations đủ dài, chạy warm-up, lặp lại, giữ JDK stable và đo nhiều thống kê; JMH phù hợp cho microbenchmark, còn ứng dụng web cần load test end-to-end.

## 6. Kiểm chứng nhanh trên máy phát triển, chưa cần Docker

Tùy chọn HotSpot `-XX:ActiveProcessorCount=N` override số processors được dùng cho một số lựa chọn VM/thread-pool. Có thể dùng nó để **kiểm tra tính thích ứng của ứng dụng**, ngay cả trên Windows/macOS, nhưng **nó không hạn chế CPU của kernel** như cgroup quota.

Biên dịch Java 17+ như mục 5, rồi chạy:

```bash
java -XX:ActiveProcessorCount=1 CpuScenario 3000000
java -XX:ActiveProcessorCount=2 CpuScenario 3000000
java -XX:ActiveProcessorCount=4 CpuScenario 3000000
```

Kết quả kiểm thử trên HotSpot JDK 24, không có system property override common pool:

| ActiveProcessorCount | `processors` | `commonPoolParallelism` | `workers` | `tasks` |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 1 | 8 |
| 2 | 2 | 1 | 2 | 8 |
| 4 | 4 | 3 | 4 | 8 |

Cả ba lượt trả `checksum=15991552347922611062` khi `iterations=3000000`. Giá trị `elapsedMs` dao động theo máy và lần chạy, nên **không đưa ra một số chuẩn**. `ForkJoinPool.getCommonPoolParallelism()` có quy tắc riêng và có thể bị ảnh hưởng bởi cấu hình `java.util.concurrent.ForkJoinPool.common.parallelism`; không suy mọi executor tự bằng `availableProcessors()`.

**Kết luận hợp lệ:** khi thay `ActiveProcessorCount`, ứng dụng thấy CPU count và chọn số worker khác. **Kết luận không hợp lệ:** máy thật hoặc container đã bị Linux giới hạn xuống 1, 2, 4 CPU; flag này không thực thi kernel throttling/affinity.

### 6.1. Vì sao flag chỉ là một phần của bài test?

Nếu bạn chạy `ActiveProcessorCount=1` trên host rảnh có 32 logical CPUs, kernel vẫn có thể cho JVM chạy trên nhiều CPU theo OS policy. Nhưng code demo chỉ tạo một worker do nhìn thấy count=1. Kết quả có thể chậm hơn vì **ứng dụng giảm parallelism**, không phải vì kernel từ chối cho process CPU time.

Ngược lại, `ActiveProcessorCount=8` dưới cgroup quota 0.5 CPU có thể khiến pool tạo nhiều worker, nhưng kernel vẫn throttle tổng CPU budget. Nhiều worker hơn đôi khi **làm tệ hơn** latency do tranh chấp và scheduler overhead.

Để đo resource limit thật, phải chạy dưới cgroup/Docker/Kubernetes, không chỉ dùng flag.

## 7. Đóng gói cùng một JAR thành image Docker

Từ đúng tệp `CpuScenario.java`, tạo **`Dockerfile`**:

```dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /work
COPY CpuScenario.java .
RUN javac --release 17 CpuScenario.java \
    && jar --create --file cpu-scenario.jar \
       --main-class CpuScenario CpuScenario.class

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /work/cpu-scenario.jar /app/cpu-scenario.jar
ENTRYPOINT ["java", "-Xms128m", "-Xmx256m",
            "-jar", "/app/cpu-scenario.jar"]
```

**Chú ý Dockerfile:** cú pháp JSON-array `ENTRYPOINT` phải được đặt **trên một dòng** hoặc escape/continuation theo Dockerfile parser. Để sao chép trực tiếp, dùng dòng đúng dưới đây thay cho hai dòng phân tách nhằm trình bày ở trên:

```dockerfile
ENTRYPOINT ["java","-Xms128m","-Xmx256m","-jar","/app/cpu-scenario.jar"]
```

Để file Dockerfile thực sự dùng được khi copy nguyên khối, hãy chỉ giữ **dòng ENTRYPOINT đơn** ở cuối; đoạn trước là minh họa bố cục. Hoặc dùng phiên bản đầy đủ, copy trực tiếp sau (đây là cấu hình khuyến nghị):

```dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /work
COPY CpuScenario.java .
RUN javac --release 17 CpuScenario.java && \
    jar --create --file cpu-scenario.jar --main-class CpuScenario CpuScenario.class

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /work/cpu-scenario.jar /app/cpu-scenario.jar
ENTRYPOINT ["java","-Xms128m","-Xmx256m","-jar","/app/cpu-scenario.jar"]
```

**Ý nghĩa:** build stage dùng JDK 21 nhưng biên dịch `--release 17`, runtime stage sử dụng Java 21 (một Java hiện đại). Cả bốn scenario đều chạy **cùng image được build một lần**. Các image tags minh họa có thể dịch chuyển tới patch build khác qua thời gian; với benchmark nghiêm ngặt, pin image digest và dùng đúng digest cho mọi run.

Build trên máy có Docker Engine hỗ trợ chạy Linux containers:

```bash
docker build -t cpu-scenario:21 .
```

Trên Windows cần Docker Desktop Linux engine đang hoạt động hoặc dùng Linux host/container engine tương đương. **Không có Docker daemon thì không thể thực sự áp `--cpus` lên một container**, dù lệnh `docker` đã cài trong terminal.

## 8. Chạy cùng image với 0.5, 1, 2 và 4 CPU

Chạy từ cùng host Linux có đủ tài nguyên; mỗi lệnh tạo một container mới, dùng cùng image và cùng input iterations. `--memory=512m` giữ memory limit giống nhau, trong khi `-Xms128m`/`-Xmx256m` giữ heap flags giống nhau.

```bash
docker run --rm --cpus=0.5 --memory=512m cpu-scenario:21 30000000

docker run --rm --cpus=1 --memory=512m cpu-scenario:21 30000000

docker run --rm --cpus=2 --memory=512m cpu-scenario:21 30000000

docker run --rm --cpus=4 --memory=512m cpu-scenario:21 30000000
```

Mỗi container chạy **cùng `CpuScenario` với 8 tasks và 30 triệu iterations mỗi task**. Giá trị CPU quota là thứ được thay. Dùng iterations đủ dài để đo ổn định trên host thực tế; nếu chạy quá nhanh, tăng số vòng với giới hạn hợp lý hoặc đo nhiều requests trong service dài hơn.

### 8.1. Kỳ vọng đúng nhưng không đoán số kết quả

- Với 0.5 CPU quota, JVM thường không thể báo “0.5 processors” vì `availableProcessors()` trả **int**, ít nhất 1. Nó có thể báo 1 trong môi trường HotSpot phù hợp, **không có nghĩa giới hạn thực của kernel là 1 CPU đầy đủ**.
- Với 1, 2, 4 CPU, `availableProcessors()` **có thể** lần lượt tăng khi host/affinity/JDK hỗ trợ; không hứa chính xác các số đó nếu cpuset nhỏ hơn hoặc cgroup parent giới hạn.
- `workers` sẽ bám theo con số `processors` đến tối đa 8, theo chính code của bài.
- `elapsedMs` của CPU-bound workload thường cải thiện khi tăng CPU budget và có đủ logical CPUs, nhưng không nhất thiết giảm tuyến tính hoặc đơn điệu trong từng lượt chạy.
- Nếu host chỉ có 2 CPUs hữu dụng, tăng quota lên 4 CPU **không tạo thêm 2 core vật lý**.
- Nếu scheduler/load/JIT/thermal throttling thay đổi, một lần test 4 CPU có thể chậm hơn 2 CPU mà code vẫn đúng. Cần repeated measurements và đối chiếu metrics.

**Không bịa bảng elapsedMs mẫu rồi coi là kết quả thật.** Đầu ra tính toán được biết, nhưng số liệu hiệu năng phải thu trên runtime/Linux host cụ thể.

### 8.2. Ví dụ quota 0.5 và active count 1

Giả sử cgroup `cpu.max` là `50000 100000`: CPU time tối đa trung bình khoảng 0.5 CPU mỗi period khi workload liên tục dùng hết quota. `availableProcessors()` có thể trả 1 vì là số nguyên; điều đó không “làm tròn quota hệ điều hành lên 1 CPU thật”. Một ứng dụng tạo một worker vẫn có thể bị kernel throttle nửa thời gian nếu worker liên tục CPU-bound.

Đây là lý do phải **đo throttling** bên cạnh `availableProcessors()`.

## 9. Xác nhận cgroup đang áp dụng quota thật

Trên Linux cgroup v2, một số file thường có:

```text
/sys/fs/cgroup/cpu.max
/sys/fs/cgroup/cpu.stat
/sys/fs/cgroup/cpuset.cpus.effective
/sys/fs/cgroup/cpu.weight
```

Một cách kiểm tra trong container mà không sửa file:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
```

**Chỉ áp dụng trực tiếp** khi các file cgroup v2 này có mặt và path được container runtime expose. Trên cgroup v1, file CPU quota có thể nằm ở `cpu.cfs_quota_us`/`cpu.cfs_period_us` và layout mount khác; không coi lỗi `No such file` của `cpu.max` là bằng chứng không có giới hạn.

### 9.1. Đọc `cpu.max`

Ví dụ minh họa:

```text
50000 100000
```

Tỷ số `50000 / 100000 = 0.5` CPU average quota. Nhưng cần xem cgroup hierarchy, cpuset và host load; một quota 0.5 không có nghĩa process được schedule trên “nửa lõi” cố định.

Nếu kết quả là `max 100000`, cgroup đó **không có quota riêng**, nhưng vẫn có thể chịu hạn chế từ ancestor hoặc affinity; đừng kết luận vô điều kiện toàn bộ host CPU đều được cấp cho process.

### 9.2. Đọc `cpu.stat` trước và sau workload

Một số trường có ý nghĩa:

| Trường cgroup v2 | Ý nghĩa |
| --- | --- |
| `usage_usec` | Thời gian CPU đã dùng, theo microseconds, có thể tính delta |
| `nr_periods` | Số accounting periods liên quan CFS bandwidth controller |
| `nr_throttled` | Số periods bị throttling |
| `throttled_usec` | Thời gian throttling được kernel báo theo semantics của cgroup/kernel |
| `user_usec` và `system_usec` | CPU time ở user/kernel mode |
| `nr_bursts` / `burst_usec` nếu có | Thông tin burst theo cấu hình/kernel |

Để chẩn đoán quota, lấy `cpu.stat` **trước** và **sau** một test dài, so delta; không lấy số cumulative đã tăng nhiều ngày rồi chia cho thời gian một request. Ví dụ:

```text
delta_nr_throttled = after.nr_throttled - before.nr_throttled
delta_nr_periods   = after.nr_periods   - before.nr_periods

delta_throttled_usec = after.throttled_usec - before.throttled_usec
delta_usage_usec     = after.usage_usec     - before.usage_usec
```

Nếu `delta_nr_periods > 0`, tỉ lệ `delta_nr_throttled / delta_nr_periods` là **tỷ lệ accounting periods có throttling**, **không phải phần trăm CPU bị mất** hoặc phần trăm requests bị chậm. `throttled_usec` cũng không được diễn giải bừa là “chính xác tổng CPU core-seconds ứng dụng thiếu” vì semantics/aggregation phụ thuộc controller/kernel.

Cgroup v2 hỗ trợ nested hierarchy; một số metrics có thể không phản ánh throttling từ ancestor theo cùng cách. Đọc tài liệu kernel phiên bản đang chạy khi cần phân tích sâu.

### 9.3. Chạy test và đọc counters từ cùng container

Với image `eclipse-temurin:21-jre` có `/bin/sh`, có thể dùng lệnh minh họa **cgroup v2** sau để kiểm tra cùng tiến trình/container:

```bash
docker run --rm --cpus=1 --memory=512m \
  --entrypoint /bin/sh cpu-scenario:21 \
  -c 'cat /sys/fs/cgroup/cpu.max; cat /sys/fs/cgroup/cpu.stat; \
      java -Xms128m -Xmx256m -jar /app/cpu-scenario.jar 30000000; \
      cat /sys/fs/cgroup/cpu.stat'
```

Đoạn `\` trong shell là line continuation; có thể viết thành một dòng nếu cần. Nó in quota, counters trước test, chạy Java, rồi in counters sau test. **Không chạy đúng lệnh trên khi Linux host đang dùng cgroup v1 và không có `cpu.max`**; thay bằng đường dẫn/chỉ số phù hợp.

Đây là **quy trình thực nghiệm**; không có số stdout cgroup cố định vì kết quả do kernel và điều kiện host quyết định.

## 10. Quan sát JVM tự nhận tài nguyên thế nào

Trên JDK HotSpot/Linux container, hai công cụ chẩn đoán hữu ích:

```bash
java -XshowSettings:system -version

java -Xlog:os+container=debug -version
```

- `-XshowSettings:system` hiển thị cấu hình hệ thống/container khi nền tảng hỗ trợ (được tài liệu hóa cho Linux); không yêu cầu ứng dụng Java riêng.
- `-Xlog:os+container=debug` in các thông tin mà HotSpot ghi khi phát hiện cgroup/container theo mức logging được chọn; `trace` có thể nhiều log hơn.
- Chạy **trong cùng container** với runtime/JDK bản thử mới đại diện. Chạy lệnh ngoài host không chứng minh HotSpot bên trong container sẽ đọc cùng quota.
- Nếu có flag `-XX:ActiveProcessorCount=N` ở lệnh production, nhớ ghi lại trong kết quả vì nó override CPU count tự động.

Ví dụ kiểm tra trực tiếp image:

```bash
docker run --rm --cpus=1 --memory=512m \
  --entrypoint java cpu-scenario:21 \
  -XshowSettings:system -version
```

Bước này tạo container mới cùng giới hạn CPU; không dùng dữ liệu từ một process Java đã dừng để đo quota của process khác đang chạy.

### 10.1. Nếu `availableProcessors()` không khớp trực giác

Kiểm tra theo thứ tự:

1. JDK vendor/build và version; có bản backport xử lý shares khác nhau?
2. Có `-XX:ActiveProcessorCount`/`JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`?
3. `UseContainerSupport` có được bật trên nền tảng HotSpot/Linux được hỗ trợ?
4. Cgroup v1 hay v2 và path process đang sử dụng?
5. Quota, period, cpuset effective và ancestor limits thực tế là gì?
6. Có CPU affinity do runtime, `taskset` hoặc Kubernetes CPU manager policy?
7. Host có bao nhiêu logical CPUs online/hữu dụng?
8. Có đang nhìn output từ JVM host thay vì JVM trong container?
9. Có khởi động **process JVM mới** sau khi đổi cấu hình CPU chưa?
10. Có container runtime/container image thay đổi giữa các lượt?

Đừng suy từ một giá trị lẻ `availableProcessors()==1` rằng kernel chắc chắn đã cấu hình 1 full CPU. Nó là số nguyên dành cho VM ergonomics.

## 11. CPU requests và limits trong Kubernetes

Ví dụ một container có request và limit tách biệt:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-cpu-study
spec:
  containers:
    - name: app
      image: cpu-scenario:21
      args: ["30000000"]
      resources:
        requests:
          cpu: "500m"
          memory: "256Mi"
        limits:
          cpu: "2"
          memory: "512Mi"
```

Đây là **manifest minh họa cho cluster có sẵn image**, không phải lời hứa mọi cluster có thể pull `cpu-scenario:21` từ registry. Khi sử dụng thật, phải push image vào registry được cluster cho phép hoặc cấu hình cách nạp image phù hợp.

Giải thích:

- `requests.cpu: "500m"` mô tả CPU request 0.5 core cho scheduling, **không** tự giới hạn quá trình chạy tối đa 0.5 core.
- `limits.cpu: "2"` mô tả hard CPU limit 2 cores tương đương, được Linux kernel áp bằng quota/throttling khi cần.
- `requests.memory` và `limits.memory` là cơ chế riêng, không phải nội dung chính của test CPU.
- Có thể bỏ `limits.cpu` để thử scenario không quota, nhưng phải chú ý admission policy/LimitRange/namespace default có thể bổ sung limit.
- Cùng Pod manifest không đồng nghĩa workload ở cùng node, CPU topology và host contention đều như nhau; muốn benchmark chính xác cần cố định/ghi nhận node và những biến đó.

### 11.1. Ma trận Kubernetes phù hợp

Thử cùng image với các giá trị `limits.cpu` 500m, 1, 2 và 4, giữ `requests.cpu`/node selection/workload có kiểm soát theo chính sách cluster. Không chạy các cấu hình bất khả thi: nếu node chỉ có 2 CPUs khả dụng và policy không cho limit 4, test phải điều chỉnh.

Để nghiên cứu requests riêng, giữ nguyên `limits.cpu` hoặc bỏ limit theo chủ đích, rồi thay `requests.cpu` trong điều kiện **có contention** để thấy tác động weight. Không gộp việc thay request và limit thành một thay đổi duy nhất rồi quy mọi khác biệt cho quota.

Kubernetes dùng cgroup CPU throttling cho limits trên Linux. Đọc cgroup metrics hoặc telemetry như `container_cpu_cfs_throttled_periods_total`/`container_cpu_cfs_periods_total` nếu nền tảng expose, đối chiếu với kernel counters. Tên metric Prometheus cụ thể còn phụ thuộc collector/cAdvisor/monitoring stack; không giả định mọi cluster đều có mọi metric.

## 12. Tách JVM ergonomics khỏi hard CPU limit

Một thí nghiệm bổ sung rất có ích:

Giữ container `--cpus=2` cho tất cả các lượt, chỉ thay JVM flag:

```bash
docker run --rm --cpus=2 --memory=512m \
  --entrypoint java cpu-scenario:21 \
  -XX:ActiveProcessorCount=1 -Xms128m -Xmx256m \
  -jar /app/cpu-scenario.jar 30000000

docker run --rm --cpus=2 --memory=512m \
  --entrypoint java cpu-scenario:21 \
  -XX:ActiveProcessorCount=2 -Xms128m -Xmx256m \
  -jar /app/cpu-scenario.jar 30000000

docker run --rm --cpus=2 --memory=512m \
  --entrypoint java cpu-scenario:21 \
  -XX:ActiveProcessorCount=4 -Xms128m -Xmx256m \
  -jar /app/cpu-scenario.jar 30000000
```

Ở cả ba lượt, **kernel quota vẫn là 2 CPU**. Flag chỉ thay con số active processors JVM dùng. Vì chương trình chọn `workers=min(processors,8)`, nó lần lượt có thể chạy với 1, 2 và 4 workers.

Nếu lượt có bốn workers chậm hơn hai workers, không thể quy lỗi cho JVM “không nhìn thấy 4 CPU” — chính thí nghiệm đã cố ý tạo **oversubscription** dưới quota 2 CPU. Nếu bốn workers nhanh hơn hai workers trong một tình huống khác, cũng không có nghĩa kernel đã tăng quota lên 4. Đo CPU throttling và scheduling để hiểu nguyên nhân.

**Tránh cài `-XX:ActiveProcessorCount` như cách “cấp thêm CPU” cho container bị limit 0.5 core.** Cờ này không thay cgroup.

## 13. Số CPU JVM thấy ảnh hưởng đến những bộ phận nào?

Nhiều thành phần HotSpot và thư viện Java dùng processor count làm đầu vào:

- Pool threads của một số garbage collectors và các lựa chọn GC ergonomics.
- Một số thread pools hoặc background VM activities.
- Mức song song mặc định của `ForkJoinPool.commonPool()`.
- `Executors.newWorkStealingPool()` và một số tiện ích dùng CPU count.
- Một số framework tự đo `Runtime.getRuntime().availableProcessors()` để tạo executor, worker hoặc event loop.
- Ứng dụng tự sizing pool như `CpuScenario`.

**Không tất cả pool đều thay đổi cùng công thức**, và không phải mọi framework đọc lại processor count liên tục. Ví dụ `Executors.newFixedThreadPool(32)` vẫn là cấu hình 32 threads cho pool đó, trừ khi code framework tự chọn lại giá trị.

### 13.1. Common ForkJoinPool không phải luôn bằng processors

Ví dụ kiểm thử với flag trên JDK 24:

```text
ActiveProcessorCount=1  -> commonPoolParallelism=1
ActiveProcessorCount=2  -> commonPoolParallelism=1
ActiveProcessorCount=4  -> commonPoolParallelism=3
```

Đây là behavior mặc định ở môi trường thử, không phải công thức phổ quát mọi JDK/config. Các system properties, init order và factory riêng có thể đổi parallelism.

**Tránh** viết assertion “CPU=2 thì commonPool phải có đúng 2 threads và ứng dụng phải chạy nhanh gấp đôi”.

### 13.2. GC threads và JIT cũng là một phần chi phí

Một JVM có nhiều processors có thể chọn nhiều GC workers hoặc compiler threads hơn theo ergonomics. Khi quota rất nhỏ, quá nhiều background threads và application workers có thể cạnh tranh budget CPU. Để phân tích, ghi nhận GC version/options và những thread counts có thể quan sát, nhưng không chỉnh tất cả cờ GC cùng lúc nếu chỉ muốn kiểm thử tác động CPU.

### 13.3. Virtual threads vẫn dùng CPU thật

Trên Java 21+, virtual threads giúp xử lý nhiều tác vụ blocking với chi phí thread thấp hơn, **không tự tạo thêm CPU**. CPU-bound virtual threads vẫn tranh CPU budget của carrier threads/OS; quota 1 CPU không thành 1000 CPU chỉ vì ứng dụng có 1000 virtual threads.

Muốn test một web service dùng virtual threads, ghi nhận carrier scheduler, blocking behavior, task mix và throughput; đừng dùng số virtual threads làm proxy cho số cores.

## 14. Đo cái gì trong mỗi scenario?

### 14.1. Bảng chỉ số

| Nhóm | Metric | Vì sao cần |
| --- | --- | --- |
| Cấu hình | CPU quota, period, cpuset, request/weight, host CPUs | Biết mức cấp thực tế |
| JVM | JDK version, `availableProcessors`, `ActiveProcessorCount`, GC | Biết JVM nhìn thấy và chọn gì |
| Workload | Tasks, iterations, checksum, input | Bảo đảm đúng cùng bài toán |
| Tốc độ | Elapsed wall time, throughput | Biết thời gian làm xong cùng công việc |
| Độ trễ | p50/p95/p99 latency khi chạy request service | Phát hiện tail latency tăng do throttling/scheduling |
| CPU | `usage_usec` delta, process CPU time, % CPU | Phân biệt busy với idle |
| Throttling | `nr_throttled`/`nr_periods`/`throttled_usec` delta | Biết quota có cắt tiến độ CPU |
| JVM runtime | GC pauses/count, heap, CPU của GC/JIT | Tránh quy mọi latency cho app workers |
| Máy host | CPU saturation, load average, cgroup parent | Phát hiện hàng xóm gây noise |
| Kết quả đúng | Exit code, checksum, lỗi/timeout | Performance không được đánh đổi correctness |

### 14.2. Wall time khác CPU time

- **Wall time:** thời gian trôi thực từ đầu đến cuối. Bao gồm chạy, chờ scheduler, bị throttle, lock wait, I/O và GC pauses.
- **CPU time:** tổng thời gian CPU được tính cho thread/process khi thật sự tiêu thụ CPU. Nhiều threads chạy song song có thể làm tổng CPU time **lớn hơn wall time**.
- **CPU utilization:** cần định nghĩa mẫu số: quota, một core, tổng host hay phần CPU có thể dùng. Không dùng một giá trị `CPU%=200` mà không nói cơ sở tính.

Nếu CPU-bound job chạy dưới quota 0.5 CPU và thường xuyên throttle, wall time có thể cao dù app code không làm thêm công việc. Đó là tác động quota, không nhất thiết là lỗi thuật toán.

### 14.3. Tính throughput/latency cho service thật

Workload batch của `CpuScenario` in `elapsedMs`, nhưng web service có queue và nhiều request. Trong trường hợp đó hãy giữ **request mix, payload và concurrency** ổn định, dùng load generator ở ngoài container/host phù hợp, rồi thu:

- Số request hoàn tất mỗi giây (throughput).
- p50, p95, p99 latency và error rate.
- Queue wait time, thread pool utilization và pool saturation.
- GC pauses và CPU throttling.
- Kết quả correctness và hành vi timeout.

Một service có thể có throughput vẫn ổn nhưng p99 xấu đi ở 0.5 CPU vì quota throttling tạo các đợt stall. Nếu chỉ nhìn average latency, bạn sẽ bỏ sót tình huống này.

## 15. Thiết kế benchmark có khả năng lặp lại

### 15.1. Chạy nhiều lần, warm up trước đo

Công việc Java chịu ảnh hưởng JIT, class loading, CPU frequency scaling, filesystem caching và các tiến trình khác. Một quy trình hợp lý:

1. Pin một JDK/container image digest.
2. Build JAR **một lần**.
3. Kiểm tra CPU count và cgroup trước run.
4. Chạy warm-up để JIT ổn định trong mức hợp lý.
5. Chạy 5–10 lần đo cho mỗi CPU limit (hoặc đủ để đạt độ tin cậy cần thiết).
6. Dùng cùng input, cùng heap/GC flags và cùng cách khởi chạy.
7. Xen kẽ thứ tự scenario, ví dụ 1–2–4–0.5 rồi 4–0.5–2–1; tránh kết quả bị ảnh hưởng do host nóng dần.
8. Thu median, p95 của elapsed/latency thay vì chỉ một lần.
9. Ghi cgroup throttling delta trong đúng khoảng đo.
10. So cùng release/JDK và báo chi tiết nếu có outliers.

**Không** cần làm máy benchmark hoàn toàn không có hoạt động OS để bắt đầu học, nhưng muốn kết luận nghiêm túc thì phải quản lý và báo rõ các nguồn nhiễu.

### 15.2. Không trộn startup benchmark với steady-state benchmark

Nếu mỗi `docker run` chỉ chạy một job rất ngắn rồi thoát, elapsed time có thể bao gồm startup/JIT khác nhau so với một service đã warm. Hãy quyết định mục tiêu:

- **Startup test:** đo thời gian từ process start tới “ready”.
- **Batch latency:** đo thời gian thực hiện một batch cố định.
- **Steady throughput:** chạy service đủ lâu qua giai đoạn warm-up.
- **Tail latency:** gửi nhiều request cùng tải và đo p99.

Không dùng một số duy nhất để trả lời cả bốn mục tiêu.

### 15.3. Độ dài job phải đủ lớn

Nếu output `elapsedMs` chỉ vài milliseconds, khác biệt giữa CPU=1 và CPU=4 có thể bị che bởi JIT, thread creation và độ phân giải đo. Có thể tăng iterations `30000000` hoặc dùng load test dài hơn. Tuy nhiên không chọn loops quá lớn làm CI bị timeout hoặc host dùng chung bị bão hòa kéo dài.

### 15.4. Kiểm soát input và correctness

Khi tăng iterations, checksum thay; kiểm tra rằng **cùng iterations** thì các scenario đều trả **cùng checksum**. Với web service, kiểm tra số bản ghi/response và error rate. Không loại bỏ các request timeout khỏi mẫu latency rồi trình bày throughput như toàn bộ request đều thành công.

## 16. Phân tích các kết quả thường gặp

### 16.1. 0.5 CPU nhưng `processors=1`

**Đây có thể là bình thường.** API trả số nguyên, quota là fractional. Một worker có thể liên tục chạy đến khi cgroup hết quota trong period rồi bị throttle. Cần đọc `cpu.max` và `cpu.stat` để xác nhận mức cấp thật.

### 16.2. 2 CPU nhưng kết quả gần bằng 1 CPU

Các nguyên nhân có thể:

- Workload chỉ có một đường thực thi tuần tự (Amdahl).
- Lock contention/queue serialization.
- Host hoặc ancestor cgroup đang nghẽn.
- Cpuset chỉ cho dùng một CPU.
- JDK không thấy quota mới hoặc `ActiveProcessorCount=1`.
- Job quá ngắn, JIT startup chi phối.
- Memory bandwidth, cache hoặc thermal limit.
- Framework pool cố định không tăng worker.

Không vội kết luận HotSpot container detection bị hỏng.

### 16.3. 4 CPU chậm hơn 2 CPU

Có thể do oversubscription, tranh chấp cache/memory, JIT/GC overhead, host contention, frequency/NUMA hoặc nhiễu số đo. Hãy xem cả `workers`/pool size, CPU throttling, CPU usage và GC logs; chạy thêm lượt. **CPU được cấp nhiều hơn không tạo bảo đảm tốc độ tăng đơn điệu trong mọi lần thử.**

### 16.4. CPU request đổi mà `availableProcessors` không đổi

Trên JDK hiện đại, CPU shares/weight không được mặc định xem như hard CPU count. Điều này có thể **đúng theo thiết kế**, không phải một bug. Đọc `JDK-8281181` và release notes của đúng vendor/build.

### 16.5. `ActiveProcessorCount=4` nhưng container chỉ có 1 CPU quota

Cờ override con số của JVM, **không** sửa quota kernel. App có thể tạo bốn workers rồi vẫn bị giới hạn tổng CPU time. Nếu latency xấu hơn, đó có thể là do nhiều worker cùng tranh quota/scheduling.

### 16.6. Thấy `cpu.max = max 100000` nhưng service vẫn chậm

Cgroup hiện tại không có quota riêng có thể vẫn chịu ancestor restrictions, cpuset, affinity, host contention, thread pool starvation hoặc I/O bottleneck. Xem hierarchy và metrics host, không kết luận “không có CPU bottleneck” chỉ dựa trên một file.

### 16.7. Throttling thấp nhưng latency cao

Có thể có lock, GC, disk/network I/O, JVM warm-up, noisy neighbors hoặc queueing. CPU throttling là **một** nguyên nhân tiềm năng, không phải đáp án cho mọi vấn đề hiệu năng.

### 16.8. Throttling cao nhưng ứng dụng vẫn đúng

CPU quota thường làm chậm tiến độ chứ không thay đổi semantics tính toán. Nếu checksum/response đúng, đó là vấn đề capacity/SLO. Nếu có timeout, cancellation hoặc queue tràn khi CPU thiếu, có thể xuất hiện lỗi nghiệp vụ do giới hạn thời gian; phải kiểm thử cả timeout/error path.

## 17. CPU-bound khác I/O-bound: đừng khái quát kết quả

### 17.1. Workload CPU-bound

Mỗi task luôn có việc tính toán, nên có nhiều task độc lập và worker đủ hiệu quả thường hưởng lợi từ CPU budget lớn hơn, cho tới khi gặp giới hạn song song, memory/cache hoặc bottleneck khác.

### 17.2. Workload I/O-bound

Ứng dụng chờ database/network có thể tận dụng concurrency lớn hơn processor count vì các request phần lớn đang đợi I/O. `newFixedThreadPool(availableProcessors())` không tự động là lựa chọn tối ưu. Virtual threads/async I/O cũng thay mô hình concurrency; CPU quota vẫn ràng buộc phần computation còn lại.

### 17.3. Ứng dụng có tải hỗn hợp

Một service gồm HTTP, JSON serialization, cache, encryption, SQL client, GC và background jobs. Thay CPU limit có thể tác động từng thành phần khác nhau. **Không dùng một microbenchmark CPU-bound đơn giản rồi hứa throughput toàn ứng dụng sẽ scale y hệt**. Demo dùng để học cơ chế; performance quyết định bằng workload đại diện.

## 18. CI và kiểm thử tự động

### 18.1. Test chức năng ổn định trên mọi runner

Những assertions nên có:

- Java process khởi động thành công trên JDK đã khai báo.
- `availableProcessors() >= 1`.
- `workers >= 1` và `workers <= tasks`.
- `checksum` của cùng iterations không đổi.
- Exit code bằng 0 và không xuất hiện exception.
- Với `-XX:ActiveProcessorCount=1` trong HotSpot tương thích, ứng dụng báo processors 1.
- Với `-XX:ActiveProcessorCount=2` trong HotSpot tương thích, ứng dụng báo processors 2.

Những assertions **không nên viết cứng** cho một CI runner bất kỳ:

- “0.5 CPU luôn báo processors=1 trên mọi vendor/kernel”.
- “4 CPUs luôn chạy nhanh hơn 1 CPU ít nhất 3.5 lần”.
- “Elapsed time luôn dưới 100 ms”.
- “CPU share request 500m luôn tương đương CPU limit 0.5”.
- “Không có kernel throttling ở mọi scenario 2 CPU”.
- “Common pool luôn bằng processors”.

### 18.2. Test integration cgroup có điều kiện

Nếu CI runner cho phép Linux Docker Engine và cgroup CPU quota:

1. Build một image digest.
2. Chạy test container `--cpus=0.5` và `--cpus=2` cùng input.
3. Đọc `cpu.max`/metrics thực tế để biết quota được áp.
4. So checksum/output của ứng dụng.
5. Thu `cpu.stat` trước/sau và elapsed time.
6. Chấp nhận biến động performance có giới hạn thiết kế thay vì hardcode speedup.
7. Nếu Docker/cgroup không sẵn, **báo skipped có lý do**, không lặng lẽ giả lập quota bằng `ActiveProcessorCount` rồi tuyên bố integration test đã chạy.

Điều này đặc biệt quan trọng trên Windows hoặc macOS: Docker Desktop Linux engine phải chạy, và cgroup limit thực tế được thực thi trong Linux VM/container, không phải trong JVM Windows native.

## 19. Cách công bố kết quả benchmark

Khi viết báo cáo, mỗi scenario cần ghi:

- Ngày giờ và tên/commit/digest của JAR/image.
- JDK vendor, full version, VM options, GC.
- Kernel/Linux/container runtime/cgroup version.
- `--cpus` hoặc Kubernetes CPU limit/requests.
- Quota và cpuset **thực đo**; parent limits nếu có.
- `Runtime.availableProcessors` và số workers thực tế.
- Input tasks/iterations, checksum/độ chính xác.
- Median và dispersion của elapsed/throughput/latency.
- Delta `cpu.stat` throttling và CPU usage.
- Số lượng runs, warm-up policy và host contention.

Kết luận mẫu đúng về **logic** nhưng không điền số liệu giả:

> Khi tăng CPU quota trong cùng host và cùng workload, ứng dụng có khả năng tăng throughput nếu phần công việc CPU-bound đủ song song. Trên quota nhỏ, cần xem `cpu.stat` để phát hiện throttling. `availableProcessors()` giúp hiểu kích thước pool mặc định, nhưng không thay thế số liệu kernel và hiệu năng thực đo.

Đừng viết “đã giảm latency 70%” khi chỉ thử một lần trên máy local mà không có data.

## 20. Những nhầm lẫn phổ biến

| Nhầm lẫn | Thực tế |
| --- | --- |
| “`availableProcessors()` luôn là số CPU vật lý của host.” | Nó phản ánh active processor count theo OS/JVM/container/override |
| “CPU quota 0.5 phải in `0.5`.” | Method trả `int`, không biểu diễn CPU fractional trực tiếp |
| “`--cpus=2` nghĩa là chỉ được chạy trên CPU 0 và 1.” | Quota là CPU time; affinity/cpuset là cơ chế khác |
| “`--cpuset-cpus=0-1` cũng tự giới hạn còn 1 CPU quota.” | Cpuset và quota độc lập |
| “CPU request 500m là hard cap 0.5 CPU.” | Request khác limit; dưới tranh chấp thường dùng weight |
| “JDK 19 vẫn mặc định tính CPU shares thành active count như Java 10.” | JDK-8281181 thay đổi hành vi; có cả backport JDK 17 |
| “`-XX:ActiveProcessorCount=4` cấp thêm CPU vật lý.” | Chỉ override CPU count dùng bởi VM; không thay cgroup |
| “`-XX:-UseContainerSupport` là cách tối ưu production.” | Vô hiệu hóa container awareness, dễ làm ergonomics sai |
| “Cùng code nhưng thay version JDK vẫn là cùng một điều kiện test.” | Version/JIT/GC/ergonomics là biến ảnh hưởng |
| “CommonPool luôn có N threads nếu processors=N.” | Parallelism có quy tắc riêng, properties và runtime |
| “Một task CPU-bound scale mãi khi tăng N cores.” | Bị giới hạn bởi số task, Amdahl, locks/cache/memory |
| “4 CPUs luôn nhanh hơn 2 CPUs ở mọi run.” | Không có bảo đảm do noise/bottlenecks |
| “CPU throttling chỉ có khi `availableProcessors` giảm.” | Throttling do quota kernel, không do field count |
| “`cpu.stat.nr_throttled` là số request chậm.” | Là bộ đếm periods throttled, không phải request count |
| “Cộng `throttled_usec` là lượng CPU core-seconds bị mất chính xác.” | Semantics kernel/accounting cần đọc theo phiên bản |
| “Đọc `/sys/fs/cgroup/cpu.max` là chạy được trên mọi Linux.” | Chỉ khi cgroup v2 expose path đó; v1 khác |
| “`cpu.max=max` chứng minh host không hạn chế CPU.” | Có thể có ancestor limit, cpuset, affinity hoặc contention |
| “Docker CLI đã cài nghĩa là Docker Engine hoạt động.” | Cần daemon/container engine chạy và có quyền |
| “Benchmark vài milliseconds là đủ chọn CPU limit.” | Cần warm-up/repeated tests và workload đại diện |
| “CPU tăng, checksum thay cũng không sao vì chạy parallel.” | Correctness phải nhất quán với cùng input |
| “Virtual threads tạo CPU time miễn phí.” | Virtual threads không vượt kernel CPU quota |
| “CPU metrics cao là mọi request sẽ nhanh.” | Có thể có queueing, throttling, lock và p99 xấu |
| “Chỉ cần JVM log CPU count, không cần kernel metrics.” | Phải kiểm tra cả JVM view và cgroup quota/throttling |
| “`-XshowSettings:system` có cùng output trên mọi OS.” | Tính năng/format phụ thuộc platform/JDK; chủ yếu Linux |
| “Một CPU-share cũ đã deprecated nên phải bật lại cho đúng Java 10.” | Special Note yêu cầu thực hành hiện đại; không phục hồi legacy behavior |

## 21. Bài tập kèm lời giải

### Bài 1 — Hai lớp thông tin

Container có quota 0.5 CPU nhưng `Runtime.getRuntime().availableProcessors()` trả 1. Có mâu thuẫn không?

**Đáp án:** không. Quota là mức CPU time theo period, còn `availableProcessors` là số nguyên dành cho VM ergonomics. CPU-bound thread vẫn có thể bị kernel throttle.

### Bài 2 — Chạy cùng app

Bạn đổi cùng lúc CPU quota từ 1 lên 4 và JDK từ 17 lên 21. Có thể khẳng định thay đổi throughput chỉ đến từ CPU không?

**Đáp án:** không. JDK/JIT/GC/container detection cũng đổi. Giữ cùng JDK/image khi cần isolate CPU; nếu muốn so hai JDK, chạy một ma trận hai biến riêng.

### Bài 3 — Request hay limit?

Kubernetes `requests.cpu=500m`, không có `limits.cpu`. Ứng dụng có bị hard limit đúng 0.5 CPU không?

**Đáp án:** không nhất thiết. Request phục vụ scheduling/relative allocation, có thể dùng CPU nhiều hơn khi node rảnh. Hãy xem cgroup quota thật và admission policy.

### Bài 4 — JVM override

Ứng dụng chạy dưới `--cpus=1` nhưng thêm `-XX:ActiveProcessorCount=8`. Kernel có cấp 8 CPU cho container không?

**Đáp án:** không. JVM báo CPU count 8 cho các quyết định ergonomics, còn quota vẫn 1 CPU. Có thể oversubscribe threads và tăng throttling/overhead.

### Bài 5 — Cùng input, checksum

`CpuScenario 3000000` chạy với 1 và 4 processors; checksum nên khác nhau?

**Đáp án:** không. Cùng algorithm/task IDs/input, checksum phải là `15991552347922611062`. Thay processor count chỉ thay mức đồng thời/thời gian, không thay kết quả.

### Bài 6 — Số task và giới hạn scaling

`CpuScenario` có tám tasks, được cấp 32 CPUs. Nó có dùng 32 workers không?

**Đáp án:** không. Code chọn `workers=min(processors,8)`, nên tối đa tám workers. Hơn nữa, nếu các tasks không đủ song song thật sự thì throughput còn bị giới hạn.

### Bài 7 — Diễn giải `cpu.max`

Cgroup v2 có `cpu.max=150000 100000`. Tương đương mức quota bao nhiêu?

**Đáp án:** khoảng 1.5 CPU average quota mỗi period. Điều này không chỉ định 1.5 physical cores; `availableProcessors()` trả số nguyên theo logic JVM.

### Bài 8 — Cpuset

Container bị pin vào hai CPUs nhưng có quota bốn CPU. Có chắc tận dụng đủ bốn CPUs tính toán song song không?

**Đáp án:** không. Cpuset chỉ cho chạy trên hai logical CPUs, nên giới hạn vị trí chạy vẫn hạn chế mức thực thi đồng thời dù quota cao hơn.

### Bài 9 — CPU shares ở JDK mới

Tài liệu JDK 10 nói shares có thể ảnh hưởng processor count, nhưng JDK 21 không đổi `availableProcessors` khi chỉ sửa request. Có phải JVM lỗi?

**Đáp án:** không thể kết luận vậy. JDK-8281181 đã thay mặc định về CPU shares ở JDK 19 và được backport một số bản JDK 17. Cần đối chiếu đúng version/flags.

### Bài 10 — Cgroup throttling

`nr_throttled` tăng trong một batch. Có thể nói đó là số requests bị throttle không?

**Đáp án:** không. Nó đếm periods xảy ra throttling, không phải số request. Lấy delta theo khoảng đo và đối chiếu latency/throughput.

### Bài 11 — Thời gian đo

Ba lượt CPU=2 có `elapsedMs` 200, 180, 190; CPU=4 có 185, 210, 170. Có chắc 4 CPU luôn nhanh hơn 2 CPU?

**Đáp án:** không. Các số minh họa giao nhau, thể hiện noise. Cần warm-up, nhiều lượt và thống kê phù hợp; không dùng một số thấp nhất làm kết luận.

### Bài 12 — Sizing executor

`Executors.newFixedThreadPool(16)` có tự giảm xuống 2 khi quota container là 2 CPU không?

**Đáp án:** không. Đây là pool kích thước cố định 16 threads theo tham số lập trình viên. JVM active CPU có thể ảnh hưởng một số ergonomics khác, không tự ghi đè mọi pool tường minh.

### Bài 13 — Throttling thấp nhưng p99 cao

Nếu throttling ít mà p99 latency cao, còn khả năng nào?

**Đáp án:** I/O, DB, lock, queueing, GC, class loading, JIT, host contention hoặc workload không đại diện. Phải xem metrics tương ứng, không quy mọi vấn đề cho CPU.

### Bài 14 — Cgroup v1/v2

Một container không có tệp `/sys/fs/cgroup/cpu.max`. Có chắc CPU không bị giới hạn không?

**Đáp án:** không. Nó có thể dùng cgroup v1, path khác hoặc mount namespace đặc thù. Xác minh cấu hình cgroup/runtime phù hợp.

### Bài 15 — Docker engine

Máy có `docker --version` nhưng `docker run` không chạy vì daemon không có. Có thể báo “đã kiểm thử mức CPU quota Linux” không?

**Đáp án:** không. Có thể kiểm thử Java ergonomics bằng `ActiveProcessorCount` và trình bày quy trình Docker cho host có engine; chỉ báo integration PASS khi thật sự chạy các container và đọc quota.

### Bài 16 — Virtual threads

Tạo 10.000 virtual threads CPU-bound dưới quota 1 CPU có tăng lên 10.000 CPU time đồng thời không?

**Đáp án:** không. Virtual threads thay mô hình concurrency/chi phí thread, không thay hard quota do kernel quản lý.

### Bài 17 — Đo throughput batch

Một batch có cùng tám tác vụ và một checksum. Khi CPU=4, job xong nhanh hơn CPU=1 trong nhiều lần, kết luận hợp lý là gì?

**Đáp án:** workload có thể tận dụng thêm CPU budget/song song trong điều kiện test đã kiểm soát. Không suy tuyến tính vĩnh viễn hoặc áp hệ số tăng cho mọi service web/I/O khác.

### Bài 18 — Chọn điều kiện cho CI

CI chạy trên host chia sẻ và có CPU noise. Nên assert `elapsedMs<100` để test correctness không?

**Đáp án:** không. Assert input/output/checksum/exit code; tách performance benchmark với ngưỡng thống kê và môi trường có kiểm soát.

## 22. Checklist trước khi triển khai/đánh giá CPU limit

1. **Tôi đang thay quota, cpuset hay shares/requests?**
2. Có ghi rõ cgroup v1/v2 và Linux/kernel/container runtime không?
3. Có chạy cùng app/JAR/image digest cho mọi CPU scenario không?
4. Có giữ JDK vendor/build và GC flags giống nhau không?
5. Có giữ heap/memory limit, input, concurrency và task mix ổn định không?
6. Có kiểm tra `availableProcessors` thực tế của từng JVM không?
7. Có biết `ActiveProcessorCount` có bị override không?
8. Có xác minh quota thật qua `cpu.max` hay cgroup v1 equivalent không?
9. Có xem effective cpuset/affinity và ancestor quota không?
10. Có phân biệt CPU request và hard limit không?
11. Có tránh sử dụng hành vi CPU shares legacy như mặc định mới không?
12. Có ghi số workers của ứng dụng và GC/ForkJoin pool khi cần không?
13. Có kiểm checksum/correctness giữa mọi scenario không?
14. Có chạy đủ iterations để đo công việc CPU thực tế không?
15. Có warm-up và đo nhiều lượt, không chỉ một lần không?
16. Có báo median/dispersion thay vì kết luận từ một outlier không?
17. Có đo throttling delta trong đúng khoảng chạy không?
18. Có hiểu `nr_throttled` không phải số requests bị chậm không?
19. Có đo p95/p99 latency nếu sản phẩm là service không?
20. Có so CPU time với wall time đúng định nghĩa không?
21. Có kiểm tra host contention, core frequency, NUMA và cpuset không?
22. Có phân biệt CPU-bound với I/O-bound workload không?
23. Có xem GC/JIT/queue/locks khi performance không tăng như kỳ vọng không?
24. Có tránh suy thread count từ CPU count theo công thức tùy tiện không?
25. Có giữ flags CPU hiện đại thay vì cài lại tùy chọn đã deprecated không?
26. Có chẩn đoán bằng `-XshowSettings:system`/`-Xlog:os+container` đúng platform không?
27. Có thử kernel quota thật trên Linux, không nhầm với flag JVM không?
28. Có tránh assert thời gian tuyệt đối cứng trên CI chia sẻ không?
29. Có biết xử lý container không có Docker daemon/cgroup access thế nào không?
30. Có lưu dữ liệu benchmark và release/commit/environment để lần sau so sánh không?

## 23. Tổng kết

**Kiểm thử cùng ứng dụng dưới các mức cấp CPU khác nhau** phải đồng thời xem ba tầng:

1. **Kernel/container:** CPU quota, cpuset, shares/weight và throttling thực tế.
2. **JVM/ứng dụng:** `Runtime.getRuntime().availableProcessors()`, `-XX:ActiveProcessorCount` và worker pool sizing.
3. **Kết quả chạy:** correctness, elapsed/throughput/latency, GC/JIT và CPU-throttling metrics.

Java 10 mở rộng khả năng nhận biết CPU container của HotSpot. Trên JDK hiện đại, không quay lại mặc định hiểu CPU shares như hard CPU count; những thay đổi từ JDK-8281181 và backports là lý do phải đối chiếu runtime thực tế. **`ActiveProcessorCount` chỉ thay tính toán CPU của JVM, không thực thi giới hạn CPU kernel**.

Dùng một JAR, một JDK và cùng workload để so 0.5/1/2/4 CPUs, kiểm checksum trước khi bàn về tốc độ, và thu `cpu.max`/`cpu.stat` khi chạy trên Linux container. Nếu không có Linux container engine, chỉ công bố kết quả kiểm thử flag JVM local, không gọi đó là kết quả quota thật. Tránh dùng một số đo elapsedMs, số workers hoặc một giá trị `availableProcessors` để tự suy ra toàn bộ hành vi CPU. Bằng chứng đáng tin đến từ **thử nghiệm có kiểm soát, nhiều lần đo và các chỉ số ở cả JVM lẫn kernel**.

### Tài liệu tham khảo còn phù hợp

- [Oracle JDK 10 release notes — Java Improvements for Docker Containers (JDK-8146115)](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html)
- [Oracle Java 17 — The java Command, ActiveProcessorCount, UseContainerSupport](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java 21 — The java Command, -XshowSettings:system, OS+container logs](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 19 release notes — CPU Shares Ignored When Computing Active Processor Count (JDK-8281181)](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html)
- [Oracle JDK 17.0.4 release notes — CPU Shares Ignored / backport](https://www.oracle.com/java/technologies/javase/17-0-4-relnotes.html)
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Linux kernel — cgroup v2 CPU controller: cpu.max, cpu.stat, cpu.weight](https://cdn.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)
- [Docker — Resource constraints on containers](https://docs.docker.com/engine/containers/resource_constraints/)
- [Java SE 17 — Runtime.availableProcessors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html)
- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)