# Executor cho service implementation

Trong gRPC Java, service implementation xử lý request trên executor do server quản lý. Executor quyết định các callback nghiệp vụ được chạy trên những thread nào, có bao nhiêu tác vụ được xử lý đồng thời và request phải chờ bao lâu khi hệ thống bận. Chọn executor phù hợp giúp Spring gRPC giữ độ trễ ổn định, tránh một service blocking làm nghẽn toàn bộ server và kiểm soát tài nguyên khi tải tăng.

ServerBuilder.executor(Executor) cấu hình executor dùng để thực thi công việc của application call trên server. Đây là **executor cho service handler**, không phải executor để tùy tiện chạy mọi tác vụ của ứng dụng. Trong ứng dụng Spring, server thường được tạo bởi starter hoặc cấu hình tự động; cần đưa executor vào server builder qua điểm mở rộng mà phiên bản tích hợp đang hỗ trợ. Nếu không cấu hình, gRPC/framework sẽ dùng executor mặc định của nó; đặc tính cụ thể phụ thuộc transport và starter.

## 1. Executor nằm ở đâu trong luồng xử lý RPC?

Khi client gửi RPC, transport nhận dữ liệu HTTP/2, giải mã frame và chuyển request tới service. Phần xử lý nghiệp vụ được dispatch qua executor của server:

~~~mermaid
flowchart LR
    C["gRPC client"] --> T["HTTP/2 transport"]
    T --> D["Dispatch application call"]
    D --> E["Server application executor"]
    E --> H["Service implementation"]
    H --> DB["Database / downstream"]
    H --> R["Response observer"]
    R --> T
    T --> C
~~~

Transport và executor ứng dụng có vai trò khác nhau. Transport chịu trách nhiệm I/O và giao thức; service executor chạy callback nghiệp vụ. Không nên chạy xử lý blocking nặng trực tiếp trên event loop hoặc thread I/O của transport.

Executor không có nghĩa mỗi RPC được gán cố định một thread riêng trong suốt vòng đời. Một call có thể kích hoạt nhiều callback; gRPC điều phối chúng theo cơ chế thực thi của server. Code ứng dụng không nên dựa vào thread affinity nếu không có bảo đảm cụ thể từ API.

## 2. Cấu hình executor trên gRPC ServerBuilder

Với server gRPC Java được tạo trực tiếp, có thể truyền một ExecutorService vào builder:

~~~java
ThreadPoolExecutor grpcServiceExecutor =
    new ThreadPoolExecutor(
        16,
        32,
        60,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(400),
        runnable -> {
            Thread thread = new Thread(
                runnable,
                "grpc-service-" + SERVICE_THREAD_COUNTER.incrementAndGet());
            thread.setDaemon(false);
            return thread;
        },
        new ThreadPoolExecutor.AbortPolicy());

Server server = ServerBuilder.forPort(9090)
    .executor(grpcServiceExecutor)
    .addService(new InventoryServiceImpl())
    .build()
    .start();
~~~

Ví dụ minh họa API gRPC Java; SERVICE_THREAD_COUNTER là AtomicInteger do ứng dụng khai báo. Trong Spring, nên tạo executor thành bean và cấu hình server builder qua integration point của starter đang dùng. Không tạo một thread pool mới cho từng RPC hoặc từng service instance.

Nếu starter tự tạo server và đăng ký service bằng annotation, hãy tìm đúng cơ chế ServerBuilder customizer/configurer mà phiên bản đó cung cấp. Tên interface và thứ tự customizer có thể khác nhau giữa các thư viện tích hợp; không nên sao chép một class cấu hình của starter khác mà chưa xác minh.

## 3. Quản lý executor như Spring bean

Executor là tài nguyên có vòng đời. Spring nên tạo một pool dùng chung cho server và shutdown nó khi application context đóng:

~~~java
@Configuration
public class GrpcExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    public ExecutorService grpcServiceExecutor() {
        return new ThreadPoolExecutor(
            16,
            32,
            60,
            TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(400),
            new ThreadFactoryBuilder()
                .setNameFormat("grpc-service-%d")
                .build(),
            new ThreadPoolExecutor.AbortPolicy());
    }
}
~~~

ThreadFactoryBuilder ở ví dụ thuộc Guava; có thể thay bằng ThreadFactory tự viết nếu dự án không dùng Guava. Bean cần được nối vào server builder thực tế. Chỉ khai báo bean mà không cấu hình server sử dụng nó thì không thay đổi executor của gRPC.

Trong shutdown, nên ngừng nhận request mới trước, cho RPC đang chạy thời gian hoàn tất, rồi shutdown executor. Nếu hết grace period, gọi shutdownNow() và theo dõi các task còn lại. Không đóng executor dùng chung trước khi gRPC server ngừng dispatch callback.

