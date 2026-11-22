# Coi gRPC là gọi hàm cục bộ và bỏ qua deadline

## 1. Vì sao đây là một lỗi thiết kế?

Trong **SPRING_GRPC**, một lời gọi gRPC nhìn giống lời gọi method Java: client gọi stub, server chạy implementation rồi trả response. Nhưng RPC đi qua ranh giới process và network. Giữa hai phía còn có serialization Protobuf, HTTP/2, TLS, load balancing, queue của server, network latency và các điểm có thể lỗi.

Một method Java cục bộ thường trả kết quả hoặc ném exception trong cùng process. Một RPC có thể:

- Không kết nối được server hoặc bị ngắt giữa chừng.
- Chờ trong queue hoặc chờ database lâu hơn dự kiến.
- Bị deadline hết trong khi server vẫn đang xử lý.
- Đã commit side effect nhưng response bị mất trên đường về.
- Bị retry ở client hoặc proxy, khiến cùng một command đến server nhiều lần.

Nếu coi RPC là gọi hàm cục bộ, code thường bỏ qua deadline, retry tùy tiện và không xác định rõ trạng thái khi timeout. Hệ quả là thread và connection bị giữ lâu, request cũ tiếp tục tiêu thụ tài nguyên, hoặc một command tạo side effect nhiều lần.

**Deadline là giới hạn thời gian đầu cuối của một RPC.** Client và server cần dùng deadline để giới hạn công việc, truyền ngân sách xuống dependency và dừng xử lý khi kết quả không còn hữu ích.

## 2. Gọi method cục bộ và gọi RPC có semantics khác nhau

| Gọi method trong process | Gọi gRPC qua network |
| --- | --- |
| Không cần serialize qua wire | Request/response được mã hóa theo Protobuf |
| Không phụ thuộc DNS, TLS hoặc network route | Có thể lỗi kết nối, handshake, proxy hoặc network |
| Thường chia sẻ heap và process lifecycle | Client và server có lifecycle độc lập |
| Exception truyền trực tiếp trong call stack | Lỗi được biểu diễn bằng gRPC status/trailers |
| Thời gian chờ thường do code kiểm soát | Có queueing, network latency và deadline |
| Không có ambiguity do response bị mất trên network | Server có thể commit nhưng client không nhận response |
| Retry thường là quyết định của code gọi | Retry có thể xuất hiện ở client, gRPC policy hoặc tầng trung gian |

Stub gRPC là client proxy, không phải object server nằm trong cùng JVM. Không giữ lock hoặc transaction database trong lúc gọi RPC từ xa như thể đó là một method nhanh, đáng tin cậy.

Một RPC có thể chậm dù server xử lý nhanh: thời gian tổng còn bao gồm chờ kết nối, queueing, network hai chiều và xử lý ở các dependency.

## 3. Đặt deadline ở client

Client nên đặt deadline cho mọi RPC có thời gian hoàn tất dự kiến. Với blocking stub:

```java
OrderReply reply = blockingStub
    .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

Ví dụ 800 ms chỉ minh họa. Chọn deadline theo SLO, latency p95/p99, độ phức tạp operation và thời gian caller còn có thể chờ.

Các nguyên tắc:

- Không dựa vào deadline mặc định vô hạn.
- Chọn deadline riêng theo loại RPC; query đơn giản và command phức tạp có thể có ngân sách khác nhau.
- Deadline phải bao gồm thời gian kết nối, queueing, server work và response.
- Nếu caller đã có deadline, dependency call phải dùng phần ngân sách còn lại, không khởi tạo một timeout đầy đủ mới.
- Tránh đặt deadline quá ngắn khiến request hợp lệ thường xuyên thất bại và retry làm tải tăng thêm.

Với stub bất đồng bộ, deadline cũng được đặt trên stub trước khi gọi method. Deadline là thuộc tính của lời gọi, không phải timeout của toàn bộ channel.

## 4. Timeout tương đối và deadline tuyệt đối

Timeout thường diễn tả một khoảng thời gian tính từ lúc bắt đầu một thao tác. Deadline diễn tả thời điểm tuyệt đối mà thao tác phải kết thúc.

Giả sử client có ngân sách tổng 1 giây:

- RPC tới service A tiêu thụ 300 ms.
- Service A gọi service B.
- Nếu A đặt timeout mới 1 giây cho B, tổng thời gian có thể vượt 1 giây.
- Nếu A truyền deadline ban đầu, B chỉ còn khoảng 700 ms, trừ overhead tiếp tục phát sinh.

Đặt lại timeout đầy đủ ở mỗi hop làm ngân sách cộng dồn và phá vỡ giới hạn đầu cuối. Hãy truyền deadline gốc hoặc tính remaining budget rồi áp dụng giới hạn nhỏ hơn theo policy của service.

## 5. Đọc và truyền deadline trong server

Trong gRPC Java, server có thể đọc deadline hiện tại từ Context:

```java
Deadline deadline = Context.current().getDeadline();

