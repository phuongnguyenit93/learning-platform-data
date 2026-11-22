# Cô lập tenant ở lớp định danh, dữ liệu và tài nguyên

Một ứng dụng serverless thường phục vụ nhiều tổ chức hoặc khách hàng trên cùng một hệ thống. Mỗi tổ chức được gọi là **tenant**. Các tenant có thể dùng chung API, function, database, queue và object storage, nhưng dữ liệu và thao tác của tenant này phải được tách khỏi tenant khác.

Cô lập tenant không chỉ là thêm cột tenant_id vào bảng. Hệ thống phải xác định đúng tenant từ danh tính đã xác thực, kiểm tra quyền trên từng tài nguyên, giữ tenant context xuyên suốt request và message, đồng thời áp dụng ranh giới phù hợp ở database, object storage, cache, queue, secret và hạ tầng mạng. Một lỗi nhỏ ở bất kỳ lớp nào cũng có thể dẫn đến cross-tenant data access.

Trong Java serverless, các execution environment được tái sử dụng và có thể xử lý nhiều request hoặc message theo cấu hình nền tảng. Vì vậy, tenant context phải gắn với từng invocation và từng công việc. Không được để biến static, thread hoặc connection pool làm rò trạng thái tenant giữa các lần xử lý.

Bài học trình bày cách thiết kế cô lập tenant theo nhiều lớp, từ identity và authorization đến dữ liệu, tài nguyên, vận hành và kiểm thử.

## 1. Tenant và ranh giới cô lập

Tenant là đơn vị sở hữu dữ liệu và quyền truy cập trong một ứng dụng multi-tenant. Tùy sản phẩm, tenant có thể là công ty, tổ chức, workspace, khách hàng doanh nghiệp hoặc tài khoản cá nhân.

Một người dùng có thể:

- Chỉ thuộc một tenant.
- Thuộc nhiều tenant với vai trò khác nhau.
- Là quản trị viên của tenant A nhưng chỉ là thành viên của tenant B.
- Được cấp quyền tạm thời vào tenant khác theo quy trình hỗ trợ.

Do đó, không thể suy ra tenant chỉ từ user ID hoặc email. Hệ thống cần một quan hệ membership rõ ràng giữa principal và tenant.

### Ranh giới cần bảo vệ

| Lớp | Câu hỏi cô lập |
|---|---|
| Identity | Ai đang gọi và họ thuộc tenant nào? |
| Authorization | Principal có quyền thực hiện hành động này trên tài nguyên của tenant không? |
| Application context | Tenant nào đang được xử lý trong invocation hiện tại? |
| Database | Query hoặc transaction có thể đọc/ghi dữ liệu tenant khác không? |
| Object storage | Tenant có thể tải hoặc ghi object của tenant khác không? |
| Queue/event | Message có thể được xử lý dưới tenant context sai không? |
| Cache/search | Key hoặc index có thể trả dữ liệu chéo tenant không? |
| Secrets/keys | Workload có thể đọc credential hoặc khóa của tenant khác không? |
| Compute/network | Một tenant có thể làm cạn tài nguyên hoặc tiếp cận dịch vụ nội bộ không? |
| Operations | Nhân viên, log, backup và công cụ quản trị có tuân thủ ranh giới tenant không? |

Cô lập phải được thiết kế xuyên suốt các lớp. Chỉ kiểm tra ở UI hoặc API gateway là chưa đủ vì worker, batch job, retry và internal API có thể đi vào cùng dữ liệu qua đường khác.

## 2. Mô hình cô lập: pool, bridge và silo

Có ba mô hình thường dùng. Một hệ thống thực tế có thể kết hợp chúng cho từng loại dữ liệu hoặc nhóm tenant.

| Mô hình | Cách tổ chức | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Pool | Nhiều tenant dùng chung database/schema/table và tài nguyên | Chi phí thấp, vận hành tập trung, dễ scale theo tổng tải | Yêu cầu kiểm soát tenant_id và policy rất chặt |
| Bridge | Một số tenant dùng chung một nhóm tài nguyên riêng, chia theo shard hoặc cell | Cân bằng chi phí và mức cô lập | Cần quản lý mapping tenant-to-cell và di chuyển tenant |
| Silo | Mỗi tenant hoặc nhóm tenant có database, bucket, account/project hoặc stack riêng | Ranh giới mạnh, dễ tùy biến quota và khóa | Chi phí và độ phức tạp vận hành cao |

### Pool

Pool phù hợp khi số lượng tenant lớn, kích thước mỗi tenant vừa phải và ứng dụng có schema tương đối đồng nhất. Các bảng dùng chung cần tenant key trong mọi truy vấn và ràng buộc dữ liệu.

### Bridge

