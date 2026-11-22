# Ánh xạ phân trang, sắp xếp và giới hạn truy vấn

## 1. Từ query string đến truy vấn có kiểm soát

Client gọi REST API:

~~~http
GET /api/orders?page=0&size=20&sort=createdAt,desc&sort=id,desc&status=PAID HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Client muốn **20 đơn PAID**, mới nhất trước và `id` làm tie-breaker. Nếu server đưa thẳng `size=1000000`, `page=999999` hoặc `sort=customer.password` xuống ORM, truy vấn có thể rất tốn kém hoặc lộ thông tin.

Bài **“Ánh xạ phân trang, sắp xếp và giới hạn truy vấn”** thuộc chương **Spring MVC** của module **INTEGRATION_API_REST**, liên hệ resource/URI, HTTP, OpenAPI, cache, phân quyền và kiểm thử Java/Spring.

Mục tiêu: bind `page/size/sort` đúng, kiểm soát giới hạn và field được phép, chọn `Page`/`Slice`/cursor theo chi phí, lọc tenant **trước phân trang** và kiểm thử hợp đồng.

> **Query parameters là dữ liệu không tin cậy.** Spring xử lý binding; validation, quyền và giới hạn tải là trách nhiệm của API.

## 2. Hợp đồng HTTP cho collection

| Tham số | Mặc định và giới hạn ví dụ |
|---|---|
| `page` | **0-based**, mặc định 0, số nguyên không âm |
| `size` | Mặc định 20, cho phép **1..100** |
| `sort` | Lặp được: `field,asc` hoặc `field,desc`; field `createdAt/totalMinor/id`, tối đa 3 field |
| `status` | Enum `PAID/PENDING/CANCELLED`, có thể bỏ qua |
| `page×size` | **Không quá 10.000** (ví dụ giới hạn offset) |

Đây là policy của API minh họa, **không phải mặc định REST/Spring**. `GET /api/orders` trả **200 với items rỗng** nếu trang hợp lệ nhưng không còn dữ liệu; query sai policy trả **400**.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{"items":[{"id":"o-913","createdAt":"2026-11-18T09:30:00Z",
          "status":"PAID","totalMinor":150000}],
 "page":0,"size":20,"totalElements":52,"totalPages":3,"hasNext":true}
~~~

`totalElements` thường dựa trên **COUNT query** và phản ánh thời điểm quan sát, không cố định giữa các request khi dữ liệu thay đổi. `no-store` là chính sách bảo thủ cho đơn riêng tư, không bắt buộc với collection công khai.

Đa cấp sort dùng **query parameter lặp theo thứ tự**: `sort=createdAt,desc&sort=id,asc`. Hợp đồng phải nêu cách xử lý duplicate field, direction sai và default tie-breaker.

## 3. Binding: `@RequestParam` và Spring Data Web `Pageable`

**Spring MVC** hỗ trợ ánh xạ kiểu:

~~~java
@GetMapping("/api/orders")
ResponseEntity<?> list(
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size) {
    // Validate page/size trước khi truy vấn.
    return ResponseEntity.ok().build();
}
~~~

`page=abc` không chuyển được sang `int` nên thường nhận **400** qua handler lỗi conversion. Nhưng `page=-1` hoặc `size=1000000` vẫn là số hợp lệ về **kiểu**, phải được kiểm soát bởi validation. Có thể dùng Bean Validation `@Min/@Max` và method validation phù hợp phiên bản Spring/config, hoặc code kiểm tra tường minh.

Với **Spring Data Web support**, `PageableHandlerMethodArgumentResolver` bind `page,size,sort` thành `Pageable`:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;

@GetMapping("/api/orders")
ResponseEntity<?> list(
    @PageableDefault(page = 0, size = 20,
        sort = {"createdAt", "id"},
        direction = Sort.Direction.DESC)
    Pageable pageable) {
    return ResponseEntity.ok().build();
}
~~~

Có thể cấu hình trong Spring Boot:

~~~yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
        one-indexed-parameters: false
~~~

