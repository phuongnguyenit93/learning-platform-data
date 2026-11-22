# Deadline qua message boundary

## 1. Deadline không tự đi qua broker

Trong **SPRING_GRPC**, gRPC client gọi service theo hợp đồng Protocol Buffers. Khi service chuyển request thành command rồi publish vào message broker, luồng xử lý đi qua một ranh giới bất đồng bộ: RPC có thể kết thúc trước khi consumer nhận hoặc xử lý message.

Deadline của gRPC giới hạn thời gian một RPC được phép tiếp tục. Nó được quản lý trong runtime gRPC và gắn với call hiện tại. Broker không tự hiểu `io.grpc.Deadline`, còn consumer chạy ở process khác không thể đọc `Context.current()` của RPC đã kết thúc.

Vì vậy, nếu deadline có ý nghĩa với xử lý phía sau broker, ingress phải chuyển ý nghĩa thời gian đó thành dữ liệu tường minh trong command envelope hoặc message headers. Consumer đọc dữ liệu này, tính ngân sách còn lại và quyết định có tiếp tục xử lý hay không.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as Spring gRPC ingress
    participant B as Message broker
    participant W as Consumer
    participant D as Downstream service
    C->>G: RPC + deadline
    G->>G: Read remaining RPC budget
    G->>B: Command + explicit expiry/budget
    G-->>C: ACCEPTED (nếu đã lưu bền vững)
    Note over B,W: Queue delay consumes time budget
    B->>W: Deliver command
    W->>W: Recalculate remaining budget
    W->>D: RPC with remaining deadline
    D-->>W: Result or deadline exceeded
~~~

Điểm cốt lõi: thời gian trong queue cũng tiêu thụ ngân sách nếu deadline được định nghĩa cho toàn bộ workflow. Consumer không được bắt đầu một bộ đếm mới đầy đủ khi nhận message.

## 2. Phân biệt RPC deadline và command expiry

Đây là hai khái niệm khác nhau và không nên gộp thành một field:

| Khái niệm | Ý nghĩa | Ai quyết định? |
|---|---|---|
| RPC deadline | Thời hạn client chờ một lần gọi gRPC | Client, có thể bị giới hạn bởi server/gateway |
| Command expiry | Thời điểm command không còn hợp lệ để bắt đầu hoặc tiếp tục nghiệp vụ | Hợp đồng nghiệp vụ và server policy |
| Processing budget | Khoảng thời gian tối đa một worker được phép dùng cho bước xử lý | Service/workflow policy |
| Operation SLA | Mục tiêu thời gian hoàn thành toàn bộ operation | Sản phẩm/vận hành |

Ví dụ, client gửi `SubmitOrder` với deadline 500 ms. Ingress có thể ghi command vào outbox trong 20 ms và trả `ACCEPTED`. RPC đã hoàn tất nhanh, nhưng command có thể cần vài giây để worker xử lý. Nếu lấy RPC deadline làm command expiry, command sẽ hết hạn ngay cả khi hệ thống đã nhận trách nhiệm xử lý.

Chỉ ánh xạ RPC deadline thành command expiry khi API thực sự định nghĩa rằng yêu cầu nghiệp vụ chỉ còn giá trị đến thời điểm đó. Với command bất đồng bộ thông thường, RPC deadline chủ yếu giới hạn thời gian ingress phản hồi; command expiry phải đến từ business policy hoặc field riêng được kiểm tra và giới hạn ở server.

## 3. Xác định deadline tại ingress

Trong gRPC Java, deadline hiện tại có thể đọc từ `Context.current().getDeadline()`. `timeRemaining(...)` trả về ngân sách còn lại dựa trên clock monotonic mà gRPC dùng cho call:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import io.grpc.Status;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.TimeUnit;

public final class DeadlinePolicy {
    private final Clock clock;

    public DeadlinePolicy(Clock clock) {
        this.clock = clock;
    }

    public Duration remainingRpcBudget() {
        Deadline deadline = Context.current().getDeadline();
        if (deadline == null) {
            return null; // Không có deadline do caller đặt.
        }

        long remainingNanos =
                deadline.timeRemaining(TimeUnit.NANOSECONDS);
        if (remainingNanos <= 0) {
            throw Status.DEADLINE_EXCEEDED
                    .withDescription("RPC deadline has expired")
                    .asRuntimeException();
        }
        return Duration.ofNanos(remainingNanos);
    }

