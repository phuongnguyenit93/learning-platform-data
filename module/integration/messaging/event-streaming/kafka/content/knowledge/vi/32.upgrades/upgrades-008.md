# Điều kiện rollback và thay đổi không thể hạ cấp

Nâng cấp Kafka không chỉ là thay file binary của broker. Một đợt nâng cấp có thể thay đổi protocol giữa broker, feature level của cluster, metadata trong KRaft, cách ghi record, client behavior và state của Kafka Connect hoặc Kafka Streams. Nếu phải rollback, phiên bản cũ phải hiểu được dữ liệu và metadata mà phiên bản mới đã tạo.

Vì vậy, cần phân biệt ba hành động:

- **Binary rollback:** chạy lại phiên bản broker/client trước đó.
- **Protocol hoặc feature downgrade:** hạ mức tính năng mà cluster công bố cho broker và client.
- **Data restore/recovery:** khôi phục metadata hoặc record từ backup/DR khi trạng thái hiện tại không còn tương thích.

Ba hành động này không tương đương. Quay lại binary cũ không tự hạ metadata.version, không khôi phục record đã bị retention xóa và không đảo ngược một migration dữ liệu. Một số thay đổi có thể downgrade trong một dải phiên bản nhất định; một số khác cần forward-fix hoặc restore từ bản backup tương thích.

## 1. Rollback không phải lúc nào cũng là downgrade

| Hành động | Thay đổi gì? | Điều kiện chính |
|---|---|---|
| Binary rollback | Phiên bản executable của broker/client | Binary cũ phải hỗ trợ metadata, protocol và log format hiện tại |
| Protocol downgrade | Inter-broker protocol level ở các release dùng cấu hình này | Tất cả broker phải hỗ trợ protocol level đích |
| Feature downgrade | Feature level như metadata.version trong KRaft | Release phải hỗ trợ downgrade và cluster chưa dùng feature không thể đảo ngược |
| Config rollback | Giá trị cấu hình broker/topic/client | Cấu hình cũ còn hợp lệ và không tạo side effect dữ liệu |
| Application rollback | Phiên bản producer/consumer/Connect/Streams | Schema, state store và record đã ghi phải tương thích |
| Data restore | Khôi phục log/metadata từ backup hoặc DR | Backup nhất quán, có thể restore và đáp ứng RPO/RTO |

Ví dụ: broker mới đã nâng feature level và ghi metadata theo format mới. Việc thay binary về bản cũ có thể làm broker không khởi động hoặc không đọc được metadata. Ngược lại, nếu binary đã được nâng nhưng feature level vẫn giữ ở mức cũ, rollback binary có thể còn khả thi nếu ma trận tương thích của release cho phép.

Không bao giờ giả định có thể rollback chỉ vì còn lưu Docker image hoặc package cũ.

## 2. Phân biệt version của binary, protocol và feature

Kafka có nhiều lớp version:

| Lớp | Mục đích | Ví dụ/khái niệm |
|---|---|---|
| Broker binary version | Phiên bản phần mềm đang chạy | Kafka broker release |
| Client version | Phiên bản producer/consumer/admin client | kafka-clients library |
| Inter-broker protocol | Protocol broker dùng để giao tiếp | IBP trong các release cũ |
| Metadata feature level | Feature/metadata format mà cluster kích hoạt | metadata.version trong KRaft |
| KRaft quorum feature | Khả năng/format của metadata quorum | kraft.version ở các release hỗ trợ |
| Record/message format | Cách record được mã hóa trong log | Message format/record batch version |
| Application/schema version | Contract payload và state của ứng dụng | Avro/Protobuf/JSON schema version |

Các lớp này có quan hệ nhưng không nhất thiết tăng cùng lúc. Một cluster có thể chạy binary mới trong khi vẫn giữ protocol/feature level cũ để duy trì khả năng tương thích trong rolling upgrade.

### IBP trong các release cũ

Các phiên bản Kafka trước đây dùng cấu hình inter.broker.protocol.version (IBP) để kiểm soát protocol giữa broker. Quy trình nâng cấp thường nâng binary trước, giữ IBP ở mức cũ trong rolling upgrade, rồi mới nâng IBP sau khi mọi broker đã chạy phiên bản mới.

IBP đã thay đổi vai trò theo lịch sử Kafka và không phải hướng điều khiển chung cho mọi release hiện đại. Không thêm inter.broker.protocol.version vào cấu hình mới nếu release đang dùng đã chuyển sang feature level hoặc loại bỏ cấu hình này.

### metadata.version trong KRaft

Trong KRaft, metadata.version là feature level của metadata cluster. Nó không đơn giản là số phiên bản binary và không nên tự sửa bằng cách chỉnh file server.properties.

Các feature level được quản lý qua cơ chế feature API/CLI của Kafka. Khả năng upgrade/downgrade phụ thuộc phiên bản broker, feature đang dùng và trạng thái finalized của cluster. Luôn đọc release notes và tài liệu upgrade/downgrade cho đúng cặp phiên bản.

