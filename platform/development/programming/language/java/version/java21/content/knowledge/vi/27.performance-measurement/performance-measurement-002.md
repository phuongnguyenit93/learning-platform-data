# Phân loại workload CPU-bound, I/O-bound và hỗn hợp

Khi đo hiệu năng một ứng dụng Java, cần xác định tài nguyên nào đang giới hạn khả năng xử lý. Một workload **CPU-bound** bị giới hạn chủ yếu bởi năng lực tính toán của CPU; workload **I/O-bound** dành phần lớn thời gian chờ mạng, database, filesystem hoặc dịch vụ khác; workload **hỗn hợp** có cả giai đoạn tính toán và giai đoạn chờ I/O đáng kể.

Phân loại đúng giúp chọn cách tối ưu và mô hình concurrency phù hợp. Tăng số thread thường không làm workload CPU-bound chạy nhanh hơn khi CPU đã bão hòa; ngược lại, với I/O-bound, nhiều tác vụ có thể cùng tồn tại trong lúc chờ. Virtual threads trong Java 21 đặc biệt hữu ích cho mô hình blocking thread-per-task, nhưng không làm CPU nhanh hơn hoặc loại bỏ giới hạn của dịch vụ phụ thuộc.

## 1. CPU-bound là gì?

Workload CPU-bound tiêu thụ phần lớn thời gian để thực hiện lệnh tính toán. CPU là tài nguyên giới hạn throughput; khi các lõi CPU được sử dụng gần hết công suất, thêm tác vụ đồng thời thường chỉ làm tăng hàng đợi runnable và context switching.

Ví dụ thường gặp:

- Mã hóa, giải mã, hash hoặc nén dữ liệu trên khối lượng lớn.
- Tính toán số học, mô phỏng, xử lý ảnh hoặc phân tích dữ liệu trong bộ nhớ.
- Parse, validate hoặc chuyển đổi cấu trúc dữ liệu lớn khi chi phí CPU chiếm phần lớn thời gian.
- Tính toán nghiệp vụ phức tạp không phải chờ dịch vụ bên ngoài.

Dấu hiệu thường thấy là CPU process hoặc một số core ở mức sử dụng cao, nhiều thread runnable, thời gian CPU chiếm tỷ lệ lớn trong thời gian xử lý và throughput không tăng khi tăng concurrency.

## 2. I/O-bound là gì?

Workload I/O-bound dành phần lớn thời gian chờ dữ liệu hoặc phản hồi từ một tài nguyên bên ngoài. Trong thời gian chờ, thread không thực hiện nhiều tính toán hữu ích.

Ví dụ thường gặp:

- Gọi HTTP đến dịch vụ khác và chờ response.
- Truy vấn database, chờ connection hoặc chờ kết quả query.
- Đọc/ghi file, object storage hoặc filesystem mạng.
- Nhận dữ liệu từ socket, message broker hoặc queue.

Dấu hiệu thường thấy là CPU còn headroom trong khi request latency cao; thời gian chờ network/database/file lớn; nhiều tác vụ đang chờ; hoặc throughput bị giới hạn bởi connection pool, quota, server từ xa hay băng thông.

Một thread ở trạng thái `WAITING` hoặc `TIMED_WAITING` không tự động chứng minh workload I/O-bound. Thread có thể đang chờ lock, timer, queue hoặc một điều kiện đồng bộ khác. Cần xác định chính xác nó đang chờ tài nguyên nào.

## 3. Workload hỗn hợp

Workload hỗn hợp có nhiều giai đoạn với đặc tính khác nhau. Ví dụ một request có thể đọc dữ liệu từ database, gọi HTTP, sau đó giải mã, kiểm tra và tổng hợp kết quả trong CPU.

```text
Nhận request
    |
    v
Đọc database / gọi HTTP  -----> chờ I/O
    |
    v
Parse và validate            -----> dùng CPU
    |
    v
Ghi kết quả / publish event  -----> chờ I/O
    |
    v
Trả response
```

