# Bucket size, shard_size, số bucket và chi phí tài nguyên

Aggregation cho phép Elasticsearch nhóm document và tính thống kê như số lượng sản phẩm theo category, thương hiệu, trạng thái hoặc khoảng thời gian. Với field có nhiều giá trị khác nhau, một terms aggregation có thể tạo rất nhiều bucket. Khi dữ liệu được phân tán trên nhiều shard, Elasticsearch còn phải thu thập các bucket ứng viên từ từng shard rồi hợp nhất ở coordinating node.

Bốn khái niệm cần phân biệt khi thiết kế aggregation:

- **size:** số bucket tối đa mà một bucket aggregation như terms trả về trong kết quả cuối.
- **shard_size:** số bucket ứng viên mà mỗi shard gửi về cho coordinating node trong một terms aggregation.
- **bucket count:** tổng số bucket được tạo trong cây aggregation của một request, kể cả các bucket lồng nhau.
- **resource cost:** CPU, heap, bộ nhớ tạm, dữ liệu truyền giữa shard và coordinating node, cùng kích thước response.

Chọn size quá nhỏ có thể bỏ mất bucket người dùng cần xem. Tăng size hoặc shard_size quá lớn có thể làm request tốn tài nguyên. Thiết kế tốt cần cân bằng giữa số liệu cần hiển thị, độ chính xác và chi phí.

## 1. Bucket aggregation là gì?

Bucket aggregation chia document thành các nhóm theo một tiêu chí. Mỗi bucket chứa document thỏa điều kiện của nhóm đó và có thể chứa các sub-aggregation để tính thống kê sâu hơn.

Ví dụ, nhóm sản phẩm theo category:

~~~json
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 10
      }
    }
  }
}
~~~

Nếu index có các category ACCESSORIES, OFFICE, HOME, Elasticsearch tạo bucket cho từng giá trị được chọn. Mỗi bucket thường có:

- key: giá trị đại diện cho bucket.
- doc_count: số document thuộc bucket.
- Các aggregation con nếu được khai báo.

Response minh họa:

~~~json
{
  "aggregations": {
    "categories": {
      "buckets": [
        { "key": "ACCESSORIES", "doc_count": 120 },
        { "key": "OFFICE", "doc_count": 85 },
        { "key": "HOME", "doc_count": 30 }
      ]
    }
  }
}
~~~

Trong ví dụ này, terms.size bằng 10 yêu cầu trả tối đa 10 category bucket trong kết quả aggregation. Nó không giới hạn số hit của search request. Thuộc tính size ở cấp cao nhất của search request điều khiển số hit; terms.size điều khiển số bucket.

Có thể đặt top-level size bằng 0 khi chỉ cần aggregation và không cần danh sách document.

## 2. size: số bucket cuối cùng được trả về

Với terms aggregation, size là số bucket tối đa mà coordinating node trả về sau khi hợp nhất kết quả từ các shard.

~~~json
{
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand",
        "size": 5
      }
    }
  }
}
~~~

Request trên lấy tối đa năm thương hiệu. Mặc định, terms aggregation thường trả 10 bucket nếu không khai báo size.

### 2.1. size không phải tổng số giá trị khác nhau

Giả sử field brand có 2.000 giá trị khác nhau, nhưng request đặt size bằng 10. Kết quả chỉ chứa tối đa 10 bucket đứng đầu theo tiêu chí sort mặc định. Các brand còn lại không được trả thành bucket trong response đó.

Điều này không có nghĩa index chỉ có 10 brand. Nó chỉ có nghĩa aggregation đang yêu cầu top 10.

Các thông tin hữu ích trong response:

- buckets: danh sách bucket thực tế được trả về.
- sum_other_doc_count: tổng document count thuộc những bucket bị bỏ khỏi danh sách kết quả.
- doc_count_error_upper_bound: cận trên của sai số doc_count khi Elasticsearch có thể tính được theo kiểu ordering hiện tại.

sum_other_doc_count không phải số document duy nhất chắc chắn nằm ngoài các bucket. Với field multi-valued, một document có thể đóng góp vào nhiều bucket nên tổng count có thể lớn hơn số document bị loại khỏi danh sách.

### 2.2. Chọn size theo giao diện

