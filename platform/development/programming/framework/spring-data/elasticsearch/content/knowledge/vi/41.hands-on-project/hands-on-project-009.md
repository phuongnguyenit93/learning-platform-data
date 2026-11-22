# Đổi mapping bằng reindex và chuyển alias

Mapping quyết định Elasticsearch lưu trữ, phân tích và truy vấn từng field như thế nào. Khi schema thay đổi, có những thuộc tính không thể sửa trực tiếp trên index đang chứa dữ liệu. Ví dụ, đổi field từ text sang keyword, thay analyzer, chuyển object thành nested hoặc bổ sung multi-field cho dữ liệu cũ đều cần một kế hoạch index lại phù hợp.

Quy trình phổ biến là tạo index mới với mapping và settings mong muốn, dùng Reindex API sao chép dữ liệu, xác minh index đích rồi chuyển alias từ index cũ sang index mới. Ứng dụng tiếp tục sử dụng alias ổn định, còn tên index vật lý được version hóa để hỗ trợ migration và rollback.

Reindex và alias switch chỉ là hai phần của quy trình. Một migration production còn phải xử lý các ghi mới phát sinh trong lúc sao chép, document lỗi mapping, routing, quyền truy cập, refresh, tính nhất quán, theo dõi task và dữ liệu ghi sau cutover. Bài này trình bày cách thực hiện toàn bộ quy trình trong ngữ cảnh Spring Data Elasticsearch.

## 1. Vì sao cần index mới khi đổi mapping?

Elasticsearch cho phép bổ sung field vào mapping hiện tại trong nhiều trường hợp. Tuy nhiên, nhiều thuộc tính đã quyết định cách dữ liệu được index không thể thay đổi tùy ý sau khi đã có document.

Các trường hợp thường cần tạo index mới:

- Đổi field type, ví dụ text thành keyword, keyword thành long hoặc object thành nested.
- Thay analyzer hoặc tokenizer của text field.
- Bổ sung multi-field và cần dữ liệu cũ có term/doc values cho field con.
- Thay đổi cấu trúc object, nested hoặc flattened.
- Thay đổi index settings cần được áp dụng khi tạo index.
- Thay đổi cách lưu vector hoặc số chiều dense_vector.
- Chuẩn hóa lại dữ liệu, đổi tên field hoặc chuyển schema.
- Thay đổi một thuộc tính mapping không hỗ trợ update trực tiếp trên field đã tồn tại.

Ví dụ mapping cũ:

~~~json
{
  "properties": {
    "status": {
      "type": "text"
    }
  }
}
~~~

Ứng dụng cần lọc chính xác, sort và aggregation theo trạng thái. Mapping mới muốn dùng keyword:

~~~json
{
  "properties": {
    "status": {
      "type": "keyword"
    }
  }
}
~~~

Không thể chỉ đổi type trên index đang chứa document và mong Elasticsearch tự xây lại cấu trúc cho dữ liệu cũ. Hãy tạo index mới, ghi lại document theo mapping mới rồi chuyển traffic.

### 1.1. Thêm multi-field cũng cần backfill

Một trường hợp dễ nhầm là bổ sung status.keyword cho field status đang là text:

