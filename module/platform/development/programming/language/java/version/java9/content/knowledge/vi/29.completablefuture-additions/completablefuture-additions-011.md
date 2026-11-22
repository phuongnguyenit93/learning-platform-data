# Tránh chặn tác vụ trong executor không phù hợp

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao tác vụ blocking có thể làm cạn worker của một executor.
- Phân biệt các continuation đồng bộ và bất đồng bộ của \`CompletableFuture\`.
- Chọn executor phù hợp cho CPU-bound work và blocking I/O.
- Tránh thread starvation và deadlock do chờ một future khác trong cùng pool.
- Dùng \`thenCompose\`, \`thenCombine\` và \`allOf\` để ghép pipeline mà không block worker.
- Hiểu giới hạn của \`ForkJoinPool.ManagedBlocker\`, timeout và cancellation.
- Đánh giá khi nào virtual thread là lựa chọn phù hợp trên JDK hiện đại.

## 1. Vì sao phải chọn executor phù hợp?

\`CompletableFuture\` cho phép mô tả các bước bất đồng bộ mà không cần tự viết toàn bộ cơ chế điều phối thread. Tuy nhiên, một future chỉ mô tả kết quả và quan hệ phụ thuộc; executor quyết định task được thực thi ở đâu.

Hai nhóm công việc có đặc tính rất khác nhau:

- **CPU-bound:** tính toán, biến đổi dữ liệu, mã hóa hoặc xử lý ảnh. Worker liên tục sử dụng CPU.
- **Blocking I/O:** chờ network, database, file, socket, khóa hoặc API đồng bộ. Worker có thể không làm việc hữu ích trong lúc chờ.

Nếu đưa nhiều tác vụ blocking vào executor được thiết kế cho công việc ngắn và CPU-bound, các worker có thể bị giữ lại trong thời gian dài. Những task khác đã sẵn sàng nhưng không có worker để chạy. Đây là thread starvation.

Một executor không phù hợp còn có thể làm độ trễ tăng, queue phình to, throughput giảm và toàn bộ pipeline bị đình trệ dù CPU chưa được sử dụng hết.

## 2. CompletableFuture thực thi continuation ở đâu?

Cần phân biệt hai nhóm method.

| Nhóm | Ví dụ | Nơi thực thi |
|---|---|---|
| Không có hậu tố Async | \`thenApply\`, \`thenAccept\`, \`thenCompose\`, \`whenComplete\` | Có thể chạy trên thread hoàn thành stage trước hoặc thread gọi phương thức completion |
| Có hậu tố Async, không truyền executor | \`thenApplyAsync\`, \`thenComposeAsync\`, \`supplyAsync\` | Dùng default asynchronous facility, thông thường là \`ForkJoinPool.commonPool()\` |
| Có hậu tố Async và truyền executor | \`thenApplyAsync(fn, executor)\`, \`supplyAsync(supplier, executor)\` | Dùng executor được truyền vào |

Có ba hệ quả thực tế:

1. Một continuation không có Async không có nghĩa là nó luôn chạy trên một thread riêng. Nếu stage trước đã hoàn thành, continuation có thể chạy ngay trên thread gọi phương thức.
2. Một continuation không có Async có thể làm chậm thread đang hoàn thành stage trước. Nếu callback thực hiện blocking I/O hoặc xử lý rất lâu, nó có thể giữ worker của executor nguồn.
3. Async không có executor vẫn dùng default executor. Chỉ thêm hậu tố Async không tự động tách công việc blocking khỏi common pool.

Theo hợp đồng của \`CompletableFuture\`, các async method không chỉ định executor dùng common pool, trừ khi common pool không hỗ trợ mức parallelism tối thiểu là hai; khi đó JDK có thể tạo một thread mới cho mỗi task. Vì vậy, hãy chỉ rõ executor khi vị trí thực thi là một phần quan trọng của thiết kế.

## 3. Vì sao blocking trong common pool dễ gây starvation?

\`ForkJoinPool.commonPool()\` là pool dùng chung trong JVM. Nó thường phục vụ các tác vụ ngắn, có thể chia nhỏ và tận dụng work-stealing. Nhiều thành phần có thể cùng sử dụng pool này, gồm các async stage mặc định của \`CompletableFuture\` và một số API xử lý song song.

Giả sử common pool có một số worker hữu hạn. Nếu các worker đều chạy tác vụ kiểu:

~~~java
CompletableFuture.supplyAsync(() -> blockingDatabaseCall());
~~~

và mỗi tác vụ chờ database trong thời gian dài, worker bị giữ trong trạng thái chờ. Những task CPU-bound hoặc continuation khác có thể phải đợi.

Đặc biệt nguy hiểm là khi một worker chặn để đợi một task khác đang nằm trong queue của chính pool đó. Nếu tất cả worker đều đang chờ theo cách này, task cần thiết để giải phóng chúng không có cơ hội chạy. Đây là dạng thread-starvation deadlock.

Không phải mọi thao tác chờ trong common pool đều lập tức gây deadlock. Mức độ ảnh hưởng phụ thuộc số worker, thời gian chờ, số task, cơ chế compensation và tải của toàn JVM. Nhưng không nên dựa vào may mắn hoặc số worker hiện tại để thiết kế một pipeline có blocking không giới hạn.

## 4. Chọn executor theo loại công việc

Một cách chia phổ biến:

| Loại công việc | Executor phù hợp | Lưu ý |
|---|---|---|
| Tính toán ngắn, CPU-bound | \`ForkJoinPool.commonPool()\` hoặc pool CPU riêng | Tránh block; cân nhắc số worker theo CPU và workload |
| Blocking I/O dùng platform thread | Executor I/O riêng | Giới hạn số worker, queue và kết nối downstream |
| Blocking I/O trên JDK 21+ | Virtual-thread-per-task executor | Dễ scale nhiều tác vụ chờ; vẫn phải giới hạn tài nguyên bên ngoài |
| Tác vụ có thứ tự hoặc giới hạn concurrency đặc biệt | Executor được cấu hình theo yêu cầu | Xác định rõ queue, rejection và lifecycle |

Không có một pool duy nhất phù hợp cho mọi loại công việc. Tách executor giúp một nhóm tác vụ không chiếm hết worker của nhóm khác.

### 4.1. CPU-bound work

Tác vụ CPU-bound nên chạy trên pool có số worker phù hợp với số lõi và tải thực tế. Common pool thường là lựa chọn hợp lý cho các async stage ngắn, không blocking.

Nếu ứng dụng có pipeline CPU riêng, có thể dùng executor riêng để kiểm soát mức cạnh tranh với các tác vụ song song khác.

### 4.2. Blocking I/O

Với API đồng bộ có thể block, đưa lời gọi vào executor dành riêng cho I/O:

~~~java
CompletableFuture.supplyAsync(
        () -> blockingRemoteCall(),
        ioExecutor);
~~~

Khi worker I/O chờ network hoặc database, worker CPU vẫn có thể tiếp tục chạy tác vụ của nó.

Executor I/O cần giới hạn concurrency theo khả năng thực tế của dịch vụ downstream. Ví dụ, nếu connection pool chỉ cho phép 20 kết nối, tạo hàng trăm worker chỉ làm tăng số thread chờ connection.

Trong production, tránh mặc định dùng \`Executors.newFixedThreadPool\` mà không xem xét queue: factory này dùng queue không giới hạn. Một tải đầu vào tăng đột biến có thể tạo backlog lớn và giữ nhiều request trong bộ nhớ. Dùng \`ThreadPoolExecutor\` với queue có giới hạn, chính sách từ chối, timeout và admission control phù hợp.

### 4.3. Virtual threads trên JDK 21+

Virtual thread là lựa chọn hiện hành cho nhiều workload có nhiều thao tác blocking I/O. Có thể dùng:

~~~java
ExecutorService ioExecutor =
        Executors.newVirtualThreadPerTaskExecutor();

CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> blockingRemoteCall(),
                ioExecutor);
~~~

Executor này tạo virtual thread cho mỗi task; không nên xem nó như một pool platform thread cần tái sử dụng. Virtual thread giúp chi phí chờ thấp hơn trong nhiều trường hợp, nhưng không làm CPU-bound task chạy nhanh hơn.

Virtual thread cũng không tạo thêm connection database, quota API hoặc băng thông. Hãy giới hạn concurrency ở tài nguyên thực tế bằng connection pool, semaphore hoặc rate limiter. Không dùng virtual thread để bỏ qua giới hạn tải của dịch vụ downstream.

## 5. Không chờ future con bằng get hoặc join bên trong cùng pool

Một lỗi thường gặp là submit task con vào cùng executor rồi block worker hiện tại để đợi task con:

~~~java
CompletableFuture<String> outer =
        CompletableFuture.supplyAsync(() -> {
            CompletableFuture<String> inner =
                    CompletableFuture.supplyAsync(
                            () -> loadChild(),
                            sameExecutor);

            return inner.join(); // Không nên block worker ở đây
        }, sameExecutor);
~~~

Nếu pool có ít worker và tất cả worker đều chạy outer task theo mẫu này, mỗi worker có thể chờ một inner task đang xếp hàng. Không còn worker để chạy inner task. Kết quả là starvation hoặc deadlock.

Hãy biểu diễn quan hệ phụ thuộc bằng composition:

~~~java
CompletableFuture<String> outer =
        CompletableFuture.supplyAsync(
                () -> loadParent(),
                ioExecutor)
        .thenCompose(parent ->
                CompletableFuture.supplyAsync(
                        () -> loadChild(parent),
                        ioExecutor));
~~~

\`thenCompose\` nối future được trả về từ bước tiếp theo vào cùng pipeline. Callback chỉ submit công việc con rồi trả về; worker không phải chờ kết quả bằng \`get()\` hoặc \`join()\`.

Các công cụ composition hữu ích khác:

- \`thenCombine\`: ghép hai future độc lập khi cả hai hoàn thành.
- \`allOf\`: tạo một future hoàn thành khi tất cả future đầu vào hoàn thành.
- \`thenApply\`: biến đổi kết quả đồng bộ, phù hợp cho callback ngắn và không blocking.
- \`thenApplyAsync(fn, executor)\`: chuyển bước biến đổi sang executor được chọn.

Có thể gọi \`join()\` hoặc \`get()\` tại ranh giới đồng bộ của ứng dụng, chẳng hạn trong \`main\`, test hoặc adapter đồng bộ. Tránh gọi chúng bên trong worker để chờ một tác vụ cần chính executor đó.

## 6. Giữ continuation không Async ngắn và không blocking

Ví dụ:

~~~java
future.thenApply(value -> {
    return blockingDatabaseCall(value);
});
~~~

Callback không có Async có thể chạy trên thread hoàn thành future trước. Nếu callback chờ database, nó có thể giữ thread hoàn thành, làm chậm các stage khác hoặc kéo dài thao tác completion của nguồn.

Nếu bước tiếp theo là I/O, chỉ rõ executor:

~~~java
future.thenApplyAsync(
        value -> blockingDatabaseCall(value),
        ioExecutor);
~~~

Nếu callback chỉ biến đổi một giá trị nhỏ, không blocking, continuation không Async có thể giảm chi phí scheduling:

~~~java
future.thenApply(String::trim);
~~~

Không cần biến mọi continuation thành Async. Mục tiêu là chọn nơi thực thi phù hợp với thời gian chạy và đặc tính blocking của callback.

## 7. ManagedBlocker: trường hợp đặc biệt của ForkJoinPool

Đôi khi thuật toán bắt buộc phải block bên trong worker của \`ForkJoinPool\`. API \`ForkJoinPool.ManagedBlocker\` và \`ForkJoinPool.managedBlock(...)\` cho phép thông báo cho pool rằng worker sắp hoặc đang block.

Pool có thể cố gắng bù worker để duy trì mức parallelism mục tiêu. Đây là hỗ trợ dành cho tình huống blocking có khai báo; nó không biến mọi blocking I/O thành miễn phí và không bảo đảm compensation không giới hạn.

Chỉ cân nhắc ManagedBlocker khi:

- Tác vụ thật sự phải chờ trong một ForkJoinPool worker.
- Có thể mô tả chính xác điều kiện đã sẵn sàng qua \`isReleasable()\`.
- Phần chờ được thực hiện trong \`block()\` và xử lý interrupt đúng.
- Đã đo tải và hiểu tác động của việc thêm worker.

Nếu có thể chọn executor riêng cho blocking I/O, thường nên làm điều đó trước. ManagedBlocker không phải cách sửa mặc định cho một pipeline đã đưa quá nhiều I/O vào common pool.

## 8. Timeout và cancellation không thay thế quản lý executor

Java 9 bổ sung các method hữu ích trên \`CompletableFuture\`:

~~~java
future.orTimeout(2, TimeUnit.SECONDS);
~~~

\`orTimeout\` hoàn thành future một cách exceptional bằng \`TimeoutException\` nếu quá thời hạn.

~~~java
future.completeOnTimeout(
        fallbackValue, 2, TimeUnit.SECONDS);
~~~

\`completeOnTimeout\` hoàn thành future bằng giá trị dự phòng nếu hết thời hạn.

Timeout giúp giới hạn thời gian chờ kết quả ở tầng future, nhưng không tự bảo đảm thao tác I/O bên dưới đã dừng. Ví dụ, một JDBC call hoặc thư viện đồng bộ có thể vẫn chạy sau khi future đã timeout.

Hãy cấu hình timeout ngay trong HTTP client, JDBC driver, socket hoặc API I/O tương ứng. Nếu cần hủy công việc, dùng cancellation handle của API gốc và xử lý interrupt theo hợp đồng của nó.

Với \`CompletableFuture\`, \`cancel(true)\` không bảo đảm interrupt task đang chạy; tham số \`mayInterruptIfRunning\` không điều khiển quá trình xử lý trong implementation này. Future bị cancel là trạng thái kết quả bị hoàn tất exceptional, không đồng nghĩa mọi công việc bên ngoài đã được dừng.

## 9. Ví dụ hoàn chỉnh: tách I/O và CPU, composition không block

Tạo file **CompletableFutureExecutorDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.CompletionException;

public class CompletableFutureExecutorDemo {

    private static String readRemoteValue() {
        try {
            // Mô phỏng một API đồng bộ có thể block.
            Thread.sleep(50L);
            return "payload";
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new CompletionException(error);
        }
    }

    private static void stop(ExecutorService executor) {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException error) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) {
        ExecutorService ioExecutor = new ThreadPoolExecutor(
                2,
                2,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(16),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            // Blocking I/O chạy trên executor riêng.
            // Phép biến đổi CPU ngắn chạy trên common pool.
            CompletableFuture<String> pipeline =
                    CompletableFuture.supplyAsync(
                            CompletableFutureExecutorDemo::readRemoteValue,
                            ioExecutor)
                    .thenApplyAsync(
                            String::toUpperCase,
                            ForkJoinPool.commonPool());

            // thenCompose nối bước bất đồng bộ tiếp theo,
            // không block worker bằng get() hoặc join().
            CompletableFuture<String> composed =
                    CompletableFuture.supplyAsync(
                            () -> "order-42",
                            ioExecutor)
                    .thenCompose(orderId ->
                            CompletableFuture.supplyAsync(
                                    () -> "loaded:" + orderId,
                                    ioExecutor));

            // orTimeout giới hạn thời gian hoàn tất ở tầng future.
            CompletableFuture<String> timed =
                    CompletableFuture.supplyAsync(
                            () -> "fast-response",
                            ioExecutor)
                    .orTimeout(2, TimeUnit.SECONDS);

            // join ở main thread, không phải bên trong worker của pool.
            System.out.println("pipeline = " + pipeline.join());
            System.out.println("composed = " + composed.join());
            System.out.println("timed = " + timed.join());
        } finally {
            stop(ioExecutor);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out CompletableFutureExecutorDemo.java
java -cp out CompletableFutureExecutorDemo
~~~

Output chính xác:

~~~text
pipeline = PAYLOAD
composed = loaded:order-42
timed = fast-response
~~~

Trong ví dụ:

- Lời gọi đồng bộ mô phỏng I/O chạy trên executor riêng có hai worker và queue giới hạn 16 task.
- Phép biến đổi chuỗi chạy trên common pool vì đây là công việc CPU ngắn.
- \`thenCompose\` submit bước kế tiếp mà không block worker.
- \`orTimeout\` giới hạn thời gian hoàn tất future.
- \`join()\` chỉ được gọi từ main thread sau khi pipeline đã được dựng.
- Executor do ứng dụng tạo được shutdown trong \`finally\`; common pool là shared executor nên không shutdown ở đây.

Ví dụ minh họa cấu trúc điều phối. Trong ứng dụng thực tế, thay \`Thread.sleep\` bằng API I/O thật và cấu hình timeout tại chính API đó.

## 10. Backpressure, queue và lifecycle

Tách executor chỉ hiệu quả khi có giới hạn tải rõ ràng.

Một executor I/O có thể dùng \`ThreadPoolExecutor\` với:

- Số worker phù hợp với giới hạn dịch vụ downstream.
- \`ArrayBlockingQueue\` hoặc queue có giới hạn khác.
- Rejection policy được thiết kế và quan sát được.
- Timeout cho thao tác I/O.
- Metrics cho active worker, queue size, rejected task và thời gian xử lý.

Queue không giới hạn có thể biến quá tải tức thời thành backlog dài và tăng memory usage. Queue quá nhỏ có thể từ chối task thường xuyên. Hãy chọn theo latency budget và khả năng xử lý của hệ thống.

Không tạo executor mới cho từng request nếu không có lifecycle và giới hạn tài nguyên rõ ràng. Thường nên tạo executor ở cấp ứng dụng hoặc service, chia sẻ trong phạm vi phù hợp và shutdown khi service dừng.

Với executor được chia sẻ, chỉ component sở hữu nó mới chịu trách nhiệm shutdown. Không shutdown common pool hoặc executor do framework khác quản lý.

## 11. Lỗi thường gặp

### Đưa blocking I/O vào common pool mặc định

Async method không truyền executor thường dùng common pool. Worker bị giữ khi chờ I/O có thể làm chậm các task khác. Hãy truyền executor I/O riêng hoặc virtual-thread executor phù hợp.

### Nghĩ thenApply luôn chạy trên thread riêng

\`thenApply\` là continuation không Async. Nó có thể chạy trên thread hoàn thành stage trước hoặc caller. Giữ callback ngắn và không blocking.

### Chỉ thêm hậu tố Async nhưng không truyền executor

\`thenApplyAsync(fn)\` vẫn dùng default async facility. Nếu cần tách I/O, truyền \`thenApplyAsync(fn, ioExecutor)\`.

### Gọi join hoặc get bên trong worker để chờ task cùng pool

Khi worker bị giữ bởi task cha, task con có thể nằm trong queue mà không còn worker để chạy. Dùng \`thenCompose\`, \`thenCombine\` hoặc \`allOf\`.

### Dùng pool có queue không giới hạn cho tải không kiểm soát

Backlog có thể tăng liên tục, làm tăng latency và memory usage. Dùng queue có giới hạn và chính sách admission/rejection rõ ràng.

### Dùng quá nhiều worker so với database hoặc remote service

Nhiều worker hơn không làm downstream xử lý nhanh hơn nếu connection hoặc quota đã hết. Giới hạn concurrency theo tài nguyên thực tế.

### Nghĩ timeout của future dừng luôn I/O

\`orTimeout\` hoàn tất future theo thời hạn nhưng không tự hủy socket, query hoặc tác vụ blocking. Cấu hình timeout và cancellation tại API I/O.

### Dùng virtual thread để tăng tốc tính toán CPU

Virtual thread giúp quản lý nhiều tác vụ chờ, không tăng năng lực CPU. Với CPU-bound work, dùng executor có mức parallelism phù hợp.

### Shutdown executor dùng chung

Chỉ shutdown executor do component hiện tại sở hữu. Không shutdown common pool hoặc pool do framework quản lý.

## 12. Checklist

- [ ] Đã phân loại từng bước là CPU-bound hay blocking.
- [ ] Đã biết continuation không Async có thể chạy trên thread hoàn thành hoặc caller.
- [ ] Đã truyền executor tường minh cho async stage cần kiểm soát vị trí thực thi.
- [ ] Đã tách blocking I/O khỏi pool dành cho CPU-bound work.
- [ ] Đã tránh chờ future con bằng \`get()\` hoặc \`join()\` trong cùng bounded executor.
- [ ] Đã dùng \`thenCompose\`, \`thenCombine\` hoặc \`allOf\` để biểu diễn dependency.
- [ ] Đã đặt giới hạn queue và concurrency theo tài nguyên downstream.
- [ ] Đã cấu hình timeout ở cả tầng future và API I/O.
- [ ] Đã hiểu ManagedBlocker là cơ chế hỗ trợ có điều kiện, không phải giải pháp chung.
- [ ] Đã cân nhắc virtual threads cho blocking I/O trên JDK 21+.
- [ ] Đã shutdown đúng executor do ứng dụng sở hữu.
- [ ] Đã đo queue wait, execution time, rejection và end-to-end latency.

## 13. Tài liệu tham khảo

- [Java SE 25 API: CompletableFuture](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 25 API: ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 25 API: ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 25 API: ForkJoinPool](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)

