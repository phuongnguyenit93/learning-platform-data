# Giới hạn thời gian và phạm vi truy vấn do người dùng điều khiển trong JPA

Trong ứng dụng sử dụng **Jakarta Persistence (JPA)**, người dùng có thể điều khiển truy vấn thông qua ô tìm kiếm, các bộ lọc, lựa chọn sắp xếp, trang kết quả, báo cáo và chức năng xuất dữ liệu. Đây là nhu cầu hợp lệ, nhưng nếu ứng dụng chuyển mọi lựa chọn đầu vào thành một truy vấn tùy ý mà không kiểm soát, một yêu cầu duy nhất có thể đọc quá nhiều dữ liệu, thực hiện phép JOIN tốn kém, giữ database connection quá lâu hoặc truy xuất dữ liệu ngoài phạm vi quyền hạn.

Ví dụ endpoint:

~~~text
GET /api/products?sort=price&page=0&size=1000000
~~~

nếu service đưa trực tiếp giá trị `size` vào `setMaxResults()` mà không giới hạn, ứng dụng có thể materialize số lượng entity rất lớn, tạo áp lực heap, kết nối database và serialization. Một endpoint khác cho phép truyền tùy ý `entity`, `field` hoặc cấu trúc JOIN còn có thể tạo truy vấn quá phức tạp hoặc lộ dữ liệu không được phép.

Ngay cả khi có:

~~~java
query.setHint(
    "jakarta.persistence.query.timeout",
    2000
);
~~~

thì **timeout không phải ranh giới bảo mật đầy đủ**: provider/driver có thể không áp dụng đúng như kỳ vọng; database vẫn có thể phải làm nhiều công việc trước khi timeout; dữ liệu trả về vẫn có thể vượt quyền nếu thiếu tenant/ACL predicates. Tương tự, một `setMaxResults(50)` chỉ giới hạn **số dòng kết quả**, không bảo đảm database chỉ đọc hoặc sắp xếp 50 dòng.

Để giới hạn truy vấn do người dùng điều khiển, cần thiết kế đồng thời:

1. **Giới hạn phạm vi dữ liệu**: tenant, owner, organization, role, trạng thái và quyền truy cập.
2. **Giới hạn cấu trúc truy vấn**: fields/operators/joins/sort keys từ allowlist, không nhận JPQL/SQL tùy ý.
3. **Giới hạn kích thước**: page size, tổng số pages/offset hoặc cursor, số rows có thể export, độ dài filter.
4. **Giới hạn thời gian**: query/statement/lock/transaction/API timeout theo tầng phù hợp.
5. **Giới hạn tài nguyên đồng thời**: rate limit, concurrency caps, connection pool, job quotas và circuit breakers.
6. **Quan sát và kiểm thử**: query plans, index usage, latency, timeout/cancellation, dữ liệu vượt tenant và tình huống tải xấu.

Mục tiêu là xây dựng API vẫn hữu ích cho người dùng nhưng **không trao cho client khả năng kiểm soát không giới hạn chi phí hoặc phạm vi dữ liệu của database**.

---

## 1. Mục tiêu học tập

Sau bài này, người đọc có thể:

- Phân biệt dữ liệu người dùng được phép quyết định với điều kiện server **bắt buộc** áp dụng.
- Thiết kế search/filter/sort API dựa trên allowlist và typed parameter binding.
- Sử dụng `setMaxResults()`, pagination, keyset cursor và DTO projection hợp lý.
- Nhận diện những yêu cầu tốn kém như OFFSET lớn, dẫn đầu wildcard, OR quá sâu và JOIN nhiều collections.
- Hiểu ý nghĩa và giới hạn của `jakarta.persistence.query.timeout`.
- Phân biệt query timeout với lock timeout, transaction timeout, JDBC/network timeout và HTTP deadline.
- Chọn transaction/read-only semantics, không giữ locks và connections qua công việc không cần thiết.
- Tạo export/report workflow có quotas, checkpoint, cancellation và quyền truy cập.
- Thiết kế monitoring và integration tests cho cả correctness lẫn resource limits.

## 2. Vì sao đây là chủ đề bảo mật dữ liệu?

Một ứng dụng có thể không bị SQL injection nhưng vẫn bị **resource exhaustion**.

Các tình huống:

~~~text
Request A:
  size = 1_000_000
  -> tạo rất nhiều entity/DTO
  -> heap và GC tăng

Request B:
  sort = unindexedTextField
  -> DB sort dataset lớn
  -> CPU/temp disk cao

Request C:
  freeText = "%a%"
  -> full table/index scan tùy DB

Request D:
  tự chọn tenantId = tenant khác
  -> rò rỉ dữ liệu xuyên tenant

Request E:
  export tất cả rows rồi gọi lặp nhiều lần
  -> chiếm pool connections và bandwidth
~~~

Những vấn đề này có thể gây **denial of service (DoS)**, cạn tài nguyên và vi phạm confidentiality. Chúng không chỉ là câu chuyện query tuning.

### Phân biệt ba loại rủi ro

| Nhóm | Ví dụ | Lớp phòng vệ |
| --- | --- | --- |
| Truy cập quá phạm vi | Xem đơn hàng của tenant khác | Authorization, tenant predicates, RLS khi phù hợp |
| Truy vấn quá phức tạp | Nested OR/JOIN/sort khó | Query-shape allowlist, complexity budget |
| Truy vấn quá tốn tài nguyên | Page lớn, quét bảng, timeout | Row/byte/time/concurrency limits |

Một hệ thống an toàn phải giải quyết **cả ba**, không chỉ sanitize strings.

## 3. Luồng dữ liệu đáng tin và không đáng tin

~~~text
Client request (untrusted)
  |
  +-- search text
  +-- requested sort
  +-- page size / cursor
  +-- filter operators
  |
  v
Controller: parse + validate
  |
  v
Application service:
  +-- authenticated identity / permissions
  +-- server-enforced tenant/owner scope
  +-- allowed query shape
  +-- maximum complexity + row budget
  |
  v
Repository / Criteria API:
  +-- bound parameters
  +-- stable ordering
  +-- bounded result
  +-- timeout hint
  |
  v
Database:
  +-- indexes / constraints / DB permissions
  +-- statement timeout / workload controls
  |
  v
Response: bounded, authorized DTOs
~~~

**Client được phép chọn một số tiêu chí trong khuôn khổ server đặt ra; client không được tự định nghĩa ranh giới an toàn.**

Ví dụ tenantId nên được lấy từ principal/session đã xác thực, không tin vào `request.getParameter("tenantId")` để xác lập quyền.

## 4. Phân biệt các giới hạn: phạm vi, kích thước và thời gian

| Loại giới hạn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authorization scope | Ai được xem rows nào? | `tenant_id = currentTenant` |
| Query shape | Client được lọc/sort theo gì? | Chỉ sku, category, createdAt |
| Page size | Trả tối đa bao nhiêu rows? | 50 hoặc 100 |
| Scan/window bound | Được nhìn sâu đến đâu? | Cursor, max offset |
| Query cost | Bao nhiêu joins/filters? | Tối đa 5 filters, 1 join |
| Query execution timeout | Statement chạy bao lâu? | Ví dụ 2 giây |
| Lock timeout | Chờ lock trong bao lâu? | Ví dụ 250 ms |
| Transaction timeout | Unit of work kéo dài bao lâu? | Ví dụ 5 giây |
| Request deadline | API hoàn tất trong bao lâu? | Ví dụ 3 giây |
| Concurrency budget | Bao nhiêu truy vấn nặng đồng thời? | 4 search exports |

Các ngưỡng trên chỉ là **số minh họa**. Một ứng dụng khác có SLA, DB capacity và workload khác; cần thử tải và chọn giá trị phù hợp.

## 5. Không cho client gửi trực tiếp JPQL/SQL

Một thiết kế nguy hiểm:

~~~java
String jpql = request.getParameter("jpql");
return em.createQuery(jpql).getResultList();
~~~

Client có thể tác động trực tiếp vào query structure, entity paths, joins hoặc những điều kiện quan trọng.

Tương tự:

~~~java
String sort = request.getParameter("sort");
String jpql = "SELECT p FROM Product p ORDER BY p." + sort;
~~~

nếu không có allowlist, user input đang điều khiển **cấu trúc JPQL**.

### Cách đúng

Định nghĩa một API contract hạn chế:

~~~text
Allowed filters:
  skuPrefix        -> startsWith(String)
  categoryId       -> equals(Long)
  active           -> equals(Boolean)

Allowed sorts:
  createdAt
  sku

Forbidden:
  arbitrary JPQL strings
  arbitrary entity names
  nested property paths
  arbitrary SQL functions
~~~

Service chuyển những tên API hợp lệ thành typed Criteria expressions hoặc những query templates đã được review.

## 6. Parameter binding chống injection giá trị, không hạn chế workload

Sai:

~~~java
String jpql =
    "SELECT p FROM Product p WHERE p.sku = '" +
    sku + "'";
~~~

Đúng:

~~~java
List<Product> result = em.createQuery(
        "SELECT p FROM Product p WHERE p.sku = :sku",
        Product.class)
    .setParameter("sku", sku)
    .getResultList();
~~~

Binding giúp xử lý **giá trị** an toàn và đúng kiểu, nhưng không giải quyết:

- User có quyền xem Product hay không.
- Số lượng rows có thể được trả.
- Query có JOIN quá nhiều bảng không.
- Giá trị `sku` có quá dài không.
- Có index phù hợp không.
- Request có chiếm 30 giây DB time không.

### Identifiers không thể bind như values

Một field name hoặc ORDER BY direction không nên được đưa vào JPQL bằng phép nối chuỗi tùy ý. Hãy map từ **enum/allowlist** sang Criteria attributes.

## 7. Allowlist field/operator thay vì blacklist

Ví dụ danh sách cho phép:

~~~java
enum ProductFilter {
    SKU_PREFIX,
    CATEGORY_ID,
    ACTIVE
}

enum SortField {
    SKU,
    CREATED_AT
}
~~~

Không chấp nhận:

~~~text
field=product.supplier.secretPricing.discountRules...
~~~

chỉ vì đường dẫn ấy có thể được JPA resolve. Entity mapping là **metadata kỹ thuật**, không phải public API authorization contract.

### Tại sao blacklist kém an toàn?

Khi model có thêm field nhạy cảm hoặc association mới, blacklist có thể quên bổ sung. Với allowlist, feature mới không tự trở thành queryable cho client cho đến khi được review.

