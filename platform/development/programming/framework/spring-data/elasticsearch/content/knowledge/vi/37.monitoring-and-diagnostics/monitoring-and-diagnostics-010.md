# Slow log, Profile API và phân tích truy vấn chậm

Khi tìm kiếm Elasticsearch chậm, câu hỏi đầu tiên không chỉ là “query JSON có phức tạp không?” mà là **thời gian đang bị tiêu tốn ở đâu**. Một request có thể chậm do query execution trên shard, fetch và tải `_source`, aggregation, nhiều shard, queue/thread pool, mạng, ứng dụng gọi lặp hoặc cluster đang thiếu tài nguyên. Cần phân biệt latency người dùng cảm nhận với thời gian Elasticsearch báo cáo.

Elasticsearch có hai công cụ thường dùng để điều tra ở mức truy vấn:

- **Slow log** ghi lại những hoạt động search hoặc indexing vượt ngưỡng thời gian cấu hình. Nó giúp tìm request thực sự chậm trong workload đang chạy.
- **Profile API** phân rã quá trình thực thi của một search request thành query, collector, fetch và các thành phần liên quan. Nó giúp hiểu vì sao một query cụ thể tốn thời gian.

Hai công cụ bổ sung cho nhau. Slow log giúp phát hiện vấn đề trong môi trường thật; Profile API giúp phân tích có mục tiêu một query đã được tái tạo. Profile có overhead đáng kể và không nên bật đại trà cho mọi request production. Slow log cũng cần ngưỡng, mức log và chính sách lưu trữ phù hợp để không tạo quá nhiều log hoặc ghi lộ nội dung query nhạy cảm.

## 1. Hiểu đúng các loại thời gian

Trước khi đọc log, hãy xác định số đo nào đang tăng:

| Số đo | Ý nghĩa | Điều nó không đại diện đầy đủ |
|---|---|---|
| Client/end-to-end latency | Thời gian từ lúc ứng dụng gửi request tới khi nhận và xử lý response | Không chỉ riêng thời gian Elasticsearch thực thi |
| Elasticsearch `took` | Thời gian server báo cáo cho việc xử lý search request | Không bao gồm toàn bộ thời gian mạng và xử lý ở ứng dụng |
| Search slow log | Thời gian một shard mất để thực hiện phần query hoặc fetch vượt ngưỡng | Không phải một bản ghi end-to-end duy nhất cho toàn request |
| Profile timings | Thời gian chi tiết của các thành phần trong quá trình search | Không phải benchmark latency production chính xác |
| Queue time / thread pool | Thời gian request chờ tài nguyên hoặc dấu hiệu áp lực xử lý | Không giải thích trực tiếp query clause nào tốn CPU |

Ví dụ, người dùng có thể chờ 900 ms nhưng Elasticsearch `took` chỉ 180 ms. Phần còn lại có thể nằm ở DNS, kết nối HTTP, gateway, queue phía ứng dụng, serialize/deserialize hoặc xử lý response. Ngược lại, `took` cao thường chỉ ra thời gian xử lý bên trong Elasticsearch tăng, nhưng vẫn cần xem slow log và node metrics để tìm nguyên nhân.

### 1.1 Search request chạy qua nhiều giai đoạn

Một search thường được điều phối qua coordinating node và các shard được chọn:

1. Client gửi request tới một node.
2. Node nhận request, xác định shard và fan-out request.
3. Các shard thực hiện query phase.
4. Coordinator hợp nhất kết quả, chọn top hits và có thể yêu cầu fetch.
5. Các shard tải document/source cần thiết trong fetch phase.
6. Coordinator tạo response và trả cho client.

Thời gian có thể tăng ở bất kỳ giai đoạn nào. Một truy vấn trên nhiều shard chậm có thể bị chi phối bởi shard chậm nhất; một truy vấn có query phase nhanh nhưng fetch nhiều `_source` lớn vẫn có thể chậm.

### 1.2 Query phase và fetch phase

- **Query phase** tìm document phù hợp, tính điểm, thu thập top hits và kết quả cần cho aggregation.
- **Fetch phase** lấy nội dung document cho các hit được chọn, áp dụng source filtering, stored fields, highlighting hoặc các phần dữ liệu cần trả về.

Nếu query slow log cho thấy query phase nhanh nhưng fetch slow log vượt ngưỡng, hãy xem kích thước `_source`, số hit được trả về, highlighting, stored fields và số shard phải fetch. Nếu query phase chậm, xem query clauses, scoring, filters, aggregation và cấu trúc index.

## 2. Slow log là gì?

Elasticsearch slow log là log ở cấp shard cho các thao tác vượt ngưỡng thời gian đã cấu hình. Với search, có thể cấu hình riêng ngưỡng cho query phase và fetch phase. Với indexing, có thể cấu hình ngưỡng cho thao tác index.

Slow log hữu ích để:

- Phát hiện query chậm xảy ra trong workload thực tế.
- Tìm index/shard có nhiều hoạt động vượt ngưỡng.
- Biết request source/query, thời gian, số hit hoặc metadata mà phiên bản Elasticsearch ghi lại.
- Nhìn xu hướng theo thời gian và tìm truy vấn lặp lại.
- Thu thập mẫu query để tái hiện bằng Dev Tools hoặc test.

Slow log không tự động phân tích query hoặc chỉ ra chính xác clause gây chậm. Nó ghi lại sự kiện vượt ngưỡng; sau đó cần dùng query DSL, Profile API và metrics để giải thích.

### 2.1 Slow log có phạm vi theo index và shard

Ngưỡng slow log được cấu hình ở cấp index. Một search request phân tán tới nhiều shard có thể tạo nhiều bản ghi nếu các shard vượt ngưỡng. Vì vậy:

- Một request có thể tạo nhiều slow log entries.
- Một shard nóng có thể xuất hiện thường xuyên hơn các shard khác.
- Thời gian trong mỗi entry phản ánh phần xử lý của shard đó, không phải toàn bộ client request.
- Không cộng các thời gian shard một cách máy móc để suy ra end-to-end latency vì các shard thường xử lý song song.

Nếu một request chạm 12 shard và chỉ một shard vượt ngưỡng, log có thể chỉ cho thấy shard đó. Đây là thông tin hữu ích để tìm skew hoặc shard có dữ liệu/segment khác biệt.

### 2.2 Search slow log và indexing slow log

Elasticsearch có các nhóm cấu hình riêng:

| Nhóm | Mục tiêu |
|---|---|
| `index.search.slowlog.*` | Search query phase và fetch phase |
| `index.indexing.slowlog.*` | Indexing operations |

Bài này tập trung vào search chậm. Indexing slow log hữu ích khi ingest, bulk hoặc update gây áp lực khiến search bị ảnh hưởng, nhưng không thay thế search slow log.

## 3. Cấu hình search slow log

Các ngưỡng được đặt bằng index settings. Ví dụ cấu hình ngưỡng cho index `products`:

