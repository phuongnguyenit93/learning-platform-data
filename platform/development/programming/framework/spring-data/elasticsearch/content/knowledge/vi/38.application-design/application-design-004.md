# DTO yêu cầu, DTO phản hồi và hợp đồng metadata

Một API tìm kiếm dùng Spring Data Elasticsearch thường có nhiều thông tin hơn một danh sách entity. Request có thể chứa từ khóa, bộ lọc, phạm vi giá, thứ tự sắp xếp và phân trang. Response có thể cần trả sản phẩm, điểm relevance, highlight, tổng số kết quả, facet, thời gian tìm kiếm hoặc cursor cho trang tiếp theo.

Nếu controller trả thẳng entity Elasticsearch hoặc đối tượng SearchHit/SearchHits, hợp đồng HTTP sẽ phụ thuộc trực tiếp vào mapping và API nội bộ của Spring Data. Khi entity thay đổi để phục vụ index, response API cũng có thể thay đổi ngoài ý muốn. DTO yêu cầu, DTO phản hồi và một hợp đồng metadata rõ ràng giúp tách giao diện HTTP khỏi mô hình lưu trữ, đồng thời kiểm soát chính xác thông tin tìm kiếm được công bố.

Bài học này trình bày cách thiết kế DTO cho search API, chuyển request thành query nội bộ, chuyển SearchHit thành response model, định nghĩa metadata phân trang và relevance, xử lý highlight/facet/cursor, quản lý tương thích hợp đồng và kiểm thử API.

## 1. Tại sao cần DTO ở ranh giới API?

Entity Elasticsearch mô tả cách dữ liệu được lưu và mapping trong index. DTO mô tả dữ liệu mà client được phép gửi hoặc nhận qua API. Hai mô hình có thể giống nhau ở một vài field, nhưng chúng có mục đích khác nhau.

Ví dụ entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String internalSupplierCode;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // getters and setters
}
~~~

Entity có thể chứa tenantId để lọc dữ liệu, internalSupplierCode để xử lý nội bộ, metadata mapping và field chỉ phục vụ index. Không phải tất cả field này đều nên xuất hiện trong response.

Nếu controller trả trực tiếp Product, một thay đổi mapping như thêm field nội bộ có thể vô tình làm lộ field đó qua JSON serialization. Ngoài ra, client có thể bắt đầu phụ thuộc vào cấu trúc entity và khiến việc thay đổi index trở nên khó khăn.

Nên giữ ba lớp rõ ràng:

~~~text
HTTP request
     |
     v
Request DTO
     |
     v
Validation + application criteria
     |
     v
Repository / ElasticsearchOperations
     |
     v
Entity + SearchHit metadata
     |
     v
Response mapper
     |
     v
Response DTO + metadata contract
     |
     v
HTTP response
~~~

Mỗi lớp có trách nhiệm riêng:

- Request DTO mô tả input công khai và giới hạn giá trị hợp lệ.
- Application criteria biểu diễn ý định tìm kiếm đã được kiểm tra.
- Entity biểu diễn dữ liệu domain/index.
- SearchHit/SearchHits chứa entity cùng metadata Elasticsearch.
- Response DTO mô tả dữ liệu và metadata mà API cam kết cung cấp.

DTO không chỉ là cách đổi tên field. Nó là ranh giới giúp API ổn định khi index, mapping hoặc thư viện thay đổi.

## 2. Thiết kế request DTO cho tìm kiếm

Request DTO nên mô tả nhu cầu nghiệp vụ, ví dụ tìm sản phẩm theo từ khóa, trạng thái và khoảng giá. Tránh để client gửi trực tiếp cấu trúc Elasticsearch Query DSL hoặc tên index vật lý.

Ví dụ request:

~~~java
public record ProductSearchRequest(
    String query,
    ProductStatus status,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Integer page,
    Integer size,
    ProductSort sort,
    SortDirection direction,
    Boolean includeFacets
) {}
~~~

Enum công khai:

~~~java
public enum ProductStatus {
    ACTIVE,
    DISCONTINUED,
    DRAFT
}

public enum ProductSort {
    RELEVANCE,
    NAME,
    PRICE,
    CREATED_AT
}

public enum SortDirection {
    ASC,
    DESC
}
~~~

Client chọn một giá trị trong tập enum được API hỗ trợ. Server ánh xạ enum sang field Elasticsearch tương ứng. Cách này tránh cho client điều khiển tùy ý tên field dùng để sort hoặc query.

### Validation ở request boundary

Dùng Bean Validation để từ chối input không hợp lệ trước khi tạo query:

~~~java
public record ProductSearchRequest(
    @Size(max = 120)
    String query,

    ProductStatus status,

    @DecimalMin("0.00")
    BigDecimal minPrice,

    @DecimalMin("0.00")
    BigDecimal maxPrice,

    @Min(0)
    Integer page,

    @Min(1)
    @Max(100)
    Integer size,

    ProductSort sort,

    SortDirection direction,

    Boolean includeFacets
) {}
~~~

Các annotation cần dependency validation tương ứng. Với record và Bean Validation, kiểm tra cấu hình Spring Boot/Validation version đang dùng.

Điều kiện minPrice không được lớn hơn maxPrice cần kiểm tra bổ sung vì đây là quan hệ giữa hai field:

