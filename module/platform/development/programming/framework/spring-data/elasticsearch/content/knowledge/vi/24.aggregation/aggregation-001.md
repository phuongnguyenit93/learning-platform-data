# Phân biệt aggregation và danh sách tài liệu tìm được

Trong Elasticsearch, một search request có thể trả về hai loại thông tin khác nhau: **các document khớp truy vấn** và **kết quả aggregation được tính trên tập document đó**. Danh sách document thường nằm trong `hits.hits`; aggregation nằm trong phần `aggregations` của response. Hai phần có thể xuất hiện cùng lúc nhưng giải quyết hai nhu cầu khác nhau.

Ví dụ trang danh sách sản phẩm cần hiển thị 20 sản phẩm phù hợp với từ khóa. Đó là kết quả hits. Cùng lúc, giao diện có thể cần biết có bao nhiêu sản phẩm theo từng category, giá trung bình hoặc khoảng giá để tạo bộ lọc. Đó là aggregation. Không nên cố lấy danh sách hàng nghìn document về Java rồi tự đếm hoặc tính trung bình nếu Elasticsearch có thể thực hiện phép tính trực tiếp.

Aggregation không phải một kiểu phân trang khác và bucket cũng không phải document. Một bucket là nhóm được tạo theo giá trị hoặc điều kiện; metric là con số được tính trên những document thuộc phạm vi aggregation. Một search response có thể có hits rỗng nhưng vẫn có aggregation đầy đủ.

## 1. Hits và aggregations nằm ở hai phần khác nhau

Giả sử index `products` chứa các document:

```json
[
  { "sku": "KB-01", "name": "Mechanical Keyboard", "category": "keyboard", "price": 120 },
  { "sku": "KB-02", "name": "Wireless Keyboard", "category": "keyboard", "price": 180 },
  { "sku": "MS-01", "name": "Wireless Mouse", "category": "mouse", "price": 40 },
  { "sku": "MN-01", "name": "Gaming Monitor", "category": "monitor", "price": 300 }
]
```

Một search request có thể vừa trả document vừa đếm số sản phẩm theo category:

```http
GET /products/_search
{
  "size": 10,
  "query": {
    "match_all": {}
  },
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category",
        "size": 10
      }
    }
  }
}
```

Response có hai phần chính:

```json
{
  "hits": {
    "total": {
      "value": 4,
      "relation": "eq"
    },
    "hits": [
      {
        "_id": "KB-01",
        "_source": {
          "sku": "KB-01",
          "name": "Mechanical Keyboard",
          "category": "keyboard",
          "price": 120
        }
      }
    ]
  },
  "aggregations": {
    "products_by_category": {
      "buckets": [
        { "key": "keyboard", "doc_count": 2 },
        { "key": "monitor", "doc_count": 1 },
        { "key": "mouse", "doc_count": 1 }
      ]
    }
  }
}
```

Ví dụ rút gọn response chỉ minh họa một hit; response thực tế có thể chứa tối đa `size` hit. Phần `hits` chứa document được trả về và metadata tìm kiếm. Phần `aggregations` chứa nhóm `products_by_category` với các bucket và số document trong từng bucket.

| Thành phần | Nội dung | Dùng để |
|---|---|---|
| `hits.hits` | Các document cụ thể | Hiển thị danh sách hoặc đọc nội dung từng document |
| `hits.total` | Tổng số document khớp query theo chế độ tracking | Hiển thị tổng kết quả hoặc số trang khi cần |
| `aggregations` | Buckets và metric | Thống kê, facet/filter, biểu đồ, phân tích |
| `bucket.doc_count` | Số document trong một nhóm | Đếm số document theo category, trạng thái, khoảng giá... |
| Metric value | Một hoặc nhiều giá trị số | Tính tổng, trung bình, min/max, cardinality... |

## 2. Hits là danh sách document tìm được

`hits.hits` là danh sách kết quả document được trả về trong response. Mỗi hit có thể chứa:

- `_index`: index vật lý chứa document.
- `_id`: định danh document.
- `_score`: relevance score nếu query có scoring.
- `_source`: nội dung document nếu được yêu cầu trả về.
- `sort`: các giá trị sort, hữu ích cho `search_after`.
- `highlight`: các fragment được đánh dấu nếu request có cấu hình highlight.
- Một số metadata khác tùy request.

