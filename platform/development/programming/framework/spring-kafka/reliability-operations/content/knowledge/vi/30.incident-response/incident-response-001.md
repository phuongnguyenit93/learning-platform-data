# Runbook khi consumer lag tăng

## Mục tiêu và phạm vi

Runbook này hướng dẫn xử lý sự cố khi một Kafka consumer group xử lý chậm hơn tốc độ phát sinh dữ liệu, khiến lượng bản ghi chưa được xử lý tăng lên. Mục tiêu trong lúc incident là xác định đúng consumer group, topic và partition bị ảnh hưởng; tìm nguyên nhân nằm ở consumer, ứng dụng, dependency hay Kafka cluster; khôi phục tốc độ xử lý an toàn; rồi xác nhận backlog đang giảm và dữ liệu vẫn được xử lý theo đúng cam kết của hệ thống.

Runbook áp dụng cho ứng dụng dùng Spring for Apache Kafka, gồm listener đơn bản ghi, batch listener và các listener có retry hoặc dead-letter topic (DLT). Tên metric, endpoint Actuator và một số tùy chọn cấu hình có thể khác theo phiên bản Spring Boot, Spring Kafka, Kafka client và hệ thống quan sát đang triển khai. Hãy dùng cấu hình thực tế của dịch vụ khi thao tác.

Trong suốt incident:

- Ghi lại thời điểm bắt đầu, alert, group ID, topic, partition, môi trường, phiên bản ứng dụng và các lần deploy hoặc thay đổi cấu hình gần nhất.
- Ưu tiên khôi phục khả năng xử lý và bảo toàn dữ liệu. Không reset offset, bỏ qua bản ghi hoặc xóa retry/DLT chỉ để làm chỉ số lag giảm.
- Thực hiện một thay đổi có kiểm soát mỗi lần, ghi lại giá trị trước và sau, rồi quan sát tác động trước khi tiếp tục.
- Nếu có dấu hiệu mất dữ liệu do retention, lỗi offset hoặc sự cố broker, chuyển sang quy trình xử lý dữ liệu/incident của hệ thống và báo người phụ trách Kafka.

## 1. Hiểu đúng consumer lag

Với một partition, consumer lag thường được tính gần đúng bằng:

~~~text
lag = log end offset - committed offset
~~~

Committed offset là vị trí tiếp theo mà consumer group sẽ đọc. Log end offset (LEO) là vị trí cuối của log theo cách đo của công cụ quan sát. Vì vậy lag thường biểu thị số offset còn cách phía sau, không phải lúc nào cũng bằng chính xác số message có thể đọc được.

Có một số trường hợp cần lưu ý:

- Topic compacted có thể có khoảng trống offset do bản ghi cũ bị compact. Chênh lệch offset khi đó không bằng số bản ghi thực tế còn lại.
- Với consumer dùng isolation level `read_committed`, consumer chỉ đọc được đến Last Stable Offset (LSO). Nếu topic có giao dịch đang mở, phép đo dựa trên LEO có thể hiển thị phần lag mà consumer chưa thể đọc.
- Khi log start offset đã vượt committed offset, dữ liệu cũ có thể đã hết retention. Đây là dấu hiệu cần điều tra ngay, không phải tình huống để tự động reset offset.
- Một số công cụ lấy high watermark, LEO hoặc LSO làm mốc; các metric vì thế có thể khác nhau. Khi so sánh xu hướng, hãy dùng cùng một nguồn metric.

Không đánh giá incident chỉ bằng tổng lag. Cần xem đồng thời:

| Chỉ số | Ý nghĩa khi điều tra |
|---|---|
| Lag theo group/topic/partition | Xác định phạm vi và partition bị nghẽn |
| Tốc độ producer (records in/sec) | Lượng công việc mới đi vào |
| Tốc độ consumer (records consumed/sec) | Năng lực xử lý hiện tại |
| Tuổi của bản ghi chưa xử lý lâu nhất | Mức trễ mà nghiệp vụ thực sự đang chịu |
| Số consumer member đang hoạt động | Kiểm tra group có consumer nhận partition hay không |
| Số lần rebalance và trạng thái group | Phát hiện consumer liên tục rời/vào group |
| Thời gian xử lý listener và tỷ lệ lỗi | Tìm listener hoặc dependency làm chậm |
| Retry, DLT và commit rate | Phát hiện bản ghi lỗi hoặc offset không tiến triển |

Lag tăng liên tục thường đáng lo hơn một giá trị lag cao nhưng đang giảm. Tuổi bản ghi có thể phản ánh tác động nghiệp vụ tốt hơn số offset, đặc biệt khi tốc độ phát sinh dữ liệu thay đổi mạnh.

