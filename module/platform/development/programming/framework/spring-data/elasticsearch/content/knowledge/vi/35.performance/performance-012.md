# Đo hiệu năng trên dữ liệu và truy vấn gần với thực tế

Đo hiệu năng Elasticsearch trên vài trăm document mẫu thường cho kết quả rất khác với hệ thống thật. Khi dữ liệu tăng lên, phân phối giá trị thay đổi, shard nhận tải không đều, cache hoạt động khác, aggregation tạo nhiều bucket hơn và các truy vấn cạnh tranh tài nguyên với thao tác ghi. Một query chạy nhanh trên laptop hoặc môi trường test nhỏ chưa chứng minh rằng hệ thống sẽ đáp ứng được khi có hàng trăm người dùng, hàng triệu document và luồng cập nhật liên tục.

Muốn đánh giá đúng, cần xây dựng benchmark gần với workload production: dữ liệu có kích thước và phân phối tương tự, mapping tương ứng, tỷ lệ đọc/ghi hợp lý, truy vấn đại diện, concurrency thực tế và môi trường có cấu hình tương đương. Đo cả Elasticsearch lẫn ứng dụng Spring Data để biết độ trễ nằm ở query, network, serialization, mapping entity hay xử lý downstream.

Một benchmark hữu ích phải trả lời được các câu hỏi cụ thể:

- Hệ thống xử lý được bao nhiêu request hoặc document mỗi giây?
- Latency p50, p95 và p99 là bao nhiêu ở tải dự kiến?
- Khi tăng concurrency, throughput tăng đến đâu và bắt đầu bão hòa ở đâu?
- Query nào tạo tail latency cao hoặc tiêu thụ nhiều CPU/memory?
- Tỷ lệ lỗi, timeout, 429 và queue backlog thay đổi thế nào?
- Search có còn đáp ứng khi bulk indexing chạy đồng thời không?
- Kết quả có lặp lại được sau khi thay đổi mapping, shard, query hoặc code không?

## 1. Vì sao cần dữ liệu gần với production?

Một index nhỏ thường nằm gọn trong filesystem cache, có ít segment, ít shard và ít giá trị phân biệt. Những điều kiện đó làm query có vẻ nhanh hơn đáng kể so với môi trường thật.

Ví dụ, một query terms aggregation trên field category có thể chỉ tạo 8 bucket trong bộ dữ liệu mẫu. Trong production, field đó có thể có hàng trăm nghìn giá trị khác nhau. Tương tự, một query filter theo tenant có thể trả về 5 document trong test nhưng hàng triệu document trong tenant lớn nhất.

Các khác biệt thường làm benchmark sai lệch:

- **Số lượng document:** tập nhỏ không phản ánh chi phí tìm kiếm, segment và merge ở quy mô lớn.
- **Phân phối dữ liệu:** giá trị đồng đều trong test nhưng lệch mạnh ở production.
- **Cardinality:** field có ít giá trị trong test nhưng có nhiều giá trị duy nhất trong thực tế.
- **Kích thước document:** payload mẫu nhỏ hơn dữ liệu thật hoặc thiếu nested arrays.
- **Tỷ lệ dữ liệu mới/cũ:** production có nhiều update, delete và document hết hạn.
- **Shard distribution:** một số tenant hoặc routing key tạo hotspot.
- **Query mix:** test chỉ chạy một match query, trong khi production có filter, sort, aggregation, nested query và pagination.
- **Concurrency:** một request đơn lẻ không thể hiện tranh chấp CPU, disk, thread pool và connection pool.
- **Cache:** benchmark chạy lặp một query có thể chỉ đo cache hit.
- **Refresh và merge:** dữ liệu được ghi liên tục tạo workload khác với index tĩnh.

Benchmark tốt không nhất thiết phải sao chép toàn bộ dữ liệu production. Điều cần thiết là giữ được những đặc tính ảnh hưởng đến chi phí xử lý: phân phối, cardinality, kích thước, độ lệch, tỷ lệ thay đổi và mẫu truy vấn.

## 2. Xác định mục tiêu và SLO trước khi đo

Trước khi tạo dữ liệu hoặc viết script, hãy xác định kết quả nào được xem là đạt yêu cầu. Nếu không có mục tiêu, benchmark chỉ tạo ra nhiều con số mà không giúp đưa ra quyết định.

Ví dụ mục tiêu cho một search API:

| Chỉ số | Mục tiêu minh họa |
|---|---:|
| Throughput | 300 request/giây |
| Search latency p50 | Dưới 80 ms |
| Search latency p95 | Dưới 250 ms |
| Search latency p99 | Dưới 600 ms |
| Error rate | Dưới 0,1% |
| Indexing lag | Dưới 5 giây |
| 429/rejected execution | Không tăng liên tục ở tải mục tiêu |

Đây chỉ là ví dụ. SLO thực tế phải dựa trên yêu cầu sản phẩm, vùng triển khai, network, kích thước response và ngân sách hạ tầng.

Nên tách mục tiêu theo loại workload:

- Search tương tác cần latency thấp.
- Aggregation dashboard có thể chấp nhận latency cao hơn.
- Bulk import ưu tiên throughput và thời gian hoàn thành.
- Update theo event cần giới hạn indexing lag.
- Export lớn ưu tiên khả năng xử lý ổn định và backpressure.

Không gộp mọi request thành một con số latency trung bình. Trung bình có thể che giấu một nhóm query rất chậm hoặc một tail latency không đáp ứng được trải nghiệm người dùng.

## 3. Tạo bộ dữ liệu đại diện

Dataset benchmark cần phản ánh cấu trúc và phân phối dữ liệu thực tế. Có thể dùng dữ liệu đã ẩn danh, dữ liệu tổng hợp hoặc kết hợp cả hai.

Ví dụ một document sản phẩm:

    {
      "productId": "p-100001",
      "tenantId": "tenant-42",
      "name": "Mechanical Keyboard K8",
      "description": "Wireless mechanical keyboard",
      "category": "keyboard",
      "brand": "Keychron",
      "price": 120.0,
      "stock": 42,
      "status": "ACTIVE",
      "createdAt": "2026-10-20T10:00:00Z",
      "updatedAt": "2026-11-10T08:30:00Z",
      "tags": ["wireless", "mechanical"],
      "offers": [
        {
          "sellerId": "seller-10",
          "price": 120.0,
          "available": true
        }
      ]
    }

Dataset không nên chỉ có các field đơn giản. Nếu production sử dụng nested object, arrays, text analyzer, date range, geo fields hoặc dynamic attributes, benchmark cũng cần có những cấu trúc đó.

### Số lượng document

Chọn quy mô đủ lớn để thể hiện đặc tính vận hành:

- Số document dự kiến ở thời điểm hiện tại.
- Số document dự kiến sau 6 hoặc 12 tháng.
- Kịch bản tăng trưởng nhanh.
- Kích thước index sau khi ingest và sau merge.

Có thể chạy nhiều mức quy mô, ví dụ 1 triệu, 10 triệu và 50 triệu document, nếu hạ tầng cho phép. Mục tiêu là hiểu đường tăng trưởng, không chỉ đo một điểm.

### Kích thước document

Đo kích thước trung bình và phân vị của document thực tế. Không chỉ tạo mọi document có cùng kích thước.

Một tập dữ liệu tốt có thể chứa:

- Document nhỏ chỉ có vài field.
- Document trung bình có description và metadata.
- Document lớn có arrays hoặc nested objects.
- Một tỷ lệ nhỏ document bất thường lớn nhưng vẫn hợp lệ.

Kích thước source ảnh hưởng đến network, storage, heap khi mapping và thời gian serialization.

## 4. Phân phối dữ liệu quan trọng hơn dữ liệu ngẫu nhiên đồng đều

