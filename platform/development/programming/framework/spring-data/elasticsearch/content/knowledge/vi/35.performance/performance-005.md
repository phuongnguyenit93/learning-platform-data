# Dùng filter cho điều kiện không cần chấm điểm

Khi tìm kiếm trong Elasticsearch, không phải điều kiện nào cũng cần ảnh hưởng đến độ liên quan của kết quả. Một truy vấn sản phẩm có thể cần tìm tài liệu khớp với tên người dùng nhập, đồng thời chỉ lấy sản phẩm đang hoạt động, thuộc một thương hiệu, nằm trong khoảng giá và còn hàng.

Trong ví dụ đó, tên sản phẩm là điều kiện tìm kiếm toàn văn: tài liệu khớp tốt hơn nên có thể nhận điểm relevance cao hơn. Các điều kiện như trạng thái, thương hiệu, khoảng giá và tồn kho thường chỉ có nhiệm vụ giữ hoặc loại tài liệu. Chúng không cần đóng góp vào điểm relevance.

Elasticsearch phân biệt hai ngữ cảnh thực thi:

- **Query context:** xác định tài liệu có khớp hay không và tính `_score` để biểu diễn mức độ khớp.
- **Filter context:** chỉ xác định tài liệu có thỏa điều kiện hay không; không tính điểm relevance cho điều kiện đó.

Đặt điều kiện không cần chấm điểm vào `bool.filter` giúp truy vấn thể hiện đúng ý nghĩa, tránh tính điểm không cần thiết và tạo cơ hội cho Elasticsearch sử dụng các tối ưu hóa dành cho filter. Trong Spring Data Elasticsearch, có thể xây dựng kiểu truy vấn này bằng `NativeQuery` và Elasticsearch Query DSL.

## 1. Query context và filter context

Một truy vấn Elasticsearch thường cần trả lời hai câu hỏi khác nhau:

1. Document có thỏa điều kiện hay không?
2. Trong các document thỏa điều kiện, document nào phù hợp hơn với nội dung tìm kiếm?

Query context xử lý cả hai câu hỏi. Filter context chỉ trả lời câu hỏi thứ nhất.

### 1.1. Query context

Trong query context, Elasticsearch đánh giá mức độ một document khớp với query và tính `_score`.

Ví dụ:

~~~json
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

`match` phân tích chuỗi tìm kiếm theo analyzer của field rồi tìm các document phù hợp. Những document khớp tốt hơn có thể có `_score` cao hơn và được xếp trước khi sắp xếp theo relevance mặc định.

Query context phù hợp với full-text search, match theo nội dung người dùng nhập, các truy vấn mà độ phù hợp tương đối giữa tài liệu có ý nghĩa và các query cần đóng góp vào `_score`.

### 1.2. Filter context

Trong filter context, Elasticsearch chỉ kiểm tra điều kiện đúng hoặc sai. Điều kiện không đóng góp điểm relevance.

Ví dụ:

~~~json
{
  "query": {
    "bool": {
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
              "lte": 200
            }
          }
        }
      ]
    }
  }
}
~~~

Truy vấn chỉ lấy sản phẩm có trạng thái ACTIVE và giá trong khoảng 50 đến 200. Hai điều kiện này không cần tính điểm relevance.

Filter context thường phù hợp với trạng thái, loại, category hoặc brand ID; khoảng giá, ngày tháng hoặc số lượng; quyền truy cập và tenant ID; trường boolean; điều kiện tồn tại field; geo distance hoặc bounding box khi chỉ cần giới hạn vùng.

### 1.3. So sánh

| Tiêu chí | Query context | Filter context |
| --- | --- | --- |
| Kết quả khớp/không khớp | Có | Có |
| Tính relevance score | Có | Không |
| Ảnh hưởng _score | Có | Không |
| Dùng để xếp hạng theo mức độ phù hợp | Có | Không |
| Phù hợp với điều kiện chính xác/range | Có thể dùng | Thường nên dùng |
| Có thể được query cache | Tùy loại query và điều kiện | Có thể, theo chính sách cache của Elasticsearch |

Filter context không có nghĩa là một cơ chế index riêng hoặc một loại mapping riêng. Đây là ngữ cảnh mà một query được thực thi.

## 2. Đặt điều kiện vào bool.filter

`bool` query kết hợp nhiều điều kiện. Các clause chính:

| Clause | Ý nghĩa | Ngữ cảnh |
| --- | --- | --- |
| `must` | Tài liệu phải khớp clause | Query context |
| `should` | Clause nên khớp để tăng điểm hoặc đáp ứng ngưỡng | Query context |
| `filter` | Tài liệu phải thỏa điều kiện | Filter context |
| `must_not` | Tài liệu không được thỏa điều kiện | Filter context |

Ví dụ tìm keyboard có tên phù hợp, thuộc brand cụ thể, còn hàng và không bị ngừng bán:

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
          "term": {
            "brandId": "BRAND-10"
          }
        },
        {
          "term": {
            "available": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 50,
              "lte": 250
            }
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "status": "DISCONTINUED"
          }
        }
      ]
    }
  }
}
~~~

Trong truy vấn này, `must` dùng match để tìm kiếm tên và tính điểm relevance; `filter` loại sản phẩm sai brand, hết hàng hoặc ngoài khoảng giá; `must_not` loại sản phẩm đã ngừng bán. Chỉ các query trong ngữ cảnh query đóng góp điểm cho việc xếp hạng.

### 2.1. Filter kết hợp theo AND

Các clause trong `bool.filter` đều phải thỏa mãn. Có thể hiểu chúng là phép AND:

~~~text
brandId = BRAND-10
       AND available = true
       AND price >= 50
       AND price <= 250
~~~

Nếu một document không thỏa một filter bắt buộc, nó bị loại khỏi kết quả.

### 2.2. must_not là điều kiện phủ định trong filter context

`must_not` loại document thỏa query được đặt bên trong. Clause này không tính điểm relevance.

~~~json
{
  "bool": {
    "must_not": [
      {
        "terms": {
          "status": ["DELETED", "BLOCKED"]
        }
      }
    ]
  }
}
~~~

Document có status DELETED hoặc BLOCKED bị loại. Không cần đưa điều kiện phủ định này vào `must` rồi dùng match chỉ để tạo điểm số không cần thiết.

### 2.3. should không mặc nhiên là filter

`should` thường được dùng để tăng relevance score khi document khớp thêm một điều kiện. Nó thuộc query context.

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "keyboard"
        }
      }
    ],
    "should": [
      {
        "term": {
          "featured": true
        }
      }
    ],
    "filter": [
      {
        "term": {
          "available": true
        }
      }
    ]
  }
}
~~~

Sản phẩm featured có thể được tăng điểm, nhưng vẫn phải thỏa filter available.

Nếu bool query có `must` hoặc `filter`, mặc định `minimum_should_match` là 0. Khi đó `should` chỉ ảnh hưởng score và không bắt buộc document phải khớp `should`. Nếu bool query chỉ có `should` mà không có `must`/`filter`, mặc định ít nhất một `should` phải khớp.

Nếu nghiệp vụ yêu cầu ít nhất một `should` phải khớp, hãy khai báo `minimum_should_match` rõ ràng thay vì dựa vào default.

## 3. Kết hợp full-text search với filter

Đây là mẫu thường gặp trong ứng dụng Spring Data Elasticsearch:

- Người dùng nhập từ khóa.
- Ứng dụng tìm theo nội dung.
- Người dùng chọn filter trên giao diện.
- Filter chỉ thu hẹp tập kết quả.

Ví dụ:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless keyboard",
            "fields": ["name^3", "description", "brandName"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "categoryId": "KEYBOARDS"
          }
        },
        {
          "term": {
            "available": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 30,
              "lte": 180
            }
          }
        }
      ]
    }
  }
}
~~~

`multi_match` tìm trên nhiều field và có thể ảnh hưởng điểm relevance. Các filter category, available và price chỉ thu hẹp tập document.

Nếu người dùng bỏ trống từ khóa nhưng vẫn chọn filter, có thể tạo bool query chỉ gồm `filter`. Không cần thêm `match_all` vào `must` chỉ để query chạy được; tuy nhiên `match_all` kết hợp với filter cũng là cách biểu đạt hợp lệ nếu ứng dụng cần một cấu trúc query cố định.

### 3.1. Filter không làm thay đổi relevance score

Giả sử hai sản phẩm đều khớp tên tìm kiếm, nhưng một sản phẩm có brand ID phù hợp và một sản phẩm không phù hợp:

- Sản phẩm không thỏa brand filter bị loại.
- Các sản phẩm còn lại được xếp hạng dựa trên query context.
- Filter không cộng thêm điểm cho sản phẩm có brand ID đúng.

Đây là khác biệt quan trọng giữa điều kiện bắt buộc và tín hiệu xếp hạng.

### 3.2. Khi nào một điều kiện nên nằm trong must?

Hãy tự hỏi điều kiện có cần làm thay đổi thứ hạng hay không.

| Điều kiện | Vị trí thường phù hợp | Lý do |
| --- | --- | --- |
| Tên sản phẩm chứa nội dung người dùng tìm | `must` / `should` | Cần relevance |
| Brand ID phải bằng một giá trị | `filter` | Chỉ cần đúng/sai |
| Trạng thái phải là ACTIVE | `filter` | Không cần điểm |
| Giá nằm trong khoảng | `filter` | Điều kiện số học |
| Tài liệu khớp thêm từ đồng nghĩa để tăng độ phù hợp | `should` | Có thể tăng score |
| Loại tài liệu bị cấm | `must_not` | Loại khỏi tập kết quả |
| Người dùng phải thuộc tenant hiện tại | `filter` | Ràng buộc bắt buộc |

Một điều kiện dạng `term` vẫn có thể đặt trong `must`, nhưng nếu nó không cần score thì đặt vào `filter` thể hiện đúng mục đích hơn.

## 4. Các query thường dùng trong filter context

Nhiều query DSL có thể được thực thi trong filter context. Chúng không cần một loại query riêng chỉ vì nằm trong filter.

### 4.1. term

Dùng để so sánh chính xác một giá trị:

~~~json
{
  "term": {
    "status": "ACTIVE"
  }
}
~~~

Phù hợp với keyword, boolean, numeric, date và các field có semantics so khớp chính xác.

Không dùng `term` trực tiếp trên field `text` đã được analyzer xử lý nếu bạn mong muốn so khớp toàn văn. Với text, thường dùng `match` trong query context. Nếu cần exact match, tạo keyword subfield hoặc mapping field dạng keyword.

### 4.2. terms

Dùng khi field có thể khớp một trong nhiều giá trị:

~~~json
{
  "terms": {
    "categoryId": ["KEYBOARDS", "MICE", "MONITORS"]
  }
}
~~~

`terms` thường được đặt trong filter khi các ID là lựa chọn lọc.

### 4.3. range

Dùng để giới hạn giá trị:

~~~json
{
  "range": {
    "price": {
      "gte": 50,
      "lt": 200
    }
  }
}
~~~

Các toán tử phổ biến: `gt` lớn hơn, `gte` lớn hơn hoặc bằng, `lt` nhỏ hơn và `lte` nhỏ hơn hoặc bằng.

Range cũng phù hợp với date:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "2026-01-01T00:00:00Z",
      "lt": "2027-01-01T00:00:00Z"
    }
  }
}
~~~

### 4.4. exists

Dùng để kiểm tra field có giá trị được index hay không:

~~~json
{
  "exists": {
    "field": "publishedAt"
  }
}
~~~

`exists` kiểm tra giá trị có tồn tại trong index theo semantics mapping. Field có giá trị null hoặc mảng rỗng thường được xem là không tồn tại; field có empty string có thể vẫn được xem là tồn tại.

### 4.5. prefix và wildcard

Khi nghiệp vụ cần prefix hoặc pattern, query vẫn có thể được đặt trong filter context:

~~~json
{
  "prefix": {
    "sku": "KB-"
  }
}
~~~

~~~json
{
  "wildcard": {
    "sku": {
      "value": "KB-10*"
    }
  }
}
~~~

Không tính score không đồng nghĩa query rẻ. Wildcard, regex hoặc pattern có thể tốn tài nguyên tùy cấu trúc pattern và mapping. Tránh wildcard bắt đầu bằng dấu sao trên tập dữ liệu lớn nếu không có lý do và benchmark.

### 4.6. nested

Nếu field là nested object, nested query cũng có thể được dùng trong filter context:

~~~json
{
  "nested": {
    "path": "variants",
    "query": {
      "bool": {
        "filter": [
          {
            "term": {
              "variants.color": "black"
            }
          },
          {
            "range": {
              "variants.price": {
                "lte": 150
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Điều kiện màu và giá phải thuộc cùng một nested variant. Nếu chỉ đặt field con trong object array thông thường, Elasticsearch có thể ghép các giá trị từ những phần tử khác nhau.

### 4.7. geo_distance và geo_bounding_box

Filter context phù hợp khi khoảng cách hoặc vùng địa lý chỉ là điều kiện giới hạn:

~~~json
{
  "geo_distance": {
    "distance": "10km",
    "location": {
      "lat": 10.7769,
      "lon": 106.7009
    }
  }
}
~~~

Nếu cần xếp hạng theo khoảng cách, có thể sử dụng sort theo geo distance hoặc một scoring function phù hợp. Nếu chỉ cần lấy các địa điểm trong bán kính, filter context là lựa chọn tự nhiên.

## 5. Filter context không tự động có nghĩa là cache

Một lý do thường được nhắc đến khi dùng filter là khả năng tận dụng query cache. Tuy nhiên, cần phân biệt hai khái niệm:

- Filter context: query không tính relevance score.
- Node query cache: cơ chế cache kết quả một số query/filter theo segment trên mỗi node.

Đặt query vào filter context không đảm bảo kết quả sẽ được cache.

### 5.1. Query cache hoạt động tự động

Elasticsearch quản lý query cache bằng heuristics. Không phải mọi filter đều được cache. Việc cache phụ thuộc vào loại query, lịch sử sử dụng, segment, chi phí và các điều kiện nội bộ khác.

Một số điểm cần nhớ:

- Query cache là cache theo segment.
- Cache tồn tại ở cấp node, không phải một cache toàn cluster duy nhất.
- Segment thay đổi hoặc bị merge có thể làm cache entry không còn hữu ích.
- Query quá ít được tái sử dụng có thể không đáng cache.
- Các query có đặc tính không phù hợp có thể không được cache.
- Elasticsearch tự quyết định cache/evict theo chính sách của nó.

Do đó, không nên thiết kế hiệu năng dựa trên giả định mọi `bool.filter` đều được cache.

### 5.2. Filter ổn định và thường lặp lại

Một filter có tính ổn định và được lặp lại nhiều lần, ví dụ `status=ACTIVE` hoặc một tenant/category phổ biến, có thể là ứng viên tốt cho query cache nếu thỏa các điều kiện nội bộ của Elasticsearch.

Một filter chứa timestamp thay đổi liên tục hoặc giá trị ngẫu nhiên theo mỗi request thường có ít cơ hội tái sử dụng kết quả cache.

### 5.3. Không tự thêm cache chỉ vì đã dùng filter

Thông thường, không cần cấu hình thủ công cache cho từng filter. Hãy:

1. Đặt điều kiện không cần score vào filter context.
2. Đo query latency và throughput.
3. Quan sát query cache hit/miss và memory qua node stats.
4. Kiểm tra query profile nếu có vấn đề.
5. Chỉ thay đổi cấu hình cache khi có bằng chứng đo lường.

Không có bảo đảm rằng filter sẽ luôn nhanh hơn mọi query context trong mọi tình huống. Lợi ích rõ ràng nhất là bỏ chi phí tính score không cần thiết và giúp query thể hiện đúng semantics.

## 6. Filter và sorting

Filter không quyết định thứ tự kết quả. Nếu query chỉ có filter và không chỉ định sort, Elasticsearch có thể trả kết quả theo thứ tự mặc định của search engine, không phải theo giá hoặc ngày cập nhật.

Ví dụ lọc sản phẩm đang bán trong khoảng giá rồi sort theo giá tăng dần:

~~~json
{
  "query": {
    "bool": {
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
              "lte": 200
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
  ]
}
~~~

Trong trường hợp này, kết quả được xếp theo `price`, không theo relevance.

### 6.1. Sort theo field và _score

Nếu chỉ sort theo field, Elasticsearch không cần dùng `_score` để sắp xếp kết quả. Nếu ứng dụng vẫn cần score trong response khi sort theo field, có thể bật `track_scores` theo API tương ứng.

~~~json
{
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
            "available": true
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
  "track_scores": true
}
~~~

`track_scores` không biến filter thành query context. Nó yêu cầu theo dõi score trong một tình huống sort theo field.

### 6.2. Pagination ổn định

Khi phân trang sâu hoặc dữ liệu thay đổi liên tục, sort cần có tie-breaker ổn định. Ví dụ sort theo price rồi theo ID duy nhất. Với pagination sâu, cân nhắc Point in Time (PIT) kết hợp `search_after` thay vì offset quá lớn.

## 7. Filter ảnh hưởng aggregations như thế nào?

Vị trí đặt filter quyết định tập document được dùng cho aggregations.

### 7.1. bool.filter bên trong query

Nếu filter nằm trong top-level query, cả hits và aggregations đều chỉ làm việc trên tập document đã qua filter.

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  },
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brandId"
      }
    }
  }
}
~~~

Aggregation `by_brand` chỉ thống kê sản phẩm ACTIVE.

### 7.2. post_filter

`post_filter` được áp dụng cho search hits sau khi aggregations đã được tính. Nó hữu ích khi giao diện cần lọc danh sách kết quả nhưng vẫn muốn aggregations phản ánh tập kết quả rộng hơn.

~~~json
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "post_filter": {
    "term": {
      "brandId": "BRAND-10"
    }
  },
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brandId"
      }
    }
  }
}
~~~

