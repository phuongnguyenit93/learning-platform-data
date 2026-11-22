# Lập bằng chứng xác nhận dữ liệu, hiệu năng và khả năng phục hồi

## Chứng minh hệ thống Kafka an toàn trước, trong và sau nâng cấp

Một lần nâng cấp Kafka chỉ được xem là thành công khi có bằng chứng cho thấy dữ liệu vẫn đúng, hệ thống đáp ứng SLO hiệu năng và các đường phục hồi vẫn hoạt động. Broker khởi động được hoặc dashboard chuyển sang màu xanh chưa đủ để kết luận.

Ba nhóm bằng chứng cần thu thập:

- **Tính toàn vẹn dữ liệu:** record không bị mất ngoài RPO đã chấp nhận, không phát sinh duplicate ngoài semantics dự kiến, key/value/header/schema còn đọc được và ordering theo key/partition được giữ.
- **Hiệu năng:** throughput, latency, error rate, consumer lag, broker resource và downstream vẫn nằm trong ngưỡng đã thống nhất.
- **Khả năng phục hồi:** replica/ISR, controller quorum, consumer group, Kafka Connect, Kafka Streams, backup và DR có thể phục hồi theo runbook.

Phải có baseline trước nâng cấp để so sánh với kết quả sau nâng cấp. Nếu không có baseline, nhóm vận hành không thể phân biệt thay đổi do bản Kafka mới với biến động tải thông thường.

## 1. Xác định phạm vi và điều kiện nâng cấp

### 1.1 Ghi rõ nguồn và đích

Trước khi thử nghiệm, lập bảng phiên bản và thành phần:

| Thành phần | Phiên bản hiện tại | Phiên bản đích | Bằng chứng cần có |
|---|---|---|---|
| Kafka brokers | Phiên bản đang chạy | Phiên bản dự kiến | Release notes, upgrade guide |
| KRaft metadata/feature | Feature level hiện tại | Feature level dự kiến | Kết quả kafka-features describe |
| Java producer/consumer | Client library | Client library | Compatibility matrix, integration test |
| Spring Kafka | Framework/dependency | Framework/dependency | Release notes và Kafka client version |
| Kafka Connect | Worker version | Worker version | Worker config, plugin compatibility |
| Connect plugins | Connector/version | Connector/version | Tài liệu nhà cung cấp connector |
| Kafka Streams | Library version | Library version | Streams upgrade guide, state compatibility |
| MirrorMaker 2 | Worker/client version | Worker/client version | Replication test và offset checkpoint |
| Schema Registry | Version | Version | Schema compatibility và serializer test |
| Monitoring/exporter | Agent/exporter | Agent/exporter | MBean/metric name mapping |

Không suy ra compatibility chỉ từ việc hai phiên bản đều kết nối TCP. Kiểm tra API protocol, Java runtime, serializer/deserializer, connector plugin, custom partitioner, custom authorizer và các thư viện tích hợp.

### 1.2 Kiểm tra đường nâng cấp được hỗ trợ

Đọc upgrade guide của đúng phiên bản đích và xác định:

- Phiên bản nguồn có nằm trong dải nâng cấp trực tiếp được hỗ trợ không.
- Có cần nâng qua phiên bản trung gian không.
- Có thay đổi về metadata version, feature version hoặc protocol không.
- Có yêu cầu nâng client, Connect, Streams hoặc Java trước broker không.
- Có cấu hình deprecated/removed cần thay thế không.
- Có giới hạn downgrade sau khi finalize feature hay ghi metadata mới không.

Ví dụ theo tài liệu Kafka 4.2:

- Kafka 4.2 chỉ hỗ trợ KRaft; cluster ZooKeeper phải migrate sang KRaft trước khi nâng lên 4.2.
- Hướng dẫn nâng server lên 4.2.0 nêu dải nguồn 3.3.x đến 4.1.x.
- Với Kafka 4.2, sau khi rolling upgrade broker và xác minh hành vi/hiệu năng, bước finalize feature được thực hiện bằng lệnh feature upgrade theo release version 4.2.
- Kafka 4.2.1 sửa lỗi rolling upgrade có thể gây UnsupportedVersionException với transactional producer; đồng thời sửa lỗi offline migration của Streams Rebalance Protocol.
- Kafka 4.2.2 bổ sung một số bản sửa lỗi liên quan exactly-once state restoration và metric end-to-end latency.

