# Phân biệt nội dung Document và metadata của SearchHit

Khi tìm kiếm bằng Spring Data Elasticsearch, một kết quả không chỉ có dữ liệu của document. Elasticsearch còn trả về thông tin mô tả hit tìm được, chẳng hạn index chứa document, ID, điểm relevance, giá trị sort, highlight và các nested hit liên quan.

Spring Data Elasticsearch tách phần dữ liệu được ánh xạ thành entity khỏi metadata của kết quả tìm kiếm. Entity đại diện cho nội dung document; SearchHit<T> bọc entity đó cùng metadata của một hit; SearchHits<T> chứa danh sách hit và metadata ở cấp toàn bộ response tìm kiếm.

Phân biệt các lớp này giúp ứng dụng không nhầm _score với field trong document, không làm mất highlight khi chuyển kết quả sang DTO, không ghi nhầm metadata vào _source, và biết khi nào nên dùng SearchHit<T> thay vì chỉ lấy T.

## 1. Một kết quả tìm kiếm có nhiều lớp thông tin

Giả sử Elasticsearch trả về một hit có cấu trúc rút gọn:

~~~json
{
  "_index": "catalog-products-v3",
  "_id": "product-1001",
  "_score": 4.82,
  "_source": {
    "sku": "KB-1042",
    "name": "Mechanical Keyboard",
    "price": 129.5,
    "category": "accessories"
  },
  "sort": [
    129.5,
    "product-1001"
  ],
  "highlight": {
    "name": [
      "Mechanical <em>Keyboard</em>"
    ]
  }
}
~~~

Response có hai nhóm thông tin chính:

| Phần response Elasticsearch | Ý nghĩa | Cách Spring Data thường biểu diễn |
| --- | --- | --- |
| _source | Nội dung document đã lưu | SearchHit<T>.getContent() sau khi mapping |
| _id | ID của document trong index | SearchHit<T>.getId() và có thể được ánh xạ vào property @Id |
| _index | Index vật lý trả về hit | SearchHit<T>.getIndex() |
| _score | Điểm relevance của hit | SearchHit<T>.getScore() |
| sort | Giá trị được dùng để sắp xếp hit | SearchHit<T>.getSortValues() |
| highlight | Các đoạn văn bản được đánh dấu | SearchHit<T>.getHighlightFields() |
| inner_hits | Hit con từ nested hoặc parent/child query | SearchHit<T>.getInnerHits() |
| matched_queries | Tên các named query đã khớp | Metadata của SearchHit<T> nếu query sử dụng named query |

Phần _source là dữ liệu nghiệp vụ. Các trường như _score, sort và highlight mô tả kết quả của một lần tìm kiếm. Chúng không tự trở thành field của document được lưu.

## 2. Phân biệt Document, entity và SearchHit

Trong Spring Data Elasticsearch, từ “document” có thể chỉ nội dung JSON được lưu trong Elasticsearch hoặc kiểu Document của Spring Data.

### 2.1. Document là cấu trúc dữ liệu lưu trữ

org.springframework.data.elasticsearch.core.document.Document là kiểu biểu diễn document dạng Map-like mà Spring Data dùng trong các API mapping và thao tác cấp thấp. Nó chứa các cặp tên field và giá trị tương ứng với nội dung document.

Ví dụ về nội dung document:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;

Document document = Document.create();
document.put("sku", "KB-1042");
document.put("name", "Mechanical Keyboard");
document.put("price", 129.5);
~~~

Đây là phần dữ liệu tương ứng với nội dung document. Nó không phải toàn bộ response tìm kiếm và không mang ý nghĩa như điểm relevance, highlight hoặc sort values.

### 2.2. Entity là mô hình Java của nội dung document

Spring Data dùng mapping metadata và MappingElasticsearchConverter để chuyển đổi giữa entity Java và document representation:

~~~text
                 Khi ghi
Entity Java  ----------------->  Document / _source
                 Converter

                 Khi đọc
Entity Java  <-----------------  Document / _source
                 Converter
~~~

Ví dụ:

~~~java
@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    private String sku;
    private String name;
    private double price;

    // Constructors, getters và setters
}
~~~

Entity ProductDocument mô tả dữ liệu ứng dụng muốn đọc/ghi. Các annotation như @Id, @Field, @Transient và custom conversions ảnh hưởng cách Spring Data ánh xạ entity.

