# Quy trình thu thập chứng cứ, khoanh vùng và xác nhận phục hồi

Khi Kafka gặp sự cố, thao tác đầu tiên không nên là restart broker, reset offset hay thay hàng loạt cấu hình. Hãy xác định tác động, thu thập bằng chứng có timestamp, hình thành giả thuyết, kiểm tra từng giả thuyết bằng dữ liệu và chỉ áp dụng thay đổi có phạm vi rõ ràng. Sau thay đổi, cần chứng minh hệ thống đã phục hồi bằng metric và kiểm tra dữ liệu end-to-end.

Quy trình này áp dụng cho broker, controller/KRaft, topic/partition, producer, consumer group, Kafka Connect, Kafka Streams và các thành phần phụ trợ như Schema Registry, DNS, TLS, database. Mục tiêu là giúp đội vận hành trả lời được bốn câu hỏi: chuyện gì đang xảy ra, ảnh hưởng đến đâu, bằng chứng nào xác định nguyên nhân và dữ liệu nào chứng minh dịch vụ đã phục hồi.

## 1. Nguyên tắc xử lý sự cố

Một incident Kafka thường liên quan nhiều thành phần và có thể lan truyền rất nhanh. Producer retry làm tăng tải; consumer chậm làm lag tăng; downstream timeout làm consumer giữ partition lâu; broker restart gây leader election và rebalance; thay đổi cấu hình thiếu kiểm soát có thể khiến sự cố rộng hơn.

Giữ các nguyên tắc sau:

1. **Bảo vệ dữ liệu trước**: không xóa topic, reset offset, xóa log directory hoặc thay replication policy khi chưa hiểu hệ quả.
2. **Ghi nhận trước khi thay đổi**: lưu timestamp, metric, log, config hiện tại và trạng thái cluster.
3. **Phân biệt triệu chứng và nguyên nhân**: lag tăng là triệu chứng; hot key, database chậm hoặc consumer restart mới có thể là nguyên nhân.
4. **Một thay đổi có thể kiểm chứng**: thay từng nhóm nhỏ, ghi lại giá trị trước/sau và điều kiện rollback.
5. **Giảm tác động trước, sửa gốc sau**: nếu downstream đang sụp, có thể cần giảm tải để ổn định rồi mới phân tích sâu.
6. **Xác nhận bằng dữ liệu**: broker online hoặc consumer process RUNNING chưa đủ chứng minh pipeline đã phục hồi.
7. **Giữ audit trail**: mọi lệnh thay đổi cần có người thực hiện, thời gian, lý do và kết quả.

Không có một checklist cố định thay thế judgment của incident commander. Ưu tiên bảo toàn dữ liệu, giảm blast radius và duy trì khả năng quan sát.

## 2. Vòng đời điều tra sự cố

~~~mermaid
flowchart TD
    A["Alert / phát hiện sự cố"] --> B["Xác nhận impact và severity"]
    B --> C["Thu thập snapshot ban đầu"]
    C --> D["Xây dựng timeline và giả thuyết"]
    D --> E["Kiểm tra bằng metric, log, config"]
    E --> F{"Đủ bằng chứng?"}
    F -- "Chưa" --> D
    F -- "Đủ" --> G["Chọn mitigation có kiểm soát"]
    G --> H["Theo dõi và xác minh phục hồi"]
    H --> I{"SLO và data integrity đạt?"}
    I -- "Chưa" --> D
    I -- "Đạt" --> J["Đóng incident, lưu evidence"]
    J --> K["RCA và action items"]
~~~

### Các giai đoạn

| Giai đoạn | Mục tiêu | Đầu ra |
|---|---|---|
| Detect | Nhận biết alert hoặc báo cáo lỗi | Incident ID, thời điểm bắt đầu |
| Triage | Xác định phạm vi và mức độ ảnh hưởng | Severity, service/topic/group bị ảnh hưởng |
| Preserve | Lưu snapshot trước thay đổi | Metric, log, config, CLI output |
| Diagnose | Khoanh vùng bằng giả thuyết | Root cause hoặc danh sách nguyên nhân đã loại trừ |
| Mitigate | Giảm tác động có kiểm soát | Change record, rollback plan |
| Recover | Khôi phục pipeline | Health và business checks PASS |
| Close | Ghi nhận bài học | RCA, action owner, deadline |

