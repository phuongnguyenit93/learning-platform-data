# Xác định tổ chức hiện tại và truyền ngữ cảnh qua tác vụ xử lý

Trong phần mềm phục vụ **nhiều tổ chức** (*multi-organization*, thường được triển khai dưới dạng *multi-tenancy*), một người dùng có thể thuộc nhiều doanh nghiệp, chi nhánh hoặc workspace. Cùng một endpoint `GET /orders/123` phải trả về dữ liệu của **đúng tổ chức hiện hành**, ngay cả khi hai tổ chức đều có Order ID 123 trong những database/schema khác nhau. Một job nhập dữ liệu, một tác vụ `@Async` hay một message consumer cũng phải biết đang xử lý cho tổ chức nào.

Khó khăn không dừng ở việc thêm `organization_id` vào bảng. Hệ thống cần làm đúng ba việc:

1. **Xác định** tổ chức mà request/tác vụ thực sự muốn xử lý.
2. **Ủy quyền**: kiểm tra actor hoặc service account có quyền thực hiện thao tác trong tổ chức ấy.
3. **Truyền ngữ cảnh an toàn** qua các ranh giới: HTTP request, Spring service, Hibernate `Session`, transaction, executor thread, batch job, message queue và downstream service.

Nếu sai, hậu quả có thể là **rò rỉ dữ liệu giữa tổ chức**, ghi nhầm database/schema, đọc nhầm cache, hoặc một worker dùng ngữ cảnh còn sót lại của tác vụ trước.

Bài học thuộc chương **Nhiều tổ chức** trong Hibernate/JPA. Các ví dụ dùng Java hiện đại, Spring Boot/Spring Security, Hibernate/JPA và một số đoạn SQL. Chúng minh họa hợp đồng kiến trúc; cách khai báo cụ thể của Hibernate multi-tenancy và các API hỗ trợ phụ thuộc phiên bản đang sử dụng.

## 1. Phân biệt tổ chức, người dùng và tenant

Trong nhiều ứng dụng SaaS:

- **Organization**: đơn vị nghiệp vụ sở hữu hoặc được phép truy cập một tập dữ liệu.
- **User/actor**: người hoặc dịch vụ thực hiện yêu cầu.
- **Membership**: quan hệ giữa actor và organization, kèm vai trò và quyền.
- **Current organization**: tổ chức được chọn cho **một tác vụ cụ thể**, không mặc nhiên là mọi tổ chức mà actor có quyền.
- **Tenant identifier**: khóa dùng ở tầng persistence để cách ly dữ liệu. Có thể trùng organization ID, nhưng không bắt buộc.
- **Organization context**: đối tượng bất biến chứa định danh tổ chức và metadata liên quan để xử lý tác vụ.

Ví dụ:

~~~text
User: user-17
Memberships:
    org-A -> ADMIN
    org-B -> VIEWER

Request:
    actor = user-17
    selected organization = org-B
    action = DELETE ORDER
~~~

Người dùng có membership với `org-B` nhưng chỉ có quyền VIEWER. Do đó resolver có thể xác định `org-B` là tổ chức được chọn, nhưng **authorization của thao tác DELETE vẫn phải từ chối**.

### 1.1. Tổ chức hiện tại không phải thuộc tính cố định của user

Một user có thể chuyển qua lại giữa nhiều organizations trong UI. Nếu backend lưu một biến global:

~~~java
static String currentOrganizationId;
~~~

thì request đồng thời của hai người dùng có thể đọc nhầm giá trị, tạo lỗi cross-tenant nghiêm trọng.

**Current organization là ngữ cảnh theo tác vụ/request/transaction**, không phải singleton state dùng chung.

### 1.2. Organization ID khác database/schema ID

Ví dụ:

~~~text
organizationId = "org-42"
tenantKey      = "tenant-zone-03"
schema         = "tenant_0042"
database       = "cluster-eu-2"
~~~

Một organization có thể được chuyển giữa database clusters mà business ID không đổi. Nên tách:

- Identity nghiệp vụ `organizationId`.
- Routing metadata `TenantRoute`: datasource, schema, shard.
- Authorization scope.

Không cho client truyền trực tiếp schema/database name rồi đưa vào SQL identifier mà không whitelist/mapping server-side.

## 2. Luồng đầy đủ từ HTTP tới Hibernate

~~~mermaid
flowchart TD
    A["HTTP request: selected org"] --> B["Authentication: ai đang gọi?"]
    B --> C["Resolve requested organization"]
    C --> D{"Có membership/quyền?"}
    D -->|"Không"| E["403 / từ chối"]
    D -->|"Có"| F["Verified OrganizationContext"]
    F --> G["Gắn context cho request scope"]
    G --> H["Service / transaction boundary"]
    H --> I["Hibernate tenant resolver + connection routing"]
    I --> J["Query với tenant isolation"]
    J --> K["Commit / rollback"]
    K --> L["Clear context trong finally"]
~~~

Đối với worker async hoặc message consumer, cần thiết lập một đường tương tự, nhưng **không dựa vào HTTP request scope còn tồn tại**.

### 2.1. Ba lớp bảo vệ

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Authentication | Xác nhận actor là ai | Spring Security principal, service identity |
| Authorization | Xác nhận actor được thao tác trên organization nào | Membership + role + policy |
| Data isolation | Ngăn SQL/ORM chạm sang organization khác | `organization_id` filter, Hibernate tenant routing, RLS hoặc DB/schema-per-tenant |

Có một lớp không thay thế hai lớp còn lại. Query có tenant filter nhưng authorization sai vẫn có thể lộ dữ liệu; authorization đúng nhưng query quên tenant predicate cũng có thể lộ dữ liệu.

### 2.2. Fail closed

Khi không xác định được tổ chức trong thao tác bắt buộc tenant, **phải từ chối**. Không được tự chọn organization đầu tiên trong database hoặc dùng một tenant chung như mặc định.

Đặc biệt nguy hiểm:

~~~java
String tenant = OrganizationContextHolder.getOrNull();

if (tenant == null) {
    tenant = "default";
}
~~~

Nếu `default` chứa dữ liệu thật, một lỗi propagation trở thành truy cập nhầm dữ liệu. Hãy báo lỗi rõ ràng thay vì tiếp tục sai scope.

## 3. Những nguồn có thể cung cấp organization ID

Một ứng dụng có thể nhận lựa chọn tổ chức từ:

- URL: `/organizations/{orgId}/orders`.
- Header: `X-Organization-Id: org-42`.
- Subdomain: `org-42.example.com`.
- JWT claim chứa active organization hoặc danh sách memberships.
- Session state do server quản lý.
- ID organization trong message payload.
- Scheduler configuration hoặc job record.
- Organization được suy ra từ resource đang thao tác.

### 3.1. Một giá trị được gửi không tự là giá trị được tin cậy

~~~http
GET /orders
Authorization: Bearer <token>
X-Organization-Id: org-admin
~~~

Client có thể sửa header. Header chỉ là **lựa chọn được đề xuất**; server phải kiểm tra membership và quyền trước khi biến nó thành verified context.

Tương tự, URL, subdomain và JSON message không được mặc định tin cậy.

### 3.2. Chọn một nguồn có thẩm quyền, định nghĩa xung đột

Nếu URL cho biết `org-A` nhưng header ghi `org-B`, nên:

- Có quy tắc chọn một nguồn chính và bỏ nguồn kia, hoặc
- Từ chối request vì không nhất quán.

Không dùng URL cho service A, header cho repository B và JWT claim cho cache C mà không có contract. Những tầng khác nhau có thể vô tình truy cập những organizations khác nhau.

### 3.3. JWT có danh sách membership có đủ chưa?

JWT ký hợp lệ có thể chứa claims như:

~~~json
{
  "sub": "user-17",
  "organizations": [
    { "id": "org-A", "role": "ADMIN" },
    { "id": "org-B", "role": "VIEWER" }
  ]
}
~~~

Nhưng cần cân nhắc:

- Token đã hết hạn/chưa được xác minh chữ ký?
- Membership vừa bị thu hồi nhưng JWT vẫn còn hạn?
- Token issuer/audience có đáng tin?
- Vai trò có đủ cho **operation hiện tại**?
- Một organization có bị khóa/suspended không?

Có thể dùng claims như tín hiệu, nhưng authorization policy phải xác định độ mới/cơ chế revocation của membership, đặc biệt với thao tác nhạy cảm.

## 4. Thiết kế OrganizationContext bất biến

Một context tối thiểu:

~~~java
package com.example.tenant;

public record OrganizationContext(
    String organizationId,
    String actorId,
    String correlationId
) {
    public OrganizationContext {
        if (organizationId == null || organizationId.isBlank()) {
            throw new IllegalArgumentException(
                "organizationId là bắt buộc");
        }
        if (actorId == null || actorId.isBlank()) {
            throw new IllegalArgumentException(
                "actorId là bắt buộc");
        }
    }
}
~~~

Nên chứa **định danh đã xác minh**, không chứa toàn bộ JPA entity `Organization`, `User` hoặc `EntityManager`.

### 4.1. Vì sao immutable?

Context không nên bị thay đổi một phần giữa lúc ORM đang thực thi SQL. Một record bất biến giúp tránh lỗi:

~~~text
transaction bắt đầu với org-A
  -> code vô tình đổi context.organizationId thành org-B
  -> query tiếp theo chuyển sang tenant khác
~~~

Việc đổi organization giữa một transaction là một thao tác khác hẳn việc cập nhật field thông thường. Nên mở transaction/session riêng nếu thực sự cần xử lý organization khác.

### 4.2. Context không phải chứng chỉ quyền truy cập

Một `OrganizationContext("org-A", "user-17", ...)` có thể được lập bởi code bất kỳ nếu constructor public. Do đó **sự tồn tại của object không tự chứng minh authorization**.

Phân biệt:

- `RequestedOrganization`: ID do client cung cấp.
- `VerifiedOrganizationContext`: kết quả của authentication/authorization.
- `TenantRoutingKey`: khóa được server ánh xạ từ organization.

Có thể dùng type riêng hoặc factory nội bộ để tránh gọi nhầm. Dù vậy, authorization vẫn phải được thực thi tại trust boundary.

## 5. Resolver và membership authorization

Một service nhận actor đã xác thực và org được đề xuất:

~~~java
@Service
public class OrganizationSelectionService {

    private final OrganizationMembershipService membership;

    public OrganizationSelectionService(
            OrganizationMembershipService membership) {
        this.membership = membership;
    }

