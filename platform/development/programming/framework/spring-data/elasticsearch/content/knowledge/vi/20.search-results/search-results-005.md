# Đọc highlight, inner hits, aggregation và suggest

Kết quả tìm kiếm của Elasticsearch không chỉ gồm các document khớp truy vấn. Một search response còn có thể chứa đoạn văn bản được đánh dấu từ khóa (`highlight`), các document con khớp điều kiện trong một document cha (`inner hits`), kết quả thống kê (`aggregations`) và các gợi ý sửa từ hoặc hoàn thành từ (`suggest`). Spring Data Elasticsearch gom những phần này vào các lớp kết quả như `SearchHit`, `SearchHits`, `ElasticsearchAggregations` và `Suggest`.

Muốn sử dụng đúng các dữ liệu bổ sung này, cần phân biệt chúng nằm ở cấp nào của response. Highlight và inner hits gắn với từng hit; aggregation và suggest nằm ở cấp toàn bộ kết quả tìm kiếm. Chúng cũng có yêu cầu mapping và cách đọc khác nhau. Ví dụ, `inner_hits` thường đi cùng `nested` query và field được map là `nested`, aggregation cần field có kiểu phù hợp như `keyword` hoặc numeric, còn completion suggester cần field kiểu `completion`.

## 1. Cấu trúc kết quả tìm kiếm

Khi gọi `ElasticsearchOperations.search(...)`, Spring Data Elasticsearch trả về `SearchHits<T>`. Mỗi document khớp truy vấn được bọc trong một `SearchHit<T>`.

```text
ElasticsearchOperations.search(query, ProductDocument.class)
                  |
                  v
             SearchHits<T>
                  |
       +----------+-----------+----------------+
       |          |           |                |
       v          v           v                v
  SearchHit   Aggregations  Suggest       Search metadata
       |
       +-- id, index, score, sort values
       +-- content (entity)
       +-- highlight fields
       +-- inner hits
```

| Dữ liệu | Vị trí trong Spring Data | Ý nghĩa |
|---|---|---|
| Document tìm được | `SearchHit.getContent()` | Entity được ánh xạ từ `_source` hoặc dữ liệu trả về |
| Điểm và định danh | `SearchHit.getScore()`, `getId()`, `getIndex()` | Metadata của một hit |
| Highlight | `SearchHit.getHighlightFields()` hoặc `getHighlightField(name)` | Các fragment có chứa phần khớp truy vấn |
| Inner hits | `SearchHit.getInnerHits()` hoặc `getInnerHits(name)` | Các document con khớp trong nested/parent-child query |
| Aggregation | `SearchHits.getAggregations()` | Metric và bucket tổng hợp trên tập document của request |
| Suggest | `SearchHits.getSuggest()` | Các gợi ý sửa từ, gợi ý cụm từ hoặc autocomplete |
| Tổng hit và thời gian | `SearchHits.getTotalHits()`, `getExecutionDuration()` | Metadata chung của request |

Nếu chỉ trả về `List<ProductDocument>`, ứng dụng thường chỉ giữ phần entity và làm mất metadata của từng hit. Khi giao diện cần highlight, inner hits, score, aggregation hoặc suggest, hãy giữ `SearchHits<T>` và chuyển các phần cần thiết sang DTO của ứng dụng.

## 2. Document mẫu và mapping

Giả sử một sản phẩm có tên, mô tả và nhiều biến thể. Mỗi biến thể có màu, kích cỡ và SKU. Ứng dụng cần tìm theo nội dung sản phẩm, chỉ trả về biến thể thỏa điều kiện, thống kê sản phẩm theo danh mục và gợi ý tên khi người dùng nhập.

```java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String description;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Nested)
    private List<ProductVariant> variants;

    @CompletionField(maxInputLength = 100)
    private Completion suggest;

    // Constructors, getters and setters
}

public class ProductVariant {

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Keyword)
    private String size;

    // Constructors, getters and setters
}
```

Mapping cần được thiết kế theo mục đích truy vấn:

- `name` và `description` là `text` để full-text search và highlight.
- `name.keyword` là subfield `keyword`, phù hợp với sort hoặc aggregation theo toàn bộ tên.
- `category` là `keyword`, phù hợp với terms aggregation.
- `price` là numeric, phù hợp với metric/range aggregation.
- `variants` là `nested` để bảo toàn quan hệ giữa màu, kích cỡ và SKU trong từng biến thể.
- `suggest` là `completion`, phục vụ autocomplete.

Highlight, aggregation và suggest không tự sửa mapping. Nếu mapping không phù hợp, request có thể lỗi hoặc kết quả không đúng mục tiêu. Ví dụ, terms aggregation trên `text` thường không phải cách đúng để nhóm theo giá trị nguyên bản; hãy dùng subfield `keyword`.

## 3. Highlight là gì?

Highlight trả về một hoặc nhiều đoạn văn bản có đánh dấu phần khớp với truy vấn. Giao diện có thể dùng các fragment này để làm nổi bật từ khóa trong tiêu đề hoặc mô tả.

Ví dụ người dùng tìm `espresso machine`, kết quả có thể chứa:

```json
{
  "_id": "p-1001",
  "_source": {
    "name": "Máy pha cà phê Espresso"
  },
  "highlight": {
    "name": [
      "Máy pha cà phê <em>Espresso</em>"
    ]
  }
}
```

