# Audit quyền gọi method

Audit quyền gọi method ghi nhận ai đã yêu cầu gọi một gRPC method, hệ thống xác thực caller ra sao, policy nào quyết định cho phép hoặc từ chối và RPC kết thúc với kết quả nào. Audit giúp điều tra truy cập trái phép, truy vết thay đổi quyền, phát hiện hành vi bất thường và chứng minh quyết định authorization trong vận hành.

Trong Spring gRPC, audit thường phối hợp với authentication/authorization interceptor, gRPC Context, service layer và một audit sink có kiểm soát. Cần ghi nhận cả request bị từ chối trước khi handler chạy lẫn request được phép; với streaming RPC, cần theo dõi thời điểm bắt đầu và kết thúc stream. Audit record phải đủ để truy nguyên quyết định nhưng không chứa bearer token, private key hoặc payload nhạy cảm.

## 1. Audit khác log và metrics như thế nào?

Ba loại telemetry có mục đích khác nhau:

| Loại | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Application log | Điều gì đã xảy ra trong quá trình xử lý? | Handler gặp lỗi khi đọc order |
| Metrics | Hệ thống có xu hướng hoạt động ra sao? | Số RPC bị PERMISSION_DENIED theo method |
| Security audit | Ai yêu cầu hành động nào, policy quyết định gì và kết quả ra sao? | Principal user-42 bị từ chối OrderService/CancelOrder bởi policy orders-admin-v3 |

Một log dòng chữ "permission denied" không đủ để làm audit nếu thiếu danh tính caller, method, policy version, thời điểm và correlation ID. Metrics tổng hợp cũng không thay thế sự kiện audit có thể truy ngược tới một request cụ thể.

Audit quyền gọi method nên trả lời tối thiểu:

- Ai gọi: principal/workload identity đã được xác minh, issuer hoặc loại authentication.
- Gọi gì: full gRPC method name, ví dụ acme.orders.v1.OrderService/CancelOrder.
- Trên đối tượng nào: resource type/id hoặc tenant khi policy cần phân quyền theo tài nguyên.
- Vì sao quyết định: ALLOW/DENY, policy/rule ID và phiên bản policy.
- Khi nào và từ đâu: timestamp UTC, request ID, peer identity hoặc nguồn kết nối theo mức dữ liệu được phép lưu.
- Kết quả: gRPC status, duration và thông tin cancellation/stream completion cần thiết.

## 2. Audit ở ranh giới method và resource

gRPC method là một ranh giới tốt để áp dụng policy chung. Full method name được tạo từ proto package, service và method; không dùng Java package hay tên Spring bean:

```text
acme.orders.v1.OrderService/GetOrder
acme.orders.v1.OrderService/CancelOrder
acme.orders.v1.OrderService/WatchOrderEvents
```

Tuy nhiên, quyền gọi method chưa chắc đồng nghĩa quyền thao tác trên mọi resource. Một principal có thể được phép gọi GetOrder nhưng chỉ được đọc order thuộc tenant của mình. Interceptor có thể kiểm tra quyền ở mức service/method; service/application layer phải tiếp tục kiểm tra quyền trên resource sau khi biết order ID và tenant thực tế.

Vì vậy, audit có thể có hai sự kiện liên quan:

1. Method authorization: caller có quyền gọi RPC method này không?
2. Resource authorization/business action: caller có quyền đọc, sửa hoặc hủy resource cụ thể không?

Không ghi một quyết định ALLOW ở interceptor như thể toàn bộ hành động nghiệp vụ đã thành công. Ghi riêng decision và outcome để điều tra không nhầm lẫn giữa "được phép bắt đầu" với "đã hoàn tất".

## 3. Thiết kế audit event

Một schema audit nên có cấu trúc ổn định, có version và có thể được truy vấn:

| Field | Ý nghĩa |
| --- | --- |
| event_id | ID duy nhất của audit event |
| schema_version | Phiên bản schema để tiến hóa dữ liệu |
| occurred_at | Timestamp UTC |
| request_id / trace_id | Liên kết event với call và trace |
| rpc_service / rpc_method | Service và method đã gọi |
| principal_id | Subject/workload identity đã xác minh |
| identity_issuer / authn_type | Nguồn và phương thức xác thực |
| tenant_id | Tenant đã được xác minh nếu có |
| peer_identity | Danh tính peer TLS/mTLS hoặc gateway theo trust model |
| decision | ALLOW, DENY hoặc NOT_EVALUATED |
| policy_id / policy_version | Rule đã quyết định |
| resource_type / resource_id | Đối tượng liên quan, nếu policy biết |
| grpc_status | Status cuối của RPC |
| duration_ms | Thời gian từ nhận call tới kết thúc |
| outcome | COMPLETED, FAILED, CANCELLED hoặc STREAM_OPEN/CLOSED theo schema |