## 3. Xác nhận impact và severity

Đừng bắt đầu bằng việc đọc hàng nghìn dòng log. Trước tiên xác định người dùng hoặc business flow nào bị ảnh hưởng.

Ghi lại:

- Cluster, environment, region/AZ và thời điểm phát hiện.
- Topic, partition, producer application, consumer group hoặc connector liên quan.
- Triệu chứng: produce failure, consume delay, timeout, under-replicated partition, unavailable partition, rebalance, authentication failure hay dữ liệu sai.
- Số producer/consumer/pipeline bị ảnh hưởng.
- Tác động business: event bị trễ, request lỗi, dữ liệu có nguy cơ mất/duplicate hay downstream ngừng cập nhật.
- Mức độ ảnh hưởng theo SLO/RTO/RPO và thời gian kéo dài.

Ví dụ phân loại nội bộ:

| Mức | Tình huống tham khảo | Phản ứng |
|---|---|---|
| SEV-1 | Mất khả năng ghi/đọc diện rộng, dữ liệu có nguy cơ mất, nhiều luồng business dừng | Incident commander, đội Kafka và owner downstream cùng xử lý |
| SEV-2 | Một pipeline quan trọng ngừng hoặc lag vượt SLA nghiêm trọng | Điều phối owner pipeline, cập nhật định kỳ |
| SEV-3 | Một số partition/member lỗi nhưng có workaround và chưa vi phạm SLA lớn | Owner dịch vụ điều tra theo runbook |
| SEV-4 | Cảnh báo sớm, lỗi đơn lẻ hoặc suy giảm nhỏ | Ghi ticket, theo dõi và xử lý theo lịch |

Severity phải theo chính sách tổ chức và business impact thực tế. Đừng hạ severity chỉ vì broker vẫn trả lời request; pipeline có thể đang mất dữ liệu ở tầng ứng dụng.

## 4. Thiết lập timeline và đồng bộ thời gian

Timeline là nền tảng để phân biệt tương quan và nguyên nhân. Thu thập thời gian theo UTC hoặc một timezone thống nhất, ghi rõ timezone của từng nguồn.

Một timeline tối thiểu nên có:

| Thời điểm | Sự kiện | Nguồn bằng chứng |
|---|---|---|
| 09:02:10 | Alert consumer lag vượt ngưỡng | Monitoring |
| 09:04:30 | Deployment consumer version mới | CI/CD |
| 09:05:12 | Rebalance count tăng | Consumer metrics |
| 09:06:00 | Database p99 tăng | DB monitoring |
| 09:08:20 | Consumer throughput giảm | Consumer metrics |
| 09:15:00 | Rollback bắt đầu | Change log |
| 09:18:40 | Handler latency trở về baseline | APM |

Ví dụ chỉ để minh họa cách ghi timeline. Khi điều tra thật, lưu timestamp gốc của log và timestamp lúc collector nhận log nếu hai thời điểm khác nhau.

### Kiểm tra đồng hồ hệ thống

Clock skew làm log các node có vẻ sai thứ tự, gây khó đối chiếu request producer, broker và consumer. Kiểm tra NTP/chrony hoặc dịch vụ đồng bộ thời gian của nền tảng:

~~~bash
timedatectl status
~~~

Trên Linux có chrony:

~~~bash
chronyc tracking
chronyc sources -v
~~~

Lệnh và quyền truy cập phụ thuộc hệ điều hành. Không thay đổi thời gian hệ thống trong lúc broker đang chạy như một thao tác điều tra thông thường; điều chỉnh clock có thể ảnh hưởng TLS, token expiry, log correlation và các tiến trình khác.

## 5. Snapshot bằng chứng trước khi can thiệp

Tạo một thư mục evidence có quyền truy cập hạn chế, gắn incident ID và timestamp. Không đưa password, token, private key hoặc payload nhạy cảm vào file bằng chứng.

Danh mục snapshot:

| Nhóm | Nội dung cần lưu |
|---|---|
| Cluster | Broker/controller ID, version, node status, quorum status |
| Topic | Partition count, replication factor, leader, replicas, ISR, config |
| Consumer | Group state, committed offset, log end offset, lag, members, assignment |
| Producer | Error rate, retry rate, request latency, timeout, buffer exhaustion |
| Broker | Request latency, request queue, network processor, disk, page cache, GC |
| Application | Release/version, config diff, CPU, heap, GC, thread pool, exception |
| Downstream | DB pool/query/lock, HTTP status/latency, rate limit, queue depth |
| Security | Principal, auth mechanism, ACL decision, certificate metadata |
| Change history | Deploy, config change, scaling, maintenance, network/DNS change |