    public Instant toAbsoluteTime(Duration remaining) {
        return clock.instant().plus(remaining);
    }
}
~~~

`Deadline` dựa trên thời gian monotonic, thích hợp để đo thời gian còn lại trong process. Không serialize trực tiếp đối tượng `Deadline` hoặc giá trị nanoTime sang broker vì giá trị monotonic chỉ có ý nghĩa trong môi trường runtime hiện tại.

Nếu cần truyền thời điểm qua process boundary, chuyển thành timestamp tuyệt đối UTC (`Instant`) hoặc một định dạng thời gian chuẩn. Khi consumer nhận message, nó tính lại khoảng còn lại theo clock của consumer.

Nếu RPC không có deadline, service cần policy riêng: từ chối request không có deadline, áp dụng deadline mặc định cho ingress, hoặc chỉ đặt command expiry theo business policy. Không được hiểu “không có deadline” là thời gian vô hạn an toàn.

## 4. Không tự động biến RPC deadline thành command expiry

Với command bất đồng bộ, nên lưu riêng hai trường nếu cả hai đều cần:

~~~json
{
  "commandId": "cmd-100",
  "correlationId": "corr-100",
  "rpcDeadlineAt": "2026-11-19T10:15:30.500Z",
  "commandExpiresAt": "2026-11-19T10:25:00Z",
  "payload": {
    "orderId": "order-42"
  }
}
~~~

`rpcDeadlineAt` có thể phục vụ chẩn đoán hoặc phân tích thời điểm caller ngừng chờ. Nó không phải lệnh tự hủy command. `commandExpiresAt` mới là thời điểm nghiệp vụ không còn cho phép xử lý, nếu hợp đồng command có expiry.

Nếu command không có expiry nghiệp vụ, có thể bỏ field này và dùng operation SLA/retention policy riêng. Không điền một timestamp tùy ý chỉ để message envelope trông đầy đủ.

## 5. Tạo command expiry theo business policy

Nếu command có thời hạn, server nên xác định hoặc kiểm soát nó. Nếu client được phép yêu cầu một thời điểm hết hạn, server cần kiểm tra giá trị đó, giới hạn lifetime tối đa và không cho phép client kéo dài quá policy.

Ví dụ khái niệm:

~~~java
public Instant resolveCommandExpiry(
        Instant requestedExpiry,
        Duration maximumLifetime,
        Clock clock) {

    Instant now = clock.instant();
    Instant serverMaximum = now.plus(maximumLifetime);

    if (requestedExpiry == null) {
        return serverMaximum;
    }
    if (!requestedExpiry.isAfter(now)) {
        throw new IllegalArgumentException("command expiry is in the past");
    }
    return requestedExpiry.isBefore(serverMaximum)
            ? requestedExpiry
            : serverMaximum;
}
~~~

Đây là policy minh họa. Có API nên từ chối thời điểm vượt giới hạn thay vì clamp; điều quan trọng là hành vi phải được công bố rõ. Không tin timestamp do caller gửi mà không xác thực, vì client clock có thể sai hoặc caller có thể cố tình đặt thời hạn quá xa.

## 6. Đưa deadline vào command envelope

Envelope nên phân biệt thời điểm tạo, thời điểm hết hạn nghiệp vụ và correlation:

~~~java
import java.time.Instant;

public record CommandEnvelope<T>(
        String messageId,
        String commandId,
        String correlationId,
        String messageType,
        int schemaVersion,
        Instant createdAt,
        Instant commandExpiresAt,
        T payload) {}
~~~

Nếu cần giữ RPC deadline để phân tích, thêm `rpcDeadlineAt` như metadata chẩn đoán. Tránh dùng một field tên chung `deadline` vì consumer không biết đó là deadline của lần gọi gRPC, command expiry hay SLA.

Serialize timestamp theo chuẩn UTC, ví dụ ISO-8601 hoặc protobuf `google.protobuf.Timestamp`. Tránh dùng chuỗi ngày giờ không có timezone hoặc số epoch có đơn vị không rõ ràng.

## 7. Consumer tính ngân sách còn lại

Khi nhận message, consumer tính thời gian còn lại từ `commandExpiresAt`. Nếu đã hết hạn, không bắt đầu side effect nghiệp vụ:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class CommandTimeBudget {
    private final Clock clock;

    public CommandTimeBudget(Clock clock) {
        this.clock = clock;
    }

    public Duration remainingUntil(Instant expiresAt) {
        if (expiresAt == null) {
            return null; // Command không có expiry nghiệp vụ.
        }

        Duration remaining = Duration.between(clock.instant(), expiresAt);
        if (remaining.isZero() || remaining.isNegative()) {
            throw new CommandExpiredException();
        }
        return remaining;
    }
}
~~~

