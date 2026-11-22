# Deadline và retry

**Retry** là việc gửi lại một RPC khi lần gọi trước thất bại vì nguyên nhân có thể phục hồi. **Deadline** giới hạn tổng thời gian caller chấp nhận chờ kết quả. Hai cơ chế phải được thiết kế cùng nhau: retry có thể tăng khả năng thành công khi lỗi mạng hoặc service tạm thời gián đoạn, nhưng mỗi lần thử và thời gian backoff đều tiêu thụ ngân sách deadline.

Trong **Spring gRPC**, deadline được đặt trên stub gRPC Java; retry có thể được cấu hình ở tầng gRPC bằng service config hoặc điều khiển ở tầng ứng dụng. Dù dùng cách nào, không được tạo một deadline mới dài hơn cho mỗi lần thử. Với command có tác dụng phụ, cần idempotency hoặc cơ chế tra cứu trạng thái vì timeout không chứng minh server chưa thực hiện thao tác.

## 1. Deadline là ngân sách chung cho toàn bộ retry

Giả sử client cấp 1.000 ms cho GetPayment. Lần thử đầu mất 250 ms rồi nhận UNAVAILABLE; client chờ backoff 100 ms và thử lại. Lần thứ hai chỉ còn khoảng 650 ms, chưa tính các chi phí truyền và xử lý tiếp theo.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as gRPC service
    C->>S: Attempt 1 (deadline tổng 1.000 ms)
    S-->>C: UNAVAILABLE sau 250 ms
    Note over C: Backoff 100 ms
    C->>S: Attempt 2 (ngân sách còn lại)
    S-->>C: Response OK
~~~

Deadline của **logical RPC** bao trùm:

- Lần thử đầu tiên.
- Các lần thử tiếp theo.
- Khoảng backoff giữa các lần thử.
- Thời gian truyền request/response và xử lý ở mỗi attempt.

Nếu deadline hết, client nhận DEADLINE_EXCEEDED và không còn ngân sách để tiếp tục retry. Không đặt lại withDeadlineAfter(1, SECONDS) cho mỗi attempt, vì như vậy tổng thời gian có thể tăng theo số lần thử và vượt giới hạn caller.

## 2. Chỉ retry lỗi có khả năng phục hồi

Không phải mọi gRPC status đều phù hợp để retry. Cần phân biệt lỗi tạm thời, lỗi đầu vào, lỗi quyền và trạng thái nghiệp vụ:

| Status | Có nên retry? | Cách xử lý |
| --- | --- | --- |
| **UNAVAILABLE** | Thường có thể, nếu thao tác an toàn | Retry có backoff; có thể do service hoặc kết nối tạm thời không sẵn sàng |
| **RESOURCE_EXHAUSTED** | Chỉ khi biết là throttling tạm thời | Chờ theo backoff/quota; không retry dồn dập khi hệ thống đang quá tải |
| **ABORTED** | Có thể cần retry ở cấp transaction | Đọc lại trạng thái và thực hiện lại toàn bộ transaction theo quy tắc nghiệp vụ |
| **DEADLINE_EXCEEDED** | Không nên tự động retry mặc định | Ngân sách tổng đã hết hoặc kết quả chưa rõ; cần truy vấn trạng thái nếu có side effect |
| **CANCELLED** | Thường không | Caller hoặc context cha đã hủy; retry sẽ đi ngược ý định hủy |
| **INVALID_ARGUMENT** | Không | Sửa request trước khi gọi lại |
| **UNAUTHENTICATED / PERMISSION_DENIED** | Không với cùng thông tin xác thực/quyền | Làm mới credential hoặc sửa quyền theo luồng riêng |
| **FAILED_PRECONDITION** | Thường không với cùng trạng thái | Thay đổi điều kiện nghiệp vụ trước khi thử lại |

Danh sách retryable status phải phản ánh hợp đồng của service. Ví dụ RESOURCE_EXHAUSTED có thể là throttling tạm thời hoặc quota đã hết trong nhiều giờ; chỉ status code không đủ để quyết định retry vô hạn.

## 3. Retry policy của gRPC qua service config