Tạo dữ liệu ngẫu nhiên đồng đều thường làm benchmark quá lạc quan. Production thường có phân phối lệch:

- Một vài category có phần lớn sản phẩm.
- Một số tenant có dữ liệu lớn hơn nhiều tenant khác.
- Một vài keyword được tìm kiếm thường xuyên.
- Nhiều document có status giống nhau.
- Một số giá trị hiếm xuất hiện trong filter.
- Dữ liệu thời gian tập trung ở vài ngày gần nhất.

Ví dụ phân phối tenant:

| Nhóm tenant | Tỷ lệ tenant | Tỷ lệ document |
|---|---:|---:|
| Nhỏ | 80% | 20% |
| Trung bình | 15% | 30% |
| Lớn | 4% | 25% |
| Rất lớn | 1% | 25% |

Phân phối này tạo ra một số tenant có lượng dữ liệu lớn hơn hẳn. Nếu benchmark chỉ tạo tenant có kích thước bằng nhau, nó sẽ bỏ qua nguy cơ hotspot và tail latency của tenant lớn.

Hãy tạo dữ liệu theo histogram hoặc phân phối lấy từ số liệu production đã ẩn danh. Nếu không thể lấy dữ liệu thật, hãy mô hình hóa độ lệch dựa trên nghiệp vụ và ghi rõ giả định.

## 5. Cardinality của field

Cardinality là số lượng giá trị phân biệt của một field. Nó ảnh hưởng đến terms aggregation, memory, doc values, sorting và khả năng nén.

Ví dụ:

| Field | Cardinality thường gặp |
|---|---|
| status | Rất thấp |
| category | Thấp đến trung bình |
| brand | Trung bình |
| tenantId | Có thể cao |
| productId | Gần bằng số document |
| email | Rất cao |
| timestamp chính xác | Có thể rất cao |

Nếu benchmark aggregation theo tenantId nhưng chỉ tạo 10 tenant, kết quả không phản ánh chi phí khi có 100.000 tenant.

Tạo dữ liệu có cardinality gần production cho mọi field được dùng trong:

- terms aggregation.
- cardinality aggregation.
- sort.
- terms query.
- composite aggregation.
- group-by hoặc dashboard.

Đặc biệt, aggregation trên field high-cardinality có thể tạo nhiều bucket và tiêu tốn bộ nhớ. Hãy đo response size, bucket count và latency cùng lúc.

## 6. Phân phối thời gian và dữ liệu mới

Với hệ thống lưu event, đơn hàng hoặc lịch sử, phân phối timestamp ảnh hưởng đến query range và index lifecycle.

Một benchmark gần production cần mô phỏng:

- Document tập trung trong vài giờ hoặc vài ngày gần đây.
- Lượng dữ liệu lịch sử lớn.
- Một số tenant có hoạt động theo mùa hoặc theo giờ.
- Event đến trễ.
- Update document cũ.
- Delete hoặc retention cleanup.

Nếu mọi document được tạo cùng một timestamp, query range theo tuần/tháng sẽ không phản ánh dữ liệu thật. Nếu mọi document có timestamp phân bố đều, benchmark có thể bỏ qua hotspot ở thời gian hiện tại.

Với date histogram, tạo cả khoảng thời gian có dữ liệu dày và khoảng thời gian ít dữ liệu hoặc rỗng. Điều này giúp kiểm tra bucket trống, extended bounds và pipeline aggregation.

## 7. Giữ mapping giống môi trường thật

Benchmark với dynamic mapping đơn giản rồi chuyển sang mapping production có analyzer, nested, doc values và normalizer sẽ cho kết quả không thể so sánh trực tiếp.

Mapping cần giữ các yếu tố:

- Field type chính xác.
- Text analyzer và keyword subfield.
- Normalizer.
- Nested/object distinction.
- Index và doc_values settings.
- Dynamic templates.
- Similarity nếu đã tùy chỉnh.
- Runtime fields nếu workload sử dụng.
- Source settings và stored fields.

Ví dụ:

    PUT products
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
          "tenantId": {
            "type": "keyword"
          },
          "price": {
            "type": "scaled_float",
            "scaling_factor": 100
          },
          "createdAt": {
            "type": "date"
          },
          "offers": {
            "type": "nested",
            "properties": {
              "sellerId": {
                "type": "keyword"
              },
              "price": {
                "type": "double"
              },
              "available": {
                "type": "boolean"
              }
            }
          }
        }
      }
    }

Mapping này chỉ là ví dụ. Benchmark phải dùng mapping thực tế hoặc một biến thể được ghi rõ mục đích. Không thay đổi field type giữa hai lần đo rồi quy kết khác biệt cho query.

## 8. Tạo dữ liệu có thể tái lập

Dataset nên được tạo theo seed cố định hoặc lấy từ snapshot có version. Nếu mỗi lần chạy tạo dữ liệu khác nhau, kết quả benchmark có thể dao động vì phân phối dữ liệu thay đổi.

Nên lưu lại:

- Seed của bộ sinh dữ liệu.
- Phiên bản generator.
- Số lượng document.
- Phân phối tenant/category/status.
- Kích thước source.
- Mapping và settings.
- Phiên bản Elasticsearch.
- Phiên bản Spring Data Elasticsearch và Java API Client.
- Ngày tạo snapshot.

Nếu dữ liệu có nguồn từ production, phải ẩn danh và loại bỏ thông tin cá nhân hoặc bí mật trước khi dùng trong môi trường benchmark.

Không dùng ID hoặc payload nhạy cảm thật trong script benchmark, log hoặc báo cáo.

### Kiểm tra dataset trước khi đo

Trước benchmark, xác nhận:

- Số document đúng dự kiến.
- Số lượng unique tenant/category/brand hợp lý.
- Phân phối field gần với mô hình.
- Kích thước document có đủ đa dạng.
- Mapping đúng.
- Không có lỗi bulk bị bỏ qua.
- Index đã refresh khi bài đo cần search visibility.

Có thể dùng count query, cardinality aggregation và thống kê mẫu để xác nhận. Không bắt đầu benchmark khi chưa biết dataset đã được ingest đầy đủ hay chưa.

## 9. Tái tạo workload truy vấn

Workload cần phản ánh tỷ lệ truy vấn thực tế thay vì chỉ chạy một query. Một search application có thể có:

| Loại request | Tỷ lệ ví dụ |
|---|---:|
| Match/full-text search | 35% |
| Filter theo tenant/status/category | 25% |
| Sort và pagination | 15% |
| Aggregation dashboard | 10% |
| Nested query | 5% |
| Get theo ID | 5% |
| Bulk/index/update | 5% |

Các tỷ lệ chỉ mang tính minh họa. Hãy dùng access log, APM hoặc số liệu API đã ẩn danh để xác định query mix thực tế.

Một workload gần production cần mô phỏng:

- Query thường xuyên.
- Query hiếm nhưng nặng.
- Query với kết quả rỗng.
- Query trả rất nhiều hit.
- Query theo tenant nhỏ và tenant lớn.
- Query có filter chọn lọc cao và chọn lọc thấp.
- Aggregation có cardinality thấp và cao.
- Pagination trang đầu và trang sâu.
- Read trong lúc write đang diễn ra.

Không chỉ benchmark query trung bình. Những query hiếm nhưng chiếm nhiều CPU hoặc tạo tail latency có thể là nguyên nhân chính khiến SLO bị vi phạm.

## 10. Dùng tham số truy vấn giống production

Một query template có thể chạy nhanh với một giá trị nhưng chậm với giá trị khác. Ví dụ filter status=ACTIVE có thể khớp 90% document, trong khi status=ARCHIVED chỉ khớp 1%.

