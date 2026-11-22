# Filter aggregation và thống kê theo tập điều kiện

Aggregation trong Elasticsearch giúp tổng hợp dữ liệu tìm kiếm thành các con số và nhóm có ý nghĩa: đếm số sản phẩm theo danh mục, tính doanh thu của đơn hàng đã thanh toán, tìm giá trung bình của mặt hàng còn bán hoặc so sánh các nhóm document theo nhiều điều kiện. Khi chỉ muốn thống kê trên một tập document thỏa điều kiện cụ thể, filter aggregation là một công cụ quan trọng.

Filter aggregation tạo một bucket chứa những document khớp một query/filter được khai báo bên trong aggregation. Các sub-aggregation đặt dưới bucket đó chỉ thống kê trên tập document đã lọc. Nếu cần chia dữ liệu thành nhiều nhóm điều kiện song song, dùng filters aggregation.

Cần phân biệt ba cấp lọc:

- Query ở cấp tìm kiếm giới hạn tập document đầu vào cho toàn bộ kết quả và aggregation thông thường.
- Filter aggregation giới hạn riêng một nhánh aggregation.
- Filters aggregation tạo nhiều bucket, mỗi bucket có một điều kiện riêng để so sánh các nhóm.

Hiểu đúng phạm vi của từng bộ lọc giúp tránh đếm sai, đặc biệt trong API tìm kiếm có cả danh sách kết quả và bộ lọc facet.

## 1. Aggregation hoạt động trên tập document nào?

Elasticsearch thực hiện query trước, sau đó chạy aggregation trên tập document phù hợp với query. Ví dụ:

~~~json
{
  "query": {
    "term": {
      "status": "PAID"
    }
  },
  "aggs": {
    "revenue": {
      "sum": {
        "field": "totalAmount"
      }
    }
  }
}
~~~

Aggregation revenue chỉ tính tổng totalAmount của các document có status là PAID. Nếu query cấp cao không có điều kiện, aggregation thông thường xét toàn bộ document trong index được tìm kiếm.

Sơ đồ:

~~~text
Index / alias
     |
     v
Top-level query
     |
     v
Tập document khớp query
     |
     +----> Hits trả về
     |
     +----> Aggregations
                |
                +----> Bucket
                |        |
                |        +----> Sub-aggregations
                |
                +----> Metrics
~~~

Điều này quan trọng vì filter ở cấp query tác động đến cả hits và các aggregation bên dưới. Nếu muốn hits vẫn hiển thị nhiều document nhưng một thống kê chỉ tính trên một nhóm con, hãy dùng filter aggregation ở nhánh thống kê đó.

## 2. Filter aggregation là gì?

Filter aggregation là một single-bucket aggregation. Nó nhận một query làm điều kiện, tạo một bucket gồm các document khớp điều kiện và cho phép đặt sub-aggregation bên trong.

Ví dụ: trả danh sách sản phẩm theo query hiện tại, đồng thời tính giá trung bình của sản phẩm còn hàng:

~~~json
{
  "size": 20,
  "query": {
    "match": {
      "name": "laptop"
    }
  },
  "aggs": {
    "available_products": {
      "filter": {
        "term": {
          "available": true
        }
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        },
        "total_stock": {
          "sum": {
            "field": "stock"
          }
        }
      }
    }
  }
}
~~~

Kết quả hits vẫn là các sản phẩm khớp từ khóa laptop, bất kể trạng thái available. Bucket available_products chỉ chứa sản phẩm available=true. Hai metric average_price và total_stock chỉ tính trên bucket đó.

Một filter aggregation thường trả về:

- doc_count: số document nằm trong bucket.
- Kết quả của các sub-aggregation, ví dụ avg, sum, min, max, terms hoặc date_histogram.

Filter aggregation phù hợp khi cần một tập con duy nhất cho một nhánh thống kê.

## 3. Filter aggregation và top-level query khác nhau thế nào?

Hai cách đều có thể giới hạn document, nhưng phạm vi ảnh hưởng khác nhau.

| Tiêu chí | Top-level query | Filter aggregation |
|---|---|---|
| Phạm vi | Hits và aggregation thông thường | Chỉ bucket aggregation đó và các sub-aggregation của nó |
| Mục đích | Giới hạn tập kết quả chính | Thống kê trên một tập con |
| Có thể có nhiều điều kiện độc lập | Có thể thông qua bool query | Có thể tạo nhiều nhánh filter aggregation |
| Dùng khi | Mọi thống kê đều cần cùng điều kiện nền | Một thống kê cần điều kiện riêng |

