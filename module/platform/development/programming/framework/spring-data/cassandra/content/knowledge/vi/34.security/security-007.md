# Tenant trong khóa và phòng tránh truy cập chéo dữ liệu

Trong ứng dụng **Spring Data Cassandra** đa tenant (*multi-tenant*), một lỗi nghiêm trọng là người dùng tenant A đọc, thay đổi hoặc xóa dữ liệu của tenant B chỉ vì biết một định danh bản ghi. Lỗi này thường thuộc nhóm **Broken Object Level Authorization (BOLA/IDOR)**: backend nhận `orderId` do client gửi và truy vấn dữ liệu mà không ràng buộc bản ghi với tenant của người gọi.

**Đưa `tenant_id` vào khóa chính Cassandra là biện pháp thiết kế dữ liệu quan trọng, nhưng bản thân partition key không phải cơ chế phân quyền.** Cần kết hợp thiết kế bảng theo truy vấn, truy xuất tenant từ ngữ cảnh xác thực đáng tin cậy, kiểm tra quyền trên tầng ứng dụng, bảo vệ mọi đường đọc/ghi và kiểm thử dữ liệu thực.

Bài thuộc chương **Bảo mật** của module **SPRING_DATA_CASSANDRA**. Nội dung kết nối entity mapping, `CassandraRepository`, `CassandraTemplate`, Java Driver/CQL với partition key, tính nhất quán, paging, hiệu năng và quản trị dữ liệu trong hệ Cassandra phân tán.

## 1. Phân biệt định vị dữ liệu và quyết định quyền truy cập

Xét API:

```http
GET /api/orders/7b8d09fd-42bd-4e60-a3d7-91d5fc1b48d3
Authorization: Bearer <access-token>
```

Giả sử access token hợp lệ cho tenant A; `orderId` thuộc tenant B. Nếu backend chỉ dùng `orderId` để tìm bản ghi, việc token hợp lệ **không bảo đảm người gọi được quyền với đơn hàng đó**.

Một luồng an toàn cần có hai bước tách biệt:

1. **Xác thực và xác định tenant được phép truy cập:** kiểm tra token/session, lấy tenant từ claim hoặc mapping đã được kiểm chứng, kiểm tra membership nếu người dùng thuộc nhiều tenant.
2. **Phạm vi truy vấn và hành động được giới hạn theo tenant:** ghép tenant hợp lệ vào key/CQL của mọi thao tác, kiểm soát quyền hành động (`read`, `create`, `update`, `delete`) trên tài nguyên.

```text
Client request + credential
            |
            v
Authentication: xác minh token / session
            |
            v
Authorization: actor có quyền trên tenant này?
            |
            v
Trusted tenant context
            |
            v
Service: tenantId + resourceId / bộ lọc
            |
            v
Repository / CassandraTemplate / CqlSession
            |
            v
CQL WHERE đầy đủ partition key + điều kiện truy vấn hợp lệ
            |
            v
Chỉ dữ liệu trong tenant scope được phép
```

Một hàng không tìm thấy khi truy vấn bằng khóa `(tenant A, orderId của B)` thường là kết quả mong muốn. Tuy nhiên, **không được xem “không tìm thấy” là bằng chứng duy nhất của phân quyền**; vẫn phải xác minh cách tenant được chọn, quyền hành động và mọi đường truy xuất khác.

| Cơ chế | Giải quyết | Không tự giải quyết |
| --- | --- | --- |
| Partition key chứa tenant | Phân chia/định vị dữ liệu theo access pattern, giảm nguy cơ bỏ lọc tenant khi API được thiết kế đúng | Người gọi có được quyền chọn tenant nào? |
| Spring Security / identity provider | Xác thực actor, kiểm tra claim, vai trò và membership | Cassandra tự ràng buộc mọi query với tenant |
| Service/repository boundary | Buộc tenant hợp lệ vào mọi thao tác; từ chối truy cập trái phép | Ngăn mọi đoạn CQL chạy trực tiếp nếu có đường bypass |
| Cassandra RBAC | Phân quyền tài khoản database theo keyspace/table tùy cấu hình | Chính sách row-level tenant bên trong một bảng dùng chung |
| TLS, secret management, encryption at rest | Bảo vệ đường truyền, credential và dữ liệu lưu trữ | Sửa lỗi BOLA trong API |
| Kiểm thử đa tenant | Xác minh các đường đọc/ghi/xóa không vượt ranh giới | Thay thế kiểm soát truy cập lúc runtime |

**Điểm thiết kế cốt lõi:** tenant là thành phần của *security context* và *data access key*, không chỉ là cột thêm vào để báo cáo.

## 2. Chọn mô hình cô lập tenant phù hợp

Cassandra không buộc mọi hệ thống multi-tenant dùng một sơ đồ duy nhất. Có ba mô hình thường gặp:

| Mô hình | Đặc điểm | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Chung cluster, chung keyspace/bảng, mỗi hàng mang tenant | Partition key thường có `tenant_id` | Đơn giản để chia sẻ schema, quản lý nhiều tenant, tối ưu vận hành | Cần thực thi chặt tenant scoping ở ứng dụng; tenant nóng có thể gây lệch tải |
| Chung cluster, keyspace hoặc bảng riêng cho tenant | Dữ liệu tách ở cấp schema | RBAC/database objects dễ tách hơn, một số chính sách retention riêng | Schema/migration/metadata/connection và số lượng đối tượng tăng mạnh khi tenant nhiều |
| Cluster riêng cho một nhóm tenant | Cô lập hạ tầng và tài nguyên cao hơn | Linh hoạt về capacity, bảo trì và chính sách | Chi phí, vận hành, backup và nâng cấp lớn hơn |

Bài tập trung vào **bảng chung có tenant trong khóa**, mô hình phổ biến khi có nhiều tenant và cùng một access pattern. Với yêu cầu cách ly pháp lý, quy mô tenant rất lớn hoặc blast radius nghiêm ngặt, có thể cần keyspace/cluster riêng và đánh giá rủi ro riêng.

