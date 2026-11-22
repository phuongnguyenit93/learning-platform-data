# Load test đầu cuối cho virtual thread và giới hạn tài nguyên

Virtual threads trong Java 21 giúp ứng dụng phục vụ nhiều tác vụ đồng thời khi phần lớn thời gian của mỗi tác vụ dành cho blocking I/O. Chúng không làm một phép tính CPU-bound chạy nhanh hơn và cũng không tạo thêm CPU, database connection, socket hoặc giới hạn rate của dịch vụ phụ thuộc. Vì vậy, load test phải đo toàn bộ đường đi của request và xác định tài nguyên nào trở thành nút thắt khi concurrency tăng.

Một bài test đáng tin cậy cần giữ workload, dữ liệu, runtime và môi trường giống nhau khi so sánh platform threads với virtual threads; đo throughput, latency percentile, lỗi và mức sử dụng tài nguyên; sau đó tăng tải đến khi tìm được điểm bão hòa. Đặc biệt, phải giới hạn số request đang hoạt động và số lần truy cập đồng thời vào tài nguyên khan hiếm. Việc tạo virtual thread rẻ hơn platform thread không có nghĩa có thể chấp nhận số lượng công việc chờ không giới hạn.

## 1. Xác định workload mà virtual threads phù hợp

Virtual threads phù hợp với mô hình thread-per-task khi nhiều tác vụ đồng thời thường xuyên chờ I/O như HTTP call, JDBC, socket hoặc file. Khi một virtual thread chờ ở thao tác blocking tương thích, JVM có thể unmount nó khỏi carrier để carrier thực thi virtual thread khác.

Virtual threads không phải lựa chọn tăng tốc mặc định cho mọi workload:

| Workload | Kỳ vọng khi dùng virtual threads |
| --- | --- |
| Nhiều request chờ HTTP/database/socket | Có thể tăng concurrency và throughput nếu giới hạn tài nguyên phụ thuộc được thiết kế đúng. |
| Tác vụ chờ I/O trong thời gian dài | Giảm nhu cầu duy trì một platform thread riêng cho mỗi tác vụ đang chờ. |
| Tính toán CPU-bound liên tục | Thường không nhanh hơn; số tác vụ thực thi đồng thời vẫn bị giới hạn bởi CPU và scheduler. |
| Công việc cần tài nguyên khan hiếm như DB connection | Chỉ tăng số task có thể chờ; cần pool, semaphore hoặc admission control để bảo vệ tài nguyên. |
| Công việc giữ dữ liệu lớn trong mỗi task | Có thể tăng áp lực heap vì mỗi virtual thread và context vẫn cần bộ nhớ. |

Không tạo một pool nhỏ các virtual threads để tái sử dụng như platform thread pool. Mô hình khuyến nghị là tạo một virtual thread cho mỗi task bằng `Executors.newVirtualThreadPerTaskExecutor()` hoặc virtual-thread-per-task executor tương ứng. Hãy giới hạn concurrency tại ranh giới công việc/tài nguyên, không dùng kích thước pool virtual thread để làm giới hạn giả tạo.

## 2. Thiết kế phép so sánh công bằng

Khi so sánh platform threads và virtual threads, thay đổi một biến tại một thời điểm. Giữ các điều kiện sau nhất quán:

- Cùng phiên bản JDK 21 và cùng bản cập nhật JDK.
- Cùng heap, GC, CPU quota, memory limit và cấu hình container.
- Cùng ứng dụng, logic nghiệp vụ, payload, dữ liệu và trạng thái cache.
- Cùng timeout, retry, connection pool, rate limit và giới hạn downstream.
- Cùng số request đồng thời hoặc cùng arrival rate, tùy mô hình load test.
- Cùng máy tạo tải, đường mạng, TLS và cấu hình HTTP client/server.
- Chạy nhiều lượt và ghi lại cả cấu hình lẫn kết quả, không chỉ giữ một con số tốt nhất.

Nếu client tạo tải và server chạy trên cùng máy, hai bên có thể tranh CPU, memory và network. Với phép đo đại diện production, nên tách load generator khỏi máy chạy service. Đồng thời kiểm tra chính load generator không trở thành nút thắt trước service.