### 2.1 `size` điều khiển số hit, không điều khiển aggregation

Ví dụ:

```json
{
  "size": 20,
  "query": {
    "match_all": {}
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

`size: 20` yêu cầu tối đa 20 document trong `hits.hits`. Nó không có nghĩa aggregation chỉ tính trên 20 document đó. Aggregation được tính trên tập document thuộc phạm vi query (và scope của aggregation), trước khi lấy lát hits theo `from`/`size`.

Điểm này rất quan trọng với giao diện phân trang: trang đầu có thể chỉ hiển thị 20 sản phẩm nhưng facet category vẫn thống kê trên toàn bộ tập sản phẩm thỏa query, không chỉ 20 sản phẩm đang nhìn thấy.

### 2.2 `hits.total` khác tổng bucket

`hits.total` là tổng số document khớp query chính theo cấu hình total-hit tracking. `bucket.doc_count` là số document thuộc bucket cụ thể. Tổng `doc_count` của một aggregation không phải lúc nào cũng bằng `hits.total`:

- Một document có thể thuộc nhiều bucket, ví dụ terms trên một field mảng.
- Terms aggregation có thể chỉ trả một số bucket hàng đầu (`size` của aggregation).
- Một số bucket có thể không được trả về do giới hạn hoặc thứ tự bucket.
- Aggregation có thể có filter/scope riêng làm tập document khác query chính.

Không cộng `doc_count` rồi coi đó là tổng document tìm được nếu chưa xác định semantics của aggregation.

## 3. Aggregation là kết quả thống kê trên document

Aggregation tính toán trên tập document mà nó nhận được. Các nhóm thường gặp:

- **Bucket aggregations:** chia document thành các nhóm, ví dụ terms, range, date histogram, filters.
- **Metric aggregations:** tính giá trị như `sum`, `avg`, `min`, `max`, `stats`, `cardinality`.
- **Pipeline aggregations:** tính toán dựa trên kết quả của aggregation khác, ví dụ derivative, moving average hoặc bucket calculations tùy loại.

Aggregation có thể lồng nhau. Ví dụ nhóm sản phẩm theo category rồi tính giá trung bình trong mỗi category.

### 3.1 Bucket aggregation

Terms aggregation nhóm document theo giá trị của field:

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
```

`size: 0` ở cấp search request yêu cầu không trả danh sách document hits. Aggregation vẫn được tính và trả về. Đây là cách phổ biến khi endpoint chỉ cần thống kê/facet.

Lưu ý có hai thuộc tính `size` khác nhau trong ví dụ:

- Search-level `size: 0`: số document hits trả về bằng 0.
- Aggregation-level `terms.size: 20`: tối đa 20 bucket category được trả về.

Hai giá trị này điều khiển hai thứ hoàn toàn khác nhau.

### 3.2 Metric aggregation

Metric aggregation tính số liệu trên field số:

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "price_stats": {
      "stats": {
        "field": "price"
      }
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
```

`stats` trả các giá trị như count, min, max, avg và sum. `avg` chỉ trả giá trị trung bình. Những phép tính này được Elasticsearch thực hiện trên các document phù hợp, không yêu cầu ứng dụng tải toàn bộ document về để tính bằng Java.

### 3.3 Aggregation lồng nhau

Có thể kết hợp bucket và metric:

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        },
        "max_price": {
          "max": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

Mỗi bucket category có `doc_count`, `average_price` và `max_price` riêng. Đây là cách tạo dữ liệu cho biểu đồ “giá trung bình theo danh mục” mà không cần lấy từng sản phẩm về ứng dụng.

## 4. Phạm vi document mà aggregation sử dụng

Thông thường, aggregation ở cấp top-level chạy trên tập document khớp query chính. Nếu query có filter, aggregation cũng nhận tập đã lọc đó.

Ví dụ chỉ thống kê sản phẩm ACTIVE:

```http
GET /products/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ]
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

Aggregation `by_category` chỉ thống kê các document ACTIVE vì query chính đã giới hạn tập document.

### 4.1 Query filter ảnh hưởng cả hits và aggregations

