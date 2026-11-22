# Giới hạn executor queue

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của executor và queue trong quá trình xử lý RPC.
- Phân biệt executor dispatch của gRPC với executor xử lý nghiệp vụ do ứng dụng quản lý.
- Cấu hình bounded queue bằng ThreadPoolExecutor hoặc Spring ThreadPoolTaskExecutor.
- Chọn core size, maximum pool size và queue capacity theo workload, deadline và ngân sách tài nguyên.
- Chọn rejection policy phù hợp khi queue đầy và ánh xạ overload thành status gRPC.
- Tránh block transport/callback thread và tránh tạo queue vô hạn trong streaming RPC.
- Kết hợp queue limit với flow control, deadline, concurrency limit và per-tenant admission.
- Theo dõi queue depth, wait time, task latency và rejection; kiểm thử hành vi quá tải.

## 1. Executor queue giải quyết vấn đề gì?

Trong **SPRING_GRPC**, một RPC đi qua transport, interceptor, service handler và có thể gọi database, HTTP client, broker hoặc service khác. Các callback của gRPC cần được thực thi trên executor. Ứng dụng cũng có thể chuyển công việc blocking hoặc CPU-intensive sang executor riêng để không giữ callback thread quá lâu.

Executor thường có một nhóm worker thread và một queue chứa task đang chờ. Khi worker đều bận, task mới được xếp hàng. Nếu queue không có giới hạn, một đợt traffic vượt năng lực xử lý có thể tích lũy hàng nghìn hoặc hàng triệu task, giữ request/message trong memory và làm latency tăng liên tục.

**Giới hạn executor queue** đặt một capacity hữu hạn cho số task chờ. Khi queue đầy và worker đã đạt giới hạn, hệ thống phải từ chối, trì hoãn hoặc áp dụng backpressure. Queue bounded giúp overload trở thành tín hiệu rõ ràng thay vì biến thành memory exhaustion.

Cần phân biệt:

- **Worker threads:** số task có thể chạy đồng thời.
- **Queue capacity:** số task đang chờ được nhận nhưng chưa chạy.
- **Active tasks:** số task đang thực thi.
- **Rejected tasks:** số task không được nhận vì executor đã bão hòa hoặc đã shutdown.
- **RPC concurrency:** số call đang mở; không đồng nghĩa số task trong executor queue.

~~~mermaid
flowchart TD
    A["gRPC service nhận RPC"] --> B["Xác thực và kiểm tra deadline"]
    B --> C["Submit công việc nghiệp vụ"]
    C --> D{"Worker còn slot?"}
    D -- "Có" --> E["Worker thực thi"]
    D -- "Không" --> F{"Queue còn chỗ?"}
    F -- "Có" --> G["Đưa task vào bounded queue"]
    G --> E
    F -- "Không" --> H["Reject / backpressure"]
    E --> I["Trả kết quả hoặc response"]
    H --> J["RESOURCE_EXHAUSTED hoặc policy phù hợp"]
~~~

Queue chỉ hấp thụ burst ngắn. Nếu tốc độ task đến liên tục cao hơn tốc độ xử lý, queue sẽ đầy dù capacity lớn đến đâu. Cần giới hạn admission và giảm tải, không chỉ tăng queue.

## 2. Hai loại executor cần phân biệt trong gRPC và Spring

### 2.1. gRPC server executor

grpc-java server builder có thể nhận executor để chạy application callbacks/listeners của server. Đây là executor phục vụ dispatch từ gRPC runtime tới service implementation. Nếu không cấu hình, runtime có thể dùng executor mặc định theo transport/version.

Không nên coi executor này là nơi chạy mọi công việc blocking kéo dài. Nếu service handler chờ database hoặc thực hiện CPU-intensive operation lâu, callback worker có thể bị chiếm dụng và làm các RPC khác chậm theo.

Nếu thay executor mặc định bằng bounded executor, cần hiểu chính xác grpc-java version/transport dùng executor đó như thế nào và cách runtime xử lý RejectedExecutionException. Không đặt queue quá nhỏ rồi giả định mọi rejection tự chuyển thành RESOURCE_EXHAUSTED. Hãy kiểm thử behavior với đúng server builder và transport đang chạy.

