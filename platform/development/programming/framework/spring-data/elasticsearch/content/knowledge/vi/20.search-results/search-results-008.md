# Ánh xạ kết quả sang DTO và projection theo API hỗ trợ

Kết quả tìm kiếm từ Elasticsearch thường được ánh xạ vào entity domain mà ứng dụng dùng để ghi và đọc document. Tuy nhiên, API trả kết quả cho người dùng không phải lúc nào cũng cần toàn bộ entity. Một màn hình danh sách có thể chỉ cần ID, tên và giá; một trang quản trị có thể cần thêm trạng thái và thời điểm cập nhật; một API công khai có thể cần cấu trúc DTO riêng để tránh làm lộ field nội bộ.

Spring Data Elasticsearch cung cấp nhiều cách xử lý kết quả:

- Ánh xạ hit vào entity rồi chuyển thành DTO trong service.
- Yêu cầu ElasticsearchOperations ánh xạ kết quả sang một kiểu đích khác nếu phiên bản API có overload result type phù hợp.
- Dùng projection interface hoặc projection class trong repository ở các query path được phiên bản hỗ trợ.
- Giữ nguyên SearchHit và SearchHits khi cần score, sort values, highlight, index name hoặc metadata khác.
- Dùng source filtering để giới hạn phần _source được trả về, kết hợp với DTO/projection khi thích hợp.

Các cách này không hoàn toàn thay thế nhau. Cần phân biệt document source, kiểu Java nhận kết quả và metadata của hit để chọn API phù hợp.

## 1. Entity, DTO và projection khác nhau như thế nào?

Giả sử entity Product được dùng để lưu document:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Keyword)
    private String internalSupplierCode;

    // constructors, getters and setters
}
~~~

API danh sách sản phẩm chỉ cần ba giá trị:

~~~java
public record ProductSummary(
    String id,
    String name,
    Long priceInCents
) {
}
~~~

Ba khái niệm:

| Khái niệm | Vai trò |
|---|---|
| Entity/domain object | Mô hình dữ liệu chính của ứng dụng, thường gắn với mapping document |
| DTO (Data Transfer Object) | Kiểu dữ liệu phục vụ một luồng trao đổi hoặc response cụ thể |
| Projection | Cách biểu diễn một phần dữ liệu của entity theo một view/interface hoặc kiểu đích |

Một DTO không nhất thiết phải là entity Elasticsearch và không cần chứa mọi field của document. Projection thường mô tả một tập field cần đọc. Trong Spring Data, projection có thể là interface hoặc class tùy cơ chế và query path được hỗ trợ.

Không nên đưa entity trực tiếp ra API chỉ vì repository đang trả về entity. DTO giúp kiểm soát hợp đồng API, tên field, dữ liệu được phép hiển thị và khả năng thay đổi cấu trúc nội bộ.

## 2. Luồng ánh xạ kết quả tìm kiếm

Một search request có thể đi qua các bước:

~~~text
Elasticsearch index
       |
       v
Search response
       |
       +---- _source document
       |
       +---- hit metadata
       |       - _id
       |       - _score
       |       - sort values
       |       - highlights
       |       - index
       |
       v
Spring Data SearchHit / SearchHits
       |
       v
Mapping converter
       |
       v
Entity hoặc result type
       |
       v
DTO / API response
~~~

Cần phân biệt hai nhóm dữ liệu:

**Document content** là nội dung được ánh xạ thành object Java, thường dựa trên _source và mapping metadata.

**Hit metadata** là thông tin do Search API trả về bên ngoài _source, ví dụ document ID, score, sort values, highlight fields và index name.

Nếu chỉ nhận List<Product>, ứng dụng thường chỉ làm việc với content. Nếu cần điểm relevance hoặc highlight để hiển thị kết quả, hãy giữ SearchHit<Product> hoặc SearchHits<Product> thay vì bỏ metadata ngay từ đầu.

## 3. Cách đơn giản và ổn định: đọc entity rồi map sang DTO

Cách dễ kiểm soát nhất là tìm entity bằng ElasticsearchOperations hoặc repository, sau đó chuyển từng kết quả thành DTO ở tầng service.

~~~java
public record ProductSummary(
    String id,
    String name,
    Long priceInCents
) {
}
~~~

Service:

~~~java
public List<ProductSummary> searchSummaries(Query query) {
    SearchHits<Product> searchHits =
        operations.search(query, Product.class);

    return searchHits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .map(product -> new ProductSummary(
            product.getId(),
            product.getName(),
            product.getPriceInCents()
        ))
        .toList();
}
~~~

Ưu điểm:

- Dễ đọc và dễ debug.
- Không phụ thuộc API projection đặc thù của một minor version.
- Có thể đổi tên field, kết hợp nhiều nguồn hoặc áp dụng quy tắc nghiệp vụ khi tạo DTO.
- Không cần đưa kiểu DTO vào Elasticsearch mapping metadata.
- Có thể kiểm soát rõ field nào được đưa ra API.

Hạn chế là Spring Data vẫn ánh xạ document thành Product trước, sau đó ứng dụng tạo ProductSummary. Nếu document có nhiều field hoặc số lượng kết quả lớn, việc này có thể tạo thêm object và chuyển dữ liệu không cần thiết.

Nếu chỉ có vài field nhưng document rất lớn, hãy xem xét source filtering hoặc API result type trực tiếp nếu phiên bản hỗ trợ.

### 3.1. Dùng mapper riêng khi DTO có logic

Khi nhiều service cùng tạo ProductSummary, có thể tách mapper:

~~~java
@Component
public class ProductSummaryMapper {

    public ProductSummary toSummary(Product product) {
        return new ProductSummary(
            product.getId(),
            product.getName(),
            product.getPriceInCents()
        );
    }
}
~~~

Service:

~~~java
return searchHits.getSearchHits().stream()
    .map(SearchHit::getContent)
    .map(productSummaryMapper::toSummary)
    .toList();
~~~

Mapper phù hợp khi có quy tắc như định dạng tiền, chuyển enum thành label, tính field hiển thị hoặc kết hợp dữ liệu từ nhiều object. Không nên đặt logic API-specific vào entity chỉ để phục vụ một response.

## 4. Ánh xạ trực tiếp sang result type bằng ElasticsearchOperations

Một số phiên bản Spring Data Elasticsearch cung cấp overload cho phép phân biệt:

- Class dùng để xác định entity/domain metadata và index.
- Result type dùng để ánh xạ document trả về.

Dạng API thường gặp:

~~~java
SearchHits<ProductSummary> hits =
    operations.search(
        query,
        Product.class,
        ProductSummary.class
    );
~~~

Trong đó Product là kiểu entity gốc, còn ProductSummary là kiểu nhận kết quả. Một số phiên bản còn cung cấp overload nhận IndexCoordinates:

~~~java
SearchHits<ProductSummary> hits =
    operations.search(
        query,
        Product.class,
        ProductSummary.class,
        IndexCoordinates.of("products")
    );
~~~

Lợi ích là có thể yêu cầu mapping converter tạo result type ngay trong quá trình đọc search response, tránh bước tạo Product trung gian ở service.

**Lưu ý về phiên bản:** chữ ký và mức hỗ trợ của các overload result type thay đổi theo thế hệ Spring Data Elasticsearch. Hãy kiểm tra ElasticsearchOperations của dependency thực tế trong IDE/Javadoc. Nếu project không có overload này, dùng cách đọc entity rồi map DTO hoặc một cơ chế projection được phiên bản hỗ trợ. Không tự tạo một method cùng tên trong code để mô phỏng API framework.

### 4.1. DTO cần có cấu trúc phù hợp với mapping converter

Ví dụ DTO dạng class:

~~~java
public class ProductSummary {

    private String id;
    private String name;
    private Long priceInCents;

    public ProductSummary() {
    }

