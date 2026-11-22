# Khóa cache, phạm vi tenant và phiên bản định dạng giá trị trong NoSQL

## 1. Mở đầu: một cache hit có thể trả nhầm dữ liệu của người khác

Ứng dụng Java phục vụ hàng trăm doanh nghiệp (*tenants*) trên cùng một cụm NoSQL. Trong mỗi tenant, mã đơn hàng có thể bắt đầu lại từ `1001`.

Một lập trình viên dùng Redis cache:

```text
GET /api/orders/1001
cache key = order:1001
```

Request của tenant A xảy ra trước:

```text
Tenant A -> order:1001 -> Redis MISS
         -> DB tenant A, order 1001 -> "Đơn của A"
         -> SET order:1001 = "Đơn của A"
```

Sau đó tenant B yêu cầu đơn hàng cùng mã:

```text
Tenant B -> order:1001 -> Redis HIT
         -> "Đơn của A" (!!)
```

Đây không chỉ là lỗi stale cache. Nó là **lỗi cách ly dữ liệu nhiều tenant**, có thể gây lộ thông tin nghiêm trọng. Database có thể đã phân quyền đúng, nhưng cache hit đã **bỏ qua toàn bộ câu truy vấn có điều kiện tenant**.

Một lỗi khác xuất hiện khi ứng dụng đổi cấu trúc JSON:

```text
Release R1 caches:
  {"id":"1001","total":500000}

Release R2 expects:
  {"orderId":"1001","totalMinorUnits":500000,"currency":"VND"}
```

Nếu cả hai phiên bản cùng dùng khóa `order:1001` và R2 đọc giá trị R1, ứng dụng có thể giải mã sai, hiển thị sai đơn vị tiền, dùng default không hợp lệ hoặc ném lỗi. Trong giai đoạn rolling deployment, R1 và R2 còn có thể **ghi đè giá trị của nhau** liên tục.

Do đó, thiết kế cache NoSQL phải trả lời đồng thời ba câu hỏi:

1. **Khóa cache định danh chính xác dữ liệu nào?** Nó đã chứa mọi chiều thay đổi kết quả chưa?
2. **Phạm vi tenant và quyền truy cập được ràng buộc ở đâu?** Ai được phép dùng chung kết quả?
3. **Phiên bản định dạng giá trị được biểu diễn và di chuyển thế nào?** Reader cũ và mới có thể cùng tồn tại an toàn không?

Bài này thuộc chương **Bộ nhớ đệm dữ liệu**, tập trung vào thiết kế **key schema, tenant isolation và value schema evolution** trong Redis, local caches, distributed caches và các read model hỗ trợ NoSQL.

## 2. Mục tiêu học tập

Sau bài này, bạn cần:

- Thiết kế **cache key có cấu trúc**, ổn định, không trùng giữa resource, tenant, môi trường và những biến thể kết quả.
- Phân biệt **tenant-scoped, user-scoped, public/global** và dữ liệu phân quyền theo vai trò/chính sách.
- Chuẩn hóa key theo thứ tự tham số, Unicode, kiểu dữ liệu và query filters.
- Phân biệt **key schema version**, **value format version**, **entity revision**, **authorization epoch** và **cache generation**.
- Dùng **value envelope** để phát hiện dữ liệu cache cũ, lỗi giải mã và payload thuộc sai scope.
- Thiết kế rolling deployment, dual-read có điều kiện, ngừng hỗ trợ giá trị cũ và chiến lược invalidation.
- Xử lý TTL, negative caching, stale refill race, event out-of-order, Redis Cluster hash slots và L1/L2 caches.
- Tránh lộ PII/secret qua key, logs, metrics, query strings và cache admin tools.
- Viết Java 17 cache key builder và cache-aside service có ranh giới authorization, source of truth rõ ràng.

## 3. Cache key không đơn thuần là ID của document

Khóa cache phải phân biệt **những tình huống cho kết quả khác nhau**.

Một phép tra cứu NoSQL có thể phụ thuộc vào:

```text
Resource type        order / customer / profile / product
Environment          prod / staging / development
Tenant               tenant-A / tenant-B
Resource identity    orderId=1001
Projection           summary / detail / price-only
Locale               vi-VN / en-US
Currency             VND / USD
Authorization scope  public / tenant / user / permissions epoch
Business variant     includeDeleted / activeOnly
Cache schema         key layout and value representation
```

**Không phải mọi khóa đều phải chứa tất cả các chiều này.** Chỉ đưa vào những chiều thực sự ảnh hưởng đến kết quả hoặc ranh giới an toàn. Nếu database trả một bản ghi thô độc lập ngôn ngữ, thêm locale vào key sẽ làm nổ số entry vô ích. Nhưng nếu response đã được dịch/localize, bỏ locale có thể trả sai ngôn ngữ.

### Một khóa có ý nghĩa rõ

```text
shop:prod:k3:t:<tenant-token>:order:by-id:<order-token>:rv2
|    |    |  | |              |     |     |             |
|    |    |  | |              |     |     |             +-- representation v2
|    |    |  | |              |     |     +---------------- encoded resource ID
|    |    |  | |              |     +---------------------- access pattern
|    |    |  | |              +---------------------------- resource type
|    |    |  | +------------------------------------------- encoded tenant ID
|    |    |  +--------------------------------------------- scope: tenant
|    |    +------------------------------------------------ key schema
|    +----------------------------------------------------- environment
+---------------------------------------------------------- application
```

Các chuỗi Base64 URL-safe hoặc HMAC chỉ minh họa cách tách segment; **Base64 không phải mã hóa bảo mật**. Cần tránh đặt thông tin nhạy cảm trực tiếp vào cache key nếu người có quyền xem logs/Redis monitoring không được nhìn thấy.

### Key phải là một hợp đồng

Một cache key tốt xác định:

> Đây là bản biểu diễn `rv2` của đơn `1001` thuộc tenant đã xác thực A, trên môi trường prod, với layout key `k3`.

Không phải một chuỗi ghép vội của vài tham số mà code hiện tại tình cờ nhớ.

## 4. Công thức thiết kế key

Một khuôn mẫu:

```text
<application>:<environment>:<keySchemaVersion>:
<scopeType>:<scopeIdentity>:
<resourceType>:<accessPattern>:<resourceIdentity>:
<representationVersion>[:<variantDimensions>]
```

Ví dụ:

```text
shop:prod:k3:t:tenantA:order:by-id:1001:rv2
shop:prod:k3:t:tenantA:orders:by-status:PAID:sort-newest:rv2
shop:prod:k3:u:user42:profile:summary:self:rv1
shop:prod:k3:global:catalog:public:sku8:rv4
```

Trong triển khai thật, các segment động phải được encode/canonicalize, không ghép raw input không kiểm soát. Khuôn mẫu có thể được rút gọn với hash của canonical query, nhưng **không được bỏ ý nghĩa scope**.

### Trường nào bắt buộc?

| Thành phần | Cần khi | Vì sao |
|---|---|---|
| Application namespace | Cùng cache được nhiều ứng dụng dùng | Tránh key collision liên ứng dụng |
| Environment | Prod/staging/dev dùng chung backend | Tránh ghi đè và lộ dữ liệu chéo môi trường |
| Key schema version | Layout/semantic key có thể đổi | Reader cũ và mới không hiểu nhầm |
| Scope type | Có public/tenant/user data | Tránh global key cho private data |
| Scope identity | Kết quả phụ thuộc tenant/user | Cách ly tenant/principal |
| Resource/access pattern | Nhiều kiểu record/query | Tránh collision `order:1` và `user:1` |
| Resource identity | Tra cứu theo khóa | Định danh chính xác đối tượng |
| Representation version | Payload/schema thay đổi không tương thích | Chặn reader giải mã sai |
| Locale/currency/timezone | Kết quả khác theo biến thể | Cache hit đúng representation |
| Authorization generation | Kết quả phụ thuộc quyền thay đổi | Giảm rủi ro cache cũ vượt quyền |

Không cần gắn **build number** vào mọi key chỉ vì mỗi lần deploy có version mới. Điều đó khiến cache lạnh toàn bộ, tiêu tốn bộ nhớ và không bảo đảm invalidation đúng. Chỉ tăng version khi **contract của key/value thực sự thay đổi** hoặc có một đợt rollover có chủ đích.

## 5. Tenant isolation: ranh giới phải đi trước cache lookup

NoSQL có thể tổ chức multi-tenant theo:

1. **Một database chung**, mỗi document chứa `tenantId`.
2. **Mỗi tenant một collection/table/keyspace**.
3. **Mỗi tenant một database hoặc cluster**.
4. **Mô hình lai**, tenant lớn có dedicated storage.

Cho dù database đã tách vật lý, nếu cache Redis được dùng chung thì **cache key vẫn phải thể hiện đúng security scope** hoặc client/backend phải có isolation vật lý đủ mạnh.

### Sai: chỉ dùng document ID

```java
String key = "order:" + orderId;
```

Nếu `orderId` chỉ duy nhất **trong tenant**, key đó không duy nhất trong cache shared.

### Đúng hơn: tenant từ principal đã xác thực

```java
String tenantId = authenticatedPrincipal.tenantId();
String key = CacheKeys.orderById(tenantId, orderId);
```

Điều cốt lõi:

- `tenantId` không được lấy trực tiếp từ query string/body **rồi tin ngay**.
- Server phải xác thực principal và xác minh principal được hoạt động trong tenant đã chọn.
- Cache lookup xảy ra sau khi xác định **scope được phép**.
- Cả database query khi MISS cũng phải filter/route theo tenant tương ứng.
- Kết quả cache HIT không được bỏ qua các bước authorization cần thiết.

### Tenant-scoped key không thay authorization

Biết một tenant ID và đoán được key **không cấp quyền truy cập**. Ứng dụng phải kiểm soát ai được gọi cache API hoặc expose dữ liệu. Một key pattern đúng là lớp cách ly phụ trợ, không thay IAM/RBAC/ABAC, network policies hay quyền của Redis/database.

