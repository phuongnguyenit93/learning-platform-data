# Giới hạn truy vấn theo người dùng hoặc tenant trong tầng dữ liệu

## Mục tiêu

Trong ứng dụng nhiều người dùng hoặc nhiều tenant, mọi truy vấn phải chỉ trả về dữ liệu mà principal hiện tại được phép xem hoặc thay đổi. Ví dụ, hai công ty cùng dùng một API quản lý Order nhưng không được nhìn thấy đơn hàng của nhau. Một người dùng trong công ty chỉ được truy cập những bản ghi thuộc tenant của mình và có thể còn bị giới hạn theo owner hoặc role.

Giới hạn dữ liệu phải được thực thi ở tầng truy vấn/persistence. Ẩn nút trên giao diện, kiểm tra tenant ở frontend hoặc chỉ lọc response sau khi đã tải toàn bộ dữ liệu đều không bảo vệ được dữ liệu. Client có thể gọi API trực tiếp, sửa ID, gửi query parameter khác hoặc truy cập một endpoint khác.

Các nguyên tắc chính:

- Xác định user và tenant từ danh tính đã xác thực ở server.
- Đưa điều kiện user/tenant vào mọi truy vấn đọc, cập nhật và xóa.
- Không tin tenant ID do client gửi trong path, query string hoặc JSON body.
- Kiểm soát cả collection, item, association, query method, count và pagination.
- Dùng database constraints và, khi phù hợp, row-level security làm lớp bảo vệ bổ sung.
- Kiểm thử trường hợp truy cập chéo tenant, không chỉ trường hợp hợp lệ.

## 1. Phân biệt authentication, authorization và data scoping

Ba khái niệm này giải quyết các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai đang gọi API? | User đăng nhập bằng OAuth2/JWT |
| Authorization | User có được phép thực hiện hành động này không? | Role ORDER_READ hoặc quyền quản lý |
| Data scoping | User được phép nhìn thấy những row nào? | Chỉ Order có tenant_id bằng tenant của user |

Một user có role `ORDER_READ` không có nghĩa user đó được đọc tất cả Order trong database. Role cho phép hành động; tenant/user predicate giới hạn tập dữ liệu mà hành động đó được phép tác động.

Ví dụ:

- User A thuộc tenant Alpha.
- User B thuộc tenant Beta.
- Cả hai đều có quyền đọc Order.
- Khi A gọi GET collection, chỉ Order của Alpha được trả về.
- Khi B gọi GET item với ID thuộc Alpha, server không được trả dữ liệu đó.

Không xem một ID khó đoán hoặc UUID là cơ chế phân quyền. Nếu biết hoặc đoán được ID của bản ghi tenant khác, client vẫn phải bị từ chối.

## 2. Lấy tenant từ danh tính đã xác thực

Tenant phải được suy ra từ authentication context hoặc một mapping đáng tin cậy trên server. Không lấy tenant làm nguồn sự thật từ request body hoặc query parameter.

Ví dụ JWT có claim tenant:

    {
      "sub": "user-100",
      "tenant_id": "tenant-alpha",
      "scope": "orders.read orders.write"
    }

Sau khi token được xác thực chữ ký, issuer, audience, thời hạn và các điều kiện bảo mật khác, ứng dụng có thể đọc claim tenant từ authenticated principal.

Nếu tenant không được đưa vào token, ứng dụng có thể tra cứu membership của user từ bảng UserTenant hoặc service identity nội bộ. Cần xác định rõ user có thể thuộc một hay nhiều tenant và tenant đang hoạt động được chọn theo quy tắc nào.

### 2.1. Tenant context ở server

Có thể định nghĩa abstraction để service lấy tenant hiện tại:

    public interface CurrentTenantProvider {
        UUID requireTenantId();
    }

