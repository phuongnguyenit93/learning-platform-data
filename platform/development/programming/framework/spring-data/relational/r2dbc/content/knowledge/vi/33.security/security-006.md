# Kiểm soát quyền truy cập bản ghi và ranh giới khách thuê

Trong ứng dụng Spring Data R2DBC, xác thực người dùng mới chỉ trả lời câu hỏi “request đến từ ai?”. Ứng dụng còn phải xác định người đó được phép làm gì với bản ghi cụ thể đang được yêu cầu. Một người dùng đã đăng nhập vẫn có thể thử thay ID trên URL để đọc, sửa hoặc xóa dữ liệu của người khác. Nếu repository chỉ truy vấn theo ID mà không giới hạn tenant, chủ sở hữu hoặc quyền chia sẻ, API có thể mắc lỗi truy cập đối tượng trực tiếp (IDOR/BOLA).

**Kiểm soát quyền ở cấp bản ghi phải được thực thi tại mỗi đường đọc và ghi dữ liệu.** Tenant và principal phải được lấy từ context đã xác thực, sau đó được đưa vào predicate của query hoặc được bảo vệ thêm bằng database policy. Không dựa vào tenant_id, owner_id hay role do client tự gửi trong request body.

Spring Data R2DBC cung cấp cách xây dựng query và transaction reactive, nhưng không tự áp dụng authorization cho mọi repository method. Ứng dụng phải thiết kế ranh giới dữ liệu xuyên suốt từ Spring Security, tenant context, service, repository đến database. Bài học này tập trung vào record-level authorization và tenant isolation khi đọc, tạo, cập nhật, xóa, truy vấn quan hệ và xử lý dữ liệu bất đồng bộ.

## 1. Phân biệt authentication, authorization và tenant isolation

Ba khái niệm liên quan nhưng giải quyết các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Ai đang gửi request? | User có subject là user-42 |
| Authorization | User đó có quyền thực hiện hành động này không? | Có quyền ORDER_READ |
| Tenant isolation | Request được phép hoạt động trong phạm vi dữ liệu nào? | Chỉ dữ liệu của tenant 20 |

Record-level authorization bổ sung một câu hỏi nữa: user có quyền trên chính bản ghi này hay không? Ví dụ hai user cùng thuộc tenant 20 nhưng chỉ người tạo hoặc người được chia sẻ mới được sửa một tài liệu riêng tư.

Một request có thể vượt qua authentication nhưng vẫn phải bị từ chối vì:

- User không thuộc tenant được yêu cầu.
- User thuộc tenant nhưng không có permission cho hành động.
- User có permission chung nhưng không sở hữu bản ghi.
- Bản ghi được chia sẻ với một nhóm khác, không bao gồm user hiện tại.
- Bản ghi đã bị khóa, lưu trữ hoặc chuyển sang trạng thái không cho phép sửa.

Không nên gộp tất cả điều kiện này thành một kiểm tra role duy nhất.

## 2. IDOR/BOLA: vì sao chỉ kiểm tra đăng nhập là chưa đủ?

Giả sử API có endpoint:

~~~http
GET /api/orders/481
~~~

Controller gọi:

~~~java
return orderRepository.findById(481L);
~~~

Nếu ID 481 thuộc tenant khác hoặc user khác, repository vẫn có thể trả dữ liệu. Việc endpoint yêu cầu authentication chỉ chứng minh caller đã đăng nhập; nó không chứng minh caller có quyền đọc order 481.

Kịch bản tấn công phổ biến:

1. User A đăng nhập hợp lệ và đọc được order 481 của mình.
2. User thay ID thành 482 trong URL hoặc request body.
3. Server truy vấn theo ID mà không kiểm tra tenant/owner/ACL.
4. Server trả dữ liệu của user B hoặc tenant khác.

Đây là lỗi authorization ở cấp đối tượng. ID có thể là số tuần tự, UUID hoặc chuỗi khó đoán; thay ID vẫn là một hành vi cần được bảo vệ. UUID khó đoán không thay thế authorization.

### 2.1. Không coi ID khó đoán là quyền truy cập

UUID làm giảm khả năng dò ID tuần tự, nhưng ID có thể lộ qua log, link chia sẻ, event, email hoặc browser history. Bất kỳ ID nào client cung cấp cũng phải được kiểm tra quyền ở server.

### 2.2. Không kiểm tra quyền chỉ ở giao diện

Ẩn nút Edit hoặc không hiển thị link Delete chỉ cải thiện trải nghiệm người dùng. Attacker vẫn có thể gửi HTTP request trực tiếp bằng curl, Postman hoặc script. Quyết định cuối cùng phải được thực hiện ở backend và database.

## 3. Xây dựng tenant context từ danh tính đáng tin cậy

Tenant ID trong header, path hoặc body là thông tin client yêu cầu, không phải bằng chứng caller được phép truy cập tenant đó.

Luồng an toàn:

~~~text
HTTP request
    |
    v
Authenticate principal
    |
    v
Resolve requested tenant
    |
    v
Verify principal membership and tenant status
    |
    v
Build trusted request context
    |
    v
Authorize action and record
    |
    v
Execute tenant-scoped R2DBC query
~~~

Ví dụ user thuộc tenant 10 và tenant 20. Request chọn tenant 20 chỉ được chấp nhận sau khi server kiểm tra membership đang còn hiệu lực và user được phép hoạt động trong tenant đó.

### 3.1. Tenant context không được lấy trực tiếp từ payload

Tránh:

~~~java
public Mono<Order> create(CreateOrderRequest request) {
    Order order = new Order();
    order.setTenantId(request.tenantId());
    order.setCustomerId(request.customerId());
    return orderRepository.save(order);
}
~~~

Client có thể đổi tenantId trong JSON để tạo dữ liệu ở tenant khác.

