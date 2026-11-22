# Rollover và quản lý index theo thời gian

Khi dữ liệu Elasticsearch tăng liên tục, việc ghi mọi document vào một index duy nhất có thể làm index ngày càng lớn, shard khó quản lý và chính sách lưu trữ trở nên phức tạp. Với dữ liệu có vòng đời theo thời gian như log, sự kiện, lịch sử truy cập hoặc telemetry, có thể chia dữ liệu thành nhiều index theo thế hệ hoặc theo khoảng thời gian, sau đó dùng alias, rollover và lifecycle policy để quản lý việc ghi, đọc, lưu trữ và xóa dữ liệu.

Rollover tạo một index mới khi index hiện tại đạt điều kiện như tuổi, số document hoặc dung lượng shard. Alias giúp ứng dụng ghi vào một tên ổn định mà không phải biết index vật lý hiện tại. Index Lifecycle Management (ILM) có thể tự động rollover và chuyển index qua các giai đoạn lưu trữ, cuối cùng xóa dữ liệu hết hạn.

## 1. Vì sao cần quản lý index theo thời gian?

Nhiều hệ thống có dữ liệu tăng theo thời gian và phần lớn chỉ ghi thêm document mới:

- Log ứng dụng và log truy cập.
- Sự kiện nghiệp vụ, audit trail và lịch sử thao tác.
- Dữ liệu cảm biến, metrics và telemetry.
- Lịch sử tìm kiếm, clickstream hoặc hoạt động người dùng.
- Sự kiện giao dịch đã hoàn tất cần lưu để tra cứu.

Nếu mọi dữ liệu nằm trong một index, index có thể tăng rất lớn và khó áp dụng chính sách lưu trữ khác nhau cho dữ liệu mới/cũ. Chia thành các index nhỏ hơn giúp giới hạn kích thước từng index, thuận tiện xóa theo thời hạn và có thể đặt cấu hình shard/replica khác nhau theo giai đoạn.

Ví dụ tên index theo thế hệ:

```text
events-000001
events-000002
events-000003
events-000004
```

Mỗi index chứa một khoảng dữ liệu. Ứng dụng dùng alias như `events-write` để gửi dữ liệu mới; quy trình đọc có thể dùng alias đọc hoặc pattern `events-*` để truy vấn nhiều thế hệ.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
|---|---|
| Index vật lý | Index Elasticsearch thực sự lưu document, ví dụ `events-000001` |
| Alias | Tên logic trỏ tới một hoặc nhiều index, ví dụ `events-write` hoặc `events-read` |
| Write index | Index nhận thao tác ghi khi alias trỏ tới nhiều index; được đánh dấu `is_write_index` |
| Rollover | Tạo index thế hệ mới và cập nhật alias ghi sang index mới |
| Index template | Mẫu settings, mapping và alias được áp dụng khi tạo index khớp pattern |
| ILM policy | Chính sách tự động quản lý vòng đời index qua các phase và action |
| Data stream | Cấu trúc hướng tới dữ liệu append-only theo thời gian, gồm nhiều backing index |

Rollover không chia nhỏ document đang nằm trong index cũ. Nó chuyển nơi nhận các lần ghi tiếp theo sang index mới. Index cũ vẫn tồn tại cho đến khi một chính sách khác xóa hoặc di chuyển nó.

## 3. Rollover bằng write alias

Một mẫu triển khai phổ biến là tạo một alias chuyên nhận ghi. Ban đầu alias trỏ tới index đầu tiên và index đó được đánh dấu là write index.

Ví dụ tạo index đầu tiên:

```http
PUT /events-000001
Content-Type: application/json

{
  "aliases": {
    "events-write": {
      "is_write_index": true
    }
  }
}
```

Ứng dụng gửi document tới `events-write` thay vì ghi trực tiếp vào `events-000001`:

```http
POST /events-write/_doc
Content-Type: application/json

{
  "@timestamp": "2026-11-13T09:30:00Z",
  "eventType": "product_view",
  "message": "A visitor opened a product page"
}
```

Khi cần rollover, Elasticsearch tạo index mới, ví dụ `events-000002`, rồi cập nhật write alias để các lần ghi tiếp theo đi vào index mới. Index cũ vẫn lưu dữ liệu lịch sử. Alias có thể được dùng cho thao tác đọc tùy cách cấu hình alias; để tách quyền và bảo đảm truy vấn lịch sử bao phủ tất cả thế hệ, thường nên tạo thêm một read alias riêng.

