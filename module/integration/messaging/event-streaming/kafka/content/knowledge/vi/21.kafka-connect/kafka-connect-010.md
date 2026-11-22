# tasks.max, phân chia công việc và giới hạn song song của nguồn

Kafka Connect dùng connector để kết nối Kafka với hệ thống bên ngoài. Một connector thường được chia thành nhiều task để xử lý công việc song song. Thuộc tính `tasks.max` đặt giới hạn số task tối đa mà connector được phép tạo.

Điểm cần nhớ là `tasks.max` là **giới hạn trên**, không phải cam kết rằng Connect sẽ luôn chạy đúng số task đó. Connector quyết định cách chia công việc và có thể tạo ít task hơn giới hạn. Khả năng song song thực tế còn phụ thuộc vào cách nguồn dữ liệu được phân vùng, số partition của topic đối với sink connector, năng lực worker và giới hạn của hệ thống đích.

Hiểu rõ quan hệ giữa connector, task và worker giúp tăng throughput có kiểm soát, tránh tăng task nhưng không tăng năng lực xử lý hoặc gây quá tải hệ thống nguồn/đích.

## 1. Connector, task và worker khác nhau thế nào?

Kafka Connect có ba thành phần cần phân biệt:

- **Connector:** thành phần quản lý cấu hình và tạo task. Connector mô tả cách kết nối với hệ thống nguồn hoặc đích.
- **Task:** đơn vị thực thi công việc. Source task đọc dữ liệu từ hệ thống bên ngoài rồi tạo SourceRecord; sink task nhận SinkRecord từ Kafka rồi ghi sang hệ thống đích.
- **Worker:** tiến trình Kafka Connect chạy connector và task. Một worker có thể chạy nhiều task.

Sơ đồ tổng quát:

~~~mermaid
flowchart TB
    C["Connector: orders-source"] --> T1["Task 0"]
    C --> T2["Task 1"]
    C --> T3["Task 2"]
    T1 --> W1["Connect worker A"]
    T2 --> W2["Connect worker B"]
    T3 --> W1
    W1 --> K["Kafka cluster"]
    W2 --> K
~~~

Trong distributed mode, nhiều worker tham gia cùng một Connect cluster. Framework phân phối task giữa các worker. Một worker có thể chạy nhiều task, và tổng số task của cluster có thể lớn hơn số worker.

Vì vậy:

- `tasks.max=8` không có nghĩa phải có 8 worker.
- Có 3 worker vẫn có thể chạy 8 task nếu tài nguyên đủ.
- Có 8 worker cũng không bảo đảm connector tạo được 8 task.
- `tasks.max` được cấu hình theo từng connector, không phải giới hạn tổng task của toàn Connect cluster.

## 2. tasks.max thực sự điều khiển điều gì?

`tasks.max` là số task tối đa mà connector có thể yêu cầu Kafka Connect tạo. Framework truyền giới hạn này cho connector khi lấy cấu hình task. Connector trả về danh sách task config phù hợp với khả năng chia công việc của nó.

Ví dụ:

~~~properties
connector.class=com.example.OrdersSourceConnector
tasks.max=8
~~~

Nếu connector có thể chia nguồn thành 6 phần độc lập, nó có thể tạo 6 task. Nếu nguồn chỉ có 2 phần hoặc connector chỉ hỗ trợ một task, số task thực tế có thể thấp hơn.

| tasks.max | Khả năng chia việc của connector | Số task thực tế |
|---:|---:|---:|
| 8 | Có 8 phần độc lập | Có thể là 8 |
| 8 | Chỉ có 3 phần độc lập | Có thể là 3 |
| 8 | Connector chỉ tạo một task | 1 |
| 2 | Có 8 phần độc lập | Tối đa 2 |

Không nên xem số task đang chạy là bằng `tasks.max` nếu chưa kiểm tra trạng thái connector. Muốn biết số task thực tế, hãy dùng Connect REST API để đọc task configs và task status.

## 3. tasks.max không phải số worker và không phải số partition

Ba con số này biểu diễn các giới hạn khác nhau:

| Thuộc tính | Đại diện cho | Được điều khiển ở đâu |
|---|---|---|
| `tasks.max` | Giới hạn task của một connector | Connector configuration |
| Số worker | Số tiến trình Kafka Connect tham gia cluster | Hạ tầng triển khai Connect |
| Số partition Kafka | Mức chia nhỏ log của topic | Topic configuration |

Tăng `tasks.max` không tự động:

- Tạo thêm worker.
- Tăng số partition của topic.
- Tăng số shard/table/query partition ở database nguồn.
- Tăng connection limit của database.
- Tăng năng lực ghi của hệ thống đích.

Muốn tăng song song thực tế, phải xác định nút thắt đang nằm ở connector, nguồn, topic partitions, worker hay downstream.

## 4. Source connector: task song song bị giới hạn bởi cách chia nguồn

Source connector đọc dữ liệu từ hệ thống bên ngoài rồi ghi record vào Kafka. Connector phải chia công việc thành các phần độc lập để nhiều source task có thể đọc song song.

Tùy connector, các phần này có thể là:

- Database table hoặc nhóm table.
- Database shard hoặc partition.
- Các query range không chồng lấn.
- File, collection, bucket hoặc logical source partition.
- Các luồng CDC hoặc đơn vị công việc do connector định nghĩa.

Ví dụ một source connector đọc dữ liệu đơn hàng từ 4 shard:

~~~mermaid
flowchart LR
    S["Order database"] --> S0["Shard 0"]
    S --> S1["Shard 1"]
    S --> S2["Shard 2"]
    S --> S3["Shard 3"]
    S0 --> T0["Source task 0"]
    S1 --> T1["Source task 1"]
    S2 --> T2["Source task 2"]
    S3 --> T3["Source task 3"]
    T0 --> K["Kafka topic: orders"]
    T1 --> K
    T2 --> K
    T3 --> K
~~~

Nếu cấu hình `tasks.max=10` nhưng connector chỉ có 4 shard có thể đọc độc lập, connector thường chỉ tạo tối đa 4 task hữu ích. Đặt cao hơn không tạo thêm shard hoặc query range.

### 4.1. Connector quyết định cách chia nguồn

Không phải source connector nào cũng có thể scale tuyến tính bằng `tasks.max`. Một connector có thể:

- Tạo một task duy nhất vì nguồn chỉ cung cấp một stream.
- Tạo một task cho mỗi database partition.
- Chia table hoặc query theo cấu hình riêng.
- Giới hạn số task theo plugin hoặc edition.
- Dùng một task điều phối và nhiều task thực thi, tùy thiết kế.

Đọc tài liệu của đúng connector và phiên bản đang dùng. Đừng suy ra số task từ số bảng hoặc số database connection nếu connector không hỗ trợ cách chia đó.

### 4.2. Source partition và source offset

Kafka Connect theo dõi vị trí đọc của source connector bằng source partition và source offset. Connector cần định danh source partition ổn định để framework biết một vị trí đọc thuộc phần nguồn nào.

Ví dụ khái niệm:

~~~json
{
  "sourcePartition": {
    "database": "orders-db",
    "shard": "shard-02"
  },
  "sourceOffset": {
    "changeSequence": "000000000045"
  }
}
~~~

Khi tăng số task, connector có thể phân phối lại các phần nguồn giữa task. Tính đúng đắn phụ thuộc vào cách connector:

- Chia nguồn không chồng lấn hoặc có cơ chế deduplicate.
- Giữ source partition identity ổn định.
- Khôi phục offset sau khi task được chuyển worker.
- Xử lý restart và rebalance mà không bỏ sót dữ liệu.
- Duy trì semantics của snapshot và streaming nếu connector hỗ trợ CDC.

Không tự thay đổi source partition identity hoặc offset schema khi tăng task. Hãy dùng cơ chế scale được tài liệu connector hỗ trợ.

### 4.3. Giới hạn của hệ thống nguồn

Tăng source task có thể làm tăng đồng thời:

- Số database connection.
- Số query hoặc cursor đang mở.
- CPU và I/O ở database.
- Số request tới API nguồn.
- Băng thông đọc và số file handle.
- Áp lực lên log/CDC retention.

Nếu database chỉ chịu được 5 query đồng thời, tăng task từ 5 lên 20 có thể làm nguồn quá tải mà throughput không tăng. Hãy phối hợp `tasks.max` với connection pool, query partitioning, rate limit và giới hạn tài nguyên nguồn.

