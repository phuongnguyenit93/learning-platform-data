# Aggregation lồng nhau và kết hợp metric với bucket

Elasticsearch Aggregations giúp tổng hợp dữ liệu ngay trên cluster: nhóm document theo danh mục, trạng thái hoặc khoảng thời gian; sau đó tính tổng, trung bình, min/max, số lượng hoặc các chỉ số thống kê trên từng nhóm. Khi một aggregation chứa aggregation con, kết quả có thể biểu diễn nhiều cấp phân tích trong cùng một search request.

Hai loại aggregation cơ bản là **bucket aggregation** và **metric aggregation**:

- Bucket aggregation chia document thành các nhóm (bucket) theo một tiêu chí, ví dụ `terms`, `range`, `date_histogram`, `filters` hoặc `nested`.
- Metric aggregation tính một hoặc nhiều giá trị trên tập document nằm trong bucket, ví dụ `sum`, `avg`, `min`, `max`, `stats`, `cardinality` hoặc `value_count`.

Kết hợp chúng cho phép trả lời các câu hỏi như:

- Mỗi danh mục có bao nhiêu sản phẩm và giá trung bình là bao nhiêu?
- Doanh thu từng tháng theo từng kênh bán hàng là bao nhiêu?
- Trong mỗi danh mục, điểm đánh giá trung bình của các review là bao nhiêu?
- Mỗi thương hiệu có bao nhiêu sản phẩm theo từng trạng thái?
- Trung bình doanh thu của các tháng là bao nhiêu?

Trong Spring Data Elasticsearch, có thể xây dựng aggregation bằng Elasticsearch Java API Client DSL rồi gắn vào `NativeQuery`, thực thi qua `ElasticsearchOperations` và đọc kết quả từ `SearchHits.getAggregations()`.

## 1. Hai khái niệm “lồng nhau” cần phân biệt

Trong Elasticsearch, cụm từ aggregation lồng nhau có thể nói đến hai cơ chế khác nhau:

1. **Aggregation con (sub-aggregation):** đặt bucket hoặc metric aggregation bên trong một bucket aggregation khác để phân tích nhiều cấp. Ví dụ: nhóm theo danh mục, trong mỗi danh mục nhóm tiếp theo theo thương hiệu, rồi tính giá trung bình.
2. **Nested aggregation:** chuyển phạm vi tính toán từ document cha sang các nested document trong một field được mapping kiểu `nested`. Ví dụ: từ product chuyển sang các review của product để tính rating trung bình.

Hai cơ chế có thể được dùng đồng thời. Một bucket theo danh mục có thể chứa nested aggregation để phân tích review của sản phẩm trong từng danh mục.

```text
Search request
    |
    v
Bucket: group by category
    |
    +-- Metric: average product price
    |
    +-- Bucket: group by brand
    |       |
    |       +-- Metric: product count / max price
    |
    +-- Nested: enter reviews
            |
            +-- Metric: average review rating
            |
            +-- Bucket: group by reviewer
```

## 2. Bucket aggregation là gì?

Bucket aggregation phân document thành các nhóm theo điều kiện. Mỗi bucket có `doc_count`, là số document thuộc bucket đó trong phạm vi aggregation.

Các bucket aggregation thường gặp:

| Aggregation | Cách chia nhóm | Ví dụ |
|---|---|---|
| `terms` | Theo từng giá trị khác nhau của field. | Nhóm sản phẩm theo `category`. |
| `range` | Theo các khoảng số hoặc ngày. | Nhóm đơn hàng theo khoảng giá trị. |
| `date_histogram` | Theo khoảng thời gian đều nhau. | Doanh thu theo ngày/tháng. |
| `filters` | Theo các query filter do ứng dụng định nghĩa. | Nhóm đơn hàng theo các trạng thái nghiệp vụ. |
| `filter` | Một bucket chứa document thỏa một điều kiện. | Chỉ tổng hợp đơn hàng `PAID`. |
| `nested` | Chuyển sang các nested document của một path. | Tổng hợp review trong product. |
| `reverse_nested` | Từ nested document quay lại document cha. | Đếm/tính metric trên product có review phù hợp. |
| `composite` | Tạo bucket theo nhiều nguồn và cho phép phân trang bucket. | Export thống kê tất cả cặp category/brand. |

### 2.1. `terms` aggregation

`terms` tạo một bucket cho mỗi giá trị khác nhau của field:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 10
      }
    }
  }
}
```

Kết quả có một bucket cho mỗi danh mục được trả về, kèm `key` và `doc_count`. `size: 10` trong `terms` là số bucket tối đa được trả về, không phải số document trong mỗi bucket.

Field dùng cho `terms` thường là `keyword`, numeric hoặc kiểu phù hợp cho aggregation. Không dùng field `text` thông thường để group theo toàn bộ chuỗi; hãy dùng subfield `keyword` hoặc một field có doc values phù hợp.

### 2.2. `range` aggregation

`range` tạo các bucket theo khoảng:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_price_range": {
      "range": {
        "field": "price",
        "ranges": [
          { "to": 1000000 },
          { "from": 1000000, "to": 5000000 },
          { "from": 5000000 }
        ]
      }
    }
  }
}
```

Các khoảng được hiểu theo dạng `[from, to)`: `from` được bao gồm, `to` không được bao gồm. Vì vậy, một sản phẩm giá đúng 1.000.000 thuộc bucket thứ hai trong ví dụ.

### 2.3. `date_histogram` aggregation

