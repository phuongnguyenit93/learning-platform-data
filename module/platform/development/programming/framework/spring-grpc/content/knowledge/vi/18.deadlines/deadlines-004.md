# Deadline hết hạn tạo DEADLINE_EXCEEDED

**DEADLINE_EXCEEDED** là gRPC status cho biết lời gọi không hoàn tất trong thời gian mà client cho phép. Khi client đặt deadline, gRPC theo dõi thời gian còn lại trong suốt RPC. Nếu deadline hết trước khi client nhận được kết quả hoàn tất, client kết thúc lời gọi với status này.

Trong **Spring gRPC**, ứng dụng Java thường nhìn thấy status qua **StatusRuntimeException** ở blocking stub hoặc callback **onError(Throwable)** ở async stub. Phía server thường quan sát **cancellation** của RPC qua **io.grpc.Context**, vì deadline phía client đã khiến lời gọi không còn cần tiếp tục. Cần phân biệt hai góc nhìn này để xử lý timeout, dừng công việc, bảo toàn tác dụng phụ và quyết định retry an toàn.

## 1. DEADLINE_EXCEEDED có nghĩa gì?

Một RPC có deadline là một lời gọi có **thời điểm kết thúc muộn nhất**. Ví dụ client cấp 500 ms. Nếu sau 500 ms client vẫn chưa nhận được kết quả hoàn tất, gRPC báo **DEADLINE_EXCEEDED**.

Status này không nhất thiết chứng minh server đã xử lý chậm toàn bộ 500 ms. Ngân sách có thể đã bị tiêu thụ bởi:

- Thời gian chờ connection, channel hoặc tài nguyên phía client.
- Độ trễ truyền request và response.
- Hàng đợi trước khi request được xử lý.
- Thời gian chạy logic server hoặc truy vấn database.
- Lời gọi downstream qua một hay nhiều service khác.
- Response đã được tạo nhưng đến client sau khi deadline hết.

~~~mermaid
flowchart LR
    A["Client đặt deadline"] --> B["Chờ / truyền request"]
    B --> C["Server xử lý"]
    C --> D["Downstream / database"]
    D --> E["Trả response"]
    E --> F{"Client nhận trước deadline?"}
    F -->|"Có"| G["Status OK"]
    F -->|"Không"| H["DEADLINE_EXCEEDED"]
~~~

Deadline áp dụng cho **toàn bộ RPC**, không chỉ phần code nghiệp vụ ở server. Với streaming RPC, thời gian sống của cả stream cũng nằm trong ngân sách; gửi thêm message không tự khởi động lại đồng hồ.

## 2. Client nhận DEADLINE_EXCEEDED như thế nào?

Với blocking stub, deadline thường được đặt bằng withDeadlineAfter. Khi hết hạn, lời gọi ném StatusRuntimeException:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;

GetPaymentRequest request = GetPaymentRequest.newBuilder()
    .setPaymentId("payment-901")
    .build();

try {
    GetPaymentResponse response = paymentStub
        .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
        .getPayment(request);

    System.out.println(response.getState());
} catch (StatusRuntimeException ex) {
    Status.Code code = ex.getStatus().getCode();

    if (code == Status.Code.DEADLINE_EXCEEDED) {
        // Client không nhận được kết quả trong ngân sách.
        // Kiểm tra trạng thái nghiệp vụ trước khi retry command.
    } else {
        throw ex;
    }
}
~~~

Với async stub, lỗi được chuyển tới callback onError:

~~~java
var stub = PaymentServiceGrpc.newStub(channel)
    .withDeadlineAfter(500, TimeUnit.MILLISECONDS);

stub.getPayment(request, new StreamObserver<GetPaymentResponse>() {
    @Override
    public void onNext(GetPaymentResponse response) {
        handleResponse(response);
    }

    @Override
    public void onError(Throwable error) {
        Status.Code code = Status.fromThrowable(error).getCode();
        if (code == Status.Code.DEADLINE_EXCEEDED) {
            handleTimeout();
        } else {
            handleRpcFailure(code, error);
        }
    }

    @Override
    public void onCompleted() {
        // RPC hoàn tất bình thường.
    }
});
~~~

