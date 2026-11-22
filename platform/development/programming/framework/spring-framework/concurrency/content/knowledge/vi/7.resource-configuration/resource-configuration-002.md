# Chọn số luồng cho tác vụ nặng CPU và tác vụ thường chờ nhập xuất

**Module:** Spring Framework - concurrency  
**Nhóm kiến thức:** Cấu hình tài nguyên  
**Mục tiêu:** Hiểu vì sao tác vụ chủ yếu dùng CPU và tác vụ thường xuyên chờ I/O cần hai chiến lược cấp phát luồng khác nhau; biết đặt `corePoolSize`, `maxPoolSize`, `queueCapacity`, giới hạn tài nguyên, đo đạc và điều chỉnh một cách có căn cứ trong Spring.

## 1. Tại sao số luồng không thể chọn theo một công thức cố định?

Một luồng Java có thể ở trạng thái **đang tiêu thụ CPU** hoặc **đang chờ** mạng, cơ sở dữ liệu, ổ đĩa, khóa, semaphore, timer và các tài nguyên khác. Với số lượng CPU hữu hạn, thêm luồng có thể tăng throughput khi nhiều luồng vốn đang chờ, nhưng có thể làm một hệ thống CPU đã bão hòa chậm hơn vì chuyển ngữ cảnh, tranh chấp cache và lập lịch.

Ví dụ có bốn lõi CPU khả dụng:

- **Bốn tác vụ tính toán liên tục:** khoảng bốn worker chạy thực sự song song nếu mỗi tác vụ chỉ dùng một lõi và máy không bị công việc khác chiếm nhiều CPU. Tăng lên 100 worker không tạo ra 100 lõi.
- **Bốn tác vụ chờ HTTP/DB trong phần lớn vòng đời:** mỗi worker chiếm thread nhưng không dùng CPU liên tục. Nhiều worker hơn có thể tận dụng CPU trong lúc các worker khác chờ, **cho đến khi** đạt giới hạn connection, remote service, bộ nhớ, băng thông hoặc timeout.
- **Bốn tác vụ gọi API theo kiểu non-blocking:** số request đang chờ mạng có thể lớn hơn số thread; không áp dụng nguyên xi tư duy “mỗi request chờ = một thread bị giữ”.

Do đó cần phân loại khối công việc, đo thời gian **tính toán (compute)** và **chờ (wait)**, biết giới hạn tài nguyên, rồi đặt một pool có hàng đợi và cơ chế từ chối rõ ràng.

### Hai mục tiêu thường xung đột

1. **Throughput:** số công việc hoàn thành mỗi giây.
2. **Latency:** thời gian từ lúc nhận việc đến khi trả kết quả; cần tách thành **queue wait** và **execution time**.

Thêm thread đôi khi cải thiện throughput nhưng khiến tail latency xấu đi khi downstream bị dồn tải. Một pool có queue lớn có thể ít từ chối tác vụ trước mắt nhưng làm hàng đợi kéo dài nhiều giây hoặc phút. **Số luồng không thể tối ưu riêng lẻ mà bỏ qua queue và downstream.**

## 2. Nhận diện CPU-bound, blocking I/O-bound và non-blocking I/O

| Loại tác vụ | Phần lớn thời gian | Dấu hiệu đo đạc | Hướng chọn concurrency |
| --- | --- | --- | --- |
| **CPU-bound** | Chạy phép toán, nén, mã hóa, parse nặng, xử lý ảnh, biến đổi dữ liệu trong RAM | CPU gần bão hòa; thêm worker tăng context switch nhưng throughput không tăng | Số worker hoạt động xấp xỉ số lõi CPU khả dụng; pool thường cố định, queue hữu hạn |
| **Blocking I/O-bound** | Thread bị giữ trong `InputStream.read`, JDBC, REST client đồng bộ, socket call, chờ lock | CPU còn dư trong khi nhiều thread `WAITING`/`TIMED_WAITING`/blocked ở stack trace | Có thể dùng nhiều worker hơn lõi CPU, nhưng giới hạn bởi connection pool và nguồn bên ngoài |
| **Non-blocking I/O** | Đăng ký hoạt động I/O và nhận callback/signal khi có dữ liệu; không giữ một worker để đợi từng request | Ít event-loop thread xử lý rất nhiều kết nối, CPU không bị chặn ở I/O | Không tăng event-loop thread theo số request; tránh chạy CPU hoặc blocking code trên event loop |
| **Mixed workload** | Có cả tính toán nặng và gọi I/O chặn | CPU lúc cao, lúc thấp; pool chung có hàng chờ không ổn định | Tách CPU pool và blocking I/O pool hoặc giới hạn riêng từng loại; đo bằng tải thực |

