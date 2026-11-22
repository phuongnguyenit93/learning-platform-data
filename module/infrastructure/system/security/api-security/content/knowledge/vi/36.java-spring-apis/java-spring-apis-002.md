# Method security và authorization manager

Spring Security bảo vệ API ở hai tầng. HTTP request authorization quyết định request được phép đi tới route nào; method security quyết định principal có được gọi một phương thức nghiệp vụ cụ thể hay không. Tầng method đặc biệt quan trọng khi nhiều controller, message listener, scheduled job hoặc service khác cùng gọi một nghiệp vụ.

Ví dụ, `GET /api/orders/{id}` và một message listener có thể cùng gọi `OrderService.getOrder(id)`. Nếu chỉ kiểm tra role ở controller, message listener hoặc một controller mới có thể gọi service mà không đi qua kiểm tra đó. Đặt policy tại service method giúp bảo vệ điểm thực thi nghiệp vụ dùng chung.

**Method security không thay thế authentication hoặc HTTP security.** Nó sử dụng `Authentication` hiện tại để kiểm tra quyền trước/sau lời gọi method. Một thiết kế tốt kết hợp request-level policy, method-level policy, object/tenant authorization, validation và business rules.

## 1. Hai tầng authorization trong Spring Security

HTTP authorization và method security giải quyết các câu hỏi khác nhau:

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| HTTP request authorization | Principal có được gọi route/method HTTP này không? | Chỉ user có authority `order:read` được gọi `GET /api/orders/**` |
| Method security | Principal có được gọi nghiệp vụ này với tham số/context cụ thể không? | User chỉ đọc được order thuộc tenant của mình |
| Domain/business policy | Thao tác có hợp lệ theo trạng thái và quy tắc nghiệp vụ không? | Chỉ order chưa giao mới được hủy |

Một cấu hình HTTP có thể chặn phần lớn request không hợp lệ:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .requestMatchers("/api/admin/**").hasAuthority("admin:access")
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Đây chỉ là ví dụ request-level policy. Nó không biết user có quyền đọc `order-42`, cập nhật account thuộc tenant nào hoặc hoàn tiền một payment cụ thể hay không. Các quyết định đó nên nằm gần service/domain logic.

### 1.1. Vì sao không chỉ bảo vệ controller?

Controller không phải nơi duy nhất có thể gọi service:

- REST controller.
- GraphQL resolver.
- Message listener/consumer.
- Scheduled job.
- Batch process.
- Một service khác trong cùng ứng dụng.
- Test hoặc integration adapter.

Nếu authorization chỉ nằm trong controller, một đường gọi mới có thể vô tình bỏ qua policy. Method security đặt kiểm tra tại bean method mà các đường gọi đó dùng chung.

Method security vẫn phụ thuộc vào cách method được gọi qua Spring proxy. Nó không tự bảo vệ lời gọi trực tiếp vào object được tạo bằng `new`, lời gọi self-invocation hoặc code chạy ngoài Spring context.

## 2. Bật method security

Với Spring Boot 3 và Spring Security 6, bật method security bằng `@EnableMethodSecurity`:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Mặc định:

- Pre/post annotations được bật (`prePostEnabled = true`).
- `@Secured` không bật mặc định.
- JSR-250 annotations như `@RolesAllowed` không bật mặc định.

Nếu ứng dụng cần các annotation tương ứng:

```java
@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfiguration {
}
```

Không cần bật lại `prePostEnabled` vì đây là mặc định. Ở ứng dụng cũ dùng `@EnableGlobalMethodSecurity`, hãy lập kế hoạch chuyển sang `@EnableMethodSecurity` khi nâng Spring Security; không trộn hai cấu hình một cách tùy tiện.

### 2.1. Dependency

Với Spring Boot, thường dùng starter phù hợp với ứng dụng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Nếu API xác minh JWT/OAuth2 access token, thêm resource server starter theo phiên bản Spring Boot đang dùng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Không tự chọn version Spring Security riêng lẻ nếu Spring Boot dependency management đã quản lý bộ version tương thích.

## 3. Các annotation method security chính

Spring Security cung cấp nhóm annotation pre/post để kiểm tra quyền trước hoặc sau khi gọi method.

| Annotation | Thời điểm | Mục đích |
|---|---|---|
| `@PreAuthorize` | Trước khi method chạy | Quyết định caller có được gọi method không |
| `@PostAuthorize` | Sau khi method trả kết quả | Kiểm tra điều kiện dựa trên return value |
| `@PreFilter` | Trước khi method chạy | Lọc phần tử trong collection/array/map đầu vào |
| `@PostFilter` | Sau khi method trả kết quả | Lọc phần tử trong collection/array/map trả về |
| `@Secured` | Trước method | Kiểm tra authority theo danh sách role/authority đơn giản |
| `@RolesAllowed` | Trước method | JSR-250 role-based access control |

Trong API nghiệp vụ, `@PreAuthorize` thường là lựa chọn chính vì có thể kết hợp authority với tham số và policy theo object.

## 4. @PreAuthorize: kiểm tra trước khi thực thi

`@PreAuthorize` đánh giá biểu thức trước khi method được gọi. Nếu policy từ chối, method body không chạy.

```java
@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public Report getReport(UUID reportId) {
        return reportRepository.findById(reportId)
            .orElseThrow(() -> new ReportNotFoundException(reportId));
    }

    @PreAuthorize("hasAuthority('report:export')")
    public byte[] exportReport(UUID reportId) {
        return reportExporter.export(reportId);
    }
}
```

