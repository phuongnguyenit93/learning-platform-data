# Sắp xếp theo _score và điều kiện giữ điểm liên quan

Elasticsearch không chỉ tìm document thỏa điều kiện mà còn tính điểm liên quan (relevance score) để xếp hạng kết quả. Với tìm kiếm toàn văn, điểm này thường được tính bằng BM25 và phản ánh mức độ khớp giữa nội dung document với truy vấn.

Khi Search API không khai báo sort, Elasticsearch mặc định sắp xếp theo _score giảm dần: document có điểm cao hơn đứng trước. Nhưng khi thêm sort theo một field như price, createdAt hoặc name, thứ tự đó thay đổi. Nếu muốn giữ relevance là yếu tố ưu tiên, cần đưa _score vào danh sách sort ở đúng vị trí và tổ chức query sao cho các điều kiện lọc không vô tình loại bỏ điểm liên quan.

Bài này giải thích cách sắp xếp theo _score, kết hợp điểm với điều kiện nghiệp vụ, phân biệt query context và filter context, dùng track_scores, xử lý tie-breaker ổn định và phân trang. Các ví dụ Java sử dụng NativeQuery cùng Elasticsearch Java API Client; chi tiết builder cần đối chiếu với phiên bản Spring Data Elasticsearch trong dự án.

## 1. _score là gì?

_score là điểm số Elasticsearch gán cho một document phù hợp với query. Điểm càng cao thường biểu thị document càng liên quan đến truy vấn trong cùng một lần tìm kiếm.

Ví dụ tìm sản phẩm:

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

Một số document có thể được xếp hạng như sau:

| Document | Tên | _score minh họa |
|---|---|---:|
| P-1001 | Wireless Mouse | 4.8 |
| P-1002 | Wireless Gaming Mouse | 4.1 |
| P-1003 | Mouse for Wireless Office Setup | 2.7 |

Các con số trên chỉ minh họa. Score thực tế phụ thuộc analyzer, term statistics, độ dài field, query boost, cấu trúc query và dữ liệu trong index.

Với full-text query, Elasticsearch thường sử dụng BM25. Một số yếu tố ảnh hưởng tới score:

- Term nào trong truy vấn xuất hiện trong document.
- Độ hiếm của term trong tập document.
- Tần suất term trong field.
- Độ dài field và chuẩn hóa theo độ dài.
- Analyzer tạo ra token nào.
- Boost và các query clause tham gia tính điểm.

Không nên coi _score là xác suất document đúng. Score chủ yếu dùng để xếp hạng kết quả của cùng một truy vấn.

## 2. Thứ tự mặc định khi không khai báo sort

Nếu Search API không có sort, Elasticsearch sắp xếp theo _score giảm dần. Ví dụ:

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

Tương đương về ý định với việc khai báo:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    {
      "_score": {
        "order": "desc"
      }
    }
  ]
}
~~~

Có thể khai báo rõ _score desc để người đọc thấy thứ tự mong muốn. Khi không có sort tường minh, không cần thêm cấu hình này chỉ để dùng hành vi mặc định.

### 2.1. Score bằng nhau

Nhiều document có thể có cùng _score. Nếu không có tiêu chí phụ, thứ tự giữa các document đồng điểm không nên được xem là ổn định. Thứ tự có thể thay đổi sau refresh, merge segment, thay đổi shard hoặc lần chạy truy vấn khác.

Nếu ứng dụng phân trang hoặc cần thứ tự lặp lại ổn định, nên thêm một field phụ có giá trị duy nhất và có thể sort, ví dụ id.keyword:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": { "order": "desc" } },
    { "id.keyword": { "order": "asc" } }
  ]
}
~~~

Ở đây relevance vẫn là ưu tiên đầu tiên. id.keyword chỉ quyết định thứ tự giữa các document có cùng score.

Elasticsearch không hỗ trợ sort trực tiếp trên metadata field _id theo cách thông thường trong nhiều cấu hình; hãy lưu một bản sao ID vào field keyword có doc values nếu cần dùng làm tie-breaker. Kiểm tra mapping thực tế của field phụ.

## 3. Vì sao sort theo field có thể làm mất ưu tiên relevance?

