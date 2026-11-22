# Retry server streaming và stream position

## 1. Vì sao server streaming cần stream position?

Trong **Spring gRPC**, một server-streaming RPC nhận một request rồi phát nhiều response message. Ví dụ client đăng ký nhận thay đổi đơn hàng, server lần lượt gửi các event có sequence tăng dần. Nếu kết nối bị ngắt sau khi client đã xử lý một phần dữ liệu, client cần biết phải tiếp tục từ đâu.

Retry một server-streaming RPC không tự động có nghĩa là tiếp tục từ response cuối cùng đã nhận. Một RPC mới thường bắt đầu lại theo request ban đầu. Nếu request không mang vị trí tiếp tục, client có thể nhận lại dữ liệu cũ; nếu tự bỏ qua quá nhiều dữ liệu, client có thể mất event.

**Stream position** là vị trí trong luồng dữ liệu logic mà client đã xử lý hoặc muốn server bắt đầu phát tiếp. Nó có thể được biểu diễn bằng sequence, offset hoặc một resume token do server cấp.

Bài học tập trung vào ba việc:

- Hiểu giới hạn automatic retry của server streaming khi RPC đã commit.
- Thiết kế position/cursor để mở một RPC mới và resume từ điểm đã xác nhận.
- Xử lý replay, duplicate, gap, checkpoint và retention để không mất hoặc áp dụng lặp tác dụng phụ.

## 2. Automatic retry không phải resume

gRPC retry policy hoạt động ở cấp RPC. Runtime có thể replay một call khi call còn **chưa commit**, status phù hợp retry policy và còn attempt/deadline. Call được xem là committed khi client nhận response headers hoặc request vượt giới hạn retry buffer.

Với server streaming:

- Client gửi một request ban đầu, server bắt đầu response stream.
- Server có thể gửi response headers trước hoặc cùng lúc với message đầu tiên.
- Khi client nhận headers, call đã commit; lỗi xảy ra sau đó không làm gRPC tự replay toàn bộ stream.
- Kể cả khi chưa nhận response message nào, nếu headers đã tới client thì call vẫn có thể đã commit.

Vì vậy, không nên xây dựng độ tin cậy của một stream dài bằng cách chỉ tăng `maxAttempts`. Automatic retry có thể hữu ích cho lỗi xảy ra rất sớm, trước commitment; **resume sau khi stream đã bắt đầu là trách nhiệm của ứng dụng**.

| Tình huống | Automatic retry có thể áp dụng? | Cách xử lý |
| --- | --- | --- |
| Server lỗi trước khi call commit, status retryable | Có thể, nếu policy và ngân sách cho phép | Để gRPC runtime retry |
| Client đã nhận response headers | Không replay call đã commit | Mở RPC mới bằng stream position |
| Client đã xử lý nhiều event rồi kết nối đứt | Không khôi phục từ event cuối bằng retry policy | Resume từ checkpoint bền vững |
| Client nhận lại event đã xử lý | Có thể xảy ra khi resume theo at-least-once | Deduplicate bằng event ID/sequence |
| Cursor đã hết retention | Không thể tiếp tục từ vị trí cũ | Reset snapshot hoặc báo lỗi cần đồng bộ lại |

## 3. Định nghĩa stream position rõ ràng

Một position phải trả lời được câu hỏi: **server sẽ bắt đầu phát từ event nào?** Có hai cách phổ biến:

1. **Sequence/offset tường minh:** client gửi `after_sequence = 120`; server bắt đầu từ sequence 121.
2. **Opaque resume token:** server cấp token đại diện cho vị trí đã phát; client gửi lại token mà không cần hiểu cấu trúc bên trong.

Sequence dễ quan sát và hữu ích khi một stream có thứ tự tuyến tính. Resume token phù hợp hơn khi vị trí phụ thuộc partition, filter, snapshot hoặc implementation storage. Token nên được server tạo và xác thực; không để client tự sửa offset tùy ý.

Một contract tốt phải xác định:

- Sequence bắt đầu từ đâu và tăng trong phạm vi nào: toàn stream, tenant, partition hay subscription.
- Position có nghĩa là **sau event đã xử lý** hay **event kế tiếp cần nhận**.
- Token gắn với stream/filter/version nào và có hết hạn không.
- Khi position không còn hợp lệ, server trả lỗi gì và client phải reset ra sao.
- Event có ID ổn định để deduplicate qua reconnect hay không.