Nên đo ít nhất hai workload riêng:

1. **I/O-bound:** mỗi request thực hiện một hoặc nhiều thao tác chờ có độ trễ thực tế, ví dụ gọi downstream HTTP hoặc database.
2. **CPU-bound:** mỗi request thực hiện lượng tính toán xác định. Bài test này cho thấy virtual threads không tạo thêm năng lực CPU và giúp tránh kết luận sai từ workload chỉ có I/O.

Một workload hỗn hợp gần production hơn có thể kết hợp CPU xử lý dữ liệu, gọi downstream, chờ connection pool và ghi response. Hãy bắt đầu từ từng phần riêng rồi mới tăng độ phức tạp.

## 3. Xây dựng chu kỳ load test đầu cuối

Một lượt test nên có các giai đoạn rõ ràng:

| Giai đoạn | Mục tiêu | Việc cần làm |
| --- | --- | --- |
| Baseline | Biết hệ thống hoạt động thế nào ở tải thấp. | Ghi latency, throughput, lỗi và tài nguyên khi có ít request. |
| Warm-up | Cho JIT, class loading, connection pool và cache ổn định. | Gửi tải tăng dần; không lấy đoạn này làm kết quả steady-state. |
| Ramp-up | Tăng concurrency hoặc arrival rate theo từng bước. | Tìm điểm latency bắt đầu tăng nhanh và tài nguyên tiến gần giới hạn. |
| Steady-state | Đo khi tải mục tiêu được duy trì. | Giữ đủ lâu để thấy GC, connection reuse, queueing và memory retention. |
| Stress / overload | Xác định hành vi khi vượt công suất. | Tăng tải có kiểm soát, theo dõi timeout, rejection, queue và phục hồi. |
| Ramp-down / recovery | Xác minh hệ thống trở lại trạng thái ổn định. | Giảm tải, chờ backlog tiêu hết và kiểm tra tài nguyên được giải phóng. |

Không chỉ chạy một lần với concurrency rất cao. Hãy tăng tải theo các nấc, ví dụ 50, 100, 200, 400 và 800 request đang hoạt động, rồi điều chỉnh theo khả năng của hệ thống. Con số cụ thể phải dựa trên giới hạn môi trường và mục tiêu kiểm thử.

Đặt trước tiêu chí dừng: error rate vượt ngưỡng, latency p99 vượt SLA, memory tiến gần giới hạn, số connection cạn hoặc CPU bị bão hòa kéo dài. Không tiếp tục tăng tải nếu hệ thống đã ở trạng thái không an toàn cho môi trường dùng chung.

## 4. Phân biệt closed-loop và open-loop load

Hai mô hình phát tải trả lời các câu hỏi khác nhau:

| Mô hình | Cách phát request | Điểm mạnh | Rủi ro khi diễn giải |
| --- | --- | --- | --- |
| Closed-loop / fixed concurrency | Mỗi worker gửi request tiếp theo sau khi request trước hoàn tất. | Dễ đặt số request đồng thời và mô phỏng số client đang hoạt động. | Khi server chậm, tốc độ phát tải tự giảm; có thể che khuất queueing và latency ở tải đến cố định. |
| Open-loop / fixed arrival rate | Bộ phát tải gửi request theo lịch độc lập với thời gian phản hồi. | Đo được hệ thống dưới một arrival rate mục tiêu và bộc lộ backlog khi service chậm. | Cần load generator đủ mạnh; phải kiểm soát số request pending để tránh chính generator hết tài nguyên. |

Hiện tượng *coordinated omission* xảy ra khi load generator chỉ phát request mới sau khi request trước hoàn tất. Nếu service bị treo hoặc latency tăng, generator cũng ngừng phát trong khoảng đó; histogram có thể bỏ sót các request lẽ ra đã được gửi trong thời gian service chậm. Kết quả latency khi đó lạc quan hơn trải nghiệm của hệ thống nhận một arrival rate cố định.

Để kiểm tra SLA theo traffic thực tế, nên bổ sung open-loop test với arrival rate đã xác định. Nếu dùng closed-loop, hãy ghi rõ đây là fixed-concurrency test và không diễn giải nó như một bài kiểm tra fixed RPS.

