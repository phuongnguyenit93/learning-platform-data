# Phân biệt mệnh đề query với toàn bộ search request

Khi tìm kiếm trong Elasticsearch, cần phân biệt **mệnh đề query** với **toàn bộ search request**. Mệnh đề query mô tả điều kiện để xác định tài liệu nào phù hợp, chẳng hạn tìm tên có chứa từ khóa, lọc theo trạng thái hoặc giới hạn giá trong một khoảng. Search request bao quanh mệnh đề đó và bổ sung các tùy chọn điều khiển việc tìm kiếm như phân trang, sắp xếp, highlight, aggregation, timeout và số lượng kết quả.

Sự khác biệt này quan trọng khi dùng Spring Data Elasticsearch. **CriteriaQuery**, **StringQuery** và **NativeQuery** giúp xây dựng phần truy vấn theo những cách khác nhau; đối tượng **Query** của Spring Data còn có thể mang một số thiết lập tìm kiếm như pageable và sort. Khi Elasticsearch nhận request, các thông tin đó được chuyển thành một search request hoàn chỉnh. Không nên đưa toàn bộ JSON của search request vào nơi chỉ mong đợi một mệnh đề query.

Bài này dùng index **products** và các trường **name**, **category**, **status**, **price**. Ta sẽ đọc cấu trúc JSON từ trong ra ngoài, phân biệt phần query với các tùy chọn ngang hàng, rồi xem cách biểu diễn các phần đó trong Spring Data Elasticsearch.

## 1. Mệnh đề query là gì?

Mệnh đề query là một đối tượng Query DSL mô tả điều kiện khớp tài liệu. Một query clause có thể là **match**, **term**, **range**, **bool**, **nested**, **prefix** hoặc nhiều loại khác.

Ví dụ, mệnh đề sau tìm tài liệu có tên phù hợp với cụm từ **wireless keyboard**:

~~~json
{
  "match": {
    "name": "wireless keyboard"
  }
}
~~~

Đây là một query clause. Nó mô tả cách tìm tài liệu theo trường **name**, nhưng chưa chỉ định:

- Lấy bao nhiêu kết quả.
- Bắt đầu từ vị trí nào.
- Sắp xếp theo trường nào.
- Có trả highlight hay không.
- Có tính aggregation hay không.
- Có giới hạn thời gian thực thi hay không.

Có thể kết hợp nhiều clause bằng **bool query**:

~~~json
{
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
        "term": {
          "category": "accessories"
        }
      },
      {
        "term": {
          "status": "ACTIVE"
        }
      },
      {
        "range": {
          "price": {
            "gte": 20,
            "lte": 100
          }
        }
      }
    ]
  }
}
~~~

Mệnh đề bool này yêu cầu tên sản phẩm khớp truy vấn toàn văn, đồng thời sản phẩm thuộc danh mục accessories, đang ACTIVE và có giá từ 20 đến 100. Nó vẫn chỉ là phần điều kiện tìm kiếm.

## 2. Toàn bộ search request là gì?

Search request là request gửi đến Elasticsearch Search API. Phần body thường chứa thuộc tính **query** cùng những tùy chọn tìm kiếm khác ở cùng cấp.

Ví dụ request hoàn chỉnh:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
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
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 100
            }
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ],
  "_source": [
    "name",
    "category",
    "price"
  ],
  "highlight": {
    "fields": {
      "name": {}
    }
  },
  "track_total_hits": true,
  "timeout": "2s"
}
~~~

Trong request này:

- **query** chứa mệnh đề Query DSL quyết định tài liệu nào phù hợp.
- **from** và **size** xác định vị trí bắt đầu và số kết quả yêu cầu.
- **sort** quy định thứ tự kết quả.
- **_source** giới hạn các trường source được trả về.
- **highlight** yêu cầu Elasticsearch trả đoạn văn bản được đánh dấu.
- **track_total_hits** điều khiển việc tính tổng số hit chính xác.
- **timeout** đặt giới hạn thời gian cho hoạt động tìm kiếm.

Các thuộc tính trên là những phần ngang hàng trong search request body. Chúng không phải thành phần con của mệnh đề **bool** hay **match**.

Có thể hình dung cấu trúc như sau:

~~~text
Search request
|
+-- from / size
|
+-- query
|   |
|   +-- bool
|       |
|       +-- must
|       +-- filter
|       +-- should
|       +-- must_not
|
+-- sort
+-- _source
+-- highlight
+-- aggregations
+-- track_total_hits
+-- timeout
~~~

Search request là chiếc khung điều khiển toàn bộ lần tìm kiếm. Mệnh đề query là một thành phần nằm trong chiếc khung đó.

## 3. So sánh trực tiếp hai cấu trúc JSON

**Chỉ là query clause:**

~~~json
{
  "bool": {
    "filter": [
      {
        "term": {
          "category": "accessories"
        }
      }
    ]
  }
}
~~~

**Toàn bộ search request body:**

~~~json
{
  "from": 0,
  "size": 10,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": "asc"
    }
  ]
}
~~~

Điểm khác biệt nằm ở lớp bao ngoài:

- Query clause bắt đầu bằng loại query như **bool**, **match**, **term** hoặc **range**.
- Search request body có thể chứa **query** và nhiều thuộc tính tìm kiếm khác.
- Trong request body, query clause nằm bên trong giá trị của key **query**.

Nếu một API nhận query clause nhưng ta truyền nguyên search request body, cấu trúc sẽ bị lồng sai. Ngược lại, nếu gửi riêng query clause đến endpoint tìm kiếm mà request body cần thuộc tính **query**, Elasticsearch có thể báo lỗi hoặc hiểu nội dung theo cấu trúc không mong muốn.

## 4. Endpoint và query string parameters cũng thuộc request

Ngoài JSON body, search request còn có phần HTTP method, endpoint và query string parameters.

Ví dụ:

~~~http
POST /products/_search?allow_partial_search_results=false&preference=search-ui
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "size": 10
}
~~~

Có thể phân biệt ba phần:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| HTTP method và endpoint | POST /products/_search | Chọn Search API và index đích |
| URL query parameters | allow_partial_search_results, preference | Điều khiển hành vi request ở cấp endpoint |
| JSON request body | query, size, sort | Mô tả điều kiện và tùy chọn tìm kiếm trong body |

Một số tùy chọn có thể được truyền qua URL hoặc body tùy API và phiên bản Elasticsearch. Không phải mọi tham số đều có thể đặt ở cả hai nơi. Hãy tham khảo Search API của phiên bản cluster khi cần sử dụng một tham số cụ thể.

Tên index trong endpoint có thể là index vật lý, nhiều index hoặc alias. Nếu dùng alias, Elasticsearch sẽ định tuyến request theo cấu hình alias tại thời điểm xử lý.

## 5. Query DSL có thể lồng nhiều cấp

Query clause có thể chứa các query clause khác. Ví dụ **bool** chứa **must**, **filter**, **should** và **must_not**; mỗi danh sách lại chứa những query như term, match hoặc range.

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "mechanical keyboard",
            "operator": "and"
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "status": "ACTIVE"
        }
      },
      {
        "range": {
          "price": {
            "gte": 50,
            "lte": 150
          }
        }
      }
    ],
    "must_not": [
      {
        "term": {
          "category": "discontinued"
        }
      }
    ]
  }
}
~~~

Đây vẫn là một query clause, dù có nhiều cấp lồng nhau. Các key **must**, **filter**, **must_not** là cấu trúc bên trong bool query, không phải các tùy chọn cấp search request.

Cần phân biệt:

- **bool.filter** là điều kiện lọc tài liệu trong filter context; các clause trong filter không đóng góp vào relevance score.
- **bool.must** là điều kiện bắt buộc và có thể đóng góp vào score.
- **bool.should** biểu đạt các điều kiện tùy chọn hoặc điều kiện OR, tùy ngữ cảnh và **minimum_should_match**.
- **bool.must_not** loại tài liệu khớp điều kiện được chỉ định.

Những thành phần này quyết định tài liệu nào khớp và cách tính điểm liên quan. Chúng vẫn nằm trong phạm vi query clause.

## 6. Những thuộc tính thường gặp ở cấp search request

Search request có thể chứa nhiều thuộc tính ngoài **query**. Một số thuộc tính thường dùng:

| Thuộc tính | Mục đích | Có phải query clause không? |
|---|---|---|
| **from** | Bỏ qua số hit đầu tiên khi phân trang | Không |
| **size** | Số hit tối đa cần trả về | Không |
| **sort** | Sắp xếp kết quả | Không |
| **_source** | Chọn hoặc loại trừ trường source trả về | Không |
| **highlight** | Tạo đoạn văn bản được đánh dấu | Không |
| **aggs** hoặc **aggregations** | Tính thống kê, nhóm và tổng hợp dữ liệu | Không |
| **post_filter** | Lọc hit sau khi aggregation đã được tính | Không; là một query riêng ở cấp request |
| **track_total_hits** | Điều khiển cách đếm tổng hit | Không |
| **timeout** | Giới hạn thời gian tìm kiếm | Không |
| **min_score** | Loại hit có score thấp hơn ngưỡng | Không |
| **collapse** | Gộp kết quả theo một trường | Không |
| **suggest** | Tạo kết quả gợi ý | Không |
| **rescore** | Tính lại điểm cho một tập kết quả | Không |
| **search_after** | Tiếp tục phân trang dựa trên sort values | Không |
| **pit** | Dùng point in time để duy trì góc nhìn dữ liệu khi phân trang | Không |
| **runtime_mappings** | Khai báo trường runtime cho request | Không |
| **script_fields** | Tính thêm các trường trong kết quả | Không |
| **profile** | Thu thập thông tin phân tích thực thi query | Không |

Các thuộc tính này có vai trò riêng và không thể thay thế lẫn nhau. Ví dụ, **size** không giới hạn số tài liệu được Elasticsearch xét để tìm kiếm; nó giới hạn số hit trả về trong response. **min_score** lọc theo score, còn **post_filter** lọc theo điều kiện query sau bước tính aggregation.

## 7. Phân biệt query và post_filter

**query** và **post_filter** đều có thể chứa một query clause, nhưng thời điểm áp dụng khác nhau.

- **query** xác định tập tài liệu được dùng cho kết quả tìm kiếm và aggregation.
- **post_filter** lọc danh sách hit sau khi aggregation đã được tính; nó không làm thay đổi tập tài liệu mà aggregation đã sử dụng.

