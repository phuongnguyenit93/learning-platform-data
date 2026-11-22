# Xây dựng tìm kiếm sản phẩm với text, keyword và multi-field

Một màn hình tìm kiếm sản phẩm thường cần nhiều cách hiểu cùng một giá trị. Với tên sản phẩm, người dùng có thể nhập một phần tên để tìm kiếm toàn văn, cần so khớp chính xác khi chọn một sản phẩm cụ thể, sắp xếp theo tên và thống kê theo thương hiệu. Nếu chỉ khai báo một field kiểu `text` hoặc `keyword`, một số thao tác sẽ không phù hợp hoặc phải đánh đổi độ chính xác và khả năng tìm kiếm.

Elasticsearch giải quyết bài toán này bằng cách phân biệt hai loại field chính:

- **`text`**: phân tích nội dung thành token để tìm kiếm toàn văn, hỗ trợ analyzer, stemming, stop words và phrase query.
- **`keyword`**: giữ giá trị như một term đơn để so khớp chính xác, lọc, sắp xếp và aggregation.

**Multi-field** cho phép index cùng một giá trị dưới nhiều cách biểu diễn. Ví dụ `name` là field `text` để tìm từ khóa, còn `name.keyword` là subfield `keyword` để exact match, sort và aggregation. Hai field này cùng lấy dữ liệu từ một thuộc tính source, không yêu cầu lưu hai bản tên trong JSON document.

Bài học này xây dựng một search model cho sản phẩm, thiết kế mapping, cấu hình Spring Data Elasticsearch, viết truy vấn full-text và exact-match, kết hợp relevance score với filter, đồng thời giải thích cách nâng mapping khi index đã có dữ liệu.

## 1. Bắt đầu từ nhu cầu tìm kiếm của sản phẩm

Giả sử một document sản phẩm có dữ liệu:

~~~json
{
  "productId": "KB-1001",
  "sku": "KB-1001-BLK",
  "name": "Wireless Mechanical Keyboard",
  "description": "Compact keyboard with hot-swappable switches",
  "brand": "KeyWorks",
  "category": "ACCESSORIES",
  "tags": ["wireless", "mechanical", "keyboard"],
  "status": "PUBLISHED",
  "priceMinor": 1299000,
  "updatedAt": "2026-11-13T08:30:00Z"
}
~~~

Một API tìm kiếm có thể cần đáp ứng các thao tác:

| Nhu cầu | Ví dụ | Field phù hợp |
|---|---|---|
| Tìm từ khóa trong tên | `mechanical keyboard` | `name` kiểu text |
| Tìm từ khóa trong mô tả | `hot-swappable` | `description` kiểu text |
| Exact match SKU | `KB-1001-BLK` | `sku` kiểu keyword |
| Exact match tên | `Wireless Mechanical Keyboard` | `name.keyword` |
| Lọc thương hiệu | `brand = KeyWorks` | `brand` kiểu keyword |
| Sắp xếp theo tên | A → Z | `name.keyword` |
| Thống kê theo thương hiệu | Đếm sản phẩm mỗi brand | `brand` kiểu keyword |
| Tìm kiếm nhiều trường | Tên hoặc mô tả | `multi_match` trên text fields |

Một field không nhất thiết chỉ phục vụ một thao tác. Multi-field cho phép giữ một source value nhưng index nó theo nhiều semantics khác nhau.

## 2. Text và keyword khác nhau như thế nào?

### Text: nội dung được phân tích

Khi index một field `text`, Elasticsearch chạy analyzer. Analyzer thường gồm:

1. Character filters: biến đổi chuỗi đầu vào trước khi tokenization.
2. Tokenizer: chia chuỗi thành token.
3. Token filters: lowercase, stemming, stop-word filtering hoặc các biến đổi khác.

Ví dụ analyzer tiêu chuẩn có thể biến:

~~~text
Wireless Mechanical Keyboard
~~~

thành các token gần như:

~~~text
wireless
mechanical
keyboard
~~~

Các token được ghi vào inverted index để tìm kiếm. Query `match` cũng phân tích input theo search analyzer rồi tìm các token phù hợp.

Vì vậy, `text` phù hợp với:

- Tìm một hoặc nhiều từ trong câu.
- Tìm cụm từ bằng phrase query.
- Tìm kiếm nhiều trường văn bản.
- Tính relevance score.
- Stemming hoặc analyzer theo ngôn ngữ.

Field text không phải lựa chọn mặc định cho exact filtering, sorting hay aggregation. Thông thường không nên bật fielddata trên text chỉ để sort hoặc aggregate; dùng keyword subfield sẽ phù hợp hơn.

### Keyword: một giá trị nguyên vẹn

Field `keyword` được index như một term duy nhất. Chuỗi:

~~~text
Wireless Mechanical Keyboard
~~~

được xem như một giá trị, không tách thành ba token như text field.

Keyword phù hợp với:

- Exact match bằng `term` query.
- Filter theo status, category, brand hoặc SKU.
- Sort.
- Terms aggregation.
- Grouping và cardinality.

Keyword mặc định thường phân biệt chữ hoa/chữ thường. Nếu muốn so khớp không phân biệt case, có thể dùng normalizer hoặc lưu thêm một field chuẩn hóa.

### So sánh trực tiếp

