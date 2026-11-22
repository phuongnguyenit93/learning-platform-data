# Số message trong một stream

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích giới hạn số message trong một streaming RPC và phân biệt nó với giới hạn kích thước message.
- Xác định message nào được tính ở chiều inbound, outbound hoặc cả hai chiều.
- Thiết kế bộ đếm theo từng stream, không dùng counter dùng chung giữa các request.
- Từ chối message vượt ngưỡng trước khi chạy business logic hoặc phát thêm response.
- Kết hợp message-count limit với byte quota, deadline, flow control và giới hạn stream đồng thời.
- Xử lý đúng terminal state, cancellation và cleanup khi stream vượt quota.
- Chọn status phù hợp và thiết kế client retry/resume an toàn.
- Kiểm thử boundary N và N+1 cho client-streaming, server-streaming và bidirectional streaming.

## 1. Vì sao cần giới hạn số message trong một stream?

Trong **SPRING_GRPC**, streaming RPC cho phép một call trao đổi nhiều message trong thời gian dài. Client-streaming nhận nhiều request rồi trả một kết quả; server-streaming nhận một request rồi phát nhiều response; bidirectional streaming trao đổi nhiều message ở cả hai chiều.

Giới hạn kích thước một message không giới hạn được số message trong stream. Ví dụ, mỗi message chỉ 1 KiB nhưng client gửi liên tục hàng triệu message. Server vẫn phải thực hiện dispatch callback, validate, cập nhật counter, truy cập storage hoặc gọi downstream. CPU, database write, event publish, log và memory dành cho queue có thể tăng mạnh.

**Số message trong một stream** là số message được phép gửi hoặc nhận trong vòng đời của một RPC. Ứng dụng cần quy định rõ giới hạn áp dụng cho chiều nào và đếm ở thời điểm nào:

- **Inbound messages:** message đi từ client tới server.
- **Outbound messages:** message đi từ server tới client.
- **Combined messages:** tổng số message của cả hai chiều, chỉ dùng khi contract định nghĩa rõ một ngân sách chung.

Với bidirectional streaming, nên có giới hạn riêng cho inbound và outbound; có thể bổ sung tổng budget nếu cần giới hạn chi phí của toàn phiên. Không mặc định một giới hạn inbound cũng tự áp dụng cho response.

~~~mermaid
flowchart TD
    A["Mở streaming RPC"] --> B["Xác thực và authorize method"]
    B --> C["Tạo counter riêng cho stream"]
    C --> D{"Có message mới?"}
    D -- "Không" --> E["Chờ, cancel hoặc deadline"]
    D -- "Có" --> F{"Counter còn quota?"}
    F -- "Không" --> G["RESOURCE_EXHAUSTED"]
    F -- "Có" --> H["Tăng counter"]
    H --> I["Validate và authorize message"]
    I --> J["Xử lý hoặc phát response"]
    J --> D
    G --> K["Dừng stream và cleanup"]
~~~

Counter cần gắn với một RPC cụ thể. Không đặt số message hiện tại vào field mutable của singleton service vì nhiều stream đồng thời có thể ghi đè hoặc cộng chung counter của nhau.

## 2. Phân biệt message count với các giới hạn khác

Các giới hạn tài nguyên bảo vệ những khía cạnh khác nhau:

| Giới hạn | Đơn vị | Điều được kiểm soát |
| --- | --- | --- |
| Max message size | Byte/message | Kích thước của một message |
| Max messages per stream | Message/RPC | Số message trong một stream |
| Total bytes per stream | Byte/RPC | Tổng dữ liệu trong stream |
| Stream concurrency | Stream/instance hoặc tenant | Số RPC streaming đang mở |
| Rate limit | Message hoặc byte/đơn vị thời gian | Tốc độ gửi |
| Deadline/maximum lifetime | Thời gian | Thời gian giữ call và tài nguyên |
| Flow control/backpressure | Message đang in-flight | Tốc độ producer so với consumer |

Ví dụ một stream gửi 100.000 message, mỗi message 200 byte. Message-size limit không ngăn được tổng số message lớn; byte quota có thể giới hạn tổng payload nhưng vẫn cho phép rất nhiều message nhỏ gây overhead callback. Ngược lại, message-count limit có thể chặn số lượng message nhưng một vài message lớn vẫn tiêu tốn nhiều memory. Vì vậy, thường cần kết hợp count limit và byte limit.