| Nhu cầu | Cách chọn ban đầu |
| --- | --- |
| Facet nhỏ, danh sách trạng thái cố định | Đặt size đủ chứa các giá trị dự kiến. |
| Top thương hiệu hoặc category | Chọn top N mà giao diện hiển thị, ví dụ 10 hoặc 20. |
| Dashboard có nhiều nhóm | Chỉ lấy các bucket thực sự được dùng trong biểu đồ. |
| Muốn duyệt mọi giá trị khác nhau | Dùng composite aggregation thay vì đặt size cực lớn. |

Không có một giá trị size phù hợp cho mọi index. Hãy dựa vào cardinality, số lượng shard, số tầng aggregation và nhu cầu UI.

## 3. shard_size: số bucket ứng viên từ mỗi shard

Trong index phân tán, mỗi shard chỉ nhìn thấy một phần dữ liệu. Để tạo top terms aggregation, mỗi shard chọn các bucket ứng viên cục bộ rồi gửi chúng tới coordinating node. Coordinating node hợp nhất các ứng viên và tạo danh sách bucket cuối cùng.

shard_size điều khiển số bucket ứng viên mỗi shard gửi về trong terms aggregation. Giá trị này thường lớn hơn size để giảm nguy cơ bỏ sót một term có tổng count lớn trên toàn index nhưng không đứng đầu ở một shard riêng lẻ.

Ví dụ:

~~~json
{
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand",
        "size": 10,
        "shard_size": 50
      }
    }
  }
}
~~~

Trong ví dụ:

- Mỗi shard gửi tối đa 50 bucket ứng viên.
- Coordinating node hợp nhất các ứng viên.
- Kết quả cuối cùng trả tối đa 10 bucket.

shard_size không phải số bucket cuối cùng trong response. Nó tác động tới lượng dữ liệu trung gian được thu thập từ mỗi shard.

### 3.1. Vì sao shard_size lớn hơn size?

Giả sử có ba shard. Một thương hiệu có phân bố document như sau:

| Brand | Shard 1 | Shard 2 | Shard 3 | Tổng |
| --- | ---: | ---: | ---: | ---: |
| ACME | 40 | 0 | 0 | 40 |
| CONTOSO | 0 | 35 | 0 | 35 |
| NORTHWIND | 0 | 0 | 30 | 30 |
| GLOBEX | 15 | 15 | 15 | 45 |

Nếu mỗi shard chỉ gửi một bucket ứng viên, shard 1 gửi ACME, shard 2 gửi CONTOSO và shard 3 gửi NORTHWIND. Bucket GLOBEX có count 15 ở từng shard nhưng không đứng đầu trên shard nào, vì vậy có thể bị bỏ khỏi tập ứng viên. Coordinating node không thể cộng các count mà nó chưa nhận được.

Khi tăng shard_size, nhiều bucket cục bộ hơn được gửi về. GLOBEX có cơ hội xuất hiện ở cả ba shard và được hợp nhất thành count 45, từ đó có thể đứng đầu kết quả toàn cục.

Ví dụ này cho thấy size lớn không tự giải quyết mọi sai số phân tán. shard_size ảnh hưởng trực tiếp đến chất lượng tập ứng viên từ từng shard.

### 3.2. Giá trị mặc định của shard_size

Với terms aggregation, Elasticsearch thường tính shard_size mặc định lớn hơn size; công thức mặc định được dùng phổ biến là:

~~~text
shard_size = size * 1.5 + 10
~~~

Đây là giá trị mặc định của terms aggregation theo tài liệu Elasticsearch hiện hành, không phải quy tắc áp dụng cho mọi loại bucket aggregation. Hãy kiểm tra tài liệu của đúng phiên bản đang chạy nếu phụ thuộc vào giá trị mặc định.

Có thể khai báo shard_size tường minh khi cần điều chỉnh độ chính xác hoặc chi phí. Không nên mặc định tăng nó lên nhiều lần mà chưa đo tác động.

## 4. Trade-off giữa size và shard_size

Hai tham số điều khiển hai phần khác nhau của quá trình:

| Tham số | Phạm vi | Tăng giá trị sẽ | Chi phí chính |
| --- | --- | --- | --- |
| size | Kết quả cuối tại coordinating node | Trả nhiều bucket hơn. | Response lớn hơn, nhiều bucket và sub-aggregation được giữ lại. |
| shard_size | Tập bucket ứng viên mỗi shard | Gửi nhiều ứng viên hơn để hợp nhất. | Nhiều dữ liệu trung gian, network traffic và bộ nhớ ở coordinating node. |

