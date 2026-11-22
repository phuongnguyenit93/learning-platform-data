# Retry, error tolerance và dead-letter queue theo loại connector

Kafka Connect đưa dữ liệu qua một pipeline gồm connector task, converter, Single Message Transform (SMT) và Kafka client. Lỗi có thể xuất hiện ở nhiều điểm khác nhau. Một lỗi parse JSON trong converter khác với lỗi kết nối database của JDBC Sink, và cả hai lại khác với exception khi source task gọi poll().

Vì vậy, không nên bật retry hoặc error tolerance theo một công thức duy nhất cho mọi connector. Cần xác định loại connector, giai đoạn phát sinh lỗi, khả năng retry của plugin và hậu quả nếu bỏ qua record.

Kafka Connect cung cấp một số cấu hình chung như **errors.tolerance**, **errors.retry.timeout**, **errors.retry.delay.max.ms**, **errors.log.enable** và dead-letter queue (DLQ). Connector plugin có thể bổ sung cơ chế retry riêng. Các cơ chế này có phạm vi khác nhau: framework retry không thay thế retry của connector, DLQ không phải nơi tự động sửa dữ liệu, và source connector không có cùng đường xử lý lỗi như sink connector.

## 1. Pipeline và các điểm có thể phát sinh lỗi

Kafka Connect có hai loại connector chính:

- **Source connector:** đọc dữ liệu từ hệ thống bên ngoài rồi ghi record vào Kafka.
- **Sink connector:** đọc record từ Kafka rồi ghi dữ liệu sang hệ thống bên ngoài.

Pipeline khái quát:

~~~mermaid
flowchart LR
    subgraph SOURCE["Source connector"]
        A["External system"] --> B["SourceTask.poll()"]
        B --> C["SMT"]
        C --> D["Converter"]
        D --> E["Kafka topic"]
    end
    subgraph SINK["Sink connector"]
        F["Kafka topic"] --> G["Converter"]
        G --> H["SMT"]
        H --> I["SinkTask.put()"]
        I --> J["External system"]
        H -. "Record lỗi" .-> K["DLQ"]
    end
~~~

Các điểm lỗi quan trọng:

| Giai đoạn | Source connector | Sink connector |
|---|---|---|
| Kết nối hệ thống ngoài | Lỗi khi mở kết nối hoặc đọc nguồn | Lỗi khi mở kết nối hoặc ghi đích |
| Task poll/put | SourceTask.poll() không đọc được dữ liệu | SinkTask.put() không ghi được batch/record |
| Converter | Chuyển SourceRecord thành Kafka record thất bại | Deserialize Kafka bytes thành Connect data thất bại |
| SMT | Biến đổi SourceRecord thất bại | Biến đổi SinkRecord thất bại |
| Kafka I/O | Gửi record vào Kafka thất bại | Đọc record từ Kafka hoặc commit offset thất bại |

Cùng một exception class có thể có ý nghĩa khác nhau tùy giai đoạn. Ví dụ timeout khi gọi database có thể retry được, nhưng lỗi schema không tương thích thường cần sửa contract hoặc dữ liệu.

### 1.1. Lỗi record và lỗi task

Cần phân biệt:

- **Record-level error:** một record cụ thể không thể deserialize, chuyển đổi hoặc áp dụng SMT.
- **Batch/task-level error:** connector task không thể đọc nguồn, ghi batch hoặc duy trì kết nối.
- **Configuration/plugin error:** thiếu credential, class plugin không tồn tại, cấu hình sai hoặc dependency không tương thích.
- **Infrastructure error:** broker, network, database hoặc object storage gặp sự cố.

Framework error handling có thể xử lý một số lỗi trong pipeline record. Nó không biến mọi lỗi task hoặc lỗi cấu hình thành một record riêng để gửi DLQ.

Ví dụ, một SinkTask ghi một batch 200 record và database trả lỗi transaction. Connector có thể retry cả batch vì chưa xác định được record nào gây lỗi. Nếu plugin ném lỗi task-level, Connect có thể retry hoặc đánh dấu task FAILED tùy loại exception và cơ chế của plugin. Không nên mặc định DLQ sẽ luôn tách được một dòng lỗi khỏi batch.

## 2. Source connector và sink connector có đường xử lý lỗi khác nhau

### 2.1. Source connector

Source connector đọc từ database, filesystem, API hoặc hệ thống khác rồi tạo SourceRecord.

Luồng xử lý:

~~~text
External source
    |
    v
SourceTask.poll()
    |
    v
SourceRecord
    |
    v
SMT
    |
    v
Key/value/header converter
    |
    v
Kafka producer
    |
    v
Kafka topic
~~~

Ví dụ với JDBC Source:

- Database không kết nối được: lỗi đọc nguồn hoặc lỗi task.
- Query timeout: connector có thể retry theo cấu hình plugin hoặc ném RetriableException.
- SourceRecord có field không phù hợp converter: lỗi converter.
- SMT truy cập field không tồn tại: lỗi transformation.
- Kafka broker unavailable: lỗi publish vào Kafka, không phải lỗi dữ liệu nguồn.

**errors.tolerance** có thể áp dụng cho những giai đoạn xử lý record được framework hỗ trợ như converter và SMT. Nếu source record bị bỏ qua do lỗi ở các giai đoạn này, dữ liệu đó có thể không được phát vào Kafka. Đây là hành vi cần được giám sát và chấp nhận rõ ràng.