Không tính lại ngân sách từ `createdAt + fullProcessingTimeout` ở mỗi consumer. Cách đó làm thời gian queue bị bỏ qua và mỗi hop được cấp lại toàn bộ thời gian, khiến workflow có thể kéo dài vô hạn.

Nếu một command đi qua nhiều worker, mỗi worker phải dùng cùng `commandExpiresAt` hoặc một expiry ngắn hơn do policy nhánh xử lý quy định. Không được tự ý kéo dài expiry ở mỗi hop.

## 8. Truyền phần ngân sách còn lại sang downstream gRPC

Nếu consumer gọi một service gRPC khác, hãy tạo deadline mới từ ngân sách còn lại:

~~~java
Duration remaining = timeBudget.remainingUntil(
        envelope.commandExpiresAt());

if (remaining != null) {
    long remainingNanos = remaining.toNanos();
    if (remainingNanos <= 0) {
        throw new CommandExpiredException();
    }

    downstreamStub
            .withDeadlineAfter(remainingNanos, TimeUnit.NANOSECONDS)
            .reserveInventory(request);
} else {
    downstreamStub.reserveInventory(request);
}
~~~

Ví dụ trên giả định `downstreamStub` là generated blocking stub; async/future stub cần cách gọi tương ứng. Trong thực tế, nên trừ một phần ngân sách cho serialization, commit và cleanup, đồng thời đặt timeout tối đa cho từng dependency.

Không truyền nguyên timeout ban đầu xuống mọi service. Nếu ingress đã tiêu thụ 300 ms trong tổng budget 1 giây, downstream chỉ nên nhận phần còn lại xấp xỉ 700 ms, không phải thêm một giây mới.

Với fan-out song song, các nhánh có thể cùng dùng chung thời điểm expiry nhưng mỗi nhánh phải có timeout và giới hạn concurrency riêng. Một nhánh chậm không nên giữ tài nguyên vô hạn sau khi operation hết hạn.

## 9. Clock monotonic và wall clock

Deadline nội bộ trong một process nên dựa trên monotonic clock vì wall clock có thể nhảy khi NTP điều chỉnh hoặc máy đổi thời gian. Timestamp cần truyền qua broker phải là thời điểm tuyệt đối, thường UTC, vì consumer khác process không thể dùng cùng monotonic origin.

| Loại thời gian | Dùng ở đâu | Có serialize qua broker? |
|---|---|---|
| Monotonic deadline / remaining nanos | Tính thời gian còn lại trong cùng process | Không |
| UTC `Instant` | Truyền thời điểm tạo/hết hạn qua service và broker | Có |
| Duration còn lại | Ngân sách tạm thời trong một hop | Có thể truyền, nhưng consumer phải trừ thời gian đã trôi qua; không reset ở mỗi hop |

Do clock giữa các máy có thể lệch, consumer nên áp dụng clock synchronization, giới hạn skew được chấp nhận và chọn policy an toàn. Với expiry mang tính bảo mật hoặc tài chính, không nên cho phép clock skew kéo dài quyền thực hiện command; có thể dùng database/server time hoặc nguồn thời gian chuẩn theo kiến trúc.

`Instant.now()` có thể được inject qua `Clock` để test và kiểm soát. Tránh gọi wall clock rải rác ở nhiều nơi làm khó kiểm thử và tạo kết quả không nhất quán.

## 10. Broker TTL không thay thế consumer expiry check

Broker có thể cung cấp cơ chế TTL hoặc retention, nhưng semantics phụ thuộc sản phẩm:

- RabbitMQ hỗ trợ message TTL và queue/message expiration theo cấu hình; message hết hạn có thể bị loại bỏ hoặc dead-letter tùy policy.
- Kafka retention thường áp dụng theo thời gian/size của log segment, không phải một TTL độc lập chính xác cho từng command record. Consumer vẫn cần kiểm tra `commandExpiresAt`.
- Các broker khác có thể có visibility timeout, scheduled delivery hoặc expiry semantics riêng.

