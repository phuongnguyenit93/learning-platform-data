# Giới hạn buffer

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện các lớp buffer trong một luồng xử lý gRPC và biết lớp nào cần giới hạn.
- Phân biệt buffer của transport, message đã deserialize và queue do application quản lý.
- Thiết kế giới hạn theo số phần tử và theo byte để kiểm soát memory thực tế.
- Dùng manual inbound flow control để không nhận message nhanh hơn khả năng xử lý.
- Dùng isReady/on-ready handler để điều tiết response outbound.
- Kết hợp buffer limit với message-size limit, byte quota, concurrency và deadline.
- Xử lý queue đầy, cancellation và cleanup mà không làm mất hoặc xử lý trùng dữ liệu.
- Kiểm thử buffer high-water, backpressure và overload trên grpc-java/Spring gRPC.

## 1. Buffer là gì trong một dịch vụ gRPC?

Trong **SPRING_GRPC**, dữ liệu đi qua nhiều tầng trước khi đến business handler hoặc rời khỏi server. Transport có thể giữ bytes trong socket, TLS và HTTP/2 buffers; grpc-java nhận và deframe gRPC message; protobuf tạo object trong heap; application có thể tiếp tục đưa message vào queue để xử lý bất đồng bộ.

**Buffer** là vùng lưu tạm dữ liệu hoặc công việc đang chờ được xử lý. Buffer giúp hấp thụ chênh lệch tốc độ giữa producer và consumer, nhưng buffer không giới hạn sẽ biến burst thành memory growth. Nếu producer liên tục nhanh hơn consumer, queue tăng cho tới khi heap hoặc direct memory cạn.

Cần xác định rõ buffer nào đang được giới hạn:

| Lớp | Ví dụ | Giới hạn/cơ chế liên quan |
| --- | --- | --- |
| Network/transport | Socket, TLS, HTTP/2 frame và flow-control windows | Cấu hình transport/OS; flow control |
| gRPC message | Bytes đang được deframe/serialize | Max inbound/outbound message size |
| Protobuf/application object | Request, response, decoded byte array | Message-size và field validation |
| Application queue | ArrayBlockingQueue, pending response list | Item capacity và byte budget |
| In-flight work | Task đã submit, message đang xử lý | Concurrency limit và bounded executor |
| Streaming producer | Event source, database cursor, broker subscription | Backpressure, pause/resume và cancellation |

Một giới hạn ở một lớp không tự động giới hạn các lớp khác. maxInboundMessageSize giới hạn kích thước một message nhận vào, nhưng không giới hạn số message đang nằm trong application queue. HTTP/2 flow control điều tiết bytes trên transport, nhưng không bảo đảm business consumer đã xử lý xong message.

~~~mermaid
flowchart TD
    A["Socket / TLS / HTTP2"] --> B["gRPC framing và message"]
    B --> C["Protobuf object"]
    C --> D["Application bounded queue"]
    D --> E["Worker / business consumer"]
    E --> F["Database hoặc downstream"]
    D --> G["Queue đầy: pause, reject hoặc shed"]
    G --> H["Backpressure / RESOURCE_EXHAUSTED"]
~~~

## 2. Vì sao phải giới hạn buffer?

Buffer hữu ích khi producer và consumer có tốc độ khác nhau trong thời gian ngắn. Ví dụ, broker có thể phát burst 2.000 event trong vài giây, trong khi service chỉ xử lý được 500 event mỗi giây. Một queue hữu hạn giúp hấp thụ một phần burst mà không buộc transport callback phải chờ.

Nếu buffer không có giới hạn:

- Heap tăng do protobuf object, byte array và domain object được giữ lại.
- Direct memory tăng do transport/network buffers.
- Queue wait tăng, khiến deadline hết trước khi task bắt đầu.
- Một stream nhanh có thể chiếm tài nguyên của các stream khác.
- Cancellation không giải phóng dữ liệu nếu producer vẫn tiếp tục enqueue.
- Garbage collection tăng và làm latency của mọi RPC xấu đi.
- Khi process bị OOM, toàn bộ instance có thể ngừng phục vụ.

Mục tiêu không phải loại bỏ mọi buffer. Mục tiêu là đặt capacity có chủ đích, có hành vi rõ khi đầy và có thể quan sát high-water mark.

## 3. Giới hạn theo item count chưa đủ

Một ArrayBlockingQueue giới hạn số phần tử, nhưng mỗi phần tử có thể có kích thước khác nhau. Queue chứa 100 message nhỏ có thể nhẹ; 100 message gần 4 MiB có thể giữ hàng trăm MiB payload, chưa tính object overhead.