Điều kiện trong `query.bool.filter` quyết định document nào tham gia cả kết quả hits và aggregation top-level. Nếu giao diện cần facet tính trên toàn bộ sản phẩm bất kể bộ lọc đang chọn, phải thiết kế scope khác thay vì đặt tất cả điều kiện trong query chính.

### 4.2 `post_filter` chỉ lọc hits sau aggregation

`post_filter` là một bộ lọc áp dụng lên hits sau khi aggregation được tính. Điều này hữu ích cho faceted navigation: người dùng chọn một facet để thu hẹp danh sách sản phẩm, nhưng muốn facet đó vẫn hiển thị số lượng của các lựa chọn khác trong phạm vi query ban đầu.

Ví dụ:

```http
GET /products/_search
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "post_filter": {
    "term": {
      "color": "black"
    }
  },
  "aggs": {
    "colors": {
      "terms": {
        "field": "color"
      }
    }
  }
}
```

Hits chỉ chứa sản phẩm màu đen, nhưng aggregation `colors` được tính trên các sản phẩm match `name = keyboard` trước khi `post_filter` áp dụng. Vì vậy, facet có thể vẫn hiển thị các màu khác cùng số lượng của chúng.

### 4.3 Filter aggregation

Nếu chỉ một aggregation cần thêm điều kiện riêng, dùng `filter` aggregation:

```http
GET /products/_search
{
  "size": 0,
  "query": {
    "match_all": {}
  },
  "aggs": {
    "active_products": {
      "filter": {
        "term": {
          "status": "ACTIVE"
        }
      },
      "aggs": {
        "average_active_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

Aggregation `active_products` có scope riêng là document ACTIVE, trong khi query chính vẫn match tất cả. Có thể tạo nhiều filter bucket nếu cần thống kê các nhóm điều kiện khác nhau trong cùng response.

### 4.4 Global aggregation

`global` aggregation bỏ qua query scope ở cấp top-level và tính trên toàn bộ document trong index mà search request nhắm tới (trong giới hạn quyền/index và các điều kiện liên quan). Nó hữu ích khi cần so sánh kết quả đang lọc với thống kê toàn bộ index.

Ví dụ query chính lọc sản phẩm ACTIVE, nhưng global aggregation tính giá trung bình toàn bộ sản phẩm:

```http
GET /products/_search
{
  "size": 0,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "aggs": {
    "all_products": {
      "global": {},
      "aggs": {
        "all_average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

Không dùng global aggregation nếu muốn giữ filter của query chính. Vì nó mở rộng scope, hãy đặc biệt cẩn thận với multi-tenant và điều kiện phân quyền. Điều kiện bảo mật phải được áp dụng ở tầng authorization/document-level security phù hợp; không dựa vào việc query thông thường đang có filter rồi giả định global aggregation tự giữ filter đó.

## 5. Các loại aggregation phổ biến

### 5.1 Terms aggregation: đếm theo giá trị

Phù hợp cho category, status, brand hoặc các field `keyword`:

```json
"aggs": {
  "by_status": {
    "terms": {
      "field": "status",
      "size": 10,
      "order": {
        "_count": "desc"
      }
    }
  }
}
```

Mặc định terms thường trả các bucket có document count cao nhất. `size` giới hạn số bucket trả về, không phải số document trong mỗi bucket.

Terms aggregation phân tán trên nhiều shard có thể có sai số đếm bucket do mỗi shard gửi một số candidate bucket lên coordinator. Response có thể chứa `doc_count_error_upper_bound` và `sum_other_doc_count`. Nếu cần độ chính xác hoặc tất cả bucket, cần hiểu giới hạn phân tán và cân nhắc `shard_size`, composite aggregation hoặc cách thiết kế khác.

### 5.2 Range aggregation: nhóm theo khoảng số

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "price",
        "ranges": [
          { "to": 100 },
          { "from": 100, "to": 250 },
          { "from": 250 }
        ]
      }
    }
  }
}
```

Các khoảng dùng biên dưới inclusive và biên trên exclusive theo semantics range aggregation. Ví dụ document có giá đúng 100 thuộc khoảng thứ hai, không thuộc khoảng đầu tiên.

### 5.3 Date histogram: nhóm theo thời gian

```http
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "+07:00",
        "min_doc_count": 0
      }
    }
  }
}
```

Date histogram nhóm document theo khoảng thời gian lịch. `calendar_interval` phù hợp với ngày/tháng/năm theo lịch; `fixed_interval` phù hợp với khoảng thời gian cố định như 15 phút hoặc 1 giờ. Timezone ảnh hưởng biên bucket. Nếu cần bucket rỗng cho khoảng thời gian không có document, cần cấu hình extended bounds và min doc count theo mục tiêu hiển thị.

### 5.4 Metric: sum, avg, min, max, stats

```json
"aggs": {
  "total_revenue": {
    "sum": {
      "field": "amount"
    }
  },
  "average_order_value": {
    "avg": {
      "field": "amount"
    }
  },
  "largest_order": {
    "max": {
      "field": "amount"
    }
  }
}
```

Các metric này tính trên document có giá trị phù hợp ở field. Document thiếu field hoặc giá trị không được index theo kiểu số không đóng góp như một giá trị số thông thường.

### 5.5 Cardinality: đếm giá trị duy nhất

```json
"aggs": {
  "unique_customers": {
    "cardinality": {
      "field": "customerId"
    }
  }
}
```

Cardinality thường là phép đếm xấp xỉ dựa trên thuật toán HyperLogLog++. Nó phù hợp để ước lượng số khách hàng duy nhất trên tập lớn. Nếu nghiệp vụ yêu cầu số lượng chính xác tuyệt đối, không được mặc định cardinality là exact count; hãy cân nhắc chi phí và phương án dữ liệu khác.

### 5.6 Composite aggregation: duyệt nhiều bucket

Terms aggregation trả một số bucket hàng đầu. Nếu cần duyệt qua lượng bucket lớn theo từng trang, composite aggregation hỗ trợ pagination bucket bằng `after_key`.

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "category_brand": {
      "composite": {
        "size": 500,
        "sources": [
          { "category": { "terms": { "field": "category" } } },
          { "brand": { "terms": { "field": "brand" } } }
        ]
      }
    }
  }
}
```

