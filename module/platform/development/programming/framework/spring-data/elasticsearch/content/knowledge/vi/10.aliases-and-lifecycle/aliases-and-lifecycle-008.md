# Data stream, dữ liệu nối thêm và yêu cầu tương thích

Elasticsearch data stream là một abstraction để lưu và tìm kiếm dữ liệu thường xuyên được ghi nối thêm, đặc biệt là log, metric, event và dữ liệu theo thời gian. Ứng dụng gửi document đến một tên data stream ổn định; Elasticsearch tự định tuyến thao tác ghi đến backing index hiện tại. Khi backing index đạt điều kiện rollover, một backing index mới được tạo và trở thành nơi nhận dữ liệu tiếp theo.

Data stream phù hợp với mô hình **append-only**: hệ thống chủ yếu thêm event mới, sau đó tìm kiếm hoặc phân tích các event đã lưu. Mô hình này khác với một index nghiệp vụ thông thường, nơi ứng dụng thường xuyên cập nhật hoặc xóa document theo id.

Để sử dụng data stream đúng cách, cần hiểu ba yêu cầu quan trọng:

- Document phải có trường thời gian @timestamp với mapping kiểu date hoặc date_nanos.
- Các document được ghi vào data stream phải tuân theo mô hình tạo mới; thao tác ghi dùng create semantics thay vì ghi đè document hiện có.
- Các backing index phải có mapping tương thích, thường được chuẩn bị bằng index template và quản lý vòng đời qua rollover/retention policy.

## 1. Data stream là gì?

Data stream là tên logic đại diện cho một chuỗi các backing index. Ứng dụng đọc và ghi thông qua tên data stream, còn Elasticsearch quản lý các index vật lý phía sau.

Ví dụ, ứng dụng ghi log vào data stream logs-app-default. Data stream có thể gồm:

    logs-app-default
       |
       +-- .ds-logs-app-default-2026.10.01-000001
       |
       +-- .ds-logs-app-default-2026.11.01-000002
       |
       +-- .ds-logs-app-default-2026.12.01-000003
                  ^
                  |
             Write index hiện tại

Tên backing index minh họa theo định dạng phổ biến của Elasticsearch. Các backing index thường là hidden index và được quản lý bởi data stream. Ứng dụng không cần tự chọn backing index khi ghi.

Data stream cung cấp một tên ổn định cho nghiệp vụ:

- Search trên tên data stream tìm dữ liệu trong các backing index thuộc stream.
- Index document vào tên data stream sẽ được định tuyến đến write index hiện tại.
- Khi rollover, write index cũ trở thành backing index chỉ đọc theo vòng đời thông thường; một backing index mới được thêm vào stream.
- Việc quản lý backing index được thực hiện qua data stream API, index template và lifecycle policy.

Data stream không phải là một index vật lý duy nhất. Nó cũng không đơn thuần là alias thông thường: nó có quy tắc tạo document, backing index và rollover riêng.

## 2. Vì sao data stream phù hợp với dữ liệu nối thêm?

Nhiều loại dữ liệu phát sinh liên tục theo thời gian:

- Log ứng dụng: mỗi request hoặc lỗi tạo một event mới.
- Audit event: mỗi hành động của người dùng tạo một bản ghi.
- Metric: hệ thống ghi nhận CPU, memory, latency theo chu kỳ.
- Event từ thiết bị: thiết bị gửi trạng thái hoặc tín hiệu theo thời gian.
- Telemetry: dịch vụ gửi dữ liệu quan sát về hệ thống.

Các dữ liệu này thường có đặc điểm:

1. Mỗi bản ghi là một sự kiện tại một thời điểm.
2. Dữ liệu mới được thêm liên tục.
3. Truy vấn thường lọc theo khoảng thời gian.
4. Dữ liệu cũ ít được sửa đổi.
5. Dữ liệu có thể được giữ trong một khoảng thời gian rồi xóa theo retention policy.

Data stream được thiết kế để phục vụ mô hình đó. Khi ứng dụng ghi event mới, nó chỉ cần biết tên data stream. Elasticsearch quyết định write index hiện tại và việc chuyển sang backing index tiếp theo.