    public OrganizationContext select(
            String authenticatedUserId,
            String requestedOrganizationId,
            String correlationId) {

        if (requestedOrganizationId == null
                || requestedOrganizationId.isBlank()) {
            throw new MissingOrganizationException();
        }

        OrganizationAccess access =
            membership.requireActiveMembership(
                authenticatedUserId,
                requestedOrganizationId
            );

        // Chính sách action-level sẽ kiểm tra quyền riêng
        // khi thực thi use case, ví dụ VIEW_ORDER hoặc DELETE_ORDER.
        return new OrganizationContext(
            access.organizationId(),
            authenticatedUserId,
            correlationId
        );
    }
}
~~~

Các kiểu `OrganizationMembershipService`, `OrganizationAccess` và exception ở trên là abstractions ứng dụng. Quan trọng là membership check **không được phụ thuộc vào tenant context chưa được xác định**, nếu không dễ rơi vào vòng lặp:

~~~text
Cần tenant để query membership
  -> cần membership để biết tenant nào hợp lệ
~~~

### 5.1. Bootstrap authorization ở đâu?

Thường có một **identity/organization catalog** chung, hoặc một nguồn membership đã xác minh:

~~~text
Global identity database:
    users
    organizations
    memberships
    roles
    tenant-routing-map

Tenant-bound operational database:
    orders
    invoices
    inventory
~~~

Resolver xác minh organization qua global catalog, rồi mới mở tenant-scoped EntityManager/transaction cho dữ liệu nghiệp vụ.

### 5.2. Không phải mọi endpoint có cùng permission

Membership viewer có thể đọc đơn nhưng không được xóa đơn. Context selection không thay thế action-level authorization:

~~~java
authorization.requirePermission(
    context.actorId(),
    context.organizationId(),
    Permission.DELETE_ORDER
);
~~~

Cũng cần kiểm tra resource ownership: ID Order được yêu cầu có thuộc organization đó không?

### 5.3. Khi thiếu orgId?

Nếu một user có đúng một organization, sản phẩm có thể định nghĩa default selection do server quyết định. Nhưng phải là **business rule tường minh và được xác minh**, không phải fallback âm thầm khi context propagation bị lỗi.

Với các thao tác mutation/cross-tenant risk cao, thường nên yêu cầu lựa chọn org rõ ràng.

## 6. ThreadLocal để lưu ngữ cảnh theo thread

Trong ứng dụng HTTP Servlet đồng bộ, một cách triển khai thường gặp là `ThreadLocal`:

~~~java
package com.example.tenant;

public final class OrganizationContextHolder {

    private static final ThreadLocal<OrganizationContext> CURRENT =
        new ThreadLocal<>();

    private OrganizationContextHolder() {}

    public static OrganizationContext require() {
        OrganizationContext context = CURRENT.get();
        if (context == null) {
            throw new IllegalStateException(
                "Chưa thiết lập organization context");
        }
        return context;
    }

    public static OrganizationContext currentOrNull() {
        return CURRENT.get();
    }

    public static void set(OrganizationContext context) {
        if (context == null) {
            throw new IllegalArgumentException("context");
        }
        CURRENT.set(context);
    }

    public static void clear() {
        CURRENT.remove();
    }

    public static void runWith(
            OrganizationContext context,
            Runnable action) {

        OrganizationContext previous = CURRENT.get();
        try {
            set(context);
            action.run();
        } finally {
            if (previous == null) {
                clear();
            } else {
                set(previous);
            }
        }
    }
}
~~~

### 6.1. Vì sao cần finally?

Web servers dùng **thread pool**. Một worker thread xử lý request org-A rồi có thể được tái sử dụng cho org-B.

Nếu context không bị xóa:

~~~text
Thread worker-7:
  Request 1: org-A → CURRENT=org-A
  Request 1 kết thúc nhưng không clear
  Request 2: thiếu header → vô tình dùng org-A
~~~

Đây không chỉ là memory leak; có thể là **cross-tenant data leak**.

### 6.2. Vì sao runWith() lưu và khôi phục previous?

Trong một số code paths có nested scopes:

~~~java
OrganizationContextHolder.runWith(contextA, () -> {
    // Scope A
    OrganizationContextHolder.runWith(contextB, () -> {
        // Scope B
    });
    // Khôi phục A
});
~~~

Khôi phục giá trị trước giúp tránh phá context của outer scope. Tuy nhiên, **không nên tùy ý đổi tenant trong cùng active Hibernate Session/transaction**; nested scope chỉ là cơ chế quản lý trạng thái thread, không tự bảo đảm persistence isolation.

### 6.3. ThreadLocal không tự lan sang thread khác

~~~java
OrganizationContextHolder.set(contextA);

new Thread(() -> {
    OrganizationContext current =
        OrganizationContextHolder.currentOrNull();
    // Thông thường null, không tự thừa hưởng contextA.
}).start();
~~~

Nếu dùng `InheritableThreadLocal` cũng không giải quyết tốt thread pools: worker được tạo ở thời điểm khác và tái sử dụng, dễ nhận context cũ. Với executors, nên **capture–install–clear** rõ ràng cho từng task hoặc truyền context như tham số.

### 6.4. ThreadLocal chỉ là carrier, không phải security model

Một đoạn code có quyền gọi `set()` có thể gắn context giả nếu trust boundary không rõ. Cần bảo đảm chỉ entry point đã xác minh mới thiết lập context cho operations nhạy cảm; xử lý đủ authorization và tenant-level data isolation.

## 7. Servlet filter thiết lập và dọn ngữ cảnh

Một Spring Web filter là vị trí tự nhiên để bao quanh xử lý HTTP đồng bộ.

~~~java
@Component
public class OrganizationContextFilter
        extends OncePerRequestFilter {

    private final OrganizationSelectionService selection;

    public OrganizationContextFilter(
            OrganizationSelectionService selection) {
        this.selection = selection;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext()
                .getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()) {
            response.sendError(401, "Unauthenticated");
            return;
        }

        String requestedOrg =
            request.getHeader("X-Organization-Id");

        OrganizationContext verified =
            selection.select(
                authentication.getName(),
                requestedOrg,
                request.getHeader("X-Correlation-Id")
            );

        OrganizationContextHolder.runWith(verified, () -> {
            try {
                chain.doFilter(request, response);
            } catch (IOException | ServletException ex) {
                throw new FilterInvocationFailure(ex);
            }
        });
    }
}
~~~

Đây là **ví dụ luồng**, không phải filter production copy-paste: `FilterInvocationFailure` là wrapper runtime giả định, cần chuyển exception về đúng kiểu HTTP và xử lý `401/403`. Quan trọng hơn, phải cấu hình **filter order** để Spring Security đã xác thực principal trước khi filter đọc `SecurityContextHolder` và trước khi bất kỳ tenant-bound persistence operation nào xảy ra.

### 7.1. Phiên bản tối giản với try/finally

Có thể viết chính ý tưởng rõ hơn như sau:

~~~java
OrganizationContext previous =
    OrganizationContextHolder.currentOrNull();

try {
    OrganizationContextHolder.set(verified);
    chain.doFilter(request, response);
} finally {
    if (previous == null) {
        OrganizationContextHolder.clear();
    } else {
        OrganizationContextHolder.set(previous);
    }
}
~~~

`try/finally` đảm bảo không giữ context khi exception xảy ra.

### 7.2. Filter ordering là thiết kế, không phải chi tiết phụ

Không được để một tenant-bound JPA query chạy **trước** khi org context đã được thiết lập. Điều này liên quan:

- Authentication filters.
- Custom organization filter.
- `OpenEntityManagerInView` hoặc các resource filters.
- Interceptors mở transaction sớm.
- Request-body deserialization có truy cập DB.
- AOP/security advice có query authorization.

Nếu filter cần đọc membership từ DB, nên dùng **global identity datasource**, không phải tenant-bound datasource đang đợi organization identifier.

### 7.3. Async servlet dispatch

`OncePerRequestFilter` và Servlet async request handling có dispatch semantics đặc biệt. Đừng giả định filter scope của request thread tồn tại nguyên vẹn trong mọi async dispatch. Với async tasks, vẫn cần propagation strategy rõ ràng.

## 8. Đọc organization context tại service boundary

Trong service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final AuthorizationService authorization;

    public OrderApplicationService(
            OrderRepository orders,
            AuthorizationService authorization) {
        this.orders = orders;
        this.authorization = authorization;
    }

    @Transactional(readOnly = true)
    public OrderView getOrder(Long id) {
        OrganizationContext org =
            OrganizationContextHolder.require();

        authorization.requireCanViewOrder(
            org.actorId(),
            org.organizationId(),
            id
        );

        PurchaseOrder order = orders
            .findByOrganizationIdAndId(
                org.organizationId(), id
            )
            .orElseThrow(NotFoundException::new);

        return OrderView.from(order);
    }
}
~~~

Repository minh họa:

~~~java
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrganizationIdAndId(
        String organizationId, Long id
    );
}
~~~

### 8.1. Chọn org trước khi mở transaction

Nếu Hibernate multi-tenancy được cấu hình để chọn connection/schema khi mở Session hoặc acquire connection, organization context phải **sẵn sàng trước thời điểm tenant được resolve/bind**.

Không làm:

~~~java
@Transactional
public void handle(String requestedOrg) {
    OrganizationContextHolder.set(
        new OrganizationContext(requestedOrg, "system", null)
    );
    // Transaction interceptor có thể đã mở Session
    // trước khi body method chạy.
}
~~~

Cách đúng: xác minh và thiết lập context ở **lớp bên ngoài** transactional method, rồi gọi transactional bean qua Spring proxy.

### 8.2. Không đổi tenant giữa transaction

Một `EntityManager` đã gắn tenant A không nên được tiếp tục dùng sau khi ThreadLocal đổi sang tenant B. Session identity, first-level cache và connection routing không tự biến đổi theo một biến thread.

Quy tắc:

> **Mỗi unit of work/transaction/session có một tenant identity bất biến.**

Nếu phải xử lý hai organizations, chia thành hai transactions/sessions độc lập, không làm hai operations đó tưởng là một ACID transaction nếu thực sự ở hai DB/schema khác nhau.

## 9. Hibernate nhiều tổ chức: ba kiểu tách dữ liệu

| Mô hình | Dữ liệu nằm ở đâu? | Cách chọn |
| --- | --- | --- |
| Shared table, discriminator | Cùng table, mỗi row có `organization_id` | Tenant predicate/filter/@TenantId/RLS |
| Schema per organization | Cùng DB, schema khác nhau | Tenant routing/connection schema |
| Database per organization | Database hoặc pool riêng | Tenant identifier → datasource/connection |

Mỗi mô hình có trách nhiệm cách ly riêng.

### 9.1. Shared table

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    organization_id VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL
);
~~~

