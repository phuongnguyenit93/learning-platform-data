# Quản lý connector qua REST API: tạo, đổi cấu hình và xem trạng thái

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này hướng dẫn quản lý Kafka Connect connector thông qua REST API: tạo connector, cập nhật cấu hình, theo dõi trạng thái connector/task, tạm dừng, tiếp tục, khởi động lại và xóa connector.

Kafka Connect cung cấp HTTP REST API trên các worker để quản trị luồng tích hợp source và sink. API này quản lý cấu hình và vòng đời connector; dữ liệu thực tế vẫn được source connector đọc từ hệ thống ngoài hoặc sink connector ghi đến hệ thống đích. Trong distributed mode, cấu hình được chia sẻ qua Kafka và các task có thể chạy trên những worker khác nhau. Vì vậy, một lệnh REST thành công chỉ xác nhận thao tác quản trị được chấp nhận hoặc hoàn tất theo endpoint; cần kiểm tra trạng thái task và dữ liệu đầu ra để xác minh pipeline hoạt động.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Kafka Connect REST API và phân biệt nó với Kafka Admin API.
- Xác định REST endpoint của Connect worker và cách gọi trong distributed mode.
- Liệt kê connector và xem cấu hình hiện tại.
- Tạo connector bằng POST /connectors.
- Kiểm tra plugin và validate cấu hình trước khi tạo.
- Thay toàn bộ cấu hình connector bằng PUT /connectors/{name}/config.
- Theo dõi trạng thái connector, task và lỗi qua REST API.
- Pause, resume, restart và delete connector đúng cách.
- Xử lý HTTP status, timeout, lỗi plugin và lỗi worker.
- Gọi REST API bằng curl, Java HttpClient và Spring RestClient.
- Bảo vệ REST API, quản lý secret và phân quyền Kafka cho Connect worker.
- Xây dựng quy trình quản trị có audit, xác minh desired state và kiểm tra dữ liệu sau thay đổi.

## 2. Kafka Connect REST API nằm ở đâu?

Kafka Connect worker mở HTTP REST server để nhận lệnh quản trị. Port mặc định thường là 8083, nhưng có thể thay đổi theo cấu hình worker.

Ví dụ:

~~~text
http://connect-1:8083
http://connect-2:8083
~~~

Trong distributed mode, nhiều worker tham gia cùng một Connect cluster. Mỗi worker có REST endpoint riêng; các thao tác cần phối hợp cluster được xử lý và chuyển tiếp đến worker điều phối phù hợp. Vì vậy, client quản trị thường có thể gọi một worker REST endpoint đang hoạt động thay vì phải tự tìm task đang chạy ở đâu.

~~~mermaid
flowchart TD
    A[Admin UI / CI pipeline] --> R[Connect REST API]
    R --> W1[Worker 1]
    R --> W2[Worker 2]
    W1 <--> K[(Kafka Connect internal topics)]
    W2 <--> K
    W1 --> T1[Connector / tasks]
    W2 --> T2[Connector / tasks]
    T1 --> S[Source system or sink system]
    T2 --> S
~~~

Trong sơ đồ, internal topics lưu cấu hình, offset và trạng thái của Connect cluster. Worker phối hợp để phân phối connector/task và phục hồi trạng thái khi một worker dừng.

### 2.1. Distributed mode và standalone mode

| Đặc điểm | Standalone mode | Distributed mode |
|---|---|---|
| Worker | Một process quản lý connector cục bộ | Nhiều worker thuộc cùng Connect cluster |
| Cấu hình | Thường truyền qua file hoặc lệnh chạy worker | Được quản lý qua REST API và lưu trong config topic |
| Task placement | Trong worker standalone | Có thể phân phối trên nhiều worker |
| Khả năng chịu lỗi | Process dừng có thể làm connector dừng | Worker còn lại có thể nhận lại task sau khi cluster cân bằng |
| REST API | Quản lý worker/connector cục bộ | REST API phối hợp cấu hình trong cả cluster |

Bài học tập trung vào REST API của distributed mode vì đây là mô hình thường dùng cho triển khai nhiều worker. Một số endpoint cũng có thể dùng ở standalone mode, nhưng hành vi phân phối và lưu trạng thái khác nhau.

### 2.2. Cấu hình REST listener

Worker cần có cấu hình listener và địa chỉ quảng bá phù hợp với môi trường. Các thuộc tính host, port và advertised address phụ thuộc phiên bản Kafka Connect và cách triển khai.

Ví dụ cấu hình minh họa:

~~~properties
rest.host.name=0.0.0.0
rest.port=8083
rest.advertised.host.name=connect-1.internal
rest.advertised.port=8083
~~~

Không quảng bá hostname chỉ phân giải được trong một container nếu các worker hoặc client ở mạng khác cần truy cập. Kiểm tra DNS, firewall, service discovery và routing giữa các worker.

### 2.3. REST API không phải data plane

REST API dùng để quản lý connector:

- Tạo và cập nhật cấu hình.
- Xem connector/task status.
- Pause, resume, restart và delete.

REST API không truyền toàn bộ record source/sink qua HTTP client quản trị. Connector task mới là thành phần đọc hoặc ghi dữ liệu theo cấu hình. Không dùng REST endpoint để thay thế Kafka producer/consumer hoặc Kafka broker protocol.

## 3. Các endpoint quản lý connector thường dùng

Giả sử Connect REST base URL là http://localhost:8083.

| HTTP method | Endpoint | Mục đích |
|---|---|---|
| GET | /connectors | Liệt kê connector |
| POST | /connectors | Tạo connector |
| GET | /connectors/{name} | Xem thông tin connector và task |
| GET | /connectors/{name}/config | Xem cấu hình connector |
| PUT | /connectors/{name}/config | Thay cấu hình connector |
| GET | /connectors/{name}/status | Xem trạng thái connector và task |
| GET | /connectors/{name}/tasks | Liệt kê task của connector |
| GET | /connectors/{name}/tasks/{taskId}/status | Xem trạng thái một task |
| PUT | /connectors/{name}/pause | Tạm dừng connector |
| PUT | /connectors/{name}/resume | Tiếp tục connector |
| POST | /connectors/{name}/restart | Khởi động lại connector |
| DELETE | /connectors/{name} | Xóa connector |
| GET | /connector-plugins | Liệt kê connector plugin |
| PUT | /connector-plugins/{connectorType}/config/validate | Kiểm tra cấu hình theo plugin |