Trong ví dụ:

- `report:read` và `report:export` là authorities chính xác.
- User có quyền đọc chưa chắc được quyền export.
- Policy được đặt ở service nên mọi caller đi qua Spring proxy của bean đều được kiểm tra.

### 4.1. hasAuthority và hasRole

Hai hàm này khác nhau ở prefix:

```java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('order:read')")
    public Order getOrder(UUID id) { ... }

    @PreAuthorize("hasRole('ADMIN')")
    public void rebuildIndex() { ... }

    @PreAuthorize("hasAnyRole('ADMIN', 'SUPPORT')")
    public void reopenCase(UUID caseId) { ... }

    @PreAuthorize("hasAnyAuthority('order:read', 'order:manage')")
    public List<Order> findOrders() { ... }
}
```

- `hasAuthority('order:read')` so khớp authority đúng bằng `order:read`.
- `hasRole('ADMIN')` mặc định tìm authority `ROLE_ADMIN`.
- `hasAnyRole` cũng dùng prefix `ROLE_` mặc định.
- `hasAnyAuthority` so khớp tên authority được truyền, không tự thêm `ROLE_`.

Nên thống nhất convention giữa authorization server, JWT converter và method policy. Tránh lúc thì dùng `ROLE_ADMIN`, lúc thì `admin`, lúc lại dùng `admin:access` mà không có mapping rõ.

### 4.2. Role và permission không giống nhau

Role thường gom nhiều quyền theo trách nhiệm, còn authority/permission mô tả hành động cụ thể:

| Role | Authorities minh họa |
|---|---|
| `ROLE_ORDER_READER` | `order:read` |
| `ROLE_ORDER_OPERATOR` | `order:read`, `order:update` |
| `ROLE_ORDER_ADMIN` | `order:read`, `order:update`, `order:cancel` |
| `ROLE_FINANCE` | `payment:read`, `payment:refund` |

Method security có thể kiểm tra role, nhưng policy theo hành động thường dễ review hơn khi dùng permission rõ ràng. Role-to-permission mapping nên được quản lý ở identity/policy layer thay vì rải logic mapping trong nhiều annotation.

## 5. SpEL: truy cập principal, tham số và bean

Pre/post annotations sử dụng Spring Expression Language (SpEL). Một số biến thường dùng:

| Biến/hàm | Ý nghĩa |
|---|---|
| `authentication` | Authentication hiện tại |
| `principal` | Principal của Authentication |
| `returnObject` | Giá trị method trả về, dùng trong post authorization/filter |
| `filterObject` | Phần tử đang được lọc |
| `#parameterName` | Tham số method theo tên |
| `@beanName` | Bean Spring được gọi từ biểu thức |

Ví dụ:

```java
@PreAuthorize("isAuthenticated() and !isAnonymous()")
public Profile getCurrentProfile() { ... }

@PreAuthorize("hasAuthority('invoice:read') and #invoiceId != null")
public Invoice getInvoice(UUID invoiceId) { ... }
```

### 5.1. Parameter name discovery

Biểu thức `#invoiceId` chỉ hoạt động khi Spring có thể khám phá tên tham số. Cấu hình compiler Java với `-parameters` là một cách phổ biến:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Với Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

Nếu cần đặt tên tường minh hoặc build không giữ parameter metadata, có thể dùng annotation parameter như `@P`:

```java
import org.springframework.security.core.parameters.P;

@PreAuthorize("hasAuthority('invoice:read') and #id != null")
public Invoice getInvoice(@P("id") UUID invoiceId) {
    ...
}
```

Hãy kiểm tra cách parameter name discovery của phiên bản Spring Security đang dùng. Không để policy quan trọng phụ thuộc vào tên tham số chưa được xác minh trong build.

### 5.2. Không ghép SpEL từ input người dùng

Biểu thức authorization nên là code tĩnh được review. Không tạo SpEL bằng cách nối chuỗi từ query parameter, header hoặc request body. Làm vậy có thể dẫn tới expression injection hoặc logic authorization không thể kiểm soát.

## 6. Authorization theo object và tenant

Kiểm tra role chung không đủ để bảo vệ object. User có `invoice:read` vẫn có thể chỉ được đọc invoice thuộc tenant của mình hoặc invoice được chia sẻ với họ.

Một cách viết trực tiếp:

```java
@Service
public class InvoiceService {

    private final InvoiceRepository invoices;

    @PreAuthorize("@invoicePolicy.canRead(authentication, #invoiceId)")
    public Invoice getInvoice(UUID invoiceId) {
        return invoices.findById(invoiceId)
            .orElseThrow(() -> new InvoiceNotFoundException(invoiceId));
    }
}
```

Policy bean:

```java
@Component("invoicePolicy")
public class InvoicePolicy {

    private final InvoiceRepository invoices;

    public boolean canRead(Authentication authentication, UUID invoiceId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        Object principal = authentication.getPrincipal();
        if (!(principal instanceof AppPrincipal appPrincipal)) {
            return false;
        }

        return invoices.existsReadableBy(
            invoiceId,
            appPrincipal.userId(),
            appPrincipal.tenantId()
        );
    }
}
```