### Vì sao cần hậu tố số thứ tự?

Với ILM rollover alias, tên index cần kết thúc bằng hậu tố số có dạng `-000001`. Elasticsearch tăng hậu tố khi tạo index tiếp theo. Ví dụ:

```text
events-000001 -> events-000002 -> events-000003
```

Quy ước này giúp rollover xác định tên index tiếp theo. Một index tùy ý như `events-2026.11.13` không đáp ứng quy ước đặt tên mà ILM rollover alias yêu cầu. Nếu muốn tên theo ngày lịch, hãy cân nhắc data stream hoặc quy trình tạo index theo lịch riêng.

## 4. Gọi Rollover API thủ công

Elasticsearch cung cấp Rollover API để tạo index thế hệ mới khi điều kiện được thỏa mãn. Có thể kiểm tra trước bằng `dry_run`:

```http
POST /events-write/_rollover?dry_run
Content-Type: application/json

{
  "conditions": {
    "max_age": "7d",
    "max_docs": 50000000,
    "max_primary_shard_size": "30gb"
  }
}
```

`dry_run` trả về việc các điều kiện đã đạt hay chưa mà không tạo index mới. Khi muốn thực hiện rollover thật:

```http
POST /events-write/_rollover
Content-Type: application/json

{
  "conditions": {
    "max_age": "7d",
    "max_docs": 50000000,
    "max_primary_shard_size": "30gb"
  }
}
```

Các điều kiện được đánh giá theo logic OR: chỉ cần một điều kiện đạt thì rollover có thể xảy ra. Trong response, các trường như `old_index`, `new_index`, `rolled_over` và `conditions` cho biết kết quả.

### Các điều kiện thường dùng

| Điều kiện | Ý nghĩa | Khi hữu ích |
|---|---|---|
| `max_age` | Tuổi tối đa của index kể từ khi được tạo | Giới hạn thời gian dữ liệu nằm trong một index |
| `max_docs` | Số document tối đa theo điều kiện rollover | Giới hạn số document trong một thế hệ |
| `max_size` | Tổng dung lượng các primary shard | Giới hạn dung lượng dữ liệu chính của index |
| `max_primary_shard_size` | Dung lượng của primary shard lớn nhất | Tránh một shard riêng lẻ trở nên quá lớn |

Khi chọn ngưỡng dung lượng, cần phân biệt dung lượng primary shard với dung lượng gồm cả replica. Replica làm tăng dung lượng cluster nhưng không phải dữ liệu primary được dùng trong điều kiện `max_primary_shard_size`. Nên theo dõi shard lớn nhất vì một index có nhiều shard vẫn có thể có một shard nóng hoặc lớn bất thường.

### Rollover không phải là xóa index cũ

Sau rollover, index cũ vẫn còn để truy vấn lịch sử. Rollover không tự xóa document, không tự chuyển shard sang node lưu trữ rẻ hơn và cũng không tự đặt thời hạn retention. Những công việc đó thuộc ILM, Data Stream Lifecycle hoặc quy trình vận hành riêng.

Không nên gọi Rollover API từ mỗi request ghi dữ liệu. Rollover là thao tác quản lý index; hãy để ILM thực hiện tự động hoặc gọi từ một job quản trị có kiểm soát.

## 5. Dùng Index Lifecycle Management (ILM)

ILM tự động áp dụng policy lên index. Policy có thể định nghĩa các phase như:

- **Hot:** index nhận ghi và được truy vấn thường xuyên; thường có rollover.
- **Warm:** dữ liệu ít được ghi hơn; có thể giảm replica, force merge hoặc shrink tùy kiến trúc.
- **Cold:** dữ liệu ít truy cập; có thể dùng cấu hình lưu trữ tiết kiệm hơn.
- **Frozen:** dữ liệu rất ít truy cập, dùng cơ chế lưu trữ/search phù hợp với phiên bản và license triển khai.
- **Delete:** xóa index khi hết thời hạn lưu giữ.

Không phải cluster nào cũng cần đủ mọi phase. Hãy chọn theo loại dữ liệu, tần suất truy vấn, chi phí lưu trữ, topology node và khả năng của phiên bản Elasticsearch đang chạy.

### Tạo ILM policy

