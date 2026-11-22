# Xử lý blocking I/O

Trong **SPRING_GRPC**, gRPC service adapter nhận request protobuf, gọi application use case và gửi kết quả qua `StreamObserver`. Nhiều use case vẫn cần thao tác đồng bộ như JDBC/JPA, đọc file, gọi SDK cũ hoặc gọi downstream bằng blocking client. Những thao tác này chờ I/O hoàn tất trước khi trả về; trong thời gian chờ, thread thực thi RPC không thể xử lý công việc khác.

Mục tiêu không phải loại bỏ mọi blocking call. Mục tiêu là đặt chúng trong thread và transaction phù hợp, giới hạn concurrency, tôn trọng deadline/cancellation và tránh giữ tài nguyên trong lúc chờ mạng. Bài này tập trung vào cách xử lý blocking I/O ở gRPC adapter của Spring, từ unary RPC tới streaming và downstream call.

## 1. Nhận diện blocking I/O

Một thao tác là blocking khi thread gọi phải chờ kết quả trước khi tiếp tục. Ví dụ thường gặp:

- JDBC/JPA query hoặc transaction commit.
- Đọc/ghi file, object storage bằng API đồng bộ.
- Gọi REST client hoặc SDK cloud đồng bộ.
- Gọi gRPC bằng blocking stub.
- Chờ lock, semaphore hoặc queue đồng bộ.

Khi một RPC handler thực hiện blocking I/O, thread phục vụ lời gọi đó bị chiếm cho đến khi thao tác hoàn tất. Nếu nhiều request cùng chờ database hoặc downstream service, số thread bị chiếm tăng lên; khi executor hết thread và queue đầy, các request mới bị trì hoãn hoặc từ chối.

Cần phân biệt blocking application call với Netty event loop. Native gRPC Java thường dispatch application listener qua server executor; không nên mặc định service method chạy trực tiếp trên Netty event-loop thread. Tuy nhiên, blocking handler vẫn chiếm thread của executor phục vụ RPC. Nếu cấu hình transport hoặc adapter tùy biến chạy callback trên event loop, blocking tại đó còn có thể làm nghẽn I/O của nhiều connection.

## 2. Unary RPC: gọi đồng bộ trực tiếp khi công việc có giới hạn

Với unary RPC có thời gian xử lý ngắn, ổn định và concurrency phù hợp, adapter có thể gọi use case đồng bộ ngay trong handler:

```java
@Override
public void getStock(
        StockRequest request,
        StreamObserver<StockReply> observer) {
    try {
        StockView result =
                stockQuery.findBySku(new Sku(request.getSku()));

        observer.onNext(mapper.toProto(result));
        observer.onCompleted();
    } catch (StockNotFoundException error) {
        observer.onError(Status.NOT_FOUND
                .withDescription("Stock item not found")
                .asRuntimeException());
    } catch (RuntimeException error) {
        log.error("GetStock failed", error);
        observer.onError(Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException());
    }
}
```

Đây là cách đơn giản và thường phù hợp khi:

- Query có thời gian phản hồi được kiểm soát.
- Connection pool và server executor đủ capacity.
- Không có thao tác chờ lâu hoặc không giới hạn.
- Deadline của RPC và timeout của dependency được cấu hình hợp lý.

Lời gọi đồng bộ không tự động là sai. Tách mọi method sang executor khác cũng tạo queue, context propagation, cancellation và lifecycle phức tạp hơn. Chỉ offload khi cần cách ly công việc chờ lâu hoặc bảo vệ executor dùng chung.

## 3. Không dùng thread tùy ý hoặc executor không giới hạn

Không tạo thread mới cho mỗi RPC và không dùng cached/unbounded executor cho tải không kiểm soát. Khi downstream chậm, số thread và bộ nhớ có thể tăng theo số request đang chờ.

Dùng executor riêng có giới hạn cho nhóm blocking workload. Ví dụ Spring:

```java
@Configuration
class GrpcBlockingIoConfiguration {

    @Bean
    ThreadPoolTaskExecutor grpcBlockingExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(16);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("grpc-blocking-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

Các con số chỉ là điểm khởi đầu minh họa. Chọn pool size dựa trên thời gian I/O, CPU, giới hạn connection pool, concurrency downstream và tải đo được. Queue lớn không làm hệ thống nhanh hơn; nó chỉ giữ thêm request chờ và có thể khiến deadline hết trước khi công việc bắt đầu.

Executor riêng tạo bulkhead: một downstream chậm không chiếm hết thread xử lý mọi loại RPC. Có thể tách pool cho database, file storage và remote SDK nếu các nhóm có đặc tính tải khác nhau.

## 4. Offload unary RPC và giữ gRPC Context

Khi cần tách blocking I/O khỏi handler thread, submit công việc vào executor. Phải capture Context hiện tại và wrap task để request-scoped state, deadline và cancellation của gRPC được gắn vào thread thực thi.

```java
@Service
class StockGrpcService
        extends StockServiceGrpc.StockServiceImplBase {

    private final AsyncTaskExecutor blockingExecutor;
    private final StockQueryUseCase stockQuery;
    private final StockProtoMapper mapper;

    StockGrpcService(
            @Qualifier("grpcBlockingExecutor")
            AsyncTaskExecutor blockingExecutor,
            StockQueryUseCase stockQuery,
            StockProtoMapper mapper) {
        this.blockingExecutor = blockingExecutor;
        this.stockQuery = stockQuery;
        this.mapper = mapper;
    }

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        Context rpcContext = Context.current();

        try {
            blockingExecutor.submit(rpcContext.wrap(() -> {
                if (rpcContext.isCancelled()) {
                    return;
                }

                try {
                    StockView result = stockQuery.findBySku(
                            new Sku(request.getSku()));

                    if (rpcContext.isCancelled()) {
                        return;
                    }

                    observer.onNext(mapper.toProto(result));
                    observer.onCompleted();
                } catch (StockNotFoundException error) {
                    observer.onError(Status.NOT_FOUND
                            .withDescription("Stock item not found")
                            .asRuntimeException());
                } catch (RuntimeException error) {
                    log.error("GetStock failed", error);
                    observer.onError(Status.INTERNAL
                            .withDescription("Internal server error")
                            .asRuntimeException());
                }
            }));
        } catch (TaskRejectedException rejected) {
            observer.onError(Status.RESOURCE_EXHAUSTED
                    .withDescription("Server is busy")
                    .asRuntimeException());
        }
    }
}
```

Ví dụ dùng `AsyncTaskExecutor` và `ThreadPoolTaskExecutor` của Spring. Các import, constructor injection và mapper được rút gọn theo cấu trúc ứng dụng. Task được wrap bằng Context đã capture trước khi handler trả về; nếu không wrap, Context key hoặc deadline hiện tại có thể không còn sẵn trong worker thread.

Mỗi task chỉ có một thread gọi `onNext`/`onCompleted`/`onError`. Không để nhiều worker cùng ghi vào một `StreamObserver`; observer không phải nơi đồng bộ hóa output của nhiều producer. Nếu cần phát từ nhiều nguồn, gom kết quả qua một hàng đợi và dùng một writer tuần tự.

Khi executor từ chối task, trả status có ý nghĩa như `RESOURCE_EXHAUSTED` hoặc `UNAVAILABLE` theo chính sách tải của service. Không âm thầm bỏ request hoặc tạo thread dự phòng không giới hạn.

## 5. Cancellation phải dừng được blocking work

Khi client hủy RPC hoặc deadline hết, server nhận trạng thái cancellation qua gRPC Context. Tuy nhiên, cancellation không tự dừng mọi JDBC driver, file API hoặc SDK đang blocking.

Với server call, có thể quan sát cancellation và yêu cầu worker dừng:

```java
ServerCallStreamObserver<StockReply> serverObserver =
        (ServerCallStreamObserver<StockReply>) observer;

AtomicReference<Future<?>> taskRef = new AtomicReference<>();

serverObserver.setOnCancelHandler(() -> {
    Future<?> task = taskRef.get();
    if (task != null) {
        task.cancel(true);
    }
});

Context rpcContext = Context.current();
Future<?> task = blockingExecutor.submit(
        rpcContext.wrap(() -> performBlockingLookup()));

taskRef.set(task);

