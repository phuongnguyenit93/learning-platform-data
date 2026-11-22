# Kiểm thử sort, phân trang, highlight và aggregation

Một chức năng tìm kiếm thường phải làm nhiều việc cùng lúc: lọc đúng tài liệu, sắp xếp kết quả theo tiêu chí người dùng chọn, chia kết quả thành từng trang, làm nổi bật phần văn bản khớp và trả về thống kê tổng hợp. Trong Spring Data Elasticsearch, bốn tính năng **sort**, **pagination**, **highlight** và **aggregation** đều có thể được cấu hình trên cùng một search request, nhưng mỗi tính năng có quy tắc riêng về mapping, hiệu năng và cách đọc kết quả.

Kiểm thử từng tính năng riêng lẻ chưa đủ. Ví dụ, sort có thể đúng ở trang đầu nhưng tạo bản ghi lặp hoặc mất bản ghi khi chuyển trang; hit có thể đã được lọc đúng nhưng aggregation lại đếm toàn index; highlight có thể trả đoạn văn bản của field không được phép hiển thị. Một bộ kiểm thử tốt cần xác nhận cả nội dung từng hit, thứ tự, ranh giới trang, snippets và buckets thống kê.

Bài này dùng index **products** với các trường như productId, name, description, category, brand, price, createdAt và status. Các ví dụ tập trung vào Spring Data Elasticsearch và Elasticsearch Java API Client. Một số chữ ký API thay đổi giữa các phiên bản Spring Data; phần REST Query DSL thể hiện semantics của Elasticsearch, còn phần Java cần đối chiếu dependency cụ thể của dự án.

## 1. Bốn tính năng trong một search request

Một search request có thể thực hiện đồng thời:

- **Sort:** xác định thứ tự tài liệu theo giá, ngày tạo, tên hoặc nhiều tiêu chí.
- **Pagination:** giới hạn số hit trả về và xác định vị trí trang.
- **Highlight:** trả về các đoạn văn bản có chứa phần khớp với query.
- **Aggregation:** tính số lượng, phân bố, min/max/avg hoặc histogram trên tập tài liệu được truy vấn.

Ví dụ, trang danh sách sản phẩm có thể yêu cầu:

1. Chỉ tìm sản phẩm ACTIVE.
2. Sắp xếp giá tăng dần, sau đó productId tăng dần để ổn định thứ tự.
3. Trả 20 sản phẩm trên một trang.
4. Highlight từ khóa tìm kiếm trong name và description.
5. Thống kê số sản phẩm theo category và khoảng giá.

Một request minh họa:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ],
      "must": [
        { "multi_match": {
          "query": "mechanical keyboard",
          "fields": ["name", "description"]
        }}
      ]
    }
  },
  "sort": [
    { "price": { "order": "asc" } },
    { "productId.keyword": { "order": "asc" } }
  ],
  "highlight": {
    "fields": {
      "name": {},
      "description": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 10
      }
    }
  }
}
~~~

Search response chứa hits, sort values, highlight fragments và aggregations. Ứng dụng cần đọc đúng từng phần; không phải mọi dữ liệu đều nằm trong source document.

## 2. Mapping quyết định khả năng sort và aggregation

Trước khi viết test sort hoặc aggregation, cần kiểm tra mapping. Elasticsearch phân biệt các kiểu field và cách lưu dữ liệu phụ trợ cho truy vấn.

Một mapping minh họa:

~~~json
PUT /products
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "tenantId": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "description": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "brand": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Các field quan trọng:

| Kiểu field | Dùng phổ biến | Sort / aggregation |
|---|---|---|
| keyword | ID, category, status, brand, mã định danh | Phù hợp |
| text | Nội dung cần full-text search | Thường không sort/aggregate trực tiếp |
| integer/long/double | Số lượng, giá, điểm | Phù hợp |
| date | Thời gian | Phù hợp |
| boolean | Trạng thái bật/tắt | Phù hợp |
| nested | Mảng object cần giữ quan hệ từng phần tử | Cần nested query/sort/aggregation tương ứng |

Field text được phân tích thành token để tìm kiếm. Nó thường không có doc values và Elasticsearch mặc định không cho sort hoặc aggregate trực tiếp trên field text. Nếu cần sort tên, thường dùng multi-field keyword như name.keyword.

Không bật fielddata cho text chỉ để sort hoặc aggregate nếu chưa hiểu chi phí bộ nhớ. Fielddata có thể tiêu thụ heap đáng kể. Thiết kế multi-field keyword thường phù hợp hơn.

## 3. Kiểm tra mapping trước khi kiểm thử

Có thể lấy mapping qua REST:

~~~http
GET /products/_mapping
~~~

Trong kiểm thử tích hợp, cần xác nhận:

- Field dùng để sort tồn tại.
- Field dùng cho terms aggregation là keyword hoặc kiểu phù hợp.
- Numeric/date có kiểu chính xác.
- Multi-field như name.keyword đã được tạo.
- Nested field được khai báo nested nếu query/sort/aggregation cần semantics nested.
- Index test được tạo với mapping mong muốn, không dựa vào dynamic mapping ngẫu nhiên.

Một lỗi thường gặp là test chạy trên index cũ có mapping khác với mapping khi deploy. Khi test không chủ động tạo index hoặc xóa fixture cũ, kết quả có thể phụ thuộc thứ tự chạy.

## 4. Sort cơ bản theo một field

Elasticsearch cho phép sắp xếp tăng dần hoặc giảm dần:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "sort": [
    { "price": { "order": "asc" } }
  ]
}
~~~

- asc: tăng dần.
- desc: giảm dần.

Sort trên số so sánh theo giá trị số, không theo chuỗi. Nếu price bị mapping thành keyword, thứ tự có thể là thứ tự từ điển, chẳng hạn "100" đứng trước "20". Do đó test phải xác nhận mapping, không chỉ xác nhận vài kết quả tình cờ.

Ví dụ test kỳ vọng giá tăng dần:

| productId | price |
|---|---:|
| p-001 | 19.50 |
| p-003 | 35.00 |
| p-002 | 120.00 |

Nên tạo fixture có giá trị dễ phân biệt, bao gồm các cặp như 9, 20 và 100 để phát hiện lỗi sort theo chuỗi.