## 4. Chọn pool theo đặc tính công việc

Không có một kích thước pool tối ưu cho mọi service. Trước tiên phân loại công việc:

| Loại công việc | Đặc điểm | Hướng chọn executor |
| --- | --- | --- |
| CPU-bound | Tính toán, serialize bổ sung, mã hóa hoặc xử lý dữ liệu trong bộ nhớ | Pool tương đối gần số core khả dụng; tránh tạo quá nhiều thread cạnh tranh CPU |
| Blocking I/O | JDBC, file, HTTP client blocking hoặc gọi blocking stub | Có thể cần nhiều worker hơn số core, nhưng phải giới hạn theo connection pool và downstream capacity |
| Tác vụ nền dài | Export, batch, xử lý file lớn | Pool riêng, queue và concurrency limit riêng; không chiếm hết worker phục vụ RPC ngắn |
| Callback nhanh | Validate, ánh xạ request/response, dispatch | Giữ thời gian callback ngắn để worker sớm phục vụ call tiếp theo |

Nếu mọi handler cùng chạy một pool, một nhóm request chờ database lâu có thể chiếm hết worker và khiến RPC đọc nhanh cũng phải xếp hàng. Tách executor theo loại tải giúp giới hạn ảnh hưởng chéo.

Ví dụ tách executor cho công việc I/O blocking:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService reportIoExecutor() {
    return new ThreadPoolExecutor(
        8,
        24,
        30,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadFactoryBuilder()
            .setNameFormat("report-io-%d")
            .build(),
        new ThreadPoolExecutor.AbortPolicy());
}
~~~

Service handler có thể offload một phần việc sang reportIoExecutor, nhưng phải quản lý deadline/cancellation và kết quả bất đồng bộ. Không nên để handler chờ vô hạn trên Future.get(); đặt deadline cho RPC và thời gian chờ riêng phù hợp với phần ngân sách còn lại.

## 5. Tránh deadlock khi dùng chung pool

Một lỗi dễ gặp là handler chạy trên pool có kích thước N, rồi submit tác vụ con vào chính pool đó và block chờ kết quả. Nếu N handler cùng làm vậy, tất cả worker có thể bị giữ bởi tác vụ cha trong khi task con nằm trong queue. Không còn worker để chạy task con, hệ thống deadlock do thread starvation.

~~~mermaid
flowchart TD
    A["N handler chiếm N worker"] --> B["Mỗi handler submit task con"]
    B --> C["Handler block chờ Future"]
    C --> D["Task con nằm trong queue"]
    D --> E["Không còn worker rảnh"]
    E --> F["Thread starvation / deadlock"]
~~~

Các cách tránh:

- Dùng async composition thay vì block chờ task con.
- Dùng executor riêng cho tác vụ blocking/downstream.
- Không submit task con vào pool đang bị các task cha chờ kết quả.
- Giới hạn fan-out và số tác vụ đồng thời trên mỗi request.
- Đặt deadline và cancellation cho cả task cha lẫn task con.

Tách pool không tự giải quyết mọi deadlock; vẫn cần kiểm tra chuỗi dependency giữa executor, connection pool và downstream.

## 6. Truyền gRPC Context khi offload tác vụ

Context.current() gắn với luồng thực thi callback hiện tại. Khi handler chuyển việc sang executor khác, context không tự xuất hiện trong thread mới. Nếu tác vụ con gọi gRPC downstream hoặc cần kiểm tra cancellation, hãy capture context trước khi submit:

~~~java
Context rpcContext = Context.current();

reportIoExecutor.execute(rpcContext.wrap(() -> {
    if (rpcContext.isCancelled()) {
        return;
    }

    ReportData data = reportRepository.load(request);

    if (!rpcContext.isCancelled()) {
        downstreamStub.withDeadlineAfter(
            300, TimeUnit.MILLISECONDS)
            .enrich(toRequest(data));
    }
}));
~~~

Ngân sách 300 ms chỉ là ví dụ; downstream call còn phải tuân theo deadline cha. Có thể dùng executor đã gắn context:

~~~java
Context rpcContext = Context.current();
Executor contextualExecutor =
    rpcContext.fixedContextExecutor(reportIoExecutor);

contextualExecutor.execute(() -> processReport(request));
~~~

Nếu task có thể chạy lâu, đăng ký cancellation listener để hủy Future, đóng resource hoặc ngừng producer. Context cancellation không tự interrupt mọi thread và không tự dừng JDBC/HTTP I/O.

## 7. Queue hữu hạn và hành vi khi quá tải

Pool với queue không giới hạn có thể tiếp tục nhận request trong khi tốc độ xử lý đã thấp hơn tốc độ đến. Queue tăng làm latency tăng, request hết deadline trước khi được xử lý và bộ nhớ bị tiêu thụ bởi các task đang chờ.