## 8. Ràng buộc filter complexity

Một request DSL có thể cho phép:

~~~json
{
  "and": [
    {"field": "status", "op": "eq", "value": "ACTIVE"},
    {"field": "skuPrefix", "op": "startsWith", "value": "BK"}
  ]
}
~~~

Nhưng không nên nhận một cây điều kiện lồng nhau không giới hạn:

~~~text
OR
  OR
    OR
      AND
        EXISTS
          ...
~~~

Các limit có thể bao gồm:

- Tối đa 5 filter nodes.
- Tối đa 1 hoặc 2 levels nesting.
- Tối đa 20 values trong `IN`.
- Tối đa 1 JOIN đã được review.
- Chỉ hỗ trợ operators được định nghĩa cho từng field.
- Không cho user tự chèn subquery/function expression.

Đây là **ví dụ policy**, cần điều chỉnh theo nghiệp vụ. Mục đích là không để client cấu trúc query có độ phức tạp lớn tùy ý.

## 9. Không nhận arbitrarily nested association paths

Một filter:

~~~text
employee.department.company.region.country.name
~~~

có thể kéo theo nhiều JOINs, access path khó dự đoán và phạm vi dữ liệu ngoài API contract.

Thay vì nhận full path, đưa ra tên public:

~~~text
departmentCode = "ENG"
~~~

và server ánh xạ nó vào **một query đã được review**.

### Giới hạn JOIN depth

Nếu thực sự cung cấp query builder cho internal admins, cần max join depth, max association expansions, collection restrictions và permission checks. Không mặc định mọi attribute trong JPA Metamodel là “được phép tìm kiếm”.

## 10. Bắt buộc tenant/owner predicate

Ví dụ multi-tenant:

~~~java
Long tenantId = currentPrincipal.tenantId();

TypedQuery<Product> q = em.createQuery(
    "SELECT p FROM Product p " +
    "WHERE p.tenantId = :tenantId " +
    "AND p.active = true",
    Product.class);

q.setParameter("tenantId", tenantId);
~~~

**Tenant ID phải đến từ danh tính đã xác thực hoặc server-trusted authorization context.** Không nhận một tenantId tùy ý từ client để xác lập phạm vi truy cập.

### Còn quyền theo từng record?

Tenant scope có thể chưa đủ. Một user trong cùng tenant chỉ được xem Products thuộc location/department nào đó. Predicate có thể cần thêm `ownerId`, ACL join, resource policy hoặc DB row-level security phù hợp.

### Không chỉ dùng filter ở controller

Nếu một repository path bỏ qua tenant predicate, có thể lộ dữ liệu. Đưa security scope vào reusable query specifications/service policy hoặc DB-level RLS defense-in-depth, kết hợp integration tests.

## 11. Bảo đảm nhóm điều kiện AND/OR đúng

Một lỗi logic nghiêm trọng:

~~~text
tenantId = currentTenant AND name LIKE 'A%'
OR categoryId = 10
~~~

Nếu không có ngoặc, `OR categoryId = 10` có thể trả rows thuộc tenant khác.

### Ý định đúng

~~~text
tenantId = currentTenant
AND (
  name LIKE 'A%'
  OR categoryId = 10
)
~~~

Với Criteria API:

~~~java
Predicate tenant =
    cb.equal(root.get("tenantId"), trustedTenantId);

Predicate byName =
    cb.like(root.get("name"), prefixPattern);

Predicate byCategory =
    cb.equal(root.get("categoryId"), categoryId);

cq.where(
    cb.and(
        tenant,
        cb.or(byName, byCategory)
    )
);
~~~

Code là ví dụ cấu trúc predicate; cần xử lý optional filters và null params theo contract. **Không cho client OR ra khỏi server-enforced tenant scope.**

## 12. Layered authorization thay vì một bộ lọc duy nhất

~~~text
API authentication
     |
     v
Service permission check
     |
     v
Mandatory tenant/owner predicates
     |
     v
Database permissions / RLS (nếu áp dụng)
~~~

Mỗi tầng giải quyết một phần:

- Auth xác định danh tính.
- Service kiểm tra hành động `product:read` hoặc `product:export`.
- Query bắt buộc scope rows.
- DB permissions/RLS có thể giảm hậu quả khi code thiếu WHERE.

### Cẩn trọng RLS

RLS có semantics DB-specific và phải được thiết lập đúng session/connection/transaction context, đặc biệt với connection pools. Không kết luận chỉ bật RLS là mọi SQL/native query tự an toàn nếu session tenant context đặt sai.

## 13. Query result size: setMaxResults()

JPA cung cấp:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p ORDER BY p.id",
    Product.class);

query.setMaxResults(50);
~~~

Thông thường chỉ lấy tối đa 50 **root results** theo query semantics.

### Nhưng đừng nhầm với work bound

Để trả 50 results theo:

~~~sql
ORDER BY unindexed_column
~~~

database có thể vẫn phải đọc/sắp xếp một tập rất lớn trước khi lấy 50 rows. LIMIT nhỏ **không bảo đảm query CPU, disk IO, sort memory hoặc scan cost nhỏ**.

### Cần thêm

- Index phù hợp filters/sorts.
- Giới hạn allowed sort keys.
- Giới hạn filter complexity.
- Statement timeout và concurrency budget.
- Query plan monitoring.

## 14. Page size phải được validate tại server

Không tin vào:

~~~java
int requestedSize =
    Integer.parseInt(request.getParameter("size"));

query.setMaxResults(requestedSize);
~~~

Vì client có thể gửi:

~~~text
size=1000000000
size=0
size=-1
size=2147483647
~~~

Thiết kế API:

~~~java
static final int DEFAULT_PAGE_SIZE = 30;
static final int MAX_PAGE_SIZE = 100;

static int validatePageSize(Integer requested) {
    if (requested == null) {
        return DEFAULT_PAGE_SIZE;
    }

    if (requested < 1 || requested > MAX_PAGE_SIZE) {
        throw new BadRequestException(
            "size phải trong khoảng 1..100"
        );
    }

    return requested;
}
~~~

`BadRequestException` là exception application-defined tương ứng HTTP 400 trong ví dụ.

### Reject hay clamp?

Có thể chọn reject để client thấy rõ lỗi contract; clamp giúp một số UX nhưng dễ che những request bất thường. Quan trọng là **server luôn áp hard maximum**, không truyền nguyên giá trị do client đề xuất.

## 15. Phân trang với OFFSET

Ví dụ:

~~~java
query.setFirstResult(pageNumber * pageSize);
query.setMaxResults(pageSize);
~~~

Rủi ro:

- `pageNumber * pageSize` có thể overflow với int.
- OFFSET lớn có thể buộc DB bỏ qua nhiều rows.
- Khi dữ liệu insert/delete đồng thời, OFFSET dễ duplicate/skip.
- `Page 1000000` có thể tạo truy vấn rất tốn dù result nhỏ.

### Validate bằng long trước khi cast

~~~java
static int validatedOffset(int page, int size) {
    if (page < 0) {
        throw new BadRequestException("page âm");
    }

    long offset = (long) page * size;
    long maxOffset = 10_000L;

    if (offset > maxOffset) {
        throw new BadRequestException(
            "Vượt cửa sổ trang cho phép"
        );
    }

    return Math.toIntExact(offset);
}
~~~

Ngưỡng 10.000 chỉ minh họa. Với dataset lớn, **cursor/keyset** có thể là lựa chọn phù hợp hơn deep OFFSET.

## 16. Keyset pagination theo khóa ổn định

Nếu Product có ID Long và hỗ trợ index/order:

~~~java
TypedQuery<Product> q = em.createQuery(
    "SELECT p FROM Product p " +
    "WHERE p.tenantId = :tenantId " +
    "AND p.id > :afterId " +
    "ORDER BY p.id",
    Product.class);

q.setParameter("tenantId", trustedTenantId);
q.setParameter("afterId", afterId);
q.setMaxResults(size + 1);
~~~

`size + 1` cho biết có thể còn trang tiếp theo:

~~~text
requested size = 30
fetched rows = 31
return 30
hasNext = true
nextCursor = id của row thứ 30
~~~

### Giới hạn

Keyset không tự giải quyết scan cost nếu filter kém hoặc index không phù hợp. Nó cũng không tự tạo một consistent snapshot xuyên nhiều requests. Nếu data thay đổi, cần xét cut-off/snapshot/version semantics.

## 17. Sort ổn định để không skip/duplicate rows

Sắp theo `createdAt` có thể có nhiều rows cùng timestamp. Nếu chỉ:

~~~sql
ORDER BY created_at
~~~

thì thứ tự giữa những rows đồng giá trị không ổn định.

Thường cần:

~~~sql
ORDER BY created_at, id
~~~

Cursor chứa cả `createdAt` và `id`, với điều kiện keyset tương ứng:

~~~text
createdAt > cursor.createdAt
OR (
  createdAt = cursor.createdAt
  AND id > cursor.id
)
~~~

Nếu sort descending/mixed directions, predicate cursor phải được điều chỉnh đúng comparator và NULL ordering. Không lấy cursor chỉ có id để áp vào một thứ tự không phải id.

## 18. Cursor không được xem là giấy phép truy cập

Một client có thể tự thay:

~~~text
cursor=afterId:500000
~~~

Nếu server có tenant/ACL predicates ở mọi page, giá trị afterId tùy ý chỉ thay điểm bắt đầu, **không được làm thay phạm vi quyền**.

### Khi cần opaque/signed cursor

Cursor có thể chứa:

- Last sort values và unique tiebreaker.
- Filter hash/query version.
- Tenant/user context.
- Expiration.
- HMAC signature hoặc encryption khi cần giữ kín.

Đừng dùng ký số cursor thay cho authorization. **Mọi truy vấn trang tiếp theo vẫn phải tái áp tenant/ACL predicates**, bất kể cursor được ký hợp lệ.

## 19. Phạm vi thời gian của dữ liệu

Một endpoint báo cáo:

~~~text
GET /orders?from=2020-01-01&to=2026-12-31
~~~

có thể quét nhiều năm dữ liệu.

Thiết kế policy:

~~~text
Maximum window: 31 days
Allowed timezone: UTC-normalized instants
from < to
to <= now + allowedFutureWindow
No unlimited "all history" for regular search
~~~

Các ngưỡng là ví dụ; báo cáo lịch sử dài có thể đi qua export job đã authorize/quotas thay vì HTTP search đồng bộ.

### Dùng khoảng half-open

