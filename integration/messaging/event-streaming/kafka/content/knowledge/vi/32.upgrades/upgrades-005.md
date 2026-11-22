# Rolling upgrade theo lộ trình hỗ trợ của từng phiên bản

Nâng cấp Kafka production cần giữ cluster hoạt động trong khi từng broker hoặc controller lần lượt chạy phiên bản phần mềm mới. Rolling upgrade giảm thời gian gián đoạn, nhưng chỉ an toàn khi phiên bản nguồn nằm trong upgrade path được hỗ trợ, các replica còn đủ khả năng phục vụ dữ liệu và cluster vượt qua health gate sau mỗi lần restart.

Một lần nâng cấp Kafka gồm nhiều lớp độc lập:

- **Binary version:** phiên bản Kafka server, broker, controller, Connect worker và thư viện client.
- **Protocol compatibility:** các API request/response mà broker và client có thể trao đổi trong giai đoạn chạy lẫn phiên bản.
- **Metadata/feature version:** mức tính năng mà cluster đã chốt trong metadata, được quản lý bằng kafka-features.sh ở các phiên bản KRaft hiện đại.
- **Runtime compatibility:** JDK, plugin, connector, Spring Kafka, Kafka Streams và thư viện tích hợp.
- **Operational state:** ISR, partition leader, controller quorum, disk, network, consumer lag và transaction coordinator.

Không nên gộp tất cả lớp này thành một thao tác đổi file binary. Với KRaft, việc nâng phần mềm và việc chốt feature version là hai bước khác nhau. Với cluster ZooKeeper, migration sang KRaft là một dự án riêng cần hoàn tất trước khi nâng lên Kafka 4.x.

## 1. Rolling upgrade là gì?

Rolling upgrade là quá trình cập nhật từng node trong cluster theo từng đợt nhỏ. Trong thời gian chuyển tiếp, cluster có thể chứa broker chạy phiên bản cũ và broker chạy phiên bản mới. Hai phía phải hỗ trợ giao tiếp tương thích trong giai đoạn đó.

Ví dụ cluster có ba broker:

~~~mermaid
flowchart TD
    A["Bắt đầu: broker-1, broker-2, broker-3 đều ở phiên bản cũ"] --> B["Nâng broker-1"]
    B --> C["Chờ broker-1 online và replica bắt kịp"]
    C --> D["Nâng broker-2"]
    D --> E["Chờ broker-2 online và replica bắt kịp"]
    E --> F["Nâng broker-3"]
    F --> G["Kiểm tra toàn cluster"]
    G --> H["Chốt metadata / feature version theo upgrade guide"]
    H --> I["Theo dõi sau nâng cấp"]
~~~

Trong mỗi bước, Kafka có thể chuyển partition leadership sang replica khác. Producer và consumer có thể gặp reconnect, retry hoặc rebalance. Client phải có retry policy và timeout phù hợp.

Rolling upgrade không phải cam kết zero downtime trong mọi cấu hình. Nếu topic có replication factor bằng 1, partition trên broker đang restart sẽ không có replica khác để phục vụ. Nếu min.insync.replicas quá cao so với số replica còn sống, producer dùng acks=all có thể nhận lỗi ghi. Nếu nhiều broker cùng restart, ISR có thể tụt dưới ngưỡng an toàn.

### 1.1. Điều kiện để rolling upgrade an toàn

- Các topic quan trọng có replication factor đủ lớn và replica phân bố qua fault domains.
- Không có offline partition.
- Under-replicated partition đã được xử lý trước maintenance.
- ISR đủ lớn để chịu được việc tạm dừng một broker.
- KRaft controller quorum khỏe và còn đa số controller hoạt động.
- Disk, CPU, RAM và network còn headroom để replica catch-up.
- Producer, consumer và ứng dụng chấp nhận reconnect/rebalance.
- Có rollback decision gate và kế hoạch phục hồi dữ liệu.
- Đã kiểm thử upgrade path trong staging với cấu hình gần production.

### 1.2. Phân biệt rolling restart và rolling upgrade

**Rolling restart** khởi động lại từng node nhưng giữ nguyên binary version. Thường dùng sau khi thay đổi cấu hình cần restart, JDK hoặc certificate.

**Rolling upgrade** thay đổi binary version và có thể thay đổi protocol/feature version sau đó. Nó cần kiểm tra compatibility, API removals, metadata migration và downgrade boundary.

Một rolling upgrade có thể gồm nhiều rolling restart, nhưng không nên xem chúng là cùng một thao tác.

## 2. Xác định upgrade path trước khi thay binary

Không phải phiên bản Kafka nào cũng có thể nâng trực tiếp lên mọi phiên bản mới. Upgrade path phải được kiểm tra trong trang Upgrading của phiên bản đích, release notes và compatibility matrix.

Tại thời điểm tài liệu Kafka 4.4.0 được công bố, hướng dẫn Apache Kafka 4.4 ghi nhận server upgrade trực tiếp từ các phiên bản 3.3.x đến 4.3.0. Kafka 4.x chỉ hỗ trợ KRaft; ZooKeeper mode đã bị loại bỏ.

| Phiên bản nguồn | Hướng đi khi mục tiêu là Kafka 4.4 |
|---|---|
| Kafka 4.3.0 | Có trong dải upgrade được tài liệu 4.4 nêu |
| Kafka 3.3.x đến 4.2.x | Có trong dải upgrade được tài liệu 4.4 nêu; kiểm tra đúng release note |
| KRaft cũ hơn 3.3.x | Nâng qua 3.9.x trước, sau đó theo lộ trình 4.x |
| ZooKeeper mode | Dùng Kafka 3.9 làm bridge release để migrate sang KRaft; hoàn tất migration rồi mới nâng lên 4.x |
| Kafka rất cũ hoặc không nằm trong dải được hỗ trợ | Xây dựng chuỗi intermediate upgrade theo tài liệu từng release; không tự nhảy thẳng phiên bản |