Không phải mọi field đều có giá trị ở mọi giai đoạn. Nếu authentication thất bại, principal có thể là anonymous/unknown; nếu interceptor từ chối trước khi đọc request, resource ID có thể chưa biết. Dùng giá trị rõ ràng như NOT_AUTHENTICATED hoặc null có schema thay vì tự suy diễn.

Timestamp nên được ghi bằng UTC. Duration dùng monotonic clock như System.nanoTime để tránh thay đổi đồng hồ hệ thống làm sai số đo. Không dùng timestamp client gửi làm thời điểm audit đáng tin cậy.

## 4. Ghi nhận full method name và request identity

Trong ServerInterceptor, lấy method name từ MethodDescriptor:

```java
String fullMethod =
    call.getMethodDescriptor().getFullMethodName();
```

Đây là định danh ổn định theo Protobuf contract và phù hợp làm dimension cho audit. Tránh dùng request payload để đoán method hoặc lấy tên method từ header do caller gửi.

Request ID có thể được gateway hoặc client truyền qua metadata. Nếu hệ thống tin gateway, xác minh kết nối tới gateway và quy định gateway được phép đặt header đó. Nếu caller không thuộc trust boundary, server nên tạo request ID riêng hoặc lưu cả caller-provided ID và server-generated ID dưới hai field khác nhau.

Không dùng request ID làm bằng chứng authentication. Request ID chỉ hỗ trợ correlation; principal phải lấy từ token/certificate đã xác minh.

## 5. Kết hợp authentication, authorization và audit interceptor

Một call pipeline có thể chia trách nhiệm:

```text
Inbound gRPC call
       |
       v
Audit envelope interceptor (outer)
       | tạo per-call audit state
       | bọc ServerCall.close
       v
Authentication interceptor
       | xác minh token hoặc peer identity
       | gắn principal vào Context
       v
Authorization interceptor
       | kiểm tra full method và policy
       | ghi ALLOW/DENY vào audit state
       v
Service handler
       | kiểm tra resource-level permission
       | thực hiện nghiệp vụ
       v
ServerCall.close(status)
       |
       v
Audit sink nhận decision + outcome
```

Audit envelope cần bao ngoài authentication/authorization để quan sát cả call bị từ chối trước khi handler chạy. Authentication/authorization ghi kết quả vào state riêng của call. Khi ServerCall đóng, audit envelope kết hợp decision với status cuối.

Thứ tự interceptor thực tế phụ thuộc cách server xây dựng chain. Không suy luận thứ tự chỉ từ thứ tự bean trong Spring context; cần cấu hình rõ và viết test xác minh interceptor audit thật sự bao quanh các nhánh deny.

## 6. Lưu state riêng cho từng call bằng Context

Không lưu principal, method decision hoặc request ID vào field mutable dùng chung của interceptor singleton. Nhiều RPC chạy đồng thời trên cùng instance. Có thể tạo một audit state cho mỗi call rồi truyền qua gRPC Context:

```java
import io.grpc.Context;

static final Context.Key<CallAuditState> AUDIT_STATE =
    Context.key("call-audit-state");

final class AuditEnvelopeInterceptor implements ServerInterceptor {
    private final AuditSink auditSink;

    AuditEnvelopeInterceptor(AuditSink auditSink) {
        this.auditSink = auditSink;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor()
            .getFullMethodName();
        CallAuditState state = new CallAuditState(
            method, System.nanoTime(), headers.get(REQUEST_ID));

        ServerCall<ReqT, RespT> wrapped =
            new ForwardingServerCall
                .SimpleForwardingServerCall<ReqT, RespT>(call) {
            private final AtomicBoolean recorded = new AtomicBoolean();

            @Override
            public void close(Status status, Metadata trailers) {
                try {
                    super.close(status, trailers);
                } finally {
                    if (recorded.compareAndSet(false, true)) {
                        state.complete(status, System.nanoTime());
                        try {
                            auditSink.tryPublish(state.toEvent());
                        } catch (RuntimeException auditFailure) {
                            auditMetrics.publishFailure();
                        }
                    }
                }
            }
        };

        Context context = Context.current()
            .withValue(AUDIT_STATE, state);
        return Contexts.interceptCall(
            context, wrapped, headers, next);
    }
}
```

