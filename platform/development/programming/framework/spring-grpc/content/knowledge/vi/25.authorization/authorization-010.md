# Quyền cho streaming RPC

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao authorization của streaming RPC cần xét cả thời điểm mở stream và quá trình trao đổi message.
- Phân biệt quyền gọi method với quyền truy cập từng resource được tham chiếu trong stream.
- Áp dụng policy phù hợp cho server-streaming, client-streaming và bidirectional streaming.
- Giữ principal, tenant và quyền đã xác minh trong phạm vi của một stream.
- Xử lý token expiry, thu hồi quyền, revalidation, cancellation và cleanup.
- Kết hợp authorization với flow control, backpressure và giới hạn tài nguyên.
- Chọn cách kết thúc stream bằng gRPC status hoặc trả kết quả từ chối ở cấp message theo contract.
- Kiểm thử để chứng minh stream không phát hoặc xử lý dữ liệu ngoài phạm vi được phép.

## 1. Vì sao streaming cần cách kiểm tra quyền riêng?

Trong **SPRING_GRPC**, gRPC hỗ trợ unary RPC và ba dạng streaming: server-streaming, client-streaming và bidirectional streaming. Unary thường có một request và một response; streaming giữ một RPC mở trong khi nhiều message được gửi theo một hoặc hai chiều.

Với unary, server thường có thể xác định method, principal và resource cần kiểm tra trước khi thực hiện use case. Với streaming, quyết định ở thời điểm mở call có thể chỉ cho biết caller được gọi method. Những message đến sau có thể tham chiếu resource khác, tenant khác hoặc yêu cầu hành động có mức nhạy cảm khác nhau.

Ví dụ, caller có quyền gọi **OrderService/WatchOrders**. Quyền đó không tự động cho phép caller theo dõi mọi đơn hàng của mọi tenant. Tương tự, caller được mở **EventService/UploadEvents** không có nghĩa mọi event gửi về sau đều hợp lệ hoặc thuộc phạm vi của caller.

Một thiết kế an toàn phân biệt hai lớp:

- **Method authorization khi mở stream:** caller có được phép bắt đầu RPC này không?
- **Message/resource authorization trong stream:** caller có được phép xử lý resource hoặc hành động mà message hiện tại yêu cầu không?

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant I as Server interceptor
    participant S as Streaming service
    participant P as Resource policy
    participant D as Data / downstream
    C->>I: Open stream + credentials
    I->>I: Authenticate principal
    I->>I: Check permission for service/method
    alt Method denied
        I-->>C: PERMISSION_DENIED
    else Method allowed
        I->>S: Start stream with principal Context
        loop Each inbound message / resource
            C->>S: Message
            S->>P: Check tenant, resource and action
            alt Resource allowed
                P-->>S: Allow
                S->>D: Process / publish authorized data
                D-->>S: Result
                S-->>C: Response message (if applicable)
            else Resource denied
                P-->>S: Deny
                S-->>C: End stream or item-level rejection
            end
        end
    end
~~~

Không phải mọi stream đều cần gọi policy engine cho từng message. Nếu stream gắn với một resource cố định, có thể kiểm tra resource khi mở stream rồi ràng buộc toàn bộ subscription với resource đó. Nếu message thay đổi resource hoặc action, cần kiểm tra tương ứng trước khi xử lý message.

## 2. Ba dạng streaming và vị trí authorization

| Dạng RPC | Luồng message | Kiểm tra khi mở | Kiểm tra trong stream |
| --- | --- | --- | --- |
| **Server-streaming** | Một request, nhiều response | Quyền gọi method và quyền subscribe resource/filter | Kiểm tra từng resource/event được phát nếu phạm vi có thể thay đổi |
| **Client-streaming** | Nhiều request, một response cuối | Quyền gọi method và quyền bắt đầu operation | Kiểm tra mỗi message trước khi ghi hoặc tạo side effect |
| **Bidirectional streaming** | Nhiều request và response hai chiều | Quyền gọi method và quyền mở session | Kiểm tra từng command/resource; chỉ trả response sau khi request được authorize |