~~~java
private void validatePriceRange(ProductSearchRequest request) {
    if (request.minPrice() != null
            && request.maxPrice() != null
            && request.minPrice().compareTo(request.maxPrice()) > 0) {
        throw new InvalidSearchRequestException(
            "minPrice must not exceed maxPrice"
        );
    }
}
~~~

Nếu điều kiện này xuất hiện ở nhiều request, có thể tạo class-level validator hoặc gom validation vào một component riêng.

### Giá trị mặc định

Không nên để mỗi controller tự chọn default page, size và sort. Có thể chuẩn hóa một lần:

~~~java
int page = request.page() == null ? 0 : request.page();
int size = request.size() == null ? 20 : request.size();

ProductSort sort = request.sort() == null
    ? ProductSort.RELEVANCE
    : request.sort();

SortDirection direction = request.direction() == null
    ? SortDirection.DESC
    : request.direction();
~~~

Giới hạn size tối đa bảo vệ Elasticsearch khỏi request trả về quá nhiều hit. Giá trị mặc định và giới hạn cần phù hợp SLA, kích thước document và khả năng xử lý của service.

### Không nhận raw Elasticsearch query từ client

Tránh request kiểu:

~~~json
{
  "index": "products-internal",
  "queryDsl": {
    "query": {
      "match_all": {}
    }
  },
  "sortField": "_script",
  "routing": "tenant-42"
}
~~~

Input này trao cho client quyền điều khiển chi tiết implementation và có thể mở ra query quá tốn tài nguyên hoặc truy cập ngoài phạm vi API dự kiến.

API công khai nên nhận từ vựng nghiệp vụ có kiểu. Server chịu trách nhiệm tạo Query DSL, chọn index/alias, tenant filter, routing và sort field.

## 3. Chuyển request DTO thành application criteria

Không nên đưa ProductSearchRequest đi sâu vào mọi repository hoặc query builder. Tạo một kiểu nội bộ đã được chuẩn hóa giúp tách HTTP contract khỏi logic tìm kiếm.

~~~java
public record ProductSearchCriteria(
    String query,
    ProductStatus status,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    int page,
    int size,
    ProductSort sort,
    SortDirection direction,
    boolean includeFacets
) {}
~~~

Factory hoặc mapper chuyển request sang criteria:

~~~java
@Component
public class ProductSearchCriteriaMapper {

    public ProductSearchCriteria toCriteria(
            ProductSearchRequest request) {

        validatePriceRange(request);

        return new ProductSearchCriteria(
            normalizeQuery(request.query()),
            request.status(),
            request.minPrice(),
            request.maxPrice(),
            request.page() == null ? 0 : request.page(),
            request.size() == null ? 20 : request.size(),
            request.sort() == null
                ? ProductSort.RELEVANCE
                : request.sort(),
            request.direction() == null
                ? SortDirection.DESC
                : request.direction(),
            Boolean.TRUE.equals(request.includeFacets())
        );
    }

    private String normalizeQuery(String query) {
        if (query == null || query.isBlank()) {
            return null;
        }
        return query.trim();
    }

    private void validatePriceRange(ProductSearchRequest request) {
        if (request.minPrice() != null
                && request.maxPrice() != null
                && request.minPrice().compareTo(request.maxPrice()) > 0) {
            throw new InvalidSearchRequestException(
                "minPrice must not exceed maxPrice"
            );
        }
    }
}
~~~

Criteria có thể bổ sung tenant ID hoặc scope lấy từ authenticated context ở service. Không thêm tenant ID do client gửi vào criteria rồi coi đó là nguồn đáng tin cậy.

Một luồng service có thể nhận criteria và tenant context riêng:

~~~java
public ProductSearchResponse search(
        ProductSearchCriteria criteria,
        String trustedTenantId) {
    // Build query with mandatory tenant filter.
    // Execute search and map results.
}
~~~

Nếu tenant được resolve từ security principal, service nên gọi abstraction như CurrentTenant thay vì nhận một chuỗi tùy ý từ controller.

## 4. Thiết kế response DTO cho nội dung domain

Response item nên chỉ chứa field client cần sử dụng. Ví dụ:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    ProductStatus status,
    BigDecimal price,
    String currency
) {}
~~~

Mapper chuyển entity sang DTO:

~~~java
@Component
public class ProductResponseMapper {

    public ProductSearchItem toItem(Product product) {
        return new ProductSearchItem(
            product.getId(),
            product.getName(),
            ProductStatus.valueOf(product.getStatus()),
            product.getPrice(),
            "VND"
        );
    }
}
~~~

Trong code thực tế, tránh gọi valueOf nếu source có thể chứa giá trị legacy hoặc null mà không có policy xử lý. Có thể viết mapper status rõ ràng và chuyển dữ liệu không hợp lệ thành lỗi mapping có context.

### Không serialize entity trực tiếp

Một response không nên tự động bao gồm:

- Tenant ID nội bộ nếu API không cần công bố.
- Field dùng cho indexing/debugging.
- Internal supplier code.
- Elasticsearch version, sequence number hoặc primary term nếu API không cam kết cung cấp.
- Raw source document.
- Field chỉ phục vụ migration hoặc analyzer.
- Internal scoring/debug metadata chưa được định nghĩa.

DTO giúp lựa chọn có chủ đích field nào được công bố và kiểu dữ liệu nào ổn định cho client.

