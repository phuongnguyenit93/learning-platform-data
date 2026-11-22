# Truyền ngữ cảnh khách hàng và ngăn rò rỉ dữ liệu chéo

## 1. Bài toán và các khái niệm cần phân biệt

Trong ứng dụng Spring Data JPA phục vụ nhiều khách hàng, mỗi request cần mang theo ngữ cảnh xác định dữ liệu mà người dùng được phép truy cập. Nếu nhiều khách hàng dùng chung một ứng dụng hoặc cùng một database, thiếu ngữ cảnh này có thể khiến người dùng đọc, sửa hoặc xóa dữ liệu của khách hàng khác.

Trong kiến trúc multi-tenant, thường dùng các thuật ngữ:

- **User/actor**: người hoặc hệ thống đang thực hiện request.
- **Customer/account**: khách hàng nghiệp vụ hoặc tài khoản tổ chức.
- **Tenant**: ranh giới cô lập dữ liệu và cấu hình trong hệ thống.
- **Tenant context**: tenant đã được xác thực và được chọn cho một request hoặc một công việc nền.
- **Data source**: nguồn kết nối database. Một tenant có thể dùng database riêng, schema riêng hoặc chia sẻ schema với tenant khác.

Không phải mọi customer đều là tenant. Ví dụ, một công ty (tenant) có thể quản lý hàng nghìn khách hàng nghiệp vụ (customer). Không được coi một customerId do client gửi lên là bằng chứng người dùng có quyền truy cập customer đó. Hãy xác định rõ ranh giới bảo mật của domain trước khi thiết kế context.

Mục tiêu của bài này là bảo đảm mọi thao tác persistence đều chạy trong đúng tenant context, kể cả khi ứng dụng dùng nhiều DataSource, xử lý bất đồng bộ, cache hoặc query native.

## 2. Chọn mô hình cô lập dữ liệu

Có ba mô hình phổ biến. Việc truyền context giống nhau ở tầng bảo mật, nhưng cách chọn connection và bảo vệ query khác nhau.

| Mô hình | Cách lưu dữ liệu | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Database per tenant | Mỗi tenant có database riêng | Cô lập mạnh, backup/restore theo tenant dễ hơn | Quản lý nhiều database, connection pool và migration phức tạp |
| Schema per tenant | Mỗi tenant có schema riêng trong cùng DBMS | Có thể dùng chung server, vẫn tách namespace | Cần quản lý schema, search path và connection/schema switching |
| Shared schema | Nhiều tenant dùng chung bảng, mỗi dòng có tenant_id | Tiết kiệm tài nguyên, dễ mở rộng số lượng tenant | Mọi truy vấn, cache, unique key và thao tác ghi phải được scope chính xác |

Có thể có nhiều DataSource vì các mục đích khác nhau như OLTP, reporting, analytics hoặc legacy database. Đó là bài toán chọn nguồn dữ liệu theo chức năng. Multi-tenancy lại là bài toán chọn phạm vi dữ liệu theo tenant. Một hệ thống có thể cần cả hai: trước tiên xác định nhóm database của chức năng, sau đó chọn tenant database/schema trong nhóm đó.

Không nên chọn database chỉ dựa vào một header tùy ý. Tenant phải được xác thực và cấp quyền trước khi nó được dùng làm khóa routing.

## 3. Xây dựng tenant context an toàn

### 3.1 Không tin tenant ID do client tự khai báo

Client có thể gửi X-Tenant-Id, tenant trong URL hoặc một trường trong request body để chọn tài khoản đang làm việc. Giá trị này chỉ là **lựa chọn cần kiểm tra**, không phải bằng chứng quyền truy cập.

Quy trình nên là:

1. Xác thực người dùng bằng Spring Security hoặc cơ chế identity đáng tin cậy.
2. Lấy danh sách tenant mà principal được phép truy cập từ claim đã xác minh hoặc dịch vụ membership.
3. Đọc tenant được chọn từ request nếu ứng dụng cho phép chọn nhiều tenant.
4. Kiểm tra tenant đó thuộc danh sách được cấp quyền và người dùng có quyền thực hiện chức năng hiện tại.
5. Tạo tenant context từ kết quả đã xác thực.
6. Nếu không có tenant hoặc tenant không hợp lệ, từ chối request; không tự động chuyển sang tenant mặc định.