Không dựa hoàn toàn vào broker để bảo đảm command hết hạn đúng thời điểm. Consumer phải kiểm tra expiry ngay trước khi thực hiện side effect quan trọng. Broker TTL là tối ưu vận hành để giảm message không còn hữu ích, không phải nguồn chân lý duy nhất của nghiệp vụ.

## 11. Retry không được làm mới deadline

Khi consumer retry do lỗi tạm thời, phải giữ nguyên command ID, idempotency key và `commandExpiresAt`:

~~~text
Command created: 10:00:00
Command expires: 10:05:00

Attempt 1: 10:01:00 -> transient database error
Attempt 2: 10:02:30 -> downstream timeout
Attempt 3: 10:04:50 -> only 10 seconds remain
After 10:05:00 -> do not execute; mark expired / dead-letter
~~~

Không đặt lại expiry thành `now + 5 minutes` ở mỗi lần retry. Nếu làm vậy, một command có thể được kéo dài mãi khi liên tục gặp lỗi.

Backoff cần nằm trong ngân sách còn lại. Nếu thời gian chờ retry dự kiến vượt quá expiry, chuyển command sang trạng thái hết hạn hoặc dead-letter theo policy thay vì lên lịch một lần thử vô ích.

Nếu nghiệp vụ cho phép gia hạn, đó phải là một quyết định mới có authorization và audit, không phải side effect ngầm của retry.

## 12. Hết hạn khi command đã được nhận

Khi consumer phát hiện command hết hạn, cần xác định trạng thái cuối và hành động:

- Không bắt đầu side effect nếu command chưa được thực hiện.
- Ghi operation state `EXPIRED` hoặc failure code tương đương.
- Ack/commit message sau khi trạng thái hết hạn đã được ghi bền vững.
- Có thể phát `CommandExpired` nếu hệ thống cần thông báo cho caller hoặc service khác.
- Giữ correlation ID và operation ID để truy vết.

Nếu command đã thực hiện một phần, expiry không tự đảo ngược side effect. Cần workflow compensation hoặc command bù theo nghiệp vụ. Không xóa message lịch sử để giả vờ operation chưa từng chạy.

## 13. Deadline và cancellation là hai tín hiệu khác nhau

Khi client hủy RPC hoặc deadline của RPC hết:

- Ingress có thể ngừng chờ và giải phóng pending future.
- Nếu command chưa được lưu bền vững, ingress có thể dừng trước khi publish.
- Nếu outbox transaction đã commit hoặc broker đã nhận message, command vẫn có thể được xử lý.
- Worker không nhận được cancellation của `io.grpc.Context` từ RPC gốc.

Nếu caller cần hủy nghiệp vụ sau khi command đã được nhận, cung cấp RPC/command `CancelOperation` riêng. Worker kiểm tra trạng thái operation và cancellation request trước các bước side effect có thể hủy. Phải xử lý race giữa completion và cancellation: operation đã hoàn tất có thể không còn hủy được.

Không dùng RPC deadline làm cơ chế cancellation xuyên broker. Deadline chỉ cho biết một budget đã hết; cancellation là một tín hiệu điều khiển cần được truyền và xử lý theo hợp đồng riêng.

## 14. Ánh xạ deadline và expiry sang gRPC status

Status của lần RPC và trạng thái của command cần được tách biệt:

| Tình huống | Kết quả phù hợp |
|---|---|
| RPC deadline hết trước khi ingress ghi nhận command | `DEADLINE_EXCEEDED`; không trả `ACCEPTED` |
| Outbox commit thành công trước khi RPC deadline hết | `OK` với operation state `ACCEPTED`, nếu contract định nghĩa như vậy |
| Broker/consumer xử lý sau khi RPC đã kết thúc | Cập nhật operation state; không thể gửi response vào RPC cũ |
| Consumer nhận command đã hết `commandExpiresAt` | Operation `EXPIRED` hoặc failure code nghiệp vụ |
| Downstream gRPC call hết remaining budget | Xử lý timeout theo retry/business policy, không tự cấp lại full budget |
| Client cancel sau durable acceptance | Command vẫn theo policy; cancellation nghiệp vụ cần request riêng |

Nếu RPC trả `DEADLINE_EXCEEDED`, client không thể suy ra chắc chắn command chưa được nhận. Kết quả có thể không chắc chắn nếu timeout xảy ra đúng lúc commit/ack. Client cần truy vấn theo idempotency key hoặc operation ID trước khi tạo một ý định mới.

## 15. Quan sát deadline xuyên message boundary