if (deadline == null) {
    // Client không gửi deadline: áp dụng service-level cap.
} else {
    long remainingMs =
        deadline.timeRemaining(TimeUnit.MILLISECONDS);

    if (remainingMs <= 0) {
        throw Status.DEADLINE_EXCEEDED
            .withDescription("Request deadline has expired")
            .asRuntimeException();
    }
}
```

Nếu gọi downstream gRPC, dùng deadline hiện tại thay vì cấp lại toàn bộ ngân sách:

```java
Deadline parentDeadline = Context.current().getDeadline();

OrderReply reply;
if (parentDeadline != null) {
    reply = orderBlockingStub
        .withDeadline(parentDeadline)
        .getOrder(downstreamRequest);
} else {
    reply = orderBlockingStub
        .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
        .getOrder(downstreamRequest);
}
```

Ví dụ giả định stub và request đã được cấu hình. Khi deadline cha không tồn tại, service vẫn nên áp dụng một service-level cap hữu hạn. Khi có deadline cha, có thể chọn deadline sớm hơn nếu service có giới hạn nội bộ thấp hơn.

Nếu công việc được chuyển sang executor tùy ý, không giả định gRPC Context tự xuất hiện trên thread mới. Hãy capture/propagate Context bằng cơ chế của gRPC Java hoặc truyền deadline rõ ràng qua application command. Với tác vụ nền tách khỏi vòng đời RPC, cần một policy deadline riêng thay vì giữ Context đã hết hạn.

## 6. Chia ngân sách cho các dependency

Một RPC có thể thực hiện nhiều bước: đọc database, gọi inventory service, gọi payment service và ghi kết quả. Mỗi bước phải tiêu thụ cùng một ngân sách đầu cuối.

Ví dụ một request còn 900 ms:

| Bước | Ngân sách minh họa |
| --- | ---: |
| Validate và application logic | 50 ms |
| Chờ connection pool | 100 ms |
| Database query và commit | 200 ms |
| Downstream RPC | 350 ms |
| Mapping response và dự phòng | 100 ms |
| Phần còn lại cho biến động | 100 ms |

Đây là cách phân bổ minh họa, không phải cấu hình chuẩn. Đo latency thực tế để chọn budget.

Trước mỗi dependency call:

1. Đọc remaining deadline.
2. Trừ phần dự phòng cần cho các bước sau.
3. Áp dụng service cap nếu dependency có giới hạn riêng.
4. Không bắt đầu công việc nếu ngân sách còn lại không đủ.
5. Ghi nhận dependency nào tiêu thụ thời gian.

Đừng cấp cho từng dependency cùng một timeout bằng deadline ban đầu. Nếu mỗi bước đều được phép chờ 1 giây, một request có thể kéo dài nhiều giây.

## 7. Deadline hết không đồng nghĩa server tự dừng mọi công việc

Khi deadline hết, gRPC đánh dấu call bị hết hạn và server Context bị cancel. Nhưng điều này không tự động dừng mọi đoạn code Java.

Các hoạt động có thể tiếp tục nếu không hỗ trợ cancellation:

- Vòng lặp CPU không kiểm tra cancellation.
- JDBC query mà driver/database chưa nhận hoặc chưa xử lý cancel.
- HTTP call hoặc RPC downstream không có deadline riêng.
- Future chạy trong executor không được cancel.
- Công việc đã được đưa vào queue nhưng không kiểm tra call còn hợp lệ.

Vì vậy, cancellation cần được xử lý hợp tác. Kiểm tra Context trước khi bắt đầu bước tốn tài nguyên; truyền deadline xuống dependency; đặt query/statement timeout; và hủy task nếu API hỗ trợ.

Với JDBC, gRPC cancellation không đảm bảo Statement tự dừng ngay. Dùng query timeout hoặc database-side statement timeout và kiểm thử driver thực tế. Không giả định hủy RPC sẽ rollback một transaction đã commit.

## 8. Kiểm tra cancellation trong server

Với unary RPC, có thể kiểm tra trạng thái Context ở các điểm an toàn:

```java
if (Context.current().isCancelled()) {
    throw Status.CANCELLED
        .withDescription("Call was cancelled")
        .asRuntimeException();
}