gRPC hỗ trợ retry policy theo service/method thông qua **service config**. Ví dụ sau chỉ retry GetPayment khi nhận UNAVAILABLE:

~~~json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "acme.payment.v1.PaymentService",
          "method": "GetPayment"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 3,
        "initialBackoff": "0.1s",
        "maxBackoff": "0.8s",
        "backoffMultiplier": 2.0,
        "retryableStatusCodes": ["UNAVAILABLE"]
      }
    }
  ]
}
~~~

Ý nghĩa:

- **maxAttempts** là tổng số attempt tối đa, **bao gồm lần gọi đầu tiên**.
- **initialBackoff** là thời gian chờ ban đầu trước lần retry.
- **maxBackoff** giới hạn thời gian chờ tăng dần.
- **backoffMultiplier** điều khiển mức tăng của backoff giữa các lần thử.
- **retryableStatusCodes** xác định status nào cho phép retry.

Service config có thể được cung cấp bởi name resolver hoặc cấu hình mặc định của channel, tùy cách ứng dụng tạo channel. gRPC Java và resolver phải hỗ trợ retry theo phiên bản đang dùng; cần kiểm tra cấu hình thực tế trong môi trường Spring. Không nên giả định chỉ thêm JSON vào file cấu hình bất kỳ là mọi channel tự áp dụng policy.

Retry policy chỉ có hiệu lực trong giới hạn deadline của logical RPC. Nếu deadline hết trước khi đủ attempt, lời gọi kết thúc theo deadline. Khi gRPC đã nhận response headers và call được xem là committed, cơ chế retry không tiếp tục khởi động attempt mới cho call đó.

## 4. Exponential backoff và tránh retry storm

Nếu nhiều client cùng retry ngay sau khi service phục hồi, chúng có thể tạo một đợt tải mới và làm service lại quá tải. **Exponential backoff** tăng thời gian chờ theo từng lần thử:

\[
B_n = \min(B_{\max}, B_0 \times m^{n-1})
\]

Trong đó:

- \(B_0\) là backoff ban đầu.
- \(m\) là hệ số tăng.
- \(B_{\max}\) là backoff tối đa.

Nên có **jitter** để phân tán thời điểm retry của nhiều client. Kết hợp giới hạn số attempt, retry throttling, circuit breaker và giới hạn concurrency giúp tránh khuếch đại sự cố.

Không retry khi deadline còn quá ít để một attempt hợp lý có thể hoàn tất. Một lần retry bắt đầu khi chỉ còn vài mili giây thường chỉ tăng tải và kết thúc ngay bằng timeout.

## 5. Đặt deadline một lần cho logical RPC

Với client gRPC Java, đặt deadline trên stub trước khi gọi:

~~~java
GetPaymentResponse response = paymentStub
    .withDeadlineAfter(1200, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

Nếu dùng retry policy của gRPC, các attempt thuộc cùng logical call và bị giới hạn bởi deadline này. Không bọc từng attempt bằng một stub có timeout mới dài bằng timeout ban đầu.

Trong nested call, deadline còn lại của RPC cha tiếp tục giới hạn service con. Retry downstream cũng phải nằm trong phần ngân sách còn lại đó; không cấp lại toàn bộ ngân sách cho từng service.

## 6. Retry thủ công ở tầng ứng dụng

Một số nghiệp vụ cần quyết định retry dựa trên trạng thái, idempotency hoặc kết quả của nhiều bước. Khi đó có thể điều khiển retry ở tầng ứng dụng. Ví dụ dưới đây minh họa retry có giới hạn cho một truy vấn đọc:

~~~java
Deadline deadline = Deadline.after(1200, TimeUnit.MILLISECONDS);
long backoffMs = 50;
int maxAttempts = 3;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    if (deadline.isExpired()) {
        throw Status.DEADLINE_EXCEEDED
            .withDescription("overall RPC budget exhausted")
            .asRuntimeException();
    }

    try {
        return paymentStub
            .withDeadline(deadline)
            .getPayment(request);
    } catch (StatusRuntimeException ex) {
        boolean retryable =
            ex.getStatus().getCode() == Status.Code.UNAVAILABLE;

        if (!retryable || attempt == maxAttempts) {
            throw ex;
        }

        long remainingMs =
            deadline.timeRemaining(TimeUnit.MILLISECONDS);
        long reserveMs = 30;
        if (remainingMs <= backoffMs + reserveMs) {
            throw ex;
        }

        try {
            TimeUnit.MILLISECONDS.sleep(backoffMs);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw Status.CANCELLED
                .withDescription("retry interrupted")
                .withCause(interrupted)
                .asRuntimeException();
        }

        backoffMs = Math.min(backoffMs * 2, 400);
    }
}
throw Status.UNAVAILABLE
    .withDescription("retry attempts exhausted")
    .asRuntimeException();
