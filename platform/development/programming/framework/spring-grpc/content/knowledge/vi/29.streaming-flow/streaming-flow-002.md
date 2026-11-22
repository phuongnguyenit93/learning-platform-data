# Inbound và outbound message queue

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **inbound queue** và **outbound queue** theo góc nhìn của một endpoint gRPC.
- Thiết kế hàng đợi có giới hạn để tách callback mạng khỏi xử lý nghiệp vụ.
- Điều tiết inbound message bằng manual flow control và **request(n)**.
- Điều tiết outbound message bằng **isReady()** và **setOnReadyHandler(...)**.
- Bảo đảm thứ tự message, xử lý queue đầy, lỗi, hoàn tất và cancellation.
- Tránh tích lũy dữ liệu không giới hạn trong client-streaming, server-streaming và bidirectional streaming của Spring gRPC.

## 1. Inbound và outbound là gì?

Inbound và outbound được xác định theo góc nhìn của endpoint đang xét:

- **Inbound message** đi từ peer vào endpoint hiện tại.
- **Outbound message** đi từ endpoint hiện tại ra peer.

Với server gRPC, inbound thường là request do client gửi; outbound là response server gửi về client. Với client, chiều này đảo lại: response là inbound, request là outbound.

Trong streaming RPC, một phía có thể nhận hoặc gửi nhiều message. Nếu callback nhận dữ liệu đồng thời phải thực hiện truy vấn, ghi database hoặc gọi service khác, luồng xử lý mạng có thể bị chậm. Nếu producer tạo response nhanh hơn transport gửi đi, dữ liệu chờ có thể tích tụ trong bộ nhớ.

**Message queue ở tầng ứng dụng** tạo ranh giới giữa việc nhận/gửi message và công việc xử lý. Queue cần có giới hạn và chính sách khi đầy; chỉ thêm một queue không tự tạo backpressure nếu producer vẫn tiếp tục đẩy dữ liệu vào đó.

## 2. Kiến trúc inbound/outbound queue

Một luồng bidirectional ở server có thể tổ chức như sau:

~~~mermaid
flowchart LR
  C["Client"] -->|"Inbound messages"| IQ["Bounded inbound queue"]
  IQ --> W["Worker / business logic"]
  W --> OQ["Bounded outbound queue"]
  OQ --> D["Outbound drain"]
  D -->|"StreamObserver.onNext"| C
  D -.->|"isReady / on-ready"| D
~~~

- Inbound callback nhận message và đưa vào inbound queue.
- Worker lấy message ra, xử lý nghiệp vụ rồi tạo response.
- Response được đưa vào outbound queue.
- Một luồng gửi duy nhất lấy response ra khi gRPC báo sẵn sàng.

Hai queue có mục đích khác nhau. Inbound queue hấp thụ dữ liệu vừa nhận để worker xử lý; outbound queue giữ kết quả chờ gửi. Không nên dùng một queue chung cho cả hai chiều vì khó áp dụng giới hạn, thứ tự và chính sách lỗi phù hợp cho từng luồng.

## 3. Queue ứng dụng khác buffer của transport

Một RPC streaming có thể có nhiều tầng lưu dữ liệu:

1. Queue do ứng dụng tạo để chờ xử lý.
2. Hàng đợi nội bộ của gRPC khi message đã được chuyển cho **StreamObserver**.
3. Buffer của HTTP/2 và hệ điều hành.
4. Buffer ở peer nhận.

HTTP/2 flow control giới hạn lượng DATA đang được truyền theo cửa sổ stream và connection. API gRPC như **isReady()** báo trạng thái khả năng gửi ở tầng gRPC. Queue ứng dụng lại quyết định lượng message nghiệp vụ được giữ trong heap.

Vì vậy, flow control của HTTP/2 không tự giới hạn một **ArrayBlockingQueue** do ứng dụng tạo. Tương tự, queue ứng dụng có giới hạn không thay thế HTTP/2 flow control hoặc giới hạn kích thước message.

## 4. Thiết kế inbound queue có giới hạn

Inbound queue lưu các message đã được gRPC chuyển tới callback **onNext**. Nên chọn queue có capacity rõ ràng:

~~~java
BlockingQueue<UploadChunk> inboundQueue =
    new ArrayBlockingQueue<>(32);