Không chọn một tenant làm partition key đơn lẻ cho *mọi* bảng. Cassandra cần thiết kế **theo truy vấn**: bảng tra chi tiết theo ID, bảng liệt kê theo tháng và bảng tra theo trạng thái có thể cần khóa phân vùng khác nhau, nhưng tất cả đều phải giữ tenant scope.

## 3. Hai bảng CQL cho hai access pattern khác nhau

Giả sử sản phẩm quản lý đơn hàng nhiều tenant cần:

- **Chi tiết:** đọc chính xác đơn theo `tenantId + orderId`.
- **Danh sách:** liệt kê các đơn trong một tháng, mới nhất trước, tối đa một số hàng/trang.

### 3.1. Bảng đọc chi tiết

```sql
CREATE TABLE orders_by_tenant_id (
    tenant_id  uuid,
    order_id   uuid,
    state      text,
    amount     decimal,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
```

Ở đây, toàn bộ tuple `(tenant_id, order_id)` là **composite partition key**. Mỗi cặp tenant/đơn được định vị như một partition; không có clustering column. Cùng một `order_id` có thể xuất hiện ở hai tenant nhưng vẫn là **hai khóa khác nhau**.

Truy vấn đúng:

```sql
SELECT tenant_id, order_id, state, amount, created_at
FROM orders_by_tenant_id
WHERE tenant_id = ?
  AND order_id = ?;
```

Mẫu truy vấn cần tránh trong ứng dụng dùng bảng này:

```sql
-- Thiếu tenant_id; không phải đường truy cập chuẩn của schema này.
SELECT *
FROM orders_by_tenant_id
WHERE order_id = ?;
```

Cassandra sẽ áp dụng quy tắc restriction của partition key; thiếu thành phần khóa thường khiến truy vấn không hợp lệ hoặc bị thúc đẩy sang cách lọc/quét tốn kém nếu thay schema/index. **Mục tiêu bảo mật không phải trông chờ Cassandra báo lỗi**, mà là thiết kế ứng dụng không bao giờ tạo truy vấn thiếu tenant scope.

### 3.2. Bảng đọc danh sách theo tháng

```sql
CREATE TABLE orders_by_tenant_month (
    tenant_id    uuid,
    month_bucket int,
    created_at   timestamp,
    order_id     uuid,
    state        text,
    amount       decimal,
    PRIMARY KEY (
        (tenant_id, month_bucket),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
```

Truy vấn:

```sql
SELECT order_id, created_at, state, amount
FROM orders_by_tenant_month
WHERE tenant_id = ?
  AND month_bucket = ?
  AND created_at <= ?
LIMIT ?;
```

Thiết kế này vừa giới hạn theo tenant vừa **bucket theo thời gian** để tránh một partition vô hạn khi tenant có nhiều đơn. `created_at` là clustering column cho truy vấn khoảng và thứ tự trong partition.

Không thể giả định “tenant đã ở trong khóa” thì có thể bỏ `month_bucket`: bảng có composite partition key `(tenant_id, month_bucket)`, nên câu truy vấn phải cung cấp đủ thành phần thích hợp. Query muốn trải nhiều tháng cần logic xác định các bucket, giới hạn số query và gộp kết quả đúng.

**Lưu ý an toàn vận hành:** dùng nhiều bảng theo access pattern có thể làm tăng số đường ghi. Một bản ghi đơn hàng có thể xuất hiện trong cả hai bảng; backend cần duy trì nhất quán nghiệp vụ giữa các bảng, xử lý ghi một phần và hiểu rằng Cassandra không tự biến tất cả các thao tác đa bảng thành transaction ACID kiểu cơ sở dữ liệu quan hệ.

## 4. Entity mapping: tenant nằm trong định danh của repository

Với bảng `orders_by_tenant_id`, khai báo Spring Data Cassandra theo một khóa tổng hợp. Ví dụ sau dùng Java 17+, Spring Data Cassandra 4.x; các import chuẩn được rút gọn để tập trung vào mapping.

```java
// TenantOrderKey.java
// Imports: java.io.Serializable, java.util.UUID, java.util.Objects;
// org.springframework.data.cassandra.core.mapping.*;

@PrimaryKeyClass
public class TenantOrderKey implements Serializable {

    @PrimaryKeyColumn(
            name = "tenant_id",
            ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
            name = "order_id",
            ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID orderId;

    public TenantOrderKey() {}

    public TenantOrderKey(UUID tenantId, UUID orderId) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.orderId = Objects.requireNonNull(orderId);
    }

    public UUID getTenantId() { return tenantId; }
    public UUID getOrderId() { return orderId; }

    public void setTenantId(UUID tenantId) { this.tenantId = tenantId; }
    public void setOrderId(UUID orderId) { this.orderId = orderId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof TenantOrderKey key)) return false;
        return Objects.equals(tenantId, key.tenantId)
                && Objects.equals(orderId, key.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, orderId);
    }
}
```

```java
// TenantOrder.java
// Imports: java.math.BigDecimal, java.time.Instant;
// org.springframework.data.cassandra.core.mapping.*;

@Table("orders_by_tenant_id")
public class TenantOrder {

    @PrimaryKey
    private TenantOrderKey key;

    @Column("state")
    private String state;

    @Column("amount")
    private BigDecimal amount;

    @Column("created_at")
    private Instant createdAt;

    public TenantOrder() {}

    public TenantOrder(
            TenantOrderKey key,
            String state,
            BigDecimal amount,
            Instant createdAt) {

        this.key = key;
        this.state = state;
        this.amount = amount;
        this.createdAt = createdAt;
    }

    public TenantOrderKey getKey() { return key; }
    public String getState() { return state; }
    public BigDecimal getAmount() { return amount; }
    public Instant getCreatedAt() { return createdAt; }

    // Bổ sung setters (hoặc constructor mapping thích hợp)
    // cho mọi trường theo cấu hình Spring Data đang dùng.
}
```

Repository:

```java
public interface TenantOrderRepository
        extends CassandraRepository<TenantOrder, TenantOrderKey> {
}
```

