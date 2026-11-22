# Lỗi giữa stream và giải phóng buffer

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả điều gì xảy ra khi một streaming RPC gặp lỗi sau khi đã trao đổi một số message.
- Phân biệt lỗi stream, half-close, cancellation và deadline.
- Kết thúc response bằng đúng một terminal event và ngăn producer tiếp tục gửi.
- Xác định quyền sở hữu của message, queue entry và buffer trong ứng dụng, gRPC runtime và Netty.
- Giải phóng queue, byte budget, subscription và tài nguyên tham chiếu đúng một lần.
- Kiểm thử lỗi giữa stream để phát hiện memory leak, late emission và dữ liệu bị xử lý sai.

## 1. Lỗi giữa stream khác lỗi trước khi RPC bắt đầu

Unary RPC thường có một request và một response. Với streaming RPC, nhiều message có thể đã được gửi hoặc xử lý trước khi lỗi xuất hiện. Ví dụ, một upload gồm nhiều chunk có thể lưu được một phần dữ liệu rồi gặp lỗi checksum ở chunk tiếp theo; một server-streaming RPC có thể gửi vài bản cập nhật trước khi nguồn dữ liệu bị ngắt.

Khi lỗi xảy ra giữa stream, gRPC kết thúc call bằng status lỗi. Client có thể đã nhận một số message trước khi callback lỗi được gọi. Những message đã được xử lý ở client không tự động bị rollback khi stream thất bại.

Vì vậy, ứng dụng phải xác định rõ:

- Phần dữ liệu nào đã được xác nhận hoặc lưu bền vững.
- Phần dữ liệu nào chỉ nằm trong buffer và chưa được chuyển giao.
- Tài nguyên nào cần dừng hoặc giải phóng.
- Client có thể retry toàn bộ RPC hay phải resume từ sequence/offset đã xác nhận.

Trong **SPRING_GRPC**, điều này quan trọng với upload/download theo chunk, event stream và bidirectional RPC chạy lâu. Một terminal error đúng status nhưng để producer, queue hoặc buffer tiếp tục sống vẫn là lỗi lifecycle.

## 2. Điều gì xảy ra với message đã gửi trước lỗi?

Giả sử server phát ba message rồi gặp lỗi:

~~~text
Server -> Client: onNext(A)
Server -> Client: onNext(B)
Server -> Client: onNext(C)
Server -> Client: onError(UNAVAILABLE)
Client: onNext(A), onNext(B), onNext(C), onError(...)
~~~

Đây là trình tự có thể quan sát nếu ba message đầu đã được chuyển tới client trước terminal status. Tuy nhiên, gọi onNext không phải ACK nghiệp vụ: sender không thể kết luận peer đã xử lý hoặc lưu bền vững message chỉ vì lời gọi onNext đã trả về.

Nếu lỗi xảy ra khi một số message vẫn còn trong buffer nội bộ, không nên giả định tất cả đều đã đến ứng dụng client. Transport có thể kết thúc stream trước khi phần dữ liệu đang chờ được chuyển hết.

Do đó, với dữ liệu cần bảo đảm giao nhận, hãy định nghĩa ACK, sequence number, idempotency key hoặc cursor ở tầng ứng dụng. Terminal status chỉ mô tả kết quả của RPC; nó không cung cấp transaction rollback cho các message đã xử lý.

## 3. Phân biệt lỗi, half-close, cancellation và deadline

Các tình huống này có ý nghĩa khác nhau:

| Tình huống | Ý nghĩa | Hành động chính |
| --- | --- | --- |
| **Stream error** | Một phía kết thúc chiều RPC bằng lỗi | Gửi/nhận status lỗi, dừng producer và cleanup. |
| **Half-close** | Một phía báo không gửi thêm message ở chiều request | Xử lý nốt dữ liệu đã nhận; chiều response vẫn có thể hoạt động. |
| **Cancellation** | Client hoặc runtime hủy call đang hoạt động | Dừng công việc nền và giải phóng tài nguyên; không cố gửi thêm response. |
| **Deadline exceeded** | Thời hạn RPC hết trước khi hoàn tất | Dừng tác vụ không còn hữu ích và giải phóng buffer. |
| **Successful completion** | Chiều response kết thúc thành công | Drain dữ liệu hợp lệ còn chờ rồi gọi onCompleted đúng một lần. |

