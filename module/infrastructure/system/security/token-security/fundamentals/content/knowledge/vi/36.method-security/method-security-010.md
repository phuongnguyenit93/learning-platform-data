# Không chỉ bảo vệ controller: Method Security ở tầng nghiệp vụ

## 1. Vì sao đặt quyền ở controller là chưa đủ?

Một API quản lý đơn hàng có thể bảo vệ đường dẫn `DELETE /api/orders/{id}` bằng rule yêu cầu `SCOPE_orders:write`. Khi ứng dụng phát triển, cùng thao tác hủy đơn có thể được gọi từ GraphQL resolver, một endpoint quản trị khác, job xử lý tự động hoặc một handler tiêu thụ message. Nếu việc kiểm quyền chỉ tồn tại ở controller REST ban đầu, đường gọi mới có thể **vô tình bỏ qua chính sách**.

Trong Spring Security, **Method Security** giúp áp dụng chính sách ngay tại phương thức nghiệp vụ được Spring quản lý, thường là application service hoặc service quan trọng. Dù phương thức được gọi qua controller nào, quy tắc bảo vệ của service vẫn có cơ hội được thực thi khi lời gọi đi qua interceptor/proxy của Spring Security.

Bài này thuộc chương **Method security** trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Phạm vi liên quan đến mô hình tin cậy và vòng đời token: phân biệt JWT/opaque token, access token/refresh token; xác thực Bearer token trong OAuth 2.0/OIDC; kiểm tra claims, issuer, audience, thời hạn, scope; ánh xạ `GrantedAuthority`; xử lý thu hồi và nguy cơ token bị đánh cắp hoặc phát lại.

Trọng tâm là nguyên tắc **không chỉ bảo vệ controller**: xác thực ở biên hệ thống, kiểm quyền ở đúng chỗ thực hiện nghiệp vụ, và giữ quyền truy cập dữ liệu ở mức tối thiểu.

Các ví dụ dùng **Java, Spring Security 6, Spring Boot 3, ứng dụng Servlet và OAuth 2.0 Resource Server**. Đoạn mã domain được lược giản để làm rõ policy; cần bổ sung các lớp repository, DTO và imports theo dự án.

### Sau bài này, bạn có thể

1. Giải thích điểm yếu của việc chỉ cấu hình bảo vệ URL hoặc dùng annotation tại controller.
2. Phân biệt xác thực access token, kiểm authority ở endpoint, Method Security và kiểm quyền trên từng đối tượng dữ liệu.
3. Dùng `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize` và những cơ chế liên quan đúng mục đích.
4. Thiết kế chính sách scope, ownership và tenant tại service mà không tin dữ liệu do client tự khai.
5. Nhận biết giới hạn Spring AOP proxy, self-invocation, final/private method, async và những entry point không phải HTTP.
6. Kiểm thử service được bảo vệ qua proxy cùng các đường gọi ngoài controller và qua Resource Server thật.
7. Hiểu vì sao Method Security không thay thế kiểm signature/audience, thu hồi token hay kiểm soát đồng thời ở cơ sở dữ liệu.

## 2. Bốn lớp kiểm soát cần phối hợp

| Lớp | Câu hỏi bảo mật | Ví dụ |
|---|---|---|
| **Xác thực ở biên** | Credential có hợp lệ, còn hạn, do issuer tin cậy phát hành và dành cho tài nguyên này không? | Resource Server xác minh JWT hoặc introspect opaque access token, kiểm `iss`, `aud`, `exp` và điều kiện khác. |
| **HTTP/route authorization** | Route này cần authenticated caller hoặc authority nào? | `requestMatchers(GET, "/api/orders/**").hasAuthority("SCOPE_orders:read")`. |
| **Method Security** | Phương thức nghiệp vụ nào được phép chạy, dù ai gọi nó? | `@PreAuthorize("hasAuthority('SCOPE_orders:read')")` trên `OrderService.readOrder`. |
| **Object/tenant authorization** | Actor có được thao tác trên **đơn hàng cụ thể** này không? | Đơn hàng thuộc đúng tenant và owner; chính sách duyệt/hủy đúng trạng thái. |

Mỗi lớp trả lời một câu hỏi khác. **Token hợp lệ** chưa bảo đảm scope phù hợp; **scope phù hợp** chưa bảo đảm người gọi sở hữu tài nguyên; **controller có rule** chưa bảo đảm tất cả các entry point đều áp dụng cùng quy tắc.

Ví dụ: người dùng có access token với `scope=orders:read`. Spring Security thường ánh xạ scope đã xác thực thành `SCOPE_orders:read`. Người đó có thể được phép gọi tính năng “đọc đơn hàng”, nhưng vẫn phải bị từ chối nếu `order-42` là đơn của tenant khác.

### Sơ đồ các đường gọi

~~~mermaid
flowchart TD
    HTTP[REST Controller] --> SERVICE[OrderApplicationService]
    GQL[GraphQL Resolver] --> SERVICE
    ADMIN[Admin Endpoint] --> SERVICE
    JOB[Job / Message Handler] --> SERVICE
    SERVICE --> GUARD[Method Security interceptor]
    GUARD --> POLICY[Authority + ownership/tenant policy]
    POLICY --> DOMAIN[Domain logic]
    DOMAIN --> DB[(Database)]
    TOKEN[JWT / opaque validation tại HTTP boundary] -. cung cấp Authentication .-> HTTP
    TOKEN -. cung cấp Authentication .-> GQL
    TOKEN -. cung cấp Authentication .-> ADMIN
    SYSTEM[Dedicated system identity/policy] -. cho luồng nội bộ phù hợp .-> JOB