`Pageable` **thuộc Spring Data, không phải Spring MVC core**. Resolver có thể **cap size** thay vì trả 400; `@PageableDefault` không bảo đảm whitelist sort. Nếu hợp đồng yêu cầu **strict 400**, phải tự validate trước khi tạo request repository. Dùng `@RequestParam` khi cần kiểm soát chặt input; dùng `Pageable` khi chấp nhận conventions và đã bổ sung guardrails.

## 4. Giới hạn truy vấn trước database

`page=25000&size=50` tạo offset **1.250.000**: DB có thể phải duyệt nhiều row dù chỉ trả 50. Quy trình an toàn: parse số → validate `page/size/offset` → whitelist sort/filter → xác định tenant từ security context → tạo `PageRequest` → truy vấn với index/timeout.

~~~java
final class PageLimits {
    static final int MAX_SIZE = 100;
    static final long MAX_OFFSET = 10_000;

    static void validate(int page, int size) {
        if (page < 0 || size < 1 || size > MAX_SIZE)
            throw new InvalidCollectionQuery(
                "page >= 0 và size phải trong 1..100");
        if ((long) page * size > MAX_OFFSET)
            throw new InvalidCollectionQuery(
                "Offset quá sâu; hãy dùng cursor pagination");
    }
}
~~~

Phép nhân trên `long` tránh overflow `int`. `InvalidCollectionQuery` là exception ứng dụng, ánh xạ 400 ở mục 11.

**Strict vs lenient:** có thể reject `size=5000` bằng 400 hoặc cap về 100; nếu cap phải **trả size hiệu lực** cho client. Chọn một chính sách và test. Max size/offset **không thay** index, query timeout, rate limit, giới hạn joins/filters và giám sát DB.

## 5. Sắp xếp ổn định: whitelist field, direction và tie-breaker

Giả sử hai đơn có cùng `createdAt`. Chỉ `ORDER BY created_at DESC` chưa đủ để xác định thứ tự **giữa các bản ghi bằng nhau**. Nếu DB đổi execution plan giữa hai page requests, client có thể thấy item lặp hoặc bỏ sót dù dữ liệu không đổi.

Hợp đồng mặc định:

~~~sql
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

`id` là **tie-breaker duy nhất**. Nếu client yêu cầu `sort=totalMinor,asc`, backend sử dụng `ORDER BY total_minor ASC, id DESC` khi `id` chưa được chỉ định, để luôn có thứ tự toàn phần.

**Chú ý:** Tie-breaker giải quyết trường hợp **các sort keys bằng nhau tại một snapshot**; nó **không thể chặn** item bị dịch trang khi có insert/delete hoặc trường sort bị cập nhật giữa hai request. Với dataset biến động nhanh, dùng cursor/keyset hoặc snapshot thích hợp.

### Không tin property name từ client

Đầu vào `sort=customer.password,asc` hoặc `sort=items.someLargeJoin,desc` không được chuyển thẳng thành `Sort.by(...)`. Ngay cả khi ORM tránh SQL injection bằng API của nó, **sort property không được phép** vẫn gây lỗi, lộ cấu trúc entity hoặc làm truy vấn cực đắt. Tương tự không dùng `JpaSort.unsafe` với chuỗi chưa kiểm chứng.

**Whitelist** ví dụ:

| Field công khai | Property entity nội bộ | Có cho phép? |
|---|---|---|
| `createdAt` | `createdAt` | Có |
| `totalMinor` | `totalMinor` | Có, nếu user có quyền xem giá |
| `id` | `id` | Có, làm tie-breaker |
| `customer.password` | Không ánh xạ | Không |
| `computedRiskScore` | Dữ liệu đặc quyền | Không trên API công khai |

### Parser `sort` có thể tái sử dụng trong application layer

~~~java
import java.util.*;
import org.springframework.data.domain.Sort;

final class OrderSortPolicy {
    private static final Map<String, String> FIELDS = Map.of(
        "createdAt", "createdAt",
        "totalMinor", "totalMinor",
        "id", "id");