```http
PUT /products/_settings
{
  "index.search.slowlog.threshold.query.warn": "5s",
  "index.search.slowlog.threshold.query.info": "2s",
  "index.search.slowlog.threshold.query.debug": "1s",
  "index.search.slowlog.threshold.query.trace": "500ms",
  "index.search.slowlog.threshold.fetch.warn": "2s",
  "index.search.slowlog.threshold.fetch.info": "1s",
  "index.search.slowlog.threshold.fetch.debug": "500ms",
  "index.search.slowlog.threshold.fetch.trace": "200ms"
}
```

Đây là ngưỡng minh họa, không phải giá trị khuyến nghị chung. Chọn ngưỡng theo latency objective, kích thước cluster, tải nền và tỷ lệ log có thể xử lý. Một ngưỡng quá thấp có thể tạo lượng log rất lớn; ngưỡng quá cao có thể bỏ qua các query chậm nhưng phổ biến.

### 3.1 Các mức warn, info, debug và trace

Mỗi phase có thể có ngưỡng ở nhiều mức:

- `warn`: hoạt động vượt ngưỡng nghiêm trọng hơn.
- `info`: hoạt động chậm cần theo dõi.
- `debug`: ngưỡng thấp hơn để điều tra chi tiết có kiểm soát.
- `trace`: ngưỡng thấp nhất, thường chỉ bật ngắn hạn.

Một thao tác thường được ghi ở mức cao nhất phù hợp với ngưỡng mà nó vượt qua; không nên giả định cùng một operation sẽ luôn được ghi bốn lần. Cách log và định dạng chi tiết phụ thuộc Elasticsearch version.

Đặt các ngưỡng theo thứ tự giảm dần, ví dụ warn 5s, info 2s, debug 1s, trace 500ms. Hãy xác nhận hành vi với phiên bản đang chạy và mức log được bật trong logging configuration.

### 3.2 Ngưỡng -1 và việc tắt slow log

Các threshold thường mặc định không ghi slow log nếu chưa cấu hình. Có thể tắt một threshold bằng giá trị `-1` theo quy ước settings của Elasticsearch:

```http
PUT /products/_settings
{
  "index.search.slowlog.threshold.query.warn": "-1",
  "index.search.slowlog.threshold.query.info": "-1",
  "index.search.slowlog.threshold.query.debug": "-1",
  "index.search.slowlog.threshold.query.trace": "-1"
}
```

Không nên vô hiệu hóa mọi mức log chỉ để giảm log volume nếu đang có sự cố. Điều chỉnh ngưỡng theo mục tiêu điều tra và ghi lại cấu hình trước/sau khi thay đổi.

### 3.3 Áp dụng cấu hình cho index mới

Nếu index được tạo liên tục theo pattern, dùng index template để đặt ngưỡng mặc định cho index mới:

```http
PUT /_index_template/products-template
{
  "index_patterns": ["products-*"],
  "template": {
    "settings": {
      "index.search.slowlog.threshold.query.warn": "5s",
      "index.search.slowlog.threshold.query.info": "2s",
      "index.search.slowlog.threshold.fetch.warn": "2s",
      "index.search.slowlog.threshold.fetch.info": "1s"
    }
  }
}
```

Index template chỉ áp dụng khi index được tạo. Thay đổi template không tự sửa settings của các index đã tồn tại; cần update settings riêng cho các index đó.

### 3.4 Cấu hình indexing slow log

Để điều tra indexing chậm, có thể cấu hình:

```http
PUT /products/_settings
{
  "index.indexing.slowlog.threshold.index.warn": "5s",
  "index.indexing.slowlog.threshold.index.info": "2s",
  "index.indexing.slowlog.threshold.index.debug": "1s",
  "index.indexing.slowlog.threshold.index.trace": "500ms"
}
```

Indexing slow log có thể giúp phát hiện document lớn, ingest pipeline nặng, mapping explosion hoặc shard indexing bị chậm. Nhưng đừng quy mọi search latency tăng cho indexing; kiểm tra CPU, disk I/O, merge, refresh và thread pool để xác định mối quan hệ.

## 4. Những thông tin cần đọc trong slow log

Format slow log có thể thay đổi giữa các phiên bản, nhưng thường chứa các thông tin như:

- Timestamp và log level.
- Tên index và shard.
- Thời gian query hoặc fetch.
- Loại search operation và số hit.
- Query source hoặc một phần query source nếu cấu hình cho phép.
- Routing, metadata hoặc thông tin shard tùy phiên bản.

Khi đọc log, tìm các pattern:

1. Cùng một query source lặp đi lặp lại.
2. Một index hoặc shard thường xuyên vượt ngưỡng.
3. Query phase chậm hay fetch phase chậm.
4. Một số query chỉ chậm khi trả nhiều hits hoặc aggregation lớn.
5. Latency tăng cùng lúc với ingest, merge, GC hoặc thread pool queue.

Không chỉ sort log theo thời gian lớn nhất. Một query mất 400 ms nhưng chạy hàng nghìn lần mỗi phút có thể tạo tác động lớn hơn query 8 giây chỉ xảy ra một lần.

### 4.1 Tìm query lặp lại

Nếu nhiều log entries có cùng query shape nhưng giá trị khác nhau, gom nhóm theo:

- Index và shard.
- Query type/shape.
- Field được tìm kiếm.
- Filter/tenant.
- Kích thước page và số hits.
- Aggregation/sort.

Không cần giữ nguyên giá trị nhạy cảm khi tạo nhóm thống kê. Có thể chuẩn hóa query bằng cách thay literal bằng placeholder để tìm cùng một query pattern.

### 4.2 Xem query source

Slow log có thể ghi query source. Điều này rất hữu ích để tái hiện request, nhưng source có thể chứa tên người dùng, email, search phrase, tenant ID hoặc dữ liệu nhạy cảm. Cần đánh giá quyền truy cập log, retention và cách redaction trước khi bật ở môi trường thật.

Nếu không cần query source đầy đủ, có thể cấu hình chế độ ghi source phù hợp với phiên bản Elasticsearch và chính sách bảo mật. Đừng bật logging toàn bộ request body trong production chỉ để điều tra một truy vấn.

## 5. Logging configuration và nơi tìm log

Index settings xác định **ngưỡng**. Logging configuration của node xác định logger có được ghi ở level tương ứng không và log được đưa tới appender/file nào. Hai phần này phải cùng được cấu hình.

Nếu threshold đã đặt nhưng không thấy slow log, kiểm tra:

1. Setting áp dụng đúng index hay chưa.
2. Logger slow log có được bật ở level cần thiết không.
3. Node logging configuration có route logger tới appender/file mong muốn không.
4. Query thực sự vượt ngưỡng trên shard nào chưa.
5. Log collector/agent có thu thập file đúng không.

Logger category và file name cụ thể phụ thuộc bản phân phối, logging framework và Elasticsearch version. Dùng tài liệu logging của đúng release thay vì dựa vào đường dẫn log cũ.

### 5.1 Xem settings hiện tại