~~~

Hoặc dùng **LinkedBlockingQueue** với capacity tường minh. Tránh constructor không giới hạn nếu producer có thể gửi nhanh hơn worker trong thời gian dài.

Trong callback:

~~~java
@Override
public void onNext(UploadChunk chunk) {
    if (!inboundQueue.offer(chunk)) {
        failCall(Status.RESOURCE_EXHAUSTED
            .withDescription("Inbound queue is full"));
        return;
    }
    scheduleWorker();
}
~~~

**offer()** trả về ngay khi queue đầy, cho phép ứng dụng áp dụng chính sách rõ ràng. **put()** có thể chặn callback nhận message; nếu callback chạy trên executor dùng chung của gRPC, việc chặn lâu có thể ảnh hưởng các RPC khác.

Queue đầy không phải tình huống để âm thầm bỏ message. Tùy hợp đồng, có thể:

- Ngừng yêu cầu thêm inbound message bằng manual flow control.
- Từ chối RPC với **RESOURCE_EXHAUSTED**.
- Giảm tốc producer nếu giao thức ứng dụng cho phép.
- Ghi dữ liệu vào một hàng đợi bền vững có quota nếu cần hấp thụ tải lâu hơn.

Chỉ drop message khi semantics nghiệp vụ cho phép mất dữ liệu, chẳng hạn một số loại telemetry best-effort; phải công bố rõ chính sách đó.

## 5. Inbound manual flow control gắn với sức chứa queue

Khi auto inbound flow control bật, gRPC tự yêu cầu message tiếp theo theo cơ chế mặc định. Nếu ứng dụng đưa message vào queue rồi xử lý bất đồng bộ, queue có thể đầy trước khi worker theo kịp.

Với server-side streaming handler, có thể tắt auto request trên **ServerCallStreamObserver** và yêu cầu message theo lượng ứng dụng sẵn sàng xử lý:

~~~java
ServerCallStreamObserver<UploadChunk> inbound =
    (ServerCallStreamObserver<UploadChunk>) requestObserver;

inbound.disableAutoRequest();
inbound.request(1);
~~~

Sau khi xử lý xong một chunk và giải phóng một slot, ứng dụng mới gọi **request(1)** để nhận thêm. Nếu yêu cầu trước **n** message, capacity queue phải đủ cho số message đang được phép gửi tới, cộng phần dự phòng đã được tính toán.

Quy tắc quan trọng:

- Chỉ request thêm khi có chỗ chứa an toàn.
- Không request số lượng lớn hơn capacity còn trống của queue và worker.
- Khi RPC bị cancel hoặc đã kết thúc, dừng request.
- Nếu có nhiều worker, phải tính cả message đang xử lý và message đang nằm trong queue.

**request(n)** điều khiển số message inbound mà gRPC cho phép chuyển lên ứng dụng; nó không tăng trực tiếp HTTP/2 byte window. Transport vẫn quản lý byte-level flow control riêng.

## 6. Xử lý inbound theo một consumer hoặc nhiều consumer

Một consumer duy nhất thường dễ giữ thứ tự:

~~~java
void consumeLoop() {
    while (!cancelled.get()) {
        UploadChunk chunk = inboundQueue.poll();
        if (chunk == null) {
            return;
        }

        process(chunk);
        requestNextMessage();
    }
}
~~~

Trong triển khai thực tế, worker nên được đánh thức bằng executor, semaphore hoặc cơ chế signal thay vì vòng lặp polling bận. Khi dùng manual flow control, **requestNextMessage()** chỉ được gọi sau khi xử lý xong và queue có capacity.

Nhiều consumer có thể tăng throughput nếu các message độc lập, nhưng thời gian xử lý khác nhau có thể khiến kết quả hoàn tất không theo thứ tự nhận. Nếu giao thức yêu cầu thứ tự, dùng một consumer tuần tự hoặc gắn sequence number và sắp xếp lại kết quả trước khi phát outbound.

## 7. Outbound queue và readiness

Outbound queue giữ response chờ gửi khi producer nghiệp vụ tạo dữ liệu nhanh hơn khả năng gửi của gRPC:

~~~java
BlockingQueue<UploadAck> outboundQueue =
    new ArrayBlockingQueue<>(64);
