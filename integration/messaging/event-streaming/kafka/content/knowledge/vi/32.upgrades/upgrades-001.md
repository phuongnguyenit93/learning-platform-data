# Đọc release notes và lập ma trận broker, client, Connect, Streams

Nâng cấp Kafka là thay đổi đồng thời nhiều thành phần: broker, Java client, Spring Kafka, Kafka Connect, connector plugin, Kafka Streams, serializer và các dependency liên quan. Một cluster có thể khởi động thành công sau khi thay binary nhưng ứng dụng vẫn lỗi do protocol/feature level, cấu hình bị loại bỏ, thay đổi default, state store không tương thích hoặc plugin chưa hỗ trợ runtime mới.

Quy trình an toàn bắt đầu bằng việc đọc release notes và upgrade guide của **từng phiên bản nằm trên đường nâng cấp**, sau đó ghi các điều kiện tương thích vào một ma trận. Ma trận này giúp xác định thành phần nào được nâng trước, thành phần nào cần giữ tương thích tạm thời, cách kiểm thử và thời điểm không còn có thể rollback đơn giản.

## 1. Xác định phạm vi và phiên bản hiện tại

Trước khi đọc release notes, lập inventory chính xác. Không chỉ ghi một dòng “Kafka đang chạy phiên bản K”; cần biết từng nhóm thành phần đang dùng phiên bản nào.

| Thành phần | Thông tin cần thu thập |
|---|---|
| Broker | Kafka distribution/version, số broker, node ID, listener, security protocol, config overrides |
| Metadata/control plane | KRaft hay ZooKeeper, controller quorum, metadata feature level hiện tại |
| Java client | kafka-clients version được đóng gói trong từng service |
| Spring Kafka | Spring Boot, Spring Kafka, Spring Framework và dependency management/BOM |
| Kafka Connect | Worker runtime, converter, SMT, source/sink connector và plugin dependencies |
| Kafka Streams | kafka-streams version, application.id, state store, Serde, topology và EOS setting |
| Schema/data | Avro/Protobuf/JSON Schema, Schema Registry compatibility mode và schema evolution policy |
| Runtime | Java runtime, container base image, OS, TLS provider và thư viện authentication |

Ghi cả phiên bản thực tế đang chạy, không chỉ phiên bản khai báo trong build file. Dependency transitive, image cũ hoặc plugin đóng gói riêng có thể khiến runtime khác với kỳ vọng.

### Tạo baseline vận hành

Lưu lại trước nâng cấp:

- Broker/API versions và trạng thái từng node.
- Topic, partition, replication factor, min.insync.replicas và topic configs quan trọng.
- Leader/ISR, under-replicated/offline partitions và reassignment đang chạy.
- Consumer group offsets, lag, rebalance frequency và processing rate.
- Connect connector/task status và source offsets.
- Streams application state, task count, changelog/repartition topics và restore duration.
- Producer/consumer error rate, latency, throughput, heap/GC, disk và network.

Baseline giúp so sánh sau nâng cấp. Nếu không biết trạng thái trước thay đổi, khó xác định lỗi mới hay vấn đề đã tồn tại.

## 2. Đọc release notes theo từng phiên bản

Không chỉ đọc release notes của phiên bản đích. Hãy đọc upgrade guide và release notes của mọi phiên bản trên đường đi từ current đến target, bao gồm patch/minor/major release có liên quan. Một thay đổi có thể được giới thiệu ở release trước, bị deprecated ở release tiếp theo rồi bị loại bỏ ở release đích.

Với mỗi phiên bản, tìm các nhóm nội dung:

| Nhóm | Câu hỏi cần trả lời |
|---|---|
| Breaking changes | API, protocol, config, format hoặc behavior nào không còn tương thích? |
| Deprecations/removals | Property, CLI option, class hoặc feature nào sắp bị loại bỏ/đã bị loại bỏ? |
| Default changes | Giá trị mặc định nào đổi và ảnh hưởng workload hiện tại ra sao? |
| Upgrade path | Có bước trung gian bắt buộc hoặc phiên bản không thể bỏ qua không? |
| Broker/client protocol | Broker mới có giao tiếp được với client/broker cũ trong giai đoạn rolling không? |
| Metadata/features | Có metadata version/feature level mới cần kích hoạt riêng không? |
| Security | TLS, SASL, ACL, cipher, certificate hoặc authentication behavior nào đổi? |
| Performance | Batch, compression, fetch, thread, memory hoặc GC behavior nào thay đổi? |
| Connect/Streams | Connector API, task behavior, state store, Serde hoặc EOS có thay đổi không? |
| Operations | CLI, metrics, JMX, logging, startup/shutdown hoặc recovery behavior nào đổi? |

