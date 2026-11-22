# Tái sử dụng bộ dựng query và ánh xạ DTO

Trong một ứng dụng Spring Data Elasticsearch, nhiều màn hình và service có thể cần tìm kiếm cùng một tập document nhưng với điều kiện, cách sắp xếp và dữ liệu trả về khác nhau. Nếu mỗi repository method hoặc service tự ghép query DSL và tự chuyển `SearchHit` thành response, logic tìm kiếm sẽ bị lặp lại, khó kiểm soát mapping và dễ phát sinh khác biệt giữa các API.

Một cách tổ chức tốt là tách ba trách nhiệm:

1. **Filter/criteria của ứng dụng:** mô tả người dùng muốn tìm gì bằng kiểu dữ liệu của domain, không phụ thuộc Elasticsearch DSL.
2. **Query builder/factory:** chuyển filter thành `CriteriaQuery` hoặc `NativeQuery`, áp dụng filter bắt buộc, sort và pagination theo quy tắc chung.
3. **DTO mapper:** chuyển `SearchHit`, entity hoặc aggregation result thành DTO dành cho API/UI, chỉ đưa ra những field được phép.

Các phần này có thể được tái sử dụng trong custom repository fragments. Repository chính chỉ cần ghép fragment tìm kiếm, còn implementation nhận query factory và mapper qua constructor injection.

```text
Controller / API
       |
       v
ProductSearchFilter (domain/application criteria)
       |
       v
ProductSearchFragment
       |
       +---- ProductQueryFactory
       |          |
       |          +---- CriteriaQuery / NativeQuery
       |
       +---- ElasticsearchOperations.search(...)
       |
       +---- ProductSearchMapper
                  |
                  +---- SearchHit<ProductDocument> -> ProductCardDto
       |
       v
ProductSearchResultDto
```

Tách các lớp như vậy giúp thay đổi query DSL mà không làm controller phụ thuộc vào Elasticsearch, đồng thời giữ quy tắc ánh xạ DTO nhất quán giữa nhiều repository/service.

## 1. Vì sao cần tái sử dụng query builder và DTO mapper?

Giả sử hệ thống có các use case:

- Trang danh sách sản phẩm lọc theo trạng thái, category và khoảng giá.
- Trang quản trị tìm theo tên, SKU và trạng thái.
- API gợi ý sản phẩm chỉ cần ID, tên, ảnh và giá.
- Báo cáo thống kê số sản phẩm theo category.
- Service nội bộ tìm sản phẩm tương tự theo từ khóa và điều kiện khả dụng.

Nếu mỗi use case tự xây query và map response, những quy tắc chung có thể bị sao chép:

- Tenant filter hoặc quyền truy cập document.
- Điều kiện chỉ lấy sản phẩm được phép hiển thị.
- Chuẩn hóa keyword và khoảng giá.
- Sort mặc định và giới hạn page size.
- Mapping `SearchHit` thành DTO.
- Cách hiển thị score, highlight và total hits.
- Cách xử lý field thiếu/null.

Việc lặp lại dễ tạo lỗi không đồng nhất. Ví dụ một endpoint quên thêm tenant filter, endpoint khác cho phép sort theo field không được hỗ trợ, hoặc một DTO vô tình trả toàn bộ entity chứa field nội bộ.

Tái sử dụng có ích khi nó tập trung vào quy tắc thật sự chung. Không nên tạo một framework query tổng quát quá phức tạp chỉ để tránh vài dòng code. Hãy bắt đầu từ filter, query builder và mapper có trách nhiệm rõ ràng.

## 2. Tách filter của ứng dụng khỏi Elasticsearch DSL

Controller không nên nhận `Criteria`, `NativeQuery`, `Query` hoặc JSON DSL làm request model. Đây là chi tiết hạ tầng và khiến API phụ thuộc trực tiếp vào thư viện Elasticsearch.

Thay vào đó, định nghĩa filter bằng kiểu dữ liệu domain/application:

```java
import java.math.BigDecimal;

public record ProductSearchFilter(
        String keyword,
        String status,
        String categoryId,
        BigDecimal minPrice,
        BigDecimal maxPrice
) {
}
```

Filter này mô tả ý định tìm kiếm. Nó không nói query phải dùng `match`, `term`, `range`, `bool` hay `nested`.

### 2.1. Chuẩn hóa và validate filter

Trước khi dựng query, chuẩn hóa input:

```java
import java.math.BigDecimal;

public record ProductSearchFilter(
        String keyword,
        String status,
        String categoryId,
        BigDecimal minPrice,
        BigDecimal maxPrice
) {

    public ProductSearchFilter normalized() {
        String normalizedKeyword = keyword == null || keyword.isBlank()
                ? null
                : keyword.trim();

        String normalizedStatus = status == null || status.isBlank()
                ? null
                : status.trim().toUpperCase();

        String normalizedCategory = categoryId == null || categoryId.isBlank()
                ? null
                : categoryId.trim();

        return new ProductSearchFilter(
                normalizedKeyword,
                normalizedStatus,
                normalizedCategory,
                minPrice,
                maxPrice
        );
    }

    public void validate() {
        if (minPrice != null && maxPrice != null
                && minPrice.compareTo(maxPrice) > 0) {
            throw new IllegalArgumentException(
                    "minPrice must be less than or equal to maxPrice");
        }
        if (minPrice != null && minPrice.signum() < 0) {
            throw new IllegalArgumentException("minPrice must not be negative");
        }
        if (maxPrice != null && maxPrice.signum() < 0) {
            throw new IllegalArgumentException("maxPrice must not be negative");
        }
    }
}
```

