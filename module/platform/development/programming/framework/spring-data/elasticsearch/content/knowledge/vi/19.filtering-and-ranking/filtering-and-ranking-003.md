# Boost từng trường và từng mệnh đề

Trong Elasticsearch, một truy vấn có thể tìm thấy đúng tập document nhưng thứ tự kết quả vẫn chưa phù hợp với kỳ vọng nghiệp vụ. Ví dụ người dùng tìm “wireless keyboard”; ứng dụng muốn bài viết có cụm từ trong `title` đứng cao hơn bài chỉ nhắc tới cụm từ trong `content`. Hoặc một sản phẩm có thương hiệu ưu tiên cần được xếp cao hơn sản phẩm khác dù cả hai đều khớp nội dung tìm kiếm.

**Boost** là cách điều chỉnh mức đóng góp của một field hoặc một query clause vào relevance score. Boost ở cấp field thường được cấu hình trong `multi_match` hoặc `query_string`, ví dụ `title^4`. Boost ở cấp mệnh đề được đặt trên từng query trong một truy vấn kết hợp, ví dụ `match` trên `title` có `boost: 2.0` còn `match` trên `description` giữ mặc định `1.0`.

Boost tác động tới xếp hạng dựa trên score. Nó không thay đổi dữ liệu trong `_source`, không sửa mapping và không bảo đảm một document luôn đứng ở vị trí cố định. Score còn phụ thuộc độ khớp, tần suất term, độ dài field, thống kê index, loại query và các clause khác.

## 1. Relevance score và ý nghĩa của boost

Các query tìm kiếm toàn văn như `match` và `multi_match` thường tạo relevance score cho mỗi hit. Elasticsearch dùng score để sắp xếp kết quả giảm dần nếu request không chỉ định sort khác.

Giả sử hai bài viết đều khớp truy vấn “spring data”:

- Bài A có cụm từ trong tiêu đề.
- Bài B chỉ nhắc tới cụm từ trong phần nội dung dài.

Nếu chỉ dùng một `multi_match` với các field có trọng số bằng nhau, điểm của hai bài có thể chưa phản ánh đúng mức quan trọng mà sản phẩm tìm kiếm mong muốn. Boost cho `title` giúp kết quả khớp ở tiêu đề có ảnh hưởng lớn hơn.

Trong Elasticsearch, boost mặc định của một query là `1.0`. Boost lớn hơn `1.0` làm tăng ảnh hưởng của query đó lên score; boost nhỏ hơn `1.0` làm giảm ảnh hưởng tương đối. Cần xem boost là một hệ số điều chỉnh relevance, không phải điểm số cuối cùng hay xác suất document đúng.

### 1.1 Boost không phải bộ lọc

Boost không quyết định document có được phép xuất hiện hay không. Nó điều chỉnh điểm của document đã thỏa query. Nếu document không match điều kiện bắt buộc, boost cao không làm nó xuất hiện.