~~~

Trong thực tế, interceptor Method Security phải chạy **trước khi thân phương thức được thực thi** nếu dùng `@PreAuthorize`. Sơ đồ thể hiện mối quan hệ logic của guard với service; luồng gọi chỉ được bảo vệ khi invocation thực sự đi qua cơ chế Spring AOP.

Một job không có người dùng đang đăng nhập thường **không có SecurityContext của HTTP request**. Nó cần một chính sách riêng hoặc một danh tính hệ thống có quyền tối thiểu được thiết kế rõ ràng. Không tự gán `ROLE_ADMIN` cho toàn bộ job để làm cho service “chạy được”.

## 3. Controller security dễ bỏ sót những trường hợp nào?

Xét cách triển khai ban đầu:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @DeleteMapping("/{orderId}")
    @PreAuthorize("hasAuthority('SCOPE_orders:write')")
    void cancel(@PathVariable UUID orderId) {
        service.cancelOrder(orderId);
    }
}

@Service
class OrderService {
    void cancelOrder(UUID orderId) {
        // Thao tác thay đổi trạng thái đơn hàng.
    }
}
~~~

Controller có annotation kiểm scope, nhưng service không có chính sách nào. Nếu sau đó xuất hiện:

~~~java
@RestController
@RequestMapping("/api/internal/orders")
class NewOrderController {
    private final OrderService service;

    NewOrderController(OrderService service) {
        this.service = service;
    }

    @DeleteMapping("/{orderId}")
    void cancelViaNewRoute(@PathVariable UUID orderId) {
        service.cancelOrder(orderId);
    }
}
~~~

Mọi thứ phụ thuộc vào việc filter chain/route mới có rule đủ chặt không. Nếu route mới vô tình được cấu hình `permitAll()` hoặc chỉ `authenticated()`, phương thức hủy đơn có thể chạy thiếu `orders:write`. Nếu service được gọi từ ngoài HTTP, annotation của controller ban đầu cũng không tham gia.

**Chính sách thực sự thuộc về hành động “hủy đơn” nên cần có mặt tại application service**, nơi thao tác được thực hiện. URL security vẫn hữu ích để từ chối request sớm, nhưng không phải nơi duy nhất quyết định quyền nghiệp vụ.

## 4. Bật Method Security trong Spring Security 6

### 4.1. Cấu hình API xác thực Bearer token

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(request -> request
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

- `@EnableMethodSecurity` kích hoạt hỗ trợ Method Security; với cấu hình mặc định, các annotation như `@PreAuthorize` và `@PostAuthorize` được hỗ trợ. Các phương thức phải được gọi qua cơ chế Spring quản lý để advice chạy.
- `oauth2ResourceServer().jwt(...)` cấu hình việc nhận access token JWT; nếu dùng opaque token, cấu hình introspection tương ứng.
- `authenticated()` ở biên giúp buộc các endpoint API có credential được xác thực. **Rule chi tiết của nghiệp vụ được áp dụng tiếp tại service**, không vì thế mà endpoint thiếu route policy có thể bỏ qua bước xác thực.
- `SessionCreationPolicy.STATELESS` nói rằng API không dựa vào HTTP session để xác thực các request kế tiếp. `SecurityContext` vẫn tồn tại trong quá trình xử lý một request.
- Ví dụ này tắt CSRF vì giả định **chỉ nhận Bearer token do client tự đưa trong header**, không dùng cookie/session tự đính kèm để xác thực. Nếu ứng dụng có cookie hoặc phương thức xác thực browser tự gửi, phải bật/thiết kế CSRF protection phù hợp.

Cấu hình JWT thật phải kiểm issuer, chữ ký, thuật toán, khóa và thời hạn; cần **kiểm audience đúng API** bằng validator/chính sách tương ứng, vì không phải mọi cấu hình `issuer-uri` đều tự bảo đảm audience nghiệp vụ. Nếu token bị thu hồi cần ngăn sử dụng sớm, Resource Server phải có cơ chế revocation thích hợp ngoài việc đọc claims.

### 4.2. Chuyển quyền xuống service

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository repository;

    public OrderApplicationService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    @Transactional(readOnly = true)
    public OrderDto getOrder(UUID orderId) {
        Order order = repository.findById(orderId)
            .orElseThrow(() -> new EntityNotFoundException("Not found"));
        return OrderDto.from(order);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:write')")
    @Transactional
    public void cancelOrder(UUID orderId) {
        Order order = repository.findById(orderId)
            .orElseThrow(() -> new EntityNotFoundException("Not found"));
        order.cancel();
    }
}
~~~

Đây là **bước đầu**, giúp cả các controller khác cùng gọi service bị kiểm scope. Tuy nhiên nó **chưa an toàn cho môi trường đa tenant**: `findById` và `order.cancel()` chưa kiểm người gọi có quyền đối với đơn hàng này không. Phần tiếp theo sẽ bổ sung ownership/tenant và phòng lỗi đồng thời.

Một phương thức `public` được Spring quản lý và gọi qua Spring proxy là điểm đặt `@PreAuthorize` thường dễ dự đoán nhất. Cần quan sát kiến trúc lời gọi để bảo đảm annotation thực sự có hiệu lực.

## 5. Method Security phải kiểm được **đúng đối tượng**, không chỉ authority

Thiết kế tốt thường dùng hai điều kiện:

1. **Chức năng:** actor phải có `SCOPE_orders:read` hoặc `SCOPE_orders:write` theo access token đã xác thực.
2. **Đối tượng:** actor được phép xem/sửa đơn hàng cụ thể dựa trên owner, tenant và business policy từ dữ liệu server kiểm soát.

### 5.1. Chính sách từ principal đã xác thực

Ví dụ API này chỉ chấp nhận JWT từ một issuer tin cậy. Claim `tenant_id` chỉ được dùng nếu Authorization Server có quy trình đáng tin để xác định tenant membership; user không được tự sửa nó như một metadata tùy ý.

~~~java
// Các lớp OrderRepository, Order và OrderDto là kiểu domain minh họa.
// Các import Java/Spring được lược bỏ.

@Component("orderPolicy")
public class OrderPolicy {
    private final OrderRepository repository;

    public OrderPolicy(OrderRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, UUID orderId) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();  // Đã được Resource Server xác thực.
        String subject = jwt.getSubject();
        String tenantId = jwt.getClaimAsString("tenant_id");

        if (subject == null || tenantId == null) {
            return false;
        }

        return repository.existsByIdAndTenantIdAndOwnerSubject(
            orderId, tenantId, subject);
    }
}
~~~

