# Exists query và ý nghĩa giá trị thiếu

Trong Elasticsearch, một field có thể xuất hiện trong JSON document nhưng không có giá trị được lập chỉ mục để tìm kiếm. Ngược lại, một field có giá trị được lập chỉ mục dù ứng dụng không cần kiểm tra nội dung cụ thể của nó. Vì vậy, khi cần tìm document có hoặc không có dữ liệu ở một field, cần hiểu **giá trị tồn tại trong index** khác với **thuộc tính xuất hiện trong `_source`** như thế nào.

Elasticsearch cung cấp **exists query** để tìm document có giá trị được lập chỉ mục cho một field. Muốn tìm document thiếu giá trị, thường dùng exists query bên trong bool query với nhánh `must_not`.

Trong Spring Data Elasticsearch, có thể xây dựng truy vấn này bằng Elasticsearch Java API Client `Query`, bọc trong `NativeQuery`, rồi thực thi qua `ElasticsearchOperations`. Hiểu đúng semantics của exists giúp tránh nhầm lẫn giữa null, chuỗi rỗng, mảng rỗng và field không được lập chỉ mục.

## 1. Exists query kiểm tra điều gì?

Exists query trả về document khi field có ít nhất một giá trị được Elasticsearch lập chỉ mục. Nó không đơn giản kiểm tra xem tên thuộc tính có xuất hiện trong JSON gốc hay không.

Giả sử index `products` có các document:

~~~json
{ "name": "Mechanical Keyboard", "description": "A keyboard for work" }
{ "name": "Wireless Mouse" }
{ "name": "USB Hub", "description": null }
{ "name": "Monitor Stand", "description": "" }
~~~

Với query:

~~~json
{
  "query": {
    "exists": {
      "field": "description"
    }
  }
}
~~~

Các document có giá trị `description` được lập chỉ mục sẽ được trả về. Trong ví dụ trên:

- Document có mô tả `"A keyboard for work"` có field tồn tại.
- Document không có thuộc tính `description` không có giá trị để lập chỉ mục.
- Document có `description: null` mặc định được xem là không có giá trị được lập chỉ mục.
- Document có `description: ""` vẫn có một giá trị chuỗi rỗng; chuỗi rỗng được xem là tồn tại.

Kết quả phụ thuộc mapping và cách index dữ liệu. Một giá trị có trong `_source` vẫn có thể không được tính là tồn tại nếu Elasticsearch không lập chỉ mục giá trị đó.

## 2. Field thiếu, null và chuỗi rỗng khác nhau thế nào?

Đây là ba trường hợp cần phân biệt khi thiết kế filter.

| Dữ liệu trong document | Kết quả exists mặc định | Giải thích |
|---|---|---|
| Không có field | Không khớp | Không có giá trị được lập chỉ mục |
| `"description": null` | Không khớp | JSON null mặc định không được lập chỉ mục |
| `"description": ""` | Khớp | Chuỗi rỗng vẫn là một giá trị |
| `"description": " "` | Khớp | Chuỗi chỉ chứa khoảng trắng vẫn là giá trị |
| `"description": []` | Không khớp | Mảng rỗng không có phần tử để lập chỉ mục |
| `"description": ["A", "B"]` | Khớp | Có ít nhất một phần tử được lập chỉ mục |
| `"description": [null, "A"]` | Khớp | Phần tử "A" được lập chỉ mục |

Với mảng, exists query chỉ cần một phần tử có giá trị được lập chỉ mục là document đã khớp. Mảng chứa null cùng một giá trị hợp lệ vẫn được xem là tồn tại.

Đừng dùng exists để kiểm tra chuỗi có nội dung hữu ích. Nếu ứng dụng coi chuỗi rỗng hoặc chỉ có khoảng trắng là thiếu, cần chuẩn hóa dữ liệu trước khi index hoặc bổ sung điều kiện nghiệp vụ phù hợp.

### JSON null không phải SQL NULL

