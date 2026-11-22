# Terms aggregation để tạo nhóm và bộ lọc thống kê

## 1. Terms aggregation là gì?

Trong Elasticsearch, aggregation dùng để tổng hợp dữ liệu tìm kiếm. Thay vì chỉ lấy danh sách document, ứng dụng có thể yêu cầu Elasticsearch nhóm document theo một thuộc tính và tính toán số liệu cho từng nhóm.

**Terms aggregation** là một bucket aggregation. Elasticsearch tạo một bucket cho mỗi giá trị khác nhau của field được chọn, sau đó đếm số document thuộc từng bucket.

Ví dụ index `products` có các document:

| ID | name | category | price |
|---|---|---|---:|
| p-01 | Wireless Headphones | audio | 1200000 |
| p-02 | Bluetooth Speaker | audio | 850000 |
| p-03 | Mechanical Keyboard | accessories | 1500000 |
| p-04 | USB Hub | accessories | 350000 |
| p-05 | Office Chair | furniture | 2400000 |
| p-06 | Standing Desk | furniture | 5200000 |

Nếu nhóm theo `category`, Elasticsearch tạo ba bucket:

| Bucket key | doc_count |
|---|---:|
| audio | 2 |
| accessories | 2 |
| furniture | 2 |

Mỗi bucket chứa những document có giá trị category tương ứng. Từ các bucket này, ứng dụng có thể tạo bộ lọc danh mục, biểu đồ phân bố sản phẩm hoặc thống kê theo từng nhóm.

Terms aggregation hữu ích cho:

- Đếm số sản phẩm theo danh mục, thương hiệu hoặc trạng thái.
- Tạo danh sách facet để người dùng lọc kết quả.
- Thống kê đơn hàng theo trạng thái, khu vực hoặc kênh bán.
- Nhóm log theo level, service hoặc mã lỗi.
- Tính metric như tổng doanh thu, giá trung bình hoặc giá lớn nhất bên trong từng nhóm.

Terms aggregation chỉ trả về các bucket được chọn theo cấu hình. Nó không mặc nhiên liệt kê toàn bộ giá trị duy nhất nếu field có cardinality rất lớn.

## 2. Cấu trúc Terms aggregation trong Query DSL

Một terms aggregation cơ bản có cấu trúc:

~~~http
GET /products/_search
{
  "size": 0,
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

- `size: 0` ở cấp search request yêu cầu không trả về document hits; request chỉ cần kết quả aggregation.
- `aggs` khai báo các aggregation cần thực hiện.
- `categories` là tên do ứng dụng đặt cho aggregation.
- `terms` xác định loại bucket aggregation.
- `field` chỉ định field được dùng để tạo bucket.

Tên `categories` chỉ là tên định danh của aggregation trong response. Nó không bắt buộc trùng tên field hoặc tên entity.

Response rút gọn:

~~~json
{
  "hits": {
    "total": {
      "value": 6,
      "relation": "eq"
    },
    "hits": []
  },
  "aggregations": {
    "categories": {
      "doc_count_error_upper_bound": 0,
      "sum_other_doc_count": 0,
      "buckets": [
        {
          "key": "accessories",
          "doc_count": 2
        },
        {
          "key": "audio",
          "doc_count": 2
        },
        {
          "key": "furniture",
          "doc_count": 2
        }
      ]
    }
  }
}
~~~

Mỗi bucket có hai thông tin cơ bản:

- `key`: giá trị của field tạo nên nhóm.
- `doc_count`: số document thuộc bucket.

Aggregation response nằm trong `aggregations`. Nó độc lập với danh sách document ở `hits.hits`. Vì vậy, request có thể trả về 0 document hits nhưng vẫn trả về các bucket thống kê.

## 3. Chọn field phù hợp để tạo bucket

Terms aggregation cần một field có thể dùng cho aggregation. Các kiểu field thường phù hợp gồm:

- `keyword`.
- Các kiểu số như `integer`, `long`, `float` và `double`.
- `ip`.
- `boolean`.
- `binary` trong các trường hợp được hỗ trợ.

Không thể chạy terms aggregation trên field `text` theo mặc định. Field text được analyzer chia thành token, nên nhóm theo field đó có thể mang ý nghĩa nhóm theo từng từ đã phân tích thay vì nhóm theo toàn bộ giá trị gốc.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "active": {
        "type": "boolean"
      }
    }
  }
}
~~~

Nếu cần nhóm theo tên đầy đủ, dùng field `name.keyword`:

~~~json
{
  "aggs": {
    "product_names": {
      "terms": {
        "field": "name.keyword"
      }
    }
  }
}
~~~