Built-in dead-letter queue của Kafka Connect được thiết kế cho sink connector. Không nên cấu hình **errors.deadletterqueue.topic.name** rồi giả định source connector sẽ tự động chuyển SourceRecord lỗi sang DLQ. Với source connector, cần xem xét khả năng retry/error handling riêng của plugin, log, source-side quarantine hoặc một luồng xử lý lỗi do ứng dụng xây dựng.

Lỗi trong **SourceTask.poll()** xảy ra trước khi worker nhận được một record cụ thể để đưa vào DLQ. Connector phải xử lý việc đọc lại, checkpoint và source offset sao cho không bỏ mất dữ liệu.

### 2.2. Sink connector

Sink connector đọc record từ Kafka, chuyển đổi, áp dụng SMT rồi gửi dữ liệu tới hệ thống đích.

~~~text
Kafka topic
    |
    v
Consumer fetch
    |
    v
Key/value/header converter
    |
    v
SMT
    |
    v
SinkRecord
    |
    v
SinkTask.put()
    |
    v
External destination
~~~

Ví dụ với JDBC Sink:

- JSON/Avro không deserialize được: lỗi converter.
- SMT đổi kiểu field thất bại: lỗi transformation.
- Cột đích không tồn tại: có thể là lỗi schema hoặc lỗi khi plugin ghi database.
- Database tạm thời unavailable: lỗi kết nối/ghi đích.
- Vi phạm unique constraint: có thể là dữ liệu xung đột hoặc một thao tác cần idempotency.

Kafka Connect hỗ trợ DLQ cho sink processing errors mà framework có thể xác định và báo cáo theo record. Tuy nhiên, nếu connector ném lỗi khi ghi một batch trong **put()**, hành vi retry hoặc tolerance còn phụ thuộc cách plugin triển khai và cách lỗi được báo cáo. Một batch failure không nhất thiết được phân loại thành một record lỗi duy nhất.

Vì vậy, hãy kiểm tra tài liệu connector cụ thể và thử nghiệm lỗi thực tế trước khi dựa vào DLQ như cơ chế cách ly mọi lỗi ghi đích.

## 3. Phân loại lỗi trước khi chọn retry

Không phải lỗi nào cũng nên retry.

| Nhóm lỗi | Ví dụ | Hướng xử lý thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Network timeout, connection reset, HTTP 503 | Retry hữu hạn với backoff |
| Rate limit | HTTP 429, API quota | Retry theo Retry-After hoặc backoff có jitter |
| Lỗi dữ liệu | JSON sai cú pháp, field bắt buộc bị thiếu | Cách ly/DLQ nếu là sink record; sửa dữ liệu trước replay |
| Lỗi schema | Schema Registry không tìm thấy schema ID, schema không tương thích | Kiểm tra schema và rollout; retry chỉ khi lỗi registry tạm thời |
| Lỗi nghiệp vụ | Trạng thái đích không cho phép chuyển đổi | Chính sách nghiệp vụ, quarantine hoặc bù trừ |
| Lỗi cấu hình | Credential sai, ACL thiếu, endpoint sai | Sửa cấu hình; retry vô hạn không giải quyết |
| Lỗi plugin | Connector class hoặc dependency không tương thích | Sửa cài đặt/plugin version |
| Lỗi nguồn | Query hoặc snapshot không thể thực hiện | Dùng cơ chế retry/checkpoint của plugin |

Một nguyên tắc hữu ích:

- Retry khi nguyên nhân có khả năng tự hết sau một khoảng thời gian.
- DLQ/quarantine khi một record cụ thể không thể xử lý tự động nhưng cần giữ lại để điều tra.
- Dừng task và cảnh báo khi cấu hình hoặc hạ tầng khiến mọi record đều thất bại.
- Không bỏ qua lỗi nếu dữ liệu đó cần thiết cho tính toàn vẹn nghiệp vụ.

## 4. Error tolerance của Kafka Connect

Kafka Connect cung cấp thuộc tính **errors.tolerance** để quyết định cách framework phản ứng với những lỗi thuộc phạm vi error handling.

Hai giá trị thường dùng:

| Giá trị | Hành vi |
|---|---|
| none | Không dung thứ lỗi; lỗi không được recover có thể làm task thất bại |
| all | Bỏ qua lỗi sau khi áp dụng chính sách retry/error reporting tương ứng |

Giá trị mặc định là **none**.

**errors.tolerance=all** không có nghĩa mọi lỗi của connector đều được sửa hoặc mọi lỗi đều được đưa vào DLQ. Nó chỉ áp dụng cho các giai đoạn mà framework có thể xử lý theo cơ chế này. Task-level failure, lỗi cấu hình hoặc lỗi hạ tầng vẫn có thể làm task dừng.

### 4.1. Khi nào dùng none?

Dùng **none** khi:

- Mỗi record đều quan trọng và không được bỏ qua.
- Dữ liệu lỗi phải làm pipeline dừng để điều tra.
- Chưa có DLQ hoặc quy trình quarantine/replay.
- Hệ thống đích yêu cầu tính toàn vẹn nghiêm ngặt.
- Việc tiếp tục sau một lỗi có thể tạo trạng thái sai.

Ưu điểm là lỗi dễ được phát hiện và không bị che giấu. Đổi lại, một record lỗi có thể làm task ngừng tiến triển cho đến khi được xử lý.

### 4.2. Khi nào dùng all?

