# Bổ sung sắp xếp, phân trang và highlight cho kết quả

Một chức năng tìm kiếm hữu ích cần kiểm soát thứ tự kết quả, chia kết quả thành các trang và làm nổi bật phần nội dung khớp với truy vấn. Spring Data Elasticsearch cung cấp các abstraction để tạo sort, pageable query và đọc metadata từ search hit. Elasticsearch cung cấp các semantics phía server như field sorting, offset pagination, search_after và highlighting.

Ba khả năng này liên quan đến nhau nhưng có mục đích riêng:

- **Sắp xếp** xác định thứ tự kết quả. Search mặc định thường xếp theo relevance score khi query có tính điểm.
- **Phân trang** giới hạn số kết quả trả về và xác định vị trí tiếp theo.
- **Highlight** trả các đoạn text trong field phù hợp với query để giao diện hiển thị vì sao document được tìm thấy.

Bài học này xây dựng một search flow hoàn chỉnh: nhận request DTO, kiểm tra sort/page input, tạo query bằng Spring Data Elasticsearch, lấy SearchHits, map highlight và metadata thành response DTO, rồi kiểm thử các trường hợp biên. Phần cuối trình bày khi nào nên chuyển từ offset pagination sang cursor với search_after.

## 1. Luồng tìm kiếm tổng thể

Một endpoint tìm kiếm không nên để client gửi tên field Elasticsearch hoặc Query DSL tùy ý. Client chọn các tùy chọn nghiệp vụ được API công bố; server ánh xạ chúng sang query, sort và highlight tương ứng.

~~~text
HTTP request
     |
     v
ProductSearchRequest
     |
     v
Validation + default values
     |
     v
ProductSearchCriteria
     |
     v
Query factory
     |
     +---- Query filters
     +---- Sort options
     +---- Pageable / cursor
     +---- Highlight fields
     |
     v
ElasticsearchOperations
     |
     v
SearchHits<Product>
     |
     v
Response mapper
     |
     +---- Product DTOs
     +---- Pagination metadata
     +---- Sort metadata
     +---- Highlight fragments
     |
     v
HTTP response
~~~

Tách các bước giúp controller không cần biết Elasticsearch Query DSL. Khi mapping hoặc chiến lược phân trang thay đổi, API contract vẫn có thể giữ ổn định.

## 2. Entity và mapping phục vụ sort/highlight

Ví dụ entity sản phẩm:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Dùng làm sort tie-breaker ổn định.
    @Field(type = FieldType.Keyword)
    private String productIdSort;

    // constructors, getters and setters
}
~~~

Mapping tương ứng có thể gồm:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    },
    "description": {
      "type": "text"
    },
    "status": {
      "type": "keyword"
    },
    "category": {
      "type": "keyword"
    },
    "price": {
      "type": "double"
    },
    "createdAt": {
      "type": "date"
    },
    "productIdSort": {
      "type": "keyword"
    }
  }
}
~~~

Field name được mapping là text để full-text search. Subfield name.keyword dùng cho exact match hoặc sort theo toàn bộ tên. Field price và createdAt phù hợp với numeric/date sort. productIdSort là field keyword có giá trị duy nhất để tạo thứ tự ổn định khi các document có cùng giá hoặc thời gian.

Không sort trực tiếp trên field text đã được analyzer tách token. Elasticsearch thường yêu cầu field có doc_values, như keyword, numeric hoặc date. Nếu cần sort theo tên, dùng multi-field keyword được mapping từ đầu.

### Đồng bộ tie-breaker

Nếu dùng productIdSort, cần gán giá trị này khi tạo document và bảo đảm nó ổn định:

~~~java
product.setProductIdSort(product.getId());
~~~

Không dựa vào _id như một field sort thông thường. Elasticsearch có giới hạn đối với việc sort theo _id; hãy dùng một field keyword riêng có doc values khi cần sort ổn định.

Mapping index đã tồn tại không tự thay đổi chỉ vì entity có thêm annotation. Nếu cần multi-field hoặc tie-breaker mới, cập nhật index template và tạo index/migration phù hợp.

## 3. Thiết kế request DTO

Request nên dùng enum cho các trường sort và direction để giới hạn lựa chọn client có thể yêu cầu.

~~~java
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

Request DTO:

~~~java
public record ProductSearchRequest(
    String query,
    String status,
    Integer page,
    Integer size,
    ProductSort sort,
    SortDirection direction,
    Boolean highlight
) {}
~~~

Chuẩn hóa và kiểm tra input trước khi tạo query:

~~~java
public record ProductSearchCriteria(
    String query,
    String status,
    int page,
    int size,
    ProductSort sort,
    SortDirection direction,
    boolean highlight
) {}
~~~

~~~java
@Component
public class ProductSearchCriteriaMapper {

    private static final int DEFAULT_SIZE = 20;
    private static final int MAX_SIZE = 100;