## 5. Đo throughput, latency và lỗi

Không chỉ nhìn thời gian trung bình. Tối thiểu cần ghi:

- **Offered rate:** số request được load generator dự định gửi mỗi giây.
- **Completed throughput:** số request hoàn tất mỗi giây, tách success và error.
- **Latency p50, p90, p95, p99 và max:** phân phối thời gian từ lúc bắt đầu gửi đến khi response hoàn tất.
- **Error rate:** HTTP status không thành công, timeout, connection failure, exception và request bị từ chối.
- **Queue/wait time:** thời gian chờ admission permit, connection pool, executor hoặc downstream.
- **Saturation:** mức sử dụng CPU, heap, GC, số connection, file descriptor, network và giới hạn downstream.

P50 mô tả request điển hình, nhưng p95/p99 cho thấy trải nghiệm ở đuôi phân phối. Một hệ thống có p50 thấp nhưng p99 rất cao có thể đang bị queueing, pool exhaustion, GC hoặc downstream chậm. Hãy dùng histogram có đủ độ phân giải và cùng cách tính percentile giữa các lượt test.

Throughput cần tính trên khoảng steady-state đã xác định. Không chia tổng request cho thời gian bao gồm cả thời gian khởi động và warm-up nếu mục tiêu là đo năng lực ổn định. Đồng thời đối chiếu offered rate với completed rate: nếu offered rate tăng nhưng completed throughput đứng yên và latency tăng, hệ thống đã tiến đến hoặc vượt điểm bão hòa.

## 6. Ví dụ burst probe bằng HttpClient và virtual threads

Đoạn code sau tạo một virtual thread cho mỗi request, dùng một `HttpClient` dùng chung và phát một đợt request đồng thời. Nó đo latency phía client, số response lỗi và các percentile cơ bản. Đây là một **burst/fixed-concurrency probe** hữu ích để kiểm tra nhanh endpoint; nó không thay thế open-loop load generator cho bài test SLA dài hạn.

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.LongAdder;

public class VirtualThreadBurstProbe {
    record Sample(long latencyNanos, int statusCode) {}

    public static void main(String[] args) throws Exception {
        URI target = URI.create(args[0]);
        int concurrency = Integer.parseInt(args[1]);
        if (concurrency <= 0) {
            throw new IllegalArgumentException("concurrency must be positive");
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        HttpRequest request = HttpRequest.newBuilder(target)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        var samples = new ConcurrentLinkedQueue<Sample>();
        var failures = new LongAdder();
        var ready = new CountDownLatch(concurrency);
        var start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        long elapsedNanos;
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < concurrency; i++) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    try {
                        start.await();
                        long startedAt = System.nanoTime();
                        HttpResponse<Void> response = client.send(
                                request,
                                HttpResponse.BodyHandlers.discarding()
                        );
                        long latency = System.nanoTime() - startedAt;
                        samples.add(new Sample(latency, response.statusCode()));

                        if (response.statusCode() / 100 != 2) {
                            failures.increment();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        failures.increment();
                    } catch (IOException e) {
                        failures.increment();
                    }
                }));
            }

            ready.await();
            long testStartedAt = System.nanoTime();
            start.countDown();

            for (Future<?> future : futures) {
                future.get();
            }
            elapsedNanos = System.nanoTime() - testStartedAt;
        }

        List<Long> latencies = samples.stream()
                .map(Sample::latencyNanos)
                .sorted()
                .toList();

        if (latencies.isEmpty()) {
            System.out.println("No response completed");
            System.out.println("Failures: " + failures.sum());
            return;
        }

        double seconds = elapsedNanos / 1_000_000_000.0;
        double throughput = samples.size() / seconds;

        System.out.printf("Completed: %d%n", samples.size());
        System.out.printf("Failures: %d%n", failures.sum());
        System.out.printf("Throughput: %.2f responses/s%n", throughput);
        System.out.printf("p50: %.2f ms%n", percentileMillis(latencies, 0.50));
        System.out.printf("p95: %.2f ms%n", percentileMillis(latencies, 0.95));
        System.out.printf("p99: %.2f ms%n", percentileMillis(latencies, 0.99));
    }

    private static double percentileMillis(List<Long> sorted, double percentile) {
        int index = Math.max(0, (int) Math.ceil(percentile * sorted.size()) - 1);
        return sorted.get(index) / 1_000_000.0;
    }
}
```

Chạy ví dụ với URL và số request đồng thời:

```shell
java VirtualThreadBurstProbe https://service.example/api 200
```

Load probe này có một request cho mỗi virtual thread, nên chỉ phù hợp với concurrency hữu hạn. Nó không có lịch arrival rate độc lập, không mô phỏng retry hoặc think time, và phần latency không bao gồm thời gian chờ trước barrier. `HttpClient` được dùng chung để tránh tạo client/connection pool mới cho từng request. Với phép so sánh platform thread, thay executor bằng fixed thread pool có cùng số worker và giữ nguyên mọi yếu tố còn lại.

Trong production load test, ưu tiên công cụ chuyên dụng có open workload model, histogram, pacing, phân phối dữ liệu và báo cáo coordinated omission. Chạy load generator trên máy riêng và kiểm tra CPU/network của chính generator.

## 7. Giới hạn số request đang hoạt động bằng admission control

`Executors.newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi task được submit. Executor này không phải bounded queue hoặc concurrency limiter. Nếu ingress gửi vô hạn task và mỗi task chờ một semaphore, số virtual thread đang đợi vẫn có thể tăng và giữ request data trong heap.