Truy vấn bắt buộc scope:

~~~sql
SELECT id, status, total_amount
FROM purchase_orders
WHERE organization_id = :organizationId
  AND id = :orderId;
~~~

Nếu code quên predicate ở một native query, có thể lộ dữ liệu. Cần ORM-enforced tenancy nếu phù hợp, database RLS và tests phòng thủ.

### 9.2. Schema per organization

~~~text
DB cluster
    tenant_a.purchase_orders
    tenant_b.purchase_orders
    tenant_c.purchase_orders
~~~

Hibernate chọn tenant/schema tương ứng khi mở/acquire connection. Việc thay đổi search path/schema trên connection **phải được reset** khi trả connection cho pool, tránh worker sau đọc sai schema.

### 9.3. Database per organization

~~~text
org-A → DataSource A
org-B → DataSource B
org-C → DataSource C
~~~

Isolation vật lý có thể mạnh hơn nhưng chi phí vận hành, migration, connection pools và reporting xuyên tenants cao hơn. Resolver vẫn phải được authorization kiểm soát.

### 9.4. Tenant isolation không tự giải quyết authorization

Ngay cả khi org-A và org-B ở hai DB khác nhau, một user không có quyền org-B vẫn có thể truy cập nếu resolver tin raw header. **Authorization trước routing** là bắt buộc.

## 10. CurrentTenantIdentifierResolver của Hibernate

Hibernate cung cấp integration point để xác định tenant identifier cho session hiện hành. Một implementation minh họa ở các phiên bản Hibernate hỗ trợ interface generic:

~~~java
import org.hibernate.context.spi.CurrentTenantIdentifierResolver;

public final class OrganizationTenantResolver
        implements CurrentTenantIdentifierResolver<String> {

    @Override
    public String resolveCurrentTenantIdentifier() {
        return OrganizationContextHolder
            .require()
            .organizationId();
    }

    @Override
    public boolean validateExistingCurrentSessions() {
        return true;
    }
}
~~~

Tên package/signature và tích hợp configuration phụ thuộc Hibernate version. Ví dụ property:

~~~properties
hibernate.tenant_identifier_resolver=com.example.tenant.OrganizationTenantResolver
~~~

Một số ứng dụng cung cấp resolver như bean/instance qua Hibernate properties thay vì class name. Phải kiểm tra bootstrapping của Spring Boot/Hibernate cụ thể.

### 10.1. validateExistingCurrentSessions() dùng để làm gì?

Nó hỗ trợ kiểm tra một current session đang gắn tenant nào trong những tình huống Hibernate sử dụng cơ chế current-session validation. Nó **không**:

- Tự kiểm tra membership.
- Tự tạo tenant từ HTTP header.
- Bảo đảm mọi repository/native SQL đều có tenant predicate.
- Cho phép đổi tenant an toàn trên một Session đã mở.

### 10.2. Không trả default tenant khi không có context

Resolver cho tenant-scoped workload nên **fail closed** nếu context thiếu. Nếu application có global administration workload, sử dụng transaction/session/connection path được thiết kế riêng, có quyền rõ ràng; không trả `"master"` như một fallback vô điều kiện.

### 10.3. Bootstrapping và schema metadata

Hibernate có thể yêu cầu connection để lấy metadata trước khi có HTTP organization. Cơ chế multi-tenant connection provider có khái niệm `getAnyConnection()` cho bootstrap, khác với việc chọn tenant cho user operation. Không đánh đồng “bootstrap connection” với một tenant mặc định mà mọi request thiếu context có thể sử dụng.

## 11. MultiTenantConnectionProvider

Với schema-per-tenant hoặc database-per-tenant, Hibernate có SPI `MultiTenantConnectionProvider<T>` ở những dòng phiên bản tương ứng, thường có các operation:

~~~java
Connection getAnyConnection() throws SQLException;

void releaseAnyConnection(Connection connection)
    throws SQLException;

Connection getConnection(String tenantIdentifier)
    throws SQLException;

void releaseConnection(
    String tenantIdentifier,
    Connection connection
) throws SQLException;
~~~

Đây là **chữ ký rút gọn để giải thích cơ chế**, không phải một implementation đầy đủ của interface cho mọi Hibernate version.

### 11.1. Cơ chế routing an toàn

~~~text
Verified OrganizationContext
    ↓
organizationId = org-A
    ↓
Server-side route catalog:
    org-A → db-cluster-2 / schema tenant_a
    ↓
Hibernate MultiTenantConnectionProvider
    ↓
Connection có isolation đúng cho org-A
~~~

Route catalog phải được server kiểm soát; không ghép raw organization ID thành SQL:

~~~java
connection.createStatement()
    .execute("SET search_path TO " + requestedOrg);
~~~

Đoạn này nguy hiểm nếu không whitelist/mapping identifier đúng, và còn gặp vấn đề pool state.

### 11.2. Reset connection state

Nếu provider gọi `Connection.setSchema(...)` hoặc SQL `SET search_path`, phải đảm bảo:

- Kết nối chỉ được release về pool sau khi trạng thái được khôi phục an toàn.
- Transaction, schema, session variables không rò giữa tenants.
- Error path cũng cleanup.
- Connection được trả lại đúng pool.
- Không share một connection tenant A cho tenant B đồng thời.

Một connection pool có thể giữ session-level state lâu hơn một request. **Cleanup là yêu cầu isolation**, không chỉ hygiene.

### 11.3. Một tenant có thể có nhiều physical routes theo thời gian

Organization org-A có thể chuyển database trong một migration. Nên map bằng tenant catalog ổn định, có version/operational controls. Retry jobs cần được thiết kế để tìm route hiện tại an toàn thay vì hardcode database server trong message cũ.

## 12. Hibernate @TenantId và discriminator tenancy

Một số phiên bản Hibernate hỗ trợ `@TenantId` cho multi-tenancy kiểu partition/discriminator:

~~~java
import org.hibernate.annotations.TenantId;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @TenantId
    @Column(name = "organization_id", nullable = false)
    private String organizationId;

    private String status;
}
~~~

Đây là ví dụ **Hibernate-specific**, không phải một annotation JPA chuẩn. Khả năng tự điền/filter field, áp dụng lên queries/DML và các hạn chế phải kiểm tra trên Hibernate version/dialect thực tế.

### 12.1. Không xem @TenantId là authorization

Tenant field/predicate có thể giới hạn dữ liệu theo tenant identifier, nhưng **ai được chọn identifier đó** vẫn là vấn đề bảo mật thuộc application.

### 12.2. Không trộn nhiều cách isolation thiếu contract

Một hệ thống vừa tự thêm `organization_id` trong HQL, vừa dùng Hibernate `@TenantId`, vừa bật custom filter, vừa dùng DB RLS có thể có các giá trị context không đồng bộ.

Defense in depth là tốt nếu tất cả dùng **cùng một verified organization**, nhưng cần test tính nhất quán và biết layer nào chịu trách nhiệm gì.

### 12.3. Native queries và bulk operations

Không giả định mọi native SQL hoặc bulk HQL/JPQL sẽ tự được sửa để thêm org predicate bởi tất cả cơ chế multitenancy. Một raw SQL trực tiếp vào shared table phải được review và test cross-tenant.

## 13. Shared-table multitenancy: tránh dựa vào developer nhớ WHERE

Một anti-pattern:

~~~java
Optional<Order> findById(Long id);
~~~

trên một bảng chung, nếu `id` unique toàn hệ thống, method có thể lấy Order thuộc org khác khi caller biết ID. Nếu ID chỉ unique trong org, truy vấn còn không đủ định danh.

Cách an toàn hơn:

~~~java
Optional<Order> findByOrganizationIdAndId(
    String organizationId, Long id
);
~~~

Cùng với các lớp bảo vệ khác như DB RLS, constraints và tests. Cũng nên có:

~~~sql
CREATE INDEX idx_orders_org_status_created
ON purchase_orders (
    organization_id,
    status,
    created_at DESC,
    id DESC
);
~~~

### 13.1. Unique constraint phải tính org

Nếu business key chỉ unique trong một org:

~~~sql
ALTER TABLE purchase_orders
ADD CONSTRAINT uk_orders_org_external
UNIQUE (organization_id, external_order_id);
~~~

Đừng vô tình dùng `UNIQUE(external_order_id)` và chặn các organizations khác nhau dùng cùng mã đơn ngoài.

### 13.2. Composite foreign keys tránh liên kết cross-tenant

Giả sử OrderLine có `organization_id` và `order_id`. Một FK chỉ trên `order_id` có thể cho phép child của org-B tham chiếu parent của org-A trong một số thiết kế ID.

Một thiết kế DB có thể:

~~~sql
ALTER TABLE purchase_orders
ADD CONSTRAINT uk_orders_org_id
UNIQUE (organization_id, id);

ALTER TABLE order_lines
ADD CONSTRAINT fk_line_order_same_org
FOREIGN KEY (organization_id, order_id)
REFERENCES purchase_orders (organization_id, id);
~~~

DB constraints giúp phát hiện cross-tenant reference ngay cả khi ORM/application có bug.

### 13.3. Không cho client tự set entity.organizationId

Trong create API, server điền orgId từ verified context. Không nhận từ request body rồi gắn vào entity mà không kiểm tra.

~~~java
Order entity = new Order(
    orgContext.organizationId(),
    request.externalOrderId(),
    request.totalAmount()
);
~~~

## 14. PostgreSQL Row-Level Security như phòng thủ bổ sung

Với shared-table architecture, PostgreSQL RLS có thể giúp DB thực thi policy theo organization:

~~~sql
ALTER TABLE purchase_orders
ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_org_isolation
ON purchase_orders
USING (
    organization_id =
        current_setting('app.organization_id', true)
)
WITH CHECK (
    organization_id =
        current_setting('app.organization_id', true)
);
~~~

Đây là ví dụ dùng `organization_id VARCHAR`. Khi setting thiếu, biểu thức so sánh với NULL thường không cho TRUE, giúp fail-closed đối với role chịu RLS.

### 14.1. Setting phải được gắn đúng connection/transaction

Ví dụ PostgreSQL:

~~~sql
SELECT set_config(
    'app.organization_id',
    :organizationId,
    true
);
~~~

Tham số thứ ba `true` là transaction-local. Phải thiết lập trong **chính transaction/connection** dùng để thực thi SQL tenant-bound.

Nếu thiết lập sau khi một query đã chạy hoặc trên connection khác, RLS có thể không hoạt động như mong đợi.

### 14.2. RLS không thay thế authorization