Nếu có backlog (B), tốc độ đến (I) bản ghi/giây và tốc độ xử lý (C) bản ghi/giây, thời gian bắt kịp ước lượng là:

~~~text
thời gian bắt kịp = B / (C - I), khi C > I
~~~

Nếu C <= I, consumer không thể làm backlog giảm ở năng lực hiện tại. Đây chỉ là ước lượng cho cả group; partition nóng, thời gian xử lý không đều và retry có thể khiến thời gian thực tế dài hơn.

## 2. Quy trình phản ứng nhanh

### Bước 1 — Xác nhận alert và phạm vi ảnh hưởng

1. Xác nhận alert đang phản ánh dữ liệu mới hay metric bị stale, mất scrape hoặc exporter lỗi.
2. Lấy group ID, topic, môi trường và khoảng thời gian lag bắt đầu tăng từ dashboard, log hoặc cấu hình dịch vụ.
3. Xác định consumer group đó phục vụ luồng nghiệp vụ nào, mức trễ tối đa được chấp nhận và có luồng downstream nào đang chờ kết quả hay không.
4. Kiểm tra producer có vừa tăng lưu lượng, replay dữ liệu, chạy backfill hoặc phát lại sự kiện hay không.
5. Ghi lại lag tổng, lag lớn nhất theo partition, tuổi bản ghi cũ nhất, tốc độ vào/ra và số consumer hiện tại làm mốc so sánh.

Không suy ra group ID chỉ từ tên deployment. Hãy xác minh group ID hiệu lực trong cấu hình Spring Kafka hoặc trong thông tin group của Kafka; nhiều listener có thể dùng group ID riêng.

### Bước 2 — Kiểm tra trạng thái consumer group

Chạy lệnh từ máy hoặc pod có Kafka CLI và quyền đọc metadata của cluster. Thay các giá trị trong dấu ngoặc nhọn bằng thông tin của môi trường:

~~~bash
BOOTSTRAP_SERVERS="<broker-1:9092,broker-2:9092>"
GROUP_ID="<consumer-group-id>"
TOPIC="<topic-name>"

# Tổng quan committed offset, log end offset và lag theo partition
kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID"

# Trạng thái group
kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --state

# Thành viên và partition assignment (nếu Kafka CLI hỗ trợ)
kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --members --verbose
~~~

Nếu cluster yêu cầu xác thực, thêm `--command-config <client.properties>` vào từng lệnh. Không đưa password, token hoặc nội dung file cấu hình xác thực vào ticket hay log incident.

Đọc kết quả:

- `CURRENT-OFFSET`: committed offset của group trên partition.
- `LOG-END-OFFSET`: mốc cuối log mà CLI báo cáo.
- `LAG`: độ chênh được CLI tính cho partition.
- `CONSUMER-ID`, `HOST`, `CLIENT-ID`: giúp xác định member và instance đang giữ assignment.
- Trạng thái group như `Stable`, `PreparingRebalance`, `CompletingRebalance` hoặc `Empty` cho biết group đang ổn định, rebalance hay không có member. Tên trạng thái có thể khác giữa các phiên bản Kafka.

Nếu lệnh không trả về group hoặc partition như mong đợi, kiểm tra lại cluster bootstrap, quyền ACL, group ID, topic và môi trường. Đừng kết luận group đã mất chỉ từ một lỗi kết nối CLI.

### Bước 3 — Phân loại nhanh theo dấu hiệu

| Dấu hiệu | Hướng điều tra đầu tiên |
|---|---|
| Group không có member hoặc trạng thái Empty | Pod không chạy, listener không khởi tạo, sai group ID, lỗi kết nối hoặc ACL |
| Group liên tục Preparing/Completing Rebalance | Pod restart, deploy, heartbeat, poll interval, xử lý một poll quá lâu hoặc member mất kết nối |
| Lag tăng trên hầu hết partition | Producer tăng tải, tổng năng lực consumer không đủ hoặc dependency chung đang chậm |
| Chỉ một vài partition lag cao | Partition nóng, key phân bố lệch, một record gây lỗi hoặc assignment không cân bằng |
| Consumer có member nhưng committed offset đứng yên | Listener bị block, retry kéo dài, xử lý chưa hoàn tất hoặc commit/ack có vấn đề |
| Consumer rate cao nhưng lag vẫn tăng | Tốc độ đầu vào cao hơn tốc độ xử lý |
| Listener xử lý nhanh nhưng lag không giảm | Kiểm tra commit, group ID/metric đang xem, rebalance và mốc offset của công cụ |
| Lag đột ngột về 0 sau một thao tác | Xác minh offset và dữ liệu nghiệp vụ; lag bằng 0 không chứng minh bản ghi đã được xử lý đúng |
| Log có OffsetOutOfRange hoặc log start vượt committed offset | Kiểm tra retention và khả năng dữ liệu đã bị loại khỏi log; báo người phụ trách |