Quyền truy cập được kiểm dựa trên người dùng và tenant đã chuẩn hóa; không lấy `tenantId` hoặc `subject` trực tiếp từ URL/query/body do client khai. Nếu hỗ trợ **nhiều issuer**, `sub` không nhất thiết duy nhất toàn hệ thống: dùng cặp `(iss, sub)` hoặc mapping ổn định sang account nội bộ đã xác thực, và mở rộng khóa truy vấn phù hợp.

`orderPolicy` là tên bean được gọi từ biểu thức SpEL. Mã trên chủ đích trả `false` nếu authentication thiếu hoặc không đúng loại mà chính sách này hỗ trợ; nếu resource server dùng **opaque token**, cần resolver riêng dựa trên `BearerTokenAuthentication`/principal đã được introspection kiểm tra, không ép kiểu JWT.

### 5.2. Gắn policy vào phương thức service

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository repository;

    public OrderApplicationService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders:read') and " +
        "@orderPolicy.canRead(authentication, #orderId)")
    @Transactional(readOnly = true)
    public OrderDto getOrder(UUID orderId) {
        // Chỉ load bản ghi thuộc đúng actor, không dựa hoàn toàn
        // vào lần kiểm authorization trước đó.
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (!(auth instanceof JwtAuthenticationToken jwtAuth)) {
            throw new AccessDeniedException("Invalid actor");
        }

        String subject = jwtAuth.getToken().getSubject();
        String tenantId =
            jwtAuth.getToken().getClaimAsString("tenant_id");

        Order order = repository
            .findByIdAndTenantIdAndOwnerSubject(
                orderId, tenantId, subject)
            .orElseThrow(() ->
                new EntityNotFoundException("Order not found"));

        return OrderDto.from(order);
    }
}
~~~

Đây là ví dụ **đọc đơn hàng theo owner**. Trong dự án thực tế nên có `CurrentActorResolver` để tránh lặp logic lấy principal và bảo đảm actor được chuẩn hóa nhất quán; code minh họa giữ cả hai bước để người học nhìn thấy sự khác biệt giữa *pre-check* và truy vấn dữ liệu có ràng buộc.

**Vì sao kiểm hai lần?** `@PreAuthorize` là cổng kiểm trước phương thức. Nhưng trạng thái quyền/tài nguyên có thể thay đổi giữa lần kiểm trong policy và lần đọc/ghi thực tế (TOCTOU – time of check to time of use). Truy vấn theo `tenantId`/`ownerSubject` tại thời điểm thực thi giúp thu hẹp rủi ro rò dữ liệu do query thiếu điều kiện, và với thao tác ghi quan trọng có thể cần atomic conditional update/lock/transaction phù hợp.

Để SpEL nhận được tên tham số `#orderId`, dự án nên build với thông tin parameter names (ví dụ `-parameters`) hoặc dùng cách đặt tên tham số được Spring Security hỗ trợ như annotation `@P("orderId")`. Nếu tên tham số không được phát hiện, policy có thể nhận `null`, khiến kiểm tra quyền sai hoặc từ chối không như mong đợi.

### 5.3. Hủy đơn: quy tắc ghi phải được kiểm ở thời điểm thay đổi

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders:write') and " +
    "@orderPolicy.canCancel(authentication, #orderId)")
@Transactional
public void cancelOrder(UUID orderId) {
    CurrentActor actor = currentActorResolver.requireCurrent();

    int changed = repository.cancelIfOwnedAndCancellable(
        orderId, actor.tenantId(), actor.subject());

    if (changed != 1) {
        throw new AccessDeniedException(
            "Order is missing, inaccessible, or cannot be cancelled");
    }
}
~~~

`canCancel`, `CurrentActor`, `currentActorResolver` và `cancelIfOwnedAndCancellable` là **API domain minh họa** phải được triển khai trong dự án. Phương thức repository cần thực hiện thay đổi có điều kiện theo `orderId`, tenant, owner và trạng thái cho phép hủy, chẳng hạn bằng câu lệnh `UPDATE ... WHERE id=? AND tenant_id=? AND owner_subject=? AND status='PENDING'` và kiểm số bản ghi cập nhật.

Ở đây:

- `@PreAuthorize` từ chối thao tác trước khi vào thân method nếu không có scope hoặc không đủ quyền theo policy.
- Lệnh update có điều kiện bảo đảm không ghi nhầm tài nguyên khi trạng thái thay đổi sau lần pre-check.
- Nếu business rule yêu cầu chặt hơn (ví dụ kiểm tồn kho hoặc tổng tiền), cần transaction/locking và xử lý concurrency đúng mức.
- Có thể trả 403 hoặc 404 theo chính sách chống lộ sự tồn tại của tài nguyên; tránh log dữ liệu nhạy cảm khi từ chối.

