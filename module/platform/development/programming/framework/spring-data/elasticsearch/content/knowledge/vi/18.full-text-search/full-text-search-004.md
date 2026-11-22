# Term, terms và khác biệt với match

Elasticsearch có nhiều loại query để tìm document. Ba query dễ bị nhầm lẫn là term, terms và match:

- **term** tìm một giá trị đã được lập chỉ mục theo cách so khớp chính xác với một term.
- **terms** tìm document có field khớp với ít nhất một giá trị trong danh sách được cung cấp.
- **match** phân tích chuỗi truy vấn bằng analyzer của field rồi tìm các token được tạo ra.

Điểm quan trọng là "chính xác" trong Elasticsearch phụ thuộc vào mapping và quá trình analysis. Một field keyword thường giữ giá trị nguyên vẹn để lọc chính xác. Một field text thường được analyzer tách và chuẩn hóa thành token để tìm kiếm toàn văn. Vì vậy, chọn đúng query cần bắt đầu từ kiểu field và mapping thực tế, không chỉ từ tên method hoặc hình dạng chuỗi đầu vào.

## 1. Ba query giải quyết ba nhu cầu khác nhau

Giả sử index products chứa các document:

~~~json
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "status": "ACTIVE"
}
~~~

Các câu hỏi tương ứng:

| Nhu cầu | Query thường dùng |
|---|---|
| Tìm sản phẩm có SKU đúng bằng SKU-1001 | term |
| Tìm sản phẩm có status là ACTIVE hoặc IN_STOCK | terms |
| Tìm sản phẩm có tên liên quan đến từ wireless mouse | match |
| Tìm tên có cụm từ wireless mouse theo thứ tự | match_phrase |

Ví dụ REST API:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "sku": "SKU-1001"
    }
  }
}
~~~

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "status": ["ACTIVE", "IN_STOCK"]
    }
  }
}
~~~

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

Cùng là một chuỗi JSON, nhưng cách Elasticsearch xử lý giá trị của từng query rất khác nhau.

## 2. Term query: so khớp một term

term là query mức term (term-level query). Nó tìm document có giá trị đã lập chỉ mục khớp với giá trị được chỉ định.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "sku": "SKU-1001"
    }
  }
}
~~~

Nếu sku được mapping là keyword, query này tìm giá trị SKU tương ứng. Term query không chạy analyzer để tách chuỗi truy vấn thành token như match query.

Các trường hợp thường dùng:

- SKU, mã đơn hàng, mã khách hàng.
- Trạng thái như ACTIVE, PENDING, CANCELLED.
- Email hoặc username khi semantics so khớp đã được xác định.
- Giá trị boolean, số hoặc ngày.
- Một giá trị keyword cần so khớp chính xác.

### 2.1. Term không có nghĩa là so sánh nguyên văn với _source trong mọi trường hợp

Elasticsearch tìm trên term đã được lập chỉ mục, không so sánh trực tiếp chuỗi đầu vào với JSON _source.

Ví dụ field keyword được khai báo normalizer lowercase:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "username": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
~~~

Document được ghi:

~~~json
{
  "username": "Alice"
}
~~~

Term được lập chỉ mục sau normalizer là alice. Với keyword field có normalizer, Elasticsearch áp dụng normalizer ở thời điểm tìm kiếm cho các truy vấn phù hợp, bao gồm term-level query trên field đó. Vì vậy query sau có thể khớp:

~~~http
POST /users/_search
{
  "query": {
    "term": {
      "username": "ALICE"
    }
  }
}
~~~

Trong khi đó _source vẫn giữ cách viết ban đầu "Alice". Normalizer thay đổi cách field được lập chỉ mục và tìm kiếm, không ghi đè nội dung gốc trong _source.

Nếu keyword không có normalizer, giá trị thường phân biệt hoa thường. Hãy kiểm tra mapping trước khi suy luận kết quả.

### 2.2. Term trên field text

Không nên dùng term như thể nó là match query cho một field text.

Giả sử mapping:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    }
  }
}
~~~

Với standard analyzer, chuỗi "Wireless Mouse" có thể được phân tích thành các token:

~~~text
Wireless Mouse
      |
      v
wireless, mouse
~~~

Query:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "name": "Wireless Mouse"
    }
  }
}
~~~