### Bước 4 — Xác định mức độ nghiêm trọng

Đánh giá theo tác động nghiệp vụ, tuổi bản ghi và khả năng bắt kịp, không dùng một ngưỡng lag chung cho mọi topic.

- **Mức nghiêm trọng cao:** luồng thanh toán, đơn hàng hoặc dữ liệu cần xử lý trong SLA đang trễ; tuổi bản ghi vượt SLA; lag tiếp tục tăng; group không có member; có dấu hiệu mất dữ liệu hoặc lỗi commit.
- **Mức cần xử lý:** lag tăng ổn định, thời gian bắt kịp vượt mục tiêu, một số partition có tốc độ xử lý thấp hoặc retry tăng.
- **Mức theo dõi:** lag dao động ngắn sau đợt tải cao, consumer rate đã vượt producer rate và tuổi bản ghi đang giảm.

Nếu hệ thống đã định nghĩa severity và SLA riêng, dùng định nghĩa đó để mở incident và escalation.

## 3. Thu thập bằng chứng trước khi thay đổi

### 3.1. Kiểm tra topic và partition

~~~bash
kafka-topics.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --topic "$TOPIC"
~~~

Ghi nhận số partition, leader, replica và ISR. So sánh partition có lag cao với partition còn lại. Nếu partition không có leader, ISR bất thường hoặc metadata thay đổi liên tục, chuyển điều tra sang Kafka broker/cluster.

Kiểm tra log start offset bằng công cụ offset phù hợp với bản Kafka đang chạy, nếu được cấp quyền. Nếu log start offset đã vượt committed offset, retention có thể đã loại bỏ dữ liệu consumer chưa xử lý. Không tự đặt offset về earliest/latest để che dấu tình trạng này.

### 3.2. Kiểm tra metric Kafka consumer

Nếu JMX được bật, các nhóm metric Kafka consumer hữu ích gồm:

| Nhóm JMX | Metric cần xem | Ý nghĩa |
|---|---|---|
| `kafka.consumer:type=consumer-fetch-manager-metrics,client-id=...` | `records-lag-max` | Lag lớn nhất mà member quan sát được |
| Cùng nhóm fetch manager | `records-consumed-rate`, `bytes-consumed-rate` | Tốc độ đọc dữ liệu |
| Cùng nhóm fetch manager | `fetch-rate`, `fetch-latency-avg`, `fetch-latency-max` | Tần suất và độ trễ fetch |
| `kafka.consumer:type=consumer-coordinator-metrics,client-id=...` | `commit-rate`, `commit-latency-avg` | Tần suất và độ trễ commit |
| Cùng nhóm coordinator | `heartbeat-rate`, `join-rate`, `sync-rate` | Hoạt động heartbeat và group coordination |

Metric JMX của từng member không thay thế dashboard lag theo group và partition. `records-lag-max` là giá trị lớn nhất của member, không phải tổng backlog của group.

Tên metric được expose qua Micrometer/Prometheus phụ thuộc phiên bản và cách cấu hình. Dùng endpoint `/actuator/metrics` để khám phá metric được đăng ký, hoặc `/actuator/prometheus` nếu ứng dụng đã bật Prometheus registry. Không giả định endpoint đang public; chỉ truy cập qua đường quản trị được phép.

### 3.3. Kiểm tra metric ứng dụng Spring Kafka

Đối chiếu các nhóm thông tin sau trên dashboard và log:

- Thời gian xử lý mỗi lần gọi listener, số record mỗi batch và tỷ lệ listener hoàn tất.
- Số exception theo loại, số lần retry, thời gian backoff, số bản ghi được chuyển sang DLT.
- Số thread listener đang hoạt động, thời gian chờ thread và mức sử dụng CPU.
- Heap, GC pause, memory pressure, số thread và tình trạng connection pool.
- Độ trễ, timeout, error rate và giới hạn throughput của database hoặc HTTP service mà listener gọi.
- Số lần rebalance, số consumer member, partition assignment và thời gian consumer không poll.
- Tốc độ producer, request/fetch latency, quota throttling và lỗi kết nối Kafka.

Khi tìm log, ghép theo group ID, listener ID, topic, partition và offset. Nếu ứng dụng chưa ghi đủ các trường này, dùng log Kafka client và metric assignment để khoanh vùng. Tránh ghi payload có dữ liệu cá nhân, token hoặc bí mật vào log.

### 3.4. Kiểm tra thay đổi gần thời điểm bắt đầu

Đối chiếu thời điểm lag bắt đầu tăng với:

- Deploy, restart, autoscaling hoặc thay đổi số replica.
- Thay đổi `group.id`, topic subscription, concurrency, partition count hoặc assignor.
- Thay đổi `max.poll.records`, `max.poll.interval.ms`, ack mode hoặc retry/backoff.
- Producer bắt đầu replay/backfill hoặc phát sinh traffic tăng đột biến.
- Database migration, connection pool cạn, downstream rate limit hoặc sự cố mạng.
- Kafka broker rolling restart, partition leader election, ISR shrink hoặc quota thay đổi.

Thời điểm trùng nhau là manh mối, chưa đủ để khẳng định nguyên nhân. Xác minh bằng metric và log.

## 4. Xử lý theo nguyên nhân

### 4.1. Không có consumer member

Kiểm tra deployment, pod/container, readiness/liveness, log khởi động và kết nối Kafka. Xác nhận:

1. Ứng dụng đã khởi động listener container thành công.
2. Broker bootstrap và DNS/network có thể truy cập từ runtime.
3. ACL cho phép đọc topic và tham gia group.
4. Group ID và topic subscription đúng với môi trường.
5. Không có lỗi deserialize hoặc cấu hình khiến listener dừng ngay khi khởi động.
6. Không có thay đổi khiến các instance vô tình dùng group ID khác nhau.

Khôi phục instance hoặc cấu hình lỗi. Sau khi member tham gia group, theo dõi assignment và committed offset. Nếu group ID thay đổi, group mới có thể bắt đầu từ offset theo `auto.offset.reset`; việc này có thể tạo một luồng đọc khác và không tự động tiếp tục vị trí của group cũ. Không đổi group ID trong incident nếu chưa hiểu rõ tác động.

### 4.2. Consumer liên tục rebalance

Các nguyên nhân phổ biến gồm pod restart, network chập chờn, listener xử lý một poll quá lâu, consumer không gọi poll trong thời gian cho phép, thay đổi membership hoặc assignment.

Kiểm tra:

- Số lần rebalance theo thời gian và log join/sync/heartbeat.
- Thời gian xử lý batch lớn nhất, không chỉ thời gian trung bình.
- Giá trị hiệu lực của `max.poll.interval.ms` và `max.poll.records`.
- Pod restart/OOM, CPU throttling, GC pause và network timeout.
- Có deploy hoặc autoscaler liên tục thêm/bớt instance hay không.
- Partition assignment có thay đổi bất thường hay không.

Với Kafka consumer, `max.poll.interval.ms` giới hạn khoảng thời gian tối đa giữa các lần gọi poll trong chế độ group management thông thường. Nếu listener mất quá lâu để xử lý dữ liệu trả về từ một poll, consumer có thể bị xem là không còn tiến triển và group thực hiện rebalance. `session.timeout.ms` và heartbeat liên quan đến phát hiện member mất kết nối; chúng không thay thế việc xử lý đúng poll interval.

Biện pháp:

1. Khắc phục nguyên nhân làm listener hoặc JVM bị treo/chậm.
2. Giảm `max.poll.records` nếu batch hiện tại mất quá lâu để xử lý; đo lại throughput và thời gian xử lý.
3. Nếu workload thực sự cần thời gian xử lý dài, tính toán lại `max.poll.interval.ms` theo thời gian xử lý tối đa có kiểm soát, cộng biên an toàn. Không tăng giá trị chỉ để che một listener bị treo.
4. Ổn định số replica và lịch deploy/autoscaling trong thời gian incident.
5. Chỉ cân nhắc static membership hoặc thay đổi partition assignor sau khi hiểu tác động đến thời gian phát hiện member lỗi và quy trình deploy.

### 4.3. Tốc độ dữ liệu vào cao hơn năng lực consumer

Nếu producer rate lớn hơn consumer rate trên phần lớn partition, group cần thêm năng lực xử lý hoặc cần giảm tải đầu vào theo thỏa thuận nghiệp vụ.

Kiểm tra trước khi scale:

- Số partition của topic và số consumer đang thực sự nhận assignment.
- Tổng số listener consumer trên tất cả pod. Với một group, một partition chỉ được gán cho tối đa một consumer member tại một thời điểm.
- CPU, memory, thread, connection pool và giới hạn downstream.
- Thời gian xử lý một record/batch và số thao tác I/O đồng bộ trong listener.
- Tốc độ producer có phải đợt tăng tải tạm thời hay thay đổi lưu lượng lâu dài.

**Tăng replica hoặc concurrency có kiểm soát**

Spring Kafka cho phép cấu hình concurrency trên listener container. Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

Hoặc cấu hình container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> kafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Giá trị trong ví dụ chỉ minh họa. Tổng consumer member cho listener group xấp xỉ số pod nhân concurrency trên mỗi pod. Số consumer thực sự có partition assignment không thể vượt số partition của topic. Nếu có 6 partition và tổng concurrency là 10, ít nhất 4 consumer sẽ không nhận partition; tăng thêm consumer không làm luồng đó xử lý nhanh hơn.