Đặc biệt, request observer nhận onCompleted ở client-streaming chỉ báo client đã gửi hết request. Server vẫn có thể xử lý chunk cuối, phát response tổng kết và kết thúc response observer.

Không coi cancellation là thành công và không gọi onCompleted để che một lỗi đã xảy ra.

## 4. Chọn status phù hợp khi lỗi xảy ra giữa stream

Server nên ánh xạ lỗi theo nguyên nhân, không dùng một status chung cho mọi trường hợp:

| Nguyên nhân | Status thường phù hợp |
| --- | --- |
| Dữ liệu chunk sai định dạng hoặc vi phạm quy tắc đầu vào | INVALID_ARGUMENT |
| Tài nguyên hoặc queue vượt quota | RESOURCE_EXHAUSTED |
| Tài nguyên được yêu cầu không tồn tại | NOT_FOUND |
| Lỗi phụ thuộc tạm thời như upstream không khả dụng | UNAVAILABLE |
| Lỗi không dự kiến trong xử lý nội bộ | INTERNAL |

Ví dụ kết thúc server-streaming khi nguồn upstream bị lỗi:

~~~java
responseObserver.onError(
    Status.UNAVAILABLE
        .withDescription("Update source is temporarily unavailable")
        .asRuntimeException());
~~~

Status là terminal event. Sau khi gọi onError, dừng producer, hủy subscription và không gọi thêm onNext hoặc onCompleted trên observer đó. Không đưa token, nội dung payload hoặc stack trace nội bộ vào description gửi cho client.

Nếu lỗi xảy ra sau khi response đã hoàn tất, không thể đổi kết quả RPC đã kết thúc. Ghi nhận lỗi muộn bằng log/metric hoặc xử lý bằng một workflow riêng.

## 5. Buffer nằm ở nhiều tầng

Khi xử lý lỗi giữa stream, cần phân biệt những nơi có thể còn giữ dữ liệu:

1. **Application queue**: message đang chờ worker hoặc writer.
2. **In-flight work**: message đã lấy khỏi queue nhưng worker vẫn đang xử lý.
3. **gRPC runtime buffer**: message đã chuyển cho observer nhưng chưa được ghi hết xuống transport.
4. **HTTP/2 và socket buffer**: byte đang chờ truyền hoặc chờ peer đọc.
5. **Peer application queue**: message đã đến peer nhưng ứng dụng chưa xử lý.

~~~mermaid
flowchart LR
  P["Producer"] --> Q["Application queue"]
  Q --> W["In-flight worker"]
  W --> G["gRPC runtime buffer"]
  G --> H["HTTP/2 / socket"]
  H --> R["Peer receiver"]
  E["Error / cancel / deadline"] -.-> P
  E -.-> Q
  E -.-> W
  E -.-> G
~~~

Ứng dụng chỉ trực tiếp quản lý queue và công việc do mình tạo. gRPC runtime và transport quản lý buffer nội bộ của chúng. Không xóa hoặc giải phóng buffer nội bộ của gRPC bằng API Netty tùy tiện.

Queue ứng dụng rỗng không có nghĩa toàn bộ dữ liệu đã đến peer; ngược lại, transport kết thúc cũng không tự giải phóng subscription, file handle hoặc object mà ứng dụng vẫn giữ tham chiếu.

## 6. Quyền sở hữu và thời điểm giải phóng buffer

Nguyên tắc quan trọng là **mỗi tài nguyên phải có một chủ sở hữu chịu trách nhiệm giải phóng**:

- Protobuf message và ByteString thông thường là object Java bất biến/GC-managed; ứng dụng bỏ tham chiếu khi không còn cần.
- Queue entry do ứng dụng tạo phải được loại bỏ và giải phóng tài nguyên đi kèm khi bị bỏ hoặc xử lý xong.
- Byte budget, semaphore permit và counter phải được trả đúng một lần.
- Netty ByteBuf là đối tượng reference-counted; bên sở hữu phải release đúng số lần retain đã thực hiện.
- Buffer nội bộ do gRPC transport sở hữu phải để gRPC quản lý vòng đời.

