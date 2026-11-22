# Tenant isolation

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích tenant isolation và các rủi ro khi nhiều tenant dùng chung một gRPC service.
- Xác định tenant từ identity đã xác minh và kiểm tra caller có quyền hoạt động trong tenant đó.
- Ngăn truy cập chéo tenant ở service/domain, repository và database.
- Truyền tenant context an toàn qua gRPC interceptor, executor và các tác vụ bất đồng bộ.
- Thiết kế cache, event, file storage và streaming không làm lẫn dữ liệu tenant.
- Xử lý trường hợp quản trị viên hoặc workload được phép truy cập nhiều tenant bằng policy tường minh.
- Kiểm thử tenant isolation bằng positive test, negative test và kiểm thử đồng thời.

## 1. Tenant isolation bảo vệ ranh giới dữ liệu nào?

Trong **SPRING_GRPC**, một service có thể phục vụ nhiều tổ chức, khách hàng hoặc đơn vị độc lập. Mỗi đơn vị là một **tenant**. Các tenant có thể dùng chung process, database, gRPC endpoint và hạ tầng, nhưng dữ liệu và thao tác của tenant này phải được cô lập khỏi tenant khác theo policy.

Ví dụ, RPC **OrderService/GetOrder** có thể nhận một order ID. Nếu server chỉ tìm đơn theo ID toàn cục, caller thuộc tenant A có thể đoán hoặc biết ID của đơn tenant B và đọc được dữ liệu. Đây là lỗi truy cập chéo tenant dù caller đã đăng nhập và có permission **orders:read**.

Tenant isolation cần bảo vệ nhiều lớp:

- **Identity:** caller đang hoạt động với tenant nào và được phép chọn tenant nào?
- **RPC authorization:** caller có được gọi method trong service này không?
- **Resource authorization:** tài nguyên được yêu cầu có thuộc tenant hoặc phạm vi được phép không?
- **Persistence:** truy vấn và ghi dữ liệu có luôn gắn tenant predicate không?
- **Infrastructure:** cache, message broker, object storage, search index và logs có giữ đúng ranh giới không?

~~~mermaid
flowchart TB
    A["gRPC request"] --> B["Authentication"]
    B --> C["Verified principal"]
    C --> D["Resolve and validate tenant"]
    D --> E["Method authorization"]
    E --> F["Tenant-scoped service"]
    F --> G["Repository query with tenant_id"]
    G --> H["Tenant data only"]
    D --> X["Reject invalid tenant"]
    E --> Y["Reject forbidden method"]
~~~

Xác thực thành công và có quyền gọi method chưa đủ để truy cập mọi tài nguyên. Tenant phải được xác định và ràng buộc với từng thao tác dữ liệu.

## 2. Tenant identity phải đến từ nguồn tin cậy

Một request có thể chứa tenant ID trong protobuf message hoặc metadata. Giá trị đó cho biết client muốn thao tác trong tenant nào; tự nó không chứng minh caller được phép truy cập tenant đó.

Có ba tình huống phổ biến:

1. **Một principal thuộc một tenant:** tenant được xác định từ claim đã xác minh hoặc mapping identity nội bộ. Client không cần tự chọn tenant.
2. **Một principal là thành viên của nhiều tenant:** client có thể gửi tenant được chọn, nhưng server phải kiểm tra tenant đó nằm trong danh sách membership/entitlement đã xác minh.
3. **Workload service-to-service:** identity của workload có thể được giới hạn vào một hoặc một nhóm tenant. Không mặc định workload nội bộ có quyền trên tất cả tenant.

Không lấy **x-tenant-id** hoặc **tenant_id** trong request làm nguồn sự thật duy nhất. Nếu kiến trúc dùng header để chọn tenant, header chỉ là **tenant selector**; server vẫn phải xác minh caller có membership hoặc permission tương ứng.

Ví dụ principal bất biến sau authentication:

~~~java
package dev.example.security;

import java.util.Set;