Bridge chia tenant thành các cell hoặc shard. Mỗi cell có database, queue hoặc compute riêng cho một nhóm tenant. Khi một cell gặp sự cố hoặc quá tải, phạm vi ảnh hưởng được giới hạn hơn so với pool toàn hệ thống.

Cần có registry ánh xạ tenant đến cell và bảo đảm mọi service dùng cùng nguồn mapping. Khi chuyển tenant giữa cell, cần quy trình migration và cutover có kiểm soát.

### Silo

Silo phù hợp với tenant có yêu cầu compliance, encryption key, backup, network hoặc quota riêng. Silo không tự động an toàn nếu quyền IAM hoặc quy trình vận hành vẫn dùng chung quá rộng. Vẫn cần authorization và audit ở lớp ứng dụng.

Không có mô hình duy nhất tốt nhất. Quyết định dựa trên mức độ nhạy cảm dữ liệu, yêu cầu pháp lý, quy mô tenant, chi phí, khả năng vận hành và mức độ tùy biến.

## 3. Xác định tenant từ danh tính đã xác thực

Luồng an toàn bắt đầu bằng việc xác thực principal. Backend phải kiểm tra chữ ký, issuer, audience, thời hạn và các điều kiện token theo identity provider. Sau đó, ứng dụng xác định tenant membership từ nguồn dữ liệu tin cậy.

Một luồng điển hình:

1. HTTP function nhận bearer token hoặc identity token.
2. Middleware hoặc nền tảng xác thực token theo contract.
3. Ứng dụng lấy principal ID từ claim đã được xác minh, thường là cặp issuer và subject.
4. Membership service kiểm tra principal có thuộc tenant được yêu cầu và membership còn hoạt động không.
5. Authorization service xác định role và permission trong tenant đó.
6. Ứng dụng tạo tenant context bất biến cho request.
7. Mọi truy cập dữ liệu và tài nguyên dùng context này.

~~~mermaid
sequenceDiagram
    participant U as User/Client
    participant F as Java Function
    participant I as Identity Provider
    participant M as Membership/Authorization
    participant D as Tenant Data

    U->>F: Request + access token
    F->>I: Verify token / claims
    I-->>F: Verified issuer, subject, audience
    F->>M: Check membership and permissions
    M-->>F: Tenant and role context
    F->>F: Build immutable TenantContext
    F->>D: Query with tenant boundary
    D-->>F: Tenant-scoped result
    F-->>U: Response
~~~

Không lấy tenant ID từ một header như X-Tenant-Id rồi tin ngay. Header, query parameter, path parameter và message body đều do caller có thể kiểm soát. Chúng chỉ có thể dùng làm **tenant selector** sau khi backend xác minh principal có quyền vào tenant đó.

### User identity khác workload identity

Trong serverless có ít nhất hai loại danh tính:

- **User/client identity:** người hoặc ứng dụng đang yêu cầu thao tác nghiệp vụ.
- **Workload identity:** service account, execution role hoặc managed identity mà function dùng để gọi cloud services.

Workload identity cho phép function truy cập database, secret, queue hoặc object storage. Nó không chứng minh người dùng cuối có quyền đọc một bản ghi. Nếu function có quyền đọc dữ liệu của mọi tenant, code phải áp dụng tenant authorization đúng cho từng request.

Không dùng một service account có quyền rộng làm lý do bỏ qua kiểm tra user và tenant ở tầng ứng dụng.

## 4. Tenant selector và authorization

Một API có thể cho người dùng chọn workspace bằng URL:

~~~http
GET /tenants/tenant-42/orders/order-918
Authorization: Bearer <access-token>
~~~

Backend cần xác minh:

- Token hợp lệ và được phát hành cho API này.
- Principal có membership đang hoạt động trong tenant-42.
- Principal có permission đọc order.
- Order order-918 thực sự thuộc tenant-42.
- Tenant không bị suspended hoặc khóa theo chính sách.

Không đủ nếu chỉ kiểm tra người dùng thuộc tenant-42 rồi truy vấn order theo order ID mà bỏ tenant predicate. Nếu ID có thể đoán hoặc bị lộ, attacker có thể truy cập tài nguyên tenant khác.

Authorization nên gắn với tài nguyên và hành động, không chỉ với route. Ví dụ, quyền orders:read không tự động cho phép đọc mọi đơn hàng nếu dữ liệu còn có owner, region hoặc project boundary.

### Tránh IDOR và cross-tenant access

Insecure Direct Object Reference (IDOR) xảy ra khi API nhận object ID và không kiểm tra quyền truy cập. Trong multi-tenant, đây thường là lỗi cross-tenant.

Ví dụ query nguy hiểm:

~~~sql
SELECT * FROM orders WHERE order_id = ?;
~~~