Ví dụ policy cho dữ liệu sự kiện: rollover khi primary shard lớn nhất đạt 30 GB hoặc index đủ 7 ngày; xóa index sau 90 ngày kể từ mốc rollover.

```http
PUT /_ilm/policy/events-policy
Content-Type: application/json

{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_primary_shard_size": "30gb",
            "max_age": "7d"
          }
        }
      },
      "delete": {
        "min_age": "90d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
```

Trong ví dụ này, `min_age` ở phase delete của index đã rollover được tính từ thời điểm rollover, không phải lúc document đầu tiên được ghi. Vì vậy, index có thể tồn tại khoảng 90 ngày sau rollover; thời gian thực tế từ khi tạo index tới khi xóa còn phụ thuộc lúc rollover diễn ra. Hãy tính retention theo cách này khi chính sách lưu trữ có yêu cầu pháp lý hoặc nghiệp vụ.

### Tạo index template

Template gắn ILM policy và rollover alias vào các index mới khớp pattern. Ví dụ:

```http
PUT /_index_template/events-template
Content-Type: application/json

{
  "index_patterns": ["events-*"],
  "priority": 200,
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1,
      "index.lifecycle.name": "events-policy",
      "index.lifecycle.rollover_alias": "events-write"
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "eventType": { "type": "keyword" },
        "message": { "type": "text" }
      }
    },
    "aliases": {
      "events-read": {}
    }
  }
}
```

`events-read` được thêm vào mọi index mới khớp template, vì vậy alias đọc có thể truy vấn các thế hệ dữ liệu. Không đặt `events-write` như một alias write index cố định trên mọi index trong template; write alias cần trỏ đúng index hiện hành và được rollover/ILM quản lý.

### Bootstrap index đầu tiên

Sau khi policy và template đã tồn tại, tạo index đầu tiên với write alias:

```http
PUT /events-000001
{
  "aliases": {
    "events-write": {
      "is_write_index": true
    }
  }
}
```

Template sẽ áp dụng settings, mapping và read alias `events-read`. Việc bootstrap này quan trọng: nếu policy có `index.lifecycle.rollover_alias` nhưng alias chưa tồn tại hoặc không có write index đúng, ILM không thể rollover theo cấu hình.

### Kiểm tra ILM

Kiểm tra trạng thái policy:

```http
GET /_ilm/policy/events-policy
```

Kiểm tra index đang được ILM quản lý và action hiện tại:

```http
GET /events-000001/_ilm/explain
```

Kiểm tra alias:

```http
GET /_alias/events-write
GET /_alias/events-read
```

Kiểm tra danh sách index:

```http
GET /_cat/indices/events-*?v&s=index
```

Nếu index không rollover, kiểm tra ILM có đang chạy không, policy có được gắn vào index không, alias có trỏ đúng write index không, hậu tố index có đúng quy ước không và điều kiện rollover đã đạt chưa.

## 6. Alias ghi và alias đọc

Với dữ liệu nhiều thế hệ, nên xác định rõ alias nào dùng để ghi và alias nào dùng để đọc.

```text
Ứng dụng ghi
    |
    v
events-write
    |
    v
events-000004  (write index hiện tại)

Ứng dụng đọc lịch sử
    |
    v
events-read
    |
    +--> events-000001
    +--> events-000002
    +--> events-000003
    +--> events-000004
```

`events-write` dành cho thao tác ghi. `events-read` trỏ tới mọi thế hệ cần truy vấn. Trong ví dụ ILM, template thêm `events-read` vào từng index mới, nên alias đọc tiếp tục bao phủ các index sau rollover.

Tách alias có một số lợi ích:

- Ứng dụng ghi không cần biết tên index vật lý hiện tại.
- Truy vấn lịch sử không bị giới hạn vào index mới nhất.
- Có thể cấp quyền ghi cho `events-write` và quyền đọc cho `events-read` riêng biệt.
- Có thể thay đổi cách đọc, ví dụ chỉ truy vấn một nhóm index hoặc alias theo tenant, mà không thay đổi logic ghi.

Nếu chỉ dùng một alias cho cả đọc và ghi, cần hiểu chính xác alias đang trỏ tới index nào sau rollover. Không giả định write alias luôn bao phủ mọi thế hệ. Kiểm tra kết quả qua `GET /_alias/{alias}` và thiết kế read alias tường minh nếu ứng dụng cần lịch sử.

## 7. Kết nối alias với Spring Data Elasticsearch

