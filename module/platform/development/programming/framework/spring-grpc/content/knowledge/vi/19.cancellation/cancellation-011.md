# Theo dõi RPC bị hủy

## 1. Vì sao cần theo dõi cancellation?

Trong **Spring gRPC**, một RPC có thể kết thúc vì server trả kết quả, phát lỗi, deadline hết hoặc caller chủ động hủy. Với unary RPC ngắn, việc hủy có thể ít được chú ý. Với server-streaming, client-streaming hoặc bidirectional streaming, cancellation còn là tín hiệu để dừng truy vấn, giải phóng subscription, ngừng phát message và trả tài nguyên về pool.

Nếu chỉ ghi log khi RPC hoàn tất, hệ thống khó trả lời các câu hỏi vận hành:

- Bao nhiêu RPC bị caller hủy?
- Bao nhiêu RPC kết thúc do deadline?
- Server có nhận được cancellation và dừng công việc không?
- Sau khi client hủy, database query hoặc broker subscription còn chạy bao lâu?
- Một đợt cancellation tăng đột biến xuất phát từ client, timeout cấu hình hay lỗi mạng?

Theo dõi cancellation cần phân biệt ba mốc:

1. **Cancel requested:** client hoặc reactive subscriber yêu cầu hủy.
2. **Cancel observed:** gRPC server/runtime quan sát call đã bị hủy.
3. **Cleanup completed:** công việc phụ thuộc call đã dừng và tài nguyên đã được giải phóng.

Ba mốc này có thể xảy ra ở các thời điểm khác nhau. Ghi nhận chúng riêng giúp phát hiện trường hợp client đã rời đi nhưng server vẫn tiếp tục làm việc.

## 2. Cancellation khác deadline và RPC error như thế nào?

Cancellation là tín hiệu kết thúc call trước khi luồng xử lý bình thường hoàn tất. Deadline là giới hạn thời gian của logical RPC; khi deadline hết, runtime hủy call và caller thường nhận status DEADLINE_EXCEEDED. Một caller chủ động cancel thường thấy status CANCELLED.

| Tình huống | Caller thường quan sát | Server có thể quan sát | Diễn giải |
| --- | --- | --- | --- |
| Caller chủ động hủy call | CANCELLED | Cancellation signal | Người gọi không còn cần kết quả |
| Reactor subscriber dispose/cancel | CANCELLED nếu bridge truyền đúng tín hiệu | Cancellation signal | Pipeline đã dừng quan tâm |
| Deadline hết | DEADLINE_EXCEEDED | Call bị hủy | Hết ngân sách thời gian |
| Kết nối bị ngắt | Có thể là CANCELLED, UNAVAILABLE hoặc lỗi transport tùy thời điểm | Context/call có thể bị hủy | Không nhất thiết là thao tác người dùng |
| Server chủ động trả lỗi CANCELLED | CANCELLED | Server biết mình đã đóng call | Không đồng nghĩa client đã yêu cầu hủy |
| Server trả lỗi nghiệp vụ khác | Status tương ứng | Server kết thúc bình thường theo lỗi | Không phải cancellation từ caller |

Không suy ra nguyên nhân chỉ từ một status. Server-side cancellation handler cho biết call đã bị hủy, nhưng không nhất thiết cho biết người dùng bấm nút hủy, deadline hết hay transport bị mất. Muốn phân loại nguyên nhân, cần kết hợp dữ liệu từ client, deadline và gateway.

## 3. Theo dõi cancellation ở server

Trong gRPC Java, có hai API hữu ích:

- **ServerCallStreamObserver.setOnCancelHandler():** đăng ký callback khi call bị hủy.
- **ServerCallStreamObserver.isCancelled():** kiểm tra trạng thái call trước khi tiếp tục phát response.

Với công việc gắn với gRPC Context, có thể đăng ký Context cancellation listener để truyền tín hiệu dừng tới task phụ thuộc context. Handler nên được đăng ký sớm, trước khi khởi chạy công việc tốn tài nguyên.

Ví dụ server-streaming service có một subscription tới event source:

~~~java
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

@Service
public class OrderWatchGrpcService
        extends OrderWatchGrpc.OrderWatchImplBase {

    private final OrderEventSource eventSource;
    private final CancellationMetrics metrics;

    public OrderWatchGrpcService(
            OrderEventSource eventSource,
            CancellationMetrics metrics) {
        this.eventSource = eventSource;
        this.metrics = metrics;
    }

    @Override
    public void watch(
            WatchRequest request,
            StreamObserver<OrderEvent> responseObserver) {

        ServerCallStreamObserver<OrderEvent> call =
                (ServerCallStreamObserver<OrderEvent>) responseObserver;
        AtomicBoolean terminated = new AtomicBoolean();
        AtomicReference<Disposable> subscriptionRef =
                new AtomicReference<>();
        AtomicBoolean cancelObserved = new AtomicBoolean();
        AtomicBoolean cleanupSignalSent = new AtomicBoolean();
        Object signalLock = new Object();

        Runnable disposeSubscription = () -> {
            Disposable subscription = subscriptionRef.get();
            if (subscription != null
                    && cleanupSignalSent.compareAndSet(false, true)) {
                subscription.dispose();
                metrics.recordCleanupRequested(
                        "orders.v1.OrderWatch/Watch");
            }
        };

        call.setOnCancelHandler(() -> {
            synchronized (signalLock) {
                if (!terminated.compareAndSet(false, true)) {
                    return;
                }
                cancelObserved.set(true);
                metrics.recordServerCancellation(
                        "orders.v1.OrderWatch/Watch");
            }
            disposeSubscription.run();
        });

        if (terminated.get() || call.isCancelled()) {
            return;
        }
        Flux<OrderEvent> events = Flux.defer(
                () -> eventSource.watch(request));
        Disposable subscription = events.subscribe(
                event -> {
                    synchronized (signalLock) {
                        if (terminated.get() || call.isCancelled()) {
                            return;
                        }
                        call.onNext(event);
                    }
                },
                error -> {
                    synchronized (signalLock) {
                        if (terminated.compareAndSet(false, true)) {
                            call.onError(Status.INTERNAL
                                    .withDescription("Event stream failed")
                                    .withCause(error)
                                    .asRuntimeException());
                        }
                    }
                },
                () -> {
                    synchronized (signalLock) {
                        if (terminated.compareAndSet(false, true)) {
                            call.onCompleted();
                        }
                    }
                });

        subscriptionRef.set(subscription);
        // Cancellation/completion có thể xảy ra đồng bộ trước khi subscribe trả về.
        if (cancelObserved.get() || call.isCancelled()) {
            disposeSubscription.run();
        }
    }
}
~~~

Ví dụ minh họa các điểm quan trọng:

- Đăng ký cancel handler trước khi subscribe event source.
- Dùng một cờ terminal để cancellation, error và completion không kết thúc call nhiều lần.
- Giữ subscription handle để dispose khi call bị hủy.
- Kiểm tra cancellation trước khi phát message.
- Xử lý race khi stream kết thúc hoặc bị hủy trước khi subscribe trả về handle.
- Đồng bộ việc ghi response vì StreamObserver không nên bị gọi đồng thời từ nhiều thread.

Các kiểu OrderEventSource, CancellationMetrics và generated service là thành phần của ứng dụng. Trong production, cần bảo đảm event source phát callback tuần tự hoặc serialize trước khi gọi observer; việc dispose subscription phải an toàn khi được gọi nhiều lần.

Trong ví dụ, `dispose()` và metric `cleanup requested` chỉ xác nhận tín hiệu dừng đã được gửi. Nếu broker/database cần đóng tài nguyên bất đồng bộ, hãy ghi `cleanup completed` khi nhận acknowledgment hoặc completion signal thực tế từ resource owner; không đo thời điểm gọi dispose như thể tài nguyên đã chắc chắn được giải phóng.

## 4. Dùng gRPC Context cho công việc phụ thuộc RPC