Tăng replica/concurrency từng bước, theo dõi rebalance, throughput, CPU và dependency. Dừng scale nếu database hoặc dịch vụ downstream bắt đầu quá tải. Nếu các pod không dùng chung group ID, mỗi group sẽ nhận bản sao dữ liệu riêng thay vì chia nhau partition; xác minh group ID trước khi scale.

**Tối ưu xử lý**

- Giảm thao tác đồng bộ hoặc truy vấn lặp trong listener; dùng bulk operation nếu dependency hỗ trợ.
- Xem xét batch listener khi nghiệp vụ cho phép xử lý theo lô và có thể kiểm soát lỗi từng record.
- Chỉ tăng `max.poll.records` khi thời gian xử lý, memory và poll interval còn đủ biên. Batch lớn hơn có thể tăng throughput nhưng cũng kéo dài thời gian trước lần poll tiếp theo và làm tăng lượng công việc đang giữ trong bộ nhớ.
- Nếu xử lý song song bên trong listener, giới hạn số tác vụ đồng thời và bảo toàn thứ tự/idempotency theo yêu cầu nghiệp vụ. Không đưa record vào một queue không giới hạn rồi commit offset trước khi công việc thực sự hoàn tất.
- Kiểm tra serialization/deserialization, kích thước record và chi phí chuyển đổi payload.

**Khi cân nhắc tăng partition**

Tăng partition có thể tăng mức song song tối đa trong tương lai, nhưng không phải thao tác chữa lag tức thời. Việc tăng partition không tự phân phối lại backlog hiện có theo cách bảo đảm cân bằng. Với key-based partitioning, tăng số partition có thể làm thay đổi partition mà key được ánh xạ tới, ảnh hưởng thứ tự của các bản ghi cùng key giữa dữ liệu cũ và mới. Chỉ tăng partition sau khi đánh giá ordering, consumer assignment, capacity broker và kế hoạch migration.

### 4.4. Dependency phía sau listener bị chậm hoặc lỗi

Ví dụ: listener đọc Kafka bình thường nhưng mỗi record phải ghi database, gọi HTTP service hoặc chờ một hệ thống khác. Khi dependency chậm, consumer giữ partition lâu hơn và committed offset không tiến triển.

Kiểm tra dashboard và log của dependency cùng thời điểm:

- Database: connection pool cạn, lock contention, query chậm, deadlock, transaction kéo dài hoặc storage latency.
- HTTP/gRPC: timeout, rate limit, retry storm, DNS hoặc network lỗi.
- Cache: miss tăng, latency cao hoặc connection bị giới hạn.
- Object storage/search service: throttling, quota hoặc request timeout.

Biện pháp:

1. Khôi phục dependency theo runbook của dịch vụ đó; phối hợp owner nếu đây là sự cố liên dịch vụ.
2. Giới hạn concurrency ở consumer hoặc client để không làm dependency quá tải thêm.
3. Dùng timeout hữu hạn và retry có backoff/jitter theo chính sách của ứng dụng; tránh retry vòng lặp nhanh.
4. Nếu cần tạm ngừng nhận thêm bản ghi trong khi dependency phục hồi, có thể pause listener container có kiểm soát. Ví dụ:

~~~java
@Autowired
private KafkaListenerEndpointRegistry registry;

public void pauseListener() {
    MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");
    if (container != null) {
        container.pause();
    }
}

public void resumeListener() {
    MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");
    if (container != null) {
        container.resume();
    }
}
~~~

Thay `ordersListener` bằng listener ID thực tế. Pause có thể chỉ có hiệu lực ở vòng poll tiếp theo và không hủy công việc đang xử lý. Container vẫn cần duy trì hoạt động poll/coordination theo cơ chế của Spring Kafka. Theo dõi trạng thái pause và chỉ resume khi dependency đã đủ khỏe.
5. Không tạo queue in-memory không giới hạn để hấp thụ backlog. Cách đó chuyển áp lực từ Kafka sang heap, có thể gây OOM và mất trạng thái công việc chưa hoàn tất.

### 4.5. Một partition bị nghẽn hoặc key phân bố lệch

Nếu một partition có lag cao trong khi các partition khác gần như bình thường, tìm nguyên nhân cục bộ:

- Một key tạo ra lượng dữ liệu lớn và dồn vào cùng partition.
- Một record có payload bất thường hoặc gây lỗi deserialize/validation.
- Một thao tác xử lý riêng cho key đó bị chậm.
- Partition leader hoặc broker chứa replica có vấn đề.
- Assignment hoặc consumer instance đang giữ partition đó có tài nguyên bất thường.