### DTO có thể khác cấu trúc entity

Một entity có thể lưu firstName và lastName, trong khi response trả displayName. Một nested structure có thể được rút gọn thành variant summary. Một số field có thể được kết hợp hoặc chuyển đơn vị.

Đây là lý do mapper nên là một thành phần rõ ràng, có unit test, thay vì dựa vào JSON serializer để biến entity thành response.

## 5. SearchHit và SearchHits chứa gì?

Spring Data Elasticsearch có kiểu kết quả giàu metadata.

- SearchHit<T> đại diện cho một hit và chứa entity content cùng metadata của hit.
- SearchHits<T> đại diện cho tập hit và chứa thông tin tổng hợp về kết quả tìm kiếm.
- SearchPage<T> có thể kết hợp paging abstraction với search hit metadata trong các API được hỗ trợ.

Một SearchHit có thể cung cấp:

- ID document.
- Index chứa document.
- Entity content.
- Relevance score.
- Highlight fields.
- Sort values.
- Inner hits nếu query sử dụng.
- Các metadata hit khác tùy phiên bản.

SearchHits có thể cung cấp:

- Danh sách SearchHit.
- Tổng số hit và quan hệ total hits.
- Max score.
- Aggregations.
- Suggest metadata.
- Scroll ID hoặc thông tin khác tùy operation.

Không nên trả nguyên SearchHit hoặc SearchHits qua REST. Đây là kiểu framework chứa nhiều chi tiết không phải lúc nào cũng thuộc hợp đồng API. Hãy map những thông tin thực sự cần thiết sang response DTO.

### SearchHit không chỉ là entity

Nếu code gọi:

~~~java
SearchHit<Product> hit = ...;
Product product = hit.getContent();
~~~

thì phần score, highlight và sort values vẫn nằm trên hit. Nếu map sang Product ngay và bỏ hit, những metadata này sẽ không còn ở bước sau.

Khi response cần score hoặc highlight, hãy giữ SearchHit tới response mapper.

## 6. Định nghĩa metadata envelope

Một search response thường có hai phần: danh sách kết quả và metadata mô tả kết quả.

Ví dụ hợp đồng:

~~~json
{
  "items": [
    {
      "id": "P-100",
      "name": "Wireless Keyboard",
      "status": "ACTIVE",
      "price": 790000,
      "currency": "VND"
    }
  ],
  "metadata": {
    "pagination": {
      "page": 0,
      "size": 20,
      "returned": 1,
      "totalHits": 1,
      "totalHitsRelation": "EXACT",
      "hasNext": false
    },
    "sort": {
      "field": "RELEVANCE",
      "direction": "DESC"
    },
    "execution": {
      "tookMillis": 12
    }
  }
}
~~~

Response có thể được biểu diễn bằng record:

~~~java
public record ProductSearchResponse(
    List<ProductSearchItem> items,
    SearchMetadata metadata
) {}

public record SearchMetadata(
    PaginationMetadata pagination,
    SortMetadata sort,
    ExecutionMetadata execution,
    List<FacetMetadata> facets
) {}

public record PaginationMetadata(
    int page,
    int size,
    int returned,
    Long totalHits,
    TotalHitsAccuracy totalHitsAccuracy,
    Boolean hasNext
) {}

public enum TotalHitsAccuracy {
    EXACT,
    LOWER_BOUND,
    NOT_REQUESTED
}

public record SortMetadata(
    ProductSort field,
    SortDirection direction
) {}

public record ExecutionMetadata(
    Long tookMillis,
    Float maxScore
) {}

public record FacetMetadata(
    String name,
    List<FacetBucket> buckets
) {}

public record FacetBucket(
    String key,
    long count
) {}
~~~

Envelope có cấu trúc rõ ràng giúp client không phải đoán metadata nằm ở đâu. Các trường metadata có thể thay đổi theo loại query, nhưng cần giữ semantics nhất quán.

### Metadata là hợp đồng công khai

Một khi client sử dụng page, totalHits, score hoặc facet, các field đó trở thành một phần API contract. Không đổi tên, kiểu dữ liệu hoặc ý nghĩa âm thầm chỉ vì Spring Data hoặc Elasticsearch thay đổi.

Định nghĩa rõ:

- totalHits là số chính xác hay cận dưới.
- page bắt đầu từ 0 hay 1.
- size là số item tối đa được yêu cầu hay số item thực tế.
- returned là số item thực tế trong response.
- hasNext được tính theo total chính xác hay theo chiến lược fetch.
- tookMillis đo thời gian nào.
- score có thể null trong trường hợp nào.
- facets có thể vắng mặt, rỗng hay không được yêu cầu.

## 7. Phân trang và total hits

Một response phân trang thường cần:

- page: số trang.
- size: số item tối đa trong trang.
- returned: số item thực tế trả về.
- totalHits: số hit phù hợp.
- totalHitsAccuracy: độ chính xác của total.
- hasNext: có thể còn trang tiếp theo hay không.

Không giả định totalHits luôn chính xác. Elasticsearch có thể giới hạn việc đếm total hit để tiết kiệm chi phí, tùy query option và version. Search response có thể cho biết total hits relation như equal-to hoặc greater-than-or-equal-to.

