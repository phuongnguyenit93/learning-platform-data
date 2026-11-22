# CommitFailedException và rebalance liên tục

`CommitFailedException` thường xuất hiện khi consumer cố commit offset sau khi đã mất tư cách thành viên hợp lệ trong consumer group. Một nguyên nhân phổ biến là ứng dụng xử lý dữ liệu quá lâu, vượt `max.poll.interval.ms`; trong thời gian đó group đã rebalance và partition có thể được giao cho consumer khác. Khi commit thất bại, offset chưa được xác nhận là đã lưu, vì vậy record đã xử lý có thể được giao lại.

Rebalance là cơ chế bình thường khi consumer tham gia/rời group, partition thay đổi hoặc coordinator cần phân phối lại assignment. Vấn đề cần xử lý là rebalance xảy ra liên tục, làm consumer thường xuyên mất partition, tăng lag và lặp nghiệp vụ. Để chẩn đoán đúng, cần phân biệt thời gian giữa hai lần `poll()`, heartbeat/session timeout, lỗi kết nối coordinator và các lần khởi động lại ứng dụng.

## 1. Hiểu đúng CommitFailedException

Consumer group dùng generation/member identity để xác định thành viên đang sở hữu assignment. Khi rebalance hoàn tất, generation cũ không còn hợp lệ. Nếu consumer gửi commit offset bằng generation đã lỗi thời hoặc không còn sở hữu partition, coordinator từ chối commit và client có thể ném `CommitFailedException`.

Ví dụ một chu kỳ xử lý gây ra lỗi:

1. Consumer A poll một batch và nhận các record thuộc partition `orders-2`.
2. Ứng dụng xử lý batch, gọi database hoặc dịch vụ HTTP và mất nhiều thời gian.
3. Consumer A không gọi `poll()` trong khoảng thời gian vượt `max.poll.interval.ms`.
4. Kafka coi consumer A không còn tiến triển, group bắt đầu rebalance và giao partition cho consumer khác.
5. Consumer A hoàn tất xử lý cũ rồi gọi `commitSync()` hoặc container thực hiện commit.
6. Coordinator từ chối commit vì membership/assignment đã thay đổi.

Side effect nghiệp vụ ở bước 2 có thể đã được ghi bền vững, trong khi offset chưa được commit. Consumer mới vì vậy có thể đọc lại record. Đây là lý do `CommitFailedException` thường đi cùng hiện tượng xử lý lặp.

`CommitFailedException` không đồng nghĩa broker đã mất record, cũng không chứng minh rằng handler chưa chạy. Nó cho biết lần commit đó không được chấp nhận. Hãy kiểm tra riêng hai trạng thái: nghiệp vụ đã hoàn tất đến đâu và offset nào đã được Kafka xác nhận. Thiết kế consumer theo hướng at-least-once và idempotent để replay không tạo tác động trùng.

## 2. Phân biệt các bộ đếm thời gian của consumer

Ba cấu hình thường bị nhầm lẫn là `max.poll.interval.ms`, `session.timeout.ms` và `heartbeat.interval.ms`.

| Cấu hình | Ý nghĩa | Khi vượt/ngừng đáp ứng |
|---|---|---|
| `max.poll.interval.ms` | Thời gian tối đa giữa hai lần gọi `poll()` liên tiếp của ứng dụng | Consumer không chứng minh được tiến triển xử lý; group có thể loại consumer và rebalance |
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat hợp lệ trước khi coi member mất kết nối | Consumer bị coi là không còn sống; partition được phân phối lại |
| `heartbeat.interval.ms` | Chu kỳ client gửi heartbeat khi dùng cơ chế heartbeat phía client | Cần đủ nhỏ so với session timeout để phát hiện mất kết nối kịp thời |