### Append-only có nghĩa gì?

Append-only nghĩa là dữ liệu được bổ sung bằng các event mới thay vì thường xuyên sửa bản ghi cũ. Ví dụ, khi trạng thái đơn hàng thay đổi, hệ thống event có thể ghi một event OrderStatusChanged mới thay vì cập nhật event OrderCreated trước đó.

Mô hình event này có một số lợi ích:

- Giữ lại lịch sử thay đổi.
- Hỗ trợ phân tích theo thời gian.
- Giảm sự phụ thuộc vào việc cập nhật document cũ.
- Dễ chia dữ liệu thành backing index theo vòng đời.
- Có thể áp dụng retention cho dữ liệu cũ.

Nếu nghiệp vụ cần một bản ghi hiện tại có thể cập nhật liên tục, chẳng hạn hồ sơ khách hàng hoặc trạng thái tồn kho hiện thời, index thông thường hoặc alias thường phù hợp hơn data stream.

## 3. Yêu cầu về trường @timestamp

Mỗi document trong data stream phải chứa trường @timestamp. Field này phải được mapping là date hoặc date_nanos.

Ví dụ document log:

    {
      "@timestamp": "2026-11-13T10:15:30Z",
      "service": "catalog-api",
      "level": "ERROR",
      "message": "Product lookup failed",
      "duration_ms": 125
    }

Trường @timestamp biểu diễn thời điểm event xảy ra. Nó là dữ liệu quan trọng để:

- Sắp xếp event theo thời gian.
- Lọc theo khoảng thời gian.
- Phân tích xu hướng và tần suất.
- Hỗ trợ routing, rollover và lifecycle trong các cấu hình phù hợp.

Mapping cần khai báo rõ kiểu thời gian:

    {
      "properties": {
        "@timestamp": {
          "type": "date"
        },
        "service": {
          "type": "keyword"
        },
        "level": {
          "type": "keyword"
        },
        "message": {
          "type": "text"
        },
        "duration_ms": {
          "type": "long"
        }
      }
    }

Không nên để dynamic mapping tự suy luận @timestamp từ một document bất kỳ trong production. Hãy khai báo mapping tường minh để đảm bảo tất cả backing index có cùng kiểu dữ liệu.

### Thời gian event và thời gian nhận event

Ứng dụng nên phân biệt:

- Event time: thời điểm sự kiện thực sự xảy ra.
- Ingestion time: thời điểm Elasticsearch nhận hoặc index document.

Nếu event được gửi trễ, hai thời điểm có thể khác nhau. @timestamp thường biểu diễn event time để truy vấn theo thời điểm nghiệp vụ. Nếu cần phân tích độ trễ ingest, có thể lưu thêm một field riêng như event.ingested.

Giá trị timestamp nên có timezone rõ ràng, thường là ISO-8601 với UTC hoặc offset. Tránh gửi thời gian không có timezone nếu hệ thống có nhiều vùng triển khai.

## 4. Tạo data stream bằng index template

Data stream cần một index template có phần khai báo data_stream. Template xác định pattern tên data stream, settings, mappings và có thể kết hợp component templates.

Ví dụ tạo template cho logs-app-*:

    PUT _index_template/logs_app_template
    {
      "index_patterns": [ "logs-app-*" ],
      "data_stream": {},
      "priority": 200,
      "template": {
        "settings": {
          "number_of_shards": 1
        },
        "mappings": {
          "properties": {
            "@timestamp": {
              "type": "date"
            },
            "service": {
              "type": "keyword"
            },
            "level": {
              "type": "keyword"
            },
            "message": {
              "type": "text"
            },
            "duration_ms": {
              "type": "long"
            }
          }
        }
      }
    }

Template có data_stream cho biết pattern này được dùng để tạo data stream. Mapping @timestamp là yêu cầu cần thiết. Các field khác được khai báo theo cách ứng dụng sẽ ghi và truy vấn.

Sau khi template được tạo, có thể tạo data stream:

    PUT _data_stream/logs-app-default

Elasticsearch tạo backing index ban đầu theo template và đăng ký data stream với tên logs-app-default.

Có thể xem trạng thái:

    GET _data_stream/logs-app-default