Bảng này là ví dụ theo mục tiêu 4.4. Khi mục tiêu thay đổi, hãy kiểm tra lại trang Upgrading của release đích. Không dùng bảng này làm quy tắc vĩnh viễn cho các phiên bản tương lai.

### 2.1. Vì sao cần bridge release?

Một phiên bản bridge có thể hỗ trợ cả định dạng metadata cũ lẫn mới, cho phép cluster hoàn tất một bước migration trước khi bỏ hẳn cơ chế cũ.

Với ZooKeeper-to-KRaft migration, Kafka 3.9 là bridge release cuối cùng được tài liệu KRaft hiện hành chỉ định. Migration thay đổi hệ thống lưu metadata của cluster; nó khác với nâng cấp binary. Không nên nâng binary và chuyển metadata mode trong cùng một thay đổi lớn nếu tài liệu không yêu cầu.

### 2.2. ZooKeeper phải được migrate trước Kafka 4.x

Kafka 4.0 trở đi không còn hỗ trợ ZooKeeper mode. Một cluster vẫn dùng zookeeper.connect không thể chỉ thay binary thành Kafka 4.x rồi khởi động.

Lộ trình tổng quát:

~~~mermaid
flowchart TD
    A["Kafka ZooKeeper mode"] --> B["Nâng lên bridge release Kafka 3.9"]
    B --> C["Thực hiện ZooKeeper to KRaft migration theo hướng dẫn 3.9"]
    C --> D["Kiểm tra controller quorum và broker ở KRaft"]
    D --> E["Hoàn tất migration và xác nhận không còn phụ thuộc ZooKeeper"]
    E --> F["Thực hiện rolling upgrade Kafka 4.x"]
    F --> G["Kiểm thử và chốt feature version"]
~~~

Các giai đoạn migration có thể bao gồm KRaft controller load metadata, hybrid phase, dual-write và finalization. Tên cấu hình, thứ tự restart và điều kiện hoàn tất phụ thuộc đúng release bridge. Phải dùng tài liệu migration của Kafka 3.9, không áp dụng một runbook cũ cho cluster khác phiên bản.

Sau khi migration được finalize, không thể đơn giản quay lại ZooKeeper mode. Hãy diễn tập migration và chuẩn bị backup/DR trước khi bắt đầu.

### 2.3. Không bỏ qua các release note trung gian

Nếu đi qua nhiều phiên bản, đọc release note của từng phiên bản trong chuỗi. Một thay đổi có thể bị deprecated ở release A và bị xóa ở release B. Nếu chỉ đọc release note của phiên bản đích, đội ngũ có thể bỏ lỡ bước chuyển đổi cần làm từ trước.

Tập trung vào:
- Broker configuration bị đổi tên hoặc xóa.
- Java API bị deprecated hoặc removed.
- Protocol/API version bị loại.
- Thay đổi metadata/feature version.
- Thay đổi group coordinator, transaction protocol hoặc Streams rebalance.
- Thay đổi JDK và logging framework.
- Thay đổi storage, KRaft quorum hoặc connector/plugin compatibility.

## 3. Binary version, protocol và metadata version

### 3.1. Binary version

Binary version là version của gói Kafka mà process đang chạy. Trong rolling upgrade, từng node được chuyển sang binary mới trong khi các node khác vẫn chạy binary cũ.

Ví dụ:
- Broker-1: 4.4.0
- Broker-2: 4.3.0
- Broker-3: 4.3.0

Đây là trạng thái chuyển tiếp. Không nên để cluster chạy lẫn phiên bản kéo dài ngoài khoảng thời gian được upgrade guide cho phép.

### 3.2. Protocol compatibility

Kafka client và broker giao tiếp qua request/response protocol. Trong giai đoạn rolling upgrade, broker mới phải tương tác được với broker cũ và client hiện tại theo các API version mà chúng cùng hỗ trợ.

Khi một phiên bản mới loại bỏ API version cũ, client quá cũ có thể không kết nối được. Vì vậy, compatibility matrix phải được kiểm tra cho cả:
- Java producer/consumer/AdminClient.
- Spring Kafka và Spring Boot.
- Kafka Connect worker và connector plugins.
- Kafka Streams application.
- MirrorMaker 2.
- Client không thuộc Apache Kafka như librdkafka hoặc connector thương mại.

### 3.3. Metadata version và feature version

Trong KRaft, metadata.version điều khiển định dạng metadata và feature level mà cluster sử dụng. kraft.version điều khiển các khả năng của KRaft quorum như static hoặc dynamic controller membership.

Các feature version được lưu trong metadata của cluster. Broker/controller mới có thể hỗ trợ feature level cao hơn nhưng cluster chưa nhất thiết đã kích hoạt level đó.

Dùng kafka-features.sh để quan sát:

~~~bash
bin/kafka-features.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  describe
~~~

Lệnh này cho biết feature, mức hỗ trợ và mức đã finalized. Với controller endpoint, có thể dùng --bootstrap-controller theo hướng dẫn của phiên bản.

### 3.4. Chốt feature version là bước riêng

Sau khi tất cả node đã chạy binary mới và cluster được kiểm tra ổn định, upgrade guide có thể yêu cầu chốt feature level bằng lệnh tương tự:

~~~bash
bin/kafka-features.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  upgrade \
  --release-version 4.4
~~~