Đây là skeleton minh họa kiến trúc; CallAuditState, AuditSink và metadata key cần được định nghĩa trong ứng dụng. Trong implementation production, tryPublish phải không ném exception ngược vào gRPC call path. Bọc lỗi sink, phát metric/alert và áp dụng chính sách audit failure đã được phê duyệt.

Contexts.interceptCall đưa state vào Context của listener/handler downstream. Interceptor xác thực và phân quyền có thể lấy state bằng AUDIT_STATE.get(), sau đó ghi principal, policy và decision vào đúng call.

Nếu call bị cancel mà server không gọi close theo một đường code cụ thể, cần bổ sung quan sát listener onCancel/onComplete hoặc cơ chế lifecycle tương ứng để state được kết thúc đúng một lần. Không phát hai audit event cho cùng một call chỉ vì nhiều terminal callback.

## 7. Ghi quyết định ALLOW/DENY từ authorization interceptor

Authorization interceptor nên ghi decision ngay sau khi policy được đánh giá:

```java
CallAuditState audit = AUDIT_STATE.get();
String method = call.getMethodDescriptor().getFullMethodName();
Principal principal = authenticatedPrincipal();

if (principal == null) {
    audit.setIdentity("anonymous", "NOT_AUTHENTICATED");
    audit.setDecision("DENY", "authentication-required", policyVersion);
    call.close(Status.UNAUTHENTICATED, new Metadata());
    return new ServerCall.Listener<>() {};
}

AuthorizationDecision decision =
    policy.evaluate(principal, method);

audit.setIdentity(principal.id(), principal.issuer());
audit.setDecision(
    decision.allowed() ? "ALLOW" : "DENY",
    decision.policyId(),
    decision.policyVersion());

if (!decision.allowed()) {
    call.close(Status.PERMISSION_DENIED, new Metadata());
    return new ServerCall.Listener<>() {};
}

return next.startCall(call, headers);
```

Đoạn code là phần logic minh họa; principal phải đến từ authentication layer đã xác minh và policy phải kiểm tra method/resource phù hợp. Nếu interceptor từ chối, outer audit wrapper vẫn nhìn thấy ServerCall.close và có thể phát event chứa DENY cùng UNAUTHENTICATED hoặc PERMISSION_DENIED.

Không ghi ALLOW trước khi policy hoàn tất. Nếu policy engine lỗi hoặc timeout, ghi decision NOT_EVALUATED/ERROR và ánh xạ lỗi theo security policy; không tự biến lỗi policy engine thành ALLOW.

## 8. Audit outcome khi RPC kết thúc

Authorization decision và RPC outcome là hai dữ kiện riêng:

| Decision | RPC outcome | Cách diễn giải |
| --- | --- | --- |
| ALLOW | OK | Được phép và RPC kết thúc thành công |
| ALLOW | INTERNAL | Được phép nhưng xử lý gặp lỗi |
| ALLOW | CANCELLED | Được phép nhưng caller hủy |
| ALLOW | DEADLINE_EXCEEDED | Được phép nhưng vượt deadline |
| DENY | UNAUTHENTICATED | Không xác minh được caller |
| DENY | PERMISSION_DENIED | Caller hợp lệ nhưng không đủ quyền |
| NOT_EVALUATED | UNAVAILABLE | Policy/authentication dependency không khả dụng |

Status OK không chứng minh thay đổi dữ liệu đã commit nếu handler trả response trước khi transaction hoàn tất hoặc thao tác bất đồng bộ còn tiếp tục. Với hành động quan trọng như chuyển tiền, thay đổi quyền hoặc hủy đơn, audit nghiệp vụ nên được ghi tại application/domain layer cùng transaction.

Không phát event "business action succeeded" chỉ dựa trên việc ServerCall.close(Status.OK) được gọi. Event đó phải dựa trên kết quả commit hoặc trạng thái nghiệp vụ xác định.

## 9. Audit cho server-streaming và bidirectional-streaming

Streaming RPC có vòng đời dài hơn unary:

- Ghi một event khi method authorization được quyết định.
- Ghi event kết thúc khi stream đóng, lỗi hoặc bị cancel.
- Có thể ghi số message hoặc byte count tổng hợp nếu cần cho điều tra.
- Không ghi từng payload/message mặc định vì có thể làm lộ dữ liệu và tạo lượng audit quá lớn.
- Với stream kéo dài, theo dõi thời lượng, inactivity timeout và giới hạn tài nguyên.