Elasticsearch không phải cơ sở dữ liệu quan hệ và exists query không phải phép kiểm tra SQL `IS NULL` theo nghĩa trực tiếp. Elasticsearch tìm giá trị có trong cấu trúc lập chỉ mục.

Theo mặc định, JSON `null` và field bị bỏ qua đều không tạo term có thể tìm kiếm cho field đó. Nếu cần phân biệt hai trường hợp này về mặt nghiệp vụ, hãy lưu thêm trạng thái rõ ràng hoặc dùng một sentinel có quy ước.

## 3. Ví dụ mapping và dữ liệu

Một entity sản phẩm có thể khai báo:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
~~~

Trong mapping:

- `sku` là keyword, thường dùng để so khớp chính xác.
- `description` là text, dùng cho tìm kiếm toàn văn.
- `status` là keyword, phù hợp với các trạng thái như `PUBLISHED` hoặc `DRAFT`.

Exists query có thể kiểm tra bất kỳ field nào được lập chỉ mục, bất kể field đó là text, keyword, numeric, date hay kiểu dữ liệu khác hỗ trợ lập chỉ mục.

Ví dụ document:

~~~json
{
  "sku": "KB-1001",
  "description": "Mechanical keyboard for office use",
  "status": "PUBLISHED"
}
~~~

Exists query trên `description` không tìm nội dung "keyboard". Nó chỉ xác định document có giá trị được lập chỉ mục cho field đó hay không.

## 4. Tìm document có field bằng exists query

Query DSL cơ bản:

~~~json
{
  "query": {
    "exists": {
      "field": "description"
    }
  }
}
~~~

Có thể kết hợp nhiều điều kiện trong bool query. Ví dụ tìm sản phẩm đã xuất bản và có mô tả:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        },
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

`filter` phù hợp vì điều kiện tồn tại field chỉ dùng để giới hạn tập kết quả, không cần tính điểm liên quan.

Nếu cần kết hợp với tìm kiếm toàn văn, có thể đặt `match` trong `must` và exists trong `filter`:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

Truy vấn này vừa tìm tên theo nội dung, vừa yêu cầu document có giá trị được lập chỉ mục cho `description`.

## 5. Tìm document thiếu field bằng must_not exists

Để tìm document không có giá trị được lập chỉ mục cho một field, đặt exists query trong `must_not` của bool query:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

Kết quả bao gồm document:

- Không có thuộc tính `description`.
- Có `description: null` theo mapping mặc định.
- Có mảng `description: []`.
- Có giá trị nhưng giá trị đó không được lập chỉ mục vì một tùy chọn mapping hoặc lỗi dữ liệu được cấu hình bỏ qua.

