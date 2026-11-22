# Ingest pipeline và giới hạn trách nhiệm của ứng dụng

Ingest pipeline là chuỗi processor chạy trên Elasticsearch khi document được đưa vào index. Pipeline có thể chuẩn hóa chuỗi, chuyển kiểu dữ liệu, phân tích ngày, tách nội dung, loại field thừa, bổ sung metadata hoặc áp dụng các phép biến đổi trước khi Elasticsearch lập chỉ mục document.

Pipeline giúp nhiều luồng ghi dùng chung một quy tắc xử lý dữ liệu. Tuy nhiên, nó không thay thế toàn bộ logic của ứng dụng. Xác thực request, phân quyền, quy tắc nghiệp vụ, gọi dịch vụ bên ngoài, quản lý giao dịch, điều phối retry và phản hồi lỗi cho người dùng vẫn cần được thiết kế ở tầng ứng dụng.

Trong Spring Data Elasticsearch, ứng dụng có thể gửi document qua pipeline khi index hoặc bulk index bằng API phù hợp của phiên bản đang dùng. Việc định nghĩa và quản lý pipeline thuộc phía Elasticsearch. Bài này giải thích vòng đời pipeline, các processor thường gặp, cách gắn pipeline vào thao tác ghi, xử lý lỗi và ranh giới trách nhiệm giữa cluster với ứng dụng.

## 1. Ingest pipeline là gì?

Ingest pipeline là một chuỗi processor được Elasticsearch thực thi trước khi document được index. Mỗi processor nhận document hiện tại, có thể đọc hoặc thay đổi field, rồi chuyển kết quả cho processor tiếp theo.

Ví dụ một hệ thống nhận sản phẩm từ nhiều nguồn. Dữ liệu đầu vào có thể chứa tên chưa chuẩn hóa, giá ở dạng chuỗi và thời gian theo định dạng của hệ thống nguồn. Pipeline có thể:

- Trim khoảng trắng ở tên.
- Chuẩn hóa chữ hoa/thường.
- Chuyển giá từ chuỗi sang số.
- Parse ngày thành field date chuẩn.
- Bỏ field raw chỉ dùng trong quá trình nhập.
- Thêm thời điểm ingest.
- Đánh dấu lỗi xử lý nếu processor thất bại và có cấu hình on_failure.

Luồng xử lý khái quát:

~~~text
Ứng dụng / Bulk importer
        |
        v
Index API hoặc Bulk API
        |
        v
Chọn ingest pipeline
        |
        v
Processor 1
        |
        v
Processor 2
        |
        v
Processor N
        |
        v
Mapping và indexing
        |
        v
Document có thể được tìm kiếm
~~~

Pipeline xử lý document ở thời điểm ghi. Nó không chạy khi người dùng thực hiện search, không tự sửa document đã tồn tại và không thay thế query-time transformation.

## 2. Pipeline và processor

Pipeline có một ID, mô tả tùy chọn và danh sách processor. Mỗi processor thực hiện một loại biến đổi.

| Processor | Công dụng |
|---|---|
| set | Gán giá trị cho field |
| remove | Xóa field |
| rename | Đổi tên field |
| append | Thêm giá trị vào field dạng list |
| lowercase / uppercase | Chuẩn hóa chữ hoa, chữ thường |
| trim | Loại khoảng trắng ở đầu và cuối chuỗi |
| convert | Chuyển kiểu dữ liệu |
| date | Parse chuỗi ngày thành giá trị date |
| date_index_name | Tạo tên index dựa trên ngày |
| grok | Phân tích chuỗi theo pattern |
| dissect | Tách chuỗi theo delimiter và cấu trúc |
| split | Tách chuỗi thành danh sách |
| join | Ghép danh sách thành chuỗi |
| script | Biến đổi bằng Painless |
| geoip | Bổ sung thông tin địa lý từ địa chỉ IP |
| user_agent | Phân tích User-Agent |
| enrich | Tra cứu dữ liệu từ enrich policy đã chuẩn bị |

Processor cụ thể phụ thuộc phiên bản Elasticsearch, plugin và cấu hình cluster. Trước khi dùng processor đặc thù, kiểm tra tài liệu của đúng phiên bản và khả năng triển khai trên ingest node.

### 2.1. Thứ tự processor có ý nghĩa

Processor chạy theo thứ tự khai báo. Processor sau nhìn thấy thay đổi của processor trước.

Ví dụ:

1. trim field name.
2. lowercase field name.
3. rename name thành normalizedName.

Nếu rename chạy trước trim/lowercase, các processor sau phải tham chiếu tên field mới. Thứ tự không đúng có thể khiến field không tồn tại hoặc pipeline tạo dữ liệu sai.

Ưu tiên processor chuyên dụng cho thao tác phổ biến. Không nên chia một phép biến đổi thành nhiều processor không cần thiết, nhưng cũng không nên nhồi mọi logic vào một script lớn khó đọc và khó debug.

### 2.2. Ingest context

Processor làm việc trên ingest document và một số metadata của ingest context. Một số giá trị hệ thống hữu ích:

- _index: index đích.
- _id: document ID.
- _routing: routing value nếu có.
- _ingest.timestamp: thời điểm ingest.
- _ingest.pipeline: pipeline hiện tại trong các context hỗ trợ.
- _ingest.on_failure_message và metadata liên quan khi xử lý lỗi.

Không nhầm ingest context với Java object ở ứng dụng. Processor thay đổi document phía Elasticsearch sau khi request đã được gửi đi; object Java gốc không tự được cập nhật ngược lại.

## 3. Tạo và quản lý pipeline

Dùng Ingest Pipeline API để tạo hoặc thay thế định nghĩa pipeline:

~~~http
PUT _ingest/pipeline/product-normalize-v1
{
  "description": "Normalize product documents before indexing",
  "processors": [
    {
      "trim": {
        "field": "name",
        "ignore_missing": true
      }
    },
    {
      "lowercase": {
        "field": "name",
        "ignore_missing": true
      }
    },
    {
      "convert": {
        "field": "price",
        "type": "long",
        "ignore_missing": true
      }
    },
    {
      "date": {
        "field": "createdAtRaw",
        "target_field": "createdAt",
        "formats": [
          "ISO8601",
          "yyyy-MM-dd HH:mm:ss"
        ],
        "timezone": "Asia/Ho_Chi_Minh"
      }
    },
    {
      "set": {
        "field": "ingestedAt",
        "value": "{{_ingest.timestamp}}",
        "override": false
      }
    },
    {
      "remove": {
        "field": "createdAtRaw",
        "ignore_missing": true
      }
    }
  ]
}
~~~

Pipeline trên giả định dữ liệu đầu vào có các field name, price và createdAtRaw theo định dạng phù hợp. Nếu createdAtRaw không parse được, date processor có thể làm thao tác index thất bại trừ khi có cấu hình xử lý lỗi.

Lấy pipeline:

~~~http
GET _ingest/pipeline/product-normalize-v1
~~~

Xóa pipeline:

~~~http
DELETE _ingest/pipeline/product-normalize-v1
~~~

Các thao tác quản lý pipeline cần quyền Elasticsearch phù hợp. Trong production, quyền tạo/sửa pipeline nên được cấp cho nhóm vận hành hoặc deployment identity có trách nhiệm; không nên để mọi request người dùng có thể tự thay đổi pipeline trên cluster.

### 3.1. Đặt tên và version pipeline

Nên đặt ID có thể nhận biết mục đích và phiên bản, ví dụ:

- product-normalize-v1
- product-normalize-v2
- order-ingest-v1
- customer-enrichment-v3

Pipeline được tham chiếu bởi index setting hoặc request ghi. Khi thay đổi logic, cần biết producer nào đang sử dụng pipeline nào.

Một cách triển khai an toàn là tạo pipeline version mới, simulate và kiểm thử, sau đó chuyển index setting hoặc ứng dụng sang ID mới. Giữ pipeline cũ trong giai đoạn chuyển đổi nếu vẫn còn producer dùng nó. Không sửa pipeline đang dùng rộng rãi mà không đánh giá tác động đến các luồng ingest hiện tại.

## 4. Chuẩn hóa dữ liệu với processor

### 4.1. set, remove và rename

Ví dụ gán source mặc định, bỏ field nội bộ và đổi tên field:

~~~json
{
  "processors": [
    {
      "set": {
        "field": "sourceSystem",
        "value": "legacy-import",
        "override": false
      }
    },
    {
      "rename": {
        "field": "productTitle",
        "target_field": "name",
        "ignore_missing": true
      }
    },
    {
      "remove": {
        "field": "temporaryImportNote",
        "ignore_missing": true
      }
    }
  ]
}
~~~

- set với override false chỉ đặt giá trị khi field chưa có theo semantics processor.
- rename chuyển field sang tên mới; cần xác định hành vi khi target đã tồn tại.
- remove xóa field khỏi ingest document trước khi index.

Dùng ignore_missing khi field thực sự có thể vắng mặt và điều đó không phải lỗi. Không bật ignore_missing cho mọi processor theo thói quen; nếu field bắt buộc mà bị thiếu, việc bỏ qua có thể che giấu dữ liệu nguồn lỗi.

### 4.2. convert

convert có thể chuyển kiểu field:

~~~json
{
  "convert": {
    "field": "price",
    "type": "long",
    "ignore_missing": true
  }
}
~~~

Ví dụ đầu vào price là chuỗi "259900", sau processor giá trị được chuyển thành số long. Mapping đích vẫn cần phù hợp với kiểu đã chuyển.

convert không thể biến mọi chuỗi tùy ý thành số hợp lệ. Dữ liệu "unknown" hoặc chuỗi chứa ký tự không mong đợi có thể gây lỗi. Nếu nghiệp vụ yêu cầu kiểm tra chặt, ứng dụng nên validate trước khi gửi hoặc pipeline cần có chiến lược xử lý lỗi rõ ràng.

### 4.3. date processor

Date processor parse chuỗi và ghi vào field date:

~~~json
{
  "date": {
    "field": "createdAtRaw",
    "target_field": "createdAt",
    "formats": ["ISO8601", "yyyy-MM-dd HH:mm:ss"],
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
~~~

Cần thống nhất timezone và định dạng nguồn. Nếu chuỗi đã có offset, không tự cộng thêm giờ ở ứng dụng rồi lại áp timezone theo cách gây dịch thời gian hai lần.

Nên lưu thời điểm dưới dạng instant thống nhất và chỉ chuyển sang timezone địa phương khi hiển thị hoặc khi xác định ranh giới nghiệp vụ.

### 4.4. grok và dissect

grok phân tích chuỗi theo pattern:

~~~json
{
  "grok": {
    "field": "message",
    "patterns": [
      "%{IP:clientIp} %{WORD:method} %{URIPATHPARAM:path} %{NUMBER:status:int}"
    ]
  }
}
~~~

dissect tách chuỗi theo cấu trúc delimiter đã biết, thường nhẹ hơn grok khi định dạng đầu vào ổn định:

~~~json
{
  "dissect": {
    "field": "message",
    "pattern": "%{timestamp} %{level} %{service}: %{message}"
  }
}
~~~

Chọn grok khi định dạng cần pattern linh hoạt; chọn dissect khi chuỗi có cấu trúc cố định và delimiter rõ. Pattern phức tạp có thể làm tăng CPU và rủi ro lỗi khi dữ liệu đầu vào thay đổi.

## 5. Processor script

Script processor cho phép dùng Painless để thực hiện biến đổi có điều kiện hoặc logic không có processor chuyên biệt.

Ví dụ tạo field displayName khi có name:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "if (ctx.name != null) { ctx.displayName = ctx.name.trim(); }"
  }
}
~~~

