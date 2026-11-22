# Kiểm tra quyền trước business action

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định điểm kiểm tra authorization trong luồng xử lý một RPC trước khi thực hiện side effect.
- Phân biệt quyền gọi method với quyền thao tác trên resource cụ thể.
- Thiết kế luồng từ authentication, principal, policy decision đến business action theo nguyên tắc deny-by-default.
- Đặt kiểm tra quyền đúng vị trí trong gRPC adapter, application service và transaction.
- Ngăn lỗi TOCTOU khi quyền phụ thuộc trạng thái resource có thể thay đổi đồng thời.
- Xử lý status, idempotency, audit, async job và streaming mà không bỏ qua authorization.
- Kiểm thử để chứng minh request bị từ chối không tạo side effect.

## 1. Vì sao phải kiểm tra quyền trước business action?

Trong **SPRING_GRPC**, một RPC có thể đọc dữ liệu, tạo đơn, hủy đơn, chuyển tiền hoặc thay đổi cấu hình. Xác thực thành công chỉ cho biết caller là ai; nó không chứng minh caller được phép thực hiện hành động cụ thể.

**Kiểm tra quyền trước business action** nghĩa là server phải xác minh đủ điều kiện authorization trước khi thực hiện bất kỳ side effect nào của use case. Side effect có thể là:

- Ghi hoặc cập nhật dữ liệu trong database.
- Phát event, gửi message hoặc tạo job.
- Gọi dịch vụ thanh toán, inventory hoặc dịch vụ bên ngoài.
- Tạo file export, signed URL hoặc tài nguyên mới.
- Thay đổi trạng thái workflow hoặc phát thông báo.

Nếu kiểm tra quyền sau khi đã ghi dữ liệu hoặc gọi downstream, việc trả **PERMISSION_DENIED** không thể đảo ngược tác động đã xảy ra. Một request bị từ chối phải kết thúc trước khi business action bắt đầu.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant I as Authentication / Authorization
    participant A as gRPC adapter
    participant U as Application use case
    participant P as Policy
    participant D as Database / downstream
    C->>I: RPC + credentials
    I->>I: Xác minh identity
    I->>A: Principal đã xác minh
    A->>U: Command + principal
    U->>P: Kiểm tra quyền method/resource
    alt Được phép
        P-->>U: Allow
        U->>D: Business action trong transaction
        D-->>U: Kết quả
        U-->>C: Response
    else Bị từ chối
        P-->>U: Deny
        U-->>C: PERMISSION_DENIED
    end
~~~

Authorization cần diễn ra trước **ranh giới side effect**. Một số bước đọc dữ liệu để xác định resource và policy vẫn có thể cần thiết; các bước đó phải được scope theo tenant và không làm lộ dữ liệu trái phép.

## 2. Phân biệt method authorization và resource authorization

Một kiểm tra quyền có thể có hai lớp:

- **Method-level authorization:** principal có được gọi OrderService/CancelOrder hay không?
- **Resource-level authorization:** principal có được hủy chính order được chỉ định trong request hay không?

Ví dụ, permission **orders:cancel** cho phép một nhóm caller yêu cầu hủy đơn. Nhưng đơn cụ thể có thể thuộc tenant khác, do người khác sở hữu hoặc đã ở trạng thái không thể hủy.

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Caller là ai? | service:order-operator đã được xác minh |
| Method authorization | Caller được gọi method này không? | Có orders:cancel |
| Resource authorization | Caller được thao tác trên resource này không? | Order thuộc tenant được phép |
| Business invariant | Trạng thái hiện tại có cho phép hành động không? | Order chưa được giao |

Business invariant và authorization có liên quan nhưng khác nhau. Một caller có thể có quyền hủy đơn nhưng đơn đã giao; đó là lỗi trạng thái nghiệp vụ, thường được biểu diễn bằng **FAILED_PRECONDITION**. Ngược lại, caller không có quyền hủy là **PERMISSION_DENIED**.

## 3. Luồng enforce quyền trước side effect

Một use case thay đổi dữ liệu thường đi theo trình tự:

1. Xác minh credential và tạo principal.
2. Kiểm tra quyền gọi service/method.
3. Xác định tenant từ principal hoặc xác minh tenant selector.
4. Tải resource bằng truy vấn đã scope tenant.
5. Đánh giá quyền trên resource và các thuộc tính liên quan.
6. Kiểm tra business invariant.
7. Chỉ sau khi tất cả điều kiện đạt, thực hiện mutation.
8. Commit dữ liệu và ghi outbox/event theo transaction phù hợp.
9. Trả kết quả và ghi nhận outcome.

Không phải mọi use case cần đủ chín bước. Một method đọc có thể không có mutation; một thao tác không phụ thuộc resource có thể bỏ bước tải resource. Nhưng không được đảo thứ tự để side effect xảy ra trước authorization.

Đối với resource không thuộc tenant, có thể trả **NOT_FOUND** để không tiết lộ resource có tồn tại ở tenant khác. Với resource thuộc phạm vi nhưng caller thiếu quyền, trả **PERMISSION_DENIED**. Chọn semantics nhất quán theo threat model và API contract.

## 4. Đặt authorization ở đúng lớp trong Spring gRPC

Nên phân chia trách nhiệm:

| Lớp | Trách nhiệm |
| --- | --- |
| **Authentication ServerInterceptor** | Xác minh credential, tạo principal đáng tin cậy và đặt vào io.grpc.Context |
| **Authorization ServerInterceptor** | Kiểm tra quyền tổng quát theo service/method trước khi handler chạy |
| **gRPC adapter** | Chuyển request protobuf thành command, lấy principal và gọi use case |
| **Application service/use case** | Kiểm tra quyền trên resource và điều phối business action |
| **Domain model** | Bảo vệ business invariant và chuyển trạng thái hợp lệ |
| **Repository/database** | Giới hạn dữ liệu theo tenant và hỗ trợ cập nhật an toàn |

Interceptor phù hợp với policy dùng chung cho toàn method. Ví dụ, chặn mọi caller thiếu orders:cancel trước khi CancelOrder handler được gọi. Tuy nhiên interceptor không nên chứa toàn bộ logic quyền trên resource vì request payload, trạng thái domain và dữ liệu liên quan thường chỉ được xử lý đúng ở application/domain layer.

Một method có thể đi qua cả hai lớp: interceptor kiểm tra permission chung, use case kiểm tra ownership/tenant trên resource. Không coi một trong hai lớp là thay thế hoàn toàn cho lớp còn lại.

## 5. Principal và Context: dữ liệu quyền phải đáng tin

Principal phải được tạo từ credential đã xác minh. Không lấy user_id, role, permissions hoặc tenant_id do client tự gửi rồi coi là danh tính.

Ví dụ principal tối giản:

~~~java
package dev.example.security;

import java.util.Set;

