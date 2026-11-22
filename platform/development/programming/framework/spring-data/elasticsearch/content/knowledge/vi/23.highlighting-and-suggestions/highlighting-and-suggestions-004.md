# Đọc highlight từ SearchHit và ánh xạ về DTO

Elasticsearch có thể trả về các đoạn văn bản chứa từ khóa đã khớp, kèm thẻ đánh dấu phần được highlight. Spring Data Elasticsearch giữ những đoạn này trong metadata của SearchHit, tách biệt với entity được chuyển đổi từ _source. Vì vậy, nếu một API cần trả cả dữ liệu sản phẩm và các đoạn highlight, ứng dụng nên nhận SearchHit<T> hoặc SearchHits<T>, đọc getHighlightField(...), rồi ánh xạ thủ công sang DTO phản hồi.

Bài học này đi theo toàn bộ luồng: cấu hình highlight trên repository hoặc query, đọc danh sách fragment từ SearchHit, phân biệt nội dung gốc với nội dung highlight, chuyển kết quả thành DTO, xử lý trường hợp không có fragment và đưa dữ liệu an toàn tới giao diện.

## 1. Highlight nằm ở đâu trong search response?

Khi gọi Search API với cấu hình highlight, Elasticsearch trả thêm một object highlight trong từng search hit. Ví dụ response rút gọn:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "p-100",
        "_score": 3.82,
        "_source": {
          "title": "Mechanical keyboard",
          "description": "A quiet wireless keyboard for daily work."
        },
        "highlight": {
          "title": [
            "<mark>Mechanical</mark> keyboard"
          ],
          "description": [
            "A quiet <mark>wireless</mark> keyboard for daily work."
          ]
        }
      }
    ]
  }
}
~~~

Trong response này có hai phần dữ liệu khác nhau:

- _source chứa nội dung gốc của document, được Spring Data ánh xạ thành entity Product.
- highlight chứa các fragment do highlighter tạo ra, bao gồm các thẻ đánh dấu term khớp.

Spring Data biểu diễn một kết quả tìm kiếm bằng SearchHit<T>. Đối tượng này chứa entity qua getContent() và metadata của hit như ID, index, score, sort values, inner hits và highlight fields. Nhiều SearchHit<T> được gom trong SearchHits<T>, nơi còn có tổng số hit, quan hệ tổng hit, max score, aggregations và suggest results.

~~~text
Search API response
       |
       v
SearchHits<Product>
       |
       +---- SearchHit<Product> #1
       |          |
       |          +-- getContent()        -> Product từ _source
       |          +-- getId()             -> document ID
       |          +-- getScore()          -> relevance score
       |          +-- getHighlightFields()-> Map<field, fragments>
       |
       +---- SearchHit<Product> #2
                  |
                  +-- getContent()
                  +-- getHighlightFields()
~~~

Không nên kỳ vọng các fragment highlight tự động trở thành thuộc tính của entity. Chúng là metadata của kết quả tìm kiếm và cần được đọc từ SearchHit.

## 2. Khai báo entity và repository

Ví dụ sử dụng index products với hai field văn bản title và description:

~~~java
package com.example.catalog.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String category;

    public Product() {
    }

    public Product(String id, String title, String description, String category) {
        this.id = id;
        this.title = title;
        this.description = description;
        this.category = category;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getDescription() {
        return description;
    }

    public String getCategory() {
        return category;
    }
}
~~~

Mapping tương ứng có thể được kiểm tra bằng Elasticsearch API:

~~~http
GET products/_mapping
~~~

Highlight thường được dùng trên các field có nội dung văn bản như text hoặc keyword. Mapping phải tồn tại và dữ liệu phải được lập chỉ mục theo analyzer phù hợp với query. Việc bật highlight không thay thế mapping field và cũng không tự làm một field có thể tìm kiếm.

## 3. Bật highlight bằng @Highlight

Spring Data Elasticsearch cung cấp annotation @Highlight để khai báo field cần highlight trên repository method. Mỗi field được chỉ định bằng @HighlightField.

~~~java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.annotations.Highlight;
import org.springframework.data.elasticsearch.annotations.HighlightField;
import org.springframework.data.elasticsearch.annotations.HighlightParameters;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Highlight(fields = {
        @HighlightField(
            name = "title",
            parameters = @HighlightParameters(numberOfFragments = 0)
        ),
        @HighlightField(
            name = "description",
            parameters = @HighlightParameters(
                fragmentSize = 140,
                numberOfFragments = 3,
                order = "score"
            )
        )
    }, parameters = @HighlightParameters(
        preTags = {"<mark>"},
        postTags = {"</mark>"},
        encoder = "html"
    ))
    SearchHits<Product> findByTitleOrDescription(String title, String description);
}
~~~