Ví dụ:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "content": "wireless keyboard"
          }
        }
      ],
      "should": [
        {
          "match": {
            "title": {
              "query": "wireless keyboard",
              "boost": 3.0
            }
          }
        }
      ]
    }
  }
}
```

Document vẫn phải match `content` vì đó là điều kiện `must`. Nếu tiêu đề cũng match, clause `should` đóng góp thêm score. Nếu tiêu đề không match, document vẫn có thể xuất hiện nhờ `must`, nhưng không nhận phần score bổ sung đó.

### 1.2 Boost không bảo đảm thứ tự tuyệt đối

Một document được boost vẫn có thể đứng sau document khác nếu document kia có độ khớp mạnh hơn ở các phần còn lại của query. Ví dụ, một bài có tiêu đề khớp một token có thể nhận điểm thấp hơn bài có tiêu đề và nội dung cùng khớp nhiều token.

Nếu nghiệp vụ cần thứ tự tuyệt đối theo một thuộc tính, chẳng hạn giá thấp nhất trước hoặc thời gian mới nhất trước, hãy dùng `sort`. Boost dành cho relevance ranking, nơi nhiều tín hiệu được kết hợp thành score.

## 2. Boost từng field trong multi_match

Khi tìm một chuỗi trên nhiều field, `multi_match` cho phép gắn trọng số riêng cho từng field bằng cú pháp `^`.

Ví dụ mapping bài viết:

```json
PUT /articles
{
  "mappings": {
    "properties": {
      "title": { "type": "text" },
      "summary": { "type": "text" },
      "content": { "type": "text" },
      "status": { "type": "keyword" }
    }
  }
}
```

Tìm kiếm trên cả ba field nhưng ưu tiên tiêu đề:

```json
GET /articles/_search
{
  "query": {
    "multi_match": {
      "query": "spring data elasticsearch",
      "fields": [
        "title^4",
        "summary^2",
        "content"
      ]
    }
  }
}
```

Trọng số được hiểu tương đối:

| Field | Boost | Ý nghĩa thiết kế |
|---|---:|---|
| `title` | 4 | Tín hiệu mạnh nhất |
| `summary` | 2 | Quan trọng, nhưng thấp hơn tiêu đề |
| `content` | 1 (mặc định) | Tín hiệu nền |

Nếu không ghi `^`, field có boost mặc định `1.0`. Cú pháp `title^4` tương đương với việc đặt boost cho field đó trong cấu hình query. Nó không thay đổi mapping hoặc dữ liệu đã index.

### 2.1 Vì sao ưu tiên title?

Tiêu đề thường được biên tập để thể hiện chủ đề chính của tài liệu. Nếu từ khóa tìm kiếm xuất hiện trong tiêu đề, đó thường là tín hiệu relevance mạnh hơn việc từ khóa xuất hiện một lần trong nội dung dài.

Tuy nhiên, đây là giả định sản phẩm cần kiểm chứng. Với một số loại dữ liệu, `description`, `tags` hoặc `category` có thể quan trọng hơn `title`. Boost nên phản ánh hành vi tìm kiếm và đánh giá relevance thực tế, không chỉ dựa vào tên field.

### 2.2 Boost field trong query_string

`query_string` cũng hỗ trợ boost field:

```json
GET /articles/_search
{
  "query": {
    "query_string": {
      "query": "spring data elasticsearch",
      "fields": [
        "title^4",
        "summary^2",
        "content"
      ]
    }
  }
}
```

`query_string` có parser cú pháp riêng và cho phép người dùng biểu diễn toán tử hoặc chỉ định field. Nó phù hợp khi ứng dụng chủ động hỗ trợ cú pháp query nâng cao. Với search box nhận văn bản tự do, `multi_match` thường dễ kiểm soát hơn vì chuỗi người dùng không bị diễn giải như một biểu thức query hoàn chỉnh.

## 3. Boost từng field trong các kiểu multi_match

Boost field kết hợp với kiểu `multi_match` sẽ tạo ra các cách kết hợp score khác nhau. Không nên chỉ thay hệ số mà bỏ qua `type` của multi_match.

### 3.1 best_fields

`best_fields` là kiểu phổ biến khi một field khớp tốt có thể đại diện cho mức độ liên quan của document. Query được xây dựng theo hướng disjunction-max: score tốt nhất giữa các field là thành phần chính; `tie_breaker` có thể cộng thêm một phần score từ các field khác.

```json
GET /articles/_search
{
  "query": {
    "multi_match": {
      "query": "spring data",
      "type": "best_fields",
      "fields": ["title^4", "summary^2", "content"],
      "tie_breaker": 0.2
    }
  }
}
```

Kiểu này phù hợp khi nội dung khớp mạnh trong một field quan trọng hơn việc từ khóa xuất hiện rải rác ở nhiều field. `tie_breaker` cho phép score từ các field khớp khác đóng góp thêm, với mức ảnh hưởng được điều chỉnh.

### 3.2 most_fields

`most_fields` cộng điểm từ nhiều field khớp. Kiểu này có thể hữu ích khi cùng một nội dung được index qua nhiều cách phân tích hoặc nhiều field biểu diễn bổ sung cho nhau.

```json
GET /articles/_search
{
  "query": {
    "multi_match": {
      "query": "spring data",
      "type": "most_fields",
      "fields": ["title^3", "title.shingles", "title.stemmed"]
    }
  }
}
```

Vì score từ nhiều field có thể được cộng, một document khớp ở nhiều field có thể được ưu tiên. Cần kiểm tra xem đây có phải tín hiệu mong muốn hay làm kết quả bị thiên lệch do một nội dung được lặp lại ở nhiều field.

### 3.3 cross_fields

`cross_fields` xử lý nhiều field theo hướng term-centric: các term trong query có thể được tìm trên nhiều field như thể chúng thuộc một nhóm field logic. Kiểu này hữu ích khi dữ liệu được chia thành nhiều field nhưng người dùng tìm một cụm thông tin chung, ví dụ `first_name` và `last_name`.

```json
GET /people/_search
{
  "query": {
    "multi_match": {
      "query": "nguyen an",
      "type": "cross_fields",
      "fields": ["firstName^2", "lastName"]
    }
  }
}
```

`cross_fields` có các ràng buộc về analyzer và cách nhóm field. Hãy kiểm tra mapping để các field có analyzer tương thích. Không dùng nó như một cách thay thế chung cho `best_fields` hoặc `most_fields`.

### 3.4 Chọn kiểu nào?

| Kiểu | Cách kết hợp chính | Tình huống thường gặp |
|---|---|---|
| `best_fields` | Ưu tiên field có score tốt nhất | Một field khớp mạnh là tín hiệu chính |
| `most_fields` | Kết hợp score từ nhiều field | Nhiều field bổ sung cho cùng nội dung |
| `cross_fields` | Kết hợp theo term qua nhóm field | Một cụm thông tin được chia thành nhiều field |

Boost field không có cùng tác động trong mọi kiểu. Hãy chọn semantics multi_match trước, sau đó mới điều chỉnh hệ số field.

## 4. Boost một query clause

Boost ở cấp clause được khai báo trong query cụ thể. Cách này phù hợp khi một truy vấn kết hợp nhiều loại tín hiệu: nội dung chính, thương hiệu, danh mục, trạng thái nổi bật hoặc cụm từ ưu tiên.

Ví dụ query chính tìm nội dung, còn tiêu đề khớp sẽ được cộng thêm điểm:

```json
GET /articles/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "content": {
              "query": "spring data elasticsearch"
            }
          }
        }
      ],
      "should": [
        {
          "match": {
            "title": {
              "query": "spring data elasticsearch",
              "boost": 3.0
            }
          }
        }
      ]
    }
  }
}
```

`must` xác định nội dung cần khớp. `should` bổ sung tín hiệu ranking. Boost `3.0` làm score của clause tiêu đề có ảnh hưởng mạnh hơn mặc định khi clause đó khớp.

### 4.1 Boost cho từng clause trong bool

Có thể gắn boost khác nhau cho từng clause:

```json
GET /articles/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "spring data",
            "fields": ["title", "content"]
          }
        }
      ],
      "should": [
        {
          "term": {
            "status": {
              "value": "FEATURED",
              "boost": 2.0
            }
          }
        },
        {
          "match": {
            "title": {
              "query": "elasticsearch",
              "boost": 1.5
            }
          }
        },
        {
          "match_phrase": {
            "title": {
              "query": "spring data",
              "boost": 3.0
            }
          }
        }
      ],
      "filter": [
        { "term": { "published": true } }
      ]
    }
  }
}
```

Các clause `should` đóng góp score khi match. Clause `filter` giới hạn document được phép xuất hiện nhưng không đóng góp relevance score. `must_not` cũng dùng để loại document và không dùng như tín hiệu tăng điểm.

### 4.2 Boost một clause khác với boost một field

Hai cách có thể tạo ra query trông tương tự nhưng điều chỉnh ở hai cấp khác nhau:

- Field boost trong `multi_match` điều chỉnh ảnh hưởng của một field khi cùng một truy vấn được chạy trên nhiều field.
- Clause boost điều chỉnh ảnh hưởng của một query con trong một query tổng hợp.

Ví dụ field boost:

```json
"multi_match": {
  "query": "spring data",
  "fields": ["title^4", "content"]
}
```

Ví dụ clause boost:

```json
"bool": {
  "should": [
    { "match": { "title": { "query": "spring data", "boost": 4 } } },
    { "match": { "content": "spring data" } }
  ]
}
```

Field boost thuận tiện khi một chuỗi được tìm trên nhiều field. Clause boost linh hoạt hơn khi từng tín hiệu có query riêng hoặc có logic AND/OR riêng.

## 5. Vai trò của must, should, filter và must_not

Khi boost clause trong `bool`, cần hiểu semantics của từng nhóm:

| Clause | Bắt buộc khớp? | Đóng góp score? | Vai trò |
|---|---|---|---|
| `must` | Có | Có | Điều kiện bắt buộc và có scoring |
| `should` | Tùy ngữ cảnh | Có khi khớp | Tín hiệu ranking hoặc điều kiện thay thế |
| `filter` | Có | Không | Giới hạn tập document, không tính relevance |
| `must_not` | Không được khớp | Không | Loại document |

### 5.1 should chỉ để tăng điểm

Khi một `bool` query đã có `must` hoặc `filter`, các clause `should` thường là tùy chọn theo mặc định. Chúng làm tăng score cho document khớp nhưng không loại document không khớp should.

Đây là cấu trúc phổ biến để “ưu tiên”:

```json
{
  "bool": {
    "must": [
      { "match": { "content": "spring data" } }
    ],
    "should": [
      { "match": { "title": { "query": "spring data", "boost": 3.0 } } }
    ]
  }
}
```

Document chỉ match content vẫn được trả về. Document match thêm title được ưu tiên nhờ score cao hơn.

### 5.2 minimum_should_match biến should thành điều kiện

Nếu cần ít nhất một số clause `should` phải khớp, dùng `minimum_should_match`:

```json
{
  "bool": {
    "must": [
      { "match": { "content": "spring data" } }
    ],
    "should": [
      { "term": { "status": "FEATURED" } },
      { "match": { "title": "elasticsearch" } }
    ],
    "minimum_should_match": 1
  }
}
```

Với cấu hình này, document phải match content và ít nhất một trong hai should clause. `should` không còn chỉ là tín hiệu tăng điểm tùy chọn; nó tham gia điều kiện chọn document.

Nếu mục tiêu chỉ là boost, không đặt `minimum_should_match` theo cách vô tình loại document phù hợp với query chính.

### 5.3 Đừng đặt boost vào filter để mong tăng score

Filter được tối ưu cho điều kiện không scoring. Ví dụ:

```json
"filter": [
  { "term": { "status": { "value": "FEATURED", "boost": 5 } } }
]
```

không phải cách đúng để ưu tiên FEATURED theo relevance, vì filter không đóng góp score. Nếu cần ưu tiên, đưa điều kiện đó vào một clause scoring như `should` hoặc dùng scoring function phù hợp. Vẫn có thể giữ điều kiện bắt buộc trong filter nếu cần giới hạn dữ liệu.

## 6. Kết hợp field boost và clause boost

Một query thực tế có thể dùng cả hai cấp:

1. Dùng `multi_match` để tìm nội dung trên nhiều field với trọng số khác nhau.
2. Dùng `should` để thêm tín hiệu độc lập như thương hiệu ưu tiên hoặc phrase match.
3. Dùng `filter` cho điều kiện bắt buộc nhưng không liên quan đến relevance.

Ví dụ:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless keyboard",
            "type": "best_fields",
            "fields": [
              "name^4",
              "shortDescription^2",
              "description"
            ]
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": {
              "value": "Northwind",
              "boost": 2.0
            }
          }
        },
        {
          "match_phrase": {
            "name": {
              "query": "wireless keyboard",
              "boost": 3.0
            }
          }
        },
        {
          "term": {
            "featured": {
              "value": true,
              "boost": 1.5
            }
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "computer-accessories" } }
      ]
    }
  }
}
```