Đây là ví dụ minh họa. Trong ứng dụng thực tế, cần xử lý principal type an toàn, anonymous authentication, tenant membership và trường hợp object không tồn tại. Repository query nên ràng buộc tenant/owner ngay trong truy vấn để tránh tải object không thuộc phạm vi rồi mới kiểm tra.

### 6.1. Tránh kiểm tra rồi truy vấn lại không cần thiết

Policy bean có thể gọi repository để kiểm tra, sau đó method lại truy vấn object lần nữa. Cách này đơn giản nhưng có thể tạo hai query và có race giữa kiểm tra và sử dụng dữ liệu.

Với nghiệp vụ quan trọng, cân nhắc:

- Dùng query có điều kiện owner/tenant để lấy object trong đúng phạm vi.
- Dùng service/domain authorization kiểm tra trạng thái và relationship.
- Giữ kiểm tra quyền và thao tác nhạy cảm trong transaction phù hợp.
- Không chỉ dựa vào object ID do client cung cấp.

Ví dụ query scope:

```java
public interface InvoiceRepository extends JpaRepository<Invoice, UUID> {
    Optional<Invoice> findByIdAndTenantId(UUID id, UUID tenantId);
}
```

Service:

```java
@PreAuthorize("hasAuthority('invoice:read')")
public Invoice getInvoice(UUID invoiceId) {
    AppPrincipal principal = currentPrincipal.require();
    return invoices.findByIdAndTenantId(invoiceId, principal.tenantId())
        .orElseThrow(InvoiceNotFoundException::new);
}
```

Phương án query-scoped này vẫn cần xử lý owner/share permission nếu domain cho phép nhiều quan hệ truy cập.

### 6.2. Function-level authorization

Các thao tác có rủi ro khác nhau cần permission khác nhau:

```java
@Service
public class InvoiceCommandService {

    @PreAuthorize("hasAuthority('invoice:approve')")
    public void approve(UUID invoiceId) { ... }

    @PreAuthorize("hasAuthority('invoice:cancel')")
    public void cancel(UUID invoiceId) { ... }

    @PreAuthorize("hasAuthority('invoice:export')")
    public byte[] export(UUID invoiceId) { ... }
}
```

Không dùng một role `USER` hoặc `ADMIN` chung cho mọi action nếu nghiệp vụ cần phân tách quyền. Dù method có permission, vẫn phải kiểm tra object và trạng thái nghiệp vụ trước side effect.

### 6.3. Field/property-level authorization

Quyền đọc object không đồng nghĩa được đọc mọi field. Method security có thể gọi policy bean để xác định representation hoặc chọn DTO riêng:

```java
@PreAuthorize("hasAuthority('customer:read')")
public CustomerView getCustomer(UUID customerId) {
    ...
}
```

Trong service/mapper, chỉ đưa field được phép vào response. Không serialize entity đầy đủ rồi hy vọng frontend ẩn field nhạy cảm.

## 7. @PostAuthorize: kiểm tra return value

`@PostAuthorize` chạy sau khi method trả kết quả. Nó hữu ích khi policy cần kiểm tra thuộc tính của object trả về:

```java
@PostAuthorize("returnObject.ownerId == authentication.principal.userId")
public Document getDocument(UUID documentId) {
    return documents.findById(documentId)
        .orElseThrow(DocumentNotFoundException::new);
}
```

Biểu thức trên chỉ là ví dụ; tên property và principal phải khớp model thật.

### 7.1. Giới hạn của post authorization

Method body đã chạy trước khi `@PostAuthorize` đánh giá. Nếu method tạo side effect rồi mới bị từ chối, side effect có thể đã xảy ra.

Không dùng `@PostAuthorize` làm lớp chính cho:

- Chuyển tiền.
- Hoàn tiền.
- Xóa dữ liệu.
- Thay đổi quyền.
- Gửi email hoặc webhook.
- Cập nhật trạng thái nghiệp vụ.

Với thao tác thay đổi trạng thái, kiểm tra quyền trước bằng `@PreAuthorize` hoặc domain policy trong transaction trước khi thực hiện side effect. `@PostAuthorize` phù hợp hơn với một số truy vấn đọc mà kết quả mới cho biết owner/relationship.

### 7.2. Không tiết lộ object qua exception

Nếu post authorization từ chối, response không nên tiết lộ nội dung object vừa tải. Cần thống nhất cách xử lý 403/404 theo disclosure policy và không log payload nhạy cảm trong exception.

## 8. @PreFilter và @PostFilter

Filter annotations có thể lọc collection đầu vào hoặc đầu ra bằng biểu thức SpEL.

### 8.1. @PostFilter

```java
@PostFilter("filterObject.ownerId == authentication.principal.userId")
public List<Document> findDocuments() {
    return documents.findAll();
}
```

Spring lọc các phần tử không thỏa điều kiện trước khi caller nhận collection.

### 8.2. @PreFilter

```java
@PreFilter("filterObject.ownerId == authentication.principal.userId")
public void updateDocuments(List<DocumentUpdate> updates) {
    ...
}
```

Nếu method có nhiều tham số collection, dùng thuộc tính `filterTarget` để chỉ định tham số cần lọc:

```java
@PreFilter(
    value = "filterObject.ownerId == authentication.principal.userId",
    filterTarget = "updates"
)
public void updateDocuments(
        List<DocumentUpdate> updates,
        UpdateOptions options
) {
    ...
}
```

### 8.3. Cẩn trọng với filtering ở memory