Đây là ví dụ validate ở application layer. Với ứng dụng dùng Bean Validation, có thể khai báo constraint riêng cho khoảng giá và kiểm tra ở controller/service. Không nên để query builder phải đoán cách xử lý input sai.

### 2.2. Dùng enum cho giá trị có tập hữu hạn

Nếu trạng thái chỉ có vài giá trị, dùng enum thay vì nhận string tùy ý:

```java
public enum ProductStatus {
    ACTIVE,
    INACTIVE,
    DISCONTINUED
}
```

Filter có thể dùng `ProductStatus status`. Query factory chuyển enum sang giá trị lưu trong index. Điều này giảm lỗi chính tả và làm rõ contract của API.

### 2.3. Filter không đồng nghĩa với quyền truy cập

Một số điều kiện phải được áp dụng từ security context, ví dụ tenant ID hoặc phạm vi dữ liệu người dùng được phép xem. Không nên tin `tenantId` do client gửi nếu đó là ranh giới bảo mật.

Có thể tách filter người dùng và context bảo mật:

```java
public record SearchScope(String tenantId, boolean includeArchived) {
}
```

Service lấy `SearchScope` từ authentication/authorization layer rồi truyền vào query factory. Query builder phải luôn thêm tenant filter bắt buộc, kể cả khi filter tìm kiếm không có điều kiện nào.

## 3. Thiết kế query factory có thể tái sử dụng

Một query factory nhận filter và trả về Spring Data `Query`. Controller và service không cần biết DSL cụ thể.

```java
import org.springframework.data.elasticsearch.core.query.Query;

public interface ProductQueryFactory {
    Query build(ProductSearchFilter filter, SearchScope scope);
}
```

Implementation có thể dùng `CriteriaQuery`:

```java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public class CriteriaProductQueryFactory implements ProductQueryFactory {

    @Override
    public Query build(ProductSearchFilter rawFilter, SearchScope scope) {
        ProductSearchFilter filter = rawFilter.normalized();
        filter.validate();

        Criteria criteria = new Criteria("tenant_id").is(scope.tenantId());

        if (filter.status() != null) {
            criteria = criteria.and("status").is(filter.status());
        }

        if (filter.categoryId() != null) {
            criteria = criteria.and("category_id").is(filter.categoryId());
        }

        if (filter.keyword() != null) {
            criteria = criteria.and("name").matches(filter.keyword());
        }

        if (filter.minPrice() != null) {
            criteria = criteria.and("price").greaterThanEqual(filter.minPrice());
        }

        if (filter.maxPrice() != null) {
            criteria = criteria.and("price").lessThanEqual(filter.maxPrice());
        }

        return new CriteriaQuery(criteria);
    }
}
```

Các field trong ví dụ là property của entity. Spring Data mapping chuyển property sang tên field Elasticsearch theo metadata `@Field`. Nếu query được tạo bằng raw Elasticsearch Java API DSL, thường phải dùng tên field trong index chính xác.

`Criteria` API và method có sẵn có thể khác giữa các phiên bản Spring Data Elasticsearch. Hãy dùng API đúng với dependency của dự án; mục tiêu kiến trúc là giữ logic tạo điều kiện ở một nơi, không buộc mọi use case phải dùng một DSL duy nhất.

### 3.1. Áp dụng pagination và sort

Có thể truyền `Pageable` từ service vào query factory hoặc áp dụng ở repository fragment. Một phiên bản interface mở rộng:

```java
public interface ProductQueryFactory {
    Query build(ProductSearchFilter filter, SearchScope scope, Pageable pageable);
}
```

Implementation:

```java
@Override
public Query build(
        ProductSearchFilter rawFilter,
        SearchScope scope,
        Pageable pageable) {

    Criteria criteria = buildCriteria(rawFilter, scope);
    CriteriaQuery query = new CriteriaQuery(criteria);
    query.setPageable(pageable);
    return query;
}
```

`setPageable` áp dụng page, size và sort vào query. Nếu version đang dùng có builder API khác, có thể tạo `CriteriaQuery` rồi cấu hình pageable bằng API tương ứng.

### 3.2. Whitelist sort field

Không chuyển trực tiếp tên sort field tùy ý từ request vào Elasticsearch. Dùng allowlist:

```java
public enum ProductSortField {
    NAME("name"),
    PRICE("price"),
    CREATED_AT("createdAt");

    private final String property;

    ProductSortField(String property) {
        this.property = property;
    }

    public String property() {
        return property;
    }
}
```

Service chuyển lựa chọn đã validate thành `Sort`:

```java
Sort sort = Sort.by(Sort.Direction.DESC, ProductSortField.PRICE.property());
Pageable pageable = PageRequest.of(page, size, sort);
```

Giới hạn page size tối đa và chỉ cho sort theo field có mapping phù hợp. Sort trên field `text` thường cần keyword subfield; sort trên numeric/date cần mapping đúng kiểu.

## 4. Tái sử dụng các mảnh điều kiện query

Khi nhiều query dùng chung một số điều kiện, có thể tách helper nhỏ:

```java
private Criteria addStatus(Criteria criteria, ProductStatus status) {
    return status == null
            ? criteria
            : criteria.and("status").is(status.name());
}

private Criteria addTenant(Criteria criteria, String tenantId) {
    return criteria.and("tenant_id").is(tenantId);
}

private Criteria addPriceRange(
        Criteria criteria,
        BigDecimal min,
        BigDecimal max) {

    if (min != null) {
        criteria = criteria.and("price").greaterThanEqual(min);
    }
    if (max != null) {
        criteria = criteria.and("price").lessThanEqual(max);
    }
    return criteria;
}
```

Query factory gọi các helper theo thứ tự. Hãy chỉ tách helper khi điều kiện có ý nghĩa riêng hoặc được tái sử dụng thật sự. Tránh tạo một method chung kiểu `addAnyFieldOperator(String field, String operator, Object value)` nếu nó khiến query khó đọc và cho phép field/operator tùy ý.

### 4.1. Tái sử dụng filter bắt buộc

Tenant filter, visibility filter hoặc soft-delete filter thường phải xuất hiện trong mọi query thuộc một phạm vi dữ liệu. Đưa chúng vào query factory hoặc một lớp policy dùng chung để giảm nguy cơ một endpoint quên áp dụng.

Ví dụ:

```java
private Criteria baseCriteria(SearchScope scope) {
    return new Criteria("tenant_id").is(scope.tenantId())
            .and("deleted").is(false);
}
```

Filter bảo mật phải được áp dụng cả với query không có keyword/status/price. Không để trường hợp filter trống vô tình tạo match-all query trên toàn bộ tenant.

### 4.2. Tránh tái sử dụng object query mutable

Không tạo một `Criteria`, `CriteriaQuery` hoặc `NativeQuery` mutable làm singleton rồi sửa nó cho từng request. Nếu hai request chạy đồng thời, điều kiện có thể rò sang nhau hoặc query bị thay đổi trong lúc đang thực thi.

Tạo object mới cho mỗi lần gọi factory. Chỉ tái sử dụng cấu hình bất biến như whitelist, field mapping constants hoặc helper thuần.

## 5. Dùng `NativeQuery` khi query phức tạp

`CriteriaQuery` phù hợp với điều kiện thông thường. Khi cần `nested`, `geo_distance`, `function_score`, `script`, aggregation hoặc query DSL đặc thù, có thể viết factory trả về `NativeQuery`.

Một abstraction có thể vẫn trả `Query`:

```java
public interface ProductQueryFactory {
    Query build(ProductSearchFilter filter, SearchScope scope, Pageable pageable);
}
```

Implementation `NativeQuery` dùng Elasticsearch Java API Client:

Ví dụ rõ ràng hơn:

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

public org.springframework.data.elasticsearch.core.query.Query buildNative(
        ProductSearchFilter filter,
        SearchScope scope,
        Pageable pageable) {

    List<Query> filters = new ArrayList<>();

    filters.add(Query.of(q -> q
            .term(t -> t
                    .field("tenant_id")
                    .value(FieldValue.of(scope.tenantId()))
            )
    ));

    if (filter.status() != null) {
        filters.add(Query.of(q -> q
                .term(t -> t
                        .field("status")
                        .value(FieldValue.of(filter.status()))
                )
        ));
    }

    Query boolQuery = Query.of(q -> q
            .bool(b -> b.filter(filters))
    );

    return NativeQuery.builder()
            .withQuery(boolQuery)
            .withPageable(pageable)
            .build();
}
```

Đây là ví dụ query động tối giản. Các builder method của Java API Client phụ thuộc version; với `range` query, kiểu value và generated DSL có thể khác giữa các bản client. Giữ import rõ ràng vì cả Elasticsearch Java API Client và Spring Data đều có kiểu tên `Query`.

### 5.1. Chọn CriteriaQuery hay NativeQuery

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Exact filter, range, điều kiện AND/OR đơn giản | `CriteriaQuery`. |
| Query thay đổi theo nhiều filter tùy chọn | Query factory với `CriteriaQuery` hoặc `NativeQuery`. |
| Nested query phức tạp | `NativeQuery`. |
| Geo distance / function score / script | `NativeQuery`. |
| Aggregation phức tạp | `NativeQuery`. |
| Query tĩnh ngắn gắn với một repository method | `@Query`. |
| Điều kiện phổ biến diễn đạt tốt bằng tên method | Derived query. |

Không cần ép mọi query về một API. Có thể có nhiều factory chuyên biệt cùng triển khai một interface nếu response contract giống nhau.

## 6. Repository fragment sử dụng query factory

Để tái sử dụng builder trong repository tùy biến, khai báo fragment:

```java
public interface ProductSearchFragment {
    ProductSearchResult search(
            ProductSearchFilter filter,
            SearchScope scope,
            Pageable pageable);
}
```

Repository chính ghép fragment:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchFragment {
}
```

Implementation theo quy ước tên fragment:

```java
public class ProductSearchFragmentImpl implements ProductSearchFragment {

    private final ElasticsearchOperations operations;
    private final ProductQueryFactory queryFactory;
    private final ProductSearchMapper mapper;

    public ProductSearchFragmentImpl(
            ElasticsearchOperations operations,
            ProductQueryFactory queryFactory,
            ProductSearchMapper mapper) {
        this.operations = operations;
        this.queryFactory = queryFactory;
        this.mapper = mapper;
    }

    @Override
    public ProductSearchResult search(
            ProductSearchFilter filter,
            SearchScope scope,
            Pageable pageable) {

        Query query = queryFactory.build(filter, scope, pageable);
        SearchHits<ProductDocument> hits =
                operations.search(query, ProductDocument.class);

        List<ProductCardDto> content = hits.getSearchHits().stream()
                .map(mapper::toCard)
                .toList();

        return new ProductSearchResult(
                content,
                hits.getTotalHits(),
                hits.getTotalHitsRelation().name(),
                pageable.getPageNumber(),
                pageable.getPageSize()
        );
    }
}
```