Response cung cấp thông tin data stream và các backing index. Khi cần kiểm tra cấu hình mapping thực tế, có thể đọc mapping của backing index hoặc sử dụng API phù hợp cho data stream.

### Vai trò của template

Index template giúp đảm bảo mỗi backing index mới nhận cùng một bộ settings và mappings. Nếu không kiểm soát template, backing index được tạo ở các thời điểm khác nhau có thể có schema không nhất quán, đặc biệt khi ứng dụng phát sinh field mới.

Với hệ thống lớn, có thể tách template thành component templates:

- Component template cho mapping dùng chung.
- Component template cho settings.
- Index template kết hợp các component template và khai báo data stream.

Điều này giúp tái sử dụng cấu hình giữa nhiều data stream mà vẫn kiểm soát được phiên bản schema.

## 5. Ghi document vào data stream

Ứng dụng gửi document đến tên data stream, không cần biết tên backing index hiện tại.

Ví dụ REST API:

    POST logs-app-default/_doc?op_type=create
    {
      "@timestamp": "2026-11-13T10:15:30Z",
      "service": "catalog-api",
      "level": "INFO",
      "message": "Product search completed"
    }

Elasticsearch định tuyến document đến write index hiện tại. Đối với data stream, thao tác ghi phải có create semantics. Trong Bulk API, action phù hợp là create:

    POST _bulk
    { "create": { "_index": "logs-app-default" } }
    { "@timestamp": "2026-11-13T10:15:30Z", "service": "catalog-api", "level": "INFO" }

Điểm quan trọng là data stream không được dùng như một index thông thường để ghi đè document đã tồn tại bằng cùng id. Một document được gửi đến data stream là một event mới. Nếu cần sửa trạng thái, hãy cân nhắc ghi một event hiệu chỉnh hoặc event mới mô tả trạng thái tiếp theo.

### Quy tắc về id

Nếu ứng dụng tự tạo id, cần đảm bảo mỗi event có định danh phù hợp. Gửi lại một event với cùng id theo create semantics có thể bị từ chối vì document đã tồn tại. Điều này có thể giúp phát hiện duplicate, nhưng ứng dụng cần có chiến lược xử lý retry và idempotency.

Nếu không cung cấp id, Elasticsearch có thể tạo id tự động. Cách này tiện cho event append-only, nhưng retry cùng một payload có thể tạo nhiều document khác nhau nếu request trước đã thành công mà client không nhận được response.

Vì vậy, thiết kế producer cần quyết định:

- Có cần id ổn định để chống duplicate không?
- Có cần lưu event id từ hệ thống nguồn không?
- Khi timeout, làm sao xác định request đã được ghi hay chưa?
- Có chấp nhận duplicate event và xử lý ở tầng phân tích không?

## 6. Đọc và tìm kiếm dữ liệu trong data stream

Data stream hỗ trợ search trên toàn bộ backing index thông qua tên stream:

    GET logs-app-default/_search
    {
      "query": {
        "bool": {
          "filter": [
            {
              "range": {
                "@timestamp": {
                  "gte": "2026-11-13T00:00:00Z",
                  "lt": "2026-11-14T00:00:00Z"
                }
              }
            },
            {
              "term": {
                "service": "catalog-api"
              }
            }
          ]
        }
      },
      "sort": [
        {
          "@timestamp": "desc"
        }
      ]
    }

Query sử dụng range trên @timestamp và filter theo service. Elasticsearch tìm trên các backing index thuộc data stream, không yêu cầu ứng dụng tự ghép từng index.

Nếu cần đọc dữ liệu qua nhiều data stream, có thể sử dụng wildcard hoặc data stream alias theo thiết kế. Cần giới hạn pattern để tránh vô tình truy vấn quá nhiều dữ liệu.

### Field mapping phải nhất quán

Khi search qua nhiều backing index, cùng một field nên có kiểu tương thích. Ví dụ:

- service nên là keyword trong tất cả backing index.
- @timestamp nên là date hoặc date_nanos theo cùng một thiết kế.
- duration_ms nên có kiểu số nhất quán.