Ví dụ xóa field chỉ khi giá trị rỗng:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "if (ctx.description != null && ctx.description.toString().trim().length() == 0) { ctx.remove('description'); }"
  }
}
~~~

Script có thể làm pipeline khó đọc và khó tái sử dụng nếu quá lớn. Ưu tiên processor chuyên dụng cho thao tác phổ biến. Với script:

- Truyền dữ liệu động qua params khi processor hỗ trợ.
- Không ghép input người dùng trực tiếp vào source.
- Xử lý field null hoặc thiếu.
- Giữ script ngắn, xác định và có test.
- Đo chi phí nếu script chạy trên lượng document lớn.

Script processor không phải chỗ để gọi dịch vụ HTTP tùy ý hoặc thực hiện giao dịch với hệ thống khác.

## 6. Enrich processor và enrichment

Enrich processor có thể tra cứu dữ liệu từ một enrich policy đã được tạo và thực thi trước đó. Ví dụ thêm thông tin phân loại đối tác hoặc khu vực từ một tập dữ liệu nội bộ đã index.

Quy trình tổng quát:

1. Tạo enrich policy mô tả match type và field nguồn.
2. Execute policy để tạo enrich index.
3. Thêm enrich processor vào ingest pipeline.
4. Khi ingest document, processor tra cứu giá trị phù hợp và bổ sung field.

Ví dụ processor về mặt ý tưởng:

~~~json
{
  "enrich": {
    "policy_name": "partner-by-code",
    "field": "partnerCode",
    "target_field": "partnerInfo",
    "max_matches": 1
  }
}
~~~

Enrich processor không phải một HTTP client gọi hệ thống đối tác theo từng document. Nó tra cứu dữ liệu đã được chuẩn bị trong Elasticsearch. Khi dữ liệu enrich thay đổi, cần thực thi lại policy theo quy trình cập nhật.

Dùng enrich cho dữ liệu tham chiếu phù hợp với mô hình ingest. Nếu cần gọi API bên ngoài theo thời gian thực, xác thực quyền truy cập, áp dụng fallback hoặc xử lý lỗi nghiệp vụ, ứng dụng nên thực hiện việc đó trước khi gửi document.

## 7. Xử lý lỗi với on_failure

Một processor có thể thất bại vì field thiếu, kiểu dữ liệu sai, ngày không parse được hoặc script phát sinh exception. Mặc định, lỗi processor có thể làm thao tác index document thất bại.

Có thể cấu hình on_failure ở processor hoặc ở cấp pipeline để thực hiện hành động khi xảy ra lỗi.

Ví dụ pipeline đánh dấu lỗi:

~~~http
PUT _ingest/pipeline/product-normalize-with-error-v1
{
  "processors": [
    {
      "convert": {
        "field": "price",
        "type": "long"
      }
    },
    {
      "date": {
        "field": "createdAtRaw",
        "target_field": "createdAt",
        "formats": ["ISO8601"]
      }
    }
  ],
  "on_failure": [
    {
      "set": {
        "field": "ingestError.message",
        "value": "{{_ingest.on_failure_message}}"
      }
    },
    {
      "set": {
        "field": "ingestError.processor",
        "value": "{{_ingest.on_failure_processor_type}}"
      }
    }
  ]
}
~~~

Khi có on_failure ở cấp pipeline, các processor xử lý lỗi được chạy theo cấu hình. Nếu lỗi được xử lý, document có thể tiếp tục qua pipeline và được index. Điều này hữu ích khi muốn lưu document có dấu lỗi để điều tra, nhưng có thể nguy hiểm nếu document chưa hợp lệ vẫn được đưa vào index phục vụ nghiệp vụ.

### 7.1. Xử lý lỗi không đồng nghĩa với dead-letter queue

Ingest pipeline không tự động gửi document lỗi sang Kafka, SQS hoặc một hệ thống queue bên ngoài. on_failure chỉ điều khiển xử lý bên trong pipeline.

Nếu yêu cầu là từ chối dữ liệu sai, để lỗi làm item index thất bại và ứng dụng ghi nhận lỗi. Nếu muốn lưu dữ liệu lỗi để xử lý sau, cần thiết kế riêng một luồng quarantine/dead-letter ở ứng dụng hoặc hạ tầng nhập liệu.

Không chỉ thêm field ingestError rồi mặc định mọi consumer sẽ bỏ qua document lỗi. Các query nghiệp vụ cần biết field đó và loại document không hợp lệ ra khỏi kết quả.

### 7.2. Processor-level on_failure

Có thể gắn on_failure trực tiếp cho một processor:

~~~json
{
  "convert": {
    "field": "price",
    "type": "long",
    "on_failure": [
      {
        "set": {
          "field": "ingestError.price",
          "value": "{{_ingest.on_failure_message}}"
        }
      },
      {
        "remove": {
          "field": "price",
          "ignore_missing": true
        }
      }
    ]
  }
}
~~~

Đây là ví dụ minh họa việc xử lý lỗi tại đúng processor. Hãy quyết định rõ document sau khi lỗi có được phép tiếp tục index hay phải bị từ chối. Không nuốt lỗi bắt buộc mà không tạo tín hiệu để vận hành và ứng dụng phát hiện.

### 7.3. Error metadata

Trong on_failure, Elasticsearch cung cấp metadata như thông điệp lỗi, loại processor, tag và pipeline liên quan trong ingest context. Có thể ghi các giá trị này vào field để điều tra.

Không nên lưu stack trace hoặc thông tin nhạy cảm không cần thiết vào document nghiệp vụ. Thông báo lỗi có thể chứa dữ liệu đầu vào hoặc chi tiết nội bộ; cần giới hạn quyền truy cập và thời gian lưu nếu ghi vào index.