Snapshot phải đủ để so sánh trước và sau mitigation. Nếu chỉ chụp dashboard hiện tại mà không lưu chuỗi thời gian, rất khó chứng minh thay đổi có hiệu quả.

### Cấu trúc evidence đề xuất

~~~text
INC-2026-0042/
  timeline.md
  impact.md
  commands/
    cluster-health.txt
    topic-describe.txt
    consumer-groups.txt
  metrics/
    broker-dashboard.png
    consumer-dashboard.png
    downstream-dashboard.png
  logs/
    broker-window-redacted.log
    consumer-window-redacted.log
  config/
    consumer-config-before-redacted.yaml
    deployment-version.txt
  changes/
    mitigation-001.md
  validation/
    recovery-checks.md
~~~

Tên thư mục chỉ là ví dụ. Tuân thủ chính sách retention, phân loại dữ liệu và quyền truy cập evidence của tổ chức.

### Nguyên tắc bảo vệ dữ liệu

- Redact credential, Authorization header, SASL password, token, private key và PII.
- Giữ nguyên timestamp, error code, correlation ID đã được phép lưu.
- Không sửa log gốc; nếu cần redact, giữ bản gốc trong kho bảo mật và ghi rõ bản đã redact.
- Ghi checksum cho file evidence quan trọng nếu quy trình forensic yêu cầu.
- Không sao chép toàn bộ topic payload sang máy cá nhân để debug.
- Hạn chế quyền đọc evidence và đặt thời gian lưu theo policy.

## 6. Thu thập trạng thái cluster

### Broker API và CLI

Ghi lại broker metadata/version và trạng thái topic. Ví dụ liệt kê topic:

~~~bash
bin/kafka-topics.sh --bootstrap-server kafka.example.net:9092 --list
~~~

Mô tả topic:

~~~bash
bin/kafka-topics.sh --bootstrap-server kafka.example.net:9092 --describe --topic orders.events
~~~

Output describe giúp xem partition, leader, replicas và ISR. Lưu ý lệnh có thể cần command config để cung cấp TLS/SASL client properties. Không đưa credential trực tiếp vào command line.

Kiểm tra cấu hình topic:

~~~bash
bin/kafka-configs.sh --bootstrap-server kafka.example.net:9092 --entity-type topics --entity-name orders.events --describe
~~~

Đối chiếu cấu hình hiện tại với baseline đã được phê duyệt. Một giá trị khác baseline chưa chắc là nguyên nhân; cần xác định thay đổi có xuất hiện trước thời điểm incident hay không.

### Kiểm tra KRaft quorum

Với cluster KRaft, ghi nhận trạng thái controller quorum:

~~~bash
bin/kafka-metadata-quorum.sh --bootstrap-server kafka.example.net:9092 describe --status
~~~

Kiểm tra thông tin voter/replication theo subcommand được Kafka version hỗ trợ:

~~~bash
bin/kafka-metadata-quorum.sh --bootstrap-server kafka.example.net:9092 describe --replication
~~~

CLI và output khác nhau theo Kafka version. Lưu version và dùng đúng tài liệu release đang vận hành. Không tự xóa metadata log hoặc thay cluster.id/node.id để xử lý quorum issue.

### Những câu hỏi cần trả lời

- Có broker/controller nào mất kết nối hoặc restart liên tục?
- Metadata quorum có leader và đủ voter hoạt động không?
- Có partition nào không có leader?
- ISR có giảm hoặc under-replicated partition tăng không?
- Broker nào có disk/network/request queue bất thường?
- Lỗi xuất hiện đồng thời ở nhiều broker hay chỉ một node?

## 7. Thu thập trạng thái topic, partition và replication

Với topic bị ảnh hưởng, lưu:

- Partition count và replication factor.
- Leader, replica list và ISR của từng partition.
- Under-replicated và offline partition count.
- Topic-level config: retention, cleanup policy, min ISR, max message bytes.
- Ingress bytes/records theo partition.
- Leader/network/disk metric theo broker chứa replica.