    static Sort parse(List<String> values) {
        if (values == null || values.isEmpty()) {
            return Sort.by(
                new Sort.Order(Sort.Direction.DESC, "createdAt"),
                new Sort.Order(Sort.Direction.DESC, "id"));
        }
        if (values.size() > 3) {
            throw new InvalidCollectionQuery("Tối đa ba sort fields");
        }

        List<Sort.Order> orders = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (String value : values) {
            String[] parts = value.split(",", -1);
            if (parts.length != 2) {
                throw new InvalidCollectionQuery(
                    "sort phải có dạng field,asc hoặc field,desc");
            }
            String field = parts[0].trim();
            String property = FIELDS.get(field);
            if (property == null || !seen.add(field)) {
                throw new InvalidCollectionQuery(
                    "Trường sort không được phép hoặc bị lặp");
            }
            Sort.Direction direction;
            switch (parts[1].trim().toLowerCase(Locale.ROOT)) {
                case "asc" -> direction = Sort.Direction.ASC;
                case "desc" -> direction = Sort.Direction.DESC;
                default -> throw new InvalidCollectionQuery(
                    "Direction phải là asc hoặc desc");
            }
            orders.add(new Sort.Order(direction, property));
        }
        if (!seen.contains("id")) {
            orders.add(new Sort.Order(Sort.Direction.DESC, "id"));
        }
        return Sort.by(orders);
    }
}
~~~

Ở đây `sort=createdAt,desc&sort=id,asc` là hai phần tử `List<String>`. Nếu `sort=createdAt,desc` được gửi lặp với cùng field, parser **trả 400**, không âm thầm lấy giá trị đầu/cuối. Có thể mở rộng cho `nullsFirst/nullsLast` hoặc case-insensitive sorting nhưng phải xác nhận **database collation, index và hiệu năng**; không tùy tiện chấp nhận function name từ input.

## 6. Controller Spring MVC hoàn chỉnh theo hợp đồng strict

Để giữ chính xác **các giá trị `sort` lặp theo thứ tự HTTP**, ta đọc chúng bằng `MultiValueMap`. `page/size` vẫn dùng `@RequestParam` có conversion; phần logic truy vấn nằm ở service.

~~~java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;

record OrderView(
    String id, String status, long totalMinor, String createdAt) {}
record OrderPage(
    List<OrderView> items, int page, int size,
    long totalElements, int totalPages, boolean hasNext) {}
class InvalidCollectionQuery extends RuntimeException {
    InvalidCollectionQuery(String message) { super(message); }
}

interface OrderSearchService {
    // Service bắt buộc ràng buộc tenant và quyền trong query.
    Page<OrderView> findVisible(
        Authentication principal, String status, PageRequest pageable);
}

@RestController
@RequestMapping("/api/orders")
class OrderListController {
    private final OrderSearchService service;
    OrderListController(OrderSearchService service) {
        this.service = service;
    }