Tên release version phải khớp với phiên bản đích và hướng dẫn chính thức của release đó. Không chạy lệnh này ngay sau khi thay binary đầu tiên.

--release-version nâng các feature version phù hợp mà cluster có thể hỗ trợ. Đây không phải lệnh cài binary. Khi metadata version được nâng, một số thay đổi metadata có thể khiến downgrade không còn được hỗ trợ.

### 3.5. Không sửa metadata version thủ công

Không sửa trực tiếp metadata log hoặc cố thay đổi metadata version bằng cách chỉnh file nội bộ. Hãy dùng công cụ chính thức và đúng quy trình.

Đối với cluster ZooKeeper đời cũ, inter.broker.protocol.version có thể xuất hiện trong upgrade procedure. Với KRaft hiện đại, metadata/feature version được quản lý qua kafka-features.sh. Không sao chép cấu hình của một release ZooKeeper cũ sang KRaft mới.

### 3.6. Static và dynamic KRaft controller quorum

Kafka 4.1 bổ sung khả năng chuyển KRaft controller quorum từ cấu hình static sang dynamic. Đây là một feature/configuration migration riêng, không chỉ là thay binary. Feature level kraft.version=1 cho phép quản lý membership controller linh hoạt hơn.

Trước khi nâng feature, kiểm tra trạng thái hiện tại:

~~~bash
bin/kafka-features.sh \
  --bootstrap-controller controller-1.example.com:9093 \
  describe
~~~

Nếu thiết kế yêu cầu dynamic quorum và release guide cho phép, nâng feature riêng:

~~~bash
bin/kafka-features.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  upgrade \
  --feature kraft.version=1
~~~

Sau khi feature đã được nâng, cập nhật cấu hình trên tất cả broker và controller: bỏ controller.quorum.voters và khai báo controller.quorum.bootstrap.servers với endpoint của các controller. Ví dụ:

~~~properties
process.roles=controller
node.id=1
controller.listener.names=CONTROLLER
controller.quorum.bootstrap.servers=controller-1.example.com:9093,controller-2.example.com:9093,controller-3.example.com:9093
~~~

Thực hiện config rollout theo hướng dẫn KRaft của đúng phiên bản, giữ controller quorum có đa số node hoạt động. Nếu không có nhu cầu chuyển sang dynamic quorum, không tự kích hoạt feature này chỉ vì binary mới hỗ trợ. Trước khi dùng upgrade --release-version, kiểm tra feature set mà lệnh sẽ finalize và xác định có cần migration cấu hình quorum đi kèm hay không.

## 4. Chuẩn bị trước khi nâng cấp

### 4.1. Lập inventory

Ghi lại:
- Kafka broker/controller version hiện tại.
- Kafka cluster ID và node ID.
- KRaft mode, controller quorum type và metadata/feature versions.
- JDK vendor/version.
- process.roles, listener, log directory và metadata log directory.
- Topic, partition, replication factor, min ISR và retention.
- Producer/consumer client versions.
- Spring Boot/Spring Kafka versions.
- Kafka Connect worker, connector plugin, converter và SMT versions.
- Kafka Streams application/library versions.
- TLS/SASL mechanism, certificate và ACL.
- Dynamic broker configs, quotas và custom plugin.
- Monitoring, alerting và automation.

Inventory giúp xác định cấu hình nào cần thay đổi do deprecation/removal và cho phép đối chiếu trước/sau upgrade.

### 4.2. Kiểm tra sức khỏe cluster

Ví dụ kiểm tra partition chưa đủ replica:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --describe \
  --under-replicated-partitions
~~~

Kiểm tra partition không có leader:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --describe \
  --unavailable-partitions
~~~

Kiểm tra metadata quorum:

~~~bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  describe \
  --status
~~~

Kiểm tra feature versions:

~~~bash
bin/kafka-features.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  describe
~~~

Cú pháp và công cụ có thể khác ở release cũ. Hãy chạy binary phù hợp với phiên bản hiện tại khi thực hiện preflight.

Không bắt đầu upgrade nếu:
- Có offline partition.
- ISR liên tục shrink/expand.
- Controller quorum mất ổn định.
- Broker đang mất log directory.
- Disk gần đầy hoặc replica catch-up quá chậm.
- Có reassignment hoặc maintenance lớn chưa hoàn tất.
- Producer/consumer đang có error rate cao không giải thích được.

### 4.3. Kiểm tra durability trước rolling restart

Ví dụ topic có replication factor 3 và min.insync.replicas=2, producer dùng acks=all. Khi một broker dừng, hai replica còn lại có thể vẫn đủ ISR để tiếp tục ghi.

Nếu replication factor 2 và min ISR 2, khi một replica dừng, producer acks=all có thể không ghi được. Đây có thể là chính sách durability mong muốn, nhưng đội vận hành phải dự kiến tác động trước maintenance.

Topic có replication factor 1 sẽ mất khả năng phục vụ khi broker chứa partition đó dừng. Rolling upgrade không thể che giấu giới hạn này.

### 4.4. Chuẩn bị backup và rollback

Lưu giữ:
- Bản cấu hình broker/controller.
- Topic configs, ACL, quotas và dynamic configs.
- Certificate, truststore, keystore và secret inventory.
- JDK, Kafka package và checksum.
- Operator/CRD manifests nếu chạy Kubernetes.
- Client dependency lockfile và connector plugin inventory.
- Metadata/feature version trước upgrade.
- Snapshot hoặc chiến lược phục hồi phù hợp với nền tảng.
- DR cluster và quy trình failover đã kiểm thử.

Không coi việc giữ lại thư mục binary cũ là một rollback plan đầy đủ. Sau khi metadata version hoặc data format đã thay đổi, binary cũ có thể không đọc được dữ liệu mới.