### Cách đọc một release note có hệ thống

1. Đọc upgrade guide trước để biết đường nâng cấp được hỗ trợ.
2. Đọc release notes theo thứ tự phiên bản từ cũ đến mới.
3. Tìm các từ khóa như `upgrade`, `compatibility`, `deprecated`, `removed`, `default`, `protocol`, `metadata`, `KIP`, `Connect` và `Streams`.
4. Ghi từng thay đổi có liên quan vào change ledger.
5. Gắn mỗi thay đổi với thành phần đang sử dụng nó.
6. Xác định hành động: sửa config, nâng dependency, migrate data/state, thay code hoặc chỉ cần xác minh.
7. Lưu đường dẫn tài liệu và phiên bản áp dụng để reviewer có thể kiểm tra lại.

Không suy luận rằng một tính năng mới tự động được bật khi nâng binary. Nhiều thay đổi cần bật feature level, thay config hoặc chủ động đổi ứng dụng.

## 3. Phân loại tác động và mức độ rủi ro

Mỗi thay đổi trong release notes nên được phân loại theo tác động:

| Mức | Ý nghĩa | Cách xử lý |
|---|---|---|
| Informational | Không ảnh hưởng cấu hình/code đang dùng | Ghi nhận và tiếp tục |
| Configuration | Property đổi tên, đổi default hoặc bị deprecated | So sánh effective config và test giá trị mới |
| Runtime behavior | Thay đổi retry, timeout, rebalance, batching hoặc ordering | Integration/load test |
| API/dependency | API bị thay đổi, thư viện/plugin cần nâng | Compile, compatibility test và packaging test |
| Data/state | Metadata, state store, schema hoặc internal format thay đổi | Backup, migration test và xác nhận downgrade boundary |
| Security | TLS/SASL/ACL/certificate behavior thay đổi | Security test và kiểm tra quyền |
| Operational | CLI, metrics, startup, recovery hoặc rolling procedure thay đổi | Diễn tập runbook và observability |

Ưu tiên rủi ro cao cho các thay đổi có thể gây mất dữ liệu, không tương thích protocol, không khôi phục được state hoặc khiến rollback không còn được hỗ trợ.

## 4. Mẫu compatibility matrix

Ma trận cần nối phiên bản hiện tại, phiên bản đích, dependency, điều kiện tương thích, kiểm thử và rollout. Không ghi chung “Kafka compatible” nếu chưa nêu cụ thể broker/client/runtime nào tương thích.

| Thành phần | Hiện tại | Đích | Điều kiện cần xác minh | Kiểm thử bắt buộc | Rollout |
|---|---|---|---|---|---|
| Broker | K | K+1 | Supported upgrade path, mixed-version window, protocol/metadata feature level | Produce/consume, replication, failover | Rolling |
| Java client | K-1 | K+1 | Client protocol/API, retry/default, Java runtime | Integration và load test | Theo service |
| Spring Kafka | S | S+1 | Spring Boot/Framework BOM và kafka-clients transitive version | Listener, transaction, error handler | Theo service |
| Connect worker | K | K+1 | Worker compatibility, internal topics, REST/config behavior | Worker rebalance và task restart | Rolling workers |
| Connector plugin | P | P+1 | Connect API, converter, SMT và dependency classpath | Source/sink end-to-end | Theo connector |
| Kafka Streams | K | K+1 | Upgrade compatibility, state store, Serde, EOS và topology | Restore, rebalance, state correctness | Theo upgrade guide |

K, K+1, S và P chỉ là ký hiệu minh họa, không đại diện cho cam kết tương thích giữa các phiên bản cụ thể.

### Các cột bổ sung nên có trong change ledger

