# Tenant trong partition key và kiểm tra quyền truy cập

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **tenant**, **principal**, **role**, **resource owner**, **partition key** và **authorization boundary** trong một ứng dụng SaaS đa khách hàng.
- Giải thích vì sao thêm `tenant_id` vào partition key giúp tổ chức dữ liệu/query theo phạm vi tenant nhưng **không tương đương row-level security** do Cassandra tự thực thi.
- Thiết kế bảng theo từng truy vấn với khóa dạng `((tenant_id, order_id))`, `((tenant_id, customer_id, month_bucket), created_at, order_id)`; tránh thiết kế `tenant_id` đơn độc tạo partition khổng lồ.
- Lấy tenant context từ **identity đã xác thực** và kiểm tra quyền truy cập tenant, không tin header, path, query parameter hoặc body làm bằng chứng phân quyền.
- Ngăn **IDOR/BOLA** (Insecure Direct Object Reference / Broken Object Level Authorization), truy vấn xuyên tenant, cache-key collision, upsert sai tenant và lọt dữ liệu qua job/event/export.
- Viết CQL với prepared statements và đủ partition key, tránh `ALLOW FILTERING`/index hoặc truy vấn theo `order_id` như một cách “lách” tenant scoping.
- Triển khai `@PrimaryKeyClass` và `CassandraRepository`/`CassandraTemplate` hoặc `CqlSession` để mọi đường đọc/ghi đều nhận tenant ID đã được cho phép.
- Áp dụng RBAC/ABAC cho **cả tenant và tài nguyên**; kiểm soát API, batch/background jobs, reactive pipelines, token claims và cache.
- Phân biệt Cassandra database roles/grants theo keyspace/table với **quyền trên từng partition** mà tầng ứng dụng phải kiểm tra; biết khi nào cần mô hình cô lập mạnh hơn.
- Xây test matrix cross-tenant, adversarial cases, audit, monitoring và kế hoạch migration khi hệ thống đã có bảng không chứa tenant trong khóa.

Bài nằm trong chương **Thiết kế ứng dụng** của **SPRING_DATA_CASSANDRA**: sử dụng Apache Cassandra qua entity mapping, repository, `CassandraTemplate` và truy vấn CQL, đồng thời thiết kế bảng theo truy vấn, partition key, tính nhất quán, paging và kiểm soát hiệu năng trong hệ dữ liệu phân tán. Trong môi trường nhiều tenant, lựa chọn partition key còn ảnh hưởng **an toàn truy cập dữ liệu**. Vì vậy thiết kế lưu trữ và kiến trúc phân quyền phải được review như **hai tầng riêng biệt nhưng bổ trợ nhau**.

> **Nguyên tắc cốt lõi:** `tenant_id` trong khóa là điều kiện cần cho nhiều kiểu truy vấn tenant-scoped, **không phải giấy phép truy cập**. Chỉ dùng một tenant ID được xác định từ ngữ cảnh người gọi đã xác thực **và đã được ủy quyền**. Mọi thao tác đọc, ghi, cập nhật, xóa, batch, cache và job phải giữ nguyên ranh giới này.

## 1. Tại sao đa tenant là bài toán ứng dụng, không chỉ là khóa Cassandra?

Một dịch vụ quản lý đơn hàng phục vụ ba tổ chức:

~~~text
Tenant A / shop-alpha
  ├── User Alice: quản trị đơn hàng
  └── User Bob: chỉ xem các đơn được giao

Tenant B / shop-beta
  └── User Carol: quản trị đơn hàng

Tenant C / shop-gamma
  └── Worker batch import được cấp quyền hạn chế
~~~

Alice có thể biết hoặc đoán `order_id` của Tenant B, nhưng **không được đọc đơn hàng đó**. Bob có thể truy cập Tenant A, nhưng chưa chắc có quyền xem **mọi** đơn hàng của Tenant A. Một background worker có thể xử lý dữ liệu của Tenant C mà không phải là người dùng đăng nhập.

Có hai yêu cầu khác nhau:

1. **Data locality / access pattern:** Câu SELECT/UPDATE có thể tìm đúng partition theo tenant và khóa nghiệp vụ không?
2. **Authorization:** Caller có quyền thực hiện **hành động cụ thể** trên **tenant và resource** đó không?

Nếu chỉ giải quyết yêu cầu 1 bằng schema, một API vẫn có thể lộ dữ liệu khi dùng tenant ID do client tự khai báo mà không xác minh quyền.

### 1.1. Những khái niệm không nên đánh đồng

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Tenant | `tenant-a`, UUID của tổ chức | Phạm vi dữ liệu/khách hàng |
| Principal | User ID hoặc service identity | Ai đang gọi? |
| Authentication | Kiểm tra JWT signature, issuer, audience, expiry | Người gọi có được xác thực không? |
| Tenant membership | User thuộc tổ chức nào, còn hiệu lực không? | Người này được tham gia tenant nào? |
| Authorization | Quyền `orders:read`, `orders:write`, ownership | Người gọi được làm gì trên resource nào? |
| Cassandra partition key | `(tenant_id, order_id)` | Cassandra tìm/phân phối dữ liệu ở đâu? |
| Resource identifier | `order_id` | Định danh business object, không tự cấp quyền |
| Database role | Role/GRANT ở Cassandra | Quyền CQL theo keyspace/table, không phải tenant-row policy |
| Tenant context | Đối tượng đã kiểm tra chứa tenant và actor | Mang phạm vi truy cập an toàn giữa các tầng |

**Biết một tenant ID không phải là bằng chứng thuộc tenant.** Một UUID khó đoán cũng không phải access-control policy. Đừng dựa vào tính ngẫu nhiên của ID để che việc thiếu authorization.

### 1.2. Hình dung các ranh giới

~~~mermaid
flowchart TD
    U["Caller: JWT / service identity"] --> A["Spring Security xác thực"]
    A --> B["Chọn tenant và xác minh membership/permission"]
    B --> C["TenantContext đã được ủy quyền"]
    C --> S["Service: kiểm tra resource/operation"]
    S --> R["Repository/DAO tenant-scoped"]
    R --> D["Cassandra: PRIMARY KEY chứa tenant_id"]
    D --> X["Replica/partition phù hợp"]
    W["Untrusted path/header/body tenant_id"] -. "Không phải bằng chứng quyền" .-> B
~~~

Cassandra giúp thực thi CQL và phân phối row theo khóa; nó **không biết business role** của Alice, Bob hay Carol nếu ứng dụng dùng một database account chung.

## 2. Ba lựa chọn bố trí dữ liệu multi-tenant

Không phải mọi hệ SaaS đều bắt buộc dùng chung table. Các mô hình phổ biến:

| Mô hình | Data layout | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **Chung keyspace/table, tenant trong key** | `orders_by_tenant_id` với `tenant_id` | Quản trị schema tập trung, phù hợp nhiều tenant nhỏ | Ứng dụng phải kiểm soát tenant isolation, noisy-neighbor, quotas |
| **Keyspace theo tenant** | `tenant_a.orders`, `tenant_b.orders` | Có ranh giới namespace/quyền Cassandra mạnh hơn theo keyspace | Schema migration, keyspace count, vận hành/backup/RF phức tạp |
| **Cụm hoặc account/đơn vị hạ tầng tách riêng** | Dedicated Cassandra per tenant/tier | Cô lập vận hành/bảo mật mạnh hơn | Chi phí và quản trị tăng, cần routing/connection lifecycle |

Không có mô hình nào thắng mọi tình huống. Chọn theo yêu cầu hợp đồng, residency, bảo mật, quy mô, cost và năng lực vận hành. Trong bài này tập trung vào **chung bảng có tenant ID trong primary key**, vì đây là phương án thường gặp ở những dịch vụ Spring Data Cassandra đa tenant.

### 2.1. Chỉ có tenant_id trong khóa có đủ an toàn không?

Không. Tưởng tượng:

~~~sql
SELECT *
FROM orders_by_tenant_id
WHERE tenant_id = ?
  AND order_id = ?;
~~~

Câu CQL chỉ đảm bảo truy vấn đi tới partition có tenant ID đã truyền. **Ai quyết định giá trị bind `tenant_id`?**