Nếu chỉ một partition có vấn đề, so sánh broker leader và follower của partition đó với các partition khỏe. Nếu nhiều partition trên cùng broker cùng chậm, nghi vấn node-level resource hoặc network.

Không chạy reassignment hoặc preferred leader election trước khi có snapshot. Reassignment làm tăng network/disk load và có thể khiến broker vốn đang quá tải càng khó phục hồi.

### Kiểm tra partition cụ thể

~~~bash
bin/kafka-topics.sh --bootstrap-server kafka.example.net:9092 --describe --topic orders.events
~~~

Ví dụ cách đọc:

~~~text
Topic: orders.events  Partition: 0  Leader: 2  Replicas: 1,2,3  Isr: 1,2,3
Topic: orders.events  Partition: 1  Leader: 3  Replicas: 2,3,1  Isr: 3,1
Topic: orders.events  Partition: 2  Leader: 1  Replicas: 3,1,2  Isr: 1,2,3
~~~

Partition 1 thiếu replica 2 trong ISR. Cần đối chiếu broker 2 log, disk, network và replica fetch lag để xác định nguyên nhân; chỉ nhìn ISR chưa cho biết vì sao follower bị loại.

## 8. Thu thập trạng thái consumer group

Chạy lệnh describe trước khi thay đổi offset:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server kafka.example.net:9092 --describe --group orders-consumer
~~~

Lưu thêm members/assignment và group state nếu CLI version hỗ trợ:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server kafka.example.net:9092 --describe --group orders-consumer --members --verbose
~~~

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server kafka.example.net:9092 --describe --group orders-consumer --state
~~~

Đối chiếu:

- Consumer group có Stable, PreparingRebalance, CompletingRebalance hay trạng thái khác?
- Member count có thay đổi theo thời gian không?
- Partition nào có lag lớn nhất?
- Có partition không được assign?
- CURRENT-OFFSET có tồn tại hay chưa?
- LOG-END-OFFSET tăng do producer hay consumer đang tụt?
- Commit latency/failure có trùng với lag growth?

Committed offset là bằng chứng về tiến độ commit, không phải bằng chứng đầy đủ về business processing. Nếu ứng dụng commit trước khi downstream hoàn tất, phải thu thêm queue depth, task completion và business record count.

## 9. Thu thập log và phân loại lỗi

Log hữu ích khi lọc theo cửa sổ thời gian và correlation ID. Không gửi toàn bộ log không lọc cho người xử lý; nó tạo noise và có thể lộ dữ liệu.

### Log broker

Tìm:

- ERROR, FATAL, exception và stack trace.
- Leader election, ISR shrink/expand, replica fetcher failure.
- Request timeout, network disconnect, authentication/authorization error.
- Disk error, log directory offline, I/O exception.
- Controller/quorum election, metadata replication lag.
- GC pause, OOM, process restart và shutdown reason.

### Log consumer

Tìm:

- CommitFailedException, RebalanceInProgressException, TimeoutException.
- RecordDeserializationException và converter/schema error.
- DisconnectException, NotCoordinatorException, OffsetOutOfRangeException.
- max.poll.interval.ms exceeded hoặc heartbeat/session timeout.
- Listener exception, retry exhaustion, DLT publish failure.
- DB connection timeout, deadlock, HTTP 429/5xx và circuit breaker.

### Log producer

Tìm:

- TimeoutException, NotEnoughReplicasException, NotEnoughReplicasAfterAppendException.
- RecordTooLargeException, serialization error.
- Buffer exhaustion/max.block.ms timeout.
- Authentication/authorization failure.
- Retry rate tăng, request latency tăng hoặc delivery callback thất bại.

Tên exception và log message có thể thay đổi theo Kafka client/Spring Kafka version. Dùng exception class, error code và context (topic, partition, offset, client ID) để phân loại; không chỉ tìm chuỗi log cố định.

## 10. Thu thập metrics, traces và cấu hình

### Broker metrics