**Không dùng `hasAuthority("SCOPE_orders:write")` như sự thay thế cho kiểm ownership hoặc tenant.**

## 6. Các annotation Method Security và giới hạn của chúng

| Annotation/cơ chế | Thời điểm áp dụng | Dùng khi nào | Giới hạn quan trọng |
|---|---|---|---|
| `@PreAuthorize` | Trước khi phương thức được gọi. | Kiểm scope, role, tham số, gọi policy bean/ABAC. | Phải đi qua interceptor; điều kiện có thể lỗi thời khi dữ liệu đổi. |
| `@PostAuthorize` | Sau khi phương thức trả kết quả. | Kiểm quyền dựa trên `returnObject` cho thao tác đọc có kiểm soát. | Đã chạy thân method; không ngăn side effect hoặc truy vấn dữ liệu diễn ra. |
| `@PreFilter` | Lọc một collection/array tham số theo biểu thức phù hợp. | Giới hạn phần tử đầu vào trước xử lý. | Không thay thế validation và kiểm quyền trong transaction. |
| `@PostFilter` | Lọc collection/stream kết quả. | Một số trường hợp trả danh sách nhỏ theo policy. | Dữ liệu có thể đã được tải; tốn hiệu năng, dễ quên phân trang, lọc muộn. |
| `@Secured` | Kiểm authority trước phương thức theo cách tương đối đơn giản. | Legacy hoặc trường hợp kiểm role/authority tĩnh. | Cần bật hỗ trợ tương ứng, ít biểu đạt hơn `@PreAuthorize`. |
| JSR-250 `@RolesAllowed` | Kiểm role theo quy tắc role của Spring. | Tích hợp hệ thống dùng chuẩn annotation JSR-250. | Cần bật JSR-250 method security; semantics role khác scope. |

Ví dụ `@PostAuthorize`:

~~~java
@PostAuthorize("returnObject != null and " +
               "returnObject.ownerSubject == authentication.name")
public OrderView fetchOrderView(UUID orderId) {
    return repository.findView(orderId);
}
~~~

Mẫu này chỉ minh họa cú pháp `returnObject`; **không phải lựa chọn ưu tiên** cho dữ liệu nhạy cảm vì bản ghi đã được truy xuất trước khi kiểm và có thể có side effects. Nó còn giả định `authentication.name` tương thích với owner subject, điều này cần được chuẩn hóa đặc biệt ở hệ thống nhiều issuer/tenant. Nên ràng buộc truy vấn và quyền **trước khi tải** khi có thể.

Với danh sách rất lớn, đừng lấy toàn bộ dữ liệu rồi dựa vào `@PostFilter` để loại phần không được xem: điều đó gây tải lớn, có thể sai phân trang và phơi dữ liệu qua code chạy trước filter. Lọc bằng điều kiện tenant/ownership trong truy vấn database thường phù hợp hơn.

Trong Spring Security 6, `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` có thể bật những nhóm annotation bổ sung khi cần. Nếu chỉ dùng `@PreAuthorize` và `@PostAuthorize`, cấu hình `@EnableMethodSecurity` mặc định thường là đủ.

## 7. Giới hạn quan trọng: Spring AOP proxy không chặn mọi lời gọi

Đây là nguồn lỗi bảo mật phổ biến khi đưa annotation vào service nhưng không kiểm đường gọi thật.

### 7.1. Self-invocation bỏ qua advice ở mô hình proxy

~~~java
@Service
public class BillingService {

    public void processBatch(List<UUID> ids) {
        for (UUID id : ids) {
            this.refundInvoice(id); // Gọi nội bộ cùng instance.
        }
    }

    @PreAuthorize("hasAuthority('SCOPE_billing:refund')")
    public void refundInvoice(UUID invoiceId) {
        // Logic hoàn tiền.
    }
}
~~~

Trong mô hình Spring AOP proxy mặc định, `processBatch` gọi `this.refundInvoice(...)` **không đi qua proxy**, do đó không chạy interceptor gắn với `@PreAuthorize` trên `refundInvoice`. Nếu không có kiểm quyền ở nơi khác, code có thể hoàn tiền trái policy.

**Cách sửa:** đặt `refundInvoice` trong một Spring bean riêng và gọi qua bean được inject, hoặc thiết kế một public use case method ở ranh giới ngoài có policy bao trùm. Không dùng thủ thuật lấy self-proxy như phương án mặc định nếu có thể thiết kế rõ ràng bằng dịch vụ riêng.

~~~java
@Service
class RefundService {

    @PreAuthorize("hasAuthority('SCOPE_billing:refund')")
    public void refund(UUID invoiceId) {
        // Refund domain logic.
    }
}

@Service
class BatchRefundService {
    private final RefundService refunds;

    BatchRefundService(RefundService refunds) {
        this.refunds = refunds;
    }

    public void processBatch(List<UUID> ids) {
        for (UUID id : ids) {
            refunds.refund(id); // Đi qua proxy của RefundService.
        }
    }
}
~~~

Ví dụ này vẫn cần chính sách để **ai được phép gọi `processBatch`** và cần ràng buộc quyền với từng hóa đơn; việc di chuyển phương thức chỉ giải quyết vấn đề proxy interception, không tự giải quyết ownership.

### 7.2. Method visibility, final và Spring bean lifecycle