if (rpcContext.isCancelled()) {
    task.cancel(true);
}
```

Đây là khung minh họa; trong code thực tế, phần gửi response và xử lý exception phải nằm trong task như ví dụ unary ở trên. Cần xử lý race giữa cancellation và lúc task được submit, đồng thời bảo đảm chỉ phát một terminal signal.

`Future.cancel(true)` gửi interrupt tới worker nếu task đang chạy. Đây là yêu cầu hủy best-effort, không phải bằng chứng I/O đã dừng. JDBC driver, socket hoặc SDK có thể không phản ứng với interrupt. Vì vậy vẫn cần query timeout, socket/read timeout, API cancellation của client và timeout ở dependency.

Không gọi `onError` từ cancellation handler rồi để worker tiếp tục gọi `onNext`. Chọn một nơi chịu trách nhiệm kết thúc observer; worker phải kiểm tra cancellation trước khi phát response.

## 6. Deadline phải giới hạn cả thời gian chờ I/O

Deadline gRPC giới hạn thời gian RPC. Nếu client chỉ còn 300 ms nhưng query database có timeout 10 giây, worker có thể tiếp tục giữ thread và connection sau khi client đã bỏ cuộc.

Lấy thời gian còn lại từ Context và dùng nó để đặt budget cho dependency:

```java
Context context = Context.current();
Deadline deadline = context.getDeadline();

long remainingMillis = deadline == null
        ? 1_000
        : deadline.timeRemaining(TimeUnit.MILLISECONDS);

if (remainingMillis <= 0 || context.isCancelled()) {
    throw new RpcWorkCancelledException();
}

long operationBudgetMillis = Math.min(
        remainingMillis, DEFAULT_QUERY_BUDGET_MILLIS);

return repository.findWithTimeout(
        sku, Duration.ofMillis(operationBudgetMillis));
```

Đây là ví dụ minh họa việc tính budget; API timeout cụ thể phụ thuộc repository, JDBC driver hoặc SDK. Trong ứng dụng thực tế, đặt một giới hạn mặc định cho operation và lấy giá trị nhỏ hơn giữa giới hạn đó với thời gian còn lại của RPC. Tránh làm tròn khiến timeout dependency dài hơn đáng kể so với deadline còn lại.

Deadline không thay thế timeout của từng dependency. Một RPC có thể gọi database, HTTP và gRPC downstream; mỗi bước cần timeout tương thích với budget còn lại. Dành một phần thời gian cho mapping và gửi response thay vì tiêu hết budget vào lần I/O cuối.

## 7. Transaction phải bắt đầu trên worker thread

Spring transaction với JDBC/JPA thường gắn với thread. Nếu handler mở transaction rồi chuyển blocking work sang executor khác, worker thread không tự tham gia transaction đó.

Hãy gọi một public application method có `@Transactional` từ worker thread; Spring proxy sẽ mở transaction trên thread đang thực thi use case:

```java
@Service
class ReserveStockService implements ReserveStockUseCase {

    @Override
    @Transactional
    public ReservationResult reserve(ReserveStockCommand command) {
        Stock stock = repository.findBySku(command.sku())
                .orElseThrow(StockNotFoundException::new);

        stock.reserve(command.quantity());
        reservationRepository.save(Reservation.create(command));
        return ReservationResult.from(stock);
    }
}
```

Adapter submit lời gọi `reserveStock.reserve(command)` vào executor; transaction được mở và đóng trong worker thread khi method kết thúc. Không truyền `EntityManager`, JDBC connection hoặc managed entity từ handler thread sang worker.

Không giữ transaction mở trong lúc chờ một remote HTTP/gRPC call nếu có thể tránh. Network có độ trễ không ổn định và có thể giữ database lock/connection quá lâu. Dùng outbox, saga hoặc tách bước nghiệp vụ khi cần phối hợp nhiều service.

## 8. Blocking downstream gRPC hoặc HTTP client

Gọi downstream bằng blocking stub cũng chiếm thread hiện tại:

```java
StockReply reply = inventoryStub
        .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
        .getStock(request);