Highlight là metadata bổ sung của hit. Nó không thay đổi `_source` và không phải một bản document đã được cập nhật. Nội dung gốc vẫn nằm trong `getContent()`; fragment được đánh dấu nằm riêng trong `getHighlightField(...)` hoặc `getHighlightFields()`.

### Các tham số thường dùng

| Tham số | Tác dụng |
|---|---|
| `pre_tags` | Chuỗi đặt trước phần khớp, ví dụ `<mark>` |
| `post_tags` | Chuỗi đặt sau phần khớp, ví dụ `</mark>` |
| `fragment_size` | Kích thước mục tiêu của fragment |
| `number_of_fragments` | Số fragment tối đa trả về cho một field |
| `no_match_size` | Số ký tự có thể lấy từ đầu field nếu không tạo được fragment khớp |
| `require_field_match` | Chỉ highlight field có tham gia khớp query hay cho phép highlight theo điều kiện khác |
| `order` | Có thể sắp xếp fragment theo score |
| `type` | Chọn highlighter như `unified`, `plain` hoặc `fvh` khi phù hợp |

Nếu `number_of_fragments` bằng 0, Elasticsearch có thể trả toàn bộ nội dung field thay vì chia thành fragment. Cách này phù hợp với field ngắn như tiêu đề nhưng có thể tạo response lớn với mô tả dài.

### Highlighter không phải analyzer

Analyzer tạo token lúc index và lúc search. Highlighter dùng thông tin truy vấn và dữ liệu field để xác định đoạn nào cần đánh dấu. Nếu analyzer của field và query khác nhau, kết quả highlight có thể khó giải thích. Hãy kiểm tra analyzer thực tế bằng `_analyze` khi highlight không đánh dấu đúng từ mong đợi.

## 4. Khai báo highlight bằng `@Highlight`

Với repository method, có thể dùng annotation `@Highlight` để chỉ định các field cần highlight. Phương thức nên trả về `SearchHits<T>` nếu cần lấy metadata của từng hit.

```java
import org.springframework.data.elasticsearch.annotations.Highlight;
import org.springframework.data.elasticsearch.annotations.HighlightField;
import org.springframework.data.elasticsearch.annotations.HighlightParameters;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Highlight(fields = {
        @HighlightField(name = "name"),
        @HighlightField(name = "description")
    })
    SearchHits<ProductDocument> findByNameOrDescription(
            String name,
            String description);
}
```

Tên trong `@HighlightField(name = ...)` là tên property của entity. Nếu tên property Java khác tên field Elasticsearch do `@Field(name = ...)` hoặc naming strategy, cần dùng đúng quy ước mà annotation yêu cầu và xác nhận mapping thực tế.

Có thể cấu hình riêng cho từng field bằng `@HighlightParameters`, ví dụ fragment size, số fragment và pre/post tags:

```java
@Highlight(fields = {
    @HighlightField(
        name = "name",
        parameters = @HighlightParameters(
            preTags = "<mark>",
            postTags = "</mark>",
            numberOfFragments = 0
        )
    ),
    @HighlightField(
        name = "description",
        parameters = @HighlightParameters(
            preTags = "<mark>",
            postTags = "</mark>",
            fragmentSize = 160,
            numberOfFragments = 3
        )
    )
})
SearchHits<ProductDocument> findByNameOrDescription(
        String name,
        String description);
```

Trong ví dụ, tiêu đề trả về nguyên field và mô tả trả về tối đa ba fragment có kích thước mục tiêu 160 ký tự. Điều chỉnh số fragment theo giao diện và kích thước response mong muốn.

## 5. Khai báo highlight bằng `NativeQuery`

Khi truy vấn đã dùng `NativeQuery`, có thể đặt `HighlightQuery` lên query builder. Cách này phù hợp khi cần kết hợp highlight với bool query, aggregation, sort hoặc các tính năng Query DSL khác.

```java
import java.util.List;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.HighlightQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.highlight.Highlight;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightField;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightParameters;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightParametersBuilder;

HighlightParameters parameters = new HighlightParametersBuilder()
    .withPreTags("<mark>")
    .withPostTags("</mark>")
    .withFragmentSize(160)
    .withNumberOfFragments(3)
    .build();

Highlight highlight = new Highlight(
    parameters,
    List.of(
        new HighlightField("name"),
        new HighlightField("description")
    )
);

HighlightQuery highlightQuery =
    new HighlightQuery(highlight, ProductDocument.class);

Query query = NativeQuery.builder()
    .withQuery(q -> q.multiMatch(m -> m
        .query("espresso machine")
        .fields("name", "description")
    ))
    .withHighlightQuery(highlightQuery)
    .build();
```

`HighlightQuery` kết hợp định nghĩa highlight với entity type để Spring Data biết cách ánh xạ field. Các lớp `Highlight`, `HighlightField` và `HighlightParametersBuilder` nằm trong package `org.springframework.data.elasticsearch.core.query.highlight`; `HighlightQuery` nằm trong `org.springframework.data.elasticsearch.core.query`.

## 6. Đọc highlight từ `SearchHit`