Nếu principal chỉ có một tenant, có thể lấy tenant đó từ principal đã xác thực. Nếu người dùng được truy cập nhiều tenant, cần kiểm tra membership mỗi lần đổi tenant hoặc dùng một lựa chọn đã được ký/xác thực và vẫn kiểm tra quyền theo chính sách hệ thống. Tài khoản quản trị có thể được phép truy cập nhiều tenant, nhưng thao tác cross-tenant phải có quyền riêng và audit log.

### 3.2 TenantContext dùng ThreadLocal có vòng đời rõ ràng

Với request xử lý đồng bộ trên servlet thread, có thể dùng ThreadLocal để truyền tenant qua các tầng service/repository mà không phải thêm tham số vào mọi method. Phải luôn xóa context khi request kết thúc vì thread được tái sử dụng trong thread pool.

```java
import java.util.Optional;

public final class TenantContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private TenantContext() {
    }

    public static String requireTenantId() {
        String tenantId = CURRENT.get();
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalStateException("Tenant context is missing");
        }
        return tenantId;
    }

    public static Optional<String> currentTenantId() {
        return Optional.ofNullable(CURRENT.get());
    }

    public static Scope open(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }

        String previous = CURRENT.get();
        CURRENT.set(tenantId);

        return () -> {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        };
    }

    public static Runnable propagate(Runnable task) {
        String capturedTenant = CURRENT.get();

        return () -> {
            String previous = CURRENT.get();
            try {
                if (capturedTenant == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(capturedTenant);
                }
                task.run();
            } finally {
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
            }
        };
    }

    @FunctionalInterface
    public interface Scope extends AutoCloseable {
        @Override
        void close();
    }
}
```

Dùng Scope với try-with-resources để bảo đảm khôi phục context trước đó ngay cả khi có exception:

```java
try (TenantContext.Scope ignored = TenantContext.open(tenantId)) {
    orderService.createOrder(command);
}
```

Trong request web, interceptor hoặc filter sẽ quản lý scope. Trong job/message consumer, worker phải mở scope từ tenant metadata đã được xác thực và đóng scope sau khi xử lý. Không để code nghiệp vụ tự ý ghi đè context mà không có cơ chế khôi phục.

Không dùng InheritableThreadLocal như giải pháp mặc định cho executor. Thread pool tái sử dụng thread và context có thể tồn tại ngoài vòng đời request, gây rò rỉ dữ liệu giữa hai tác vụ. Hãy truyền context tường minh hoặc dùng cơ chế propagation có kiểm soát.

### 3.3 Đặt context sau xác thực và trước khi gọi service

Spring Security xử lý authentication trong filter chain trước khi request đi vào Spring MVC. Một HandlerInterceptor có thể đọc principal đã xác thực, kiểm tra tenant được chọn và mở context trước khi controller gọi service có @Transactional.

Ví dụ dưới đây giả định ứng dụng có TenantAuthorizer chịu trách nhiệm xác minh membership:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.AsyncHandlerInterceptor;

@Component
public class TenantContextInterceptor implements AsyncHandlerInterceptor {

    private static final String SCOPE_ATTRIBUTE =
            TenantContextInterceptor.class.getName() + ".scope";

    private final TenantAuthorizer tenantAuthorizer;

    public TenantContextInterceptor(TenantAuthorizer tenantAuthorizer) {
        this.tenantAuthorizer = tenantAuthorizer;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        String requestedTenant = request.getHeader("X-Tenant-Id");
        String authorizedTenant =
                tenantAuthorizer.resolveAuthorizedTenant(
                        authentication, requestedTenant);

        TenantContext.Scope scope = TenantContext.open(authorizedTenant);
        request.setAttribute(SCOPE_ATTRIBUTE, scope);
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        closeScope(request);
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        closeScope(request);
    }

