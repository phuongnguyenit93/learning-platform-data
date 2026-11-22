# CurrentTenantIdentifierResolver và phạm vi sử dụng

Trong ứng dụng SaaS sử dụng Hibernate/JPA, một mã nguồn có thể phục vụ nhiều tổ chức khác nhau. Mỗi tổ chức (*tenant*) cần có vùng dữ liệu riêng và không được vô tình truy cập dữ liệu của tổ chức khác. Hibernate phải biết **tenant identifier** mỗi khi khởi tạo một `Session`.

Có thể chọn tenant tường minh:

    try (Session session = sessionFactory.withOptions()
            .tenantIdentifier("tenant-a")
            .openSession()) {
        // Session làm việc với tenant-a.
    }

Nhưng với Spring Data JPA, JTA hoặc `SessionFactory.getCurrentSession()`, ứng dụng không trực tiếp mở tất cả Sessions. Để Hibernate lấy tenant ID từ ngữ cảnh ứng dụng, chúng ta dùng:

    org.hibernate.context.spi.CurrentTenantIdentifierResolver<T>

Ví dụ:

    public final class RequestTenantResolver
            implements CurrentTenantIdentifierResolver<String> {

        @Override
        public String resolveCurrentTenantIdentifier() {
            return TenantContext.requireTenantId();
        }

        @Override
        public boolean validateExistingCurrentSessions() {
            return true;
        }
    }

**Ý tưởng chính:** Resolver cung cấp **tenant identity của Session**. Nó không tự xác thực người dùng, không tự chọn database/schema, không tự áp điều kiện tenant lên mọi native SQL và không thay thế các cơ chế bảo mật.

Bài học thuộc chương **Nhiều tổ chức** trong module *Data Persistence Relational Access ORM Hibernate*. Nội dung sử dụng Hibernate ORM 6.6/7.2, Jakarta Persistence và Spring Boot để làm rõ contract, phạm vi sử dụng, cách tích hợp, kiểm soát transaction/context và các lỗi multi-tenancy khó phát hiện.

## 1. Tenant ID và user identity là hai khái niệm khác nhau

Giả sử Alice có quyền ở hai tổ chức:

    Alice:
      tenant-a -> ADMIN
      tenant-b -> VIEWER

Một request của Alice có thể chọn tenant-a để sửa dữ liệu. Request khác chọn tenant-b chỉ để đọc. Tenant ID ở đây không phải user ID, tên hiển thị, hostname hoặc database URL.

| Khái niệm | Vai trò |
| --- | --- |
| Authentication | Xác minh người dùng hoặc service identity |
| Authorization | Xác định identity có quyền làm gì ở tenant nào |
| Tenant identifier | Định danh vùng dữ liệu mà Session sử dụng |
| Tenant context | Nơi ứng dụng giữ tenant ID đã được phê duyệt |
| CurrentTenantIdentifierResolver | Chuyển tenant context thành tenant ID cho Hibernate |
| Connection/schema routing | Tìm tài nguyên database tương ứng |
| Tenant discriminator | Đánh dấu tenant sở hữu một hàng dữ liệu |

Một client biết chuỗi `tenant-b` không đồng nghĩa có quyền truy cập tenant-b. Phải authorize trước khi để resolver cung cấp chuỗi đó cho Hibernate.

## 2. Ba mô hình multi-tenancy

**Database-per-tenant**:

    Application
       |-- tenant-a --> Database A
       |-- tenant-b --> Database B

Mỗi tenant có database riêng. Hibernate cần JDBC connection đúng database.

**Schema-per-tenant**:

    One database
       |-- schema tenant_a: products, orders
       |-- schema tenant_b: products, orders

Các tenant chia sẻ database nhưng có schema khác nhau; cần chọn schema đúng trên connection.

**Shared-schema/discriminator**:

    products
    +----+-----------+-------------------+
    | id | tenant_id | name              |
    +----+-----------+-------------------+
    |  1 | tenant-a  | Product for A     |
    |  2 | tenant-b  | Product for B     |
    +----+-----------+-------------------+

Các tenant chia sẻ bảng, mỗi row mang tenant discriminator. Hibernate có `@TenantId` cho kiểu mapping này.

Resolver có thể được dùng trong cả ba mô hình, nhưng chỉ cung cấp **tenant identifier**; các thành phần khác thực thi isolation.

## 3. Mô hình trách nhiệm

    Authenticated request
            |
            v
    Tenant authorization
            |
            v
    Trusted TenantContext
            |
            v
    CurrentTenantIdentifierResolver
            |
            v
    Hibernate Session có tenant ID
            |
            +--> Database-per-tenant: MultiTenantConnectionProvider
            |
            +--> Schema-per-tenant: schema routing / TenantSchemaMapper
            |
            +--> Shared-schema: @TenantId discriminator
            |
            v
    SQL và persistence context của tenant

Resolver không tự xác định JDBC URL, database schema, quyền truy cập, PK/FK constraints hoặc native SQL WHERE. Nếu chỉ viết resolver mà chưa cấu hình strategy phù hợp, ứng dụng **chưa có multi-tenancy an toàn**.

## 4. Contract chính thức trong Hibernate 6.6/7.2

Interface generic có ba phương thức quan trọng:

    public interface CurrentTenantIdentifierResolver<T> {

        T resolveCurrentTenantIdentifier();

        boolean validateExistingCurrentSessions();

        default boolean isRoot(T tenantId) {
            return false;
        }
    }

Đây là bản giản lược để minh họa contract.

| Method | Ý nghĩa |
| --- | --- |
| `resolveCurrentTenantIdentifier()` | Trả tenant ID trong context hiện tại |
| `validateExistingCurrentSessions()` | Có xác minh existing current Session khớp tenant ID không |
| `isRoot(T tenantId)` | Có coi tenant ID này là root tenant theo tính năng hỗ trợ không |