Nếu một backing index có service là text và index khác là keyword, truy vấn, sort hoặc aggregation trên toàn stream có thể phát sinh lỗi hoặc kết quả không nhất quán.

Đây là lý do index template và component template quan trọng: mọi backing index mới cần nhận cùng schema đã được kiểm soát.

## 7. Rollover và backing index

Rollover là quá trình chuyển write index của data stream sang một backing index mới. Data stream tiếp tục giữ cùng tên logic, trong khi dữ liệu mới được ghi vào index mới.

Ví dụ:

    Trước rollover:
      logs-app-default
        -> .ds-logs-app-default-...-000001 (write index)

    Sau rollover:
      logs-app-default
        -> .ds-logs-app-default-...-000001
        -> .ds-logs-app-default-...-000002 (write index)

Rollover có thể được kích hoạt thủ công hoặc theo điều kiện của lifecycle policy. Những điều kiện thường gặp gồm:

- Tuổi backing index.
- Dung lượng dữ liệu.
- Số lượng document.

Ví dụ rollover thủ công:

    POST logs-app-default/_rollover

Có thể thêm điều kiện:

    POST logs-app-default/_rollover
    {
      "conditions": {
        "max_age": "1d",
        "max_primary_shard_size": "30gb"
      }
    }

Ví dụ minh họa điều kiện tuổi và kích thước shard. Giá trị thực tế cần dựa trên tốc độ ingest, kích thước document, số shard và yêu cầu vận hành.

Sau rollover:

- Tên data stream không đổi.
- Backing index cũ tiếp tục phục vụ search.
- Backing index mới trở thành write index.
- Ứng dụng tiếp tục gửi document đến tên data stream như trước.

Ứng dụng không nên ghi trực tiếp vào tên backing index. Việc đó bỏ qua định tuyến và lifecycle mà data stream cung cấp.

## 8. Quản lý vòng đời và retention

Data stream thường được kết hợp với lifecycle policy để tự động rollover và quản lý dữ liệu cũ.

Elasticsearch có các cơ chế lifecycle như Index Lifecycle Management (ILM) và Data Stream Lifecycle (DSL), tùy phiên bản và loại cluster. Chúng có thể quản lý:

- Rollover khi index đạt tuổi hoặc dung lượng.
- Di chuyển dữ liệu giữa các tier lưu trữ nếu kiến trúc hỗ trợ.
- Giữ dữ liệu trong khoảng thời gian quy định.
- Xóa backing index hết hạn.

Một ví dụ ILM policy đơn giản:

    PUT _ilm/policy/logs_app_policy
    {
      "policy": {
        "phases": {
          "hot": {
            "actions": {
              "rollover": {
                "max_age": "1d",
                "max_primary_shard_size": "30gb"
              }
            }
          },
          "delete": {
            "min_age": "30d",
            "actions": {
              "delete": {}
            }
          }
        }
      }
    }

Để policy ILM áp dụng cho backing index, template cần gắn lifecycle policy phù hợp, ví dụ thông qua setting index.lifecycle.name. Với data stream, không cần cấu hình rollover_alias như cách thường dùng cho write alias; hãy dùng cơ chế rollover dành cho data stream theo đúng phiên bản Elasticsearch. Nếu chọn Data Stream Lifecycle, cấu hình lifecycle theo API và giới hạn của phiên bản tương ứng.

Không nên mặc định rằng mọi cluster đều hỗ trợ cùng một lifecycle API hoặc mọi tính năng đều có trong cùng một license. Kiểm tra phiên bản và chính sách triển khai trước khi chọn ILM hay Data Stream Lifecycle.

Retention policy có tác động trực tiếp đến dữ liệu. Khi backing index hết hạn và bị xóa, document bên trong cũng không còn khả dụng. Thời gian lưu cần phù hợp yêu cầu nghiệp vụ, kiểm toán và chính sách dữ liệu của tổ chức.

## 9. Data stream và index alias khác nhau như thế nào?

Data stream và alias đều cung cấp tên logic để ứng dụng không phải gắn chặt với một index vật lý. Tuy nhiên, semantics của chúng khác nhau.