Trong ví dụ:

- `name^4` được ưu tiên hơn `shortDescription^2` và `description`.
- `brand = Northwind` làm tăng score nếu document thuộc thương hiệu đó.
- Phrase match trong `name` là một tín hiệu mạnh hơn khi cụm từ xuất hiện đúng thứ tự.
- `featured = true` tạo thêm một tín hiệu ưu tiên.
- `active` và `category` là điều kiện lọc bắt buộc, không ảnh hưởng score.

Document không thể vượt qua filter active/category chỉ nhờ boost thương hiệu hoặc featured. Điều này giúp tách rõ eligibility khỏi ranking.

## 7. Disjunction max và tie_breaker

Khi tìm trên nhiều field, cách kết hợp score ảnh hưởng tới tác dụng của field boost. `dis_max` chọn score tốt nhất từ các query con và có thể cộng thêm một phần score của các query còn lại thông qua `tie_breaker`.

Ví dụ:

```json
GET /articles/_search
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match": {
            "title": {
              "query": "spring data",
              "boost": 4.0
            }
          }
        },
        {
          "match": {
            "summary": {
              "query": "spring data",
              "boost": 2.0
            }
          }
        },
        {
          "match": {
            "content": "spring data"
          }
        }
      ],
      "tie_breaker": 0.2
    }
  }
}
```