## 3. Xác định supported upgrade path trước khi bắt đầu

Không phải mọi phiên bản Kafka đều hỗ trợ nâng trực tiếp từ bất kỳ bản cũ nào. Có thể phải nâng qua một hoặc nhiều phiên bản trung gian, thay đổi Java runtime hoặc xử lý ZooKeeper/KRaft riêng.

Preflight cần xác minh:

- Phiên bản Kafka hiện tại và phiên bản đích.
- Phiên bản trung gian bắt buộc theo release notes.
- Java runtime được hỗ trợ bởi từng phiên bản.
- Broker protocol/metadata feature level hiện tại.
- KRaft hay ZooKeeper mode; nếu KRaft thì controller quorum và role layout.
- Kafka client compatibility của producer, consumer và AdminClient.
- Kafka Connect worker, connector plugin và converter.
- Kafka Streams application, state store và changelog compatibility.
- Schema Registry hoặc schema service nếu có.
- OS, filesystem, container image và security provider.
- Các cấu hình đã deprecated/removed hoặc đổi default.

Ví dụ inventory cần lưu:

~~~text
Cluster: payments-prod
Current broker release: <current-version>
Target broker release: <target-version>
Current metadata.version: <current-feature-level>
Current KRaft/ZooKeeper mode: <mode>
Controller layout: <controller-only or combined>
Java runtime: <version>
Connect workers/plugins: <versions>
Streams applications: <versions>
Producer/consumer client libraries: <versions>
Schema compatibility policy: <policy>
~~~

Không suy ra version chỉ từ tên Docker tag hoặc tên thư mục cài đặt. Kiểm tra broker runtime, package/image digest và feature state thực tế.

## 4. Ma trận tương thích phải bao gồm toàn bộ hệ sinh thái

Broker không phải thành phần duy nhất có thể bị ảnh hưởng:

| Thành phần | Rủi ro khi nâng cấp | Cần xác minh |
|---|---|---|
| Producer | Thay đổi default, retry, idempotence, compression hoặc API | Client compatibility, acks, serializer và timeout |
| Consumer | Thay đổi rebalance, fetch, group protocol hoặc offset behavior | Group membership, commit và replay |
| Kafka Connect | Worker protocol, connector plugin, converter và offset | Worker/connector compatibility, config và source offsets |
| Kafka Streams | State store, changelog, topology và processing semantics | Upgrade path, standby restore và application ID |
| Schema Registry | Compatibility mode, serializer/deserializer | Schema IDs, subject naming và backward/forward compatibility |
| Security | SASL/TLS provider, principal mapping, ACL | Authentication và authorization sau upgrade |
| Monitoring | JMX names, metric labels và exporter | Dashboard/alert không bị mất series |
| Automation | CLI flags, config defaults và Admin API | Script và IaC chạy được với version đích |

Một broker upgrade thành công nhưng Connect worker không tương thích vẫn có thể làm CDC pipeline dừng. Một Streams application rollback không tương thích state store có thể phải rebuild state từ changelog hoặc nguồn gốc.

## 5. Phân biệt rollback config với rollback dữ liệu

Một số thay đổi cấu hình có thể hoàn tác bằng cách ghi lại giá trị cũ. Nhưng cấu hình có thể đã tạo side effect trước khi được revert.

| Thay đổi | Revert config có đủ không? | Lý do |
|---|---|---|
| Tăng log level | Thường có | Không thay đổi dữ liệu |
| Thay request thread count | Thường có | Cần theo dõi tải sau khi đổi |
| Thay quota | Thường có | Client có thể đã bị throttle hoặc vượt capacity trong thời gian áp dụng |
| Thay retention.ms giảm | Không chắc | Segment đã bị xóa không tự xuất hiện lại |
| Bật compaction | Không | Record cũ có thể đã bị compact |
| Tăng partition count | Không | Kafka không hỗ trợ giảm partition count tại chỗ |
| Xóa topic | Không | Tạo lại topic cùng tên không khôi phục log cũ |
| Nâng metadata feature level | Phụ thuộc feature/release | Có thể không còn downgrade path |
| ZooKeeper sang KRaft migration | Không nên giả định | Migration/finalization có thể là điểm không thể quay lại |
| Thay schema và phát record mới | Không | Record mới có thể không đọc được bởi consumer cũ |

Rollback phải đánh giá cả trạng thái cấu hình và side effect đã xảy ra.

## 6. Các thay đổi cần coi là không thể hạ cấp

Một thay đổi nên được coi là non-downgradable nếu tài liệu release không công bố đường quay lại được hỗ trợ hoặc nếu dữ liệu đã được ghi theo format mà phiên bản cũ không hiểu.

### Metadata hoặc feature level mới