### 2.1. Server-streaming

Ví dụ **WatchOrder** nhận một order ID rồi phát nhiều trạng thái của đơn đó. Server cần:

1. Xác thực principal và permission **orders:watch**.
2. Tải order bằng tenant-scoped query.
3. Kiểm tra caller được xem order đó.
4. Tạo subscription chỉ cho đúng order và tenant đã xác minh.
5. Khi phát event, bảo đảm event thuộc subscription đã được authorize.
6. Hủy subscription khi client cancel, quyền bị thu hồi hoặc resource không còn trong phạm vi.

Nếu request chứa filter cho nhiều order hoặc nhiều tenant, filter đó là input không tin cậy. Server phải kiểm tra từng phạm vi được yêu cầu và giới hạn kết quả ngay tại nguồn dữ liệu. Không lấy toàn bộ event rồi lọc ở client; dữ liệu không được phép đã rời khỏi server.

### 2.2. Client-streaming

Ví dụ **UploadEvents** nhận nhiều event trong cùng một RPC. Method permission **events:write** cho phép caller bắt đầu upload, nhưng mỗi message có thể chứa tenant ID, aggregate ID hoặc loại event khác nhau.

Trước khi xử lý từng message, server cần xác minh tenant, quyền trên aggregate/resource, schema và các invariant nghiệp vụ. Chỉ sau đó mới ghi event hoặc tạo side effect. Một message bị từ chối có thể làm kết thúc cả stream; nếu contract cho phép tiếp tục và trả lỗi từng item, response schema phải thể hiện rõ item nào được chấp nhận/từ chối.

### 2.3. Bidirectional streaming

Bidirectional stream thường được dùng cho command/response liên tục, đồng bộ trạng thái hoặc trao đổi sự kiện. Mỗi request message có thể yêu cầu hành động khác nhau và response có thể chứa dữ liệu nhạy cảm.

Server phải authorize từng command trước khi thực hiện và kiểm tra quyền đọc trước khi phát response tương ứng. Không suy ra rằng caller đã được phép với message đầu tiên thì mọi command sau đó đều được phép. Nếu stream có session state, state phải gắn với principal/tenant đã xác minh và không được client thay đổi tùy ý.

## 3. Authentication và method authorization tại thời điểm mở stream

Mỗi streaming RPC vẫn bắt đầu bằng một lần mở call. Authentication interceptor xác minh credential, tạo principal bất biến và đặt vào **io.grpc.Context**. Authorization interceptor kiểm tra method thực tế bằng **ServerCall.getMethodDescriptor().getFullMethodName()**.

Ví dụ policy mở stream:

~~~java
String method = call.getMethodDescriptor().getFullMethodName();
GrpcPrincipal principal = GrpcSecurityContext.PRINCIPAL.get();