Đối chiếu partition, consumer ID, offset và log của listener. Nếu cùng một offset xuất hiện lặp lại với cùng exception, có thể record đang chặn tiến độ partition do retry/error handler.

Không tự bỏ qua record. Xác định loại lỗi:

- **Lỗi tạm thời:** dependency timeout hoặc throttling. Khôi phục dependency và retry theo backoff hữu hạn.
- **Lỗi dữ liệu:** schema không tương thích, payload sai hoặc dữ liệu nghiệp vụ không hợp lệ. Thu thập metadata cần thiết, chuyển theo quy trình xử lý lỗi/DLT của ứng dụng và bảo đảm có người chịu trách nhiệm xử lý bản ghi.
- **Lỗi lập trình:** exception tái hiện ổn định. Cân nhắc rollback/fix ứng dụng theo quy trình deploy; xác định cách replay sau khi sửa.

Nếu dùng `DefaultErrorHandler`, `DeadLetterPublishingRecoverer` hoặc `@RetryableTopic`, kiểm tra số lần retry, backoff, exception được retry hay recover, DLT destination và chính sách commit sau khi recover. Retry topic có thể làm thay đổi thứ tự xử lý so với topic gốc; phải hiểu rõ cam kết ordering trước khi thay đổi retry policy.

### 4.6. Committed offset không tiến triển

Nếu listener có vẻ vẫn hoạt động nhưng `CURRENT-OFFSET` đứng yên, kiểm tra cơ chế ack/commit:

- `enable.auto.commit` đang bật hay tắt.
- Ack mode thực tế của listener container: RECORD, BATCH, TIME, COUNT, COUNT_TIME, MANUAL hoặc MANUAL_IMMEDIATE.
- Với MANUAL, ứng dụng có gọi acknowledge sau khi xử lý thành công hay không.
- Có exception khiến listener không hoàn tất hoặc error handler chưa recover hay không.
- Transaction có commit thành công hay rollback liên tục không.
- Có async processing khiến offset được ack trước khi công việc thực tế kết thúc không.
- Dashboard đang quan sát đúng group ID và đúng cluster hay không.

Spring Kafka listener container thường quản lý commit theo ack mode của container; cấu hình thực tế có thể khác theo phiên bản và ứng dụng. Kiểm tra cấu hình đang chạy thay vì suy luận từ cấu hình mẫu. Với xử lý bất đồng bộ, cần thiết kế ack/commit sao cho offset chỉ tiến lên khi công việc tương ứng đã hoàn tất theo semantics mong muốn. Việc commit sớm có thể làm mất khả năng phát lại record sau sự cố.

### 4.7. Kafka broker, network hoặc quota có vấn đề

Nếu nhiều consumer group cùng bị ảnh hưởng, hoặc consumer fetch latency và lỗi kết nối tăng đồng thời, kiểm tra cluster:

- Broker offline, partition leader không có hoặc leader election liên tục.
- Under-replicated partitions, ISR shrink và controller instability.
- Disk utilization/latency, network saturation và request queue time.
- Fetch request latency, request handler idle percent và quota throttling.
- ACL/authentication, DNS, TLS, firewall hoặc kết nối từ subnet của ứng dụng.
- Producer ingress tăng bất thường làm cluster chịu tải cao.

Dùng `kafka-topics.sh --describe` để kiểm tra leader/replica/ISR của topic. Các metric broker và log cluster cần được Kafka operator/platform team xác nhận. Không restart broker, thay replication factor hoặc thay quota trong lúc incident nếu chưa có người phụ trách cluster điều phối.

## 5. Kiểm tra cấu hình Spring Kafka liên quan

Các cấu hình dưới đây là điểm cần xem xét khi đã có bằng chứng phù hợp. Không áp dụng đồng loạt trong incident:

| Cấu hình | Tác động | Điều cần cân nhắc |
|---|---|---|
| `spring.kafka.listener.concurrency` hoặc container `setConcurrency` | Số consumer thread cho listener container trên mỗi instance | Tổng consumer group và số partition; tải dependency |
| `max.poll.records` | Số record tối đa trả về trong một lần poll | Batch processing time, memory và poll interval |
| `max.poll.interval.ms` | Khoảng tối đa giữa các lần poll trong group management | Thời gian xử lý poll dài nhất; không dùng để che listener bị treo |
| `session.timeout.ms` | Thời gian phát hiện member mất heartbeat theo cấu hình protocol | Độ nhạy phát hiện lỗi và network jitter |
| `heartbeat.interval.ms` | Nhịp heartbeat trong các cấu hình dùng heartbeat interval phía client | Phải phù hợp với session timeout và protocol |
| `fetch.min.bytes`, `fetch.max.wait.ms` | Điều kiện gom dữ liệu cho fetch | Độ trễ và throughput; chỉ tinh chỉnh khi có số đo |
| `max.partition.fetch.bytes`, `fetch.max.bytes` | Giới hạn dữ liệu fetch | Kích thước record/batch, memory và broker response |
| `auto.offset.reset` | Hành vi khi group không có offset hợp lệ | Không phải cơ chế khôi phục offset đã mất; có thể bắt đầu ở earliest/latest theo cấu hình |
| Ack mode và `enable.auto.commit` | Thời điểm commit offset | At-least-once/exactly-once và khả năng phát lại |