Thay vào đó, lấy tenant đã được xác thực từ context:

~~~java
public Mono<Order> create(CreateOrderRequest request) {
    return tenantContext.currentTenantId()
            .flatMap(tenantId -> {
                Order order = Order.newOrder(
                        tenantId,
                        request.customerId(),
                        request.totalAmount());
                return orderRepository.save(order);
            });
}
~~~

Nếu endpoint cho phép administrator chọn tenant đích, đây là use case quản trị riêng. Server phải kiểm tra permission cross-tenant, ghi audit actor và tenant nguồn/đích, đồng thời giới hạn phạm vi thao tác.

### 3.2. Kiểm tra membership ở server

Một mô hình đơn giản có bảng membership:

~~~sql
CREATE TABLE tenant_memberships (
    tenant_id BIGINT NOT NULL,
    user_id VARCHAR(120) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);
~~~

Trước khi tạo tenant context, service xác nhận membership:

~~~java
public Mono<TenantContextData> resolveTenant(
        String userId,
        Long requestedTenantId) {

    return membershipRepository
            .findActiveMembership(userId, requestedTenantId)
            .switchIfEmpty(Mono.error(new TenantAccessDeniedException()))
            .map(membership -> new TenantContextData(
                    requestedTenantId,
                    userId,
                    membership.role()));
}
~~~

Không nên cache membership vô thời hạn. Khi user bị thu hồi quyền, cache cũ có thể tiếp tục cho phép truy cập. Nếu cache membership, hãy xác định TTL, invalidation và hành vi khi nguồn quyền không khả dụng.

## 4. Truyền principal và tenant trong reactive pipeline

WebFlux và Reactor có thể đổi thread trong quá trình xử lý. Không nên dựa vào ThreadLocal để lưu tenant hoặc user hiện tại. Reactor Context đi cùng subscription và phù hợp để truyền dữ liệu context trong reactive pipeline.

### 4.1. Tenant context tối giản

~~~java
public record RequestTenant(
        Long tenantId,
        String userId
) {
}

public final class TenantContext {

    public static final String KEY = "requestTenant";

    private TenantContext() {
    }

    public static Mono<RequestTenant> current() {
        return Mono.deferContextual(context -> {
            if (!context.hasKey(KEY)) {
                return Mono.error(new IllegalStateException(
                        "Trusted tenant context is missing"));
            }
            return Mono.just(context.get(KEY));
        });
    }
}
~~~

Sau khi authentication và membership check hoàn tất, filter hoặc service boundary có thể đưa object đã xác thực vào Reactor Context:

~~~java
return chain.filter(exchange)
        .contextWrite(context -> context.put(
                TenantContext.KEY,
                trustedTenant));
~~~

Đây là phác thảo về vị trí truyền context; cách triển khai WebFilter cần bảo đảm tenant được resolve trước khi business pipeline thực thi. Không lấy trustedTenant từ header mà bỏ qua bước membership authorization.

### 4.2. Reactive Security Context

Với Spring Security WebFlux, có thể lấy principal qua ReactiveSecurityContextHolder:

~~~java
public Mono<String> currentUserId() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
}
~~~

Trong ứng dụng thực tế, nên chuyển principal thành một kiểu identity ổn định có user ID, tenant membership và permission đã được xác minh. Không dùng display name hoặc email làm khóa authorization nếu chúng có thể thay đổi.

### 4.3. Context không phải nguồn dữ liệu authorization duy nhất

Reactor Context giúp truyền identity đã xác minh giữa các bước. Nó không tự bảo đảm query có tenant predicate. Repository vẫn phải dùng tenantId trong SQL, hoặc database phải áp dụng policy dựa trên context transaction.

## 5. Thiết kế schema để giữ ranh giới tenant

Trong shared schema, các bảng tenant-scoped nên có tenant_id. Các khóa và quan hệ cần bảo đảm dữ liệu không tham chiếu chéo tenant.

Ví dụ:

~~~sql
CREATE TABLE customers (
    id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(160) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_customers_tenant_id UNIQUE (tenant_id, id)
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    owner_user_id VARCHAR(120) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer_same_tenant
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, id)
);
~~~

Composite foreign key gồm tenant_id và customer_id ngăn order tenant A tham chiếu customer tenant B, ngay cả khi code ứng dụng truyền nhầm ID.

### 5.1. Unique constraint theo tenant

Nếu order number chỉ cần duy nhất trong tenant:

~~~sql
CREATE UNIQUE INDEX uk_orders_tenant_number
ON orders (tenant_id, order_number);
~~~

Nếu email phải duy nhất toàn hệ thống thì mới dùng unique constraint toàn cục. Quy tắc uniqueness cần xuất phát từ nghiệp vụ, không mặc định mọi field đều unique trong toàn database.

### 5.2. Index hỗ trợ predicate authorization

Nếu query thường dùng tenant và owner:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = :tenantId
  AND owner_user_id = :userId
  AND id = :orderId;
~~~

Index có thể phù hợp:

~~~sql
CREATE INDEX ix_orders_tenant_owner_id
ON orders (tenant_id, owner_user_id, id);
~~~

Thứ tự index cần dựa vào query thực tế và execution plan. Nếu có ACL table, cần index cho cả chiều tra cứu theo resource và theo principal.

## 6. Mọi query đọc phải có phạm vi quyền

Không nên expose repository generic findById cho các đường xử lý tenant-scoped nếu service có thể vô tình gọi mà không kiểm tra tenant.

Repository:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Mono<Order> findByIdAndTenantId(Long id, Long tenantId);

    Mono<Order> findByIdAndTenantIdAndOwnerUserId(
            Long id,
            Long tenantId,
            String ownerUserId);

    Flux<Order> findAllByTenantIdAndOwnerUserId(
            Long tenantId,
            String ownerUserId);
}
~~~

Service:

~~~java
public Mono<Order> findOwnedOrder(Long orderId) {
    return TenantContext.current()
            .flatMap(context -> orderRepository
                    .findByIdAndTenantIdAndOwnerUserId(
                            orderId,
                            context.tenantId(),
                            context.userId()));
}
~~~

Query trả empty nếu không có hàng thỏa toàn bộ điều kiện. Controller có thể trả 404 để không tiết lộ bản ghi có tồn tại ở tenant khác hay không.

### 6.1. Không tải bản ghi toàn cục rồi mới kiểm tra owner

Tránh:

~~~java
return orderRepository.findById(orderId)
        .flatMap(order -> {
            if (!order.getOwnerUserId().equals(currentUserId)) {
                return Mono.error(new AccessDeniedException("Forbidden"));
            }
            return Mono.just(order);
        });
~~~

Đoạn code này đã tải entity trước khi kiểm tra quyền. Nếu entity có dữ liệu nhạy cảm, các bước log, tracing, callback hoặc mapping trung gian có thể vô tình xử lý dữ liệu mà caller không được phép đọc. Tốt hơn là đưa tenant/owner vào predicate database ngay từ đầu.

Kiểm tra quyền sau khi tải có thể cần thiết cho một số policy phức tạp, nhưng query vẫn nên giới hạn tenant và chỉ lấy field cần thiết. Không trả entity trước khi authorization hoàn tất.

### 6.2. Query native phải tự mang điều kiện tenant

Ví dụ @Query:

~~~java
@Query("""
       SELECT *
       FROM orders
       WHERE id = :orderId
         AND tenant_id = :tenantId
         AND owner_user_id = :userId
       """)
Mono<Order> findOwnedOrder(
        @Param("orderId") Long orderId,
        @Param("tenantId") Long tenantId,
        @Param("userId") String userId);
~~~

Đối với DatabaseClient, bind các giá trị tenant và principal như parameter. Không nối giá trị user hoặc tenant trực tiếp vào chuỗi SQL.

## 7. Mọi thao tác ghi cũng phải được giới hạn

Một lỗi phổ biến là SELECT có tenant predicate nhưng UPDATE hoặc DELETE chỉ dùng ID. Attacker có thể không đọc được bản ghi nhưng vẫn sửa hoặc xóa nó nếu đoán được ID.

### 7.1. INSERT

Tenant và owner phải được gán từ context tin cậy:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return TenantContext.current()
            .flatMap(context -> {
                Order order = Order.newOrder(
                        context.tenantId(),
                        context.userId(),
                        command.customerId(),
                        command.totalAmount());
                return orderRepository.save(order);
            });
}
~~~

Nếu command chứa tenantId hoặc ownerUserId, bỏ qua các field đó hoặc từ chối request theo hợp đồng API. Client chỉ nên cung cấp dữ liệu nghiệp vụ mà họ được phép quyết định.

### 7.2. UPDATE

Conditional update nên mang tenant và quyền owner:

~~~java
@Modifying
@Query("""
       UPDATE orders
       SET status = :status,
           last_modified_at = :modifiedAt
       WHERE id = :orderId
         AND tenant_id = :tenantId
         AND owner_user_id = :userId
       """)
Mono<Integer> updateOwnedOrder(
        @Param("orderId") Long orderId,
        @Param("tenantId") Long tenantId,
        @Param("userId") String userId,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt);
~~~

Service phải kiểm tra số hàng được cập nhật. Với ID unique, số hàng mong đợi là 1. Số 0 có thể biểu thị resource không tồn tại, không thuộc tenant hoặc caller không phải owner. Có thể trả 404 chung để tránh lộ sự tồn tại; nếu API cần 403, phải có một quy trình phân biệt an toàn.

### 7.3. DELETE

DELETE cũng phải giới hạn tenant và quyền:

~~~sql
DELETE FROM orders
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND owner_user_id = :userId;
~~~

Không dựa vào việc controller đã kiểm tra quyền trước đó rồi gọi deleteById(orderId) toàn cục. Điều kiện authorization nên nằm ngay trong câu lệnh thay đổi để giảm race giữa kiểm tra và ghi.

### 7.4. Soft delete

Với soft delete:

~~~sql
UPDATE orders
SET deleted_at = :deletedAt,
    deleted_by = :userId
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND owner_user_id = :userId
  AND deleted_at IS NULL;
~~~

Mọi query đọc sau đó cần có quy tắc rõ ràng về deleted_at. Không để một endpoint quên điều kiện này rồi vô tình trả lại dữ liệu đã xóa mềm. Nếu admin có thể khôi phục, đó là permission riêng và cũng phải có tenant scope.

## 8. Quyền theo role, permission và ownership

Role thường mô tả nhóm quyền, ví dụ TENANT_ADMIN, ORDER_MANAGER hoặc MEMBER. Permission mô tả hành động cụ thể, ví dụ ORDER_READ, ORDER_UPDATE hoặc ORDER_DELETE. Ownership xác định caller có quan hệ nào với bản ghi.

Một policy có thể được diễn đạt:

~~~text
Cho phép đọc order nếu:
  user thuộc tenant của order
  AND (
      user có permission ORDER_READ_ALL
      OR user là owner
      OR order được chia sẻ với user
  )
~~~

Quyền sửa có thể chặt hơn quyền đọc:

~~~text
Cho phép sửa order nếu:
  user thuộc tenant của order
  AND (
      user có permission ORDER_UPDATE_ALL
      OR (user là owner AND order.status = DRAFT)
  )
~~~

Không nên suy ra rằng user có quyền đọc thì cũng có quyền sửa hoặc xóa.

### 8.1. Bảng permission theo tenant

Một mô hình có thể gồm:

~~~sql
CREATE TABLE tenant_roles (
    tenant_id BIGINT NOT NULL,
    user_id VARCHAR(120) NOT NULL,
    role_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, user_id, role_code)
);