Spring Data Elasticsearch làm việc với tên index được khai báo trong `@Document`. Giá trị đó có thể là alias thay vì tên index vật lý. Với index do ILM quản lý, ứng dụng không nên tự tạo index theo tên alias khi khởi động.

Ví dụ document ghi qua write alias:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events-write", createIndex = false)
public class EventDocument {

    @Id
    private String id;

    @Field(name = "@timestamp", type = FieldType.Date)
    private Instant timestamp;

    @Field(type = FieldType.Keyword)
    private String eventType;

    @Field(type = FieldType.Text)
    private String message;

    // Constructors, getters and setters
}
```

`createIndex = false` ngăn Spring Data cố tạo một index vật lý tên `events-write` khi khởi tạo mapping/repository. Alias và index vật lý phải được bootstrap bởi ILM/template hoặc quy trình triển khai riêng.

Repository có thể ghi document qua alias:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface EventRepository
        extends ElasticsearchRepository<EventDocument, String> {
}
```

Khi gọi `save`, request đi tới `events-write`; Elasticsearch định tuyến tới write index hiện tại. Ứng dụng không cần thay đổi tên index trong code sau mỗi lần rollover.

### Đọc qua read alias

Nếu cần tìm dữ liệu trên toàn bộ lịch sử, dùng read alias. Với `ElasticsearchOperations`, có thể chỉ định `IndexCoordinates` cho thao tác đọc:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;

public class EventSearchService {

    private final ElasticsearchOperations operations;

    public EventSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void searchAllEvents(Query query) {
        operations.search(
            query,
            EventDocument.class,
            IndexCoordinates.of("events-read")
        );
    }
}
```

Ví dụ bỏ qua phần xử lý `SearchHits` để tập trung vào việc chọn alias. API cụ thể có thể khác nhẹ theo phiên bản Spring Data. Điều quan trọng là thao tác đọc phải nhắm tới alias bao phủ các thế hệ cần tìm, còn thao tác ghi nhắm tới write alias.

## 8. Rollover theo thời gian và tạo index theo ngày

Rollover dựa trên điều kiện như tuổi hoặc dung lượng; nó không nhất thiết tạo index đúng lúc nửa đêm mỗi ngày. Nếu cần nhóm dữ liệu theo ngày lịch, có thể dùng tên index như:

```text
orders-2026.11.11
orders-2026.11.12
orders-2026.11.13
```

Ứng dụng hoặc một job định kỳ chọn index theo ngày và index template cung cấp mapping/settings cho mỗi index. Truy vấn lịch sử thường dùng wildcard hoặc alias đọc bao phủ các ngày.

So sánh hai cách:

| Cách | Ưu điểm | Hạn chế |
|---|---|---|
| Index theo ngày/tháng | Tên index thể hiện rõ khoảng thời gian, dễ xóa theo lịch | Cần tự quản lý tạo index và định tuyến ghi; lưu lượng không đều làm kích thước index chênh lệch |
| Rollover theo điều kiện | Kích thước và tuổi index được giới hạn theo ngưỡng; ứng dụng ghi qua alias ổn định | Ranh giới index không nhất thiết trùng ngày lịch; cần alias và ILM/bootstrap đúng |
| Data stream | Mô hình thuận tiện cho dữ liệu append-only theo thời gian | Cần mapping timestamp và hiểu backing index/retention của data stream |

Không nên tạo một index cho mỗi khoảng thời gian quá nhỏ nếu lưu lượng thấp, vì nhiều index nhỏ làm tăng overhead shard, cluster state và chi phí quản lý. Ngược lại, index quá lớn có thể làm recovery, relocation và truy vấn khó kiểm soát.

## 9. Khi nào nên dùng Data Stream?

Data stream được thiết kế cho dữ liệu time-series, thường là dữ liệu ghi thêm như log, metrics và sự kiện. Tên data stream là điểm truy cập logic; bên dưới Elasticsearch quản lý các backing index và rollover.

Đặc điểm chính:

- Document phải có trường timestamp được cấu hình, thường là `@timestamp` kiểu `date`.
- Ghi document qua tên data stream; Elasticsearch gửi dữ liệu vào backing index ghi hiện tại.
- Truy vấn qua tên data stream có thể tìm trên các backing index của stream.
- Rollover và retention có thể được quản lý bằng ILM hoặc Data Stream Lifecycle tùy phiên bản và nhu cầu.
- Data stream phù hợp nhất với luồng append-only; nếu ứng dụng thường xuyên cập nhật/xóa document cũ, cần đánh giá kỹ cách định tuyến thao tác và liệu data stream có phù hợp không.

Ví dụ thao tác tạo data stream cần có index template phù hợp trước:

```http
PUT /_index_template/app-events-template
Content-Type: application/json