## 6. Chọn đúng cấp scope: global, tenant, user, permission

### Public/global

Ví dụ catalog SKU công khai giống hệt cho mọi tenant:

```text
shop:prod:k3:global:catalog:sku:SKU-8:rv2
```

Chỉ dùng global nếu **dữ liệu và chính sách hiển thị thực sự chung**. Nếu sản phẩm có giá theo tenant, currency, khu vực hoặc hợp đồng, key global có thể trả giá của khách khác.

### Tenant-scoped

Ví dụ đơn hàng thuộc tenant A nhưng **mọi thành viên tenant** không nhất thiết được xem toàn bộ:

```text
shop:prod:k3:t:<tenant>:order:by-id:<order>:rv2
```

Key đủ để tách tenant A/B, nhưng nếu dữ liệu có field chỉ quản trị viên được thấy, cache **không được coi là đã thỏa authorization của mọi user trong tenant**.

### User-scoped

Ví dụ dashboard cá nhân:

```text
shop:prod:k3:t:<tenant>:u:<user>:dashboard:home:rv1
```

Cần cả tenant và user nếu user ID có thể trùng giữa tenant hoặc cùng user có vai trò/đơn vị khác nhau theo tenant.

### Authorization-dependent

Ví dụ response có chứa/ẩn trường theo role, group membership hoặc policy:

```text
scope = tenant + user + permissionRevision
```

Nhưng **thêm permissionRevision vào key chưa đủ** nếu có một instance vẫn dùng revision cũ hoặc một token stale. Khi cần thu hồi quyền ngay, phải kiểm tra tại authority hoặc dùng giao thức invalidation/fencing đủ mạnh. Không dựa vào TTL của cache để giữ invariant bảo mật.

## 7. Hai kiểu dữ liệu có cùng tenant nhưng khác quyền

Một endpoint:

```text
GET /api/orders/1001
```

trả:

**Nhân viên bán hàng:**

```json
{"orderId":"1001","totalMinor":500000,"status":"PAID"}
```

**Nhân viên tài chính:**

```json
{
  "orderId":"1001",
  "totalMinor":500000,
  "status":"PAID",
  "paymentReference":"PAY-778",
  "internalRiskScore":72
}
```

Nếu cả hai response được cache dưới **cùng tenant/order key**, nhân viên bán hàng có thể nhận payload tài chính do người khác tạo.

### Hai chiến lược

**A. Cache dữ liệu nội bộ có quyền truy cập bảo vệ chặt, rồi chiếu ra response sau authz:**

```text
Cache internal OrderSnapshot
    |
    v
Authorize current user
    |
    v
Project allowed response fields
```

Đòi hỏi cache và source chứa dữ liệu ở một security domain backend phù hợp; **không gửi nguyên snapshot chứa field nhạy cảm xuống browser**.

**B. Cache response đã được projection theo security scope:**

```text
tenant + user/role/policy revision + response variant
```

Đổi lại key cardinality lớn hơn, invalidation phức tạp hơn và phải bảo vệ stale authorization decisions.

### Vai trò không đủ nếu có ABAC

Quyền có thể phụ thuộc ownership, đơn vị, region, dự án, thời gian hoặc trạng thái order. Key `role=MANAGER` chưa chắc định danh đầy đủ tập dữ liệu được xem. Khi không thể mô tả ổn định tất cả chiều quyền, **đừng cache kết quả đã lọc theo quyền dưới một key quá rộng**.

## 8. Cache theo user nhưng user có thể thuộc nhiều tenant

Một user `U10` có thể thuộc tenant A và B:

```text
Principal U10:
  member of Tenant A, role ADMIN
  member of Tenant B, role VIEWER
```

Khóa:

```text
profile:U10
```

không phân biệt ngữ cảnh tenant khi profile/permission/branding khác nhau.

Nên có:

```text
tenant:<A>:user:<U10>:dashboard:rv2
tenant:<B>:user:<U10>:dashboard:rv2
```

Khi user chuyển tenant đang hoạt động, **request-local tenant scope** phải được cập nhật trong request, không lưu một `currentTenantId` mutable vào singleton cache service hay một `ThreadLocal` không được làm sạch.

### Tenant ID ổn định

Không dùng **tên tenant có thể đổi** như `acme-company` làm định danh duy nhất nếu nghiệp vụ cho phép rename. Dùng tenant ID nội bộ ổn định, còn slug/name là thuộc tính hiển thị.

Nếu tenant bị xóa rồi ID có thể tái sử dụng, cần generation/incarnation để tránh key cache của tenant đời trước được dùng cho tenant đời sau.

## 9. Key collision vì ghép chuỗi có delimiter

Giả sử code:

```java
String key = tenant + ":" + resourceId;
```

Hai cặp input:

```text
(tenant="a:b", resourceId="c") -> a:b:c
(tenant="a", resourceId="b:c") -> a:b:c
```

Khác identity nhưng **cùng key**.

### Cách tránh

- Encode từng segment bằng Base64 URL-safe hoặc percent encoding đã chuẩn hóa.
- Hoặc dùng length-prefix representation có thể giải mã một nghĩa.
- Hoặc tạo canonical serialized key rồi hash bằng thuật toán phù hợp.
- Tránh tự nối raw JSON/user input mà không escape.

Ví dụ biểu diễn có độ dài:

```text
3:a:b1:c
1:a3:b:c
```

Khuôn length-prefix chỉ minh họa; parser phải có spec, không đọc dựa vào dấu ngăn mơ hồ.

### Encode không có nghĩa bảo mật

`Base64("secret@example.com")` vẫn có thể bị giải mã. Nếu identifiers chứa PII/secret hoặc có entropy thấp, cân nhắc **HMAC có secret** thay vì plain SHA hoặc Base64, và vẫn bảo vệ cache server/log/metrics.

## 10. Canonicalization: cùng một query phải cho cùng key

Hai request tương đương:

```text
/orders?status=PAID&sort=createdAt&limit=20
/orders?limit=20&sort=createdAt&status=PAID
```

Nếu cache key bằng raw query string, hệ tạo hai entry dù kết quả giống nhau. Ngược lại, nếu key chỉ dùng `status` mà bỏ `limit`, có thể trả sai số kết quả.

### Các chiều cần chuẩn hóa

| Input | Quy tắc ví dụ | Cảnh báo |
|---|---|---|
| Query parameter order | Sort theo tên tham số | Chỉ khi thứ tự params không mang nghĩa |
| Repeated filters | Sort như set khi semantics không phụ thuộc thứ tự | Đừng sort một sequence có nghĩa |
| Integer | Chuẩn hóa `01` thành `1` nếu API coi bằng nhau | Có ID dạng "001" không được mất zero |
| Decimal | Cùng một dạng scale khi business coi bằng nhau | Monetary decimal có scale/currency |
| Boolean | `true/false` canonical | Không lẫn string "false" |
| Missing vs null | Mã riêng | Không tự coi vắng field = null |
| Empty string | Mã riêng | Không hợp nhất với missing |
| Locale | BCP 47/canonical locale policy | Locale fallback ảnh hưởng representation |
| Timezone | IANA zone hoặc UTC instant | Calendar dates khác UTC instant |
| Unicode | NFC nếu domain cho phép | Không tùy ý lowercase tên/ID |
| Case | Case fold nếu identifier case-insensitive | Không đổi nếu key case-sensitive |
| Sort order | Gồm field, direction, tie breaker | Query pagination phụ thuộc |
| Page cursor | Giữ nguyên cursor stable | Không lẫn page 1 với page 2 |

### Bẫy hash Map trong Java

Không serialize một `HashMap` rồi tin iteration order luôn ổn định. Với các tham số có semantics là map, sắp xếp keys và serialize theo canonical format **được phiên bản hóa**.

### Query filter không đầy đủ

Nếu kết quả phụ thuộc:

```text
tenantId, status, createdAfter, createdBefore,
sort, includeDeleted, locale, currency, permission scope
```

mà key chỉ chứa `tenantId:status`, cache hit có thể trả record không thuộc khoảng ngày hoặc đã bị xóa. Đây là **semantic collision**, không phải cryptographic hash collision.

## 11. Hash canonical query: tránh key quá dài

Một filter phức tạp có thể có vài KB JSON. Đưa toàn bộ JSON vào Redis key tạo overhead:

- Tốn memory vì key được lưu cùng value.
- Khó quan sát/đọc logs.
- Có thể chứa PII hoặc nội dung tìm kiếm nhạy cảm.
- Khó quản lý key naming.

Một mô hình:

```text
logical components:
  app=shop
  env=prod
  keySchema=k3
  tenant=T01
  resource=orderSearch
  canonicalFilter={...}
  repr=rv2

cache key:
  shop:prod:k3:t:<tenantToken>:orders:search:<digest>:rv2
```

Digest được tính từ **canonical payload**. Khi có đầu vào entropy thấp hoặc PII, dùng **HMAC-SHA-256 với secret phù hợp** để tránh người ngoài dò hash qua dictionary đơn giản. Một hash trơn (SHA-256) của email dễ bị thử với danh sách email dự đoán.

### Không xem digest thay identity validation

Nên lưu trong value envelope các trường version/scope cần thiết để kiểm tra khi đọc. Digest cryptographic có xác suất collision rất thấp khi sử dụng đầy đủ, nhưng **không cứu được việc bỏ quên tenant/status/permissions khỏi canonical input**.

### Secret rotation

Khi rotate HMAC key, cùng input tạo digest khác. Cần key identifier/version cho HMAC namespace hoặc rollout plan; không cho old/new writer vô tình dùng chung key với bí mật khác mà không có kế hoạch invalidation.

## 12. Java 17: xây dựng cache key có kiểu và segment an toàn

Ví dụ sau tránh delimiter collisions và buộc caller chỉ rõ tenant scope.

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Objects;

public final class CacheKeys {
    private static final Base64.Encoder ENCODER =
        Base64.getUrlEncoder().withoutPadding();

    private CacheKeys() {}