    public ProductSearchCriteria toCriteria(
            ProductSearchRequest request) {

        int page = request.page() == null ? 0 : request.page();
        int size = request.size() == null
            ? DEFAULT_SIZE
            : request.size();

        if (page < 0) {
            throw new InvalidSearchRequestException(
                "page must be zero or greater"
            );
        }

        if (size < 1 || size > MAX_SIZE) {
            throw new InvalidSearchRequestException(
                "size must be between 1 and " + MAX_SIZE
            );
        }

        return new ProductSearchCriteria(
            normalize(request.query()),
            request.status(),
            page,
            size,
            request.sort() == null
                ? ProductSort.RELEVANCE
                : request.sort(),
            request.direction() == null
                ? SortDirection.DESC
                : request.direction(),
            Boolean.TRUE.equals(request.highlight())
        );
    }

    private String normalize(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }
}
~~~

Có thể dùng Bean Validation như @Min, @Max và @Size để từ chối input ở controller boundary. Việc kiểm tra trong criteria mapper vẫn hữu ích nếu criteria được tạo từ nhiều nguồn khác nhau.

Không cho client gửi raw sort field như internalSupplierCode hoặc một script sort tùy ý. Enum công khai là allowlist để server kiểm soát field và chi phí query.

## 4. Xây dựng sort từ allowlist

Sort mapping chuyển enum API sang field Elasticsearch:

~~~java
@Component
public class ProductSortMapper {

    public Sort toSpringSort(ProductSort field, SortDirection direction) {
        Sort.Direction order =
            direction == SortDirection.ASC
                ? Sort.Direction.ASC
                : Sort.Direction.DESC;

        return switch (field) {
            case NAME -> Sort.by(order, "name.keyword")
                .and(Sort.by(Sort.Direction.ASC, "productIdSort"));

            case PRICE -> Sort.by(order, "price")
                .and(Sort.by(Sort.Direction.ASC, "productIdSort"));

            case CREATED_AT -> Sort.by(order, "createdAt")
                .and(Sort.by(Sort.Direction.ASC, "productIdSort"));

            case RELEVANCE -> Sort.by(
                Sort.Order.desc("_score"),
                Sort.Order.asc("productIdSort")
            );
        };
    }
}
~~~

Đây là ví dụ dùng Spring Data Sort. Cách biểu diễn sort score và việc kết hợp score với field sort cần kiểm tra trên release train cụ thể. Với NativeQuery, có thể dùng Elasticsearch Java API Client SortOptions để chỉ định _score và field sort rõ ràng.

### Relevance sort và field sort

- Khi sort theo _score, kết quả ưu tiên document khớp query tốt hơn.
- Khi sort theo price, kết quả theo giá; score không còn là tiêu chí chính.
- Khi sort theo createdAt, kết quả theo thời gian.
- Tie-breaker tạo thứ tự ổn định khi field chính có giá trị trùng.

Nếu query là match_all hoặc filter-only, score có thể không mang ý nghĩa nghiệp vụ. Chọn sort mặc định phù hợp với loại endpoint.

### Missing values

Document có thể thiếu field dùng để sort. Elasticsearch có tùy chọn missing để đặt các document thiếu giá trị lên đầu hoặc cuối. Cần chọn chính sách rõ ràng cho field như price hoặc createdAt.

Nếu mọi document phải có giá hoặc thời gian tạo, có thể enforce ở tầng ghi và kiểm tra mapping/data quality. Đừng để thứ tự của missing value trở thành hành vi ngẫu nhiên mà API không mô tả.

### Nested sort

Nếu sort theo field nằm trong nested object, query cần khai báo nested sort path và filter phù hợp. Sort theo nested field không tương đương sort theo object thông thường. Chỉ dùng khi domain cần thứ tự theo child object cụ thể và có integration test cho mapping nested.

## 5. Phân trang offset với Pageable

Spring Data dùng Pageable để biểu diễn page index, page size và sort.

~~~java
Pageable pageable = PageRequest.of(
    criteria.page(),
    criteria.size(),
    sortMapper.toSpringSort(
        criteria.sort(),
        criteria.direction()
    )
);
~~~

Page index bắt đầu từ 0:

- page = 0, size = 20: yêu cầu 20 kết quả đầu.
- page = 1, size = 20: yêu cầu 20 kết quả tiếp theo.
- page = 2, size = 20: yêu cầu trang thứ ba.

Nếu API muốn page bắt đầu từ 1, chuyển đổi tại request mapper và giữ cùng quy ước ở response. Không để frontend và backend hiểu page index khác nhau.

### Dùng Pageable với repository

Một derived query có thể nhận Pageable:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Page<Product> findByStatus(
        String status,
        Pageable pageable
    );
}
~~~

Caller:

~~~java
Page<Product> page = repository.findByStatus(
    "ACTIVE",
    pageable
);
~~~

Page phù hợp khi cần abstraction phân trang tiêu chuẩn. Tuy nhiên, với search cần highlight, score, aggregations hoặc các metadata đặc thù Elasticsearch, nên dùng SearchHits/SearchPage hoặc ElasticsearchOperations để không làm mất metadata.

### Dùng Pageable với NativeQuery

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ))
    ))
    .withPageable(pageable)
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

NativeQuery giúp kết hợp Query DSL với pageable và các tùy chọn search khác. Các builder method có thể thay đổi theo Spring Data Elasticsearch và Elasticsearch Java API Client version.

## 6. Elasticsearch thực hiện offset pagination như thế nào?

Offset pagination dùng hai tham số:

- from: số hit bỏ qua trước khi bắt đầu trang.
- size: số hit tối đa cần trả về.