Flow control cũng không thay thế message-count limit. Flow control điều tiết số message đang truyền hoặc chờ xử lý tại một thời điểm; sau khi consumer xử lý xong, client vẫn có thể tiếp tục gửi thêm message cho tới khi stream kết thúc. Message-count limit giới hạn tổng số message trong toàn bộ RPC.

## 3. Xác định phạm vi đếm theo kiểu streaming

Mỗi kiểu RPC có hướng message khác nhau:

| RPC type | Inbound tại server | Outbound tại server | Giới hạn thường cần |
| --- | --- | --- | --- |
| Unary | Một request | Một response | Thường không cần stream count riêng; vẫn có message-size limit |
| Client-streaming | Nhiều request | Một response cuối | Inbound message count và total bytes |
| Server-streaming | Một request | Nhiều response | Outbound message count và total bytes |
| Bidirectional | Nhiều request | Nhiều response | Inbound và outbound count; có thể thêm combined budget |

Với client-streaming, đếm mỗi request message server nhận trong onNext. Với server-streaming, đếm mỗi response trước khi gọi onNext của response observer. Với bidirectional streaming, duy trì hai counter độc lập vì số request và response có thể khác nhau.

Nếu contract định nghĩa một ngân sách combined, hãy ghi rõ message nào được tính vào ngân sách và thứ tự cập nhật. Ví dụ, một request nhận vào và một response phát ra có thể cùng tiêu thụ một đơn vị; nhưng cách tính này thường khó dự đoán cho client. Hai giới hạn riêng theo chiều thường dễ vận hành và debug hơn.

## 4. Đặt giới hạn ở application boundary

grpc-java cung cấp các giới hạn như max inbound message size và flow control, nhưng không nên giả định transport tự áp một quota tổng số message cho mọi stream. Số message tối đa thường là policy của application, vì mỗi method có ý nghĩa và workload khác nhau.

Ví dụ:

- Upload batch có thể cho phép tối đa 5.000 item message.
- Một subscription event có thể cho phép tối đa 20.000 event trước khi client phải reconnect bằng cursor.
- Một command stream có thể giới hạn 500 command mỗi phiên.
- Một stream telemetry có thể giới hạn message count theo thời lượng và quota tenant.

Đặt policy theo method và loại dữ liệu. Không dùng một giá trị quá lớn chung cho mọi RPC chỉ để tránh phải cấu hình từng API. Nếu một method hợp lệ cần số message lớn, cần xác định rõ quota, lifetime, resume semantics và chi phí downstream.

Một policy có thể mô tả limit theo full method name:

~~~java
public interface StreamMessageLimitPolicy {
    long maxInboundMessages(String fullMethodName);
    long maxOutboundMessages(String fullMethodName);
}
~~~

Method chưa được khai báo phải có hành vi rõ ràng: dùng default bảo thủ hoặc từ chối stream theo policy. Không để method mới vô tình có quota vô hạn.

Trong hệ sinh thái **Spring gRPC**, policy có thể được inject vào service adapter hoặc interceptor thông qua bean. Nếu server được starter quản lý, hãy đăng ký policy/handler qua extension point mà phiên bản starter hỗ trợ; không tự dựng một server thứ hai để né cấu hình. Integration test cần khởi động Spring application context để xác nhận bean giới hạn message thực sự được dùng bởi service đang chạy.

## 5. Bộ đếm an toàn theo từng stream

Một bộ đếm nên có giới hạn dương và thao tác consume nguyên tử. Dùng long để tránh giới hạn nhỏ của int khi stream dài:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class MessageBudget {

    private final long maximum;
    private final AtomicLong consumed = new AtomicLong();

    public MessageBudget(long maximum) {
        if (maximum <= 0) {
            throw new IllegalArgumentException(
                    "maximum must be positive");
        }
        this.maximum = maximum;
    }

    public boolean tryConsume() {
        while (true) {
            long current = consumed.get();

            if (current >= maximum) {
                return false;
            }

            if (consumed.compareAndSet(current, current + 1)) {
                return true;
            }
        }
    }

    public long consumed() {
        return consumed.get();
    }

    public long remaining() {
        return Math.max(0, maximum - consumed.get());
    }
}
~~~

Khi counter đang ở N-1, message thứ N được chấp nhận và counter trở thành N. Message thứ N+1 bị từ chối. Không tăng counter trước rồi mới so sánh bằng một phép toán không nguyên tử nếu callbacks có thể chạy từ nhiều producer.