`date_histogram` nhóm document theo ngày, tuần, tháng hoặc khoảng thời gian:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_month": {
      "date_histogram": {
        "field": "created_at",
        "calendar_interval": "month",
        "time_zone": "Asia/Ho_Chi_Minh"
      }
    }
  }
}
```

`calendar_interval` phù hợp với lịch (ngày/tháng/năm); `fixed_interval` phù hợp với khoảng thời gian cố định như 15 phút hoặc 1 giờ. Nếu báo cáo theo ngày nghiệp vụ, hãy xác định timezone rõ ràng để tránh bucket lệch ngày khi dữ liệu lưu UTC.

## 3. Metric aggregation là gì?

Metric aggregation tính giá trị trên các document trong phạm vi hiện tại. Metric có thể là một giá trị đơn (single-value) hoặc nhiều giá trị (multi-value).

| Metric | Kết quả | Ví dụ |
|---|---|---|
| `sum` | Tổng các giá trị | Tổng doanh thu. |
| `avg` | Trung bình | Giá trung bình sản phẩm. |
| `min` / `max` | Nhỏ nhất/lớn nhất | Giá thấp nhất/cao nhất. |
| `value_count` | Số giá trị được đếm | Số giá trị của field có mặt. |
| `cardinality` | Số giá trị phân biệt ước lượng | Số khách hàng khác nhau. |
| `stats` | `count`, `min`, `max`, `avg`, `sum` | Thống kê giá. |
| `extended_stats` | Stats mở rộng, gồm độ lệch chuẩn và các giá trị liên quan | Phân tích phân phối giá. |
| `percentiles` | Các phân vị | P50, P90, P95 của thời gian xử lý. |
| `weighted_avg` | Trung bình có trọng số | Giá trung bình theo số lượng bán. |

Metric aggregation không tạo bucket mới. Nó trả kết quả tính toán trong phạm vi document mà query hoặc bucket cha đã xác định.

Ví dụ `avg` trên toàn bộ sản phẩm:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
```

Nếu field thiếu hoặc không có giá trị numeric, document đó không đóng góp giá trị vào metric `avg`. Vì vậy, `avg` không nhất thiết bằng `sum / tổng doc_count` của bucket khi có document thiếu field `price`.

### 3.1. `value_count` không luôn bằng `doc_count`

`doc_count` đếm document trong bucket. `value_count` đếm số giá trị được xem xét của field. Với field đơn trị có mặt trên mọi document, hai số có thể bằng nhau. Với field thiếu hoặc multi-valued, chúng có thể khác nhau.

Ví dụ một document có ba tag sẽ đóng góp ba giá trị cho `value_count(tags)` nhưng chỉ đóng góp một vào `doc_count` của bucket.

### 3.2. `cardinality` là ước lượng

`cardinality` dùng thuật toán HyperLogLog++ để ước lượng số giá trị khác nhau. Nó hữu ích cho tập dữ liệu lớn khi cần distinct count với chi phí thấp hơn việc tạo tất cả bucket, nhưng không nên mặc định kết quả luôn chính xác tuyệt đối.

Nếu nghiệp vụ yêu cầu số lượng phân biệt chính xác, cần chọn giải pháp phù hợp và đánh giá chi phí, ví dụ composite aggregation để duyệt các giá trị distinct theo trang hoặc xử lý ở hệ thống chuyên biệt.

## 4. Kết hợp metric bên trong bucket

Đây là mẫu aggregation phổ biến nhất: bucket chia dữ liệu thành nhóm, metric con tính toán trong từng nhóm.