Ví dụ trang thứ ba, mỗi trang 20 kết quả:

~~~http
GET /products/_search
{
  "from": 40,
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "sort": [
    {
      "price": "asc"
    },
    {
      "productIdSort": "asc"
    }
  ]
}
~~~

Elasticsearch cần giữ và xử lý candidate results từ các shard để xác định phần kết quả nằm trong khoảng from đến from + size. Khi offset lớn, chi phí và bộ nhớ tăng.

### max_result_window

Elasticsearch thường giới hạn from + size bằng index.max_result_window, mặc định phổ biến là 10.000. Khi request vượt giới hạn, Elasticsearch trả lỗi thay vì cho phép đọc sâu vô hạn.

Không nên tăng giới hạn thật lớn như giải pháp mặc định. Một trang rất sâu thường là dấu hiệu nên dùng search_after, cursor hoặc một luồng export chuyên biệt.

### Khi offset phù hợp?

- Trang đầu và các trang nông.
- Giao diện cần nhảy tới một trang cụ thể.
- Tập dữ liệu và concurrency ở mức vừa phải.
- Tổng số hit cần hiển thị cho người dùng.

Nếu người dùng thường đi qua hàng nghìn trang, cursor pagination thường phù hợp hơn.

## 7. Total hits và metadata phân trang

SearchHits cung cấp total hits và quan hệ của tổng số hit theo API/version. Không phải lúc nào Elasticsearch cũng đếm chính xác toàn bộ kết quả nếu query được cấu hình giới hạn tracking.

Một response DTO có thể là:

~~~java
public record ProductSearchResponse(
    List<ProductSearchItem> items,
    PaginationMetadata pagination,
    SortMetadata sort
) {}

public record PaginationMetadata(
    int page,
    int size,
    int returned,
    Long totalHits,
    String totalHitsRelation,
    Boolean hasNext
) {}

public record SortMetadata(
    ProductSort field,
    SortDirection direction
) {}
~~~

Map kết quả:

~~~java
private PaginationMetadata toPagination(
        SearchHits<Product> hits,
        ProductSearchCriteria criteria) {

    long total = hits.getTotalHits();
    int returned = hits.getSearchHits().size();

    String relation = hits.getTotalHitsRelation().name();

    Boolean hasNext = relation.equals("EQUAL_TO")
        ? (long) (criteria.page() + 1) * criteria.size() < total
        : null;

    return new PaginationMetadata(
        criteria.page(),
        criteria.size(),
        returned,
        total,
        relation,
        hasNext
    );
}
~~~

Tên enum/method getTotalHitsRelation() và các giá trị relation cần khớp Spring Data version. Nếu API không expose relation trong version đang dùng, không tự khẳng định total là exact.

### Track total hits

Nếu API cần số kết quả chính xác, có thể cấu hình track total hits trong query. Exact counting có chi phí trên tập dữ liệu lớn. Nếu UI chỉ cần biết có thêm kết quả hay không, có thể fetch thêm một hit hoặc dùng cursor thay vì luôn đếm toàn bộ.

Hợp đồng nên phân biệt:

- Total chính xác.
- Total là cận dưới.
- Không yêu cầu total.
- Has next được xác định chính xác hay chỉ là ước lượng.

Không tính total pages từ lower-bound total rồi trả như số trang chính xác.

## 8. Highlight hoạt động như thế nào?

Highlighting trả về các fragment text có chứa phần khớp query. Nó giúp giao diện hiển thị vì sao một document xuất hiện trong kết quả.

Ví dụ query:

~~~http
GET /products/_search
{
  "query": {
    "multi_match": {
      "query": "bàn phím cơ",
      "fields": ["name", "description"]
    }
  },
  "highlight": {
    "pre_tags": ["<em>"],
    "post_tags": ["</em>"],
    "fields": {
      "name": {
        "number_of_fragments": 0
      },
      "description": {
        "fragment_size": 140,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Response có thể chứa:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "P-100",
        "_source": {
          "name": "Bàn phím cơ không dây"
        },
        "highlight": {
          "name": [
            "<em>Bàn phím cơ</em> không dây"
          ],
          "description": [
            "Sản phẩm <em>bàn phím cơ</em> phù hợp làm việc..."
          ]
        }
      }
    ]
  }
}
~~~

Highlight không thay đổi _source. Nó là metadata bổ sung trên từng search hit.

### Highlight không phải snippet generator tổng quát

Highlighter làm việc dựa trên query và field được yêu cầu. Nó không tự viết lại đoạn văn, tóm tắt tài liệu hoặc bảo đảm mọi từ đồng nghĩa về ngữ nghĩa đều được đánh dấu.

Với vector-only query, highlight có thể không có hoặc không thể hiện lý do semantic match như người dùng mong đợi. Nếu hybrid search cần highlight, thường cần một lexical query phù hợp hoặc một cơ chế snippet riêng.

## 9. Chọn field và fragment cho highlight

Không nên highlight mọi field trong document. Chọn các field có ý nghĩa hiển thị:

- name: thường trả toàn bộ field bằng number_of_fragments = 0.
- description: trả một vài fragment giới hạn độ dài.
- categoryText: có thể highlight nếu UI cần.
- Field nội bộ hoặc nhạy cảm: không highlight và không đưa ra response.

