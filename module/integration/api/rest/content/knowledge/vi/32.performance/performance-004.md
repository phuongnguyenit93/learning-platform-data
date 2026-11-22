# Kích thước payload, chọn trường và nén phản hồi

## 1. Bài toán: response đúng nhưng quá nặng

Trong module **INTEGRATION_API_REST**, hợp đồng của REST API không chỉ là resource, URI, HTTP method và status code. Một response đúng về nghiệp vụ vẫn có thể làm trải nghiệm kém nếu **payload quá lớn**, khiến thời gian truyền, parse JSON, cấp phát bộ nhớ và vẽ giao diện tăng cao.

Ví dụ hệ thống SaaS có Product API:

- **GET /api/v1/products?limit=20&cursor=...** trả một trang danh sách.
- **GET /api/v1/products/{id}** trả chi tiết sản phẩm.
- **GET /api/v1/products/{id}?fields=id,name,priceMinor,currency** chỉ lấy một tập trường đã được phép.
- **POST /api/v1/products** và **PATCH /api/v1/products/{id}** thay đổi dữ liệu, chịu ràng buộc validation và quyền.
- Client có thể là browser SPA, Java HTTP client hoặc mobile app qua API gateway.

Nếu mỗi item trong danh sách chứa mô tả dài, hàng trăm ảnh, reviews và metadata nội bộ, request một trang 20 item có thể nặng nhiều MB dù UI chỉ dùng **id, name, priceMinor và currency**. Bật gzip có thể giảm số bytes trên mạng nhưng **không chữa việc DB đọc dư, JSON serializer phải xử lý nhiều object, browser parse JSON dư hay dữ liệu bị lộ**.

**Mục tiêu bài học:** bạn sẽ biết đo kích thước payload, xây dựng budget cho list/detail; thiết kế **sparse fieldsets/projection**, tránh overfetching và N+1; thiết lập **Content-Encoding** phù hợp với **Accept-Encoding** (gzip, Brotli khi hỗ trợ); xử lý cache, ETag, Vary, HTTP security; và kiểm thử thực tế bằng Java/Spring, HTTP/curl, JUnit và OpenAPI.

### 1.1. Ba nhóm tối ưu không thay thế nhau

| Cách làm | Đổi điều gì? | Giảm được | Không tự giải quyết |
| --- | --- | --- | --- |
| **Pagination/bounded collection** | Giảm số resource một request | DB work, JSON count, bytes, parse | Item vẫn có thể quá nặng |
| **Field selection / DTO projection** | Giảm trường/association trong representation | Object materialization, serialization, parse, wire bytes | Dữ liệu còn lại có thể lặp và cần nén |
| **HTTP compression** | Giữ cùng nội dung logic nhưng mã hóa bytes trên mạng | Transfer bytes, network time ở liên kết yếu | DB query, overfetching, parsing JSON sau giải nén |

Đôi khi **pagination + DTO projection + compression** đều cần, nhưng mỗi thành phần có chi phí và tác động contract khác nhau. **Performance tối ưu là giảm công việc tổng thể mà không làm sai dữ liệu hoặc bypass authorization.**

## 2. Đo đúng những loại kích thước khác nhau

Một JSON response có ít nhất bốn con số khác nhau:

1. **Kích thước dữ liệu nguồn:** số rows/columns, object được đọc từ DB/cache và dữ liệu lấy qua upstream; còn có N+1/joins.
2. **Serialized JSON bytes (uncompressed):** bytes sau khi server chuyển DTO thành JSON UTF-8, gồm key names, dấu câu, escapes và các chuỗi Unicode.
3. **Encoded body bytes (wire body):** bytes body sau nén gzip/br hoặc identity; có thể được stream theo chunks, không nhất thiết biết trước Content-Length.
4. **End-to-end response cost:** header/TLS/HTTP framing + latency + CPU encode/decode + client JSON parse + allocation; bytes giảm **không luôn kéo latency giảm**.

Ví dụ **minh họa, không phải số đo production**:

| Phương án | JSON chưa nén | Body truyền qua mạng | Các chi phí còn lại |
| --- | ---: | ---: | --- |
| Trả object graph dư thừa | 1.200 KB | 180 KB gzip | DB + serializer + browser parse 1.200 KB |
| Chọn trường cần thiết | 150 KB | 48 KB gzip | DB + serializer + parse nhỏ hơn |
| Chọn trường, không nén | 150 KB | 150 KB identity | Không tốn CPU gzip; có thể tốt trên mạng nhanh |
| Một response JSON rất nhỏ | 400 B | Có thể còn lớn hơn nếu gzip | Header/compression overhead áp đảo |

**Tỷ lệ giảm bytes** = 1 − (encoded body bytes / uncompressed body bytes). Với 150 KB → 48 KB, giảm khoảng 68%. Nhưng đây không phải bằng chứng p95 giảm 68%: request có thể chủ yếu chờ DB hoặc network RTT.

### 2.1. Metrics phải đo theo endpoint và trạng thái

Nên tách theo **route template + method + status class + representation profile**, không dùng raw IDs gây nổ cardinality.

| Metric | Câu hỏi |
| --- | --- |
| **uncompressed response bytes p50/p95** | API đang serialize bao nhiêu dữ liệu logic? |
| **wire response bytes p50/p95** | Nén/caching giúp gì cho đường mạng? |
| **compression ratio / compression CPU** | Lợi ích nén có đáng chi phí CPU không? |
| **server handler + serialization duration** | Bottleneck trước khi phát bytes nằm ở đâu? |
| **TTFB, download duration, total latency p95/p99** | Mạng hay ứng dụng chậm? |
| **DB rows, query count, N+1, pool pending** | Chọn trường đã giảm I/O hay chỉ cắt JSON ở cuối? |
| **client JSON parse time, heap, long tasks** | Payload đã nhẹ đối với mobile/browser chưa? |
| **Cache hit/miss, 304 rate, CDN hit** | Tiết kiệm transfer do cache hay nén? |

HTTP/2 **HPACK** và HTTP/3 **QPACK** nén **headers**, khác với gzip/Brotli cho **response body**. Đừng suy ra HTTP/2 tự nén nội dung JSON.

## 3. Thiết kế payload budget và các mức representation

Đừng bật nén rồi coi response "nhỏ". Trước hết định nghĩa **ngân sách kích thước** cho từng operation, phù hợp thiết bị/mạng và mục tiêu SLO.

Ví dụ ngân sách **giả định để thực hành**:

| Operation | Mục đích | Budget khởi điểm |
| --- | --- | --- |
| GET /products?limit=20 | Card danh sách | ≤100 KB JSON chưa nén/page |
| GET /products/{id} | Chi tiết cơ bản | ≤40 KB JSON chưa nén |
| GET /products/{id}?include=reviews | Chi tiết có reviews | Reviews phân trang riêng, không nhúng vô hạn |
| POST /products | Kết quả tạo resource | 201 + Location + body tối thiểu hoặc full theo contract |
| GET /export-jobs/{id}/result | File xuất dữ liệu | Streaming, quota rows/bytes, lifecycle riêng |