## 5. Sink connector: task song song bị giới hạn bởi Kafka partitions và hệ thống đích

Sink connector đọc record từ Kafka rồi ghi sang hệ thống bên ngoài. Các sink task nhận partition assignment từ consumer group do Kafka Connect quản lý.

Ví dụ topic `orders` có 6 partition:

~~~mermaid
flowchart TB
    K["Kafka topic: orders"]
    K --> P0["Partition 0"]
    K --> P1["Partition 1"]
    K --> P2["Partition 2"]
    K --> P3["Partition 3"]
    K --> P4["Partition 4"]
    K --> P5["Partition 5"]
    P0 --> T0["Sink task 0"]
    P1 --> T1["Sink task 1"]
    P2 --> T2["Sink task 2"]
    P3 --> T3["Sink task 3"]
    P4 --> T4["Sink task 4"]
    P5 --> T5["Sink task 5"]
    T0 --> D["Target database"]
    T1 --> D
    T2 --> D
    T3 --> D
    T4 --> D
    T5 --> D
~~~

Nếu connector có 6 partition đầu vào và `tasks.max=10`, không có nghĩa 10 task đều có thể đọc dữ liệu từ cùng một partition trong cùng consumer group. Một partition tại một thời điểm chỉ được gán cho tối đa một consumer trong group. Một số task có thể không nhận partition nào.

Nếu `tasks.max=3`, mỗi task có thể nhận nhiều partition. Điều đó có thể giảm số connection đến hệ thống đích, nhưng mỗi task phải xử lý nhiều dữ liệu hơn.

### 5.1. Không dùng công thức cứng cho mọi sink connector

Với một topic đơn giản, số sink task có việc làm hữu ích thường bị giới hạn bởi số partition đang được subscribe. Với nhiều topic, số partition tổng cộng và logic connector cùng ảnh hưởng assignment.

Tuy nhiên, không thể luôn lấy:

`actual tasks = min(tasks.max, total topic partitions)`

làm công thức chính xác cho mọi connector. Connector có thể tự giới hạn task, quản lý subscription đặc biệt hoặc áp dụng cơ chế song song riêng. Hãy kiểm tra task configs, partition assignment và metric thực tế.

### 5.2. Giới hạn của hệ thống đích

Mỗi sink task có thể tạo connection pool, batch writer hoặc request riêng. Tăng task có thể làm tăng:

- Số database connection.
- Số transaction đồng thời.
- Lượng batch ghi cùng lúc.
- CPU, lock contention và I/O ở database.
- Request rate tới REST API.
- Khả năng gặp rate limit hoặc throttling.

Ví dụ database chỉ cho phép 30 connection và các ứng dụng khác đã dùng 20. Nếu mỗi sink task mở 3 connection, tăng từ 2 lên 6 task có thể vượt giới hạn còn lại. Cần xem cấu hình pool của connector trước khi scale.

## 6. Worker capacity và distributed mode

Trong distributed mode, các worker cùng tham gia một Connect cluster thông qua cấu hình worker chung, gồm group ID và các internal topics lưu config, offset và status.

Framework phân phối connector/task giữa worker. Khi worker mới tham gia hoặc worker cũ rời cluster, task có thể được reassigned và khởi động lại ở worker khác.

~~~mermaid
flowchart TB
    H["Connect cluster / herder"] --> W1["Worker A"]
    H --> W2["Worker B"]
    H --> W3["Worker C"]
    W1 --> A["Source task 0"]
    W1 --> B["Sink task 0"]
    W2 --> C["Source task 1"]
    W2 --> D["Sink task 1"]
    W3 --> E["Source task 2"]
~~~

Một worker có thể chạy nhiều task. Nếu số task tăng nhưng số worker và tài nguyên không tăng, worker hiện tại phải gánh thêm CPU, heap, thread, connection và network I/O.

### 6.1. Standalone mode

Trong standalone mode, một worker process chạy connector và task trong cùng tiến trình. Tăng `tasks.max` có thể cho connector tạo thêm task trong process đó, nhưng không phân phối công việc sang các worker khác.

Nếu mục tiêu là scale ngang qua nhiều máy, cần dùng distributed mode và triển khai thêm worker trong cùng Connect cluster.