Ví dụ tìm sản phẩm đã xuất bản nhưng chưa có mô tả:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        }
      ],
      "must_not": [
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

`must_not` là điều kiện loại trừ. Query không tìm một giá trị null cụ thể; nó loại các document có giá trị được lập chỉ mục cho field.

### Phân biệt must_not exists với term null

Không nên viết:

~~~json
{
  "query": {
    "term": {
      "description": null
    }
  }
}
~~~

Đây không phải cách chuẩn để tìm field thiếu hoặc JSON null. Hãy dùng `must_not exists` cho nhu cầu tìm document không có giá trị được lập chỉ mục.

## 6. Các lý do khiến giá trị trong _source không được tính là tồn tại

Một số cấu hình mapping có thể khiến giá trị vẫn xuất hiện trong `_source` nhưng không có giá trị được lập chỉ mục cho field.

| Nguyên nhân | Ví dụ | Hệ quả với exists |
|---|---|---|
| Field bị bỏ qua | Field không xuất hiện trong JSON | Không khớp |
| Giá trị null mặc định | `"description": null` | Không khớp |
| Mảng rỗng | `"tags": []` | Không khớp |
| Vượt `ignore_above` | Chuỗi keyword dài hơn giới hạn | Field đó không có giá trị được lập chỉ mục |
| Sai định dạng và `ignore_malformed` bật | Chuỗi không hợp lệ cho numeric/date | Giá trị field bị bỏ qua khi lập chỉ mục |
| Tắt cả `index` và `doc_values` | Field không có cấu trúc tra cứu | Không thể kiểm tra bằng exists |
| Dynamic mapping không lập chỉ mục field | Field mới trong object `dynamic: false` | Giá trị có thể còn trong source nhưng không được mapping/index |

### ignore_above

Với keyword, có thể cấu hình giới hạn độ dài:

~~~json
{
  "mappings": {
    "properties": {
      "externalCode": {
        "type": "keyword",
        "ignore_above": 20
      }
    }
  }
}
~~~

Nếu document chứa `externalCode` dài hơn 20 ký tự, giá trị có thể vẫn được lưu trong `_source`, nhưng không được lập chỉ mục cho field `externalCode`. Exists query trên field này sẽ không khớp document đó.

Nếu dùng multi-field, ví dụ `name` kiểu text và `name.keyword` kiểu keyword có `ignore_above`, kết quả exists trên hai field có thể khác nhau. Field text chính có thể tồn tại trong khi subfield keyword không có giá trị được lập chỉ mục.

### ignore_malformed

Với field numeric hoặc date, `ignore_malformed` cho phép Elasticsearch bỏ qua giá trị sai định dạng thay vì từ chối toàn bộ document.

~~~json
{
  "mappings": {
    "properties": {
      "rating": {
        "type": "integer",
        "ignore_malformed": true
      }
    }
  }
}
~~~

Nếu document có `"rating": "not-a-number"`, giá trị rating có thể bị bỏ qua khi lập chỉ mục. Document vẫn có thể được index với các field hợp lệ khác; exists query trên `rating` không khớp document đó.

Không nên bật `ignore_malformed` chỉ để che giấu dữ liệu sai. Nếu nghiệp vụ yêu cầu rating luôn là số hợp lệ, hãy validate ở ứng dụng và theo dõi lỗi dữ liệu.

### index và doc_values

Exists query cần có dữ liệu tra cứu được trong cấu trúc index phù hợp. Nếu một field bị cấu hình không lập chỉ mục và cũng không có doc values, Elasticsearch không có dữ liệu để kiểm tra sự tồn tại qua query.

Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "internalNote": {
        "type": "keyword",
        "index": false,
        "doc_values": false
      }
    }
  }
}
~~~

Giá trị `internalNote` vẫn có thể nằm trong `_source`, nhưng exists query không thể tìm document dựa trên field này. Với keyword, chỉ tắt `index` mà vẫn giữ `doc_values` có thể vẫn cho phép một số thao tác kiểm tra/đọc dựa trên doc values; cần xét đầy đủ mapping thay vì chỉ nhìn một thuộc tính.

### Dynamic mapping

Nếu object có `dynamic: false`, field mới có thể được giữ trong source mà không được thêm vào mapping. Khi đó, exists query trên field chưa được lập chỉ mục không thể tìm thấy giá trị đó.

Đây là lý do cần kiểm tra mapping thực tế khi exists query trả về kết quả khác với nội dung JSON mà ứng dụng đã gửi.

## 7. null_value: biến null thành một giá trị có thể tìm kiếm

Elasticsearch hỗ trợ mapping parameter `null_value` cho một số kiểu field. Khi document có giá trị JSON null, Elasticsearch thay thế null bằng một giá trị sentinel trong quá trình lập chỉ mục.

Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "status": {
        "type": "keyword",
        "null_value": "UNKNOWN"
      }
    }
  }
}
~~~

Với mapping này, document:

~~~json
{
  "status": null
}
~~~

được lập chỉ mục cho field `status` bằng giá trị sentinel `UNKNOWN`. Do đó:

- Exists query trên `status` sẽ khớp.
- Term query với `status = UNKNOWN` có thể khớp.
- Giá trị trong `_source` vẫn là JSON null; `null_value` không sửa nội dung source.

Ví dụ truy vấn:

~~~json
{
  "query": {
    "term": {
      "status": "UNKNOWN"
    }
  }
}
~~~