Dùng **all** khi:

- Đã xác định loại lỗi có thể bỏ qua hoặc cách ly.
- Sink connector có DLQ được vận hành và giám sát.
- Có quy trình sửa dữ liệu và replay.
- Nghiệp vụ chấp nhận luồng chính tiếp tục trong khi record lỗi được xử lý riêng.
- Đã hiểu ảnh hưởng đến ordering và offset.

Không bật **all** một cách máy móc. Nếu không có DLQ và log phù hợp, record có thể bị bỏ qua mà đội vận hành không nhận ra.

## 5. Retry của framework: errors.retry.timeout

**errors.retry.timeout** xác định tổng khoảng thời gian tối đa framework tiếp tục retry một lỗi thuộc phạm vi error handling trước khi áp dụng tolerance/recovery.

Các nguyên tắc:

- Giá trị **0** nghĩa là không chờ retry theo cơ chế này.
- Giá trị dương giới hạn thời gian retry.
- Một số phiên bản Kafka Connect hỗ trợ **-1** để retry vô hạn; cần kiểm tra phiên bản và cân nhắc kỹ trước khi sử dụng.
- Hết thời gian retry không đồng nghĩa dữ liệu đã được sửa; framework chuyển sang hành vi theo **errors.tolerance** và reporter được cấu hình.

Ví dụ cấu hình hữu hạn:

~~~properties
errors.retry.timeout=60000
errors.retry.delay.max.ms=10000
~~~

Trong ví dụ, framework được phép retry tối đa khoảng 60 giây cho lỗi thuộc phạm vi hỗ trợ. Khoảng chờ giữa các lần retry tăng dần nhưng bị giới hạn bởi **errors.retry.delay.max.ms**.

Không nhầm thuộc tính này với retry riêng của plugin. Một JDBC Sink có thể có **max.retries** riêng cho thao tác database. Hai cơ chế có thể nằm ở hai tầng khác nhau.

### 5.1. Backoff và giới hạn retry

Retry liên tục có thể làm hệ thống đang lỗi quá tải nặng hơn. Backoff tạo khoảng chờ giữa các lần thử.

Ví dụ minh họa:

~~~text
Lần thử 1: thất bại
    chờ 500 ms
Lần thử 2: thất bại
    chờ 1 giây
Lần thử 3: thất bại
    chờ 2 giây
Lần thử 4: thất bại
    chờ 4 giây
...
Không vượt quá errors.retry.delay.max.ms
~~~

Thời gian thực tế phụ thuộc implementation và phiên bản. Không nên dựa vào sơ đồ trên để tính chính xác lịch retry của một connector.

### 5.2. Retry vô hạn có thể tạo backlog

Nếu lỗi kéo dài và retry vô hạn:

- Sink task có thể giữ record/batch chưa xử lý.
- Consumer lag tăng.
- Partition bị chặn ở tiến độ chưa commit.
- Các record sau cùng partition có thể không được giao tới bước ghi đích.
- Dung lượng Kafka và hệ thống downstream chịu áp lực kéo dài.
- Một lỗi cấu hình cố định có thể làm pipeline không bao giờ phục hồi.

Chỉ cân nhắc retry vô hạn khi hệ thống có cảnh báo, giới hạn tài nguyên và runbook xử lý outage. Với lỗi dữ liệu vĩnh viễn, retry vô hạn chỉ trì hoãn việc phát hiện nguyên nhân.

## 6. Retry riêng của connector plugin

Connector plugin hiểu hệ thống nguồn/đích nên thường có cấu hình retry riêng. Các thuộc tính này không thống nhất giữa các connector.

Ví dụ, JDBC Sink có thể cung cấp:

~~~properties
max.retries=10
retry.backoff.ms=3000
~~~

Các thuộc tính minh họa này điều khiển số lần thử lại và khoảng chờ cho một số thao tác database theo implementation của JDBC Sink. Tên, default và phạm vi có thể khác theo phiên bản connector.

Một số điểm cần phân biệt:

| Cơ chế | Chủ thể | Phạm vi |
|---|---|---|
| errors.retry.timeout | Kafka Connect framework | Lỗi ở các stage record được framework quản lý |
| errors.retry.delay.max.ms | Kafka Connect framework | Giới hạn delay retry framework |
| max.retries | Connector plugin nếu hỗ trợ | Thao tác riêng của connector |
| retry.backoff.ms | Connector plugin nếu hỗ trợ | Khoảng chờ retry của plugin |
| Task restart policy | Connect worker/cluster | Khởi động lại task sau task failure |

Không phải mọi connector đều có **max.retries** hoặc **retry.backoff.ms**. Đọc tài liệu đúng plugin và đúng version trước khi đưa cấu hình vào connector JSON.

### 6.1. Ví dụ cấu hình JDBC Sink

Một cấu hình minh họa:

~~~json
{
  "name": "orders-jdbc-sink",
  "config": {
    "connector.class": "io.confluent.connect.jdbc.JdbcSinkConnector",
    "tasks.max": "2",
    "topics": "orders",
    "connection.url": "jdbc:postgresql://db:5432/orders",
    "connection.user": "connect_user",
    "connection.password": "__DB_PASSWORD_FROM_SECRET_PROVIDER__",
    "insert.mode": "upsert",
    "pk.mode": "record_key",
    "pk.fields": "order_id",
    "max.retries": "10",
    "retry.backoff.ms": "3000",
    "errors.tolerance": "all",
    "errors.retry.timeout": "60000",
    "errors.retry.delay.max.ms": "10000",
    "errors.log.enable": "true",
    "errors.log.include.messages": "false",
    "errors.deadletterqueue.topic.name": "orders-jdbc-dlq",
    "errors.deadletterqueue.topic.replication.factor": "3",
    "errors.deadletterqueue.context.headers.enable": "true"
  }
}
~~~

