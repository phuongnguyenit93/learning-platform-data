# Test method security

> **Chương:** Testing token security  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Bối cảnh:** Kiểm thử xác thực và phân quyền trong vòng đời token bảo mật; JWT, opaque token, access token, refresh token, claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại trong OAuth 2.0/OIDC.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích method security và xác định lớp kiểm soát quyền ở tầng service/business method.
2. Kiểm thử các annotation như **@PreAuthorize**, **@PostAuthorize**, **@PreFilter**, **@PostFilter**, **@Secured** và **@RolesAllowed**.
3. Phân biệt role, authority, OAuth scope và tenant claim trong các biểu thức phân quyền.
4. Tạo SecurityContext kiểm thử với user, JWT principal, scope và tenant context phù hợp.
5. Kiểm tra cả trường hợp được phép, bị từ chối, thiếu xác thực, sai tenant và gọi qua proxy.
6. Kết hợp method security tests với API integration tests, JWT decoder/introspection tests và kiểm thử quyền trên tài nguyên thực tế.

## 1. Method security là gì?

**Method security** là cơ chế thực thi authorization ngay tại phương thức của ứng dụng, thường ở service layer. Thay vì chỉ kiểm tra quyền ở controller hoặc API gateway, ứng dụng đặt chính sách lên method để mọi đường gọi đi qua Spring-managed bean đều phải tuân thủ.

Ví dụ một endpoint đọc đơn hàng có thể được bảo vệ bởi URL rule, nhưng cùng service đó cũng được gọi từ scheduled job, message consumer hoặc một service khác. Nếu chỉ kiểm tra quyền tại controller, những đường gọi còn lại có thể bỏ qua chính sách. Method security giúp đặt kiểm soát gần với nghiệp vụ hơn.

~~~mermaid
flowchart TD
    A["HTTP Controller"] --> S["OrderService method"]
    B["Message Consumer"] --> S
    C["Scheduled Job"] --> S
    D["Other Spring Service"] --> S
    S --> M["Method Security Interceptor"]
    M -->|Được phép| R["Business logic + Repository"]
    M -->|Bị từ chối| X["Access denied"]
~~~

Method security thường được triển khai bằng Spring AOP proxy và authorization interceptors. Khi caller gọi method qua proxy, Spring đánh giá Authentication, authorities và biểu thức authorization trước hoặc sau khi method chạy, tùy annotation.

**Method security không thay thế token validation.** Một access token phải được xác thực ở tầng security filter/resource server hoặc cơ chế tương ứng trước khi Authentication đáng tin được đưa vào SecurityContext. Method security sử dụng Authentication đó để quyết định quyền thực hiện nghiệp vụ.

## 2. Bật và cấu hình method security

Trong Spring Security hiện đại, có thể bật method security bằng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Với cấu hình mặc định, các annotation pre/post authorization được bật. Nếu dùng annotation kiểu cũ hoặc JSR-250, cần bật rõ ràng:

~~~java
@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfiguration {
}
~~~

| Annotation | Cấu hình cần thiết | Thời điểm kiểm tra |
|---|---|---|
| **@PreAuthorize** | Method security mặc định | Trước khi method chạy |
| **@PostAuthorize** | Method security mặc định | Sau khi method trả kết quả |
| **@PreFilter** | Method security mặc định | Lọc tham số collection trước khi method chạy |
| **@PostFilter** | Method security mặc định | Lọc collection kết quả sau khi method chạy |
| **@Secured** | securedEnabled = true | Kiểm tra authority trước method |
| **@RolesAllowed** | jsr250Enabled = true | Kiểm tra role trước method |

Không nên cho rằng chỉ thêm annotation là đủ. Phải xác nhận cấu hình method security thực sự được nạp trong Spring context, bean được quản lý bởi Spring và caller đi qua proxy được bảo vệ.

## 3. Role, authority và OAuth scope

Trong Spring Security, biểu thức method security thường so sánh GrantedAuthority.

- **Role** thường được biểu diễn bằng authority có prefix **ROLE_**, ví dụ **ROLE_ADMIN**.
- **Authority** là chuỗi quyền cụ thể, ví dụ **orders:approve**.
- **OAuth scope** thường được ánh xạ thành authority có prefix **SCOPE_**, ví dụ **SCOPE_orders.read**.

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void reconcileAllOrders() {
    // Chỉ role ROLE_ADMIN
}

