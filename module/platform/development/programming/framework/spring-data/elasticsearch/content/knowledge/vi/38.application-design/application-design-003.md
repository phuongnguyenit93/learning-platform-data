# Tổ chức dịch vụ tìm kiếm, Repository và bộ dựng truy vấn

Trong một ứng dụng Spring Data Elasticsearch, code tìm kiếm thường bắt đầu bằng một repository method đơn giản. Khi yêu cầu tăng lên — nhiều bộ lọc tùy chọn, tenant, sort, phân trang, highlight, aggregation và nhiều loại response — nếu controller tự dựng Query DSL hoặc service chứa toàn bộ logic truy vấn, code sẽ nhanh chóng khó đọc và khó kiểm thử.

Một thiết kế dễ duy trì cần phân chia trách nhiệm rõ ràng:

- **Controller/API** nhận request, xác thực đầu vào và chuyển đổi sang tiêu chí tìm kiếm.
- **Search service** điều phối use case, áp dụng chính sách nghiệp vụ và giới hạn truy vấn.
- **Repository hoặc search adapter** thực hiện truy cập Elasticsearch.
- **Query builder** chuyển tiêu chí tìm kiếm thành query có cấu trúc, không thực hiện I/O.
- **Mapper/projection** chuyển search hit thành response model phù hợp với API.

Không phải truy vấn nào cũng cần một lớp builder riêng. Repository method vẫn là lựa chọn tốt cho thao tác đơn giản. `ElasticsearchOperations` và `NativeQuery` phù hợp khi cần kiểm soát Query DSL, metadata, aggregation hoặc search hit. Mục tiêu là đặt mỗi loại logic ở đúng nơi và giữ cho đường đi từ API tới Elasticsearch có thể hiểu, kiểm thử và quan sát được.

## 1. Bức tranh kiến trúc

Một luồng tìm kiếm điển hình:

~~~mermaid
flowchart TD
    A["HTTP Search Request"] --> B["Search Controller"]
    B --> C["Request validation / DTO mapping"]
    C --> D["ProductSearchService"]
    D --> E["Search criteria + policy"]
    E --> F["ProductSearchQueryBuilder"]
    F --> G["ProductSearchRepository / Search Adapter"]
    G --> H["ElasticsearchOperations or Repository"]
    H --> I["Elasticsearch index / alias"]
    I --> H
    H --> J["SearchHits / entities"]
    J --> K["Result mapper"]
    K --> L["SearchResponse DTO"]
    L --> A
~~~

Mỗi thành phần có một câu hỏi riêng:

| Thành phần | Câu hỏi nó trả lời |
|---|---|
| Controller | Người gọi gửi gì và được phép gọi use case nào? |
| Criteria | Các điều kiện tìm kiếm có ý nghĩa nghiệp vụ là gì? |
| Search service | Có thể tìm kiếm trong phạm vi nào và cần áp dụng policy nào? |
| Query builder | Criteria được biểu diễn thành Query DSL ra sao? |
| Repository/adapter | Gửi request tới Elasticsearch và lấy kết quả bằng cách nào? |
| Mapper | Search hit trở thành response contract nào? |

Không nên để controller biết tên field Elasticsearch, analyzer, nested path hoặc cách tạo bool query. Cũng không nên để query builder tự đọc SecurityContext, gọi repository hoặc tự gửi request. Các ranh giới rõ giúp thay đổi mapping hoặc cách truy cập dữ liệu mà ít ảnh hưởng phần còn lại.

## 2. Phân biệt Repository, ElasticsearchOperations và Query Builder

Ba thành phần này thường bị gộp vào một lớp nhưng có vai trò khác nhau.

### Repository

Repository cung cấp abstraction cho các thao tác lưu/đọc document và các query method có tên hoặc query khai báo.

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByStatus(String status);

    List<ProductDocument> findByStatusAndCategory(
            String status,
            String category
    );

    Optional<ProductDocument> findByProductId(String productId);
}
~~~

Phù hợp khi:

- Query có điều kiện đơn giản, ổn định.
- Tên method mô tả được ý nghĩa truy vấn.
- Không cần nhiều metadata ngoài entity.
- Repository là abstraction tự nhiên cho document được lưu.

### ElasticsearchOperations

`ElasticsearchOperations` là API cấp thấp hơn repository, cho phép ứng dụng điều khiển query, index coordinates, search hit, update, bulk và các thao tác Elasticsearch khác.

Ví dụ:

~~~java
SearchHits<ProductDocument> hits =
        operations.search(
                query,
                ProductDocument.class,
                IndexCoordinates.of("products")
        );
~~~

Phù hợp khi:

- Query có nhiều filter tùy chọn.
- Cần bool/nested/function score/query DSL phức tạp.
- Cần highlight, aggregation, suggest hoặc search metadata.
- Cần `SearchHits<T>`, sort values hoặc score.
- Cần kiểm soát index/alias cụ thể.
- Cần xây một custom repository fragment.

### Query builder

Query builder chỉ chịu trách nhiệm biến tiêu chí đầu vào thành query object. Nó không thực thi request và không biết repository nào đang dùng.

Ví dụ:

~~~java
public class ProductSearchQueryBuilder {

    public Query build(ProductSearchCriteria criteria) {
        // Build Query DSL from validated criteria.
    }
}
~~~

Builder phù hợp khi có nhiều nhánh điều kiện, cần tái sử dụng logic dựng query hoặc muốn unit test riêng query semantics.

Không cần tạo builder chỉ để bọc một câu gọi `findByStatus(...)`. Thêm lớp không tạo thêm giá trị nếu nó chỉ chuyển tiếp một method.