Giả sử ứng dụng muốn tìm sản phẩm liên quan tới từ khóa và ưu tiên giá thấp. Query:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    {
      "priceInCents": {
        "order": "asc"
      }
    }
  ]
}
~~~

Kết quả được sắp xếp theo giá tăng dần. Sản phẩm rẻ nhất đứng trước, kể cả khi document đó có _score thấp hơn.

Đây không phải lỗi của Elasticsearch. Sort array xác định thứ tự ưu tiên của các khóa sort. Khi chỉ định priceInCents đầu tiên, giá là tiêu chí xếp hạng chính.

Nếu muốn relevance đứng trước và giá chỉ phân xử giữa các kết quả có score bằng nhau, khai báo:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": { "order": "desc" } },
    { "priceInCents": { "order": "asc" } },
    { "id.keyword": { "order": "asc" } }
  ]
}
~~~

Thứ tự có ý nghĩa:

1. _score giảm dần.
2. Nếu score bằng nhau, giá tăng dần.
3. Nếu score và giá đều bằng nhau, ID tăng dần.

Đừng đặt price trước _score nếu yêu cầu nghiệp vụ là ưu tiên relevance.

## 4. Query context và filter context

Đây là điểm quan trọng nhất khi muốn giữ điểm liên quan.

Elasticsearch có hai ngữ cảnh cơ bản:

- **Query context** đánh giá document khớp đến mức nào và tính _score.
- **Filter context** chỉ kiểm tra document có thỏa điều kiện hay không. Điều kiện filter không đóng góp vào _score và có thể được cache khi phù hợp.

Trong bool query:

| Clause | Vai trò | Đóng góp vào _score? |
|---|---|---|
| must | Điều kiện bắt buộc | Có |
| should | Điều kiện tùy chọn hoặc bắt buộc theo minimum_should_match | Có |
| filter | Điều kiện bắt buộc dạng yes/no | Không |
| must_not | Loại document khỏi kết quả | Không |

Ví dụ tìm sản phẩm theo tên, đồng thời chỉ lấy sản phẩm đang hoạt động thuộc danh mục accessories:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
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

match nằm trong must nên tính relevance. active và category nằm trong filter nên chỉ giới hạn tập kết quả, không làm thay đổi điểm liên quan.

Đây là cấu trúc thường phù hợp cho tìm kiếm sản phẩm: full-text quyết định mức liên quan, còn trạng thái, tenant, danh mục và khoảng giá là các điều kiện lọc.

### 4.1. Không đặt toàn bộ truy vấn full-text vào filter nếu cần _score

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ]
    }
  }
}
~~~

Document vẫn được lọc theo match, nhưng clause chạy trong filter context nên không tạo điểm relevance thông thường. Nếu sau đó sort theo _score, các kết quả không có điểm phân biệt hữu ích theo query này.

Nếu cần xếp hạng theo độ khớp văn bản, đặt match trong must hoặc should. Dùng filter cho các điều kiện chỉ nhằm loại document không phù hợp.

### 4.2. Điều kiện filter không làm mất score từ must

Có thể kết hợp nhiều filter với một must:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "ergonomic wireless mouse"
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
          "range": {
            "priceInCents": {
              "gte": 100000,
              "lte": 800000
            }
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "visibility": "HIDDEN"
          }
        }
      ]
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Score đến từ match trong must. Các filter và must_not giới hạn kết quả nhưng không cộng hoặc trừ điểm relevance.

## 5. should và minimum_should_match

should clause có thể vừa giúp tìm document vừa đóng góp score. Tuy nhiên, có một quy tắc mặc định dễ gây nhầm:

- Nếu bool chỉ có should và không có must/filter, mặc định cần ít nhất một should khớp.
- Nếu bool đã có must hoặc filter, should thường là tùy chọn theo mặc định (minimum_should_match mặc định là 0).

