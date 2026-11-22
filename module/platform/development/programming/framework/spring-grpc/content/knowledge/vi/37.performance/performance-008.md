# Executor sizing

**Executor sizing** là việc chọn số thread, loại hàng đợi và giới hạn tác vụ chờ để gRPC xử lý RPC ổn định dưới tải dự kiến. Trong **SPRING_GRPC**, executor ảnh hưởng đến thời gian chờ trước khi handler chạy, throughput, tail latency, mức sử dụng CPU, memory và khả năng phục hồi khi downstream chậm.

Một executor quá nhỏ làm RPC xếp hàng dù CPU hoặc dependency vẫn còn khả năng xử lý. Một executor quá lớn có thể tạo quá nhiều thread, context switching, stack memory và cạnh tranh connection pool. Hàng đợi không giới hạn có thể biến một đợt quá tải ngắn thành độ trễ kéo dài hoặc cạn heap. Vì vậy, sizing phải dựa trên loại công việc, concurrency, CPU quota, thời gian blocking và giới hạn của downstream.

## 1. Hiểu executor nào đang được sizing

Trong gRPC Java, cần phân biệt executor chạy application callback với thread xử lý transport:

| Thành phần | Vai trò | Khi sizing |
| --- | --- | --- |
| Server application executor | Chạy service implementation/callback của server | Chọn theo CPU work, blocking và concurrency của handler |
| Client application executor | Chạy callback của async client và một số application task | Chọn theo số callback, thời gian xử lý và blocking ở client |
| Transport event loop | Xử lý I/O, HTTP/2 frame và sự kiện network | Được transport quản lý; không dùng làm nơi chạy công việc blocking |
| Offload executor | Chạy một số tác vụ nội bộ có thể blocking hoặc không phù hợp event loop, tùy API/runtime | Chỉ cấu hình khi hiểu rõ tác vụ và hướng dẫn phiên bản |
| Downstream pool | Ví dụ JDBC connection pool hoặc HTTP client pool | Là giới hạn năng lực riêng; không tăng executor vượt quá khả năng downstream một cách vô ích |

ServerBuilder.executor(Executor) cấu hình executor dùng để thực thi application code của server. ManagedChannelBuilder.executor(Executor) cấu hình executor cho application callback ở client. Các API cụ thể có thể khác khi dùng Spring gRPC starter; hãy dùng cơ chế cấu hình của đúng starter/phiên bản, nhưng vẫn giữ sự phân biệt giữa application executor và transport event loop.

Không giả định một gRPC RPC luôn chiếm một thread từ lúc bắt đầu đến khi kết thúc. Với service bất đồng bộ, thread có thể chạy callback rồi được trả về pool. Một stream dài chỉ chiếm thread liên tục nếu handler hoặc callback thực hiện công việc blocking hay giữ thread trong vòng lặp.

## 2. Phân loại workload trước khi chọn số thread

Sizing bắt đầu bằng cách xác định handler làm gì:

| Loại workload | Đặc điểm | Hướng sizing ban đầu |
| --- | --- | --- |
| CPU-bound | Tính toán, mã hóa, transform dữ liệu; ít chờ I/O | Số thread gần số CPU khả dụng, điều chỉnh theo mục tiêu utilization |
| Blocking I/O | Chờ JDBC, HTTP client đồng bộ, file hoặc lock | Có thể cần nhiều thread hơn CPU, nhưng phải giới hạn theo downstream capacity |
| Non-blocking I/O | Dùng async client/reactive API, callback hoàn tất sau | Không cần một thread cho mỗi request đang chờ; sizing theo callback work |
| Mixed workload | Vừa tính toán vừa blocking | Tách executor theo loại công việc nếu có thể |
| Streaming callback | Xử lý từng message, có thể kéo dài theo thời gian | Sizing theo thời gian xử lý callback và số callback đồng thời, không chỉ số stream mở |

Một service có 2.000 stream đang mở không nhất thiết cần 2.000 thread. Nếu stream chủ yếu idle và callback ngắn, số thread có thể nhỏ hơn nhiều. Ngược lại, chỉ 100 RPC đồng thời cũng có thể làm pool cạn nếu mỗi handler giữ thread chờ database hoặc gọi downstream đồng bộ.

## 3. Ước lượng thread cho CPU-bound và blocking workload