Không copy đè log directory đang hoạt động để tạo “backup nóng”. Dùng quy trình backup/restore hoặc replication được thiết kế cho Kafka.

### 4.5. Staging và rehearsal

Staging nên gần production về:
- Kafka version và KRaft topology.
- Topic count, partition count và replication factor.
- Security configuration.
- Producer/consumer client versions.
- Connector plugins và Streams applications.
- Disk type, network latency và CPU/RAM.
- Traffic pattern và message size.

Diễn tập đủ các bước: nâng client, rolling broker, controller restart, feature finalization, smoke test và rollback decision. Ghi lại thời gian từng bước để dự đoán maintenance window.

## 5. Compatibility của client và ứng dụng

### 5.1. Quy tắc client/broker

Không phải client library mới nhất luôn tương thích đầy đủ với mọi broker cũ. Đọc compatibility matrix cho cặp phiên bản cụ thể.

Một mốc quan trọng là Kafka 4.0:
- Protocol API versions trước 0.10.x đã bị loại bỏ.
- Client 0.x, 1.x và 2.0 không tương thích với broker 4.0.
- Client 2.1 đến 2.8 có compatibility một phần và giới hạn theo API.
- Client 3.x được liệt kê là tương thích đầy đủ với broker 4.0.
- Trước khi nâng client lên 4.0, broker cần đạt tối thiểu 2.1 theo upgrade guide.
- Trước khi nâng broker lên 4.0, client Apache Kafka cần từ 2.1 trở lên.

Đây là ví dụ cụ thể cho Kafka 4.0. Với release đích khác, kiểm tra compatibility matrix hiện hành thay vì suy rộng mọi con số.

### 5.2. JDK

Kafka 4.0 đã bỏ Java 8. Broker và Kafka Connect yêu cầu Java 17 trở lên; client và Kafka Streams có mức yêu cầu riêng theo module. Kafka 4.4 có ma trận JDK riêng và có thể khác release cũ.

Trước khi nâng JDK:
1. Kiểm tra JDK được Kafka server đích hỗ trợ.
2. Kiểm tra JDK của Spring Boot/Spring Kafka application.
3. Kiểm tra connector plugin và thư viện native.
4. Kiểm tra TLS provider, GC flags và logging.
5. Chạy staging với cùng JDK vendor/version.

Không nâng Kafka, JDK, Spring Boot và connector plugin cùng một lúc nếu không có lý do bắt buộc.

### 5.3. Spring Kafka và Spring Boot

Spring Kafka sử dụng Kafka Java client bên dưới. Cần kiểm tra:
- Spring Boot BOM quản lý phiên bản Spring Kafka nào.
- Spring Kafka version đó kéo theo kafka-clients version nào.
- Client API đã bị loại bỏ ở Kafka 4.0 có còn được ứng dụng gọi không.
- Error handler, retry topic, DLT, transaction và observation có thay đổi behavior không.
- Serializer/deserializer và custom partitioner có dùng API deprecated không.

Không chỉ đổi kafka-clients độc lập nếu Spring Boot quản lý dependency qua BOM. Kiểm tra dependency tree và dùng version matrix chính thức của Spring Boot/Spring Kafka.

### 5.4. Kafka Streams

Kafka Streams có upgrade guide riêng. Kiểm tra:
- Streams API version và broker compatibility.
- State store format, changelog và repartition topics.
- Application ID và topology compatibility.
- Custom processor, serializer/deserializer và state store plugin.
- Rebalance protocol và consumer group protocol.
- Exactly-once processing và transaction coordinator behavior.
- Thời gian restore state sau rolling restart.

Kafka Streams app có thể cần thay đổi code do API bị xóa, kể cả khi broker upgrade thành công. Với topology có state lớn, cần đo thời gian restore và đảm bảo không làm downstream mất freshness quá lâu.

Kafka 4.4 có một điểm cần chú ý: static membership qua group.instance.id khi dùng group.protocol=streams yêu cầu cả broker và client chạy 4.4 trở lên. Broker cũ hơn 4.4 sẽ từ chối heartbeat và Kafka Streams client có thể shutdown. Nếu cần downgrade broker xuống dưới 4.4, phải bỏ group.instance.id khỏi các app dùng Streams protocol và restart các app trước khi downgrade.

### 5.5. Kafka Connect

Connect worker là Kafka client và cần tương thích với broker. Kiểm tra:
- Worker version và Kafka client library.
- Connector plugin version.
- Converter và Schema Registry client.
- SMT và custom plugin.
- Internal topics: config, offset và status.
- Connector task state và restart behavior.
- Secret provider và callback handler.
- Distributed worker rebalance.

Nâng broker không tự nâng connector plugin. Nâng Connect worker có thể làm task restart hoặc rebalance. Thực hiện theo từng worker và kiểm tra connector/task state trước khi tiếp tục.

## 6. Rolling upgrade broker theo từng node

Quy trình sau là khung vận hành. Thứ tự chi tiết và health gate phải tuân theo upgrade guide của source/target version.

### 6.1. Trước node đầu tiên

1. Xác nhận upgrade path được hỗ trợ.
2. Hoàn tất client compatibility remediation.
3. Kiểm tra cluster health và controller quorum.
4. Xác nhận backup/DR và rollback boundary.
5. Chuẩn bị binary, JDK và cấu hình đã review.
6. Xác nhận log directory và metadata log directory được giữ nguyên.
7. Thông báo maintenance window và owner.
8. Bắt đầu với một broker ít rủi ro theo kế hoạch.

### 6.2. Nâng một broker

Với mỗi broker:

1. Chuyển leadership hoặc để Kafka thực hiện controlled shutdown theo runbook của nền tảng.
2. Dừng broker một cách có kiểm soát.
3. Cài hoặc chuyển sang binary version đích.
4. Giữ đúng cấu hình, node.id, cluster.id, log directories, metadata log directory và security material.
5. Khởi động broker với JDK và binary mới.
6. Chờ broker đăng ký lại và trở về trạng thái phục vụ request.
7. Kiểm tra log startup, controller connection và authentication.
8. Chờ replica catch-up; xác nhận ISR trở lại mức bình thường.
9. Kiểm tra Produce/Fetch latency, request errors, disk và network.
10. Chỉ chuyển sang broker tiếp theo khi health gate đạt.

Không nâng đồng thời nhiều broker thuộc cùng cluster nếu tài liệu hoặc thiết kế không cho phép. Không để một partition mất tất cả replica đang ISR trong lúc thao tác.

### 6.3. KRaft controller nodes

Với dedicated controller quorum:
- Controller là thành viên của metadata quorum, không phải broker phục vụ record traffic.
- Quorum cần đa số controller hoạt động để tiếp tục xử lý metadata.
- Với ba controller, chỉ một controller có thể tạm dừng mà vẫn giữ đa số.
- Nâng từng controller theo thứ tự trong upgrade guide, chờ node quay lại và quorum ổn định trước khi tiếp tục.
- Không restart đồng thời hai trong ba controller.
- Kiểm tra active controller, metadata log replication và quorum health sau mỗi bước.

Với combined mode (process.roles=broker,controller), broker và controller cùng nằm trong một process nên không thể nâng controller tách biệt với broker. Kafka khuyến nghị combined mode cho môi trường nhỏ/dev; production quan trọng nên cân nhắc tách role để vận hành độc lập.

### 6.4. Health gate sau mỗi broker

| Tín hiệu | Điều kiện tiếp tục |
|---|---|
| Broker availability | Node online và nhận request |
| Offline partitions | Không tăng, mục tiêu bằng 0 |
| Under-replicated partitions | Trở về baseline/0 trước node tiếp theo |
| ISR | Replica bắt kịp, không shrink liên tục |
| KRaft quorum | Có leader, metadata lag ổn định |
| Produce/Fetch | Error rate và latency trong ngưỡng |
| Consumer | Lag không tăng bất thường, rebalance hoàn tất |
| Storage | Log directory online, disk latency ổn định |
| JVM | GC, heap và thread ổn định |
| Security | TLS/SASL/ACL hoạt động |
| Connect/Streams | Worker, connector task và Streams app khỏe |

Nếu health gate không đạt, dừng rollout và điều tra. Không tiếp tục chỉ vì broker process đã chạy.

## 7. Chốt feature version sau khi toàn cluster đã nâng binary

Khi tất cả broker/controller đã chạy binary đích:
1. Xác minh cluster health.
2. Kiểm tra feature versions bằng kafka-features.sh describe.
3. Kiểm tra release notes và feature nào sẽ được bật.
4. Xác nhận ứng dụng/client đã sẵn sàng với behavior mới.
5. Chạy lệnh feature upgrade theo đúng phiên bản đích.
6. Đọc lại feature versions và theo dõi cluster.

Ví dụ cho Kafka 4.4:

~~~bash
bin/kafka-features.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  upgrade \
  --release-version 4.4
~~~

Lệnh trên là bước chốt feature level, không phải thay binary. Chỉ chạy sau khi hoàn tất rolling upgrade và validation theo hướng dẫn release.

Không kích hoạt một feature riêng lẻ chỉ vì thấy nó được hỗ trợ. Feature như dynamic controller membership, Streams rebalance protocol hoặc share groups có thể yêu cầu client upgrade, config migration và quy trình riêng.

## 8. Các thay đổi cần chú ý khi nâng lên Kafka 4.x và 4.4

### 8.1. Kafka 4.0 loại bỏ ZooKeeper mode

Kafka 4.x chỉ chạy KRaft. Nếu cluster đang dùng ZooKeeper, phải migrate sang KRaft trước. Các cấu hình zookeeper.connect và nhiều ZooKeeper-specific properties không còn dùng trong KRaft.

### 8.2. API và config bị loại bỏ

Kafka 4.0 loại bỏ nhiều API đã deprecated:
- log.message.format.version và message.format.version.
- Một số producer partitioner class cũ.
- Một số AdminClient API cũ.
- Các class/tool cũ thuộc Kafka package.
- Các API Streams đã deprecated từ trước.

Hãy compile và test ứng dụng với Kafka client version đích. Một ứng dụng có thể chạy với broker mới nhưng không compile do Java API đã bị xóa.

### 8.3. Kafka 4.4 thay đổi liên quan OAuthBearer

Nếu broker dùng OAuthBearer JWT validator và cấu hình JWKS endpoint, Kafka 4.4 yêu cầu sasl.oauthbearer.expected.audience và sasl.oauthbearer.expected.issuer. Broker có thể fail startup nếu thiếu các giá trị này.

Trước khi rolling restart:
- Kiểm tra listener đang bật OAUTHBEARER.
- Kiểm tra JWKS endpoint và issuer.
- Cấu hình expected audience/issuer đúng với token thực tế.
- Kiểm tra staging với token hợp lệ và token sai audience.
- Không bật allow-unverified để né lỗi cấu hình trong production.

### 8.4. Storage directory và kafka-storage tool ở Kafka 4.4

Kafka 4.4 thay đổi quy tắc tương thích của storage directory được format bằng kafka-storage tool. Broker phải cùng phiên bản hoặc mới hơn phiên bản của tool đã format directory, bất kể giá trị --release-version.