| Nhóm | Dữ liệu nên lấy | Ý nghĩa |
|---|---|---|
| Request | Request rate, request latency, queue time, handler idle | Broker có đang quá tải request? |
| Network | Bytes in/out, network processor idle, connection count | Có nghẽn network hoặc nhiều connection churn? |
| Replication | Under-replicated partitions, ISR shrink/expand, replica lag | Follower có theo kịp leader? |
| Storage | Disk usage, I/O latency, log flush, log directory error | Storage có trở thành nút thắt? |
| JVM | Heap, GC pause, allocation, thread count | JVM có pause hoặc thiếu tài nguyên? |
| Controller | Active controller/quorum health, metadata replication | Control plane có ổn định? |

### Producer metrics

- Record send rate và byte rate.
- Request latency p50/p95/p99.
- Retry rate, error rate, record error rate.
- Buffer available bytes và buffer wait time.
- Compression rate và batch size.
- In-flight requests và connection churn.

### Consumer metrics

- Records consumed rate và bytes consumed rate.
- Fetch latency, fetch rate, records per request.
- Records lag/lag max theo partition.
- Commit rate, commit latency và commit failure.
- Rebalance count/duration và assigned partitions.
- Poll interval, processing duration và listener error.

### Application/downstream metrics

- Handler duration theo event type.
- Queue depth và tuổi task cũ nhất.
- Executor active/queued/rejected.
- DB connection active/idle/pending, query p95/p99, lock wait.
- HTTP latency, 429, 5xx, timeout, retry.
- Business throughput: số event đã hoàn tất ở hệ thống đích.

### Tracing và correlation

Nếu dùng OpenTelemetry hoặc tracing framework, giữ trace/correlation ID qua producer, Kafka headers, consumer và downstream. Kafka không tự truyền distributed trace context trong mọi cấu hình; ứng dụng cần inject/extract headers phù hợp.

Không dùng trace ID làm metric label có cardinality cao. Metric dùng topic/group/partition hoặc operation label có giới hạn; trace phục vụ điều tra từng request/event.

### Lưu cấu hình thực tế

Ghi nhận:

- Broker properties và dynamic topic configs.
- Producer/consumer properties sau khi Spring Boot bind.
- Listener container factory, error handler, retry/backoff và acknowledgment mode.
- Deployment image digest, environment variables đã redact và resource limits.
- Connector config/worker config nếu Connect liên quan.
- Schema Registry compatibility/subject strategy nếu deserialize lỗi.

So sánh config runtime với Git/IaC source of truth để tìm drift. Không chỉ đọc file YAML trong repository rồi giả định pod đang chạy đúng file đó.

## 11. Xây dựng giả thuyết và khoanh vùng

Mỗi giả thuyết cần có ba phần: bằng chứng ủng hộ, bằng chứng có thể bác bỏ và phép kiểm tra tiếp theo.

Ví dụ:

| Giả thuyết | Bằng chứng ủng hộ | Kiểm tra để bác bỏ |
|---|---|---|
| Consumer code chậm | Handler p99 tăng, CPU/GC/queue tăng | So sánh profile và downstream time |
| Database nghẽn | Pool pending, query p99/lock tăng | Thử query health độc lập, xem DB resource |
| Hot partition | Một partition lag tăng nhanh, partition khác rảnh | Đếm key/bytes per partition |
| Broker quá tải | Request queue/latency tăng ở nhiều client | So sánh broker và client-side latency |
| Rebalance liên tục | Member churn, rebalance metric tăng | Đối chiếu restart, poll interval, heartbeat |
| Producer burst | Ingress rate tăng trước lag | So sánh producer rate và business batch schedule |
| Schema/deserialize lỗi | Deserialization exception lặp theo schema/event type | Decode sample record với schema đúng |
| ACL/TLS lỗi | Auth/authorization/handshake failure | Test bằng principal/certificate được phép |

Không coi hai metric tăng cùng lúc là bằng chứng nhân quả. Dùng timeline để xác định cái nào xuất hiện trước, rồi thực hiện kiểm tra độc lập nếu có thể.

### Phương pháp loại trừ

1. Chọn một phạm vi nhỏ: một topic, group, partition hoặc broker.
2. So sánh với một phạm vi khỏe có cùng loại workload.
3. Giữ nguyên một biến và thay đổi phép đo khác.
4. Kiểm tra trên cùng khoảng thời gian và cùng đơn vị.
5. Ghi kết quả xác nhận hoặc loại trừ giả thuyết.
6. Chỉ mở rộng phạm vi khi bằng chứng chỉ ra ảnh hưởng rộng hơn.