~~~text
createdAt >= fromInclusive
createdAt < toExclusive
~~~

Giảm nhập nhằng khi xử lý millisecond/nanosecond precision và date boundaries.

## 20. Giới hạn text search và LIKE

Một endpoint cho tìm kiếm tùy ý:

~~~text
q=a
q=%a%
q=_____ 
~~~

có thể match rất nhiều rows hoặc tạo scan tốn kém.

Policy mẫu:

- Trim/normalize input theo contract.
- Giới hạn độ dài, ví dụ từ 2 đến 64 ký tự.
- Chỉ cho prefix search trên indexed SKU khi phù hợp.
- Không cho tùy ý regex/leading wildcard.
- Escape ký tự LIKE wildcard nếu user cần tìm literal.

### Parameter binding không tự escape LIKE wildcard

`%` và `_` vẫn là wildcard có ý nghĩa trong SQL LIKE dù được bind parameter. Nếu semantics là prefix literal, cần escape đúng theo dialect/JPA query.

## 21. CriteriaBuilder.like với ký tự escape

Ví dụ helper cho LIKE literal prefix:

~~~java
static String escapeLikeLiteral(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}
~~~

Dùng:

~~~java
String pattern =
    escapeLikeLiteral(skuPrefix) + "%";

Predicate bySku = cb.like(
    root.<String>get("sku"),
    pattern,
    '\\'
);
~~~

Đây là ví dụ Java sử dụng backslash làm escape character và Criteria API overload hỗ trợ `char escapeChar`. Cần kiểm tra SQL/driver/collation trên DBMS thực, đặc biệt khi áp dụng case-insensitive matching hoặc vendor functions.

**Quan trọng:** escaping LIKE và parameter binding bảo vệ cú pháp/semantics, nhưng **không tự tạo index** hoặc hạn chế số rows sẽ match.

## 22. Tránh mở full text search bằng LIKE không giới hạn

Các mẫu:

~~~sql
WHERE description LIKE '%word%'
~~~

thường khó tận dụng B-tree index như equality hoặc left-anchored prefix search (tùy DB collation/index strategy).

Khi cần tìm trong mô tả dài:

- Xem full-text index/search engine theo quy mô.
- Hạn chế query length/terms.
- Cấm hoặc giới hạn regex backtracking có chi phí lớn.
- Áp pagination và server-enforced authorization filter.
- Benchmark worst-case queries.

Không dùng một text box làm cổng cho mọi biểu thức SQL do người dùng nghĩ ra.

## 23. Giới hạn số giá trị IN

Input:

~~~text
GET /products?ids=1,2,3,...100000
~~~

có thể tạo quá nhiều parameters, plan compilation overhead hoặc vượt giới hạn của DB/driver.

Policy ví dụ:

~~~java
if (ids.isEmpty() || ids.size() > 100) {
    throw new BadRequestException(
        "ids phải có 1..100 giá trị");
}
~~~

Kiểm tra thêm:

- IDs có đúng kiểu không.
- Duplicates có được loại bỏ không.
- User có quyền với từng ID không.
- Có nên dùng batch endpoint hoặc temp table được quản lý riêng không.

**IN limit là giới hạn query shape**, không thay việc kiểm tra ownership/tenant của các records.

## 24. Giới hạn JOIN, GROUP BY và aggregation

Các truy vấn do người dùng cấu hình có thể có:

~~~text
group by category, brand, day, region, ...
count(distinct ...)
join products -> orders -> lines -> customers ...
sort aggregate descending
~~~

Đối với API thông thường:

- Chỉ cung cấp một số báo cáo đã định nghĩa.
- Giới hạn group dimensions.
- Dùng summary/materialized views hoặc pre-aggregation cho báo cáo nặng.
- Không cho arbitrary cross joins, recursive paths hoặc distinct toàn tập.
- Cân nhắc run report dưới background queue thay vì HTTP request.

Một `setMaxResults(50)` trên GROUP BY query vẫn có thể yêu cầu DB tổng hợp rất nhiều rows **trước khi trả 50 groups**.

## 25. COUNT queries cũng có chi phí

Để trả:

~~~text
totalElements = 2_346_000
totalPages = 23_460
~~~

service có thể chạy một `COUNT(*)` trên filtered dataset.

Với filters/joins phức tạp, count có thể đắt ngang hoặc hơn query lấy một page.

### Khi nào không cần total count?

Một UI chỉ cần Next có thể dùng `size+1` result và trả `hasNext`. Trong Spring Data, `Slice` là một abstraction có thể hữu ích khi không cần total count; còn `Page` thường cần tính tổng trong những tình huống nhất định.

**Không mặc định mọi request phải có exact total count.** Nếu nghiệp vụ cần, phải đưa count vào query budget và đo riêng.

## 26. Một truy vấn bị giới hạn rows vẫn có thể nạp graph lớn

Ví dụ:

~~~java
List<Order> orders = em.createQuery(
        "SELECT o FROM Order o " +
        "JOIN FETCH o.lines",
        Order.class)
    .setMaxResults(50)
    .getResultList();
~~~

Với to-many fetch join và pagination, một số providers có thể cần pagination in-memory hoặc có semantics/performance constraints khác; result có thể kéo theo rất nhiều OrderLine instances.

### Hướng thiết kế

1. Query page các Order IDs có tenant filter và stable order.
2. Fetch dữ liệu cần cho đúng IDs trong query thứ hai.
3. Hoặc dùng DTO projection/aggregation không materialize toàn graph.

Đo SQL và heap, không tin rằng `setMaxResults(50)` có nghĩa “chỉ tối đa 50 Java objects”.

## 27. Ưu tiên DTO/scalar projection cho read-only endpoints

Entity result:

~~~java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p",
        Product.class)
    .setMaxResults(50)
    .getResultList();
~~~

DTO:

~~~java
List<ProductRow> rows = em.createQuery(
        "SELECT NEW com.example.api.ProductRow(" +
        "p.id, p.sku, p.name, p.price) " +
        "FROM Product p",
        ProductRow.class)
    .setMaxResults(50)
    .getResultList();
~~~

DTO giảm nguy cơ để JSON serializer đi qua LAZY associations của managed entity và có thể giảm memory/dirty tracking overhead.

**DTO không thay authorization**: SQL project ít fields nhưng vẫn có thể đọc sai tenant nếu WHERE thiếu.

## 28. Không trả entity graph trực tiếp ra API

Nếu JSON serializer truy cập:

~~~text
Product
 -> Category
 -> Supplier
 -> SupplierContracts
 -> ...
~~~

thì có thể gây N+1, cycles, dữ liệu nhạy cảm và response size lớn dù query ban đầu giới hạn 50 Products.

### Hướng phù hợp

- Dùng response DTO.
- Giới hạn fields/relations public.
- Chọn fetch plan explicit.
- Tránh Open EntityManager in View như một giải pháp thay domain/API design.
- Áp response byte budget nếu hệ thống có khả năng.

**Giới hạn rows tại repository không đủ nếu response serialization tự truy cập thêm associations không kiểm soát.**

## 29. Giới hạn thời gian: cần phân biệt nhiều tầng

Một request có thể mất thời gian ở:

~~~text
HTTP ingress/rate-limit
   |
   +-- Queue/cpu parse/validation
   |
   +-- Acquire DB connection
   |
   +-- Transaction begin
   |
   +-- Prepare/execute SQL
   |      |
   |      +-- Lock wait
   |      +-- CPU/IO/network
   |
   +-- Materialize entities/DTOs
   |
   +-- Serialize response
   |
HTTP response
~~~

Một **query timeout** thường chỉ kiểm soát một phần thời gian SQL/JPA operation, không tự giới hạn thời gian chờ connection pool, toàn bộ Java processing hoặc response streaming.

## 30. JPA query timeout hint

JPA định nghĩa standard hint:

~~~java
TypedQuery<ProductRow> query = em.createQuery(
    "SELECT NEW com.example.api.ProductRow(" +
    "p.id, p.sku, p.name, p.price) " +
    "FROM Product p WHERE p.tenantId = :tenantId",
    ProductRow.class);

query.setParameter("tenantId", tenantId);
query.setMaxResults(50);

query.setHint(
    "jakarta.persistence.query.timeout",
    2000
); // 2.000 milliseconds
~~~

Ý nghĩa: **yêu cầu/hint** về thời gian tối đa cho query execution, tính bằng **milliseconds** theo Jakarta Persistence hint convention.

### Quan trọng: provider có thể không hỗ trợ

Các standard query hints về timeout không phải bảo đảm **hard deadline** luôn được thực thi chính xác cho mọi provider/driver/DBMS. Một provider có thể bỏ qua hint không hỗ trợ hoặc ánh xạ nó sang cơ chế gần nhất.

Không kết luận truy vấn chắc chắn bị dừng ở đúng 2.000 ms nếu chưa kiểm chứng end-to-end.

## 31. Cách kiểm tra query timeout có hiệu lực

Trong integration environment:

1. Cấu hình provider và database giống môi trường chạy thật.
2. Đặt query timeout nhỏ có chủ đích.
3. Chạy một test query chắc chắn chậm bằng fixture/test helper phù hợp DB.
4. Quan sát actual elapsed time, exception và DB session state.
5. Xác nhận JDBC/DB statement thực sự bị hủy hoặc giới hạn.
6. Kiểm tra transaction rollback/cancellation aftermath.
7. Lặp lại với driver/provider version đang triển khai.

### Không dùng sleep hoặc heavy query trên production để thử

Timeout tests có thể tiêu tốn CPU/lock resources. Dùng test database cô lập, có giới hạn thời gian và số sessions.

### Không dựa vào query.getHints() làm bằng chứng đủ

Việc API chấp nhận hoặc trả lại hint trong metadata **không chứng minh** database đã thực thi deadline như ý định.

## 32. Query timeout khác JDBC Statement timeout

JDBC có:

~~~java
Statement statement = connection.createStatement();
statement.setQueryTimeout(2); // Đơn vị seconds.
~~~

Trong khi JPA standard hint:

~~~java
query.setHint(
    "jakarta.persistence.query.timeout",
    2000
); // Đơn vị milliseconds.
~~~

### Vì sao dễ nhầm?

Hai API dùng đơn vị khác nhau. Provider có thể ánh xạ JPA timeout sang JDBC mechanisms nhưng conversion/granularity phụ thuộc implementation.

### Không điều khiển JDBC Statement tùy ý bên dưới JPA