## 3. Bắt đầu từ use case, không bắt đầu từ Query DSL

Hãy mô tả điều người dùng cần làm bằng ngôn ngữ nghiệp vụ:

- Tìm sản phẩm đang xuất bản.
- Lọc theo danh mục.
- Tìm theo từ khóa trong tên và mô tả.
- Giới hạn khoảng giá.
- Chỉ xem sản phẩm thuộc tenant hiện tại.
- Sắp xếp theo giá hoặc thời điểm cập nhật.
- Phân trang kết quả.

Một API request có thể trông như:

~~~http
GET /api/products/search?q=keyboard&category=ACCESSORIES&minPrice=100000&maxPrice=2000000&page=0&size=25&sort=price,asc
~~~

Controller nên chuyển request này thành một criteria object có kiểu dữ liệu rõ ràng:

~~~java
public record ProductSearchCriteria(
        String text,
        String category,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        String status,
        int page,
        int size,
        ProductSort sort
) {
}
~~~

Criteria biểu diễn ý định tìm kiếm. Nó không nên chứa Elasticsearch `Query`, tên analyzer hoặc raw JSON do client gửi lên.

Nếu API có nhiều loại filter, có thể dùng nested records hoặc value objects để nhóm các điều kiện có liên quan. Đừng tạo một criteria với hàng chục tham số rời rạc nếu chúng thuộc các khái niệm khác nhau.

## 4. Tách request DTO khỏi search criteria

Request DTO là hợp đồng HTTP. Search criteria là đầu vào của use case. Hai kiểu này có thể giống nhau lúc đầu nhưng không nhất thiết phải trùng nhau.

Ví dụ:

~~~java
public record ProductSearchRequest(
        String q,
        String category,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Integer page,
        Integer size,
        String sort
) {
}
~~~

Controller chuyển request sang criteria:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductSearchController {

    private final ProductSearchService searchService;

    public ProductSearchController(ProductSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping("/search")
    public ProductSearchResponse search(ProductSearchRequest request) {
        ProductSearchCriteria criteria =
                ProductSearchRequestMapper.toCriteria(request);

        return searchService.search(criteria);
    }
}
~~~

Mapper có thể chuẩn hóa giá trị mặc định và chuyển sort string sang enum. Tuy nhiên, các policy phụ thuộc user/tenant phải được lấy từ security context đã xác thực trong service hoặc một authorization component đáng tin cậy.

Không nhận raw Query DSL, index name hoặc field name tùy ý từ client rồi đưa thẳng vào Elasticsearch. Điều đó làm API phụ thuộc implementation và có thể mở ra truy vấn quá rộng hoặc truy cập sai phạm vi dữ liệu.

## 5. Search service điều phối use case

Service chịu trách nhiệm áp dụng quy tắc nghiệp vụ và điều phối repository/adapter.

Ví dụ:

~~~java
@Service
public class ProductSearchService {

    private final ProductSearchRepository searchRepository;
    private final CurrentTenantProvider tenantProvider;

    public ProductSearchService(
            ProductSearchRepository searchRepository,
            CurrentTenantProvider tenantProvider
    ) {
        this.searchRepository = searchRepository;
        this.tenantProvider = tenantProvider;
    }

    public ProductSearchResponse search(ProductSearchCriteria criteria) {
        validate(criteria);

        String tenantId = tenantProvider.requiredTenantId();

        ProductSearchCriteria scopedCriteria =
                criteria.withTenantId(tenantId);

        ProductSearchResult result =
                searchRepository.search(scopedCriteria);

        return ProductSearchResponse.from(result);
    }

    private void validate(ProductSearchCriteria criteria) {
        if (criteria.minPrice() != null
                && criteria.maxPrice() != null
                && criteria.minPrice().compareTo(criteria.maxPrice()) > 0) {
            throw new InvalidProductSearchException(
                    "minPrice must not exceed maxPrice"
            );
        }
    }
}
~~~

Đoạn code minh họa một criteria có phương thức `withTenantId`; có thể triển khai bằng record bổ sung tenant hoặc một criteria nội bộ khác.

Service nên:

- Xác thực quan hệ giữa các filter.
- Áp dụng tenant/ownership scope bắt buộc.
- Giới hạn page size và sort.
- Chọn use case/search mode.
- Gọi adapter phù hợp.
- Chuyển kết quả thành response contract.
- Ánh xạ lỗi kỹ thuật sang lỗi ứng dụng ở ranh giới thích hợp.

Service không nên chứa hàng trăm dòng builder Query DSL nếu query logic có thể tách riêng. Cũng không nên biến service thành một proxy chỉ gọi repository nếu không có orchestration hoặc policy nào.

## 6. Khi nào chỉ cần derived repository method?

Derived query method phù hợp với điều kiện đơn giản và ít thay đổi.

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByStatus(String status);

    List<ProductDocument> findByStatusAndCategory(
            String status,
            String category
    );

    List<ProductDocument> findByCategoryAndPriceBetween(
            String category,
            BigDecimal min,
            BigDecimal max
    );

    long countByStatus(String status);
}
~~~

Ưu điểm:

- Ít code.
- Tên method thể hiện điều kiện truy vấn.
- Dễ hiểu với query method đơn giản.
- Phù hợp CRUD và lookup theo thuộc tính.

Giới hạn:

- Tên method dài khi nhiều điều kiện.
- Khó biểu diễn nhiều nhánh OR lồng nhau.
- Khó quản lý nhiều filter tùy chọn.
- Không phải nơi tốt để chứa scoring, nested query hoặc aggregation phức tạp.
- Có thể khó giữ ổn định khi query cần nhiều metadata.

