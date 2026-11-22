# Quota, giới hạn tốc độ và cô lập tải nền

Kafka phục vụ nhiều producer và consumer trên cùng cluster. Nếu một batch job đột ngột đọc hàng trăm MB mỗi giây hoặc một producer ghi dữ liệu không giới hạn, workload đó có thể chiếm network, request handler, disk I/O và tài nguyên downstream của các luồng quan trọng. **Quota** giúp broker điều tiết mức sử dụng theo user hoặc client ID; **rate limit và backpressure ở ứng dụng** kiểm soát tốc độ tạo/nhận việc; **cô lập tải** kết hợp các cơ chế này để workload nền không làm suy giảm luồng realtime.

Quota không phải giới hạn tốc độ toàn diện cho mọi tài nguyên và cũng không tự tạo ra cách ly vật lý. Muốn bảo vệ payment hoặc order processing, cần nhận diện đúng workload, đặt ngưỡng dựa trên capacity, quan sát thời gian throttle và kiểm soát concurrency ở cả producer, consumer lẫn hệ thống đích.

## 1. Phân biệt quota, rate limit, backpressure và capacity

Các khái niệm này liên quan nhưng giải quyết những vấn đề khác nhau:

| Cơ chế | Nơi thực thi | Mục tiêu | Ví dụ |
|---|---|---|---|
| Kafka quota | Broker | Giới hạn mức sử dụng Kafka theo user/client | Producer tối đa 10 MiB/s |
| Application rate limit | API/service | Giới hạn tốc độ request hoặc event được chấp nhận | Importer tối đa 500 event/s |
| Backpressure | Producer/consumer/pipeline | Làm chậm upstream khi downstream không theo kịp | Tạm dừng poll hoặc giảm worker concurrency |
| Capacity limit | Hạ tầng và ứng dụng | Bảo đảm workload nằm trong năng lực xử lý an toàn | Giới hạn connection pool, CPU và disk IOPS |
| Resource isolation | Kiến trúc triển khai | Giảm mức độ tranh chấp giữa workload | Cluster riêng cho luồng critical |

Ví dụ một importer có thể bị giới hạn ở 500 event/s tại API, nhưng mỗi event lớn hơn dự kiến nên vẫn vượt producer byte quota. Ngược lại, producer byte rate nằm dưới quota nhưng consumer ghi database quá nhanh có thể làm database quá tải. Vì vậy, đặt quota cần đi cùng rate limit và backpressure tại đúng điểm nghẽn.

## 2. Kafka quota kiểm soát điều gì?

Kafka có các loại quota client phổ biến:

| Quota | Ý nghĩa | Workload chịu tác động |
|---|---|---|
| producer_byte_rate | Giới hạn byte producer gửi tới broker trong một đơn vị thời gian | Producer write |
| consumer_byte_rate | Giới hạn byte broker trả về cho consumer | Consumer fetch/read |
| request_percentage | Giới hạn phần trăm thời gian request handler/network thread mà client được sử dụng | Client tạo nhiều request hoặc request tốn thời gian |

Các quota này được áp dụng dựa trên danh tính user, client ID hoặc tổ hợp của chúng. Kafka broker theo dõi mức sử dụng và có thể trì hoãn phản hồi để đưa tốc độ trung bình về gần quota. Client thường quan sát thời gian throttle qua response/request metrics và tiếp tục hoạt động sau thời gian chờ.

### Producer byte quota

Producer byte quota phù hợp để hạn chế một ứng dụng ghi dữ liệu quá nhanh hoặc quá lớn. Ví dụ, một job backfill chỉ được dùng tối đa 10 MiB/s để không chiếm băng thông của order service.

Quota byte không giới hạn trực tiếp số event. Nếu kích thước record thay đổi, cùng một byte rate có thể tương ứng với event/s rất khác nhau:

\[
EventRate \approx \frac{ByteRate}{AverageRecordSize}
\]

Ví dụ 10 MiB/s với record trung bình 1 KiB tương đương xấp xỉ 10.240 record/s trước khi tính overhead và cách broker đo byte. Nếu record trung bình tăng lên 10 KiB, event rate tương ứng chỉ còn khoảng 1.024 record/s.

