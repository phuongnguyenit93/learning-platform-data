# Buffering trong stream observer

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **StreamObserver** là callback contract và xác định những tầng thực sự giữ dữ liệu chờ.
- Phân biệt inbound buffering, outbound buffering, buffer của gRPC transport và flow-control buffer của HTTP/2.
- Thiết kế queue ứng dụng có giới hạn theo số message và dung lượng byte.
- Điều tiết inbound bằng manual flow control và **request(n)**; điều tiết outbound bằng **isReady()**/**setOnReadyHandler()**.
- Tuần tự hóa lời gọi observer, xử lý terminal event, cancellation và queue overflow.
- Chọn chiến lược buffer hoặc batch phù hợp với streaming RPC trong Spring gRPC.

## 1. StreamObserver không phải một message queue

Trong gRPC Java, **StreamObserver<T>** là interface callback với ba tín hiệu chính:

- **onNext(T)**: chuyển một message tới observer.
- **onError(Throwable)**: kết thúc luồng bằng lỗi.
- **onCompleted()**: kết thúc luồng thành công.

Interface này không cung cấp capacity, không định nghĩa một queue ứng dụng có giới hạn và cũng không cam kết rằng mỗi lần gọi onNext() đồng nghĩa message đã được gửi qua mạng hoặc xử lý ở peer.

Trong **SPRING_GRPC**, Spring Boot có thể quản lý vòng đời server và đăng ký service, nhưng semantics buffering vẫn đến từ gRPC Java, HTTP/2 transport và logic ứng dụng. Muốn kiểm soát bộ nhớ, cần xác định rõ message đang được giữ ở tầng nào và ai chịu trách nhiệm dừng producer.

## 2. Những tầng có thể giữ message

Một RPC streaming thường có nhiều vùng đệm:

1. **Inbound queue của ứng dụng**: message đã được callback nhận và được ứng dụng giữ để worker xử lý.
2. **Outbound queue của ứng dụng**: response được tạo nhưng chưa chuyển cho observer.
3. **Buffer nội bộ của gRPC**: message đã được chuyển qua onNext() nhưng chưa được transport ghi hoàn toàn.
4. **HTTP/2 và socket buffer**: byte đang chờ truyền hoặc chờ peer đọc.
5. **Queue phía nhận**: message đã được nhận nhưng ứng dụng peer chưa xử lý.

~~~mermaid
flowchart LR
  P["Producer"] --> OQ["App outbound queue"]
  OQ --> G["gRPC observer / transport buffer"]
  G --> H["HTTP/2 and socket buffers"]
  H --> I["Peer inbound callback"]
  I --> IQ["Peer application queue"]
  IQ --> W["Consumer worker"]
~~~

Các vùng đệm có thể cùng tồn tại. Ví dụ, nếu ứng dụng drain toàn bộ outbound queue vào observer mà không kiểm tra readiness, dữ liệu có thể chuyển từ queue của ứng dụng sang buffer nội bộ gRPC. Queue ứng dụng trông có vẻ rỗng nhưng tổng bộ nhớ đang giữ message vẫn lớn.

Do đó, cần kiểm soát điểm chuyển giao giữa các tầng, thay vì chỉ quan sát kích thước một queue.

## 3. Inbound buffering: message đi vào ứng dụng

Ở server, inbound thường là request message từ client. Ở client, inbound thường là response message từ server. Khi callback onNext() được gọi, gRPC đã chuyển một message đã được parse lên tầng ứng dụng.

Nếu callback chỉ validate nhanh rồi đưa message vào một queue để worker xử lý, queue đó trở thành inbound buffer của ứng dụng:

~~~java
BlockingQueue<UploadChunk> inbound =
    new ArrayBlockingQueue<>(32);

void onChunk(UploadChunk chunk) {
    if (!inbound.offer(chunk)) {
        rejectCall(Status.RESOURCE_EXHAUSTED
            .withDescription("Inbound buffer is full"));
        return;
    }
    scheduleConsumer();
}
~~~

**offer()** cho phép phát hiện queue đầy mà không chặn callback vô thời hạn. Tránh gọi **put()** lâu trên thread callback gRPC; việc chặn executor nhận message có thể ảnh hưởng các RPC khác.

Queue có capacity theo số message chưa đủ nếu payload khác nhau nhiều về kích thước. Nên kết hợp giới hạn số phần tử với byte budget, maximum message size và số worker đang xử lý.

## 4. Điều tiết inbound bằng manual flow control

Nếu ứng dụng nhận message nhanh hơn worker xử lý, queue có thể đầy. Với streaming, có thể gắn số message được phép nhận với sức chứa thực bằng manual inbound flow control.

Ở server, **ServerCallStreamObserver** cho phép tắt auto request và yêu cầu thêm message khi ứng dụng sẵn sàng:

~~~java
ServerCallStreamObserver<UploadResult> call =
    (ServerCallStreamObserver<UploadResult>) responseObserver;

call.disableAutoRequest();
call.request(1);
~~~

Sau khi worker xử lý xong chunk hiện tại và giải phóng slot, ứng dụng mới gọi **call.request(1)** để cho phép chuyển tiếp message tiếp theo. Với nhiều worker, cần tính cả message đang nằm trong queue lẫn message đang được xử lý.

Ở client, **ClientResponseObserver.beforeStart(...)** cung cấp **ClientCallStreamObserver** để điều tiết response inbound:

~~~java
ClientResponseObserver<SubscribeRequest, PriceUpdate> observer =
    new ClientResponseObserver<>() {
        private ClientCallStreamObserver<SubscribeRequest> call;

        @Override
        public void beforeStart(
                ClientCallStreamObserver<SubscribeRequest> requestStream) {
            call = requestStream;
            requestStream.disableAutoRequestWithInitial(1);
        }

        @Override
        public void onNext(PriceUpdate update) {
            consumerExecutor.execute(() -> {
                process(update);
                call.request(1);
            });
        }

        @Override
        public void onError(Throwable error) {
            handleFailure(error);
        }

        @Override
        public void onCompleted() {
            finishConsumption();
        }
    };
~~~

Ví dụ minh họa demand một message tại một thời điểm. Trong code production, cần đồng bộ việc request với trạng thái call, xử lý lỗi từ executor và không request thêm sau cancellation/terminal event.

**request(n)** điều khiển số message inbound được chuyển lên observer. Nó không tăng trực tiếp HTTP/2 byte window; transport vẫn tự quản lý flow control theo byte.

## 5. Outbound buffering: message đi ra khỏi ứng dụng

Ở server, outbound thường là response; ở client, outbound thường là request. Khi producer tạo response nhanh hơn khả năng gửi, ứng dụng có thể giữ chúng trong queue:

~~~java
BlockingQueue<PriceUpdate> outbound =
    new ArrayBlockingQueue<>(128);
~~~

Producer chỉ enqueue; một writer duy nhất chuyển message sang observer. Với **ServerCallStreamObserver**, writer kiểm tra readiness:

~~~java
ServerCallStreamObserver<PriceUpdate> call =
    (ServerCallStreamObserver<PriceUpdate>) responseObserver;

call.setOnReadyHandler(this::scheduleDrain);
~~~

**isReady()** cho biết gRPC hiện có thể nhận thêm outbound message theo ngưỡng readiness của implementation. Nếu trả về false, tạm dừng drain và để message còn lại trong queue ứng dụng. Khi readiness trở lại, callback đánh thức writer.

Client streaming request cũng có thể dùng **ClientCallStreamObserver.isReady()** và **setOnReadyHandler()** để điều tiết việc gửi request message.

## 6. Drain queue mà không tạo thêm buffer vô hạn

Một drain đơn giản:

~~~java
void drain() {
    while (!cancelled.get() && call.isReady()) {
        PriceUpdate next = outbound.poll();
        if (next == null) {
            break;
        }
        call.onNext(next);
    }
}
~~~

Đoạn mã cần được gọi khi producer enqueue message và khi on-ready callback báo có thể gửi tiếp. Trong triển khai thực tế:

- Dùng một executor tuần tự hoặc cơ chế single-writer cho mỗi observer.
- Không để nhiều thread cùng drain queue và gọi onNext().
- Không dùng vòng lặp bận để chờ isReady() thành true.
- Xử lý race giữa lúc drain kết thúc và producer enqueue message mới bằng cách kiểm tra lại queue/readiness khi nhường quyền.
- Tuần tự hóa onNext(), onError() và onCompleted() trên cùng một đường gửi.

**onNext()** trả về không có nghĩa peer đã nhận hoặc xử lý message. Nếu nghiệp vụ cần xác nhận, phải định nghĩa ACK trong protocol ở tầng ứng dụng.

## 7. Giới hạn buffer theo số message và byte

Giới hạn queue chỉ theo số lượng có thể gây bất ngờ. Một queue 100 message với payload 1 KiB khác rất xa queue 100 message với payload 5 MiB.

Nên đặt đồng thời:

| Giới hạn | Ý nghĩa |
| --- | --- |
| **Message capacity** | Số message tối đa trong queue. |
| **Queued byte budget** | Tổng serialized bytes tối đa đang chờ. |
| **Single-message limit** | Kích thước lớn nhất của một message. |
| **In-flight work** | Số message worker đang xử lý đồng thời. |
| **Per-RPC quota** | Tổng dữ liệu hoặc số message trong vòng đời một RPC. |
| **Global quota** | Ngân sách buffer dùng chung toàn service. |

Với message Protobuf Java, **getSerializedSize()** hữu ích để ước lượng byte budget. Kích thước này không bao gồm toàn bộ object overhead, reference, queue node hoặc bản sao tạm thời khi serialize.

Khi enqueue, cập nhật cả message count và byte count một cách nguyên tử. Khi dequeue hoặc hoàn tất xử lý, giải phóng đúng phần quota. Nếu nhiều producer cùng enqueue, cần lock hoặc cơ chế reservation để không vượt ngân sách do race.

## 8. Queue đầy và chính sách overflow

Queue đầy có nghĩa tốc độ producer vượt khả năng consumer trong khoảng thời gian đó. Ứng dụng phải chọn chính sách phù hợp với semantics:

- **Pause/backpressure**: dừng producer hoặc ngừng yêu cầu inbound message; ưu tiên khi cần giữ đủ dữ liệu.
- **Reject**: kết thúc RPC bằng **RESOURCE_EXHAUSTED** khi không thể tiếp nhận thêm.
- **Drop newest**: bỏ message mới nếu dữ liệu mới ít quan trọng hơn dữ liệu đang chờ.
- **Drop oldest**: chỉ giữ trạng thái mới nhất, phù hợp với một số luồng snapshot/telemetry.
- **Persist**: ghi vào kho bền vững có quota nếu cần hấp thụ tải dài hơn.

Không tự ý drop message của lệnh nghiệp vụ, thanh toán hoặc dữ liệu kiểm toán. Với telemetry best-effort, drop có thể chấp nhận nếu có metric và tài liệu hóa rõ.

Không retry vô hạn khi queue đầy. Retry cần deadline, backoff, giới hạn số lần và idempotency để tránh tạo thêm tải hoặc xử lý trùng.

## 9. Buffering và batching không giống nhau

**Buffering** giữ message chờ xử lý hoặc chờ truyền. **Batching** gom nhiều đơn vị công việc thành một nhóm để xử lý cùng lúc, ví dụ ghi nhiều record vào database trong một transaction.

Batching có thể giảm số lần gọi database hoặc chi phí xử lý, nhưng làm tăng độ trễ và bộ nhớ nếu chờ quá nhiều phần tử. Một batcher nên có ít nhất ba ngưỡng:

1. Số message tối đa mỗi batch.
2. Tổng byte tối đa mỗi batch.
3. Thời gian chờ tối đa trước khi flush.

Ví dụ, flush khi đủ 100 record, đủ 512 KiB hoặc đã chờ 50 ms. Giá trị thực tế phải dựa trên tải và mục tiêu latency. Khi stream hoàn tất, cần flush phần batch cuối chưa đủ ngưỡng; khi lỗi/cancel, phải xác định rõ có discard hay persist batch đang dở.

Không gom cả stream vào một danh sách rồi mới xử lý. Cách đó biến một luồng streaming thành buffering toàn bộ, khiến bộ nhớ tăng theo tổng kích thước stream.

## 10. Vòng đời observer và terminal event

Một observer có vòng đời rõ:

- **onNext()** chuyển message trong khi stream còn hoạt động.
- **onError()** kết thúc stream với lỗi.
- **onCompleted()** kết thúc stream thành công.

Sau terminal event, không gọi thêm onNext() hoặc terminal event thứ hai. Với queue bất đồng bộ, điều này đòi hỏi trạng thái call được quản lý đồng bộ để producer không enqueue mãi sau khi RPC kết thúc.

Ở server, **ServerCallStreamObserver.setOnCancelHandler(...)** có thể thông báo client đã hủy call. Khi cancellation hoặc deadline xảy ra:

- Dừng producer/upstream subscription.
- Ngừng nhận hoặc yêu cầu thêm inbound message.
- Hủy worker có thể hủy.
- Xóa queue còn lại theo semantics.
- Giải phóng byte budget, semaphore, file handle và tài nguyên liên quan.

Nếu cần khôi phục sau reconnect, dùng cursor/sequence number và lưu trạng thái bền vững. Queue trong RAM gắn với một observer đã kết thúc không phải cơ chế resume.

## 11. Thread safety và thứ tự message

Không nên giả định mọi implementation **StreamObserver** đều thread-safe. Đặc biệt, nhiều producer cùng gọi onNext() trên một observer có thể gây race, sai thứ tự hoặc xung đột với onCompleted()/onError().

Một mẫu an toàn là:

1. Nhiều producer chỉ ghi vào queue thread-safe.
2. Một writer duy nhất drain queue.
3. Writer kiểm tra readiness trước mỗi message.
4. Writer là nơi duy nhất phát terminal event.

Nếu worker xử lý inbound song song, kết quả có thể hoàn tất khác thứ tự nhận. Khi thứ tự nghiệp vụ quan trọng, dùng một consumer tuần tự hoặc gắn sequence number và reorder trước khi enqueue outbound.

Nếu thứ tự không quan trọng, vẫn cần quy tắc rõ về correlation ID để client ghép response với request tương ứng.

## 12. Quan sát buffering trong production

Các metric hữu ích:

- Inbound/outbound queue depth và capacity.
- Tổng queued bytes và global buffer bytes.
- Queue wait time trung bình, p95/p99.
- Số lần queue đầy, reject hoặc drop.
- Thời gian observer không ready.
- Số lần on-ready callback được kích hoạt.
- Số message đang được worker xử lý.
- Số RPC kết thúc do cancellation, deadline hoặc RESOURCE_EXHAUSTED.

Quan sát riêng từng tầng giúp xác định bottleneck:

- Queue ứng dụng tăng: producer nhanh hơn worker hoặc writer.
- Queue ứng dụng thấp nhưng thời gian not-ready cao: áp lực có thể nằm ở gRPC/HTTP/2/network hoặc peer.
- Inbound callback đến nhanh nhưng xử lý chậm: consumer nghiệp vụ là bottleneck.
- Queue depth thấp nhưng heap vẫn tăng: kiểm tra payload lớn, object retention và các buffer khác.

Không log toàn bộ payload để điều tra. Dùng RPC ID, sequence, message size, queue metrics và status; tránh làm lộ dữ liệu hoặc tăng tải log.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi **StreamObserver** là queue có capacity | Không kiểm soát được lượng message chờ | Tạo bounded queue ở tầng ứng dụng. |
| Chỉ nhìn queue ứng dụng | Bỏ qua buffer nội bộ gRPC và transport | Theo dõi readiness và flow control ở các tầng. |
| Drain toàn bộ queue vào observer | Chuyển áp lực sang buffer gRPC | Drain theo **isReady()**. |
| Queue chỉ giới hạn số message | Payload lớn vẫn có thể chiếm nhiều heap | Thêm byte budget và single-message limit. |
| Dùng callback để xử lý nghiệp vụ nặng | Chặn luồng callback và làm chậm RPC khác | Đưa việc nặng sang worker có giới hạn. |
| Nhiều thread gọi observer trực tiếp | Race condition và sai thứ tự terminal | Một writer tuần tự cho mỗi observer. |
| Batch không có ngưỡng thời gian | Message đầu tiên chờ quá lâu | Có count, byte và time threshold. |
| Không cleanup khi cancel | Queue và worker giữ tài nguyên sau RPC | Hủy producer và giải phóng mọi quota. |

## 14. Bài tập thực hành

Thiết kế một bidirectional RPC nhận sự kiện cảm biến và trả cảnh báo:

1. Tạo inbound queue có giới hạn số message và byte.
2. Tắt auto inbound request; chỉ **request(1)** khi worker đã giải phóng capacity.
3. Tạo outbound queue riêng cho cảnh báo; chỉ drain khi **isReady()** là true.
4. Đảm bảo một writer duy nhất gọi **onNext()**, **onError()** và **onCompleted()**.
5. Thử batching 50 sự kiện hoặc flush sau 100 ms, tùy điều kiện nào đến trước.
6. Định nghĩa chính sách khi queue đầy, client hủy call hoặc deadline hết hạn.
7. Đề xuất metric để phân biệt inbound consumer chậm với outbound transport not-ready.

**Tiêu chí hoàn thành:** giải thích được các tầng buffering, giới hạn được bộ nhớ theo message và byte, điều tiết inbound/outbound đúng API và xử lý trọn vòng đời observer.

## 15. Ghi nhớ

- **StreamObserver** là callback contract, không phải queue ứng dụng có giới hạn.
- Buffer có thể nằm ở ứng dụng, gRPC runtime, HTTP/2/socket và peer nhận.
- Dùng bounded queue, giới hạn cả message count và byte; tránh chuyển toàn bộ backlog sang buffer nội bộ gRPC.
- Điều tiết inbound bằng manual flow control/**request(n)**; điều tiết outbound bằng **isReady()** và on-ready handler.
- Chỉ một writer tuần tự gọi observer; terminal event chỉ được phát một lần.
- Buffering khác batching; batch cần ngưỡng count, byte và thời gian.
- Cancellation, deadline và lỗi phải dừng producer, worker và giải phóng queue/quota.

Quản lý buffering trong stream observer theo từng tầng giúp dịch vụ Spring gRPC giữ bộ nhớ trong giới hạn, duy trì thứ tự message và tiếp tục xử lý ổn định khi tốc độ gửi, nhận và xử lý khác nhau.