~~~json
{
  "properties": {
    "status": {
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

Elasticsearch có thể cho phép thêm multi-field vào mapping, nhưng document đã index trước đó không tự động được phân tích lại để tạo term và doc values cho field con. Nếu cần sort hoặc aggregation trên toàn bộ dữ liệu cũ, phải reindex hoặc cập nhật lại document.

Reindex sang index mới giúp thay đổi schema được review, kiểm thử và rollback rõ ràng hơn.

## 2. Alias giúp ứng dụng không phụ thuộc tên index vật lý

Alias là tên logic trỏ tới một hoặc nhiều index. Ứng dụng có thể dùng alias như endpoint ổn định:

~~~text
products-v1  <--- products
~~~

Sau khi tạo index mới và cutover:

~~~text
products-v1
products-v2  <--- products
~~~

Code ứng dụng tiếp tục gọi products. Việc chuyển từ products-v1 sang products-v2 được thực hiện ở Elasticsearch cluster.

Alias có thể dùng cho:

- Read alias: đọc dữ liệu từ index được trỏ tới.
- Write alias: xác định index nhận thao tác ghi.
- Filter alias: chỉ hiển thị một tập document phù hợp.
- Routing alias: định tuyến request tới shard phù hợp.
- Điểm chuyển đổi giữa các phiên bản index.

### 2.1. Đặt tên index theo version

Một quy ước đơn giản:

~~~text
products-v1
products-v2
products-v3
products       (alias ổn định)
~~~

Không dùng cùng một tên cho alias và index vật lý. Giữ index có version riêng và alias không đổi. Cách này cho phép tạo index kế tiếp trong khi index hiện tại vẫn phục vụ traffic, đồng thời giữ index cũ để rollback.

### 2.2. Read alias và write alias

Nếu alias chỉ trỏ tới một index, Elasticsearch có thể dùng alias đó cho đọc và ghi. Khi alias trỏ tới nhiều index, thao tác ghi cần biết index nào là write index. Có thể đặt is_write_index trên một index.

Mô hình tách alias:

~~~text
products-read  -> products-v2
products-write -> products-v2 (is_write_index)
~~~

Tách read/write alias hữu ích khi cần nhiều index đọc hoặc muốn kiểm soát ghi riêng. Với ứng dụng đơn giản, một alias có thể đủ nếu chỉ trỏ tới một index.

Alias không phải cơ chế dual-write. Alias trỏ tới nhiều index không có nghĩa một write sẽ tự được nhân bản sang tất cả index.

## 3. Kiểm kê trước khi migration

Trước khi tạo index mới, xác định trạng thái hiện tại và mọi thành phần phụ thuộc.

Cần ghi nhận:

- Tên index vật lý hiện tại.
- Alias đọc/ghi và các thuộc tính filter/routing.
- Mapping và settings hiện tại.
- Số document, dung lượng, shard và replica.
- Analyzer, normalizer, ingest pipeline và index template.
- Các query, sort, aggregation và repository dùng field nào.
- Những ứng dụng hoặc batch job ghi trực tiếp vào index vật lý.
- Chính sách refresh và retention.
- Tốc độ ghi trong lúc migration.
- Cửa sổ downtime có thể chấp nhận.
- Snapshot/backup và kế hoạch rollback.

Kiểm tra alias:

~~~http
GET _cat/aliases?v
~~~

Xem mapping và settings:

~~~http
GET products-v1/_mapping
GET products-v1/_settings
~~~

Xem số document và trạng thái index:

~~~http
GET products-v1/_count
GET _cat/indices/products-v1?v
~~~

Nếu một service vẫn ghi trực tiếp vào products-v1 sau cutover, dữ liệu mới có thể không xuất hiện trong index đang hoạt động. Cần chuyển tất cả writer sang alias hoặc phối hợp với migration job.

### 3.1. Lập kế hoạch rollback trước

Trước khi bắt đầu, xác định:

- Khi nào được phép rollback.
- Có tiếp tục ghi vào index mới sau cutover không.
- Nếu rollback, các write mới sẽ được replay thế nào.
- Có durable event log/outbox để khôi phục không.
- Khi nào index cũ được phép xóa.

Rollback alias không tự đồng bộ dữ liệu ghi vào index mới trở lại index cũ. Chuyển alias ngược có thể làm ứng dụng nhìn thấy dữ liệu cũ nếu chưa reconcile các write phát sinh sau cutover.

## 4. Tạo index mới với mapping và settings hoàn chỉnh

Tạo index đích với đầy đủ settings và mapping đã được review. Không tạo index bằng schema mặc định rồi để application tự suy luận trong lúc ingest.

Ví dụ:

~~~http
PUT products-v2
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "status": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      },
      "priceInCents": {
        "type": "long"
      },
      "createdAt": {
        "type": "date"
      },
      "active": {
        "type": "boolean"
      }
    }
  }
}
~~~

Số shard/replica trong ví dụ chỉ mang tính minh họa. Chọn theo kích thước dữ liệu, số node, workload và chính sách cluster.

### 4.1. Xác nhận mapping trước khi reindex

Đọc lại mapping và settings sau khi tạo:

~~~http
GET products-v2/_mapping
GET products-v2/_settings
~~~

Xác nhận:

- Field type đúng.
- Analyzer và normalizer đã tồn tại.
- Multi-field có đúng tên.
- Dynamic mapping policy đúng.
- Date format tương thích dữ liệu nguồn.
- Numeric type đủ miền giá trị.
- Object/nested structure đúng.
- Dense vector có đúng dimensions và similarity nếu sử dụng.
- Shard/replica phù hợp.

Nếu mapping sai, tạo lại index mới khi nó còn rỗng. Không tiếp tục reindex vào schema chưa được xác nhận.