Không nên gắn nhãn toàn bộ hệ thống là CPU-bound hoặc I/O-bound chỉ dựa trên một đoạn code. Hãy phân tích theo endpoint, loại tác vụ hoặc từng stage. Bottleneck có thể chuyển từ database sang CPU khi tối ưu một giai đoạn trước đó.

## 4. So sánh ba loại workload

| Đặc điểm | CPU-bound | I/O-bound | Hỗn hợp |
|---|---|---|---|
| Tài nguyên thường giới hạn | CPU core và năng lực tính toán | Network, database, disk, connection hoặc dịch vụ ngoài | Thay đổi theo stage |
| Thời gian chính | Thực thi lệnh CPU | Chờ I/O hoặc tài nguyên | Cả tính toán và chờ |
| CPU utilization | Thường cao khi tải đủ lớn | Có thể thấp dù latency cao | Dao động theo giai đoạn |
| Tăng concurrency | Thường không giúp khi CPU đã bão hòa | Có thể tăng throughput đến giới hạn phụ thuộc | Có thể giúp stage chờ, nhưng cần giới hạn stage CPU |
| Hướng tối ưu | Thuật toán, dữ liệu, allocation, mức song song | Giảm round trip, connection reuse, batching, concurrency có kiểm soát | Tách stage và đo riêng từng bottleneck |
| Mô hình Java thường cân nhắc | Pool có giới hạn theo CPU | Virtual thread cho blocking I/O hoặc API async phù hợp | Kết hợp executor theo từng loại công việc |

Đây là mô hình phân loại theo bottleneck chính. Một workload có thể chuyển loại khi tải, dữ liệu hoặc môi trường triển khai thay đổi.

## 5. Đo lường trước khi phân loại

Không phân loại workload chỉ bằng cảm giác hoặc bằng một lần chạy. Cần đo dưới tải đại diện và thu thập ít nhất các nhóm số liệu sau:

| Nhóm số liệu | Cần quan sát | Câu hỏi trả lời |
|---|---|---|
| Throughput | Request/operation hoàn tất mỗi giây | Hệ thống xử lý được bao nhiêu công việc? |
| Latency | p50, p95, p99 và thời gian tối đa có ý nghĩa | Người dùng phải chờ bao lâu? |
| CPU | Process CPU, từng core, runnable queue, CPU time | CPU có phải tài nguyên bão hòa không? |
| I/O | Thời gian socket, database, filesystem và dịch vụ ngoài | Thời gian đang mất ở đâu? |
| Concurrency và queue | In-flight requests, queue depth, connection pool usage | Công việc đang chờ ở tầng nào? |
| Bộ nhớ và GC | Allocation rate, live set, GC pauses, allocation stalls | GC hoặc áp lực bộ nhớ có làm lệch kết quả không? |
| Lỗi và timeout | Error rate, retry, cancellation | Tăng tải có làm hệ thống thất bại trước khi tăng throughput không? |

Đo trong trạng thái ổn định, dùng dữ liệu gần production và ghi nhận cấu hình JVM, CPU quota, heap, JDK, số kết nối và giới hạn dịch vụ phụ thuộc. Nếu load generator dùng chung CPU với ứng dụng, nó có thể trở thành bottleneck và làm sai kết quả.

## 6. Đọc CPU utilization đúng cách

CPU utilization cao là một dấu hiệu của CPU-bound, nhưng cần kết hợp với throughput và latency. Nếu CPU gần bão hòa, throughput không tăng khi tăng concurrency và runnable queue tăng, CPU có khả năng là bottleneck.

Ngược lại, CPU utilization thấp không đủ để kết luận ứng dụng I/O-bound. Có thể ứng dụng đang bị giới hạn bởi lock contention, connection pool quá nhỏ, rate limit, một thread đơn lẻ hoặc một dịch vụ phụ thuộc. Một luồng đơn có thể bão hòa một core trong khi tổng CPU của máy vẫn thấp.

Với máy nhiều core, hãy xem cả mức sử dụng theo từng core và CPU quota của container. JVM có thể nhìn thấy số processor khác với số core vật lý của host; `Runtime.getRuntime().availableProcessors()` là điểm bắt đầu để quan sát số processor mà JVM nhận diện, không phải cam kết rằng ứng dụng luôn được cấp đủ năng lực CPU đó.