public record TenantPrincipal(
        String subject,
        Set<String> allowedTenantIds,
        Set<String> permissions) {

    public TenantPrincipal {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        allowedTenantIds = Set.copyOf(allowedTenantIds);
        permissions = Set.copyOf(permissions);
    }

    public boolean canAccessTenant(String tenantId) {
        return allowedTenantIds.contains(tenantId);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

allowedTenantIds phải được tạo từ credential đã xác minh hoặc membership lookup tin cậy. Với số lượng tenant lớn, không nhất thiết nhét toàn bộ danh sách vào token; có thể dùng tenant được chọn đã xác minh, membership service hoặc policy engine. Dù dùng cách nào, server phải có bằng chứng đáng tin cậy trước khi thực hiện truy vấn.

## 3. Đưa tenant context vào gRPC Context

Authentication interceptor xác minh credential và đặt principal vào **io.grpc.Context**. Các interceptor hoặc handler tiếp theo có thể đọc principal theo từng RPC.

Khai báo key dùng chung:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class TenantSecurityContext {

    public static final Context.Key<TenantPrincipal> PRINCIPAL =
            Context.key("tenant-principal");

    private TenantSecurityContext() {}
}
~~~

Sau khi credential hợp lệ, authentication layer có thể gắn principal:

~~~java
Context context = Context.current().withValue(
        TenantSecurityContext.PRINCIPAL,
        verifiedPrincipal);

return Contexts.interceptCall(context, call, headers, next);
~~~

Trong handler hoặc service, lấy principal từ đúng key:

~~~java
TenantPrincipal principal =
        TenantSecurityContext.PRINCIPAL.get();

if (principal == null) {
    throw Status.UNAUTHENTICATED
            .withDescription("Authentication required")
            .asRuntimeException();
}
~~~

Dùng cùng một Context.Key instance trong toàn bộ pipeline. Tạo hai key khác nhau dù cùng tên chuỗi sẽ không làm chúng chia sẻ giá trị.

### 3.1. Resolve tenant cho từng request

Nếu principal chỉ có một tenant, service có thể dùng tenant đó làm phạm vi thao tác. Nếu principal có nhiều tenant, request có thể chọn tenant, nhưng server phải kiểm tra membership trước khi dùng:

~~~java
package dev.example.security;

import io.grpc.Status;
import org.springframework.stereotype.Component;

@Component
public class TenantAccess {

    public String requireTenant(
            TenantPrincipal principal,
            String requestedTenantId) {

        if (principal == null) {
            throw Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException();
        }

        if (requestedTenantId == null
                || requestedTenantId.isBlank()
                || !principal.canAccessTenant(requestedTenantId)) {
            throw Status.PERMISSION_DENIED
                    .withDescription("Tenant access denied")
                    .asRuntimeException();
        }

        return requestedTenantId;
    }
}
~~~

Đoạn code giả định membership đã được nạp vào principal. Nếu phải truy vấn membership service, cần đặt deadline, cache có TTL/invalidation và xử lý lỗi theo hướng fail-closed. Không fallback sang tenant mặc định khi tenant selector thiếu hoặc không hợp lệ.

Với API chỉ cho phép một tenant trong principal, không cần nhận requested tenant ID từ client; dùng tenant đã xác minh trực tiếp sẽ giảm bề mặt sai sót.

## 4. Enforce tenant boundary ở service và repository

Một authorization interceptor có thể kiểm tra permission chung của method, nhưng thường không đọc được resource ID nằm trong protobuf request trước khi service xử lý. Vì vậy, kiểm tra tenant của tài nguyên phải nằm ở service/domain và data access layer.

Giả sử bảng orders có cột tenant_id. Repository nên yêu cầu cả tenant và resource ID:

~~~java
package dev.example.orders.persistence;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, String> {

    Optional<OrderEntity> findByTenantIdAndId(
            String tenantId,
            String id);
}
~~~

Service lấy tenant từ principal đã xác minh, sau đó dùng truy vấn có tenant predicate:

~~~java
package dev.example.orders.service;

import dev.example.orders.persistence.OrderEntity;
import dev.example.orders.persistence.OrderRepository;
import dev.example.security.TenantPrincipal;
import io.grpc.Status;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderEntity getOrder(
            TenantPrincipal principal,
            String orderId) {

        String tenantId = requireTenant(principal);

        return repository.findByTenantIdAndId(tenantId, orderId)
                .orElseThrow(() -> Status.NOT_FOUND
                        .withDescription("Order not found")
                        .asRuntimeException());
    }

    private String requireTenant(TenantPrincipal principal) {
        if (principal == null) {
            throw Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException();
        }
        if (principal.allowedTenantIds().size() != 1) {
            throw Status.PERMISSION_DENIED
                    .withDescription("Tenant selection required")
                    .asRuntimeException();
        }
        return principal.allowedTenantIds().iterator().next();
    }
}
~~~

Ví dụ service trên minh họa mô hình một tenant cho mỗi principal. Với principal đa tenant, hãy resolve tenant đã chọn bằng **TenantAccess.requireTenant(...)** trước khi gọi repository.

Tránh truy vấn theo ID trước rồi mới so sánh tenant ở Java:

~~~java
// Không dùng làm ranh giới bảo vệ chính:
OrderEntity order = repository.findById(orderId).orElseThrow();
if (!order.getTenantId().equals(tenantId)) {
    throw new AccessDeniedException("Denied");
}
~~~

Truy vấn không giới hạn tenant có thể đưa dữ liệu nhạy cảm vào memory, cache hoặc log trước khi kiểm tra. Đặt tenant predicate ngay trong truy vấn giúp giới hạn dữ liệu được đọc. Tùy chính sách chống dò ID, trả **NOT_FOUND** cho resource không tồn tại trong tenant hiện tại có thể tránh tiết lộ rằng resource tồn tại ở tenant khác; chọn status nhất quán với contract bảo mật.

## 5. Bảo vệ cả thao tác ghi và ràng buộc dữ liệu

Tenant predicate cần áp dụng cho cả read, update và delete. Với update, điều kiện tenant phải nằm trong câu lệnh hoặc điều kiện truy vấn:

~~~sql
UPDATE orders
SET status = :new_status
WHERE tenant_id = :tenant_id
  AND id = :order_id;
~~~

Nếu số dòng cập nhật bằng 0, resource không tồn tại trong tenant đó hoặc không thể được cập nhật theo điều kiện hiện tại. Không thực hiện update chỉ dựa trên ID.

Một số biện pháp ở database:

- Đặt **tenant_id NOT NULL** cho bảng thuộc tenant.
- Tạo composite index như **(tenant_id, id)** để hỗ trợ truy vấn scoped.
- Dùng unique constraint theo tenant, ví dụ **(tenant_id, external_order_number)**, nếu mã đơn chỉ cần duy nhất trong tenant.
- Thiết lập foreign key/relationship để ngăn record của tenant A tham chiếu record thuộc tenant B.
- Cân nhắc Row-Level Security (RLS) nếu database hỗ trợ và ứng dụng có thể thiết lập tenant context an toàn trong transaction.

Nếu dùng PostgreSQL RLS với session variable, phải đặt tenant trong đúng transaction và bảo đảm connection pool không giữ context của request trước. Dùng transaction-local setting, reset an toàn và test reuse connection. RLS là lớp phòng vệ bổ sung; application vẫn phải xác minh tenant và permission.

## 6. Tenant isolation trong cache, search và object storage

Ranh giới tenant không dừng ở database. Một truy vấn đã scoped vẫn có thể làm lộ dữ liệu nếu cache key hoặc storage path không chứa tenant.

| Thành phần | Quy tắc cô lập |
| --- | --- |
| **Cache** | Đưa tenant vào key, ví dụ tenant:{tenantId}:order:{orderId} |
| **Search index** | Filter tenant bắt buộc ở mọi query; không chỉ dựa vào filter do client gửi |
| **Object storage** | Xác minh tenant trước khi tạo/đọc object; dùng namespace/path có tenant |
| **Idempotency key** | Scope key theo tenant và operation để tenant khác không va chạm |
| **Distributed lock** | Gắn tenant vào lock name nếu thao tác thuộc tenant |
| **Export/report** | Kiểm tra tenant trước khi tạo file và khi tải file |
| **Metrics/logs** | Hạn chế dữ liệu tenant; không đưa tenant ID cardinality cao vào metric label |

Ví dụ cache key:

~~~java
String cacheKey =
        "tenant:" + tenantId + ":order:" + orderId;
~~~

Nếu cache chỉ dùng order ID, một tenant có thể nhận kết quả đã được cache bởi tenant khác trong trường hợp ID không toàn cục hoặc cache namespace dùng chung. Tenant phải là một phần của identity dữ liệu ở mọi tầng.

Với object storage, không cho client tự chọn path tùy ý. Server xác minh quyền rồi tạo key theo tenant và resource, đồng thời kiểm tra quyền ở bước tải xuống. Signed URL cũng phải có thời hạn ngắn, phạm vi object cụ thể và chỉ được cấp sau authorization.

## 7. Tenant context qua async processing và message broker

gRPC Context có thể được truyền qua callback của grpc-java, nhưng không tự động lan truyền qua mọi executor, thread pool hoặc message broker.

Khi chuyển việc sang executor riêng, bọc tác vụ bằng Context:

~~~java
Context current = Context.current();

executor.execute(current.wrap(() -> {
    TenantPrincipal principal =
            TenantSecurityContext.PRINCIPAL.get();

    processTenantWork(principal);
}));
~~~

Khi publish event, tenant cần được gắn vào event envelope theo schema nội bộ đã kiểm soát:

~~~json
{
  "eventId": "evt-123",
  "tenantId": "tenant-a",
  "eventType": "OrderCreated",
  "aggregateId": "order-42"
}
~~~

Consumer không nên tin tenant field chỉ vì nó xuất hiện trong payload. Cần xác thực producer/channel, kiểm tra tenant có phù hợp với workload và event subscription, rồi dùng tenant đó để scope mọi truy vấn. Nếu broker topic tách theo tenant, vẫn cần xác minh quyền publish/consume và tránh để tenant A publish event giả mang tenant B.

Outbox, retry queue, dead-letter queue và scheduled job cũng phải giữ tenant context. Nếu mất tenant khi retry, tác vụ có thể chạy với tenant mặc định hoặc sai tenant.

## 8. Tenant isolation cho streaming RPC

Một streaming RPC có thể tồn tại lâu và xử lý nhiều message. Kiểm tra tenant khi mở stream chỉ đủ khi toàn bộ stream được ràng buộc với đúng một tenant và mọi message đều tuân theo ràng buộc đó.

- Xác định tenant từ principal hoặc tenant selector đã được xác minh khi mở stream.
- Nếu message có resource ID, truy vấn resource với tenant predicate ở mỗi message.
- Không cho client thay tenant giữa stream nếu contract không hỗ trợ rõ ràng.
- Khi stream phục vụ nhiều tenant, yêu cầu policy đa tenant riêng và kiểm tra từng tenant/resource.
- Khi permission hoặc membership bị thu hồi, quyết định có revalidate theo chu kỳ hay hủy stream.
- Cleanup subscription, buffer và worker khi client cancel hoặc quyền bị từ chối.

Ví dụ server-streaming **WatchOrder** nên tạo subscription bằng cặp **(tenantId, orderId)**, không chỉ order ID. Nếu stream nhận command cho nhiều order, từng command phải được xác minh tenant trước khi thực hiện side effect.

Flow control và cancellation cũng liên quan tới isolation: một tenant không nên chiếm toàn bộ buffer hoặc worker của các tenant khác. Có thể đặt quota, giới hạn stream đồng thời và fairness theo tenant để ngăn noisy neighbor.

## 9. Trường hợp truy cập nhiều tenant và cross-tenant administration

Một số actor có nhu cầu hợp lệ để truy cập nhiều tenant, chẳng hạn support agent, operator hoặc hệ thống quản trị. Đây là quyền đặc biệt và cần policy tường minh.

- Principal phải có permission riêng như **tenants:support** hoặc **tenants:admin**.
- Tenant mục tiêu vẫn phải được chọn và xác minh membership/assignment.
- Mọi thao tác cross-tenant phải được audit với subject, tenant mục tiêu, method, resource và lý do.
- Giới hạn method được phép; quyền support đọc dữ liệu không mặc nhiên bao gồm export hoặc sửa dữ liệu.
- Có thể yêu cầu step-up authentication hoặc approval cho thao tác nhạy cảm.
- Không dùng tenant wildcard hoặc tenant mặc định như cách bỏ qua kiểm tra.

Với service-to-service, workload có thể được cấp danh sách tenant cụ thể hoặc permission xử lý một nhóm tenant. Scope phải được giới hạn theo mục đích và audience; certificate hợp lệ chỉ xác minh workload identity, không tự cấp quyền mọi tenant.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| User tenant A đọc được order tenant B | Query chỉ dùng resource ID | Bắt buộc tenant predicate ở repository |
| Request có tenant khác nhưng vẫn được xử lý | Tin tenant ID hoặc header do client gửi | Kiểm tra membership với principal đã xác minh |
| Cache trả dữ liệu của tenant khác | Cache key không có tenant | Namespace key theo tenant và resource |
| Update/delete xuyên tenant | Câu lệnh chỉ lọc theo ID | Đưa tenant vào WHERE clause và kiểm tra affected rows |
| Search trả kết quả lẫn tenant | Thiếu mandatory tenant filter | Áp filter server-side trên mọi query |
| Async task chạy sai tenant | Context không được truyền sang executor | Dùng Context.wrap hoặc event envelope có xác minh |
| Event tenant B được xử lý như tenant A | Consumer tin tenant trong payload | Xác minh producer và scope tenant trước xử lý |
| Streaming đọc resource ngoài tenant | Chỉ kiểm tra tenant lúc mở stream | Kiểm tra từng resource/message |
| Connection pool giữ tenant cũ | DB session variable không được reset | Dùng transaction-local context và test connection reuse |
| Support agent truy cập quá rộng | Cross-tenant permission không giới hạn method | Tách permission, scope, approval và audit |

Khi điều tra, lần theo tenant từ credential đã xác minh tới Context, tenant resolver, service, repository query và cache/storage key. Đừng chỉ kiểm tra request có gửi đúng tenant ID; cần chứng minh server đã ràng buộc tenant đó với principal và mọi tầng dữ liệu.

## 11. Kiểm thử tenant isolation

Kiểm thử cần chứng minh tenant A không thể đọc, sửa, xóa, tìm kiếm hoặc nhận event của tenant B. Một số test cốt lõi:

| Test | Kỳ vọng |
| --- | --- |
| Principal A đọc order A | Thành công |
| Principal A đọc order B bằng ID hợp lệ | Không trả dữ liệu B |
| Principal A gửi tenant selector B nhưng không có membership | PERMISSION_DENIED |
| Principal nhiều tenant chọn tenant được cấp | Thành công theo policy |
| Principal thiếu tenant identity | Từ chối; không fallback tenant mặc định |
| Update/delete bằng ID của tenant khác | Không có row bị thay đổi |
| Cache cùng resource ID ở hai tenant | Hai key và hai kết quả tách biệt |
| Search query thiếu tenant filter từ client | Server vẫn áp tenant filter |
| Event tenant B đến consumer chỉ được phép A | Bị từ chối hoặc cách ly |
| Stream của tenant A gửi resource B | Message bị từ chối, stream cleanup đúng |
| Hai request đồng thời khác tenant | Không trộn Context, response hoặc cache |
| Connection DB được tái sử dụng | Không còn tenant setting của transaction trước |

Nên dùng test data có cùng resource ID ở hai tenant nếu schema cho phép; điều này phát hiện giả định sai rằng ID luôn toàn cục. Với database, kiểm tra trực tiếp SQL/repository behavior và affected rows. Với cache, broker và storage, kiểm thử key/namespace riêng. Bổ sung integration test qua gRPC runtime để xác minh interceptor, Context và service cùng thực thi đúng.

## 12. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo **TenantPrincipal** chứa subject, allowed tenant IDs và permissions đã xác minh.
2. Tạo shared gRPC Context key và gắn principal trong authentication interceptor.
3. Viết **TenantAccess** để xác minh tenant selector với membership của principal.
4. Tạo repository method **findByTenantIdAndId** và không dùng lookup theo ID đơn lẻ cho resource thuộc tenant.
5. Thêm tenant predicate vào update/delete và composite uniqueness cho dữ liệu có phạm vi tenant.
6. Đưa tenant ID vào cache key, object storage key và event envelope; xác minh ở consumer.
7. Với **WatchOrder**, kiểm tra tenant cho mỗi resource và cleanup khi cancellation/deny.
8. Viết integration test cross-tenant read/write, cache collision, async context và concurrent calls.

### Câu hỏi tự kiểm tra

**1. Tenant ID trong request có chứng minh caller thuộc tenant đó không?**  
Không. Nó chỉ là tenant selector. Server phải xác minh caller có membership hoặc permission cho tenant đó.

**2. Vì sao repository cần nhận cả tenant ID và resource ID?**  
Để giới hạn dữ liệu ngay trong truy vấn, tránh đọc resource của tenant khác rồi mới kiểm tra ở Java.

**3. Có thể chỉ dùng authorization interceptor để bảo vệ tenant không?**  
Không đầy đủ. Interceptor kiểm tra quyền chung của method; resource/tenant cần được ràng buộc ở service và data access layer.

**4. Vì sao tenant phải nằm trong cache key?**  
Để cùng một resource key hoặc ID không làm dữ liệu tenant này được trả cho tenant khác.

**5. Khi dùng database RLS với connection pool cần chú ý gì?**  
Tenant setting phải gắn với transaction và được reset an toàn; không để connection tái sử dụng mang tenant context cũ.

**6. Một lần kiểm tra tenant lúc mở streaming RPC có đủ không?**  
Chỉ đủ nếu stream bị ràng buộc một tenant và mọi message tuân theo ràng buộc. Nếu message tham chiếu resource khác, cần kiểm tra theo từng message.

**7. Support agent có thể truy cập mọi tenant không?**  
Chỉ khi policy cấp quyền cross-tenant rõ ràng, giới hạn method/resource và audit từng thao tác.

**8. Làm sao chứng minh tenant A không đọc được dữ liệu tenant B?**  
Gọi cùng RPC với principal A và ID tài nguyên B, xác minh không có dữ liệu trả về, không có side effect và mọi cache/query đều có tenant scope.

## Tổng kết

**Tenant isolation** bảo đảm caller chỉ thao tác trên dữ liệu thuộc tenant mà identity đã xác minh cho phép. Trong Spring gRPC, authentication tạo principal và Context; tenant selector từ request chỉ được dùng sau khi kiểm tra membership. Service/repository phải đưa tenant vào mọi truy vấn đọc/ghi, còn cache, search, object storage, event và streaming cũng phải giữ cùng ranh giới. Quyền gọi method không thay thế resource authorization. Các trường hợp cross-tenant cần permission riêng, giới hạn và audit. Kiểm thử chéo tenant, đồng thời và connection reuse giúp phát hiện những đường rò rỉ mà một bài test RPC đơn lẻ có thể bỏ sót.