### 4.2. Index template

Nếu index được tạo theo quy ước version hoặc rollover, có thể quản lý schema bằng index template. Kiểm tra template đã được áp dụng trước khi reindex:

~~~http
GET _index_template/products-template
~~~

Template giúp các index mới có cùng schema. Nó không tự sửa mapping của index đã tồn tại và không thay thế việc kiểm tra index đích.

## 5. Reindex API sao chép dữ liệu như thế nào?

Reindex API đọc document từ source index và index chúng vào destination index. Mặc định, Elasticsearch giữ document ID của source.

Ví dụ:

~~~http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Mapping mới được áp dụng khi document được ghi vào index đích. Reindex không tự hiểu mọi quy tắc chuyển đổi nghiệp vụ. Nếu field cũ chứa dữ liệu không tương thích mapping mới, document có thể thất bại hoặc cần transform.

### 5.1. Giữ document ID và routing

Mặc định Reindex giữ _id. Điều này quan trọng nếu ứng dụng đọc document bằng cùng identifier.

Nếu source dùng custom routing, phải bảo đảm destination giữ routing phù hợp. Mất routing có thể khiến document nằm ở shard khác, làm các query chỉ định routing không tìm thấy dữ liệu hoặc thay đổi hiệu năng. Kiểm tra routing contract và tùy chọn routing của Reindex API theo phiên bản.

Nếu cần đổi ID, hãy kiểm tra collision và tính duy nhất. Không tạo ID ngẫu nhiên mới cho mỗi lần chạy lại vì có thể tạo duplicate.

### 5.2. Dùng script để chuyển đổi source

Ví dụ status cũ có chữ hoa/thường lẫn lộn và cần chuẩn hóa:

~~~http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  },
  "script": {
    "lang": "painless",
    "source": """
      if (ctx._source.status != null) {
        ctx._source.status = ctx._source.status.toLowerCase();
      }
    """
  }
}
~~~

Script chỉ nên thực hiện transform có quy tắc rõ và có thể kiểm thử. Với chuyển đổi phức tạp, có thể dùng ingest pipeline hoặc ETL ở application.

### 5.3. Xử lý dữ liệu không hợp lệ

Nếu mapping mới yêu cầu priceInCents là long nhưng source có chuỗi không phải số, reindex có thể báo lỗi ở document đó.

Các lựa chọn:

- Làm sạch dữ liệu nguồn trước.
- Dùng script chuyển đổi theo quy tắc nghiệp vụ.
- Đưa document lỗi vào quarantine để sửa sau.
- Điều chỉnh mapping nếu dữ liệu thực tế có nhiều dạng hợp lệ.
- Báo cáo số lượng item thất bại và xử lý trước cutover.

Không âm thầm thay giá trị lỗi thành 0 nếu 0 có ý nghĩa nghiệp vụ. Mọi transform cần có quy tắc, log và khả năng audit.

## 6. Chạy reindex bất đồng bộ và theo dõi task

Với index lớn, reindex có thể mất nhiều thời gian. Dùng wait_for_completion=false để chạy bất đồng bộ:

~~~http
POST _reindex?wait_for_completion=false
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Response trả task ID. Theo dõi task:

~~~http
GET _tasks/<task_id>
~~~

Liệt kê reindex task:

~~~http
GET _tasks?detailed=true&actions=*reindex
~~~

Task response có thể cho biết tổng document, số created/updated, batch count, version conflicts, noops, failures và thời gian bị throttle. Tên field và cấu trúc cụ thể tùy Elasticsearch version; hãy đọc response thực tế.

Lưu task ID để có thể giám sát, điều tra hoặc cancel khi cần. Cancel task không rollback các document đã được ghi.

### 6.1. Slicing và throttling

Reindex hỗ trợ slicing để chia công việc và xử lý song song. Tăng slices có thể tăng throughput nhưng cũng làm tăng tải lên cluster.

Có thể điều chỉnh requests_per_second để throttle. Đo CPU, I/O, indexing pressure, merge và search latency khi chọn mức tải. Không chạy reindex với concurrency tối đa trên cluster production đang có search/ingest traffic mà chưa có capacity plan.

## 7. Reindex không tự bắt kịp các ghi mới

Đây là vấn đề quan trọng nhất khi reindex index đang có traffic.

Reindex đọc dữ liệu source trong quá trình chạy. Document được tạo hoặc cập nhật sau khi quá trình đọc đã đi qua document đó có thể không được phản ánh trong destination.

Ví dụ:

~~~text
T0: products-v1 có 1,000,000 documents
T1: bắt đầu reindex sang products-v2
T2: ứng dụng update product P-100
T3: reindex đã đọc P-100 trước lần update
T4: reindex hoàn tất
~~~

products-v2 có thể chứa phiên bản cũ của P-100. Reindex không phải CDC và không tự theo dõi mọi thay đổi sau thời điểm bắt đầu.

Cần một chiến lược đồng bộ writes trong suốt migration.

## 8. Chiến lược migration khi ứng dụng vẫn tiếp tục ghi

Có ba chiến lược thường gặp. Chọn theo khả năng chấp nhận downtime và độ phức tạp.

### 8.1. Dừng ghi trong cửa sổ migration

Quy trình:

1. Tạm dừng tất cả writer và consumer.
2. Chờ request/batch đang chạy hoàn tất.
3. Chạy reindex source sang destination.
4. Kiểm tra dữ liệu và query.
5. Chuyển alias.
6. Khởi động writer qua alias mới.

Ưu điểm là dễ hiểu và không cần dual-write hoặc replay. Nhược điểm là có downtime ghi trong thời gian reindex. Phù hợp với hệ thống có cửa sổ bảo trì.

### 8.2. Dual-write trong thời gian chuyển đổi

Ứng dụng ghi đồng thời vào index cũ và mới:

~~~text
Application write
       |
       +------> products-v1
       |
       +------> products-v2
~~~

Dual-write cần bật trước hoặc cùng lúc với reindex, nhưng phải xử lý race khi reindex ghi dữ liệu cũ đè lên write mới ở destination.

Một quy trình khả thi:

1. Bật dual-write với source version hoặc sequence guard.
2. Bắt đầu reindex.
3. Đảm bảo reindex không ghi đè bản mới hơn đã dual-write.
4. Theo dõi lỗi của cả hai đích.
5. Chờ reindex hoàn tất.
6. Reconcile document có version khác nhau.
7. Chuyển alias.
8. Tắt dual-write sau khi xác nhận.

Hai lần ghi không phải transaction. Một index có thể thành công trong khi index kia thất bại. Cần retry và reconciliation riêng cho từng đích.

### 8.3. Outbox/CDC và replay thay đổi

Một cách linh hoạt hơn là lưu mọi thay đổi vào outbox hoặc change stream có thứ tự:

~~~text
Database/source of truth
       |
       +----> products-v1
       |
       +----> durable change log
                       |
                       v
                 replay worker
                       |
                       v
                   products-v2
~~~

Quy trình:

1. Ghi nhận checkpoint/sequence của change log.
2. Bắt đầu reindex snapshot hiện tại.
3. Trong lúc reindex, tiếp tục ghi change event vào durable log.
4. Sau khi reindex hoàn tất, replay event từ checkpoint theo thứ tự.
5. Chờ destination bắt kịp watermark đã xác định.
6. Chuyển alias.
7. Tiếp tục consumer trên destination mới.

Cần xử lý duplicate, ordering, delete event và event đến trễ. Dùng event ID/document version để áp dụng idempotent và từ chối event cũ.

Không chỉ dựa vào timestamp nếu nguồn có sequence/offset đáng tin cậy. Checkpoint phải có semantics rõ về thứ tự và tính đầy đủ.

## 9. Version guard để tránh ghi cũ đè dữ liệu mới

Nếu document có sourceVersion tăng đơn điệu, destination cần một write strategy có kiểm tra version.

Ví dụ document:

~~~json
{
  "productId": "P-100",
  "sourceVersion": 42,
  "name": "Wireless Mouse"
}
~~~

Mỗi write cần mang version và chỉ áp dụng nếu version mới hơn version đang có. Có thể dùng external versioning hoặc script/update condition phù hợp với API/version.

Lưu ý:

- Reindex có thể giữ Elasticsearch internal version theo semantics riêng; điều đó không tự tương đương sourceVersion của database.
- External versioning phải được cấu hình đúng API.
- Script kiểm tra sourceVersion cần xử lý cả trường hợp document chưa tồn tại.
- Delete cần tombstone/version để event cũ không tạo lại document đã xóa.
- Nếu version không tăng đơn điệu, cần cơ chế ordering khác.

Không giả định Reindex API tự dùng field sourceVersion làm external version. Kiểm tra request cụ thể hoặc để replay worker áp dụng source version theo contract của hệ thống.

## 10. Xác minh dữ liệu trước khi cutover