Phương thức `findById` nay yêu cầu **`TenantOrderKey`**, giúp code dễ nhận ra khóa tenant là một phần không thể thiếu của truy cập chi tiết:

```java
repository.findById(new TenantOrderKey(trustedTenantId, orderId));
```

Đây là **thiết kế API giúp giảm lỗi**, chưa phải ranh giới bảo mật hoàn chỉnh. Nếu caller có thể tự đưa `tenantId` tùy ý, nó vẫn truy cập được bản ghi tương ứng. Khóa đúng chỉ hữu ích khi `trustedTenantId` thực sự xuất phát từ ngữ cảnh đã được ủy quyền.

### Tránh nhầm lẫn giữa partition key và clustering key

Hai định nghĩa sau **không tương đương**:

```sql
-- Cả tenant_id và order_id thuộc một partition key tổng hợp
PRIMARY KEY ((tenant_id, order_id))

-- tenant_id là partition key; order_id là clustering column
PRIMARY KEY (tenant_id, order_id)
```

Cấu trúc thứ hai gom toàn bộ đơn của tenant vào một partition, có thể tạo partition rất lớn khi tenant tăng trưởng. Vì vậy, ngoài bảo mật, thiết kế khóa phải xét **partition size, hotspot, giới hạn thời gian và truy vấn cần phục vụ**. Việc tenant nằm trong một phần khóa không tự động giải quyết cân bằng tải.

## 5. Nguồn tenant đáng tin cậy nằm ở đâu?

Một API thường nhận `orderId` từ URL hoặc body; nhưng **không nên tin `tenantId` do client tự tuyên bố**, chẳng hạn header `X-Tenant-Id`, query parameter `?tenantId=...` hoặc body `{"tenantId":"..."}`, trừ khi giá trị ấy đã được đối chiếu với quyền của actor.

Nguồn tenant tin cậy có thể là:

1. Claim trong access token **đã được xác minh chữ ký, issuer, audience, thời hạn và các điều kiện bảo mật cần thiết**.
2. Session phía server gắn với actor đã đăng nhập, tra membership trong dữ liệu có thẩm quyền.
3. Context được một gateway tin cậy truyền tới qua kênh xác thực nội bộ và được backend kiểm chứng; không cho phép Internet gửi header tương tự trực tiếp.

**Không coi việc parse được JWT là đã xác thực token.** Việc xác minh token phải do cơ chế authentication được cấu hình đúng đảm nhiệm. Một claim `tenant_id` hợp lệ về cú pháp vẫn cần được đối chiếu với mô hình phân quyền thực tế khi người dùng có quyền trên nhiều tenant hoặc token có thể bị thu hồi theo chính sách.

### Tách nguồn tenant khỏi tham số API

Định nghĩa một cổng đọc tenant hiện hành:

```java
public interface CurrentTenant {
    UUID requiredTenantId();
}
```

Ví dụ adapter dùng Spring Security resource server và `JwtAuthenticationToken`:

```java
// JwtCurrentTenant.java — các import được rút gọn
@Component
public final class JwtCurrentTenant implements CurrentTenant {

    @Override
    public UUID requiredTenantId() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        if (!(auth instanceof JwtAuthenticationToken jwtAuth)
                || !auth.isAuthenticated()) {
            throw new AccessDeniedException(
                    "Yêu cầu ngữ cảnh xác thực hợp lệ");
        }

        String tenantClaim =
                jwtAuth.getToken().getClaimAsString("tenant_id");

        if (tenantClaim == null || tenantClaim.isBlank()) {
            throw new AccessDeniedException(
                    "Không có tenant đã được cấp quyền");
        }

        try {
            return UUID.fromString(tenantClaim);
        } catch (IllegalArgumentException ex) {
            throw new AccessDeniedException(
                    "Tenant claim không hợp lệ");
        }
    }
}
```

Ví dụ này giả sử **bộ lọc Spring Security đã xác minh access token** và hệ thống có quy tắc rằng claim `tenant_id` chỉ được identity provider tin cậy phát hành. Nó **không thay thế** cấu hình `oauth2ResourceServer(...).jwt(...)`, kiểm tra issuer/audience hoặc chính sách membership. Cần dùng phiên bản Spring Security và API tương ứng với dự án.

Đối với hệ thống cho phép người dùng đổi tenant trong một phiên, có thể nhận `selectedTenantId` trong URL/context nhưng phải kiểm tra:

```text
selectedTenantId ∈ allowedTenants(authenticatedActor)
                  AND actor có quyền hành động tương ứng
```

Chỉ sau khi xác minh membership và quyền mới tạo **trusted tenant context**. Nếu người dùng không có quyền trên tenant được chọn, yêu cầu phải bị từ chối trước khi thực thi CQL. Không copy ngẫu nhiên `tenantId` từ request vào `SecurityContext`.

### Bảo vệ context khi xử lý bất đồng bộ

`SecurityContextHolder` thường dùng thread-local trong ứng dụng servlet thông thường. Khi chuyển qua `@Async`, executor, callback, Reactor hoặc xử lý message nền, context không mặc định luôn đi theo luồng công việc. Cần dùng cơ chế truyền context được framework hỗ trợ hoặc một đối tượng **TenantScope đã được xác minh**, đồng thời giới hạn vòng đời của scope.

Không lưu `currentTenantId` trong một field thay đổi được của singleton repository/service: một request có thể ghi đè tenant của request khác, tạo lỗi rò rỉ dữ liệu khó tái hiện.

## 6. Service là ranh giới bắt buộc tenant scoping

Một service đọc/ghi chi tiết đơn hàng có thể chỉ nhận `orderId` và dữ liệu nghiệp vụ từ controller. Nó tự lấy tenant đã xác thực:

```java
// Ví dụ lớp service; lược bỏ import và exception mapping.
@Service
public final class TenantOrderService {

    private final TenantOrderRepository repository;
    private final CurrentTenant currentTenant;

    public TenantOrderService(
            TenantOrderRepository repository,
            CurrentTenant currentTenant) {

        this.repository = repository;
        this.currentTenant = currentTenant;
    }

    public OrderView get(UUID orderId) {
        UUID tenantId = currentTenant.requiredTenantId();

        TenantOrder row = repository.findById(
                new TenantOrderKey(tenantId, orderId))
                .orElseThrow(OrderNotFoundException::new);

        return new OrderView(
                row.getKey().getOrderId(),
                row.getState(),
                row.getAmount(),
                row.getCreatedAt());
    }

    public OrderView create(CreateOrderCommand command) {
        UUID tenantId = currentTenant.requiredTenantId();

        UUID orderId = UUID.randomUUID();
        TenantOrder row = new TenantOrder(
                new TenantOrderKey(tenantId, orderId),
                command.state(),
                command.amount(),
                Instant.now());

        repository.save(row);
        return new OrderView(
                orderId, row.getState(), row.getAmount(),
                row.getCreatedAt());
    }

    public void delete(UUID orderId) {
        UUID tenantId = currentTenant.requiredTenantId();
        repository.deleteById(new TenantOrderKey(tenantId, orderId));
    }
}

// DTO không có tenantId do client kiểm soát
public record CreateOrderCommand(String state, BigDecimal amount) {}
public record OrderView(
        UUID orderId, String state, BigDecimal amount, Instant createdAt) {}
```

**Đây là ví dụ tập trung vào tenant scoping:** mã sản xuất còn cần validation nghiệp vụ, kiểm tra role/quyền hành động và mapping lỗi phù hợp. Với nghiệp vụ cần biết đối tượng có tồn tại trước khi xóa, có thể đọc theo khóa đã scope trước; cần hiểu rằng kiểm tra rồi xóa không tự tạo tính nguyên tử khi có cập nhật đồng thời.

Controller chỉ chuyển ID của đơn hàng:

```java
@RestController
@RequestMapping("/api/orders")
public final class OrderController {

    private final TenantOrderService service;

    public OrderController(TenantOrderService service) {
        this.service = service;
    }

    @GetMapping("/{orderId}")
    public OrderView get(@PathVariable UUID orderId) {
        return service.get(orderId);
    }

    @PostMapping
    public OrderView create(@RequestBody CreateOrderCommand request) {
        return service.create(request);
    }

    @DeleteMapping("/{orderId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable UUID orderId) {
        service.delete(orderId);
    }
}
```

Nhờ cách này, các endpoint không có tham số “tenant tùy ý” để vô tình truyền xuống repository. Nhưng **vẫn phải bảo vệ quyền `create`/`delete`**. Ví dụ actor chỉ có quyền xem tenant A thì `requiredTenantId()` trả A vẫn chưa đủ để cho phép xóa; cần kiểm tra `OrderPermission.DELETE` trong authorization layer.

### Không trả thông tin giúp dò tài nguyên tenant khác

Khi tenant A hỏi `orderId` của tenant B, truy vấn khóa `(A, orderId)` không trả dữ liệu. Trả phản hồi nhất quán (thường là `404 Not Found` với resource nằm ngoài phạm vi) giúp tránh tiết lộ tồn tại của đối tượng tenant khác. Đối với hành động chọn một tenant mà actor không có membership, `403 Forbidden` thường phù hợp theo hợp đồng API.

Không phát lộ cho client thông tin “đơn hàng này có tồn tại nhưng thuộc tenant B” khi điều đó không thuộc quyền biết của actor. Logging nội bộ có thể lưu lý do chặn ở mức thích hợp, cần bảo vệ thông tin nhạy cảm và tuân thủ chính sách lưu vết.

## 7. Repository fragment, CassandraTemplate và Java Driver đều phải giữ tenant

Không chỉ `CassandraRepository.findById` mới cần bảo vệ. Cùng một codebase có thể có fragment tự viết, `@Query`, `CassandraTemplate`, `CqlSession` hoặc các tác vụ migration/consumer. Mọi đường đi đọc/ghi dữ liệu của tenant phải tuân theo cùng một hợp đồng scope.

### 7.1. Fragment với tham số tenant tường minh

```java
public interface TenantOrderLookupFragment {

    Optional<OrderView> findForTenant(
            UUID tenantId, UUID orderId);
}
```

Tên phương thức làm rõ key cần cả tenant và tài nguyên. **Không đưa fragment này trực tiếp lên controller**; service sẽ truyền `tenantId` từ `CurrentTenant` đã xác minh. Nếu codebase lớn có nguy cơ gọi fragment bằng tenant tùy ý từ nhiều nơi, có thể thay tham số UUID bằng một kiểu `AuthorizedTenantScope` được tạo ở authorization layer và hạn chế quyền tạo đối tượng ấy.

### 7.2. CQL bằng prepared statement

```java
// TenantOrderLookupFragmentImpl.java — lược bỏ import
public final class TenantOrderLookupFragmentImpl
        implements TenantOrderLookupFragment {

    private static final String READ_CQL = """
            SELECT order_id, state, amount, created_at
            FROM orders_by_tenant_id
            WHERE tenant_id = ?
              AND order_id = ?
            """;

    private final CqlSession session;
    private final PreparedStatement readStatement;

    public TenantOrderLookupFragmentImpl(CqlSession session) {
        this.session = session;
        this.readStatement = session.prepare(READ_CQL);
    }

    @Override
    public Optional<OrderView> findForTenant(
            UUID tenantId, UUID orderId) {

        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(orderId, "orderId");

        Row row = session.execute(
                readStatement.bind(tenantId, orderId)).one();

        if (row == null) return Optional.empty();

        return Optional.of(new OrderView(
                row.getUuid("order_id"),
                row.getString("state"),
                row.getBigDecimal("amount"),
                row.getInstant("created_at")));
    }
}
```

Câu CQL ràng buộc **đủ composite partition key** và tham số qua bind markers. Prepared statement giúp tránh lỗi nối chuỗi/injection từ giá trị; tuy nhiên **prepared statement không tự xác thực tenant**. Nếu service truyền tenant B cho actor A, truy vấn vẫn có thể trả dữ liệu B.

CQL thiếu tenant:

```sql
-- Không sử dụng làm API multi-tenant mặc định:
SELECT *
FROM orders_by_tenant_id
WHERE order_id = ?
ALLOW FILTERING;
```