## 7. CPU-bound: chọn mức song song theo năng lực CPU

Với tác vụ CPU-bound, số tác vụ thực thi đồng thời hữu ích thường gần với số CPU core mà tiến trình có thể sử dụng. Một fixed thread pool có kích thước dựa trên `availableProcessors()` là điểm bắt đầu để benchmark; giá trị tối ưu còn phụ thuộc thuật toán, thời gian GC, tác vụ nền và CPU quota.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Callable;
import java.util.concurrent.Future;
import java.util.ArrayList;
import java.util.List;

static void runCpuTasks() throws Exception {
    int parallelism = Runtime.getRuntime().availableProcessors();

    try (ExecutorService executor =
            Executors.newFixedThreadPool(parallelism)) {
        List<Future<Long>> results = new ArrayList<>();
        for (int i = 0; i < 100; i++) {
            final int input = i;
            Callable<Long> task = () -> calculate(input);
            results.add(executor.submit(task));
        }
        for (Future<Long> result : results) {
            System.out.println(result.get());
        }
    }
}

static long calculate(int input) {
    long result = 0;
    for (int i = 1; i <= 1_000_000; i++) {
        result += (long) input * i;
    }
    return result;
}
```

Ví dụ minh họa pool giới hạn số thread thực thi CPU task. Trong ứng dụng thật, cần thu thập và xử lý `Future` hoặc lỗi tác vụ thay vì bỏ qua kết quả. Nếu queue có thể tăng không giới hạn, hãy thêm giới hạn admission hoặc queue bounded để kiểm soát bộ nhớ và latency.

Không tăng pool size vô hạn để cố cải thiện throughput. Khi CPU đã bão hòa, nhiều thread hơn thường làm tăng context switching, queueing và latency mà không tăng công việc hoàn tất.

## 8. I/O-bound: virtual threads trong Java 21

Virtual threads cho phép viết code blocking theo phong cách tuần tự mà vẫn phục vụ nhiều tác vụ đồng thời. Khi virtual thread chờ một thao tác blocking được JVM hỗ trợ, nó thường có thể unmount khỏi carrier; carrier được dùng cho virtual thread khác.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

static void loadManyAccounts() throws Exception {
    try (ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor()) {
        Future<String> first = executor.submit(() -> loadAccount("A-101"));
        Future<String> second = executor.submit(() -> loadAccount("B-202"));

        System.out.println(first.get());
        System.out.println(second.get());
    }
}

static String loadAccount(String id) {
    // Thay bằng lời gọi HTTP hoặc database blocking.
    return "account-" + id;
}
```

Virtual threads phù hợp khi có nhiều tác vụ độc lập chủ yếu chờ I/O. Chúng không làm request đến database hoặc HTTP server hoàn tất nhanh hơn; lợi ích là giảm chi phí giữ một platform thread trong lúc chờ và giúp mô hình thread-per-task mở rộng hơn.

Không pool virtual thread để tái sử dụng. Dùng một virtual thread cho mỗi task; giới hạn số kết nối database, số request tới dịch vụ ngoài hoặc quota bằng connection pool, semaphore hay rate limiter.

## 9. Khi nào chọn API bất đồng bộ?

Virtual threads không thay thế mọi API asynchronous. API async phù hợp khi thư viện hoặc framework đã cung cấp pipeline bất đồng bộ, khi cần compose nhiều tác vụ qua `CompletableFuture`, hoặc khi giữ một thread cho mỗi thao tác không phù hợp với kiến trúc hiện tại.

Với blocking I/O và code tuần tự dễ đọc, virtual thread thường là lựa chọn đơn giản. Với non-blocking I/O, stream hoặc pipeline event-driven, tiếp tục dùng API async phù hợp. So sánh bằng benchmark end-to-end thay vì giả định một mô hình luôn nhanh hơn.

Khi dùng virtual thread, vẫn cần xem xét các thao tác có thể pin carrier trên JDK 21, chẳng hạn blocking trong vùng `synchronized` hoặc native call. Hành vi monitor pinning đã được cải thiện từ JDK 24 qua JEP 491; hãy đánh giá theo đúng runtime đang chạy.