Query có tenant boundary:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = ?
  AND order_id = ?;
~~~

Cần lấy tenant ID từ context đã được xác minh, không lấy từ trường do caller tự gửi mà chưa kiểm tra. Với update/delete, điều kiện tenant phải có trong câu lệnh thay đổi dữ liệu, không chỉ trong bước đọc trước đó.

## 5. TenantContext trong Java serverless

Sau khi xác thực và kiểm tra membership, tạo một object immutable chứa thông tin cần cho request:

~~~java
import java.util.Set;

public record TenantContext(
        String tenantId,
        String issuer,
        String subject,
        Set<String> permissions,
        String correlationId) {

    public TenantContext {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("principal is required");
        }
        permissions = Set.copyOf(permissions);
    }

    public void require(String permission) {
        if (!permissions.contains(permission)) {
            throw new SecurityException("Permission denied");
        }
    }
}
~~~

Truyền context rõ ràng qua các lớp:

~~~java
public OrderView getOrder(
        TenantContext tenant,
        String orderId) {

    tenant.require("orders:read");

    return orderRepository.findByTenantAndId(
            tenant.tenantId(),
            orderId);
}
~~~

Cách truyền explicit parameter giúp code dễ review và test. Các service không phải tự đọc một biến global có thể bị thay đổi bởi request khác.

### Vì sao không nên lưu tenant trong static field?

Một function instance có thể được tái sử dụng cho nhiều invocation. Nếu handler gán:

~~~java
static String currentTenantId;
~~~

thì request của tenant B có thể ghi đè giá trị trong lúc request của tenant A vẫn đang chạy, nhất là khi runtime hỗ trợ concurrency hoặc ứng dụng dùng thread/async task. Ngay cả khi invocation tuần tự, giá trị cũ có thể bị dùng nhầm nếu đường code quên cập nhật.

Không dùng static mutable field để lưu tenant, user, authorization result hoặc request-specific data.

### Thận trọng với ThreadLocal

ThreadLocal đôi khi được dùng để truyền security context trong framework. Trong thread pool, thread được tái sử dụng. Nếu không xóa context trong finally, request tiếp theo có thể nhìn thấy dữ liệu của tenant trước.

Với async/reactive execution, ThreadLocal cũng không tự truyền context qua thread khác. Ưu tiên truyền TenantContext tường minh hoặc dùng context propagation được framework hỗ trợ và kiểm tra cleanup ở mọi đường kết thúc.

## 6. Cô lập tenant trong database dùng chung

Với mô hình pool, nhiều tenant có thể dùng chung bảng. Mọi bảng chứa dữ liệu tenant cần có tenant key và mọi query cần giới hạn theo key đó.

Ví dụ schema:

~~~sql
CREATE TABLE orders (
    tenant_id  VARCHAR(64) NOT NULL,
    order_id   VARCHAR(64) NOT NULL,
    status     VARCHAR(32) NOT NULL,
    total      DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE INDEX idx_orders_tenant_created
    ON orders (tenant_id, created_at);
~~~

Composite primary key giúp định danh order trong phạm vi tenant. Index bắt đầu bằng tenant_id cũng hỗ trợ query tenant-scoped và có thể cải thiện hiệu năng.

Mẫu query:

~~~sql
SELECT order_id, status, total, created_at
FROM orders
WHERE tenant_id = ?
  AND order_id = ?;
~~~

Với foreign key, nên giữ tenant key trong quan hệ để ngăn liên kết chéo tenant:

~~~sql
CREATE TABLE order_items (
    tenant_id VARCHAR(64) NOT NULL,
    order_id  VARCHAR(64) NOT NULL,
    item_id   VARCHAR(64) NOT NULL,
    sku       VARCHAR(100) NOT NULL,
    quantity  INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, item_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders (tenant_id, order_id)
);
~~~

Ràng buộc ở database giúp ngăn một order item của tenant A tham chiếu đến order của tenant B do lỗi code.

### Repository phải yêu cầu tenant

Một pattern hữu ích là bắt buộc tenant ID trong chữ ký repository:

~~~java
public interface OrderRepository {
    OrderView findByTenantAndId(String tenantId, String orderId);

    int updateStatus(
            String tenantId,
            String orderId,
            String newStatus);
}
~~~

Tránh API repository chỉ nhận orderId nếu dữ liệu thuộc tenant. Khi viết update/delete, thêm tenant vào điều kiện:

~~~sql
UPDATE orders
SET status = ?
WHERE tenant_id = ?
  AND order_id = ?;
~~~

Kiểm tra số dòng bị ảnh hưởng để phân biệt không tìm thấy tài nguyên hoặc trạng thái không còn phù hợp theo contract. Không tiết lộ sự tồn tại của tài nguyên tenant khác qua thông báo lỗi khác biệt nếu điều đó tạo side channel.

## 7. Row-Level Security trong PostgreSQL

Row-Level Security (RLS) là lớp bảo vệ bổ sung ở database. PostgreSQL có thể áp dụng policy để giới hạn row mà database role được phép đọc hoặc ghi.

Ví dụ:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_orders
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

Ứng dụng đặt tenant context trong transaction trước khi truy vấn:

~~~sql
SELECT set_config('app.tenant_id', 'tenant-42', true);
~~~

Tham số thứ ba true làm setting chỉ có hiệu lực trong transaction hiện tại. Khi transaction kết thúc, giá trị được khôi phục. Điều này rất quan trọng khi connection được trả lại pool và dùng cho tenant khác.

Ví dụ Java với JDBC:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public List<Order> findOrders(
        DataSource dataSource,
        TenantContext tenant) throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement setTenant =
                    connection.prepareStatement(
                            "select set_config('app.tenant_id', ?, true)")) {
                setTenant.setString(1, tenant.tenantId());
                setTenant.execute();
            }

            List<Order> result = new ArrayList<>();

            try (PreparedStatement query =
                    connection.prepareStatement(
                            "select order_id, status, total "
                            + "from orders order by created_at desc")) {
                try (ResultSet rs = query.executeQuery()) {
                    while (rs.next()) {
                        result.add(new Order(
                                rs.getString("order_id"),
                                rs.getString("status"),
                                rs.getBigDecimal("total")));
                    }
                }
            }

            connection.commit();
            return result;
        } catch (SQLException | RuntimeException ex) {
            connection.rollback();
            throw ex;
        }
    }
}
~~~