Giải thích cấu hình:

- @Highlight(fields = ...) chọn các field cần trả fragment.
- @HighlightField(name = "title") yêu cầu highlight thuộc tính title.
- numberOfFragments = 0 trả toàn bộ nội dung field title thay vì cắt thành nhiều fragment.
- fragmentSize = 140 yêu cầu fragment mô tả có kích thước mục tiêu khoảng 140 ký tự.
- numberOfFragments = 3 giới hạn số fragment description được trả.
- order = "score" yêu cầu sắp xếp fragment theo mức độ liên quan.
- preTags và postTags xác định thẻ bọc term được highlight.
- encoder = "html" yêu cầu encode nội dung fragment dưới dạng HTML trước khi thêm thẻ highlight.

Tên trong @HighlightField.name là tên property của entity, không phải tên field đã đổi trong Elasticsearch mapping. Nếu dùng @Field(name = "product_title") cho property Java title, annotation highlight vẫn tham chiếu property title. Khi đọc map từ SearchHit, hãy kiểm tra key thực tế trong response nếu mapping có tên field tùy chỉnh.

Method trên trả về SearchHits<Product>, nhờ vậy ứng dụng có thể đọc cả entity lẫn metadata highlight. Spring Data cũng hỗ trợ các dạng như List<SearchHit<Product>>; nếu chỉ trả List<Product>, ứng dụng không còn đối tượng SearchHit để truy cập metadata của từng hit.

### 3.1. Gọi repository method

~~~java
SearchHits<Product> hits = repository.findByTitleOrDescription(
        "wireless keyboard",
        "wireless keyboard");
~~~

Spring Data tạo search request dựa trên query method và thêm cấu hình highlight từ annotation. Trong ví dụ, query tìm theo title hoặc description; highlighter tạo fragment cho các field được khai báo.

Để tránh nhầm giữa tên tham số và ý nghĩa tìm kiếm, trong ứng dụng thực tế có thể dùng @Query để khai báo rõ Query DSL, sau đó vẫn kết hợp @Highlight trên cùng method:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

@Query("""
    {
      "multi_match": {
        "query": "?0",
        "fields": ["title", "description"]
      }
    }
    """)
@Highlight(fields = {
    @HighlightField(name = "title"),
    @HighlightField(name = "description")
})
SearchHits<Product> searchHighlighted(String text);
~~~

@Query mô tả query clause; @Highlight mô tả phần highlight của search request. Hai cấu hình đảm nhiệm hai phần khác nhau của request.

## 4. Đọc fragment từ SearchHit

Sau khi nhận SearchHits<Product>, duyệt qua các SearchHit<Product>:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> hits = repository.searchHighlighted("wireless keyboard");

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    String id = hit.getId();
    float score = hit.getScore();

    List<String> titleFragments = hit.getHighlightField("title");
    List<String> descriptionFragments = hit.getHighlightField("description");

    System.out.println(id + " / " + score);
    System.out.println("Title: " + titleFragments);
    System.out.println("Description: " + descriptionFragments);
}
~~~

Hai method quan trọng:

~~~java
Map<String, List<String>> getHighlightFields();
List<String> getHighlightField(String field);
~~~

getHighlightFields() trả map từ tên field sang danh sách fragment. Theo API SearchHit, map này không bao giờ là null. getHighlightField(field) trả danh sách fragment của một field; danh sách có thể rỗng nhưng không bao giờ là null.

Ví dụ đọc toàn bộ map:

~~~java
Map<String, List<String>> highlightFields = hit.getHighlightFields();

highlightFields.forEach((field, fragments) -> {
    System.out.println("Field: " + field);
    fragments.forEach(System.out::println);
});
~~~

Ví dụ kết quả:

~~~text
Field: title
  <mark>Wireless</mark> Keyboard
Field: description
  A compact <mark>wireless</mark> keyboard for travel.
  The keyboard connects through Bluetooth.
~~~

Một field có thể không xuất hiện trong map nếu không có fragment phù hợp hoặc field không được yêu cầu highlight. Không truy cập trực tiếp map.get("title").get(0) khi chưa kiểm tra danh sách có phần tử.

## 5. Phân biệt nội dung gốc và fragment highlight

hit.getContent() trả entity được ánh xạ từ document source. hit.getHighlightField("title") trả các đoạn highlight do Elasticsearch tạo ra. Hai giá trị này có thể khác nhau về độ dài và cấu trúc:

| Giá trị | Nguồn | Nội dung |
|---|---|---|
| hit.getContent().getTitle() | _source | Toàn bộ title gốc, không có tag highlight |
| hit.getHighlightField("title") | Search response highlight | Một hoặc nhiều fragment có tag đánh dấu |
| hit.getScore() | Search metadata | Điểm relevance của document |
| hit.getId() | Search metadata | Document ID |

Fragment không nhất thiết chứa toàn bộ field. Với field dài, Elasticsearch thường cắt thành các đoạn xung quanh term khớp. Nếu cần hiển thị đầy đủ nội dung, giữ field gốc và dùng fragment riêng để làm phần preview.

Ví dụ:

~~~java
Product source = hit.getContent();
String originalTitle = source.getTitle();
List<String> highlightedTitle = hit.getHighlightField("title");

String displayTitle = highlightedTitle.isEmpty()
        ? originalTitle
        : highlightedTitle.get(0);
~~~

Đoạn code dùng title gốc làm fallback nếu không có fragment highlight. Đây là cách xử lý an toàn hơn việc giả định mọi hit đều có highlight cho mọi field.

## 6. Ánh xạ SearchHit thành DTO

Trong REST API, không nên trả trực tiếp SearchHit<Product> nếu hợp đồng API chỉ cần một cấu trúc kết quả ổn định. Tạo DTO mô tả rõ dữ liệu gốc, fragment highlight và score.

### 6.1. Định nghĩa DTO

~~~java
package com.example.catalog.api.dto;

import java.util.List;

public record ProductSearchResult(
        String id,
        String title,
        String description,
        List<String> titleHighlights,
        List<String> descriptionHighlights,
        float score) {
}
~~~

DTO có hai lớp nội dung:

- title, description: giá trị gốc lấy từ entity.
- titleHighlights, descriptionHighlights: fragment do Elasticsearch trả về.

Giữ hai loại dữ liệu riêng giúp client quyết định hiển thị toàn bộ nội dung, fragment preview hay highlight theo từng field.

### 6.2. Viết mapper từ một SearchHit

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;

import com.example.catalog.api.dto.ProductSearchResult;
import com.example.catalog.domain.Product;

public final class ProductSearchMapper {

    private ProductSearchMapper() {
    }

    public static ProductSearchResult toDto(SearchHit<Product> hit) {
        Product product = hit.getContent();

        return new ProductSearchResult(
                hit.getId(),
                product.getTitle(),
                product.getDescription(),
                hit.getHighlightField("title"),
                hit.getHighlightField("description"),
                hit.getScore());
    }
}
~~~

Mapper chỉ đọc highlight từ SearchHit; không ghi fragment vào entity. Nếu DTO dùng List, Spring Data đã trả một danh sách rỗng khi field không có fragment, nên không cần tự kiểm tra null cho getHighlightField.

### 6.3. Ánh xạ toàn bộ SearchHits

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHits;

public List<ProductSearchResult> toDtos(SearchHits<Product> hits) {
    return hits.getSearchHits().stream()
            .map(ProductSearchMapper::toDto)
            .toList();
}
~~~

Nếu dự án dùng Java 8 đến Java 15, thay .toList() bằng .collect(Collectors.toList()):

~~~java
return hits.getSearchHits().stream()
        .map(ProductSearchMapper::toDto)
        .collect(Collectors.toList());
~~~

Nếu API cần trả tổng số hit hoặc thông tin phân trang, có thể tạo response DTO cấp cao hơn:

~~~java
public record ProductSearchResponse(
        List<ProductSearchResult> items,
        long totalHits,
        float maxScore) {
}
~~~

Mapper:

~~~java
public ProductSearchResponse toResponse(SearchHits<Product> hits) {
    List<ProductSearchResult> items = hits.getSearchHits().stream()
            .map(ProductSearchMapper::toDto)
            .toList();

    return new ProductSearchResponse(
            items,
            hits.getTotalHits(),
            hits.getMaxScore());
}
~~~

SearchHits chứa thông tin của toàn bộ search response, còn từng SearchHit chứa dữ liệu và metadata của một document. Khi xây API, hãy quyết định metadata nào thực sự cần công khai thay vì trả nguyên cấu trúc nội bộ của Spring Data.

## 7. Tạo DTO chỉ có nội dung hiển thị

Một số API không cần trả lại toàn bộ nội dung gốc; chúng chỉ cần ID, title hiển thị và snippet. Có thể tạo DTO ngắn hơn:

~~~java
public record ProductSuggestion(
        String id,
        String displayTitle,
        String snippet,
        float score) {
}
~~~