Trong ví dụ dưới đây, `after_sequence` có nghĩa là client đã xử lý thành công tới sequence đó; server phát từ sequence kế tiếp. `resume_token` mang cùng semantics nhưng là dữ liệu opaque do server cấp.

## 4. Hợp đồng Protobuf cho resume

Ví dụ `order_events.proto`:

```proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.v1";

service OrderEvents {
  rpc Watch(WatchRequest) returns (stream OrderEvent);
}

message WatchRequest {
  string tenant_id = 1;
  string order_id = 2;
  oneof position {
    int64 after_sequence = 3;
    string resume_token = 4;
  }
}

message OrderEvent {
  string event_id = 1;
  int64 sequence = 2;
  string resume_token = 3;
  string order_id = 4;
  string event_type = 5;
  bytes payload = 6;
}
```

Contract này dùng server streaming: một request xác định order và vị trí bắt đầu, server phát nhiều event. Sau mỗi event, server trả sequence và token đại diện cho vị trí **sau event đó**.

Một số quy tắc quan trọng:

- `event_id` ổn định qua các lần phát lại; không tạo UUID mới mỗi lần server replay cùng một event.
- `sequence` tăng đơn điệu trong phạm vi stream được xác định bởi tenant/order và không được tái sử dụng cho event khác.
- `resume_token` là opaque; client chỉ lưu và gửi lại, không phân tích hay tự tăng token.
- Request mới phải giữ nguyên phạm vi subscription (tenant, order và filter). Thay filter có thể tạo một stream logic khác, khiến position cũ không còn áp dụng.
- Nếu dùng sequence, `after_sequence=120` có nghĩa server bắt đầu ở 121, không phải phát lại 120.

Trong hệ thống phân tán có nhiều partition, một sequence đơn có thể không đủ. Khi đó token có thể mã hóa vector offset theo partition hoặc một cursor storage cụ thể.

## 5. Server: đọc event từ position và phát tiếp

Server cần kiểm tra cursor trước khi bắt đầu stream. Với sequence tường minh, truy vấn event store theo điều kiện `sequence > afterSequence`, giữ thứ tự và phát từng event. Với token, server giải mã/xác thực token rồi chuyển thành position nội bộ.