    private static String segment(String value) {
        Objects.requireNonNull(value, "cache key segment");
        if (value.isBlank()) {
            throw new IllegalArgumentException("Empty key segment");
        }
        return ENCODER.encodeToString(
            value.getBytes(StandardCharsets.UTF_8)
        );
    }

    public static String orderById(
            String tenantId,
            String orderId) {
        return String.join(":",
            "shop", "prod", "k3",
            "tenant", segment(tenantId),
            "order", "by-id", segment(orderId),
            "rv2"
        );
    }

    public static String localizedProduct(
            String tenantId,
            String sku,
            String locale,
            String currency) {
        return String.join(":",
            "shop", "prod", "k3",
            "tenant", segment(tenantId),
            "product", "detail", segment(sku),
            "locale", segment(locale),
            "currency", segment(currency),
            "rv4"
        );
    }
}
```

Đây là **ví dụ về cấu trúc**, chưa xử lý HMAC PII, config nhiều môi trường hoặc độ dài key tối ưu. Không đặt chuỗi `prod` cố định vào thư viện dùng chung mọi môi trường: production cần cấu hình environment từ nguồn được kiểm soát, **không nhận environment từ HTTP input**.

### Tenant lấy từ security context

```java
String tenantId = verifiedPrincipal.activeTenantId();
authorization.requireOrderRead(verifiedPrincipal, tenantId, orderId);
String key = CacheKeys.orderById(tenantId, orderId);
```

`verifiedPrincipal` và `authorization` là abstraction minh họa. Hệ thực phải xác thực user/tenant membership và bảo đảm database query sau MISS cũng dùng đúng tenant.

### Kiểm thử tính không trùng

```text
tenant="a:b", order="c"
tenant="a",   order="b:c"
=> keys must differ

tenant="T01", order="1001"
tenant="T02", order="1001"
=> keys must differ
```

## 13. Java 17: HMAC cho segment nhạy cảm

Với email, số điện thoại hoặc token có thể bị đoán, không nên để raw value trong key. Một đoạn minh họa dùng HMAC:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class KeyDigest {
    private KeyDigest() {}

    public static String hmacSha256(
            SecretKey secret,
            String canonicalInput) {
        try {
            // New Mac per call. Mac instances are mutable
            // and should not be shared unsafely between threads.
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(secret);
            byte[] digest = mac.doFinal(
                canonicalInput.getBytes(StandardCharsets.UTF_8)
            );
            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }
}
```

### Điều kiện sử dụng

- Secret phải được lưu/rotate qua secret manager hoặc cấu hình bảo mật; không hardcode vào repo.
- Canonical input phải có **type/scope/version**, không chỉ email trần nếu cùng digest được dùng giữa các loại đối tượng.
- HMAC không thay mã hóa dữ liệu nhạy cảm ở **value**.
- Đừng log canonical input trước khi hash.
- HMAC giảm rủi ro suy đoán key nhưng người có quyền đọc cache vẫn có thể lấy payload; cần ACL, TLS, network isolation và audit.
- Nếu secret bị lộ, attacker có thể thử giá trị entropy thấp; phải có rotation/incident plan.

## 14. Phiên bản hóa: không phải chỉ có một con số `v2`

Trong cache NoSQL thường có **nhiều loại version độc lập**:

| Version | Ví dụ | Điều nó bảo vệ |
|---|---|---|
| Key schema version | `k3` | Cấu trúc key, ranh giới scope/canonicalization |
| Value schema version | `valueSchema=2` / `rv2` | Format JSON/CBOR/Protobuf và ý nghĩa field |
| Entity revision | `orderRevision=87` | Thứ tự cập nhật của order tại nguồn |
| Authorization revision | `policyEpoch=14` | Phiên bản quyền/role của chủ thể |
| Cache generation | `tenantCacheGen=9` | Invalidate cả tập entry logic |
| API version | `v1/v2` | Hợp đồng response công khai |
| Deployment version | `build-2026...` | Bản binary đang chạy, không mặc định là cache version |
| Serializer version | `codec=protobuf3` | Cách mã hóa/giải mã cụ thể |

### Vì sao phải tách?

Nếu sửa field `total` thành `totalMinorUnits`, bạn cần nâng **value schema version**, nhưng order revision tại database có thể không đổi.

Nếu sửa cache key từ `order:1001` thành `tenant:T01:order:1001`, bạn đã đổi **key schema và security scope**; có thể giữ nguyên payload JSON.

Nếu user bị thu hồi quyền, **authorization epoch** đổi trong khi cache key layout/value format vẫn như cũ.

Nếu order chuyển từ revision 87 lên 88 vì update, đó là **business data version**; không cần tăng key schema version cho mọi thay đổi.

### Dùng “v2” không rõ nghĩa gây lỗi

```text
order:v2:1001
```

Không ai biết `v2` là API v2, JSON v2, tenant policy v2 hay cache generation 2. Nên dùng tên và tài liệu:

```text
shop:prod:k3:tenant:<t>:order:<id>:rv2
```

và ghi `entityRevision` trong envelope.

## 15. Value envelope: biến cache value thành dữ liệu có hợp đồng

Một payload trần:

```json
{"orderId":"1001","total":500000}
```

thiếu ngữ cảnh để biết nó thuộc schema nào, tenant nào, nguồn revision nào hoặc đã được tạo bởi code version nào.

Một **envelope**:

```json
{
  "valueSchema": 2,
  "resourceType": "order",
  "tenantScope": "T01",
  "resourceId": "1001",
  "sourceRevision": 87,
  "cachedAt": "2026-11-14T09:10:00Z",
  "expiresAt": "2026-11-14T09:15:00Z",
  "payload": {
    "orderId": "1001",
    "totalMinorUnits": 500000,
    "currency": "VND",
    "state": "PAID"
  }
}
```

**Không phải mọi entry cần giữ raw tenant ID trong value.** Nếu logs/Redis access exposure là vấn đề, dùng scope token/HMAC hoặc metadata phù hợp. Dù lưu kiểu nào, reader phải có cách xác minh entry thuộc request scope mà không dựa vào dữ liệu untrusted.

### Check khi đọc

1. `valueSchema` có thuộc những phiên bản reader hỗ trợ?
2. `resourceType` có đúng với expected type?
3. Tenant scope có khớp tenant đã xác thực?
4. `resourceId` và biến thể representation có khớp?
5. `expiresAt`/TTL/epoch còn hợp lệ theo policy?
6. JSON/Protobuf có field bắt buộc và đơn vị đúng?
7. Nếu có source revision/permission revision, nó có đạt ràng buộc cần thiết không?

Nếu sai: **coi là cache miss hoặc fail closed tùy security semantics**, không tự đưa default tenant hay giá 0.

## 16. Schema version trong key hay trong value?

Có ba cách phổ biến:

### A. Version chỉ trong key

```text
order:T01:1001:rv2 -> JSON v2
order:T01:1001:rv3 -> JSON v3
```

Ưu điểm: reader v3 không đọc nhầm key v2. Đổi lại hai nhóm entries cùng tồn tại đến khi TTL và tăng memory tạm thời.

### B. Version chỉ trong envelope

```text
order:T01:1001 -> {"valueSchema":2,...}
```

Reader đọc value và chọn decoder. Hợp khi mọi client có **dual-decoder** và writers không trộn semantics sai. Nguy cơ writer cũ ghi v1 lên cùng key mà writer mới vừa ghi v2, gây cache thrash nếu reader mới đã bỏ hỗ trợ v1.

### C. Version ở cả hai

```text
shop:prod:k3:tenant:T01:order:1001:rv3
    -> {"valueSchema":3,...}
```

Đây thường là lựa chọn dễ kiểm soát cho **breaking changes**, đồng thời envelope giúp phát hiện dữ liệu bẩn/nhầm scope.

### Bảng lựa chọn

| Thay đổi | Key version | Envelope version |
|---|---|---|
| Thêm field optional có default an toàn, old reader bỏ qua | Có thể giữ | Có thể giữ hoặc tăng theo policy |
| Đổi đơn vị số tiền | Nên tách representation | **Phải phân biệt rõ** |
| Đổi tenant scoping trong key | **Phải đổi key schema/namespace** | Nên có scope check |
| Đổi JSON thành Protobuf | Nên đổi representation/codec namespace | Bắt buộc decoder phân biệt |
| Thay tên field nhưng có migration decoder | Tùy chiến lược | Tăng hoặc dual-read |
| Thay entity state v87 lên v88 | Không cần | Giữ schema, cập nhật sourceRevision |
| Thu hồi quyền của user | Tùy scoped key policy | Policy epoch/check khác |

## 17. Rolling deployment: khi R1 và R2 cùng truy cập cache

Một rollout có nhiều application instances:

```text
               Load balancer
                /        \
             R1           R2
         writer rv1    reader/writer rv2
                \        /
                 Shared Redis
```

Nếu cả hai dùng cùng key `order:T01:1001`:

```text
R2 writes JSON rv2
R1 overwrites same key with rv1
R2 decode fails or misinterprets rv1
R2 rehydrates rv2
R1 overwrites rv1 again
```

Đây là **cache thrashing do schema collision**.

### Cách an toàn: namespace tách theo representation

```text
R1 uses ...:rv1
R2 uses ...:rv2
```

R2 bị cache miss lúc đầu rồi lấy từ nguồn chính xác, tạo entry mới. R1 tiếp tục dùng entry cũ cho đến khi không còn R1 hoặc TTL hết.

### Nếu muốn dual-read

R2 có thể thử `rv2` trước; nếu miss, thử `rv1` **chỉ khi**:

- Old key đã có đúng tenant/security scope.
- Old format có thể chuyển đổi chính xác.
- Không mất field bắt buộc hay đổi đơn vị sai.
- Không đưa dữ liệu bị stale/revoked vào path nhạy cảm.
- Có kế hoạch sunset old-read và metrics fallback.

Nếu old key vốn **thiếu tenant ID**, **tuyệt đối không fallback** sang old shared key đó để “warm cache”: đó là cửa lộ dữ liệu.