Mapper chọn fragment đầu tiên và dùng nội dung gốc làm fallback:

~~~java
public static ProductSuggestion toSuggestion(SearchHit<Product> hit) {
    Product product = hit.getContent();

    String displayTitle = hit.getHighlightField("title").stream()
            .findFirst()
            .orElse(product.getTitle());

    String snippet = hit.getHighlightField("description").stream()
            .findFirst()
            .orElse(product.getDescription());

    return new ProductSuggestion(
            hit.getId(),
            displayTitle,
            snippet,
            hit.getScore());
}
~~~

Nếu highlighter trả nhiều fragment, không nên nối tất cả bằng một dấu cách một cách tùy tiện. Mỗi fragment có thể là một đoạn ở vị trí khác nhau trong nội dung gốc. Giữ List<String> nếu giao diện cần hiển thị nhiều đoạn hoặc để người dùng mở rộng kết quả.

## 8. Ánh xạ khi đã dùng MapStruct hoặc mapper riêng cho entity

Nếu dự án đã có mapper chuyển Product thành ProductDto, có thể tái sử dụng mapper đó và bổ sung metadata của SearchHit ở lớp search mapper:

~~~java
public record ProductSearchDto(
        ProductDto product,
        Map<String, List<String>> highlights,
        float score,
        String documentId) {
}
~~~

~~~java
public ProductSearchDto toSearchDto(SearchHit<Product> hit) {
    ProductDto productDto = productMapper.toDto(hit.getContent());

    return new ProductSearchDto(
            productDto,
            hit.getHighlightFields(),
            hit.getScore(),
            hit.getId());
}
~~~

Cách này giữ mapper entity hiện có độc lập với Elasticsearch search metadata. Nếu DTO công khai không nên phụ thuộc tên field nội bộ, hãy chuyển map highlight thành các property rõ ràng như titleFragments và descriptionFragments thay vì trả một map tổng quát.

## 9. Cấu hình highlight bằng ElasticsearchOperations

Khi query được tạo động trong service, có thể cấu hình highlight bằng HighlightQuery thay vì annotation trên repository method.

Spring Data Elasticsearch cung cấp các lớp trong package org.springframework.data.elasticsearch.core.query.highlight:

- Highlight: chứa danh sách field cần highlight và tham số chung.
- HighlightField: xác định field cần highlight.
- HighlightParameters: chứa tag, kích thước fragment, số fragment, encoder và các tham số chung.
- HighlightQuery: kết hợp định nghĩa highlight với kiểu entity.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.HighlightQuery;
import org.springframework.data.elasticsearch.core.query.highlight.Highlight;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightField;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightParameters;

public SearchHits<Product> searchWithHighlight(
        ElasticsearchOperations operations,
        String text) {

    HighlightParameters parameters = HighlightParameters.builder()
            .withPreTags("<mark>")
            .withPostTags("</mark>")
            .withEncoder("html")
            .withFragmentSize(140)
            .withNumberOfFragments(3)
            .build();

    Highlight highlight = new Highlight(
            parameters,
            List.of(
                    new HighlightField("title"),
                    new HighlightField("description")));

    HighlightQuery highlightQuery = new HighlightQuery(highlight, Product.class);

    CriteriaQuery query = new CriteriaQuery(
            Criteria.where("title").matches(text));
    query.setHighlightQuery(highlightQuery);

    return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products"));
}
~~~

HighlightParameters.builder() tạo tham số chung. Highlight ghép tham số với danh sách field. HighlightQuery gắn cấu hình với entity Product, sau đó setHighlightQuery thêm nó vào query được thực thi qua ElasticsearchOperations.

API này hữu ích khi danh sách field hoặc tùy chọn highlight phụ thuộc request. Nếu chỉ có một cấu hình cố định, @Highlight trên repository method thường ngắn và dễ đọc hơn.

## 10. Những tham số highlight thường dùng

Elasticsearch có nhiều tùy chọn điều khiển cách tạo fragment. Spring Data expose nhiều tùy chọn này qua @HighlightParameters và builder HighlightParameters/HighlightFieldParameters.