Ví dụ: đếm số sản phẩm theo danh mục và tính giá trung bình, giá thấp nhất, giá cao nhất của từng danh mục:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 20
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        },
        "minimum_price": {
          "min": {
            "field": "price"
          }
        },
        "maximum_price": {
          "max": {
            "field": "price"
          }
        },
        "price_stats": {
          "stats": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

Kết quả có cấu trúc khái quát:

```json
{
  "aggregations": {
    "by_category": {
      "buckets": [
        {
          "key": "KEYBOARD",
          "doc_count": 120,
          "average_price": { "value": 2450000.0 },
          "minimum_price": { "value": 350000.0 },
          "maximum_price": { "value": 8900000.0 },
          "price_stats": {
            "count": 118,
            "min": 350000.0,
            "max": 8900000.0,
            "avg": 2450000.0,
            "sum": 289100000.0
          }
        }
      ]
    }
  }
}
```

Các số trong response chỉ minh họa. Lưu ý `doc_count` là 120 nhưng `price_stats.count` là 118 vì hai document không có giá trị `price` được tính.

### 4.1. Bucket con bên trong bucket cha

Có thể tiếp tục nhóm theo một field khác. Ví dụ nhóm sản phẩm theo category, rồi trong từng category nhóm theo brand và tính giá trung bình:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 20
      },
      "aggs": {
        "by_brand": {
          "terms": {
            "field": "brand.keyword",
            "size": 10
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
  }
}
```

Kết quả có cấu trúc category → brand → average price. Metric `average_price` được tính riêng trong từng bucket brand, không phải trên toàn bộ category.

Số bucket có thể tăng rất nhanh khi lồng nhiều cấp. Nếu mỗi category có 100 brand và có 100 category, một aggregation có thể tạo hàng nghìn bucket. Cần đặt `size`, giới hạn cardinality và cân nhắc `composite` nếu phải duyệt toàn bộ nhóm.

## 5. Kết hợp nhiều metric trong cùng một bucket

Một bucket có thể chứa nhiều metric aggregation cùng lúc. Ví dụ báo cáo theo trạng thái đơn hàng:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_status": {
      "terms": {
        "field": "status.keyword"
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
        },
        "order_stats": {
          "stats": {
            "field": "amount"
          }
        },
        "unique_customers": {
          "cardinality": {
            "field": "customer_id"
          }
        }
      }
    }
  }
}
```

Mỗi trạng thái có:

- Số đơn hàng trong `doc_count`.
- Tổng tiền trong `total_amount`.
- Giá trị trung bình trong `average_amount`.
- Thống kê chi tiết trong `order_stats`.
- Số khách hàng phân biệt ước lượng trong `unique_customers`.

Đây là cách hiệu quả để xây dựng dashboard nhiều chỉ số trong một request thay vì gửi một search riêng cho từng metric. Tuy nhiên, aggregation nhiều cấp hoặc cardinality cao vẫn có chi phí đáng kể; hãy đo request thật.

## 6. Lọc tập document trước khi bucket và metric

Query ở cấp search xác định tập document đầu vào cho tất cả aggregation. Có thể kết hợp query context và filter context, nhưng nếu dashboard chỉ cần thống kê document thỏa điều kiện nghiệp vụ, thường dùng filter trong `bool` query.

Ví dụ chỉ thống kê đơn hàng đã thanh toán trong quý:

```json
GET /orders/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "PAID" } },
        {
          "range": {
            "created_at": {
              "gte": "2026-07-01T00:00:00Z",
              "lt": "2026-10-01T00:00:00Z"
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword"
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

Tất cả bucket và metric ở đây chỉ nhìn thấy các đơn hàng `PAID` trong khoảng thời gian đã chọn.

### 6.1. Filter aggregation bên trong bucket

Nếu cần nhiều tập con trong cùng một nhóm, dùng `filters` aggregation hoặc `filter` aggregation bên trong bucket.

Ví dụ trong mỗi category, tính riêng doanh thu đơn đã thanh toán và đơn đang chờ:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword"
      },
      "aggs": {
        "by_status": {
          "filters": {
            "filters": {
              "paid": { "term": { "status": "PAID" } },
              "pending": { "term": { "status": "PENDING" } }
            }
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
  }
}
```

Kết quả có bucket `paid` và `pending` trong từng category, mỗi bucket có `doc_count` và metric `revenue` riêng. Khác với filter đặt ở top-level query, filter aggregation chỉ áp dụng cho nhánh aggregation con đó; các nhánh khác của cùng bucket vẫn có thể nhìn thấy tập document rộng hơn.

## 7. Nested aggregation trên field kiểu `nested`

Trong JSON, một product có thể chứa mảng review:

```json
{
  "product_id": "P-100",
  "category": "KEYBOARD",
  "price": 2500000,
  "reviews": [
    { "reviewer": "u1", "rating": 5 },
    { "reviewer": "u2", "rating": 4 }
  ]
}
```

Nếu cần truy vấn và tổng hợp các phần tử trong mảng object một cách độc lập, field `reviews` cần được mapping kiểu `nested`:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "product_id": { "type": "keyword" },
      "category": { "type": "keyword" },
      "price": { "type": "double" },
      "reviews": {
        "type": "nested",
        "properties": {
          "reviewer": { "type": "keyword" },
          "rating": { "type": "integer" },
          "created_at": { "type": "date" }
        }
      }
    }
  }
}
```

`nested` bảo đảm các field của từng phần tử mảng được giữ trong cùng một nested document. Nếu mapping là `object` thông thường, Elasticsearch có thể làm phẳng mảng object và query kết hợp nhiều field có thể khớp chéo giữa các phần tử.

### 7.1. Nested aggregation

Để tính rating trung bình của các review, cần chuyển vào nested path `reviews`:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "review_data": {
      "nested": {
        "path": "reviews"
      },
      "aggs": {
        "average_rating": {
          "avg": {
            "field": "reviews.rating"
          }
        },
        "rating_distribution": {
          "terms": {
            "field": "reviews.rating"
          }
        }
      }
    }
  }
}
```

Sau khi vào `review_data`, các aggregation con chạy trên nested review document thay vì product document. Vì vậy:

- `average_rating` tính trung bình trên các review có rating.
- `rating_distribution` tạo bucket theo giá trị rating.
- `review_data.doc_count` là số nested review document, không phải số product.

### 7.2. Nested aggregation bên trong bucket cha