- Nếu frontend gửi bất kỳ UUID rồi backend truyền thẳng, caller có thể thử UUID tenant khác.
- Nếu backend lấy từ token có chữ ký nhưng không xác minh quyền phù hợp trên resource, user vẫn có thể đọc đơn hàng của đồng nghiệp trong tenant.
- Nếu backend lấy từ phiên truy cập đã xác thực, xác minh membership và permission, sau đó buộc key của query dùng đúng tenant đó, nguy cơ BOLA giảm đáng kể.

**Schema là một lớp phòng thủ cấu trúc**, không thay cho chính sách phân quyền.

## 3. Đừng dùng tenant_id làm partition key duy nhất cho mọi dữ liệu

Một schema trông “đúng tenant” nhưng dễ gặp wide partition:

~~~sql
-- Phản mẫu nếu một tenant có hàng triệu đơn hàng:
CREATE TABLE orders_by_tenant_unbounded (
    tenant_id uuid,
    order_id uuid,
    created_at timestamp,
    status text,
    PRIMARY KEY ((tenant_id), order_id)
);
~~~

Trong bảng này, **toàn bộ đơn hàng của một tenant nằm trong một partition**. Một tenant lớn với hàng triệu orders có thể tạo wide partition, tăng chi phí truy vấn, compaction và tải replica. `tenant_id` trong partition key không phải lý do để gom **toàn bộ dữ liệu tenant** vào một partition.

### 3.1. Lookup một đơn hàng theo ID

Nếu API là:

~~~text
GET /tenants/{tenantId}/orders/{orderId}
~~~

và luôn biết tenant cùng order ID, một lựa chọn là:

~~~sql
CREATE TABLE IF NOT EXISTS orders_by_tenant_id (
    tenant_id uuid,
    order_id uuid,
    customer_id uuid,
    status text,
    amount_minor bigint,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Ở đây, **composite partition key** là `(tenant_id, order_id)`; mỗi cặp là một partition. Hai tenant khác nhau có thể có cùng `order_id` nhưng được lưu ở hai partition khác nhau.

Đọc:

~~~sql
SELECT tenant_id, order_id, customer_id,
       status, amount_minor, created_at
FROM orders_by_tenant_id
WHERE tenant_id = ?
  AND order_id = ?;
~~~

Điểm cần nhớ:

- Tenant ID là **thành phần bắt buộc của khóa truy cập**.
- Order ID nằm cùng partition key, nên không tạo một partition rất lớn chỉ theo tenant.
- Một row/partition nhỏ có thể phù hợp lookup; không có nghĩa mọi query list đều được hỗ trợ.
- `PRIMARY KEY ((tenant_id, order_id))` khác `PRIMARY KEY ((tenant_id), order_id)`: ở dạng thứ hai `order_id` là clustering column và mọi đơn tenant có thể cùng partition.

### 3.2. Truy vấn danh sách đơn của khách hàng

Một API khác:

~~~text
GET /tenants/{tenantId}/customers/{customerId}/orders
    ?month=2026-11
~~~

Nên có bảng **theo truy vấn**, ví dụ:

~~~sql
CREATE TABLE IF NOT EXISTS orders_by_customer_month (
    tenant_id uuid,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    amount_minor bigint,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        created_at, order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC, order_id DESC
);
~~~

CQL:

~~~sql
SELECT created_at, order_id, status, amount_minor
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
~~~

Tại sao có `customer_id` và `month_bucket` trong partition key?

- Một tenant nhiều khách hàng không dồn tất cả orders vào một partition.
- Theo từng customer và tháng, kích thước partition được giới hạn tốt hơn.
- API có thể dự đoán partition cần đọc.
- `created_at, order_id` giúp phân biệt events cùng millisecond và phân trang theo thứ tự trong partition.

**Đây là denormalization theo read pattern**, không phải database join. Khi cập nhật trạng thái đơn, ứng dụng phải đồng bộ hai bảng read model theo workflow được thiết kế.

### 3.3. Danh sách tất cả đơn của một tenant

Nếu API yêu cầu “đơn mới nhất của tenant bất kể customer”, `orders_by_customer_month` không tự trả lời hiệu quả. Có thể thêm một read model:

~~~sql
CREATE TABLE IF NOT EXISTS orders_by_tenant_month_shard (
    tenant_id uuid,
    month_bucket text,
    shard_id int,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    status text,
    PRIMARY KEY (
        (tenant_id, month_bucket, shard_id),
        created_at, order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC, order_id DESC
);
~~~

`shard_id` cần được chọn ổn định theo một quy tắc có kiểm soát; reader sẽ truy vấn nhiều shards, merge/sort và dùng cursor phù hợp. **Thêm shard là đánh đổi write/load distribution lấy read fan-out**, không phải cơ chế phân quyền.

### 3.4. Bảng quyết định theo access pattern

| API | Partition key hợp lý | Đường đọc |
| --- | --- | --- |
| Order detail bằng orderId trong tenant | `(tenant_id, order_id)` | Tra cứu chính xác một partition |
| Orders của customer theo tháng | `(tenant_id, customer_id, month_bucket)` | Range theo clustering time |
| Recent orders của tenant theo tháng | `(tenant_id, month_bucket, shard_id)` | Fan-out shards, merge cursor |
| Invoice theo invoiceId trong tenant | `(tenant_id, invoice_id)` | Lookup tenant-scoped |
| User theo email trong tenant | `(tenant_id, normalized_email)` | Tenant-local uniqueness |
| Global audit bởi internal admin | Mô hình riêng/đường truy vấn được cấp quyền | Không loại bỏ tenant authorization trên public API |

**Không thiết kế bảng đa tenant chỉ dựa vào tính tiện lợi của method repository**. Bắt đầu từ truy vấn, kích thước partition, isolation và chính sách cập nhật.

## 4. Những sai lầm trong khóa truy cập gây rò rỉ dữ liệu

### 4.1. Chỉ có order ID, không có tenant

~~~java
// RỦI RO khi tìm theo business ID toàn cục
// rồi tin rằng biết ID là đủ quyền đọc:
Order order = globalOrderRepository.findById(orderId)
    .orElseThrow();
return toDto(order);
~~~

Nếu API không xác minh tenant/owner, một người dùng đoán được order ID có thể truy cập order khác. Đây là ví dụ của **BOLA/IDOR**.

Một thiết kế an toàn hơn tạo query **tenant-scoped ngay từ đầu**:

~~~java
OrderKey key = new OrderKey(
    authorizedTenantId,
    requestedOrderId
);
Order order = repository.findById(key)
    .orElseThrow();
~~~

Nhưng vẫn cần kiểm tra quyền trên **resource**: user cùng tenant có thể chỉ được xem các orders do mình quản lý.

### 4.2. Dùng request body tenant_id để quyết định nơi ghi

~~~json
{
  "tenantId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "orderId": "11111111-1111-4111-8111-111111111111",
  "status": "PAID"
}
~~~

Nếu backend nhận tenant ID từ JSON và ghi thẳng vào Cassandra, caller của Tenant A có thể cố ghi vào tenant B. Dù CQL dùng prepared statements, **giá trị bind vẫn có thể là tenant không được cấp quyền**.

Cách xử lý:

- Tenant đang tác nghiệp được chọn qua path/header nếu API cần nhiều tenant, nhưng phải kiểm tra membership/role với principal đã xác thực.
- Tenant ID trong body nên **bỏ qua** hoặc đối chiếu phải khớp với tenant đã được cấp quyền, không lấy làm source-of-truth.
- Service tạo entity với `tenantId=authorizedContext.tenantId()`, không lấy từ DTO tùy ý.
- Object owner, customerId và các business references khác cũng phải được kiểm tra thuộc tenant này.

### 4.3. Dùng ALLOW FILTERING để bỏ tenant_id

~~~sql
-- Phản mẫu:
SELECT * FROM orders_by_tenant_id
WHERE order_id = ?
ALLOW FILTERING;
~~~

Cassandra không biến query thiếu partition key thành phép tìm tốt. `ALLOW FILTERING` không phải cách bypass schema hoặc authorization an toàn: nó có thể dẫn tới scan tốn kém, phụ thuộc data distribution, và nếu trả được row theo ID mà không giới hạn tenant sẽ có nguy cơ lộ dữ liệu.

Nếu nghiệp vụ **thật sự cần** lookup chỉ theo order ID, hãy thiết kế một đường lookup riêng có authority phù hợp (ví dụ internal service được cấp quyền đặc biệt) và **không bỏ bước kiểm tra tenant khi đọc tài nguyên cuối**.

### 4.4. Secondary index không phải row-level security

Một index trên `tenant_id` hoặc `order_id` chỉ thay đổi cách truy cập dữ liệu (kèm chi phí hiệu năng). Nó không kiểm tra JWT, membership, resource owner hoặc permission. SAI/2i/đường search bên ngoài cũng không thay thế authorization; mọi kết quả trả về phải được giới hạn theo tenant và policy.

## 5. Phân biệt xác thực, chọn tenant và ủy quyền

Đối với ứng dụng một user có thể tham gia nhiều tổ chức:

~~~text
User U được cấp:
  tenant-a: orders:read
  tenant-b: orders:read + orders:write
  tenant-c: không có quyền
~~~

Một request có thể chọn tenant bằng URL:

~~~http
GET /tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/orders/11111111-1111-4111-8111-111111111111
Authorization: Bearer <verified-access-token>
~~~

**UUID trên URL chỉ là tenant được yêu cầu**, không chứng minh user thuộc tenant đó. Tầng Security/Service phải:

1. Xác minh access token bằng cơ chế chuẩn: chữ ký, issuer, audience, expiry, alg/key phù hợp và các controls liên quan.
2. Xác định principal subject và loại identity (user/service).
3. Xác định tenant được yêu cầu.
4. Kiểm tra membership hiện hành và quyền `orders:read` hoặc `orders:write` trong tenant đó.
5. Xác định giới hạn resource cụ thể, ví dụ assigned customer/department/owner.
6. Truyền **TenantContext đã được ủy quyền** xuống service/repository; không truyền nguyên request body làm policy.
7. Dùng tenant từ context khi tạo partition key và khóa cache/event.

### 5.1. JWT có tenant_id claim vẫn cần chính sách

Một token được ký hợp lệ có thể chứa:

~~~json
{
  "sub": "user-123",
  "tenant_id": "tenant-a",
  "scope": "orders:read"
}
~~~

Cần đảm bảo token **đúng issuer/audience** và tenant claim do identity provider đáng tin cậy cấp. Khi membership bị thu hồi nhưng token còn sống, authorization có thể cần kiểm tra trạng thái membership hiện hành hoặc có cơ chế token TTL/revocation/cached authorization phù hợp.

Nếu một user có nhiều tenants, token `tenant_id` đơn có thể đại diện **active tenant** hoặc không đủ biểu diễn toàn bộ quyền. Không suy từ claim này rằng user được truy cập tất cả resources của tenant.

### 5.2. RBAC và ABAC

**RBAC** kiểm tra role/permission: admin tenant được đọc nhiều đơn; viewer chỉ đọc.

**ABAC** kiểm tra thêm thuộc tính: user thuộc sales team nào, order gán cho ai, trạng thái đơn có cho sửa không, thời gian giao dịch, loại khách hàng.

Ví dụ:

~~~text
CanReadOrder =
    Authenticated
    AND MembershipActive(principal, tenant)
    AND HasPermission(principal, tenant, "orders:read")
    AND (
        HasRole(principal, tenant, "tenant-admin")
        OR order.assigneeId == principal.userId
    )
~~~

Với Cassandra, không thể đẩy toàn bộ logic này vào điều kiện partition key. Partition key giúp tìm **đúng tenant**, còn chính sách row/resource vẫn do application/service enforcement hoặc một hệ policy engine đáng tin cậy thực thi.

## 6. Tạo TenantContext đã được ủy quyền

Một cách giảm khả năng developer vô tình bind sai tenant là tách **tenant ID được yêu cầu** khỏi **tenant context đã được phép**.

### 6.1. Object riêng để mang authority

~~~java
import java.util.Set;
import java.util.UUID;

public record TenantContext(
    UUID tenantId,
    String actorId,
    Set<String> permissions
) {
    public TenantContext {
        if (tenantId == null || actorId == null
                || actorId.isBlank() || permissions == null) {
            throw new IllegalArgumentException(
                "Invalid authorized tenant context");
        }
        permissions = Set.copyOf(permissions);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

`TenantContext` ở đây là **dữ liệu đã qua kiểm tra**, không phải object tùy ý người gọi được tạo từ JSON. Controller không nên nhận một `TenantContext` client-supplied rồi bỏ qua bước xác minh.

Một API phân quyền có thể khai báo:

~~~java
import java.util.UUID;
import org.springframework.security.oauth2.jwt.Jwt;

public interface TenantAuthorization {

    TenantContext require(
        Jwt verifiedJwt,
        UUID requestedTenantId,
        String requiredPermission
    );
}
~~~

Một implementation đúng của `require` phải:

1. Giả định token **đã được xác minh bởi Spring Security Resource Server** với cấu hình issuer/audience/keys/expiry phù hợp; hoặc kiểm tra tương đương ở boundary đáng tin cậy.
2. Xác định `sub` của người gọi và identity type.
3. Tra cứu membership/role tenant từ nguồn có thẩm quyền (hoặc claims đáng tin cậy có chính sách freshness rõ).
4. Kiểm tra membership chưa bị khóa/thu hồi, scope có hành động yêu cầu.
5. Trả `TenantContext` chứa **requestedTenantId đã được cho phép**.
6. Từ chối `requestedTenantId` nằm ngoài tập tenant hợp lệ mà không dò dữ liệu business.
7. Với service identity, xác minh quyền machine-to-machine theo tenant/workload, không mặc định “service account = full access”.

Mẫu interface này cố ý **không giả định** mô hình dữ liệu membership trong module; membership có thể nằm trong hệ IAM, database riêng hoặc dịch vụ policy phù hợp.

### 6.2. Spring Security Resource Server là tầng authentication

Một ứng dụng có thể cấu hình Spring Security xác thực JWT access token ở filter chain. Một số điều kiện quan trọng:

- Token signature hợp lệ theo key/algorithm được chấp nhận.
- `iss`, `aud`, `exp`, `nbf` và những claims cần thiết được validate theo hợp đồng.
- Không dùng **ID token** như access token của API nếu hệ thống OIDC phân biệt chúng.
- Không chấp nhận JWT không verify hoặc tự decode base64 rồi tin claims.
- Không lấy `X-Tenant-Id` hoặc `tenantId` trong body làm authority nếu token chưa được kiểm tra.
- Nếu vai trò/membership có thể bị thu hồi giữa vòng đời access token, định nghĩa thời hạn token, kiểm tra quyền cập nhật hoặc cơ chế revocation/cache invalidation.

**Tách rõ:** Spring Security xác thực danh tính; `TenantAuthorization.require` xác minh quyền truy cập tenant; `OrderPolicy` kiểm tra quyền trên một **order cụ thể**.

### 6.3. Controller chọn tenant qua path rồi xác minh

~~~java
import java.util.UUID;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/tenants/{tenantId}/orders")
public class OrderController {

    private final TenantAuthorization authorization;
    private final OrderService orderService;

    public OrderController(
            TenantAuthorization authorization,
            OrderService orderService) {
        this.authorization = authorization;
        this.orderService = orderService;
    }

    @GetMapping("/{orderId}")
    public ResponseEntity<OrderDto> find(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID tenantId,
            @PathVariable UUID orderId) {

        TenantContext context = authorization.require(
            jwt, tenantId, "orders:read"
        );

        return orderService.findAuthorized(context, orderId)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Ở đây, `tenantId` trong path chỉ là **yêu cầu chọn phạm vi**. Chỉ sau khi `require` kiểm tra quyền, tenant ID mới trở thành `context.tenantId()` được service tin cậy để tạo khóa Cassandra.

Trong API thật, cần thêm exception mapping để phân biệt unauthenticated (401), unauthorized tenant/permission (403 hoặc 404 theo policy che giấu) và resource không có trong phạm vi (404). Không tiết lộ dữ liệu của tenant khác trong error payload.

## 7. Spring Data Cassandra với composite key tenant-aware

### 7.1. Key class khớp CQL composite partition key

Với bảng:

~~~sql
CREATE TABLE orders_by_tenant_id (
    tenant_id uuid,
    order_id uuid,
    customer_id uuid,
    status text,
    amount_minor bigint,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Có thể dùng `@PrimaryKeyClass`:

~~~java
import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderKey implements Serializable {

    @PrimaryKeyColumn(
        name = "tenant_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "order_id",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID orderId;

    public OrderKey() {}

    public OrderKey(UUID tenantId, UUID orderId) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.orderId = Objects.requireNonNull(orderId);
    }

    public UUID getTenantId() { return tenantId; }
    public UUID getOrderId() { return orderId; }

    public void setTenantId(UUID tenantId) {
        this.tenantId = tenantId;
    }

    public void setOrderId(UUID orderId) {
        this.orderId = orderId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderKey key)) return false;
        return Objects.equals(tenantId, key.tenantId)
            && Objects.equals(orderId, key.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, orderId);
    }
}
~~~

`@PrimaryKeyColumn(type=PARTITIONED)` cho cả tenant và order ID tương ứng **cùng một composite partition key**, không phải chỉ tenant là partition key và order ID là clustering column. `equals`/`hashCode` dùng đủ thành phần khóa để tránh map/cache behavior không nhất quán.

### 7.2. Entity gắn khóa ghép

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_tenant_id")
public class OrderByTenantId {

    @PrimaryKey
    private OrderKey key;

    @Column("customer_id")
    private UUID customerId;

    @Column("status")
    private String status;

    @Column("amount_minor")
    private Long amountMinor;

    @Column("created_at")
    private Instant createdAt;

    public OrderByTenantId() {}

    public OrderKey getKey() { return key; }
    public void setKey(OrderKey key) { this.key = key; }

    public UUID getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public Long getAmountMinor() { return amountMinor; }
    public Instant getCreatedAt() { return createdAt; }

    // Các setter business fields còn lại...
}
~~~

`@PrimaryKey` của entity là một object chứa **tenant + order**. Đây là một biện pháp kết cấu hữu ích: method repository tiêu chuẩn không thể chỉ nhận `UUID orderId` làm ID nếu khai báo đúng kiểu `OrderKey`.

### 7.3. Repository với ID type là composite key

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderByTenantIdRepository
        extends CassandraRepository<OrderByTenantId, OrderKey> {
}
~~~

Truy vấn đúng:

~~~java
OrderKey key = new OrderKey(
    context.tenantId(), requestedOrderId
);

return repository.findById(key);
~~~

Dù thế, **repository không tự kiểm tra quyền của caller**. Nếu developer tạo `new OrderKey(otherTenantId, orderId)` bằng dữ liệu chưa xác minh, repository vẫn có thể đọc tenant khác theo quyền của database account.

Do đó, có thêm tầng service/policy.

### 7.4. Service giữ tenant context và kiểm tra resource

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderByTenantIdRepository repository;
    private final OrderPolicy orderPolicy;

    public OrderService(
            OrderByTenantIdRepository repository,
            OrderPolicy orderPolicy) {
        this.repository = repository;
        this.orderPolicy = orderPolicy;
    }

    public Optional<OrderDto> findAuthorized(
            TenantContext context, UUID orderId) {

        if (!context.hasPermission("orders:read")) {
            throw new SecurityException("Access denied");
        }

        OrderKey key = new OrderKey(
            context.tenantId(), orderId
        );

        return repository.findById(key)
            .filter(order -> orderPolicy.canRead(context, order))
            .map(OrderDto::fromEntity);
    }
}
~~~

`OrderPolicy.canRead` cần xác minh quyền trên resource, ví dụ customer/team/assigned user. Nó không nên chỉ so `context.tenantId() == order.key.tenantId` rồi mặc định mọi thành viên tenant được đọc tất cả.

Với dữ liệu rất nhạy cảm, cân nhắc **kiểm tra policy dựa trên metadata có thể query tenant-scoped** trước khi đọc payload lớn, hoặc trả projection hạn chế theo quyền. **Đọc rồi lọc trong service chỉ chấp nhận được khi payload chưa rời ranh giới tin cậy và mọi đường xuất dữ liệu đều qua policy**; không stream danh sách/cached DTO trước khi lọc.

### 7.5. Đảm bảo tenant của entity khi ghi

~~~java
public void create(
        TenantContext context,
        UUID orderId,
        CreateOrderRequest request) {

    if (!context.hasPermission("orders:write")) {
        throw new SecurityException("Access denied");
    }

    // Validate customerId thuộc context.tenantId() trước khi ghi.
    validateCustomerInTenant(
        context.tenantId(), request.customerId()
    );

    OrderByTenantId entity = new OrderByTenantId();
    entity.setKey(new OrderKey(context.tenantId(), orderId));
    entity.setCustomerId(request.customerId());
    entity.setStatus("CREATED");

    repository.save(entity);
}
~~~

Đây là skeleton: các setters và `validateCustomerInTenant` cần được triển khai trong service thật. Điểm chính là **không lấy tenantId từ request body**; tenant được gán từ context đã kiểm tra. `repository.save` có semantics Cassandra upsert, không tự giải quyết tạo trùng hoặc xung đột trạng thái. Khi cần create-only, cân nhắc `IF NOT EXISTS`/LWT và xử lý `[applied]`; khi cần version locking, dùng điều kiện phù hợp.

## 8. CqlSession và prepared statements: mọi mutation phải đủ tenant key

Trong những write path cần kiểm soát rõ CQL, dùng `CqlSession` do Spring inject và query đã prepare.

### 8.1. SELECT theo tenant + ID

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderCqlDao {

    private final CqlSession session;
    private final PreparedStatement byTenantAndId;

    public OrderCqlDao(CqlSession session) {
        this.session = session;
        this.byTenantAndId = session.prepare(
            "SELECT tenant_id, order_id, customer_id, status, " +
            "amount_minor, created_at " +
            "FROM orders_by_tenant_id " +
            "WHERE tenant_id = ? AND order_id = ?"
        );
    }

    public Row findRow(TenantContext ctx, UUID orderId) {
        return session.execute(
            byTenantAndId.bind(ctx.tenantId(), orderId)
        ).one();
    }
}
~~~

Ví dụ trả `Row` để dễ thấy bind values; production DAO nên map sang một kiểu domain/DTO nội bộ, không trả `Row` trực tiếp tới web client. Kiểm tra `Row==null` và nullability trước khi đọc fields.

### 8.2. UPDATE và DELETE theo tenant

~~~sql
UPDATE orders_by_tenant_id
SET status = ?
WHERE tenant_id = ?
  AND order_id = ?;
~~~

~~~sql
DELETE FROM orders_by_tenant_id
WHERE tenant_id = ?
  AND order_id = ?;
~~~

Trước khi gửi lệnh:

1. Xác định principal, tenant, permission.
2. Xác minh resource tồn tại **trong tenant** và caller có quyền sửa/xóa resource đó.
3. Bind `tenant_id=context.tenantId()`, không cho body tự thay.
4. Khi cần state transition đúng, dùng `IF status = ?` hoặc version/CAS, không chỉ upsert.
5. Xử lý timeout và readback theo tenant; không dùng global ID để điều tra khi người dùng chỉ có quyền tenant-scoped.

### 8.3. INSERT IF NOT EXISTS chống ghi đè cùng khóa, không cấp quyền

~~~sql
INSERT INTO orders_by_tenant_id (
    tenant_id, order_id, customer_id,
    status, amount_minor, created_at
)
VALUES (?, ?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

`IF NOT EXISTS` có thể giảm rủi ro hai requests tạo cùng order key, nhưng **không kiểm tra membership/role**. Nếu một caller trái phép được bind tenant B, LWT vẫn có thể tạo row tenant B vì Cassandra không biết quyền business của caller. LWT dùng serial consistency và có chi phí, timeout có thể cho kết quả chưa rõ; xử lý theo request ID/idempotency workflow.

### 8.4. Prepared statement không phải phép kiểm tra tenant

~~~java
// Phản mẫu: query đã prepare vẫn có thể lộ dữ liệu
// nếu tenantId lấy thẳng từ request mà chưa được cho phép.
session.execute(prepared.bind(request.tenantId(), orderId));
~~~

**Bind markers phòng lỗi SQL/CQL injection ở giá trị**, nhưng không đảm bảo giá trị đó thuộc quyền của caller. Injection defense và authorization là hai lớp tách biệt, cả hai đều cần.

## 9. CassandraTemplate: luôn kèm tenant trong query

Với `CassandraTemplate`, có thể tạo `Query` dùng tenant và order ID:

~~~java
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

Query query = Query.query(
    Criteria.where("tenant_id").is(context.tenantId())
        .and("order_id").is(orderId)
);

OrderByTenantId order = cassandraTemplate.selectOne(
    query, OrderByTenantId.class
);
~~~

Không nên làm:

~~~java
// Không phù hợp: query thiếu tenant scope.
Query unsafe = Query.query(
    Criteria.where("order_id").is(orderId)
);

// Thêm ALLOW FILTERING không biến nó thành an toàn.
~~~

Trong Cassandra, query thiếu thành phần composite partition key thường không được thực thi hiệu quả/hợp lệ nếu không có cơ chế truy vấn khác; nếu một thay đổi schema/index khiến query “chạy được” thì **authorization vẫn còn thiếu**. Vì vậy review phải phát hiện query không có tenant scope ngay cả khi test dataset nhỏ làm nó có vẻ đúng.

### 9.1. Không xây một repository method mơ hồ

Một method như:

~~~java
findByOrderId(UUID orderId)
~~~

không thể tự biết tenant nào được phép nếu thiếu tham số/ngữ cảnh. Tên method không tạo security boundary. Thay vì để tầng controller gọi trực tiếp raw repositories, cung cấp một service method như:

~~~java
findAuthorized(TenantContext context, UUID orderId)
~~~

và đóng gói raw data access sau adapter. Với list queries, bảo đảm `tenant_id` nằm trong CQL **trước khi phân trang hoặc lấy projection**.

### 9.2. Trường hợp admin nội bộ cần truy vấn nhiều tenant

Không mở một public endpoint có tham số `tenantId="*"` rồi bỏ điều kiện khóa. Nếu nghiệp vụ có operator được phép xem nhiều tenant:

- Xác minh quyền admin ở tầng riêng, có audit và approval khi phù hợp.
- Liệt kê những tenant hợp lệ cụ thể, rồi query partition theo từng tenant.
- Hoặc dùng read model/audit index được thiết kế riêng cho mục đích này.
- Giới hạn fan-out, throughput, dữ liệu nhạy cảm và scope của export.
- Không tái sử dụng request tenant-scoped của người dùng thường cho “superuser mode”.

Một người dùng có role `admin` **trong Tenant A** không mặc nhiên là admin của mọi tenant.

## 10. Quản lý phân quyền theo resource, không chỉ tenant

### 10.1. Có quyền tenant nhưng vẫn không thấy mọi order

Giả sử user Bob là nhân viên bán hàng của Tenant A; chỉ được xem orders do Bob phụ trách. Khi đọc một order:

1. Kiểm tra Bob là member Tenant A và có `orders:read`.
2. Query bằng `(tenantA, orderId)`.
3. Kiểm tra `assigneeId` / customer ownership / department ở domain policy.
4. Chỉ trả các fields Bob có quyền xem (ví dụ không lộ payment details).
5. Ghi audit có actor, tenant, action, decision và correlation ID.

Không thể giải bước 3 chỉ bằng `tenant_id` trong partition key. Nếu access pattern thường xuyên lọc theo assignee, tạo read model `orders_by_assignee_month` có **tenant + assignee + bucket** trong partition key; vẫn phải kiểm tra assignee được phép.

### 10.2. Không dùng client-supplied customerId để vượt quyền

Ví dụ API:

~~~http
GET /tenants/{tenantId}/customers/{customerId}/orders
~~~

Việc `tenantId` hợp lệ **không tự chứng minh** user có quyền với `customerId`. Service phải xác minh customer thuộc tenant và user có quyền đọc customer; sau đó mới query bảng:

~~~sql
SELECT ...
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?;
~~~

Vì Cassandra không có foreign-key constraint theo RDBMS, việc đảm bảo `customerId` không tham chiếu customer của tenant khác là trách nhiệm của application/workflow.

### 10.3. Field-level authorization

Không phải role `orders:read` nào cũng được xem địa chỉ, thông tin thanh toán hoặc PII. Có thể trả DTO khác nhau theo permission hoặc dùng projection rõ ràng:

~~~text
Viewer:
  orderId, status, createdAt

Manager:
  orderId, status, createdAt, customerId

Finance:
  orderId, status, amountMinor, invoiceStatus
~~~

**Không SELECT * rồi serialize nguyên entity** vì dễ lộ field mới khi schema mở rộng. Sử dụng DTO/mapper allowlist theo quyền, và test khi thêm cột mới.

## 11. Phân trang, cursor và tìm kiếm cũng phải tenant-scoped

Trong một API danh sách, lỗi thường xuất hiện khi developer tối ưu paging mà quên **điều kiện tenant ở mỗi lần fetch**.

~~~sql
SELECT created_at, order_id, status, amount_minor
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
~~~

Ứng dụng phải kiểm tra quyền với **tenant và customer** trước khi bind. Không truy vấn global rồi lọc data trong Java vì row không thuộc quyền có thể đã đi qua logs, caches, metrics hoặc serializer.

### 11.1. Paging state không phải authorization token

Cassandra/Java Driver cung cấp paging state để tiếp tục cùng một query. Paging state **không chứng minh** caller có quyền tiếp tục đọc một tenant.

~~~text
Page 1:
  tenant A, customer X, query A
  -> server trả cursor/paging-state

Page 2:
  caller thay tenant B hoặc customer Y
  -> không được reuse paging-state của query A
~~~

Mỗi lần request page mới phải:

1. Xác thực principal và quyền tenant hiện hành.
2. Ràng buộc query theo tenant/customer/filter **được phép**.
3. Kiểm tra cursor gắn với cùng tenant, actor/scope, query shape, sort và schema version.
4. Áp dụng giới hạn page size, số partitions/buckets được quét và thời gian request.
5. Không coi cursor cũ là bằng chứng permission vẫn còn hiệu lực sau khi membership bị thu hồi.

Một cursor opaque nên có **integrity protection** (ký HMAC hoặc server-side state), expiry và scope/hash của query. Nếu nó chứa bí mật hoặc PII, cần mã hóa hoặc giữ dữ liệu ở server. Không dùng CQL `OFFSET` để nhảy trang ngẫu nhiên, và không dùng page size như một giới hạn tổng số row toàn query.

### 11.2. Đọc qua nhiều shards/buckets

Nếu `orders_by_tenant_month_shard` có nhiều shards, phải query từng shard thuộc tenant **được ủy quyền**, merge theo `(created_at,order_id)`, giữ tiến độ của từng shard và giới hạn fan-out. Không tạo cursor chỉ chứa `lastOrderId` rồi hy vọng Cassandra tự xử lý global ordering.

### 11.3. Search index cũng cần tenant filter

Nếu hệ thống dùng search engine bên ngoài, filter tenant phải có ngay **trong query search**, không chỉ lọc các hits sau khi lấy top K. Mọi hit còn phải qua policy resource khi scope phức tạp. Secondary index SAI/2i của Cassandra cũng không tự là cơ chế row-level authorization.

## 12. Cache key, idempotency key và file export

### 12.1. Cẩn thận cache xuyên tenant

Phản mẫu:

~~~text
cache key = orderId
~~~

Nếu Tenant A và B có cùng orderId (hoặc DTO đã được cache trước khi check quyền), Tenant B có thể nhận dữ liệu của A mà không gọi Cassandra. Key đúng hơn:

~~~text
order-details:v2:{tenantId}:{orderId}:{policyVersion}
~~~

Tuy nhiên tenant trong cache key **không thay kiểm tra quyền resource**. Với order chỉ nhân viên phụ trách được xem, có thể cache raw tenant-scoped data bên trong service tin cậy và áp policy mỗi lần, hoặc cache kết quả theo actor/scope được quản lý cẩn thận.

Kiểm tra thêm:

- Caches được invalidated khi user bị thu hồi quyền hoặc data thay đổi.
- Không trộn public summary và private finance view vào cùng key.
- Mọi cache lookup lấy `tenantId` từ authorized context.
- Background preload không lấy tenant tùy ý từ untrusted message.
- Không log PII trong cache keys nếu policy cấm.
- Rate limit/quota cũng nên scope theo tenant để tránh noisy-neighbor.

### 12.2. Idempotency key phải có tenant/operation scope

Một key client đặt như `request-123` có thể tồn tại ở nhiều tenant. Nếu dedup store chỉ dùng key đó, retry tenant B có thể nhận response của tenant A. Dùng khóa mang ngữ cảnh:

~~~text
(tenantId, operationType, idempotencyKey)
~~~

Cần kiểm tra cùng payload (hoặc payload hash), principal/scope theo contract, TTL và lifecycle. Tương tự event ID nguồn không global unique thì phải scope theo tenant/producer.

### 12.3. Xuất hóa đơn và object storage

Trước khi tạo pre-signed URL download:

1. Xác thực caller và tenant đã chọn.
2. Xác minh caller có quyền `invoice:download` trên invoice cụ thể.
3. Tra file key **từ metadata đã tenant-scoped**, không nhận raw storage key do caller tự chọn.
4. Tạo URL thời hạn ngắn và quyền tối thiểu; audit nếu cần.
5. Không để export cache hoặc object storage URL trở thành đường đi vòng qua authorization Cassandra.

## 13. Background jobs, events và service identity

Không phải mọi write đều đến từ HTTP Controller. Scheduler, message consumer, data migration và admin tools thường dùng database account mạnh hơn user.

### 13.1. Event payload không tự có quyền

~~~json
{
  "eventId": "11111111-1111-4111-8111-111111111111",
  "tenantId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "orderId": "22222222-2222-4222-8222-222222222222",
  "type": "OrderPaid",
  "schemaVersion": 2
}
~~~

Consumer phải xác minh **producer identity và nguồn event**, producer có được viết cho tenant này hay không, event ID/nguồn dữ liệu có hợp lệ không, order/customer có cùng tenant không. `tenantId` trong untrusted message là một **claim chưa được kiểm tra**, không phải authority.

### 13.2. Đừng dựa vào ThreadLocal/MDC làm nguồn tenant của job

Phản mẫu:

~~~java
CompletableFuture.runAsync(() -> repository.save(order));
~~~

Nếu `order` chứa tenant lấy từ request body hoặc code dùng fallback “tenant mặc định” khi thread mới không có security context, có thể ghi sai. Đường an toàn hơn truyền explicit context/command được authorize:

~~~java
TenantContext authorized = context;
VerifiedOrderCommand command = verifiedCommand;

taskExecutor.execute(() ->
    orderWriter.writeForTenant(
        authorized.tenantId(), command
    )
);
~~~

Ví dụ giả định `VerifiedOrderCommand` đã được validate trước khi schedule và job còn quyền thực thi theo workflow. Với delayed jobs kéo dài, có thể phải **kiểm tra lại** membership/service authorization tại thời điểm chạy. `ThreadLocal`/MDC chỉ thích hợp logging/correlation nếu được quản lý, không thay access-control context.

### 13.3. Job toàn hệ thống phải có quyền riêng

Một billing export chạy qua nhiều tenant cần:

- Service identity có quyền rõ và được audit.
- Danh sách tenants từ nguồn tin cậy.
- Mỗi iteration có scope tenant riêng; không có fallback `tenant=null` nghĩa là “all”.
- Giới hạn throughput/bucket theo tenant, tránh ảnh hưởng tenant khác.
- Có kế hoạch retry/idempotency và kết quả đối soát.
- Không thêm `skipTenantCheck=true` vào public-facing service; dùng interface đặc quyền riêng.

## 14. Reactive Spring Data Cassandra và Reactor Context

Trong reactive pipeline, logic có thể đổi thread khi subscribe/execute. **Không** dùng một `ThreadLocal tenantId` static rồi hy vọng nó theo suốt `Mono`/`Flux`.

### 14.1. Reactive repository

~~~java
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;

public interface ReactiveOrderRepository
        extends ReactiveCassandraRepository<OrderByTenantId, OrderKey> {
}
~~~

Service tenant-aware:

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;

public Mono<OrderDto> findAuthorizedReactive(
        TenantContext ctx, UUID orderId) {

    if (!ctx.hasPermission("orders:read")) {
        return Mono.error(
            new SecurityException("Access denied"));
    }

    OrderKey key = new OrderKey(ctx.tenantId(), orderId);

    return reactiveRepository.findById(key)
        .filter(order -> orderPolicy.canRead(ctx, order))
        .map(OrderDto::fromEntity);
}
~~~

`reactiveRepository` và `orderPolicy` là dependencies đã inject. `orderPolicy.canRead` ở đây chỉ phù hợp nếu **không blocking**; khi cần gọi DB/HTTP để kiểm tra policy, dùng API reactive rồi `flatMap` thay vì chặn event loop.

### 14.2. Reactor Context chỉ truyền dữ liệu, không cấp quyền

`Reactor Context` có thể mang `TenantContext` xuyên async boundaries, nhưng object được đưa vào đó phải đến từ bước authenticate/authorize; giá trị client tự gửi không trở thành tin cậy vì đã được lưu trong Reactor Context.

~~~text
Verified principal + requested tenant
  -> authorization service
  -> TenantContext đã xác minh
  -> reactive query with WHERE tenant_id = ctx.tenantId()
  -> resource policy -> DTO
~~~

Nếu context không có, phải **fail closed**, không fallback sang query bỏ `tenant_id`. Reactive backpressure/paging không thực thi authorization: query không tenant-scoped được `filter` ở cuối stream vẫn có nguy cơ fetch/cache dữ liệu không được phép.

## 15. Cassandra roles/grants: bảo vệ keyspace/table, không mặc định theo partition

Cassandra có cơ chế authentication và database authorization theo roles/permissions khi được cấu hình. Ví dụ:

~~~sql
GRANT SELECT
ON TABLE orders_by_tenant_id
TO app_orders_reader;
~~~

Role này có thể đọc bảng theo quyền CQL, nhưng Cassandra không tự kiểm tra mỗi row có `tenant_id` nào phù hợp với JWT user. Nếu mọi tenants dùng một connection và database role chung, Cassandra chỉ biết **identity của service**, không biết người gọi HTTP Alice hay Bob.

### 15.1. Least privilege

- Reader role chỉ SELECT trên bảng cần đọc.
- Writer role chỉ có quyền ghi trên bảng cần ghi.
- Migration/DDL dùng role riêng, không dùng superuser cho runtime.
- Credentials/secrets không hardcode trong repo/log.
- Dùng TLS phù hợp topology và cơ chế encryption-at-rest nếu môi trường hỗ trợ/yêu cầu.
- Kiểm toán backup, snapshots, object storage, audit logs và export.
- Giới hạn truy cập trực tiếp cqlsh/admin, vì các đường này có thể bypass mọi tenant filter của ứng dụng.

### 15.2. Khi cần isolation mạnh hơn

Một số yêu cầu compliance, residency hoặc khách hàng lớn có thể cần **keyspace-per-tenant** hoặc **cluster riêng**. Đánh đổi là nhiều schema objects, migrations, connection/routing/backup/repair phức tạp hơn.

Nếu chọn dynamic keyspace/table identifiers, **không** nối tên raw từ request. Identifiers không phải ordinary CQL value bind markers; cần mapping/allowlist giữa authorized tenant ID với identifiers đã cấu hình. Dù keyspace riêng, application vẫn cần authorization trên resource/operation.

### 15.3. Tài khoản service không đồng nghĩa global business admin

Một Cassandra database role có thể được cấp `SELECT` trên nhiều bảng để phục vụ runtime. Nó **không có nghĩa** mọi HTTP request được phép xem mọi tenant. Khi làm threat modeling, phân biệt credential/permissions của service với business authority của end user.


## 16. Vòng đời tenant: onboarding, thu hồi quyền và xóa dữ liệu

**Onboarding** gồm cấp tenant ID duy nhất, owner, memberships/roles, data retention, quota, cache namespace, event isolation và kiểm thử với tenant khác. Không tái dùng tenant ID đã xóa; tenant của entity phải được tạo từ authorized context.

Khi user bị thu hồi membership, access token/cached permissions có thể còn hiệu lực ngắn hạn. Phải định nghĩa thời hạn token, refresh/revocation, membership cache TTL và cách xử lý background jobs đang chạy. Cassandra không tự thu hồi quyền row chỉ vì membership trong ứng dụng bị thay đổi.

### 16.1. Offboarding không phải DELETE theo một thành phần khóa

Với khóa `PRIMARY KEY ((tenant_id, order_id))`:

~~~sql
-- Thiếu thành phần order_id nên không xóa được mọi order của tenant:
DELETE FROM orders_by_tenant_id WHERE tenant_id = ?;
~~~

Một quy trình xóa tenant cần:

1. Chặn ghi mới của tenant trước cleanup.
2. Inventory mọi bảng, denormalized read models, events, caches, search indexes, exports, snapshots và backups.
3. Liệt kê đầy đủ order IDs, buckets/shards theo các access patterns hợp lệ; không dùng `ALLOW FILTERING` global trong request path.
4. Xóa có rate limit, checkpoint/idempotency và đo tombstones/compaction/repair.
5. Xác minh API không trả dữ liệu; xử lý backup retention và quyền truy cập export theo policy.
6. Không tuyên bố mọi bản sao vật lý đã mất ngay khi CQL DELETE trả success.

Nếu yêu cầu isolation/offboarding mạnh, cân nhắc keyspace/cluster riêng từ thiết kế ban đầu thay vì sửa trong sự cố.

## 17. Consistency, LWT và toàn vẹn tham chiếu không thay phân quyền

`LOCAL_QUORUM` chỉ điều khiển replica acknowledgements. `IF NOT EXISTS` thực hiện điều kiện dữ liệu tại primary key; cả hai **không kiểm tra tenant membership**.

~~~sql
INSERT INTO orders_by_tenant_id (tenant_id, order_id, status)
VALUES (?, ?, 'CREATED')
IF NOT EXISTS;
~~~

Trước statement, ứng dụng vẫn phải xác thực principal và kiểm tra quyền `orders:write` của tenant. Khi timeout sau LWT, outcome có thể chưa rõ; retry và readback phải giữ tenant scope và request ID, không chuyển sang global lookup.

Khi ghi một đơn vào `orders_by_tenant_id` và `orders_by_customer_month`, hai bảng có thể lệch tạm thời nếu một mutation thất bại; Cassandra không tự có transaction ACID toàn workflow. Dùng event/outbox, idempotent projection và reconciliation thích hợp.

Cassandra cũng không tạo foreign-key constraint để kiểm tra một customer có cùng tenant với order. Tại service:

~~~text
order.tenantId == authorizedContext.tenantId
customer.tenantId == authorizedContext.tenantId
assignee.tenantId == authorizedContext.tenantId (nếu áp dụng)
invoice.tenantId == authorizedContext.tenantId (nếu áp dụng)
~~~

Không chỉ xác minh customer ID tồn tại toàn cụm; phải tra cứu **trong tenant được ủy quyền**.

## 18. Migration từ bảng cũ chỉ có order ID

Giả sử trước đây có:

~~~sql
CREATE TABLE orders_by_id_old (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    status text
);
~~~

Chỉ thêm cột `tenant_id` bình thường không thay được cấu trúc primary key hoặc ngăn old repository lookup xuyên tenant. Cần bảng mới cùng migration có kiểm soát:

1. Inventory và **xác minh tenant ownership của từng record cũ**.
2. Tạo bảng với khóa `((tenant_id, order_id))` và các read models theo truy vấn.
3. Cập nhật write path để dùng authorized tenant context.
4. Backfill với checkpoint, idempotency và giới hạn tốc độ/độ ảnh hưởng compaction.
5. Nếu dual-write, có reconciliation và event IDs.
6. Nếu dual-read, chỉ fallback old data khi có **ownership mapping đáng tin**, không phải tra `findById(orderId)` tùy tiện.
7. Test hai tenants trùng business ID, CRUD, cache và cursor.
8. Cutover, vô hiệu hóa đường global access cũ, xử lý retention/backup và giữ rollback không mở lại lỗ hổng.

### 18.1. Sai lầm khi fallback

~~~text
newRepo.find(tenantA, O123) -> not found
oldRepo.find(O123) -> found
return oldRecord ngay -> có thể là row của tenantB
~~~

Khi không chứng minh được tenant owner, **fail closed**; đưa record vào remediation queue, không trả dữ liệu rồi mới kiểm tra quyền sau.

## 19. Threat model và ma trận kiểm thử cross-tenant

| Trường hợp | Rủi ro | Kiểm soát |
| --- | --- | --- |
| User A sửa tenant trong URL thành B | BOLA/IDOR | Membership + permission validation |
| Body chứa tenant B nhưng path A | Ghi sai partition | Bind tenant từ authorized context |
| User trong A đoán orderId của đồng nghiệp | BOLA nội bộ | Resource ownership/ABAC |
| Cache key chỉ có orderId | Cached data xuyên tenant | Cache tenant/scope aware |
| Cursor tenant A dùng lại ở B | Trộn dữ liệu pages | Signed/scoped cursor + reauthorization |
| Broker event tenant B do producer A gửi | Mutation sai tenant | Producer scope check |
| ThreadLocal bị mất ở reactive job | Query default/global | Explicit verified context; fail closed |
| Search index không filter tenant | Lộ search hits | Filter trước retrieval |
| Global admin không audit | Bulk data exposure | Privileged workflow riêng |
| JWT cũ sau khi user bị revoke | Stale authorization | Expiry/cache freshness/revocation |
| Migration fallback global | Lộ order cũ | Proven owner mapping |
| Cassandra role có quyền SELECT bảng | Bypass business policy khi đọc trực tiếp | Least privilege và access audit |

### 19.1. Fixture hai tenants cùng order ID

~~~text
Tenant A: O123 => PAID
Tenant B: O123 => CANCELLED

Alice: member Tenant A, orders:read
Carol: member Tenant B, orders:read
Bob: member Tenant A nhưng không được đọc O123
~~~

Các tests cần chứng minh:

1. Alice GET A/O123 → `PAID`, không phải `CANCELLED`.
2. Alice GET B/O123 → denied, không có payload Tenant B.
3. Carol GET B/O123 → `CANCELLED`.
4. Carol GET A/O123 → denied.
5. Bob GET A/O123 → denied theo resource policy.
6. Alice PATCH A nhưng body B → không ghi B.
7. DELETE A không ảnh hưởng B.
8. Cache sau Alice không bị trả sai cho Carol.
9. Cursor của A không được dùng trên B.
10. Job/event không có producer authorization bị chặn.
11. Membership bị revoke làm request mới không còn quyền theo freshness SLA.
12. Migration fallback chỉ được phép khi owner đã xác minh.
13. Export/finance views không lộ fields ngoài scope.

### 19.2. Ví dụ kiểm thử MockMvc (skeleton)

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;

class OrderIsolationWebTest {
    @Test
    void cannotReadOtherTenantEvenKnowingOrderId() throws Exception {
        // Cần inject mockMvc, tenantB, orderId, JWT test helper.
        mockMvc.perform(
            get("/tenants/{tenantId}/orders/{orderId}", tenantB, orderId)
                .with(jwtForAliceOfTenantA())
        ).andExpect(status().isForbidden());
    }
}
~~~

Đây là skeleton chưa có fixture, không phải test đã chạy. Nếu chính sách API chủ động dùng 404 để che sự tồn tại resource, đổi assertion tương ứng và vẫn khẳng định không trả payload. Kiểm tra cả data write side effects, không chỉ status code.

### 19.3. DAO test theo composite key

~~~text
Given: authorized ctx tenantA, order O123
When: repository.findById(...)
Then: key == (tenantA, O123)

Given: ctx tenantA, request body tenantB
When: create order
Then: reject request hoặc persist key dùng tenantA

Given: ctx tenantA, customer thuộc tenantB
When: create order
Then: reject cross-tenant reference
~~~

Không chạy các bài thử xóa dữ liệu hoặc truy cập trái phép trên production; dùng keyspace fixtures được cô lập và policy thực của hệ thống test.

## 20. Audit, metrics và xử lý sự cố rò rỉ

Một audit event có thể ghi:

~~~json
{
  "requestId": "trace-123",
  "actorId": "user-456",
  "requestedTenantId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "authorizedTenantId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "action": "orders:read",
  "resourceType": "order",
  "decision": "ALLOW",
  "policyVersion": "v3"
}
~~~

Log phải tuân quy tắc privacy: không log full JWT, credentials, PII hoặc object payload không cần thiết. Phân biệt tenant **được yêu cầu** với tenant **đã authorize** để điều tra.

Metrics nên gồm deny rate, mismatched path/body, cursor scope failures, cached view invalidation, background messages thiếu tenant, privileged exports, foreign-reference validation failures, per-tenant QPS và p95/p99/hot partitions.

### 20.1. Runbook incident

1. Chặn đường truy cập bị lỗi qua feature flag/gateway hoặc policy thích hợp.
2. Bảo toàn audit/trace có kiểm soát.
3. Xác định tenants, actor, resources, thời gian, operations và export scope.
4. Kiểm tra authN/authZ, query bindings, cache keys, cursors, job/event pipelines và search.
5. Nếu có ghi sai, ngăn writer và đối soát dữ liệu trước khi sửa/xóa.
6. Sửa ở authorization boundary **và** DAO/query layer, không chỉ ẩn UI.
7. Chạy regression matrix hai tenants trùng business ID.
8. Xử lý thông báo/pháp lý theo chính sách tổ chức và quy định áp dụng.
9. Giám sát sau rollout, cập nhật threat model và code review checklist.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Có `tenant_id` trong partition key thì Cassandra tự làm row-level authorization chưa?

*Đáp án:* Chưa. Tenant key giúp lookup và phân nhóm; ứng dụng kiểm tra quyền.

**Câu 2.** `PRIMARY KEY ((tenant_id,order_id))` khác `PRIMARY KEY ((tenant_id),order_id)` thế nào?

*Gợi ý:* Dạng sau gom orders tenant trong một partition với clustering theo orderId.

**Câu 3.** Vì sao tenantId trong request body không phải authority?

*Gợi ý:* Caller có thể đổi nó mà không có quyền tenant đó.

**Câu 4.** Người dùng thuộc Tenant A có tự được đọc mọi order A không?

*Đáp án:* Không nhất thiết; còn role và resource ownership.

**Câu 5.** Prepared statement giúp chống injection, có tự kiểm tra tenant không?

*Đáp án:* Không.

**Câu 6.** Vì sao global `findById(orderId)` dễ gây BOLA?

*Gợi ý:* Không buộc tenant scope hoặc owner permission.

**Câu 7.** Paging state từ tenant A có thể làm access token tenant B không?

*Đáp án:* Không; cursor cần kiểm tra scope và quyền mỗi request.

**Câu 8.** Cache key chỉ gồm orderId nguy hiểm gì?

*Gợi ý:* Có thể trả DTO của tenant khác.

**Câu 9.** Với reactive pipeline, có nên phụ thuộc ThreadLocal tenant không?

*Đáp án:* Không; dùng explicit context hoặc Reactor Context đã authorize, fail closed.

**Câu 10.** `GRANT SELECT ON TABLE` có tự giới hạn rows theo tenant không?

*Đáp án:* Không.

**Câu 11.** Offboarding khi partition key là `(tenantId,orderId)` cần gì?

*Gợi ý:* Enumeration các keys/read models và cleanup có kiểm soát.

**Câu 12.** `LOCAL_QUORUM` hoặc `IF NOT EXISTS` có thay authorization không?

*Đáp án:* Không, đó là consistency/data-conditional mechanisms.

**Câu 13.** Vì sao global fallback khi migration nguy hiểm?

*Gợi ý:* Có thể trả record mà owner chưa được xác minh.

**Câu 14.** Event chứa tenantId từ broker đã tự được phép ghi chưa?

*Đáp án:* Chưa; phải xác minh producer identity và quyền.

## 22. Checklist production

- **AuthN:** Verify token/identity, issuer/audience/expiry, service credentials.
- **Tenant scope:** Membership/permission trước CQL, không tin path/header/body độc lập.
- **Resource policy:** RBAC/ABAC, ownership và field-level access.
- **Partition keys:** Tenant trong khóa, tránh partition tenant-only quá lớn.
- **Read models:** Tenant-scoped composite keys, buckets/shards đúng access patterns.
- **Data access:** SELECT/INSERT/UPDATE/DELETE/CAS có tenant từ authorized context.
- **Spring Data:** Composite key class đúng ID type; raw repositories không mở công khai.
- **Cache/search:** Tenant-aware keys, filter trước retrieval, cache invalidation theo quyền.
- **Cursor:** Query/tenant/actor/sort binding và tái validate.
- **Async/reactive:** Không fallback global khi context mất, service identity hợp lệ.
- **References:** Customer, assignee, invoice, file thuộc tenant trước khi liên kết.
- **DB roles:** Least privilege, không runtime superuser, GRANT không thay row policy.
- **Export:** Permission riêng, giới hạn tải, storage IAM và audit.
- **LWT/CL:** Không coi consistency hoặc IF NOT EXISTS là quyền truy cập.
- **Offboarding:** Inventory mọi dữ liệu và copies, retention/repair/compaction plan.
- **Migration:** Proven ownership, dual-read có kiểm soát, không fallback global.
- **Testing:** Trùng order ID khác tenant; CRUD/cache/cursor/events/revoke/export.
- **Monitoring:** Cross-tenant deny rates, admin access, per-tenant QPS và p99.
- **QA:** Bài STEP_4; vòng content QA học thuật diễn ra sau trong workflow.

## Tài liệu tham khảo

- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/): partition và clustering key.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): truy vấn, khóa và conditional writes.
- [Apache Cassandra — Security](https://cassandra.apache.org/doc/latest/cassandra/operating/security.html): database authentication/authorization.
- [Spring Data Cassandra Reference](https://docs.spring.io/spring-data/cassandra/reference/): composite key mapping, repository, CassandraTemplate, reactive.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): JWT Resource Server, method security và reactive security.
- [OWASP API Security — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): kiểm soát quyền trên đối tượng.
- [Apache Cassandra Java Driver](https://apache.github.io/cassandra-java-driver/): prepared CQL, paging và driver config.

## Kết luận

**Tenant trong partition key là quyết định thiết kế quan trọng cho ứng dụng Cassandra đa tenant**: query có thể giới hạn dữ liệu theo tenant ngay từ khóa, tránh nhiều global lookups và hỗ trợ query-driven design. Nhưng `tenant_id` **không tự thực thi xác thực hoặc phân quyền**. Nếu caller được tùy ý bind tenant ID, hoặc service không kiểm tra quyền trên resource, dữ liệu vẫn có thể bị đọc/ghi xuyên tenant.

Với **SPRING_DATA_CASSANDRA**, hãy kết hợp composite tenant keys, `TenantContext` được xác minh và ủy quyền, Spring Security, repository/`CassandraTemplate`/prepared CQL và resource-level policy. Bảo vệ cùng scope trong cache, cursor, search, job nền, reactive pipelines, exports, migration và offboarding. Database roles/GRANT hỗ trợ least-privilege trên keyspace/table nhưng không thay business authorization. **Chỉ khi partition design, quyền truy cập, adversarial tests và monitoring được xây dựng đồng bộ**, ranh giới dữ liệu giữa các tenant mới đáng tin cậy trong Cassandra phân tán.