~~~

Đây là ví dụ đồng bộ cho thao tác đọc; cần import Deadline, Status, StatusRuntimeException và TimeUnit. Trong production, nên thêm jitter, telemetry cho từng attempt và kiểm thử trường hợp deadline hết trong backoff. Với async flow, dùng scheduler/future thay cho sleep để không chiếm thread.

Không kết hợp retry thủ công với retry tự động của channel một cách thiếu kiểm soát. Nếu cả hai tầng đều thử lại, số attempt thực tế có thể nhân lên. Chọn một tầng chịu trách nhiệm chính hoặc tính rõ ngân sách attempt của cả hai.

## 7. Command có side effect cần idempotency

Giả sử client gọi CreatePayment. Server đã ghi nhận thanh toán nhưng response bị mất hoặc đến sau deadline. Client nhận DEADLINE_EXCEEDED; nếu gửi command mới, hệ thống có thể tạo thanh toán lần hai.

Giải pháp là dùng **idempotency key** ổn định cho cùng một ý định nghiệp vụ:

~~~proto
rpc CreatePayment(CreatePaymentRequest)
    returns (CreatePaymentResponse);

message CreatePaymentRequest {
  string customer_id = 1;
  int64 amount_minor = 2;
  string currency = 3;
  string idempotency_key = 4;
}
~~~

Server cần:

1. Tạo phạm vi duy nhất cho key, ví dụ theo tenant và operation.
2. Lưu key cùng hash của payload và trạng thái xử lý.
3. Ghi key/kết quả một cách nguyên tử với side effect hoặc dùng transaction/outbox phù hợp.
4. Khi nhận lại cùng key và cùng payload, trả kết quả đã lưu hoặc trạng thái operation hiện tại.
5. Từ chối cùng key nhưng payload khác.

Chỉ thêm field idempotency_key vào Protobuf không tạo ra tính idempotent. Cơ chế lưu trữ, khóa đồng thời, thời gian retention và xử lý request đang chạy phải được triển khai ở server.

Nếu client không biết thao tác đã commit hay chưa, nên cung cấp method truy vấn theo operation ID/idempotency key. Đây thường là cách an toàn hơn việc tạo một command mới sau timeout.

## 8. Retry với streaming RPC

Retry streaming phức tạp hơn unary vì một phần dữ liệu có thể đã được gửi hoặc xử lý:

- **Client streaming:** server có thể đã lưu một số chunk trước khi stream bị lỗi.
- **Server streaming:** client có thể đã nhận và xử lý một phần event trước khi lỗi.
- **Bidirectional streaming:** cả hai chiều có thể đã trao đổi command/event trước khi phiên bị hủy.

Không phát lại toàn bộ stream một cách mù quáng. Thiết kế giao thức có:

- Session hoặc upload ID ổn định.
- Message ID hoặc sequence cho từng chunk/event.
- Acknowledgement để xác định dữ liệu đã được chấp nhận.
- Cursor để resume từ vị trí cuối đã xử lý.
- Deduplication để xử lý an toàn message được gửi lại.

Với subscription server streaming, client có thể reconnect từ sequence cuối đã lưu. Với upload, client gửi lại chunk theo upload ID và sequence; server xác nhận chunk đã nhận để tránh ghi trùng. Cơ chế resume là logic ứng dụng, không tự xuất hiện chỉ vì bật retry policy.