Có thể nhóm product theo category trước rồi tính review rating trong từng category:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      },
      "aggs": {
        "reviews": {
          "nested": {
            "path": "reviews"
          },
          "aggs": {
            "average_rating": {
              "avg": {
                "field": "reviews.rating"
              }
            },
            "review_count": {
              "value_count": {
                "field": "reviews.rating"
              }
            }
          }
        }
      }
    }
  }
}
```

Trong mỗi category:

- `by_category` bucket chứa product document.
- `reviews` chuyển phạm vi sang nested review document thuộc những product trong category đó.
- `average_rating` tính điểm trung bình của review trong nhóm.
- `review_count` đếm các giá trị rating có mặt.

Đừng so sánh `by_category.doc_count` với `reviews.doc_count` như thể chúng cùng đơn vị. Một product có thể có nhiều review nên số nested document có thể lớn hơn số product.

## 8. `reverse_nested`: quay từ nested document về document cha

Sau khi đi vào nested path, các aggregation con hoạt động trong ngữ cảnh nested document. Nếu cần tính metric trên product cha, dùng `reverse_nested` để quay lại parent document.

Ví dụ: nhóm review theo rating, sau đó đếm số product có ít nhất một review ở mỗi rating và tính giá trung bình của những product đó:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "reviews": {
      "nested": {
        "path": "reviews"
      },
      "aggs": {
        "by_rating": {
          "terms": {
            "field": "reviews.rating"
          },
          "aggs": {
            "products": {
              "reverse_nested": {},
              "aggs": {
                "average_product_price": {
                  "avg": {
                    "field": "price"
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

Kết quả:

- `reviews.doc_count` là số review.
- `by_rating.doc_count` là số nested review có rating tương ứng.
- `products.doc_count` là số product cha có ít nhất một review thuộc bucket rating đó.
- `average_product_price` tính giá trên tập product cha đã quay lại.

Một product có thể có nhiều review cùng rating, nhưng trong `reverse_nested` nó chỉ được tính một lần trong bucket cha tương ứng. Vì vậy số product cha thường không bằng số review.

Có thể chỉ định `path` cho `reverse_nested` khi cần quay đến một nested ancestor cụ thể; nếu bỏ trống, aggregation quay về root document.

## 9. Nested query và nested aggregation không giống nhau

Hai API có tên gần nhau nhưng làm hai việc khác nhau:

- `nested` query xác định parent document nào khớp điều kiện trên nested child.
- `nested` aggregation chuyển phạm vi tổng hợp vào các nested child tương ứng.

Ví dụ tìm product có review rating từ 4 trở lên:

```json
GET /products/_search
{
  "query": {
    "nested": {
      "path": "reviews",
      "query": {
        "range": {
          "reviews.rating": {
            "gte": 4
          }
        }
      }
    }
  },
  "aggs": {
    "matching_reviews": {
      "nested": {
        "path": "reviews"
      },
      "aggs": {
        "high_ratings": {
          "filter": {
            "range": {
              "reviews.rating": {
                "gte": 4
              }
            }
          },
          "aggs": {
            "average_rating": {
              "avg": {
                "field": "reviews.rating"
              }
            }
          }
        }
      }
    }
  }
}
```

Top-level nested query giới hạn tập product cha được trả về. Tuy nhiên, nested aggregation không tự động chỉ lấy các review đã khớp nested query; nó đi vào các review thuộc những product cha trong tập đó. Vì vậy, nếu metric phải chỉ tính review rating từ 4 trở lên, cần thêm `filter` aggregation bên trong nested aggregation như ví dụ.

Đây là lỗi dễ gặp: search hits đúng nhưng aggregation lại tính cả các nested child không thỏa điều kiện chi tiết. Hãy đặt filter đúng cấp nested khi muốn metric chỉ tính một tập review con.

## 10. Pipeline aggregation: tính metric từ kết quả aggregation khác

Metric aggregation thông thường tính trên document field. Pipeline aggregation lại tính toán dựa trên kết quả của các aggregation khác, thường là các bucket/metric đã được tạo.

Một số pipeline aggregation:

| Pipeline aggregation | Mục đích |
|---|---|
| `avg_bucket` | Tính trung bình các metric trong nhiều bucket. |
| `sum_bucket` | Cộng metric từ nhiều bucket. |
| `min_bucket` / `max_bucket` | Tìm giá trị metric nhỏ nhất/lớn nhất giữa các bucket. |
| `stats_bucket` | Thống kê các giá trị metric giữa bucket. |
| `bucket_script` | Tính biểu thức từ một hoặc nhiều metric trong bucket. |
| `bucket_selector` | Giữ hoặc loại bucket theo điều kiện script. |
| `derivative` | Tính mức thay đổi giữa các bucket theo thứ tự. |
| `cumulative_sum` | Tính tổng lũy kế theo bucket. |

Pipeline aggregation không chạy lại query trên document. Nó tiêu thụ kết quả của các aggregation đã được tính trong request.

### 10.1. `avg_bucket`: trung bình metric giữa các bucket

Ví dụ tính giá trung bình của từng category rồi tính trung bình các giá trị trung bình đó:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
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
    },
    "average_of_category_averages": {
      "avg_bucket": {
        "buckets_path": "by_category>average_price"
      }
    }
  }
}
```

`buckets_path` dùng `>` để truy cập metric con `average_price` bên trong bucket aggregation `by_category`.

Lưu ý: trung bình các giá trị trung bình của category không nhất thiết bằng trung bình giá của toàn bộ product. Ví dụ category A có 10 sản phẩm, giá trung bình 100; category B có 100 sản phẩm, giá trung bình 200. Trung bình hai category average là 150, còn trung bình trên 110 sản phẩm là khoảng 190,91. Hãy chọn metric theo đúng câu hỏi nghiệp vụ.

### 10.2. `bucket_script`: tính chỉ số từ nhiều metric