Ví dụ, nếu tất cả kết quả và thống kê chỉ cần đơn hàng đã thanh toán, đặt status=PAID trong top-level query thường đơn giản và hiệu quả hơn bọc mọi aggregation trong filter.

Nếu API cần trả hits của tất cả đơn hàng theo từ khóa, đồng thời có một metric riêng chỉ tính đơn hàng đã thanh toán, filter aggregation phù hợp hơn.

### 3.1. Ví dụ cùng lúc có thống kê tổng và thống kê đã thanh toán

~~~json
{
  "query": {
    "match": {
      "customerName": "Nguyen"
    }
  },
  "aggs": {
    "all_matching_orders": {
      "stats": {
        "field": "totalAmount"
      }
    },
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "paid_amount": {
          "sum": {
            "field": "totalAmount"
          }
        }
      }
    }
  }
}
~~~

all_matching_orders tính thống kê trên toàn bộ đơn hàng khớp tên khách hàng. paid_orders chỉ xét các đơn hàng có trạng thái PAID. Cả hai nhánh dùng chung tập document sau top-level query.

### 3.2. Filter aggregation không lọc hits

Một lỗi thường gặp là nghĩ rằng đặt filter aggregation sẽ làm danh sách hits chỉ còn document khớp filter đó. Điều này không đúng. Filter aggregation chỉ tạo bucket cho phần aggregation.

Nếu muốn hits cũng chỉ gồm sản phẩm còn hàng, đặt điều kiện available=true trong top-level query. Nếu chỉ muốn thống kê hàng còn hàng nhưng vẫn trả về hits rộng hơn, giữ điều kiện trong filter aggregation.

## 4. Cấu trúc filter aggregation và sub-aggregation

Cấu trúc cơ bản:

~~~json
{
  "aggs": {
    "aggregation_name": {
      "filter": {
        "query_clause": {}
      },
      "aggs": {
        "metric_name": {
          "metric_aggregation": {
            "field": "numeric_field"
          }
        }
      }
    }
  }
}
~~~

Trong đó:

- aggregation_name là tên do ứng dụng đặt để đọc kết quả.
- filter là điều kiện Query DSL áp dụng cho bucket.
- aggs lồng bên trong là các thống kê chạy trên bucket.
- metric_name là tên của từng kết quả con.

Có thể lồng nhiều cấp bucket và metric. Ví dụ: lọc đơn hàng đã thanh toán, nhóm theo khu vực, rồi tính tổng doanh thu mỗi khu vực.

~~~json
{
  "aggs": {
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "by_region": {
          "terms": {
            "field": "region.keyword"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "totalAmount"
              }
            },
            "average_order_value": {
              "avg": {
                "field": "totalAmount"
              }
            }
          }
        }
      }
    }
  }
}
~~~

Thứ tự xử lý là: lọc đơn hàng PAID, chia các document còn lại theo region, sau đó tính revenue và average_order_value trong từng bucket khu vực.

## 5. Dùng filters aggregation để thống kê nhiều tập điều kiện

Khi cần so sánh nhiều nhóm điều kiện trong cùng một truy vấn, filters aggregation tạo nhiều bucket có tên. Mỗi bucket có một filter riêng.

Ví dụ so sánh đơn hàng theo trạng thái:

~~~json
{
  "aggs": {
    "orders_by_status": {
      "filters": {
        "filters": {
          "paid": {
            "term": {
              "status": "PAID"
            }
          },
          "pending": {
            "term": {
              "status": "PENDING"
            }
          },
          "cancelled": {
            "term": {
              "status": "CANCELLED"
            }
          }
        }
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalAmount"
          }
        }
      }
    }
  }
}
~~~

Kết quả có ba bucket paid, pending và cancelled. Mỗi bucket có doc_count và metric revenue riêng.

### 5.1. Filter và filters

Tên hai aggregation khá giống nhau nhưng ý nghĩa khác:

| Aggregation | Bucket được tạo | Khi dùng |
|---|---:|---|
| filter | Một bucket | Thống kê một tập con |
| filters | Nhiều bucket có tên | So sánh nhiều tập điều kiện |