    @GetMapping
    ResponseEntity<OrderPage> list(
        Authentication principal,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(required = false) String status,
        @RequestParam MultiValueMap<String, String> params) {

        PageLimits.validate(page, size);
        Sort sort = OrderSortPolicy.parse(params.get("sort"));
        // Validate status theo enum/whitelist trong service.
        PageRequest pageable = PageRequest.of(page, size, sort);
        Page<OrderView> result =
            service.findVisible(principal, status, pageable);

        OrderPage body = new OrderPage(
            result.getContent(),
            page, size,
            result.getTotalElements(),
            result.getTotalPages(),
            result.hasNext());

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

**Cần phân biệt rõ phạm vi:** Đây là skeleton ở cấp MVC/service, không phải project hoàn chỉnh có sẵn repository, authentication và fixture. `MultiValueMap` nhận `sort` đúng các lần xuất hiện trong query string; `PageRequest.of` chỉ được gọi **sau validation**.

Với `status`, ứng dụng nên sử dụng một enum/whitelist rõ, ví dụ `PAID/PENDING/CANCELLED`, và từ chối giá trị không hợp lệ bằng 400. Nếu `status` xuất hiện nhiều lần mà hợp đồng chỉ cho một giá trị, phải **phát hiện và từ chối duplicate**, thay vì để cách binding ngầm quyết định lấy phần tử nào. Với dữ liệu riêng tư, `no-store` là lựa chọn bảo thủ; không thay cho authorization.

### Tại sao không trả thẳng `Page<OrderEntity>`?

`Page`/entity là **mô hình thư viện/lưu trữ**, không nhất thiết là HTTP contract ổn định. Trả entity trực tiếp có thể tiết lộ nội bộ (`tenantId`, quan hệ ORM lazy, trường bảo mật) hoặc phụ thuộc vào cách serializer thể hiện `Page` của từng version. Dùng **DTO/envelope do API sở hữu** và mô tả cụ thể trong OpenAPI.

## 7. Service/Repository: lọc quyền trước LIMIT, OFFSET và COUNT

Một repository Spring Data JPA minh họa:

~~~java
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
    Page<OrderEntity> findByTenantIdAndStatus(
        String tenantId, OrderStatus status, Pageable pageable);
}
~~~

Trong service: lấy tenant từ **Authentication đã xác thực**, validate `status`, đưa predicate **`tenant_id = :tenant`** vào SQL **trước paging/count**, map entity thành `OrderView` chỉ có các field được phép. Nếu status optional, xây query phù hợp; không coi `status = NULL` là bỏ lọc. Không dùng `findAll(pageable)` rồi lọc tenant trong Java: vừa làm sai tổng vừa gây BOLA.

~~~sql
SELECT id, status, total_minor, created_at
FROM orders
WHERE tenant_id = :tenant AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :size OFFSET :offset;
~~~

Index ví dụ `(tenant_id, status, created_at DESC, id DESC)` **có thể** hỗ trợ pattern này, cần kiểm tra execution plan thực tế. Dùng DTO projection để tránh tải thừa/N+1; áp statement timeout/DB budgets. Phân quyền có thể còn phụ thuộc owner/role, không chỉ tenant.

## 8. `Page` hay `Slice`: tổng số item có thật sự cần?

| Kiểu | Trả lời | Chi phí/đặc điểm |
|---|---|---|
| `Page<T>` | Content, page/size, totalElements/totalPages | Thường cần **COUNT**, có thể đắt |
| `Slice<T>` | Content và **hasNext** | Thường lấy **size+1**, không cần tổng |
| `List<T>` | Content | Caller phải giới hạn số lượng |
| Cursor/keyset | Content sau vị trí cuối | Phù hợp trang sâu, cần token và index |

~~~java
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Pageable;

interface OrderSliceRepository {
    Slice<OrderEntity> findByTenantIdAndStatus(
        String tenantId, OrderStatus status, Pageable pageable);
}
~~~

Interface minh họa một truy vấn slice theo convention Spring Data; cách khai báo repository/implementation thực tùy ứng dụng. Nếu UI chỉ có “Xem thêm”, có thể trả `items, size, hasNext` thay vì tính tổng. Nếu dùng `Page`, `COUNT(*)` trên join/filter nhiều bảng có thể tốn kém.

**Offset không phải snapshot:** khi trang 0 có A,B,C và X mới được thêm ở đầu, trang 1 có thể lặp C. Tie-breaker bảo đảm thứ tự khi sort keys bằng nhau, không ngăn dữ liệu đổi giữa hai request.

## 9. Cursor/keyset: giới hạn chi phí và giải quyết trang sâu

Với các trường `created_at DESC, id DESC`, thay vì truyền `page=9000`, client lấy `nextCursor` từ response trước:

~~~http
GET /api/orders?limit=20&after=eyJ2IjoxLC4uLn0 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Backend giải mã cursor đã xác minh chứa **createdAt cuối và id cuối**, rồi áp điều kiện lexicographic:

~~~sql
SELECT id, status, total_minor, created_at
FROM orders
WHERE tenant_id = :tenant
  AND status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limitPlusOne;
~~~

`limitPlusOne = limit + 1` dùng để biết còn trang tiếp không. Query này dựa trên giả định **sort DESC cho cả hai trường**, cursor chứa giá trị cuối trang trước và có index phù hợp. Nếu đổi direction, null ordering hoặc sort field, điều kiện keyset cũng phải thay cho đúng; không sao chép điều kiện trên cho mọi sort.

**Cursor không phải chuỗi Base64 đáng tin chỉ vì nhìn khó đọc.** Một thiết kế an toàn thường có:

- Version, sort keys/values, filter hash, scope tenant và expiry.
- Mã hóa dạng opaque cho client; **HMAC/signature** hoặc cơ chế tương đương để chống sửa nội dung.
- Kiểm tra token có **khớp filter, sort, principal/tenant** của lần đọc hiện tại.
- Giới hạn `limit` độc lập với `size` và tránh cho client kết hợp `page` với `after` một cách nhập nhằng.

Cursor **không thay authorization** và không bảo đảm snapshot nếu trường sắp xếp bị cập nhật. Nếu khách hàng cần truy vấn trạng thái tại cùng một thời điểm, phải thêm mô hình snapshot/version token hoặc xuất báo cáo từ một nguồn cố định.

## 10. Link điều hướng, cache và HTTP semantics

API có thể gửi **RFC 8288 Link**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </api/orders?page=1&size=20&sort=createdAt,desc&sort=id,desc&status=PAID>; rel="next"
Cache-Control: private, no-store

{"items":[{"id":"o-913","status":"PAID","totalMinor":150000,
           "createdAt":"2026-11-18T09:30:00Z"}],
 "page":0,"size":20,"hasNext":true}
~~~

Next link phải giữ **filter/sort/size đã validate**, mã hóa query đúng và chỉ xuất hiện nếu thực sự còn trang. Tránh tạo absolute URL dựa vào `Host/X-Forwarded-Host` chưa được tin cậy; không gắn token vào link.

HTTP cache phân biệt **URI/query và các headers trong `Vary`**. Với response theo tenant/user, dùng `private/no-store` hoặc shared-cache controls đúng, tránh trộn trang và rò dữ liệu. Mutation có thể khiến các trang/filter cũ; `ETag`/304 không tự sửa offset shift khi dữ liệu thay đổi.

## 11. Lỗi API và Problem Details cho query không hợp lệ

Một request cố ý vượt giới hạn:

~~~http
GET /api/orders?page=5&size=5000&sort=customer.password,asc HTTP/1.1
Host: api.example.test
~~~

Backend phải từ chối trước database. Với policy strict ở bài này:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-collection-query",
  "title": "Invalid collection query",
  "status": 400,
  "code": "INVALID_QUERY",
  "detail": "size phải trong khoảng 1..100."
}
~~~

