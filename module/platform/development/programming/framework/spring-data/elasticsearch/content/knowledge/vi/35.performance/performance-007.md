# Giảm chi phí aggregation, đếm tổng và phân trang sâu

## 1. Vì sao tìm kiếm có thể tốn kém dù chỉ trả về vài document?

Một request Elasticsearch có thể trả về 20 document nhưng phải xử lý hàng triệu document phù hợp với query. Phần dữ liệu trả về nhỏ không đồng nghĩa với công việc tìm kiếm nhỏ.

Một request thường có nhiều phần việc: tìm các document khớp query, đếm tổng số document khớp, tính aggregation trên tập document khớp, sắp xếp kết quả, bỏ qua các hit của những trang trước, đọc và serialize dữ liệu để trả về ứng dụng.

Ví dụ giao diện danh sách sản phẩm hiển thị 20 sản phẩm, đồng thời yêu cầu tổng số sản phẩm, số sản phẩm theo từng danh mục, giá trung bình theo thương hiệu, tổng số thương hiệu duy nhất và trang thứ 500 của kết quả tìm kiếm.

Dù response chỉ chứa 20 sản phẩm, Elasticsearch vẫn có thể phải duyệt một tập document rất lớn để tính count và aggregation, đồng thời giữ lại nhiều hit trung gian để phục vụ phân trang sâu.

Muốn giảm chi phí, trước hết cần xác định ứng dụng thực sự cần loại kết quả nào:

1. Cần danh sách document hay chỉ cần một con số?
2. Cần tổng chính xác hay ước lượng?
3. Cần top bucket hay phải duyệt mọi bucket?
4. Người dùng cần nhảy đến trang bất kỳ hay chỉ cần đi tiếp?
5. Có cần giữ một snapshot ổn định khi dữ liệu đang thay đổi không?

Các lựa chọn như Count API, `track_total_hits`, composite aggregation, `search_after` và Point in Time (PIT) giải quyết những nhu cầu khác nhau. Không có một tham số duy nhất làm mọi loại query nhanh hơn.

## 2. Phân biệt đếm document, đếm giá trị và đếm bucket

Trước khi tối ưu, cần hiểu các con số trong response có ý nghĩa gì.

| Loại số liệu | Câu hỏi | Cơ chế thường dùng |
|---|---|---|
| Total hits | Có bao nhiêu document khớp query? | `hits.total`, Count API |
| Value count | Có bao nhiêu giá trị của một field? | `value_count` aggregation |
| Bucket `doc_count` | Có bao nhiêu document thuộc bucket? | `terms`, `filters`, `date_histogram` |
| Cardinality | Có bao nhiêu giá trị duy nhất? | `cardinality` aggregation |
| Tổng hoặc trung bình | Tổng/giá trị trung bình của field là bao nhiêu? | `sum`, `avg` aggregation |

Các số liệu này không thể thay thế cho nhau.

Ví dụ có ba document:

~~~json
[
  {
    "id": "p-1",
    "tags": ["audio", "sale"]
  },
  {
    "id": "p-2",
    "tags": ["audio"]
  },
  {
    "id": "p-3",
    "tags": ["sale", "new"]
  }
]
~~~

Có ba document, nhưng có năm lần xuất hiện của tag. Cardinality của tag là ba vì có ba giá trị khác nhau: `audio`, `sale`, `new`.

Nếu chạy terms aggregation theo `tags`, tổng các `doc_count` có thể lớn hơn total hits vì một document có thể thuộc nhiều bucket.

Khi thiết kế dashboard, cần đặt tên metric theo đúng ý nghĩa. Ví dụ `totalProducts`, `tagAssignments` và `uniqueTags` là ba số liệu khác nhau.

## 3. Khi nào nên dùng Count API?

Nếu ứng dụng chỉ cần biết có bao nhiêu document khớp một điều kiện, hãy cân nhắc Count API thay vì Search API.

Ví dụ Search API chỉ để lấy tổng:

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "size": 0,
  "track_total_hits": true
}
~~~

Request này không trả hit nhưng vẫn dùng Search API để tính tổng số hit chính xác.

Có thể dùng Count API:

~~~http
GET /products/_count
{
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Response có dạng:

~~~json
{
  "count": 125430,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  }
}
~~~

Count API chỉ trả số lượng document khớp query. Nó không trả danh sách hit, sort, highlight hoặc aggregation.

### Lợi ích của Count API

- Request thể hiện rõ mục đích chỉ đếm.
- Không cần xây dựng response hit.
- Không phải trả source hoặc sort values của document.
- Phù hợp với endpoint thống kê tổng đơn giản.

Count API vẫn phải xác định số document phù hợp trên các shard. Nó không làm cho một query phức tạp hoặc một tập dữ liệu rất lớn trở nên miễn phí. Các điều kiện query, mapping, shard layout và filter vẫn ảnh hưởng đến chi phí.

### Khi nào không dùng Count API?

Nếu cùng request cần vừa danh sách sản phẩm vừa aggregation, dùng Search API để tránh gửi nhiều request độc lập không cần thiết.

Nếu chỉ cần top danh mục và không cần tổng document, dùng Search API với `size: 0` và aggregation, có thể tắt theo dõi total hits.

## 4. Spring Data Elasticsearch: đếm bằng ElasticsearchOperations

Spring Data Elasticsearch cung cấp phương thức `count` trên `ElasticsearchOperations`.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public long countAudioProducts() {
        CriteriaQuery query = new CriteriaQuery(
            Criteria.where("category").is("audio")
        );

        return operations.count(query, Product.class);
    }
}
~~~

`operations.count(query, Product.class)` thực hiện thao tác đếm theo query và mapping của entity. Khi chỉ cần một con số, đây là API rõ ràng hơn việc chạy search rồi lấy `SearchHits.getTotalHits()`.

Có thể dùng query phức tạp hơn:

~~~java
Criteria criteria = new Criteria("category").is("audio")
    .and("active").is(true);

CriteriaQuery query = new CriteriaQuery(criteria);

long count = operations.count(query, Product.class);
~~~

Với query không cần Criteria API, có thể dùng `StringQuery` hoặc query implementation khác mà Spring Data hỗ trợ.

Không nên gọi Count API riêng cho từng widget trên dashboard nếu nhiều metric có thể được tính trong một request aggregation. Hãy cân nhắc gộp những số liệu có cùng tập document đầu vào.

## 5. track_total_hits và chi phí đếm tổng trong Search API