- Phương thức `private` không thể được advice qua Spring AOP proxy thông thường; gọi nội bộ private method cũng không qua proxy.
- Với proxy tạo subclass, phương thức `final` và class `final` không thể override để chèn advice; Kotlin mặc định final nên cần cấu hình Spring plugin/all-open hoặc cách tổ chức bean tương thích.
- Các phương thức trên đối tượng tạo bằng `new` không do Spring quản lý sẽ không có advice.
- Với JDK dynamic proxy, lời gọi qua interface/proxy cần được xét theo kiểu bean và phương thức được expose; đừng dựa vào việc annotation “nằm trên file” mà bỏ qua cơ chế thực tế.
- Lời gọi trong constructor hoặc giai đoạn khởi tạo bean có thể xảy ra trước khi proxy/interceptor sẵn sàng.
- Spring AOP có các biến thể proxy và giới hạn riêng; nếu dự án dùng AspectJ weaving, đặc điểm interception có thể khác. Cần xác nhận chế độ đang dùng.

**Cần integration test gọi qua bean thật lấy từ Spring context**, để chứng minh annotation có hiệu lực. Chỉ gọi trực tiếp `new OrderService(...)` trong unit test không kiểm được Method Security.

### 7.3. Khi một service public gọi nhiều bước nội bộ

Annotation ở một phương thức public là **cổng bảo vệ** cho logic mà nó gọi. Không nhất thiết phải gắn annotation trên mọi private helper. Tuy nhiên, mỗi public use case có thể được gọi độc lập từ entry point khác cần một policy đủ chặt. Thiết kế ranh giới theo hành động nghiệp vụ dễ kiểm chứng hơn việc đánh dấu ngẫu nhiên từng helper.

## 8. Không có HTTP request thì lấy Authentication từ đâu?

Bảo vệ service làm phát sinh câu hỏi thực tế: job scheduler, Kafka listener, batch, event consumer hoặc một luồng nền có thể gọi service. Những luồng này không mặc nhiên có người dùng đăng nhập hoặc access token của HTTP request.

| Nguồn gọi | Vấn đề | Hướng xử lý |
|---|---|---|
| REST/GraphQL qua Resource Server | Có Bearer token sau khi xác thực. | Dùng `SecurityContext` do Spring Security thiết lập; service áp dụng policy. |
| Kafka/RabbitMQ consumer | Message có thể do tác nhân khác tạo; không có HTTP `SecurityContext` mặc định. | Xác thực nguồn message/danh tính workload, validate payload, dùng policy cho actor hệ thống hoặc user delegation đã được kiểm chứng. |
| Scheduler/batch | Không có user tương tác. | Thiết kế system use case riêng với quyền hẹp, có audit và ownership phù hợp. |
| `@Async`, executor, `CompletableFuture` | Chuyển thread có thể mất context. | Nếu cần, dùng cơ chế truyền SecurityContext được Spring Security hỗ trợ; xác định vòng đời và kiểm lại quyền khi phù hợp. |
| RPC nội bộ | Có thể bị gọi từ một service khác. | Xác thực service identity/access token đúng audience và phân quyền tại service. |
| Test hoặc import script | Có thể gọi trực tiếp bean. | Không dùng đường bypass lén qua service không bảo vệ; định nghĩa capability và policy đúng nhu cầu. |

**Không coi message chứa `userId` hoặc header `X-User-Role` là danh tính đáng tin chỉ vì nó xuất phát từ hệ thống nội bộ.** Nếu cần thực hiện công việc thay mặt người dùng, phải có cơ chế delegation được xác minh, ghi lại actor gốc và giới hạn quyền tương ứng; chỉ truyền một chuỗi user ID không đủ.

Truyền `SecurityContext` sang thread pool có thể giúp một tác vụ ngắn giữ context đúng tại thời điểm khởi tạo, nhưng cũng có rủi ro **quyền cũ**: user có thể bị vô hiệu hóa hoặc token hết hạn trước khi tác vụ chạy. Với job dài hoặc thao tác tài chính, cần mô hình ủy quyền độc lập và kiểm tra quyền tại thời điểm thực thi theo yêu cầu.

Spring WebFlux sử dụng `ReactiveSecurityContextHolder` và Reactor Context, không thể giả định `SecurityContextHolder` dựa trên `ThreadLocal` trong Servlet luôn đúng với reactive pipeline.

## 9. Không dùng Method Security để “hợp thức hóa” token sai

Một access token JWT có thể đã được parse ra `scope=orders:read` nhưng **chưa được xác thực**. Không dùng claims đó để tạo `Authentication` hoặc tự điền `SecurityContextHolder` trước khi service chạy.

Các bước cần tách rõ:

1. **Resource Server xác thực token:** JWT phải được kiểm chữ ký với thuật toán/khóa tin cậy, `iss`, thời hạn, `aud` và token purpose phù hợp; opaque token phải được introspect tại Authorization Server đáng tin và kiểm các attributes bắt buộc.
2. **Ánh xạ authorities:** ví dụ `scope=orders:read` thành `SCOPE_orders:read` theo converter được cấu hình. Claim `roles` không tự biến thành `ROLE_ADMIN` và chỉ được dùng nếu issuer có thẩm quyền cấp role đó cho API.
3. **Method Security kiểm chính sách chức năng:** `@PreAuthorize("hasAuthority('SCOPE_orders:read')")`.
4. **Domain policy kiểm đối tượng:** tenant/ownership, trạng thái business và ràng buộc về đồng thời.
5. **Quản lý vòng đời token:** nếu JWT ký còn hạn nhưng đã bị thu hồi, Resource Server cần cơ chế denylist/version/introspection hoặc TTL chấp nhận được. Method Security không tự phát hiện revoke chỉ vì có authority.