Response có `after_key` khi còn bucket để lấy tiếp. Request tiếp theo truyền `after` bằng đúng `after_key` trả về. Composite aggregation dành cho pagination bucket; nó khác với `search_after` dùng để pagination document hits.

## 6. Hits rỗng nhưng aggregation vẫn có kết quả

Một trường hợp phổ biến là endpoint chỉ cần số liệu, không cần document. Đặt search-level `size: 0`:

```http
GET /orders/_search
{
  "size": 0,
  "query": {
    "range": {
      "createdAt": {
        "gte": "2025-01-01",
        "lt": "2026-01-01"
      }
    }
  },
  "aggs": {
    "revenue": {
      "sum": {
        "field": "amount"
      }
    },
    "orders_by_status": {
      "terms": {
        "field": "status"
      }
    }
  }
}
```

Response vẫn chứa `aggregations.revenue` và `aggregations.orders_by_status`, trong khi `hits.hits` là mảng rỗng. Đây là cách hiệu quả cho dashboard hoặc API thống kê không hiển thị danh sách document.

`size: 0` không có nghĩa không có document match; nó chỉ yêu cầu không trả document hits. `hits.total` vẫn có thể được tính nếu tracking được bật, nhưng nếu chỉ cần aggregation thì thường không cần yêu cầu đếm total hits chính xác.

## 7. `hits.total` và `track_total_hits` không phải aggregation

Elasticsearch trả tổng số hit trong `hits.total`. Việc đếm có thể bị giới hạn để cải thiện hiệu năng:

```json
"track_total_hits": true
```

Yêu cầu đếm chính xác tổng document khớp query. Với index lớn, việc này có thể tăng chi phí.

Có thể đặt ngưỡng:

```json
"track_total_hits": 10000
```

Khi vượt ngưỡng, response có thể trả relation `gte`, nghĩa là tổng ít nhất bằng giá trị được báo. `track_total_hits: false` không yêu cầu total chính xác.

Aggregation `value_count` cũng có thể đếm số giá trị của một field, nhưng nó không giống `hits.total`: field có thể thiếu hoặc là mảng nhiều giá trị, nên value count đếm số giá trị được index chứ không nhất thiết là số document.