Implementation có thể đọc claim từ Spring Security Authentication:

    @Component
    public class SecurityCurrentTenantProvider
            implements CurrentTenantProvider {

        @Override
        public UUID requireTenantId() {
            Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()) {
                throw new AccessDeniedException(
                    "Authenticated tenant is required"
                );
            }

            Object principal = authentication.getPrincipal();

            if (!(principal instanceof TenantPrincipal tenantPrincipal)) {
                throw new AccessDeniedException(
                    "Tenant context is unavailable"
                );
            }

            return tenantPrincipal.tenantId();
        }
    }

Đây là ví dụ minh họa. Kiểu principal và cách lấy claim phụ thuộc cấu hình Spring Security/OAuth2 của ứng dụng. Không cast trực tiếp sang một class cụ thể nếu ứng dụng đang dùng JwtAuthenticationToken hoặc principal type khác.

### 2.2. Không tin tenant ID từ client

Tránh thiết kế endpoint như:

    GET /orders?tenantId=tenant-alpha
    GET /tenants/tenant-alpha/orders

nếu server dùng giá trị client gửi làm căn cứ phân quyền. Client có thể thay tenant ID thành tenant khác.

Nếu API cần tenant trong URL để chọn context, server vẫn phải xác nhận authenticated user có membership và quyền sử dụng tenant đó. Tenant trong URL là một lựa chọn đầu vào cần kiểm tra, không phải bằng chứng quyền truy cập.

Tương tự, không nhận tenant_id từ JSON khi tạo hoặc cập nhật entity rồi lưu trực tiếp. Service nên gán tenant từ CurrentTenantProvider:

    order.setTenantId(currentTenant.requireTenantId());

Nếu tenant ID là field do server quản lý, không expose nó như field có thể được client ghi tự do.

### 2.3. Dọn context sau request

Nếu ứng dụng dùng ThreadLocal để lưu tenant context, phải đặt và xóa context trong cùng một request boundary, kể cả khi exception xảy ra. Thread trong servlet container được tái sử dụng; context còn sót có thể khiến request kế tiếp chạy dưới tenant sai.

Với async processing, scheduled job hoặc message consumer, không giả định SecurityContext/ThreadLocal tự truyền sang thread khác. Hãy truyền tenant một cách tường minh trong job/message đã được xác thực và thiết lập context trong phạm vi xử lý tương ứng.

## 3. Đưa tenant predicate vào repository query

Ví dụ entity Order có tenant ID:

    @Entity
    @Table(name = "orders")
    public class Order {

        @Id
        @GeneratedValue
        private UUID id;

        @Column(name = "tenant_id", nullable = false)
        private UUID tenantId;

        private String status;
        private Instant createdAt;
    }

Repository cung cấp các method luôn nhận tenant:

    public interface OrderRepository
            extends JpaRepository<Order, UUID> {

        Page<Order> findAllByTenantId(
            UUID tenantId,
            Pageable pageable
        );

        Optional<Order> findByIdAndTenantId(
            UUID id,
            UUID tenantId
        );

        boolean existsByIdAndTenantId(
            UUID id,
            UUID tenantId
        );

        long countByTenantId(UUID tenantId);
    }

Service lấy tenant từ authenticated context rồi gọi method scoped:

    @Service
    public class OrderService {

        private final OrderRepository orders;
        private final CurrentTenantProvider currentTenant;

        public OrderService(
                OrderRepository orders,
                CurrentTenantProvider currentTenant) {
            this.orders = orders;
            this.currentTenant = currentTenant;
        }

        @Transactional(readOnly = true)
        public Page<Order> list(Pageable pageable) {
            UUID tenantId = currentTenant.requireTenantId();
            return orders.findAllByTenantId(tenantId, pageable);
        }

        @Transactional(readOnly = true)
        public Order get(UUID id) {
            UUID tenantId = currentTenant.requireTenantId();

            return orders.findByIdAndTenantId(id, tenantId)
                .orElseThrow(OrderNotFoundException::new);
        }
    }