Vì vậy:
- Không chạy kafka-storage.sh format trên log directory đang có dữ liệu như một bước thông thường của rolling upgrade.
- Không dùng kafka-storage.sh từ binary mới để format directory mà sau đó định chạy bằng broker cũ.
- Giữ nguyên cluster ID, node ID và metadata/log directory hiện có.
- Chỉ format storage cho node mới hoặc cluster mới theo đúng hướng dẫn provisioning của phiên bản.
- Kiểm tra tool version và broker version trước khi thêm node vào cluster.

Đây là điểm đặc biệt quan trọng khi dùng automation tự động format volume lúc Pod khởi động.

### 8.5. Các thay đổi Kafka 4.4 khác

| Thay đổi | Việc cần làm |
|---|---|
| broker.id deprecated | Ưu tiên node.id trong cấu hình KRaft và automation |
| kafka-broker-api-versions.sh deprecated | Dùng kafka-cluster.sh api-versions |
| Streams static membership với group.protocol=streams yêu cầu broker/client 4.4+ | Kiểm tra group.instance.id và version đồng bộ |
| Controller unregister cần metadata version 4.4-IV2 | Chỉ dùng khi thực sự quản lý membership và đã hiểu feature level |
| Connect internal topic auto-creation có cấu hình mới | Kiểm tra cách provisioning internal topics của worker |

Không cần bật mọi tính năng mới trong cùng đợt nâng cấp. Trước hết đạt trạng thái binary ổn định, sau đó lập change riêng cho tính năng cần sử dụng.

## 9. Nâng cấp trong Kubernetes hoặc dùng operator

Khi Kafka chạy qua operator, quy trình có thêm lớp version compatibility của Kubernetes, operator và CRD.

Trước khi thay Kafka version:
- Kiểm tra operator hỗ trợ source và target Kafka versions.
- Kiểm tra CRD schema và upgrade path của operator.
- Đọc tài liệu về rolling update và controller/broker role.
- Xác nhận PodDisruptionBudget, anti-affinity và topology spread.
- Kiểm tra PVC, storage class và volume mount.
- Kiểm tra operator có tự thay image khi sửa Kafka CR hay không.
- Kiểm tra thay đổi có gây rolling restart hay yêu cầu migration không.

Một quy trình chung:
1. Nâng operator/CRD trước hoặc sau theo đúng compatibility matrix.
2. Chờ operator reconcile ổn định.
3. Thay Kafka version trong CR hoặc cấu hình mà operator quản lý.
4. Theo dõi từng broker/controller Pod.
5. Kiểm tra ISR và KRaft quorum sau mỗi node.
6. Chỉ chốt feature version khi cluster đã chạy binary đích và operator hỗ trợ bước đó.
7. Kiểm tra operator status và Kafka metrics.

Không tự sửa StatefulSet/Pod do operator quản lý nếu không có hướng dẫn. Operator có thể reconcile và ghi đè thay đổi. Không xóa PVC để ép node khởi tạo lại trong lúc upgrade.

## 10. Nâng cấp trên managed Kafka service

Với managed service, provider có thể thực hiện broker rolling upgrade theo maintenance window hoặc yêu cầu khách hàng chọn version. Người dùng vẫn phải chuẩn bị ứng dụng.

Kiểm tra:
- Version đích và source version được hỗ trợ.
- Provider có hỗ trợ upgrade trực tiếp hay yêu cầu intermediate version.
- Maintenance window và thời gian dự kiến.
- Broker connection reset, leader movement và client retry.
- API/config bị giới hạn hoặc khác Apache Kafka.
- Quota, partition count và storage capacity.
- Client compatibility, Connect/Streams compatibility.
- SLA, support escalation và rollback policy.
- Có thể downgrade hay phải restore sang cluster mới.

Không giả định managed service cho phép dùng kafka-features.sh hoặc truy cập controller. Dùng quy trình và công cụ của nhà cung cấp.

## 11. Rollback và ranh giới không thể quay lại

Rollback binary chỉ an toàn khi:
- Phiên bản cũ vẫn tương thích với metadata version hiện tại.
- Không có metadata change mà binary cũ không đọc được.
- Không kích hoạt feature mới chỉ có ở phiên bản đích.
- Storage directory chưa được format bởi tool mới theo cách không tương thích.
- Các client/app chưa phụ thuộc behavior mới.
- Release guide xác nhận downgrade path được hỗ trợ.

Sau khi chốt metadata version có metadata changes, downgrade có thể không được hỗ trợ. Kafka 4.0 và 4.3 có ghi chú metadata downgrade không được hỗ trợ trong các release có metadata changes. Với 4.4, phải kiểm tra release note và metadata version cụ thể trước khi quyết định.

### 11.1. Khi nào dừng và rollback?

Có thể cân nhắc rollback binary nếu:
- Broker mới liên tục crash hoặc không join cluster.
- Controller quorum không ổn định.
- ISR giảm không hồi phục.
- Request error/latency vượt ngưỡng và không thể khắc phục trong maintenance window.
- Client không tương thích hoặc connector/Streams không hoạt động.
- Có regression dữ liệu hoặc transaction.

Trước khi rollback, kiểm tra metadata version và feature level. Không hạ binary nếu release guide không cho phép.

### 11.2. Khi không thể downgrade

Nếu metadata hoặc storage đã thay đổi không tương thích, phương án phục hồi có thể là:
- Sửa lỗi tiến về phía trước bằng patch release.
- Khôi phục từ backup hợp lệ.
- Chuyển traffic sang DR cluster.
- Dựng cluster mới ở phiên bản phù hợp và migrate dữ liệu bằng replication.
- Chấp nhận downtime có kiểm soát theo RTO đã định.