CREATE TABLE role_permissions (
    role_code VARCHAR(80) NOT NULL,
    permission_code VARCHAR(100) NOT NULL,
    PRIMARY KEY (role_code, permission_code)
);
~~~

Role cần được gắn trong phạm vi tenant. Một user có thể là admin ở tenant A nhưng chỉ là member ở tenant B. Không lưu một global role rồi áp dụng cho mọi tenant nếu nghiệp vụ yêu cầu quyền theo tổ chức.

### 8.2. Reactive method security

Spring Security WebFlux hỗ trợ reactive method security. Có thể bật:

~~~java
@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Một method có thể yêu cầu permission tổng quát:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
public Mono<OrderSummary> listOrders() {
    return orderService.listCurrentTenantOrders();
}
~~~

Method security phù hợp cho coarse-grained authorization như permission gọi chức năng. Nó không tự bảo đảm từng row thuộc tenant/owner hiện tại. Repository query vẫn cần predicate tenant và record-level policy.

### 8.3. Không đặt toàn bộ authorization vào controller

Nếu chỉ kiểm tra trong controller, một service có thể được gọi từ message consumer, scheduled job hoặc endpoint khác mà bỏ qua kiểm tra. Hãy đặt quy tắc quan trọng ở application/service boundary và bảo vệ thêm ở database.

Controller vẫn có thể kiểm tra quyền endpoint, nhưng service/repository không nên giả định mọi caller đã đi qua đúng controller.

## 9. Chia sẻ bản ghi bằng ACL

Không phải mọi ứng dụng đều chỉ có owner và tenant admin. Một tài liệu có thể được chia sẻ với user hoặc nhóm cụ thể.

Ví dụ bảng ACL:

~~~sql
CREATE TABLE document_permissions (
    tenant_id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    principal_type VARCHAR(20) NOT NULL,
    principal_id VARCHAR(120) NOT NULL,
    permission_code VARCHAR(40) NOT NULL,
    PRIMARY KEY (
        tenant_id,
        document_id,
        principal_type,
        principal_id,
        permission_code
    )
);
~~~

Query đọc document có thể dùng EXISTS:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :documentId
  AND d.tenant_id = :tenantId
  AND (
      d.owner_user_id = :userId
      OR EXISTS (
          SELECT 1
          FROM document_permissions p
          WHERE p.tenant_id = d.tenant_id
            AND p.document_id = d.id
            AND p.principal_type = 'USER'
            AND p.principal_id = :userId
            AND p.permission_code IN ('READ', 'WRITE')
      )
  );
~~~

Nếu permission được kế thừa từ group, query cần xác định group membership và trạng thái group trong cùng tenant. Cần index cho document_id, principal_id và permission_code theo workload thực tế.

### 9.1. Kiểm tra quyền và ghi trong cùng thao tác

Một pattern dễ mắc race:

1. SELECT kiểm tra user có quyền WRITE.
2. Một request khác thu hồi quyền.
3. UPDATE chạy sau đó vẫn thay đổi document.

Với policy cần nhất quán chặt, có thể gộp điều kiện authorization vào UPDATE bằng EXISTS:

~~~sql
UPDATE documents d
SET title = :title,
    last_modified_at = :modifiedAt
WHERE d.id = :documentId
  AND d.tenant_id = :tenantId
  AND (
      d.owner_user_id = :userId
      OR EXISTS (
          SELECT 1
          FROM document_permissions p
          WHERE p.tenant_id = d.tenant_id
            AND p.document_id = d.id
            AND p.principal_type = 'USER'
            AND p.principal_id = :userId
            AND p.permission_code = 'WRITE'
      )
  );
~~~

Đây là authorization check được thực thi tại thời điểm ghi. Nếu policy phức tạp, hãy xác định isolation/locking cần thiết và test race giữa thu hồi quyền với update.

### 9.2. Phân biệt owner và người được chia sẻ

Không nên ghi đè owner_user_id khi một document được chia sẻ. Ownership và ACL là hai quan hệ khác nhau. Chuyển ownership là thao tác đặc biệt, cần kiểm tra quyền, cập nhật audit và có thể cần thông báo cho owner cũ/mới.

## 10. Bảo vệ truy vấn quan hệ và JOIN

Nếu order thuộc tenant 10 và customer thuộc tenant 20 do dữ liệu sai, một query join chỉ theo customer_id có thể kết hợp nhầm dữ liệu.

Query nên kiểm tra cùng tenant:

~~~sql
SELECT o.id, o.status, c.name
FROM orders o
JOIN customers c
  ON c.id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.id = :orderId
  AND o.tenant_id = :tenantId;
~~~

Composite foreign key nên ngăn dữ liệu chéo tenant ngay khi insert/update. Predicate trong join là defense in depth và làm rõ phạm vi dữ liệu của query.

### 10.1. Subquery và aggregate cũng cần tenant scope

Không chỉ bảng chính mà các bảng con trong subquery cần được giới hạn:

~~~sql
SELECT o.id,
       (
           SELECT COUNT(*)
           FROM order_items i
           WHERE i.order_id = o.id
             AND i.tenant_id = o.tenant_id
       ) AS item_count
FROM orders o
WHERE o.tenant_id = :tenantId;
~~~

Nếu join một bảng ACL hoặc membership, phải giới hạn tenant ở cả hai phía. Không để group của tenant A cấp quyền cho resource tenant B chỉ vì group ID bị trùng.

### 10.2. Bulk update và export

Bulk operation thường dễ bỏ sót authorization hơn thao tác một bản ghi. Ví dụ:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE created_at < :cutoff;
~~~

Nếu chạy trong context tenant, phải thêm tenant predicate. Nếu là job toàn hệ thống, cần identity/service permission riêng và xử lý theo batch từng tenant, có audit actor và giới hạn tài nguyên.