{
  "index_patterns": ["app-events*"],
  "data_stream": {},
  "template": {
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "eventType": { "type": "keyword" },
        "message": { "type": "text" }
      }
    }
  }
}
```

Sau đó tạo stream:

```http
PUT /_data_stream/app-events
```

Ghi document qua tên stream:

```http
POST /app-events/_doc
Content-Type: application/json

{
  "@timestamp": "2026-11-13T09:30:00Z",
  "eventType": "login",
  "message": "User signed in"
}
```

Đây là ví dụ tối giản. Trong môi trường production, template cần kết hợp settings, mapping, lifecycle policy và quyền truy cập theo đúng phiên bản Elasticsearch đang dùng. Data stream có thể là lựa chọn đơn giản hơn alias rollover cho luồng sự kiện append-only, nhưng không phải thay thế chung cho mọi index.

## 10. Shard, replica và kích thước index

Rollover chỉ hiệu quả khi ngưỡng được chọn phù hợp với shard topology. Một index có nhiều primary shard sẽ phân chia dữ liệu, nhưng mỗi shard vẫn có chi phí bộ nhớ, file descriptor, segment và cluster metadata.

Một số nguyên tắc:

- Chọn số primary shard dựa trên dung lượng và throughput dự kiến của mỗi thế hệ index.
- Theo dõi kích thước primary shard lớn nhất, không chỉ tổng dung lượng index.
- Dùng `max_primary_shard_size` nếu mục tiêu là tránh một shard đơn lẻ quá lớn.
- Đặt replica theo yêu cầu sẵn sàng và khả năng chịu lỗi; replica không thay thế backup/snapshot.
- Tránh rollover quá thường xuyên khiến cluster có quá nhiều index nhỏ.
- Theo dõi số shard tổng thể và năng lực node trước khi tăng số index.

Không có một ngưỡng shard duy nhất phù hợp mọi cluster. Hãy đo kích thước, indexing rate, search latency và thời gian recovery trong môi trường gần production trước khi chốt policy.

## 11. Truy vấn và xóa dữ liệu lịch sử

Khi dùng read alias, truy vấn có thể bao phủ nhiều index. Để giảm lượng dữ liệu cần đọc, nên lọc theo timestamp và các trường có ích cho routing/filter.

Ví dụ tìm sự kiện trong một khoảng thời gian:

```http
GET /events-read/_search
Content-Type: application/json