| Tiêu chí | Data stream | Index alias |
|---|---|---|
| Mục tiêu chính | Dữ liệu nối thêm, thường theo thời gian | Tên logic cho một hoặc nhiều index |
| Cấu trúc | Một chuỗi backing index được quản lý như data stream | Alias trỏ đến index hoặc nhiều index |
| Ghi document | Create semantics vào write index hiện tại | Phụ thuộc index/alias và thao tác được gửi |
| Cập nhật/xóa theo id | Không phù hợp với thao tác update/delete thông thường | Có thể thực hiện trên index đích nếu quyền và routing phù hợp |
| Rollover | Có semantics riêng cho data stream | Có thể dùng rollover API với alias được cấu hình |
| @timestamp | Bắt buộc | Không bắt buộc |
| Trường hợp dùng | Log, metric, event, telemetry | Versioned index, read/write alias, blue-green migration |

Nếu dữ liệu là event nối thêm và có timestamp rõ ràng, data stream thường là lựa chọn tự nhiên. Nếu dữ liệu là entity nghiệp vụ có thể cập nhật/xóa theo id, index alias thường linh hoạt hơn.

Không nên chọn data stream chỉ vì muốn có tên index ổn định. Hãy chọn theo mô hình dữ liệu và thao tác mà ứng dụng cần thực hiện.

## 10. Tương thích với Spring Data Elasticsearch

Spring Data Elasticsearch có thể ánh xạ entity Java đến tên data stream giống cách ánh xạ đến index, nhưng cần lưu ý các quy tắc của data stream ở phía Elasticsearch.

Ví dụ entity log:

    @Document(
        indexName = "logs-app-default",
        createIndex = false
    )
    public class AppLog {

        @Id
        private String id;

        @Field(name = "@timestamp", type = FieldType.Date)
        private Instant timestamp;

        @Field(type = FieldType.Keyword)
        private String service;

        @Field(type = FieldType.Keyword)
        private String level;

        @Field(type = FieldType.Text)
        private String message;
    }

Entity tham chiếu tên data stream. createIndex = false thể hiện ứng dụng không tự tạo index thông qua lifecycle repository; data stream và mapping đã được provision bằng template hoặc quy trình triển khai.

Mapping @timestamp phải khớp với mapping được tạo trong index template. Tên thuộc tính Java có thể là timestamp, nhưng tên field lưu trong Elasticsearch phải là @timestamp theo annotation.

### Chú ý thao tác ghi phải là create

Data stream yêu cầu thao tác ghi có create semantics. Các API ghi thông thường của một index có thể mặc định dùng index semantics, cho phép ghi đè document cùng id. Vì vậy, không nên giả định mọi phương thức save của Spring Data đều phù hợp với data stream ở mọi phiên bản.

Khi dùng Spring Data, hãy kiểm tra API của phiên bản đang triển khai để thiết lập thao tác tạo document (CREATE) cho từng lần ghi. Với các API cho phép cấu hình IndexQuery, có thể chỉ định operation type tương ứng nếu phiên bản hỗ trợ. Nếu abstraction repository không biểu diễn được semantics cần thiết, sử dụng Elasticsearch Java Client và gửi create operation trực tiếp.

Ví dụ ở mức Elasticsearch Java Client:

    client.index(request -> request
        .index("logs-app-default")
        .id(log.getId())
        .opType(OpType.Create)
        .document(log)
    );

Tên enum và kiểu builder cần theo phiên bản Java API Client. Ý nghĩa bắt buộc là request phải dùng op_type=create khi ghi vào data stream.

Đối với bulk indexing, dùng create action cho từng event:

    client.bulk(request -> request
        .operations(operation -> operation
            .create(create -> create
                .index("logs-app-default")
                .id(log.getId())
                .document(log)
            )
        )
    );

Không dùng bulk index action với ý định ghi đè document cũ trong data stream.

### Tìm kiếm bằng Spring Data

Các API search của Spring Data có thể dùng tên data stream làm IndexCoordinates hoặc indexName của entity:

    SearchHits<AppLog> hits =
        operations.search(query, AppLog.class);

Spring Data gửi truy vấn đến tên data stream; Elasticsearch thực hiện search trên các backing index. Cần bảo đảm mapping của entity và backing index tương thích.