Export/report cũng là một data access path. Kiểm tra tenant trước khi đọc, giới hạn field, kiểm tra quyền export riêng và không tạo file dùng chung mà URL có thể truy cập chéo tenant.

## 11. Dùng Row-Level Security làm lớp bảo vệ database

Với PostgreSQL, Row-Level Security (RLS) có thể giới hạn hàng ở database ngay cả khi câu SQL của ứng dụng vô tình thiếu tenant predicate.

Ví dụ:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_policy
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)::BIGINT
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::BIGINT
);
~~~

USING giới hạn hàng có thể đọc hoặc được target bởi UPDATE/DELETE. WITH CHECK kiểm tra hàng được insert hoặc trạng thái mới sau update.

### 11.1. Thiết lập tenant trong transaction

PostgreSQL hỗ trợ set_config với is_local = true để đặt giá trị trong transaction hiện tại:

~~~sql
SELECT set_config('app.tenant_id', :tenantId, true);
~~~

Sau đó mọi query được bảo vệ bởi RLS phải chạy trên cùng transaction connection:

~~~java
public <T> Mono<T> executeForTenant(
        Long tenantId,
        Mono<T> work) {

    Mono<Void> setTenant = databaseClient
            .sql("SELECT set_config('app.tenant_id', :tenantId, true)")
            .bind("tenantId", tenantId.toString())
            .fetch()
            .rowsUpdated()
            .then();

    return transactionalOperator.transactional(
            setTenant.then(work));
}
~~~

Đây là phác thảo cần điều chỉnh theo API DatabaseClient của phiên bản dự án. Điểm bắt buộc là thiết lập context và truy vấn phải dùng cùng transaction/connection. Không chạy set_config ở connection này rồi query ở connection khác.

### 11.2. Runtime role không được bypass RLS

PostgreSQL table owner thường có thể bypass RLS, trừ khi bật FORCE ROW LEVEL SECURITY. Superuser và role có BYPASSRLS cũng bypass policy.

~~~sql
ALTER TABLE orders FORCE ROW LEVEL SECURITY;
~~~

Ứng dụng runtime nên dùng role có quyền tối thiểu, không dùng superuser hoặc migration owner. Test phải kết nối bằng role tương tự production; test bằng owner có thể tạo cảm giác sai rằng RLS đã bảo vệ dữ liệu.

### 11.3. RLS không thay thế membership authorization

RLS chỉ áp dụng policy dựa trên tenant context đã được đặt. Nếu application nhận tenant ID từ header không đáng tin cậy và đưa thẳng vào app.tenant_id, RLS sẽ bảo vệ nhầm tenant do attacker chọn.

Hãy xác thực principal và membership trước, sau đó mới thiết lập tenant context trong transaction. Nếu cần record-level owner/ACL policy, có thể mở rộng policy hoặc giữ predicate owner/ACL trong query.

## 12. Transaction và thời điểm kiểm tra quyền

Một use case có thể đọc resource, kiểm tra permission, thay đổi dữ liệu và ghi audit. Các thao tác cần nguyên tử nên dùng reactive transaction với đúng R2dbcTransactionManager/ConnectionFactory.

~~~java
@Transactional
public Mono<Document> renameDocument(
        Long documentId,
        String newTitle) {

    return TenantContext.current()
            .flatMap(context -> documentRepository
                    .findWritableDocument(
                            documentId,
                            context.tenantId(),
                            context.userId()))
            .switchIfEmpty(Mono.error(new DocumentNotFoundException()))
            .flatMap(document -> {
                document.setTitle(newTitle);
                return documentRepository.save(document);
            });
}
~~~

Ví dụ này giả định findWritableDocument áp dụng owner/ACL predicate trong query. Nếu quyền có thể bị thu hồi đồng thời và phải có hiệu lực tức thì, cần xác định mức cô lập hoặc đưa điều kiện quyền vào câu UPDATE cuối cùng.

### 12.1. Authorization check trước update có thể bị race

Kiểm tra quyền ở một query rồi update ở query khác tạo khoảng thời gian giữa check và use. Nếu policy thay đổi trong khoảng đó, update có thể dựa trên quyền đã bị thu hồi.

Các cách xử lý tùy yêu cầu:

- Gộp authorization predicate vào UPDATE/DELETE.
- Dùng transaction isolation hoặc lock phù hợp với database.
- Kiểm tra version của ACL/membership khi thực hiện ghi.
- Thiết kế quyền có hiệu lực theo snapshot transaction nếu đó là semantics chấp nhận được.

Không tăng isolation level một cách máy móc. Hãy mô tả semantics thu hồi quyền và kiểm thử cạnh tranh thực tế.

### 12.2. Không giữ transaction trong lúc chờ service ngoài

Tránh mở transaction database rồi gọi HTTP service chậm để kiểm tra permission. Điều đó giữ connection lâu và tạo thêm áp lực lên pool.

Nếu authorization phụ thuộc service ngoài, hãy xác định token/claim hoặc policy snapshot có thời hạn phù hợp, sau đó thực hiện thao tác database ngắn với predicate/transaction rõ ràng. Nếu cần phối hợp nhiều hệ thống, thiết kế workflow riêng.

## 13. Reactive method security và repository boundary

Spring Security reactive method security có thể bảo vệ method theo authority:

~~~java
@Configuration
@EnableReactiveMethodSecurity
public class SecurityConfiguration {
}
~~~

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('DOCUMENT_READ')")
public Flux<DocumentSummary> listDocuments() {
    return documentService.listVisibleToCurrentUser();
}
~~~

Annotation này bảo vệ quyền gọi chức năng. Method listVisibleToCurrentUser vẫn phải query theo tenant và ACL của user hiện tại.

### 13.1. Tránh repository là public entry point cho mọi tầng