```http
GET /products/_settings?include_defaults=true&flat_settings=true
```

Tìm các key `index.search.slowlog.threshold.*` để xác nhận threshold đang được áp dụng. Nếu dùng nhiều index:

```http
GET /products-*/_settings?include_defaults=true&flat_settings=true
```

Kiểm tra template và index thực tế riêng biệt; template có thể đúng nhưng index đã tạo trước đó vẫn dùng settings cũ.

### 5.2 Thay đổi động và thay đổi cần restart

Nhiều `index.search.slowlog.threshold.*` là dynamic index settings và có thể thay đổi qua `_settings` mà không cần recreate index. Cấu hình logger/appender ở node là phần logging configuration riêng và có quy tắc cập nhật/restart khác nhau tùy version/deployment.

Không nhầm thay threshold của index với thay log level của node. Nếu chỉ chỉnh một phía, slow log vẫn có thể không xuất hiện.

## 6. Đọc query slow log và fetch slow log

Search slow log tách query phase và fetch phase:

| Log phase | Phần được đo | Dấu hiệu thường gặp |
|---|---|---|
| Query | Tìm và thu thập matching documents/top hits | Query DSL nặng, nhiều clauses, scoring, aggregation, shard data lớn |
| Fetch | Lấy nội dung document cho hits | `_source` lớn, nhiều hits, highlighting, stored fields hoặc fetch nhiều shard |

### 6.1 Query phase chậm

Kiểm tra:

- Query có `wildcard`, `regexp`, `prefix` hoặc fuzzy search quá rộng không?
- Có `script_score`, script query hoặc runtime field không?
- Bool query có nhiều clauses và nested query không?
- Có `must` scoring trong khi chỉ cần filter không?
- Có `terms` list quá lớn không?
- Aggregation có cardinality cao, nhiều buckets hoặc nested aggregation không?
- Có quá nhiều shard được fan-out cho một query không?

Các query trên không mặc nhiên sai. Vấn đề phụ thuộc dữ liệu, mapping, cardinality, index structure và giới hạn tài nguyên. Dùng Profile API để tìm phần cụ thể tiêu tốn thời gian.

### 6.2 Fetch phase chậm

Kiểm tra:

- Page size có quá lớn không?
- Có trả toàn bộ `_source` trong khi chỉ cần vài field không?
- Document có `_source` rất lớn hoặc nhiều nested object không?
- Có highlighting trên nhiều field hoặc fragment dài không?
- Có yêu cầu stored fields/doc values không cần thiết không?
- Có fetch nhiều hits trên nhiều shard không?

Có thể giảm dữ liệu trả về bằng source filtering:

```http
GET /products/_search
{
  "_source": ["sku", "name", "price"],
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "size": 20
}
```

Trong Spring Data Elasticsearch, cấu hình source filtering hoặc projection/DTO phù hợp với API version để chỉ lấy field cần dùng. Tránh tải toàn bộ entity lớn nếu response chỉ cần một vài thuộc tính.
## 7. Profile API là gì?

Profile API cung cấp thông tin chi tiết về cách Elasticsearch thực thi một search request. Nó cho biết các query component được tạo thành cây như thế nào, thời gian thực thi ước tính của từng node và một số bộ đếm nội bộ. Đây là công cụ để phân tích một query cụ thể sau khi đã phát hiện vấn đề.

Profile có thể giúp trả lời:

- Query nào được rewrite thành query Lucene nào?
- Clause nào trong bool query tốn thời gian nhất?
- Collector hoặc scoring có phải phần tốn thời gian không?
- Aggregation/fetch có đóng góp đáng kể không?
- Các shard có hành vi thực thi khác nhau không?

Profile không tự đưa ra khuyến nghị tối ưu và không đo toàn bộ thời gian người dùng chờ. Hãy dùng nó cùng slow log, response took, client latency, thread pool, node stats và dữ liệu thực tế.
## 8. Bật Profile API cho một search request

Thêm `"profile": true` vào search body:

```http
GET /products/_search
{
  "profile": true,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
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
  "size": 20
}
```

Elasticsearch trả kết quả search bình thường cùng một phần `profile` chứa thống kê theo shard. Phần profile thường có các nhóm như:

- `shards`: danh sách shard đã tham gia profiling.
- `searches`: các search context được profile trên shard.
- `query`: cây query nodes và breakdown của chúng.
- `rewrite_time`: thời gian rewrite query nếu được báo cáo.
- `collector`: thông tin collector thu thập kết quả.
- `fetch`: thông tin fetch phase trong các phiên bản hỗ trợ phần này.
- `aggregations`: thông tin profiling aggregation khi request có aggregation và phiên bản hỗ trợ.

Cấu trúc chi tiết thay đổi theo Elasticsearch version và loại query. Dùng response thật của cluster làm nguồn để đọc field, không hard-code một JSON shape cho mọi release.

### 8.1 Profile theo từng shard

Profile được tạo tại shard. Một response có thể có nhiều entry trong `profile.shards`, mỗi entry xác định node, index, shard và các search execution liên quan.

Khi so sánh:

- Xem shard nào tốn nhiều thời gian nhất.
- Kiểm tra shard đó có số document/segment hoặc workload khác biệt không.
- Xem cùng query node có timing chênh lệch lớn giữa shard không.
- Xác định có shard nào không tham gia vì routing hoặc query target hay không.

Không cộng tất cả `time_in_nanos` trong cây query hoặc giữa các shard để suy ra `took`. Một số timing là inclusive (bao gồm thời gian của child), một số shard chạy song song và Profile không đo mọi phần của request.

### 8.2 Đọc cây query

Trong `profile.shards[].searches[].query`, mỗi query node có thể chứa:

- `type`: loại query Lucene thực thi, ví dụ BooleanQuery hoặc TermQuery.
- `description`: mô tả query và các tham số.
- `time_in_nanos`: thời gian của node theo profiler.
- `breakdown`: các phép đo nội bộ như tạo scorer, advance, next document, score.
- `children`: query nodes con nếu query được cấu thành từ nhiều clause.

Ví dụ minh họa cấu trúc rút gọn:

```json
{
  "profile": {
    "shards": [
      {
        "id": "[node-id][products][0]",
        "searches": [
          {
            "query": [
              {
                "type": "BooleanQuery",
                "description": "+name:wireless +active:true",
                "time_in_nanos": 4200000,
                "breakdown": {
                  "score": 300000,
                  "advance": 1200000,
                  "build_scorer": 700000
                },
                "children": [
                  {
                    "type": "TermQuery",
                    "description": "name:wireless",
                    "time_in_nanos": 1800000,
                    "breakdown": {},
                    "children": []
                  }
                ]
              }
            ],
            "rewrite_time": 12000,
            "collector": []
          }
        ]
      }
    ]
  }
}
```

Các con số và trường trong ví dụ chỉ để minh họa cách đọc; không phải response đầy đủ hay timing chuẩn của Elasticsearch.

### 8.3 Hiểu breakdown