Đối với unary, client thường nhận một response hoặc một lỗi. Đối với streaming, client có thể đã nhận một số message qua onNext trước khi onError báo DEADLINE_EXCEEDED. Những message đã nhận không biến RPC thành thành công; client phải áp dụng quy tắc nghiệp vụ cho dữ liệu từng phần.

## 3. Client status và server cancellation là hai góc nhìn

Đây là điểm quan trọng nhất khi chẩn đoán:

| Phía quan sát | Điều thường thấy khi deadline client hết |
| --- | --- |
| **Client** | RPC kết thúc với **DEADLINE_EXCEEDED** |
| **Server handler** | Context của RPC bị đánh dấu cancelled |
| **Outbound call của server** | Các lời gọi con gắn với context có thể bị hủy theo |
| **Tác vụ Java tự viết** | Chỉ dừng nếu code hoặc API tác vụ hỗ trợ cancellation |

Server không nhất thiết nhận một callback ứng dụng mang status DEADLINE_EXCEEDED để xử lý. Khi client deadline hết, transport hủy lời gọi; server thường quan sát context cancellation. Vì vậy, đừng chỉ chờ một exception DEADLINE_EXCEEDED trong code server rồi mới cleanup.

Ngược lại, nếu chính server gọi một downstream RPC và downstream trả DEADLINE_EXCEEDED, server có thể nhận StatusRuntimeException tương ứng. Đó là lỗi từ lời gọi con; nó khác với việc RPC cha bị client hủy.

## 4. Server phát hiện deadline hết và dừng công việc

Trong handler gRPC Java, đọc context hiện tại để kiểm tra deadline và cancellation:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (rpcContext.isCancelled()
        || (deadline != null
            && deadline.timeRemaining(TimeUnit.NANOSECONDS) <= 0)) {
    // Không bắt đầu thêm công việc cho RPC đã hết hạn.
    return;
}
~~~

Kiểm tra này hữu ích trước các bước tốn kém, nhưng không thay thế cancellation xuyên suốt. Nếu server đang chờ một truy vấn blocking hoặc một tác vụ nền, cần API có thể hủy, timeout riêng cho tài nguyên đó hoặc cơ chế kiểm tra context trong quá trình xử lý.

Có thể đăng ký listener để giải phóng tài nguyên khi RPC bị hủy:

~~~java
Context rpcContext = Context.current();
rpcContext.addListener(cancelledContext -> {
    downstreamFuture.cancel(true);
    closeTemporaryFile();
    releaseReservationLock();
}, Runnable::run);
~~~

Các tên future và hàm cleanup là ví dụ theo ứng dụng. Cleanup phải idempotent, không được giải phóng tài nguyên hai lần và không nên chặn callback gRPC quá lâu. Nếu công việc đã commit, cancellation không tự rollback transaction.

## 5. Nguyên nhân thường gặp và cách khoanh vùng

Không nên xử lý mọi DEADLINE_EXCEEDED bằng cách tăng deadline. Trước hết cần xác định thời gian bị tiêu thụ ở đâu:

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Request đến server khi deadline còn rất ít | Chậm ở client, gateway, queue hoặc network | Đo thời gian trước khi gọi và thời gian truyền |
| Server nhận request với ngân sách đủ nhưng xử lý lâu | Logic nghiệp vụ, lock contention, thread pool hoặc DB | Trace từng bước và đo thời gian chờ |
| Service cha timeout khi gọi service con | Downstream chậm hoặc ngân sách con không phù hợp | Theo dõi deadline còn lại ở từng hop |
| Timeout tăng khi tải cao | Quá tải, queue tăng, pool cạn | Kiểm tra CPU, memory, queue depth và pool saturation |
| Server đã hoàn tất nhưng client vẫn timeout | Response/trailers về muộn hoặc network bất ổn | Đối chiếu timestamp server, client và trace |
| Chỉ streaming timeout | Stream sống lâu hơn deadline hoặc consumer chậm | Xem tuổi stream, throughput và chính sách reconnect |