Vì vậy, không nên đặt tên field là exactTotal nếu query không yêu cầu đếm chính xác.

### Mapping metadata từ SearchHits

Ví dụ:

~~~java
private PaginationMetadata toPagination(
        SearchHits<Product> hits,
        int page,
        int size) {

    long totalHits = hits.getTotalHits();

    TotalHitsAccuracy accuracy =
        mapAccuracy(hits.getTotalHitsRelation());

    int returned = hits.getSearchHits().size();

    return new PaginationMetadata(
        page,
        size,
        returned,
        totalHits,
        accuracy,
        accuracy == TotalHitsAccuracy.EXACT
            ? (long) (page + 1) * size < totalHits
            : null
    );
}
~~~

Tên enum, method getTotalHitsRelation và kiểu trả về phụ thuộc phiên bản Spring Data Elasticsearch. Đoạn code minh họa cách ánh xạ relation sang contract nội bộ. Nếu relation không được cung cấp trong API hiện tại, không tự gán EXACT; hãy dùng NOT_REQUESTED hoặc một trạng thái phù hợp.

Với lower-bound total, không thể tính hasNext chính xác chỉ từ totalHits. Có thể dùng chiến lược fetch thêm một item, cursor pagination hoặc trả hasNext theo semantics đã định nghĩa.

### Page number và offset

PageRequest.of(page, size) dùng page index bắt đầu từ 0. Nếu HTTP API công bố page bắt đầu từ 1, cần chuyển đổi ở request mapper và response mapper. Đừng để controller, service và client mỗi nơi dùng một quy ước.

Offset pagination phù hợp với trang đầu và các trang nông. Với page sâu, Elasticsearch có giới hạn và chi phí cho from/size. Search_after hoặc cursor pagination có thể phù hợp hơn.

## 8. Sort metadata phải phản ánh lựa chọn công khai

Request không nên gửi tên field tùy ý. Dùng enum:

~~~java
public enum ProductSort {
    RELEVANCE,
    NAME,
    PRICE,
    CREATED_AT
}
~~~

Server ánh xạ enum sang field đã được cho phép:

~~~java
private String toSortField(ProductSort sort) {
    return switch (sort) {
        case NAME -> "name.keyword";
        case PRICE -> "price";
        case CREATED_AT -> "createdAt";
        case RELEVANCE -> "_score";
    };
}
~~~

Tên field name.keyword chỉ hợp lệ nếu mapping thực tế có multi-field đó. Mapping và sort field cần được thống nhất khi tạo index.

Response nên trả sort field theo từ vựng API, ví dụ PRICE, không nhất thiết trả tên field Elasticsearch price. Như vậy, API không bị ràng buộc vào chi tiết mapping.

### Stable sort

Nếu nhiều document có cùng giá hoặc cùng tên, chỉ sort theo field đó có thể tạo thứ tự không ổn định giữa các trang. Nên thêm tie-breaker ổn định, ví dụ document ID hoặc field có giá trị duy nhất phù hợp với Elasticsearch version và sort semantics.

Response metadata có thể công bố lựa chọn sort chính mà client yêu cầu, trong khi tie-breaker là chi tiết implementation nội bộ. Nếu client dùng cursor, cursor phải giữ đủ sort values để tiếp tục đúng vị trí.

## 9. Score và relevance metadata

Relevance score là metadata của search hit, không phải thuộc tính domain của Product. Không thêm score vào entity chỉ để trả response.

DTO có thể có trường score tùy API:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    BigDecimal price,
    Float score
) {}
~~~

Mapper nhận SearchHit:

~~~java
private ProductSearchItem toItem(SearchHit<Product> hit) {
    Product product = hit.getContent();

    return new ProductSearchItem(
        product.getId(),
        product.getName(),
        product.getPrice(),
        hit.getScore()
    );
}
~~~

Score có thể null hoặc không có ý nghĩa với một số loại query/sort. Ví dụ query không tính relevance hoặc sort hoàn toàn theo field. Không để client mặc định score luôn có giá trị và có thể so sánh giữa hai query khác nhau.

Nếu score chỉ dùng nội bộ để sắp xếp, có thể không công bố nó. Chỉ đưa score vào response khi client thực sự cần và semantics đã được mô tả.

Không dùng score như một xác suất hoặc phần trăm độ phù hợp nếu chưa có mô hình hiệu chỉnh riêng.

## 10. Highlight metadata

Highlight trả các fragment chứa đoạn text khớp query. Đây là metadata của hit, không phải nội dung gốc trong entity.

Response có thể có:

~~~json
{
  "id": "P-100",
  "name": "Wireless Keyboard",
  "highlights": {
    "name": [
      "Wireless <em>Keyboard</em>"
    ]
  }
}
~~~

Một DTO có thể định nghĩa:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    Map<String, List<String>> highlights
) {}
~~~

Mapper lấy highlight từ SearchHit:

~~~java
private Map<String, List<String>> toHighlights(
        SearchHit<Product> hit) {

    return hit.getHighlightFields();
}
~~~

Kiểu trả về và cách lấy highlight có thể thay đổi theo Spring Data version. Nếu không bật highlight trong query, map có thể rỗng.

### HTML trong highlight

Một số highlighter tạo fragment có tag như em hoặc strong. Không render fragment như HTML tùy ý nếu nội dung gốc có thể chứa markup không tin cậy.