Đoạn trích giả định lớp domain Order đã tồn tại trong ứng dụng. Phần quan trọng là set tenant context và chạy query trong cùng transaction; mọi đường thoát đều rollback khi có lỗi và đóng connection bằng try-with-resources.

Trong ví dụ, query không cần lặp lại tenant predicate vì RLS áp dụng policy ở database. Tuy nhiên, nhiều hệ thống vẫn giữ tenant predicate trong query để code thể hiện rõ phạm vi và hỗ trợ index. RLS là lớp defense-in-depth, không phải lý do để bỏ kiểm tra authorization.

Các lưu ý quan trọng:

- Role của ứng dụng không nên là table owner hoặc role có quyền bypass RLS.
- FORCE ROW LEVEL SECURITY giúp policy áp dụng cả với table owner trong những trường hợp phù hợp; superuser và role có BYPASSRLS vẫn có thể vượt qua.
- Nếu app.tenant_id chưa được thiết lập, policy cần deny thay vì mở rộng quyền.
- Tenant context phải được đặt trong cùng transaction với query.
- Rollback khi lỗi và đóng connection đúng cách.
- Không dùng session-level setting tồn tại sau khi trả connection về pool.
- Kiểm thử bằng đúng database role mà function production sử dụng.

Custom setting như app.tenant_id là context do ứng dụng cung cấp, không phải danh tính database độc lập. Nếu attacker có thể thực thi SQL tùy ý dưới role của ứng dụng, họ có thể thử thay đổi setting này. Vì vậy, RLS kiểu này là defense-in-depth cho lỗi query thiếu tenant predicate; nó không thay thế parameterized query, chống SQL injection, authorization ở ứng dụng và giới hạn quyền database role.

## 8. Schema hoặc database riêng cho tenant

Với yêu cầu cô lập cao hơn, có thể dùng schema riêng hoặc database riêng cho mỗi tenant.

### Schema-per-tenant

Mỗi tenant có schema riêng trong cùng database. Cách này tách namespace và có thể giúp quản lý migration theo tenant, nhưng vẫn chia sẻ database instance, quyền cấp cao và tài nguyên. Nếu ứng dụng ghép tên schema từ input, có thể tạo SQL injection hoặc truy cập nhầm schema.

Không ghép identifier trực tiếp từ request. Dùng tenant registry đã xác minh để ánh xạ sang schema name do hệ thống tạo, rồi kiểm tra identifier theo quy tắc cố định. Prepared statement không thể bind tên schema như một value thông thường.

### Database-per-tenant

Mỗi tenant có database riêng hoặc cluster riêng. Mức cô lập mạnh hơn về dữ liệu và có thể dùng credential, backup, quota riêng. Đổi lại, provisioning, migration, connection pool và monitoring phức tạp hơn.

Với số lượng tenant lớn, không nên tạo một pool connection vô hạn cho mọi database trong mọi execution environment. Cần cache pool có giới hạn, idle eviction và cơ chế đóng pool khi tenant không hoạt động.

### Chọn mức cô lập theo rủi ro