Sau khi thực thi query:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : results.getSearchHits()) {
    ProductDocument product = hit.getContent();

    List<String> nameFragments = hit.getHighlightField("name");
    List<String> descriptionFragments = hit.getHighlightField("description");

    System.out.println(product.getName());
    System.out.println(nameFragments);
    System.out.println(descriptionFragments);
}
```

Các accessor hữu ích:

```java
Map<String, List<String>> allHighlights = hit.getHighlightFields();
List<String> nameHighlights = hit.getHighlightField("name");
```

`getHighlightFields()` trả về map từ tên field tới danh sách fragment. `getHighlightField(name)` trả về danh sách fragment của một field; nếu không có highlight cho field đó, danh sách có thể rỗng. Không nên giả định mỗi field luôn có đúng một fragment.

### Hiển thị highlight an toàn

Các tag như `<mark>` hoặc `<em>` là chuỗi do request cấu hình. Nội dung fragment vẫn có thể chứa văn bản do người dùng nhập. Không đưa fragment thô vào HTML bằng cách tắt escaping một cách vô điều kiện. Hãy dùng encoder HTML phù hợp và chỉ cho phép các tag đánh dấu mà ứng dụng đã kiểm soát. Highlight không phải cơ chế làm sạch HTML hay bảo vệ XSS.

### Highlight có thể không có

Một số lý do khiến map highlight rỗng:

- Query không khớp field được yêu cầu highlight.
- `require_field_match` giữ hành vi mặc định và field không tham gia điều kiện khớp.
- Field không hỗ trợ highlighter đang chọn hoặc dữ liệu cần thiết không sẵn có.
- Mapping/analyzer và query không tạo ra phần khớp có thể highlight.
- Query chỉ dùng filter không có phần full-text thích hợp.

Khi cần, kiểm tra request `_search` trực tiếp và thử highlighter trên một document cụ thể trước khi thay đổi mapping.

## 7. Inner hits là gì?

`inner_hits` trả về các document con khớp điều kiện bên trong một document cha. Nó đặc biệt hữu ích với field được mapping `nested`.

Ví dụ một sản phẩm có nhiều biến thể:

```json
{
  "name": "Áo khoác thể thao",
  "variants": [
    { "sku": "JKT-BLK-S", "color": "black", "size": "S" },
    { "sku": "JKT-BLK-L", "color": "black", "size": "L" },
    { "sku": "JKT-WHT-M", "color": "white", "size": "M" }
  ]
}
```

Nếu dùng `nested` query tìm `color = black` và `size = L`, Elasticsearch có thể trả về document sản phẩm cha cùng với riêng biến thể `JKT-BLK-L` trong `inner_hits`. Ứng dụng biết chính xác phần tử nào trong mảng đã làm document cha khớp.

### Vì sao phải dùng `nested`?

Mảng object thông thường được Elasticsearch làm phẳng khi lập chỉ mục. Điều đó có thể khiến điều kiện trên các thuộc tính thuộc những object khác nhau bị ghép với nhau. `nested` lưu mỗi phần tử như một document con độc lập, giữ quan hệ giữa các trường trong cùng phần tử.

Chỉ khai báo `inner_hits` trong query là chưa đủ. Field phải được mapping `nested` nếu muốn truy vấn nested đúng ngữ nghĩa.

## 8. Mapping nested trong Spring Data

Khai báo thuộc tính mảng bằng `FieldType.Nested`:

```java
public class ProductVariant {

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Keyword)
    private String size;

    // Constructors, getters and setters
}

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Nested)
    private List<ProductVariant> variants;

    // Constructors, getters and setters
}
```

Mapping JSON tương ứng:

```json
{
  "properties": {
    "name": { "type": "text" },
    "variants": {
      "type": "nested",
      "properties": {
        "sku": { "type": "keyword" },
        "color": { "type": "keyword" },
        "size": { "type": "keyword" }
      }
    }
  }
}
```

Mapping của index đã tồn tại phải thực sự là `nested`. Thay annotation Java sau khi index đã được tạo không tự chuyển field `object` thành `nested`; thay đổi này thường cần index mới và reindex dữ liệu.

## 9. Khai báo nested query kèm inner hits

Với Elasticsearch Java API Client, có thể dùng `NativeQuery` và nested query. Đặt tên cho inner hits giúp đọc đúng nhóm kết quả khi query có nhiều nested path.

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.nested(n -> n
        .path("variants")
        .query(nq -> nq.bool(b -> b
            .must(m -> m.term(t -> t
                .field("variants.color")
                .value("black")
            ))
            .must(m -> m.term(t -> t
                .field("variants.size")
                .value("L")
            ))
        ))
        .innerHits(ih -> ih
            .name("matching_variants")
            .size(5)
        )
    ))
    .build();
```

Query này tìm document cha có ít nhất một biến thể vừa màu đen vừa cỡ L, sau đó trả tối đa năm nested hit khớp trong nhóm tên `matching_variants`.

JSON Query DSL tương ứng về mặt ý nghĩa:

```json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "must": [
            { "term": { "variants.color": "black" } },
            { "term": { "variants.size": "L" } }
          ]
        }
      },
      "inner_hits": {
        "name": "matching_variants",
        "size": 5
      }
    }
  }
}
```

Tên field trong Query DSL là tên field Elasticsearch, bao gồm path `variants.`. Tên `matching_variants` là nhãn response do ứng dụng đặt, không phải mapping field.

## 10. Đọc inner hits từ `SearchHit`