Một dấu hiệu nên chuyển sang custom search adapter là method bắt đầu có nhiều nhánh điều kiện hoặc tên method không còn diễn đạt được ý nghĩa một cách rõ ràng.

Đừng tạo method cho mọi tổ hợp filter như `findByStatusAndCategoryAndMinPriceAndMaxPriceAndBrandAnd...`. Khi filter tùy chọn tăng, một query builder có cấu trúc thường dễ bảo trì hơn.

## 7. Repository interface kết hợp custom fragment

Spring Data cho phép mở rộng repository bằng custom fragment. Đây là cách tốt để giữ API repository quen thuộc nhưng đặt truy vấn phức tạp trong implementation riêng.

Khai báo fragment:

~~~java
public interface ProductSearchRepository {

    ProductSearchResult search(ProductSearchCriteria criteria);
}
~~~

Repository chính:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchRepository {
}
~~~

Implementation của fragment:

~~~java
@Repository
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;
    private final ProductSearchQueryBuilder queryBuilder;

    public ProductSearchRepositoryImpl(
            ElasticsearchOperations operations,
            ProductSearchQueryBuilder queryBuilder
    ) {
        this.operations = operations;
        this.queryBuilder = queryBuilder;
    }

    @Override
    public ProductSearchResult search(ProductSearchCriteria criteria) {
        Query query = queryBuilder.build(criteria);

        SearchHits<ProductDocument> hits =
                operations.search(
                        query,
                        ProductDocument.class,
                        IndexCoordinates.of("products")
                );

        return ProductSearchResult.from(hits);
    }
}
~~~

Tên implementation phải tuân theo quy ước fragment discovery của Spring Data và cấu hình repository trong dự án. Với fragment có tên `ProductSearchRepository`, implementation thường là `ProductSearchRepositoryImpl`. Nếu dự án dùng repository postfix hoặc package cấu hình riêng, cần đồng bộ tên theo convention đó.

Cách tổ chức này giúp:

- Interface repository công khai use case tìm kiếm.
- Implementation sở hữu chi tiết Elasticsearch.
- Builder có thể unit test độc lập.
- Service không cần biết `NativeQuery` hoặc Query DSL.

Nếu custom fragment được đặt riêng trong repository chính, tránh tạo nhiều fragment có tên gần giống nhưng cùng chịu trách nhiệm cho một truy vấn.

## 8. Tách search repository khỏi write repository khi có lý do

Không bắt buộc mọi ứng dụng phải có hai repository. Nhưng khi search projection có nhiều query đặc thù và đường ghi có vòng đời khác, tách interface có thể giúp ranh giới rõ hơn.

Ví dụ:

~~~java
public interface ProductDocumentWriter {

    void index(ProductDocument document);

    void delete(String productId);
}
~~~

~~~java
public interface ProductSearchReader {

    ProductSearchResult search(ProductSearchCriteria criteria);

    Optional<ProductSearchView> findViewById(String productId);
}
~~~

Implementation có thể dùng chung `ElasticsearchOperations` nhưng expose các khả năng khác nhau cho service.

Lợi ích:

- Search service không vô tình gọi delete/index.
- Writer không phụ thuộc vào API tìm kiếm.
- Có thể gắn credential hoặc client khác nhau nếu security model yêu cầu.
- Test doubles nhỏ hơn và diễn đạt đúng nhu cầu use case.

Không tách chỉ vì muốn có nhiều interface. Nếu hệ thống nhỏ và một `ProductRepository` đã đủ rõ, thêm abstraction có thể làm tăng indirection không cần thiết.

## 9. Query builder nên là pure component

Một query builder tốt nhận criteria và trả query. Nó không:

- Đọc request HTTP.
- Đọc SecurityContext trực tiếp.
- Gọi Elasticsearch.
- Ghi log toàn bộ source/query nhạy cảm.
- Tự quyết định user có được truy cập tenant nào.
- Giữ state giữa các lần gọi.

Ví dụ:

~~~java
@Component
public class ProductSearchQueryBuilder {

    public Query build(ProductSearchCriteria criteria) {
        return Query.of(query -> query.bool(bool -> {
            bool.filter(filter -> filter.term(term -> term
                    .field("status")
                    .value("PUBLISHED")
            ));

            if (criteria.category() != null) {
                bool.filter(filter -> filter.term(term -> term
                        .field("category")
                        .value(criteria.category())
                ));
            }

            if (criteria.minPrice() != null
                    || criteria.maxPrice() != null) {
                bool.filter(filter -> filter.range(range -> range
                        .number(number -> {
                            number.field("price");

                            if (criteria.minPrice() != null) {
                                number.gte(
                                        criteria.minPrice().doubleValue()
                                );
                            }

                            if (criteria.maxPrice() != null) {
                                number.lte(
                                        criteria.maxPrice().doubleValue()
                                );
                            }

                            return number;
                        })
                ));
            }

            return bool;
        }));
    }
}
~~~

Đây là cách minh họa query builder theo Elasticsearch Java API Client được Spring Data Elasticsearch tích hợp ở các phiên bản hiện đại. Lambda builder có thể cần điều chỉnh theo phiên bản client cụ thể của dự án.

Một số nguyên tắc:

- Điều kiện bắt buộc dùng `filter` nếu không cần scoring.
- Điều kiện full-text thường dùng `must` hoặc `should` tùy semantics.
- Chỉ thêm clause khi criteria có giá trị.
- Không thêm range rỗng hoặc term với chuỗi blank.
- Field name phải do server kiểm soát.
- Query builder không tự thêm tenant scope nếu tenant chưa được xác thực và đưa vào criteria một cách đáng tin cậy.