**Không tiết lộ** danh sách cột nội bộ, SQL text hoặc stack trace cho client khi từ chối sort. Có thể công bố các field sort hợp lệ trong tài liệu API. Nếu quota request bị vượt thì **429 Too Many Requests**, khác với **400 do tham số không hợp lệ**. Nếu database tạm quá tải có thể trả **503**, nhưng không dùng nó để che giấu một truy vấn vượt policy đã biết ngay ở input.

Một `@RestControllerAdvice` minh họa:

~~~java
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
class CollectionQueryErrors {
    @ExceptionHandler(InvalidCollectionQuery.class)
    ResponseEntity<ProblemDetail> badQuery(
            InvalidCollectionQuery ex) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, ex.getMessage());
        body.setTitle("Invalid collection query");
        body.setType(URI.create(
            "https://api.example.test/problems/invalid-collection-query"));
        body.setProperty("code", "INVALID_QUERY");
        return ResponseEntity.badRequest()
            .contentType(MediaType.parseMediaType(
                "application/problem+json"))
            .body(body);
    }
}
~~~

Spring MVC lỗi chuyển kiểu `page=abc` có thể đi qua handler khác với exception ứng dụng; cần thống nhất **error format** cho cả conversion, validation và business query policy bằng cấu hình `@ControllerAdvice`/exception handling phù hợp Spring version.

## 12. OpenAPI 3.1: diễn đạt đúng query parameters lặp và constraints