Các tùy chọn thường dùng:

| Tùy chọn | Ý nghĩa |
|---|---|
| pre_tags | Marker đặt trước phần khớp |
| post_tags | Marker đặt sau phần khớp |
| fragment_size | Kích thước fragment mục tiêu |
| number_of_fragments | Số fragment tối đa |
| no_match_size | Số ký tự trả về khi không có fragment match, nếu được cấu hình |
| encoder | Cách encode fragment theo highlighter/version hỗ trợ |

Giá trị fragment size là mục tiêu của highlighter, không phải giới hạn ký tự tuyệt đối trong mọi trường hợp. Field ngắn có thể trả toàn bộ nội dung.

### Unified, plain và postings highlighter

Elasticsearch có nhiều highlighter implementation:

- **Unified highlighter:** lựa chọn phổ biến, hỗ trợ nhiều query type và field.
- **Plain highlighter:** dùng cho một số trường hợp đơn giản nhưng có thể tốn chi phí khi phân tích nội dung.
- **Postings highlighter:** có thể hiệu quả khi mapping lưu term vectors/postings phù hợp.

Chọn highlighter theo mapping, query type, field size và benchmark. Không cần thay highlighter mặc định nếu không có bằng chứng về vấn đề hiệu năng hoặc chất lượng fragment.

## 10. Dùng HighlightQuery trong Spring Data Elasticsearch

Spring Data Elasticsearch có abstraction HighlightQuery và các kiểu Highlight/HighlightField ở những release phù hợp. Ví dụ minh họa:

~~~java
HighlightField nameField =
    new HighlightField("name");

HighlightField descriptionField =
    new HighlightField("description");

Highlight highlight = new Highlight(
    List.of(nameField, descriptionField)
);

HighlightQuery highlightQuery =
    new HighlightQuery(highlight, Product.class);
~~~

Các constructor và cách tạo HighlightField phụ thuộc version, đặc biệt khi cần thiết lập fragment size, tag và highlighter type. Hãy dùng API có trong dependency đang cài.

Với NativeQuery, một số release cho phép gắn HighlightQuery vào builder; release khác có thể yêu cầu tạo query bằng Elasticsearch Java API Client hoặc cấu hình khác. Khi cần tùy chọn chi tiết, direct client request có thể rõ hơn.

Ví dụ dùng Java API Client ở mức request:

~~~java
SearchResponse<Product> response = client.search(s -> s
    .index("products")
    .query(q -> q.multiMatch(m -> m
        .query(searchText)
        .fields("name", "description")
    ))
    .highlight(h -> h
        .preTags("<em>")
        .postTags("</em>")
        .fields("name", f -> f
            .numberOfFragments(0)
        )
        .fields("description", f -> f
            .fragmentSize(140)
            .numberOfFragments(2)
        )
    ),
    Product.class
);
~~~

Đoạn Java API Client minh họa cách truyền highlight options. Builder method cần khớp version client. Nếu ứng dụng dùng Spring Data Operations, có thể cô lập direct client trong một gateway thay vì để controller gọi client trực tiếp.

## 11. Đọc highlight từ SearchHit

Khi dùng Spring Data ElasticsearchOperations, kết quả search có thể giữ highlight metadata trong từng SearchHit.

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    Map<String, List<String>> highlights =
        hit.getHighlightFields();

    // Map content and highlights to response DTO.
}
~~~

getHighlightFields() thường trả map từ tên field sang danh sách fragment. Nếu query không yêu cầu highlight hoặc field không có fragment phù hợp, map có thể rỗng hoặc không chứa field đó.

Không lấy highlight từ entity property. Highlight thuộc SearchHit metadata; nếu chỉ giữ hit.getContent() rồi bỏ SearchHit, phần này sẽ mất.

### Response DTO

~~~java
public record ProductSearchItem(
    String id,
    String name,
    BigDecimal price,
    Map<String, List<String>> highlights
) {}
~~~

Mapper:

~~~java
private ProductSearchItem toItem(SearchHit<Product> hit) {
    Product product = hit.getContent();

    return new ProductSearchItem(
        product.getId(),
        product.getName(),
        product.getPrice(),
        hit.getHighlightFields()
    );
}
~~~

Có thể lọc chỉ các field được phép xuất hiện trong response:

~~~java
private Map<String, List<String>> publicHighlights(
        SearchHit<Product> hit) {

    Map<String, List<String>> source =
        hit.getHighlightFields();

    Map<String, List<String>> result = new LinkedHashMap<>();

    for (String field : List.of("name", "description")) {
        List<String> fragments = source.get(field);
        if (fragments != null && !fragments.isEmpty()) {
            result.put(field, fragments);
        }
    }

    return result;
}
~~~

Cách này tránh vô tình công bố highlight của field nội bộ nếu query builder được mở rộng sau này.

## 12. Bảo vệ frontend khi render highlight

Ví dụ highlight dùng em làm marker. Nếu frontend đưa fragment vào innerHTML mà không kiểm soát, nội dung gốc có thể chứa HTML hoặc script độc hại.

Một số nguyên tắc:

- Chỉ cho phép tag marker nằm trong allowlist như em hoặc strong.
- Escape nội dung gốc trước khi render.
- Dùng sanitizer phù hợp nếu phải render HTML.
- Hoặc trả fragment dạng plain text cùng offset/token metadata để frontend tự đánh dấu an toàn.
- Không tin rằng highlighter tự động sanitize toàn bộ source content.

Highlight là nội dung lấy từ document đã index. Nếu dữ liệu đến từ người dùng hoặc hệ thống bên ngoài, cần coi nó là input không tin cậy.

### Marker tùy chỉnh

Có thể dùng marker riêng không phải HTML, ví dụ [[ và ]], rồi frontend parse thành text node và element an toàn. Cần bảo đảm marker không thể xuất hiện tự nhiên hoặc có cơ chế escape rõ ràng.

## 13. Kết hợp sort, pagination và highlight trong NativeQuery

Một query có thể bao gồm cả ba chức năng. Ví dụ cấu trúc REST DSL:

~~~http
GET /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "bàn phím cơ",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  },
  "sort": [
    {
      "_score": "desc"
    },
    {
      "productIdSort": "asc"
    }
  ],
  "highlight": {
    "pre_tags": ["<em>"],
    "post_tags": ["</em>"],
    "fields": {
      "name": {
        "number_of_fragments": 0
      },
      "description": {
        "fragment_size": 140,
        "number_of_fragments": 2
      }
    }
  },
  "track_total_hits": true
}
~~~

Trong Spring Data, có thể dùng NativeQuery với query, pageable, sort và highlight options mà version đang hỗ trợ:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.multiMatch(mm -> mm
            .query(criteria.query())
            .fields("name^3", "description")
        ))
        .filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ))
    ))
    .withPageable(pageable)
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Đây là skeleton cho query và pageable. Phần sort có thể được đưa qua Pageable hoặc withSort tùy cách dùng; phần highlight có thể gắn HighlightQuery nếu Spring Data release hỗ trợ. Cần đối chiếu chữ ký API đang dùng và xác nhận JSON cuối cùng tương ứng DSL mong muốn.

Nếu cần chính xác mọi tùy chọn của Elasticsearch, dùng Java API Client trực tiếp trong gateway và vẫn trả application DTO thống nhất.

## 14. Sort theo relevance và sort theo field có semantics khác nhau

Khi search query có full-text clause, _score biểu diễn relevance. Khi sort theo giá hoặc ngày, Elasticsearch sắp xếp theo field đó; không nên giả định kết quả vẫn theo relevance.

Ví dụ:

- Search “bàn phím cơ” + sort PRICE ASC: sản phẩm rẻ hơn lên trước trong số kết quả phù hợp.
- Search “bàn phím cơ” + sort RELEVANCE DESC: sản phẩm match tốt hơn lên trước.
- Filter status ACTIVE + sort CREATED_AT DESC: sản phẩm mới nhất lên trước dù không có full-text query.

Response metadata nên phản ánh sort lựa chọn của client, ví dụ PRICE ASC, thay vì chỉ trả raw sort field.

### Kết hợp score với field sort

Elasticsearch cho phép nhiều sort criterion theo thứ tự ưu tiên. Nếu sort list là _score desc, sau đó price asc, score quyết định trước; price chỉ phá hòa. Nếu sort list là price asc, sau đó _score desc, giá quyết định trước.

Thứ tự các criterion rất quan trọng. Hãy viết test để xác nhận tie-break và ưu tiên nghiệp vụ.

## 15. Stable pagination và tie-breaker

Nếu chỉ sort theo price, nhiều document có thể cùng giá. Khi dữ liệu được index/update trong lúc người dùng đi qua các trang, thứ tự giữa các document cùng giá có thể thay đổi. Điều này dẫn đến item bị lặp hoặc bị bỏ qua giữa các trang.

Thêm tie-breaker duy nhất:

~~~json
"sort": [
  { "price": "asc" },
  { "productIdSort": "asc" }
]
~~~

Tie-breaker phải:

- Có giá trị cho mọi document cần trả về.
- Có giá trị duy nhất trong phạm vi index/query.
- Có kiểu field hỗ trợ sort hiệu quả.
- Không thay đổi tùy tiện sau khi document được index.

Một field keyword có doc values thường phù hợp. Không dùng field text đã analyzer hoặc một field có nhiều document trùng nếu mục tiêu là total ordering.

Stable sort giảm vấn đề thứ tự không xác định, nhưng offset pagination vẫn có thể dịch chuyển khi dữ liệu mới được thêm trước offset. Nếu cần duyệt nhất quán qua tập dữ liệu đang thay đổi, cân nhắc Point in Time (PIT) cùng search_after.

## 16. Deep pagination với search_after

search_after dùng sort values của hit cuối trang hiện tại làm điểm bắt đầu cho trang tiếp theo. Nó tránh phải bỏ qua một offset rất lớn.

Ví dụ request trang đầu:

~~~http
GET /products/_search
{
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "sort": [
    {
      "price": "asc"
    },
    {
      "productIdSort": "asc"
    }
  ]
}
~~~

Một hit cuối có thể trả sort values:

~~~json
{
  "_id": "P-100",
  "sort": [790000, "P-100"]
}
~~~

Request tiếp theo dùng chính các sort values đó:

~~~http
GET /products/_search
{
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "sort": [
    {
      "price": "asc"
    },
    {
      "productIdSort": "asc"
    }
  ],
  "search_after": [790000, "P-100"]
}
~~~

Các sort values phải khớp thứ tự và kiểu của sort criteria. Không tự tạo cursor từ document ID nếu sort có nhiều field.

### Cursor response

Không cần expose mảng sort values thô như hợp đồng public. Server có thể encode chúng thành token opaque:

~~~json
{
  "items": [],
  "nextCursor": "eyJ2IjoxLCJzb3J0IjpbNzkwMDAwLCJQLTEwMF19"
}
~~~

Cursor nên chứa version payload, sort values và context cần thiết để tiếp tục query. Có thể ký token để phát hiện client sửa nội dung. Khi nhận cursor, server phải xác minh nó thuộc cùng filter, sort và tenant context hiện tại.

Cursor không phải authorization. Mọi query tiếp theo vẫn phải áp dụng quyền và filter dữ liệu.

## 17. Dùng Point in Time cho kết quả ổn định

Nếu dữ liệu thay đổi trong khi client duyệt nhiều trang, các trang search_after có thể thấy snapshot khác nhau. Point in Time (PIT) giữ một view ổn định của index trong một khoảng thời gian.

Luồng khái quát:

1. Mở PIT trên index/alias.
2. Chạy search với PIT và sort ổn định.
3. Lấy sort values của hit cuối.
4. Gửi request tiếp theo với cùng PIT và search_after.
5. Gia hạn keep_alive khi tiếp tục.
6. Đóng PIT khi hoàn tất hoặc hết hạn.

PIT giúp tránh nhiều lỗi do dữ liệu thay đổi giữa các trang. Nó giữ resource trên cluster, vì vậy keep_alive nên ngắn vừa đủ và PIT phải được đóng khi không còn sử dụng.

API PIT và cách truyền PIT qua Spring Data/Java API Client phụ thuộc version. Có thể cần direct Java API Client cho cursor gateway nếu abstraction hiện tại chưa expose đầy đủ.

### PIT không phải transaction nghiệp vụ

PIT giữ snapshot đọc cho search. Nó không khóa document, không bảo đảm mọi dữ liệu mới được thêm sau khi PIT mở sẽ xuất hiện trong phiên duyệt và không thay thế transaction của database.

Nếu người dùng refresh search, mở PIT mới để xem trạng thái hiện tại.

## 18. search_after trong ứng dụng Spring

Một abstraction cursor có thể giữ các giá trị cần thiết:

~~~java
public record ProductSearchCursor(
    List<Object> sortValues,
    String pointInTimeId
) {}
~~~

Response:

~~~java
public record CursorSearchResponse(
    List<ProductSearchItem> items,
    String nextCursor,
    boolean hasNext
) {}
~~~

Service xử lý:

~~~text
Decode and verify cursor
        |
        v
Restore PIT and search_after values
        |
        v
Build query with same filter and sort
        |
        v
Execute search
        |
        v
Map hits and last sort values
        |
        v
Encode next cursor
~~~

Không serialize Java object bất kỳ rồi tin dữ liệu client gửi lại. Cursor phải có schema/version rõ, giới hạn kích thước và chữ ký nếu cần chống sửa đổi.

Nếu cursor có chứa index/alias hoặc tenant, đừng cho phép token thay đổi phạm vi truy cập. Server vẫn lấy tenant từ principal đã xác thực và so khớp với cursor context.

## 19. Sort, pagination và highlight với nested fields

Nếu query tìm nested object nhưng response cần highlight field nested, cần cấu hình nested path phù hợp với mapping và query. Highlight nested fields có semantics khác field ở root document; có thể cần inner hits để xác định child object khớp.

Ví dụ document có variants:

~~~json
{
  "name": "T-Shirt",
  "variants": [
    {
      "color": "black",
      "description": "Áo đen cotton"
    },
    {
      "color": "white",
      "description": "Áo trắng linen"
    }
  ]
}
~~~

Nếu tìm variants.description, query phải là nested query theo path variants. Nếu UI cần hiển thị đúng variant khớp, dùng inner hits và map metadata nested phù hợp.

Không giả định highlight fragment trên nested field sẽ tự động cho biết toàn bộ child object. Cần giữ child identifier hoặc inner hit metadata nếu UI phải liên kết fragment với một variant cụ thể.

Sort theo nested field cũng cần nested sort path và mode như min/max tùy nghiệp vụ. Kiểm thử riêng với nhiều child có giá trị khác nhau để xác nhận kết quả.

## 20. Kết hợp tenant filter và sort

Trong ứng dụng nhiều tenant, mọi nhánh tìm kiếm cần scope theo tenant đã xác thực. Sort không thay thế filter và không được để client chọn tenant.

Ví dụ query:

~~~http
GET /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "tenantId": "tenant-A"
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": "asc"
    },
    {
      "productIdSort": "asc"
    }
  ]
}
~~~

tenantId trong ví dụ phải được lấy từ security context phía server. Nếu client truyền tenant ID trong query parameter, service cần xác minh quyền trước khi dùng.

Khi dùng routing theo tenant để giảm shard fan-out, vẫn giữ tenant filter trong query. Routing là shard selection, không phải authorization hay document filter.