Các endpoint và query parameter có thể thay đổi theo phiên bản Kafka Connect. Hãy đối chiếu REST API reference của đúng phiên bản worker đang chạy trước khi triển khai tự động hóa.

## 4. Kiểm tra worker và plugin trước khi tạo connector

Trước khi gửi cấu hình, cần xác nhận worker REST API truy cập được và plugin cần dùng đã được cài đặt.

### 4.1. Kiểm tra REST endpoint

~~~bash
curl -i http://localhost:8083/
~~~

Nếu kết nối thất bại:

- Kiểm tra worker process có đang chạy không.
- Kiểm tra REST port và bind address.
- Kiểm tra DNS, network policy, firewall hoặc container port mapping.
- Kiểm tra TLS và authentication nếu endpoint được bảo vệ.
- Xem log khởi động worker để tìm lỗi cấu hình.

Một số bản triển khai không cung cấp nội dung root endpoint có ý nghĩa quản trị. Có thể kiểm tra trực tiếp endpoint liệt kê connector.

~~~bash
curl -i http://localhost:8083/connectors
~~~

### 4.2. Liệt kê plugin

~~~bash
curl -s http://localhost:8083/connector-plugins
~~~

Ví dụ kết quả:

~~~json
[
  {
    "class": "org.apache.kafka.connect.file.FileStreamSourceConnector",
    "type": "source",
    "version": "3.8.0"
  },
  {
    "class": "org.apache.kafka.connect.file.FileStreamSinkConnector",
    "type": "sink",
    "version": "3.8.0"
  }
]
~~~

Kết quả thực tế phụ thuộc plugin đã cài và phiên bản. Nếu connector class không xuất hiện, worker chưa load được plugin hoặc plugin không nằm trong plugin.path.

Trong distributed mode, cài cùng plugin và phiên bản tương thích trên mọi worker có thể nhận task. Nếu chỉ một worker có plugin, task có thể được phân công sang worker khác rồi thất bại do không tìm thấy class.

### 4.3. Plugin path

Worker dùng cấu hình plugin.path để tìm connector, converter và transform plugin.

~~~properties
plugin.path=/opt/kafka/plugins,/usr/local/share/kafka/plugins
~~~

Sau khi cài hoặc cập nhật plugin, cần khởi động lại worker theo quy trình triển khai. Kiểm tra log để xác nhận plugin được phát hiện và không có xung đột dependency.

Ví dụ FileStream connector trong bài thực hành yêu cầu plugin tương ứng có sẵn trong Kafka Connect distribution hoặc được cài vào plugin path. Đường dẫn file phải tồn tại trên worker được giao chạy task; trong cluster nhiều worker, nên dùng volume hoặc filesystem được triển khai nhất quán.

## 5. Tạo connector bằng POST /connectors

Để tạo connector, gửi POST đến /connectors với JSON gồm hai trường:

- name: tên định danh connector trong Connect cluster.
- config: map cấu hình connector dưới dạng key/value string.

Ví dụ tạo FileStream Source Connector đọc file và ghi vào topic orders.raw:

~~~json
{
  "name": "orders-file-source",
  "config": {
    "connector.class": "org.apache.kafka.connect.file.FileStreamSourceConnector",
    "tasks.max": "1",
    "file": "/tmp/orders.txt",
    "topic": "orders.raw"
  }
}
~~~

Gọi REST API:

~~~bash
curl -i -X POST -H "Content-Type: application/json" --data-binary @orders-file-source.json http://localhost:8083/connectors
~~~

Trên Windows PowerShell, dùng curl.exe nếu cần gọi chương trình curl thật:

~~~powershell
curl.exe -i -X POST -H "Content-Type: application/json" --data-binary "@orders-file-source.json" http://localhost:8083/connectors
~~~

Nếu tạo thành công, REST API thường trả HTTP 201 Created và thông tin connector. Nếu tên đã tồn tại, request thường trả conflict. Hãy kiểm tra connector hiện tại trước khi quyết định cập nhật.

### 5.1. Ý nghĩa cấu hình

| Thuộc tính | Ý nghĩa |
|---|---|
| name | Tên connector được quản lý trong Connect cluster. |
| connector.class | Tên class triển khai connector plugin. |
| tasks.max | Số task tối đa connector được yêu cầu tạo. |
| file | Đường dẫn file mà FileStream Source Connector đọc. |
| topic | Kafka topic đích cho source record. |

Đây là cấu hình mẫu để học REST API, không phải cấu hình production cho tích hợp file. Connector thực tế có thể cần endpoint database, credentials, schema, converter, topic mapping hoặc nhiều tham số riêng của plugin.

### 5.2. tasks.max không bảo đảm có đúng số task

tasks.max là giới hạn mong muốn cho số task. Connector quyết định có thể chia công việc thành bao nhiêu task dựa trên loại plugin, số nguồn dữ liệu và cấu hình.

Ví dụ, một connector có thể chỉ tạo một task dù tasks.max đặt bằng 8. Kiểm tra endpoint tasks và status để biết số task thực tế.

### 5.3. Tạo connector idempotent ở tầng quản trị

POST /connectors không phải upsert. Nếu tên đã tồn tại, hãy:

1. GET /connectors/{name}/config.
2. So sánh với desired config.
3. Nếu cần thay đổi, dùng PUT /connectors/{name}/config.
4. GET /connectors/{name}/status để xác nhận task chạy lại.

Không xóa connector rồi tạo lại chỉ để đổi một thuộc tính nếu API cập nhật cấu hình đáp ứng được yêu cầu.