Nếu controller, scheduled job và message consumer có thể gọi trực tiếp ReactiveCrudRepository.findById hoặc deleteById, rất dễ có đường code bỏ qua tenant/owner.

Có thể:

- Đóng gói repository trong adapter/service có tenant scope.
- Expose custom method như findVisibleToUser thay vì findById.
- Giữ repository package-private hoặc không inject trực tiếp vào controller.
- Tạo code review rule cho query trên bảng tenant-scoped.
- Bổ sung RLS làm lớp bảo vệ cuối.

Đây là biện pháp kiến trúc để giảm khả năng gọi nhầm method; nó không thay thế kiểm thử và database policy.

### 13.2. Method security không thay thế database predicate

Một method có @PreAuthorize("hasAuthority('ORDER_READ')") vẫn có thể trả order của tenant khác nếu query chỉ dùng ID. Permission chức năng và quyền trên record là hai điều kiện độc lập.

## 14. Xử lý 403 và 404 mà không làm lộ dữ liệu

HTTP status cần tuân theo hợp đồng API:

- 401 Unauthorized: chưa xác thực hoặc token không hợp lệ.
- 403 Forbidden: đã xác thực nhưng không có quyền với chức năng/tài nguyên mà server xác định được.
- 404 Not Found: resource không tồn tại trong phạm vi truy cập, hoặc API cố ý che giấu sự tồn tại của resource ngoài phạm vi.

Với tenant-scoped API, query theo tenant thường trả empty nếu ID thuộc tenant khác. Trả 404 có thể ngăn attacker dò sự tồn tại của ID ở tenant khác.

Nếu hệ thống cần phân biệt 403 cho user cùng tenant nhưng không phải owner, hãy cân nhắc thông tin nào được phép tiết lộ. Không nên chạy query toàn cục rồi trả thông báo “bản ghi có tồn tại nhưng thuộc user khác” nếu điều đó tiết lộ dữ liệu nhạy cảm.

## 15. Cache, file và message cũng phải có tenant boundary

Database query đúng vẫn chưa đủ nếu cache hoặc message bỏ tenant scope.

### 15.1. Cache key

Không dùng cache key chỉ có resource ID nếu ID có thể trùng hoặc quyền phụ thuộc tenant:

~~~text
orders:{tenantId}:{orderId}
documents:{tenantId}:{documentId}:{userId}
~~~

Với dữ liệu có ACL, cache theo tenant thôi có thể vẫn chưa đủ nếu hai user trong cùng tenant có quyền khác nhau. Cần cache key theo principal/permission scope hoặc chỉ cache dữ liệu chung rồi áp dụng authorization trước khi trả.

### 15.2. Cache không được thay thế authorization

Một cache hit không chứng minh user hiện tại có quyền đọc dữ liệu. Kiểm tra authorization trước khi trả cached object hoặc thiết kế cache chứa dữ liệu đã phân vùng theo đúng quyền.

Khi membership/ACL bị thu hồi, cần invalidation hoặc TTL phù hợp để dữ liệu không tiếp tục được phục vụ theo quyền cũ.

### 15.3. Message/event

Event tenant-scoped nên mang tenant ID và event ID. Consumer xác thực nguồn phát, dựng context đúng tenant và query theo tenant. Không tin tenant ID từ message đến từ nguồn không đáng tin cậy.

Khi publish event sau transaction, dùng outbox để lưu ý định phát event cùng dữ liệu nghiệp vụ. Consumer vẫn cần authorization/service identity và idempotency/deduplication.

### 15.4. Object storage và file export

Object key có thể dùng prefix tenant:

~~~text
tenant/20/documents/481/contract.pdf
~~~

Prefix chỉ giúp tổ chức dữ liệu; nó không phải authorization. Server phải kiểm tra quyền đọc document trước khi tạo signed URL hoặc trả file. Signed URL cần thời hạn ngắn và phạm vi object cụ thể.

## 16. Các trường hợp đặc biệt cần policy riêng

### 16.1. Tenant administrator

Tenant admin có thể đọc hoặc quản lý nhiều bản ghi trong tenant nhưng không mặc nhiên có quyền sang tenant khác. Query vẫn phải có tenant_id của tenant đang quản trị.

### 16.2. Support operator

Nhân viên hỗ trợ có thể cần truy cập tạm thời vào tenant để xử lý sự cố. Đây là quyền đặc biệt:

- Có quy trình cấp quyền và thời hạn.
- Ghi lý do, actor, tenant và resource được truy cập.
- Giới hạn read/write theo nhiệm vụ.
- Có audit trail không thể bị user thông thường sửa.
- Thu hồi quyền khi hoàn tất.

Không dùng một global SUPPORT role để bỏ toàn bộ tenant predicate.

### 16.3. Chuyển owner hoặc chuyển tenant

Chuyển ownership là hành động có quyền riêng. Chuyển resource từ tenant A sang tenant B còn phức tạp hơn vì quan hệ, foreign key, ACL, file, cache và event có thể phụ thuộc tenant.

Hãy coi thao tác chuyển tenant là workflow quản trị riêng, kiểm tra quyền ở cả nguồn và đích, cập nhật quan hệ trong transaction phù hợp và ghi audit đầy đủ. Không cho client đổi tenant_id bằng một PATCH thông thường.

### 16.4. Background job

Job nền không có user principal nhưng vẫn phải có phạm vi. Ví dụ job xử lý tenant 20 phải nhận tenant ID từ job registry đáng tin cậy và query giới hạn tenant. Actor audit có thể là system:billing-worker, kèm correlation ID.

Job toàn hệ thống cần permission/service identity riêng và nên xử lý theo từng tenant hoặc batch nhỏ, tránh một query vô tình quét toàn bộ tenant.

## 17. Những lỗi authorization thường gặp