Task completed không đủ để chứng minh index mới đúng. Cần kiểm tra dữ liệu và behavior của ứng dụng.

Checklist xác minh:

1. So sánh document count.
2. So sánh số lượng theo tenant/status/category.
3. Kiểm tra sample document theo ID.
4. Kiểm tra field null/missing.
5. Kiểm tra routing.
6. Kiểm tra mapping và field capabilities.
7. Chạy query quan trọng trên index cũ và mới.
8. Chạy sort, aggregation, nested, script và kNN nếu có.
9. Kiểm tra ACL/filter.
10. Đo latency và resource usage.
11. Xử lý mọi reindex failure.
12. Xác nhận destination đã bắt kịp watermark của change log.

### 10.1. So sánh count

~~~http
GET products-v1/_count
GET products-v2/_count
~~~

Count bằng nhau là tín hiệu hữu ích nhưng không chứng minh nội dung giống nhau. Có thể một số document bị lỗi trong khi document khác bị duplicate và tổng count vẫn bằng.

### 10.2. Kiểm tra document mẫu

~~~http
GET products-v1/_doc/P-100
GET products-v2/_doc/P-100
~~~

So sánh source, routing và metadata. Nếu mapping mới chuẩn hóa status, khác biệt có thể là chủ đích; đối chiếu với quy tắc transform.

### 10.3. Kiểm tra field capabilities

~~~http
POST products-v2/_field_caps?fields=status,name,name.keyword,priceInCents,createdAt
~~~

Field capabilities giúp xác nhận field type và khả năng search/aggregate. Nếu alias đọc nhiều index, kiểm tra trên alias để phát hiện mapping conflict.

## 11. Chuyển alias bằng một thao tác atomic

Khi index mới sẵn sàng, dùng Aliases API để remove alias khỏi index cũ và add vào index mới trong cùng một request.

~~~http
POST _aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Elasticsearch áp dụng actions trong một cập nhật cluster state. Client quan sát alias trước hoặc sau lần cập nhật, tránh khoảng thời gian alias bị tháo rời do hai request riêng.

Không thực hiện DELETE alias khỏi index cũ rồi sau đó mới ADD alias vào index mới bằng hai request riêng. Khoảng giữa hai request có thể làm ứng dụng không tìm thấy alias.

### 11.1. Nếu có read alias và write alias riêng

Chuyển cả hai trong cùng request:

~~~http
POST _aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-write"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Nếu alias có filter, routing, hidden hoặc thuộc tính khác, khai báo lại chính xác khi add. Không giả định mọi thuộc tính sẽ được chuyển theo ý muốn nếu request không nêu rõ.

### 11.2. Kiểm tra alias sau cutover

~~~http
GET _cat/aliases/products?v
GET _alias/products
~~~

Xác nhận alias trỏ đúng index, write index đúng, filter/routing đúng, không còn index cũ trong alias ngoài dự kiến và ứng dụng đang dùng alias thay vì physical index.

## 12. Cutover và write traffic

Atomic alias switch không tự làm mọi request đang chạy trở nên nguyên tử với việc đổi index. Một write bắt đầu trước cutover có thể đã resolve tới index cũ và hoàn tất sau khi alias được chuyển.

Một quy trình kiểm soát:

- Dừng hoặc flush writer trong vài giây nếu có thể.
- Chờ bulk in-flight hoàn tất.
- Chốt change log watermark.
- Replay tới watermark trước switch.
- Chuyển alias.
- Xác nhận write mới đi vào index mới.
- Tiếp tục consumer và theo dõi lag.

Nếu hệ thống chấp nhận eventual consistency, có thể cho phép một khoảng ngắn dữ liệu chưa đồng nhất, nhưng cần reconciliation và hiểu tác động tới người dùng.

Không tuyên bố zero downtime chỉ vì alias switch atomic. Zero downtime phụ thuộc vào đồng bộ writes, client retry và query behavior trong suốt cutover.

## 13. Rollback nếu index mới có vấn đề

Nếu phát hiện lỗi sau cutover, có thể chuyển alias về index cũ bằng một Aliases API request:

~~~http
POST _aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v2",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v1",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Nhưng nếu ứng dụng đã ghi vào products-v2 sau cutover, rollback alias sẽ làm các write đó không còn được nhìn thấy qua alias cũ.

Trước khi rollback, cần quyết định:

- Có thể bỏ các write sau cutover không?
- Có thể replay chúng vào v1 không?
- Có durable outbox/change log không?
- Có thể reindex v2 về index rollback mới không?
- Có cần dừng ghi để reconcile không?