Tăng size giúp người dùng thấy nhiều bucket hơn, nhưng cũng làm tăng số bucket cuối cùng và các sub-aggregation cần tính cho chúng.

Tăng shard_size chủ yếu cải thiện độ đầy đủ của tập ứng viên và độ chính xác count/top terms trong một số kiểu ordering. Nó không làm response cuối có nhiều bucket hơn nếu size vẫn giữ nguyên.

Ví dụ:

~~~json
{
  "aggs": {
    "top_categories": {
      "terms": {
        "field": "category",
        "size": 20,
        "shard_size": 100
      }
    }
  }
}
~~~

Kết quả cuối vẫn tối đa 20 category, dù mỗi shard có thể gửi tới 100 ứng viên.

## 5. Sai số doc_count trong aggregation phân tán

Với nhiều shard, coordinating node không nhất thiết nhận mọi term từ mọi shard. Một term bị bỏ khỏi danh sách ứng viên ở shard nào đó có thể khiến doc_count cuối cùng thấp hơn số thực tế.

Terms aggregation có thể trả thêm thông tin về sai số:

~~~json
{
  "aggregations": {
    "top_brands": {
      "doc_count_error_upper_bound": 12,
      "sum_other_doc_count": 430,
      "buckets": [
        {
          "key": "GLOBEX",
          "doc_count": 120,
          "doc_count_error_upper_bound": 3
        },
        {
          "key": "ACME",
          "doc_count": 98,
          "doc_count_error_upper_bound": 0
        }
      ]
    }
  }
}
~~~

doc_count_error_upper_bound là cận trên cho phần count có thể bị thiếu, khi Elasticsearch tính được cận đó với ordering đã chọn. Giá trị 0 nghĩa là không có sai số bị bỏ sót theo cận được báo cáo. Giá trị -1 có nghĩa là Elasticsearch không thể xác định cận sai số cho cách sắp xếp đó.

Có thể yêu cầu sai số theo từng bucket bằng show_term_doc_count_error khi ordering hỗ trợ:

~~~json
{
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand",
        "size": 10,
        "show_term_doc_count_error": true
      }
    }
  }
}
~~~

Không nên diễn giải doc_count_error_upper_bound như một tỷ lệ phần trăm hoặc số document bị thiếu chính xác. Đây là cận trên được báo cáo theo thuật toán và điều kiện của aggregation.

### 5.1. Ordering ảnh hưởng độ chính xác

Ordering mặc định của terms aggregation là theo document count giảm dần. Với ordering này, Elasticsearch có thể tính cận sai số hữu ích và tăng shard_size có thể cải thiện độ chính xác.

Một số kiểu ordering khác có giới hạn:

- Sắp xếp theo _key có thể bảo đảm count chính xác cho các bucket được trả trong trường hợp được hỗ trợ.
- Sắp xếp theo _count tăng dần có thể không chính xác trên nhiều shard. Nếu cần tìm term hiếm, nên xem xét rare_terms aggregation.
- Sắp xếp theo kết quả sub-aggregation có thể tạo kết quả top bucket khó bảo đảm chính xác toàn cục. Chỉ một số trường hợp ordering theo metric min/max có tính chất đặc biệt được Elasticsearch bảo đảm.

Nếu nghiệp vụ phụ thuộc vào thứ hạng chính xác theo một metric con, hãy xác minh giới hạn ordering của Elasticsearch thay vì cho rằng tăng shard_size luôn giải quyết được.

## 6. min_doc_count và shard_min_doc_count

Ngoài size và shard_size, terms aggregation có hai ngưỡng lọc bucket theo số document:

- min_doc_count: số document tối thiểu mà bucket phải có sau khi hợp nhất kết quả trên toàn bộ shard.
- shard_min_doc_count: ngưỡng count cục bộ để shard loại bucket trước khi gửi ứng viên tới coordinating node.

Ví dụ chỉ lấy brand có ít nhất 20 document toàn cục:

~~~json
{
  "aggs": {
    "brands": {
      "terms": {
        "field": "brand",
        "size": 50,
        "min_doc_count": 20
      }
    }
  }
}
~~~