thường không khớp, vì term query không phân tích chuỗi truy vấn thành hai token. Nó tìm một term tương ứng với giá trị được đưa vào. Ngược lại, term query với "wireless" có thể khớp token đã được analyzer lập chỉ mục:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "name": "wireless"
    }
  }
}
~~~

Cách dùng này đòi hỏi người viết query biết chính xác token mà analyzer đã tạo. Với tìm kiếm văn bản thông thường, match thường phù hợp hơn.

## 3. Terms query: so khớp với một trong nhiều giá trị

terms query nhận một danh sách giá trị. Document được khớp nếu field có ít nhất một giá trị trùng với một giá trị trong danh sách.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "status": ["ACTIVE", "IN_STOCK", "BACKORDER"]
    }
  }
}
~~~

Về logic, điều kiện gần tương đương:

~~~text
status = ACTIVE
OR status = IN_STOCK
OR status = BACKORDER
~~~

terms thường được dùng để:

- Lọc nhiều trạng thái được chấp nhận.
- Tìm document thuộc một tập ID.
- Lọc theo danh sách SKU hoặc mã danh mục.
- Áp dụng một tập giá trị do ứng dụng xác định.

### 3.1. Terms không yêu cầu tất cả giá trị phải khớp

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "category": ["accessories", "computer", "office"]
    }
  }
}
~~~

Document có category là accessories hoặc computer hoặc office đều có thể khớp. Query không yêu cầu một document phải có cả ba giá trị.

Nếu nghiệp vụ yêu cầu document phải thỏa nhiều điều kiện độc lập, dùng bool query với các điều kiện tương ứng hoặc terms_set nếu cần semantics về số lượng giá trị khớp trên một field nhiều giá trị.

### 3.2. Terms trên field chứa mảng

Một keyword field có thể chứa nhiều giá trị:

~~~json
{
  "tags": ["wireless", "bluetooth", "accessory"]
}
~~~

Query:

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "tags": ["bluetooth", "gaming"]
    }
  }
}
~~~

Document khớp nếu mảng tags chứa bluetooth hoặc gaming. Chỉ cần một giá trị trong danh sách query khớp với một giá trị của field là đủ.

Nếu cần document chứa đồng thời cả bluetooth và wireless, hãy ghép hai term query bằng bool must:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tags": "bluetooth"
          }
        },
        {
          "term": {
            "tags": "wireless"
          }
        }
      ]
    }
  }
}
~~~

### 3.3. Giới hạn số giá trị trong terms

Elasticsearch có giới hạn số giá trị trong một terms query. Mặc định phổ biến là 65.536 giá trị, được kiểm soát bằng index setting index.max_terms_count. Giá trị thực tế có thể được cấu hình khác trên cluster.

Không nên gửi một danh sách hàng trăm nghìn hoặc hàng triệu giá trị trong một query mà không đánh giá giới hạn và chi phí. Với tập ID lớn, cân nhắc chia batch, dùng terms lookup hoặc thay đổi thiết kế truy vấn.

### 3.4. Terms lookup

Elasticsearch có thể lấy danh sách giá trị cho terms query từ một document khác thay vì gửi toàn bộ danh sách trong request. Cơ chế này gọi là terms lookup.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "sku": {
        "index": "saved-filters",
        "id": "filter-1001",
        "path": "skus"
      }
    }
  }
}
~~~

Elasticsearch đọc field skus trong document filter-1001 của index saved-filters và dùng các giá trị đó cho terms query.

Terms lookup phù hợp khi danh sách filter được lưu sẵn trên Elasticsearch và được tái sử dụng. Cần bảo đảm document nguồn tồn tại, field path đúng, quyền truy cập phù hợp và các điều kiện cluster liên quan. Với danh sách nhỏ, truyền trực tiếp mảng values thường đơn giản hơn.

## 4. Match query: tìm kiếm có phân tích văn bản

match là query mức full-text. Trước khi tìm, Elasticsearch phân tích chuỗi truy vấn bằng analyzer của field (hoặc analyzer được chỉ định trong query).

Ví dụ field name kiểu text:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "analyzer": "standard"
    }
  }
}
~~~

Query:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "Wireless Mouse"
    }
  }
}
~~~

