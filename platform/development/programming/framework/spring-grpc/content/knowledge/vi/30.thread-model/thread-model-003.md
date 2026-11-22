# Tách blocking call khỏi event loop

**Chương:** Thread model  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng hợp đồng Protocol Buffers, mã Java được sinh và server/client cho unary hoặc streaming RPC. Bài này tập trung vào cách đưa JDBC, HTTP client đồng bộ, SDK và các thao tác blocking khác ra khỏi Netty event loop, đồng thời giữ deadline, cancellation, context và response observer an toàn.

## 1. Vì sao phải tách blocking call?

Netty event loop phục vụ các sự kiện I/O của nhiều channel/stream. Nó cần xử lý nhanh việc đọc socket, ghi socket và điều phối frame HTTP/2. Nếu một event-loop thread bị giữ bởi một thao tác chờ lâu, các sự kiện của những kết nối khác do event loop đó quản lý cũng có thể bị trì hoãn.

Các thao tác thường gây blocking:

- JDBC/JPA đồng bộ: chờ connection, query hoặc transaction.
- HTTP client đồng bộ: chờ DNS, kết nối, response body.
- SDK của dịch vụ bên thứ ba: chờ network hoặc lock nội bộ.
- Đọc/ghi file hoặc object storage bằng API đồng bộ.
- Chờ `Future.get()`, `CompletableFuture.join()`, `CountDownLatch.await()` hoặc `Thread.sleep()`.
- Giữ monitor/lock trong khi chờ một dependency.

Một RPC có thể chỉ mất 300 ms chờ database, nhưng nếu nó chạy trên event loop đang phục vụ nhiều channel, tác động không giới hạn ở RPC đó. Latency tăng, client hết deadline và retry, tạo thêm tải lên hệ thống đang nghẽn.

**Nguyên tắc:** event loop xử lý transport I/O; blocking work phải chạy trên một executor phù hợp, có giới hạn và có timeout.

## 2. Phân biệt event loop với server application executor

Không nên mặc định mọi handler Spring gRPC đều chạy trên Netty event loop. Trong cấu hình gRPC Java Netty thông thường, transport dùng event loop cho I/O, còn callback ứng dụng được điều phối trên server application executor. Hai nhóm thread có vai trò khác nhau:

| Thread/executor | Trách nhiệm | Blocking có tác động gì? |
| --- | --- | --- |
| Netty event loop | Socket, HTTP/2 frame, transport events | Có thể làm trễ nhiều channel/stream trên event loop |
| Server application executor | Service method và server listener callbacks | Chiếm worker, làm callback khác xếp hàng |
| Blocking I/O worker pool | JDBC/HTTP/SDK đồng bộ do ứng dụng offload | Chiếm capacity của pool riêng; cần giới hạn và timeout |
| CPU executor | Mã hóa, nén, tính toán nặng | Chiếm CPU worker; cần giới hạn concurrency |

Vì vậy, trước khi offload cần xác định callback đang chạy ở đâu:

- Nếu dùng server executor riêng, handler blocking làm cạn application worker; một pool I/O riêng có thể cô lập tải.
- Nếu cấu hình `directExecutor()` hoặc tự gọi blocking code từ callback chạy trên transport thread, blocking có thể giữ event loop.
- Nếu một interceptor, callback hoặc adapter tùy biến chạy trực tiếp trên event loop, nó cũng phải tránh blocking.

Không cần chuyển mọi dòng code khỏi handler. Validation ngắn, ánh xạ protobuf và logic CPU rất nhỏ có thể chạy trên application executor. Mục tiêu là tách các thao tác chờ lâu hoặc có thời gian thực thi khó dự đoán.

### Cẩn thận với directExecutor

`directExecutor()` yêu cầu gRPC chạy callback trực tiếp trên thread đang gọi executor. Với Netty transport, thread đó có thể là transport/event-loop thread. Chế độ này giảm chi phí chuyển thread cho callback rất ngắn, nhưng không phù hợp với handler gọi JDBC hoặc HTTP đồng bộ.

Không bật direct executor chỉ để “tăng tốc” khi chưa đo tải. Nếu dùng, callback phải ngắn, không block và không chờ một future hoàn tất.