Với CPU-bound task, số thread chạy đồng thời thường bắt đầu gần số CPU thực sự được cấp cho process. Tạo nhiều thread CPU-bound hơn số core không làm tăng năng lực tính toán; chúng chủ yếu tranh CPU và tạo context switching.

Với blocking workload, có thể dùng công thức kinh nghiệm để ước lượng ban đầu:

\[
N \approx N_{cpu} \times U_{cpu} \times
\left(1 + \frac{W}{C}\right)
\]

Trong đó:

- \(N\): số thread ước lượng.
- \(N_{cpu}\): số CPU khả dụng cho process/container.
- \(U_{cpu}\): mức sử dụng CPU mục tiêu, từ 0 đến 1.
- \(W\): thời gian chờ trung bình của một task.
- \(C\): thời gian CPU thực sự dùng cho task.

Ví dụ, container có 8 CPU, mục tiêu CPU utilization 0,8, task dùng CPU 10 ms và chờ I/O 30 ms:

\[
N \approx 8 \times 0.8 \times (1 + 30/10)
  = 25.6
\]

Có thể bắt đầu benchmark quanh 24–26 thread cho workload đó. Đây chỉ là ước lượng, không phải cấu hình production mặc định. Nếu downstream chỉ cho phép 16 request đồng thời, pool 26 thread có thể tạo thêm thread chờ connection mà không tăng throughput. Cần giới hạn concurrency ở đúng tầng và đo lại.

### 3.1. Dùng CPU quota thực tế

Runtime.getRuntime().availableProcessors() là điểm tham khảo, nhưng cần xác nhận JDK/container runtime nhận diện đúng CPU quota. Container có thể chạy trên máy host 64 core nhưng chỉ được cấp 4 CPU. Sizing theo số core host sẽ tạo pool quá lớn.

Khi đánh giá, ghi nhận:

- CPU quota/limit của container và CPU thực tế được cấp.
- Số core process nhìn thấy trong runtime.
- CPU utilization và throttling.
- Số replica và tổng concurrency trên toàn cluster.

Nếu tăng replicas, tổng số thread và kết nối downstream cũng tăng. Sizing một instance mà không tính tổng tải của toàn cluster có thể làm database hoặc dependency quá tải.

## 4. Giới hạn executor theo downstream capacity

Executor không tạo thêm năng lực cho database hoặc service downstream. Nếu mỗi RPC đồng bộ lấy một JDBC connection, số tác vụ DB đồng thời bị giới hạn bởi connection pool và database capacity.

Ví dụ:

- Server executor có 64 thread.
- JDBC pool có 16 connection.
- Nhiều handler cùng gọi database đồng bộ.

Tối đa khoảng 16 handler có thể giữ connection DB cùng lúc; phần còn lại có thể chờ trong connection pool trong khi vẫn chiếm thread executor. Hậu quả là active thread tăng, queue tăng và latency lan truyền sang các RPC khác.

Hãy xác định concurrency limit cho từng dependency. Có thể dùng semaphore/admission control trước đoạn blocking để chỉ cho phép số tác vụ phù hợp chạy đồng thời. Nếu hệ thống có nhiều dependency, không dùng một giới hạn chung thiếu phân biệt cho tất cả.

## 5. Bounded pool và bounded queue

Trong production, executor nên có giới hạn rõ ràng về:

- Core thread count.
- Maximum thread count.
- Queue capacity.
- Keep-alive cho thread vượt core.
- Rejection/overload behavior.

Ví dụ với ThreadPoolExecutor:

```java
int coreThreads = 12;
int maxThreads = 24;
int queueCapacity = 128;

ThreadPoolExecutor grpcExecutor = new ThreadPoolExecutor(
    coreThreads,
    maxThreads,
    60,
    TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(queueCapacity),
    runnable -> {
        Thread thread = new Thread(
            runnable,
            "grpc-app-" + THREAD_IDS.incrementAndGet());
        thread.setDaemon(false);
        return thread;
    },
    new ThreadPoolExecutor.AbortPolicy()
);
```

Đây là ví dụ cấu trúc, các con số cần được benchmark. THREAD_IDS là AtomicInteger được khai báo ở phạm vi cấu hình. Queue hữu hạn giúp hệ thống có một điểm quá tải quan sát được thay vì giữ task vô hạn trong heap.