`ALLOW FILTERING` không phải biện pháp bảo mật và có thể gây hiệu năng tệ. Nếu bài toán cần tìm mọi tenant theo `orderId` cho nghiệp vụ quản trị, phải thiết kế **một API quản trị được phân quyền riêng**, cùng bảng/access pattern thích hợp và audit đầy đủ; không mở rộng âm thầm quyền của endpoint tenant thông thường.

### 7.3. Sử dụng CassandraTemplate/Criteria

Với bảng danh sách theo tháng, fragment dùng `CassandraOperations` có thể nhận tenant đã xác minh rồi xây query:

```java
public List<TenantMonthOrder> recentForTenant(
        UUID tenantId, int monthBucket,
        Instant before, int limit) {

    if (tenantId == null || before == null
            || limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Tham số không hợp lệ");
    }

    Query query = Query
            .query(Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("month_bucket").is(monthBucket))
            .and(Criteria.where("created_at").lte(before))
            .limit(limit);

    return cassandraOperations.select(
            query, TenantMonthOrder.class);
}
```

Giả sử `TenantMonthOrder` đã mapping đúng `orders_by_tenant_month` và `cassandraOperations` là dependency được tiêm. Truy vấn cần kiểm thử thật trên Cassandra để xác nhận khóa và mapping đúng; mock `CassandraOperations` chỉ chứng minh lời gọi Java.

Một lỗi dễ phát sinh khi code tự xây query động:

```java
// Nguy hiểm: tenant filter là một lựa chọn tùy chọn
if (request.tenantId() != null) {
    query = query.and(
            Criteria.where("tenant_id").is(request.tenantId()));
}
```

Đối với dữ liệu yêu cầu tenant scoping, điều kiện tenant phải là **bắt buộc từ trusted context**, không phải tùy chọn do client bật/tắt. Cần tránh cả trường hợp caller truyền `null`, điều kiện bị bỏ qua, hoặc fallback chạy truy vấn rộng với vai trò database có quyền cao.

## 8. Các thao tác ghi, cập nhật và xóa cũng có thể vượt tenant

Nhiều đội kiểm tra kỹ SELECT nhưng bỏ qua UPDATE/DELETE. Trong Cassandra, thao tác write thường định vị hàng bằng **primary key đầy đủ** và có thể có **upsert semantics**. Một `save(entity)` với `tenantId` sai có nguy cơ ghi bản sao dữ liệu dưới khóa tenant khác, kể cả khi không đọc được bản ghi gốc.

### 8.1. Không tin khóa nằm trong request body

Đoạn sau là anti-pattern:

```java
// Không dùng: client kiểm soát cả tenantId và khóa ghi.
@PostMapping
public TenantOrder save(@RequestBody TenantOrder entity) {
    return repository.save(entity);
}
```

Thay bằng DTO chỉ chứa các trường mà người gọi được phép cung cấp; backend dựng `TenantOrderKey(trustedTenantId, generatedOrValidatedOrderId)`. Nếu endpoint cập nhật, lấy tenant từ context và ID từ path, **không cho client đổi `tenantId` hoặc khóa chính một cách gián tiếp**.

### 8.2. Update phải phân biệt tồn tại, quyền và upsert

Ví dụ CQL:

```sql
UPDATE orders_by_tenant_id
SET state = ?
WHERE tenant_id = ?
  AND order_id = ?;
```

Câu lệnh đã scope theo tenant, nhưng với Cassandra, write trên khóa chưa tồn tại có thể tạo trạng thái bản ghi mới (upsert). Nếu nghiệp vụ bắt buộc “chỉ cập nhật khi đơn đã tồn tại”, cân nhắc conditional update với `IF EXISTS`:

```sql
UPDATE orders_by_tenant_id
SET state = ?
WHERE tenant_id = ?
  AND order_id = ?
IF EXISTS;
```

`IF EXISTS` dùng cơ chế **lightweight transaction (LWT)**, mang chi phí và yêu cầu vận hành khác read/write thông thường. Nó **không thay thế authorization** và không nên dùng đại trà mà không đánh giá latency, concurrency và consistency. Có thể cần thêm điều kiện trạng thái nghiệp vụ, kiểm tra quyền và chiến lược xử lý tranh chấp.

### 8.3. Delete và background jobs

`DELETE` cũng phải ràng buộc khóa tenant. Tác vụ hết hạn, đồng bộ, import/export, message consumer hoặc job chạy lịch thường không có HTTP request principal; chúng cần **system tenant scope rõ ràng**, nguồn sự kiện/queue được xác thực, kiểm soát quyền và giới hạn các tenant được xử lý.

Không giả định job “chạy nội bộ” thì tự động được quyền truy cập mọi tenant. Nếu có tác vụ liên tenant thực sự (billing tổng hợp, bảo trì, tuân thủ), hãy tách quyền, đường thực thi, audit và truy vấn khỏi API tenant thông thường.

## 9. Phân trang, cache, search và export: các đường rò rỉ ít được để ý

### 9.1. Paging state không mang quyền truy cập

Với bảng `orders_by_tenant_month`, endpoint trả cursor cho trang tiếp theo. **Paging state của Cassandra chỉ mô tả tiến độ đọc**, không phải bằng chứng actor được quyền với tenant.

Khi nhận cursor:

1. Xác thực actor và xác định tenant scope hiện tại.
2. Xác minh cursor do server phát hành, chưa hết hạn, không bị chỉnh sửa.
3. Đối chiếu cursor với tenant, loại truy vấn, filter, bucket, sort và phiên bản API.
4. Chỉ sau đó xây lại truy vấn với tenant scope bắt buộc và paging state hợp lệ.

Một thiết kế thường dùng là token cursor có chữ ký/MAC hoặc tham chiếu opaque tới state được lưu trên server. Không cho client tùy ý thay tenant trong cursor, và không tin rằng paging state driver tự ngăn chuyển giữa tenant. Nếu user mất membership sau khi có cursor, request trang sau phải kiểm tra lại quyền.