## 5. Sort nhiều field và thứ tự ưu tiên

Sort array được đánh giá theo thứ tự khai báo. Field đầu tiên là tiêu chí chính; field tiếp theo dùng khi giá trị trước bằng nhau.

~~~http
POST /products/_search
{
  "sort": [
    { "price": { "order": "asc" } },
    { "createdAt": { "order": "desc" } },
    { "productId": { "order": "asc" } }
  ]
}
~~~

Thứ tự này có nghĩa:

1. Giá thấp đứng trước.
2. Nếu giá bằng nhau, sản phẩm mới hơn đứng trước.
3. Nếu cả giá và thời gian bằng nhau, productId quyết định thứ tự cuối.

Test cần tạo ít nhất hai document có cùng giá và thời gian để xác nhận tie-breaker thực sự được áp dụng. Nếu fixture không có giá trị trùng, test sẽ không chứng minh được tiêu chí thứ hai hoặc thứ ba.

Không dựa vào thứ tự mặc định của Elasticsearch khi nhiều tài liệu có cùng sort value. Thứ tự giữa các document bằng nhau có thể thay đổi theo shard, refresh hoặc lần thực thi.

## 6. Sort ổn định và tie-breaker duy nhất

Pagination cần thứ tự xác định. Nếu chỉ sort theo price và nhiều sản phẩm có cùng giá, một document có thể xuất hiện ở trang khác sau refresh hoặc khi dữ liệu thay đổi.

Hãy thêm một field duy nhất có doc values làm tie-breaker, ví dụ productId kiểu keyword. Không mặc định sort trực tiếp trên trường đặc biệt _id: Elasticsearch có giới hạn và chi phí riêng đối với việc sort trên _id. Lưu một business ID riêng kiểu keyword thường dễ kiểm soát hơn.

Ví dụ:

~~~json
"sort": [
  { "price": "asc" },
  { "productId": "asc" }
]
~~~

Test ổn định:

- Index nhiều document có cùng price.
- Chạy cùng query nhiều lần.
- So sánh thứ tự productId giữa các lần.
- Chuyển qua các trang liên tiếp.
- Xác nhận không có ID lặp hoặc bị bỏ sót khi tập dữ liệu không đổi.

Tie-breaker phải thực sự duy nhất trong phạm vi search. Nếu productId chỉ duy nhất trong tenant, query luôn lọc tenant thì có thể đủ; nếu query có thể chạy qua nhiều tenant, cần một ID duy nhất toàn index.

## 7. Sort theo field text và multi-field keyword

Nếu name được mapping là text, request sau thường không phù hợp:

~~~http
POST /products/_search
{
  "sort": [
    { "name": "asc" }
  ]
}
~~~

Dùng multi-field keyword:

~~~http
POST /products/_search
{
  "sort": [
    { "name.keyword": { "order": "asc" } }
  ]
}
~~~

Mapping có thể khai báo:

~~~json
"name": {
  "type": "text",
  "fields": {
    "keyword": {
      "type": "keyword",
      "normalizer": "lowercase_normalizer"
    }
  }
}
~~~

Nếu muốn sort không phân biệt chữ hoa/thường, có thể cấu hình normalizer trên keyword field. Cần xác nhận normalizer đã được khai báo trong settings trước khi tạo index.

Test nên dùng tên như Alpha, alpha và BETA để xác nhận quy tắc sort. Nếu không có normalizer, sort keyword có thể phân biệt chữ hoa/thường theo thứ tự term.

## 8. Missing values và unmapped fields

Một số document có thể không có field dùng để sort. Elasticsearch hỗ trợ cấu hình missing để đưa giá trị thiếu lên đầu hoặc cuối:

~~~http
POST /products/_search
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

Các lựa chọn phổ biến gồm _first, _last hoặc một giá trị cụ thể phù hợp kiểu field.

Khi search trên nhiều index có mapping khác nhau, field có thể không tồn tại ở một index. Có thể dùng unmapped_type trong sort để chỉ định kiểu dự kiến cho field không được mapping. Tuy nhiên, đây là cách xử lý tương thích schema; không nên dùng để che giấu việc index đáng lẽ phải có mapping nhưng bị tạo sai.

Test nên có document thiếu price và xác nhận vị trí của nó. Cũng cần kiểm tra index alias trỏ tới nhiều backing index có mapping tương thích.

## 9. Sort trên field nhiều giá trị

Một field có thể chứa nhiều giá trị. Ví dụ product có nhiều mức giá theo khu vực hoặc nhiều timestamp. Khi sort trên multi-valued field, Elasticsearch cần chọn giá trị đại diện bằng sort mode.

Một ví dụ:

~~~http
POST /products/_search
{
  "sort": [
    {
      "regionalPrices": {
        "order": "asc",
        "mode": "min"
      }
    }
  ]
}
~~~

Các mode thường gặp:

- min: dùng giá trị nhỏ nhất.
- max: dùng giá trị lớn nhất.
- avg: trung bình.
- sum: tổng.
- median: trung vị.

Mode áp dụng được tùy kiểu field và semantics sort. Test cần tạo một document có nhiều giá trị khác nhau để xác nhận mode, không chỉ tạo field có một phần tử.

## 10. Nested sort

Khi dữ liệu là nested object, sort phải chỉ rõ nested path và có thể cần nested filter. Ví dụ sản phẩm có nhiều offer:

~~~json
{
  "productId": "p-1001",
  "offers": [
    { "region": "VN", "price": 120 },
    { "region": "SG", "price": 135 }
  ]
}
~~~

Nếu offers được mapping là nested, sort theo giá offer ở VN cần chỉ định nested path và filter:

~~~http
POST /products/_search
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "offers",
          "filter": {
            "term": {
              "offers.region": "VN"
            }
          }
        }
      }
    }
  ]
}
~~~

Nếu offers chỉ là object thông thường thay vì nested, Elasticsearch không giữ quan hệ giữa các thuộc tính trong từng phần tử theo cách nested query yêu cầu. Test phải dùng mapping và fixture đúng mô hình dữ liệu.

## 11. Pagination bằng from và size