Điều kiện tenant được áp dụng ngay trong SQL do Spring Data JPA tạo. Database chỉ trả những row phù hợp; ứng dụng không cần tải dữ liệu tenant khác rồi lọc sau đó.

### 3.1. Item lookup phải có tenant predicate

Một lỗi phổ biến là collection đã được lọc nhưng item lookup vẫn dùng:

    orders.findById(id);

Nếu ID thuộc tenant khác, method này có thể trả entity ngoài phạm vi được phép. Dùng:

    orders.findByIdAndTenantId(id, tenantId);

Cùng nguyên tắc áp dụng cho:

- existsById.
- update và save.
- deleteById.
- association lookup.
- query method tìm theo business key.
- custom repository implementation.
- export, download và bulk operation.

Đối với item không tồn tại và item thuộc tenant khác, API thường nên trả cùng một contract, ví dụ 404, để tránh tiết lộ sự tồn tại của dữ liệu tenant khác. Quy tắc status cụ thể phải nhất quán với API.

### 3.2. Cập nhật và xóa phải scoped

Không tải entity chỉ bằng ID rồi tin rằng client có quyền sửa. Service nên tìm entity trong tenant hiện tại trước:

    @Transactional
    public Order changeStatus(UUID id, String status) {
        UUID tenantId = currentTenant.requireTenantId();

        Order order = orders.findByIdAndTenantId(id, tenantId)
            .orElseThrow(OrderNotFoundException::new);

        order.setStatus(status);
        return orders.save(order);
    }

Xóa cũng phải kiểm tra scope:

    @Transactional
    public void delete(UUID id) {
        UUID tenantId = currentTenant.requireTenantId();

        Order order = orders.findByIdAndTenantId(id, tenantId)
            .orElseThrow(OrderNotFoundException::new);

        orders.delete(order);
    }

Một câu lệnh delete trực tiếp có thể dùng derived delete query scoped nếu phù hợp, nhưng cần chú ý lifecycle callbacks, entity events và semantics của bulk delete. Không dùng deleteById(id) không có tenant predicate cho request từ client.

## 4. Phân trang, count và sort cũng phải nằm trong scope

Một collection endpoint có thể trả đúng các row nhưng vẫn rò rỉ thông tin nếu count query không được lọc. Ví dụ page content chỉ chứa Order của Alpha nhưng totalElements lại đếm cả Alpha và Beta.

Mọi phần của Page phải dùng cùng tenant predicate:

- Nội dung page.
- Count query.
- Tổng số trang.
- Aggregation và summary.
- Facet hoặc thống kê filter.
- Export và báo cáo.

Derived method như `findAllByTenantId(tenantId, pageable)` thường để Spring Data xây dựng cả page query và count query với predicate tương ứng.

Nếu dùng custom `@Query`, phải áp dụng điều kiện tenant cho cả query chính và countQuery khi khai báo riêng:

    @Query(
        value = """
            select o from Order o
            where o.tenantId = :tenantId
              and o.status = :status
            """,
        countQuery = """
            select count(o) from Order o
            where o.tenantId = :tenantId
              and o.status = :status
            """
    )
    Page<Order> findByTenantAndStatus(
        UUID tenantId,
        String status,
        Pageable pageable
    );

Đây là ví dụ JPQL. Điều kiện tenant không được bỏ sót trong count query.

Sort do client yêu cầu cần được giới hạn vào property hợp lệ và phù hợp với API. Sort không thay thế tenant predicate. Nếu client gửi sort theo field nhạy cảm hoặc tốn kém, có thể áp dụng allowlist ở service/controller trước khi tạo Pageable.

## 5. Kết hợp tenant scope với bộ lọc nghiệp vụ

Client có thể gửi các filter như status, ngày tạo hoặc loại Order. Các filter đó phải được kết hợp với tenant predicate bằng AND.

Ví dụ logic:

    tenant_id = currentTenant
    AND status = requestedStatus
    AND created_at >= requestedStart

