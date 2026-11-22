# Đóng gói tìm kiếm phức tạp mà vẫn giữ metadata kết quả

Khi một ứng dụng dùng Spring Data Elasticsearch, truy vấn đơn giản có thể được khai báo bằng repository method. Nhưng tìm kiếm thực tế thường cần kết hợp nhiều điều kiện, phân trang, sort, highlight, aggregation, inner hits hoặc các quy tắc nghiệp vụ khác. Nếu dồn toàn bộ logic vào service, lớp nghiệp vụ sẽ biết quá nhiều chi tiết Elasticsearch. Nếu chỉ trả về danh sách entity, ứng dụng lại có thể làm mất metadata mà Elasticsearch đã tính cho từng hit và cho toàn bộ kết quả tìm kiếm.

Một repository tùy biến giải quyết hai vấn đề cùng lúc:

- Đóng gói việc xây dựng query phức tạp vào một thành phần có trách nhiệm rõ ràng.
- Trả về kiểu kết quả giữ nguyên metadata tìm kiếm, thường là `SearchHits<T>` hoặc `SearchPage<T>`, thay vì chỉ trả `List<T>` hay `Page<T>`.

Điểm cốt lõi là phân biệt nội dung entity với thông tin tìm kiếm bao quanh nó. Một hit có thể chứa entity, ID, score, sort values, highlight fields và inner hits. Toàn bộ response còn có total hits, quan hệ chính xác/ước lượng của tổng số hit, max score, aggregations, suggestions hoặc thông tin scroll. Khi chỉ lấy content, các metadata này không còn nằm trong kiểu dữ liệu trả về.

## 1. Vì sao cần repository tùy biến?

Repository method khai báo sẵn phù hợp với truy vấn ổn định và đơn giản:

~~~java
List<Product> findByStatus(String status);
Page<Product> findByCategory(String category, Pageable pageable);
~~~

Khi truy vấn có nhiều điều kiện động, nhiều kiểu query DSL và metadata kết quả, method name có thể trở nên khó đọc. Một service tự xây NativeQuery trực tiếp cũng khiến logic tìm kiếm bị phân tán.

Ví dụ một trang tìm kiếm sản phẩm cần:

- Từ khóa trên tên và mô tả.
- Lọc theo trạng thái, danh mục, thương hiệu và khoảng giá.
- Sort theo độ liên quan hoặc thời gian tạo.
- Phân trang.
- Highlight đoạn văn bản khớp.
- Trả score và sort values của từng hit.
- Trả tổng số hit và aggregation theo danh mục.

Đây là một use case phù hợp với repository fragment tùy biến. Fragment nhận tiêu chí tìm kiếm, xây query, gọi `ElasticsearchOperations`, rồi trả một kiểu kết quả có đủ metadata.

## 2. Phân biệt entity content và SearchHit

`Product` là dữ liệu nghiệp vụ được map từ `_source`. `SearchHit<Product>` là một kết quả tìm kiếm cụ thể, gồm content và metadata của hit đó.

Một hit có thể cung cấp:

| Metadata | Ý nghĩa |
|---|---|
| `id` | Document ID |
| `index` | Index chứa document |
| `score` | Điểm relevance do Elasticsearch tính |
| `sortValues` | Giá trị sort của hit, hữu ích khi phân trang theo sort/search after |
| `highlightFields` | Các đoạn văn bản được highlight theo field |
| `innerHits` | Các hit con từ nested hoặc parent-child query |
| `content` | Entity được map từ document source |

Ví dụ về mặt khái niệm:

~~~text
SearchHit<Product>
    |
    +-- id: product-42
    +-- score: 8.7
    +-- sortValues: [8.7, "product-42"]
    +-- highlightFields:
    |      name -> ["Mechanical <em>Keyboard</em>"]
    +-- innerHits: ...
    +-- content: Product(...)
~~~

Nếu lấy `hit.getContent()` rồi chỉ trả `Product`, ứng dụng vẫn có entity nhưng mất score, highlight, sort values và inner hits gắn với hit đó.

## 3. Metadata ở cấp toàn bộ SearchHits

`SearchHits<T>` là container cho toàn bộ kết quả search. Ngoài danh sách `SearchHit<T>`, nó giữ metadata ở cấp response:

| Metadata | Ý nghĩa |
|---|---|
| `totalHits` | Tổng số document khớp theo thông tin Elasticsearch trả về |
| `totalHitsRelation` | Cho biết tổng hit là chính xác hay chỉ là cận dưới |
| `maxScore` | Score cao nhất trong kết quả |
| `aggregations` | Kết quả aggregation |
| `suggest` | Kết quả suggest nếu truy vấn có dùng |
| `scrollId` | ID của scroll context nếu response thuộc luồng scroll |

Không nên luôn diễn giải totalHits như một con số chính xác tuyệt đối. Elasticsearch có thể trả quan hệ `EQUAL_TO` hoặc `GREATER_THAN_OR_EQUAL_TO`, tùy cách tính total hits và cấu hình truy vấn. UI hoặc API nên giữ thông tin quan hệ này nếu quyết định phân trang hoặc hiển thị dựa trên độ chính xác của tổng kết quả.

Ví dụ đọc kết quả:

~~~java
SearchHits<Product> searchHits =
        operations.search(query, Product.class);

long totalHits = searchHits.getTotalHits();
float maxScore = searchHits.getMaxScore();

for (SearchHit<Product> hit : searchHits.getSearchHits()) {
    Product product = hit.getContent();
    float score = hit.getScore();
    Map<String, List<String>> highlights = hit.getHighlightFields();
}
~~~

Các getter metadata cụ thể phụ thuộc phiên bản Spring Data Elasticsearch, nhưng nguyên tắc là giữ `SearchHits` hoặc `SearchHit` cho đến khi tầng ứng dụng quyết định metadata nào cần xuất ra.

## 4. SearchHits, SearchHit, SearchPage và Page khác nhau thế nào?

| Kiểu kết quả | Nội dung | Metadata từng hit | Metadata toàn search | Phân trang |
|---|---|---|---|---|
| `List<T>` | Entity | Không | Không | Không tự mang thông tin page |
| `Page<T>` | Entity | Không | Chủ yếu tổng số và page metadata | Có |
| `SearchHits<T>` | `SearchHit<T>` | Có | Có | Theo query/pageable nếu đã cấu hình |
| `SearchPage<T>` | `SearchHit<T>` trong một page | Có | Giữ liên kết với `SearchHits` | Có |

`Page<T>` phù hợp nếu caller chỉ cần entity và metadata phân trang cơ bản. `SearchPage<T>` phù hợp khi caller cần một page nhưng vẫn phải giữ score, highlight, sort values hoặc inner hits trên từng hit.

Ví dụ:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);
SearchPage<Product> searchPage =
        SearchHitSupport.searchPageFor(hits, pageable);
~~~

`SearchPage<Product>` là một page của các `SearchHit<Product>`, vì vậy từng phần tử vẫn có metadata tìm kiếm. Nếu chuyển thành `Page<Product>` bằng cách chỉ lấy content của mỗi hit, metadata của hit sẽ bị loại bỏ.

## 5. Thiết kế criteria thay vì truyền Query từ controller

Controller nên nhận tiêu chí nghiệp vụ, không nên nhận Elasticsearch Query DSL trực tiếp. Tạo một object criteria mô tả điều kiện mà người dùng được phép chọn:

~~~java
public record ProductSearchCriteria(
        String keyword,
        String status,
        String category,
        String brand,
        Double minPrice,
        Double maxPrice
) {
}
~~~

Criteria giữ ý nghĩa nghiệp vụ. Repository fragment chuyển criteria thành query DSL, kiểm tra điều kiện hợp lệ và giới hạn các trường được phép sort/filter.

Không để client truyền tên field tùy ý rồi ghép trực tiếp vào query. Với sort động, dùng enum hoặc allowlist:

~~~java
public enum ProductSortField {
    RELEVANCE,
    CREATED_AT,
    PRICE
}
~~~

Service/controller có thể nhận `ProductSortField`, rồi repository ánh xạ sang `Sort` tương ứng. Cách này ngăn client yêu cầu sort theo field nội bộ hoặc field không được index.

## 6. Repository fragment tùy biến

Spring Data hỗ trợ ghép repository từ nhiều fragment. Một fragment có thể khai báo hành vi tìm kiếm riêng, còn repository chính tiếp tục kế thừa `ElasticsearchRepository`.

Interface fragment:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.SearchPage;

public interface ProductSearchOperations {

    SearchPage<Product> searchProducts(
            ProductSearchCriteria criteria,
            Pageable pageable
    );
}
~~~

Repository chính:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchOperations {
}
~~~

Implementation của fragment:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Repository;