## 3. Chọn cách tách blocking work

Có ba hướng chính:

1. **Dedicated bounded worker pool:** phù hợp khi phải dùng JDBC, SDK hoặc HTTP client đồng bộ. Pool và queue hữu hạn giúp giới hạn số công việc đang chờ.
2. **Non-blocking client/API:** dùng HTTP client async, reactive data access hoặc gRPC async stub để không giữ thread trong lúc chờ I/O. Không gọi `get()` hoặc `join()` để biến API async thành blocking.
3. **Virtual threads:** có thể hữu ích cho workload blocking trong runtime hỗ trợ, nhưng vẫn cần giới hạn concurrency và bảo vệ database/downstream. Virtual thread không làm tăng capacity của dependency và không nên được dùng để block Netty event loop.

Không có một giải pháp duy nhất cho mọi workload. JDBC đồng bộ thường cần worker pool hoặc virtual-thread-per-task executor có semaphore/connection limits; CPU-intensive work cần pool CPU riêng.

## 4. Tạo bounded worker pool cho blocking I/O

Ví dụ cấu hình một pool chuyên phục vụ thao tác I/O của customer service:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

@Configuration
public class BlockingIoConfiguration {

    @Bean(destroyMethod = "shutdown")
    public ExecutorService customerBlockingExecutor() {
        AtomicInteger sequence = new AtomicInteger();
        ThreadFactory threadFactory = task -> {
            Thread thread = new Thread(
                    task,
                    "customer-blocking-" + sequence.incrementAndGet());
            thread.setDaemon(false);
            return thread;
        };

        return new ThreadPoolExecutor(
                12,
                12,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(200),
                threadFactory,
                new ThreadPoolExecutor.AbortPolicy());
    }
}
```

Các con số chỉ là ví dụ; chọn kích thước theo throughput, thời gian chờ, giới hạn connection pool và tải downstream. Nếu database chỉ cho phép 20 connection đồng thời, tạo hàng trăm worker cùng gọi database không làm query nhanh hơn; nó chỉ tạo thêm hàng đợi và timeout.

### Vì sao queue phải hữu hạn?

- Queue vô hạn giữ request quá tải trong thời gian dài, làm tăng memory và latency.
- Queue hữu hạn tạo điểm từ chối sớm khi hệ thống đã hết capacity.
- `AbortPolicy` báo `RejectedExecutionException` để adapter chuyển overload thành status rõ ràng.
- Không dùng `CallerRunsPolicy` cho blocking task: khi pool đầy, task có thể chạy ngay trên thread submitter, vốn có thể là thread callback nhạy cảm hoặc event loop.
- Không dùng `DiscardPolicy` hoặc `DiscardOldestPolicy` nếu việc bỏ task khiến RPC không bao giờ được kết thúc.

Khi queue đầy, server có thể trả `RESOURCE_EXHAUSTED` hoặc status overload đã được quy định trong hợp đồng. Không nhận task rồi để RPC treo.

## 5. Offload blocking call trong Spring gRPC handler

Handler kiểm tra request nhanh, capture gRPC Context, rồi submit thao tác blocking sang worker pool. Ví dụ unary RPC:

```java
import io.grpc.Context;
import io.grpc.ServerCallStreamObserver;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.beans.factory.annotation.Qualifier;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;