Hãy tạo tập tham số đại diện:

- Giá trị phổ biến.
- Giá trị hiếm.
- Tenant lớn nhất.
- Tenant nhỏ.
- Khoảng thời gian ngắn.
- Khoảng thời gian dài.
- Keyword ngắn và dài.
- Keyword phổ biến và hiếm.
- Trường hợp query không có kết quả.

Nếu dùng cùng một keyword cho hàng nghìn request, cache có thể làm benchmark thiên lệch về cache hit. Nếu production có query phân tán, tập tham số benchmark cũng cần có mức đa dạng tương ứng.

## 11. Ví dụ query mix

### Full-text search

    GET products/_search
    {
      "query": {
        "match": {
          "name": "mechanical keyboard"
        }
      },
      "size": 20
    }

### Filter theo tenant và trạng thái

    GET products/_search
    {
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "tenantId": "tenant-42"
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
                  "gte": 50,
                  "lte": 300
                }
              }
            }
          ]
        }
      },
      "sort": [
        {
          "createdAt": {
            "order": "desc"
          }
        }
      ],
      "size": 20
    }

### Aggregation theo category

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "by_category": {
          "terms": {
            "field": "category",
            "size": 100
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

### Nested query

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "offers",
          "query": {
            "bool": {
              "filter": [
                {
                  "term": {
                    "offers.available": true
                  }
                },
                {
                  "range": {
                    "offers.price": {
                      "lt": 100
                    }
                  }
                }
              ]
            }
          }
        }
      }
    }

Query mix cần giữ cả cấu trúc và tần suất. Một query nặng chỉ chiếm 1% traffic nhưng có thể chiếm phần lớn CPU nếu nó tạo nhiều bucket hoặc đọc nhiều document.

## 12. Mô phỏng thao tác ghi cùng search

Production thường không chỉ search trên index tĩnh. Nó có thể vừa nhận document mới, update trạng thái, xóa record cũ vừa phục vụ query.

Benchmark cần có các kịch bản:

- Search-only để đo giới hạn đọc.
- Index-only để đo ingest throughput.
- Search và index đồng thời.
- Update/delete đồng thời với search.
- Bulk import lớn trong khi API tương tác vẫn chạy.
- Refresh interval bình thường và kịch bản refresh bị trì hoãn.

Ghi đồng thời có thể tạo segment mới, merge, indexing pressure và cạnh tranh disk. Query latency ở chế độ search-only thường không phản ánh điều này.

Nếu production có bulk import ban đêm và traffic search ban ngày, benchmark riêng hai giai đoạn và cả trường hợp chúng chồng lấn khi có sự cố hoặc backfill.

## 13. Mô hình tải: closed-loop và open-loop

Hai cách tạo tải phổ biến có hành vi khác nhau:

- **Closed-loop:** mỗi virtual user gửi request tiếp theo sau khi request trước hoàn tất. Khi hệ thống chậm, tốc độ gửi request tự giảm.
- **Open-loop:** request được phát theo tốc độ định trước, độc lập với thời gian phản hồi. Nếu hệ thống chậm, hàng đợi và latency có thể tăng.

Closed-loop dễ dùng nhưng có thể che giấu overload vì client tự giảm tốc khi server chậm. Open-loop phù hợp để kiểm tra khả năng chịu một arrival rate cụ thể, nhưng cần giới hạn queue và tránh tạo tải vượt ngoài khả năng của generator.

Nên dùng mô hình gần với hành vi thực tế của client. Nếu production có request đến theo tốc độ ổn định, cần kiểm tra open-loop. Nếu ứng dụng có số worker cố định chờ phản hồi rồi mới gọi tiếp, closed-loop có thể phù hợp hơn.

## 14. Các kiểu bài đo cần thực hiện

Một kế hoạch benchmark không nên chỉ có một lần chạy 5 phút. Có thể chia thành các bài đo:

| Bài đo | Mục tiêu |
|---|---|
| Baseline | Đo hệ thống ở tải thấp để có mốc so sánh |
| Load test | Đo ở tải dự kiến trong thời gian đủ dài |
| Stress test | Tăng tải vượt mục tiêu để tìm điểm bão hòa |
| Spike test | Tăng tải đột ngột để xem khả năng hấp thụ burst |
| Soak test | Chạy lâu để phát hiện memory leak, merge backlog và degradation |
| Recovery test | Quan sát hệ thống sau overload hoặc node restart |
| Mixed workload | Đo đọc/ghi/aggregation cùng lúc |
| Scale test | So sánh khi thay đổi node, shard hoặc tài nguyên |

Mỗi bài đo cần ghi rõ mục tiêu, thời gian warm-up, thời gian đo, concurrency, request rate và tiêu chí dừng.

## 15. Warm-up và cold-cache test

Lần chạy đầu có thể chậm do:

- JVM vừa khởi động hoặc JIT chưa tối ưu.
- Filesystem cache chưa nóng.
- Query cache hoặc request cache chưa có dữ liệu.
- Connection pool mới tạo kết nối.
- Elasticsearch đang mở segment hoặc tải mapping.

Nếu chỉ đo lần chạy đầu, benchmark có thể đánh giá thấp hiệu năng steady-state. Nếu chỉ đo sau khi chạy cùng query hàng nghìn lần, benchmark có thể đánh giá quá cao hiệu năng với query đa dạng.

Nên tách:

- Cold-start measurement.
- Warm-up phase.
- Steady-state measurement.
- Cache-hit workload.
- Cache-miss hoặc query đa dạng workload.

Ghi rõ cache state của từng kết quả. Không so một lần cold-cache với một lần warm-cache rồi kết luận rằng code mới nhanh hơn.

## 16. Cache ảnh hưởng đến kết quả như thế nào?

Elasticsearch và hệ điều hành có nhiều lớp cache:

- Filesystem page cache.
- Node query cache.
- Shard request cache.
- Cache của ứng dụng hoặc reverse proxy nếu có.
- Connection pool và DNS/TLS session reuse.

Không phải mọi query đều được cache. Cache behavior phụ thuộc loại query, segment, request và index settings.

Nếu benchmark chạy lại cùng một aggregation request trên index tĩnh, shard request cache có thể làm lần chạy sau nhanh hơn. Nếu query thay đổi liên tục hoặc index đang được cập nhật, cache hit rate có thể thấp hơn.

Để đo workload thực tế:

- Dùng tập tham số query đa dạng như production.
- Ghi nhận cache hit/miss nếu metric tương ứng có sẵn.
- Không xóa cache tùy tiện giữa mọi request.
- Chạy cả warm và cold scenario.
- Giữ index state tương đương giữa các lần so sánh.

Không tắt toàn bộ cache chỉ để có một con số benchmark. Hãy đo cache behavior theo workload mà người dùng thực sự tạo ra.

## 17. Refresh và merge trong benchmark

Index tĩnh đã refresh và merge ổn định có thể cho kết quả khác index đang ingest liên tục.

Refresh tạo điều kiện để document searchable. Segment mới được tạo thường nhỏ hơn và có thể được merge về sau. Merge tiêu thụ CPU và I/O, ảnh hưởng đến search/indexing latency.

Vì vậy, cần benchmark:

- Search trên index tĩnh đã ổn định.
- Search trong khi index liên tục.
- Search trong lúc bulk import.
- Search trong lúc merge backlog tăng.
- Các refresh policy khác nhau nếu ứng dụng có lựa chọn.

Nếu benchmark chỉ index xong, refresh, force merge rồi mới search, kết quả có thể không phản ánh trạng thái production đang ghi liên tục.

Force merge có thể hữu ích cho index gần như chỉ đọc, nhưng không nên chạy trước mọi benchmark nếu production không có cùng quy trình. Nó thay đổi segment layout và cache behavior.