~~~

Với server streaming hoặc bidi streaming, lấy **ServerCallStreamObserver** để kiểm tra readiness:

~~~java
ServerCallStreamObserver<UploadAck> outbound =
    (ServerCallStreamObserver<UploadAck>) responseObserver;

outbound.setOnReadyHandler(this::scheduleDrain);
~~~

**isReady()** cho biết gRPC hiện có thể nhận thêm outbound message mà không vượt ngưỡng buffer nội bộ được kiểm soát bởi transport. Nó không có nghĩa peer đã nhận hoặc xử lý message trước đó.

Khi **isReady()** là false, dừng drain và giữ các response còn lại trong outbound queue. Khi readiness chuyển sang true, on-ready handler đánh thức drain để gửi tiếp.

~~~java
void drain() {
    while (!cancelled.get() && outbound.isReady()) {
        UploadAck next = outboundQueue.poll();
        if (next == null) {
            break;
        }
        outbound.onNext(next);
    }
}
~~~

Đây là thuật toán cốt lõi; ứng dụng cần gọi drain lần đầu nếu observer đã ready, đăng ký on-ready handler và bảo đảm drain không chạy đồng thời trên nhiều thread. Không dùng vòng lặp chờ **isReady()** trở thành true vì sẽ lãng phí CPU.

## 8. Chỉ có một luồng ghi outbound

**StreamObserver** không phải API để nhiều producer thread gọi **onNext**, **onError** và **onCompleted** đồng thời. Hãy gom response từ các producer vào queue và dùng một drain executor hoặc một cơ chế tuần tự hóa duy nhất để phát message.

Một mẫu điều phối:

~~~java
private final AtomicBoolean draining = new AtomicBoolean();

void scheduleDrain() {
    if (!draining.compareAndSet(false, true)) {
        return;
    }

    writerExecutor.execute(() -> {
        try {
            while (!cancelled.get() && outbound.isReady()) {
                UploadAck next = outboundQueue.poll();
                if (next == null) {
                    break;
                }
                outbound.onNext(next);
            }
            completeIfInputFinishedAndQueueEmpty();
        } finally {
            draining.set(false);
            if (!cancelled.get()
                    && outbound.isReady()
                    && (!outboundQueue.isEmpty() || shouldComplete())) {
                scheduleDrain();
            }
        }
    });
}
~~~

Đặt on-ready handler gọi **scheduleDrain()** và cũng gọi **scheduleDrain()** sau khi producer enqueue response. Cờ **draining** tránh nhiều drain task chạy đồng thời. Mọi lời gọi terminal như **onCompleted()** hoặc **onError()** cũng phải được tuần tự hóa với **onNext()** và chỉ phát đúng một lần.

Đoạn mã là khung điều phối; **completeIfInputFinishedAndQueueEmpty()** phải kiểm tra trạng thái hoàn tất bằng biến đồng bộ/atomic và chỉ kết thúc khi producer đã xong, queue rỗng và không còn message đang được gửi.

## 9. Giới hạn queue theo số lượng và dung lượng byte

Capacity theo số message là cần thiết nhưng có thể chưa đủ. 64 message nhỏ chỉ chiếm ít bộ nhớ, trong khi 64 message chứa payload vài megabyte có thể làm heap tăng mạnh.

Nên cân nhắc đồng thời:

- **Maximum message count**: số message tối đa được giữ.
- **Maximum queued bytes**: tổng kích thước ước tính của message đang chờ.
- **Maximum message size**: giới hạn kích thước của một message.
- **Maximum in-flight work**: số tác vụ đang xử lý đồng thời.

Với Protobuf Java, **getSerializedSize()** có thể dùng để ước tính kích thước serialized của message. Đây là ước lượng hữu ích cho ngân sách payload; nó không bao gồm toàn bộ overhead của object, queue node và bản sao trong runtime.

Khi enqueue, kiểm tra cả số lượng lẫn ngân sách byte. Khi dequeue hoặc xử lý xong, giải phóng phần ngân sách tương ứng. Cần bảo đảm cập nhật bộ đếm nguyên tử hoặc được bảo vệ bởi lock để nhiều producer không cùng vượt quota.

## 10. Queue đầy: chọn chính sách theo semantics

Không có một chính sách overflow phù hợp cho mọi RPC:

| Chính sách | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| **Backpressure** | Producer có thể chờ hoặc chỉ gửi tiếp khi được yêu cầu | Cần phối hợp demand/readiness đúng cách. |
| **Reject** | Không thể xử lý tải vượt capacity | Client nhận lỗi và có thể cần retry. |
| **Drop newest** | Dữ liệu mới ít quan trọng, hệ thống ưu tiên giữ lịch sử đang chờ | Mất dữ liệu mới. |
| **Drop oldest** | Chỉ cần trạng thái gần nhất, ví dụ snapshot/telemetry | Mất sự kiện cũ chưa xử lý. |
| **Persist** | Cần hấp thụ tải lâu hơn và có yêu cầu độ bền | Tăng độ phức tạp, độ trễ và chi phí lưu trữ. |

Với lệnh nghiệp vụ, thanh toán hoặc dữ liệu upload, drop thường không phù hợp. Có thể trả **RESOURCE_EXHAUSTED** để client điều chỉnh tốc độ hoặc retry theo chính sách có giới hạn. Với telemetry best-effort, drop có kiểm soát có thể chấp nhận được nếu có metric đếm số message bị bỏ.

Không retry vô hạn khi queue đầy. Retry cần deadline, backoff, giới hạn số lần và semantics idempotent để tránh tạo tải lớn hơn.

## 11. Thứ tự message và đồng bộ trạng thái

gRPC giữ thứ tự message trong một chiều của stream. Tuy nhiên, ứng dụng có thể phá thứ tự đó nếu:

- Nhiều callback/producer cùng thêm response vào queue mà không có quy tắc thứ tự.
- Nhiều worker xử lý song song và hoàn tất khác thứ tự.
- Nhiều thread trực tiếp gọi **onNext()** trên cùng observer.

Nếu thứ tự là yêu cầu nghiệp vụ:

1. Gắn sequence number ở nguồn nếu cần kiểm chứng thứ tự.
2. Chọn một producer/consumer tuần tự, hoặc dùng reorder buffer.
3. Chỉ có một drain writer cho outbound observer.
4. Không phát response có sequence sau khi response trước vẫn đang chờ.

Nếu các message độc lập và thứ tự không quan trọng, có thể xử lý song song, nhưng vẫn cần tuần tự hóa outbound callback và định nghĩa cách client đối chiếu kết quả.

## 12. Hoàn tất, lỗi và cancellation

Queue phải có vòng đời gắn với RPC:

- **onCompleted inbound**: không có thêm request message. Worker có thể tiếp tục xử lý các message đã nhận; chỉ hoàn tất outbound khi công việc xong và outbound queue đã drain.
- **onError inbound**: dừng nhận thêm dữ liệu, áp dụng chính sách cho công việc đang chờ và kết thúc call bằng lỗi phù hợp.
- **cancel**: ngừng producer, hủy tác vụ có thể hủy, giải phóng queue và bộ đếm byte.
- **deadline exceeded**: không tiếp tục tạo response vô ích sau khi call hết hạn.
- **outbound terminal**: không gọi **onNext()** sau **onCompleted()** hoặc **onError()**.

Trên server, có thể đăng ký **setOnCancelHandler(...)** với **ServerCallStreamObserver** để dừng công việc khi client hủy call. Handler không nên chặn lâu; hãy signal cho worker/executor thực hiện cleanup.

Khi call kết thúc, xóa các message còn chờ nếu semantics cho phép. Nếu cần lưu kết quả để client tiếp tục sau reconnect, hãy dùng cơ chế lưu trữ bền vững và cursor/ack ở tầng ứng dụng thay vì giữ queue trong bộ nhớ gắn với một RPC đã kết thúc.

## 13. Kiểm thử và quan sát queue

Các kiểm thử nên xác nhận:

1. Inbound queue không vượt capacity khi producer gửi nhanh.
2. Manual flow control chỉ request thêm khi có slot an toàn.
3. Outbound producer không gọi **onNext()** khi drain chưa được phép chạy.
4. Khi **isReady()** chuyển false rồi true, drain dừng và tiếp tục mà không mất hoặc nhân đôi message.
5. Nhiều producer không làm các lời gọi **onNext()** đồng thời.
6. **onCompleted**, **onError**, cancellation và deadline không để worker hoặc queue tồn tại vô hạn.
7. Queue đầy áp dụng đúng chính sách đã công bố.