if (principal == null) {
    call.close(
            Status.UNAUTHENTICATED
                    .withDescription("Authentication required"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}

if (!policy.allows(principal, method)) {
    call.close(
            Status.PERMISSION_DENIED
                    .withDescription("Permission denied"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}

return next.startCall(call, headers);
~~~

Đây là kiểm tra quyền **gọi method**. Interceptor biết method nào đang được dispatch, nhưng không nhất thiết có đủ thông tin domain để quyết định quyền trên từng order, document hoặc event trong message. Không nhầm method authorization với resource authorization.

Khi method bị từ chối, call phải kết thúc trước khi streaming handler được gọi. Nếu đã cho handler chạy rồi mới kiểm tra permission, service có thể đã tạo subscription, cấp buffer hoặc thực hiện side effect.

## 4. Principal và tenant phải gắn với đúng stream

Principal được tạo sau authentication phải bất biến và gắn với Context của chính RPC. Ví dụ key dùng chung:

~~~java
public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Trong streaming handler, lấy principal một lần khi bắt đầu và giữ reference bất biến cho vòng đời stream:

~~~java
GrpcPrincipal principal = GrpcSecurityContext.PRINCIPAL.get();

if (principal == null) {
    responseObserver.onError(
            Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException());
    return;
}
~~~

Nếu principal có quyền trên nhiều tenant, tenant được chọn phải được xác minh trước khi tạo subscription hoặc xử lý message. Một tenant ID trong protobuf message chỉ là tenant selector; server phải kiểm tra membership/entitlement với principal. Không cho message sau tự đổi tenant của một stream đã được ràng buộc vào tenant cố định.

Không lưu principal vào field mutable của singleton service implementation. Nhiều stream đồng thời có thể chạy trên cùng instance; field như currentUser hoặc currentTenant sẽ bị request khác ghi đè. Giữ principal trong biến cục bộ của stream handler hoặc truyền actor/tenant tường minh vào use case.

## 5. Kiểm tra từng message trước khi xử lý

Với client-streaming và bidirectional streaming, mỗi inbound message có thể tham chiếu resource khác. Quy trình cho từng message nên là:

1. Xác thực cấu trúc và kích thước message.
2. Kiểm tra tenant selector với tenant đã xác minh của principal.
3. Tải resource bằng truy vấn có tenant predicate.
4. Kiểm tra permission và ownership/relationship cho hành động cụ thể.
5. Kiểm tra business invariant.
6. Chỉ sau đó mới ghi dữ liệu, phát event hoặc gọi downstream.

Ví dụ một phần xử lý message upload:

~~~java
private void processEvent(
        GrpcPrincipal principal,
        UploadEventRequest request) {

    String tenantId = tenantAccess.requireTenant(
            principal,
            request.getTenantId());

    eventAuthorization.requireCanAppend(
            principal,
            tenantId,
            request.getAggregateId());

    eventUseCase.append(
            principal.subject(),
            tenantId,
            request);
}
~~~

tenantAccess xác minh caller được hoạt động trong tenant đã chọn; eventAuthorization kiểm tra quyền trên aggregate; eventUseCase chỉ chạy sau khi cả hai quyết định thành công. Repository bên dưới vẫn phải scope truy vấn/ghi theo tenant. Không chỉ kiểm tra tenant trong interceptor rồi tin mọi message tiếp theo.

Nếu một message không hợp lệ, contract cần quyết định rõ:

- **Terminate stream:** trả status như **PERMISSION_DENIED**, **INVALID_ARGUMENT** hoặc **FAILED_PRECONDITION**; phù hợp khi lỗi làm toàn bộ operation không còn an toàn.
- **Reject item and continue:** trả response item có accepted=false cùng mã lỗi ổn định; phù hợp khi từng item độc lập và contract cho phép partial success.

Không gửi chi tiết policy nội bộ trong response item. Nếu tiếp tục stream, tuyệt đối không thực hiện side effect cho item bị từ chối.

## 6. Ví dụ client-streaming có authorization theo message

Một client-streaming method có thể trả một summary sau khi nhận hết request. Phần cốt lõi dưới đây minh họa việc kiểm tra từng message trước khi gọi use case:

~~~java
@Override
public StreamObserver<UploadEventRequest> uploadEvents(
        StreamObserver<UploadSummary> responseObserver) {

    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    if (principal == null) {
        responseObserver.onError(
                Status.UNAUTHENTICATED
                        .withDescription("Authentication required")
                        .asRuntimeException());
        return new StreamObserver<>() {
            @Override public void onNext(UploadEventRequest value) {}
            @Override public void onError(Throwable error) {}
            @Override public void onCompleted() {}
        };
    }

    if (!principal.hasPermission("events:write")) {
        responseObserver.onError(
                Status.PERMISSION_DENIED
                        .withDescription("Permission denied")
                        .asRuntimeException());
        return new StreamObserver<>() {
            @Override public void onNext(UploadEventRequest value) {}
            @Override public void onError(Throwable error) {}
            @Override public void onCompleted() {}
        };
    }

    return new StreamObserver<>() {
        private int accepted;
        private boolean terminal;

        @Override
        public void onNext(UploadEventRequest request) {
            if (terminal) {
                return;
            }
            try {
                processEvent(principal, request);
                accepted++;
            } catch (AuthorizationDeniedException denied) {
                terminal = true;
                responseObserver.onError(
                        Status.PERMISSION_DENIED
                                .withDescription("Permission denied")
                                .asRuntimeException());
                cleanupUpload(principal);
            }
        }

        @Override
        public void onError(Throwable error) {
            if (!terminal) {
                terminal = true;
                cleanupUpload(principal);
            }
        }

        @Override
        public void onCompleted() {
            if (terminal) {
                return;
            }
            terminal = true;
            responseObserver.onNext(
                    UploadSummary.newBuilder()
                            .setAcceptedCount(accepted)
                            .build());
            responseObserver.onCompleted();
            cleanupUpload(principal);
        }
    };
}
~~~

Đây là skeleton minh họa vị trí kiểm tra. Implementation production cần bảo đảm callback được tuần tự hóa hoặc bảo vệ state terminal bằng cơ chế thread-safe; cleanup phải idempotent. Khi bị deny, cần dừng xử lý inbound stream; không tiếp tục nhận message rồi vô tình chạy use case.

Với lỗi item có thể phục hồi, thay vì kết thúc stream trong catch, hãy trả kết quả item-level theo contract và tiếp tục. Không được vừa gọi onError để kết thúc RPC vừa tiếp tục gửi response hoặc xử lý message tiếp theo.

## 7. Server-streaming phải kiểm soát cả dữ liệu phát ra

Server-streaming thường không nhận thêm request message sau khi mở call, nhưng server có thể phát nhiều response trong thời gian dài. Authorization không chỉ bảo vệ lúc tạo subscription; nó còn phải bảo đảm mọi dữ liệu được phát đều thuộc phạm vi đã được phép.

Ví dụ **WatchOrders**:

- Principal có permission **orders:watch**.
- Tenant được xác minh từ principal hoặc selector đã kiểm tra membership.
- Query/subscription lọc tenant tại repository hoặc event source.
- Nếu filter cho phép nhiều order, từng order phải nằm trong phạm vi caller.
- Không phát event đã bị xóa quyền truy cập hoặc thuộc tenant khác.
- Khi quyền hoặc membership bị thu hồi, hủy subscription hoặc tái đánh giá theo policy.

Nên đẩy filter tenant xuống nguồn dữ liệu thay vì subscribe tất cả rồi lọc sau. Điều này giảm nguy cơ dữ liệu trái phép đi vào buffer, log, cache hoặc callback trước khi bị loại bỏ.

Với stream dài, một policy snapshot tại thời điểm mở có thể trở nên cũ. Hãy định nghĩa thời hạn tối đa, chu kỳ revalidation hoặc cơ chế push revocation. Nếu policy chỉ có hiệu lực tại thời điểm mở stream, tài liệu API và threat model phải nói rõ giới hạn đó.

## 8. Thu hồi quyền, token expiry và revalidation

Authentication thường xác minh credential khi RPC được mở. Token hết hạn sau đó không nhất thiết tự động đóng một stream đang tồn tại. Tương tự, quyền hoặc membership có thể bị thu hồi trong khi stream vẫn mở.

Cần chọn một mô hình có chủ đích:

| Mô hình | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| **Authorize at open** | Quyền được kiểm tra khi mở; stream sống tối đa trong thời hạn quy định | Stream ngắn, quyền ít thay đổi |
| **Periodic revalidation** | Kiểm tra lại principal/policy theo chu kỳ hoặc trước nhóm message | Stream dài, quyền có thể thay đổi |
| **Event-driven revocation** | Nhận tín hiệu thu hồi và hủy stream liên quan | Cần thu hồi nhanh |
| **Per-message authorization** | Kiểm tra quyền/resource trước mỗi message hoặc action | Message có resource/action khác nhau |

Không nhất thiết gọi policy engine từ xa cho mọi message. Có thể dùng permission snapshot đã xác minh, cache có TTL ngắn hoặc batch evaluation; nhưng phải tính đến thời gian thu hồi quyền và phạm vi dữ liệu. Với thao tác nhạy cảm, revalidate ngay trước side effect nếu policy có thể thay đổi trong thời gian stream.

Khi token hết hạn, cần chính sách cho stream hiện tại: kết thúc bằng **UNAUTHENTICATED**, cho phép hoàn tất trong giới hạn ngắn đã công bố, hoặc yêu cầu client mở stream mới bằng credential mới. Không tự động refresh credential phía server bằng token của client nếu không có flow được thiết kế rõ.

## 9. Cancellation, cleanup và giới hạn tài nguyên

Streaming giữ subscription, buffer, callback và có thể cả tài nguyên downstream trong thời gian dài. Khi client cancel, deadline hết hoặc authorization bị thu hồi, server phải dừng công việc liên quan.

Với grpc-java, **ServerCallStreamObserver** cung cấp cơ chế kiểm tra cancellation và đăng ký callback hủy. Ví dụ:

~~~java
if (responseObserver instanceof ServerCallStreamObserver<?> serverObserver) {
    serverObserver.setOnCancelHandler(() -> {
        subscription.cancel();
        releaseStreamResources();
    });
}
~~~

Tên và cách dùng API cần đối chiếu phiên bản grpc-java trong dự án. Dù dùng API nào, cleanup phải idempotent vì cancellation, lỗi downstream và lỗi authorization có thể xảy ra gần nhau.

Các tài nguyên cần giải phóng:

- Subscription tới broker hoặc event source.
- Database cursor, change stream hoặc reactive subscription.
- Buffer và queue đang giữ message.
- Scheduled task revalidation/heartbeat.
- Future và tác vụ async có thể cancel.
- Quota/concurrency slot đã cấp cho tenant.

Không để một stream bị deny tiếp tục giữ subscription hoặc worker. Không giữ principal/Context của RPC trong job dài hạn sau khi stream kết thúc; chuyển dữ liệu actor/tenant tối thiểu vào job envelope nếu cần xử lý độc lập.

## 10. Flow control và backpressure là một phần của isolation

Một caller được phép mở stream vẫn có thể gửi message quá nhanh hoặc không đọc response. Nếu server nhận message nhanh hơn khả năng xử lý, queue có thể tăng không giới hạn và làm ảnh hưởng tenant khác.

- Giới hạn kích thước message và số message đang chờ.
- Áp quota stream đồng thời theo principal/tenant.
- Dùng flow control để điều tiết inbound/outbound thay vì buffer vô hạn.
- Kiểm tra authorization trước khi enqueue công việc tạo side effect.
- Không phát response nhạy cảm khi outbound stream chưa sẵn sàng.
- Hủy hoặc throttle stream vượt quota theo contract.
- Dùng fairness để một tenant không chiếm toàn bộ worker, connection hoặc buffer.

Ở outbound streaming, **isReady()** và callback on-ready của grpc-java có thể giúp producer chỉ gửi khi transport có khả năng nhận thêm dữ liệu. Với inbound streaming, manual flow control có thể giới hạn số message được yêu cầu tiếp theo. Dù dùng cơ chế nào, authorization phải được thực hiện trước khi dữ liệu được đưa vào hàng đợi xử lý nghiệp vụ.

**RESOURCE_EXHAUSTED** phù hợp khi quota hoặc giới hạn tài nguyên bị vượt. Không dùng status này để biểu diễn thiếu permission; thiếu quyền vẫn là **PERMISSION_DENIED**.

## 11. Status và lỗi trong một stream đang mở

Một stream có thể kết thúc bằng status sau khi đã trao đổi một số message. Client cần biết các message trước đó có thể đã được xử lý hay chưa; status cuối không tự động rollback side effect đã commit.

| Tình huống | Status thường dùng | Lưu ý |
| --- | --- | --- |
| Không có principal khi mở stream | **UNAUTHENTICATED** | Không gọi streaming handler |
| Thiếu quyền gọi method | **PERMISSION_DENIED** | Từ chối trước khi tạo subscription |
| Một message truy cập resource ngoài phạm vi | **PERMISSION_DENIED** hoặc **NOT_FOUND** | Theo chính sách resource concealment |
| Message sai cấu trúc | **INVALID_ARGUMENT** | Có thể kết thúc stream hoặc trả lỗi item-level |
| Resource không ở trạng thái phù hợp | **FAILED_PRECONDITION** | Không thực hiện action cho message đó |
| Policy dependency không sẵn sàng | **UNAVAILABLE** | Fail-closed; không xử lý message chưa được authorize |
| Deadline của call hết | **DEADLINE_EXCEEDED** | Dừng tác vụ và cleanup |
| Client hủy stream | **CANCELLED** | Dừng subscription và công việc có thể hủy |
| Quota stream/message bị vượt | **RESOURCE_EXHAUSTED** | Throttle hoặc kết thúc theo contract |

Với server async API, có thể kết thúc stream bằng **responseObserver.onError(Status.PERMISSION_DENIED.asRuntimeException())**. Sau terminal signal, không gửi thêm onNext hoặc onCompleted. Nếu muốn tiếp tục sau lỗi một message, biểu diễn lỗi trong response message thay vì kết thúc RPC.

Không gửi tên permission nội bộ, tenant membership hoặc policy expression trong status description. Dùng reason code ổn định và thông tin tối thiểu mà caller được phép biết.

## 12. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra permission khi mở stream | Message sau truy cập resource khác vẫn được xử lý | Authorize từng resource/action khi cần |
| Tin tenant ID trong message | Caller đổi tenant giữa stream | Xác minh selector với principal; ràng buộc stream vào tenant |
| Dùng một principal mutable trên service singleton | Hai stream đồng thời có thể lẫn danh tính | Principal bất biến, state cục bộ theo stream |
| Subscribe toàn bộ rồi lọc response | Dữ liệu ngoài phạm vi vào buffer/cache/log | Tenant filter tại nguồn dữ liệu |
| Không revalidate stream dài | Quyền đã thu hồi vẫn còn hiệu lực | TTL, periodic check hoặc revocation cancellation |
| Không cleanup khi cancel/deny | Rò subscription, worker và buffer | Cleanup idempotent ở mọi terminal path |
| Buffer inbound vô hạn | Một tenant gây noisy neighbor | Flow control, quota và queue giới hạn |
| Gọi onError rồi vẫn gửi response | Vi phạm terminal state của stream | Quản lý state terminal, chỉ phát một terminal signal |
| Dùng PERMISSION_DENIED cho quota | Client hiểu sai nguyên nhân | Dùng RESOURCE_EXHAUSTED cho quota |
| Gửi lỗi policy chi tiết trong status | Lộ cấu trúc bảo mật | Status chung, audit nội bộ có kiểm soát |

## 13. Kiểm thử authorization cho streaming RPC

Test phải bao phủ cả lúc mở stream và từng message. Một unary test cho interceptor không chứng minh streaming an toàn.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không có credential | **UNAUTHENTICATED**; handler không được gọi |
| Principal thiếu method permission | **PERMISSION_DENIED**; không tạo subscription |
| Client-streaming gửi message thuộc tenant được cấp | Message được xử lý |
| Client-streaming gửi message thuộc tenant khác | Message bị từ chối; không có side effect |
| Bidirectional stream đổi resource giữa các message | Mỗi resource được authorize độc lập |
| Server-streaming filter yêu cầu tenant ngoài phạm vi | Stream không được mở hoặc bị từ chối |
| Resource bị thu hồi quyền trong stream dài | Revalidation/revocation policy kết thúc hoặc giới hạn stream |
| Client cancel | Subscription, queue và worker được cleanup |
| Deadline hết | Không tiếp tục công việc nền vô hạn |
| Client gửi message nhanh hơn khả năng xử lý | Flow control/quota giới hạn buffer |
| Một item bị reject theo partial-success contract | Có kết quả item-level; không có side effect cho item đó |
| Hai stream đồng thời thuộc hai tenant | Không lẫn principal, tenant, response hoặc cache |

Nên dùng in-process gRPC test hoặc transport integration test với generated stub và interceptor production. Với client-streaming/bidi, gửi nhiều message có resource ID khác nhau và kiểm tra repository/downstream mock. Với server-streaming, xác minh event source được subscribe bằng tenant/resource đã scope. Thêm test cancellation, deadline, revalidation và terminal signal để phát hiện resource leak.

Các assertion quan trọng:

1. Method authorization xảy ra trước khi streaming handler tạo subscription.
2. Per-message authorization xảy ra trước repository mutation hoặc downstream call.
3. Message bị deny không tạo event, không ghi database và không phát response chứa dữ liệu nhạy cảm.
4. Stream terminal chỉ phát một lần; sau đó không có message mới.
5. Cancellation/revocation giải phóng mọi subscription và buffer.
6. Hai stream đồng thời không chia sẻ mutable principal hoặc tenant state.

## 14. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Định nghĩa **EventService/UploadEvents** là client-streaming và **OrderService/WatchOrders** là server-streaming.
2. Thêm authentication interceptor tạo principal bất biến trong shared **io.grpc.Context**.
3. Thêm method authorization để kiểm tra **events:write** và **orders:watch** trước khi handler chạy.
4. Với mỗi UploadEventRequest, xác minh tenant, aggregate và quyền append trước khi ghi event.
5. Với WatchOrders, scope subscription bằng tenant đã xác minh và chỉ phát event thuộc phạm vi.
6. Thêm cơ chế terminal state và cleanup khi deny, error, cancellation hoặc deadline.
7. Đặt giới hạn message size, stream concurrency và inbound/outbound buffering.
8. Viết integration test cho message cross-tenant, quyền bị thu hồi, client cancel, deadline và hai stream đồng thời.

### Câu hỏi tự kiểm tra

**1. Vì sao method authorization khi mở stream chưa đủ?**  
Vì message về sau có thể tham chiếu resource hoặc tenant khác; quyền gọi method không cấp quyền cho mọi resource.

**2. Server-streaming cần kiểm tra gì ngoài permission của method?**  
Quyền subscribe filter/resource và bảo đảm từng event được phát thuộc phạm vi đã authorize.

**3. Client-streaming cần kiểm tra gì trước mỗi message?**  
Tenant, resource/aggregate, permission cho hành động và business invariant trước khi ghi hoặc tạo side effect.

**4. Có phải gọi policy engine từ xa cho mọi message không?**  
Không nhất thiết. Có thể dùng snapshot/cache/batch theo threat model, nhưng phải bảo đảm TTL và thời điểm thu hồi quyền đáp ứng yêu cầu bảo mật.

**5. Token hết hạn có tự động đóng stream đang mở không?**  
Không nên giả định điều đó. Ứng dụng cần quy định max stream lifetime, revalidation hoặc cơ chế thu hồi và cancellation.

**6. Khi một message bị từ chối, stream có phải kết thúc không?**  
Tùy contract. Có thể kết thúc bằng gRPC status hoặc trả kết quả từ chối ở cấp item; cả hai cách đều phải bảo đảm không có side effect trái phép.

**7. Vì sao cần cleanup khi client cancel?**  
Để giải phóng subscription, buffer, worker, cursor và quota; nếu không, stream đã kết thúc vẫn tiêu thụ tài nguyên.

**8. RESOURCE_EXHAUSTED khác PERMISSION_DENIED thế nào?**  
RESOURCE_EXHAUSTED biểu diễn quota/giới hạn tài nguyên; PERMISSION_DENIED biểu diễn policy đã từ chối quyền.

## Tổng kết

Authorization cho streaming RPC có hai phạm vi: quyền gọi method tại thời điểm mở stream và quyền trên từng resource/action trong quá trình trao đổi message. Server-streaming phải giới hạn subscription và dữ liệu phát ra; client-streaming và bidirectional streaming phải kiểm tra từng message trước side effect khi message có thể tham chiếu resource khác nhau. Principal và tenant phải gắn với đúng stream, còn quyền bị thu hồi, deadline và cancellation cần chính sách revalidation/cleanup rõ ràng. Flow control, quota và buffer giới hạn bảo vệ cả tính sẵn sàng lẫn ranh giới tenant. Kiểm thử phải chứng minh message ngoài phạm vi không tạo side effect, stream được kết thúc đúng cách và tài nguyên được giải phóng.