Với consumer group protocol truyền thống, `heartbeat.interval.ms` thường được đặt không lớn hơn khoảng một phần ba `session.timeout.ms`. Giá trị hợp lệ của `session.timeout.ms` còn phụ thuộc cấu hình giới hạn của broker. Khi dùng group protocol mới, một số tham số heartbeat được điều khiển phía broker; hãy kiểm tra đúng protocol và phiên bản Kafka đang chạy.

Kafka client hiện đại có heartbeat thread riêng, vì vậy một handler chậm không nhất thiết làm heartbeat ngừng ngay. Tuy nhiên, heartbeat còn sống không thay thế yêu cầu gọi `poll()` đúng hạn. Ứng dụng có thể vẫn gửi heartbeat nhưng bị loại khỏi group vì vượt `max.poll.interval.ms`.

**Dấu hiệu để phân biệt:**

- Nếu log nhắc đến `max.poll.interval.ms`, `poll timeout`, hoặc thời gian xử lý batch quá dài, hãy đo thời gian giữa hai lần `poll()` trước tiên.
- Nếu log có heartbeat timeout, session expired, connection reset hoặc coordinator unavailable, hãy kiểm tra mạng, JVM pause, broker và heartbeat/session timeout.
- Nếu rebalance xuất hiện trùng với deploy, autoscaling hoặc restart pod, hãy kiểm tra vòng đời instance và cách định danh member.
- Nếu consumer liên tục nhận rồi mất partition dù không có lỗi xử lý rõ ràng, hãy kiểm tra group có bị nhiều tiến trình cùng tham gia/rời hoặc cùng dùng một `group.id` ngoài dự kiến hay không.

## 3. Tìm nguyên nhân rebalance liên tục

### 3.1. Xử lý một poll quá lâu

`max.poll.interval.ms` đo thời gian giữa hai lần gọi `poll()`, không chỉ đo thời gian chạy một hàm handler. Khoảng thời gian thực tế cần tính gồm fetch, xử lý toàn bộ batch, retry/backoff đồng bộ, ghi offset, thời gian chờ lock, GC pause và các khoảng chờ khác trước lần poll kế tiếp.

Với xử lý tuần tự, có thể ước lượng:

\[
T_{cycle} = T_{fetch} + T_{batch} + T_{retry} + T_{commit} + T_{pause} + T_{jitter}
\]

`T_cycle` phải nhỏ hơn `max.poll.interval.ms` với khoảng dự phòng đủ lớn. Không chỉ lấy thời gian trung bình; hãy đo p95/p99 và trường hợp xấu khi database chậm hoặc dịch vụ phụ thuộc bị lỗi. Retry có backoff dài ngay trên poll thread có thể làm tổng thời gian vượt giới hạn dù từng lần xử lý riêng lẻ khá nhanh.

`max.poll.records` giới hạn số record tối đa trả về trong một lần poll. Nếu xử lý từng record mất 1,5 giây và batch có 200 record, riêng phần xử lý tuần tự có thể mất khoảng 300 giây, chưa tính fetch, commit và các lần retry. Với `max.poll.interval.ms` 300 giây, cấu hình này không có khoảng an toàn.

Hướng xử lý:

- Giảm `max.poll.records` để giới hạn lượng công việc của mỗi batch.
- Tối ưu truy vấn database, gọi HTTP, serialization và xử lý CPU nặng.
- Đặt timeout cho dịch vụ phụ thuộc; tránh để một request treo vô hạn.
- Chuyển retry kéo dài sang retry topic hoặc cơ chế xử lý ngoài poll thread khi phù hợp với yêu cầu ordering.
- Chỉ tăng `max.poll.interval.ms` sau khi đã đo thời gian xử lý và xác định batch cần khoảng thời gian lớn hơn.

### 3.2. Mất heartbeat hoặc coordinator

Nếu consumer không gửi heartbeat trong `session.timeout.ms`, coordinator sẽ loại member và khởi động rebalance. Nguyên nhân có thể gồm:

- Mạng giữa consumer và broker chập chờn, DNS lỗi hoặc route/firewall thay đổi.
- Broker đang restart, coordinator chuyển broker hoặc broker chịu tải cao.
- JVM dừng lâu do GC, CPU starvation hoặc máy/container bị throttling.
- `session.timeout.ms` quá thấp so với độ trễ mạng thực tế.
- Client gặp lỗi xác thực, TLS hoặc kết nối tới broker/coordinator.

Hãy đối chiếu timestamp ở log consumer và broker. Nếu nhiều consumer cùng group mất heartbeat cùng thời điểm, khả năng cao là vấn đề hạ tầng hoặc broker. Nếu chỉ một instance bị ảnh hưởng, xem tài nguyên JVM/container, network path và cấu hình riêng của instance đó.

Không tăng `session.timeout.ms` để chữa lỗi `max.poll.interval.ms`: đây là hai cơ chế khác nhau. Tăng session timeout có thể làm phát hiện member chết chậm hơn và kéo dài thời gian group chờ phục hồi.

### 3.3. Thành viên group thay đổi liên tục

Rebalance có thể xảy ra khi instance khởi động lại, scale up/down, health check làm container bị restart, hoặc nhiều tiến trình cùng tham gia group. Cần kiểm tra:

- Các replica có cùng `group.id` đúng chủ đích và cùng subscription không.
- Deployment có rolling restart quá dày hoặc autoscaler dao động quanh ngưỡng không.
- Kubernetes liveness/readiness probe có kill consumer trong lúc đang xử lý batch không.
- Một instance có bị OOMKilled, crash loop hoặc bị scheduler di chuyển liên tục không.
- Một `group.id` có vô tình được dùng chung giữa môi trường dev, staging và production không.
- Ứng dụng có liên tục tạo/hủy listener container hoặc gọi `subscribe()` lặp ngoài dự kiến không.

Thay đổi số partition, subscription hoặc assignor cũng gây rebalance. Một lần rebalance sau thay đổi cấu hình là bình thường; chuỗi rebalance lặp lại cần được giải thích bằng log membership và lịch sử deploy.

### 3.4. Assignment strategy làm tăng tác động

Các assignor eager có thể thu hồi toàn bộ partition trong một đợt rebalance. `CooperativeStickyAssignor` hỗ trợ chuyển partition dần dần, giúp giảm lượng partition bị thu hồi trong các lần rebalance tương thích. Tuy nhiên, cooperative assignor không sửa được consumer xử lý quá lâu, heartbeat timeout hoặc member liên tục restart.

Khi đổi assignor, cần bảo đảm các consumer trong cùng group có cấu hình tương thích và thực hiện chuyển đổi theo hướng dẫn của phiên bản Kafka đang dùng. Đừng coi việc đổi assignor là biện pháp đầu tiên khi chưa xác định nguồn gốc rebalance.

## 4. Thu thập bằng chứng trước khi thay cấu hình

### 4.1. Đọc log consumer và listener

Tìm các cụm từ sau trong log của cùng một `group.id` và đối chiếu theo thời gian:

| Log/dấu hiệu | Ý nghĩa cần kiểm tra |
|---|---|
| `CommitFailedException` | Commit bị từ chối do membership hoặc assignment không còn hợp lệ |
| `max.poll.interval.ms` | Khoảng cách giữa hai lần poll vượt giới hạn |
| `Heartbeat failed`, `session timed out`, `member ... failed` | Heartbeat hoặc kết nối tới coordinator bị gián đoạn |
| `Revoking previously assigned partitions` | Consumer đang nhường partition trong rebalance |
| `Successfully joined group`, `Setting newly assigned partitions` | Consumer đã tham gia lại và nhận assignment |
| `coordinator unavailable` hoặc lỗi kết nối | Kiểm tra broker coordinator, network, DNS, TLS và xác thực |