Đây là ví dụ theo tài liệu 4.2 tại thời điểm biên soạn, không phải quy trình chung cho mọi lần nâng cấp. Luôn kiểm tra trang Upgrade của đúng patch release trước khi thực hiện.

Với cluster KRaft nâng lên Kafka 4.2, lệnh finalize theo hướng dẫn release có dạng:

```bash
kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --release-version 4.2
```

Chạy lệnh này sau khi toàn bộ broker đã nâng và các evidence gate về cluster, dữ liệu, hiệu năng đã đạt. Không chạy như một bước thử nghiệm sớm trong rolling phase.

### 1.3 Đánh giá thay đổi có thể ảnh hưởng dữ liệu

Lập danh sách workload đang sử dụng:

- Producer idempotence, transaction và acks=all.
- Consumer group protocol, static membership và cooperative rebalance.
- Kafka Streams state store, changelog, repartition topic và EOS.
- Share Groups hoặc Streams Rebalance Protocol nếu đã bật.
- Log compaction, retention, tiered storage và remote log.
- ACL, SASL/TLS, custom principal builder/authorizer.
- Kafka Connect source/sink offset, SMT và converter.
- MirrorMaker 2, offset checkpoint và topic config sync.

Với mỗi tính năng, xác định test case và người chịu trách nhiệm xác nhận. Không chỉ test producer/consumer đơn giản nếu hệ thống thực tế có transaction, Streams, Connect hoặc compacted topic.

## 2. Tạo baseline trước nâng cấp

### 2.1 Chụp trạng thái cluster

Thu thập trạng thái trong khoảng thời gian tải bình thường và giờ cao điểm:

| Nhóm | Dữ liệu cần lưu |
|---|---|
| Version | Broker version, client version, build/revision nếu có |
| KRaft | Controller leader, voter set, quorum status, metadata/feature level |
| Topology | Broker, controller, rack, listener, partition assignment |
| Replication | RF, ISR, under-replicated, under-min-ISR, offline partition |
| Topic | Partition count, cleanup policy, retention, config quan trọng |
| Consumer | Group ID, member, assignment, committed offset, lag theo partition |
| Connect | Connector/task status, source/sink offset, error/retry |
| Streams | Application ID, state restoration, task assignment, changelog lag |
| Security | Listener, TLS/SASL, ACL và principal đang dùng |

Các lệnh kiểm tra cơ bản:

```bash
# Xem broker và API versions mà từng broker hỗ trợ
kafka-broker-api-versions.sh --bootstrap-server kafka-1:9092

# Xem feature/metadata version đã finalize
kafka-features.sh --bootstrap-server kafka-1:9092 describe

# Xem trạng thái KRaft metadata quorum
kafka-metadata-quorum.sh --bootstrap-server kafka-1:9092 describe --status

# Xem leader, replicas và ISR của topic
kafka-topics.sh --bootstrap-server kafka-1:9092 --describe --topic orders

# Xem lag và offset của consumer group
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 \
  --describe --group order-projection
```

Lưu nguyên output, timestamp, cluster identity và endpoint đã truy vấn. Nếu môi trường dùng TLS/SASL, truyền file cấu hình bảo mật bằng tùy chọn CLI của phiên bản đó; không đưa password hoặc token trực tiếp vào command history.

### 2.2 Ghi baseline metric

Thu thập metric theo cùng cửa sổ thời gian, cùng tag và cùng workload:

**Broker và replication**

- UnderReplicatedPartitions.
- UnderMinIsrPartitionCount.
- OfflinePartitionsCount.
- IsrShrinksPerSec và IsrExpandsPerSec.
- Produce/fetch request rate và latency.
- Request queue time, request handler idle và network processor idle.
- Bytes in/out, replication bytes in/out.
- Disk utilization, disk latency, CPU, heap và GC pause.

**Producer**

- Record send rate và byte rate.
- Request/ack latency p50/p95/p99.
- Retry rate, error rate và timeout.
- Buffer available bytes, waiting threads và buffer exhaustion.

**Consumer**

- Records/bytes consumed rate.
- Consumer lag tổng và theo partition.
- Time between poll, processing time và commit latency.
- Rebalance rate, failed fetch và commit errors.

**Connect và Streams**

- Connector/task state và task restart count.
- Source/sink record rate, error/retry và offset commit.
- Streams task assignment, rebalance, state restore duration.
- Changelog/repartition lag và RocksDB state-store health.