### Consumer byte quota

Consumer byte quota hạn chế tốc độ dữ liệu broker gửi về client. Đây là cách bảo vệ cluster khỏi một consumer group analytics hoặc export job đọc dữ liệu quá mạnh.

Quota không quyết định consumer được phép đọc topic nào. ACL/authorizer vẫn kiểm soát quyền truy cập; quota chỉ điều tiết mức sử dụng sau khi client đã được xác thực và được phép thực hiện request.

### Request percentage quota

Request percentage quota giới hạn phần thời gian xử lý request mà client có thể sử dụng trên broker. Nó hữu ích khi request có chi phí CPU/network handler khác nhau và byte rate không phản ánh đầy đủ mức tiêu thụ tài nguyên.

Một client gửi ít byte nhưng tạo nhiều request nhỏ hoặc request xử lý tốn thời gian vẫn có thể ảnh hưởng broker. Request percentage giúp bổ sung góc nhìn sử dụng request handler/network thread.

Tên quota, phạm vi và cách broker áp dụng có thể mở rộng theo Kafka release. Hãy xác nhận loại quota được hỗ trợ trong broker version đang triển khai trước khi thiết kế policy.

## 3. Quota gắn với user và client ID

Kafka có thể áp dụng quota theo:

- **User:** principal đã xác thực, ví dụ user SCRAM hoặc principal từ TLS certificate.
- **Client ID:** giá trị client đặt trong cấu hình Kafka, giúp phân biệt ứng dụng hoặc workload.
- **User + client ID:** kết hợp hai danh tính để áp dụng policy cụ thể hơn.
- **Default:** quota mặc định cho các identity không có cấu hình cụ thể.

Ví dụ:

| Identity | Quota gợi ý | Mục đích |
|---|---:|---|
| user=orders-service | producer 20 MiB/s | Bảo vệ luồng order |
| client.id=analytics-backfill | consumer 5 MiB/s | Hạn chế job đọc nền |
| user=payments, client.id=payment-writer | producer 15 MiB/s | Policy cụ thể cho writer thanh toán |
| default client | producer 2 MiB/s | Ngăn client mới dùng tài nguyên không giới hạn |

Các giá trị trên chỉ là ví dụ. Ngưỡng thực tế phải dựa trên load test, peak traffic, record size, replication factor, số broker và năng lực downstream.

### Vì sao client ID phải ổn định?

Quota theo client ID chỉ hữu ích nếu workload dùng client ID nhận diện được:

~~~properties
client.id=analytics-backfill
~~~

Không dùng cùng một client ID cho mọi ứng dụng nếu cần quota khác nhau. Cũng không tạo client ID ngẫu nhiên cho mỗi lần khởi động, vì policy sẽ khó quản lý và metric bị phân mảnh.

Client ID không phải cơ chế xác thực. Client có thể tự khai báo client ID; nếu cần phân biệt workload đáng tin cậy, kết hợp với user/principal và ACL. Tránh chỉ dựa vào client ID để tạo ranh giới bảo mật.

### Principal ảnh hưởng đến quota user

Quota theo user dựa trên principal mà broker xác định sau authentication. Với SASL/SCRAM, principal thường gắn với username. Với mTLS, principal có thể được suy ra từ distinguished name của certificate theo mapping rules.

Nếu nhiều ứng dụng dùng chung một SASL user hoặc certificate principal, quota theo user có thể gộp chúng thành cùng một nhóm. Dùng identity riêng cho các workload cần policy và audit riêng.

## 4. Thứ tự áp dụng quota và phạm vi hiệu lực

Kafka hỗ trợ quota theo identity cụ thể và quota mặc định. Khi cấu hình nhiều cấp, broker chọn quota phù hợp nhất cho client theo quy tắc matching của phiên bản. Mô hình thường gặp:

1. Cặp user và client ID cụ thể.
2. User cụ thể.
3. Client ID cụ thể.
4. Quota mặc định.