## 21. Xử lý highlight khi query có nhiều nhánh

Một query có thể gồm match, filter, synonym, phrase hoặc hybrid branch. Highlight thường dựa trên lexical query và field được chỉ định.

Các tình huống cần xem xét:

- Field không được highlight dù document match qua vector branch.
- Query match synonym nhưng fragment thể hiện token gốc hoặc token được phân tích tùy highlighter.
- Field được query nhưng không có fragment do analyzer/highlighter settings.
- Một document có nhiều fragment, cần giới hạn số lượng.
- Query phrase cần highlight cụm từ phù hợp.
- Highlight có thể tăng response size và chi phí.

Nếu API hỗ trợ hybrid search, không hứa mọi kết quả vector-only đều có highlight. Có thể dùng lexical query song song để tạo snippet, hoặc dùng passage extraction riêng. Phải ghi rõ trong contract rằng highlight là optional.

## 22. End-to-end service mẫu

Một service có thể phối hợp criteria, sort, pageable, query, search và response mapping:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;
    private final ProductSearchCriteriaMapper criteriaMapper;
    private final ProductSortMapper sortMapper;

    public ProductSearchService(
            ElasticsearchOperations operations,
            ProductSearchCriteriaMapper criteriaMapper,
            ProductSortMapper sortMapper) {
        this.operations = operations;
        this.criteriaMapper = criteriaMapper;
        this.sortMapper = sortMapper;
    }

    public ProductSearchResponse search(
            ProductSearchRequest request) {

        ProductSearchCriteria criteria =
            criteriaMapper.toCriteria(request);

        Pageable pageable = PageRequest.of(
            criteria.page(),
            criteria.size(),
            sortMapper.toSpringSort(
                criteria.sort(),
                criteria.direction()
            )
        );

        NativeQuery query = NativeQuery.builder()
            .withQuery(q -> buildProductQuery(q, criteria))
            .withPageable(pageable)
            .build();

        SearchHits<Product> hits =
            operations.search(query, Product.class);

        return mapResponse(hits, criteria);
    }
}
~~~

buildProductQuery và mapResponse đại diện cho các method riêng của ứng dụng. Trong implementation thực tế, highlight query được gắn qua API HighlightQuery hoặc Java API Client builder phù hợp version.

Nên tách các trách nhiệm thành component nhỏ:

- Criteria mapper: default và validation.
- Sort mapper: enum sang field allowlist.
- Query factory: full-text/filter conditions.
- Highlight factory: field và fragment options.
- Search gateway: gọi Spring Data/Java API Client.
- Response mapper: content và metadata.
- Cursor codec: encode/decode cursor nếu dùng deep pagination.

Không cần tạo class riêng cho mọi method nếu ứng dụng nhỏ; mục tiêu là tránh để controller/service chứa một khối logic query và mapping khó kiểm thử.

## 23. Kiểm thử sorting

Dữ liệu test nên có nhiều document cùng giá trị sort chính để xác nhận tie-breaker.

Ví dụ seed:

| ID | Name | Price |
|---|---|---:|
| P-100 | Keyboard A | 500000 |
| P-200 | Keyboard B | 500000 |
| P-300 | Keyboard C | 700000 |

Test price ascending:

~~~java
@Test
void sortsByPriceThenStableId() {
    ProductSearchResponse response =
        searchService.search(request(
            ProductSort.PRICE,
            SortDirection.ASC,
            0,
            20
        ));

    assertThat(response.items())
        .extracting(ProductSearchItem::id)
        .containsExactly("P-100", "P-200", "P-300");
}
~~~

Test cần đảm bảo productIdSort được seed tương ứng. Nếu query không có tie-breaker, không assert thứ tự giữa hai document cùng giá.

Cũng nên test:

- Name sort dùng keyword subfield.
- Created date sort đúng chiều.
- Relevance sort ưu tiên score.
- Missing values theo policy.
- Client gửi sort enum không hợp lệ bị từ chối.
- Field nội bộ không thể được yêu cầu qua request.

## 24. Kiểm thử pagination

Tạo ít nhất 45 document với thứ tự rõ ràng và size 20:

- Page 0 trả 20 document đầu.
- Page 1 trả 20 document tiếp.
- Page 2 trả 5 document còn lại.
- Không có duplicate giữa các trang khi dataset không thay đổi.
- returned phản ánh số item thực tế.
- totalHits và relation được map đúng theo query configuration.
- hasNext không bị tính sai khi total là lower-bound.

Ví dụ assertion:

~~~java
assertThat(firstPage.items()).hasSize(20);
assertThat(secondPage.items()).hasSize(20);
assertThat(thirdPage.items()).hasSize(5);

assertThat(firstPage.items())
    .extracting(ProductSearchItem::id)
    .doesNotContainAnyElementsOf(
        secondPage.items().stream()
            .map(ProductSearchItem::id)
            .toList()
    );
~~~

Trong integration test, refresh index sau seed data. Nếu dữ liệu thay đổi giữa các request, offset page có thể dịch chuyển; test pagination ổn định nên dùng dataset cố định hoặc kiểm thử cursor/PIT riêng.

## 25. Kiểm thử highlight