Tenant predicate phải luôn có mặt, kể cả khi client không gửi filter nào.

Với Spring Data JPA Specification:

    public static Specification<Order> belongsToTenant(
            UUID tenantId) {
        return (root, query, builder) ->
            builder.equal(root.get("tenantId"), tenantId);
    }

    public static Specification<Order> hasStatus(String status) {
        return (root, query, builder) ->
            builder.equal(root.get("status"), status);
    }

Service kết hợp các specification:

    Specification<Order> specification =
        Specification.where(belongsToTenant(tenantId))
            .and(hasStatus(status));

    return orders.findAll(specification, pageable);

Ví dụ này giả định repository hỗ trợ JpaSpecificationExecutor. Nếu filter optional, chỉ thêm specification tương ứng khi có giá trị; không được bỏ specification tenant trong bất kỳ nhánh nào.

Không nhận một Specification tùy ý do client tạo trực tiếp. API nên parse filter được cho phép, sau đó service luôn kết hợp điều kiện bảo mật vào query.

## 6. Spring Data REST: các endpoint mặc định cần chú ý

Spring Data REST có thể tự export repository thành REST resources. Đây là điểm cần chú ý trong ứng dụng multi-tenant: các method CRUD mặc định như `findAll(Pageable)`, `findById(id)`, `save(entity)` hoặc `deleteById(id)` không tự biết tenant hiện tại chỉ vì entity có field `tenantId`.

Thêm một method `findAllByTenantId(...)` không tự động thay thế mọi endpoint CRUD mặc định. Nếu collection exporter vẫn gọi method `findAll(Pageable)` không scoped, endpoint có thể trả dữ liệu của nhiều tenant.

### 6.1. Không chỉ bảo vệ query method search

Ví dụ repository có:

    Page<Order> findAllByTenantId(UUID tenantId, Pageable pageable);

Nếu method này được export thành search endpoint, client có thể gọi nó với tenant ID do client cung cấp nếu API để lộ tham số đó. Không để client tự chọn tenant rồi xem đó là cơ chế isolation.

Ngoài search endpoint, phải xem xét cả:

- GET collection mặc định.
- GET item mặc định.
- PUT/PATCH item.
- DELETE item.
- Association resources.
- Query methods.
- Projections và excerpts.
- Custom controller và export endpoint.

### 6.2. Các lựa chọn tích hợp an toàn

Có hai hướng phổ biến:

**Hướng A — Tắt repository export và dùng controller/service scoped**

Đánh dấu repository không export:

    @RepositoryRestResource(exported = false)
    public interface OrderRepository
            extends JpaRepository<Order, UUID> {
        // Tenant-scoped methods
    }

Sau đó tạo controller/service riêng. Controller lấy tenant từ CurrentTenantProvider và chỉ gọi các repository method đã scoped. Đây là cách rõ ràng khi cần kiểm soát chặt mọi endpoint.

**Hướng B — Giữ Spring Data REST nhưng ẩn các method không scoped**

Có thể dùng `@RestResource(exported = false)` trên các CRUD method không an toàn và cung cấp endpoint riêng gọi service/repository scoped. Cần kiểm tra tất cả method kế thừa có thể được exporter sử dụng, bao gồm collection, item, update và delete.

Ví dụ về ý định ẩn một method:

    @Override
    @RestResource(exported = false)
    Page<Order> findAll(Pageable pageable);

Ẩn riêng method này không đủ để bảo vệ toàn bộ repository. Phải xử lý các method không scoped còn lại và các đường association/query liên quan. Khi chưa chứng minh được mọi đường truy cập đều scoped, nên tắt export repository và dùng custom controller.

### 6.3. Method security không tự lọc collection

Spring Security có thể bảo vệ method bằng `@PreAuthorize`:

    @EnableMethodSecurity

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public Page<Order> list(Pageable pageable) {
        // Tenant-scoped repository query.
    }