| Cột | Nội dung |
|---|---|
| Release/source | Phiên bản và mục release note/upgrade guide |
| Component owner | Nhóm chịu trách nhiệm |
| Change | Mô tả thay đổi ngắn gọn |
| Current usage | Cấu hình/API hiện đang dùng |
| Required action | Sửa config, code, dependency, data hoặc không cần sửa |
| Validation evidence | Test, dashboard hoặc log chứng minh |
| Rollback note | Điều kiện cuối cùng còn có thể downgrade |
| Decision | Accepted, deferred, blocked hoặc not applicable |

## 5. Nâng cấp Kafka broker theo rolling upgrade

Rolling upgrade thay binary từng broker trong khi cluster tiếp tục phục vụ traffic. Cách này giảm downtime nhưng chỉ an toàn khi phiên bản và protocol trong giai đoạn mixed-version được Kafka hỗ trợ.

### Điều kiện trước khi bắt đầu

- Đã xác nhận upgrade path chính thức từ version hiện tại tới version đích.
- Không có offline partition hoặc under-replicated partition kéo dài.
- ISR ổn định và replication factor/min.insync.replicas đáp ứng durability objective.
- Không có reassignment, preferred leader election hoặc migration khác đang chạy.
- Có đủ disk/network/CPU headroom để chịu một broker restart.
- Producer/consumer retry và timeout đủ để chịu leader movement ngắn hạn.
- Có backup cấu hình, ACL, topic config, secret và metadata/cluster identity theo quy trình của tổ chức.
- Đã kiểm thử restore/rollback trong môi trường staging.

Không bắt đầu rolling upgrade khi cluster đang degraded. Nếu một broker khác mất trong lúc broker đầu tiên restart, số replica khả dụng có thể giảm dưới ngưỡng an toàn.

### Trình tự tổng quát

1. Xác nhận toàn cluster healthy và lưu baseline.
2. Chọn một broker theo rollout plan.
3. Di chuyển leader khỏi broker đó nếu cần và chờ ISR ổn định.
4. Dừng broker theo quy trình graceful shutdown.
5. Cài binary/runtime mới và áp dụng config đã review.
6. Khởi động broker, kiểm tra registration, logs, listeners và metadata catch-up.
7. Xác nhận broker tham gia ISR, không có offline partition và latency trở lại bình thường.
8. Chỉ tiếp tục broker kế tiếp sau khi health gate của broker hiện tại PASS.
9. Lặp lại cho broker còn lại, tuân thủ thứ tự controller/broker theo kiến trúc và upgrade guide.
10. Sau khi toàn cluster đã nâng binary, kiểm tra mixed-version residue, metrics, consumer groups và replication.

Với KRaft có dedicated controller nodes, controller quorum có quy trình rolling riêng. Với node kết hợp broker/controller, thứ tự và giới hạn restart phụ thuộc topology. Không áp dụng một thứ tự restart chung cho mọi deployment.

## 6. Inter-broker protocol và metadata version

Nâng binary và bật tính năng protocol/metadata mới là hai quyết định khác nhau.

Ở các Kafka release cũ, `inter.broker.protocol.version` (IBP) được dùng để kiểm soát protocol compatibility trong giai đoạn rolling upgrade. Với KRaft, metadata feature level, thường được biểu diễn qua `metadata.version`, kiểm soát định dạng/tính năng metadata mà cluster sử dụng. Cơ chế và property điều khiển đã thay đổi theo các thế hệ Kafka; một số phiên bản không còn dùng cùng cách cấu hình cũ.

Quy tắc vận hành:

- Đọc upgrade guide của đúng phiên bản để xác định cơ chế compatibility đang áp dụng.
- Giữ protocol/metadata feature ở mức tương thích cũ trong giai đoạn rolling nếu tài liệu yêu cầu.
- Không đặt IBP hoặc metadata.version bằng giá trị đoán từ số version binary.
- Chỉ nâng feature level sau khi toàn bộ broker/controller đủ phiên bản và các điều kiện tương thích đã được xác nhận.
- Ghi lại feature level trước/sau và xác định rõ thời điểm không còn rollback.

Nâng metadata feature level có thể thay đổi metadata format và làm binary cũ không thể đọc/khởi động lại cluster. Đây thường là một ranh giới rollback quan trọng. Không thực hiện bước finalize chỉ vì mọi broker đã chạy binary mới; cần kiểm tra compatibility và phê duyệt riêng.