Seed một document có từ khóa ở cả name và description. Gọi search với highlight bật và xác nhận:

- SearchHit có fragment cho field được cấu hình.
- Response DTO có highlight map.
- Field không được yêu cầu highlight không xuất hiện.
- number_of_fragments giới hạn số fragment theo cấu hình.
- Khi highlight tắt, response có semantics nhất quán: field vắng mặt, null hoặc map rỗng theo contract.
- Nội dung gốc của entity không bị thay đổi bởi marker.

Không nên assert toàn bộ fragment string nếu analyzer/highlighter có thể tạo khác biệt nhỏ giữa các version. Có thể kiểm tra fragment chứa từ khóa và có marker theo contract của test.

## 26. Kiểm thử cursor và PIT

Với search_after:

- Trang đầu trả sort values cho hit cuối.
- Cursor được encode từ các giá trị đó.
- Trang tiếp theo bắt đầu sau hit cuối và không lặp hit.
- Cursor bị sửa hoặc sai version bị từ chối.
- Cursor dùng với tenant khác bị từ chối.
- Filter/sort thay đổi giữa các request làm cursor không hợp lệ theo policy.
- PIT hết hạn được trả lỗi rõ ràng.
- PIT được đóng khi client hoàn tất hoặc session bị hủy.

Không assert một document cụ thể thắng khi hai hit có sort values giống nhau nếu chưa có tie-breaker ổn định.

## 27. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Sort theo text báo lỗi hoặc không đúng | Field không có doc values | Dùng keyword subfield hoặc field sortable |
| Thứ tự giữa hai trang thay đổi | Sort không có tie-breaker duy nhất | Thêm keyword tie-breaker |
| Page sâu bị từ chối | Vượt max_result_window | Dùng search_after/PIT |
| Tổng hit không chính xác | Total tracking bị giới hạn | Expose total relation hoặc bật exact tracking có kiểm soát |
| hasNext sai | Tính từ lower-bound total | Fetch thêm hit hoặc dùng cursor |
| Highlight map rỗng | Query không bật highlight hoặc field không match | Kiểm tra highlight query, field và analyzer |
| Highlight có HTML nguy hiểm | Render fragment như HTML không sanitize | Escape/sanitize hoặc dùng marker an toàn |
| Highlight mất sau mapping | Chỉ giữ entity content, bỏ SearchHit | Map highlight trước khi bỏ metadata |
| Sort enum gây truy vấn field ngoài ý muốn | Cho client gửi raw field | Dùng enum allowlist |
| Kết quả relevance bị mất | Sort theo field thay vì _score | Chọn sort semantics rõ |
| search_after lặp/mất hit | Sort values không ổn định hoặc sai thứ tự | Dùng tie-breaker và giữ nguyên sort |
| Cursor dùng chéo filter/tenant | Token không ràng buộc context | Ký và xác minh cursor context |
| Highlight vector-only không có | Vector similarity không có lexical term để đánh dấu | Dùng lexical snippet hoặc mô tả highlight optional |
| Nested highlight không gắn đúng child | Thiếu nested path/inner hits | Kiểm tra nested query và inner hits |

## 28. Checklist triển khai

- [ ] Request DTO dùng enum/allowlist cho sort field và direction.
- [ ] Page index, default size và maximum size được quy định rõ.
- [ ] Sort field có mapping hỗ trợ sort, thường là keyword/numeric/date.
- [ ] Không sort trực tiếp trên text field không có doc values.
- [ ] Sort có tie-breaker ổn định khi cần pagination.
- [ ] Missing sort values có policy rõ.
- [ ] Pageable được tạo từ criteria đã validate.
- [ ] Offset pagination chỉ dùng cho độ sâu phù hợp.
- [ ] Vượt max_result_window thì cân nhắc search_after.
- [ ] Cursor giữ sort values và được kiểm tra context.
- [ ] PIT được quản lý và đóng đúng cách nếu sử dụng.
- [ ] Total hits relation được phản ánh trong response.
- [ ] Highlight chỉ áp dụng field cần hiển thị.
- [ ] Fragment size và số fragment được giới hạn.
- [ ] Highlight được map từ SearchHit metadata.
- [ ] Frontend render fragment an toàn, tránh XSS.
- [ ] Vector-only result không bị hứa có highlight.
- [ ] Tenant filter vẫn được áp dụng cùng routing nếu có.
- [ ] Unit test sort mapper và criteria validation.
- [ ] Integration test sort, pagination và highlight với Elasticsearch thật.
- [ ] Có test page boundary, duplicate và cursor tampering.

Sắp xếp, phân trang và highlight tạo nên trải nghiệm tìm kiếm hoàn chỉnh. Sort phải dựa trên field có mapping phù hợp và có tie-breaker khi cần thứ tự ổn định. Offset pagination đơn giản cho các trang nông, còn search_after kết hợp PIT phù hợp hơn khi duyệt sâu trên tập dữ liệu thay đổi. Highlight là metadata của SearchHit, cần được map rõ vào response DTO và render an toàn. Khi các lựa chọn này được kiểm soát qua request criteria, query factory và response mapper, ứng dụng Spring Data Elasticsearch có thể giữ API ổn định trong khi thay đổi mapping và chiến lược tìm kiếm.