    private void closeScope(HttpServletRequest request) {
        Object value = request.getAttribute(SCOPE_ATTRIBUTE);
        if (value instanceof TenantContext.Scope scope) {
            scope.close();
            request.removeAttribute(SCOPE_ATTRIBUTE);
        }
    }
}
```

TenantAuthorizer là thành phần nghiệp vụ bảo mật của ứng dụng; không được triển khai nó bằng cách chỉ trả lại header mà không kiểm tra principal/membership. Đăng ký interceptor bằng WebMvcConfigurer. Vì interceptor chạy trong MVC sau Spring Security filter chain, SecurityContextHolder đã có authentication nếu cấu hình security đúng.

afterCompletion dọn context trong request đồng bộ. Với MVC async, afterConcurrentHandlingStarted dọn thread ban đầu; công việc trên executor phải nhận tenant context riêng bằng TaskDecorator như phần sau. Không dùng context của thread servlet sau khi request đã chuyển sang xử lý bất đồng bộ.

Nếu dùng WebFlux/reactive stack, không dùng ThreadLocal theo cách này; dùng Reactor Context và cơ chế propagation tương ứng vì một request có thể chuyển thread giữa các operator.

## 4. Chọn DataSource theo tenant

### 4.1 Database riêng cho từng tenant

Khi mỗi tenant có database riêng, AbstractRoutingDataSource của Spring có thể chọn DataSource theo tenant context hiện tại:

```java
import org.springframework.jdbc.datasource.lookup.AbstractRoutingDataSource;

public class TenantRoutingDataSource extends AbstractRoutingDataSource {

    @Override
    protected Object determineCurrentLookupKey() {
        return TenantContext.requireTenantId();
    }
}
```

Cấu hình routing datasource với các tenant đã đăng ký:

```java
Map<Object, Object> targets = new HashMap<>();
targets.put("tenant-a", tenantADataSource);
targets.put("tenant-b", tenantBDataSource);

TenantRoutingDataSource routing = new TenantRoutingDataSource();
routing.setTargetDataSources(targets);
routing.setLenientFallback(false);
routing.afterPropertiesSet();
```

Đây là phần cấu hình cốt lõi; các bean tenantADataSource, tenantBDataSource, credentials và connection pool phải được tạo từ cấu hình bảo mật. Không đưa password vào map hoặc source code. Trong cấu hình Spring Boot thực tế, routing datasource thường được expose làm bean @Primary và được dùng bởi đúng EntityManagerFactory/JpaTransactionManager.

Một số nguyên tắc quan trọng:

- Không khai báo default datasource trỏ về tenant A. Thiếu context phải fail closed, không được âm thầm truy cập dữ liệu tenant mặc định.
- setLenientFallback(false) từ chối lookup key không có trong danh sách target. requireTenantId() cũng từ chối context rỗng.
- Chỉ route đến tenant đã được đăng ký trong tenant registry; không tạo datasource dựa trên chuỗi do client gửi.
- Không tạo connection pool mới cho từng request. Số pool và tổng connection có thể tăng theo số tenant; cần giới hạn, quản lý vòng đời và ngân sách connection.
- Khi thêm/xóa tenant, cập nhật registry an toàn và quản lý migration/credentials theo quy trình riêng. AbstractRoutingDataSource mặc định phù hợp với tập target được cấu hình khi khởi tạo; registry động cần thiết kế đồng bộ riêng.

### 4.2 Schema riêng cho từng tenant

Nếu các tenant dùng chung database nhưng mỗi tenant có schema riêng, có thể chuyển schema trên connection hoặc dùng Hibernate multi-tenancy. Với Hibernate, các thành phần thường liên quan là CurrentTenantIdentifierResolver và MultiTenantConnectionProvider.

Khi dùng schema switching:

- Tenant identifier phải được resolve từ context đã xác thực.
- Connection phải được chuyển sang schema đúng trước khi query.
- Khi trả connection về pool, phải reset schema/search_path về trạng thái an toàn.
- Không để schema của tenant trước còn sót trên connection được cấp cho tenant tiếp theo.
- Migration phải tạo/cập nhật schema cho tất cả tenant theo cùng phiên bản.
- Test phải kiểm tra việc đổi schema trên connection được tái sử dụng.

Cấu hình chi tiết phụ thuộc Hibernate version và DBMS. JPA chuẩn không quy định đầy đủ chiến lược multi-tenancy; hãy kiểm tra tài liệu provider đang sử dụng thay vì sao chép cấu hình của một phiên bản khác.

### 4.3 Shared schema với tenant_id

Nếu nhiều tenant dùng chung bảng, mỗi bảng dữ liệu tenant phải có cột tenant_id. Mọi query đọc/ghi phải được giới hạn theo tenant. Một lỗi quên điều kiện tenant trong một repository method có thể làm lộ dữ liệu chéo.

Ví dụ entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
    name = "orders",
    schema = "app",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_orders_tenant_external",
        columnNames = {"tenant_id", "external_id"}
    )
)
public class PurchaseOrder {

    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private String tenantId;

    @Column(name = "external_id", nullable = false)
    private String externalId;

    @PrePersist
    void assignTenant() {
        String currentTenant = TenantContext.requireTenantId();

        if (tenantId != null && !tenantId.equals(currentTenant)) {
            throw new SecurityException("Entity tenant does not match context");
        }

        tenantId = currentTenant;
    }

    @PreUpdate
    void preventTenantChange() {
        if (!TenantContext.requireTenantId().equals(tenantId)) {
            throw new SecurityException("Cross-tenant entity update rejected");
        }
    }
}
```