Khi cluster kích hoạt feature level mới, broker cũ có thể không hiểu metadata hoặc protocol tương ứng. Một số feature level có thể downgrade trước khi feature được finalized/được sử dụng; một số feature khác không hỗ trợ downgrade. Không có quy tắc chung cho mọi Kafka release.

### ZooKeeper sang KRaft

Migration metadata từ ZooKeeper sang KRaft thay đổi nơi và cách cluster quản lý metadata. Đây là thay đổi kiến trúc, không chỉ đổi một config. Sau khi migration/finalization hoàn tất, không lập kế hoạch rollback bằng cách khởi động lại ZooKeeper cũ trừ khi quy trình của đúng release nêu rõ hỗ trợ.

### Record format và log data

Các release cũ có thể dùng cấu hình message format version riêng. Phiên bản mới có thể ghi record batch hoặc metadata mà broker/client cũ không đọc được. Nếu log đã chứa format mới, binary rollback có thể không an toàn.

### Partition count

Kafka hỗ trợ tăng partition count nhưng không hỗ trợ giảm partition count của một topic tại chỗ. Nếu tăng nhầm, hướng xử lý thường là tạo topic mới với số partition mong muốn và migrate dữ liệu/consumer theo kế hoạch.

### Retention và compaction

Khi retention hoặc compaction đã xóa record/segment, tăng retention hoặc tắt compaction không phục hồi dữ liệu đã bị loại. Cần backup/archive độc lập nếu dữ liệu phải khôi phục.

### Schema và application state

Producer mới có thể đã ghi schema/payload mà consumer cũ không hiểu. Streams state store hoặc changelog có thể đã thay đổi theo application version. Quay lại application binary không bảo đảm state có thể đọc được.

## 7. KRaft: kiểm soát metadata.version và quorum

Trong KRaft, metadata quorum lưu metadata log của cluster. Nâng broker binary và nâng metadata feature level là hai bước khác nhau. Cần kiểm tra cả broker compatibility lẫn quorum health.

Trước khi upgrade:

- Xác minh controller quorum có leader và đủ voter majority.
- Kiểm tra lag của metadata log và trạng thái snapshot.
- Kiểm tra controller-only hoặc combined node layout.
- Xác minh mọi broker/controller hỗ trợ feature level đích.
- Xác định feature nào sẽ được bật sau upgrade.
- Đọc downgrade support của từng feature level.

Kiểm tra quorum status:

~~~bash
kafka-metadata-quorum.sh \
  --bootstrap-server kafka-1:9092 \
  describe \
  --status
~~~

Kiểm tra feature level:

~~~bash
kafka-features.sh \
  --bootstrap-server kafka-1:9092 \
  describe
~~~

Tên command và option có thể thay đổi theo Kafka release/distribution. Dùng --help của đúng binary và tài liệu phiên bản đang chạy.

### Không nâng metadata.version giữa rolling binary upgrade

Trong rolling upgrade, giữ feature level ở mức được tất cả broker đang chạy hỗ trợ. Chỉ nâng feature level sau khi broker/controller binaries đã được nâng và cluster health ổn định, theo thứ tự trong release guide.

Ví dụ lệnh upgrade feature ở dạng minh họa:

~~~bash
kafka-features.sh \
  --bootstrap-server kafka-1:9092 \
  upgrade \
  --feature metadata.version=<supported-target-level>
~~~

Không copy giá trị feature level từ cluster khác hoặc từ ví dụ cũ. Xác minh level đích được hỗ trợ bởi tất cả broker/controller và đúng release.

### Downgrade feature chỉ khi được hỗ trợ

Một số release có lệnh downgrade feature:

~~~bash
kafka-features.sh \
  --bootstrap-server kafka-1:9092 \
  downgrade \
  --feature metadata.version=<supported-previous-level>
~~~

Đây là cú pháp định hướng, không phải lời khẳng định mọi metadata.version đều có thể downgrade. Trước khi chạy, xác minh release support matrix, feature dependencies, finalized status và điều kiện rollback. Nếu downgrade không được hỗ trợ, giữ binary hiện tại và forward-fix hoặc restore theo DR plan.

## 8. ZooKeeper sang KRaft là một migration riêng

Không gộp migration ZooKeeper-to-KRaft vào một lần broker version upgrade thông thường nếu chưa có kế hoạch riêng. Migration có các bước, điều kiện version và metadata synchronization riêng.

Preflight:

- Kiểm tra release hỗ trợ migration path từ mode hiện tại.
- Xác minh ZooKeeper ensemble khỏe và có backup theo hướng dẫn.
- Kiểm tra broker/controller version và cấu hình quorum.
- Kiểm tra metadata sync, ACL, topic config và broker registration.
- Lập kế hoạch chuyển controller quorum và cutover.
- Xác định rõ migration point sau đó không còn đường quay về ZooKeeper được hỗ trợ.

Không tự copy ZooKeeper data vào KRaft metadata directory hoặc ngược lại. Không khởi động đồng thời hai metadata authority cho cùng cluster ngoài quy trình migration được hỗ trợ.