Tên `ProductSearchFragmentImpl` theo mặc định là tên interface fragment cộng `Impl`. Nếu dự án cấu hình repository implementation postfix khác, tên class phải theo postfix đó.

`ElasticsearchOperations.search` trả về `SearchHits<T>`, giữ cả entity và metadata của từng hit. Mapper có thể sử dụng metadata này trước khi trả DTO.

## 7. Thiết kế DTO dành cho kết quả tìm kiếm

Không nên trả trực tiếp Elasticsearch entity ra API nếu entity chứa field nội bộ hoặc mapping-specific metadata.

Ví dụ DTO cho card sản phẩm:

```java
import java.math.BigDecimal;
import java.util.List;

public record ProductCardDto(
        String id,
        String name,
        BigDecimal price,
        String status,
        Float score,
        List<String> highlights
) {
}
```

DTO tổng hợp kết quả:

```java
import java.util.List;

public record ProductSearchResult(
        List<ProductCardDto> items,
        long totalHits,
        String totalHitsRelation,
        int page,
        int size
) {
}
```

`totalHitsRelation` cho biết total hit là chính xác hay chỉ là cận dưới theo semantics Elasticsearch. Nếu API chỉ trả `totalHits` mà bỏ relation, client có thể hiểu nhầm số lượng là chính xác trong mọi trường hợp.

Nếu contract API không cần score hoặc highlight, bỏ chúng khỏi DTO. Không đưa metadata Elasticsearch ra ngoài chỉ vì `SearchHit` cung cấp sẵn.

## 8. Ánh xạ `SearchHit<T>` sang DTO

Spring Data Elasticsearch có các kiểu kết quả:

- `SearchHit<T>`: một hit, gồm content và metadata như ID, score, sort values, highlight fields.
- `SearchHits<T>`: tập hit và metadata tổng thể như total hits, relation, aggregations.
- `SearchPage<T>`: abstraction phân trang dựa trên search hits trong các API hỗ trợ.

Nếu chỉ dùng `SearchHits<T>.getSearchHits()`, mapper nhận từng `SearchHit<ProductDocument>`.

```java
import org.springframework.data.elasticsearch.core.SearchHit;

public interface ProductSearchMapper {
    ProductCardDto toCard(SearchHit<ProductDocument> hit);
}
```

Implementation thủ công:

```java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.elasticsearch.core.SearchHit;

public class ProductSearchMapperImpl implements ProductSearchMapper {

    @Override
    public ProductCardDto toCard(SearchHit<ProductDocument> hit) {
        ProductDocument document = hit.getContent();

        List<String> highlights = hit.getHighlightFields()
                .getOrDefault("name", List.of());

        return new ProductCardDto(
                hit.getId(),
                document.getName(),
                BigDecimal.valueOf(document.getPrice()),
                document.getStatus(),
                hit.getScore(),
                List.copyOf(highlights)
        );
    }
}
```

Ví dụ giả định `price` trong entity là `double`. Với tiền tệ, nên cân nhắc lưu bằng đơn vị nhỏ nhất (ví dụ cents) hoặc `scaled_float` với quy tắc scale rõ ràng để tránh sai số floating point. Nếu entity dùng `BigDecimal`, mapper nên chuyển trực tiếp theo chính sách precision/scale đã định nghĩa.

### 8.1. Vì sao nhận `SearchHit` thay vì chỉ nhận entity?

Nếu mapper chỉ nhận `ProductDocument`, nó không thể lấy score, highlight hoặc sort values. Nhận `SearchHit<ProductDocument>` cho phép DTO có chọn lọc metadata của search.

Ngược lại, với use case chỉ cần entity content, có thể dùng method mapper đơn giản:

```java
ProductCardDto toCard(ProductDocument document);
```

Không bắt mapper phụ thuộc `SearchHit` nếu DTO không cần metadata đó. Chọn abstraction nhỏ nhất phù hợp với response.

### 8.2. Không trả raw highlight tùy tiện

Highlight fragment có thể chứa HTML tag do Elasticsearch highlight configuration. Nếu API/UI hiển thị trực tiếp, cần xác định cách render an toàn và escape nội dung. Không xem highlight string là HTML tin cậy.

Chỉ lấy các highlight field được phép, ví dụ `name`. Không trả tất cả `getHighlightFields()` nếu query có thể highlight field nội bộ.

## 9. Tách mapper theo loại response

Một entity có thể có nhiều DTO:

```text
ProductDocument
    |
    +---- ProductCardDto       (danh sách/tìm kiếm)
    |
    +---- ProductDetailDto     (trang chi tiết)
    |
    +---- ProductAdminDto      (quản trị)
    |
    +---- ProductExportRow     (xuất dữ liệu)
```

Không nên dùng một DTO lớn có mọi field rồi để từng endpoint tự bỏ field. Tạo DTO theo use case giúp xác định dữ liệu được phép lộ và giảm coupling giữa index schema với API contract.

Ví dụ:

```java
public record ProductDetailDto(
        String id,
        String sku,
        String name,
        String description,
        BigDecimal price,
        String status
) {
}

public record ProductAdminDto(
        String id,
        String sku,
        String name,
        String status,
        String internalReviewState
) {
}
```

Mapper có thể dùng MapStruct cho mapping entity-to-DTO thông thường. Tuy nhiên, việc map `SearchHit` metadata, highlight và aggregation thường cần method custom rõ ràng.

## 10. Ánh xạ `SearchHits` sang page response

Một cách đơn giản là map danh sách hit và giữ metadata pagination:

```java
public ProductSearchResult toResult(
        SearchHits<ProductDocument> hits,
        Pageable pageable) {

    List<ProductCardDto> items = hits.getSearchHits().stream()
            .map(this::toCard)
            .toList();

    return new ProductSearchResult(
            items,
            hits.getTotalHits(),
            hits.getTotalHitsRelation().name(),
            pageable.getPageNumber(),
            pageable.getPageSize()
    );
}
```

Nếu dùng Spring Data `Page<T>`, có thể chuyển `SearchHits` thành page response theo API của phiên bản đang dùng hoặc tự tạo `PageImpl` khi total hits chính xác. Với Elasticsearch, total hits có thể là `GREATER_THAN_OR_EQUAL_TO` nếu query không yêu cầu đếm chính xác toàn bộ; vì vậy cần giữ relation hoặc thiết kế response không giả định total là exact.

### 10.1. Không nhầm `totalHits` với số item trong trang

`hits.getSearchHits().size()` là số phần tử trong trang hiện tại. `hits.getTotalHits()` là số hit tổng thể theo total-hit tracking của request. Hai số này khác nhau khi có pagination.

Nếu query chỉ yêu cầu tối đa một số lượng hit hoặc total-hit tracking bị giới hạn, không được diễn giải total hits như con số tuyệt đối chính xác nếu relation báo cận dưới.

### 10.2. Giới hạn page size

API nên áp dụng page size tối đa:

```java
int safeSize = Math.min(Math.max(requestedSize, 1), 100);
Pageable pageable = PageRequest.of(page, safeSize, sort);
```

Giới hạn này giúp tránh request vô tình tải hàng chục nghìn document và map toàn bộ vào heap. Với tập dữ liệu lớn, cân nhắc `search_after`/PIT thay vì page number sâu.

## 11. DTO cho cursor pagination và `search_after`

Offset pagination phù hợp với tập kết quả vừa phải. Với dữ liệu lớn hoặc page sâu, Elasticsearch thường phù hợp hơn với `search_after` kết hợp Point in Time (PIT) để duyệt kết quả ổn định.

Một response cursor có thể gồm:

```java
public record ProductCursorPage(
        List<ProductCardDto> items,
        String nextCursor,
        boolean hasMore
) {
}
```

Cursor nên là token opaque do server tạo, chứa hoặc tham chiếu đến sort values và PIT context theo cách được bảo vệ. Không để client tự sửa sort values tùy ý hoặc truyền một cursor có thể trỏ sang tenant khác.

Luồng khái quát:

1. Mở PIT cho index/alias phù hợp.
2. Chạy query với sort ổn định và tie-breaker duy nhất.
3. Lấy sort values của hit cuối cùng.
4. Tạo cursor chứa PIT ID và sort values đã ký/mã hóa hoặc lưu server-side.
5. Request tiếp theo dùng cursor để gọi `search_after`.
6. Đóng PIT khi hoàn tất hoặc khi hết thời hạn.

`SearchHit` có metadata sort values ở các API tương ứng. Cách cấu hình PIT và `search_after` trong Spring Data/Java API Client phụ thuộc version; hãy đóng gói phần này trong một cursor query adapter riêng thay vì để controller tự tạo DSL.

### 11.1. Sort cần ổn định

Nếu sort chỉ theo `price`, nhiều document có thể cùng giá và thứ tự giữa các trang không ổn định. Thêm tie-breaker duy nhất như `_id` hoặc một field sortable duy nhất phù hợp với API/version. PIT giữ góc nhìn dữ liệu nhất quán trong quá trình phân trang, nhưng không tự sửa một sort không xác định.

### 11.2. Cursor phải gắn với scope truy vấn

Cursor cần ràng buộc với:

- Tenant/security scope.
- Filter đã chuẩn hóa.
- Sort order.
- PIT ID/expiry.
- Phiên bản cấu trúc cursor.

Nếu client gửi cursor của một filter khác hoặc tenant khác, server phải từ chối hoặc tạo query mới theo chính sách. Không cho cursor trở thành cách vượt qua authorization filter.

## 12. DTO cho aggregation result

Aggregation không nhất thiết trả về một `ProductDocument` cho mỗi kết quả. Ví dụ dashboard cần số sản phẩm theo category:

```java
public record CategoryCountDto(
        String categoryId,
        long productCount
) {
}

public record ProductCategorySummaryDto(
        List<CategoryCountDto> categories
) {
}
```

Tách mapper aggregation khỏi mapper document:

```text
SearchHits<ProductDocument>
       -> ProductSearchMapper
       -> ProductCardDto

SearchHits aggregations
       -> ProductAggregationMapper
       -> CategoryCountDto
```