gRPC Context mang thông tin gắn với vòng đời call, bao gồm deadline và cancellation. Khi một RPC bị hủy, Context liên quan có thể chuyển sang trạng thái cancelled. Một task phụ thuộc Context có thể đăng ký listener:

~~~java
import io.grpc.Context;
import java.util.concurrent.Executor;

Context rpcContext = Context.current();
Context.CancellationListener listener =
        cancelledContext -> stopDependentWork();

Executor directExecutor = Runnable::run;
rpcContext.addListener(listener, directExecutor);
~~~

Đăng ký listener trong lúc đang xử lý RPC để lấy đúng Context của call. Listener có thể được gọi trên executor đã chỉ định; vì vậy callback cần ngắn, không thực hiện blocking cleanup dài ngay trên thread callback. Có thể phát tín hiệu tới task owner hoặc scheduler để dừng công việc.

Nếu task chạy ở executor riêng, hãy truyền Context/cancellation token một cách tường minh hoặc dùng executor có cơ chế propagate Context. Không giả định mọi thread do ứng dụng tự tạo đều tự động mang Context hiện tại.

Nếu task hoàn tất bình thường trước khi Context bị hủy, gỡ listener bằng `rpcContext.removeListener(listener)` để không giữ tham chiếu không cần thiết. Nếu listener chỉ sống cùng một RPC ngắn, vẫn nên quản lý vòng đời đăng ký rõ ràng.

Với downstream gRPC call, giữ deadline và cancellation của thao tác cha trong phạm vi phù hợp. Nếu tạo một call mới sau khi parent đã bị hủy, cần kiểm tra trạng thái và không khởi động công việc vô ích.

## 5. Theo dõi cancellation ở client

Client là nơi biết rõ nhất caller có chủ động hủy hay không. Hãy ghi nhận ý định tại điểm gọi cancellation:

- Người dùng rời màn hình hoặc hủy thao tác.
- Reactive subscriber gọi dispose/cancel.
- Một request mới thay thế request cũ.
- Ứng dụng đóng hoặc ngừng một subscription.

Ví dụ với Reactor:

~~~java
Mono<GetOrderResponse> result = orderClient.getOrderReactive(request)
        .doOnCancel(() ->
                cancellationMetrics.recordClientCancelRequested(
                        "orders.v1.OrderService/GetOrder"));
~~~

Bridge phía dưới phải nối cancellation của Mono tới Future hoặc gRPC ClientCall. Nếu chỉ ghi metric ở doOnCancel mà bridge không hủy call thật, số liệu client sẽ báo đã cancel trong khi RPC vẫn chạy.

Với future stub, ghi nhận nơi ứng dụng gọi future.cancel(...). Với async stub, ghi nhận nơi ứng dụng gọi ClientCallStreamObserver.cancel(...). Đừng phân loại mọi terminal status CANCELLED là user cancellation: cancellation có thể xuất phát từ deadline, parent call hoặc transport.

## 6. Phân biệt cancel requested, observed và completed

Một mô hình sự kiện rõ ràng giúp tránh đếm trùng:

| Sự kiện | Nơi ghi nhận | Ý nghĩa |
| --- | --- | --- |
| client.cancel.requested | Client application/bridge | Caller hoặc pipeline yêu cầu dừng |
| server.cancel.observed | Server cancellation handler/Context | Server nhận biết call đã bị hủy |
| server.cleanup.started | Service/resource owner | Bắt đầu dọn tài nguyên |
| server.cleanup.completed | Service/resource owner | Subscription/task/resource đã dừng |
| rpc.closed | Client/server instrumentation | Call đã có terminal status |

Không phải mọi RPC bị hủy đều có đủ mọi sự kiện. Client có thể mất kết nối trước khi telemetry gửi đi; server có thể bị process kill trước cleanup; hoặc call hoàn tất ngay trước khi cancellation tới.

Khi đo thời gian cleanup, dùng monotonic clock hoặc Timer của telemetry, không lấy chênh lệch wall-clock dễ bị ảnh hưởng bởi đồng bộ thời gian hệ thống.

## 7. Metric và nhãn phù hợp