`SearchHit<T>` cung cấp `getInnerHits()` để lấy map các nhóm inner hit hoặc `getInnerHits(name)` để lấy nhóm cụ thể.

```java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> parentHit : results.getSearchHits()) {
    ProductDocument product = parentHit.getContent();

    SearchHits<?> matchingVariants =
        parentHit.getInnerHits("matching_variants");

    if (matchingVariants == null) {
        continue;
    }

    for (SearchHit<?> variantHit : matchingVariants.getSearchHits()) {
        Object variant = variantHit.getContent();
        System.out.println(product.getName());
        System.out.println(variant);
    }
}
```

`getInnerHits(name)` có thể trả về `null` nếu nhóm không tồn tại trên hit đó. Nếu Spring Data ánh xạ được inner hit vào kiểu nested entity, `getContent()` có thể là `ProductVariant`; nếu không, nội dung có thể được trả dưới dạng `SearchDocument`. Khi cần kiểu cụ thể, hãy kiểm tra kiểu ánh xạ thực tế và tránh ép kiểu không kiểm tra.

Có thể lấy tất cả nhóm inner hit:

```java
Map<String, SearchHits<?>> allInnerHits = parentHit.getInnerHits();
```

Mỗi parent hit có thể có số inner hit khác nhau. Inner hits có thể mang metadata riêng như score, highlight và sort values.

## 11. Inner hits và highlight kết hợp

Một ứng dụng có thể cần đánh dấu từ khóa trong chính nested object đã khớp. Khi đó, đặt `highlight` bên trong phần `inner_hits` của nested query.

Ví dụ REST DSL:

```json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "match": {
          "variants.description": "waterproof"
        }
      },
      "inner_hits": {
        "name": "matching_variants",
        "highlight": {
          "fields": {
            "variants.description": {
              "pre_tags": ["<mark>"],
              "post_tags": ["</mark>"]
            }
          }
        }
      }
    }
  }
}
```

Sau khi đọc `parentHit.getInnerHits("matching_variants")`, lấy `getHighlightField("variants.description")` từ từng nested `SearchHit` nếu response được Spring Data ánh xạ phần highlight đó. Kiểm tra tên field theo mapping và response thực tế; field lồng có thể xuất hiện với path đầy đủ.

## 12. Aggregation là gì?

Aggregation dùng để tổng hợp dữ liệu trên tập document phù hợp truy vấn. Nó có thể tính số liệu tổng quan hoặc chia document thành các bucket.

| Loại | Ví dụ | Kết quả |
|---|---|---|
| Metric | `avg`, `sum`, `min`, `max`, `stats`, `cardinality` | Giá trị thống kê |
| Bucket | `terms`, `range`, `date_histogram`, `filters` | Các nhóm document cùng `doc_count` |
| Sub-aggregation | `terms` chứa `avg` hoặc `sum` | Thống kê con trong từng bucket |
| Pipeline | `derivative`, `moving_fn`, `bucket_script` | Tính toán dựa trên kết quả aggregation khác |

Ví dụ, thống kê số sản phẩm theo danh mục và giá trung bình:

```json
{
  "size": 0,
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

`size: 0` yêu cầu không trả document hits, nhưng aggregation vẫn được tính và trả về. Điều này hữu ích cho dashboard chỉ cần số liệu.

## 13. Khai báo aggregation bằng `NativeQuery`

Spring Data Elasticsearch dùng `NativeQuery` để khai báo các aggregation từ Elasticsearch Java API Client.

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withAggregation(
        "products_by_category",
        Aggregation.of(a -> a.terms(t -> t
            .field("category")
            .size(20)
        ).aggregations(
            "average_price",
            Aggregation.of(sub -> sub.avg(avg -> avg.field("price")))
        ))
    )
    .build();
```

Tên `products_by_category` và `average_price` là tên aggregation do ứng dụng đặt. Dùng đúng tên này khi đọc kết quả. Field `category` cần mapping `keyword`; field `price` cần mapping số.

Có thể kết hợp query lọc với aggregation. Query cấp cao nhất giới hạn tập document đầu vào cho cả hits và các aggregation thông thường:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.term(t -> t
        .field("status")
        .value("PUBLISHED")
    ))
    .withAggregation(
        "products_by_category",
        Aggregation.of(a -> a.terms(t -> t.field("category").size(20)))
    )
    .build();
