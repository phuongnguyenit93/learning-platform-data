# Composite aggregation và phân trang bucket

Composite aggregation của Elasticsearch dùng để nhóm document theo một hoặc nhiều nguồn giá trị và đọc các bucket theo từng trang. Nó đặc biệt hữu ích khi cần duyệt toàn bộ nhóm dữ liệu, chẳng hạn mọi danh mục, mọi cặp danh mục–trạng thái hoặc mọi tổ hợp ngày–khu vực, trong khi `terms` aggregation chủ yếu trả về một số bucket đứng đầu.

Điểm cốt lõi của composite aggregation là **cursor phân trang**. Request đầu tiên khai báo `sources` và `size`. Response trả về các bucket cùng `after_key` nếu còn trang tiếp theo. Request sau gửi `after` bằng chính `after_key` vừa nhận để tiếp tục. Ứng dụng lặp lại cho đến khi không còn bucket.

Composite aggregation không dùng `from`/`size` như phân trang document. Nó phân trang trên tập bucket được tạo bởi aggregation, vì vậy phải quản lý cursor riêng và giữ nguyên thứ tự, cấu trúc của các source giữa các request.

## 1. Vì sao cần Composite aggregation?

Giả sử index `sales` có hàng triệu đơn hàng. Một báo cáo cần thống kê doanh thu theo tất cả danh mục sản phẩm. Có thể dùng `terms` aggregation:

```json
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        }
      }
    }
  }
}
```

Request trên chỉ trả tối đa 20 bucket theo cấu hình `terms.size`. Nó phù hợp với dashboard cần top 20 danh mục, nhưng không phải cơ chế phân trang để lấy lần lượt mọi danh mục.

Nếu có hàng nghìn hoặc hàng trăm nghìn tổ hợp cần đọc, tăng `terms.size` lên một con số rất lớn có thể làm tăng bộ nhớ và tải cluster. Composite aggregation được thiết kế để duyệt bucket theo trang, dùng `after_key` để tiếp tục từ vị trí trước đó.

### Khi nào dùng Composite aggregation?

- Export toàn bộ nhóm kết quả sang CSV, data warehouse hoặc hệ thống báo cáo.
- Duyệt mọi tổ hợp giá trị của nhiều field, ví dụ `category` + `status`.
- Tính thống kê theo từng ngày và từng tenant.
- Đồng bộ facet có cardinality cao theo từng batch.
- Xử lý ngoại tuyến các nhóm mà không thể trả tất cả bucket trong một response.

### Khi nào dùng `terms` aggregation?

- Cần top N bucket theo số document hoặc metric.
- Số bucket nhỏ và đã biết giới hạn.
- Giao diện chỉ hiển thị vài facet phổ biến nhất.
- Không cần duyệt toàn bộ bucket theo cursor.

Composite aggregation thường trả các bucket theo thứ tự key xác định bởi các source, không phải tự động chọn top bucket theo `doc_count`. Nếu mục tiêu là top danh mục bán chạy nhất, `terms` aggregation với order phù hợp thường là lựa chọn trực tiếp hơn.

## 2. Cấu trúc của Composite aggregation

Composite aggregation gồm ba thành phần chính:

1. `sources`: danh sách nguồn tạo key cho bucket. Mỗi source có tên và kiểu như `terms`, `histogram`, `date_histogram` hoặc `geotile_grid`.
2. `size`: số bucket tối đa được trả về trong một trang.
3. `after`: cursor dùng để bắt đầu sau key đã xử lý ở trang trước.

Response có thể chứa:

- `buckets`: các bucket trong trang hiện tại.
- `key`: object chứa giá trị của từng source trong bucket.
- `doc_count`: số document thuộc bucket.
- Các sub-aggregation nếu request khai báo.
- `after_key`: cursor cho trang kế tiếp nếu còn dữ liệu.

Ví dụ một bucket có hai chiều:

```json
{
  "key": {
    "category": "books",
    "status": "PAID"
  },
  "doc_count": 125
}
```

Key ở đây là tổ hợp `category = books` và `status = PAID`. Mỗi tổ hợp giá trị của các source tạo thành một bucket riêng.

## 3. Ví dụ một chiều: phân trang theo category

Request đầu tiên:

```http
POST /sales/_search
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "sales_by_category": {
      "composite": {
        "size": 2,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          }
        ]
      },
      "aggs": {
        "total_amount": {
          "sum": {
            "field": "amount"
          }
        }
      }
    }
  }
}
```