@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Order getOrder(String orderId) {
    // Chỉ authority SCOPE_orders.read
}
~~~

**hasRole('ADMIN')** thường kiểm tra **ROLE_ADMIN** theo role prefix mặc định. **hasAuthority('SCOPE_orders.read')** so sánh chính xác chuỗi authority. Không trộn **hasRole('ROLE_ADMIN')** nếu role prefix đang tự thêm **ROLE_**, vì có thể tạo ra kiểm tra sai.

### Test phải phản ánh đúng cách ánh xạ token

Ví dụ JWT có claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "alice",
  "aud": "orders-api",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a",
  "exp": 1893456000
}
~~~

Resource Server có thể dùng JwtGrantedAuthoritiesConverter để ánh xạ scope thành **SCOPE_orders.read** và **SCOPE_orders.write**. Nếu ứng dụng có custom converter, tests phải kiểm tra converter đó. Một test tạo sẵn authority **SCOPE_orders.read** chỉ kiểm tra method authorization; nó chưa chứng minh claim scope từ JWT thật được ánh xạ đúng.

## 4. Các annotation cần kiểm thử

### 4.1. @PreAuthorize

Đánh giá biểu thức trước khi method thực thi. Đây là annotation phổ biến nhất để kiểm tra role, scope, subject, tenant hoặc quyền trên resource.

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Order findOrder(String orderId) {
    return repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);
}
~~~

Test cần có:

- Principal có scope phù hợp: method được gọi.
- Principal thiếu scope: method bị từ chối.
- Principal chỉ có role không liên quan: bị từ chối.
- Không có Authentication: bị từ chối.
- Scope có sai chính tả hoặc prefix: bị từ chối.

### 4.2. @PostAuthorize

Đánh giá biểu thức sau khi method trả kết quả. Có thể dùng để kiểm tra ownership của object trả về.

~~~java
@PostAuthorize("@tenantPolicy.canRead(authentication, returnObject)")
public Order findOrder(String orderId) {
    return repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);
}
~~~

Test phải xác nhận dữ liệu của tenant hiện tại được trả về và dữ liệu tenant khác bị từ chối. Cần lưu ý method đã chạy và có thể đã truy vấn dữ liệu trước khi post-authorization được đánh giá. Không dùng @PostAuthorize làm cơ chế duy nhất cho method có side effect như chuyển tiền, xóa hoặc cập nhật dữ liệu.

### 4.3. @PreFilter và @PostFilter

**@PreFilter** lọc phần tử đầu vào trước khi method thực thi. **@PostFilter** lọc phần tử collection sau khi method trả kết quả.

~~~java
@PreFilter("filterObject.tenantId == authentication.tokenAttributes['tenant_id']")
public void updateOrders(List<OrderCommand> commands) {
    // Xử lý collection sau khi lọc
}

@PostFilter("filterObject.tenantId == authentication.tokenAttributes['tenant_id']")
public List<Order> findVisibleOrders() {
    return repository.findAll();
}
~~~

Cú pháp truy cập claim phụ thuộc kiểu Authentication và cấu hình ứng dụng. Trong thực tế nên cân nhắc bean policy chuyên biệt thay vì lặp biểu thức SpEL phức tạp.

Không nên dùng @PostFilter để thay thế tenant predicate ở database: method có thể đã tải toàn bộ dữ liệu trước khi lọc, gây tốn tài nguyên và tăng nguy cơ lộ dữ liệu qua count, timing hoặc log. Với bulk update, cần xác định rõ atomic reject hay per-item authorization.

### 4.4. @Secured và @RolesAllowed

Hai annotation này có thể xuất hiện trong codebase cũ:

~~~java
@Secured("ROLE_FINANCE")
public void closeSettlement() {
}

@RolesAllowed({"ADMIN", "AUDITOR"})
public AuditReport readAuditReport() {
    return reportService.create();
}
~~~

Test cần xác nhận đã bật **securedEnabled** hoặc **jsr250Enabled**. **@RolesAllowed** dùng tên role theo semantics JSR-250 và cách mapping role cần được thống nhất trong ứng dụng.

## 5. Đặt authorization tại method theo nghiệp vụ

Một method service nên thể hiện quyền cần thiết một cách rõ ràng:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @tenantPolicy.canRead(authentication, #orderId)"
    )
    public Order getOrder(@P("orderId") String orderId) {
        return repository.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.write') " +
        "and @tenantPolicy.canModify(authentication, #orderId)"
    )
    public void cancelOrder(@P("orderId") String orderId) {
        repository.markCancelled(orderId);
    }
}
~~~