Ví dụ muốn tên sản phẩm là điều kiện bắt buộc, còn brand và category chỉ giúp tăng điểm:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": {
              "value": "Northwind",
              "boost": 3
            }
          }
        },
        {
          "term": {
            "category": {
              "value": "accessories",
              "boost": 1.5
            }
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

Document phải khớp name và active=true. Nếu thêm brand hoặc category phù hợp, score có thể tăng. Nếu không khớp các should clause, document vẫn được trả về vì must đã thỏa và should đang tùy chọn.

### 5.1. Khi nào cần minimum_should_match?

Nếu nghiệp vụ yêu cầu ít nhất một should clause phải khớp, hãy khai báo rõ:

~~~json
{
  "bool": {
    "must": [
      { "match": { "name": "wireless mouse" } }
    ],
    "should": [
      { "term": { "brand": "Northwind" } },
      { "term": { "category": "accessories" } }
    ],
    "minimum_should_match": 1
  }
}
~~~

Khi đó document cần khớp ít nhất một trong hai tín hiệu bổ sung. Nếu mục tiêu chỉ là tăng điểm khi có thêm tín hiệu mà không loại document, không đặt minimum_should_match lớn hơn 0.

Phân biệt rõ hai mục tiêu:

- should để boost: clause có thể không khớp mà document vẫn được giữ.
- should để ràng buộc: cần minimum_should_match phù hợp.

## 6. Sắp xếp theo _score cùng tiêu chí phụ

Có ba kiểu sắp xếp thường gặp:

| Yêu cầu | Sort |
|---|---|
| Chỉ ưu tiên relevance | _score desc |
| Relevance trước, giá phân xử khi đồng điểm | _score desc, price asc |
| Giá là ưu tiên chính, relevance chỉ phân xử khi cùng giá | price asc, _score desc |
| Relevance trước, ngày mới hơn phân xử khi đồng điểm | _score desc, createdAt desc |
| Kết quả ổn định giữa các trang | _score desc và unique keyword tie-breaker |

Ví dụ relevance trước, sau đó ngày cập nhật mới nhất:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "updatedAt": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Nếu updatedAt đứng trước _score, bài mới nhất sẽ đứng đầu bất kể mức độ liên quan. Cần xác định tiêu chí nghiệp vụ nào là chính trước khi xếp thứ tự sort.

### 6.1. Tie-breaker cần ổn định và duy nhất

Nếu sort chỉ gồm _score, nhiều hit có thể đồng điểm. Nếu sort gồm _score và createdAt, hai hit vẫn có thể có cùng score và cùng thời điểm.

Thêm một field keyword duy nhất như id.keyword để thứ tự hoàn toàn xác định trong tập kết quả. Field này cần có doc values và mapping hỗ trợ sort.

Không nên dựa vào thứ tự tình cờ giữa các hit đồng điểm, đặc biệt khi dùng from/size hoặc search_after.

## 7. track_scores khi sort theo field

Khi sort theo một field thông thường như price hoặc date, Elasticsearch có thể không tính _score nếu không cần thiết cho thứ tự sort. Nếu vẫn muốn nhận score trong kết quả dù field sort là chính, Search API có tùy chọn track_scores: true.

Ví dụ sort theo giá nhưng vẫn yêu cầu theo dõi score:

~~~http
POST /products/_search
{
  "track_scores": true,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    {
      "priceInCents": {
        "order": "asc"
      }
    }
  ]
}
~~~

track_scores chỉ yêu cầu tính và trả score trong trường hợp sort theo field. Nó **không** biến _score thành tiêu chí sort và không thay đổi thứ tự ưu tiên của sort array.

Nếu muốn relevance quyết định thứ tự, hãy đưa _score vào sort:

~~~json
{
  "sort": [
    { "_score": "desc" },
    { "priceInCents": "asc" }
  ]
}
~~~

Nếu chỉ sort theo price và bật track_scores, kết quả vẫn được sắp theo price. Score chỉ là metadata có thể dùng để hiển thị hoặc phân tích.

## 8. Dùng NativeQuery để khai báo sort trong Spring Data Elasticsearch

Với Spring Data Elasticsearch 5.x và Elasticsearch Java API Client, có thể tạo sort options rồi truyền vào NativeQuery.

Ví dụ _score giảm dần, ID tăng dần:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

SortOptions scoreSort = SortOptions.of(s -> s
    .score(sc -> sc.order(SortOrder.Desc))
);

SortOptions idSort = SortOptions.of(s -> s
    .field(f -> f
        .field("id.keyword")
        .order(SortOrder.Asc)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(textQuery)
    .withSort(List.of(scoreSort, idSort))
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

Ví dụ dùng kiểu SortOptions của Elasticsearch Java API Client. Tên builder method của NativeQuery có thể khác theo minor version; kiểm tra Javadoc/IDE của dependency dự án. Nếu builder nhận varargs thay vì List, điều chỉnh đúng overload có trong phiên bản đang dùng.

Có thể thêm sort field thứ hai hoặc thứ ba:

~~~java
SortOptions priceSort = SortOptions.of(s -> s
    .field(f -> f
        .field("priceInCents")
        .order(SortOrder.Asc)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(textQuery)
    .withSort(List.of(scoreSort, priceSort, idSort))
    .build();
~~~

Trong ví dụ này _score vẫn là tiêu chí đầu tiên. Giá chỉ phân xử giữa các document có cùng score; ID tạo thứ tự ổn định cuối cùng.

### 8.1. Dùng Pageable và Sort

Với query/repository path hỗ trợ Pageable, có thể khai báo sort qua Spring Data Sort:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("_score"),
        Sort.Order.asc("id.keyword")
    )
);
~~~

Sau đó truyền pageable vào query hoặc repository method tương ứng. Cách sử dụng cụ thể phụ thuộc API query và repository của phiên bản Spring Data Elasticsearch đang dùng.

Với sort nhiều loại hoặc các option đặc thù của Elasticsearch, NativeQuery cùng SortOptions thường biểu đạt rõ hơn.

## 9. Field sort có thể làm score không còn là yếu tố xếp hạng

Ví dụ muốn giá thấp trước, nhưng vẫn muốn giữ score để hiển thị:

~~~http
POST /products/_search
{
  "track_scores": true,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "priceInCents": "asc" },
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Thứ tự lúc này là:

1. Giá thấp hơn đứng trước.
2. Nếu giá bằng nhau, score cao hơn đứng trước.
3. Nếu cả giá và score bằng nhau, ID quyết định.

Đây là cách phù hợp nếu giá là tiêu chí chính. Nếu yêu cầu là relevance trước, phải đảo hai sort đầu tiên.

Đặt track_scores=true giúp có score để xem/hiển thị khi sort theo field. Nhưng nếu _score đã là sort key, score được tính để sắp xếp; track_scores không phải thứ làm cho _score trở thành ưu tiên.

## 10. Giữ điểm liên quan khi kết hợp nhiều field

Nếu query tìm kiếm nhiều field, cần chọn cách kết hợp score phù hợp trước khi sort.

Ví dụ bool query:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless mouse",
            "type": "best_fields",
            "fields": [
              "title^4",
              "subtitle^2",
              "description"
            ],
            "tie_breaker": 0.1
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "accessories" } }
      ]
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

