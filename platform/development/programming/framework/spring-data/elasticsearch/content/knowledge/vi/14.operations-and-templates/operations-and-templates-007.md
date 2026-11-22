# Truy xuất metadata kết quả thay vì chỉ lấy nội dung Document

Khi tìm kiếm trong Elasticsearch, kết quả không chỉ là các document khớp điều kiện. Mỗi hit còn có thể mang theo ID, index nguồn, điểm relevance, giá trị sort, đoạn highlight và metadata khác. Toàn bộ response có thể chứa tổng số hit, quan hệ chính xác hay ước lượng của con số đó, aggregation và suggestion.

Nếu ứng dụng chỉ lấy danh sách **Product** hoặc chỉ đọc **_source**, phần metadata này có thể bị bỏ mất. Trong Spring Data Elasticsearch, **SearchHits<T>** và **SearchHit<T>** giữ cả nội dung entity lẫn thông tin tìm kiếm. **ElasticsearchOperations** cho phép thực hiện query và nhận lại cấu trúc kết quả này để service quyết định cần trả dữ liệu nào cho tầng trên.

Bài học tập trung vào cách phân biệt nội dung document với metadata của hit và metadata của toàn bộ search response, cách truy xuất chúng bằng Operations, và cách giữ metadata khi chuyển kết quả thành DTO hoặc API response.

## 1. Nội dung document và metadata tìm kiếm là hai phần khác nhau

Một document trong Elasticsearch thường có phần **_source**, chứa dữ liệu nghiệp vụ đã được index. Ví dụ:

~~~json
{
  "_index": "products-000042",
  "_id": "p-100",
  "_score": 2.41,
  "_source": {
    "name": "Wireless Mechanical Keyboard",
    "category": "accessories",
    "price": 89.5
  },
  "sort": [89.5, "p-100"]
}
~~~

Trong ví dụ này:

- **_source** chứa nội dung document: name, category và price.
- **_id** là định danh document trong index.
- **_index** cho biết document đến từ index vật lý nào.
- **_score** là điểm relevance của hit đối với query.
- **sort** chứa các giá trị được dùng để sắp xếp hit.

Một response tìm kiếm có thể còn chứa tổng số hit, aggregation, suggestion và các thông tin điều khiển phân trang.

Entity Java thường mô tả dữ liệu trong _source:

~~~java
@Document(indexName = "products-read")
public class Product {

    @Id
    private String id;

    private String name;
    private String category;
    private Double price;

    // constructors, getters, setters
}
~~~

Entity Product có thể không chứa _index, _score hay sort values. Những thông tin này thuộc kết quả tìm kiếm, không nhất thiết là thuộc tính nghiệp vụ của document. Vì vậy, không nên thêm mọi metadata tìm kiếm vào entity chỉ để giữ chúng sau khi search.

### Ba lớp dữ liệu cần phân biệt

| Lớp | Ví dụ | Phạm vi |
|---|---|---|
| Nội dung document | name, category, price | Một document |
| Metadata của hit | ID, index, score, sort values, highlights | Một kết quả khớp |
| Metadata của response | total hits, max score, aggregations, suggestions | Toàn bộ request tìm kiếm |

Sự phân biệt này giúp chọn đúng kiểu trả về. Nếu chỉ cần document, entity là đủ. Nếu cần thông tin của từng hit, dùng SearchHit<T>. Nếu cần cả kết quả tìm kiếm và thống kê ở cấp request, giữ SearchHits<T>.

## 2. SearchHits và SearchHit trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp hai abstraction quan trọng:

- **SearchHits<T>** là container cho toàn bộ kết quả tìm kiếm và metadata cấp response.
- **SearchHit<T>** là wrapper cho một document khớp cùng metadata riêng của hit đó.

Quan hệ có thể hình dung như sau:

~~~text
ElasticsearchOperations.search(...)
                |
                v
          SearchHits<Product>
          /       |          \
         /        |           \
        v         v            v
  SearchHit  SearchHit ...  Response metadata
      |          |           |
      v          v           +-- total hits
   Product    Product        +-- total hits relation
   hit meta   hit meta       +-- max score
                             +-- aggregations
                             +-- suggestions
~~~

Ví dụ:

~~~java
SearchHits<Product> searchHits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : searchHits.getSearchHits()) {
    Product product = hit.getContent();

    System.out.println(product.getName());
    System.out.println(hit.getId());
    System.out.println(hit.getScore());
}
~~~

**getContent()** trả về entity đã được Spring Data chuyển đổi từ document. Các method khác của SearchHit cho phép đọc metadata của chính hit đó.

Đừng gọi getContent() rồi loại bỏ wrapper quá sớm nếu các bước sau còn cần score, index nguồn, highlight hoặc sort values.

## 3. Truy xuất metadata của từng hit

### Document ID và index nguồn

SearchHit<T> cung cấp ID và tên index của document được trả về:

~~~java
for (SearchHit<Product> hit : searchHits) {
    String documentId = hit.getId();
    String indexName = hit.getIndex();
    Product product = hit.getContent();
}
~~~

ID rất hữu ích khi UI cần tạo liên kết tới trang chi tiết hoặc khi service cần thực hiện thao tác tiếp theo trên document. Index nguồn hữu ích trong hệ thống có nhiều index phía sau alias, nhất là khi cần truy vết dữ liệu hoặc điều tra migration.

Không nên giả định index nguồn luôn giống tên alias mà ứng dụng gọi. Alias là tên định tuyến; hit metadata có thể cho biết index vật lý chứa document.

Một số kết quả cũng có thể cung cấp routing metadata. Giá trị này hữu ích khi ứng dụng dùng custom routing và cần biết document được định tuyến theo khóa nào. Chỉ sử dụng nếu use case cần nó và API của phiên bản đang dùng có cung cấp.

### Relevance score

getScore() trả về điểm relevance của hit theo query:

~~~java
for (SearchHit<Product> hit : searchHits) {
    float score = hit.getScore();
    Product product = hit.getContent();

    System.out.printf(
        "name=%s, score=%f%n",
        product.getName(),
        score
    );
}
~~~

Score giúp ứng dụng:

- Hiển thị hoặc giải thích thứ tự kết quả tìm kiếm.
- So sánh mức độ phù hợp tương đối giữa các hit của cùng một query.
- Chẩn đoán vì sao document được xếp trước document khác.
- Xây dựng logic trình bày kết quả dựa trên relevance nếu nghiệp vụ yêu cầu.

Không nên coi score là xác suất. Giá trị score không có nghĩa một document có bao nhiêu phần trăm khả năng đúng. Score chỉ có ý nghĩa trong ngữ cảnh query, field statistics, similarity và cách Elasticsearch tính điểm.

Nếu request chỉ sort theo một field và không cần tính relevance, score có thể không có ý nghĩa hữu ích. Khi đó không nên đưa score vào hợp đồng API như một giá trị luôn có thể so sánh.

### Sort values

Khi request có sort, mỗi hit có thể chứa các giá trị đã dùng để sắp xếp:

~~~java
for (SearchHit<Product> hit : searchHits) {
    List<Object> sortValues = hit.getSortValues();
}
~~~

Ví dụ request:

~~~http
POST /products-read/_search
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "_id": {
        "order": "asc"
      }
    }
  ]
}
~~~

Hit đầu tiên có thể có sort values tương ứng với price và _id. Giá trị này có thể được dùng làm điểm bắt đầu cho request tiếp theo với search_after.

Để phân trang sâu ổn định, cần:

1. Xác định thứ tự sort cố định.
2. Thêm tie-breaker duy nhất nếu field sort chính có thể trùng giá trị.
3. Lấy sort values từ hit cuối của trang hiện tại.
4. Truyền nguyên các giá trị đó vào request tiếp theo.
5. Nếu cần kết quả nhất quán khi index vẫn thay đổi, cân nhắc Point in Time (PIT) theo khả năng của phiên bản Elasticsearch và Spring Data đang dùng.