DB chỉ biết giá trị setting được truyền; application phải xác minh user có quyền chọn organization trước khi set. DB role dùng bởi application phải được cấu hình phù hợp và không có đặc quyền bypass RLS ngoài ý muốn.

### 14.3. Transaction-local giảm nguy cơ leak pool state

Session-level `SET` kéo dài sau request có thể rò qua connection pool. Transaction-local setting giúp giới hạn phạm vi, nhưng vẫn phải kiểm tra pooling mode, transaction manager và connection lifecycle.

### 14.4. FORCE ROW LEVEL SECURITY và privileges

PostgreSQL table owner và những role có quyền đặc biệt có thể không chịu policy theo cách role thông thường. Với nhu cầu isolation mạnh, xem `FORCE ROW LEVEL SECURITY`, privileges và role design theo PostgreSQL documentation/version. Không chỉ viết policy rồi giả định mọi DB user đều bị chặn.

## 15. Spring transaction boundary và thứ tự thiết lập context

Một lỗi thường gặp:

~~~java
@Service
public class ImportService {

    @Transactional
    public void importFor(String organizationId) {
        OrganizationContextHolder.set(
            new OrganizationContext(
                organizationId, "system", null
            )
        );
        // Quá muộn nếu Session đã được bind với tenant khác.
    }
}
~~~

Với proxy-based Spring transactions, transaction interceptor chạy **trước khi method body bắt đầu**. Một Hibernate Session/connection có thể đã được tạo hoặc bind với tenant identifier tại thời điểm đó.

### 15.1. Pattern an toàn: outer coordinator và inner transaction bean

~~~java
@Service
public class ImportCoordinator {

    private final ImportWriter writer;
    private final OrganizationSelectionService selector;

    public ImportCoordinator(
            ImportWriter writer,
            OrganizationSelectionService selector) {
        this.writer = writer;
        this.selector = selector;
    }

    public void importFor(
            String actorId,
            String requestedOrg,
            List<ImportRecord> records) {

        OrganizationContext verified = selector.select(
            actorId,
            requestedOrg,
            null
        );

        OrganizationContextHolder.runWith(
            verified,
            () -> writer.write(records)
        );
    }
}
~~~

~~~java
@Service
public class ImportWriter {

    private final EntityManager em;

    public ImportWriter(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public void write(List<ImportRecord> records) {
        for (ImportRecord item : records) {
            em.persist(ImportedOrder.from(
                OrganizationContextHolder.require()
                    .organizationId(),
                item
            ));
        }
    }
}
~~~

`ImportWriter.write()` được gọi **qua Spring bean proxy** sau khi context đã được thiết lập.

### 15.2. Không gọi transactional method bằng this

~~~java
public void run() {
    write(); // self-invocation, @Transactional có thể bị bypass.
}

@Transactional
public void write() {
    // ...
}
~~~

Tách bean như ví dụ hoặc dùng `TransactionTemplate` nếu muốn transaction programmatically. Nếu outer method đã có transaction, inner self-call có thể chạy trong outer transaction nhưng **không áp dụng propagation riêng**.

### 15.3. Không xử lý nhiều org trong một EntityManager

Một coordinator có thể duyệt:

~~~java
for (String orgId : organizations) {
    OrganizationContextHolder.runWith(
        verifiedContextFor(orgId),
        () -> writer.writeBatchForCurrentOrg()
    );
}
~~~

Mỗi `writer.writeBatchForCurrentOrg()` phải đi qua boundary tạo transaction/session phù hợp. Không dùng một outer `@Transactional` bao toàn vòng lặp rồi thay org context từng lượt.

## 16. Vì sao @RequestScope không đủ cho background jobs?

Spring có bean `@RequestScope` và có thể truy cập thông tin HTTP request hiện tại trong một Servlet request.

Nhưng:

- `@Async` có thể chạy trên thread khác sau response.
- Scheduled job không có HTTP request.
- Kafka/RabbitMQ consumer không có request scope.
- Command-line import không có web context.
- Message có thể được xử lý sau nhiều giờ.
- Retry có thể diễn ra trên instance khác.

Vì vậy không nên định nghĩa tenant resolution **chỉ** là:

~~~java
RequestContextHolder.currentRequestAttributes()
~~~

và giả định mọi execution paths đều có HTTP context.

### 16.1. Tách resolver theo entry point

Một thiết kế:

~~~text
HTTP request
    -> OrganizationSelectionService.select(user, requestedOrg)

Scheduled job
    -> OrganizationServiceAccountPolicy.select(job, configuredOrg)

Message consumer
    -> OrganizationMessageValidator.select(message, consumerIdentity)

Test/CLI
    -> Explicit test/system organization context
~~~

Các nguồn khác nhau nhưng tất cả tạo verified context trước khi vào tenant-scoped transaction.

## 17. @Async và vấn đề ThreadLocal không tự truyền

Ví dụ sai kỳ vọng:

~~~java
@Service
public class ExportService {

    private final AsyncExportWorker worker;

    public void requestExport() {
        // Request thread có OrganizationContext org-A.
        worker.exportAsync();
    }
}
~~~

~~~java
@Service
public class AsyncExportWorker {

    @Async
    public void exportAsync() {
        OrganizationContext org =
            OrganizationContextHolder.require();
        // Thường thất bại: worker thread chưa có context.
    }
}
~~~

`@Async` chuyển xử lý sang executor thread. ThreadLocal của request thread **không tự lan sang đó**.

### 17.1. Giải pháp ưu tiên: truyền explicit context/organization ID

~~~java
@Service
public class ExportService {

    private final AsyncExportWorker worker;

    public void requestExport() {
        OrganizationContext org =
            OrganizationContextHolder.require();

        worker.exportAsync(
            new ExportCommand(
                org.organizationId(),
                org.actorId(),
                org.correlationId()
            )
        );
    }
}
~~~

~~~java
public record ExportCommand(
    String organizationId,
    String requestedBy,
    String correlationId
) {}
~~~

Tuy nhiên, **truyền ID không tự xác minh authorization** cho worker. Nếu task chạy trong cùng trust boundary, có thể sử dụng context đã được xác minh từ request; với job lưu lâu hoặc cần quyền thay đổi theo thời gian, worker phải kiểm tra lại policy trước khi thực thi.

### 17.2. Tách async entrypoint và transactional worker

~~~java
@Service
public class AsyncExportWorker {

    private final OrganizationJobPolicy jobPolicy;
    private final ExportTransactionService transactionService;

    @Async("tenantExecutor")
    public void exportAsync(ExportCommand command) {
        OrganizationContext verified =
            jobPolicy.verifyForExecution(command);

        OrganizationContextHolder.runWith(
            verified,
            () -> transactionService.exportData(command)
        );
    }
}
~~~

~~~java
@Service
public class ExportTransactionService {

    @Transactional(readOnly = true)
    public void exportData(ExportCommand command) {
        // Hibernate Session được tạo trong verified context.
    }
}
~~~

Đây là skeleton; `verifyForExecution()` phải xác thực actor/service identity và quyền trên org tại thời điểm xử lý theo business policy.

Điểm quan trọng: **thiết lập context trước khi gọi transactional method qua một bean khác**, không thiết lập sau khi transaction đã mở.

## 18. TaskDecorator truyền context qua Executor

Khi muốn tự động truyền organization context trong một executor nội bộ được kiểm soát, Spring có `TaskDecorator`.

~~~java
import org.springframework.core.task.TaskDecorator;

public final class OrganizationTaskDecorator
        implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {

        // Capture tại thread submit task.
        OrganizationContext captured =
            OrganizationContextHolder.currentOrNull();

        return () -> {
            OrganizationContext previous =
                OrganizationContextHolder.currentOrNull();

            try {
                if (captured == null) {
                    OrganizationContextHolder.clear();
                } else {
                    OrganizationContextHolder.set(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    OrganizationContextHolder.clear();
                } else {
                    OrganizationContextHolder.set(previous);
                }
            }
        };
    }
}
~~~

Đăng ký executor:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("tenantExecutor")
    public ThreadPoolTaskExecutor tenantExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(
            new OrganizationTaskDecorator()
        );
        executor.initialize();
        return executor;
    }
}
~~~

### 18.1. Vì sao capture lúc submit, không lúc execute?

Khi task được submit:

~~~text
Request thread: org-A
  -> executor.submit(task)
  -> request kết thúc, context được clear
  -> worker thực thi sau 2 giây
~~~

Nếu worker lúc thực thi mới đọc context của request thread, context đã không còn. Decorator capture một **immutable snapshot** khi submit và thiết lập trên worker trước khi chạy.

### 18.2. Decorator phải cleanup kể cả task lỗi

Nếu task ném exception, `finally` vẫn phải restore/remove context. Nếu không, worker pool có thể mang org-A sang task sau của org-B.

### 18.3. captured == null nên làm gì?

Ví dụ decorator xóa context trước khi chạy task không có tenant. Điều này tránh kế thừa ngẫu nhiên tenant cũ. Nhưng một tenant-bound task nên **fail closed** khi vào service/tenant resolver vì thiếu context, thay vì tự dùng fallback.

### 18.4. TaskDecorator không bao trùm mọi async path

Nếu code dùng:

~~~java
CompletableFuture.runAsync(task);
~~~

không truyền executor của Spring, nó có thể chạy trên common pool và **không dùng TaskDecorator**. Các thư viện tự quản lý threads cũng vậy.

Nên dùng explicit executor:

~~~java
CompletableFuture.runAsync(
    task,
    tenantExecutor
);
~~~

hoặc explicit context wrapper, và không mặc định mọi queue/scheduler áp dụng cùng decorator.

### 18.5. Truyền toàn bộ SecurityContext cần thận trọng

Spring Security có các wrappers/delegating executors để truyền SecurityContext. Nhưng **truyền SecurityContext không tự truyền OrganizationContext** nếu app lưu riêng.

Ngược lại, copy cả authentication/session objects vào long-lived jobs có thể tăng rủi ro token expiry/leak. Với durable tasks, lưu stable actor/org IDs rồi xác thực lại quyền là cách thường dễ kiểm soát hơn.

## 19. TaskDecorator không thay thế phân quyền

Decorator capture dữ liệu từ thread submit. Nếu submitter set một org giả hoặc có quyền bị thu hồi trước lúc task chạy, decorator vẫn truyền dữ liệu đó.

Nên phân biệt hai loại tác vụ:

- **Short-lived trusted in-process task:** capture verified context, dùng ngay trong boundary và policy cho phép.
- **Durable/security-sensitive task:** chứa org ID và actor identity trong job record, worker xác minh lại quyền trước xử lý.

Context propagation là **kỹ thuật vận chuyển**, không phải cơ chế trao quyền.

