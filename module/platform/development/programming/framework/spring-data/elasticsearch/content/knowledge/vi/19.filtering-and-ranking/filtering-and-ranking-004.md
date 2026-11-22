# Disjunction max và cách kết hợp điểm nhiều trường

Khi tìm kiếm toàn văn, cùng một từ khóa có thể xuất hiện trong nhiều field của một document: tiêu đề, tên sản phẩm, mô tả, tên tác giả hoặc nội dung chi tiết. Elasticsearch cần một cách kết hợp điểm liên quan (relevance score) từ các field đó để xếp hạng kết quả.

**Disjunction max**, thường viết tắt là **dis_max**, là query kết hợp nhiều query con bằng cách ưu tiên điểm cao nhất. Nó phù hợp khi một document có thể khớp ở nhiều field nhưng việc khớp mạnh ở field quan trọng nhất nên quyết định phần lớn thứ hạng.

Công thức của dis_max là:

~~~text
score = max(score của các query con)
        + tie_breaker × tổng score của các query con còn lại
~~~

Với tie_breaker bằng 0, chỉ điểm cao nhất được dùng. Khi tie_breaker lớn hơn 0, các query con khác cũng đóng góp một phần vào điểm cuối. Cơ chế này khác với bool query có nhiều should clause, nơi điểm của các clause khớp thường được cộng lại.

Trong Spring Data Elasticsearch, có thể dùng NativeQuery để xây dựng dis_max hoặc multi_match theo Elasticsearch Query DSL. Bài này giải thích cách tính điểm, cách chọn tie_breaker, cách kết hợp nhiều field và các tình huống nên dùng dis_max, bool hoặc multi_match.

## 1. Bài toán tìm kiếm trên nhiều field

Giả sử document sản phẩm có cấu trúc:

~~~json
{
  "id": "P-1001",
  "title": "Wireless Mouse",
  "subtitle": "Ergonomic Bluetooth Mouse",
  "description": "A wireless mouse for office and travel use",
  "brand": "Northwind"
}
~~~

Người dùng tìm từ khóa wireless mouse. Cụm từ có thể xuất hiện trong:

- title: tên sản phẩm ngắn, thường rất quan trọng.
- subtitle: thông tin bổ sung, có thể quan trọng nhưng thấp hơn tiêu đề.
- description: nội dung dài, có thể chứa từ khóa nhưng mức liên quan thường thấp hơn.
- brand: tên thương hiệu, có semantics khác với nội dung mô tả.

Nếu chỉ tìm trong title, có thể bỏ sót document có từ khóa trong description. Nếu cộng điểm của mọi field một cách đơn giản, document có mô tả dài hoặc lặp từ khóa nhiều nơi có thể được đẩy lên quá cao.

Một cách tiếp cận là chạy query riêng trên từng field rồi kết hợp điểm bằng dis_max. Một cách khác là dùng multi_match với type phù hợp.

## 2. Disjunction max (dis_max) là gì?

dis_max nhận một danh sách query con. Document chỉ cần khớp ít nhất một query con để được đưa vào kết quả. Khi nhiều query con cùng khớp một document, Elasticsearch chọn điểm cao nhất làm phần chính của score.

Ví dụ REST DSL:

~~~http
POST /products/_search
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match": {
            "title": "wireless mouse"
          }
        },
        {
          "match": {
            "subtitle": "wireless mouse"
          }
        },
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ]
    }
  }
}
~~~

Document khớp ở bất kỳ field nào trong ba field trên đều có thể được trả về. Nếu document khớp cả title và description, score của query con có điểm cao nhất sẽ chi phối kết quả khi không đặt tie_breaker.

### 2.1. Vì sao gọi là disjunction max?

- **Disjunction** biểu thị logic OR: document có thể khớp một trong các query con.
- **Max** biểu thị điểm của query con tốt nhất được ưu tiên.

dis_max vừa kết hợp điều kiện theo kiểu OR, vừa áp dụng quy tắc tính điểm riêng. Nó không yêu cầu document khớp tất cả field.