Một công việc có thể *cả hai*: ví dụ nhận HTTP, parse JSON, tính chữ ký, gửi JDBC query, biến đổi ảnh. Phân loại dựa vào nơi **thời gian thực sự trôi qua**, không chỉ tên method hay framework.

Phân biệt rất quan trọng:

- Gọi `Thread.sleep(...)` là **chặn thread**, nhưng không phải I/O thực. Dùng sleep chỉ để mô phỏng thời gian chờ trong ví dụ kiểm thử.
- Gọi `CompletableFuture.supplyAsync` không tự biến một JDBC call đồng bộ thành non-blocking I/O; nó chỉ chuyển công việc chặn sang một worker khác.
- WebFlux, Reactor/Netty giúp tổ chức I/O bất đồng bộ khi driver/client thực sự non-blocking. Đặt phép tính CPU dài hoặc JDBC chặn trên event loop vẫn gây nghẽn.
- Java 21+ có virtual threads: nhiều thao tác blocking có thể dùng virtual thread để giảm chi phí giữ *platform thread*. Điều này **không** làm CPU vô hạn và không tự tăng giới hạn DB connections, rate limit hay khả năng của dịch vụ ngoài.

## 3. Tính đúng số CPU thực sự khả dụng

Dùng một điểm xuất phát:

```java
int processors = Runtime.getRuntime().availableProcessors();
System.out.println("reportedProcessors=" + processors);
```

Đoạn Java trên là **minh họa** về cách lấy số bộ xử lý được JVM báo cáo, không phải toàn bộ chương trình độc lập. Giá trị có thể phản ánh giới hạn affinity/container tùy phiên bản JVM và môi trường, nhưng vẫn phải kiểm tra thực tế **CPU quota, cgroup, số lõi bị tranh chấp, SMT/hyper-threading và giới hạn hạ tầng**.

Đặt:

- `P` = lượng năng lực CPU khả dụng cho **quy trình này** (đơn vị lõi CPU tương đương, có thể nhỏ hơn số lõi máy vật lý).
- `U` = mức sử dụng CPU mục tiêu cho pool, ví dụ `0.75` đến `0.9` để còn dư cho HTTP, GC và tác vụ khác.
- `N_cpu` = số **worker đồng thời có thể chạy CPU**.

Điểm khởi đầu thường dùng cho công việc CPU-bound thuần:

\[
N_{\mathrm{cpu}} \approx P
\]

Nếu JVM còn chạy HTTP, GC, scheduler, hoặc nhiều pool CPU, cần chia tổng ngân sách CPU giữa chúng. Với CPU rất ít hoặc quota lẻ, số worker phải là số nguyên ít nhất một; không diễn giải công thức như một bảo đảm throughput tối ưu.

### Ví dụ

Giả sử container có ngân sách CPU tương đương **4 lõi**, tác vụ làm phép tính dài và không đợi I/O. Bắt đầu thử **3–4 worker CPU** cho riêng pool này, dùng queue hữu hạn, đo throughput và p95/p99. Tăng lên 8 chỉ có ích nếu tác vụ thực sự có phần chờ đáng kể hoặc CPU còn dư; nếu CPU luôn 100%, có thể làm trễ xử lý vì tranh CPU.

**Đừng tạo một pool CPU 4 worker cho từng endpoint** rồi cộng thành hàng chục pool chạy tối đa đồng thời. Tổng concurrency của tất cả pool và request thread mới là yếu tố gây quá tải CPU.

### Dấu hiệu CPU-bound trên hệ thống thực

- CPU process/container cao liên tục; runnable thread nhiều hơn CPU khả dụng.
- Profiling cho thấy thời gian tích lũy ở hàm tính toán, mã hóa, giải nén, JSON conversion, vòng lặp.
- Khi tăng từ 4 lên 8 worker: throughput không tăng, CPU giữ nguyên, context switching và p99 tăng.
- Nhiều worker cùng cập nhật một cấu trúc dữ liệu hoặc lock có thể **không** mở rộng theo số lõi: phải sửa contention, chia nhỏ dữ liệu hoặc giảm critical section.

## 4. Sizing cho blocking I/O: thời gian chờ là yếu tố chủ chốt

Với tác vụ blocking, đặt:

- `C` = thời gian CPU thực sự dùng cho một công việc, chẳng hạn **20 ms**.
- `W` = thời gian thread chờ I/O, chẳng hạn **80 ms**.
- `P` = số lõi CPU khả dụng.
- `U` = CPU utilization mục tiêu trong phạm vi pool.

Một heuristic để **ước lượng thử nghiệm ban đầu**, với các việc độc lập và điều kiện tương đối ổn định, là:

\[
N_{\mathrm{blocking}} \approx P \times U \times \left(1 + \frac{W}{C}\right)
\]

Ví dụ `P = 4`, `U = 0.8`, `W = 80 ms`, `C = 20 ms`:

\[
N \approx 4 \times 0.8 \times (1+4)=16
\]

Giải thích: một worker dành khoảng 20% thời gian tính toán và 80% để đợi; cần nhiều tác vụ đang hoạt động để giữ CPU hữu ích trong lúc các tác vụ khác chờ.

Đây là **ước lượng, không phải đáp số bắt buộc**. Công thức không thể thay cho load test, và thường trở nên sai khi có bottleneck downstream, thay đổi tỷ lệ W/C, contention, batching, cache, CPU burst, timeout hoặc tác vụ không độc lập.

### Giới hạn I/O thật quan trọng hơn phép tính 16

Giả sử 16 worker đều gọi cùng một database, nhưng pool JDBC chỉ có **8 connection**. Chỉ tối đa 8 query có thể dùng connection cùng lúc; các worker còn lại có thể chờ lấy connection ngay trong JVM. Tăng tiếp lên 64 worker có thể làm tăng thời gian chờ, request timeout và bộ nhớ mà không tăng query throughput.

Giới hạn cần xét:

- JDBC connection pool, giới hạn connection đồng thời của database và transaction duration.
- HTTP connection pool, số request đồng thời được đối tác cho phép, rate limit và latency mạng.
- File descriptors, sockets, memory/thread stack, heap pressure, GC.
- Độ trễ hàng đợi downstream và retry amplification: khi remote service chậm, số task đồng thời có thể bùng lên.
- SLA: mỗi request có **deadline**, timeout và chính sách retry; queue không được giữ các task đã quá hạn.

Đặt một **concurrency limit riêng** bằng semaphore/bulkhead ở sát tài nguyên nếu cần. `N_threads = 16` không nhất thiết đồng nghĩa cho phép 16 truy vấn DB đồng thời.

### Little's Law để kiểm tra tải

Ở trạng thái ổn định:

\[
L = \lambda \times T
\]

Trong đó `L` là số công việc trung bình đang ở trong hệ thống, `λ` là throughput (việc/giây), `T` là tổng thời gian một công việc lưu lại trong hệ thống (giây), **bao gồm thời gian xếp hàng** nếu đo cả hệ thống. Ví dụ throughput 100 việc/giây với thời gian trung bình 0,2 giây thì có khoảng 20 công việc in-flight trung bình.

Không suy ra “luôn cần 20 thread” từ con số đó: công việc có thể dùng non-blocking I/O, nhiều job có thể đang chờ trong queue và các pool phía sau có thể dùng tài nguyên khác. Little's Law giúp kiểm tra quan hệ tải và độ trễ, không thay thế sizing cho từng pool.

## 5. Cấu trúc ThreadPool trong Spring: `core`, `max` và queue liên hệ thế nào?

`ThreadPoolTaskExecutor` là lựa chọn tiện dụng của Spring để quản lý pool theo bean. Với một cấu hình thông thường:

```java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setQueueCapacity(40);
```

Các giá trị trên chỉ là **ví dụ để hiểu cơ chế**, không tự động phù hợp mọi dịch vụ.

Trong `ThreadPoolExecutor` được Spring bọc, khi một task mới đến:

1. Nếu số worker đang tồn tại **nhỏ hơn `corePoolSize`**, executor ưu tiên tạo worker mới để xử lý.
2. Khi đạt core, executor **ưu tiên đưa task vào queue** nếu còn chỗ.
3. **Chỉ khi queue không nhận thêm**, executor mới tạo thêm worker vượt core, tối đa `maxPoolSize`.
4. Nếu worker đã đạt max và queue không nhận thêm, task bị từ chối theo `RejectedExecutionHandler`.

```text
Task đến
  |
  +-- Worker count < core? ---- Có ----> Tạo worker, chạy task
  |
  +-- Queue còn chỗ? --------- Có ----> Xếp hàng chờ
  |
  +-- Worker count < max? ----- Có ----> Tạo worker vượt core
  |
  +-- Từ chối / thực thi ở caller tùy rejection policy
```

Hệ quả dễ gây bất ngờ: **`maxPoolSize=100` không có nghĩa pool sẽ tăng đến 100 khi CPU bận**. Nếu queue đủ rộng hoặc không giới hạn, sau khi đạt core, công việc có thể cứ xếp hàng mà không kích hoạt worker mới.

Cần hiểu các thuộc tính:

| Thuộc tính | Vai trò | Lưu ý |
| --- | --- | --- |
| `corePoolSize` | Số worker mục tiêu duy trì ở tải thường | Không phải tổng số task đang chạy và chờ |
| `maxPoolSize` | Giới hạn worker pool trong các đợt tăng | Chỉ phát huy khi queue không nhận thêm task |
| `queueCapacity` | Số task **đang chờ**, không tính task đang chạy | Cần hạn mức hữu hạn theo bộ nhớ/độ trễ cho production |
| `keepAliveSeconds` | Thời gian idle trước khi worker vượt core được thu hồi | Không giải quyết queue quá lớn |
| `threadNamePrefix` | Giúp nhận diện thread trong log/thread dump | Tách tên pool CPU/IO để quan sát |
| `RejectedExecutionHandler` | Chính sách khi worker/queue không còn sức chứa | `AbortPolicy` báo lỗi; `CallerRunsPolicy` có thể chạy task trên thread gửi |
| `TaskDecorator` | Bọc callback chạy task (context/metrics) | Cần cleanup `ThreadLocal`; không tự chuyển transaction |

**Mặc định của lớp Spring `ThreadPoolTaskExecutor`** có core 1, max rất lớn và queue capacity rất lớn. Vì queue mặc định không giới hạn theo nhu cầu thực, không nên chỉ cấu hình `maxPoolSize` mà kỳ vọng tự mở rộng nhanh; chủ động quyết định core, max và queue.

Một `ThreadPoolTaskExecutor` với queue capacity **0** dùng cơ chế chuyển giao trực tiếp tương tự `SynchronousQueue`, thường có thể mở rộng nhanh khi task đến; nếu max quá lớn, lại có nguy cơ tăng thread đột biến. Dùng khi đã hiểu hành vi từ chối và áp lực tải.

## 6. Tách pool CPU và blocking I/O trong ứng dụng Spring

Nếu dùng chung một executor cho cả nén file nặng CPU và JDBC/HTTP blocking, các task blocking có thể chiếm hết worker khiến công việc CPU không được chạy dù CPU đang rảnh. Ngược lại, CPU-bound task có thể chiếm pool và trì hoãn I/O. Có thể dùng **hai bean executor**, mỗi bean có queue và giới hạn riêng.

Ví dụ **Spring Framework 6.x, Java 17+**, dành cho ứng dụng Spring Boot dùng `spring-boot-starter-web` hoặc cấu hình Spring có `spring-context`.

Lưu file `src/main/java/com/example/sizing/ExecutorConfiguration.java`:

```java
package com.example.sizing;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ExecutorConfiguration {

    @Bean("cpuExecutor")
    public ThreadPoolTaskExecutor cpuExecutor() {
        int available = Runtime.getRuntime().availableProcessors();

        // Trần 8 là giới hạn minh họa của ứng dụng, không phải quy tắc chung.
        int cpuWorkers = Math.max(1, Math.min(8, available));
        return createExecutor("cpu-", cpuWorkers, cpuWorkers, 32);
    }

    @Bean("blockingIoExecutor")
    public ThreadPoolTaskExecutor blockingIoExecutor() {
        // 8/16/64 chỉ là cấu hình khởi đầu để đo; kiểm tra giới hạn DB/API.
        return createExecutor("blocking-io-", 8, 16, 64);
    }

    private static ThreadPoolTaskExecutor createExecutor(
            String prefix, int core, int max, int queueCapacity) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(core);
        executor.setMaxPoolSize(max);
        executor.setQueueCapacity(queueCapacity);
        executor.setThreadNamePrefix(prefix);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

Lưu file `src/main/java/com/example/sizing/WorkService.java`:

```java
package com.example.sizing;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class WorkService {

    @Async("cpuExecutor")
    public CompletableFuture<Long> calculate(int upperBound) {
        if (upperBound < 0) {
            return CompletableFuture.failedFuture(
                    new IllegalArgumentException("upperBound must be >= 0"));
        }
        long sum = 0;
        for (int i = 1; i <= upperBound; i++) {
            sum += i;
        }
        return CompletableFuture.completedFuture(sum);
    }

    @Async("blockingIoExecutor")
    public CompletableFuture<String> fetchLegacy(String key) {
        try {
            // Chỉ mô phỏng 50 ms blocking I/O; không phải lời gọi mạng thật.
            TimeUnit.MILLISECONDS.sleep(50);
            return CompletableFuture.completedFuture("data-" + key);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }
    }
}
```

Hai file trên là **các class hoàn chỉnh trong một ứng dụng Spring**; muốn chạy dưới Spring Boot cần có class `@SpringBootApplication` và dependency tương ứng. Không thể dùng `javac` thuần khi chưa có Spring trên classpath. Ví dụ `fetchLegacy` chỉ mô phỏng thời gian bị chặn; trong ứng dụng thật, thay bằng JDBC/HTTP client đồng bộ có timeout và đo phần chờ thực.

Giải thích những quyết định:

- `cpuExecutor`: fixed-size pool theo một ngân sách CPU giới hạn, tránh tạo thread vượt số lõi có ích.
- `blockingIoExecutor`: cho phép concurrency cao hơn vì mỗi worker có phần chờ; nhưng `8`, `16`, `64` **không phải giá trị production mặc định**. Phải đo `W/C` và giới hạn downstream.
- Queue hữu hạn giúp biết điểm bão hòa; với `AbortPolicy`, Spring báo `TaskRejectedException` khi không nhận việc. Bên gửi task phải xử lý tình trạng bận theo hợp đồng API.
- `@Async("cpuExecutor")` và `@Async("blockingIoExecutor")` buộc Spring chọn bean có tên rõ ràng; tránh dùng mặc định một pool cho mọi loại việc.
- `@EnableAsync` trong cấu hình proxy mặc định chỉ intercept lời gọi qua **Spring proxy**. Gọi `this.calculate()` trong cùng bean bỏ qua proxy và có thể thực thi ngay trên thread gọi.
- `@Async` làm việc ở thread khác: transaction, request context và các `ThreadLocal` tùy biến không tự động đi theo. Worker nên có ranh giới transaction riêng và truyền dữ liệu cần thiết một cách tường minh.
- Bean `ThreadPoolTaskExecutor` được Spring quản lý lifecycle khi đăng ký đúng cách; tránh tự tạo pool mới trong mỗi request hoặc gọi `shutdown` trong controller.

Nếu ứng dụng cần nhiều CPU pool, tính **tổng** số worker CPU đồng thời qua mọi pool, không xem `availableProcessors()` là hạn mức riêng cho từng bean.

## 7. Java 17 chạy độc lập: cùng số job, hai kiểu công việc và overload

Để hiểu cơ chế mà không cần khởi động Spring, chương trình JDK sau chạy:

1. **12 tác vụ CPU:** mỗi tác vụ cộng các số từ `1` đến `100_000`, dùng pool 2 worker.
2. **12 tác vụ mô phỏng blocking I/O:** mỗi tác vụ chờ `20 ms`, dùng pool 4 worker.
3. **Một pool có 1 worker + 1 chỗ queue:** giữ worker bằng `CountDownLatch`, xếp thêm 1 job, rồi kiểm tra job thứ ba bị từ chối theo `AbortPolicy`.

Cả hai kích thước pool chỉ nhằm minh họa. Không lấy thời gian chạy của ví dụ nhỏ làm kết luận benchmark. Điều được kiểm chứng là **kết quả không mất việc**, hành vi chờ khác nhau và queue hữu hạn có thể từ chối tác vụ.

Lưu toàn bộ vào **`WorkloadSizingDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class WorkloadSizingDemo {

    static long cpuWork() {
        long total = 0;
        for (int i = 1; i <= 100_000; i++) {
            total += i;
        }
        return total;
    }

    static long runJobs(int workers, int jobs, Callable<Long> task)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        try {
            List<Future<Long>> futures = new ArrayList<>();
            for (int i = 0; i < jobs; i++) {
                futures.add(pool.submit(task));
            }

            long total = 0;
            for (Future<Long> future : futures) {
                total += future.get();
            }
            return total;
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    static boolean rejectWhenFull() throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch running = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> first = pool.submit(() -> {
                running.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!running.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // 1 worker đang bận; job này chiếm đúng 1 vị trí queue.
            Future<?> second = pool.submit(() -> { });

            boolean rejected = false;
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            release.countDown();
            first.get();
            second.get();
            return rejected;
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        long cpuTotal = runJobs(2, 12, WorkloadSizingDemo::cpuWork);

        long ioTotal = runJobs(4, 12, () -> {
            TimeUnit.MILLISECONDS.sleep(20); // Mô phỏng chờ I/O.
            return 1L;
        });

        System.out.println("cpuTotal=" + cpuTotal);
        System.out.println("ioTotal=" + ioTotal);
        System.out.println("rejected=" + rejectWhenFull());
    }
}
```

Chạy:

```bash
javac WorkloadSizingDemo.java
java WorkloadSizingDemo
```

**Stdout khi chương trình hoàn tất bình thường:**

```text
cpuTotal=60000600000
ioTotal=12
rejected=true
```

Tại sao kết quả ổn định?

- Một job CPU cộng `1 + 2 + ... + 100000 = 5.000.050.000`; nhân 12 job được `60.000.600.000`. Dùng `long` để không tràn số 32 bit.
- Mỗi job I/O mô phỏng trả `1`, tổng 12 là `12`; chỉ thứ tự/thời gian task chạy là không xác định.
- Trong `rejectWhenFull`, latch xác nhận worker duy nhất đã thực sự bắt đầu và đang chờ; sau đó job thứ hai đi vào queue có sức chứa một, nên job thứ ba không còn worker/queue và bị từ chối. `finally` luôn mở latch và dừng pool để không treo chương trình.

**Lưu ý quan trọng:** `Executors.newFixedThreadPool` dùng queue không giới hạn theo lượng bộ nhớ nên chỉ phù hợp để tạo ví dụ đơn giản ở đây. Trong dịch vụ chịu tải, cấu hình `ThreadPoolExecutor`/Spring `ThreadPoolTaskExecutor` có **bounded queue** và rejection policy phù hợp. `Future.get()` trong `runJobs` có mục đích đợi kết quả kiểm thử; controller HTTP production cần cân nhắc khi nào được phép chặn.

## 8. Làm thế nào để chọn kích thước pool có thể kiểm chứng?

Thay vì nhìn CPU count rồi điền một số cố định, hãy đo ở **mức tải mục tiêu**, gồm tải thường và peak.

### Bước 1 — Xác định một đơn vị công việc

Ví dụ `renderPdf`, `recalculatePrice`, `callPartnerApi`, `sendEmail`. Đo riêng từng loại để không trộn CPU và blocking I/O. Nếu một task chứa nhiều giai đoạn, có thể đo CPU time và wall time cho từng giai đoạn.

Thông số gợi ý:

- Arrival rate `λ` (task/s), completion rate (task/s).
- CPU time trung bình/task và wall-clock duration/task.
- Phân phối waiting time, đặc biệt p95/p99 của JDBC/HTTP.
- Số task đang chạy, số đang queue, queue wait p50/p95/p99.
- Số active threads, pool size, số lần reject.
- CPU utilization theo **container quota**, heap/GC và memory.
- JDBC pool: active, idle, pending acquisition, acquisition timeout; HTTP pool và remote error/timeout.

### Bước 2 — Chọn điểm xuất phát

**Tác vụ CPU:** bắt đầu `N ≈ P` cho tổng ngân sách công việc CPU tương ứng; nếu JVM còn nhiều trách nhiệm, giảm hoặc chia ngân sách. Với 4 lõi, thử 3–4 worker.

**Blocking I/O:** đo `W/C`, dùng `P×U×(1+W/C)` để có điểm xuất phát, rồi **giới hạn bằng tài nguyên I/O**. Ví dụ heuristic cho 16 worker nhưng JDBC pool chỉ có 8 connections: cần kiểm tra DB, không chọn 16 chỉ vì công thức trả về 16.

**Mixed:** chia pool theo tài nguyên/giai đoạn nếu lợi ích cô lập tải rõ ràng. Ví dụ một pool CPU cho chuyển đổi ảnh và một pool I/O cho upload. Nếu chi phí tách và chuyển task không đáng, có thể giữ pool chung nhỏ nhưng phải đo hiện tượng starvation.

### Bước 3 — Chọn queue bằng **ngân sách chờ**

Giả sử pool CPU xử lý được trung bình 40 job/s trong peak ngắn, client không muốn một job đợi quá 0,5 giây *chỉ trong queue*. Một queue 20 job tương ứng khoảng 0,5 giây đợi theo tốc độ xử lý giả định trong điều kiện bão hòa ổn định (`20/40 = 0,5 s`). Đây chỉ là **ước lượng giản lược**: với arrival burst, thời gian phục vụ biến động, task ưu tiên hay nhiều loại job, queue latency thực có thể khác rất nhiều.

Queue rất lớn không giải quyết thiếu throughput nếu arrival rate dài hạn vượt completion rate. Khi đó thời gian chờ tăng không giới hạn cho đến khi tràn tài nguyên. Chọn queue hữu hạn theo deadline/SLI, sau đó xác định hệ thống phản ứng ra sao khi đầy.

### Bước 4 — Load test theo ma trận, giữ tiêu chí chấp nhận

Ví dụ cho CPU pool có ngân sách 4 lõi: thử worker `2, 3, 4, 6` với cùng dữ liệu và arrival pattern. Với I/O: thử `4, 8, 12, 16`, đồng thời đo connection pool và remote throughput. Mỗi tổ hợp đo:

- Throughput thành công và tỷ lệ lỗi/rejection.
- p50/p95/p99 từ lúc nhận việc tới xong, tách riêng queue wait.
- CPU throttling, time in GC, memory, lock contention.
- Downstream timeouts, JDBC pending/connection wait.
- Thời gian phục hồi sau burst.

Chọn **cấu hình nhỏ nhất đáp ứng SLO** ở peak dự kiến, còn khoảng dư cho lỗi/thay đổi tải. Một con số tốt trong máy dev có thể tệ trên container bị giới hạn 1 CPU hoặc ở production có 20 replica.

### Bước 5 — Theo dõi để điều chỉnh

`ThreadPoolTaskExecutor` hỗ trợ introspection như:

```java
int active = cpuExecutor.getActiveCount();
int currentPoolSize = cpuExecutor.getPoolSize();
int queueDepth =
        cpuExecutor.getThreadPoolExecutor().getQueue().size();
```

Đây là **đoạn mã minh họa** trong bean có tham chiếu `cpuExecutor`; phải gọi sau khi executor được khởi tạo. Kết hợp metrics từ Spring Boot Actuator/Micrometer hoặc bộ đo đang dùng để quan sát hàng đợi, số task bị từ chối, hiệu năng và tài nguyên. Đừng chỉ nhìn active thread mà kết luận mọi worker đang dùng CPU: chúng có thể đang chờ I/O hoặc lock.

## 9. Backpressure, timeout và công việc không thể nhận thêm

Khi pool/queue chạm hạn mức, cần **một hợp đồng phản hồi**. Tùy loại hệ thống:

1. API đồng bộ có thể trả `429 Too Many Requests` hoặc `503 Service Unavailable` theo chính sách tải, kèm gợi ý retry khi phù hợp.
2. Job API trả `202 Accepted` chỉ sau khi đã **nhận công việc** theo mức bảo đảm của nó. Nếu executor trong RAM từ chối, không được báo đã chấp nhận thành công.
3. Job quan trọng cần lưu bền vững: DB/job queue, message broker, transactional outbox, retry có giới hạn và idempotency. Thread pool Java/Spring **không** thay cho hệ thống hàng đợi bền vững.
4. Có thể giới hạn số lời gọi downstream đồng thời bằng semaphore/bulkhead; nếu không lấy permit trong deadline, từ chối sớm thay vì giữ một worker chờ vô hạn.
5. Đặt timeout cho HTTP/JDBC/DB lock phù hợp với deadline tổng; retry phải có backoff, jitter và giới hạn thử lại để tránh nhân tải khi bên ngoài đang lỗi.

`CallerRunsPolicy` của JDK là một dạng backpressure: khi không nhận được task và executor chưa shutdown, thread **gửi task** có thể tự chạy task. Nếu đó là Servlet request thread, nó có thể bị giữ trong tác vụ nặng; không nên coi chính sách này là “luôn trả lỗi khi đầy”. Với Spring `ThreadPoolTaskExecutor`, nếu muốn báo quá tải rõ ràng có thể chọn `AbortPolicy`, bắt `TaskRejectedException` ở ranh giới giao việc và chuyển thành response phù hợp.

### Không mở rộng pool để che giấu lỗi nội bộ

- Pool I/O tràn vì thiếu timeout HTTP: sửa timeout/connection management trước.
- Pool CPU quá bận vì mỗi job giữ khóa toàn cục: profile và giảm contention trước.
- JDBC connection pool cạn vì transaction mở trong khi gọi remote API: thu hẹp transaction; thêm worker chỉ khiến chờ dài hơn.
- Queue tăng nhanh vì upstream gửi nhanh hơn công suất lâu dài: cần kiểm soát tốc độ/scale thực sự, không chỉ tăng `queueCapacity`.

## 10. Các tình huống dễ chọn sai

| Hiện tượng | Giả định dễ sai | Cách xử lý đúng |
| --- | --- | --- |
| CPU 100%, tăng từ 4 lên 40 worker | “Nhiều luồng luôn xử lý nhanh hơn” | Giới hạn gần CPU hữu ích, đo context switch và throughput |
| CPU thấp, nhiều thread chờ DB | “Cứ tăng thread lên vài trăm” | Kiểm tra connection pool, query latency, locking và pending acquisition |
| `maxPoolSize=32`, core=4, queue rất lớn | “Pool sẽ dùng ngay 32 thread khi bận” | Hiểu queue-before-grow; đặt queue hữu hạn và core phù hợp |
| `queueCapacity` cực lớn | “Không còn lỗi overload” | Queue wait kéo dài, tràn bộ nhớ; chọn giới hạn theo deadline |
| `@Async` gọi từ cùng bean qua `this.method()` | “Tự động chạy trên executor” | Dùng lời gọi qua Spring proxy, kiểm tra cấu hình `@EnableAsync` |
| Chạy JDBC blocking trong Netty event loop | “WebFlux đã non-blocking cho mọi dependency” | Driver non-blocking hoặc chuyển blocking work sang scheduler phù hợp có giới hạn |
| Dùng virtual thread cho hàng nghìn query cùng lúc | “Virtual thread giải quyết luôn giới hạn DB” | Vẫn giới hạn connections/rate/deadline; virtual thread chủ yếu giảm chi phí chờ thread |
| Một pool chung cho tác vụ CPU và chờ mạng | “Pool đủ lớn sẽ công bằng” | Tách hoặc hạn mức theo loại việc; theo dõi starvation |
| Pool từ request tạo mới liên tục | “Mỗi request có pool riêng sẽ song song hơn” | Dùng bean/pool sống cùng ứng dụng, quản lý lifecycle |
| Trả `202` dù executor từ chối task | “Gửi API thành công nghĩa là đã ghi nhận job” | Chỉ báo accepted khi nhận việc chắc chắn, có lỗi overload rõ ràng |
| Dựa vào `availableProcessors()` như số lõi máy | “Giá trị này là năng lực CPU ổn định mọi môi trường” | Kiểm tra container quota/CPU throttling và đo tải thật |
| Chọn số thread qua `sleep` benchmark đơn giản | “IO lúc nào cũng tỉ lệ 80% chờ” | Đo W/C và phân phối latency của I/O production |

## 11. Tự kiểm tra

**Câu 1.** Một server có ngân sách CPU 4 lõi, xử lý tác vụ thuần tính toán không block. Chọn 40 thread có giúp đạt throughput cao hơn 4 thread gấp 10 lần không?  
**Trả lời:** Không. Số lõi giới hạn công việc CPU song song; thêm nhiều thread thường tăng lập lịch/tranh chấp, cần đo nếu có các yếu tố khác.

**Câu 2.** Công thức heuristic `N ≈ P × U × (1 + W/C)` với `P=4`, `U=0,8`, `W/C=4` cho bao nhiêu?  
**Trả lời:** 16 worker để **thử nghiệm ban đầu**. Phải kiểm tra số connection, remote quota và thời gian chờ queue; không coi 16 là cấu hình tối ưu chắc chắn.

**Câu 3.** Spring `ThreadPoolTaskExecutor(core=4,max=16,queue=100)` có tăng ngay lên 16 thread khi 5 job CPU đang chạy không?  
**Trả lời:** Không nhất thiết. Khi đã đạt core, pool ưu tiên xếp task vào queue trước; chỉ khi queue không nhận thêm mới thử mở rộng vượt core.

**Câu 4.** Có 32 worker làm JDBC, nhưng pool connection chỉ có 8 và CPU thấp. Tăng lên 64 worker có chắc tăng throughput không?  
**Trả lời:** Không. Khả năng phục vụ của DB/connection giới hạn; có thể chỉ tăng thời gian chờ và memory. Cần profile query, connection wait và concurrency limit.

**Câu 5.** Vì sao nên tách CPU executor và blocking I/O executor?  
**Trả lời:** Để worker chờ I/O không giữ hết slot dành cho CPU, có thể đặt queue/budget/backpressure riêng và đo độc lập.

**Câu 6.** Một API trả `202` ngay khi gọi `@Async`, nhưng executor đang đầy và task bị từ chối. Hợp đồng có đúng không?  
**Trả lời:** Không, nếu chưa có cơ chế nhận việc bền vững khác. Phải xử lý `TaskRejectedException` và phản hồi rằng hệ thống chưa nhận job.

**Câu 7.** Virtual threads có cho phép bỏ giới hạn remote connection, request timeout và rate limit không?  
**Trả lời:** Không. Chúng thay đổi chi phí lưu giữ thread khi blocking; tài nguyên vật lý, CPU và downstream vẫn hữu hạn.

**Câu 8.** `queueDepth` liên tục tăng trong khi `activeCount == maxPoolSize`; nên tăng `queueCapacity` trước hay điều tra throughput?  
**Trả lời:** Điều tra arrival/completion rate, thời gian xử lý, timeout, bottleneck và giới hạn downstream; queue lớn hơn chỉ kéo dài thời gian chờ nếu tốc độ đến vượt tốc độ xử lý lâu dài.

## 12. Ghi nhớ và tài liệu tham khảo

- **CPU-bound:** khởi đầu gần ngân sách lõi CPU khả dụng, tránh pool quá đông; ưu tiên profiler và đo throughput/tail latency.
- **Blocking I/O-bound:** có thể cần nhiều worker hơn số lõi; dùng tỷ lệ chờ/tính toán để ước lượng, sau đó chặn trên bằng giới hạn connection, memory, timeout và load test.
- **Non-blocking I/O:** concurrency request có thể lớn mà không giữ một platform thread cho mỗi lời gọi; không đưa blocking work lên event loop.
- **Trong Spring:** cấu hình rõ `corePoolSize`, `maxPoolSize` và `queueCapacity`. Queue được dùng trước khi vượt core; dùng pool hữu hạn, rejection policy và tách executor theo tài nguyên khi thích hợp.
- **Trong production:** sizing là một vòng lặp **đo → giả thuyết → thử tải → quan sát → điều chỉnh**, không phải công thức cho một giá trị cố định.

Tài liệu chính thức:

- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — abstraction, cấu hình thread pool, hành vi queue trước khi tăng worker.
- [Spring Framework – `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — các thuộc tính core/max/queue, trạng thái pool, rejection.
- [Java SE 17 – `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — nguyên tắc chọn thread/queue và rejection policy.
- [Java SE 17 – `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html) — submit, shutdown và lifecycle.
- [Spring Framework – `@Async`](https://docs.spring.io/spring-framework/reference/integration/scheduling.html#scheduling-annotation-support-async) — khai báo, proxy, chọn executor.