**Budget không phải giới hạn HTTP chung cho mọi endpoint.** File download, export và media streaming có hợp đồng khác JSON API. Khi payload vượt budget, đừng truncate JSON giữa chừng; cần đổi representation, pagination, projection hoặc trả lỗi rõ theo hợp đồng.

### 3.1. Chọn endpoint/shape phù hợp màn hình

Một số lựa chọn:

- **Summary DTO** cho collection, **Detail DTO** cho item; không dùng một entity đầy đủ cho mọi route.
- **Sparse fieldsets** khi client có nhiều nhu cầu thật sự khác nhau và có thể kiểm soát tập field.
- **Resource con và pagination** cho collection như reviews, comments, attachments.
- **include/expand** có allowlist và budget nếu cần bớt round trips; chỉ expand quan hệ có quyền, không expand vô hạn.
- **Compression** cho representation text đủ lớn, sau khi định nghĩa shape.
- **304 Not Modified** cho conditional GET hợp lệ; khi representation không đổi, không truyền lại body.

**Một request lớn không tự tốt hơn nhiều request nhỏ.** Cần cân bằng số round trips, HTTP/2 multiplexing, cache granularity, chính sách tải trước và memory trên client. Với mọi biến thể, đo p95 và bytes thực tế.

## 4. Sparse fieldsets: thiết kế hợp đồng chọn trường

Một cách phổ biến là tham số **fields**:

~~~http
GET /api/v1/products/11111111-1111-4111-8111-111111111111?fields=id,name,priceMinor,currency HTTP/1.1
Authorization: Bearer <token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "id":"11111111-1111-4111-8111-111111111111",
  "name":"Bàn phím cơ",
  "priceMinor":2590000,
  "currency":"VND"
}
~~~

Hợp đồng cần trả lời trước khi implement:

1. **Không có fields**: dùng representation mặc định ổn định hay toàn bộ field được phép? Nên dùng **default projection có chủ đích**, không expose mọi thuộc tính mới của entity.
2. **Fields hợp lệ**: allowlist có version; có field bắt buộc như **id**; không được chọn passwordHash, privateCost hoặc internalNotes chỉ bằng cách đổi query.
3. **Unknown/unauthorized field**: trả **400** khi field không tồn tại, **403/404 hoặc 400 chung** theo privacy policy khi field bị cấm; không để error liệt kê toàn bộ field bí mật.
4. **Trường rỗng vs không được yêu cầu**: field bị omit không đồng nghĩa field có giá trị **null**, collection rỗng hoặc lỗi upstream. Client phải phân biệt.
5. **Canonical order**: các request fields=id,name và fields=name,id có thể cùng projection để tăng cache hit, nhưng canonicalization phải nhất quán.
6. **Giới hạn số field/độ sâu/expand**: đừng cho client biến một field selector thành truy vấn graph vô hạn.
7. **Tài liệu hóa**: projection làm thay đổi properties xuất hiện trong JSON; generated SDK có thể kỳ vọng required fields. Thiết kế schema/profiles và contract test tương thích.

### 4.1. Ngữ nghĩa HTTP của field selection

Với query parameter fields, mỗi URI query khác nhau có thể đại diện một **selected representation** khác nhau. Cache phải tính cả query đầy đủ/canonicalized; không dùng cache key chỉ theo path. Nếu chọn field bằng header tùy biến như **X-Fields**, response cacheable cần **Vary: X-Fields** thích hợp, bên cạnh Accept-Encoding và các Vary khác.

**Chọn field không phải là authorization.** A được phép yêu cầu id,name không có nghĩa A được yêu cầu id,internalCost. Sử dụng **BOLA/BOPLA**: kiểm quyền xem resource và kiểm quyền đọc từng property/association.

### 4.2. Không làm lộ trường qua lỗi và metadata

Các đường rò thường gặp:

- Trả DTO mặc định rồi chỉ ẩn field trong UI, nhưng JSON vẫn chứa **email, internalCost, token**.
- Cho fields=owner.email,adminNotes hoặc expand=tenant.users mà không kiểm ACL.
- Thông báo 400 kèm danh sách **mọi field có thể chọn**, kể cả field không được phép biết.
- Trả count/facets của dữ liệu nằm ngoài scope người gọi.
- Cache projection dành cho admin rồi phát lại cho reader vì key không có tenant/scope.
- Trả ETag/Last-Modified hoặc Content-Length của dữ liệu nhạy cảm bị che theo cách tạo side channel.

Cách an toàn là **field-level allowlist theo role/scope, resource-level ACL, DTO explicit và cache isolation**; không serialize JPA entity nguyên vẹn rồi dựa vào tên field ở frontend để bảo vệ dữ liệu.

## 5. Field selection phải đi qua DB và service, không chỉ JSON serializer

Giả sử DB có 50 cột và entity Product liên kết 1.000 review rows. Nếu backend luôn fetch Product + reviews rồi dùng Jackson bỏ bớt field trong output, **wire bytes giảm nhưng DB query, heap và CPU mapping có thể không giảm**.

~~~mermaid
flowchart TD
  A[Client fields=id,name,priceMinor] --> B[Validate fields + principal]
  B --> C[Authorize tenant/resource/property]
  C --> D[Choose allowed projection and bounded filters]
  D --> E[Query only needed columns/relations]
  E --> F[Map explicit DTO]
  F --> G[JSON serialize / optional compression]
  G --> H[HTTP response with cache/ETag policy]
~~~

**Tối ưu bền vững:** push projection xuống repository/index query khi đáng giá, nhưng vẫn bảo đảm query **tenant-bound và ACL-bound**.

~~~sql
-- Ví dụ SQL cho summary với trusted tenant và scope người gọi.
SELECT p.id, p.name, p.price_minor, p.currency
FROM products p
WHERE p.id = :productId
  AND p.tenant_id = :trustedTenant
  AND p.deleted_at IS NULL
  AND (
    p.visibility = 'TENANT'
    OR p.owner_id = :viewer
    OR EXISTS (
      SELECT 1 FROM product_acl a
      WHERE a.product_id = p.id
        AND a.tenant_id = p.tenant_id
        AND a.user_id = :viewer
        AND a.can_read = TRUE
    )
  );
~~~

**trustedTenant/viewer** đến từ principal đã xác thực; không lấy từ query/body để tự nâng quyền. Predicate ACL trong SQL chỉ là một ví dụ policy; sản phẩm thật có thể có field classification/consent và quyền đọc giá riêng.

### 5.1. Spring Data JPA projection cho trường cố định

~~~java
public interface ProductSummaryView {
    UUID getId();
    String getName();
    long getPriceMinor();
    String getCurrency();
}