Nếu dùng repository, cần xác nhận repository không kích hoạt thao tác tạo index ngoài ý muốn và phương thức ghi tuân thủ create semantics. Cấu hình createIndex = false thường phù hợp khi data stream được quản lý bằng template và lifecycle riêng.

## 11. Quy tắc về update và delete

Data stream được thiết kế cho dữ liệu nối thêm. Các thao tác update hoặc delete document trực tiếp theo id không phù hợp với semantics create-only của data stream.

Nếu cần điều chỉnh thông tin đã ghi, có một số cách tiếp cận:

- Ghi một event mới mô tả việc hiệu chỉnh hoặc trạng thái mới.
- Dùng event sourcing hoặc projection để tính trạng thái hiện tại ở tầng đọc.
- Với nhu cầu quản trị đặc biệt, xem xét các API update_by_query hoặc delete_by_query mà phiên bản Elasticsearch hỗ trợ, đồng thời hiểu rõ tác động lên tính append-only và lifecycle.
- Nếu nghiệp vụ thường xuyên cập nhật/xóa document theo id, chuyển dữ liệu đó sang index thông thường hoặc index được truy cập qua alias.

Không nên thiết kế data stream như một bảng CRUD. Việc cố dùng update theo id có thể bị server từ chối hoặc tạo ra quy trình xử lý phức tạp, không phù hợp với mục tiêu ban đầu.

## 12. Yêu cầu tương thích giữa các backing index

Data stream có thể chứa nhiều backing index được tạo tại các thời điểm khác nhau. Khi truy vấn toàn stream, field mapping cần tương thích để Elasticsearch có thể thực hiện search, sort và aggregation nhất quán.

Ví dụ một lỗi schema:

- Backing index đầu tiên có duration_ms là long.
- Một backing index mới vô tình suy luận duration_ms thành keyword.
- Query range hoặc aggregation trên toàn data stream có thể thất bại hoặc hoạt động không như mong muốn.

Nguyên nhân thường gặp:

- Dựa hoàn toàn vào dynamic mapping.
- Thay đổi entity Java nhưng không cập nhật template.
- Template mới có priority không như dự kiến.
- Nhiều template cùng khớp pattern và cấu hình bị ghi đè.
- Producer gửi kiểu JSON khác nhau giữa các phiên bản.

Để giữ tương thích:

1. Khai báo mapping tường minh cho field quan trọng.
2. Dùng index template có pattern và priority được kiểm soát.
3. Dùng component template để tái sử dụng mapping chung.
4. Kiểm tra template trước khi tạo backing index mới.
5. Kiểm tra mapping của tất cả backing index khi điều tra lỗi query.
6. Thực hiện thay đổi schema có kế hoạch, không chỉ sửa entity.

Có thể kiểm tra template bằng API simulate index template trước khi áp dụng. Điều này giúp biết template nào sẽ được chọn và cấu hình cuối cùng mà index mới nhận được.

## 13. Data stream thông thường và time series data stream

Data stream thông thường phù hợp với log, event và các dữ liệu append-only có timestamp. Elasticsearch còn có chế độ time series data stream (TSDS) cho dữ liệu metric theo thời gian với các yêu cầu chặt chẽ hơn.

TSDS có thể yêu cầu:

- index.mode được đặt là time_series.
- @timestamp với mapping date phù hợp.
- Các field dimension được khai báo và xác định rõ.
- Metric field có kiểu và cấu hình tương ứng.
- routing_path được cấu hình theo dimensions.
- Tuân thủ các giới hạn về thời gian và cấu trúc dữ liệu theo phiên bản Elasticsearch.

Ví dụ khái quát một mapping metric:

    {
      "settings": {
        "index.mode": "time_series",
        "index.routing_path": [ "host", "service" ]
      },
      "mappings": {
        "properties": {
          "@timestamp": {
            "type": "date"
          },
          "host": {
            "type": "keyword",
            "time_series_dimension": true
          },
          "service": {
            "type": "keyword",
            "time_series_dimension": true
          },
          "cpu_usage": {
            "type": "double",
            "time_series_metric": "gauge"
          }
        }
      }
    }