| Tham số | Tác dụng |
|---|---|
| preTags | Tag đặt trước đoạn khớp, mặc định thường là <em> |
| postTags | Tag đặt sau đoạn khớp, mặc định thường là </em> |
| fragmentSize | Kích thước fragment mục tiêu theo ký tự |
| numberOfFragments | Số fragment tối đa trả về cho field |
| numberOfFragments = 0 | Trả toàn bộ nội dung field thay vì cắt thành fragment |
| noMatchSize | Trả một đoạn đầu field khi không có fragment khớp |
| order = "score" | Sắp xếp fragment theo điểm liên quan |
| requireFieldMatch | Mặc định true, chỉ highlight field có match tương ứng |
| type | Chọn highlighter như unified, plain hoặc fvh |
| encoder | html để encode nội dung fragment trước khi thêm tag highlight |
| matchedFields | Kết hợp match từ nhiều field để highlight một field đích, tùy highlighter |
| highlightQuery | Dùng query riêng để quyết định nội dung được highlight |

Ví dụ REST request tương ứng:

~~~http
GET products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless keyboard",
      "fields": ["title", "description"]
    }
  },
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "encoder": "html",
    "fields": {
      "title": {
        "number_of_fragments": 0
      },
      "description": {
        "fragment_size": 140,
        "number_of_fragments": 3,
        "order": "score"
      }
    }
  }
}
~~~

### 10.1. Khi nào dùng number_of_fragments = 0?

Với field ngắn như title, địa chỉ hoặc tên, có thể không cần chia thành fragment. number_of_fragments: 0 yêu cầu trả toàn bộ nội dung field đã highlight; khi đó fragment_size bị bỏ qua.

Với description dài, đặt fragment_size và number_of_fragments để chỉ trả một vài đoạn liên quan. Điều này giảm kích thước response và tránh gửi toàn bộ nội dung dài về client.

### 10.2. no_match_size

Mặc định nếu không có fragment khớp, Elasticsearch không trả nội dung highlight cho field đó. no_match_size cho phép trả một đoạn ở đầu field để làm preview dù không có term được highlight.

Đoạn no_match_size không có nghĩa field đã khớp query. Nếu DTO dùng fallback từ fragment sang source, hãy phân biệt fragment thực sự highlight với preview không có tag.

### 10.3. require_field_match

Mặc định require_field_match = true: field cần có match tương ứng mới được highlight. Đặt false có thể yêu cầu highlighter tìm term của query trên các field được chỉ định rộng hơn.

Không nên đặt false chỉ để “có highlight ở mọi field”. Nó có thể tạo fragment không phản ánh đúng field hoặc logic tìm kiếm mà ứng dụng muốn trình bày. Hãy kiểm tra kết quả với query thực tế.

## 11. Các loại highlighter

Elasticsearch hỗ trợ các highlighter chính:

| Highlighter | Đặc điểm | Lưu ý |
|---|---|---|
| unified | Dùng Lucene Unified Highlighter; mặc định cho text và keyword | Hỗ trợ phrase và multi-term query; thường là lựa chọn mặc định tốt |
| plain | Dùng Lucene Highlighter truyền thống | Phù hợp query đơn giản; có thể tốn thêm thời gian khi xử lý nhiều field/document |
| fvh | Fast Vector Highlighter | Cần term_vector: with_positions_offsets, làm tăng dung lượng index |
| semantic | Dành cho field semantic/semantic_text | Tạo fragment theo semantic similarity; khác cách highlight term truyền thống |

Với fvh, mapping cần bật term vectors:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "term_vector": "with_positions_offsets"
      }
    }
  }
}
~~~

Unified highlighter có thể sử dụng offsets từ postings nếu mapping đặt index_options: offsets, hoặc dùng term vectors nếu có. Với nội dung lớn, lựa chọn offset strategy có thể ảnh hưởng hiệu năng và dung lượng index. Không bật term vectors cho mọi field chỉ để thử highlighter; hãy đo và chọn theo workload.

## 12. Highlight không làm thay đổi entity hoặc kết quả match

Highlight là dữ liệu trình bày, không phải dữ liệu được lưu lại trong index. Nó không thay đổi _source, không sửa entity và không ảnh hưởng document có khớp query hay không.

Một số hệ quả:

- Entity trong hit.getContent() vẫn chứa nội dung gốc.
- Highlight fragments chỉ tồn tại trong metadata của search hit.
- Nếu không bật highlight cho field, getHighlightField(field) có thể trả danh sách rỗng.
- Highlight không phải một dạng score; score vẫn lấy từ hit.getScore().
- Không lưu fragment có tag vào database như nội dung gốc của sản phẩm.

Đặc biệt, highlighter không phải lúc nào cũng phản ánh đầy đủ logic Boolean của query. Với các query phức tạp như nested bool hoặc minimum_should_match, một số term có thể được highlight dù đoạn đó không tương ứng với toàn bộ điều kiện Boolean làm document khớp. Nếu giao diện cần giải thích chính xác vì sao document khớp, hãy dùng Explain API; không dùng highlight như bằng chứng duy nhất về logic match.