Đây là ví dụ cấu trúc, không phải cấu hình dùng nguyên xi cho mọi môi trường. Cần xác nhận:

- Connector plugin có hỗ trợ các thuộc tính JDBC được nêu không.
- Converter và schema phù hợp với kiểu dữ liệu database.
- insert.mode, pk.mode và pk.fields phù hợp với khóa nghiệp vụ; ví dụ pk.fields=order_id giả định key có schema chứa field order_id.
- DLQ topic đã tồn tại hoặc worker có quyền tạo topic theo policy.
- Worker có quyền ghi DLQ và consumer vận hành có quyền đọc.
- Số partition, replication factor, retention và quota của DLQ phù hợp.
- Cấu hình secret không bị lưu plaintext trong connector config hoặc log.

**errors.tolerance=all** chỉ nên bật sau khi đã định nghĩa rõ record nào được phép cách ly và cách replay. Nếu lỗi xảy ra trong thao tác **put()** của plugin, hãy xác minh bằng integration test xem plugin retry, worker retry hay task restart; không suy ra từ ví dụ rằng mọi lỗi database sẽ tự thành một DLQ record.

## 7. Logging và quan sát lỗi

Kafka Connect có thể ghi lại lỗi qua các thuộc tính:

~~~properties
errors.log.enable=true
errors.log.include.messages=false
~~~

- **errors.log.enable** bật việc ghi log lỗi trong pipeline được hỗ trợ.
- **errors.log.include.messages** quyết định có đưa nội dung record vào log lỗi hay không.

Không nên bật include.messages rộng rãi nếu record chứa PII, token, thông tin thanh toán hoặc dữ liệu nhạy cảm. Log có thể được chuyển tới hệ thống tập trung và có retention/access policy khác Kafka.

Logging giúp chẩn đoán nhưng không thay thế DLQ. Nếu record bị skip và không có log hoặc metric phù hợp, lỗi có thể bị che khuất.

### 7.1. Nội dung log cần truy vết

Nên thu thập:

- Connector name và task ID.
- Connector type: source hoặc sink.
- Stage phát sinh lỗi.
- Exception class và message đã được làm sạch.
- Topic, partition, offset nếu record đã có metadata Kafka.
- Key hoặc event ID theo chính sách dữ liệu.
- Retry attempt và elapsed time nếu có.
- Thời điểm lỗi.
- Trạng thái task và nguyên nhân restart.

Không log credential, payload nhạy cảm hoặc raw record nếu không có nhu cầu và kiểm soát truy cập phù hợp.

## 8. Dead-letter queue của Kafka Connect

DLQ là topic riêng để lưu record sink không thể xử lý theo pipeline thông thường nhưng được phép cách ly.

Cấu hình cơ bản:

~~~properties
errors.tolerance=all
errors.deadletterqueue.topic.name=orders-dlq
errors.deadletterqueue.topic.replication.factor=3
errors.deadletterqueue.context.headers.enable=true
~~~

DLQ hữu ích khi một số record không thể chuyển đổi hoặc áp dụng transformation, nhưng sink pipeline vẫn cần tiếp tục với các record hợp lệ.

DLQ không tự động:
- Sửa payload.
- Thay đổi schema.
- Đảm bảo record được replay.
- Bảo đảm thứ tự giữa topic gốc và DLQ.
- Thay thế backup hoặc source of truth.
- Giải quyết mọi task-level failure.

### 8.1. Cấu hình DLQ theo sink connector

Ví dụ:

~~~properties
connector.class=io.confluent.connect.jdbc.JdbcSinkConnector
topics=orders
errors.tolerance=all
errors.deadletterqueue.topic.name=orders-jdbc-dlq
errors.deadletterqueue.context.headers.enable=true
errors.log.enable=true
errors.log.include.messages=false
~~~

Tên topic DLQ phải duy nhất hoặc có quy ước rõ nếu nhiều connector cùng gửi lỗi. Có thể dùng DLQ riêng theo connector/domain để phân quyền, retention và replay độc lập.

Không nên để mọi connector ghi vào một DLQ chung nếu không có metadata, quota và consumer vận hành đủ mạnh để phân loại lỗi.

### 8.2. Context headers

Khi bật **errors.deadletterqueue.context.headers.enable**, Connect có thể gắn headers mô tả nguồn gốc và lỗi. Tùy phiên bản, các header có thể chứa thông tin như:

- Connector/task phát sinh lỗi.
- Original topic, partition và offset.
- Exception class và message.
- Stage hoặc context xử lý.
- Metadata liên quan tới record gốc.

Tên và tập header phụ thuộc phiên bản. Hãy kiểm tra record thực tế trong DLQ và tài liệu version đang triển khai thay vì hard-code tên header nội bộ.

Context headers giúp xác định record gốc, nhưng có thể làm lộ thông tin lỗi hoặc metadata nhạy cảm. Kiểm soát quyền đọc DLQ và log như dữ liệu production.

### 8.3. Key và value trong DLQ