## 8. Tag processor và quan sát pipeline

Có thể gắn tag cho processor:

~~~json
{
  "convert": {
    "tag": "normalize-price",
    "field": "price",
    "type": "long"
  }
}
~~~

Tag giúp nhận diện processor khi debug hoặc phân tích lỗi. Mô tả pipeline nên nêu mục đích, owner và phiên bản.

Quan sát ingest nên gồm:

- Số lượng document được gửi.
- Tỷ lệ item thành công/thất bại.
- Lỗi pipeline theo processor/tag.
- Thời gian bulk request và tốc độ ingest.
- Số lượng document bị quarantine hoặc đánh dấu lỗi.
- Sự thay đổi mapping hoặc tỷ lệ field thiếu.
- Tác động lên CPU và ingest node.

HTTP status của bulk request có thể thành công ở cấp request nhưng một số item vẫn thất bại. Luôn đọc trường errors và kết quả từng item. Không chỉ kiểm tra HTTP 200 rồi kết luận toàn bộ batch đã được index.

## 9. Mô phỏng pipeline trước khi dùng

Simulate API cho phép chạy pipeline với document mẫu mà không ghi document vào index.

~~~http
POST _ingest/pipeline/product-normalize-v1/_simulate
{
  "docs": [
    {
      "_source": {
        "name": "  WIRELESS MOUSE  ",
        "price": "259900",
        "createdAtRaw": "2026-11-13T08:00:00Z"
      }
    }
  ]
}
~~~

Response hiển thị source sau khi chạy pipeline. Có thể bật verbose để xem trạng thái sau từng processor:

~~~http
POST _ingest/pipeline/product-normalize-v1/_simulate?verbose=true
{
  "docs": [
    {
      "_source": {
        "name": "  WIRELESS MOUSE  ",
        "price": "259900",
        "createdAtRaw": "2026-11-13T08:00:00Z"
      }
    }
  ]
}
~~~

Simulate hữu ích để kiểm tra:

- Field đầu vào thiếu.
- Chuỗi có khoảng trắng.
- Kiểu dữ liệu không hợp lệ.
- Định dạng ngày khác nhau.
- Kết quả rename/remove.
- Hành vi on_failure.
- Document có nested object hoặc array.

Simulate không kiểm tra toàn bộ hệ quả của mapping, authorization, bulk retry hoặc nghiệp vụ ứng dụng. Sau simulate, vẫn cần integration test ghi document vào index thử nghiệm và đọc lại kết quả.

## 10. Pipeline được chọn như thế nào?

Pipeline có thể được chọn trực tiếp trong request hoặc cấu hình ở index.

### 10.1. Chỉ định pipeline trong Index API

~~~http
PUT /products/_doc/P-1001?pipeline=product-normalize-v1
{
  "name": "  WIRELESS MOUSE  ",
  "price": "259900",
  "createdAtRaw": "2026-11-13T08:00:00Z"
}
~~~

Pipeline được chỉ định trong request áp dụng cho thao tác index này.

### 10.2. Default pipeline

Có thể cấu hình index dùng default pipeline:

~~~http
PUT /products-v1
{
  "settings": {
    "index.default_pipeline": "product-normalize-v1"
  },
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "price": { "type": "long" },
      "createdAt": { "type": "date" },
      "ingestedAt": { "type": "date" }
    }
  }
}
~~~

Khi request index không chỉ định pipeline khác, Elasticsearch dùng default pipeline của index. Request có thể chỉ định pipeline khác hoặc dùng giá trị đặc biệt _none để bỏ qua default pipeline theo semantics Elasticsearch hỗ trợ.

Default pipeline tiện khi mọi producer ghi vào index cần cùng một bước chuẩn hóa. Tuy nhiên, nó tạo một phụ thuộc ở phía index: producer có thể không biết document đã được biến đổi bởi pipeline nào. Hãy ghi lại pipeline contract và kiểm thử tất cả producer.

### 10.3. Final pipeline

Index có thể cấu hình final pipeline. Final pipeline chạy sau pipeline được chọn từ request hoặc default pipeline và được áp dụng như bước cuối của ingest.

~~~http
PUT /products-v1
{
  "settings": {
    "index.default_pipeline": "product-normalize-v1",
    "index.final_pipeline": "product-audit-v1"
  }
}
~~~

Final pipeline thường được dùng cho các biến đổi bắt buộc ở cấp index mà producer không được bỏ qua. Request không thể vô hiệu hóa final pipeline bằng cách chọn _none cho default pipeline.

| Cấu hình | Vai trò |
|---|---|
| Request pipeline | Pipeline được chỉ định cho một thao tác ghi |
| index.default_pipeline | Pipeline mặc định nếu request không chỉ định pipeline khác |
| index.final_pipeline | Pipeline cuối được áp dụng theo cấu hình index |

Hành vi chi tiết và khả năng thay đổi index settings phụ thuộc Elasticsearch version. Trước khi triển khai, xác nhận thứ tự thực thi và chính sách thay thế pipeline trên đúng phiên bản cluster.

### 10.4. Chỉ định pipeline trong Bulk API

Bulk API có thể chỉ định pipeline cho các thao tác index/create trong request:

~~~http
POST /_bulk?pipeline=product-normalize-v1
{"index":{"_index":"products","_id":"P-1001"}}
{"name":"  WIRELESS MOUSE  ","price":"259900","createdAtRaw":"2026-11-13T08:00:00Z"}
{"index":{"_index":"products","_id":"P-1002"}}
{"name":"  ERGONOMIC KEYBOARD  ","price":"799900","createdAtRaw":"2026-11-13T09:00:00Z"}
~~~