~~~yaml
openapi: 3.1.0
info: {title: Orders API, version: 1.0.0}
paths:
  /api/orders:
    get:
      summary: Danh sách đơn hàng theo trang và thứ tự
      security:
        - BearerAuth: []
      parameters:
        - name: page
          in: query
          schema: {type: integer, minimum: 0, default: 0}
          description: Page index 0-based; offset=page*size <= 10000
        - name: size
          in: query
          schema: {type: integer, minimum: 1, maximum: 100, default: 20}
        - name: sort
          in: query
          style: form
          explode: true
          description: >
            Có thể lặp sort=field,direction theo thứ tự ưu tiên.
            Field: createdAt, totalMinor, id. Direction: asc hoặc desc.
            Tối đa ba field, không được lặp cùng field.
          schema:
            type: array
            maxItems: 3
            items:
              type: string
              pattern: '^(createdAt|totalMinor|id),(asc|desc)$'
        - name: status
          in: query
          schema:
            type: string
            enum: [PAID, PENDING, CANCELLED]
      responses:
        '200':
          description: Trang đơn hàng (có thể rỗng)
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderPage'
        '400':
          description: Query không hợp lệ
          content:
            application/problem+json:
              schema: {type: object}
        '401': {description: Chưa xác thực}
        '403': {description: Không có quyền xem đơn}
        '429': {description: Vượt hạn mức}
components:
  securitySchemes:
    BearerAuth: {type: http, scheme: bearer, bearerFormat: JWT}
  schemas:
    OrderPage:
      type: object
      required: [items, page, size, totalElements, totalPages, hasNext]
      properties:
        items:
          type: array
          items: {$ref: '#/components/schemas/Order'}
        page: {type: integer}
        size: {type: integer}
        totalElements: {type: integer, format: int64}
        totalPages: {type: integer}
        hasNext: {type: boolean}
    Order:
      type: object
      required: [id, status, totalMinor, createdAt]
      properties:
        id: {type: string}
        status: {type: string}
        totalMinor: {type: integer, format: int64}
        createdAt: {type: string, format: date-time}
~~~

OpenAPI diễn tả `sort` dưới dạng **array, style=form, explode=true**, tương ứng các query parameters lặp. `page×size<=10000` là **ràng buộc giữa hai tham số**, không thể diễn đạt bằng hai `minimum/maximum` độc lập; nó cần mô tả, server validation và tests.

Nếu implementation có **cả cursor API**, hãy tách operation/query contract hoặc dùng tài liệu nêu rõ **`after` và `page` loại trừ nhau**. `securitySchemes` không thay object-level permission; token hợp lệ vẫn không có nghĩa caller được xem mọi đơn.

## 13. Kiểm thử binding, sorting, security và chi phí truy vấn