multi_match best_fields kết hợp relevance giữa các field. Bool filter áp dụng điều kiện nghiệp vụ mà không cộng score. Sort _score desc giữ document liên quan nhất ở đầu.

Nếu đưa multi_match vào filter, score của nó không được dùng để xếp hạng thông thường. Đặt nó trong must hoặc should nếu cần relevance.

## 11. Boost và function_score có ảnh hưởng thế nào?

Boost thay đổi score của query hoặc field. Ví dụ title^4 làm kết quả khớp title được ưu tiên hơn field không boost. Khi sort theo _score desc, boost ảnh hưởng trực tiếp thứ tự kết quả.

function_score cho phép thay đổi score dựa trên function như field value factor, decay hoặc script. Ví dụ có thể kết hợp relevance với độ mới của document:

~~~http
POST /articles/_search
{
  "query": {
    "function_score": {
      "query": {
        "match": {
          "content": "spring data elasticsearch"
        }
      },
      "functions": [
        {
          "gauss": {
            "publishedAt": {
              "origin": "now",
              "scale": "30d",
              "decay": 0.5
            }
          }
        }
      ],
      "boost_mode": "multiply"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Ở đây function_score điều chỉnh score của query dựa trên độ gần thời gian xuất bản. boost_mode xác định cách kết hợp score query và score function.

Các lựa chọn function_score có nhiều tham số như score_mode, boost_mode, max_boost và min_score. Hãy hiểu rõ semantics trước khi dùng. Một hàm score tốt có thể thay đổi đáng kể thứ hạng; cần kiểm thử bằng truy vấn thực tế và Explain API.

Nếu sort theo publishedAt trước _score, kết quả vẫn ưu tiên thời gian thay vì score đã điều chỉnh. Function_score chỉ tác động đến thứ tự khi score được dùng làm tiêu chí sort.

## 12. Filter, constant_score và điểm liên quan

constant_score query đặt một score cố định cho mọi document khớp filter:

~~~http
POST /products/_search
{
  "query": {
    "constant_score": {
      "filter": {
        "term": {
          "active": true
        }
      },
      "boost": 1.2
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

Mọi document thỏa filter nhận cùng điểm cố định (được điều chỉnh bởi boost). Điều này hữu ích khi muốn một điều kiện filter tạo score cố định, nhưng không thay thế relevance của match query.

Nếu query chỉ gồm filter hoặc constant_score với cùng boost, nhiều kết quả sẽ có score bằng nhau. Hãy thêm sort phụ ổn định nếu thứ tự giữa chúng quan trọng.

Trong một query tìm kiếm kết hợp, có thể dùng must cho match để giữ relevance và filter cho điều kiện yes/no. Không cần chuyển tất cả filter thành constant_score chỉ để giữ điểm.

## 13. Phân trang theo _score

Có thể dùng from/size để lấy trang:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Trang tiếp theo:

~~~http
POST /products/_search
{
  "from": 20,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Sort có tie-breaker duy nhất giúp thứ tự giữa các hit đồng điểm ổn định hơn. Tuy nhiên, nếu index thay đổi giữa các request, document mới hoặc cập nhật có thể làm thứ tự và ranh giới trang thay đổi.

Elasticsearch giới hạn tổng số hit có thể truy cập bằng from/size; mặc định phổ biến của index.max_result_window là 10.000. Phân trang sâu làm Elasticsearch phải giữ và xử lý nhiều kết quả hơn, vì vậy không nên tăng giới hạn một cách tùy tiện.

## 14. search_after và sort ổn định

Khi cần duyệt sâu, search_after cho phép dùng sort values của hit cuối trang trước làm điểm bắt đầu cho trang tiếp theo.

Ví dụ sort:

~~~http
POST /products/_search
{
  "size": 20,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Giả sử hit cuối cùng của trang đầu có sort values tương ứng:

~~~json
[3.72, "P-1020"]
~~~

Request trang kế tiếp dùng chính các giá trị sort đó:

~~~http
POST /products/_search
{
  "size": 20,
  "search_after": [3.72, "P-1020"],
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Các nguyên tắc:

- Giữ nguyên query và sort giữa các trang.
- Truyền đúng sort values của hit cuối trang trước.
- Có tie-breaker duy nhất để tránh mơ hồ khi score bằng nhau.
- Không tự tính lại sort value từ source.
- Với tập dữ liệu cần snapshot ổn định, dùng Point in Time (PIT) cùng search_after nếu phiên bản và API hỗ trợ.

PIT giữ một góc nhìn nhất quán của index trong khoảng thời gian truy vấn. Khi dùng PIT, tuân theo yêu cầu sort và tham số PIT của Elasticsearch version; Elasticsearch có thể thêm _shard_doc làm tie-breaker nội bộ trong một số cách dùng. Không tự thay đổi sort giữa các request.

### 14.1. Vì sao tie-breaker quan trọng với search_after?

Nếu sort chỉ theo _score, nhiều document có thể cùng score. Khi đó ranh giới trang không đủ xác định để phân trang ổn định. Thêm field duy nhất như id.keyword tạo thứ tự toàn phần cho tập hit.

Nếu dùng PIT, vẫn cần dùng sort values được trả về và giữ nguyên thứ tự sort. Không tự thay một giá trị ID hoặc score bằng giá trị đọc từ _source.

## 15. total hits không phải _score

Cần phân biệt hai thông tin:

- _score là điểm liên quan của từng document.
- hits.total là số document khớp query, có thể là tổng chính xác hoặc một cận dưới tùy cấu hình.

Ví dụ:

~~~http
POST /products/_search
{
  "track_total_hits": true,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

track_total_hits yêu cầu theo dõi tổng số hit chính xác. Nó không điều khiển score và không thay thế track_scores.

Phân biệt:

| Tùy chọn | Tác dụng |
|---|---|
| sort: _score desc | Xếp document theo relevance score giảm dần |
| track_scores: true | Theo dõi score khi sort theo field khác |
| track_total_hits: true | Yêu cầu tổng số hit chính xác |
| minimum_should_match | Xác định số should clause tối thiểu cần khớp |
| min_score | Loại document có score thấp hơn ngưỡng |

Không nhầm track_scores với track_total_hits. Một cái liên quan score của hit, cái còn lại liên quan tổng số hit.

## 16. min_score và điều kiện giữ document có score đủ cao

min_score cho phép loại document có _score thấp hơn một ngưỡng:

~~~http
POST /products/_search
{
  "min_score": 1.5,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

Document phải khớp query và có score ít nhất bằng ngưỡng. Điều này có thể hữu ích khi muốn loại các kết quả rất yếu.

Tuy nhiên, score phụ thuộc dữ liệu và cấu trúc query. Một ngưỡng phù hợp với query này chưa chắc phù hợp với query khác. min_score có thể yêu cầu đánh giá score của các document ứng viên và làm tăng chi phí. Hãy chọn ngưỡng qua dữ liệu đánh giá, không chọn một số tùy ý.

Nếu muốn ràng buộc theo nội dung hoặc trạng thái, ưu tiên query/filter phù hợp. min_score là công cụ lọc theo điểm, không thay thế điều kiện nghiệp vụ.

## 17. Kiểm tra thứ hạng bằng Explain API

Khi kết quả không đứng đúng vị trí mong muốn, dùng Explain để xem score đến từ đâu:

~~~http
GET /products/_explain/P-1001
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  }
}
~~~

Explain có thể giúp kiểm tra:

- Document có khớp query hay không.
- Match clause đóng góp score thế nào.
- Boost được áp dụng ra sao.
- Query nào không đóng góp điểm vì ở filter context.
- Function score điều chỉnh score như thế nào.

Search API có thể bật explain=true cho các hit trả về, nhưng response sẽ lớn hơn và tốn chi phí. Chỉ dùng khi debug một số truy vấn hoặc trong môi trường thử nghiệm.

Profile API giúp phân tích thời gian thực thi query trên shard; nó không thay thế Explain để hiểu ý nghĩa score. Cả hai có overhead, không nên bật đại trà trong production.

## 18. Kiểm thử sort và điều kiện giữ score

Nên tạo dữ liệu test có điểm liên quan và thuộc tính sort khác nhau để xác nhận thứ tự.

Ví dụ:

| ID | name | priceInCents | active |
|---|---|---:|---|
| P-1 | Wireless Mouse | 300000 | true |
| P-2 | Wireless Gaming Mouse | 250000 | true |
| P-3 | Mouse Pad | 100000 | true |
| P-4 | Wireless Mouse | 150000 | false |

Query mong muốn:

- Match tên liên quan tới wireless mouse.
- Chỉ lấy active=true.
- Sắp xếp theo _score giảm dần.
- Nếu score bằng nhau, giá tăng dần.
- Nếu cả score và giá bằng nhau, ID tăng dần.

REST DSL:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  },
  "sort": [
    { "_score": "desc" },
    { "priceInCents": "asc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Test cần xác nhận:

1. P-4 bị loại vì active=false.
2. Các document còn lại được sắp theo score trước.
3. Giá chỉ phân xử khi score bằng nhau.
4. ID tạo thứ tự ổn định khi các tiêu chí trước đều bằng nhau.
5. Nếu thay sort thành price trước _score, kết quả đổi theo đúng semantics giá là ưu tiên chính.

Không hard-code score BM25 cụ thể nếu không kiểm soát đầy đủ dataset, analyzer và version. Thay vào đó, kiểm tra thứ tự tương đối hoặc kiểm tra cấu trúc sort và tập kết quả.

### 18.1. Kiểm thử filter không làm mất relevance

So sánh hai query:

- match trong must + active trong filter.
- match trong filter.

Query đầu phải có score liên quan từ match. Query thứ hai chỉ lọc document, không dùng match để tính relevance. Có thể kiểm tra _score trong response hoặc dùng Explain để xác nhận.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Kết quả rẻ nhất đứng đầu dù relevance thấp | price được đặt trước _score | Đặt _score ở đầu sort nếu relevance là ưu tiên chính |
| _score bằng 0 hoặc không hữu ích | Full-text query nằm trong filter context | Đưa match vào must/should |
| Score không được trả khi sort theo field | Elasticsearch không track score theo mặc định trong trường hợp đó | Bật track_scores nếu cần đọc score |
| Bật track_scores nhưng thứ tự vẫn theo giá | track_scores không thay đổi sort precedence | Đưa _score vào sort nếu cần relevance ưu tiên |
| Kết quả đồng điểm đổi thứ tự | Không có tie-breaker ổn định | Thêm unique keyword field vào cuối sort |
| Trang bị trùng hoặc thiếu hit | Sort không ổn định hoặc index thay đổi giữa trang | Dùng sort duy nhất, search_after và PIT khi phù hợp |
| Search_after trả kết quả sai | Sort/query thay đổi hoặc search_after values không đúng | Dùng sort values từ hit cuối trang trước |
| should không bắt buộc như mong đợi | Có must/filter nên minimum_should_match mặc định bằng 0 | Đặt minimum_should_match tường minh |
| Filter làm thay đổi tập kết quả nhưng không thay score | Đây là semantics bình thường của filter context | Đặt query relevance trong must/should |
| min_score loại quá nhiều document | Ngưỡng không phù hợp score distribution | Đánh giá trên tập truy vấn thực tế |
| Score thay đổi sau khi đổi mapping hoặc dữ liệu | BM25 phụ thuộc term statistics/analyzer | Kiểm tra mapping, analyzer và Explain |

## 20. Quy trình thiết kế sort có giữ relevance

Khi xây dựng endpoint tìm kiếm:

1. Xác định relevance hay field nghiệp vụ là tiêu chí xếp hạng chính.
2. Đặt full-text query trong must hoặc should nếu cần _score.
3. Đưa điều kiện yes/no như tenant, active, category và quyền truy cập vào filter.
4. Nếu relevance là chính, sort theo _score desc đầu tiên.
5. Thêm field sort phụ chỉ khi cần phân xử giữa kết quả đồng điểm.
6. Thêm unique keyword tie-breaker để thứ tự ổn định.
7. Nếu sort theo field nhưng vẫn cần score trong response, bật track_scores.
8. Phân biệt track_scores với track_total_hits.
9. Dùng search_after và PIT cho phân trang sâu cần tính ổn định.
10. Dùng Explain và tập truy vấn đại diện để đánh giá ranking.

## 21. Bảng tra cứu nhanh

| Nhu cầu | Cách cấu hình |
|---|---|
| Relevance mặc định | Không khai báo sort; Elasticsearch dùng _score desc |
| Relevance là ưu tiên chính | sort _score desc ở đầu danh sách |
| Giá chỉ phân xử khi đồng score | _score desc, price asc |
| Giá là ưu tiên chính, score phân xử | price asc, _score desc |
| Lọc điều kiện mà giữ relevance | bool.must cho match, bool.filter cho điều kiện yes/no |
| Thêm tín hiệu boost tùy chọn | bool.should; hiểu rõ minimum_should_match |
| Giữ score khi sort field | track_scores: true |
| Theo dõi tổng số hit chính xác | track_total_hits: true |
| Loại kết quả score thấp | min_score sau khi đánh giá ngưỡng |
| Thứ tự ổn định | Thêm unique keyword tie-breaker |
| Phân trang sâu | search_after, cân nhắc PIT |
| Tìm nguyên nhân score | Explain API |
| Điều chỉnh score theo quy tắc | boost, function_score hoặc script_score khi cần |

Sắp xếp theo _score giúp giữ document liên quan nhất ở đầu kết quả. Để giữ điểm liên quan khi lọc, đặt full-text query trong must/should và đặt điều kiện yes/no trong filter. Khi kết hợp sort theo giá hoặc thời gian, thứ tự các khóa sort quyết định tiêu chí nào là chính; track_scores chỉ giữ score khi sort theo field, không tự biến score thành tiêu chí xếp hạng. Với phân trang ổn định, thêm unique tie-breaker và dùng search_after/PIT khi phù hợp.