## 13. Bảo vệ nội dung highlight khi hiển thị HTML

Highlight fragments thường chứa tag như <em>...</em> hoặc tag tùy chỉnh từ preTags/postTags. Nội dung gốc trong _source có thể đến từ người dùng hoặc nguồn bên ngoài. Không nên mặc định rằng mọi chuỗi fragment đều an toàn để đưa trực tiếp vào innerHTML hoặc cơ chế render HTML thô.

Các lựa chọn:

1. Dùng encoder = "html" để highlighter encode phần nội dung trước khi chèn tag highlight.
2. Nếu render HTML, chỉ cho phép các tag highlight đã định nghĩa bằng một HTML sanitizer theo allow-list.
3. Nếu giao diện có thể xử lý dữ liệu dạng cấu trúc, chuyển fragment thành các đoạn text và đoạn matched rồi render bằng text node/component an toàn.
4. Không cho người dùng điều khiển preTags hoặc postTags tùy ý.

Ví dụ cấu hình encoder trong annotation:

~~~java
@Highlight(
    fields = @HighlightField(name = "description"),
    parameters = @HighlightParameters(
        preTags = {"<mark>"},
        postTags = {"</mark>"},
        encoder = "html"
    )
)
SearchHits<Product> searchDescription(String text);
~~~

encoder = "html" giúp encode nội dung fragment trước khi thêm tag. Ở frontend vẫn nên áp dụng quy tắc render HTML an toàn của framework và ứng dụng, đặc biệt khi có nội dung đến từ nhiều nguồn.

## 14. Highlight cho multi-fields và nested data

### 14.1. Multi-fields

Một property có thể được lập chỉ mục thành nhiều subfield, ví dụ title dạng text và title.keyword dạng keyword. Khi cần kết hợp match từ nhiều field phân tích để highlight một field, Elasticsearch có tùy chọn matched_fields.

Ví dụ cấu hình REST:

~~~json
{
  "highlight": {
    "fields": {
      "title": {
        "matched_fields": ["title", "title.english"]
      }
    }
  }
}
~~~

Khả năng kết hợp và điều kiện mapping phụ thuộc highlighter. Với fvh, các field được kết hợp phải có term vectors phù hợp. Spring Data expose matchedFields qua tham số highlight field trong các phiên bản hiện hành; nếu cần cấu trúc phức tạp, kiểm tra Javadoc và request thực tế.

### 14.2. Nested objects và inner hits

Nếu field nằm trong object có mapping nested, query thường dùng nested query và có thể cấu hình highlight trong inner_hits. Kết quả nested được trả trong metadata inner hits của document cha.

Spring Data SearchHit có getInnerHits() và getInnerHits(name). Giá trị trả về là SearchHits<?> cho inner hits; nếu inner hit được ánh xạ sang entity nested, content có thể là kiểu entity đó, nếu không có thể là SearchDocument.

Khi DTO cần fragment của nested field, phải đọc SearchHit bên trong inner hits tương ứng, thay vì tìm fragment đó ở map highlight cấp document cha. Tên inner hit và kiểu content cần khớp với cấu hình query.

## 15. Ánh xạ DTO với nested inner hits

Giả sử document có nested comments và query trả inner hits tên comments:

~~~json
{
  "query": {
    "nested": {
      "path": "comments",
      "query": {
        "match": {
          "comments.text": "wireless"
        }
      },
      "inner_hits": {
        "name": "matchingComments",
        "highlight": {
          "fields": {
            "comments.text": {}
          }
        }
      }
    }
  }
}
~~~

Ở tầng Spring Data, đọc inner hits theo tên đã khai báo:

~~~java
SearchHits<?> innerHits = parentHit.getInnerHits("matchingComments");

if (innerHits != null) {
    for (SearchHit<?> innerHit : innerHits) {
        Map<String, List<String>> highlights = innerHit.getHighlightFields();
        // Map nested content and its highlight fragments to a nested DTO.
    }
}
~~~

Đây là trường hợp nâng cao; nếu chỉ highlight field top-level, không cần xử lý inner hits. Khi triển khai nested DTO, hãy kiểm tra mapping và response thực tế vì kiểu content phụ thuộc entity mapping và query configuration.

## 16. Vì sao không thấy highlight?

Nếu getHighlightField("title") trả danh sách rỗng, hãy kiểm tra lần lượt:

1. Repository method hoặc Query đã bật highlight chưa?
2. Field có nằm trong danh sách @HighlightField/Highlight.fields không?
3. Query có thực sự match field đó không, nhất là khi require_field_match mặc định là true?
4. Tên field dùng trong annotation có phải property name của entity không?
5. Mapping field có phải kiểu hỗ trợ highlighter và có nội dung được lập chỉ mục không?
6. Query analyzer và index analyzer có tạo token tương ứng không?
7. Có highlight_query riêng làm khác điều kiện match không?
8. Field có quá dài và vượt giới hạn index.highlight.max_analyzed_offset không?
9. Query có trả inner hits, khiến highlight nằm ở hit lồng nhau không?
10. Bạn có đang trả SearchHit/SearchHits hay chỉ trả entity và làm mất metadata không?

Có thể xem request/response REST tương đương để xác định lỗi nằm ở Elasticsearch hay ở bước mapping của Spring Data. Nếu Elasticsearch trả highlight nhưng DTO rỗng, kiểm tra key trong hit.getHighlightFields() và mapper.

## 17. Kiểm thử việc đọc highlight và ánh xạ DTO

Một integration test nên kiểm tra cả hai phần: entity content và highlight metadata.

Ví dụ test minh họa:

~~~java
@Test
void returnsProductWithHighlightFragments() {
    repository.save(new Product(
            "p-100",
            "Wireless Keyboard",
            "A compact wireless keyboard for travel.",
            "keyboards"));

    // Ensure the document is visible to search before asserting.
    SearchHits<Product> hits = repository.searchHighlighted("wireless");

    assertThat(hits.getSearchHits()).isNotEmpty();

    SearchHit<Product> hit = hits.getSearchHit(0);
    assertThat(hit.getContent().getTitle()).isEqualTo("Wireless Keyboard");
    assertThat(hit.getHighlightField("title")).isNotEmpty();

    ProductSearchResult dto = ProductSearchMapper.toDto(hit);
    assertThat(dto.title()).isEqualTo("Wireless Keyboard");
    assertThat(dto.titleHighlights()).isNotEmpty();
}
~~~

Đoạn test minh họa luồng kiểm tra; tên method repository, setup index và cách refresh cần khớp cấu hình dự án. Elasticsearch là hệ thống near-real-time, nên document vừa lưu có thể chưa xuất hiện ngay trong search cho tới khi shard được refresh.

Các tình huống nên kiểm thử:

- Một field có một fragment.
- Một field có nhiều fragment.
- Một field không có fragment và mapper dùng fallback.
- Field title dùng number_of_fragments = 0.
- Field dài bị chia đoạn theo fragment_size.
- Nội dung có dấu tiếng Việt, ký tự HTML và dấu nháy.
- Query match nhiều field nhưng chỉ yêu cầu highlight một field.
- Mapping có custom field name.
- Nested query có inner hits và highlight.
- DTO giữ nội dung gốc riêng với fragment đã đánh dấu.

Mock SearchHit có thể kiểm tra logic mapper, nhưng integration test với Elasticsearch thật hoặc Testcontainers mới xác nhận được highlighter tạo fragment đúng theo mapping, analyzer và Query DSL.

## 18. Thiết kế service trả DTO tìm kiếm

Có thể gom thao tác repository và mapping DTO trong service:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public ProductSearchResponse search(String text) {
        SearchHits<Product> hits = repository.searchHighlighted(text);

        List<ProductSearchResult> items = hits.getSearchHits().stream()
                .map(ProductSearchMapper::toDto)
                .toList();

        return new ProductSearchResponse(
                items,
                hits.getTotalHits(),
                hits.getMaxScore());
    }
}
~~~

Controller chỉ cần trả DTO:

~~~java
@RestController
@RequestMapping("/products")
public class ProductSearchController {

    private final ProductSearchService service;

    public ProductSearchController(ProductSearchService service) {
        this.service = service;
    }

    @GetMapping("/search")
    public ProductSearchResponse search(@RequestParam String q) {
        return service.search(q);
    }
}
~~~

Service chịu trách nhiệm chuyển metadata của Elasticsearch thành hợp đồng API. Controller không cần biết SearchHit, SearchHits hay cách Elasticsearch biểu diễn highlight.

## 19. Các lỗi thường gặp

### Repository chỉ trả List<Product>

Entity không mang metadata highlight. Hãy trả SearchHits<Product> hoặc List<SearchHit<Product>> khi cần đọc fragment.

### Tìm highlight trong entity

Highlight nằm ở SearchHit, không tự được gán vào Product. Lấy entity bằng hit.getContent() và fragment bằng hit.getHighlightField(...).

### Giả định getHighlightField luôn có ít nhất một phần tử