Một deadline ngắn có thể làm lộ ra quá tải vốn đã tồn tại. Tăng deadline có thể giảm tỷ lệ lỗi trước mắt nhưng đồng thời giữ request, thread hoặc tài nguyên lâu hơn, khiến tình trạng quá tải nặng thêm.

## 6. DEADLINE_EXCEEDED không chứng minh thao tác chưa xảy ra

Client chỉ biết rằng **không nhận được kết quả trước deadline**. Server có thể đã thực hiện và commit thao tác, nhưng response bị trễ hoặc bị mất. Điều này đặc biệt nguy hiểm với command có tác dụng phụ:

- Tạo đơn hàng.
- Trừ tiền hoặc phát lệnh thanh toán.
- Giữ hoặc giải phóng hàng tồn kho.
- Gửi thông báo hoặc tạo tác vụ bên ngoài.

Nếu client tự retry với một request mới, thao tác có thể được thực hiện hai lần. Cách xử lý an toàn:

1. Tạo **idempotency key** ổn định cho một ý định nghiệp vụ.
2. Server lưu key cùng kết quả xử lý một cách nguyên tử với thay đổi nghiệp vụ.
3. Nếu nhận lại cùng key và cùng payload, trả kết quả đã ghi nhận.
4. Nếu cùng key nhưng payload khác, từ chối theo quy tắc rõ ràng.
5. Nếu cần biết trạng thái sau timeout, cung cấp API truy vấn theo operation ID hoặc idempotency key.

Idempotency không tự có chỉ vì request chứa một field key; server phải thực thi và lưu trạng thái chống lặp. Với tác vụ dài, có thể dùng mô hình nhận command nhanh, trả operation ID, rồi cho client truy vấn hoặc theo dõi trạng thái riêng.

## 7. Phân biệt với CANCELLED và UNAVAILABLE

Ba status này có thể xuất hiện trong các tình huống mạng và deadline, nhưng ý nghĩa khác nhau:

| Status | Ý nghĩa chính | Cách xử lý |
| --- | --- | --- |
| **DEADLINE_EXCEEDED** | Không hoàn tất trước deadline của lời gọi | Xem lại ngân sách và trạng thái tác vụ |
| **CANCELLED** | Lời gọi bị hủy bởi client, context cha hoặc tác nhân khác | Dừng công việc và cleanup |
| **UNAVAILABLE** | Service hoặc kết nối tạm thời không sẵn sàng | Retry có kiểm soát nếu thao tác an toàn |
| **RESOURCE_EXHAUSTED** | Vượt quota hoặc giới hạn tài nguyên | Giảm tải, xem quota và backpressure |
| **FAILED_PRECONDITION** | Trạng thái hiện tại không cho phép thao tác | Sửa điều kiện nghiệp vụ trước khi thử lại |

Không nên đổi mọi lỗi downstream thành DEADLINE_EXCEEDED. Hãy giữ status có ý nghĩa để client, telemetry và retry policy phân loại đúng. Nếu server tự đặt timeout cho một bước nghiệp vụ và quyết định trả DEADLINE_EXCEEDED, mô tả lỗi nên chỉ rõ bước nào hết ngân sách mà không tiết lộ thông tin nội bộ nhạy cảm.

## 8. DEADLINE_EXCEEDED trong streaming RPC

Deadline của streaming RPC áp dụng cho **toàn bộ lời gọi**, không phải từng message:

- **Server streaming:** client có thể nhận một số response rồi stream kết thúc do deadline.
- **Client streaming:** client có thể đã gửi một phần request; server có thể đã xử lý một phần trước khi deadline hết.
- **Bidirectional streaming:** hai chiều có thể đã trao đổi nhiều message trước khi lời gọi bị hủy.

Với server streaming, client phải phân biệt stream hoàn tất bình thường bằng onCompleted với stream lỗi bằng onError. Nếu đã nhận event đến sequence 120 rồi gặp DEADLINE_EXCEEDED, client có thể dùng sequence/cursor để kết nối lại từ vị trí phù hợp, nếu server hỗ trợ replay.