Cách phân trang quen thuộc là dùng from và size:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "sort": [
    { "createdAt": { "order": "desc" } },
    { "productId": { "order": "asc" } }
  ]
}
~~~

- from: số hit bỏ qua trước khi bắt đầu trả kết quả.
- size: số hit tối đa cần trả.

Trang đầu 20 item: from = 0, size = 20.

Trang thứ hai 20 item: from = 20, size = 20.

Trang thứ ba 20 item: from = 40, size = 20.

Với giao diện page-based, có thể dùng PageRequest trong Spring Data:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("productId")
        )
);
~~~

Repository có thể khai báo:

~~~java
Page<Product> findByStatus(String status, Pageable pageable);
~~~

Ví dụ gọi:

~~~java
Page<Product> page =
        productRepository.findByStatus("ACTIVE", pageable);
~~~

Hành vi chính xác của Page, Pageable và sort field phụ thuộc repository/API và phiên bản. Với query tùy chỉnh, hãy xác nhận pageable và sort thực sự được áp dụng trong request được gửi tới Elasticsearch.

## 12. Đọc kết quả Page và SearchHits

Page thường cung cấp:

- content: danh sách phần tử của trang.
- number: số thứ tự trang.
- size: kích thước trang.
- totalElements: tổng số phần tử.
- totalPages: tổng số trang.
- hasNext/hasPrevious: trạng thái phân trang.

Với ElasticsearchOperations, kết quả search có thể là SearchHits<T>. Mỗi SearchHit có thể cung cấp:

- content: entity được convert.
- id và index.
- score.
- sortValues.
- highlightFields.
- metadata liên quan tới hit.

Ví dụ:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();
    List<Object> sortValues = hit.getSortValues();
    Map<String, List<String>> highlights =
            hit.getHighlightFields();
}
~~~

Tên kiểu và getter cần đối chiếu phiên bản. Không giả định SearchHit content đã chứa highlight fragments; highlight thường được trả trong metadata riêng.

Khi cần aggregation, có thể đọc aggregations từ SearchHits thông qua abstraction aggregation container mà Spring Data cung cấp. Cấu trúc cụ thể phụ thuộc Java API Client và phiên bản Spring Data Elasticsearch.

## 13. Giới hạn deep pagination với from/size

Elasticsearch thường đặt giới hạn mặc định max_result_window là 10.000 cho from + size. Truy vấn trang quá sâu có thể bị từ chối hoặc tốn tài nguyên đáng kể.

Ví dụ:

- Trang 1: from 0, size 20.
- Trang 100: from 1.980, size 20.
- Trang 500: from 9.980, size 20.
- Trang 501: from 10.000, size 20.

Khi from + size vượt giới hạn, request có thể trả lỗi result window too large.

Không nên tăng max_result_window vô hạn chỉ để hỗ trợ nút “trang tiếp theo”. Elasticsearch phải giữ và xử lý nhiều kết quả hơn ở mỗi shard cho deep offset, làm tăng bộ nhớ và chi phí merge.

Với người dùng cần nhảy tới trang xa, cân nhắc thiết kế UX khác hoặc dùng chiến lược cursor/search_after. from/size phù hợp cho các trang đầu và kết quả vừa phải.

## 14. Search_after cho phân trang sâu

search_after dùng sort values của hit cuối trang hiện tại làm điểm bắt đầu cho trang kế tiếp. Nó tránh phải bỏ qua một offset lớn như from/size.

Trang đầu:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Giả sử hit cuối có sort values:

~~~json
[
  "2026-11-13T08:30:00Z",
  "p-020"
]
~~~

Trang tiếp theo gửi lại đúng sort và search_after:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "search_after": [
    "2026-11-13T08:30:00Z",
    "p-020"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

search_after cần giữ nguyên thứ tự sort và kiểu giá trị trả về. Không tự tạo cursor bằng cách chỉ lấy createdAt nếu sort có thêm productId. Mỗi sort key phải được đưa vào đúng thứ tự.

search_after không dùng cùng offset from > 0 theo cách phân trang thông thường. Nó phù hợp cho luồng next-page/cursor hơn là nhảy tùy ý tới trang thứ 500.

## 15. PIT kết hợp search_after

Nếu dữ liệu thay đổi trong lúc người dùng đang phân trang, thứ tự hoặc tập kết quả có thể thay đổi giữa các request. **Point in Time (PIT)** giữ một view nhất quán của index trong một khoảng thời gian.

Luồng khái quát:

1. Mở PIT cho index.
2. Gửi search đầu tiên với PIT, sort và size.
3. Lấy sort values của hit cuối.
4. Gửi request tiếp theo với cùng PIT và search_after.
5. Tiếp tục cho đến khi hết kết quả.
6. Đóng PIT khi hoàn tất hoặc khi hết thời gian sử dụng.

Mở PIT:

~~~http
POST /products/_pit?keep_alive=1m
~~~

Search với PIT:

~~~http
POST /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Trang tiếp theo thêm search_after từ hit cuối. Response có thể trả PIT ID mới; nếu vậy, dùng ID mới nhất cho request tiếp theo.

Đóng PIT:

~~~http
DELETE /_pit
{
  "id": "PIT_ID"
}
~~~

PIT tiêu thụ tài nguyên cluster trong thời gian mở. Đặt keep_alive vừa đủ, đóng khi xong và xử lý trường hợp client ngừng phân trang. Không mở PIT mới cho mỗi trang nếu cần một chuỗi kết quả nhất quán.

## 16. Kiểm thử pagination không lặp và không mất hit

Một test phân trang cơ bản cần có đủ số document để lấp nhiều trang. Ví dụ tạo 45 sản phẩm, page size 10, kết quả mong đợi có 5 trang.

Các assertion nên bao gồm:

- Trang 0 có 10 hit.
- Trang 1 có 10 hit.
- Trang cuối có 5 hit.
- Total elements bằng 45.
- ID giữa các trang không trùng.
- Hợp tất cả ID của các trang bằng tập fixture.
- Sort đúng trên từng trang.
- Không có hit ngoài filter.
- Empty result trả content rỗng và totalElements bằng 0.

Nếu sort field có giá trị trùng, hãy thêm tie-breaker để test không phụ thuộc thứ tự ngẫu nhiên.

Với search_after, cần lặp request bằng sort values của hit cuối, gom tất cả ID rồi xác nhận không lặp và không mất tài liệu trong một PIT cố định.

## 17. Pagination khi dữ liệu thay đổi

Không dùng một test dữ liệu tĩnh để kết luận pagination ổn định trong môi trường ghi liên tục. Khi dùng from/size và có insert/update giữa các trang, document có thể dịch chuyển vị trí.

Ví dụ:

1. Trang đầu trả các giá trị sort 100 đến 91.
2. Một document mới có sort value 110 được thêm vào.
3. Trang thứ hai dùng from = 10.
4. Một document có thể bị lặp hoặc bị bỏ qua do offset thay đổi.

PIT + search_after phù hợp khi cần duyệt một snapshot nhất quán. Nếu sản phẩm chấp nhận dữ liệu thay đổi giữa các trang, cần xác định UX và test theo semantics đó.

Không cam kết pagination không trùng trong mọi điều kiện nếu ứng dụng không giữ snapshot và dữ liệu đang thay đổi.

## 18. Highlight hoạt động thế nào?

Highlight trả các fragment của field có chứa phần khớp với query. Nó thường được dùng để người dùng thấy vì sao document xuất hiện trong kết quả.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": "wireless mechanical keyboard"
    }
  },
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "description": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Nếu source description là:

~~~text
A compact wireless keyboard with mechanical switches.
~~~

Một highlight fragment có thể là:

~~~html
A compact <mark>wireless</mark> <mark>keyboard</mark> with mechanical switches.
~~~

Elasticsearch chọn fragment theo nội dung khớp và highlighter. Không bảo đảm fragment luôn là câu hoàn chỉnh hoặc chứa mọi từ trong query.

Highlight không phải là phép biến đổi source document. Nó được trả trong metadata của search hit; ứng dụng quyết định cách hiển thị và escape nội dung.

## 19. Các cấu hình highlight quan trọng

| Thuộc tính | Ý nghĩa |
|---|---|
| fields | Field cần highlight |
| pre_tags | Chuỗi đánh dấu trước phần khớp |
| post_tags | Chuỗi đánh dấu sau phần khớp |
| fragment_size | Kích thước fragment mục tiêu |
| number_of_fragments | Số fragment tối đa |
| no_match_size | Độ dài đoạn đầu field khi không có match, nếu cấu hình |
| require_field_match | Chỉ highlight field khớp query hay không |
| type | Loại highlighter |
| boundary_scanner | Cách tìm ranh giới fragment |
| order | Thứ tự fragment, ví dụ theo score |

Có thể cấu hình riêng từng field:

~~~json
"highlight": {
  "pre_tags": ["<em>"],
  "post_tags": ["</em>"],
  "fields": {
    "name": {
      "number_of_fragments": 0
    },
    "description": {
      "fragment_size": 150,
      "number_of_fragments": 3
    }
  }
}
~~~

number_of_fragments = 0 yêu cầu trả toàn bộ field được highlight thay vì chia thành fragments. Cách này có thể trả nội dung dài; cần cân nhắc payload và quyền truy cập field.

## 20. Chọn highlighter phù hợp

Elasticsearch có các loại highlighter phổ biến:

- **unified:** lựa chọn mặc định trong nhiều trường hợp, hỗ trợ nhiều kiểu query và phân tích fragment.
- **plain:** highlighter đơn giản dựa trên query và nội dung field.
- **fvh (Fast Vector Highlighter):** có thể phù hợp khi field lưu term vectors với offsets/positions phù hợp.
- **semantic:** dành cho các trường hợp semantic search và phụ thuộc phiên bản/cấu hình.

FVH có thể cần mapping term_vector với positions và offsets. Nếu mapping không lưu thông tin cần thiết, highlighter có thể không hoạt động như mong đợi hoặc phải dùng cách khác.

Không chọn highlighter chỉ dựa vào tên. Hãy kiểm thử trên loại query thực tế: match, multi_match, phrase, nested, synonym hoặc query có nhiều nhánh.

## 21. Highlight nhiều field và multi_match

Khi query tìm trên nhiều field, có thể highlight từng field riêng:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless keyboard",
      "fields": ["name", "description", "brand"]
    }
  },
  "highlight": {
    "fields": {
      "name": {},
      "description": {
        "fragment_size": 100,
        "number_of_fragments": 2
      },
      "brand": {
        "number_of_fragments": 0
      }
    }
  }
}
~~~

Test cần xác nhận:

- Field nào thực sự được highlight.
- Fragment có chứa term phù hợp.
- Field không nằm trong cấu hình không xuất hiện highlight ngoài dự kiến.
- Query nhiều field không làm mất highlight ở một field.
- Không nhầm highlight fragment với giá trị đầy đủ trong source.

Nếu query dùng field alias hoặc multi-field, kiểm tra highlighter có nhận đúng field được query hay không.

## 22. Đọc highlight từ SearchHit trong Spring Data

Với ElasticsearchOperations, mỗi SearchHit có thể cung cấp map highlight fields.

Ví dụ:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    List<String> nameFragments =
            hit.getHighlightField("name");

    List<String> descriptionFragments =
            hit.getHighlightField("description");
}
~~~

Tên phương thức cụ thể có thể khác theo phiên bản; API thường cung cấp highlightFields map hoặc getter theo tên field. Cần kiểm tra SearchHit của dependency đang dùng.

Đừng giả định Product.name đã chứa thẻ highlight. Nếu cần trả snippets cho frontend, hãy xây response DTO riêng:

~~~java
public record ProductSearchResult(
        Product product,
        List<String> nameHighlights,
        List<String> descriptionHighlights
) {
}
~~~

Chuyển SearchHit thành DTO:

~~~java
ProductSearchResult toResult(SearchHit<Product> hit) {
    return new ProductSearchResult(
            hit.getContent(),
            hit.getHighlightField("name"),
            hit.getHighlightField("description")
    );
}
~~~

Tách metadata khỏi entity giúp tránh lưu các thẻ HTML vào source document hoặc vô tình ghi lại fragment đã highlight khi save entity.