### 6.2. Nhiều task trên một worker

Một worker chạy nhiều task không có nghĩa mỗi task được cấp CPU hoặc connection riêng biệt. Các task chia sẻ tài nguyên tiến trình và máy chủ.

Khi tăng task, cần theo dõi:

- CPU và load average.
- JVM heap, GC pause và thread count.
- Network throughput.
- Số connection đến nguồn/đích.
- Worker task failure và restart.
- Độ trễ xử lý batch.

Đừng scale task vượt năng lực worker chỉ vì cluster còn ít worker. Thêm worker có thể giúp phân phối tải, nhưng chỉ hiệu quả nếu connector và nguồn/đích có đủ khả năng song song.

## 7. Cách chọn tasks.max cho source connector

Một quy trình thực tế:

1. Xác định nguồn có thể chia thành bao nhiêu phần độc lập.
2. Đọc tài liệu connector để biết cách nó tạo task configs.
3. Kiểm tra giới hạn connection, query và rate limit của nguồn.
4. Xác định tài nguyên worker có thể dành cho connector.
5. Bắt đầu với số task nhỏ và đo throughput.
6. Tăng dần khi nguồn và worker còn dư năng lực.
7. Kiểm tra source offsets, duplicate, gap và thứ tự dữ liệu.
8. Dừng tăng khi throughput không cải thiện hoặc nguồn bắt đầu quá tải.

Ví dụ nguồn có 12 shard độc lập, database cho phép 8 reader đồng thời và worker đủ tài nguyên. Có thể bắt đầu với `tasks.max=4`, quan sát rồi tăng lên 6 hoặc 8. Không nhất thiết đặt 12 chỉ vì có 12 shard.

### 7.1. Đo hiệu quả scale

Theo dõi:

- Source records polled per second.
- Source records written per second.
- Thời gian đọc mỗi batch.
- Độ trễ từ nguồn đến Kafka.
- Lỗi query, timeout và reconnect.
- Số task đang RUNNING/FAILED.
- Tải database nguồn và worker.

Nếu số task tăng gấp đôi nhưng throughput chỉ tăng nhẹ, có thể nguồn đã chạm giới hạn I/O hoặc worker đang bão hòa.

## 8. Cách chọn tasks.max cho sink connector

Với sink connector, bắt đầu từ số partition của các topic được subscribe và khả năng ghi của hệ thống đích.

Quy trình:

1. Xác định danh sách topic và số partition mỗi topic.
2. Kiểm tra connector hỗ trợ bao nhiêu sink task và cách nó phân phối partition.
3. Xác định giới hạn connection/batch/transaction của hệ thống đích.
4. Đặt `tasks.max` ban đầu đủ để tận dụng partition nhưng không vượt capacity.
5. Quan sát task assignment và sink throughput.
6. Tăng dần nếu còn partition chưa được xử lý đủ nhanh và target còn dư năng lực.
7. Giảm task nếu target gặp lock contention, rate limit hoặc connection exhaustion.

Ví dụ topic có 12 partition, database đích chịu được 6 writer đồng thời. Có thể bắt đầu với 4 hoặc 6 task. Đặt 20 không tạo thêm partition và có thể làm một số task idle hoặc gây quá tải nếu connector mở nhiều connection.

### 8.1. Sink task không nhất thiết bằng một partition

Một task có thể được gán nhiều partition. Số partition là nguồn song song của consumer group, còn cách task xử lý batch và ghi đích phụ thuộc connector.

Nếu một partition chứa hot key hoặc lượng record lớn hơn nhiều partition khác, một task có thể trở thành nút thắt dù tổng số task bằng số partition. Hãy xem throughput và lag theo partition, không chỉ tổng lag của connector.

## 9. tasks.max và thứ tự record

Tăng task có thể thay đổi cách công việc được phân chia, nhưng không tạo ra thứ tự toàn cục giữa nhiều partition.

### 9.1. Source connector

Khi source connector đọc nhiều phần nguồn song song, thứ tự giữa các task thường không được bảo đảm. Nếu nghiệp vụ yêu cầu thứ tự theo entity, connector cần dùng source partition/offset ổn định hoặc Kafka key phù hợp để các event cùng entity được đưa về cùng Kafka partition.

