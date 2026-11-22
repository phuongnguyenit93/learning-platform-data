# Deadline bắt buộc

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích deadline như ngân sách thời gian hữu hạn cho một RPC.
- Phân biệt deadline với timeout socket, retry policy và thời gian xử lý riêng của server.
- Thiết lập deadline bắt buộc ở client bằng grpc-java stub và CallOptions.
- Kiểm tra deadline tại server, từ chối call không có deadline và áp dụng giới hạn tối đa.
- Truyền phần ngân sách còn lại tới database, HTTP client và downstream gRPC.
- Xử lý cancellation, cleanup và race condition khi deadline hết.
- Thiết kế deadline cho unary và streaming RPC, kể cả stream dài cần reconnect/resume.
- Kiểm thử trường hợp thiếu deadline, deadline quá ngắn, hết hạn và retry.

## 1. Deadline là ngân sách thời gian của một RPC

Trong **SPRING_GRPC**, một RPC có thể chờ network, queue, database, service downstream và xử lý nghiệp vụ. Nếu caller không giới hạn thời gian, request bị kẹt có thể giữ thread, connection, buffer hoặc subscription lâu hơn nhu cầu thực tế.

**Deadline** xác định thời điểm cuối cùng mà caller còn chờ kết quả của một RPC. Nó là ngân sách thời gian tổng cho call, không chỉ là thời gian chờ một socket hay một bước xử lý. Khi deadline hết, gRPC hủy call và báo trạng thái phù hợp; server nên dừng công việc có thể hủy và giải phóng tài nguyên.

Deadline khác timeout tương đối ở chỗ deadline biểu diễn một thời điểm kết thúc. Client thường đặt timeout tương đối bằng phương thức **withDeadlineAfter**; grpc-java chuyển nó thành deadline nội bộ và truyền thời gian còn lại qua giao thức. Cách truyền remaining timeout giúp tránh phụ thuộc đồng hồ tuyệt đối giữa các máy.

Một deadline hữu ích phải được áp dụng xuyên suốt chuỗi xử lý:

~~~mermaid
flowchart TD
    A["Client đặt deadline hữu hạn"] --> B["gRPC gửi remaining timeout"]
    B --> C["Server kiểm tra deadline bắt buộc"]
    C --> D{"Deadline hợp lệ và còn thời gian?"}
    D -- "Không có" --> E["Từ chối call"]
    D -- "Đã hết" --> F["DEADLINE_EXCEEDED"]
    D -- "Có" --> G["Xử lý với ngân sách còn lại"]
    G --> H["Database / downstream gRPC / HTTP"]
    H --> I{"Còn ngân sách?"}
    I -- "Có" --> J["Trả response"]
    I -- "Không" --> K["Cancel, cleanup, kết thúc"]
~~~

Không có deadline, một service chậm có thể tiếp tục tiêu thụ tài nguyên dù caller đã bỏ cuộc. Deadline bắt buộc tạo một ranh giới rõ ràng cho cả client và server.

## 2. Deadline bắt buộc nghĩa là gì?

Deadline bắt buộc là contract vận hành: mọi RPC được phép xử lý phải có thời hạn hữu hạn. Quy tắc cần được thực thi ở cả hai phía:

- **Client:** mọi stub/call phải được tạo với deadline hoặc timeout phù hợp với method.
- **Server:** kiểm tra deadline nhận được; từ chối call không có deadline theo policy.
- **Server policy:** áp dụng trần thời gian tối đa để caller không thể yêu cầu một call tồn tại quá lâu.
- **Application:** truyền phần ngân sách còn lại tới database, HTTP client và downstream RPC.
- **Streaming:** quy định lifetime tối đa hoặc deadline theo phiên; stream dài cần cơ chế reconnect/resume.

Chỉ đặt default timeout trong client SDK là chưa đủ, vì client khác có thể gọi server trực tiếp. Chỉ kiểm tra ở server cũng chưa đủ, vì client chính thức vẫn có thể chờ quá lâu nếu không cấu hình deadline. Hai phía cần cùng thực thi contract.

Không dùng metadata tùy ý như x-timeout-ms để thay thế deadline của gRPC. gRPC runtime đã có cơ chế deadline riêng; client nên dùng CallOptions/stub API để thư viện truyền timeout đúng cách. Không tự tạo hoặc ghi đè header grpc-timeout.