Không tự tạo lại sort values từ thuộc tính entity. Elasticsearch có thể trả giá trị đã chuẩn hóa hoặc có thứ tự và kiểu dữ liệu cụ thể; dùng đúng giá trị metadata từ hit giúp tránh sai lệch khi phân trang.

### Highlight fields

Highlight trả về các đoạn văn bản có chứa phần khớp với query. Đây là metadata của hit, không phải giá trị _source đã bị thay đổi.

Ví dụ request:

~~~http
POST /products-read/_search
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  },
  "highlight": {
    "fields": {
      "name": {}
    },
    "pre_tags": ["<em>"],
    "post_tags": ["</em>"]
  }
}
~~~

Sau khi request được gửi bằng Operations, mỗi hit có thể chứa highlight map:

~~~java
for (SearchHit<Product> hit : searchHits) {
    Map<String, List<String>> highlights =
        hit.getHighlightFields();

    List<String> nameFragments = highlights.get("name");
}
~~~

Một field có thể có nhiều fragment. Fragment có thể chứa thẻ đánh dấu do request cấu hình. Khi hiển thị trên web, phải xử lý markup an toàn; không đưa trực tiếp chuỗi highlight không tin cậy vào HTML mà không kiểm soát.

Highlight không thay thế _source. Nếu ứng dụng cần hiển thị toàn bộ tên sản phẩm, dùng hit.getContent().getName(). Nếu cần hiển thị đoạn trích khớp query, dùng highlight fragments.

### Inner hits

Với query trên nested object hoặc parent-child relationship, Elasticsearch có thể trả về các hit con phù hợp thông qua inner_hits.

Ví dụ mapping có nested lines:

~~~java
@Document(indexName = "orders")
public class PurchaseOrder {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;
}

public class OrderLine {
    private String productCode;
    private Integer quantity;
}
~~~

Một nested query có thể yêu cầu inner hits:

~~~http
POST /orders/_search
{
  "query": {
    "nested": {
      "path": "lines",
      "query": {
        "term": {
          "lines.productCode": "KB-100"
        }
      },
      "inner_hits": {}
    }
  }
}
~~~

Ở cấp hit cha, metadata inner hits cho biết những nested document nào khớp:

~~~java
for (SearchHit<PurchaseOrder> hit : searchHits) {
    Map<String, SearchHits<?>> innerHits = hit.getInnerHits();
}
~~~

Cấu trúc và kiểu truy cập chi tiết phụ thuộc API của phiên bản. Chỉ có inner hits nếu query yêu cầu và Elasticsearch trả phần dữ liệu đó. Việc một property là nested trong mapping không có nghĩa mọi search response tự động có inner hits.

## 4. Metadata ở cấp toàn bộ SearchHits

Ngoài metadata từng hit, SearchHits<T> còn giữ thông tin của cả request.

### Tổng số hit

~~~java
long totalHits = searchHits.getTotalHits();
~~~

Đây là số lượng hit mà Elasticsearch báo cáo cho query. Tuy nhiên, cần xem thêm quan hệ của con số đó:

~~~java
var relation = searchHits.getTotalHitsRelation();
~~~

Tổng số hit có thể là chính xác hoặc chỉ là cận dưới, tùy cách request yêu cầu đếm và cấu hình Elasticsearch. Ví dụ, khi đặt ngưỡng đếm để tối ưu hiệu năng, Elasticsearch có thể dừng đếm chính xác sau ngưỡng và báo rằng tổng số thực tế ít nhất bằng giá trị trả về.

Vì vậy, không nên luôn hiển thị totalHits như một con số chính xác tuyệt đối. Nếu API hoặc UI cần thông báo chính xác, hãy giữ cả total hits relation và thiết kế query để đếm theo yêu cầu nghiệp vụ.

### Max score