Search API có thể trả tổng số document khớp trong `hits.total`. Việc theo dõi tổng chính xác có thể làm tăng chi phí query.

Tham số `track_total_hits` điều khiển mức độ đếm:

| Giá trị | Hành vi |
|---|---|
| `true` | Theo dõi tổng số hit chính xác |
| `false` | Không yêu cầu tính total hits |
| Số nguyên `N` | Theo dõi chính xác đến ngưỡng N; khi vượt ngưỡng, kết quả có thể chỉ là cận dưới |

Elasticsearch mặc định theo dõi chính xác đến ngưỡng 10.000 hit. Khi vượt ngưỡng, response có thể có quan hệ `gte` thay vì `eq`.

Ví dụ:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    }
  }
}
~~~

`gte` có nghĩa là có ít nhất 10.000 hit; con số không phải tổng chính xác.

### Không cần tổng thì tắt tracking

Ví dụ request chỉ cần lấy danh sách kết quả:

~~~http
GET /products/_search
{
  "track_total_hits": false,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "size": 20,
  "sort": [
    {
      "createdAt": "desc"
    }
  ]
}
~~~

Ứng dụng vẫn nhận các hit phù hợp nhưng không yêu cầu Elasticsearch tính total hits.

Đây là lựa chọn hữu ích cho autocomplete, trang tìm kiếm chỉ cần biết còn kết quả tiếp theo hay không, feed hoặc timeline, API cursor-based và các truy vấn mà con số tổng không được hiển thị.

### Chỉ cần tổng đến một ngưỡng

Ví dụ giao diện chỉ hiển thị `10.000+ kết quả`, không cần biết chính xác là 12.345 hay 1.200.000:

~~~http
GET /products/_search
{
  "track_total_hits": 10000,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "size": 20
}
~~~

Khi số hit không vượt ngưỡng, Elasticsearch có thể trả tổng chính xác. Khi vượt ngưỡng, ứng dụng cần đọc `relation` để biết đó chỉ là cận dưới.

Không nên chỉ đọc `value` rồi luôn hiển thị nó như một con số chính xác.

### Khi nào bắt buộc phải đếm chính xác?

Một số nghiệp vụ cần tổng chính xác, ví dụ báo cáo đối soát hoặc thống kê được cam kết với người dùng. Khi đó có thể dùng `track_total_hits: true` hoặc Count API.

Cần nhớ rằng đếm chính xác trên tập dữ liệu lớn có chi phí. Nếu một màn hình cần tổng chính xác ở mọi lần người dùng đổi filter, hãy cân nhắc cache, pre-aggregation hoặc một read model thống kê riêng.

## 6. size: 0 không làm aggregation miễn phí

Khi chỉ cần aggregation, có thể đặt `size: 0`:

~~~http
GET /products/_search
{
  "size": 0,
  "track_total_hits": false,
  "query": {
    "term": {
      "active": true
    }
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
~~~

`size: 0` có nghĩa là không trả document hits. Nó giảm chi phí fetch và serialize source, nhưng Elasticsearch vẫn phải tìm document phù hợp và tính aggregation.

Nếu aggregation có hàng triệu giá trị khác nhau, `size: 0` không loại bỏ chi phí tạo bucket.

Khi chỉ cần aggregation, kết hợp `size: 0`, `track_total_hits: false` nếu không cần tổng chính xác, query filter để giới hạn tập dữ liệu và aggregation phù hợp với cardinality và nhu cầu hiển thị.

Không nhầm `size` của search hits với `size` của terms aggregation. Chúng điều khiển hai phần kết quả khác nhau.

## 7. Giảm chi phí bằng filter trước aggregation

Aggregation thường tính trên tập document khớp query. Vì vậy, giới hạn tập đầu vào là một trong những cách trực tiếp để giảm chi phí.

Ví dụ dashboard chỉ thống kê sản phẩm đang hoạt động trong một khoảng thời gian:

~~~http
GET /products/_search
{
  "size": 0,
  "track_total_hits": false,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "2026-01-01T00:00:00Z",
              "lt": "2027-01-01T00:00:00Z"
            }
          }
        }
      ]
    }
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
~~~

Các điều kiện trong `bool.filter` không cần tính relevance score. Chúng phù hợp cho điều kiện trạng thái, tenant, ngày tháng và quyền truy cập.

Nếu ứng dụng có tenant ID, hãy áp dụng tenant filter trước aggregation. Không để aggregation quét dữ liệu của mọi tenant rồi mới lọc kết quả ở Java.

### Query filter và filter aggregation khác nhau

Top-level query giới hạn tập document được dùng cho toàn bộ search, gồm hits và aggregation.

Filter aggregation tạo một phạm vi con bên trong aggregation tree:

~~~json
{
  "size": 0,
  "query": {
    "term": {
      "tenantId": "tenant-7"
    }
  },
  "aggs": {
    "active_products": {
      "filter": {
        "term": {
          "active": true
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
  }
}
~~~

Trong ví dụ, mọi aggregation đều chỉ thấy document của tenant 7; aggregation `active_products` tiếp tục giới hạn vào sản phẩm active.

Nếu tất cả aggregation đều cần cùng một điều kiện, top-level query thường rõ ràng và hiệu quả hơn việc bọc từng aggregation bằng một filter giống nhau.

### Lưu ý về post_filter

`post_filter` chỉ lọc hits sau khi aggregation đã được tính. Nếu dùng nó cho điều kiện mà bạn nghĩ sẽ giảm tập document đầu vào của aggregation, kết quả có thể vẫn chứa số liệu của tập rộng hơn.

Ví dụ giao diện faceted search có thể cố ý dùng post_filter để giữ nguyên facet counts khi người dùng chọn một facet. Đây là hành vi có chủ đích, nhưng không phải cách tối ưu nếu mục tiêu là giảm chi phí aggregation.

## 8. Chọn đúng field type cho aggregation

Aggregation thường cần đọc giá trị field qua doc values. Vì vậy, mapping có ảnh hưởng trực tiếp đến hiệu năng.

Các field thường phù hợp:

- `keyword` cho danh mục, mã, trạng thái và tên chuẩn hóa.
- `long`, `integer`, `double` cho số.
- `date` cho histogram theo thời gian.
- `boolean` cho cờ trạng thái.

Không nên chạy terms aggregation trực tiếp trên field `text` được phân tích nếu không có lý do rõ ràng. Thường nên khai báo multi-field:

~~~json
{
  "mappings": {
    "properties": {
      "brand": {
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

Aggregation dùng `brand.keyword`:

~~~json
{
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand.keyword",
        "size": 20
      }
    }
  }
}
~~~

Field `text` lưu token đã phân tích để phục vụ full-text search. Field `keyword` lưu giá trị nguyên vẹn, phù hợp cho grouping, sorting và terms aggregation.

Bật `fielddata` trên text có thể tiêu thụ nhiều heap. Chỉ làm vậy sau khi hiểu rõ chi phí và có lý do đặc biệt; trong phần lớn trường hợp, multi-field keyword là lựa chọn phù hợp hơn.

## 9. Terms aggregation: giới hạn số bucket cần trả về

Terms aggregation thường dùng để lấy top danh mục, thương hiệu hoặc trạng thái.

Ví dụ:

~~~http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand.keyword",
        "size": 10
      }
    }
  }
}
~~~