Không xóa log directory hoặc format lại volume để ép broker cũ chạy. Việc đó có thể làm mất dữ liệu.

### 11.3. Rollback decision gate

| Thời điểm | Khả năng rollback |
|---|---|
| Trước khi dừng node đầu tiên | Trở về trạng thái ban đầu |
| Đang rolling binary, metadata chưa nâng | Có thể có đường quay lại nếu compatibility cho phép |
| Tất cả binary mới, chưa chốt feature | Có thể có đường rollback, cần kiểm tra từng release |
| Sau khi chốt metadata/feature version | Có thể không downgrade được |
| Sau khi dùng feature mới hoặc thay storage format | Phải kiểm tra rõ khả năng tương thích; không giả định downgrade |

Bảng này là khung ra quyết định, không thay thế downgrade guide của release cụ thể.

## 12. Kiểm thử sau upgrade

### 12.1. Broker và replication

- Tất cả broker/controller online.
- KRaft quorum có leader và metadata replication ổn định.
- Không có offline partition.
- Under-replicated partition trở về baseline.
- ISR ổn định.
- Leader distribution hợp lý.
- Disk log directory và metadata directory online.

### 12.2. Producer và consumer

- Producer gửi record với key và value serializer thực tế.
- Producer acks, idempotence và retry behavior đúng.
- Consumer đọc đúng topic/partition và commit offset.
- Consumer group rebalance hoàn tất.
- Consumer lag không tăng bất thường.
- Retry topic và dead-letter topic hoạt động.
- Transactional producer commit/abort hoạt động theo kỳ vọng.
- Ordering trong partition vẫn được giữ theo key/partitioning strategy.

### 12.3. Connect và Streams

- Connect worker REST API healthy.
- Connector/task state RUNNING.
- Converter, SMT và plugin load thành công.
- Internal topics có replication factor và ACL đúng.
- Streams app restore state thành công.
- Changelog/repartition topics hoạt động.
- Rebalance và processing guarantee không thay đổi ngoài dự kiến.

### 12.4. Security và observability

- TLS handshake và hostname verification thành công.
- SASL mechanism và credential hoạt động.
- ACL cho topic, group và transactional ID đúng.
- Quota và audit log vẫn có hiệu lực.
- Metrics/JMX exporter tương thích.
- Alert broker down, ISR shrink, offline partition và consumer lag hoạt động.
- Log format và logging configuration không bị mất sau nâng cấp.

## 13. Theo dõi trong và sau maintenance

Theo dõi dashboard theo timeline của từng broker:
- Broker up/down và startup duration.
- Controller leader/quorum status.
- Offline và under-replicated partitions.
- ISR shrink/expand.
- Produce/Fetch request latency và error rate.
- Request handler idle, network processor và connection count.
- Disk latency, free space, log directory failures.
- JVM heap, GC pause, thread count và CPU.
- Consumer lag, rebalance count và commit failures.
- Transaction coordinator errors.
- Connect task failures và Streams restore/rebalance.
- Authentication/authorization failures.

So sánh với baseline trước upgrade. Một cluster có thể online nhưng vẫn bị suy giảm throughput, p99 latency hoặc consumer freshness.

Giữ thời gian theo dõi đủ dài để quan sát:
- Peak traffic.
- Retention/compaction cycle.
- Consumer replay.
- Transaction timeout.
- Scheduled connector tasks.
- Backup và batch job.

Không kết thúc maintenance chỉ vì health check ngay sau restart đã xanh.

## 14. Ví dụ runbook nâng Kafka 3.9 KRaft lên 4.4

Ví dụ này minh họa cluster đã ở KRaft, nằm trong dải version được tài liệu Kafka 4.4 hỗ trợ và đã kiểm tra compatibility. Nó không thay thế upgrade guide cụ thể của release đang chạy.

### Giai đoạn A — Preflight

1. Xác nhận broker và metadata version hiện tại.
2. Kiểm tra controller quorum và partition health.
3. Xác nhận client/Connect/Streams versions đáp ứng yêu cầu.
4. Kiểm tra JDK và cấu hình đã bị deprecated.
5. Kiểm tra OAuth expected issuer/audience nếu có JWKS.
6. Kiểm tra node.id, storage directories và automation format.
7. Xác nhận backup/DR và rollback decision gate.
8. Chạy staging upgrade và workload smoke test.

### Giai đoạn B — Rolling binary

1. Nâng một broker theo đúng quy trình triển khai.
2. Chờ broker online, replica catch-up và ISR bình thường.
3. Kiểm tra produce/fetch, request latency và logs.
4. Tiếp tục broker kế tiếp.
5. Nâng các dedicated controller từng node theo thứ tự tài liệu, giữ đa số quorum.
6. Với combined nodes, coi mỗi node là cả broker lẫn controller và duy trì quorum/ISR trong suốt rollout.
7. Dừng rollout nếu bất kỳ health gate nào thất bại.

### Giai đoạn C — Validation và feature finalization

1. Xác nhận mọi node chạy binary 4.4.
2. Kiểm tra kafka-features.sh describe.
3. Kiểm thử producer/consumer/transaction.
4. Kiểm tra Connect và Streams.
5. Kiểm tra security và metrics.
6. Chạy feature upgrade theo release guide.
7. Đọc lại feature versions và theo dõi sau maintenance.

### Giai đoạn D — Kết thúc

- Lưu version inventory và kết quả validation.
- Cập nhật runbook và rollback boundary.
- Ghi lại deprecated config/API cần xử lý ở release sau.
- Theo dõi latency, throughput, consumer lag và error rate.
- Chỉ đóng maintenance khi toàn bộ owner xác nhận.