Ví dụ báo cáo doanh thu và số đơn theo tháng, sau đó tính giá trị đơn hàng trung bình (average order value):

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_month": {
      "date_histogram": {
        "field": "created_at",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        },
        "order_count": {
          "value_count": {
            "field": "order_id"
          }
        },
        "average_order_value": {
          "bucket_script": {
            "buckets_path": {
              "total": "revenue",
              "count": "order_count"
            },
            "script": "params.count > 0 ? params.total / params.count : 0"
          }
        }
      }
    }
  }
}
```

Trong mỗi month bucket, `bucket_script` đọc hai metric con:

- `revenue` được gán vào biến `params.total`.
- `order_count` được gán vào biến `params.count`.

Sau đó script tính `total / count`. Điều kiện `count > 0` tránh phép chia cho 0. Nếu `order_id` có thể multi-valued hoặc thiếu, hãy kiểm tra xem `value_count` có thực sự biểu diễn số đơn hàng hay không; một field đơn trị, luôn có mặt hoặc metric phù hợp hơn có thể cần thiết.

### 10.3. `bucket_selector`: lọc bucket theo metric

Nếu chỉ muốn giữ tháng có doanh thu từ 100 triệu trở lên:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_month": {
      "date_histogram": {
        "field": "created_at",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        },
        "minimum_revenue": {
          "bucket_selector": {
            "buckets_path": {
              "total": "revenue"
            },
            "script": "params.total >= 100000000"
          }
        }
      }
    }
  }
}
```

`bucket_selector` loại bucket khỏi kết quả aggregation sau khi các metric đã được tính. Nó không làm giảm số document mà các aggregation trước đó phải xử lý; vì vậy không nên xem nó là filter thay thế cho query/filter aggregation khi mục tiêu là giảm dữ liệu đầu vào.

### 10.4. `derivative` và `cumulative_sum`

Với chuỗi doanh thu theo tháng, có thể tính thay đổi so với tháng trước:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_month": {
      "date_histogram": {
        "field": "created_at",
        "calendar_interval": "month",
        "min_doc_count": 0
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        },
        "revenue_change": {
          "derivative": {
            "buckets_path": "revenue"
          }
        },
        "running_revenue": {
          "cumulative_sum": {
            "buckets_path": "revenue"
          }
        }
      }
    }
  }
}
```

Pipeline này phụ thuộc thứ tự bucket. Với date histogram, thứ tự thời gian được xác định theo key của bucket. Bucket đầu tiên không có bucket trước đó nên derivative thường không có giá trị. `min_doc_count: 0` có thể tạo bucket rỗng trong phạm vi extended bounds phù hợp; nếu cần đầy đủ tháng không có đơn, hãy cấu hình bounds và xử lý giá trị rỗng theo mục tiêu báo cáo.

## 11. Kết hợp nhiều cấp: doanh thu theo tháng và category

Một dashboard có thể cần doanh thu theo từng category trong từng tháng. Có thể lồng `terms` và `date_histogram`, rồi đặt metric `sum` ở cấp cuối:

```json
GET /orders/_search
{
  "size": 0,
  "query": {
    "range": {
      "created_at": {
        "gte": "2026-01-01T00:00:00Z",
        "lt": "2027-01-01T00:00:00Z"
      }
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 20
      },
      "aggs": {
        "by_month": {
          "date_histogram": {
            "field": "created_at",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "order_count": {
              "value_count": {
                "field": "order_id"
              }
            }
          }
        }
      }
    }
  }
}
```

Cấu trúc kết quả:

```text
by_category
  KEYBOARD (bucket)
    by_month
      2026-01 (bucket)
        revenue (sum)
        order_count (value_count)
      2026-02 (bucket)
        revenue (sum)
        order_count (value_count)
  ACCESSORIES (bucket)
    by_month
      2026-01 (bucket)
        revenue (sum)
        order_count (value_count)
```

Khi đọc kết quả, cần duyệt từng bucket category, rồi từng bucket month, sau đó lấy metric của tháng đó. Đừng lấy metric `revenue` ở cấp category nếu nó chỉ được định nghĩa ở cấp month.

## 12. `composite` khi cần duyệt tất cả bucket

`terms` aggregation trả một số lượng bucket giới hạn theo `size` và thường sắp xếp theo document count hoặc key. Nếu có hàng chục nghìn category/brand combinations và cần xuất tất cả, tăng `terms.size` lên rất lớn không phải cách phù hợp.

`composite` aggregation tạo bucket từ một hoặc nhiều nguồn và hỗ trợ phân trang bằng `after` key:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "category_brand": {
      "composite": {
        "size": 500,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category.keyword"
              }
            }
          },
          {
            "brand": {
              "terms": {
                "field": "brand.keyword"
              }
            }
          }
        ]
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
```

Response có thể chứa `after_key`. Để lấy trang bucket tiếp theo, truyền nguyên giá trị đó vào `composite.after`:

```json
{
  "size": 0,
  "aggs": {
    "category_brand": {
      "composite": {
        "size": 500,
        "after": {
          "category": "KEYBOARD",
          "brand": "OMEGA"
        },
        "sources": [
          { "category": { "terms": { "field": "category.keyword" } } },
          { "brand": { "terms": { "field": "brand.keyword" } } }
        ]
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
```

Trong code thực tế, luôn dùng `after_key` do Elasticsearch trả về; không tự tạo từ bucket cuối cùng vì `after_key` không phải lúc nào cũng giống key của bucket cuối response. Nếu cần kết quả nhất quán qua nhiều request composite trong lúc index thay đổi, cần kết hợp chiến lược snapshot phù hợp như PIT theo khả năng phiên bản Elasticsearch hỗ trợ và xác minh semantics của request aggregation.

## 13. Xây dựng aggregation bằng Spring Data Elasticsearch