### Thứ tự rollout khái niệm

1. Định nghĩa schema mới và reader/writer compatibility.
2. Deploy code hỗ trợ schema mới (và old decode nếu thật sự an toàn).
3. Bắt đầu ghi key namespace mới.
4. Đo miss/hit/error per version.
5. Dừng writer cũ.
6. Ngừng fallback/reader cũ sau khi đủ điều kiện.
7. Đợi old keys hết TTL hoặc cleanup theo phạm vi chính xác.

Không cần `FLUSHALL` để đổi một schema; thao tác đó có thể ảnh hưởng toàn hệ và gây stampede.

## 18. Schema evolution: optional, required, rename, type, units

Các dạng thay đổi:

| Thay đổi | Ví dụ | Rủi ro |
|---|---|---|
| Thêm optional field | `couponCode` | Old decoder có thể bỏ qua |
| Thêm required field | `currency` | Old cache không có; default sai |
| Rename | `id` -> `orderId` | Decoder mới không tìm field |
| Type change | `total` number -> string | Cast/exception/sai nghĩa |
| Unit change | đồng -> minor unit khác | Lỗi tài chính khó phát hiện |
| Enum change | `PAID` -> `SETTLED` | Reader cũ không nhận giá trị |
| Nested path change | `customer.name` -> `customer.profile.name` | Mất dữ liệu |
| Time semantics | local time -> UTC instant | Lệch thời gian |
| Serialization codec | JSON -> protobuf/CBOR | Không thể đọc raw byte cũ |
| Redaction policy | Bỏ field nhạy cảm khỏi response | Cache cũ có thể làm rò field |

### Không dùng default nguy hiểm

Ví dụ reader rv2 thấy rv1 không có `currency` rồi tự gán `"USD"`; đơn hàng thực tế dùng VND. Trạng thái “decode thành công” nhưng **sai nghiệp vụ**.

Nếu không có thông tin chuyển đổi đáng tin từ source, hãy **cache miss + load authoritative value** thay vì đoán.

### Compatibility matrix

| Writer | Reader | Có thể chấp nhận? |
|---|---|---|
| rv1 | rv1 | Có |
| rv2 | rv2 | Có |
| rv1 | rv2 có decoder an toàn | Có điều kiện |
| rv2 | rv1 chỉ hiểu rv1 | Không nên cùng key |
| rv2 | rv2 nhưng tenant scope không khớp | **Không** |
| rv1 thiếu mandatory currency | rv2 | Không nếu không thể suy ra |

## 19. Không dùng key schema version để thay entity revision

Một order chuyển trạng thái:

```text
Order O1 revision 87: DRAFT
Order O1 revision 88: PAID
```

Cả hai cùng có **value schema rv2**.

Nếu chỉ lưu `rv2`, reader không biết payload nào mới. Cần invalidation/TTL hoặc revision metadata:

```json
{
  "valueSchema": 2,
  "sourceRevision": 88,
  "payload": {"orderId":"O1","state":"PAID"}
}
```

### Revision cần so được trong scope phù hợp

Một `revision` nên tăng đơn điệu cho **cùng aggregate/source authority**. Không lấy hai số local offset từ hai shard khác nhau rồi so như global timeline nếu engine không bảo đảm. Với distributed version vectors, conditional version semantics phức tạp hơn một integer.

### Timestamp chưa đủ chống stale overwrite

Clock skew và response out-of-order có thể làm timestamp của một payload cũ lớn hơn payload mới. Nếu dùng version guard, ưu tiên **revision cấp nguồn** có nghĩa rõ, không chỉ `cachedAt` tính trên máy ứng dụng.

## 20. Cache-aside: ví dụ đơn giản và ranh giới an toàn

Luồng cache-aside:

```text
GET order
   |
   v
Construct key with authenticated tenant and rv2
   |
   v
Cache GET
   | HIT + valid envelope
   +-----------------------> Return allowed projection
   |
   | MISS / invalid / unsupported format
   v
Authoritative NoSQL query with tenant filter
   |
   +--> Not found (handle negative caching policy)
   |
   v
Serialize correct rv2 envelope
   |
   v
Cache SET with TTL
   |
   v
Return source result
```

**Quan trọng:** cache-aside không tự đồng bộ mọi update. Một `SET` sau DB read có thể ghi dữ liệu cũ nếu update chạy đồng thời; cần invalidation/version/guards như các mục sau.

## 21. Java 17: abstraction cache-aside có tenant và schema

Ví dụ sau ưu tiên diễn đạt trách nhiệm. `CacheCodec` và `CacheBackend` là interfaces cần implementation thật; code không tự tạo một end-to-end transactional cache.

```java
import java.time.Duration;
import java.util.Optional;

record OrderSnapshot(
    String tenantId,
    String orderId,
    long revision,
    String state,
    long totalMinorUnits,
    String currency
) {}

record OrderCacheEnvelope(
    int valueSchema,
    String tenantId,
    String orderId,
    long sourceRevision,
    OrderSnapshot payload
) {}

interface CacheBackend {
    Optional<String> get(String key);
    void put(String key, String serializedValue, Duration ttl);
}

interface CacheCodec {
    Optional<OrderCacheEnvelope> decode(String raw);
    String encode(OrderCacheEnvelope value);
}

interface OrderSource {
    Optional<OrderSnapshot> findAuthoritative(
        String tenantId, String orderId
    );
}

interface OrderAuthorizer {
    void requireRead(String principalId, String tenantId, String orderId);
}

public final class OrderCacheService {
    private static final int VALUE_SCHEMA = 2;
    private static final Duration TTL = Duration.ofMinutes(3);

    private final CacheBackend cache;
    private final CacheCodec codec;
    private final OrderSource source;
    private final OrderAuthorizer authorizer;

    public OrderCacheService(
        CacheBackend cache,
        CacheCodec codec,
        OrderSource source,
        OrderAuthorizer authorizer
    ) {
        this.cache = cache;
        this.codec = codec;
        this.source = source;
        this.authorizer = authorizer;
    }

    public Optional<OrderSnapshot> find(
        String authenticatedPrincipalId,
        String verifiedTenantId,
        String orderId
    ) {
        // Authorization must apply even when Redis has a HIT.
        authorizer.requireRead(
            authenticatedPrincipalId, verifiedTenantId, orderId
        );

        String key = CacheKeys.orderById(
            verifiedTenantId, orderId
        );

        Optional<String> raw = cache.get(key);
        if (raw.isPresent()) {
            Optional<OrderCacheEnvelope> parsed =
                codec.decode(raw.get());

            if (parsed.isPresent()) {
                OrderCacheEnvelope e = parsed.get();
                if (e.valueSchema() == VALUE_SCHEMA
                        && verifiedTenantId.equals(e.tenantId())
                        && orderId.equals(e.orderId())
                        && e.payload() != null
                        && verifiedTenantId.equals(
                            e.payload().tenantId())
                        && orderId.equals(
                            e.payload().orderId())
                        && e.sourceRevision()
                            == e.payload().revision()) {
                    return Optional.of(e.payload());
                }
            }
        }

        Optional<OrderSnapshot> fromDb =
            source.findAuthoritative(verifiedTenantId, orderId);

        fromDb.ifPresent(item -> {
            if (!verifiedTenantId.equals(item.tenantId())
                    || !orderId.equals(item.orderId())) {
                throw new IllegalStateException(
                    "Source returned a mismatched scope");
            }

            OrderCacheEnvelope envelope =
                new OrderCacheEnvelope(
                    VALUE_SCHEMA,
                    verifiedTenantId,
                    orderId,
                    item.revision(),
                    item
                );

            cache.put(key, codec.encode(envelope), TTL);
        });

        return fromDb;
    }
}
```

### Những giới hạn phải hiểu

1. Caller phải cung cấp `verifiedTenantId` được suy từ authentication/tenant membership; method không thể tự chứng minh điều đó.
2. `authorizer.requireRead` phải kiểm tra **quyền hiện hành**, không chỉ so role từ cache stale nếu nghiệp vụ cần revoke tức thời.
3. `CacheBackend` phải có timeout, metrics, resilience và codec giới hạn kích thước/loại field.
4. Code **chưa xử lý stale refill race**, concurrent source update, authorization policy epoch, negative cache hoặc failover. Các phần sau trình bày cách giải quyết.
5. Cache availability không được làm source data mất consistency. Tùy ứng dụng, Redis unavailable có thể fallback source, nhưng đường đọc nhạy cảm không được silently skip authz.
6. `CacheCodec.decode` cần phân loại malformed/unsupported và không kích hoạt deserialization nguy hiểm từ untrusted bytes.
7. Không cache toàn bộ sensitive payload nếu cache backend không có security controls tương ứng.

## 22. Redis với Java Lettuce: put TTL và resource lifecycle

Một implementation minh họa cho `CacheBackend` dùng Lettuce; giả định connection được tạo một lần tại application startup:

```java
import io.lettuce.core.RedisClient;
import io.lettuce.core.SetArgs;
import io.lettuce.core.api.StatefulRedisConnection;
import java.time.Duration;
import java.util.Optional;

public final class LettuceCacheBackend
        implements CacheBackend, AutoCloseable {

    private final RedisClient client;
    private final StatefulRedisConnection<String, String> connection;

    public LettuceCacheBackend(String redisUri) {
        this.client = RedisClient.create(redisUri);
        this.connection = client.connect();
    }

    @Override
    public Optional<String> get(String key) {
        return Optional.ofNullable(connection.sync().get(key));
    }

    @Override
    public void put(String key, String value, Duration ttl) {
        long seconds = ttl.getSeconds();
        if (seconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        connection.sync().set(
            key, value, SetArgs.Builder.ex(seconds)
        );
    }

    @Override
    public void close() {
        connection.close();
        client.shutdown();
    }
}
```

**Lưu ý:** API cụ thể có thể khác theo phiên bản Lettuce; đây là ví dụ đồng bộ và đơn giản. Không tạo `RedisClient` cho từng request. Phải cấu hình TLS/auth, timeout, topology Redis Cluster/Sentinel, retry budget và theo dõi pool/command latency. Một `SET` như trên là **blind write**, không giải quyết stale overwrite; cần thêm version guard/invalidation tùy correctness.