Ví dụ, trang danh mục muốn hiển thị số lượng sản phẩm theo category trên toàn bộ kết quả phù hợp, nhưng danh sách sản phẩm chỉ hiển thị category accessories:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "post_filter": {
    "term": {
      "category": "accessories"
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

Trong ví dụ:

1. **query** chọn tất cả sản phẩm đang ACTIVE.
2. **aggs.categories** đếm và nhóm các sản phẩm theo category trong tập ACTIVE.
3. **post_filter** chỉ giữ lại hit thuộc category accessories để trả về danh sách.
4. Aggregation vẫn có thể hiển thị các category khác vì post_filter không tác động ngược lên aggregation.

Nếu đặt điều kiện category vào **query** thay vì post_filter, aggregation cũng chỉ tính trên các sản phẩm thuộc category accessories. Vì vậy, lựa chọn vị trí đặt điều kiện có thể thay đổi ý nghĩa kết quả.

Không nên dùng post_filter thay cho filter thông thường. Nếu điều kiện phải giới hạn cả hit lẫn aggregation, hãy đặt điều kiện trong query hoặc bool.filter.

## 8. Aggregation là phần của search request, không phải query clause

Aggregation dùng để thống kê hoặc nhóm dữ liệu. Ví dụ đếm số sản phẩm theo danh mục:

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

Đây là phần aggregation của search request. Nó không quyết định tài liệu có khớp query hay không. Nếu request không có **query**, Elasticsearch có thể thực hiện aggregation trên toàn bộ tài liệu trong phạm vi index mà request nhắm tới, theo hành vi mặc định của Search API.

Kết hợp query và aggregation:

~~~http
POST /products/_search
{
  "size": 0,
  "query": {
    "range": {
      "price": {
        "gte": 20,
        "lte": 200
      }
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
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
~~~

Trong request này:

- **query** chỉ chọn sản phẩm có giá từ 20 đến 200.
- **size: 0** không trả về danh sách hit, nhưng aggregation vẫn được tính.
- **aggs.categories** nhóm tài liệu theo category.
- **average_price** tính giá trung bình cho từng nhóm.

Đây là ví dụ rõ ràng cho thấy search request có thể làm nhiều việc trong một lần gọi: lọc tài liệu, phân trang hoặc bỏ hit, tính aggregation và trả metadata.

## 9. Phân trang và sắp xếp là tùy chọn của request

Mệnh đề query quyết định tài liệu phù hợp. **from**, **size** và **sort** điều khiển phần kết quả được trả về.

~~~http
POST /products/_search
{
  "from": 20,
  "size": 10,
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "sku": {
        "order": "asc"
      }
    }
  ]
}
~~~

Request này:

- Tìm các sản phẩm thuộc category accessories.
- Sắp xếp giá tăng dần.
- Nếu giá bằng nhau, sắp xếp tiếp theo SKU.
- Bỏ qua 20 hit đầu và trả tối đa 10 hit tiếp theo.

**from** và **size** không thay đổi điều kiện query. Chúng chỉ điều khiển lát kết quả được trả về.

Với tập dữ liệu lớn, phân trang sâu bằng from/size có thể tốn tài nguyên vì Elasticsearch cần xử lý các hit trước vị trí bắt đầu trên từng shard. Khi cần duyệt nhiều trang, nên xem xét **search_after** kết hợp sort ổn định hoặc **point in time** theo yêu cầu của ứng dụng.

Ví dụ search_after trong request:

~~~http
POST /products/_search
{
  "size": 10,
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "sort": [
    {
      "price": "asc"
    },
    {
      "sku": "asc"
    }
  ],
  "search_after": [
    89.5,
    "KB-1001"
  ]
}
~~~

Giá trị search_after phải lấy từ **sort values** của hit cuối trang trước. Không tự đoán giá trị cursor. Thứ tự sort cần ổn định và có tie-breaker phù hợp để tránh bỏ sót hoặc lặp hit khi phân trang.

## 10. Source filtering không phải điều kiện lọc tài liệu

**_source** quyết định trường nào trong JSON gốc được trả về. Nó không quyết định tài liệu có khớp query hay không.

Ví dụ:

~~~http
POST /products/_search
{
  "_source": [
    "name",
    "price"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Elasticsearch vẫn tìm các tài liệu có status ACTIVE, nhưng response chỉ chứa source của trường name và price. Trường status có thể không xuất hiện trong source trả về dù nó đã được dùng để lọc.

Phân biệt:

- **query/filter** chọn tài liệu.
- **_source** chọn phần nội dung source trả về.
- **fields** hoặc **docvalue_fields** có thể yêu cầu giá trị trường theo cách khác tùy kiểu dữ liệu và API.

Nếu chỉ cần giảm kích thước response, source filtering là lựa chọn phù hợp. Không nên chuyển điều kiện tìm kiếm sang _source vì hai thuộc tính giải quyết hai vấn đề khác nhau.

## 11. Spring Data Elasticsearch: CriteriaQuery biểu diễn phần nào?

Trong Spring Data Elasticsearch, **Criteria** mô tả điều kiện tìm kiếm và **CriteriaQuery** đóng gói các điều kiện đó thành một đối tượng **Query**.

Ví dụ:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

Criteria criteria = Criteria.where("category").is("accessories")
        .and("status").is("ACTIVE")
        .and("price").between(20.0, 100.0);

CriteriaQuery query = new CriteriaQuery(criteria);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Ở đây:

- **criteria** chứa điều kiện trên category, status và price.
- **CriteriaQuery** là đối tượng truy vấn của Spring Data.
- **operations.search(...)** thực hiện tìm kiếm trên index products.
- **SearchHits<Product>** chứa hit cùng metadata kết quả.

CriteriaQuery chủ yếu giúp xây dựng phần điều kiện. Đối tượng Query của Spring Data còn có thể mang các thiết lập chung như pageable, sort hoặc source filtering tùy API. Những thiết lập đó sẽ được chuyển đổi vào các phần tương ứng của search request.

Ví dụ thêm phân trang:

~~~java
Criteria criteria = Criteria.where("category").is("accessories");

CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 20));

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

**PageRequest** cung cấp thông tin trang và kích thước trang. Spring Data chuyển thông tin này thành các tùy chọn phân trang của search request, thường tương ứng với **from** và **size**.

Tên method và cách kết hợp pageable/sort có thể khác giữa các phiên bản. Hãy kiểm tra API của phiên bản dự án đang sử dụng.

Điểm cần nhớ: **CriteriaQuery không phải JSON body hoàn chỉnh của Search API**. Nó là đối tượng truy vấn trong Spring Data, có thể chứa điều kiện và một số tùy chọn truy vấn mà Spring Data hỗ trợ.

## 12. StringQuery nhận query clause, không phải toàn bộ request body

**StringQuery** cho phép truyền JSON Query DSL dưới dạng chuỗi. Nội dung thường là query clause mà Spring Data sẽ đặt vào phần **query** của search request.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
  "bool": {
    "filter": [
      {
        "term": {
          "category": "accessories"
        }
      },
      {
        "term": {
          "status": "ACTIVE"
        }
      }
    ]
  }
}
""";

Query query = new StringQuery(dsl);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Chuỗi JSON bắt đầu bằng **bool** vì nó mô tả query clause.

Không truyền nguyên body như sau vào constructor chỉ mong đợi query JSON:

~~~json
{
  "from": 0,
  "size": 20,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": "asc"
    }
  ]
}
~~~

Body trên là search request hoàn chỉnh. Nếu API nhận query clause, việc đưa cả body vào có thể tạo cấu trúc sai vì Spring Data có thể bọc chuỗi đó thêm một lần dưới key **query**.

Khi cần cả điều kiện query lẫn phân trang/sort, dùng các thuộc tính tương ứng trên đối tượng Query của Spring Data nếu được hỗ trợ. Khi cần tùy chọn request nâng cao chưa được Query abstraction biểu diễn, hãy dùng NativeQuery hoặc API Elasticsearch Java Client phù hợp.

## 13. NativeQuery và những tùy chọn ngoài query clause

Trong Spring Data Elasticsearch 5.x, **NativeQuery** cho phép xây dựng query bằng Elasticsearch Java API Client. Nó cũng hỗ trợ nhiều tùy chọn tìm kiếm ở cấp Query abstraction, tùy phiên bản.

Ví dụ chỉ xây dựng điều kiện query và phân trang:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("name")
                .query("wireless keyboard")))
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Trong ví dụ:

- **withQuery(...)** xây dựng query clause.
- **withPageable(...)** bổ sung thông tin phân trang.
- **operations.search(...)** thực hiện request và trả SearchHits.

NativeQuery có thể biểu diễn thêm sort, aggregation, highlight và các tính năng khác tùy phiên bản Spring Data Elasticsearch/Elasticsearch Java API Client. Cần đối chiếu tài liệu tương ứng thay vì giả định mọi trường Search API đều có builder giống nhau.

Nếu cần một tính năng chưa được Query abstraction hỗ trợ, có thể dùng Elasticsearch Java API Client trực tiếp để tạo **SearchRequest** và gọi client. Cách này cho phép điều khiển request ở cấp thấp hơn nhưng cũng khiến mã ứng dụng phụ thuộc chặt hơn vào phiên bản client.

## 14. Đối chiếu các abstraction của Spring Data với search request

| Spring Data abstraction | Phần chính mà nó biểu diễn | Có phải toàn bộ Search API request? |
|---|---|---|
| **Criteria** | Điều kiện trên trường và phép kết hợp | Không |
| **CriteriaQuery** | Criteria được đóng gói thành Query, có thể kèm một số thiết lập chung | Không |
| **StringQuery** | Query DSL JSON dưới dạng chuỗi | Không |
| **NativeQuery** | Query DSL bằng Java client builder và các tùy chọn tìm kiếm được hỗ trợ | Không mặc nhiên |
| **Query** | Hợp đồng truy vấn chung của Spring Data, có thể chứa query, pageable, sort và tùy chọn khác | Không phải raw SearchRequest |
| **SearchRequest** của Elasticsearch Java API Client | Request tìm kiếm ở cấp client | Gần với request hoàn chỉnh |
| HTTP POST /{index}/_search | Endpoint, URL parameters và body của Search API | Là request thực tế gửi đến cluster |

Điều quan trọng là không đồng nhất tên lớp **Query** của Spring Data với toàn bộ Query DSL hay toàn bộ SearchRequest của Elasticsearch. Chúng là các abstraction ở những tầng khác nhau.

## 15. Một ví dụ từ yêu cầu nghiệp vụ đến request hoàn chỉnh

Giả sử màn hình danh sách sản phẩm cần:

- Chỉ lấy sản phẩm ACTIVE.
- Tìm tên chứa từ khóa **keyboard**.
- Giới hạn giá từ 20 đến 150.
- Sắp xếp theo giá tăng dần.
- Trả 10 kết quả ở trang thứ hai.
- Chỉ trả về name, category và price.
- Highlight từ khóa trong name.
- Tính số lượng sản phẩm theo category.

Search request tương ứng:

~~~http
POST /products/_search
{
  "from": 10,
  "size": 10,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 150
            }
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ],
  "_source": [
    "name",
    "category",
    "price"
  ],
  "highlight": {
    "fields": {
      "name": {}
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

Có thể chia request thành hai nhóm:

**Điều kiện chọn tài liệu**

- match name.
- term status.
- range price.
- bool kết hợp must và filter.

**Tùy chọn và phần mở rộng của request**

- from và size.
- sort.
- _source.
- highlight.
- aggs.

Cách chia này giúp debug dễ hơn. Nếu tài liệu không xuất hiện, xem query và mapping trước. Nếu tài liệu đúng nhưng thứ tự hoặc số lượng trả về không như mong muốn, xem sort, from và size. Nếu thiếu highlight hoặc aggregation, kiểm tra các thuộc tính tương ứng ở cấp request.

## 16. Đọc response cũng cần phân biệt hit và metadata

Search response không chỉ chứa danh sách tài liệu. Nó còn có metadata về tổng số hit, thời gian thực thi, shard và aggregation.

Ví dụ response rút gọn:

~~~json
{
  "took": 8,
  "timed_out": false,
  "_shards": {
    "total": 1,
    "successful": 1,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 42,
      "relation": "eq"
    },
    "max_score": 1.2,
    "hits": [
      {
        "_index": "products",
        "_id": "p-1001",
        "_score": 1.2,
        "_source": {
          "name": "Wireless Keyboard",
          "category": "accessories",
          "price": 89.5
        },
        "highlight": {
          "name": [
            "Wireless <em>Keyboard</em>"
          ]
        }
      }
    ]
  },
  "aggregations": {
    "categories": {
      "buckets": []
    }
  }
}
~~~

Một số thành phần:

- **took** là thời gian Elasticsearch thực hiện request.
- **timed_out** cho biết request có hết thời gian chờ hay không.
- **_shards** mô tả trạng thái xử lý trên các shard.
- **hits.total** mô tả tổng số kết quả và quan hệ của con số đó.
- **hits.hits** chứa các tài liệu được trả về.
- **_score** là điểm liên quan nếu query có scoring.
- **_source** chứa dữ liệu source được yêu cầu.
- **highlight** chứa đoạn văn bản đã đánh dấu.
- **aggregations** chứa kết quả thống kê.

Trong Spring Data Elasticsearch, **SearchHits<T>** và **SearchHit<T>** giúp truy cập các hit cùng metadata. Các aggregation có thể được lấy từ kết quả truy vấn theo API aggregation của phiên bản tương ứng.

Đừng nhầm **hits.total** với số phần tử thực tế trong mảng **hits.hits**. Request có thể chỉ yêu cầu 10 kết quả nhưng tổng số hit phù hợp là 42.

## 17. Những lỗi thường gặp khi nhầm query clause với search request

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| StringQuery báo lỗi JSON hoặc query không hợp lệ | Truyền toàn bộ search request body vào nơi chỉ mong query clause | Chỉ truyền object query phù hợp với constructor |
| Search không giới hạn số kết quả như mong muốn | Đưa size vào trong bool hoặc match | Đặt size ở cấp search request hoặc dùng Pageable |
| Sort không có tác dụng | Đặt sort bên trong query clause | Dùng sort ở cấp request hoặc API sort của Query |
| Aggregation không xuất hiện | Chỉ xây dựng Criteria mà chưa cấu hình aggregation | Dùng NativeQuery hoặc API hỗ trợ aggregation |
| Aggregation đếm nhiều tài liệu hơn danh sách hit | Điều kiện được đặt trong post_filter | Đặt điều kiện chung vào query nếu aggregation cũng phải chịu lọc |
| Source bị thiếu trường | _source filtering chỉ yêu cầu một phần dữ liệu | Kiểm tra danh sách trường source được chọn |
| Highlight không xuất hiện | Chưa cấu hình highlight ở cấp request hoặc trường không phù hợp | Bổ sung highlight và kiểm tra mapping |
| Pagination sai | Nhầm page number với from hoặc size | Xem cách Pageable được chuyển đổi và page index bắt đầu từ 0 |
| Query đúng nhưng request vẫn lỗi | Sai endpoint, URL parameter hoặc quyền truy cập | Kiểm tra toàn bộ HTTP request và phản hồi cluster |
| Response có tổng hit lớn hơn số hit trả về | size giới hạn số hit trong response | So sánh hits.total với hits.hits.length |

Khi debug, hãy xác định lỗi nằm ở đâu: cấu trúc query clause, tùy chọn request, endpoint/URL parameters, mapping hay dữ liệu. Không nên sửa Criteria nếu vấn đề thực tế là size hoặc sort ở cấp request.

## 18. Quy trình đọc một search request

Khi nhận được JSON tìm kiếm từ Dev Tools, log hoặc code, có thể đọc theo thứ tự:

1. **Xem endpoint.** Xác định index hoặc alias, API được gọi và URL parameters.
2. **Tìm key query.** Đây là vị trí chứa mệnh đề Query DSL chính.
3. **Đọc query từ trong ra ngoài.** Bắt đầu với match, term, range, nested rồi xem bool kết hợp chúng.
4. **Đọc context.** Phân biệt must, filter, should và must_not.
5. **Đọc các thuộc tính ngang hàng.** Xem from, size, sort, _source, highlight, aggs, post_filter, timeout và các tùy chọn khác.
6. **Đọc response.** Tách hits, tổng số kết quả, score, highlight, aggregation và trạng thái shard.
7. **Đối chiếu với Spring Data.** Xác định phần nào đến từ Criteria, phần nào đến từ Pageable/Sort hoặc NativeQuery options.
8. **Kiểm tra mapping.** Xác nhận loại query phù hợp với kiểu trường và analyzer.
9. **Kiểm tra hành vi.** Dùng request tương đương trong Dev Tools, _validate/query, _explain hoặc profile khi cần.

Đừng so sánh hai request chỉ bằng thứ tự key JSON. Hãy so sánh cấu trúc và ý nghĩa: query clause có giống nhau không, pagination có giống nhau không, sort có giống nhau không và aggregation/filter có được đặt ở đúng cấp không.

## 19. Nguyên tắc thiết kế khi dùng Spring Data Elasticsearch

- Dùng **CriteriaQuery** cho các điều kiện đơn giản, phổ biến và dễ biểu đạt bằng Criteria.
- Dùng **Pageable** và **Sort** cho phân trang và sắp xếp khi Query abstraction hỗ trợ.
- Dùng **StringQuery** khi cần truyền trực tiếp query clause JSON.
- Dùng **NativeQuery** khi cần Query DSL nâng cao hoặc các tùy chọn tìm kiếm mà Criteria không biểu đạt thuận tiện.
- Dùng Elasticsearch Java API Client trực tiếp khi cần kiểm soát SearchRequest ở cấp thấp và API Spring Data không cung cấp tùy chọn cần thiết.
- Không đưa **from**, **size**, **sort**, **aggs** hoặc **highlight** vào trong bool query.
- Không đưa toàn bộ search request body vào StringQuery nếu constructor chỉ nhận query clause.
- Đặt điều kiện ở **query** hay **post_filter** theo đúng ý nghĩa aggregation.
- Kiểm tra endpoint, index/alias và URL parameters khi request không hoạt động như mong đợi.
- Đọc cả request lẫn response để phân biệt lỗi truy vấn và lỗi tùy chọn tìm kiếm.

Một search request hoàn chỉnh bao gồm endpoint, các tham số URL và body tìm kiếm. Trong body, **query** là nơi chứa mệnh đề Query DSL quyết định tài liệu phù hợp; các thuộc tính như **from**, **size**, **sort**, **_source**, **highlight**, **aggs** và **timeout** điều khiển cách thực hiện và trình bày kết quả. Trong Spring Data Elasticsearch, CriteriaQuery và StringQuery chủ yếu giúp xây dựng phần query, còn Query abstraction có thể mang thêm một số tùy chọn chung. Khi cần kiểm soát đầy đủ request, hãy chọn NativeQuery hoặc Elasticsearch Java API Client phù hợp với phiên bản dự án.
