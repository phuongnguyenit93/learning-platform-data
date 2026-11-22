# Cấu hình highlight bằng Query hoặc annotation Repository

Highlighting trong Elasticsearch giúp làm nổi bật phần văn bản khớp với truy vấn trong kết quả tìm kiếm. Thay vì chỉ trả về document và điểm liên quan, Elasticsearch có thể trả thêm các đoạn văn bản (highlight fragments) kèm thẻ đánh dấu trước và sau phần khớp.

Spring Data Elasticsearch hỗ trợ cấu hình highlight theo hai cách:

- **Qua Query**: tạo cấu hình highlight bằng các lớp trong package `org.springframework.data.elasticsearch.core.query.highlight`, đóng gói bằng `HighlightQuery`, rồi gắn vào `CriteriaQuery` hoặc `NativeQuery`.
- **Qua annotation Repository**: đặt `@Highlight` trên phương thức repository, khai báo field cần highlight bằng `@HighlightField` và tùy chỉnh bằng `@HighlightParameters`.

Cả hai cách đều dùng cơ chế highlighting của Elasticsearch. Kết quả highlight được trả trong metadata của `SearchHit<T>`, vì vậy nên nhận kết quả dưới dạng `SearchHit` hoặc `SearchHits` nếu ứng dụng cần đọc các đoạn văn bản được đánh dấu.

## 1. Highlighting hoạt động như thế nào?

Giả sử document có tên sản phẩm:

`Wireless Mechanical Keyboard for Office`

Người dùng tìm từ khóa:

`mechanical keyboard`

Query tìm kiếm có thể dùng `match` trên field `name`. Khi bật highlight cho field này, Elasticsearch trả thêm fragment:

~~~json
{
  "_index": "products",
  "_id": "P-1001",
  "_score": 2.4,
  "_source": {
    "name": "Wireless Mechanical Keyboard for Office"
  },
  "highlight": {
    "name": [
      "Wireless <mark>Mechanical</mark> <mark>Keyboard</mark> for Office"
    ]
  }
}
~~~

Trong ví dụ:

- `_source.name` là dữ liệu gốc của document.
- `highlight.name` là nội dung fragment được tạo cho kết quả tìm kiếm.
- `<mark>` và `</mark>` là thẻ bao quanh phần khớp.
- Highlight không ghi thay đổi ngược vào document và không sửa giá trị trong `_source`.

~~~mermaid
flowchart TD
    A["Người dùng nhập từ khóa"] --> B["Query match trên field"]
    B --> C["Elasticsearch tìm document"]
    C --> D["Highlight cấu hình cho các field"]
    D --> E["Tạo fragment và thẻ đánh dấu"]
    E --> F["Search response"]
    F --> G["Spring Data SearchHit / SearchHits"]
~~~

Highlight là metadata bổ sung cho kết quả search. Nó không thay thế query, không làm thay đổi cách document được lập chỉ mục và cũng không tự quyết định document nào được trả về.

## 2. Chuẩn bị entity và mapping

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
~~~

Trong ví dụ:

- `name` và `description` là field text, phù hợp với tìm kiếm toàn văn và highlight.
- `status` là keyword, thường dùng để lọc chính xác.
- Highlight thường hữu ích nhất trên field văn bản có thể phân tích.

Một query phải thực sự tìm kiếm nội dung liên quan đến field thì highlight mới có nội dung hữu ích. Nếu query chỉ lọc `status = PUBLISHED`, Elasticsearch không có cụm từ tìm kiếm trong `name` để đánh dấu. Có thể cấu hình highlight cho field, nhưng kết quả vẫn phụ thuộc query và khả năng tạo fragment của highlighter.

## 3. Các tham số highlight thường dùng

Elasticsearch hỗ trợ nhiều tùy chọn để điều khiển cách tạo fragment.