Tên metric/MBean có thể thay đổi theo phiên bản hoặc exporter. Lưu cả metric gốc, tag và mapping của exporter để so sánh đúng sau nâng cấp.

### 2.3 Chuẩn hóa tải thử

Baseline cần ghi lại:

- Tốc độ producer theo record/giây và byte/giây.
- Kích thước record trung bình, p95 và phân bố key.
- Số topic, partition, replication factor và consumer group.
- Tỷ lệ transaction, compression, TLS và authentication.
- Tỷ lệ đọc/ghi, số consumer, số connector/task.
- Downstream latency, database write rate và API quota.
- Thời gian warm-up và khoảng đo ổn định.

Không so sánh một lần đo giờ thấp điểm trước nâng cấp với giờ cao điểm sau nâng cấp. Tốt nhất chạy lại cùng kịch bản benchmark, cùng dữ liệu mẫu và cùng giới hạn tài nguyên.

## 3. Bằng chứng xác nhận tính toàn vẹn dữ liệu

### 3.1 Dùng canary event có thể đối chiếu

Tạo một bộ event kiểm thử có:

- event_id duy nhất.
- Key xác định để kiểm tra ordering.
- Sequence number theo key.
- Timestamp và event type.
- Payload cố định hoặc có checksum.
- Header/schema version.

Ví dụ envelope:

```json
{
  "event_id": "upgrade-check-2026-000001",
  "key": "customer-42",
  "sequence": 1,
  "event_type": "UpgradeCanary",
  "payload": {
    "amount": 125000,
    "currency": "VND"
  },
  "payload_sha256": "expected-sha256-from-test-fixture"
}
```

Hash trong ví dụ là giá trị do test harness tính ra; không dùng chuỗi minh họa này như checksum thật. Chuẩn hóa payload trước khi hash để thứ tự field hoặc whitespace không làm sai kết quả.

Nên gửi canary vào topic kiểm thử riêng hoặc dùng namespace/key được quy định cho test. Tránh ghi dữ liệu giả vào topic nghiệp vụ production nếu chưa có quy trình cho phép.

### 3.2 Đối chiếu producer và consumer

Với mỗi batch test, lưu:

| Bằng chứng | Cách xác nhận |
|---|---|
| Số event dự kiến | Manifest của test producer |
| Số event đã được ACK | Producer callback/result với acks theo cấu hình |
| Số event consumer nhận | Bộ đếm ở consumer test |
| Event bị thiếu | So sánh tập event_id expected và received |
| Duplicate | Đếm event ID xuất hiện nhiều lần |
| Payload corruption | So sánh checksum sau deserialize |
| Ordering | Kiểm tra sequence tăng đúng theo key/partition |
| Schema | Deserialize và validate schema version |
| Header/timestamp | So sánh metadata mong đợi với record nhận được |

Không dùng offset tuyệt đối làm bằng chứng duy nhất rằng dữ liệu giống nhau. Offset là vị trí trong partition của một log cụ thể; sau restore, mirror hoặc tạo topic mới, offset có thể khác. Dùng event ID, payload hash và business invariant để xác minh nội dung.

### 3.3 Kiểm tra transaction và idempotence

Nếu ứng dụng dùng transactional producer:

1. Gửi một transaction chứa nhiều record và commit.
2. Gửi transaction thứ hai rồi abort.
3. Đọc bằng consumer isolation.level=read_committed.
4. Xác nhận transaction committed xuất hiện đầy đủ.
5. Xác nhận transaction aborted không bị lộ cho consumer read_committed.
6. Kiểm tra producer fencing, transaction timeout và retry.

Với idempotent producer, chạy test có retry/network interruption trong môi trường kiểm thử và xác nhận không có duplicate ngoài semantics đã thiết kế. Không mô phỏng lỗi mạng bằng cách ngắt ngẫu nhiên broker production.

Ví dụ consumer test:

```properties
enable.auto.commit=false
isolation.level=read_committed
```

Nếu hệ thống không dùng transaction, không áp đặt điều kiện read_committed như một tiêu chí bắt buộc. Chọn isolation level theo semantics thực tế của ứng dụng.

### 3.4 Kiểm tra compacted topic và retention

Với compacted topic:

- Ghi nhiều phiên bản cho cùng key.
- Gửi tombstone cho key kiểm thử.
- Kiểm tra consumer rebuild state nhận được trạng thái cuối đúng.
- Xác nhận key đã xóa không xuất hiện trong state cuối.

