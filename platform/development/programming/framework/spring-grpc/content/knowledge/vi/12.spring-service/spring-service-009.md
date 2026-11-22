# Blocking handler và thread model

## Mục tiêu bài học

Trong **SPRING_GRPC**, một RPC handler có thể gọi repository JPA, HTTP client hoặc một gRPC service khác. Những lời gọi này thường chờ I/O. Nếu hiểu sai thread model, một handler chậm có thể chiếm hết luồng xử lý RPC, làm request khác phải chờ và tăng tỷ lệ timeout.

Bài học này tập trung vào **blocking handler và thread model**: phân biệt luồng I/O của transport với executor chạy callback ứng dụng, hiểu chi phí của thao tác blocking, biết khi nào xử lý đồng bộ là hợp lý và khi nào cần offload sang executor có giới hạn.

Sau bài này, bạn có thể:

1. Phân biệt Netty event loop, gRPC application executor và executor nghiệp vụ của Spring.
2. Giải thích vì sao một RPC handler blocking chiếm worker trong thời gian chờ dependency.
3. Chọn cách xử lý đồng bộ hoặc bất đồng bộ dựa trên đặc tính công việc.
4. Offload I/O blocking bằng executor có giới hạn, hàng đợi và chính sách từ chối rõ ràng.
5. Giữ gRPC Context, cancellation và thứ tự ghi response khi chuyển sang thread khác.
6. Xử lý streaming mà không giữ worker hoặc phát dữ liệu vô hạn.
7. Đo queueing, thời gian dependency, saturation và deadline để tìm nút thắt.

> **Phạm vi:** Ví dụ dùng gRPC Java với Spring gRPC chính thức. Chi tiết cấu hình server executor phụ thuộc server factory và phiên bản thư viện; bài không giả định một property Spring cụ thể cho mọi transport.

## 1. Ba nhóm thread cần phân biệt

Trong server gRPC chạy trên Netty, các công việc thường được phân chia thành nhiều nhóm:

| Nhóm | Nhiệm vụ | Điều cần tránh |
| --- | --- | --- |
| **Transport event loop** | Nhận/gửi dữ liệu mạng, xử lý sự kiện socket và HTTP/2 frame | Không chạy truy vấn DB, gọi HTTP đồng bộ hoặc tác vụ kéo dài trên event loop |
| **gRPC application executor** | Thực thi callback service như method unary hoặc callback nhận message stream | Không để toàn bộ worker bị chiếm bởi I/O chờ lâu mà không có giới hạn |
| **Executor nghiệp vụ** | Chạy tác vụ blocking hoặc công việc CPU được tách riêng theo chính sách ứng dụng | Không dùng pool vô hạn hoặc chia sẻ tùy tiện với các tác vụ không liên quan |

Transport event loop không đồng nghĩa với thread chạy method `getProduct(...)`. Trong cấu hình server thông thường, gRPC dispatch callback ứng dụng qua executor riêng. Tuy nhiên, cấu hình low-level `directExecutor()` có thể chạy callback trực tiếp trên thread xử lý transport. Vì vậy, không bao giờ dựa vào giả định rằng mọi handler đều được cách ly khỏi event loop; hãy kiểm tra cấu hình server thực tế.

Trong gRPC Java, `ServerBuilder.executor(...)` là điểm cấu hình executor cho callback ứng dụng ở cấp builder. Spring gRPC tạo server thông qua server factory; cách tùy chỉnh executor phụ thuộc factory/transport và phiên bản đang dùng. Khi cần thay đổi, hãy dùng extension point được tài liệu của phiên bản đó hỗ trợ, không tự đặt một property chưa được xác nhận.

## 2. Blocking handler tiêu thụ worker như thế nào?

Ví dụ unary handler gọi service đồng bộ:

```java
@GrpcService
public class ProductGrpcEndpoint
        extends ProductGrpc.ProductImplBase {

    private final ProductService service;

    public ProductGrpcEndpoint(ProductService service) {
        this.service = service;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<ProductReply> responses) {
        try {
            // Lời gọi repository/JPA đồng bộ có thể chờ database.
            ProductView product = service.getProduct(request.getProductId());

            responses.onNext(toProto(product));
            responses.onCompleted();
        } catch (ProductNotFoundException ex) {
            responses.onError(Status.NOT_FOUND
                    .withDescription("Không tìm thấy sản phẩm")
                    .asRuntimeException());
        }
    }
}
```

Khi callback `getProduct` bắt đầu, một application worker thực thi method. Nếu `service.getProduct(...)` chờ database 180 ms, worker đó không thể đồng thời xử lý callback khác trong cùng thread. Khi lời gọi trả về, handler map response và kết thúc.

Điều này **không mặc nhiên là lỗi**. Một handler đồng bộ, thời gian ngắn và có giới hạn có thể đơn giản, dễ đọc và đủ hiệu quả. Vấn đề xuất hiện khi số RPC đồng thời lớn, thời gian chờ không ổn định hoặc pool không đủ khả năng hấp thụ độ trễ.

### 2.1. Ước lượng tác động của thời gian chờ

Giả sử executor có 16 worker và mỗi handler trung bình giữ worker 200 ms. Nếu tất cả worker đều bận gần như liên tục, năng lực xử lý thô theo số worker xấp xỉ:

```text
16 worker / 0,2 giây ≈ 80 lần xử lý mỗi giây
```

Đây chỉ là ước lượng để hiểu mức độ chiếm dụng, không phải throughput cam kết. Thời gian queue, CPU, serialization, database connection pool, lock contention và độ phân tán latency đều làm kết quả thực tế khác đi.

Khi tất cả worker đều bận:

1. Callback mới phải chờ trong queue hoặc bị từ chối theo chính sách executor.
2. Thời gian chờ queue cộng với thời gian xử lý làm tăng RPC latency.
3. Deadline của client có thể hết trước khi handler được chạy hoặc trước khi dependency trả kết quả.
4. Retry không kiểm soát có thể làm tải tăng thêm và tạo vòng lặp quá tải.

### 2.2. Không phải cứ handler đồng bộ là phải offload

Giữ handler đồng bộ thường phù hợp khi:

- Use case ngắn và có thời gian tối đa dự đoán được.
- Dependency có timeout rõ ràng.
- Executor server được sizing theo tải và có khả năng quan sát.
- Việc offload sẽ thêm queue, context propagation và đồng bộ hóa mà không mang lại lợi ích rõ ràng.

Cân nhắc offload khi:

- Handler gọi hệ thống blocking có latency cao hoặc biến động.
- Cần tách tải I/O khỏi executor callback của gRPC.
- Muốn giới hạn số tác vụ blocking đồng thời độc lập với transport.
- Có chính sách overload, timeout và cancellation cụ thể.

Không offload chỉ vì muốn method trông “bất đồng bộ”. Offload không làm dependency nhanh hơn; nó chỉ chuyển nơi tiêu thụ thread và giúp kiểm soát tài nguyên nếu pool được thiết kế đúng.

## 3. Nhận diện các nguồn blocking thường gặp

| Lệnh/công việc | Vì sao có thể blocking? | Cách kiểm soát |
| --- | --- | --- |
| Spring Data JPA/JDBC | Chờ lấy connection, query, lock hoặc database response | Giới hạn connection pool, query timeout, chỉ mục và thời gian transaction |
| HTTP client đồng bộ | Chờ DNS, connect, response hoặc body | Connect/read timeout, connection pool, deadline và circuit breaker |
| gRPC blocking stub | Chờ response từ downstream | Dùng deadline trên từng call; phân loại DEADLINE_EXCEEDED/UNAVAILABLE |
| File I/O | Chờ filesystem hoặc thiết bị lưu trữ | Giới hạn concurrency, timeout khi phù hợp, dùng API phù hợp |
| `Thread.sleep()`/chờ lock | Giữ thread mà không xử lý công việc khác | Loại bỏ chờ nhân tạo; rút ngắn critical section |
| Tính toán CPU nặng | Không chờ I/O nhưng chiếm CPU | Đo CPU; cân nhắc CPU executor riêng, giới hạn concurrency |
| `Future.get()` hoặc `join()` | Thread hiện tại chờ kết quả chưa hoàn thành | Kết hợp async end-to-end hoặc dùng blocking pool có giới hạn |