Nếu JPA provider tự tạo PreparedStatement, application không nên trộn raw JDBC Statement lifecycle để ép timeout cho một Query object khác trừ khi có integration được hỗ trợ rõ.

## 33. Query timeout khác lock timeout

JPA có hint:

~~~java
query.setHint(
    "jakarta.persistence.lock.timeout",
    250
);
~~~

Hint này liên quan **chờ để lấy pessimistic lock** trên những operation thích hợp, không phải giới hạn toàn bộ SELECT/UPDATE runtime.

### Ví dụ lock

~~~java
Product p = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE,
    Map.of(
        "jakarta.persistence.lock.timeout",
        250
    )
);
~~~

Trong JPA, lock timeout là một provider/DB-supported hint; hiệu lực, precision và fallback khác nhau. Nên thử trên DB thật.

### Có transaction vẫn có thể timeout

Nếu database lock contention lớn, operation có thể ném `LockTimeoutException` hoặc `PessimisticLockException` tùy phạm vi transaction failure. Không lẫn với `TransactionRequiredException` do thiếu transaction ngay từ đầu.

## 34. Transaction timeout khác query timeout

Trong Spring:

~~~java
@Transactional(
    readOnly = true,
    timeout = 5
)
public ProductPage search(...) {
    // ...
}
~~~

`timeout = 5` thường được diễn giải theo **seconds** trong Spring transaction annotation. Nó mô tả timeout cho transaction mới được tạo bởi transaction interceptor/manager phù hợp.

### Các hạn chế

- Method phải được Spring transaction interceptor thực sự xử lý.
- Một method tham gia transaction đã có thường không tự đặt lại deadline của outer transaction.
- Manager/provider/driver quyết định cách deadline được áp dụng tới SQL.
- Transaction timeout không tự áp hard timeout cho toàn bộ HTTP request/serialization.

**Không dùng @Transactional(timeout=5) như bằng chứng mọi truy vấn chắc chắn chấm dứt sau 5 giây.**

## 35. Query, transaction, lock và HTTP deadlines: bảng phân biệt

| Mechanism | Thường áp dụng cho | Không tự bảo đảm |
| --- | --- | --- |
| JPA `jakarta.persistence.query.timeout` | SQL query execution hint | Hard API/request deadline |
| JPA `jakarta.persistence.lock.timeout` | Lock acquisition/wait hint | Total query execution bound |
| JDBC `Statement.setQueryTimeout` | Statement execution | Connection pool wait/serialization |
| Spring `@Transactional(timeout=...)` | Transaction policy | Hủy mọi threads/calls đúng mốc |
| DB statement timeout | Statement ở database | Total web request deadline |
| Connection acquisition timeout | Chờ connection pool | SQL execution duration |
| HTTP gateway timeout | Request/response lifecycle | DB statement tự ngừng |
| Background job timeout | Job processing budget | Queries tự rollback nếu không tích hợp |

Timeout là **nhiều vòng bảo vệ khác nhau**. Cần định nghĩa deadline tổng cùng các budgets con, không nghĩ một số config duy nhất bảo vệ toàn hệ thống.

## 36. Query bị timeout không có nghĩa DB ngừng tức thì

Tùy provider/driver/database:

- Lệnh cancel có thể được gửi bất đồng bộ.
- Database có thể chỉ nhận cancel ở một điểm kiểm tra.
- Network/socket có thể đã lỗi, để session state chưa rõ.
- Transaction có thể bị đánh dấu rollback-only hoặc thất bại theo semantics DB.
- Resource cleanup vẫn cần diễn ra.

### Hướng xử lý

1. Không dùng lại transaction đã thất bại một cách mù quáng.
2. Để transaction manager rollback/close resources theo contract.
3. Trả lỗi có kiểm soát, tránh lộ SQL/schema nội bộ.
4. Ghi metric nguyên nhân/cancellation outcome.
5. Chỉ retry với transaction mới nếu operation được thiết kế idempotent và lỗi có tính transient.

**Một exception timeout không đồng nghĩa dữ liệu đã hoặc chưa commit theo mọi khả năng**. Với write transaction, phải xử lý trạng thái outcome không rõ đúng cách.

## 37. Database-level statement timeout: vòng bảo vệ tiếp theo

Ngoài JPA hints, DBMS thường cung cấp các cơ chế workload control, ví dụ giới hạn thời gian statement/session/role ở một số database.

### Lợi ích

- Không phụ thuộc hoàn toàn vào một query hint của application.
- Có thể áp toàn bộ SQL từ một app database role.
- Giúp ngăn một query chạy vô hạn khi provider không cancel như mong đợi.

### Những rủi ro cấu hình

- Timeout quá thấp làm hỏng migration/maintenance queries.
- Session-scoped setting có thể rò rỉ qua pooled connections nếu không reset.
- Transaction-scoped setting có semantics DB-specific.
- Application role và maintenance role có nhu cầu khác nhau.
- Statement timeout không giới hạn số rows/network bytes của response.

Cần phối hợp DBA/platform team để thiết lập theo **DBMS/version thực tế**, không dùng một câu lệnh SQL giả định portable cho mọi database.

## 38. Timeout budget ví dụ cho HTTP search

Giả sử SLA một search endpoint:

~~~text
HTTP overall budget:       3,000 ms
Connection acquisition:     300 ms
DB statement budget:       1,500 ms
Lock wait budget:            250 ms
App mapping/serialization:   500 ms
Safety margin:               650 ms
~~~

Các con số chỉ minh họa. Tổng budgets con có thể chồng nhau và không nhất thiết là phép cộng tuyến tính do cơ chế thực thi thực tế.

### Không để từng tầng đặt deadline lớn hơn phần thời gian còn lại

Nếu request đã tiêu tốn 2.5 giây trong queue, khởi động một query cho phép 10 giây không phù hợp SLA 3 giây. Thiết kế nâng cao cần propagate **remaining deadline** qua tầng ứng dụng và chọn timeouts phù hợp, đồng thời có database guardrails riêng.

## 39. Timeouts không thay thế concurrency limits

Giả sử một query chỉ chạy tối đa 2 giây, nhưng 1.000 người cùng gửi request nặng:

~~~text
1.000 queries × tối đa 2 giây
-> connection pool/CPU/IO vẫn có thể bị quá tải
~~~

Cần thêm:

- Rate limits theo user/tenant/API key.
- In-flight concurrency caps.
- Request queue có bound/backpressure.
- Separate quotas cho exports/reports.
- Maximum page size và byte budget.
- Fair scheduling cho multi-tenant workloads.

### Không cho một tenant monopolize toàn pool

Một tenant có thể phát nhiều truy vấn nặng và ảnh hưởng tenant khác. Quotas theo tenant hoặc workload class giúp bảo vệ tính sẵn sàng chung.

## 40. Timeout và read-only transaction

Trong Spring:

~~~java
@Transactional(
    readOnly = true,
    timeout = 5
)
public ProductPage search(
        ProductSearchRequest request) {
    // ...
}
~~~

Read-only hint có thể giúp transaction manager/provider tối ưu certain reads nhưng:

- Không thay tenant/ACL predicates.
- Không cấm mọi write tuyệt đối theo mọi DB/provider.
- Không tự giới hạn page size.
- Không bảo đảm statement timeout được DB enforce.
- Không tạo index hoặc sửa query plan.

**Read-only, timeout và authorization là ba trách nhiệm khác nhau.**

## 41. Thời gian transaction dài nguy hiểm với locking

Một search endpoint thuần đọc có thể không cần pessimistic locking. Nếu thêm:

~~~java
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
~~~

thì có thể giữ locks và gây tranh chấp với writers. Lock mode khác NONE có transaction requirements và concurrency implications.

### Khi nào phải lock?

Với use case “đọc rồi giữ chỗ kho”, lock có thể là một phần của atomic operation và phải nằm trong transaction phù hợp. Với public search/reporting, thường không nên dùng pessimistic lock chỉ để “an toàn hơn”.

**Đừng biến một endpoint tìm kiếm thành transaction giữ khóa lâu.**

## 42. Ví dụ domain cho một search API có giới hạn

Giả sử có entity:

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    private Category category;

    protected Product() {}
}
~~~

`Category` là entity có ID tương ứng, không cần materialize toàn bộ quan hệ khi search chỉ trả vài trường Product.

API cho phép:

~~~text
skuPrefix: optional String 2..32
pageSize: int 1..100
afterId: optional positive Long

Response fields:
  id, sku, name, price
~~~

Không cung cấp arbitrary SQL, entity name, field path, tùy ý JOIN hoặc public tenantId parameter.

## 43. Request/response DTO

~~~java
public record ProductSearchRequest(
    String skuPrefix,
    int pageSize,
    Long afterId
) {}

public record ProductRow(
    Long id,
    String sku,
    String name,
    BigDecimal price
) {}

public record ProductPage(
    List<ProductRow> items,
    Long nextAfterId
) {}
~~~

Trong ví dụ, cursor đi theo ID ascending. `nextAfterId == null` có nghĩa tại thời điểm query chưa phát hiện page kế tiếp.

Một API production có thể dùng opaque, signed cursor với filter hash/tenant/expiry, nhưng kể cả có chữ ký thì query vẫn phải tái áp authorization cho mọi request.

## 44. AuthorizationService lấy tenant đáng tin

~~~java
public interface AuthorizationService {
    Long requireCurrentTenantWithPermission(
        String permission);
}
~~~

Implementation lấy tenant từ security principal/session do server tin cậy và từ chối request thiếu permission. **Không lấy tenantId do client tự gửi** để đặt phạm vi query.

Nếu cần admin cross-tenant export, phải có permission và audit riêng.

## 45. Criteria API: scope, cursor, page size và timeout

Ví dụ Spring:

~~~java
@Service
public class ProductSearchService {

    private static final int MAX_PAGE_SIZE = 100;
    private static final int QUERY_TIMEOUT_MS = 1500;

    @PersistenceContext
    private EntityManager em;

    private final AuthorizationService authorization;

    public ProductSearchService(
            AuthorizationService authorization) {
        this.authorization = authorization;
    }

    @Transactional(readOnly = true, timeout = 5)
    public ProductPage search(ProductSearchRequest request) {

        if (request.pageSize() < 1
                || request.pageSize() > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "pageSize phải trong khoảng 1..100");
        }

        if (request.afterId() != null
                && request.afterId() < 0) {
            throw new IllegalArgumentException(
                "afterId không hợp lệ");
        }

        Long tenantId =
            authorization.requireCurrentTenantWithPermission(
                "product:read");