Spring Data Elasticsearch bọc aggregation response trong abstraction phụ thuộc version, thường có `AggregationsContainer<?>` trên `SearchHits`. Khi cần truy cập kiểu aggregation cụ thể, adapter có thể lấy native response/aggregation container rồi chuyển thành DTO. Chi tiết accessor và bucket type thay đổi giữa các phiên bản, nên giữ phần chuyển đổi đó ở một lớp riêng và kiểm tra với đúng API version.

Không đưa toàn bộ Elasticsearch aggregation response vào API contract. Chỉ map bucket key, count và metric mà client thực sự cần.

## 13. Dùng MapStruct hay mapper thủ công?

MapStruct phù hợp với mapping thuần giữa Java bean/record có field tương ứng:

```java
@Mapper(componentModel = "spring")
public interface ProductDocumentMapper {
    ProductDetailDto toDetail(ProductDocument document);
}
```

Ưu điểm:

- Mapping được sinh lúc compile time.
- Phát hiện nhiều lỗi tên/kiểu field sớm.
- Có thể dùng chung mapper cho nhiều service.
- Không cần reflection runtime cho mapping cơ bản.

Mapper thủ công phù hợp khi:

- Cần đọc `SearchHit` score/highlight/sort values.
- Cần xử lý null/default phức tạp.
- Cần tính toán giá trị tổng hợp.
- Cần che hoặc loại field theo security context.
- Cần chuyển aggregation response phụ thuộc client version.

Có thể kết hợp: MapStruct map `ProductDocument` sang DTO cơ bản, còn adapter nhận `SearchHit` gắn metadata bổ sung. Không ép MapStruct xử lý các object Elasticsearch phức tạp nếu method custom dễ hiểu hơn.

## 14. Tái sử dụng mapper mà không làm lộ field nội bộ

Entity Elasticsearch có thể chứa field chỉ dùng nội bộ:

```java
@Document(indexName = "products")
public class ProductDocument {
    @Id
    private String id;
    private String name;
    private String status;
    private String internalModerationNote;
    private String sourceSystem;
}
```

Không dùng entity làm response trực tiếp. Tạo DTO allowlist:

```java
public record ProductPublicDto(
        String id,
        String name,
        String status
) {
}
```

Mapper chỉ đưa ba field được phép. Nếu admin được xem thêm thông tin, dùng DTO riêng và authorization riêng.

Tái sử dụng mapper không có nghĩa mọi endpoint phải trả cùng một DTO. Tái sử dụng mapping component nhỏ và policy, nhưng giữ response model theo đúng use case.

## 15. Ánh xạ field thiếu, null và giá trị mặc định

Elasticsearch document cũ có thể không có field mới sau khi schema tiến hóa. Mapper cần xác định cách xử lý:

- Giữ `null` để client biết dữ liệu không có.
- Dùng default nếu domain xác định default đó đúng.
- Dùng optional field trong DTO.
- Gắn schema/projection version nếu cần phân biệt document cũ và mới.

Không tự động biến mọi null thành `0`, `false` hoặc chuỗi rỗng. Ví dụ `price = 0` có thể mang ý nghĩa khác với “chưa có giá”.

Ví dụ mapper rõ ràng:

```java
String displayName = document.getName() == null
        ? "Unnamed product"
        : document.getName();
```

Chỉ dùng default hiển thị nếu nghiệp vụ chấp nhận. Không ghi default vào index chỉ để che lỗi dữ liệu khi chưa xác định nguồn gốc missing field.

## 16. Reuse query builder qua nhiều repository fragment

Một query factory có thể được inject vào nhiều fragment nếu cùng entity/index semantics:

```text
ProductRepository
   +-- ProductSearchFragmentImpl
   |       +-- ProductQueryFactory
   |       +-- ProductSearchMapper
   |
   +-- ProductAdminFragmentImpl
           +-- ProductAdminQueryFactory
           +-- ProductAdminMapper
```

Không nên dùng chung một factory cho các query có policy khác nhau nếu điều kiện bảo mật khác nhau. Ví dụ public search và admin search có thể có scope khác; hãy thể hiện rõ trong type hoặc method để tránh vô tình bỏ filter.

Nếu hai repository dùng chung fragment nhưng khác entity, có thể tạo abstraction generic hoặc composition nhỏ. Chỉ làm generic khi mapping/query contract thật sự giống nhau; nếu không, hai factory chuyên biệt thường dễ hiểu và an toàn hơn.

## 17. Tái sử dụng query builder trong nhiều use case

Ví dụ public search và admin search dùng chung một số điều kiện:

```java
public class ProductQueryFactory {

    public Query buildPublicSearch(
            ProductSearchFilter filter,
            SearchScope scope,
            Pageable pageable) {
        Criteria criteria = baseVisibleCriteria(scope);
        criteria = addCommonFilters(criteria, filter);
        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(pageable);
        return query;
    }

    public Query buildAdminSearch(
            ProductSearchFilter filter,
            SearchScope scope,
            Pageable pageable) {
        Criteria criteria = baseTenantCriteria(scope);
        criteria = addCommonFilters(criteria, filter);
        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(pageable);
        return query;
    }

    private Criteria baseVisibleCriteria(SearchScope scope) {
        return new Criteria("tenant_id").is(scope.tenantId())
                .and("visible").is(true)
                .and("deleted").is(false);
    }

    private Criteria baseTenantCriteria(SearchScope scope) {
        return new Criteria("tenant_id").is(scope.tenantId())
                .and("deleted").is(false);
    }

    private Criteria addCommonFilters(
            Criteria criteria,
            ProductSearchFilter filter) {
        // Add validated status/category/price/keyword filters.
        return criteria;
    }
}
```