### TTL tại backend và `expiresAt` trong envelope

Redis key expiry là cơ chế thu hồi vật lý/logical của backend. `expiresAt` trong envelope có thể dùng để kiểm soát logical freshness nếu cần:

- Tránh phục vụ entry đã quá hạn khi cache backend chưa dọn.
- Phân biệt soft TTL và hard TTL.
- Ghi audit khi migrate giữa caches.

Nhưng hai nguồn thời gian có thể lệch; cần định nghĩa **ai là clock authority** và tránh sai lệch giữa Redis expire và application checks.

## 23. Negative caching: “không tìm thấy” cũng có tenant scope

Nếu order không tồn tại, cache-aside có thể lưu negative entry để tránh liên tục query DB:

```json
{
  "valueSchema": 2,
  "state": "NOT_FOUND",
  "tenantScope": "T01",
  "resourceType": "order",
  "resourceId": "1001"
}
```

Nhưng cần phân biệt:

1. **Không tồn tại trong tenant T01.**
2. **User không được quyền biết dữ liệu đó có tồn tại.**
3. **Database tạm timeout/unavailable.**
4. **Replica/query index chưa bắt kịp write mới.**
5. **Order tồn tại nhưng bị soft-delete theo policy.**

**Không cache tất cả thành NOT_FOUND.**

### Rủi ro security

Nếu cache 403/permission denied thành `order:T01:1001 = NOT_FOUND` **không có principal scope**, một user ít quyền có thể khiến user đủ quyền sau đó nhận sai 404.

Nếu có negative caching cho authorization, nó phải có policy principal/role/revision và cơ chế invalidation phù hợp; với đường phân quyền nhạy cảm, nên tách khỏi cache resource và dùng authority.

### Rủi ro create sau negative

```text
T0 GET order 1001 -> NOT_FOUND cached for 5min
T1 CREATE order 1001 -> COMMITTED
T2 GET order 1001 -> negative cache HIT
```

Nếu hệ yêu cầu read-your-writes, negative cache phải được invalidated khi create, hoặc dùng short TTL/strong read/version guard. Không chọn negative TTL bằng TTL của record ổn định.

### Khuyến nghị về state

Đặt negative result trong **envelope có type riêng**, không dùng chuỗi rỗng hay `null` gây nhầm với JSON hợp lệ.

## 24. TTL: freshness, memory, stampede và sự cố cùng hết hạn

TTL giúp giới hạn tuổi entry, nhưng không tự đồng bộ với source.

| Loại dữ liệu | TTL khởi đầu minh họa | Điều kiện cần |
|---|---|---|
| Public catalog gần ổn định | Vài phút | Có invalidation khi giá/sản phẩm đổi |
| Order status | Ngắn hoặc versioned | Read-after-write/status SLA |
| Negative NOT_FOUND | Ngắn | Invalidate khi create |
| Personalized dashboard | Tùy mức stale cho phép | Scope user, permission checks |
| Authorization decision | Rất thận trọng; có thể không cache | Revoke semantics mạnh |
| Generated report | Có thể dài | Bất biến theo report version/content hash |

**Không có TTL mặc định đúng cho mọi nghiệp vụ.** Con số ở bảng chỉ minh họa cách suy nghĩ, không phải SLA.

### TTL jitter

Nếu 10.000 entries cùng hết hạn đúng 12:00:

```text
All keys expire
  -> simultaneous misses
  -> database thundering herd
```

Có thể áp jitter:

```text
baseTTL = 300s
jitter = random 0..60s
actualTTL = 300s + jitter
```

Cần giữ giới hạn stale tối đa. Nếu hard freshness ≤300s, **không được cộng thêm jitter** vượt hợp đồng; có thể chọn một phân phối TTL không quá hard limit.

### Soft TTL và hard TTL

Một entry có thể:

```text
softExpiresAt: 12:05
hardExpiresAt: 12:10
```

Sau soft TTL, request có thể nhận stale **nếu API cho phép** trong khi background refresh chạy. Sau hard TTL, không được phục vụ mà phải reload hoặc báo unavailable.

Với authorization/revocation hoặc payment status cần strong freshness, **stale-while-revalidate có thể không phù hợp**.

## 25. Cache-aside và race “stale refill” sau invalidation

Ngay cả khi update xóa cache sau commit, vẫn có race:

```text
Reader A                       Writer B
--------                       --------
GET cache -> MISS
Read old DB version=7
                               Update DB -> version=8
                               DEL cache key
SET cache version=7
GET cache by C -> stale v7
```

Lệnh `DEL` của B đã chạy **trước** `SET` của A. Dữ liệu cũ được **nạp lại sau invalidation**.

### Vì sao TTL không giải quyết đúng ngay?

TTL giúp stale entry cuối cùng biến mất. Nhưng trong khoảng TTL, API có thể trả sai read-your-writes hoặc trạng thái đã thu hồi.

### Các lựa chọn tùy hợp đồng

1. **Versioned value + conditional cache write**: chỉ nhận bản có source revision ≥ revision hiện đang lưu, với so sánh nguyên tử tại cache backend.
2. **Version/fence marker** cho invalidation: khi DB cập nhật v8, giữ một marker tối thiểu v8 đủ lâu; loader v7 không được ghi lại.
3. **Versioned keys** có generation/revision được xác định qua authority; reader chỉ tra namespace hiện hành.
4. **Read barrier/DB authoritative read** cho những request cần freshness mạnh.
5. **Short TTL + event invalidation** khi chỉ cần eventual consistency.

### Chú ý: CAS trên value chưa đủ khi key vắng

Nếu B `DEL` hoàn toàn key sau update, A thấy key trống và `SET v7`, cache CAS chỉ so với value hiện có **không có v8 để chặn**. Muốn chặn cần marker/version floor, namespace generation hoặc cơ chế khác giữ thông tin fencing qua cửa sổ race.

### Invalidation event đến muộn

```text
DB v8 -> event invalidate v8
DB v9 -> event invalidate v9
Consumer receives v9 first, then v8
```

Nếu handler mù quáng ghi lại cache từ sự kiện v8 sau v9, dữ liệu cũ thắng. Khi dùng events, cần event IDs, source revisions, idempotency/out-of-order handling và định nghĩa semantics của invalidation/publish.

## 26. Revision guard và CAS: không để kết quả cũ ghi đè mới

Một value envelope có `sourceRevision`.

Pseudocode:

```text
cachePutIfNewer(key, incoming):
    atomically read cached revision and mutation fence
    if incoming.tenantScope != expected tenant: reject
    if incoming.valueSchema not supported: reject
    if incoming.revision < minimumAcceptedRevision: reject
    if cached exists and incoming.revision < cached.revision: reject
    else write incoming + TTL
```

“Atomically” có thể được triển khai bằng Redis Lua/script hoặc transaction/conditional operation được cache backend hỗ trợ **trong đúng phạm vi key/fence liên quan**. Một `GET` rồi `SET` từ Java ở hai network round trips **không phải CAS**.

### Fence phải có cùng authority

Nếu fence v8 chỉ tồn tại ở app instance A, instance B dùng local memory khác có thể ghi v7. Với distributed cache, cần cơ chế đồng bộ generation/revision hoặc authoritative read.

### Revision không tự đảm bảo quyền

Order v100 có thể chứa field người dùng không được xem. Cache có revision cao vẫn cần authz và representation scope; **mới nhất không đồng nghĩa được phép**.

### Có khi nào nên bỏ cache thay vì làm protocol phức tạp?

Có. Với số dư tiền, ghế duy nhất hoặc permission revoke nghiêm ngặt, nếu không thể đảm bảo freshness qua cache mà không tăng độ phức tạp quá mức, đọc trực tiếp nguồn mạnh hoặc cache chỉ dữ liệu không nhạy cảm là lựa chọn hợp lý.

## 27. Invalidation theo tenant generation

Một tenant có hàng triệu keys:

```text
shop:prod:k3:tenant:T01:g8:orders:...
shop:prod:k3:tenant:T01:g8:dashboard:...
```

Khi thay đổi mô hình dữ liệu/policy rộng, có thể tăng:

```text
tenantCacheGeneration T01: 8 -> 9
```

Key mới:

```text
shop:prod:k3:tenant:T01:g9:orders:...
```

Entry g8 trở thành **không thể truy cập bởi reader mới** và hết hạn dần.

### Nhưng generation cũng cần consistency

Nếu app A dùng g9, app B còn cache generation g8 trong RAM, B vẫn đọc dữ liệu g8. Để đáp ứng yêu cầu “tất cả request mới phải theo g9”, cần **đồng bộ version/authority hoặc policy fail-closed**; tăng integer ở một nơi không tự làm mọi app nhìn thấy ngay.

### Thêm generation vào mọi key có chi phí

- Tốn metadata lookup hoặc local generation cache.
- Old generations giữ memory đến TTL.
- Có thể làm miss hàng loạt và gây stampede.
- Generation tăng quá thường xuyên làm mất lợi ích cache.

Vì vậy dùng generation cho **đợt invalidation có scope rõ**, không thay việc invalidation từng entity khi chỉ một order thay đổi.

## 28. Cache key namespace và môi trường triển khai

Nếu staging và production dùng cùng Redis endpoint:

```text
order:T01:1001
```

nguy cơ dữ liệu test đè production. Namespace:

```text
shop:prod:...
shop:staging:...
```

giảm nguy cơ collision, nhưng **không nên coi prefix là ranh giới bảo mật duy nhất**. Production/staging tốt nhất có tài khoản/ACL, network controls, quota, connection và policy tách riêng tùy mức nhạy cảm.

### Mã ứng dụng cũng cần namespace

Nếu hệ A/B cùng dùng `profile:U1` nhưng semantics khác, collisions xảy ra ngay cả trong một environment. Dùng application/service namespace cụ thể.