Ví dụ này kết hợp scope với tenant/resource policy. **@tenantPolicy** là Spring bean được gọi từ SpEL; nó phải lấy tenant context từ Authentication đã xác thực và kiểm tra quan hệ với resource ở server-side.

Ví dụ policy ở mức khái niệm:

~~~java
@Component("tenantPolicy")
public class TenantPolicy {

    private final OrderRepository repository;

    public TenantPolicy(OrderRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, String orderId) {
        String tenantId = verifiedTenant(authentication);
        return tenantId != null
            && repository.findTenantId(orderId)
                .filter(tenantId::equals)
                .isPresent();
    }

    private String verifiedTenant(Authentication authentication) {
        if (authentication instanceof JwtAuthenticationToken jwtAuth) {
            return jwtAuth.getToken().getClaimAsString("tenant_id");
        }
        return null;
    }
}
~~~

Đây là ví dụ minh họa. Nếu người dùng có thể thuộc nhiều tenant, policy còn phải xác minh membership và tenant đang hoạt động. Không lấy tenant ID từ request header rồi coi nó là claim đã xác thực.

### Tham số method trong SpEL

Biểu thức **#orderId** cần Spring Security nhận diện được tên tham số. Có thể biên dịch với tùy chọn **-parameters** hoặc dùng annotation **@P("orderId")** của Spring Security. Nếu parameter name không được nhận diện, biểu thức có thể lỗi lúc chạy hoặc không hoạt động như mong muốn.

## 6. Kiểm thử trực tiếp method security bằng Spring Test

Để kiểm thử annotation, cần gọi **Spring-managed bean qua proxy**. Không tự tạo service bằng **new**, vì object đó không được method-security interceptor bảo vệ.

Ví dụ test scope:

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootTest
class OrderMethodSecurityTest {

    @Autowired
    OrderService orderService;

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void userWithReadScopeCanRead() {
        authenticateAs("alice", "tenant-a", "SCOPE_orders.read");
        assertDoesNotThrow(() -> orderService.getOrder("order-a1"));
    }

    @Test
    void readOnlyUserCannotCancelOrder() {
        authenticateAs("alice", "tenant-a", "SCOPE_orders.read");
        assertThrows(
            AccessDeniedException.class,
            () -> orderService.cancelOrder("order-a1")
        );
    }

    @Test
    void unrelatedScopeCannotReadOrder() {
        authenticateAs("alice", "tenant-a", "SCOPE_profile.read");
        assertThrows(
            AccessDeniedException.class,
            () -> orderService.getOrder("order-a1")
        );
    }
}
~~~

Test trên giả định test database có fixture **order-a1** thuộc tenant A và **tenantPolicy** có thể xác nhận tenant context. Helper **authenticateAs** được khai báo trong mục tiếp theo và tạo JWT Authentication giả với tenant claim cùng authorities.

Với method chỉ kiểm tra role/authority mà không đọc JWT claims, có thể dùng **@WithMockUser** để thiết lập Authentication ngắn gọn. Annotation này không kiểm tra việc JWT decoder xác minh chữ ký, issuer, audience hoặc ánh xạ claims thật.

## 7. Tạo SecurityContext kiểm thử có JWT và tenant claim

Khi method policy cần tenant claim, test có thể tạo **JwtAuthenticationToken** giả lập. Việc này hữu ích cho method-level authorization tests, nhưng token được tạo trực tiếp trong test **không trải qua chữ ký JWT decoder**.

~~~java
import java.time.Instant;
import java.util.Arrays;
import java.util.List;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

private static void authenticateAs(
        String subject,
        String tenantId,
        String... authorities
) {
    Instant now = Instant.now();

    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "none")
        .subject(subject)
        .issuedAt(now)
        .expiresAt(now.plusSeconds(300))
        .claim("tenant_id", tenantId)
        .build();

    List<GrantedAuthority> granted = Arrays.stream(authorities)
        .map(SimpleGrantedAuthority::new)
        .map(authority -> (GrantedAuthority) authority)
        .toList();

    SecurityContext context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(new JwtAuthenticationToken(jwt, granted));
    SecurityContextHolder.setContext(context);
}
~~~

Đặt helper này bên trong class **OrderMethodSecurityTest** ở mục trước. Sau đó có thể viết thêm test:

~~~java
@Test
void tenantACannotReadTenantBOrder() {
    authenticateAs(
        "alice",
        "tenant-a",
        "SCOPE_orders.read"
    );

    assertThrows(
        AccessDeniedException.class,
        () -> orderService.getOrder("order-b1")
    );
}
~~~

Test cần dữ liệu **order-b1** thực sự thuộc tenant B. Cũng cần test chiều ngược lại: subject tenant B không thể đọc resource tenant A. Việc chỉ kiểm tra một chiều có thể bỏ sót lỗi mapping hoặc dữ liệu fixture.

Không nên dùng JWT **alg=none** trong môi trường ứng dụng. Header đó chỉ xuất hiện trong ví dụ tạo đối tượng Jwt trực tiếp để test method policy; nó không phải cách phát hành hoặc xác minh token production.

## 8. Kiểm thử qua MockMvc và JWT request postprocessor

Method security thường kết hợp với request-level security. MockMvc có thể giúp kiểm tra controller, filter chain và method security trong cùng một request.

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void jwtWithReadScopeCanReadOrder() throws Exception {
    mvc.perform(get("/api/orders/order-a1")
            .with(jwt()
                .jwt(token -> token
                    .subject("alice")
                    .claim("tenant_id", "tenant-a")
                    .claim("scope", "orders.read"))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                )))
        .andExpect(status().isOk());
}

@Test
void jwtTenantACannotReadTenantBOrder() throws Exception {
    mvc.perform(get("/api/orders/order-b1")
            .with(jwt()
                .jwt(token -> token
                    .subject("alice")
                    .claim("tenant_id", "tenant-a"))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                )))
        .andExpect(status().isForbidden());
}
~~~

**jwt()** là request postprocessor của Spring Security Test để gắn JWT Authentication giả vào request. Nó giúp kiểm tra authorization và controller flow, nhưng **không kiểm tra chữ ký JWT thật, JWKS retrieval hoặc issuer validation**. Nếu endpoint dùng policy trả 404 để tránh tiết lộ resource, hãy điều chỉnh assertion theo API contract.

### Khi nào dùng từng cách?

| Cách test | Phạm vi kiểm tra | Giới hạn |
|---|---|---|
| **@WithMockUser** | Method role/authority | Không mô phỏng JWT claims |
| Tạo **JwtAuthenticationToken** | Method policy cần subject/tenant claims | Bỏ qua JWT decoder và chữ ký |
| MockMvc **jwt()** | Request filter/controller/method authorization với JWT giả | Không kiểm tra chữ ký/issuer thực |
| Integration test với JWT ký thật | Decoder, issuer, audience, signature và authorization | Cần test key/issuer fixture |
| Opaque token introspection test | Introspection client, active state và metadata | Cần mock hoặc test Authorization Server |

## 9. Kiểm thử @PostAuthorize, ownership và object-level authorization

Một test chỉ kiểm tra scope có thể chưa phát hiện lỗi truy cập object của tenant khác. Cần test cả subject/tenant và resource.

Ví dụ ma trận:

| Principal | Scope | Resource | Kết quả |
|---|---|---|---|
| Alice, tenant A | orders.read | order-a1 | Cho phép |
| Alice, tenant A | orders.read | order-b1 | Từ chối |
| Alice, tenant A | orders.write | order-a1 | Cho phép nếu policy cho phép sửa |
| Alex, tenant A | orders.read | order-a1 | Cho phép đọc |
| Alex, tenant A | orders.write | order-a1 | Từ chối |
| Bob, tenant B | orders.read | order-a1 | Từ chối |
| Không có Authentication | bất kỳ | order-a1 | Từ chối |

### Kiểm tra ownership sau khi lấy object

~~~java
@PostAuthorize(
    "returnObject.tenantId == authentication.tokenAttributes['tenant_id']"
)
public Order loadForDisplay(String orderId) {
    return repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);
}
~~~

Đây là biểu thức minh họa cho Authentication có token attributes. Nếu ứng dụng dùng principal khác, hãy dùng policy bean để đọc tenant context đúng kiểu.

Test cần bao gồm:

- Object thuộc tenant hiện tại.
- Object thuộc tenant khác.
- Object không tồn tại.
- Principal không có tenant claim.
- Token có tenant claim không hợp lệ hoặc membership đã bị thu hồi.
- Policy bean ném lỗi khi dữ liệu quyền không thể xác minh.