Ví dụ khai báo cấu hình consumer trong Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      concurrency: 3
~~~

Đây là cấu hình minh họa, không phải giá trị khuyến nghị chung. Xác nhận phiên bản Spring Boot và cách binder nhận property có dấu chấm trước khi áp dụng. Giá trị `max.poll.interval.ms` phải lớn hơn thời gian xử lý poll lớn nhất có biên an toàn; `max.poll.records` phải phù hợp với thời gian xử lý và tài nguyên. Sau mỗi thay đổi, deploy theo quy trình chuẩn và theo dõi rebalance, throughput, lỗi và dependency.

## 6. Xác nhận phục hồi

Chỉ đóng incident khi có bằng chứng cho thấy cả khả năng xử lý và kết quả nghiệp vụ đã phục hồi. Kiểm tra tối thiểu:

1. Consumer group có member ổn định và partition assignment đúng.
2. Lag theo từng partition đang giảm trong một khoảng thời gian đủ dài; không chỉ tổng lag giảm do metric mất dữ liệu hoặc offset bị thay đổi.
3. Consumer rate cao hơn producer rate đủ lâu để backlog tiếp tục giảm.
4. Tuổi bản ghi chưa xử lý lâu nhất đang trở về trong SLA.
5. Committed offset tiến triển bình thường và không có lỗi commit/transaction kéo dài.
6. Listener error, retry, DLT và rebalance rate trở về mức chấp nhận được.
7. CPU, heap, GC, connection pool và dependency không bị quá tải sau khi tăng concurrency.
8. Các luồng nghiệp vụ downstream đã nhận và xử lý dữ liệu; kiểm tra bằng số liệu nghiệp vụ hoặc đối soát phù hợp.

Theo dõi thêm sau khi lag về ngưỡng bình thường để chắc chắn hệ thống không tái diễn khi tải trở lại. Ghi lại thời điểm bắt đầu phục hồi, thời điểm đạt SLA và thay đổi đã giúp khắc phục.

## 7. Thao tác có rủi ro cao cần kiểm soát

### Không reset offset để làm đẹp dashboard

Lệnh reset offset có thể bỏ qua dữ liệu chưa xử lý hoặc phát lại dữ liệu đã xử lý. Ví dụ các lựa chọn `--to-earliest`, `--to-latest`, `--to-offset` và `--shift-by` có tác động khác nhau; chế độ `--execute` ghi thay đổi thật vào group. Không chạy các lệnh này như bước xử lý lag thông thường.

Nếu có yêu cầu reset offset nghiệp vụ:

1. Xác định chính xác cluster, group, topic và partition.
2. Chốt offset hiện tại, offset mục tiêu và khoảng dữ liệu bị ảnh hưởng.
3. Xác định replay có gây duplicate side effect hay không; kiểm tra idempotency và cơ chế deduplication.
4. Có phê duyệt của owner nghiệp vụ và người phụ trách Kafka theo quy trình tổ chức.
5. Thực hiện trong cửa sổ kiểm soát, lưu lại output trước/sau và kế hoạch rollback hoặc đối soát.

### Không tăng concurrency vượt năng lực downstream

Thêm consumer có thể tăng request đồng thời đến database/API và làm sự cố nặng hơn. Trước mỗi lần scale, xác minh dependency còn headroom, connection pool và giới hạn rate. Nếu dependency đang bão hòa, giới hạn concurrency hoặc pause listener có thể an toàn hơn.

### Không tăng partition hoặc đổi group ID tùy tiện

Tăng partition có thể thay đổi key-to-partition mapping và ordering. Đổi group ID có thể tạo group mới với hành vi chọn offset khác. Cả hai đều cần đánh giá dữ liệu và kế hoạch triển khai riêng.

### Không commit trước khi xử lý hoàn tất

Không ack/commit offset chỉ vì record đã được đưa vào một queue bất đồng bộ. Nếu process chết trước khi queue xử lý xong, Kafka có thể xem record đã hoàn tất và không phát lại. Dùng cơ chế lưu trạng thái bền vững, transaction hoặc ack sau xử lý theo thiết kế của ứng dụng.