Một request-level pipeline áp dụng cho các thao tác index/create đủ điều kiện trong bulk request. Nếu cần pipeline khác nhau cho các nhóm document, chia thành các bulk request riêng hoặc dùng API/khả năng được phiên bản hỗ trợ và kiểm tra rõ semantics từng item.

Không giả định pipeline được áp dụng giống nhau cho mọi action trong bulk. Đặc biệt, thao tác update trong bulk có semantics khác index/create; xác nhận API tương ứng trước khi thiết kế luồng update.

## 11. Bulk import và xử lý item failure

Trong luồng nhập liệu lớn, pipeline thường được dùng để chuẩn hóa document ngay khi bulk index.

Ví dụ bulk response có thể có:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "P-1001",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-1002",
        "status": 400,
        "error": {
          "type": "document_parsing_exception",
          "reason": "failed to parse field"
        }
      }
    }
  ]
}
~~~

Một số item thành công và một số item thất bại. Ứng dụng nhập liệu cần:

1. Kiểm tra errors.
2. Duyệt từng item result.
3. Ghép item lỗi với source record hoặc business key.
4. Ghi nhận lý do thất bại.
5. Retry có kiểm soát nếu lỗi có thể khắc phục.
6. Đưa record không thể xử lý vào quarantine/dead-letter nếu quy trình yêu cầu.

Không retry toàn bộ batch một cách mù quáng. Index operation với ID cố định thường dễ retry hơn, nhưng script tăng counter, thao tác append hoặc side effect ngoài Elasticsearch có thể không an toàn khi chạy lại.

### 11.1. Chọn kích thước batch

Batch quá nhỏ làm tăng overhead request. Batch quá lớn có thể tăng memory, latency và áp lực lên ingest node.

Không có một con số batch cố định phù hợp với mọi cluster. Hãy đo:

- Kích thước trung bình của document.
- Số document mỗi request.
- Thời gian xử lý processor.
- Bulk item failure rate.
- Queue/rejection của ingest thread pool.
- CPU, heap và network.
- Kích thước response.

Điều chỉnh batch size và concurrency dựa trên metrics. Khi processor như grok, script hoặc enrich tốn CPU, tăng số worker ghi có thể làm ingest node quá tải thay vì tăng throughput.

### 11.2. Retry và idempotency

Ứng dụng cần xác định thao tác retry có an toàn không.

- Ghi snapshot đầy đủ với ID ổn định thường dễ retry hơn.
- Gửi lại partial update gán giá trị cố định có thể idempotent đối với field đó.
- Script cộng dồn hoặc append array có thể tạo kết quả khác nếu chạy hai lần.
- Gọi external API trong ứng dụng có thể tạo side effect lặp nếu không có idempotency key.

Pipeline nên ưu tiên phép biến đổi xác định: cùng một input và cùng phiên bản pipeline tạo ra cùng một output. Điều này giúp retry và reindex dễ dự đoán hơn.

## 12. Gắn pipeline với Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp abstraction để index document. Mức hỗ trợ pipeline trong các kiểu query/operation phụ thuộc phiên bản. Một số API cho phép gắn pipeline vào IndexQuery; nếu dùng Elasticsearch Java API Client trực tiếp, request có thể chỉ định pipeline rõ ràng.

Ví dụ dạng IndexQuery thường gặp trong Spring Data Elasticsearch 5.x:

~~~java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexQuery indexQuery = new IndexQueryBuilder()
    .withId(product.getId())
    .withObject(product)
    .withPipeline("product-normalize-v1")
    .build();

String id = operations.index(
    indexQuery,
    IndexCoordinates.of("products")
);
~~~

Tên package, builder method và hỗ trợ withPipeline có thể thay đổi theo minor version. Hãy kiểm tra IndexQueryBuilder/IndexQuery trong dependency dự án. Nếu API hiện tại không expose pipeline, dùng Elasticsearch Java API Client hoặc REST client được cấu hình cho ứng dụng.

### 12.1. Elasticsearch Java API Client: index một document

Ví dụ request trực tiếp:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;

client.index(request -> request
    .index("products")
    .id(product.getId())
    .pipeline("product-normalize-v1")
    .document(product)
);
~~~

Cách này làm rõ pipeline được gắn vào request index. Cần cấu hình client với endpoint, credentials, TLS và lifecycle phù hợp của ứng dụng.

### 12.2. Elasticsearch Java API Client: bulk index

~~~java
client.bulk(request -> request
    .index("products")
    .pipeline("product-normalize-v1")
    .operations(operation -> operation
        .index(index -> index
            .id(firstProduct.getId())
            .document(firstProduct)
        )
    )
    .operations(operation -> operation
        .index(index -> index
            .id(secondProduct.getId())
            .document(secondProduct)
        )
    )
);
~~~

Ví dụ minh họa request-level pipeline cho bulk index. Builder có thể khác theo client version và cách tạo danh sách operation; kiểm tra BulkRequest.Builder trong dependency thực tế. Sau khi gọi, phải kiểm tra response item-level thay vì chỉ dựa vào việc method trả về bình thường.

### 12.3. Repository save không tự động biết pipeline nào cần dùng

Một lệnh repository.save(entity) thông thường không nhất thiết mang pipeline ID do ứng dụng mong muốn. Nếu index đã cấu hình default/final pipeline, cluster có thể áp dụng theo setting. Nếu pipeline cần chỉ định rõ cho từng loại import, dùng API index/query hỗ trợ pipeline hoặc Java API Client trực tiếp.

Không dựa vào một default pipeline ẩn nếu nhiều producer có yêu cầu khác nhau mà không có hợp đồng rõ ràng.

## 13. Pipeline và mapping: hai lớp khác nhau

Pipeline biến đổi source trước khi indexing. Mapping quy định cách field được lưu trữ và lập chỉ mục.

Ví dụ pipeline convert price thành long không tự bảo đảm mapping của price là long. Nếu mapping hiện tại là keyword, giá trị số vẫn có thể được xử lý theo mapping keyword hoặc gây ra kết quả không mong muốn.