Tăng task không nên làm hai task đồng thời đọc chồng lấn cùng một source range mà không có cơ chế phối hợp.

### 9.2. Sink connector

Kafka giữ thứ tự record trong từng partition. Consumer group phân phối các partition cho sink task, nhưng không có thứ tự tổng thể giữa các partition.

Nếu sink connector ghi song song hoặc batch bất đồng bộ, thứ tự ghi tới hệ thống đích còn phụ thuộc implementation. Hãy kiểm tra semantics của connector nếu thứ tự ghi là yêu cầu bắt buộc.

### 9.3. Tăng partition khác với tăng task

Tăng số partition của topic có thể tăng mức song song của sink connector, nhưng có thể thay đổi key-to-partition mapping đối với record mới. Điều này ảnh hưởng thứ tự theo key nếu partitioner mặc định được sử dụng.

Không tăng partition chỉ để làm cho số partition bằng `tasks.max`. Chọn partition count theo throughput, key distribution, ordering và kế hoạch dài hạn của topic.

## 10. Cấu hình tasks.max trong connector config

`tasks.max` là thuộc tính trong cấu hình của từng connector. Ví dụ source connector:

~~~json
{
  "connector.class": "com.example.OrdersSourceConnector",
  "tasks.max": "6",
  "topic.prefix": "orders",
  "source.endpoint": "https://source.example.internal"
}
~~~

Ví dụ sink connector:

~~~json
{
  "connector.class": "com.example.OrdersSinkConnector",
  "tasks.max": "4",
  "topics": "orders",
  "target.endpoint": "https://target.example.internal"
}
~~~

Tên class và các thuộc tính kết nối trong ví dụ là placeholder; thay bằng plugin thực tế đã cài đặt. Giá trị config của Kafka Connect REST thường được truyền dưới dạng chuỗi.

Không đặt `tasks.max` trong worker properties để điều khiển toàn bộ cluster. Hãy đặt trong connector configuration tương ứng.

## 11. Cập nhật tasks.max qua Kafka Connect REST API

Để thay đổi giới hạn task, đọc cấu hình hiện tại rồi cập nhật toàn bộ connector config.

Đọc config:

~~~bash
curl -s http://connect-1:8083/connectors/orders-source/config
~~~

Ví dụ file `orders-source-config.json` sau khi điều chỉnh:

~~~json
{
  "connector.class": "com.example.OrdersSourceConnector",
  "tasks.max": "8",
  "topic.prefix": "orders",
  "source.endpoint": "https://source.example.internal"
}
~~~

Gửi cấu hình mới:

~~~bash
curl -X PUT \
  -H "Content-Type: application/json" \
  --data-binary @orders-source-config.json \
  http://connect-1:8083/connectors/orders-source/config
~~~

Endpoint PUT nhận cấu hình connector đầy đủ. Không chỉ gửi mỗi trường `tasks.max` nếu các thuộc tính khác đang tồn tại; hãy giữ lại cấu hình cần thiết, gồm converter, transforms, connection, topic và security settings.

Cập nhật config có thể khiến connector/task được reconfigure và cluster phân phối lại task. Tác động cụ thể phụ thuộc phiên bản Kafka Connect và connector. Thực hiện trong cửa sổ triển khai phù hợp nếu việc dừng/restart task ảnh hưởng nguồn hoặc đích.

## 12. Kiểm tra số task thực tế và trạng thái

Sau khi cập nhật, không chỉ nhìn giá trị `tasks.max`. Hãy kiểm tra số task được tạo và trạng thái từng task.

Lấy trạng thái connector và task:

~~~bash
curl -s http://connect-1:8083/connectors/orders-source/status
~~~

Kết quả minh họa:

~~~json
{
  "name": "orders-source",
  "connector": {
    "state": "RUNNING",
    "worker_id": "connect-1:8083"
  },
  "tasks": [
    {
      "id": 0,
      "state": "RUNNING",
      "worker_id": "connect-1:8083"
    },
    {
      "id": 1,
      "state": "RUNNING",
      "worker_id": "connect-2:8083"
    }
  ]
}
~~~

Đọc task configs:

~~~bash
curl -s http://connect-1:8083/connectors/orders-source/tasks
~~~