### Kết nối sai environment nguy hiểm hơn key lỗi

Nếu staging được cấp quyền đọc production cache, key prefix vẫn có thể bị đọc hoặc xóa nhầm qua một lệnh wildcard. Network/IAM/ACL phải bảo vệ ngoài naming convention.

## 29. Redis Cluster hash tags và tenant scope

Redis Cluster phân chia keys theo hash slot. Khi multi-key operation cần keys **cùng slot**, một cơ chế là hash tag:

```text
{tenant-T01}:cart:C1
{tenant-T01}:cart-items:C1
```

Đây là ví dụ minh họa về hash tag. Cùng phần trong cặp dấu ngoặc nhọn khiến keys được route tới cùng slot theo Redis Cluster.

### Cạm bẫy

Nếu **mọi key của một tenant lớn** đều có hash tag `{tenant-T01}`, chúng có thể dồn về một slot/nút, tạo **hotspot**, làm mất lợi ích phân mảnh.

Thực hành tốt hơn:

- Chỉ colocate những keys **thật sự cần multi-key atomic operation**.
- Chọn hash tag theo entity/aggregate nhỏ, ví dụ `{cart-T01-C1}` nếu có nhu cầu.
- Không đưa raw tenant ID nhạy cảm vào hash tag nếu không phù hợp security policy.
- Hiểu giới hạn Redis Cluster với multi-key commands/transactions và key movements.
- Hash tag để routing **không** cấp quyền giữa tenants; client vẫn cần authentication/authorization.

### Không đặt hash tag tùy ý từ user input

Nếu user điều khiển raw phần trong dấu ngoặc nhọn, họ có thể cố ảnh hưởng slot placement hoặc tạo hot key. Encode/validate segments và chỉ xây key qua một builder dùng chung.

## 30. Local cache L1 và distributed cache L2

Một Java service có thể dùng:

```text
HTTP request
    |
    v
L1 local cache (e.g., Caffeine, per JVM)
    |
    +-- hit
    |
    v
L2 Redis distributed cache
    |
    +-- hit -> populate L1
    |
    v
NoSQL source
    |
    +--> populate L2/L1
```

### Key schema phải nhất quán trên hai tầng

Nếu L1 key chỉ là `orderId` còn L2 key có `tenantId`, ứng dụng vẫn có thể leak dữ liệu giữa tenant ngay tại L1 **trước khi chạm Redis**.

Nếu L1 đã dùng value schema v1 nhưng L2 đã chuyển v2, có thể đọc sai dù Redis được version hóa tốt.

### Invalidation nhiều tầng

```text
DB update
   -> invalidate Redis L2
   -> broadcast invalidation to all L1 instances
```

Một app instance bị bỏ lỡ event có thể tiếp tục phục vụ L1 stale. Cần TTL, generation, event version và policy xử lý missed invalidations/restart.

### Caffeine cache key

Một Java object key có thể dùng record:

```java
record LocalOrderKey(
    String tenantId,
    String orderId,
    int representationVersion
) {}
```

`record` giúp có `equals/hashCode` theo fields, nhưng caller vẫn phải đưa **tenantId đã xác minh** và mọi chiều làm thay đổi kết quả. Không đặt mutable `Map` không có hash stability vào cache key.

## 31. Negative cache và soft delete trong NoSQL

Một document có thể:

```json
{
  "_id": "1001",
  "tenantId": "T01",
  "state": "DELETED",
  "deletedAt": "2026-11-14T09:00:00Z",
  "revision": 93
}
```

Query mặc định loại state DELETED; một endpoint admin có thể yêu cầu `includeDeleted=true`.

Hai kết quả đó **không được chia sẻ một key**:

```text
...:order:1001:mode:activeOnly:rv2
...:order:1001:mode:includeDeleted:rv2
```

Admin path phải kiểm tra quyền hiện hành trước khi trả bản đã xóa.

### Tombstone khác NOT_FOUND

`NOT_FOUND` có thể nghĩa chưa từng tồn tại; `DELETED at revision 93` chứa bằng chứng xóa để ngăn cache cũ hoặc event cũ làm dữ liệu hồi sinh. Với pipeline CDC, có thể cần tombstone/version để xử lý event out-of-order.

### Quy định data retention

Cache có thể giữ byte của document bị xóa cho đến TTL nếu không invalidated. Nếu có yêu cầu xóa dữ liệu hoặc thu hồi truy cập, cần phân biệt:

- Logical delete tại NoSQL.
- Invalidate L1/L2.
- Delete search projections.
- Log/backups retention.
- Quyền đọc cache và phân quyền admin.

Key schema đúng không tự thực hiện xóa vật lý toàn hệ.

## 32. Cache stampede và singleflight theo đúng scope

Một hot key hết TTL, 500 requests cùng lúc thấy MISS:

```text
500 requests -> Redis MISS
             -> 500 NoSQL queries
             -> same key SET many times
```

Các kỹ thuật:

- **Singleflight/coalescing** trong một JVM cho **cùng canonical scoped key**.
- Distributed refresh lock/lease nếu workload cần.
- TTL jitter, proactive refresh, stale-while-revalidate khi được phép.
- Bounded DB fallback concurrency.
- Cache warming có kiểm soát.

### Singleflight theo tenant

Nếu key singleflight chỉ là `orderId`, request từ tenant A/B có thể **chia sẻ kết quả cùng một Future**, dù Redis key đã đúng scope! Map để coalesce cũng phải dùng cùng **canonical safe key**.

### Lock không thay authorization

Một distributed lock dùng `lock:order:1001` có thể bị tenant B tranh lock với tenant A, tạo availability leak hoặc cache poisoning nếu worker không xác minh scope. Lock key cần tenant/resource scope và TTL/fencing phù hợp.

### Refresh lock không ngăn stale writer tuyệt đối

Lease hết hạn, worker cũ vẫn có thể tiếp tục query và SET. Cần kiểm tra generation/fencing hoặc version guard tại nơi ghi cache; không chỉ `SETNX lock` rồi tin worker cũ đã dừng.

## 33. Cache poisoning và dữ liệu untrusted

Cache poisoning xảy ra khi attacker hoặc một request không được kiểm soát khiến cache chứa giá trị không đúng cho identity mà người khác dùng.

Ví dụ:

- Input tenant giả được tin, entry bị ghi dưới tenant khác.
- Query key bỏ một filter quan trọng.
- Request header `Accept-Language` không được đưa vào key của response đã dịch.
- Cache key dùng raw `Host`/`X-Forwarded-*` không được xác minh.
- User có thể đưa strings trùng prefix/segment hoặc chen Redis hash tag.
- Cached HTML/JSON chứa phần dữ liệu riêng tư nhưng key global.
- Old valueSchema parser chấp nhận field thiếu và default nguy hiểm.

### Các lớp bảo vệ

1. Định danh tenant/principal **từ security context**.
2. Canonical key builder tập trung, không tự ghép tại từng controller.
3. Đưa mọi chiều khác biệt kết quả vào key.
4. Value envelope có type/scope/version validation.
5. Không cache kết quả unauthorized như dữ liệu public.
6. TTL, invalidation, cache namespace rotation có quản trị.
7. Giới hạn value size và loại dữ liệu được giải mã.
8. Cấm dynamic deserialization không an toàn, tránh mapper tự khởi tạo loại class tùy ý từ JSON untrusted.
9. Redis ACL/TLS, mạng riêng, monitoring và audit.
10. Test cross-tenant và query-equivalence có chủ đích.

### Tránh “security by obscurity”

HMAC cache key giúp giảm lộ identifier qua tên key, nhưng **không cấp authorization**. Redis credentials yếu hoặc API bỏ qua quyền vẫn lộ payload.

## 34. Invalidation theo event: outbox, CDC và thứ tự sự kiện

Khi NoSQL document thay đổi:

```text
Service writes Order v88 to source
   |
   +--> Outbox/CDC event OrderChanged(v88)
               |
               v
        Cache invalidator
               |
               v
        DEL/advance version fence for scoped key
```

### Điều cần bảo đảm

- Event chứa **tenant scope**, resource type/ID và source revision.
- Consumer không tạo key bằng format khác Java service.
- Duplicate event xử lý idempotent.
- Out-of-order event không ghi lại state cũ.
- Nếu consumer downtime, có checkpoint/replay và có cách reconcile.
- Cache invalidation chỉ có hiệu lực khi **DB write đã commit theo source contract**.

### Event payload và security

Không nhất thiết publish nguyên document nhạy cảm để invalidation; thường chỉ cần:

```json
{
  "eventId": "EV-88",
  "tenantId": "T01",
  "resourceType": "order",
  "resourceId": "1001",
  "sourceRevision": 88,
  "eventType": "OrderChanged"
}
```

Event consumers cần quyền phù hợp; tenant ID và order ID cũng có thể nhạy cảm tùy nghiệp vụ.

### Invalidation không luôn atomic với commit

Nếu code:

```text
DB commit -> Redis DEL
```

process crash giữa hai bước để lại stale cache. Outbox/CDC có thể giúp truyền intent một cách bền theo các bảo đảm được hệ hỗ trợ, nhưng **cache vẫn có một cửa sổ stale**. Nếu API không chấp nhận cửa sổ đó, phải đọc nguồn mạnh/version barrier hoặc thiết kế transaction/authority khác.

## 35. Cache key và consistency của nguồn dữ liệu

Một source NoSQL có thể có primary, read replicas và materialized views:

```text
Primary Order v88
Replica  Order v87
Search   Order v86
```

Loader cache đọc replica v87 rồi ghi vào Redis. Như vậy **Redis đã trở thành một bản copy stale lâu hơn** nếu TTL dài.

### Thiết kế cần chỉ rõ source read

- Với product catalog eventual, đọc replica có thể chấp nhận.
- Với order status ngay sau update, cần read-your-writes/causal session hoặc authoritative read theo API.
- Với permission, cần nguồn bảo đảm không chấp nhận stale allow theo hợp đồng.
- Với idempotency/unique claim, cache hit/miss không thay conditional write tại source.