`@PostFilter` có thể tải toàn bộ collection rồi mới lọc, gây tốn bộ nhớ và thời gian. Nó không thay thế query scope trong database. Với danh sách lớn, pagination hoặc dữ liệu nhạy cảm, ưu tiên query có điều kiện owner/tenant/relationship.

`@PreFilter` cũng không đảm bảo mọi phần tử hợp lệ theo trạng thái nghiệp vụ. Nếu phần tử bị lọc âm thầm, caller có thể hiểu nhầm rằng toàn bộ batch đã được xử lý. Với command batch quan trọng, thường tốt hơn là validate từng phần tử, từ chối toàn bộ hoặc trả kết quả từng phần theo contract rõ ràng.

## 9. @Secured và @RolesAllowed

Ngoài pre/post annotations, Spring hỗ trợ hai kiểu annotation đơn giản hơn.

```java
@Secured({"ROLE_ADMIN", "ROLE_SUPPORT"})
public void reopenCase(UUID caseId) { ... }
```

Với JSR-250:

```java
@RolesAllowed({"ADMIN", "SUPPORT"})
public void reopenCase(UUID caseId) { ... }
```

Để dùng:

```java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
```

Khác biệt:

- `@Secured` dùng tên authority/role theo convention của ứng dụng, thường có `ROLE_`.
- `@RolesAllowed` theo JSR-250 và thường khai báo role không có prefix; Spring ánh xạ theo role prefix configuration.
- Hai annotation này phù hợp cho kiểm tra role đơn giản, không mạnh bằng SpEL khi cần object/tenant policy.

Không dùng annotation role đơn giản để thay thế domain authorization phức tạp.

## 10. AuthorizationManager là gì?

`AuthorizationManager` là abstraction của Spring Security để đưa ra quyết định authorization. Thay vì gắn logic vào một annotation cụ thể, manager nhận authentication và đối tượng cần bảo vệ, rồi trả kết quả cho phép/từ chối.

Spring Security dùng authorization managers ở nhiều nơi:

- HTTP request authorization.
- Method authorization trước khi gọi method.
- Method authorization sau khi method trả kết quả.
- Các integration tùy chỉnh cần policy thống nhất.