## 9. Deadline hết trong lúc retry

Khi deadline hết trong lần attempt hoặc trong thời gian backoff, logical RPC kết thúc với DEADLINE_EXCEEDED. Client không nên bắt đầu một attempt mới với deadline mới nếu đó vẫn là cùng một yêu cầu.

Nếu status cuối là DEADLINE_EXCEEDED:

1. Không kết luận server chưa thực hiện side effect.
2. Với command, truy vấn operation state hoặc retry cùng idempotency key theo hợp đồng server.
3. Với stream, dùng session ID/cursor để resume nếu giao thức hỗ trợ.
4. Ghi nhận số attempt, thời gian backoff và ngân sách còn lại.
5. Không retry tiếp nếu caller đã hủy hoặc deadline tổng đã hết.

CANCELLED thường thể hiện caller không còn muốn kết quả; retry tự động lúc này có thể đi ngược ý định của caller.

## 10. Kiểm thử retry và deadline

Kiểm thử cần xác nhận cả số lần gọi, thời gian và side effect:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Attempt đầu UNAVAILABLE, attempt sau OK | Retry đúng số lần và trả kết quả |
| Tất cả attempt đều UNAVAILABLE | Dừng tại maxAttempts |
| Deadline hết trong backoff | Không bắt đầu attempt tiếp theo |
| Caller đặt deadline ngắn | Tổng thời gian không vượt deadline |
| Command commit nhưng response bị mất | Cùng idempotency key không tạo side effect lần hai |
| INVALID_ARGUMENT hoặc PERMISSION_DENIED | Không retry vô ích |
| Stream lỗi sau một phần message | Resume bằng cursor/sequence, không xử lý trùng |

Có thể dùng gRPC in-process server hoặc fake downstream để điều khiển status và độ trễ. Dùng latch/future thay cho Thread.sleep dài trong test. Với Spring, integration test cần xác nhận service config/interceptor được gắn vào đúng channel và retry policy có hiệu lực ở môi trường thực tế.

## 11. Quan sát retry trong production

Theo dõi theo full method name:

- Tổng số logical RPC và tổng số attempt.
- Tỷ lệ thành công ở attempt đầu và sau retry.
- Status của từng attempt và status cuối cùng.
- Thời gian backoff, deadline còn lại trước mỗi attempt.
- Số logical call kết thúc bằng DEADLINE_EXCEEDED.
- Retry throttling, circuit breaker và queue saturation.
- Tỷ lệ idempotency hit, conflict key và operation chưa rõ trạng thái.
- Với streaming: số lần reconnect, sequence bị lặp hoặc bị thiếu.

Nếu tỷ lệ retry tăng, cần tìm nguyên nhân gốc như service không sẵn sàng, pool cạn, queue tăng hoặc network bất ổn. Không xem retry thành công là bằng chứng hệ thống khỏe; nhiều attempt có thể đang che giấu lỗi và làm tăng tải.

## 12. Ghi nhớ và tự kiểm tra

**Deadline giới hạn toàn bộ logical RPC; retry chỉ sử dụng phần ngân sách còn lại.** Chọn status có thể retry theo hợp đồng, dùng backoff có giới hạn và tránh retry storm. Với command có side effect, dùng idempotency key hoặc operation ID vì timeout không chứng minh server chưa commit. Với streaming, cần session, sequence và resume thay vì phát lại mù quáng.

Tự kiểm tra:

1. Vì sao không được cấp lại toàn bộ deadline ban đầu cho mỗi retry?
2. maxAttempts trong retry policy bao gồm những lần gọi nào?
3. Vì sao DEADLINE_EXCEEDED không phải status mặc định phù hợp để retry?
4. Làm thế nào để retry CreatePayment mà không tạo thanh toán trùng?
5. Vì sao streaming cần cursor hoặc sequence khi reconnect sau lỗi?

Kết hợp deadline, retry policy có kiểm soát, idempotency và quan sát theo attempt giúp Spring gRPC phục hồi trước lỗi tạm thời mà vẫn giữ giới hạn thời gian, tải hệ thống và tính nhất quán nghiệp vụ.
