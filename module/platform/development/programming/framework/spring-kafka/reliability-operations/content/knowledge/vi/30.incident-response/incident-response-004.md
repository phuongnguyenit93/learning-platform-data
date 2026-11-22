# Runbook khi rebalance liên tục

## Mục đích và phạm vi

Runbook này hướng dẫn xử lý một consumer group của Apache Kafka liên tục thay đổi thành viên hoặc phân công partition khi ứng dụng sử dụng Spring for Apache Kafka. Mục tiêu là khôi phục membership ổn định, giảm gián đoạn xử lý và giữ nguyên tính đúng đắn của offset.

Một lần rebalance đơn lẻ có thể là hành vi bình thường khi triển khai phiên bản mới, thêm consumer, thay đổi số partition hoặc khi một consumer rời nhóm. Sự cố cần xử lý khi rebalance lặp lại trong thời gian ngắn, khiến partition liên tục bị thu hồi và cấp lại, listener không có đủ thời gian xử lý, consumer group không ổn định hoặc consumer lag tăng.

Runbook tập trung vào consumer group và listener container của Spring Kafka. Tên log, metric và khả năng cấu hình có thể khác nhau theo phiên bản Kafka client, broker, Spring Kafka và group protocol đang sử dụng. Trước khi áp dụng cấu hình, xác nhận phiên bản và protocol thực tế của cluster.

## Dấu hiệu nhận biết và ảnh hưởng

Các dấu hiệu thường gặp:

- Log consumer lặp lại các thông báo tham gia nhóm, bắt đầu/kết thúc rebalance, thu hồi partition hoặc nhận assignment mới.
- Callback `onPartitionsRevoked`, `onPartitionsAssigned` hoặc `onPartitionsLost` được gọi thường xuyên.
- Số lần rebalance tăng liên tục trong khi số consumer và cấu hình subscription không có thay đổi dự kiến.
- Consumer group chuyển qua lại giữa các trạng thái `PreparingRebalance`, `CompletingRebalance` và `Stable`, hoặc liên tục thay đổi generation.
- Consumer lag tăng, throughput giảm, thời gian xử lý bị ngắt quãng hoặc độ trễ đầu cuối tăng.
- Ứng dụng ghi nhận lỗi commit như `CommitFailedException`, lỗi xử lý do partition đã bị thu hồi, hoặc bản ghi được giao lại sau khi rebalance.

Rebalance có thể làm tạm dừng việc tiêu thụ trong lúc coordinator phân công partition. Bản ghi chưa được commit có thể được giao lại, vì vậy handler vẫn phải an toàn khi xử lý trùng. Rebalance không tự động chứng minh rằng broker bị lỗi; nguyên nhân có thể nằm ở listener xử lý quá lâu, pod khởi động lại, autoscaling dao động, mạng hoặc cấu hình consumer.

## Nguyên tắc xử lý

1. Xác định đúng cluster, consumer group và khoảng thời gian xảy ra sự cố trước khi thay đổi cấu hình.
2. Thu thập trạng thái group, log và metric trước khi restart hoặc scale consumer. Giữ lại timestamp và client ID để đối chiếu giữa ứng dụng với broker.
3. Tìm nguyên nhân làm consumer rời nhóm hoặc khiến coordinator phải tính lại assignment. Không xem việc tăng timeout là cách sửa mặc định.
4. Chỉ thay đổi một nhóm tham số trong mỗi lần can thiệp, ghi lại giá trị cũ và theo dõi kết quả.
5. Không xóa consumer group, reset offset hoặc thay đổi số partition như một biện pháp chữa cháy khi chưa có kế hoạch riêng và phê duyệt vận hành.

## Quy trình xử lý sự cố

### 1. Xác nhận phạm vi và mức độ ảnh hưởng

Ghi lại các thông tin sau:

| Thông tin | Cần xác định |
|---|---|
| Môi trường và cluster | Production/staging, bootstrap servers và khu vực triển khai |
| Consumer group | `group.id` chính xác, các topic được subscribe |
| Ứng dụng | Tên service, phiên bản release, Spring Kafka và Kafka client version |
| Thời điểm | Thời điểm bắt đầu, tần suất rebalance, thay đổi gần nhất trước sự cố |
| Phạm vi | Một group, nhiều group trên cùng cluster hay nhiều cluster |
| Ảnh hưởng | Lag, throughput, lỗi xử lý, độ trễ và các luồng nghiệp vụ bị ảnh hưởng |