## 18. Đo latency đúng cách

Latency cần được đo ở nhiều lớp:

- Client bắt đầu gửi request đến khi nhận response.
- Spring service xử lý request.
- Elasticsearch client thực hiện network call.
- Elasticsearch server xử lý query.
- Mapping source thành entity.
- Mapping entity thành DTO.
- Serialize response HTTP.

Một timer quanh operations.search có thể đo nhiều phần hơn thời gian query server, vì nó có thể bao gồm network và conversion tùy API. Thời gian took trong Elasticsearch response không bao gồm toàn bộ latency mà người dùng trải nghiệm.

Nên thu thập ít nhất:

- p50: latency trung vị.
- p90 hoặc p95: latency của nhóm request chậm.
- p99: tail latency.
- Maximum: hữu ích để điều tra nhưng nhạy với outlier.
- Error rate và timeout rate.

Không chỉ báo cáo average. Một hệ thống có average 50 ms nhưng p99 5 giây vẫn có thể tạo trải nghiệm rất tệ cho một nhóm người dùng.

## 19. Throughput và latency phải được xem cùng nhau

Throughput là số thao tác hoàn thành trong một đơn vị thời gian. Tăng số worker có thể tăng throughput lúc đầu, nhưng sau một điểm hệ thống bão hòa:

- CPU đạt giới hạn.
- Disk queue tăng.
- Thread pool queue tăng.
- GC pause dài hơn.
- Request bị reject hoặc timeout.
- p95/p99 tăng nhanh.

Ví dụ:

| Concurrency | Throughput | p95 latency | Error rate |
|---:|---:|---:|---:|
| 10 | 120 req/s | 90 ms | 0% |
| 25 | 260 req/s | 140 ms | 0% |
| 50 | 340 req/s | 280 ms | 0,02% |
| 100 | 355 req/s | 900 ms | 1,2% |
| 150 | 350 req/s | 1.8 s | 4,5% |

Ví dụ cho thấy throughput gần như không tăng sau concurrency 50, trong khi latency và lỗi tăng mạnh. Tăng concurrency thêm không làm hệ thống nhanh hơn.

Mục tiêu không phải throughput tối đa bằng mọi giá. Cần tìm điểm vận hành đáp ứng SLO với headroom đủ cho burst và biến động.

## 20. Đo p95 và p99 đúng cách

Percentile cần được tính trên đủ số mẫu và trong một khoảng đo có ý nghĩa. Một benchmark vài chục request không đủ để kết luận p99.

Hãy:

- Thu thập đủ request trong mỗi scenario.
- Tách percentile theo loại query.
- Không gộp query nhẹ và query nặng thành một histogram duy nhất nếu mix có thể thay đổi.
- Ghi rõ thời gian window.
- Dùng histogram phù hợp để tổng hợp từ nhiều instance.
- Tránh tính percentile trung bình của các percentile riêng lẻ.

Nếu chạy nhiều generator, percentile tổng cần được tổng hợp từ histogram/bucket hoặc dữ liệu mẫu đúng cách. Không lấy p99 của từng máy rồi tính trung bình số học.

## 21. Đo lỗi và timeout

Latency thấp không có ý nghĩa nếu một phần request bị drop hoặc timeout. Thu thập:

- HTTP 4xx/5xx.
- Elasticsearch item errors trong Bulk response.
- 429 và rejected execution.
- Connection timeout.
- Socket timeout.
- Circuit breaker open.
- Retry count.
- Cancellation.
- Request generator dropped iterations.

Một số load testing tool có thể không tạo đủ request khi generator hết CPU hoặc connection. Nếu generator bị bão hòa, số throughput đo được không còn đại diện cho khả năng Elasticsearch.

Theo dõi CPU, memory và network của cả load generator lẫn cluster.

## 22. Đo tài nguyên Elasticsearch

Các chỉ số cluster cần theo dõi:

| Nhóm | Chỉ số ví dụ | Điều cần hiểu |
|---|---|---|
| CPU | Node CPU, process CPU | Query, merge, indexing có bão hòa không |
| Heap | Heap used, old generation | Áp lực bộ nhớ và GC |
| GC | Pause time, collection count | Tail latency có bị ảnh hưởng không |
| Disk | Read/write throughput, latency, queue | Storage có là bottleneck không |
| Network | Bytes, packets, retransmission | Data transfer hoặc network có nghẽn không |
| Thread pool | Active, queue, rejected | Request đang chờ hay bị từ chối |
| Indexing pressure | Coordinating/primary/replica bytes | Ingest có vượt khả năng xử lý không |
| Segment | Segment count, memory | Segment fragmentation và merge |
| Merge | Merge time, throttling | Merge có cạnh tranh tài nguyên không |
| Shard | Shard size, distribution | Có shard quá lớn hoặc lệch tải không |

Tên metric và endpoint cụ thể phụ thuộc Elasticsearch version. Có thể dùng Stack Monitoring, node stats, index stats, cat APIs hoặc hệ thống metrics đang triển khai.

## 23. Đo tài nguyên ở ứng dụng Spring

Benchmark chỉ đo Elasticsearch sẽ bỏ qua chi phí của ứng dụng:

- Query builder.
- JSON serialization.
- HTTP connection pool.
- TLS handshake nếu connection không được tái sử dụng.
- Mapping source thành entity.
- Mapping entity sang DTO.
- Validation và business logic.
- JSON serialization cho response.
- Thread scheduling hoặc reactive operator overhead.

Dùng Micrometer hoặc APM để đo:

- Số request search theo endpoint.
- Duration của operations.search.
- Bulk request duration.
- Error count theo loại.
- Connection pool active/pending.
- JVM heap, allocation và GC.
- CPU và thread utilization.
- Time spent in DTO mapping và serialization nếu cần.

Không gắn raw search text, email, tenant ID hoặc document ID vào metric tag có cardinality cao. Dùng tag có số lượng giá trị giới hạn như operation, query family, index alias và status class.

## 24. Instrumentation quanh ElasticsearchOperations

Có thể đo thời gian service-level bằng Micrometer:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;
        private final MeterRegistry registry;

        public ProductSearchService(
                ElasticsearchOperations operations,
                MeterRegistry registry) {
            this.operations = operations;
            this.registry = registry;
        }

        public SearchHits<Product> search(Query query) {
            return Timer.builder("product.search.duration")
                .tag("operation", "search")
                .register(registry)
                .record(() ->
                    operations.search(query, Product.class)
                );
        }
    }

Ví dụ đo thời gian đồng bộ quanh operations.search. Timer này đo thời gian mà service call tiêu thụ, không chỉ thời gian xử lý query bên server.

Với reactive API, không đo thời gian tạo Mono vì publisher thường lazy. Dùng Timer.Sample hoặc operator instrumentation để ghi nhận từ lúc subscription bắt đầu đến khi complete/error:

    Mono<SearchHits<Product>> result =
        reactiveOperations.search(query, Product.class)
            .name("product.search")
            .metrics();

Tên metric, registry integration và cách instrument Reactor phụ thuộc dependency. Nếu dùng Micrometer Observation hoặc tracing instrumentation, ưu tiên cơ chế đã được cấu hình thống nhất trong ứng dụng.

Không gọi block chỉ để dùng Timer.record trong reactive flow.

## 25. Đo query server-side và application-side riêng

Một request có thể có:

    Application latency: 180 ms
    Elasticsearch took: 45 ms

Khoảng chênh lệch có thể đến từ network, queue, connection acquisition, source transfer, entity mapping hoặc service logic. Không thể kết luận chỉ từ hai số này rằng phần chênh lệch hoàn toàn là serialization.

Đo riêng:

- Thời gian chờ connection.
- Thời gian gửi/nhận request.
- Elasticsearch took.
- Mapping entity.
- Business processing.
- Response serialization.

Nếu chưa có instrumentation chi tiết, hãy thêm timer ở các boundary quan trọng và dùng tracing để xác định span nào chiếm thời gian.

Không tối ưu query DSL nếu phần lớn latency nằm ở application mapping hoặc network. Ngược lại, nếu Elasticsearch took cao, tập trung vào query, mapping, shard và cluster resources.

## 26. Query profiling

Elasticsearch Profile API cho phép quan sát chi tiết quá trình thực thi một số thành phần query và aggregation:

    GET products/_search
    {
      "profile": true,
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "tenantId": "tenant-42"
              }
            },
            {
              "range": {
                "price": {
                  "gte": 50,
                  "lte": 300
                }
              }
            }
          ]
        }
      }
    }

Profile response có thể giúp nhận ra query component nào tốn thời gian. Tuy nhiên, profiling thêm overhead và có thể làm kết quả khác với request bình thường.

Dùng Profile API để điều tra một query cụ thể, không dùng kết quả profile làm benchmark latency production. Sau khi tối ưu, đo lại bằng workload bình thường.

## 27. Explain và slow logs

Explain giúp hiểu vì sao một document khớp query và score được tính như thế nào. Nó hữu ích cho relevance/debugging, nhưng không phải công cụ benchmark throughput.

Slow logs ghi lại query hoặc indexing operation vượt ngưỡng thời gian cấu hình. Chúng giúp phát hiện request chậm trong workload thật.

Một cách dùng:

1. Đặt ngưỡng slow log hợp lý theo index và workload.
2. Thu thập trong khoảng thời gian có tải thực.
3. Nhóm theo query shape hoặc endpoint.
4. Kiểm tra query DSL và shard.
5. Dùng Profile API để điều tra sâu một số query.
6. Tắt hoặc giảm logging chi tiết khi không cần để tránh overhead.

Slow log không thay thế histogram latency. Nó chỉ ghi những request vượt ngưỡng đã cấu hình.

## 28. Kiểm tra shard distribution

Một index có quá nhiều shard nhỏ hoặc một vài shard quá lớn có thể tạo overhead và mất cân bằng.

Benchmark cần ghi:

- Số primary shard và replica.
- Kích thước từng shard.
- Số document từng shard.
- Routing key và phân phối tenant.
- Số shard mỗi query phải truy cập.
- Shard relocation/recovery trong lúc đo.

Nếu một query luôn chạm tất cả shard, chi phí coordinating node và network có thể tăng. Nếu custom routing dồn một tenant lớn vào một shard, shard đó có thể trở thành hotspot.

Không chọn số shard chỉ dựa trên tổng dung lượng. Hãy đo cả kích thước shard, throughput ingest, query fan-out và khả năng mở rộng cluster.

## 29. Kiểm tra thread pool và queue

Khi Elasticsearch không xử lý request nhanh bằng tốc độ nhận request, queue có thể tăng. Nếu queue đầy, request có thể bị reject.

Theo dõi:

- Active thread.
- Queue length.
- Rejected count.
- Thời gian queue.
- Số request đang chạy đồng thời.

Tên thread pool và endpoint stats phụ thuộc version. Không tăng queue size một cách tự động khi thấy reject. Queue lớn có thể chỉ biến lỗi nhanh thành latency dài và tiêu thụ memory nhiều hơn.

Hãy xác định bottleneck trước: CPU, disk, network, shard imbalance, bulk size hay query quá nặng. Backpressure và điều chỉnh concurrency thường hiệu quả hơn chỉ tăng queue.

## 30. Benchmark bulk indexing

Để đo ingest, cần cố định:

- Batch size theo số document và bytes.
- Số worker/concurrency.
- Refresh policy.
- Replica count và index settings.
- Mapping và ingest pipeline.
- Kích thước source.
- Phân phối routing.
- Số shard.

Một kịch bản cần ghi:

    Documents attempted: 5,000,000
    Documents indexed:   4,998,700
    Item failures:       1,300
    Duration:            900 seconds
    Throughput:          calculated from successful items
    p95 bulk latency:    measured per request

Throughput phải tính từ số document thành công, không phải số document đã gửi. Ghi riêng item failure, retry và DLQ.

Không dùng refresh IMMEDIATE sau từng batch nếu production không có cùng policy. Với import lớn, đo policy thực tế như NONE và refresh một lần sau khi hoàn tất.

## 31. Bulk batch size và concurrency

Batch size quá nhỏ tạo nhiều request overhead. Batch quá lớn có thể:

- Tăng memory ở ứng dụng và coordinating node.
- Tăng latency của một request.
- Làm retry tốn kém.
- Gây indexing pressure.
- Vượt giới hạn HTTP request.

Concurrency quá thấp không khai thác đủ tài nguyên; quá cao gây queue, reject và tail latency.

Benchmark ma trận:

| Batch size | Worker count | Mục tiêu |
|---:|---:|---|
| 250 docs | 1 | Baseline nhỏ |
| 500 docs | 2 | Kiểm tra tăng song song |
| 1.000 docs | 4 | Kiểm tra throughput |
| 2.000 docs | 4 | Kiểm tra tác động payload lớn |
| 1.000 docs | 8 | Kiểm tra concurrency |

Đây là ma trận minh họa. Thay đổi một biến mỗi lần khi cần hiểu nguyên nhân; sau đó chạy lại workload kết hợp để xác nhận.

Theo dõi bytes/request, latency, 429, heap, disk và merge. Không chọn batch lớn nhất chỉ vì nó có throughput cao trong một lần chạy ngắn.

## 32. Benchmark pagination

Pagination trang đầu và trang sâu có chi phí khác nhau. from/size có thể tốn hơn khi offset tăng vì Elasticsearch cần thu thập và bỏ qua nhiều kết quả hơn.

Benchmark các mức:

- Trang đầu.
- Trang 5 hoặc 10.
- Offset sâu gần giới hạn thực tế.
- PIT + search_after.
- Kết quả có sort theo field keyword/date.
- Kết quả có tie-breaker ổn định.

Nếu production dùng search_after, benchmark phải dùng đúng sort và cursor. Nếu production dùng from/size, không thay bằng search_after trong benchmark rồi kết luận hệ thống hiện tại đáp ứng SLO.

Đo cả latency từng trang và thời gian hoàn thành toàn bộ export. Với cursor pagination, kiểm tra overhead mở/đóng PIT và giữ context trong thời gian dài.

## 33. Benchmark aggregation

Aggregation có chi phí phụ thuộc số document, cardinality, số bucket và độ sâu lồng nhau.

Nên đo:

- Terms aggregation trên low-cardinality field.
- Terms aggregation trên high-cardinality field.
- Composite aggregation qua nhiều trang.
- Nested aggregation.
- Pipeline aggregation.
- Aggregation kết hợp query filter.
- Aggregation trên khoảng thời gian dài.

Theo dõi:

- Query latency.
- Bucket count.
- Response size.
- Heap pressure.
- Circuit breaker events.
- Số shard tham gia.

Không chỉ benchmark một aggregation có 5 bucket. Nếu dashboard thực tế nhóm theo tenant hoặc product ID, cần mô phỏng cardinality thực tế.

## 34. Benchmark search với nested và parent-child

Nếu mô hình dữ liệu dùng nested hoặc parent-child, benchmark cần có phân phối số phần tử con trên mỗi parent gần production.

Với nested:

- Đo số nested object trung bình và p95 mỗi document.
- Tạo một tỷ lệ document có nhiều nested object.
- Benchmark nested query, nested aggregation, inner_hits và nested sort.
- Đo tác động update document cha.

Với parent-child:

- Đo số child trung bình và p99 mỗi parent.
- Mô phỏng routing thực tế.
- Benchmark has_child và has_parent.
- Kiểm tra shard hotspot.
- Đo chi phí index/update child.

Không so nested và parent-child bằng dataset khác nhau. Giữ cùng logic nghiệp vụ, query semantics và số document tương đương để kết quả có ý nghĩa.

## 35. Công cụ tạo tải

Một số công cụ thường dùng:

| Công cụ | Phù hợp với |
|---|---|
| Elasticsearch Rally | Benchmark Elasticsearch, track và workload có thể tái lập |
| k6 | Load test HTTP API và mô hình arrival rate |
| Gatling | Load test HTTP với kịch bản và virtual users |
| JMeter | Kịch bản HTTP/API và kiểm thử tích hợp tải |
| Locust | Sinh tải bằng Python và mô hình user tùy chỉnh |
| Công cụ nội bộ | Workload đặc thù, event stream hoặc batch job |

Elasticsearch Rally hữu ích khi muốn benchmark engine, index và query trực tiếp. k6/Gatling/JMeter phù hợp khi cần đo toàn bộ API Spring Boot từ góc nhìn client.

Không nên chỉ dùng benchmark trực tiếp Elasticsearch để suy ra latency end-to-end của ứng dụng. Cũng không nên chỉ dùng HTTP load test nếu cần xác định query engine là bottleneck.

## 36. Elasticsearch Rally

Rally là công cụ benchmark dành cho Elasticsearch. Nó hỗ trợ track, corpus, challenge và workload để đo indexing/search performance.

Một benchmark Rally nên cố định:

- Elasticsearch version.
- Track/corpus version.
- Cluster topology.
- Node hardware.
- JVM settings.
- Challenge.
- Client settings.
- Thời gian chạy.

Nếu dùng custom track, lưu cấu hình track cùng repository hoặc artifact để lần sau chạy lại. Không chỉnh corpus và query mix giữa hai lần so sánh mà không ghi nhận.

Rally đo hiệu năng Elasticsearch ở tầng cluster/client benchmark. Nó không đo toàn bộ Spring Data conversion và business logic.

## 37. k6 cho Spring Boot API

Một kịch bản k6 có thể mô phỏng request search:

    import http from 'k6/http';
    import { check, sleep } from 'k6';

    export const options = {
      scenarios: {
        search: {
          executor: 'constant-arrival-rate',
          rate: 100,
          timeUnit: '1s',
          duration: '5m',
          preAllocatedVUs: 50,
          maxVUs: 200
        }
      }
    };

    export default function () {
      const response = http.get(
        'http://localhost:8080/products/search?q=keyboard'
      );

      check(response, {
        'status is 200': (r) => r.status === 200
      });
    }

Ví dụ này dùng một query cố định nên chưa đại diện cho query mix thực tế. Trong benchmark thật, hãy chọn tham số từ tập dữ liệu có phân phối, giữ tỷ lệ các query family và tránh chỉ lặp một keyword.

Constant arrival rate giúp kiểm tra hệ thống với tốc độ request định trước. Cần theo dõi dropped iterations và tài nguyên của load generator để xác nhận generator tạo được tải yêu cầu.

## 38. Benchmark qua Spring Data và benchmark trực tiếp Elasticsearch

Nên thực hiện hai lớp đo:

### Đo trực tiếp Elasticsearch

Mục tiêu:

- Đo query DSL.
- Đo indexing.
- Đo shard và cluster.
- Đo aggregation.
- Xác định server-side bottleneck.

### Đo qua Spring Boot/Spring Data

Mục tiêu:

- Đo API latency.
- Đo conversion và mapping.
- Đo connection pool.
- Đo DTO và serialization.
- Đo auth, validation và business logic.
- Đo concurrency của request thực tế.

Nếu benchmark trực tiếp Elasticsearch nhanh nhưng API chậm, hãy điều tra application path. Nếu cả hai đều chậm, điều tra query/cluster và data layout trước.

## 39. Kiểm soát môi trường benchmark

Để so sánh có ý nghĩa, cần ghi lại:

- CPU model và số core.
- RAM và heap size.
- Disk type, IOPS và filesystem.
- Network bandwidth và latency.
- Số Elasticsearch node.
- Node roles.
- Số primary/replica shard.
- Elasticsearch version.
- JVM version và flags.
- Spring Boot/Spring Data/client versions.
- Container CPU/memory limits.
- TLS/proxy/load balancer.
- Refresh interval và index settings.

Không so hai kết quả được chạy trên phần cứng hoặc cấu hình khác nhau rồi kết luận thay đổi query là nguyên nhân.

Nếu benchmark trong Kubernetes, ghi lại requests/limits, node placement, storage class, pod restarts và CPU throttling.

## 40. Cố định trạng thái cluster

Trước mỗi lần chạy:

1. Xác nhận cluster health.
2. Kiểm tra shard allocation và relocation.
3. Kiểm tra không có snapshot, reindex hoặc job nền bất thường.
4. Kiểm tra index settings và mapping.
5. Kiểm tra disk watermark.
6. Kiểm tra heap và GC baseline.
7. Xác nhận dataset đã ingest đầy đủ.
8. Ghi lại cache/refresh state.

Nếu một node đang restart hoặc shard đang relocate, kết quả có thể không đại diện cho trạng thái steady-state.

Không nhất thiết phải làm cluster hoàn toàn nhàn rỗi nếu mục tiêu là đo production mixed workload. Nhưng trạng thái nền phải được ghi lại và tái tạo được.

## 41. Mỗi lần chỉ thay đổi một biến

Khi tối ưu, hãy thay đổi từng yếu tố:

- Query DSL.
- Mapping/analyzer.
- Number of shards.
- Replica count.
- Refresh interval.
- Bulk batch size.
- Concurrency.
- Source filtering.
- DTO conversion.
- Connection pool.

Nếu cùng lúc đổi mapping, query, shard và heap, không thể biết yếu tố nào tạo ra khác biệt.

Một vòng thử nghiệm:

    Baseline
       |
       v
    Thay đổi một yếu tố
       |
       v
    Chạy cùng dataset/workload
       |
       v
    So latency/throughput/error/resources
       |
       v
    Giữ hoặc rollback thay đổi

Sau khi tìm được các thay đổi tốt riêng lẻ, chạy lại mixed workload để kiểm tra chúng không tạo tác dụng phụ khi kết hợp.

## 42. Lặp lại benchmark và báo cáo biến động

Một lần chạy có thể bị ảnh hưởng bởi background activity, cache, GC hoặc network. Hãy chạy nhiều lần trong điều kiện tương đương.

Báo cáo:

- Số lần lặp.
- Warm-up duration.
- Measurement duration.
- Median hoặc range giữa các lần chạy.
- p50/p95/p99 từng lần.
- Error rate.
- Cluster state.
- Dataset/version.

Nếu kết quả thay đổi mạnh giữa các lần, cần tìm nguyên nhân trước khi tối ưu dựa trên một con số đơn lẻ.

Không chọn lần chạy nhanh nhất làm kết quả chính. Dùng thống kê ổn định và mô tả độ biến động.

## 43. Soak test và memory pressure

Một hệ thống có thể chạy tốt trong 5 phút nhưng suy giảm sau nhiều giờ do:

- Heap tăng.
- GC pause dài.
- Segment merge backlog.
- Thread pool queue tích lũy.
- Connection leak.
- Reactive subscription không được giải phóng.
- PIT/scroll context tồn tại quá lâu.
- DLQ/retry backlog tăng.

Soak test chạy workload ổn định trong thời gian dài và theo dõi xu hướng. Không chỉ xem latency cuối cùng; xem heap, disk, queue và resource utilization theo thời gian.

