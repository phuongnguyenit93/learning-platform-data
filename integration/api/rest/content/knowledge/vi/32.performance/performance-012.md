# Kiểm chứng tối ưu không làm sai ngữ nghĩa, bảo mật hoặc tính nhất quán

## 1. API nhanh hơn nhưng sai thì không phải tối ưu thành công

Một REST API đang trả đơn hàng trong 180 ms (p95). Nhóm phát triển thêm Redis cache, projection chỉ lấy vài cột và đọc từ replica. p95 giảm xuống 35 ms; dashboard hiệu năng xanh. Nhưng một người dùng khác tenant nhận lại đơn đã cache, một PATCH trả thành công rồi GET lại thấy phiên bản cũ, hoặc endpoint `GET /v1/orders/{id}` vô tình trả `200` cho order không thuộc quyền thay vì `404` trung tính. **Thời gian đáp ứng tốt không bù được sai hợp đồng, rò dữ liệu hay mất nhất quán nghiệp vụ.**

~~~mermaid
flowchart LR
    A["Tối ưu: cache / DB / async / batching"] --> B["Đo p95, throughput, resource"]
    A --> C["So khớp HTTP contract"]
    A --> D["Kiểm object/field authorization"]
    A --> E["Kiểm phiên bản, transaction, replay"]
    B --> F{"Tất cả tiêu chí đạt?"}
    C --> F
    D --> F
    E --> F
    F -->|Có| G["Canary → rollout theo ngân sách lỗi"]
    F -->|Không| H["Rollback / sửa tối ưu"]
~~~

Bài thuộc chương **Hiệu năng** của module **INTEGRATION_API_REST**. Người học đã tiếp cận resource/URI, phương thức và mã trạng thái HTTP, phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử với Java/Spring hoặc công nghệ tương đương. Trọng tâm ở đây là **chứng minh thay đổi tối ưu vẫn giữ những hành vi bắt buộc**, không chỉ đo RPS.

**Sau bài học**, bạn có thể lập danh mục bất biến trước khi tối ưu, thiết kế thử nghiệm so sánh baseline với phiên bản mới, kiểm xác thực/phân quyền và độ mới dữ liệu qua cache/replica, kiểm transaction và retry dưới concurrency, thực hiện contract/integration/load test trên Spring Boot và ra quyết định rollout có thể đảo ngược.

## 2. Định nghĩa tối ưu bằng hai trục: hiệu năng và tính đúng

Mỗi thay đổi cần **hai nhóm điều kiện chấp nhận**:

| Trục | Ví dụ tiêu chí | Không được suy nhầm |
|---|---|---|
| **Hiệu năng** | p95 latency giảm, p99 không xấu đi quá budget, throughput tăng, CPU/DB load giảm | RPS cao không chứng minh response đúng |
| **HTTP semantics** | Status, body, headers và side effect giữ hợp đồng theo từng operation | `200` có JSON không đồng nghĩa thành công nghiệp vụ |
| **Authorization** | Đúng principal/tenant/resource/field, kể cả cache hit và batch | Cache key theo URL không đủ cho dữ liệu private |
| **Consistency** | Commit/ETag/precondition/RYW/idempotency không đổi ngoài SLA đã công bố | Replica stale có thể nhanh hơn nhưng trả sai |
| **Reliability** | Timeout, cancellation, retry, fallback, dependency failure có giới hạn | p50 tốt có thể che p99/duplicate side effects |
| **Security/PII** | Không phản chiếu token, header hoặc dữ liệu bị cấm qua response/log/metrics | “Đã che ở frontend” không sửa response thừa |

Một công thức quyết định hữu ích:

\[
\text{Chấp nhận tối ưu} =
\text{đạt ngưỡng hiệu năng}
\;\land\;
\text{không vi phạm bất biến bắt buộc}.
\]

Đừng gộp thành một điểm số trung bình mà “thưởng” 50 ms để đổi lấy một lỗi bảo mật hiếm. Những tiêu chí như **không rò dữ liệu tenant**, **không charge hai lần**, **không mất cập nhật**, **không dùng token sai audience** phải là **release gate cứng**.

### 2.1. Viết danh mục bất biến trước khi thay mã

Ví dụ cho `GET /v1/orders/{id}` và `PATCH /v1/orders/{id}`:

| Mã | Bất biến | Cách quan sát |
|---|---|---|
| S1 | GET thành công chỉ trả trường public đã công bố | JSON schema/allowlist, snapshot contract |
| S2 | User A không thấy order B kể cả đã từng cache | HTTP 404/403 theo policy, không lộ body/ETag |
| S3 | Invalid/expired token không mở cache/private resource | 401, `WWW-Authenticate` đúng; service không bypass security |
| S4 | `If-Match` lỗi không ghi, trả 412 | Version/row count trước–sau |
| S5 | PATCH thành công có version mới; GET theo hợp đồng RYW không đọc phiên bản thấp hơn | ETag/version floor, primary/replica fault test |
| S6 | Retry POST cùng key/intent không tạo side effect thứ hai | Đếm order, outbox, provider events |
| S7 | Pagination giữ đủ phạm vi tenant và thứ tự ổn định | So tập phần tử, cursor/next link, count |
| S8 | Cache và HTTP 304 không trả bản cũ khi quyền/representation đổi | ETag, `Vary`, cache-key test |
| S9 | Error body không chứa stack trace/SQL/PII | Problem Details, sentinel test |
| S10 | Khi dependency lỗi, fallback không biến lỗi thành dữ liệu sai | Timeout/deadline, fail-safe response |

Đừng xác định bất biến bằng “đúng như hiện tại” nếu hệ thống hiện có lỗi. Cần lấy **OpenAPI, business rules, privacy/security policy và các quyết định nhất quán** làm nguồn chuẩn; baseline cũ là bằng chứng thực nghiệm, **không phải thẩm quyền tuyệt đối**.

### 2.2. Phân loại thay đổi theo độ nguy hiểm

- **Chỉ thay cách thực thi, giữ cùng outcome**: giảm số query, projection đúng field, cải thiện index, connection reuse. Vẫn cần kiểm behavior dưới concurrency.
- **Thay nơi hoặc thời điểm quan sát**: cache, CDN, replica, denormalized read model, batching. Cần định nghĩa freshness, tenant visibility và invalidation.
- **Thay ranh giới side effect**: async `202`, outbox, retry, bulk update, queue. Có thể là **thay đổi hợp đồng**, không còn “tối ưu trong suốt”.
- **Thay representation hoặc protocol**: nén, streaming, ETag, pagination, serializer. Cần giữ Content-Type/status/headers/shape; nếu thay semantics, version và migration contract thay vì gọi là tối ưu không đổi hành vi.

## 3. Kiểm HTTP contract trước và sau tối ưu

### 3.1. Một GET có nhiều kết quả hợp lệ, không phải tất cả là 200

~~~http
GET /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <redacted-access-token>
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v7"
Cache-Control: private, no-cache

{"id":"o-42","status":"PAID","totalMinorUnits":125000}
~~~

Khi không có quyền nhìn thấy resource, theo policy che giấu sự tồn tại:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"https://api.example.com/problems/not-visible",
 "title":"Resource not found","status":404,"code":"RESOURCE_NOT_FOUND"}
~~~

Khi client có cached representation hợp lệ và GET có precondition:

~~~http
GET /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <redacted-access-token>
If-None-Match: "order-v7"

HTTP/1.1 304 Not Modified
ETag: "order-v7"
Cache-Control: private, no-cache
~~~

Trong ví dụ, `private, no-cache` cho phép cache riêng lưu representation nhưng **phải revalidate trước khi dùng lại**; 304 chỉ có ích nếu client có bản lưu phù hợp và vẫn được phép xem. Với dữ liệu nhạy cảm không được lưu, dùng `no-store` thay thế và **không kỳ vọng cache tái sử dụng body**. Luôn xét quyền, variant và freshness trước khi trả 304.