Hãy xác nhận precedence và entity matching theo release đang chạy, đặc biệt khi đồng thời cấu hình user default, client default và user/client combination. Không giả định hai quota ở hai cấp sẽ cộng dồn thành một giới hạn duy nhất.

Quota được thực thi tại broker phục vụ request. Tổng throughput quan sát của một client trên toàn cluster phụ thuộc request được phân phối tới những broker nào, partition leader placement và số kết nối. Không mặc định một quota byte-rate ở broker là một cap chính xác duy nhất cho toàn cluster trong mọi topology.

Với workload có nhiều partition leader trên nhiều broker, hãy kiểm tra quota và throttle trên từng broker. Đo throughput aggregate trong thực tế để xác nhận mức giới hạn mà ứng dụng nhận được.

## 5. Broker throttling hoạt động ra sao?

Khi client vượt quota, broker có thể tính thời gian throttle và trì hoãn response hoặc request tiếp theo để giảm mức sử dụng trung bình. Thay vì hiểu quota như một hard reject ngay tại ngưỡng, hãy xem nó như cơ chế broker điều tiết tốc độ.

~~~mermaid
flowchart TD
    A["Producer / Consumer gửi request"] --> B["Broker đo byte rate và request usage"]
    B --> C{"Vượt quota?"}
    C -->|Không| D["Xử lý request bình thường"]
    C -->|Có| E["Tính throttle time"]
    E --> F["Trì hoãn response / request tiếp theo"]
    D --> G["Client tiếp tục gửi/đọc"]
    F --> G
~~~

Client có thể quan sát:

- Throttle time trong response hoặc client metrics.
- Produce/fetch latency tăng khi quota bị áp dụng.
- Throughput ổn định quanh giới hạn khi tải tiếp tục cao.
- Retry/timeout tăng nếu timeout ứng dụng quá ngắn so với thời gian throttle cộng thời gian xử lý.

Quota không nhất thiết làm tốc độ tức thời luôn bằng ngưỡng. Cơ chế đo theo cửa sổ thời gian, burst và cách request được phân phối khiến throughput có thể dao động quanh quota.

### Throttle không đồng nghĩa lỗi nghiệp vụ

Nếu producer nhận response thành công nhưng có throttle time, record vẫn có thể được ghi. Ứng dụng cần phân biệt throttling có chủ đích với produce failure, timeout hoặc authorization error.

Không retry vô hạn chỉ vì thấy latency tăng. Theo dõi throttle time và quota metrics để biết broker đang điều tiết hợp lệ hay có lỗi khác.

## 6. Cấu hình quota động bằng kafka-configs

Kafka hỗ trợ cấu hình quota động trên broker thông qua công cụ kafka-configs. Ví dụ đặt quota cho client analytics-backfill:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --alter \
  --entity-type clients \
  --entity-name analytics-backfill \
  --add-config 'producer_byte_rate=1048576,consumer_byte_rate=5242880,request_percentage=20'
~~~

Trong ví dụ:

- Producer được giới hạn khoảng 1 MiB/s.
- Consumer được giới hạn khoảng 5 MiB/s.
- Request percentage được đặt ở mức 20 theo đơn vị quota của Kafka.

Các giá trị byte-rate tính bằng byte/giây. Kiểm tra cách phiên bản Kafka hiện tại diễn giải request percentage và quota entity trước khi áp dụng.

Xem cấu hình:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --describe \
  --entity-type clients \
  --entity-name analytics-backfill
~~~

Xóa một quota cụ thể:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --alter \
  --entity-type clients \
  --entity-name analytics-backfill \
  --delete-config consumer_byte_rate
~~~

Để cấu hình quota theo user, thay entity type thành users và entity name thành principal tương ứng:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --alter \
  --entity-type users \
  --entity-name analytics-user \
  --add-config 'consumer_byte_rate=5242880'
~~~

Lệnh minh họa cần chạy bằng admin identity có quyền alter broker configuration. Dùng bootstrap endpoint quản trị phù hợp với authentication/TLS của cluster. Không đưa password hoặc JAAS secret trực tiếp vào shell history.

### Quota mặc định

Có thể đặt quota mặc định qua broker configuration hoặc dynamic default entity tùy Kafka version và cách quản trị cluster. Ví dụ các broker property truyền thống:

~~~properties
quota.producer.default=2097152
quota.consumer.default=5242880
quota.request.default=50
~~~

Các property default và cơ chế dynamic config có thể khác theo release; xác minh tài liệu broker version trước khi dùng. Nên bắt đầu bằng quota mặc định đủ bảo vệ cluster, sau đó cấp quota riêng cho workload đã được phân loại.

## 7. Tính quota từ workload thực tế

Không chọn quota chỉ dựa vào số event/s. Hãy tính theo kích thước record, throughput peak, replication và nhu cầu của workload quan trọng.

Ví dụ một backfill job:

- Tốc độ mục tiêu khi chạy không giới hạn: 30 MiB/s.
- Mức tài nguyên được phép dùng trong giờ làm việc: 5 MiB/s.
- Mức ưu tiên: thấp hơn order/payment.

Quota producer/consumer 5 MiB/s giúp giới hạn lưu lượng theo broker. Nếu cần ước lượng event/s với record trung bình 2 KiB:

\[
EventRate \approx \frac{5 \times 1.048.576}{2.048}
\approx 2.560\ event/s
\]

Con số thực tế thay đổi do batch overhead, compression, protocol overhead và cách broker tính byte. Đo throughput ở cả client và broker trong load test.

### Tính capacity và headroom

Giả sử peak business traffic là 40 MiB/s và backfill được phép dùng tối đa 5 MiB/s. Không nên đặt quota business writer bằng đúng 40 MiB/s nếu broker còn phục vụ replication, consumer fetch, metadata và traffic khác.

Hãy:

1. Đo throughput peak theo broker và theo partition leader.
2. Đo request latency, disk/network utilization và ISR health.
3. Xác định headroom cần giữ cho burst và failover.
4. Đặt quota nền thấp hơn mức còn lại sau khi dành headroom cho workload critical.
5. Kiểm thử khi một broker hoặc một AZ mất để xác nhận tải còn lại vẫn an toàn.

Quota không thay thế capacity planning. Nếu tổng nhu cầu vượt capacity cluster, mọi workload cuối cùng vẫn bị ảnh hưởng dù đã đặt quota.

## 8. Phân loại workload và đặt policy

Một cluster thường có nhiều loại workload:

| Tier | Ví dụ | Chính sách gợi ý |
|---|---|---|
| Critical realtime | Payment, order state, inventory | Dành headroom, identity riêng, quota bảo vệ và alert nghiêm ngặt |
| Interactive | Search indexing, user activity | Quota có kiểm soát, latency objective rõ |
| Background | Backfill, reprocessing, export, analytics | Quota thấp, chạy theo lịch, concurrency giới hạn |
| Best effort | Telemetry phụ, thử nghiệm | Quota thấp nhất, có thể pause khi cluster chịu tải cao |

Đừng để batch job dùng cùng user/client ID với payment writer. Nếu chúng dùng chung identity, quota khó tách biệt và một workload có thể tiêu hết phần ngân sách chung.

Với workload critical, quota không phải lúc nào cũng là “unlimited”. Có thể đặt quota đủ cao để tránh noisy neighbor nhưng vẫn bảo vệ broker khỏi client lỗi hoặc loop gửi dữ liệu.

## 9. Cô lập tải nền ở producer

Quota broker là lớp bảo vệ cuối. Producer ứng dụng vẫn nên điều tiết tốc độ và batch để tránh tạo burst quá lớn.

Ví dụ cấu hình producer cho backfill:

~~~properties
client.id=analytics-backfill
acks=all
compression.type=zstd
linger.ms=20
batch.size=65536
buffer.memory=67108864
max.in.flight.requests.per.connection=5
delivery.timeout.ms=120000
request.timeout.ms=30000
~~~

Các cấu hình cần cân nhắc:

- linger.ms và batch.size giúp gom record thành batch, giảm số request nhưng tăng một phần latency.
- compression.type giảm byte truyền trên network và lưu trên broker, đổi lại tiêu thụ CPU.
- buffer.memory giới hạn bộ nhớ producer dùng để giữ record chờ gửi.
- delivery.timeout.ms cần đủ lớn để bao gồm retry và thời gian throttle hợp lý.
- acks và idempotence phải theo yêu cầu durability/ordering; không giảm durability chỉ để vượt quota.