### 2.3. SearchHit là một kết quả tìm kiếm đơn lẻ

SearchHit<T> bao bọc nội dung đã ánh xạ thành kiểu T và metadata gắn với hit đó:

~~~text
SearchHit<ProductDocument>
├── content: ProductDocument
├── id: product-1001
├── index: catalog-products-v3
├── score: 4.82
├── sortValues: [129.5, product-1001]
├── highlightFields
└── innerHits
~~~

Vì vậy, SearchHit<ProductDocument> không phải một entity khác và cũng không phải bản sao của _source. Nó là wrapper kết quả tìm kiếm.

### 2.4. SearchHits là toàn bộ tập kết quả

SearchHits<T> chứa nhiều SearchHit<T> cùng thông tin ở cấp response:

~~~text
SearchHits<ProductDocument>
├── totalHits
├── maxScore
├── executionDuration
├── aggregations
├── suggest
└── searchHits
    ├── SearchHit<ProductDocument>
    ├── SearchHit<ProductDocument>
    └── SearchHit<ProductDocument>
~~~

SearchHits<T> trả lời câu hỏi về toàn bộ lần tìm kiếm: có bao nhiêu hit, điểm cao nhất là bao nhiêu, có aggregation hoặc suggest result hay không và các hit cụ thể là gì.

## 3. SearchHit<T>: nội dung và metadata của từng hit

Các thuộc tính thường dùng của SearchHit<T>:

| Phương thức | Ý nghĩa |
| --- | --- |
| getContent() | Entity hoặc projection được ánh xạ từ nội dung document |
| getId() | Elasticsearch document ID |
| getIndex() | Tên index Elasticsearch trả về cho hit |
| getScore() | Điểm relevance của hit |
| getSortValues() | Danh sách giá trị sort theo thứ tự các sort clause |
| getHighlightFields() | Map tên field sang các đoạn highlight |
| getInnerHits() | Các nhóm nested/child hits theo tên |
| getMatchedQueries() | Tên các named query đã khớp, nếu có |
| getExplanation() | Thông tin giải thích điểm khi request bật explain và phiên bản API cung cấp |

API chi tiết có thể thay đổi theo phiên bản Spring Data Elasticsearch. Khi sử dụng thuộc tính ít phổ biến, hãy kiểm tra Javadoc của dependency thực tế.

### 3.1. Lấy content và metadata

Ví dụ thực hiện tìm kiếm qua ElasticsearchOperations:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> results =
    operations.search(
        query,
        ProductDocument.class,
        IndexCoordinates.of("catalog-products")
    );

for (SearchHit<ProductDocument> hit : results.getSearchHits()) {
    ProductDocument product = hit.getContent();

    String documentId = hit.getId();
    String indexName = hit.getIndex();
    float score = hit.getScore();

    // Xử lý nội dung entity và metadata hit theo mục đích riêng.
}
~~~

Nếu chỉ cần dữ liệu nghiệp vụ, dùng getContent(). Nếu cần ID, điểm relevance, highlight hoặc sort values, giữ SearchHit<T> cho tới khi đã trích xuất xong metadata cần thiết.

### 3.2. ID của hit và property @Id

Elasticsearch có trường metadata _id nằm ngoài _source. Spring Data dùng annotation @Id để liên kết property ID của entity với Elasticsearch document ID.

~~~java
@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    private String sku;
    private String name;
}
~~~

hit.getId() đọc ID từ metadata của hit. hit.getContent().getId() đọc property ID sau khi Spring Data ánh xạ metadata vào entity. Với entity được mapping đúng, hai giá trị này thường tương ứng.

Không nên giả định ID nhất thiết phải xuất hiện trong _source. Trong mapping thông thường, @Id được dùng làm document ID; nó không phải một field source thông thường. Nếu nghiệp vụ cần lưu thêm một mã định danh trong nội dung document, hãy khai báo field riêng, chẳng hạn sku.

### 3.3. Index của hit và tên alias ứng dụng sử dụng

Ứng dụng có thể tìm kiếm thông qua alias như catalog-products, trong khi Elasticsearch trả _index là index vật lý chứa document, chẳng hạn catalog-products-v3.