Nếu dùng field `name` kiểu text, Elasticsearch thường báo lỗi rằng fielddata bị tắt. Có thể bật fielddata, nhưng việc này có thể sử dụng nhiều heap memory vì Elasticsearch phải xây dựng dữ liệu phục vụ aggregation trên các token đã phân tích. Với nhu cầu nhóm theo giá trị nguyên văn, multi-field keyword thường là lựa chọn phù hợp hơn.

Trước khi viết aggregation, hãy kiểm tra mapping bằng:

~~~http
GET /products/_mapping
~~~

Không nên chọn field chỉ vì tên của nó có vẻ phù hợp. Kiểu dữ liệu và cách mapping quyết định semantics của bucket.

## 4. Size: số bucket được trả về

Theo mặc định, terms aggregation trả về tối đa 10 bucket có số document lớn nhất.

Ví dụ:

~~~json
{
  "aggs": {
    "top_categories": {
      "terms": {
        "field": "category",
        "size": 5
      }
    }
  }
}
~~~

`size: 5` yêu cầu trả về tối đa năm bucket. Mặc định thứ tự là số document giảm dần, tức bucket có `doc_count` lớn nhất đứng trước.

Cần phân biệt hai tham số `size`:

| Vị trí | Ý nghĩa |
|---|---|
| Search request `size` | Số document hits trả về |
| Terms aggregation `size` | Số bucket trả về |

Ví dụ:

~~~json
{
  "size": 20,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 8
      }
    }
  }
}
~~~

Request này trả về tối đa 20 document hits và tối đa 8 bucket danh mục. Hai giới hạn hoạt động độc lập.

Nếu chỉ cần thống kê, đặt search request `size` bằng 0 để không tải document không cần thiết:

~~~json
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
~~~

Tăng aggregation size giúp lấy thêm bucket nhưng cũng làm tăng lượng dữ liệu và bộ nhớ cần thiết. Elasticsearch áp dụng giới hạn `search.max_buckets` cho tổng số bucket của request. Không nên đặt size cực lớn để cố lấy tất cả giá trị duy nhất.

## 5. Order: sắp xếp bucket

Terms aggregation mặc định sắp xếp bucket theo `_count` giảm dần:

~~~json
{
  "terms": {
    "field": "category",
    "size": 10,
    "order": {
      "_count": "desc"
    }
  }
}
~~~

Có thể sắp xếp theo key:

~~~json
{
  "terms": {
    "field": "category",
    "size": 20,
    "order": {
      "_key": "asc"
    }
  }
}
~~~

Các lựa chọn thường gặp:

| Order | Ý nghĩa |
|---|---|
| `_count: desc` | Số document giảm dần; mặc định |
| `_count: asc` | Số document tăng dần |
| `_key: asc` | Giá trị bucket tăng dần |
| `_key: desc` | Giá trị bucket giảm dần |

Sắp xếp theo key tăng hoặc giảm là cách an toàn để lấy bucket theo thứ tự giá trị. Với keyword, thứ tự key là thứ tự từ vựng; với số, Elasticsearch sắp xếp theo giá trị số.

Cần thận trọng với `_count: asc`. Khi dữ liệu phân tán trên nhiều shard, mỗi shard chỉ gửi một tập candidate terms về node điều phối. Những term hiếm có thể không được chọn làm candidate ở tất cả shard, khiến danh sách kết quả không đầy đủ. Nếu cần tìm term hiếm, hãy xem xét `rare_terms` aggregation thay vì sắp xếp terms theo count tăng dần.

Sắp xếp theo sub-aggregation cũng có thể cho kết quả sai nếu chọn một metric không phù hợp. Elasticsearch chỉ bảo đảm một số trường hợp đặc biệt, ví dụ sort theo giá trị max giảm dần hoặc min tăng dần. Hãy ưu tiên thứ tự mặc định theo count giảm dần hoặc theo key khi không có yêu cầu khác.

## 6. min_doc_count: chỉ lấy nhóm có đủ số document

`min_doc_count` xác định số document tối thiểu để bucket được trả về. Mặc định là 1.

Ví dụ chỉ lấy danh mục có ít nhất 5 sản phẩm:

~~~json
{
  "aggs": {
    "popular_categories": {
      "terms": {
        "field": "category",
        "size": 20,
        "min_doc_count": 5
      }
    }
  }
}
~~~

Nếu một danh mục chỉ có 2 sản phẩm, bucket đó không xuất hiện trong response.

Có thể kết hợp với `shard_min_doc_count` để loại candidate terms có số lượng quá thấp ngay tại từng shard:

~~~json
{
  "terms": {
    "field": "category",
    "size": 20,
    "min_doc_count": 10,
    "shard_min_doc_count": 2
  }
}
~~~

`min_doc_count` được đánh giá sau khi tổng hợp kết quả từ các shard. `shard_min_doc_count` được áp dụng ở shard trước khi gửi candidate lên node điều phối. Đặt `shard_min_doc_count` quá cao có thể làm mất term đáng lẽ đạt ngưỡng khi cộng dồn giữa các shard.

Nếu đặt `min_doc_count: 0`, Elasticsearch có thể trả về bucket có count bằng 0 từ những term còn trong dictionary, bao gồm một số term chỉ còn liên quan đến document đã xóa. Không nên coi mọi bucket count 0 là một giá trị hiện hành chắc chắn có document phù hợp.

## 7. Include và exclude: giới hạn giá trị bucket

`include` và `exclude` lọc các giá trị term được phép xuất hiện trong bucket. Chúng không thay thế query filter và không có nghĩa là document bị xóa khỏi kết quả hits.

Ví dụ chỉ thống kê một số danh mục:

~~~json
{
  "aggs": {
    "selected_categories": {
      "terms": {
        "field": "category",
        "include": [
          "audio",
          "accessories"
        ]
      }
    }
  }
}
~~~

Ví dụ loại một số giá trị:

~~~json
{
  "aggs": {
    "categories_without_test": {
      "terms": {
        "field": "category",
        "exclude": [
          "test",
          "internal"
        ]
      }
    }
  }
}
~~~

Có thể dùng pattern dạng regular expression cho include hoặc exclude khi cần lọc theo quy tắc tên. Hãy kiểm tra cú pháp và semantics regex của Elasticsearch trước khi sử dụng.

Cần phân biệt:

- Query filter giới hạn document được đưa vào quá trình tìm kiếm và aggregation.
- Include/exclude giới hạn term values được phép tạo bucket.
- Nếu document bị loại khỏi bucket vì giá trị field không nằm trong include, document đó vẫn có thể xuất hiện trong `hits.hits` nếu query chính khớp.

## 8. Missing: xử lý document không có field

Mặc định, document không có giá trị cho field được aggregate sẽ không được đưa vào bucket nào.

Ví dụ có sản phẩm không có category. Nếu muốn gom các document đó vào một bucket có nhãn riêng, dùng `missing`:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "missing": "uncategorized"
      }
    }
  }
}
~~~

Khi đó, document thiếu category được tính vào bucket có key `uncategorized`.

`missing` là giá trị thay thế trong aggregation. Nó không ghi giá trị đó ngược lại vào document và không làm thay đổi source.

Nếu field là numeric hoặc kiểu khác, chọn giá trị missing phù hợp với kiểu dữ liệu của field và phiên bản Elasticsearch.

## 9. Kết hợp Terms aggregation với metric sub-aggregation

Terms aggregation tạo bucket; metric aggregation tính toán số liệu trong từng bucket.

Ví dụ nhóm sản phẩm theo danh mục và tính giá trung bình, tổng giá và giá cao nhất:

~~~http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "categories": {
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
        "total_price": {
          "sum": {
            "field": "price"
          }
        },
        "maximum_price": {
          "max": {
            "field": "price"
          }
        }
      }
    }
  }
}
~~~

Mỗi bucket category sẽ có:

- `doc_count`: số sản phẩm thuộc danh mục.
- `average_price.value`: giá trung bình.
- `total_price.value`: tổng giá trị field price.
- `maximum_price.value`: giá cao nhất.

Response rút gọn:

~~~json
{
  "aggregations": {
    "categories": {
      "buckets": [
        {
          "key": "audio",
          "doc_count": 2,
          "average_price": {
            "value": 1025000.0
          },
          "total_price": {
            "value": 2050000.0
          },
          "maximum_price": {
            "value": 1200000.0
          }
        },
        {
          "key": "accessories",
          "doc_count": 2,
          "average_price": {
            "value": 925000.0
          },
          "total_price": {
            "value": 1850000.0
          },
          "maximum_price": {
            "value": 1500000.0
          }
        }
      ]
    }
  }
}
~~~

Các metric phổ biến có thể đặt bên trong bucket:

| Metric aggregation | Ý nghĩa |
|---|---|
| `avg` | Trung bình |
| `sum` | Tổng |
| `min` | Giá trị nhỏ nhất |
| `max` | Giá trị lớn nhất |
| `value_count` | Đếm số giá trị của field |
| `stats` | Kết hợp count, min, max, avg và sum |
| `extended_stats` | Thống kê mở rộng như độ lệch chuẩn |
| `cardinality` | Ước lượng số giá trị duy nhất |