Annotation này kiểm tra quyền gọi method. Nó không tự thêm `tenant_id = ...` vào SQL và không lọc page/count.

Tương tự, `@PostFilter` có thể lọc kết quả sau khi method chạy, nhưng thường không phù hợp để bảo vệ collection lớn hoặc Page: dữ liệu đã được tải trước, count/pagination có thể sai, và có thể phát sinh lộ dữ liệu qua các đường khác. Hãy áp dụng tenant predicate ngay trong repository/database query.

## 7. Kiểm soát quan hệ giữa các entity

Foreign key chỉ chứng minh row được tham chiếu tồn tại. Nó không nhất thiết chứng minh hai row thuộc cùng tenant.

Ví dụ Order thuộc tenant Alpha nhưng client cố gán Customer thuộc tenant Beta. Nếu foreign key chỉ tham chiếu `customer.id`, database vẫn có thể chấp nhận association đó.

Service cần kiểm tra cả hai entity thuộc cùng tenant:

    UUID tenantId = currentTenant.requireTenantId();

    Customer customer = customers
        .findByIdAndTenantId(customerId, tenantId)
        .orElseThrow(CustomerNotFoundException::new);

    Order order = new Order();
    order.setTenantId(tenantId);
    order.setCustomer(customer);

    orders.save(order);

Không deserialize một object association từ client rồi gán thẳng vào entity mà không xác minh ownership.

### 7.1. Composite foreign key để bảo vệ tenant boundary

Nếu cần database cũng bảo vệ quan hệ cùng tenant, có thể dùng composite key/constraint. Ví dụ:

    CREATE TABLE customer (
        tenant_id UUID NOT NULL,
        id UUID NOT NULL,
        PRIMARY KEY (tenant_id, id)
    );

    CREATE TABLE orders (
        tenant_id UUID NOT NULL,
        id UUID NOT NULL,
        customer_id UUID NOT NULL,
        PRIMARY KEY (tenant_id, id),
        CONSTRAINT fk_order_customer_same_tenant
            FOREIGN KEY (tenant_id, customer_id)
            REFERENCES customer (tenant_id, id)
    );

Foreign key này buộc Order và Customer có cùng tenant_id. Cấu trúc khóa thực tế phụ thuộc schema hiện tại và database; nếu ID vẫn là primary key riêng, có thể cần unique constraint trên `(tenant_id, id)` để làm đích tham chiếu.

Đây là lớp bảo vệ bổ sung cho những association mà nghiệp vụ yêu cầu cùng tenant. Vẫn cần kiểm tra authorization và tenant ở service để trả lỗi rõ ràng.

## 8. Unique constraint và business key theo tenant

Trong multi-tenant system, một mã có thể duy nhất trong tenant thay vì duy nhất toàn hệ thống.

Ví dụ mỗi tenant được dùng cùng external key:

    @Table(
        uniqueConstraints = @UniqueConstraint(
            name = "uk_order_tenant_external_key",
            columnNames = {"tenant_id", "external_key"}
        )
    )

Repository kiểm tra trùng phải dùng cả hai field:

    boolean existsByTenantIdAndExternalKey(
        UUID tenantId,
        String externalKey
    );

Không dùng `existsByExternalKey(...)` nếu nghiệp vụ cho phép hai tenant khác nhau có cùng key.

Unique constraint trong database vẫn cần thiết để chống race condition giữa hai request cùng tenant. Validator hoặc exists query chỉ giúp phát hiện sớm.

## 9. Row-level security ở database

Với database hỗ trợ row-level security, có thể thêm policy để database tự giới hạn row theo tenant. Đây là defense in depth khi ứng dụng có nhiều repository, custom query hoặc đường truy cập dữ liệu khác nhau.

Ví dụ PostgreSQL:

    ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

    CREATE POLICY orders_tenant_policy
    ON orders
    USING (
        tenant_id = current_setting('app.tenant_id')::uuid
    )
    WITH CHECK (
        tenant_id = current_setting('app.tenant_id')::uuid
    );

