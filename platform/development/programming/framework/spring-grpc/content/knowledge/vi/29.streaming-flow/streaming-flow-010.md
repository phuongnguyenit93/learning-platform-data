# Concurrency trong callback

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu callback gRPC được thực thi trên executor do runtime quản lý và không phụ thuộc vào một thread cố định.
- Phân biệt callback tuần tự với công việc bất đồng bộ mà ứng dụng đưa sang worker pool.
- Bảo vệ trạng thái theo từng RPC và tránh chia sẻ mutable state giữa các call.
- Tuần tự hóa các thao tác trên StreamObserver, giữ thứ tự message và terminal event.
- Dùng executor có giới hạn, manual flow control và readiness để kiểm soát concurrency/backpressure.
- Propagate gRPC Context, xử lý cancellation và kiểm thử race condition trong Spring gRPC.

## 1. Callback gRPC chạy trong mô hình bất đồng bộ

Với async API, gRPC gọi các callback như onNext, onError và onCompleted khi có message hoặc sự kiện kết thúc. Callback được thực thi trên executor do gRPC runtime/transport quản lý; thread cụ thể có thể thay đổi giữa các lần gọi. Không nên dựa vào tên thread, thread-local tự tạo hoặc giả định callback luôn chạy trên thread đã khởi tạo stub/server.

Callback là điểm nối giữa transport và ứng dụng. Nếu callback thực hiện truy vấn database lâu, gọi HTTP đồng bộ, chờ lock hoặc chạy phép tính nặng, nó có thể giữ executor xử lý RPC và làm các call khác chậm theo.

Trong **SPRING_GRPC**, service bean Spring thường được dùng chung giữa nhiều RPC. Vì vậy, xử lý trong callback phải phân biệt trạng thái riêng của từng call với dependency dùng chung như repository hoặc service bean. Không đặt buffer, sequence number hay cờ terminal của một RPC vào field mutable dùng chung của singleton service.

## 2. Callback tuần tự không đồng nghĩa worker của ứng dụng tuần tự

Transport điều phối callback theo contract của call, nhưng khi ứng dụng submit từng message sang một pool nhiều thread, các tác vụ đó có thể chạy đồng thời và hoàn tất sai thứ tự.

Ví dụ:

~~~text
gRPC callback: onNext(A) -> onNext(B) -> onNext(C)
                         |           |           |
                         v           v           v
                    worker-1     worker-2     worker-3
                         |           |           |
                         +---- B hoàn tất trước A ----+
~~~

Thứ tự callback nhận không tự bảo đảm thứ tự xử lý khi worker chạy song song. Nếu message B phụ thuộc vào A, việc xử lý song song có thể làm sai trạng thái nghiệp vụ dù gRPC đã chuyển message theo đúng thứ tự stream.

Trước khi chọn executor, xác định rõ:

- Message có độc lập để xử lý song song không?
- Có yêu cầu giữ thứ tự nhận và thứ tự response không?
- Một RPC được phép có bao nhiêu tác vụ đang chạy?
- Queue chờ worker có capacity và byte budget bao nhiêu?

## 3. Giữ trạng thái riêng cho từng RPC

Service Spring thường là singleton. Các biến như currentUpload, lastSequence, terminated hoặc pendingMessages không nên là field mutable của service nếu chúng thuộc về một call cụ thể.

Tạo một đối tượng session riêng cho mỗi RPC:

~~~java
final class UploadCallState {
    final String uploadId;
    final AtomicBoolean terminated = new AtomicBoolean();
    final AtomicLong nextSequence = new AtomicLong();
    final BlockingQueue<UploadChunk> pending =
        new ArrayBlockingQueue<>(32);

    UploadCallState(String uploadId) {
        this.uploadId = uploadId;
    }
}
~~~

Handler tạo state khi RPC bắt đầu và đóng state khi call kết thúc. Những dependency dùng chung như UploadService, repository và bounded worker pool có thể được inject vào service; dữ liệu thay đổi theo từng call nằm trong UploadCallState.