Dùng `null_value` khi nghiệp vụ muốn biểu diễn null thành một trạng thái có thể tìm kiếm. Hãy chọn sentinel không thể nhầm với giá trị thật; nếu một document có status thật là `UNKNOWN`, truy vấn không thể phân biệt nó với giá trị null đã được thay thế.

`null_value` không biến một field hoàn toàn bị bỏ qua thành field có giá trị. Nó áp dụng cho giá trị null tường minh trong dữ liệu được index, theo kiểu field và mapping hỗ trợ.

## 8. Exists query với mảng và object

### Mảng nhiều giá trị

Một field có thể chứa nhiều giá trị cùng kiểu:

~~~json
{
  "tags": ["mechanical", "wireless", "office"]
}
~~~

Exists query trên `tags` khớp nếu ít nhất một phần tử được lập chỉ mục. Nếu mảng là `[]` hoặc chỉ gồm các giá trị null theo mapping mặc định, query không khớp.

Với một mảng như:

~~~json
{
  "tags": [null, "wireless"]
}
~~~

Document vẫn khớp vì phần tử `wireless` được lập chỉ mục.

### Object thông thường

Với object mapping:

~~~json
{
  "manufacturer": {
    "name": "Acme",
    "country": "VN"
  }
}
~~~

Nên kiểm tra field lá như `manufacturer.name` hoặc `manufacturer.country`, vì đó là các field có mapping và giá trị cụ thể.

Không nên suy luận rằng chỉ vì object `manufacturer` xuất hiện trong source thì mọi field con đều tồn tại. Một object có thể chỉ chứa một số thuộc tính.

### Nested field

Với `nested` mapping, các object con được lập chỉ mục như các nested document riêng. Khi truy vấn field bên trong nested path, cần đặt exists query trong nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "comments",
      "query": {
        "exists": {
          "field": "comments.author"
        }
      }
    }
  }
}
~~~

Truy vấn trên tìm document cha có ít nhất một nested comment chứa giá trị được lập chỉ mục cho `comments.author`.

Nếu muốn tìm parent document có nested child thiếu author, cần dùng nested query với bool `must_not exists` bên trong nested path. Kết quả đó có nghĩa là tồn tại ít nhất một nested child thiếu author; nó không đồng nghĩa với việc parent không có nested child nào. Cần xác định đúng phạm vi nghiệp vụ trước khi viết query.

## 9. Sử dụng Exists query bằng Elasticsearch Java API Client

Trong Spring Data Elasticsearch 5.x, có thể tạo query bằng kiểu `co.elastic.clients.elasticsearch._types.query_dsl.Query`.

### Tìm document có field

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query existsQuery = Query.of(q -> q
        .exists(e -> e
                .field("description")
        )
);
~~~

### Tìm document thiếu field

~~~java
Query missingDescriptionQuery = Query.of(q -> q
        .bool(b -> b
                .mustNot(mn -> mn
                        .exists(e -> e
                                .field("description")
                        )
                )
        )
);
~~~

Trong ví dụ thứ hai:

- `bool` tạo nhóm điều kiện.
- `mustNot` loại document có giá trị được lập chỉ mục cho description.
- `exists` kiểm tra field description.

Đây là query DSL của Elasticsearch Java API Client, không phải interface `org.springframework.data.elasticsearch.core.query.Query` của Spring Data. Đặt tên biến rõ ràng như `missingDescriptionQuery` giúp tránh nhầm lẫn hai kiểu cùng tên.

## 10. Đóng gói vào NativeQuery và thực thi bằng Spring Data

Sau khi tạo Java Client Query, dùng `NativeQuery` để đưa nó vào Spring Data Query abstraction:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