| Tham số | Ý nghĩa |
|---|---|
| `pre_tags` | Thẻ hoặc chuỗi đặt trước phần khớp |
| `post_tags` | Thẻ hoặc chuỗi đặt sau phần khớp |
| `fragment_size` | Độ dài mục tiêu của mỗi fragment |
| `number_of_fragments` | Số fragment tối đa cho mỗi field |
| `no_match_size` | Số ký tự có thể trả về khi field không có đoạn khớp |
| `require_field_match` | Yêu cầu query phải khớp chính field được highlight |
| `type` | Loại highlighter, ví dụ `unified`, `plain`, `fvh` |
| `order` | Cách sắp xếp fragment, ví dụ theo điểm liên quan |
| `encoder` | Cách encode nội dung fragment |
| `highlight_query` | Query riêng dùng để xác định nội dung highlight |

Một số lưu ý:

- `number_of_fragments = 0` yêu cầu trả toàn bộ nội dung field thay vì chia thành nhiều fragment.
- `fragment_size` là kích thước mục tiêu, không phải giới hạn cứng cho mọi ngôn ngữ hoặc ranh giới câu.
- `no_match_size` chỉ cung cấp một phần nội dung khi không có đoạn khớp; nó không biến một kết quả không khớp thành kết quả tìm kiếm.
- `require_field_match = true` là mặc định phổ biến. Nếu đặt `false`, highlighter có thể dùng query để highlight field dù field đó không trực tiếp khớp theo quy tắc mặc định.
- Một field có thể trả về nhiều fragment, vì vậy kết quả thường là danh sách chuỗi chứ không phải một chuỗi duy nhất.

## 4. Cấu hình highlight qua Query

Với Spring Data Elasticsearch 5.4, có thể tạo highlight bằng các lớp trong package:

- `org.springframework.data.elasticsearch.core.query.highlight.Highlight`
- `org.springframework.data.elasticsearch.core.query.highlight.HighlightField`
- `org.springframework.data.elasticsearch.core.query.highlight.HighlightParameters`
- `org.springframework.data.elasticsearch.core.query.highlight.HighlightFieldParameters`
- `org.springframework.data.elasticsearch.core.query.HighlightQuery`

`Highlight` chứa cấu hình chung và danh sách field cần highlight. `HighlightQuery` kết hợp cấu hình đó với kiểu entity để Spring Data ánh xạ tên thuộc tính.

### 4.1. Tạo tham số highlight chung

~~~java
import org.springframework.data.elasticsearch.core.query.highlight.HighlightParameters;

HighlightParameters highlightParameters =
        new HighlightParameters.HighlightParametersBuilder()
                .withPreTags("<mark>")
                .withPostTags("</mark>")
                .withFragmentSize(150)
                .withNumberOfFragments(3)
                .withNoMatchSize(0)
                .withRequireFieldMatch(true)
                .build();
~~~

Trong ví dụ:

- `withPreTags("<mark>")` đặt thẻ mở trước đoạn khớp.
- `withPostTags("</mark>")` đặt thẻ đóng sau đoạn khớp.
- `withFragmentSize(150)` đặt kích thước mục tiêu cho fragment.
- `withNumberOfFragments(3)` yêu cầu tối đa ba fragment cho mỗi field.
- `withNoMatchSize(0)` không yêu cầu excerpt khi field không có đoạn khớp.
- `withRequireFieldMatch(true)` yêu cầu query khớp field được highlight.

`HighlightParameters.HighlightParametersBuilder` là builder của mô hình cấu hình Spring Data. Nó khác với annotation `@HighlightParameters` dùng trong repository.

### 4.2. Khai báo các field cần highlight

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.query.highlight.Highlight;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightField;

Highlight highlight = new Highlight(
        highlightParameters,
        List.of(
                new HighlightField("name"),
                new HighlightField("description")
        )
);
~~~

Ở đây, cả `name` và `description` đều được yêu cầu highlight với cấu hình chung.

Có thể cấu hình riêng cho từng field bằng `HighlightFieldParameters`:

~~~java
import org.springframework.data.elasticsearch.core.query.highlight.HighlightFieldParameters;

HighlightFieldParameters nameParameters =
        new HighlightFieldParameters.HighlightFieldParametersBuilder()
                .withFragmentSize(100)
                .withNumberOfFragments(2)
                .build();

Highlight highlight = new Highlight(
        highlightParameters,
        List.of(
                new HighlightField("name", nameParameters),
                new HighlightField("description")
        )
);
~~~

Trong ví dụ này, field `name` có cấu hình fragment riêng. Field `description` dùng cấu hình chung từ `Highlight`.

### 4.3. Tạo HighlightQuery và gắn vào NativeQuery

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.HighlightQuery;

Query elasticsearchQuery = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("mechanical keyboard")
        )
);

HighlightQuery highlightQuery =
        new HighlightQuery(highlight, ProductDocument.class);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withHighlightQuery(highlightQuery)
        .build();
~~~

Các bước:

1. Tạo query DSL bằng Elasticsearch Java API Client.
2. Tạo `Highlight` với cấu hình chung và các field.
3. Tạo `HighlightQuery` từ `Highlight` và entity class.
4. Gắn `HighlightQuery` vào `NativeQuery` bằng `withHighlightQuery(...)`.
5. Thực thi qua `ElasticsearchOperations.search(...)`.

`NativeQueryBuilder` kế thừa `BaseQueryBuilder`, nên có thể dùng `withHighlightQuery(...)` cùng các tùy chọn query, sort và pageable.

### 4.4. Dùng CriteriaQuery cũng được

Highlight không chỉ dành cho `NativeQuery`. `HighlightQuery` thuộc Query abstraction của Spring Data, nên có thể gắn vào query khác hỗ trợ cấu hình này.

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("name").matches("mechanical keyboard");

CriteriaQuery criteriaQuery = new CriteriaQuery(criteria);
criteriaQuery.setHighlightQuery(
        new HighlightQuery(highlight, ProductDocument.class)
);
~~~

Cách này phù hợp khi điều kiện tìm kiếm đơn giản và đã được biểu diễn bằng Criteria API. Nếu query phức tạp, có nhiều bool clause hoặc cần DSL của Elasticsearch Java Client, `NativeQuery` thường linh hoạt hơn.

## 5. Thực thi và đọc highlight qua SearchHit