Không dùng ThreadLocal để giữ state của RPC qua nhiều callback. Các callback có thể chạy trên thread khác nhau, còn thread pool có thể tái sử dụng thread cho call khác.

## 4. Giữ callback ngắn và chuyển việc nặng sang worker

Callback nên thực hiện công việc nhỏ, có thời gian dự đoán được:

1. Kiểm tra trạng thái call và điều kiện đầu vào cơ bản.
2. Đưa message vào queue có giới hạn hoặc chuyển một tác vụ sang executor.
3. Trả quyền điều khiển nhanh cho runtime.

Ví dụ minh họa:

~~~java
@Override
public void onNext(UploadChunk chunk) {
    if (state.terminated.get()) {
        return;
    }

    if (!state.pending.offer(chunk)) {
        terminateWithResourceExhausted();
        return;
    }

    scheduleWorker();
}
~~~

Không gọi offer() rồi bỏ qua kết quả; queue đầy phải kích hoạt backpressure hoặc chính sách reject rõ ràng. scheduleWorker() cũng phải có giới hạn số task và tránh submit một task mới cho mỗi message nếu hàng đợi executor có thể tăng vô hạn.

Không dùng Thread.sleep, Future.get() không timeout hoặc chờ semaphore lâu ngay trong callback. Nếu cần chờ tài nguyên, chuyển việc chờ sang worker có giới hạn và gắn nó với deadline/cancellation của RPC.

## 5. Chọn xử lý tuần tự hay song song

| Mô hình | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| Xử lý trực tiếp trong callback | Xử lý xong message trước khi callback trả về | Công việc rất nhẹ và nhanh. |
| Một serial lane cho mỗi RPC | Message được xử lý tuần tự trên executor dùng chung | Cần giữ thứ tự nhưng không muốn block callback. |
| Worker pool song song | Nhiều message xử lý đồng thời | Message độc lập và thứ tự hoàn tất không quan trọng. |
| Parallel + reorder | Xử lý song song, phát kết quả theo sequence | Cần throughput cao nhưng response phải đúng thứ tự. |

Serial lane không nhất thiết phải tạo một thread riêng cho mỗi RPC. Có thể dùng một executor dùng chung với hàng đợi tuần tự theo call. Cần giới hạn số tác vụ chờ trên mỗi call và toàn service để số RPC lớn không tạo ra số lượng task không kiểm soát.

Nếu xử lý song song, gắn sequence number hoặc correlation ID vào công việc. Khi cần trả kết quả theo thứ tự, dùng reorder buffer có giới hạn và chỉ phát sequence kế tiếp khi đã sẵn sàng.

## 6. Tuần tự hóa thao tác trên StreamObserver

Không giả định một StreamObserver outbound có thể được nhiều thread gọi đồng thời. Nếu nhiều worker gọi onNext, hoặc một worker gọi onCompleted trong lúc worker khác đang gửi, có thể xảy ra race, sai thứ tự và callback sau terminal event.

Mẫu an toàn là nhiều producer chỉ enqueue; một writer duy nhất thực hiện:

- Kiểm tra state còn OPEN.
- Kiểm tra outbound readiness nếu observer hỗ trợ.
- Lấy message từ queue và gọi onNext.
- Phát đúng một onError hoặc onCompleted.

~~~mermaid
flowchart LR
  A["Worker A"] --> Q["Bounded outbound queue"]
  B["Worker B"] --> Q
  C["Worker C"] --> Q
  Q --> W["Single writer"]
  W --> O["StreamObserver"]
  W --> S["Terminal state"]
~~~

Việc tuần tự hóa phải bao trùm cả kiểm tra state và callback. Chỉ kiểm tra AtomicBoolean terminated rồi gọi onNext bên ngoài vùng tuần tự vẫn có race: thread khác có thể kết thúc observer sau lần kiểm tra nhưng trước lời gọi.

## 7. Ví dụ điều phối outbound bằng một writer

Ví dụ dưới đây minh họa một writer tuần tự dùng executor đơn luồng cho một call:

~~~java
final class OutboundWriter<T> {
    private final StreamObserver<T> observer;
    private final Executor serialExecutor;
    private final AtomicBoolean terminal = new AtomicBoolean();