public interface ProductRepository extends JpaRepository<Product, UUID> {
    @Query("""
        select p.id as id, p.name as name,
               p.priceMinor as priceMinor,
               p.currency as currency
          from Product p
         where p.id = :id
           and p.tenantId = :tenantId
           and p.deletedAt is null
        """)
    Optional<ProductSummaryView> findSummaryForTenant(
        @Param("id") UUID id,
        @Param("tenantId") UUID tenantId);
}
~~~

Đây là minh họa **projection theo tenant**, chưa đủ cho mọi ACL của hệ thống: service/repository phải thêm predicate owner/ACL/visibility tương ứng với policy thật **trước** khi trả row. Không chỉ kiểm tenant trong query rồi coi việc truy cập object private của user khác là được phép.

**JPA projection** tránh materialize toàn bộ entity ở nhiều trường hợp; với join/collection cần cẩn thận duplicate rows, N+1 và phép phân trang trên fetch join. **Đừng fetch join collection rồi phân trang trong memory** chỉ để tạo một response nhỏ.

### 5.2. SQL động không được ghép raw field name

~~~java
// KHÔNG AN TOÀN:
// String sql = "SELECT " + request.getParameter("fields")
//     + " FROM products WHERE ...";
~~~

Tên cột không thể bind như giá trị SQL parameter thông thường. Nếu thật sự cần **dynamic SQL projection**, ánh xạ mỗi field contract sang một **fragment cố định do server định nghĩa** rồi ghép từ allowlist; giá trị filter/tenant vẫn dùng prepared parameters. Đối với trường hợp đơn giản, **2–3 static DTO projections** thường an toàn và dễ tối ưu hơn một DSL tùy ý.

## 6. Spring MVC: validate fields và trả DTO rõ ràng

Ví dụ minh họa **Spring Boot 3 / Java 17+**. Ứng dụng giả định có **CallerResolver, AuthorizedProductReader** và quyền field do chính ứng dụng triển khai.

~~~java
public record Caller(UUID userId, UUID tenantId, Set<String> scopes) {
    public boolean can(String scope) {
        return scopes.contains(scope);
    }
}

public record ProductRow(
    UUID id, String name, long priceMinor, String currency,
    String description, String internalCost) {}

@Service
public class ProductProjectionService {
    private static final Set<String> PUBLIC_FIELDS =
        Set.of("id", "name", "priceMinor", "currency", "description");

    private final AuthorizedProductReader reader;

    public ProductProjectionService(AuthorizedProductReader reader) {
        this.reader = reader;
    }

    public Map<String, Object> get(
            Caller caller, UUID id, String requestedFields) {

        // Hàm này phải enforce tenant + object ACL tại DB/service.
        ProductRow row = reader.requireVisible(caller, id);

        Set<String> fields;
        if (requestedFields == null || requestedFields.isBlank()) {
            fields = Set.of("id", "name", "priceMinor", "currency");
        } else {
            fields = Arrays.stream(requestedFields.split(",", -1))
                .map(String::trim)
                .collect(Collectors.toSet());

            if (fields.isEmpty() || fields.contains("")
                    || fields.size() > 8
                    || !PUBLIC_FIELDS.containsAll(fields)) {
                throw new InvalidFieldSelectionException();
            }
        }

        // Required field của hợp đồng luôn xuất hiện.
        Set<String> selected = new HashSet<>(fields);
        selected.add("id");

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", row.id());
        if (selected.contains("name")) {
            result.put("name", row.name());
        }
        if (selected.contains("priceMinor")) {
            if (!caller.can("products:price:read")) {
                throw new AccessDeniedException("Price field denied");
            }
            result.put("priceMinor", row.priceMinor());
        }
        if (selected.contains("currency")) {
            result.put("currency", row.currency());
        }
        if (selected.contains("description")) {
            result.put("description", row.description());
        }

        // internalCost không nằm trong allowlist nên không thể serialize.
        return result;
    }
}
~~~

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/v1/products")
public class ProductController {
    private final ProductProjectionService projections;
    private final CallerResolver callerResolver;