## 8. Checklist thao tác trong incident

### Trong 5 phút đầu

- [ ] Xác nhận alert, thời điểm và môi trường.
- [ ] Xác định group ID, topic, partition và owner nghiệp vụ.
- [ ] Kiểm tra metric có cập nhật; ghi lại lag, tuổi bản ghi, producer/consumer rate.
- [ ] Chạy `kafka-consumer-groups --describe` và kiểm tra trạng thái/member.
- [ ] Xác định group không có member, rebalance, lag toàn bộ partition hay chỉ partition cụ thể.
- [ ] Kiểm tra deploy, restart, traffic spike và dependency có thay đổi gần đây.

### Trước khi mitigation

- [ ] Thu thập log/metric liên quan và ghi lại giá trị ban đầu.
- [ ] Xác định nút thắt là consumer, listener, dependency hay broker.
- [ ] Ước lượng tác động nếu tăng consumer/concurrency.
- [ ] Chọn một thay đổi nhỏ, có thể quan sát và có cách hoàn nguyên.
- [ ] Xác định người theo dõi lag, dependency và tác động nghiệp vụ sau thay đổi.

### Trước khi đóng incident

- [ ] Lag giảm trên các partition bị ảnh hưởng.
- [ ] Tuổi bản ghi và SLA nghiệp vụ đã phục hồi.
- [ ] Group ổn định, offset tiến triển, không có lỗi commit bất thường.
- [ ] Retry/DLT và error rate đã được kiểm tra, bản ghi lỗi có owner xử lý.
- [ ] Dependency không bị quá tải do mitigation.
- [ ] Ghi lại nguyên nhân, timeline, mitigation và follow-up.

## 9. Mẫu ghi nhận incident

Sử dụng mẫu dưới đây trong ticket hoặc incident channel:

~~~text
Incident:
Environment:
Service / listener ID:
Consumer group:
Topic:
Affected partitions:
First observed at:
Business impact / SLA:

Initial state:
- Total lag:
- Max partition lag:
- Oldest unprocessed event age:
- Producer rate:
- Consumer rate:
- Active members:
- Group state:
- Retry / DLT rate:

Evidence:
- Relevant dashboard links:
- Log time range / correlation:
- Recent deploy or config change:
- Dependency / broker health:

Root cause:
Mitigation and timestamps:
Observed result after each change:
Recovery confirmed at:
Remaining backlog / follow-up owner:
~~~

## 10. Sau incident

Trong post-incident review, xác định vì sao alert phát hiện đủ sớm hoặc vì sao hệ thống không phát hiện trước khi SLA bị ảnh hưởng. Bổ sung hoặc điều chỉnh:

- Alert theo group/topic/partition, kết hợp lag, độ dốc lag và tuổi bản ghi.
- Dashboard producer rate, consumer rate, thời gian bắt kịp ước lượng và số member.
- Metric listener processing duration, retry, DLT, rebalance và commit.
- Kiểm thử tải để xác định throughput an toàn theo số partition và concurrency.
- Giới hạn concurrency, timeout, retry/backoff và connection pool cho downstream.
- Kiểm thử record lỗi, poison message, broker restart và dependency chậm.
- Quy trình replay/DLT có idempotency, audit và owner rõ ràng.
- Hướng dẫn scale consumer, pause/resume và escalation theo đúng quyền vận hành.

Mỗi follow-up cần có owner, thời hạn và cách xác nhận hoàn thành. Nếu nguyên nhân là lưu lượng tăng trưởng lâu dài, cập nhật capacity plan thay vì chỉ giữ cấu hình scale tạm thời.

## 11. Khi nào cần escalation

Escalate ngay tới Kafka/platform owner khi có broker offline, partition mất leader, ISR bất thường diện rộng, lỗi authentication/ACL không rõ nguyên nhân, quota throttling trên nhiều group hoặc nghi ngờ retention đã loại bỏ dữ liệu chưa xử lý.

Escalate tới owner của ứng dụng khi listener lỗi lặp lại, deserialize/schema incompatibility, commit không tiến triển hoặc cần thay đổi retry/ack semantics.

Escalate tới owner downstream khi database/API/cache là nút thắt hoặc cần thay đổi rate limit, capacity hay dữ liệu.

Escalate tới owner nghiệp vụ khi tuổi bản ghi vượt SLA, cần bỏ qua/replay dữ liệu, có duplicate side effect hoặc cần quyết định thứ tự ưu tiên xử lý backlog.

Khi bàn giao, cung cấp group ID, topic/partition, thời gian bắt đầu, lag và tuổi bản ghi, group state, log/metric có liên quan, các thay đổi đã thực hiện và tác động quan sát được. Không gửi credential hoặc payload nhạy cảm.