Spring Data Elasticsearch hiện đại sử dụng Elasticsearch Java API Client cho `NativeQuery`. Kiểu aggregation là `co.elastic.clients.elasticsearch._types.aggregations.Aggregation`.

Ví dụ tạo bucket theo category và metric giá trung bình:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg.field("price"))
);

Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t
                .field("category.keyword")
                .size(20)
        )
        .aggregations("average_price", averagePrice)
);

NativeQuery query = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .withMaxResults(0)
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Ý nghĩa:

- `averagePrice` định nghĩa metric aggregation `avg` trên field `price`.
- `byCategory` định nghĩa bucket `terms` trên `category.keyword`.
- `.aggregations("average_price", averagePrice)` đặt metric làm sub-aggregation bên trong mỗi category bucket.
- `.withAggregation("by_category", byCategory)` gắn aggregation vào search query.
- `.withMaxResults(0)` yêu cầu không lấy document hits nếu chỉ cần aggregation; kiểm tra API builder tương ứng của phiên bản Spring Data đang dùng.

Nếu cần cả document hits và aggregation, đặt max results/pageable theo số hit cần trả thay vì 0.

### 13.1. Nested aggregation bằng Java API Client DSL

Ví dụ tạo nested aggregation để tính rating trung bình:

```java
Aggregation averageRating = Aggregation.of(a -> a
        .avg(avg -> avg.field("reviews.rating"))
);

Aggregation nestedReviews = Aggregation.of(a -> a
        .nested(n -> n.path("reviews"))
        .aggregations("average_rating", averageRating)
);

NativeQuery query = NativeQuery.builder()
        .withAggregation("review_data", nestedReviews)
        .withMaxResults(0)
        .build();
```

Nếu cần bucket theo rating trong nested context, có thể lồng `terms` bên trong `nestedReviews` rồi thêm metric hoặc bucket con tương tự ví dụ Query DSL.

### 13.2. Lồng nhiều bucket và metric

Ví dụ category → brand → average price:

```java
Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg.field("price"))
);

Aggregation byBrand = Aggregation.of(a -> a
        .terms(t -> t.field("brand.keyword").size(10))
        .aggregations("average_price", averagePrice)
);

Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t.field("category.keyword").size(20))
        .aggregations("by_brand", byBrand)
);

NativeQuery query = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .withMaxResults(0)
        .build();
```

Các đối tượng `Aggregation` có thể được tạo riêng rồi lồng vào nhau. Cách này giúp chia nhỏ query lớn thành các phần có tên và tái sử dụng được.

## 14. Đọc aggregation result từ `SearchHits`

Khi thực thi bằng `ElasticsearchOperations.search`, kết quả trả về `SearchHits<T>`. Aggregation nằm trong `getAggregations()` chứ không nằm trong `getContent()` của entity.

Với client ELC trong Spring Data Elasticsearch, kết quả thường được bọc bởi `ElasticsearchAggregations` và từng aggregation bởi `ElasticsearchAggregation`:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> hits = operations.search(query, ProductDocument.class);

ElasticsearchAggregations aggregations =
        (ElasticsearchAggregations) hits.getAggregations();

ElasticsearchAggregation categoryAggregation =
        aggregations.get("by_category");

Aggregate categoryAggregate = categoryAggregation.aggregation();
StringTermsAggregate terms = categoryAggregate.sterms();

for (StringTermsBucket bucket : terms.buckets().array()) {
    String category = bucket.key().stringValue();
    long productCount = bucket.docCount();

    Aggregate averagePriceAggregate = bucket.aggregations().get("average_price");
    double averagePrice = averagePriceAggregate.avg().value();

    System.out.printf("%s: count=%d, avgPrice=%.2f%n",
            category, productCount, averagePrice);
}
```

Đoạn code minh họa cách truy cập String terms aggregation của Elasticsearch Java API Client. Các kiểu aggregate cụ thể phụ thuộc loại bucket và phiên bản client. Với `long`, `date_histogram`, `range`, `nested` hoặc metric khác, cần dùng accessor tương ứng của union `Aggregate`.

Nếu chỉ cần kết quả aggregation, query có thể đặt số hit trả về bằng 0 để tránh chuyển đổi các document không cần thiết. Khi `size` bằng 0, `SearchHits` vẫn có thể chứa aggregation metadata.

### 14.1. Đọc metric trong bucket

Trong ví dụ trên, mỗi `StringTermsBucket` có:

- `key()`: giá trị category.
- `docCount()`: số product thuộc category.
- `aggregations()`: map aggregation con theo tên.

Để lấy metric `avg`, đọc aggregation con có tên `average_price`, sau đó lấy `avg().value()`. Tên trong map phải khớp chính xác tên được khai báo trong Query DSL/Java builder.

### 14.2. Đọc nested aggregation

Với nested aggregation, accessor là `nested()` thay vì `sterms()` ở cấp tương ứng. Sau đó lấy map aggregation con để đọc metric hoặc bucket. Ví dụ khái quát:

```java
Aggregate reviewAggregate =
        aggregations.get("review_data").aggregation();