Với analyzer phù hợp, chuỗi truy vấn có thể được chuẩn hóa và tách thành các token wireless và mouse. Elasticsearch tìm document dựa trên các token này.

Match phù hợp với:

- Tên sản phẩm.
- Mô tả.
- Tiêu đề bài viết.
- Nội dung tài liệu.
- Trường văn bản cần tìm theo từ hoặc cụm từ.

### 4.1. Operator OR và AND

Mặc định, match query thường dùng operator OR giữa các token được phân tích. Ví dụ truy vấn "wireless mouse" có thể khớp document chứa wireless hoặc mouse, tùy analyzer và các tùy chọn query.

Có thể yêu cầu tất cả token phải khớp:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": {
        "query": "wireless mouse",
        "operator": "and"
      }
    }
  }
}
~~~

Với operator AND, document phải thỏa các token được tạo ra từ query theo điều kiện AND. Điều này vẫn không có nghĩa hai từ phải đứng cạnh nhau hoặc đúng thứ tự.

### 4.2. minimum_should_match

Nếu muốn kiểm soát số token cần khớp linh hoạt hơn AND/OR, dùng minimum_should_match:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": {
        "query": "wireless bluetooth ergonomic mouse",
        "minimum_should_match": "75%"
      }
    }
  }
}
~~~

Tùy cách tính và số token sau analysis, 75% yêu cầu một tỷ lệ token nhất định phải khớp. Tùy chọn này hữu ích khi truy vấn có nhiều từ và muốn cân bằng giữa độ bao phủ với độ chặt.

### 4.3. Match không đồng nghĩa với cụm từ chính xác

Query:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

không đảm bảo hai từ đứng liền nhau theo đúng thứ tự. Nếu cần tìm cụm từ, dùng match_phrase:

~~~http
POST /products/_search
{
  "query": {
    "match_phrase": {
      "name": "wireless mouse"
    }
  }
}
~~~

match_phrase vẫn sử dụng analysis và vị trí token (positions). Nó không phải phép so sánh chuỗi nguyên văn byte-for-byte với _source. Nếu cần exact value, dùng keyword field phù hợp.

## 5. Khác biệt quan trọng giữa term, terms và match

| Tiêu chí | term | terms | match |
|---|---|---|---|
| Loại query | Term-level | Term-level | Full-text |
| Số giá trị đầu vào | Một | Một danh sách | Một chuỗi truy vấn |
| Phân tích query bằng analyzer | Không | Không | Có |
| Logic mặc định | Một term phải khớp | Bất kỳ giá trị nào trong danh sách khớp | OR giữa các token thường là mặc định |
| Field thường dùng | keyword, số, boolean, date | keyword, ID, số, boolean, date | text |
| Dùng cho | Exact filter | Exact filter theo tập giá trị | Tìm kiếm nội dung |
| Có xử lý normalizer của keyword | Có, theo mapping/query behavior | Có, theo mapping/query behavior | Analyzer/normalizer của field áp dụng theo query semantics |

Tóm lại:

- term: một giá trị đã lập chỉ mục.
- terms: một trong nhiều giá trị đã lập chỉ mục.
- match: phân tích chuỗi truy vấn thành token rồi tìm văn bản.

## 6. Mapping quyết định query hoạt động ra sao

Một entity có thể cần vừa tìm toàn văn vừa lọc chính xác trên cùng một thuộc tính. Multi-fields giúp lập chỉ mục cùng một giá trị theo nhiều kiểu.

Ví dụ:

~~~http
PUT /products
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
      },
      "sku": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "price": {
        "type": "long"
      }
    }
  }
}
~~~

Mapping này tạo:

- name: text để match.
- name.keyword: keyword để exact filter, sort hoặc aggregation.
- sku: keyword để tìm chính xác SKU.
- status: keyword để lọc nhiều trạng thái bằng terms.
- price: long để range hoặc term query theo số.

Ví dụ tìm toàn văn:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

Tìm tên nguyên vẹn:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "name.keyword": "Wireless Mouse"
    }
  }
}
~~~

Nếu field keyword có normalizer, kết quả exact matching sẽ tuân theo giá trị đã chuẩn hóa. Hãy xem mapping trước khi chọn name hay name.keyword.

### 6.1. Không thể đổi text thành keyword chỉ bằng cách đổi query