Hibernate 6.6/7.2 sử dụng `CurrentTenantIdentifierResolver<T>`. Tài liệu Hibernate 5.x/6.1 cũ có thể dùng interface không generic và trả `String`. Khi áp dụng phải đối chiếu Javadocs đúng version.

Trong ví dụ, `T` là `String`. Kiểu này cần nhất quán với mapping và các SPI liên quan.

## 5. Khi nào Hibernate gọi resolver?

Theo Hibernate User Guide, hai tình huống nổi bật:

1. Ứng dụng sử dụng `CurrentSessionContext` với `SessionFactory.getCurrentSession()`. Nếu phải tạo một Session mới trong scope, Hibernate hỏi resolver tenant ID.
2. Ứng dụng không muốn truyền tenant ID khi tạo từng Session. Resolver được dùng làm nguồn tenant mặc định theo context.

    getCurrentSession()
           |
           v
    Có current Session trong scope?
       |                |
      Có               Không
       |                |
       v                v
    Reuse /          Resolver trả tenant
    validate               |
       |                   v
       |              Open tenant Session
       +-------------------+
                           |
                           v
                       ORM operations

**Không phải mọi query đều gọi lại resolver.** Tenant identity thông thường được gắn khi tạo Session, không phải một tham số thay đổi tùy ý theo từng SELECT.

## 6. Tenant gắn với Session, không gắn với một query

Một `Session` có tenant ID, persistence context, managed entities và transaction state.

    Session A:
      tenant-a
      Product id=42 của tenant-a
      Order id=7 của tenant-a

    Session B:
      tenant-b
      Product id=42 của tenant-b
      Order id=7 của tenant-b

Sai:

    // Session đã mở cho tenant-a.
    TenantContext.use("tenant-b");

    // Session không tự đổi tenant!
    session.find(Product.class, 42L);

Thay `ThreadLocal` không chuyển Session sang tenant-b. L1 cache có thể vẫn chứa Product 42 của tenant-a.

**Muốn đổi tenant, phải kết thúc unit of work và mở Session/EntityManager mới.**

## 7. TenantContext theo scope của thread