Đối chiếu thời điểm bắt đầu với deployment, pod restart, thay đổi replica/concurrency, autoscaling, thay đổi topic/partition, broker restart hoặc sự cố mạng. Nếu nhiều group độc lập cùng bị ảnh hưởng tại một thời điểm, ưu tiên kiểm tra broker, coordinator và hạ tầng mạng trước khi sửa riêng từng listener.

### 2. Chụp trạng thái consumer group

Chạy lệnh từ máy có Kafka CLI và quyền truy cập cluster. Thay biến môi trường bằng thông tin của môi trường đang điều tra:

```bash
export BOOTSTRAP_SERVERS="broker-1:9092,broker-2:9092"
export GROUP_ID="orders-consumer-v1"

kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --members \
  --verbose
```

Tùy phiên bản Kafka, các tùy chọn `--state`, `--members` và `--verbose` có thể khác nhau. Nếu CLI hiện tại không hỗ trợ, dùng lệnh `--describe --group` cơ bản và lấy thông tin member từ công cụ quản trị hoặc log broker.

Ghi lại:

- Group đang `Stable` hay đang trong quá trình rebalance.
- Số member, consumer ID, client ID, host và partition được gán cho từng member.
- Member có biến mất rồi xuất hiện lại hay không; có nhiều client ID mới liên tiếp hay không.
- Partition nào không có consumer nhận, hoặc assignment thay đổi giữa các lần kiểm tra.
- Lag theo từng partition và tốc độ tăng/giảm lag.

Chụp trạng thái nhiều lần, cách nhau một khoảng ngắn phù hợp với tần suất sự cố. Một ảnh chụp đơn lẻ có thể bắt đúng lúc group đang rebalance và không thể hiện được member nào đang rời nhóm.

### 3. Đối chiếu log và metric của ứng dụng

Tìm log theo `group.id`, `client.id`, pod/host và timestamp. Các logger hữu ích thường gồm:

- `org.apache.kafka.clients.consumer.internals.ConsumerCoordinator`
- `org.apache.kafka.clients.consumer.internals.AbstractCoordinator`
- `org.springframework.kafka.listener.KafkaMessageListenerContainer`
- Logger của listener và các dependency mà listener gọi tới.

Tìm những thông điệp cho biết consumer rời nhóm, mất kết nối coordinator, vượt `max.poll.interval.ms`, heartbeat thất bại, partition bị thu hồi/cấp lại hoặc container dừng và khởi động. Nội dung chính xác phụ thuộc phiên bản Kafka client.

Nếu ứng dụng xuất Kafka client metrics qua JMX hoặc Micrometer, đối chiếu các metric tương ứng có sẵn trong phiên bản đang chạy:

| Nhóm metric | Cách sử dụng |
|---|---|
| `rebalance-total`, `rebalance-rate-per-hour` | Xác nhận số lần và tốc độ rebalance |
| `assigned-partitions` | Theo dõi số partition đang được giao cho consumer |
| `heartbeat-rate`, `heartbeat-response-time-max` | Phát hiện heartbeat chậm hoặc phản hồi bất thường |
| `poll-idle-ratio-avg`, `time-between-poll-max` (nếu có) | Tìm consumer dành quá nhiều thời gian ngoài vòng poll |
| `records-lag-max` và lag theo partition | Đánh giá ảnh hưởng tới khả năng bắt kịp dữ liệu |

Tên metric và cách export thay đổi theo Kafka client và hệ thống quan sát. Không kết luận metric không tồn tại chỉ vì dashboard hiện tại chưa thu thập nó. Đồng thời kiểm tra JVM pause/GC, CPU throttling, memory pressure, thread pool, connection pool và thời gian phản hồi của database hoặc API mà listener gọi.

### 4. Xác định nguyên nhân theo tín hiệu

#### A. Listener xử lý lâu hơn `max.poll.interval.ms`

Đây là nguyên nhân phổ biến khi listener xử lý đồng bộ. Consumer cần gọi `poll()` đủ thường xuyên. Trong Spring Kafka, thời gian listener xử lý bản ghi hoặc cả batch thường nằm trên đường thực thi của container; nếu xử lý kéo dài quá giới hạn giữa hai lần poll, Kafka client có thể chủ động rời group và rebalance.