Nếu name đang là text, dùng term query với chuỗi đầy đủ không biến field đó thành keyword. Ngược lại, dùng match trên field keyword cũng không tự tạo token như field text; keyword analyzer thường giữ toàn bộ giá trị như một token.

Muốn hỗ trợ cả hai cách tìm, hãy khai báo multi-field từ đầu hoặc bổ sung mapping theo quy trình phù hợp. Khi thêm multi-field cho dữ liệu đã tồn tại, cần cập nhật/reindex document cũ để giá trị được lập chỉ mục cho field mới.

## 7. Phân biệt term với match trên field keyword

Một field keyword thường dùng keyword analyzer, tức toàn bộ chuỗi được xem là một token. Do đó match trên keyword có thể cho kết quả gần như exact matching thay vì full-text search.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "sku": "SKU-1001"
    }
  }
}
~~~

Nếu sku là keyword, query string thường được xử lý như một giá trị đơn. Tuy vậy, khi mục tiêu là lọc chính xác một mã, term diễn đạt ý định rõ ràng hơn.

Không nên dùng match trên keyword rồi kỳ vọng tìm một phần chuỗi. Nếu cần tìm prefix hoặc wildcard, dùng query phù hợp như prefix hoặc wildcard trên keyword field và cân nhắc chi phí.

## 8. Term, terms và kiểu dữ liệu

Term-level query không chỉ dành cho chuỗi. Chúng còn hữu ích với kiểu dữ liệu có giá trị được lập chỉ mục trực tiếp.

### 8.1. Số

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "price": 259900
    }
  }
}
~~~

Tìm document có price đúng bằng 259900. Nếu cần khoảng giá, dùng range query:

~~~http
POST /products/_search
{
  "query": {
    "range": {
      "price": {
        "gte": 100000,
        "lte": 500000
      }
    }
  }
}
~~~

### 8.2. Boolean

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

### 8.3. Date

~~~http
POST /orders/_search
{
  "query": {
    "term": {
      "status": "PAID"
    }
  }
}
~~~

Với ngày giờ, thường dùng range query để biểu đạt khoảng thời gian. Cần bảo đảm format và timezone phù hợp mapping.

### 8.4. ID

Có thể dùng ids query khi cần tìm nhiều document theo _id:

~~~http
POST /products/_search
{
  "query": {
    "ids": {
      "values": ["P-1001", "P-1002", "P-1003"]
    }
  }
}
~~~

Đây là query chuyên biệt cho document ID. Nếu cần lọc theo field ID được lưu trong _source, hãy xác định field mapping và chọn term/terms tương ứng.

## 9. Bool query để kết hợp term, terms và match

Trong ứng dụng thực tế, các query thường được kết hợp. Ví dụ tìm sản phẩm có nội dung liên quan đến "wireless mouse", trạng thái thuộc ACTIVE hoặc IN_STOCK và giá tối đa 500.000:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless mouse",
              "operator": "and"
            }
          }
        }
      ],
      "filter": [
        {
          "terms": {
            "status": ["ACTIVE", "IN_STOCK"]
          }
        },
        {
          "range": {
            "price": {
              "lte": 500000
            }
          }
        }
      ]
    }
  }
}
~~~

Trong ví dụ:

- must chứa match để tìm văn bản và tham gia tính điểm liên quan.
- filter chứa terms và range để lọc chính xác mà không cần tính điểm cho các điều kiện đó.

Nếu điều kiện keyword chỉ dùng để giới hạn tập kết quả, filter thường phù hợp hơn must. Điều này giúp diễn đạt rõ mục tiêu của từng điều kiện và có thể tận dụng cơ chế cache filter khi thích hợp.

## 10. Tích hợp với Spring Data Elasticsearch

Có thể dùng ElasticsearchOperations cùng NativeQuery để xây dựng các query term-level và full-text. Ví dụ dưới đây sử dụng Spring Data Elasticsearch 5.x cùng Elasticsearch Java API Client.