Trong ví dụ, query tìm tất cả sản phẩm liên quan đến keyboard; aggregation tính phân bố theo brand trên tập kết quả query; post_filter chỉ thu hẹp hits trả về cho brand BRAND-10.

Nếu đặt brand filter vào top-level `bool.filter`, aggregation cũng chỉ thấy brand BRAND-10. Vì vậy, không thay `bool.filter` bằng `post_filter` một cách máy móc.

## 8. Dùng filter trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `NativeQuery` để xây dựng Elasticsearch Query DSL thông qua Java API Client query builder.

Ví dụ dưới đây dùng:

- `must` cho full-text query.
- `filter` cho các điều kiện không cần score.
- `must_not` để loại document.

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(mm -> mm
                    .field("name")
                    .query("mechanical keyboard")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("brandId")
                    .value("BRAND-10")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("available")
                    .value(true)
                )
            )
            .filter(f -> f
                .range(r -> r
                    .number(n -> n
                        .field("price")
                        .gte(50.0)
                        .lte(250.0)
                    )
                )
            )
            .mustNot(mn -> mn
                .term(t -> t
                    .field("status")
                    .value("DISCONTINUED")
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Tên builder method và overload của range query có thể khác theo phiên bản Elasticsearch Java API Client và Spring Data Elasticsearch. Đối chiếu Javadoc của dependency dự án nếu compiler yêu cầu một kiểu value hoặc builder khác. Ý nghĩa DSL không đổi: các điều kiện nằm trong `filter` chạy trong filter context.

### 8.1. Tách query builder khỏi service

Với ứng dụng có nhiều filter động, nên tạo một thành phần chuyên xây dựng query thay vì đặt tất cả lambda trong service.

Ví dụ cấu trúc criteria:

~~~java
public record ProductSearchCriteria(
    String text,
    String brandId,
    String categoryId,
    Double minPrice,
    Double maxPrice,
    Boolean available,
    Pageable pageable
) {}
~~~

Logic xây dựng filter nên phân biệt:

- Không gửi field: không áp dụng điều kiện.
- Giá trị boolean false: vẫn là filter hợp lệ, không được coi là thiếu.
- Danh sách rỗng: thường không thêm terms query; cần quy định rõ empty list nghĩa là không lọc hay không có kết quả.
- Giá trị 0: là giá trị hợp lệ, không được kiểm tra bằng điều kiện lớn hơn 0 nếu nghiệp vụ cho phép.
- Khoảng min/max: chỉ thêm range khi có ít nhất một biên và xử lý trường hợp min lớn hơn max.

Khi xây query động, chỉ thêm clause khi criteria tương ứng có giá trị. Không tạo range hoặc term với giá trị null, và không chuyển điều kiện bắt buộc thành should chỉ để tránh lỗi query.

### 8.2. CriteriaQuery

Spring Data Elasticsearch cũng có `CriteriaQuery` và Criteria API để mô tả các điều kiện theo kiểu fluent.

Criteria phù hợp với query đơn giản và các điều kiện field-oriented. Khi cần điều khiển rõ `bool.must`, `bool.filter`, `must_not`, `minimum_should_match`, nested scoring hoặc query DSL phức tạp, `NativeQuery` thường biểu đạt chính xác hơn.

Không nên mặc định mọi Criteria condition đều mang cùng semantics với một `bool.filter` cụ thể mà không kiểm tra query DSL được tạo ra. Nếu yêu cầu hiệu năng phụ thuộc việc điều kiện nằm trong filter context, hãy xác nhận request thực tế qua logging hoặc integration test.

## 9. Thiết kế filter động từ search criteria

Một search form thường cho phép người dùng chọn nhiều filter tùy chọn. Ứng dụng nên chỉ thêm clause tương ứng khi filter có giá trị.

Ví dụ criteria:

~~~java
public record ProductSearchCriteria(
    String text,
    String brandId,
    String categoryId,
    Double minPrice,
    Double maxPrice,
    Boolean available,
    Pageable pageable
) {}
~~~

### 9.1. Filter theo danh sách

Nếu người dùng chọn nhiều category:

~~~json
{
  "terms": {
    "categoryId": ["KEYBOARDS", "MICE"]
  }
}
~~~

Đây là OR trong cùng một terms query: document có một trong các giá trị được chọn là phù hợp. Nếu kết hợp với một filter khác, hai filter ở cấp bool.filter vẫn được AND với nhau.

### 9.2. Nhiều lựa chọn trong cùng nhóm và giữa các nhóm

Giao diện faceted search thường có semantics:

- OR giữa các giá trị cùng một facet, ví dụ category thuộc KEYBOARDS hoặc MICE.
- AND giữa các facet, ví dụ category hợp lệ và brand hợp lệ và available.

~~~json
{
  "bool": {
    "filter": [
      {
        "terms": {
          "categoryId": ["KEYBOARDS", "MICE"]
        }
      },
      {
        "terms": {
          "brandId": ["BRAND-10", "BRAND-20"]
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
~~~

Document phải khớp ít nhất một category, ít nhất một brand và available=true.

## 10. Filter cho tenant và quyền truy cập

Tenant ID hoặc điều kiện phân vùng dữ liệu thường không cần score. Có thể đặt chúng trong filter context:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "content": "invoice"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "tenantId": "TENANT-42"
          }
        }
      ]
    }
  }
}
~~~

Điều kiện tenant là một ràng buộc bắt buộc và không cần tăng relevance score.

Việc đặt tenant ID vào filter không tự nó tạo ra một ranh giới bảo mật. Ứng dụng phải lấy tenant ID từ context đã được xác thực và kiểm soát, không tin trực tiếp giá trị do client gửi lên. Nếu người dùng có thể tự đổi tenant ID trong request, họ có thể truy vấn dữ liệu tenant khác.

Tương tự, filter quyền truy cập phải được tạo từ authorization context đáng tin cậy. Query filter là một phần của enforcement ở tầng tìm kiếm, nhưng không thay thế authentication và authorization của ứng dụng.

## 11. Filter và scoring: các trường hợp cần cân nhắc

Không phải mọi điều kiện dạng category hoặc numeric đều luôn phải ở filter. Cần dựa vào semantics sản phẩm.

Ví dụ:

- Người dùng chọn brand từ dropdown: filter.
- Hệ thống muốn ưu tiên brand được quảng bá: should hoặc function_score.
- Người dùng yêu cầu giá nằm trong khoảng: filter.
- Hệ thống muốn điểm phù hợp giảm dần theo độ gần với mức giá mục tiêu: scoring function.
- Người dùng yêu cầu sản phẩm đang còn hàng: filter.
- Hệ thống muốn ưu tiên sản phẩm có tồn kho dồi dào: scoring signal nếu nghiệp vụ cho phép.

### 11.1. Khi điều kiện phải lọc nhưng cũng muốn tăng điểm

Một điều kiện có thể vừa là ràng buộc vừa là tín hiệu scoring, nhưng cần diễn đạt rõ hai vai trò.

Ví dụ, chỉ lấy sản phẩm available=true, sau đó ưu tiên sản phẩm featured:

~~~json
{
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
            "available": true
          }
        }
      ],
      "should": [
        {
          "term": {
            "featured": true
          }
        }
      ]
    }
  }
}
~~~