### 2.2. dis_max không tự động có nghĩa là tìm chính xác hơn

dis_max là cơ chế kết hợp điểm, không phải một analyzer hay một loại matching riêng. Mỗi query con vẫn có semantics riêng: match, term, range hoặc query khác.

Ví dụ, ba query con đều là match query nên từng field được phân tích theo analyzer tương ứng. Nếu một field có mapping sai hoặc analyzer không phù hợp, dis_max không sửa được vấn đề đó.

## 3. Cách dis_max tính điểm

Giả sử một document có ba điểm từ các query con:

| Field | Query score |
|---|---:|
| title | 8.0 |
| subtitle | 4.0 |
| description | 2.0 |

Với tie_breaker = 0:

~~~text
score = 8.0 + 0 × (4.0 + 2.0)
      = 8.0
~~~

Với tie_breaker = 0.1:

~~~text
score = 8.0 + 0.1 × (4.0 + 2.0)
      = 8.6
~~~

Với tie_breaker = 0.5:

~~~text
score = 8.0 + 0.5 × (4.0 + 2.0)
      = 11.0
~~~

Với tie_breaker = 1:

~~~text
score = 8.0 + 1 × (4.0 + 2.0)
      = 14.0
~~~

Công thức tổng quát:

\[
S_{\text{dis\_max}} = S_{\max} + t \sum_{i \ne \max} S_i
\]

Trong đó:

- S_i là score của query con thứ i.
- S_max là score cao nhất trong các query con khớp.
- t là tie_breaker, thường nằm trong khoảng từ 0 đến 1.

Nếu chỉ có một query con khớp, tie_breaker không làm thay đổi score vì không có điểm phụ để cộng.

## 4. tie_breaker ảnh hưởng thứ hạng như thế nào?

tie_breaker điều khiển mức đóng góp của các query con không có score cao nhất.

| tie_breaker | Cách kết hợp | Ý nghĩa |
|---:|---|---|
| 0 | Chỉ lấy score cao nhất | Field khớp tốt nhất quyết định thứ hạng |
| 0.1 | Cộng 10% score của các query con còn lại | Có ghi nhận khớp ở nhiều field nhưng vẫn ưu tiên field tốt nhất |
| 0.3 | Cộng 30% score phụ | Nhiều field cùng khớp có ảnh hưởng rõ hơn |
| 0.5 | Cộng một nửa score phụ | Cân bằng hơn giữa khớp mạnh nhất và khớp ở các field khác |
| 1 | Cộng toàn bộ score phụ | Điểm gần với tổng score của các query con khớp |

tie_breaker mặc định của dis_max là 0 nếu không được chỉ định.

### 4.1. Ví dụ so sánh hai document

Tìm wireless mouse, có hai document:

| Document | title | description |
|---|---:|---:|
| A | 8.0 | 0.0 |
| B | 6.0 | 5.0 |

Với tie_breaker = 0:

- A có score 8.0.
- B có score 6.0.
- A đứng trên B.

Với tie_breaker = 0.5:

- A có score 8.0.
- B có score 6.0 + 0.5 × 5.0 = 8.5.
- B có thể đứng trên A.

Như vậy tie_breaker có thể thay đổi thứ hạng. Hãy chọn giá trị dựa trên cách sản phẩm muốn đánh giá độ liên quan, rồi kiểm tra với tập truy vấn và kết quả mong đợi thực tế.

### 4.2. tie_breaker không phải field boost

Hai cấu hình này giải quyết hai việc khác nhau:

- Field boost thay đổi tầm quan trọng của một field hoặc query con.
- tie_breaker quyết định phần score của các query con khớp bổ sung được cộng vào score lớn nhất.

Có thể dùng đồng thời cả hai. Ví dụ title có boost cao, còn tie_breaker nhỏ để ghi nhận document khớp thêm ở description.

## 5. Dùng dis_max với field boost