Nên chọn queue hữu hạn dựa trên:

- Số request chờ tối đa mà SLA còn cho phép.
- Thời gian xử lý trung bình và p95/p99.
- Số worker và khả năng của database/downstream.
- Bộ nhớ cần cho mỗi task đang chờ.

Khi queue đầy, cần một chính sách load shedding rõ ràng. AbortPolicy làm execute ném RejectedExecutionException; cần biết gRPC server/starter xử lý exception dispatch ra sao và chuyển overload thành hành vi có kiểm soát. Tránh mặc định dùng CallerRunsPolicy cho executor phục vụ handler nếu task có thể blocking, vì nó có thể đẩy công việc lên thread gọi execute và gây nghẽn luồng dispatch/transport tùy đường gọi.

Có thể kết hợp admission control, giới hạn concurrency theo method/tenant và status overload phù hợp như RESOURCE_EXHAUSTED. Không biến queue thành nơi giữ request lâu hơn deadline caller.

## 8. Callback và streaming không nên giữ worker bằng vòng chờ

Với async stub hoặc streaming RPC, callback có thể được gọi nhiều lần trong vòng đời call. Không nên giữ worker bằng vòng lặp chờ message hoặc sleep. Hãy xử lý message trong callback ngắn, chuyển công việc nặng sang executor phù hợp và kiểm soát backpressure.

Với server streaming, nếu producer nhanh hơn consumer, cần giới hạn queue và tôn trọng readiness/backpressure của ServerCallStreamObserver. Không để mỗi stream tạo một queue không giới hạn hoặc một thread riêng chạy mãi.

Executor cho service implementation chịu trách nhiệm callback ứng dụng; executor cho producer, I/O hoặc tác vụ nền có thể là pool khác. Cần phân định rõ ai sở hữu task, ai hủy task và ai đóng tài nguyên khi RPC hoàn tất/cancel.

## 9. Quan sát và hiệu chỉnh executor

Theo dõi theo server và theo nhóm service:

- Active worker, pool size và số worker đang chờ.
- Queue depth, thời gian chờ queue và số task bị reject.
- Thời gian thực thi handler, chia theo method.
- Tỷ lệ DEADLINE_EXCEEDED, CANCELLED và RESOURCE_EXHAUSTED.
- CPU, memory, context switch và GC pause.
- JDBC/HTTP connection pool utilization và thời gian chờ downstream.
- Số task còn chạy sau khi RPC đã bị hủy.

Nếu queue tăng nhưng CPU thấp, có thể worker đang block ở I/O hoặc pool bị giới hạn bởi connection pool. Nếu CPU luôn cao và queue tăng, cần xem lại chi phí tính toán, số worker và giới hạn concurrency. Không chỉ tăng maxPoolSize mà không kiểm tra capacity của database và downstream.

## 10. Kiểm thử executor cho service implementation

Các kiểm thử nên xác minh:

1. Server builder thực sự sử dụng executor được cấu hình.
2. Handler chạy trên thread có tên/prefix mong đợi.
3. Pool không vượt giới hạn worker và queue đã đặt.
4. Queue đầy tạo hành vi overload có kiểm soát, không làm nghẽn transport.
5. Blocking handler không làm cạn pool phục vụ RPC nhanh.
6. Context deadline/cancellation được truyền khi task chuyển sang executor khác.
7. Shutdown Spring dừng server trước khi đóng executor và không để thread tồn tại ngoài ý muốn.

Có thể dùng in-process server, executor có thread name riêng và latch để kiểm soát thứ tự. Với Spring integration test, khởi động application context để xác minh bean executor thực sự được nối vào server builder, không chỉ tồn tại trong context.

## 11. Ghi nhớ và tự kiểm tra

**Executor cho service implementation** là nơi gRPC Java dispatch callback ứng dụng trên server. Chọn pool theo loại công việc, giữ queue hữu hạn, tách blocking I/O khỏi callback ngắn, tránh handler block chờ task con trên cùng pool và truyền Context khi offload. Trong Spring, executor phải được quản lý theo vòng đời bean và thực sự được gắn vào server builder do starter sử dụng.

Tự kiểm tra:

1. ServerBuilder.executor(...) điều khiển phần nào của xử lý gRPC server?
2. Vì sao một pool duy nhất có thể bị cạn khi nhiều handler cùng chờ blocking I/O?
3. Tình huống nào gây thread starvation khi handler submit task con vào chính pool đang chạy handler?
4. Vì sao cần truyền Context khi offload sang executor khác?
5. Queue hữu hạn và load shedding giúp bảo vệ deadline, bộ nhớ và downstream như thế nào?

Executor được thiết kế đúng giúp Spring gRPC phân bổ thread có kiểm soát, giữ callback phản hồi nhanh và ngăn một loại công việc chậm làm suy giảm toàn bộ service.