Rollback là một quy trình dữ liệu, không chỉ là thao tác đổi alias. Giữ v1 nguyên trạng và không xóa trong rollback window.

## 14. Spring Data Elasticsearch: quản lý index bằng IndexOperations

Spring Data Elasticsearch cung cấp IndexOperations để thao tác index, mapping và alias ở mức Spring Data.

Lấy operations cho index cụ thể:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

Tạo index nếu chưa tồn tại:

~~~java
if (!indexOperations.exists()) {
    indexOperations.create();
}
~~~

Đọc mapping:

~~~java
Map<String, Object> mapping = indexOperations.getMapping();
~~~

Tạo index và mapping từ entity:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping(
        indexOperations.createMapping()
    );
}
~~~

Tên method, kiểu trả về và cách tạo mapping phụ thuộc Spring Data Elasticsearch version. Với settings/mapping phức tạp, có thể quản lý JSON hoặc IndexSettings riêng và gọi API phù hợp.

Không gọi create mù quáng mỗi lần application start nếu index đã tồn tại với mapping cũ. Production schema cần một workflow migration được kiểm soát.

### 14.1. Entity nên dùng alias ổn định

Nếu repository/template thao tác trên index theo @Document(indexName = "products"), giá trị products có thể là alias:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    @Id
    private String productId;
}
~~~

Khi alias chuyển từ products-v1 sang products-v2, code tiếp tục dùng products.

Kiểm tra mọi cấu hình repository và custom query có hard-code physical index. Một chỗ dùng products-v1 có thể tiếp tục đọc/ghi index cũ sau cutover.

### 14.2. Kiểm soát auto index creation

Nếu Spring Data tự tạo index từ entity, mapping sinh ra phải khớp mapping đã provision. Với migration được quản lý bằng script hoặc deployment pipeline, bảo đảm application không ghi trước khi index và mapping được tạo.

Có thể cấu hình lifecycle để ứng dụng không tự tạo schema production, tùy version và cấu hình. Điều quan trọng là có một nguồn quản lý schema duy nhất và xác nhận mapping thực tế trên cluster.

## 15. Chuyển alias bằng Elasticsearch Java API Client

Trong Spring Data 5.x, có thể dùng Elasticsearch Java API Client trực tiếp cho Aliases API.

Ví dụ minh họa:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;

elasticsearchClient.indices().updateAliases(a -> a
    .actions(action -> action
        .remove(r -> r
            .index("products-v1")
            .alias("products")
        )
    )
    .actions(action -> action
        .add(add -> add
            .index("products-v2")
            .alias("products")
            .isWriteIndex(true)
        )
    )
);
~~~

Builder API và cách thêm nhiều action phụ thuộc client version. Có thể tạo một danh sách AliasAction rồi truyền một lần vào updateAliases để giữ tất cả thay đổi trong cùng request.

Không gửi remove và add bằng hai request riêng. Nếu dùng low-level REST client, gửi một POST _aliases với cả hai actions trong cùng body.

Một số version Spring Data cung cấp AliasActions/IndexOperations alias APIs. Kiểm tra Javadoc đúng version. Nếu abstraction không biểu diễn được filter/routing/is_write_index cần thiết, dùng Java API Client adapter riêng.

Giữ cutover logic trong migration component hoặc deployment job, không rải alias switching vào business service.

## 16. Reindex với alias và write index

Một quy trình tổng quát:

~~~text
Before:
  products (alias) -> products-v1

Create:
  products-v2 (new mapping)

Copy:
  products-v1 --_reindex--> products-v2

Validate:
  compare count, sample, queries, mapping

Cutover:
  products (alias) -> products-v2

After:
  products-v1 (retained for rollback)
  products-v2 (active)
~~~

Không tạo alias production products trỏ đồng thời tới v1 và v2 cho cùng tập document nếu query không có generation filter. Điều đó có thể làm duplicate hits, count sai hoặc aggregation cộng đôi.

Nếu cần dual-read/shadow-read để validation, gọi trực tiếp từng index hoặc dùng alias riêng. Không biến alias production thành alias đọc cả hai index chỉ để thử nghiệm.