Field boost cho phép ưu tiên một field. Cú pháp boost trong query DSL thường được biểu diễn bằng dấu mũ trong danh sách field hoặc bằng thuộc tính boost của query.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match": {
            "title": {
              "query": "wireless mouse",
              "boost": 4
            }
          }
        },
        {
          "match": {
            "subtitle": {
              "query": "wireless mouse",
              "boost": 2
            }
          }
        },
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ],
      "tie_breaker": 0.15
    }
  }
}
~~~

Ý nghĩa:

- title được boost 4 lần theo hệ số boost của query.
- subtitle được boost 2.
- description giữ boost mặc định 1.
- tie_breaker 0.15 cho phép các field khác đóng góp một phần nhỏ khi cùng khớp.

Boost nhân vào score của query tương ứng, sau đó dis_max kết hợp các score đã điều chỉnh. Score cuối vẫn phụ thuộc query, analyzer, term statistics, mapping và dữ liệu thực tế; không thể hiểu boost như một điểm cộng cố định.

### 5.1. Boost không phải phần trăm xác suất

Boost 4 không có nghĩa document liên quan gấp bốn lần hoặc có xác suất đúng cao gấp bốn. Đây là hệ số ảnh hưởng tới điểm xếp hạng nội bộ.

Không nên so sánh score giữa hai query khác nhau như xác suất tuyệt đối. Hãy dùng score để xếp hạng trong cùng một truy vấn và kiểm tra kết quả trên tập dữ liệu đại diện.

## 6. Kết hợp query bằng dis_max và bool should khác nhau ra sao?

Cả dis_max và bool should đều có thể biểu diễn nhiều lựa chọn OR, nhưng quy tắc tính điểm khác nhau.

### dis_max

Với dis_max, score lớn nhất chi phối, các score còn lại chỉ đóng góp theo tie_breaker:

~~~http
POST /products/_search
{
  "query": {
    "dis_max": {
      "queries": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ],
      "tie_breaker": 0.1
    }
  }
}
~~~

### bool should

Với bool query có nhiều should clause, score của các clause khớp thường được cộng lại:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "should": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

| Đặc điểm | dis_max | bool.should |
|---|---|---|
| Logic khớp | OR giữa query con | OR giữa should clause, theo minimum_should_match |
| Score khi nhiều clause cùng khớp | Max + tie_breaker × tổng score còn lại | Thường cộng score của các clause khớp |
| Field mạnh nhất | Chi phối rõ | Có thể bị tổng nhiều field khác vượt qua |
| Điều khiển số clause phải khớp | Không có minimum_should_match trực tiếp ở dis_max | Có minimum_should_match |
| Trường hợp điển hình | Một field khớp rất tốt nên quan trọng hơn nhiều field khớp yếu | Muốn nhiều tín hiệu khớp cùng đóng góp mạnh vào điểm |

### 6.1. Khi nào dùng bool.should?

Dùng bool.should khi nhiều tín hiệu cùng khớp là bằng chứng liên quan cần cộng dồn.

Ví dụ:

- Tên sản phẩm khớp.
- Thương hiệu khớp.
- Danh mục khớp.
- Một tag quan trọng khớp.

Nếu muốn càng nhiều tín hiệu khớp thì document càng được ưu tiên, bool.should thường phù hợp.

### 6.2. Khi nào dùng dis_max?

Dùng dis_max khi các field là những vị trí thay thế nhau để tìm cùng một thông tin, và một kết quả khớp mạnh ở field quan trọng nhất nên chi phối.

Ví dụ tìm tên người trên firstName và fullName. Nếu document khớp rất mạnh ở fullName, không nhất thiết phải cộng toàn bộ score của firstName như một tín hiệu độc lập.

## 7. Multi_match và type best_fields

Elasticsearch cung cấp multi_match để tìm cùng một truy vấn trên nhiều field. Với type best_fields, Elasticsearch xây dựng logic gần tương đương dis_max trên các field được chỉ định.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless mouse",
      "type": "best_fields",
      "fields": [
        "title^4",
        "subtitle^2",
        "description"
      ],
      "tie_breaker": 0.15
    }
  }
}
~~~