Sau khi KRaft migration được finalize, xem KRaft là metadata authority. Nếu cần phục hồi, dùng KRaft-aware backup/DR procedure phù hợp; không coi ZooKeeper snapshot cũ là rollback tương đương.

## 9. Chuẩn bị backup và recovery trước upgrade

Backup phải có thể khôi phục, không chỉ là một bản sao file được tạo ra. Xác định dữ liệu và metadata cần bảo vệ:

| Đối tượng | Cần lưu | Cách xác minh |
|---|---|---|
| Broker configuration | Static/dynamic config, listener, log dirs, rack, quotas | Export và diff |
| Topic metadata/config | Partition, RF, cleanup, retention, min ISR | Describe/export trước upgrade |
| ACL | Principal, resource, operation, host, pattern | Export và kiểm tra restore |
| Quota | User/client/default overrides | Describe configs |
| Consumer offsets | Group, topic, partition, committed offset | Export offsets cho workload quan trọng |
| Connect | Worker config, connector config, plugin version, source offsets | Export REST config và backup backend cần thiết |
| Streams | Application config, state/changelog strategy | Kiểm thử restore/rebuild |
| Schema | Subject, schema version, compatibility mode | Export và test compatibility |
| KRaft metadata | Snapshot/backup theo cơ chế được hỗ trợ | Restore drill trên môi trường cô lập |
| Business records | Archive, source of truth hoặc DR cluster | Thử replay và reconcile |

Không copy trực tiếp thư mục log hoặc metadata đang được broker sử dụng rồi gọi đó là backup nhất quán. Dùng snapshot/quy trình backup được Kafka distribution, storage platform hoặc vendor hỗ trợ.

Replication không phải backup độc lập. Delete, logical corruption hoặc record sai có thể được replicate sang DR. Cần backup/archive có retention và quyền xóa tách biệt.

## 10. Kiểm tra sức khỏe cluster trước upgrade

Không bắt đầu rolling upgrade khi cluster đang degraded.

Kiểm tra:

- Offline partition count bằng 0.
- Under-replicated partitions bằng 0 hoặc có exception được hiểu rõ.
- ISR ổn định, không shrink liên tục.
- Không có broker/log directory offline.
- KRaft quorum có leader và đủ voter.
- Disk còn headroom cho log growth, reassignment và recovery.
- CPU, heap, GC và network không ở mức saturation.
- Consumer lag nằm trong SLO hoặc có kế hoạch drain.
- Producer error/retry/throttle không bất thường.
- Connect task và Streams app ở trạng thái ổn định.
- Backup/restore test đã đạt.

Nếu cluster đang có URP, offline partition, quorum instability hoặc disk gần đầy, xử lý nguyên nhân trước. Upgrade đồng thời với incident làm tăng blast radius và khó xác định lỗi do đâu.

## 11. Canary và staging trước production

Một upgrade plan cần được diễn tập trên môi trường tương đồng production:

1. Dùng cùng source version và target version.
2. Dùng cùng KRaft/ZooKeeper mode và controller layout.
3. Dùng cùng loại storage, filesystem và JVM.
4. Dùng topic/partition/RF tương tự.
5. Dùng cùng client, Connect plugin và Streams application versions.
6. Chạy workload đại diện và đo latency/throughput.
7. Thử rolling restart, controller failover và broker recovery.
8. Kiểm tra feature-level activation/downgrade path trong lab.
9. Diễn tập rollback hoặc forward-fix.
10. Ghi thời gian mỗi bước và điều kiện stop.

Staging chỉ hữu ích khi topology và workload đủ tương đồng. Một cluster nhỏ không thể xác nhận đầy đủ thời gian recovery hoặc network load của production.

## 12. Rolling upgrade: binary trước, feature sau

Quy trình tổng quát:

~~~mermaid
flowchart TD
    A[Inventory and supported path] --> B[Backup and restore test]
    B --> C[Pre-upgrade health gates]
    C --> D[Upgrade one controller/broker at a time]
    D --> E[Wait for quorum, ISR and traffic recovery]
    E --> F{All nodes on target binary?}
    F -->|No| D
    F -->|Yes| G[Validate clients, Connect and Streams]
    G --> H[Upgrade protocol/feature level]
    H --> I[Post-upgrade validation]
    I --> J[Close rollback window after approval]
~~~

Thứ tự controller-only nodes và broker nodes phải theo upgrade guide của đúng release. Với KRaft, duy trì quorum majority trong suốt rolling restart; không dừng nhiều voter cùng lúc đến mức mất quorum. Với combined broker/controller nodes, phải giữ cluster có đủ controller voters và data brokers khả dụng.

Một node mỗi lần là nguyên tắc an toàn chung, nhưng số node và sequence cụ thể phụ thuộc topology, quorum size và release procedure. Sau mỗi node:

- Chờ broker đăng ký lại và phục vụ request.
- Kiểm tra leader/ISR và URP.
- Kiểm tra controller quorum nếu node có vai trò controller.
- Kiểm tra producer/consumer errors và latency.
- Chỉ tiếp tục khi các guardrail đã phục hồi.

Không nâng feature level khi vẫn còn broker chạy binary cũ không hỗ trợ level đó.

## 13. Giữ feature level cũ trong rollback window

Sau khi toàn bộ binary đã nâng cấp, có thể tồn tại một giai đoạn cluster vẫn dùng feature level cũ. Đây là cửa sổ kiểm chứng trước khi bật tính năng metadata/protocol mới.

Trong cửa sổ này:

- Xác minh mọi broker/controller đang chạy target binary.
- Kiểm tra client, Connect, Streams và schema compatibility.
- Chạy production-like traffic.
- Theo dõi latency, throughput, ISR, quorum và consumer lag.
- Xác minh binary rollback có được release hỗ trợ khi feature level vẫn ở mức cũ.
- Chưa kích hoạt feature mới nếu quyết định rollback vẫn còn mở.

Khi owner chấp thuận, nâng feature level theo release guide. Ghi rõ thời điểm feature activation và ai phê duyệt; đó có thể là ranh giới đóng rollback window.

## 14. Stop conditions trong rolling upgrade

Dừng rollout và không nâng node tiếp theo nếu gặp một trong các tình huống:

| Tín hiệu | Hành động |
|---|---|
| KRaft quorum mất leader hoặc thiếu majority | Dừng rollout; khôi phục quorum |
| Offline partition xuất hiện | Dừng rollout; xác định data availability |
| URP tăng kéo dài hoặc ISR shrink liên tục | Dừng; khôi phục replica health |
| Broker không đăng ký lại | Giữ rollout; kiểm tra startup/log/config |
| Disk/log directory offline hoặc free space dưới ngưỡng | Dừng; xử lý storage |
| Producer error/timeout tăng vượt SLO | Dừng; kiểm tra request path và protocol |
| Consumer lag tăng nhanh | Dừng; kiểm tra rebalance/fetch/processing |
| Connect task hoặc Streams app fail | Dừng component rollout; kiểm tra compatibility/state |
| Authentication/ACL failure | Dừng; kiểm tra listener, principal mapping và ACL |
| Latency p99 hoặc resource vượt guardrail | Dừng; đánh giá tác động trước khi tiếp tục |

Không coi việc process đã start là tiêu chí đủ để nâng node kế tiếp.

## 15. Rollback matrix

| Trạng thái hiện tại | Binary rollback | Feature/protocol downgrade | Hướng xử lý |
|---|---|---|---|
| Chưa thay binary | Không cần | Không cần | Hủy change |
| Một vài node đã nâng, feature level cũ | Có thể nếu release hỗ trợ và data/metadata tương thích | Chưa thay đổi | Rollback node theo procedure đã thử |
| Tất cả node đã nâng, feature level cũ | Có thể nếu supported path cho phép | Không cần | Có thể rollback binary trong cửa sổ này |
| Feature level đã nâng | Không được giả định | Chỉ nếu release công bố downgrade và feature state cho phép | Thử downgrade trong lab; nếu không hỗ trợ thì forward-fix |
| Feature mới đã được sử dụng/metadata mới đã ghi | Có thể bị chặn | Có thể không hỗ trợ | Forward-fix hoặc restore từ backup tương thích |
| ZooKeeper-to-KRaft migration đã finalized | Không quay lại mode cũ theo giả định | Không áp dụng đơn giản | KRaft recovery/DR theo release |
| Retention/compaction đã xóa record | Binary rollback không phục hồi | Không phục hồi | Restore archive/backup hoặc replay source |
| Partition count đã tăng | Binary rollback không giảm count | Không liên quan | Tạo topic mới và migrate nếu bắt buộc |
| Schema mới đã được produce | Broker rollback không đổi payload | Không liên quan | Roll forward consumer hoặc migrate/rewrite dữ liệu |

Ma trận này là khung quyết định, không phải guarantee cho mọi cặp version. Release-specific downgrade matrix luôn có quyền ưu tiên.

## 16. Khi nào nên rollback, khi nào nên forward-fix?

### Rollback phù hợp khi

- Lỗi xuất hiện ngay sau binary upgrade.
- Release guide xác nhận binary rollback được hỗ trợ.
- Feature/protocol level chưa vượt giới hạn binary cũ.
- Metadata và record format vẫn tương thích.
- Có procedure đã diễn tập và health gate rõ ràng.

### Forward-fix phù hợp khi

- Feature level mới đã được kích hoạt và không có downgrade path.
- Metadata/log đã ghi theo format mà binary cũ không hỗ trợ.
- ZooKeeper-to-KRaft migration đã qua điểm finalize.
- Application đã phát schema/payload không tương thích với code cũ.
- Rollback làm mất quorum hoặc có nguy cơ corrupt metadata.