    OutboundWriter(StreamObserver<T> observer, Executor serialExecutor) {
        this.observer = observer;
        this.serialExecutor = serialExecutor;
    }

    void send(T value) {
        serialExecutor.execute(() -> {
            if (!terminal.get()) {
                observer.onNext(value);
            }
        });
    }

    void complete() {
        serialExecutor.execute(() -> {
            if (terminal.compareAndSet(false, true)) {
                observer.onCompleted();
            }
        });
    }

    void fail(Throwable error) {
        serialExecutor.execute(() -> {
            if (terminal.compareAndSet(false, true)) {
                observer.onError(error);
            }
        });
    }
}
~~~

Ở đây serialExecutor phải thực sự tuần tự hóa mọi task của writer. Nếu dùng Executors.newSingleThreadExecutor() riêng cho mỗi call, phải shutdown executor khi RPC kết thúc; cách này đơn giản để minh họa nhưng không phù hợp khi có rất nhiều RPC đồng thời vì tạo quá nhiều executor/queue.

Trong production, ưu tiên serial lane dựa trên bounded shared executor, giới hạn task chờ, xử lý RejectedExecutionException và dừng admission khi call terminal. Không enqueue vô hạn các send() task rồi mới kiểm tra readiness ở bên trong writer.

## 8. Kết hợp concurrency với backpressure inbound

Nếu callback submit mỗi message vào worker pool nhanh hơn tốc độ worker xử lý, queue executor hoặc queue ứng dụng sẽ tăng. Manual flow control cho phép gắn demand inbound với số slot thực sự có sẵn.

Ở server, lấy ServerCallStreamObserver từ response observer:

~~~java
ServerCallStreamObserver<UploadResult> call =
    (ServerCallStreamObserver<UploadResult>) responseObserver;

call.disableAutoRequest();
call.request(1);
~~~

Sau khi worker xử lý xong một chunk và giải phóng slot, mới gọi call.request(1) để cho phép nhận tiếp. Khi có nhiều worker, số message đang xử lý cũng tiêu thụ capacity; không chỉ đếm message đang nằm trong queue.

Ở client, ClientResponseObserver.beforeStart(...) cung cấp ClientCallStreamObserver để gọi disableAutoRequestWithInitial(n) và request(n) cho response inbound. Đây là điều khiển số message; HTTP/2 flow control vẫn điều khiển byte ở transport.

## 9. Kết hợp concurrency với outbound readiness

Với server streaming, ServerCallStreamObserver.isReady() và setOnReadyHandler() giúp writer dừng gửi khi gRPC chưa sẵn sàng nhận thêm response:

~~~java
call.setOnReadyHandler(this::scheduleDrain);

void drain() {
    while (!cancelled.get() && call.isReady()) {
        PriceUpdate update = outboundQueue.poll();
        if (update == null) {
            break;
        }
        writer.onNext(update);
    }
}
~~~

Đoạn mã cần chạy trên cùng serial lane với terminal event. Nếu callback on-ready chạy trên thread khác, nó chỉ nên đánh thức writer; không tự drain song song. Producer cũng cần bị pause khi outbound queue gần đầy, nếu không readiness chỉ dừng transport handoff còn queue ứng dụng tiếp tục tăng.

## 10. Executor phải có giới hạn và chính sách từ chối

Một newFixedThreadPool thường dùng hàng đợi không giới hạn. Số thread được giới hạn nhưng số task chờ có thể tăng mãi nếu tải đầu vào vượt khả năng xử lý.

Với RPC streaming, cân nhắc:

- Thread count tối đa.
- Queue capacity của executor.
- Số task in-flight trên mỗi RPC.
- Tổng task/buffer toàn service.
- Chính sách khi executor từ chối task.
- Cách shutdown và drain khi ứng dụng dừng.

Ví dụ tạo bounded executor:

~~~java
ThreadPoolExecutor workers = new ThreadPoolExecutor(
    8,
    16,
    60,
    TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(256),
    new ThreadPoolExecutor.AbortPolicy());