## 10. Bắt buộc đưa tenant scope vào truy vấn

Trong ứng dụng multi-tenant dùng chung index, tenant filter là điều kiện bảo mật. Không được để filter này trở thành một điều kiện tùy chọn mà controller có thể quên truyền.

Criteria nội bộ nên chứa tenant đã được xác thực:

~~~java
public record ProductSearchCriteria(
        String tenantId,
        String text,
        String category,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        int page,
        int size,
        ProductSort sort
) {
}
~~~

Builder luôn thêm tenant filter:

~~~java
bool.filter(filter -> filter.term(term -> term
        .field("tenantId")
        .value(criteria.tenantId())
));
~~~

Không lấy tenant ID từ query parameter nếu chưa kiểm tra quyền truy cập tenant đó. Tốt nhất, SearchService lấy tenant từ principal/authorization service và tạo criteria nội bộ.

Với query theo nhiều index hoặc alias, xác minh tenant field có mặt và mapping thống nhất trên mọi index được tìm. Một alias trỏ sang index cũ thiếu tenant mapping có thể làm truy vấn hoặc authorization sai.

## 11. Phân biệt must, filter và should

Query builder nên phản ánh semantics tìm kiếm, không chỉ gom mọi điều kiện vào một bool.

| Clause | Dùng khi | Ảnh hưởng score |
|---|---|---|
| `must` | Điều kiện bắt buộc và có liên quan scoring | Có |
| `filter` | Điều kiện bắt buộc nhưng không cần score | Không |
| `should` | Điều kiện tăng độ phù hợp hoặc một nhánh match tùy minimum_should_match | Có |
| `must_not` | Loại document không mong muốn | Không |

Ví dụ tìm từ khóa và lọc theo trạng thái/danh mục:

~~~java
Query query = Query.of(q -> q.bool(bool -> bool
        .must(must -> must.multiMatch(multi -> multi
                .query(criteria.text())
                .fields("name^3", "description")
        ))
        .filter(filter -> filter.term(term -> term
                .field("status")
                .value("PUBLISHED")
        ))
        .filter(filter -> filter.term(term -> term
                .field("tenantId")
                .value(criteria.tenantId())
        ))
));
~~~

`name^3` tăng trọng số field name so với description. Các điều kiện status/tenant nằm trong filter vì chúng là ràng buộc, không phải tín hiệu xếp hạng.

Nếu `text` có thể null hoặc blank, builder cần bỏ clause full-text thay vì gửi query rỗng. Nếu API yêu cầu có từ khóa, validate ở service trước khi gọi builder.

## 12. Không để raw field name và sort field từ client đi vào query

Client có thể gửi:

~~~http
GET /api/products/search?sort=internalCost,desc
~~~

Nếu code đưa thẳng giá trị `internalCost` vào sort builder, API đã để client điều khiển chi tiết mapping. Điều này có thể gây truy vấn tốn kém hoặc làm lộ cấu trúc dữ liệu nội bộ qua behavior.

Dùng enum/allowlist:

~~~java
public enum ProductSort {
    RELEVANCE,
    NAME_ASC,
    PRICE_ASC,
    PRICE_DESC,
    UPDATED_DESC
}
~~~

Chuyển enum sang sort server-side:

~~~java
private Sort toSort(ProductSort sort) {
    return switch (sort) {
        case NAME_ASC -> Sort.by(
                Sort.Order.asc("name.keyword"),
                Sort.Order.asc("productId")
        );
        case PRICE_ASC -> Sort.by(
                Sort.Order.asc("price"),
                Sort.Order.asc("productId")
        );
        case PRICE_DESC -> Sort.by(
                Sort.Order.desc("price"),
                Sort.Order.asc("productId")
        );
        case UPDATED_DESC -> Sort.by(
                Sort.Order.desc("updatedAt"),
                Sort.Order.asc("productId")
        );
        case RELEVANCE -> Sort.unsorted();
    };
}
~~~

Với relevance, Elasticsearch score thường quyết định thứ tự mặc định theo query; nếu dùng explicit score sort hoặc tie-breaker, cấu hình theo semantics của use case.

Sort field phải tồn tại và có mapping hỗ trợ sort, thường là keyword/numeric/date. Không sort trực tiếp trên text field nếu không có field phù hợp.

## 13. Chuẩn hóa phân trang trong một nơi

Page number và size là input từ client nhưng giới hạn là policy của service.

~~~java
public record SearchPage(int page, int size) {

    public static SearchPage normalize(
            Integer requestedPage,
            Integer requestedSize
    ) {
        int page = requestedPage == null
                ? 0
                : Math.max(0, requestedPage);

        int requested = requestedSize == null
                ? 25
                : requestedSize;

        int size = Math.min(Math.max(requested, 1), 100);

        return new SearchPage(page, size);
    }

    public Pageable toPageable(Sort sort) {
        return PageRequest.of(page, size, sort);
    }
}
~~~

Dùng một component chuẩn hóa để các endpoint không tự chọn default và max size khác nhau.

Với phân trang `from/size`, cần giới hạn độ sâu và cân nhắc `max_result_window`. Với export sâu, dùng `search_after` và PIT thay vì cho client gửi page number rất lớn.

Sort nên ổn định và có tie-breaker duy nhất. Nếu dữ liệu thay đổi trong lúc người dùng chuyển trang, offset pagination vẫn có thể lặp hoặc bỏ sót document; PIT/search_after cần thiết khi yêu cầu snapshot nhất quán.