Không release một ByteBuf chỉ vì đã gọi observer.onNext nếu code serializer hoặc một tác vụ bất đồng bộ vẫn còn tham chiếu tới nó. Cũng không giữ ByteBuf mãi sau khi stream kết thúc.

Nếu không có hợp đồng ownership rõ ràng, cách đơn giản hơn là copy payload sang ByteString hoặc byte array do ứng dụng sở hữu trước khi đưa vào message Protobuf. Sau khi copy hoàn tất, ứng dụng có thể release buffer nguồn của mình.

## 7. Chuyển Netty ByteBuf sang Protobuf an toàn

Ví dụ một adapter nhận ByteBuf từ tầng ứng dụng và tạo payload Protobuf độc lập:

~~~java
ByteString payload;
try {
    ByteBuffer view = source.nioBuffer(
        source.readerIndex(),
        source.readableBytes());
    payload = ByteString.copyFrom(view);
} finally {
    ReferenceCountUtil.release(source);
}

UploadChunk chunk = UploadChunk.newBuilder()
    .setData(payload)
    .build();
~~~

ByteString.copyFrom tạo bản sao dữ liệu; message Protobuf không còn phụ thuộc vòng đời của ByteBuf nguồn. Ví dụ này giả định adapter sở hữu reference được release trong finally. Nếu buffer được chia sẻ hoặc đã retain thêm, phải tuân thủ đúng ownership/reference count của nơi cấp phát.

Không release buffer mà code khác vẫn sở hữu. Không gọi release hai lần cho cùng một reference. Khi queue giữ một đối tượng có tài nguyên cần đóng, queue entry nên có phương thức close/release rõ ràng để cleanup có thể xử lý cả message chưa được gửi.

## 8. Cleanup phải idempotent

Lỗi, cancellation và deadline có thể xảy ra gần nhau. Ví dụ upstream phát lỗi đúng lúc client hủy call. Nhiều callback có thể cùng yêu cầu cleanup.

Một hàm cleanup an toàn cần:

- Có cờ hoặc cơ chế đồng bộ bảo đảm chỉ thực hiện phần giải phóng một lần.
- Hủy upstream subscription/producer.
- Ngừng worker hoặc báo worker dừng ở checkpoint an toàn.
- Duyệt queue, đóng/release từng entry và trả byte budget.
- Hủy timer, task và đăng ký callback.
- Đóng cursor, file handle hoặc resource nghiệp vụ.

Ví dụ khung cleanup:

~~~java
final class StreamResources {
    private final AtomicBoolean cleaned = new AtomicBoolean();
    private final Queue<PendingChunk> pending = new ConcurrentLinkedQueue<>();
    private final AtomicReference<Subscription> upstream =
        new AtomicReference<>();

    void cleanup() {
        if (!cleaned.compareAndSet(false, true)) {
            return;
        }

        Subscription subscription = upstream.getAndSet(null);
        if (subscription != null) {
            subscription.cancel();
        }

        PendingChunk item;
        while ((item = pending.poll()) != null) {
            item.close();
        }
    }
}
~~~

**PendingChunk.close()** phải idempotent hoặc được gọi đúng một lần bởi owner. Nếu producer có thể enqueue đồng thời với cleanup, cần đồng bộ thao tác kiểm tra trạng thái và enqueue; nếu không, một entry mới có thể xuất hiện sau khi vòng cleanup đã duyệt queue.

Không giữ lock trong lúc thực hiện I/O hoặc đợi worker dừng. Cleanup nên phát tín hiệu dừng, đóng tài nguyên nhanh và để các bước dài chạy trên executor phù hợp.

## 9. Dừng producer và writer sau terminal event

Khi stream lỗi, việc gọi onError mới chỉ kết thúc observer. Producer bất đồng bộ vẫn có thể chạy nếu ứng dụng không hủy nó. Writer cũng có thể còn task đang chờ drain.

Một đường kết thúc an toàn cần:

1. Chuyển trạng thái call từ OPEN sang FAILED/CANCELLED bằng thao tác nguyên tử hoặc serial executor.
2. Ngăn enqueue mới và ngăn writer phát onNext.
3. Hủy upstream subscription hoặc producer.
4. Dọn queue và in-flight task theo chính sách.
5. Phát đúng một terminal event nếu call còn khả năng gửi.
6. Giải phóng tài nguyên còn thuộc ứng dụng.