```

Nếu đây là một phần của use case đồng bộ, hãy tính thời gian đó vào RPC budget và tránh gọi trong khi giữ transaction database. Nếu downstream call có thể chậm, cách ly nó trong executor/bulkhead riêng hoặc dùng async stub và xử lý callback phù hợp.

Không dùng một pool chung không giới hạn cho tất cả downstream. Một service phụ thuộc chậm có thể chiếm hết worker của service khác. Đặt timeout, giới hạn concurrency và chính sách retry có backoff; retry phải xét idempotency và deadline còn lại.

Nếu dùng Spring HTTP client đồng bộ, cấu hình connection timeout, response/read timeout và pool connection. Chỉ đặt gRPC deadline mà không đặt timeout ở HTTP client có thể vẫn để thread mắc kẹt lâu sau khi RPC đã kết thúc.

## 9. Streaming: không giữ thread và transaction trong lúc chờ consumer

Trong server-streaming, producer có thể đọc dữ liệu từ database rồi gửi nhiều response. Nếu đọc một cursor blocking và gọi `onNext` liên tục, server có thể tiếp tục tạo dữ liệu nhanh hơn client nhận; nếu client chậm, buffer và bộ nhớ tăng.

Với `ServerCallStreamObserver`, kiểm tra readiness và đăng ký `onReadyHandler` để phát dữ liệu theo khả năng transport:

```java
ServerCallStreamObserver<StockReply> output =
        (ServerCallStreamObserver<StockReply>) observer;