## 17. Các lỗi thường gặp khi reindex

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Reindex thất bại một số document | Dữ liệu không tương thích mapping mới | Đọc failures, sửa transform/dữ liệu và replay |
| Count đích thấp hơn nguồn | Item lỗi, source query lọc hoặc task chưa xong | Kiểm tra task response và count |
| Document mới bị mất | Write phát sinh sau snapshot reindex | Dual-write, outbox/CDC hoặc pause writes |
| Bản mới bị ghi đè bởi bản cũ | Reindex và dual-write race | Version guard và reconcile |
| Sort/aggregation mới thiếu dữ liệu cũ | Multi-field chưa backfill | Reindex/update by query |
| Alias không có write target | Thiếu is_write_index khi alias trỏ nhiều index | Đặt write index rõ |
| Ứng dụng ghi vào index cũ | Hard-code physical index | Chuyển cấu hình sang alias |
| Cutover tạo lỗi tạm thời | Remove/add alias bằng hai request | Dùng một updateAliases request |
| Rollback làm mất write mới | Chuyển alias về index cũ mà không replay | Reconcile hoặc replay change log |
| Routing query không tìm thấy document | Reindex không giữ routing | Bảo toàn routing |
| Reindex quá tải cluster | Quá nhiều slices/concurrency | Throttle và chạy theo cửa sổ tải |
| Mapping mới tự phát sinh field | Dynamic mapping chưa kiểm soát | Explicit mapping/dynamic templates |
| Index mới có analyzer sai | Settings không được tạo đúng | Tạo lại index trước reindex |
| Alias đọc v1 và v2 gây duplicate | Cùng document xuất hiện ở cả hai | Chỉ trỏ active generation hoặc dùng filter |
| Application tự tạo mapping khác | Lifecycle auto-create không thống nhất | Chỉ định nguồn quản lý schema |

## 18. Checklist trước, trong và sau cutover

### Trước migration

- [ ] Xác nhận index hiện tại và alias.
- [ ] Xác định tất cả writer/reader.
- [ ] Lưu mapping/settings và snapshot theo chính sách.
- [ ] Thiết kế mapping/settings đích.
- [ ] Tạo index version mới.
- [ ] Kiểm tra analyzer, field type và templates.
- [ ] Chọn chiến lược pause, dual-write hoặc outbox/CDC.
- [ ] Chuẩn bị rollback và replay.

### Trong reindex

- [ ] Lưu task ID.
- [ ] Theo dõi progress, failures và throttling.
- [ ] Giám sát CPU, heap, disk và indexing pressure.
- [ ] Bảo đảm writes mới được capture.
- [ ] Kiểm tra version/routing.
- [ ] Xử lý item lỗi và chạy lại có kiểm soát.

### Trước cutover

- [ ] Count và sample document phù hợp.
- [ ] Không còn failure chưa xử lý.
- [ ] Change log đã catch up tới watermark.
- [ ] Query/filter/sort/aggregation hoạt động.
- [ ] ACL/tenant/routing đúng.
- [ ] Read/write alias actions đã được chuẩn bị.
- [ ] Writer đang ở trạng thái an toàn cho cutover.

### Sau cutover

- [ ] Xác nhận alias trỏ index mới.
- [ ] Xác nhận is_write_index.
- [ ] Kiểm tra đọc và ghi qua alias.
- [ ] Theo dõi lỗi, latency và indexing rate.
- [ ] Đối chiếu source/index version.
- [ ] Giữ index cũ trong rollback window.
- [ ] Chỉ xóa index cũ sau khi xác nhận retention và rollback policy.

## 19. Ví dụ quy trình hoàn chỉnh bằng REST API

Các bước dưới đây minh họa migration đơn giản khi có thể tạm dừng writes. Hệ thống không thể dừng writes cần bổ sung dual-write hoặc outbox/CDC.

### Bước 1: Xác nhận alias hiện tại

~~~http
GET _alias/products
~~~

Giả sử alias products đang trỏ tới products-v1.

### Bước 2: Tạo index mới

~~~http
PUT products-v2
{
  "mappings": {
    "properties": {
      "productId": { "type": "keyword" },
      "name": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword" }
        }
      },
      "status": { "type": "keyword" },
      "priceInCents": { "type": "long" }
    }
  }
}
~~~

### Bước 3: Chạy reindex

~~~http
POST _reindex?wait_for_completion=true
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Đọc response và xác nhận failures rỗng, số created/updated hợp lý.

### Bước 4: Kiểm tra dữ liệu

~~~http
GET products-v1/_count
GET products-v2/_count
GET products-v2/_mapping
~~~

Chạy query thực tế và kiểm tra document mẫu.

### Bước 5: Chuyển alias atomic