`doc_count` đếm document trong bucket, còn `value_count` đếm số giá trị của một field. Với field đa trị, hai con số có thể khác nhau. `cardinality` thường là phép ước lượng, không nên dùng như số đếm chính xác tuyệt đối khi nghiệp vụ yêu cầu exact count.

## 10. Kết hợp Terms aggregation với filter aggregation

Có thể đặt một filter aggregation bên trong từng bucket để tính số liệu cho một tập con document.

Ví dụ, với mỗi danh mục, thống kê số sản phẩm đang hoạt động:

~~~json
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      },
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

Mỗi bucket category có thêm bucket `active_products`. `doc_count` của bucket con là số sản phẩm active trong danh mục đó.

Có thể thêm metric trong filter bucket:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "active_products": {
          "filter": {
            "term": {
              "active": true
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
  }
}
~~~

Cấu trúc này trả về số sản phẩm active và giá trung bình của sản phẩm active trong từng danh mục.

## 11. Filters aggregation: tạo các nhóm theo điều kiện nghiệp vụ

Terms aggregation tạo nhóm theo giá trị field. Nếu muốn tạo nhóm theo các điều kiện nghiệp vụ tự định nghĩa, có thể dùng `filters` aggregation.

Ví dụ chia sản phẩm thành ba nhóm giá:

~~~json
{
  "size": 0,
  "aggs": {
    "price_groups": {
      "filters": {
        "filters": {
          "budget": {
            "range": {
              "price": {
                "lt": 500000
              }
            }
          },
          "mid_range": {
            "range": {
              "price": {
                "gte": 500000,
                "lt": 2000000
              }
            }
          },
          "premium": {
            "range": {
              "price": {
                "gte": 2000000
              }
            }
          }
        }
      }
    }
  }
}
~~~

Response trả về bucket có tên `budget`, `mid_range` và `premium`. Mỗi bucket có `doc_count` tương ứng.

So sánh:

| Aggregation | Cách tạo nhóm | Ví dụ |
|---|---|---|
| `terms` | Một bucket cho mỗi giá trị field khác nhau | Nhóm theo category |
| `filter` | Một bucket cho một điều kiện | Chỉ đếm sản phẩm active |
| `filters` | Nhiều bucket, mỗi bucket có một điều kiện riêng | Nhóm theo khoảng giá hoặc trạng thái |

Các filter bucket có thể chồng lấn. Một document có thể thuộc nhiều bucket nếu đáp ứng nhiều điều kiện. Điều này khác với cách người dùng thường hình dung về các nhóm loại trừ lẫn nhau, nên hãy thiết kế điều kiện cẩn thận.

## 12. Query filter và post_filter khác gì bộ lọc bucket?

Trong trang tìm kiếm có facet, cần phân biệt ba vị trí lọc:

1. `query` lọc document trước khi tính hits và aggregations.
2. `post_filter` lọc hits sau khi aggregation đã được tính.
3. `include`/`exclude` trong terms aggregation lọc các term value được phép tạo bucket.

Ví dụ người dùng chọn danh mục audio nhưng giao diện vẫn muốn hiển thị số lượng của tất cả danh mục khác để người dùng có thể đổi lựa chọn. Có thể dùng query cho các bộ lọc chung và post_filter cho danh mục đã chọn:

~~~json
{
  "query": {
    "term": {
      "active": true
    }
  },
  "post_filter": {
    "term": {
      "category": "audio"
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
~~~

Trong ví dụ:

- Query chỉ lấy document active làm phạm vi cho hits và aggregation.
- Post filter chỉ giới hạn danh sách hits theo category audio.
- Aggregation categories vẫn thống kê các danh mục trong tập document active trước post filter.

Nếu đặt category audio trong query thay vì post_filter, aggregation categories cũng chỉ nhìn thấy document audio. Khi xây dựng faceted search, vị trí đặt filter quyết định số liệu facet phản ánh tập dữ liệu nào.

## 13. Terms aggregation trên nhiều field

Một terms aggregation thông thường chỉ nhóm theo một field. Nếu cần nhóm theo tổ hợp nhiều field, có thể dùng `multi_terms` aggregation.

Ví dụ nhóm theo danh mục và thương hiệu:

~~~json
{
  "size": 0,
  "aggs": {
    "category_brand": {
      "multi_terms": {
        "terms": [
          {
            "field": "category"
          },
          {
            "field": "brand"
          }
        ],
        "size": 50
      }
    }
  }
}
~~~

Mỗi bucket đại diện cho một cặp giá trị, ví dụ `audio + Acme` hoặc `audio + Contoso`.

`multi_terms` tiện lợi cho top nhóm theo tổ hợp field, nhưng thường tốn tài nguyên hơn terms aggregation một field vì Elasticsearch cần tạo khóa ghép. Nếu cần duyệt tất cả tổ hợp bucket qua nhiều trang, hãy cân nhắc composite aggregation.

Không nên nối hai field thành một chuỗi bằng script chỉ để nhóm theo cặp nếu multi_terms hoặc composite đã đáp ứng yêu cầu. Script có thể làm tăng chi phí tính toán.

## 14. Phân biệt Terms aggregation và Composite aggregation

Terms aggregation được tối ưu cho việc lấy một số bucket nổi bật, thường là các term có nhiều document nhất. Nó không phải công cụ phân trang để duyệt toàn bộ cardinality rất lớn.

Nếu field có hàng trăm nghìn hoặc hàng triệu giá trị duy nhất và ứng dụng cần đọc tất cả bucket, dùng `composite` aggregation:

| Tiêu chí | Terms aggregation | Composite aggregation |
|---|---|---|
| Mục tiêu | Top bucket theo count hoặc thứ tự | Duyệt các bucket theo từng trang |
| Số lượng | Giới hạn bởi size và max_buckets | Lấy theo batch với after_key |
| Phân trang bucket | Không có cursor phân trang đầy đủ như composite | Có after_key |
| Trường hợp phù hợp | Facet, top danh mục, top thương hiệu | Export hoặc duyệt toàn bộ nhóm có cardinality lớn |

Ví dụ composite aggregation:

~~~json
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
          }
        ]
      }
    }
  }
}
~~~