Nếu benchmark lâu tạo lỗi tăng dần, kiểm tra memory leak và resource lifecycle trước khi tăng node size.

## 44. Spike test và burst

Production có thể có traffic burst do campaign, batch job, event replay hoặc client retry. Spike test tăng tải đột ngột để đo:

- Thời gian hệ thống hấp thụ burst.
- Mức tăng p95/p99.
- Queue growth.
- 429/reject.
- Thời gian phục hồi sau khi burst kết thúc.
- Tác động đến search trong lúc bulk import.

Một hệ thống tốt không nhất thiết không bao giờ reject. Quan trọng là backpressure, retry và recovery có kiểm soát, không gây cascading failure.

## 45. Tách tải generator khỏi tải cluster

Nếu load generator dùng hết CPU, không thể gửi request đúng tốc độ. Khi đó throughput đo được bị giới hạn bởi generator.

Theo dõi:

- CPU và memory của generator.
- Số connection mở.
- DNS/TLS overhead.
- Network throughput.
- Request queue và dropped iterations.
- Số virtual users thực tế.

Có thể chạy generator trên máy riêng hoặc nhiều máy để tránh cạnh tranh tài nguyên với Elasticsearch. Nếu đo end-to-end API, giữ đường network giống production nhất có thể.

## 46. Dữ liệu test và quyền riêng tư

Không sao chép dữ liệu cá nhân production sang môi trường benchmark mà không có kiểm soát. Có thể:

- Mask email/phone.
- Thay tên và địa chỉ bằng dữ liệu tổng hợp.
- Giữ phân phối nhưng thay giá trị định danh.
- Loại token, credential và ghi chú nội bộ.
- Giới hạn quyền truy cập dataset.
- Mã hóa storage và giới hạn retention.

Benchmark cần đặc tính dữ liệu, không cần danh tính thật của người dùng.

Nếu dùng snapshot production đã ẩn danh, lưu thông tin nguồn và quy trình biến đổi để có thể tái lập dataset.

## 47. Đọc kết quả và tìm bottleneck

Một vài mẫu dấu hiệu:

| Dấu hiệu | Nguyên nhân cần kiểm tra |
|---|---|
| Elasticsearch took cao, CPU cao | Query phức tạp, aggregation, scoring hoặc shard fan-out |
| Elasticsearch took thấp, API latency cao | Network, connection pool, entity mapping, DTO hoặc serialization |
| Throughput indexing thấp, 429 cao | Concurrency/batch quá lớn, indexing pressure hoặc cluster quá tải |
| p99 cao nhưng p50 ổn | Một nhóm query nặng, shard hotspot, GC hoặc disk latency |
| Latency tăng khi dữ liệu lớn | Cardinality, segment, shard sizing hoặc query selectivity |
| Search chậm chỉ khi ingest | Merge, refresh, indexing contention và disk I/O |
| Aggregation chậm theo tenant lớn | Cardinality và skew |
| Heap tăng theo thời gian | Aggregation/bucket pressure, cache, memory leak hoặc workload |
| Một node nóng hơn nhiều | Shard allocation, routing skew hoặc node resource imbalance |

Đây là hướng điều tra, không phải kết luận tự động. Cần đối chiếu với node stats, query profile, slow logs, APM và dữ liệu benchmark.

## 48. Đừng tối ưu dựa trên một query đơn lẻ

Một query có thể nhanh hơn sau khi thay đổi mapping nhưng workload tổng thể lại chậm hơn:

- Tăng fielddata hoặc cache làm tốn heap.
- Thêm replica cải thiện search throughput nhưng tăng write cost.
- Tăng số shard giảm shard size nhưng tăng fan-out và overhead.
- Tắt _source giảm storage nhưng làm thay đổi response/update/reindex workflow.
- Thêm nested field làm query chính xác hơn nhưng tăng indexing cost.

Hãy đo toàn bộ query mix và read/write ratio. Tối ưu phải dựa trên tradeoff của hệ thống, không chỉ một endpoint.

## 49. Benchmark và A/B test mapping

Khi so sánh mapping hoặc query mới:

1. Tạo hai index với cùng dữ liệu.
2. Giữ shard count, replica và settings tương đương.
3. Chỉ thay mapping hoặc query cần kiểm tra.
4. Chạy cùng workload và seed.
5. Đo latency, throughput, heap, disk và index size.
6. Kiểm tra tính đúng của kết quả query.
7. Chạy mixed workload trước khi chọn phương án.

Không so index mới đã force merge với index cũ đang ingest liên tục. Giữ trạng thái segment và cache tương đương nếu mục tiêu là so query.

## 50. Đo độ đúng cùng với hiệu năng

Một query nhanh nhưng trả sai kết quả không phải tối ưu thành công.

Khi thay query/mapping, kiểm tra:

- Số hit.
- Tập ID trả về.
- Thứ tự sort.
- Aggregation values.
- Nested matching semantics.
- Highlight.
- Total hits relation.
- Tenant/document isolation.
- Kết quả ở biên range và null/missing.

Benchmark nên có correctness assertion cho mỗi query family. Có thể so kết quả với một baseline đáng tin cậy trên dataset cố định.

Không dùng benchmark để thay thế test chức năng; nhưng mỗi thay đổi hiệu năng cần bảo đảm semantics không bị thay đổi ngoài dự kiến.

## 51. Quy trình benchmark từ đầu đến cuối

Một quy trình thực tế:

1. Xác định SLO và workload mục tiêu.
2. Thu thập query mix và phân phối dữ liệu từ production đã ẩn danh.
3. Tạo dataset có seed/version cố định.
4. Tạo index với mapping/settings giống production.
5. Bulk ingest và xác nhận số document, cardinality, kích thước.
6. Chuẩn bị trạng thái refresh/cache phù hợp với scenario.
7. Chạy warm-up.
8. Chạy baseline ở tải thấp.
9. Chạy load test ở request rate mục tiêu.
10. Tăng concurrency để tìm điểm bão hòa.
11. Chạy mixed read/write và bulk.
12. Chạy spike và soak test.
13. Thu thập p50/p95/p99, throughput, errors và tài nguyên.
14. Dùng slow logs/Profile API để điều tra query chậm.
15. Thay đổi một biến và chạy lại cùng workload.
16. Xác nhận correctness và so sánh kết quả nhiều lần.
17. Lưu report, dataset version, config và script để tái lập.

## 52. Mẫu báo cáo benchmark

Một báo cáo nên có:

    Benchmark: product-search-mixed-v3
    Date:
    Commit:
    Elasticsearch version:
    Spring Data version:
    Java version:
    Cluster nodes:
    CPU / RAM / disk:
    Primary shards / replicas:
    Dataset version:
    Document count:
    Index size:
    Query mix:
    Read/write ratio:
    Arrival rate:
    Concurrency:
    Warm-up:
    Measurement duration:
    Cache scenario:
    Refresh interval:

    Results:
      Throughput:
      p50:
      p95:
      p99:
      Error rate:
      429 count:
      Bulk item failure rate:
      Indexing lag:
      CPU:
      Heap:
      Disk I/O:
      Thread pool queue/rejections:

    Notes:
      Known deviations from production:
      Bottleneck observed:
      Follow-up experiments:

Ghi rõ mọi sai khác với production. Ví dụ cluster test chỉ có một node, dataset chưa đủ lớn hoặc không có traffic write. Những giới hạn đó giúp người đọc hiểu phạm vi kết luận.

## 53. Những sai lầm thường gặp

### Benchmark trên vài trăm document

Dataset quá nhỏ có thể nằm trong cache và không phản ánh cardinality hoặc shard distribution. Dùng quy mô và phân phối gần thực tế.

### Dữ liệu ngẫu nhiên đồng đều