**Không đổi `404` thành `200 {"items":[]}` chỉ vì cache trả empty default**, không đổi `401` thành `500` do decoder JWT chậm và không deserialize JSON từ `204`/`304`. Các HTTP status 201/202/204/304/409/412/422/429/503 đều có ngữ nghĩa riêng và cần được kiểm theo operation.

### 3.2. Precondition và side effect trên PATCH

~~~http
PATCH /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <redacted-access-token>
If-Match: "order-v7"
Content-Type: application/merge-patch+json

{"deliveryNote":"Gọi trước khi giao"}

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v8"

{"id":"o-42","status":"PAID","deliveryNote":"Gọi trước khi giao"}
~~~

Nếu ETag đã cũ, phải trả **412 Precondition Failed** và **không commit cập nhật**. Một bản tối ưu dùng `UPDATE orders SET ... WHERE id=?` mà bỏ `version=?` có thể nhanh hơn nhưng gây **lost update**. Nếu dùng optimistic concurrency, câu SQL phải kèm version và phân biệt “0 hàng vì stale version” với “0 hàng vì ngoài tenant” theo policy bảo mật.

**ETag là validator của representation**, không phải quyền truy cập. ETag mạnh/yếu có ngữ nghĩa so sánh khác nhau; `If-Match` sử dụng **so sánh mạnh**. Nếu representation của customer khác support view, không mặc định một entity version đủ làm strong ETag hợp lệ cho **mọi representation**. Nếu có content encoding/projection/locale khác nhau, cần thiết kế validator/`Vary` theo các biến thể thực tế.

### 3.3. OpenAPI contract test, không chỉ JSON equals

So response ở mức:

1. Method/URI, status (không phải chỉ thuộc nhóm 2xx).
2. `Content-Type`, `Location`, `ETag`, `Cache-Control`, `Vary`, `Retry-After` khi có ngữ nghĩa.
3. JSON schema: field required/optional/nullable, enum, format, pagination cursor và Problem Details.
4. Quyền đọc/trường cho mỗi role, tenant và trạng thái tài nguyên.
5. Side effect: row được ghi, event được phát và idempotency outcome.

Nếu tối ưu cố ý thay từ `201` sang `202` vì xử lý async, đây là **thay contract công khai**: client phải biết poll operation; cập nhật OpenAPI/versioning/migration và test mới. Không đánh dấu thành công chỉ vì response nhanh hơn.

## 4. Tối ưu database: projection và N+1 không được bỏ mất phạm vi quyền

### 4.1. Phản mẫu: lấy ít cột nhưng quên điều kiện tenant

Giả sử endpoint trước đây gọi:

~~~java
OrderEntity order = repository
    .findByIdAndTenantIdAndCustomerId(
        id, actor.tenantId(), actor.customerId())
    .orElseThrow(ResourceNotVisibleException::new);
return mapper.toCustomerView(order);
~~~

Nhóm tối ưu nhận thấy entity kéo nhiều quan hệ lazy và đề xuất query projection:

~~~sql
-- SAI: nhanh hơn nhưng có thể đọc order của tenant khác
SELECT id, status, total_minor_units
FROM orders
WHERE id = :orderId;
~~~

Query nhanh hơn do đọc ít cột, nhưng **đã bỏ object-level authorization**. Truy vấn đúng cho customer:

~~~sql
SELECT id, status, total_minor_units, currency, version
FROM orders
WHERE id = :orderId
  AND tenant_id = :trustedTenantId
  AND customer_id = :trustedCustomerId;
~~~

`trustedTenantId`/`trustedCustomerId` lấy từ principal/membership **đã xác minh**; không lấy `tenant_id` trong path/body làm bằng chứng quyền. Nếu role support được xem order khác customer, policy phải được biểu diễn riêng (assignment/role và field projection), **không xóa mọi predicate**. Với query có join ACL, đặt điều kiện rõ và test trường hợp một order có nhiều assignment để không nhân bản hàng.

### 4.2. Spring Data JPA projection có ranh giới public rõ

~~~java
public record CustomerOrderView(
    UUID id, String status,
    long totalMinorUnits, String currency, long version
) {}

public interface OrderReadRepository extends JpaRepository<OrderEntity, UUID> {
    @Query("""
        select new com.example.api.CustomerOrderView(
            o.id, o.status, o.totalMinorUnits, o.currency, o.version)
        from OrderEntity o
        where o.id = :id
          and o.tenantId = :tenantId
          and o.customerId = :customerId
        """)
    Optional<CustomerOrderView> findCustomerView(
        UUID id, UUID tenantId, UUID customerId);
}

@Service
class OrderQueryService {
    private final OrderReadRepository repo;

    OrderQueryService(OrderReadRepository repo) {
        this.repo = repo;
    }

    @Transactional(readOnly = true)
    CustomerOrderView getVisible(Actor actor, UUID id) {
        return repo.findCustomerView(
            id, actor.tenantId(), actor.customerId())
            .orElseThrow(ResourceNotVisibleException::new);
    }
}
~~~

Mã dùng **Java 17+, Spring Boot 3.x/Spring Data JPA**; `Actor` là identity đã xác thực và các class import/package được lược. Constructor expression `new com.example.api.CustomerOrderView(...)` cần đúng package và **kiểu enum/status** của entity; trong ứng dụng thực nếu `o.status` là enum thì DTO nên nhận đúng enum hoặc map ở service. Đoạn ví dụ giả định `o.status` là String đã chuẩn hóa. Nếu status là enum, đổi constructor projection để nhận enum và chuyển sang mã public ổn định trước serialization.

Đây là tối ưu đúng hướng khi số bytes/entity hoặc lazy loading là bottleneck. Nhưng **đọc ít cột không chứng minh truy vấn đủ điều kiện quyền**; test multi-tenant phải áp trên repository/query thật. Nếu filter chỉ nằm ở controller, một async export hoặc batch service có thể gọi repository trực tiếp và bypass.

### 4.3. Giảm N+1 và batch mà không nhân đôi/mất phần tử

N+1 thường xảy ra khi lấy 20 orders rồi gọi thêm query cho items của từng order. Có thể dùng batch fetching, entity graph hoặc query theo tập ID đã scoped. Nhưng:

- `JOIN FETCH` trên collection cộng với pagination có thể làm page size không đúng, duplicate root hoặc paginate trong memory; cần chọn giải pháp theo ORM/SQL và test giới hạn page ở DB.
- Batch `WHERE id IN (...)` **không tự giữ thứ tự input**, cũng không bảo vệ tenant nếu thiếu predicate scoped.
- Một lần bulk query có thể về 19/20 hàng do order không thuộc quyền; **không được trả phần tử “gần đúng”** hoặc leak sự tồn tại của ID bị loại trong error.
- Không trả full entity từ cache/batch rồi cắt field ở frontend; projection ở server phải đúng **field-level authorization**.

Ví dụ cách tách page of IDs và fetch child rows:

~~~text
1) SELECT order.id FROM orders
   WHERE tenant_id=? AND customer_id=?
   ORDER BY created_at DESC, id DESC LIMIT ?;
2) SELECT ... FROM order_items
   WHERE tenant_id=? AND order_id IN (:scopedIds);
3) Lắp OrderView theo thứ tự IDs của bước 1.
~~~

**Vấn đề consistency:** giữa bước 1 và 2, order/items có thể thay đổi. Nếu contract yêu cầu snapshot nhất quán, dùng transaction isolation/snapshot phù hợp hoặc version check; nếu endpoint cho phép eventual/inconsistent list thì phải ghi rõ. Query plan giảm từ 21 queries xuống 2 **không đủ** nếu kết quả bị nhân đôi, thiếu item, sai tổng hay lộ tenant.