## 20. @Scheduled không có HTTP organization

Ví dụ:

~~~java
@Scheduled(cron = "0 0 2 * * *")
public void nightlyAggregation() {
    // Không có request header/principal của HTTP user.
}
~~~

Cần quyết định scheduler xử lý:

1. Một organization cụ thể, cấu hình server-side.
2. Mọi organizations đang active.
3. Một partition các organizations được claim bởi worker.
4. Một system-level report có dữ liệu tổng hợp được ủy quyền riêng.

### 20.1. Duyệt organizations với transaction riêng

~~~java
@Component
public class AggregationScheduler {

    private final OrganizationCatalog catalog;
    private final OrganizationJobPolicy policy;
    private final AggregationWorker worker;

    @Scheduled(cron = "0 0 2 * * *")
    public void run() {
        for (String orgId : catalog.activeOrganizationIds()) {
            OrganizationContext verified =
                policy.contextForSystemJob(
                    "nightly-aggregation",
                    orgId
                );

            OrganizationContextHolder.runWith(
                verified,
                () -> worker.aggregateOneOrganization()
            );
        }
    }
}
~~~

~~~java
@Service
public class AggregationWorker {

    @Transactional
    public void aggregateOneOrganization() {
        // Đọc/ghi dữ liệu của organization hiện tại.
    }
}
~~~

Sơ đồ này chỉ phù hợp nếu `worker` là bean proxy độc lập và scheduler không có transaction ngoài bao trùm toàn vòng lặp.

### 20.2. Đừng dùng root tenant để xử lý tất cả

Một service account có quyền xử lý mọi tổ chức **không có nghĩa** query nên mở “tenant root” rồi bỏ filtering. Thường an toàn và dễ đối soát hơn khi lặp từng verified organization và ghi metric theo org.

### 20.3. Scheduler cần idempotency và checkpoint

Nếu job fail sau org-A nhưng trước org-B, lần chạy lại cần biết trạng thái. Sử dụng job ID, per-org checkpoint, uniqueness và retry policy; context truyền đúng chưa bảo đảm xử lý đúng một lần.

## 21. Spring Batch: JobParameters và StepExecutionContext

Với Spring Batch, organization có thể được mang qua:

- `JobParameters` (ví dụ `organizationId`).
- `StepExecutionContext`.
- `ItemReader`/`ItemProcessor`/`ItemWriter` scope.
- Partition metadata cho multi-org processing.

Ví dụ conceptual:

~~~text
Job: import-orders
JobParameters:
    organizationId = org-A
    sourceFileId = file-100
    importRunId = run-2026-11-15-01

Step:
    verify org-A
    -> install context
    -> open tenant-scoped transaction
    -> read/process/write
    -> cleanup
~~~

### 21.1. JobParameters là dữ liệu, không phải giấy phép

Ai đó có thể khởi tạo job với `organizationId=org-B`. Job launcher/worker phải kiểm tra quyền của initiating actor/service account theo trust boundary.

### 21.2. Chunk transactions và tenant context

Trong Spring Batch, transaction của chunk có thể bắt đầu **trước** `ItemReader` hoặc `ItemWriter` chạy, tùy step pipeline. Nếu context chỉ được đặt trong `ItemWriter.write()`, có thể quá muộn đối với tenant resolver.

Cần thiết lập org **trước chunk transaction/session acquisition**, ví dụ qua partition worker entrypoint/step-scoped orchestration được thiết kế và kiểm thử, không chỉ trong writer callback.

### 21.3. Multi-threaded/partitioned steps

Mỗi partition/worker phải có immutable org identity của riêng mình. Không dùng một ThreadLocal được set ở scheduler thread rồi mặc định mọi partition workers nhìn thấy nó.

### 21.4. Restart/retry

Spring Batch restart có thể chạy worker trên thread/process khác. Ngữ cảnh chỉ sống trong RAM không đủ; org ID phải nằm trong **durable job/partition metadata**, và được xác minh/thiết lập lại lúc restart.

## 22. Message queue/Kafka: context phải đi trong envelope

Một HTTP request tạo command bất đồng bộ:

~~~json
{
  "messageId": "msg-9001",
  "organizationId": "org-A",
  "actorId": "user-17",
  "action": "GENERATE_INVOICE",
  "invoiceId": 123,
  "correlationId": "trace-7788"
}
~~~

Message có thể đến sau nhiều giờ, trên JVM khác; ThreadLocal HTTP không tồn tại. Vì vậy cần **truyền các định danh cần thiết trong message envelope**.

### 22.1. Không xem organizationId trong message là trusted vô điều kiện

Consumer cần:

- Xác thực producer/service identity hoặc bảo đảm topic/queue chỉ nhận từ nguồn được phép.
- Kiểm tra schema/version của message.
- Xác minh organization tồn tại, active, và actor/job có quyền tương ứng.
- Kiểm tra resource `invoiceId` thuộc org đó.
- Thiết lập context trước khi mở persistence transaction.
- Dọn context sau khi xử lý, kể cả khi message fail.

### 22.2. Message headers hay payload?

Cả hai đều có thể chứa organization ID. Quan trọng là contract nhất quán và bảo vệ integrity. Với headers:

~~~text
x-organization-id: org-A
x-correlation-id: trace-7788
x-message-version: 1
~~~

Không tin headers của nguồn chưa xác thực; consumer vẫn phải validate. Một message header có thể bị giả mạo nếu broker ACL/producer authentication thiếu kiểm soát.

### 22.3. Entry point consumer rồi gọi transaction bean

~~~java
@Component
public class InvoiceMessageListener {

    private final OrganizationMessagePolicy policy;
    private final InvoiceTransactionWorker worker;

    public InvoiceMessageListener(
            OrganizationMessagePolicy policy,
            InvoiceTransactionWorker worker) {
        this.policy = policy;
        this.worker = worker;
    }

    @KafkaListener(topics = "invoice-commands")
    public void onMessage(InvoiceCommand command) {
        OrganizationContext verified =
            policy.verifyForProcessing(command);

        OrganizationContextHolder.runWith(
            verified,
            () -> worker.process(command)
        );
    }
}
~~~

~~~java
@Service
public class InvoiceTransactionWorker {

    @Transactional
    public void process(InvoiceCommand command) {
        // Hibernate tenant context đã sẵn sàng.
        // Kiểm tra resource tenant ownership và idempotency.
    }
}
~~~

`InvoiceCommand` và `OrganizationMessagePolicy` là abstractions minh họa; application phải triển khai serialization, authentication và retry/dead-letter policy.

### 22.4. @Transactional trực tiếp trên listener có thể sai thứ tự

Nếu Spring interceptor mở transaction trước khi body `onMessage()` gọi `OrganizationContextHolder.set()`, Hibernate có thể resolve tenant quá sớm.

Tách entrypoint context-selection khỏi transactional worker là cách an toàn, dễ test hơn.

### 22.5. Retry và redelivery

Broker thường có at-least-once processing; khi consumer commit DB rồi crash trước ack, message có thể được gửi lại. Dùng idempotency key theo **organization + message ID/business key**:

~~~sql
CREATE TABLE processed_messages (
    organization_id VARCHAR(64) NOT NULL,
    message_id VARCHAR(150) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (organization_id, message_id)
);
~~~

Dedup record và business update cần được ghi trong cùng transaction phù hợp khi cùng DB.

## 23. Context qua downstream HTTP/gRPC

Một service A gọi service B:

~~~text
A: verified user-17 / org-A
    ↓ HTTP/gRPC
B: nhận request chọn org-A
    ↓ authenticate service/user context
B: authorize org-A
    ↓
B: set verified organization context
~~~

Không nên coi `X-Organization-Id` do A chuyển tiếp là proof of authorization cho B. Service B cần tin cậy producer theo mTLS/JWT/service token hoặc cơ chế tương ứng, và kiểm tra policy của mình.

### 23.1. Trusted delegation khác impersonation

Một backend service có thể gọi thay user. Cần phân biệt:

- `actorId`: người yêu cầu ban đầu.
- `serviceIdentity`: dịch vụ thực sự gửi request.
- `organizationId`: scope dữ liệu.
- `delegationScope`: những quyền được cho phép truyền tiếp.
- `correlationId`: trace.

Không để service B tự suy toàn bộ quyền của user chỉ từ một chuỗi actorId trong header.

### 23.2. Correlation ID không phải security credential

`X-Correlation-Id` hữu ích cho logging/tracing. Client có thể gửi giá trị này; phải giới hạn độ dài/định dạng và không coi nó là bằng chứng quyền hay dùng trực tiếp làm SQL identifier.

### 23.3. Retry và timeout

Một downstream call có thể timeout sau khi B đã commit. Nếu A retry, B cần idempotency key có scope organization. Context đúng vẫn không giải quyết commit-unknown/exactly-once.

## 24. Reactor và WebFlux: ThreadLocal không theo logical request

Trong ứng dụng reactive, processing có thể chuyển thread giữa các operators:

~~~text
HTTP request on thread-1
    -> publishOn thread-8
    -> flatMap on thread-12
    -> database client on thread-4
~~~

`ThreadLocal` không phải cơ chế lưu context đáng tin cho **logical reactive flow** vì một flow có thể chuyển thread, còn một thread có thể chạy nhiều flows.

### 24.1. Reactor Context

Ví dụ khái niệm:

~~~java
public static final String ORG_CONTEXT_KEY =
    "verifiedOrganizationContext";

Mono<OrderView> viewOrder(Long orderId) {
    return Mono.deferContextual(contextView -> {
        OrganizationContext org =
            contextView.get(ORG_CONTEXT_KEY);

        return reactiveOrderService.findByOrganizationAndId(
            org.organizationId(),
            orderId
        );
    });
}
~~~

Entry point sau authorization thêm context:

~~~java
return viewOrder(orderId)
    .contextWrite(ctx ->
        ctx.put(ORG_CONTEXT_KEY, verifiedOrg)
    );
~~~

Reactor Context gắn với subscriber chain, không phải một ThreadLocal toàn cục.

### 24.2. Nếu gọi blocking Hibernate/JPA trong WebFlux?

Hibernate ORM/JPA truyền thống thường là blocking và dùng transaction/session thread-bound theo cách triển khai. Không chạy blocking database calls trực tiếp trên event-loop. Nếu cần bridge sang blocking executor, phải có **explicit context handoff** và thiết lập tenant context trước khi mở transaction của blocking worker.

Không giả định Reactor Context tự hiện diện trong Hibernate `CurrentTenantIdentifierResolver` dùng ThreadLocal.

### 24.3. Reactive transaction khác imperative transaction