getMaxScore() trả về score cao nhất trong các hit của response khi score có ý nghĩa:

~~~java
float maxScore = searchHits.getMaxScore();
~~~

Max score giúp đánh giá thang điểm của một response hoặc phục vụ hiển thị/debug. Không nên so sánh max score giữa các query khác nhau như một thước đo chất lượng tuyệt đối, vì score phụ thuộc cấu trúc query và dữ liệu index.

### Aggregations

Aggregation trả về thống kê trên tập document khớp query hoặc trên phạm vi được xác định bởi aggregation. Ví dụ:

~~~http
POST /products-read/_search
{
  "size": 0,
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "aggs": {
    "average_price": {
      "avg": {
        "field": "price"
      }
    },
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Response chứa bucket và metric, không phải document entity. Spring Data giữ aggregation metadata trên kết quả search; có thể truy cập từ SearchHits bằng API aggregation tương ứng của phiên bản đang dùng.

Không nên cố chuyển aggregation thành Product. Bucket by_category là một nhóm thống kê, còn Product là một document. Hãy chuyển kết quả aggregation sang DTO riêng nếu cần trả cho controller hoặc báo cáo.

### Suggest

Search response có thể chứa suggestion được tạo bởi Suggest API, ví dụ gợi ý cách viết từ hoặc cụm từ gần đúng. Nếu ứng dụng dùng suggestion, giữ metadata suggestion từ kết quả Operations thay vì cố suy ra nó từ danh sách entity.

Suggestion có cấu trúc riêng và không phải hit thông thường. Cách truy cập và chuyển đổi phụ thuộc API client và release train.

### Scroll ID và Point in Time

Một số workflow phân trang hoặc đọc tập dữ liệu lớn có thể sử dụng scroll hoặc Point in Time. Response có thể chứa ID phục vụ request tiếp theo. Đây là metadata điều khiển phiên đọc, không phải dữ liệu nghiệp vụ.

Nếu dùng scroll/PIT:

- Giữ ID mới nhất được server trả về theo quy tắc của API.
- Gửi request tiếp theo với ID đó.
- Đóng hoặc giải phóng context khi hoàn tất.
- Xử lý timeout và trường hợp context hết hạn.
- Không lưu ID vào URL công khai nếu không cần thiết.

API cụ thể và cách SearchHits bộc lộ các giá trị này phụ thuộc phiên bản Spring Data Elasticsearch. Với luồng xử lý dữ liệu lớn, hãy đọc tài liệu đúng release train.

## 5. Thực hiện search bằng ElasticsearchOperations

ElasticsearchOperations là abstraction cấp cao để chạy query và chuyển đổi kết quả sang entity Java. Khi gọi search, thay vì chỉ nhận danh sách document, ta nhận SearchHits<T>.

Ví dụ service:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(String keyword) {
        Query query = /* build query for name */;

        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products-read")
        );
    }
}
~~~

IndexCoordinates cho phép chọn index hoặc alias tường minh. Điều này hữu ích khi ứng dụng đọc qua read alias hoặc cần tìm trên index cụ thể. Nếu entity đã khai báo index mặc định và use case dùng đúng index đó, có thể sử dụng overload phù hợp không cần truyền coordinates.

Query có thể được tạo bằng CriteriaQuery hoặc NativeQuery. Với query phức tạp, NativeQuery cho phép sử dụng các tính năng của Elasticsearch Java API Client. Cú pháp builder thay đổi theo phiên bản, nên cần đối chiếu dependency thực tế.

Ví dụ query đơn giản bằng Criteria:

~~~java
Criteria criteria = new Criteria("category").is("accessories");
Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Kết quả vẫn chứa cả content và metadata. Không cần tự gọi REST endpoint chỉ để lấy ID hoặc score.

### Duyệt kết quả nhưng vẫn giữ wrapper

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();

    String id = hit.getId();
    String sourceIndex = hit.getIndex();
    float score = hit.getScore();
    List<Object> sortValues = hit.getSortValues();
    Map<String, List<String>> highlights =
        hit.getHighlightFields();

    // Xử lý entity và metadata theo use case.
}
~~~