Sau khi tạo query, thực thi bằng `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);

for (SearchHit<ProductDocument> hit : hits) {
    ProductDocument product = hit.getContent();

    List<String> nameFragments =
            hit.getHighlightField("name");

    List<String> descriptionFragments =
            hit.getHighlightField("description");

    System.out.println(product.getName());
    System.out.println(nameFragments);
    System.out.println(descriptionFragments);
}
~~~

Các API quan trọng:

| API | Kết quả |
|---|---|
| `SearchHit.getContent()` | Entity đã được chuyển đổi |
| `SearchHit.getHighlightField("name")` | Danh sách fragment của field name |
| `SearchHit.getHighlightFields()` | Map từ tên field sang danh sách fragment |
| `SearchHits.getSearchHits()` | Danh sách SearchHit |
| `SearchHits.getTotalHits()` | Tổng số kết quả theo response |

`getHighlightField(field)` trả về danh sách fragment cho field được chỉ định. Nếu không có fragment, danh sách có thể rỗng. `getHighlightFields()` trả về map các field có dữ liệu highlight.

Ví dụ đọc toàn bộ map:

~~~java
for (SearchHit<ProductDocument> hit : hits) {
    Map<String, List<String>> highlighted =
            hit.getHighlightFields();

    highlighted.forEach((field, fragments) -> {
        System.out.println("Field: " + field);
        fragments.forEach(System.out::println);
    });
}
~~~

Không nên giả định fragment luôn có mặt. Một document có thể được trả về vì điều kiện filter, nhưng field được yêu cầu highlight không chứa term khớp; trong trường hợp đó, danh sách fragment có thể rỗng.

## 6. Cấu hình highlight bằng annotation Repository

Spring Data Elasticsearch cung cấp annotation để khai báo highlight ngay trên phương thức repository:

- `@Highlight`: đánh dấu method cần highlight và liệt kê các field.
- `@HighlightField`: xác định một field cần highlight.
- `@HighlightParameters`: cấu hình các tham số highlight chung hoặc riêng cho field.

Ví dụ entity:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    // ...
}
~~~

Repository:

~~~java
import org.springframework.data.elasticsearch.annotations.Highlight;
import org.springframework.data.elasticsearch.annotations.HighlightField;
import org.springframework.data.elasticsearch.annotations.HighlightParameters;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Highlight(
        fields = {
            @HighlightField(name = "name"),
            @HighlightField(name = "description")
        },
        parameters = @HighlightParameters(
            preTags = {"<mark>"},
            postTags = {"</mark>"},
            fragmentSize = 150,
            numberOfFragments = 3,
            requireFieldMatch = true
        )
    )
    SearchHits<ProductDocument> findByNameOrDescription(
            String name,
            String description
    );
}
~~~

Khi gọi:

~~~java
SearchHits<ProductDocument> hits =
        productRepository.findByNameOrDescription(
                "mechanical keyboard",
                "mechanical keyboard"
        );
~~~

Spring Data tạo truy vấn repository theo tên method và áp dụng cấu hình highlight từ annotation.

Dùng `SearchHits<ProductDocument>` giúp giữ metadata của từng hit, trong đó có highlight fields. Có thể dùng `List<SearchHit<ProductDocument>>` nếu API repository và kiểu kết quả của ứng dụng phù hợp. Nếu chỉ trả về `List<ProductDocument>`, ứng dụng không còn wrapper `SearchHit` để đọc metadata highlight một cách trực tiếp.

### 6.1. Highlight với repository method dùng @Query

Có thể kết hợp `@Query` với `@Highlight` khi muốn định nghĩa query DSL cụ thể:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

@Query("{\"bool\":{\"should\":["
        + "{\"match\":{\"name\":\"?0\"}},"
        + "{\"match\":{\"description\":\"?0\"}}"
        + "],\"minimum_should_match\":1}}")
@Highlight(
    fields = {
        @HighlightField(name = "name"),
        @HighlightField(name = "description")
    },
    parameters = @HighlightParameters(
        preTags = {"<mark>"},
        postTags = {"</mark>"},
        fragmentSize = 120,
        numberOfFragments = 2
    )
)
SearchHits<ProductDocument> searchText(String text);
~~~

Trong ví dụ:

- `@Query` định nghĩa điều kiện tìm kiếm trên hai field.
- `minimum_should_match: 1` yêu cầu ít nhất một nhánh match.
- `@Highlight` yêu cầu trả highlight cho `name` và `description`.
- Tham số `?0` được thay bằng đối số đầu tiên của method.

Tên field trong `@HighlightField` phải là tên thuộc tính của entity, không phải lúc nào cũng là tên field vật lý trong mapping Elasticsearch. Spring Data dùng metadata của entity để ánh xạ thuộc tính. Điều này quan trọng nếu thuộc tính Java có `@Field(name = "...")` hoặc naming strategy tùy chỉnh.

## 7. Tùy chỉnh ở mức toàn cục và từng field

Có hai cấp cấu hình:

- **Cấp highlight**: áp dụng cho toàn bộ request highlight, ví dụ thẻ mở/đóng, encoder hoặc highlighter type.
- **Cấp field**: áp dụng riêng cho từng field, ví dụ fragment size, số fragment, matched fields hoặc fragment offset.

Ví dụ annotation:

~~~java
@Highlight(
    parameters = @HighlightParameters(
        preTags = {"<strong>"},
        postTags = {"</strong>"},
        encoder = "html",
        numberOfFragments = 3,
        fragmentSize = 160
    ),
    fields = {
        @HighlightField(
            name = "name",
            parameters = @HighlightParameters(
                fragmentSize = 100,
                numberOfFragments = 2
            )
        ),
        @HighlightField(name = "description")
    }
)
SearchHits<ProductDocument> searchByText(String text);
~~~

Field `name` có tham số riêng, còn `description` dùng tham số chung. Cấu hình cụ thể nào được áp dụng phụ thuộc cách Spring Data chuyển annotation thành request highlight; khi cần hành vi chính xác, kiểm tra request được tạo và response Elasticsearch trong môi trường test.

Với Query API, cấu hình tương đương có thể dùng `HighlightParameters` và `HighlightFieldParameters` builder:

~~~java
HighlightParameters common = new HighlightParameters.HighlightParametersBuilder()
        .withPreTags("<strong>")
        .withPostTags("</strong>")
        .withEncoder("html")
        .withFragmentSize(160)
        .withNumberOfFragments(3)
        .build();

HighlightFieldParameters nameOptions =
        new HighlightFieldParameters.HighlightFieldParametersBuilder()
                .withFragmentSize(100)
                .withNumberOfFragments(2)
                .build();

Highlight highlight = new Highlight(
        common,
        List.of(
                new HighlightField("name", nameOptions),
                new HighlightField("description")
        )
);
~~~

Các builder cung cấp thêm tùy chọn như:

- `withBoundaryScanner(...)` và `withBoundaryScannerLocale(...)`: điều khiển cách tìm ranh giới fragment.
- `withBoundaryChars(...)` và `withBoundaryMaxScan(...)`: cấu hình ký tự và phạm vi tìm ranh giới.
- `withOrder("score")`: sắp xếp fragment theo điểm liên quan khi được hỗ trợ.
- `withNoMatchSize(...)`: lấy một phần nội dung khi không có fragment khớp.
- `withRequireFieldMatch(false)`: thay đổi quy tắc yêu cầu query khớp field.
- `withHighlightQuery(...)`: cung cấp query riêng cho highlighter.
- `withMatchedFields(...)`: kết hợp các field liên quan trong một cấu hình field highlight.

Không cần bật tất cả tham số. Chỉ cấu hình những gì giao diện thực sự cần, vì nhiều fragment và cấu hình highlighter phức tạp có thể làm tăng chi phí search.

## 8. Chọn highlighter type

Elasticsearch có nhiều loại highlighter. Spring Data cho phép truyền loại qua tham số `type`.

| Highlighter | Đặc điểm | Khi nên cân nhắc |
|---|---|---|
| `unified` | Highlighter mặc định, hỗ trợ nhiều loại field và query | Lựa chọn đầu tiên cho phần lớn trường hợp |
| `plain` | Dựa trên một bộ máy phân tích văn bản theo từng document | Khi cần hành vi plain highlighter cụ thể |
| `fvh` | Fast Vector Highlighter, khai thác term vectors | Khi dữ liệu và mapping được thiết kế cho FVH |

Ví dụ cấu hình unified:

~~~java
HighlightParameters parameters =
        new HighlightParameters.HighlightParametersBuilder()
                .withType("unified")
                .withPreTags("<mark>")
                .withPostTags("</mark>")
                .withFragmentSize(150)
                .withNumberOfFragments(2)
                .build();
~~~

Unified thường là lựa chọn hợp lý để bắt đầu. Chỉ chuyển sang highlighter khác khi đã hiểu yêu cầu về mapping và đo hiệu năng trên dữ liệu thật.

### Điều kiện mapping cho FVH

Fast Vector Highlighter cần term vectors phù hợp, thường là `term_vector: with_positions_offsets`:

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

Cấu hình term vectors làm tăng dung lượng index. Không nên bật chỉ vì muốn có highlight; hãy chọn highlighter mặc định trước rồi đo lường nhu cầu thực tế.

Một số highlighter có thể tận dụng offsets được lưu trong postings hoặc term vectors. Khả năng và giới hạn phụ thuộc loại field, mapping và query. Hãy đối chiếu tài liệu Elasticsearch của phiên bản cluster đang chạy trước khi thay đổi mapping.

## 9. Highlight với multi-field và matched_fields

Một field text có thể có multi-field, ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "english": {
            "type": "text",
            "analyzer": "english"
          }
        }
      }
    }
  }
}
~~~

Ứng dụng có thể tìm kiếm qua field chính hoặc field con đã phân tích. Khi cần kết hợp thông tin match từ nhiều field liên quan để highlight, Elasticsearch hỗ trợ `matched_fields` với các điều kiện tương thích highlighter.

Trong Spring Data, có thể cấu hình `matchedFields` cho field highlight:

~~~java
HighlightFieldParameters parameters =
        new HighlightFieldParameters.HighlightFieldParametersBuilder()
                .withMatchedFields("name", "name.english")
                .withFragmentSize(150)
                .withNumberOfFragments(2)
                .build();

HighlightField nameField =
        new HighlightField("name", parameters);
~~~

Dùng `matchedFields` khi các field là những biểu diễn khác nhau của cùng một nội dung và cần gom match để tạo fragment. Không nên đưa các field không liên quan vào cùng nhóm vì đoạn highlight có thể gây hiểu nhầm.

## 10. Dùng highlightQuery khi cần quy tắc highlight riêng

Thông thường highlighter dùng query chính để xác định term cần đánh dấu. Nếu cần highlight theo một query riêng, có thể cấu hình `highlightQuery`.

Ví dụ, query chính có thể kết hợp full-text với filter, trong khi highlight chỉ dùng phần match tên sản phẩm. Spring Data hỗ trợ `highlightQuery` trong `HighlightParameters`:

~~~java
Query highlightOnlyName = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("mechanical keyboard")
        )
);

HighlightParameters parameters =
        new HighlightParameters.HighlightParametersBuilder()
                .withPreTags("<mark>")
                .withPostTags("</mark>")
                .withHighlightQuery(highlightOnlyName)
                .build();
~~~

Query riêng giúp điều khiển cách highlighter xác định đoạn cần đánh dấu. Tuy nhiên, nó không thay đổi query chính dùng để chọn document. Nếu highlight query không khớp nội dung field, kết quả fragment có thể rỗng.

## 11. Highlight không phải là nội dung đã được sanitize

Các fragment thường chứa thẻ HTML hoặc chuỗi do ứng dụng cấu hình. Nếu đưa trực tiếp fragment vào HTML mà không xử lý, nội dung gốc của document có thể chứa markup độc hại.

Ví dụ dữ liệu có thể chứa:

~~~text
Wireless Keyboard <script>alert(1)</script>
~~~

Nếu ứng dụng hiển thị highlight bằng cách tin tưởng toàn bộ fragment, có thể tạo lỗ hổng cross-site scripting (XSS).

Một số nguyên tắc:

- Cân nhắc `encoder = "html"` để encode nội dung field trong quá trình highlight.
- Dùng thẻ đánh dấu do ứng dụng kiểm soát, ví dụ `<mark>`.
- Không cho người dùng tùy ý truyền `pre_tags` hoặc `post_tags`.
- Nếu frontend cần render markup, chỉ cho phép các thẻ highlight đã được allowlist.
- Không dùng thao tác render HTML thô với fragment chưa được kiểm tra.

Ví dụ cấu hình encoder trong annotation:

~~~java
@Highlight(
    fields = {
        @HighlightField(name = "description")
    },
    parameters = @HighlightParameters(
        preTags = {"<mark>"},
        postTags = {"</mark>"},
        encoder = "html"
    )
)
SearchHits<ProductDocument> searchDescription(String text);
~~~

Encoder giúp encode nội dung fragment theo cấu hình highlighter, nhưng ứng dụng vẫn cần kiểm soát cách render đầu ra và không nên coi dữ liệu search là đáng tin cậy.

## 12. Khi nào không có highlight fragment?

Có nhiều lý do khiến document được trả về nhưng map highlight không có field mong đợi:

1. Query không khớp field được highlight.
2. Field không được yêu cầu trong cấu hình highlight.
3. Field không hỗ trợ highlighter theo mapping hoặc kiểu dữ liệu.
4. Analyzer của query và field tạo ra token không tương thích.
5. `require_field_match` đang bật và query chỉ khớp field khác.
6. Field không có nội dung hoặc nội dung quá ngắn/không tạo được fragment.
7. Highlighter type yêu cầu term vectors/offsets mà mapping chưa cung cấp.
8. Source hoặc cấu hình field không phù hợp với cách highlighter lấy nội dung.

Khi debug, hãy kiểm tra theo thứ tự:

- Query thực tế có match field không?
- Mapping của field là text, keyword hay kiểu khác?
- Highlight request có chứa đúng field path không?
- Highlighter type có yêu cầu mapping đặc biệt không?
- Response thô có chứa thuộc tính `highlight` không?
- Spring Data có ánh xạ highlight field vào `SearchHit` như dự kiến không?

Có thể dùng Elasticsearch Dev Tools để gửi trực tiếp query có `highlight` và xem response trước khi kiểm tra lớp chuyển đổi của Spring Data.

## 13. Phân biệt highlight với source filtering

Highlight và source filtering giải quyết hai nhu cầu khác nhau:

| Tính năng | Mục đích |
|---|---|
| Highlight | Trả fragment có đánh dấu phần khớp |
| Source filtering | Giảm các field trong `_source` được trả về |
| Stored fields | Trả các field được lưu riêng trong index theo mapping |

Ví dụ query có source filtering chỉ trả `name`:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

NativeQuery sourceFilteredQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(
                new FetchSourceFilter(
                        new String[] {"name"},
                        new String[] {}
                )
        )
        .withHighlightQuery(highlightQuery)
        .build();
~~~

Highlight cho `description` là metadata riêng. Nếu source filtering loại `description`, ứng dụng vẫn có thể nhận highlight fragment cho field đó trong một số cấu hình, nhưng không có nội dung source đầy đủ của field để hiển thị. Cần quyết định rõ response cần source nào và highlight field nào.

Không nên dùng highlight như cách thay thế source filtering hoặc ngược lại.

## 14. So sánh cấu hình qua Query và Repository annotation

| Tiêu chí | Query / HighlightQuery | Repository annotation |
|---|---|---|
| Nơi khai báo | Trong code xây dựng query | Trên method repository |
| API chính | `Highlight`, `HighlightField`, `HighlightParameters`, `HighlightQuery` | `@Highlight`, `@HighlightField`, `@HighlightParameters` |
| Điều kiện tìm kiếm | CriteriaQuery hoặc NativeQuery | Derived query hoặc `@Query` |
| Tính linh hoạt | Cao, có thể thay đổi theo request | Cấu hình cố định theo method |
| Dùng khi | Query động, service cần điều khiển highlight | Repository method có hành vi tìm kiếm ổn định |
| Đọc kết quả | `SearchHit.getHighlightField(...)` | `SearchHit.getHighlightField(...)` |

Chọn cấu hình Query khi một service có nhiều chế độ tìm kiếm hoặc cần thay đổi field/fragment theo request. Chọn annotation khi một repository method có query và cấu hình highlight cố định, dễ đọc ngay tại nơi khai báo.

Không cần kết hợp cả hai cách cho cùng một request nếu không có lý do rõ ràng. Hãy giữ một nguồn cấu hình để tránh khó hiểu khi debug.

## 15. Các lỗi thường gặp

### Dùng tên field index thay cho tên property trong @HighlightField

Javadoc của Spring Data quy định `@HighlightField.name` là tên thuộc tính entity. Nếu Java property là `productName` nhưng mapping field được đặt tên là `name`, annotation repository cần tham chiếu property theo quy tắc Spring Data, không tự suy đoán tên vật lý.

### Chỉ trả về entity và làm mất metadata

Highlight được lưu trong `SearchHit`, không tự động trở thành thuộc tính của entity. Dùng `SearchHits<T>` hoặc `SearchHit<T>` khi cần đọc fragments.

### Query chỉ lọc nhưng mong highlighter đánh dấu từ khóa

Filter như `term(status)` không cung cấp từ khóa văn bản để highlight. Cần có query phù hợp trên field hoặc cấu hình highlight query riêng.

### Nhầm fragment với toàn bộ field

Một field dài có thể trả nhiều đoạn ngắn. Nếu muốn toàn bộ field, cấu hình `numberOfFragments = 0` và cân nhắc kích thước response.

### Cấu hình quá nhiều fragment

Nhiều fragment trên nhiều field có thể làm response lớn và tăng chi phí xử lý. Giới hạn field, số fragment và kích thước phù hợp với giao diện.

### Chọn FVH mà không cấu hình term vectors

Fast Vector Highlighter cần mapping hỗ trợ term vectors thích hợp. Nếu chưa có, dùng unified hoặc cập nhật mapping/reindex theo kế hoạch.

### Dùng thẻ HTML không an toàn

Fragment có thể chứa dữ liệu người dùng. Kiểm soát pre/post tags, encoder và cách render để tránh XSS.

### Coi highlight là bằng chứng tuyệt đối về relevance

Highlight chỉ cho thấy phần nội dung được highlighter chọn để đánh dấu theo query. Nó không phải điểm số, không thay thế `_score` và không đảm bảo mọi phần liên quan đều được hiển thị.

## 16. Quy trình triển khai

Khi thêm highlight vào chức năng tìm kiếm:

1. Xác định field văn bản cần làm nổi bật.
2. Kiểm tra mapping và analyzer của từng field.
3. Xác định query có thực sự match các field đó hay không.
4. Chọn cấu hình qua `HighlightQuery` hoặc annotation `@Highlight`.
5. Đặt `preTags`, `postTags`, `fragmentSize` và `numberOfFragments` theo nhu cầu giao diện.
6. Dùng `SearchHit<T>` hoặc `SearchHits<T>` để giữ metadata highlight.
7. Kiểm tra cả trường hợp có fragment và không có fragment.
8. Nếu dùng multi-field, xác định có cần `matchedFields` hay không.
9. Chọn highlighter type dựa trên mapping và đo hiệu năng.
10. Kiểm soát encoder và cách frontend render fragment.
11. Kiểm tra response Elasticsearch thực tế khi có lỗi.
12. Giới hạn số field và fragment để tránh response quá lớn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch 5.4.8 — Repository methods và @Highlight](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/reference/html/#elasticsearch.repositories.annotations)
- [Spring Data Elasticsearch 5.4.8 — Highlight annotation](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/annotations/Highlight.html)
- [Spring Data Elasticsearch 5.4.8 — HighlightParameters annotation](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/annotations/HighlightParameters.html)
- [Spring Data Elasticsearch 5.4.8 — NativeQueryBuilder](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch 5.4.8 — SearchHit](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/core/SearchHit.html)
- [Elasticsearch — Highlighting search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html)

## Kết luận

Spring Data Elasticsearch hỗ trợ highlight theo hai hướng. Với Query API, tạo `Highlight` và `HighlightField`, kết hợp thành `HighlightQuery`, rồi gắn vào `NativeQuery` hoặc `CriteriaQuery`. Với Repository, đặt `@Highlight` trên method, liệt kê field bằng `@HighlightField` và cấu hình bằng `@HighlightParameters`. Kết quả nằm trong metadata của `SearchHit<T>`, có thể đọc qua `getHighlightField(...)` hoặc `getHighlightFields()`. Hãy chọn field có mapping phù hợp, giới hạn fragment hợp lý và kiểm soát an toàn HTML trước khi hiển thị cho người dùng.