### Cache không cải thiện consistency mặc định

Nếu DB eventual, cache-aside thông thường **không tự nâng nó thành strongly consistent**; nó có thể giữ thêm stale. Nếu DB strong read được dùng cho MISS nhưng HIT cũ được trả vô điều kiện, toàn endpoint cũng không còn strong consistency.

### Version check chi phí bao nhiêu?

Nếu mỗi cache hit đều phải đọc sourceRevision từ database mạnh, lợi ích performance có thể giảm. Hãy cân nhắc mục tiêu freshness, version tokens, event invalidation hoặc bỏ cache cho path không phù hợp.

## 36. Redis namespace và quản trị dữ liệu

Các thao tác bulk như:

```redis
KEYS shop:prod:*
FLUSHALL
```

không nên là chiến lược invalidation thông thường trong production. `KEYS` có thể gây tải/blocking không phù hợp trên dataset lớn; `FLUSHALL` ảnh hưởng toàn database/cache backend.

### Tùy tình huống

- Ưu tiên **exact key delete** cho một entity.
- Dùng tenant generation cho namespace invalidation lớn.
- Với cleanup có kiểm soát, có thể dùng `SCAN` theo phạm vi đúng, có rate limit và hiểu Redis Cluster phân bố nhiều nodes.
- Không coi `SCAN` là transaction/snapshot: keys có thể thay đổi khi quét.
- Các keys cũ có TTL để hết hạn dần, tránh phải dọn nóng.

### Đặt giới hạn memory và eviction policy

Namespace version mới và cũ cùng tồn tại có thể tăng memory. Khi Redis chịu áp lực, eviction có thể làm hit ratio giảm đột biến, tăng load NoSQL. Phải theo dõi memory/evictions sau migration.

### Hợp đồng key có người chịu trách nhiệm

Viết tài liệu:

```yaml
keySpec:
  namespace: shop:prod
  keySchema: k3
  scope: tenant
  resource: order
  identity: encoded(tenantId, orderId)
  representation: rv2
  ttl: 180s
  source: authoritative-orders-store
  invalidation: OrderChanged event + explicit exact-key deletion
  owner: order-service
```

Đây là schema tài liệu minh họa, không phải config Redis thực thi.

## 37. Cross-language cache: Java, Node.js và Python cùng phải hiểu một spec

Nếu Java tạo key:

```text
tenant:T01:order:0001
```

còn Node.js chuẩn hóa order ID thành số `1`:

```text
tenant:T01:order:1
```

hai service có thể tạo hai keys cho cùng object, hoặc tệ hơn: gộp hai ID `0001` và `1` vốn khác nhau.

### Cần spec độc lập ngôn ngữ

- Encoding UTF-8.
- Normalization Unicode cho từng field.
- Phân biệt số/string/missing/null.
- Cách escape/encode segments.
- Canonical query representation, sorting order.
- Hash algorithm/HMAC key identifier.
- Resource scope và version.
- Timezone/locale/currency.
- Value codec/envelope và unknown fields policy.
- Error handling khi decoder không hỗ trợ version.

### Golden vectors

Tạo những bộ input/output chuẩn để mọi SDK thực hiện giống nhau:

```json
{
  "input": {
    "environment": "prod",
    "tenantId": "a:b",
    "orderId": "0001",
    "representationVersion": 2
  },
  "expectedKey": "the-canonical-key-generated-by-spec"
}
```

`expectedKey` ở đây là placeholder cho giá trị được spec/implementation tham chiếu tạo ra, không phải một key thực để copy. Golden vectors nên bao gồm Unicode, delimiter, ID có zero đầu, null, empty và tên tenant khác nhau.

## 38. Test phân tách tenant và security scope

Một bộ test tối thiểu:

### Test A — Cùng ID, khác tenant

```text
Tenant A, orderId=1001 -> payload A
Tenant B, orderId=1001 -> payload B
Expected: different keys and distinct outputs
```

Kiểm tra cả L1 local và L2 Redis.

### Test B — Cùng tenant, khác user rights

Admin và viewer cùng yêu cầu order có field nhạy cảm. Cache hit của viewer không được lộ nội dung chỉ admin thấy.

### Test C — Tenant đổi vai trò

User từ ADMIN xuống VIEWER. Kiểm tra permission revision/invalidation và response trong khoảng rollout; không chỉ chờ TTL nếu revoke cần hiệu lực ngay.

### Test D — Delimiter collision

Hai cặp `("a:b","c")` và `("a","b:c")` phải tạo khác key.

### Test E — Null/missing/empty

Query `filter missing`, `filter=null` và `filter=""` phải khác nhau nếu API có semantics khác.

### Test F — Equivalent queries

Hai query có thứ tự filter khác nhưng cùng nghĩa phải có canonical key bằng nhau nếu spec quyết định vậy. Query có sort/limit khác phải tạo key khác.

### Test G — Locale/currency

`vi-VN/VND` và `en-US/USD` không được dùng cùng formatted-response key.

### Test H — Value rv1/rv2

Deploy R1 và R2 đồng thời; xác minh R2 không deserialize rv1 như rv2, không default currency sai, không ghi đè lẫn nhau nếu namespace tách.

## 39. Test stale data, invalidation và race

### Test I — Stale refill

1. Reader A cache MISS và đọc DB version 7 nhưng bị giữ trước SET.
2. Writer B commit version 8 và invalidate key.
3. Cho Reader A SET version 7.
4. Verify policy có chặn stale refill hoặc endpoint chỉ cam kết eventual với TTL rõ.

### Test J — Out-of-order invalidation

Gửi event v9 trước v8; consumer không được làm cache quay về v8 hay bỏ version fence.

### Test K — Negative cache

GET order 1001 trả NOT_FOUND và cache. Sau đó CREATE order 1001. Read-after-write phải thấy order nếu contract yêu cầu.

### Test L — Tenant generation

Tăng g8→g9; một app instance giữ g8. Kiểm tra stale generation có thể bị nhận hay từ chối theo policy.

### Test M — L1 missed event

Một app instance mất subscription invalidation, còn L1 stale. Kiểm tra TTL/policy epoch/reconnect reconciliation.

### Test N — Cache backend outage

Redis timeout. Với endpoint public catalog có thể fallback DB; với authorization path, không được trả allow từ cache stale không đáng tin.

### Test O — Rolling deploy rollback

R2 đã ghi rv2, một số R1 vẫn chạy. Khi rollback R1, các keys rv1 vẫn hoạt động, không đọc nhầm rv2; memory/TTL có kế hoạch.

### Test P — Key poisoning

Gửi raw input chứa dấu `:`, dấu ngoặc nhọn, unicode combining marks, URL encoding, chuỗi rất dài và query filters thiếu. Verify builder tạo key đúng, không vượt tài nguyên hoặc scope.

Các phép thử phải dùng dữ liệu giả trong lab/staging và quyền hợp lệ, không cố làm leak tenant production.

## 40. Metrics cần theo dõi

| Metric gợi ý | Giúp trả lời |
|---|---|
| `cache_hit_total` / `cache_miss_total` | Hit rate theo resource/representation |
| `cache_lookup_latency` | Redis/L1 có trở thành bottleneck? |
| `cache_decode_error_total` | Value corrupt/unsupported format? |
| `cache_schema_fallback_total` | Có bao nhiêu đọc fallback rv1? |
| `cache_scope_mismatch_total` | Có entry sai tenant/resource? |
| `cache_authz_recheck_denied_total` | Authorization chặn cache hit? |
| `cache_negative_hit_total` | Negative caching có gây stale? |
| `cache_invalidation_lag_seconds` | Bao lâu sau commit cache được xử lý? |
| `cache_stale_refill_detected_total` | Loader cũ có bị version guard chặn? |
| `cache_evictions_total` | Memory pressure/namespace migration? |
| `cache_generation_current` | Hiện dùng generation nào? |
| `cache_backend_errors_total` | Cache timeouts/outages |
| `db_fallback_rate` | Cache miss/stampede có đẩy tải DB? |
| `cache_value_bytes` / `cache_key_bytes` | Tốn memory theo representation |
| `cache_refresh_inflight` | Singleflight/refresh có hiệu quả? |

Đây là **tên đề xuất cho instrumentation**, không phải metric có sẵn nguyên văn trong mọi SDK.

### Tránh metric labels quá chi tiết

Không gắn `email`, `orderId`, `tenantId` hàng trăm nghìn giá trị vào metric labels. Dùng resource type, key schema, value version, service, environment, error class. Với enterprise tenants cần phân tích riêng, dùng logging/tracing có quyền hoặc aggregate an toàn.

### Hit rate cao không chứng minh đúng

Một cache có 99.9% hit rate có thể đang lộ dữ liệu tenant A cho tenant B. Correctness cần **security scope tests, schema decode validation và freshness contract**, không chỉ hit ratio.

## 41. Runbook khi phát hiện cache trả sai tenant hoặc sai schema

### Bước 1 — Phân loại mức độ

Nếu thấy tenant A đọc dữ liệu B, xử lý như **sự cố an toàn dữ liệu**, không phải “cache miss bình thường”. Cần cô lập đường phục vụ rủi ro và tuân incident policy.

### Bước 2 — Xác định nguồn key

Thu thập:

```text
requestId
verified tenant/principal scope
cache layer (L1/L2)
key schema version
resource type/id (redacted when needed)
value schema version
source entity revision
application release
```

Không dump raw secrets/PII vào log công khai.

### Bước 3 — Chặn lookup sai

Tạm bypass cache cho endpoint/scope lỗi hoặc tăng safe key namespace/schema nếu cần. Đảm bảo fallback vẫn **xác thực và query nguồn đúng tenant**.

### Bước 4 — Không fallback key cũ thiếu tenant

Nếu sự cố đến từ key v1 không chứa tenant, **đừng dùng dual-read v1** để tăng hit ratio. Ngừng reader/writer cũ, isolate/bỏ dùng namespace v1.

### Bước 5 — Xử lý value không tương thích