    public ProductSummary(
            String id,
            String name,
            Long priceInCents) {
        this.id = id;
        this.name = name;
        this.priceInCents = priceInCents;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Long getPriceInCents() {
        return priceInCents;
    }

    public void setId(String id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setPriceInCents(Long priceInCents) {
        this.priceInCents = priceInCents;
    }
}
~~~

Mapping converter cần biết cách tạo và gán giá trị cho result type. Constructor binding, record support, property access và tên tham số phụ thuộc mapping infrastructure và phiên bản Spring Data.

Nếu DTO dùng record hoặc constructor bất biến, bảo đảm tên/thứ tự tham số có thể được Spring Data nhận diện và các field tương ứng có thể được chuyển đổi. Nếu gặp lỗi khởi tạo, thử DTO class có constructor không tham số cùng setter để phân biệt lỗi constructor mapping với lỗi dữ liệu.

### 4.2. Field ID cần được xử lý riêng

Elasticsearch document ID thường nằm trong metadata _id, không nhất thiết là một field trong _source. Nếu DTO cần ID, hãy khai báo property phù hợp và xác nhận cách mapping của API result type trong phiên bản đang dùng có đưa ID từ hit metadata vào DTO hay không.

Khi chưa chắc chắn, giữ SearchHit và dùng hit.getId() để tạo DTO:

~~~java
ProductSummary summary = new ProductSummary(
    hit.getId(),
    hit.getContent().getName(),
    hit.getContent().getPriceInCents()
);
~~~

Cách này tránh giả định _id đã được ghi vào _source.

## 5. Interface-based projection trong repository

Spring Data Commons có cơ chế projection interface. Một interface mô tả các getter mà ứng dụng cần:

~~~java
public interface ProductNameView {

    String getName();

    Long getPriceInCents();
}
~~~

Trong repository, có thể khai báo kiểu trả về projection ở những query method được phiên bản Spring Data Elasticsearch hỗ trợ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<ProductNameView> findByCategory(String category);
}
~~~

Mục tiêu là nhận view chỉ chứa các property cần dùng thay vì phụ thuộc trực tiếp vào entity đầy đủ.

Tuy nhiên, không nên mặc định mọi loại repository method đều hỗ trợ projection giống nhau. Cần xác nhận trên đúng phiên bản và loại query đang dùng, đặc biệt với:

- Derived query method.
- Method dùng @Query.
- Native query.
- SearchHit hoặc SearchHits wrapper.
- Dynamic projection nhận Class<T> làm tham số.
- Projection có nested property hoặc computed accessor.

Nếu method không được hỗ trợ hoặc Spring không tạo được projection proxy, dùng ElasticsearchOperations và map DTO tường minh.

### 5.1. Closed projection

Closed projection chỉ khai báo getter cho property có sẵn trên domain object:

~~~java
public interface ProductCard {

    String getName();

    Long getPriceInCents();
}
~~~

Vì các getter tương ứng với property cụ thể, Spring Data có thể biết trước dữ liệu mà view cần. Khả năng tối ưu lượng dữ liệu thực sự được Elasticsearch trả về còn phụ thuộc query implementation và source filtering của phiên bản.

Không nên suy luận rằng khai báo closed projection chắc chắn khiến Elasticsearch chỉ đọc đúng hai field. Hãy kiểm tra request thực tế nếu tối ưu payload là yêu cầu quan trọng.

### 5.2. Open projection

Open projection có thể dùng biểu thức để tính giá trị từ target object trong những cơ chế Spring Data Commons hỗ trợ:

~~~java
public interface ProductLabel {

    @Value("#{target.name + ' - ' + target.priceInCents}")
    String getLabel();
}
~~~

Đây là ví dụ về cơ chế projection của Spring Data Commons. Mức hỗ trợ open projection trên từng repository query path của Spring Data Elasticsearch cần được xác nhận theo phiên bản.

Open projection có thể cần toàn bộ target object để tính biểu thức, do đó thường không có cùng lợi ích giới hạn field như một projection chỉ đọc property.

Nếu logic tính toán phức tạp hoặc cần gọi service, nên map sang DTO ở tầng ứng dụng thay vì đưa logic vào projection expression.

### 5.3. Dynamic projection

Một số repository abstraction hỗ trợ method nhận Class<T> để caller chọn projection:

~~~java
<T> List<T> findByCategory(
    String category,
    Class<T> projectionType
);
~~~

Ví dụ cách gọi:

~~~java
List<ProductNameView> names =
    productRepository.findByCategory(
        "accessories",
        ProductNameView.class
    );

List<Product> entities =
    productRepository.findByCategory(
        "accessories",
        Product.class
    );
~~~

Đây là dạng dynamic projection của Spring Data. Trước khi dùng với Elasticsearch repository, kiểm tra phiên bản có hỗ trợ dynamic projection cho loại query đó không. Đừng giả định chỉ vì Spring Data JPA hỗ trợ một method pattern thì Spring Data Elasticsearch cũng có cùng hành vi.

## 6. Class-based projection và DTO constructor

Class-based projection thường dùng một DTO có constructor nhận các property cần thiết:

~~~java
public record ProductCardDto(
    String name,
    Long priceInCents
) {
}
~~~

Với Spring Data Commons, constructor projection cần có thể xác định tham số nào tương ứng với property của domain. Record có tên component rõ ràng có thể phù hợp với mapping theo constructor ở các phiên bản hỗ trợ.

Cần phân biệt hai trường hợp:

1. Repository projection: Spring Data repository query tạo kiểu trả về projection theo cơ chế repository.
2. Operations result type: ElasticsearchOperations được yêu cầu đọc search result thành một class đích cụ thể nếu overload đó có sẵn.

Hai cơ chế có thể dùng chung mapping infrastructure nhưng API, giới hạn và metadata trả về khác nhau. Khi không chắc chắn, kiểm tra chữ ký API và viết integration test nhỏ trên phiên bản dependency thật.

## 7. SearchHit và SearchHits: giữ metadata của kết quả

Nếu chỉ cần content, có thể lấy danh sách object từ SearchHits. Nhưng khi cần ranking hoặc thông tin hit, hãy giữ wrapper.

Một SearchHit<T> chứa content cùng metadata, thường gồm:

- ID của document.
- Index name.
- Score.
- Sort values.
- Highlight fields.
- Explanation nếu query yêu cầu.
- Inner hits khi query có inner_hits.

SearchHits<T> chứa tập SearchHit và thông tin chung như tổng số hit, relation của total hits, max score và các metadata search khác tùy API.

Ví dụ:

~~~java
SearchHits<Product> searchHits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : searchHits) {
    Product product = hit.getContent();

    System.out.println("id = " + hit.getId());
    System.out.println("score = " + hit.getScore());
    System.out.println("index = " + hit.getIndex());
    System.out.println("name = " + product.getName());
}
~~~