## 6. Validate cấu hình trước khi tạo

Kafka Connect có endpoint kiểm tra cấu hình theo connector plugin:

~~~text
PUT /connector-plugins/{connectorType}/config/validate
~~~

Ví dụ:

~~~bash
curl -i -X PUT -H "Content-Type: application/json" --data-binary @orders-file-source-config.json http://localhost:8083/connector-plugins/org.apache.kafka.connect.file.FileStreamSourceConnector/config/validate
~~~

Body là map cấu hình connector, không bọc trong đối tượng có name và config như POST /connectors.

Ví dụ body:

~~~json
{
  "connector.class": "org.apache.kafka.connect.file.FileStreamSourceConnector",
  "tasks.max": "1",
  "file": "/tmp/orders.txt",
  "topic": "orders.raw"
}
~~~

Kết quả validation thường chứa:

- Config keys đã nhận diện.
- Giá trị hiện tại.
- Trạng thái valid.
- Danh sách error message.
- Các giá trị phụ thuộc hoặc recommended value theo plugin.

Validation có thể phát hiện thiếu field bắt buộc, sai kiểu dữ liệu hoặc giá trị không hợp lệ. Tuy nhiên, validation không chứng minh database, file, API hoặc Kafka topic có thể truy cập được tại thời điểm task chạy.

## 7. Liệt kê và xem thông tin connector

### 7.1. Liệt kê tên connector

~~~bash
curl -s http://localhost:8083/connectors
~~~

Ví dụ kết quả:

~~~json
[
  "orders-file-source",
  "payments-jdbc-source",
  "shipments-sink"
]
~~~

Danh sách tên giúp tìm connector hiện có trước khi tạo hoặc cập nhật.

### 7.2. Xem thông tin connector

~~~bash
curl -s http://localhost:8083/connectors/orders-file-source
~~~

Endpoint này trả thông tin connector và task được khai báo trong cấu hình hiện tại. Để lấy cấu hình riêng, dùng endpoint config.

### 7.3. Xem cấu hình connector

~~~bash
curl -s http://localhost:8083/connectors/orders-file-source/config
~~~

Kết quả là map cấu hình:

~~~json
{
  "connector.class": "org.apache.kafka.connect.file.FileStreamSourceConnector",
  "tasks.max": "1",
  "file": "/tmp/orders.txt",
  "topic": "orders.raw"
}
~~~

Cấu hình trả về có thể xử lý giá trị nhạy cảm theo cơ chế masking hoặc ConfigProvider của phiên bản worker. Không giả định GET config luôn trả lại secret rõ hoặc có thể dùng nguyên response làm file backup mà không kiểm tra.

## 8. Thay đổi cấu hình bằng PUT /connectors/{name}/config

Để cập nhật cấu hình, gửi PUT đến endpoint:

~~~text
PUT /connectors/orders-file-source/config
~~~

Body là toàn bộ map cấu hình mới, không có lớp bọc name/config.

~~~json
{
  "connector.class": "org.apache.kafka.connect.file.FileStreamSourceConnector",
  "tasks.max": "2",
  "file": "/data/orders-current.txt",
  "topic": "orders.raw"
}
~~~

Lệnh curl:

~~~bash
curl -i -X PUT -H "Content-Type: application/json" --data-binary @orders-file-source-config.json http://localhost:8083/connectors/orders-file-source/config
~~~

### 8.1. PUT là thay toàn bộ config

PUT /config thay cấu hình connector bằng cấu hình được gửi lên. Không xem đây là PATCH chỉ cập nhật một field.

Khi thay đổi, hãy gửi đủ các field bắt buộc:

- connector.class.
- tasks.max.
- Các field bắt buộc của plugin.
- Các field tùy chọn mà ứng dụng cần giữ nguyên.
- Converter, transform hoặc security setting nếu chúng nằm trong connector config.

Nếu chỉ gửi tasks.max mà bỏ file, topic hoặc JDBC URL, cấu hình mới có thể thiếu field và connector sẽ chuyển sang FAILED hoặc không khởi động được.

### 8.2. Cập nhật có thể làm task được khởi tạo lại

Khi cấu hình thay đổi, Connect cluster có thể dừng và tạo lại task theo cấu hình mới, đồng thời phân phối lại task giữa worker.

Tác động phụ thuộc loại connector và field thay đổi:

- Task có thể tạm ngừng xử lý.
- Source có thể tiếp tục từ offset đã lưu.
- Sink có thể đọc lại record chưa commit hoặc chưa ghi nhận.
- Thay đổi topic mapping hoặc database query có thể thay đổi phạm vi dữ liệu.
- Thay đổi số task có thể làm thay đổi song song và thứ tự xử lý.

Trước khi cập nhật production, cần đánh giá connector semantics, offset behavior và khả năng replay. Với sink, hệ thống đích nên có idempotency hoặc upsert nếu connector có thể retry record.

### 8.3. Xác minh sau cập nhật

Sau khi PUT thành công:

1. GET /connectors/{name}/config để kiểm tra cấu hình đã lưu.
2. GET /connectors/{name}/status để kiểm tra connector và task.
3. Xem log worker nếu có task FAILED.
4. Kiểm tra metric source/sink và dữ liệu thực tế.
5. Theo dõi lag hoặc throughput sau khi task được phân phối lại.

Không coi HTTP 200 là bằng chứng toàn bộ task đã RUNNING và dữ liệu đang đi qua pipeline.

## 9. Xem trạng thái connector và task

Endpoint quan trọng:

~~~text
GET /connectors/{name}/status
~~~

Ví dụ:

~~~bash
curl -s http://localhost:8083/connectors/orders-file-source/status
~~~

Kết quả minh họa:

~~~json
{
  "name": "orders-file-source",
  "connector": {
    "state": "RUNNING",
    "worker_id": "connect-1:8083"
  },
  "tasks": [
    {
      "id": 0,
      "state": "RUNNING",
      "worker_id": "connect-2:8083"
    }
  ],
  "type": "source"
}
~~~

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| name | Tên connector. |
| connector.state | Trạng thái connector instance. |
| connector.worker_id | Worker đang chạy connector instance. |
| tasks | Danh sách task và trạng thái từng task. |
| tasks[].id | ID task trong connector. |
| tasks[].state | Trạng thái task. |
| tasks[].worker_id | Worker đang chạy task. |
| type | Loại connector, thường là source hoặc sink. |

Khi FAILED, response có thể kèm trace hoặc thông tin lỗi tùy phiên bản. Hãy lấy log worker tương ứng để xem stack trace đầy đủ.

### 9.1. Các trạng thái thường gặp

| State | Ý nghĩa khái quát |
|---|---|
| RUNNING | Connector hoặc task đang chạy. |
| PAUSED | Connector/task đang được tạm dừng. |
| FAILED | Connector/task đã thất bại. |
| UNASSIGNED | Chưa được gán cho worker hoặc chưa hoàn tất phân phối. |
| RESTARTING | Đang trong quá trình restart nếu phiên bản hiển thị trạng thái này. |

Tên và trạng thái trung gian có thể khác theo phiên bản Connect. Trạng thái cần được đọc cùng loại component và thời điểm quan sát.

### 9.2. Connector RUNNING nhưng task FAILED

Connector instance có thể RUNNING trong khi một hoặc nhiều task FAILED. Vì vậy, cần kiểm tra từng task chứ không chỉ đọc connector.state.

~~~text
Connector: RUNNING
Task 0: RUNNING
Task 1: FAILED
Task 2: RUNNING
~~~

Trong trường hợp này, pipeline chỉ xử lý phần công việc do task còn sống phụ trách. Một connector có trạng thái tổng thể RUNNING không có nghĩa toàn bộ dữ liệu đã được đồng bộ.

### 9.3. Xem task riêng lẻ

~~~bash
curl -s http://localhost:8083/connectors/orders-file-source/tasks
~~~

Xem trạng thái task 0:

~~~bash
curl -s http://localhost:8083/connectors/orders-file-source/tasks/0/status
~~~

Các endpoint này hữu ích khi connector có nhiều task và cần xác định worker nào đang chạy task lỗi.

## 10. Pause và resume connector

Pause tạm dừng hoạt động connector và các task liên quan:

~~~bash
curl -i -X PUT http://localhost:8083/connectors/orders-file-source/pause
~~~

Resume tiếp tục hoạt động:

~~~bash
curl -i -X PUT http://localhost:8083/connectors/orders-file-source/resume
~~~

Pause hữu ích khi:

- Hệ thống đích đang bảo trì.
- Cần ngừng sink trước khi thay đổi schema.
- Cần điều tra lỗi dữ liệu.
- Cần tạm dừng source trong lúc kiểm tra upstream.
- Cần kiểm soát tải trước khi triển khai thay đổi.

### 10.1. Pause không đồng nghĩa delete

Pause giữ connector configuration và trạng thái quản lý trong Connect cluster. Resume có thể tiếp tục từ offset mà connector đã lưu, tùy semantics của connector.

Pause không:

- Xóa connector.
- Xóa Kafka topic.
- Xóa offset connector.
- Xóa dữ liệu trong hệ thống nguồn hoặc đích.

Đừng dùng pause thay cho quy trình backup hoặc thay đổi cấu hình.

### 10.2. Kiểm tra trạng thái sau pause/resume

Các lệnh pause/resume có thể trả về trước khi mọi task chuyển trạng thái hoàn toàn. Hãy poll endpoint status cho đến khi connector và task đạt trạng thái mong muốn hoặc timeout vận hành.

Ví dụ:

~~~bash
curl -s http://localhost:8083/connectors/orders-file-source/status
~~~

Nếu task vẫn RUNNING sau pause, chờ trong giới hạn hợp lý rồi kiểm tra log worker và trạng thái connector. Không gửi lặp pause/resume liên tục vì có thể làm khó quan sát vòng đời task.

## 11. Restart connector hoặc task

Khi task FAILED do lỗi tạm thời đã được xử lý, có thể restart.

Restart connector:

~~~bash
curl -i -X POST http://localhost:8083/connectors/orders-file-source/restart
~~~

Một số phiên bản hỗ trợ query parameter để chọn restart task và chỉ restart thành phần FAILED:

~~~bash
curl -i -X POST "http://localhost:8083/connectors/orders-file-source/restart?includeTasks=true&onlyFailed=true"
~~~

Ý nghĩa thường gặp:

- includeTasks=true: yêu cầu restart cả task thuộc connector.
- onlyFailed=true: chỉ restart thành phần đang FAILED thay vì tất cả.

Hãy xác nhận query parameter được hỗ trợ bởi phiên bản Connect đang chạy. Sau restart, kiểm tra lại connector status và task status.

### 11.1. Restart không sửa nguyên nhân gốc

Nếu task FAILED do:

- Sai database credential.
- Plugin thiếu dependency.
- Schema không tương thích.
- Topic không tồn tại hoặc thiếu ACL.
- Database query sai.
- API đích trả lỗi dữ liệu vĩnh viễn.

Thì restart có thể khiến task FAILED lại ngay. Trước khi restart, cần xem error trace và sửa cấu hình hoặc dependency liên quan.

### 11.2. Restart task riêng

Một số phiên bản cung cấp endpoint restart task:

~~~text
POST /connectors/{name}/tasks/{taskId}/restart
~~~

Ví dụ:

~~~bash
curl -i -X POST http://localhost:8083/connectors/orders-file-source/tasks/0/restart
~~~

Kiểm tra API reference đúng phiên bản trước khi dùng. Sau restart, task có thể được phân phối lại và worker_id thay đổi.

## 12. Xóa connector bằng DELETE

Xóa connector:

~~~bash
curl -i -X DELETE http://localhost:8083/connectors/orders-file-source
~~~

Thao tác này yêu cầu Connect xóa cấu hình connector và dừng các task liên quan. Nó không đồng nghĩa với xóa topic Kafka, xóa bảng database hoặc xóa dữ liệu trong hệ thống ngoài.