Với `tie_breaker` bằng 0, score tốt nhất là thành phần chính. Giá trị lớn hơn 0 cho phép các query con khác đóng góp thêm. Giá trị cao hơn làm nhiều field cùng khớp có ảnh hưởng lớn hơn.

`multi_match` kiểu `best_fields` sử dụng cơ chế gần với dis_max. Nếu muốn kiểm soát từng field như một query riêng, có thể dùng `dis_max` trực tiếp. Không nên tăng `tie_breaker` mà không hiểu việc cộng điểm từ nhiều field sẽ làm thay đổi ranking như thế nào.

## 8. Boost giảm hạng và các tín hiệu scoring nâng cao

Boost thường được dùng để tăng ảnh hưởng, nhưng đôi khi nghiệp vụ cần giảm mức ưu tiên của một nhóm kết quả mà vẫn giữ chúng trong tập kết quả.

### 8.1 Boosting query

`boosting` query kết hợp một positive query với negative query. Document khớp positive vẫn có thể xuất hiện; nếu đồng thời khớp negative, score được nhân với `negative_boost`.

```json
GET /articles/_search
{
  "query": {
    "boosting": {
      "positive": {
        "match": {
          "content": "spring data"
        }
      },
      "negative": {
        "term": {
          "status": "ARCHIVED"
        }
      },
      "negative_boost": 0.2
    }
  }
}
```