## 7. KRaft và ZooKeeper là hai bối cảnh nâng cấp khác nhau

Nếu cluster hiện tại dùng ZooKeeper, hãy xác định target Kafka còn hỗ trợ ZooKeeper hay yêu cầu chuyển sang KRaft. Chuyển metadata mode từ ZooKeeper sang KRaft là một migration riêng với quy trình, điều kiện và kiểm tra riêng; không nên gộp vào một đợt nâng binary thông thường nếu chưa có kế hoạch được hỗ trợ.

Với KRaft, cần ghi rõ:

- Cluster ID và node ID hiện tại.
- Vai trò broker/controller của từng node.
- Controller quorum membership và availability.
- Metadata feature level.
- Metadata log/snapshot health.
- Cấu hình storage dành cho metadata log.

Không tạo cluster ID mới khi chỉ nâng cấp cluster hiện có. Không xóa metadata log hoặc tái khởi tạo controller quorum để xử lý lỗi nâng cấp nếu chưa có quy trình recovery chính thức.

Nếu phải chuyển ZooKeeper sang KRaft:

1. Xác định phiên bản hỗ trợ migration path.
2. Đọc migration guide riêng và các điều kiện về broker, controller, config và metadata.
3. Diễn tập trên bản sao staging có topology gần production.
4. Lập kế hoạch quorum, rollback và backup theo đúng hướng dẫn.
5. Thực hiện như một change riêng, có checkpoint và phê duyệt.

## 8. Lập ma trận tương thích cho Java client

Kafka Java client có thể được nâng độc lập với broker trong phạm vi protocol/API được hỗ trợ, nhưng không nên giả định mọi feature của client mới đều hoạt động với broker cũ. Client mới có thể fallback cho một số thao tác hoặc từ chối feature cần broker capability mới.

Với từng service, ghi:

- Phiên bản `kafka-clients` thực tế.
- Java runtime và build tool.
- Producer/consumer/AdminClient API đang dùng.
- Serializer/deserializer và Schema Registry client.
- Security mechanism, TLS provider và truststore.
- Consumer group protocol/partition assignor.
- Producer idempotence, transaction, retries và max in-flight.
- Timeout, fetch/batch size và compression.

### Kiểm tra hành vi client

Không chỉ compile thành công. Cần kiểm tra:

- Producer gửi record với acks, idempotence, retry và transaction như trước.
- Consumer join/rebalance, commit offset và xử lý revoke/assign callback.
- Deserializer xử lý schema cũ/mới và payload biên.
- AdminClient gọi được API đang sử dụng.
- TLS/SASL xác thực và ACL vẫn đúng.
- Client không tự thay đổi throughput/latency quá mức do default mới.

Đọc release notes của Kafka client artifact và release notes của framework bao quanh nó. Nếu dùng Spring Boot dependency management, xác minh dependency tree để biết kafka-clients cuối cùng được đóng gói.

## 9. Spring Kafka và Spring Boot

Spring Kafka là lớp tích hợp dựa trên Kafka Java client. Nâng Spring Kafka có thể kéo theo thay đổi ở listener container, error handler, transaction manager, retry topic, observation/metrics và dependency version.

Compatibility matrix cho ứng dụng Spring nên có:

| Thành phần | Kiểm tra |
|---|---|
| Spring Boot | Phiên bản Boot hỗ trợ Spring Framework và Spring Kafka nào |
| Spring Framework | API/runtime baseline và Jakarta namespace nếu có |
| Spring Kafka | Kafka client version, listener/container API, error handling |
| kafka-clients | Protocol compatibility và producer/consumer behavior |
| Serializer | JSON/Avro/Protobuf và schema evolution |
| Security | SASL/TLS, certificate, JAAS và ACL |

Kiểm thử ít nhất:

- `@KafkaListener` concurrency và lifecycle.
- Manual/automatic ack, batch listener và offset commit.
- Retry, DLT, recoverer và backoff.
- Transactional producer và transaction synchronization nếu sử dụng.
- Error handler, deserialization exception và poison record.
- Observation, Micrometer metrics và tracing.

Không nâng Spring Boot, Spring Kafka và Kafka broker cùng lúc trong một bước không thể tách nguyên nhân. Nếu cần nâng đồng thời, chia thành các checkpoint có thể kiểm thử và rollback độc lập.