Với ThreadPoolExecutor, khi số thread đạt core size, task thường được đưa vào queue trước; chỉ khi queue đầy pool mới tăng thread tới maximum. Vì vậy, queue quá lớn có thể làm task chờ lâu trong khi pool chưa mở rộng. Hãy chọn queue capacity theo ngân sách chờ và kiểm tra hành vi thực tế.

### 5.1. Chọn queue capacity theo latency budget

Queue không phải nơi lưu backlog tùy ý. Một cách ước lượng là dùng định luật Little:

\[
L = \lambda \times W_q
\]

Trong đó L là số task trung bình đang chờ, λ là tốc độ task đến và Wq là thời gian chờ trung bình. Nếu service nhận khoảng 500 task/s và chỉ cho phép queue wait khoảng 40 ms, số task chờ trung bình tương ứng khoảng 20. Capacity thực tế còn cần xét burst, service time và mức biến động; không lấy con số trung bình làm giới hạn duy nhất.

Queue lớn làm tăng thời gian chờ và giữ request context/payload lâu hơn. Nếu deadline RPC chỉ còn 100 ms nhưng task nằm trong queue 300 ms, công việc có thể đã hết giá trị trước khi handler bắt đầu. Có thể loại bỏ hoặc từ chối công việc đã hết deadline thay vì tiếp tục xử lý vô ích.

## 6. Rejection policy và load shedding

Khi pool và queue đều đầy, hệ thống cần hành vi quá tải rõ ràng:

| Policy | Hành vi | Đánh giá với gRPC |
| --- | --- | --- |
| Abort/reject | Từ chối submit bằng exception | Có thể quan sát overload; cần kiểm thử cách gRPC runtime xử lý rejection |
| CallerRuns | Thread gọi submit tự chạy task | Nguy hiểm nếu caller là transport/event-loop thread vì có thể block I/O |
| Discard | Bỏ task mới | Không phù hợp với RPC nếu làm mất công việc âm thầm |
| DiscardOldest | Bỏ task cũ nhất trong queue | Có thể làm mất request đã được nhận mà caller không biết |

Không dùng CallerRunsPolicy như cách tự động điều tiết cho server executor nếu chưa chứng minh caller không phải transport thread. Cũng không dùng discard policy cho RPC có semantics cần bảo đảm.

Không nên dựa vào việc RejectedExecutionException tự động biến thành một gRPC status cụ thể. Cách gRPC runtime phản ứng có thể phụ thuộc vị trí rejection và phiên bản. Nếu cần trả status overload có kiểm soát như RESOURCE_EXHAUSTED hoặc UNAVAILABLE, hãy thực hiện admission control ở application boundary/interceptor trước khi dispatch công việc nặng, rồi integration test status thực tế.

Load shedding nên sớm và có giới hạn: từ chối request mới khi hệ thống đã quá tải, giữ năng lực cho request đang chạy và tránh để queue lớn kéo dài latency của toàn bộ service.

## 7. Cấu hình executor trong Spring

Có thể quản lý application executor bằng Spring bean. Ví dụ với ThreadPoolTaskExecutor:

```java
@Configuration
class GrpcExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor grpcServerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(12);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(128);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("grpc-server-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
```

Spring khởi tạo ThreadPoolTaskExecutor qua lifecycle của bean. Nó cung cấp Executor để truyền vào gRPC server builder. Ví dụ tích hợp với API gRPC Java:

```java
@Bean(destroyMethod = "shutdown")
Server grpcServer(
        @Qualifier("grpcServerExecutor") Executor grpcExecutor,
        GreeterService greeterService) throws IOException {

    return ServerBuilder.forPort(9090)
        .executor(grpcExecutor)
        .addService(greeterService)
        .build()
        .start();
}
```

Ví dụ dùng API gRPC Java chuẩn. Nếu starter đang dùng tự quản lý server, hãy cấu hình executor qua extension point của starter thay vì tự tạo thêm server thứ hai. Tên property/annotation phụ thuộc starter và phiên bản; không sao chép cấu hình của thư viện khác mà chưa kiểm tra.

Đảm bảo server dừng trước executor mà nó sử dụng. Với Spring dependency graph, server bean nhận executor bean làm dependency nên Spring có thể hủy dependent bean trước dependency. Với lifecycle tùy chỉnh, cần điều phối rõ: stop nhận RPC mới, shutdown server, đợi call đang chạy, rồi mới shutdown executor.