| Lỗi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra user đã đăng nhập | IDOR/BOLA qua ID của resource khác | Kiểm tra tenant, owner hoặc ACL |
| Tin tenant_id từ body/header | User tự chọn tenant không được phép | Resolve tenant từ membership đã xác thực |
| SELECT có tenant nhưng UPDATE thiếu tenant | Có thể sửa dữ liệu tenant khác | Đưa tenant predicate vào mọi DML |
| DELETE chỉ dùng ID | Xóa được resource ngoài phạm vi | DELETE theo ID + tenant + policy |
| Dùng UUID để thay authorization | ID bị lộ vẫn truy cập được | Luôn kiểm tra quyền ở server |
| Kiểm tra quyền sau khi trả entity | Dữ liệu có thể bị xử lý/lộ trước khi kiểm tra | Query giới hạn quyền ngay từ đầu |
| Dựa vào @PreAuthorize duy nhất | Permission chức năng không giới hạn row | Predicate ở repository/database |
| Role không có tenant scope | Admin ở tenant A có quyền ở tenant B | Gắn role/membership theo tenant |
| ACL check rồi update tách rời | Quyền có thể bị thu hồi giữa check và use | Gộp EXISTS vào DML hoặc transaction policy |
| Cache key thiếu tenant/user | Trả cache của tenant hoặc user khác | Cache key theo tenant và permission scope |
| Message tin tenant ID không xác thực | Consumer ghi nhầm tenant | Xác thực producer và dựng context tin cậy |
| RLS chạy bằng table owner | Policy có thể bị bypass | Runtime role tối thiểu và FORCE RLS khi cần |
| Connection giữ tenant setting cũ | Rò context qua connection pool | Transaction-local setting và test pool reuse |
| Support role bỏ mọi filter | Truy cập cross-tenant quá rộng | Just-in-time access, scope và audit |
| Job nền query không có tenant | Quét hoặc sửa dữ liệu toàn hệ thống | Service identity và tenant batch scope |

## 18. Kiểm thử ranh giới tenant và record-level authorization

Kiểm thử cần chứng minh caller không thể đọc, tạo, sửa, xóa hoặc chia sẻ resource ngoài phạm vi, kể cả khi thay ID trong request.

### 18.1. Fixture hai tenant và hai user

Chuẩn bị:

| Identity | Tenant | Resource |
| --- | --- | --- |
| user-A | tenant-10 | order-101, owner user-A |
| user-B | tenant-10 | order-102, owner user-B |
| user-C | tenant-20 | order-201, owner user-C |

Kỳ vọng:

- user-A đọc được order-101.
- user-A không đọc được order-201.
- user-A không sửa hoặc xóa order-102 nếu không có quyền quản lý.
- user-C không đọc order-101 dù ID hợp lệ.
- Tenant admin của tenant-10 chỉ quản lý được dữ liệu tenant-10.

### 18.2. Test IDOR trên GET

Với WebTestClient:

~~~java
webTestClient.get()
        .uri("/api/orders/201")
        .headers(headers -> headers.setBearerAuth(tokenForUserA))
        .exchange()
        .expectStatus().isNotFound();
~~~

Test cần xác nhận response không chứa field của order tenant-20. Nếu API dùng 403 theo policy, hãy kiểm tra status và body không tiết lộ dữ liệu ngoài phạm vi.

### 18.3. Test INSERT không tin tenant từ client

Gửi body có tenantId = 20 trong khi token/context của caller thuộc tenant 10. Xác nhận server từ chối hoặc bỏ qua field không được phép và hàng được ghi có tenant_id = 10.

### 18.4. Test UPDATE/DELETE

Trong context user-A, gửi PATCH/DELETE với ID của order-102 hoặc order-201. Xác nhận không có hàng nào bị thay đổi/xóa và audit record không ghi một thao tác thành công giả.

Kiểm tra trực tiếp database sau request, không chỉ kiểm tra HTTP response.

### 18.5. Test quan hệ chéo tenant

Thử tạo order tenant-10 với customer ID của tenant-20. Composite foreign key phải từ chối thao tác. Test này chứng minh database constraint bảo vệ ngay cả khi service có lỗi.

### 18.6. Test ACL

Tạo document có owner user-A và ACL READ cho user-B:

- user-B đọc được nhưng không sửa được.
- user-C không đọc được.
- Sau khi thu hồi ACL, user-B không đọc được theo semantics hiệu lực đã chọn.
- Một request đang cập nhật đồng thời với thao tác thu hồi quyền có kết quả đúng theo isolation/policy đã định nghĩa.

### 18.7. Test reactive context isolation

Chạy hai request đồng thời:

- Request A có tenant 10/user-A.
- Request B có tenant 20/user-C.

Thực hiện query sau scheduler boundary hoặc các thao tác bất đồng bộ để xác nhận context không bị trộn giữa subscription. Không chỉ test tuần tự trên một thread.

### 18.8. Test RLS bằng runtime role

Nếu dùng PostgreSQL RLS:

- Kết nối bằng role ứng dụng, không phải superuser.
- Không có tenant context thì không đọc được hàng.
- Tenant 10 không đọc/ghi được tenant 20.
- INSERT với tenant_id sai bị từ chối.
- Connection được tái sử dụng không giữ tenant setting cũ.
- Kiểm tra role runtime không có BYPASSRLS.

## 19. Quy trình thiết kế access control cho một endpoint

Với mỗi endpoint đọc/ghi resource, xác định theo thứ tự:

1. Principal đã được authentication là ai?
2. Tenant nào được chọn và membership còn hiệu lực không?
3. Permission chức năng cho hành động này là gì?
4. Resource thuộc tenant nào?
5. Caller có phải owner hoặc có ACL phù hợp không?
6. Resource có trạng thái cho phép hành động không?
7. Query cuối cùng có tenant/owner/ACL predicate không?
8. Database constraint/RLS có thể ngăn truy cập sai không?
9. Response 401/403/404/409 có làm lộ thông tin ngoài phạm vi không?
10. Cache, event, export và audit có giữ cùng ranh giới không?