Query missingDescriptionQuery = Query.of(q -> q
        .bool(b -> b
                .mustNot(mn -> mn
                        .exists(e -> e.field("description"))
                )
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(missingDescriptionQuery)
        .build();

SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);
~~~

`ElasticsearchOperations.search(...)` thực thi truy vấn và chuyển đổi kết quả thành `ProductDocument`. `SearchHits` chứa metadata và các kết quả tìm được.

Ví dụ service tìm sản phẩm chưa có mô tả:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductAuditService {

    private final ElasticsearchOperations operations;

    public ProductAuditService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> findWithoutDescription() {
        Query query = Query.of(q -> q
                .bool(b -> b
                        .mustNot(mn -> mn
                                .exists(e -> e.field("description"))
                        )
                )
        );

        NativeQuery nativeQuery = NativeQuery.builder()
                .withQuery(query)
                .build();

        return operations.search(
                nativeQuery,
                ProductDocument.class
        );
    }
}
~~~

Nếu chỉ cần kiểm tra một giá trị cụ thể, có thể dùng repository finder hoặc term query. Exists query dành cho câu hỏi field có giá trị được lập chỉ mục hay không, không thay thế truy vấn theo nội dung.

## 11. Kết hợp exists với các điều kiện khác

### Sản phẩm đã xuất bản nhưng thiếu ảnh

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        }
      ],
      "must_not": [
        {
          "exists": {
            "field": "imageUrl"
          }
        }
      ]
    }
  }
}
~~~

### Sản phẩm có mô tả và thuộc một danh mục

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "exists": {
            "field": "description"
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

### Sản phẩm thiếu ngày phát hành hoặc thiếu mô tả

Muốn tìm document thiếu ít nhất một trong hai field, dùng nhóm OR của các điều kiện missing:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "bool": {
            "must_not": [
              {
                "exists": {
                  "field": "releaseDate"
                }
              }
            ]
          }
        },
        {
          "bool": {
            "must_not": [
              {
                "exists": {
                  "field": "description"
                }
              }
            ]
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Nếu nghiệp vụ yêu cầu thiếu cả hai field, đặt hai nhóm missing trong `filter` hoặc `must` thay vì `should`. Luôn phân biệt "thiếu ít nhất một" với "thiếu tất cả".

## 12. Exists query khác gì sort missing và aggregation missing?

Exists query lọc document theo việc field có giá trị được lập chỉ mục hay không. Sort và aggregation có tùy chọn riêng để xử lý document thiếu field; các tùy chọn đó không có nghĩa là đang lọc document.

### Sort với missing

Ví dụ sort theo giá, đưa document thiếu giá xuống cuối:

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc",
        "missing": "_last"
      }
    }
  ]
}
~~~

`missing: "_last"` chỉ quy định vị trí của document thiếu giá trong kết quả sort. Các document đó vẫn có thể xuất hiện trong kết quả nếu query không loại chúng.

Nếu muốn chỉ lấy document có giá, hãy thêm exists filter:

~~~json
{
  "query": {
    "exists": {
      "field": "price"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

### Aggregation với missing bucket

Terms aggregation có thể gom các document không có giá trị cho field vào bucket `missing` nếu cấu hình:

~~~json
{
  "aggs": {
    "products_by_status": {
      "terms": {
        "field": "status",
        "missing": "UNKNOWN"
      }
    }
  }
}
~~~

Giá trị `missing` trong aggregation là giá trị thay thế cho mục đích nhóm kết quả aggregation. Nó không ghi ngược giá trị vào document và không làm field trở nên tồn tại trong mapping.

## 13. Phân biệt exists, term và match

| Query | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| `exists` | Field có giá trị được lập chỉ mục không? | Có description không? |
| `term` | Field có term bằng một giá trị cụ thể không? | status có đúng PUBLISHED không? |
| `match` | Nội dung có phù hợp với văn bản tìm kiếm sau phân tích không? | Tên có liên quan đến wireless keyboard không? |
| `must_not exists` | Field không có giá trị được lập chỉ mục phải không? | Sản phẩm chưa có description? |

Ví dụ, document có:

~~~json
{
  "description": "Wireless keyboard for office"
}
~~~

- Exists query trên `description` khớp.
- Term query với nguyên câu có thể không khớp như mong đợi nếu field là text đã phân tích.
- Match query với `keyboard` có thể khớp vì tìm kiếm toàn văn.

Exists query không kiểm tra chất lượng nội dung, độ dài hoặc giá trị cụ thể. Nó chỉ kiểm tra khả năng tìm thấy giá trị của field trong index.

## 14. Những lỗi thường gặp

### Nghĩ rằng exists kiểm tra thuộc tính trong _source

Field có thể còn trong source nhưng không có giá trị được lập chỉ mục do `ignore_above`, `ignore_malformed`, `dynamic: false` hoặc mapping tắt cả index lẫn doc values. Hãy kiểm tra mapping và dữ liệu thực tế.

### Coi chuỗi rỗng là thiếu

Chuỗi rỗng `""` vẫn được xem là một giá trị. Nếu nghiệp vụ muốn coi chuỗi rỗng như thiếu, hãy chuẩn hóa trước khi index hoặc dùng điều kiện bổ sung phù hợp.

### Dùng term null để tìm field thiếu

Term query không phải cách tìm missing field. Dùng bool `must_not exists`.

### Nhầm null_value với thay đổi _source

`null_value` chỉ thay giá trị null trong quá trình lập chỉ mục. Source vẫn giữ null, nhưng exists query có thể khớp vì sentinel được lập chỉ mục.

### Không xét mảng rỗng

`[]` không có phần tử nên không tạo giá trị để exists query tìm thấy. Một mảng có ít nhất một phần tử hợp lệ thì khớp.

### Quên ignore_above ở multi-field

`name` và `name.keyword` có thể cho kết quả exists khác nhau. Kiểm tra đúng field path mà truy vấn đang dùng.

### Dùng exists sai với nested mapping

Field nested phải được truy vấn trong đúng nested path. Nếu thiếu nested query, kết quả có thể không phản ánh cấu trúc object con như mong muốn.

### Dùng exists để kiểm tra nội dung hợp lệ

Exists không xác minh email đúng định dạng, mô tả không rỗng hay giá trị số nằm trong miền nghiệp vụ. Những quy tắc đó cần validation riêng.

## 15. Quy trình thiết kế filter theo giá trị thiếu

Khi xây dựng tính năng tìm document có hoặc thiếu field:

1. Xác định câu hỏi nghiệp vụ là "field có giá trị được lập chỉ mục" hay "thuộc tính có xuất hiện trong source".
2. Kiểm tra mapping của field: type, `null_value`, `ignore_above`, `ignore_malformed`, `index`, `doc_values`.
3. Kiểm tra dữ liệu mẫu gồm field bị bỏ qua, null, chuỗi rỗng, mảng rỗng và giá trị hợp lệ.
4. Dùng `exists` cho document có giá trị được lập chỉ mục.
5. Dùng `bool.must_not.exists` cho document thiếu giá trị được lập chỉ mục.
6. Với nested field, đặt exists query trong nested query đúng path.
7. Kết hợp filter với tenant, trạng thái hoặc quyền truy cập từ nguồn đã xác thực.
8. Nếu cần phân biệt null tường minh với field bị bỏ qua, thiết kế sentinel hoặc field trạng thái riêng.
9. Kiểm tra query trên dữ liệu thật và mapping thực tế.
10. Phân biệt filter missing với tùy chọn sort/aggregation dành cho missing.

## Kết luận

Exists query tìm document có giá trị được lập chỉ mục cho một field; bool query với `must_not exists` tìm document không có giá trị được lập chỉ mục. Field bị bỏ qua, JSON null mặc định và mảng rỗng thường được xem là thiếu, trong khi chuỗi rỗng vẫn được xem là tồn tại. Các mapping option như `null_value`, `ignore_above`, `ignore_malformed`, `index` và `doc_values` có thể làm thay đổi kết quả. Trong Spring Data Elasticsearch, có thể tạo exists query bằng Java Client DSL, bọc trong `NativeQuery` và thực thi qua `ElasticsearchOperations`.