### 10.1. Term query bằng NativeQuery

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Query termQuery = Query.of(q -> q
    .term(t -> t
        .field("sku")
        .value(FieldValue.of("SKU-1001"))
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(termQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

FieldValue và Query trong ví dụ thuộc Elasticsearch Java API Client, không phải Query của Spring Data Criteria API.

### 10.2. Terms query bằng NativeQuery

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

List<FieldValue> statuses = List.of(
    FieldValue.of("ACTIVE"),
    FieldValue.of("IN_STOCK")
);

Query termsQuery = Query.of(q -> q
    .terms(t -> t
        .field("status")
        .terms(tf -> tf.value(statuses))
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(termsQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

Danh sách values có semantics OR: document khớp nếu status bằng một trong các giá trị. Với một số lượng giá trị lớn, cần xem giới hạn terms query và kích thước request.

### 10.3. Match query bằng NativeQuery

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Operator;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query matchQuery = Query.of(q -> q
    .match(m -> m
        .field("name")
        .query(FieldValue.of("wireless mouse"))
        .operator(Operator.And)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(matchQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

Operator.And yêu cầu các token được analyzer tạo ra phải khớp theo semantics của match query. Nó không yêu cầu cụm từ nằm liền nhau; nếu cần cụm từ, dùng match_phrase.

Các builder method có thể khác theo minor version. Hãy xác nhận import và chữ ký API với phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client trong project.

## 11. Derived repository method có thay thế term/terms/match không?

Spring Data Elasticsearch hỗ trợ derived query method, ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByStatusIn(Collection<String> statuses);

    List<Product> findByName(String name);
}
~~~

Tên method giúp Spring Data suy ra query dựa trên property và predicate. Tuy nhiên, không nên giả định:

- findBySku luôn được triển khai bằng đúng JSON term query trong mọi version.
- findByStatusIn luôn giống hoàn toàn terms query trong mọi trường hợp.
- findByName luôn có semantics full-text mong muốn chỉ vì field có tên name.

Kết quả phụ thuộc phiên bản Spring Data Elasticsearch, mapping và query derivation được hỗ trợ. Nếu cần kiểm soát rõ term, terms hoặc match DSL, dùng @Query hoặc NativeQuery và kiểm tra request thực tế.

Ví dụ @Query cho một điều kiện term cố định:

~~~java
@Query("{\"term\":{\"sku\":\"?0\"}}")
List<Product> findExactSku(String sku);
~~~

Với query động hoặc kết hợp nhiều điều kiện, NativeQuery/ElasticsearchOperations thường dễ kiểm soát hơn việc ghép chuỗi JSON trong annotation.

## 12. Kiểm tra analyzer bằng Analyze API

Khi match hoặc term trên text field cho kết quả khác kỳ vọng, cần xem analyzer tạo ra token nào.

Ví dụ:

~~~http
POST /products/_analyze
{
  "field": "name",
  "text": "Wireless Mouse"
}
~~~

Response có thể chứa các token:

~~~json
{
  "tokens": [
    {
      "token": "wireless",
      "position": 0
    },
    {
      "token": "mouse",
      "position": 1
    }
  ]
}
~~~

Kết quả cụ thể phụ thuộc analyzer được mapping cho field. Nếu dùng custom analyzer, lowercase filter, stemming hoặc synonym, token có thể khác.

Analyze API giúp giải thích:

- Vì sao match với chữ hoa vẫn tìm thấy kết quả.
- Vì sao term với chuỗi đầy đủ không khớp field text.
- Vì sao từ gốc và từ đã stemming có thể tìm thấy nhau.
- Vì sao dấu câu hoặc ký tự đặc biệt bị tách/chuẩn hóa.

Có thể chỉ định analyzer trực tiếp trong Analyze API nếu cần thử nghiệm một cấu hình riêng, nhưng khi debug query thực tế nên kiểm tra analyzer được gắn vào field trong mapping.

## 13. Case sensitivity và normalizer

Đối với keyword, mặc định thường phân biệt hoa thường. Ví dụ:

~~~json
{
  "username": "Alice"
}
~~~

Với keyword không normalizer:

~~~http
POST /users/_search
{
  "query": {
    "term": {
      "username": "alice"
    }
  }
}
~~~

có thể không khớp vì giá trị khác chữ hoa/chữ thường.

Có thể khai báo lowercase normalizer cho keyword nếu nghiệp vụ muốn tìm không phân biệt hoa thường. Khi đó cả giá trị index và giá trị query được chuẩn hóa theo mapping.

Với text, analyzer thường có lowercase filter nên match query có thể tìm được nội dung bất kể cách viết hoa thường. Term query trên text không chạy analyzer cho giá trị query, do đó người viết phải biết token đã được chuẩn hóa ra sao.

Không nên tự động thêm lowercase hoặc asciifolding cho mọi field. Một số mã định danh có semantics phân biệt ký tự hoặc dấu. Chọn quy tắc theo nghiệp vụ.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| term với cả cụm từ không khớp field text | Analyzer đã tách thành nhiều token | Dùng Analyze API và match/match_phrase phù hợp |
| term không phân biệt hoa thường như mong đợi | Keyword không có normalizer hoặc token khác cách viết | Kiểm tra mapping và normalizer |
| terms trả nhiều kết quả hơn dự kiến | Query dùng OR giữa các giá trị | Xác nhận có cần AND hay terms_set không |
| terms không khớp một số giá trị | Sai kiểu, sai ký tự, normalizer hoặc field | Kiểm tra mapping và giá trị thực tế |
| match trả kết quả có một từ nhưng thiếu từ còn lại | Operator mặc định OR | Dùng operator AND hoặc minimum_should_match |
| match không yêu cầu đúng thứ tự từ | Match không phải phrase query | Dùng match_phrase |
| match trên keyword không tìm một phần chuỗi | Keyword thường là một token nguyên vẹn | Dùng text field hoặc prefix/wildcard tùy yêu cầu |
| Terms query quá lớn bị từ chối | Vượt index.max_terms_count hoặc request quá lớn | Chia batch, dùng terms lookup hoặc điều chỉnh thiết kế |
| Query chạy sai trên index cũ | Mapping/analyzer đã thay đổi nhưng dữ liệu chưa được reindex | Kiểm tra mapping và migration |
| Derived query không có semantics mong muốn | Version hoặc predicate support khác nhau | Dùng @Query/NativeQuery và kiểm tra API thực tế |

## 15. Quy trình chọn query

Khi xây dựng truy vấn, có thể đi theo thứ tự:

1. Xác định field được mapping là keyword, text, số, boolean hay date.
2. Nếu cần so khớp một giá trị đã lập chỉ mục, dùng term.
3. Nếu cần so khớp một trong nhiều giá trị, dùng terms.
4. Nếu cần tìm nội dung văn bản qua analyzer, dùng match.
5. Nếu cần các từ nằm theo cụm và thứ tự, dùng match_phrase.
6. Nếu cần tất cả token khớp, dùng operator AND hoặc minimum_should_match phù hợp.
7. Nếu query không cho kết quả như mong đợi, kiểm tra mapping, normalizer và Analyze API.
8. Nếu cần điều khiển DSL chính xác từ Spring Data, dùng NativeQuery hoặc @Query.

## 16. Bảng tra cứu nhanh

| Nhu cầu | Query |
|---|---|
| SKU chính xác | term trên keyword |
| Một trong nhiều trạng thái | terms trên keyword |
| Một trong nhiều ID | ids hoặc terms tùy field |
| Giá bằng một số cụ thể | term trên field số |
| Giá trong khoảng | range |
| Tìm nội dung theo từ | match trên text |
| Tất cả token phải khớp | match với operator AND |
| Tìm cụm từ theo thứ tự | match_phrase |
| Tìm chính xác giá trị gốc của text multi-field | term trên field .keyword |
| Tìm keyword không phân biệt hoa thường | term trên keyword có lowercase normalizer |
| Tìm một trong tập lớn lưu trên Elasticsearch | terms lookup |
| Kết hợp full-text và exact filter | bool với must match và filter term/terms |

term, terms và match không thể thay thế lẫn nhau. term tìm một term đã lập chỉ mục, terms tìm document khớp một trong nhiều giá trị, còn match phân tích chuỗi truy vấn thành token để tìm kiếm toàn văn. Hãy chọn query dựa trên mapping và analyzer của field: keyword cho lọc chính xác, text cho full-text, multi-fields khi một giá trị cần cả hai cách tìm. Trong Spring Data Elasticsearch, dùng NativeQuery hoặc @Query khi cần kiểm soát rõ DSL và kiểm tra analyzer/mapping thực tế khi kết quả không như mong đợi.