### 2.2. Application/business executor

Ứng dụng thường có executor riêng cho công việc cần tách khỏi gRPC callback thread, ví dụ:

- Gọi thư viện blocking không có API async.
- Tạo report hoặc xử lý file.
- Chạy CPU-intensive transformation.
- Xử lý batch hoặc event.
- Thực hiện tác vụ phụ có giới hạn concurrency.

Executor này nằm dưới quyền kiểm soát của application. Service có thể chủ động bắt rejection khi submit task và kết thúc RPC bằng status phù hợp.

### 2.3. Spring @Async executor

Spring có thể quản lý executor cho @Async hoặc task submission qua ThreadPoolTaskExecutor. Executor này không tự động đồng nhất với gRPC server executor. Một ứng dụng có thể có nhiều pool khác nhau; mỗi pool cần tên, capacity, metrics và shutdown policy rõ ràng.

Không tạo một pool mới cho mỗi RPC. Tái sử dụng executor singleton do Spring quản lý và đóng nó theo lifecycle của application context.

## 3. Cấu hình bounded ThreadPoolExecutor

Java ThreadPoolExecutor nhận core size, maximum size, keep-alive, queue và rejection handler. Ví dụ một pool xử lý công việc blocking:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

AtomicLong threadSequence = new AtomicLong();

ThreadPoolExecutor reportExecutor = new ThreadPoolExecutor(
        8,
        16,
        30,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(200),
        runnable -> {
            Thread thread = new Thread(runnable);
            thread.setName("grpc-report-" + threadSequence.incrementAndGet());
            thread.setDaemon(false);
            return thread;
        },
        new ThreadPoolExecutor.AbortPolicy());
~~~

Ý nghĩa:

- 8 worker là core pool size.
- Pool có thể tăng tối đa 16 worker khi tải tăng.
- Tối đa 200 task chờ trong queue.
- Khi worker và queue đều đầy, AbortPolicy ném RejectedExecutionException.
- Keep-alive cho phép worker vượt core size được thu hồi khi idle.

Đây là ví dụ sizing, không phải con số khuyến nghị chung. Queue capacity phải hữu hạn. Tránh LinkedBlockingQueue không truyền capacity vì queue đó có thể gần như không giới hạn và che giấu overload.

Tên thread trong ví dụ dùng AtomicLong để tạo hậu tố duy nhất và tương thích với các Java version phổ biến.

## 4. Cấu hình bằng Spring ThreadPoolTaskExecutor