@Repository
public class ProductSearchOperationsImpl
        implements ProductSearchOperations {

    private final ElasticsearchOperations operations;

    public ProductSearchOperationsImpl(
            ElasticsearchOperations operations
    ) {
        this.operations = operations;
    }

    @Override
    public SearchPage<Product> searchProducts(
            ProductSearchCriteria criteria,
            Pageable pageable
    ) {
        // Build query and preserve SearchHits metadata.
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

Tên implementation cần tuân theo cơ chế discovery của repository fragment trong phiên bản Spring Data đang dùng. Mẫu phổ biến là tên interface fragment cộng hậu tố `Impl`. Nếu ứng dụng dùng cấu hình repository base package hoặc bean naming tùy chỉnh, hãy xác nhận Spring Data tìm thấy fragment implementation.

Lợi ích của fragment:

- Repository chính vẫn giữ các thao tác CRUD thông thường.
- Logic tìm kiếm phức tạp có interface riêng để kiểm thử.
- Có thể thêm fragment khác mà không làm repository phình to.
- Service gọi một method nghiệp vụ thay vì biết chi tiết query DSL.

## 7. Xây dựng NativeQuery trong fragment

`NativeQuery` phù hợp khi cần các khả năng Elasticsearch DSL mà abstraction query đơn giản không biểu diễn đầy đủ. Có thể kết hợp bool, match, term, range, sort, pageable, highlight và aggregation.

Ví dụ query có từ khóa và filter trạng thái:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(match -> match
                        .field("name")
                        .query(criteria.keyword())
                ))
                .filter(f -> f.term(term -> term
                        .field("status")
                        .value("ACTIVE")
                ))
        ))
        .withPageable(pageable)
        .withSort(Sort.by(Sort.Order.desc("createdAt")))
        .build();
~~~

Đây là ví dụ rút gọn để minh họa cách kết hợp query, filter, sort và pageable bằng Elasticsearch Java Client builder. Trong implementation thực tế, chỉ thêm must khi keyword có giá trị và chỉ thêm từng filter khi criteria tương ứng có giá trị. Không gửi một điều kiện match với chuỗi null hoặc rỗng.

### 7.1. Tách hàm build query

Khi nhiều điều kiện động, tách việc xây query khỏi việc thực thi:

~~~java
private NativeQuery buildQuery(
        ProductSearchCriteria criteria,
        Pageable pageable
) {
    // Validate criteria.
    // Build bool query from non-empty conditions.
    // Add pageable, sort, highlight and aggregations.
    // Return a NativeQuery.
}
~~~

Hàm này có thể được unit test ở mức kiểm tra các nhánh xây query hoặc được xác minh bằng integration test trên Elasticsearch. Tránh để method repository vừa validate request, vừa xây DSL, vừa gọi client, vừa map response thành nhiều DTO trong một khối code dài.

### 7.2. Kết hợp must và filter

Trong bool query:

- `must` thường dùng điều kiện full-text cần relevance score.
- `filter` dùng điều kiện bắt buộc nhưng không cần tính score, như trạng thái, tenant, danh mục hoặc khoảng giá.
- `must_not` loại document theo điều kiện.
- `should` bổ sung điều kiện tăng độ phù hợp hoặc điều kiện tùy cấu hình minimum_should_match.

Đặt đúng điều kiện vào đúng clause giúp score dễ hiểu và query hiệu quả hơn. Những điều kiện bảo mật hoặc tenant scope phải luôn được thêm ở phía server, không phụ thuộc client có gửi filter hay không.

## 8. Giữ metadata khi thực thi query

Sau khi build query, gọi `ElasticsearchOperations.search` và giữ nguyên `SearchHits`:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

return SearchHitSupport.searchPageFor(hits, pageable);
~~~

Ví dụ implementation đầy đủ ở mức cấu trúc:

~~~java
@Override
public SearchPage<Product> searchProducts(
        ProductSearchCriteria criteria,
        Pageable pageable
) {
    NativeQuery query = buildQuery(criteria, pageable);

    SearchHits<Product> hits =
            operations.search(query, Product.class);

    return SearchHitSupport.searchPageFor(hits, pageable);
}
~~~

`SearchHitSupport.searchPageFor` tạo một `SearchPage` từ `SearchHits` và `Pageable`. Kết quả giữ từng `SearchHit<Product>` để caller vẫn truy cập content và metadata của hit.

Nếu cần metadata toàn search như aggregations, suggestions hoặc scroll ID, hãy giữ `SearchHits` hoặc expose nó qua response envelope phù hợp. Đừng chuyển ngay sang danh sách entity rồi bỏ container gốc.