// Lấy nested aggregate theo API client version.
// Sau đó truy cập aggregation con "average_rating" và đọc avg().value().
```

Nên tách code parse aggregation thành mapper/helper riêng thay vì đặt toàn bộ logic ép kiểu trong controller. Aggregation response là cấu trúc động; nếu query thay đổi tên bucket hoặc metric, mapper cũng phải được cập nhật.

## 15. Xử lý missing values và bucket rỗng

Aggregation chỉ tính trên giá trị được lập chỉ mục phù hợp. Field bị thiếu, null hoặc không có doc value có thể làm metric bỏ qua document đó.

Một số lựa chọn:

- Dùng `missing` trong metric aggregation để cung cấp giá trị thay thế cho document thiếu field.
- Dùng `missing` trong bucket aggregation để gom document thiếu field vào một bucket riêng.
- Chuẩn hóa dữ liệu khi index nếu field bắt buộc phải có.
- Dùng `min_doc_count: 0` và extended bounds cho histogram khi cần bucket rỗng trong một khoảng xác định.

Ví dụ:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand.keyword",
        "missing": "UNKNOWN"
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price",
            "missing": 0
          }
        }
      }
    }
  }
}
```

Ở đây, document không có brand được đưa vào bucket `UNKNOWN`. Metric `average_price` dùng giá trị 0 thay thế cho document thiếu price. Cách thay thế này làm thay đổi ý nghĩa thống kê; chỉ dùng nếu 0 thực sự là giá trị nghiệp vụ hợp lệ cho trường hợp thiếu.

## 16. Hiệu năng và giới hạn của aggregation lồng nhau

Aggregation nhiều cấp có thể tạo số lượng bucket rất lớn. Ví dụ category × brand × month × status có thể sinh hàng chục nghìn hoặc hàng triệu tổ hợp nếu cardinality cao.

Các nguyên tắc thực tế:

- Chỉ tạo bucket theo field cần thiết cho báo cáo.
- Dùng `keyword`, numeric hoặc date field có doc values phù hợp.
- Giới hạn `terms.size` ở mức giao diện thực sự cần.
- Dùng `composite` để phân trang bucket khi phải duyệt toàn bộ tổ hợp.
- Đặt filter ở query hoặc filter aggregation phù hợp để giảm tập document đầu vào.
- Tránh lồng nhiều cấp bucket cardinality cao nếu không cần thiết.
- Cân nhắc `cardinality` khi chỉ cần distinct count ước lượng thay vì bucket cho từng giá trị.
- Dùng `size: 0` khi chỉ cần aggregation, không lấy hits.
- Theo dõi giới hạn `search.max_buckets`; request có thể bị từ chối nếu tạo quá nhiều bucket.
- Benchmark trên dữ liệu và số shard gần production.

Metric aggregation thường nhẹ hơn việc tạo bucket cho từng giá trị khác nhau, nhưng metric trên nested data hoặc pipeline nhiều cấp vẫn có thể tốn tài nguyên. Không có quy tắc chung rằng thêm sub-aggregation luôn rẻ; cần đo cụ thể.

### 16.1. Terms aggregation không đảm bảo mọi bucket đều được trả về

`terms` thường trả về top bucket theo thứ tự mặc định là document count giảm dần và bị giới hạn bởi `size`. Khi có nhiều giá trị khác nhau, bucket ít phổ biến có thể không xuất hiện. Phân phối bucket giữa shard và cách chọn candidate cũng có thể khiến `doc_count` là giá trị xấp xỉ trong một số cấu hình.

Nếu cần tất cả bucket để export hoặc tính toán đầy đủ, cân nhắc composite aggregation. Nếu cần chính xác distinct count, không suy ra nó bằng cách đếm số bucket của một `terms` aggregation bị giới hạn.

### 16.2. `search.max_buckets`

Elasticsearch giới hạn tổng số bucket được tạo trong một response bằng setting `search.max_buckets`. Aggregation lồng nhiều cấp có thể vượt giới hạn này. Không nên chỉ tăng giới hạn để chữa mọi request; trước tiên hãy giảm cardinality, giảm số cấp hoặc phân trang bucket.

## 17. Kiểm thử aggregation trong Spring Data Elasticsearch

Nên kiểm thử trên Elasticsearch thật hoặc Testcontainers với phiên bản tương thích, vì mock không xác nhận được mapping, nested semantics, bucket counts hoặc kết quả metric.

Một bộ dữ liệu nhỏ có thể gồm:

| Product | Category | Brand | Price | Reviews |
|---|---|---|---:|---|
| P1 | KEYBOARD | ACME | 100 | 5, 4 |
| P2 | KEYBOARD | OMEGA | 200 | 3 |
| P3 | MOUSE | ACME | 50 | 5 |
| P4 | MOUSE | OMEGA | 150 | Không có review |

Kiểm thử:

1. `by_category` trả hai bucket KEYBOARD và MOUSE.
2. `doc_count` của KEYBOARD bằng 2 và MOUSE bằng 2.
3. `average_price` của KEYBOARD bằng 150 và MOUSE bằng 100.
4. Nested aggregation đếm 3 review cho KEYBOARD và 1 review cho MOUSE.
5. `average_rating` của KEYBOARD bằng 4 và MOUSE bằng 5.
6. `reverse_nested` đếm product cha theo bucket rating, không đếm review.
7. Pipeline aggregation cho kết quả theo công thức đã định nghĩa.
8. Missing values được xử lý theo quy tắc nghiệp vụ.