    public ProductController(
            ProductProjectionService projections,
            CallerResolver callerResolver) {
        this.projections = projections;
        this.callerResolver = callerResolver;
    }

    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> get(
            @PathVariable UUID id,
            @RequestParam(required = false) String fields,
            Authentication authentication) {

        Caller caller = callerResolver.require(authentication);
        Map<String, Object> body =
            projections.get(caller, id, fields);

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

**Giới hạn có chủ đích của skeleton:**

- **AuthorizedProductReader** và các exception/CallerResolver là abstractions phải định nghĩa; ví dụ không phải project độc lập chạy ngay.
- Service lấy **ProductRow đầy đủ** trước khi chọn fields; nó minh họa **an toàn serialize/allowlist**, **chưa tiết kiệm DB I/O**. Bản production chuyển sang repository projection tương ứng ở mục 5 khi đã đo.
- Price permission được kiểm trước khi trả giá; nếu người dùng có quyền xem product nhưng không xem giá, API phải thống nhất default projection với quyền. Ví dụ default có price và sẽ trả 403 với reader không có permission giá. Có thể định nghĩa default theo scope để không gây bất ngờ.
- Không để fields tự mang **tenantId, ownerId, passwordHash, internalCost**, và không tin client tự tuyên bố có quyền.
- Đối với collection, áp **limit + authorized query** trước projection; xử lý tổng số item/cursor có cùng ACL, không lọc quyền sau LIMIT.
- Với API nhiều variant, cân nhắc **record DTO** hoặc Jackson views cụ thể; tránh phản chiếu entity bằng reflection theo tên client yêu cầu.

## 7. Pagination, include và tránh tăng graph vô hạn

Sparse field selection giải quyết **columns**, nhưng không tự giới hạn **số rows, số associations hoặc nested depth**. Một endpoint có thể bị quá tải bởi:

~~~http
GET /api/v1/products?limit=100000&include=reviews,images,variants
GET /api/v1/products/{id}?include=reviews.comments.author
GET /api/v1/products/{id}?fields=id,variants.reviews.comments
~~~

**Phòng vệ:**

- Limit mặc định và hard cap; ưu tiên **cursor/keyset pagination** khi tập dữ liệu lớn và có cập nhật đồng thời.
- Include/expand là **allowlist riêng**, giới hạn số quan hệ và độ sâu, không tự recursive theo tên field từ user.
- Mỗi collection con có pagination độc lập; trả link tới **/products/{id}/reviews?limit=...** thay vì nhúng hàng nghìn review.
- Bắt buộc **authorization từng relation**; được đọc product không mặc định được đọc review private, owner contact hay internal notes.
- Với DB, hạn chế N+1 bằng batch fetch/projection; không fetch join nhiều collection rồi phân trang trong memory.
- Rate limiting/response size guards phải xét **chi phí query**, không chỉ bytes response cuối. Tăng nén không cứu một SQL query quét hàng triệu rows.

**Ví dụ hợp đồng:** GET /products?limit=20 trả summary DTO; GET /products/{id} trả detail đã bounded; chỉ dùng include=images nếu client cần và có quota ảnh. Payload lớn như export phải dùng **asynchronous job/streaming** thay vì mở rộng list endpoint vô hạn.

## 8. Content negotiation và nén HTTP response

Nén nội dung HTTP là **content coding**, do server và client thương lượng qua **Accept-Encoding**; response dùng **Content-Encoding** để mô tả coding đã chọn. Đây là một cơ chế khác với **Accept** (media type JSON/XML) và **Transfer-Encoding** (cách truyền message trên một hop).

Client thông báo những coding có thể giải mã:

~~~http
GET /api/v1/products?limit=50 HTTP/1.1
Host: api.example.test
Accept: application/json
Accept-Encoding: br, gzip;q=0.9, identity;q=0.5
Authorization: Bearer <token>
~~~

Nếu origin/gateway hỗ trợ Brotli và chọn **br**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: br
Vary: Accept-Encoding
Cache-Control: private, no-store

(binary Brotli-encoded JSON body)
~~~

Nếu hệ thống chỉ hỗ trợ gzip và chọn gzip:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
Cache-Control: private, no-store

(binary gzip-encoded JSON body)
~~~

**Hai response chứa cùng thông tin JSON logic nhưng body bytes khác.** Client giải mã theo Content-Encoding **trước** khi parse JSON. Server không nên gửi Content-Encoding: gzip rồi thực tế phát JSON UTF-8 chưa nén; browser và Java client sẽ báo lỗi decode.

### 8.1. q-value và identity

- **Accept-Encoding: gzip, br**: client thông báo có thể nhận gzip/Brotli; server chọn thuật toán nó hỗ trợ và được client chấp nhận.
- **Accept-Encoding: gzip;q=1, br;q=0.8**: client ưu tiên gzip theo trọng số nếu cả hai có thể đáp ứng; server còn xét thuật toán sẵn có và policy.
- **Accept-Encoding: identity**: muốn dữ liệu không nén.
- **Accept-Encoding: gzip;q=0, identity;q=1**: không chấp nhận gzip, cho phép identity.
- Nếu **identity** chưa bị cấm rõ ràng, server thông thường có thể trả body không nén; không coi việc client gửi Accept-Encoding là bắt buộc phải nén.
- Khi client **từ chối identity và mọi coding khả dụng**, cần xử lý theo negotiation/HTTP semantics, có thể trả **406 Not Acceptable** theo trường hợp, không cố gửi coding client cấm.

**Accept-Encoding** từ browser thường do browser tự điều khiển; frontend fetch không nên tự đặt header rồi kỳ vọng thay cơ chế giải nén của browser. Với Java HttpClient, kiểm API/version để biết client có tự yêu cầu hoặc tự giải mã coding hay không.

### 8.2. Các thuật toán phổ biến và giới hạn

| Coding | Ưu điểm thường gặp | Chi phí/rủi ro |
| --- | --- | --- |
| **identity** | Không tốn CPU nén, thích hợp payload rất nhỏ hoặc đã nén | Nhiều bytes nếu JSON lặp |
| **gzip** | Hỗ trợ rộng, tỷ lệ tốt với JSON/text | CPU encode/decode, gzip level cao tăng CPU |
| **br (Brotli)** | Có thể nén text tốt hơn gzip ở nhiều trường hợp | Encode đắt hơn ở một số mức, support phụ thuộc gateway/container |
| **zstd** | Nén/giải nén nhanh trong nhiều workload, có hỗ trợ ở một số HTTP stacks | Chỉ dùng khi client/server/CDN thực hỗ trợ content coding tương ứng |

**Không giả định mọi servlet container đều hỗ trợ br/zstd chỉ vì client gửi Accept-Encoding.** Nhiều ứng dụng Spring Boot bật gzip ở embedded container, còn Brotli nếu có được thực hiện tại reverse proxy/CDN. Đo trên artifact runtime thật.

Với **JPEG, PNG, MP4, ZIP, gzip file**, nhiều dữ liệu đã được nén; nén thêm thường đem lại ít lợi ích, đôi khi tăng kích thước và CPU. **SVG, HTML, CSS, JSON, text/plain** thường nén tốt hơn. PDF tùy nội dung có thể đã chứa streams nén, cần đo thay vì luôn nén.

## 9. Khi nào nên nén và nơi nào sở hữu việc nén?

Nén không phải "bật là càng nhiều càng tốt": nên dựa vào **Content-Type, kích thước, CPU budget, thiết bị và đường đi qua gateway**.

| Tình huống | Cách chọn |
| --- | --- |
| JSON 200–500 B | Thường ưu tiên identity vì gzip header/CPU overhead |
| JSON nhiều KB, nhiều key lặp | Thử gzip và đo ratio/CPU/latency |
| HTML/CSS/JS asset tĩnh | Có thể precompress và cache edge khi phù hợp |
| Ảnh/video/ZIP đã nén | Bỏ qua hoặc thử nghiệm trước |
| SSE/stream thời gian thực | Tránh buffering do middleware nén khiến event đến trễ |
| File tải bằng byte ranges | Phải bảo toàn semantics Range/Content-Range trên representation được chọn |
| Response có secret cùng input attacker kiểm soát | Đánh giá compression side channel trước khi bật |
| Response lỗi nhỏ | Đo/áp threshold, không ép gzip vì chỉ có 200 bytes |

### 9.1. Chọn một điểm chịu trách nhiệm chính

Có hai cách triển khai phổ biến:

**Nén tại Spring/embedded server:** Spring Boot cấu hình container, server xem Accept-Encoding và response type/size; gateway chuyển tiếp đúng headers/body, không tự nén lại.

**Nén tại gateway/CDN:** backend trả identity, gateway quyết định gzip/br theo client và cache policy. Ưu điểm là gom logic, tận dụng edge; nhưng gateway phải xử lý **Vary, Content-Length, ETag, CORS và lỗi 4xx/5xx** đúng.

**Anti-pattern:** nén hai lần rồi trả Content-Encoding: gzip chỉ một lần, hoặc gateway đổi bytes nhưng giữ **Content-Length** và strong **ETag** không còn đúng representation. Cũng không bỏ Content-Encoding khi body vẫn còn encoded.

### 9.2. Spring Boot 3: cấu hình gzip ở embedded container

Ví dụ **application.yml** theo các thuộc tính cấu hình Spring Boot thông dụng:

~~~yaml
server:
  compression:
    enabled: true
    mime-types:
      - application/json
      - application/problem+json
      - text/plain
      - text/html
      - text/css
      - application/javascript
    min-response-size: 2KB
~~~

Giải thích:

- **enabled** bật response compression mà container hỗ trợ; không tự đảm bảo Brotli.
- **mime-types** là những loại representation có thể được cân nhắc nén.
- **min-response-size** tránh nén quá nhiều response rất nhỏ; threshold nên được đo, không nên copy như một giá trị tối ưu phổ quát.
- Cấu hình thực tế còn phụ thuộc embedded container, compression level/defaults, transfer handling, upstream gateway và status. Phải **test qua HTTP socket thật** thay vì chỉ đọc YAML.
- Một số deployment nén tại ingress/CDN: **không bật chồng** mà thiếu kiểm thử negotiation và validator.

**Không tự nén trong controller bằng GZIPOutputStream** rồi set header/Content-Length tùy tiện. Container/proxy chuẩn thường xử lý stream, flush, transfer và ETag an toàn hơn nếu được cấu hình đồng nhất.

### 9.3. Spring WebClient/RestClient nhận compressed response

Khi gọi upstream, HTTP client có thể quảng cáo Accept-Encoding và/hoặc tự giải mã tùy transport:

- **RestClient + Apache HttpClient 5**: kiểm behavior content compression của Apache client theo configuration thực, nhất là khi đã disable decoder hoặc có gateway ở giữa.
- **WebClient + Reactor Netty**: kiểm option compression/decoder và giữ limit kích thước sau giải nén ở đúng layer.
- **JDK HttpClient**: không suy rằng thêm Accept-Encoding đồng nghĩa Java tự decompress mọi coding; kiểm bằng binary-body test, dùng thư viện giải mã thích hợp nếu cần.
- Client không được parse gzip bytes như JSON khi transport **chưa giải nén**, cũng không được decompress hai lần khi transport đã giải mã.

Bảo vệ **response body max size sau decompression**. Một response nhỏ trên mạng vẫn có thể bung thành JSON khổng lồ trong heap; compressed byte limit và decoded byte limit là hai giới hạn khác nhau.

## 10. Cache, Vary và ETag cho các biến thể

Một URL có thể được trả dưới dạng **identity, gzip hoặc br** tùy **Accept-Encoding**. Cache trung gian phải biết response nào áp dụng cho request nào.

~~~http
GET /api/v1/products/123 HTTP/1.1
Accept-Encoding: gzip
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
ETag: "product-123-fields-default-gzip-v8"
Cache-Control: public, max-age=60

(compressed representation)
~~~

**Ví dụ ETag chỉ minh họa**, không phải pattern bắt buộc và không phù hợp với dữ liệu private nếu chưa có cache authorization policy. **Vary: Accept-Encoding** làm cache phân biệt variants theo request header. Nếu API còn negotiation theo Accept, ngôn ngữ hay header field selector, cần phối hợp **Vary** phù hợp.

### 10.1. ETag phải phản ánh đúng selected representation

**Strong ETag** đại diện cho một representation ở mức đủ để so khớp mạnh. Nếu bytes của **gzip** khác **identity**, không nên dùng **cùng strong ETag** cho hai content-coded representations; đặc biệt nguy hiểm với **Range** và cache. Có thể tính validator riêng cho các biến thể encoded.

**Weak ETag** (bắt đầu bằng W/) có thể biểu diễn tương đương về ngữ nghĩa trong những trường hợp phù hợp, nhưng **không dùng làm strong validator cho If-Match** và byte range. Nếu data API hỗ trợ PATCH với If-Match để tránh lost update, cần phân biệt **validator của representation** với **version của resource nghiệp vụ**, bảo đảm contract concurrency nhất quán.

Đối với **fields=id,name** và **fields=id,name,priceMinor**, JSON representation khác: ETag của bản này không tự dùng cho bản kia. Ngoài content encoding, ETag còn phụ thuộc projection, locale, visibility và policy nếu những yếu tố ấy làm thay đổi nội dung được chọn.

### 10.2. Conditional GET và 304

~~~http
GET /api/v1/products/123?fields=id,name HTTP/1.1
Authorization: Bearer <token>
Accept-Encoding: gzip
If-None-Match: "fields-id-name-gzip-v8"
~~~

Khi representation đã chọn vẫn hợp lệ và caller **vẫn được phép đọc**:

~~~http
HTTP/1.1 304 Not Modified
ETag: "fields-id-name-gzip-v8"
Vary: Accept-Encoding
Cache-Control: private, max-age=0, must-revalidate
~~~

Ví dụ 304 này giả định endpoint **cho phép private cache lưu representation và bắt buộc revalidate**. Với response dùng **no-store** vì dữ liệu quá nhạy cảm, browser/shared cache không nên lưu representation để tái sử dụng; không thiết kế 304 làm tối ưu cache cho trường hợp đó. Response **304 không chứa message body**. Không dùng 304 để bỏ qua xác thực, tenant ACL hoặc để client dùng cache của người khác. Một **200 compressed** và một **304 no body** phải được đo riêng, không tính 304 là JSON payload 0 B từ tính năng compression.

### 10.3. Cache theo quyền của người gọi

Đối với Product API SaaS chứa giá riêng, contract hoặc thông tin tùy quyền:

- Dùng **Cache-Control: private, no-store** cho response nhạy cảm khi phù hợp.
- Nếu có cache ứng dụng/Redis, key theo **tenant, user/permission context, fields, locale/filter, version**, không chỉ productId.
- Không phát lại variant admin cho reader vì cùng URI nhưng Authorization khác.
- Không để user đổi fields query nhưng CDN cache theo path và bỏ query.
- Không cache response 401/403/404 riêng tư bằng chính sách public ngoài ý định.

**no-store không cấm server có cache nội bộ được kiểm soát**, nhưng HTTP cache directive không tự thực hiện DB/Redis authorization policy.

## 11. Compression, Range, HEAD, streaming và lỗi HTTP

Mỗi endpoint có semantics riêng:

| Tình huống | Điều cần giữ đúng |
| --- | --- |
| **HEAD /products/{id}** | Metadata tương ứng selected representation của GET, không có body |
| **304 Not Modified** | Không có body; gửi headers validator/cache cần thiết |
| **204 No Content** | Không có message body; không gửi gzip stream rỗng để "nén" |
| **206 Partial Content** | Dùng cho Range của representation, không phải JSON thiếu trường |
| **Response streaming** | Không serialize toàn bộ vào RAM để tính kích thước rồi mới stream |
| **SSE** | Tránh compressor buffer khiến events đến muộn; flush đúng |
| **Binary/file downloads** | Xem Content-Disposition, Range, checksum, already-compressed |
| **Error responses** | application/problem+json, status/headers vẫn đúng khi gateway nén |
| **CORS** | Browser phải đọc được response đúng origin; compression không thay CORS |

Nếu client yêu cầu **Range: bytes=...**, byte ranges áp trên selected representation ở tầng HTTP. Khi content coding thay đổi bytes của representation, **Content-Range, Content-Length và validator** phải phản ánh variant chính xác. Với media/video/download đã nén, nhiều hệ thống **không gzip thêm** để giữ Range đơn giản, nhưng quyết định cần kiểm thử end-to-end.

**Transfer-Encoding: chunked** là message framing của HTTP/1.1, không phải gzip. **Content-Length** nếu có là số bytes của body đã encoded trong message đang truyền; với streaming có thể không được biết trước hoặc không gửi header này. Khi proxy nén/giải nén lại, nó phải điều chỉnh/loại bỏ Content-Length không còn đúng và giữ integrity.

## 12. Rủi ro bảo mật khi chọn trường và nén

### 12.1. BOLA/BOPLA: field selection không cấp thêm quyền

Giả sử user A đọc được product nhưng không có quyền **internalCost**. Request:

~~~http
GET /api/v1/products/123?fields=id,name,internalCost HTTP/1.1
Authorization: Bearer <token-reader>
~~~

Phải bị từ chối hoặc áp chính sách chỉ trả field được phép **có thông báo rõ**. Không trả internalCost, dù dữ liệu đã nằm trong entity/cache. Truy vấn search, sort, facets và include cũng phải dùng **allowlist theo quyền**, vì ngay cả khi response không chứa field bí mật, việc lọc/sắp xếp trên field đó có thể rò thông tin.

**Không dùng reflection tùy ý**, ví dụ map request fields trực tiếp thành getter của entity rồi serialize: vừa có nguy cơ BOPLA vừa mở ra độ sâu/chi phí object graph không giới hạn.

### 12.2. Compression side channel

Nếu response **đồng thời chứa secret phản hồi về cho browser (ví dụ CSRF token hoặc dữ liệu session) và chuỗi attacker có thể điều khiển**, độ dài của body nén có thể rò thông tin về secret khi attacker quan sát được nhiều lần (họ attack họ **BREACH-like compression oracle**). Rủi ro phụ thuộc mô hình ứng dụng/origin và khả năng quan sát độ dài, không phải mọi JSON dùng gzip đều dễ bị khai thác.

Biện pháp tùy threat model:

- Tránh đưa **secret và dữ liệu attacker-controlled** vào cùng compressed response; tách response nếu khả thi.
- Với response rất nhạy cảm, cân nhắc **không nén** hoặc dùng thiết kế giảm khả năng quan sát độ dài; không tin chỉ giảm compression level đã loại bỏ side channel.
- Dùng CSRF protections, cookie attributes, origin/authorization checks và token design phù hợp; **CORS không loại bỏ mọi kênh quan sát**.
- Không phản chiếu dữ liệu đầu vào chứa secret vào error/log/body.
- Kiểm cả **compression tại CDN/gateway**, vì tắt ở Spring nhưng bật ở edge vẫn còn rủi ro.

### 12.3. Compression bombs và input bodies

Khi API nhận request có **Content-Encoding: gzip** (nếu server thực sự hỗ trợ), một body nén 1 MB có thể bung thành hàng trăm MB JSON. Cần giới hạn **compressed bytes, uncompressed bytes, nesting depth, collection counts, CPU và thời gian giải nén**. Nếu server không hỗ trợ content coding của request, trả lỗi như **415 Unsupported Media Type** theo contract thay vì parse bytes lạ như JSON.

Response nén từ upstream cũng cần decoded-size cap để tránh memory exhaustion. Không suy rằng **Content-Length nhỏ** thì sau giải nén cũng nhỏ. Với XML/JSON parser, đặt các hạn mức an toàn độc lập với transport.

## 13. Nén ảnh hưởng latency và CPU thế nào?

Ở mạng yếu, truyền 50 KB thay vì 200 KB có thể giảm đáng kể download time. Nhưng khi server CPU saturation, nén hàng nghìn JSON response mỗi giây ở compression level nặng có thể làm **p99 tệ hơn**, tăng GC/thread contention và gây queue.

Một mô hình hiệu năng đơn giản:

~~~text
Response total time
  = DB/service time
  + serialization time
  + compression CPU/queue time
  + transfer/network time
  + client decompression + JSON parse + render
~~~

Các bước có thể **overlap/pipeline/stream**, nên không thể cộng cứng mọi thành phần cho mọi request. Cần đo riêng ở CPU-limited, network-limited, mobile-limited scenarios.

### 13.1. Thử nhiều tổ hợp thay vì chỉ bật/tắt gzip

| Variant | Tối ưu được kiểm tra |
| --- | --- |
| Full DTO + identity | Baseline hiện tại |
| Full DTO + gzip | Hiệu quả nén thuần túy |
| Summary DTO + identity | Lợi ích giảm dữ liệu trước network |
| Summary DTO + gzip | Kết hợp projection và compression |
| Summary DTO + br (nếu có hỗ trợ) | So br với gzip về CPU/wire bytes/p95 |
| Summary DTO + conditional GET 304 | Lợi ích cache validation cho dữ liệu không đổi |

So sánh **same route, same fixture, same user permissions, same load profile**. Ghi cả average và **p95/p99**, bytes uncompressed/wire, CPU, memory, DB queries và client decode/parse cost. Có thể gzip thắng về bytes nhưng thua về latency khi CPU bị quá tải; khi đó giảm level, tăng threshold, chuyển compression ra edge hoặc bỏ nén với một số type/response.

**Đo khi load generator đạt target arrival rate**; nếu VUs hoặc CPU generator bão hòa, kết quả về server có thể sai. Tách warm/cold cache, HTTP/1.1 vs HTTP/2, network RTT và TLS reuse.

## 14. Kiểm thử nén và field selection qua HTTP thực

**MockMvc** kiểm routing, validation, controller và Spring Security, nhưng thường **không chạy qua embedded HTTP connector** chịu trách nhiệm gzip. Vì vậy cần **@SpringBootTest(webEnvironment = RANDOM_PORT)** hoặc endpoint staging qua gateway để kiểm body bytes đã được mã hóa thực sự.

### 14.1. JUnit 5 + JDK HttpClient kiểm gzip

Tạo product fixture có description dài, ổn định, dễ nén và vượt ngưỡng 2 KB. Ví dụ dưới đây dùng JDK HttpClient với explicit Accept-Encoding và lấy binary response:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class CompressionHttpIT {
    @LocalServerPort
    int port;

    @Autowired
    TestTokenFactory tokens;

    @Test
    void gzipDecodesToSameRepresentationAsIdentity()
            throws Exception {
        String url = "http://localhost:" + port
            + "/api/v1/products/" + TestIds.LARGE_PRODUCT;
        String token = tokens.readerWithPriceScope();
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest gzip = HttpRequest.newBuilder(
                URI.create(url))
            .header("Authorization", "Bearer " + token)
            .header("Accept-Encoding", "gzip")
            .GET().build();

        HttpResponse<byte[]> zipped = client.send(
            gzip, HttpResponse.BodyHandlers.ofByteArray());
        assertEquals(200, zipped.statusCode());
        assertEquals("gzip", zipped.headers()
            .firstValue("Content-Encoding").orElse(""));

        byte[] raw;
        try (GZIPInputStream stream = new GZIPInputStream(
                new ByteArrayInputStream(zipped.body()))) {
            raw = stream.readAllBytes();
        }

        HttpRequest identity = HttpRequest.newBuilder(
                URI.create(url))
            .header("Authorization", "Bearer " + token)
            .header("Accept-Encoding", "identity")
            .GET().build();
        HttpResponse<byte[]> plain = client.send(
            identity, HttpResponse.BodyHandlers.ofByteArray());

        assertEquals(200, plain.statusCode());
        assertArrayEquals(plain.body(), raw);
        assertTrue(zipped.body().length < raw.length);
    }
}
~~~

Các lớp **TestTokenFactory/TestIds** là test fixtures tự xây; bổ sung imports JUnit, SpringBootTest, java.net.http, ByteArrayInputStream, GZIPInputStream. Test yêu cầu **JSON cùng nội dung giữa hai GET** và server thật sự nén; nếu JSON có timestamp thay đổi từng request hoặc response quá nhỏ, so bytes không hợp lệ.

Một số HTTP libraries **tự động decompress**; phải biết cách lấy encoded body để kiểm byte thực. JDK HttpClient/transport cũng cần được kiểm theo phiên bản và cấu hình đang chạy, đừng suy đoán từ việc chỉ thêm header.

### 14.2. REST Assured kiểm fieldset và BOPLA

~~~java
@Test
void sparseFieldsetDoesNotExposeHiddenData() {
    Response response = given()
        .spec(api())
        .auth().oauth2(readerToken)
        .queryParam("fields", "id,name")
    .when()
        .get("/products/{id}", productId)
    .then()
        .statusCode(200)
        .contentType(ContentType.JSON)
        .extract().response();

    Map<String, Object> body = response.jsonPath().getMap("$");
    assertEquals(productId, body.get("id"));
    assertTrue(body.containsKey("name"));
    assertFalse(body.containsKey("priceMinor"));
    assertFalse(body.containsKey("internalCost"));
}
~~~

Dùng token reader **không có products:price:read** để thử fields=id,priceMinor và xác minh 403 như skeleton mục 6. Với product thuộc tenant khác, kiểm 403/404 và **không có metadata nhạy cảm**. Response JSON đúng chưa chứng minh SQL projection tối ưu; cần đo DB query count/rows và heap.

### 14.3. Kiểm qua curl và browser

~~~bash
curl -i --compressed \
  -H 'Authorization: Bearer <test-token>' \
  'https://api.example.test/api/v1/products/123?fields=id,name'

curl -i \
  -H 'Accept-Encoding: identity' \
  -H 'Authorization: Bearer <test-token>' \
  'https://api.example.test/api/v1/products/123?fields=id,name'
~~~

**curl --compressed** yêu cầu encoding mà curl hỗ trợ và thường tự giải nén khi hiển thị, nên body nhìn thấy **không phải raw gzip bytes**. Muốn đo wire bytes chính xác, dùng capture/download không tự decode và ghi rõ có tính header/TLS/framing không. Trong browser, fetch thường cung cấp nội dung **đã giải nén** cho JavaScript; không coi độ dài chuỗi JS là số bytes trên mạng.

## 15. Ma trận kiểm thử HTTP, hiệu năng và an toàn

| ID | Tình huống | Tiêu chí |
| --- | --- | --- |
| P01 | GET default projection | Chỉ field hợp đồng mặc định |
| P02 | fields=id,name | Không có price/internalCost |
| P03 | Field lạ, rỗng hoặc quá giới hạn | 400/contract error, không truy vấn vô hạn |
| P04 | Field bí mật hoặc thiếu scope giá | Không lộ BOPLA |
| P05 | Resource tenant khác | Không lộ dữ liệu, 403/404 theo policy |
| P06 | Pagination + fieldsets | Limit/cursor/ACL đúng, không N+1 |
| P07 | include/expand quá sâu | Bounded/reject rõ |
| C01 | JSON lớn, Accept-Encoding: gzip | Có Content-Encoding gzip và decoded JSON đúng |
| C02 | Accept-Encoding: identity | Không gửi gzip |
| C03 | JSON nhỏ hoặc media đã nén | Không ép gzip vô ích |
| C04 | Client chỉ hỗ trợ br, backend chỉ gzip | Không gửi coding client không nhận |
| C05 | Gateway và Spring cùng cấu hình nén | Không double gzip/sai Content-Length |
| C06 | Vary: Accept-Encoding + cache | Không reuse sai variant |
| C07 | Strong ETag: gzip, identity, các fieldsets | Validator đúng selected representation |
| C08 | 304/204 | Không có message body |
| C09 | Range/206 cho file | Content-Range/bytes/validator nhất quán |
| S01 | Cache user A/admin sang user B | Không phát lại data trái quyền |
| S02 | JSON nén nhỏ bung thành rất lớn | Decoded size/depth/CPU caps |
| S03 | Secret cùng input attacker-controlled | Compression side-channel review |
| M01 | Full vs summary + identity/gzip | So raw/wire bytes, p95, CPU, DB work |
| M02 | HTTP/1.1 vs HTTP/2; warm/cold cache | Kết quả tách cấu hình |
| M03 | Tải cao/cpu saturation | Nén không làm p99 xấu vượt SLO |

Các case cần **dữ liệu synthetic, nhiều tenant/role, body sizes đa dạng** và kiểm đúng response trạng thái lỗi, không chỉ happy path. Với nén, cần assert **cả encoded bytes, nội dung sau decode và headers**.

## 16. OpenAPI 3.1: hợp đồng cho sparse fields

OpenAPI mô tả request/response và security, nhưng không tự kiểm quyền field hay tối ưu SQL:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: 1.0.0
paths:
  /api/v1/products/{id}:
    get:
      operationId: getProduct
      security: [{ bearerAuth: [] }]
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
        - in: query
          name: fields
          description: >
            CSV tên field được phép, id luôn hiện diện.
            Field ngoài quyền sẽ bị từ chối.
          schema: { type: string, maxLength: 150 }
          example: id,name,priceMinor,currency
      responses:
        '200':
          description: Product theo projection đã authorize
          headers:
            ETag:
              schema: { type: string }
            Vary:
              schema: { type: string }
            Cache-Control:
              schema: { type: string }
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductProjection'
        '400': { description: Field selector không hợp lệ }
        '401': { description: Chưa xác thực }
        '403': { description: Không có quyền xem field/resource }
        '404': { description: Product không được công bố }
        '406': { description: Không có representation chấp nhận được }
        '429': { description: Vượt quota }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
  schemas:
    ProductProjection:
      type: object
      required: [id]
      additionalProperties: false
      properties:
        id: { type: string, format: uuid }
        name: { type: string }
        priceMinor: { type: integer, format: int64, minimum: 0 }
        currency: { type: string }
        description: { type: string }
~~~

Với projection linh hoạt, **id** là trường required; các field khác có thể vắng vì client không yêu cầu. Nếu list endpoint luôn trả summary cố định, nên có **schema ProductSummary riêng** chặt hơn. JSON Schema không thể thay field-level permission của server.

**Accept-Encoding/Content-Encoding là cơ chế HTTP**, không phải query param bắt buộc. OpenAPI không tự áp compression/ETag/caching đúng. Trong production cần thêm response schemas cho lỗi, cursor collection, scopes theo role, conditional requests và các ví dụ nén/không nén.

## 17. Benchmark: so projection và nén bằng số liệu thực

Một benchmark tái hiện được phải dùng cùng **fixtures, identity, method, routing, load profile và cache state**:

1. Seed sản phẩm nhỏ, trung bình và lớn (ví dụ raw JSON 1 KB/10 KB/100 KB), cả text lặp lẫn text khó nén.
2. Đo **Full DTO + identity**, **Full DTO + gzip**, **Summary DTO + identity**, **Summary DTO + gzip**, và br khi stack hỗ trợ.
3. Warm-up phù hợp, rồi phát tải có **arrival rate ổn định**, ghi đạt bao nhiêu RPS và dropped iterations.
4. Đo **DB rows/query count, uncompressed JSON bytes, wire body bytes, server CPU, p95/p99, browser/mobile decode/parse**.
5. Thử một network latency/bandwidth profile riêng; so kết quả qua HTTP/1.1 vs HTTP/2 và cache cold/warm.
6. Lặp lại trên cùng git commit/config và ghi artifact/report; không suy từ một lần chạy ngắn ra p99 production.

| Biến thể | Raw KB | Wire KB | p95 ms | CPU% | DB queries | Nhận định |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Full + identity | — | — | — | — | — | Baseline |
| Full + gzip | — | — | — | — | — | Nén đơn thuần |
| Summary + identity | — | — | — | — | — | Giảm dữ liệu |
| Summary + gzip | — | — | — | — | — | Kết hợp |
| Summary + br | — | — | — | — | — | Chỉ khi hỗ trợ |
| Summary + 304 | — | 0 body | — | — | — | Conditional cache |

**Đừng lấy trung bình p95 từ các pods rồi gọi là p95 toàn hệ thống.** Cần histogram/distribution phù hợp; cũng đừng gọi compression tốt khi bytes giảm nhưng CPU và p99 tệ hơn. Kiểm load generator có thực sự đạt target trước khi kết luận.

## 18. Những anti-pattern phổ biến

| Sai lầm | Tác hại | Cách khắc phục |
| --- | --- | --- |
| Serialize JPA entity nguyên vẹn | Overfetch, lộ BOPLA, N+1 | Explicit summary/detail DTO |
| @JsonIgnore được coi là DB projection | DB vẫn đọc cột dư | Repository projection |
| Cho fields biến thành raw SQL | Injection, lộ schema | Allowlist server-defined columns |
| Cho include/expand không giới hạn | Query/JSON graph bùng nổ | Bound depth, page và quota |
| Gzip mọi response vài trăm bytes | Tăng overhead CPU/bytes | Threshold và MIME types |
| Gzip lại ZIP/PNG/MP4 | Ít lợi ích, tốn CPU | Bỏ qua already-compressed |
| Double gzip tại Spring và gateway | Sai Content-Encoding/Length | Ownership rõ |
| Strong ETag giống cho gzip/identity | Range/cache có thể sai | Validator theo variant |
| Quên Vary: Accept-Encoding | CDN đưa sai coding | Negotiation-aware cache |
| Cache theo productId không tenant | Rò dữ liệu riêng tư | Scope/permission cache key |
| Chỉ tắt gzip tại Spring để chống BREACH | Edge vẫn có thể nén | Review cả đường đi |
| Test gzip chỉ qua MockMvc | Không chạy server compression | RANDOM_PORT/raw bytes |
| Đo chỉ Content-Length | Chunked/stream/proxy làm sai | Đo thực bytes từng tầng |

## 19. Bài thực hành: tối ưu Product API an toàn

**Bối cảnh:** Spring Boot 3 + PostgreSQL + gateway, Product API đa tenant có id/name/price/currency/description/reviews/images. Trang list chỉ cần bốn trường nhưng currently tải toàn entity, 20 items tạo response lớn.

**Nhiệm vụ (100 điểm):**

1. **Thiết kế – 25:** xác định payload budget list/detail, phân biệt JSON/wire bytes; chọn summary/detail DTO, limit/cursor và fieldset allowlist.
2. **Java/Spring – 30:** implement GET detail với fields, kiểm tenant + object ACL + field permission; dùng repository projection để giảm DB work, không chỉ ẩn JSON.
3. **HTTP/bảo mật – 25:** configure gzip threshold và gateway ownership; trình bày identity/gzip, Vary/ETag/Cache-Control, 304 so với 206; test unauthorized fields, cache isolation và sensitive compression.
4. **Đo/kiểm thử – 20:** ít nhất 12 test ở mục 15, so Full/Summary × identity/gzip về bytes, p95, CPU, DB queries; giải thích vì sao bytes giảm chưa chắc p99 tốt hơn.

**Gợi ý:** ưu tiên bounded collections và SQL projection, rồi đo gzip cho JSON đủ lớn. Field selector chỉ lấy field được phép, không có internalCost. ETag và cache phải theo representation và caller scope; tránh dùng shared cache cho data riêng. Không tuyên bố tối ưu thành công nếu query vẫn N+1 hoặc CPU compression làm latency tăng.

## 20. Checklist và tài liệu chuẩn

- [ ] Đo riêng DB work, raw JSON bytes, encoded body, p95/p99 và client parse.
- [ ] Dùng DTO summary/detail, projection DB, tránh N+1.
- [ ] Collection có limit/cursor; include/expand có depth/size caps.
- [ ] Sparse fieldsets có allowlist, required IDs, field-level ACL.
- [ ] Compression negotiation đúng Accept-Encoding/Content-Encoding, MIME, threshold.
- [ ] Spring/gateway/CDN không nén trùng, không phát headers sai.
- [ ] Vary, ETag, conditional GET/304, Range/206 theo variant.
- [ ] Không ép gzip lên stream nhỏ, ảnh/video/ZIP đã nén.
- [ ] Có protection chống compression side channel và decompression bomb.
- [ ] Test qua HTTP thật, có raw/decoded bytes, nhiều tenant và quota.
- [ ] Benchmark được lặp, ghi CPU, latency, bytes và DB cost.

**Ghi nhớ:** giảm lượng dữ liệu không cần thiết trước, nén phù hợp sau. API nhanh nhưng vẫn phải **đúng hợp đồng HTTP, đúng quyền và đo được cải thiện thực sự**.

**Tham khảo:** RFC 9110 (Content-Encoding, Accept-Encoding, Range, 206/304), RFC 9111 (HTTP Caching, Vary), Spring Boot Server Compression/Spring MVC/Data/Security, OpenAPI 3.1, MDN Content Negotiation/Content-Encoding, OWASP API Security (BOLA/BOPLA/resource consumption) và tài liệu về BREACH/compression side channels.