Nếu code chỉ cần nội dung, có thể dùng hit.getContent(). Nếu cần metadata, hãy xử lý wrapper trước khi chuyển thành collection entity thuần.

## 6. Repository cũng có thể trả về metadata-aware result

Repository không bắt buộc luôn trả về List<T>. Tùy phiên bản Spring Data Elasticsearch và kiểu query, repository method có thể hỗ trợ các kiểu kết quả như SearchHits<T>, SearchPage<T> hoặc danh sách SearchHit<T>.

Ví dụ hình thức method:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    SearchHits<Product> findByCategory(String category);
}
~~~

Với kiểu trả về metadata-aware, caller có thể đọc thông tin hit thay vì chỉ nhận entity. Tuy nhiên, hãy kiểm tra danh sách return type được hỗ trợ trong phiên bản Spring Data Elasticsearch đang sử dụng; không phải mọi kiểu trả về của Spring Data module khác đều có thể áp dụng nguyên trạng.

Nếu method trả List<Product>, wrapper metadata không còn trong kết quả. Nếu service cần score, highlight hoặc index nguồn, chọn kiểu trả về giữ SearchHit hoặc dùng ElasticsearchOperations.

### SearchPage khi cần phân trang và metadata

SearchPage<T> kết hợp thông tin phân trang với search hits. Nó hữu ích khi API cần cả page number, page size, total count và metadata của từng hit.

Một luồng thường gặp:

~~~java
SearchHits<Product> searchHits =
    operations.search(query, Product.class);

// Chuyển thành SearchPage theo API hỗ trợ của phiên bản.
SearchPage<Product> page =
    SearchHitSupport.searchPageFor(searchHits, pageable);
~~~

SearchPage giữ các SearchHit<T> thay vì chỉ có entity content. Nếu chuyển ngay sang Page<Product>, ứng dụng có thể mất metadata từng hit. Chọn kiểu page theo dữ liệu mà caller cần.

## 7. Chuyển SearchHit thành DTO mà không làm mất metadata

Tầng API thường không nên trả trực tiếp các object framework nếu hợp đồng API cần ổn định. Có thể chuyển mỗi hit thành DTO rõ ràng.

Ví dụ DTO:

~~~java
public record ProductSearchItem(
    String id,
    String index,
    float score,
    Product product,
    List<Object> sortValues,
    Map<String, List<String>> highlights
) {}
~~~

Mapper:

~~~java
private ProductSearchItem toItem(SearchHit<Product> hit) {
    return new ProductSearchItem(
        hit.getId(),
        hit.getIndex(),
        hit.getScore(),
        hit.getContent(),
        hit.getSortValues(),
        hit.getHighlightFields()
    );
}
~~~

Response cấp search:

~~~java
public record ProductSearchResponse(
    List<ProductSearchItem> items,
    long totalHits,
    String totalHitsRelation,
    float maxScore
) {}
~~~

Service có thể tạo response:

~~~java
public ProductSearchResponse searchProducts(Query query) {
    SearchHits<Product> result =
        operations.search(query, Product.class);

    List<ProductSearchItem> items =
        result.getSearchHits().stream()
            .map(this::toItem)
            .toList();

    return new ProductSearchResponse(
        items,
        result.getTotalHits(),
        result.getTotalHitsRelation().name(),
        result.getMaxScore()
    );
}
~~~

Đây là ví dụ định hướng; kiểu enum và API chính xác cần đối chiếu với phiên bản đang dùng. Trong API thực tế, có thể biểu diễn total hits relation bằng enum hoặc một chuỗi có ý nghĩa rõ ràng.

Lợi ích của DTO:

- API công khai chỉ chứa metadata mà client thực sự cần.
- Entity domain không phải mang field phục vụ riêng cho search.
- Có thể đổi implementation Spring Data mà không buộc client phụ thuộc kiểu framework.
- Có thể kiểm soát dữ liệu nhạy cảm và giới hạn thông tin trả về.
- Có thể thêm cursor hoặc sort values vào response cho phân trang.

Không nên trả toàn bộ metadata nội bộ chỉ vì framework cung cấp. Chỉ expose những field có ý nghĩa với use case.

## 8. Giữ metadata khi tạo API tìm kiếm

Một endpoint tìm kiếm thường cần nhiều hơn danh sách document:

~~~json
{
  "items": [
    {
      "id": "p-100",
      "index": "products-000042",
      "score": 2.41,
      "product": {
        "name": "Wireless Mechanical Keyboard",
        "category": "accessories",
        "price": 89.5
      },
      "highlights": {
        "name": [
          "Wireless <em>Mechanical</em> <em>Keyboard</em>"
        ]
      }
    }
  ],
  "totalHits": 124,
  "totalHitsRelation": "EQUAL_TO",
  "maxScore": 2.41
}
~~~

Ví dụ cho thấy metadata được giữ cùng content. Một API thực tế có thể không cần index hoặc score; thay vào đó có thể trả nextCursor được tạo từ sort values.

Nếu trả highlight fragments, cần quy định rõ client nhận HTML fragment hay text fragment. Đừng để API vô tình biến chuỗi highlight thành HTML có thể thực thi. Dùng escaping/sanitization phù hợp ở tầng trình bày.

### Metadata nào nên giữ ở backend?

Một số metadata chỉ cần ở backend:

- Index vật lý để phục vụ tracing hoặc debug.
- Routing key nội bộ.
- Explanation đầy đủ của score.
- Scroll ID hoặc PIT ID nếu được quản lý phía server.
- Các aggregation không dùng ở giao diện hiện tại.

Một số metadata có thể có ích cho client:

- Total hits và quan hệ chính xác/ước lượng.
- Highlight fragments.
- Sort values hoặc cursor token.
- Score nếu UI cần hiển thị relevance.
- Aggregation đã chuyển thành DTO.

Hãy xác định hợp đồng API theo use case, không serialize nguyên object SearchHits một cách mặc định.

## 9. Metadata và phân trang sâu với search_after

Phân trang bằng from và size phù hợp với những trang đầu. Khi cần đi sâu vào tập kết quả lớn, Elasticsearch khuyến nghị cân nhắc search_after thay vì tăng from không giới hạn.

search_after cần các giá trị sort của hit cuối cùng ở trang hiện tại. Đây là lý do SearchHit.getSortValues() quan trọng.

Ví dụ request đầu:

~~~http
POST /products-read/_search
{
  "size": 20,
  "sort": [
    { "price": "asc" },
    { "_id": "asc" }
  ],
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Giả sử hit cuối trang có sort values:

~~~json
[129.9, "p-120"]
~~~

Request tiếp theo dùng các giá trị đó:

~~~http
POST /products-read/_search
{
  "size": 20,
  "sort": [
    { "price": "asc" },
    { "_id": "asc" }
  ],
  "search_after": [129.9, "p-120"],
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Trong ứng dụng Spring Data, lấy sortValues từ hit cuối và đưa vào query tiếp theo bằng API hỗ trợ của phiên bản đang dùng. Không tự lấy price và id từ entity rồi giả định chúng luôn giống hoàn toàn sort values do Elasticsearch trả về.

Nếu dữ liệu có thể thay đổi trong lúc người dùng đi qua nhiều trang, kết quả có thể dịch chuyển. PIT có thể giúp giữ một góc nhìn ổn định trong suốt phiên phân trang. Khi dùng PIT, quản lý ID và vòng đời context theo tài liệu Elasticsearch của phiên bản triển khai.

## 10. Metadata và aggregation trong cùng SearchHits

Một request có thể trả cả document hits và aggregation:

~~~http
POST /products-read/_search
{
  "size": 10,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
~~~

SearchHits<Product> chứa danh sách hit và metadata response. Aggregation không thuộc một Product cụ thể, mà thuộc toàn bộ query result.

Một service có thể trả kết hợp:

~~~java
public record ProductSearchSummary(
    List<ProductSearchItem> items,
    long totalHits,
    Map<String, Object> statistics
) {}
~~~

Phần statistics là DTO do service xây dựng từ aggregation response. Không nên để controller tự giải mã aggregation container hoặc phụ thuộc trực tiếp vào client response type.

Aggregation API trong Spring Data đã thay đổi qua các phiên bản do client phía dưới thay đổi. Cần đọc tài liệu đúng release train để truy cập bucket/metric và chuyển chúng sang DTO.

## 11. Giải thích score khi cần điều tra kết quả

Khi một document xuất hiện ở vị trí bất ngờ, chỉ nhìn score có thể chưa đủ. Elasticsearch có thể cung cấp explanation nếu request bật tùy chọn tương ứng.

Explanation mô tả các thành phần góp phần tạo ra điểm relevance. Nó có thể rất chi tiết và làm response nặng hơn, vì vậy chỉ nên bật trong môi trường debug hoặc use case cần giải thích kết quả.

Quy trình điều tra:

1. Ghi lại query và index đang được truy vấn.
2. Xác định hit có score bất thường.
3. Bật explain cho request hoặc dùng Explain API trên document cụ thể.
4. Kiểm tra analyzer, token, field boost và similarity.
5. So sánh với một document có nội dung tương tự.
6. Điều chỉnh query hoặc mapping nếu kết quả thực sự không phù hợp.

Score không phải dữ liệu cố định được lưu trong document. Nó được tính theo query và dữ liệu index tại thời điểm search.

## 12. Các lỗi thường gặp khi làm việc với metadata

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Có Product nhưng không có score/index | Caller chỉ giữ getContent() hoặc repository trả entity thuần | Giữ SearchHit<T>/SearchHits<T> |
| Highlight map rỗng | Query không yêu cầu highlight hoặc field không có fragment khớp | Kiểm tra highlight request và field |
| Sort values rỗng | Request không khai báo sort hoặc API không trả sort metadata | Kiểm tra sort clauses và response |
| Total hits được hiển thị như số chính xác nhưng thực ra là cận dưới | Bỏ qua total hits relation | Giữ và kiểm tra relation |
| Aggregation không xuất hiện trong entity | Aggregation là response metadata, không phải _source | Đọc aggregation từ search result |
| UI không biết document nằm ở index nào | Chỉ serialize entity content | Giữ SearchHit.getIndex() nếu cần |
| Phân trang sâu bị lặp hoặc bỏ sót hit | Tạo lại cursor từ entity hoặc thiếu tie-breaker ổn định | Dùng sort values nguyên bản và sort ổn định |
| Inner hits rỗng | Query không khai báo inner_hits hoặc không có nested match | Kiểm tra nested query |
| API response phình lớn | Trả toàn bộ highlight, explain, aggregation hoặc metadata nội bộ | Chuyển sang DTO chỉ giữ field cần thiết |
| Score thay đổi giữa các query | So sánh score của các query hoặc index context khác nhau | Chỉ diễn giải score trong cùng ngữ cảnh query |

### Lỗi phổ biến nhất: chuyển SearchHits thành danh sách entity quá sớm

Ví dụ:

~~~java
List<Product> products = operations.search(query, Product.class)
    .getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

Đoạn code này hoàn toàn hợp lệ nếu caller chỉ cần entity. Nhưng sau bước này, thông tin ID hit, index nguồn, score, highlight và sort values không còn nằm trong danh sách.

Nếu use case cần metadata, hãy chuyển sang DTO ngay từ SearchHit:

~~~java
List<ProductSearchItem> items =
    operations.search(query, Product.class)
        .getSearchHits()
        .stream()
        .map(this::toItem)
        .toList();
~~~

## 13. Kiểm thử metadata của search result

Unit test cho service có thể kiểm tra cách chuyển SearchHits thành DTO, nhưng một số metadata chỉ được tạo đúng khi Elasticsearch thực thi query thực tế.

Nên kiểm tra các tình huống:

- Một query trả nhiều hit có ID và index đúng.
- Score có mặt khi query dùng relevance scoring.
- Sort values tương ứng với thứ tự sort khai báo.
- Highlight xuất hiện khi request cấu hình đúng field.
- Total hits relation được xử lý đúng khi đếm bị giới hạn.
- Aggregation được chuyển thành DTO chính xác.
- Kết quả rỗng vẫn trả metadata hợp lệ.
- Pagination cursor được lấy từ hit cuối, không từ hit đầu.

Ví dụ test ở mức service có thể xác nhận mapper:

~~~java
@Test
void mapsHitMetadataIntoSearchItem() {
    // Tạo SearchHit/Product test fixture theo API của phiên bản.
    // Gọi mapper.
    // Xác nhận ID, index, score và content được giữ.
}
~~~

Với integration test, dùng Elasticsearch version tương thích và dữ liệu kiểm thử cố định. Test highlight cần kiểm tra analyzer và query; test aggregation cần mapping có doc values; test sort cần field hỗ trợ sort.

Không nên viết test chỉ kiểm tra getContent() nếu mục tiêu của use case là bảo toàn metadata.

## 14. Quy tắc thiết kế khi trả metadata

- Giữ SearchHits<T> cho tới khi service đã xử lý xong metadata cấp response.
- Giữ SearchHit<T> khi cần metadata của từng document.
- Chỉ chuyển sang List<T> nếu caller thực sự chỉ cần entity.
- Phân biệt _source với ID, index, score, sort values và highlight.
- Không diễn giải score như xác suất.
- Kiểm tra total hits relation trước khi tuyên bố tổng số kết quả là chính xác.
- Dùng sort values do Elasticsearch trả về khi xây cursor search_after.
- Thêm tie-breaker ổn định khi phân trang theo sort có giá trị trùng.
- Dùng highlight để hiển thị đoạn trích, còn entity content là dữ liệu nguồn.
- Giữ aggregation và suggestion ở cấp response, chuyển sang DTO riêng nếu cần.
- Không expose metadata nội bộ hoặc session ID nếu client không cần.
- Đối chiếu API SearchHit, SearchHits, SearchPage và aggregation với phiên bản Spring Data Elasticsearch đang chạy.

## 15. Checklist trước khi bỏ metadata khỏi kết quả

- [ ] Caller chỉ cần nội dung _source hay cần cả metadata?
- [ ] Có cần ID hoặc index nguồn cho từng hit không?
- [ ] Có cần score để xếp hạng hoặc giải thích kết quả không?
- [ ] Có sort values để phân trang tiếp không?
- [ ] Có highlight fragments cho UI không?
- [ ] Query có trả inner hits không?
- [ ] Có cần total hits relation để phân biệt số chính xác và cận dưới không?
- [ ] Có aggregation hoặc suggestion ở cấp response không?
- [ ] Có cần chuyển metadata sang DTO trước khi trả API không?
- [ ] Có đang chuyển SearchHits<T> thành List<T> quá sớm không?
- [ ] Có kiểm thử metadata với Elasticsearch tương thích không?

Khi truy vấn bằng Spring Data Elasticsearch, entity chỉ là một phần của kết quả. SearchHit<T> giữ metadata của từng document, còn SearchHits<T> giữ thông tin tổng thể của request. Dùng ElasticsearchOperations để nhận và xử lý các wrapper này giúp ứng dụng giữ được ID, index nguồn, score, sort values, highlight, aggregation và các thông tin cần thiết cho phân trang hoặc hiển thị. Chỉ loại bỏ metadata sau khi đã xác định rõ tầng nghiệp vụ phía trên không còn cần nó.