```

Ở đây, bucket chỉ tính trên các sản phẩm có `status = PUBLISHED`.

## 14. Đọc aggregation từ `SearchHits`

`SearchHits.getAggregations()` trả về `AggregationsContainer<?>`. Với ELC, Spring Data cung cấp `ElasticsearchAggregations` để truy cập kết quả theo tên.

```java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.hasAggregations()
        && results.getAggregations() instanceof ElasticsearchAggregations aggregations) {

    ElasticsearchAggregation categoryAggregation =
        aggregations.get("products_by_category");

    var categoryTerms = categoryAggregation.aggregation().sterms();

    for (var bucket : categoryTerms.buckets().array()) {
        String category = bucket.key().stringValue();
        long productCount = bucket.docCount();
        double averagePrice = bucket.aggregations()
            .get("average_price")
            .avg()
            .value();
    }
}
```

`sterms()` là biến thể terms cho key chuỗi. Với field số, kiểu aggregate có thể là `lterms()` hoặc `dterms()`. Metric `avg` trả về một aggregate có giá trị `value()`. Chọn accessor theo đúng kiểu aggregation đã khai báo và kiểu field; không ép mọi aggregate về cùng một loại.

Nếu chỉ cần metric tổng quát, ví dụ stats:

```java
Query query = NativeQuery.builder()
    .withAggregation(
        "price_stats",
        Aggregation.of(a -> a.stats(s -> s.field("price")))
    )
    .build();

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.getAggregations() instanceof ElasticsearchAggregations aggregations) {
    var stats = aggregations.get("price_stats").aggregation().stats();
    long count = stats.count();
    double min = stats.min();
    double max = stats.max();
    double average = stats.avg();
    double sum = stats.sum();
}
```

## 15. Phạm vi lọc của aggregation

Cần phân biệt query cấp cao nhất, `filter` aggregation và `post_filter`:

- Query cấp cao nhất giới hạn tập document đầu vào cho hits và aggregation.
- `filter` aggregation tạo một bucket con riêng chỉ chứa document thỏa điều kiện của nó.
- `post_filter` lọc hits sau khi aggregation được tính; nó không làm thay đổi tập document đầu vào của aggregation.

Ví dụ cần trả hits cho mọi sản phẩm nhưng chỉ tính số liệu cho sản phẩm còn hàng:

```json
{
  "post_filter": {
    "term": {
      "available": true
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
```

Trong ví dụ này, `post_filter` tác động tới danh sách hits nhưng aggregation `by_category` vẫn tính trên tập document trước post-filter. Nếu muốn aggregation cũng chỉ tính sản phẩm còn hàng, đưa điều kiện vào query cấp cao nhất hoặc dùng filter aggregation phù hợp.

### Terms aggregation không tự trả tất cả bucket

`terms.size` giới hạn số bucket được trả về, thường dùng cho top N. Nếu cần duyệt số lượng bucket lớn hoặc toàn bộ tổ hợp, hãy cân nhắc composite aggregation và phân trang bằng `after_key`. Không nên đặt `size` cực lớn mà chưa đánh giá bộ nhớ và tải cluster.

## 16. Suggest là gì?

Suggest trả về gợi ý liên quan tới văn bản người dùng nhập. Nó thường được dùng cho sửa lỗi chính tả, đề xuất cụm từ hoặc autocomplete.

| Suggester | Mục đích | Ví dụ |
|---|---|---|
| `term` | Đề xuất từ thay thế dựa trên khoảng cách chỉnh sửa | `elastcsearch` → `elasticsearch` |
| `phrase` | Đề xuất cả cụm từ dựa trên mô hình thống kê/ngữ cảnh | `noble prize` → `nobel prize` |
| `completion` | Autocomplete nhanh theo prefix | `iph` → `iPhone` |
| Context completion | Autocomplete có lọc hoặc boost theo context | Gợi ý địa điểm theo loại hoặc vị trí |

Suggest là phần riêng trong search response. Một request có thể vừa chạy query để lấy document hits, vừa chạy suggest để trả gợi ý. Với term suggester, phần gợi ý dựa trên văn bản và field được chỉ định; nó không nhất thiết bị giới hạn bởi query document đi kèm.

## 17. Term suggester và phrase suggester

### Term suggester

Term suggester phân tích văn bản nhập và tìm các thuật ngữ có khả năng là cách viết đúng dựa trên edit distance. Nó hoạt động theo từng token, vì vậy có thể trả nhiều entry cho một câu truy vấn.

REST DSL ví dụ:

```http
POST /products/_search
Content-Type: application/json

{
  "suggest": {
    "name_terms": {
      "text": "wireles hedphones",
      "term": {
        "field": "name",
        "suggest_mode": "popular",
        "size": 5
      }
    }
  }
}
```

`suggest_mode` có thể là `missing`, `popular` hoặc `always`. Chế độ điều khiển khi nào thuật ngữ đầu vào được xem xét để gợi ý. Field được chọn phải có token phù hợp và analyzer phù hợp với ngôn ngữ.

### Phrase suggester

Phrase suggester kết hợp candidate generator với thống kê n-gram để chọn cách sửa cho cả cụm từ, thay vì chỉ đề xuất thay thế độc lập cho từng token. Nó thường cần field n-gram hoặc cấu hình mapping/analyzer phù hợp.

Ví dụ REST DSL:

```json
{
  "suggest": {
    "name_phrase": {
      "text": "wireles hedphones",
      "phrase": {
        "field": "name.trigram",
        "size": 3,
        "direct_generator": [
          {
            "field": "name.trigram",
            "suggest_mode": "always"
          }
        ],
        "highlight": {
          "pre_tag": "<mark>",
          "post_tag": "</mark>"
        }
      }
    }
  }
}
```

Phrase suggester phù hợp với “Bạn có phải muốn tìm…?” khi người dùng nhập sai cả cụm. Nó cần được kiểm thử bằng dữ liệu thật vì candidate generation và thống kê n-gram ảnh hưởng mạnh tới chất lượng gợi ý.

## 18. Completion suggester cho autocomplete

Completion suggester được tối ưu cho truy vấn prefix có độ trễ thấp. Field dùng để gợi ý phải được mapping kiểu `completion`.

Ví dụ mapping JSON:

```json
{
  "properties": {
    "suggest": {
      "type": "completion",
      "analyzer": "simple",
      "search_analyzer": "simple",
      "preserve_separators": true,
      "preserve_position_increments": true,
      "max_input_length": 100
    }
  }
}
```

Spring Data Elasticsearch hỗ trợ `@CompletionField` và kiểu `Completion`:

```java
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@CompletionField(
    analyzer = "simple",
    searchAnalyzer = "simple",
    maxInputLength = 100
)
private Completion suggest;
```

Khi lưu sản phẩm, cung cấp các chuỗi có thể gợi ý:

```java
product.setSuggest(new Completion(new String[] {
    "iPhone 16",
    "Apple iPhone 16 Pro",
    "iPhone 16 Pro Max"
}));
```

Trọng số (weight) có thể dùng để ưu tiên một số suggestion nếu kiểu `Completion` và API phiên bản đang dùng hỗ trợ cấu hình tương ứng. Completion field được tối ưu cho lookup nhanh và sử dụng cấu trúc dữ liệu trong bộ nhớ; hãy theo dõi kích thước completion index khi có nhiều input.

### Query completion bằng REST

```http
POST /products/_search
Content-Type: application/json

{
  "_source": ["name", "category"],
  "suggest": {
    "product_autocomplete": {
      "prefix": "iph",
      "completion": {
        "field": "suggest",
        "size": 5,
        "skip_duplicates": true
      }
    }
  }
}
```

`prefix` là chuỗi người dùng đã nhập. `size` giới hạn số gợi ý và `skip_duplicates` loại các gợi ý trùng nhau. Completion suggester không phải spelling corrector; nếu cần sửa lỗi chính tả, cân nhắc term hoặc phrase suggester.

## 19. Khai báo suggest bằng `NativeQuery`

`NativeQueryBuilder` hỗ trợ `withSuggester(...)`, nhận `Suggester` của Elasticsearch Java API Client.

Ví dụ term suggester:

```java
import co.elastic.clients.elasticsearch.core.search.FieldSuggester;
import co.elastic.clients.elasticsearch.core.search.Suggester;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Suggester suggester = Suggester.of(s -> s
    .text("wireles hedphones")
    .suggesters("name_terms", FieldSuggester.of(fs -> fs
        .term(t -> t
            .field("name")
            .size(5)
        )
    ))
);

Query query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();
```

Có thể thêm `withQuery(...)` nếu cùng request cần lấy document hits và gợi ý. `withSuggester(...)` dùng API ELC; không nhầm với cấu hình của `RestHighLevelClient` ở các dòng tích hợp cũ.

Ví dụ completion suggester:

```java
Suggester suggester = Suggester.of(s -> s
    .suggesters("product_autocomplete", FieldSuggester.of(fs -> fs
        .prefix("iph")
        .completion(c -> c
            .field("suggest")
            .size(5)
            .skipDuplicates(true)
        )
    ))
);

Query query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();
```

Tên builder và kiểu enum của Java API Client được sinh theo phiên bản client do Spring Data quản lý. Nếu IDE không nhận một method, hãy kiểm tra version ELC thực tế và Javadoc tương ứng, không trộn import từ client cũ.

## 20. Đọc suggest từ `SearchHits`

Kết quả suggest nằm ở cấp `SearchHits`, không nằm trong `SearchHit` riêng lẻ:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.Suggest;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.hasSuggest()) {
    Suggest suggest = results.getSuggest();
    Suggest.Suggestion<?> nameSuggestion =
        suggest.getSuggestion("name_terms");

    if (nameSuggestion != null) {
        for (Suggest.Suggestion.Entry<?> entry : nameSuggestion.getEntries()) {
            String originalToken = entry.getText();

            for (Suggest.Suggestion.Entry.Option option : entry.getOptions()) {
                String candidate = option.getText();
                Double score = option.getScore();
            }
        }
    }
}
```

`Suggest.getSuggestion(name)` lấy gợi ý theo tên đã khai báo trong request. Mỗi suggestion có thể chứa nhiều entry; mỗi entry có thể chứa nhiều option. `getText()` của entry là token/cụm đầu vào, còn `getText()` của option là candidate được đề xuất. Một số loại option còn có score, highlighted text, document frequency hoặc metadata riêng.

Đối với term suggestion, `TermSuggestion.Entry.Option` cung cấp thêm `getFreq()`. Đối với completion suggestion, option có thể chứa thông tin hit/document tương ứng. Hãy đọc theo loại suggester khi cần metadata chuyên biệt.

## 21. Kết hợp highlight, aggregation và suggest trong một search

Một request có thể chứa nhiều thành phần kết quả cùng lúc:

- Query tìm sản phẩm theo nội dung.
- Highlight đánh dấu từ khớp trong tên/mô tả.
- Aggregation đếm số sản phẩm theo danh mục.
- Suggest đề xuất cách viết hoặc autocomplete.

Ví dụ REST DSL rút gọn:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "multi_match": {
      "query": "wireless headphones",
      "fields": ["name", "description"]
    }
  },
  "highlight": {
    "fields": {
      "name": { "number_of_fragments": 0 },
      "description": {
        "fragment_size": 160,
        "number_of_fragments": 2
      }
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 10
      }
    }
  },
  "suggest": {
    "name_terms": {
      "text": "wireles hedphones",
      "term": {
        "field": "name",
        "size": 5
      }
    }
  }
}
```

Trong response, highlight nằm trong từng hit, aggregation nằm trong `aggregations`, còn suggest nằm trong `suggest`. Query cấp cao nhất xác định tập document được tìm kiếm và cũng là tập đầu vào cho aggregation. Term suggester sử dụng suggest text và field riêng để tạo candidate.

Khi triển khai bằng `NativeQuery`, có thể kết hợp `withQuery`, `withHighlightQuery`, `withAggregation` và `withSuggester` trên cùng builder. Sau đó đọc từng phần từ `SearchHits` theo đúng cấp dữ liệu.

## 22. Phân biệt inner hits và aggregation

Hai tính năng này đôi khi bị nhầm vì đều trả về thông tin bên trong kết quả search:

| Tiêu chí | Inner hits | Aggregation |
|---|---|---|
| Mục tiêu | Trả về các document con cụ thể đã khớp | Tổng hợp hoặc nhóm nhiều document |
| Phạm vi | Gắn với từng parent hit | Gắn với toàn bộ search response hoặc bucket |
| Dữ liệu trả về | Nested/child hits cùng metadata | Metric và bucket như count, sum, avg |
| Ví dụ | Các biến thể màu đen size L của một sản phẩm | Số sản phẩm theo category |
| Cách đọc | `SearchHit.getInnerHits(name)` | `SearchHits.getAggregations()` |

Nếu giao diện cần hiển thị từng biến thể phù hợp, dùng inner hits. Nếu cần bộ lọc facet hoặc số lượng theo danh mục, dùng aggregation. Có thể kết hợp cả hai trong cùng request nếu thực sự cần.

## 23. Phân biệt highlight và suggest

Highlight đánh dấu phần văn bản đã khớp trong document được trả về. Suggest đề xuất văn bản thay thế hoặc phần tiếp theo người dùng có thể chọn.

| Tiêu chí | Highlight | Suggest |
|---|---|---|
| Dùng khi | Người dùng đã tìm thấy document và cần thấy chỗ khớp | Người dùng cần sửa từ hoặc hoàn thành truy vấn |
| Nguồn dữ liệu | Field trong document hit | Field được cấu hình cho suggester hoặc completion |
| Kết quả | Fragment của văn bản | Candidate suggestion và metadata |
| Vị trí Spring Data | `SearchHit.getHighlightField(s)` | `SearchHits.getSuggest()` |
| Có cần mapping riêng? | Tùy highlighter và field; thường dùng field text đã index | Completion cần field `completion`; term/phrase cần field và analyzer phù hợp |

Một trải nghiệm tìm kiếm tốt có thể dùng suggest trước khi người dùng gửi query, highlight sau khi có kết quả và aggregation để cung cấp facet lọc.

## 24. Hiệu năng và giới hạn cần lưu ý

### Highlight

- Chỉ highlight những field giao diện thực sự hiển thị.
- Giới hạn số fragment và fragment size cho field dài.
- Dùng `number_of_fragments: 0` có chủ đích với field ngắn.
- Highlighter có thể cần truy cập `_source`, postings hoặc term vectors tùy loại; chọn mapping phù hợp với workload.
- Tránh yêu cầu nhiều field dài trong một query có lượng hit lớn.

### Inner hits

- Giới hạn `inner_hits.size` vì mỗi parent hit có thể trả nhiều child hit.
- Chỉ lấy các field cần thiết từ nested document.
- Dùng `nested` khi cần giữ quan hệ phần tử; không chuyển mọi object thành nested vì nested có chi phí lưu trữ và truy vấn.
- Chú ý phân trang parent hits và số inner hits mỗi parent là hai giới hạn khác nhau.

### Aggregation

- Dùng `keyword`, numeric hoặc date field có mapping phù hợp.
- Giới hạn số bucket và độ sâu sub-aggregation.
- `terms.size` chỉ trả top bucket; dùng composite khi cần duyệt nhiều bucket.
- `cardinality` thường là ước lượng, không mặc định là số distinct chính xác.
- Dùng `size: 0` nếu chỉ cần aggregation, tránh truyền hits không cần thiết.

### Suggest

- Giới hạn `size` của candidate.
- Completion field dùng cấu trúc dữ liệu trong bộ nhớ; theo dõi kích thước và số input.
- Context completion làm tăng dung lượng và cần context nhất quán cả lúc index lẫn query.
- Term/phrase suggester cần analyzer và dữ liệu từ vựng phù hợp; không phải bộ sửa chính tả hoàn hảo.
- Đối với autocomplete, debounce request ở client và chỉ gửi prefix đủ dài để giảm tải.

## 25. Kiểm thử và chẩn đoán

Khi một phần kết quả bổ sung không xuất hiện, hãy kiểm tra theo từng lớp.

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| Highlight rỗng | Field có khớp query không, field name, analyzer, highlighter type và số fragment |
| Highlight sai đoạn | Query thực tế, analyzer, `require_field_match`, matched fields và nội dung `_source` |
| Inner hits không có | Mapping có phải `nested`, nested path, query có khớp child document và inner hits name |
| Inner hits không map thành entity | Kiểu nested class, mapping metadata và kiểu `SearchHit<?>` thực tế |
| Aggregation rỗng | Field mapping, query filter, tên aggregation và `hasAggregations()` |
| Bucket thiếu | `terms.size`, `shard_size`, cardinality hoặc cần composite aggregation |
| Suggest không trả candidate | Field suggester, analyzer, mapping completion hoặc input text |
| Completion trả duplicate | `skip_duplicates`, dữ liệu input và context mapping |

Các API hữu ích để kiểm tra:

```http
GET /products/_mapping
```

```http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "wireless headphones"
}
```

Chạy search request trực tiếp trong Elasticsearch Dev Tools trước để xác nhận response JSON có đủ `highlight`, `inner_hits`, `aggregations` hoặc `suggest`. Sau đó đối chiếu với các accessor Spring Data. Cách này giúp tách lỗi cấu trúc Query DSL khỏi lỗi ánh xạ response sang Java.

Trong integration test, dùng Elasticsearch version cố định tương thích với Spring Data/client của dự án. Nạp fixture, refresh index khi cần để search nhìn thấy dữ liệu, rồi kiểm tra cả document hits lẫn metadata bổ sung. Không chỉ assert repository trả về một document; hãy assert fragment highlight, inner hit ID, bucket count hoặc suggestion option tương ứng.

## 26. Chuyển kết quả thành DTO cho API

Không nhất thiết trả trực tiếp `SearchHits`, `ElasticsearchAggregations` hoặc các lớp suggest của Spring Data ra REST API. Nên tạo DTO chỉ chứa dữ liệu giao diện cần.

Ví dụ:

```java
public record ProductSearchItem(
        String id,
        String name,
        List<String> nameHighlights,
        List<String> descriptionHighlights,
        List<ProductVariant> matchingVariants,
        float score) {
}