Đọc trạng thái một task:

~~~bash
curl -s http://connect-1:8083/connectors/orders-source/tasks/1/status
~~~

Các API hữu ích:

| Endpoint | Mục đích |
|---|---|
| `GET /connectors/{name}/config` | Đọc cấu hình connector |
| `GET /connectors/{name}/status` | Trạng thái connector và các task |
| `GET /connectors/{name}/tasks` | Danh sách task config |
| `GET /connectors/{name}/tasks/{taskId}/status` | Trạng thái một task |
| `PUT /connectors/{name}/config` | Cập nhật cấu hình connector |
| `GET /connectors` | Liệt kê connector |

Worker ID cho biết task đang chạy ở worker nào. Nếu số task ít hơn `tasks.max`, hãy xem task configs và tài liệu plugin để hiểu connector đang giới hạn ở đâu.

## 13. Rebalance và vòng đời task khi scale

Trong distributed mode, Connect phân phối task giữa worker. Khi cấu hình connector thay đổi hoặc worker tham gia/rời cluster, framework có thể reconfigure và rebalance.

Một số tác động có thể xảy ra:

- Task cũ dừng và task mới được tạo.
- Task chuyển sang worker khác.
- Source task khôi phục source offset trước khi tiếp tục đọc.
- Sink task tham gia lại consumer group và nhận partition assignment mới.
- Trong thời gian chuyển tiếp, throughput có thể giảm hoặc lag tăng.

Do đó, tăng `tasks.max` không phải thao tác hoàn toàn không gián đoạn. Cần theo dõi trạng thái task cho đến khi ổn định.

### 13.1. Không tự sửa Connect internal topics

Distributed Connect sử dụng internal topics để lưu connector config, source offsets và status. Không chỉnh sửa trực tiếp các topic này để ép số task hoặc điều khiển assignment.

Số task được điều khiển qua connector configuration và framework. Thay đổi nội dung internal topics có thể làm mất metadata, offset hoặc trạng thái cluster.

## 14. Giới hạn song song và dấu hiệu cần scale

| Dấu hiệu | Nút thắt có thể | Hướng xử lý |
|---|---|---|
| Source task ít hơn tasks.max | Connector không chia được thêm nguồn | Kiểm tra source partitions và plugin capability |
| Sink task nhiều nhưng một số task idle | Ít Kafka partitions hơn task hoặc assignment không cân bằng | Kiểm tra topic partitions và task assignment |
| Task đều RUNNING nhưng throughput không tăng | Nguồn/đích hoặc worker đã bão hòa | Đo CPU, I/O, connection và batch latency |
| Worker CPU/GC cao sau khi tăng task | Quá nhiều task trên cùng worker | Thêm worker hoặc giảm tasks.max |
| Database nguồn nhiều query timeout | Quá nhiều source task đồng thời | Giảm task, giới hạn connection và query concurrency |
| Database đích lock contention | Quá nhiều sink writer | Giảm task, tăng batch hợp lý, tối ưu index/transaction |
| Một task có lag lớn hơn hẳn | Hot partition hoặc công việc chia không đều | Kiểm tra key distribution và partition assignment |
| Task liên tục FAILED sau scale | Connector không hỗ trợ mức song song hoặc resource limit | Kiểm tra task logs, connector docs và giới hạn nguồn/đích |

### 14.1. Đo trước và sau khi tăng task

Ghi nhận baseline:

- Số task thực tế.
- Records per second.
- Batch size và batch latency.
- Source-to-Kafka latency hoặc sink write latency.
- Consumer lag đối với sink.
- CPU, heap và GC trên worker.
- Connection count và tải nguồn/đích.
- Task failure/restart count.

Sau khi tăng task, so sánh cùng khoảng thời gian và tải đầu vào tương đương. Nếu throughput không tăng nhưng CPU, connection hoặc error rate tăng, hãy rollback về mức task trước đó và tìm bottleneck.

## 15. Quy trình scale tasks.max an toàn

Một quy trình có thể áp dụng:

1. Xác định connector là source hay sink.
2. Đọc tài liệu đúng phiên bản plugin để biết giới hạn task.
3. Xác định nguồn có thể chia thành bao nhiêu phần độc lập hoặc sink có bao nhiêu partition đầu vào.
4. Kiểm tra connection limit và capacity của hệ thống nguồn/đích.
5. Kiểm tra số worker, CPU, heap, GC và network.
6. Ghi lại cấu hình và metric baseline.
7. Tăng `tasks.max` theo từng bước nhỏ.
8. PUT lại toàn bộ connector config qua REST API.
9. Theo dõi connector/task status đến khi ổn định.
10. Xác minh source offset hoặc sink partition assignment không có gap/duplicate ngoài dự kiến.
11. So sánh throughput, latency, lag và tài nguyên.
12. Tiếp tục tăng chỉ khi còn bottleneck có thể giải quyết bằng thêm task.
13. Giảm `tasks.max` hoặc khôi phục config trước nếu task lỗi, nguồn/đích quá tải hoặc throughput giảm.

Không scale nhiều connector cùng lúc nếu chúng dùng chung database hoặc API có giới hạn connection. Thay đổi từng connector giúp xác định tác động và rollback chính xác hơn.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đặt tasks.max=10 nhưng chỉ có 2 task | Connector chỉ tạo 2 task configs | Kiểm tra plugin capability và cách chia nguồn |
| Tăng tasks.max nhưng throughput không tăng | Nguồn/đích, worker hoặc partition đã là bottleneck | Đo từng tầng trước khi scale tiếp |
| Có task RUNNING nhưng không có record | Task không có source split hoặc sink partition được gán | Kiểm tra task assignment và connector logs |
| Tăng task làm database timeout | Quá nhiều connection/query đồng thời | Giảm tasks.max và giới hạn concurrency |
| Sink có task idle | Số task vượt số partition hữu ích | Điều chỉnh task count theo partition và connector |
| Scale làm lag tăng | Rebalance, task restart hoặc target chậm | Theo dõi thời gian reconfiguration và downstream |
| Source tạo duplicate sau reconfiguration | Connector không chia/khôi phục source offset đúng | Kiểm tra source partition identity và offset behavior |
| Thứ tự record thay đổi | Nhiều source task hoặc retry/partition khác nhau | Xác định ordering key và semantics của connector |
| PUT config làm mất thuộc tính khác | Chỉ gửi tasks.max thay vì toàn bộ config | GET config trước, giữ đầy đủ field rồi PUT |
| Worker bão hòa sau khi tăng task | Nhiều task chia sẻ CPU/heap/connection | Thêm worker hoặc giảm task |

## 17. Checklist chọn và vận hành tasks.max

- [ ] Đã phân biệt connector, task và worker.
- [ ] Hiểu `tasks.max` là giới hạn trên, không phải số task bảo đảm.
- [ ] Đã xác minh connector thực tế tạo bao nhiêu task configs.
- [ ] Source connector có đủ source partitions/ranges độc lập.
- [ ] Sink connector có đủ Kafka partitions hữu ích.
- [ ] Đã kiểm tra giới hạn connection, query và rate limit của nguồn/đích.
- [ ] Worker có đủ CPU, heap, network và thread capacity.
- [ ] Đã đánh giá source offset, duplicate và ordering khi task reassign.
- [ ] Không nhầm tasks.max với số worker hoặc số partition.
- [ ] Cập nhật bằng REST API với toàn bộ connector config.
- [ ] Đã kiểm tra status của connector và từng task sau thay đổi.
- [ ] Theo dõi throughput, latency, lag, CPU, GC và connection count.
- [ ] Có baseline và kế hoạch rollback.
- [ ] Không chỉnh sửa trực tiếp Connect internal topics.
- [ ] Đã thử scale trong môi trường test với tải gần thực tế.

`tasks.max` giới hạn số task mà một connector có thể tạo; connector mới là thành phần quyết định cách chia công việc thực tế. Source connector bị giới hạn bởi khả năng phân vùng hệ thống nguồn, còn sink connector thường bị giới hạn bởi số Kafka partition được gán và năng lực ghi của hệ thống đích. Worker cung cấp tài nguyên để chạy task, nhưng số worker không quyết định số task. Hãy tăng `tasks.max` từng bước, kiểm tra task status và đo throughput, lag cùng tải nguồn/đích để xác định mức song song thực sự có ích.