Tạo một MessageBudget cho mỗi chiều của mỗi stream. Không dùng một static AtomicLong chung cho tất cả RPC, vì khi đó quota của một caller sẽ bị tiêu thụ bởi caller khác.

Mặc dù grpc-java thường tuần tự hóa callback của một call, application có thể phát response từ nhiều thread hoặc dùng nhiều producer. Nếu nhiều thread cùng gọi outbound observer, cần serialize việc gửi message và cập nhật counter; StreamObserver không mặc định an toàn cho concurrent writes.

## 6. Client-streaming: đếm request message nhận vào

Với client-streaming, server nhận nhiều request qua StreamObserver. Đếm trước khi validate và chạy use case để message N+1 không tạo side effect:

~~~java
@Override
public StreamObserver<UploadItemRequest> uploadItems(
        StreamObserver<UploadSummary> responseObserver) {

    MessageBudget inbound =
            new MessageBudget(MAX_UPLOAD_MESSAGES);

    return new StreamObserver<>() {
        private boolean terminal;
        private long accepted;

        @Override
        public synchronized void onNext(UploadItemRequest request) {
            if (terminal) {
                return;
            }

            if (!inbound.tryConsume()) {
                terminal = true;
                responseObserver.onError(
                        Status.RESOURCE_EXHAUSTED
                                .withDescription("Stream message limit reached")
                                .asRuntimeException());
                cleanupUpload();
                return;
            }

            try {
                validateAndAuthorize(request);
                uploadUseCase.process(request);
                accepted++;
            } catch (RuntimeException failure) {
                terminal = true;
                responseObserver.onError(mapError(failure));
                cleanupUpload();
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
            responseObserver.onNext(
                    UploadSummary.newBuilder()
                            .setAcceptedCount(accepted)
                            .build());
            responseObserver.onCompleted();
            cleanupUpload();
        }
    };
}
~~~

Ví dụ minh họa cần được điều chỉnh theo use case và quy tắc thread của ứng dụng. Trong implementation thực tế, cleanup nên idempotent; lỗi ở bất kỳ bước nào không được làm phát terminal signal nhiều lần. Nếu xử lý message bất đồng bộ, phải giới hạn cả số task đang chờ và bảo đảm thứ tự hoặc semantics song song được contract cho phép.

Điểm quan trọng là message count được tiêu thụ trước khi business side effect. Nếu chỉ tăng counter sau khi xử lý, một message thứ N+1 vẫn có thể được ghi trước khi phát hiện quota đã vượt.

## 7. Server-streaming: đếm response trước khi phát

Với server-streaming, một request tạo ra nhiều response. Bộ đếm outbound được tạo theo call và kiểm tra trước mỗi lần onNext:

~~~java
public void watchEvents(
        WatchRequest request,
        StreamObserver<EventResponse> responseObserver) {

    MessageBudget outbound =
            new MessageBudget(MAX_RESPONSE_MESSAGES);

    try {
        for (Event event : eventSource.read(request)) {
            if (!outbound.tryConsume()) {
                responseObserver.onError(
                        Status.RESOURCE_EXHAUSTED
                                .withDescription("Stream message limit reached")
                                .asRuntimeException());
                return;
            }

            responseObserver.onNext(toResponse(event));
        }

        responseObserver.onCompleted();
    } catch (RuntimeException failure) {
        responseObserver.onError(mapError(failure));
    }
}
~~~

Ở ví dụ đồng bộ, vòng lặp dừng ngay khi hết quota. Với event source bất đồng bộ, cần cancel subscription khi hết quota hoặc khi client hủy call. Không tiếp tục đọc broker/database rồi bỏ response vì nguồn dữ liệu vẫn tiêu tốn tài nguyên.

Nếu API cần tiếp tục từ vị trí cuối cùng, response nên chứa cursor hoặc sequence. Khi đạt message limit, client có thể mở stream mới từ cursor tiếp theo thay vì yêu cầu server giữ một stream vô hạn.

## 8. Bidirectional streaming: hai counter độc lập

Với bidirectional streaming, client và server đều có thể gửi nhiều message. Một request inbound có thể kích hoạt zero, one hoặc nhiều response outbound. Do đó không nên giả định số request bằng số response.

Tạo hai budget:

~~~java
MessageBudget inbound =
        new MessageBudget(MAX_REQUEST_MESSAGES);

MessageBudget outbound =
        new MessageBudget(MAX_RESPONSE_MESSAGES);
~~~

Trong callback nhận request:

~~~java
if (!inbound.tryConsume()) {
    terminate(Status.RESOURCE_EXHAUSTED);
    return;
}

validateAuthorizeAndProcess(request);
~~~

Trước khi gửi response:

~~~java
if (!outbound.tryConsume()) {
    terminate(Status.RESOURCE_EXHAUSTED);
    return;
}

responseObserver.onNext(response);
~~~

Nếu contract có combined budget, thêm một counter thứ ba và consume theo quy tắc đã công bố. Tránh cập nhật counter inbound nhưng phát nhiều response vượt outbound quota; mỗi hướng cần được kiểm soát riêng.

Nếu server gửi response từ worker thread, dùng một outbound serializer hoặc executor tuần tự để bảo đảm observer không bị gọi đồng thời. Terminal state cũng cần atomic/synchronized để tránh onError và onCompleted cùng phát.

## 9. Xử lý khi vượt giới hạn

Khi message N+1 đến, application có thể kết thúc stream bằng **RESOURCE_EXHAUSTED**. Status này biểu diễn quota hoặc giới hạn tài nguyên đã bị chạm.

Phân biệt:

| Nguyên nhân | Status/hành vi |
| --- | --- |
| Vượt số message tối đa của stream | **RESOURCE_EXHAUSTED** |
| Vượt tổng byte hoặc quota nghiệp vụ | **RESOURCE_EXHAUSTED** |
| Message sai cấu trúc hoặc field không hợp lệ | **INVALID_ARGUMENT** |
| Caller thiếu quyền gửi message | **PERMISSION_DENIED** |
| Credential không hợp lệ | **UNAUTHENTICATED** |
| Deadline hết | **DEADLINE_EXCEEDED** |
| Client hủy stream | **CANCELLED** |

Không dùng **INVALID_ARGUMENT** cho mọi trường hợp vượt quota. Message có thể hoàn toàn hợp lệ về schema nhưng stream đã dùng hết ngân sách. Ngược lại, message thứ hai có thể bị từ chối vì field sai dù count còn quota.

Không đưa quota nội bộ, số lượng tenant khác hoặc policy detail nhạy cảm vào status description. Client nên dựa vào status code và reason code ổn định nếu API cung cấp.

## 10. Partial success hay kết thúc toàn stream?

Một message vượt quota có thể kết thúc toàn bộ RPC, hoặc API có thể dùng protocol item-level để từ chối một item và tiếp tục. Hai semantics này khác nhau và phải được định nghĩa trong contract.

**Terminate stream** phù hợp khi message count là giới hạn cứng của cả phiên. Khi đã đạt N message, message N+1 làm stream kết thúc bằng RESOURCE_EXHAUSTED. Client cần mở stream mới nếu còn quota/phiên mới.

**Reject item and continue** phù hợp khi server áp quota theo batch hoặc item độc lập và contract cho phép kết quả từng item. Tuy nhiên, nếu message count chính là quota tổng của stream thì tiếp tục nhận message sau khi hết quota sẽ phá vỡ giới hạn. Không nên trả lỗi item-level rồi vẫn xử lý vô hạn các item tiếp theo.

Nếu dùng partial success, cần giới hạn số item được nhận, số item bị từ chối, tổng bytes và thời gian stream. Có thể đóng stream sau một số lượng rejection liên tiếp để tránh client dùng lỗi item-level như cách dò policy hoặc tiêu tốn CPU.

## 11. Kết hợp count limit với byte quota, rate limit và flow control

Một stream có thể gửi nhiều message nhỏ hoặc ít message lớn. Cần dùng các giới hạn bổ trợ:

- **Message count:** chặn tổng số lần xử lý message.
- **Total bytes:** chặn tổng payload.
- **Max message size:** chặn một message quá lớn.
- **Rate limit:** chặn tốc độ message/byte quá cao.
- **Flow control:** giới hạn message đang in-flight.
- **Deadline/idle timeout:** giới hạn thời gian giữ tài nguyên.
- **Stream concurrency:** giới hạn số stream đồng thời.

Ví dụ upload có thể cho phép tối đa 2.000 chunk, mỗi chunk tối đa 256 KiB, tổng upload tối đa 100 MiB, thời gian tối đa 10 phút và tối đa 3 upload đồng thời cho mỗi tenant. Mỗi giới hạn bảo vệ một khía cạnh riêng.

Khi cập nhật total bytes, dùng kiểu long và kiểm tra overflow trước khi cộng. Với quota phân tán theo tenant, cập nhật phải nguyên tử để hai stream không cùng tiêu thụ vượt hạn mức.

Flow control không thay thế count limit: một stream có thể gửi lần lượt từng message, chờ server xử lý xong rồi gửi tiếp, cuối cùng vẫn gửi hàng triệu message. Count limit giới hạn tổng số lần đó.

## 12. Deadline, cancellation và cleanup

Một stream có thể kết thúc trước khi đạt message limit do deadline, client cancellation hoặc lỗi downstream. Mọi đường terminal phải giải phóng subscription, queue, timer và quota.

Với server streaming, có thể kiểm tra cancellation qua ServerCallStreamObserver:

~~~java
if (responseObserver instanceof ServerCallStreamObserver<?> serverObserver) {
    serverObserver.setOnCancelHandler(() -> {
        subscription.cancel();
        cleanupStreamState();
    });
}
~~~

Khi message limit bị vượt, dừng nguồn phát ngay. Khi client cancel, không tiếp tục đọc message từ broker chỉ để bỏ đi. Với client-streaming, không giữ buffer chứa tất cả message nếu use case có thể xử lý theo từng item.

Các nguyên tắc:

- Dùng terminal guard để chỉ kết thúc stream một lần.
- Cleanup idempotent trong complete, error, cancel và quota exceeded.
- Hủy future/subscription/producer khi stream kết thúc.
- Không giữ principal hoặc Context của RPC trong background job dài hạn.
- Release concurrency permit khi call kết thúc.
- Không phát thêm onNext sau onError/onCompleted.

Nếu cần tiếp tục công việc sau khi RPC kết thúc, tạo job độc lập với identity, quota, deadline và trạng thái riêng thay vì kéo dài vòng đời stream để giữ tài nguyên.

## 13. Client retry và resume khi đạt message limit

Client không nên tự động retry cùng một stream từ đầu khi nhận RESOURCE_EXHAUSTED. Nếu server đã xử lý một phần message, retry có thể tạo side effect trùng.

Với upload hoặc event ingestion, dùng:

- **Sequence number:** xác định thứ tự message.
- **Idempotency key:** nhận diện operation hoặc item đã xử lý.
- **Resume cursor:** tiếp tục từ vị trí server đã xác nhận.
- **Acknowledgement:** server xác nhận message đã commit.
- **Transfer/session ID:** liên kết các stream reconnect thuộc cùng operation.

Với server-streaming, response có thể chứa cursor cuối cùng. Khi stream đạt count limit, client mở stream mới từ cursor đó. Với bidirectional stream, hai chiều có thể cần sequence độc lập.

Retry nên có backoff và jitter, đồng thời tôn trọng quota mới. Nếu server từ chối vì một stream đã dùng hết message budget, reconnect chỉ hữu ích khi contract cấp một phiên mới hoặc cho phép resume; mở stream mới liên tục mà không thay cursor/quota sẽ chỉ lặp lỗi.

## 14. Quan sát message count trong vận hành

Theo dõi theo method và quota tier:

- Số message inbound/outbound trung bình và p95/p99 mỗi stream.
- Số stream kết thúc do message-count limit.
- Số message bị từ chối là N+1.
- Tổng bytes và message count cùng nhau.
- Thời lượng stream và tốc độ message.
- Số stream active và số callback đang chờ.
- Status RESOURCE_EXHAUSTED theo method.
- Tỷ lệ reconnect/resume sau khi đạt quota.

Metric nên dùng method, direction và status làm label có cardinality kiểm soát. Không dùng stream ID, request ID hoặc user ID tùy ý làm metric label. Log có thể ghi correlation ID đã được kiểm soát để điều tra, nhưng không ghi payload nhạy cảm.

Nếu nhiều stream kết thúc đúng tại giới hạn, đó có thể là hành vi bình thường của contract hoặc dấu hiệu limit quá thấp. So sánh số lần đạt limit với throughput, downstream cost và tần suất reconnect trước khi điều chỉnh.

## 15. Kiểm thử boundary N và N+1

Test cần xác minh chính xác số message được chấp nhận:

| Số message gửi | Kỳ vọng khi limit là N |
| --- | --- |
| 0 | Stream có thể hoàn tất nếu contract cho phép stream rỗng |
| N-1 | Chấp nhận |
| N | Chấp nhận message thứ N |
| N+1 | Từ chối message vượt ngưỡng; không chạy business logic cho message đó |

Bao phủ từng hướng:

- Client-streaming: gửi N request, rồi N+1 request.
- Server-streaming: nguồn phát có N response, rồi N+1 response.
- Bidirectional: kiểm tra inbound và outbound budget độc lập.
- Combined budget: nếu có, kiểm tra tổng request + response.
- Concurrent streams: counter của stream A không làm giảm quota stream B.
- Cancellation trước khi đủ N: cleanup và release permit.
- Retry/resume: không xử lý trùng message đã commit.

Các assertion quan trọng:

1. Counter không vượt N.
2. Message N được xử lý đúng một lần.
3. Message N+1 không tạo side effect.
4. RPC kết thúc bằng RESOURCE_EXHAUSTED nếu contract chọn terminate.
5. Không có onNext sau terminal signal.
6. Cleanup và permit release xảy ra đúng một lần.
7. Hai stream đồng thời có counter độc lập.

Dùng in-process gRPC test hoặc transport integration test với generated stub. Điều khiển stream bằng CountDownLatch, CyclicBarrier hoặc test observer thay vì Thread.sleep. Kiểm tra cả application counter và trạng thái downstream để phát hiện message đã được xử lý trước khi quota check.

Với Spring application test, khởi động đúng cấu hình server do starter quản lý, inject policy có giới hạn nhỏ (ví dụ N=2), mở stream qua generated stub và gửi N+1 message. Xác minh message thứ ba không vào use case, client nhận status theo contract và bean admission/cleanup đã được wiring. Test này bổ sung cho in-process test tự dựng interceptor chain, vì nó kiểm tra cấu hình Spring thực tế.

## 16. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo client-streaming method nhận UploadItemRequest và đặt giới hạn 1.000 message.
2. Tạo MessageBudget dùng AtomicLong/CAS và một instance riêng cho mỗi stream.
3. Tăng counter trước validate/use case; từ chối message N+1 bằng RESOURCE_EXHAUSTED.
4. Tạo server-streaming method giới hạn số response và dừng nguồn phát khi hết quota.
5. Với bidirectional streaming, đặt inbound và outbound budget riêng.
6. Kết hợp max message size, total bytes, deadline và stream concurrency.
7. Thêm cancellation cleanup, terminal guard và resume cursor cho upload dài.
8. Viết integration test N-1, N, N+1, hai stream đồng thời và cancellation.

### Câu hỏi tự kiểm tra

**1. Message count limit khác max message size thế nào?**  
Message count giới hạn số message trong một RPC; max message size giới hạn byte của từng message.

**2. Client-streaming nên đếm ở đâu?**  
Ở callback nhận request message, trước khi validate và thực hiện side effect.

**3. Server-streaming nên đếm ở đâu?**  
Ngay trước khi phát mỗi response qua observer.

**4. Bidirectional streaming cần một counter hay hai?**  
Thông thường cần inbound và outbound counter riêng; chỉ thêm combined budget nếu contract định nghĩa rõ.

**5. Status nào phù hợp khi vượt message-count quota?**  
RESOURCE_EXHAUSTED.

**6. Flow control có thay count limit không?**  
Không. Flow control giới hạn message in-flight; count limit giới hạn tổng message trong cả stream.

**7. Vì sao counter phải theo từng stream?**  
Để một RPC không tiêu thụ quota của RPC khác và tránh lẫn state giữa các tenant/caller.

**8. Client có nên retry toàn bộ stream sau RESOURCE_EXHAUSTED không?**  
Không tự động. Cần sequence, idempotency và resume cursor để tránh xử lý trùng dữ liệu đã commit.

## Tổng kết

Giới hạn số message trong một stream kiểm soát tổng số lần trao đổi message của một RPC. Hãy xác định rõ chiều inbound/outbound, tạo counter riêng cho từng stream và consume quota trước khi chạy business logic hoặc phát response. Client-streaming, server-streaming và bidirectional streaming có vị trí đếm khác nhau; bidirectional thường cần hai budget riêng. Kết hợp message count với byte quota, max message size, rate limit, flow control, deadline và stream concurrency để bảo vệ tài nguyên. Khi vượt ngưỡng, kết thúc bằng RESOURCE_EXHAUSTED theo contract, cleanup mọi tài nguyên và hỗ trợ resume/idempotency nếu client cần tiếp tục. Integration test phải kiểm tra N-1, N, N+1, side effect, cancellation và isolation giữa các stream đồng thời.