| Nhu cầu | Lựa chọn có thể cân nhắc |
|---|---|
| Nhiều tenant nhỏ, schema đồng nhất | Shared tables + tenant key + RLS |
| Tenant cần nhóm tài nguyên riêng | Cell/shard hoặc schema-per-tenant |
| Tenant regulated hoặc hợp đồng yêu cầu tách biệt | Database/account/project/bucket riêng |
| Tenant cần khóa mã hóa riêng | Per-tenant key hoặc encryption context riêng |
| Tenant có tải rất lớn | Dedicated cell hoặc silo để kiểm soát noisy neighbor |

## 9. Object storage và file theo tenant

Object key nên có tenant namespace do backend tạo:

~~~text
tenants/{tenantId}/documents/{documentId}
~~~

Tuy nhiên, prefix trong key không tự động là security boundary. Nếu runtime service account có quyền đọc toàn bucket, code vẫn có thể truy cập object của tenant khác nếu tạo sai key.

Các biện pháp:

- Lấy tenantId từ TenantContext đã xác minh.
- Tạo object key ở backend, không để client tự chọn key tùy ý.
- Kiểm tra tenant ownership trước khi cấp presigned URL.
- Giới hạn URL vào đúng bucket, object key, method và thời hạn.
- Không trả presigned GET cho object chưa được phép đọc.
- Dùng bucket/prefix policy hoặc access point phù hợp nếu cần ranh giới ở IAM.
- Mã hóa dữ liệu và cân nhắc key riêng cho tenant có yêu cầu cao.
- Kiểm soát metadata và filename; không đưa dữ liệu nhạy cảm vào object key.

Ví dụ API upload:

1. Client yêu cầu upload vào tenant hiện tại.
2. Backend kiểm tra quyền upload và quota.
3. Backend tạo documentId và object key.
4. Backend cấp presigned PUT chỉ cho key đó.
5. Client upload trực tiếp.
6. Backend xác minh object và lưu record có tenantId.
7. Worker xử lý file với cùng tenant context và kiểm tra ownership.

Với bucket dùng chung, cần bảo vệ cả đường upload, download, copy, delete và lifecycle cleanup. Một job cleanup chạy với quyền rộng vẫn có thể xóa nhầm object tenant khác nếu prefix hoặc registry bị lỗi.

## 10. Queue, event và tenant context

Message bất đồng bộ cần mang đủ thông tin để consumer biết tenant, nhưng message body không phải nguồn xác thực độc lập.

Ví dụ envelope:

~~~json
{
  "eventId": "evt-9182",
  "tenantId": "tenant-42",
  "eventType": "order.paid",
  "schemaVersion": 2,
  "aggregateId": "order-918",
  "occurredAt": "2026-11-17T10:20:00Z",
  "payload": {
    "paymentReference": "pay-774"
  }
}
~~~

Consumer nên:

1. Xác minh event đến từ queue/topic và producer được phép.
2. Validate schema và version.
3. Đối chiếu tenantId với record hoặc aggregate trong nguồn dữ liệu chuẩn.
4. Xác minh eventId chưa được xử lý hoặc dùng idempotency store.
5. Tạo TenantContext riêng cho message.
6. Truy vấn và cập nhật dữ liệu bằng tenant key.
7. Ghi kết quả và idempotency marker theo transaction phù hợp.

Không tin tenantId trong message chỉ vì queue được gọi là internal. Một producer bị xâm phạm hoặc bug có thể publish message mang tenantId sai.

### Queue riêng hay queue dùng chung?

Queue riêng cho mỗi tenant giúp giới hạn backlog và policy, nhưng tăng số lượng resource, mapping và chi phí quản lý. Queue dùng chung đơn giản hơn nhưng cần message-level tenant validation, fair scheduling, quota và cơ chế DLQ không làm lộ dữ liệu giữa tenant.

Mô hình bridge/cell có thể dùng một queue cho mỗi cell hoặc nhóm tenant. Chọn theo throughput, mức cô lập, khả năng vận hành và yêu cầu retention.

## 11. Cache, search index và khóa phân vùng

Cache là nơi dễ xảy ra rò rỉ cross-tenant nếu key không chứa tenant scope.

Key nguy hiểm:

~~~text
order:order-918
~~~

Key có tenant scope:

~~~text
tenant:tenant-42:order:order-918
~~~

Nếu cache chứa dữ liệu phụ thuộc user hoặc role, cần thêm chiều phù hợp hoặc cache theo permission-safe representation. Không chỉ dùng tenantId nếu hai người trong cùng tenant có quyền khác nhau.

Các hệ thống search cũng cần filter tenant ở server side. Không tin tenant filter do client gửi. Search index dùng chung cần có tenant field và query layer bắt buộc filter; với dữ liệu nhạy cảm, cân nhắc index hoặc collection riêng.