## 10. Nâng cấp Kafka Connect và connector plugin

Kafka Connect worker runtime, connector plugin và converter là các thành phần có vòng đời riêng:

- **Worker runtime:** Kafka Connect framework và Kafka client được đóng gói cùng distribution.
- **Connector plugin:** source/sink connector do vendor hoặc tổ chức cung cấp.
- **Converter:** JSON, ByteArray, Avro, Protobuf hoặc converter tùy chỉnh.
- **SMT:** transform class và dependency.
- **ConfigProvider:** cơ chế lấy secret/config từ external system.

### Kiểm tra trước nâng cấp

1. Xác định Connect worker version và plugin version đang chạy trên từng worker.
2. Kiểm tra connector hỗ trợ Connect API/runtime đích.
3. Kiểm tra dependency jar, classloader isolation và xung đột thư viện.
4. Kiểm tra converter/SMT/config provider và schema registry client.
5. Lưu connector config, status và source offsets theo quy trình backup.
6. Xác định connector có thể restart/rebalance mà không gây duplicate hoặc bỏ sót không.

### Rolling upgrade worker

Với distributed Connect cluster, nâng worker theo từng node nếu compatibility window của các version cho phép:

1. Xác nhận worker group và tất cả connector/task đang RUNNING.
2. Dừng một worker theo quy trình.
3. Nâng runtime và plugin bundle tương thích.
4. Khởi động lại worker, xác nhận join cluster và REST status.
5. Kiểm tra task assignment, source/sink throughput, error và offset.
6. Chỉ nâng worker tiếp theo khi task đã ổn định.

Trong rolling period, task có thể được chuyển giữa worker và connector có thể restart. Một số plugin yêu cầu mọi worker có cùng plugin version; nếu classpath không đồng nhất, task có thể chạy được trên worker này nhưng FAILED khi chuyển sang worker khác. Hãy giữ plugin bundle đồng nhất trước khi mở rộng rollout.

Không xóa hoặc tạo lại Connect config/offset/status topics để xử lý upgrade. Các topic này chứa trạng thái runtime quan trọng; thay đổi partition/replication/cleanup policy phải theo hướng dẫn của Connect.

## 11. Nâng cấp Kafka Streams và state compatibility

Kafka Streams application là một Java application nhúng Kafka client và quản lý state store. Upgrade cần xét cả binary lẫn dữ liệu state:

- `application.id` và consumer group identity.
- Internal repartition topics và changelog topics.
- State store schema, Serde và RocksDB/native dependencies.
- Topology changes và processor behavior.
- Exactly-once processing setting.
- Standby replicas, restoration và local state directory.
- Partition count và task assignment.

### Upgrade compatibility

Kafka Streams có cơ chế hỗ trợ một số rolling upgrade giữa các version, bao gồm cấu hình `upgrade.from` ở các release hỗ trợ. Giá trị hợp lệ, điều kiện và quy trình phụ thuộc chính xác vào phiên bản đang nâng; không copy một giá trị từ ví dụ khác release.

Trước khi rolling upgrade:

1. Đọc Kafka Streams upgrade guide cho đúng đường version.
2. Kiểm tra version compatibility và cấu hình upgrade cần thiết.
3. Xác nhận state store/changelog có thể được đọc bởi binary mới.
4. Kiểm tra Serde tương thích với record cũ trong changelog/repartition topics.
5. Đo thời gian state restore và dung lượng network/disk cần thiết.
6. Kiểm tra topology optimization và EOS behavior có thay đổi không.

Nếu không có rolling compatibility được tài liệu xác nhận, hãy dùng quy trình stop-the-world có kiểm soát: dừng toàn bộ instance cũ, xác nhận không còn task active, triển khai binary mới theo kế hoạch, rồi khởi động lại và theo dõi restore. Không để hai version không tương thích cùng xử lý một `application.id`.

### State store và Serde

Binary mới có thể khởi động nhưng vẫn lỗi khi restore nếu Serde thay đổi format hoặc code không đọc được changelog record cũ. Khi thay đổi schema:

- Duy trì backward/forward compatibility theo hướng restore thực tế.
- Kiểm tra dữ liệu state cũ, tombstone và null handling.
- Test restore từ changelog đầy đủ, không chỉ test record mới.
- Đảm bảo retention của changelog đủ cho recovery objective.
- Không xóa internal topics để ép Streams tạo state mới nếu chưa chấp nhận mất state.