Vì vậy, buffer thường cần hai giới hạn:

- **Item capacity:** số message/task tối đa trong queue.
- **Byte budget:** tổng kích thước payload được phép giữ trong queue.

Ví dụ queue giới hạn 128 message và 16 MiB payload. Một message phải thỏa cả hai điều kiện mới được nhận. Khi lấy message ra để xử lý hoặc bỏ message, phải giải phóng đúng phần byte budget đã reserve.

Với protobuf generated message, getSerializedSize() cho biết kích thước serialized payload theo byte. Đây là phép đo hữu ích để đặt ngân sách, nhưng không bằng chính xác heap footprint: protobuf object, collection, string, byte array và reference có overhead. Hãy cộng headroom hoặc đo heap thực tế khi load test.

## 4. Byte budget an toàn khi có nhiều producer

Có thể dùng một budget nguyên tử để reserve/release byte cho queue. Kiểm tra current lớn hơn maximum trừ bytes để tránh overflow khi cộng:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class ByteBudget {

    private final long maximumBytes;
    private final AtomicLong usedBytes = new AtomicLong();

    public ByteBudget(long maximumBytes) {
        if (maximumBytes <= 0) {
            throw new IllegalArgumentException(
                    "maximumBytes must be positive");
        }
        this.maximumBytes = maximumBytes;
    }

    public boolean tryReserve(long bytes) {
        if (bytes <= 0 || bytes > maximumBytes) {
            return false;
        }

        while (true) {
            long current = usedBytes.get();
            if (current > maximumBytes - bytes) {
                return false;
            }
            if (usedBytes.compareAndSet(current, current + bytes)) {
                return true;
            }
        }
    }

    public void release(long bytes) {
        if (bytes <= 0) {
            throw new IllegalArgumentException("bytes must be positive");
        }

        while (true) {
            long current = usedBytes.get();
            if (bytes > current) {
                throw new IllegalStateException("Byte budget underflow");
            }
            if (usedBytes.compareAndSet(current, current - bytes)) {
                return;
            }
        }
    }

    public long usedBytes() {
        return usedBytes.get();
    }

    public long remainingBytes() {
        return maximumBytes - usedBytes.get();
    }
}
~~~

Khi enqueue, reserve bytes trước rồi mới đưa phần tử vào queue. Nếu queue offer thất bại, release ngay:

~~~java
int bytes = message.getSerializedSize();

if (!byteBudget.tryReserve(bytes)) {
    return false;
}

if (!pending.offer(new PendingMessage(message, bytes))) {
    byteBudget.release(bytes);
    return false;
}

return true;
~~~

Khi consumer lấy phần tử khỏi queue, cần quyết định rõ thời điểm release. Nếu message vẫn được giữ trong lúc xử lý, release sau khi xử lý xong; nếu queue budget chỉ đo dữ liệu chờ và worker có ngân sách riêng, release ngay khi dequeue rồi reserve vào in-flight budget. Không được release sớm trong khi object vẫn còn được giữ mà không có budget khác.

CAS trong release tránh trạng thái tổng tạm thời bị âm khi nhiều producer/consumer chạy đồng thời. Tuy nhiên, counter tổng không thể nhận ra một reservation cụ thể đã bị release lặp nếu vẫn còn reservation khác. Trong code production, bọc mỗi reservation bằng lease có AtomicBoolean/close idempotent và gắn lease đó với đúng phần tử. Không cho nhiều nhánh complete/error/cancel cùng release một reservation. Nếu cần giới hạn cả queue lẫn worker đang xử lý, quản lý queue bytes và in-flight bytes riêng hoặc dùng một tổng budget xuyên suốt.

## 5. Bounded queue và hành vi khi queue đầy

Queue cần capacity hữu hạn. Ví dụ:

~~~java
BlockingQueue<PendingMessage> pending =
        new ArrayBlockingQueue<>(128);
~~~

Khi offer trả false, queue đã đầy. Hãy chọn policy theo contract:

| Hành vi | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| Pause inbound reads | Producer có thể bị backpressure | Cần resume đúng lúc và không deadlock |
| Reject stream/call | Quota cứng đã hết | Client cần hiểu RESOURCE_EXHAUSTED |
| Drop theo policy | Chỉ với telemetry/event có semantics cho phép mất | Có thể mất dữ liệu; phải đo và công bố |
| Persist to durable storage | Cần tiếp nhận burst dài hơn memory budget | Tăng latency và chi phí storage |
| Block callback thread | Hầu như không phù hợp với gRPC callback | Có thể block transport và gây starvation |

