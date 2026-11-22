# Thread safety của stream observer

Trong gRPC Java, `StreamObserver` là API gửi và nhận message bất đồng bộ. Một stream có thể được nhiều phần của ứng dụng tạo dữ liệu, trong khi transport tiếp tục gửi/nhận message và xử lý cancellation. Nếu nhiều thread cùng gọi `onNext`, `onError` hoặc `onCompleted` trên một observer, message có thể bị xen kẽ, terminal signal chạy sai thứ tự hoặc call bị đóng khi producer vẫn đang gửi.

Quy tắc cốt lõi: **observer mà ứng dụng chủ động ghi phải có một luồng ghi được tuần tự hóa**. gRPC điều phối các callback nhận message của một call theo thứ tự, nhưng callback có thể chạy trên các thread khác nhau theo thời gian; các RPC khác nhau cũng có thể chạy đồng thời. Vì vậy cần phân biệt observer dùng để gửi với observer nhận callback, đồng thời quản lý state riêng cho từng call.

## 1. Xác định ai đang ghi vào observer

Tên `StreamObserver` xuất hiện ở cả hai chiều. Hãy xác định bên nào gọi các method:

| Vị trí | Ai gọi `onNext`? | Quy tắc thread |
| --- | --- | --- |
| Server trả response từ unary/server-streaming handler | Application gọi response observer | Application phải serialize các lần ghi nếu có nhiều producer |
| Server nhận request của client-streaming/bidi | gRPC gọi observer do service trả về | Callback của cùng call được gRPC tuần tự hóa; không giả định thread cố định |
| Client gửi request của client-streaming/bidi | Application gọi request observer do async stub trả về | Application phải serialize các lần ghi |
| Client nhận response từ async stub | gRPC gọi response observer do application cung cấp | Callback của cùng call được gRPC tuần tự hóa; các call khác vẫn có thể đồng thời |

Ví dụ client streaming:

```java
StreamObserver<ImportRequest> requestObserver =
        asyncStub.importProducts(new StreamObserver<ImportSummary>() {
            @Override
            public void onNext(ImportSummary summary) {
                handleSummary(summary);
            }

            @Override
            public void onError(Throwable error) {
                handleFailure(error);
            }

            @Override
            public void onCompleted() {
                handleCompletion();
            }
        });

// Ứng dụng ghi request vào observer được stub trả về.
requestObserver.onNext(firstBatch);
requestObserver.onCompleted();
```

`requestObserver` là đầu ghi của ứng dụng. Nếu nhiều worker cùng gọi nó, ứng dụng chịu trách nhiệm đồng bộ hóa. Observer nhận `ImportSummary` được gRPC gọi callback cho call đó; không cần tự tạo nhiều thread để gọi callback này.

## 2. Vì sao ghi đồng thời gây lỗi?

Một observer có ba loại thao tác chính:

- `onNext(value)`: gửi một message.
- `onError(error)`: kết thúc stream bằng lỗi.
- `onCompleted()`: kết thúc stream thành công.

Các thao tác này phải có thứ tự nhất quán. Những tình huống nguy hiểm thường gặp:

1. Hai producer gọi `onNext` cùng lúc; message có thể không còn theo thứ tự nghiệp vụ.
2. Một thread gọi `onCompleted` trong khi thread khác vẫn gọi `onNext`.
3. Một thread gọi `onError` sau khi thread khác đã hoàn tất bằng `onCompleted`.
4. Producer giữ reference tới observer sau khi RPC đã bị cancel hoặc deadline đã hết hạn.

`onError` và `onCompleted` là terminal signal. Sau khi một trong hai đã được gửi, không gửi thêm message hoặc terminal signal khác. Đồng bộ hóa phải bao phủ cả message lẫn thao tác kết thúc, không chỉ riêng `onNext`.

## 3. Cách đơn giản: serialize bằng một lock

Nếu nhiều thread phải ghi trực tiếp vào cùng observer, có thể bọc observer bằng một lớp đồng bộ hóa. Tất cả thao tác ghi và terminal signal dùng chung một monitor:

```java
import io.grpc.stub.StreamObserver;

public final class SerializedStreamObserver<T>
        implements StreamObserver<T> {

    private final StreamObserver<T> delegate;
    private boolean terminated;

    public SerializedStreamObserver(StreamObserver<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public synchronized void onNext(T value) {
        if (terminated) {
            throw new IllegalStateException("stream is already terminated");
        }
        delegate.onNext(value);
    }

    @Override
    public synchronized void onError(Throwable error) {
        if (terminated) {
            return;
        }
        terminated = true;
        delegate.onError(error);
    }

    @Override
    public synchronized void onCompleted() {
        if (terminated) {
            return;
        }
        terminated = true;
        delegate.onCompleted();
    }
}
```

Wrapper này bảo đảm không có hai lời gọi đồng thời đi vào delegate và không gửi `onNext` sau terminal signal. Nó phù hợp khi thao tác ghi ngắn và số producer ít.

Lock chỉ bảo đảm tuần tự theo thứ tự các thread giành được monitor; nó **không bảo đảm thứ tự nghiệp vụ xác định** giữa các producer cạnh tranh. Nếu message phải theo sequence, hãy gán sequence ở nơi tạo dữ liệu rồi sắp xếp hoặc chuyển qua một single writer. Không thực hiện database/network I/O trong khi giữ lock.

## 4. Khuyến nghị cho nhiều producer: một writer tuần tự

Khi nhiều worker tạo message, thiết kế dễ kiểm soát hơn là để chúng gửi message vào một hàng đợi; một consumer duy nhất gọi observer. Hàng đợi phải có giới hạn:

```java
BlockingQueue<ImportRequest> queue =
        new ArrayBlockingQueue<>(256);

ExecutorService streamWriter =
        Executors.newSingleThreadExecutor();

streamWriter.execute(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            ImportRequest message = queue.take();
            requestObserver.onNext(message);
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        requestObserver.onError(interrupted);
    }
});
```

Đây là khung minh họa; production cần có giao thức dừng writer và gửi terminal signal đúng một lần. Khi producer gọi `queue.offer(message)` mà hàng đợi đầy, phải có policy rõ ràng: chờ trong giới hạn, từ chối producer, giảm tốc nguồn hoặc hủy stream. Không dùng queue không giới hạn và không âm thầm bỏ message.

Chỉ writer được gọi `requestObserver.onNext`, `onError` hoặc `onCompleted`. Khi mọi producer hoàn tất, gửi một lệnh terminal qua cùng hàng đợi để bảo đảm nó được xử lý sau các message đã nhận. Nếu thứ tự giữa nhiều producer có ý nghĩa, cấp sequence trước khi enqueue; thứ tự thread đưa message vào queue có thể không trùng thứ tự nghiệp vụ.

## 5. Callback nhận message không có thread affinity

Ở chiều nhận, gRPC gọi observer callback cho từng call theo thứ tự, nhưng không cam kết tất cả callback của call đó luôn chạy trên cùng một thread. Callback của các RPC khác nhau có thể chạy đồng thời.

Vì vậy:

- Không dựa vào `ThreadLocal` tự tạo để giữ state xuyên suốt các callback.
- Không lưu dữ liệu từng call vào field mutable của singleton service/client.
- Dùng biến cục bộ hoặc một đối tượng state riêng cho mỗi RPC.
- Nếu callback chuyển công việc sang executor tùy chỉnh, propagate gRPC Context và OpenTelemetry Context khi cần.
- Nếu callback cập nhật cache hoặc bộ đếm dùng chung giữa nhiều RPC, cấu trúc dữ liệu đó phải thread-safe.

Ví dụ tạo state riêng cho từng call:

```java
public void getProduct(
        GetProductRequest request,
        StreamObserver<ProductEvent> responseObserver) {

    AtomicLong eventCount = new AtomicLong();
    // eventCount chỉ thuộc RPC hiện tại.
    eventPublisher.subscribe(event -> {
        eventCount.incrementAndGet();
        responseObserver.onNext(toProto(event));
    });
}
```