Với topic retention:

- Kiểm tra log start offset và log end offset.
- Xác nhận segment mới vẫn đọc được.
- Không yêu cầu đọc dữ liệu đã hết retention.
- So sánh retention config trước và sau nâng cấp.

### 3.5 Kiểm tra metadata và quyền truy cập

Xác nhận:

- Topic/partition không bị thiếu hoặc tự tạo ngoài kế hoạch.
- RF, leader và ISR đạt chính sách.
- Cleanup policy, retention, compression và message size giữ đúng cấu hình.
- ACL cho producer, consumer, Connect và Streams còn hiệu lực.
- TLS certificate, SASL mechanism và authorization hoạt động.
- Schema Registry subject/version/compatibility còn đúng.

Lưu output describe trước và sau để review thay đổi ngoài dự kiến.

## 4. Bằng chứng xác nhận hiệu năng

### 4.1 So sánh cùng một workload

Chạy ít nhất ba giai đoạn:

1. **Baseline:** đo trước nâng cấp khi cluster ổn định.
2. **Canary:** đo một broker hoặc nhóm ứng dụng đã nâng cấp trong môi trường/stage phù hợp.
3. **Post-upgrade:** đo sau khi toàn cluster và client đã nâng cấp, warm-up hoàn tất.

Mỗi lần đo cần giữ nguyên:

- Số producer/consumer và tốc độ input.
- Payload size, key distribution và compression.
- Số partition, RF và số replica ISR.
- Downstream capacity và quota.
- Thời gian warm-up, thời gian lấy mẫu và tài nguyên cấp phát.

Nếu workload thực tế thay đổi, ghi rõ khác biệt và không gộp các số liệu thành một kết luận duy nhất.

### 4.2 Chỉ số hiệu năng cần đối chiếu

| Chỉ số | Cách đánh giá |
|---|---|
| Producer throughput | Records/s và MB/s đã được ACK |
| Producer latency | p50/p95/p99 của thời gian gửi/ACK |
| Consumer throughput | Records/s và MB/s đã xử lý thành công |
| Consumer lag | Tổng lag, lag lớn nhất theo partition và xu hướng |
| End-to-end latency | Từ lúc phát event đến khi side effect hoàn tất |
| Error/retry | Producer error/retry, consumer error, Connect task failure |
| Broker request | Produce/fetch latency và request queue time |
| Replication | Under-replicated, ISR shrink/expand, replica lag |
| Resource | CPU, heap, GC, disk latency, network throughput |
| Downstream | DB/API latency, connection pool, quota và error rate |

Ưu tiên p95/p99 và xu hướng theo thời gian. Average có thể che giấu một partition nóng hoặc một số request có latency rất cao.

### 4.3 Tính mức thay đổi

Với metric mà giá trị lớn hơn là tốt hơn, ví dụ throughput:

\[
\Delta(\%)=\frac{After-Before}{Before}\times100
\]

Với latency hoặc error rate, mức tăng thường là xấu:

\[
Regression(\%)=\frac{After-Before}{Before}\times100
\]

Nếu baseline bằng 0 hoặc rất nhỏ, không dùng phần trăm để kết luận; dùng số tuyệt đối và SLO. Ví dụ error rate tăng từ 0 lên 1 lỗi/giờ cần được đánh giá theo loại lỗi, không diễn giải bằng phần trăm vô hạn.

### 4.4 Ví dụ bảng so sánh

Các số dưới đây chỉ minh họa cách trình bày bằng chứng, không phải ngưỡng mặc định của Kafka:

| Metric | Baseline | Sau nâng cấp | SLO/giới hạn | Kết quả |
|---|---:|---:|---:|---|
| Producer throughput | 80.000 rec/s | 82.000 rec/s | >= 75.000 rec/s | Đạt |
| Producer p99 ACK | 18 ms | 20 ms | <= 30 ms | Đạt |
| Consumer processing p99 | 45 ms | 48 ms | <= 60 ms | Đạt |
| Consumer lag trend | Giảm/ổn định | Giảm/ổn định | Không tăng liên tục | Đạt |
| Under-replicated partitions | 0 | 0 | 0 sau ổn định | Đạt |
| Produce errors | 0 | 0 | Theo error budget | Đạt |