min_doc_count hữu ích khi giao diện không cần những bucket quá nhỏ. Tuy nhiên, bucket bị loại khỏi kết quả không có nghĩa document đã bị xóa; chúng chỉ không được trả trong aggregation.

### 6.1. Rủi ro khi shard_min_doc_count quá cao

Giả sử một term có tổng 30 document nhưng phân bố trên 10 shard, mỗi shard chỉ có 3 document. Nếu shard_min_doc_count đặt là 5, từng shard có thể loại term đó trước khi gửi lên coordinator. Dù tổng toàn cục đạt 30, bucket vẫn có thể biến mất khỏi kết quả.

Vì vậy, shard_min_doc_count cần được đặt thấp hơn nhiều so với ngưỡng toàn cục khi dữ liệu phân tán. Nếu không có lý do rõ ràng, giữ mặc định thường an toàn hơn. Đừng dùng ngưỡng cục bộ như một cách thay thế cho min_doc_count.

## 7. Số bucket và giới hạn max_buckets

Một request aggregation có thể tạo cây bucket lồng nhau. Ví dụ:

- Terms theo 20 category.
- Mỗi category có 30 brand.
- Mỗi brand có 10 trạng thái tồn kho.

Số bucket có thể tăng theo tích số ở từng tầng. Với ví dụ trên, số bucket con tối đa có thể lên tới hàng nghìn, chưa tính các bucket ở tầng cha và các nhánh aggregation khác.

Elasticsearch có giới hạn search.max_buckets để ngăn một request tạo quá nhiều bucket. Giá trị mặc định trong các phiên bản hiện đại là 65.536 bucket cho một response; kiểm tra cấu hình và tài liệu phiên bản cụ thể của cluster.

Ví dụ aggregation lồng nhau:

~~~json
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 100
      },
      "aggs": {
        "brands": {
          "terms": {
            "field": "brand",
            "size": 100
          },
          "aggs": {
            "availability": {
              "terms": {
                "field": "availability",
                "size": 10
              }
            }
          }
        }
      }
    }
  }
}
~~~

Nếu mỗi category có 100 brand và mỗi brand có 10 availability bucket, cây bucket có thể tăng rất nhanh. Giới hạn max_buckets áp dụng cho tổng bucket trong kết quả, không chỉ bucket ở tầng ngoài cùng.

Khi vượt giới hạn, Elasticsearch có thể trả lỗi too_many_buckets_exception. Không nên xử lý bằng cách tăng max_buckets ngay lập tức. Trước hết hãy xem lại số bucket cần thiết, kích thước từng tầng và liệu có thể phân trang hoặc tách request.

### 7.1. Ước tính bucket count

Với cấu trúc lồng nhau có size cố định, có thể ước tính số bucket tối đa gần đúng bằng cách nhân số bucket ở các tầng:

~~~text
outer buckets = 100
middle buckets per outer = 100
inner buckets per middle = 10

approximate bucket count
  = 100 + (100 * 100) + (100 * 100 * 10)
  = 110,100
~~~

Đây là ước tính worst-case đơn giản. Số thực tế có thể thấp hơn nếu ít bucket tồn tại hoặc các ngưỡng min_doc_count loại bớt bucket, nhưng thiết kế không nên dựa vào việc dữ liệu hiện tại tình cờ thưa.

## 8. Bucket explosion và chi phí tài nguyên

Bucket explosion xảy ra khi một request tạo quá nhiều bucket hoặc quá nhiều sub-aggregation trên các bucket. Nó có thể làm tăng:

- **Heap và bộ nhớ tạm:** Elasticsearch phải theo dõi bucket, count, metric và cấu trúc thu thập.
- **CPU:** mỗi document cần được kiểm tra và đưa vào các aggregation phù hợp.
- **Network traffic:** các shard gửi bucket ứng viên và dữ liệu aggregation về coordinating node.
- **Garbage collection:** nhiều object tạm có thể làm tăng allocation và GC pressure.
- **Response size:** nhiều bucket và metric làm JSON trả về lớn.
- **Latency:** nhiều tầng aggregation và cardinality cao có thể kéo dài thời gian xử lý.

Các nguyên nhân thường gặp:

- Đặt terms size quá lớn.
- Tạo nhiều terms aggregation lồng nhau.
- Dùng field cardinality rất cao như user ID, session ID hoặc email.
- Gắn nhiều sub-aggregation đắt tiền vào từng bucket.
- Trả quá nhiều top_hits trong mỗi bucket.
- Chạy đồng thời nhiều dashboard query có cấu trúc tương tự.
- Dùng aggregation trên field text với fielddata gây áp lực heap.