Đổi `application.id` không phải cách nâng version thông thường. Nó tạo identity/group/internal topic namespace khác và có thể khiến application bắt đầu xử lý lại dữ liệu theo reset policy.

## 12. Ma trận ví dụ cho một đợt nâng cấp

Giả sử tổ chức nâng từ release K lên K+1. Đây là ví dụ cấu trúc; các giá trị tương thích phải được điền từ upgrade guide chính thức của đúng release.

| Thành phần | Trạng thái hiện tại | Trạng thái đích | Gate trước khi rollout |
|---|---|---|---|
| Broker | K, KRaft | K+1, KRaft | Mixed-version support, controller order, metadata feature level |
| Java services | Client K-1 | Client K+1 | Broker protocol, Java runtime, retry/default, security |
| Spring services | Boot S / Spring Kafka T | Boot S+1 / Spring Kafka T+1 | BOM, transitive client, listener/transaction tests |
| Connect workers | Runtime K | Runtime K+1 | Worker compatibility, internal topics, plugin parity |
| Source/sink plugins | Plugin P | Plugin P+1 | Connect API, converters, SMT, source offsets |
| Streams apps | Streams K | Streams K+1 | Upgrade guide, state/Serde compatibility, restore |

### Change ledger mẫu

| Release note | Component | Tác động | Hành động | Bằng chứng |
|---|---|---|---|---|
| Default producer config changed | Java producer | Có thể đổi batching/latency | So sánh effective config, benchmark | Producer load test |
| Deprecated broker property removed | Broker | Broker không nhận config cũ | Thay property trước rollout | Startup/config validation |
| Connect plugin API change | Connect | Plugin cũ có thể không load | Nâng plugin và test classpath | Connector task RUNNING |
| Streams state compatibility note | Streams | Có thể cần upgrade.from hoặc stop/restart | Diễn tập restore | State correctness test |

Mỗi hàng cần link tới release note cụ thể, owner và quyết định. Không để các ghi chú mơ hồ như “đã đọc release notes” mà không chỉ ra thay đổi nào ảnh hưởng hệ thống.

## 13. Thứ tự nâng cấp tổng thể

Một trình tự thường dùng, cần điều chỉnh theo upgrade guide:

1. **Inventory và baseline:** ghi version, config, metrics, topic/group và state.
2. **Đọc release notes:** hoàn thành change ledger và compatibility matrix.
3. **Staging:** nâng toàn bộ stack trên môi trường gần production, kiểm thử rollback.
4. **Broker binaries:** rolling upgrade theo thứ tự được hỗ trợ, giữ compatibility level nếu tài liệu yêu cầu.
5. **Broker validation:** kiểm tra ISR, controller, protocol, latency, disk và client traffic.
6. **Connect workers/plugins:** nâng runtime/plugin theo compatibility window, xác nhận task/offset.
7. **Java clients/Spring services:** nâng dependency theo service, kiểm thử producer/consumer/API.
8. **Streams applications:** nâng theo state compatibility và rolling/stop-restart procedure.
9. **Finalize feature level:** chỉ nâng metadata/protocol feature khi đủ điều kiện và đã qua rollback gate.
10. **Enable new features:** bật tính năng mới theo từng workload, không bật đồng loạt chỉ vì binary hỗ trợ.
11. **So sánh baseline:** xác nhận SLO và business correctness không suy giảm.

Thứ tự Connect/Streams/client có thể thay đổi theo yêu cầu cụ thể của release. Điều quan trọng là mỗi giai đoạn phải có compatibility gate và trạng thái rollback rõ ràng.

## 14. Kiểm thử trước production

Staging nên dùng cùng Kafka mode (KRaft/ZooKeeper), security, replication factor, plugin và workload profile với production.

### Broker tests

- Produce/consume với acks và replication như production.
- Broker restart và leader election.
- Follower catch-up, ISR shrink/expand và broker failure.
- Rolling restart controller nếu có dedicated quorum.
- Topic creation/config alter và AdminClient API.
- TLS/SASL/ACL và certificate rotation nếu có thay đổi.

### Client/Spring tests