Kết quả chỉ có ý nghĩa khi hai lần đo dùng cùng tải, thời gian đo và phạm vi metric. Nếu p99 tăng nhưng vẫn trong SLO, cần ghi nhận mức thay đổi và theo dõi thay vì tự động kết luận nâng cấp thất bại.

### 4.5 Phân biệt benchmark tổng hợp và benchmark ứng dụng

Công cụ kafka-producer-perf-test.sh và kafka-consumer-perf-test.sh hữu ích để đo đường truyền broker/client và tạo tải có kiểm soát. Chúng không thay thế benchmark ứng dụng đầu-cuối vì không mô phỏng đầy đủ:

- Serialization/deserialization thật.
- Business validation và database/API side effect.
- Transaction, retry và idempotency của ứng dụng.
- Spring Kafka listener container, thread pool và error handler.
- Connect converter/SMT và connector-specific behavior.
- Kafka Streams state store, changelog và restore.

Chạy cả synthetic benchmark lẫn application-level test. Khi dùng CLI, đọc help và tài liệu của đúng phiên bản vì tên option có thể được đổi hoặc deprecated giữa các release.

## 5. Bằng chứng xác nhận khả năng phục hồi

### 5.1 Replica và leader election

Trong staging hoặc môi trường diễn tập đã được phê duyệt:

1. Ghi canary records với ID và checksum đã biết.
2. Xác nhận leader, replicas và ISR trước thử nghiệm.
3. Dừng một broker theo kịch bản kiểm thử.
4. Xác nhận partition có leader hợp lệ nếu còn ISR.
5. Kiểm tra producer/consumer tiếp tục theo SLA.
6. Khởi động lại broker và chờ follower catch up.
7. Xác nhận ISR trở lại mục tiêu và canary data không mất.

Không đồng thời dừng nhiều broker hoặc controller nếu kịch bản chưa được thiết kế để kiểm tra tình huống đó. Không bật unclean leader election chỉ để test partition online.

### 5.2 KRaft controller quorum

Với KRaft, kiểm tra riêng:

- Controller leader và voter set.
- Metadata log end/high watermark nếu công cụ cung cấp.
- Quorum majority và trạng thái controller.
- Thời gian controller failover trong diễn tập.
- Broker registration và partition state sau khi controller mới được bầu.

Controller quorum là lớp metadata, khác với data replication của partition. Quorum khỏe không chứng minh mọi ISR khỏe; ISR đầy đủ cũng không chứng minh controller quorum có thể chịu lỗi.

Lưu output trước/sau từ:

```bash
kafka-metadata-quorum.sh --bootstrap-server kafka-1:9092 describe --status
kafka-features.sh --bootstrap-server kafka-1:9092 describe
```

### 5.3 Consumer group và offset recovery

Thực hiện restart consumer member hoặc rolling restart ứng dụng:

- Xác nhận group rejoin và partition assignment hoàn tất.
- Kiểm tra rebalance count và thời gian rebalance.
- So sánh committed offset, current position và lag.
- Xác nhận không bỏ sót event ID đã được producer ACK.
- Kiểm tra duplicate theo semantics at-least-once hoặc exactly-once của ứng dụng.
- Xác nhận commit chỉ diễn ra sau side effect theo thiết kế.

Không yêu cầu offset number phải giữ nguyên giữa các cluster hoặc sau restore. Điều cần chứng minh là vị trí xử lý và business result chính xác.

### 5.4 Kafka Connect

Với mỗi connector quan trọng:

- Lưu connector config đã loại secret.
- Ghi trạng thái connector và từng task.
- Lưu source offset hoặc sink progress trước thử nghiệm.
- Restart worker/task trong staging.
- Xác nhận task trở lại RUNNING và không tạo duplicate/missing record ngoài semantics.
- Kiểm tra DLQ, retry, converter, SMT và external system side effect.

Một connector ở trạng thái RUNNING không bảo đảm dữ liệu đã được ghi đúng vào hệ thống ngoài. Đối chiếu record count hoặc business key ở database/object store đích.

### 5.5 Kafka Streams

Với mỗi Streams application:

- Ghi application.id, topology, input/output topic và internal topics.
- Lưu trạng thái task, changelog lag và state restoration duration.
- Kiểm tra state store sau restart/rebalance.
- Chạy test join, window, aggregation và suppression đang được dùng.
- Với EOS, xác nhận output và committed offsets nằm trong transaction đúng.
- Kiểm tra RocksDB local state và khả năng restore từ changelog.