Spring reactive transaction thường dùng Reactor context khác ThreadLocal transaction của JDBC/JPA. Đừng sao chép `@Transactional` từ imperative service sang reactive chain mà kỳ vọng transaction manager và resource hoạt động y hệt.

Với stack Spring Data R2DBC/reactive, dùng transaction manager/context propagation của reactive stack, không lấy Hibernate Session như reactive resource.

### 24.4. Micrometer context propagation

Một số phiên bản Spring/Micrometer cung cấp cơ chế propagation qua thread boundaries, có thể bridge ThreadLocal/Reactor Context theo cấu hình. Đây là **hạ tầng cần đăng ký accessor/đánh giá phạm vi**; không mặc định nó đã truyền organization context hoặc thực thi authorization.

## 25. Virtual threads và ScopedValue

Trên Java hiện đại, virtual threads có thể giúp workload blocking, nhưng không loại bỏ nhu cầu tenant context đúng.

- `ThreadLocal` vẫn là state theo thread, không phải context tự truyền qua mọi executor/task.
- Thread-per-task khác thread pool về tái sử dụng, nhưng tenant identity vẫn phải được thiết lập rõ.
- `ScopedValue` ở những Java versions hỗ trợ phù hợp có thể là một cách truyền immutable context có cấu trúc, nhưng API/version/structured concurrency policy phải được xác nhận.

Dù dùng cơ chế nào, **context phải tồn tại trước khi Hibernate resolve tenant** và không được tự động ủy quyền chỉ vì ID đã được truyền.

## 26. Tổ chức hiện tại và cache

Một lỗi phổ biến nằm ngoài SQL: cache key không có organization.

~~~java
@Cacheable("orders")
public OrderView getOrder(Long orderId) {
    // ...
}
~~~

Nếu org-A và org-B có cùng `orderId=123`, cache với key chỉ `123` có thể trả OrderView của org-A cho org-B.

### 26.1. Cache key phải tenant-scoped

~~~java
@Cacheable(
    cacheNames = "orders",
    key = "T(com.example.tenant.OrganizationContextHolder)" +
          ".require().organizationId() + ':' + #orderId"
)
public OrderView getOrder(Long orderId) {
    // ...
}
~~~

Đây là ví dụ SpEL mang tính minh họa; với dự án thật nên dùng typed cache key/key generator thay vì nối chuỗi tùy tiện, vì phải xử lý escaping/collisions và test context availability.

Một key logic tốt:

~~~text
(organizationId, resourceType, resourceId, filterVersion)
~~~

### 26.2. Hibernate second-level cache

Khi dùng Hibernate multi-tenancy được cấu hình đúng, provider có cơ chế tenant-aware cache keys theo tính năng/version. Nhưng custom application caches, Redis keys, HTTP caches và CDN vẫn cần tự thiết kế scope.

Không kết luận “Hibernate tenant resolver đã có” nên mọi cache tự an toàn.

### 26.3. Cache invalidation cũng cần org

Khi sửa Order 123 của org-A, đừng evict hoặc update cache entry của org-B vô tình. Key strategy và invalidation events cần mang cùng tenant identity.

## 27. Organization và optimistic locking

`@Version` bảo vệ concurrent modification của một row/entity:

~~~java
@Version
private long version;
~~~

Nó không thay tenant isolation. Hai tenants có thể có cùng ID/version nhưng dữ liệu khác.

Với shared table:

~~~sql
UPDATE purchase_orders
SET status = :status,
    version = version + 1
WHERE organization_id = :orgId
  AND id = :id
  AND version = :expectedVersion;
~~~

Nếu không có `organization_id` predicate, `@Version` không ngăn ghi nhầm organization.

### 27.1. Row count = 0

Có thể nghĩa:

- Row không tồn tại trong tenant.
- User không được truy cập.
- Version stale.
- Filter business condition không khớp.

API không nên tiết lộ dữ liệu tenant khác trong thông báo lỗi. Có thể trả 404 hoặc 409 theo policy mà không làm lộ sự tồn tại của resource ngoài scope.

## 28. Organization và native/bulk SQL

Mọi truy vấn native vào shared table phải xét tenant:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE organization_id = :organizationId
  AND status = 'EXPIRED';
~~~

Không an toàn:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE status = 'EXPIRED';
~~~

### 28.1. Bulk HQL/JPA bypass một số lifecycle/filters

Bulk operations có semantics khác entity dirty checking. Một số hooks, callbacks, Envers audit và ORM-level filters có thể không được áp dụng như developer tưởng tùy cơ chế/phiên bản.

Với multi-tenancy, các bulk operations phải có tenant predicates rõ và được kiểm thử trên DB thực, hoặc được RLS/ORM tenancy enforcement hỗ trợ với hiểu biết đầy đủ.

### 28.2. Raw JDBC không biết ThreadLocal của ORM

Một `JdbcTemplate` dùng connection trực tiếp không tự hỏi `CurrentTenantIdentifierResolver` của Hibernate trong mọi cấu hình. Cần route DataSource đúng hoặc bind tenant predicate/RLS setting tương ứng.

### 28.3. Native SQL và schema name

Nếu dùng schema-per-tenant, không ghép raw header thành SQL identifier. Bind parameters không thể thay thế identifier ở nhiều SQL dialects; phải dùng server-side whitelist/schema route hoặc driver `setSchema()` an toàn với cleanup.

## 29. Idempotency phải có phạm vi tổ chức

Nếu org-A và org-B đều gửi event `payment-100`, dedup key chỉ là `payment-100` sẽ làm một org bị coi nhầm duplicate của org kia.

Sử dụng:

~~~sql
CREATE TABLE idempotent_operations (
    organization_id VARCHAR(64) NOT NULL,
    operation_key VARCHAR(150) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    result_reference VARCHAR(150),
    PRIMARY KEY (organization_id, operation_key)
);
~~~

Khi retry, kiểm tra key, payload/version và business outcome trong cùng tenant.

### 29.1. Không coi duplicate cùng key nhưng khác payload là success

Nếu org-A gửi operation key X lần 1 với amount=100, lần 2 với amount=200, đó có thể là conflict, không phải cùng một command. So payload hash/version theo business policy.

### 29.2. Transaction và message ack

Consumer có thể commit DB rồi crash trước broker ack, dẫn đến redelivery. Unique idempotency key theo org giúp nhận biết đã xử lý, nhưng cần transaction boundary/outbox nếu có side effects khác.

## 30. Tenant-scoped logging và tracing

Context có thể cấp:

~~~text
organizationId = org-A
actorId        = user-17
correlationId  = trace-7788
jobId          = import-2026-11
~~~

Structured log minh họa:

~~~json
{
  "event": "order_import_completed",
  "organizationId": "org-A",
  "actorId": "system:import-worker",
  "correlationId": "trace-7788",
  "jobId": "import-2026-11",
  "recordCount": 500,
  "durationMs": 180
}
~~~

### 30.1. MDC cũng thường dựa vào ThreadLocal

Nếu dùng SLF4J MDC, phải propagation và cleanup giống organization context. Không suy rằng MDC và Hibernate tenant resolver luôn đồng bộ chỉ vì đều có `tenantId`.

### 30.2. Không log secrets hoặc raw tokens

Tenant ID thường không phải secret, nhưng metadata actor, resource IDs, headers và correlation data có thể chịu privacy requirements. Tránh log JWT/raw authentication headers hoặc payload nhạy cảm.

### 30.3. Metrics có cardinality cao

Nếu có 100.000 organizations, gắn organizationId vào mọi Prometheus metric label có thể gây nổ cardinality. Có thể dùng logs/traces theo org và metrics aggregate theo tier/region, hoặc tenant-specific monitoring có kiểm soát.

## 31. Chuyển organization trong cùng HTTP session

UI thường có lựa chọn “Switch organization”. Một request mới chọn org-B khác org-A.

### 31.1. Không đổi context đang chạy

Khi request A đang xử lý transaction org-A, việc user đổi org trên tab khác không nên làm transaction A chuyển sang org-B giữa chừng.

Mỗi request/task phải giữ một verified organization identity bất biến trong phạm vi xử lý.

### 31.2. Cache, pagination cursor và links phải đúng scope

Nếu người dùng đang xem orders của org-A với cursor phân trang, sau đó chuyển sang org-B, cursor cũ phải bị từ chối hoặc reset. Cursor có thể ràng buộc với org ID/filter fingerprint và được ký; không dùng cursor org-A để seek dữ liệu org-B.

### 31.3. Browser có nhiều tabs

Nếu active organization được lưu trong session server và người dùng mở hai tabs ở hai organizations, một global “current org in session” có thể gây race. Một lựa chọn an toàn hơn là truyền selected org cho mỗi request qua URL/header/token có kiểm soát, xác minh theo request.

Không dùng mutable session-global selection mà không hiểu concurrency/UX của multi-tab.

## 32. Cross-organization operations và super-admin

Một số use cases hợp lệ cần nhiều organizations:

- Billing tổng hợp.
- Platform administration.
- Migrate organization sang DB khác.
- Aggregate analytics liên org.
- Cross-org data transfer có sự đồng ý.

Đây không phải lý do để mọi request thiếu context mặc định “super-admin”.

### 32.1. Định nghĩa đường vận hành riêng

Ví dụ:

~~~text
PlatformAdminService
  -> xác minh platform permission riêng
  -> enumerate organizations được phép
  -> for each org:
         tạo verified org context
         mở transaction/session tenant tương ứng
         xử lý item
~~~

### 32.2. Một transaction không tự atomic trên nhiều databases

Nếu org-A và org-B nằm ở hai DB khác nhau, hai local JPA transactions không trở thành một distributed ACID transaction chỉ vì đặt `@Transactional` ở coordinator.

Nếu cần chuyển dữ liệu xuyên organizations, dùng saga, outbox, idempotent commands hoặc distributed transaction coordination có chủ đích. Ghi rõ partial failure/recovery policy.

### 32.3. Quyền platform admin phải được audit

Nếu một privileged operator chọn org khác, audit nên ghi actor thực và lý do/operation metadata. Không ghi mọi thao tác dưới `"system"` rồi mất dấu ai đã truy cập dữ liệu.

## 33. Transaction context, flush và commit

Khi org context xác định tenant cho Hibernate, vẫn phải tách:

- **Context selection**: dùng dữ liệu của org nào.
- **Persistence context**: các managed entities trong Session nào.
- **Transaction boundary**: thay đổi nào được commit/rollback cùng nhau.

Một thao tác `em.flush()` chỉ đồng bộ SQL với database trong transaction, không tự commit.

### 33.1. Không thay context sau flush

Giả sử:

~~~text
set org-A
begin transaction
persist Order A
flush
set org-B
persist Order B
commit
~~~

Đây không phải cách viết hai tenants an toàn. Session/connection có thể đang gắn org-A; đổi ThreadLocal giữa chừng có thể làm sai hoặc fail. Cần tách transactions.

### 33.2. OpenEntityManagerInView

Nếu ứng dụng bật OSIV, EntityManager có thể được mở/bind trong HTTP request ngoài business transaction. Đảm bảo tenant identity được xác định đúng **trước khi EntityManager/Session được khởi tạo hoặc tenant được resolve** theo tích hợp thực tế.

Không dùng OSIV để duy trì tenant context qua async workers sau HTTP response.

### 33.3. Lazy loading

Một entity được tải dưới org-A không nên bị đưa sang worker đang ở org-B rồi truy cập lazy relationship. Ngoài thread safety/detached entity problems, đó còn có rủi ro tenant confusion. Truyền ID/DTO, mở Session mới trong đúng verified org context.

## 34. Những lỗi nguy hiểm và dấu hiệu

| Lỗi | Hậu quả | Cách phòng |
| --- | --- | --- |
| Header orgId được tin trực tiếp | User chọn tenant không có quyền | Membership/action authorization |
| Fallback tenant mặc định | Thiếu context dẫn tới data leak | Fail closed |
| Singleton `currentOrg` | Request đồng thời ghi đè nhau | Context theo task/request |
| ThreadLocal không clear | Thread pool reuse org cũ | `finally` restore/remove |
| Dùng InheritableThreadLocal trong pool | Nhận org cũ/sai | Explicit handoff/decorator |
| @Async không truyền context | Worker thiếu tenant | Explicit command/TaskDecorator |
| @Scheduled đọc request scope | Không có HTTP request | System job policy + per-org context |
| Kafka listener đặt context sau transaction | Session tenant có thể chọn quá sớm | Entry point rồi transactional bean |
| Self-invocation `@Transactional` | Boundary không kích hoạt | Bean proxy khác/TransactionTemplate |
| Đổi org trong cùng Session | Tenant mismatch hoặc sai DB | Session/transaction per org |
| Shared-table query quên org predicate | Cross-tenant reads/writes | Enforced tenancy/RLS/tests |
| Native JDBC nghĩ Hibernate resolver tự áp | SQL không được tenant-filtered | Route/predicate/RLS riêng |
| Cache key chỉ có row ID | Cross-tenant cached data | Key gồm org |
| Unique key không có org | Collision giữa tenants | Composite unique constraints |
| FK không có org | Cross-tenant association | Composite FK/DB integrity |
| Retry message key không có org | Dedup nhầm tenants | Per-org idempotency |
| RLS setting còn ở pool connection | SQL của request sau dùng org cũ | Transaction-local/reset |
| Actor từ message không xác minh | Giả mạo principal | Verify producer/delegation |
| Async truyền EntityManager | Không thread-safe/tenant confusion | ID/DTO + Session riêng |
| Test luôn có outer transaction | Che lỗi tenant initialization | Test real entrypoint |
| Reuse org context khi membership bị thu hồi | Worker làm việc không còn quyền | Re-authorize durable jobs |
| Log raw token | Lộ credential | Redaction + structured metadata |

## 35. Kiểm thử HTTP multi-organization

Một bộ integration test với DB thật nên có **ít nhất hai organizations** và dữ liệu trùng business IDs khi schema cho phép.

### 35.1. Authentication/authorization matrix

| Actor | Organization | Role | Action | Mong đợi |
| --- | --- | --- | --- | --- |
| user-1 | org-A | ADMIN | VIEW | Cho phép |
| user-1 | org-A | ADMIN | DELETE | Cho phép nếu policy |
| user-1 | org-B | VIEWER | VIEW | Cho phép |
| user-1 | org-B | VIEWER | DELETE | Từ chối |
| user-2 | org-A | Không membership | VIEW | Từ chối |
| anonymous | org-A | — | VIEW | 401 theo API |
| service-worker | org-A | Job permission | IMPORT | Cho phép theo job policy |

Test phải xác nhận **không có dữ liệu org khác được trả**, không chỉ HTTP status.

### 35.2. Không tin raw header

Gửi header org-B với token user chỉ thuộc org-A. Server phải từ chối trước tenant-bound query. Kể cả raw header có định dạng hợp lệ, membership check là bắt buộc.

### 35.3. Tenant-safe search và sorting

Test repository search, count, pagination, bulk update và native SQL. Một query trả đúng Order by ID chưa chứng minh list/search query đã lọc org.

### 35.4. Đổi org giữa hai requests

Gửi hai requests liên tiếp qua cùng server thread/pool nếu có thể. Kết quả phải độc lập; request thiếu context không được tái sử dụng org của request trước.

## 36. Test thread pool không bị rò organization

Một test quan trọng là cho cùng executor worker xử lý nhiều tasks nối tiếp:

~~~java
@Test
void contextIsRestoredAfterTaskFailure() throws Exception {
    ExecutorService delegate =
        Executors.newSingleThreadExecutor();

    try {
        // Test fixture wrapTask là decorator hoặc carrier
        // thực tế mà hệ thống sử dụng.
        Future<?> first = delegate.submit(
            wrapWithOrg("org-A", () -> {
                assertThat(
                    OrganizationContextHolder
                        .require().organizationId()
                ).isEqualTo("org-A");

                throw new IllegalStateException("expected");
            })
        );

        assertThrows(ExecutionException.class, first::get);

        Future<String> second = delegate.submit(
            () -> {
                OrganizationContext current =
                    OrganizationContextHolder.currentOrNull();
                return current == null
                    ? "EMPTY"
                    : current.organizationId();
            }
        );

        assertThat(second.get()).isEqualTo("EMPTY");
    } finally {
        delegate.shutdownNow();
    }
}
~~~

`wrapWithOrg` là test helper cần triển khai dựa trên code carrier thực tế. Không nhất thiết phải dùng raw `ExecutorService` trong production; mục tiêu là ép **thread reuse** và xác minh cleanup khi task ném exception.

### 36.1. Test đúng TaskDecorator với Spring executor

Một integration test nên submit task qua chính `tenantExecutor` bean, không chỉ một executor mới thiếu decorator. Test capture org-A và org-B ở thời điểm submit, task nhận đúng org và không rò context sang task không có org.

### 36.2. Test nested scopes

~~~java
runWith(orgA, () -> {
    runWith(orgB, () -> {
        assertCurrentOrg("org-B");
    });
    assertCurrentOrg("org-A");
});
~~~

Sau outer scope, current phải trở về giá trị trước hoặc null.

### 36.3. Test thất bại trước set

Nếu authorization throw trước `set()`, context cũ cũng không được giữ hay được coi hợp lệ. Request filter phải có clear/restore trong mọi error path có thể.

## 37. Test Hibernate resolver và session affinity

Các test cần kiểm chứng:

1. Có verified org-A trước khi mở transaction → Hibernate chọn org-A.
2. Có verified org-B → chọn org-B.
3. Thiếu context → fail closed.
4. Mở Session org-A rồi đổi context sang org-B → không cho phép tiếp tục/không đọc B bằng Session A.
5. Trả connection org-A về pool rồi dùng org-B → schema/session vars đúng B, không rò A.
6. Truy vấn native và bulk DML có tenant protection.
7. Rollback và exception path cũng reset connections.
8. Membership check không phụ thuộc tenant resolver chưa sẵn sàng.

### 37.1. Schema-per-tenant test

Tạo cùng tên bảng nhưng dữ liệu khác nhau:

~~~text
tenant_a.purchase_orders: (id=1, status=PAID)
tenant_b.purchase_orders: (id=1, status=DRAFT)
~~~

Trong context org-A trả PAID, trong org-B trả DRAFT. Nếu chỉ test mỗi tenant có ID khác nhau, route bug có thể bị che.

### 37.2. Database-per-tenant test

Dùng hai databases hoặc schemas giả lập connection routing, xác minh datasource selection và pool release trên cả success/exception.

### 37.3. Shared-table test

Lưu org-A và org-B có cùng externalOrderId. Query/count/pagination/update/delete phải chỉ thay đổi scope được cấp quyền. Dùng database constraint để ngăn FK cross-tenant.

## 38. Test message consumer, retry và permission revocation

### 38.1. Message thiếu organizationId

Consumer phải reject/dead-letter theo policy, không default sang org trước đó.

### 38.2. Message có organizationId của user không có quyền

Consumer phải kiểm tra producer/actor authorization theo thời điểm xử lý. Không mở tenant session chỉ để xác minh quyền nếu membership thuộc global catalog.

### 38.3. Redelivery

Gửi cùng `messageId` hai lần trong cùng org → business outcome chỉ áp dụng theo idempotency contract. Gửi cùng messageId ở hai org khác nhau → không deduplicate nhầm.

### 38.4. Worker crash

Sau DB commit trước broker ack, test redelivery xác minh target không bị duplicate, audit/outbox phù hợp và context không bị rò.

### 38.5. Membership bị thu hồi

Job được lên lịch lúc actor còn quyền org-A, chạy sau khi quyền bị thu hồi. Test policy: có revalidate khi chạy, hoặc job chạy dưới service authority độc lập đã được cấp phép và audit rõ.

## 39. Thực hành xây một request-to-job flow

Giả sử user tải CSV để import Orders vào organization hiện hành.

### Bước 1 — Request xác định organization

~~~http
POST /organizations/org-A/order-imports
Authorization: Bearer <verified-token>
Content-Type: text/csv
~~~

Backend:

- Xác thực actor.
- Kiểm tra membership + permission `IMPORT_ORDERS`.
- Xác minh path org-A khớp scope.
- Tạo verified OrganizationContext.
- Lưu job record với `organization_id=org-A`, `requested_by=user-17`, `job_id=...`.
- Trả job ID.

### Bước 2 — Job command bền vững

~~~json
{
  "jobId": "import-9001",
  "organizationId": "org-A",
  "requestedBy": "user-17",
  "sourceFileId": "file-500",
  "correlationId": "trace-7788"
}
~~~

Message chỉ chứa IDs/correlation metadata cần thiết; không truyền Hibernate entity/Session hoặc raw security credential.

### Bước 3 — Worker xác minh lại

- Xác thực message producer.
- Tải job record từ global job catalog.
- So organization ID giữa message và job record.
- Kiểm tra organization còn active.
- Kiểm tra service account có quyền xử lý.
- Kiểm tra user permission nếu contract yêu cầu re-authorization.
- Tạo verified OrganizationContext cho job actor.

### Bước 4 — Mỗi chunk một transaction tenant-scoped