Một field có thể không có fragment. Kiểm tra isEmpty() hoặc dùng stream().findFirst().orElse(fallback).

### Dùng sai tên field trong @HighlightField

Annotation yêu cầu tên property của entity, không phải tên field đã đổi trong Elasticsearch mapping. Nếu dùng custom mapping name, kiểm tra key thực tế trong map highlight khi đọc.

### Ghi fragment vào entity rồi lưu lại

Fragment là dữ liệu trình bày tạm thời. Nếu gán vào entity rồi gọi save, ứng dụng có thể lưu tag HTML hoặc snippet bị cắt vào _source. Hãy giữ fragment trong DTO riêng.

### Nối các fragment thành một đoạn văn duy nhất

Mỗi fragment có thể đến từ một vùng khác nhau trong nội dung. Nối chúng có thể làm mất ngữ cảnh và tạo câu sai. Giữ danh sách hoặc chọn fragment phù hợp theo giao diện.

### Không encode hoặc sanitize nội dung HTML

Fragment có thể chứa nội dung từ document và tag highlight. Cấu hình encoder phù hợp và render bằng cơ chế an toàn của frontend.

### Dùng number_of_fragments = 0 cho field rất dài

Thiết lập này trả toàn bộ field. Chỉ dùng cho field ngắn; với nội dung dài, giới hạn số fragment và kích thước fragment.

### Highlight không giống điều kiện Bool Query

Highlighter có thể đánh dấu term nhưng không phản ánh toàn bộ logic Boolean của query. Không dùng highlight để suy luận duy nhất vì sao document được trả về.

### Chỉ kiểm thử mapper mà không kiểm thử Elasticsearch

Mapper test không xác nhận highlighter tạo fragment. Cần integration test để kiểm tra request highlight, mapping, analyzer và response thực tế.

## 20. Quy trình triển khai

Khi thêm highlight vào API tìm kiếm, có thể thực hiện theo trình tự:

1. Xác định các field văn bản cần highlight và kiểm tra mapping/analyzer.
2. Bật highlight bằng @Highlight cho repository method hoặc HighlightQuery cho query động.
3. Chọn preTags, postTags, fragmentSize, numberOfFragments và encoder theo giao diện.
4. Dùng return type SearchHits<T> hoặc List<SearchHit<T>> để giữ metadata.
5. Đọc fragment bằng getHighlightField(field) hoặc getHighlightFields().
6. Lấy dữ liệu gốc từ getContent() và metadata khác từ SearchHit.
7. Ánh xạ từng hit sang DTO có property riêng cho source content và highlight fragments.
8. Xử lý danh sách rỗng và fallback rõ ràng.
9. Giữ fragment tách khỏi entity để không ghi ngược tag/snippet vào _source.
10. Encode/sanitize nội dung trước khi render HTML.
11. Kiểm thử một fragment, nhiều fragment, không có fragment, custom field name và nested inner hits.
12. Đo kích thước response và chi phí highlight trên field dài trước khi bật rộng rãi.

## 21. Tổng kết

Spring Data Elasticsearch đặt highlight fragments trong metadata của SearchHit<T>, có thể đọc bằng getHighlightFields() hoặc getHighlightField(field). SearchHit.getContent() vẫn là entity được ánh xạ từ _source; fragment highlight không tự trở thành thuộc tính entity. Vì vậy, repository method cần trả SearchHits<T> hoặc SearchHit<T> khi ứng dụng muốn giữ thông tin highlight.

Để trả dữ liệu qua REST API, hãy ánh xạ từng SearchHit thành DTO: lấy ID, score và nội dung gốc từ hit/entity, sau đó lấy danh sách fragment theo từng field. Giữ source content và highlight fragments riêng biệt, xử lý danh sách rỗng và dùng fallback phù hợp. @Highlight phù hợp với repository query cố định; HighlightQuery cùng ElasticsearchOperations phù hợp với query được xây động. Cấu hình fragment, highlighter và encoder theo nội dung, đồng thời xử lý HTML an toàn ở tầng hiển thị.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Repository method annotations and @Highlight](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repositories.html)
- [Spring Data Elasticsearch – SearchHit<T> API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHit.html)
- [Spring Data Elasticsearch – SearchHits<T> API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch – @HighlightParameters API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/HighlightParameters.html)
- [Spring Data Elasticsearch – HighlightQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/HighlightQuery.html)
- [Elasticsearch – Highlighting](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/highlighting)
- [Elasticsearch – Highlighting settings](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/highlighting-settings)
- [Elasticsearch – Highlighting examples](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/highlighting-examples)