Trong Spring Kafka, bật log của listener container và consumer ở mức phù hợp trong thời gian điều tra. Ghi nhận `group.id`, client ID, member ID, partition bị revoke/assign, thời gian bắt đầu/kết thúc listener và thời gian xử lý mỗi batch. Không bật TRACE lâu dài trên toàn bộ hệ thống nếu lượng log lớn; giới hạn theo package/client và khoảng thời gian cần thiết.

### 4.2. Kiểm tra trạng thái group bằng CLI

Lệnh cơ bản:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe \
  --group order-service
```

Kết quả cho biết topic, partition, committed offset, log end offset và lag của từng partition. Tùy phiên bản Kafka, có thể xem thêm trạng thái group và danh sách member bằng các tùy chọn `--state`, `--members` hoặc `--members --verbose`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe \
  --group order-service \
  --members --verbose
```

Nếu phiên bản CLI không hỗ trợ tùy chọn trên, dùng `kafka-consumer-groups.sh --help` để kiểm tra cú pháp tương ứng. Khi chạy lệnh trong môi trường bảo mật, cần truyền đúng cấu hình client properties để xác thực với cluster.

Quan sát các điểm sau:

- Group có liên tục chuyển giữa `Stable`, `PreparingRebalance` và `CompletingRebalance` không.
- Member ID hoặc client ID có thay đổi theo chu kỳ không.
- Partition nào có lag tăng nhanh và có thường xuyên đổi owner không.
- Số consumer thực tế có vượt số partition hay không. Consumer dư có thể idle; bản thân điều này không nhất thiết tạo rebalance liên tục.
- Committed offset có đứng yên trong khi log end offset tăng không.

### 4.3. Theo dõi metric

Tên metric có thể khác theo phiên bản Kafka client và hệ thống thu thập. Ưu tiên các nhóm metric tương đương sau:

| Nhóm | Metric nên theo dõi | Dấu hiệu bất thường |
|---|---|---|
| Poll | `time-between-poll-avg`, `time-between-poll-max`, `poll-idle-ratio-avg` | Khoảng cách giữa poll tăng gần giới hạn cấu hình |
| Heartbeat | `heartbeat-rate`, `heartbeat-response-time-max`, `last-heartbeat-seconds-ago` | Heartbeat giảm, độ trễ phản hồi tăng hoặc thời gian từ heartbeat cuối tăng |
| Rebalance | `rebalance-rate-per-hour`, `rebalance-total`, `rebalance-latency-avg/max` | Tần suất hoặc thời gian rebalance tăng đột biến |
| Commit | `commit-rate`, `commit-latency-avg/max` | Commit chậm hoặc giảm trong khi record vẫn được xử lý |
| Throughput/lag | `records-consumed-rate`, `records-lag-max`, bytes/records consumed | Lag tăng kéo dài, throughput thấp hơn tốc độ producer |
| Runtime | JVM GC pause, CPU throttling, heap, thread contention | Pause hoặc thiếu CPU trùng với thời điểm mất membership |

Không phải mọi client đều xuất metric với đúng tên trong bảng. Dùng JMX metric list của Kafka client đang chạy để ánh xạ tên thực tế. Đặt dashboard theo `client.id`, `group.id` và instance để không trộn số liệu của nhiều consumer.

## 5. Khắc phục theo nguyên nhân

### 5.1. Điều chỉnh batch và poll interval

Ví dụ cấu hình Spring Boot để giảm batch và dành đủ thời gian cho poll cycle:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      max-poll-records: 50
      properties:
        max.poll.interval.ms: 300000