## 9. Cardinality của field và chọn loại aggregation

Cardinality là số giá trị khác nhau của một field. Nó quyết định mức độ lớn tiềm năng của terms aggregation.

| Loại field | Ví dụ | Cardinality thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| Trạng thái | ACTIVE, DRAFT, ARCHIVED | Thấp | Terms aggregation nhỏ hoặc filters aggregation. |
| Category | ACCESSORIES, OFFICE, HOME | Thấp đến trung bình | Terms aggregation với size phù hợp. |
| Brand | Tên thương hiệu | Trung bình | Terms aggregation top N; composite nếu cần duyệt hết. |
| User ID | Mã người dùng | Cao | Tránh tạo mọi bucket trong một request; cân nhắc composite hoặc cardinality metric. |
| Session ID | Mã phiên | Rất cao | Thường không phù hợp để tạo bucket đầy đủ trong dashboard. |

Không phải lúc nào cũng cần terms aggregation để trả tất cả giá trị. Hãy chọn API theo mục đích:

- terms: lấy top N giá trị phổ biến.
- filters: nhóm theo tập điều kiện đã biết trước.
- composite: duyệt các bucket theo từng trang khi cần nhiều hoặc toàn bộ tổ hợp giá trị.
- cardinality: ước tính số giá trị khác nhau mà không tạo một bucket cho từng giá trị.
- rare_terms: tìm những term hiếm thay vì sort terms theo count tăng dần.

### 9.1. Filters aggregation cho nhóm cố định

Nếu giao diện chỉ cần các nhóm đã biết, ví dụ trạng thái đơn hàng, filters aggregation thường rõ ràng hơn terms:

~~~json
{
  "aggs": {
    "order_status": {
      "filters": {
        "filters": {
          "active": { "term": { "status": "ACTIVE" } },
          "pending": { "term": { "status": "PENDING" } },
          "archived": { "term": { "status": "ARCHIVED" } }
        }
      }
    }
  }
}
~~~

Cách này tạo đúng các bucket đã khai báo và không cần khám phá mọi giá trị khác nhau của field. Nó phù hợp với enum hoặc nhóm nghiệp vụ cố định.

## 10. Composite aggregation để duyệt nhiều bucket

Terms aggregation được thiết kế chủ yếu để lấy top bucket. Nếu cần duyệt toàn bộ giá trị khác nhau hoặc tổ hợp nhiều field, tăng terms size lên một con số rất lớn không phải giải pháp phù hợp.

Composite aggregation hỗ trợ phân trang bucket bằng after_key.

Ví dụ nhóm theo category và brand:

~~~json
{
  "size": 0,
  "aggs": {
    "catalog": {
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

Response trả các bucket của trang hiện tại và có thể có after_key. Gửi after trong request kế tiếp để lấy trang bucket tiếp theo:

~~~json
{
  "size": 0,
  "aggs": {
    "catalog": {
      "composite": {
        "size": 100,
        "after": {
          "category": "ACCESSORIES",
          "brand": "ACME"
        },
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

Trong ứng dụng, nên dùng chính after_key được Elasticsearch trả về làm cursor cho request kế tiếp; không tự suy ra cursor từ bucket cuối cùng nếu response đã cung cấp after_key.

Composite aggregation giúp duyệt bucket theo từng trang và giữ kích thước response có giới hạn. Nó không làm cho việc quét toàn bộ cardinality trở nên miễn phí: mỗi trang vẫn tiêu tốn tài nguyên và cần nhiều request. Nếu dữ liệu thay đổi trong khi duyệt và cần góc nhìn nhất quán, hãy cân nhắc Point in Time (PIT) nếu phiên bản và API sử dụng hỗ trợ kết hợp phù hợp.

## 11. Pipeline aggregation không thay thế giới hạn bucket

Pipeline aggregation như bucket_sort hoặc bucket_selector xử lý bucket đã được tạo bởi aggregation cha.

Ví dụ:

~~~json
{
  "aggs": {
    "brands": {
      "terms": {
        "field": "brand",
        "size": 100
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "revenue"
          }
        },
        "top_revenue": {
          "bucket_sort": {
            "sort": [
              { "revenue": { "order": "desc" } }
            ],
            "size": 10
          }
        }
      }
    }
  }
}
~~~

bucket_sort có thể sắp xếp và cắt danh sách bucket đã được aggregation cha tạo. Nó không ngăn terms aggregation cha thu thập bucket ứng viên ban đầu. Vì vậy, đặt bucket_sort.size bằng 10 không có nghĩa chi phí của terms aggregation chỉ tương đương 10 bucket.

Tương tự, bucket_selector loại bucket sau khi các metric liên quan đã được tính. Nó hữu ích cho logic hậu xử lý nhưng không phải cơ chế thay thế terms.size, shard_size hoặc composite pagination.

## 12. Sub-aggregation làm tăng chi phí như thế nào?

Mỗi bucket có thể chứa metric hoặc bucket aggregation con. Khi số bucket cha tăng, sub-aggregation được tính trên từng bucket tương ứng.

Ví dụ:

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
        },
        "brands": {
          "terms": {
            "field": "brand",
            "size": 10
          }
        }
      }
    }
  }
}
~~~