Không nên chuyển ngay SearchHits thành List<Product> nếu tầng API còn cần score hoặc highlight. Metadata không nằm trong Product và có thể mất khi chỉ lấy content.

### 7.1. Map SearchHit sang DTO nhưng giữ score

Nếu API response cần cả DTO và relevance score, tạo response model riêng:

~~~java
public record ProductSearchResult(
    String id,
    String name,
    Long priceInCents,
    float score
) {
}
~~~

Mapping:

~~~java
List<ProductSearchResult> results =
    searchHits.getSearchHits().stream()
        .map(hit -> {
            Product product = hit.getContent();

            return new ProductSearchResult(
                hit.getId(),
                product.getName(),
                product.getPriceInCents(),
                hit.getScore()
            );
        })
        .toList();
~~~

Cách này giữ metadata cần thiết trong API contract mà không buộc DTO phải là entity Elasticsearch.

### 7.2. Highlight fields

Nếu query bật highlighting, SearchHit có thể chứa các đoạn highlight theo field:

~~~java
for (SearchHit<Product> hit : searchHits) {
    List<String> fragments =
        hit.getHighlightField("description");

    // Map fragments into the API response.
}
~~~

Tên method và kiểu dữ liệu cụ thể cần đối chiếu API version. Highlight là metadata của hit, không phải nội dung source đã được cập nhật. Không ghi các fragment highlight trở lại entity như thể đó là dữ liệu gốc.

## 8. Phân trang và SearchPage

Khi repository hoặc Operations trả về kết quả phân trang, cần phân biệt:

- Page<T>: content cùng thông tin trang và tổng số phần tử.
- SearchHits<T>: các hit và metadata tìm kiếm.
- SearchPage<T>: page abstraction bao quanh search hits, giữ metadata của kết quả.

Một số repository query method hỗ trợ trả SearchPage hoặc SearchHits với Pageable tùy loại query và phiên bản.

Ví dụ dạng repository method:

~~~java
SearchPage<Product> findByCategory(
    String category,
    Pageable pageable
);
~~~

Khi dùng Operations, có thể nhận SearchHits rồi chuyển sang page abstraction bằng tiện ích được phiên bản Spring Data cung cấp, ví dụ SearchHitSupport nếu API hiện tại có lớp này.

Đừng tự tính total pages từ số hit hiện tại nếu Search API chỉ trả một trang. Nếu giao diện không cần tổng chính xác, cân nhắc dạng kết quả không yêu cầu total count hoặc giới hạn theo nhu cầu thực tế.

### 8.1. Phân trang sâu

Projection hoặc DTO không loại bỏ chi phí phân trang sâu. Với from/size lớn, Elasticsearch vẫn phải xử lý các kết quả trước offset. Nếu cần duyệt lượng dữ liệu lớn, cân nhắc search_after với sort ổn định hoặc scroll cho các tác vụ batch theo semantics của API.