Điều này hữu ích khi vận hành index theo version. Không nên dùng hit.getIndex() như tên alias logic của ứng dụng; nó mô tả index vật lý được trả về cho hit.

## 4. Score và thứ tự kết quả

_score là điểm relevance do Elasticsearch tính theo query và cấu hình similarity. SearchHit.getScore() cung cấp giá trị này cho ứng dụng.

### 4.1. Score không phải field nghiệp vụ

Ví dụ, sản phẩm có rating = 4.8 và score = 7.2:

- rating là dữ liệu nghiệp vụ trong _source.
- score là điểm relevance của một hit trong một lần search cụ thể.

Không ghi score trở lại entity như thể đó là rating hoặc giá trị cố định của sản phẩm.

### 4.2. Score phụ thuộc query

Một document có thể có score khác nhau khi:

- Từ khóa tìm kiếm thay đổi.
- Query dùng match, multi_match, phrase hoặc bool khác nhau.
- Analyzer hoặc similarity thay đổi.
- Trọng số boost thay đổi.
- Các điều kiện scoring khác nhau.

Do đó, không nên so sánh score của hai request không tương đương như một chỉ số chất lượng cố định.

### 4.3. Filter context và score

Điều kiện trong bool.filter được dùng để lọc mà không đóng góp relevance score. Ví dụ, range giá và trạng thái tồn kho thường nằm trong filter, trong khi match query trên tên sản phẩm nằm trong must.

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      ],
      "filter": [
        {
          "range": {
            "price": {
              "gte": 50,
              "lte": 200
            }
          }
        },
        {
          "term": {
            "available": true
          }
        }
      ]
    }
  }
}
~~~

Trong trường hợp này, score chủ yếu phản ánh mức khớp văn bản; giá và available chỉ lọc kết quả.

### 4.4. Sort values không phải score

Nếu query sắp xếp theo giá:

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

Kết quả được xếp theo price. getSortValues() trả các giá trị sort của hit theo thứ tự sort clause. Giá trị này không đồng nghĩa với getScore().

Khi phân trang sâu bằng search_after, ứng dụng thường cần giữ sort values của hit cuối trang để làm con trỏ cho trang tiếp theo. Sort phải ổn định và nên có tie-breaker để tránh các hit cùng giá trị sort bị đổi vị trí giữa các request.

## 5. Highlight fields là metadata của hit

Highlight giúp trả các đoạn văn bản có chứa phần khớp với query, thường kèm tag đánh dấu. Ví dụ:

~~~json
{
  "highlight": {
    "name": [
      "Mechanical <em>Keyboard</em>"
    ],
    "description": [
      "A compact <em>keyboard</em> for daily use"
    ]
  }
}
~~~

Spring Data cung cấp các highlight fragment qua SearchHit.getHighlightFields(), thường dưới dạng map từ tên field tới danh sách chuỗi fragment.

~~~java
for (SearchHit<ProductDocument> hit : results) {
    ProductDocument product = hit.getContent();

    List<String> nameFragments =
        hit.getHighlightFields().get("name");

    // Dùng fragment để hiển thị phần văn bản khớp.
}
~~~

### 5.1. Highlight không thay thế nội dung document

Giá trị product.getName() vẫn là nội dung được ánh xạ từ _source. Highlight là đoạn trích được Elasticsearch tạo cho lần tìm kiếm hiện tại.

Ví dụ:

| Nguồn | Giá trị |
| --- | --- |
| Entity name | Mechanical Keyboard |
| Highlight fragment | Mechanical <em>Keyboard</em> |

Highlight có thể:

- Chỉ chứa một phần văn bản thay vì toàn bộ field.
- Chứa markup hoặc tag do ứng dụng cấu hình.
- Có nhiều fragment cho cùng một field.
- Không xuất hiện nếu field không được highlight hoặc không có đoạn phù hợp.

Không dùng highlight fragment để ghi đè nội dung chuẩn trong entity hoặc lưu ngược về Elasticsearch.

### 5.2. Bảo vệ khi hiển thị highlight

Nếu highlight fragment được đưa lên giao diện web, cần quy định rõ tag nào được phép render. Không nên coi mọi chuỗi trả về từ Elasticsearch là HTML an toàn, đặc biệt khi nội dung gốc do người dùng nhập.