## 5. Cache/CDN: nhanh hơn nhưng có thể trả sai user, phiên bản và trạng thái

### 5.1. Cache key không chỉ là URI

Một phản mẫu thường thấy:

~~~java
@Cacheable(cacheNames = "orders", key = "#id")
public CustomerOrderView get(UUID id, Actor actor) { ... }
~~~

Nếu permission/projection khác nhau theo tenant, actor hoặc role, cache chỉ theo ID có thể gây **cross-tenant disclosure**. Tệ hơn, cache hit có thể khiến body từ user có quyền được trả **trước khi authorization theo object được đánh giá**.

Một lựa chọn đơn giản cho dữ liệu nhạy cảm là **không cache response private** và chỉ cache dữ liệu public/bất biến. Nếu cache thật sự cần thiết, thiết kế:

~~~text
cache key =
  (resource type, resource ID, trusted tenant ID,
   viewer/policy scope, representation variant, locale, policy version)

value = DTO đã lọc đúng quyền + version/expiry
~~~

Không tin `X-Tenant-ID` do client tự khai để tạo key; identity phải đến từ security context. **Kể cả cache key có actor**, quyền của actor có thể bị thu hồi sau khi entry được tạo; cần TTL ngắn, invalidation theo permission/version hoặc **recheck authorization trên cache hit** theo policy. Cache cả một `Page<OrderDto>` phải tính cả filter, sort, cursor, tenant và permission; chỉ key bằng `page=1` là sai.

### 5.2. Cache hit và miss phải cho kết quả quan sát tương đương

~~~mermaid
flowchart TD
    A["Request + principal đã xác thực"] --> B["Authorization & scope"]
    B -->|Không được phép| C["401/403/404 theo policy"]
    B -->|Được phép| D{"Cache hit phù hợp phiên bản/quyền?"}
    D -->|Có| E["DTO đúng contract"]
    D -->|Không| F["Read source phù hợp freshness"]
    F --> G["DTO + cache policy/invalidation"]
    G --> E
~~~

**Không coi cache hit là bước authorization.** Với dữ liệu công khai có chính sách khác, pipeline có thể cache ở edge trước app, nhưng phải có bằng chứng resource/variant là public và không chứa auth-specific data. Với API private, CDN không được bỏ qua `Authorization` hoặc phát response private giữa các principals.

### 5.3. Conditional requests và cache revalidation

Để client cache riêng có thể revalidate, API có thể chọn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "orders-customer-v7"
Cache-Control: private, no-cache
Vary: Accept-Language

{"id":"o-42","status":"PAID"}
~~~

`private` không cho shared cache lưu response theo ngữ nghĩa HTTP; `no-cache` **cho phép lưu nhưng phải revalidate trước khi sử dụng**. `no-store` nghiêm ngặt hơn: **không lưu response**. Với dữ liệu rất nhạy cảm, ưu tiên `private, no-store`; khi đó không nên kỳ vọng 304 mang lại lợi ích cache thông thường.

Một `304 Not Modified` có thể là đúng nếu **server đã xác minh quyền của caller, chọn đúng representation variant và so ETag trên trạng thái đủ mới**. Nếu server trả 304 vì replica đang giữ v7 trong khi primary có v8 mà contract hứa read-your-writes, đó là lỗi consistency. `ETag` cũng không thay `If-Match` trên write path: validator phải được xử lý tại điểm ghi để tránh lost update.

**HTTP cache không tự hiểu mọi giá trị custom consistency token**. Nếu route GET có `X-Read-After-Write` để yêu cầu minimum version, tránh caching hoặc làm rõ `Vary`/cache partition; không dựa vào `Vary: Authorization` như biện pháp bảo mật duy nhất khi CDN có cấu hình override.

### 5.4. Stampede, stale fallback và fail-open phải có giới hạn

Khi một entry hết hạn, nhiều requests có thể đồng loạt query DB. Cache stampede protection/single-flight giảm tải nhưng phải **khóa theo scoped cache key**. Stale-while-revalidate có thể phù hợp catalog public, nhưng có thể sai ở balance/quyền đã bị revoke/order vừa thanh toán. Hãy viết policy theo operation:

| Endpoint | Có thể stale? | Cache/fallback |
|---|---|---|
| `GET /v1/catalog` public | Có, trong SLA đã công bố | Shared cache, bounded staleness |
| `GET /v1/orders/{id}` private | Thường giới hạn chặt, có RYW nếu hứa | Private cache/invalidate/revalidate hoặc primary |
| `GET /v1/wallet/balance` | Không dùng stale cho quyết định chuyển tiền | Authoritative read/fail rõ |
| Quyền/ACL/token revocation | Phụ thuộc security SLA, thường nghiêm ngặt | Không fail-open từ cache cũ khi unknown |

Một fallback “nếu DB lỗi thì cứ trả cache bất kể cũ” có thể giảm `500` nhưng **tạo thành công giả**. Nếu không thể đáp ứng freshness/authorization, trả lỗi phù hợp và cảnh báo; không nói `200` chỉ để dashboard availability đẹp.

## 6. Replica và read model: độ trễ thấp nhưng không được đi lùi phiên bản

Đọc replica là tối ưu phổ biến cho GET nhiều, nhưng replication bất đồng bộ tạo **replica lag**. HTTP `201 Created` sau primary commit không tự có nghĩa GET ngay trên replica sẽ thấy resource. Tương tự PATCH trả ETag v8 nhưng GET tiếp theo từ replica v7 có thể trả JSON cũ hoặc `304` sai theo hợp đồng RYW.

~~~text
t0 primary: order o-42 version=7, status=CREATED
t1 PATCH If-Match "order-v7" -> COMMIT version=8, PAID
t2 API trả 200 / ETag "order-v8"
t3 GET route sang replica v7 -> CREATED (SAI nếu hứa RYW)
t4 replica apply version=8 -> PAID
~~~

### 6.1. Nói rõ mức nhất quán từng operation

| Use case | Hợp đồng gợi ý | Đường dữ liệu |
|---|---|---|
| Trang catalog ít thay đổi | Eventual hoặc bounded staleness | Replica/read cache |
| User vừa tạo/cập nhật order | Read-your-writes (RYW) | Primary, session affinity có floor, hoặc chờ replica đạt version |
| Kiểm tra tồn kho trước reserve | Tính đúng tại transaction ghi | Primary/authoritative state, concurrency control |
| Search index / dashboard | Eventual với checkpoint/SLO | Read model async, hiển thị độ mới khi cần |
| Quyền vừa bị thu hồi | Theo security revocation SLA | Nguồn quyền đủ mới, cache invalidation hoặc deny |

`@Transactional(readOnly=true)` của Spring **không tự làm query route sang replica**; route datasource cần cấu hình có chủ ý và test. Sticky app instance cũng không nhất thiết là sticky primary DB. Nếu dùng **consistency token** có minimum version, phải ký/giới hạn token theo actor–tenant–resource–expiry; **token không thay object authorization**.

### 6.2. Tối ưu có điều kiện: replica nếu đủ mới, fallback primary

~~~java
record VerifiedReadFloor(UUID tenantId, UUID orderId, long minVersion) {}

class VersionAwareOrderReader {
    private final OrderReadPort replica;
    private final OrderReadPort primary;

    OrderView read(Actor actor, UUID orderId, VerifiedReadFloor floor) {
        requireAuthorizedScope(actor, orderId, floor);
        Optional<OrderView> fromReplica =
            replica.findVisible(actor, orderId);
        if (fromReplica.isPresent()
                && fromReplica.get().version() >= floor.minVersion()) {
            return fromReplica.get();
        }
        OrderView authoritative = primary.findVisible(actor, orderId)
            .orElseThrow(ResourceNotVisibleException::new);
        if (authoritative.version() < floor.minVersion()) {
            throw new ConsistencyUnavailableException();
        }
        return authoritative;
    }
}
~~~