Ứng dụng phải thiết lập tenant context trong transaction trước khi chạy query:

    SELECT set_config('app.tenant_id', :tenantId, true);

Tham số cuối `true` làm cấu hình có hiệu lực trong transaction hiện tại. Cách thiết lập cụ thể phụ thuộc JDBC/JPA transaction manager và database.

Các điểm quan trọng khi dùng RLS:

- Dùng database role có quyền tối thiểu.
- Bảo đảm application set tenant context trước mọi query.
- Tenant context phải gắn với transaction/connection đang dùng.
- Không để giá trị tenant của request trước rò sang connection được pool tái sử dụng.
- Kiểm tra table owner, superuser và role có quyền BYPASSRLS; các role này có thể bỏ qua policy theo quy tắc PostgreSQL.
- Cân nhắc FORCE ROW LEVEL SECURITY nếu cần áp dụng policy cho table owner.
- Test cả query đọc, insert, update và delete.
- Không coi RLS là thay thế cho authorization ở ứng dụng.

RLS là tính năng đặc thù database. Cú pháp và semantics của PostgreSQL không thể dùng nguyên xi cho MySQL, SQL Server hoặc Oracle.

## 10. Hibernate filter và cơ chế multi-tenancy

Hibernate cung cấp các cơ chế riêng như discriminator-based multi-tenancy, `@TenantId` hoặc `@Filter` tùy phiên bản.

Các cơ chế này có thể tự động thêm điều kiện tenant trong một số truy vấn ORM, nhưng cần hiểu phạm vi:

- Hibernate `@TenantId` là tính năng provider-specific; không phải annotation JPA portable.
- Hibernate filter phải được khai báo và bật trong session theo đúng lifecycle.
- Một filter không được bật ở mọi đường xử lý có thể khiến query thiếu tenant predicate.
- Native SQL, JDBC trực tiếp, bulk operation hoặc công cụ ngoài Hibernate có thể không đi qua filter như truy vấn ORM thông thường.
- Cần kiểm tra cache, association loading và session lifecycle với cơ chế đã chọn.

Không trộn nhiều cơ chế tenant context mà không có quy tắc rõ ràng. Nếu dùng Hibernate multi-tenancy hoặc filter, hãy kiểm thử các đường truy cập thực tế và cân nhắc database RLS làm lớp phòng vệ bổ sung.

## 11. Cache, search và dữ liệu phụ

Ngay cả khi repository query đã scoped, các lớp phụ vẫn có thể gây rò rỉ dữ liệu:

- Cache key phải bao gồm tenant ID hoặc scope tương đương.
- Không dùng cache key chỉ dựa trên entity ID nếu ID không global unique.
- Search index cần lưu tenant metadata và filter bắt buộc theo tenant.
- Export file phải tạo từ query scoped và kiểm tra quyền download.
- Dashboard, count, aggregation và autocomplete phải giới hạn tenant.
- Event/message cần mang tenant context đã xác thực.
- Log và audit phải ghi tenant ID phù hợp nhưng không làm lộ dữ liệu nhạy cảm.

Nếu một cache hoặc search service dùng chung cho nhiều tenant, filter tenant phải được áp dụng ở mọi truy vấn và không được client tùy ý bỏ qua.

## 12. Kiểm thử tenant isolation

Kiểm thử phải chứng minh tenant A không đọc, sửa, xóa hoặc liên kết được dữ liệu của tenant B.

Chuẩn bị dữ liệu:

- Tenant Alpha có Order A1 và Customer AC1.
- Tenant Beta có Order B1 và Customer BC1.
- Hai user được xác thực lần lượt thuộc Alpha và Beta.