## 14. Builder cho cả query và pageable

Có thể tách query filter và page/sort thành hai component:

- `ProductSearchQueryBuilder`: tạo điều kiện query.
- `ProductSearchPageFactory`: chuẩn hóa page size và sort.

Ví dụ orchestration trong adapter:

~~~java
public ProductSearchResult search(ProductSearchCriteria criteria) {
    Query query = queryBuilder.build(criteria);

    Pageable pageable = pageFactory.create(
            criteria.page(),
            criteria.size(),
            criteria.sort()
    );

    NativeQuery nativeQuery = NativeQuery.builder()
            .withQuery(query)
            .withPageable(pageable)
            .build();

    SearchHits<ProductDocument> hits =
            operations.search(
                    nativeQuery,
                    ProductDocument.class,
                    IndexCoordinates.of("products")
            );

    return ProductSearchResult.from(hits);
}
~~~

Cách tách này có lợi khi pagination/sort được dùng ở nhiều search use case. Nếu chỉ một query nhỏ, có thể giữ trong một builder để tránh chia lớp quá mức.

Không để hai builder cùng thay đổi một `NativeQuery.Builder` mutable dùng chung. Mỗi lần tìm kiếm nên tạo query object mới, không giữ builder trong singleton bean.

## 15. SearchHit, SearchHits và response DTO

Search result thường chứa nhiều metadata ngoài entity:

- Nội dung document.
- ID, index.
- Score.
- Sort values.
- Highlight fields.
- Matched queries.
- Total hits và relation.
- Aggregations ở cấp kết quả.

Nếu service chỉ trả `List<ProductDocument>`, một số metadata sẽ bị bỏ đi. Nếu API cần score/highlight/total hit, adapter nên giữ `SearchHits<T>` đủ lâu để map chúng.

Ví dụ response:

~~~java
public record ProductSearchItem(
        String productId,
        String name,
        BigDecimal price,
        Float score,
        Map<String, List<String>> highlights
) {
}
~~~

~~~java
public record ProductSearchResponse(
        List<ProductSearchItem> items,
        long totalHits,
        int page,
        int size,
        boolean hasMore
) {
}
~~~

Mapper:

~~~java
private ProductSearchItem toItem(SearchHit<ProductDocument> hit) {
    ProductDocument source = hit.getContent();

    return new ProductSearchItem(
            source.getProductId(),
            source.getName(),
            source.getPrice(),
            hit.getScore(),
            hit.getHighlightFields()
    );
}
~~~

Tên kiểu highlight/score và cách chuyển đổi cần theo version Spring Data Elasticsearch đang dùng. Không trả thẳng entity persistence nếu API cần một contract ổn định hoặc cần ẩn field nội bộ.

## 16. Projection riêng cho search result

Search result có thể cần ít field hơn document dùng để ghi.

Ví dụ:

~~~java
public class ProductDocument {

    @Id
    private String id;

    private String productId;
    private String tenantId;
    private String name;
    private String description;
    private BigDecimal price;
    private String status;
    private String internalNotes;
    private Instant updatedAt;
}
~~~

Projection cho kết quả:

~~~java
public record ProductSearchView(
        String productId,
        String name,
        BigDecimal price
) {
}
~~~

Có thể dùng projection/DTO mapping hoặc source filtering để chỉ lấy field cần thiết. DTO phía ứng dụng không tự giảm network payload nếu Elasticsearch vẫn gửi toàn bộ `_source`; cần source filter khi mục tiêu là giảm dữ liệu truyền về.

Giữ mapping document và API response tách nhau để thay đổi analyzer, index field hoặc cấu trúc source không bắt buộc phải đổi public API.

## 17. Khi nào dùng NativeQuery?

`NativeQuery` là lựa chọn khi query cần tính năng Elasticsearch hoặc Query DSL phức tạp hơn những gì derived method diễn đạt gọn.

Ví dụ use case có:

- Full-text multi-match.
- Filter nhiều điều kiện tùy chọn.
- Nested query.
- Function score.
- Highlight.
- Aggregation.
- Source filtering.
- Search after.
- Explicit sort và track total hits.

Một query có thể được xây từ các phần:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(queryBuilder.build(criteria))
        .withPageable(pageFactory.create(criteria))
        .withSourceFilter(sourceFilterFactory.forProductList())
        .withTrackTotalHits(true)
        .build();
~~~

Tên và kiểu các builder method có thể khác theo version. Kiểm tra API của Spring Data Elasticsearch/Elasticsearch Java API Client trong dependency thực tế.

Không dùng `NativeQuery` cho mọi truy vấn chỉ vì nó linh hoạt. Repository method đơn giản thường dễ đọc và ít code hơn.

## 18. Query specification và composition

Khi có nhiều filter tái sử dụng, có thể tạo các hàm nhỏ để xây clause.

Ví dụ:

~~~java
private Query statusFilter(String status) {
    return Query.of(q -> q.term(t -> t
            .field("status")
            .value(status)
    ));
}

private Query categoryFilter(String category) {
    return Query.of(q -> q.term(t -> t
            .field("category")
            .value(category)
    ));
}
~~~

Hoặc mỗi specification trả về một bool clause, rồi builder kết hợp chúng. Cách này giúp test riêng từng filter.

Không nên tạo abstraction quá chung chung như một DSL tự chế bao phủ mọi Query DSL của Elasticsearch. Abstraction tốt cần phản ánh các khái niệm nghiệp vụ có ý nghĩa: published products, tenant scope, price range, text relevance.