Trước khi xóa:

1. Xác minh đúng Connect cluster.
2. Xác minh connector name chính xác.
3. Kiểm tra connector có đang phục vụ pipeline production không.
4. Xác định hệ thống downstream có còn phụ thuộc dữ liệu không.
5. Lưu cấu hình và thông tin vận hành cần thiết.
6. Xác nhận quy trình change/decommission.
7. Ghi audit người yêu cầu và kết quả.

Connector offsets được lưu riêng trong offset storage topic. Không suy luận rằng DELETE connector sẽ xóa toàn bộ offset hoặc dữ liệu nguồn/đích. Hành vi quản lý/reset offsets có API riêng và phụ thuộc phiên bản cùng loại connector.

### 12.1. Xác minh sau delete

Sau khi DELETE:

- GET /connectors để xác nhận tên không còn trong danh sách.
- Kiểm tra task đã dừng.
- Kiểm tra source/sink không còn phát sinh request.
- Xác minh topic và dữ liệu đích theo chính sách retention riêng.
- Lưu lại cấu hình, offset hoặc audit nếu quy trình yêu cầu.

Nếu client timeout khi DELETE, kiểm tra lại danh sách và trạng thái trước khi retry. Request có thể đã được xử lý dù response bị mất.

## 13. Mã HTTP và xử lý lỗi REST

Các mã thường gặp:

| HTTP status | Ý nghĩa thường gặp | Cách xử lý |
|---|---|---|
| 200 OK | GET hoặc cập nhật trả kết quả thành công | Đọc body và xác minh trạng thái. |
| 201 Created | Connector được tạo | Lưu tên và kiểm tra status. |
| 202 Accepted | Pause, resume hoặc restart được chấp nhận xử lý | Poll status để xác nhận chuyển trạng thái. |
| 204 No Content | Xóa thành công, không có body | Kiểm tra lại danh sách connector. |
| 400 Bad Request | JSON hoặc connector config không hợp lệ | Đọc error message và validation result. |
| 401 Unauthorized | Thiếu hoặc sai thông tin xác thực | Kiểm tra auth của REST endpoint. |
| 403 Forbidden | Principal không có quyền REST operation | Kiểm tra REST authorization policy. |
| 404 Not Found | Connector, task hoặc endpoint không tồn tại | Kiểm tra tên và API version. |
| 409 Conflict | Connector name đã tồn tại hoặc trạng thái không cho phép thao tác | GET connector và quyết định PUT/retry. |
| 5xx | Worker, plugin, broker hoặc cluster gặp lỗi | Kiểm tra worker log, broker health và retry có kiểm soát. |

Mã cụ thể có thể khác theo endpoint và phiên bản. Không dựa duy nhất vào status code; đọc response body để lấy error message.

### 13.1. Timeout và kết quả không rõ ràng

Nếu HTTP client timeout sau khi gửi POST hoặc PUT, server có thể đã xử lý request. Trước khi gửi lại:

- GET /connectors.
- GET /connectors/{name}/config.
- GET /connectors/{name}/status.
- So sánh desired config với trạng thái thực tế.

Với POST create, retry mù có thể nhận conflict vì connector đã được tạo. Với PUT, gửi lại cùng desired config thường dễ kiểm soát hơn nhưng vẫn cần xem tác động reconfiguration.

### 13.2. Retry REST request

Không retry mọi mã lỗi:

- 400: sửa request/config trước.
- 401/403: sửa authentication/authorization.
- 404: kiểm tra connector name hoặc endpoint.
- 409: đọc trạng thái hiện tại.
- 429: tôn trọng Retry-After nếu proxy/API gateway trả về.
- 5xx hoặc network timeout: retry giới hạn với exponential backoff và jitter sau khi xác minh operation state.

Đối với DELETE và restart, luôn kiểm tra trạng thái trước khi retry vì đây là thao tác có side effect.

## 14. Ví dụ quản lý connector bằng Java HttpClient

Java 11 trở lên có HttpClient để gọi REST API mà không cần thư viện HTTP bên ngoài.

Ví dụ tạo connector:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class ConnectRestClient {

    private final HttpClient client;
    private final String baseUrl;

    public ConnectRestClient(String baseUrl) {
        this.baseUrl = baseUrl;

        this.client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    }

    public HttpResponse<String> createConnector(
        String connectorJson
    ) throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(baseUrl + "/connectors"))
            .timeout(Duration.ofSeconds(15))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(
                connectorJson,
                StandardCharsets.UTF_8
            ))
            .build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        if (response.statusCode() != 201) {
            throw new IllegalStateException(
                "Create connector failed: HTTP "
                + response.statusCode()
                + " body=" + response.body()
            );
        }

        return response;
    }

    public HttpResponse<String> getStatus(
        String connectorName
    ) throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(
                baseUrl + "/connectors/" + connectorName + "/status"
            ))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        return client.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );
    }

    public HttpResponse<String> updateConfig(
        String connectorName,
        String configJson
    ) throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(
                baseUrl + "/connectors/" + connectorName + "/config"
            ))
            .timeout(Duration.ofSeconds(15))
            .header("Content-Type", "application/json")
            .PUT(HttpRequest.BodyPublishers.ofString(
                configJson,
                StandardCharsets.UTF_8
            ))
            .build();

        return client.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );
    }
}
~~~

Cách sử dụng:

~~~java
String connectorJson = """
{
  "name": "orders-file-source",
  "config": {
    "connector.class": "org.apache.kafka.connect.file.FileStreamSourceConnector",
    "tasks.max": "1",
    "file": "/tmp/orders.txt",
    "topic": "orders.raw"
  }
}
""";

ConnectRestClient connect =
    new ConnectRestClient("http://localhost:8083");

var created = connect.createConnector(connectorJson);
System.out.println(created.body());

var status = connect.getStatus("orders-file-source");
System.out.println(status.statusCode());
System.out.println(status.body());
~~~