Các lưu ý:

- Namespace cache theo tenant và loại dữ liệu.
- Không để cache key bị collision giữa tenant.
- Áp dụng TTL và invalidation khi membership hoặc permission thay đổi.
- Không cache authorization decision lâu hơn chính sách cho phép.
- Kiểm tra mọi đường cache hit, không chỉ đường đọc database.
- Không ghi dữ liệu tenant vào cache global không có tenant dimension.

## 12. Encryption, secret và khóa riêng tenant

Mã hóa at rest ở cấp storage/database giúp bảo vệ dữ liệu khi lưu trữ, nhưng không tự động tạo ranh giới authorization. Nếu mọi tenant dùng cùng một key và cùng runtime identity, ứng dụng vẫn phải kiểm tra quyền truy cập.

Với tenant cần khóa riêng:

- Dùng KMS key riêng theo tenant hoặc envelope encryption với data key riêng.
- Ràng buộc encryption context với tenantId và resource ID nếu dịch vụ hỗ trợ.
- Cấp quyền decrypt theo tenant/cell khi kiến trúc cho phép.
- Không để caller tự đặt encryption context tùy ý mà không kiểm tra.
- Quản lý rotation, disable và deletion theo vòng đời tenant.
- Audit thao tác encrypt/decrypt và key policy.

Secret của tích hợp tenant (ví dụ API key riêng của tenant) nên được lưu trong secret manager, gắn với tenant registry và chỉ cho workload phù hợp đọc. Không đưa secret vào queue, log hoặc cache dùng chung nếu không có bảo vệ tương xứng.

Nếu runtime identity có thể đọc mọi secret tenant, ứng dụng cần một authorization layer chặt và audit. Với tenant yêu cầu cô lập mạnh, dùng workload identity hoặc resource policy riêng cho cell/tenant có thể giảm phạm vi truy cập.

## 13. Cô lập tài nguyên compute và chống noisy neighbor

Trong serverless, nhiều tenant có thể chia sẻ cùng function và execution environment. Một tenant có thể tạo tải lớn, message backlog hoặc request chậm khiến tenant khác bị ảnh hưởng. Đây là hiện tượng **noisy neighbor**.

Cần có quota theo tenant:

- Số request mỗi phút.
- Số job đang chạy.
- Tổng dung lượng upload.
- Số message được publish.
- Số lần gọi API đối tác.
- Số tài nguyên hoặc bản ghi được tạo.
- Giới hạn concurrency hoặc mức ưu tiên theo plan.

Không chỉ giới hạn ở API gateway. Worker cũng cần quota vì tenant có thể tạo backlog qua queue hoặc event.

### Kiểm soát ở các tầng

- API: rate limit theo tenant và principal.
- Queue: giới hạn publish, consumer concurrency và số job đang chờ.
- Worker: giới hạn số job đồng thời cho từng tenant/cell.
- Database: quota connection, query timeout và workload management nếu có.
- Object storage: quota dung lượng và số object.
- External API: rate limit riêng theo credential hoặc tenant.
- Compute: max instances, concurrency và queue-based buffering.

Nếu một tenant vượt quota, trả lỗi có thể xử lý được như 429 hoặc đưa công việc vào trạng thái throttled theo contract. Không để một tenant chiếm hết worker capacity hoặc database connection pool.

### Fair scheduling

Với queue dùng chung, FIFO đơn giản có thể khiến tenant có nhiều message chiếm đầu hàng đợi. Có thể dùng queue theo tenant/cell, scheduler có weighted fairness hoặc giới hạn số message mỗi tenant trong một batch. Thiết kế cần cân bằng độ trễ, thứ tự và chi phí.

## 14. Tenant context qua các service

Một request có thể đi qua API gateway, Java function, queue, worker và service khác. Tenant context cần được truyền theo một contract có xác minh.

Không nên chỉ forward một header X-Tenant-Id mà mọi service đều tin. Các lựa chọn:

- Truyền user token đã ký và để service đích xác minh issuer/audience.
- Dùng token nội bộ có claim tenant và audience cụ thể.
- Truyền event envelope có tenantId nhưng consumer đối chiếu producer và dữ liệu chuẩn.
- Dùng workload identity để xác thực service-to-service, đồng thời truyền user/tenant authorization context có chữ ký hoặc theo contract tin cậy.

Service đích cần xác định context nào là nguồn tin cậy và có quyền gì. Không để một service trung gian nâng quyền bằng cách tự đặt tenantId khác trong header.

### Không nhầm service identity với delegated user context

Một worker có thể được phép đọc database bằng workload identity. Điều đó không đồng nghĩa worker được phép xử lý mọi tenant. Nếu công việc được tạo thay mặt user, event nên giữ reference đến actor và tenant; consumer kiểm tra quyền hoặc trạng thái authorization theo chính sách nghiệp vụ khi xử lý.