| Đặc điểm | text | keyword |
|---|---|---|
| Phân tích token | Có | Không, trừ normalizer một token |
| Tìm kiếm toàn văn | Phù hợp | Không phải mục đích chính |
| Exact term query | Thường không phù hợp với cả cụm | Phù hợp |
| Sort | Không nên dùng mặc định | Phù hợp |
| Aggregation | Thường không nên dùng mặc định | Phù hợp |
| Stemming | Có thể cấu hình analyzer | Không |
| Lowercase | Qua analyzer | Qua normalizer nếu cấu hình |
| Ví dụ | name, description | sku, brand, status |

Không nên coi `text` là “tìm gần đúng” còn `keyword` là “tìm chính xác tuyệt đối” trong mọi trường hợp. Kết quả phụ thuộc analyzer, normalizer, query type và mapping cụ thể.

## 3. Multi-field là gì?

Multi-field cho phép một source field có nhiều cách index. Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Document vẫn chỉ có:

~~~json
{
  "name": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch tạo các indexed representation:

- `name`: text để dùng analyzer tìm từ.
- `name.keyword`: keyword để exact match, sort và aggregation.

Tên `name.keyword` là đường dẫn field trong mapping, không phải thuộc tính JSON lồng nhau trong source. Source không cần chứa:

~~~json
{
  "name": {
    "keyword": "Wireless Mechanical Keyboard"
  }
}
~~~

Multi-field không tạo thêm một thuộc tính source độc lập. Nó tạo thêm cách biểu diễn trong index.

Một field có thể có nhiều subfield như `name.keyword`, `name.folded` hoặc `name.english` nếu các use case cần semantics khác nhau. Không nên tạo subfield chỉ vì có thể; mỗi field bổ sung làm tăng chi phí index và cần được duy trì trong mapping.

## 4. Thiết kế mapping cho index sản phẩm

Một mapping tường minh giúp kiểm soát analyzer, exact match và sort. Ví dụ dưới đây dùng:

- `name`: text để tìm kiếm.
- `name.keyword`: keyword phân biệt hoa thường để exact match.
- `name.folded`: keyword đã lowercase và bỏ dấu để exact match thân thiện hơn với người dùng.
- `description`: text.
- `sku`, `brand`, `category`, `status`: keyword.
- `priceMinor`: long để lưu giá theo đơn vị tiền nhỏ nhất đã quy ước.

Tạo index:

~~~http
PUT /products-v1
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folding_lowercase": {
          "type": "custom",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "sku": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      },
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          },
          "folded": {
            "type": "keyword",
            "normalizer": "folding_lowercase",
            "ignore_above": 256
          }
        }
      },
      "description": {
        "type": "text",
        "analyzer": "standard"
      },
      "brand": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      },
      "category": {
        "type": "keyword"
      },
      "tags": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      },
      "status": {
        "type": "keyword"
      },
      "priceMinor": {
        "type": "long"
      },
      "updatedAt": {
        "type": "date"
      }
    }
  }
}
~~~

`dynamic: strict` khiến Elasticsearch từ chối field không khai báo. Điều này giúp phát hiện sai lệch schema sớm, nhưng mọi field mới cần được thêm vào mapping trước khi writer gửi dữ liệu.

Normalizers chỉ áp dụng cho keyword field và phải tạo ra một token duy nhất. `lowercase` và `asciifolding` giúp giá trị brand/name folded được chuẩn hóa khi index và khi chạy các query term-level phù hợp.

`ignore_above: 256` ngăn giá trị quá dài được index vào keyword subfield. Source vẫn có thể giữ giá trị đó, nhưng exact match/sort/aggregation trên subfield sẽ không hoạt động với document vượt giới hạn. Chọn ngưỡng theo dữ liệu thực tế.

## 5. Chọn tên subfield rõ nghĩa

Tên subfield nên diễn đạt semantics:

| Field | Mục đích |
|---|---|
| `name` | Full-text search |
| `name.keyword` | Exact match có phân biệt case |
| `name.folded` | Exact match sau lowercase/asciifolding |
| `description` | Full-text search |
| `brand` | Filter/grouping không phân biệt case theo normalizer |
| `sku` | Exact SKU, chuẩn hóa theo policy |
| `category` | Exact category filter |
| `status` | Exact status filter |

Không phải mọi field text đều cần keyword subfield. Ví dụ description dài thường không cần exact-match hoặc sort. Ngược lại, `brand` vốn chỉ dùng để filter/aggregate có thể khai báo trực tiếp kiểu keyword, không cần một parent text.

Multi-field hữu ích nhất khi **cùng một giá trị** cần nhiều cách index. Nếu dữ liệu có hai thuộc tính khác nhau như `displayName` và `normalizedName` do nghiệp vụ quản lý riêng, hãy biểu diễn chúng thành hai source property thay vì giả lập multi-field.

## 6. Ánh xạ mapping bằng Spring Data Elasticsearch

Có thể mô tả document bằng annotation:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String productId;

    @Field(
            type = FieldType.Keyword,
            normalizer = "folding_lowercase"
    )
    private String sku;

    @MultiField(
            mainField = @Field(
                    type = FieldType.Text,
                    analyzer = "standard"
            ),
            otherFields = {
                    @InnerField(
                            suffix = "keyword",
                            type = FieldType.Keyword,
                            ignoreAbove = 256
                    ),
                    @InnerField(
                            suffix = "folded",
                            type = FieldType.Keyword,
                            normalizer = "folding_lowercase",
                            ignoreAbove = 256
                    )
            }
    )
    private String name;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String description;

    @Field(
            type = FieldType.Keyword,
            normalizer = "folding_lowercase"
    )
    private String brand;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(
            type = FieldType.Keyword,
            normalizer = "folding_lowercase"
    )
    private List<String> tags;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Long)
    private Long priceMinor;

    @Field(type = FieldType.Date)
    private Instant updatedAt;

    // Constructors, getters and setters
}
~~~