Kiểm tra:

- Thời gian xử lý p95/p99 và thời gian tối đa của một record hoặc một batch.
- Batch listener có xử lý tuần tự nhiều record hoặc chờ một dependency chậm không.
- Listener có gọi API bên ngoài, truy vấn database, chờ lock hoặc retry đồng bộ không.
- Error handler/backoff có giữ luồng listener ở trạng thái chờ lâu không.
- Có log cho biết consumer đã vượt `max.poll.interval.ms` hoặc không poll đúng hạn không.

Hướng xử lý:

1. Đo thời gian thực tế ở từng bước của listener để tìm dependency chậm.
2. Giảm `max.poll.records` để giới hạn lượng công việc trong một lần poll nếu batch hiện tại quá lớn.
3. Tối ưu truy vấn, dùng bulk operation phù hợp, đặt timeout cho lời gọi bên ngoài và giới hạn thời gian xử lý mỗi batch.
4. Chỉ tăng `max.poll.interval.ms` khi thời gian xử lý dài là yêu cầu có chủ đích và đã được đo. Chọn giá trị có khoảng đệm dựa trên thời gian xử lý xấu nhất có thể chấp nhận; đồng thời kiểm tra timeout của nghiệp vụ và transaction.

Tăng `max.poll.interval.ms` có thể ngăn consumer bị loại khỏi group trong lúc xử lý lâu, nhưng làm chậm thời điểm phát hiện consumer bị treo. Nó không khắc phục CPU quá tải, dependency mất kết nối hoặc listener bị block vô hạn.

#### B. Heartbeat, session timeout, mạng hoặc JVM không ổn định

Consumer có thể bị coordinator xem là không còn hoạt động khi heartbeat không đến đúng hạn. Nguyên nhân có thể là network interruption, DNS/TLS, broker/coordinator quá tải, JVM stop-the-world pause, CPU bị throttling hoặc tiến trình bị treo.

Kiểm tra:

- Log heartbeat timeout, coordinator unavailable, disconnect/reconnect và request timeout.
- Metric heartbeat, độ trễ phản hồi và thời điểm member mất kết nối.
- JVM GC pause, CPU throttling, node pressure, packet loss, DNS và kết nối tới broker.
- Broker log về coordinator, request queue, network thread và lần restart/failover.

Với classic group protocol, kiểm tra `session.timeout.ms` và `heartbeat.interval.ms` cùng giới hạn broker cho phép. Không tăng riêng session timeout theo cảm tính: giá trị lớn hơn có thể làm phát hiện consumer chết chậm hơn, còn giá trị quá thấp khiến group nhạy với jitter. Chỉ điều chỉnh sau khi đã loại trừ vấn đề mạng, JVM và broker. Với consumer group protocol mới (`group.protocol=consumer`), một số tham số heartbeat/session được quản lý ở broker và cách cấu hình khác classic protocol; dùng tài liệu đúng phiên bản Kafka đang chạy.

#### C. Member liên tục được thêm, xóa hoặc khởi động lại

Các lần deployment, pod crash, liveness probe quá gắt, autoscaling dao động hoặc thay đổi `concurrency` đều có thể làm thay đổi membership. Khi đó rebalance là phản ứng của group với việc thành viên thay đổi.

Kiểm tra:

- Lịch sử rollout, pod restart count, OOMKilled, liveness/readiness probe và node eviction.
- Số replica và `spring.kafka.listener.concurrency` trước/sau thời điểm sự cố.
- Autoscaler có tăng/giảm replica liên tục quanh một ngưỡng lag hoặc CPU không.
- Tổng số consumer thực tế, xấp xỉ `số replica × listener concurrency` cho mỗi listener container tương ứng.
- `group.instance.id` có bị trùng giữa các member không nếu đang dùng static membership.

Hướng xử lý:

- Ổn định replica và concurrency trong lúc điều tra; điều chỉnh autoscaling với cooldown/stabilization phù hợp để tránh scale lên xuống liên tục.
- Sửa nguyên nhân pod restart, probe timeout, OOM hoặc rollout quá dồn dập.
- Triển khai rolling update có kiểm soát và cho container dừng graceful để consumer rời group đúng quy trình.
- Nếu dùng static membership, cấp `group.instance.id` duy nhất và ổn định cho từng member. Tránh tái sử dụng cùng ID cho hai pod đang chạy đồng thời. Xác nhận cách Spring Kafka tạo ID cho các child container khi `concurrency > 1` và phiên bản thư viện đang dùng.