Response có thể trả `after_key`. Request tiếp theo truyền `after` bằng giá trị đó để lấy batch bucket tiếp theo.

Nếu chỉ cần 10 danh mục phổ biến nhất, terms aggregation đơn giản hơn. Nếu cần xuất tất cả giá trị category, composite aggregation phù hợp hơn.

## 15. Giới hạn phân tán: size, shard_size và độ chính xác

Elasticsearch thường chạy aggregation trên nhiều shard. Mỗi shard tạo danh sách candidate buckets cục bộ rồi gửi kết quả lên node điều phối để hợp nhất.

Terms aggregation mặc định yêu cầu mỗi shard gửi nhiều candidate hơn số bucket cuối cùng. `shard_size` mặc định được ước tính xấp xỉ `size * 1.5 + 10`.

Ví dụ:

~~~json
{
  "terms": {
    "field": "category",
    "size": 10,
    "shard_size": 30
  }
}
~~~

- `size` là số bucket cuối cùng được trả về.
- `shard_size` là số candidate terms mỗi shard gửi về để node điều phối hợp nhất.

Tăng `shard_size` thường giúp cải thiện độ chính xác của top buckets và doc counts khi dữ liệu phân tán không đồng đều giữa các shard. Tuy nhiên, nó làm tăng dữ liệu truyền qua mạng và bộ nhớ ở node điều phối. `shard_size` không thể nhỏ hơn `size`; Elasticsearch sẽ điều chỉnh lên bằng size nếu cần.

Ngay cả khi tăng shard_size, doc_count vẫn có thể là ước lượng trong một số tình huống. Hãy đọc các metadata aggregation thay vì mặc định mọi count đều chính xác.

### sum_other_doc_count

`sum_other_doc_count` là tổng số document không nằm trong các bucket được trả về, do giới hạn top bucket ở size hoặc do quá trình chọn candidate trên shard.

Nếu giá trị này lớn hơn 0, aggregation đã bỏ qua một phần document khỏi các bucket trong response. Điều đó không có nghĩa các document bị xóa khỏi index; chúng chỉ không thuộc những bucket được trả về.

### doc_count_error_upper_bound

Có thể bật `show_term_doc_count_error`:

~~~json
{
  "terms": {
    "field": "category",
    "size": 10,
    "show_term_doc_count_error": true
  }
}
~~~

Elasticsearch trả thêm `doc_count_error_upper_bound`, là cận trên của sai số doc_count theo từng bucket trong điều kiện có thể tính toán.

Thông tin sai số này có ý nghĩa khi terms được sắp xếp theo `_count` giảm dần. Với một số kiểu order khác, Elasticsearch có thể trả giá trị `-1` để chỉ ra không thể xác định cận sai số theo cách đó.