Các annotation quan trọng:

- `@Field(type = FieldType.Text)` khai báo field full-text.
- `@Field(type = FieldType.Keyword)` khai báo field exact/filter.
- `@MultiField` khai báo field chính và các subfield.
- `@InnerField` định nghĩa một subfield với suffix.
- `analyzer` điều khiển cách tokenization cho text.
- `normalizer` điều khiển chuẩn hóa keyword.
- `@Id` ánh xạ document ID vào metadata `_id`.

Annotation mô tả mapping, nhưng custom normalizer `folding_lowercase` vẫn phải được khai báo trong index settings trước khi mapping sử dụng nó. Có thể quản lý settings bằng resource JSON/YAML và tạo index qua `IndexOperations` hoặc migration/provisioning riêng.

Đừng giả định chỉ vì class có annotation là index production hiện tại tự thay đổi theo. Việc tạo index, mapping và alias nên có lifecycle rõ ràng.

## 7. Cấu hình analyzer và normalizer

Analyzer của text field quyết định token được index và query. `standard` phù hợp cho nhiều nội dung tiếng Anh tổng quát, nhưng không tự động là analyzer tốt nhất cho mọi ngôn ngữ hoặc mọi loại dữ liệu.

Với tiếng Anh, có thể cân nhắc analyzer hỗ trợ stemming:

~~~json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "product_english": {
          "type": "standard",
          "stopwords": "_english_"
        }
      }
    }
  }
}
~~~

Sau đó khai báo field text dùng analyzer đó. Nếu dùng analyzer tùy chỉnh, đảm bảo analyzer có mặt trên mọi node và index được tạo với settings đúng.

Normalizer dành cho keyword không chia giá trị thành nhiều token. Ví dụ:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folding_lowercase": {
          "type": "custom",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  }
}
~~~

Với normalizer này, `KEYWORKS` và `KeyWorks` được chuẩn hóa về dạng tương đương khi index/search theo field đó. `asciifolding` còn chuyển một số ký tự có dấu thành dạng ASCII tương ứng. Đây là lựa chọn nghiệp vụ: với tên thương hiệu, có thể hữu ích; với mã SKU phân biệt ký tự, cần quyết định có nên bỏ dấu hay không.

### Kiểm tra analyzer bằng _analyze API