Ví dụ này dùng HTTP không mã hóa cho lab. Production cần cấu hình TLS và authentication theo REST security layer. Cũng cần encode connector name khi đưa vào URL nếu tên có ký tự đặc biệt; nên giới hạn tên theo naming convention đơn giản.

## 15. Tích hợp Spring bằng RestClient

Trong Spring Framework 6.1 / Spring Boot 3.2 trở lên, có thể dùng RestClient để gọi Connect REST API.

Cấu hình base URL:

~~~yaml
kafka:
  connect:
    base-url: http://connect-1.internal:8083
~~~

Khai báo bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.web.client.RestClient;

@Configuration
public class ConnectRestConfiguration {

    @Bean
    RestClient connectRestClient(
        RestClient.Builder builder,
        Environment environment
    ) {
        String baseUrl =
            environment.getRequiredProperty("kafka.connect.base-url");

        return builder
            .baseUrl(baseUrl)
            .build();
    }
}
~~~

Service gọi API:

~~~java
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.Map;

@Service
public class ConnectManagementService {

    private final RestClient restClient;

    public ConnectManagementService(RestClient restClient) {
        this.restClient = restClient;
    }

    public String createConnector(
        Map<String, Object> request
    ) {
        return restClient.post()
            .uri("/connectors")
            .contentType(MediaType.APPLICATION_JSON)
            .body(request)
            .retrieve()
            .body(String.class);
    }

    public String getConnectorStatus(String name) {
        return restClient.get()
            .uri("/connectors/{name}/status", name)
            .retrieve()
            .body(String.class);
    }

    public void pauseConnector(String name) {
        restClient.put()
            .uri("/connectors/{name}/pause", name)
            .retrieve()
            .toBodilessEntity();
    }

    public void resumeConnector(String name) {
        restClient.put()
            .uri("/connectors/{name}/resume", name)
            .retrieve()
            .toBodilessEntity();
    }
}
~~~

Trong ứng dụng thực tế, nên dùng DTO thay cho Map để validate request, phân loại response và không để caller truyền tùy ý connector class hoặc config nhạy cảm. Cấu hình authentication, TLS, timeout và error handler trên RestClient theo môi trường.

Nếu dùng Spring phiên bản cũ hơn, có thể dùng RestTemplate hoặc WebClient. REST client chỉ gọi API quản trị; không thay thế Kafka Connect worker và không thực hiện thay connector task.

## 16. Secret và bảo mật REST API

Connector config có thể chứa database password, API token, private key hoặc credential hệ thống đích. REST API là bề mặt quản trị nhạy cảm: người có quyền sửa connector có thể thay đổi luồng dữ liệu, đọc dữ liệu nguồn hoặc ghi dữ liệu đến hệ thống khác.

Các nguyên tắc:

- Không expose Connect REST API trực tiếp ra Internet.
- Đặt REST endpoint trong mạng quản trị nội bộ hoặc qua gateway được bảo vệ.
- Dùng TLS để mã hóa kết nối.
- Bật authentication/authorization qua cơ chế bảo vệ REST phù hợp với triển khai.
- Dùng REST extension hoặc reverse proxy có kiểm soát nếu cần tích hợp danh tính.
- Giới hạn quyền create/update/delete connector theo role.
- Ghi audit cho mọi thay đổi cấu hình, pause, resume, restart và delete.
- Không log nguyên văn secret hoặc toàn bộ config nhạy cảm.
- Dùng ConfigProvider để lấy secret từ file/secret manager thay vì gửi password dạng rõ trong JSON.
- Bảo vệ Kafka broker ACL cho principal mà Connect worker sử dụng.

Bảo vệ Kafka broker không tự động bảo vệ HTTP REST endpoint. Hai lớp cần được cấu hình riêng.

### 16.1. Kafka ACL cho Connect worker

Connect worker cần quyền trên:

- Internal config topic.
- Internal offset topic.
- Internal status topic.
- Kafka topic mà source connector ghi vào.
- Kafka topic mà sink connector đọc.
- Các resource khác tùy connector, converter và plugin.

Nên dùng principal riêng cho Connect worker và cấp quyền theo đúng connector workload. Không dùng superuser cho mọi connector nếu không cần.

### 16.2. Internal topics trong distributed mode

Distributed worker sử dụng các topic nội bộ:

| Worker config | Mục đích |
|---|---|
| config.storage.topic | Lưu cấu hình connector và task. |
| offset.storage.topic | Lưu source connector offsets. |
| status.storage.topic | Lưu trạng thái connector/task. |

Các topic này cần được cấu hình phù hợp với durability, replication và compaction. Trong production, thường nên tạo trước với replication factor phù hợp, ví dụ 3 nếu cluster có đủ broker và failure domain.

Không xóa hoặc chỉnh sửa thủ công các internal topic này khi Connect cluster đang hoạt động. Làm vậy có thể khiến worker mất cấu hình, offset hoặc trạng thái và cần quy trình khôi phục riêng.

## 17. Quan sát trạng thái không đủ để xác minh dữ liệu

REST status cho biết connector/task đang ở trạng thái nào, nhưng không chứng minh record đã được chuyển thành công đến hệ thống đích.

Ví dụ connector và task đều RUNNING nhưng:

- Source không có dữ liệu mới.
- File path không được cập nhật.
- JDBC query trả về 0 row.
- Sink bị chậm do downstream throttling.
- Record bị lỗi converter hoặc SMT.
- Topic đích không có consumer kiểm tra.

Cần kết hợp status với:

- Worker log và task error trace.
- Connect JMX metrics.
- Source record poll rate.
- Sink record write rate.
- Error/retry/dead-letter metrics nếu plugin có hỗ trợ.
- Kafka topic offset và consumer lag.
- Kiểm tra dữ liệu thực tế ở nguồn hoặc đích.

### 17.1. Checklist kiểm tra connector RUNNING