Nếu mỗi filter chỉ dùng một lần và rất ngắn, giữ inline trong builder có thể rõ hơn việc tạo hàng chục class specification.

## 19. Truy vấn có nhiều nhánh OR

Ví dụ tìm sản phẩm nếu:

- Tên khớp từ khóa; hoặc
- SKU khớp chính xác; đồng thời
- Status phải là PUBLISHED và tenant phải đúng.

Có thể dùng `should` cho nhánh OR và `filter` cho điều kiện bắt buộc:

~~~java
Query query = Query.of(q -> q.bool(bool -> bool
        .filter(filter -> filter.term(term -> term
                .field("status")
                .value("PUBLISHED")
        ))
        .filter(filter -> filter.term(term -> term
                .field("tenantId")
                .value(criteria.tenantId())
        ))
        .should(should -> should.match(match -> match
                .field("name")
                .query(criteria.text())
        ))
        .should(should -> should.term(term -> term
                .field("sku")
                .value(criteria.text())
        ))
        .minimumShouldMatch("1")
));
~~~

`minimumShouldMatch("1")` yêu cầu ít nhất một nhánh should khớp trong ngữ cảnh bool này. Nếu không cấu hình, semantics mặc định của should phụ thuộc việc bool có must/filter hay không; đừng dựa vào mặc định nếu ý nghĩa OR là bắt buộc.

Đây là ví dụ query composition. Cần xác nhận field `sku` là keyword và `name` có analyzer phù hợp.

## 20. Nested query và mapping cần khớp nhau

Nếu document có mảng object cần truy vấn độc lập theo từng phần tử, mapping có thể cần `nested`. Ví dụ sản phẩm có các biến thể:

~~~json
{
  "variants": [
    {
      "color": "black",
      "size": "M",
      "stock": 10
    },
    {
      "color": "white",
      "size": "L",
      "stock": 0
    }
  ]
}
~~~

Nếu cần tìm một biến thể vừa có màu black vừa có stock lớn hơn 0, nested query giữ điều kiện trong cùng một object:

~~~java
Query nestedQuery = Query.of(q -> q.nested(nested -> nested
        .path("variants")
        .query(inner -> inner.bool(bool -> bool
                .filter(filter -> filter.term(term -> term
                        .field("variants.color")
                        .value("black")
                ))
                .filter(filter -> filter.range(range -> range
                        .number(number -> number
                                .field("variants.stock")
                                .gt(0.0)
                        )
                ))
        ))
));
~~~

Nếu mapping là object thường thay vì nested, Elasticsearch có thể flatten các giá trị và query có thể match chéo giữa các phần tử. Query builder không thể sửa lỗi mapping; mapping và semantics phải được thiết kế cùng nhau.

## 21. Highlight và aggregation thuộc search adapter

Khi endpoint cần highlight, aggregation hoặc suggest, adapter có thể dùng `NativeQuery` và trả về một result model giàu metadata.

Không nên nhồi aggregation parsing vào controller. Mapper hoặc một component chuyên trách nên chuyển aggregation response thành DTO nghiệp vụ.

Ví dụ response aggregation:

~~~java
public record CategoryCount(
        String category,
        long count
) {
}
~~~

Search result có thể chứa:

- Danh sách sản phẩm.
- Tổng số hit.
- Số lượng theo category.
- Highlight snippets.
- Giá thấp nhất/cao nhất.

Nếu endpoint chỉ cần aggregation, đặt số hit bằng 0 hoặc không lấy source hits. Nếu cần cả hits và aggregation, page size nên nhỏ và có chủ đích.

## 22. Chọn IndexCoordinates và alias ở adapter

Tên index vật lý là chi tiết triển khai. Ứng dụng thường nên truy cập qua alias như `products` thay vì gắn cứng `products-v1` trong nhiều service.

~~~java
private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products");
~~~

Adapter dùng alias:

~~~java
SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class, PRODUCTS);
~~~

Alias giúp deployment chuyển từ `products-v1` sang `products-v2` mà service không phải thay đổi code.

Nếu có nhiều tenant index hoặc nhiều region, cách resolve index phải nằm trong một component có policy rõ ràng. Không cho client gửi index name tùy ý.

## 23. Không để query builder trở thành nơi chứa authorization ngầm

Query builder có thể thêm tenant filter, soft-delete filter hoặc trạng thái bắt buộc, nhưng cần có hợp đồng rõ ràng về nguồn criteria.

Một thiết kế dễ hiểu:

~~~text
Authenticated principal
       |
       v
Authorization / Tenant provider
       |
       v
Search service creates scoped criteria
       |
       v
Query builder adds mandatory scope filters
       |
       v
Search adapter executes query
~~~

Các quy tắc:

- Tenant ID lấy từ identity đã xác thực.
- Permission được kiểm tra ở service/policy layer.
- Builder không tự đọc HTTP request hoặc thread-local security context.
- Mọi đường gọi builder đều phải cung cấp scope hợp lệ.
- Không có overload “search all tenants” cho endpoint người dùng thông thường.
- Test xác nhận tenant filter luôn xuất hiện.

Nếu có tác vụ quản trị cần tìm trên nhiều tenant, hãy tạo một use case riêng với authorization rõ ràng, không dùng tenant null như cách ngầm bỏ filter.

## 24. Cache tìm kiếm ở service boundary

Một số truy vấn đọc có thể cache, nhưng cache key phải bao gồm toàn bộ điều kiện ảnh hưởng kết quả:

- Tenant ID.
- Query text đã chuẩn hóa.
- Category/status/price filters.
- Sort.
- Page/cursor.
- Locale hoặc analyzer mode nếu có.
- Quyền/visibility scope nếu ảnh hưởng dữ liệu.

Không cache theo query text đơn lẻ nếu cùng từ khóa nhưng tenant khác nhau. Điều đó có thể làm lộ dữ liệu giữa tenant.

Cache invalidation cần theo event cập nhật document/index. Vì Elasticsearch thường là projection eventual consistency, cache TTL và invalidation phải phù hợp với độ trễ đồng bộ.

Không cache toàn bộ `SearchHits` nếu object chứa dữ liệu nội bộ hoặc metadata không cần thiết. Ưu tiên cache response DTO nhỏ đã áp dụng authorization.

## 25. Error handling ở ranh giới adapter

Adapter có thể giữ chi tiết Elasticsearch và chuyển lỗi sang loại lỗi kỹ thuật/ứng dụng có ý nghĩa:

- Query sai do bug lập trình: lỗi cần sửa, không retry.
- 401/403: cấu hình credential/role.
- 429/503: có thể retry có giới hạn theo policy.
- Timeout: kết quả phụ thuộc loại operation và idempotency.
- Mapping error: dữ liệu hoặc index mapping không tương thích.
- Partial shard failure: cần quyết định có chấp nhận kết quả một phần không.

Controller không nên bắt mọi `Exception` rồi trả danh sách rỗng. Search thất bại khác với search thành công nhưng không có kết quả.

Service có thể trả response rỗng khi query hợp lệ không match document; adapter cần phát lỗi nếu Elasticsearch request thất bại. Không nuốt lỗi transport thành `List.of()`.

## 26. Tổ chức package theo feature

Một cấu trúc package ví dụ:

~~~text
com.example.catalog
├── product
│   ├── api
│   │   ├── ProductSearchController.java
│   │   ├── ProductSearchRequest.java
│   │   └── ProductSearchResponse.java
│   ├── application
│   │   ├── ProductSearchService.java
│   │   ├── ProductSearchCriteria.java
│   │   └── ProductSort.java
│   ├── search
│   │   ├── ProductSearchRepository.java
│   │   ├── ProductSearchRepositoryImpl.java
│   │   ├── ProductSearchQueryBuilder.java
│   │   ├── ProductSearchPageFactory.java
│   │   └── ProductSearchResultMapper.java
│   ├── persistence
│   │   ├── ProductRepository.java
│   │   └── ProductDocument.java
│   └── domain
│       └── Product.java
└── shared
    ├── security
    └── observability
~~~

Không nhất thiết phải có đủ mọi package/class ngay từ đầu. Khi feature nhỏ, có thể đặt query builder và custom repository cạnh nhau. Khi nhiều use case phát triển, tách theo trách nhiệm và feature sẽ dễ tìm hơn tổ chức toàn bộ ứng dụng theo một thư mục `controller`, `service`, `repository` khổng lồ.

Điều quan trọng là tránh dependency ngược:

- API không phụ thuộc Elasticsearch client.
- Domain không phụ thuộc Query DSL.
- Query builder không phụ thuộc controller.
- Search adapter là nơi biết Elasticsearch-specific API.
- Service phụ thuộc abstraction phù hợp với use case.

## 27. Kiểm thử từng lớp

### Unit test cho request/criteria mapper

Kiểm tra default page, size, sort enum, khoảng giá và input không hợp lệ. Không cần Elasticsearch cho những quy tắc thuần Java.

### Unit test cho query builder

Kiểm tra criteria tạo đúng semantics:

- Tenant filter luôn có.
- Status bắt buộc.
- Category chỉ thêm khi có giá trị.
- Range chỉ thêm bound đã cung cấp.
- Blank text không tạo full-text clause.
- OR branch có minimum_should_match phù hợp.
- Field sort nằm trong allowlist.

Có thể serialize query object thành JSON trong test theo API client version để kiểm tra DSL, hoặc kiểm tra object structure bằng helper phù hợp.

### Unit test cho search service

Mock search port/repository và tenant provider để xác nhận:

- Tenant lấy từ principal, không lấy từ request body.
- Page size được chuẩn hóa.
- Validation được áp dụng.
- Service gọi adapter với scoped criteria.
- Lỗi adapter không bị biến thành kết quả rỗng.

### Integration test với Elasticsearch

Dùng Testcontainers hoặc test cluster tương thích để xác nhận:

- Mapping và analyzer thực tế.
- Repository derived methods.
- Query builder tạo kết quả đúng.
- Sort/pagination.
- Highlight/aggregation nếu dùng.
- Alias/index coordinates.
- Source filtering/projection.
- Tenant isolation.
- Index version/mapping compatibility.

Unit test chứng minh builder tạo object mong đợi; integration test chứng minh Elasticsearch thực sự hiểu query và mapping đó.

## 28. Kiểm thử tenant isolation và sort allowlist

Một test quan trọng phải chứng minh hai tenant không nhìn thấy dữ liệu của nhau:

~~~java
@Test
void searchOnlyReturnsDocumentsFromAuthenticatedTenant() {
    // Arrange:
    // - Index product A thuộc tenant-1.
    // - Index product B thuộc tenant-2.
    // - CurrentTenantProvider trả tenant-1.
    //
    // Act:
    // - Gọi ProductSearchService.search(criteria).
    //
    // Assert:
    // - Chỉ product A xuất hiện.
}
~~~

Test sort:

~~~java
@Test
void rejectsUnsupportedSortField() {
    // Client gửi sort field không nằm trong ProductSort allowlist.
    // Request mapper trả lỗi validation hoặc dùng default theo API contract.
}
~~~