DLQ thường giữ dữ liệu record gốc dưới dạng phù hợp để điều tra và replay, cùng metadata lỗi trong headers. Nếu lỗi xảy ra khi deserialize, record có thể không có object Connect đã chuyển đổi; cần giữ khả năng truy cập raw bytes.

Consumer DLQ nên có khả năng đọc đúng serializer hoặc xử lý raw byte. Không giả định mọi DLQ record đều deserialize được bằng cùng value converter của topic gốc.

### 8.4. DLQ topic cần được vận hành như topic production

Đặt các thuộc tính rõ ràng:

- Replication factor phù hợp.
- Số partition đủ cho tải DLQ.
- Retention đủ dài để điều tra và replay.
- ACL giới hạn quyền đọc/ghi.
- Quota và cảnh báo khi backlog tăng.
- Quy trình xóa dữ liệu theo chính sách lưu trữ.
- Theo dõi DLQ producer failure.

Nếu worker không thể publish vào DLQ do ACL, broker hoặc topic không tồn tại, quá trình recover cũng có thể thất bại và task tiếp tục lỗi. DLQ không phải nơi miễn nhiễm với sự cố hạ tầng.

## 9. Ordering và offset khi một record bị đưa vào DLQ

Khi một record lỗi được cách ly và sink tiếp tục với record sau, consumer offset của topic nguồn có thể tiến qua record đó theo chính sách recovery.

Ví dụ:

~~~text
orders partition 0:
offset 100: order-1 -> ghi database thành công
offset 101: order-2 -> lỗi converter, chuyển DLQ
offset 102: order-3 -> ghi database thành công

orders-jdbc-dlq:
record gốc offset 101: order-2
~~~

Main sink đã xử lý offset 102 trong khi order-2 chưa được ghi database. Khi replay DLQ sau này, order-2 có thể được áp dụng sau order-3.

Nếu các record cùng key cần đúng thứ tự, việc bỏ qua một record và tiếp tục có thể tạo trạng thái nghiệp vụ sai. Hãy dùng version/sequence trong event, idempotent upsert, hoặc holdback/stop policy tùy yêu cầu.

### 9.1. DLQ không phải retry queue theo thứ tự

Retry topic thường biểu thị record sẽ được thử lại sau delay. DLQ biểu thị record đã bị cách ly khỏi luồng xử lý tự động theo policy hiện tại.

Không replay DLQ mù quáng vào topic gốc. Cần xác định:
- Nguyên nhân đã được khắc phục chưa?
- Record có còn hợp lệ về mặt nghiệp vụ?
- Các version sau đã được áp dụng chưa?
- Replay có gây duplicate side effect không?
- Có cần chạy bù trừ hoặc rebuild state không?

### 9.2. Idempotency trước replay

Sink đích nên có khóa idempotency hoặc upsert theo business key nếu có thể. Ví dụ JDBC Sink có thể dùng **insert.mode=upsert** cùng primary key phù hợp, nhưng vẫn cần đánh giá semantics cập nhật và thứ tự version.

Nếu replay record cũ sau record mới, upsert đơn thuần có thể ghi đè state mới. Có thể cần câu lệnh conditional update theo version hoặc xử lý replay qua một service có kiểm tra trạng thái.

## 10. Source connector: xử lý lỗi khi đọc nguồn

Với source connector, dữ liệu được lấy từ hệ thống bên ngoài. Các tình huống thường gặp:

| Lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Kết nối nguồn | Database/API unavailable | Retry theo plugin, reconnect và backoff |
| Query/read | Query timeout, cursor invalid | Điều chỉnh query, timeout hoặc checkpoint |
| Snapshot | Snapshot quá tải hoặc schema thay đổi | Dùng snapshot/recovery policy của plugin |
| Source offset | Offset không hợp lệ hoặc bị mất | Phục hồi checkpoint theo tài liệu connector |
| SMT/converter | Field không đúng kiểu hoặc transform lỗi | Framework tolerance/log; kiểm tra record trước khi skip |
| Kafka publish | Broker unavailable hoặc authorization failure | Producer retry và xử lý task theo worker/plugin |

Lỗi **poll()** không nhất thiết gắn với một SourceRecord cụ thể. Khi source task không thể đọc dữ liệu, không có record nào để DLQ theo cơ chế sink. Connector cần giữ source offset/checkpoint đúng để có thể đọc lại sau khi phục hồi.

### 10.1. Không skip lỗi nguồn chỉ để task luôn RUNNING

Nếu source connector bỏ qua một đoạn dữ liệu vì query hoặc parse lỗi, Kafka có thể không bao giờ nhận các record đó. Task RUNNING không đồng nghĩa dữ liệu đầy đủ.

Với dữ liệu quan trọng:
- Theo dõi source offset và watermark.
- Đối soát số lượng bản ghi giữa nguồn và Kafka.
- Kiểm tra snapshot/binlog/CDC position.
- Dùng connector-native retry và recovery.
- Ghi lại các record lỗi ở nguồn nếu plugin hỗ trợ.
- Có quy trình backfill từ hệ thống nguồn.

## 11. Connector-specific error handling

Mỗi plugin có semantics riêng. Cần đọc cấu hình và tài liệu theo connector class/version.