Với tác vụ kéo dài, membership của user có thể bị thu hồi sau khi job được tạo. Hệ thống phải quyết định quyền được đánh giá tại thời điểm enqueue hay thời điểm execute. Quyết định này cần được ghi rõ trong contract và audit.

## 15. Provisioning, migration và offboarding tenant

Cô lập tenant không chỉ là xử lý request. Vòng đời tenant cần được quản lý:

### Provisioning

1. Tạo tenant ID bất biến và registry record.
2. Gán cell, database/schema, bucket/prefix và quota.
3. Tạo encryption key hoặc secret namespace nếu cần.
4. Thiết lập role/membership và owner đầu tiên.
5. Khởi tạo cấu hình và resource policy.
6. Chạy kiểm tra quyền truy cập trước khi cho tenant hoạt động.

### Migration giữa cell hoặc mô hình cô lập

- Xác định snapshot dữ liệu và write freeze/dual-write strategy.
- Giữ tenant mapping nhất quán giữa các service.
- Copy dữ liệu và xác minh row/object count, checksum.
- Chuyển routing tại một điểm cutover rõ ràng.
- Kiểm tra queue message cũ và event đến muộn.
- Có kế hoạch rollback và tránh hai cell cùng ghi dữ liệu chuẩn.

### Offboarding

- Thu hồi membership, token, API key và quyền truy cập.
- Ngừng nhận job mới và xử lý backlog theo chính sách.
- Xóa hoặc lưu trữ dữ liệu theo retention/legal hold.
- Thu hồi hoặc lên lịch xóa encryption key theo quy trình.
- Dọn object, cache, search index và secret liên quan.
- Giữ audit record phù hợp với chính sách.
- Xác minh tenant không còn truy cập được qua API, worker hoặc URL đã cấp trước đó.

Không xóa tenant record ngay khi bắt đầu offboarding nếu worker hoặc audit cần nó để hoàn tất quy trình. Dùng trạng thái lifecycle như ACTIVE, SUSPENDED, DEPROVISIONING và DELETED để điều phối.

## 16. Logging, metrics và audit theo tenant

Observability cần giúp điều tra sự cố mà không làm lộ dữ liệu.

Log có thể ghi:

- tenant ID nội bộ hoặc mã đã pseudonymize.
- principal ID đã chuẩn hóa.
- request/correlation ID.
- resource type và action.
- authorization decision.
- service, revision và region.
- policy version hoặc config version nếu liên quan.

Không ghi access token, secret, payload nhạy cảm hoặc toàn bộ dữ liệu khách hàng. Hạn chế đưa tenant ID làm label metric nếu số lượng tenant lớn vì cardinality có thể tăng mạnh. Thay vào đó, dùng metric tổng hợp toàn hệ thống và log/tracing có kiểm soát để điều tra một tenant cụ thể.

Audit log nên ghi các hành động nhạy cảm: thay đổi role, thêm/xóa membership, tải file, export dữ liệu, thay đổi key, truy cập support và thao tác quản trị tenant.

Quyền support/admin cần được tách riêng, có lý do truy cập, thời hạn, approval nếu cần và audit. Không dùng một tài khoản quản trị chung không truy vết được.

## 17. Kiểm thử cô lập tenant

Test phải chứng minh tenant A không thể đọc, sửa, xóa hoặc suy luận dữ liệu tenant B qua mọi đường truy cập.

| Kiểm thử | Kết quả mong đợi |
|---|---|
| User A truy cập resource tenant A | Cho phép nếu có permission |
| User A đổi path sang tenant B | Từ chối |
| User A gửi header tenant B | Từ chối nếu không có membership |
| User thuộc nhiều tenant chuyển workspace | Context và permission được đổi đúng |
| Query chỉ có resource ID | Repository yêu cầu tenant hoặc policy DB chặn |
| RLS không được set | Không đọc/ghi được row tenant |
| Connection được tái sử dụng cho tenant khác | Transaction-local tenant context không bị rò |
| Message mang tenantId giả | Consumer đối chiếu và từ chối |
| Cache key thiếu tenant | Test phát hiện collision/cross-tenant result |
| Presigned URL cho object tenant A | Không thể dùng để đọc object tenant B |
| Tenant vượt quota | Bị throttled trong phạm vi tenant đó |
| Membership bị thu hồi | Request mới bị từ chối theo policy |
| Support access | Có quyền tạm thời và audit |
| Tenant offboarding | API, queue, cache và storage không còn cho phép truy cập trái phép |

### Property-based và negative testing