`size: 10` giới hạn số bucket trả về ở mức 10. Nếu field có hàng triệu giá trị duy nhất, request vẫn có thể cần xử lý nhiều giá trị để tìm top 10, nhưng response và phần reduce sẽ nhỏ hơn so với yêu cầu tất cả bucket.

Không đặt `size` quá lớn chỉ để lấy mọi giá trị. Nếu cần duyệt toàn bộ danh sách bucket, hãy xem composite aggregation.

### shard_size và độ chính xác

Terms aggregation chạy phân tán. Mỗi shard gửi một tập ứng viên bucket về coordinating node để reduce thành top buckets toàn cục.

`shard_size` điều khiển số bucket ứng viên mỗi shard gửi lên. Giá trị lớn hơn có thể cải thiện độ chính xác của top terms nhưng làm tăng bộ nhớ trên shard và coordinating node, dữ liệu truyền giữa các node, công việc reduce và kích thước response trung gian.

Ví dụ:

~~~json
{
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand.keyword",
        "size": 10,
        "shard_size": 50,
        "show_term_doc_count_error": true
      }
    }
  }
}
~~~

`show_term_doc_count_error` giúp trả thông tin sai số của `doc_count` trong những trường hợp Elasticsearch có thể tính được cận sai số.

Response có thể chứa `doc_count_error_upper_bound`, cận trên của sai số đếm, và `sum_other_doc_count`, số document count nằm trong các bucket không được trả về, với semantics của aggregation.

Đây là thông tin hữu ích khi top terms được dùng cho báo cáo. Không nên mặc định `doc_count` của distributed terms aggregation luôn chính xác tuyệt đối trong mọi cấu hình.

### Không sắp xếp terms theo _count tăng dần nếu cần kết quả chính xác

Sắp xếp terms theo số lượng tăng dần (`_count: asc`) có thể cho kết quả không chính xác trong môi trường nhiều shard. Nếu cần top ít phổ biến, hãy cân nhắc thiết kế khác, chẳng hạn composite để duyệt bucket rồi xử lý ở tầng ứng dụng, hoặc duy trì thống kê phù hợp với nghiệp vụ.

## 10. Composite aggregation để duyệt mọi bucket

Nếu cần lấy tất cả bucket của một field có cardinality cao, terms aggregation với `size` rất lớn không phải cách phù hợp.

Composite aggregation cho phép phân trang bucket bằng `after` key.

Ví dụ:

~~~http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "products_by_brand": {
      "composite": {
        "size": 500,
        "sources": [
          {
            "brand": {
              "terms": {
                "field": "brand.keyword"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Response trả về các bucket cùng `after_key` nếu còn dữ liệu. Request tiếp theo truyền `after`:

~~~http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "products_by_brand": {
      "composite": {
        "size": 500,
        "after": {
          "brand": "Brand Z"
        },
        "sources": [
          {
            "brand": {
              "terms": {
                "field": "brand.keyword"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Giá trị `after` phải được lấy từ `after_key` của response trước. Không tự tạo nó từ bucket cuối cùng nếu Elasticsearch đã trả `after_key` riêng.

Luồng xử lý:

~~~text
Request composite page 1
          |
          v
   500 buckets + after_key
          |
          v
Request page 2 với after_key
          |
          v
   500 buckets + after_key
          |
          v
       ...
          |
          v
      Hết bucket
~~~

Composite aggregation phù hợp cho export hoặc xử lý tuần tự mọi bucket. Nó không phải công cụ để lấy top 10 bucket phổ biến nhất; dùng terms aggregation cho top-N.

Nếu dữ liệu thay đổi trong khi phân trang bucket, kết quả có thể thay đổi giữa các request. Khi cần snapshot ổn định, hãy đánh giá việc kết hợp PIT theo khả năng của phiên bản Elasticsearch và kiểu aggregation đang dùng.

## 11. Cardinality aggregation là ước lượng

Khi cần đếm số giá trị duy nhất, ví dụ số khách hàng duy nhất, có thể dùng cardinality aggregation:

~~~http
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "unique_customers": {
      "cardinality": {
        "field": "customerId"
      }
    }
  }
}
~~~

Cardinality sử dụng thuật toán HyperLogLog++ để ước lượng số lượng giá trị duy nhất. Nó thường dùng ít bộ nhớ hơn cách tạo một bucket cho từng giá trị, nhưng kết quả là ước lượng và có thể sai số.

Không dùng cardinality nếu nghiệp vụ bắt buộc một con số chính xác tuyệt đối.

### precision_threshold

Có thể điều chỉnh ngưỡng độ chính xác:

~~~json
{
  "aggs": {
    "unique_customers": {
      "cardinality": {
        "field": "customerId",
        "precision_threshold": 10000
      }
    }
  }
}
~~~

Giá trị `precision_threshold` cao hơn thường cải thiện độ chính xác ở cardinality thấp và trung bình, nhưng tăng mức sử dụng bộ nhớ. Elasticsearch hỗ trợ giá trị tối đa 40.000; mặc định là 3.000.

Đây là ngưỡng điều chỉnh độ chính xác, không phải giới hạn cứng số lượng giá trị duy nhất. Cardinality lớn hơn ngưỡng vẫn được ước lượng.

Nếu cần exact distinct count trên tập dữ liệu rất lớn, hãy cân nhắc một bảng thống kê hoặc read model riêng, một quy trình tính trước theo batch, một khóa duy nhất đã được chuẩn hóa để đếm theo cách phù hợp, hoặc chấp nhận chi phí cao hơn nếu yêu cầu nghiệp vụ thật sự cần chính xác.

Không thay cardinality bằng terms aggregation có `size` khổng lồ nếu mục tiêu chỉ là một con số unique.

## 12. Aggregation nhiều tầng và bucket explosion

Một aggregation tree có thể tạo số lượng bucket tăng rất nhanh.

Ví dụ:

~~~json
{
  "aggs": {
    "by_country": {
      "terms": {
        "field": "country",
        "size": 100
      },
      "aggs": {
        "by_city": {
          "terms": {
            "field": "city.keyword",
            "size": 100
          },
          "aggs": {
            "by_category": {
              "terms": {
                "field": "category",
                "size": 50
              }
            }
          }
        }
      }
    }
  }
}
~~~

Trong trường hợp tối đa, cây này có thể tạo ra hàng trăm nghìn bucket. Mỗi bucket có thể mang sub-aggregation riêng. Chi phí bộ nhớ và reduce tăng theo số bucket và độ sâu.

Một số cách giảm:

- Giảm `size` của từng tầng.
- Dùng filter để giới hạn phạm vi.
- Chỉ tính sub-aggregation cho bucket thật sự cần.
- Dùng composite khi cần duyệt mọi tổ hợp.
- Tránh lồng nhiều terms aggregation cardinality cao.
- Không gửi nhiều aggregation trùng lặp trên cùng field nếu có thể tái sử dụng kết quả.

Elasticsearch có giới hạn `search.max_buckets` để bảo vệ cluster trước response có quá nhiều bucket. Tăng giới hạn chỉ để request chạy được có thể làm tăng nguy cơ dùng hết heap. Hãy giảm số bucket hoặc đổi chiến lược trước.

## 13. value_count, sum, avg, min và max

Nếu chỉ cần một metric trên field, hãy dùng metric aggregation tương ứng thay vì tạo bucket.

Ví dụ:

~~~http
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "total_amount": {
      "sum": {
        "field": "amount"
      }
    },
    "average_amount": {
      "avg": {
        "field": "amount"
      }
    },
    "minimum_amount": {
      "min": {
        "field": "amount"
      }
    },
    "maximum_amount": {
      "max": {
        "field": "amount"
      }
    },
    "amount_values": {
      "value_count": {
        "field": "amount"
      }
    }
  }
}
~~~

Ý nghĩa:

- `sum`: tổng các giá trị.
- `avg`: trung bình.
- `min`: giá trị nhỏ nhất.
- `max`: giá trị lớn nhất.
- `value_count`: số giá trị của field, không phải luôn là số document.

Nếu field đa trị, một document có thể đóng góp nhiều giá trị vào `value_count`. Nếu cần đếm document có field tồn tại, hãy xác định rõ semantics và dùng một cách đếm document phù hợp.

## 14. Nested aggregation và ý nghĩa của doc_count

Với mapping `nested`, một document cha có thể chứa nhiều nested document. Nested aggregation đếm nested document trong phạm vi nested path, không nhất thiết đếm document cha.

Ví dụ một order có ba line items. Nested aggregation theo `items` có thể có `doc_count = 3`, trong khi chỉ có một order.

Nếu cần quay lại đếm document cha, dùng `reverse_nested` aggregation.

~~~json
{
  "aggs": {
    "items": {
      "nested": {
        "path": "items"
      },
      "aggs": {
        "by_sku": {
          "terms": {
            "field": "items.sku"
          },
          "aggs": {
            "parent_orders": {
              "reverse_nested": {}
            }
          }
        }
      }
    }
  }
}
~~~

Khi đọc dashboard, hãy kiểm tra aggregation đang đếm root document, nested document hay giá trị field. Sai semantics có thể tạo ra con số có vẻ hợp lý nhưng không phản ánh đúng nghiệp vụ.

## 15. Giảm chi phí script và runtime field trong aggregation

Aggregation trên field đã có doc values thường hiệu quả hơn việc tính một biểu thức phức tạp cho từng document.

Ví dụ runtime field:

~~~json
{
  "runtime_mappings": {
    "netAmount": {
      "type": "double",
      "script": {
        "source": "emit(doc['grossAmount'].value - doc['discount'].value)"
      }
    }
  },
  "aggs": {
    "average_net_amount": {
      "avg": {
        "field": "netAmount"
      }
    }
  }
}
~~~

Runtime field tiện khi cần thay đổi logic mà không reindex. Tuy nhiên, nếu aggregation chạy thường xuyên trên hàng triệu document, script có thể trở thành chi phí đáng kể.

Nếu giá trị tính toán ổn định và được dùng nhiều lần:

1. Tính giá trị ở ứng dụng hoặc ingest pipeline.
2. Lưu vào field numeric/keyword phù hợp.
3. Index field để có doc values.
4. Dùng metric hoặc bucket aggregation trực tiếp.

Đây là trade-off giữa linh hoạt schema và chi phí query time. Không phải mọi runtime field đều chậm, nhưng cần đo trên dữ liệu thật trước khi dùng trong dashboard có tần suất cao.

## 16. Global ordinals và terms aggregation

Terms aggregation trên field `keyword` thường tận dụng global ordinals để nhóm các giá trị. Global ordinals giúp map term thành ordinal chung cho shard, nhưng việc xây dựng chúng có thể tốn bộ nhớ và thời gian sau refresh.

Với field được aggregation thường xuyên, có thể cân nhắc:

~~~json
{
  "mappings": {
    "properties": {
      "brand": {
        "type": "keyword",
        "eager_global_ordinals": true
      }
    }
  }
}
~~~

`eager_global_ordinals: true` yêu cầu xây global ordinals trong quá trình refresh thay vì đợi query đầu tiên cần dùng. Điều này có thể giảm latency của query đầu tiên nhưng chuyển chi phí sang refresh và tăng tài nguyên.

Nó không làm mất chi phí xây ordinal. Nếu dữ liệu thay đổi liên tục, eager global ordinals có thể làm refresh tốn kém hơn.

Chỉ bật khi field có cardinality và tần suất aggregation phù hợp, query latency quan trọng hơn refresh latency, heap và refresh load đã được đo, và có nhiều aggregation lặp lại trên cùng field.

## 17. Phân trang nông với from và size

Cách phân trang quen thuộc:

~~~http
GET /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    }
  ]
}
~~~

Trang tiếp theo:

~~~http
GET /products/_search
{
  "from": 20,
  "size": 20,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    }
  ]
}
~~~

Đây là cách phù hợp cho những trang đầu. Tuy nhiên, `from` và `size` có chi phí tăng theo độ sâu.

Khi yêu cầu `from: 9900` và `size: 100`, mỗi shard có thể phải thu thập và giữ nhiều hit hơn số hit cuối cùng trả về. Coordinating node cũng cần reduce tập kết quả trung gian.

Tổng số hit cần xét tăng theo:

\[
from + size
\]

Ví dụ:

| Trang | from | size | Tổng hit cần xét |
|---:|---:|---:|---:|
| 1 | 0 | 20 | 20 |
| 10 | 180 | 20 | 200 |
| 100 | 1.980 | 20 | 2.000 |
| 500 | 9.980 | 20 | 10.000 |
| 1.000 | 19.980 | 20 | 20.000 |

Độ sâu càng lớn, chi phí càng tăng.

### index.max_result_window

Elasticsearch mặc định giới hạn tổng `from + size` ở 10.000 qua setting `index.max_result_window`.

Nếu request vượt giới hạn, Elasticsearch trả lỗi thay vì cho phép phân trang sâu không kiểm soát.

Không nên tăng giới hạn lên hàng trăm nghìn chỉ để hỗ trợ nút “Trang cuối”. Điều đó có thể làm tăng memory và CPU trên cluster. Hãy cân nhắc cursor-based pagination hoặc một luồng export riêng.

## 18. Vì sao phân trang sâu dễ bị trùng hoặc thiếu document?

Ngay cả khi tăng `max_result_window`, phân trang bằng offset có thể gặp vấn đề khi dữ liệu thay đổi giữa hai request.

Ví dụ:

1. Request trang 1 trả 20 document.
2. Một document mới được thêm vào đầu danh sách.
3. Request trang 2 dùng `from: 20`.
4. Vị trí của các document đã dịch chuyển.
5. Người dùng có thể thấy document trùng hoặc bỏ sót.

Nếu sort field không duy nhất, thứ tự giữa các document có cùng giá trị sort cũng có thể không ổn định.

Vì vậy, phân trang cần cả hai điều kiện: cách duyệt không phải bỏ qua một lượng lớn kết quả trước đó và thứ tự cần ổn định trong phạm vi duyệt.

`search_after` và PIT được thiết kế để giải quyết các vấn đề này.

## 19. Dùng search_after thay cho from/size

`search_after` dùng sort values của hit cuối cùng trong trang trước để yêu cầu trang tiếp theo.

Ví dụ request đầu:

~~~http
GET /products/_search
{
  "size": 20,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    },
    {
      "productSortId": "asc"
    }
  ]
}
~~~

Giả sử hit cuối cùng trả về có sort values:

~~~json
[
  "2026-10-15T09:30:00.000Z",
  "product-120"
]
~~~

Request tiếp theo truyền đúng mảng sort values đó:

~~~http
GET /products/_search
{
  "size": 20,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    },
    {
      "productSortId": "asc"
    }
  ],
  "search_after": [
    "2026-10-15T09:30:00.000Z",
    "product-120"
  ]
}
~~~