Với HTTP DSL, ví dụ:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/admin/**").hasAuthority("admin:access")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
```

Các matcher DSL được xây dựng trên hệ thống authorization manager của Spring Security. Ở method security, `@PreAuthorize` và các interceptor tương ứng cũng sử dụng mô hình manager để quyết định trước/sau lời gọi.

### 10.1. AuthorizationManager nhận context nào?

Tùy loại manager, đối tượng cần quyết định có thể là:

- `RequestAuthorizationContext` cho HTTP request.
- `MethodInvocation` cho lời gọi Java method.
- Context tùy chỉnh cho resource hoặc thao tác cụ thể.

Điều này cho phép manager đọc method/arguments hoặc request metadata để áp dụng policy. Tuy nhiên, không nên biến manager thành nơi chứa toàn bộ nghiệp vụ hoặc thực hiện nhiều query không kiểm soát.

### 10.2. Phân biệt AuthorizationManager với PermissionEvaluator

`PermissionEvaluator` thường được gọi qua biểu thức `hasPermission(...)` để kiểm tra quyền trên object/target ID. `AuthorizationManager` là abstraction rộng hơn, được dùng trực tiếp bởi interceptors và request authorization. Có thể tích hợp cả hai, nhưng nên chọn một điểm thực thi rõ ràng để tránh cùng một policy bị lặp ở nhiều nơi với kết quả khác nhau.

## 11. Dùng policy bean trong SpEL hay custom AuthorizationManager?

Hai cách có thể bổ trợ nhau:

| Cách | Phù hợp khi | Ví dụ |
|---|---|---|
| `@PreAuthorize` với authority | Quy tắc đơn giản, dễ đọc | `hasAuthority('order:cancel')` |
| `@PreAuthorize` gọi bean | Domain policy cần repository hoặc relationship | `@orderPolicy.canCancel(authentication, #id)` |
| Custom `AuthorizationManager` | Muốn một thành phần manager tái sử dụng trong interceptor/HTTP/method policy | Policy manager nhận invocation/context |
| Domain service method | Quyết định gắn chặt với trạng thái/transaction nghiệp vụ | `order.cancelBy(principal)` |

Đừng chọn custom manager chỉ vì nó có tên abstraction tổng quát. Nếu một biểu thức `@PreAuthorize` gọi policy bean đã rõ ràng, đó có thể là cách đơn giản và dễ review hơn.

### 11.1. Policy bean có thể tái sử dụng

```java
@Component("orderPolicy")
public class OrderPolicy {

    private final OrderRepository orders;

    public boolean canRead(Authentication authentication, UUID orderId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        Object principal = authentication.getPrincipal();
        if (!(principal instanceof AppPrincipal appPrincipal)) {
            return false;
        }

        return orders.existsVisibleTo(
            orderId,
            appPrincipal.userId(),
            appPrincipal.tenantId()
        );
    }
}
```

Sử dụng:

```java
@PreAuthorize("hasAuthority('order:read') and @orderPolicy.canRead(authentication, #orderId)")
public OrderView getOrder(UUID orderId) {
    ...
}
```

Policy method nên trả boolean/decision rõ ràng, xử lý principal type và lỗi dữ liệu cẩn thận. Tránh để exception từ repository vô tình bị diễn giải như allow. Mặc định khi không xác định được quyền nên từ chối.

### 11.2. Custom AuthorizationManager cho MethodInvocation

Với các version Spring Security có API legacy `check`/`AuthorizationDecision` (được dùng trong các bản 6.x trước khi chuyển sang `authorize`), một manager cho method invocation có hình dạng như sau:

```java
public final class OrderMethodAuthorizationManager
        implements AuthorizationManager<MethodInvocation> {

    private final OrderPolicy orderPolicy;

    public OrderMethodAuthorizationManager(OrderPolicy orderPolicy) {
        this.orderPolicy = orderPolicy;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            MethodInvocation invocation
    ) {
        Authentication current = authentication.get();
        Object[] args = invocation.getArguments();

        if (args.length == 0 || !(args[0] instanceof UUID orderId)) {
            return new AuthorizationDecision(false);
        }

        boolean granted = orderPolicy.canRead(current, orderId);
        return new AuthorizationDecision(granted);
    }
}
```

Đây là ví dụ cho API legacy có method `check`; các phiên bản Spring Security mới hơn có thể dùng `authorize` và `AuthorizationResult` thay cho chữ ký cũ. Hãy đối chiếu API đúng version đang được Spring Boot quản lý trước khi copy code vào dự án.

Trong production, không nên giả định tham số đầu tiên luôn là UUID. Manager cần gắn với pointcut/method cụ thể hoặc dùng metadata/annotation riêng để xác định argument và action. Nếu manager áp dụng chung cho nhiều method, cần xử lý overload, bridge method và method signature.

### 11.3. Gắn manager với method interceptor

Spring cung cấp `AuthorizationManagerBeforeMethodInterceptor` và `AuthorizationManagerAfterMethodInterceptor` để áp dụng manager cho method invocation. Có thể dùng pointcut để giới hạn method nào được bảo vệ.

Ví dụ khái niệm theo Spring Security 6.x:

```java
@Bean
static Advisor orderAuthorizationAdvisor(
        OrderMethodAuthorizationManager manager
) {
    AspectJExpressionPointcut pointcut = new AspectJExpressionPointcut();
    pointcut.setExpression(
        "execution(* com.example.orders.OrderQueryService.getOrder(..))"
    );

    return new AuthorizationManagerBeforeMethodInterceptor(
        pointcut,
        manager
    );
}
```

Pointcut và constructor cụ thể cần đối chiếu đúng version Spring Security đang dùng. Tránh đồng thời bảo vệ cùng method bằng nhiều manager có logic mâu thuẫn mà không hiểu advisor order.

### 11.4. Đừng để AuthorizationManager thành nơi chạy toàn bộ business logic

Manager nên tập trung vào quyết định authorization. Các thao tác như thay đổi trạng thái order, tính phí, reserve inventory hoặc ghi audit nghiệp vụ vẫn thuộc domain/application service. Nếu manager làm side effect, kiểm tra quyền có thể khó lặp lại, khó test và gây bất ngờ khi interceptor chạy.

## 12. PermissionEvaluator và hasPermission

Nếu ứng dụng đã dùng Spring expression `hasPermission`, có thể triển khai `PermissionEvaluator` để kiểm tra quyền trên object hoặc target ID.

Ví dụ biểu thức:

```java
@PreAuthorize("hasPermission(#documentId, 'Document', 'READ')")
public Document getDocument(UUID documentId) {
    ...
}
```

`PermissionEvaluator` có hai dạng thường gặp:

- Kiểm tra object đã có sẵn.
- Kiểm tra target ID và target type trước khi tải object.

Đây là abstraction hữu ích khi ứng dụng có mô hình permission evaluator thống nhất. Cần kiểm tra cách evaluator xử lý target type, ID không tồn tại, tenant và lỗi repository. Không coi việc target ID tồn tại là bằng chứng caller có quyền.

Nếu policy phức tạp phụ thuộc trạng thái nghiệp vụ hoặc relationship nhiều tầng, một domain policy service có thể dễ hiểu hơn một biểu thức `hasPermission` quá dài.

## 13. Proxy, self-invocation và các giới hạn thực thi

Method security của Spring dựa trên method interception/AOP proxy. Annotation chỉ có tác dụng khi lời gọi đi qua proxy đã được cấu hình.

### 13.1. Self-invocation có thể bỏ qua security

Ví dụ:

```java
@Service
public class AccountService {

    public void importAccounts(List<AccountInput> inputs) {
        for (AccountInput input : inputs) {
            this.createAccount(input); // gọi nội bộ, không đi qua proxy
        }
    }

    @PreAuthorize("hasAuthority('account:create')")
    public void createAccount(AccountInput input) {
        ...
    }
}
```

Khi `importAccounts` gọi `this.createAccount`, lời gọi không đi qua Spring proxy; method security trên `createAccount` có thể không được áp dụng.

Các cách xử lý:

- Tách method được bảo vệ sang một Spring bean khác và gọi bean đó.
- Đặt authorization ở entry point public mà mọi caller phải đi qua, đồng thời kiểm tra từng item theo policy.
- Dùng cấu trúc service/domain phù hợp để không dựa vào self-invocation.

Không giải quyết bằng cách tự lấy proxy hoặc gọi `AopContext` tràn lan nếu có thể thiết kế bean boundary rõ hơn.

### 13.2. Object phải do Spring quản lý

Object được tạo bằng `new AccountService()` không tự có method-security proxy. Unit test tạo object trực tiếp cũng không kiểm tra được method security thực tế.

Hãy kiểm tra qua Spring application context và gọi bean đã được proxy. Nếu dùng JDK dynamic proxy, chỉ method exposed qua interface mới được gọi qua proxy đó. CGLIB proxy có các giới hạn với method `final`/class `final`; private method không phải điểm phù hợp để đặt method security dựa trên proxy.

Ưu tiên bảo vệ public service method qua bean boundary ổn định.

### 13.3. Method overload và annotation inheritance

Khi dùng interface, implementation, class inheritance hoặc method overload, cần test method thực tế được proxy/interceptor áp dụng. Không giả định annotation trên một method/interface luôn được phát hiện giống nhau trong mọi proxy mode.

Không đặt policy quan trọng trên private helper rồi kỳ vọng caller bên ngoài bị chặn. Đặt policy ở method boundary mà mọi luồng thực sự đi qua.

## 14. Kết hợp HTTP security và method security

Một cấu hình tốt thường có cả hai:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
    // HTTP SecurityFilterChain được cấu hình riêng.
}
```

HTTP layer:

- Xác minh JWT/session/API credential.
- Chặn route công khai hoặc nội bộ theo policy.
- Áp dụng CORS/CSRF, rate limit và security headers ở lớp phù hợp.
- Áp dụng request-level authorization chung.

Method layer:

- Kiểm tra permission cho nghiệp vụ.
- Kiểm tra object/tenant relationship.
- Bảo vệ method được gọi từ controller, listener hoặc job.
- Kiểm tra điều kiện trước side effect.

Không dùng method security để thay thế network segmentation hoặc authentication. Không dùng HTTP route rule làm lớp duy nhất cho object authorization.

### 14.1. Default deny ở cả hai tầng

Ở HTTP layer, kết thúc bằng `denyAll()` cho route chưa khai báo. Ở method layer, method nhạy cảm phải có policy rõ hoặc chỉ được gọi từ một application service đã kiểm soát. Tránh một service public có thể thực hiện action nhạy cảm nhưng không có annotation/policy vì “controller đã kiểm tra”.

Có thể dùng architecture test hoặc code review rule để phát hiện method nhạy cảm không có policy.

## 15. Async method và SecurityContext

Thông thường Spring Security lưu `SecurityContext` trong `SecurityContextHolder` theo cơ chế ThreadLocal. Khi chuyển sang thread khác, context không tự động được chia sẻ an toàn trong mọi executor.

Ví dụ rủi ro:

```java
@Async
public void generateReport(UUID reportId) {
    // Không giả định Authentication từ thread gọi luôn có ở đây.
}
```

Nếu method async cần principal của caller, hãy thiết kế truyền identity/context một cách rõ ràng:

- Dùng executor được bọc bằng `DelegatingSecurityContextExecutor` hoặc wrapper phù hợp.
- Với tác vụ chạy lâu, cân nhắc truyền actor ID và authorization context đã được xác minh vào job payload.
- Khi worker xử lý, xác minh job issuer, tenant, action và quyền hiện tại theo policy.
- Không serialize toàn bộ `SecurityContext` hoặc access token vào queue nếu không cần.

Một job chạy sau vài phút có thể cần kiểm tra lại quyền vì user đã bị thu hồi access hoặc trạng thái resource đã thay đổi. Không coi quyền tại thời điểm enqueue luôn còn hợp lệ khi thực thi.

### 15.1. Scheduled job và system principal

Scheduled job không có user tương tác. Dùng service identity/system principal với authority tối thiểu, không tạo một user admin giả để tiện chạy job. Ghi nhận actor là service/job và giới hạn action/resource.

## 16. Reactive method security

Ứng dụng WebFlux/Reactor dùng security context trong Reactor Context thay vì giả định ThreadLocal thông thường. Bật reactive method security bằng:

```java
@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
```

Ví dụ:

```java
@Service
public class ReactiveDocumentService {

    @PreAuthorize("hasAuthority('document:read')")
    public Mono<Document> getDocument(UUID id) {
        return repository.findById(id);
    }
}
```

Với reactive flow, không block để lấy Authentication từ `SecurityContextHolder`. Dùng reactive security context integration như `ReactiveSecurityContextHolder` hoặc các cơ chế được framework hỗ trợ. Đảm bảo authorization expression được áp dụng đúng publisher và không subscribe thủ công làm mất context.

Không trộn blocking repository hoặc ThreadLocal security context vào reactive pipeline mà không có context propagation được thiết kế.

## 17. Exception và response khi bị từ chối

Method security thường ném `AccessDeniedException` hoặc exception liên quan khi policy từ chối. Trong HTTP request được xử lý qua Spring Security filter chain, exception translation có thể chuyển thành 403 theo cấu hình.

Phân biệt:

- 401: chưa xác thực hoặc credential không hợp lệ theo authentication entry point.
- 403: đã xác thực nhưng không được phép theo policy.
- 404: có thể được dùng để che giấu sự tồn tại của object theo disclosure policy; cần nhất quán và tránh tạo side channel.

Nếu gọi method từ test, scheduled job hoặc listener ngoài HTTP filter chain, exception có thể được truyền trực tiếp tới caller. Cần xử lý theo contract của từng entry point.

Không trả chi tiết policy nội bộ, role mapping, tenant ID khác hoặc lý do nhạy cảm trong error body. Log reason code nội bộ với request/correlation ID.

## 18. Kiểm thử method security

Không chỉ test rằng user hợp lệ gọi được method. Cần test cả trường hợp bị từ chối, object khác tenant, self-invocation và các đường gọi ngoài controller.

### 18.1. Spring Security Test

Thêm test dependency:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ dùng `@WithMockUser`:

```java
@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanReadReport() {
        assertThatCode(() -> reportService.getReport(UUID.randomUUID()))
            .doesNotThrowAnyException();
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void writerWithoutReadPermissionIsDenied() {
        assertThatThrownBy(() -> reportService.getReport(UUID.randomUUID()))
            .isInstanceOf(AccessDeniedException.class);
    }
}
```

Ví dụ trên giả định repository/test data được cấu hình phù hợp. `@WithMockUser` tạo Authentication giả cho test; nó không xác minh JWT converter hoặc principal custom của ứng dụng.

### 18.2. Custom principal

Nếu policy cần tenant ID hoặc user ID từ principal tùy chỉnh, dùng `@WithUserDetails`, `@WithSecurityContext` hoặc tạo Authentication test đúng type. Không ép kiểu principal giả thành `AppPrincipal` rồi bỏ qua lỗi trong test.

### 18.3. Test qua proxy

Inject service bean từ Spring context để test method interceptor. Nếu gọi `new Service()`, test chỉ gọi Java method bình thường và không kiểm tra method security.

### 18.4. Ma trận kiểm thử

| Principal | Permission | Object | Kết quả |
|---|---|---|---|
| Anonymous | Không có | Bất kỳ | Authentication/authorization từ chối |
| User A | `order:read` | Order của tenant A | Cho phép nếu relationship hợp lệ |
| User A | `order:read` | Order tenant B | Từ chối hoặc che giấu theo policy |
| User A | `order:cancel` | Order chưa giao thuộc A | Cho phép nếu business rule hợp lệ |
| User A | `order:cancel` | Order đã giao | Business rule từ chối |
| User A | Chỉ `order:read` | Gọi cancel | Từ chối trước side effect |
| Support | `case:read` | Case ngoài phạm vi support | Từ chối theo assignment/relationship |
| Service principal | `report:generate` | Report được phép | Cho phép theo service policy |
| Caller async | Quyền đã bị thu hồi | Job chạy sau đó | Kiểm tra lại theo execution policy |

### 18.5. Test các lỗi proxy

- Gọi method qua Spring bean proxy và xác minh deny.
- Gọi public wrapper method có self-invocation và xác minh policy không bị bỏ qua.
- Kiểm tra interface/JDK proxy nếu ứng dụng sử dụng.
- Kiểm tra method overload và inherited method.
- Kiểm tra async executor có truyền context theo thiết kế.
- Kiểm tra reactive context qua publisher.

## 19. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra role ở controller | Listener/job/service khác có thể bypass | Bảo vệ service method |
| Dùng `hasRole` với permission không có prefix | Policy không match như mong đợi | Dùng `hasAuthority` hoặc mapping role rõ |
| Không bật `@EnableMethodSecurity` | Annotation không được thực thi | Bật config và test qua context |
| Self-invocation | Bỏ qua proxy/interceptor | Tách bean hoặc đổi entry point |
| Tạo object bằng `new` | Không có method-security proxy | Dùng Spring-managed bean |
| Dùng `@PostAuthorize` cho side effect | Side effect đã chạy trước khi từ chối | Kiểm tra trước bằng pre/domain policy |
| Dùng `@PostFilter` cho dữ liệu lớn | Tải toàn bộ rồi mới lọc | Query theo tenant/owner trong DB |
| Tin tham số ID do client gửi | BOLA/IDOR | Kiểm tra object relationship và tenant |
| SpEL quá dài | Khó review, khó test, lặp policy | Gọi policy bean hoặc custom manager |
| Custom manager fail-open khi lỗi | Bypass authorization | Deny khi không xác định được quyền |
| Không truyền security context cho async | Worker chạy thiếu hoặc sai principal | Context-aware executor hoặc actor context rõ |
| Dùng ThreadLocal trong WebFlux | Mất context hoặc lỗi concurrency | Reactive security context |
| Test gọi service bằng `new` | Không kiểm tra interceptor | Inject bean từ Spring context |
| Chỉ test user admin | Bỏ sót tenant/object/permission mismatch | Test ma trận allow và deny |

## 20. Quy trình thiết kế policy cho một service method

Khi thêm method nghiệp vụ mới:

1. Xác định actor có thể gọi method: user, service principal, job hay system.
2. Xác định action cụ thể: read, update, approve, cancel, export, refund.
3. Xác định resource/object và tenant relationship.
4. Xác định permission/authority cần thiết.
5. Chọn điểm thực thi: `@PreAuthorize`, policy bean, AuthorizationManager hoặc domain service.
6. Đảm bảo mọi đường gọi đi qua Spring-managed proxy hoặc domain entry point đã bảo vệ.
7. Đặt authorization trước side effect; dùng transaction và query scope phù hợp.
8. Viết test cho allowed, denied, wrong tenant, missing permission và proxy behavior.
9. Ghi audit decision mà không log dữ liệu nhạy cảm.
10. Review policy khi thay đổi method signature, caller hoặc resource relationship.

Ví dụ policy design:

| Method | Permission | Object condition | Business condition |
|---|---|---|---|
| `getOrder(id)` | `order:read` | Tenant/owner/share access | Order tồn tại và không bị ẩn |
| `updateOrder(id, input)` | `order:update` | Tenant/owner access | Order còn ở trạng thái cho phép sửa |
| `cancelOrder(id)` | `order:cancel` | Caller được quản lý order | Chưa giao/chưa hoàn tất |
| `refundPayment(id)` | `payment:refund` | Finance role và payment scope | Payment đã capture, chưa refund |
| `exportOrders(filter)` | `order:export` | Filter giới hạn tenant | Giới hạn số bản ghi và dữ liệu export |

## 21. Monitoring và audit

Method security quyết định ở tầng nghiệp vụ, vì vậy log/audit cần cung cấp đủ ngữ cảnh để điều tra:

- Principal/user/service identity đã xác minh.
- Method/action hoặc policy ID.
- Resource type và identifier đã được giảm thiểu theo privacy policy.
- Tenant context.
- Decision allow/deny và reason code.
- Request ID/trace ID hoặc job/message ID.
- Thời điểm và phiên bản policy/deployment.

Không log access token, session cookie, secret hoặc toàn bộ object chỉ để debug authorization. Với object ID nhạy cảm, dùng reference nội bộ hoặc pseudonymized identifier theo retention policy.

Theo dõi:

- Tỷ lệ 401/403 theo route, method và principal class.
- Authorization deny tăng sau deploy/policy change.
- Method nhạy cảm được gọi từ caller type không mong đợi.
- Cross-tenant access attempt.
- Lỗi SpEL/parameter discovery.
- Async task không có actor context hoặc dùng principal không hợp lệ.
- Custom AuthorizationManager exception/timeout.

Không tự động coi mọi deny là tấn công; có thể là client lỗi hoặc quyền vừa thay đổi. Kết hợp tần suất, resource pattern và caller identity để phân loại.

## 22. Checklist trước khi phát hành

- [ ] `@EnableMethodSecurity` được bật trong cấu hình đúng.
- [ ] HTTP authorization và method authorization có trách nhiệm rõ ràng.
- [ ] Method nhạy cảm được bảo vệ tại service/domain boundary.
- [ ] Dùng `hasAuthority`/permission đúng convention; role prefix được hiểu rõ.
- [ ] Parameter names hoạt động trong build hoặc dùng `@P` tường minh.
- [ ] SpEL không được tạo từ input người dùng.
- [ ] Object/tenant/relationship được kiểm tra, không chỉ kiểm tra role chung.
- [ ] Query giới hạn object theo tenant/owner khi phù hợp.
- [ ] `@PostAuthorize` không được dùng làm kiểm tra chính trước side effect.
- [ ] `@PreFilter`/`@PostFilter` không thay query scoping cho collection lớn.
- [ ] Custom AuthorizationManager mặc định deny khi thiếu context hoặc lỗi policy.
- [ ] Self-invocation, proxy mode, final/private methods và Spring-managed bean đã được xem xét.
- [ ] Async/reactive security context được truyền đúng cơ chế.
- [ ] Có test allow/deny qua Spring context proxy với principal thật của ứng dụng.
- [ ] Có test wrong tenant, missing authority, business state và side effect.
- [ ] Exception response không tiết lộ object hoặc policy nội bộ.
- [ ] Audit/monitoring có decision và correlation ID nhưng không log credential.

## 23. Nguyên tắc cần ghi nhớ

Method security đặt authorization gần service method để bảo vệ nghiệp vụ khỏi các đường gọi khác nhau. `@EnableMethodSecurity` bật các interceptor; `@PreAuthorize` kiểm tra trước khi chạy, `@PostAuthorize` kiểm tra return value sau khi chạy, còn filter annotations lọc collection. Dùng `hasAuthority` cho permission cụ thể và hiểu rõ prefix của `hasRole`.

`AuthorizationManager` là abstraction đưa ra quyết định allow/deny cho request hoặc method invocation. Với policy đơn giản, annotation thường dễ đọc; với object/tenant policy, có thể gọi policy bean; với nhu cầu tái sử dụng/interceptor phức tạp, custom manager có thể phù hợp. Dù dùng cách nào, mặc định phải deny khi không xác định được quyền.

Method security dựa trên proxy nên self-invocation hoặc object tự tạo có thể bỏ qua interceptor. Async và reactive có cơ chế security context riêng; không giả định ThreadLocal luôn được truyền qua thread/publisher. Test phải gọi bean từ Spring context và bao gồm cả trường hợp từ chối.

Một phép kiểm tra thực tế là gọi cùng một service method từ REST controller và message listener với principal có quyền và principal sai tenant. Hai đường gọi phải nhận cùng một quyết định policy. Nếu chỉ REST route bị chặn còn listener vẫn thực thi, authorization đang đặt sai ranh giới.

## Tài liệu tham khảo

- Spring Security Reference — Method Security.
- Spring Security Reference — Authorization Architecture and AuthorizationManager.
- Spring Security API — `@EnableMethodSecurity`, `AuthorizationManager`, `AuthorizationManagerBeforeMethodInterceptor`.
- Spring Security Reference — Testing Method Security.
- Spring Security Reference — Reactive Method Security and SecurityContext.
- OWASP Authorization Cheat Sheet — deny by default, least privilege và authorization trên từng request/resource.
- OWASP API Security Top 10 — Broken Object Level Authorization và Broken Function Level Authorization.