1. Connector state là RUNNING.
2. Tất cả task cần thiết đều RUNNING.
3. Worker ID đúng và worker đó khỏe.
4. Source/sink metrics có hoạt động phù hợp.
5. Không có lỗi lặp trong worker log.
6. Kafka topic hoặc hệ thống đích có dữ liệu mới.
7. Offset tiến triển theo kỳ vọng.
8. Không có backlog hoặc retry tăng liên tục.

Nếu task RUNNING nhưng dữ liệu không di chuyển, hãy điều tra connector-specific behavior thay vì restart liên tục.

## 18. Quy trình thay đổi connector an toàn

Một quy trình quản trị có thể dùng cho CI/CD hoặc trang quản trị nội bộ:

~~~mermaid
flowchart TD
    A[Nhận yêu cầu thay đổi] --> B[Kiểm tra Connect cluster]
    B --> C[GET connector config và status]
    C --> D[Validate plugin config]
    D --> E{Config hợp lệ?}
    E -->|Không| F[Trả lỗi và dừng]
    E -->|Có| G[PUT full connector config]
    G --> H[Poll connector/task status]
    H --> I{Tất cả task cần thiết RUNNING?}
    I -->|Không| J[Đọc worker log và error trace]
    I -->|Có| K[Kiểm tra record/offset thực tế]
    K --> L{Data flow đúng?}
    L -->|Không| J
    L -->|Có| M[Ghi audit và hoàn tất]
~~~

Các bước cụ thể:

1. Ghi nhận người yêu cầu, connector name và môi trường.
2. GET config/status hiện tại.
3. Lưu snapshot config theo chính sách bảo mật.
4. Validate cấu hình mới bằng plugin validation endpoint.
5. Đánh giá tác động của field thay đổi.
6. PUT toàn bộ config mới.
7. Poll status theo timeout có giới hạn.
8. Kiểm tra task, log và dữ liệu thực tế.
9. Nếu thất bại, quyết định rollback config hoặc xử lý nguyên nhân.
10. Ghi audit kết quả và thời điểm thay đổi.

Rollback bằng PUT cấu hình cũ chỉ an toàn nếu connector semantics cho phép và offset/source state không bị ảnh hưởng ngoài dự kiến. Không giả định rollback config sẽ hoàn tác dữ liệu đã ghi sang Kafka hoặc hệ thống đích.

## 19. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| REST API connection refused | Worker chưa chạy, sai port hoặc bind address. | Kiểm tra process, rest.port, network và firewall. |
| POST /connectors trả 409 | Connector name đã tồn tại. | GET config/status và dùng PUT nếu cần cập nhật. |
| POST trả 400 | Thiếu config, sai kiểu hoặc field plugin không hợp lệ. | Gọi config validation và đọc response body. |
| Plugin class not found | Plugin chưa cài hoặc plugin.path sai trên worker được giao task. | Cài plugin đồng nhất và restart worker theo quy trình. |
| Connector RUNNING nhưng task FAILED | Task không truy cập được source/sink hoặc lỗi dữ liệu. | Xem task status, error trace và worker log. |
| PUT config xong task không RUNNING | Config thiếu field hoặc task reconfiguration thất bại. | GET config, validate và xem log. |
| Pause trả thành công nhưng task vẫn RUNNING | Trạng thái chuyển đổi chưa hoàn tất hoặc worker chưa xử lý xong. | Poll status và kiểm tra log trước khi gửi lệnh tiếp. |
| Resume không phục hồi task FAILED | Lỗi gốc chưa được sửa. | Sửa config/dependency rồi restart theo chính sách. |
| Restart xong FAILED ngay | Lỗi plugin, auth, schema hoặc downstream vẫn còn. | Điều tra nguyên nhân gốc; không restart lặp vô hạn. |
| DELETE timeout | Server có thể đã xử lý nhưng response bị mất. | GET /connectors để xác minh trước khi retry. |
| Task liên tục đổi worker | Worker restart, rebalance hoặc cluster không ổn định. | Kiểm tra worker health, group membership và internal topics. |
| REST API truy cập được nhưng broker ACL lỗi | REST authentication và Kafka broker ACL là hai lớp riêng. | Kiểm tra principal và quyền Kafka của Connect worker. |
| Status RUNNING nhưng không có dữ liệu | Source không có record hoặc sink không ghi được dữ liệu kỳ vọng. | Kiểm tra metrics, connector log, offset và hệ thống nguồn/đích. |

## 20. Checklist production

Trước khi quản lý connector production, hãy xác nhận:

1. Đang gọi đúng Connect cluster và REST endpoint chưa?
2. Plugin class có mặt trên tất cả worker có thể chạy task không?
3. Plugin version có tương thích giữa các worker không?
4. Connector name có theo naming convention không?
5. Cấu hình đã được validate trước khi tạo/cập nhật chưa?
6. PUT request có gửi đầy đủ toàn bộ config cần thiết không?
7. Secret có được lấy qua ConfigProvider hoặc secret manager không?
8. REST API có TLS và authentication/authorization phù hợp không?
9. Kafka ACL của Connect worker có đúng least privilege không?
10. Config, offset và status internal topics có replication/compaction phù hợp không?
11. Có snapshot config và audit log trước khi thay đổi không?
12. Sau PUT, connector và từng task có RUNNING không?
13. Đã kiểm tra record thực tế ở Kafka hoặc hệ thống đích chưa?
14. Có timeout và backoff khi poll status không?
15. Có rollback plan cho cấu hình mới không?
16. DELETE có được bảo vệ bởi xác nhận và allowlist connector không?
17. Worker log, JMX metric và task error trace có được giám sát không?

## 21. Bài tập thực hành

### Bài 1: Liệt kê plugin và connector

1. Khởi động Kafka Connect distributed mode.
2. Gọi GET /connector-plugins.
3. Gọi GET /connectors.
4. Ghi lại plugin class, version và connector hiện có.
5. Xác định plugin cần dùng cho bài thực hành.
6. Kiểm tra plugin có trên mọi worker hay không.

### Bài 2: Tạo FileStream Source Connector