Theo dõi các mốc thời gian:

- RPC deadline budget tại ingress và remaining budget trước khi persist.
- `createdAt` và `commandExpiresAt` của message.
- Queue age khi consumer bắt đầu xử lý.
- Remaining budget tại từng worker/hop.
- Downstream RPC latency và deadline exceeded.
- Số command hết hạn trước khi xử lý, hết hạn khi retry và hết hạn trong lúc đang chạy.
- Retry count, backoff duration và dead-letter reason.
- Chênh lệch clock được phát hiện giữa producer/consumer nếu có.

Log/trace nên mang `operationId`, `commandId`, `correlationId`, message ID và expiry timestamp đã được kiểm soát. Không dùng các ID này làm metric label có cardinality cao; metrics nên nhóm theo message type, consumer, outcome và expiry reason.

Khi thấy command xử lý quá hạn, kiểm tra queue age, retry backoff, clock skew, consumer concurrency và việc mỗi hop có reset budget hay không. Nếu RPC timeout nhưng operation vẫn chạy, kiểm tra API có phân biệt RPC deadline với command expiry chưa.

## 16. Kiểm thử deadline qua message boundary

Kiểm thử nên dùng `Clock` giả hoặc clock có thể điều khiển để tránh test phụ thuộc thời gian thực:

| Kịch bản | Điều cần xác minh |
|---|---|
| RPC có deadline còn đủ | Ingress đọc đúng remaining budget |
| RPC deadline đã hết trước persist | Trả `DEADLINE_EXCEEDED`, không ghi nhận command |
| RPC không có deadline | Áp dụng default/reject policy đã công bố |
| Command có expiry nghiệp vụ | Envelope lưu đúng UTC timestamp |
| Queue delay tiêu thụ gần hết budget | Consumer chỉ dùng phần thời gian còn lại |
| Command hết hạn trước khi consumer chạy | Không thực hiện side effect; operation chuyển `EXPIRED` |
| Downstream gRPC call | Deadline được đặt bằng remaining budget |
| Retry nhiều lần | `commandExpiresAt` không bị làm mới |
| Backoff vượt expiry | Không lên lịch retry vô ích |
| Clock skew | Policy xử lý skew đúng giới hạn |
| Client cancel sau outbox commit | Durable command không tự bị xóa |
| Command đã thực hiện một phần | Expiry không tự rollback; compensation theo nghiệp vụ |
| Broker TTL khác nhau | Consumer expiry gate vẫn bảo vệ side effect |

Integration test cần xác minh message envelope được serialize/deserialise đúng, queue delay được tính, retry giữ expiry và consumer không thực hiện side effect sau expiry. Với Kafka, test không nên giả định retention là per-message TTL; hãy kiểm tra consumer-side expiry enforcement.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nghĩ gRPC deadline tự truyền qua broker | Consumer không biết budget còn lại | Serialize expiry/budget rõ ràng |
| Dùng monotonic nanoTime làm timestamp message | Giá trị vô nghĩa ở process khác | Chuyển sang UTC `Instant` |
| Dùng RPC deadline làm command expiry mặc định | Command đã accepted bị loại khi client ngừng chờ | Tách RPC deadline và business expiry |
| Cấp full timeout mới ở mỗi consumer | Workflow kéo dài vô hạn | Giữ một absolute expiry và tính remaining |
| Làm mới expiry khi retry | Command không bao giờ hết hạn | Giữ nguyên expiry ban đầu |
| Chỉ dựa vào broker TTL | Một số broker không có per-message expiry chính xác | Consumer kiểm tra expiry trước side effect |
| Bỏ qua clock skew | Command bị hết hạn sớm hoặc muộn | Đồng bộ clock và đặt skew policy |
| Coi RPC cancellation là hủy command | Worker vẫn thực hiện sau khi caller hủy | Có command cancellation riêng |
| Không lưu expiry trong outbox | Relay/retry mất deadline gốc | Persist expiry cùng command |

**Ghi nhớ:** Deadline của gRPC không tự đi qua message boundary. Ingress phải chuyển thời hạn cần thiết thành timestamp UTC hoặc budget tường minh; consumer tính remaining budget và truyền phần còn lại cho downstream. Phân biệt RPC deadline với command expiry, giữ nguyên expiry qua retry, kiểm tra hết hạn ngay trước side effect và không dựa riêng vào broker TTL. RPC cancellation không tự hủy command đã được ghi nhận bền vững.