- Producer retry, idempotence, transaction và timeout.
- Consumer rebalance, commit, pause/resume và shutdown.
- Deserialization failure, retry/DLT và duplicate handling.
- Schema compatibility với record cũ/mới.
- Load test theo peak traffic và burst.

### Connect tests

- Worker restart/rebalance.
- Connector/task restart và task migration giữa worker.
- Source offset resume và sink delivery semantics.
- Converter/SMT/plugin classpath.
- REST API và secret/config provider.

### Streams tests

- Restore state từ changelog.
- Repartition và task migration.
- Serde của state cũ và record mới.
- EOS/transaction behavior.
- Rolling upgrade nếu được hỗ trợ; nếu không, stop/restart drill.

## 15. Rollout gates và quan sát sau mỗi bước

Đặt gate đo được thay vì quyết định dựa vào “service đã lên”:

| Gate | Điều kiện gợi ý |
|---|---|
| Broker health | Không có offline partition; ISR ổn định theo policy |
| Produce/consume | Error rate và p95/p99 latency trong ngưỡng |
| Replication | Không có under-replicated partition kéo dài |
| Consumer | Lag/record age và rebalance duration không tăng bất thường |
| Connect | Tất cả connector/task cần thiết RUNNING; source offsets tiến |
| Streams | Task RUNNING, restore hoàn tất, state correctness pass |
| Security | Authentication/authorization và TLS handshake thành công |
| Business | Event không mất/trùng ngoài semantics chấp nhận; end-to-end SLO đạt |

Theo dõi đủ lâu để quan sát peak/batch cycle của hệ thống. Một lần smoke test vài phút không đủ chứng minh throughput hoặc retention behavior ổn định.

## 16. Rollback và ranh giới không thể quay lại

Rollback không chỉ là cài lại binary cũ. Khả năng downgrade phụ thuộc:

- Broker protocol/metadata feature level đã nâng hay chưa.
- Cluster metadata hoặc log format đã thay đổi chưa.
- Connector config/source offset có được version mới ghi theo format khác không.
- Streams state store/changelog có tương thích với binary cũ không.
- Ứng dụng đã ghi record/schema mới mà consumer cũ không đọc được chưa.
- Có thay đổi security/config/API không thể đảo ngược không.

Trước khi nâng:

1. Ghi rõ phiên bản cuối cùng có thể downgrade.
2. Ghi rõ thao tác nào làm mất khả năng downgrade (ví dụ finalize metadata feature level hoặc ghi state/data theo format mới).
3. Chuẩn bị image/binary/config cũ và dependency artifact.
4. Có backup/restore plan và kiểm thử thực tế.
5. Xác định điều kiện abort rollout.

Sau khi vượt rollback boundary, phương án có thể là forward-fix, restore cluster/data từ backup hoặc dựng cluster mới và replicate/recover dữ liệu. Không hứa rollback binary nếu upgrade guide không hỗ trợ.

### Ví dụ quyết định

| Tình huống | Hành động |
|---|---|
| Một broker mới khởi động lỗi, feature level chưa đổi | Dừng rollout, khôi phục broker theo downgrade path được hỗ trợ |
| Client mới gây tăng retry/latency | Rollback service/client artifact, giữ broker nếu protocol tương thích |
| Connect plugin mới FAILED | Khôi phục plugin/runtime tương thích, kiểm tra source offsets trước resume |
| Streams restore lỗi do Serde | Dừng rollout, giữ state/changelog, sửa compatibility; không xóa state |
| Metadata feature đã finalize và binary cũ không hỗ trợ | Không downgrade tùy tiện; dùng forward-fix hoặc recovery plan được phê duyệt |

## 17. Công cụ kiểm tra và lệnh vận hành

Kiểm tra broker API versions được quảng bá:

~~~bash
bin/kafka-broker-api-versions.sh \
  --bootstrap-server kafka-1.example.com:9092
~~~

Kiểm tra topic, leader, replica và ISR:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --describe
~~~

Kiểm tra consumer group lag:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --describe \
  --all-groups
~~~

Kiểm tra Connect:

~~~bash
curl -s http://connect-1:8083/connectors
curl -s http://connect-1:8083/connectors/orders-sink/status
~~~