available là điều kiện bắt buộc; featured là tín hiệu tăng điểm. Không cần đưa available vào should vì sản phẩm hết hàng không được phép xuất hiện.

### 11.2. constant_score

`constant_score` chạy query con trong filter context và gán một score cố định cho mọi document khớp.

~~~json
{
  "query": {
    "constant_score": {
      "filter": {
        "term": {
          "status": "ACTIVE"
        }
      },
      "boost": 1.0
    }
  }
}
~~~

`constant_score` hữu ích khi muốn một tập document khớp filter nhận cùng một điểm số. Nếu ứng dụng chỉ cần lọc, `bool.filter` thường trực tiếp và dễ đọc hơn.

## 12. Đo lường hiệu năng

Dùng filter là một quyết định về semantics và tối ưu thực thi. Không nên kết luận hiệu năng chỉ từ số lượng clause hoặc từ việc query có filter.

### 12.1. Profile query

Elasticsearch Profile API giúp xem thời gian thực thi các thành phần query. Profile có overhead, vì vậy chỉ nên bật trong quá trình chẩn đoán, không bật thường trực cho mọi request production.

Có thể dùng profile để xác định clause nào tốn thời gian, so sánh query có scoring với query filter tương ứng, phát hiện wildcard/nested/script query tốn tài nguyên và hiểu query execution trên từng shard.