Giới hạn tốc độ ở application bằng token bucket hoặc semaphore nếu cần event/s cap chính xác. Kafka quota giới hạn byte/request usage ở broker, không thay thế rate limiter theo nghiệp vụ.

## 10. Cô lập tải nền ở consumer

Consumer analytics hoặc export job có thể đọc dữ liệu lớn và gây áp lực network, broker fetch, disk cache hoặc hệ thống đích. Kết hợp quota với giới hạn fetch và worker concurrency:

~~~properties
client.id=analytics-exporter
max.partition.fetch.bytes=1048576
fetch.max.bytes=8388608
max.poll.records=200
max.poll.interval.ms=300000
~~~

Các cấu hình này kiểm soát kích thước fetch và số record trả về trong một poll; chúng không phải quota byte/s. Ứng dụng vẫn phải xử lý batch trong thời gian phù hợp với max.poll.interval.ms hoặc thiết kế pause/resume và worker coordination đúng cách.

Ở tầng ứng dụng:

- Giới hạn số worker xử lý đồng thời.
- Dùng bounded queue thay vì queue vô hạn.
- Giảm poll/fetch khi sink chậm.
- Commit offset chỉ sau khi công việc tương ứng hoàn tất an toàn.
- Có thể pause partition khi downstream quá tải và resume khi phục hồi.
- Đặt rate limit cho database/API đích để không chuyển bottleneck sang hệ thống khác.

Không tăng max.poll.records hoặc worker count chỉ để giảm offset lag nếu database đang bão hòa. Việc đó có thể tăng in-flight records và kéo dài thời gian phục hồi.

## 11. Lập lịch và điều phối batch job

Một cách hiệu quả để cô lập tải nền là tránh chạy mọi batch vào giờ cao điểm:

- Chạy backfill theo khung giờ ít traffic.
- Chia job thành các đợt nhỏ có checkpoint.
- Đặt concurrency và quota theo thời gian.
- Tạm dừng batch khi business SLO burn rate tăng hoặc broker headroom giảm.
- Giảm tốc độ khi có under-replicated partitions hoặc downstream latency cao.

Ví dụ policy:

| Điều kiện | Hành động |
|---|---|
| Giờ cao điểm | Backfill tối đa 2 MiB/s |
| Ngoài giờ cao điểm | Có thể tăng lên 8 MiB/s nếu broker còn headroom |
| Oldest payment event age vượt deadline | Pause batch/export job |
| Under-replicated partitions tăng | Giảm quota background và điều tra replication |
| Database sink latency vượt ngưỡng | Giảm worker concurrency và fetch rate |

Điều kiện pause/resume nên dựa trên SLI và metric có hysteresis để tránh bật/tắt liên tục. Ghi lại job checkpoint để batch có thể tiếp tục mà không tạo duplicate side effect.

## 12. Quota và ACL giải quyết hai việc khác nhau

ACL quyết định client được phép thực hiện hành động nào; quota quyết định client được sử dụng tài nguyên ở mức nào.

Ví dụ:

- ACL cho analytics-user quyền READ trên topic events và group analytics-export.
- Quota giới hạn analytics-user hoặc client ID analytics-exporter ở 5 MiB/s.
- Producer payment-writer chỉ có WRITE trên topic payments và quota riêng phù hợp.

Không cấp quyền rộng cho client chỉ để quota hoạt động. Quota không thay thế authentication, authorization, TLS hoặc network policy.

## 13. Cô lập ở cấp cluster khi quota không đủ

Kafka quota điều tiết request nhưng không bảo đảm cách ly tuyệt đối CPU, disk I/O, page cache, network, controller hoặc mọi hoạt động nền. Các workload cùng broker vẫn chia sẻ một số tài nguyên vật lý.

Khi yêu cầu isolation cao, cân nhắc:

- Cluster riêng cho payment/ledger hoặc workload có SLA khác biệt lớn.
- Broker pool riêng nếu kiến trúc và phiên bản triển khai hỗ trợ placement phù hợp.
- Network/storage QoS ở hạ tầng.
- Dedicated consumer/worker pool và database connection pool.
- Tách topic/partition và replication policy theo tier.

Chỉ tách topic không tạo isolation vật lý: topic vẫn có thể đặt partition leader trên cùng broker và dùng chung network/disk. Chỉ tách client ID cũng không tách tài nguyên nếu workload vẫn chạy cùng broker.

Quyết định tách cluster cần tính cả chi phí vận hành, replication, disaster recovery, monitoring, schema governance và cross-cluster data movement.

## 14. Monitoring quota và phát hiện noisy neighbor

Theo dõi cả quota usage lẫn tác động tới SLO:

| Nhóm | Chỉ số cần theo dõi | Ý nghĩa |
|---|---|---|
| Producer | Byte rate theo user/client, throttle time, produce latency, retry/error | Producer có đang bị điều tiết hoặc lỗi không |
| Consumer | Fetch byte rate, throttle time, fetch latency, lag và record age | Consumer có bị quota làm chậm và backlog có tăng không |
| Broker | Request handler/network utilization, request queue, disk/network throughput | Broker còn headroom hay không |
| Replication | Under-replicated/offline partitions, ISR shrink/expand | Background load có ảnh hưởng durability không |
| Business | End-to-end latency, success rate, oldest event age, error budget | Workload critical có bị ảnh hưởng không |

Metric cụ thể và tên JMX phụ thuộc Kafka version, client và exporter. Kiểm tra metric catalog thực tế; không giả định mọi exporter đều cung cấp quota usage theo cùng một tên hoặc label.

Ví dụ metric do monitoring pipeline tự định nghĩa:

~~~text
kafka_client_quota_throttle_seconds{client_id,quota_type}
kafka_client_produce_bytes_per_second{client_id}
kafka_client_fetch_bytes_per_second{client_id}
kafka_client_request_percentage{client_id}
kafka_background_job_inflight{job}
kafka_background_job_paused{job}
~~~

Đây là tên metric minh họa, không phải cam kết tên JMX built-in. Tránh label có cardinality cao như event ID, request ID hoặc raw exception.

### Alert gợi ý

- Throttle time tăng liên tục trên workload critical.
- Background client đạt quota trong thời gian dài và backlog job tăng vượt batch window.
- Consumer lag/oldest record age của payment tăng trong khi background fetch throughput cao.
- Broker request queue hoặc network utilization vượt ngưỡng an toàn.
- Under-replicated partitions xuất hiện đồng thời với batch load tăng.
- Một client ID lạ tạo throughput bất thường hoặc dùng sai principal.

Không alert chỉ vì quota throttle khác 0. Với background job, throttle có thể là hành vi mong muốn. Alert khi throttle làm vi phạm batch deadline hoặc ảnh hưởng SLO critical.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Producer latency tăng nhưng không có lỗi | Producer byte quota đang throttle | Xem client ID, principal, throttle time và quota config |
| Consumer lag tăng sau khi chạy export | Consumer byte quota hoặc sink không theo kịp | Phân biệt broker throttle với database latency |
| Quota không có tác dụng | Client ID thay đổi, principal dùng chung hoặc cấu hình sai entity | Kiểm tra client.id, authenticated principal và describe config |
| Một workload vẫn dùng quá nhiều tài nguyên | Request được phân phối qua nhiều broker hoặc quota chỉ giới hạn một chiều | Đo từng broker, request percentage, producer và consumer rates |
| Realtime latency tăng khi batch chạy | Shared broker resource hoặc downstream contention | Giảm batch quota/concurrency, kiểm tra disk/network và sink |
| Batch không hoàn tất trong cửa sổ | Quota quá thấp hoặc throughput thực tế thấp hơn dự tính | Tính lại byte/event, record size, compression và drain time |
| Broker có under-replicated partitions | Disk/network contention hoặc broker failure | Pause/reduce background load, kiểm tra replication và storage |
| Consumer timeout khi throttle | Timeout ứng dụng không phù hợp với throttle/fetch wait | Điều chỉnh timeout có căn cứ và giảm concurrency |