        CriteriaBuilder cb = em.getCriteriaBuilder();
        CriteriaQuery<ProductRow> cq =
            cb.createQuery(ProductRow.class);

        Root<Product> root = cq.from(Product.class);
        List<Predicate> predicates = new ArrayList<>();

        // Mandatory authorization scope.
        predicates.add(
            cb.equal(root.<Long>get("tenantId"), tenantId)
        );

        predicates.add(
            cb.isTrue(root.<Boolean>get("active"))
        );

        if (request.afterId() != null) {
            predicates.add(
                cb.greaterThan(
                    root.<Long>get("id"),
                    request.afterId()
                )
            );
        }

        if (request.skuPrefix() != null) {
            String prefix = request.skuPrefix().trim();

            if (prefix.length() < 2
                    || prefix.length() > 32) {
                throw new IllegalArgumentException(
                    "skuPrefix phải dài 2..32 ký tự");
            }

            predicates.add(
                cb.like(
                    root.<String>get("sku"),
                    escapeLikeLiteral(prefix) + "%",
                    '\\'
                )
            );
        }

        cq.select(
            cb.construct(
                ProductRow.class,
                root.get("id"),
                root.get("sku"),
                root.get("name"),
                root.get("price")
            )
        );

        cq.where(
            cb.and(predicates.toArray(Predicate[]::new))
        );
        cq.orderBy(cb.asc(root.get("id")));

        TypedQuery<ProductRow> query =
            em.createQuery(cq);

        query.setMaxResults(request.pageSize() + 1);
        query.setHint(
            "jakarta.persistence.query.timeout",
            QUERY_TIMEOUT_MS
        );

        List<ProductRow> fetched =
            query.getResultList();

        int count = Math.min(
            request.pageSize(),
            fetched.size()
        );

        List<ProductRow> items = List.copyOf(
            fetched.subList(0, count)
        );

        boolean hasNext =
            fetched.size() > request.pageSize();

        Long next = hasNext
            ? items.get(items.size() - 1).id()
            : null;

        return new ProductPage(items, next);
    }

    private static String escapeLikeLiteral(
            String value) {
        return value
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_");
    }
}
~~~

Code minh họa sử dụng các imports từ Jakarta Persistence Criteria, Spring Transaction/Service, Java collections và entity/DTO đã định nghĩa. Controller phải parse/validate input theo HTTP contract, rồi gọi managed service qua Spring proxy.

### Những lớp phòng vệ có trong ví dụ

- Tenant ID đến từ authorization service.
- `active` là server-defined predicate.
- User chỉ chọn optional prefix và cursor trong phạm vi xác định.
- Prefix được validate/escape; query dùng Criteria.
- Query lấy tối đa `pageSize + 1` DTOs.
- Order theo ID ổn định.
- JPA query-timeout hint được gắn với một transaction read-only.

### Những điều ví dụ chưa tự bảo đảm

- Database index/query plan tốt.
- Provider và JDBC driver thực thi timeout chính xác.
- Permission chi tiết theo từng Product ngoài tenant.
- Signed cursor, cross-request snapshot consistency.
- Response byte budget và rate/concurrency limit.
- Monitoring và exception translation.

Đó là lý do phải kết hợp mã repository với API/database-level controls.

## 46. Sort động: map enum thay vì nối chuỗi JPQL

~~~java
public enum ProductSort {
    SKU,
    CREATED_AT
}
~~~

Với Criteria:

~~~java
Path<?> path = switch (sort) {
    case SKU -> root.get("sku");
    case CREATED_AT -> root.get("createdAt");
};

cq.orderBy(
    cb.asc(path),
    cb.asc(root.get("id"))
);
~~~

Client được chọn từ enum allowlist, không gửi arbitrary field path. Khi sort theo `sku, id`, cursor phải chứa cả sku và id:

~~~text
sku > cursorSku
OR (sku = cursorSku AND id > cursorId)
~~~

Nếu sort theo createdAt/descending, dùng comparator/predicate phù hợp. **Không dùng afterId đơn lẻ với một sort order không dựa vào id.**

## 47. Sort/filters cần index phù hợp

Với tenant-scoped search, một composite index có thể gồm các cột tenant, active và sort key, nhưng thứ tự index tốt nhất phụ thuộc selectivity, query predicates và database engine.

Hãy dùng EXPLAIN hoặc EXPLAIN ANALYZE trên dataset representative để quan sát:

- Rows scanned/returned.
- Full scans và sorts.
- Temporary tables/disk spills.
- Index usage.
- Lock waits.
- Estimated versus actual rows.

`LIMIT 50` và statement timeout là giới hạn bổ sung; chúng không thay việc thiết kế query/index tốt.

## 48. Không cho client chọn fetch graph tùy ý

Endpoint:

~~~text
GET /orders?include=lines,customer,payments,events,logs
~~~

có thể vô tình materialize một graph lớn, thậm chí lộ fields nhạy cảm.

Chỉ hỗ trợ những response shapes được review:

~~~text
OrderListItem
OrderDetails
OrderFinancialSummary (permission required)
~~~

Mỗi shape có DTO, query/fetch plan, authorization và row/byte budgets riêng. Một API có dynamic include thì phải giới hạn association depth, collection fan-out và combinations.

## 49. GraphQL và query DSL cũng cần complexity budget

Nếu ứng dụng cho một DSL/filter tree:

~~~text
deep nesting
many aliases
multiple collection expansions
expensive aggregate/regex operators
unbounded OR branches
~~~

thì cần:

- Maximum query depth.
- Maximum filter nodes.
- Maximum selected fields.
- Maximum JOIN/collection expansions.
- Per-field authorization.
- Result size/deadline budgets.
- Rate/concurrency limits.

JPA Metamodel có thể giúp xác nhận field tồn tại, **không chứng minh field được phép public query**.

## 50. Row limit và response byte limit

`setMaxResults(100)` vẫn có thể trả rất nhiều bytes nếu mỗi row chứa CLOB, large JSON, base64 hoặc nested collections.

Ngoài row maximum, cân nhắc:

- Projection chỉ những cột cần dùng.
- Không include BLOB/CLOB ở list endpoints.
- Max response bytes.
- Tách file/media download endpoint với authorization.
- Streaming với backpressure.

**Số rows và số bytes là hai đơn vị chi phí khác nhau.**

## 51. Pagination liên tiếp cũng có thể gây tải

Một bot có thể gọi page size 50 nhưng duyệt 100.000 pages liên tục. Giới hạn mỗi page vẫn không đủ.

Có thể đặt:

- Max cursor lifetime.
- Per-user search request quota.
- Per-tenant query budget.
- Maximum accessible window cho synchronous API.
- Export workflow riêng khi cần toàn bộ dataset.

Cursor được ký hoặc mã hóa chỉ bảo vệ một phần integrity/confidentiality của cursor, không thay authorization, query complexity hoặc rate limiting.

## 52. Xuất dữ liệu lớn nên có workflow riêng

Thay vì:

~~~text
GET /api/orders/export?all=true
~~~

giữ một HTTP request và DB connection rất lâu, dùng:

~~~text
POST /exports
  -> authenticate + authorize
  -> validate filters and quotas
  -> create ExportJob(PENDING)
  -> return jobId

Background worker:
  -> acquire quota
  -> fetch bounded chunks
  -> write output incrementally
  -> checkpoint progress
  -> mark COMPLETE/FAILED/CANCELED

GET /exports/{jobId}
  -> check owner and tenant

GET /exports/{jobId}/download
  -> authorize again, limited retention
~~~

### Background không đồng nghĩa không giới hạn

Job vẫn cần max rows, bytes, runtime, concurrent workers, queue length, cancellation và cleanup. Không biến synchronous DoS thành **unbounded job queue**.

## 53. Admission control theo user và tenant

Policy minh họa:

~~~text
Regular search:
  20 requests/minute/user
  100 requests/minute/tenant

Heavy report:
  2 concurrent jobs/tenant
  5 queued jobs/tenant

Export:
  max rows: 1,000,000/job
  max bytes: 500 MiB/job
~~~

Các con số không phải tiêu chuẩn bắt buộc; cần đánh giá theo SLA/capacity và đối tượng người dùng. Dùng distributed quota storage/admission control khi ứng dụng chạy trên nhiều instances, không chỉ một in-memory HashMap trên từng node.

### Đảm bảo công bằng

Quota per-user giúp tránh một tài khoản lạm dụng; quota per-tenant giúp tránh một tổ chức tiêu thụ toàn bộ pool/database capacity của những tổ chức khác.

## 54. Backpressure và bounded work queues

Queue không giới hạn không bảo vệ được hệ thống khi reports/exports đến quá nhanh.

~~~text
Incoming requests
       |
       v
 Admission control
   /        \
Quota OK   Quota exhausted
   |         |
   v         v
Bounded     Reject/defer
queue       with clear retry policy
   |
   v
Limited workers
   |
   v
Bounded queries
~~~

Giới hạn:

- Số jobs được đợi.
- Số jobs chạy cùng lúc.
- Thời gian tồn tại trong queue.
- Thời gian runtime mỗi job.
- Retries và idempotency.
- Số rows/bytes được xuất.

Nếu worker bị hủy, phải release resource và không để DB statement/cursor tiếp tục chiếm capacity ngoài ý muốn.

## 55. Connection pool là tài nguyên chung

Một query nặng có thể chiếm JDBC connection. Nhiều queries chạy đồng thời sẽ làm requests khác phải chờ connection, thậm chí timeout ở pool.

### Theo dõi

- Pool active, idle và pending acquisition.
- Connection acquisition latency.
- DB query duration.
- Transaction duration.
- Lock waits, blocking sessions.
- Canceled statements và session cleanup.

Một HTTP timeout không có nghĩa database tự dừng query ngay lập tức. Cần liên kết cancellation semantics và pool/resource lifecycle với DB-specific safeguards.

## 56. Không giữ transaction qua external call dài

Ví dụ:

~~~text
BEGIN TRANSACTION
   Read 5,000 Orders
   Call external analytics API (20 seconds)
   Write export metadata
COMMIT
~~~

Transaction có thể giữ connection, locks hoặc snapshot resources quá lâu.

### Hướng tốt hơn

Phân tách report state transitions:

~~~text
TX1: create ExportJob(PENDING), commit

Background worker:
  query bounded chunks
  write to object storage

TX2: mark ExportJob(COMPLETE), commit
~~~