~~~http
POST /products-v1/_analyze
{
  "analyzer": "standard",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Kiểm tra normalizer/keyword field:

~~~http
POST /products-v1/_analyze
{
  "normalizer": "folding_lowercase",
  "text": "KeyWörks"
}
~~~

Kết quả giúp thấy token hoặc normalized token thực tế. Khi search không trả kết quả như dự kiến, kiểm tra analyzer thường nhanh hơn việc thay query một cách phỏng đoán.

## 8. Dynamic mapping có đủ không?

Elasticsearch có thể tự tạo mapping khi gặp field mới. Với string, dynamic mapping thường tạo text field kèm keyword subfield `.keyword` theo cấu hình mặc định.

Điều đó tiện cho thử nghiệm, nhưng không nên dựa hoàn toàn vào dynamic mapping cho index sản phẩm quan trọng vì:

- Analyzer mặc định có thể không phù hợp với ngôn ngữ.
- Keyword subfield có thể có `ignore_above` mặc định.
- Field name và kiểu dữ liệu được quyết định từ document đầu tiên.
- Một field gửi số ở document đầu và chuỗi ở document sau có thể tạo lỗi mapping.
- Không kiểm soát được semantics của normalizer, sort và aggregation.
- Một object bất ngờ có thể làm mapping phát triển ngoài dự kiến.

Dùng explicit mapping cho các field có vai trò rõ ràng: name, SKU, brand, category, status, price và timestamps. Dynamic mapping có thể được bật cho vùng dữ liệu mở có kiểm soát, hoặc tắt bằng `dynamic: strict` khi schema phải nghiêm ngặt.

## 9. Index document và kiểm tra các field

Sau khi tạo index, ghi document:

~~~http
PUT /products-v1/_doc/P-1001
{
  "productId": "KB-1001",
  "sku": "KB-1001-BLK",
  "name": "Wireless Mechanical Keyboard",
  "description": "Compact keyboard with hot-swappable switches",
  "brand": "KeyWorks",
  "category": "ACCESSORIES",
  "tags": ["wireless", "mechanical", "keyboard"],
  "status": "PUBLISHED",
  "priceMinor": 1299000,
  "updatedAt": "2026-11-13T08:30:00Z"
}
~~~

Kiểm tra mapping:

~~~http
GET /products-v1/_mapping
~~~

Kiểm tra document source:

~~~http
GET /products-v1/_doc/P-1001
~~~

Source trả về vẫn có `name` là một chuỗi. Các multi-field chỉ xuất hiện trong mapping/indexed representation, không xuất hiện thành object lồng trong `_source`.

Nếu dùng Spring Data để lưu:

~~~java
ProductDocument product = new ProductDocument();
product.setId("P-1001");
product.setProductId("KB-1001");
product.setSku("KB-1001-BLK");
product.setName("Wireless Mechanical Keyboard");
product.setDescription(
        "Compact keyboard with hot-swappable switches"
);
product.setBrand("KeyWorks");
product.setCategory("ACCESSORIES");
product.setStatus("PUBLISHED");
product.setPriceMinor(1_299_000L);
product.setUpdatedAt(Instant.now());

productRepository.save(product);
~~~

Spring Data converter chuyển object thành source document. Mapping index phải tương thích với các field và kiểu dữ liệu thực tế.

## 10. Tìm kiếm toàn văn bằng match query

`match` là query phổ biến cho field text. Elasticsearch phân tích giá trị query bằng search analyzer phù hợp với field.

~~~http
GET /products-v1/_search
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Với analyzer standard, query text có thể được tách thành token `mechanical` và `keyboard`. Theo operator mặc định, match thường có semantics OR giữa các token. Có thể yêu cầu tất cả token:

~~~json
{
  "query": {
    "match": {
      "name": {
        "query": "mechanical keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

Hoặc kiểm soát tỷ lệ token cần match bằng `minimum_should_match`:

~~~json
{
  "query": {
    "match": {
      "name": {
        "query": "wireless mechanical keyboard",
        "minimum_should_match": "2"
      }
    }
  }
}
~~~

Chọn OR, AND hoặc minimum percentage theo trải nghiệm tìm kiếm. AND chính xác hơn nhưng có thể loại document khi người dùng nhập thêm từ không xuất hiện trong tên.

## 11. Tìm cụm từ bằng match_phrase

Nếu yêu cầu các từ xuất hiện theo thứ tự và khoảng cách phù hợp, dùng `match_phrase`:

~~~http
GET /products-v1/_search
{
  "query": {
    "match_phrase": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

`match_phrase` sử dụng vị trí token để kiểm tra phrase. Nó không tương đương exact string equality:

- Exact string equality: thường dùng keyword field.
- Phrase matching: dùng text field và match_phrase.
- Full-text matching: dùng match/multi_match.

Ví dụ tên `Wireless Mechanical Keyboard` có thể match phrase `mechanical keyboard`, dù source name không bằng chuỗi đó.

Có thể dùng `slop` để cho phép một số khoảng cách/hoán vị token, nhưng tăng slop làm query rộng hơn và có thể tốn chi phí hơn. Chỉ thêm khi UX cần.

## 12. Exact match bằng term query

Để tìm SKU chính xác, dùng keyword field và `term`:

~~~http
GET /products-v1/_search
{
  "query": {
    "term": {
      "sku": "KB-1001-BLK"
    }
  }
}
~~~

Exact name case-sensitive:

~~~http
GET /products-v1/_search
{
  "query": {
    "term": {
      "name.keyword": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

Exact name sau khi chuẩn hóa lowercase/asciifolding:

~~~http
GET /products-v1/_search
{
  "query": {
    "term": {
      "name.folded": "wireless mechanical keyboard"
    }
  }
}
~~~

Với keyword normalizer, query term-level phù hợp sẽ được chuẩn hóa theo mapping. Cần xác nhận bằng `_analyze` và integration test cho đúng version/server.

Không dùng `term` trên `name` text với kỳ vọng match nguyên câu. Text field đã được phân tích thành token; exact whole-value semantics thuộc keyword subfield.

## 13. Multi-match tìm trên nhiều text fields

Một màn hình tìm kiếm thường cần tìm cùng từ khóa trên tên và mô tả.

~~~http
GET /products-v1/_search
{
  "query": {
    "multi_match": {
      "query": "mechanical keyboard",
      "fields": [
        "name^3",
        "description"
      ],
      "type": "best_fields"
    }
  }
}
~~~

Ý nghĩa:

- `name^3`: tăng boost của field name.
- `description`: field hỗ trợ thêm.
- `best_fields`: chọn điểm phù hợp nhất giữa các field, có thể kết hợp tie breaker tùy cấu hình.

Boost không phải xác suất. `^3` chỉ là hệ số ảnh hưởng relevance score. Cần kiểm tra kết quả với dữ liệu đại diện, không chọn boost bằng cảm tính rồi coi đó là quy tắc cố định.

Các kiểu multi_match thường gặp:

| Type | Khi dùng |
|---|---|
| `best_fields` | Một field nên match tốt là đủ, ví dụ name hoặc description |
| `most_fields` | Kết hợp điểm từ nhiều representation của cùng nội dung |
| `cross_fields` | Các từ query có thể nằm rải trên nhiều field có analyzer tương thích |
| `phrase` | Phrase search trên nhiều field |
| `phrase_prefix` | Phrase với token cuối được xử lý theo prefix |

`most_fields` có ích khi một giá trị được index theo nhiều analyzer khác nhau, ví dụ field chính và subfield stemmed. `cross_fields` phù hợp với field có analyzer tương thích và query token có thể phân bố qua chúng. Chọn type theo semantics thay vì mặc định dùng một type cho mọi search.

## 14. Kết hợp text search với exact SKU

Khi người dùng nhập một chuỗi, có thể ưu tiên exact SKU nhưng vẫn cho phép full-text name/description.

~~~http
GET /products-v1/_search
{
  "query": {
    "bool": {
      "should": [
        {
          "term": {
            "sku": {
              "value": "KB-1001-BLK",
              "boost": 10
            }
          }
        },
        {
          "term": {
            "name.keyword": {
              "value": "KB-1001-BLK",
              "boost": 8
            }
          }
        },
        {
          "multi_match": {
            "query": "KB-1001-BLK",
            "fields": [
              "name^3",
              "description"
            ],
            "type": "best_fields"
          }
        }
      ],
      "minimum_should_match": 1,
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        },
        {
          "term": {
            "category": "ACCESSORIES"
          }
        }
      ]
    }
  }
}
~~~

`should` tạo các cách match thay thế. `minimum_should_match: 1` yêu cầu ít nhất một nhánh match. Filter status/category giới hạn tập document nhưng không ảnh hưởng relevance score.

Nếu dùng query text không phải SKU, exact SKU clause có thể không match; các nhánh full-text vẫn hoạt động. Trong thực tế, có thể nhận diện format SKU trước rồi tạo query khác nhau, miễn logic đó là quy tắc nghiệp vụ rõ ràng.

Không đưa filter bảo mật như tenant scope vào `should`. Tenant/visibility phải luôn nằm trong filter bắt buộc.

## 15. Dùng Spring Data NativeQuery

Spring Data Elasticsearch hiện đại cung cấp `NativeQuery` để kết hợp Query DSL của Elasticsearch Java API Client với pagination và các tùy chọn search.

Ví dụ multi-match:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.multiMatch(mm -> mm
                .query("mechanical keyboard")
                .fields("name^3", "description")
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(
                query,
                ProductDocument.class,
                IndexCoordinates.of("products-v1")
        );
~~~

`NativeQuery` là cách biểu diễn query cụ thể của Elasticsearch. Nếu dự án dùng Spring Data Elasticsearch 4.x/HLRC, API query builder và client sẽ khác; không copy nguyên đoạn code của dòng 5.x vào dự án cũ mà không kiểm tra migration/API.

Đọc từng hit:

~~~java
hits.getSearchHits().forEach(hit -> {
    ProductDocument product = hit.getContent();

    System.out.println(product.getName());
    System.out.println(hit.getScore());
});
~~~

`SearchHits<T>` giữ metadata như score, ID, sort values, highlight fields và total hits. Nếu chỉ lấy content thành list, một số metadata này sẽ bị mất.

## 16. Xây query kết hợp filter và multi-match trong Java

Một query production thường vừa tìm full-text vừa lọc status/tenant/category:

~~~java
String searchText = "mechanical keyboard";
String tenantId = "tenant-42";

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.multiMatch(mm -> mm
                        .query(searchText)
                        .fields("name^3", "description")
                ))
                .filter(f -> f.term(t -> t
                        .field("tenantId")
                        .value(tenantId)
                ))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value("PUBLISHED")
                ))
                .filter(f -> f.term(t -> t
                        .field("category")
                        .value("ACCESSORIES")
                ))
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();
~~~

`must` chứa text query có scoring. `filter` chứa điều kiện bắt buộc không cần scoring.

Nếu category là tùy chọn, chỉ thêm filter khi criteria có giá trị. Tenant và visibility scope phải được lấy từ identity đã xác thực và luôn được thêm cho endpoint người dùng thông thường.

Khi có nhiều nhánh OR như exact SKU hoặc text match, đặt các nhánh vào bool lồng nhau và xác định `minimum_should_match` rõ ràng.

## 17. Sắp xếp theo keyword field

Sort trên text field thường không phù hợp vì text được token hóa và không có doc values mặc định. Dùng keyword subfield:

~~~http
GET /products-v1/_search
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ],
  "query": {
    "match_all": {}
  }
}
~~~

`productId` là tie-breaker để thứ tự ổn định hơn khi nhiều sản phẩm có cùng tên.

Nếu muốn sort không phân biệt hoa thường và dấu, có thể dùng `name.folded`. Lưu ý sort theo normalized value có thể cho thứ tự khác với thứ tự từ điển của source gốc.

Không bật `fielddata=true` trên text field chỉ để tránh tạo keyword subfield. Fielddata có thể sử dụng nhiều heap. Hãy thiết kế mapping cho sort ngay từ đầu.

## 18. Aggregation trên keyword field

Đếm số sản phẩm theo brand:

~~~http
GET /products-v1/_search
{
  "size": 0,
  "aggs": {
    "products_by_brand": {
      "terms": {
        "field": "brand",
        "size": 20
      }
    }
  }
}
~~~

Terms aggregation thường cần keyword hoặc field có doc values phù hợp. Nếu dùng `brand` kiểu text, aggregation có thể bị từ chối do fielddata disabled hoặc phải bật fielddata với chi phí bộ nhớ.

Đếm theo category:

~~~json
{
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Nếu aggregation cần hiển thị label gốc nhưng keyword field đã normalize, cân nhắc giữ một field display value và một field normalized key, hoặc dùng bucket key và lookup display value từ ứng dụng. Không để việc chuẩn hóa làm mất thông tin hiển thị cần thiết.

## 19. Highlight kết quả text search

Highlight giúp UI đánh dấu phần văn bản match:

~~~http
GET /products-v1/_search
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
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

Highlight hoạt động trên field text và trả fragments. Không nên giả định fragment luôn là HTML an toàn để render; nếu dùng tag highlight, cấu hình pre/post tags phù hợp và escape nội dung trước khi đưa vào UI.

Trong Spring Data Elasticsearch, `SearchHit` có thể chứa highlight fields. Map chúng sang response DTO thay vì sửa trực tiếp document source.

## 20. Tìm kiếm theo SKU và prefix

SKU thường là keyword vì cần exact semantics. Nếu cần tìm theo tiền tố, có thể dùng prefix query:

~~~http
GET /products-v1/_search
{
  "query": {
    "prefix": {
      "sku": "KB-1001"
    }
  }
}
~~~

Prefix query có thể tốn kém nếu field cardinality lớn hoặc prefix quá ngắn. Đặt giới hạn độ dài input, cân nhắc index design và kiểm tra latency.

Nếu cần autocomplete theo từng ký tự, prefix query trên keyword không phải lúc nào cũng là giải pháp tối ưu. Có thể thiết kế subfield edge n-gram/search-as-you-type hoặc dùng completion suggester tùy UX. Analyzer/index settings phải nhất quán giữa index analyzer và search analyzer.

Không dùng wildcard query dạng `*keyboard*` trên mọi field để thay autocomplete; leading wildcard thường đắt.

## 21. Analyzer cho tiếng Việt và nội dung đa ngôn ngữ

Analyzer `standard` là điểm khởi đầu, nhưng không hiểu đầy đủ ngữ nghĩa tiếng Việt, dấu, biến thể từ và cách tách từ theo yêu cầu sản phẩm.

Các lựa chọn phụ thuộc dữ liệu:

- Giữ text gốc và dùng analyzer phù hợp.
- Tạo thêm field normalized cho exact/filter.
- Dùng plugin phân tích ngôn ngữ nếu yêu cầu tách từ tiếng Việt nâng cao.
- Dùng edge n-gram cho autocomplete nếu có yêu cầu.
- Giữ field keyword riêng cho SKU, category, brand code.
- Kiểm thử query với từ có dấu/không dấu, dấu câu và ký tự đặc biệt.

`asciifolding` hỗ trợ một số chuyển đổi ký tự có dấu sang ASCII, nhưng không thay thế tokenizer/ngữ pháp tiếng Việt. Đừng giả định lowercase + asciifolding tự tạo ra chất lượng search tiếng Việt như một analyzer chuyên dụng.

Nếu cài analysis plugin, plugin phải tương thích với Elasticsearch server version và có mặt trên các node cần thiết. Testcontainers cũng phải cài cùng plugin để test phản ánh môi trường đích.

## 22. Kiểm tra mapping và query bằng _explain

Khi một document không match hoặc score không như mong đợi, dùng `_explain`:

~~~http
GET /products-v1/_explain/P-1001
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Response giải thích document có match không và các phần đóng góp vào score.

Dùng `_validate/query` để kiểm tra query có hợp lệ:

~~~http
POST /products-v1/_validate/query?explain=true
{
  "query": {
    "multi_match": {
      "query": "mechanical keyboard",
      "fields": ["name^3", "description"]
    }
  }
}
~~~

Dùng `_analyze` để kiểm tra token; `_mapping` để kiểm tra field type; `_explain` để hiểu scoring. Mỗi API trả lời một câu hỏi khác nhau.

## 23. Thay đổi multi-field khi index đã có dữ liệu

Có thể thêm một multi-field vào mapping hiện hữu bằng put mapping nếu thay đổi được hỗ trợ:

~~~http
PUT /products-v1/_mapping
{
  "properties": {
    "name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    }
  }
}
~~~

Nhưng có một điểm quan trọng: **thêm multi-field không tự động index lại giá trị của các document cũ vào subfield mới**. Document mới sau thay đổi sẽ được index theo mapping mới; document cũ cần được backfill.

Có thể dùng `_update_by_query` để reprocess source hiện có cho field mới, hoặc tạo index version mới rồi reindex. Ví dụ:

~~~http
POST /products-v1/_update_by_query
~~~

Thực hiện trên môi trường phù hợp, kiểm tra số document được cập nhật và theo dõi task/timeout. Với index lớn, có thể cần batch/throttle hoặc quy trình reindex có kiểm soát.

Không thể đổi tùy ý kiểu field hiện hữu, ví dụ `name` từ text sang keyword, hoặc thay analyzer của field đã tạo theo cách sửa mapping đơn giản. Với thay đổi không tương thích, tạo index mới và reindex.

## 24. Versioned index và alias khi đổi mapping

Một quy trình an toàn hơn cho mapping thay đổi lớn:

~~~text
products-v1
    |
    | Create products-v2 with new mapping
    v
Reindex documents from v1 to v2
    |
    v
Validate counts, mappings and representative searches
    |
    v
Switch read/write alias to v2
    |
    v
Monitor application
    |
    v
Retire v1 after rollback window
~~~

Ví dụ tạo alias:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Alias cho phép ứng dụng dùng tên ổn định `products` trong khi index vật lý thay đổi. Việc switch alias cần được phối hợp với writer và migration để tránh ghi đồng thời vào index cũ/mới ngoài ý muốn.

Với thay đổi mapping/analyzer, hãy kiểm thử reindex, alias cutover, rollback và tính nhất quán dữ liệu. Không xóa index cũ ngay khi vừa switch alias.

## 25. Thiết kế API tìm kiếm sản phẩm

Request API nên mô tả nhu cầu nghiệp vụ:

~~~http
GET /api/products/search?q=mechanical%20keyboard&category=ACCESSORIES&page=0&size=20&sort=NAME_ASC
~~~

Request DTO:

~~~java
public record ProductSearchRequest(
        String q,
        String category,
        Integer page,
        Integer size,
        ProductSort sort
) {
}
~~~

Enum sort cho phép server kiểm soát field:

~~~java
public enum ProductSort {
    RELEVANCE,
    NAME_ASC,
    PRICE_ASC,
    UPDATED_DESC
}
~~~

Service:

~~~java
@Service
public class ProductSearchService {

    private final ProductSearchRepository searchRepository;
    private final CurrentTenantProvider tenantProvider;

    public ProductSearchResponse search(ProductSearchRequest request) {
        String tenantId = tenantProvider.requiredTenantId();

        ProductSearchCriteria criteria = new ProductSearchCriteria(
                tenantId,
                request.q(),
                request.category(),
                normalizePage(request.page()),
                normalizeSize(request.size()),
                normalizeSort(request.sort())
        );

        return searchRepository.search(criteria);
    }
}
~~~

Trong service thực tế, inject repository/provider qua constructor; ví dụ trên tập trung vào luồng. Không lấy tenant ID từ query parameter mà không kiểm tra authorization.

Page size cần có default và maximum. Sort field cần allowlist. Nếu query rỗng, quyết định endpoint có cho browse toàn bộ sản phẩm trong tenant hay yêu cầu ít nhất một điều kiện.

## 26. Repository search adapter

Một custom search adapter có thể dùng `ElasticsearchOperations` để chạy NativeQuery:

~~~java
public interface ProductSearchRepository {

    ProductSearchResult search(ProductSearchCriteria criteria);
}
~~~

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
        NativeQuery query = queryBuilder.build(criteria);

        SearchHits<ProductDocument> hits = operations.search(
                query,
                ProductDocument.class,
                IndexCoordinates.of("products")
        );

        return ProductSearchResult.from(hits);
    }
}
~~~

Cách này giữ controller/service độc lập với Query DSL. Với query rất đơn giản, repository derived method vẫn phù hợp. Dùng custom fragment khi có multi-match, exact SKU boost, filter tùy chọn, highlight hoặc aggregation.

## 27. DTO kết quả và relevance score

Search response thường cần cả document data lẫn metadata:

~~~java
public record ProductSearchItem(
        String productId,
        String name,
        String brand,
        Long priceMinor,
        Float score
) {
}
~~~

~~~java
public record ProductSearchResponse(
        List<ProductSearchItem> items,
        long totalHits,
        int page,
        int size
) {
}
~~~

Map từ `SearchHit<ProductDocument>`:

~~~java
private ProductSearchItem toItem(SearchHit<ProductDocument> hit) {
    ProductDocument source = hit.getContent();

    return new ProductSearchItem(
            source.getProductId(),
            source.getName(),
            source.getBrand(),
            source.getPriceMinor(),
            hit.getScore()
    );
}
~~~

Không nhất thiết trả score ra API công khai. Có thể dùng score để xếp hạng nội bộ và chỉ trả thứ tự. Nếu response cần highlight, thêm field riêng chứa fragments đã được xử lý an toàn.

Không trả entity persistence trực tiếp nếu nó chứa tenant ID, internal notes hoặc field chỉ phục vụ indexing.

## 28. Testcontainers integration test

Unit test có thể kiểm tra query builder tạo đúng field name, boost và bool structure. Nhưng chỉ integration test với Elasticsearch thật mới xác nhận mapping, analyzer, normalizer và query behavior.

Một container test cần pin version:

~~~java
@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:8.x.y"
            );

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add(
                "spring.elasticsearch.uris",
                elasticsearch::getHttpHostAddress
        );
    }
}
~~~