Breakdown cho biết profiler ghi nhận thời gian ở các thao tác nội bộ. Một vài tên có thể gặp:

| Thành phần | Cách hiểu khái quát |
|---|---|
| `create_weight` | Chuẩn bị query weight cho việc thực thi |
| `build_scorer` | Xây scorer dùng để tìm/đánh điểm document |
| `next_doc` | Chuyển tới document kế tiếp phù hợp |
| `advance` | Nhảy tới document ID mục tiêu hoặc vị trí tiếp theo |
| `score` | Tính điểm relevance |
| `match` | Kiểm tra match trong một số query type |
| `shallow_advance` | Bước advance tối ưu cho một số iterator |
| `compute_max_score` | Tính max score phục vụ tối ưu top hits |

Tên và tập breakdown phụ thuộc query type và Lucene version. Không phải mọi query đều có mọi bộ đếm. Hãy đọc chúng như bằng chứng về loại công việc, không coi một counter đơn lẻ là chỉ số hiệu năng tổng quát.

### 8.4 Timing của parent và child

Một query node cha có thể bao gồm thời gian của child query. Vì vậy, không cộng `time_in_nanos` của parent với tất cả child để tìm tổng thời gian. Thay vào đó, xem cây để hiểu query được cấu thành ra sao và so sánh các node cùng cấp hoặc breakdown tương ứng.

Nếu parent `BooleanQuery` tốn nhiều thời gian, mở child nodes để xem clause nào góp phần lớn. Nếu child nodes đều nhanh nhưng parent vẫn cao, phần còn lại có thể nằm ở việc kết hợp, scoring, coordination hoặc collector.

## 9. Profile collector, fetch và aggregation

Query nodes không phải phần duy nhất của một search.

### 9.1 Collector

Collector nhận document match và thu thập kết quả như top hits, total hits hoặc dữ liệu phục vụ aggregation. Query có thể tìm candidate nhanh nhưng collector vẫn tốn thời gian nếu phải thu thập nhiều document, tính điểm hoặc giữ nhiều bucket.

Trong profile output, đọc collector information cùng query tree. Nếu collector chiếm đáng kể, xem:

- `size` và `track_total_hits`.
- Sort theo field hay theo score.
- Aggregation và số lượng bucket.
- Query có phải duyệt nhiều candidate trước khi chọn top hits không.
- Có thể dùng filter context thay cho scoring ở điều kiện không cần relevance không.

### 9.2 Fetch phase

Fetch lấy nội dung của các hit đã chọn. Nếu query tree nhanh nhưng fetch timing đáng kể, hãy giảm payload:

```http
GET /products/_search
{
  "_source": ["sku", "name", "price"],
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "size": 20
}
```

Ngoài source filtering, kiểm tra highlighting, stored fields, script fields và document size. Không phải mọi response có phần fetch profile giống nhau ở mọi phiên bản; kết hợp với fetch slow log và request options để xác định chi phí.

### 9.3 Aggregation

Aggregation có thể tiêu tốn nhiều tài nguyên dù số hits trả về ít. Ví dụ terms aggregation trên field cardinality cao có thể tạo nhiều buckets và cần merge kết quả giữa shard.

Ví dụ:

```http
GET /products/_search
{
  "size": 0,
  "profile": true,
  "aggs": {
    "by_sku": {
      "terms": {
        "field": "sku",
        "size": 10000
      }
    }
  }
}
```

Nếu aggregation là phần chậm:

- Xác nhận field có mapping `keyword` hoặc numeric phù hợp.
- Kiểm tra cardinality thực tế và `size` bucket.
- Cân nhắc composite aggregation khi cần paginate qua nhiều bucket.
- Dùng pre-aggregation/materialized summary nếu workload lặp lại và dữ liệu lớn.
- Tránh aggregation trên text field nếu chưa dùng subfield phù hợp.

## 10. Giới hạn và chi phí của Profile API

Profile API có overhead đáng kể vì Elasticsearch phải thu thập và ghi lại timing cho nhiều thao tác nội bộ. Query được profile có thể chậm hơn nhiều so với khi chạy bình thường.

Các giới hạn cần nhớ:

- Không dùng profile timing làm SLO hoặc benchmark production.
- Không bật profile cho mọi request người dùng.
- Profile không đo đầy đủ network latency, client processing hoặc mọi queueing ở bên ngoài query execution.
- Một search request nhiều shard có nhiều profile trees; kết quả dài và khó đọc.
- Profiling có thể làm tăng CPU, memory và response payload.
- Query cache/request cache hoặc execution path có thể bị ảnh hưởng bởi chế độ profiling tùy version.
- Một profile đơn lẻ không đại diện workload có concurrency cao.

Hãy chọn một query đại diện, dùng dữ liệu và điều kiện tương tự production, chạy profile ở môi trường an toàn hoặc trong cửa sổ điều tra có kiểm soát. Sau khi hiểu vấn đề, tắt profile và đo lại query bình thường.

## 11. Dùng slow log và Profile API cùng nhau

Một quy trình hữu ích:

1. Dùng metrics/APM và slow log để tìm query pattern thực sự chậm.
2. Gom nhóm các entries theo query shape, index, shard và tần suất.
3. Lấy một request đại diện và loại bỏ dữ liệu nhạy cảm.
4. Tái hiện query trên cùng index/mapping và dữ liệu tương tự.
5. Chạy query bình thường để ghi nhận baseline `took` và client latency.
6. Bật `profile: true` cho request đó.
7. Đọc per-shard query tree, breakdown, collector, fetch và aggregation.
8. Thay đổi một yếu tố mỗi lần: query clause, sort, size, source filtering hoặc aggregation.
9. Chạy lại không profile để so sánh latency thực tế.
10. Theo dõi slow log/metrics sau khi deploy để xác nhận cải thiện trong workload thật.

Slow log trả lời “request nào vượt ngưỡng trong môi trường đang chạy?”. Profile trả lời “query này được thực thi như thế nào?”. Đừng dùng Profile để thay cho việc thu thập request thật, và đừng kỳ vọng slow log tự giải thích nguyên nhân.
## 12. Nơi phát slow log và cách kiểm tra logger

Slow log được phát vào Elasticsearch logging với metadata dataset `slowlog`. Các logger thường gặp:

- `index.search.slowlog`: search slow log.
- `index.indexing.slowlog.index`: indexing slow log trong các phiên bản hiện hành.

File log cụ thể phụ thuộc cách cài đặt và cấu hình node. Với bản phân phối Elasticsearch tiêu chuẩn, search slow log thường có suffix `_index_search_slowlog.json`, còn indexing slow log có suffix `_index_indexing_slowlog.json`. Nếu dùng Elastic Stack Monitoring, các sự kiện có thể được quan sát trong Stack Monitoring.

### 12.1 Hai nơi cấu hình khác nhau

Phân biệt:

- Index settings: quyết định operation nào vượt ngưỡng và được phát ra.
- `log4j2.properties`/node logging configuration: quyết định logger level, destination, rotation và cách log được ghi ra file.