**ID token của OIDC** chủ yếu dành cho client xác minh thông tin đăng nhập; **refresh token** thuộc luồng xin access token mới tại Authorization Server. Chúng không được dùng như Bearer access token của Resource Server nếu không có hợp đồng xác thực riêng phù hợp. Access token bị đánh cắp và phát lại vẫn có thể mang authority hợp lệ: phải bảo vệ token, rút ngắn TTL và áp dụng sender-constrained token/revocation khi phù hợp.

### Lỗi 401 và 403

| Trường hợp | Kết quả thông thường |
|---|---|
| Thiếu Bearer token trên endpoint yêu cầu xác thực | 401, có thể có `WWW-Authenticate: Bearer`. |
| Token sai chữ ký, issuer, audience hoặc hết hạn | 401 tại bước xác thực. |
| Token hợp lệ nhưng thiếu `SCOPE_orders:read` | 403 từ HTTP hoặc method security. |
| Token có scope, nhưng đơn hàng thuộc tenant khác | 403 hoặc 404 theo policy nghiệp vụ. |
| Lời gọi service không có Authentication (job nội bộ) | Bị từ chối theo method policy; exception mapping thành HTTP status chỉ áp dụng trong HTTP request. |

Spring Security `ExceptionTranslationFilter` và các handler phù hợp xử lý nhiều lỗi xác thực/phân quyền trong HTTP filter chain; exception từ service ngoài HTTP cần được xử lý trong job/consumer đúng cách, không mặc nhiên có mã HTTP 403.

## 10. Giao dịch, TOCTOU và kiểm quyền trên dữ liệu

Method Security chặn trước/ sau method, nhưng thời điểm kiểm quyền và thời điểm commit dữ liệu không nhất thiết trùng nhau.

Ví dụ: tại `T1` policy đọc đơn hàng thuộc user A. Ở `T2`, một quy trình chuyển ownership sang user B. Ở `T3`, phương thức vẫn cập nhật đơn hàng dựa trên kết quả `T1`. Nếu không có điều kiện tại truy vấn ghi, A có thể sửa dữ liệu đã không còn thuộc quyền.

~~~text
T1: @PreAuthorize -> order-42.owner = A -> allow
T2: Transaction khác đổi owner order-42 thành B
T3: UPDATE orders SET status='CANCELLED' WHERE id='order-42'
    (Thiếu điều kiện owner/tenant/trạng thái)
T4: Update thành công dù A không còn quyền
~~~

Các lựa chọn kỹ thuật gồm:

- **Conditional update:** thêm điều kiện `tenant_id`, `owner_id`, trạng thái nghiệp vụ trong `WHERE`; kiểm số bản ghi bị thay đổi.
- **Transactional locking/versioning:** dùng optimistic locking, row lock hoặc isolation phù hợp nếu nghiệp vụ đòi hỏi quyết định nhất quán hơn.
- **Policy gắn vào truy vấn:** load/read dữ liệu bằng điều kiện giới hạn tenant/owner thay vì load rộng rồi lọc muộn.
- **Phân biệt quyền trên actor và thuộc tính object:** một service có `@PreAuthorize` vẫn phải xác minh trạng thái business có thể thay đổi lúc commit.

Method Security và transaction advice đều dùng AOP; thứ tự advice có thể ảnh hưởng việc kiểm quyền xảy ra ngoài hay trong transaction. Không tự giả định mọi `@PreAuthorize` chạy dưới cùng transaction isolation với thao tác ghi; kiểm chứng cấu hình `@Order`/advice và điều kiện database thật khi yêu cầu chặt chẽ.

## 11. Thiết kế policy dễ bảo trì và dễ kiểm toán

### 11.1. Nên dùng policy bean thay vì SpEL quá dài

Có thể viết:

~~~java
@PreAuthorize("@orderPolicy.canCancel(authentication, #orderId)")
public void cancelOrder(UUID orderId) {
    // ...
}
~~~

Chính sách trong `OrderPolicy` có thể kiểm scope, tenant, ownership và trạng thái đơn hàng. Nếu chọn cách này, phải đảm bảo bean **không bỏ qua bước kiểm scope**. Với hành động nhạy cảm, ví dụ kết hợp:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders:write') and " +
    "@orderPolicy.canCancel(authentication, #orderId)")
~~~

Đưa logic phức tạp vào policy/service rõ ràng giúp kiểm thử từng điều kiện và tránh phải sao chép biểu thức dài trên nhiều phương thức.

### 11.2. Xác định phạm vi quyền ở từng tầng

- **Scope:** quyền của access token để gọi chức năng (ví dụ `orders:write`).
- **Role:** vai trò được cấp trong ứng dụng (ví dụ `ROLE_SUPPORT`), phải đến từ nguồn role đáng tin.
- **ABAC:** quyết định từ actor, đối tượng, tenant, trạng thái và các thuộc tính liên quan.
- **System capability:** quyền xử lý công việc nền cụ thể, được cấp riêng và có audit.
- **Ownership:** điều kiện cụ thể trên bản ghi, không mặc nhiên suy ra từ scope.

Không trộn role của ứng dụng khác, issuer khác hoặc tenant khác thành role cục bộ chỉ vì claim trùng tên. Với hệ thống hỗ trợ nhiều issuer, cần định danh người dùng ổn định và namespace phù hợp.

### 11.3. Tránh lỗi phủ sóng annotation

Không có bảo đảm rằng mọi method trong ứng dụng đều có security annotation. Một số use case cho phép public, một số yêu cầu quyền; hãy xác định danh mục service boundary và tiêu chí “chặn mặc định”, kiểm thử những hành động nhạy cảm. Ở HTTP level, `anyRequest().denyAll()` giúp phát hiện route mới chưa khai báo, nhưng ở service level cần review và test vì một method public không có annotation có thể được gọi từ nơi khác.