Metric hữu ích:

- Số message hiện có và capacity của từng queue.
- Số byte đang chờ.
- Thời gian chờ trung bình và percentile trong queue.
- Số lần queue đầy, số message bị từ chối hoặc drop.
- Số worker đang hoạt động và số tác vụ đang chờ.
- Thời gian outbound không ready và số lần drain được đánh thức.
- Số RPC bị cancel hoặc kết thúc do deadline.

Không ghi toàn bộ nội dung message vào log để chẩn đoán queue. Dùng request ID, kích thước, sequence number và metric tổng hợp; tránh lộ dữ liệu nhạy cảm và tránh log làm tăng tải.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng queue không giới hạn | Heap tăng không kiểm soát khi producer nhanh hơn consumer | Dùng bounded queue và byte budget. |
| Chặn callback **onNext()** bằng **put()** lâu | Chiếm executor nhận RPC, làm chậm các call khác | Dùng **offer()** và chính sách overflow. |
| Auto inbound request trong khi worker xử lý chậm | Queue có thể đầy trước khi xử lý kịp | Dùng manual flow control hoặc giới hạn queue/worker. |
| Gửi outbound bất kể **isReady()** | Tăng buffer và latency | Drain theo readiness callback. |
| Nhiều thread gọi observer trực tiếp | Race condition hoặc sai thứ tự terminal | Một outbound writer tuần tự. |
| Chỉ giới hạn số message | Payload lớn vẫn làm bộ nhớ tăng mạnh | Giới hạn cả số message và byte. |
| Hoàn tất response ngay khi inbound complete | Bỏ sót công việc hoặc response còn trong queue | Chờ worker hoàn tất và outbound queue rỗng. |
| Bỏ qua cancellation/deadline | Tiếp tục xử lý và giữ tài nguyên sau khi call kết thúc | Signal worker dừng và cleanup. |

## 15. Bài tập thực hành

Thiết kế bidirectional RPC nhận lệnh xử lý ảnh và trả trạng thái:

1. Định nghĩa **ProcessImageRequest** và **ProcessImageUpdate**.
2. Thiết kế inbound queue có capacity hữu hạn; giải thích cách chọn capacity theo số message và kích thước payload.
3. Dùng server-side manual flow control để chỉ request message tiếp theo khi worker đã giải phóng slot.
4. Đưa update vào outbound queue và chỉ drain khi **ServerCallStreamObserver.isReady()** là true.
5. Bảo đảm một writer tuần tự gọi **onNext()**, **onError()** và **onCompleted()**.
6. Định nghĩa hành vi khi queue đầy, client hủy call và deadline hết hạn.
7. Đề xuất metric để phát hiện consumer chậm hoặc outbound readiness bị nghẽn.

**Tiêu chí hoàn thành:** thiết kế được hai queue bounded độc lập, điều tiết inbound demand và outbound readiness, bảo toàn thứ tự cần thiết và giải phóng tài nguyên khi RPC kết thúc.

## 16. Ghi nhớ

- Inbound queue giữ message chờ xử lý; outbound queue giữ response chờ gửi.
- Queue ứng dụng là tầng riêng, không thay thế HTTP/2 flow control hoặc buffer nội bộ của gRPC.
- Dùng bounded queue, giới hạn cả số message lẫn byte và xác định rõ chính sách overflow.
- Điều tiết inbound bằng manual flow control và **request(n)** khi cần gắn demand với sức chứa thực.
- Điều tiết outbound bằng **isReady()** và on-ready handler; chỉ có một writer tuần tự cho observer.
- Bảo toàn thứ tự khi nghiệp vụ yêu cầu; worker song song có thể làm kết quả hoàn tất sai thứ tự.
- Hoàn tất, lỗi, cancellation và deadline phải kết thúc worker, queue và mọi tài nguyên liên quan.

Thiết kế inbound và outbound message queue có giới hạn giúp dịch vụ Spring gRPC hấp thụ chênh lệch tốc độ giữa producer và consumer, duy trì thứ tự dữ liệu và bảo vệ bộ nhớ trong các RPC streaming dài hạn.