Forward-fix có thể là patch release, config correction, thay connector plugin hoặc sửa client. Nếu dữ liệu đã bị mất/corrupt, forward-fix phần mềm không đủ; cần data recovery.

## 17. Rollback broker binary theo từng node

Chỉ thực hiện khi release guide cho phép và feature level/data format còn tương thích.

Quy trình khái quát:

1. Dừng rollout và ghi lại broker/controller state.
2. Xác định node nào đã nâng và node nào chưa nâng.
3. Xác minh cluster feature/protocol level vẫn tương thích với bản cũ.
4. Xác minh log/metadata format chưa vượt giới hạn.
5. Chọn một node canary để rollback theo procedure của package/container.
6. Khởi động lại node và kiểm tra registration, partition leadership, ISR và quorum.
7. Chỉ rollback node tiếp theo sau khi node trước khỏe.
8. Xác minh producer/consumer, Connect/Streams và metrics.
9. Ghi lại binary, config và feature state sau rollback.

Không xóa log directory, metadata directory hoặc format lại volume khi rollback. Không copy thư mục dữ liệu của broker khác sang node lỗi để thay thế.

## 18. Rollback client và application

Client library có thể được nâng riêng với broker. Khi rollback producer/consumer:

- Kiểm tra client protocol/API tương thích với broker hiện tại.
- Kiểm tra producer có phát compression/record format mới không.
- Kiểm tra serializer/schema version.
- Kiểm tra consumer có thể đọc record đã được phiên bản mới ghi không.
- Kiểm tra offset commit và group protocol behavior.
- Kiểm tra transaction/idempotence semantics.

Với Kafka Streams:

- Kiểm tra application.id và state directory.
- Kiểm tra state store/changelog compatibility.
- Xác định có cần restore standby, rebuild state hoặc đổi application ID không.
- Không xóa changelog topic chỉ để app cũ khởi động.

Với Kafka Connect:

- Giữ connector config và source offsets.
- Xác minh plugin version và converter tương thích.
- Không reset source offsets như một cách rollback mặc định.
- Kiểm tra sink idempotence để tránh duplicate khi task restart.

## 19. Schema compatibility và expand-contract

Rollback ứng dụng thường thất bại vì producer mới đã phát payload mà consumer cũ không hiểu. Cần dùng chiến lược expand-contract:

1. Mở rộng schema theo hướng backward/forward compatible theo policy.
2. Nâng consumer để đọc được cả format cũ và mới.
3. Nâng producer để ghi field/format mới.
4. Chờ hết thời gian lưu dữ liệu cũ và xác minh toàn bộ consumer đã nâng.
5. Sau đó mới loại bỏ field/format cũ.

Schema Registry compatibility mode phải được chọn theo hướng deployment và loại serializer. Backward compatibility, forward compatibility và full compatibility có semantics khác nhau; không bật một mode chỉ vì tên nghe an toàn.

Nếu producer mới đã ghi dữ liệu không đọc được bởi consumer cũ, có thể phải forward-fix consumer hoặc chạy migration/rewrite có kiểm soát. Revert schema registration không tự sửa record đã nằm trong Kafka.

## 20. Partition count và các thay đổi không thể hoàn tác tại chỗ

Tăng partition count có thể thay đổi key-to-partition mapping. Kafka không hỗ trợ giảm partition count tại chỗ vì log và assignment đã được tạo cho partition đó.

Với partitioner mặc định dựa trên hash(key), tăng partition count có thể làm cùng một key được route sang partition khác cho record mới. Record cũ vẫn nằm ở partition cũ, nên ordering của aggregate có thể bị chia qua hai partition. Nếu topic có yêu cầu ordering theo key, phải xem việc tăng partition là thay đổi semantics và lập kế hoạch migration thay vì chỉ coi đó là mở rộng capacity.

Nếu cần giảm:

1. Tạo topic mới với partition count mục tiêu.
2. Xác định mapping key/partition và ordering requirement.
3. Replicate hoặc consume-transform-produce dữ liệu sang topic mới.
4. Dừng hoặc dual-write có kiểm soát để chốt cutover.
5. Translate consumer offsets bằng mapping riêng; không copy offset số học.
6. Chuyển producer/consumer sang topic mới.
7. Verify record count, event ID, ordering và lag.
8. Chỉ xóa topic cũ sau khi owner chấp thuận.

Tạo topic mới là migration, không phải rollback tự động. Cần capacity cho dữ liệu kép trong thời gian cutover.

## 21. Retention, compaction và delete là thay đổi dữ liệu

Giảm retention có thể làm segment hết hạn và bị xóa. Bật compaction có thể loại bỏ phiên bản cũ theo key. Xóa topic loại bỏ log của topic. Khi dữ liệu đã bị xóa, đổi cấu hình về giá trị cũ không khôi phục record.

Trước khi thay:

- Xác định retention/legal hold.
- Ước tính lượng segment có thể bị xóa.
- Kiểm tra compacted topic có cần full event history hay không.
- Export/archive dữ liệu nếu cần.
- Thử trên staging với dữ liệu đại diện.
- Theo dõi log start offset và segment deletion.