### 12.2. Theo dõi node stats

Query cache stats có thể giúp quan sát cache hit count, cache miss count, memory đang dùng và số entry được cache/evict.

Các con số này cần được xem trong bối cảnh workload và segment churn. Hit ratio cao không tự động chứng minh query latency tốt; hit ratio thấp cũng không có nghĩa phải ép cache mọi filter.

### 12.3. Benchmark với dữ liệu đại diện

Khi so sánh query, cần giữ cùng dataset và mapping, số shard/replica, query parameters, page size và sort, tình trạng cache nóng/lạnh, mức tải đồng thời, refresh và indexing activity.

Đo nhiều lần và so sánh latency phân vị như p50, p95, p99, throughput và CPU. Tránh so sánh một lần chạy cache lạnh với một lần chạy cache nóng rồi kết luận.

## 13. Những lỗi thường gặp

**Đặt mọi điều kiện vào must.** Điều kiện chính xác như status, brand ID và price range không cần relevance score. Đưa chúng vào filter.

**Nghĩ rằng filter làm query không còn score.** Filter clause không đóng góp score, nhưng query context như must/should vẫn có thể tính score cho document.

**Nghĩ rằng filter luôn được cache.** Query cache được Elasticsearch quản lý theo heuristics; filter context không bảo đảm cache hit.

**Dùng term trên text field để tìm nội dung.** Text field được analyzer xử lý; dùng match cho full-text hoặc keyword subfield cho exact match.

**Đưa điều kiện xếp hạng vào filter.** Nếu một thuộc tính phải tăng hoặc giảm relevance, dùng should, function_score hoặc scoring query phù hợp.

**Dùng should để biểu diễn điều kiện bắt buộc.** Khi có must/filter, should mặc định có thể không bắt buộc. Dùng filter cho điều kiện bắt buộc hoặc đặt minimum_should_match rõ ràng.

**Quên semantics của post_filter.** post_filter chỉ lọc hits sau aggregation; top-level query/filter ảnh hưởng cả hits và aggregation.

**Cho rằng filter tự sort kết quả.** Filter chỉ giới hạn document. Nếu cần thứ tự theo giá, ngày hoặc score, phải khai báo sort.

**Dùng wildcard rộng trong filter và kỳ vọng luôn nhanh.** Filter không tính score nhưng wildcard vẫn có thể tốn tài nguyên.

**Đưa tenant ID trực tiếp từ client vào filter.** Lấy tenant từ context đã xác thực và kiểm soát authorization ở tầng ứng dụng.

**Dùng CriteriaQuery mà không kiểm tra DSL được sinh ra.** Nếu semantics filter context là yêu cầu bắt buộc, xác nhận query thực tế hoặc dùng NativeQuery để biểu đạt rõ.

**Bật track_scores mà không cần score.** Khi sort theo field, chỉ theo dõi score nếu caller thực sự cần giá trị _score.

## 14. Quy trình xây dựng truy vấn có filter

Khi thiết kế một search endpoint:

1. Phân loại từng điều kiện: cần relevance hay chỉ cần đúng/sai.
2. Đặt full-text search vào must hoặc should.
3. Đặt điều kiện chính xác, range, tenant và trạng thái vào filter.
4. Đặt điều kiện loại trừ vào must_not.
5. Xác định minimum_should_match nếu should có vai trò bắt buộc.
6. Chọn mapping phù hợp: keyword cho exact match, numeric/date cho range, nested cho object array có quan hệ.
7. Xác định sort độc lập với filter.
8. Xác định aggregation cần thống kê trên tập document nào; chọn query filter hay post_filter đúng semantics.
9. Tạo query bằng NativeQuery hoặc API phù hợp của Spring Data Elasticsearch.
10. Đo query bằng dữ liệu đại diện; chỉ tối ưu cache khi có số liệu.

~~~text
Search request
     |
     v
Build bool query
     |
     +-- must: full-text relevance
     |
     +-- should: optional ranking signals
     |
     +-- filter: exact/range/tenant constraints
     |
     +-- must_not: excluded documents
     |
     v
Sort and pagination
     |
     v
Elasticsearch
     |
     v
SearchHits + aggregations
~~~

## 15. Ví dụ hoàn chỉnh: tìm kiếm sản phẩm

Yêu cầu:

- Tìm sản phẩm theo từ khóa trong tên và mô tả.
- Chỉ lấy sản phẩm đang ACTIVE.
- Lọc theo brand tùy chọn.
- Lọc theo category tùy chọn.
- Lọc theo khoảng giá tùy chọn.
- Chỉ lấy sản phẩm còn hàng nếu người dùng bật bộ lọc.
- Xếp hạng theo relevance, sau đó có thể sort theo giá khi người dùng chọn.

Query DSL minh họa:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless keyboard",
            "fields": ["name^3", "description"]
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
          "term": {
            "brandId": "BRAND-10"
          }
        },
        {
          "terms": {
            "categoryId": ["KEYBOARDS", "ACCESSORIES"]
          }
        },
        {
          "range": {
            "price": {
              "gte": 40,
              "lte": 180
            }
          }
        },
        {
          "term": {
            "available": true
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "deleted": true
          }
        }
      ]
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

Trong production, brand, category, price và available chỉ được thêm khi criteria tương ứng có giá trị. Status ACTIVE và deleted=false có thể là điều kiện hệ thống luôn áp dụng.

### 15.1. Khi người dùng sort theo giá

Thay sort:

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "_score": {
        "order": "desc"
      }
    }
  ]
}
~~~

Lúc này giá là tiêu chí sắp xếp chính; _score dùng để phân định thứ tự giữa các sản phẩm cùng giá nếu query theo API và mapping cho phép.

### 15.2. Khi không có từ khóa

Nếu người dùng chỉ chọn brand, category và price, có thể tạo bool query chỉ với filter:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "term": {
            "brandId": "BRAND-10"
          }
        },
        {
          "range": {
            "price": {
              "lte": 180
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
  ]
}
~~~

Không có full-text query nên không có relevance ranking có ý nghĩa. Sort theo field đáp ứng yêu cầu giao diện.

## 16. Tài liệu tham khảo

- [Elasticsearch - Query and filter context](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-filter-context.html): khác biệt query context và filter context.
- [Elasticsearch - Boolean query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html): must, should, filter, must_not và minimum_should_match.
- [Elasticsearch - Query cache](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-cache.html): cache theo segment và điều kiện sử dụng.
- [Elasticsearch - Term query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-term-query.html): so khớp chính xác.
- [Elasticsearch - Range query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-range-query.html): điều kiện khoảng.
- [Elasticsearch - Post filter](https://www.elastic.co/guide/en/elasticsearch/reference/current/filter-search-results.html): lọc hits sau aggregation.
- [Elasticsearch - Profile search requests](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-profile.html): phân tích chi phí thực thi query.
- [Spring Data Elasticsearch - Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): xây dựng query và thực thi search qua ElasticsearchOperations.
- [Spring Data Elasticsearch - NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQuery.html): API NativeQuery dùng Elasticsearch Java API Client.

Các builder method cụ thể có thể khác theo phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Khi triển khai, hãy kiểm tra Javadoc đúng dependency. Nguyên tắc quan trọng là dùng query context cho điều kiện cần relevance, filter context cho điều kiện chỉ cần xác định document có được giữ lại hay không; việc đặt filter không tự bảo đảm cache hit và không thay thế việc đo hiệu năng thực tế.