Nếu có 20 category và mỗi category tối đa 10 brand, aggregation có thể trả tới 200 bucket brand cộng với bucket category, cùng metric average price. Tăng size ở cả hai tầng làm cây bucket tăng theo cấp số nhân theo cấu trúc lồng nhau.

Khi thiết kế:

- Chỉ thêm sub-aggregation mà giao diện thực sự hiển thị.
- Giữ size nhỏ ở các tầng sâu.
- Tránh lồng terms theo field cardinality cao.
- Tách dashboard thành các request độc lập nếu một request tạo cây quá lớn và không cần cùng một snapshot.
- Cân nhắc composite aggregation khi cần duyệt tổ hợp bucket.

## 13. collect_mode: depth_first và breadth_first

Terms aggregation có thể dùng các cách thu thập sub-aggregation:

- depth_first: thu thập sub-aggregation khi document được thu vào bucket cha.
- breadth_first: trì hoãn việc thu thập sub-aggregation cho đến khi các bucket cha hàng đầu đã được chọn.

Ví dụ:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20,
        "collect_mode": "breadth_first"
      },
      "aggs": {
        "brands": {
          "terms": {
            "field": "brand",
            "size": 10
          }
        }
      }
    }
  }
}
~~~

breadth_first có thể hữu ích khi parent terms có cardinality cao và sub-aggregation đắt tiền, vì nó trì hoãn xử lý sub-aggregation cho những bucket cha không nằm trong top được giữ lại. Tuy nhiên, nó có thể cần lưu trạng thái document để replay cho các bucket được chọn, nên không phải lúc nào cũng ít bộ nhớ hơn.

Mặc định thường là depth_first. Chỉ thay đổi collect_mode khi đã đo trên dữ liệu đại diện và hiểu trade-off giữa chi phí sub-aggregation với bộ nhớ cần cho việc trì hoãn/replay.

## 14. execution_hint và global ordinals

Terms aggregation trên field keyword thường sử dụng global ordinals để nhóm term hiệu quả. Global ordinals là cấu trúc ánh xạ các term trên segment thành ordinal toàn cục cho shard.

Một số trường hợp có thể dùng execution_hint để yêu cầu cách thực thi khác, ví dụ map:

~~~json
{
  "aggs": {
    "brands": {
      "terms": {
        "field": "brand",
        "size": 20,
        "execution_hint": "map"
      }
    }
  }
}
~~~

map có thể phù hợp trong một số truy vấn chọn lọc trên tập document nhỏ, nhưng thường không phải lựa chọn mặc định cho aggregation trên tập lớn. Global ordinals có thể cần chi phí xây dựng/cập nhật, đặc biệt sau refresh; eager global ordinals là một tùy chọn mapping để chuyển một phần chi phí sang refresh thay vì lần truy vấn đầu tiên.

Không đặt execution_hint chỉ dựa trên suy đoán. Hãy profile và benchmark với cardinality, refresh pattern, query selectivity và số shard thực tế. Giá trị hint và hành vi có thể thay đổi theo phiên bản Elasticsearch và field type.

## 15. Spring Data Elasticsearch: khai báo size và shard_size