Document ARCHIVED vẫn có thể được trả về nếu match positive, nhưng score bị giảm. Nếu nghiệp vụ muốn loại hẳn ARCHIVED, dùng `must_not` hoặc filter phù hợp thay vì demote.

### 8.2 Function score

Nếu ranking phụ thuộc vào số liệu như popularity, freshness hoặc rating, chỉ tăng boost cố định cho một clause có thể không đủ. `function_score` cho phép kết hợp query score với function tính từ field hoặc công thức.

Ví dụ khái quát:

```json
GET /products/_search
{
  "query": {
    "function_score": {
      "query": {
        "match": {
          "name": "wireless keyboard"
        }
      },
      "field_value_factor": {
        "field": "popularity",
        "modifier": "log1p",
        "factor": 1.2,
        "missing": 0
      },
      "boost_mode": "multiply"
    }
  }
}
```

Ở đây score relevance được điều chỉnh bằng tín hiệu popularity. Function score mạnh hơn boost tĩnh và cần kiểm soát scale, missing values, modifier và cách kết hợp (`boost_mode`). Dùng khi có yêu cầu ranking dựa trên dữ liệu định lượng; đừng dùng nó chỉ để thay một boost field đơn giản.

### 8.3 Rescore

Với ranking phức tạp, có thể dùng rescore để áp dụng một query đắt hơn lên một tập kết quả đầu đã được chọn. Ví dụ query đầu dùng match nhanh, rescore dùng phrase match để tinh chỉnh top documents.

Rescore có thể giảm chi phí so với áp dụng query phức tạp lên toàn bộ tập document, nhưng chỉ tác động trong cửa sổ rescore được cấu hình. Nó cần được đánh giá với pagination, shard và thứ tự kết quả.

## 9. Boost trong Spring Data Elasticsearch bằng NativeQuery

Với Spring Data Elasticsearch sử dụng Elasticsearch Java API Client, `NativeQuery` cho phép xây dựng Query DSL bằng builder Java. Field boost được truyền trong danh sách field của `multi_match`; clause boost được đặt trên query con.

### 9.1 Field boost trong multi_match

```java
import java.util.List;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.multiMatch(m -> m
        .query("wireless keyboard")
        .fields(List.of(
            "name^4",
            "shortDescription^2",
            "description"
        ))
    ))
    .build();
```

`fields` chứa cú pháp field boost giống Query DSL JSON. `name` có trọng số 4, `shortDescription` có trọng số 2 và `description` dùng mặc định. Query được thực thi qua `ElasticsearchOperations`:

```java
SearchHits<Product> hits = operations.search(query, Product.class);
```