Khi membership store hoặc policy service không khả dụng, quyết định bảo mật nên **fail closed** cho thao tác cần xác minh tenant, thay vì mặc định cho phép.

## 10. Kiểm thử pre-filter, post-filter và bulk operations

Với method nhận collection, test cần xác định chính xác phần tử nào được phép xử lý.

~~~java
@PreFilter(
    filterTarget = "commands",
    value = "@tenantPolicy.canModify(authentication, filterObject.orderId)"
)
public void cancelOrders(List<OrderCommand> commands) {
    // Thực hiện sau khi filter
}
~~~

Ví dụ test cần kiểm tra:

- Danh sách chỉ có resource của tenant hiện tại.
- Danh sách trộn resource thuộc tenant A và B.
- Danh sách rỗng.
- Một phần tử không tồn tại.
- Một phần tử thiếu quyền nhưng các phần tử khác có quyền.
- Kết quả và side effect có khớp chính sách atomic/partial success không.

**@PreFilter** có thể thay đổi collection trước khi method chạy, nhưng không tự định nghĩa hợp đồng bulk operation. Nếu yêu cầu atomic reject, hãy validate toàn bộ danh sách và từ chối trước khi ghi bất kỳ thay đổi nào. Nếu partial success được cho phép, trả kết quả từng phần tử theo contract rõ ràng.

**@PostFilter** chỉ lọc kết quả sau khi method đã truy vấn dữ liệu. Đối với dữ liệu nhạy cảm hoặc collection lớn, ưu tiên truy vấn đã có tenant predicate ở repository/database.

## 11. Những lỗi khiến method security test không phát hiện được lỗ hổng

### 11.1. Tự tạo object bằng new

~~~java
OrderService service = new OrderService(repository);
service.cancelOrder("order-a1");
~~~

Object tự tạo không đi qua Spring proxy nên annotation method security có thể không được thực thi. Test phải lấy bean từ Spring context hoặc dùng cấu hình test tạo proxy tương đương production.

### 11.2. Self-invocation

~~~java
@Service
public class ReportService {