## 9. Highlight và inner hits

### 9.1. Highlight

Highlight giúp giao diện hiển thị đoạn văn bản khớp với truy vấn. Elasticsearch trả highlight theo field trong metadata của từng hit, không nhất thiết thay đổi giá trị field gốc trong entity.

Ví dụ DSL:

~~~json
{
  "query": {
    "match": {
      "description": "wireless keyboard"
    }
  },
  "highlight": {
    "fields": {
      "name": {},
      "description": {}
    }
  }
}
~~~

Kết quả highlight có thể được đọc từ `SearchHit.getHighlightFields()`. Đây là map từ tên field sang danh sách fragment đã được đánh dấu. UI nên render fragment theo quy tắc an toàn HTML phù hợp; không coi chuỗi highlight là HTML đáng tin cậy nếu dữ liệu gốc có thể chứa markup.

### 9.2. Inner hits

Inner hits hữu ích khi query trên nested document hoặc quan hệ parent-child và cần lấy các document con đã khớp. Metadata này gắn với từng hit cha:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "term": {
          "variants.color": "black"
        }
      },
      "inner_hits": {
        "name": "matching_variants"
      }
    }
  }
}
~~~

Khi đọc kết quả, kiểm tra `SearchHit.getInnerHits()` thay vì kỳ vọng các nested object đã khớp sẽ tự được lọc khỏi entity content. Entity content thường phản ánh source document; inner hits là tập kết quả riêng của truy vấn con.

## 10. Aggregations và metadata cấp search

Một truy vấn có thể vừa trả hits vừa trả aggregation:

~~~json
{
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 20
      }
    }
  }
}
~~~

Hits trả các sản phẩm ACTIVE; aggregation `by_category` thống kê số lượng theo danh mục trong tập document đã qua query. Kết quả aggregation không nằm trong từng Product. Nó thuộc metadata cấp SearchHits.

Khi repository trả `SearchPage<Product>`, hãy bảo đảm tầng cần aggregation vẫn truy cập được container aggregation từ SearchHits tương ứng hoặc dùng response envelope giữ cả page lẫn aggregation. Không chuyển aggregation thành một danh sách Product vì đó là hai loại dữ liệu khác nhau.

## 11. Thiết kế response envelope khi API cần DTO

Không phải API nào cũng muốn trả trực tiếp kiểu Spring Data. Có thể tạo DTO response riêng, nhưng cần quyết định metadata nào phải được bảo toàn.

Ví dụ:

~~~java
public record ProductSearchItem(
        String id,
        Product product,
        float score,
        List<Object> sortValues,
        Map<String, List<String>> highlights
) {
}

public record ProductSearchResponse(
        List<ProductSearchItem> items,
        long totalHits,
        String totalHitsRelation,
        float maxScore,
        int page,
        int size
) {
}
~~~

Mapper:

~~~java
List<ProductSearchItem> items = searchHits.getSearchHits().stream()
        .map(hit -> new ProductSearchItem(
                hit.getId(),
                hit.getContent(),
                hit.getScore(),
                hit.getSortValues(),
                hit.getHighlightFields()
        ))
        .toList();
~~~

Response envelope nên giữ thêm aggregations hoặc suggestions nếu API cần chúng. Kiểu cụ thể của aggregation container và total hits relation phụ thuộc phiên bản Spring Data Elasticsearch, nên map sang DTO ổn định của ứng dụng thay vì làm lộ kiểu client nội bộ nếu hợp đồng API cần độc lập với thư viện.

Không phải mọi metadata đều cần xuất ra client. Hãy chọn theo use case:

- UI tìm kiếm thường cần score, highlight, paging và tổng hit.
- API dùng cursor có thể cần sort values.
- Trang kết quả nested có thể cần inner hits.
- Dashboard có thể cần aggregations.
- Backend scroll/batch có thể cần scroll ID hoặc point-in-time context.

## 12. Vì sao không nên unwrap kết quả quá sớm?

Một lỗi phổ biến:

~~~java
List<Product> products = searchHits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();

return products;
~~~

Đoạn code này hợp lệ nếu caller chỉ cần entity. Nhưng sau khi unwrap, mỗi phần tử không còn score, sort values, highlights hoặc inner hits. Container SearchHits cũng không còn trong response để truy cập totalHits, aggregations và các metadata khác.

Nếu một tầng cần entity thuần và tầng khác cần metadata, hãy tạo hai method hoặc hai kiểu response rõ ràng:

- `searchProducts(...)` trả `SearchPage<Product>` cho use case tìm kiếm.
- `findProductsForExport(...)` trả entity hoặc stream theo use case export nếu metadata search không cần thiết.

Không dùng một kiểu `List<T>` cho mọi use case rồi cố gắng bổ sung metadata bằng các truy vấn phụ.

## 13. Phân trang và sort cần giữ đúng metadata

`Pageable` mô tả page, size và sort. Query phải dùng pageable để Elasticsearch trả đúng cửa sổ kết quả. Sau đó, `SearchHitSupport.searchPageFor` gắn `SearchHits` với pageable.

Ví dụ:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
);

SearchPage<Product> result =
        productRepository.searchProducts(criteria, pageable);
~~~

Khi phân trang theo score hoặc sort nhiều field, `SearchHit.getSortValues()` có thể quan trọng cho việc tiếp tục truy vấn bằng search-after. Không tự suy ra sort values từ entity vì chúng là metadata do Elasticsearch trả về theo query.

Với dữ liệu rất lớn hoặc yêu cầu cursor, page/offset có thể không phù hợp. Hãy cân nhắc `search_after` hoặc PIT theo phiên bản Elasticsearch hỗ trợ. Khi dùng cursor, giữ sort values và context cần thiết trong response/service state; không chỉ giữ entity content.

## 14. Total hits và độ chính xác của tổng số kết quả

Elasticsearch có thể giới hạn việc đếm tổng hit chính xác để giảm chi phí. Do đó, tổng số hit cần đi cùng quan hệ:

- `EQUAL_TO`: tổng số hit là chính xác.
- `GREATER_THAN_OR_EQUAL_TO`: số trả về là cận dưới.

Nếu UI hiển thị “1,000 kết quả”, cần biết con số là chính xác hay ít nhất 1,000. Nếu nghiệp vụ yêu cầu tổng chính xác, cấu hình truy vấn phù hợp để track total hits, nhưng hãy hiểu chi phí tăng thêm.

Không nên tự tính total bằng `content.size()` vì đó chỉ là số hit của trang hiện tại, không phải tổng kết quả.

## 15. Kiểm soát trách nhiệm của custom repository

Một custom repository tốt đóng gói query nhưng không biến thành một lớp khổng lồ xử lý mọi thứ.

Nên tách:

- Criteria validation: kiểm tra khoảng giá, từ khóa, page size và sort field.
- Query builder: chuyển criteria thành Query DSL.
- Search executor: gọi ElasticsearchOperations.
- Result mapper: giữ hoặc chuyển metadata theo response contract.

Nếu query có nhiều nhánh, có thể tách helper cho full-text, filters, sort, highlight và aggregations. Nhưng không cần tạo abstraction cho mọi clause nhỏ; giữ cấu trúc đủ dễ đọc để developer nhìn ra query cuối.

### 15.1. Bảo mật và tenant filter

Điều kiện tenant hoặc quyền truy cập phải được áp dụng ở phía server, không để client có thể bỏ qua bằng cách không gửi filter. Custom repository là nơi thích hợp để thêm filter bắt buộc từ security context hoặc tham số được service kiểm soát.

Không cho client gửi trực tiếp field path hoặc Query DSL tùy ý nếu API không được thiết kế như một search console tin cậy. Dùng criteria có allowlist để giới hạn những khả năng tìm kiếm được phép.

## 16. Kiểm thử custom search repository

Kiểm thử cần xác nhận cả nội dung và metadata.

### 16.1. Kiểm thử query criteria

Với mỗi điều kiện:

- Keyword null/rỗng không tạo match query vô nghĩa.
- Status/category/brand chỉ được đưa vào filter khi có giá trị.
- Min price không lớn hơn max price.
- Sort field nằm trong allowlist.
- Page size nằm trong giới hạn.
- Tenant/security filter luôn được áp dụng.

### 16.2. Kiểm thử metadata của hit

Chuẩn bị document có nội dung khớp và chạy truy vấn có highlight/sort. Xác nhận content map đúng Product, ID trong SearchHit đúng document ID, score được giữ lại, sort values có mặt khi query yêu cầu, highlight fields chứa fragment mong đợi và inner hits có mặt khi query nested/parent-child yêu cầu.

### 16.3. Kiểm thử metadata toàn search

Xác nhận total hits và total hits relation đúng, max score có giá trị như mong đợi, aggregations được giữ lại, SearchPage có đúng page/size/tổng số phần tử và trang rỗng vẫn giữ metadata response phù hợp.