## 12. Phân biệt lỗi cấu hình, lỗi hạ tầng và lỗi ứng dụng

| Lớp | Dấu hiệu | Evidence ưu tiên |
|---|---|---|
| Application | Một release/consumer cụ thể lỗi, handler exception, CPU/GC | Release diff, trace, stack trace, runtime config |
| Kafka client/config | Timeout, poll violation, serializer, retry bất thường | Effective client config, client metrics, exception |
| Broker/cluster | Nhiều client cùng lỗi, partition offline, ISR giảm | Broker logs, topic describe, request/replication metrics |
| Network/DNS | Disconnect, timeout theo node/AZ, TLS handshake | DNS lookup, route, connection metrics, certificate |
| Security | Authentication/authorization failure | Principal, mechanism, ACL, certificate chain |
| Downstream | Consumer chờ DB/API, pool hoặc quota cạn | DB/APM/API metrics, trace |
| Data contract | Schema incompatibility, malformed record | Schema ID/subject/version, raw sample đã bảo vệ |

Nếu nhiều application độc lập cùng gặp lỗi ở cùng broker/AZ, ưu tiên kiểm tra shared infrastructure. Nếu chỉ một consumer version lỗi ngay sau deploy, ưu tiên kiểm tra code/config thay đổi.

## 13. Chọn mitigation và kiểm soát thay đổi

Trước khi thực hiện thay đổi, ghi một change record ngắn:

~~~text
Incident: INC-2026-0042
Hypothesis: Database connection pool saturation is slowing the consumer.
Evidence: Pool pending > 200, query p99 increased, Kafka fetch rate remains healthy.
Action: Reduce consumer concurrency from 12 to 6 for this workload.
Expected: DB pending falls and handler p99 improves; Kafka lag may temporarily grow.
Risk: Backlog grows while concurrency is reduced.
Rollback: Restore concurrency to 12 if DB recovers and processing remains under capacity.
Owner: on-call application engineer
Start time: 09:20 UTC
~~~

Chọn thay đổi theo blast radius:

- Ưu tiên thay đổi ở một workload/consumer group trước.
- Không restart toàn cluster nếu một broker hoặc client cụ thể gặp lỗi.
- Không thay partition count, replication factor và consumer config cùng lúc.
- Không tắt authentication/authorization để “test nhanh” trên production.
- Không xóa log, internal topic hoặc consumer offset.
- Có rollback condition rõ ràng và người theo dõi metric sau thay đổi.

### Mitigation và remediation khác nhau

- **Mitigation** giảm tác động ngay: giảm concurrency, tạm rate limit, rollback release, pause workload hoặc chuyển traffic theo runbook.
- **Remediation** sửa nguyên nhân gốc: tối ưu query, sửa hot key, điều chỉnh capacity, fix serializer, thay network route hoặc bổ sung monitoring.

Đóng incident sau mitigation không có nghĩa root cause đã được sửa. Ghi action item riêng cho remediation và xác định owner/deadline.

## 14. Xác nhận phục hồi theo từng lớp

Không dùng duy nhất trạng thái process hoặc broker RUNNING để kết luận. Xác minh từ hạ tầng đến business:

### Cluster

- Broker/controller health ổn định.
- Metadata quorum khỏe với KRaft cluster.
- Không có offline partition ngoài kế hoạch.
- Under-replicated partitions/ISR trở về baseline.
- Disk, network và request latency ổn định.

### Topic và producer

- Topic metadata/leader/ISR đúng.
- Producer send success rate trở về baseline.
- Retry, timeout và buffer wait giảm.
- Record canary được ghi vào partition mong đợi.

### Consumer

- Group ổn định, member count và assignment hợp lệ.
- Lag tăng đã dừng; backlog giảm theo catch-up rate dự kiến.
- Commit failure/rebalance bất thường đã hết.
- Listener handler duration và error rate trở về baseline.

### Downstream và dữ liệu

- Database/API hết saturation.
- Queue nội bộ giảm và oldest task age đạt mục tiêu.
- Event canary xuất hiện ở downstream.
- Số lượng event, business key, version/sequence và trạng thái cuối được đối chiếu.
- Duplicate/missing nằm trong delivery policy và được xử lý theo thiết kế.

### Security và contract