`8.x.y` là placeholder. Dùng image tương thích với Spring Data/client và pin version giống server mục tiêu.

Test các trường hợp:

1. `match(name)` tìm được token trong tên.
2. `match(description)` tìm được token trong mô tả.
3. `term(sku)` match đúng SKU.
4. `term(name.keyword)` có semantics case-sensitive như mapping.
5. `term(name.folded)` xử lý case/diacritics theo normalizer.
6. Sort theo `name.keyword` hoạt động.
7. Aggregation theo `brand` hoạt động.
8. `multi_match` ưu tiên tên theo boost.
9. Document thiếu field hoặc keyword value vượt `ignore_above` được xử lý theo thiết kế.
10. Tenant filter không trả document của tenant khác.

## 29. Kiểm thử analyzer và scoring

Không chỉ assert kết quả có document. Hãy kiểm tra thứ tự khi scoring là yêu cầu của UX.

Ví dụ dữ liệu:

| ID | Name | Description |
|---|---|---|
| P1 | Mechanical Keyboard | Compact wireless keyboard |
| P2 | Wireless Mouse | Mechanical switches not included |
| P3 | Keyboard Stand | Stand for mechanical keyboard |

Với query `mechanical keyboard`, có thể mong đợi P1 xếp trên vì tên match cả hai token và được boost. P3 cũng có thể match; P2 chỉ match phần description tùy query semantics.