Với Spring Data Elasticsearch dùng Elasticsearch Java API Client, NativeQuery có thể mang aggregation builder. Ví dụ:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Aggregation brandsAggregation = Aggregation.of(a -> a
        .terms(t -> t
                .field("brand")
                .size(20)
                .shardSize(60)));

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.matchAll(m -> m))
        .withAggregation("top_brands", brandsAggregation)
        .build();
~~~

Trong ví dụ:

- size(20) yêu cầu tối đa 20 bucket cuối.
- shardSize(60) yêu cầu mỗi shard gửi tối đa 60 bucket ứng viên.
- Tên top_brands là key của aggregation trong response.

Nếu không cần hit, có thể thiết lập page size bằng 0 theo API tương ứng của phiên bản Spring Data, hoặc dùng query builder phù hợp để chỉ lấy aggregation. Hãy kiểm tra request được sinh ra vì cách cấu hình hit window và aggregation phụ thuộc API phiên bản.

### 15.1. Đặt min_doc_count và show_term_doc_count_error

Có thể thêm các tùy chọn khác trên terms builder:

~~~java
Aggregation brandsAggregation = Aggregation.of(a -> a
        .terms(t -> t
                .field("brand")
                .size(20)
                .shardSize(60)
                .minDocCount(5)
                .showTermDocCountError(true)));
~~~

Các method builder được sinh từ Elasticsearch Java API Client. Tên và kiểu tham số cần tương thích với phiên bản client được Spring Data Elasticsearch quản lý trong dự án.

### 15.2. Đọc kết quả aggregation

ElasticsearchOperations.search(...) trả SearchHits<T>, trong đó aggregation metadata được cung cấp qua container aggregation của Spring Data. Cách lấy từng bucket phụ thuộc phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client.

Khi đọc response, cần phân biệt:

- Bucket key.
- doc_count.
- doc_count_error_upper_bound.
- sum_other_doc_count.
- Metric hoặc sub-aggregation bên trong mỗi bucket.

Không lấy số lượng hit của search request để thay thế doc_count trong bucket. Hits và aggregation có thể dùng các phạm vi hoặc cách tính khác nhau.

## 16. Ví dụ thiết kế aggregation cho dashboard

Giả sử dashboard cần top 10 category và giá trung bình của mỗi category. Có thể dùng:

~~~json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } }
      ]
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 10,
        "shard_size": 30,
        "show_term_doc_count_error": true
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

Thiết kế này:

- Giới hạn dữ liệu theo tenant và trạng thái trước khi aggregation.
- Trả tối đa 10 category.
- Thu thập tối đa 30 ứng viên mỗi shard để giảm rủi ro bỏ sót bucket top.
- Tính giá trung bình trên document trong từng category bucket.
- Trả thông tin sai số để ứng dụng có thể đánh giá độ chính xác count.

Nếu category có cardinality thấp và cố định, có thể tăng size đủ chứa tất cả category. Nếu category có cardinality cao, chỉ lấy top N hoặc dùng composite để duyệt từng trang.

## 17. Cách chẩn đoán aggregation tốn tài nguyên

Khi aggregation chậm hoặc lỗi, hãy kiểm tra theo thứ tự:

1. **Số shard:** request chạy trên bao nhiêu shard? Có shard quá lớn hoặc mất cân bằng không?
2. **Cardinality:** field dùng terms có bao nhiêu giá trị khác nhau?
3. **size và shard_size:** có đang lấy quá nhiều bucket hoặc quá nhiều ứng viên mỗi shard không?
4. **Cây aggregation:** có nhiều tầng terms và sub-aggregation không?
5. **Metric đắt tiền:** có top_hits, scripted metric, pipeline hoặc nested aggregation không?
6. **Field mapping:** field có doc values không? Có đang bật fielddata trên text không?
7. **Concurrency:** có nhiều dashboard hoặc người dùng chạy aggregation lớn cùng lúc không?
8. **Bucket limit:** có chạm search.max_buckets không?
9. **Response size:** client có thực sự cần tất cả bucket và metric trả về không?
10. **Profile:** query profile hoặc benchmark có chỉ ra tầng aggregation gây tốn thời gian không?

Elasticsearch Profile API có thể giúp phân tích thời gian từng phần query/aggregation nhưng có overhead. Chỉ bật trong môi trường điều tra hoặc request thử nghiệm, không bật thường trực cho mọi request production.