Không dùng queue không giới hạn hoặc put() blocking trong gRPC callback nếu điều đó có thể block transport executor. Không dùng CallerRunsPolicy để chạy task nặng ngay trên callback thread. Nếu queue đầy, cần pause producer, từ chối có kiểm soát hoặc chuyển dữ liệu sang durable queue.

Không drop message một cách im lặng với command, payment, upload hoặc dữ liệu cần đảm bảo đầy đủ. Nếu hệ thống cho phép drop telemetry, cần xác định rõ sampling/drop policy và metric dropped count.

## 6. Inbound streaming: manual flow control để giới hạn buffer

Với client-streaming hoặc bidirectional streaming, server có thể chủ động điều khiển số request message được phép gửi tiếp. grpc-java cung cấp ServerCallStreamObserver.disableAutoRequest() để tắt auto inbound flow control; application gọi request(n) khi có capacity.

Mẫu xử lý khái niệm cho client-streaming:

~~~java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {

    ServerCallStreamObserver<UploadResult> call =
            (ServerCallStreamObserver<UploadResult>) responseObserver;

    call.disableAutoRequest();
    call.request(1);

    return new StreamObserver<>() {
        private boolean terminal;

        @Override
        public synchronized void onNext(UploadChunk chunk) {
            if (terminal || call.isCancelled()) {
                return;
            }

            processChunkAndReleaseCapacity(chunk);

            if (!terminal && !call.isCancelled()) {
                call.request(1);
            }
        }

        @Override
        public synchronized void onError(Throwable error) {
            if (!terminal) {
                terminal = true;
                cleanupUpload();
            }
        }

        @Override
        public synchronized void onCompleted() {
            if (terminal) {
                return;
            }
            terminal = true;
            finishUpload(responseObserver);
            cleanupUpload();
        }
    };
}
~~~

Ví dụ minh họa xử lý tuần tự ngay trong callback. Nếu xử lý blocking, không giữ callback thread lâu; hãy chuyển task sang bounded worker executor và chỉ gọi request(1) sau khi worker xử lý xong, giải phóng buffer và còn capacity. Nếu cho phép nhiều task in-flight, request ban đầu chỉ nên bằng số slot đã reserve, không phải một con số tùy ý lớn.

request(n) là điều khiển số message, không phải ngân sách byte. Kết hợp nó với max inbound message size và byte budget để một message lớn không làm vượt memory budget. Gọi request tiếp theo quá sớm sẽ làm mất tác dụng backpressure.

## 7. Outbound streaming: isReady và on-ready handler

Ở chiều server gửi nhiều response, ServerCallStreamObserver.isReady() cho biết transport hiện có khả năng nhận thêm dữ liệu theo cơ chế flow control. setOnReadyHandler() đăng ký callback khi trạng thái readiness thay đổi sang sẵn sàng.

~~~java
ServerCallStreamObserver<EventResponse> call =
        (ServerCallStreamObserver<EventResponse>) responseObserver;

ArrayBlockingQueue<EventResponse> pending =
        new ArrayBlockingQueue<>(128);

call.setOnReadyHandler(() -> {
    while (call.isReady()) {
        EventResponse next = pending.poll();
        if (next == null) {
            break;
        }
        call.onNext(next);
    }
});
~~~

Đây là skeleton minh họa; production code cần bảo đảm chỉ một producer/serialized drain gọi onNext tại một thời điểm và không thực hiện công việc blocking trong on-ready callback. Khi producer enqueue response đầu tiên, hãy kích hoạt drain ngay nếu call đang ready; không chỉ chờ callback chuyển trạng thái, vì transport có thể đã ready từ trước khi queue có dữ liệu. Nếu queue trống, producer có thể tiếp tục lấy dữ liệu từ nguồn; nếu queue đầy, phải pause source hoặc áp dụng policy đã định.

isReady() không cho biết chính xác còn bao nhiêu byte trống trong transport buffer. Nó là tín hiệu readiness, không phải phép đo memory hay giới hạn byte. Vẫn cần bounded application queue và byte budget. Nếu response object có kích thước thay đổi, chỉ giới hạn 128 item không bảo đảm tổng memory.

Với producer bất đồng bộ, dùng một drain loop tuần tự và kiểm tra isReady() trước mỗi lần phát. Khi client cancel, hủy subscription/producer và bỏ queue pending. Không phát onNext sau terminal event.