### 9.2 Boost từng clause trong bool query

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("description")
            .query("wireless keyboard")
        ))
        .should(s -> s.match(mm -> mm
            .field("name")
            .query("wireless keyboard")
            .boost(3.0f)
        ))
        .should(s -> s.match(mm -> mm
            .field("brandDescription")
            .query("Northwind")
            .boost(1.5f)
        ))
        .filter(f -> f.term(t -> t
            .field("active")
            .value(v -> v.booleanValue(true))
        ))
    ))
    .build();
```

Trong ví dụ, clause `must` xác định nội dung cần match. Hai clause `should` làm tăng score khi tên hoặc mô tả thương hiệu khớp. Filter `active` chỉ giới hạn document. Vì `bool` đã có `must`, `should` là tùy chọn theo mặc định và không loại document nếu không khớp hai tín hiệu ưu tiên.

Các kiểu builder và kiểu số của `boost` phụ thuộc phiên bản Elasticsearch Java Client do Spring Data quản lý. Nếu API trong dự án yêu cầu kiểu `Float` hoặc overload khác, hãy dùng đúng Javadoc của dependency; cấu trúc Query DSL và semantics boost vẫn như ví dụ JSON.

### 9.3 Kết hợp field boost, clause boost và filter

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.multiMatch(mm -> mm
            .query("wireless keyboard")
            .fields(List.of(
                "name^4",
                "shortDescription^2",
                "description"
            ))
        ))
        .should(s -> s.term(t -> t
            .field("featured")
            .value(v -> v.booleanValue(true))
            .boost(1.5f)
        ))
        .should(s -> s.matchPhrase(mp -> mp
            .field("name")
            .query("wireless keyboard")
            .boost(3.0f)
        ))
        .filter(f -> f.term(t -> t
            .field("active")
            .value(v -> v.booleanValue(true))
        ))
    ))
    .build();
```

Đây là mẫu cho thấy hai cấp boost cùng tồn tại trong một query. Nếu builder của phiên bản client không có overload tương ứng, có thể tạo query bằng JSON/native request hoặc dùng API query builder đúng phiên bản. Không cần chuyển toàn bộ logic sang chuỗi JSON nếu Java Client đã cung cấp builder type-safe.

## 10. Boost với repository `@Query`