Một lựa chọn an toàn là dùng tag highlight cố định, escape nội dung gốc theo framework frontend hoặc chuyển fragment thành cấu trúc DTO gồm đoạn text và trạng thái matched.

## 6. Inner hits cũng là metadata của hit cha

Khi query dùng nested hoặc parent/child, Elasticsearch có thể trả các hit con phù hợp trong phần inner_hits.

Ví dụ:

~~~json
{
  "_index": "catalog-products-v3",
  "_id": "product-1001",
  "_source": {
    "sku": "KB-1042",
    "offers": [
      { "seller": "seller-a", "price": 120 },
      { "seller": "seller-b", "price": 95 }
    ]
  },
  "inner_hits": {
    "matching_offers": {
      "hits": {
        "hits": [
          {
            "_nested": {
              "field": "offers",
              "offset": 1
            },
            "_source": {
              "seller": "seller-b",
              "price": 95
            }
          }
        ]
      }
    }
  }
}
~~~

Hit cha vẫn có ProductDocument làm content. Nhóm matching_offers là metadata mở rộng chứa các nested hit khớp.

Spring Data biểu diễn các nhóm này qua map inner hits:

~~~java
for (SearchHit<ProductDocument> productHit : results) {
    SearchHits<?> matchingOffers =
        productHit.getInnerHits().get("matching_offers");

    if (matchingOffers == null) {
        continue;
    }

    for (SearchHit<?> offerHit : matchingOffers.getSearchHits()) {
        Object matchedContent = offerHit.getContent();
        // Chuyển sang kiểu/DTO phù hợp với mapping và phiên bản.
    }
}
~~~

Tên map key phải khớp với tên đặt trong inner_hits.name. Nếu query có nhiều nested path hoặc nhiều nhóm inner hits, đặt tên riêng cho từng nhóm để tránh nhầm lẫn.

Inner hits không tự biến kết quả chính thành danh sách document con. Ứng dụng cần đọc chúng từ từng parent hit.

## 7. SearchHits<T>: metadata ở cấp toàn bộ kết quả

SearchHits<T> đại diện cho response tìm kiếm, không chỉ là một List<T>.

Các thông tin thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| getSearchHits() | Danh sách SearchHit<T> |
| getTotalHits() | Tổng số hit được Elasticsearch báo cáo |
| getMaxScore() | Điểm lớn nhất trong kết quả |
| getAggregations() | Kết quả aggregation nếu query có yêu cầu |
| getSuggest() | Kết quả suggest nếu query có yêu cầu |
| getExecutionDuration() | Thời gian thực thi được response cung cấp |
| getScrollId() / PIT metadata | Thông tin tiếp tục hoặc đóng một số kiểu search context, tùy API và phiên bản |

Không phải mọi lần tìm kiếm đều có aggregation, suggest, scroll ID hoặc PIT ID. Kiểm tra sự hiện diện trước khi sử dụng.

### 7.1. Đọc tổng số hit và từng hit

~~~java
SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

long totalHits = results.getTotalHits();
float maxScore = results.getMaxScore();

for (SearchHit<ProductDocument> hit : results) {
    ProductDocument product = hit.getContent();
    // Xử lý từng kết quả
}
~~~

getTotalHits() là số lượng hit Elasticsearch báo cáo. Tùy cấu hình track_total_hits và giới hạn đếm của Elasticsearch, tổng số có thể là một cận dưới thay vì số đếm chính xác tuyệt đối. Nếu giao diện yêu cầu tổng số chính xác, cần cấu hình tracking phù hợp và cân nhắc chi phí.

### 7.2. Aggregations không nằm trong content

Aggregation là kết quả tổng hợp trên tập document, ví dụ số sản phẩm theo category hoặc histogram theo giá. Nó thuộc metadata cấp SearchHits, không tự xuất hiện trong entity của từng hit.

Ví dụ Query DSL:

~~~json
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
    }
  }
}
~~~

Response có hai phần:

- hits.hits: danh sách document tìm được.
- aggregations.categories: bucket thống kê theo category.

Ứng dụng đọc danh sách sản phẩm qua SearchHit<ProductDocument> và đọc aggregation qua SearchHits.getAggregations(). Cấu trúc aggregation cụ thể phụ thuộc query và aggregation container của phiên bản Spring Data Elasticsearch.