Dùng test query thực tế, xem `_explain` khi thứ tự không đúng. Relevance phụ thuộc corpus, analyzer, field length, term frequency, boosts và query type; không nên assert score là một số cố định nếu không kiểm soát mọi dữ liệu/index setting.

Kiểm tra cả:

- Từ có dấu và không dấu.
- Chữ hoa/chữ thường.
- Dấu gạch nối trong SKU.
- Từ đơn và cụm từ.
- Token stop words.
- Tên dài vượt ignore_above.
- Brand có nhiều cách viết.
- Document mới và document backfill.

## 30. Các lỗi thường gặp

### Dùng text cho mọi field

Filter, sort và aggregation trên text không phù hợp hoặc cần fielddata tốn heap. Dùng keyword cho status, SKU, category và brand.

### Dùng keyword cho tên sản phẩm rồi mong tìm từng từ

Keyword giữ nguyên giá trị. Dùng text field cho full-text search.

### Dùng term query trên text

Text đã được phân tích thành token. Exact match nguyên giá trị nên dùng keyword subfield.

### Dùng match query trên SKU

SKU thường cần exact semantics. Dùng keyword và term query; prefix/autocomplete là use case riêng.

### Nghĩ multi-field tạo thêm thuộc tính source

Multi-field tạo indexed representation, không tạo JSON object lồng trong source.