Ví dụ này chỉ minh họa các thành phần chính; TSDS có thêm quy tắc validation và yêu cầu tương thích theo phiên bản. Không nên dùng TSDS chỉ vì document có timestamp. Chỉ chọn khi dữ liệu thực sự là metric/time-series và có thể đáp ứng mô hình dimensions, metrics và routing của Elasticsearch.

## 14. Kiểm tra và vận hành data stream

Một số API thường dùng để quan sát:

    GET _data_stream/logs-app-default

Xem mapping:

    GET .ds-logs-app-default-*/_mapping

Xem backing index:

    GET _cat/indices/.ds-logs-app-default-*?v

Kiểm tra analyzer hoặc mapping field bằng API phù hợp khi data stream có nội dung văn bản.

Khi vận hành, cần quan sát:

- Số lượng backing index.
- Tuổi và kích thước write index.
- Tốc độ ingest và số document.
- Tình trạng rollover.
- Lỗi mapping hoặc lỗi create operation.
- Dung lượng lưu trữ và retention.
- Tải search trên các backing index.

Nếu rollover không xảy ra, write index có thể tiếp tục tăng kích thước. Nếu retention không hoạt động, dữ liệu cũ có thể chiếm dung lượng lâu hơn dự kiến. Nếu mapping template sai, lỗi có thể chỉ xuất hiện khi backing index mới được tạo hoặc khi producer gửi một field mới.

## 15. Những lỗi thường gặp

### Thiếu @timestamp

Data stream yêu cầu document có @timestamp và field phải được mapping là date hoặc date_nanos. Document thiếu field này hoặc có kiểu không phù hợp sẽ bị từ chối.

### Dùng data stream cho entity cần update thường xuyên

Data stream tối ưu cho event append-only. Nếu nghiệp vụ cần cập nhật hoặc xóa một document theo id như CRUD thông thường, nên cân nhắc index thông thường hoặc alias.

### Ghi bằng index semantics

Data stream yêu cầu create semantics. Nếu client gửi request ghi đè document theo id, server có thể từ chối. Kiểm tra op_type và API được Spring Data/client sử dụng.

### Ghi trực tiếp vào backing index

Ứng dụng nên ghi qua tên data stream. Ghi vào backing index cụ thể có thể bỏ qua định tuyến write index và phá vỡ giả định của lifecycle.

### Dựa vào dynamic mapping

Các backing index có thể nhận mapping khác nhau nếu dữ liệu đầu tiên hoặc template khác nhau. Khai báo mapping tường minh và kiểm tra template trước khi tạo index.

### Nhầm data stream với alias

Hai loại đều cung cấp tên logic nhưng có quy tắc ghi và vòng đời khác nhau. Data stream dành cho append-only/time-series; alias phù hợp với nhiều mô hình index, bao gồm CRUD và chuyển đổi index theo phiên bản.

### Không lập kế hoạch duplicate khi retry

Nếu request ghi thành công nhưng response bị mất, gửi lại có thể tạo event trùng nếu id tự động. Cần thiết kế event id hoặc chấp nhận và xử lý duplicate ở tầng tiêu thụ.

### Không kiểm tra mapping sau rollover

Mapping của backing index mới phụ thuộc template tại thời điểm tạo. Sau khi thay template, cần xác nhận index mới nhận đúng schema và các backing index cũ vẫn tương thích với query toàn stream.

## Kết luận

Data stream là tên logic quản lý một chuỗi backing index, phù hợp với dữ liệu nối thêm như log, event, metric và telemetry. Mọi document cần có @timestamp với mapping date/date_nanos; thao tác ghi phải tuân theo create semantics; backing index được tạo và quản lý theo template cùng rollover/lifecycle policy.

Trong Spring Data Elasticsearch, entity có thể tham chiếu tên data stream và dùng converter để ánh xạ document, nhưng ứng dụng phải bảo đảm index đã được provision đúng và thao tác ghi dùng create semantics. Nếu dữ liệu cần CRUD theo id, một index thông thường hoặc alias thường phù hợp hơn. Hiểu các yêu cầu tương thích này giúp tránh lỗi ghi, lệch mapping giữa backing index và khó khăn khi vận hành dữ liệu theo thời gian.