Không dùng retention hoặc compaction để rollback một migration ứng dụng. Nếu cần khôi phục, lấy dữ liệu từ backup/archive hoặc source of truth.

## 22. Metadata và storage format: không tự sửa filesystem

Kafka giữ log segment, index, checkpoint, metadata log và snapshot theo cấu trúc nội bộ. Các file này phụ thuộc version, configuration và broker identity.

Không:

- Xóa metadata log hoặc snapshot để ép broker khởi động.
- Copy metadata directory giữa controller không đúng quy trình.
- Trộn log directory của broker khác.
- Chạy formatter lên volume đang chứa dữ liệu.
- Chỉnh cluster ID hoặc node ID để né lỗi upgrade.
- Khởi động đồng thời binary mới/cũ ngoài ma trận hỗ trợ.

Nếu broker không start sau upgrade, giữ nguyên dữ liệu và thu thập startup log, config diff, feature state, quorum status. Dùng recovery procedure theo release; thao tác filesystem sai có thể biến lỗi có thể khôi phục thành mất dữ liệu.

## 23. Config drift và default thay đổi giữa phiên bản

Một cấu hình không khai báo có thể dùng default khác sau upgrade. Do đó rollback config không chỉ là copy file cũ; cần hiểu giá trị hiệu lực và dynamic overrides.

Ghi lại:

- server.properties hoặc cấu hình container.
- Dynamic broker configs ở cluster-default và per-broker scope.
- Topic-level overrides.
- Listener/SASL/TLS/principal mapping.
- Quota và ACL.
- JVM flags, GC, heap và environment.
- Log directory, rack, node ID và controller role.
- Connector/Streams application configs.

Sau upgrade, compare effective config với baseline. Không áp dụng toàn bộ config file cũ nếu một số property đã deprecated, removed hoặc đổi semantics.

## 24. Ví dụ kiểm tra trước và sau upgrade

### Kiểm tra broker API và version

~~~bash
kafka-broker-api-versions.sh \
  --bootstrap-server kafka-1:9092
~~~

Lệnh này giúp kiểm tra broker endpoint và API versions được quảng bá; không thay thế inventory/package verification.

### Kiểm tra topic/replica health

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe
~~~

### Kiểm tra consumer lag

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --all-groups
~~~

### Kiểm tra KRaft quorum và feature level

~~~bash
kafka-metadata-quorum.sh \
  --bootstrap-server kafka-1:9092 \
  describe \
  --status

kafka-features.sh \
  --bootstrap-server kafka-1:9092 \
  describe
~~~

Các lệnh này là ví dụ theo Kafka CLI hiện đại; option và khả năng có thể khác theo release/distribution. Dùng --help của đúng binary.

### Kiểm tra dynamic broker config

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type brokers \
  --entity-default \
  --describe \
  --all
~~~

Lưu output trước và sau upgrade để phát hiện config drift.

## 25. Post-upgrade validation

Không đóng change ngay khi tất cả broker process đã chạy phiên bản mới. Cần xác minh:

- Mọi broker/controller chạy đúng binary version và node role.
- KRaft quorum có leader, voter majority và metadata lag ổn định.
- Feature level đúng với kế hoạch; không tự nâng ngoài ý muốn.
- Offline partition bằng 0.
- URP bằng 0 hoặc đã trở lại baseline được chấp nhận.
- ISR ổn định.
- Producer success rate, retry và p99 latency trong SLO.
- Consumer lag, rebalance và commit errors ổn định.
- Connect connector/task và source offsets khỏe.
- Streams state store/changelog restore thành công.
- Schema Registry và serializer/deserializer hoạt động.
- Authentication, ACL, quotas và principal mapping đúng.
- JMX/Prometheus dashboards và alerts còn hoạt động.
- Backup/DR replication tiếp tục healthy.

Theo dõi ít nhất một chu kỳ peak workload hoặc thời gian đủ đại diện theo SLO. Một vài phút không có lỗi không chứng minh upgrade ổn định.

## 26. Rollback decision record

Mỗi upgrade production nên có một bảng quyết định trước khi thực hiện:

| Câu hỏi | Giá trị cần ghi |
|---|---|
| Source/target release | Version chính xác |
| Supported path | Release guide và bước trung gian |
| Current/target feature level | Metadata/protocol feature |
| Binary rollback supported? | Có/không và điều kiện |
| Feature downgrade supported? | Có/không và điều kiện |
| Non-reversible step | Bước nào đóng rollback window |
| Backup/restore | Vị trí, owner, lần restore test gần nhất |
| Stop conditions | URP, quorum, latency, lag, error |
| Rollback owner | Người ra quyết định và người thực hiện |
| Forward-fix owner | Người xử lý nếu downgrade không được hỗ trợ |
| RPO/RTO | Mức mất dữ liệu/thời gian phục hồi chấp nhận |
| Approval | Người duyệt feature activation/finalization |