Một bộ metric ứng dụng có thể gồm:

| Metric | Loại | Mục đích |
| --- | --- | --- |
| app.grpc.server.rpc.started | Counter | RPC server bắt đầu xử lý |
| app.grpc.server.rpc.completed | Counter | RPC kết thúc, gắn status cuối |
| app.grpc.server.rpc.cancel.observed | Counter | Server quan sát cancellation |
| app.grpc.server.rpc.cleanup.duration | Histogram | Thời gian từ lúc nhận cancel tới cleanup hoàn tất |
| app.grpc.client.rpc.cancel.requested | Counter | Client chủ động yêu cầu hủy |
| app.grpc.client.rpc.completed | Counter | Client nhận terminal status |
| app.grpc.server.rpc.active | Gauge | Số RPC đang hoạt động |

Đây là tên metric do ứng dụng tự đặt, không phải tên bắt buộc của OpenTelemetry. Nếu gRPC/OpenTelemetry instrumentation đã cung cấp metric RPC started, duration hoặc status, hãy tái sử dụng metric chuẩn và chỉ bổ sung metric riêng cho cancellation/cleanup mà instrumentation chưa đo.

Nhãn metric nên có cardinality thấp:

- RPC service/method.
- gRPC status.
- Nguồn cancellation đã xác định: caller, deadline hoặc server policy.
- Loại resource được cleanup: subscription, task hoặc stream.

Không dùng request ID, trace ID, user ID, tenant ID hoặc order ID làm metric label. Các giá trị này phù hợp hơn với log/trace có kiểm soát.

## 8. Status và nguyên nhân cancellation

Khi client nhận terminal status, thường có thể phân loại:

| Status cuối | Diễn giải thường gặp | Ghi nhận |
| --- | --- | --- |
| CANCELLED | Call bị hủy trước khi hoàn tất | Cancellation outcome |
| DEADLINE_EXCEEDED | Deadline của call hết | Timeout outcome; server cũng có thể nhận cancellation |
| UNAVAILABLE | Transport hoặc service không khả dụng | Availability failure; không tự động coi là user cancel |
| OK | RPC hoàn tất thành công | Normal completion |
| INTERNAL/UNKNOWN | Lỗi thực thi hoặc lỗi không phân loại được | Error outcome |

Server cancellation handler thường không có tham số nguyên nhân. Nếu server chỉ biết call bị hủy, hãy ghi source là server_observed hoặc unknown. Chỉ gắn source=deadline khi có bằng chứng deadline đã hết; chỉ gắn source=caller khi client gửi được thông tin đáng tin cậy từ điểm gọi.

Không dùng metadata do client tự khai báo như bằng chứng bảo mật về nguyên nhân. Metadata có thể hữu ích để correlation, nhưng không thay thế trạng thái cancellation mà runtime quan sát.

## 9. Log và trace để điều tra

Log có cấu trúc nên chứa:

~~~json
{
  "event": "grpc.server.cancel.observed",
  "rpc.method": "orders.v1.OrderWatch/Watch",
  "grpc.status": "CANCELLED",
  "cancel.source": "server_observed_unknown",
  "rpc.elapsed_ms": 840,
  "cleanup.duration_ms": 12,
  "trace_id": "trace-id",
  "rpc_id": "logical-call-id"
}
~~~

Trace có thể đánh dấu span RPC bằng trạng thái cancelled hoặc status tương ứng, đồng thời thêm event:

- cancellation observed;
- cleanup started;
- cleanup completed;
- deadline remaining tại thời điểm nhận tín hiệu, nếu có.

Không ghi payload hoặc dữ liệu nhạy cảm vào event cancellation. Giữ cùng trace/correlation ID giữa client, gateway và server để xác định cancellation bắt đầu ở đâu và truyền tới server lúc nào.

Với retry, phân biệt logical call và từng server attempt. Một logical call có thể tạo nhiều attempt; cancellation của một attempt không nhất thiết có nghĩa toàn bộ thao tác người dùng đã bị hủy. Đặt tên metric và span theo đúng phạm vi đo.