Có thể chọn một trong các contract:

- Trả plain text fragments và metadata vị trí.
- Trả markup đã sanitize theo allowlist.
- Trả fragment có marker token rõ ràng để frontend render an toàn.

Đừng để API ngầm cam kết mọi fragment đều là HTML an toàn.

## 11. Facet và aggregation metadata

Facet giúp client hiển thị bộ lọc như số sản phẩm theo trạng thái, thương hiệu hoặc danh mục. Trong Elasticsearch, facet thường được xây từ aggregation.

Ví dụ response:

~~~json
{
  "facets": [
    {
      "name": "status",
      "buckets": [
        { "key": "ACTIVE", "count": 120 },
        { "key": "DISCONTINUED", "count": 8 }
      ]
    }
  ]
}
~~~

DTO:

~~~java
public record FacetMetadata(
    String name,
    List<FacetBucket> buckets
) {}

public record FacetBucket(
    String key,
    long count
) {}
~~~

Không trả raw aggregation object của Elasticsearch. Map aggregation thành cấu trúc ổn định theo nghiệp vụ.

### Tên facet và bucket

Tên facet công khai có thể là status, brand hoặc category. Nó không cần trùng tên aggregation nội bộ như status_facet_v2. Điều này cho phép đổi tên aggregation mà không đổi API.

Bucket key nên có kiểu dữ liệu rõ. Nếu facet có key số hoặc date range, cân nhắc DTO chuyên biệt thay vì ép tất cả thành String mà không mô tả semantics.

### Aggregation count không phải lúc nào cũng chính xác

Một số aggregation phân tán có thể trả kết quả xấp xỉ hoặc có error bound tùy loại aggregation và cấu hình. Nếu client dùng facet count để ra quyết định chính xác, cần hiểu semantics của aggregation và expose thông tin độ chính xác khi phù hợp.

Không hứa mọi facet count là exact nếu aggregation có thể approximate.

## 12. Cursor metadata cho search_after

Với tập kết quả lớn, cursor pagination có thể phù hợp hơn offset pagination. Elasticsearch search_after dùng sort values của hit cuối để tiếp tục trang sau.

Không nên expose một mảng sort values thô làm public API nếu muốn giữ implementation linh hoạt. Có thể trả cursor opaque:

~~~json
{
  "items": [],
  "metadata": {
    "cursor": {
      "next": "eyJ2IjoxLCJzIjpbNzkwMDAwLCJQLTEwMF19"
    }
  }
}
~~~

Cursor là token do server tạo từ dữ liệu cần thiết để tiếp tục truy vấn. Server có thể encode payload có version và ký token để ngăn client sửa giá trị. Nếu cursor chứa tenant, filter hoặc sort state, phải xác minh nó vẫn khớp request và principal hiện tại khi sử dụng.

### Cursor không phải quyền truy cập

Cursor chỉ giúp tiếp tục vị trí đọc. Nó không thay thế authorization, tenant filter hoặc kiểm tra request scope. Một cursor được gửi từ client không được phép mở rộng phạm vi dữ liệu.

### Giữ contract cursor ổn định

Cursor nên có version nội bộ để server có thể thay đổi cấu trúc payload. Client chỉ lưu và gửi lại token, không cần biết sort values hoặc field mapping bên trong.

Nếu index thay đổi mạnh hoặc snapshot search context hết hạn, server cần trả lỗi cursor expired/invalid theo contract rõ ràng.

## 13. Thời gian thực thi và metadata kỹ thuật

Một response có thể công bố tookMillis, nhưng phải định nghĩa nó đo thời gian nào.

Elasticsearch response có thể có thời gian xử lý ở phía cluster. Thời gian đo ở application service bao gồm network, mapping và code phía server. Hai giá trị không giống nhau.

Có thể tách tên rõ:

- elasticsearchTookMillis: thời gian Elasticsearch báo cho search operation.
- serviceElapsedMillis: thời gian service đo từ lúc bắt đầu đến lúc hoàn tất.
- returned: số item response mapper tạo ra.

Không gộp các con số vào một field took nếu client có thể hiểu sai.

### Không công bố mọi debug metadata

Không cần trả node name, shard ID, raw query DSL, cluster endpoint hoặc internal index name trong response công khai nếu không có use case. Những thông tin này có thể làm lộ cấu trúc hạ tầng hoặc khiến client phụ thuộc implementation.

Có thể ghi chúng vào structured logs hoặc tracing nội bộ với quyền truy cập phù hợp.

## 14. Mapping SearchHits sang response envelope

Một mapper có thể nhận SearchHits và criteria:

~~~java
@Component
public class ProductSearchResponseMapper {

    private final ProductResponseMapper productMapper;

    public ProductSearchResponseMapper(
            ProductResponseMapper productMapper) {
        this.productMapper = productMapper;
    }

    public ProductSearchResponse toResponse(
            SearchHits<Product> hits,
            ProductSearchCriteria criteria) {

        List<ProductSearchItem> items =
            hits.getSearchHits().stream()
                .map(this::toSearchItem)
                .toList();

        SearchMetadata metadata = new SearchMetadata(
            toPagination(hits, criteria.page(), criteria.size()),
            new SortMetadata(
                criteria.sort(),
                criteria.direction()
            ),
            new ExecutionMetadata(
                null,
                hits.getMaxScore()
            ),
            List.of()
        );

        return new ProductSearchResponse(items, metadata);
    }