Static membership có thể giảm rebalance do restart ngắn hạn, nhưng member cũ có thể giữ vị trí cho tới khi hết session timeout nếu không quay lại. Không bật static membership khi hệ thống không thể đảm bảo ID duy nhất và vòng đời member ổn định.

#### D. Thay đổi subscription, partition hoặc assignment strategy

Group có thể rebalance khi topic được thêm/xóa, pattern subscription phát hiện topic mới, partition count thay đổi hoặc các member có subscription/assignment strategy không tương thích.

Kiểm tra:

- Danh sách topic mà từng ứng dụng subscribe; chú ý `topic pattern` và thay đổi metadata.
- Thay đổi partition count, topic được tạo mới hoặc thay đổi quyền truy cập.
- `partition.assignment.strategy` trên tất cả member của group và phiên bản client.
- Cấu hình listener/container được tạo từ Spring Boot hay từ `ConsumerFactory`/`ConcurrentKafkaListenerContainerFactory` tùy chỉnh.

Với classic group protocol, `CooperativeStickyAssignor` có thể giảm lượng partition phải thu hồi khi membership thay đổi. Chỉ chuyển assignment strategy sau khi xác nhận mọi member trong group hỗ trợ và thực hiện migration theo hướng dẫn của phiên bản Kafka client. Cooperative assignment giảm mức độ gián đoạn khi cần rebalance; nó không sửa được member liên tục rời nhóm. Với `group.protocol=consumer`, cơ chế assignor và cấu hình liên quan khác classic protocol.

#### E. Broker hoặc group coordinator gặp sự cố

Nếu nhiều consumer group trên cùng cluster cùng bất ổn, hoặc log ứng dụng cho thấy coordinator liên tục unavailable, kiểm tra broker và hạ tầng trước khi chỉnh listener.

Kiểm tra broker restart/failover, controller/coordinator log, request queue, network processor, disk/IO, network latency và lỗi kết nối giữa client với broker. Đối chiếu sự cố theo broker đang giữ vai trò coordinator của từng group. Nếu cần chuyển cấp, cung cấp timestamp, group ID, broker/coordinator liên quan, client ID, log hai phía và metric trước/sau sự cố.

### 5. Áp dụng biện pháp khắc phục có kiểm soát

Chọn biện pháp theo nguyên nhân đã có bằng chứng. Ví dụ cấu hình Spring Boot dưới đây minh họa cách giới hạn batch và cấu hình một số consumer properties; giá trị là điểm khởi đầu cần điều chỉnh theo tải thực tế, không phải cấu hình mặc định cho mọi hệ thống:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-consumer-v1
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 600000
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
    listener:
      concurrency: 3