Slow log có thể không xuất hiện nếu threshold đã bật nhưng logger level ở node không cho phép level đó đi qua, hoặc log collector không thu thập đúng file.

Logger search slow log hiện thường là `index.search.slowlog`; indexing slow log có thể có logger name chi tiết hơn theo operation và version. Hãy kiểm tra trường `log.logger` trong event thực tế thay vì đoán tên logger từ file.

### 12.2 Xem settings slow log hiện tại

```http
GET /products/_settings?include_defaults=true&flat_settings=true
```

Có thể lọc riêng slow log settings trên nhiều index:

```http
GET /_all/_settings?expand_wildcards=all&filter_path=*.settings.index.*.slowlog
```

Tất cả threshold mặc định là `-1`, nghĩa là slow logging bị tắt cho đến khi cấu hình. Không thấy log trong trường hợp mặc định là hành vi bình thường.

### 12.3 Theo dõi file và metadata

Trong log event, các trường có thể giúp phân tích gồm:

- `log.level`, `log.logger`.
- `elasticsearch.slowlog.took` và `elasticsearch.slowlog.took_millis`.
- `elasticsearch.slowlog.message` để nhận diện index/shard.
- `elasticsearch.slowlog.source` nếu query source được ghi.
- `elasticsearch.slowlog.total_hits`, `total_shards`, `search_type`.
- `elasticsearch.slowlog.id` nếu request gửi `X-Opaque-Id`.

Schema chính xác phụ thuộc phiên bản và cách log được ingest. Nếu cần nối log với request từ ứng dụng, gửi `X-Opaque-Id` có giá trị correlation ID không nhạy cảm. Tránh đưa token, email hoặc dữ liệu cá nhân vào header này.

## 13. Query logging: lựa chọn thống nhất cho search ở phiên bản mới

Trong các bản Elasticsearch mới, Elastic cung cấp **query logging** như một lựa chọn thống nhất cho search operations. Query logging ghi thời gian xử lý end-to-end mà Elasticsearch đo cho request, trong khi slow log truyền thống ghi thời gian xử lý ở cấp shard. Query logging có thể bao phủ nhiều ngôn ngữ truy vấn như Query DSL, ES|QL, EQL và SQL bằng một cấu hình.

Theo tài liệu Elastic hiện hành, với search operations, query logging là lựa chọn thay thế được khuyến nghị khi phiên bản/deployment hỗ trợ. Slow logs vẫn là lựa chọn cho indexing operations. Khả năng query logging và phạm vi hỗ trợ phụ thuộc phiên bản Elasticsearch, license/deployment và trạng thái phát hành của tính năng; kiểm tra docs đúng cluster trước khi thiết kế logging pipeline.

| Công cụ | Phạm vi thời gian | Loại request | Mục đích |
|---|---|---|---|
| Search slow log | Shard-level query/fetch | Search operations | Tìm shard/phase chậm |
| Indexing slow log | Index operation | Indexing operations | Tìm document/indexing operation chậm |
| Query logging | End-to-end request duration do Elasticsearch đo | Query DSL, ES\|QL, EQL, SQL theo version hỗ trợ | Tìm request chậm ở cấp Elasticsearch |
| Profile API | Chi tiết nội bộ query execution | Search request được profile | Giải thích chi phí query component |

Query logging không làm Profile API trở nên thừa. Query logging giúp xác định request chậm; Profile giúp xem cấu trúc và chi phí thực thi của một query cụ thể. Slow log vẫn hữu ích khi cần biết shard nào hoặc query/fetch phase nào chậm.

### 13.1 Khi nào nên bắt đầu bằng query logging?

Nếu cluster hỗ trợ query logging, hãy ưu tiên dùng nó để tìm request search chậm theo thời gian server đo. Nó hữu ích khi:

- Cần nhìn thời gian xử lý toàn request thay vì chỉ shard phase.
- Ứng dụng dùng nhiều loại query language.
- Muốn tìm request chậm mà không cần suy ra từ nhiều shard log entries.
- Cần nối request với nguồn gọi qua correlation metadata.

Sau khi tìm được query chậm, vẫn có thể dùng slow log để tìm shard/phase cụ thể và Profile API để phân tích query DSL tương ứng.

### 13.2 Khi nào slow log vẫn cần thiết?

Slow log phù hợp khi:

- Phiên bản chưa hỗ trợ query logging hoặc deployment không có tính năng đó.
- Cần phân biệt query phase với fetch phase.
- Cần xác định shard cụ thể thường xuyên vượt ngưỡng.
- Đang điều tra indexing operations, vì query logging không thay thế indexing slow log.

### 13.3 Không bật đồng thời mọi logging ở ngưỡng thấp

Query logging, search slow log, indexing slow log và audit/request body logging có thể tạo lượng log lớn. Bật từng nguồn theo mục tiêu, chọn ngưỡng phù hợp và đặt retention. Nếu cần ghi request body để tìm nguồn query, giới hạn thời gian và quyền truy cập vì payload có thể chứa dữ liệu nhạy cảm.

## 14. Search Profiler trong Kibana

Nếu môi trường có Kibana và Search Profiler được cài đặt, có thể dùng giao diện này để xem Profile API response dưới dạng cây query và biểu đồ thời gian. Nó giúp điều hướng query nodes, mở rộng child clauses và xem breakdown dễ hơn khi query phức tạp.

Search Profiler là giao diện hỗ trợ đọc profile; dữ liệu nền vẫn đến từ profiling của Elasticsearch. Vì vậy:

- Vẫn có overhead của Profile API.
- Timing vẫn không phải latency production thực tế.
- JSON profile có thể thay đổi theo Elasticsearch/Lucene version.
- Không nên tự động hóa phụ thuộc vào các field debug nội bộ dễ thay đổi.

Nếu không có Kibana Search Profiler, có thể gọi trực tiếp `_search` với `profile: true`, lưu response JSON và đọc từng shard/query tree.
## 15. Các nguyên nhân phổ biến của query chậm

Không có một query type nào luôn chậm trong mọi dữ liệu. Dưới đây là các pattern thường cần điều tra:

| Pattern | Vì sao có thể chậm | Hướng kiểm tra |
|---|---|---|
| Wildcard/regexp rộng | Có thể phải xét lượng term lớn trong dictionary | Profile query, giới hạn pattern, thiết kế field/index phù hợp |
| Fuzzy query với độ rộng lớn | Tạo nhiều term expansion | Giảm fuzziness, prefix length hoặc số expansion |
| Script query/script score | Tính toán theo document trong quá trình search | Xem số document candidate, thay bằng field được index trước nếu phù hợp |
| Deep pagination bằng from/size | Phải giữ nhiều kết quả trung gian trên mỗi shard | Dùng search_after và PIT cho pagination sâu |
| track_total_hits chính xác trên tập lớn | Cần đếm nhiều matching documents | Tắt hoặc giới hạn total hit tracking nếu sản phẩm không cần con số chính xác |
| Terms aggregation cardinality cao | Tạo/merge nhiều buckets, dùng global ordinals | Kiểm tra cardinality, bucket size và cách paginate aggregation |
| Sort trên field không tối ưu | Có thể cần đọc nhiều giá trị hoặc thiếu doc values | Kiểm tra mapping, sort field và số candidate |
| Trả nhiều _source lớn | Fetch và truyền payload tốn thời gian | Source filtering, DTO/projection, giảm size |
| Nhiều shard nhỏ | Một request fan-out tới nhiều shard, tăng coordination overhead | Xem shard count, routing và index strategy |
| Nested query nhiều tầng | Tăng lượng nested documents và query work | Kiểm tra nested path, cardinality và query shape |
| Ingest/merge cạnh tranh tài nguyên | CPU, disk I/O, heap và refresh bị chia sẻ | Đối chiếu slow log với indexing, merge, GC và thread pool metrics |

### 15.1 Wildcard, prefix và regexp

Query như:

```json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*1001"
      }
    }
  }
}
```

có thể tốn kém vì wildcard ở đầu chuỗi không giới hạn vùng term cần xét. Nếu yêu cầu nghiệp vụ cho phép, thiết kế field/search strategy khác như exact keyword, prefix field, n-gram hoặc normalized field. Không thay đổi query type nếu semantics tìm kiếm phải được giữ nguyên.

### 15.2 Deep pagination

Với `from` lớn, Elasticsearch phải thu thập nhiều kết quả trung gian ở từng shard trước khi trả page sau. Dùng `search_after` với sort ổn định và Point in Time (PIT) cho pagination sâu:

```http
POST /products/_search
{
  "size": 100,
  "sort": [
    { "createdAt": "asc" },
    { "productId": "asc" }
  ],
  "search_after": [1730000000000, "product-1000"],
  "query": {
    "match_all": {}
  }
}
```

Giá trị `search_after` phải lấy từ sort values của hit cuối page trước. Sort nên có tie-breaker ổn định và field hỗ trợ sort. Với PIT, gửi search request qua PIT để giữ snapshot nhất quán trong lúc paginate; cú pháp mở/đóng PIT tùy API/version.

### 15.3 track_total_hits

Nếu UI chỉ cần hiển thị “có thêm kết quả” thay vì tổng số chính xác, cân nhắc tắt hoặc giới hạn `track_total_hits`. Đếm toàn bộ hits có thể tốn thêm công việc trên tập dữ liệu lớn:

```json
{
  "track_total_hits": false,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
```

Chỉ thay đổi nếu sản phẩm không cần tổng số chính xác. Pagination, page count và UI có thể phụ thuộc total hits.

### 15.4 Dùng filter context cho điều kiện không cần score

Điều kiện trạng thái, tenant, loại sản phẩm hoặc khoảng giá thường chỉ quyết định document có được chọn hay không. Đặt chúng trong `filter` khi không cần relevance score:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "category": "keyboard"
          }
        }
      ]
    }
  }
}
```

Filter context không tính relevance score cho clause đó và có thể tận dụng cache khi phù hợp. Không phải mọi filter đều được cache; cache behavior phụ thuộc query, segment và workload.

### 15.5 Aggregation cardinality và global ordinals

Terms aggregation trên keyword field thường sử dụng global ordinals. Khi cardinality cao hoặc index vừa refresh, việc xây global ordinals có thể góp phần vào latency. Profile API không đo đầy đủ mọi công việc xây global ordinals, vì vậy hãy đối chiếu với node/index stats và latency theo thời điểm refresh.

Mapping có thể dùng `eager_global_ordinals` để chuyển một phần chi phí sang refresh/segment lifecycle:

```json
{
  "mappings": {
    "properties": {
      "category": {
        "type": "keyword",
        "eager_global_ordinals": true
      }
    }
  }
}
```

Đây không phải tối ưu miễn phí: nó có thể tăng heap usage và làm refresh lâu hơn. Chỉ cân nhắc khi workload aggregation đủ thường xuyên và có tài nguyên để chịu chi phí.

## 16. Kiểm tra cluster khi Profile không giải thích đủ

Một query có thể chậm vì tài nguyên hoặc queue của cluster, dù query tree không có một clause bất thường. Khi đó, mở rộng điều tra ra node và thread pool.

### 16.1 Thread pool

Kiểm tra search thread pool:

```http
GET /_cat/thread_pool/search?v
```

Hoặc node stats:

```http
GET /_nodes/stats/thread_pool,jvm,fs,indices
```

Xem active, queue, rejected và completed. Queue/rejection tăng có thể cho thấy node không xử lý kịp workload. Tên thread pool và response fields tùy version; đọc tài liệu API hiện tại.

### 16.2 Node và index stats

```http
GET /_nodes/stats/indices,thread_pool,jvm,process,fs
```

```http
GET /products/_stats/search,query_cache,request_cache,segments,merges,refresh
```

Các nhóm số liệu hữu ích:

- Search query/fetch count và time.
- Query cache/request cache hit, miss, eviction.
- Segment count và merge activity.
- Refresh count/time.
- JVM heap, GC và process CPU.
- Disk I/O, free space và shard allocation.

So sánh theo thời gian và theo node; một snapshot đơn lẻ ít khi giải thích được xu hướng.

### 16.3 Hot threads

Khi CPU cao hoặc một node có latency bất thường, có thể xem hot threads:

```http
GET /_nodes/hot_threads
```

Kết quả giúp nhận biết thread đang tiêu tốn CPU ở query execution, aggregation, indexing, merge hoặc GC. Hot threads là ảnh chụp ngắn tại thời điểm gọi, vì vậy nên thu thập khi sự cố đang diễn ra.

### 16.4 Tasks API

Xem các search task đang chạy:

```http
GET /_tasks?detailed=true&actions=*search
```

Tasks API giúp phát hiện request chạy lâu hoặc nhiều task đồng thời. Không phải mọi tác vụ đều hiển thị cùng mức chi tiết; kết hợp với slow log và client correlation ID.

## 17. Tái hiện query chậm một cách công bằng

Khi lấy query từ slow log hoặc query logging, tái hiện nó với các điều kiện càng gần thực tế càng tốt:

- Cùng cluster/index hoặc cùng mapping và data volume.
- Cùng alias target, routing và preference nếu có.
- Cùng query body, sort, aggregation và `track_total_hits`.
- Cùng page size, source filtering và highlighting.
- Cùng tenant/security filter.
- Cùng trạng thái cache và refresh/merge nếu đang điều tra hiệu ứng đó.

Nếu chỉ copy phần query mà bỏ sort, aggs, size, post_filter hoặc source fields, benchmark có thể không tái hiện đúng request chậm.

### 17.1 Chạy baseline không profile

Trước khi bật Profile:

1. Gửi query gốc một số lần trong môi trường an toàn.
2. Ghi `took`, client latency và số hits.
3. Quan sát nhiều lần thay vì chỉ một request.
4. Ghi lại điều kiện cache và concurrency.

Không dùng một request đầu tiên sau cold start để kết luận query luôn chậm. Segment warming, cache và filesystem cache có thể làm thời gian giữa các lần chạy khác nhau.

### 17.2 Bật profile cho một request đại diện

Thêm `profile: true` vào đúng query đã tái hiện. Đọc query tree và breakdown để tìm component tương đối tốn thời gian. Nếu request có nhiều shard, so sánh từng shard thay vì chỉ nhìn node đầu tiên.

### 17.3 Thay đổi một yếu tố mỗi lần

Thử lần lượt:

- Thay query clause hoặc chuyển điều kiện phù hợp sang filter.
- Giảm page size hoặc `track_total_hits`.
- Giảm source fields/highlighting.
- Tách hoặc đơn giản hóa aggregation.
- Thay deep pagination bằng `search_after`.
- Giảm fan-out bằng routing nếu mô hình dữ liệu hỗ trợ.

Giữ lại semantics nghiệp vụ. Một query nhanh hơn nhưng trả kết quả sai không phải là tối ưu thành công.

### 17.4 Đo lại không profile

Sau mỗi thay đổi:

1. Chạy query không có `profile`.
2. Đo nhiều lần với điều kiện tương đương.
3. So sánh median và tail latency (p95/p99) nếu có đủ mẫu.
4. Kiểm tra kết quả có tương đương nghiệp vụ không.
5. Theo dõi slow/query logs sau deploy.

Không so trực tiếp `time_in_nanos` của profile với `took` của query không profile. Profile instrument nội bộ làm tăng overhead và có thể vô hiệu hóa một số tối ưu Lucene.
## 18. Áp dụng trong ứng dụng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp repository abstraction và ElasticsearchOperations để tạo query. Khi slow log hoặc query logging đã xác định một request chậm, hãy tìm đúng call site trong ứng dụng và xác nhận request thực tế tương ứng với method nào.

### 18.1 Repository query method

Ví dụ:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Page<ProductDocument> findByActiveTrue(Pageable pageable);

    List<ProductDocument> findByCategoryAndActiveTrue(String category);
}
```