Trong ví dụ:

- Cùng một chuỗi truy vấn được áp dụng lên nhiều field.
- title được ưu tiên bằng boost 4.
- subtitle được ưu tiên bằng boost 2.
- best_fields chọn score tốt nhất làm phần chính.
- tie_breaker cho phép các field còn lại đóng góp thêm.

Khi các field có cùng kiểu analysis phù hợp, multi_match best_fields là cách gọn để biểu đạt tìm kiếm nhiều field theo nguyên tắc dis_max.

### 7.1. best_fields và operator

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless mouse",
      "type": "best_fields",
      "fields": ["title", "description"],
      "operator": "and"
    }
  }
}
~~~

Với best_fields, điều kiện operator được áp dụng trong từng field query. Vì vậy document có wireless ở title và mouse ở description có thể không khớp nếu không field riêng lẻ nào chứa đủ các token theo AND.

Nếu muốn các token có thể xuất hiện ở các field khác nhau, hãy xem xét cross_fields.

## 8. Phân biệt best_fields, most_fields và cross_fields

multi_match có nhiều type với semantics khác nhau:

| Type | Cách kết hợp | Khi phù hợp |
|---|---|---|
| best_fields | Ưu tiên field có score tốt nhất, theo logic dis_max | Một field thường chứa phần lớn nội dung liên quan |
| most_fields | Cộng score từ nhiều field | Nhiều cách phân tích của cùng nội dung cùng đóng góp |
| cross_fields | Xử lý theo từng term trên nhiều field có analyzer tương thích | Các từ trong truy vấn có thể nằm ở những field khác nhau |
| phrase | Tìm cụm từ trên từng field | Cần thứ tự/vị trí token trong field |
| phrase_prefix | Tìm cụm từ với token cuối theo prefix | Gợi ý hoàn thành cụm từ |
| bool_prefix | Tìm theo token với prefix cho token cuối | Search-as-you-type trong một số thiết kế |

### 8.1. best_fields

Dùng khi một field đơn lẻ nên chứa phần lớn truy vấn:

~~~http
POST /people/_search
{
  "query": {
    "multi_match": {
      "query": "Will Smith",
      "type": "best_fields",
      "fields": ["firstName", "lastName", "fullName"]
    }
  }
}
~~~

Document có fullName khớp cả cụm có thể nhận score cao. best_fields phù hợp khi các field là lựa chọn thay thế, không phải các mảnh bắt buộc phải ghép lại.

### 8.2. most_fields

most_fields cộng điểm từ các field khớp. Nó hữu ích khi cùng nội dung được lưu ở nhiều field có analyzer hoặc cách biểu diễn khác nhau.

Ví dụ một tên sản phẩm có field title chuẩn, title.shingles và title.stemmed. Các field thể hiện các góc nhìn phân tích khác nhau của cùng nội dung:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless mouse",
      "type": "most_fields",
      "fields": [
        "title",
        "title.shingles",
        "title.stemmed"
      ]
    }
  }
}
~~~

Điểm từ các field được cộng để tăng hạng cho document khớp qua nhiều cách phân tích. Cách này khác với dis_max, nơi field có điểm cao nhất chi phối.

### 8.3. cross_fields

cross_fields phù hợp khi các phần của truy vấn có thể nằm trong các field khác nhau.

Ví dụ người dùng tìm Will Smith, trong khi dữ liệu được lưu riêng:

~~~json
{
  "firstName": "Will",
  "lastName": "Smith"
}
~~~

Dùng best_fields với operator AND có thể yêu cầu cả hai token xuất hiện trong cùng một field, dẫn tới không khớp. cross_fields xử lý theo hướng term-centric trên các field có analyzer tương thích:

~~~http
POST /people/_search
{
  "query": {
    "multi_match": {
      "query": "Will Smith",
      "type": "cross_fields",
      "fields": ["firstName", "lastName"],
      "operator": "and"
    }
  }
}
~~~

cross_fields có yêu cầu về analyzer và cách nhóm field. Các field có analyzer khác nhau có thể được xử lý thành nhóm riêng, làm semantics khác kỳ vọng. Kiểm tra mapping/analyzer của từng field trước khi chọn type này.

### 8.4. Chọn type theo cấu trúc dữ liệu

- Dữ liệu lặp lại ở nhiều field theo các cách phân tích khác nhau: cân nhắc most_fields.
- Các field thay thế nhau và muốn field tốt nhất quyết định: best_fields.
- Một truy vấn được phân tán qua nhiều field thành phần: cross_fields.
- Cần query tùy chỉnh trên từng field và quy tắc điểm rõ ràng: dis_max trực tiếp.

## 9. dis_max lồng trong bool query

dis_max có thể là một nhánh trong bool query. Điều này hữu ích khi muốn tìm kiếm nhiều field theo max score, đồng thời áp dụng các filter nghiệp vụ.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "dis_max": {
            "queries": [
              {
                "match": {
                  "title": {
                    "query": "wireless mouse",
                    "boost": 4
                  }
                }
              },
              {
                "match": {
                  "description": "wireless mouse"
                }
              }
            ],
            "tie_breaker": 0.1
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  }
}
~~~

Ở đây:

- dis_max kết hợp điểm của title và description.
- must yêu cầu document phải khớp dis_max.
- filter giới hạn kết quả theo active và category mà không cộng điểm relevance.
- Các filter không làm thay đổi thứ tự xếp hạng theo score của dis_max.

Đây là cấu trúc thường gặp trong search sản phẩm: phần full-text quyết định relevance, còn trạng thái và danh mục là điều kiện lọc.

## 10. Xây dựng dis_max bằng Spring Data Elasticsearch NativeQuery

Với Spring Data Elasticsearch 5.x sử dụng Elasticsearch Java API Client, NativeQuery có thể nhận query type của client.

Ví dụ tạo các query con:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Query titleQuery = Query.of(q -> q
    .match(m -> m
        .field("title")
        .query("wireless mouse")
        .boost(4.0f)
    )
);

Query descriptionQuery = Query.of(q -> q
    .match(m -> m
        .field("description")
        .query("wireless mouse")
    )
);

Query disMaxQuery = Query.of(q -> q
    .disMax(d -> d
        .queries(List.of(titleQuery, descriptionQuery))
        .tieBreaker(0.1)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(disMaxQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

Trong ví dụ:

- Query là co.elastic.clients.elasticsearch._types.query_dsl.Query.
- NativeQuery là org.springframework.data.elasticsearch.client.elc.NativeQuery.
- queries(...) nhận danh sách query con.
- tieBreaker(0.1) thiết lập mức đóng góp của score phụ.
- boost(4.0f) ưu tiên title.

Đây là ví dụ theo thế hệ Spring Data Elasticsearch 5.x và Elasticsearch Java API Client. Tên package, builder method và kiểu số của boost cần khớp minor version trong project. Không trộn Query của Criteria API với Query của Elasticsearch Java API Client.

## 11. Dùng multi_match trong NativeQuery

Nếu cùng một chuỗi được tìm trên nhiều field và muốn best_fields, multi_match có thể viết ngắn hơn dis_max thủ công.

Ví dụ với Elasticsearch Java API Client:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import co.elastic.clients.elasticsearch._types.query_dsl.TextQueryType;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query multiMatchQuery = Query.of(q -> q
    .multiMatch(m -> m
        .query("wireless mouse")
        .fields(List.of(
            "title^4",
            "subtitle^2",
            "description"
        ))
        .type(TextQueryType.BestFields)
        .tieBreaker(0.15)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(multiMatchQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

Cú pháp builder của Elasticsearch Java API Client có thể khác giữa các version. Nếu IDE không nhận TextQueryType hoặc method fields/type/tieBreaker, hãy kiểm tra Javadoc của dependency thực tế và dùng đúng enum/type của version đó.

### 11.1. Khi nào nên viết dis_max thủ công thay vì multi_match?

Dùng multi_match khi:

- Cùng một query string được áp dụng cho nhiều field.
- Cần field boosts.
- Muốn chọn best_fields hoặc một type multi_match khác.

Dùng dis_max thủ công khi:

- Mỗi field cần một query con khác nhau.
- Field cần analyzer, operator hoặc điều kiện riêng.
- Một nhánh dùng match, nhánh khác dùng term/prefix/fuzzy.
- Muốn kết hợp query con không chỉ là full-text trên cùng chuỗi.

Ví dụ query title có match_phrase nhưng description dùng match:

~~~http
POST /products/_search
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match_phrase": {
            "title": {
              "query": "wireless mouse",
              "boost": 4
            }
          }
        },
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ],
      "tie_breaker": 0.1
    }
  }
}
~~~