## 10. Kiểm thử cancellation

Nên dùng in-process gRPC server/channel hoặc test server có thể điều khiển stream và xác nhận cleanup:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Client gọi cancel trên async call | Server cancellation handler được gọi |
| Reactor subscriber dispose | Bridge hủy gRPC call, server quan sát cancellation |
| Deadline hết | Client nhận DEADLINE_EXCEEDED; server dừng công việc phụ thuộc call |
| Client cancel trước khi resource handle được tạo | Khi handle xuất hiện, resource được đóng ngay |
| Cancel đồng thời với onNext | Không phát response sau terminal state |
| RPC hoàn tất bình thường | Không ghi cancellation event giả |
| Server cleanup gọi từ nhiều đường | Cleanup idempotent, chỉ ghi nhận hoàn tất một lần |
| Network disconnect | Server dừng task khi runtime phát hiện call không còn hoạt động |
| Client cancel sau khi DB commit | Không giả định transaction đã rollback |

Test nên dùng latch/await có timeout để xác minh subscription đã dispose hoặc task đã dừng. Tránh sleep cố định vì tạo test chập chờn. Đo riêng thời gian từ cancel observed tới cleanup completed để phát hiện resource leak.

## 11. Sai lầm thường gặp

1. **Chỉ nhìn status CANCELLED.** Không biết cancellation do caller, deadline hay transport nếu thiếu telemetry ở nguồn.
2. **Coi DEADLINE_EXCEEDED là không liên quan cancellation.** Server thường vẫn cần dừng công việc khi deadline hết.
3. **Đăng ký onCancel handler quá muộn.** Công việc có thể đã chạy và resource được tạo trước khi có cleanup hook.
4. **Cleanup không idempotent.** Context listener và onCancel handler có thể cùng yêu cầu dọn tài nguyên.
5. **Cho rằng cancellation rollback database.** Transaction đã commit không tự bị đảo ngược.
6. **Để task nền tiếp tục sau khi RPC kết thúc.** Cần gắn task với vòng đời call hoặc có cơ chế ownership riêng.
7. **Gọi blocking cleanup trên callback thread.** Có thể làm chậm xử lý các cancellation khác.
8. **Đếm một cancellation nhiều lần.** Dùng terminal guard để ghi nhận một lần cho mỗi server call.
9. **Đưa ID duy nhất vào metric label.** Tạo cardinality cao và làm monitoring backend quá tải.

## 12. Bài tập vận dụng

Với server-streaming RPC Watch:

1. Đăng ký ServerCallStreamObserver.setOnCancelHandler trước khi tạo subscription.
2. Dùng terminal guard để xử lý cancellation, error và completion đúng một lần.
3. Đo cancel requested ở client và cancel observed ở server.
4. Mô phỏng Reactor dispose và deadline expiry; so sánh status client với tín hiệu server nhận được.
5. Đo cleanup duration từ lúc cancellation tới khi subscription thực sự đóng.
6. Mô phỏng cancel race với onNext và xác minh không phát message sau terminal state.
7. Mô phỏng cancellation sau khi server commit dữ liệu; xác minh dữ liệu đã commit không bị hiểu nhầm là rollback.

**Tiêu chí hoàn thành:** người học phân biệt được cancel requested, cancel observed và cleanup completed; theo dõi đúng status/deadline; giải phóng tài nguyên phía server; thiết kế metric, log và trace có cardinality hợp lý; kiểm thử được cancellation race và cleanup.

### Tài liệu tham khảo

- [gRPC Cancellation](https://grpc.io/docs/guides/cancellation/): cancellation và cách server/client phản ứng.
- [gRPC Deadlines](https://grpc.io/docs/guides/deadlines/): deadline và hủy RPC khi hết thời gian.
- [gRPC Java ServerCallStreamObserver API](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ServerCallStreamObserver.html): on-cancel handler và trạng thái call phía server.
- [gRPC Java Context API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html): cancellation context và listener.
- [OpenTelemetry](https://opentelemetry.io/docs/): metric, trace và log cho quan sát hệ thống.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