Cassandra paging có giới hạn khi dữ liệu thay đổi đồng thời; **không mặc định cung cấp snapshot bất biến** qua nhiều trang. Bộ test phải nêu rõ cam kết của API về tính ổn định và trùng/lặp trong trường hợp có ghi/xóa.

### 9.2. Cache key phải chứa tenant

Một lỗi nguy hiểm:

```java
// Sai nếu orderId có thể trùng hoặc thuộc tenant khác
@Cacheable(cacheNames = "orders", key = "#orderId")
public OrderView get(UUID orderId) { ... }
```

Nếu cache dùng chung, tenant B có thể nhận object đã cache cho tenant A khi key trùng hoặc khi đường cache bỏ qua authorization. Có thể bọc cache ở method nhận trusted tenant rõ ràng:

```java
@Cacheable(
    cacheNames = "orders",
    key = "#tenantId.toString() + ':' + #orderId.toString()")
public OrderView loadScoped(UUID tenantId, UUID orderId) {
    // Chỉ gọi từ service đã xác minh tenantId.
    ...
}
```

Đảm bảo chính sách invalidation cập nhật đúng cache key khi sửa/xóa. Cache scoped vẫn không tự quyết định quyền: actor phải được kiểm tra trước khi đọc cache, kể cả khi data đã có sẵn.

### 9.3. Batch, report và tìm kiếm toàn văn

Bảng tìm kiếm theo `state` hoặc `event_type` thường được denormalize hoặc chuyển sang search engine. **Index/search engine cũng phải nhận và áp dụng tenant filter được xác minh**, không chỉ Cassandra table gốc. Report/export thường có nguy cơ lớn vì trả nhiều dữ liệu; cần tenant scope ở mọi truy vấn, giới hạn số bản ghi, streaming/paging an toàn và kiểm tra quyền tải xuống file xuất.

Nếu API `GET /orders/count` hoặc analytics tổng hợp quên điều kiện tenant, nó có thể lộ metadata/tổng lượng hoạt động của tenant khác ngay cả khi không lộ chi tiết từng đơn.

## 10. Role Cassandra, network và secret management

Bảo mật tầng ứng dụng và bảo mật database cần bổ trợ nhau.

- **Authentication/authorization của Cassandra:** cấu hình xác thực và RBAC theo phiên bản, tạo role riêng cho ứng dụng, chỉ cấp quyền keyspace/table cần thiết. Không dùng tài khoản superuser cho ứng dụng thường ngày.
- **Giới hạn network:** chỉ service/host được phép mới truy cập cluster; kiểm soát đường kết nối nội bộ.
- **Mã hóa truyền tải:** bật và xác minh TLS cho kết nối driver ↔ Cassandra theo chính sách, xác minh chứng chỉ, không bỏ kiểm tra certificate/hostname tùy tiện.
- **Credential/secrets:** dùng secret manager hoặc biến môi trường được quản lý, xoay vòng credential, không hard-code mật khẩu trong repository hay log.
- **Mã hóa dữ liệu lưu trữ:** chọn cơ chế phù hợp (storage/volume/managed platform và yêu cầu pháp lý), bảo vệ backup/snapshot và quyền truy cập tập tin.
- **Query/audit logging:** ghi các sự kiện từ chối quyền, thao tác nhạy cảm và correlation ID, nhưng tránh log raw token, credential, PII hoặc payload của khách hàng.

**Cassandra RBAC thông thường hoạt động ở cấp role/resource như keyspace/table, không tự áp đặt hàng rào tenant theo từng partition trong một bảng chung.** Nếu tất cả tenant dùng cùng tài khoản database và cùng bảng, trách nhiệm giới hạn tenant thuộc về các tầng ứng dụng/authorization và thiết kế API. Với yêu cầu người dùng kết nối trực tiếp CQL và được cách ly ở DB layer, cần phân tích một mô hình cô lập khác.

### Quy tắc cho hệ thống đa service

Một service gọi service khác có thể chuyển token end-user, sử dụng token trao đổi có phạm vi hạn chế hoặc một service identity được cấp quyền cụ thể. **Không chấp nhận “tenant_id” do service phía trước gửi như một chuỗi tự do** nếu backend không thể xác minh nguồn và quyền tương ứng. Mỗi hop phải có hợp đồng tin cậy, kiểm soát truy cập và dấu vết audit rõ ràng.

## 11. Tính nhất quán của bảng nhiều tenant có liên quan đến bảo mật

Cassandra là cơ sở dữ liệu phân tán; consistency level của read/write ảnh hưởng khả năng quan sát thay đổi gần đây. Tuy nhiên, **consistency không thay thế authorization**:

- `LOCAL_QUORUM` hoặc `LOCAL_ONE` quyết định số replica tham gia phản hồi trong local datacenter theo cấu hình; không quyết định actor có quyền đọc tenant nào.
- Đọc dữ liệu không cập nhật kịp có thể khiến service áp dụng quyết định cũ nếu membership/permission chỉ được lưu trong Cassandra rồi cache hoặc đọc ở consistency không phù hợp.
- Thu hồi quyền người dùng cần thiết kế riêng: token hết hạn, membership invalidation, cache TTL, phiên bản quyền hoặc kiểm tra trực tuyến tùy mức độ nhạy cảm.
- Denormalization đa bảng có thể tạm thời không đồng bộ. Vì vậy, đừng dựa vào một bản sao read model đang trễ làm nguồn duy nhất cho quyền truy cập nhạy cảm.

**Ví dụ:** người dùng vừa bị loại khỏi tenant A nhưng token cũ vẫn còn `tenant_id=A`. Nếu backend chỉ tin claim còn hiệu lực và chính sách yêu cầu thu hồi tức thời, người dùng vẫn có thể truy cập cho tới khi token hết hạn. Cần cơ chế thu hồi hoặc đối chiếu membership theo yêu cầu bảo mật; việc đưa tenant vào partition key không giải quyết tình huống này.

## 12. Kiểm thử thực tế với ít nhất hai tenant