## 23. An toàn khi hiển thị highlight

Highlight thường chứa pre_tags và post_tags do ứng dụng cấu hình. Nếu frontend render fragment như HTML, cần tránh XSS.

Không cho người dùng kiểm soát tùy ý pre_tags/post_tags. Nội dung field có thể chứa HTML hoặc script do người dùng nhập; highlighter không phải HTML sanitizer.

Một số nguyên tắc:

- Dùng tag cố định, ví dụ mark hoặc em.
- Escape nội dung không tin cậy theo cơ chế render của frontend.
- Chỉ cho phép markup đã được kiểm soát.
- Không nối fragment vào HTML bằng innerHTML một cách tùy tiện.
- Không ghi fragment đã đánh dấu trở lại document.
- Kiểm tra field nhạy cảm có bị highlight rồi trả về role không được phép hay không.

Test nên tạo description chứa chuỗi HTML đặc biệt và từ khóa tìm kiếm. Xác nhận response được xử lý an toàn và không thực thi script khi render.

## 24. Aggregation là gì?

Aggregation cho phép tính thống kê trên tập tài liệu được query. Thay vì chỉ trả danh sách document, Elasticsearch có thể trả các bucket và metric.

Ba nhóm thường dùng:

- **Bucket aggregation:** chia tài liệu thành nhóm, ví dụ theo category, brand hoặc khoảng giá.
- **Metric aggregation:** tính giá trị như min, max, avg, sum, cardinality.
- **Pipeline aggregation:** tính toán dựa trên kết quả của aggregation khác.

Ví dụ terms aggregation theo category:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 10
      }
    }
  }
}
~~~

Response có thể chứa:

~~~json
{
  "aggregations": {
    "by_category": {
      "buckets": [
        {
          "key": "keyboard",
          "doc_count": 12
        },
        {
          "key": "mouse",
          "doc_count": 8
        }
      ]
    }
  }
}
~~~

Khi chỉ cần thống kê, size = 0 giúp không trả hit documents. Tuy nhiên query vẫn cần được lọc đúng phạm vi dữ liệu.

## 25. Terms aggregation và bucket size

Terms aggregation nhóm document theo từng giá trị của field keyword:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand",
        "size": 20,
        "order": {
          "_count": "desc"
        }
      }
    }
  }
}
~~~

size ở đây là số bucket tối đa trả về, khác với size của search hits.

Các khái niệm cần phân biệt:

- Search size: số hit documents trả về.
- Aggregation terms size: số bucket trả về.
- shard_size: số bucket mỗi shard gửi về coordinator để cải thiện độ chính xác.
- doc_count: số document trong bucket.
- sum_other_doc_count: số document thuộc các bucket không được trả.
- doc_count_error_upper_bound: giới hạn sai số đếm trong một số kiểu phân phối/order.

Terms aggregation thường phù hợp để hiển thị top category hoặc brand. Nếu cần duyệt toàn bộ giá trị cardinality cao, không nên chỉ tăng size lên rất lớn.

## 26. Kiểm thử độ chính xác của terms aggregation

Fixture nên có phân bố biết trước. Ví dụ:

| Category | Số document |
|---|---:|
| keyboard | 5 |
| mouse | 3 |
| monitor | 2 |

Test kiểm tra:

- Bucket keyboard có doc_count 5.
- Bucket mouse có doc_count 3.
- Bucket monitor có doc_count 2.
- Thứ tự bucket đúng nếu order theo _count desc.
- Không có bucket ngoài tập fixture.
- Nếu size nhỏ hơn số category, chỉ các bucket theo quy tắc top-N xuất hiện.
- sum_other_doc_count phù hợp nếu test cần xác nhận bucket bị lược bỏ.

Không chỉ assert số lượng bucket. Một lỗi có thể trả đúng ba bucket nhưng count từng bucket sai do query filter không đúng.

Với dữ liệu phân tán nhiều shard, terms aggregation có thể có sai số tùy shard_size và cách sắp xếp. Test tích hợp nhỏ trên một shard không chứng minh độ chính xác ở cluster lớn nhiều shard. Khi ứng dụng cần count chính xác theo từng bucket, phải hiểu semantics và chọn cách aggregation phù hợp.

## 27. Metric aggregation: min, max, avg, sum và cardinality

Ví dụ thống kê giá:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_stats": {
      "stats": {
        "field": "price"
      }
    },
    "unique_brands": {
      "cardinality": {
        "field": "brand"
      }
    }
  }
}
~~~

stats thường trả count, min, max, avg và sum. Cardinality ước lượng số giá trị duy nhất bằng thuật toán xác suất; kết quả không nhất thiết chính xác tuyệt đối trên tập dữ liệu lớn.

Test với fixture nhỏ có thể xác nhận min/max/avg/sum chính xác. Với cardinality, nên chọn fixture và cấu hình phù hợp, hiểu precision threshold và tránh giả định đây luôn là phép đếm chính xác tuyệt đối.

Các metric thường dùng:

| Aggregation | Mục đích |
|---|---|
| min | Giá trị nhỏ nhất |
| max | Giá trị lớn nhất |
| avg | Trung bình |
| sum | Tổng |
| value_count | Số giá trị field |
| cardinality | Ước lượng số giá trị duy nhất |
| stats | Nhiều metric cơ bản cùng lúc |
| extended_stats | Thêm độ lệch chuẩn và các thống kê liên quan |
| percentiles | Phân vị |
| top_hits | Lấy một số hit đại diện trong bucket |

## 28. Histogram và range aggregation

Histogram chia giá trị số thành các khoảng có độ rộng cố định:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "histogram": {
        "field": "price",
        "interval": 50,
        "min_doc_count": 0
      }
    }
  }
}
~~~

Range aggregation cho phép tự định nghĩa các khoảng:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "price",
        "ranges": [
          { "to": 50 },
          { "from": 50, "to": 100 },
          { "from": 100 }
        ]
      }
    }
  }
}
~~~

Các range thường dùng cho bộ lọc giao diện như dưới 50, từ 50 đến 100, trên 100. Hãy xác định rõ biên khoảng; Elasticsearch thường diễn giải from là inclusive và to là exclusive.