Ví dụ:

```json
"aggs": {
  "sku_values": {
    "value_count": {
      "field": "sku"
    }
  }
}
```

Nếu mỗi document chỉ có một SKU, value count có thể trùng số document có SKU. Nhưng nếu field có thể thiếu hoặc chứa nhiều giá trị, hai số khác nhau.

## 8. Aggregation và phân trang hits độc lập

`from`/`size` điều khiển hits được trả về. Chúng không phân trang bucket aggregation. Ví dụ:

```json
{
  "from": 20,
  "size": 10,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 5
      }
    }
  }
}
```

Request trả hits từ offset 20, tối đa 10 document và tối đa 5 bucket category theo cấu hình terms. Hai phần có kích thước và quy tắc riêng.

Nếu cần phân trang qua tất cả bucket, dùng composite aggregation và `after_key`; không dùng `from`/`size` của hits để điều khiển bucket.

## 9. Aggregation trong Spring Data Elasticsearch

Spring Data Elasticsearch thực thi aggregation qua `ElasticsearchOperations` cùng query object, thường là `NativeQuery` khi cần DSL linh hoạt. Kết quả tìm kiếm được biểu diễn bằng `SearchHits<T>`; document hits và aggregation được truy cập riêng.

### 9.1 Khai báo aggregation với NativeQuery