Sau khi index fixture, refresh index trước khi chạy search. Không dựa vào `Thread.sleep` để chờ dữ liệu xuất hiện.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `terms` không nhóm đúng chuỗi | Dùng field `text` thay vì `keyword` hoặc field exact. | Dùng `.keyword` hoặc mapping keyword phù hợp. |
| Bucket con có count khác mong đợi | Sub-aggregation chạy trong tập document của bucket cha, không phải toàn index. | Xác định rõ phạm vi mỗi cấp bucket. |
| Average không bằng sum chia doc_count | Một số document thiếu giá trị metric field. | Kiểm tra metric `count` và missing values. |
| Nested aggregation trả số lớn hơn số parent | `doc_count` trong nested context đếm nested child document. | Dùng `reverse_nested` nếu cần quay về parent. |
| Metric review tính cả review không khớp nested query | Nested query lọc parent nhưng nested aggregation vẫn duyệt child trong parent đó. | Thêm filter aggregation bên trong nested aggregation. |
| Không dùng được nested aggregation | Field được mapping `object` thay vì `nested`. | Tạo lại index với mapping nested và reindex dữ liệu. |
| `reverse_nested` không trả metric parent đúng | Đang đọc field ở sai document scope hoặc path. | Kiểm tra context nested/parent và đặt metric sau reverse_nested. |
| Pipeline aggregation không tìm thấy buckets_path | Đường dẫn metric con sai tên hoặc sai cấp. | Kiểm tra tên aggregation và dùng cú pháp `parent>child`. |
| `avg_bucket` khác average toàn bộ document | Đang tính trung bình các bucket average, mỗi bucket có trọng số như nhau. | Dùng metric phù hợp hoặc tính weighted average theo count. |
| Thiếu bucket giá trị hiếm | `terms.size` giới hạn số bucket được trả về. | Tăng size trong giới hạn hợp lý hoặc dùng composite. |
| Request bị từ chối vì quá nhiều bucket | Aggregation lồng nhiều cấp tạo số bucket vượt `search.max_buckets`. | Giảm cardinality, số cấp hoặc phân trang bucket. |
| Java code không lấy được metric | Đọc sai kiểu union Aggregate hoặc sai tên aggregation. | Dùng accessor đúng loại và tách mapper theo response structure. |

## 19. Quy trình thiết kế aggregation

1. **Xác định câu hỏi nghiệp vụ:** cần nhóm theo field nào và tính chỉ số nào?
2. **Xác định document scope:** metric tính trên root document hay nested child?
3. **Kiểm tra mapping:** field group cần keyword/numeric/date; nested path phải được khai báo `nested`.
4. **Xác định filter:** điều kiện nào áp dụng cho toàn query, điều kiện nào chỉ áp dụng cho một nhánh aggregation?
5. **Thiết kế cây bucket:** nhóm cha, nhóm con và số lượng bucket dự kiến.
6. **Đặt metric:** sum/avg/stats/cardinality hoặc metric phù hợp trong đúng bucket.
7. **Thêm pipeline khi cần:** tính trung bình giữa bucket, tỷ lệ, derivative hoặc cumulative sum.
8. **Tích hợp Spring Data:** xây dựng `Aggregation`, gắn vào `NativeQuery` và thực thi qua `ElasticsearchOperations`.
9. **Đọc kết quả:** duyệt đúng kiểu bucket/metric và giữ rõ document scope.
10. **Đo hiệu năng:** kiểm tra số bucket, memory, latency và giới hạn cluster.
11. **Kiểm thử dữ liệu biên:** missing, nested array rỗng, bucket không có document và giá trị multi-valued.

## 20. Những điểm cần nhớ

- Bucket aggregation chia document thành nhóm; metric aggregation tính giá trị trên tập document hiện tại.
- Sub-aggregation có thể là bucket hoặc metric và luôn chạy trong phạm vi bucket cha.
- `terms` nhóm theo giá trị, `range` nhóm theo khoảng, `date_histogram` nhóm theo thời gian.
- `sum`, `avg`, `min`, `max`, `stats`, `value_count` và `cardinality` trả các loại metric khác nhau.
- `doc_count` đếm document trong bucket; `value_count` đếm giá trị của field.
- Nested aggregation chuyển sang nested document; `reverse_nested` quay lại parent document.
- Nested query lọc parent document; nested aggregation cần filter riêng nếu chỉ muốn tính trên child document thỏa điều kiện.
- Pipeline aggregation tính từ kết quả aggregation khác; `buckets_path` phải trỏ đúng cấp và tên.
- `avg_bucket` tính trung bình các metric bucket, không mặc định là trung bình có trọng số theo số document.
- `terms.size` giới hạn số bucket; dùng composite để phân trang khi cần duyệt toàn bộ bucket.
- Spring Data Elasticsearch có thể gắn Java API Client `Aggregation` vào `NativeQuery` và đọc kết quả qua `SearchHits.getAggregations()`.
- Chọn đúng mapping, document scope và giới hạn bucket để aggregation trả kết quả đúng và vận hành ổn định.

Aggregation lồng nhau cho phép xây dựng báo cáo nhiều cấp trong một search request: bucket xác định nhóm, metric mô tả từng nhóm và pipeline metric tính toán trên các kết quả đã tổng hợp. Khi làm việc với nested data, phải theo dõi rõ đang ở document cha hay nested child; khi kết hợp metric với bucket, hãy đặt mỗi aggregation đúng cấp để số liệu có ý nghĩa nghiệp vụ.

## Tài liệu tham khảo

- [Elasticsearch — Aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html)
- [Elasticsearch — Bucket aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket.html)
- [Elasticsearch — Metrics aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-metrics.html)
- [Elasticsearch — Pipeline aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-pipeline.html)
- [Elasticsearch — Nested aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-nested-aggregation.html)
- [Spring Data Elasticsearch — Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