## 8. Tách executor cho server, client và công việc blocking

Không nhất thiết mọi công việc đều chạy trên một pool:

- Server application executor chạy callback/handler của server.
- Client callback executor chạy callback của async stub nếu được cấu hình riêng.
- Blocking I/O executor dành cho đoạn code bắt buộc phải chờ JDBC/HTTP/file.
- CPU executor dành cho transform hoặc tính toán nặng.

Tách pool giúp một workload blocking không chiếm hết thread cần cho callback khác. Nhưng quá nhiều pool cũng tạo thêm thread, queue và cấu hình khó vận hành. Chỉ tách khi workload hoặc SLO khác nhau và số liệu chứng minh cần.

Ví dụ, handler gRPC có thể chuyển đoạn blocking sang executor chuyên dụng có giới hạn:

```java
blockingIoExecutor.execute(() -> {
    try {
        Item item = repository.findById(request.getItemId());
        responseObserver.onNext(toReply(item));
        responseObserver.onCompleted();
    } catch (Exception error) {
        responseObserver.onError(mapToGrpcStatus(error));
    }
});
```

Đây là skeleton minh họa. Cần bảo đảm observer chỉ được phát từ một execution path được serialize, xử lý cancellation/deadline và không gửi response sau khi call đã đóng. Nếu task bị reject, phải xử lý overload theo contract; không bỏ qua exception.

Không dùng ForkJoinPool.commonPool() cho blocking JDBC/HTTP call một cách tùy tiện. Blocking task có thể chiếm worker dùng chung và ảnh hưởng các tác vụ không liên quan.

## 9. Tránh starvation và deadlock

Một số lỗi executor khó phát hiện khi tải thấp nhưng xuất hiện ở production:

**Nested blocking call trên cùng pool:** handler chiếm thread rồi submit task vào cùng pool và chờ Future.get(). Nếu tất cả thread đều bị giữ bởi handler đang chờ task con, task con không có thread để chạy; pool bị deadlock/starvation.

**Blocking callback:** callback gRPC chờ database, lock hoặc network lâu, làm các callback khác không có thread.

**Một pool cho mọi workload:** tác vụ CPU nặng làm chậm callback nhẹ; task blocking làm cạn worker.

**Queue quá dài:** thread không bận hết nhưng RPC vẫn hết deadline khi đang chờ.

**Thread count quá lớn:** context switching và memory overhead tăng, downstream bị dồn tải.

Hướng xử lý:

- Tránh submit vào cùng pool rồi block chờ task con.
- Dùng API async/non-blocking nếu có thể.
- Tách CPU-bound và blocking work khi cần.
- Đặt deadline cho downstream call và truyền cancellation.
- Dùng queue hữu hạn và admission control.
- Profile thread dump khi thấy latency tăng hoặc worker bị BLOCKED/WAITING lâu.

## 10. Streaming và thời gian chiếm thread

Một bidi stream có thể sống hàng phút hoặc hàng giờ. Điều đó không nhất thiết có nghĩa một thread phải bị giữ suốt thời gian stream tồn tại. Với gRPC Java callback model, application thường nhận callback khi có message hoặc sự kiện kết thúc.

Điều làm thread bị chiếm là công việc trong callback:

- Parse/validate message lớn.
- Ghi database đồng bộ.
- Chờ downstream response.
- Chạy vòng lặp phát nhiều message liên tục.
- Chờ lock hoặc queue.

Với stream có message frequency cao, callback ngắn nhưng dày có thể làm executor bận liên tục. Cần đo callback duration và message rate, không chỉ active stream count. Dùng manual flow control/backpressure để consumer không nhận message nhanh hơn khả năng xử lý.

Với outbound stream, tránh vòng lặp phát message lớn trên một worker mà không kiểm tra readiness. Với inbound stream, không gọi request thêm message trước khi consumer có capacity nếu dùng manual flow control.

## 11. Client executor và callback của async stub

Client dùng async stub có thể thực hiện callback khi response đến. Nếu callback làm công việc blocking hoặc xử lý payload nặng, hãy cân nhắc cấu hình client application executor riêng:

```java
ExecutorService clientCallbacks =
    new ThreadPoolExecutor(
        4,
        8,
        60,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(64));

ManagedChannel channel = ManagedChannelBuilder
    .forAddress("catalog.internal", 8443)
    .useTransportSecurity()
    .executor(clientCallbacks)
    .build();
```

Ví dụ chỉ minh họa API và giới hạn; production cần đặt thread factory, rejection policy và lifecycle cho cả executor lẫn channel. Client callback executor không phải transport event loop. Đừng dùng cùng executor cho server và client nếu việc chia sẻ làm một phía có thể làm cạn thread của phía còn lại.

Nếu callback chỉ chuyển kết quả sang reactive pipeline hoặc queue bounded, pool nhỏ có thể đủ. Nếu callback thực hiện blocking I/O, hãy tách phần blocking sang pool phù hợp và không giữ callback thread trong lúc chờ.

## 12. Deadline, cancellation và Context propagation

Một task đã nằm trong executor queue có thể không còn hữu ích khi deadline RPC đã hết hoặc caller đã cancel. Trước khi thực hiện công việc tốn kém, nên kiểm tra call context/cancellation và truyền deadline còn lại tới downstream.

gRPC Java dùng io.grpc.Context để truyền một số context theo call. Tuy nhiên, ThreadLocal như MDC hoặc security context của framework không tự động được bảo toàn qua mọi executor. Nếu cần correlation ID, principal hoặc tracing context, dùng interceptor/context propagation mechanism phù hợp và kiểm thử trên thread thực thi callback.

Khi chuyển task sang executor riêng:

- Capture context tại thời điểm nhận RPC.
- Khôi phục context khi task chạy theo API hỗ trợ.
- Clear context sau khi task hoàn tất để tránh rò rỉ giữa request.
- Hủy task nếu cancellation có thể truyền an toàn.
- Không giữ request/credential nhạy cảm lâu hơn cần thiết trong queue.

## 13. Sizing theo quy trình đo lường

Không chọn thread count chỉ bằng cảm giác. Một quy trình thực tế:

1. **Lập workload profile:** tách unary, client/server/bidi streaming; đo tỷ lệ CPU, blocking và payload.
2. **Xác định giới hạn:** CPU quota, JDBC pool, HTTP connection pool, downstream rate limit và max concurrent streams.
3. **Chọn baseline:** pool CPU gần số core; pool blocking ước lượng theo wait/compute và downstream capacity.
4. **Đặt queue budget:** xác định thời gian chờ tối đa mà deadline/SLO cho phép rồi chọn queue hữu hạn.
5. **Tăng tải theo bước:** tăng concurrency và arrival rate, giữ mỗi mức đủ lâu để quan sát steady state.
6. **Thay đổi từng biến:** thread count, queue capacity, downstream concurrency hoặc callback duration.
7. **Quan sát saturation:** tìm thời điểm throughput không tăng nhưng queue wait, p95/p99 hoặc CPU throttling tăng.
8. **Kiểm thử overload:** xác minh request bị từ chối có kiểm soát và hệ thống phục hồi sau khi tải giảm.

Ví dụ ma trận benchmark:

| Run | Core threads | Max threads | Queue | Mục tiêu |
| --- | ---: | ---: | ---: | --- |
| A | 8 | 8 | 32 | Baseline gần CPU count |
| B | 8 | 16 | 64 | Thử tăng concurrency |
| C | 12 | 24 | 128 | Thử pool lớn hơn |
| D | 12 | 24 | 32 | Giảm queue wait, load shed sớm hơn |

Đây là ma trận ví dụ, không phải giá trị mặc định. Chạy cùng payload, TLS, JVM options, CPU quota và downstream configuration để so sánh công bằng.

## 14. Metrics cần theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| Pool size / active threads | Mức sử dụng worker |
| Queue depth | Backlog đang chờ |
| Queue wait time | Thời gian task chờ trước khi chạy |
| Task execution time | Thời gian worker thực hiện task |
| Rejected task count | Tần suất chạm giới hạn executor |
| RPC latency p50/p95/p99 | Tác động thực tế tới client |
| RPC throughput/error/cancel | Năng lực và độ tin cậy |
| CPU utilization/throttling | CPU có phải bottleneck không |
| GC pause/allocation/heap | Áp lực memory do thread, queue và payload |
| JDBC/HTTP pool active, pending, wait | Executor có đang đẩy quá nhiều tải xuống dependency không |
| Thread state/thread dump | Phát hiện BLOCKED, WAITING, deadlock hoặc callback bị giữ lâu |