## 8. Flow control, buffer limit và message-size limit là ba cơ chế khác nhau

| Cơ chế | Giới hạn điều gì? | Không giải quyết điều gì? |
| --- | --- | --- |
| Max inbound/outbound message size | Byte của một gRPC message | Tổng message hoặc queue của stream |
| HTTP/2/gRPC flow control | Bytes đang truyền/in-flight theo stream và connection | Số task đang chờ ở application |
| Application buffer limit | Item và/hoặc bytes được application giữ | Transport buffers và message parsing trước handler |
| Message count limit | Tổng số message trong một RPC | Kích thước từng message |
| Stream concurrency limit | Số RPC đang mở | Queue bytes của từng RPC |
| Deadline | Thời gian giữ call/tài nguyên | Memory cap tức thời |

Không nên tăng HTTP/2 flow-control window để sửa application queue đầy. Window lớn hơn có thể cho phép nhiều bytes in-flight và tăng memory pressure. Cũng không nên giảm window rồi giả định application đã có backpressure đúng; cần điều khiển producer/consumer ở tầng ứng dụng.

Một thiết kế tốt đặt giới hạn ở cả nơi dữ liệu được nhận, nơi dữ liệu được giữ và nơi dữ liệu được xử lý.

## 9. Tính memory budget theo stream và theo instance

Để chọn buffer capacity, ước lượng memory giữ bởi mỗi stream và tổng số stream đồng thời:

\[
M_{\text{instance}} \approx
M_{\text{base}} +
N_{\text{streams}} \times
(M_{\text{state}} + M_{\text{inflight}} + M_{\text{queue}})
\]

Trong đó:

- \(M_{\text{base}}\): heap/direct memory nền của process, cache và framework.
- \(N_{\text{streams}}\): số streaming RPC đồng thời.
- \(M_{\text{state}}\): state, principal, subscription và callback của mỗi stream.
- \(M_{\text{inflight}}\): message đang được xử lý và buffer tương ứng.
- \(M_{\text{queue}}\): dữ liệu đang chờ trong application queue.

Công thức là mô hình ước lượng. Protobuf object và Java collection có overhead; direct memory của Netty khác heap; compression có thể làm payload nở khi giải nén. Đo memory trong load test với payload gần giới hạn và concurrency gần production.

Nếu mỗi stream có queue 4 MiB và server cho phép 500 stream, riêng queue budget lý thuyết đã lên tới 2 GiB. Vì vậy, capacity per-stream phải được nhân với concurrency khi tính tổng memory. Cần có global cap để tổng các queue không vượt ngân sách instance.

Không cộng trùng một vùng memory vào nhiều budget; xác định thời điểm ownership chuyển từ transport sang application và từ queue sang worker. Dành headroom cho burst, garbage collection, response buffers và hoạt động quản trị.

## 10. Cancellation và cleanup buffer

Khi client hủy stream hoặc deadline hết, server phải dừng producer và giải phóng dữ liệu đang chờ:

~~~java
call.setOnCancelHandler(() -> {
    upstreamSubscription.cancel();
    pending.clear();
    releaseAllOutstandingReservations();
    stopProducer();
});
~~~

Đoạn code minh họa cần có cơ chế idempotent. Nếu consumer đồng thời dequeue message trong lúc cancel xóa queue, mỗi reservation chỉ được release đúng một lần. Dùng lease/atomic state cho từng entry hoặc một owner duy nhất quản lý queue lifecycle.

Các tài nguyên cần cleanup:

- Pending message queue và byte reservations.
- Broker/database subscription hoặc cursor.
- Scheduled task và heartbeat.
- Future/task đang chờ trong executor.
- Concurrency permit của stream.
- Temporary file hoặc staging buffer.
- Context/reference giữ principal hoặc request payload.

Khi complete/error/cancel, đặt terminal state trước khi cleanup để producer không enqueue thêm. Không gọi onNext sau onError hoặc onCompleted. Nếu task đang chạy không thể hủy ngay, task phải kiểm tra cancellation trước khi commit side effect hoặc phát response.

## 11. Queue đầy: overload, retry và durable buffering

Khi application buffer đầy, quyết định phụ thuộc semantics của dữ liệu:

- Với command hoặc upload, dừng nhận message và trả lỗi rõ ràng nếu không thể backpressure.
- Với subscription event có thể resume, pause source và lưu cursor; nếu quota cứng hết, kết thúc stream để client reconnect.
- Với telemetry có thể drop, áp dụng sampling/drop policy có metric và contract.
- Với tác vụ phải tồn tại sau khi RPC kết thúc, ghi vào durable queue/job store thay vì giữ vô hạn trong memory.

RESOURCE_EXHAUSTED phù hợp khi stream hoặc buffer vượt quota/capacity. UNAVAILABLE có thể dùng nếu service tạm thời không thể nhận công việc theo contract; chọn mapping ổn định. Không dùng PERMISSION_DENIED cho buffer full.

Client không nên retry ngay trong vòng lặp nhanh. Dùng exponential backoff, jitter và cursor/sequence để resume. Với operation có side effect, dùng idempotency key để tránh xử lý trùng khi client không biết message cuối đã commit hay chưa.

Durable buffering cũng cần quota disk, retention, retry limit và dead-letter policy. Chuyển mọi thứ từ memory sang disk mà không giới hạn chỉ chuyển resource exhaustion sang ổ đĩa.

## 12. Buffer trong executor và downstream

Một RPC có thể đi qua nhiều queue: gRPC callback dispatch, application executor, HTTP client connection pool, database pool và broker client. Mỗi queue cần capacity và timeout riêng.

Nếu application executor queue có 500 task nhưng database pool chỉ có 20 connection, task có thể xếp hàng tiếp ở database layer. Nhiều queue nối tiếp làm latency khó dự đoán và giữ request lâu. Ưu tiên giới hạn admission ở đầu luồng và tránh submit task vượt capacity downstream.

Khi queue wait cộng với thời gian xử lý dự kiến lớn hơn deadline còn lại, bỏ task trước khi bắt đầu. Không dùng CallerRunsPolicy để biến queue đầy thành việc chạy business logic trên gRPC callback thread. Dùng bounded executor, rejection rõ ràng và status phù hợp.

Theo dõi queue depth ở từng tầng để xác định bottleneck. Một queue thấp không có nghĩa toàn hệ thống không bị buffer pressure; dữ liệu có thể đang chờ ở network, downstream client hoặc broker.

## 13. Quan sát buffer và high-water mark

Các metric nên có:

- Item count hiện tại, capacity và high-water mark của từng queue.
- Reserved bytes, maximum bytes và byte high-water mark.
- In-flight message/task count.
- Số lần queue offer thất bại hoặc buffer budget bị từ chối.
- Số inbound message được request/pause/resume.
- Thời gian message nằm trong queue và processing latency.
- Outbound readiness stall duration và số lần producer pause.
- Số stream cancel khi queue đang có dữ liệu.
- Heap, direct memory, allocation rate và GC pause.
- RESOURCE_EXHAUSTED theo method/quota group.

Không dùng stream ID, user ID hoặc tenant ID tùy ý làm metric label vì cardinality có thể tăng không kiểm soát. Dùng method, direction, workload class và quota tier; log/trace đã redaction để điều tra một call cụ thể.

Cảnh báo khi queue depth hoặc reserved bytes duy trì gần capacity, high-water mark tăng liên tục, rejection tăng hoặc queue wait tiến gần deadline. Một buffer thường xuyên đầy là dấu hiệu producer/consumer mất cân bằng, không chỉ là lý do tăng capacity.

## 14. Kiểm thử giới hạn buffer và backpressure

Test nên xác minh cả capacity lẫn vòng đời reservation:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Queue còn slot và byte budget | Message được enqueue |
| Queue đầy | Offer thất bại hoặc admission bị pause |
| Queue còn slot nhưng byte budget hết | Message bị từ chối |
| Dequeue và xử lý xong | Byte reservation được release đúng |
| Enqueue thất bại sau reserve | Reservation được rollback |
| Inbound flow control bật | Server chỉ nhận số message đã request |
| Consumer xử lý xong | Server request thêm message |
| Outbound observer không ready | Producer không tiếp tục phát vô hạn |
| Client cancel | Queue, subscription và reservation được cleanup |
| Nhiều stream đồng thời | Budget từng stream và global budget không bị vượt |
| Message gần max size | Buffer memory vẫn trong ngân sách |
| Deadline hết khi message đang chờ | Task không tạo side effect sau terminal state |

Dùng deterministic test với queue capacity nhỏ, byte budget nhỏ và latches để giữ consumer bận. Không dùng Thread.sleep làm cơ chế đồng bộ chính. Test N+1 item, byte vừa đủ và byte vượt một đơn vị để kiểm tra boundary.