Có thể quan sát các chỉ số cluster như heap pressure, search thread pool, request breaker, GC và search latency. Nếu request bị từ chối do circuit breaker, tăng giới hạn bộ nhớ không nên là bước xử lý đầu tiên; hãy giảm bucket, shard_size, sub-aggregation hoặc concurrency trước.

## 18. Các giới hạn và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đặt terms size cực lớn để lấy mọi giá trị | Nhiều bucket, response lớn và có thể vượt max_buckets. | Dùng composite aggregation để phân trang. |
| Tăng shard_size rất cao mà không đo | Tăng dữ liệu trung gian, network và bộ nhớ coordinator. | Chỉ tăng khi cần cải thiện top terms/count accuracy. |
| Lồng nhiều terms aggregation có size lớn | Bucket count tăng theo tích các tầng. | Giảm size tầng sâu, bỏ sub-aggregation không cần thiết. |
| Aggregation theo user/session ID cho dashboard | Cardinality cao và số bucket lớn. | Dùng cardinality metric, composite pagination hoặc mô hình dữ liệu tổng hợp. |
| Dùng terms theo count tăng dần để tìm term hiếm | Kết quả có thể không chính xác trên nhiều shard. | Dùng rare_terms aggregation. |
| Cho rằng bucket_sort giảm chi phí aggregation cha | Bucket cha vẫn được thu thập trước pipeline. | Giảm size ở aggregation cha hoặc dùng cách phân trang phù hợp. |
| Bật fielddata trên text để terms aggregation | Có thể tăng mạnh heap usage. | Tạo subfield keyword và aggregate trên field đó. |
| Tăng search.max_buckets để bỏ qua lỗi | Có thể làm request tiêu thụ nhiều bộ nhớ hơn. | Tối ưu cây aggregation và phân trang trước. |
| Dùng shard_min_doc_count cao | Term có count toàn cục đủ lớn có thể bị loại ở từng shard. | Giữ ngưỡng thấp hoặc dùng mặc định nếu không có lý do rõ ràng. |
| Chạy nhiều request aggregation nặng đồng thời | Cạnh tranh CPU, heap và request breaker. | Giới hạn concurrency, cache kết quả phù hợp và phân tách dashboard workload. |

## 19. Quy trình chọn size và shard_size

Khi xây dựng terms aggregation, hãy đi theo trình tự:

1. Xác định giao diện cần top N hay cần duyệt toàn bộ bucket.
2. Kiểm tra cardinality của field và mapping có hỗ trợ aggregation qua doc values không.
3. Chọn size theo số bucket thực sự cần hiển thị.
4. Giữ shard_size mặc định trước; chỉ tăng khi cần cải thiện độ chính xác hoặc thứ hạng.
5. Kiểm tra doc_count_error_upper_bound và sum_other_doc_count nếu count quan trọng.
6. Dùng min_doc_count để bỏ bucket quá nhỏ khi phù hợp; tránh shard_min_doc_count cao.
7. Ước tính tổng bucket khi có sub-aggregation và đối chiếu search.max_buckets.
8. Dùng filters cho nhóm cố định, composite để duyệt nhiều bucket, cardinality để ước tính số giá trị khác nhau và rare_terms để tìm term hiếm.
9. Chỉ dùng collect_mode hoặc execution_hint sau khi profile.
10. Kiểm thử trên số shard, cardinality và concurrency gần với production.

## 20. Tài liệu tham khảo

- [Elasticsearch — Terms aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-terms-aggregation.html)
- [Elasticsearch — Composite aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-composite-aggregation.html)
- [Elasticsearch — Bucket aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket.html)
- [Elasticsearch — Search settings: max buckets](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-settings.html)
- [Elasticsearch — Cardinality aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-metrics-cardinality-aggregation.html)
- [Elasticsearch — Rare terms aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-rare-terms-aggregation.html)
- [Spring Data Elasticsearch — NativeQuery and aggregations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

size giới hạn số bucket cuối cùng được trả về; shard_size giới hạn số bucket ứng viên mỗi shard gửi lên coordinator. Tăng hai giá trị có tác động khác nhau tới độ đầy đủ, độ chính xác và tài nguyên. Với field cardinality cao hoặc cần duyệt toàn bộ bucket, dùng composite pagination thay vì đặt size rất lớn. Luôn tính cả bucket lồng nhau, sub-aggregation và concurrency khi đánh giá chi phí.