Một stream có thể được authorize lúc mở nhưng quyền của principal thay đổi trong khi stream đang chạy. Với dữ liệu nhạy cảm hoặc stream lâu, cần quyết định có kiểm tra lại quyền theo chu kỳ, theo từng message hoặc khi credential hết hạn hay không. Ghi rõ policy này trong audit design.

Nếu server gửi nhiều message rồi kết thúc bằng lỗi, audit outcome phải giữ status cuối, không coi các message trước đó là một RPC thành công. Nếu cần biết message nào đã được xử lý/commit, ghi domain event riêng với sequence/correlation phù hợp.

## 10. Audit sink: độ bền, thứ tự và backpressure

Audit chỉ có giá trị nếu event được lưu đủ bền và có thể truy xuất. Một sink có thể là queue bền vững, event broker hoặc storage audit chuyên dụng. Cần quyết định:

1. Event được ghi đồng bộ hay enqueue bất đồng bộ?
2. Queue đầy hoặc storage lỗi thì RPC có tiếp tục không?
3. Event nào phải durable trước khi thực hiện hành động?
4. Có retry và deduplication theo event_id không?
5. Ai được đọc/xóa dữ liệu audit và thời gian retention bao lâu?

Không gọi remote audit database với blocking I/O trong interceptor trên mỗi RPC nếu điều đó làm tăng latency hoặc cạn server threads. Có thể enqueue vào bounded durable buffer và xử lý bất đồng bộ. Queue không được phép tăng vô hạn; cần metric queue depth, publish failure, oldest event age và alert.

Fail-open hay fail-closed là quyết định theo rủi ro:

| Loại hoạt động | Hướng xử lý có thể chọn |
| --- | --- |
| RPC đọc thông thường, audit telemetry không bắt buộc giao dịch | Có thể tiếp tục khi sink tạm lỗi nếu event được buffer bền và có cảnh báo |
| Thay đổi quyền, thao tác tài chính hoặc hành động bắt buộc compliance | Có thể yêu cầu audit durable trước commit hoặc từ chối khi không thể ghi |
| Security denial event | Ưu tiên giữ event bằng durable queue/buffer để không mất dấu truy cập bị từ chối |

Với hành động nghiệp vụ cần audit nguyên tử, transactional outbox trong cùng database transaction thường phù hợp hơn việc cố ghi remote audit sink từ interceptor. Interceptor không biết transaction đã commit hay rollback; application layer phải phát domain audit event đúng thời điểm.

## 11. Tính toàn vẹn, bảo mật và quyền truy cập audit

Audit store có thể trở thành mục tiêu chỉnh sửa hoặc xóa dấu vết. Biện pháp bảo vệ gồm:

- Append-only hoặc WORM storage khi yêu cầu compliance cần tính bất biến.
- Hạn chế quyền ghi, đọc, export và xóa theo vai trò riêng.
- Mã hóa khi truyền và khi lưu.
- Hash chain/chữ ký hoặc cơ chế integrity proof nếu threat model yêu cầu phát hiện sửa đổi.
- Đồng bộ thời gian và giám sát clock drift.
- Retention, legal hold và quy trình xóa theo chính sách dữ liệu.
- Audit cả hành động quản trị trên chính audit system.

Hash chain cần có anchor hoặc chữ ký được bảo vệ; chỉ nối hash trong cùng một database mà administrator có thể sửa cả dữ liệu lẫn hash không tạo bảo đảm bất biến mạnh. Chọn mức kiểm soát theo threat model và yêu cầu pháp lý.

Không ghi access token, refresh token, private key, mật khẩu, toàn bộ request payload hoặc dữ liệu cá nhân không cần thiết. Ưu tiên principal ID, resource ID đã phân loại, policy ID và status. Nếu cần lưu IP/peer address, xác định mục đích, retention và quyền truy cập.

## 12. Spring gRPC integration và kiểm thử audit

Trong Spring, audit interceptor, authentication interceptor, authorization policy và AuditSink có thể được quản lý bằng dependency injection. Cần xác minh chúng được gắn vào đúng gRPC server do starter quản lý:

1. Tạo unit test cho policy: principal, method, resource và decision.
2. Dựng in-process server với audit envelope bao ngoài authentication/authorization interceptor.
3. Gọi RPC hợp lệ và bị từ chối; kiểm tra audit event có principal, method, decision và status.
4. Gọi hai RPC đồng thời với principal khác nhau để xác minh per-call state không rò.
5. Kiểm tra stream hoàn tất, lỗi và cancellation chỉ phát event terminal một lần.
6. Mô phỏng audit sink timeout/full và xác minh fail-open/closed policy.
7. Khởi động Spring context để kiểm tra interceptor bean và sink thực sự được đăng ký.
8. Chạy TCP/TLS test nếu cần xác minh peer identity từ certificate hoặc gateway.

Không chỉ test rằng AuditSink được gọi. Kiểm tra nội dung event, policy version, correlation ID, outcome và redaction. Dùng fake clock hoặc clock injection để kiểm tra timestamp/duration ổn định; tránh assertion phụ thuộc thời gian wall-clock chính xác tuyệt đối.

## 13. Ma trận kiểm thử và bài tập vận dụng

| Nhóm | Ca kiểm thử | Điều kiện PASS |
| --- | --- | --- |
| Allowed call | Principal có quyền gọi method | Audit ghi ALLOW và method đúng |
| Missing identity | Không có credential | DENY/UNAUTHENTICATED, handler không chạy |
| Invalid identity | Token/chứng thư sai | DENY và identity failure được phân loại |
| Permission denied | Principal thiếu role | DENY/PERMISSION_DENIED, policy ID được ghi |
| Resource policy | Principal truy cập resource ngoài tenant | Resource decision bị từ chối |
| Outcome | Call được phép nhưng handler lỗi | Decision ALLOW, status lỗi riêng |
| Cancellation | Caller hủy call | Audit ghi CANCELLED một lần |
| Streaming | Stream kết thúc sau nhiều message | Có decision và terminal outcome |
| Concurrency | Nhiều principal gọi đồng thời | Không rò identity/request ID giữa call |
| Sink unavailable | Queue/storage lỗi | Hành vi đúng fail-open/closed policy |
| Integrity | Event bị sửa/xóa | Cơ chế phát hiện hoặc storage policy hoạt động |
| Privacy | Token/payload nhạy cảm | Không xuất hiện trong audit record |
| Spring wiring | Server do starter quản lý | Audit/authz interceptor thực sự chạy |
| Transport identity | mTLS/gateway | Peer identity được xác minh và liên kết đúng principal |

**Bài tập:** OrderService có GetOrder, CancelOrder và WatchOrderEvents. ORDER_READ được phép đọc đơn hàng trong tenant của principal; ORDER_ADMIN được phép hủy. Mọi call phải có request ID, policy version và audit event.

1. Thiết kế audit event schema có decision và outcome tách biệt.
2. Viết authentication/authorization interceptor và audit envelope theo per-call Context state.
3. Kiểm tra GetOrder được phép, CancelOrder bị từ chối và handler không chạy khi DENY.
4. Kiểm tra resource-level authorization khi order thuộc tenant khác.
5. Ghi audit cho WatchOrderEvents khi stream complete, error hoặc cancel.
6. Mô phỏng audit sink đầy/không khả dụng và xác minh policy đã chọn.
7. Bổ sung transactional outbox cho hành động hủy đơn nếu audit thành công nghiệp vụ phải nguyên tử với commit.
8. Kiểm tra redaction, retention, quyền đọc audit và integrity controls.
9. Viết Spring context test xác minh interceptor chain đúng thứ tự.

**Câu hỏi tự kiểm tra:**

- Audit khác application log và metrics ở mục tiêu nào?
- Vì sao phải lưu full gRPC method name?
- Vì sao ALLOW không đồng nghĩa business action đã commit?
- Làm thế nào audit được request bị từ chối trước service handler?
- Vì sao audit state phải riêng cho từng call?
- Streaming RPC cần event bắt đầu và kết thúc như thế nào?
- Khi nào nên dùng transactional outbox?
- Fail-open và fail-closed ảnh hưởng audit ra sao?
- Vì sao hash chain cần anchor/chữ ký được bảo vệ?
- Những dữ liệu nào không nên ghi vào audit record?

**Ghi nhớ:** Audit quyền gọi method phải nối được danh tính đã xác minh, full method name, policy decision và RPC outcome. Bao audit interceptor quanh authentication/authorization để ghi cả call bị từ chối; dùng Context state riêng từng call; tách method permission khỏi resource/business authorization; bảo vệ sink, integrity và dữ liệu nhạy cảm. Với Spring gRPC, kiểm tra interceptor chain trong server thực tế và ghi domain audit tại transaction boundary khi cần bảo đảm commit nguyên tử.