Với server, có thể đăng ký cancellation handler:

~~~java
ServerCallStreamObserver<Update> call =
    (ServerCallStreamObserver<Update>) responseObserver;

call.setOnCancelHandler(() -> {
    session.markCancelled();
    session.stopProducer();
    session.cleanup();
});
~~~

Khi transport đã báo cancellation, không gọi thêm onError hoặc onCompleted để phản hồi cancellation. Handler chỉ dừng công việc và cleanup; nó không phải một đường phát response.

Với lỗi do ứng dụng phát hiện khi call còn hoạt động, writer/terminal coordinator phát onError đúng một lần rồi chạy cleanup. Mọi producer phải kiểm tra trạng thái trước khi enqueue hoặc gửi message.

## 10. Inbound stream gặp lỗi

Ở server nhận client-streaming, gRPC gọi các callback trên request observer do service trả về. Nếu xử lý một chunk lỗi:

- Ngừng nhận hoặc yêu cầu thêm chunk.
- Hủy công việc phụ thuộc vào dữ liệu không hợp lệ.
- Đóng session upload và giải phóng buffer đang chờ.
- Nếu call còn hoạt động, kết thúc response bằng status lỗi phù hợp.

Nếu request stream bị client hủy, server cần dùng cancellation handler để dừng công việc. Không giả định mọi trường hợp disconnect đều là lỗi nghiệp vụ cần trả response; call có thể đã bị hủy ở transport.

Ở client nhận server-streaming, callback onError là terminal result từ server hoặc transport. Client cần dừng consumer, xóa queue còn chờ theo chính sách và giải phóng tài nguyên; không gọi request thêm sau terminal event.

## 11. Dữ liệu đã xử lý và khả năng resume

Lỗi giữa stream không khôi phục trạng thái nghiệp vụ. Với upload, có thể một số chunk đã được ghi bền vững trong khi chunk tiếp theo lỗi. Với event stream, client có thể đã áp dụng một phần event trước khi mất kết nối.

Nếu cần retry hoặc resume:

- Gắn sequence number hoặc offset ổn định cho từng message.
- Chỉ xác nhận sau khi dữ liệu đã đạt mức bền vững mà hợp đồng yêu cầu.
- Dùng idempotency key để xử lý lại chunk/event mà không tạo tác dụng phụ trùng.
- Lưu cursor/checkpoint ở nơi có thể tồn tại qua RPC.
- Xác định chính sách cho chunk đang xử lý nhưng chưa được xác nhận.

Không retry toàn bộ stream một cách mù quáng nếu các message trước đã gây side effect. Status UNAVAILABLE có thể cho biết lỗi tạm thời, nhưng không tự chứng minh thao tác trước đó chưa được thực hiện.

## 12. Kiểm thử lỗi giữa stream và buffer cleanup

Nên chủ động tạo lỗi tại nhiều thời điểm:

1. Lỗi trước message đầu tiên.
2. Lỗi sau một vài message đã gửi.
3. Lỗi khi outbound queue còn message.
4. Lỗi khi worker đang xử lý một entry.
5. Client cancel đúng lúc upstream phát lỗi.
6. Deadline hết hạn khi queue chưa rỗng.
7. Lỗi sau khi request half-close nhưng trước response cuối.

Sau mỗi ca, kiểm tra:

- Client nhận đúng status và không có callback sau terminal event.
- Producer/subscription đã bị hủy.
- Queue depth và queued bytes trở về 0.
- Byte permit, semaphore và reference-counted buffer được trả đúng số lần.
- Không còn worker hoặc scheduled task giữ session đã kết thúc.
- Các message đã xác nhận được lưu đúng; phần chưa xác nhận có thể retry theo hợp đồng.

Với Netty ByteBuf, có thể dùng công cụ leak detection trong môi trường kiểm thử phù hợp. Không chỉ dựa vào heap sau một lần chạy; hãy lặp lại test nhiều lần và quan sát xu hướng retained memory, active task và queue metrics.

## 13. Quan sát và chẩn đoán trong production

Metric nên gắn với RPC ID hoặc trace context, không gắn trực tiếp payload:

- Terminal status theo phương thức RPC.
- Số message và byte đã gửi/nhận trước khi lỗi.
- Queue depth, queued bytes và số entry bị loại bỏ.
- Số lần cleanup được gọi và số lần cleanup thực sự chạy.
- Số upstream subscription/worker còn hoạt động sau terminal event.
- Số buffer release lỗi hoặc reference count bất thường nếu có instrumentation.
- Thời gian từ terminal event đến khi tài nguyên được giải phóng.

Nếu status lỗi tăng nhưng queue và worker vẫn còn, có thể cleanup path chưa dừng producer. Nếu queue về 0 nhưng bộ nhớ không giảm ngay, cần phân biệt garbage collection, buffer pool và leak thật. Không giải phóng thủ công buffer của transport chỉ vì metric heap còn cao.

Không log token, nội dung file hoặc toàn bộ message khi lỗi. Ghi status code, kích thước, sequence/offset và correlation ID là đủ cho phần lớn chẩn đoán.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ gọi onError mà không dừng producer | Message tiếp tục được tạo sau terminal event | Chuyển state, cancel producer và dừng writer. |
| Chỉ clear queue mà không đóng entry | ByteBuf/file/resource bên trong bị leak | Duyệt queue và release/close từng entry. |
| Release ByteBuf ngay sau khi chuyển reference cho tác vụ bất đồng bộ | Consumer dùng buffer đã bị release | Copy payload hoặc xác định rõ ownership handoff. |
| Release buffer nội bộ của gRPC/Netty transport | Corrupt dữ liệu hoặc double-release | Chỉ release tài nguyên ứng dụng sở hữu. |
| Cleanup không idempotent | Double release hoặc trả permit nhiều lần | Dùng state/atomic và ownership rõ ràng. |
| Enqueue đồng thời với cleanup không đồng bộ | Entry mới bị bỏ sót sau khi queue đã dọn | Đồng bộ admission với trạng thái đóng. |
| Coi onNext là ACK đã lưu bền vững | Retry có thể làm mất hoặc lặp side effect | Dùng ACK/checkpoint ở tầng ứng dụng. |
| Retry toàn bộ stream sau lỗi | Xử lý trùng các message đã thành công | Sequence, idempotency và resume cursor. |

## 15. Bài tập thực hành

Thiết kế upload client-streaming nhận các chunk và lưu vào kho:

1. Mỗi chunk có upload ID, sequence, offset, payload và checksum.
2. Giới hạn inbound queue theo số message và byte.
3. Khi checksum sai ở chunk thứ N, kết thúc RPC bằng status phù hợp.
4. Hủy producer/worker, dọn queue và release mọi buffer ứng dụng đang giữ.
5. Giả lập client cancel đồng thời với lỗi checksum; xác nhận cleanup chỉ chạy một lần.
6. Lưu checkpoint cho các chunk đã ghi bền vững và thiết kế resume sau reconnect.
7. Viết integration test xác nhận không có onNext sau terminal event và không còn queue entry sau cleanup.

**Tiêu chí hoàn thành:** phân biệt dữ liệu đã gửi với dữ liệu đã xác nhận, kết thúc stream đúng một lần, giải phóng buffer theo ownership và có thể giải thích chiến lược retry/resume an toàn.

## 16. Ghi nhớ

- Lỗi giữa stream kết thúc RPC nhưng không rollback message đã được client xử lý.
- Phân biệt stream error, request half-close, cancellation, deadline và successful completion.
- Sau terminal event, dừng producer/writer; không phát thêm onNext hoặc terminal callback.
- Dọn application queue bằng cách đóng/release từng entry, trả byte budget và hủy tác vụ nền.
- Protobuf ByteString thường do GC quản lý; Netty ByteBuf cần release đúng ownership/reference count.
- Không tự giải phóng buffer nội bộ do gRPC transport sở hữu.
- Cleanup phải idempotent và an toàn khi lỗi, cancellation và deadline xảy ra đồng thời.
- Muốn retry/resume an toàn, dùng sequence, checkpoint, ACK và idempotency ở tầng ứng dụng.

Xử lý lỗi giữa stream cùng giải phóng buffer đúng ownership giúp dịch vụ Spring gRPC dừng công việc kịp thời, tránh memory leak/double-release và bảo toàn khả năng phục hồi của các RPC streaming dài hạn.