```

Đây là cấu hình minh họa, không phải bộ giá trị tối ưu cho mọi ứng dụng. Đo p95/p99 thời gian xử lý batch rồi chọn `max-poll-records` và `max.poll.interval.ms` có khoảng dự phòng. Nếu handler có retry đồng bộ, phải tính cả thời gian backoff. Tăng interval quá lớn có thể khiến group mất nhiều thời gian hơn để phát hiện consumer bị treo ở tầng xử lý.

Khi xử lý từng record mất thời gian không ổn định, cân nhắc batch nhỏ hơn hoặc chuyển tác vụ chậm sang worker có giới hạn. Giữ cho consumer thread tiếp tục gọi `poll()` theo đúng chu kỳ.

### 5.2. Quản lý xử lý bất đồng bộ đúng cách

Đưa công việc sang thread pool có thể giữ poll loop hoạt động, nhưng tạo ra các vấn đề mới. `KafkaConsumer` không thread-safe; không gọi `poll()`, `commitSync()`, `seek()` hoặc thao tác consumer tùy tiện từ worker thread. Một thiết kế bất đồng bộ phải:

1. Giới hạn số tác vụ đang chạy và áp dụng backpressure.
2. Pause partition khi hàng đợi đầy, nhưng tiếp tục poll để duy trì group membership.
3. Theo dõi offset đã xử lý liên tục theo từng partition; chỉ commit offset cao nhất mà tất cả record trước đó đã hoàn tất.
4. Khi partition bị revoke, dừng nhận việc mới và chờ/huỷ tác vụ đang chạy theo chính sách rõ ràng.
5. Khi partition bị lost, không cố commit offset của partition đã mất quyền sở hữu.
6. Dùng idempotency key vì tác vụ đang chạy có thể hoàn tất sau rebalance và bị thực hiện lại ở consumer khác.

Nếu yêu cầu ordering theo partition, không cho phép worker xử lý record cùng partition hoàn tất tùy ý rồi commit offset lớn hơn record còn đang chạy. Một offset đã commit sẽ bỏ qua mọi record thấp hơn offset đó trong lần đọc tiếp theo.

Trong Spring Kafka, ưu tiên listener container và cơ chế pause/resume, acknowledgement, concurrency đã được framework hỗ trợ. Nếu dùng async listener hoặc trả về `CompletableFuture`/kiểu bất đồng bộ, kiểm tra tài liệu của đúng phiên bản Spring Kafka để hiểu thời điểm acknowledgement và commit được thực hiện. Không tự tạo thread rồi commit consumer từ thread đó.

### 5.3. Xử lý rebalance và commit an toàn trong Java

Với KafkaConsumer thuần, `ConsumerRebalanceListener` cung cấp callback khi partition bị revoke, assign hoặc lost. Có thể commit offset của những record đã xử lý hoàn tất khi đang revoke quyền sở hữu:

```java
ConsumerRebalanceListener listener = new ConsumerRebalanceListener() {
    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        Map<TopicPartition, OffsetAndMetadata> completed =
            offsetsCompletedFor(partitions);
        if (!completed.isEmpty()) {
            consumer.commitSync(completed);
        }
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
        initializePartitionState(partitions);
    }

    @Override
    public void onPartitionsLost(Collection<TopicPartition> partitions) {
        discardLocalState(partitions);
    }
};
```

Đây là khung minh họa; `offsetsCompletedFor`, `initializePartitionState` và `discardLocalState` là logic ứng dụng. Chỉ commit offset của record đã hoàn tất, và giá trị commit là offset kế tiếp cần đọc. Callback `onPartitionsLost` báo rằng partition đã mất; không cố commit trong callback này. Với cooperative rebalance, chỉ xử lý các partition được revoke trong callback, không giả định toàn bộ assignment bị thu hồi.

Nếu commit trong callback revoke thất bại, ghi nhận lỗi và bảo đảm nghiệp vụ chịu được replay. Không giữ thread trong callback quá lâu; rebalance cần hoàn tất để các member khác tiếp tục. Với Spring Kafka, thường nên để container quản lý rebalance callback và offset commit thay vì tự cài đặt `ConsumerRebalanceListener` lên consumer do container sở hữu.

### 5.4. Ổn định member identity khi restart

Với ứng dụng có instance identity ổn định, static membership qua `group.instance.id` có thể giảm rebalance khi một instance restart ngắn hạn. Ví dụ cấu hình cho một consumer instance:

```yaml
spring:
  kafka:
    consumer:
      properties:
        group.instance.id: order-service-pod-0