Nếu nâng Kafka Streams từ 3.4 hoặc cũ hơn lên 4.2, upgrade guide yêu cầu hai rolling bounces: lượt đầu đặt upgrade.from theo phiên bản nguồn, lượt thứ hai bỏ cấu hình này. Cơ chế này xử lý thay đổi serialization của foreign-key join và internal repartition topic. Không áp dụng một rolling restart chung cho mọi bước nâng Streams.

### 5.6 Backup và DR

Để chứng minh khả năng phục hồi thực sự, cần ít nhất một bài diễn tập:

- Restore topic/event archive vào cluster hoặc topic cô lập.
- Kiểm tra schema, record count, checksum và business invariant.
- Kiểm tra consumer offset mapping nếu chuyển cluster.
- Thử MirrorMaker 2 failover/failback nếu hệ thống dùng geo-replication.
- Ghi RPO và RTO thực tế.

Backup chưa từng restore thành công chỉ là một giả định, không phải bằng chứng recovery.

## 6. Quy trình thu thập bằng chứng trong một lần nâng cấp

### Giai đoạn A — Trước thay đổi

1. Chốt source/target version và compatibility matrix.
2. Lưu cấu hình broker, KRaft feature level, topic config, ACL và client inventory.
3. Kiểm tra backup/DR và xác nhận restore path.
4. Chụp baseline metrics, consumer lag và replication health.
5. Chạy canary data test và lưu manifest ID/hash.
6. Chạy benchmark cùng workload để có baseline hiệu năng.
7. Lập rollback boundary: bước nào còn có thể downgrade, bước nào đã finalize metadata/feature.

### Giai đoạn B — Trong rolling upgrade

1. Nâng từng broker theo thứ tự và quy trình của release guide.
2. Sau mỗi broker, xác nhận broker online, API version, controller/quorum health và partition leadership.
3. Xác nhận ISR không suy giảm ngoài ngưỡng cho phép.
4. Chạy canary produce/consume và kiểm tra transaction nếu có.
5. So sánh request latency, error/retry, throughput và consumer lag.
6. Chỉ tiếp tục broker kế tiếp khi evidence gate của broker hiện tại đạt.

### Giai đoạn C — Sau khi mọi broker đã nâng

1. Xác nhận tất cả broker chạy đúng binary/version đích.
2. Xác nhận controller quorum và broker registration ổn định.
3. Xác nhận partition leader, ISR và under-replicated/offline partition.
4. Chạy data integrity test, transaction test và client integration test.
5. Chạy benchmark sau upgrade trong cùng điều kiện baseline.
6. Chạy recovery drill đã định trước.
7. Review toàn bộ evidence và quyết định có finalize feature/metadata version hay không.

### Giai đoạn D — Sau khi finalize

1. Chạy kafka-features describe và lưu feature/metadata level mới.
2. Kiểm tra lại API, producer, consumer, Connect, Streams và security.
3. Lặp lại canary test và kiểm tra dữ liệu.
4. Theo dõi hiệu năng qua ít nhất một chu kỳ tải đại diện.
5. Kiểm tra backup, DR, offset checkpoint và runbook.
6. Đóng change chỉ khi mọi tiêu chí acceptance đã có bằng chứng.

## 7. Evidence gate và tiêu chí nghiệm thu

Không dùng một ngưỡng chung cho mọi cluster. Xác định ngưỡng từ SLO, RPO/RTO, error budget và baseline của chính hệ thống.

| Gate | Bằng chứng bắt buộc | Điều kiện đạt mẫu |
|---|---|---|
| Compatibility | Version matrix, release notes, client/plugin inventory | Mọi thành phần quan trọng nằm trong dải được hỗ trợ |
| Cluster health | Broker/API version, KRaft quorum, partition describe | Broker online, quorum có majority, không có offline partition |
| Durability | RF, ISR, min ISR, canary ACK | ISR đạt chính sách và canary được xác nhận |
| Data integrity | Event ID, count, checksum, schema, ordering | Không thiếu/corrupt event ngoài RPO và semantics đã duyệt |
| Transactions | Commit/abort test, read_committed result | Transaction behavior đúng như baseline/contract |
| Performance | Before/after p95/p99, throughput, lag, resource | Đạt SLO và không có regression vượt ngưỡng đã duyệt |
| Connect/Streams | Task state, offset, state restore, output check | Pipeline và state phục hồi đúng |
| Recovery | Broker/controller drill, restore/DR rehearsal | RPO/RTO thực tế nằm trong mục tiêu |
| Finalization | Feature/metadata describe, sign-off | Đã hiểu downgrade boundary và có quyết định rõ |