In-process gRPC test phù hợp để kiểm tra application queue, counter và cancellation logic. Đối với isReady, HTTP/2 window và transport buffer behavior, bổ sung integration test bằng đúng Netty transport/version; in-process transport có thể không mô phỏng đầy đủ network backpressure.

Trong Spring application test, xác minh executor, interceptor và streaming service được wiring qua application context thật. Đo heap/direct memory trong load test riêng để xác nhận capacity đã chọn phù hợp với deployment.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ giới hạn item count | Message lớn làm tổng memory vượt budget | Thêm byte budget |
| Chỉ giới hạn max message size | Nhiều message nhỏ tích lũy vô hạn | Bounded queue và stream quota |
| Dùng queue vô hạn | Heap tăng tới OOM | Queue capacity hữu hạn |
| Gọi put/block trong callback | Block gRPC executor và gây starvation | Manual flow control hoặc reject |
| Gọi request tiếp ngay sau submit | Consumer chưa xử lý nhưng message tiếp tục vào | Request sau khi capacity được giải phóng |
| Bỏ qua isReady khi phát response | Transport/application buffers tăng | Bounded outbound queue và on-ready drain |
| Xem isReady là số byte còn trống | Ước lượng sai memory | Xem đây là readiness signal, giữ byte budget riêng |
| Release reservation khi dequeue dù worker còn giữ object | Budget báo thấp hơn memory thật | Release khi object được thả hoặc chuyển sang in-flight budget |
| Cleanup queue không idempotent | Double release hoặc leak | Lease/terminal guard |
| Chỉ test in-process | Bỏ sót transport flow-control behavior | Thêm Netty integration test |

## 16. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo bounded queue 128 item và byte budget 16 MiB cho một streaming method.
2. Reserve serialized size trước enqueue; rollback reservation nếu queue offer thất bại.
3. Dùng manual inbound flow control để chỉ request message tiếp theo khi worker có capacity.
4. Dùng ServerCallStreamObserver.isReady/on-ready handler để phát outbound response có kiểm soát.
5. Thêm cancellation handler để dừng producer, clear queue và release reservation.
6. Kết hợp per-stream budget với global stream concurrency và max inbound message size.
7. Ghi metric item count, reserved bytes, high-water mark và rejection count.
8. Viết unit/in-process tests cho queue full, byte full, N+1, cancellation và nhiều stream đồng thời; bổ sung Netty test cho readiness/flow control.

### Câu hỏi tự kiểm tra

**1. Vì sao giới hạn số item chưa đủ?**  
Vì kích thước mỗi message khác nhau; một queue ít item nhưng payload lớn vẫn có thể giữ quá nhiều memory.

**2. getSerializedSize() có bằng heap footprint không?**  
Không. Nó đo serialized protobuf payload; object graph và buffer có overhead riêng.

**3. request(n) giới hạn byte hay message?**  
Nó yêu cầu số message inbound tiếp theo; cần kết hợp message-size limit và byte budget.

**4. isReady() cho biết điều gì?**  
Transport hiện có thể nhận thêm response theo flow-control state; nó không cung cấp chính xác số byte buffer còn trống.

**5. Khi nào release byte reservation?**  
Khi dữ liệu không còn được giữ trong phạm vi budget đó, hoặc khi ownership được chuyển sang một budget khác.

**6. Queue đầy nên block callback thread không?**  
Không nên. Dùng manual flow control, pause producer hoặc từ chối có kiểm soát.

**7. RESOURCE_EXHAUSTED phù hợp khi nào?**  
Khi buffer/stream quota đã đạt giới hạn và service không thể nhận thêm dữ liệu theo contract.

**8. Vì sao cần Netty integration test ngoài in-process test?**  
Để xác minh readiness, HTTP/2 flow control và transport buffer behavior thực tế.

## Tổng kết

Giới hạn buffer cần được áp dụng ở đúng tầng: transport, gRPC message, protobuf object và application queue. Queue phải có capacity hữu hạn theo item và byte; với streaming, manual inbound flow control giúp server chỉ nhận thêm message khi consumer có chỗ, còn outbound isReady/on-ready handler giúp producer tôn trọng transport readiness. Kết hợp buffer budget với message-size, total-byte, stream-concurrency và deadline limits. Khi đầy, pause hoặc reject rõ ràng; cancellation phải dừng producer và giải phóng queue/reservation đúng một lần. Theo dõi high-water mark và kiểm thử cả application logic lẫn Netty transport để tránh memory growth và overload dây chuyền.