Unit test mock repository kiểm tra service có dựng khóa đúng, nhưng không xác nhận entity mapping, CQL hay partition key trên Cassandra. Dùng **Cassandra thực/Testcontainers** cho integration test, đồng thời kiểm thử HTTP/Spring Security cho ranh giới xác thực.

### 12.1. Bộ dữ liệu thử chủ đích

Tạo hai tenant khác nhau, cố ý dùng **cùng `orderId`** để bắt lỗi thiếu scope:

| Bản ghi | tenant_id | order_id | state |
| --- | --- | --- | --- |
| A | `tenantA` | `sameOrderId` | `CREATED` |
| B | `tenantB` | `sameOrderId` | `CANCELLED` |
| A2 | `tenantA` | `anotherOrderId` | `PAID` |

Nếu repository truy vấn bằng khóa tenant đúng, tenant A nhìn thấy trạng thái `CREATED` cho `sameOrderId`, tenant B nhìn thấy `CANCELLED`. Nếu API trả cache theo mỗi `orderId` mà thiếu tenant, bộ test này dễ bắt lỗi.

Ví dụ phác thảo integration test (sau khi cấu hình schema, Spring Data repository thực và container Cassandra):

```java
@Test
void compositeKeyPhanBietHaiTenantCungOrderId() {
    UUID a = UUID.randomUUID();
    UUID b = UUID.randomUUID();
    UUID sameId = UUID.randomUUID();
    Instant now = Instant.parse("2026-11-25T00:00:00Z");

    repository.save(new TenantOrder(
            new TenantOrderKey(a, sameId),
            "CREATED", BigDecimal.TEN, now));

    repository.save(new TenantOrder(
            new TenantOrderKey(b, sameId),
            "CANCELLED", BigDecimal.ONE, now));

    TenantOrder fromA = repository.findById(
            new TenantOrderKey(a, sameId)).orElseThrow();
    TenantOrder fromB = repository.findById(
            new TenantOrderKey(b, sameId)).orElseThrow();

    assertEquals("CREATED", fromA.getState());
    assertEquals("CANCELLED", fromB.getState());
    assertNotEquals(fromA.getKey(), fromB.getKey());
}
```

Test này chứng minh **khóa và mapping trên Cassandra thực**; nó chưa chứng minh JWT/role đã được xác minh. Cần test riêng ở tầng service/API khi actor tenant A gửi ID của tenant B hoặc cố đổi header/body/cursor.

### 12.2. Ma trận kiểm thử chống truy cập chéo

| Tình huống | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Đọc đúng tenant | Token A, ID thuộc A | Đọc thành công khi actor có quyền `read` |
| Đọc ID tenant khác | Token A, ID chỉ thuộc B | Không trả dữ liệu B, không lộ B có bản ghi |
| Hai tenant trùng ID | Token A/B, cùng `orderId` | Mỗi tenant nhận bản ghi riêng của mình |
| Ghi với tenant giả mạo | Token A, body có `tenantId=B` | Từ chối field hoặc bỏ qua; bản ghi chỉ thuộc tenant A |
| Cập nhật/xóa tenant khác | Token A, ID thuộc B | Bản ghi B không đổi |
| Đổi tenant qua header/query | Token A, `X-Tenant-Id=B` | Không chuyển scope nếu actor chưa được ủy quyền |
| Tenant membership hết hiệu lực | Token/session cũ cho A | Quyết định theo chính sách thu hồi quyền đã định |
| Danh sách theo bucket | Token A, nhiều tháng và nhiều tenant | Không trộn hàng B trong mọi trang/bucket |
| Cursor đổi tenant | Cursor của A dùng từ B | Từ chối, không lộ dữ liệu A |
| Cache dùng chung | Hai tenant trùng ID | Cache không trả nhầm object |
| Export/report/search | Token A, truy vấn số lượng lớn | Chỉ dữ liệu A hoặc đúng tập quyền được cấp |
| Async/background job | Event có tenant và actor/service identity | Job chỉ truy cập tenant được phép, context không bị rò giữa task |

### 12.3. Unit test kiểm tra nguồn tenant

Với service dùng `CurrentTenant`, mock cả `repository` và `currentTenant` để xác nhận:

```java
@Test
void serviceLuonDungTenantDaXacThuc() {
    UUID trustedTenant = UUID.randomUUID();
    UUID orderId = UUID.randomUUID();

    CurrentTenant currentTenant = mock(CurrentTenant.class);
    TenantOrderRepository repository =
            mock(TenantOrderRepository.class);

    when(currentTenant.requiredTenantId()).thenReturn(trustedTenant);
    when(repository.findById(
            new TenantOrderKey(trustedTenant, orderId)))
            .thenReturn(Optional.empty());

    TenantOrderService service =
            new TenantOrderService(repository, currentTenant);

    assertThrows(OrderNotFoundException.class,
            () -> service.get(orderId));

    verify(repository).findById(
            new TenantOrderKey(trustedTenant, orderId));
}
```

Ví dụ giả sử `OrderNotFoundException` là exception ứng dụng đã định nghĩa. Nếu thiếu `equals/hashCode` trong `TenantOrderKey`, lời gọi `verify` với khóa mới có thể thất bại dù hai đối tượng mang cùng các trường: đây cũng là lý do khóa entity cần có equality đúng.

Test mock trên **không thay thế** test Spring Security: trong API test, cần mô phỏng token/role hợp lệ và không hợp lệ hoặc dùng cơ chế cấp token thử thực sự, kiểm tra security chain có validate issuer/audience và membership. Nếu test thay toàn bộ security filter bằng principal giả, nó chỉ chứng minh controller/service xử lý principal ấy.

## 13. Kịch bản tấn công và lỗi triển khai thường gặp

### Trường hợp 1 — IDOR qua findById

Một API lấy ID theo URL và đọc bảng có khóa chỉ gồm `order_id`, rồi trả bản ghi mà không xác minh tenant. Actor A đoán hoặc có được ID của B sẽ đọc được. **Khắc phục:** kiểm tra quyền tài nguyên và/hoặc thiết kế query luôn có tenant scope đáng tin cậy, kiểm thử BOLA.

### Trường hợp 2 — Tenant header tự do