Các lệnh trên là ví dụ; thêm security client config phù hợp và giới hạn phạm vi topic/group để tránh output quá lớn. Công cụ quản lý metadata feature level thay đổi theo Kafka release; dùng đúng CLI/upgrade guide của phiên bản thay vì chạy lệnh feature-level không xác định.

### Metrics cần so sánh

- Broker request latency, request queue, network processor idle và request handler idle.
- Produce/fetch rate, error, retry và throttle.
- Under-replicated/offline partitions, ISR shrink/expand.
- Consumer lag, record age, rebalance và commit latency.
- Connect worker/connector/task state, source offset progress và sink error.
- Streams process latency, task state, restore rate, RocksDB/state metrics.
- Heap, GC pause, CPU, disk latency/free space và network throughput.
- Business success rate, duplicate/missing event và end-to-end latency.

So sánh cùng cửa sổ thời gian, cùng workload và cùng aggregation. Không kết luận hiệu năng tốt hơn chỉ vì CPU giảm nếu throughput hoặc business completion cũng giảm.

## 18. Những lỗi thường gặp khi nâng cấp

- **Chỉ đọc release notes của phiên bản đích:** bỏ sót thay đổi ở phiên bản trung gian.
- **Nâng tất cả cùng lúc:** khó xác định broker, client, plugin hay state store gây lỗi.
- **Nhầm binary version với feature level:** bật metadata/protocol mới quá sớm và mất rollback.
- **Giả định client mới luôn tương thích:** feature mới có thể cần broker capability mới.
- **Không kiểm tra dependency transitive:** Spring Boot hoặc plugin kéo kafka-clients khác dự kiến.
- **Connect worker không đồng nhất plugin:** task restart trên worker khác và thất bại vì thiếu class.
- **Không test Streams restore:** application khởi động nhưng không đọc được state/changelog cũ.
- **Đổi application.id để né lỗi upgrade:** tạo group/internal topic mới và có thể replay toàn bộ dữ liệu.
- **Xóa internal topics:** làm mất offset/config/state cần thiết cho recovery.
- **Rollback không xét metadata/data format:** binary cũ không đọc được state đã được ghi bởi version mới.
- **Không có baseline:** không phát hiện latency, lag hoặc duplicate tăng sau rollout.

## 19. Production checklist

- [ ] Inventory đầy đủ broker, KRaft/ZooKeeper, Java client, Spring Kafka, Connect, plugin và Streams.
- [ ] Xác định version path được hỗ trợ và đọc release notes của từng phiên bản đi qua.
- [ ] Ghi change ledger cho breaking change, deprecation, default, security và feature level.
- [ ] Hoàn thành compatibility matrix có owner, test evidence và rollback note.
- [ ] Baseline topic/partition/ISR, consumer groups, Connect tasks, Streams state và SLO.
- [ ] Xác nhận broker mixed-version và rolling upgrade procedure.
- [ ] Xác định IBP/metadata.version/feature-level gate đúng theo Kafka release.
- [ ] Tách ZooKeeper-to-KRaft migration khỏi binary upgrade nếu chưa có procedure kết hợp được hỗ trợ.
- [ ] Kiểm tra Java runtime, kafka-clients và Spring dependency tree.
- [ ] Kiểm thử producer, consumer, AdminClient, transaction, retry và security.
- [ ] Kiểm tra Connect worker topics, plugin parity, converter/SMT và source offsets.
- [ ] Kiểm tra Streams state store, Serde, changelog, EOS và upgrade compatibility.
- [ ] Diễn tập staging với load, broker failure, rebalance và state restore.
- [ ] Rollout theo từng thành phần, có health gate sau mỗi bước.
- [ ] Ghi rõ rollback boundary trước khi finalize feature level hoặc ghi format mới.
- [ ] So sánh metrics và business SLO sau nâng cấp.
- [ ] Cập nhật runbook, version inventory và quyết định đã phê duyệt.

Đọc release notes là bước tìm thay đổi; compatibility matrix biến các thay đổi đó thành quyết định kỹ thuật có thể kiểm chứng. Hãy nâng broker, client, Connect và Streams theo các giai đoạn riêng, giữ protocol/metadata compatibility trong cửa sổ rolling theo đúng upgrade guide, kiểm thử state và plugin, rồi chỉ finalize feature mới khi rollback boundary đã được hiểu và chấp nhận.