Production thường có tenant/category/keyword skew. Mô phỏng phân phối lệch và giá trị phổ biến/hiếm.

### Chỉ đo một query

Workload thật có nhiều query family và tỷ lệ khác nhau. Dùng query mix.

### Chỉ đo average latency

Average che giấu tail latency. Báo p50/p95/p99 và error rate.

### Không warm-up hoặc chỉ đo warm cache

Cold-start và steady-state là hai scenario khác nhau. Ghi rõ cache state và warm-up.

### Chỉ đo search-only

Indexing, refresh và merge có thể làm search chậm. Chạy mixed workload nếu production có read/write đồng thời.

### Dùng Profile API để báo latency production

Profile thêm overhead. Dùng nó để điều tra, rồi đo lại bằng request bình thường.

### Không theo dõi load generator

Generator bão hòa có thể làm throughput đo được thấp giả tạo. Theo dõi CPU, connection và dropped iterations.

### Tăng concurrency vô hạn

Sau điểm bão hòa, latency và lỗi tăng mà throughput không tăng. Tìm operating point có headroom.

### Force merge trước mọi lần đo

Force merge thay đổi segment state. Chỉ dùng khi production có cùng quy trình.

### Thay nhiều biến cùng lúc

Không biết thay đổi nào tạo ra kết quả. Thay từng biến rồi chạy mixed workload để xác nhận.

### Bỏ qua correctness

Query nhanh nhưng trả thiếu hoặc sai document là regression. So kết quả với baseline.

### Không ghi lại cấu hình

Không thể tái lập hoặc giải thích khác biệt. Lưu mapping, settings, versions, dataset seed và workload script.

### Dùng dữ liệu cá nhân thật

Benchmark không cần danh tính thật. Mask hoặc tạo dữ liệu tổng hợp và kiểm soát quyền truy cập.

## 54. Khi nào dùng JMH?

JMH phù hợp để đo các đoạn code Java nhỏ như:

- Chuyển đổi DTO.
- Serialization/deserialization thuần.
- Xử lý collection.
- Tạo query object.
- Một thuật toán mapping độc lập.

JMH không thay thế load test cho Elasticsearch. Một benchmark JMH không mô phỏng shard, network, disk, refresh, merge hoặc concurrency của cluster.

Nếu cần tách application CPU cost khỏi network, có thể benchmark mapper/serializer bằng JMH, rồi dùng load test end-to-end để đo toàn bộ request path.

## 55. Đánh giá tác động của connection pool

Spring Data Elasticsearch sử dụng client và transport ở bên dưới. Connection pool, keep-alive, TLS và timeout ảnh hưởng đến latency.

Benchmark cần kiểm tra:

- Connection được tái sử dụng hay tạo mới mỗi request.
- Pool size và số request đang chờ connection.
- Connection timeout.
- Socket/request timeout.
- TLS handshake.
- Load balancer/proxy.
- Retry ở transport/client.

Nếu mỗi request tạo một client mới, benchmark sẽ đo chi phí khởi tạo và connection thay vì workload production. Client nên được quản lý theo lifecycle của ứng dụng và tái sử dụng theo cấu hình phù hợp.

Không tăng pool size vô hạn. Nhiều connection hơn có thể làm tăng concurrency đến cluster và tạo overload.

## 56. Tác động của source filtering và response size

Response lớn tiêu tốn network, heap và serialization. Nếu endpoint chỉ cần name, price và category, lấy toàn bộ source có thể tạo chi phí không cần thiết.

Benchmark hai kịch bản:

- Full source.
- Source filtering hoặc projection chỉ lấy field cần thiết.

Đo:

- Response bytes.
- Elasticsearch took.
- Network throughput.
- Application mapping time.
- Heap allocation.
- HTTP serialization time.

Source filtering có thể giảm payload nhưng không tự bảo vệ field. Khi đo hiệu năng, vẫn phải giữ query và semantics tương đương để so sánh đúng.

## 57. Tác động của _source, stored fields và doc values

Mapping ảnh hưởng cả hiệu năng và khả năng trả dữ liệu:

- _source giúp lấy lại document JSON nhưng có storage/transfer cost.
- doc values hỗ trợ sort/aggregation và một số cách fetch field.
- stored fields có thể trả field được cấu hình store.
- index:false có thể giảm indexing work nhưng làm thay đổi query capability.

Không thay đổi mapping chỉ để cải thiện một benchmark nhỏ. Hãy xác định field nào cần query, sort, aggregation, fetch và reindex; sau đó đo index size, ingest throughput, query latency và response size.

## 58. Tác động của replica

Replica có thể tăng khả năng phục vụ search và khả năng chịu lỗi, nhưng làm tăng chi phí ghi và storage.

Benchmark:

- Một primary không replica.
- Primary cùng replica theo cấu hình production.
- Search concurrency cao.
- Bulk indexing đồng thời.
- Node failure hoặc replica recovery nếu cần đánh giá resilience.

Không so throughput write giữa hai cấu hình rồi chỉ kết luận replica làm chậm. Hãy xem cả search throughput, availability và recovery.

## 59. Benchmark trong môi trường gần production nhưng an toàn

Không nên chạy stress test trực tiếp trên production nếu chưa có kế hoạch và kiểm soát. Có thể tạo staging/performance environment với:

- Cấu hình node và disk gần production.
- Dataset đã ẩn danh.
- Mapping/settings tương đương.
- Query mix lấy từ telemetry đã loại dữ liệu nhạy cảm.
- Rate limit và thời gian chạy có kiểm soát.
- Dashboard theo dõi cluster.
- Kế hoạch dừng nếu lỗi hoặc resource vượt ngưỡng.

Nếu phải chạy một bài đo production có kiểm soát, cần giới hạn tải, chọn thời điểm, giám sát và có tiêu chí dừng rõ ràng. Không tạo tải bất ngờ lên hệ thống phục vụ người dùng.

## 60. Checklist trước khi kết luận một thay đổi nhanh hơn

- Dataset và seed giống nhau.
- Mapping/settings giống nhau trừ biến đang thử.
- Cluster topology và hardware tương đương.
- Query mix và tham số giống nhau.
- Warm-up và cache state được ghi rõ.
- Measurement duration đủ dài.
- Load generator không bão hòa.
- Throughput, p50, p95, p99 và error rate được so sánh.
- CPU, heap, GC, disk, thread pool và merge được theo dõi.
- Search và indexing concurrency giống workload mục tiêu.
- Correctness của kết quả được xác nhận.
- Kết quả được lặp lại.
- Sai khác với production được ghi nhận.

## Kết luận

Đo hiệu năng trên dữ liệu và truy vấn gần với thực tế cần tái tạo cả data shape lẫn workload. Dataset phải có quy mô, kích thước document, cardinality, skew, phân phối thời gian, nested data và tỷ lệ update gần production. Query mix cần gồm các loại search, filter, sort, pagination, aggregation và nested query với tham số phổ biến/hiếm. Benchmark cũng phải mô phỏng đọc và ghi đồng thời nếu production có workload hỗn hợp.

Đo throughput cùng p50/p95/p99, error rate và tài nguyên cluster; đồng thời instrument Spring Data/application để tách thời gian server khỏi network, connection pool, entity mapping và serialization. Warm-up, cache, refresh, merge, shard distribution và load generator đều ảnh hưởng kết quả. Dùng Profile API và slow logs để điều tra, nhưng đo lại bằng request bình thường. Thay đổi từng biến, chạy lặp, xác nhận correctness và lưu dataset/config/workload để tái lập. Một benchmark đáng tin cậy phải giúp tìm operating point đáp ứng SLO với headroom, chứ không chỉ tạo ra một con số throughput cao trong điều kiện thuận lợi.