public record GrpcPrincipal(
        String subject,
        String tenantId,
        Set<String> permissions) {

    public GrpcPrincipal {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        permissions = Set.copyOf(permissions);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

Khai báo một Context key dùng chung:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Sau khi authentication xác minh token/certificate, interceptor gắn principal:

~~~java
Context context = Context.current().withValue(
        GrpcSecurityContext.PRINCIPAL,
        verifiedPrincipal);

return Contexts.interceptCall(context, call, headers, next);
~~~

Adapter hoặc application boundary có thể đọc principal từ đúng key. Nếu chuyển công việc sang executor tùy chỉnh, cần truyền Context bằng API như Context.wrap hoặc truyền principal/actor một cách tường minh. Không dựa vào ThreadLocal tự viết.

## 6. Ví dụ: kiểm tra quyền trước khi hủy đơn

Giả sử CancelOrder là một unary RPC. Interceptor đã kiểm tra permission method orders:cancel; use case vẫn cần xác minh order thuộc tenant của principal và trạng thái cho phép hủy.

~~~java
package dev.example.orders.application;

import dev.example.orders.persistence.OrderEntity;
import dev.example.orders.persistence.OrderRepository;
import dev.example.security.GrpcPrincipal;
import io.grpc.Status;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CancelOrderUseCase {

    private final OrderRepository orders;
    private final OrderResourceAuthorization authorization;
    private final OrderEventOutbox outbox;

    public CancelOrderUseCase(
            OrderRepository orders,
            OrderResourceAuthorization authorization,
            OrderEventOutbox outbox) {
        this.orders = orders;
        this.authorization = authorization;
        this.outbox = outbox;
    }

    @Transactional
    public CancelOrderResult execute(
            GrpcPrincipal principal,
            String orderId) {

        if (!principal.hasPermission("orders:cancel")) {
            throw Status.PERMISSION_DENIED
                    .withDescription("Permission denied")
                    .asRuntimeException();
        }

        OrderEntity order = orders
                .findByTenantIdAndIdForUpdate(
                        principal.tenantId(), orderId)
                .orElseThrow(() -> Status.NOT_FOUND
                        .withDescription("Order not found")
                        .asRuntimeException());

        authorization.requireCanCancel(principal, order);

        if (!order.isCancelable()) {
            throw Status.FAILED_PRECONDITION
                    .withDescription("Order cannot be cancelled")
                    .asRuntimeException();
        }

        // Business action chỉ bắt đầu sau các kiểm tra quyền và invariant.
        order.cancel();

        outbox.append(OrderCancelledEvent.from(order, principal.subject()));

        return CancelOrderResult.from(order);
    }
}
~~~

Ví dụ giả định repository có truy vấn tenant-scoped và lock phù hợp; OrderResourceAuthorization đánh giá ownership/relationship; outbox ghi event cùng transaction. Trong dự án thực tế, application service có thể ném exception nghiệp vụ riêng rồi ánh xạ sang gRPC status ở adapter/interceptor. Đưa io.grpc.Status trực tiếp vào use case là lựa chọn đơn giản cho ví dụ, không phải yêu cầu bắt buộc của kiến trúc.

Điểm quan trọng là không gọi order.cancel() hoặc outbox.append(...) trước requireCanCancel. findByTenantIdAndIdForUpdate giới hạn dữ liệu theo tenant và giữ trạng thái resource ổn định trong transaction theo cơ chế lock của database.

## 7. Tránh TOCTOU giữa kiểm tra quyền và business action

**TOCTOU** (time-of-check to time-of-use) xảy ra khi điều kiện được kiểm tra thay đổi trước lúc hành động sử dụng điều kiện đó.

Ví dụ:

1. Server đọc order ở trạng thái PENDING.
2. Policy cho phép principal hủy order khi order thuộc tenant của họ và chưa được giao.
3. Một transaction khác đồng thời chuyển order sang SHIPPED.
4. Request đầu tiếp tục hủy order dựa trên trạng thái cũ.

Kiểm tra quyền đúng ở thời điểm đầu không đủ nếu trạng thái resource thay đổi trước khi mutation commit. Cách xử lý tùy dữ liệu và mức đồng thời:

- Dùng transaction và pessimistic lock (SELECT ... FOR UPDATE) khi cần khóa resource trong lúc kiểm tra và mutation.
- Dùng optimistic locking/version để phát hiện resource đã thay đổi.
- Dùng câu lệnh update có điều kiện, chứa tenant, trạng thái và version trong WHERE.
- Với policy phụ thuộc membership/relationship có thể thay đổi, xác định mức nhất quán và thời gian hiệu lực của quyết định.

Ví dụ cập nhật có điều kiện:

~~~sql
UPDATE orders
SET status = 'CANCELLED',
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :order_id
  AND status = 'PENDING'
  AND version = :expected_version;
~~~

Nếu affected rows bằng 0, trạng thái hoặc version đã thay đổi, resource không thuộc tenant hoặc không còn thỏa điều kiện. Đọc lại trong transaction phù hợp và trả kết quả theo contract; không giả định update thành công chỉ vì authorization trước đó đã allow.

Với permission thuần túy dựa trên principal và policy bất biến trong thời gian call, TOCTOU có thể ít phức tạp hơn. Với quyền dựa trên resource state, membership hoặc quota thay đổi đồng thời, cần thiết kế tính nguyên tử rõ ràng.

## 8. Authorization trước các side effect bên ngoài

Không chỉ database write mới là business action. Một use case có thể gọi payment provider, publish event hoặc gửi email. Các side effect này không thể được hoàn tác chỉ bằng rollback transaction database.

Thứ tự an toàn:

- Xác minh principal, permission và tenant trước khi gọi downstream.
- Tải resource theo tenant và kiểm tra quyền trên resource.
- Kiểm tra trạng thái nghiệp vụ.
- Ghi thay đổi dữ liệu và outbox event trong cùng transaction nếu dùng transactional outbox.
- Worker publish event sau commit; worker xác minh service identity và tenant context trước khi xử lý tiếp.
- Với downstream call trực tiếp, cân nhắc saga/compensation và idempotency; không phát lệnh trước authorization.

Không gửi email, tạo payment intent hoặc publish event rồi mới kiểm tra quyền. Nếu authorization service bên ngoài không sẵn sàng, không thực hiện business action dựa trên giả định allow.

## 9. Idempotency và retry không được bỏ qua authorization

gRPC client hoặc gateway có thể retry. Ứng dụng cũng có thể gửi lại cùng command khi không nhận được response. Một idempotency key giúp tránh thực hiện side effect nhiều lần, nhưng nó không thay thế authorization.

Thứ tự cần bảo đảm:

1. Xác thực caller và xác định tenant.
2. Kiểm tra caller có quyền gọi operation và truy cập resource.
3. Xác định idempotency key trong phạm vi tenant/operation.
4. Nếu đã có kết quả trước đó, chỉ trả lại kết quả khi caller hiện tại vẫn được phép xem kết quả đó.
5. Nếu chưa có, thực hiện action một lần và lưu kết quả/idempotency record theo transaction phù hợp.

Scope idempotency key theo tenant và loại operation, ví dụ (tenant_id, operation, key). Không dùng key toàn cục do client cung cấp mà không ràng buộc tenant; hai tenant không được va chạm hoặc đọc kết quả của nhau.

Một caller có thể đã được phép lúc tạo command nhưng bị thu hồi quyền trước lần retry. Policy phải quyết định có kiểm tra quyền lại khi replay kết quả hay không; với dữ liệu nhạy cảm, luôn kiểm tra quyền đọc kết quả tại thời điểm trả response.

## 10. Async job và quyền tại thời điểm thực thi

Một RPC có thể chỉ tạo job để xử lý sau. Authorization trước khi enqueue là cần thiết, nhưng worker chạy sau đó có thể ở thời điểm quyền đã thay đổi.

Cần quyết định rõ job hoạt động theo mô hình nào:

- **Delegated user action:** job tiếp tục hành động thay mặt user. Lưu actor, tenant, operation và authorization context tối thiểu; worker kiểm tra lại policy tại thời điểm thực thi nếu yêu cầu thu hồi quyền có hiệu lực.
- **Service-owned operation:** job là trách nhiệm của service sau khi đã chấp nhận command hợp lệ. Worker dùng service identity riêng và chỉ có quyền tối thiểu; vẫn giữ tenant/resource scope của command.
- **Approved workflow:** thao tác cần approval. Job chỉ được thực thi sau khi có quyết định phê duyệt hợp lệ và còn hiệu lực.

Không lưu access token thô trong queue để dùng lại tùy tiện. Truyền identity/reference và tenant context theo schema nội bộ được bảo vệ; xác minh producer và quyền của worker. Nếu policy service lỗi lúc thực thi, fail-closed và giữ job ở trạng thái retry/dead-letter phù hợp, không thực hiện action.

## 11. Streaming: kiểm tra trước khi mở và trước từng action

Với server-streaming, client-streaming hoặc bidirectional streaming, một RPC có thể chứa nhiều message và kéo dài lâu.

- Kiểm tra permission gọi method trước khi tạo subscription hoặc bắt đầu xử lý.
- Với mỗi message có resource ID, kiểm tra tenant/ownership trước side effect tương ứng.
- Không cho message thay đổi tenant tùy ý nếu contract không hỗ trợ multi-tenant stream.
- Khi quyền bị thu hồi, quy định rõ revalidation, giới hạn thời lượng hoặc cancellation.
- Dừng stream và cleanup buffer/subscription khi một message bị từ chối.
- Áp quota/fairness để một tenant không chiếm tài nguyên của tenant khác.

Ví dụ UploadEvents có thể được phép ở mức method, nhưng mỗi event vẫn cần xác minh event thuộc tenant của principal trước khi ghi hoặc phát event downstream. Một lần authorize khi mở stream không tự động cho phép mọi thao tác về sau.

## 12. Status và xử lý lỗi authorization

Chọn status để phản ánh đúng loại lỗi:

| Tình huống | gRPC status thường dùng |
| --- | --- |
| Credential thiếu/sai hoặc principal không được tạo | UNAUTHENTICATED |
| Principal đã xác minh nhưng thiếu permission | PERMISSION_DENIED |
| Resource không tồn tại trong tenant được phép | NOT_FOUND |
| Resource tồn tại nhưng trạng thái không cho action | FAILED_PRECONDITION |
| Version/state conflict khi mutation | ABORTED |
| Policy dependency không thể đánh giá do lỗi hạ tầng | UNAVAILABLE hoặc status hạ tầng theo contract |

Không biến lỗi policy dependency thành allow. Cũng không nhầm "policy từ chối" với "policy service không phản hồi": trường hợp đầu là quyết định authorization, trường hợp sau là lỗi hạ tầng và có thể cần retry có kiểm soát.

Status description trả cho client nên ngắn và không tiết lộ permission nội bộ, claim, tenant membership hoặc chi tiết resource nhạy cảm. Ghi lý do chi tiết ở audit log có kiểm soát.

## 13. Audit và observability

Một quyết định authorization cần có dấu vết đủ để điều tra mà không làm lộ bí mật. Có thể ghi:

- Subject/principal ID đã chuẩn hóa.
- Tenant ID theo chính sách log.
- Full method name và resource type/ID đã được redact hoặc pseudonymize khi cần.
- Quyết định allow/deny và policy version.
- Correlation/trace ID, thời điểm và outcome của business action.
- Lý do phân loại như missing_permission, wrong_tenant, resource_state_denied.

Tách **authorization decision** khỏi **business outcome**. Một request có thể được allow nhưng business action thất bại do trạng thái hoặc dependency; ngược lại, request bị deny không được có mutation. Metrics nên nhóm theo method, status, decision và policy version có cardinality kiểm soát; tránh đưa user ID, token hoặc request ID làm label.

Audit không nên block interceptor bằng I/O chậm. Với hành động cần audit bền vững, xác định rõ liệu audit record phải commit cùng business transaction hay được publish qua outbox. Không để lỗi ghi audit vô tình biến deny thành allow.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Dữ liệu đã thay đổi nhưng client nhận PERMISSION_DENIED | Kiểm tra quyền sau mutation | Di chuyển enforcement trước side effect |
| Đã gọi payment rồi mới phát hiện thiếu quyền | Downstream call nằm trước authorization | Xác minh method/resource trước mọi external action |
| Caller có permission nhưng thao tác nhầm tenant | Chỉ kiểm tra method, không scope resource | Tenant-scoped query và resource authorization |
| Quyền đúng nhưng action dùng trạng thái cũ | TOCTOU | Transaction, lock, version hoặc conditional update |
| Retry trả lại kết quả cho caller đã mất quyền | Replay idempotency trước authorization | Reauthorize trước khi trả kết quả |
| Async job chạy bằng quyền quá rộng | Worker dùng identity của service chung | Service identity tối thiểu, tenant scope và revalidation |
| Stream tiếp tục thao tác sau khi quyền bị thu hồi | Chỉ authorize khi mở stream | Revalidation/cancellation theo policy |
| Policy dependency lỗi nhưng action vẫn chạy | Fallback allow | Fail-closed, không side effect khi decision indeterminate |
| Audit nói deny nhưng database đã commit | Audit/decision và transaction không đồng bộ | Đặt decision trước action, ghi outcome theo transaction/outbox |

## 15. Kiểm thử: deny phải đồng nghĩa không có side effect

Một test authorization không nên chỉ assert status. Nó cần chứng minh không có thay đổi dữ liệu, không có event và không có downstream call khi request bị từ chối.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Thiếu credential | UNAUTHENTICATED; use case không chạy |
| Thiếu permission method | PERMISSION_DENIED; không đọc/mutation ngoài phạm vi cần thiết |
| Sai tenant | Không trả dữ liệu; không mutation |
| Có quyền nhưng resource không thuộc caller | NOT_FOUND hoặc PERMISSION_DENIED theo contract; không side effect |
| Có quyền nhưng business state không hợp lệ | FAILED_PRECONDITION; không mutation |
| Policy service không khả dụng | Fail-closed; không gọi downstream |
| Hai mutation cạnh tranh | Một mutation phù hợp version/state; không vi phạm invariant |
| Retry cùng idempotency key | Một side effect; kết quả replay vẫn qua authorization |
| Quyền bị thu hồi trước async execution | Worker xử lý theo revalidation policy; không dùng quyền cũ ngoài thời hạn |
| Streaming message truy cập resource khác tenant | Message bị từ chối; không side effect cho resource đó |

Các kỹ thuật kiểm thử hữu ích:

1. Dùng mock/spy repository để xác nhận không gọi save/update khi deny.
2. Dùng mock downstream client để xác nhận payment/event/email không được gọi.
3. Kiểm tra database state trước và sau request bị từ chối.
4. Kiểm tra outbox không có event khi authorization fail.
5. Chạy test đồng thời để phát hiện TOCTOU và optimistic-lock conflict.
6. Gọi qua generated stub và interceptor thật trong in-process hoặc transport integration test.
7. Kiểm tra cả log/audit để chắc chắn không ghi token hay payload nhạy cảm.

## 16. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo CancelOrder unary RPC và principal chứa subject, tenant cùng permission đã xác minh.
2. Thêm interceptor kiểm tra permission orders:cancel trước khi gọi handler.
3. Trong use case, truy vấn order bằng tenant và ID, sau đó kiểm tra ownership/relationship.
4. Kiểm tra trạng thái có thể hủy trước khi gọi order.cancel().
5. Dùng transaction/lock hoặc optimistic version để ngăn trạng thái thay đổi giữa check và mutation.
6. Ghi outbox event cùng transaction; xác minh event không được tạo khi authorization deny.
7. Thêm idempotency key theo tenant/operation và kiểm tra authorization trước khi replay kết quả.
8. Viết test cho missing permission, wrong tenant, invalid state, policy unavailable, retry và concurrent mutation.

### Câu hỏi tự kiểm tra

**1. Vì sao phải kiểm tra authorization trước business action?**  
Vì side effect đã xảy ra không thể được hoàn tác chỉ bằng cách trả PERMISSION_DENIED.

**2. Method permission có đủ để hủy một order không?**  
Không. Cần kiểm tra tenant, ownership/relationship và trạng thái nghiệp vụ của order cụ thể.

**3. Có thể tải resource trước authorization không?**  
Có thể cần tải để đánh giá resource policy, nhưng phải dùng truy vấn tenant-scoped và tránh tiết lộ dữ liệu. Không mutation trước khi authorization hoàn tất.

**4. TOCTOU là gì?**  
Điều kiện thay đổi giữa thời điểm kiểm tra và thời điểm sử dụng; xử lý bằng transaction, lock, version hoặc conditional update.

**5. Idempotency key có thay authorization không?**  
Không. Phải authorize trước khi thực hiện hoặc replay kết quả, và scope key theo tenant/operation.

**6. Async worker có cần kiểm tra quyền lại không?**  
Tùy mô hình delegated action và chính sách thu hồi. Cần xác định worker thực hiện thay mặt user hay service, giữ tenant scope và revalidate khi cần.

**7. Khi policy service không phản hồi thì có được tiếp tục action không?**  
Không. Không thể đánh giá quyền thì phải fail-closed và không tạo side effect.

**8. Test nào chứng minh authorization đặt đúng chỗ?**  
Assert status từ gRPC client, đồng thời xác nhận database không đổi, outbox rỗng và downstream mock không được gọi khi deny.

## Tổng kết

Trong Spring gRPC, authorization phải được enforce trước khi use case thực hiện side effect. Authentication tạo principal đáng tin; interceptor kiểm tra quyền method; application service kiểm tra tenant và quyền trên resource; domain bảo vệ invariant; transaction/database bảo đảm mutation không dựa trên trạng thái cũ. Idempotency, async job và streaming cũng phải giữ nguyên thứ tự kiểm tra quyền trước action. Khi policy không thể đánh giá, fail-closed và không thực hiện business action. Kiểm thử cần chứng minh request bị từ chối không ghi dữ liệu, không phát event và không gọi downstream.