Đoạn code là ví dụ minh họa; entity cần constructor/accessor và các import JPA tương ứng. Trong thực tế, tốt hơn là không expose setter cho tenantId. Tenant ID phải được gán từ context phía server khi tạo entity, không lấy trực tiếp từ request body. Unique constraint thường phải gồm tenant_id cùng business key; nếu chỉ unique theo email hoặc external_id toàn cục thì có thể vô tình cấm các tenant dùng cùng giá trị hoặc tạo logic kiểm tra sai.

Repository nên có method scope tenant tường minh:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {

    Optional<PurchaseOrder> findByIdAndTenantId(
            UUID id, String tenantId);

    List<PurchaseOrder> findAllByTenantIdAndStatus(
            String tenantId, OrderStatus status);

    boolean existsByTenantIdAndExternalId(
            String tenantId, String externalId);
}
```

Service lấy tenant từ context đã xác thực:

```java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public PurchaseOrder getOrder(UUID id) {
        String tenantId = TenantContext.requireTenantId();

        return repository.findByIdAndTenantId(id, tenantId)
                .orElseThrow(() -> new EntityNotFoundException(
                        "Order not found"));
    }
}
```

Trong shared schema, tránh dùng trực tiếp findById(id) cho entity thuộc tenant nếu method đó không được bảo vệ bởi cơ chế tenant filter đáng tin cậy. Không tiết lộ việc ID tồn tại ở tenant khác; thường trả kết quả không tìm thấy hoặc access denied theo chính sách API.

### 4.4 Hibernate @TenantId

Hibernate cung cấp annotation riêng org.hibernate.annotations.TenantId cho discriminator-based multi-tenancy. Khi cấu hình Hibernate multi-tenancy đúng với CurrentTenantIdentifierResolver, Hibernate có thể gán tenant id khi persist và áp dụng tenant restriction cho các thao tác entity được provider quản lý.

Đây là tính năng Hibernate-specific, không phải annotation của Jakarta Persistence. Trước khi dùng:

- Xác nhận phiên bản Hibernate hỗ trợ và cấu hình resolver phù hợp.
- Không giả định native SQL, JDBC trực tiếp hoặc mọi thao tác bulk đều tự được bảo vệ giống entity query.
- Kiểm thử các đường truy cập qua EntityManager, repository, native query, bulk update/delete và cache.
- Không cho client tự gán tenant field; context phải đến từ authentication/authorization.

Dù dùng @TenantId, vẫn cần test cross-tenant và database-level defense in depth cho dữ liệu nhạy cảm.

## 5. Đảm bảo transaction dùng đúng tenant

Đây là điểm dễ gây lỗi nhất khi kết hợp routing datasource với @Transactional.

Spring transaction manager thường lấy connection hoặc bind EntityManager/connection vào thread khi transaction bắt đầu. Vì vậy, tenant context phải được thiết lập **trước khi gọi phương thức service có @Transactional**. Nếu set tenant bên trong method sau khi transaction đã mở, connection có thể đã được chọn theo tenant cũ hoặc chưa có context.

Luồng đúng:

1. Spring Security xác thực user.
2. Interceptor xác minh tenant và mở TenantContext.
3. Controller gọi service.
4. Spring transaction proxy mở transaction.
5. DataSource/EntityManager lấy connection theo tenant context.
6. Repository chạy trong transaction đó.
7. Transaction commit/rollback.
8. Interceptor đóng TenantContext khi request kết thúc.

Không đổi tenant giữa một transaction. Một transaction nên gắn với đúng một tenant từ đầu đến cuối. Nếu cần xử lý nhiều tenant, chia thành các transaction riêng, mỗi transaction có context riêng. Khi dùng REQUIRES_NEW, context hiện tại vẫn được giữ trên thread; chỉ đổi tenant nếu nghiệp vụ thực sự cần và phải mở/khôi phục context có kiểm soát trước khi transaction mới bắt đầu.

Với nhiều EntityManagerFactory/transaction manager, cần gắn repository vào đúng cặp bằng entityManagerFactoryRef và transactionManagerRef. Không để routing datasource của một nhóm tenant bị dùng nhầm bởi repository thuộc database chức năng khác.

## 6. Truyền context sang @Async, executor và message queue

### 6.1 ThreadLocal không tự truyền sang thread khác

ThreadLocal chỉ gắn với thread hiện tại. Khi dùng @Async, Executor, CompletableFuture hoặc scheduler, công việc có thể chạy trên thread khác và không tự nhận tenant context. Nếu thread pool giữ lại context cũ, một tác vụ tiếp theo còn có nguy cơ chạy nhầm tenant.

Có thể dùng Spring TaskDecorator để capture context lúc submit và thiết lập/khôi phục context khi chạy:

```java
import org.springframework.core.task.TaskDecorator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TenantAsyncConfiguration {

    @Bean
    TaskDecorator tenantTaskDecorator() {
        return TenantContext::propagate;
    }
}
```

Cấu hình TaskDecorator vào ThreadPoolTaskExecutor được dùng bởi @Async hoặc executor tương ứng. Method TenantContext.propagate() trong ví dụ ở phần 3 capture tenant hiện tại, đặt context trong worker thread và khôi phục giá trị trước đó trong finally.

Không truyền nguyên SecurityContext hoặc tenant context không kiểm soát qua mọi executor. Chỉ truyền dữ liệu tối thiểu cần thiết và xác minh quyền ở ranh giới thực thi phù hợp. Với tác vụ chạy lâu hoặc qua process khác, lưu tenant identifier vào message/job metadata có chữ ký hoặc được tạo bởi service tin cậy, sau đó xác thực lại khi consumer nhận message.

### 6.2 Message consumer và scheduled job

Với Kafka/RabbitMQ/JMS hoặc scheduler:

- Message phải mang tenant key rõ ràng nếu xử lý dữ liệu tenant.
- Chỉ producer tin cậy mới được tạo tenant metadata; consumer vẫn kiểm tra tenant tồn tại và được phép xử lý.
- Mở TenantContext trong phạm vi một message/job và luôn đóng trong finally.
- Không dựa vào ThreadLocal còn lại từ message trước.
- Retry/dead-letter phải giữ đúng tenant metadata để tránh xử lý nhầm tenant.
- Nếu batch chứa nhiều tenant, chia batch theo tenant và mở transaction riêng cho từng tenant.

Không dùng tenant id trong message làm căn cứ duy nhất cho quyền truy cập. Nếu message có thể đến từ client hoặc nguồn không tin cậy, cần xác thực chữ ký/producer và kiểm tra quan hệ giữa message, tenant và nghiệp vụ.

## 7. Ngăn rò rỉ qua repository, query và cache

### 7.1 Scope mọi query

Trong shared schema, mỗi query tenant-scoped cần điều kiện tenant. Điều này áp dụng cho:

- Derived query và JPQL.
- Native SQL.
- Query update/delete với @Modifying.
- Specification/Criteria API.
- Pagination, sorting và projection.
- Repository custom implementation và JdbcTemplate.

Không viết một query findAll() cho dữ liệu tenant rồi lọc trong Java sau khi đã tải toàn bộ dữ liệu. Dữ liệu của tenant khác đã đi qua application memory, log hoặc serialization trước khi lọc. Scope phải được áp dụng ngay tại database query.

Với bulk update/delete, kiểm tra điều kiện tenant trong chính câu lệnh SQL/JPQL. Bulk operation thường bỏ qua lifecycle callback và có thể bỏ qua persistence context; cần cân nhắc clearAutomatically hoặc clear/refresh EntityManager phù hợp sau khi chạy.

### 7.2 Cache key phải chứa tenant

Nếu cache chỉ dùng entity id làm key, hai tenant có cùng business id có thể đọc chung cache entry. Key cần bao gồm tenant identifier:

```java
@Cacheable(
    cacheNames = "orders",
    key = "T(com.example.TenantContext).requireTenantId() + ':' + #id"
)
public OrderView getOrder(UUID id) {
    // Load order trong tenant context hiện tại.
}
```

Đây là ví dụ Spring Cache; thay package class và DTO theo dự án. Áp dụng cùng nguyên tắc cho Redis, Caffeine, cache projection, API response cache, search index, object storage path và distributed lock key.

Với Hibernate second-level/query cache, kiểm tra hành vi tenant-aware của đúng phiên bản/provider. Cache tùy chỉnh hoặc cache bên ngoài Hibernate phải tự đưa tenant vào key. Khi logout, chuyển tenant hoặc thay đổi membership, cần cân nhắc invalidation theo tenant/user.

### 7.3 Unique key và quan hệ dữ liệu

Trong shared schema, các ràng buộc thường phải bao gồm tenant:

- UNIQUE (tenant_id, external_id) thay vì chỉ UNIQUE (external_id) nếu mã chỉ duy nhất trong phạm vi tenant.
- Foreign key nên ngăn bản ghi con của tenant A tham chiếu bản ghi cha của tenant B.
- Index thường bắt đầu bằng tenant_id cho các query lọc theo tenant, tùy workload và query plan.
- Các bảng phụ như attachment, audit, outbox, notification và join table cũng cần tenant scope khi chứa dữ liệu tenant.

Với foreign key cross-tenant, có thể dùng composite key/constraint gồm tenant_id và entity id để database kiểm soát quan hệ cùng tenant. Không chỉ dựa vào validation ở service.

## 8. Bảo vệ thêm ở database bằng Row-Level Security

Nếu dùng PostgreSQL shared schema, Row-Level Security (RLS) có thể bổ sung một lớp bảo vệ ở database. Policy lọc các dòng được đọc và kiểm tra dòng được insert/update.

Ví dụ khi tenant_id là UUID:

```sql
ALTER TABLE app.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.orders FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON app.orders
USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::uuid
);
```

Trong mỗi transaction, đặt tenant vào cùng connection trước khi truy cập bảng:

```java
@Transactional
public void processTenantOrder(UUID orderId) {
    String tenantId = TenantContext.requireTenantId();

    entityManager.createNativeQuery(
            "select set_config('app.tenant_id', :tenantId, true)")
        .setParameter("tenantId", tenantId)
        .getSingleResult();

    // Các query tiếp theo trong transaction chịu RLS policy.
    orderRepository.findById(orderId);
}
```

Tham số thứ ba true của set_config yêu cầu giá trị chỉ có hiệu lực trong transaction hiện tại. Câu lệnh phải chạy trên cùng physical connection và trước mọi query cần được bảo vệ. Trong Spring transaction, dùng cùng EntityManager/transaction-bound connection; không đặt session-level setting rồi trả connection chưa reset về pool.

RLS là tính năng PostgreSQL, không phải giải pháp portable cho mọi DBMS. Cần chú ý:

- Role chạy ứng dụng không nên là superuser, có BYPASSRLS hoặc sở hữu bảng theo cách bỏ qua policy. FORCE ROW LEVEL SECURITY buộc table owner chịu policy, nhưng superuser/BYPASSRLS vẫn có thể bypass.
- Khi app.tenant_id chưa được đặt, policy so sánh với NULL không cho phép dòng nào khớp; đây là hành vi fail closed mong muốn.
- Test cả SELECT, INSERT, UPDATE, DELETE, bulk SQL và connection reuse.
- Nếu có bảng không thuộc tenant hoặc job quản trị cross-tenant, thiết kế role/policy riêng có audit; không nới policy cho toàn bộ ứng dụng.

RLS bổ sung cho authorization và query scoping. Nó không thay thế việc xác thực người dùng, kiểm tra membership và giới hạn quyền của application role.

## 9. Kiểm thử chống rò rỉ dữ liệu chéo

Đừng chỉ test rằng tenant A đọc được dữ liệu của chính mình. Cần test cả việc A không thể đọc, sửa, xóa hoặc suy ra sự tồn tại của dữ liệu B.

Bộ test nên bao gồm:

| Kịch bản | Kỳ vọng |
|---|---|
| Tenant A tạo order | Row được gắn tenant A từ server context |
| Tenant B tạo cùng external_id | Được phép nếu unique key chỉ duy nhất trong tenant |
| Tenant A đọc ID thuộc B | Không trả dữ liệu B; API xử lý như not found/forbidden theo policy |
| Tenant A cập nhật hoặc xóa ID thuộc B | Không có row nào của B bị thay đổi |
| Thiếu tenant context | Request/job bị từ chối trước khi truy cập tenant datasource |
| Tenant header không thuộc membership | 403 hoặc lỗi authorization tương ứng |
| Tenant key không có datasource | Routing fail closed, không rơi về datasource mặc định |
| Exception giữa request | Context được xóa; request sau trên cùng thread không nhận tenant cũ |
| @Async/message consumer | Task chạy với đúng tenant đã capture/xác thực |
| Cache cùng ID ở hai tenant | Hai tenant nhận hai cache entry riêng |
| Native/bulk query | Điều kiện tenant hoặc RLS vẫn được áp dụng |
| RLS context không được đặt | Database không trả dòng tenant nào |
| Connection được tái sử dụng | Không còn schema/tenant setting từ request trước |

Có thể dùng Testcontainers với DBMS mục tiêu để kiểm tra routing, schema, RLS, constraint và transaction. Với database-per-tenant, test hai database riêng; với schema-per-tenant, tạo hai schema; với shared schema, tạo dữ liệu tenant A/B trong cùng bảng. Dùng cùng một entity id nếu thiết kế cho phép hoặc cùng business key trong hai tenant để phát hiện cache/query key bị thiếu tenant.

Một test quan trọng là xác minh context được dọn sau exception. Dùng executor có một thread để buộc hai tác vụ chạy tuần tự trên cùng worker thread; tác vụ thứ hai không được nhìn thấy tenant của tác vụ thứ nhất.

## 10. Logging, audit và vận hành

Log nên ghi tenant identifier đã được xác thực để hỗ trợ điều tra, nhưng không ghi thông tin nhạy cảm không cần thiết. Có thể đưa tenant id vào MDC:

- Thiết lập MDC sau khi tenant context được xác thực.
- Xóa MDC trong cùng cleanup path với TenantContext.
- Không dùng tenant id chưa xác thực từ header để gắn vào log như danh tính đáng tin cậy.
- Giới hạn quyền truy cập log vì log có thể tiết lộ quy mô và hoạt động của tenant.

Audit log cho thao tác nhạy cảm nên ghi actor, tenant, action, resource, timestamp, outcome và correlation id. Với quản trị viên truy cập cross-tenant, ghi rõ quyền/justification theo chính sách. Không ghi token, password, nội dung PII hoặc dữ liệu nghiệp vụ đầy đủ nếu không cần.

Metrics có thể phân nhóm theo tenant ở quy mô nhỏ, nhưng không tạo metric label có cardinality vô hạn cho hàng trăm nghìn tenant. Thay vào đó dùng aggregate metrics, sampling, log/tracing có kiểm soát hoặc dashboard theo tenant được chọn khi điều tra.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Request đầu đúng tenant, request sau đọc nhầm | ThreadLocal không được clear | Dùng scope try/finally hoặc interceptor cleanup |
| Async job chạy tenant rỗng/tenant cũ | ThreadLocal không tự truyền qua thread pool | Dùng TaskDecorator hoặc truyền context tường minh |
| Transaction dùng nhầm database | Tenant context được set sau khi transaction bắt đầu | Thiết lập context trước khi gọi transactional service |
| Tenant không có datasource lại rơi về DB mặc định | Routing fallback cho phép default target | Không cấu hình default tenant; fail closed và lenientFallback=false |
| Query trả dữ liệu tenant khác | Thiếu tenant predicate hoặc native SQL bỏ qua filter | Scope query, kiểm thử cross-tenant, cân nhắc RLS |
| Cache trả object của tenant khác | Cache key chỉ chứa entity id | Thêm tenant id vào mọi cache key |
| Tạo entity với tenant do client gửi | Tin tenantId trong request body | Gán tenant từ authenticated context ở server |
| Bản ghi con tham chiếu bản ghi cha tenant khác | Foreign key chỉ kiểm tra entity id | Dùng composite constraint gồm tenant_id |
| RLS không có tác dụng | App role là owner/superuser/BYPASSRLS hoặc setting sai connection | Kiểm tra role, FORCE RLS và transaction-local setting |
| Migration tenant bị lệch phiên bản | Chỉ cập nhật schema của một số tenant | Theo dõi migration version và rollout có kiểm soát |

## 12. Checklist thiết kế an toàn

- [ ] Phân biệt user, customer và tenant trong domain.
- [ ] Tenant được resolve từ principal đã xác thực và membership, không tin header/body trực tiếp.
- [ ] Không có tenant context thì từ chối; không fallback sang tenant mặc định.
- [ ] Tenant context được mở/đóng trong scope rõ ràng và luôn cleanup.
- [ ] Context được truyền tường minh qua async/job/message boundary.
- [ ] Tenant context được thiết lập trước khi transaction bắt đầu.
- [ ] Không đổi tenant giữa một transaction hoặc một persistence context.
- [ ] Mọi query, native SQL, bulk operation và cache đều có tenant isolation.
- [ ] Unique key, foreign key, audit, outbox, file/object storage có tenant scope phù hợp.
- [ ] Routing/schema switching reset connection trước khi trả về pool.
- [ ] Database RLS được cân nhắc như lớp bảo vệ bổ sung cho dữ liệu nhạy cảm.
- [ ] Test chứng minh tenant A không thể đọc/sửa/xóa dữ liệu tenant B.
- [ ] Có test thiếu context, exception cleanup, async propagation và cache isolation.

## 13. Ghi nhớ

- Tenant context là kết quả của authentication và authorization; tenant id từ client chỉ là lựa chọn cần xác minh.
- Database-per-tenant, schema-per-tenant và shared schema có cách routing và cách bảo vệ khác nhau.
- ThreadLocal cần cleanup và không tự truyền qua executor; dùng scope và TaskDecorator.
- Đặt tenant context trước khi @Transactional mở transaction; không đổi tenant giữa transaction.
- Shared schema cần tenant predicate trên mọi query và tenant-aware cache/constraint.
- Không có default tenant fallback; thiếu context phải fail closed.
- RLS có thể bảo vệ thêm ở database nhưng phải dùng application role không bypass policy.
- Kiểm thử cross-tenant theo cả đọc, ghi, xóa, cache, async và connection reuse.

## 14. Tài liệu tham khảo

- [Spring Framework — AbstractRoutingDataSource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/lookup/AbstractRoutingDataSource.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Hibernate ORM — Multi-tenancy](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