| Thành phần | Trách nhiệm |
|---|---|
| Ingest pipeline | Chuẩn hóa/biến đổi document trước khi index |
| Mapping | Định nghĩa kiểu field, analyzer, doc values và cách index |
| Analyzer | Tokenize và chuẩn hóa text cho tìm kiếm |
| Query | Chọn và xếp hạng document khi search |
| Application mapper | Chuyển API/domain model sang document phù hợp |

Pipeline không thay thế mapping migration. Nếu cần đổi kiểu field đã tồn tại, thường cần index mới với mapping mới rồi reindex dữ liệu.

### 13.1. Pipeline có thể tạo field mới

Processor set hoặc script có thể thêm field. Nếu mapping bật dynamic mapping, Elasticsearch có thể tự tạo mapping cho field mới. Điều này tiện trong thử nghiệm nhưng có thể gây mapping explosion hoặc kiểu field ngoài ý muốn.

Với schema production, nên định nghĩa mapping cho field quan trọng và giới hạn dynamic mapping phù hợp. Pipeline và mapping cần được version hóa, triển khai và kiểm thử cùng nhau.

## 14. Reindex dữ liệu qua pipeline

Pipeline có thể áp dụng cho dữ liệu được chuyển qua Reindex API bằng cách chỉ định pipeline ở destination.

Ví dụ chuyển từ products-v1 sang products-v2 và chuẩn hóa theo pipeline mới:

~~~http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2",
    "pipeline": "product-normalize-v2"
  }
}
~~~

Điều này hữu ích khi muốn áp dụng logic ingest mới lên dữ liệu cũ. Reindex không tự động sửa index nguồn; nó đọc source và ghi document vào index đích qua pipeline được chỉ định.

Trước khi chạy trên dữ liệu lớn:

- Tạo index đích với mapping/settings đúng.
- Simulate pipeline với document đại diện.
- Thử reindex trên tập nhỏ hoặc index thử nghiệm.
- Theo dõi task, failures và tốc độ.
- Xác nhận số document và dữ liệu sau biến đổi.
- Có kế hoạch chuyển alias/đọc ghi và rollback.

Reindex lớn có thể tiêu tốn tài nguyên đáng kể. Không chạy đồng thời nhiều tác vụ nặng nếu cluster chưa được đánh giá tải.

## 15. Giới hạn trách nhiệm của ingest pipeline và ứng dụng

Pipeline là một phần của hạ tầng lưu trữ/search. Ứng dụng là nơi hiểu request, người dùng và quy tắc nghiệp vụ. Chia trách nhiệm rõ giúp tránh đưa logic không phù hợp vào cluster.

| Công việc | Nơi thường phù hợp | Lý do |
|---|---|---|
| Trim, lowercase, rename field | Ingest pipeline hoặc application mapper | Biến đổi dữ liệu cơ học, dùng chung |
| Parse ngày theo format nguồn | Pipeline hoặc ứng dụng | Pipeline phù hợp khi quy tắc đơn giản và nhiều producer cùng dùng |
| Convert kiểu dữ liệu | Pipeline sau khi xác định schema | Cần mapping đích rõ ràng |
| Validate request body | Ứng dụng | Cần trả lỗi phù hợp với API contract |
| Authentication và authorization | Ứng dụng/security layer | Pipeline không thay thế kiểm soát truy cập |
| Tenant isolation | Ứng dụng và query/index design | Không được dựa vào client gửi field tenant tùy ý |
| Kiểm tra business invariant | Ứng dụng/domain service | Cần hiểu trạng thái và quy tắc nghiệp vụ |
| Gọi payment, CRM hoặc API đối tác | Ứng dụng/integration service | Cần timeout, credentials, retry và xử lý side effect |
| Enrich từ dữ liệu tham chiếu đã index | Enrich processor hoặc ứng dụng | Chọn theo freshness và semantics |
| Ghi audit business event | Ứng dụng/event architecture | Cần định danh actor, correlation và chính sách lưu |
| Chuẩn hóa document chung cho nhiều producer | Ingest pipeline | Một quy tắc tập trung ở phía Elasticsearch |
| Query-time ranking và filtering | Query | Không thuộc ingest pipeline |
| Giao dịch xuyên nhiều hệ thống | Application/service architecture | Pipeline không phải distributed transaction coordinator |

### 15.1. Những việc không nên đẩy vào pipeline

Không dùng ingest pipeline để:

- Xác thực người dùng hoặc quyết định quyền truy cập.
- Tin tưởng tenantId, ownerId hoặc role do client tự gửi.
- Thực hiện quy trình thanh toán, đặt hàng hoặc chuyển trạng thái có nhiều bước.
- Gọi API ngoài theo từng document như một phần bắt buộc của giao dịch.
- Gửi email, webhook hoặc tạo side effect không idempotent.
- Thay thế transaction hoặc outbox pattern.
- Trả lỗi nghiệp vụ thân thiện cho HTTP client.
- Làm orchestration giữa nhiều dịch vụ.

Pipeline có thể xử lý một document ở phía Elasticsearch, nhưng không cung cấp transaction xuyên hệ thống và không biết đầy đủ ngữ cảnh nghiệp vụ của request.

### 15.2. Khi nào nên đặt logic trong pipeline?

Pipeline phù hợp khi phép biến đổi:

- Có tính cơ học và xác định.
- Chỉ cần dữ liệu đã có trong document hoặc enrich index.
- Cần dùng nhất quán cho nhiều producer.
- Có thể simulate và kiểm thử độc lập.
- Không phụ thuộc vào quyền của người dùng hay side effect bên ngoài.
- Có thể triển khai/version hóa như cấu hình hạ tầng.