1. Chuẩn bị file orders.txt trên đường dẫn mà Connect worker có thể đọc.
2. Tạo JSON config cho FileStreamSourceConnector.
3. Gọi endpoint config validation.
4. Gọi POST /connectors.
5. Gọi GET /connectors/orders-file-source/status.
6. Ghi thêm dòng vào file.
7. Kiểm tra topic orders.raw có record mới.
8. Giải thích vì sao task RUNNING chưa đủ chứng minh record đã được ghi.

### Bài 3: Cập nhật cấu hình

1. GET /connectors/orders-file-source/config.
2. Thay file path hoặc tasks.max trong desired config.
3. Gửi PUT /connectors/orders-file-source/config với toàn bộ config.
4. Poll status cho đến khi task ổn định.
5. Kiểm tra record tiếp tục được đọc theo semantics của connector.
6. Quan sát log và worker ID nếu task được phân phối lại.

### Bài 4: Pause và resume

1. Gọi PUT /connectors/orders-file-source/pause.
2. Poll status và xác nhận connector/task PAUSED.
3. Thêm dữ liệu vào file nguồn.
4. Kiểm tra dữ liệu chưa được chuyển trong lúc pause.
5. Gọi PUT /connectors/orders-file-source/resume.
6. Xác minh record được xử lý tiếp theo.

### Bài 5: Restart task lỗi

1. Cố ý cấu hình sai file path hoặc topic trong môi trường lab.
2. Quan sát connector/task status.
3. Đọc error trace và worker log.
4. Sửa config.
5. Restart connector hoặc task theo API phiên bản đang chạy.
6. Kiểm tra task RUNNING và data flow phục hồi.

### Bài 6: Xóa connector lab

1. GET config/status để lưu snapshot.
2. Xác minh connector name là connector lab.
3. Gọi DELETE /connectors/orders-file-source.
4. GET /connectors để xác nhận connector biến mất.
5. Kiểm tra topic orders.raw vẫn tồn tại.
6. Giải thích vì sao xóa connector không đồng nghĩa xóa topic hoặc dữ liệu đã ghi.

## 22. Câu hỏi tự kiểm tra

1. Kafka Connect REST API chạy ở thành phần nào?
2. REST API khác Kafka Admin API như thế nào?
3. Trong distributed mode, vì sao có thể gọi REST endpoint của một worker để quản lý connector?
4. POST /connectors cần những trường JSON nào?
5. tasks.max có bảo đảm connector tạo đúng số task không?
6. Endpoint nào liệt kê connector plugin?
7. Config validation endpoint nhận body có cấu trúc gì?
8. PUT /connectors/{name}/config là cập nhật một field hay thay toàn bộ config?
9. Vì sao cần GET config và status sau PUT?
10. Connector RUNNING nhưng task FAILED có ý nghĩa gì?
11. Pause khác delete connector như thế nào?
12. Restart task có sửa được lỗi cấu hình sai không?
13. DELETE connector có xóa Kafka topic và dữ liệu đích không?
14. Vì sao REST authentication và Kafka ACL phải được cấu hình riêng?
15. Secret nên được đưa vào connector config bằng cách nào?
16. Vì sao plugin phải có mặt trên mọi worker có thể nhận task?
17. HTTP 202 sau pause/resume có chứng minh task đã chuyển trạng thái không?
18. Nếu POST timeout, làm sao tránh tạo connector trùng?
19. Vì sao status RUNNING không chứng minh data flow đang hoạt động?
20. Cần kiểm tra gì trước khi xóa connector production?

## Kết luận

Kafka Connect REST API là giao diện quản trị connector và task trên Connect worker. POST /connectors tạo connector, PUT /connectors/{name}/config thay toàn bộ cấu hình, GET /connectors/{name}/status cho biết trạng thái connector và từng task. Các endpoint pause, resume, restart và DELETE hỗ trợ điều khiển vòng đời connector.

Trong distributed mode, cấu hình và trạng thái được phối hợp qua các internal topics, còn task có thể chạy trên nhiều worker. Plugin cần được cài đồng nhất trên các worker có thể nhận task. Sau mỗi thao tác quản trị, hãy kiểm tra config, connector/task status, worker log và dữ liệu thực tế.

REST API là bề mặt quản trị có quyền thay đổi luồng dữ liệu, vì vậy cần TLS, authentication/authorization, Kafka ACL, quản lý secret và audit. Với production, hãy validate cấu hình, lưu snapshot, thay đổi theo quy trình và xác minh data flow trước khi kết thúc thao tác.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Kafka Connect REST API | HTTP API quản lý connector và task trên Connect worker. |
| Connect worker | Process chạy connector và task. |
| Distributed mode | Chế độ nhiều worker phối hợp qua Kafka internal topics. |
| Connector | Plugin xác định cách đọc từ source hoặc ghi đến sink. |
| Task | Đơn vị công việc thực thi của connector. |
| connector.class | Tên class plugin triển khai connector. |
| tasks.max | Giới hạn số task connector được yêu cầu tạo. |
| POST /connectors | Endpoint tạo connector. |
| PUT /connectors/{name}/config | Endpoint thay cấu hình connector. |
| GET /connectors/{name}/status | Endpoint xem trạng thái connector và task. |
| Pause / Resume | Tạm dừng hoặc tiếp tục connector. |
| Restart | Khởi động lại connector hoặc task. |
| Config validation | Kiểm tra cấu hình theo connector plugin trước khi tạo/cập nhật. |
| plugin.path | Danh sách đường dẫn worker dùng để tìm plugin. |
| config.storage.topic | Internal topic lưu connector/task config. |
| offset.storage.topic | Internal topic lưu source connector offsets. |
| status.storage.topic | Internal topic lưu trạng thái connector/task. |
| ConfigProvider | Cơ chế lấy secret hoặc giá trị cấu hình từ nguồn bên ngoài. |
| Worker ID | Định danh worker đang chạy connector hoặc task. |
| REST authorization | Cơ chế kiểm soát ai được gọi REST management API. |