`size: 0` ở cấp search request nghĩa là không cần document hits. `composite.size: 2` nghĩa là mỗi trang aggregation trả tối đa hai bucket. Hai `size` này nằm ở hai cấp khác nhau và không thay thế nhau.

Response rút gọn có thể như sau:

```json
{
  "hits": {
    "hits": []
  },
  "aggregations": {
    "sales_by_category": {
      "after_key": {
        "category": "electronics"
      },
      "buckets": [
        {
          "key": { "category": "books" },
          "doc_count": 125,
          "total_amount": { "value": 82500.0 }
        },
        {
          "key": { "category": "electronics" },
          "doc_count": 98,
          "total_amount": { "value": 194000.0 }
        }
      ]
    }
  }
}
```

`after_key` được Elasticsearch trả về để tiếp tục phân trang. Hãy lưu nguyên object này để dùng trong request kế tiếp.

## 4. Request tiếp theo với `after`

Giả sử response trang đầu trả về:

```json
{
  "category": "electronics"
}
```

Request trang thứ hai thêm `after`:

```http
POST /sales/_search
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "sales_by_category": {
      "composite": {
        "size": 2,
        "after": {
          "category": "electronics"
        },
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          }
        ]
      },
      "aggs": {
        "total_amount": {
          "sum": {
            "field": "amount"
          }
        }
      }
    }
  }
}
```

Request thứ hai phải giữ nguyên tên aggregation, thứ tự và định nghĩa `sources`, kiểu field, query filter và các cấu hình ảnh hưởng đến bucket. Chỉ thay `after` bằng cursor mới nhận được.

Không tự lấy key của bucket cuối cùng rồi đoán cursor. Elasticsearch có thể trả `after_key` khác key của bucket cuối; hãy luôn dùng chính xác `after_key` từ response.

## 5. Phân trang nhiều chiều

Composite aggregation có thể kết hợp nhiều source. Ví dụ báo cáo số đơn theo danh mục và trạng thái:

```http
POST /sales/_search
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "by_category_and_status": {
      "composite": {
        "size": 3,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          },
          {
            "status": {
              "terms": {
                "field": "status"
              }
            }
          }
        ]
      }
    }
  }
}
```

Mỗi bucket có key gồm hai thành phần:

```json
{
  "key": {
    "category": "books",
    "status": "PAID"
  },
  "doc_count": 125
}
```

Nếu có 5 category và 3 status, về lý thuyết có thể có tối đa 15 tổ hợp, nhưng chỉ các tổ hợp có document mới xuất hiện mặc định. Composite trả các tổ hợp theo thứ tự key; `size: 3` lấy tối đa ba bucket trong một trang.

### Thứ tự source có ý nghĩa

Thứ tự khai báo source quyết định thứ tự sắp xếp key của composite. Nếu đổi thứ tự `category` và `status` giữa hai request, cursor `after` trước đó không còn tương ứng với cùng cấu trúc phân trang.

Do đó, trong suốt một lượt scan:

- Giữ nguyên tên source.
- Giữ nguyên thứ tự source.
- Giữ nguyên loại aggregation của mỗi source.
- Giữ nguyên sort order của từng source.
- Chỉ cập nhật cursor `after`.

## 6. Các loại composite source

Composite aggregation hỗ trợ nhiều kiểu nguồn để tạo key.

| Source | Dùng cho | Ví dụ |
|---|---|---|
| `terms` | Nhóm theo giá trị chính xác của field | `category`, `status`, `tenantId` |
| `histogram` | Nhóm số theo khoảng đều nhau | Giá theo bước 100, số lượng theo bước 10 |
| `date_histogram` | Nhóm ngày giờ theo lịch hoặc khoảng cố định | Doanh thu theo ngày/tháng |
| `geotile_grid` | Nhóm vị trí địa lý theo ô bản đồ | Số sự kiện theo tile |

### Terms source

```json
{
  "category": {
    "terms": {
      "field": "category"
    }
  }
}
```

Thường dùng với `keyword`, numeric hoặc field có giá trị chính xác. Với field text cần nhóm theo toàn bộ giá trị, dùng subfield `keyword`.

### Histogram source

```json
{
  "price_range": {
    "histogram": {
      "field": "price",
      "interval": 100
    }
  }
}
```

Các key được tạo theo interval số. Đây là nhóm khoảng đều nhau, không phải danh sách range tùy ý.