## 15. Anti-pattern thường gặp

- **Nhảy qua version không được hỗ trợ:** cluster có thể không đọc được metadata hoặc protocol mới.
- **Nâng ZooKeeper cluster thẳng lên Kafka 4.x:** Kafka 4.x không còn ZooKeeper mode.
- **Migration KRaft và software upgrade cùng lúc:** khó xác định lỗi thuộc metadata migration hay binary.
- **Nâng nhiều broker đồng thời:** làm ISR và availability giảm ngoài dự kiến.
- **Bỏ qua controller quorum:** broker có thể online nhưng cluster không thể commit metadata.
- **Chốt feature version trước khi validation:** có thể đóng mất đường downgrade.
- **Nghĩ giữ binary cũ là đủ rollback:** metadata/storage có thể không tương thích.
- **Format lại log directory trong rolling upgrade:** có thể làm mất dữ liệu hoặc tạo cluster identity sai.
- **Dùng kafka-storage.sh mới để format volume cho broker cũ:** vi phạm quy tắc tương thích storage tool của Kafka 4.4.
- **Bỏ qua client compatibility:** broker nâng xong nhưng Spring Kafka, Connect hoặc Streams client fail.
- **Không test transaction:** producer thường có thể chạy nhưng transactional flow có thể lỗi.
- **Chỉ kiểm tra broker process:** không phát hiện ISR, latency, consumer lag hoặc Connect task failure.
- **Đổi JDK, Kafka, Spring Boot và connector cùng một đợt:** khó cô lập nguyên nhân regression.
- **Không có health gate:** rollout tiếp tục dù node trước chưa ổn định.

## 16. Production checklist

### Upgrade path và compatibility
- [ ] Source/target version nằm trong upgrade path được hỗ trợ.
- [ ] Đã đọc release notes của các phiên bản trung gian.
- [ ] ZooKeeper cluster đã migrate sang KRaft nếu target là Kafka 4.x.
- [ ] Kafka client, Spring Kafka, Connect, Streams và plugin đã được kiểm tra compatibility.
- [ ] JDK target nằm trong ma trận hỗ trợ.

### Cluster health
- [ ] Không có offline partition.
- [ ] Under-replicated partition đã được xử lý.
- [ ] ISR đủ chịu rolling restart.
- [ ] KRaft quorum ổn định.
- [ ] Disk/CPU/RAM/network có headroom.
- [ ] Không có reassignment hoặc incident chưa hoàn tất.

### Thực hiện
- [ ] Binary và checksum đã được xác minh.
- [ ] Config diff đã được review.
- [ ] Log directory, metadata directory, cluster ID và node ID được giữ nguyên.
- [ ] Mỗi broker được nâng từng node.
- [ ] Dedicated controllers được nâng từng node và giữ quorum majority.
- [ ] Health gate PASS trước node tiếp theo.
- [ ] Storage format tool được dùng đúng version và đúng mục đích.

### Feature và rollback
- [ ] Feature versions đã được ghi nhận trước upgrade.
- [ ] Chỉ chốt feature version sau validation.
- [ ] Downgrade boundary được xác định theo metadata changes.
- [ ] Không giả định binary rollback luôn khả thi.
- [ ] DR/backup và phương án forward recovery đã được kiểm tra.

### Sau upgrade
- [ ] Produce/Fetch smoke test thành công.
- [ ] Consumer group, retry, DLT và transaction hoạt động.
- [ ] Connect tasks và Streams state restore hoạt động.
- [ ] TLS/SASL/ACL/quota hoạt động.
- [ ] Metrics và alerts hoạt động.
- [ ] Latency, throughput, consumer lag và ISR ổn định qua peak traffic.
- [ ] Runbook và inventory đã được cập nhật.

## 17. Kết luận

Rolling upgrade giúp nâng Kafka mà không cần dừng toàn bộ cluster, nhưng chỉ an toàn khi đi đúng upgrade path, giữ đủ replica và controller quorum, kiểm tra client compatibility và nâng từng node qua health gate.

Với KRaft, hãy phân biệt binary version với metadata/feature version. Nâng binary trước, kiểm chứng hành vi, rồi mới chốt feature level theo hướng dẫn release. Với ZooKeeper, hoàn tất migration sang KRaft trên bridge release trước khi nâng lên Kafka 4.x. Không xem downgrade là điều hiển nhiên sau khi metadata hoặc storage đã thay đổi.

Hãy diễn tập trên staging, chuẩn bị client và ứng dụng, theo dõi ISR/latency/consumer lag, kiểm tra Connect/Streams/transaction và ghi rõ rollback boundary. Một lần nâng cấp chỉ hoàn tất khi dữ liệu, ứng dụng và vận hành đều ổn định sau maintenance.

## Tài liệu tham khảo

- Apache Kafka 4.4 — Upgrading: https://kafka.apache.org/44/getting-started/upgrade/
- Apache Kafka 4.4 — Compatibility: https://kafka.apache.org/44/getting-started/compatibility/
- Apache Kafka 4.4 — KRaft operations and upgrades: https://kafka.apache.org/44/operations/kraft/
- Apache Kafka 4.4 — ZooKeeper to KRaft migration overview: https://kafka.apache.org/44/getting-started/zk2kraft/
- Apache Kafka 4.4 — Kafka Streams Upgrade Guide: https://kafka.apache.org/44/streams/upgrade-guide/
- Apache Kafka 3.9 — Upgrade and ZooKeeper to KRaft migration bridge release: https://kafka.apache.org/39/getting-started/upgrade/