### 7.1 Khi nào phải dừng rollout?

Dừng ở broker/phase hiện tại và điều tra khi:

- Broker không rejoin cluster hoặc controller quorum mất majority.
- Offline partition xuất hiện hoặc ISR giảm dưới chính sách durability.
- Producer nhận lỗi tăng bất thường hoặc transactional producer gặp UnsupportedVersionException.
- Consumer lag tăng liên tục và không có khả năng drain.
- Canary event thiếu, checksum sai, ordering sai hoặc transaction bị lộ.
- p99 vượt SLO, request queue tăng hoặc broker resource bão hòa.
- Connect task restart loop hoặc Streams state restoration thất bại.
- Không xác định được feature/metadata version hoặc rollback boundary.

Không tiếp tục nâng node tiếp theo chỉ vì node vừa nâng đã mở port và nhận connection.

## 8. Downgrade, rollback và giới hạn phục hồi

### 8.1 Phân biệt rollback binary với downgrade metadata

Trong một số rolling upgrade, có thể quay lại binary cũ khi cluster vẫn giữ protocol/feature/metadata level tương thích. Nhưng sau khi finalize feature hoặc metadata version có thay đổi không tương thích, downgrade có thể không được hỗ trợ.

Vì vậy, trước khi chạy lệnh finalize:

- Lưu feature/metadata level hiện tại.
- Đọc downgrade note của release guide.
- Xác định rõ dữ liệu/metadata mới có được ghi hay không.
- Có backup/restore plan đã thử nghiệm.
- Có quyết định go/no-go được ghi nhận.

Không coi việc còn giữ file binary cũ là bằng chứng có thể rollback an toàn.

### 8.2 Kafka Streams cần đánh giá riêng

Streams có serialization cho repartition topic, state store format và RocksDB format. Một bản Streams mới có thể ghi định dạng mà bản cũ không đọc được. Downgrade in-flight có thể yêu cầu chuyển upgrade.from, chờ xử lý hết dữ liệu định dạng mới hoặc xóa local state store để rebuild từ changelog theo hướng dẫn phiên bản.

Không xóa state directory hoặc internal topic theo phỏng đoán. Chỉ làm theo downgrade guide của đúng phiên bản và sau khi đã xác định dữ liệu có thể tái tạo.

### 8.3 Khi không thể downgrade

Chuẩn bị phương án forward-fix hoặc restore:

- Giữ nguyên cluster và log data để điều tra.
- Khôi phục service từ cluster DR nếu cần.
- Restore backup vào môi trường cô lập.
- Reconcile record đã xử lý trong thời gian nâng cấp.
- Chỉ chuyển traffic sau khi xác minh event ID, checksum và business state.

## 9. Bộ hồ sơ bằng chứng nên lưu

Một evidence pack tối thiểu nên có:

| Artifact | Nội dung |
|---|---|
| upgrade-plan.md | Source/target version, scope, sequence, owner và rollback boundary |
| compatibility-matrix.csv | Broker, client, Connect, Streams, plugin và Java version |
| cluster-before/ | Broker API versions, feature level, quorum, topic/ISR, group lag |
| metrics-before/ | Baseline dashboard export và raw time series |
| canary-manifest.json | Event ID, expected count, key sequence và checksum |
| test-results/ | Producer/consumer, transaction, schema và integration test |
| cluster-after/ | Các lệnh describe/API/quorum sau mỗi phase |
| metrics-after/ | Throughput, p95/p99, lag, error, resource và replication |
| recovery-drill.md | Kịch bản, thời gian, RPO/RTO và kết quả restore |
| decision-record.md | Acceptance, exception, người phê duyệt và thời điểm finalize |

Lưu timestamp có timezone, cluster ID, release/build ID, command đã chạy và exit code. Nếu lưu dashboard screenshot, kèm query/metric/tag và khoảng thời gian để người khác có thể tái tạo kết quả.

Không đưa SASL password, private key, token, secret connector hoặc dữ liệu cá nhân vào evidence pack. Redact thông tin nhạy cảm nhưng giữ lại tên config, principal alias và kết quả kiểm tra cần thiết.

## 10. Ví dụ báo cáo nghiệm thu

Ví dụ cấu trúc báo cáo; thay bằng số liệu đo thực tế:

```text
Change: KAFKA-UPGRADE-2026-014
Cluster: kafka-prod-a
Source: 4.1.x
Target: 4.2.x
Window: 2026-11-20T01:00:00Z - 2026-11-20T03:00:00Z

DATA
- Canary expected: 1,000,000 event IDs
- Canary received: 1,000,000
- Missing IDs: 0
- Duplicate IDs: 0 (under the test's idempotency contract)
- Payload checksum mismatches: 0
- Transaction commit/abort test: PASS
- Schema and ordering checks: PASS

PERFORMANCE
- Producer throughput: baseline vs post-upgrade
- Producer ACK p99: baseline vs post-upgrade
- Consumer processing p99: baseline vs post-upgrade
- Consumer lag: stable or draining
- Broker request latency/resource: within agreed SLO

RECOVERY
- Broker restart/leader election drill: PASS
- ISR returned to target: PASS
- Consumer group restart and offset continuity: PASS
- Backup/DR restore test: PASS
- Measured RPO/RTO: within agreed objectives

FINALIZATION
- Feature/metadata level before:
- Feature/metadata level after:
- Downgrade boundary reviewed: YES
- Go/no-go decision:
- Approver and timestamp:
```

Không điền PASS khi chưa có log, metric, test output hoặc người xác nhận tương ứng. Báo cáo phải cho phép người review truy ngược từng kết luận đến artifact gốc.

## 11. Checklist vận hành

- [ ] Đã đọc upgrade guide của đúng source/target version.
- [ ] Đã kiểm tra compatibility của broker, client, Java, Connect, Streams và plugin.
- [ ] Đã xác nhận KRaft/ZooKeeper migration prerequisite nếu có.
- [ ] Đã lưu feature/metadata version và controller quorum baseline.
- [ ] Đã lưu topic, partition, RF, ISR, ACL và consumer group baseline.
- [ ] Đã tạo canary event có ID, sequence và checksum.
- [ ] Đã lưu throughput, p95/p99, lag, retry/error và resource baseline.
- [ ] Đã kiểm tra backup và khả năng restore trước rollout.
- [ ] Đã có evidence gate sau từng broker/phase.
- [ ] Đã xác nhận data integrity và transaction semantics.
- [ ] Đã benchmark cùng workload trước/sau.
- [ ] Đã thử broker restart, controller failover và consumer recovery trong môi trường phù hợp.
- [ ] Đã kiểm tra Connect task, Streams state và offset recovery.
- [ ] Đã xác định downgrade boundary trước feature/metadata finalization.
- [ ] Đã lưu evidence pack, exception và quyết định go/no-go.

## Kết luận

Một lần nâng cấp Kafka cần được chứng minh bằng ba nhóm bằng chứng: dữ liệu vẫn toàn vẹn, hiệu năng vẫn đạt SLO và hệ thống có thể phục hồi theo RPO/RTO. Baseline trước nâng cấp là mốc so sánh; canary event, checksum, transaction test và business invariant chứng minh dữ liệu; throughput, p95/p99, lag và resource metrics chứng minh hiệu năng; broker/controller/consumer/Connect/Streams/backup drill chứng minh khả năng phục hồi.

Thực hiện kiểm tra theo từng gate, giữ lại output và metric có thể truy vết, rồi mới finalize feature hoặc metadata version. Đặc biệt với KRaft và Kafka Streams, ranh giới downgrade có thể phụ thuộc metadata và serialization state. Không kết luận thành công chỉ vì broker đã khởi động; chỉ đóng change khi bằng chứng dữ liệu, hiệu năng và phục hồi đều đạt tiêu chí đã thống nhất.

## Tài liệu tham khảo

- Apache Kafka 4.2 Upgrade Guide: https://kafka.apache.org/42/getting-started/upgrade/
- Apache Kafka 4.2 KRaft Operations: https://kafka.apache.org/42/operations/kraft/
- Apache Kafka 4.2 Compatibility: https://kafka.apache.org/42/getting-started/compatibility/
- Apache Kafka 4.2 Monitoring: https://kafka.apache.org/42/operations/monitoring/
- Apache Kafka 4.2 Kafka Streams Upgrade Guide: https://kafka.apache.org/42/streams/upgrade-guide/
- Apache Kafka 4.2 Kafka Streams Broker Compatibility: https://kafka.apache.org/42/streams/upgrade-guide/#streams-api-broker-compatibility