Query method giúp code ứng dụng ngắn, nhưng không làm query tự động rẻ. Kiểm tra mapping của field, page size, sort và cách Spring Data tạo query. Một method trả Page có thể cần total hits để tạo page metadata; nếu UI không cần tổng số chính xác, cân nhắc API trả Slice hoặc kết quả phù hợp hơn với nhu cầu.

### 18.2 NativeQuery và ElasticsearchOperations

Khi cần query DSL tùy biến:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("name")
            .query("wireless keyboard")
        ))
        .filter(f -> f.term(t -> t
            .field("active")
            .value(true)
        ))
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<ProductDocument> hits = operations.search(
    query,
    ProductDocument.class,
    IndexCoordinates.of("products-read")
);
```

Ghi lại query shape, index coordinates, pageable, sort, aggregation và source filtering khi tái hiện. Đừng chỉ lưu chuỗi người dùng nhập; các tùy chọn khác có thể quyết định phần lớn thời gian xử lý.

### 18.3 Gửi profile bằng Elasticsearch Java API Client

Nếu cần profile một request được tạo trong ứng dụng, có thể dùng Elasticsearch Java API Client trực tiếp (nếu client bean/dependency của phiên bản đang dùng được cấu hình):

```java
SearchResponse<ProductDocument> response = elasticsearchClient.search(
    search -> search
        .index("products-read")
        .profile(true)
        .query(query -> query.match(match -> match
            .field("name")
            .query("wireless keyboard")
        )),
    ProductDocument.class
);
```

Response chứa profile data theo API client version. Dùng đúng client generation và generated types của dependency dự án. Nếu chỉ cần phân tích một query, gọi REST trong Kibana Dev Tools thường đơn giản hơn việc thay đổi code production để bật profiling.

### 18.4 Gắn correlation ID bằng X-Opaque-Id

Để nối request log với một thao tác ở ứng dụng, gửi header X-Opaque-Id:

```http
GET /products-read/_search
X-Opaque-Id: catalog-search-req-8f31