## 10. Workload hỗn hợp: tách stage theo loại tài nguyên

Với pipeline có cả I/O và CPU, có thể dùng virtual thread cho phần chờ I/O và một executor có giới hạn cho phần tính toán nặng. Cách tách này giúp kiểm soát số CPU task đang chạy mà không phải giới hạn số virtual thread chờ dịch vụ.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

static void processRequests() throws Exception {
    int cpuParallelism = Runtime.getRuntime().availableProcessors();

    try (ExecutorService ioExecutor =
                 Executors.newVirtualThreadPerTaskExecutor();
         ExecutorService cpuExecutor =
                 Executors.newFixedThreadPool(cpuParallelism)) {

        Future<Report> report = ioExecutor.submit(() -> {
            Input input = fetchFromRemoteService();
            Callable<Report> cpuTask = () -> analyze(input);
            Future<Report> calculation = cpuExecutor.submit(cpuTask);
            return calculation.get();
        });

        System.out.println(report.get());
    }
}
```

Ví dụ cho thấy cách phân chia stage. Trong hệ thống chịu tải cao, cần thêm backpressure hoặc giới hạn số công việc được đưa vào CPU stage; fixed thread pool mặc định có queue không giới hạn. Có thể dùng semaphore để giới hạn số tác vụ CPU đang chạy và đang chờ, hoặc dùng executor với bounded queue cùng chính sách từ chối rõ ràng.

Không nên để hàng chục nghìn virtual thread gửi vô hạn CPU task vào một queue. Khi CPU stage chậm hơn I/O stage, queue sẽ tăng, làm tăng bộ nhớ và latency. Backpressure giúp tốc độ nhận việc phù hợp với năng lực xử lý.

## 11. Định luật Little và mối liên hệ giữa concurrency với latency

Trong hệ thống ổn định, định luật Little mô tả quan hệ giữa số công việc trung bình đang ở trong hệ thống (L), throughput trung bình (λ) và thời gian trung bình trong hệ thống (W):

\[L = \lambda \times W\]

Ví dụ, nếu hệ thống hoàn tất trung bình 200 request mỗi giây và mỗi request ở trong hệ thống trung bình 0,1 giây, số request trung bình đang được xử lý hoặc chờ là khoảng 20.

Quan hệ này giúp hiểu vì sao tăng concurrency có thể làm tăng throughput khi tài nguyên còn dư, nhưng cũng làm tăng số request đang chờ khi bottleneck đã bão hòa. Tăng concurrency mà không tăng năng lực xử lý có thể làm latency và queue depth tăng mạnh.

## 12. Dùng JMH và load test đúng mục đích

JMH phù hợp để đo một đoạn code hoặc thuật toán trong điều kiện JVM được kiểm soát, chẳng hạn chi phí parse, hash, transform hoặc thao tác trên collection. Nó giúp xử lý warmup, fork và tối ưu hóa của JIT compiler tốt hơn một vòng lặp tự viết đơn giản.

Load test hoặc benchmark ở cấp ứng dụng phù hợp để đo request end-to-end có network, database, queue, serialization và nhiều thành phần phụ thuộc. Không dùng microbenchmark JMH đơn lẻ để kết luận thời gian phản hồi của một API phân tán.

Khi đo:

- Warm up ứng dụng để JIT compiler và runtime đạt trạng thái ổn định.
- Dùng đủ thời gian và số lần lặp để giảm nhiễu.
- Giữ cố định dữ liệu, cấu hình, concurrency và môi trường khi so sánh hai phương án.
- Đo throughput cùng latency percentiles và error rate.
- Tách thời gian khởi động khỏi thời gian steady-state nếu mục tiêu là hiệu năng vận hành.
- Chạy load generator đủ năng lực và theo dõi cả tài nguyên của máy tạo tải.

## 13. Công cụ quan sát trong Java 21

Có thể kết hợp nhiều nguồn dữ liệu để nhận diện bottleneck:

| Công cụ | Hữu ích cho | Lưu ý |
|---|---|---|
| Java Flight Recorder (JFR) | CPU execution samples, socket/file I/O, thread park, monitor contention, allocation và GC | Cấu hình event và thời gian recording phù hợp với câu hỏi cần trả lời |
| `jcmd` và thread dump | Stack của thread tại một thời điểm, trạng thái chờ và lock | Thread dump là snapshot; dùng JSON dump khi cần quan sát số lượng lớn virtual thread |
| `ThreadMXBean` | CPU time và thông tin quản lý platform thread | Trong Java 21, không dùng bean này để đếm hoặc lấy CPU time từng virtual thread |
| OS/container metrics | CPU theo core, CPU quota/throttling, disk/network throughput | Đối chiếu với giới hạn thực tế mà process được cấp |
| Application metrics/tracing | Latency từng stage, queue, in-flight request, lỗi và timeout | Gắn nhãn theo endpoint/loại công việc, tránh cardinality quá cao |

JFR event như `jdk.ExecutionSample`, `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite`, `jdk.ThreadPark` và `jdk.JavaMonitorEnter` có thể giúp phân biệt thời gian thực thi với thời gian chờ. Kiểm tra event có được bật trong recording profile đang dùng hay không.

## 14. Một quy trình phân loại thực tế

1. Chọn một operation hoặc endpoint cụ thể và xác định throughput, latency p50/p95/p99, error rate cần đạt.
2. Chạy workload với dữ liệu và concurrency gần production; ghi nhận CPU, I/O, queue, pool, heap và GC.
3. Nếu CPU bão hòa và execution samples tập trung ở code tính toán, kiểm tra khả năng CPU-bound.
4. Nếu CPU còn dư nhưng thời gian chờ socket/database/file hoặc queue lớn, xác định I/O-bound hay giới hạn ở dependency.
5. Nếu mỗi request có cả chờ I/O và tính toán đáng kể, đo thời gian từng stage và phân loại workload hỗn hợp.
6. Thay đổi một yếu tố mỗi lần: thuật toán, pool size, concurrency, batching, cache hoặc giới hạn kết nối.
7. Chạy lại cùng workload và so sánh throughput, latency percentiles, error rate cùng mức tiêu thụ tài nguyên.
8. Phân loại lại sau mỗi tối ưu vì bottleneck có thể chuyển sang stage khác.

## 15. Các lỗi thường gặp khi đánh giá workload

- **Tăng thread count để chữa CPU saturation:** thường làm queue và context switching tăng mà không cải thiện throughput.
- **Dùng virtual thread như bộ giới hạn concurrency:** virtual thread nhẹ nhưng không giới hạn database connection, API quota hoặc memory.
- **Kết luận I/O-bound chỉ vì thread đang WAITING:** phải xác định nguyên nhân chờ là network, lock, queue hay timer.
- **Chỉ nhìn CPU trung bình của cả máy:** một core hoặc CPU quota của container có thể đã bão hòa.
- **Chỉ đo throughput:** latency p99 và error rate có thể xấu đi khi tăng tải.
- **Dùng JMH để đại diện cho hệ thống phân tán:** microbenchmark không mô phỏng đầy đủ network, database và contention production.
- **Không đo lại sau tối ưu:** khi một bottleneck được gỡ, tài nguyên khác có thể trở thành giới hạn mới.

## 16. Biên dịch và chạy với Java 21

Các ví dụ sử dụng `ExecutorService`, virtual threads, `Runtime.availableProcessors()` và API đo lường có trong Java 21. Có thể biên dịch bằng release 21 mà không bật Preview:

```bash
javac --release 21 -d out src/WorkloadClassificationDemo.java
java -cp out WorkloadClassificationDemo
```

Khi đo trên môi trường triển khai, ghi lại cả phiên bản runtime thực tế, CPU quota, bộ nhớ và cấu hình GC. `--release 21` chỉ đặt mức API/ngôn ngữ lúc biên dịch, không cố định runtime hay tài nguyên mà ứng dụng nhận được.

## 17. Tài liệu tham khảo

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — Runtime.availableProcessors()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html#availableProcessors())
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
- [Oracle — Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.pdf)
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