- Client authentication/TLS handshake thành công.
- ACL đúng quyền, không cần cấp super user tạm.
- Schema ID/subject/version resolve được.
- Connector task/Streams application hoạt động nếu pipeline dùng chúng.

## 15. Xác minh consumer catch-up và tính toàn vẹn dữ liệu

Sau khi xử lý, lấy lại cùng snapshot như trước:

- Lag per partition tại các mốc thời gian.
- Ingress và processed/commit rate.
- Group member/assignment và rebalance count.
- Handler/downstream p95/p99.
- Business output count hoặc checkpoint.

Nếu lag đang giảm, tính catch-up time bằng:

\[
T_{catchup} \approx \frac{Lag}{ConsumerRate - IngressRate}
\]

Chỉ dùng khi consumer rate lớn hơn ingress rate và workload tương đối ổn định. Nếu một partition nóng vẫn tăng, tổng lag giảm có thể che giấu partition đó; kiểm tra từng partition.

### Canary event

Một canary event nên có:

- Event ID duy nhất.
- Correlation ID.
- Timestamp phát sinh.
- Business key đại diện.
- Schema/version đã biết.

Theo dõi canary qua producer acknowledgment, topic partition/offset, consumer processing và downstream record. Không gửi dữ liệu canary có thể kích hoạt side effect thật như thanh toán hoặc gửi thông báo cho khách hàng; dùng môi trường/test tenant hoặc payload an toàn.

### Đối chiếu dữ liệu

Tùy pipeline, dùng một hoặc nhiều cách:

- Đếm event theo cửa sổ thời gian ở source và sink.
- So sánh sequence/version theo business key.
- Đối chiếu database CDC checkpoint/LSN với source log position.
- Kiểm tra DLT và retry topic.
- Tìm duplicate theo event ID/idempotency key.
- Đối chiếu output state/changelog với input history.

Không kết luận không mất dữ liệu chỉ vì consumer group lag về 0. Offset có thể đã bị reset hoặc commit sai; cần kiểm tra business invariant.

## 16. Khi nào incident được xem là phục hồi?

Chỉ đóng incident khi đáp ứng các tiêu chí đã thống nhất:

| Tiêu chí | Điều kiện hoàn tất |
|---|---|
| Service health | Broker, controller và client ổn định qua một cửa sổ quan sát |
| Error rate | Produce/consume/handler error trở về baseline |
| Lag | Lag không còn tăng và catch-up đạt mục tiêu |
| Replication | ISR/under-replicated partition đạt trạng thái mong đợi |
| Downstream | DB/API latency, pool và queue trở lại ngưỡng bình thường |
| Data integrity | Canary và business reconciliation PASS |
| Security | Không còn bypass tạm hoặc credential lộ |
| Ownership | Owner, follow-up và action items đã được ghi |

Cửa sổ quan sát phải phù hợp với workload. Với batch workload theo giờ, một vài phút xanh không đủ để chứng minh sự cố đã hết.

## 17. Mẫu ghi nhận RCA

~~~markdown
# Incident review: INC-2026-0042

## Impact
- Service/topic/group:
- Start/end time (UTC):
- Customer/business impact:
- SLO/RPO/RTO impact:

## Detection
- Alert or report:
- Time to detect:
- Time to acknowledge:

## Timeline
| Time (UTC) | Event | Evidence |
|---|---|---|

## Root cause
- Trigger:
- Contributing factors:
- Why existing safeguards did not prevent impact:

## Mitigation
- Actions and owners:
- Rollback performed:
- Recovery evidence:

## Data integrity
- Duplicate/missing assessment:
- Reconciliation result:

## Follow-up
| Action | Owner | Due date | Verification |
|---|---|---|---|
~~~

RCA tập trung vào điều kiện hệ thống và lỗ hổng trong quy trình, không tìm người để đổ lỗi. Tách trigger trực tiếp, yếu tố góp phần và lý do cảnh báo/guardrail không phát hiện sớm.