## 3. Đặt deadline ở client bằng grpc-java

Generated stub của grpc-java hỗ trợ **withDeadlineAfter**. Đây là cách phổ biến để đặt timeout cho một call:

~~~java
import java.util.concurrent.TimeUnit;

OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel);

GetOrderResponse response = stub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(request);
~~~

800 ms chỉ là ví dụ. Chọn timeout theo latency budget của method, thời gian network, queueing và dependency. Một method đọc cache có thể cần ngân sách nhỏ; method tổng hợp nhiều service có thể cần lớn hơn. Không đặt một timeout rất dài cho mọi method để che latency bất thường.

Với async hoặc streaming stub, deadline được đặt tương tự trên stub trước khi gọi method:

~~~java
OrderServiceGrpc.OrderServiceStub asyncStub =
        OrderServiceGrpc.newStub(channel)
                .withDeadlineAfter(5, TimeUnit.SECONDS);

asyncStub.watchOrders(request, responseObserver);
~~~

Deadline của call bao trùm thời gian sống của streaming RPC. Với stream lâu dài, một deadline hữu hạn có nghĩa stream sẽ kết thúc khi ngân sách hết; thiết kế client cần biết cách mở stream mới và resume từ cursor.

### 3.1. Đặt deadline tập trung trong client factory

Trong ứng dụng lớn, không nên trông chờ mỗi developer nhớ gọi withDeadlineAfter. Có thể cung cấp factory hoặc wrapper theo method:

~~~java
public final class GrpcStubFactory {

    private final ManagedChannel channel;

    public GrpcStubFactory(ManagedChannel channel) {
        this.channel = channel;
    }

    public OrderServiceGrpc.OrderServiceBlockingStub orderStub() {
        return OrderServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS);
    }

    public ReportServiceGrpc.ReportServiceBlockingStub reportStub() {
        return ReportServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(4, TimeUnit.SECONDS);
    }
}
~~~

Đây là ví dụ đơn giản để minh họa policy theo method. Có thể dùng cấu hình tập trung, typed client hoặc interceptor/wrapper của ứng dụng để giảm việc bỏ sót. Tuy nhiên, hãy bảo đảm mọi đường tạo stub đều đi qua factory và có test cho từng nhóm RPC.

Với Spring, đăng ký channel/stub factory bằng bean theo cơ chế của starter đang dùng. Tránh tạo ManagedChannel mới cho mỗi request; channel nên được tái sử dụng theo lifecycle ứng dụng và được shutdown khi context đóng.

## 4. Server kiểm tra deadline bắt buộc

Ở server grpc-java, deadline hiện hành có thể đọc từ **Context.current().getDeadline()**. Nếu không có deadline, server có thể từ chối call ngay trong interceptor:

~~~java
import io.grpc.Context;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class RequiredDeadlineInterceptor
        implements ServerInterceptor {

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        if (Context.current().getDeadline() == null) {
            call.close(
                    Status.FAILED_PRECONDITION
                            .withDescription("A finite RPC deadline is required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

FAILED_PRECONDITION ở đây biểu diễn call không đáp ứng điều kiện vận hành của API. Một hệ thống có thể chọn status khác theo error contract, nhưng cần thống nhất và test rõ. Không trả UNAUTHENTICATED: thiếu deadline không có nghĩa credential không hợp lệ.

Interceptor phải chạy trước khi handler tạo subscription hoặc side effect. Đăng ký nó trong server interceptor chain mà Spring gRPC starter đang quản lý; kiểm thử cấu hình application thực tế để chắc chắn mọi service cần bảo vệ đều đi qua interceptor.

Deadline có thể đã hết ngay khi server nhận call. Vì vậy, ngoài kiểm tra null, cần xác minh deadline còn hiệu lực trước khi bắt đầu công việc đắt tiền.

## 5. Áp dụng maximum deadline ở server

Bắt buộc có deadline chưa đủ: caller có thể đặt một timeout rất dài. Server nên có maximum allowed duration theo method hoặc nhóm workload.

Ví dụ kiểm tra phần thời gian còn lại:

~~~java
Deadline deadline = Context.current().getDeadline();

if (deadline == null) {
    rejectMissingDeadline(call);
    return new ServerCall.Listener<ReqT>() {};
}

long remainingNanos =
        deadline.timeRemaining(TimeUnit.NANOSECONDS);

if (remainingNanos <= 0) {
    call.close(
            Status.DEADLINE_EXCEEDED
                    .withDescription("RPC deadline has expired"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}

long maxAllowedNanos =
        TimeUnit.SECONDS.toNanos(5);

if (remainingNanos > maxAllowedNanos) {
    call.close(
            Status.INVALID_ARGUMENT
                    .withDescription("Requested deadline exceeds the method limit"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}
~~~

Đây là ví dụ policy nghiêm ngặt từ chối timeout lớn hơn mức cho phép. Một lựa chọn khác là áp dụng server-side cap bằng Context deadline con và thực thi call trong Context đó. Cách triển khai phải bảo đảm listener callback vẫn chạy trong Context con và cancellation được truyền đúng. Đừng chỉ kiểm tra rồi bỏ qua deadline dài nếu mục tiêu là giới hạn thời gian thật sự.

Có thể dùng ngưỡng khác nhau:

| Nhóm RPC | Ví dụ maximum duration | Ghi chú |
| --- | ---: | --- |
| Read nhỏ | 1 giây | Phản hồi nhanh, dependency ít |
| Command ghi | 3 giây | Bao gồm transaction và downstream |
| Report tổng hợp | 8 giây | Nhiều dependency, có budget rõ |
| Streaming session | 2 phút | Reconnect/resume trước khi hết hạn |

Các con số chỉ để minh họa. Chọn theo SLO, latency distribution, retry policy và chi phí tài nguyên.

## 6. Chia ngân sách deadline cho các bước xử lý

Nếu client cấp 2 giây, server không nên dùng trọn 2 giây cho database rồi mới gọi service khác. Cần chia budget cho queueing, validation, database, downstream và serialize response.

Ví dụ budget:

| Giai đoạn | Ngân sách minh họa |
| --- | ---: |
| Network/queue và dispatch | 150 ms |
| Authentication/authorization và validation | 100 ms |
| Database | 500 ms |
| Downstream gRPC/HTTP | 700 ms |
| Mapping và trả response | 150 ms |
| Headroom | 400 ms |

Tổng ngân sách phải nằm trong deadline còn lại. Đây không phải lịch cố định; các bước có thể chạy song song hoặc dùng ít thời gian hơn. Mục đích là tránh một dependency tiêu thụ toàn bộ thời gian của call.

Trước mỗi thao tác đắt tiền, kiểm tra thời gian còn lại. Nếu ngân sách không đủ để bắt đầu operation có ích, dừng sớm thay vì tạo thêm công việc chắc chắn không hoàn thành.

Không trừ thời gian bằng đồng hồ wall-clock tự viết để quyết định deadline. Dùng **Deadline.timeRemaining(...)** hoặc API timeout của dependency; grpc-java Deadline được thiết kế để đo thời gian còn lại an toàn với thay đổi đồng hồ hệ thống.

## 7. Truyền deadline tới downstream gRPC

Một server thường gọi tiếp các service khác. Deadline của inbound call phải giới hạn tổng thời gian của cả chuỗi, không để downstream chạy lâu hơn caller đang chờ.

Đọc deadline hiện tại:

~~~java
Deadline inboundDeadline = Context.current().getDeadline();

if (inboundDeadline == null) {
    throw Status.FAILED_PRECONDITION
            .withDescription("A finite RPC deadline is required")
            .asRuntimeException();
}
~~~

Khi tạo outbound stub, truyền cùng deadline hoặc một deadline con ngắn hơn nếu cần giữ thời gian cho mapping/response:

~~~java
long remainingNanos =
        inboundDeadline.timeRemaining(TimeUnit.NANOSECONDS);

long reserveNanos = TimeUnit.MILLISECONDS.toNanos(100);
long downstreamBudget = remainingNanos - reserveNanos;

if (downstreamBudget <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("No time budget remains for downstream call")
            .asRuntimeException();
}

InventoryServiceGrpc.InventoryServiceBlockingStub downstream =
        inventoryStub.withDeadlineAfter(
                downstreamBudget,
                TimeUnit.NANOSECONDS);
~~~

Ví dụ giữ lại 100 ms cho phần xử lý còn lại. Trong hệ thống có nhiều dependency, chia budget theo critical path và mức song song. Không cấp cho từng downstream cùng toàn bộ remaining time nếu các call nối tiếp nhau; tổng thời gian có thể vượt deadline của inbound operation.

Một số framework/runtime có cơ chế propagation deadline qua Context. Dù vậy, hãy xác minh behavior của phiên bản và cách tạo stub trong ứng dụng. Đặt deadline tường minh cho outbound call giúp contract rõ ràng và tránh vô tình gọi downstream không timeout.

## 8. Database và HTTP client cũng cần timeout tương ứng

Deadline gRPC không tự động cấu hình timeout cho JDBC, JPA, HTTP client hoặc message broker. Nếu server thread gọi một database query không có timeout, RPC có thể bị cancel nhưng query vẫn tiếp tục chạy.

Ánh xạ remaining budget sang timeout của dependency:

- JDBC statement/query timeout.
- Transaction timeout của framework.
- HTTP connect timeout và response/read timeout.
- Timeout của Redis, broker hoặc object storage client.
- Timeout của lock acquisition và semaphore wait.

Một số API nhận timeout theo millisecond hoặc second nguyên, trong khi gRPC Deadline có độ chính xác cao hơn. Làm tròn cẩn thận và không đặt timeout dependency dài hơn thời gian còn lại. Dành headroom cho cleanup và response.

Nếu thư viện không hỗ trợ cancellation hoặc timeout thực sự, cần hiểu giới hạn đó. Gửi interrupt hoặc cancel future không bảo đảm database/server bên ngoài đã dừng xử lý. Theo dõi query đang chạy và dùng cơ chế cancel của driver khi có thể.

## 9. Deadline và cancellation phải đi cùng nhau

Khi deadline hết, gRPC call bị cancel. Server nên quan sát cancellation và dừng tác vụ có thể hủy:

~~~java
Context context = Context.current();

context.addListener(
        cancelledContext -> {
            cancelDatabaseQuery();
            cancelDownstreamFuture();
            closeSubscription();
        },
        cleanupExecutor);
~~~

Listener cần được đăng ký trong Context của RPC. Cleanup phải idempotent vì cancellation có thể xảy ra gần lúc handler hoàn tất hoặc dependency trả lỗi. Không chạy cleanup chậm trên transport event loop; dùng executor phù hợp và giới hạn queue.

Với streaming, cancellation cần dừng producer và subscription, giải phóng buffer và concurrency permit. Không tiếp tục đọc broker hoặc database chỉ để bỏ response vì client đã ngắt stream.

Deadline không rollback transaction đã commit. Nếu operation đã tạo side effect trước khi hết thời gian, client có thể nhận DEADLINE_EXCEEDED mà không biết server đã commit hay chưa. Với command có side effect, cần idempotency key, operation status hoặc reconciliation để client truy vấn kết quả.

## 10. Deadline cho streaming RPC

Streaming call có deadline bao trùm toàn bộ vòng đời stream, không reset sau mỗi message. Nếu client đặt deadline 30 giây, stream kết thúc khi ngân sách 30 giây hết dù message cuối vừa được gửi.

Đối với stream ngắn như upload một batch, deadline tổng là phù hợp. Đối với subscription dài, không nên tạo stream vô hạn không deadline. Dùng maximum lifetime hữu hạn, sau đó client reconnect và resume bằng cursor/sequence.

Thiết kế reconnect cần:

1. Server trả cursor hoặc sequence đã xác nhận.
2. Client lưu checkpoint an toàn.
3. Khi deadline hết, client mở stream mới với deadline mới.
4. Server xác thực lại credential và authorization.
5. Client resume từ checkpoint; server deduplicate nếu có thể phát lại message.
6. Subscription cũ được cleanup trước hoặc ngay khi stream kết thúc.

Không dùng heartbeat để kéo dài deadline vô hạn. Heartbeat chỉ giúp phát hiện peer/connection; nó không thay thế maximum stream lifetime và resource policy.

## 11. Retry không được tạo deadline mới vô hạn

Retry là một phần của cùng operation và cần nằm trong ngân sách thời gian tổng. Nếu mỗi lần retry được cấp timeout đầy đủ mới, tổng thời gian có thể vượt quá kỳ vọng của caller.

Ví dụ caller có 2 giây. Attempt đầu dùng 700 ms, backoff 100 ms, attempt hai chỉ còn khoảng 1,2 giây trừ headroom. Không đặt lại 2 giây cho mỗi attempt.

Các nguyên tắc:

- Retry policy phải tôn trọng deadline còn lại.
- Backoff có giới hạn và jitter.
- Không retry INVALID_ARGUMENT, PERMISSION_DENIED hoặc call bị từ chối vì thiếu deadline.
- Với DEADLINE_EXCEEDED, chỉ retry nếu còn budget và operation an toàn.
- Mutation cần idempotency key hoặc deduplication.
- Không dùng wait-for-ready để chờ vô hạn; nó vẫn phải nằm trong deadline.
- Không khởi chạy retry mới nếu remaining budget không đủ cho một attempt hữu ích.

Nếu server đã commit nhưng response không đến kịp, retry có thể tạo side effect trùng. Client cần operation ID hoặc idempotency key để truy vấn/tránh thực hiện lại.

## 12. Chọn status cho deadline và lỗi liên quan

| Tình huống | Status gợi ý | Ý nghĩa |
| --- | --- | --- |
| Client không gửi deadline theo contract bắt buộc | FAILED_PRECONDITION | Call thiếu điều kiện vận hành |
| Deadline đã hết trước khi xử lý | DEADLINE_EXCEEDED | Ngân sách thời gian không còn |
| Deadline yêu cầu vượt maximum policy | INVALID_ARGUMENT hoặc status contract riêng | Tham số thời gian không hợp lệ |
| Dependency hết timeout trong khi inbound deadline còn | Map theo lỗi dependency và ngân sách còn lại | Phân biệt lỗi downstream với deadline tổng |
| Client chủ động hủy | CANCELLED | Caller không còn cần kết quả |
| Dependency không sẵn sàng nhưng còn thời gian | UNAVAILABLE | Lỗi hạ tầng, retry có điều kiện |

Client có thể quan sát DEADLINE_EXCEEDED ngay cả khi server đã hoàn thành side effect nhưng response bị trễ hoặc thất lạc. Không coi status này là bằng chứng transaction đã rollback.

Không nhầm thiếu deadline với UNAUTHENTICATED hoặc PERMISSION_DENIED. Authentication và authorization là quyết định bảo mật; deadline là điều kiện thời gian của call.

## 13. Quan sát deadline trong production

Theo dõi theo method và loại RPC:

- Tỷ lệ call thiếu deadline bị từ chối.
- Remaining time tại thời điểm server nhận call.
- Latency p50/p95/p99 và tỷ lệ DEADLINE_EXCEEDED.
- Thời gian xử lý theo từng dependency.
- Số downstream call bị cancel khi inbound deadline hết.
- Stream lifetime, reconnect/resume và cancellation.
- Retry count, backoff time và số attempt bị bỏ vì không còn budget.
- Query/task vẫn chạy sau khi RPC đã kết thúc.

Không đưa deadline tuyệt đối hoặc request ID cardinality cao vào metric label. Ghi remaining budget theo bucket và trace span để tìm bước tiêu thụ thời gian. Không log token hoặc payload nhạy cảm.

Nếu tỷ lệ deadline hết tăng, phân tách queue delay, application processing, downstream latency và network. Tăng timeout một cách máy móc có thể chỉ làm request giữ tài nguyên lâu hơn và tăng số call đồng thời.

## 14. Kiểm thử deadline bắt buộc

Cần test cả client contract lẫn server enforcement:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Client đặt deadline hợp lệ | RPC được xử lý trong budget |
| Client không đặt deadline | Server từ chối trước khi handler chạy |
| Deadline đã hết | DEADLINE_EXCEEDED hoặc cancellation phù hợp |
| Deadline vượt maximum policy | Bị từ chối hoặc cap theo policy |
| Downstream chậm | Outbound call bị giới hạn bởi remaining budget |
| Database query chậm | Query timeout/cancel theo budget |
| Client cancel | Server dừng công việc và cleanup |
| Streaming deadline hết | Stream kết thúc, subscription/permit được giải phóng |
| Retry nhiều attempt | Tổng thời gian không vượt deadline của operation |
| Mutation response bị timeout | Idempotency/status query tránh side effect trùng |

Một test quan trọng là gửi call không có deadline qua raw generated stub, không dùng factory chính thức. Điều đó chứng minh server interceptor bảo vệ cả client không tuân thủ SDK. Test khác đặt deadline rất ngắn và dùng latch để giữ handler; xác minh cancellation được quan sát và cleanup chạy.

Trong Spring application integration test, khởi động server theo cấu hình starter thật, xác minh interceptor bắt buộc được đăng ký cho mọi service cần bảo vệ. In-process test tự dựng interceptor chain không chứng minh bean wiring production đã đúng.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đặt timeout trong client SDK | Client khác có thể gọi không deadline | Server kiểm tra deadline bắt buộc |
| Chỉ kiểm tra deadline khác null | Caller có thể yêu cầu thời gian quá dài | Áp dụng maximum duration |
| Tạo timeout mới cho mỗi retry | Tổng operation kéo dài vô hạn | Dùng chung deadline budget |
| Không truyền budget xuống database/HTTP | Dependency vẫn chạy sau khi RPC hết hạn | Ánh xạ remaining time sang timeout/cancel |
| Coi DEADLINE_EXCEEDED là rollback | Retry tạo side effect trùng | Idempotency key và operation status |
| Dùng heartbeat để giữ stream vô hạn | Giữ subscription và permit mãi | Maximum lifetime và resume cursor |
| Cleanup trên event loop | Chặn transport khi cleanup chậm | Dùng cleanup executor có giới hạn |
| Chỉ test qua client factory | Bỏ sót caller không tuân thủ contract | Raw-stub integration test |
| Cấu hình interceptor ở test nhưng quên Spring | Production không enforce | Spring application integration test |

## 16. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo client stub factory với deadline riêng cho GetOrder, CancelOrder và GenerateReport.
2. Viết server interceptor từ chối RPC không có deadline và kiểm tra maximum duration.
3. Đăng ký interceptor qua cấu hình Spring gRPC đang dùng.
4. Trong application service, truyền remaining budget tới downstream gRPC và HTTP/database client.
5. Thêm cancellation listener để dừng future, query hoặc subscription.
6. Với server-streaming, đặt maximum lifetime và triển khai resume cursor khi deadline hết.
7. Định nghĩa retry budget tổng, backoff và idempotency cho command có side effect.
8. Viết integration test cho missing deadline, expired deadline, overlong deadline, slow dependency, cancel và retry.

### Câu hỏi tự kiểm tra

**1. Deadline khác timeout thế nào?**  
Deadline là thời điểm kết thúc; timeout là khoảng thời gian tương đối dùng để tính deadline.

**2. Vì sao cần bắt buộc deadline ở server?**  
Vì client SDK có thể bị bỏ qua; server cần bảo vệ tài nguyên trước caller không gửi timeout.

**3. Vì sao kiểm tra deadline khác null chưa đủ?**  
Caller có thể gửi deadline quá dài; server cần maximum duration theo method.

**4. Deadline có tự dừng JDBC hoặc HTTP request không?**  
Không. Application phải truyền remaining budget sang timeout/cancellation API của dependency.

**5. Retry có được cấp lại toàn bộ timeout ban đầu không?**  
Không. Các attempt phải chia sẻ deadline budget tổng của operation.

**6. Deadline hết có bảo đảm transaction rollback không?**  
Không. Side effect có thể đã commit; cần idempotency và cơ chế tra cứu trạng thái.

**7. Streaming dài xử lý deadline thế nào?**  
Dùng lifetime hữu hạn, cursor/sequence và reconnect/resume thay vì stream vô hạn.

**8. Status nào dùng khi client thiếu deadline bắt buộc?**  
Theo contract; ví dụ bài này dùng FAILED_PRECONDITION để biểu thị thiếu điều kiện vận hành.

## Tổng kết

**Deadline bắt buộc** nghĩa là mọi RPC phải có ngân sách thời gian hữu hạn, được client thiết lập và server thực thi. Client dùng grpc-java stub/CallOptions để đặt deadline; server kiểm tra Context.current().getDeadline(), từ chối call thiếu deadline và áp dụng maximum duration. Phần thời gian còn lại phải được truyền tới database, HTTP và downstream gRPC; cancellation cần dừng công việc và cleanup tài nguyên. Retry phải dùng chung ngân sách tổng, còn streaming dài cần maximum lifetime cùng cursor/resume. Kiểm thử raw client không deadline, deadline hết, dependency chậm và Spring wiring để chứng minh policy được enforce trên server thực tế.