Trong Spring, ThreadPoolTaskExecutor giúp quản lý pool theo lifecycle của application context:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GrpcWorkExecutorConfiguration {

    @Bean
    public ThreadPoolTaskExecutor grpcWorkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("grpc-work-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Spring khởi tạo và quản lý executor bean. Queue capacity 200 là ví dụ. Khi queue đầy, việc submit qua Spring task executor có thể ném TaskRejectedException, một dạng rejection cần được xử lý tại ranh giới submit.

Nếu dùng @Async, chỉ định executor rõ ràng để tránh vô tình dùng common/default executor:

~~~java
@Async("grpcWorkExecutor")
public CompletableFuture<Report> generateReport(ReportRequest request) {
    return CompletableFuture.completedFuture(reportService.generate(request));
}
~~~

Không dựa vào tên bean mặc định để suy ra pool đang được dùng. Trong integration test, xác minh service thực sự submit vào bean đã cấu hình và queue capacity được áp dụng.

## 5. Chọn queue capacity và pool size

Queue capacity là số task chờ, không phải số task đang chạy. Tổng task được giữ bởi pool thường xấp xỉ active workers cộng queue capacity. Nếu mỗi task giữ request, protobuf object, tracing context hoặc buffer lớn, queue lớn có thể tiêu tốn nhiều memory.

Chọn cấu hình theo các yếu tố:

1. **Task service time:** thời gian trung bình và p95/p99 để xử lý một task.
2. **Arrival rate:** số task đến mỗi giây ở giờ bình thường và burst.
3. **Worker capacity:** số task có thể chạy đồng thời mà không làm downstream quá tải.
4. **Task memory:** lượng object/buffer mỗi task giữ trong lúc chờ.
5. **Deadline:** task chờ trong queue phải còn đủ thời gian để chạy và hoàn thành.
6. **Downstream capacity:** database pool, HTTP connection pool, broker quota và rate limit.
7. **Fairness:** một method hoặc tenant không được chiếm toàn bộ queue.

Có thể dùng định luật Little để ước lượng quan hệ giữa số task trong hệ thống, throughput và thời gian chờ:

\[
L = \lambda W
\]

Trong đó L là số task trung bình đang ở trong hệ thống, λ là throughput task/giây và W là thời gian trung bình task ở trong hệ thống. Đây là quan hệ trung bình trong trạng thái ổn định, không phải công thức chọn queue capacity trực tiếp cho burst hoặc tail latency.

Một queue lớn làm tăng thời gian chờ. Nếu deadline còn 300 ms nhưng task phải chờ 2 giây trong queue, task khi bắt đầu đã vô ích. Hãy kiểm tra deadline trước khi submit và bỏ task đã hết hạn trước khi chạy.

Không tăng queue để bù cho throughput thấp kéo dài. Nếu arrival rate lớn hơn service capacity trong thời gian dài, queue sẽ đầy; cần scale worker có kiểm soát, giảm request, rate limit hoặc tối ưu xử lý.

## 6. Rejection policy khi queue đầy

Khi worker đạt max size và queue đầy, ThreadPoolExecutor gọi RejectedExecutionHandler. Mỗi policy có semantics khác nhau:

| Policy | Hành vi | Rủi ro/điểm dùng |
| --- | --- | --- |
| AbortPolicy | Ném RejectedExecutionException | Rõ ràng; application có thể map sang overload response |
| CallerRunsPolicy | Chạy task trên thread gọi submit | Có thể block gRPC callback/transport thread; chỉ dùng khi caller thread được phép chạy task |
| DiscardPolicy | Bỏ task im lặng | Dễ mất RPC/task và treo response nếu không có xử lý bổ sung |
| DiscardOldestPolicy | Bỏ task đầu queue rồi thử submit task mới | Có thể làm mất request cũ và phá thứ tự |

Với gRPC service, AbortPolicy thường dễ kiểm soát nhất ở application executor vì service có thể bắt rejection và kết thúc call. Tránh CallerRunsPolicy nếu submit xảy ra từ gRPC callback thread hoặc transport-related executor: task blocking sẽ chạy ngay trên thread đó, làm chậm các RPC khác và phá vỡ isolation.

Không dùng DiscardPolicy cho RPC nếu client đang chờ response, trừ khi application có cơ chế báo thất bại riêng. Bỏ task mà không kết thúc observer có thể khiến call chờ tới deadline.

## 7. Map rejection thành status gRPC

Khi application submit công việc và executor từ chối, service có thể kết thúc RPC rõ ràng:

~~~java
public void generateReport(
        ReportRequest request,
        StreamObserver<ReportResponse> responseObserver) {

    try {
        reportExecutor.execute(() -> {
            try {
                Report report = reportService.generate(request);
                responseObserver.onNext(toResponse(report));
                responseObserver.onCompleted();
            } catch (Exception failure) {
                responseObserver.onError(mapFailure(failure));
            }
        });
    } catch (RejectedExecutionException rejected) {
        responseObserver.onError(
                Status.RESOURCE_EXHAUSTED
                        .withDescription("Server is at capacity")
                        .asRuntimeException());
    }
}
~~~

Ví dụ minh họa cần thêm terminal guard nếu nhiều đường lỗi/cancellation có thể cạnh tranh. Không gọi onNext sau onError/onCompleted. Nếu client cancel trong lúc task đang chạy, task nên được hủy nếu có thể và không gửi response nữa.

RESOURCE_EXHAUSTED phù hợp khi server từ chối do quota hoặc capacity đã đạt giới hạn. UNAVAILABLE có thể phù hợp nếu policy của hệ thống coi instance tạm thời không sẵn sàng; chọn một contract nhất quán. Không dùng PERMISSION_DENIED cho overload vì đây không phải lỗi authorization.

Không để exception rejection thoát ra khỏi callback rồi kỳ vọng grpc-java luôn ánh xạ nó thành status đúng. Ở application executor, bắt lỗi tại nơi submit. Với executor nội bộ của gRPC server, behavior phụ thuộc runtime/transport và cần test riêng.

## 8. Queue wait phải nằm trong deadline

Deadline của RPC bao gồm thời gian chờ executor queue. Một task không nên bắt đầu nếu call đã hết hạn hoặc không còn đủ thời gian để thực hiện công việc hữu ích.

Có thể lưu Context/deadline cùng task và kiểm tra trước khi chạy:

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

try {
    reportExecutor.execute(() -> {
        if (rpcContext.isCancelled()) {
            return;
        }

        if (deadline != null
                && deadline.isExpired()) {
            return;
        }

        Context previous = rpcContext.attach();
        try {
            Report report = reportService.generate(request);
            // Complete the RPC only if it is still active.
        } finally {
            rpcContext.detach(previous);
        }
    });
} catch (RejectedExecutionException rejected) {
    responseObserver.onError(
            Status.RESOURCE_EXHAUSTED.asRuntimeException());
}
~~~

Đây là skeleton nhấn mạnh việc truyền Context qua ranh giới thread. Trong implementation production, cần dùng Context.wrap hoặc cơ chế propagation tương ứng để tránh attach/detach sai, và bảo đảm cleanup khi task bị cancel. Không giữ Context sau khi RPC đã kết thúc.

Nếu remaining deadline thấp hơn thời gian tối thiểu dự kiến cho task, từ chối sớm hoặc không submit. Đừng xếp một task đã hết hạn vào queue; nó chỉ chiếm slot và có thể chạy sau khi caller đã bỏ cuộc.

Queue capacity cũng nên được chọn sao cho queue wait p95/p99 phù hợp với latency budget. Đo queue wait riêng thay vì chỉ nhìn tổng RPC latency.

## 9. Streaming RPC và bounded work queue

Trong client-streaming hoặc bidirectional streaming, mỗi inbound message có thể tạo một task. Nếu callback chỉ submit task rồi tiếp tục nhận message không giới hạn, application executor queue có thể đầy rất nhanh.

Cần kết hợp:

- Bounded executor queue.
- Giới hạn số message đang chờ xử lý cho mỗi stream.
- Manual inbound flow control để chỉ yêu cầu message tiếp theo khi có capacity.
- Giới hạn tổng bytes/message count của stream.
- Cancellation để dừng producer và task đang chờ.
- Per-stream hoặc per-tenant admission để một stream không chiếm hết queue.

Với grpc-java, ServerCallStreamObserver có thể tắt auto inbound flow control và yêu cầu message tiếp theo có kiểm soát. Ví dụ khái niệm:

~~~java
if (responseObserver instanceof ServerCallStreamObserver<?> serverObserver) {
    serverObserver.disableAutoRequest();
    serverObserver.request(1);
}
~~~

Sau khi xử lý xong một message và giải phóng capacity, service mới yêu cầu message tiếp theo. API cụ thể và quy tắc thread-safety cần kiểm tra theo grpc-java version. Không gọi request tiếp theo ngay sau khi submit task nếu queue chưa có chỗ hoặc task trước chưa hoàn tất; như vậy backpressure không có tác dụng.

Ở outbound streaming, dùng isReady/on-ready handler để producer không đẩy response nhanh hơn transport có thể nhận. Bounded executor queue và flow control bảo vệ hai tầng khác nhau.

## 10. Fairness và cô lập workload

Một global queue hữu hạn vẫn có thể bị một tenant hoặc method chiếm hết. Khi đó request nhỏ từ tenant khác bị reject dù workload của họ nhẹ.

Có thể áp dụng:

- Queue hoặc semaphore riêng theo nhóm workload.
- Per-tenant in-flight task limit.
- Per-method concurrency limit.
- Weighted admission cho task có chi phí khác nhau.
- Ưu tiên có giới hạn cho health/admin task nếu contract cần.
- Tách pool cho CPU-intensive và blocking I/O.

Không tạo executor không giới hạn theo từng tenant; số pool/thread sẽ tăng theo tenant và gây resource exhaustion theo cách khác. Dùng admission controller hoặc quota map có lifecycle/eviction, rồi submit vào một số pool hữu hạn.

Tách blocking I/O khỏi CPU-bound work giúp một loại workload không chiếm worker của loại còn lại. Tuy nhiên, quá nhiều pool làm phức tạp capacity planning và dễ tạo hàng đợi nối tiếp. Chỉ tách khi có lý do đo được.

## 11. Shutdown và task đang chờ

Khi Spring application shutdown, executor cần chính sách rõ cho task đang chạy và task trong queue:

- Ngừng nhận task mới.
- Cho task đang chạy hoàn tất trong một khoảng thời gian hữu hạn nếu phù hợp.
- Hủy hoặc đánh dấu task còn chờ khi shutdown deadline hết.
- Kết thúc RPC đang chờ bằng status/cancellation rõ ràng nếu có thể.
- Không giữ channel, subscription hoặc transaction sau khi context đã đóng.

ThreadPoolTaskExecutor hỗ trợ cấu hình chờ task hoàn tất và thời gian chờ shutdown. Tuy nhiên, không nên chờ vô hạn vì một task blocking có thể treo shutdown. Task phải có deadline/timeout riêng cho dependency.

Với task đã submit cho RPC, lưu trạng thái terminal/cancellation để worker không gửi response sau khi call đã kết thúc. Nếu công việc cần tiếp tục sau khi RPC mất kết nối, chuyển nó thành background job có ID/status API và lifecycle độc lập, không giữ observer của RPC.

## 12. Quan sát executor queue

Các metric quan trọng:

- Pool size, active thread count và core/max size.
- Queue depth và queue remaining capacity.
- Task submit rate, completion rate và rejection count.
- Queue wait time p50/p95/p99.
- Task execution time p50/p95/p99.
- Số task bị bỏ vì deadline đã hết trước khi chạy.
- Số task cancel khi client hủy RPC.
- RPC status RESOURCE_EXHAUSTED/UNAVAILABLE liên quan executor.
- Downstream pool utilization và latency.

Nếu queue depth liên tục gần capacity, task wait tăng và rejection xuất hiện, hệ thống đang ở trạng thái bão hòa. Tăng queue chỉ trì hoãn thời điểm reject và có thể làm deadline miss nhiều hơn.

Gắn metric với executor name và workload group. Tránh dùng request ID, user ID hoặc tenant ID tùy ý làm metric label vì cardinality có thể tăng vô hạn. Có thể ghi tenant/quota tier đã chuẩn hóa trong log hoặc trace khi cần điều tra.

## 13. Kiểm thử bounded queue và rejection

Test nên chứng minh queue không vượt capacity và overload được phản hồi đúng:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Worker còn chỗ | Task chạy |
| Worker bận, queue còn chỗ | Task được enqueue |
| Worker đạt max, queue đầy | Task mới bị reject |
| Rejection trong gRPC handler | Client nhận status theo overload contract |
| Task chờ tới khi deadline hết | Task không chạy business logic |
| Client cancel khi task đang chờ | Task bị loại/hủy nếu có thể |
| Streaming gửi nhanh hơn consumer | Flow control ngăn queue tăng vô hạn |
| Một tenant đạt quota | Tenant khác vẫn có capacity theo policy |
| Shutdown khi queue có task | Task hoàn tất/hủy theo lifecycle đã cấu hình |

Dùng executor nhỏ trong test, ví dụ một worker và queue capacity một. Dùng CountDownLatch để giữ worker bận, submit task thứ hai vào queue và task thứ ba để xác minh rejection. Không dùng Thread.sleep làm cơ chế đồng bộ chính.

Với gRPC integration test, gọi method qua generated stub, xác minh handler nhận RESOURCE_EXHAUSTED khi application executor reject, và xác minh observer chỉ nhận một terminal signal. Test cancellation/deadline phải kiểm tra task không tạo side effect sau khi RPC đã kết thúc.

Với Spring application test, inject ThreadPoolTaskExecutor bean thật, xác minh queue capacity và rejection handler, rồi khởi động server theo cấu hình starter thực tế để kiểm tra wiring.

## 14. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng queue gần như vô hạn | Memory tăng và latency không kiểm soát | Dùng bounded queue |
| Chỉ tăng queue khi reject | Che overload và làm task hết deadline trong queue | Đo throughput, wait time và scale/limit admission |
| Dùng CallerRuns trên gRPC callback thread | Callback thread bị block bởi business task | Dùng AbortPolicy và map rejection |
| Dùng DiscardPolicy cho RPC | Client chờ response tới deadline | Kết thúc call rõ ràng khi reject |
| Chạy blocking task trên server executor | Starve gRPC callback dispatch | Tách application worker executor |
| Submit mọi streaming message không backpressure | Queue đầy và giữ nhiều message | Manual flow control, bounded pending work |
| Không truyền Context/deadline sang worker | Task chạy sau khi RPC hết hạn | Propagate Context và kiểm tra cancellation |
| Dùng chung queue cho workload khác biệt lớn | Workload nặng chặn task nhẹ | Tách pool/admission theo nhu cầu |
| Không đóng executor khi shutdown | Thread và task tồn tại sau application | Quản lý lifecycle và shutdown timeout |
| Không test rejection | Overload behavior không rõ ràng | Test queue full và status thực tế |

## 15. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo ThreadPoolTaskExecutor bean cho công việc blocking do gRPC service gọi.
2. Đặt core size, max size, queue capacity hữu hạn và AbortPolicy.
3. Submit task từ một async gRPC handler; bắt rejection và trả RESOURCE_EXHAUSTED.
4. Truyền Context/deadline vào worker và bỏ task đã hết hạn.
5. Với client-streaming, dùng manual flow control để chỉ nhận message tiếp theo khi worker có capacity.
6. Thêm per-tenant in-flight quota và bounded queue cho workload cần thiết.
7. Thêm metrics queue depth, wait time, execution time và rejection count.
8. Viết test worker bận + queue đầy, RPC rejection, cancellation, deadline, shutdown và Spring bean wiring.

### Câu hỏi tự kiểm tra

**1. Executor queue giới hạn điều gì?**  
Số task đang chờ được executor nhận nhưng chưa được worker thực thi.

**2. Queue capacity có phải số task chạy đồng thời không?**  
Không. Số task chạy phụ thuộc số worker; queue chỉ chứa task chờ.

**3. Vì sao không nên dùng queue vô hạn?**  
Task tích lũy giữ memory và làm queue wait tăng; request có thể hết deadline trước khi chạy.

**4. Rejection policy nào dễ xử lý cho application RPC?**  
AbortPolicy, vì nó báo rejection để service có thể kết thúc call rõ ràng.

**5. Vì sao CallerRunsPolicy nguy hiểm với gRPC callback?**  
Task có thể chạy trực tiếp trên callback/transport-related thread và block việc dispatch RPC khác.

**6. Flow control có thay bounded queue không?**  
Không. Flow control điều tiết message in-flight; bounded queue giới hạn task chờ ở application executor.

**7. Queue wait có nằm trong deadline RPC không?**  
Có. Task chờ trong queue vẫn tiêu thụ ngân sách thời gian của call.

**8. Khi nào cần tách nhiều executor?**  
Khi workload có đặc tính CPU, blocking, latency hoặc downstream capacity khác nhau và việc tách có lợi được đo lường.

## Tổng kết

Giới hạn executor queue kiểm soát số task chờ trong khi worker đang bận. Trong Spring gRPC, cần phân biệt executor dispatch callback của grpc-java với application executor xử lý công việc blocking/CPU-intensive và với executor dùng cho @Async. Dùng bounded queue, chọn pool size theo throughput và tài nguyên, kiểm tra deadline trước khi chạy task, và xử lý rejection rõ ràng. Tránh CallerRuns trên gRPC callback thread; với streaming, kết hợp queue limit với manual flow control và giới hạn pending message. Theo dõi queue depth, wait time, task latency và rejection; kiểm thử queue full, cancellation, deadline và Spring wiring để chứng minh overload được xử lý an toàn.