## 18. Những sai lầm khi điều tra

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Restart ngay khi thấy lỗi | Mất trạng thái và evidence, rebalance hoặc recovery kéo dài | Snapshot trước, restart theo runbook |
| Chỉ đọc log, không xem metrics | Không thấy xu hướng và phạm vi | Ghép log, metrics, traces và change timeline |
| Thay nhiều config cùng lúc | Không biết thay đổi nào có tác dụng | Một giả thuyết, một thay đổi có kiểm chứng |
| Reset offset để xóa lag | Bỏ sót hoặc replay dữ liệu | Xác minh business impact và dry-run |
| Xem broker online là phục hồi | Pipeline có thể vẫn lỗi ở schema/downstream | Canary end-to-end và reconciliation |
| Không ghi timestamp/timezone | Timeline sai, kết luận nhân quả sai | Chuẩn hóa UTC và kiểm tra clock skew |
| Lưu log/config có secret | Tạo thêm sự cố bảo mật | Redact và hạn chế quyền evidence |
| Đóng incident khi metric vừa xanh | Sự cố có thể tái diễn theo chu kỳ | Quan sát qua cửa sổ đủ dài |
| Không giao action item | Root cause tái diễn | Owner, deadline và tiêu chí verify |

## 19. Checklist điều tra nhanh

### Triage

- [ ] Xác định incident ID, severity, owner và thời điểm bắt đầu.
- [ ] Xác định cluster/topic/partition/group/application bị ảnh hưởng.
- [ ] Ghi nhận business impact, SLO, RPO/RTO.
- [ ] Chuẩn hóa timestamp/timezone.

### Evidence

- [ ] Snapshot cluster/quorum/broker health.
- [ ] Topic metadata, leader, replicas, ISR và config.
- [ ] Consumer group state, member, assignment, offset và lag.
- [ ] Producer/consumer/broker metrics theo cùng thời gian.
- [ ] Broker, client và downstream logs đã lọc/redact.
- [ ] Release, config, scaling, network và security change history.
- [ ] Evidence được lưu ở nơi có quyền truy cập phù hợp.

### Diagnosis và mitigation

- [ ] Có giả thuyết, evidence ủng hộ và phép kiểm tra bác bỏ.
- [ ] Đã phân biệt application, broker, network, security và downstream.
- [ ] Change record có expected result, risk và rollback.
- [ ] Không reset offset/xóa dữ liệu khi chưa có phê duyệt.
- [ ] Theo dõi metric sau mỗi thay đổi.

### Recovery và closure

- [ ] Broker/controller/topic/ISR ổn định.
- [ ] Producer và consumer error rate trở về baseline.
- [ ] Lag và catch-up time đạt mục tiêu.
- [ ] Downstream và queue nội bộ phục hồi.
- [ ] Canary end-to-end PASS.
- [ ] Business data reconciliation PASS.
- [ ] RCA và action items có owner/deadline.

## 20. Bài tập tự kiểm tra

1. Vì sao cần snapshot metric/log/config trước khi restart broker hoặc consumer?
2. Một timeline tốt phải ghi những timestamp và timezone nào?
3. Làm sao phân biệt lag do consumer với lag do database/API downstream?
4. Những thông tin nào cần lấy từ kafka-topics.sh describe?
5. Khi KRaft quorum bất thường, nên thu thập bằng chứng nào trước khi can thiệp?
6. Vì sao committed offset không chứng minh business processing đã hoàn tất?
7. Làm sao kiểm tra giả thuyết hot partition bằng dữ liệu?
8. Một change record cần có những nội dung nào?
9. Vì sao RUNNING hoặc lag bằng 0 chưa đủ để đóng incident?
10. Canary event cần được theo dõi qua những điểm nào?
11. Làm sao xác minh duplicate/missing sau khi consumer catch up?
12. RCA nên phân biệt trigger, contributing factors và failed safeguards như thế nào?

## Kết luận

Điều tra Kafka hiệu quả bắt đầu bằng việc xác định impact, chuẩn hóa timeline và lưu snapshot trước khi thay đổi. Sau đó thu thập bằng chứng từ cluster, topic/partition, producer, consumer group, application, network, security và downstream. Mỗi giả thuyết cần có phép kiểm tra để xác nhận hoặc loại trừ; mỗi mitigation cần có expected result, rủi ro và rollback.

Phục hồi chỉ được xác nhận khi cluster ổn định, producer/consumer hoạt động, lag catch up, downstream trở lại bình thường và dữ liệu được kiểm tra end-to-end. Giữ lại evidence, timeline và RCA với action owner cụ thể để sự cố tiếp theo được phát hiện sớm hơn và xử lý có cơ sở hơn.