Gateway gắn `X-Tenant-Id`, nhưng backend cũng cho Internet gửi header đó và dùng trực tiếp để lọc. Actor thay header là đổi phạm vi query. **Khắc phục:** chỉ lấy context qua cơ chế xác thực được backend tin cậy; ràng buộc mạng/gateway; đối chiếu actor membership.

### Trường hợp 3 — Danh sách có tenant filter nhưng detail thì không

`findRecentByTenantId(...)` an toàn nhưng `findByOrderId(...)` không có tenant. Tester chỉ kiểm tra màn danh sách nên bỏ qua endpoint chi tiết. **Khắc phục:** rà soát tất cả read path và mutation path, đánh dấu API tenant-scoped; viết kiểm thử cross-tenant cho từng route.

### Trường hợp 4 — Background job giữ tenant cũ

Service singleton lưu `currentTenantId` trong field thay đổi được; hai request đồng thời ghi đè nhau. **Khắc phục:** dùng request/security context phù hợp hoặc scope immutable cho từng tác vụ; không dùng mutable global tenant state.

### Trường hợp 5 — Cursor hoặc cache không gắn tenant

Trang 1 an toàn, nhưng API cho dùng paging state của tenant khác hoặc cache theo `orderId`. **Khắc phục:** cursor/cached data phải gắn tenant, bộ lọc và quyền đã xác minh; test trùng ID/cursor giữa hai tenant.

### Trường hợp 6 — Query phân quyền dựa vào bảng read model bị trễ

Membership vừa bị thu hồi nhưng bảng denormalized hoặc cache chưa đồng bộ. **Khắc phục:** coi quyền là nguồn quyết định có yêu cầu consistency và freshness riêng; dùng thời hạn token, kiểm tra cập nhật hoặc invalidation theo chính sách.

### Trường hợp 7 — Tin rằng Cassandra native user sẽ cách ly từng tenant

Ứng dụng dùng chung một database role được cấp `SELECT` bảng chứa mọi tenant. Actor B khai thác một API chạy CQL tùy ý hoặc service nội bộ quên scope sẽ chạm được dữ liệu khác. **Khắc phục:** giới hạn quyền chạy CQL, không cấp query-console đa tenant cho end user, dùng API có kiểm tra quyền; cân nhắc keyspace/cluster riêng khi yêu cầu DB-level isolation.

## 14. Checklist thiết kế và review bảo mật

- [ ] Mọi bảng dùng chung tenant có access pattern và partition key được thiết kế có chủ đích; tenant scope xuất hiện trong mọi đường đọc phù hợp.
- [ ] Tenant được lấy từ identity/session hoặc membership đáng tin cậy; request header/body/query không tự cấp quyền.
- [ ] Repository ID và custom CQL yêu cầu tenant, các fragment/Template/Driver không có đường query bỏ tenant scope.
- [ ] Tất cả **read, create, update, delete, count, search, export và background job** áp dụng cùng nguyên tắc tenant isolation.
- [ ] Có kiểm tra **quyền hành động** ngoài việc xác định tenant.
- [ ] Entity được dựng từ tenant backend cấp, không cho client đổi partition key.
- [ ] Cache key, paging cursor, message và file xuất đều ràng buộc tenant.
- [ ] Khi actor thuộc nhiều tenant, việc đổi tenant đòi hỏi kiểm tra membership/quyền; thu hồi quyền có chính sách freshness.
- [ ] Database role được cấp ít quyền nhất, TLS/secrets/backups/audit được quản lý.
- [ ] Test có **ít nhất hai tenant cùng order ID**, bao phủ chi tiết, danh sách, sửa/xóa, cache, cursor và các đường admin.
- [ ] Integration test chạy CQL/repository thực với Cassandra, API test kiểm tra authentication và authorization thực tế.
- [ ] Không xem `ALLOW FILTERING`, secondary index hay việc biết partition key là bằng chứng authorization.

## 15. Bài tập thực hành

**Bài 1 — Lỗi IDOR:** tạo endpoint chi tiết dùng `orderId`, viết test token tenant A truy cập ID của B. Sau đó sửa để dùng `TenantOrderKey(trustedTenant, orderId)` và thêm kiểm tra quyền hành động.

**Bài 2 — Bảng theo truy vấn:** với yêu cầu “20 đơn mới nhất trong 7 ngày” và “tra chi tiết bằng ID”, thiết kế ít nhất hai bảng Cassandra. Chỉ ra partition key, clustering key, truy vấn CQL phù hợp và cách bảo đảm tất cả bảng cùng mang tenant scope.

**Bài 3 — Viết fragment an toàn:** triển khai `TenantOrderLookupFragment` bằng `CqlSession` và bằng `CassandraOperations`. So sánh API có/không có tenant context; thêm unit test kiểm tra gọi đúng tenant và integration test kiểm tra dữ liệu thật.

**Bài 4 — Cursor và cache:** giả lập hai tenant có cùng `orderId` và hai cursor truy vấn khác nhau. Thiết kế định dạng cache key và cách kiểm tra cursor để không thể đọc chéo dữ liệu; kiểm tra khi token cũ mất membership.

**Bài 5 — Review hoạt động nền:** một job xuất CSV cho tenant và một consumer nhận sự kiện cập nhật đơn. Mô tả nguồn tenant được tin cậy ở mỗi luồng, kiểm tra quyền, cơ chế tránh rò context khi chạy đồng thời, và audit cần thiết.

**Ghi nhớ:** trong **Spring Data Cassandra**, đặt `tenant_id` vào partition key giúp định vị dữ liệu và làm tenant scope rõ ràng trong repository, entity và CQL. Nhưng **tenant isolation là thuộc tính của toàn bộ luồng xác thực → ủy quyền → truy vấn → cache/paging → ghi/xóa**, không phải hiệu ứng tự động của một cột khóa. Khi tenant luôn được xác minh và bắt buộc đi cùng mọi access pattern, ứng dụng giảm đáng kể nguy cơ truy cập chéo dữ liệu mà vẫn tuân theo cách thiết kế bảng, consistency và hiệu năng của Cassandra.