Ví dụ chuẩn hóa tên, parse timestamp, bỏ field import tạm thời hoặc bổ sung metadata ingest là các ứng viên phù hợp.

### 15.3. Khi nào nên giữ logic trong ứng dụng?

Ứng dụng nên chịu trách nhiệm khi logic:

- Cần hiểu người gọi và quyền truy cập.
- Cần truy cập database hoặc service khác.
- Có quy tắc thay đổi theo trạng thái nghiệp vụ.
- Cần bảo đảm idempotency hoặc điều phối retry.
- Cần quyết định trả lỗi 4xx/5xx cụ thể.
- Cần giao dịch, outbox hoặc audit trail.
- Cần bảo vệ dữ liệu nhạy cảm và tenant boundary.

Ứng dụng có thể chuẩn hóa một số field trước khi gửi, sau đó pipeline áp dụng bước chuẩn hóa chung. Nếu cùng một phép biến đổi được thực hiện ở cả hai nơi, hãy xác định một nơi là nguồn chuẩn để tránh kết quả khác nhau.

## 16. Validation trước pipeline và sau pipeline

Ứng dụng nên validate request trước khi gửi document:

- Field bắt buộc có mặt.
- Kiểu dữ liệu hợp lệ.
- Giá trị nằm trong miền nghiệp vụ.
- Caller có quyền ghi document.
- Tenant và document ID được xác định từ context đáng tin cậy.

Pipeline có thể thực hiện kiểm tra kỹ thuật bổ sung khi dữ liệu đến từ nhiều producer, nhưng không nên xem pipeline là lớp authorization.

Sau pipeline, mapping vẫn có thể từ chối document nếu kiểu dữ liệu không tương thích. Vì vậy, integration test nên xác nhận cả output sau processor và khả năng index theo mapping đích.

Nếu pipeline có thể biến đổi field mà ứng dụng đã validate, cần kiểm tra output cuối vẫn thỏa invariant. Ví dụ application xác nhận price là số dương, pipeline convert chuỗi thành long; test cần xác nhận giá trị cuối không bị chuyển đổi sai.

## 17. External enrichment và freshness

Có ba mô hình thường gặp:

1. Ứng dụng gọi dịch vụ ngoài trước khi index, rồi gửi document đã được enrich.
2. Ingest pipeline dùng enrich processor tra cứu enrich index đã chuẩn bị.
3. Hệ thống khác đồng bộ dữ liệu tham chiếu vào Elasticsearch, sau đó pipeline dùng dữ liệu đó.

Chọn mô hình dựa trên freshness và độ tin cậy:

- Nếu dữ liệu cần chính xác theo trạng thái hiện thời của dịch vụ ngoài, ứng dụng có thể phải gọi dịch vụ đó.
- Nếu chấp nhận dữ liệu tham chiếu được đồng bộ theo chu kỳ, enrich processor có thể giảm coupling lúc ingest.
- Nếu enrich index chưa được cập nhật, pipeline có thể dùng dữ liệu cũ cho đến khi policy được execute lại.

Không giả định enrich processor là truy vấn trực tiếp một database nghiệp vụ hoặc API bên ngoài tại thời điểm từng document được ghi.

## 18. Security và quyền quản lý pipeline

Pipeline có thể thay đổi dữ liệu trước khi index. Người có quyền sửa pipeline có thể ảnh hưởng đến mọi producer đang sử dụng pipeline đó.

Một số nguyên tắc vận hành:

- Giới hạn quyền tạo, cập nhật và xóa ingest pipeline.
- Tách quyền ghi document khỏi quyền quản lý pipeline nếu có thể.
- Không để client công khai tùy ý truyền pipeline ID.
- Không cho request người dùng chọn pipeline có thể thay đổi field tenant/security.
- Kiểm soát quyền truy cập vào field error hoặc metadata nhạy cảm.
- Review pipeline changes như code/configuration production.
- Có quy trình rollback và version ID rõ ràng.

Nếu final pipeline được dùng cho biến đổi bắt buộc, cần kiểm tra quyền và luồng triển khai để tránh producer vô tình hoặc cố ý bỏ qua default pipeline nhưng vẫn phải tuân thủ final pipeline.

## 19. Observability và vận hành ingest

Một pipeline tốt cần được vận hành như một thành phần production:

- Đặt tên ID và description rõ.
- Version hóa định nghĩa.
- Lưu pipeline JSON trong source control hoặc hạ tầng configuration.
- Simulate trước khi deploy.
- Kiểm thử với dữ liệu hợp lệ và lỗi.
- Theo dõi item failure của bulk.
- Theo dõi ingest node CPU, queue và rejection.
- Ghi nhận pipeline ID và version trong deployment log.
- Định kỳ loại bỏ pipeline cũ sau khi không còn producer sử dụng.

Elasticsearch có ingest node statistics và pipeline statistics tùy phiên bản. Có thể kiểm tra node stats:

~~~http
GET _nodes/stats/ingest
~~~

Các metrics có thể bao gồm processor count, failed count, current và thời gian thực thi ở mức node/pipeline theo cấu trúc response của phiên bản. Kết hợp với bulk item errors và application logs để xác định nguồn lỗi.

## 20. Kiểm thử pipeline và tích hợp ứng dụng

Nên có nhiều lớp kiểm thử:

### 20.1. Simulate test

Dùng _simulate để kiểm tra processor trên các mẫu document:

- Document đầy đủ.
- Field optional bị thiếu.
- Giá trị sai kiểu.
- Ngày sai format.
- Nested object hoặc array.
- Input có khoảng trắng, ký tự Unicode và chuỗi rỗng.
- Trường hợp processor thất bại.

### 20.2. Integration test

Tạo index thử nghiệm với mapping giống production, tạo pipeline rồi index document qua pipeline. Sau đó đọc document từ Elasticsearch và kiểm tra source/indexed behavior.

Kiểm tra:

- Field được chuẩn hóa.
- Field raw được giữ hoặc xóa đúng ý định.
- Kiểu field tương thích mapping.
- Date được parse đúng instant/timezone.
- Processor lỗi tạo item failure hoặc marker đúng chính sách.
- Bulk response được đọc item-level.
- Default/final/request pipeline được áp dụng đúng thứ tự mong đợi.

### 20.3. Application contract test

Test tầng ứng dụng để xác nhận:

- Request invalid bị từ chối trước khi gọi Elasticsearch.
- Tenant/owner được gán từ context tin cậy.
- Pipeline ID đúng theo loại luồng import.
- Retry không lặp side effect.
- Bulk partial failure được báo cáo theo từng record.
- Lỗi pipeline được chuyển thành response hoặc dead-letter theo hợp đồng.

Simulate test một mình không chứng minh application đã gắn đúng pipeline vào request. Integration test cần xác nhận đường ghi thực tế.

## 21. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Pipeline không chạy | Request không chọn pipeline và index không có default | Kiểm tra request pipeline và index settings |
| Pipeline request không có hiệu lực như mong đợi | Default/final pipeline có thứ tự riêng | Kiểm tra request, default và final pipeline |
| Field bị mất sau ingest | Processor remove/rename hoặc script thay đổi source | Simulate từng processor |
| Convert/date processor làm bulk item thất bại | Input không parse được | Validate trước, cấu hình on_failure có chủ đích |
| Document lỗi vẫn được index | on_failure đã xử lý lỗi và pipeline tiếp tục | Đánh dấu/quarantine rõ hoặc để item thất bại |
| Bulk HTTP request thành công nhưng record thiếu | Một số item lỗi trong response | Kiểm tra errors và từng item |
| Data cũ không được chuẩn hóa | Pipeline chỉ chạy lúc ingest mới | Reindex qua pipeline mới |
| Enrich trả dữ liệu cũ | Enrich policy chưa execute lại | Cập nhật nguồn và execute policy |
| Mapping exception sau pipeline | Output processor không khớp mapping | Đồng bộ pipeline output với mapping |
| Ingest node CPU tăng | Script/grok/enrich hoặc concurrency cao | Đo processor, tối ưu batch và tải |
| Producer ghi dữ liệu khác nhau | Không thống nhất pipeline/default settings | Công bố contract và chỉ định pipeline rõ |
| Retry làm dữ liệu bị nhân đôi | Script append/cộng dồn không idempotent | Thiết kế thao tác retry an toàn |
| Pipeline update làm thay đổi mọi producer | Sửa ID pipeline đang được chia sẻ | Version hóa pipeline và chuyển đổi có kiểm soát |

## 22. Quy trình thiết kế ingest pipeline cho bulk import

Khi triển khai một luồng import:

1. Xác định schema đầu vào và schema index đích.
2. Quyết định field nào ứng dụng phải validate hoặc enrich.
3. Chọn các biến đổi cơ học phù hợp để đặt trong pipeline.
4. Định nghĩa mapping tương thích với output cuối.
5. Tạo pipeline có ID/version rõ ràng.
6. Simulate với mẫu dữ liệu tốt, xấu và biên.
7. Tạo index thử nghiệm và chạy integration test.
8. Chỉ định pipeline trong Index/Bulk API hoặc cấu hình default/final có chủ đích.
9. Kiểm tra từng item trong bulk response.
10. Xây dựng retry/quarantine theo idempotency và loại lỗi.
11. Theo dõi ingest metrics và application logs.
12. Version hóa pipeline khi thay đổi logic; reindex nếu cần chuyển đổi dữ liệu cũ.

Không đưa toàn bộ business workflow vào pipeline chỉ vì pipeline có thể sửa source. Hãy giữ các quyết định phụ thuộc người dùng, quyền truy cập, trạng thái nghiệp vụ và dịch vụ ngoài ở ứng dụng.

## 23. Bảng tra cứu nhanh

| Nhu cầu | Cách làm |
|---|---|
| Chuẩn hóa document trước khi index | Ingest pipeline |
| Chuỗi processor | processors theo thứ tự |
| Thêm/xóa/đổi tên field | set, remove, rename |
| Chuẩn hóa chuỗi | trim, lowercase, uppercase |
| Chuyển kiểu | convert |
| Parse timestamp | date processor |
| Tách log/message | grok hoặc dissect |
| Biến đổi tùy chỉnh | Painless script processor |
| Tra cứu dữ liệu tham chiếu đã index | enrich processor |
| Xử lý lỗi processor | on_failure và error metadata |
| Kiểm tra trước khi ghi | _simulate |
| Áp dụng cho một request | pipeline parameter |
| Pipeline mặc định của index | index.default_pipeline |
| Bước bắt buộc cuối cùng | index.final_pipeline |
| Áp dụng cho bulk index | Bulk API pipeline parameter |
| Chuẩn hóa dữ liệu cũ | Reindex với dest.pipeline |
| Đọc lỗi từng record | Bulk response items và errors |
| Theo dõi ingest node | Nodes ingest stats |
| Xác thực và phân quyền | Application/security layer |
| Quy tắc nghiệp vụ và external API | Application/domain/integration service |

Ingest pipeline phù hợp với các biến đổi document có tính cơ học, xác định và cần dùng chung ở thời điểm ghi. Pipeline không thay thế mapping, query, authorization hay business workflow. Trong Spring Data Elasticsearch, hãy gắn pipeline rõ ràng vào thao tác index/bulk bằng API được phiên bản hỗ trợ; kiểm tra bulk response ở cấp item, simulate trước khi triển khai và version hóa pipeline. Ứng dụng vẫn chịu trách nhiệm xác thực request, phân quyền, quy tắc nghiệp vụ, gọi dịch vụ ngoài, idempotency, retry và phản hồi lỗi.