Đừng để quyết định rollback tới lúc incident xảy ra mới tìm release notes hoặc xác định ai có quyền quyết định.

## 27. Bài thực hành trong lab

Tạo môi trường Kafka lab có broker/controller topology tương tự production:

1. Ghi broker version, client version, metadata.version và quorum status.
2. Export topic configs, ACL, quotas, consumer offsets và application configs.
3. Tạo workload producer/consumer và ghi baseline.
4. Nâng binary theo rolling procedure trong khi giữ feature level cũ.
5. Sau mỗi node, kiểm tra quorum, ISR, URP và latency.
6. Kiểm tra client/Connect/Streams compatibility.
7. Thử binary rollback trong cửa sổ được release hỗ trợ.
8. Nâng metadata feature level trong lab theo release guide.
9. Xác minh downgrade có được hỗ trợ cho level đó; không giả định lệnh thành công đồng nghĩa dữ liệu tương thích.
10. Thử application rollback với schema cũ/mới.
11. Tạo topic mới để mô phỏng migration khi partition count không thể giảm.
12. Thử restore từ backup/archive trên cluster cô lập.
13. Ghi thời gian, lỗi và điều kiện stop/rollback.

Không thử hạ metadata level, format lại data directory hoặc migration ZooKeeper/KRaft trên production để học quy trình.

## 28. Checklist production

### Trước upgrade

- Xác định supported upgrade path và version trung gian.
- Đọc release notes, deprecation và downgrade matrix.
- Inventory binary, client, Java, Connect, Streams, Schema Registry và plugin.
- Ghi metadata.version/IBP, KRaft quorum và controller layout.
- Export config, ACL, quota, topic metadata và offsets quan trọng.
- Kiểm thử backup/restore hoặc DR recovery.
- Xác minh offline partition bằng 0 và ISR ổn định.
- Kiểm tra disk, CPU, network, heap, GC và consumer lag.
- Canary/staging đã diễn tập.
- Ghi stop conditions, rollback owner và forward-fix owner.

### Trong upgrade

- Theo đúng sequence controller/broker của release.
- Nâng từng node và chờ health phục hồi.
- Duy trì KRaft quorum majority.
- Giữ feature/protocol level tương thích trong rolling phase.
- Theo dõi producer/consumer/Connect/Streams.
- Dừng rollout ngay khi stop condition xảy ra.
- Chưa kích hoạt feature mới trước khi binary rollout hoàn tất và được phê duyệt.

### Sau upgrade

- Xác minh mọi node và feature level.
- Kiểm tra partition/ISR, quorum, lag và error rate.
- Kiểm tra schema, connector, Streams state và security.
- Kiểm tra metrics, alert và backup/DR.
- Theo dõi peak workload.
- Ghi thời điểm đóng rollback window.
- Cập nhật runbook và inventory.

## 29. Những nhầm lẫn thường gặp

- **Rollback binary là đủ:** protocol, metadata, record format và application data có thể đã thay đổi.
- **Binary mới luôn tương thích ngược với binary cũ:** chỉ release support matrix mới xác định được.
- **metadata.version giống broker version:** đây là feature level của cluster, không phải tên release.
- **Có thể downgrade mọi feature level:** một số feature không hỗ trợ downgrade hoặc có điều kiện riêng.
- **ZooKeeper snapshot là rollback cho KRaft:** sau migration/finalization, recovery phải theo KRaft-aware procedure.
- **Đã start broker nghĩa là upgrade thành công:** phải kiểm tra quorum, ISR, traffic, clients và applications.
- **Revert retention khôi phục record:** segment đã bị xóa không tự xuất hiện lại.
- **Tắt compaction khôi phục lịch sử:** record cũ đã compact không tự được phục hồi.
- **Giảm partition count bằng config:** cần tạo topic mới và migrate.
- **Schema rollback chỉ cần revert registry:** record đã produce vẫn giữ payload/schema của phiên bản mới.
- **MirrorMaker là backup:** replication có thể truyền cả logical deletion/corruption.
- **Có thể sửa metadata directory để broker chạy lại:** thao tác filesystem sai có thể gây mất metadata hoặc log.
- **Rollback và restore là một việc:** rollback đổi phiên bản; restore khôi phục trạng thái dữ liệu/metadata.

Một kế hoạch nâng cấp an toàn phải xác định trước binary, protocol/feature và data compatibility. Giữ feature level cũ trong rolling phase tạo cửa sổ kiểm chứng, nhưng không bảo đảm mọi release đều cho phép rollback. Khi feature level, metadata format, KRaft migration, partition layout hoặc dữ liệu đã qua điểm không thể đảo ngược, cần forward-fix hoặc restore từ backup tương thích. Chỉ đóng change sau khi quorum, ISR, clients, Connect/Streams, schema, security và workload thực tế đều đạt guardrail.