| Loại connector | Ví dụ lỗi | Cơ chế cần kiểm tra |
|---|---|---|
| JDBC Source | Database timeout, query lỗi | Connection retry, poll/query interval, source offset |
| Debezium Source | Lỗi snapshot, schema hoặc log position | Snapshot/recovery policy, connector-specific error handling |
| JDBC Sink | Constraint violation, database unavailable | Plugin retry, batch semantics, Connect tolerance/DLQ |
| S3 Sink | Upload/multipart failure, schema/format issue | Retry upload, flush/rotation, task recovery và DLQ stage |
| Elasticsearch Sink | Mapping conflict, cluster unavailable | Plugin retry, bulk response handling, DLQ behavior |
| HTTP Sink | Rate limit, timeout, 4xx/5xx | Plugin retry, Retry-After, dead-letter policy của plugin |

Không suy rộng cấu hình của JDBC Sink sang Debezium, S3 hoặc Elasticsearch. Một plugin có thể retry HTTP 429 theo cách riêng, plugin khác có thể fail task ngay khi nhận response 400.

### 11.1. JDBC Sink: lỗi dữ liệu và lỗi kết nối

Ví dụ:

- Database down: lỗi tạm thời, retry có backoff.
- Unique constraint violation: có thể là duplicate hoặc xung đột nghiệp vụ; cần xác định có thể upsert hay không.
- Column không tồn tại: lỗi schema/configuration; retry không giải quyết cho đến khi schema được sửa.
- Null ở cột NOT NULL: lỗi dữ liệu; cần quarantine hoặc sửa producer.
- Transaction deadlock: có thể retry toàn transaction nếu connector hỗ trợ.

Đối với batch, một record lỗi có thể làm cả batch thất bại. Hãy kiểm tra connector có hỗ trợ batch splitting, retry từng record hoặc báo cáo lỗi theo record hay không.

### 11.2. Debezium Source: checkpoint và phục hồi

Debezium là source connector đọc transaction log hoặc snapshot từ database. Khi gặp lỗi, cần phân biệt:

- Không thể kết nối database.
- Snapshot thất bại.
- Log position/offset không hợp lệ.
- Schema history không đọc được.
- SMT/converter không xử lý được record đã tạo.

Source offset và schema history là thành phần phục hồi quan trọng. Không reset offset hoặc xóa schema history chỉ để làm task khởi động lại nếu chưa hiểu tác động đến CDC completeness.

### 11.3. S3 hoặc object storage Sink

Lỗi upload có thể liên quan network, credential, bucket policy, multipart upload hoặc format writer. Plugin có thể chỉ commit offset sau khi file/object được ghi thành công.

Cần xem xét:
- Retry của SDK và connector.
- Flush size/time.
- File rotation và partitioner.
- Partial upload cleanup.
- Idempotency của object naming.
- Dữ liệu lỗi format có được DLQ theo stage hay làm task fail.

## 12. Cấu hình worker và connector

Kafka Connect chạy ở standalone hoặc distributed mode. Các thuộc tính error handling thường được đặt trong worker configuration và một số cấu hình có thể được cung cấp/override theo connector tùy phiên bản và cách triển khai.

Worker config minh họa:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
group.id=connect-cluster
config.storage.topic=connect-configs
offset.storage.topic=connect-offsets
status.storage.topic=connect-status

key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=false

errors.tolerance=none
errors.retry.timeout=30000
errors.retry.delay.max.ms=5000
errors.log.enable=true
errors.log.include.messages=false
~~~

Cấu hình worker tạo baseline chung. Với từng connector, cần kiểm tra cách version Kafka Connect hiện tại áp dụng các thuộc tính **errors.*** và khả năng override connector-level. Không đưa một giá trị **all** thành default cho toàn cluster nếu các connector có yêu cầu toàn vẹn khác nhau.

Có thể triển khai một worker baseline nghiêm ngặt, sau đó bật tolerance/DLQ riêng cho sink connector đã có runbook. Cách đặt property cụ thể cần tuân theo deployment model và version.

Nếu REST API từ chối một thuộc tính **errors.*** trong connector config, đặt thuộc tính đó ở worker configuration theo đúng phiên bản Connect đang chạy. Việc connector JSON được chấp nhận không chứng minh plugin hỗ trợ mọi thuộc tính retry; kiểm tra cấu hình hiệu lực và hành vi thực tế sau khi triển khai.

### 12.1. Kiểm tra cấu hình hiệu lực

Sau khi tạo hoặc cập nhật connector, kiểm tra cấu hình qua REST API:

~~~bash
curl -s http://connect-worker:8083/connectors/orders-jdbc-sink/config
~~~

Kiểm tra trạng thái:

~~~bash
curl -s http://connect-worker:8083/connectors/orders-jdbc-sink/status
~~~

Các endpoint trên là ví dụ cho REST API mặc định. Môi trường production có thể dùng TLS, authentication, reverse proxy hoặc endpoint khác.

Không chỉ kiểm tra HTTP 200 khi tạo connector. Cần xác minh task state, worker logs, DLQ và dữ liệu thực tế ở đích.

## 13. Quy trình replay DLQ có kiểm soát

Một quy trình replay an toàn:

1. Đọc DLQ và thống kê theo connector, stage, exception và topic gốc.
2. Phân loại lỗi dữ liệu, lỗi schema, lỗi hạ tầng và lỗi nghiệp vụ.
3. Khắc phục nguyên nhân ở producer, schema, SMT hoặc hệ thống đích.
4. Xác định record có còn hợp lệ và chưa bị áp dụng hay chưa.
5. Đọc original topic/partition/offset và event ID từ headers.
6. Sắp xếp record theo key và version nếu nghiệp vụ cần ordering.
7. Chạy thử trên môi trường staging hoặc tập dữ liệu nhỏ.
8. Replay với tốc độ giới hạn.
9. Theo dõi duplicate, task lag và lỗi mới.
10. Đối soát trạng thái đích sau replay.
11. Chỉ xóa/expire DLQ theo retention và quy trình lưu trữ đã duyệt.

Có thể replay vào topic gốc hoặc topic recovery riêng. Nếu replay vào topic gốc, record mới sẽ có offset mới và có thể được xử lý sau các event hiện tại. Cần hiểu rõ tác động ordering và idempotency.

## 14. Monitoring và cảnh báo

Không chỉ theo dõi connector status RUNNING. Cần theo dõi tiến độ, lỗi và backlog.

| Chỉ số/dấu hiệu | Ý nghĩa |
|---|---|
| Connector/task state | Task có đang RUNNING, PAUSED hay FAILED |
| Source record poll rate | Tốc độ đọc từ hệ thống nguồn |
| Source record write rate | Tốc độ ghi record vào Kafka |
| Sink record read rate | Tốc độ consumer đọc record |
| Sink record send rate | Tốc độ ghi record sang đích |
| Consumer lag | Khoảng cách giữa offset đọc và log end offset |
| Retry count/latency | Mức độ lỗi tạm thời và thời gian phục hồi |
| DLQ produce rate | Tốc độ record bị cách ly |
| DLQ topic lag/size | Backlog lỗi chưa được xử lý |
| Task restart count | Task có crash/restart lặp lại không |
| Error stage distribution | Converter, SMT, connector hay Kafka I/O đang lỗi |
| Source offset progress | Source checkpoint có tiến triển không |

Tên metric cụ thể phụ thuộc phiên bản Kafka Connect, connector plugin và metrics reporter. Có thể kết hợp JMX, Prometheus exporter, REST API và log.

### 14.1. Cảnh báo nên có

- Task FAILED hoặc restart liên tục.
- Source offset không tiến triển quá ngưỡng.
- Sink consumer lag tăng liên tục.
- DLQ xuất hiện record mới hoặc backlog vượt ngưỡng.
- Retry duration vượt SLA.
- Tỷ lệ record bị skip tăng đột biến.
- DLQ producer không thể publish.
- Connector RUNNING nhưng throughput bằng 0 trong thời gian bất thường.

Một connector RUNNING với **errors.tolerance=all** vẫn có thể bỏ qua nhiều record. Cần đo tỷ lệ lỗi/skip thay vì chỉ nhìn trạng thái task.

## 15. Bảo mật và quản trị DLQ

DLQ thường chứa record không thể xử lý và metadata exception. Nội dung có thể chứa dữ liệu nhạy cảm hoặc thông tin nội bộ.

Cần:

- ACL write cho Connect worker trên DLQ topic.
- ACL read chỉ cho nhóm vận hành/replay cần thiết.
- TLS và authentication cho producer/consumer.
- Encryption at rest theo chính sách cluster.
- Retention và deletion policy rõ ràng.
- Không đưa payload vào log nếu không cần.
- Không lưu credential trong connector config plaintext.
- Mask hoặc loại bỏ PII trước khi gửi DLQ nếu policy yêu cầu.
- Audit mọi thao tác replay và xóa record.

Context headers có thể tiết lộ exception message, hostname hoặc metadata của hệ thống nguồn/đích. Kiểm tra trước khi cho phép nhiều nhóm truy cập DLQ.

## 16. Runbook khi connector phát sinh lỗi

### Tình huống A: Sink task FAILED do database unavailable

1. Kiểm tra database health, DNS, network và credential.
2. Xác định lỗi là timeout tạm thời hay authentication/configuration.
3. Kiểm tra plugin retry và Connect error retry có đang hoạt động không.
4. Theo dõi consumer lag và task restart.
5. Phục hồi database.
6. Xác minh task RUNNING và sink throughput tăng trở lại.
7. Đối soát record chưa ghi và record đã retry.

Không chuyển sang **errors.tolerance=all** chỉ để task hiển thị RUNNING nếu lỗi là toàn bộ database unavailable.

### Tình huống B: Một số record bị lỗi converter

1. Xác định topic, partition, offset và schema/format.
2. Kiểm tra converter và schema registry.
3. Xác định lỗi do dữ liệu sai hay do registry tạm thời.
4. Nếu là sink connector và policy cho phép, dùng DLQ để cách ly record.
5. Lưu raw bytes và metadata gốc.
6. Sửa producer/schema hoặc dữ liệu.
7. Replay sau khi kiểm tra idempotency và ordering.

### Tình huống C: DLQ tăng nhanh

1. Nhóm lỗi theo connector, stage và exception.
2. Kiểm tra deployment hoặc schema rollout gần nhất.
3. Kiểm tra hệ thống đích và plugin version.
4. Xác định lỗi có ảnh hưởng nhiều key hay chỉ một nhóm record.
5. Tạm dừng hoặc giới hạn connector nếu replay/skip có thể gây sai dữ liệu.
6. Khắc phục nguyên nhân.
7. Replay theo batch nhỏ và đối soát.

### Tình huống D: Source task không tiến triển