Các trường hợp cần kiểm tra:

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| Alpha GET collection | Chỉ thấy Order A1 |
| Beta GET collection | Chỉ thấy Order B1 |
| Alpha GET item B1 | Không trả dữ liệu của Beta |
| Alpha PATCH/PUT item B1 | Không thay đổi row của Beta |
| Alpha DELETE item B1 | Không xóa row của Beta |
| Alpha filter status/page/sort | Content và totalElements đều chỉ tính Alpha |
| Alpha tạo Order gắn Customer Beta | Bị từ chối |
| Client gửi tenantId=Beta trong body | Server bỏ qua hoặc từ chối; tenant được lấy từ auth context |
| Hai tenant dùng cùng external key | Được phép nếu unique scope là tenant + key |
| Hai request trong cùng tenant dùng cùng external key | Một request bị unique constraint từ chối |
| Cache/search/export | Không trả kết quả của tenant khác |
| Background job | Tenant context được thiết lập tường minh và không rò sang job khác |

Nên kiểm tra trực tiếp database sau các request bị từ chối để xác nhận không có side effect. Với pagination, kiểm tra cả nội dung và metadata count. Với RLS, test bằng đúng application database role, không chỉ bằng superuser hoặc table owner.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Collection đã lọc nhưng GET item vẫn lộ dữ liệu | Item lookup dùng findById không có tenant predicate |
| totalElements lớn hơn số row được phép thấy | Count query thiếu điều kiện tenant |
| Client đổi tenantId và thấy dữ liệu tenant khác | Server tin tenant ID từ query/path/body |
| Search endpoint bỏ qua tenant | Query method nhận tenantId do client tự truyền |
| Method security có nhưng dữ liệu vẫn lộ | Authorization kiểm tra role nhưng query không scoped |
| @PostFilter làm pagination sai | Lọc sau khi đã tải page; count không được giới hạn |
| Order gắn Customer của tenant khác | Foreign key chỉ kiểm tra ID tồn tại, không kiểm tra cùng tenant |
| Duplicate key bị báo nhầm giữa tenant | Unique constraint chỉ trên business key, thiếu tenant_id |
| Cache trả entity tenant khác | Cache key hoặc cache lookup thiếu tenant scope |
| Background job dùng nhầm tenant trước | TenantContext/ThreadLocal không được thiết lập và dọn đúng |
| Hibernate filter đôi lúc không áp dụng | Filter không được bật trên mọi session hoặc có đường SQL bypass |
| Repository REST endpoint vẫn gọi findAll mặc định | Chưa ẩn/tắt method exporter không scoped |

## 14. Checklist triển khai

1. Xác định mô hình tenant: một user/một tenant hay user có nhiều tenant membership.
2. Lấy tenant từ authenticated principal hoặc membership đã xác thực.
3. Không tin tenant ID từ client làm căn cứ phân quyền.
4. Tạo CurrentTenantProvider hoặc abstraction tương đương ở server.
5. Đưa tenant predicate vào mọi repository query đọc, count, update và delete.
6. Dùng findByIdAndTenantId thay cho findById không scoped trong luồng người dùng.
7. Kết hợp tenant predicate với mọi filter, sort, pagination và aggregation.
8. Kiểm tra Spring Data REST CRUD exporter không để lộ method mặc định không scoped.
9. Dùng custom controller/service hoặc ẩn các endpoint không thể bảo đảm tenant scope.
10. Kiểm tra association ownership và cân nhắc composite foreign key cùng tenant.
11. Tạo unique constraint theo phạm vi tenant khi business key chỉ cần duy nhất trong tenant.
12. Cân nhắc RLS hoặc Hibernate multi-tenancy như lớp bảo vệ bổ sung.
13. Đưa tenant vào cache key, search filter, export và background job context.
14. Kiểm thử đọc, cập nhật, xóa, count, association và truy cập chéo tenant.
15. Kiểm tra database bằng application role thực tế, không chỉ bằng quyền quản trị.

## Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA — Query methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Hibernate ORM — Multi-tenancy](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#multitenacy)
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