### MockMvc: input vượt policy bị từ chối

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPaginationContractTest {
    @Autowired MockMvc mvc;

    @Test
    @WithMockUser
    void invalidSizeRejected() throws Exception {
        mvc.perform(get("/api/orders")
                .param("page", "0").param("size", "5000"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("INVALID_QUERY"));
    }

    @Test
    @WithMockUser
    void unsafeSortRejected() throws Exception {
        mvc.perform(get("/api/orders")
                .param("sort", "customer.password,asc"))
           .andExpect(status().isBadRequest());
    }

    @Test
    @WithMockUser
    void negativePageRejected() throws Exception {
        mvc.perform(get("/api/orders").param("page", "-1"))
           .andExpect(status().isBadRequest());
    }
}
~~~

Đây là **khung test** cần fixture, principal tenant hợp lệ, controller/service và `spring-security-test`; chưa chạy thực tế. Các test 400 chứng minh **binding/validation**, chưa chứng minh quyền tenant hoặc SQL đúng.

| Integration/contract test | Điều cần assert |
|---|---|
| Default không tham số | Page 0/size 20, sort createdAt DESC/id DESC |
| `page=abc`, size 0/101, deep offset | 400 trước query |
| Sort đa cấp/duplicate/sai direction | Thứ tự đúng hoặc 400 |
| Rows cùng timestamp, trang cuối | Stable tie-breaker; trang rỗng 200 |
| Hai tenant/role khác nhau | Không leak item, count hoặc field sort nhạy cảm |
| Insert giữa các trang/cursor sửa token | Giới hạn offset; cursor có kiểm tra scope/chữ ký |
| COUNT/filter tốn kém | Query plan, timeout, indexes và giới hạn tài nguyên |
| Cache/auth | Không trộn page/filter/tenant |

**DB integration tests** (ví dụ Testcontainers/PostgreSQL) nên seed các trường hợp tie, tenant khác, trang sâu; MockMvc một mình không phát hiện execution plan sai. Metrics quan trọng: page size/offset distribution, 400/429/503, query p95/p99, scanned rows/COUNT cost, sort phổ biến và timeouts; không đưa raw query/token vào high-cardinality labels.

## 14. Bài tập: danh sách khóa học có dữ liệu liên tục thay đổi

API:

~~~text
GET /api/courses?page=0&size=25&sort=publishedAt,desc&status=PUBLISHED
~~~

Dữ liệu có `id,publishedAt,priceMinor,status,ownerId,tenantId`; nhiều bản ghi cùng timestamp và admin thêm liên tục. Team định inject `Pageable` rồi dùng `findAll(pageable)`. Client thử `size=20000` hoặc `sort=owner.passwordHash,asc`.

**Yêu cầu:** (1) Nêu bốn rủi ro; (2) đưa default/max size và whitelist sort; (3) viết SQL tenant filter với tie-breaker; (4) chọn Page/Slice/cursor; (5) chọn status HTTP cho size quá lớn, sort sai, không có quyền và trang rỗng; (6) thiết kế sáu tests.

### Đáp án gợi ý

1. **Không giới hạn tải**, sort không whitelist, thiếu tenant predicate (BOLA), thiếu tie-breaker, count đắt, serialize entity lộ field.
2. Ví dụ page 0, size 25/tối đa 100, offset<=10000; sort chỉ `publishedAt/priceMinor/id`, direction asc/desc.
3. SQL:

   ~~~sql
   SELECT id, published_at, price_minor, status
   FROM courses
   WHERE tenant_id = :tenant AND status = 'PUBLISHED'
   ORDER BY published_at DESC, id DESC
   LIMIT 25 OFFSET 0;
   ~~~

4. `Slice` cho “Xem thêm”, cursor/keyset nếu cuộn sâu và nhiều inserts; cần stable keys, token scope/expiry, không thay quyền.
5. Size/sort sai: **400**; không có quyền: **403/404** theo policy; trang hợp lệ rỗng: **200 + items=[]**.
6. Test defaults, invalid size/page, unsafe sort, tie-breaker, tenant/role isolation, cursor tamper, concurrent insert và COUNT performance.

## 15. Checklist production

- [ ] Quy ước **page 0-based**, default, size/offset tối đa và chính sách reject/cap rõ.
- [ ] Biết `@RequestParam` thuộc Spring MVC, `Pageable` resolver thuộc Spring Data Web; không coi binding là authorization/validation đầy đủ.
- [ ] Sort params lặp đúng thứ tự; whitelist field/direction, reject duplicate; thêm **id tie-breaker**.
- [ ] Query tenant/role predicates **trước page/count**; không truyền raw SQL/entity path hay serialize entity nhạy cảm.
- [ ] Chọn `Page` nếu cần total, `Slice` nếu chỉ cần hasNext, cursor cho duyệt sâu và thay đổi thường xuyên.
- [ ] Kiểm tra index, DB timeout, QPS/quota và query latency/COUNT cost.
- [ ] Next link giữ filters/sort được validate; không tin Host/forwarded headers chưa xác minh.
- [ ] Cache/Vary/Auth không trộn tenant hoặc trang; mutations có chiến lược invalidation.
- [ ] HTTP 400/401/403/429/503 và Problem Details đúng; trang rỗng vẫn có thể 200.
- [ ] OpenAPI mô tả `sort` lặp, page size, response DTO; MockMvc và DB integration tests bao phủ boundaries, ties, tenant, concurrent updates.

**Kết luận:** Spring MVC chuyển query parameters thành đối số; **hợp đồng, giới hạn tải, whitelist sort, tenant authorization và kiểm thử** mới quyết định endpoint phân trang có đúng và an toàn. `Pageable` giúp viết nhanh nhưng không thay thế những bảo đảm này.

### Tài liệu nền

- **Spring Framework — Spring MVC:** `@RequestParam`, conversion, ProblemDetail.
- **Spring Data Commons/JPA:** Pageable, Page/Slice, Web Support, sorting, count queries.
- **RFC 9110, RFC 8288, RFC 9457:** HTTP, Link, Problem Details.
- **OpenAPI 3.1:** query params `style=form`/`explode=true`, schema và security.