Ví dụ trên vẫn cần serialize `responseObserver` nếu `eventPublisher` gọi subscriber từ nhiều thread. `AtomicLong` chỉ bảo vệ bộ đếm; nó không làm cho `responseObserver.onNext` trở nên thread-safe.

## 6. Flow control và readiness cũng phải được phối hợp

Tuần tự hóa lời gọi không tự giải quyết backpressure. Producer có thể nhanh hơn network hoặc consumer; nếu cứ enqueue message, bộ nhớ sẽ tăng.

Ở server streaming/bidi, response observer có thể là `ServerCallStreamObserver`. Có thể kiểm tra `isReady()` và đăng ký `setOnReadyHandler` để chỉ phát tiếp khi transport sẵn sàng:

```java
if (responseObserver instanceof ServerCallStreamObserver<?> rawStream) {
    @SuppressWarnings("unchecked")
    ServerCallStreamObserver<ProductEvent> serverStream =
            (ServerCallStreamObserver<ProductEvent>) rawStream;
    serverStream.setOnReadyHandler(() -> {
        if (serverStream.isReady() && !serverStream.isCancelled()) {
            drainBoundedQueue(serverStream);
        }
    });
    serverStream.setOnCancelHandler(this::stopProducer);
}
```

Đoạn minh họa cần được đặt trong handler trước khi bắt đầu gửi message. `drainBoundedQueue` phải bảo đảm chỉ có một drain loop ghi observer tại một thời điểm, kiểm tra `isReady()` trước khi gửi tiếp và không chạy I/O blocking trong on-ready callback.

Ở client streaming/bidi, `ClientCallStreamObserver` cung cấp `isReady()` và `setOnReadyHandler` cho request stream. Có thể dùng `ClientResponseObserver.beforeStart` để lấy request stream control trước khi gửi. Readiness là tín hiệu flow control, không phải khóa đồng bộ; vẫn cần một writer tuần tự.

## 7. Terminal signal, cancellation và deadline

Một stream có thể kết thúc bởi completion, lỗi, cancellation hoặc deadline:

| Tình huống | Việc producer cần làm |
| --- | --- |
| Tất cả message đã gửi | Gửi `onCompleted` đúng một lần |
| Lỗi nghiệp vụ | Gửi `onError` với status phù hợp |
| Client hủy stream | Dừng producer và giải phóng queue/state |
| Deadline hết hạn | Ngừng công việc không còn hữu ích; không tiếp tục enqueue vô hạn |
| Queue đầy | Áp dụng backpressure hoặc fail/cancel theo policy |

Phía server có thể dùng `ServerCallStreamObserver.isCancelled()` và `setOnCancelHandler` để dừng nguồn phát. Phía client cần giữ quyền hủy call nếu ứng dụng không còn cần kết quả. Cancellation của RPC không tự động dừng mọi tác vụ Java mà ứng dụng đã submit; producer cần cancellation token/cờ riêng và kiểm tra nó trong vòng lặp.

Không gọi `onCompleted` đồng thời từ callback `onError`. Hãy có một nơi duy nhất quyết định terminal state, ví dụ state machine per-call với trạng thái OPEN, COMPLETED, FAILED hoặc CANCELLED. Chuyển trạng thái bằng atomic compare-and-set hoặc lock để chỉ một đường kết thúc thắng.

## 8. Những lỗi triển khai thường gặp

- Dùng chung một request observer cho nhiều RPC khác nhau.
- Cho nhiều producer gọi `onNext` đồng thời mà không serialize.
- Chỉ đồng bộ `onNext` nhưng để `onCompleted` hoặc `onError` chạy ngoài lock.
- Nghĩ rằng `AtomicLong` hoặc `volatile` làm observer thread-safe.
- Gửi terminal signal rồi tiếp tục phát message.
- Dùng queue không giới hạn cho streaming producer.
- Dựa vào `isReady()` như một lock thay vì phối hợp readiness với single writer.
- Giữ observer trong field singleton và vô tình dùng nó cho call tiếp theo.
- Không dừng producer khi client cancel hoặc deadline hết hạn.

Một observer riêng cho mỗi RPC và một writer tuần tự cho mỗi stream giúp giới hạn phạm vi state, dễ reasoning và dễ test hơn.