@GrpcService
public class CustomerGrpcService
        extends CustomerServiceGrpc.CustomerServiceImplBase {

    private final CustomerApplicationService applicationService;
    private final Executor customerBlockingExecutor;
    private final GrpcExceptionMapper exceptionMapper;

    public CustomerGrpcService(
            CustomerApplicationService applicationService,
            @Qualifier("customerBlockingExecutor")
                    Executor customerBlockingExecutor,
            GrpcExceptionMapper exceptionMapper) {
        this.applicationService = applicationService;
        this.customerBlockingExecutor = customerBlockingExecutor;
        this.exceptionMapper = exceptionMapper;
    }

    @Override
    public void getCustomer(
            GetCustomerRequest request,
            StreamObserver<Customer> responseObserver) {

        ServerCallStreamObserver<Customer> serverObserver =
                (ServerCallStreamObserver<Customer>) responseObserver;
        Context callContext = Context.current();
        AtomicBoolean cancelled = new AtomicBoolean(
                callContext.isCancelled());
        AtomicBoolean terminated = new AtomicBoolean(false);

        serverObserver.setOnCancelHandler(() -> cancelled.set(true));
        Executor contextAwareExecutor =
                callContext.fixedContextExecutor(customerBlockingExecutor);

        try {
            contextAwareExecutor.execute(() -> {
                if (cancelled.get() || callContext.isCancelled()) {
                    return;
                }

                try {
                    Customer customer = applicationService.findBlocking(
                            request.getCustomerId());

                    if (cancelled.get() || callContext.isCancelled()) {
                        return;
                    }
                    if (terminated.compareAndSet(false, true)) {
                        responseObserver.onNext(toProto(customer));
                        responseObserver.onCompleted();
                    }
                } catch (Exception failure) {
                    if (!cancelled.get()
                            && !callContext.isCancelled()
                            && terminated.compareAndSet(false, true)) {
                        responseObserver.onError(
                                exceptionMapper.map(failure));
                    }
                }
            });
        } catch (RejectedExecutionException overloaded) {
            if (terminated.compareAndSet(false, true)) {
                responseObserver.onError(
                        Status.RESOURCE_EXHAUSTED
                                .withDescription(
                                        "Server is temporarily at capacity")
                                .asRuntimeException());
            }
        }
    }
}
```

Đây là mẫu unary có một task worker và một nơi phát terminal response. Các import, mapper và bean cần khớp với ứng dụng. Những điểm quan trọng:

- Handler trả về nhanh sau khi submit task; JDBC/SDK blocking chạy trên pool riêng.
- `fixedContextExecutor` gắn lại gRPC Context đã capture, để worker đọc được deadline, cancellation và dữ liệu theo RPC.
- Cancellation handler chỉ đặt cờ; nó không gọi response observer từ thread cancellation.
- `terminated` ngăn các nhánh cạnh tranh phát nhiều terminal signal.
- Rejection được xử lý ngay bằng status overload; không dùng caller-runs.

`StreamObserver` không được mặc định là thread-safe. Nếu nhiều worker có thể gửi response, phải tuần tự hóa các lời gọi `onNext`, `onError` và `onCompleted`. Với unary một worker, chỉ worker đó phát response; callback cancellation chỉ cập nhật cờ.

Cancellation có thể xảy ra đúng lúc worker đang hoàn tất. Kiểm tra cờ giảm công việc thừa nhưng không biến cancellation thành thao tác đồng bộ tuyệt đối; transport vẫn có thể đã đóng call trước khi worker kịp gửi. Vì vậy, cần giữ terminal state, timeout dependency và xử lý lỗi khi call đã kết thúc.

## 6. Deadline phải đi theo blocking operation

Offload sang worker không được làm mất deadline của caller. Capture `Context` trước khi submit và lấy deadline còn lại trong worker:

```java
import io.grpc.Context;
import io.grpc.Deadline;
import io.grpc.Status;
import java.util.concurrent.TimeUnit;

Deadline deadline = Context.current().getDeadline();
long configuredLimitNanos =
        TimeUnit.SECONDS.toNanos(2);
long cleanupReserveNanos =
        TimeUnit.MILLISECONDS.toNanos(50);

long usableBudgetNanos = configuredLimitNanos;
if (deadline != null) {
    long remainingNanos =
            deadline.timeRemaining(TimeUnit.NANOSECONDS);
    usableBudgetNanos = Math.min(
            configuredLimitNanos,
            remainingNanos - cleanupReserveNanos);
}