Pseudocode cho service Spring gRPC:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class OrderEventsGrpcService
        extends OrderEventsGrpc.OrderEventsImplBase {

    private final OrderEventStore eventStore;
    private final ResumeTokenCodec tokenCodec;

    public OrderEventsGrpcService(
            OrderEventStore eventStore,
            ResumeTokenCodec tokenCodec) {
        this.eventStore = eventStore;
        this.tokenCodec = tokenCodec;
    }

    @Override
    public void watch(
            WatchRequest request,
            StreamObserver<OrderEvent> responseObserver) {
        ServerCallStreamObserver<OrderEvent> output =
                (ServerCallStreamObserver<OrderEvent>) responseObserver;

        StreamPosition position;
        try {
            position = resolvePosition(request);
        } catch (InvalidResumeTokenException error) {
            output.onError(Status.INVALID_ARGUMENT
                    .withDescription("resume_token không hợp lệ")
                    .asRuntimeException());
            return;
        } catch (PositionExpiredException error) {
            output.onError(Status.OUT_OF_RANGE
                    .withDescription("stream position đã hết retention")
                    .asRuntimeException());
            return;
        }

        EventSubscription subscription = eventStore.subscribe(
                request.getTenantId(),
                request.getOrderId(),
                position);

        Object writeLock = new Object();
        AtomicBoolean terminal = new AtomicBoolean();
        output.setOnCancelHandler(() -> {
            synchronized (writeLock) {
                terminal.set(true);
                subscription.close();
            }
        });
        subscription.start(event -> {
            synchronized (writeLock) {
                if (terminal.get() || output.isCancelled()) {
                    terminal.set(true);
                    subscription.close();
                    return;
                }
                try {
                    output.onNext(toProto(event,
                            tokenCodec.tokenAfter(event)));
                } catch (RuntimeException sendError) {
                    terminal.set(true);
                    subscription.close();
                }
            }
        }, error -> {
            synchronized (writeLock) {
                if (terminal.get()) {
                    return;
                }
                terminal.set(true);
                subscription.close();
                if (!output.isCancelled()) {
                    output.onError(Status.UNAVAILABLE
                            .withDescription("event source tạm thời không khả dụng")
                            .asRuntimeException());
                }
            }
        }, () -> {
            synchronized (writeLock) {
                if (terminal.get()) {
                    return;
                }
                terminal.set(true);
                subscription.close();
                if (!output.isCancelled()) {
                    output.onCompleted();
                }
            }
        });
    }

    private StreamPosition resolvePosition(WatchRequest request) {
        return switch (request.getPositionCase()) {
            case AFTER_SEQUENCE ->
                    eventStore.validatePosition(request.getAfterSequence());
            case RESUME_TOKEN ->
                    tokenCodec.decodeAndValidate(
                            request.getResumeToken(),
                            request.getTenantId(),
                            request.getOrderId());
            case POSITION_NOT_SET -> eventStore.initialPosition(
                    request.getTenantId(), request.getOrderId());
        };
    }
}
```

Các kiểu `OrderEventStore`, `EventSubscription`, `StreamPosition` và `ResumeTokenCodec` là abstraction của ứng dụng, cần triển khai theo database hoặc broker thực tế. `writeLock` và `terminal` bảo đảm callback event, error, completion và cancellation không ghi đồng thời hoặc phát sau terminal event. Đoạn mã nhấn mạnh các trách nhiệm:

- Xác thực position trước khi đọc dữ liệu.
- Đăng ký subscription từ đúng vị trí, không đọc từ đầu một cách mặc định khi client gửi cursor.
- Đóng subscription khi client cancel hoặc stream kết thúc.
- Không phát tiếp sau terminal event.
- Phân biệt cursor sai định dạng với cursor hợp lệ nhưng đã hết retention.

Trong production, response writer còn phải có queue giới hạn và xử lý `isReady()`/`setOnReadyHandler()` nếu event source có thể phát nhanh hơn client đọc. Không để callback broker gọi trực tiếp `onNext()` đồng thời từ nhiều thread.

## 6. Client: checkpoint sau khi xử lý thành công

Client không nên lưu position mới ngay khi vừa nhận event nếu việc áp dụng event chưa hoàn tất. Nếu client crash sau khi ghi checkpoint nhưng trước khi cập nhật dữ liệu nghiệp vụ, lần resume sau sẽ bỏ qua event chưa được xử lý.

Quy tắc an toàn:

1. Nhận event.
2. Kiểm tra event ID/sequence để phát hiện duplicate hoặc gap.
3. Áp dụng thay đổi nghiệp vụ.
4. Lưu dữ liệu đã áp dụng và checkpoint trong cùng transaction nếu cùng database.
5. Chỉ sau khi commit mới coi position đó là điểm tiếp tục.

Pseudocode:

```java
void onEvent(OrderEvent event) {
    consumerTransaction.execute(() -> {
        if (processedEventRepository.exists(event.getEventId())) {
            return; // Replay: không áp dụng side effect lần nữa.
        }

        long expected = checkpointRepository.currentSequence(
                event.getOrderId()) + 1;
        if (event.getSequence() != expected) {
            throw new SequenceGapException(expected, event.getSequence());
        }

        applyOrderChange(event);
        processedEventRepository.insert(event.getEventId());
        checkpointRepository.save(
                event.getOrderId(),
                event.getSequence(),
                event.getResumeToken());
    });
}
```

Đây là pseudocode: transaction phải bao trùm cả thay đổi nghiệp vụ, dedup record và checkpoint. Nếu các phần này nằm ở storage khác nhau, cần một giao thức phối hợp như inbox/outbox hoặc chấp nhận at-least-once với consumer idempotent.

### 6.1. Vì sao checkpoint phải đi sau xử lý?

| Thứ tự | Sự cố | Hệ quả |
| --- | --- | --- |
| Lưu checkpoint trước, xử lý sau | Process crash sau checkpoint | Event bị bỏ qua khi resume |
| Xử lý trước, checkpoint sau, không có dedup | Process crash giữa hai bước | Event được phát lại và side effect có thể lặp |
| Xử lý + dedup + checkpoint cùng transaction | Process crash trước commit | Cả ba rollback; event được phát lại an toàn |
| Xử lý + dedup + checkpoint cùng transaction | Process crash sau commit | Resume từ event kế tiếp; duplicate được nhận diện |

Mục tiêu thực tế thường là **at-least-once delivery với idempotent processing**, không phải exactly-once delivery của mạng.

## 7. Reconnect và resume ở client

Khi response observer nhận `onError`, client tạo một RPC mới bằng checkpoint bền vững gần nhất. Không dùng cursor chỉ lưu trong RAM vì process có thể crash.

Pseudocode:

```java
void openSubscription(String tenantId, String orderId) {
    Checkpoint checkpoint =
            checkpointRepository.load(tenantId, orderId);

    WatchRequest.Builder request = WatchRequest.newBuilder()
            .setTenantId(tenantId)
            .setOrderId(orderId);

    if (checkpoint != null && !checkpoint.resumeToken().isBlank()) {
        request.setResumeToken(checkpoint.resumeToken());
    } else if (checkpoint != null) {
        request.setAfterSequence(checkpoint.sequence());
    }

    stub.withDeadlineAfter(10, TimeUnit.MINUTES)
            .watch(request.build(), new StreamObserver<>() {
        @Override
        public void onNext(OrderEvent event) {
            processAndCheckpoint(event);
        }

        @Override
        public void onError(Throwable error) {
            scheduleReconnect(error);
        }

        @Override
        public void onCompleted() {
            // Stream hoàn tất bình thường; chỉ reconnect nếu subscription
            // được định nghĩa là liên tục và caller vẫn còn quan tâm.
        }
    });
}
```

Đây là mẫu khung; cần bảo đảm chỉ có một reconnect loop cho một subscription, hủy timer khi caller dừng và không tạo nhiều stream song song dùng cùng checkpoint.

Chính sách reconnect nên:

- Retry lỗi tạm thời như `UNAVAILABLE` bằng exponential backoff và jitter.
- Không reconnect vô hạn với lỗi xác thực hoặc request sai.
- Dùng deadline hợp lý cho mỗi RPC stream; nếu subscription dài hạn, chủ động reconnect trước giới hạn vận hành nếu hệ thống yêu cầu.
- Giữ nguyên tenant, filter và subscription identity khi dùng cursor cũ.
- Phân biệt `onError` với `onCompleted`: hoàn tất bình thường không nhất thiết là lỗi cần retry.

## 8. Xử lý duplicate, gap và cursor hết hạn

Resume thường có thể phát lại event cuối cùng đã nhận hoặc đã xử lý, tùy semantics cursor và thời điểm checkpoint. Client phải có quy tắc rõ:

- **Duplicate:** cùng `event_id` đã xử lý thì bỏ qua side effect, nhưng vẫn xác minh sequence/cursor nhất quán.
- **Gap:** sequence nhận được lớn hơn sequence kỳ vọng; dừng áp dụng dữ liệu tiếp theo và khôi phục từ checkpoint hoặc yêu cầu snapshot.
- **Out-of-order:** nếu nguồn không bảo đảm thứ tự, cần buffer có giới hạn hoặc partition-specific checkpoint. Không tự sắp xếp toàn cục nếu event có quan hệ nhân quả.
- **Expired cursor:** server không còn lưu event cần thiết. Client phải tải snapshot mới và nhận một position mới làm điểm bắt đầu.
- **Invalid token:** token sai chữ ký, sai tenant/filter hoặc bị sửa; từ chối thay vì diễn giải như cursor mặc định.

Một cursor opaque nên được ràng buộc với tenant, stream identity, filter và phiên bản schema. Nếu token có thể đoán hoặc sửa, client có thể truy cập event ngoài phạm vi được cấp quyền.

## 9. Snapshot và event stream không được tạo khoảng trống

Một số API vừa trả snapshot hiện tại vừa theo dõi event mới. Nếu server đọc snapshot rồi mới đăng ký stream, event phát sinh giữa hai bước có thể bị mất. Nếu đăng ký stream rồi đọc snapshot mà không có ranh giới nhất quán, client có thể xử lý event trùng hoặc đảo thứ tự.

Một thiết kế thường dùng:

1. Server tạo snapshot tại một **high-water mark** (H).
2. Server trả snapshot cùng cursor đại diện cho vị trí (H).
3. Client áp dụng snapshot và lưu checkpoint (H).
4. Client mở server stream từ `after_sequence=H`, nhận các event có sequence lớn hơn (H).

Việc tạo snapshot và high-water mark phải nhất quán theo cùng nguồn dữ liệu hoặc cùng cơ chế log. Nếu không, sequence (H) không chứng minh snapshot bao gồm chính xác mọi thay đổi trước đó.

## 10. Kiểm thử retry và stream position

Các test nên bao phủ cả việc ngắt stream và khôi phục:

| Kịch bản | Assertion |
| --- | --- |
| Stream gửi sequence 1–5 rồi bị ngắt | Client mở RPC mới từ checkpoint đã commit |
| Event cuối được nhận nhưng chưa commit xử lý | Checkpoint không tiến; event được phát lại |
| Event đã commit nhưng response bị phát lại | Dedup ngăn side effect lần hai |
| Sequence nhảy từ 5 sang 7 | Client phát hiện gap, không âm thầm bỏ qua 6 |
| Resume token thuộc tenant khác | Server từ chối token |
| Cursor còn retention | Server bắt đầu từ event ngay sau position |
| Cursor hết retention | Server trả lỗi reset/snapshot theo contract |
| Snapshot + tail | Không mất event giữa snapshot và đăng ký stream |
| Lỗi trước khi nhận headers | Automatic retry có thể xảy ra nếu policy đủ điều kiện |
| Lỗi sau khi nhận headers | Client dùng reconnect/resume ở tầng ứng dụng |
| Caller cancel subscription | Stream và subscription phía server được đóng |

Test cần kiểm tra **số side effect đã commit**, không chỉ số event callback. Với checkpoint và business state trong cùng database, mô phỏng crash trước/sau commit để xác minh event không mất và không áp dụng trùng.

## 11. Sai lầm thường gặp

1. **Tăng `maxAttempts` để khôi phục stream dài.** Automatic retry không replay call đã commit.
2. **Lưu position ngay khi nhận event.** Crash trước khi xử lý xong có thể làm mất dữ liệu.
3. **Dùng sequence không xác định phạm vi.** Sequence theo partition không thể so sánh như một offset toàn cục.
4. **Tạo event ID mới khi replay.** Client không nhận diện được duplicate.
5. **Không deduplicate event.** Resume có thể lặp side effect.
6. **Tin `NOT_FOUND` từ replica trễ.** Có thể kết luận sai rằng command/event chưa tồn tại.
7. **Không ràng buộc token với tenant/filter.** Có thể gây đọc sai phạm vi hoặc lỗ hổng truy cập.
8. **Đăng ký stream sau snapshot mà không có high-water mark.** Event ở khoảng giữa có thể bị mất.
9. **Reconnect không backoff.** Một outage có thể tạo retry storm ở tầng ứng dụng.

## 12. Bài tập vận dụng

Với `orders.v1.OrderEvents/Watch`:

1. Thêm sequence tăng đơn điệu và event ID ổn định cho từng order stream.
2. Triển khai request nhận `after_sequence` hoặc `resume_token`; xác định rõ position có nghĩa là sau event đã xử lý.
3. Viết client lưu checkpoint cùng transaction với cập nhật order và dedup record.
4. Ngắt stream sau sequence 5, reconnect và xác minh server phát từ 6.
5. Mô phỏng crash sau khi nhận event nhưng trước commit; xác minh event được replay.
6. Mô phỏng cursor hết retention; triển khai snapshot/reset rồi tiếp tục tail từ high-water mark.
7. Kiểm tra token không thể dùng chéo tenant hoặc filter.

**Tiêu chí hoàn thành:** người học phân biệt automatic retry với application resume, định nghĩa stream position không mơ hồ, lưu checkpoint sau xử lý bền vững, phát hiện duplicate/gap và khôi phục stream mà không bỏ sót hoặc lặp tác dụng phụ.

### Tài liệu tham khảo

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry commitment, retry buffer và giới hạn replay.
- [gRPC Core Concepts](https://grpc.io/docs/what-is-grpc/core-concepts/): vòng đời RPC và server streaming.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): status kết thúc RPC.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