public record CategoryFacet(String category, long count) {
}

public record ProductSearchResponse(
        List<ProductSearchItem> items,
        List<CategoryFacet> categories,
        List<String> suggestions,
        long totalHits) {
}
```

Service có thể chuyển từng `SearchHit` thành `ProductSearchItem`, đọc `getInnerHits("matching_variants")` cho biến thể, chuyển bucket aggregation thành `CategoryFacet` và chuyển suggest options thành danh sách chuỗi. DTO làm rõ hợp đồng API và tránh để frontend phụ thuộc vào kiểu ELC.

Khi chuyển highlight sang DTO, vẫn phải xử lý HTML an toàn ở tầng hiển thị. Nếu frontend nhận fragment chứa tag đánh dấu, quy định rõ tag nào được phép và encode phần văn bản không tin cậy.

## 27. Quy trình triển khai một trang kết quả tìm kiếm

Một trang tìm kiếm sản phẩm có thể được xây dựng theo trình tự:

1. Thiết kế mapping: text/keyword/numeric, nested variants và completion field nếu cần autocomplete.
2. Tạo query chính để tìm sản phẩm và xác định filter bắt buộc.
3. Thêm highlight cho tiêu đề/mô tả mà giao diện sẽ hiển thị.
4. Thêm nested query cùng inner hits nếu cần trả đúng biến thể đã khớp.
5. Thêm aggregation để tính facet theo danh mục hoặc khoảng giá.
6. Thêm suggest cho spelling correction hoặc autocomplete theo mục tiêu UX.
7. Thực thi qua `ElasticsearchOperations.search(...)` với `NativeQuery`.
8. Đọc hit metadata qua `SearchHit`, aggregation qua `SearchHits.getAggregations()` và suggestion qua `SearchHits.getSuggest()`.
9. Chuyển kết quả thành DTO có cấu trúc ổn định.
10. Kiểm thử dữ liệu biên, mapping, response và chi phí request trên Elasticsearch tương thích.

## 28. Kết luận

Spring Data Elasticsearch cung cấp một mô hình kết quả thống nhất để đọc các phần mở rộng của search response. Highlight và inner hits gắn với từng `SearchHit`; aggregation và suggest nằm ở cấp `SearchHits`. Dùng `@Highlight` cho repository method đơn giản hoặc `HighlightQuery` trong `NativeQuery` khi cần query linh hoạt. Dùng nested mapping và nested query có `inner_hits` khi cần trả về đúng phần tử con đã khớp. Dùng `withAggregation(...)` để khai báo metric/bucket và đọc qua `ElasticsearchAggregations`. Dùng `withSuggester(...)` để khai báo term, phrase hoặc completion suggester và lấy kết quả qua `SearchHits.getSuggest()`.

Mỗi tính năng có yêu cầu riêng về mapping và cách xử lý: highlight trả fragment chứ không sửa source, inner hits cần đúng nested path, aggregation phụ thuộc kiểu field và phạm vi query, còn completion cần field `completion` được lập chỉ mục. Khi giữ đúng ranh giới giữa từng phần response, kiểm tra mapping và chuyển dữ liệu sang DTO rõ ràng, ứng dụng có thể xây dựng trang tìm kiếm giàu thông tin mà vẫn kiểm soát được hiệu năng và cấu trúc API.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Search result types and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – Repository `@Highlight`](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repositories.html)
- [Spring Data Elasticsearch – `SearchHit` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHit.html)
- [Spring Data Elasticsearch – `SearchHits` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch – `NativeQueryBuilder` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Elasticsearch – Highlighting](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/highlighting)
- [Elasticsearch – Nested query and inner hits](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-nested-query)
- [Elasticsearch – Search suggesters](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters)
- [Elasticsearch – Aggregations](https://www.elastic.co/docs/explore-analyze/query-filter/aggregations)