if (usableBudgetNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Request deadline exceeded")
            .asRuntimeException();
}
```

Sau đó áp dụng ngân sách cho dependency:

- Downstream gRPC: `stub.withDeadlineAfter(usableBudgetNanos, NANOSECONDS)`.
- HTTP client: connect, response và read timeout không vượt ngân sách còn lại.
- JDBC: query/statement timeout và transaction timeout phù hợp với độ phân giải driver.
- SDK bên ngoài: cấu hình timeout riêng nếu SDK hỗ trợ.

Đừng để RPC có deadline 800 ms gọi HTTP client với timeout 10 giây. Khi client đã hết thời gian chờ, worker vẫn có thể giữ thread và connection nếu dependency không có timeout riêng.

Nếu không có deadline từ caller, vẫn đặt timeout tối đa của service. Không dùng deadline null làm lý do cho phép một blocking call chạy vô hạn.

## 7. Cancellation không tự dừng mọi blocking API

Khi client hủy RPC hoặc deadline hết, gRPC Context được đánh dấu cancelled. Worker cần kiểm tra trạng thái này trước khi bắt đầu thao tác mới và sau khi dependency trả kết quả. Tuy nhiên:

- JDBC driver có thể cần query timeout hoặc statement cancel.
- HTTP client cần API cancel riêng.
- SDK có thể không hỗ trợ interruption.
- `Future.cancel(true)` chỉ gửi interrupt; code và thư viện phải hợp tác với interrupt.

Nếu ứng dụng giữ `Future` hoặc handle của task, cancellation handler có thể yêu cầu hủy task. Dù vậy, timeout ở chính dependency vẫn cần thiết vì interrupt không đảm bảo dừng socket/database call ngay lập tức.

Không gọi `onNext`, `onError` hoặc `onCompleted` sau khi call đã bị hủy. Khi cleanup, giải phóng resource và transaction; không commit một thao tác chỉ vì worker đã chạy đến cuối nếu deadline/cancellation policy yêu cầu dừng.

## 8. Khi nào nên dùng API non-blocking?

Nếu downstream đã cung cấp API bất đồng bộ, thường không cần giữ một worker thread chỉ để chờ:

```java
import java.util.concurrent.CompletionStage;

CompletionStage<Customer> result =
        customerClient.findAsync(customerId);

result.whenCompleteAsync((customer, failure) -> {
    if (failure != null) {
        responseObserver.onError(exceptionMapper.map(failure));
        return;
    }
    responseObserver.onNext(toProto(customer));
    responseObserver.onCompleted();
}, responseExecutor);
```

Ví dụ dùng `whenCompleteAsync` để chọn executor chạy callback. Trong code thực tế cần thêm cancellation propagation, deadline và terminal guard giống mẫu worker pool. Không gọi `result.get()` hoặc `result.join()` trong handler; làm vậy sẽ biến API async thành blocking.

Non-blocking không đồng nghĩa không giới hạn concurrency. Cần kiểm soát số request đang bay, memory của pending future và backpressure tới dependency.

## 9. Streaming cần thêm flow control

Đối với server streaming hoặc bidirectional streaming, tách blocking producer khỏi event loop mới giải quyết vị trí chạy; nó không tự điều tiết tốc độ gửi.

Dùng `ServerCallStreamObserver.isReady()` và `setOnReadyHandler()` để producer chỉ phát khi transport sẵn sàng:

```java
import io.grpc.stub.ServerCallStreamObserver;

ServerCallStreamObserver<Update> serverObserver =
        (ServerCallStreamObserver<Update>) responseObserver;

serverObserver.setOnReadyHandler(() -> {
    while (serverObserver.isReady() && hasNextUpdate()) {
        serverObserver.onNext(nextUpdate());
    }
});