### Date histogram source

```json
{
  "month": {
    "date_histogram": {
      "field": "createdAt",
      "calendar_interval": "month",
      "time_zone": "Asia/Ho_Chi_Minh",
      "format": "yyyy-MM"
    }
  }
}
```

`calendar_interval` phù hợp với kỳ lịch như ngày/tháng; `fixed_interval` phù hợp với khoảng thời gian cố định. `time_zone` quyết định ranh giới bucket theo timezone mong muốn. `format` ảnh hưởng cách key được hiển thị dưới dạng chuỗi, không thay đổi bản chất thời điểm.

### Geotile grid source

```json
{
  "tile": {
    "geotile_grid": {
      "field": "location",
      "precision": 7
    }
  }
}
```

Dùng với field `geo_point` hoặc `geo_shape` phù hợp. Precision cao tạo tile nhỏ hơn và có thể tạo nhiều bucket hơn.

## 7. `after_key` là cursor, không phải số trang

Composite pagination không có `page=1`, `page=2` như phân trang giao diện. `after_key` là object chứa key của vị trí tiếp tục trong thứ tự composite.

Ví dụ với hai source:

```json
{
  "category": "electronics",
  "status": "PAID"
}
```

Ứng dụng lưu nguyên object này và gửi lại trong `after`:

```json
{
  "after": {
    "category": "electronics",
    "status": "PAID"
  }
}
```

Không chuyển cursor thành một số offset, không chỉ lưu một phần key và không tự sắp xếp lại các thuộc tính. Cần giữ đủ tên source và giá trị đúng kiểu.

### Không suy diễn `after_key` từ bucket cuối

Elasticsearch ghi rõ `after_key` không nhất thiết giống key của bucket cuối cùng được trả về. Vì vậy, cách an toàn là lấy `after_key` từ response và dùng nguyên trạng cho request kế tiếp.

### Khi nào kết thúc?

Thông thường, lặp cho đến khi response không còn bucket. Không chỉ dựa vào việc trang hiện tại có ít bucket hơn `size`; việc kết thúc nên dựa vào response và cursor thực tế. Một trang có thể có đúng `size` bucket và vẫn còn trang tiếp theo.

## 8. `missing_bucket` và dữ liệu thiếu field

Mặc định, composite source bỏ qua document không có giá trị được lập chỉ mục cho source field. Nếu cần tạo bucket đại diện cho giá trị thiếu, có thể bật `missing_bucket`:

```json
{
  "category": {
    "terms": {
      "field": "category",
      "missing_bucket": true,
      "missing_order": "last"
    }
  }
}
```

Khi bật, bucket có thể có key `null` cho source đó. `missing_order` điều khiển vị trí của bucket thiếu trong thứ tự, nếu được cấu hình và hỗ trợ bởi kiểu source/version tương ứng.

Phân biệt rõ:

- Field không tồn tại.
- Field được ghi với JSON `null`.
- Field có chuỗi rỗng `""`.
- Field có một giá trị sentinel do ứng dụng quy ước.

Elasticsearch thường không lập chỉ mục JSON null như một giá trị term thông thường, trừ khi mapping có `null_value`. Vì vậy, bucket thiếu không nhất thiết phân biệt được mọi trường hợp nguồn dữ liệu null theo cách của SQL.

## 9. Thứ tự key và sắp xếp bucket

Composite aggregation sắp xếp bucket theo thứ tự của các source, theo cấu hình từng source. Với `terms` source, có thể cấu hình `order` tăng hoặc giảm:

```json
{
  "category": {
    "terms": {
      "field": "category",
      "order": "desc"
    }
  }
}
```

Khi có nhiều source, source đầu tiên có mức ưu tiên sắp xếp trước; nếu key source đầu bằng nhau thì xét source kế tiếp. Đây là thứ tự key để phân trang, không phải thứ tự theo `doc_count` hoặc metric sub-aggregation.

Nếu cần xếp hạng top bucket theo doanh thu, `terms` aggregation với `order` theo metric có thể phù hợp hơn. Composite được thiết kế để duyệt key space theo cursor, không phải để tìm top N theo một metric tùy ý.

## 10. Sub-aggregation bên trong composite bucket

Composite aggregation có thể chứa sub-aggregation để tính metric cho từng tổ hợp key.

Ví dụ nhóm theo category và status, đồng thời tính tổng doanh thu và giá trung bình:

```json
{
  "size": 0,
  "aggs": {
    "sales_groups": {
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
            "status": {
              "terms": {
                "field": "status"
              }
            }
          }
        ]
      },
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
        }
      }
    }
  }
}
```

Mỗi bucket sẽ chứa `key`, `doc_count`, `total_amount` và `average_amount`. Khi chuyển trang, sub-aggregation được tính cho các bucket của trang hiện tại. Ứng dụng có thể xử lý và ghi từng bucket ra đích trước khi lấy trang tiếp theo.

### Sub-aggregation không làm thay đổi cursor

Cursor được tạo từ composite key sources, không phải từ metric. Không dùng `total_amount` hoặc `doc_count` để tự tạo `after`.

## 11. Phạm vi document được tổng hợp

Query ở cấp cao nhất giới hạn tập document đầu vào cho composite aggregation. Ví dụ chỉ thống kê đơn hàng đã thanh toán trong một khoảng thời gian:

```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PAID"
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "2026-01-01T00:00:00Z",
              "lt": "2026-02-01T00:00:00Z"
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "sales_groups": {
      "composite": {
        "size": 100,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          }
        ]
      }
    }
  }
}
```

Mọi trang composite tiếp theo phải giữ nguyên query filter. Nếu đổi query giữa các trang, cursor có thể tiếp tục trên một tập bucket khác và kết quả scan sẽ không còn nhất quán về mặt logic.

## 12. Ví dụ dữ liệu và kết quả nhiều chiều

Giả sử dữ liệu:

| Order | Category | Status | Amount |
|---|---|---|---:|
| o-1 | books | PAID | 100 |
| o-2 | books | PAID | 200 |
| o-3 | books | PENDING | 50 |
| o-4 | electronics | PAID | 500 |
| o-5 | electronics | PENDING | 150 |
| o-6 | toys | PAID | 80 |

Composite sources gồm `category` và `status` sẽ tạo các bucket:

| Key category | Key status | `doc_count` | Tổng amount |
|---|---|---:|---:|
| books | PAID | 2 | 300 |
| books | PENDING | 1 | 50 |
| electronics | PAID | 1 | 500 |
| electronics | PENDING | 1 | 150 |
| toys | PAID | 1 | 80 |

Với `size: 2`, ứng dụng có thể nhận hai bucket đầu tiên, lưu cursor `after_key`, rồi lấy các bucket còn lại ở trang sau. Composite không tạo bucket cho tổ hợp `toys + PENDING` vì không có document khớp tổ hợp đó, trừ khi cấu hình và dữ liệu có cách biểu diễn tương ứng.

## 13. Dùng Composite aggregation trong Spring Data Elasticsearch

Spring Data Elasticsearch tích hợp Elasticsearch Java API Client qua `NativeQuery`. Composite aggregation được khai báo bằng kiểu `Aggregation` của ELC và gắn vào query bằng `withAggregation(name, aggregation)`.

Ví dụ minh họa một composite aggregation theo category:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.aggregations.CompositeAggregationSource;
import co.elastic.clients.elasticsearch._types.aggregations.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

import java.util.List;
import java.util.Map;

Map<String, FieldValue> afterKey = null;

Aggregation compositeAggregation = Aggregation.of(a -> a.composite(c -> {
    c.size(100);
    c.sources(List.of(
        Map.of("category", CompositeAggregationSource.of(s -> s
            .terms(t -> t.field("category"))
        ))
    ));
    if (afterKey != null) {
        c.after(afterKey);
    }
    return c;
}));

Query query = NativeQuery.builder()
    .withMaxResults(0)
    .withAggregation("sales_by_category", compositeAggregation)
    .build();