Đặt giới hạn ở ranh giới nhận công việc. Nếu đã đạt mức request đang xử lý, có thể từ chối sớm hoặc trả về trạng thái quá tải thay vì giữ một backlog không giới hạn:

```java
import java.util.concurrent.Semaphore;

public final class RequestAdmission {
    private final Semaphore inFlight = new Semaphore(500);

    public Response handle(Request request) throws Exception {
        if (!inFlight.tryAcquire()) {
            return Response.tooManyRequests();
        }

        try {
            return processRequest(request);
        } finally {
            inFlight.release();
        }
    }

    private Response processRequest(Request request) throws Exception {
        // Xử lý nghiệp vụ, có thể chờ I/O.
        return Response.ok();
    }
}
```

`Request`, `Response` ở đây là kiểu dữ liệu của ứng dụng; `Response.tooManyRequests()` biểu diễn phản hồi quá tải theo giao thức của service. Semaphore giới hạn số request đồng thời đi vào phần xử lý được bảo vệ; `tryAcquire()` từ chối ngay khi hết permit. Trong web framework, đặt admission gate càng sớm càng tốt tại ingress/handler boundary để tránh tạo backlog task lớn trước khi kiểm tra permit.

Semaphore giới hạn concurrency, không giới hạn số request mỗi giây. Nếu cần giới hạn arrival rate, dùng rate limiter (ví dụ token bucket) riêng. Nếu muốn chờ một khoảng ngắn trước khi từ chối, dùng `tryAcquire(timeout, unit)` và đặt timeout nhỏ, có đo queue wait; không chờ vô hạn.

## 8. Bảo vệ tài nguyên downstream riêng biệt