serverObserver.setOnCancelHandler(this::stopProducer);
```

Đây là phác thảo: producer thực tế phải bảo đảm chỉ một thread phát message trên observer tại một thời điểm. Nếu `onReady` schedule producer sang worker, cần serialize các lần chạy và dừng producer khi cancellation. Flow control điều tiết outbound messages; worker pool giới hạn công việc blocking. Hai cơ chế bổ sung cho nhau.

Với client streaming, nếu mỗi `onNext` cần gọi database đồng bộ, không nên block callback thread. Có thể đưa từng message vào worker queue, nhưng phải giới hạn số message đang chờ và giữ đúng thứ tự nếu nghiệp vụ yêu cầu. Khi queue đầy, áp dụng policy rõ ràng: từ chối call, dừng nhận hoặc điều tiết upstream; không xếp hàng vô hạn.

## 10. Tránh các lỗi thiết kế phổ biến

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi JDBC trên Netty event loop | Chặn I/O của nhiều channel | Offload sang worker pool |
| Dùng direct executor cho handler blocking | Callback có thể chạy trên transport thread | Dùng application executor phù hợp |
| Worker pool không giới hạn | Thread/queue tăng quá mức, downstream bị quá tải | Pool và queue hữu hạn |
| Dùng CallerRunsPolicy | Blocking task có thể chạy trên thread submitter nhạy cảm | Dùng AbortPolicy và map rejection |
| Dùng DiscardPolicy | RPC có thể không bao giờ kết thúc | Báo overload rõ ràng |
| Chờ future bằng get/join | Giữ thread trong khi chờ I/O | Compose callback/CompletionStage |
| Không truyền deadline | Worker tiếp tục chạy sau khi caller hết hạn | Truyền timeout xuống dependency |
| Chỉ dựa vào interrupt | Blocking driver có thể không dừng | Timeout/cancel API ở dependency |
| Nhiều worker gọi observer đồng thời | Response order và terminal signal không xác định | Serialize output và bảo vệ terminal state |
| Offload streaming mà không flow control | Producer có thể tích lũy message quá nhanh | Dùng readiness/backpressure |

## 11. Kiểm thử và quan sát

### Kiểm thử tách thread

Với Netty transport thực, ghi nhận thread name trong handler và trong blocking operation. Dùng prefix như `customer-blocking-` để xác nhận thao tác đã được offload. In-process transport hữu ích cho status/lifecycle nhưng không chứng minh hành vi của Netty event loop; bài test thread isolation cần chạy với transport Netty.

### Kiểm thử overload, deadline và cancellation

| Ca | Kỳ vọng |
| --- | --- |
| Worker pool còn capacity | Blocking operation chạy trên worker thread |
| Worker queue đầy | RPC kết thúc sớm bằng status overload đã quy định |
| Caller deadline ngắn hơn dependency timeout mặc định | Timeout dependency được rút theo ngân sách caller |
| Client hủy khi task đang chờ queue | Task bỏ qua công việc nếu cancellation đã được nhận biết |
| Client hủy khi JDBC đang chạy | Statement/query được timeout hoặc cancel theo khả năng driver |
| Worker ném exception | Mapper chuyển thành status; RPC không treo |
| Hai nhánh cùng cố kết thúc | Chỉ một terminal response được phát |
| Streaming client đọc chậm | Producer tôn trọng readiness/backpressure |

### Metrics cần theo dõi

- Active thread, queue depth và rejection count của blocking pool.
- Thời gian chờ trong queue tách biệt với thời gian thực thi.
- JDBC connection pool active/idle/pending và query latency.
- HTTP/downstream connection pool, timeout và cancellation rate.
- Số RPC hết deadline trong khi worker vẫn đang chạy.
- Netty event-loop CPU và transport latency.
- Số message streaming bị trì hoãn vì not-ready.

Nếu worker queue tăng nhưng event loop vẫn khỏe, bottleneck nằm ở application/dependency capacity. Nếu event-loop CPU hoặc I/O latency tăng bất thường, kiểm tra xem có callback tùy biến hoặc direct executor đang chạy blocking trên transport thread hay không.

## 12. Tự luyện tập

1. Trong cấu hình gRPC Netty mặc định, vì sao cần phân biệt server application executor với Netty event loop trước khi quyết định offload?
2. Vì sao `CallerRunsPolicy` có thể đưa blocking call trở lại thread mà ta đang cố bảo vệ?
3. Thiết kế bounded worker pool cho JDBC với queue hữu hạn và status khi bị reject.
4. Một client hủy RPC khi JDBC query đang chạy. Cần kết hợp gRPC Context, query timeout và statement cancellation như thế nào?
5. Với client streaming, làm thế nào giới hạn số message đang chờ worker mà vẫn giữ thứ tự xử lý?

**Ghi nhớ:** Tách blocking call khỏi event loop bằng cách giữ Netty event loop cho transport I/O và chuyển JDBC/HTTP/SDK đồng bộ sang worker pool hữu hạn hoặc API non-blocking. Không dùng `directExecutor()` cho handler blocking, không dùng `CallerRunsPolicy`, và luôn truyền deadline/cancellation xuống dependency. Với streaming, phải kết hợp worker isolation với flow control và serialize response observer.