multi_match không phải cách thay thế trực tiếp cho mọi tổ hợp query con này.

## 12. Hiểu score của từng field

Score của match query thường dựa trên thuật toán BM25 theo cấu hình Elasticsearch. Một số yếu tố ảnh hưởng:

- Tần suất term trong document.
- Độ hiếm của term trong tập document.
- Độ dài field và chuẩn hóa theo độ dài.
- Analyzer và token được tạo ra.
- Query boost và các yếu tố liên quan khác.

Do đó score của title và description không chỉ phụ thuộc số từ khớp. Một term hiếm trong title có thể có điểm khác với cùng term trong description do thống kê và độ dài field.

Khi dùng dis_max, không nên giả định title luôn có score cao hơn description chỉ vì title ngắn. Nếu title cần được ưu tiên về nghiệp vụ, hãy đặt boost và kiểm tra kết quả thực tế.

### 12.1. Field length và nội dung lặp lại

Field description thường dài hơn title. BM25 có cơ chế chuẩn hóa độ dài, nhưng một field dài vẫn có thể chứa nhiều tín hiệu khớp. Nếu cộng score từ mọi field bằng bool.should hoặc most_fields, nội dung lặp lại có thể làm document tăng điểm.

dis_max giúp giảm hiện tượng cộng dồn này bằng cách chỉ cộng một phần score phụ. Tuy nhiên, nó không loại bỏ mọi ảnh hưởng của field length, term statistics hoặc analyzer.

## 13. Debug thứ hạng với Explain API

Khi document đứng sai vị trí, cần xem score được tính từ đâu thay vì đoán tie_breaker.

Elasticsearch Explain API:

~~~http
GET /products/_explain/P-1001
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match": {
            "title": {
              "query": "wireless mouse",
              "boost": 4
            }
          }
        },
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ],
      "tie_breaker": 0.1
    }
  }
}
~~~

Explain trả về thông tin giải thích vì sao document khớp hoặc không khớp và các thành phần đóng góp vào score. Có thể kiểm tra:

- Query con nào khớp.
- Score của từng nhánh.
- Boost đã được áp dụng ra sao.
- Phần score phụ từ tie_breaker.
- Term nào đóng góp điểm.

Search API cũng hỗ trợ explain: true để lấy thông tin giải thích cho từng hit:

~~~http
POST /products/_search
{
  "explain": true,
  "query": {
    "dis_max": {
      "queries": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ],
      "tie_breaker": 0.1
    }
  }
}
~~~

Explain có thể tạo response lớn và tốn chi phí. Chỉ bật khi debug một số document hoặc trong môi trường kiểm thử; không bật đại trà cho mọi request production.

### 13.1. Profile API

Profile API cung cấp thông tin chi tiết về thời gian thực thi query ở shard. Nó hữu ích khi điều tra hiệu năng, nhưng có overhead và không phải công cụ đo latency production chính xác.

Ví dụ:

~~~http
POST /products/_search
{
  "profile": true,
  "query": {
    "dis_max": {
      "queries": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ]
    }
  }
}
~~~

Dùng Explain để hiểu score; dùng Profile để nghiên cứu cấu trúc và thời gian thực thi query. Hai công cụ trả lời hai câu hỏi khác nhau.

## 14. Kết hợp dis_max với filter và minimum_should_match

dis_max không có tham số minimum_should_match giống bool query. Nó chỉ cần một query con khớp để document đủ điều kiện.

Nếu nghiệp vụ cần ít nhất hai trong ba tín hiệu khớp, hãy dùng bool.should với minimum_should_match:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "should": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "subtitle": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ],
      "minimum_should_match": 2,
      "filter": [
        { "term": { "active": true } }
      ]
    }
  }
}
~~~

Nếu chỉ cần một field khớp nhưng muốn field có score cao nhất chi phối, dis_max phù hợp hơn. Nếu cần quy định số field/tín hiệu tối thiểu, bool.should là cấu trúc phù hợp.

Lưu ý: trong bool query, khi có must hoặc filter, các should clause thường trở thành tùy chọn theo mặc định nếu không đặt minimum_should_match. Hãy đặt rõ giá trị nếu should phải là điều kiện bắt buộc.

## 15. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Document khớp nhiều field nhưng không tăng hạng | tie_breaker mặc định bằng 0 | Chọn tie_breaker > 0 nếu nhiều field cùng khớp cần đóng góp |
| Document có mô tả dài đứng quá cao | Cộng điểm nhiều field bằng bool.should hoặc most_fields | Cân nhắc dis_max và field boost |
| Title không được ưu tiên | Chưa boost field title | Dùng title^N hoặc boost cho query con |
| Kết quả có một từ vẫn được trả về | match mặc định có thể dùng OR | Dùng operator AND hoặc minimum_should_match |
| Từ khóa phân tán ở nhiều field không khớp | best_fields với AND yêu cầu đủ token trong một field | Xem xét cross_fields |
| Score thay đổi sau khi thêm field | Thống kê term và field/query composition thay đổi | Dùng Explain và kiểm tra ranking trên tập truy vấn |
| tie_breaker quá lớn làm thứ hạng khó đoán | Score phụ đóng góp quá nhiều | Giảm tie_breaker và đo lại |
| Search đúng field nhưng score thấp | Analyzer, mapping hoặc boost chưa phù hợp | Kiểm tra mapping, Analyze API và Explain |
| Query NativeQuery không biên dịch | Trộn kiểu Query/import hoặc version API khác | Kiểm tra package và version client |
| Search chậm | Nhiều query con, field lớn hoặc shard fan-out | Giới hạn field, filter trước và đo Profile/metrics |

## 16. Quy trình điều chỉnh ranking

Không nên chọn boost và tie_breaker chỉ dựa vào cảm giác. Hãy tạo một tập truy vấn đại diện cùng danh sách document mong muốn đứng đầu.

Quy trình gợi ý:

1. Xác định field nào là nguồn thông tin quan trọng nhất.
2. Viết query cơ bản bằng multi_match best_fields hoặc dis_max.
3. Đặt boost ban đầu cho field quan trọng như title.
4. Đặt tie_breaker thấp hoặc để mặc định 0 để có baseline.
5. Chạy tập truy vấn mẫu và xem top kết quả.
6. Dùng Explain để hiểu vì sao document được xếp hạng.
7. Thay đổi một yếu tố mỗi lần: boost, tie_breaker, analyzer hoặc query type.
8. So sánh thứ hạng trước/sau bằng các tiêu chí đánh giá phù hợp.
9. Giữ lại cấu hình có cải thiện ổn định trên nhiều truy vấn, không chỉ một ví dụ.

Các chỉ số đánh giá ranking có thể gồm Precision@k, Recall@k, Mean Reciprocal Rank (MRR) hoặc Normalized Discounted Cumulative Gain (NDCG), tùy mục tiêu tìm kiếm. Nếu chưa có tập relevance judgment, hãy thu thập truy vấn thực tế và đánh giá thủ công có cấu trúc.