    private ProductSearchItem toSearchItem(
            SearchHit<Product> hit) {
        Product product = hit.getContent();

        return new ProductSearchItem(
            product.getId(),
            product.getName(),
            product.getStatus(),
            product.getPrice(),
            "VND",
            hit.getScore(),
            hit.getHighlightFields()
        );
    }
}
~~~

Đây là skeleton minh họa; constructor ProductSearchItem và SearchMetadata cần thống nhất với DTO được chọn trong dự án. Các method SearchHits và kiểu relation cần đối chiếu Spring Data version.

Một mapper riêng giúp:

- Giữ controller mỏng.
- Tách metadata framework khỏi contract công khai.
- Unit test cách map score/highlight/total hits.
- Thay đổi entity mà ít ảnh hưởng response.
- Chuẩn hóa các loại query khác nhau về cùng một envelope.

### Tránh map metadata ở controller

Controller nên nhận request, gọi service và trả DTO. Nếu controller tự đọc SearchHits, tính total pages, lấy highlight và chuyển entity, nhiều endpoint sẽ dễ có semantics khác nhau.

## 15. Controller và service hoàn chỉnh

Controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductSearchController {

    private final ProductSearchService searchService;

    public ProductSearchController(
            ProductSearchService searchService) {
        this.searchService = searchService;
    }

    @PostMapping("/search")
    public ProductSearchResponse search(
            @Valid @RequestBody ProductSearchRequest request) {
        return searchService.search(request);
    }
}
~~~

Service:

~~~java
@Service
public class ProductSearchService {

    private final ProductSearchCriteriaMapper criteriaMapper;
    private final ProductQueryFactory queryFactory;
    private final ElasticsearchOperations operations;
    private final ProductSearchResponseMapper responseMapper;
    private final CurrentTenant currentTenant;

    public ProductSearchService(
            ProductSearchCriteriaMapper criteriaMapper,
            ProductQueryFactory queryFactory,
            ElasticsearchOperations operations,
            ProductSearchResponseMapper responseMapper,
            CurrentTenant currentTenant) {
        this.criteriaMapper = criteriaMapper;
        this.queryFactory = queryFactory;
        this.operations = operations;
        this.responseMapper = responseMapper;
        this.currentTenant = currentTenant;
    }

    public ProductSearchResponse search(
            ProductSearchRequest request) {

        ProductSearchCriteria criteria =
            criteriaMapper.toCriteria(request);

        String tenantId = currentTenant.requireTenantId();

        Query query = queryFactory.create(criteria, tenantId);

        SearchHits<Product> hits =
            operations.search(query, Product.class);

        return responseMapper.toResponse(hits, criteria);
    }
}
~~~

ProductQueryFactory chịu trách nhiệm tạo query từ criteria và tenant context. Nó có thể sử dụng NativeQuery để kết hợp match, filter, range, sort, pageable và aggregation.

Service không trả entity hoặc SearchHits trực tiếp. Response mapper chuyển kết quả thành hợp đồng HTTP.

### Không đưa ElasticsearchOperations vào controller

Controller không nên biết cách chọn index, tạo Query DSL hoặc đọc SearchHit metadata. Những trách nhiệm này thuộc application/service layer.

## 16. Error response cũng là một hợp đồng DTO

Request không hợp lệ, cursor hết hạn, Elasticsearch timeout hoặc lỗi mapping nên được biểu diễn qua error response ổn định.

Ví dụ:

~~~json
{
  "error": {
    "code": "INVALID_SEARCH_RANGE",
    "message": "minPrice must not exceed maxPrice",
    "details": [
      {
        "field": "minPrice",
        "reason": "must be less than or equal to maxPrice"
      }
    ],
    "traceId": "c2b5e3a1"
  }
}
~~~

DTO:

~~~java
public record ApiErrorResponse(
    ApiError error
) {}

public record ApiError(
    String code,
    String message,
    List<ApiErrorDetail> details,
    String traceId
) {}

public record ApiErrorDetail(
    String field,
    String reason
) {}
~~~

Dùng ControllerAdvice để chuyển exception sang response:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(InvalidSearchRequestException.class)
    ResponseEntity<ApiErrorResponse> handleInvalidSearch(
            InvalidSearchRequestException ex) {

        ApiError error = new ApiError(
            "INVALID_SEARCH_REQUEST",
            ex.getMessage(),
            List.of(),
            null
        );

        return ResponseEntity.badRequest()
            .body(new ApiErrorResponse(error));
    }
}
~~~

Không trả stack trace, raw Elasticsearch exception, index name nội bộ hoặc query DSL cho client. Ghi thông tin kỹ thuật đầy đủ vào log nội bộ theo chính sách bảo mật, rồi trả mã lỗi có thể xử lý ở client.

### Phân loại lỗi

Một số lỗi có thể map thành:

- 400: input không hợp lệ.
- 404: resource domain không tồn tại theo contract.
- 409: conflict hoặc version conflict nếu API công bố semantics này.
- 429: giới hạn tốc độ hoặc quá tải theo policy.
- 503: dependency Elasticsearch không khả dụng tạm thời.
- 500: lỗi mapping hoặc lỗi nội bộ không dự kiến.