Giới hạn request tổng thể và giới hạn tài nguyên downstream là hai phạm vi khác nhau. Một service có thể xử lý 500 request đồng thời nhưng chỉ cho phép 40 request cùng lúc gọi một hệ thống thanh toán. Hãy dùng connection pool hoặc semaphore phù hợp với giới hạn thực của downstream.

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class PaymentGateway {
    private final Semaphore permits = new Semaphore(40);

    public PaymentResult authorize(Payment payment) throws InterruptedException {
        if (!permits.tryAcquire(100, TimeUnit.MILLISECONDS)) {
            throw new DownstreamBusyException("Payment capacity is exhausted");
        }

        try {
            return callRemoteGateway(payment);
        } finally {
            permits.release();
        }
    }

    private PaymentResult callRemoteGateway(Payment payment) {
        // Gọi API downstream với connect/read/request timeout đã cấu hình.
        return PaymentResult.approved();
    }
}
```

`Payment`, `PaymentResult` và `DownstreamBusyException` là các kiểu do ứng dụng định nghĩa để biểu diễn request, kết quả và lỗi quá tải. Điểm cần giữ là permit luôn được trả trong `finally`, kể cả khi lời gọi downstream ném exception.

Nếu task chạy trên virtual thread, thời gian chờ permit có thể nhường carrier trong thao tác blocking phù hợp. Tuy nhiên, rất nhiều virtual threads cùng chờ permit vẫn tiêu thụ heap và giữ request context. Kết hợp admission control ở tầng request với giới hạn downstream để không tích lũy waiter vô hạn.

Không đặt semaphore thứ hai quanh JDBC nếu connection pool đã là cơ chế giới hạn connection duy nhất và pool cung cấp queue/timeout phù hợp. Hai lớp giới hạn không đồng bộ có thể làm giảm throughput hoặc tạo hai hàng chờ khó chẩn đoán. Chỉ thêm semaphore khi nó bảo vệ một giới hạn nghiệp vụ khác với giới hạn connection của pool.

## 9. Theo dõi điểm bão hòa của tài nguyên

Khi tăng concurrency, theo dõi ít nhất các nhóm sau:

| Tài nguyên | Chỉ số cần quan sát | Dấu hiệu bão hòa |
| --- | --- | --- |
| CPU | Process CPU, host CPU, CPU throttling trong container. | CPU gần quota liên tục, throughput không tăng dù arrival rate tăng. |
| Heap/GC | Heap used/committed, allocation rate, GC frequency/duration, live set. | Heap tăng liên tục, GC dày hơn, pause/CPU GC tăng. |
| Virtual tasks | In-flight request/task, số task chờ permit, task duration. | Số task pending tăng nhưng completed throughput không tăng. |
| Platform/carrier threads | OS thread count, carrier utilization, thread dump/JFR. | Carrier bị block/pin hoặc số native thread tiến sát giới hạn. |
| Database | Active/idle connections, pending borrowers, acquisition latency. | Pool cạn, thời gian chờ connection tăng, DB CPU/lock contention cao. |
| HTTP/downstream | Connection pool, in-flight request, response latency, rate limit. | Connection chờ, timeout, 429/503 hoặc downstream latency tăng. |
| OS/network | File descriptors, socket count, ephemeral ports, bandwidth, retransmits. | Lỗi mở socket, cạn FD/port, network saturation. |
| Admission/queue | Permit đang dùng, rejected requests, queue depth và wait time. | Rejection tăng hoặc queue tăng liên tục. |

Số platform thread hoặc OS thread không cho biết số virtual thread. Virtual threads không có một native thread riêng trong suốt vòng đời; do đó cần metric ở tầng ứng dụng cho số request/task đang hoạt động, đang chờ và bị từ chối. `ThreadMXBean` và OS process metrics hữu ích để quan sát platform/native threads nhưng không thay thế metric in-flight virtual tasks.

## 10. Phát hiện pinning trong Java 21

Trong JDK 21, virtual thread có thể bị *pinned* vào carrier khi nó thực hiện blocking trong một vùng `synchronized` hoặc khi đang ở native/foreign call. Khi bị pin, JVM không thể unmount virtual thread khỏi carrier trong thời gian đó; nhiều thao tác blocking bị pin có thể làm cạn carrier và giảm khả năng mở rộng.

Không cần thay mọi `synchronized` bằng lock khác. Hãy tìm các vùng đồng bộ có thể giữ lâu hoặc thực hiện blocking I/O bên trong; giữ critical section ngắn và tránh gọi dịch vụ mạng/database trong monitor. Khi cần lock quanh một đoạn xử lý có blocking, đánh giá `ReentrantLock` hoặc thay đổi ranh giới đồng bộ sau khi đã hiểu tính đúng đắn của code.

Để chẩn đoán trên Java 21, có thể bật:

```shell
-Djdk.tracePinnedThreads=full
```

JVM có thể in stack trace khi virtual thread bị pin và cố thực hiện thao tác blocking. Dùng trong một khoảng chẩn đoán có kiểm soát vì output có thể nhiều.

Java Flight Recorder có event `jdk.VirtualThreadPinned`. Có thể ghi recording khi khởi động:

```shell
java -XX:StartFlightRecording=filename=virtual-thread-load.jfr,settings=profile,dumponexit=true -jar application.jar
```

Sau khi test kết thúc, lọc event:

```shell
jfr print --events jdk.VirtualThreadPinned virtual-thread-load.jfr
```

Event này hữu ích để tìm các khoảng pin đáng chú ý; mặc định JDK 21 dùng duration threshold 20 ms nên không nhất thiết ghi mọi lần pin rất ngắn. Nếu không có event trong recording, không nên kết luận không có pinning nếu event bị tắt hoặc ngưỡng/recording không phù hợp.

## 11. Dùng JFR, GC log và metrics để giải thích kết quả

Latency percentile cho biết hiện tượng, nhưng chưa giải thích nguyên nhân. Kết hợp nhiều nguồn dữ liệu trong cùng một khoảng thời gian:

```shell
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -XX:StartFlightRecording=filename=load-test.jfr,settings=profile,dumponexit=true -jar application.jar
```

Trong lúc load test, thu thập:

- JFR: CPU hot methods, allocation, lock contention, socket/file I/O, thread scheduling và virtual-thread pinning.
- GC log: allocation pressure, collection frequency, heap occupancy và thời gian GC.
- Application metrics: request rate, p50/p95/p99, errors, active requests, semaphore wait/rejection, pool wait time.
- Infrastructure metrics: CPU quota/throttling, memory, file descriptors, network và database saturation.

Đồng bộ timestamp hoặc dùng cùng một time window để đối chiếu. Ví dụ, nếu p99 tăng cùng lúc connection acquisition latency tăng nhưng CPU còn thấp, bottleneck có thể là database pool/downstream. Nếu p99 tăng cùng CPU throttling và CPU-bound spans kéo dài, tăng số virtual threads không giải quyết được nút thắt.

JFR profile có overhead; dùng cùng cấu hình recording khi so sánh hai mô hình hoặc chạy thêm lượt không recording để đánh giá overhead của công cụ. Không so sánh một lượt có profiler với một lượt không profiler rồi quy toàn bộ chênh lệch cho virtual threads.

## 12. Phân tích kết quả và tìm điểm bão hòa

Với mỗi mức tải, ghi một dòng kết quả gồm offered rate, completed throughput, p50/p95/p99, error rate, CPU, heap, GC, in-flight tasks, pool wait và downstream latency.

Một số mẫu diễn giải:

- **Throughput tăng, latency ổn định, lỗi thấp:** còn headroom; tiếp tục tăng tải theo nấc.
- **Throughput gần như đứng yên, p95/p99 tăng nhanh:** đã đến điểm bão hòa hoặc một queue đang tăng.
- **CPU thấp nhưng pool wait cao:** có thể bị giới hạn bởi database, downstream, semaphore hoặc network.
- **CPU cao và latency CPU-bound tăng:** năng lực tính toán đã bão hòa; cần tối ưu code/CPU hoặc tăng capacity, không chỉ đổi loại thread.
- **Số in-flight task tăng liên tục:** arrival rate lớn hơn khả năng hoàn tất; cần admission control/backpressure và xác định downstream chậm ở đâu.
- **Heap tăng theo số task chờ:** mỗi task giữ request/context/buffer; giảm backlog, giới hạn admission và kiểm tra object retention.
- **Carrier bị pin trong blocking operation:** điều tra `synchronized` hoặc native/foreign call trên JDK 21.

Điểm bão hòa không nhất thiết là thời điểm CPU đạt 100%. Một connection pool 40 kết nối có thể trở thành giới hạn trước khi CPU đáng kể; ngược lại, một tác vụ CPU-bound có thể bão hòa CPU khi concurrency còn thấp. Xác định tài nguyên đầu tiên chạm ngưỡng và liên kết nó với p99/error rate.

## 13. Các lỗi thường gặp khi load test virtual threads

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đo số virtual thread tạo được | Không phản ánh latency hoặc giới hạn downstream. | Đo end-to-end request, throughput, errors và tài nguyên. |
| So sánh workload hoặc cấu hình khác nhau | Không thể quy kết chênh lệch cho thread model. | Giữ môi trường, payload, pool và arrival model giống nhau. |
| Chỉ dùng closed-loop rồi kết luận fixed RPS | Khi service chậm, load generator tự giảm tốc. | Bổ sung open-loop test và ghi offered rate. |
| Chỉ báo cáo average latency | Che giấu tail latency. | Báo p50/p95/p99/max và histogram. |
| Tạo task không giới hạn rồi chờ semaphore | Số virtual thread chờ và heap có thể tăng không giới hạn. | Admission control sớm, bounded queue hoặc reject/backpressure. |
| Dùng virtual thread pool để giới hạn concurrency | Nhầm thread reuse với resource control. | Dùng thread-per-task; giới hạn bằng semaphore/pool/rate limiter. |
| Nghĩ virtual threads tăng năng lực CPU | CPU-bound workload vẫn bị giới hạn bởi CPU. | Đo riêng CPU-bound và I/O-bound. |
| Tạo HttpClient hoặc DB connection cho mỗi request | Đo chi phí khởi tạo và tạo áp lực tài nguyên không đại diện. | Tái sử dụng HttpClient; dùng DataSource/connection pool. |
| Chỉ theo dõi OS thread count | Không thấy số virtual task đang hoạt động/chờ. | Thêm application-level in-flight metrics và JFR. |
| Bỏ qua pinning trong JDK 21 | Carrier có thể bị giữ bởi blocking trong monitor/native call. | Dùng JFR `jdk.VirtualThreadPinned` và `jdk.tracePinnedThreads`. |
| Chạy load generator trên cùng host rồi quy kết CPU | Client và server tranh tài nguyên. | Tách máy tạo tải và kiểm tra generator capacity. |
| Dùng JMH để kết luận throughput HTTP end-to-end | Microbenchmark không mô phỏng hệ thống phân tán và queueing thực. | Dùng load test chuyên dụng; dùng JMH cho phép đo microbenchmark riêng. |

## 14. Checklist cho một lượt kiểm thử có thể lặp lại

1. Xác định mục tiêu: throughput, SLA latency, concurrency, capacity hay overload behavior.
2. Tách workload I/O-bound, CPU-bound và workload hỗn hợp.
3. Ghi rõ JDK build, JVM flags, heap/GC, CPU/memory quota và cấu hình connection pool.
4. Giữ nguyên payload, dữ liệu, TLS, timeout, retry và downstream trong các lượt so sánh.
5. Chọn closed-loop hoặc open-loop phù hợp; ghi rõ offered rate và concurrency.
6. Thực hiện warm-up, ramp-up, steady-state, stress và recovery.
7. Đo p50/p95/p99, completed throughput, error rate, queue wait và resource saturation.
8. Giới hạn in-flight requests và concurrency của tài nguyên khan hiếm; không để waiter tăng không giới hạn.
9. Thu JFR, GC log và infrastructure metrics trong cùng time window.
10. Kiểm tra pinning, đặc biệt blocking bên trong `synchronized` hoặc native/foreign call trên Java 21.
11. Lặp lại nhiều lần và báo cáo phân phối kết quả, không chọn một lượt tốt nhất.
12. Lưu kịch bản, dữ liệu, cấu hình và tiêu chí dừng để lần sau có thể tái lập.

## 15. Tài liệu tham khảo chính thức

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mục tiêu, scheduler, blocking, pinning, thread-per-task và khuyến nghị không pool virtual threads.
- [Java SE 21 API — `Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor()` và virtual-thread executor.
- [Java SE 21 API — `Semaphore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html): giới hạn số hoạt động đồng thời bằng permits.
- [Java SE 21 Guide — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): sử dụng và chẩn đoán virtual threads.
- [Java SE 21 `java` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): cấu hình JFR và JVM options.
- [Java SE 21 `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): đọc và lọc Flight Recording.
- [Java SE 21 `jcmd` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): diagnostic command cho tiến trình JVM đang chạy.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): công cụ microbenchmark; không thay thế load test end-to-end.