{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
```

Slow log có thể ghi ID này vào trường correlation tương ứng. Trong ứng dụng, tạo ID không chứa thông tin cá nhân, ghi nó vào application log và truyền xuyên suốt các request cần điều tra. Cách cấu hình default headers/interceptors phụ thuộc Elasticsearch Java Client/transport version.

### 18.5 Không bật profile cho toàn bộ repository call

Không biến profiling thành hành vi mặc định của mọi repository request. Chỉ bật cho một request được chọn trong môi trường debug hoặc qua một đường điều tra có kiểm soát. Tắt lại sau khi lấy được profile.

## 19. Cách đọc một sự cố từ đầu đến cuối

Giả sử API tìm kiếm sản phẩm có p95 tăng từ 120 ms lên 1,2 s.

### Bước 1: Xác định latency nằm ở đâu

So sánh client latency với Elasticsearch took. Nếu client latency cao nhưng took thấp, kiểm tra gateway, connection pool, network, ứng dụng và xử lý response. Nếu cả hai tăng, tiếp tục ở Elasticsearch.

### Bước 2: Tìm request chậm

Dùng query logging nếu phiên bản hỗ trợ. Nếu không, cấu hình search slow log cho index liên quan với threshold có kiểm soát. Dùng correlation ID để nối log với endpoint/caller.

### Bước 3: Phân biệt query và fetch

Nếu query phase chậm, kiểm tra query clauses, shard và aggregation. Nếu fetch phase chậm, kiểm tra page size, source, highlighting và document size.

### Bước 4: Tái hiện query đầy đủ

Lấy body, sort, size, routing, filters, aggregation, source filtering và alias target. Dùng cùng dữ liệu hoặc môi trường có mapping/cardinality tương đương.

### Bước 5: Profile một request

Bật Profile API cho request đại diện. Đọc từng shard, query tree, child clauses, collector, fetch và aggregation. Đừng cộng timing parent-child hoặc coi profile là end-to-end latency.

### Bước 6: Kiểm tra cluster

Nếu profile không giải thích độ trễ, xem search thread pool queue/rejections, node CPU/heap/GC, disk I/O, merges, refresh và shard distribution. Profile không đo network, queue time hoặc coordinating-node reduce/merge đầy đủ.

### Bước 7: Thay đổi có kiểm soát

Thay một yếu tố mỗi lần và giữ semantics. Ví dụ giảm source payload, giới hạn total hits, thay pagination sâu, chuyển điều kiện sang filter hoặc điều chỉnh aggregation.

### Bước 8: Đo lại và xác nhận

Chạy query không profile, đo nhiều mẫu, kiểm tra p95/p99, xác nhận kết quả nghiệp vụ và theo dõi log sau deploy.

## 20. Các sai lầm thường gặp

### 20.1 Coi slow log là thời gian toàn request

Search slow log là shard-level và có thể ghi riêng query/fetch. Nó không bao gồm toàn bộ network, queue và thời gian xử lý ở ứng dụng. Với request-level duration, xem query logging nếu phiên bản hỗ trợ.

### 20.2 Coi Profile API là benchmark

Profiling thêm overhead và có thể tắt một số tối ưu nội bộ. Chỉ dùng để hiểu tương quan giữa query components, rồi đo lại không profile.

### 20.3 Cộng timing trong query tree

Parent timing có thể inclusive child timing. Cộng các node sẽ đếm trùng. So sánh đúng cấp và đọc breakdown.

### 20.4 Chỉ profile một shard

Search phân tán có thể có shard chậm bất thường. Xem tất cả profile shard entries và đối chiếu shard stats.

### 20.5 Bật slow log với threshold quá thấp

Log volume tăng có thể tạo thêm I/O và chi phí ingest/retention. Bắt đầu với ngưỡng cao, index cụ thể và cửa sổ điều tra ngắn.

### 20.6 Quên logger level và appender

Index threshold và node logging configuration là hai lớp khác nhau. Kiểm tra cả hai nếu không thấy log.

### 20.7 Dùng profile để tìm queue/network latency

Profile không đo network, queue time hoặc merge shard responses trên coordinating node. Xem client APM, query logging, thread pool và node stats.

### 20.8 Tối ưu query nhưng bỏ qua fetch

Query phase có thể nhanh nhưng trả payload lớn. Đọc fetch slow log và giảm source/highlighting/page size khi phù hợp.

### 20.9 Tối ưu theo một request hiếm gặp

Ưu tiên query có tần suất cao, p95/p99 lớn hoặc tổng chi phí đáng kể. Một request 5 giây chỉ chạy một lần mỗi ngày có thể ít quan trọng hơn request 300 ms chạy hàng nghìn lần mỗi phút.
## 21. Checklist điều tra truy vấn chậm

### Xác định tín hiệu

- [ ] Ghi nhận endpoint, thời điểm, p50/p95/p99 và client latency.
- [ ] So sánh Elasticsearch took với end-to-end latency.
- [ ] Xác định index/alias, shard và query type.
- [ ] Ghi correlation ID hoặc X-Opaque-Id nếu có.

### Thu thập request

- [ ] Dùng query logging nếu version hỗ trợ; nếu không, bật slow log có kiểm soát.
- [ ] Lưu query body đầy đủ, gồm sort, size, routing, filters và aggregations.
- [ ] Phân biệt query phase và fetch phase.
- [ ] Gom nhóm theo query shape và tần suất, không chỉ theo latency cao nhất.

### Phân tích

- [ ] Tái hiện query trên dữ liệu/mapping tương đương.
- [ ] Chạy baseline không profile.
- [ ] Bật Profile API cho request đại diện.
- [ ] Đọc từng shard, query tree, breakdown và collector.
- [ ] Kiểm tra fetch, source payload và aggregation.
- [ ] Xem thread pool, node stats, GC, disk, merges, refresh và shard skew khi cần.

### Khắc phục và xác nhận

- [ ] Thay đổi một yếu tố mỗi lần.
- [ ] Giữ semantics và quyền truy cập dữ liệu.
- [ ] Đo lại không profile với nhiều mẫu.
- [ ] So sánh p95/p99 và throughput dưới tải tương đương.
- [ ] Theo dõi query/slow logs sau deploy.
- [ ] Tắt logging/profiling tạm thời và đặt lại ngưỡng phù hợp.
- [ ] Xác nhận retention, quyền truy cập và redaction của log.

## 22. Nguyên tắc triển khai

- Dùng slow log để tìm search shard/phase và indexing operations vượt ngưỡng.
- Nhớ mọi slow log threshold mặc định là -1 và phải được cấu hình rõ ràng.
- Cấu hình query phase và fetch phase riêng; áp dụng settings vào đúng index.
- Phân biệt index threshold với logger level/appender trong node logging configuration.
- Chọn threshold theo latency objective và log volume; tránh bật ngưỡng thấp trên mọi index.
- Với phiên bản hỗ trợ, cân nhắc query logging để tìm request search chậm ở cấp Elasticsearch.
- Dùng Profile API cho một query đại diện để hiểu query tree, breakdown, collector, fetch và aggregation.
- Không dùng profile timings làm benchmark hoặc SLO.
- Không cộng parent/child timings hoặc shard timings một cách máy móc.
- Xem thread pool, node stats, hot threads và Tasks API khi độ trễ nằm ngoài query execution.
- Tái hiện query đầy đủ và thay đổi từng yếu tố một lần.
- Đo lại query không profile và theo dõi p95/p99 sau deploy.
- Dùng correlation ID không nhạy cảm để nối log với request ứng dụng.
- Giới hạn thời gian bật logging, bảo vệ query source và đặt retention phù hợp.

## 23. Tổng kết

Slow log và Profile API giải quyết hai câu hỏi khác nhau. Slow log ghi lại hoạt động vượt ngưỡng ở cấp shard đối với search và ở cấp document/indexing operation đối với indexing. Search slow log có thể tách query phase và fetch phase, giúp nhận biết shard hoặc giai đoạn nào chậm. Ngưỡng mặc định là -1, nên cần bật có chủ đích và đồng thời kiểm tra logger level/appender của node. Với các phiên bản Elasticsearch mới hỗ trợ query logging, đây là lựa chọn thống nhất để tìm request search chậm theo thời gian server đo; slow log vẫn cần cho indexing và phân tích shard/phase.

Profile API đi sâu vào cách một search request được thực thi: query tree, Lucene query nodes, breakdown, collector, fetch và aggregation. Nó tạo overhead đáng kể và không đo network latency, queue time, coordinating-node merge/reduce hoặc mọi công việc nền như xây global ordinals. Timing trong cây có thể inclusive child nên không cộng các giá trị một cách máy móc. Dùng profile để hiểu chi phí tương đối của query components, sau đó đo lại request không profile.

Một quy trình hiệu quả bắt đầu từ latency metrics và query/slow logs, tái hiện request đầy đủ, profile một mẫu, kiểm tra node/thread-pool khi cần, thay đổi từng yếu tố và đo lại dưới tải tương đương. Kết quả tối ưu phải giữ nguyên semantics tìm kiếm và được xác nhận bằng latency thực tế sau triển khai.

## Tài liệu tham khảo

- [Elasticsearch — Slow query and index logging](https://www.elastic.co/docs/deploy-manage/monitor/logging-configuration/slow-logs)
- [Elasticsearch — Slow log settings](https://www.elastic.co/docs/reference/elasticsearch/index-settings/slow-log)
- [Elasticsearch — Profile search requests](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-profile)
- [Elasticsearch — Tune for search speed](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/search-speed)
- [Elasticsearch — Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch — Nodes stats API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-nodes-stats)
- [Elasticsearch — Tasks API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-tasks-list)
- [Spring Data Elasticsearch Reference — Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