Metric nên gắn với service/method và loại workload có cardinality giới hạn. Không dùng request ID, user ID hoặc token làm label. Kết hợp metrics với trace và thread dump khi cần điều tra.

## 15. Những lỗi sizing thường gặp

| Sai lầm | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Dùng số core của host thay vì CPU quota | Tạo quá nhiều thread trong container | Sizing theo CPU process thực sự được cấp |
| Đặt max thread rất lớn | Context switching và downstream overload | Ước lượng theo workload và đo |
| Queue không giới hạn | Memory tăng và latency kéo dài | Bounded queue theo latency budget |
| Dùng CallerRuns trên transport path | Có thể block event loop | Admission control và rejection được kiểm thử |
| Dùng discard policy | Mất RPC/task âm thầm | Overload behavior tường minh |
| Gộp CPU và blocking workload vào một pool | Starvation giữa các loại công việc | Tách pool khi cần và có giới hạn |
| Coi mỗi stream là một thread | Sizing quá lớn cho stream idle | Đo callback occupancy và message rate |
| Tăng executor vượt JDBC pool | Nhiều thread chờ connection | Giới hạn DB concurrency phù hợp |
| Dùng directExecutor cho handler blocking | Block transport thread | Chỉ dùng khi code nhẹ và non-blocking |
| Không kiểm tra deadline/cancellation | Tiếp tục làm việc đã hết giá trị | Propagate deadline và dừng task phù hợp |

## 16. Checklist production

Trước khi phát hành cấu hình executor, hãy xác nhận:

1. **Executor boundary:** biết executor nào chạy application callback và executor nào phục vụ transport/offload.
2. **Workload:** phân loại CPU-bound, blocking, non-blocking và streaming callback.
3. **CPU:** sizing theo quota thực tế của container.
4. **Downstream:** thread concurrency không vượt capacity DB/HTTP/dependency một cách vô ích.
5. **Bounds:** core/max thread và queue capacity đều có giới hạn.
6. **Queue budget:** thời gian chờ phù hợp deadline và latency SLO.
7. **Rejection:** không dùng discard; tránh CallerRuns trên transport path; test overload behavior.
8. **Spring lifecycle:** server dừng/drain trước khi executor bị shutdown.
9. **Client callbacks:** không block callback thread; tách blocking work nếu cần.
10. **Streaming:** đo callback duration, message rate và áp dụng backpressure.
11. **Context:** correlation/security/tracing context được truyền và clear đúng cách.
12. **Cancellation:** task tôn trọng deadline/cancellation khi có thể.
13. **Benchmark:** có warm-up, steady-state, tải tăng dần và test overload.
14. **Observability:** active threads, queue wait/depth, rejection, RPC p95/p99, CPU và downstream pool được theo dõi.

## 17. Ghi nhớ

Executor sizing trong Spring gRPC là bài toán cân bằng giữa khả năng xử lý song song, thời gian chờ, CPU, memory và năng lực downstream. CPU-bound workload thường bắt đầu gần số CPU khả dụng; blocking workload có thể cần nhiều thread hơn nhưng phải bị giới hạn bởi connection pool và capacity của dependency. Công thức wait/compute chỉ là ước lượng ban đầu, cần benchmark trong môi trường có CPU quota và traffic gần production.

Hãy phân biệt application executor với transport event loop, dùng bounded thread pool và queue, tránh CallerRuns/discard thiếu kiểm soát, không block callback hoặc dùng directExecutor cho công việc blocking. Quản lý executor bằng Spring lifecycle, truyền deadline/cancellation/context qua thread boundary và theo dõi active threads, queue wait, rejection, p95/p99 cùng downstream wait. Khi hệ thống quá tải, load shedding sớm và có quan sát thường bảo vệ độ tin cậy tốt hơn việc tăng thread hoặc queue vô hạn.

### Tài liệu tham khảo

- [gRPC – Performance](https://grpc.io/docs/guides/performance/)
- [gRPC Java – ServerBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html)
- [gRPC Java – ManagedChannelBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html)
- [Java – ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