return applicationService.execute(command);
```

Với streaming RPC, server có thể dùng ServerCallStreamObserver để nhận thông báo client hủy:

```java
if (observer instanceof ServerCallStreamObserver<?> serverObserver) {
    serverObserver.setOnCancelHandler(() -> {
        cancellationSignal.cancel();
    });
}
```

Ví dụ dùng cancellationSignal là cơ chế do ứng dụng quản lý để báo cho producer/worker dừng. Handler cần ngắn gọn; không thực hiện cleanup blocking hoặc database work dài ngay trong callback cancellation.

Không phát thêm message sau khi stream đã bị cancel hoặc đã gửi terminal signal. Nếu công việc đã commit trước khi cancellation tới, giữ nguyên dữ liệu đã commit và cung cấp idempotency/status query nếu caller cần xác định kết quả.

## 9. Phân biệt deadline, timeout nội bộ và cancellation

| Tình huống | gRPC status thường gặp | Ý nghĩa |
| --- | --- | --- |
| Client deadline hết trước khi nhận kết quả | DEADLINE_EXCEEDED | Caller đã hết ngân sách chờ |
| Client chủ động hủy RPC | CANCELLED | Caller không muốn tiếp tục chờ |
| Database query vượt query timeout | Có thể ánh xạ DEADLINE_EXCEEDED hoặc status theo contract | Timeout nội bộ của dependency |
| Downstream tạm không sẵn sàng | UNAVAILABLE | Dependency không thể phục vụ tạm thời |
| Transaction gặp optimistic conflict | ABORTED | Cần đọc lại và retry workflow |
| Request sai | INVALID_ARGUMENT | Caller phải sửa input |

Status không mô tả đầy đủ commit state. Client nhận DEADLINE_EXCEEDED không thể kết luận server chưa thực hiện command. Nếu database commit trước khi response bị mất, side effect vẫn tồn tại.

Không biến mọi timeout thành UNAVAILABLE. Phân loại theo nguyên nhân và contract giúp client quyết định có nên retry, chờ hay sửa request.

## 10. Retry phải nằm trong deadline tổng và có semantics an toàn

Retry có thể hữu ích với lỗi transient, nhưng mỗi attempt tiêu thụ thêm thời gian và tài nguyên. Retry policy phải giới hạn attempt, dùng backoff có jitter và dừng khi remaining deadline không đủ.

Nguyên tắc:

- Chỉ retry status được contract xác định là retryable.
- Giữ nguyên idempotency key cho cùng một command.
- Không retry INVALID_ARGUMENT hoặc lỗi nghiệp vụ không thể tự phục hồi.
- Với ABORTED, đọc lại dữ liệu và chạy lại toàn bộ use case trong transaction mới.
- Với UNAVAILABLE hoặc DEADLINE_EXCEEDED, outcome có thể chưa rõ; command có side effect cần idempotency.
- Không retry ở client, server, proxy và worker cùng lúc mà không tính tổng số attempt.
- Không dùng retry để che giấu database hoặc dependency đang quá tải.

Ví dụ backoff:

```text
delay = min(max_delay, base_delay × 2^(attempt - 1))
wait  = delay + random_jitter
```

Trước khi ngủ hoặc bắt đầu attempt mới, kiểm tra remaining deadline. Không tạo deadline mới đầy đủ cho mỗi lần retry.

## 11. Idempotency bảo vệ command khi response bị mất

Với command như CreateOrder hoặc CapturePayment, client cần gửi một idempotency key ổn định cho một ý định nghiệp vụ.

Server lưu key, request fingerprint và kết quả cùng transaction với business update. Database unique constraint bảo vệ khi hai attempt cùng key tới đồng thời.

Khi retry:

- Cùng key và cùng fingerprint, server trả lại kết quả đã lưu.
- Cùng key nhưng payload khác, server từ chối.
- Attempt đầu rollback, attempt sau có thể thực thi.
- Attempt đầu commit nhưng response mất, attempt sau replay kết quả và không tạo side effect mới.

Nếu command cần phát event, ghi outbox trong cùng transaction. Không gọi payment provider hoặc broker rồi giả định database rollback sẽ hoàn tác side effect bên ngoài; dùng downstream idempotency key, outbox hoặc saga/compensation.

## 12. Đừng giữ transaction khi chờ RPC từ xa

Một lỗi liên quan là mở transaction database, đọc/khóa row rồi gọi downstream gRPC trước khi commit. Nếu downstream chậm, transaction giữ connection và lock trong suốt thời gian network call.

Hệ quả:

- Connection pool nhanh cạn dưới tải.
- Lock contention và deadlock tăng.
- Deadline downstream có thể hết trong khi transaction vẫn giữ tài nguyên.
- Retry có thể lặp lại cả network call và database update.

Thiết kế nên tách các bước:

1. Đọc/ghi dữ liệu cần thiết trong transaction ngắn.
2. Ghi outbox intent nếu cần phát event hoặc gọi tác vụ bất đồng bộ.
3. Commit và trả connection.
4. Dispatcher/worker gọi downstream ngoài transaction.
5. Dùng idempotency và state machine để xử lý retry/recovery.

Nếu nghiệp vụ bắt buộc gọi đồng bộ downstream trước khi hoàn tất, xác định rõ consistency và compensation. Giữ transaction mở trong lúc chờ network chỉ nên là quyết định có chủ đích sau khi đánh giá tải và failure mode.

## 13. Quan sát deadline end-to-end

Đừng chỉ đo tổng RPC latency. Thu thập:

- Deadline/remaining budget khi server nhận call.
- Thời gian queueing và application processing.
- Pool acquisition, query, lock wait và transaction duration.
- Latency của từng downstream RPC.
- Số lần deadline hết, client cancel và query timeout.
- Số request tiếp tục chạy sau khi caller đã cancel.
- Retry count, backoff time và status cuối.

Trace nên thể hiện từng dependency span để xác định thời gian bị tiêu thụ ở đâu. Tránh đưa request ID hoặc user ID có cardinality cao vào metric labels; dùng trace/log correlation để điều tra từng call.

Nếu RPC thường hết deadline ở downstream, tăng deadline không nhất thiết giải quyết vấn đề. Trước hết xác định bottleneck là queue, network, database, lock hay dependency latency.

## 14. Kiểm thử deadline và cancellation

Cần integration test qua gRPC server thật:

| Test | Điều cần xác nhận |
| --- | --- |
| Client đặt deadline ngắn | Client nhận DEADLINE_EXCEEDED |
| Server nhận request không có deadline | Service-level cap vẫn giới hạn xử lý |
| Downstream RPC chậm | Downstream dùng deadline cha/remaining budget |
| Database query chậm | Query timeout giới hạn thời gian và transaction xử lý đúng |
| Client chủ động cancel | Server nhận cancellation và dừng công việc có thể hủy |
| Executor task | Context/deadline được truyền rõ ràng |
| Commit rồi mất response | Retry cùng key replay kết quả, không duplicate |
| Nhiều downstream hop | Tổng thời gian không reset timeout ở từng hop |
| RPC hết deadline khi đang stream | Không gửi tiếp message sau cancellation |

Không chỉ test bằng sleep và assert thời gian gần đúng. Dùng controllable latch/fake downstream để tạo điểm chờ xác định, rồi xác nhận Context cancellation, query state và database state. Một số driver hủy query khác nhau; test với driver/database gần production.

## 15. Checklist review

- Mọi RPC quan trọng có deadline hữu hạn theo SLO.
- Không coi stub như method Java cục bộ hoặc tin rằng network luôn sẵn sàng.
- Deadline đầu cuối được truyền xuống downstream; không reset full timeout ở mỗi hop.
- Server đọc remaining deadline và có service-level cap khi client không gửi.
- Công việc async truyền Context/deadline rõ ràng.
- Pool/query/transaction timeout phù hợp phần ngân sách còn lại.
- Cancellation được kiểm tra ở các điểm an toàn.
- JDBC/HTTP/downstream call có cơ chế timeout/cancel riêng.
- Không giữ database transaction/lock trong lúc chờ network.
- DEADLINE_EXCEEDED không bị hiểu là transaction chắc chắn rollback.
- Retry có giới hạn, backoff/jitter và deadline tổng.
- Command có side effect dùng idempotency key; external event dùng outbox.
- Metrics/traces phân rã latency theo từng dependency.
- Có integration tests cho deadline, cancellation, downstream propagation và lost response.

Trong **SPRING_GRPC**, RPC là một lời gọi qua ranh giới process nên có latency, lỗi network và outcome không chắc chắn. Đặt deadline hữu hạn ở client, giữ cùng ngân sách qua các downstream hop, và làm cho database/query có timeout phù hợp. Khi deadline hết, dừng công việc có thể hủy; với command có side effect, dùng idempotency để xử lý trường hợp server đã commit nhưng client không nhận response.