Quy trình điều tra:

1. Xác định client ID và authenticated principal của workload gây tải.
2. Kiểm tra quota hiện tại và entity matching.
3. Đối chiếu throttle time với produce/fetch latency.
4. Xem request distribution trên từng broker và partition leader.
5. Kiểm tra downstream, disk, network, replication và consumer processing.
6. Giảm hoặc pause workload nền nếu SLO critical bị đe dọa.
7. Điều chỉnh quota sau khi xác định bottleneck, rồi quan sát lại dưới tải thực tế.

Không xóa quota để “thử xem có nhanh hơn không” trên production khi chưa có kế hoạch rollback và headroom được xác nhận.

## 16. Ví dụ policy cho một cluster nhiều workload

Giả sử cluster phục vụ ba nhóm:

| Workload | Identity | Producer quota | Consumer quota | Điều phối |
|---|---|---:|---:|---|
| Order service | user=orders, client.id=orders-writer | 20 MiB/s | 5 MiB/s | Luôn hoạt động, ưu tiên cao |
| Payment service | user=payments, client.id=payment-writer | 15 MiB/s | 10 MiB/s | Luôn hoạt động, theo dõi SLO nghiêm |
| Analytics backfill | user=analytics, client.id=analytics-backfill | 2 MiB/s | 5 MiB/s | Chạy theo lịch, pause khi cluster chịu tải cao |

Đây là ví dụ phân bổ policy, không phải sizing mặc định. Khi một broker mất, partition leader được chuyển và request distribution thay đổi; quota cùng headroom phải được kiểm thử trong tình huống degraded cluster.

Sau khi áp dụng:

1. Đo throughput thực tế theo client và broker.
2. Xác nhận order/payment không bị throttle ngoài dự kiến.
3. Xác nhận analytics hoàn tất trong batch window.
4. Kiểm tra broker request latency, ISR và network/disk.
5. Điều chỉnh quota và lịch chạy theo dữ liệu quan sát.

## 17. Production checklist

- [ ] Phân loại workload theo mức độ quan trọng và deadline.
- [ ] Gán client.id ổn định, có naming convention và owner.
- [ ] Dùng principal riêng cho workload cần quota/audit riêng.
- [ ] Xác định quota producer byte, consumer byte và request percentage phù hợp.
- [ ] Kiểm tra quota precedence, default và entity matching theo Kafka version.
- [ ] Hiểu quota được thực thi trên các broker phục vụ request; benchmark aggregate throughput.
- [ ] Đặt quota từ baseline/load test và giữ headroom cho peak/failover.
- [ ] Kết hợp Kafka quota với application rate limit và backpressure.
- [ ] Giới hạn producer batching/buffer và consumer fetch/worker concurrency.
- [ ] Dùng bounded queue, pause/resume và checkpoint cho batch job.
- [ ] Lập lịch background load ngoài giờ cao điểm hoặc theo SLO signal.
- [ ] Không dùng chung identity giữa realtime và batch nếu cần policy khác nhau.
- [ ] Dùng ACL riêng; không coi quota là cơ chế authorization.
- [ ] Theo dõi throttle time, throughput, lag, record age, broker utilization và ISR.
- [ ] Kiểm thử khi broker mất, downstream chậm và batch burst.
- [ ] Có runbook giảm/pause background workload và rollback quota.
- [ ] Cân nhắc cluster riêng khi yêu cầu isolation vượt khả năng quota.

Kafka quota điều tiết mức sử dụng broker theo user/client identity; application rate limit và backpressure kiểm soát tốc độ ở tầng nghiệp vụ; resource isolation giảm tranh chấp ở hạ tầng. Muốn tải nền không ảnh hưởng luồng realtime, hãy nhận diện workload rõ ràng, đặt quota theo byte/request, giới hạn concurrency, lập lịch batch và theo dõi SLI của luồng quan trọng. Khi cần cách ly cứng, quota đơn lẻ không thay thế cluster hoặc tài nguyên chuyên dụng.