```

Mỗi consumer instance trong cùng group phải có `group.instance.id` duy nhất và ổn định qua lần restart tương ứng. Không dùng cùng một giá trị cho nhiều replica đồng thời; member trùng ID có thể bị fencing và gây lỗi membership. Static membership cũng có thể làm group chờ lâu hơn trước khi thay thế member mất tích, tùy timeout và phiên bản. Đây là cách giảm churn do restart ngắn, không thay thế việc sửa poll chậm hoặc mất kết nối.

### 5.5. Chọn assignor phù hợp

Nếu rebalance xảy ra vì scale hoặc thay đổi membership thường xuyên, cân nhắc cooperative sticky assignment để giảm lượng partition phải thu hồi trong mỗi đợt. Trước khi đổi:

- Xác nhận phiên bản Kafka client và assignor hỗ trợ cooperative protocol.
- Bảo đảm các member trong group có cấu hình tương thích trong giai đoạn chuyển đổi.
- Đánh giá ordering và thời gian chuyển partition trong ứng dụng.
- Đo lại rebalance duration và số partition bị revoke sau thay đổi.

Assignor chỉ ảnh hưởng cách phân phối partition. Nó không giải quyết nguyên nhân member bị loại vì `max.poll.interval.ms`, session timeout hoặc crash loop.

## 6. Xử lý CommitFailedException mà không làm sai dữ liệu

Khi commit thất bại, đừng mặc định gọi lại handler hoặc commit lại cùng một offset bằng mọi giá. Trước tiên cần xác định consumer còn sở hữu partition không và generation hiện tại có hợp lệ không. Nếu rebalance đã đổi assignment, lần commit cũ không thể được coi là thành công chỉ vì ứng dụng đã gửi request.

Nguyên tắc xử lý:

- Ghi log `group.id`, client ID, topic/partition, offset, exception và thời gian xử lý record.
- Coi offset chưa được xác nhận là chưa commit; record có thể replay.
- Cho consumer tiếp tục chu kỳ poll/join group theo lifecycle của client hoặc listener container.
- Đảm bảo handler idempotent bằng event ID, unique constraint, inbox hoặc idempotency key ở dịch vụ đích.
- Chỉ commit offset sau khi side effect cần bảo vệ đã hoàn tất bền vững.
- Không commit offset cao hơn một record chưa xử lý xong trong cùng partition.
- Không nuốt lỗi commit rồi phát metric thành công giả.

Với Spring Kafka, container quản lý consumer và commit theo `AckMode`. Mặc định của nhiều cấu hình container là commit theo batch; cấu hình thực tế có thể khác. Kiểm tra `spring.kafka.listener.ack-mode`, `enable.auto.commit` và cách listener acknowledge. Không bật Kafka client auto commit đồng thời với cơ chế commit do container quản lý trừ khi đã hiểu rõ tương tác của chúng.

Ví dụ listener xử lý đồng bộ với acknowledgement thủ công:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderCreated event, Acknowledgment acknowledgment) {
    orderHandler.applyIdempotently(event); // Hoàn tất transaction nghiệp vụ trước.
    acknowledgment.acknowledge();         // Báo container record đã xử lý.
}
```

Listener này cần cấu hình `AckMode.MANUAL` hoặc `AckMode.MANUAL_IMMEDIATE` phù hợp với ứng dụng. `acknowledge()` báo container về trạng thái xử lý; nó không bảo đảm listener luôn nhận trực tiếp exception từ broker nếu commit sau đó thất bại. Hãy quan sát log/container event và metric commit để phát hiện lỗi thực tế.

## 7. Runbook điều tra theo thứ tự

Khi hệ thống bắt đầu rebalance liên tục, thực hiện theo thứ tự sau để tránh thay nhiều tham số cùng lúc:

1. **Khoanh vùng group:** xác định `group.id`, các instance, client ID, topic và partition bị ảnh hưởng.
2. **Đối chiếu thời gian:** ghép log rebalance với deploy, autoscaling, restart, lỗi broker và thời điểm lag tăng.
3. **Đo poll cycle:** ghi nhận thời gian giữa hai lần poll và thời gian xử lý p95/p99 của batch.
4. **Kiểm tra membership:** xem member ID, generation, partition revoke/assign và trạng thái group qua CLI.
5. **Kiểm tra heartbeat:** đối chiếu heartbeat/session timeout với network, broker coordinator và JVM pause.
6. **Xác nhận commit semantics:** kiểm tra auto commit, ack mode, offset được commit và record đã tạo side effect hay chưa.
7. **Thay một yếu tố:** giảm batch, tối ưu handler, điều chỉnh timeout hoặc sửa deployment theo nguyên nhân đã có bằng chứng.
8. **Theo dõi sau thay đổi:** xác nhận rebalance rate giảm, lag ổn định, commit thành công và không tăng tác động nghiệp vụ trùng.

Không tăng đồng thời `max.poll.interval.ms`, `session.timeout.ms`, `heartbeat.interval.ms` và `max.poll.records` khi chưa biết nguyên nhân. Khi nhiều biến đổi được áp dụng cùng lúc, rất khó xác định thay đổi nào thực sự giải quyết vấn đề và thay đổi nào chỉ trì hoãn việc phát hiện lỗi.

## 8. Ma trận triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có khả năng | Hành động ưu tiên |
|---|---|---|
| `CommitFailedException` sau một batch dài | Vượt `max.poll.interval.ms` | Đo poll cycle, giảm batch, tối ưu handler, cân nhắc tăng interval có căn cứ |
| Nhiều consumer cùng timeout heartbeat | Broker/coordinator hoặc network chung | Kiểm tra broker log, network, DNS, TLS và session timeout |
| Một pod liên tục rời rồi vào group | GC, CPU throttling, OOM, crash/restart | Kiểm tra JVM, container events, probe và tài nguyên |
| Rebalance trùng rolling deployment | Member identity thay đổi khi restart | Điều chỉnh rollout; cân nhắc static membership với ID duy nhất |
| Rebalance hoàn tất nhưng partition di chuyển nhiều | Eager assignor hoặc membership churn | Đánh giá cooperative sticky và ổn định số member |
| Commit thất bại nhưng database đã cập nhật | Offset chưa commit sau side effect | Bổ sung inbox/idempotency; chấp nhận replay an toàn |
| Lag tăng nhưng group stable | Throughput xử lý thấp hơn tốc độ producer | Tối ưu xử lý, kiểm tra partition/concurrency và downstream capacity |

## 9. Tiêu chí xác nhận đã khắc phục

- [ ] Thời gian giữa hai lần `poll()` luôn thấp hơn `max.poll.interval.ms` với khoảng dự phòng đã đo.
- [ ] Không còn chuỗi heartbeat/session timeout không giải thích được.
- [ ] Group giữ trạng thái ổn định; rebalance chỉ xuất hiện khi có thay đổi membership hoặc subscription dự kiến.
- [ ] Consumer không commit offset cho record chưa hoàn tất.
- [ ] Record bị replay sau commit failure không tạo tác động nghiệp vụ trùng.
- [ ] Lag và throughput trở lại mức phù hợp với tải producer.
- [ ] Log và metric cho phép xác định member, partition, thời gian poll, commit và rebalance.

`CommitFailedException` là tín hiệu cần kiểm tra membership và thời điểm commit. Khi poll loop, heartbeat, assignment và xử lý nghiệp vụ được theo dõi riêng, có thể xác định đúng nguyên nhân rebalance và phục hồi consumer group mà vẫn bảo toàn khả năng replay an toàn của Kafka.