```

Đoạn code cho thấy các thành phần chính: `CompositeAggregationSource` định nghĩa từng source, `size` đặt số bucket mỗi trang và `after` nhận cursor. Cú pháp builder cụ thể của ELC có thể khác theo phiên bản Elasticsearch Java API Client mà Spring Data đang quản lý; hãy dùng Javadoc của dependency thực tế nếu overload `sources` hoặc kiểu `after` khác. Không trộn lớp từ `RestHighLevelClient` cũ với package `co.elastic.clients` của ELC.

Với phiên bản có `NativeQueryBuilder.withMaxResults(0)`, có thể đặt số document hits tối đa bằng 0 khi chỉ cần aggregation. Nếu API version dùng cách cấu hình khác, mục tiêu ở tầng REST vẫn là `size: 0`.

### Composite aggregation với nhiều source

Khai báo thêm source `status`:

```java
Aggregation compositeAggregation = Aggregation.of(a -> a.composite(c -> c
    .size(100)
    .sources(List.of(
        Map.of("category", CompositeAggregationSource.of(s -> s
            .terms(t -> t.field("category"))
        )),
        Map.of("status", CompositeAggregationSource.of(s -> s
            .terms(t -> t.field("status"))
        ))
    ))
));
```

Khi phân trang, `afterKey` cần có đủ cả `category` và `status`. Không chỉ gửi source đầu tiên.

## 14. Đọc composite buckets trong Spring Data

Sau khi thực thi:

```java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<SaleDocument> hits = operations.search(query, SaleDocument.class);

if (hits.getAggregations() instanceof ElasticsearchAggregations aggregations) {
    var composite = aggregations
        .get("sales_by_category")
        .aggregation()
        .composite();

    for (var bucket : composite.buckets().array()) {
        Map<String, FieldValue> key = bucket.key();
        long documentCount = bucket.docCount();

        String category = key.get("category").stringValue();
    }

    Map<String, FieldValue> nextAfterKey = composite.afterKey();
}
```

`ElasticsearchAggregations` là container của Spring Data cho aggregation response ELC. `aggregation().composite()` lấy biến thể composite; `buckets().array()` chứa các bucket của trang hiện tại; `bucket.key()` là map các giá trị source; `docCount()` là số document trong bucket; `afterKey()` là cursor tiếp theo nếu response có trả về.

Với source có kiểu số, ngày hoặc geo, đọc `FieldValue` theo kiểu tương ứng. Ví dụ `longValue()`, `doubleValue()` hoặc `stringValue()` tùy kiểu key. Không gọi `stringValue()` cho mọi source nếu key thực tế là số hoặc null.

Khi response không có `afterKey`, hoặc trang tiếp theo không có bucket, scan đã kết thúc. Cần xử lý trường hợp `afterKey()` có thể null/empty và không giả định luôn có cursor.

## 15. Vòng lặp phân trang bucket trong ứng dụng

Quy trình tổng quát:

```text
afterKey = null

do:
    query = buildCompositeQuery(afterKey)
    response = execute(query)
    aggregation = readComposite(response)

    for each bucket in aggregation.buckets:
        process(bucket.key, bucket.doc_count, bucket.metrics)

    afterKey = aggregation.after_key

while afterKey exists and current page has buckets
```

Ví dụ pseudocode Java:

```java
Map<String, FieldValue> after = null;