### 16.4. Kiểm thử unwrap

Nếu API có mapper DTO, kiểm tra mapper giữ lại tất cả metadata nằm trong hợp đồng response. Nếu API chỉ trả entity, xác nhận việc bỏ metadata là chủ đích và không ảnh hưởng use case khác.

Mock ElasticsearchOperations có thể kiểm tra repository gọi đúng query và chuyển kết quả đúng. Integration test với Elasticsearch tương thích vẫn cần thiết để xác nhận DSL, highlight, aggregation và inner hits thực sự hoạt động.

## 17. Các lỗi thường gặp

### 17.1. Trả List<Entity> cho một use case cần score/highlight

Danh sách entity không chứa metadata từng hit. Trả SearchHits hoặc SearchPage nếu caller cần thông tin đó.

### 17.2. Dùng Page<Entity> rồi nghĩ đã giữ toàn bộ Search metadata

Page giữ thông tin phân trang cơ bản, không giữ score, highlight hoặc inner hits trên từng phần tử. Dùng SearchPage.

### 17.3. Unwrap SearchHit quá sớm

Khi chỉ lấy getContent(), metadata hit bị loại bỏ. Chỉ unwrap tại ranh giới mà ứng dụng đã quyết định không cần metadata.

### 17.4. Quên totalHitsRelation

Total hits có thể là cận dưới. Không luôn hiển thị nó như tổng chính xác.

### 17.5. Đọc aggregation từ entity

Aggregation thuộc SearchHits, không nằm trong content entity. Giữ container hoặc map riêng.

### 17.6. Tự tạo lại sort values

Sort values là metadata của kết quả query. Không suy ra từ entity nếu cần search-after hoặc cursor chính xác.

### 17.7. Dồn DSL vào service

Service trở nên gắn chặt với Elasticsearch và khó kiểm thử. Đóng gói query trong repository fragment.

### 17.8. Tạo repository implementation không đúng tên

Spring Data không tìm thấy fragment implementation nếu tên hoặc cấu hình discovery không phù hợp. Tuân theo naming convention của phiên bản và xác nhận bean được đăng ký.

### 17.9. Dùng query client-specific trong public API

Lộ trực tiếp kiểu query/aggregation của Elasticsearch ra controller khiến API khó thay đổi. Nhận criteria nghiệp vụ và map kết quả sang response DTO nếu cần.

## 18. Quy trình xây dựng một custom search method

1. Xác định use case và metadata mà caller cần.
2. Tạo criteria object chỉ chứa điều kiện nghiệp vụ được phép.
3. Khai báo custom repository fragment.
4. Implement fragment bằng ElasticsearchOperations.
5. Xây query DSL từ criteria, thêm filter bảo mật và tenant.
6. Thêm pageable, sort, highlight, aggregation hoặc inner hits theo yêu cầu.
7. Gọi search và giữ nguyên SearchHits<T>.
8. Chuyển sang SearchPage<T> nếu cần page abstraction mà vẫn giữ SearchHit metadata.
9. Nếu cần DTO, map có chủ đích từng metadata vào response envelope.
10. Kiểm thử content, metadata từng hit, metadata toàn search và trường hợp rỗng.

## 19. Kết luận

Repository tùy biến giúp đóng gói việc xây dựng truy vấn Elasticsearch phức tạp sau một method nghiệp vụ rõ ràng. Criteria object giữ API độc lập với Query DSL; repository fragment xây query, áp dụng filter bắt buộc, sort, pageable, highlight và aggregation rồi thực thi qua ElasticsearchOperations.

Để giữ metadata kết quả, không chuyển SearchHits<T> thành List<T> quá sớm. SearchHit<T> chứa content cùng ID, score, sort values, highlight fields và inner hits; SearchHits<T> chứa tổng số hit, quan hệ độ chính xác, max score và metadata cấp search. SearchPage<T> kết hợp phân trang với các SearchHit<T>, phù hợp khi caller cần page nhưng vẫn phải giữ metadata từng hit.

Nếu API cần DTO riêng, hãy thiết kế response envelope để giữ đúng những metadata cần dùng. Chỉ unwrap thành entity thuần khi use case thực sự không cần score, highlight, inner hits, aggregations hoặc sort values. Một custom repository tốt vừa che giấu độ phức tạp của query vừa bảo toàn đủ thông tin để tầng trên trình bày và xử lý kết quả chính xác.