Test cần có giá trị đúng tại biên, ví dụ 49.99, 50, 99.99 và 100 để phát hiện lỗi khoảng.

Date histogram chia dữ liệu theo thời gian:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "created_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh"
      }
    }
  }
}
~~~

Test cần chú ý timezone, daylight saving ở những khu vực có áp dụng, và khác biệt giữa calendar_interval với fixed_interval.

## 29. Nested aggregation và filter aggregation

Nếu dữ liệu nested, aggregation phải đi qua nested path:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "offers": {
      "nested": {
        "path": "offers"
      },
      "aggs": {
        "by_region": {
          "terms": {
            "field": "offers.region"
          }
        }
      }
    }
  }
}
~~~

Nếu cần thống kê một tập con, dùng filter aggregation:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "active_products": {
      "filter": {
        "term": {
          "status": "ACTIVE"
        }
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

Filter aggregation chỉ giới hạn bucket con của nó. Nếu response có nhiều aggregation khác, mỗi nhánh cần semantics filter riêng. Đối với tenant isolation, đặt tenant filter ở query gốc để giới hạn toàn bộ hits và aggregations; không chỉ lọc một bucket con.

## 30. Composite aggregation để duyệt nhiều bucket

Terms aggregation trả top bucket theo size, không phải cơ chế phân trang tổng quát cho tất cả bucket. Với cardinality cao và cần duyệt từng nhóm, dùng composite aggregation với after_key.

Trang đầu:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "all_categories": {
      "composite": {
        "size": 100,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          },
          {
            "brand": {
              "terms": {
                "field": "brand"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Response có after_key. Trang tiếp theo gửi lại after:

~~~json
"after": {
  "category": "keyboard",
  "brand": "acme"
}
~~~

Composite aggregation phù hợp để export hoặc duyệt tất cả nhóm theo batch. Nó khác với terms size và không nên thay bằng cách tăng terms size rất lớn.

Test cần:

- Đọc hết các trang bucket đến khi không còn after_key.
- Xác nhận không lặp key.
- Xác nhận không bỏ sót tổ hợp category/brand.
- Giữ nguyên thứ tự sources giữa các request.
- Xử lý response cuối không có after_key.
- Duy trì cùng query filter và snapshot semantics nếu dữ liệu thay đổi.

## 31. Kết hợp aggregation với query filter

Aggregation mặc định được tính trên tập document phù hợp với query gốc. Vì vậy, filter của query cần phản ánh đúng tập dữ liệu mà người dùng được phép xem.

Ví dụ lọc ACTIVE và tenant trước khi tính category:

~~~http
POST /products/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-a" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
~~~

Không đặt tenant filter chỉ ở hit retrieval nếu aggregation được tạo trên query khác hoặc request khác. Một endpoint có thể trả đúng danh sách sản phẩm nhưng thống kê lại phản ánh toàn bộ tenant.

Test nên có một category chỉ xuất hiện trong tenant B. Khi tenant A search, category đó và count của nó không được xuất hiện.

## 32. Aggregation không nhất thiết phản ánh cùng tập hit sau post-filter

Elasticsearch có khái niệm post_filter. Nó lọc hits sau khi aggregation đã được tính, do đó aggregation có thể phản ánh tập document rộng hơn hits.

Điều này hữu ích khi thiết kế faceted navigation: hits có thể áp dụng toàn bộ bộ lọc, còn một số facet được tính trên tập rộng hơn để người dùng vẫn nhìn thấy các lựa chọn khác. Nhưng đây cũng là nguồn gây hiểu nhầm nếu ứng dụng mong aggregation chỉ tính trên hits.

Ví dụ, query filter status ACTIVE và post_filter category keyboard có thể làm hits chỉ còn keyboard, trong khi aggregation category vẫn tính trên tất cả ACTIVE.

Test phải xác nhận chính xác semantics mong muốn:

- Nếu aggregation cần cùng tập document với hits, đặt filter vào query.
- Nếu facet cố ý bỏ qua một filter, dùng post_filter có chủ đích và kiểm tra kết quả.
- Không dùng post_filter để thực hiện tenant isolation; tenant boundary phải ở query gốc.

## 33. Đọc aggregation từ Spring Data Elasticsearch

Khi dùng ElasticsearchOperations, search trả SearchHits<T>. Aggregation metadata có thể truy cập qua getAggregations() và container cụ thể của phiên bản.

Ví dụ khung:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

AggregationsContainer<?> container = hits.getAggregations();

if (container != null) {
    Object aggregations = container.aggregations();
    // Chuyển đổi hoặc đọc aggregation theo implementation/version.
}
~~~

Với Elasticsearch Java API Client, aggregation response có các kiểu dữ liệu typed tương ứng. Có thể đọc trực tiếp từ response khi cần kiểm soát chi tiết.

Không ép kiểu aggregation container một cách tùy tiện. Hãy kiểm tra implementation cụ thể và tên aggregation đã khai báo. Nên tách phần chuyển đổi response thành một mapper/service nhỏ để controller không chứa logic parse aggregation.

Nếu aggregation là một phần quan trọng của API, hãy tạo DTO rõ ràng:

~~~java
public record CategoryCount(
        String category,
        long count
) {
}

public record ProductSearchSummary(
        List<CategoryCount> categories,
        double averagePrice,
        long totalHits
) {
}
~~~

DTO giúp tránh trả nguyên object aggregation nội bộ của Elasticsearch cho client và giữ API ứng dụng ổn định khi thư viện thay đổi.

## 34. NativeQuery trong Spring Data Elasticsearch

Với Spring Data Elasticsearch dùng Elasticsearch Java API Client, NativeQuery cho phép cấu hình query DSL nâng cao. Một ví dụ minh họa cho search, sort, pageable và aggregation:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value("ACTIVE")
                ))
                .must(m -> m.multiMatch(mm -> mm
                        .query("keyboard")
                        .fields("name", "description")
                ))
        ))
        .withPageable(PageRequest.of(0, 20))
        .withSort(SortOptions.of(s -> s.field(f -> f
                .field("price")
                .order(SortOrder.Asc)
        )))
        .withAggregation(
                "by_category",
                Aggregation.of(a -> a.terms(t -> t
                        .field("category")
                        .size(10)
                ))
        )
        .build();
~~~

Đây là khung minh họa cho API NativeQuery/Java API Client. Import, builder overload, cách cấu hình highlight và kiểu aggregation response phụ thuộc phiên bản. Trong dự án, hãy dùng đúng API được cung cấp bởi dependency đang quản lý.

Thứ tự sort nhiều field có thể được cấu hình bằng cách thêm nhiều SortOptions theo API tương ứng. Với query phức tạp, nên tạo helper cho từng phần: query filters, sort options, highlight query và aggregations. Điều đó giúp test riêng từng phần mà không nhân bản toàn bộ request builder.

## 35. Cấu hình highlight trong NativeQuery

Spring Data Elasticsearch có abstraction cho highlight query. Một số phiên bản dùng HighlightQuery kết hợp với đối tượng Highlight/HighlightField; chi tiết constructor và builder có thể thay đổi.

Về mặt semantics, cấu hình cần chỉ rõ:

- Field cần highlight.
- Pre/post tags.
- Fragment size.
- Number of fragments.
- Highlighter type nếu cần.

REST DSL tương đương:

~~~json
{
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "name": {
        "number_of_fragments": 0
      },
      "description": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Nếu Java abstraction không đáp ứng một option cần thiết, có thể dùng NativeQuery/Java API Client ở tầng phù hợp. Tránh trộn một phần query bằng abstraction và một phần bằng raw JSON theo cách không kiểm soát được mapping hoặc escaping.

## 36. Test sort trong repository và Operations

Với repository method hỗ trợ Pageable, có thể test sort qua PageRequest:

~~~java
@Test
void returnsProductsSortedByPriceAscending() {
    Pageable pageable = PageRequest.of(
            0,
            10,
            Sort.by(
                    Sort.Order.asc("price"),
                    Sort.Order.asc("productId")
            )
    );

    Page<Product> result =
            repository.findByStatus("ACTIVE", pageable);

    assertThat(result.getContent())
            .extracting(Product::getPrice)
            .isSorted();
}
~~~

Nếu có tie-breaker, test riêng thứ tự productId trong nhóm có cùng price. Test trên danh sách giá đã sort không chứng minh tiêu chí phụ.

Với NativeQuery, nên kiểm tra SearchHit sortValues hoặc ID thứ tự trả về. Khi có thể, tạo request test và xác nhận sort options thực sự được gửi.

## 37. Test highlight

Một test highlight cần fixture chứa từ khóa trong đúng field:

~~~java
@Test
void highlightsMatchingDescription() {
    SearchHits<Product> hits = operations.search(
            queryWithDescriptionHighlight("wireless"),
            Product.class
    );

    SearchHit<Product> hit = hits.getSearchHit(0);

    assertThat(hit.getHighlightField("description"))
            .isNotEmpty()
            .anySatisfy(fragment ->
                    assertThat(fragment).contains("<mark>wireless</mark>")
            );
}
~~~

Đây là ví dụ minh họa; phương thức lấy hit và cấu hình query cần khớp API của phiên bản.

Test nên xác nhận:

- Fragment có chứa term đã query.
- Pre/post tags đúng.
- Field mong muốn được highlight.
- Số fragment không vượt cấu hình.
- Không có highlight ở field ngoài cấu hình nếu require_field_match hoặc query semantics yêu cầu.
- Không thay đổi source document sau khi search.
- Response DTO tách highlight khỏi entity.

Không nên assert toàn bộ fragment chính xác từng ký tự nếu highlighter có thể thay đổi ranh giới fragment theo analyzer hoặc phiên bản. Assert những thuộc tính ổn định như field, term và số lượng là phù hợp hơn.

## 38. Test aggregation

Với fixture nhỏ, có thể kiểm tra số lượng bucket và giá trị metric đã biết:

~~~java
@Test
void aggregatesProductsByCategory() {
    ProductSearchSummary summary = searchService.categorySummary();

    assertThat(summary.categories())
            .contains(
                    new CategoryCount("keyboard", 5),
                    new CategoryCount("mouse", 3)
            );
}
~~~

Test cần tạo đúng số document, đảm bảo refresh, và dùng query filter tương ứng. Nếu test nhiều case trên cùng index, xóa hoặc dùng namespace index riêng để tránh dữ liệu cũ ảnh hưởng.

Với histogram/range, test các giá trị ở biên. Với cardinality, nhớ đây có thể là ước lượng. Với composite, test toàn bộ vòng lặp after_key.

## 39. Kiểm thử tích hợp cả bốn tính năng cùng lúc

Một integration test end-to-end nên mô phỏng yêu cầu giao diện thực tế:

- Query tìm sản phẩm ACTIVE có từ khóa.
- Sort price tăng dần, productId tăng dần.
- Pagination 10 item mỗi trang.
- Highlight name và description.
- Aggregation theo category và brand.
- Tổng hit chỉ tính trên tập query filter.
- Kết quả không có document ngoài điều kiện.

Kịch bản:

1. Tạo 25 sản phẩm fixture với category và brand đã biết.
2. Có ít nhất ba sản phẩm cùng price để kiểm tra tie-breaker.
3. Có sản phẩm chứa từ khóa ở name và sản phẩm chỉ chứa từ khóa ở description.
4. Có sản phẩm INACTIVE để xác nhận filter.
5. Tạo index với mapping explicit.
6. Index fixture và refresh.
7. Gọi search trang đầu.
8. Kiểm tra 10 hit và thứ tự sort.
9. Kiểm tra highlight fragments.
10. Kiểm tra category/brand bucket counts.
11. Gọi trang hai và ba.
12. Gom ID và xác nhận không trùng/mất.
13. Kiểm tra tổng hit và total pages.

Test kết hợp phát hiện lỗi mà test riêng lẻ có thể bỏ sót, ví dụ query filter được áp dụng cho hits nhưng không cho aggregation, hoặc pageable ghi đè sort options.

## 40. Testcontainers và quản lý index test

Có thể dùng Testcontainers để chạy Elasticsearch tương thích với phiên bản Spring Data Elasticsearch của ứng dụng. Cấu hình test nên:

- Chọn image/version phù hợp.
- Khởi tạo cluster trước khi tạo client.
- Tạo index với mapping/settings rõ ràng.
- Dùng tên index riêng cho test hoặc xóa dữ liệu giữa các test.
- Chờ refresh hoặc dùng refresh policy phù hợp.
- Đóng client/container theo lifecycle.
- Không chạy test đồng thời trên cùng index nếu fixture dùng chung và có thể xung đột.

Nếu chạy test song song, tạo index có tên riêng theo test class hoặc test run. Tránh test phụ thuộc thứ tự thực thi.

## 41. Những lỗi thường gặp khi kết hợp sort, pagination, highlight và aggregation

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Sort tên báo lỗi | Sort trên field text | Dùng multi-field keyword |
| Giá 100 đứng trước 20 | Price bị mapping keyword | Dùng numeric mapping |
| Thứ tự thay đổi giữa các lần | Sort values trùng và thiếu tie-breaker | Thêm unique keyword field |
| Hit lặp hoặc mất giữa các trang | Offset pagination trên dữ liệu thay đổi hoặc sort không ổn định | Tie-breaker; PIT + search_after |
| Trang sâu bị từ chối | from + size vượt max_result_window | Dùng search_after/PIT |
| Trang cuối thiếu hoặc thừa item | Tính total/page sai hoặc fixture cũ | Kiểm tra total hits, refresh và test boundaries |
| Highlight rỗng | Field không match, sai mapping hoặc highlighter config | Kiểm tra query, field và analyzer |
| Highlight không nằm trong entity | Đọc source thay vì SearchHit metadata | Đọc highlightFields và map sang DTO |
| Snippet chứa HTML không an toàn | Render fragment trực tiếp | Escape/sanitize theo chính sách frontend |
| Aggregation đếm nhiều hơn hits | Query và post_filter có semantics khác | Xác định tập dữ liệu aggregation cần dùng |
| Terms bucket thiếu category | Terms size quá nhỏ | Tăng size có kiểm soát hoặc dùng composite |
| Count bucket không chính xác tuyệt đối | Distributed terms aggregation có sai số | Xem shard_size/error bound hoặc dùng cách phù hợp |
| Average price sai | Aggregation không có cùng filter | Đưa filter vào query hoặc bucket đúng chỗ |
| Composite bucket lặp | Không dùng after_key trả về hoặc đổi sources | Giữ nguyên sources và after_key |
| Test chạy lúc được lúc không | Fixture, refresh hoặc sort không xác định | Mapping rõ, refresh và tie-breaker |

## 42. Checklist kiểm thử

**Mapping và sort**

- Field sort có mapping đúng kiểu.
- Text sort dùng keyword multi-field.
- Numeric sort là số, không phải chuỗi.
- Missing value có quy tắc rõ.
- Multi-valued field có sort mode phù hợp.
- Nested sort có path và filter đúng.
- Multi-field sort theo đúng thứ tự ưu tiên.
- Có tie-breaker duy nhất.

**Pagination**

- Page đầu, trang giữa và trang cuối đúng kích thước.
- Total hits và total pages đúng.
- Không có ID trùng giữa các trang trên tập dữ liệu cố định.
- Không mất ID trong toàn bộ tập trang.
- Deep pagination xử lý bằng chiến lược phù hợp.
- search_after giữ đầy đủ sort values.
- PIT được mở, dùng và đóng đúng cách nếu cần snapshot.

**Highlight**

- Đúng field được highlight.
- Fragment chứa term khớp.
- Pre/post tags đúng.
- Fragment size và số lượng đúng.
- Entity source không bị thay đổi.
- Response không làm lộ field nhạy cảm.
- Nội dung được render an toàn.

**Aggregation**

- Query filter áp dụng cho aggregation.
- Bucket key và doc_count đúng.
- Metric đúng với fixture.
- Range boundaries được kiểm tra.
- Timezone của date histogram rõ ràng.
- Cardinality được hiểu là ước lượng khi phù hợp.
- Terms size và shard_size được chọn có chủ đích.
- Composite after_key không lặp hoặc bỏ bucket.

**Tích hợp**

- Kiểm tra cả repository và Operations/NativeQuery path thực tế.
- Index test được tạo với mapping explicit.
- Fixture được refresh trước khi search.
- Kiểm tra request có đồng thời sort, pagination, highlight và aggregation.
- Không dùng mock làm bằng chứng duy nhất cho Query DSL thực tế.

## 43. Nguyên tắc thiết kế

Sort, pagination, highlight và aggregation là các phần khác nhau của search response nhưng phải được kiểm thử như một hợp đồng chung:

- Sort cần mapping đúng và thứ tự xác định.
- Pagination cần tie-breaker ổn định; dữ liệu thay đổi có thể cần PIT và search_after.
- Highlight là metadata của hit, cần tách khỏi entity và render an toàn.
- Aggregation được tính theo query/filter semantics; không giả định nó luôn khớp tập hits sau post_filter.
- Search size và terms aggregation size là hai giới hạn khác nhau.
- Terms aggregation trả top buckets; composite phù hợp để duyệt nhiều bucket.
- Test cần dữ liệu fixture có giá trị trùng, biên và phân bố đã biết.
- Integration test phải kiểm tra hành vi Elasticsearch thực tế với mapping của dự án.
- Khi kết hợp bốn tính năng, xác nhận hit IDs, sort order, page boundaries, fragments và bucket counts trong cùng một request.

Một chức năng tìm kiếm đáng tin cậy không chỉ trả đúng danh sách sản phẩm. Nó phải giữ thứ tự ổn định, phân trang không lặp hoặc bỏ sót trong semantics đã chọn, highlight đúng phần văn bản và tính aggregation trên đúng tập tài liệu. Spring Data Elasticsearch cung cấp các abstraction để xây dựng request và đọc SearchHits, còn Elasticsearch quyết định semantics cuối cùng dựa trên mapping và Query DSL. Vì vậy, bộ kiểm thử cần kết hợp unit test cho query builder với integration test có mapping và dữ liệu thật, đồng thời kiểm tra cả bốn tính năng trong một search request hoàn chỉnh.