```

Lưu ý khi áp dụng:

- Ví dụ chỉ phù hợp khi listener có thời gian xử lý dài đã được đo và mọi member của group tương thích với assignment strategy được chọn. Không tăng `max.poll.interval.ms` chỉ để che giấu listener bị treo.
- `max.poll.records` giới hạn số record trả về trong một lần poll; giảm giá trị có thể giảm thời gian xử lý mỗi batch nhưng cũng có thể giảm throughput nếu batch quá nhỏ.
- Tổng consumer của cùng group phụ thuộc số replica và concurrency. Khi số consumer vượt số partition, một số consumer sẽ không được gán partition; điều này không nhất thiết gây rebalance liên tục nhưng có thể làm tăng chi phí và độ phức tạp vận hành.
- Nếu khai báo `ConsumerFactory` hoặc listener container factory riêng, xác nhận cấu hình cuối cùng được truyền vào Kafka client/container. Cấu hình riêng có thể ghi đè cấu hình Spring Boot.
- `group.instance.id` phải duy nhất cho từng member. Không dùng một literal giống nhau cho mọi replica.
- Thay đổi `partition.assignment.strategy` hoặc group protocol cần kế hoạch rollout tương thích cho toàn bộ member của group.

Nếu sự cố đến từ retry/backoff đồng bộ, xem xét cách xử lý lỗi phù hợp với phiên bản Spring Kafka. Với backoff dài, `ContainerPausingBackOffHandler` (có từ các phiên bản Spring Kafka hỗ trợ cơ chế này) hoặc retry topic có thể phù hợp hơn việc giữ listener thread chờ quá lâu. Kiểm tra semantics offset, thứ tự xử lý và khả năng giao lại trước khi chuyển retry strategy.

Không chuyển công việc sang thread tùy ý rồi trả khỏi listener nếu chưa thiết kế rõ việc commit/acknowledge, xử lý lỗi và quyền sở hữu partition. Khi listener trả về trước khi công việc hoàn tất, offset có thể được commit trong khi nghiệp vụ chưa hoàn thành, hoặc kết quả có thể đến sai thứ tự. Nếu cần xử lý bất đồng bộ, thiết kế acknowledgement và giới hạn số công việc đang chạy theo đúng khả năng của Spring Kafka version.

## Xác nhận sau khi khắc phục

Theo dõi ít nhất qua một khoảng thời gian dài hơn chu kỳ rebalance trước đó và đủ để bao phủ tải đại diện. Xác nhận các điểm sau:

- Consumer group giữ trạng thái `Stable`; số member và assignment không dao động ngoài thay đổi dự kiến.
- `rebalance-total` không tiếp tục tăng bất thường; callback revoke/assign không còn lặp dày đặc.
- Không còn log vượt `max.poll.interval.ms`, heartbeat timeout hoặc disconnect/reconnect bất thường.
- Consumer lag giảm hoặc ổn định ở mức chấp nhận được; throughput và độ trễ trở lại mục tiêu.
- Thời gian xử lý p95/p99 nằm trong giới hạn đã chọn cho poll interval và timeout nghiệp vụ.
- Không xuất hiện lỗi commit, mất bản ghi hoặc lỗi nghiệp vụ do xử lý trùng. Đối chiếu offset và kết quả nghiệp vụ theo cơ chế idempotency hiện có.
- Các consumer mới tham gia group nhận partition đúng dự kiến sau rollout/scale.

Ghi lại thay đổi cấu hình, thời điểm áp dụng, người thực hiện, metric trước/sau và kết quả theo dõi. Nếu rebalance quay lại, khôi phục cấu hình trước đó khi thay đổi mới làm tình hình xấu hơn, sau đó tiếp tục điều tra theo tín hiệu mới.

## Khi nào cần chuyển cấp

Chuyển cấp cho đội Kafka/platform khi có một trong các tình huống sau:

- Nhiều consumer group cùng cluster rebalance đồng thời mà không có thay đổi tương ứng ở ứng dụng.
- Coordinator/broker liên tục mất kết nối, restart hoặc có lỗi request/network kéo dài.
- Group không thể ổn định dù member và listener đã hoạt động bình thường, cấu hình nhất quán.
- Cần thay đổi broker-level setting, group protocol, partition topology hoặc thực hiện thao tác có thể ảnh hưởng nhiều consumer group.

Khi chuyển cấp, đính kèm cluster/environment, group ID, topic, timestamp và timezone, Kafka broker/client version, Spring Kafka version, group protocol, số member, trạng thái group, lag, log consumer/coordinator, metric rebalance/heartbeat/poll và các thay đổi triển khai gần nhất. Nêu rõ biện pháp đã thử cùng kết quả để tránh lặp lại thao tác.

## Checklist thao tác nhanh

- [ ] Xác nhận group ID, cluster, thời điểm bắt đầu và mức độ ảnh hưởng.
- [ ] Chụp trạng thái group, member, assignment và lag nhiều lần.
- [ ] Đối chiếu log consumer/container/coordinator cùng metric poll, heartbeat và rebalance.
- [ ] Kiểm tra thời gian xử lý listener, batch size, retry/backoff và dependency chậm.
- [ ] Kiểm tra pod restart, deployment, replica, concurrency, autoscaling và static member ID.
- [ ] Kiểm tra subscription, topic/partition changes, assignment strategy và group protocol.
- [ ] Nếu nhiều group cùng bị ảnh hưởng, kiểm tra broker/coordinator và mạng.
- [ ] Áp dụng một thay đổi có căn cứ, ghi lại giá trị cũ và theo dõi kết quả.
- [ ] Xác nhận group ổn định, lag phục hồi và không phát sinh lỗi commit hoặc lỗi nghiệp vụ.