Một lựa chọn tổ chức là public facade service có các method bảo vệ, còn domain helper chỉ được gọi thông qua facade. Không nên dựa duy nhất vào quy ước đặt tên hoặc comment “internal only” làm ranh giới bảo mật.

## 12. Kiểm thử bảo vệ nhiều entry point

Kiểm thử cần bao phủ **đường đi thực tế qua Spring proxy**, không chỉ xem annotation có xuất hiện trong source code.

### 12.1. Kiểm thử HTTP và authority

Với Spring Security Test, có thể mô phỏng một JWT đã xác thực tại lớp authorization:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt()
            .jwt(token -> token
                .subject("user-123")
                .claim("tenant_id", "tenant-7"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders:read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/orders/42")
        .with(jwt()
            .jwt(token -> token
                .subject("user-123")
                .claim("tenant_id", "tenant-7"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders:write"))))
    .andExpect(status().isForbidden());
~~~

Đây là ví dụ kiểm **authorization**; cần fixture database sao cho đơn hàng 42 thuộc đúng owner/tenant ở trường hợp thành công. `jwt()` của Spring Security Test **không xác minh chữ ký hay audience**. Phải có integration test riêng đi qua `JwtDecoder` thật hoặc test introspection cho opaque token để chứng minh token sai bị từ chối.

Một test có `@WithMockUser(authorities = "SCOPE_orders:read")` cũng không chứng minh một JWT thật đã được xác thực, và nếu `OrderPolicy` của ứng dụng yêu cầu `JwtAuthenticationToken` thì mock user không có kiểu principal đúng. Hãy tạo test fixture phù hợp policy đang kiểm.

### 12.2. Test gọi service trực tiếp qua bean Spring

Để phát hiện lỗi chỉ bảo vệ controller:

1. Tạo Spring test context có bật `@EnableMethodSecurity` và lấy `OrderApplicationService` từ dependency injection.
2. Gọi service với `Authentication` thiếu `SCOPE_orders:read`; mong đợi `AccessDeniedException` trước khi repository xử lý.
3. Gọi service với scope đúng nhưng sai owner/tenant; cũng phải bị từ chối.
4. Gọi service bằng authenticated actor hợp lệ cho một order được phép; kiểm trả đúng dữ liệu.
5. Gọi service từ một **controller thứ hai** hoặc adapter khác; policy phải vẫn được thực hiện.
6. Tạo đường gọi self-invocation như ví dụ ở phần trước để xác định interceptor có thực sự được áp dụng hay không.
7. Kiểm soát dọn `SecurityContextHolder` giữa các test; nếu tự đặt authentication, dùng `finally { SecurityContextHolder.clearContext(); }`.

Nếu test khởi tạo service bằng `new`, annotation proxy không hoạt động; đó có thể là unit test nghiệp vụ hữu ích nhưng **không phải test Method Security**.

### 12.3. Test đường gọi không phải HTTP

Với job/message listener, test cần chứng minh khi không có `Authentication` phù hợp, protected method bị từ chối theo policy; khi có system identity đã được xác thực và quyền hẹp, chỉ những hành động được ủy quyền mới chạy. Đừng làm test pass bằng cách vô điều kiện tạo user `admin` ở listener.

### 12.4. Ma trận kết quả mong đợi

| Tình huống | Kết quả |
|---|---|
| REST route yêu cầu xác thực, không có token | 401. |
| Token sai audience/issuer/chữ ký | 401, trước khi tạo authority dùng được. |
| Token hợp lệ thiếu scope đọc đơn hàng | 403 tại route hoặc service. |
| Token hợp lệ có scope nhưng sai tenant/owner | Từ chối trong Method Security/domain policy. |
| Một GraphQL resolver hoặc controller khác gọi cùng service | Vẫn bị kiểm policy ở service. |
| `this.refundInvoice` self-invocation trong cùng bean | Test phải phát hiện nguy cơ interceptor bị bỏ qua và thiết kế lại. |
| Service được gọi từ batch thiếu actor | Bị từ chối hoặc dùng system use case có chính sách được định nghĩa, không cấp quyền ngầm. |
| Ownership thay đổi giữa pre-check và update | Truy vấn ghi có điều kiện/transaction ngăn cập nhật trái phép. |
| Token đã bị revoke theo yêu cầu | Cơ chế revocation ở Resource Server từ chối token. |
| HTTP test dùng `jwt()` giả lập | Chỉ xác minh policy; không coi là test chữ ký. |

## 13. Bài tập tình huống

### Tình huống A: một phương thức bị gọi qua hai controller

Controller A bảo vệ `/api/orders/{id}/cancel` bằng `SCOPE_orders:write`, rồi gọi `orderService.cancel(id)`. Controller B mới thêm `/api/support/orders/{id}/cancel` với `authenticated()` nhưng không có rule scope. Cả hai dùng cùng service chưa có annotation.

**Câu hỏi:**

1. Đường nào có thể gọi hủy đơn với quyền thấp hơn yêu cầu?
2. Nên đặt điều kiện `SCOPE_orders:write` ở đâu để ràng buộc hành động hủy đơn?
3. Nếu user có scope nhưng đơn của tenant khác, điều kiện nào còn thiếu?
4. Nếu handler batch chạy không có người dùng HTTP, làm sao thể hiện actor hệ thống an toàn?

**Hướng giải:** Đường B có thể bỏ qua scope nếu service không kiểm. Đặt `@PreAuthorize`/policy ở public application service; thực hiện kiểm owner/tenant và atomic state update. Job cần policy và danh tính hệ thống rõ ràng, không dùng “permitAll để tiện chạy”.

### Tình huống B: annotation có nhưng vẫn hoàn tiền trái phép

Lập trình viên đặt `@PreAuthorize("hasAuthority('SCOPE_billing:refund')")` lên phương thức `refundInvoice` nhưng `processBatch` gọi `this.refundInvoice(id)` trong cùng bean.

**Câu hỏi:** Vì sao annotation không chặn như mong đợi? Cần sửa thiết kế lời gọi thế nào? Test nào phát hiện?

**Hướng giải:** Self-invocation không đi qua Spring proxy trong chế độ Spring AOP proxy mặc định. Chuyển lời gọi qua protected Spring bean riêng hoặc public use case boundary thích hợp; test gọi qua Spring context để xác minh interceptor và quyền trên từng invoice.

### Tình huống C: pre-check đúng nhưng update vẫn sai

Policy kiểm owner của order ở thời điểm T1 và chấp nhận. Trước khi service ghi ở T3, đơn được chuyển sang owner khác tại T2. Service cập nhật chỉ bằng `WHERE id = ?`.

**Câu hỏi:** Có phải `@PreAuthorize` đã “bị lỗi” không? Nên sửa ở tầng nào?

**Hướng giải:** Đây là vấn đề TOCTOU; pre-check đơn lẻ không tạo ra quyền bất biến qua thời gian. Dùng điều kiện owner/tenant/trạng thái trong truy vấn ghi, locking hoặc transaction isolation phù hợp; kiểm số dòng cập nhật.

### Tình huống D: JWT hợp lệ nhưng dành cho API khác

Client gửi JWT có `scope=orders:read`, chữ ký đúng, nhưng `aud=["catalog-api"]`. Controller kiểm scope và service cũng có `@PreAuthorize("hasAuthority('SCOPE_orders:read')")`.

**Câu hỏi:** Có đủ an toàn không? Điều kiện nào phải từ chối token trước khi tới service?

**Hướng giải:** Không. Token cần được Resource Server từ chối tại validation `aud` vì không dành cho `orders-api`; cả controller và Method Security chỉ phân quyền trên kết quả xác thực đã đáng tin.

## 14. Checklist triển khai

- [ ] Resource Server xác thực access token đúng issuer, audience, chữ ký/introspection, thời hạn và token purpose.
- [ ] Scope trong access token được ánh xạ thành authorities theo hợp đồng, ví dụ `SCOPE_orders:read`; claim role chỉ dùng từ nguồn cấp quyền đáng tin.
- [ ] HTTP route có quy tắc xác thực tối thiểu và chính sách mặc định hợp lý.
- [ ] Các public application service thực hiện hành động nhạy cảm có Method Security hoặc policy kiểm tra quyền tương đương.
- [ ] `@EnableMethodSecurity` được bật; test xác minh interceptor hoạt động trên bean/proxy thực.
- [ ] Policy kiểm ownership/tenant bằng actor đã xác thực và dữ liệu server, không tin tham số từ client.
- [ ] Với thao tác ghi, truy vấn/transaction xử lý rủi ro dữ liệu thay đổi giữa pre-check và commit.
- [ ] Không có self-invocation/private/final/non-Spring object làm bỏ qua annotation ngoài dự kiến.
- [ ] Job, message consumer, async và RPC có system identity/delegation phù hợp; context không bị rò sang request/task khác.
- [ ] Logic trả collection có lọc ở database; tránh dựa hoàn toàn vào `@PostFilter` để bảo vệ dữ liệu lớn.
- [ ] Có test đường gọi ngoài controller, test scope và owner, test decoder/audience và test revocation nếu yêu cầu.
- [ ] Access/refresh/ID token có vòng đời riêng; không nhầm Method Security với chống token replay hoặc thu hồi token.

### Câu hỏi tự đánh giá

1. Vì sao một controller có `@PreAuthorize` chưa bảo đảm cùng nghiệp vụ được bảo vệ nếu xuất hiện entry point khác?
2. `@EnableMethodSecurity` và `@PreAuthorize` thực hiện chức năng nào trong request có access token?
3. Tại sao `hasAuthority("SCOPE_orders:read")` chưa đủ cho endpoint đọc một đơn hàng?
4. Điều gì xảy ra với `@PreAuthorize` khi `this.protectedMethod()` được gọi trong cùng bean?
5. Tại sao không được lấy `tenant_id` từ query parameter để cấp quyền?
6. `@PostAuthorize` có thể ngăn mọi side effect của phương thức vừa chạy không?
7. Làm sao test được Method Security thật khi dùng Spring AOP?
8. Khi job không có `SecurityContext` từ HTTP, cần làm gì để chạy use case một cách an toàn?
9. Nếu JWT đúng scope nhưng sai audience, phải từ chối ở lớp nào?
10. Khi ownership thay đổi giữa pre-check và transaction ghi, cần cơ chế nào bảo vệ?

**Ghi nhớ:** Controller và HTTP filter là các ranh giới quan trọng, nhưng **hành động nghiệp vụ cần được bảo vệ tại nơi nó có thể được gọi từ nhiều entry point**. Method Security đặt policy ở service; truy vấn và domain policy bảo vệ đúng đối tượng; Resource Server xác thực access token ở phía trước. Cả ba phải phối hợp để hệ thống không cấp quyền ngoài ý muốn, kể cả khi thêm route mới, chạy job, xử lý đồng thời hoặc nhận token không hợp lệ.