Với truy vấn cố định, có thể khai báo Query DSL trong `@Query`:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String> {

    @Query("{\"multi_match\":{\"query\":\"?0\",\"fields\":[\"title^4\",\"summary^2\",\"content\"]}}")
    List<Article> searchBoosted(String text);
}
```

Query annotation thuận tiện cho truy vấn ổn định và đơn giản. Nếu cần boost động theo loại người dùng, danh sách field thay đổi hoặc nhiều clause có điều kiện, `NativeQuery` thường dễ tổ chức và kiểm thử hơn.

Không nối trực tiếp chuỗi người dùng vào JSON query. Dùng placeholder binding hoặc builder có tham số để tránh lỗi escaping và giữ rõ ranh giới giữa dữ liệu đầu vào với cấu trúc query.

## 11. Boost và BM25: hiểu score đúng cách

Elasticsearch mặc định thường dùng BM25 cho scoring full-text. BM25 xét nhiều yếu tố như:

- Mức độ xuất hiện của term trong document.
- Mức độ phổ biến của term trên toàn index.
- Độ dài field/document so với độ dài trung bình.
- Các tham số similarity và cấu hình mapping/index.

Boost điều chỉnh score do query tạo ra, nhưng không xóa bỏ các yếu tố này. Một field có boost 4 không có nghĩa mọi document khớp field đó sẽ luôn đứng trên document có boost 1. Một document có nhiều term phù hợp, tần suất phù hợp hoặc nhiều clause khác cùng khớp vẫn có thể đạt score cao hơn.

### 11.1 Không diễn giải boost như phần trăm

Boost `2.0` không có nghĩa document liên quan gấp đôi hoặc xác suất đúng tăng 100%. Nó là hệ số tác động vào scoring của query. Score cuối cùng còn phụ thuộc cấu trúc query và các tín hiệu khác.

### 11.2 Không đặt boost quá lớn tùy tiện

Nếu `title` được đặt boost `1000`, tín hiệu title có thể áp đảo hầu hết các tín hiệu còn lại. Điều đó có thể làm kết quả chứa title khớp yếu đứng trên tài liệu có nội dung phù hợp hơn nhiều.

Bắt đầu bằng các hệ số vừa phải, ví dụ `title^3`, `summary^2`, `content` mặc định, sau đó đánh giá trên bộ truy vấn mẫu. Đây chỉ là điểm khởi đầu để thử nghiệm, không phải công thức chung.

### 11.3 Score không ổn định giữa các index hoặc query khác nhau

Score chịu ảnh hưởng của thống kê term và cấu trúc index. Khi shard/index hoặc tập dữ liệu thay đổi, score có thể thay đổi. Không nên lưu score như một chỉ số nghiệp vụ bền vững hoặc so sánh trực tiếp score của hai query có cấu trúc khác nhau.

## 12. Khi nào dùng boost, khi nào dùng sort hoặc function_score?

Ba cách này giải quyết các yêu cầu khác nhau:

| Cơ chế | Mục tiêu | Ví dụ |
|---|---|---|
| Boost | Điều chỉnh relevance của field/query clause | Ưu tiên title hơn body |
| Sort | Sắp xếp theo giá trị có thứ tự xác định | Giá tăng dần, thời gian mới nhất |
| Function score | Kết hợp relevance với tín hiệu tính toán | Popularity, freshness, rating |

Nếu yêu cầu là “document có từ khóa trong tiêu đề nên được ưu tiên”, dùng field/clause boost. Nếu yêu cầu là “giá thấp nhất phải đứng đầu bất kể nội dung”, dùng sort. Nếu yêu cầu là “kết hợp relevance với popularity theo công thức”, cân nhắc function_score hoặc một ranking pipeline phù hợp.

Không nên dùng boost để mô phỏng một thứ tự tuyệt đối khi sort có thể diễn đạt trực tiếp hơn.

## 13. Kiểm tra score bằng explain và profile

Khi kết quả xếp hạng chưa hợp lý, hãy kiểm tra score thay vì chỉ tăng boost đến khi kết quả “trông có vẻ đúng”.

### 13.1 Explain một document

`_explain` cho biết vì sao một document match và các thành phần đóng góp vào score:

```http
GET /articles/_explain/article-1001
{
  "query": {
    "multi_match": {
      "query": "spring data",
      "fields": ["title^4", "summary^2", "content"]
    }
  }
}
```

Response giải thích query con nào match, boost nào được áp dụng và các yếu tố scoring liên quan. Dùng nó để xác nhận field boost đang có hiệu lực và document nhận score từ những clause nào.

### 13.2 Profile search request

Profile API cung cấp thông tin chi tiết về thời gian thực thi các query component:

```json
GET /articles/_search
{
  "profile": true,
  "query": {
    "multi_match": {
      "query": "spring data",
      "fields": ["title^4", "summary^2", "content"]
    }
  }
}
```

Profile hữu ích để điều tra chi phí query, nhưng tạo overhead và response lớn. Chỉ bật trong môi trường điều tra hoặc trên request kiểm soát; không bật mặc định cho mọi search production.

### 13.3 So sánh tập truy vấn đại diện

Để điều chỉnh boost, tạo một tập truy vấn đại diện với thứ tự kết quả mong muốn hoặc judgment relevance. So sánh:

1. Query baseline không boost.
2. Query có field boost.
3. Query có clause boost.
4. Query kết hợp cả hai.

Đánh giá các trường hợp title khớp, body khớp, nhiều field cùng khớp, từ khóa phổ biến và truy vấn dài. Có thể dùng các metric như Precision@K, Recall@K, MRR hoặc NDCG nếu có relevance labels.

Không chỉ kiểm tra một truy vấn thuận lợi. Boost tốt cần cải thiện chất lượng trên nhiều truy vấn mà không làm giảm nghiêm trọng các nhóm truy vấn khác.

## 14. Các lỗi thường gặp

### 14.1 Đặt boost trong filter và mong score tăng

Filter không tính relevance score. Đưa tín hiệu cần ưu tiên vào query scoring như `should`, hoặc dùng function_score nếu cần công thức.

### 14.2 Dùng should nhưng vô tình biến nó thành điều kiện bắt buộc

Khi có `must` hoặc `filter`, should thường là tùy chọn. Nếu đặt `minimum_should_match`, một số document không match should sẽ bị loại. Hãy xác định should chỉ để tăng điểm hay thật sự là điều kiện lựa chọn.

### 14.3 Dùng field boost mà không kiểm tra multi_match type

`best_fields`, `most_fields` và `cross_fields` kết hợp score khác nhau. Chọn type theo semantics rồi mới điều chỉnh field boost.

### 14.4 Boost quá lớn làm mất cân bằng ranking

Hệ số lớn có thể áp đảo BM25 và các tín hiệu khác. Bắt đầu với hệ số vừa phải, đo relevance và điều chỉnh từng bước.

### 14.5 Nhầm boost với sort

Boost chỉ ảnh hưởng score. Nếu cần thứ tự tuyệt đối theo giá, ngày hoặc số lượng, dùng sort.

### 14.6 Boost field không có khả năng scoring

Các field `keyword` có thể dùng trong query scoring như term query, nhưng nếu đặt điều kiện trong filter thì boost không có tác dụng. Cần phân biệt kiểu field với vị trí query clause.

### 14.7 Không hiểu tie_breaker

Trong dis_max/best_fields, tie_breaker cho phép các field khớp khác đóng góp thêm score. Giá trị quá lớn có thể làm nhiều field lặp nội dung cộng điểm mạnh hơn dự kiến.

### 14.8 So sánh score như xác suất

Score không phải xác suất và không nên được hiển thị như phần trăm độ tin cậy nếu chưa có mô hình hiệu chỉnh riêng.

## 15. Quy trình thiết kế boost

Khi xây dựng ranking cho một search endpoint, có thể đi theo trình tự:

1. Xác định điều kiện bắt buộc: tenant, trạng thái, quyền truy cập, loại dữ liệu. Đặt chúng trong `filter` hoặc `must` theo semantics.
2. Xác định nội dung chính cần tìm kiếm. Chọn `match`, `multi_match` hoặc query phù hợp.
3. Xác định field nào quan trọng hơn và gắn field boost trong `multi_match`.
4. Xác định tín hiệu độc lập cần ưu tiên, như phrase match, thương hiệu hoặc trạng thái featured. Đưa chúng vào `should` với clause boost.
5. Kiểm tra `minimum_should_match` để bảo đảm các clause ưu tiên có đúng vai trò tùy chọn hay bắt buộc.
6. Chọn `multi_match` type và `tie_breaker` theo cách kết hợp score mong muốn.
7. Nếu ranking phụ thuộc số liệu, đánh giá function_score; nếu cần thứ tự tuyệt đối, dùng sort.
8. Kiểm tra `_explain`, profile và tập truy vấn đánh giá.
9. Điều chỉnh boost từng bước và theo dõi chất lượng sau triển khai.

## 16. Tổng kết

Boost giúp điều chỉnh relevance score ở hai cấp. Field boost, thường dùng trong `multi_match` hoặc `query_string` với cú pháp `field^n`, ưu tiên một field so với field khác. Clause boost được đặt trên từng query con để điều chỉnh mức đóng góp của các tín hiệu khác nhau trong `bool`, `dis_max` hoặc query tổng hợp.

Khi dùng bool query, `must` vừa bắt buộc vừa tính score; `should` có thể là tín hiệu ưu tiên tùy chọn hoặc trở thành điều kiện khi dùng `minimum_should_match`; `filter` và `must_not` không đóng góp relevance score. Hiểu đúng các vai trò này giúp tránh đặt boost sai chỗ hoặc vô tình loại document.

Trong Spring Data Elasticsearch, `NativeQuery` cho phép cấu hình field boost trong `multi_match` và clause boost trong Java Client query builder. Hãy chọn semantics multi_match phù hợp, kiểm tra tie_breaker, dùng explain để hiểu score và đánh giá trên tập truy vấn đại diện. Dùng boost cho relevance, sort cho thứ tự xác định và function_score khi cần kết hợp thêm tín hiệu định lượng.

## Tài liệu tham khảo

- [Elasticsearch — Multi-match query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-multi-match-query.html)
- [Elasticsearch — Boosting query clauses](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-boosting-query.html)
- [Elasticsearch — Bool query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html)
- [Elasticsearch — Disjunction max query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-dis-max-query.html)
- [Elasticsearch — Function score query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-function-score-query.html)
- [Spring Data Elasticsearch Reference — Search Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