Nếu nghiệp vụ yêu cầu thống kê chính xác tuyệt đối, hãy đánh giá lại cách phân phối dữ liệu, yêu cầu order và cơ chế tổng hợp. Không nên mặc định terms aggregation top-N luôn trả mọi count chính xác tuyệt đối trên cluster nhiều shard.

## 16. Giới hạn hiệu năng và cardinality

Cardinality là số lượng giá trị khác nhau của field. Field có ít giá trị như trạng thái đơn hàng thường có cardinality thấp; field như email, mã giao dịch hoặc user ID có thể có cardinality rất cao.

Một số nguyên tắc:

- Dùng terms aggregation cho field có cardinality phù hợp với số bucket cần trả.
- Chỉ tăng size khi ứng dụng thực sự cần thêm bucket.
- Theo dõi giới hạn `search.max_buckets`.
- Tăng shard_size có chủ đích, dựa trên sai số và phân bố dữ liệu.
- Dùng keyword/doc_values cho các field phân loại.
- Tránh bật fielddata trên text chỉ để làm aggregation nếu chưa đánh giá bộ nhớ.
- Dùng composite aggregation khi cần duyệt tất cả bucket.
- Không chạy nhiều aggregation có cardinality cao trong cùng request nếu không cần.

Global ordinals là một cơ chế tối ưu thường được Elasticsearch sử dụng cho terms aggregation trên keyword field. Với workload ghi và tìm kiếm có yêu cầu đặc biệt, có thể cân nhắc `eager_global_ordinals` để chuyển một phần công việc xây dựng ordinal sang lúc refresh. Thiết lập này cần cân bằng chi phí refresh và thời gian truy vấn, không nên bật mặc định cho mọi field.

## 17. Thực hiện Terms aggregation bằng Spring Data Elasticsearch

Spring Data Elasticsearch sử dụng `NativeQuery` khi cần query phức tạp hoặc aggregation. `NativeQuery` cho phép xây dựng aggregation bằng các kiểu của Elasticsearch Java API Client.

Giả sử entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String brand;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // Constructors, getters và setters
}
~~~

Tạo terms aggregation theo category:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withAggregation(
        "categories",
        Aggregation.of(a -> a
            .terms(t -> t
                .field("category")
                .size(20)
            )
        )
    )
    .build();

SearchHits<Product> searchHits = operations.search(
    query,
    Product.class
);
~~~

Tên aggregation là `categories`. Field được nhóm là `category`. Size 20 giới hạn số bucket trả về.

Có thể kết hợp query filter để chỉ thống kê sản phẩm active:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q
        .term(t -> t
            .field("active")
            .value(true)
        )
    )
    .withAggregation(
        "categories",
        Aggregation.of(a -> a
            .terms(t -> t
                .field("category")
                .size(20)
            )
        )
    )
    .build();
~~~

Khi có query filter, aggregation chỉ tính trên document khớp query. Nếu chỉ cần aggregation mà không cần document hits, có thể dùng request size bằng 0 thông qua tùy chọn query phù hợp của phiên bản đang sử dụng hoặc gọi Search API trực tiếp với `size: 0`.

Các import liên quan trong Spring Data Elasticsearch dùng Elasticsearch Java API Client:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
~~~

`Aggregation` ở đây là class builder của Elasticsearch Java API Client. Không nhầm với các lớp aggregation legacy của Elasticsearch client cũ.

## 18. Đọc kết quả aggregation từ SearchHits

Khi dùng Spring Data Elasticsearch, aggregation được trả về trong `SearchHits.getAggregations()`. Kiểu trả về là `AggregationsContainer<?>`; với Elasticsearch Java API Client hiện hành, implementation thường là `ElasticsearchAggregations`.

Ví dụ lấy các bucket của string terms aggregation:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;

import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;

SearchHits<Product> searchHits = operations.search(
    query,
    Product.class
);

if (searchHits.getAggregations() instanceof ElasticsearchAggregations aggregations) {

    ElasticsearchAggregation categories = aggregations.get("categories");

    if (categories != null) {
        Aggregate aggregate = categories.aggregation().getAggregate();

        if (aggregate.isSterms()) {
            for (StringTermsBucket bucket : aggregate.sterms().buckets().array()) {
                String category = bucket.key().stringValue();
                long documentCount = bucket.docCount();

                System.out.println(category + ": " + documentCount);
            }
        }
    }
}
~~~

Luồng đọc dữ liệu:

1. Gọi `SearchHits.getAggregations()` để lấy container.
2. Ép kiểu về `ElasticsearchAggregations` khi đang dùng client implementation tương ứng.
3. Gọi `get("categories")` để lấy aggregation theo tên đã khai báo trong query.
4. Gọi `aggregation().getAggregate()` để lấy aggregate của Elasticsearch Java API Client.
5. Kiểm tra kiểu bucket bằng `isSterms()`.
6. Lấy danh sách bucket bằng `sterms().buckets().array()`.
7. Đọc key và doc_count của từng bucket.

Terms aggregation có thể trả bucket kiểu string, long, double hoặc kiểu dữ liệu khác tùy field. Vì vậy, không phải aggregation nào cũng là `sterms`. Với field số nguyên, response có thể là `lterms`; với số thực, có thể là `dterms`. Hãy kiểm tra variant trước khi đọc bucket và chọn kiểu bucket tương ứng.

Trong Spring Data 6.x, cấu trúc `ElasticsearchAggregations` dựa trên Java API Client. Các phiên bản Spring Data cũ sử dụng client và kiểu aggregation khác, vì vậy code đọc kết quả có thể không tương thích nguyên trạng.

## 19. Đọc metric sub-aggregation trong từng bucket

Khi terms aggregation có metric con, mỗi bucket mang thêm map các aggregation con. Ví dụ request có `average_price`:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
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

Trong Java API Client, bucket có thể chứa aggregation con thông qua `bucket.aggregations()`. Ví dụ đọc giá trung bình:

~~~java
for (StringTermsBucket bucket : aggregate.sterms().buckets().array()) {

    String category = bucket.key().stringValue();
    long count = bucket.docCount();

    Aggregate averagePrice = bucket.aggregations().get("average_price");

    if (averagePrice != null && averagePrice.isAvg()) {
        double average = averagePrice.avg().value();

        System.out.println(
            category + " | count=" + count + " | average=" + average
        );
    }
}
~~~

Tên aggregation con phải khớp với tên đã khai báo trong request. Cần kiểm tra variant trước khi gọi accessor như `avg()` hoặc `sum()` vì kiểu trả về phụ thuộc loại metric.

## 20. Filters và terms trong cùng một request

Có thể tạo dashboard thống kê gồm nhiều nhóm và nhiều metric trong một request, giúp Elasticsearch thực hiện tổng hợp trên cùng tập document.

Ví dụ thống kê theo danh mục, đồng thời chỉ tính sản phẩm active và chia nhóm giá bên trong mỗi danh mục:

~~~json
{
  "size": 0,
  "query": {
    "term": {
      "active": true
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "price_ranges": {
          "range": {
            "field": "price",
            "ranges": [
              {
                "key": "under_500k",
                "to": 500000
              },
              {
                "key": "500k_to_2m",
                "from": 500000,
                "to": 2000000
              },
              {
                "key": "over_2m",
                "from": 2000000
              }
            ]
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

Kết quả có cấu trúc:

~~~text
categories
  ├── audio
  │    ├── doc_count
  │    ├── price_ranges
  │    │    ├── under_500k
  │    │    ├── 500k_to_2m
  │    │    └── over_2m
  │    └── average_price
  ├── accessories
  │    └── ...
  └── furniture
       └── ...
~~~

Đây là ví dụ về bucket aggregation lồng nhau. Từ một request, ứng dụng có thể xây dựng dashboard gồm số lượng theo danh mục, phân bố giá và giá trung bình.

Khi lồng nhiều aggregation, hãy kiểm tra tổng số bucket được tạo ra và giới hạn `search.max_buckets`. Một terms aggregation có 100 bucket, mỗi bucket có 20 range bucket con, có thể tạo số lượng bucket lớn hơn nhiều so với dự kiến.

## 21. Những lỗi thường gặp khi dùng Terms aggregation

**Aggregate trên field text.** Elasticsearch mặc định không cho phép terms aggregation trên text field. Dùng keyword sub-field hoặc mapping phù hợp.

**Nhầm search size với aggregation size.** Search size điều khiển hits, aggregation size điều khiển bucket. Hai giá trị không thay thế nhau.

**Nghĩ rằng terms trả tất cả giá trị duy nhất.** Mặc định chỉ trả top 10 bucket. Tăng size trong giới hạn hoặc dùng composite khi cần duyệt tất cả.

**Coi doc_count luôn chính xác tuyệt đối.** Terms aggregation phân tán trên nhiều shard có thể trả count gần đúng. Kiểm tra shard_size và metadata sai số.

**Dùng count tăng dần để tìm term hiếm.** Order theo `_count: asc` có thể bỏ sót term do cách chọn candidate trên shard. Dùng `rare_terms` cho nhu cầu tìm giá trị hiếm.

**Tăng shard_size quá cao.** Tăng shard_size có thể cải thiện độ chính xác nhưng cũng tăng bộ nhớ và dữ liệu truyền giữa shard và node điều phối.

**Nhầm include/exclude với query filter.** Include/exclude lọc term values của bucket. Query filter giới hạn document tham gia tìm kiếm và aggregation.

**Bỏ qua document không có field.** Mặc định document không có giá trị sẽ không nằm trong bucket. Dùng `missing` nếu cần nhóm riêng.

**Coi doc_count là số giá trị field.** Với field đa trị, một document có thể xuất hiện trong nhiều bucket. `doc_count` đếm document trong bucket, không phải số lần xuất hiện của mọi giá trị.

**Lạm dụng fielddata.** Bật fielddata trên text có thể tăng đáng kể heap usage. Ưu tiên keyword field nếu cần nhóm theo giá trị đầy đủ.

**Lấy quá nhiều bucket.** Cardinality cao và size lớn có thể chạm `search.max_buckets` hoặc gây áp lực bộ nhớ. Chọn top-N hoặc composite theo nhu cầu.

**Đọc sai kiểu aggregation trong Java.** String terms, long terms và double terms có variant khác nhau. Kiểm tra aggregate type trước khi gọi accessor.

**Dùng post_filter không đúng mục đích.** Post filter chỉ lọc hits sau aggregation. Nếu muốn aggregation cũng phản ánh điều kiện lọc, đặt điều kiện trong query hoặc trong filter aggregation thích hợp.

## 22. Quy trình thiết kế Terms aggregation

Có thể triển khai theo các bước:

1. Xác định câu hỏi thống kê: nhóm theo danh mục, thương hiệu, trạng thái hay thuộc tính khác.
2. Kiểm tra mapping của field và chọn keyword/numeric field có thể aggregate.
3. Xác định có cần lấy document hits hay chỉ cần thống kê; đặt search size phù hợp.
4. Khai báo tên aggregation và field trong `terms`.
5. Chọn số bucket `size` theo giao diện.
6. Giữ order mặc định theo count giảm dần nếu muốn top nhóm phổ biến.
7. Dùng `min_doc_count`, `include`, `exclude` hoặc `missing` khi nghiệp vụ cần.
8. Thêm metric sub-aggregation để tính số liệu bên trong từng bucket.
9. Thêm `filter` hoặc `filters` aggregation nếu cần các nhóm theo điều kiện.
10. Kiểm tra `sum_other_doc_count`, `doc_count_error_upper_bound` và shard distribution.
11. Đọc aggregation từ `SearchHits` và kiểm tra đúng variant.
12. Dùng composite aggregation nếu cần duyệt tất cả bucket có cardinality lớn.
13. Đánh giá số lượng bucket, thời gian thực thi và bộ nhớ trên dữ liệu thực tế.

## Kết luận

Terms aggregation tạo một bucket cho mỗi giá trị khác nhau của field và đếm số document trong từng bucket. Đây là nền tảng để xây dựng facet, bộ lọc danh mục và dashboard thống kê. Có thể kết hợp terms với metric sub-aggregation để tính tổng, trung bình, min, max hoặc với filter aggregation để thống kê các tập con theo điều kiện.

Cần chọn field có thể aggregate, thường là `keyword` hoặc numeric. Mặc định terms chỉ trả top 10 bucket theo doc_count giảm dần; `size`, `shard_size`, `min_doc_count`, `include`, `exclude` và `missing` giúp điều chỉnh kết quả. Trên cluster nhiều shard, bucket count có thể là ước lượng, nên cần chú ý `sum_other_doc_count` và `doc_count_error_upper_bound`.

Trong Spring Data Elasticsearch, `NativeQuery` cho phép khai báo terms aggregation bằng Elasticsearch Java API Client. Kết quả được đọc từ `SearchHits.getAggregations()` qua `ElasticsearchAggregations` và các bucket tương ứng. Nếu cần duyệt toàn bộ giá trị duy nhất với cardinality lớn, hãy dùng composite aggregation thay vì tăng terms size vô hạn.

## Tài liệu tham khảo

- [Elasticsearch — Terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-terms-aggregation)
- [Elasticsearch — Bucket aggregations](https://www.elastic.co/docs/reference/aggregations)
- [Elasticsearch — Filters aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-filters-aggregation)
- [Elasticsearch — Composite aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-composite-aggregation)
- [Elasticsearch — Rare terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-rare-terms-aggregation)
- [Spring Data Elasticsearch — Elasticsearch Operations and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — ElasticsearchAggregations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregations.html)