~~~http
POST _aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

### Bước 6: Xác nhận read/write

~~~http
GET _alias/products
GET products/_search
~~~

Kiểm tra qua ứng dụng rằng read/write đều đi qua alias mới. Không ghi dữ liệu giả vào production chỉ để kiểm tra nếu chưa có quy trình cleanup.

### Bước 7: Giữ index cũ

Giữ products-v1 trong rollback window. Chỉ xóa sau khi xác nhận traffic, dữ liệu, backup và retention policy.

## 20. Vận hành migration trong Spring Data Elasticsearch

Tách migration thành deployment step hoặc job riêng:

- Schema definition: mapping/settings theo version.
- Index provisioner: tạo index đích và xác minh schema.
- Reindex runner: bắt đầu và theo dõi reindex.
- Data validator: kiểm tra count, sample và query.
- Alias switcher: thực hiện một Aliases API update atomic.
- Cleanup job: xóa index cũ sau rollback window.

Business service chỉ dùng alias ổn định. Không để mỗi application instance tự quyết định thời điểm chuyển alias khi deploy nhiều replica.

Cấu hình có thể chứa alias ổn định:

~~~yaml
app:
  elasticsearch:
    read-alias: products
    write-alias: products
~~~

Nếu alias là nguồn sự thật cho active index, tránh lưu một cấu hình active-index khác có thể lệch với alias. Runtime service thường chỉ cần alias; migration job mới cần biết tên index vật lý.

### 20.1. Tách quyền runtime và migration

Ứng dụng runtime thường chỉ cần quyền đọc/ghi alias và index được phép. Migration job cần quyền tạo index, reindex, update alias và có thể xóa index sau này.

Tách role runtime khỏi role migration giúp tránh service thông thường có quyền xóa index hoặc đổi alias ngoài ý muốn. Không cấp quyền delete index cho mọi application instance chỉ vì chúng cần CRUD.

## 21. Khi nào dùng data stream thay alias?

Data stream phù hợp với dữ liệu append-only/time-series như logs, metrics hoặc events. Write thường đi vào backing index hiện tại và rollover tạo backing index mới.

Với dữ liệu entity có update/delete theo ID, alias trỏ tới versioned index thường dễ hiểu hơn. Data stream có quy tắc riêng về write index, backing indices và update/delete; không thay thế alias migration một cách cơ học.

Nếu hệ thống đang dùng data stream, kiểm tra API migration và template/rollover policy tương ứng. Bài này tập trung vào alias trên regular indices.

## 22. Bảng tra cứu nhanh

| Nhu cầu | Cách làm |
|---|---|
| Đổi field type | Tạo index mới và reindex |
| Đổi analyzer/settings | Tạo index mới với settings đích |
| Thêm multi-field cho dữ liệu cũ | Reindex hoặc update by query |
| Giữ tên index ổn định | Dùng alias |
| Sao chép dữ liệu | Reindex API |
| Theo dõi reindex dài | wait_for_completion=false và Tasks API |
| Giảm tải reindex | Slices/throttling theo khả năng cluster |
| Bắt kịp writes mới | Pause writes, dual-write hoặc outbox/CDC |
| Tránh event cũ ghi đè | Source version và version guard |
| Chuyển alias không có khoảng trống | Một Aliases API request gồm remove + add |
| Alias trỏ nhiều index | Đặt is_write_index rõ |
| Kiểm tra dữ liệu | Count, sample, field caps và query regression |
| Rollback | Chuyển alias lại sau khi reconcile writes |
| Giữ schema nhất quán | Index templates và versioned mappings |
| Spring Data index management | IndexOperations và migration component |
| Xóa index cũ | Sau rollback window và xác nhận retention |

Đổi mapping bằng reindex và chuyển alias là quy trình migration schema có kiểm soát. Tạo index version mới với settings/mapping hoàn chỉnh, reindex dữ liệu, xử lý transform và failures, đồng bộ các writes phát sinh trong lúc copy, rồi xác minh count, sample, query và field capabilities. Chuyển read/write alias trong một Aliases API request để thay đổi đích atomic ở cấp cluster state. Alias giúp ứng dụng giữ tên ổn định, nhưng không tự dual-write, bắt kịp thay đổi hoặc bảo vệ rollback. Hãy dùng source version, outbox/CDC hoặc cửa sổ dừng ghi phù hợp; giữ index cũ cho rollback và chỉ xóa sau khi dữ liệu, traffic và chính sách retention đã được xác nhận.