Ngoài unit test thông thường, tạo dữ liệu nhiều tenant rồi chạy cùng một tập thao tác với tenant ID ngẫu nhiên. Với mọi response, kiểm tra tất cả record trả về có tenant_id đúng. Với mọi mutation, xác minh chỉ row thuộc tenant hiện tại thay đổi.

Kiểm thử cả đường lỗi: exception giữa transaction, timeout trước commit, retry message và function reuse. Nhiều lỗi isolation xuất hiện ở cleanup code hoặc retry path hơn là happy path.

## 18. Những lỗi triển khai thường gặp

- **Tin tenantId từ request:** attacker có thể đổi tenant selector; xác minh membership từ identity đã được xác thực.
- **Chỉ kiểm tra tenant ở UI:** caller có thể gọi API trực tiếp; authorization phải ở backend.
- **Query chỉ theo object ID:** tạo IDOR/cross-tenant access; mọi truy vấn cần tenant boundary.
- **Không dùng composite key hoặc foreign key có tenant:** có thể tạo liên kết dữ liệu chéo tenant.
- **Dùng ThreadLocal/static tenant context mà không cleanup:** request sau có thể nhận context cũ; truyền explicit context và cleanup đúng lifecycle.
- **Đặt RLS context ngoài transaction:** connection pool có thể giữ context cho tenant tiếp theo; dùng transaction-local setting.
- **Dùng database role có BYPASSRLS:** policy không bảo vệ được query của ứng dụng; dùng role runtime bị giới hạn.
- **Coi object prefix là security boundary:** quyền bucket có thể vẫn cho đọc toàn bộ; kiểm tra IAM và key cụ thể.
- **Tin tenantId trong message:** producer bug hoặc bị xâm phạm có thể phát message sai tenant; consumer phải đối chiếu.
- **Cache key thiếu tenant:** dữ liệu tenant A có thể được trả cho tenant B.
- **Dùng một secret chung cho mọi tenant:** một lần lộ credential ảnh hưởng toàn bộ khách hàng; tách secret theo nhu cầu.
- **Không có quota:** một tenant có thể làm cạn concurrency, connection hoặc storage của tenant khác.
- **Không kiểm soát support access:** nhân viên hoặc công cụ vận hành có thể truy cập dữ liệu không có audit.
- **Offboarding chỉ xóa user:** object, queue, secret và cache vẫn có thể tồn tại hoặc truy cập được.

## 19. Quy trình thiết kế multi-tenant cho Java serverless

Khi xây dựng hoặc rà soát hệ thống multi-tenant, có thể đi theo trình tự:

1. Xác định tenant là tổ chức, workspace hay đơn vị sở hữu dữ liệu.
2. Thiết kế identity và membership; không suy tenant từ email hoặc client-supplied ID.
3. Xác minh issuer, subject, audience và trạng thái principal.
4. Tạo TenantContext immutable cho từng HTTP request hoặc message.
5. Kiểm tra permission theo tenant, resource và action.
6. Chọn pool, bridge hoặc silo cho database và tài nguyên.
7. Đặt tenant key trong schema, query, unique constraint và foreign key.
8. Bổ sung RLS hoặc database policy làm defense-in-depth nếu phù hợp.
9. Namespace object storage, cache, search và queue theo tenant.
10. Quản lý secret và encryption key theo mức cô lập yêu cầu.
11. Truyền tenant context qua service/event theo contract được xác minh.
12. Đặt quota và fair scheduling để chống noisy neighbor.
13. Thiết kế provisioning, migration, suspension và offboarding.
14. Thiết lập audit, logging và metric không gây lộ dữ liệu/cardinality quá cao.
15. Kiểm thử cross-tenant access, retry, connection reuse và mọi đường async.

## 20. Ghi nhớ

Cô lập tenant cần bắt đầu từ identity đã xác thực và membership đáng tin, sau đó được áp dụng ở authorization, database, object storage, queue, cache, secret và tài nguyên compute. Tenant ID trong request hoặc message chỉ là dữ liệu đầu vào cho đến khi được đối chiếu với nguồn tin cậy.

Trong Java serverless, tạo TenantContext riêng cho từng invocation, truyền rõ ràng qua các lớp và không lưu tenant state trong static field hoặc ThreadLocal không được cleanup. Với database dùng chung, tenant key, composite constraints và RLS có thể tạo nhiều lớp bảo vệ; với tenant cần cô lập mạnh hơn, cân nhắc cell hoặc silo.

Kiểm soát quota để một tenant không làm ảnh hưởng tenant khác, quản lý vòng đời provisioning/offboarding và kiểm thử negative path trên cả HTTP lẫn worker. Mục tiêu là bảo đảm mọi thao tác chỉ tác động đến dữ liệu và tài nguyên mà tenant hiện tại được phép sử dụng.