Ví dụ dùng Elasticsearch Java API Client trong Spring Data Elasticsearch 5.x:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Aggregation byCategory = Aggregation.of(a -> a
    .terms(t -> t
        .field("category")
        .size(20)
    )
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withMaxResults(0)
    .withAggregation("by_category", byCategory)
    .build();
```

`withMaxResults(0)` yêu cầu không trả document hits trong những phiên bản API hỗ trợ cách thiết lập này. Có thể cấu hình page size bằng 0 theo API của phiên bản đang dùng. Tên method và cách biểu diễn zero hits có thể thay đổi giữa các phiên bản Spring Data; mục tiêu của request Elasticsearch vẫn là search-level `size: 0`.

Thực thi:

```java
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> searchHits = operations.search(query, Product.class);
```

`searchHits.getSearchHits()` chứa danh sách hit (rỗng khi size bằng 0). `searchHits.getTotalHits()` là tổng số document match theo total-hit tracking. Aggregation được lấy qua `searchHits.getAggregations()`.

### 9.2 Đọc aggregation từ SearchHits

Kiểu trả về của `getAggregations()` là `AggregationsContainer<?>`. Spring Data Elasticsearch dùng implementation tương ứng với client đang được cấu hình; với Elasticsearch Java Client, implementation phổ biến là `ElasticsearchAggregations`.

Ví dụ khung truy cập:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.AggregationsContainer;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;

SearchHits<Product> searchHits = operations.search(query, Product.class);

AggregationsContainer<?> container = searchHits.getAggregations();
if (container instanceof ElasticsearchAggregations aggregations) {
    // Lấy các aggregation đã đăng ký theo tên "by_category".
    // Cấu trúc wrapper và kiểu Aggregate cụ thể phụ thuộc phiên bản client.
    var aggregationMap = aggregations.aggregations();
}
```

Đoạn code minh họa điểm truy cập ở cấp Spring Data. Khi lấy bucket/metric cụ thể, cần dùng kiểu aggregate của Elasticsearch Java Client và tên aggregation đã đăng ký. Cấu trúc accessor của wrapper có thể thay đổi theo phiên bản; hãy kiểm tra Javadoc đúng dependency để đọc `StringTermsAggregate`, `LongTermsAggregate`, `DoubleTermsAggregate` hoặc kiểu bucket tương ứng. Không nên ép mọi aggregation về cùng một kiểu bucket vì terms trên keyword và số có thể có kiểu aggregate khác nhau.

### 9.3 Dùng Java Client để xây dựng metric aggregation

Ví dụ khai báo `avg` và `sum`:

```java
Aggregation averagePrice = Aggregation.of(a -> a
    .avg(v -> v.field("price"))
);

Aggregation totalPrice = Aggregation.of(a -> a
    .sum(v -> v.field("price"))
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withMaxResults(0)
    .withAggregation("average_price", averagePrice)
    .withAggregation("total_price", totalPrice)
    .build();
```

Sau khi thực thi, hai kết quả metric nằm trong aggregation container, không nằm trong danh sách `Product`.

### 9.4 Đọc hits và aggregation cùng lúc

Một trang tìm kiếm có thể cần cả danh sách document và facet category:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withPageable(PageRequest.of(0, 20))
    .withAggregation("by_category", byCategory)
    .build();

SearchHits<Product> result = operations.search(query, Product.class);

List<Product> products = result.getSearchHits().stream()
    .map(SearchHit::getContent)
    .toList();

long totalMatches = result.getTotalHits();
AggregationsContainer<?> aggregations = result.getAggregations();
```

`products` dùng để render danh sách. `totalMatches` dùng cho metadata kết quả nếu total-hit tracking được cấu hình phù hợp. `aggregations` dùng để tạo facet hoặc thống kê. Không cố chuyển aggregation bucket thành Product vì bucket không đại diện cho document.

### 9.5 Không dùng `SearchHits` như thể chỉ có hits

`SearchHits<T>` là wrapper của toàn bộ search response ở mức Spring Data. Ngoài danh sách `SearchHit<T>`, nó còn có total hits, max score, aggregations và metadata khác tùy phiên bản. Khi endpoint chỉ cần aggregation, có thể vẫn dùng `SearchHits<T>` nhưng cấu hình zero hits; không cần tải document về rồi bỏ đi.

## 10. Đọc bucket và metric: ví dụ về kiểu dữ liệu

Aggregation response là dữ liệu có cấu trúc riêng. Ví dụ terms aggregation:

```json
{
  "aggregations": {
    "by_category": {
      "buckets": [
        { "key": "keyboard", "doc_count": 12 },
        { "key": "mouse", "doc_count": 8 }
      ]
    }
  }
}
```

Mỗi bucket có key và document count. Nếu là terms trên số, key có thể được trả về dưới dạng số; nếu là date histogram, bucket có thể có `key` dạng epoch millis và `key_as_string`.

Metric response:

```json
{
  "aggregations": {
    "average_price": {
      "value": 152.5
    },
    "price_stats": {
      "count": 20,
      "min": 20.0,
      "max": 500.0,
      "avg": 152.5,
      "sum": 3050.0
    }
  }
}
```

Metric đơn giản thường trả `value`; metric stats trả nhiều thuộc tính. Vì vậy, code đọc kết quả phải biết aggregation nào đã khai báo và kiểu kết quả mong đợi. Tránh đọc mọi aggregation theo một cấu trúc JSON cố định.

## 11. Terms aggregation có giới hạn và độ chính xác

Terms aggregation thường trả top bucket theo document count. Nếu category có 10.000 giá trị khác nhau nhưng `size` là 10, chỉ 10 bucket hàng đầu được trả về. Điều đó không có nghĩa chỉ có 10 category tồn tại.

Response có thể chứa:

- `sum_other_doc_count`: số document thuộc các bucket không được trả về (theo semantics aggregation).
- `doc_count_error_upper_bound`: giới hạn trên của sai số đếm bucket trong một số chế độ phân phối.

Khi cần duyệt toàn bộ bucket, cân nhắc composite aggregation. Khi cần đếm số giá trị duy nhất, cardinality có thể phù hợp nhưng là xấp xỉ. Chọn loại aggregation theo yêu cầu chính xác và số lượng giá trị khác nhau.

### 11.1 Field phải phù hợp aggregation

Terms aggregation thường dùng trên `keyword`, numeric hoặc các field có thể aggregate. Field `text` thường không có doc values và không phù hợp cho terms aggregation mặc định. Nếu cần facet theo tên, hãy dùng multi-field keyword như `name.raw`.

Ví dụ mapping:

```json
"name": {
  "type": "text",
  "fields": {
    "raw": {
      "type": "keyword"
    }
  }
}
```

Aggregation theo tên dùng:

```json
"terms": {
  "field": "name.raw"
}
```

Không bật fielddata trên text chỉ để làm aggregation nếu chưa đánh giá bộ nhớ và cardinality; multi-field keyword thường là thiết kế phù hợp hơn.

## 12. Aggregation không tự động theo page hiện tại

Một lỗi dễ gặp là nghĩ aggregation chỉ tính trên document của trang hiện tại. Thực tế, top-level aggregation thường chạy trên toàn bộ document thỏa query, không chỉ `hits.hits` được trả về theo `from`/`size`.

Ví dụ:

```json
{
  "from": 40,
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
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

Hits là trang thứ ba gồm tối đa 20 sản phẩm ACTIVE. Aggregation `by_category` thống kê tất cả sản phẩm ACTIVE thỏa query, không chỉ 20 document của trang đó.

Nếu muốn aggregation chỉ trên một tập con riêng, hãy dùng filter aggregation hoặc query scope phù hợp. Đừng cố dùng `from`/`size` để giới hạn phạm vi aggregation.

## 13. Khi nào dùng aggregation thay vì lấy hits về Java?

Dùng aggregation khi cần:

- Đếm document theo category, status, brand hoặc khoảng thời gian.
- Tính tổng, trung bình, min, max hoặc thống kê trên field số.
- Tạo facet để người dùng lọc kết quả.
- Xây dựng biểu đồ doanh thu theo ngày/tháng.
- Ước lượng số giá trị duy nhất.
- Nhóm và phân tích dữ liệu ở phía Elasticsearch.

Dùng hits khi cần:

- Hiển thị nội dung từng document.
- Đọc field nghiệp vụ của từng record.
- Chỉnh sửa hoặc xử lý từng document ở ứng dụng.
- Xuất dữ liệu đầy đủ theo batch.
- Lấy highlight hoặc metadata gắn với từng hit.

Hai phần thường được dùng cùng nhau. Ví dụ trang tìm kiếm sản phẩm hiển thị 20 hit, đồng thời có facet category, brand và range giá.

Không lấy hàng triệu hits về Java chỉ để đếm hoặc tính trung bình. Ngược lại, không dùng aggregation nếu ứng dụng cần nội dung chi tiết của từng document.

## 14. Những sai lầm thường gặp

### 14.1 Nghĩ `size: 0` làm aggregation không chạy

`size: 0` chỉ tắt danh sách document hits. Aggregation vẫn được tính và trả về. Đây là cách thường dùng cho dashboard/facet chỉ cần thống kê.

### 14.2 Nhầm search `size` với terms `size`

Search-level `size` là số document hits. `terms.size` là số bucket được trả về. Chúng không ảnh hưởng lẫn nhau.

### 14.3 Nghĩ aggregation chỉ tính trên trang hiện tại

Top-level aggregation tính trên tập document thuộc query scope, không bị giới hạn bởi `from`/`size` của hits. Dùng filter aggregation nếu cần scope riêng.

### 14.4 Cộng doc_count của bucket rồi coi là hits.total

Một document có thể thuộc nhiều bucket hoặc bucket bị giới hạn. Tổng bucket count không nhất thiết bằng tổng hit.

### 14.5 Dùng terms aggregation trên field text

Field text thường không có doc values và không phù hợp cho terms aggregation mặc định. Dùng keyword sub-field hoặc thiết kế mapping phù hợp.

### 14.6 Nghĩ cardinality là phép đếm chính xác

Cardinality thường là ước lượng. Nếu cần chính xác tuyệt đối, phải chọn giải pháp khác hoặc đánh giá sai số cho nghiệp vụ.

### 14.7 Nghĩ mọi terms bucket đều được trả về

`terms.size` chỉ trả một số bucket hàng đầu. Dùng composite aggregation để phân trang qua lượng bucket lớn.

### 14.8 Đọc aggregation từ danh sách SearchHit

Aggregation nằm trong `SearchHits.getAggregations()`, không phải field của entity hoặc mỗi `SearchHit` thông thường. Hãy xử lý aggregation container riêng.

### 14.9 Dùng global aggregation mà quên phạm vi bảo mật

Global aggregation bỏ qua query scope ở cấp top-level. Nếu hệ thống có tenant hoặc quyền truy cập dữ liệu, cần bảo đảm scope bảo mật vẫn được áp dụng ở tầng phù hợp.

### 14.10 Bật track_total_hits chính xác dù không cần

Đếm chính xác tổng hits có chi phí. Nếu endpoint chỉ cần facet/metric, đặt `size: 0` và chỉ bật total tracking khi nghiệp vụ cần.

## 15. Kiểm tra aggregation trong REST response

Khi aggregation không đúng, kiểm tra lần lượt:

1. Query chính có chọn đúng tập document không.
2. Field aggregation có mapping phù hợp không (`keyword`, số, date...).
3. `size` của terms có đang giới hạn số bucket không.
4. Có `post_filter`, filter aggregation hoặc global aggregation làm thay đổi scope không.
5. Có field thiếu/null hoặc dữ liệu sai kiểu không.
6. Terms aggregation phân tán có báo sai số bucket không.
7. Cardinality có đang được dùng như số chính xác tuyệt đối không.
8. Search response có `aggregations` nhưng code Java đang đọc nhầm `hits` không.

Kiểm tra mapping:

```http
GET /products/_mapping
```

Chạy riêng aggregation không cần hits:

```http
GET /products/_search
{
  "size": 0,
  "query": {
    "match_all": {}
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
```

Đọc cả `hits.total`, `hits.hits` và `aggregations` để xác nhận từng phần đang thể hiện đúng mục đích.

## 16. Nguyên tắc thiết kế

- Dùng hits khi cần document cụ thể; dùng aggregation khi cần thống kê/nhóm.
- Kết hợp cả hai trong một request khi trang tìm kiếm cần danh sách và facet.
- Đặt search-level `size: 0` khi chỉ cần aggregation.
- Nhớ rằng `size` của hits và `size` của terms aggregation là hai cấu hình độc lập.
- Top-level aggregation thường tính trên toàn bộ tập document thỏa query, không chỉ trang hits hiện tại.
- Dùng `query`/`filter` để xác định scope chung; dùng `post_filter` khi cần lọc hits mà giữ facet rộng hơn.
- Dùng filter aggregation cho scope riêng của từng thống kê; dùng global aggregation chỉ khi thật sự muốn bỏ qua query scope.
- Chọn field mapping phù hợp cho aggregation; ưu tiên keyword sub-field thay vì fielddata trên text.
- Hiểu giới hạn top buckets, sai số terms và cardinality approximation.
- Dùng composite aggregation để duyệt nhiều bucket; không dùng `search_after` của hits cho bucket.
- Trong Spring Data, đọc hits qua `getSearchHits()` và aggregation qua `getAggregations()`.
- Không save entity được tạo từ projection/source-filtered response như document đầy đủ.
- Chỉ bật exact total-hit tracking khi ứng dụng thực sự cần.

## 17. Tổng kết

Danh sách tài liệu tìm được và aggregation là hai phần độc lập của search response. `hits.hits` chứa các document cụ thể được trả về theo `from`/`size`; `hits.total` mô tả tổng số document khớp query theo chế độ tracking; `aggregations` chứa bucket và metric được tính trên tập document trong scope tương ứng.

Aggregation không bị giới hạn bởi page hiện tại của hits. Search-level `size: 0` có thể loại bỏ danh sách document nhưng vẫn trả đầy đủ aggregation. Ngược lại, `terms.size` giới hạn số bucket được trả về chứ không phải số document. Query/filter, post_filter, filter aggregation và global aggregation quyết định phạm vi document được thống kê. Terms, range, date histogram, metric, cardinality và composite aggregation phục vụ các dạng thống kê khác nhau, mỗi loại có giới hạn về mapping, số bucket hoặc độ chính xác.

Trong Spring Data Elasticsearch, `ElasticsearchOperations.search(...)` trả `SearchHits<T>`; danh sách document được đọc qua `getSearchHits()`, còn aggregation được đọc riêng qua `getAggregations()`. Hãy dùng hits để hiển thị/xử lý document và aggregation để thống kê/facet. Tách hai mục đích này giúp giảm dữ liệu truyền về ứng dụng, tận dụng khả năng tính toán của Elasticsearch và tránh nhầm bucket với document.

## Tài liệu tham khảo

- [Elasticsearch — Aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html)
- [Elasticsearch — Terms aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-terms-aggregation.html)
- [Elasticsearch — Metric aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-metrics.html)
- [Elasticsearch — Composite aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-composite-aggregation.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Spring Data Elasticsearch Reference — Search Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