### Nghĩ thêm multi-field sẽ tự backfill document cũ

Document cũ cần reprocess bằng update_by_query hoặc reindex để populate subfield mới.

### Sort trên text field

Dùng keyword subfield có doc values. Tránh bật fielddata chỉ để sort.

### Aggregation trên text field

Dùng keyword field/subfield cho terms aggregation.

### Không cấu hình normalizer nhưng mong exact match không phân biệt case

Keyword mặc định thường phân biệt case. Khai báo normalizer hoặc normalized field theo yêu cầu.

### Dùng asciifolding như analyzer tiếng Việt hoàn chỉnh

Asciifolding chỉ xử lý một số ký tự. Search tiếng Việt có yêu cầu tách từ/ngữ nghĩa nâng cao cần analyzer/plugin phù hợp và test thực tế.

### Thay analyzer hoặc kiểu field trực tiếp trên index hiện hữu

Thay đổi không tương thích thường cần index mới và reindex. Không cố cập nhật mapping tại chỗ.

### Tin dynamic mapping cho schema sản phẩm

Field đầu tiên quyết định mapping có thể tạo schema không phù hợp. Khai báo explicit mapping cho các field quan trọng.

### Chỉ unit test query builder

Unit test không xác nhận analyzer, mapping hoặc behavior của server. Bổ sung integration test.