## 9. Source filtering: chỉ lấy một phần _source

DTO/projection quyết định kiểu Java ứng dụng muốn nhận. Source filtering quyết định phần nào của _source được Elasticsearch trả về.

Ví dụ REST DSL:

~~~http
POST /products/_search
{
  "_source": [
    "name",
    "priceInCents"
  ],
  "query": {
    "term": {
      "category": "accessories"
    }
  }
}
~~~

Request chỉ yêu cầu hai field trong _source. Điều này có thể giảm payload khi document chứa nhiều dữ liệu lớn.

Có thể dùng include/exclude patterns:

~~~http
POST /products/_search
{
  "_source": {
    "includes": ["name", "priceInCents", "brand"],
    "excludes": ["internalNotes", "supplierSecrets"]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Cần nhớ:

- Source filtering không thay đổi mapping của index.
- Nó không xóa field khỏi document lưu trữ.
- Nó không thay thế authorization.
- Một field bị loại khỏi response có thể khiến DTO property tương ứng nhận null/default.
- Metadata như _id và _score nằm ngoài _source.

Nếu DTO cần ID, hãy xác nhận ID được ánh xạ từ hit metadata hay phải lấy riêng từ SearchHit.

### 9.1. Source filtering không giống stored fields

_source filtering chọn phần JSON source được trả về. Stored fields là cơ chế khác của Elasticsearch và cần mapping field phù hợp. Không dùng thuật ngữ source filtering và stored fields thay thế cho nhau.

Nếu chỉ cần vài field để hiển thị, source filtering thường là cách đơn giản. Nếu cần kiểm soát payload chính xác hơn hoặc field có cấu trúc đặc biệt, kiểm tra Search API và mapping thực tế.

## 10. NativeQuery và source filter trong Spring Data Elasticsearch

Với Spring Data Elasticsearch 5.x, NativeQuery sử dụng Elasticsearch Java API Client. Một số phiên bản cung cấp builder để cấu hình source filter.

Ví dụ minh họa:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

NativeQuery query = NativeQuery.builder()
    .withQuery(elasticsearchQuery)
    .withSourceFilter(
        new FetchSourceFilter(
            new String[] {"name", "priceInCents"},
            new String[] {"internalNotes"}
        )
    )
    .build();
~~~

Tên class, package và builder method có thể khác theo minor version. Hãy kiểm tra NativeQuery.Builder và FetchSourceFilter trong dependency đang dùng. Nếu API không expose cấu hình này, dùng query abstraction hoặc Elasticsearch Java API Client tương ứng với phiên bản.

Không đặt source filter quá hẹp nếu mapping converter cần field khác để tạo DTO hoặc nếu service còn cần dữ liệu để áp dụng quy tắc nghiệp vụ.

## 11. Ánh xạ DTO từ SearchHit một cách rõ ràng

Một pattern thực tế là giữ SearchHit trong service và xây dựng API DTO:

~~~java
public record ProductSearchResponse(
    String id,
    String name,
    Long priceInCents,
    float score,
    List<String> nameHighlights
) {
}
~~~

Service:

~~~java
public List<ProductSearchResponse> search(Query query) {
    SearchHits<Product> hits =
        operations.search(query, Product.class);

    return hits.getSearchHits().stream()
        .map(hit -> {
            Product product = hit.getContent();

            List<String> highlights =
                hit.getHighlightField("name");

            return new ProductSearchResponse(
                hit.getId(),
                product.getName(),
                product.getPriceInCents(),
                hit.getScore(),
                highlights
            );
        })
        .toList();
}
~~~

Ví dụ giả định query đã cấu hình highlight cho field name. Nếu không có highlight, danh sách có thể rỗng. Cần xử lý null theo kiểu trả về của phiên bản và bảo đảm response DTO không phụ thuộc vào implementation detail của SearchHit.

Pattern này phù hợp khi API cần phối hợp content, score, highlight hoặc index metadata.

## 12. Projection không tự động thay thế security và validation

Một projection chỉ giới hạn property được biểu diễn trong view. Nó không phải cơ chế phân quyền.

Ví dụ ProductPublicView không có internalSupplierCode:

~~~java
public interface ProductPublicView {
    String getName();
    Long getPriceInCents();
}
~~~

Điều đó không có nghĩa người dùng đã được authorization vào dữ liệu sản phẩm. Query vẫn phải được giới hạn theo tenant, quyền truy cập, trạng thái hoặc điều kiện bảo mật cần thiết.

Tương tự, source filtering loại field khỏi response nhưng không thay thế kiểm soát truy cập ở tầng ứng dụng. Hãy dùng authorization trước khi truy vấn và thiết kế response DTO theo đúng hợp đồng công khai.

Không trả SearchHit, entity hoặc raw _source trực tiếp ra API nếu các cấu trúc đó có thể chứa metadata hoặc field nội bộ không dành cho client.

## 13. DTO lồng nhau và field không có trong source

DTO có thể có cấu trúc khác entity:

~~~java
public record ProductCard(
    String name,
    PriceView price
) {
}

public record PriceView(
    Long amountInCents,
    String currency
) {
}
~~~

Để mapping trực tiếp hoạt động, cấu trúc source và mapping converter phải có đủ dữ liệu tương ứng hoặc có custom conversion phù hợp. Nếu entity lưu amountInCents nhưng DTO yêu cầu một object PriceView có currency lấy từ cấu hình, converter không thể tự biết quy tắc nghiệp vụ đó nếu không được khai báo.

Trong trường hợp DTO được tổng hợp từ nhiều field hoặc nguồn, map thủ công trong service thường rõ ràng hơn.

Nếu field trong DTO không tồn tại trong _source:

- Property có thể nhận null hoặc giá trị mặc định.
- Constructor bắt buộc có thể không tạo được object nếu thiếu tham số.
- Custom converter có thể cần bổ sung logic.
- Có thể cần lấy metadata từ SearchHit thay vì _source.

Hãy phân biệt field thiếu trong document với field bị source filtering loại khỏi response. Hai tình huống có thể tạo kết quả Java giống nhau nhưng nguyên nhân khác nhau.

## 14. Khi nào dùng DTO mapping trực tiếp, projection hay map thủ công?

| Cách làm | Phù hợp khi | Cần cân nhắc |
|---|---|---|
| Entity rồi map DTO | Cần logic nghiệp vụ hoặc muốn cách làm rõ ràng, ổn định | Có bước tạo entity trung gian |
| Operations result type | Phiên bản có overload nhận domain type và result type; DTO ánh xạ trực tiếp được | API phụ thuộc version và constructor/property mapping |
| Interface projection | Query path hỗ trợ projection và chỉ cần một view đơn giản | Không phải mọi query type/wrapper đều hỗ trợ |
| Class/record projection | Cần kiểu DTO bất biến hoặc cấu trúc trả về cụ thể | Constructor binding và property name phải phù hợp |
| SearchHit + DTO | Cần score, highlight, sort values hoặc index metadata | Phải map content và metadata rõ ràng |
| Source filtering + DTO | Document lớn và chỉ cần một phần _source | Thiếu field có thể làm mapping DTO không đầy đủ |

Quy tắc thực tế:

- Bắt đầu với entity rồi map DTO nếu cần hành vi dễ dự đoán.
- Dùng result type trực tiếp khi Operations version hỗ trợ và DTO mapping đơn giản.
- Dùng projection interface khi repository query path đã được xác nhận hỗ trợ.
- Giữ SearchHit khi cần metadata.
- Thêm source filtering khi cần giảm payload và đã biết rõ các field cần thiết.

## 15. Kiểm thử mapping DTO và projection

Nên có integration test trên Elasticsearch test instance để xác nhận mapping thực tế, đặc biệt khi dùng result type hoặc projection.

Ví dụ kiểm thử cách map entity rồi chuyển DTO:

~~~java
@Test
void shouldMapSearchHitToSummary() {
    Product product = new Product(
        "P-1001",
        "SKU-1001",
        "Wireless Mouse",
        259900L,
        true,
        "SUPPLIER-SECRET"
    );

    operations.save(product);
    indexOperations.refresh();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

    Product actual = hits.getSearchHit(0).getContent();

    ProductSummary summary = new ProductSummary(
        hits.getSearchHit(0).getId(),
        actual.getName(),
        actual.getPriceInCents()
    );

    assertThat(summary.id()).isEqualTo("P-1001");
    assertThat(summary.name()).isEqualTo("Wireless Mouse");
    assertThat(summary.priceInCents()).isEqualTo(259900L);
}
~~~

Với result type trực tiếp hoặc repository projection, viết test riêng để xác nhận:

- DTO được tạo đúng.
- Field có giá trị đúng kiểu.
- ID có được lấy từ _id hay không.
- Field bị source filtering có nhận null/default đúng dự kiến không.
- Projection không vô tình trả field nội bộ.
- SearchHit metadata còn được giữ nếu API cần score/highlight.
- Pagination và total hits có semantics đúng.

Không chỉ kiểm tra rằng danh sách khác null. Hãy xác nhận các giá trị quan trọng và trường hợp field thiếu.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| DTO property bị null | Tên property không khớp source hoặc mapping converter | Kiểm tra _source và tên property |
| DTO không khởi tạo được | Constructor binding hoặc kiểu tham số không phù hợp | Thử constructor/no-args setter và kiểm tra mapping metadata |
| ID DTO bị null | _id nằm ngoài _source và chưa được map từ hit metadata | Lấy ID từ SearchHit.getId() |
| Interface projection không được tạo | Query path/version không hỗ trợ projection đó | Kiểm tra API version và dùng DTO mapping thủ công |
| Dynamic projection không hoạt động | Repository method không hỗ trợ Class<T> projection | Kiểm tra Spring Data version/query derivation |
| SearchHit metadata bị mất | Chuyển SearchHits thành content list quá sớm | Giữ SearchHit tới tầng tạo response |
| Highlight rỗng | Query chưa cấu hình highlight hoặc field không khớp | Kiểm tra highlight query và tên field |
| DTO thiếu dữ liệu sau source filtering | Include/exclude loại field cần thiết | Kiểm tra source filter và DTO constructor |
| Result type overload không biên dịch | API không có overload trong dependency hiện tại | Xem Javadoc/IDE của ElasticsearchOperations |
| Projection lộ dữ liệu ngoài ý muốn | Dùng entity hoặc raw source trực tiếp trong API | Tạo response DTO rõ field được phép trả |
| SearchPage mất metadata | Chỉ giữ content thay vì wrapper | Giữ SearchHits/SearchPage khi cần total và hit metadata |

## 17. Quy trình chọn API

Khi thiết kế kết quả search cho một endpoint:

1. Xác định endpoint cần entity đầy đủ hay chỉ một tập field.
2. Xác định có cần score, highlight, sort values, index name hoặc total hits không.
3. Nếu chỉ cần response DTO đơn giản, cân nhắc entity-to-DTO mapping hoặc result type API nếu có.
4. Nếu dùng repository projection, xác nhận query method và phiên bản hỗ trợ.
5. Nếu document lớn, cân nhắc source filtering nhưng vẫn giữ các field DTO cần.
6. Nếu cần metadata, giữ SearchHit/SearchHits đến tầng tạo response.
7. Viết integration test cho ID, constructor mapping, null/missing field và source filtering.
8. Đảm bảo DTO không trở thành cơ chế thay thế authorization.

## 18. Bảng tra cứu nhanh

| Nhu cầu | API/hướng triển khai |
|---|---|
| Trả DTO đơn giản | Search entity rồi map DTO |
| Map trực tiếp sang result type | ElasticsearchOperations overload domain type/result type nếu version hỗ trợ |
| View chỉ gồm getter | Interface projection trên repository query path được hỗ trợ |
| DTO bất biến | Class/record projection nếu constructor mapping hỗ trợ |
| Cần score và index metadata | SearchHit<T> / SearchHits<T> |
| Cần highlight | SearchHit highlight metadata |
| Cần phân trang và total | Page/SearchPage hoặc SearchHits kết hợp pageable theo API version |
| Giảm _source payload | Source filtering |
| Cần DTO tổng hợp từ nhiều field/nguồn | Map thủ công ở service |
| Bảo vệ field nội bộ | Response DTO và authorization; không chỉ dựa vào projection |

Ánh xạ kết quả sang DTO và projection giúp tách cấu trúc document khỏi hợp đồng API. Hãy phân biệt content với hit metadata, dùng Operations result type hoặc repository projection khi đúng phiên bản hỗ trợ, và giữ SearchHit/SearchHits nếu cần score, highlight hay thông tin phân trang. Khi API projection không rõ hoặc DTO cần logic nghiệp vụ, map entity sang DTO trong service là cách dễ kiểm soát. Source filtering có thể giảm payload, nhưng không thay thế mapping, validation hoặc authorization.