Đối với Servlet application đồng bộ, `ThreadLocal` có thể giúp giữ tenant ID của request:

    package com.example.multitenancy;

    public final class TenantContext {

        private static final ThreadLocal<String> CURRENT =
            new ThreadLocal<>();

        private TenantContext() {
        }

        public static String requireTenantId() {
            String id = CURRENT.get();

            if (id == null || id.isBlank()) {
                throw new IllegalStateException(
                    "Chưa có tenant hợp lệ"
                );
            }

            return id;
        }

        public static Scope use(String tenantId) {
            if (tenantId == null || tenantId.isBlank()) {
                throw new IllegalArgumentException(
                    "Tenant ID không được rỗng"
                );
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

        @FunctionalInterface
        public interface Scope extends AutoCloseable {
            @Override
            void close();
        }
    }

Sử dụng:

    String approvedTenant =
        tenantAuthorization.requireMembership(
            authenticatedPrincipal,
            requestedTenantId
        );

    try (TenantContext.Scope scope =
             TenantContext.use(approvedTenant)) {

        documentService.listDocuments();
    }

`tenantAuthorization` và `documentService` là components của ứng dụng. Đặt tenant context **sau khi xác thực/ủy quyền**, trước khi Hibernate Session được tạo.

### Vì sao cần cleanup?

Web servers tái sử dụng threads. Nếu request A đặt `tenant-a` mà không xóa ThreadLocal, request B cùng thread có thể nhìn thấy tenant-a dù chưa được xác thực.

`try-with-resources` gọi `Scope.close()` ngay cả khi có exception; đồng thời scope hoàn nguyên giá trị trước đó.

Scope lồng nhau không có nghĩa được phép chuyển tenant của một Session đang mở. Session/transaction vẫn phải có ranh giới riêng.

## 8. Viết resolver fail closed

    package com.example.multitenancy;

    import org.hibernate.context.spi.CurrentTenantIdentifierResolver;

    public final class RequestTenantResolver
            implements CurrentTenantIdentifierResolver<String> {

        @Override
        public String resolveCurrentTenantIdentifier() {
            return TenantContext.requireTenantId();
        }

        @Override
        public boolean validateExistingCurrentSessions() {
            return true;
        }
    }

Resolver chỉ đọc context; không cần biết HTTP request hoặc JDBC Connection.

**Fail closed** nghĩa thiếu tenant thì ném exception. Không nên:

    @Override
    public String resolveCurrentTenantIdentifier() {
        String id = TenantContext.getOrNull();
        return id == null ? "public" : id;
    }

Một request thiếu context vì lỗi pipeline sẽ bị route âm thầm sang tenant `public`. Nếu `public` chứa dữ liệu thật, điều đó gây sai hành vi hoặc lộ thông tin.

Tuyệt đối tránh fallback thành `system-root`.

## 9. `validateExistingCurrentSessions()` dùng để làm gì?

Method này được Hibernate mô tả cho tình huống `CurrentSessionContext.currentSession()` phát hiện current Session **đã tồn tại trong scope**.

    Existing current Session:
      tenant-a

    Resolver tại thời điểm kiểm tra:
      tenant-b

Nếu:

    @Override
    public boolean validateExistingCurrentSessions() {
        return true;
    }

Hibernate có thể đối chiếu tenant của existing Session với kết quả resolver. Khi khác nhau, Hibernate có thể ném:

    org.hibernate.context.TenantIdentifierMismatchException

### Nó không làm những gì?

- Không xác thực user membership.
- Không kiểm tra mọi `SessionFactory.openSession()`.
- Không kiểm tra từng SQL SELECT.
- Không thay tenant của Session.
- Không xóa entities đang managed.
- Không sửa connection pool bị route sai.
- Không tự thêm tenant predicate cho native SQL.

Vì vậy `validateExistingCurrentSessions=true` là cơ chế phát hiện lỗi **current-session reuse**, không phải hệ thống authorization.

Không trả `false` chỉ để bỏ qua một mismatch thật; nên sửa lifecycle Session/context.

## 10. `getCurrentSession` và `openSession` khác nhau

    Session current =
        sessionFactory.getCurrentSession();

    Session fresh =
        sessionFactory.openSession();

`getCurrentSession()` phụ thuộc `CurrentSessionContext`: thread-bound, JTA hoặc managed context theo configuration. Nó có thể lấy Session đã bind, hoặc tạo Session mới nếu contract cho phép.

`openSession()` tạo Session mới. Nếu không truyền tenant ID explicit, Hibernate có thể dùng resolver mặc định.

| API | Đặc điểm |
| --- | --- |
| `getCurrentSession()` | Sử dụng current-session context |
| `openSession()` | Mở Session mới |
| `withOptions().tenantIdentifier(id).openSession()` | Mở Session với tenant tường minh |
| `EntityManagerFactory.createEntityManager(Map)` | Có thể truyền Hibernate tenant hint |
| Spring `@PersistenceContext` | EntityManager thường do Spring quản lý |

Nếu app chưa cấu hình current-session context, `getCurrentSession()` có thể báo lỗi. Trong Spring, không cần tự bind `ThreadLocalSessionContext` khi framework đang quản lý transactions.

## 11. Explicit tenant trong Hibernate Session

Một cách rõ ràng không phụ thuộc resolver:

    try (Session session = sessionFactory.withOptions()
            .tenantIdentifier("tenant-a")
            .openSession()) {

        Transaction tx = session.beginTransaction();

        try {
            processTenantData(session);
            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        }
    }

Thích hợp cho:

- Scheduled/batch jobs.
- Integration tests.
- Administrative workflows được authorize.
- Native Hibernate applications tự quản Session.
- Các job xử lý từng tenant một.

Nếu tenant ID đã được truyền explicit, resolver không cần chọn tenant cho lời gọi Session builder đó.

## 12. Explicit tenant trong JPA EntityManager

Hibernate cung cấp:

    org.hibernate.jpa.HibernateHints.HINT_TENANT_ID

Ví dụ:

    import java.util.Map;
    import jakarta.persistence.EntityManager;
    import org.hibernate.jpa.HibernateHints;

    EntityManager em =
        entityManagerFactory.createEntityManager(
            Map.of(
                HibernateHints.HINT_TENANT_ID,
                "tenant-b"
            )
        );

    try {
        List<Product> products = em.createQuery(
            "from Product p", Product.class
        ).getResultList();
    } finally {
        em.close();
    }

Đây là Hibernate-specific hint **khi tạo EntityManager**, không phải query hint để đổi tenant của EntityManager đang tồn tại.

Với Spring-managed EntityManager, thường nên để framework tạo Session đúng tenant từ resolver.

## 13. Cấu hình Hibernate resolver

Property chính:

    hibernate.tenant_identifier_resolver

Constant:

    MultiTenancySettings.MULTI_TENANT_IDENTIFIER_RESOLVER

Ví dụ programmatic:

    Map<String, Object> settings = new HashMap<>();

    settings.put(
        MultiTenancySettings.MULTI_TENANT_IDENTIFIER_RESOLVER,
        new RequestTenantResolver()
    );

Hibernate MultiTenancySettings cho phép sử dụng resolver instance, implementation `Class` hoặc class name theo version hỗ trợ.

Nếu resolver cần dependency injection, **instance** thường dễ kiểm soát hơn tên class dạng chuỗi.

## 14. SessionFactoryBuilder integration

Native Hibernate boot có method:

    SessionFactoryBuilder.applyCurrentTenantIdentifierResolver(
        CurrentTenantIdentifierResolver<?> resolver
    )

Ví dụ:

    Metadata metadata = metadataSources.buildMetadata();

    SessionFactory factory = metadata
        .getSessionFactoryBuilder()
        .applyCurrentTenantIdentifierResolver(
            new RequestTenantResolver()
        )
        .build();

`metadataSources` giả định đã được cấu hình entity mappings, JDBC services và tenancy strategy. Đoạn code chỉ minh họa cách đăng ký resolver.

Resolver được gắn ở **factory bootstrap**, không phải thay động giữa các requests.

## 15. Spring Boot `HibernatePropertiesCustomizer`

Với Spring Boot 3.x:

    package com.example.multitenancy.config;

    import org.hibernate.cfg.MultiTenancySettings;
    import org.hibernate.context.spi.CurrentTenantIdentifierResolver;
    import org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer;
    import org.springframework.context.annotation.Bean;
    import org.springframework.context.annotation.Configuration;

    @Configuration(proxyBeanMethods = false)
    public class TenantHibernateConfiguration {

        @Bean
        CurrentTenantIdentifierResolver<String> tenantResolver() {
            return new RequestTenantResolver();
        }

        @Bean
        HibernatePropertiesCustomizer tenantCustomizer(
                CurrentTenantIdentifierResolver<String> resolver) {

            return properties -> properties.put(
                MultiTenancySettings.MULTI_TENANT_IDENTIFIER_RESOLVER,
                resolver
            );
        }
    }

Với Spring Boot 4.x, `HibernatePropertiesCustomizer` được chuyển sang package:

    org.springframework.boot.hibernate.autoconfigure.HibernatePropertiesCustomizer

Cần dùng đúng Spring Boot/Hibernate versions. Với nhiều EntityManagerFactories tự cấu hình, phải bảo đảm resolver được đưa vào **đúng factory**.

Một cấu hình bằng FQCN:

    spring.jpa.properties.hibernate.tenant_identifier_resolver=com.example.multitenancy.RequestTenantResolver

chỉ phù hợp khi Hibernate/provider có thể tạo instance từ class name theo cơ chế version. Nó không tự bảo đảm constructor dependencies được inject từ Spring.

## 16. Thứ tự tenant context và transaction

Một flow an toàn:

    HTTP request
      -> Authenticate principal
      -> Authorize requested tenant
      -> TenantContext.use(approvedTenant)
      -> Call @Transactional service
      -> Session/EntityManager created
      -> Repository queries
      -> Commit/rollback and close
      -> Cleanup TenantContext

Ví dụ:

    public List<DocumentDto> handleRequest(
            Principal principal,
            String requestedTenant) {

        String authorized =
            tenantAccess.requireAuthorizedTenant(
                principal, requestedTenant
            );

        try (TenantContext.Scope scope =
                 TenantContext.use(authorized)) {

            return transactionalDocumentService.findDocuments();
        }
    }

`transactionalDocumentService` nên là bean khác có method `@Transactional` được gọi qua Spring proxy đúng cách.

Không set tenant sau lời gọi repository đầu tiên. Session có thể đã được mở và bound với tenant khác.

## 17. Servlet request filter

Một synchronous web application có thể đặt TenantContext trong filter chạy **sau authentication và trước persistence access**.

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Principal principal =
            authentication.currentPrincipal();

        String requested =
            tenantSelection.fromRequest(request);

        String authorized =
            tenantAuthorization.requireTenant(
                principal, requested
            );

        try (TenantContext.Scope scope =
                 TenantContext.use(authorized)) {

            chain.doFilter(request, response);
        }
    }

Các dependencies là ví dụ, không phải Hibernate APIs.

Cần kiểm tra thứ tự filter chain, request exception paths, async servlet dispatch và Open Session in View. **Không lấy tenant từ header do client gửi rồi tin ngay.**

## 18. ThreadLocal không tự truyền qua async threads

Ví dụ:

    try (TenantContext.Scope scope =
             TenantContext.use("tenant-a")) {

        CompletableFuture.runAsync(() -> {
            repository.findAll();
        });
    }

Worker thread không được bảo đảm có TenantContext đúng; ThreadLocal không tự propagate qua mọi executor.

| Execution model | Cách tiếp cận |
| --- | --- |
| Servlet synchronous | Scoped ThreadLocal và cleanup |
| `@Async` | Truyền tenant ID/context rõ |
| CompletableFuture | Scope tenant trong worker |
| Scheduled job | Tenant explicit từ trusted registry |
| Message consumer | Verify tenant từ message/source |
| Reactor/WebFlux | Dùng context propagation thích hợp, không dựa ThreadLocal đơn thuần |
| Virtual threads | Kiểm soát lifecycle và propagation |
| Batch nhiều tenants | Tách Session/transaction theo tenant |

Không dùng một static mutable `String currentTenant` dùng chung toàn JVM vì concurrent requests sẽ ghi đè nhau.

## 19. Scheduled jobs và background consumers

Không có HTTP request trong một scheduled job:

    for (String tenantId :
            tenantRegistry.approvedActiveTenants()) {

        try (TenantContext.Scope scope =
                 TenantContext.use(tenantId)) {

            tenantJobService.processOneTenant();
        }
    }

Mỗi vòng phải tạo transaction/Session đúng tenant; danh sách tenants phải đến từ trusted registry.

Cách tường minh với native Sessions:

    for (String tenantId : approvedTenantIds) {
        try (Session session = sessionFactory.withOptions()
                .tenantIdentifier(tenantId)
                .openSession()) {

            // Một transaction cho tenantId.
        }
    }

Không dùng một Session duy nhất xuyên qua vòng lặp và thay tenant context.

Với message consumer, tenant ID trong payload cũng cần verify producer/service identity và authorization scope.

## 20. Resolver và `MultiTenantConnectionProvider`

Hai contracts trả lời hai câu hỏi:

    Resolver:
      "Tenant hiện tại là ai?"
      -> tenant-a

    MultiTenantConnectionProvider:
      "Với tenant-a, dùng JDBC Connection nào?"
      -> DataSource/Database A

Các phương thức provider thường có:

    Connection getConnection(String tenantId);

    void releaseConnection(
        String tenantId, Connection connection);

    Connection getAnyConnection();

    void releaseAnyConnection(Connection connection);

    boolean supportsAggressiveRelease();

Đây là trích yếu để học, không phải full implementation interface.

Connection provider cần chọn đúng pool/resource, release đúng pool, bảo đảm connection state an toàn và phục vụ một connection metadata khi Hibernate bootstrap.

Resolver **không** nên truy vấn database hoặc tự mở connection để tìm tenant; làm vậy dễ gây recursion và tăng overhead.

## 21. Database-per-tenant configuration

Hibernate settings:

    hibernate.tenant_identifier_resolver=...
    hibernate.multi_tenant_connection_provider=...

Hoặc Java:

    properties.put(
        MultiTenancySettings.MULTI_TENANT_IDENTIFIER_RESOLVER,
        tenantResolver
    );

    properties.put(
        MultiTenancySettings.MULTI_TENANT_CONNECTION_PROVIDER,
        multiTenantConnectionProvider
    );

Flow:

    Session tenant-a -> provider -> Database A
    Session tenant-b -> provider -> Database B

`getAnyConnection()` dùng cho mục đích metadata/bootstrapping của Hibernate trong contract phù hợp. Nó không đại diện một “root tenant request” được phép đọc tất cả dữ liệu.

## 22. Schema-per-tenant trên Hibernate 6.6 và 7.2

Ví dụ:

    app_db
       schema tenant_a
          products, orders
       schema tenant_b
          products, orders

Trong Hibernate 6.x, schema-based multi-tenancy thường dùng `MultiTenantConnectionProvider` để lấy/set schema của connection.

Hibernate **7.1+** giới thiệu:

    org.hibernate.context.spi.TenantSchemaMapper<T>

với method:

    String schemaName(T tenantIdentifier);

và setting:

    hibernate.multi_tenant.schema_mapper

Ví dụ Hibernate 7.2:

    import org.hibernate.context.spi.TenantSchemaMapper;

    public final class TenantSchemaDirectory
            implements TenantSchemaMapper<String> {

        private final Map<String, String> schemas = Map.of(
            "tenant-a", "tenant_a",
            "tenant-b", "tenant_b"
        );

        @Override
        public String schemaName(String tenantId) {
            String schema = schemas.get(tenantId);

            if (schema == null) {
                throw new IllegalArgumentException(
                    "Unknown tenant"
                );
            }

            return schema;
        }
    }

`TenantSchemaMapper` được đánh dấu incubating trong Hibernate 7.2 và **không có trong 6.6**. Phải chọn SPI đúng target version.

Không ghép tenant ID do client truyền thành SQL schema identifier; dùng canonical mapping/allowlist.

## 23. Schema connection leakage

Một connection pool tái sử dụng connection:

    Tenant-a:
      Borrow Connection C
      Set schema tenant_a
      Query
      Return C without reset

    Tenant-b:
      Borrow SAME C
      Query before setting schema correctly
      -> Có thể đọc sai tenant_a

Resolver trả tenant-b không đủ để sửa lỗi đó. Provider/mapper phải chọn schema đúng, reset connection state, quản lý transaction/search_path/session variables và test connection reuse sau rollback/exception.

Một test hữu ích là pool size=1, request tenant-a xong rồi tenant-b để buộc sử dụng lại cùng connection.

## 24. Shared-schema với `@TenantId`

SQL:

    CREATE TABLE invoices (
        id BIGINT PRIMARY KEY,
        tenant_id VARCHAR(64) NOT NULL,
        invoice_number VARCHAR(80) NOT NULL,
        total NUMERIC(18, 2) NOT NULL
    );

Entity:

    package com.example.billing.domain;

    import jakarta.persistence.Column;
    import jakarta.persistence.Entity;
    import jakarta.persistence.GeneratedValue;
    import jakarta.persistence.GenerationType;
    import jakarta.persistence.Id;
    import jakarta.persistence.Table;
    import org.hibernate.annotations.TenantId;

    @Entity
    @Table(name = "invoices")
    public class Invoice {

        @Id
        @GeneratedValue(strategy = GenerationType.IDENTITY)
        private Long id;

        @TenantId
        @Column(name = "tenant_id", nullable = false)
        private String tenantId;

        @Column(name = "invoice_number", nullable = false)
        private String number;

        @Column(name = "total", nullable = false)
        private BigDecimal total;

        protected Invoice() {}

        public String getTenantId() {
            return tenantId;
        }
    }

`@TenantId` đánh dấu tenant discriminator. Hibernate 6.x/7.x tự gán tenant ID theo Session khi entity lần đầu persistent; application không nên tự sửa field đó.

Resolver chọn tenant của Session. Mapping `@TenantId` hỗ trợ SQL filtering trên các ORM paths phù hợp.

**Chỉ có field `tenantId` bình thường không đồng nghĩa đã bật tenant filtering.** Phải có mapping/strategy riêng.

## 25. Native SQL không tự chịu discriminator filter

Hibernate documentation nói rõ native SQL queries **không được tự động lọc theo tenant ID** trong discriminator-based multi-tenancy.

Sai nếu cần tenant isolation:

    session.createNativeQuery(
        "select id, tenant_id, total from invoices"
    );

Một hướng tenant-aware:

    List<Object[]> rows = session.createNativeQuery(
        """
        select id, tenant_id, total
        from invoices
        where tenant_id = :tenantId
        """,
        Object[].class
    )
    .setParameter("tenantId", authorizedTenantId)
    .getResultList();

Vẫn cần authorization; nếu có yêu cầu nghiêm ngặt, kết hợp database Row-Level Security hoặc cách cô lập khác.

Resolver **không phải SQL firewall** và không sửa arbitrary JDBC/raw SQL do ứng dụng viết.

## 26. Resolver khác Hibernate dynamic `@Filter`

Dynamic filter:

    @FilterDef(
        name = "tenantFilter",
        parameters = @ParamDef(
            name = "tenantId",
            type = String.class
        )
    )
    @Filter(
        name = "tenantFilter",
        condition = "tenant_id = :tenantId"
    )
    @Entity
    public class Invoice {
        // ...
    }

Bật:

    session.enableFilter("tenantFilter")
           .setParameter("tenantId", tenantId);

So sánh:

| Cơ chế | CurrentTenantIdentifierResolver | `@Filter` |
| --- | --- | --- |
| Vai trò | Xác định tenant identity Session | Bật predicate trên mapping |
| Scope | Session creation/current-session validation | Filter state trong Session |
| Database routing | Không tự làm | Không tự làm |
| Shared-table isolation | Cần `@TenantId`/strategy | Phụ thuộc mapping đã gắn filter |
| Native SQL | Không tự sửa | Không tự sửa |
| Có thể toggle khi Session mở? | Không đổi tenant identity | Có thể đổi filter, nhưng L1 không tự refilter |

Không dùng một filter tùy chọn làm lớp bảo vệ duy nhất khi tenant isolation là yêu cầu bảo mật.

## 27. `isRoot(T)` và root tenant

Interface có method default:

    default boolean isRoot(T tenantId) {
        return false;
    }

Nó cho Hibernate biết một tenant ID có đại diện **root tenant** được phép truy cập nhiều partitions theo tính năng hỗ trợ hay không.

Ví dụ concept:

    @Override
    public boolean isRoot(String tenantId) {
        return "system-root".equals(tenantId);
    }

**Đừng biến mọi tenant admin thành root.** Admin trong tenant-a không đồng nghĩa superuser toàn hệ thống.

Root không tự route tới mọi database khi database-per-tenant sử dụng connection provider riêng. Cần special authorization, audit, service identity và giới hạn phạm vi dữ liệu.

Đặc biệt không dùng:

    return tenantId == null ? "system-root" : tenantId;

vì lỗi thiếu context có thể biến request thường thành root.

## 28. Cache và tenant isolation

L1 cache thuộc Session. Nếu Session tenant-a giữ Product 42, đổi ThreadLocal tenant-b mà vẫn dùng Session cũ có thể trả object A đang managed.

L2 cache của Hibernate có các cơ chế tenant-aware theo multi-tenancy strategy, nhưng cache ứng dụng tự viết có thể sai:

    Map<Long, ProductDto> cache;

Nếu tenant-a và tenant-b cùng có ID 42, key Long 42 không đủ phân biệt.

Một key tốt hơn:

    record TenantProductKey(
        String tenantId,
        Long productId
    ) {}

HTTP/Redis/DTO caches cũng cần tenant dimension. Cache hit không phải bằng chứng đã authorize tenant.

## 29. Foreign keys và database constraints

Resolver không tự tạo database constraints bảo vệ cross-tenant relationships. Với shared tables, đôi khi cần composite PK/FK:

    CREATE TABLE customers (
        tenant_id VARCHAR(64) NOT NULL,
        customer_id BIGINT NOT NULL,
        name VARCHAR(200) NOT NULL,
        PRIMARY KEY (tenant_id, customer_id)
    );

    CREATE TABLE orders (
        tenant_id VARCHAR(64) NOT NULL,
        order_id BIGINT NOT NULL,
        customer_id BIGINT NOT NULL,
        PRIMARY KEY (tenant_id, order_id),
        FOREIGN KEY (tenant_id, customer_id)
            REFERENCES customers(tenant_id, customer_id)
    );

FK với cặp tenant/customer ngăn order tenant-a tham chiếu customer thuộc tenant-b có cùng local customer ID.

Không phải mọi hệ thống cần composite PK; globally unique identifiers cũng có thể dùng, nhưng thiết kế constraints phải phản ánh tenant isolation.

## 30. Database Row-Level Security

Với PostgreSQL hoặc DB hỗ trợ RLS, ứng dụng có thể enforce tenant access ở tầng database.

Cần phối hợp:

- DB principal và quyền bypass RLS.
- Tenant context trên connection/transaction.
- Connection pool state reset.
- Policy cho native SQL và background jobs.
- Hibernate Session tenant identity.
- Service authorization.

Resolver không tự đặt database session variables và không thay thế RLS.

## 31. `@Transactional`, `REQUIRES_NEW` và nhiều tenants

Một transaction nên có tenant context ổn định. Nếu Spring `REQUIRES_NEW` tạo Session mới, resolver phải nhìn thấy tenant đã được approve trước khi transaction mới mở.

Không dùng `REQUIRES_NEW` như cách switch tenant tùy tiện khi outer Session còn managed entities tenant cũ.

Với cross-tenant report:

1. Authorize hoạt động cross-tenant.
2. Đọc từng tenant bằng Session/transaction riêng.
3. Chuyển kết quả thành DTO.
4. Đóng Session trước khi chuyển tenant.
5. Tổng hợp ngoài persistence context.
6. Audit phạm vi từng tenant.

## 32. Open Session in View (OSIV)

Spring OSIV có thể giữ EntityManager qua controller/view rendering, lâu hơn service transaction.

Các rủi ro:

- Session được tạo trước tenant context nếu web filters sai thứ tự.
- Lazy loading xảy ra sau transaction.
- Tenant context cleanup trước serialization/async continuation.
- Entity graph bị serialize rộng hơn dữ liệu đã authorize.

Cân nhắc tắt OSIV và dùng DTO trong service transaction cho API multi-tenant nhạy cảm, hoặc thiết kế request-scoped tenant context nhất quán.

Không dùng một Session qua nhiều HTTP requests.

## 33. Lỗi `TenantIdentifierMismatchException`

Khi current Session tenant-a còn tồn tại nhưng resolver trả tenant-b và validation bật, Hibernate có thể báo mismatch.

Không nên nuốt exception rồi tiếp tục dùng Session.

Quy trình:

1. Dừng unit of work.
2. Rollback transaction nếu cần.
3. Close/unbind Session theo framework lifecycle.
4. Tìm nơi TenantContext bị đổi sau Session creation.
5. Sửa filter/transaction boundaries.
6. Nếu retry, tạo Session mới cho tenant đúng.

Mismatch biểu thị một lỗi quản lý context, không phải điều kiện bình thường để bắt rồi bỏ qua.

## 34. Unit test resolver

JUnit 5:

    @Test
    void missingTenantFailsClosed() {
        RequestTenantResolver resolver =
            new RequestTenantResolver();

        assertThrows(
            IllegalStateException.class,
            resolver::resolveCurrentTenantIdentifier
        );
    }

Test phải đảm bảo ThreadLocal từ test trước đã cleanup.

    @Test
    void resolverReadsScopedTenant() {
        RequestTenantResolver resolver =
            new RequestTenantResolver();

        try (TenantContext.Scope scope =
                 TenantContext.use("tenant-a")) {

            assertEquals(
                "tenant-a",
                resolver.resolveCurrentTenantIdentifier()
            );
        }
    }

Unit test này kiểm tra resolution, không kiểm tra tenant authorization hoặc database routing.

## 35. Integration test hai tenants

Với database/schema-per-tenant:

    tenant-a: Product id=42, name="A Product"
    tenant-b: Product id=42, name="B Product"

Code test:

    try (Session a = sessionFactory.withOptions()
             .tenantIdentifier("tenant-a")
             .openSession();
         Session b = sessionFactory.withOptions()
             .tenantIdentifier("tenant-b")
             .openSession()) {

        Product productA = a.find(Product.class, 42L);
        Product productB = b.find(Product.class, 42L);

        // Assert name/tenant/routing/cache chính xác.
    }

Nếu dùng shared-table với PK toàn cục, fixture phải tuân thủ PK constraint; không cố insert duplicate IDs khi schema không cho phép.

Cần kiểm tra native SQL và cache khi có nhiều tenants, không chỉ entity `find`.

## 36. Test current-session validation

Một kịch bản:

1. Cài `CurrentSessionContext` hoạt động.
2. Resolver trả `validateExistingCurrentSessions()=true`.
3. TenantContext là tenant-a.
4. Gọi `getCurrentSession()` và giữ Session trong scope.
5. Trong test, chuyển TenantContext sang tenant-b.
6. Gọi `getCurrentSession()` lần nữa.
7. Kiểm tra mismatch exception theo Hibernate version.
8. Rollback/close/cleanup.

Không viết test khẳng định `openSession()` cũng có exact validation như `getCurrentSession()`. Contract nói tới current-session context.

## 37. Test async propagation và connection reuse

Với async:

    Trusted message tenant-a
       -> worker verifies scope
       -> TenantContext.use(tenant-a)
       -> create Session/transaction
       -> process
       -> cleanup

Không có tenant → fail closed, không lấy stale ThreadLocal từ worker pool.

Với schema connection reuse:

    Pool size = 1
    tenant-a borrows C -> schema tenant_a -> release
    tenant-b borrows C -> schema tenant_b -> release

Nếu tenant-b thấy dữ liệu tenant-a, lỗi ở schema routing/reset; resolver không khắc phục được.

Test thêm exception/rollback path.

## 38. Monitoring và hiệu năng

| Chỉ số | Điều cần quan sát |
| --- | --- |
| Tenant resolution failures | Request/job thiếu tenant |
| Tenant mismatch | Current Session scope sai |
| Unauthorized selection | User cố chọn tenant không được phép |
| DB pool usage | Routing/pool capacity |
| Connection state leaks | Schema hoặc role sai sau reuse |
| SQL latency | Workload và index theo tenant |
| Cache hit/miss | Tenant-aware caching |
| Schema migration state | Tenant DB/schema chưa cùng version |
| Background job progress | Retry/checkpoint per tenant |

Resolver nên nhẹ, không blocking network/DB I/O. Đừng truy vấn chính SessionFactory từ trong resolver để tìm tenant directory: có nguy cơ mở Session đệ quy.

## 39. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Resolver không được gọi | Tenant explicit hoặc Session đã tồn tại | Kiểm tra Session creation |
| Thiếu tenant | Set context quá muộn | Đặt trước transaction |
| Mismatch exception | Existing Session tenant khác context | Sửa scope |
| Resolver trả null | Chưa có trusted tenant | Fail closed |
| Cả app cùng tenant | Static/global fallback | Scoped context |
| Root thấy mọi dữ liệu | `isRoot` quá rộng | Special authorization |
| Schema B đọc A | Connection chưa reset | Provider/pool |
| Native SQL thấy tất cả tenants | Thiếu tenant predicate/RLS | Sửa SQL/database policy |
| `@TenantId` không lọc | Mapping/config chưa đúng | Kiểm tra SQL và mapping |
| Hibernate 6.6 thiếu TenantSchemaMapper | API từ 7.1 | Chọn SPI đúng version |
| Spring không inject resolver | FQCN được instantiate ngoài Spring | Dùng customizer instance |
| Multi-EMF chỉ một có resolver | Config không áp mọi factory | Cấu hình từng factory |
| `@Async` thiếu tenant | ThreadLocal không propagate | Explicit worker scope |
| Scheduler dùng tenant cũ | Quên cleanup | try-with-resources/finally |
| Cache nhầm tenant | App cache key thiếu tenant | Tenant-aware key |
| Session cũ thấy entity cũ | L1 persistence context | New Session |
| OSIV load ngoài scope | Lifecycle kéo dài | DTO/OSIV policy |
| Connection pool cạn | Tạo pool per tenant không giới hạn | Capacity planning |
| Hibernate startup vòng lặp | Resolver gọi Hibernate session | Resolver chỉ đọc context |

## 40. Anti-patterns cần tránh

**Global mutable tenant:**

    public static String currentTenant;

Concurrent requests có thể ghi đè nhau.

**Tin header client trực tiếp:**

    return request.getHeader("X-Tenant-Id");

Nếu không authorize, người dùng có thể đoán tenant khác.

**Fallback root khi thiếu tenant:**

    return tenantId == null ? "system-root" : tenantId;

Biến bug thành đặc quyền cao nhất.

**Đổi context giữa Session:**

    // Session tenant-a đã tồn tại.
    TenantContext.use("tenant-b");

Không thay tenant của Session.

**Resolver tự mở connection:**

    public String resolveCurrentTenantIdentifier() {
        Connection c = dataSource.getConnection();
        // ...
    }

Trộn trách nhiệm, dễ recursion và resource leaks.

**Cache chỉ key bằng entity ID:**

    Map<Long, ProductDto> globalCache;

Có thể va chạm dữ liệu giữa tenants.

## 41. Sơ đồ lựa chọn cơ chế

    Bắt đầu: cần truy cập dữ liệu tenant
       |
       +-- Có tenant explicit và đã authorize?
       |       |
       |       +-- Có -> Session.withOptions().tenantIdentifier(id)
       |
       +-- Không -> Có trusted tenant context?
               |
               +-- Không -> Fail closed
               |
               +-- Có -> CurrentTenantIdentifierResolver
                           |
                           v
                    Hibernate Session tenant
                           |
           +---------------+----------------+
           |               |                |
       Database         Schema          Shared table
           |               |                |
       Connection       Schema mapper      @TenantId
       provider          / routing         discriminator
           |               |                |
           +---------------+----------------+
                           |
                      SQL + auth +
                    cache isolation

## 42. Bài tập tình huống

**1.** Resolver có trả JDBC Connection? **Không**, nó trả tenant ID.

**2.** Có cần gọi resolver trước mọi SELECT? **Không**, chủ yếu khi cần xác định tenant của Session.

**3.** `validateExistingCurrentSessions` xác minh user membership? **Không**, chỉ liên quan existing current Session tenant mismatch.

**4.** Có thể đổi tenant giữa một Session bằng ThreadLocal? **Không**.

**5.** Thiếu tenant context nên làm gì? **Fail closed**, không fallback tùy tiện.

**6.** Database-per-tenant cần SPI nào? **MultiTenantConnectionProvider**.

**7.** Hibernate 7.2 schema-based có SPI nào? **TenantSchemaMapper**, xuất hiện từ 7.1.

**8.** Hibernate 6.6 có `TenantSchemaMapper` không? **Không**.

**9.** Shared-table đánh dấu tenant column bằng gì? **@TenantId**.

**10.** Chỉ có field tên tenantId mà không annotation/policy có đủ không? **Không**.

**11.** Native SQL được tự thêm WHERE tenant? **Không** trong discriminator mode.

**12.** `isRoot` có nên bật cho admin của tenant-a? **Không** nếu chỉ là admin trong một tenant.

**13.** Spring TenantContext nên đặt trước hay sau `@Transactional`? **Trước khi Session/transaction được tạo**.

**14.** ThreadLocal tự đi qua CompletableFuture? **Không được bảo đảm**.

**15.** L2/app cache có thể bị trộn khi IDs giống nhau? **Có**, nếu cache key thiếu tenant.

**16.** Scheduler xử lý nhiều tenants có nên dùng một Session? **Không**, chia theo tenant.

**17.** Connection còn search_path tenant cũ phải sửa ở đâu? **Provider/schema routing/pool**.

**18.** Root có tự truy cập mọi database không? **Không**, connection routing vẫn riêng.

**19.** `HINT_TENANT_ID` dùng để làm gì? **Truyền tenant ID khi tạo EntityManager với Hibernate provider**.

**20.** Có nên dùng resolver như lớp bảo mật duy nhất không? **Không**, cần authorization và DB isolation.

## 43. Checklist triển khai

- Có canonical tenant ID/tenant directory đáng tin cậy.
- Authenticate và authorize tenant trước khi resolve.
- Không tin tenant header khi chưa kiểm tra membership.
- Resolver chỉ đọc trusted context, không làm DB query.
- Thiếu tenant fail closed; không fallback root.
- Sử dụng đúng generic type và Hibernate version.
- Bật current-session validation khi phù hợp.
- Một Session/transaction thuộc một tenant.
- Tenant context có trước Session creation.
- Dọn ThreadLocal kể cả exception.
- Async workers/schedulers có tenant explicit.
- Database mode có connection provider đúng.
- Schema mode có routing/mapper đúng version.
- Shared table có `@TenantId` và DB constraints phù hợp.
- Native SQL/JDBC được kiểm soát riêng.
- Root tenant được authorize và audit chặt.
- Connection pool reset schema/role state.
- L1/L2/application cache tenant-aware.
- Spring customizer áp dụng đúng EntityManagerFactory.
- OSIV không làm mở Session ngoài tenant scope.
- Test isolation, mismatch, cache, async và connection reuse.
- Monitor resolution failures và unauthorized access.

## 44. Tổng kết

**`CurrentTenantIdentifierResolver<T>` là callback để Hibernate biết tenant identifier hiện tại khi một Session cần xác định tenant.** Nó không phải một cơ chế multi-tenancy hoàn chỉnh.

Những điểm quan trọng:

1. `resolveCurrentTenantIdentifier()` trả tenant ID, không trả Connection.
2. `validateExistingCurrentSessions()` hỗ trợ phát hiện current-session tenant mismatch, không thay authorization.
3. `isRoot` là đặc quyền đặc biệt theo tính năng hỗ trợ, không dùng mặc định.
4. Tenant identity thuộc về Session; không switch giữa unit of work bằng ThreadLocal.
5. Có thể dùng `tenantIdentifier(id)` hoặc `HINT_TENANT_ID` để cấp tenant explicit khi tạo Session/EntityManager.
6. Có thể đăng ký resolver qua `hibernate.tenant_identifier_resolver`, `MultiTenancySettings` hoặc Spring customizer.
7. Database-per-tenant cần connection provider; schema-per-tenant cần routing; shared-table có `@TenantId`.
8. Hibernate 7.1+ có `TenantSchemaMapper`, khác với cách dùng SPI trên 6.6.
9. Native SQL không tự có tenant filter trong shared-table mode.
10. ThreadLocal, async, transactions, caches và connection pools cần bảo vệ tenant context.
11. Authorization luôn chạy **trước** khi resolver được cho phép trả tenant ID.

Một thiết kế đa tổ chức vững chắc phải trả lời: **Ai xác nhận tenant? Session mang tenant nào? Thành phần nào route database/schema? SQL nào cần tenant predicate? Cache và connection state được cô lập thế nào?** Resolver là mắt xích chuyển context ứng dụng thành tenant identity của Hibernate Session.

## Tài liệu tham khảo

- [Hibernate ORM 7.2 Javadocs — CurrentTenantIdentifierResolver](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/context/spi/CurrentTenantIdentifierResolver.html)
- [Hibernate ORM 6.6 Javadocs — CurrentTenantIdentifierResolver](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/context/spi/CurrentTenantIdentifierResolver.html)
- [Hibernate ORM 7.2 Introduction — Multi-tenancy](https://docs.hibernate.org/orm/7.2/introduction/html_single/)
- [Hibernate ORM 6.6 Introduction — Multi-tenancy](https://docs.hibernate.org/orm/6.6/introduction/html_single/)
- [Hibernate ORM 7.2 Javadocs — MultiTenancySettings](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/cfg/MultiTenancySettings.html)
- [Hibernate ORM 7.2 Javadocs — TenantSchemaMapper](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/context/spi/TenantSchemaMapper.html)
- [Hibernate ORM 7.2 Javadocs — MultiTenantConnectionProvider](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/engine/jdbc/connections/spi/MultiTenantConnectionProvider.html)
- [Hibernate ORM 7.2 Javadocs — @TenantId](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/annotations/TenantId.html)
- [Hibernate ORM 7.2 Javadocs — HibernateHints](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/jpa/HibernateHints.html)
- [Spring Boot 3.5 — HibernatePropertiesCustomizer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/orm/jpa/HibernatePropertiesCustomizer.html)
- [Spring Boot 4 — HibernatePropertiesCustomizer](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/hibernate/autoconfigure/HibernatePropertiesCustomizer.html)