Nếu nghiệp vụ cần snapshot nhất quán xuyên chunks, phải thiết kế isolation/cut-off/export snapshot strategy rõ ràng. Chia transaction cơ học mà không xét consistency là sai.

## 57. Xử lý QueryTimeoutException

JPA có thể ném `QueryTimeoutException` khi query timeout theo semantics mà transaction không bị đánh dấu rollback toàn bộ, hoặc provider có thể bọc một lỗi khác.

### Đừng nhầm timeout với kết quả rỗng

Sai:

~~~java
try {
    return query.getResultList();
} catch (PersistenceException ex) {
    return List.of();
}
~~~

Một query bị timeout **không có nghĩa database không chứa rows**. Trả empty list có thể làm client tưởng tìm kiếm thành công nhưng không có dữ liệu.

### Cách đúng

- Phân loại exception và cause chain.
- Để transaction owner rollback/cleanup theo trạng thái thật.
- Trả lỗi tường minh và có kiểm soát.
- Ghi timeout metric không lộ SQL/bind values nhạy cảm.
- Retry chỉ khi transient và có budget.

## 58. LockTimeoutException và PessimisticLockException

Nếu endpoint cố lấy pessimistic lock:

~~~java
em.find(
    Product.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

có thể gặp:

| Exception | Hướng xử lý |
| --- | --- |
| `LockTimeoutException` | Lock wait timeout theo operation/DB semantics |
| `PessimisticLockException` | Lock acquisition failed, transaction effects cần xét |
| `TransactionRequiredException` | Operation yêu cầu transaction nhưng không có |

Đừng gọi tất cả chúng là “query quá chậm”. Có transaction nhưng không lấy được lock là bài toán concurrency khác thiếu transaction hoặc full-table scan.

## 59. Timeout và trạng thái transaction

Sau cancellation:

- Database có thể đã hủy statement.
- Transaction có thể rollback-only hoặc cần rollback, tùy provider/DB.
- Connection/session có thể cần cleanup.
- Với một write request, trạng thái commit có thể không rõ khi mất kết nối.

### Không tiếp tục trên transaction lỗi

Không bắt exception rồi chạy queries khác trên cùng persistence context/transaction nếu provider/database đã đánh dấu invalid/rollback-only.

### Với write operation có retry

Chỉ retry bằng **transaction mới** với idempotency key và kiểm tra outcome nếu commit state mơ hồ. Không tạo duplicate orders/payments chỉ vì client thấy timeout.

## 60. Mapping errors sang HTTP response

Một API có thể có chính sách:

| Điều kiện | HTTP status thường phù hợp |
| --- | --- |
| Input sai, size quá lớn, filter không hỗ trợ | 400 |
| Chưa xác thực | 401 |
| Có xác thực nhưng không có quyền | 403 |
| Rate limit/tenant quota exceeded | 429 |
| DB/dependency tạm thời không khả dụng | 503 |
| Gateway timeout | 504 |
| Lỗi server không dự kiến | 500 |

Đây là **gợi ý API design**, không phải mapping JPA exception → HTTP status bắt buộc. Lựa chọn thực tế tùy request pipeline và lỗi xảy ra ở tầng nào.

### Error payload

Nên có:

~~~json
{
  "code": "SEARCH_LIMIT_EXCEEDED",
  "message": "Kích thước trang tối đa là 100.",
  "requestId": "trace-id"
}
~~~

Không trả raw SQL, stack trace, schema names, tenant IDs không thuộc quyền hoặc database connection details cho client.

## 61. Retry storm sau timeout

Một chuỗi:

~~~text
Query timeout
  -> Client retry immediately
  -> Query timeout
  -> Client retry immediately
  -> ...
~~~

có thể khiến database càng quá tải.

### Chính sách nên có

- Không retry lỗi input không hợp lệ hoặc quota exceeded.
- Retry có giới hạn cho transient failures.
- Backoff và jitter.
- Retry-After khi phù hợp.
- Global retry budget.
- Caching hoặc degradation strategies cho dữ liệu ít thay đổi.

Retries cũng tiêu thụ quota; không để nhiều clients nhân số truy vấn từ một endpoint bình thường thành hàng triệu statements.

## 62. Theo dõi query fingerprints thay vì dữ liệu nhạy cảm

Log:

~~~text
traceId
operation=product.search
queryTemplateId=product_search_v1
tenantHash/tenantInternalId theo policy
pageSize
numberOfFilters
rowsReturned
durationMs
timeoutCategory
status
~~~

Không log toàn bộ search text, emails, personal identifiers, raw bind values hoặc SQL chứa secrets nếu không có quyền/chính sách bảo vệ tương ứng.

### Tại sao dùng query fingerprints?

Cho phép thống kê truy vấn dạng nào làm DB chậm mà không cần lưu toàn bộ input của người dùng.

### Metrics riêng cho export

Thêm jobs active/queued, rows written, bytes, retries, checkpoint age, cancellation count và maximum runtime.

## 63. Chỉ số giám sát quan trọng

| Metric | Tín hiệu |
| --- | --- |
| Search latency p95/p99 | Tail latency cao |
| JDBC execution time | Database/query cost |
| Timeouts per query template | Queries vượt budget |
| Rows scanned/returned ratio | Filters/indexes không hiệu quả |
| Response size bytes | Không chỉ đếm rows |
| Active DB connections | Pool saturation |
| Connection acquire wait | Backpressure |
| Lock waits | Transaction contention |
| Requests rejected by policy | Client gửi quá hạn mức |
| Per-tenant queries/second | Fairness |
| Export queued/running | Heavy workload |
| DB CPU/temp IO | Sort/hash/aggregation cost |
| JVM heap/GC | Entity/DTO materialization pressure |

Nên phân loại theo endpoint và query template, không cần nhúng user input trực tiếp vào metric label có high cardinality.

## 64. Query plan regression khi đổi mapping hoặc index

Một query từng nhanh có thể chậm sau:

- Thêm JOIN FETCH/association vào mapping.
- Tăng dữ liệu nhanh.
- Thay index/schema.
- Thay database statistics.
- Thay predicate từ equality sang leading wildcard.
- Bật dynamic sorting trên cột mới.

### Cách phòng ngừa

Giữ một bộ slow-query/query-plan benchmarks trong staging với data representative và workload distributions.

Kết hợp:

- EXPLAIN plans.
- Query latency budgets.
- Connection/lock metrics.
- Load tests dưới concurrency tương đương.

Timeout threshold chỉ cắt hậu quả; **tối ưu query plan** xử lý một phần nguyên nhân.

## 65. Phân biệt quyền list và quyền export

Một user được phép xem 30 Products mỗi page **không mặc nhiên có quyền tải toàn bộ catalog**.

Policy có thể tách:

~~~text
product:read
product:search
product:export
product:report:financial
~~~

Mỗi operation có:

- Authorized scope.
- Allowed filters/sorts.
- Size/time/concurrency budgets.
- Audit policy.
- Response field visibility.

Không dựa trên việc client gửi `isAdmin=true` để bỏ page limit.

## 66. Export phải kiểm tra quyền lại khi tải file

Ngay cả khi tạo job đã authorize, khi download cần xác nhận:

- Người tải là job owner hoặc có permission tương đương.
- Job thuộc tenant phù hợp.
- File chưa hết hạn/đã bị thu hồi.
- Link đã ký có TTL phù hợp nếu dùng pre-signed URL.
- Data retention và audit rules.

Không đặt file với URL đoán được rồi cho tải không cần xác thực. Giới hạn truy vấn không chỉ kết thúc lúc query DB xong; **đầu ra dữ liệu** cũng cần bảo vệ.

## 67. RLS và pooled connections

Nếu dùng database row-level security (RLS) dựa trên session/transaction variables, phải đặt trusted tenant context đúng scope:

~~~text
Acquire connection
  -> set trusted tenant context
  -> execute scoped query
  -> clear/reset context
  -> return connection to pool
~~~

Nếu quên reset session context, connection tái sử dụng có thể mang tenant setting cũ, gây lỗi confidentiality.

Đây là DB/provider-specific integration cần integration tests trên connection pool thật. Không assume JPA tenant predicate tự sửa một lỗi session RLS.

## 68. Lỗi bảo mật khi ghép OR không đúng

Giả sử intent:

~~~text
tenant_id = currentTenant
AND (
  sku LIKE 'BK%'
  OR category_id = 10
)
~~~

Một implementation sai:

~~~text
tenant_id = currentTenant
AND sku LIKE 'BK%'
OR category_id = 10
~~~

có thể trả Product của tenant khác nếu điều kiện category đúng.

### Integration test bắt buộc

Tạo fixture:

~~~text
Tenant A:
  Product A1 (sku BK-1)

Tenant B:
  Product B1 (category 10)
~~~

Gọi search dưới danh tính Tenant A với cả hai filters/OR, khẳng định **không bao giờ thấy B1**.

Đây là ví dụ cho thấy authorization predicate phải được đặt **ngoài mọi user-controlled OR**.

## 69. Integration test: page size không vượt max

Test controller/service:

~~~java
@Test
void pageSizeMustBeBounded() {
    ProductSearchRequest invalid =
        new ProductSearchRequest("BK", 1000, null);

    assertThrows(
        IllegalArgumentException.class,
        () -> productSearchService.search(invalid)
    );
}
~~~

Một test HTTP nên kiểm tra response status/error code đúng policy, không chỉ Java exception.

### Boundary values

Thử:

~~~text
size = -1
size = 0
size = 1
size = 100
size = 101
size = Integer.MAX_VALUE
~~~

Không chỉ thử một giá trị bất thường.

## 70. Integration test: cross-tenant access

Fixture:

~~~text
Tenant A:
  Product A1
  Product A2

Tenant B:
  Product B1
  Product B2
~~~

Chạy search với principal Tenant A rồi kiểm tra mọi ProductRow thuộc A theo fixture expectations.

Các test bổ sung:

- Client sửa cursor/afterId.
- Client gửi field/tenant ID ngoài contract.
- Client thay OR filters để cố bypass.
- Pagination page 2 không lộ tenant B.
- Export/job download cross tenant bị từ chối.

Không chỉ test `WHERE tenantId` ở một repository method; cần test toàn đường API, nhất là dynamic filters.

## 71. Integration test: LIKE escaping

Tạo Products:

~~~text
SKU: BK-100
SKU: BK%REAL
SKU: BK_REAL
~~~

Nếu người dùng tìm literal prefix `BK%`, chỉ những SKU chứa ký tự percent đúng nghĩa mới match theo policy, không biến percent thành wildcard có thể match mọi BK prefix.

Các case:

- `%`.
- `_`.
- Backslash.
- Unicode.
- Case-folding/collation.
- Blank/too-long prefix.

Kiểm thử trên DBMS thật vì SQL LIKE escaping/collation có khác biệt giữa dialects.

## 72. Integration test: query timeout

Một test database cô lập:

1. Tạo/chọn slow query fixture có thời gian xử lý biết trước.
2. Đặt `jakarta.persistence.query.timeout` ở mức thấp.
3. Đo elapsed time thực.
4. Ghi exception class/cause.
5. Kiểm tra statement cancellation outcome.
6. Xác nhận connection/transaction cleanup.
7. Sau đó chạy query đơn giản để xác nhận pool/DB còn hoạt động.

### Điều không nên làm

Không tự gửi expensive cross joins hoặc cố ý giữ locks trên production để test timeout.

**Provider support là điều phải đo**, không thể chỉ assert `getHints()` trả 2000.

## 73. Integration test: lock timeout khác statement timeout

Dùng hai transactions thật:

~~~text
TX1:
  lock Product #10
  giữ lock một thời gian ngắn có kiểm soát

TX2:
  cố lock Product #10 với lock timeout
  quan sát lỗi và thời gian chờ
~~~

Kiểm tra loại exception/transaction effects theo provider/database. Không lẫn kết quả với statement execution timeout hoặc missing transaction.

### Cleanup

Trong finally, rollback hoặc commit đúng owner; release connections, tránh để test gây lock hanging làm các tests sau fail.

## 74. Integration test: deep OFFSET và query plan

Tạo dataset đủ lớn (trong test environment) và so sánh:

~~~text
OFFSET 0 + LIMIT 50
OFFSET 100000 + LIMIT 50
KEYSET id > lastId + LIMIT 50
~~~

Đo:

- SQL elapsed time.
- Rows scanned.
- Sort work.
- Index usage.

Không suy keyset luôn nhanh hơn: nếu filters/sort/index không phù hợp, nó cũng có thể chậm. Query policy vẫn phải có timeouts và result bounds.

## 75. Integration test: nhiều concurrent expensive requests

Giả lập nhiều users/tenants cùng gửi:

~~~text
100 concurrent search requests
each pageSize <= 100
some filters expensive
~~~

Kiểm tra:

- Rate limit/admission control có hoạt động không.
- Pool có giữ một phần capacity cho requests khác không.
- p95 latency và timeout rate.
- Không có unbounded queue.
- Rejected requests trả 429/response phù hợp.
- Không lộ dữ liệu giữa tenants.

Đây là kiểm thử availability, bổ sung cho correctness tests.

## 76. Sơ đồ chẩn đoán truy vấn chậm

~~~text
Request search chậm
         |
         v
Input có vượt contract?
    /           \
  Có             Không
  |                |
  v                v
Reject 400    Authorized scope đúng?
                       |
                       v
              Query shape/index tốt?
                  /          \
                Không        Có
                 |            |
                 v            v
              Optimize    DB locks/pool?
              query plan   /        \
                         Có          Không
                         |             |
                         v             v
                     Fix locking  Measure DB/serialization
                                      |
                                      v
                            Check timeout enforcement,
                            row/byte limits/concurrency
~~~

**Đừng chỉ tăng query timeout** khi database đang slow vì missing index hoặc query shape không phù hợp. Tăng timeout có thể khiến connections bị giữ lâu hơn và làm sự cố availability nghiêm trọng hơn.

## 77. Bảng đối chiếu các biện pháp

| Biện pháp | Ngăn vấn đề gì? | Không giải quyết |
| --- | --- | --- |
| Parameter binding | Injection qua values | Arbitrary query shape, large scan |
| Field/operator allowlist | Unreviewed query expressions | Tenant leaks nếu WHERE thiếu |
| Mandatory tenant predicate | Cross-tenant rows | Query quá chậm |
| ACL/ownership checks | Record-level access | Request concurrency overload |
| `setMaxResults()` | Số root results | Sort/scan cost, graph size |
| Max offset | Deep OFFSET abuse | Expensive first page |
| Keyset cursor | Deep paging efficiency khi index phù hợp | Authorization, snapshot |
| Filter length/complexity limits | Oversized filter trees | DB lock contention |
| DTO projection | Materialization/serializer graph | SQL scan/aggregation cost |
| Query timeout hint | Một lớp thời gian SQL | Hard deadline tuyệt đối |
| DB statement timeout | Server-side statement runtime | Whole HTTP response bytes |
| Lock timeout | Lock wait | Full query execution |
| Transaction timeout | Transaction lifetime policy | Query shape authorization |
| Rate/concurrency caps | Multi-request resource exhaustion | Individual slow query root cause |
| Export job quota | Heavy workload scheduling | Data authorization nếu thiếu |
| RLS | Defense-in-depth row filtering | Bad context setup/pool leaks |
| Observability | Phát hiện bottlenecks | Tự sửa dữ liệu/query |

## 78. Bài tập thực hành

### Bài 1 — Phạm vi và quyền

Một client gửi `tenantId=42` trên search endpoint. Có nên dùng giá trị này trực tiếp làm điều kiện xác lập quyền xem dữ liệu không?

**Gợi ý:** Không. Tenant scope phải đến từ trusted identity hoặc authorization logic; một admin chọn tenant vẫn cần quyền được kiểm tra.

### Bài 2 — Query shape

Vì sao không nên nhận một chuỗi JPQL tùy ý từ URL rồi gọi `em.createQuery(jpql)`?

**Gợi ý:** Client điều khiển entity paths, joins, predicates và query complexity; nguy cơ injection, DoS và truy cập quá phạm vi.

### Bài 3 — Parameter binding

`setParameter("sku", value)` giải quyết nhóm rủi ro gì, và không giải quyết nhóm gì?

**Gợi ý:** Bảo vệ giá trị và typing; không tự hạn chế row count, field selection, tenant authorization hoặc query cost.

### Bài 4 — ORDER BY

User gửi `sort=secretSupplierContract`. Field này tồn tại trong entity nhưng không thuộc public API allowlist. Có nên chấp nhận?

**Gợi ý:** Không. JPA-mapped attribute không đồng nghĩa client được quyền truy vấn nó.

### Bài 5 — Page size

Thiết kế kiểm tra cho `pageSize` chỉ trong khoảng 1..100. Kiểm tra các giá trị -1, 0, 1, 100 và 101.

**Gợi ý:** Reject hoặc clamp theo policy, nhưng tuyệt đối không thực hiện với size tùy ý vượt hard maximum.

### Bài 6 — LIMIT

Tại sao `setMaxResults(50)` không bảo đảm database chỉ đọc 50 rows?

**Gợi ý:** ORDER BY, WHERE, GROUP BY, JOIN và aggregations có thể cần xét tập lớn trước LIMIT.

### Bài 7 — OFFSET

Vì sao `setFirstResult(page * size)` cần kiểm tra integer overflow?

**Gợi ý:** Phép nhân int có thể overflow; hãy dùng long và max offset policy trước khi cast.

### Bài 8 — Deep pagination

Một client gửi page=500000 và size=50. Hãy nêu hai cách bảo vệ.

**Gợi ý:** Max offset/page window, keyset pagination hoặc export workflow riêng.

### Bài 9 — Cursor

Một cursor hợp lệ được ký bởi server có tự chứng minh user được phép truy cập Product nào cũng được không?

**Gợi ý:** Không. Authorization/tenant predicates phải áp dụng lại cho mỗi page.

### Bài 10 — Stable ordering

Nếu sort theo `createdAt` và nhiều rows có cùng timestamp, cursor cần thêm gì?

**Gợi ý:** Unique tiebreaker như id và predicate lexicographic phù hợp.

### Bài 11 — Cursor filter changes

User đổi filter giữa hai requests nhưng dùng lại cursor của truy vấn cũ. Nên xử lý gì?

**Gợi ý:** Bind cursor với filter hash/query version hoặc reject cursor không phù hợp.

### Bài 12 — LIKE wildcard

Nếu user tìm literal `BK%`, có nên đưa thẳng vào LIKE prefix mà không escape không?

**Gợi ý:** Không, nếu semantics là literal prefix; `%` là wildcard.

### Bài 13 — Leading wildcard

Tại sao mẫu `LIKE '%abc%'` thường có thể tốn hơn `LIKE 'abc%'`?

**Gợi ý:** Cách sử dụng B-tree indexes thông thường khác nhau; xác minh bằng EXPLAIN trên DBMS thật.

### Bài 14 — IN clause

User gửi 200.000 IDs trong một request. Cần giới hạn gì?

**Gợi ý:** Max elements/bytes; cân nhắc batch endpoints và vẫn kiểm tra quyền trên từng ID.

### Bài 15 — AND/OR

So sánh hai điều kiện:

~~~text
tenant = A AND name = X OR category = Y

tenant = A AND (name = X OR category = Y)
~~~

Vì sao điều kiện đầu có thể leak dữ liệu?

**Gợi ý:** Precedence khiến nhánh OR không còn bị giới hạn bởi tenant.

### Bài 16 — Time window

Endpoint chỉ cho phép dữ liệu 31 ngày gần nhất, nhưng client yêu cầu 6 năm. Nên làm gì?

**Gợi ý:** Trả validation error hoặc chuyển sang báo cáo/export được cấp quyền và quota riêng.

### Bài 17 — GROUP BY

Tại sao result chỉ có 10 groups vẫn có thể là query rất đắt?

**Gợi ý:** DB có thể phải scan/aggregate rất nhiều rows trước khi trả groups.

### Bài 18 — COUNT

UI chỉ cần nút Next. Có nhất thiết phải chạy exact COUNT trên mọi search không?

**Gợi ý:** Không; có thể dùng size+1/Slice/hasNext nếu API contract cho phép.

### Bài 19 — Fetch graph

Vì sao `setMaxResults(50)` trên query JOIN FETCH Order.lines không bảo đảm chỉ 50 managed Java objects?

**Gợi ý:** Mỗi Order có thể có rất nhiều OrderLines; provider có thể còn có pagination caveats.

### Bài 20 — DTO projection

Vì sao trả DTO có thể giảm áp lực L1 và serialization khi chỉ cần id, sku, price?

**Gợi ý:** Tránh tạo/traverse graph managed entity không cần thiết.

### Bài 21 — Query timeout

Standard JPA hint nào đặt query execution timeout, đơn vị thường là gì?

**Gợi ý:** `jakarta.persistence.query.timeout`, milliseconds.

### Bài 22 — JDBC timeout

`Statement.setQueryTimeout(2)` và JPA query timeout 2000 mang đơn vị giống nhau không?

**Gợi ý:** Không; JDBC dùng seconds, JPA hint dùng milliseconds.

### Bài 23 — Provider support

`query.getHints()` trả lại timeout 2000. Có chứng minh DB đã hủy mọi query đúng 2 giây không?

**Gợi ý:** Chưa; cần integration test với provider/driver/DBMS thực.

### Bài 24 — Lock timeout

`jakarta.persistence.lock.timeout` và `jakarta.persistence.query.timeout` có cùng mục đích không?

**Gợi ý:** Không; lock acquisition vs query execution.

### Bài 25 — Spring transaction

`@Transactional(timeout=5)` có nhất thiết đặt lại deadline của outer transaction khi method tham gia existing transaction không?

**Gợi ý:** Không; transaction owner/propagation/manager quyết định.

### Bài 26 — HTTP timeout

Gateway trả 504 có chứng minh database statement tự dừng ngay không?

**Gợi ý:** Không; cancellation và SQL timeout cần integration riêng.

### Bài 27 — Transaction after timeout

Provider báo timeout trong một transaction ghi. Có nên tiếp tục flush và commit bất chấp không?

**Gợi ý:** Không; kiểm tra rollback/transaction state, cleanup và outcome.

### Bài 28 — Rate limit

Một query giới hạn 2 giây nhưng 1000 users gửi cùng lúc. Tại sao vẫn có DoS?

**Gợi ý:** CPU, connection pool và concurrency budget có giới hạn.

### Bài 29 — Per-tenant quota

Vì sao rate limit per-user chưa đủ trong multi-tenant SaaS?

**Gợi ý:** Một tenant có thể có hàng trăm users, cùng tiêu tốn tài nguyên của tenants khác.

### Bài 30 — Export

Vì sao export hàng triệu rows không nên luôn chạy trên HTTP GET đồng bộ?

**Gợi ý:** Connection/HTTP deadline, heap và cancellation; background job có quota/checkpoint/cleanup sẽ phù hợp hơn trong nhiều workload.

### Bài 31 — Download permission

Tạo export job đã authorize rồi thì download link có cần kiểm tra quyền nữa không?

**Gợi ý:** Cần owner/tenant permission, TTL, retention và audit phù hợp.

### Bài 32 — Retrying

Một search timeout liên tục do missing index. Client retry ngay 10 lần có giải quyết được không?

**Gợi ý:** Không; nguy cơ retry storm, cần query/index fix hoặc admission control.

### Bài 33 — RLS

Một pooled DB connection mang tenant session variable từ request cũ. Rủi ro gì?

**Gợi ý:** Truy cập nhầm tenant; phải quản lý/reset context đúng scope.

### Bài 34 — Query monitoring

Kể ít nhất sáu metrics để phát hiện search bị lạm dụng.

**Gợi ý:** p99 latency, timeouts, rows scanned/returned, bytes, active connections, pool wait, per-tenant QPS, export queue.

### Bài 35 — Query plan

Khi một search dù LIMIT 50 vẫn chạy 12 giây, nên kiểm tra gì trước khi chỉ tăng timeout?

**Gợi ý:** EXPLAIN, index/selectivity, sort, JOIN, count query, lock waits, database load.

### Bài 36 — Complexity

Một internal query builder cho phép 1000 OR nodes và nested associations vô hạn. Hãy đề xuất hard limits.

**Gợi ý:** Max nodes, depth, joins, IN elements, execution deadline, result rows và concurrency.

### Bài 37 — Error handling

Vì sao không nên catch mọi `PersistenceException` và trả danh sách rỗng?

**Gợi ý:** Timeout, DB failure hoặc permission error không tương đương không tìm thấy kết quả.

### Bài 38 — Security test

Tạo fixture của hai tenants để kiểm tra một OR condition không làm bỏ tenant filter.

**Gợi ý:** Tenant B có Product match nhánh OR thứ hai; search dưới Tenant A không được trả Product ấy.

### Bài 39 — Performance test

Thử OFFSET sâu và keyset cùng dataset/index, những metrics nào giúp so sánh?

**Gợi ý:** Rows scanned, query latency, sorts, EXPLAIN plan, memory, timeout rate.

### Bài 40 — Thiết kế tổng hợp

Thiết kế một API tìm kiếm Orders cho nhiều tenants với filters theo date/status/customer, tối đa 100 rows/page, export một năm dữ liệu cho admin và deadline 3 giây. Mô tả input policy, authorization, pagination, timeout layers, quotas, audit, integration tests và cleanup.

**Gợi ý:** Trusted tenant/ACL, allowlisted filters/sorts, half-open time window, indexed keyset, DTO/Slice, JPA/DB guardrails, export queue và per-tenant quota.

## 79. Checklist áp dụng cho một endpoint mới

Trước khi đưa một search endpoint ra production, trả lời:

- Người gọi được xác thực và có action permission nào?
- Tenant/owner/ACL scope có được **server bắt buộc áp dụng** ở mọi query path không?
- Query field/operator/sort allowlist đã được review chưa?
- Input size, IN length, OR nesting, JOIN depth và time window có giới hạn không?
- Page size, max offset hoặc cursor contract có hard bound không?
- Ordering có unique tiebreaker không?
- Có dữ liệu nhạy cảm/large fields bị vô tình fetch/serialize không?
- DTO projection có thể dùng thay managed entity không?
- Có count/aggregation query ẩn làm chi phí tăng không?
- Database có index/plan phù hợp query shape cho phép không?
- Query timeout, lock timeout và transaction timeout khác nhau có được cấu hình/thử nghiệm không?
- DB statement timeout có hoạt động với provider/driver hiện tại không?
- Rate/concurrency limits và bounded queue đã có chưa?
- Background export có quotas, ownership và lifecycle/cancellation không?
- Timeout/error có được báo chính xác mà không lộ SQL/secrets không?
- Có metrics và integration/load tests cho worst-case query không?

Checklist này phục vụ **thiết kế endpoint**; không thay việc đánh giá định kỳ theo dữ liệu, hành vi người dùng và môi trường triển khai thực tế.

## 80. Bảng ghi nhớ nhanh

| Chủ đề | Nguyên tắc |
| --- | --- |
| Người dùng chọn filter | Chỉ những fields/operators cho phép |
| User-provided SQL/JPQL | Không thực thi tùy ý |
| Parameter binding | Bảo vệ values, không thay query budget |
| Tenant scope | Lấy từ trusted identity |
| ACL/owner scope | Bắt buộc trong query theo quyền |
| AND/OR | Server predicate phải bao phủ mọi nhánh |
| Page size | Hard maximum tại server |
| `setMaxResults()` | Giới hạn results, không giới hạn scan/sort |
| OFFSET sâu | Max offset hoặc keyset |
| Keyset | Cần stable sort, unique tiebreaker |
| Cursor | Có thể ký/expire; không thay authorization |
| LIKE | Parameter binding không escape wildcard literal |
| IN | Max elements/parameters |
| JOIN/OR depth | Bounded query shape |
| Date range | Max window, half-open bounds |
| GROUP BY/COUNT | Có thể scan nhiều rows trước LIMIT |
| Entity graph | Có thể tải thêm rất nhiều associations |
| DTO projection | Tránh managed graph không cần thiết |
| Query timeout hint | `jakarta.persistence.query.timeout`, milliseconds |
| Lock timeout hint | `jakarta.persistence.lock.timeout`, milliseconds |
| JDBC Statement timeout | `setQueryTimeout(seconds)` |
| Transaction timeout | Transaction-level deadline/policy |
| HTTP timeout | Không tự cancel database SQL |
| Provider timeout support | Phải xác minh thực tế |
| DB statement timeout | Một lớp bảo vệ bổ sung |
| Cancellation | Có thể best-effort, cần cleanup |
| Timeout exception | Không có nghĩa result rỗng |
| Rate limit | Ngăn lạm dụng nhiều requests |
| Concurrency cap | Bảo vệ pool/DB capacity |
| Heavy export | Job có quota/checkpoint/cancel |
| RLS | Defense-in-depth, đúng session context |
| Audit | Ghi operation metrics, không lộ secrets |
| Retry | Chỉ transient failures, có budget |
| Query plan | EXPLAIN trên data representative |
| Business goal | Authorized, bounded và available |

## Kết luận

**Giới hạn thời gian và phạm vi truy vấn do người dùng điều khiển là bài toán kết hợp bảo mật, thiết kế API và quản trị tài nguyên database.** Một endpoint an toàn không thực thi JPQL/SQL tùy ý từ client, không lấy tenant/ACL scope từ các tham số chưa xác thực, và không để người dùng chọn không giới hạn fields, joins, operators, sorting, page size hoặc thời gian dữ liệu.

Trong JPA, `setMaxResults()`, Criteria API, parameter binding, DTO projection và `jakarta.persistence.query.timeout` là những công cụ hữu ích, nhưng **mỗi công cụ giải quyết một phần khác nhau**. `setMaxResults(50)` không bảo đảm database chỉ xử lý 50 rows; Criteria API không tự kiểm tra authorization; parameter binding không giới hạn query cost; query timeout hint không phải hard deadline tuyệt đối hoặc biện pháp chống DoS duy nhất. Lock timeout, transaction timeout, DB statement timeout và HTTP deadline có phạm vi riêng và cần được thiết kế nhất quán.

Đối với dữ liệu lớn, nên ưu tiên **pagination theo khóa ổn định, DTO projection và truy vấn có index**, giới hạn filter complexity và giữ các báo cáo nặng trong một export job có quota, checkpoint, cancellation và audit. Quotas theo user/tenant và connection-pool admission controls bảo vệ tính sẵn sàng khi nhiều người truy vấn đồng thời. Mọi trang kết quả và file export phải tái áp quyền truy cập đúng cách, kể cả khi cursor đã được ký.

Phương pháp triển khai bền vững là **quy định một query policy rõ ràng tại server, bắt buộc authorization trước và trong query, áp row/time/concurrency budgets ở nhiều tầng, đo bằng query plans và production-like tests, rồi xử lý timeout/cleanup không gây sai dữ liệu**. Một truy vấn tốt không chỉ trả kết quả đúng, mà còn **chỉ trả những dữ liệu được phép, trong phạm vi chi phí mà hệ thống có thể chịu đựng một cách công bằng**.