Đoạn này là **thuật toán minh họa**, không phải lớp đầy đủ có thể copy–compile: `OrderReadPort`, `Actor`, `OrderView`, `requireAuthorizedScope` và exceptions do ứng dụng định nghĩa, token `floor` **đã được verify** trước khi gọi. Phải kiểm cả **actor/subject quyền đọc hiện hành** ngoài tenant; mọi query từ replica và primary đều scoped. `minVersion` phải tăng đơn điệu và có nguồn đáng tin, không cho client tự đặt version cực lớn để gây DoS.

Nếu **DELETE** làm hàng biến mất, kiểm version bằng hàng hiện tại không đủ để phân biệt replica còn bản cũ với primary đã xóa; cần route primary hoặc có tombstone/checkpoint. Sau failover, nếu primary mới không chứa commit đã ACK trước đó, không được lặng lẽ trả phiên bản thấp hơn và nói RYW đã thành công. Đây là vấn đề durability/RPO/replication, không giải được chỉ bằng retry.

### 6.3. Đo cả độ mới và chi phí fallback

Chỉ giảm p95 đọc replica chưa chứng minh tối ưu. Cần đo `stale_read_detected_total`, `minimum_version_unmet_total`, `replica_lag`, `fallback_primary_ratio`, latency wait/fallback, primary connection/CPU và tỷ lệ 404 giả sau 201. Nếu replica lỗi, cho tất cả request fallback primary có thể tạo **thác quá tải**; áp concurrency cap, timeout, circuit breaker và ưu tiên endpoint critical.

## 7. Tối ưu write path: batching, transaction và retry không được nhân đôi side effect

### 7.1. Bulk update phải giữ precondition và tenant scope

Một thay đổi từ cập nhật từng order sang câu SQL bulk có thể giảm round trips nhưng bỏ mất optimistic locking và lifecycle hooks:

~~~sql
-- SAI khi API có If-Match và tenant isolation:
UPDATE orders SET status='CANCELLED'
WHERE id IN (:ids);

-- MINH HỌA bảo vệ từng order/version:
UPDATE orders
SET status = 'CANCELLED', version = version + 1
WHERE id = :id
  AND tenant_id = :trustedTenantId
  AND customer_id = :trustedCustomerId
  AND version = :expectedVersion
  AND status = 'CREATED';
~~~

Với statement thứ hai, số hàng updated phải là **1 nếu được phép và precondition/state phù hợp**. Nếu 0, cần xác định lỗi theo chính sách: resource không nhìn thấy → 404 trung tính; version cũ → 412; trạng thái cấm → 409 khi caller có quyền biết. Không dùng row count đơn thuần để tiết lộ order tenant khác. Bulk update nhiều order có thể cần **atomic all-or-nothing** hoặc **per-item results** theo hợp đồng, không trả 200 “mọi mục thành công” khi chỉ 7/10 row được cập nhật.

JPA bulk JPQL update có thể **bỏ qua entity listeners, dirty checking và @Version tự động** tùy cách viết; không giả định nó tương đương `repository.save`. Nếu có audit/outbox/stock reservation, cần đảm bảo các tác dụng ấy vẫn được phát một lần và trong ranh giới transaction đúng.

### 7.2. Timeout và retry: latency tốt hơn có thể tạo thanh toán trùng

Tối ưu aggressive timeout, parallel retry hoặc hedged requests có thể giảm tail latency nhưng tăng số request/side effects. Với POST không idempotent, **mất response sau primary commit là trường hợp nguy hiểm**: client không biết giao dịch đã xảy ra và gửi lại.

~~~http
POST /v1/orders HTTP/1.1
Authorization: Bearer <redacted>
Content-Type: application/json
Idempotency-Key: "b912be4b-11d9-43db-84dc-34ff61f157ad"

{"productId":"sku-7","quantity":2}

HTTP/1.1 201 Created
Location: /v1/orders/o-42
Content-Type: application/json

{"id":"o-42","status":"CREATED"}
~~~

Server cần ledger scoped theo `(tenant, actor/client, operation, key)`, fingerprint request và **atomic commit ledger + business side effect** nếu cùng DB. Khi retry cùng key/payload, replay outcome đã lưu; cùng key với payload khác phải từ chối; request cạnh tranh khi đầu chưa hoàn tất cần policy in-progress. Nếu side effect ở payment provider, dùng **provider idempotency key** hoặc reconciliation; local transaction không rollback charge ngoài hệ thống.

### 7.3. Async `202` có thể là thay contract, không phải tối ưu trong suốt

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/op-91
Retry-After: 3
Content-Type: application/json

{"id":"op-91","status":"QUEUED"}
~~~

Nếu API trước đó trả `201` sau khi order commit, đổi thành `202` ngay khi đưa job vào queue **thay đổi ngữ nghĩa**: client phải poll operation; đơn chưa chắc đã tồn tại/hoàn tất. Cần OpenAPI/migration, durable operation state, outbox, kiểm retry và failure/recovery. Không tối ưu thời gian đáp ứng bằng cách **chỉ trì hoãn lỗi sang nền rồi vẫn trả “đã hoàn tất”**.

### 7.4. Parallel fan-out và race

Cho `GET /v1/checkout-summary` chạy song song 5 downstream có thể giảm latency, nhưng:

- Nếu các nguồn có version khác nhau, tổng hợp balance mới với order cũ có thể tạo kết quả không hợp lệ. Dùng consistency boundary/checkpoint hoặc công bố snapshot semantics.
- Nếu gọi ghi song song, không được đổi thứ tự nghiệp vụ (reserve stock, charge, confirm) mà bỏ state machine/compensation.
- Khi client hủy request, propagation cancellation phải có policy; không hứa rollback side effect đã commit.
- Retry/hedging làm tăng tải downstream; giới hạn concurrency, deadline và idempotency. **Hedged POST** không an toàn nếu không có bảo đảm dedupe phù hợp.

## 8. Phân trang, nén và streaming: giữ nguyên thứ tự, bytes và lỗi

### 8.1. Pagination không được sai vì thay ORDER BY/index

Một index mới có thể cho page đầu rất nhanh nhưng bỏ `ORDER BY created_at DESC, id DESC` vì “DB thường trả đúng thứ tự”. Đây là sai: **SQL không bảo đảm thứ tự nếu không ORDER BY**. Khi nhiều rows có cùng `created_at`, phải có tie-breaker ổn định như `id`; nếu dùng cursor phải có cùng tuple sort/filter và visibility scope.