Không map mọi Elasticsearch exception thành 500 hoặc mọi kết quả rỗng thành 404. Phân loại theo nguyên nhân và hành vi API mong đợi.

## 17. Versioning và tương thích response

API DTO là hợp đồng với client. Khi thêm field mới, đổi enum hoặc thay semantics metadata, cần đánh giá tác động tới client cũ.

Các nguyên tắc:

- Thêm field response optional thường ít phá vỡ hơn đổi field hiện có.
- Không đổi kiểu number thành string nếu chưa version hóa.
- Không đổi page index từ 0 sang 1 âm thầm.
- Không đổi totalHits từ exact sang lower-bound mà không cập nhật contract.
- Không đổi enum value đã được client lưu hoặc so sánh.
- Xác định chính sách null, absent và empty list.
- Giữ error code ổn định.
- Dùng API version hoặc migration plan cho thay đổi breaking.

### Null và field vắng mặt

Có ba trạng thái khác nhau:

- Field không xuất hiện.
- Field xuất hiện với null.
- Field xuất hiện với giá trị rỗng như [] hoặc "".

Client có thể diễn giải chúng khác nhau. Ví dụ facets vắng mặt có thể nghĩa là không được yêu cầu; facets rỗng có thể nghĩa là đã tính nhưng không có bucket. Hãy chọn một quy tắc và giữ nhất quán.

### Không expose enum nội bộ trực tiếp

Nếu enum entity thay đổi vì index legacy, không để enum persistence tự động quyết định JSON contract. Dùng enum API riêng hoặc mapper để kiểm soát tên và giá trị công khai.

## 18. Hợp đồng metadata cho nhiều loại kết quả

Không phải mọi query đều có cùng metadata. Có thể định nghĩa envelope chung và các phần optional có semantics rõ.

| Metadata | Dùng khi nào | Lưu ý |
|---|---|---|
| pagination | Kết quả được phân trang | Công bố page/size/returned và total accuracy |
| sort | Client chọn thứ tự | Trả lựa chọn công khai, không nhất thiết raw field |
| score | Relevance có ý nghĩa với client | Có thể null và không phải xác suất |
| highlights | Query bật highlighting | Render fragment an toàn |
| facets | Query có aggregations | Nêu rõ bucket count có thể approximate hay không |
| cursor | Search_after hoặc cursor paging | Token opaque, ràng buộc với filter/sort/tenant |
| execution | Cần quan sát thời gian | Phân biệt Elasticsearch time và service elapsed |
| warnings | Kết quả có giới hạn hoặc partial | Dùng mã ổn định và giải thích semantics |

Có thể có response chuyên biệt cho search, autocomplete, geo search hoặc aggregation-only endpoint. Không cố nhét mọi kiểu kết quả vào một DTO quá tổng quát với hàng chục field nullable.

Nếu các endpoint có cấu trúc nội dung khác nhau nhưng chia sẻ pagination metadata, có thể tái sử dụng một record metadata nhỏ thay vì một response class khổng lồ.

## 19. Kiểm thử request DTO và validation

Unit test criteria mapper nên xác nhận:

- Giá trị mặc định page, size và sort.
- Chuỗi query được normalize theo policy.
- minPrice lớn hơn maxPrice bị từ chối.
- size vượt giới hạn bị từ chối.
- Enum không hợp lệ bị validation từ chối.
- Giá trị null/blank được xử lý đúng.
- Không có input công khai nào ghi đè tenant context.

Controller test có thể dùng MockMvc hoặc WebTestClient tùy stack để xác nhận JSON request được validate trước khi service được gọi.

Ví dụ test mapper:

~~~java
@Test
void rejectsInvalidPriceRange() {
    ProductSearchRequest request =
        new ProductSearchRequest(
            "keyboard",
            ProductStatus.ACTIVE,
            new BigDecimal("200"),
            new BigDecimal("100"),
            0,
            20,
            ProductSort.RELEVANCE,
            SortDirection.DESC,
            false
        );

    assertThatThrownBy(() -> mapper.toCriteria(request))
        .isInstanceOf(InvalidSearchRequestException.class);
}
~~~

Kiểm tra cả lỗi field validation và lỗi quan hệ giữa field. Không chỉ test happy path.

## 20. Kiểm thử response mapper và metadata contract

Response mapper unit test nên tạo SearchHit/SearchHits mẫu hoặc dùng fixture phù hợp, sau đó xác nhận:

- Entity content được chuyển đúng sang DTO.
- Internal field không xuất hiện.
- Score được map theo policy.
- Highlight map đúng field.
- Total hits và relation được chuyển chính xác.
- Page, size và returned có semantics nhất quán.
- Facets được chuyển thành bucket DTO.
- Metadata optional được xử lý rõ.
- Không có raw SearchHit hoặc SearchHits trong response object.

Có thể dùng contract test kiểm tra JSON serialization để phát hiện đổi tên field hoặc kiểu dữ liệu ngoài ý muốn.

Ví dụ JSON assertion:

~~~java
mockMvc.perform(post("/api/products/search")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "query": "keyboard",
              "page": 0,
              "size": 20,
              "sort": "RELEVANCE"
            }
            """))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.metadata.pagination.page").value(0))
    .andExpect(jsonPath("$.metadata.pagination.size").value(20));
~~~

Đây là cấu trúc minh họa; endpoint, fixture và JSON path cần khớp API thực tế.

### Kiểm thử không lộ field nội bộ

Có thể serialize response DTO và xác nhận không chứa tenantId, internalSupplierCode hoặc raw query metadata nếu chúng không thuộc public contract.

Test này đặc biệt hữu ích khi entity có thêm field mới. Vì response dùng DTO riêng, thay đổi entity không tự động làm JSON response đổi.

## 21. Integration test cho SearchHits metadata

Unit test mapper không chứng minh Elasticsearch trả đúng score, highlight, total hits hoặc aggregation. Khi các metadata này là chức năng quan trọng, cần integration test với Elasticsearch version tương thích.

Ví dụ:

- Seed document có từ khóa để match.
- Chạy match query với highlight.
- Xác nhận SearchHit có highlight fragment.
- Kiểm tra score tồn tại khi query tính relevance.
- Chạy aggregation và xác nhận bucket key/count.
- Cấu hình total hits tracking phù hợp và xác nhận relation.
- Kiểm tra sort values khi dùng cursor.
- Xác nhận mapping DTO không làm mất metadata cần thiết.

Không kiểm tra giá trị score tuyệt đối nếu không có lý do, vì score có thể thay đổi khi analyzer, corpus hoặc query thay đổi. Thường nên kiểm tra hit được sắp xếp theo relevance hoặc score có giá trị hợp lệ.

## 22. Các lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Response thay đổi khi thêm field entity | Controller serialize entity trực tiếp | Dùng response DTO và mapper |
| Client gửi tên field sort tùy ý | Request DTO nhận raw field name | Dùng enum và allowlist |
| Client gửi raw Query DSL | API để lộ implementation Elasticsearch | Dùng request criteria có kiểu |
| Mất score/highlight | Map SearchHit sang entity quá sớm | Giữ SearchHit tới response mapper |
| Total pages sai | Giả định totalHits luôn exact | Expose total relation/accuracy |
| hasNext sai với total lower-bound | Tính next page từ số đếm không chính xác | Dùng cursor hoặc fetch thêm một hit |
| Trang sau bị trùng/thiếu item | Sort không ổn định | Thêm tie-breaker ổn định |
| Client phụ thuộc tên field index | Response trả raw mapping field | Trả enum/tên nghiệp vụ |
| Highlight gây XSS | Render HTML fragment không sanitize | Trả plain text hoặc sanitize allowlist |
| Facet count bị hiểu là exact | Không công bố aggregation semantics | Mô tả accuracy/error bound phù hợp |
| Cursor bị sửa hoặc dùng chéo tenant | Token không ràng buộc request context | Ký token và xác minh tenant/filter |
| Error response làm lộ hạ tầng | Trả raw exception hoặc query | Dùng error DTO và log nội bộ |
| Null và empty list bị dùng lẫn lộn | Không định nghĩa contract | Quy định absent/null/empty |
| API thay đổi breaking ngoài ý muốn | Không có contract test/versioning | Thêm serialization và compatibility tests |

## 23. Checklist thiết kế DTO và metadata

- [ ] Request DTO mô tả nhu cầu nghiệp vụ, không phải Query DSL.
- [ ] Validate query length, range, page và size ở boundary.
- [ ] Dùng enum/allowlist cho sort field và direction.
- [ ] Không nhận index, routing hoặc tenant scope tùy ý từ client.
- [ ] Chuyển request thành application criteria nội bộ.
- [ ] Entity Elasticsearch không được trả trực tiếp qua controller.
- [ ] Response DTO chỉ chứa field công khai cần thiết.
- [ ] Giữ SearchHit khi cần score, highlight hoặc sort values.
- [ ] Map SearchHits metadata thành DTO riêng.
- [ ] Định nghĩa page index, size, returned và totalHits accuracy.
- [ ] Không hứa totalHits chính xác nếu Elasticsearch trả lower-bound.
- [ ] Dùng stable sort cho pagination.
- [ ] Dùng cursor opaque cho search_after khi phù hợp.
- [ ] Công bố score chỉ khi semantics rõ.
- [ ] Sanitize hoặc thiết kế an toàn cho highlight fragments.
- [ ] Map aggregation thành facet DTO ổn định.
- [ ] Phân biệt Elasticsearch took với service elapsed.
- [ ] Error response có code ổn định, không lộ raw exception.
- [ ] Có unit test cho criteria mapper và response mapper.
- [ ] Có controller/serialization contract test.
- [ ] Có Elasticsearch integration test cho metadata thực tế.
- [ ] Có chiến lược versioning cho thay đổi breaking.

DTO yêu cầu, DTO phản hồi và metadata envelope tạo ranh giới ổn định giữa API và Elasticsearch. Request DTO chỉ nhận lựa chọn nghiệp vụ đã được kiểm tra; application criteria chuyển chúng thành query có kiểm soát; response mapper chuyển entity cùng SearchHit metadata thành một hợp đồng công khai rõ nghĩa. Khi định nghĩa chính xác pagination, total-hit accuracy, sort, score, highlight, facets, cursor và error response, client không cần phụ thuộc vào SearchHits hoặc mapping nội bộ. Điều này giúp ứng dụng thay đổi index và query strategy mà vẫn giữ API nhất quán.