## 17. Khi nào không nên dùng dis_max?

dis_max không phải lựa chọn mặc định cho mọi truy vấn nhiều field.

Không nhất thiết dùng dis_max khi:

- Các tín hiệu độc lập cần cộng dồn mạnh để tăng thứ hạng.
- Từ khóa cần được phân phối qua nhiều field như firstName và lastName.
- Cần yêu cầu ít nhất một số lượng field/tín hiệu nhất định khớp.
- Query cần logic phức tạp theo nhóm AND/OR.
- Một field đã có mapping/structure phù hợp để biểu đạt truy vấn đơn giản hơn.

Các lựa chọn thay thế:

| Nhu cầu | Cấu trúc phù hợp |
|---|---|
| Ưu tiên field khớp tốt nhất | dis_max hoặc multi_match best_fields |
| Cộng điểm từ nhiều cách phân tích | multi_match most_fields |
| Ghép token trên các field thành phần | multi_match cross_fields |
| Cộng điểm từ nhiều tín hiệu độc lập | bool.should |
| Yêu cầu tối thiểu N clause khớp | bool.should + minimum_should_match |
| Lọc bắt buộc nhưng không cộng score | bool.filter |
| Điều chỉnh điểm bằng quy tắc tùy chỉnh | function_score hoặc script_score khi thực sự cần |

## 18. Checklist trước khi đưa ranking vào ứng dụng

- Các field được tìm có mapping text/keyword phù hợp.
- Analyzer của các field được hiểu rõ và nhất quán với query type.
- Field quan trọng đã có boost hợp lý.
- tie_breaker được chọn dựa trên kết quả thử nghiệm.
- Đã phân biệt dis_max với bool.should và multi_match type.
- Nếu cần AND giữa token trên nhiều field, đã đánh giá cross_fields.
- Nếu cần tối thiểu số tín hiệu khớp, đã dùng minimum_should_match đúng chỗ.
- Có tập truy vấn mẫu và kết quả mong muốn để đánh giá.
- Explain đã được dùng khi cần hiểu score.
- Không bật explain/profile đại trà trong production.
- Đã đo latency và tải với số field/query con gần thực tế.
- NativeQuery dùng đúng Elasticsearch Java API Client version.

## 19. Bảng tra cứu nhanh

| Mục đích | Cách dùng |
|---|---|
| Kết hợp nhiều query theo score cao nhất | dis_max |
| Cho score của query phụ đóng góp ít | tie_breaker từ 0 đến 1 |
| Ưu tiên title hơn description | Field boost, ví dụ title^4 |
| Tìm cùng query trên nhiều field theo max score | multi_match best_fields |
| Cộng score từ nhiều field | multi_match most_fields hoặc bool.should |
| Tìm token phân tán giữa firstName/lastName | multi_match cross_fields |
| Yêu cầu ít nhất N tín hiệu khớp | bool.should + minimum_should_match |
| Lọc trạng thái không ảnh hưởng score | bool.filter |
| Giải thích score một document | Explain API |
| Phân tích thời gian thực thi query | Profile API |
| Dùng từ Java trong Spring Data | NativeQuery + Elasticsearch Java API Client |

Disjunction max giúp kết hợp nhiều query bằng cách ưu tiên score cao nhất, đồng thời cho phép các query con khác đóng góp một phần qua tie_breaker. Khi tìm trên nhiều field, hãy chọn giữa dis_max/best_fields, most_fields, cross_fields và bool.should theo cấu trúc dữ liệu cũng như mục tiêu ranking. Field boost thể hiện mức quan trọng nghiệp vụ; tie_breaker thể hiện mức cộng điểm khi nhiều field cùng khớp. Dùng Explain và một tập truy vấn đại diện để điều chỉnh thứ hạng thay vì chọn các con số một cách tùy ý.