{
  "query": {
    "range": {
      "@timestamp": {
        "gte": "2026-11-01T00:00:00Z",
        "lt": "2026-11-14T00:00:00Z"
      }
    }
  }
}
```

Khi retention hết hạn, ILM có thể xóa index cũ. Xóa index là thao tác ở cấp index, nhanh hơn việc xóa từng document bằng delete-by-query khi toàn bộ index đã hết thời hạn và không còn dữ liệu cần giữ.

Hãy phân biệt retention của dữ liệu với snapshot/backup. Xóa index theo ILM không tự động xóa snapshot đã lưu ở repository. Nếu yêu cầu xóa dữ liệu áp dụng cả backup, cần có chính sách vòng đời snapshot riêng.

## 12. Theo dõi và xử lý sự cố rollover

Các dấu hiệu thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| ILM báo rollover alias missing | Alias chưa được tạo hoặc sai tên | `GET /_alias/events-write` và kiểm tra `index.lifecycle.rollover_alias` |
| Không xác định được write index | Alias không có `is_write_index` đúng hoặc trỏ nhiều index mà thiếu write flag | Kiểm tra alias metadata và bootstrap index |
| Rollover không chạy | Policy chưa gắn, ILM dừng, điều kiện chưa đạt hoặc action đang retry | `GET /events-000001/_ilm/explain` |
| Tạo index mới thất bại | Template sai, mapping/settings không hợp lệ hoặc quyền thiếu | Kiểm tra cluster logs, template và quyền tạo index |
| Ứng dụng ghi vào index cũ | Ứng dụng đang ghi tên index vật lý thay vì alias | Kiểm tra `@Document(indexName=...)` và request target |
| Truy vấn không thấy dữ liệu cũ | Đọc qua alias chỉ trỏ index hiện tại hoặc read alias chưa gắn vào index cũ | Kiểm tra `GET /_alias/events-read` |
| Quá nhiều index nhỏ | Ngưỡng rollover quá thấp hoặc index theo lịch quá chi tiết | Đánh giá lại max_age/max_docs/max_primary_shard_size |

Khi ILM gặp lỗi, xem bước đang chạy và thông báo trong `_ilm/explain` trước khi retry hoặc chỉnh policy. Không xóa index đang được quản lý chỉ để làm mất trạng thái lỗi nếu chưa hiểu ảnh hưởng tới alias và retention.

## 13. Các lưu ý vận hành quan trọng

### Thay đổi policy

Khi cập nhật ILM policy, các index đang gắn policy có thể nhận thay đổi theo cơ chế cập nhật của ILM. Cần kiểm tra policy hiện hành và trạng thái từng index trước khi đổi ngưỡng rollover hoặc retention.

### Đồng bộ dữ liệu khi chuyển thế hệ

Rollover chỉ chuyển ghi mới. Nếu ứng dụng đang có luồng backfill hoặc ghi song song, cần đảm bảo không bỏ sót document và xử lý retry/idempotency. Alias cập nhật nguyên tử giúp chuyển điểm ghi, nhưng không thay thế cơ chế đảm bảo dữ liệu trong pipeline.

### Quyền truy cập

Ứng dụng thông thường chỉ cần quyền ghi qua alias ghi và đọc qua alias đọc. Quyền tạo index, rollover, thay template và sửa ILM policy nên thuộc vai trò vận hành riêng. Không cấp quyền quản trị cluster rộng cho service chỉ để nó có thể ghi document.

### Tên index và thời gian

Với index theo ngày, xác định timezone dùng để chia ngày. Một sự kiện có timestamp UTC nhưng được nhóm theo ngày địa phương có thể rơi vào index khác nếu producer và consumer không thống nhất timezone. Với rollover theo tuổi, tuổi index dựa trên thời điểm tạo/rollover chứ không dựa trên timestamp bên trong document.

## 14. Quy trình thiết kế vòng đời index

Khi triển khai dữ liệu theo thời gian, có thể đi theo trình tự:

1. Xác định loại dữ liệu, tốc độ ghi, nhu cầu truy vấn lịch sử và thời hạn lưu trữ.
2. Chọn index theo lịch, rollover alias hoặc data stream dựa trên mô hình ghi và truy vấn.
3. Thiết kế mapping có trường thời gian rõ ràng, thường là `@timestamp` kiểu `date`.
4. Chọn số shard và replica theo kích thước dự kiến của từng thế hệ.
5. Tạo index template để chuẩn hóa mapping/settings cho mọi index mới.
6. Với ILM alias, tạo policy, gắn policy/template và bootstrap index đầu tiên cùng write alias.
7. Tạo read alias bao phủ mọi thế hệ cần truy vấn.
8. Cấu hình Spring Data dùng alias hoặc data stream, không ghi cứng tên index vật lý.
9. Kiểm tra rollover bằng dry run, xác nhận alias và theo dõi `_ilm/explain`.
10. Kiểm thử truy vấn lịch sử, retention, snapshot và quy trình khôi phục trước khi vận hành production.

## 15. Kết luận

Rollover và quản lý index theo thời gian giúp kiểm soát tốc độ tăng dữ liệu, kích thước shard và thời hạn lưu trữ. Rollover chuyển điểm ghi sang index thế hệ mới; alias giữ tên truy cập ổn định; index template đảm bảo mapping/settings nhất quán; ILM tự động thực hiện rollover và các phase lưu trữ/xóa.

Trong Spring Data Elasticsearch, nên để ứng dụng ghi qua write alias hoặc data stream và đọc qua alias bao phủ các thế hệ dữ liệu cần thiết. Không tạo index vật lý mới từ mỗi request và không phụ thuộc vào tên index hiện tại trong code. Với dữ liệu append-only theo thời gian, data stream là lựa chọn đáng cân nhắc; với mô hình alias rollover, cần bootstrap đúng index có hậu tố số, cấu hình write alias và kiểm tra ILM. Khi thiết kế cả retention, shard, read alias và snapshot cùng nhau, vòng đời dữ liệu sẽ dễ dự đoán và vận hành hơn.