Không chỉ test builder với tenant ID bất kỳ. Cần test service lấy tenant từ security context/provider để tránh lỗi wiring khiến scope bị bỏ qua.

## 29. Khi nào cần CQRS hoặc read model riêng?

Một ứng dụng có thể dùng cùng document cho cả write và search lúc đầu. Khi search use case ngày càng phức tạp, có thể tách:

- Write model: mô hình nghiệp vụ chuẩn trong database.
- Search projection: document Elasticsearch tối ưu cho truy vấn.
- Search API: chỉ đọc projection.
- Event/CDC pipeline: đồng bộ thay đổi sang projection.

Điều này phù hợp khi search cần denormalize dữ liệu từ nhiều bảng, analyzer riêng, nested structure hoặc aggregation đặc thù.

Không cần áp dụng CQRS chỉ vì có Elasticsearch. Nếu một repository document đơn giản đáp ứng use case, giữ kiến trúc gọn. Tách read model khi có lợi ích rõ về query, scaling, ownership hoặc release cycle.

## 30. Những lỗi thiết kế thường gặp

### Controller tự build Query DSL

Controller biết field name, nested path và Elasticsearch API. Điều này làm API gắn chặt với mapping và khó test. Chuyển query construction sang builder/adapter.

### Service chứa toàn bộ query construction

Service trở nên dài và trộn policy nghiệp vụ với cú pháp Elasticsearch. Tách builder khi query có nhiều nhánh hoặc cần tái sử dụng.

### Tạo builder cho mọi repository method

Một method đơn giản như `findByStatus` không cần thêm nhiều lớp chuyển tiếp. Dùng derived method khi nó đủ diễn đạt.

### Repository method có quá nhiều tổ hợp filter

Tên method dài và khó thay đổi. Dùng criteria object và custom search implementation cho filter tùy chọn.

### Query builder tự đọc SecurityContext

Builder khó test và có dependency ẩn. Service/policy layer lấy tenant đã xác thực rồi truyền vào criteria.

### Cho client truyền field sort hoặc index name tùy ý

Có thể tạo query không an toàn hoặc tốn kém. Dùng enum/allowlist và alias do server quản lý.

### Quên tie-breaker khi sort

Kết quả có cùng sort value có thể đổi thứ tự giữa các trang. Thêm field duy nhất và dùng PIT/search_after nếu cần snapshot.

### DTO được cho là tự giảm source payload

DTO chỉ giới hạn field được map. Muốn giảm bytes truyền về cần source filtering.

### Trả entity trực tiếp cho API

API bị gắn chặt với mapping document và có thể lộ field nội bộ. Dùng response DTO.

### Nuốt lỗi Elasticsearch thành kết quả rỗng

Client không phân biệt được "không có kết quả" và "search thất bại". Giữ error semantics rõ ràng.

### Dùng alias/index name không nhất quán

Một số service gọi alias, service khác hard-code version index. Đưa index coordinates vào adapter/configuration.

### Tách quá nhiều abstraction

Mỗi interface/class chỉ chuyển tiếp một lệnh khiến việc lần theo code khó hơn. Chỉ tách khi có trách nhiệm, policy hoặc khả năng kiểm thử riêng.

## 31. Quy trình thiết kế một search use case

Khi thêm một endpoint tìm kiếm mới:

1. Viết rõ use case và response contract.
2. Xác định field filter, text search, sort, page và metadata cần trả.
3. Phân biệt điều kiện nghiệp vụ bắt buộc với filter tùy chọn.
4. Xác định tenant/ownership scope từ authenticated principal.
5. Nếu query đơn giản, dùng repository derived method.
6. Nếu query có nhiều nhánh hoặc metadata, dùng custom repository fragment và ElasticsearchOperations.
7. Tạo criteria object độc lập với HTTP và Query DSL.
8. Tạo query builder pure, không I/O và không đọc security context.
9. Chuẩn hóa page size và sort bằng allowlist.
10. Dùng alias/IndexCoordinates do server quản lý.
11. Giữ SearchHits khi cần score, highlight, sort values hoặc total-hit metadata.
12. Map sang response DTO; source filter nếu cần giảm payload.
13. Phân loại lỗi ở adapter và giữ error semantics.
14. Unit test criteria, policy và query builder.
15. Integration test trên Elasticsearch thật cho mapping/query semantics.
16. Test tenant isolation, sort validation, pagination và error behavior.
17. Thêm log/metrics có request ID nhưng không ghi raw query/source nhạy cảm.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/query-methods.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Custom repository implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Elasticsearch — Query DSL](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
- [Elasticsearch — Bool query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html)
- [Elasticsearch — Pagination](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Spring Framework — Application architecture](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)

## Kết luận

Tổ chức tìm kiếm bền vững bằng cách để controller xử lý HTTP, service áp dụng use case và policy, repository/search adapter thực hiện I/O, query builder chuyển criteria thành Query DSL, còn mapper tạo response DTO. Dùng derived repository method cho query đơn giản; chuyển sang custom fragment với `ElasticsearchOperations`/`NativeQuery` khi cần filter động, nested query, scoring, highlight hoặc aggregation. Criteria nên độc lập với HTTP và Query DSL; tenant scope phải được lấy từ identity đã xác thực; sort field phải nằm trong allowlist; pagination cần giới hạn và thứ tự ổn định. Tách lớp khi trách nhiệm thực sự khác nhau, tránh cả controller chứa Query DSL lẫn việc tạo abstraction chỉ để chuyển tiếp một lời gọi.