Elasticsearch tiếp tục sau vị trí của hit cuối cùng. Không cần yêu cầu và bỏ qua tất cả hit ở những trang trước.

### Sort phải có tie-breaker

Nếu nhiều document có cùng `createdAt`, chỉ sort theo thời gian có thể không tạo thứ tự duy nhất.

Hãy thêm một field duy nhất và có doc values, ví dụ `productSortId` kiểu keyword:

~~~json
{
  "mappings": {
    "properties": {
      "createdAt": {
        "type": "date"
      },
      "productSortId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Không nên dựa vào `_id` làm sort field tùy tiện vì `_id` không được thiết kế để sort qua doc values như một field thông thường. Có thể copy ID vào một field keyword riêng khi index.

Thứ tự sort, query và các tham số liên quan phải được giữ nguyên giữa các trang. `search_after` không phải offset và không dùng `from` để nhảy tới một trang bất kỳ.

## 20. Point in Time (PIT) để giữ snapshot ổn định

`search_after` một mình không giữ snapshot dữ liệu. Nếu document được thêm, xóa hoặc cập nhật trong khi người dùng đang duyệt, thứ tự và tập kết quả có thể thay đổi.

Point in Time (PIT) tạo một view nhất quán của index trong một khoảng thời gian. Kết hợp PIT với `search_after` là cách phù hợp cho phân trang sâu cần tính ổn định.

### Mở PIT

~~~http
POST /products/_pit?keep_alive=2m
~~~

Response trả về một PIT ID.

### Search trang đầu trong PIT

~~~http
GET /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID_FROM_RESPONSE",
    "keep_alive": "2m"
  },
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    },
    {
      "productSortId": "asc"
    }
  ]
}
~~~

### Search trang tiếp theo

Dùng sort values của hit cuối cùng trong trang trước:

~~~http
GET /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID_FROM_RESPONSE",
    "keep_alive": "2m"
  },
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    },
    {
      "productSortId": "asc"
    }
  ],
  "search_after": [
    "2026-10-15T09:30:00.000Z",
    "product-120"
  ]
}
~~~

Trong một số phiên bản hoặc tình huống, response có thể trả PIT ID mới. Ứng dụng cần dùng ID mới nhất được trả về cho request tiếp theo.

PIT `keep_alive` là thời gian Elasticsearch giữ search context kể từ request, không phải thời gian sống cố định bất kể hoạt động. Mỗi request tiếp theo có thể gia hạn thời gian giữ PIT.

### Đóng PIT

Khi người dùng kết thúc duyệt hoặc export hoàn tất:

~~~http
DELETE /_pit
{
  "id": "LATEST_PIT_ID"
}
~~~

Đóng PIT giúp giải phóng tài nguyên search context sớm.

### PIT và tie-breaker

Khi dùng PIT, Elasticsearch có thể bổ sung `_shard_doc` làm tie-breaker nội bộ nếu sort không có tie-breaker riêng. Ứng dụng vẫn phải giữ nguyên toàn bộ sort values được trả về và gửi lại chính xác trong `search_after`.

Một unique keyword field tường minh có thể hữu ích khi cần kiểm soát thứ tự nghiệp vụ. `_shard_doc` phù hợp cho duyệt snapshot, nhưng thứ tự của nó không phải thứ tự nghiệp vụ ổn định giữa các lần mở PIT khác nhau.

## 21. Khi nào nên dùng Scroll?

Scroll API được thiết kế cho việc duyệt một tập kết quả lớn theo từng batch, ví dụ export hàng triệu document, di chuyển dữ liệu, batch processing, reindex hoặc xử lý offline.