while (true) {
    Query query = buildCompositeQuery(after);
    SearchHits<SaleDocument> hits = operations.search(query, SaleDocument.class);

    ElasticsearchAggregations aggregations =
        (ElasticsearchAggregations) hits.getAggregations();

    var composite = aggregations
        .get("sales_by_category")
        .aggregation()
        .composite();

    var buckets = composite.buckets().array();
    if (buckets.isEmpty()) {
        break;
    }

    for (var bucket : buckets) {
        processBucket(bucket);
    }

    after = composite.afterKey();
    if (after == null || after.isEmpty()) {
        break;
    }
}
```

`buildCompositeQuery(after)` phải tạo lại đúng cùng một aggregation definition và chỉ thay cursor. Trong code thực tế, nên kiểm tra container/aggregation tồn tại và đúng kiểu trước khi cast; phần ví dụ tập trung vào vòng lặp cursor.

Nếu response trả trang có bucket nhưng không có `after_key`, đó thường là trang cuối. Nếu API version hoặc wrapper biểu diễn cursor khác, hãy kiểm tra response JSON và accessor tương ứng.

## 16. Lưu cursor để tiếp tục job

Nếu job chỉ chạy liên tục trong một process, có thể giữ `after_key` trong bộ nhớ. Nếu job cần restart sau sự cố, có thể lưu cursor bền vững cùng metadata của job:

```json
{
  "jobId": "monthly-sales-export-2026-01",
  "index": "sales-2026-01",
  "aggregation": "sales_groups",
  "pageSize": 500,
  "afterKey": {
    "category": "electronics",
    "status": "PAID"
  },
  "processedBuckets": 1500,
  "updatedAt": "2026-02-01T02:15:00Z"
}
```

Để resume chính xác, ngoài cursor cần lưu cả định nghĩa logic của scan:

- Index hoặc alias nguồn.
- Query filter và khoảng thời gian.
- Danh sách source, thứ tự và kiểu của từng source.
- Page size và cấu hình order.
- Phiên bản job hoặc schema.
- Trạng thái output đã ghi thành công.

Nếu đổi source, filter hoặc index mà vẫn dùng cursor cũ, vị trí tiếp tục không còn tương ứng với cùng một tập bucket.

### Lưu cursor và kết quả phải nhất quán

Giả sử ứng dụng ghi bucket vào database đích rồi mới lưu `after_key`. Nếu process chết sau khi ghi bucket nhưng trước khi lưu cursor, bucket có thể được xử lý lại. Vì vậy, ghi output nên idempotent hoặc có khóa duy nhất dựa trên composite key.

Ngược lại, nếu lưu cursor trước khi ghi output và process chết sau đó, bucket có thể bị bỏ qua. Hãy xác định thứ tự commit và thiết kế idempotency/checkpoint phù hợp.

## 17. Dữ liệu thay đổi trong lúc phân trang

Mỗi trang composite là một search request riêng. Nếu index thay đổi giữa các request, các bucket có thể thay đổi theo dữ liệu mới, dẫn đến kết quả scan không còn tương ứng với một snapshot duy nhất.

Ví dụ:

- Trang đầu đã đọc bucket `books`.
- Trong lúc job chạy, một document mới được thêm vào bucket `books`.
- Request sau có thể không tính lại bucket đã đọc ở trang trước.
- Một key mới được thêm vào vùng key chưa đọc có thể xuất hiện ở trang sau.

Nếu cần báo cáo nhất quán:

- Chạy trên index bất biến hoặc index đã đóng ghi trong suốt quá trình export.
- Giới hạn dữ liệu bằng watermark/time range đã chốt.
- Dùng snapshot/PIT trong cùng luồng search nếu phiên bản Elasticsearch hỗ trợ kết hợp PIT với aggregation và ứng dụng giữ đúng PIT ID.
- Hoặc tạo bản sao dữ liệu ổn định trước khi tổng hợp.

PIT là cơ chế snapshot của search context, không phải cursor thay thế `after_key`. Khi kết hợp được trong phiên bản triển khai, PIT giữ góc nhìn dữ liệu; composite `after_key` vẫn dùng để đi tiếp giữa các bucket. Cần kiểm tra khả năng tương thích và vòng đời PIT theo version Elasticsearch đang chạy.

## 18. Composite aggregation và `terms` aggregation

| Tiêu chí | `terms` | `composite` |
|---|---|---|
| Mục tiêu | Top bucket theo số lượng hoặc metric | Duyệt bucket theo key và phân trang |
| Giới hạn trả về | `size` bucket đầu | `size` bucket mỗi trang |
| Cursor | Không có cơ chế `after_key` phân trang đầy đủ | Có `after_key` và `after` |
| Thứ tự mặc định | Theo `doc_count` giảm dần | Theo key của source |
| Nhiều chiều | Có thể lồng bucket aggregation | Nhiều source tạo key tổ hợp phẳng |
| Duyệt toàn bộ bucket | Không phải lựa chọn chính | Là mục đích thiết kế chính |
| Top N theo metric | Phù hợp hơn | Không phù hợp bằng terms |
| Export bucket lớn | Có thể tốn bộ nhớ nếu tăng size lớn | Chia nhỏ theo trang |

Composite không thay thế mọi trường hợp của terms. Chọn theo câu hỏi nghiệp vụ: “top N nhóm nào?” thường dùng terms; “hãy duyệt tất cả nhóm theo key” thường dùng composite.

## 19. Composite aggregation và `bucket_sort`

`bucket_sort` là pipeline aggregation có thể sắp xếp hoặc cắt bớt bucket đã được tạo bởi parent aggregation. Nó không phải cơ chế phân trang toàn bộ key space như composite.

Nếu cần top một số bucket theo metric, có thể cân nhắc terms order theo metric hoặc pipeline phù hợp. Nếu cần lấy lần lượt toàn bộ bucket theo key, dùng composite `after_key`.

Không nên dùng `bucket_sort` để mô phỏng cursor pagination. Nó chỉ xử lý bucket đã được parent aggregation tạo trong request hiện tại; nó không thay thế việc tiếp tục trên key space qua nhiều request.

## 20. Mapping và kiểu dữ liệu của source

Composite aggregation phụ thuộc mapping và doc values của field nguồn.

| Source field | Mapping phù hợp | Lưu ý |
|---|---|---|
| Mã, trạng thái, danh mục | `keyword` | Không dùng text nếu muốn nhóm theo toàn bộ giá trị |
| Số lượng, giá, điểm | `integer`, `long`, `double`, `scaled_float` | Chọn độ chính xác phù hợp nghiệp vụ |
| Thời điểm | `date` hoặc `date_nanos` | Xác định timezone và calendar/fixed interval |
| Vị trí | `geo_point` hoặc `geo_shape` | Dùng geotile grid source phù hợp |

Các field thường cần doc values để aggregation hoạt động hiệu quả. Với keyword và numeric, doc values thường được bật mặc định. Không tắt doc values trên field cần composite aggregation nếu không có lý do cụ thể.

### Multi-valued field

Nếu source field chứa nhiều giá trị trong một document, document có thể tham gia nhiều bucket. Khi composite có nhiều source đa trị, số tổ hợp bucket có thể tăng theo tích các giá trị của từng source.

Ví dụ một document có `tags = [java, spring]` và `regions = [vn, sg]` có thể đóng góp vào các tổ hợp:

```text
(java, vn)
(java, sg)
(spring, vn)
(spring, sg)
```

Điều này có thể làm cardinality bucket tăng nhanh. Hãy kiểm tra dữ liệu multi-valued và chỉ dùng composite nhiều chiều khi ngữ nghĩa tổ hợp là điều nghiệp vụ cần.

## 21. Hiệu năng và giới hạn

Composite aggregation giúp phân trang bucket nhưng không làm phép tổng hợp trở nên miễn phí. Elasticsearch vẫn phải đọc và nhóm dữ liệu phù hợp trên shard để tạo bucket.

Một số nguyên tắc:

- Chọn page size đủ lớn để giảm số round trip nhưng không làm response quá lớn.
- Lọc document bằng query cấp cao nhất trước khi tổng hợp.
- Dùng field có doc values và mapping phù hợp.
- Tránh source có cardinality quá cao nếu không thực sự cần.
- Giảm số sub-aggregation và độ sâu tính toán không cần thiết.
- Chỉ đọc bucket và metric cần cho output.
- Theo dõi thời gian mỗi trang, heap, CPU, search thread pool và tải shard.
- Giới hạn số job composite chạy đồng thời.
- Không tăng page size vô hạn để giảm số request.

Page size lớn làm giảm số lần gọi nhưng tăng số bucket và sub-aggregation trong response. Page size nhỏ làm giảm bộ nhớ cho từng response nhưng tăng overhead round trip. Cần đo với phân bố key và dữ liệu gần production.

### Cardinality và số bucket

Nếu source đầu tiên có 100.000 giá trị và source thứ hai có 20 giá trị, key space lý thuyết có thể rất lớn. Composite chỉ trả một trang mỗi lần, nhưng tổng công việc vẫn tỷ lệ với số bucket cần duyệt. Hãy ước lượng số tổ hợp và xác định có thật sự cần xuất tất cả hay chỉ cần top N.

## 22. Lỗi thường gặp

### Dùng `terms.size` lớn để lấy toàn bộ bucket

Tăng size có thể tạo response lớn, tốn bộ nhớ và vẫn không phải cursor pagination tổng quát. Dùng composite khi cần duyệt toàn bộ bucket.

### Dùng `after` theo key cuối cùng thay vì `after_key`

`after_key` có thể không bằng key cuối trong mảng buckets. Luôn dùng cursor Elasticsearch trả về.

### Thay đổi sources giữa các trang

Đổi tên, thứ tự hoặc kiểu source làm cursor không còn hợp lệ về mặt logic. Giữ nguyên cấu hình aggregation suốt lượt scan.

### Đổi query filter giữa các trang

Cursor được tạo cho key space của query ban đầu. Thay filter giữa chừng có thể bỏ sót hoặc lặp bucket. Giữ query nhất quán.

### Dừng khi trang có ít bucket hơn size

Không dùng số lượng bucket ít hơn page size làm điều kiện duy nhất để kết thúc. Kiểm tra `after_key` và trang tiếp theo theo response thực tế.

### Nhầm composite với top N

Composite duyệt theo key; nó không tự xếp hạng theo doanh thu hoặc `doc_count`. Dùng terms nếu mục tiêu là top bucket theo metric.

### Bỏ qua bucket thiếu field

Mặc định document thiếu source value có thể không tham gia bucket. Nếu cần nhóm giá trị thiếu, cân nhắc `missing_bucket: true` và quy tắc `missing_order`.

### Xử lý output không idempotent

Nếu job restart và đọc lại trang trước, cùng bucket có thể được ghi trùng. Dùng composite key làm khóa duy nhất hoặc transaction/checkpoint phù hợp.

### Để dữ liệu thay đổi giữa các trang

Các request độc lập có thể nhìn thấy dữ liệu khác nhau. Với export cần snapshot, dùng index bất biến, watermark hoặc PIT tương thích.

## 23. Kiểm thử phân trang composite

Nên chuẩn bị dữ liệu có:

- Nhiều key hơn page size để buộc phải có nhiều trang.
- Nhiều source để kiểm tra key tổ hợp.
- Document thiếu một source field.
- Field multi-valued nếu hệ thống thực sự dùng dạng dữ liệu này.
- Bucket có metric sub-aggregation.
- Các key nằm sát ranh giới thứ tự.

Các hành vi cần xác nhận:

1. Trang đầu trả tối đa page size bucket.
2. `after_key` của trang đầu được truyền nguyên vẹn vào `after` trang sau.
3. Không có bucket nào bị lặp giữa các trang trong một tập dữ liệu ổn định.
4. Không có bucket nào bị bỏ sót.
5. Tổ hợp nhiều source có key đúng và giữ đúng thứ tự.
6. Sub-aggregation được đọc đúng cho từng bucket.
7. Bucket thiếu field xuất hiện hoặc bị loại đúng theo `missing_bucket`.
8. Vòng lặp kết thúc khi không còn bucket/cursor.
9. Restart từ cursor đã lưu không ghi trùng output.
10. Query filter được giữ nguyên giữa các trang.

Không chỉ kiểm tra tổng số bucket. Hãy so sánh tập composite key duy nhất giữa kết quả scan và tập kỳ vọng từ dữ liệu fixture.

## 24. Quy trình triển khai export bucket

Một job export có thể thực hiện theo trình tự:

1. Xác định index/alias và query filter của tập dữ liệu.
2. Chọn các source và thứ tự key cần nhóm.
3. Chọn page size dựa trên số bucket, kích thước sub-aggregation và khả năng xử lý.
4. Gửi request đầu tiên không có `after`.
5. Đọc buckets, chuyển key/metric thành DTO hoặc record output.
6. Ghi output theo cách idempotent dựa trên composite key.
7. Lấy `after_key` từ response và lưu checkpoint nếu cần resume.
8. Gửi request tiếp theo với `after` bằng cursor mới nhất.
9. Lặp đến khi không còn bucket hoặc cursor.
10. Đóng PIT nếu có sử dụng snapshot.
11. Ghi nhận tổng số bucket, thời gian và trạng thái hoàn tất.

## 25. Kết luận

Composite aggregation là cơ chế phân trang bucket dành cho trường hợp cần duyệt toàn bộ các nhóm dữ liệu hoặc các tổ hợp nhiều field. Request khai báo `sources` và `size`; response trả `buckets` cùng `after_key`; request tiếp theo gửi chính cursor đó trong `after`. Luôn dùng `after_key` do Elasticsearch trả về, không tự suy ra từ bucket cuối và giữ nguyên định nghĩa source/query giữa các trang.

Trong Spring Data Elasticsearch, composite aggregation được khai báo qua `NativeQuery` và Elasticsearch Java API Client, sau đó đọc từ `SearchHits.getAggregations()` thông qua `ElasticsearchAggregations`. Mỗi bucket chứa composite key, `doc_count` và có thể có metric sub-aggregation. `terms` phù hợp với top N, còn composite phù hợp với cursor scan toàn bộ bucket. Khi triển khai job dài, cần thiết kế checkpoint, output idempotent và cách xử lý dữ liệu thay đổi giữa các trang; page size phải được chọn dựa trên đo lường thực tế.

## Tài liệu tham khảo

- [Elasticsearch – Composite aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-composite-aggregation)
- [Elasticsearch – Terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-terms-aggregation)
- [Elasticsearch – Date histogram aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-datehistogram-aggregation)
- [Elasticsearch – Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Spring Data Elasticsearch – NativeQuery and search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – ElasticsearchAggregations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregations.html)