1. Kiểm tra task state và log SourceTask.poll().
2. Kiểm tra database/API nguồn và checkpoint.
3. Kiểm tra source offset và snapshot/binlog position.
4. Phân biệt lỗi poll với lỗi SMT/converter sau poll.
5. Dùng connector-native recovery.
6. Đối soát dữ liệu nguồn với topic sau khi phục hồi.

## 17. Anti-patterns thường gặp

- **Bật errors.tolerance=all trên mọi worker:** lỗi dữ liệu có thể bị bỏ qua trên các connector vốn cần fail-fast.
- **Cho rằng mọi lỗi đều được gửi DLQ:** lỗi task, poll, cấu hình hoặc hạ tầng không nhất thiết tạo DLQ record.
- **Dùng retry vô hạn cho lỗi dữ liệu:** record sai không tự trở nên hợp lệ sau thời gian chờ.
- **Nhầm framework retry với plugin retry:** hai tầng có phạm vi và giới hạn khác nhau.
- **Bật log payload trong production:** có thể lộ PII, token hoặc dữ liệu nhạy cảm.
- **Không giám sát DLQ:** lỗi được cách ly nhưng không bao giờ được xử lý.
- **Replay toàn bộ DLQ không kiểm tra:** có thể tạo duplicate hoặc đảo thứ tự.
- **Cho rằng task RUNNING nghĩa là không mất dữ liệu:** tolerance all có thể cho phép skip record.
- **Không kiểm tra batch semantics của SinkTask:** một lỗi ghi batch có thể làm cả batch retry/fail.
- **Dùng cùng DLQ cho mọi connector mà không có phân quyền:** khó vận hành và khó kiểm soát retention.
- **Reset source offset để xử lý task lỗi:** có thể bỏ sót hoặc phát lại lượng lớn dữ liệu.
- **Chỉ tăng retry timeout khi lỗi kéo dài:** lỗi cấu hình hoặc credential không được giải quyết bằng backoff.

## 18. Ma trận lựa chọn retry và DLQ

| Loại lỗi | Source connector | Sink connector |
|---|---|---|
| Lỗi kết nối hệ thống ngoài | Plugin reconnect/retry; giữ source offset | Plugin retry write; theo dõi lag |
| Lỗi converter | Framework tolerance/log; cân nhắc skip và backfill | Framework retry/log/DLQ nếu stage hỗ trợ |
| Lỗi SMT | Framework tolerance/log; source record có thể bị bỏ qua | Framework tolerance/log/DLQ nếu stage hỗ trợ |
| Lỗi dữ liệu nghiệp vụ | Connector-native quarantine hoặc luồng xử lý riêng | DLQ nếu record-level failure được nhận diện |
| Lỗi task-level | Task restart và source checkpoint | Plugin retry/task restart; không giả định record-level DLQ |
| Lỗi Kafka broker | Producer retry và task recovery | Consumer retry/reconnect và task recovery |
| Lỗi cấu hình/ACL | Dừng và sửa cấu hình | Dừng và sửa cấu hình |

Đây là ma trận định hướng. Xác minh chính xác error stage, plugin behavior và Kafka Connect version trước khi quyết định policy.

## 19. Checklist production

| Hạng mục | Câu hỏi |
|---|---|
| Connector type | Đây là source hay sink connector? |
| Error stage | Lỗi xảy ra ở poll, converter, SMT, put hay Kafka I/O? |
| Error class | Lỗi tạm thời, dữ liệu, nghiệp vụ, cấu hình hay hạ tầng? |
| Framework retry | errors.retry.timeout và delay có giới hạn phù hợp không? |
| Plugin retry | Plugin có max.retries, backoff hoặc retry policy riêng không? |
| Tolerance | Có thật sự cần errors.tolerance=all không? |
| DLQ support | Connector type và stage có được built-in DLQ hỗ trợ không? |
| DLQ topic | Topic có replication, partitions, retention, ACL và quota phù hợp không? |
| Context headers | Có bật metadata lỗi và đánh giá rò rỉ thông tin không? |
| Logging | Có log lỗi nhưng tránh ghi payload nhạy cảm không? |
| Ordering | Skip/DLQ có cho phép event sau vượt event lỗi không? |
| Idempotency | Replay có tạo duplicate side effect không? |
| Monitoring | Có task state, lag, retry và DLQ alert không? |
| Replay | Có runbook, rate limit và đối soát không? |
| Recovery | Source offset hoặc sink offset có thể phục hồi an toàn không? |

## 20. Kết luận

Kafka Connect có retry và error tolerance ở tầng framework, nhưng mỗi connector còn có hành vi riêng. Source connector phải bảo vệ quá trình đọc nguồn và checkpoint; sink connector phải xử lý lỗi khi chuyển đổi và ghi dữ liệu đích. Built-in DLQ chủ yếu dành cho sink connector và chỉ xử lý những lỗi record mà framework có thể nhận diện, không thay thế cơ chế phục hồi task hoặc plugin.

Hãy phân biệt **errors.retry.timeout** với retry của connector, phân loại lỗi trước khi chọn **errors.tolerance**, và chỉ bật **all** khi đã có log, DLQ hoặc quarantine cùng quy trình replay. DLQ phải được bảo vệ, giám sát và đối soát như một phần của data pipeline production.

Một chiến lược đúng cần biết chính xác lỗi xuất hiện ở stage nào, connector nào sở hữu retry, record nào có thể bị skip, offset nào được tiến lên và cách phục hồi dữ liệu sau khi nguyên nhân được khắc phục.