Một policy nên được biểu diễn rõ ràng bằng code hoặc query. Tránh các điều kiện authorization rải rác trong controller mà không thể kiểm thử độc lập.

## 20. Ví dụ service tenant-aware có kiểm tra owner

Entity:

~~~java
@Table("documents")
public class Document {

    @Id
    private Long id;

    @Column("tenant_id")
    private Long tenantId;

    @Column("owner_user_id")
    private String ownerUserId;

    private String title;

    @Column("last_modified_by")
    private String lastModifiedBy;

    @Column("last_modified_at")
    private Instant lastModifiedAt;

    public static Document create(
            Long tenantId,
            String ownerUserId,
            String title) {
        Document document = new Document();
        document.tenantId = tenantId;
        document.ownerUserId = ownerUserId;
        document.title = title;
        return document;
    }
}
~~~

Repository:

~~~java
public interface DocumentRepository
        extends ReactiveCrudRepository<Document, Long> {

    Mono<Document> findByIdAndTenantIdAndOwnerUserId(
            Long id,
            Long tenantId,
            String ownerUserId);
}
~~~

Service:

~~~java
@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<Document> findMine(Long documentId) {
        return TenantContext.current()
                .flatMap(context -> repository
                        .findByIdAndTenantIdAndOwnerUserId(
                                documentId,
                                context.tenantId(),
                                context.userId()));
    }
}
~~~

Ví dụ này chỉ cho phép owner đọc. Nếu ứng dụng có tenant admin hoặc ACL sharing, hãy đưa các nhánh policy đó vào query riêng có tên rõ ràng, chẳng hạn findVisibleToPrincipal, và kiểm thử từng nhánh. Không thêm một điều kiện OR rộng mà không có test chứng minh phạm vi.

## 21. Checklist bảo vệ record và tenant

- [ ] Principal được xác thực bằng cơ chế server tin cậy.
- [ ] Tenant được resolve và membership được kiểm tra trước khi truy cập dữ liệu.
- [ ] Không tin tenant_id/owner_id/role do client gửi.
- [ ] Tenant context được truyền bằng Reactor Context hoặc cơ chế reactive tương thích.
- [ ] Mọi SELECT trên bảng tenant-scoped có tenant predicate hoặc được bảo vệ bằng RLS.
- [ ] Mọi INSERT gán tenant và owner từ context tin cậy.
- [ ] Mọi UPDATE/DELETE có tenant và record-level policy trong predicate.
- [ ] JOIN, subquery, aggregate và bulk operation giữ tenant scope.
- [ ] Composite foreign key ngăn quan hệ chéo tenant khi phù hợp.
- [ ] Unique constraint phản ánh đúng phạm vi uniqueness của nghiệp vụ.
- [ ] Role/permission được scope theo tenant.
- [ ] Owner và ACL sharing được phân biệt rõ.
- [ ] Quyền thu hồi và race giữa authorization check với update có semantics rõ.
- [ ] Cache key và invalidation giữ tenant/user permission scope.
- [ ] Message, object storage, export và background job có tenant boundary.
- [ ] RLS dùng runtime role không bypass policy.
- [ ] Integration test có ít nhất hai tenant và nhiều user với quyền khác nhau.
- [ ] Test GET, INSERT, UPDATE, DELETE và quan hệ chéo tenant.
- [ ] Test concurrent request và reactive context isolation.

## 22. Sơ đồ quyết định quyền truy cập bản ghi

~~~mermaid
flowchart TD
    A[Nhận request] --> B[Authenticate principal]
    B --> C{Principal hợp lệ?}
    C -->|Không| D[401 Unauthorized]
    C -->|Có| E[Resolve tenant và kiểm tra membership]
    E --> F{Được vào tenant?}
    F -->|Không| G[403 hoặc 404 theo policy]
    F -->|Có| H[Kiểm tra permission chức năng]
    H --> I{Có permission?}
    I -->|Không| J[403 Forbidden]
    I -->|Có| K[Query theo tenant và record policy]
    K --> L{Có hàng được phép truy cập?}
    L -->|Không| M[404 Not Found]
    L -->|Có| N{Hành động có hợp lệ với trạng thái?}
    N -->|Không| O[409 Conflict]
    N -->|Có| P[Thực thi DML có predicate bảo vệ]
    P --> Q[Commit và ghi audit]
    Q --> R[Trả response]
~~~

## 23. Kết luận

Authentication xác định caller, nhưng không chứng minh caller có quyền trên mọi bản ghi. Trong Spring Data R2DBC, record-level authorization phải được thực hiện cho từng thao tác đọc và ghi bằng tenant, owner, permission hoặc ACL phù hợp. Tenant context cần được xây dựng từ principal đã xác thực và membership được kiểm tra, sau đó truyền theo reactive context. Không tin tenant ID hoặc owner ID do client tự gửi.

Hãy đưa tenant và quyền truy cập vào predicate của SELECT, UPDATE và DELETE; gán tenant/owner từ context khi INSERT; bảo vệ JOIN, subquery, bulk operation, cache, event và file export. Composite foreign key và Row-Level Security có thể tạo thêm lớp bảo vệ ở database, nhưng không thay thế authorization ở application. Reactive method security giúp bảo vệ chức năng, còn query vẫn phải giới hạn từng record.

Kiểm thử bằng nhiều tenant và nhiều user có quyền khác nhau. Thử thay ID, thay tenant trong body, sửa/xóa bản ghi của người khác, tạo quan hệ chéo tenant và chạy request đồng thời. Một ranh giới an toàn phải giữ được ngay cả khi client cố tình gửi ID hợp lệ nhưng không thuộc phạm vi của họ.