Những payload sai schema hoặc đổi đơn vị không an toàn phải coi là miss, regenerate từ nguồn. Không default fields một cách đoán mò.

### Bước 6 — Điều tra invalidation

Xem DB write, event outbox/CDC, cache delete, stale refill, L1 propagation và generation. Không cho rằng `DEL` đã chạy nghĩa không thể có stale SET sau đó.

### Bước 7 — Giới hạn tải do cold cache

Bypass/invalidate quy mô lớn có thể tạo stampede. Dùng rate limit, bounded fallback, TTL jitter, warm-up có kiểm soát nếu phù hợp.

### Bước 8 — Đối soát và ngăn tái diễn

Xác định những tenant/users có thể bị ảnh hưởng qua traces/audit, cập nhật key builder chung, tests và policy; chỉ đóng incident khi cache/scope/decoder/invalidation đúng và hậu quả dữ liệu đã được xử lý.

## 42. Bài tập thực hành

### Bài 1 — Cross-tenant collision

Tenant A và B đều có order ID `1001`. Khóa `order:1001` có lỗi gì? Thiết kế key mới kèm namespace, tenant ID và representation version.

### Bài 2 — Tenant từ request

Controller lấy `tenantId` trực tiếp từ query string và dùng để tạo Redis key. Vì sao đây chưa phải cách ly tenant an toàn? Viết luồng xác thực/ủy quyền trước lookup.

### Bài 3 — Phạm vi permission

Admin và viewer trong cùng tenant nhận JSON khác nhau. Chọn cache raw backend model rồi projection sau authz hoặc cache response theo user/policy scope. Nêu trade-off.

### Bài 4 — Delimiter collision

Với `tenant + ":" + resourceId`, tìm hai cặp input khác nhau cho cùng key. Đề xuất Base64 URL-safe, length prefix hoặc canonical hash.

### Bài 5 — Canonical query

Hai URL có thứ tự tham số khác nhau nhưng cùng filter. Thiết kế canonicalization, đồng thời giải thích lúc nào **không được sort** tham số lặp.

### Bài 6 — Locale và currency

Product price response được định dạng theo locale và currency. Nếu key chỉ là `product:SKU8`, sẽ xảy ra lỗi gì?

### Bài 7 — Key schema và value schema

Phân biệt `k3`, `rv2`, `sourceRevision=87`, `authzEpoch=14`, `tenantCacheGen=9`. Trường nào đổi khi order chuyển sang PAID? Trường nào đổi khi JSON renames field?

### Bài 8 — Breaking schema

Release R1 lưu `total` theo đồng; R2 cần `totalMinorUnits` và `currency`. Thiết kế rollout để R1/R2 cùng chạy, không đọc nhầm, không double writer cache thrash.

### Bài 9 — Value envelope

Viết envelope cho order có tenant, resource ID, schema, revision, expiry và payload. Đề xuất checks khi đọc; làm gì nếu tenant mismatch?

### Bài 10 — Old key thiếu tenant

R2 muốn fallback sang R1 để cache warm, nhưng R1 dùng `order:1001` không có tenant. Có được fallback không? Vì sao?

### Bài 11 — HMAC

Một team dùng SHA-256(email) làm Redis key. Rủi ro dictionary attack là gì? HMAC giúp gì và không giúp gì? Nêu kế hoạch rotate secret.

### Bài 12 — Negative cache

GET order trả NOT_FOUND và cache 10 phút, sau đó order được CREATE. Read-after-write có thể sai thế nào? Nêu invalidation/short TTL/authority options.

### Bài 13 — Stale refill race

Reader A đọc DB v7 rồi chờ; writer B commit v8 và DEL cache; sau đó A SET v7. Vì sao “DB write rồi DEL” chưa đủ? Đề xuất một version floor/generation/authority strategy.

### Bài 14 — CAS thiếu marker

Một cache chỉ so incoming revision với value đang tồn tại. Writer invalidates bằng DEL, sau đó loader cũ SET v7 khi key empty. Vì sao CAS đó không chặn? Cần giữ thêm chứng cứ nào?

### Bài 15 — Event out-of-order

Cache invalidator nhận event Order v9 trước v8. Làm sao tránh đưa value trở về v8 hoặc tạo duplicate side effect?

### Bài 16 — Redis Cluster

Một team đặt mọi key của tenant lớn trong `{tenant-T01}` để co-locate. Điều gì xảy ra với slot/hotspot? Khi nào nên hash tag theo một cart thay vì toàn tenant?

### Bài 17 — L1/L2

Ứng dụng có Caffeine L1 và Redis L2. L2 key chứa tenant nhưng L1 key chỉ có orderId. Hãy xác định lỗ hổng và phương án invalidation/rollout.

### Bài 18 — Soft delete

Endpoint user mặc định loại deleted orders; admin có `includeDeleted=true`. Thiết kế keys, authz, negative cache và tombstone handling.

### Bài 19 — Cache stampede

10.000 tenant-scoped keys cùng TTL và hết hạn một lúc. Hãy mô tả bounded fallback, singleflight đúng tenant scope, jitter và sự khác biệt soft/hard TTL.

### Bài 20 — Tổng hợp Java

Thiết kế `CacheKeys`, `OrderCacheEnvelope`, `CacheBackend` và `OrderCacheService` cho NoSQL source + Redis, có kiểm tra tenant, schema và read-after-write policy. Liệt kê các test collision, tenant isolation, rollout rv1/rv2 và stale refill.

## 43. Checklist trước khi đưa cache vào production

1. Cache entry này có phải **public, tenant, user hay permission-scoped**?
2. Tenant ID có được lấy từ identity đã xác thực và quyền tenant membership không?
3. Cache hit có bypass một authorization check quan trọng không?
4. Các resource ID có duy nhất global hay chỉ trong tenant?
5. Key có **application/environment namespace** và semantic key version không?
6. Dynamic segments có được encode, phân biệt null/missing/empty và canonicalize không?
7. Query key có đủ filter, sort, page cursor, locale, currency, delete visibility không?
8. Hash/digest có dùng canonical input và đủ ràng buộc scope không?
9. Có PII/secret trong key hoặc log không? Cần HMAC/ACL/TLS không?
10. Value có **schema version** và decoder xử lý unknown version an toàn không?
11. Reader có kiểm tra type, resource ID, tenant scope và source revision không?
12. Đổi format value có cần representation namespace mới không?
13. Rolling deployment có old/new writers cùng key không?
14. Dual-read old key có nguy cơ lộ tenant hoặc đổi đơn vị sai không?
15. TTL có đáp ứng freshness/SLO và giới hạn stampede không?
16. Negative cache có phân biệt NOT_FOUND, FORBIDDEN và UNAVAILABLE không?
17. Có chiến lược invalidation sau DB commit, bao gồm sự cố crash/event lag không?
18. Stale refill race có được xử lý hoặc được chấp nhận rõ trong SLA không?
19. L1/L2 và singleflight/lock keys có cùng scope không?
20. Redis Cluster hash tags có gây hotspot cho tenant lớn không?
21. Có metrics decode errors, scope mismatches, version fallback, invalidation lag và DB fallback không?
22. Có test liên tenant, rolling deploy, failover, soft delete, authorization revoke và stale fills không?
23. Nếu phải invalidation hàng triệu keys, có generation/rollout thay vì `FLUSHALL` không?
24. Có runbook sự cố dữ liệu sai tenant và khả năng tạm bypass cache an toàn không?

## 44. Kết luận

Trong hệ NoSQL nhiều tenant, **cache key là một phần của ranh giới đúng dữ liệu**. Một key thiếu tenant có thể gây lộ dữ liệu; một key thiếu biến thể locale/permission có thể trả sai kết quả; một value thiếu version có thể bị giải mã sai khi rolling deployment.

Các nguyên tắc quan trọng:

1. **Định danh đúng trước khi tối ưu tốc độ.** Key phải chứa resource identity, mọi chiều làm thay đổi kết quả và security scope cần thiết.
2. **Tenant scope phải được xác minh trước cache lookup.** Không lấy raw tenant ID do client cung cấp làm bằng chứng quyền; key naming không thay authorization.
3. **Phân biệt các loại version.** Key schema, value schema, source revision, authz epoch và cache generation giải quyết những vấn đề khác nhau.
4. **Dùng value envelope khi cần kiểm tra hợp đồng.** Format, scope, resource, revision và expiry có thể được xác nhận trước khi trả cache hit.
5. **Rolling deployment phải tránh old/new writer conflict.** Namespace theo representation, dual-read có điều kiện và cấm fallback sang old key thiếu tenant.
6. **Canonicalization phải được định nghĩa độc lập ngôn ngữ.** Ghép chuỗi thô, Map iteration và ID normalization tùy tiện gây semantic/key collisions.
7. **Không để cache key tiết lộ thông tin nhạy cảm.** Encode không phải bảo mật; cân nhắc HMAC, secret rotation, ACL, TLS và hạn chế logs.
8. **TTL và DEL không tự bảo đảm freshness.** Stale refill, event out-of-order, replica lag và L1 invalidation cần xử lý theo hợp đồng nhất quán của API.
9. **Redis Cluster hash tags và cache generation đều có trade-off.** Colocation quá rộng có thể tạo hotspot; thay namespace liên tục có thể gây cold cache.
10. **Đo correctness cùng performance.** Hit rate cao mà lộ dữ liệu giữa tenant vẫn là hệ thống sai nghiêm trọng.

Trước khi đặt một kết quả NoSQL vào cache, hãy hỏi:

> **“Giá trị này thuộc đúng tenant và quyền của ai, được định danh bởi những tham số nào, dùng định dạng phiên bản nào, và khi dữ liệu hoặc chính sách thay đổi thì điều gì bảo đảm cache hit cũ không trả một kết quả sai?”**

Trả lời rõ những câu hỏi đó giúp ứng dụng Java và hệ NoSQL tận dụng cache để giảm độ trễ **mà không đánh đổi tính đúng, khả năng triển khai nhiều phiên bản và an toàn dữ liệu giữa các tenant**.