## 31. Quy trình triển khai

Khi xây dựng tìm kiếm sản phẩm với text, keyword và multi-field:

1. Liệt kê use case: full-text, exact SKU, exact name, filter, sort, aggregation và autocomplete.
2. Chọn `text` cho nội dung cần tokenization.
3. Chọn `keyword` cho giá trị exact/filter/sort/aggregation.
4. Dùng `@MultiField` hoặc explicit mapping để tạo các representation của cùng source value.
5. Khai báo analyzer và normalizer trước khi tạo mapping sử dụng chúng.
6. Chọn normalizer theo semantics; không tự động lowercase/asciifold mọi mã định danh.
7. Tạo index với mapping rõ ràng và kiểm tra bằng `_mapping`.
8. Kiểm tra token bằng `_analyze`.
9. Dùng `match`, `match_phrase` và `multi_match` cho full-text.
10. Dùng `term` trên keyword field cho exact match.
11. Kết hợp relevance clauses với filter bắt buộc như tenant/status.
12. Dùng keyword subfield cho sort và aggregation.
13. Map SearchHits sang response DTO.
14. Nếu thêm multi-field, backfill document cũ; nếu đổi type/analyzer, cân nhắc index mới và reindex.
15. Test bằng Elasticsearch version được pin, với dữ liệu đại diện.
16. Theo dõi search latency, hit quality, shard behavior và index size.

## Tài liệu tham khảo

- [Elasticsearch — Text field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/text.html)
- [Elasticsearch — Keyword field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/keyword.html)
- [Elasticsearch — Multi-fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/multi-fields.html)
- [Elasticsearch — Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [Elasticsearch — Analyzers](https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-analyzers.html)
- [Elasticsearch — Normalizers](https://www.elastic.co/guide/en/elasticsearch/reference/current/normalizer.html)
- [Elasticsearch — Match query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-match-query.html)
- [Elasticsearch — Match phrase query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-match-query-phrase.html)
- [Elasticsearch — Multi-match query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-multi-match-query.html)
- [Elasticsearch — Term query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-term-query.html)
- [Elasticsearch — Update by query](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update-by-query.html)
- [Spring Data Elasticsearch — Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

## Kết luận

Xây dựng search sản phẩm đúng cách bằng cách dùng `text` cho nội dung cần phân tích và `keyword` cho exact/filter/sort/aggregation. Multi-field cho phép cùng source value có nhiều indexed representation như `name`, `name.keyword` và `name.folded`. Trong Spring Data Elasticsearch, khai báo mapping bằng annotation hoặc index settings/mapping có quản lý; dùng match/multi_match cho full-text và term cho keyword. Khi thay mapping, nhớ multi-field mới không tự backfill dữ liệu cũ; kiểm tra analyzer, mapping, sort, aggregation và scoring bằng integration test trên Elasticsearch thật trước khi triển khai.