~~~text
Verified context org-A
  -> ImportChunkWriter bean proxy
     -> @Transactional
        -> Hibernate Session org-A
        -> INSERT Orders org-A
        -> checkpoint/ledger trong DB phù hợp
     -> commit
  -> cleanup context
~~~

Nếu các chunks có thể chạy trên các threads khác nhau, mỗi chunk worker phải thiết lập context trước transaction; không dựa vào ThreadLocal của job coordinator.

### Bước 5 — Retry và đối soát

- Key idempotency: `(organizationId, jobId, sourceItemKey)`.
- Batch failure: rollback chunk/transaction.
- Retry transaction mới, context được xác minh lại.
- Commit unknown: query target theo org + business key trên nguồn consistent, không retry mù.
- Log mọi job/chunk outcome với org ID.
- Từ chối một chunk nếu context thiếu hoặc scope mismatch.

### Bước 6 — Người dùng xem trạng thái

~~~http
GET /organizations/org-A/order-imports/import-9001
~~~

API kiểm tra actor có quyền xem job của org-A, không chỉ biết jobId. Nếu user gửi URL org-B với job của org-A thì trả lỗi theo policy mà không lộ job details.

## 40. Bài tập thực hành

### Bài 1 — Header không đáng tin

User có quyền ở org-A nhưng gửi `X-Organization-Id: org-B`. Backend nên làm gì trước khi gọi repository? Vì sao không thể tin header?

### Bài 2 — Multi-membership

User có ADMIN ở org-A và VIEWER ở org-B. Nếu chọn org-B rồi gọi DELETE, context selection và authorization nên trả kết quả nào?

### Bài 3 — Fail closed

Hãy viết pseudocode resolver khi không có organization context. Vì sao fallback sang `"default"` nguy hiểm?

### Bài 4 — ThreadLocal leak

Thread pool có một worker. Request 1 org-A kết thúc không clear, request 2 org-B thiếu org header. Mô tả hậu quả và cách sửa bằng `try/finally`.

### Bài 5 — Self-invocation

Một method `@Transactional` nằm cùng class và được gọi qua `this` sau khi đổi org context. Vì sao không chắc có transaction/session mới? Đề xuất cấu trúc hai beans.

### Bài 6 — Session affinity

Mở EntityManager khi context org-A, sau đó thay ThreadLocal sang org-B. Có nên tiếp tục query bằng EntityManager cũ không? Vì sao?

### Bài 7 — Hibernate resolver

Viết `CurrentTenantIdentifierResolver<String>` lấy organization ID từ verified context. Khi context thiếu nên làm gì? `validateExistingCurrentSessions()` có thay thế membership check không?

### Bài 8 — Database routing

Với schema-per-tenant, vì sao connection được trả pool phải reset schema/search_path? Vì sao không ghép raw org header vào SQL schema identifier?

### Bài 9 — Shared-table FK

OrderLine có orgId và orderId. Viết composite FK để ngăn line org-B tham chiếu Order org-A.

### Bài 10 — RLS

PostgreSQL RLS policy theo `current_setting('app.organization_id', true)` có tác dụng gì? Vì sao phải set transaction-local và không dùng DB role bypass RLS tùy tiện?

### Bài 11 — @Async

Request thread có org-A, worker `@Async` đọc ThreadLocal và gặp null. So sánh truyền explicit command và dùng `TaskDecorator`.

### Bài 12 — Decorator cleanup

Một task ném RuntimeException. Điều gì phải xảy ra với organization context trên worker thread? Vì sao `finally` là bắt buộc?

### Bài 13 — CompletableFuture

Tại sao `CompletableFuture.runAsync(task)` không được đảm bảo dùng Spring `tenantExecutor` đã gắn TaskDecorator? Sửa code thế nào?

### Bài 14 — Scheduler

Nightly job xử lý mọi active organizations. Thiết kế nơi tạo per-org context và nơi mở per-org transaction, tránh một outer transaction cho tất cả.

### Bài 15 — Spring Batch

Một chunk step chỉ set org trong `ItemWriter.write()`. Tại sao có thể quá muộn? Cần thiết lập context ở boundary nào?

### Bài 16 — Kafka

Một message chứa orgId nhưng người gửi không được xác thực. Vì sao consumer không được tin tenant ID đó? Nêu các bước verify trước khi transaction.

### Bài 17 — Retry/idempotency

Hai organizations cùng gửi messageId `msg-1`. Nếu dedup key chỉ là messageId, lỗi gì xảy ra? Thiết kế khóa phù hợp.

### Bài 18 — Reactor

Vì sao ThreadLocal không phải context carrier đúng cho reactive pipeline chuyển threads? Reactor Context và boundary blocking JPA cần xử lý thế nào?

### Bài 19 — Cache leak

Một Redis cache dùng key `order:123`. org-A và org-B có Order 123 khác nhau. Điều gì có thể xảy ra? Thiết kế key mới.

### Bài 20 — OSIV

Một HTTP request chọn org sau khi EntityManager đã bind vào thread. Tại sao có thể lỗi tenant selection? Điều chỉnh filter/transaction ordering thế nào?

### Bài 21 — Cross-org admin

Platform admin cần sửa dữ liệu org-A và org-B. Vì sao một ThreadLocal thay đổi giữa cùng transaction không phải cách đúng? Nếu hai org ở hai DB, atomicity ra sao?

### Bài 22 — Authorization revocation

Một import job được tạo lúc user có quyền, chạy sau 24 giờ khi membership bị thu hồi. Nên sử dụng user delegation hay service job authority, và revalidation policy nào?

### Bài 23 — Logging

Cần ghi organization ID trong logs/traces nhưng tránh nổ metric cardinality và lộ raw JWT. Thiết kế logging policy.

### Bài 24 — Native UPDATE

Viết SQL update trạng thái Order có tenant predicate và optimistic version. Nếu affected rows bằng 0, những khả năng nào cần xem xét?

### Bài 25 — Integration testing

Thiết kế test có hai organizations cùng Order ID, một task async, một worker thread reuse, một Kafka redelivery, một missing-org case, một raw SQL và một cache. Nêu các assertions nhằm chứng minh isolation.

### Gợi ý đáp án

- **Bài 1:** Xác thực token và membership/quyền trước khi dùng org-B; từ chối nếu không có quyền.
- **Bài 2:** Chọn org-B có thể hợp lệ, nhưng DELETE phải bị từ chối vì role VIEWER.
- **Bài 3:** Throw missing-context/authorization error; không tự route sang tenant mặc định.
- **Bài 4:** Request 2 có thể dùng org-A; cleanup `finally` và fail closed khi thiếu context.
- **Bài 5:** Self-call bypass transactional proxy; context trước khi gọi writer bean khác.
- **Bài 6:** Không; Session/connection/first-level cache có tenant affinity.
- **Bài 7:** `require()` fail closed; validateExistingCurrentSessions không làm authorization.
- **Bài 8:** Pool tái sử dụng connection; schema state nếu không reset có thể rò tenant; dùng server-side route catalog.
- **Bài 9:** FK `(organization_id, order_id)` tới unique `(organization_id,id)` của parent.
- **Bài 10:** RLS lọc DB-side; context phải ở cùng transaction/connection và DB role không bypass.
- **Bài 11:** Explicit command dễ bền vững/revalidate; decorator hữu ích cho short-lived in-process tasks.
- **Bài 12:** Restore/remove context dù exception; không để thread pool mang org cũ.
- **Bài 13:** Default common pool có thể không có decorator; truyền configured executor.
- **Bài 14:** Scheduler dùng global catalog chọn từng org, tạo context trước khi gọi transactional worker bean.
- **Bài 15:** Transaction/session có thể được mở trước ItemWriter; context phải có trước step/chunk transaction.
- **Bài 16:** Verify producer/message integrity/authorization, rồi tạo context trước transactional processing.
- **Bài 17:** Dedup nhầm org-B là duplicate của org-A; key `(orgId,messageId)`.
- **Bài 18:** Reactor Context gắn logical subscriber; bridge explicit sang blocking executor và tạo Session đúng scope.
- **Bài 19:** Cache cross-tenant leak; key nên gồm org ID + resource ID và các tham số cần thiết.
- **Bài 20:** Resolver có thể đã chọn tenant trước body; đặt verified context sớm hơn resource acquisition.
- **Bài 21:** Transaction/session per org; hai DB không tự có distributed atomicity, cần saga/outbox/coordination.
- **Bài 22:** Contract quyết định re-authorize user hoặc dùng audited service authority; không tin quyền cũ vô thời hạn.
- **Bài 23:** Structured logs/traces có org scope, redact secrets; metrics labels phải kiểm soát cardinality.
- **Bài 24:** `WHERE organization_id=:org AND id=:id AND version=:version`; 0 có thể not found/unauthorized/stale.
- **Bài 25:** Assert không đọc/ghi nhầm tenant, thiếu org fail, thread cleanup, message idempotency, cache keys phân biệt.

---

## Tổng kết

**Xác định tổ chức hiện tại là một bước bảo mật và định tuyến dữ liệu**, không phải việc lấy một chuỗi tenantId rồi đặt vào biến toàn cục. Để Hibernate/JPA hoạt động đúng trong môi trường nhiều tổ chức:

1. **Xác định và xác minh** organization từ request/job/message bằng authentication, membership và action authorization. Raw header, subdomain, JWT claim chưa xác minh hoặc message payload không tự là giấy phép truy cập.
2. **Thiết lập context trước transaction/Session creation**, giữ bất biến trong một unit of work. Không đổi tenant giữa một EntityManager đang hoạt động.
3. **Truyền context đúng theo boundary:** HTTP Servlet có thể dùng ThreadLocal với cleanup; `@Async`/executors cần explicit handoff hoặc TaskDecorator; scheduler, Spring Batch và Kafka cần durable org identity rồi verify khi xử lý; reactive flows cần Reactor Context.
4. **Bảo vệ dữ liệu ở persistence layer:** Hibernate tenant resolver/connection routing, shared-table tenant predicates, composite constraints và database RLS khi phù hợp. Native SQL, bulk DML, cache và idempotency keys cũng phải tenant-scoped.
5. **Kiểm thử cross-tenant và lifecycle**: hai org cùng IDs, executor thread reuse, missing context, permission revocation, pool cleanup, async retries và transaction ordering.

**Nguyên tắc quan trọng nhất:** Không có verified organization context thì **không thực hiện tenant-bound operation**. Có context đúng nhưng thiếu quyền thì vẫn phải từ chối; và sau khi tác vụ kết thúc phải dọn context để không làm rò dữ liệu sang tác vụ tiếp theo.