Scroll giữ search context trong một khoảng thời gian và trả một scroll ID cho lần lấy batch tiếp theo.

Ví dụ mở scroll:

~~~http
GET /products/_search?scroll=1m
{
  "size": 1000,
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

Lấy batch tiếp theo:

~~~http
POST /_search/scroll
{
  "scroll": "1m",
  "scroll_id": "SCROLL_ID_FROM_RESPONSE"
}
~~~

Khi hoàn tất, xóa context:

~~~http
DELETE /_search/scroll
{
  "scroll_id": ["SCROLL_ID_FROM_RESPONSE"]
}
~~~

Scroll phù hợp cho xử lý tuần tự lớn, nhưng không phải lựa chọn tốt cho phân trang tương tác của người dùng. Với UI cần đi qua các trang, `search_after` + PIT thường phù hợp hơn.

Không giữ scroll context lâu hơn cần thiết. Một số lượng lớn scroll đang mở có thể tiêu thụ tài nguyên của cluster.

## 22. Chọn chiến lược phân trang

| Nhu cầu | Lựa chọn |
|---|---|
| Trang đầu và vài trang tiếp theo | `from` + `size` |
| Người dùng cần nhảy đến trang số bất kỳ | `from` + `size`, trong giới hạn hợp lý |
| Duyệt hàng chục nghìn hoặc hàng triệu hit tuần tự | `search_after` |
| Duyệt ổn định trong khi dữ liệu có thể thay đổi | PIT + `search_after` |
| Export/batch scan dữ liệu lớn | Scroll hoặc PIT + `search_after` |
| Tìm tất cả bucket aggregation | Composite aggregation với `after_key` |

Không nên chọn `search_after` chỉ vì nó mới hơn. Nếu UI chỉ có 5 trang kết quả, `from` + `size` đơn giản và phù hợp.

Nếu UI có nút “Trang cuối” hoặc cho phép nhập số trang rất sâu, cần cân nhắc lại thiết kế sản phẩm. Cursor-based pagination không hỗ trợ nhảy trực tiếp đến trang 50.000 nếu chưa duyệt các trang trước để lấy cursor.

## 23. Spring Data Elasticsearch: phân trang nông bằng Pageable

Spring Data Elasticsearch hỗ trợ `Pageable` để biểu diễn page number và page size.

Ví dụ:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.NativeQuery;

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .term(t -> t
            .field("category")
            .value("audio")
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

`PageRequest.of(0, 20)` yêu cầu trang đầu với 20 kết quả. Trang tiếp theo có thể dùng `PageRequest.of(1, 20)`.

Đây là cách phù hợp cho phân trang nông. Khi page number lớn, offset tăng và chi phí cũng tăng như cơ chế `from` + `size` của Elasticsearch.

Không tăng `index.max_result_window` chỉ để làm `PageRequest.of(10000, 20)` hoạt động. Hãy dùng cursor-based pagination nếu người dùng cần duyệt sâu.

## 24. Spring Data Elasticsearch: giảm chi phí total hits

Với `NativeQuery`, có thể cấu hình việc theo dõi total hits. API builder của Spring Data Elasticsearch hiện hành cung cấp `withTrackTotalHits(...)`:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.NativeQuery;

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .matchAll(m -> m)
    )
    .withPageable(PageRequest.of(0, 20))
    .withTrackTotalHits(false)
    .build();

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

Khi không cần tổng chính xác, tắt tracking giúp Elasticsearch tránh phần việc đếm total hits không cần thiết.

Nếu ứng dụng chuyển `SearchHits` thành `Page`, hãy kiểm tra semantics mà API trả về. `Page` thường biểu diễn total elements và total pages; nếu total hits chỉ là cận dưới hoặc không được theo dõi, không nên hiển thị nó như tổng chính xác.

### Page, Slice và SearchHits

| Kiểu kết quả | Thông tin | Khi phù hợp |
|---|---|---|
| `Page<T>` | Nội dung, pageable, tổng phần tử và tổng trang | UI thực sự cần tổng chính xác |
| `Slice<T>` | Nội dung và thông tin còn trang tiếp theo | UI chỉ cần Next/Previous |
| `SearchHits<T>` | SearchHit metadata, total hits, sort values và aggregation container | Cần kiểm soát kết quả Elasticsearch |
| `List<T>` | Chỉ nội dung entity | API không cần metadata phân trang |

Khả năng hỗ trợ trực tiếp `Slice` phụ thuộc loại repository query và phiên bản Spring Data. Nếu cần cursor pagination, một custom service trả về DTO chứa danh sách hit và cursor kế tiếp thường rõ ràng hơn việc cố biểu diễn cursor bằng `Page`.

### Tránh đếm tổng khi chỉ cần biết còn trang tiếp theo

Một cách phổ biến là lấy `pageSize + 1` hit:

1. Yêu cầu 21 hit khi kích thước trang là 20.
2. Nếu nhận đủ 21, có trang tiếp theo.
3. Trả 20 hit đầu tiên.
4. Không cần total hits chính xác.

Với cursor pagination, cũng có thể yêu cầu một hit dư để xác định `hasNext`. Đây là cách giảm chi phí cho feed hoặc API cuộn vô hạn.

## 25. Spring Data Elasticsearch: đọc aggregation từ SearchHits

Spring Data Elasticsearch có thể gửi aggregation qua `NativeQuery` và trả aggregation metadata trong `SearchHits`.

Ví dụ xây query aggregation bằng Java API Client:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.NativeQuery;

Aggregation byCategory = Aggregation.of(a -> a
    .terms(t -> t
        .field("category")
        .size(20)
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .term(t -> t
            .field("active")
            .value(true)
        )
    )
    .withMaxResults(0)
    .withTrackTotalHits(false)
    .withAggregation("by_category", byCategory)
    .build();

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

`withMaxResults(0)` biểu diễn không lấy document hits; `withAggregation` gắn aggregation vào request. Các API builder cụ thể cần khớp với phiên bản Elasticsearch Java API Client mà Spring Data đang dùng.

Aggregation result được truy cập qua `SearchHits.getAggregations()`. Kiểu container và cách lấy bucket phụ thuộc aggregation cụ thể cũng như phiên bản client. Hãy chuyển aggregation response thành DTO của ứng dụng tại service boundary, tránh để controller phụ thuộc trực tiếp vào các kiểu client quá sâu.

Nếu chỉ cần aggregation, không cần entity hits. Có thể dùng query trả `size: 0` và giữ aggregation response.

## 26. Spring Data Elasticsearch: dùng Count API thay cho Page khi không cần dữ liệu

Một anti-pattern là tạo một Page chỉ để lấy tổng số kết quả:

~~~java
Page<Product> page = repository.findByCategory(
    "audio",
    PageRequest.of(0, 1)
);

long total = page.getTotalElements();
~~~

Nếu ứng dụng chỉ cần con số, request này vẫn xây dựng một kết quả phân trang và có thể kéo theo việc lấy hit không cần thiết.

Dùng Count API qua operations:

~~~java
long total = operations.count(
    new CriteriaQuery(Criteria.where("category").is("audio")),
    Product.class
);
~~~

Nếu cần vừa count vừa aggregation, có thể dùng một search request với `size: 0`, nhưng phải cân nhắc có cần exact total hits hay không. Một request gộp có thể giảm round trip; Count API riêng có thể đơn giản hơn khi chỉ đếm.

Không nên gọi Count API sau mỗi thao tác ghi để kiểm tra tổng số document nếu ứng dụng không cần số liệu ngay. Cân nhắc cache hoặc cập nhật counter theo event nếu số liệu được đọc thường xuyên.

## 27. Tạo cursor DTO cho API Spring Data

Khi dùng `search_after`, API nên trả cursor opaque để client gửi lại trong request tiếp theo.

Ví dụ DTO:

~~~java
import java.util.List;

public record CursorPage<T>(
    List<T> content,
    String nextCursor,
    boolean hasNext
) {
}
~~~

Cursor có thể mã hóa PIT ID, sort values của hit cuối, query/filter fingerprint, thời hạn sử dụng và phiên bản cursor format.

Không nên để client tự sửa sort values hoặc PIT ID. Hãy serialize cursor theo một định dạng có version và ký hoặc bảo vệ tính toàn vẹn nếu client không đáng tin cậy.

Ví dụ response:

~~~json
{
  "content": [
    {
      "id": "p-120",
      "name": "Wireless Headphones"
    }
  ],
  "nextCursor": "eyJwaXQiOi4uLiwic29ydCI6Wy4uLl19",
  "hasNext": true
}
~~~

Ở request tiếp theo, backend giải mã cursor, xác thực query/filter có cùng semantics, gửi `search_after` và PIT ID. Khi hết kết quả, backend đóng PIT và trả `hasNext: false`.

Không nên đưa một cursor không giới hạn thời gian sống vào URL công khai. PIT là tài nguyên có thời hạn; cursor cần expire tương ứng.

## 28. Chọn kích thước batch và page size

Page size lớn hơn không luôn tốt hơn.

Khi tăng `size`:

- Elasticsearch phải thu thập thêm hit.
- Response lớn hơn.
- Network và JSON serialization tốn hơn.
- Ứng dụng cần nhiều bộ nhớ hơn để giữ kết quả.
- PIT hoặc scroll context có thể tồn tại lâu hơn nếu client xử lý chậm.

Với UI, page size 20–100 thường đủ trong nhiều trường hợp, nhưng cần đo theo payload và độ phức tạp của document.

Với export, batch size có thể lớn hơn nhưng cần cân bằng giữa throughput và memory. Hãy thử nhiều kích thước trên dữ liệu thực tế, theo dõi heap, latency, số shard và kích thước response.

Không dùng một batch size duy nhất cho cả UI và export. Hai luồng có yêu cầu khác nhau.

## 29. Index sorting và sort field

Sort có thể tốn kém, đặc biệt khi phải sắp xếp theo field không phù hợp hoặc trên lượng lớn hit.

Một số nguyên tắc:

- Sort trên field có doc values.
- Tránh sort trực tiếp trên `text`.
- Dùng keyword multi-field cho chuỗi.
- Thêm tie-breaker duy nhất khi dùng `search_after`.
- Giữ kiểu dữ liệu sort nhất quán giữa các document.
- Không dùng script sort nếu có thể materialize giá trị.
- Cân nhắc index sorting khi workload có thứ tự sort cố định và được dùng thường xuyên.

Ví dụ mapping:

~~~json
{
  "settings": {
    "index": {
      "sort.field": ["createdAt", "productSortId"],
      "sort.order": ["desc", "asc"]
    }
  },
  "mappings": {
    "properties": {
      "createdAt": {
        "type": "date"
      },
      "productSortId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Index sorting sắp xếp document trong segment khi index. Nó có thể giúp một số query sort tương thích, nhưng làm tăng chi phí indexing và có giới hạn về cấu hình. Không thể thay đổi index sort tùy ý trên một index đã tạo; cần thiết kế từ lúc tạo index hoặc tạo index mới và reindex.

Chỉ bật khi query workload thực tế phù hợp với thứ tự index sort.

## 30. Query cache và aggregation

Elasticsearch có query cache cho một số filter context. Query cache có thể giúp những filter lặp lại trên cùng segment, nhưng không phải mọi query đều được cache.

Không nên kỳ vọng một aggregation request tự động được cache chỉ vì nó giống request trước. Kết quả aggregation phụ thuộc query, segment và cách request được thực thi.

Các nguyên tắc:

- Đặt điều kiện lọc phù hợp trong filter context.
- Giữ query ổn định nếu muốn tận dụng cache.
- Tránh tạo hàng nghìn biến thể query chỉ vì thay đổi tham số nhỏ.
- Theo dõi cache hit/miss thay vì tự giả định.
- Không dùng cache để che một aggregation tree có bucket explosion.

Nếu dashboard cần cùng metric lặp đi lặp lại, cache ở tầng ứng dụng hoặc materialize thống kê có thể phù hợp hơn.

## 31. Dùng Profile API và đo hiệu năng

Trước khi tối ưu, hãy đo phần nào đang tốn thời gian.

Profile API có thể giúp quan sát thời gian thực thi query và aggregation ở các shard:

~~~http
GET /products/_search
{
  "profile": true,
  "size": 0,
  "query": {
    "term": {
      "active": true
    }
  },
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand.keyword",
        "size": 20
      }
    }
  }
}
~~~

Profile có overhead và response khá lớn. Chỉ bật cho request chẩn đoán, không bật mặc định trên mọi request production.

Nên đo riêng query latency, aggregation latency, exact total hit tracking, sort latency, response size, CPU và heap trên shard/coordinating node, số bucket và cardinality, số shard được query.

Khi kiểm tra hiệu năng, dùng tập dữ liệu và concurrency gần production. Một query nhanh trên index vài nghìn document có thể chậm đáng kể khi cardinality tăng lên hàng triệu.

## 32. Những lỗi thường gặp

**Dùng Search API chỉ để đếm.** Nếu không cần hit hoặc aggregation, Count API thể hiện đúng mục đích hơn.

**Luôn bật track_total_hits: true.** Exact count có chi phí. Chỉ bật khi giao diện hoặc nghiệp vụ cần tổng chính xác.

**Đọc gte như tổng chính xác.** Kiểm tra relation của hits.total trước khi hiển thị.

**Nghĩ size: 0 làm aggregation miễn phí.** Nó chỉ bỏ hit khỏi response; aggregation vẫn phải xử lý tập document phù hợp.

**Dùng terms aggregation với size cực lớn.** Khi cần tất cả bucket, dùng composite aggregation và after_key.

**Tăng shard_size mà không đo.** Nó có thể cải thiện độ chính xác nhưng tăng memory, network và reduce cost.

**Dùng cardinality như exact count.** Cardinality là ước lượng; tăng precision threshold chỉ đổi trade-off memory/độ chính xác.

**Dùng fielddata trên text để aggregation.** Thường nên dùng multi-field keyword với doc values.

**Tạo aggregation tree quá sâu.** Bucket explosion làm tăng memory và có thể vượt search.max_buckets.

**Nhầm doc_count với số document cha.** Nested aggregation đếm nested documents; dùng reverse_nested khi cần quay lại parent.

**Dùng post_filter để giảm aggregation input.** post_filter không lọc aggregation; dùng top-level query hoặc filter aggregation theo mục đích.

**Phân trang sâu bằng from và size.** Chi phí tăng theo from + size và bị giới hạn bởi index.max_result_window.

**Tăng max_result_window để hỗ trợ trang rất sâu.** Điều này có thể làm tăng memory và CPU. Dùng search_after khi cần duyệt tuần tự.

**Dùng search_after với sort không duy nhất.** Các hit có cùng sort values có thể làm kết quả không ổn định. Thêm tie-breaker.

**Dùng search_after mà không giữ snapshot khi dữ liệu thay đổi.** Kết hợp PIT nếu cần duyệt một view nhất quán.

**Không đóng PIT hoặc scroll.** Search context giữ tài nguyên. Đóng khi hoàn tất và đặt keep_alive hợp lý.

**Dùng Scroll cho UI pagination.** Scroll phù hợp cho batch scan/export; search_after + PIT phù hợp cho cursor pagination.

**Dùng Page chỉ để lấy hasNext.** Nếu không cần total pages, lấy dư một hit hoặc dùng Slice/cursor response.

**Dùng Page nhưng tắt total hits mà vẫn tin totalPages.** Total pages cần total count đáng tin cậy. Chọn contract API đúng với dữ liệu trả về.

**Không giữ sort values trong cursor.** search_after cần đúng sort values của hit cuối trang trước.

**Dùng index sorting mà không đánh giá ingest cost.** Index sorting có thể giúp sort workload phù hợp nhưng làm tăng chi phí ghi và cần thiết kế từ lúc tạo index.

## 33. Quy trình chọn cách tối ưu

Có thể áp dụng trình tự sau cho từng endpoint:

1. Xác định endpoint cần hits, count, aggregation hay cả ba.
2. Nếu chỉ cần tổng document, dùng Count API.
3. Nếu cần search nhưng không cần tổng, tắt track_total_hits.
4. Nếu chỉ cần tổng đến một ngưỡng, dùng integer threshold và đọc relation.
5. Nếu chỉ cần aggregation, đặt size: 0.
6. Lọc tập document bằng query/filter trước khi aggregation.
7. Dùng field keyword/numeric/date có doc values.
8. Dùng terms cho top-N bucket; dùng composite để duyệt mọi bucket.
9. Dùng cardinality khi chấp nhận ước lượng distinct count.
10. Giới hạn bucket và độ sâu aggregation tree.
11. Dùng from/size cho phân trang nông.
12. Dùng search_after cho duyệt sâu tuần tự.
13. Kết hợp PIT nếu cần snapshot ổn định.
14. Dùng Scroll cho batch export hoặc scan lớn.
15. Với Spring Data, chọn count, NativeQuery, SearchHits, Page hoặc cursor DTO theo đúng contract.
16. Đo Profile API, latency, heap, response size và tải shard trước/sau thay đổi.

## Kết luận

Giảm chi phí aggregation, đếm tổng và phân trang sâu bắt đầu từ việc phân biệt chính xác loại kết quả ứng dụng cần. Count API phù hợp khi chỉ cần số document; track_total_hits cho phép bỏ hoặc giới hạn việc đếm tổng trong Search API. size: 0 giảm phần trả hit nhưng không loại bỏ chi phí aggregation.

Với aggregation, hãy giới hạn tập document đầu vào, dùng field có doc values, giới hạn số bucket và chọn đúng loại aggregation. Terms phù hợp cho top-N, composite phù hợp để duyệt mọi bucket, còn cardinality là lựa chọn ước lượng cho distinct count. Với phân trang, from và size phù hợp cho các trang đầu; search_after tránh chi phí bỏ qua hit cũ, và PIT giữ snapshot ổn định khi dữ liệu thay đổi. Scroll dành cho batch scan/export.

Trong Spring Data Elasticsearch, ElasticsearchOperations.count(...) phục vụ nhu cầu đếm riêng; NativeQuery cho phép cấu hình total hits, aggregation và phân trang; SearchHits cung cấp metadata của kết quả. Chỉ dùng Page khi tổng số trang thật sự cần thiết. Nếu giao diện chỉ cần đi tiếp, hãy dùng cursor hoặc một kết quả kiểu slice để tránh đếm chính xác không cần thiết.

## Tài liệu tham khảo

- [Elasticsearch — Count API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-count)
- [Elasticsearch — Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch — Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch — Terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-terms-aggregation)
- [Elasticsearch — Composite aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-composite-aggregation)
- [Elasticsearch — Cardinality aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-metrics-cardinality-aggregation)
- [Elasticsearch — Search aggregations](https://www.elastic.co/docs/explore-analyze/query-filter/aggregations)
- [Elasticsearch — Point in Time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-open-point-in-time)
- [Elasticsearch — Scroll search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch — Index sorting](https://www.elastic.co/docs/reference/elasticsearch/index-settings/sorting)
- [Elasticsearch — Profile search requests](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-profile)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — Query API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Query.html)