output.setOnReadyHandler(() -> {
    // Đánh thức producer/writer khi transport có thể nhận thêm dữ liệu.
    streamPump.signalReady();
});
```

`onReadyHandler` có thể được gọi nhiều lần và không nên tự chạy một vòng blocking dài trên callback thread. Dùng một producer/writer có lifecycle rõ ràng; chỉ một writer phát `onNext`. Khi `isReady()` là false, tạm dừng lấy hoặc phát dữ liệu và chờ tín hiệu sẵn sàng.

Với dữ liệu database, đọc theo page/chunk bằng transaction ngắn rồi phát từng batch. Không giữ cursor, transaction hoặc connection trong toàn bộ thời gian client nhận stream nếu có thể tránh. Khi client hủy, dừng producer và đóng cursor/resource.

Client-streaming cũng cần giới hạn lượng dữ liệu đang chờ xử lý. Không gom toàn bộ stream vào một `List` hoặc queue vô hạn. Xử lý theo batch, áp dụng backpressure/flow control và xác định rõ chính sách partial commit/resume nếu stream bị ngắt.

## 10. Bounded concurrency, queue và overload

Kích thước executor cần được tính cùng các giới hạn downstream. Ví dụ database pool chỉ có 20 connection thì tạo 200 worker đồng thời cùng chờ database không làm throughput tăng tương ứng; nó chỉ làm tăng queue, context switching và thời gian chờ.

Các điểm cần theo dõi:

- Active worker, pool size và queue depth.
- Số task bị reject và thời gian nằm trong queue.
- Thời gian chờ connection pool và thời gian query.
- RPC deadline exceeded, cancellation và status `RESOURCE_EXHAUSTED`.
- Số connection/stream đang mở.
- Latency p95/p99 của từng dependency.

Khi queue đầy, từ chối sớm giúp client có thể backoff hoặc chọn replica khác. Một request nằm trong queue quá lâu rồi mới bắt đầu I/O thường đã hết deadline và chỉ tạo tải vô ích.

Không đặt `CallerRunsPolicy` một cách máy móc cho executor nhận task từ gRPC handler. Chính sách này có thể buộc handler thread thực hiện blocking work khi pool đầy, làm mất tác dụng cách ly. Dùng rejection rõ ràng và map thành status theo overload policy.

## 11. Virtual threads và non-blocking I/O

Virtual threads (Java 21+) có thể làm mô hình thread-per-request cho blocking I/O nhẹ hơn trong nhiều workload. Tuy nhiên, chúng không làm database connection, remote service hoặc CPU capacity trở nên vô hạn.

Nếu chọn virtual threads:
- Cấu hình executor dùng virtual thread một cách tường minh cho blocking task.
- Xác minh gRPC server executor thực sự dùng executor đó; property bật virtual threads của Spring Boot không có nghĩa mọi transport executor tự đổi.
- Vẫn giới hạn concurrency tới database/downstream bằng semaphore, bulkhead hoặc connection pool.
- Đo pinning, throughput và latency trên JDK/driver thực tế.
- Giữ timeout và cancellation vì virtual thread không tự hủy I/O không thể interrupt.

Nếu toàn bộ stack hỗ trợ reactive/non-blocking, có thể dùng driver và client non-blocking để giảm số thread chờ. Không gọi JDBC/JPA blocking trực tiếp trên event-loop của reactive runtime; một mắt xích blocking có thể làm nghẽn nhiều request khác.

## 12. Kiểm thử blocking I/O và cancellation

Kiểm thử cần chứng minh cả kết quả nghiệp vụ lẫn hành vi khi tải/chờ:

1. Dùng stub hoặc repository giả lập một I/O chậm có thể điều khiển bằng latch.
2. Gửi nhiều RPC đồng thời và xác nhận số blocking task không vượt giới hạn executor.
3. Làm đầy queue trong test cô lập; xác nhận request mới nhận status overload dự kiến.
4. Đặt deadline ngắn hơn thời gian I/O; xác nhận worker dừng hoặc timeout dependency được kích hoạt.
5. Hủy RPC khi task đang chạy; xác nhận cancellation handler được gọi và resource được giải phóng.
6. Kiểm tra exception domain được map thành status đúng; lỗi bất ngờ không lộ chi tiết nội bộ.
7. Với streaming, làm client đọc chậm; xác nhận producer tôn trọng readiness/backpressure.
8. Kiểm tra transaction được mở trên worker thread và commit/rollback đúng.
9. Đo queue wait, execution time và p95/p99 bằng tải đại diện.

Dùng latch hoặc controllable fake thay cho `Thread.sleep` dài để test ổn định. In-process transport hữu ích cho logic interceptor và status, nhưng kiểm thử network, TLS hoặc flow control cần transport phù hợp với mục tiêu.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Blocking I/O không timeout | Worker bị giữ vô hạn | Đặt timeout ở từng dependency và RPC deadline |
| Tạo thread cho mỗi request | Thread/bộ nhớ tăng không kiểm soát | Executor có giới hạn và rejection policy |
| Dùng queue vô hạn | Latency tăng, request hết deadline trong queue | Queue hữu hạn, từ chối sớm |
| Offload mà không wrap Context | Mất request-scoped state/deadline | Capture và wrap gRPC Context |
| Giả định cancellation tự ngắt JDBC | Query vẫn chạy và giữ connection | Query/socket timeout, driver cancellation, interrupt best-effort |
| Transaction mở trước khi offload | Worker không tham gia transaction handler | Mở transaction trong application method trên worker |
| Gửi observer từ nhiều thread | Race hoặc vi phạm thứ tự response | Một writer tuần tự cho mỗi RPC |
| Gửi stream nhanh hơn consumer | Buffer và memory tăng | Readiness, flow control, chunking |
| Blocking downstream trong transaction | Giữ lock/connection khi chờ mạng | Tách network call, outbox hoặc saga |
| Bật virtual threads nhưng không giới hạn tài nguyên | Database/downstream vẫn quá tải | Bulkhead và connection/concurrency limits |

## 14. Bài tập thực hành

1. Viết một unary adapter gọi application service có JDBC/JPA blocking I/O và đo thời gian thực thi.
2. Tạo `ThreadPoolTaskExecutor` riêng với pool size, queue capacity và rejection policy hữu hạn.
3. Offload một RPC vào executor bằng `Context.current().wrap(...)`.
4. Thêm deadline phía client và chuyển remaining budget thành query/downstream timeout.
5. Thêm cancellation handler; kiểm tra worker dừng best-effort và resource được đóng.
6. Xác nhận `@Transactional` chạy trên worker thread qua Spring proxy.
7. Gọi một downstream bằng blocking stub với deadline ngắn hơn deadline tổng.
8. Viết server-streaming producer đọc theo page và chỉ phát khi observer ready.
9. Làm queue đầy trong test và xác nhận overload status được trả đúng.
10. Đo active workers, queue wait, I/O latency, cancellation và p95/p99 dưới tải đại diện.

### Ghi nhớ

**Blocking I/O có thể dùng trong gRPC adapter nếu thread, timeout và concurrency được quản lý có chủ đích.** Với unary ngắn, gọi đồng bộ có thể đủ; với công việc chờ lâu, dùng executor bounded và giữ gRPC Context khi offload. Đặt timeout cho từng dependency, kiểm tra cancellation, mở transaction trên đúng worker thread và điều tiết streaming bằng readiness/backpressure. Virtual threads giúp giảm chi phí thread nhưng không thay thế giới hạn database, downstream hay queue.

## Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html)
- [gRPC Java — ServerCallStreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ServerCallStreamObserver.html)
- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/)
- [gRPC — Flow Control](https://grpc.io/docs/guides/flow-control/)