    public Report readForCurrentUser(String id) {
        return this.readInternal(id);
    }

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public Report readInternal(String id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

Khi **readForCurrentUser** gọi **this.readInternal**, lời gọi nội bộ không đi qua proxy như một lời gọi từ bean khác. Annotation trên **readInternal** có thể bị bỏ qua.

Cách xử lý thường tốt hơn là chuyển method được bảo vệ sang một Spring bean riêng, để caller gọi qua proxy. Không thiết kế test chỉ gọi trực tiếp method có annotation rồi kết luận mọi đường nội bộ đều an toàn.

### 11.3. Method/class không thể được proxy như mong đợi

Spring AOP proxy có giới hạn với class/method final và cách dùng JDK/CGLIB proxy. Cần bảo đảm method cần bảo vệ có thể được intercept theo proxy strategy của ứng dụng. Kiểm tra bean thực tế trong Spring context thay vì chỉ kiểm tra annotation tồn tại trên source code.

### 11.4. Test chỉ mock service

Nếu controller test mock toàn bộ OrderService, method security bên trong service không được chạy. Controller test đó chỉ xác nhận routing/response. Cần thêm test tích hợp gọi bean service thật qua proxy.

### 11.5. Không bật method security trong test profile

Một test configuration có thể vô tình bỏ qua **@EnableMethodSecurity** hoặc import nhầm application configuration. Nên có test xác nhận một request thiếu quyền thật sự bị từ chối khi gọi bean trong context test.

### 11.6. Dùng principal giả không giống production

Production dùng **JwtAuthenticationToken** với scope và tenant claims, nhưng test chỉ dùng **@WithMockUser** với role. Test có thể xanh trong khi mapping claims hoặc tenant policy bị lỗi. Cần một nhóm test dùng đúng loại Authentication và một nhóm integration test xác minh decoder.

## 12. Kiểm thử method security với JWT và opaque token

Method security chỉ thấy Authentication và authorities được tạo ra trước đó. Vì vậy cần phân chia trách nhiệm test:

### JWT access token

Kiểm thử riêng:

- Chữ ký hợp lệ và chữ ký sai.
- Issuer đúng/sai.
- Audience đúng/sai.
- Expired token và token chưa có hiệu lực.
- Thuật toán không được phép.
- JWKS key rotation và unknown kid.
- Claim scope được ánh xạ thành authority đúng.
- Tenant claim được resolve và membership được xác minh.
- Token có loại sai, ví dụ ID token dùng thay access token.

Method security tests sau đó xác nhận authority/claims đã được ánh xạ dẫn tới quyết định cho phép/từ chối đúng.

### Opaque access token

Kiểm thử riêng:

- Introspection trả active=true và active=false.
- Introspection endpoint timeout hoặc lỗi.
- Token hết hạn/thu hồi.
- Client authentication với introspection endpoint.
- Scope, subject, audience và tenant metadata được ánh xạ.
- Cache introspection không giữ trạng thái active quá thời gian policy cho phép.

Sau khi resource server tạo Authentication, method security tests kiểm tra cùng các quyền nghiệp vụ như JWT.

### Không gộp mọi lỗi thành 403

Ở HTTP boundary, token thiếu/sai/hết hạn thường dẫn đến **401 Unauthorized**; người đã xác thực nhưng thiếu quyền thường dẫn đến **403 Forbidden**. Khi gọi trực tiếp service method trong test, Spring có thể ném exception như **AccessDeniedException** hoặc exception liên quan đến authentication. Hãy kiểm tra exception ở tầng method và status code ở tầng MockMvc theo đúng contract.

## 13. Kiểm thử async và SecurityContext propagation

SecurityContext trong ứng dụng servlet truyền thống thường gắn với thread hiện tại. Khi method tạo task chạy trong executor khác, không nên giả định Authentication tự động được truyền sang thread mới.

Các trường hợp cần test:

- **@Async** gọi service được bảo vệ.
- Scheduled task chạy không có user context.
- Message consumer nhận event và dùng workload identity riêng.
- Executor có cấu hình **DelegatingSecurityContextExecutor** hoặc cơ chế propagation tương đương.
- Context được clear sau task để không rò principal giữa các request.
- Reactive pipeline dùng Reactor Context thay vì giả định ThreadLocal hoạt động như servlet thread.

Với background job, thường nên dùng **workload identity/service principal** và quyền hẹp thay vì sao chép bearer token người dùng vào queue. Nếu nghiệp vụ cần giữ ngữ cảnh người dùng, dùng token exchange/delegation theo policy và giới hạn audience, scope, lifetime.

## 14. Kiểm thử method security theo nhiều lớp

Một bộ kiểm thử tốt không chỉ có một loại test.

| Lớp kiểm thử | Mục tiêu | Ví dụ |
|---|---|---|
| Unit test policy bean | Quy tắc tenant/ownership | Tenant A không đọc order B |
| Method security integration | Annotation thực sự được intercept | Thiếu SCOPE_orders.write bị từ chối |
| Controller/MockMvc | Filter chain, endpoint và method security | JWT giả có scope đúng/sai |
| JWT decoder integration | Xác minh chữ ký và claims | Sai issuer/audience/exp bị từ chối |
| Opaque token integration | Introspection và trạng thái token | active=false bị từ chối |
| Database integration | Tenant predicate/RLS và object ownership | Query không trả dữ liệu tenant khác |
| Async/concurrency test | Context propagation và isolation | Hai request song song không lẫn principal |
| End-to-end test | Chuỗi gateway/service/authorization server | Token exchange đúng audience/scope |

### Negative tests là bắt buộc

Các test sau thường phát hiện lỗ hổng tốt hơn việc chỉ kiểm tra một user admin được phép:

- User đã đăng nhập nhưng không có scope.
- Có scope đọc nhưng không có scope ghi.
- Role admin của tenant A nhưng resource thuộc tenant B.
- JWT đúng chữ ký nhưng sai audience.
- Opaque token đã bị revoke.
- Token hết hạn giữa lúc xử lý hoặc sau cache.
- Principal thiếu tenant claim.
- Actor/service hợp lệ nhưng subject không có quyền.
- Method bị gọi qua self-invocation hoặc bean không có proxy.
- Background thread thiếu SecurityContext.
- Policy service lỗi hoặc không thể xác minh membership.

## 15. Ví dụ kiểm tra quyền bằng bảng test

Một test matrix có thể biểu diễn bằng dữ liệu:

| Subject | Tenant claim | Authorities | Method | Resource tenant | Kết quả |
|---|---|---|---|---|---|
| Alice | tenant-a | SCOPE_orders.read | getOrder | tenant-a | Allow |
| Alice | tenant-a | SCOPE_orders.read | getOrder | tenant-b | Deny |
| Alice | tenant-a | SCOPE_orders.read | cancelOrder | tenant-a | Deny |
| Alice | tenant-a | SCOPE_orders.write | cancelOrder | tenant-a | Allow |
| Bob | tenant-b | SCOPE_orders.read | getOrder | tenant-b | Allow |
| Bob | tenant-b | SCOPE_orders.read | getOrder | tenant-a | Deny |
| Service A | tenant-a | SCOPE_inventory.read | readInventory | tenant-a | Allow |
| Service A | tenant-a | SCOPE_inventory.read | updateInventory | tenant-a | Deny |
| Alice | missing | SCOPE_orders.read | getOrder | tenant-a | Deny |
| Unauthenticated | none | none | getOrder | tenant-a | Deny |

Bảng này cần được mở rộng theo role, membership, trạng thái resource, token issuer/audience và policy đặc biệt của hệ thống. Không dùng một test admin toàn quyền làm đại diện cho mọi principal.

## 16. Audit và quan sát kết quả authorization

Method security denial cần có thông tin đủ để điều tra nhưng không tiết lộ token hoặc dữ liệu tenant khác.

Audit event có thể gồm:

- Thời điểm, correlation ID/trace ID.
- Subject ID và actor/workload identity đã xác thực.
- Tenant context server-side đã resolve.
- Tên method hoặc action code.
- Resource ID theo chính sách phân loại dữ liệu.
- Policy decision và mã lý do từ chối.
- Client ID, issuer hoặc token ID nếu được phép ghi.

Không log raw access token, refresh token, client secret hoặc private key. Không đưa toàn bộ claims vào log chỉ để tiện debug; một số claim có thể chứa thông tin cá nhân hoặc dữ liệu nhạy cảm.

Test audit cần xác nhận:

- Có event cho cả allow và deny theo yêu cầu.
- Tenant và subject trong event lấy từ context đã xác minh.
- Không có token trong message/log.
- Denial không làm lộ resource của tenant khác.
- Retry hoặc duplicate event không tạo side effect ngoài ý muốn.

## 17. Checklist trước khi xác nhận method security

- **@EnableMethodSecurity** đã được nạp trong production và test context chưa?
- Bean cần bảo vệ có phải Spring-managed proxy không?
- Mọi caller đều đi qua proxy hay có self-invocation/direct construction?
- Role và scope được ánh xạ đúng authority chưa?
- JWT decoder kiểm tra issuer, audience, chữ ký, thời hạn và loại token chưa?
- Opaque token introspection có kiểm tra active và metadata chưa?
- Tenant context đến từ claim/membership đáng tin hay từ header không xác thực?
- Policy kiểm tra cả method permission lẫn object-level ownership chưa?
- **@PostAuthorize** có đang được dùng trên method có side effect không?
- **@PostFilter** có thay thế database tenant filtering một cách nguy hiểm không?
- Async executor có propagation/clear SecurityContext đúng không?
- Negative tests có bao gồm thiếu scope, sai tenant, sai audience, token revoke và cache/context leakage không?
- Có integration tests gọi bean thật và kiểm tra HTTP response thật không?
- Audit có ghi đúng subject/actor/tenant mà không lộ credential không?

## 18. Tổng kết

**Test method security** xác nhận các quy tắc authorization được thực thi ngay tại service method, bất kể lời gọi đến từ controller, service khác, job hay consumer. Với Spring Security, cần bật method security, gọi bean qua proxy và kiểm tra các annotation pre/post authorization theo đúng loại Authentication production sử dụng.

Trong hệ thống token security, method authorization cần làm việc cùng token validation: JWT hoặc opaque token phải được xác minh trước; claims như subject, audience, scope và tenant phải được ánh xạ đúng; service sau đó kiểm tra quyền nghiệp vụ và quyền trên từng resource. Một test chỉ dùng user giả với role admin không đủ chứng minh toàn bộ chuỗi này an toàn.

Bộ test tốt phải bao gồm trường hợp được phép và bị từ chối, tenant khác, thiếu scope, sai audience, token hết hạn/thu hồi, proxy/self-invocation, async context, database isolation và audit. **Mục tiêu là mọi đường gọi tới nghiệp vụ đều thực thi đúng chính sách, và không có principal nào vượt qua quyền chỉ vì gọi service từ một đường khác.**