## 9. Kiểm thử thread safety của stream observer

Test cần tạo cạnh tranh thật giữa producer và terminal signal, không chỉ gọi observer tuần tự trong một thread:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Nhiều producer gửi message | Delegate không bị gọi đồng thời |
| Producer và completion chạy cạnh tranh | Không có message sau terminal signal |
| Error và completion chạy cạnh tranh | Chỉ một terminal signal được gửi |
| Sequence nhiều producer | Thứ tự nghiệp vụ được giữ theo quy tắc đã chọn |
| Queue đầy | Producer bị backpressure hoặc stream kết thúc theo policy, không mất message âm thầm |
| Server không ready | Writer dừng drain và tiếp tục khi on-ready |
| Client cancel/deadline | Producer dừng và queue được giải phóng |
| Hai stream đồng thời | Observer và state không bị chia sẻ chéo |
| Callback trên thread khác | Context/state cần thiết vẫn đúng |

Có thể dùng fake `StreamObserver` ghi lại số lời gọi đồng thời lớn nhất và thứ tự message. Assertion quan trọng là `maxConcurrentCalls` bằng 1, terminal count không vượt 1 và không có `onNext` sau terminal. Với flow control, dùng in-process server/channel và stream nhiều message để kiểm tra queue, readiness và cancellation.

## 10. Checklist triển khai

- [ ] Xác định observer là đầu ghi của application hay đầu nhận callback từ gRPC.
- [ ] Mỗi RPC có observer và state riêng.
- [ ] Mọi lời gọi ghi vào cùng observer được serialize.
- [ ] Serialize cả `onNext`, `onError` và `onCompleted`.
- [ ] Dùng single writer/serial executor khi có nhiều producer hoặc cần thứ tự xác định.
- [ ] Queue có giới hạn và có policy khi đầy.
- [ ] Readiness/flow control được phối hợp với writer, không thay thế synchronization.
- [ ] Dừng producer khi cancel, deadline hoặc terminal signal.
- [ ] Không giả định callback của nhiều RPC chạy trên cùng thread.
- [ ] Không giữ observer/state per-call trong field mutable của singleton.
- [ ] Có concurrency test cho message ordering, terminal race, overload và cancellation.

**Tự kiểm tra**

**Câu 1.** Một `StreamObserver` có thể được nhiều thread gọi `onNext` đồng thời không?

*Đáp án:* Không nên. Observer không được bảo đảm thread-safe cho các lời gọi ghi từ application; phải serialize bằng lock hoặc một writer duy nhất.

**Câu 2.** gRPC có bảo đảm callback nhận message của cùng một call luôn chạy trên cùng thread không?

*Đáp án:* Không. Callback của cùng call được điều phối tuần tự, nhưng có thể chạy trên các thread khác nhau theo thời gian. Callback của nhiều RPC cũng có thể chạy đồng thời.

**Câu 3.** Vì sao phải đồng bộ cả `onCompleted` và `onError`?

*Đáp án:* Đây là terminal signal. Nếu không dùng cùng cơ chế đồng bộ với `onNext`, một thread có thể đóng stream trong khi thread khác vẫn gửi message hoặc gửi terminal signal thứ hai.

**Câu 4.** `isReady()` có thay thế lock hoặc single writer không?

*Đáp án:* Không. Nó báo trạng thái flow control của transport, không tuần tự hóa các producer. Ứng dụng vẫn cần một writer duy nhất hoặc đồng bộ hóa.

**Câu 5.** Khi client cancel, các producer Java đã chạy có tự dừng không?

*Đáp án:* Không nhất thiết. Cần cancellation handler/token để dừng producer, ngừng enqueue và giải phóng queue/state.

Thread safety của stream observer phụ thuộc vào quyền sở hữu luồng ghi và cách kết thúc call. Giữ một writer tuần tự cho mỗi stream, serialize cả message lẫn terminal signal, giới hạn queue theo flow control và dừng producer khi cancel/deadline; khi đó streaming trong Spring gRPC tránh được race, mất thứ tự và phát message sau khi call đã kết thúc.