~~~

AbortPolicy ném RejectedExecutionException khi đã hết thread và queue. Ứng dụng phải bắt tình huống này, ngừng nhận thêm công việc hoặc kết thúc RPC với status phù hợp; không bỏ qua exception và cũng không chạy công việc nặng ngược lại trên callback thread một cách vô tình.

Tránh CallerRunsPolicy nếu task có thể dài: nó có thể khiến callback gRPC thực hiện toàn bộ công việc bị từ chối và block executor transport.

## 11. Propagate gRPC Context qua executor

gRPC Context thường mang deadline, cancellation và metadata gắn với call. Khi callback submit công việc sang executor khác, không nên giả định context tự động hiện diện trên worker thread.

Có thể capture context hiện tại và wrap executor:

~~~java
Context callContext = Context.current();
Executor contextExecutor =
    callContext.fixedContextExecutor(workerPool);

contextExecutor.execute(() -> {
    if (callContext.isCancelled()) {
        return;
    }
    processChunk(chunk);
});
~~~

Việc propagate context giúp worker truy cập đúng context của RPC và kiểm tra cancellation/deadline. Nếu cần truyền MDC hoặc security context của Spring, phải cấu hình cơ chế propagation tương ứng; không giả định gRPC Context tự động sao chép mọi ThreadLocal.

Không giữ Context của RPC lâu hơn vòng đời công việc cần thiết. Khi call kết thúc, task đang chờ phải được hủy hoặc bỏ qua và tham chiếu tới state phải được giải phóng.

## 12. Cancellation và lỗi trong khi có task đang chạy

Khi client hủy call hoặc deadline hết hạn, worker có thể vẫn đang chạy. Cần một cờ trạng thái dùng chung theo call và nối cancellation với:

- Không nhận hoặc enqueue thêm message.
- Hủy upstream subscription.
- Hủy task chưa bắt đầu nếu có thể.
- Báo task đang chạy dừng tại checkpoint an toàn.
- Không phát response sau terminal event.
- Xóa queue và giải phóng byte budget.

Ở server, có thể dùng ServerCallStreamObserver.setOnCancelHandler() để phát tín hiệu:

~~~java
call.setOnCancelHandler(() -> {
    state.cancelled.set(true);
    upstream.cancel();
    workerTasks.forEach(task -> task.cancel(true));
    cleanupPendingBuffers();
});
~~~

Interrupt chỉ có tác dụng nếu worker và dependency hợp tác với interruption. Với I/O hoặc API không hỗ trợ cancel, dùng timeout riêng và kiểm tra trạng thái ở các checkpoint. Cleanup phải idempotent vì cancellation có thể xảy ra gần lúc worker báo lỗi hoặc hoàn tất.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chạy truy vấn hoặc I/O dài trong callback | Giữ executor xử lý RPC và làm call khác chậm | Chuyển sang worker bounded. |
| Đưa task vào pool không giới hạn | Task chờ và bộ nhớ tăng vô hạn | Dùng bounded executor và admission control. |
| Lưu state của RPC trong field singleton | Nhiều call ghi đè dữ liệu của nhau | Tạo state riêng cho từng call. |
| Giả định worker hoàn tất theo thứ tự submit | Response có thể sai thứ tự | Serial lane hoặc sequence/reorder buffer. |
| Nhiều thread gọi observer trực tiếp | Race giữa onNext và terminal event | Một writer tuần tự. |
| Chỉ dùng AtomicBoolean trước callback | Race giữa check và observer call | Tuần tự hóa cả kiểm tra lẫn phát callback. |
| Dùng CallerRunsPolicy cho task nặng | Callback thread có thể bị block | Reject có kiểm soát hoặc executor chuyên dụng. |
| Mất gRPC Context khi chuyển thread | Mất deadline/cancellation context | Wrap task bằng Context executor. |
| Không dừng worker khi client cancel | Tốn tài nguyên sau khi RPC kết thúc | Propagate cancellation và cleanup. |

## 14. Kiểm thử concurrency

Kiểm thử nên chủ động tạo cạnh tranh thay vì chỉ chạy một message tuần tự:

1. Gửi nhiều message nhanh hơn tốc độ worker và xác nhận queue/executor không vượt capacity.
2. Cho worker xử lý chậm để kiểm tra manual inbound demand.
3. Tạo nhiều worker hoàn tất khác thứ tự và xác nhận response vẫn đúng thứ tự nếu hợp đồng yêu cầu.
4. Gọi cancel trong lúc worker đang xử lý; xác nhận không phát response sau terminal event.
5. Làm executor từ chối task và xác nhận RPC kết thúc theo chính sách.
6. Đua onNext với onCompleted/onError; xác nhận chỉ có một thứ tự terminal hợp lệ.
7. Kiểm tra Context/deadline còn đúng trên worker thread.
8. Chạy nhiều RPC đồng thời để phát hiện state bị chia sẻ nhầm giữa các call.

Dùng latch/barrier để tái tạo race có kiểm soát. Tránh dùng Thread.sleep() làm cơ chế đồng bộ của test vì kết quả phụ thuộc lịch scheduler. Kiểm tra cả status, thứ tự message, queue depth và việc giải phóng tài nguyên.

## 15. Quan sát trong production

Các chỉ số hữu ích:

- Callback duration theo phương thức RPC.
- Số task đang chạy và số task chờ trong executor.
- Rejected task count.
- Inbound/outbound queue depth và queued bytes theo call.
- Số worker đang xử lý mỗi RPC.
- Thời gian observer không ready.
- Số RPC bị cancel, deadline exceeded hoặc resource exhausted.
- Số late emission hoặc terminal event bị yêu cầu lặp.

Nếu callback duration tăng, kiểm tra I/O/blocking hoặc lock contention. Nếu executor queue tăng nhưng callback ngắn, worker pool có thể thiếu capacity hoặc consumer đang chậm. Nếu queue thấp nhưng response chậm, xem thêm readiness, transport và peer.

Không log toàn bộ payload. Dùng RPC ID, sequence, queue metrics và status để liên kết sự kiện mà không làm lộ dữ liệu.

## 16. Bài tập thực hành

Thiết kế server-side bidirectional RPC nhận lệnh và trả tiến độ:

1. Tạo state object riêng cho mỗi call; service Spring không giữ mutable state của RPC trong field singleton.
2. Callback inbound chỉ validate nhanh và enqueue vào bounded queue.
3. Dùng manual flow control để chỉ request message khi có capacity.
4. Worker xử lý theo serial lane hoặc song song có sequence, tùy yêu cầu thứ tự.
5. Các worker đưa response vào outbound queue; một writer duy nhất gửi khi isReady().
6. Propagate gRPC Context sang worker và dừng công việc khi cancellation/deadline.
7. Viết test cho queue overflow, executor rejection, race terminal event và nhiều RPC đồng thời.

**Tiêu chí hoàn thành:** callback không bị block bởi công việc nặng, state không rò giữa các RPC, observer được gọi tuần tự, queue/executor có giới hạn và cancellation được truyền tới worker.

## 17. Ghi nhớ

- Callback gRPC chạy trên executor do runtime quản lý; không dựa vào thread cố định.
- Tác vụ được submit sang worker pool có thể chạy đồng thời và hoàn tất sai thứ tự.
- Tạo state riêng cho từng RPC; không lưu mutable call state trong singleton service bean.
- Dùng bounded executor, bounded queue và chính sách rejection rõ ràng.
- Tuần tự hóa thao tác outbound trên StreamObserver, bao gồm kiểm tra state và terminal event.
- Kết hợp manual inbound demand và outbound readiness để giới hạn công việc đang chờ.
- Propagate gRPC Context qua executor và dừng worker khi cancellation/deadline.
- Kiểm thử race, queue overflow, executor rejection và nhiều RPC đồng thời.

Quản lý concurrency trong callback đúng cách giúp dịch vụ Spring gRPC giữ thứ tự message, bảo vệ executor và bộ nhớ, đồng thời tránh race condition khi nhiều streaming RPC hoạt động đồng thời.