~~~sql
SELECT id, status, total_minor_units, created_at
FROM orders
WHERE tenant_id = :trustedTenantId
  AND customer_id = :trustedCustomerId
  AND (
      :cursorCreatedAt IS NULL
      OR created_at < :cursorCreatedAt
      OR (created_at = :cursorCreatedAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

Trong ví dụ keyset pagination, `cursorId` phải đi cùng `cursorCreatedAt` và được validate/ký/đóng gói nếu client không được tự thay boundary; bảo đảm các giá trị cursor đúng kiểu và scope. **Count, next link, filters và sort phải cùng quyền/tenant**; đổi từ offset sang cursor là đổi contract nếu client cần total counts hoặc random page jumps.

### 8.2. Compression, HEAD và conditional content

Gzip/Brotli có thể giảm bytes trên mạng nhưng tăng CPU và ảnh hưởng representation validator. Test `Content-Encoding`/`Vary: Accept-Encoding`/`Content-Length` khi có, decode payload và so schema. Với HEAD, **không gửi response body** nhưng giữ metadata đúng semantics; với 204/304 không parse JSON. Không tạo strong ETag giống nhau cho hai byte representations khác nhau nếu validator được áp trên bytes khác theo HTTP semantics.

### 8.3. Streaming: nhanh first byte nhưng lỗi có thể tới sau 200

Chuyển từ `List<OrderView>` buffer thành JSON streaming giảm memory và time-to-first-byte. Nhưng khi headers `200` đã được flush rồi, nếu DB lỗi ở phần tử thứ 100, **không thể đổi status thành 500**: client có thể thấy JSON bị cắt hoặc response không hoàn chỉnh. Hợp đồng phải quyết định **atomic response hay partial stream**, định dạng framed/NDJSON/SSE nếu phù hợp, cancellation và cách client xác minh hoàn tất.

Thử dữ liệu lớn, lỗi giữa luồng, client ngắt kết nối, slow consumer/backpressure, timeout, compression và không rò field. Với file download, test `Range`/`206 Partial Content`/`Content-Range`/checksum khi được hỗ trợ. Không chỉ benchmark first-byte mà bỏ qua **time-to-last-byte, completeness và memory peak**.

## 9. Phương pháp kiểm chứng: contract, differential, metamorphic và fault injection

### 9.1. Dựng oracle độc lập với đường tối ưu

Một cách mạnh để kiểm chứng tối ưu không sai logic là chạy **baseline và optimized implementation trên cùng snapshot dữ liệu thử** rồi so sánh outcome được phép quan sát:

~~~text
Fixture DB/identity/policy đã biết
          |
          +-- Baseline implementation --+
          |                            |
          +-- Optimized implementation -+--> Normalized responses
                                       |
                            Contract/invariant assertions
                                       |
                              Performance comparison
~~~

**Không clone request ghi production sang hai implementations và hy vọng idempotency bảo vệ:** shadow writes có thể tạo hai đơn, charge hai lần hoặc phát hai sự kiện. So sánh differential thích hợp nhất với **read-only endpoint** trên dữ liệu snapshot/isolated test database. Với write path, dùng **môi trường tách biệt**, business fixtures độc lập và so invariants; hoặc test state machine/side effects bằng fake provider có ledger.

Với JSON responses, so object có ý nghĩa thay vì so chuỗi text nếu serializer có thứ tự field khác. Nhưng **không tự bỏ qua field/headers tùy tiện** vì chính field bị rò có thể nằm trong phần “không so”. Chỉ normalize các trường không xác định mà hợp đồng cho phép (ví dụ server-generated request ID, Date, một số pagination links có host khác giữa môi trường). Đối với security response, so **cả danh sách field được phép và bị cấm**.

### 9.2. Ma trận thay đổi–rủi ro–bằng chứng

| Tối ưu | Lỗi âm thầm thường gặp | Bằng chứng tối thiểu |
|---|---|---|
| JPA projection / giảm N+1 | Mất tenant filter, lộ field, duplicate do JOIN | DB test nhiều tenant, schema DTO, page membership/order |
| Index/query rewrite | Sai sort, sai count, stale snapshot | Differential query trên fixture lớn, EXPLAIN và page tests |
| Redis/CDN cache | Cache key user sai, ACL stale, ETag cũ | A/B principals, hit/miss, invalidate/permission revoke |
| Replica read routing | 404 giả sau 201, đi lùi version | Commit→read ngay, version floor, fallback/failover test |
| Bulk UPDATE | Bỏ `If-Match`/transaction hook/outbox | Concurrency, affected rows, events, version increments |
| Timeout/retry/hedging | Duplicate POST/charge, retry storm | Drop response after commit, same idempotency key, count side effects |
| Async queue/`202` | Trả completed quá sớm, job mất | Poll lifecycle, crash recovery, outbox/idempotent consumer |
| Compression/stream | Sai Content-Encoding/ETag, truncated JSON | Decode, schema, midstream failure, checksum/EOF |
| Pagination/keyset | Mất hàng/trùng hàng, lộ total count | Stable ordering, cursor scope, insert/delete during traversal |
| Pool/concurrency tuning | Deadlock, connection starvation, p99 tail tăng | So latency distribution, saturation, controlled overload |

**Một test chỉ đo “response time nhỏ hơn” không nằm trong cột bằng chứng tính đúng.** Với mỗi tối ưu, buộc chọn những ca negative và fault tương ứng trước khi chạy benchmark.

### 9.3. Metamorphic tests: thay input nhưng bất biến phải giữ

Khi không thể liệt kê toàn bộ expected JSON, dùng quan hệ giữa hai lần gọi:

- Đổi **order ID** trong cùng tenant: kết quả thay đúng order, quyền không đổi.
- Đổi **tenant principal** và giữ ID: kết quả chuyển thành 404/403 theo policy, không phải dữ liệu của tenant trước dù cache hit.
- Đảo thứ tự JSON properties trong request **nếu contract coi payload tương đương**: fingerprint idempotency không được tạo hai side effects.
- Gửi hai lần `PATCH If-Match: "order-v7"` đồng thời: tối đa một update v7→v8, request còn lại 412 (theo hợp đồng).
- Lấy page sau với cursor đã ký: mỗi order trong snapshot nhất quán không lặp/khuyết khi không có concurrent writes.
- Tăng dữ liệu fixture từ 10 lên 100.000 rows: latency có thể đổi, nhưng **authorization và membership của result vẫn đúng**.

Phải định nghĩa **điều kiện tiên quyết**. Pagination đi qua DB đang có insert/delete đồng thời thường không có snapshot nhất quán giữa requests; không thể assert “không bao giờ thiếu hàng” nếu contract không hứa snapshot. Đây là lý do quan hệ metamorphic phải gắn với **mô hình nhất quán đã công bố**.

### 9.4. Kiểm concurrency bằng barrier, không bằng may mắn

Để chứng minh hai thao tác thật sự cạnh tranh, dùng `CountDownLatch`, `CyclicBarrier`, transaction test hooks hoặc DB lock có timeout; **không chỉ `Thread.sleep(100)`**. Khi load lớn, race condition có thể hiếm nhưng nghiêm trọng: lost update, double charge, row count sai hoặc cache invalidation đến trước commit.

Test trên **PostgreSQL/MySQL tương thích production** cho isolation/unique/lock; in-memory repository mock và H2 không thay được semantics transaction thật. Test phải có tiêu chí “không có duplicate rows/outbox/provider charges” bên cạnh response.

## 10. Java/Spring tests: ví dụ kiểm được hợp đồng và quyền

### 10.1. MockMvc: response allowlist và lỗi bảo mật

Giả sử `GET /v1/orders/{id}` yêu cầu scope `orders.read`, áp principal→actor từ Security Context và dùng `CustomerOrderView`. Test slice mức controller (Spring Boot 3.4+ dùng `@MockitoBean`; Boot 3.2/3.3 có thể dùng `@MockBean`):

~~~java
@WebMvcTest(OrderController.class)
@Import({SecurityConfig.class, ApiErrorAdvice.class})
class OrderContractMvcTest {
    @Autowired MockMvc mvc;
    @MockitoBean OrderQueryService queries;
    @MockitoBean ActorFactory actors;
    @MockitoBean JwtDecoder jwtDecoder; // Nếu security config cần

    @Test
    void authorizedGetReturnsOnlyPublicDto() throws Exception {
        UUID id = UUID.fromString(
            "7c4a604d-573d-4aab-82a5-667d73d4de3c");
        Actor actor = fixtureActor("tenant-a", "customer-1");
        when(actors.fromVerifiedJwt(any(Jwt.class))).thenReturn(actor);
        when(queries.getVisible(actor, id)).thenReturn(
            new CustomerOrderView(id, "PAID", 125000L, "VND", 7L));

        mvc.perform(get("/v1/orders/{id}", id)
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(id.toString()))
            .andExpect(jsonPath("$.status").value("PAID"))
            .andExpect(jsonPath("$.internalNotes").doesNotHaveJsonPath())
            .andExpect(jsonPath("$.paymentToken").doesNotHaveJsonPath())
            .andExpect(jsonPath("$.riskScore").doesNotHaveJsonPath());
    }

    @Test
    void missingAuthenticationDoesNotReturnCachedResource()
            throws Exception {
        mvc.perform(get("/v1/orders/{id}", UUID.randomUUID()))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(queries);
    }
}
~~~

**Lưu ý:** `OrderController`, `ActorFactory`, `SecurityConfig`, `ApiErrorAdvice` và fixture là thành phần app minh họa; cần điều chỉnh signature cho endpoint thật. Test `jwt()` của Spring Security Test **giả lập authentication**, không xác minh JWT cryptographic signature/issuer/audience; cần thêm integration test resource-server verification riêng. Test này chứng minh serialization/route contract, **không** chứng minh query JPA giữ tenant: service đang mock.

### 10.2. PostgreSQL integration test: projection tối ưu phải scoped

Một test quan trọng cần đi qua **repository thật**, ví dụ Testcontainers PostgreSQL với hai tenant:

~~~java
@SpringBootTest
@Testcontainers
class OrderProjectionIT {
    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired OrderReadRepository repository;
    @Autowired TestOrderFixtures fixtures; // Insert vào DB thật

    @Test
    void projectionNeverReturnsOrderOfOtherTenant() {
        UUID tenantA = UUID.randomUUID();
        UUID tenantB = UUID.randomUUID();
        UUID customerA = UUID.randomUUID();
        UUID customerB = UUID.randomUUID();
        UUID foreignId = fixtures.insertOrder(
            tenantB, customerB, "PAID", 42_000);

        assertTrue(repository.findCustomerView(
            foreignId, tenantA, customerA).isEmpty());
        assertTrue(repository.findCustomerView(
            foreignId, tenantB, customerB).isPresent());
    }
}
~~~

`TestOrderFixtures` là fixture **cần được triển khai**; migration/schema của production phải chạy trong test. Test thêm projection cho support role, field visibility và pagination. Hãy assert **scope ở DB/query**, không chỉ mock phương thức repository để luôn trả `Optional.empty()`. Với query tối ưu chứa JOIN, test fixtures có multiple child rows để bắt duplicate root và sai count.

### 10.3. Cache test: A xem được nhưng B tuyệt đối không thấy

~~~text
Given: order X thuộc tenant A, support A có quyền read
  1. GET X với principal A -> 200, cache miss rồi cache hit
  2. GET X với principal B -> 404/403 theo policy, không trả body/ETag A
  3. Thu hồi quyền A hoặc chuyển policy version
  4. GET X với A -> không dùng cache quyền cũ
  5. Cập nhật X từ v7 sang v8
  6. GET với yêu cầu RYW -> không 304 hay body v7 từ cache/replica
Assert: kết quả giống nhau giữa cache enabled/disabled theo contract
~~~

Nếu cache có TTL, dùng **fake clock/controlled invalidation** thay vì `sleep` để test. Dùng `Testcontainers`/Redis hoặc instance cache thật phù hợp vì in-memory cache không bộc lộ vấn đề phân tán. Kiểm cả cache key, value projection và **nơi kiểm authorization**; cache hit không được bypass các quyền mới bị thu hồi.

## 11. Kiểm concurrency, nhất quán và lỗi qua fault injection

### 11.1. Ma trận test regression tối thiểu

| Ca | Thay đổi liên quan | Tình huống | Bất biến phải đạt |
|---|---|---|---|
| P01 | JPA projection | Một ID thuộc tenant khác | Không trả field/order, lỗi theo visibility policy |
| P02 | Cache | A hit rồi B GET cùng URI | B không nhận DTO/ETag của A |
| P03 | Cache invalidation | A bị thu hồi quyền | Không tiếp tục trả từ cache theo quyền cũ |
| P04 | Conditional GET | Primary v8, replica/cache v7, floor v8 | Không trả `304`/body v7 như thể đạt RYW |
| P05 | Pagination | 2 orders cùng `createdAt` | Thứ tự ổn định bằng tie-breaker, không lặp khi snapshot cố định |
| P06 | JOIN/batch | Order có 4 items | Không duplicate order hoặc thiếu items |
| P07 | Bulk update | Hai PATCH cùng `If-Match: "v7"` | Chỉ một thành công, version tăng đúng |
| P08 | Async/queue | Worker crash sau commit | Không mất/outcome sai; retry đúng policy |
| P09 | HTTP retry | POST commit, response bị drop | Retry cùng key không tạo order/charge thứ hai |
| P10 | Idempotency scope | Cùng key ở tenant A/B | Không cross-tenant replay hoặc khóa oan |
| P11 | Streaming | Client ngắt sau 10/100 rows | Resource cleanup; không đổi semantics thành completed giả |
| P12 | Compression | `Accept-Encoding: gzip` | Decode đúng schema, ETag/Vary/Content-Encoding phù hợp |
| P13 | Load/circuit breaker | DB timeout/Redis outage | Fallback/error có deadline, không trả dữ liệu cũ trái policy |
| P14 | Security filter | JWT hết hạn, cache đã nóng | Vẫn 401, không trả private JSON |
| P15 | Observability | 100.000 raw order IDs | Metric labels/trace không bùng cardinality hoặc chứa PII |
| P16 | Canary | 10% traffic qua bản tối ưu | Bất biến không vi phạm; p95/p99/error/saturation đạt budget |

Mỗi test cần **oracle rõ**, không chỉ assertion status. Ví dụ P09 phải kiểm **row order, ledger, outbox và charge ở provider fake**, không dừng ở “retry trả 201”. P07 phải kiểm **version và payload cuối**. P04 phải có **version floor đã được server xác minh**, không cho client tự đặt version để buộc primary overload.

### 11.2. Dùng barrier để chứng minh lost update không xảy ra

~~~text
Given: order o-42 version=7, status=CREATED
T1: PATCH If-Match "order-v7", chờ tại barrier
T2: PATCH If-Match "order-v7", cùng đến barrier
Release: hai transaction tranh cùng row/version
Expected:
  - Một transaction cập nhật version 7 → 8
  - Transaction còn lại không ghi và nhận 412 theo hợp đồng
  - DB chỉ có một version mới, outbox event đúng một lần
~~~

Nếu chuyển code từ entity `@Version` sang SQL bulk, test này phát hiện mất precondition/optimistic locking. Phải đặt barrier ở **điểm cạnh tranh thực** trước update, không chỉ cùng lúc gọi HTTP rồi hy vọng scheduler tạo race. Với PostgreSQL, dùng Testcontainers/transaction boundaries chính xác, không đặt `@Transactional` trên test rồi làm mọi request rollback khi tưởng chúng đã commit.

### 11.3. Fault injection đặt tại ranh giới hậu quả

Đối với checkout:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Optimized API
    participant D as Primary DB
    C->>A: POST checkout + idempotency key K
    A->>D: Commit order + ledger + outbox
    D-->>A: COMMIT
    Note over A,C: Fault proxy cắt response sau commit
    C--xA: Client thấy timeout
    C->>A: Retry cùng K và payload
    A->>D: Đọc outcome K
    D-->>A: COMPLETED + order o-42
    A-->>C: Replay outcome
~~~

**Cắt response sau commit** khác cắt request trước khi server nhận. Nếu tối ưu timeout hoặc retry tự động, phải thử cả hai. Khi timeout ở payment provider, trạng thái bên ngoài có thể là unknown; retry với **provider idempotency key ổn định** hoặc reconcile, không tự charge với key mới. Nếu endpoint đổi sang `202`, kiểm operation lifecycle `QUEUED/RUNNING/SUCCEEDED/FAILED` và GET status có chính sách nhất quán.

### 11.4. Differential tests dưới quyền và dữ liệu thay đổi

Nếu so baseline/optimized trên cùng snapshot, chuẩn bị fixture:

~~~text
Tenant A: customer A1, A2; order A1 v7, order A2 v2
Tenant B: customer B1; order B1 v4 (ID biết trước)
Support A: có assignment với một order A2
Fraud A: được phép thấy riskScore, customer không được phép
Các đơn có createdAt trùng, items 0/1/nhiều, status khác nhau
Một order vừa DELETE, một order có permission vừa revoke
~~~

So **đúng role và tập field**; benchmark chỉ trên tenant A với toàn dữ liệu “sạch” dễ bỏ qua lỗi JOIN và privilege. Nếu test repository trả kết quả giống baseline nhưng baseline cũng sai vì quên tenant, phải có **independent expected result từ policy**, không dựa hoàn toàn differential equality.

## 12. Load test: cùng dữ liệu đúng, dưới tải tương đương

### 12.1. Chuẩn bị đo công bằng

Một benchmark có ý nghĩa cần:

- **Baseline** và candidate chạy trên hardware/config/dependency/data volume so sánh được; tách warmup, đo ổn định, ghi commit/version cấu hình.
- Traffic mix **theo operation thực**: GET detail/list, PATCH/POST, cache hit/miss, tenant size, payload small/large và tỷ lệ lỗi; không chỉ GET một ID đã cache.
- Có **closed-loop và open-loop** khi cần: closed-loop có thể che overload vì user chờ response rồi mới gửi tiếp; đo arrivals/RPS và độ trễ cả khi system saturated.
- Quan sát **p50, p95, p99**, timeout, throughput, connection pool/DB saturation, retry amplification, Redis/cache hit/eviction, queue lag, GC/memory.
- Song song, kiểm **semantic error rate**: sai JSON/schema, 200 thay 404, missing rows, cross-tenant data, stale version, duplicate side effects. Đây không giống HTTP 5xx rate.

**Không benchmark production bằng request ghi tạo charge thật.** Dùng environment cách ly, test payment provider và dữ liệu không nhạy cảm; nếu canary production cần giám sát read-only/dry-run với policy rõ, không shadow write sang cả hai backend.

### 12.2. Ví dụ load test GET có kiểm tính đúng

Ví dụ k6 minh họa luồng GET (không thay test security đầy đủ):

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    orders_read: {
      executor: 'constant-arrival-rate',
      rate: 50, timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 40,
      maxVUs: 120,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<250', 'p(99)<500'],
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const url = String(__ENV.API_URL) + '/v1/orders/' + __ENV.ORDER_ID;
  const token = __ENV.READ_TOKEN; // test credential, không log
  const result = http.get(url, {
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/json',
    },
    tags: { operation: 'orders.read' },
  });
  const valid = result.status === 200
      && result.headers['Content-Type']?.includes('application/json');
  let body = null;
  if (valid) {
    try { body = result.json(); } catch (_) {}
  }
  check(result, {
    'expected HTTP 200': () => valid,
    'body matches chosen order': () =>
      body?.id === __ENV.ORDER_ID,
    'internal fields absent': () =>
      body !== null
      && !('paymentToken' in body)
      && !('internalNotes' in body),
  });
}
~~~

**Lưu ý:** script giả định **fixture order chắc chắn thuộc token READ_TOKEN** và GET luôn trả 200; test 401/403/404/304 cần scenarios riêng, không làm `http_req_failed` trông xấu vì kỳ vọng lỗi nghiệp vụ. `API_URL`/`ORDER_ID`/`READ_TOKEN` là biến môi trường test; không in token, không lưu vào repository. Nếu không có đủ VUs để giữ arrival rate, kết quả có **dropped iterations**, phải ghi vào đánh giá; đừng chọn p95 đẹp trên số request thực tế thấp hơn mục tiêu.

Các threshold 250/500 ms và 1% ở đây **chỉ minh họa**, không phải SLO áp dụng chung. Thêm threshold custom về `semantic_violation`, cũng như check expected 404/412/429 ở các scenarios khác. Quan sát metric business duplicates bằng DB/fake provider sau chạy tải, không chỉ đọc report k6.

### 12.3. Tách lỗi hiệu năng khỏi lỗi quyền và inconsistency

~~~text
Release gate (ví dụ):
  Performance: p95 <= 250 ms; p99 <= 500 ms; RPS >= target
  Reliability: timeout + unexpected 5xx < ngưỡng cho phép
  Security:    0 cross-tenant disclosure, 0 forbidden fields
  Semantics:   0 sai status/schema/precondition
  Consistency: 0 RYW violation trên endpoints cam kết
  Side effect: 0 duplicate charge/order trên cùng logical intent
~~~

“0” trong một test run nghĩa là **không phát hiện vi phạm trong tập test**, không phải chứng minh xác suất lỗi production bằng 0. Với lỗi hiếm, bổ sung formal invariant, transaction/unique constraints, chaos tests và monitoring sau rollout; không giảm yêu cầu bảo mật chỉ vì test không bắt được.

## 13. Canary, feature flags và rollback không được làm sai state

### 13.1. Tối ưu đường đọc trước, theo dõi khác biệt có kiểm soát

Một kế hoạch rollout an toàn:

~~~text
Baseline fixture + invariant tests
      |
      v
Integration DB/cache/fault + performance benchmark
      |
      v
Shadow-read trên snapshot/traffic read-only phù hợp
      |
      v
Canary 1% -> 5% -> 25% -> 100%
      |        |       |
      +-- Mỗi bước: latency + status + semantic + tenant + stale + error
      |
      +-- Gate fail: rollback feature flag, điều tra, không tăng tỷ lệ
~~~

Tỷ lệ canary chỉ là ví dụ; cần chọn theo lưu lượng, khả năng khôi phục, side effects và độ nhạy nghiệp vụ. **Shadow read** không được gửi dữ liệu nhạy cảm sang môi trường không có quyền và không được thực thi write side effect hai lần. Nếu so JSON tại tầng proxy, không log full private response để tính diff; có thể so **schema/field presence, status và digest đã được phép** trong kênh được bảo vệ.

**Khi feature flag chọn read replica**, cần ghi audit cấu hình, bật theo tenant/route allowlist đã xác minh và cho rollback về primary khi lag tăng. Nếu vừa thay cache-key schema, rollback code không có nghĩa cache entries cũ tự trở lại đúng: phải dùng versioned keys hoặc invalidation plan. Nếu vừa phát outbox events hoặc chạy migration, rollback write path có thể **không đảo ngược dữ liệu đã commit**; cần forward-compatible schema và runbook tương thích.

### 13.2. Mỗi chỉ số có nguồn sự thật và giới hạn

| Tín hiệu canary | Mục đích | Cảnh báo cách diễn giải |
|---|---|---|
| p95/p99 theo route + response status | Có thật sự nhanh hơn không? | Traffic mix/cold cache có thể khác baseline |
| Unexpected 5xx/timeout và retry amplification | Có gây overload dây chuyền? | 429 có thể là rate policy, không tự gộp với 500 |
| SQL query count/rows scanned, DB CPU/connections | N+1/index/bulk có giảm tải? | Ít query chưa chắc ít data/ít lock |
| Cache hit/miss và authorization denies | Cache có hiệu quả, có rò quyền? | Hit rate cao không chứng minh cache key đúng |
| `ryw_version_violation`, 304-after-write bất thường | Replica/cache có trả cũ? | Cần version/floor, không đo bằng đồng hồ đơn thuần |
| Duplicate business intent/outbox charge count | Retry/async có nhân đôi side effect? | Không dùng HTTP 201 count thay row/provider count |
| Semantic diff rate theo operation | Response candidate khác baseline không mong muốn | Bỏ qua chỉ field không ổn định được duyệt |
| Metric label cardinality và log/trace PII | Observability có tự gây lỗi/bảo mật? | Không gắn tenantId/requestId thô vào metric label |

Nếu tín hiệu business safety **không thể đo được**, không coi đó là “không có vi phạm”; bổ sung test/counter/audit trước rollout. Logs/traces phục vụ điều tra phải không chứa token, raw request body hoặc thuộc tính khách hàng bị cấm. Với lỗi tenant leakage, **dừng canary ngay**, không chờ đủ mẫu thống kê p99.

### 13.3. Rollback phải được thử, không chỉ ghi trên giấy

Trước rollout, diễn tập:

1. Tắt cache mới/chuyển read path về primary; không trả entry sai từ một cache layer còn sống.
2. Nếu schema/query thay đổi, bản code cũ vẫn đọc được dữ liệu do bản mới đã ghi (**expand/contract migration**).
3. Retry requests đang in-flight vẫn dùng idempotency ledger tương thích, không tạo duplicate khi thay pod/version.
4. Background workers/queue consumers đang chạy vẫn xử lý event đúng version; nếu không, cần drain/canary consumers riêng.
5. SLO metrics và security/freshness metrics vẫn đo được sau rollback; correlation IDs không mất để đối soát incident.

**Rollback không thể “uncharge” một payment đã thực hiện** hoặc khôi phục quyền riêng tư khi response đã lộ. Những bất biến này phải được phòng ngừa ở data/model/transaction boundary, không chỉ trông chờ feature flag.

## 14. Bài tập và checklist kiểm chứng tối ưu

### 14.1. Tình huống

Nhóm của bạn tối ưu `GET /v1/orders/{id}` từ **p95 220 ms xuống 45 ms** bằng ba thay đổi:

- Chuyển JPA entity loading sang query projection chỉ lấy `id,status,totalMinorUnits`.
- Thêm Redis với cache key `"order:" + orderId`, TTL 5 phút.
- Route mọi GET sang read replica để giảm tải primary.

Đồng thời, để giảm tail latency của `POST /v1/orders`, client bật tự động retry một lần khi timeout (không giữ idempotency key).

Yêu cầu:

1. Liệt kê ít nhất **sáu rủi ro** về contract, bảo mật hoặc consistency.
2. Viết test tương ứng, nêu test nào cần DB/Redis thật và test nào dùng mock.
3. Đề xuất phiên bản thiết kế an toàn hơn mà vẫn có thể giảm latency.
4. Nêu release gate và hành vi rollback khi canary phát hiện một order khác tenant trả 200.

### 14.2. Lời giải tham khảo

| Rủi ro | Bằng chứng kiểm thử | Hướng sửa |
|---|---|---|
| Projection bỏ `tenant/customer` predicate | Tạo order tenant B, A GET ID B phải 404/403 đúng policy | SQL/JPA projection scoped; kiểm principal tin cậy |
| Cache key chỉ theo order ID | A GET warm cache, B GET cùng ID không được thấy dữ liệu A | Key tenant/actor/policy + recheck quyền/invalidation hoặc không cache private |
| Redis giữ ACL/quyền đã thu hồi | Revoke A, GET lại trên cache hit không còn dữ liệu trái policy | Policy version/TTL + invalidation/authorization check |
| Replica trả 404 ngay sau POST | POST 201 rồi GET cùng actor khi replay đang trễ phải thấy order | Đọc primary cho critical GET hoặc min-version gate/fallback |
| GET/ETag/304 từ replica version cũ | PATCH v7→v8 rồi conditional GET không được trả 304/200 v7 nếu hứa RYW | Evaluate freshness trước conditional cache |
| Projection mất field public `currency`/`version` | JSON schema/contract test so baseline và tối ưu | Chỉ projection field đúng hợp đồng, version semantics rõ |
| Retry POST với key mới | Drop response **sau commit**, retry phải không thêm order/charge | Giữ cùng Idempotency-Key scoped; ledger + transaction/outbox |
| Load tập trung fallback làm primary quá tải | Giả lập replica lag/circuit open ở tải cao | Concurrency cap, deadline, ưu tiên critical reads |

**Thiết kế cải tiến:** giữ projection scoped ở DB và DTO public; nếu dữ liệu order private có rủi ro cao, **bỏ Redis response cache** trước, đo hiệu quả index/projection. Nếu vẫn cache, dùng key/version/policy an toàn và test quyền trước mọi response; route GET detail cần RYW về primary, các GET aggregate được công bố eventual có thể ở replica. Thêm ledger idempotency cho POST, retry budget và giữ nguyên key/payload của cùng ý định.

**Release gate:** p95/p99 và tải DB đạt mục tiêu **đồng thời** 0 cross-tenant leak trong các kiểm thử/anomaly detection, 0 RYW violation trong contract test và 0 duplicate side effect trên test fault. Phát hiện một response 200 của tenant khác → **dừng/rollback canary ngay, cô lập cache, xác minh log/audit quyền hạn chế, đánh giá tác động dữ liệu và xử lý theo quy trình sự cố**; không chờ xem p95 có tiếp tục tốt không.

### 14.3. Checklist trước khi phê duyệt tối ưu

- [ ] Ghi rõ **baseline, mục tiêu p95/p99, workload và ngưỡng saturation**, không chỉ đo một GET hot cache.
- [ ] Danh mục bất biến đã bao phủ HTTP status/headers/body, 201/202/204/304/409/412, pagination, idempotency và Problem Details.
- [ ] Dữ liệu cần trả được định nghĩa bằng **public DTO/OpenAPI**, không serialize entity/field mới ngoài contract.
- [ ] Mọi query/projection/cache key giữ đúng **tenant, principal, object/field policy**; có negative tests cross-tenant.
- [ ] `If-Match`/version/transaction được kiểm tại điểm ghi; bulk SQL không bỏ mất outbox/event và state machine.
- [ ] GET/cache/replica đáp ứng freshness contract; có test commit→read, 304/ETag, permission revoke và failover.
- [ ] Retry/timeout/hedging có deadline/budget/idempotency; side effects ngoài DB có dedupe/reconciliation.
- [ ] Sorting, count, cursor, stable pagination, compression và streaming giữ response semantics.
- [ ] Có differential/metamorphic/contract/integration tests, real DB/cache cần thiết và fault injection **sau commit**.
- [ ] Load test kiểm cả **semantic correctness**, p95/p99, queue/DB/Redis, retry amplification và dropped load iterations.
- [ ] Canary có metrics cho security/freshness/duplicates và kế hoạch rollback đã được diễn tập.
- [ ] Log/trace/metric không lộ PII/token, route labels bounded và không biến chi phí observability thành bottleneck mới.

**Tài liệu tham khảo:** [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111), [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457), [OWASP API Security Top 10](https://owasp.org/API-Security/), [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html), [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html), [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing.html), [Spring Framework — Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction.html).

**Kết luận:** tối ưu hiệu năng REST API chỉ thành công khi hệ thống **nhanh hơn mà vẫn trả đúng resource, đúng trường, đúng HTTP status, đúng phiên bản và đúng một lần tác dụng nghiệp vụ cần thiết**. Chứng minh bằng bất biến từ contract, kiểm thử đa tenant/concurrency/fault injection, load test có oracle tính đúng và canary có khả năng rollback. Nếu một thay đổi làm lệch semantics, quyền hoặc consistency đã hứa, đó là **regression**, không phải đánh đổi có thể bỏ qua vì latency giảm.