### 7.3. Suggest không phải highlight

Suggest trả các đề xuất như từ khóa gần đúng hoặc completion. Highlight trả đoạn văn bản trong document có phần khớp với query.

Hai tính năng có thể cùng xuất hiện trong một search response nhưng có mục đích khác nhau. Suggest thường được đọc từ metadata cấp SearchHits, còn highlight nằm trên từng SearchHit.

## 8. SearchHit và SearchHits khác List<Entity> như thế nào?

Nếu chỉ cần nội dung document, có thể chuyển kết quả thành danh sách entity:

~~~java
List<ProductDocument> products = results.getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

Sau bước này, các metadata của hit như score, highlight và sort values không còn nằm cùng entity trong danh sách mới. SearchHits ban đầu vẫn giữ chúng, nhưng danh sách ProductDocument không có.

| Kiểu kết quả | Giữ nội dung entity | Giữ metadata từng hit | Giữ metadata toàn response |
| --- | --- | --- | --- |
| ProductDocument | Có | Không | Không |
| List<ProductDocument> | Có, nhiều entity | Không | Không |
| SearchHit<ProductDocument> | Có, một entity | Có | Không |
| SearchHits<ProductDocument> | Có, qua các hit | Có | Có |

Chọn kiểu trả về theo nhu cầu:

- CRUD hoặc truy vấn chỉ cần dữ liệu: entity hoặc List<Entity> thường đủ.
- Trang kết quả cần score, highlight hoặc sort values: giữ SearchHit<Entity>.
- Trang tìm kiếm cần cả tổng hit, aggregation, suggest và metadata từng hit: giữ SearchHits<Entity>.

## 9. Repository có thể trả về SearchHit và SearchHits

Spring Data Elasticsearch hỗ trợ các kiểu trả về tìm kiếm để giữ metadata, tùy phương thức và phiên bản module.

Ví dụ repository:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<SearchHit<ProductDocument>> findByName(String name);

    SearchHits<ProductDocument> findByCategory(String category);
}
~~~

Với query method trả về SearchHit<T> hoặc SearchHits<T>, ứng dụng có thể tiếp cận metadata tìm kiếm. Cần xác nhận kiểu trả về được hỗ trợ cho query method cụ thể trong phiên bản Spring Data Elasticsearch đang sử dụng.

Nếu cần kiểm soát chính xác query DSL, sort, highlight hoặc aggregation, dùng ElasticsearchOperations.search(...) với NativeQuery thường rõ ràng hơn việc cố biểu diễn mọi thứ bằng tên phương thức repository.

## 10. SearchPage và Page

Spring Data có thể chuyển SearchHits<T> thành kiểu page để tích hợp với abstraction phân trang của Spring Data Commons.

Page<T> thường chứa content, số trang, kích thước trang và tổng số phần tử. Nếu content là entity T, metadata riêng của từng hit có thể bị mất. Với kết quả tìm kiếm cần giữ metadata, kiểu SearchPage<T> giữ nội dung dưới dạng SearchHit<T>.

Ví dụ khái quát:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.SearchPage;
import org.springframework.data.elasticsearch.core.SearchHitSupport;

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);

SearchPage<ProductDocument> page =
    SearchHitSupport.searchPageFor(hits, pageable);
~~~

SearchPage<T> cung cấp cơ chế phân trang cùng các search hit. Kiểm tra API của phiên bản dự án nếu dùng adapter page hoặc kiểu trả về repository cụ thể.

Không nên chuyển ngay SearchHits<T> thành Page<T> nếu giao diện cần score, highlight hoặc inner hits. Hãy xác định metadata nào phải được giữ trong contract API trước khi unwrap content.

## 11. Source filtering và nội dung entity không đầy đủ

Elasticsearch cho phép giới hạn field được trả về trong _source. Điều này giảm lượng dữ liệu truyền qua mạng, nhưng ảnh hưởng trực tiếp đến entity được Spring Data ánh xạ.

Ví dụ chỉ lấy SKU và tên:

~~~json
{
  "_source": [
    "sku",
    "name"
  ],
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Khi Spring Data chuyển _source đã lọc thành ProductDocument, các property không được trả về có thể là null hoặc giá trị mặc định. getContent() lúc này là entity được dựng từ source một phần, không phải toàn bộ document ban đầu.

### 11.1. Không lưu lại entity partial một cách tùy tiện

Giả sử entity có sku, name, price và description. Query chỉ trả sku và name. Nếu ứng dụng lấy entity partial rồi gọi repository.save(entity), các field bị thiếu có thể bị ghi thành null hoặc mất giá trị cũ tùy mapping và hành vi cập nhật.

Để tránh lỗi:

- Dùng projection/DTO riêng cho kết quả chỉ đọc một số field.
- Không gọi save trên entity được tạo từ source filtering nếu chưa nạp đầy đủ dữ liệu.
- Nếu cần cập nhật một phần, dùng API partial update phù hợp.
- Nếu cần entity đầy đủ, không loại field khỏi _source.

### 11.2. Stored fields và _source

_source là nội dung JSON gốc được lưu cùng document (nếu được bật). stored_fields là các field được cấu hình lưu riêng để trả về. Hai cơ chế không giống nhau.

Nếu _source bị tắt hoặc chỉ lấy một phần, việc mapping đầy đủ entity có thể không khả thi. Khi thiết kế index, hãy xác định rõ yêu cầu đọc dữ liệu và cách ứng dụng cần tái tạo entity.

## 12. Chuyển SearchHit thành DTO response

Không nên trả trực tiếp SearchHit<T> hoặc SearchHits<T> từ controller nếu API công khai chỉ cần một cấu trúc response ổn định. Kiểu Spring Data là abstraction persistence/search, không nhất thiết là hợp đồng API phù hợp cho frontend.

Có thể tạo DTO giữ riêng phần content và metadata cần thiết:

~~~java
public record ProductSearchItem(
    String id,
    String sku,
    String name,
    double price,
    float score,
    List<String> nameHighlights
) {}

public record ProductSearchResponse(
    long totalHits,
    List<ProductSearchItem> items
) {}
~~~

Mapper:

~~~java
private ProductSearchItem toSearchItem(
        SearchHit<ProductDocument> hit) {

    ProductDocument product = hit.getContent();

    List<String> highlights = hit.getHighlightFields()
        .getOrDefault("name", List.of());

    return new ProductSearchItem(
        hit.getId(),
        product.getSku(),
        product.getName(),
        product.getPrice(),
        hit.getScore(),
        highlights
    );
}
~~~

Service:

~~~java
public ProductSearchResponse search(NativeQuery query) {
    SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

    List<ProductSearchItem> items = hits.getSearchHits()
        .stream()
        .map(this::toSearchItem)
        .toList();

    return new ProductSearchResponse(
        hits.getTotalHits(),
        items
    );
}
~~~

Ví dụ DTO chỉ giữ những trường mà API thực sự cần. Nếu API cần sort values, inner hits hoặc aggregation, hãy thiết kế trường DTO tương ứng thay vì serialize toàn bộ object nội bộ của Spring Data.

## 13. Không trộn metadata tìm kiếm vào entity

Một cách làm dễ gây nhầm lẫn là thêm các property như score, highlight, indexName hoặc sortValues vào entity chỉ để nhận kết quả search.

Ví dụ không nên thiết kế entity persistence như sau:

~~~java
@Document(indexName = "catalog-products")
public class ProductDocument {

    private String name;
    private double price;

    // Không nên coi các giá trị dưới đây là field nghiệp vụ của document
    private Float score;
    private String highlight;
    private String indexName;
}
~~~

Các giá trị này thuộc metadata của hit, không phải nội dung document. Đưa chúng vào entity có thể khiến:

- Mapping converter xem chúng như field persistence.
- Index nhận các field không thuộc schema nghiệp vụ.
- Giá trị metadata cũ bị lưu lại hoặc bị ghi đè.
- Entity trở nên phụ thuộc vào một lần tìm kiếm cụ thể.

Giữ metadata ở SearchHit<T> và chuyển sang DTO response khi cần.

## 14. Highlight, score và sort có vòng đời khác nhau

Ba loại metadata này đều thuộc hit nhưng có semantics khác nhau:

| Metadata | Được tạo từ đâu? | Phụ thuộc điều gì? | Có nên lưu vào document? |
| --- | --- | --- | --- |
| Score | Bộ máy scoring của Elasticsearch | Query, analyzer, similarity, boost và dữ liệu | Không |
| Highlight | Highlight subsystem của Elasticsearch | Query, field, analyzer và highlight configuration | Không |
| Sort values | Các sort clause của search request | Thứ tự sort và giá trị field trên hit | Không |

Ví dụ:

- Một document có thể có score cao khi tìm keyboard nhưng thấp khi tìm mouse.
- Highlight của field name có thể khác giữa hai từ khóa.
- Sort values có thể là [129.5, "product-1001"] khi sort theo giá rồi ID.

Không có metadata nào trong ba loại trên là thuộc tính ổn định của document.

## 15. Matched queries và explanation

### 15.1. Named query

Bool query có thể chứa nhiều nhánh. Khi đặt tên cho một nhánh query, Elasticsearch có thể trả tên query đã khớp trong matched_queries.

Ví dụ:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "match": {
            "name": {
              "query": "keyboard",
              "_name": "name_match"
            }
          }
        },
        {
          "match": {
            "description": {
              "query": "keyboard",
              "_name": "description_match"
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Tên query giúp ứng dụng hoặc quá trình debug biết nhánh nào khớp. Spring Data có thể cung cấp danh sách tên này qua metadata hit nếu phiên bản và response mapping hỗ trợ.

### 15.2. Explanation

Nếu request bật explain, Elasticsearch trả lời giải thích cách tính điểm cho hit. Đây là dữ liệu hữu ích khi điều tra vì sao một document có score cao hoặc thấp.

Explanation có thể khá lớn và tốn chi phí. Chỉ bật trong quá trình debug hoặc cho một lượng nhỏ request có kiểm soát; không bật mặc định cho mọi truy vấn production.

## 16. SearchHit trong các kiểu tìm kiếm khác

### 16.1. Search có highlight

Khi query yêu cầu highlight, phần fragment được gắn vào từng hit. Entity vẫn là content; highlight nằm trong hit metadata.

### 16.2. Search có inner hits

Khi query dùng nested hoặc parent/child, các nhóm inner hits nằm trong metadata của parent hit. Chúng không thay đổi kiểu content chính.

### 16.3. Search có aggregation

Aggregation thường nằm ở cấp SearchHits, không thuộc riêng một SearchHit. Một bucket có thể thống kê nhiều document, kể cả document không nằm trong top hits trả về.

### 16.4. Scroll và Point in Time

Một số thao tác scroll hoặc PIT trả về ID/context để tiếp tục tìm kiếm. Đây là metadata phục vụ vòng đời search context, không phải field của document. Cần đóng search context theo API tương ứng sau khi hoàn tất.

## 17. Ví dụ hoàn chỉnh: giữ metadata khi tìm sản phẩm

Giả sử trang tìm kiếm cần:

- Nội dung sản phẩm.
- ID document và index vật lý.
- Điểm relevance.
- Highlight của tên.
- Tổng số kết quả.

Service:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductSearchResponse search(NativeQuery query) {
        SearchHits<ProductDocument> hits =
            operations.search(query, ProductDocument.class);

        List<ProductSearchItem> items = hits.getSearchHits()
            .stream()
            .map(this::toItem)
            .toList();

        return new ProductSearchResponse(
            hits.getTotalHits(),
            items
        );
    }

    private ProductSearchItem toItem(SearchHit<ProductDocument> hit) {
        ProductDocument product = hit.getContent();

        return new ProductSearchItem(
            hit.getId(),
            hit.getIndex(),
            product.getSku(),
            product.getName(),
            product.getPrice(),
            hit.getScore(),
            hit.getHighlightFields()
                .getOrDefault("name", List.of())
        );
    }
}
~~~

DTO:

~~~java
public record ProductSearchItem(
    String id,
    String index,
    String sku,
    String name,
    double price,
    float score,
    List<String> highlights
) {}

public record ProductSearchResponse(
    long totalHits,
    List<ProductSearchItem> items
) {}
~~~

Query builder cần cấu hình highlight cho field name. Cú pháp builder highlight của Elasticsearch Java API Client phụ thuộc phiên bản, nhưng về mặt Query DSL, phần request tương đương:

~~~json
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "highlight": {
    "fields": {
      "name": {}
    }
  }
}
~~~

Ví dụ trên cho thấy cách giữ metadata khi cần rồi chuyển thành response contract rõ ràng. Trong ứng dụng thực tế, hãy validate input, giới hạn page size và chỉ trả các metadata mà frontend cần.

## 18. Những lỗi thường gặp

**Chỉ lấy getContent() rồi mong vẫn có score và highlight.** getContent() trả entity. Giữ SearchHit<T> nếu cần metadata từng hit.

**Coi _score là field của document.** Score phụ thuộc query và không phải dữ liệu nghiệp vụ. Đọc qua SearchHit.getScore().

**Coi sort values là danh sách field của entity.** Sort values phản ánh các sort clause của request. Đọc qua getSortValues().

**Cho rằng highlight thay đổi source field.** Highlight là fragment riêng. Nội dung chuẩn vẫn nằm trong content entity.

**Dùng @Id rồi tìm ID trong _source.** ID thường được quản lý bằng metadata _id. Đọc hit.getId() hoặc property ID đã được Spring Data ánh xạ.

**Cho rằng hit.getIndex() luôn bằng alias truyền vào request.** Elasticsearch có thể trả tên index vật lý. Phân biệt alias logic và index vật lý.

**Bỏ qua inner hits.** Nested query trả parent hit; muốn lấy nested object đã khớp phải đọc inner hits.

**Nhầm aggregation với danh sách hit.** Aggregation nằm ở cấp response SearchHits, không phải content entity.

**Chuyển SearchHits<T> thành List<T> quá sớm.** Việc unwrap làm mất metadata từng hit trong danh sách mới. Chỉ làm khi chắc chắn không cần metadata.

**Dùng source filtering rồi lưu entity partial.** Các field bị loại có thể trở thành null hoặc giá trị mặc định. Dùng projection/DTO hoặc partial update.

**Trả trực tiếp kiểu SearchHit nội bộ qua API mà không kiểm soát contract.** Chuyển sang DTO để tránh phụ thuộc cấu trúc Spring Data và tránh lộ metadata không cần thiết.

**Bật explain cho mọi truy vấn.** Explanation có chi phí và response lớn. Chỉ bật khi debug có kiểm soát.

## 19. Quy trình đọc và chuyển đổi kết quả

Khi xử lý kết quả tìm kiếm trong Spring Data Elasticsearch:

1. Xác định ứng dụng chỉ cần nội dung document hay cần cả metadata của hit.
2. Dùng operations.search(...) hoặc repository return type phù hợp để nhận SearchHits<T> khi cần metadata.
3. Dùng SearchHit<T>.getContent() để đọc entity đã ánh xạ.
4. Dùng getId() và getIndex() để đọc metadata định danh của hit.
5. Dùng getScore() khi query có ý nghĩa relevance.
6. Dùng getSortValues() cho sort hoặc search_after nếu cần.
7. Dùng getHighlightFields() để lấy fragment hiển thị.
8. Dùng getInnerHits() khi query có nested/parent-child.
9. Đọc aggregation và suggest ở cấp SearchHits.
10. Chuyển nội dung cùng metadata cần thiết sang DTO response trước khi trả khỏi application layer.
11. Không ghi score, highlight hoặc sort values vào entity persistence.
12. Không lưu lại entity partial được tạo từ source filtering nếu chưa nạp đủ dữ liệu.

## 20. Tài liệu tham khảo

- [Spring Data Elasticsearch - Search result types](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): cách thực thi tìm kiếm và sử dụng SearchHits.
- [Spring Data Elasticsearch API - SearchHit](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHit.html): metadata của một hit và nội dung được ánh xạ.
- [Spring Data Elasticsearch API - SearchHits](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html): metadata ở cấp response tìm kiếm.
- [Elasticsearch - Search API response](https://www.elastic.co/docs/solutions/search/the-search-api): cấu trúc hits, total, score, sort, highlight và aggregations.
- [Elasticsearch - Highlighting](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/highlighting): cấu hình và nội dung highlight fragments.
- [Elasticsearch - Source filtering](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrieve-selected-fields): giới hạn field được trả về từ source.

API chi tiết của SearchHit, SearchHits và các kiểu response có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy đối chiếu Javadoc của dependency trong dự án khi cần dùng các thuộc tính metadata ít phổ biến.