Filter aggregation có một điều kiện và một bucket. Filters aggregation có một map các điều kiện, mỗi điều kiện tạo một bucket riêng.

### 5.2. Một document có thể thuộc nhiều bucket

Các filter trong filters aggregation không mặc định loại trừ lẫn nhau. Một document có thể khớp nhiều điều kiện và được tính trong nhiều bucket.

Ví dụ:

- Bucket high_value lọc totalAmount lớn hơn 1000.
- Bucket vip_customer lọc customerTier là VIP.

Một đơn hàng giá trị lớn của khách VIP sẽ xuất hiện trong cả hai bucket. Vì vậy, tổng doc_count của các bucket có thể lớn hơn số document đầu vào.

Nếu cần các nhóm loại trừ lẫn nhau, hãy thiết kế điều kiện rõ ràng, ví dụ chia khoảng giá không chồng lấn hoặc dùng status có một giá trị duy nhất.

### 5.3. Bucket other

Filters aggregation có thể cấu hình other_bucket để gom document không khớp bất kỳ filter nào vào một bucket riêng:

~~~json
{
  "aggs": {
    "status_groups": {
      "filters": {
        "other_bucket": true,
        "other_bucket_key": "other",
        "filters": {
          "paid": {
            "term": {
              "status": "PAID"
            }
          },
          "pending": {
            "term": {
              "status": "PENDING"
            }
          }
        }
      }
    }
  }
}
~~~

Bucket other chứa document không khớp paid hoặc pending. Nếu một document khớp nhiều bucket đã đặt tên, nó vẫn được tính trong từng bucket tương ứng; other không phải bucket loại trừ để biến các filter chồng lấn thành phân hoạch.

## 6. Thống kê theo nhiều điều kiện với bool query

Filter aggregation nhận một Query DSL clause, vì vậy có thể dùng bool query để kết hợp nhiều điều kiện.

Ví dụ thống kê doanh thu của sản phẩm đang bán, còn hàng và thuộc hai danh mục được chọn:

~~~json
{
  "aggs": {
    "eligible_products": {
      "filter": {
        "bool": {
          "filter": [
            {
              "term": {
                "active": true
              }
            },
            {
              "range": {
                "stock": {
                  "gt": 0
                }
              }
            },
            {
              "terms": {
                "category": ["books", "electronics"]
              }
            }
          ],
          "must_not": [
            {
              "term": {
                "visibility": "private"
              }
            }
          ]
        }
      },
      "aggs": {
        "total_value": {
          "sum": {
            "field": "inventoryValue"
          }
        },
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

Trong bool:

- filter yêu cầu active=true, stock lớn hơn 0 và category thuộc danh sách.
- must_not loại sản phẩm có visibility=private.
- Các metric chỉ chạy trên document thỏa toàn bộ điều kiện đó.

Với điều kiện chỉ dùng để lọc, filter context thường phù hợp hơn must vì không cần tính score cho bucket.

## 7. Metric aggregation bên trong filter bucket

Filter aggregation có thể chứa nhiều loại metric aggregation.

| Metric | Ý nghĩa | Ví dụ |
|---|---|---|
| count qua doc_count | Số document trong bucket | Số đơn hàng PAID |
| sum | Tổng giá trị số | Tổng doanh thu |
| avg | Trung bình | Giá trị đơn trung bình |
| min | Giá trị nhỏ nhất | Giá đơn thấp nhất |
| max | Giá trị lớn nhất | Giá đơn cao nhất |
| stats | count, min, max, avg, sum | Thống kê tổng hợp |
| extended_stats | Stats mở rộng, có phương sai và độ lệch chuẩn | Phân tích phân phối giá |
| value_count | Số giá trị được lập chỉ mục trong field | Số giá trị của field multi-valued |
| cardinality | Số giá trị duy nhất ước lượng | Số khách hàng duy nhất |

Ví dụ:

~~~json
{
  "aggs": {
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "amount_stats": {
          "stats": {
            "field": "totalAmount"
          }
        },
        "unique_customers": {
          "cardinality": {
            "field": "customerId"
          }
        }
      }
    }
  }
}
~~~

Lưu ý:

- doc_count đếm document trong bucket.
- value_count đếm số giá trị của field, không nhất thiết bằng doc_count nếu field thiếu hoặc là mảng.
- cardinality thường là ước lượng dựa trên thuật toán HyperLogLog++; không coi là phép đếm chính xác tuyệt đối.
- sum và avg chỉ có ý nghĩa khi field có mapping numeric phù hợp.

## 8. Filter aggregation kết hợp terms và date_histogram

Một thống kê thường có nhiều cấp: lọc tập dữ liệu, nhóm theo danh mục, sau đó chia theo thời gian hoặc tính metric.

Ví dụ: doanh thu đã thanh toán theo danh mục và theo tháng:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-01-01",
        "lt": "2027-01-01"
      }
    }
  },
  "aggs": {
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "by_category": {
          "terms": {
            "field": "category.keyword",
            "size": 20
          },
          "aggs": {
            "monthly_revenue": {
              "date_histogram": {
                "field": "createdAt",
                "calendar_interval": "month",
                "time_zone": "Asia/Ho_Chi_Minh"
              },
              "aggs": {
                "revenue": {
                  "sum": {
                    "field": "totalAmount"
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
~~~

Query cấp cao giới hạn năm 2026. Filter aggregation chỉ giữ đơn hàng PAID. Terms chia theo category, date_histogram chia mỗi category thành các bucket tháng, và sum tính doanh thu của từng tháng.

Tham số time_zone quyết định ranh giới bucket lịch theo múi giờ mong muốn. Nếu bỏ qua, Elasticsearch thường dùng UTC. Với báo cáo nghiệp vụ theo ngày/tháng địa phương, hãy chọn múi giờ tường minh và thống nhất với quy tắc lưu timestamp.

## 9. Filter aggregation và facet trên trang tìm kiếm

Một use case phổ biến là trang tìm kiếm sản phẩm có bộ lọc danh mục, thương hiệu và trạng thái. API cần trả:

- Hits theo từ khóa.
- Số lượng sản phẩm theo từng danh mục.
- Số lượng theo thương hiệu.
- Số lượng theo trạng thái.

Có hai cách thiết kế tùy semantics:

1. Nếu tất cả facet phải phản ánh cùng tập document đã lọc bởi query và filter chính, dùng top-level query cho điều kiện chung rồi tạo terms aggregations.
2. Nếu một facet cần thống kê trên một tập con riêng, dùng filter aggregation hoặc filters aggregation trong nhánh đó.

### 9.1. Query lọc chung và facet terms

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "phone"
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
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      }
    },
    "brands": {
      "terms": {
        "field": "brand",
        "size": 20
      }
    }
  }
}
~~~

Hits và cả hai facet chỉ xét sản phẩm active khớp từ khóa phone.

### 9.2. Thống kê bỏ qua một filter lựa chọn

Một trải nghiệm facet có thể muốn hiển thị số lượng của tất cả danh mục trong khi người dùng đã chọn một danh mục. Khi đó cần xác định rõ filter nào được áp dụng cho hits và filter nào được bỏ qua cho facet.

Một lựa chọn là dùng post_filter cho điều kiện chỉ áp dụng lên hits sau khi aggregation đã chạy. Ví dụ:

~~~json
{
  "query": {
    "term": {
      "active": true
    }
  },
  "post_filter": {
    "term": {
      "category": "phones"
    }
  },
  "aggs": {
    "all_categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Ở đây query active=true áp dụng cho hits và aggregations. post_filter category=phones chỉ lọc hits, không lọc aggregation all_categories. Đây là một cơ chế khác với filter aggregation; nó hữu ích khi facet cần cho thấy lựa chọn thay thế.

Nếu chỉ một nhánh aggregation cần bỏ qua điều kiện category, có thể dùng global aggregation ở cấp cao nhất để quay lại toàn bộ document của index, sau đó đặt filter riêng bên trong global bucket. Global aggregation bỏ qua top-level query, vì vậy phải lặp lại các điều kiện nền cần giữ, chẳng hạn tenant, quyền truy cập hoặc trạng thái hợp lệ. Cơ chế này cần dùng thận trọng để không vô tình thống kê dữ liệu ngoài phạm vi được phép.

## 10. Global aggregation so với filter aggregation

Global aggregation tạo bucket chứa tất cả document của index hoặc index pattern, bỏ qua top-level query. Nó chỉ được đặt ở cấp aggregation cao nhất.

Ví dụ:

~~~json
{
  "query": {
    "term": {
      "category": "phones"
    }
  },
  "aggs": {
    "all_products": {
      "global": {},
      "aggs": {
        "active_products": {
          "filter": {
            "term": {
              "active": true
            }
          }
        }
      }
    }
  }
}
~~~

Hits vẫn bị giới hạn bởi category=phones. Nhánh all_products bỏ qua query đó và xét toàn bộ document trong index, sau đó filter active_products chỉ giữ active=true.

So sánh:

| Cơ chế | Phạm vi document |
|---|---|
| Top-level query | Giới hạn hits và aggregation thông thường |
| filter aggregation | Lọc một nhánh aggregation trong tập đã qua query |
| filters aggregation | Chia tập đã qua query thành nhiều bucket theo điều kiện |
| post_filter | Lọc hits sau aggregation, không tác động aggregation |
| global aggregation | Bỏ qua top-level query, xét toàn bộ document của index |

Khi dùng global aggregation, cần đặc biệt chú ý tenant isolation và quyền truy cập. Nếu top-level query có điều kiện bảo mật dữ liệu, global aggregation sẽ bỏ qua nó. Hãy lặp lại điều kiện bảo mật trong nhánh global trước khi tính thống kê.

## 11. Mapping field ảnh hưởng đến filter và aggregation

Aggregation cần mapping phù hợp:

| Loại dữ liệu | Mapping thường dùng | Aggregation/query phù hợp |
|---|---|---|
| Danh mục, thương hiệu, trạng thái | keyword | term filter, terms aggregation |
| Tên hoặc mô tả | text | match query; dùng sub-field keyword nếu cần nhóm chính xác |
| Giá, doanh thu, số lượng | integer, long, scaled_float, double | range, sum, avg, stats |
| Ngày giờ | date hoặc date_nanos | range, date_histogram |
| ID khách hàng | keyword | terms, cardinality |
| Boolean | boolean | term filter |

Không nên chạy terms aggregation trên field text với kỳ vọng gom theo nguyên văn chuỗi. Field text được phân tích thành token. Hãy khai báo multi-field keyword, ví dụ:

~~~json
{
  "properties": {
    "category": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Khi đó:

- Tìm toàn văn có thể dùng category.
- Lọc chính xác hoặc nhóm bucket có thể dùng category.keyword.

Nếu index đã tồn tại và chưa có sub-field keyword, việc thêm mapping không tự tạo lại giá trị đã lập chỉ mục cho dữ liệu cũ trong mọi trường hợp. Có thể cần reindex để backfill field.

## 12. Filters aggregation có keyed và array response

Filters aggregation thường dùng các key để đặt tên bucket. Khi keyed, response trả các bucket theo tên, ví dụ paid, pending, cancelled. Đây là cách dễ ánh xạ sang DTO hoặc object thống kê.

Ví dụ response rút gọn:

~~~json
{
  "aggregations": {
    "orders_by_status": {
      "buckets": {
        "paid": {
          "doc_count": 120,
          "revenue": {
            "value": 98000.0
          }
        },
        "pending": {
          "doc_count": 18,
          "revenue": {
            "value": 12000.0
          }
        },
        "cancelled": {
          "doc_count": 7,
          "revenue": {
            "value": 4300.0
          }
        }
      }
    }
  }
}
~~~

Nếu filters aggregation không dùng keyed response, buckets có thể được trả như một mảng theo thứ tự khai báo. Hãy dùng key hoặc thứ tự bucket theo đúng cấu hình, không suy luận từ vị trí nếu API có thể đổi cấu trúc response.

## 13. Tạo filter aggregation bằng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp nhiều cách gửi aggregation:

- Dùng repository method với annotation @Aggregation cho một aggregation DSL cố định.
- Dùng ElasticsearchOperations và NativeQuery khi cần ghép query, filter và nhiều aggregation động.
- Dùng Elasticsearch Java Client trực tiếp khi cần kiểm soát đầy đủ DSL và response aggregation.

Các package, builder và kiểu đọc kết quả aggregation thay đổi theo release train. Ví dụ dưới đây minh họa cấu trúc với NativeQuery và Elasticsearch Java Client; hãy đối chiếu dependency đang dùng.

### 13.1. Dùng @Aggregation cho truy vấn cố định

Ví dụ repository khai báo filters aggregation theo trạng thái:

~~~java
import org.springframework.data.elasticsearch.annotations.Aggregation;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {

    @Aggregation("""
        {
          "filters": {
            "filters": {
              "paid": {
                "term": {
                  "status": "PAID"
                }
              },
              "pending": {
                "term": {
                  "status": "PENDING"
                }
              }
            }
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "totalAmount"
              }
            }
          }
        }
        """)
    AggregationResult summarizeOrders();
}
~~~

AggregationResult ở đây là kiểu DTO/kiểu trả về minh họa cho kết quả aggregation. Repository aggregation có cách ánh xạ kết quả phụ thuộc vào kiểu trả về và phiên bản Spring Data Elasticsearch; không phải mọi cấu trúc bucket lồng nhau đều tự ánh xạ sang một DTO tùy ý. Khi cần đọc metadata hoặc bucket phức tạp, hãy dùng ElasticsearchOperations và API Aggregations tương ứng.

### 13.2. Dùng NativeQuery với Aggregation builder

Với Elasticsearch Java Client, có thể tạo Aggregation object và gắn vào NativeQuery:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Aggregation paidOrders = Aggregation.of(a -> a
        .filter(f -> f.term(t -> t
                .field("status")
                .value("PAID")
        ))
        .aggregations("revenue", Aggregation.of(revenue -> revenue
                .sum(s -> s.field("totalAmount"))
        ))
);

NativeQuery query = NativeQuery.builder()
        .withAggregation("paid_orders", paidOrders)
        .build();

SearchHits<Order> hits = operations.search(query, Order.class);
~~~

Đoạn code minh họa cách lồng filter aggregation và metric aggregation bằng builder của client. Trong một ứng dụng thực tế, có thể thêm top-level query bằng withQuery(...), thêm nhiều aggregation bằng các lần gọi builder tương ứng và chọn kích thước hits phù hợp. Nếu chỉ cần aggregation mà không cần document hits, đặt kích thước kết quả về 0 bằng API phù hợp của phiên bản đang dùng.

### 13.3. Đọc aggregation result

Trong Spring Data Elasticsearch, SearchHits có thể chứa metadata aggregation. Với client Elasticsearch Java, response aggregation được biểu diễn qua các kiểu Aggregation và Aggregate có union variants. Cách truy xuất cụ thể phụ thuộc phiên bản Spring Data và client.

Luồng đọc kết quả về mặt khái niệm:

~~~text
SearchHits<Order>
       |
       v
getAggregations()
       |
       v
ElasticsearchAggregations
       |
       v
aggregationsAsMap()
       |
       +----> paid_orders
                 |
                 +----> doc_count
                 |
                 +----> revenue.value
~~~

Hãy kiểm tra tên aggregation đúng với key đã khai báo trong query. Khi chuyển kết quả sang DTO, ánh xạ rõ:

- Tên bucket.
- doc_count.
- Giá trị metric.
- Giá trị null hoặc bucket rỗng.

Không nên ép kiểu một Aggregate sang bucket cụ thể mà chưa kiểm tra variant thực tế. Nếu aggregation có thể thay đổi theo query, tạo mapper riêng để xử lý từng loại kết quả và báo lỗi rõ ràng khi cấu trúc không như mong đợi.

## 14. Ví dụ nghiệp vụ: báo cáo doanh thu theo trạng thái và khu vực

Giả sử hệ thống cần báo cáo đơn hàng trong một khoảng thời gian, nhưng chỉ muốn tính doanh thu của đơn đã thanh toán, đồng thời so sánh các nhóm trạng thái.

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-10-01T00:00:00Z",
        "lt": "2026-11-01T00:00:00Z"
      }
    }
  },
  "aggs": {
    "by_status": {
      "filters": {
        "filters": {
          "paid": {
            "term": {
              "status": "PAID"
            }
          },
          "pending": {
            "term": {
              "status": "PENDING"
            }
          },
          "cancelled": {
            "term": {
              "status": "CANCELLED"
            }
          }
        }
      },
      "aggs": {
        "amount_stats": {
          "stats": {
            "field": "totalAmount"
          }
        },
        "by_region": {
          "terms": {
            "field": "region",
            "size": 20
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "totalAmount"
              }
            }
          }
        }
      }
    }
  }
}
~~~

Top-level query giới hạn tháng 10/2026. Filters aggregation tạo các bucket theo trạng thái. Mỗi bucket có thống kê amount_stats và nhóm theo khu vực để tính revenue. Kết quả có thể dùng làm dữ liệu cho dashboard hoặc báo cáo vận hành.

Nếu chỉ cần tính doanh thu của trạng thái PAID, có thể thay filters aggregation bằng một filter aggregation duy nhất. Chọn cấu trúc đơn giản nhất thể hiện đúng yêu cầu nghiệp vụ.

## 15. Hiệu năng và giới hạn cần lưu ý

Aggregation có thể tốn CPU, bộ nhớ và thời gian hơn truy vấn chỉ trả hits, đặc biệt khi nhóm theo field có cardinality cao hoặc có nhiều cấp sub-aggregation.

Một số nguyên tắc:

- Dùng top-level query cho điều kiện chung của mọi aggregation.
- Dùng filter aggregation khi một nhánh cần tập con riêng.
- Dùng filters aggregation khi cần nhiều bucket điều kiện cố định.
- Chọn field keyword/numeric có mapping phù hợp.
- Giới hạn size của terms aggregation theo nhu cầu thực tế.
- Tránh lồng quá nhiều bucket có cardinality cao.
- Chỉ yêu cầu các metric cần thiết.
- Dùng size: 0 khi chỉ cần aggregation và không cần hits.
- Theo dõi thời gian, memory và shard failures trong response.

### 15.1. Cardinality và số lượng bucket

Terms aggregation có thể tạo nhiều bucket nếu field có nhiều giá trị khác nhau. Đặt size lớn không phải lúc nào cũng phù hợp. Nếu cần duyệt toàn bộ giá trị có cardinality cao, hãy xem xét composite aggregation để phân trang bucket.

Cardinality aggregation thường cho kết quả ước lượng. Nếu báo cáo tài chính yêu cầu số lượng duy nhất chính xác, cần xác định liệu sai số của cardinality có chấp nhận được hay phải dùng cách tính khác.

### 15.2. Shard và doc_count

Bucket aggregation có thể được tính trên nhiều shard rồi gộp lại. Với terms aggregation, top buckets và doc_count_error_upper_bound phụ thuộc cách phân phối bucket trên shard và các tham số shard_size/size. Nếu số đếm phải chính xác trong phạm vi nghiệp vụ, hãy hiểu giới hạn của aggregation đang dùng và cân nhắc composite hoặc thiết kế dữ liệu phù hợp.

Filter aggregation với một điều kiện không có vấn đề chọn top bucket như terms, nhưng vẫn chịu ảnh hưởng của dữ liệu shard, mapping và tình trạng cluster.

### 15.3. Filter context và cache

Điều kiện bên trong filter aggregation được đánh giá trong filter context. Điều kiện này không tính relevance score. Elasticsearch có thể cache một số kết quả filter phù hợp, nhưng không nên giả định mọi filter sẽ luôn được cache. Hãy đo trên workload thực tế.

## 16. Các lỗi thường gặp

### 16.1. Dùng filter aggregation nhưng mong hits cũng bị lọc

Filter aggregation chỉ giới hạn bucket aggregation. Nếu hits cần cùng điều kiện, đưa điều kiện vào top-level query hoặc post_filter theo semantics mong muốn.

### 16.2. Lặp lại điều kiện top-level trong mọi aggregation

Nếu mọi aggregation cùng cần một điều kiện, đặt nó ở top-level query để giảm lặp và giúp cấu trúc dễ hiểu.

### 16.3. Dùng filter thay vì filters khi cần so sánh nhiều nhóm

Filter chỉ tạo một bucket. Nếu cần paid, pending và cancelled trong cùng response, dùng filters aggregation.

### 16.4. Nghĩ các filter trong filters aggregation loại trừ nhau

Một document có thể khớp nhiều bucket. Nếu cần nhóm không chồng lấn, thiết kế điều kiện không giao nhau.

### 16.5. Dùng terms aggregation trên field text

Field text được phân tích token. Dùng keyword field hoặc multi-field keyword để nhóm theo giá trị đầy đủ.

### 16.6. Nhầm doc_count với value_count

doc_count đếm document trong bucket. value_count đếm số giá trị của field và có thể khác khi field thiếu hoặc có nhiều giá trị.

### 16.7. Dùng global aggregation nhưng quên điều kiện bảo mật

Global aggregation bỏ qua top-level query. Nếu query chứa tenant hoặc authorization scope, phải áp dụng lại điều kiện đó bên trong global branch.

### 16.8. Ánh xạ aggregation response sai kiểu

Aggregation response có thể chứa single bucket, multi-bucket và metric khác nhau. Kiểm tra variant và key trước khi ép kiểu hoặc chuyển DTO.

## 17. Kiểm thử filter aggregation

Hãy chuẩn bị dữ liệu nhỏ với kết quả dự kiến rõ ràng. Ví dụ:

| Order | Status | Region | Amount |
|---|---|---|---:|
| O1 | PAID | North | 100 |
| O2 | PAID | South | 200 |
| O3 | PENDING | North | 50 |
| O4 | CANCELLED | South | 80 |
| O5 | PAID | North | 300 |

Với filters aggregation theo status, kết quả mong đợi:

| Bucket | doc_count | revenue |
|---|---:|---:|
| paid | 3 | 600 |
| pending | 1 | 50 |
| cancelled | 1 | 80 |

Các kiểm thử nên bao gồm:

1. Bucket filter chỉ đếm document thỏa điều kiện.
2. Sub-aggregation chỉ tính trên bucket cha.
3. Top-level query thu hẹp mọi bucket.
4. Filters aggregation trả đúng bucket theo key.
5. Document khớp nhiều filter được đếm trong nhiều bucket nếu điều kiện chồng lấn.
6. other_bucket nhận document không khớp bucket nào.
7. Field thiếu không làm sai kỳ vọng doc_count và metric.
8. Mapping keyword/numeric/date phù hợp.
9. Global aggregation thực sự bỏ qua top-level query và có filter bảo mật riêng.
10. Kết quả aggregation được ánh xạ đúng sang DTO.

Trong integration test, dùng Elasticsearch tương thích với phiên bản client. Mock response có thể kiểm tra mapper, nhưng không xác nhận DSL thực tế hoặc semantics aggregation trên cluster.

## 18. Quy trình thiết kế thống kê theo tập điều kiện

Khi xây báo cáo hoặc facet:

1. Xác định tập document nền và đặt điều kiện chung ở top-level query.
2. Xác định mỗi thống kê cần toàn bộ tập nền hay một tập con.
3. Dùng filter aggregation cho một tập con.
4. Dùng filters aggregation cho nhiều tập điều kiện cần so sánh.
5. Đặt metric hoặc bucket aggregation làm sub-aggregation.
6. Kiểm tra field mapping trước khi chạy terms, range, date_histogram hoặc metric.
7. Quyết định có cần post_filter hoặc global aggregation cho facet không.
8. Nếu dùng global, áp dụng lại tenant và điều kiện bảo mật.
9. Chọn size phù hợp và kiểm soát cardinality.
10. Đọc đúng response bucket/metric và kiểm thử với dữ liệu mẫu.

Ví dụ lựa chọn:

| Yêu cầu | Cấu trúc |
|---|---|
| Tổng doanh thu của đơn PAID | filter aggregation + sum |
| So sánh PAID/PENDING/CANCELLED | filters aggregation + metrics |
| Mọi aggregation chỉ xét một tenant | top-level query |
| Hits lọc theo danh mục nhưng facet vẫn hiển thị mọi danh mục | post_filter hoặc global branch có filter bảo mật |
| Doanh thu theo tháng trong nhóm PAID | filter aggregation + date_histogram + sum |

## 19. Kết luận

Filter aggregation tạo một bucket duy nhất chứa document khớp điều kiện và cho phép chạy sub-aggregation trên tập con đó. Filters aggregation tạo nhiều bucket theo các điều kiện có tên, phù hợp để so sánh trạng thái, phân khúc hoặc nhóm nghiệp vụ. Các bucket của filters có thể chồng lấn nếu một document khớp nhiều filter.

Top-level query giới hạn tập document cho hits và aggregation thông thường. Filter aggregation chỉ ảnh hưởng nhánh thống kê của nó; post_filter chỉ lọc hits sau khi aggregation chạy; global aggregation bỏ qua top-level query và cần được dùng cẩn thận với điều kiện bảo mật.

Trong Spring Data Elasticsearch, có thể khai báo aggregation cố định bằng @Aggregation hoặc xây dựng query động bằng NativeQuery và Elasticsearch Java Client. Hãy chọn mapping phù hợp, đọc đúng bucket và metric, giới hạn cardinality, rồi kiểm thử bằng dữ liệu có kết quả dự kiến rõ ràng. Cấu trúc aggregation tốt phải thể hiện chính xác tập document mà mỗi con số đang mô tả.