Ví dụ này cho thấy reuse phần filter chung nhưng vẫn giữ hai base policy khác nhau. Trong code thật, nên truyền scope/permission rõ ràng và test để public query không trả document ẩn.

## 18. Kiểm thử query factory bằng unit test

Query factory có thể được unit test ở mức logic đầu vào:

- Keyword rỗng có bị bỏ qua không?
- Status được chuẩn hóa không?
- Khoảng giá min/max sai có bị từ chối không?
- Tenant scope có bắt buộc không?
- Sort field không nằm trong allowlist có bị từ chối không?
- Page size có bị giới hạn không?

Ví dụ kiểm tra filter validation:

```java
@Test
void rejectsInvalidPriceRange() {
    ProductSearchFilter filter = new ProductSearchFilter(
            null,
            "ACTIVE",
            null,
            new BigDecimal("200"),
            new BigDecimal("100")
    );

    assertThatThrownBy(filter::validate)
            .isInstanceOf(IllegalArgumentException.class);
}
```

Đối với query object, không nên chỉ so sánh `toString()` vì format nội bộ có thể thay đổi. Có thể kiểm tra builder branch qua method nhỏ hoặc kiểm tra query execution bằng integration test.

## 19. Kiểm thử mapper độc lập

Mapper thuần có thể được unit test mà không cần Elasticsearch:

```java
@Test
void mapsSearchHitContentAndMetadata() {
    ProductDocument document = new ProductDocument(
            "P-100", "Mechanical Keyboard", "ACTIVE", 250.0
    );

    SearchHit<ProductDocument> hit = createSearchHitFixture(
            document,
            1.25f,
            Map.of("name", List.of("Mechanical <em>Keyboard</em>"))
    );

    ProductCardDto dto = mapper.toCard(hit);

    assertThat(dto.id()).isEqualTo("P-100");
    assertThat(dto.name()).isEqualTo("Mechanical Keyboard");
    assertThat(dto.score()).isEqualTo(1.25f);
    assertThat(dto.highlights()).containsExactly("Mechanical <em>Keyboard</em>");
}
```

`createSearchHitFixture` là helper test cần tạo `SearchHit` theo constructor/builder có trong Spring Data version của dự án. Vì các constructor nội bộ có thể thay đổi, có thể test mapper bằng một adapter interface nhỏ hoặc integration test tạo SearchHit thật nếu việc dựng fixture quá phức tạp.

Những trường hợp nên test:

- Field null/missing.
- Highlight không có.
- Score có/không có theo loại query.
- Sort values rỗng.
- Field nội bộ không xuất hiện trong DTO.
- Giá tiền giữ precision theo quy tắc.
- DTO public và admin không lẫn field.

## 20. Kiểm thử query factory và mapper qua repository integration test

Unit test factory/mapper không chứng minh query hoạt động với Elasticsearch mapping. Nên có integration test cho một số luồng tiêu biểu:

1. Tạo index bằng mapping production hoặc mapping test tương đương.
2. Index dữ liệu đại diện.
3. Refresh index.
4. Gọi repository fragment với filter và scope.
5. Xác minh đúng document được chọn.
6. Xác minh DTO chỉ có field cần thiết, score/highlight nếu có.
7. Kiểm tra pagination/sort/total-hit relation.
8. Kiểm tra tenant filter không thể bị bỏ qua.

Testcontainers có thể cung cấp Elasticsearch thật với version pin. Không dùng mock `ElasticsearchOperations` để kết luận `CriteriaQuery`/`NativeQuery` có semantics đúng.

## 21. Tách DTO cho aggregation và suggest

Không phải kết quả search nào cũng là danh sách entity. Một API autocomplete có thể chỉ cần:

```java
public record ProductSuggestionDto(
        String id,
        String label
) {
}
```

Một API dashboard có thể cần:

```java
public record PriceStatsDto(
        BigDecimal minimum,
        BigDecimal maximum,
        BigDecimal average,
        long count
) {
}
```

Đặt mapper theo loại kết quả giúp không phụ thuộc vào một DTO lớn. Aggregation mapper có thể chuyển bucket/metric từ Elasticsearch response sang domain number/DTO, còn document mapper chuyển `SearchHit<T>`.

Nếu response aggregation phụ thuộc Java API Client version, hãy tạo adapter chuyển từ native aggregation container sang model nội bộ ổn định trước khi map ra API DTO.

## 22. Hiệu năng: source filtering và chỉ map dữ liệu cần thiết

Nếu danh sách chỉ cần `id`, `name`, `price`, không nhất thiết tải toàn bộ `_source` chứa mô tả dài, internal metadata hoặc mảng lớn.

Có thể dùng source filtering/includes/excludes ở query để giảm payload. API cụ thể phụ thuộc `Query`/`NativeQuery` version, nhưng ý tưởng là chỉ lấy field cần cho DTO.

Tuy nhiên, source filtering không thay thế DTO allowlist. Một field có thể được trả về từ Elasticsearch nhưng mapper không đưa vào response; ngược lại, nếu field bị loại khỏi source mà mapper cần, DTO sẽ thiếu dữ liệu.

Tối ưu theo thứ tự:

1. Xác định field DTO thực sự cần.
2. Chọn mapping và query phù hợp.
3. Giới hạn `_source` nếu payload lớn.
4. Map ngay trong stream kết quả thay vì giữ cả hai collection entity và DTO nếu không cần.
5. Giới hạn page size hoặc dùng cursor pagination.

## 23. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Controller phụ thuộc `CriteriaQuery`/`NativeQuery` | Query DSL được tạo ngay ở web layer. | Dùng filter DTO và query factory trong repository/application layer. |
| Mỗi service tạo query khác nhau cho cùng filter | Logic query bị lặp. | Tách query factory hoặc fragment dùng chung. |
| Query bị rò tenant filter | Điều kiện bảo mật được thêm thủ công từng endpoint. | Đưa mandatory scope vào factory/policy và test bắt buộc. |
| Request sort được field bất kỳ | Chuyển string client trực tiếp thành sort. | Whitelist sort property và direction. |
| Query của request này ảnh hưởng request khác | Tái sử dụng Criteria/Query mutable singleton. | Tạo query object mới cho mỗi lần build. |
| DTO trả field nội bộ | Trả trực tiếp entity hoặc mapper copy toàn bộ field. | DTO allowlist theo use case. |
| Mất score/highlight | Mapper chỉ nhận entity content. | Nhận `SearchHit<T>` khi cần metadata. |
| Total count bị hiểu sai | Bỏ qua total hits relation. | Giữ relation hoặc dùng response contract biểu diễn approximate total. |
| Giá tiền sai số | Map từ `double` sang `BigDecimal` tùy tiện. | Dùng scaled integer/`scaled_float` hoặc BigDecimal policy rõ ràng. |
| Highlight gây lỗi hiển thị | Xem highlight string là HTML tin cậy. | Escape/render an toàn ở client hoặc sanitize theo policy. |
| Query builder generic quá mức | Abstraction nhận field/operator tùy ý. | Tạo factory theo use case và helper nhỏ có kiểu rõ ràng. |
| Test builder pass nhưng query sai | Chỉ unit test object creation. | Thêm integration test trên Elasticsearch thật. |
| DTO/mapper phụ thuộc version client | Map native aggregation response trực tiếp ở nhiều nơi. | Tạo adapter chuyển về model nội bộ ổn định. |

## 24. Quy trình xây dựng query factory và DTO mapper

1. **Xác định use case:** liệt kê filter, scope, sort, pagination và dữ liệu response.
2. **Tạo filter model:** dùng kiểu domain/application, validate và normalize input.
3. **Tách security scope:** lấy tenant/permission từ context đáng tin cậy, không nhận tùy ý từ client.
4. **Tạo query factory:** chuyển filter thành `CriteriaQuery` hoặc `NativeQuery` và thêm mandatory filter.
5. **Giới hạn sort/page:** whitelist field, giới hạn page size và chọn offset/cursor phù hợp.
6. **Tạo DTO theo use case:** public card, detail, admin, suggestion hoặc aggregation.
7. **Tạo mapper:** map entity hoặc `SearchHit` metadata sang DTO theo allowlist.
8. **Ghép vào repository fragment:** inject factory, `ElasticsearchOperations` và mapper.
9. **Unit test:** kiểm tra validation, filter normalization, query factory branches và mapper.
10. **Integration test:** chạy query trên Elasticsearch thật với mapping và dữ liệu đại diện.
11. **Đánh giá hiệu năng:** source filtering, page size, total hits, highlight và cursor pagination.

## 25. Những điểm cần nhớ

- Filter của ứng dụng nên độc lập với Elasticsearch DSL.
- Query factory chuyển filter thành `CriteriaQuery` hoặc `NativeQuery` và tập trung quy tắc query dùng chung.
- Tenant/authorization filter phải được lấy từ security context đáng tin cậy và luôn áp dụng.
- Tạo query object mới cho mỗi request; không chia sẻ object mutable giữa các thread.
- Dùng whitelist cho sort field và giới hạn page size.
- Repository fragment có thể inject query factory và mapper để tái sử dụng trong nhiều use case.
- `SearchHit<T>` giữ entity content cùng score, highlight và metadata; `SearchHits<T>` giữ kết quả tổng thể.
- Mapper nên trả DTO allowlist, không trả entity Elasticsearch trực tiếp ra API.
- Tách DTO theo use case như card, detail, admin, suggestion và aggregation.
- Giữ `totalHitsRelation` nếu total hit có thể chỉ là cận dưới.
- Với dữ liệu lớn, cân nhắc PIT + `search_after` và cursor opaque gắn với filter/scope.
- MapStruct phù hợp mapping bean cơ bản; mapper thủ công phù hợp SearchHit metadata và aggregation.
- Unit test kiểm tra logic builder/mapper; integration test xác minh query và mapping trên Elasticsearch thật.
- Source filtering giúp giảm payload nhưng không thay thế DTO allowlist.

Tái sử dụng bộ dựng query và ánh xạ DTO giúp repository tùy biến có một nơi thống nhất để diễn đạt filter, bảo vệ scope dữ liệu và chuyển kết quả Elasticsearch thành response ổn định. Giữ filter độc lập với DSL, tạo query mới cho từng request, map qua DTO allowlist và kiểm thử cả logic thuần lẫn hành vi trên Elasticsearch thật sẽ giúp code dễ mở rộng mà không làm lộ chi tiết hạ tầng ra API.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch — Elasticsearch Operations and Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — SearchHit API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/SearchHit.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Commons — Repository Composition](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch — Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