Với client streaming hoặc bidirectional, không phát lại toàn bộ dữ liệu một cách mù quáng. Dùng message ID, sequence, upload ID và cơ chế deduplication để tránh xử lý trùng. Server cần dừng producer và giải phóng subscription/queue khi context bị hủy.

## 9. Kiểm thử DEADLINE_EXCEEDED

Một bộ test hữu ích nên kiểm tra cả kết quả client và hành vi server:

1. **Server trả kịp hạn:** client nhận response và status OK.
2. **Server xử lý lâu hơn deadline:** client nhận DEADLINE_EXCEEDED.
3. **Server cleanup:** context bị cancelled và tài nguyên/tác vụ có thể hủy được dừng.
4. **Nested call:** downstream không tiếp tục làm việc sau khi request cha hết hạn.
5. **Commit trước timeout:** retry cùng idempotency key không tạo tác dụng phụ lần hai.
6. **Streaming một phần:** client nhận một số message rồi deadline hết; trạng thái cuối được nhận diện là lỗi.

Ví dụ kiểm tra status ở client:

~~~java
var stub = PaymentServiceGrpc.newBlockingStub(channel)
    .withDeadlineAfter(50, TimeUnit.MILLISECONDS);

StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> stub.getPayment(request));

assertEquals(
    Status.Code.DEADLINE_EXCEEDED,
    error.getStatus().getCode());
~~~

Để test ổn định, dùng service giả lập chậm bằng latch hoặc controllable future thay vì phụ thuộc vào sleep dài. Test in-process xác nhận hành vi gRPC Java cơ bản; integration test Spring cần xác nhận bean service, executor, downstream channel và interceptor trong cấu hình thực tế.

## 10. Quan sát timeout trong production

Theo dõi theo service và full method name:

- Tỷ lệ **DEADLINE_EXCEEDED** trên tổng RPC.
- Latency p50, p95, p99 so với deadline được cấu hình.
- Deadline còn lại khi request vào server và trước mỗi downstream call.
- Thời gian queue, xử lý nghiệp vụ, DB và network.
- Số tác vụ còn chạy sau cancellation và thời gian cleanup.
- Tỷ lệ retry, idempotency hit và lỗi do payload/key không nhất quán.
- Với streaming: tuổi stream, số message đã nhận trước lỗi và số lần reconnect.

Trace phân tách từng service giúp tìm đúng hop làm tiêu thụ ngân sách. Log nên ghi status, method, trace ID và thời gian còn lại; không ghi credential hoặc payload nhạy cảm.

## 11. Ghi nhớ và tự kiểm tra

**DEADLINE_EXCEEDED** có nghĩa client không nhận được kết quả hoàn tất trong thời gian cho phép. Client thường thấy status này qua **StatusRuntimeException** hoặc callback **onError**. Server thường thấy **Context cancellation** và cần dừng công việc có thể hủy. Timeout không chứng minh transaction chưa commit, vì vậy command có tác dụng phụ cần idempotency và khả năng tra cứu trạng thái.

Tự kiểm tra:

1. Vì sao client có thể nhận DEADLINE_EXCEEDED dù server đã commit thao tác?
2. Server thường quan sát điều gì khi deadline client hết?
3. DEADLINE_EXCEEDED khác CANCELLED ở góc nhìn client như thế nào?
4. Vì sao không nên retry một command với idempotency key mới sau timeout?
5. Khi streaming timeout sau một số message, client cần sequence/cursor để làm gì?

Xử lý đúng DEADLINE_EXCEEDED đòi hỏi nhìn cả hai phía của RPC: client cần phân loại status và quyết định retry an toàn; server cần nhận cancellation, dừng công việc phù hợp và giải phóng tài nguyên. Kết hợp deadline propagation, idempotency và telemetry giúp dịch vụ Spring gRPC giữ được độ tin cậy khi tải hoặc độ trễ mạng thay đổi.