Một handler gọi nhiều dependency nối tiếp sẽ giữ worker trong tổng thời gian chờ của các dependency. Nếu các lời gọi độc lập, có thể cân nhắc thực hiện song song, nhưng chỉ khi có giới hạn concurrency và kết quả có thể kết hợp an toàn. Không dùng `parallelStream()` hoặc common pool như một cách offload mặc định.

## 4. Mô hình A: xử lý đồng bộ trên RPC application executor

Đây là mô hình đơn giản nhất: handler gọi application service, chờ kết quả rồi gửi response.

```java
@Override
public void getProduct(
        GetProductRequest request,
        StreamObserver<ProductReply> responses) {
    try {
        ProductView view = service.getProduct(request.getProductId());
        responses.onNext(toProto(view));
        responses.onCompleted();
    } catch (ProductNotFoundException ex) {
        responses.onError(Status.NOT_FOUND
                .withDescription("Không tìm thấy sản phẩm")
                .asRuntimeException());
    } catch (RuntimeException ex) {
        log.error("getProduct failed", ex);
        responses.onError(Status.INTERNAL
                .withDescription("Không thể xử lý yêu cầu")
                .asRuntimeException());
    }
}
```

Mô hình này có ưu điểm: luồng điều khiển tuần tự, không cần quản lý callback hoàn tất ở thread khác, và transaction của application service có thể kết thúc trước khi adapter gửi response nếu transaction được đặt đúng ở service.

Nhưng phải kiểm soát thời gian chờ ở mọi dependency. Nếu handler có thể chờ vô hạn, executor có thể cạn worker dù lượng request không lớn. Deadline phía client không tự động bảo đảm một JDBC query đang chạy sẽ bị dừng ngay lập tức; cần timeout hoặc cơ chế hủy ở tầng database/client.

## 5. Mô hình B: offload blocking I/O sang executor có giới hạn

Khi công việc blocking cần được tách khỏi gRPC application executor, dùng một pool chuyên biệt. Pool cần giới hạn cả số thread và hàng đợi để hệ thống có điểm dừng rõ ràng khi quá tải.

### 5.1. Khai báo Spring executor

Ví dụ cấu hình một `ThreadPoolTaskExecutor` cho các thao tác blocking:

```java
@Configuration
public class GrpcWorkExecutorConfiguration {

    @Bean(name = "grpcBlockingExecutor")
    public ThreadPoolTaskExecutor grpcBlockingExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("grpc-blocking-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

Các con số chỉ là giá trị khởi đầu minh họa. Cần chọn theo thời gian dependency, giới hạn connection pool và tải đo được. Nếu database chỉ cho phép 12 connection dành cho workload này, tạo 50 worker blocking có thể chỉ làm tăng số thread chờ connection. Queue lớn cũng làm request nằm chờ lâu và có thể hết deadline trước khi bắt đầu.

### 5.2. Gửi công việc sang pool và hoàn tất response

Đoạn sau minh họa unary RPC. `Context` được chụp trước khi offload và bọc callback hoàn tất để callback nhìn thấy context của RPC ban đầu.

```java
@GrpcService
public class ProductGrpcEndpoint
        extends ProductGrpc.ProductImplBase {

    private final ProductService service;
    private final Executor blockingExecutor;

    public ProductGrpcEndpoint(
            ProductService service,
            @Qualifier("grpcBlockingExecutor") Executor blockingExecutor) {
        this.service = service;
        this.blockingExecutor = blockingExecutor;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<ProductReply> responses) {

        Context rpcContext = Context.current();

        try {
            CompletableFuture
                    .supplyAsync(
                            () -> service.getProduct(request.getProductId()),
                            blockingExecutor)
                    .whenComplete((product, failure) ->
                            rpcContext.wrap(() -> {
                                if (rpcContext.isCancelled()) {
                                    return;
                                }

                                if (failure != null) {
                                    responses.onError(toStatus(failure));
                                    return;
                                }

                                responses.onNext(toProto(product));
                                responses.onCompleted();
                            }).run());
        } catch (RejectedExecutionException ex) {
            responses.onError(Status.RESOURCE_EXHAUSTED
                    .withDescription("Máy chủ đang quá tải")
                    .asRuntimeException());
        }
    }

    private Throwable toStatus(Throwable failure) {
        Throwable cause = failure;
        while (cause instanceof CompletionException
                && cause.getCause() != null) {
            cause = cause.getCause();
        }

        if (cause instanceof ProductNotFoundException) {
            return Status.NOT_FOUND
                    .withDescription("Không tìm thấy sản phẩm")
                    .asRuntimeException();
        }

        log.error("getProduct failed", cause);
        return Status.INTERNAL
                .withDescription("Không thể xử lý yêu cầu")
                .asRuntimeException();
    }
}
```

Đây là ví dụ cấu trúc; cần bổ sung import và mapper theo dự án. Khi `supplyAsync` được submit, handler trả về nhanh; blocking work chạy trên `grpc-blocking-*`. Khi future hoàn tất, callback gửi response. Nếu pool từ chối task, adapter trả `RESOURCE_EXHAUSTED` thay vì tạo thêm thread vô hạn.

**Lưu ý quan trọng:**

- `CompletableFuture` không tự làm tác vụ blocking có thể hủy. `cancel(true)` cũng không bảo đảm JDBC hoặc thư viện bên dưới dừng ngay.
- `Context.wrap(...)` giúp khôi phục gRPC Context trong callback, nhưng không tự làm mọi ThreadLocal của ứng dụng được truyền sang thread khác. Security context, tracing và MDC cần cơ chế propagation phù hợp.
- Khi client hủy RPC, ví dụ kiểm tra `rpcContext.isCancelled()` trước khi gửi response. Công việc blocking có thể vẫn đang chạy; hãy đặt timeout ở database/downstream và dùng API hỗ trợ cancellation nếu có.
- `StreamObserver` không nên được gọi đồng thời từ nhiều thread. Với một future hoàn tất duy nhất, callback trên chỉ có một đường ghi. Nếu có nhiều nguồn kết quả, cần serialize các lần `onNext`, `onError` và `onCompleted`.
- Không để callback lỗi phát sinh sau khi observer đã kết thúc. Mọi nhánh terminal phải được bảo vệ để chỉ kết thúc một lần.

### 5.3. Tách pool theo loại công việc

Không nhất thiết chỉ có một executor. Nếu workload gồm I/O blocking và CPU nặng, có thể tách:

| Pool | Đặc tính | Ví dụ |
| --- | --- | --- |
| I/O blocking pool | Nhiều thời gian chờ; số worker dựa trên giới hạn dependency | JDBC, HTTP client đồng bộ |
| CPU pool | Số worker thường gần năng lực CPU; tránh oversubscription | Mã hóa, tính toán thuần CPU |
| gRPC application executor | Chạy callback và điều phối RPC | Validate request, gọi nhanh application service, quản lý observer |

Không chuyển mọi thao tác sang I/O pool. Validation nhỏ, mapping Protobuf và logic rất ngắn có thể chạy ngay trên callback executor. Mục tiêu là cô lập công việc blocking có chủ đích, không tạo thêm một tầng queue cho từng dòng code.

## 6. Deadline, cancellation và context khi đổi thread

### 6.1. Deadline không phải timeout tự động cho mọi dependency

Deadline gRPC giới hạn thời gian client chờ RPC. Khi deadline hết, server nhận tín hiệu cancellation trong context. Nhưng nếu handler đang ở trong một lệnh JDBC hoặc HTTP client không có timeout, lệnh đó có thể tiếp tục chạy sau khi client đã bỏ cuộc.

Vì vậy cần đặt ngân sách ở từng tầng:

1. RPC deadline giới hạn toàn bộ lời gọi từ góc nhìn client.
2. Database query/transaction timeout giới hạn thời gian chờ DB.
3. HTTP/gRPC downstream deadline nhỏ hơn phần ngân sách còn lại.
4. Công việc nền kiểm tra cancellation và dừng sớm khi API hỗ trợ.

Không đặt timeout cho downstream dài hơn deadline còn lại của RPC. Cũng không retry mù quáng một lệnh ghi khi không biết lần gọi trước đã commit hay chưa; cần idempotency.

### 6.2. gRPC Context không tự truyền sang executor

`Context.current()` chỉ trả context gắn với thread đang chạy tại thời điểm gọi. Khi offload sang thread pool, không được giả định context sẽ tự xuất hiện ở thread mới. Chụp context trước khi submit và dùng `context.wrap(...)` hoặc executor có context propagation của gRPC.

Context có thể mang deadline, cancellation và metadata đã được interceptor đưa vào. Với Spring Security, tracing hoặc MDC, dùng cơ chế propagation tương ứng; gRPC Context và các ThreadLocal khác là những cơ chế riêng.

### 6.3. Cancellation cần hợp tác từ dependency

Khi cancellation xảy ra:

- Không gửi response mới nếu RPC đã bị hủy.
- Dừng vòng lặp đọc/ghi hoặc subscription nếu nguồn dữ liệu hỗ trợ hủy.
- Dùng query timeout, HTTP call timeout hoặc downstream deadline để giới hạn tác vụ đang chờ.
- Giải phóng tài nguyên khi hoàn tất hoặc bị hủy.
- Không coi việc client hủy là bằng chứng rằng thao tác ghi chắc chắn chưa commit.

Nếu thao tác ghi đã commit trước lúc cancellation được xử lý, client có thể không nhận response nhưng dữ liệu vẫn thay đổi. Request ghi quan trọng nên có idempotency key và cơ chế tra cứu kết quả để retry an toàn.

## 7. Thread model trong streaming RPC

### 7.1. Server streaming

Một handler server streaming đồng bộ có thể phát nhiều response trong vòng lặp. Nếu mỗi vòng lặp đọc database hoặc gọi downstream blocking, application worker bị giữ trong suốt thời gian đó.

Với stream dài, nên đọc theo page/chunk bằng thao tác có giới hạn, sau đó phát dữ liệu theo flow control. `ServerCallStreamObserver` cung cấp `isReady()` và `setOnReadyHandler(...)` để ứng dụng biết khi nào transport sẵn sàng nhận thêm dữ liệu. Cũng có thể đăng ký `setOnCancelHandler(...)` để dừng nguồn dữ liệu khi client hủy.

Nguyên tắc là **một luồng ghi tuần tự cho mỗi observer**. Không để callback `onReady` và một worker khác cùng gọi `onNext` không đồng bộ mà thiếu cơ chế serialize.

### 7.2. Client streaming

Method handler thường trả về `StreamObserver<Request>` ngay để nhận các message tiếp theo. Callback `onNext` có thể được gọi nhiều lần; nếu mỗi lần xử lý đều chờ database, callback executor có thể bị giữ lâu.

Có thể xử lý theo chunk hoặc đưa tác vụ vào bounded executor, nhưng cần giữ thứ tự nếu giao thức yêu cầu. Không tạo một future độc lập cho mỗi message mà không giới hạn số task đang chờ; nếu client gửi nhanh hơn tốc độ xử lý, queue và bộ nhớ sẽ tăng không kiểm soát.

### 7.3. Bidirectional streaming

Hai chiều có thể hoạt động đồng thời. Việc nhận request và phát response không nhất thiết theo cặp 1:1. Nếu các request được xử lý song song, response có thể về sai thứ tự; nếu thứ tự quan trọng, cần tuần tự hóa hoặc gắn sequence number và xác định rõ quy tắc reorder.

Với stream lâu dài, không giữ một thread chỉ để chờ message tiếp theo. Handler có thể đăng ký nguồn bất đồng bộ, nhận message, và gửi response khi dữ liệu sẵn sàng. Tuy nhiên, nguồn dữ liệu, executor, cancellation và observer phải có vòng đời rõ ràng.

## 8. Backpressure và giới hạn tài nguyên

Offload sang pool không giải quyết overload nếu số tác vụ submit không bị giới hạn. Một bounded queue chỉ giúp hệ thống có điểm từ chối rõ ràng; nó không làm cho dependency xử lý nhanh hơn.

Các giới hạn nên được xem xét cùng nhau:

- **RPC concurrency:** số cuộc gọi đang hoạt động mà server chấp nhận.
- **Application executor:** số callback có thể chạy đồng thời và chính sách queue.
- **Blocking executor:** số tác vụ I/O blocking được phép chạy.
- **Database pool:** số connection có thể sử dụng.
- **Downstream pool:** connection và concurrency tới dịch vụ ngoài.
- **Message/stream limit:** kích thước request, số phần tử và tốc độ phát dữ liệu.

Khi queue đã đầy, từ chối sớm bằng status có ý nghĩa thường tốt hơn để request chờ đến khi deadline hết. `RESOURCE_EXHAUSTED` có thể biểu đạt giới hạn tài nguyên; `UNAVAILABLE` có thể phù hợp khi service tạm thời không nhận thêm tải. Chọn status theo API contract và chính sách retry của client.

## 9. Đo lường để tìm đúng nút thắt

Không chỉ đo tổng RPC latency. Hãy phân rã thời gian:

| Chỉ số | Giúp trả lời câu hỏi |
| --- | --- |
| RPC duration và deadline exceeded | Client đang chờ bao lâu và có bao nhiêu request quá hạn? |
| Application executor active threads/queue | Callback có đang chờ worker không? |
| Blocking executor active threads/queue/rejections | Tác vụ blocking có đang bão hòa pool không? |
| Database connection wait/query duration | Chậm do thiếu connection, lock hay query? |
| Downstream latency/error | Một dịch vụ ngoài có làm handler giữ worker lâu? |
| Cancellation và in-flight RPC | Bao nhiêu công việc vẫn chạy sau khi client rời đi? |
| CPU utilization và GC | Nút thắt là CPU/bộ nhớ hay I/O? |

Dùng thread name prefix để nhận diện pool trong thread dump. Khi hệ thống chậm, thread dump có thể cho thấy worker đang chờ JDBC, socket read, lock hoặc `Future.get()`. Kết hợp với metric queue và dependency latency để xác định nơi nghẽn; không tăng thread count ngay khi chưa biết giới hạn database/downstream.

## 10. Kiểm thử blocking và saturation

Một số kiểm thử hữu ích:

1. **Handler đồng bộ:** dùng dependency giả có `CountDownLatch` để giữ lời gọi trong thời gian xác định; quan sát worker bị chiếm cho đến khi latch mở.
2. **Bounded executor:** cấu hình pool nhỏ và queue nhỏ trong test; submit nhiều tác vụ chờ để xác minh task vượt giới hạn bị từ chối theo chính sách.
3. **Context propagation:** đặt một gRPC Context value trước khi offload; xác minh callback hoàn tất đọc được giá trị sau khi dùng `context.wrap(...)`.
4. **Cancellation:** hủy RPC khi công việc đang chờ; xác minh adapter không phát response sau cancellation và dependency timeout/cancel theo thiết kế.
5. **Streaming flow control:** tạo client đọc chậm; xác minh server không phát vô hạn và tôn trọng readiness/cancellation.
6. **Load test:** tăng dần concurrency, đo p50/p95/p99, queue depth, rejection, DB wait và deadline exceeded. Không chỉ đo requests/second.

Unit test executor không thay thế integration test với server thật. Cần kiểm tra transport/server factory đang dùng, vì thread model có thể thay đổi khi cấu hình executor hoặc direct execution khác nhau.

## 11. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| RPC khác chậm khi một dependency chậm | Handler blocking chiếm application worker | Giới hạn thời gian dependency, sizing executor hoặc offload có giới hạn |
| Thread event loop bị treo | Callback chạy inline/direct executor hoặc code blocking nằm trên transport thread | Không dùng direct executor cho handler blocking; kiểm tra cấu hình server |
| Tăng thread nhưng DB vẫn chậm | Số worker vượt connection pool hoặc năng lực DB | Đồng bộ concurrency với giới hạn dependency, tối ưu query |
| Queue tăng liên tục | Submit nhanh hơn tốc độ hoàn thành | Bounded queue, admission control, overload status |
| Client timeout nhưng tác vụ vẫn chạy | Deadline không tự ngắt JDBC/HTTP call | Timeout/cancellation ở dependency và kiểm tra context |
| Callback không thấy metadata/security context | ThreadLocal/context không được propagate | Capture gRPC Context; cấu hình propagation cho tracing/security/MDC |
| Response stream lỗi ngẫu nhiên | Nhiều thread gọi cùng observer hoặc terminal event nhiều lần | Serialize writes, một owner cho observer, kiểm soát trạng thái terminal |
| Client streaming làm tăng RAM | Tạo task cho mỗi message không giới hạn hoặc buffer toàn bộ stream | Giới hạn in-flight, chunking và flow control |
| Dùng common pool gây ảnh hưởng tác vụ khác | Tác vụ blocking chiếm worker dùng chung | Executor chuyên biệt, bounded và có metric |
| Retry làm tăng quá tải | Retry đồng loạt khi server đang saturation | Backoff, jitter, retry budget và idempotency |

## 12. Bài tập thực hành

1. Đo thời gian một unary handler gọi repository đồng bộ. Ghi lại active worker và latency khi tăng số client đồng thời.
2. Tạo `ThreadPoolTaskExecutor` có 4 worker và queue 8 phần tử. Mô phỏng dependency chậm, xác minh hành vi từ chối khi pool và queue đầy.
3. Offload một lời gọi blocking sang executor riêng. Capture gRPC Context và kiểm tra cancellation trước khi gửi response.
4. Thêm timeout cho database/downstream. Xác minh client deadline không khiến tác vụ blocking tiếp tục chạy vô thời hạn.
5. Chuyển server streaming sang đọc theo page và phát theo readiness. Kiểm thử client đọc chậm và client hủy giữa chừng.
6. Với client streaming, giới hạn số message đang xử lý đồng thời và giữ thứ tự khi giao thức yêu cầu.
7. Thu thread dump khi hệ thống bị chậm; phân biệt worker chờ DB, worker chờ downstream và thread xử lý CPU.

### Câu hỏi tự kiểm tra

- Transport event loop khác gRPC application executor ở nhiệm vụ nào?
- Vì sao handler gọi JDBC đồng bộ có thể làm các RPC khác phải chờ?
- Khi nào xử lý đồng bộ đơn giản là lựa chọn phù hợp?
- Vì sao bounded executor cần queue capacity và rejection policy?
- `Context.current()` có tự xuất hiện trên thread executor khác không?
- Deadline gRPC có bảo đảm dừng một câu SQL đang chạy không?
- Vì sao không nên gọi `onNext` đồng thời từ nhiều thread?
- Server streaming cần tôn trọng readiness và cancellation như thế nào?
- Tăng số worker có thể làm database chậm hơn trong trường hợp nào?

## Tài liệu tham khảo

- [gRPC Java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): cấu hình executor và server behavior.
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html): context propagation, deadline và cancellation.
- [gRPC Java — ServerCallStreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ServerCallStreamObserver.html): readiness, cancellation và flow control cho server streaming.
- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/): giới hạn thời gian RPC và propagation.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): cấu hình executor và task execution trong Spring.

**Kết quả mong đợi:** Người học hiểu handler blocking tiêu thụ application worker như thế nào, phân biệt được worker ứng dụng với transport event loop, biết khi nào giữ xử lý đồng bộ và khi nào offload sang bounded executor; đồng thời bảo toàn Context, cancellation, thứ tự response và flow control để Spring gRPC duy trì latency và độ tin cậy dưới tải.
