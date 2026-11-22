# Phân biệt phiên bản phần mềm với metadata.version và feature level

Khi nâng cấp Apache Kafka, có ba khái niệm rất dễ bị gọi chung là “version”: phiên bản phần mềm đang chạy trên broker/controller/client, phiên bản metadata của cluster và feature level của từng tính năng. Chúng có quan hệ với nhau nhưng không phải một giá trị.

Một cluster có thể đã chạy binary Kafka 4.4.0 trên tất cả broker nhưng vẫn giữ `metadata.version` ở mức 4.3. Khi đó binary mới đã được cài đặt, nhưng cluster chưa được phép sử dụng các thay đổi metadata mới của 4.4. Ngược lại, một feature riêng như `kraft.version` hoặc `share.version` có thể được nâng cấp độc lập theo điều kiện tương thích của nó.

Hiểu đúng ba lớp này giúp vận hành rolling upgrade an toàn, biết lúc nào còn cửa sổ rollback và tránh kích hoạt thay đổi metadata trước khi toàn bộ cluster sẵn sàng.

## 1. Mục tiêu bài học

Sau bài học, người học có thể:

- Phân biệt Kafka software release, `metadata.version`, feature level và API version.
- Giải thích tại sao binary đã nâng cấp nhưng metadata version vẫn có thể giữ ở mức cũ.
- Đọc `SupportedMinVersion`, `SupportedMaxVersion`, `FinalizedVersionLevel` và `Epoch` từ `kafka-features.sh describe`.
- Dùng `version-mapping` để xem feature levels tương ứng với một Kafka release.
- Phân biệt `metadata.version` với các feature độc lập như `kraft.version`, `group.version`, `streams.version` và `share.version`.
- Thực hiện quy trình nâng cấp software trước, xác minh tương thích rồi mới finalize feature levels.
- Đánh giá giới hạn rollback khi metadata đã thay đổi.
- Nhận biết các ràng buộc của KRaft và các yêu cầu nâng cấp trong Kafka 4.x.

## 2. Ba lớp version cần phân biệt

### 2.1. Kafka software version

Software version là phiên bản binary được cài đặt và chạy trên từng thành phần:

- Broker.
- KRaft controller.
- Kafka Connect worker.
- Kafka Streams application.
- Producer/consumer client library.
- Công cụ quản trị và thư viện tích hợp.

Ví dụ:

~~~text
Kafka broker: 4.4.0
KRaft controller: 4.4.0
Kafka Connect worker: 4.3.0
Spring Kafka application: đang dùng Kafka client 3.x
~~~

Các thành phần không nhất thiết phải được nâng cấp cùng một thời điểm. Trong rolling upgrade, cluster có thể tạm thời chạy nhiều software version trên các node khác nhau nếu phiên bản đích và nguồn nằm trong phạm vi tương thích được tài liệu Kafka hỗ trợ.

Software version quyết định:

- Code và bug fixes có trong binary.
- Những feature levels mà node có thể hỗ trợ.
- Những Kafka API versions mà node có thể phục vụ.
- Các cấu hình, thư viện và công cụ có sẵn.
- Khả năng đọc/ghi metadata và record theo những mức mà binary hỗ trợ.

Cài binary mới không tự động có nghĩa cluster đã bật mọi tính năng mới của release đó.

### 2.2. Metadata version

`metadata.version` là feature version cấp cluster dùng trong KRaft để điều khiển các thay đổi liên quan đến metadata record format và những RPC/semantics cần phối hợp giữa các node.

Metadata của Kafka bao gồm thông tin như:

- Topic và partition.
- Replica assignment và leader.
- Broker/controller registration.
- Cấu hình tài nguyên được lưu trong cluster metadata.
- Các record điều khiển trạng thái cluster.

Mỗi metadata version được đặt tên theo release và inter-version revision, ví dụ:

~~~text
3.9-IV0
4.0-IV1
4.4-IV2
~~~

`IV0`, `IV1`, `IV2` là các revision metadata trong một release line. Một release có thể có nhiều metadata version nếu có thay đổi metadata qua các lần phát hành.

Metadata version cũng có feature level dạng số. Trong mã nguồn Kafka 4.4, `4.4-IV2` tương ứng feature level `33`:

~~~text
metadata.version = 4.4-IV2
feature level    = 33
~~~

Đây là hai cách biểu diễn cùng một mức metadata. Người vận hành thường nhìn thấy tên như `4.4-IV2` trong output của công cụ; nội bộ feature record lưu level số.

Metadata version:

- Là trạng thái được finalize cho cluster.
- Được các node dùng để quyết định metadata capability đang được bật.
- Không phải phiên bản binary cài đặt.
- Không phải version của từng topic.
- Không phải version của từng consumer group.
- Không tự tăng chỉ vì broker đã chạy binary mới.

### 2.3. Feature level

Kafka có cơ chế versioning cho từng feature. Mỗi feature có tên và một tập level được hỗ trợ.

Ví dụ:

| Feature | Ý nghĩa khái quát |
|---|---|
| `metadata.version` | Metadata format và các capability liên quan đến cluster metadata |
| `kraft.version` | Capability của KRaft controller quorum |
| `group.version` | Capability/protocol của consumer groups |
| `streams.version` | Capability/protocol dành cho Kafka Streams groups |
| `share.version` | Capability/protocol của share groups |

Một feature level là mức version của đúng feature đó. Level của hai feature khác nhau không thể đem so trực tiếp để kết luận feature nào mới hơn.

Ví dụ:

~~~text
kraft.version = 1
share.version = 2
~~~

Không có nghĩa share group “mới hơn” KRaft vì 2 lớn hơn 1. Hai con số thuộc hai version space độc lập.

Một số feature có level 0 mang nghĩa “chưa bật capability mới” hoặc trạng thái nền; ý nghĩa chính xác tùy feature. Không được mặc định level 0 luôn đồng nghĩa feature bị tắt. Ví dụ, `kraft.version=0` có thể biểu thị static controller quorum trong một KRaft cluster.

`metadata.version` cũng là một feature trong hệ thống feature versioning. Vì vậy, có thể nói “metadata feature level”, nhưng không nên coi metadata.version là tên gọi cho mọi feature level của Kafka.

## 3. Sơ đồ quan hệ giữa software và feature levels

~~~mermaid
flowchart TB
    A["Kafka software release<br/>4.4.0"] --> B["Node capabilities<br/>SupportedMin / SupportedMax"]
    B --> C["Cluster feature state<br/>FinalizedVersionLevel"]
    C --> D["metadata.version<br/>4.4-IV2 / level 33"]
    C --> E["kraft.version<br/>ví dụ level 1"]
    C --> F["group.version"]
    C --> G["streams.version"]
    C --> H["share.version"]
    I["Kafka client release"] --> J["Client API capabilities"]
    K["Broker API versions"] --> J
~~~

Có thể hình dung:

- Software version là code được cài trên node.
- Supported feature range là những mức code đó có khả năng hiểu.
- Finalized feature level là mức cluster đang thực sự sử dụng.
- Client API versions là tập request/response protocol mà client và broker có thể thương lượng.

Trong rolling upgrade, các node mới có thể hỗ trợ feature level cao hơn trong khi cluster vẫn giữ feature level cũ. Đây là cơ chế cho phép nâng cấp phần mềm từng node trước khi bật capability mới.

## 4. Ví dụ: Kafka 4.4.0 nhưng metadata.version vẫn ở 4.3

Giả sử cluster ban đầu:

~~~text
Broker 1: Kafka 4.3.0
Broker 2: Kafka 4.3.0
Broker 3: Kafka 4.3.0
metadata.version: 4.3-IV0
~~~

Đội vận hành bắt đầu rolling upgrade lên 4.4.0:

~~~text
Broker 1: Kafka 4.4.0
Broker 2: Kafka 4.3.0
Broker 3: Kafka 4.3.0
metadata.version: 4.3-IV0
~~~

Sau khi nâng cấp broker 2:

~~~text
Broker 1: Kafka 4.4.0
Broker 2: Kafka 4.4.0
Broker 3: Kafka 4.3.0
metadata.version: 4.3-IV0
~~~

Sau khi tất cả broker đã chạy 4.4.0 và cluster được kiểm tra:

~~~text
Broker 1: Kafka 4.4.0
Broker 2: Kafka 4.4.0
Broker 3: Kafka 4.4.0
metadata.version: 4.3-IV0
~~~

Ở thời điểm này:

- Binary đã được nâng cấp.
- Các broker 4.4 có thể hỗ trợ metadata version cao hơn.
- Cluster vẫn dùng metadata version cũ.
- Những thay đổi metadata mới chưa được finalize.

Khi đã xác nhận cluster ổn định và sẵn sàng sử dụng capability mới, operator mới thực hiện feature upgrade tương ứng.

Đây là trạng thái có chủ đích trong quy trình upgrade. Không nên thấy hai version khác nhau rồi tự động coi đó là lỗi.

## 5. Phân biệt metadata.version với API version

Kafka có nhiều loại protocol/API version khác nhau.

### 5.1. Metadata version

Metadata version điều khiển các capability metadata và những thay đổi RPC/record liên quan được phối hợp ở cấp cluster. Nó được quản lý qua feature versioning.

### 5.2. Kafka API version

Kafka protocol có nhiều API như:

- Produce.
- Fetch.
- Metadata.
- FindCoordinator.
- JoinGroup.
- SyncGroup.
- Heartbeat.
- DescribeConfigs.
- AlterPartition.

Mỗi API có version range riêng. Client và broker thương lượng API version phù hợp khi giao tiếp.

Một broker có thể hỗ trợ nhiều API versions khác nhau; API version không phải metadata.version. Nếu cần kiểm tra API versions mà broker/controller hỗ trợ, dùng công cụ API versions phù hợp với release.

Trong Kafka 4.4, `kafka-cluster.sh api-versions` có thể hiển thị API versions được broker hoặc controller hỗ trợ:

~~~bash
bin/kafka-cluster.sh api-versions --bootstrap-server kafka-1:9092
~~~

Có thể dùng `--bootstrap-controller` để truy vấn controller endpoint nếu công cụ/release hỗ trợ đường kết nối đó.

### 5.3. Inter-broker protocol version

Trong các quy trình ZooKeeper-era, operator thường gặp cấu hình:

~~~properties
inter.broker.protocol.version=3.8
log.message.format.version=3.8
~~~

Đây là cơ chế nâng cấp lịch sử để kiểm soát protocol/message format giữa các broker.

Trong KRaft, `metadata.version` thay thế và mở rộng vai trò versioning cluster metadata/feature capability. Cấu hình `inter.broker.protocol.version` không còn là cơ chế điều khiển feature level cho KRaft; Kafka 4.x chỉ hỗ trợ KRaft và các cấu hình ZooKeeper-era đã bị loại bỏ.

Không sao chép nguyên quy trình nâng cấp từ tài liệu Kafka 2.x hoặc ZooKeeper-mode sang một cluster KRaft hiện đại.


## 6. Đọc output của kafka-features.sh describe

Lệnh kiểm tra feature state:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 describe
~~~

Với KRaft, có thể kết nối trực tiếp controller quorum:

~~~bash
bin/kafka-features.sh --bootstrap-controller controller-1:9093 describe
~~~

Có thể truyền cấu hình xác thực bằng `--command-config`:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 --command-config admin-client.properties describe
~~~

Output có dạng:

~~~text
Feature: metadata.version
  SupportedMinVersion: ...
  SupportedMaxVersion: ...
  FinalizedVersionLevel: ...
  Epoch: ...

Feature: kraft.version
  SupportedMinVersion: ...
  SupportedMaxVersion: ...
  FinalizedVersionLevel: ...
  Epoch: ...
~~~

Ý nghĩa các trường:

| Trường | Ý nghĩa |
|---|---|
| `SupportedMinVersion` | Feature level thấp nhất node đang được hỏi hỗ trợ |
| `SupportedMaxVersion` | Feature level cao nhất node đang được hỏi hỗ trợ |
| `FinalizedVersionLevel` | Feature level đã được finalize trong cluster |
| `Epoch` | Epoch của trạng thái feature/metadata được báo cáo |

### 6.1. SupportedMinVersion và SupportedMaxVersion

Hai giá trị này phản ánh capability của software đang chạy trên node được truy vấn.

Khi rolling upgrade, node mới có thể có `SupportedMaxVersion` cao hơn node cũ. Cluster chưa thể finalize một feature level nếu các node cần tham gia chưa hỗ trợ mức đó.

Đừng chỉ kiểm tra một broker rồi kết luận toàn bộ cluster đã hỗ trợ target level. Hãy xác nhận broker và controller theo topology, đặc biệt khi cluster đang ở trạng thái mixed-version.

### 6.2. FinalizedVersionLevel

Đây là mức feature mà cluster hiện đang sử dụng.

Ví dụ:

~~~text
SupportedMaxVersion: 4.4-IV2
FinalizedVersionLevel: 4.3-IV0
~~~

Điều này cho biết binary có khả năng hỗ trợ mức metadata mới nhưng cluster vẫn đang dùng mức đã finalize cũ.

### 6.3. Epoch

Epoch giúp nhận biết lần cập nhật feature/metadata. Khi feature được thay đổi, epoch có thể tăng. Dùng nó để đối chiếu trạng thái giữa các lần kiểm tra và log controller; không dùng epoch như software version.

### 6.4. Truy vấn node cụ thể

Lệnh có thể nhận `--node-id` để gửi request đến một node cụ thể:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 describe --node-id 2
~~~

Hãy kiểm tra node IDs thực tế và vai trò của từng node. Với controller chuyên dụng, có thể dùng bootstrap controller endpoint và node ID controller tương ứng.

## 7. Xem feature mapping của một Kafka release

Không nên tự đoán feature level của một release. Dùng `version-mapping` để xem mapping do đúng phiên bản Kafka binary cung cấp.

~~~bash
bin/kafka-features.sh version-mapping --release-version 4.4
~~~

Lệnh này hiển thị:

- Metadata version và numeric level tương ứng.
- Default level của từng production feature ở release được chọn.

Ví dụ metadata mapping trong Kafka 4.4:

~~~text
metadata.version = 4.4-IV2
metadata feature level = 33
~~~

Các feature khác sẽ được in theo mapping của binary. Hãy dùng output thực tế của release đích thay vì sao chép level từ một bài viết cũ.

### 7.1. Vì sao version-mapping quan trọng?

Giả sử cluster đang chạy Kafka 4.3 và chuẩn bị nâng lên 4.4:

1. Nâng cấp binary không đồng nghĩa mọi feature đều phải bật ngay.
2. Mapping cho biết mức mặc định tương ứng với release 4.4.
3. Operator so sánh mapping với feature state hiện tại.
4. Sau khi xác nhận tương thích, operator finalize feature levels.

Mapping là thông tin tham khảo cho kế hoạch nâng cấp. Nó không thực hiện thay đổi cluster.

## 8. Feature level độc lập: ví dụ thực tế

### 8.1. kraft.version

`kraft.version` kiểm soát capability của KRaft controller quorum.

Một ví dụ quan trọng là dynamic controller membership:

| Level | Ý nghĩa khái quát |
|---:|---|
| 0 | Static quorum |
| 1 | Hỗ trợ dynamic quorum/controller membership |

Có thể kiểm tra:

~~~bash
bin/kafka-features.sh --bootstrap-controller controller-1:9093 describe
~~~

Nếu muốn nâng riêng feature:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --feature kraft.version=1 --dry-run
~~~

Sau khi xác nhận cấu hình, phiên bản và quorum đáp ứng yêu cầu, mới thực hiện lệnh upgrade thật:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --feature kraft.version=1
~~~

Sau khi feature được finalize, kiểm tra lại:

~~~bash
bin/kafka-features.sh --bootstrap-controller controller-1:9093 describe
~~~

`kraft.version=1` không có nghĩa là “bật KRaft mode” cho một cluster ZooKeeper. Nó là một feature version trong một cluster KRaft. Static quorum có thể được migrate sang dynamic quorum từ Kafka 4.1 trở lên, nhưng đây là một migration riêng: sau khi nâng kraft.version lên level 1, operator phải cập nhật cấu hình trên tất cả node, bỏ controller.quorum.voters và dùng controller.quorum.bootstrap.servers theo KRaft upgrade guide. Chỉ nâng feature level không tự thay thế các bước cấu hình này.

Trước khi thay cấu hình `controller.quorum.voters` hoặc `controller.quorum.bootstrap.servers`, phải làm theo quy trình KRaft controller membership tương ứng. Không thay cấu hình quorum chỉ vì thấy level đã tăng.

### 8.2. share.version

Kafka 4.4 có share group DLQ functionality được kích hoạt khi `share.version` được nâng lên level 2.

Ví dụ:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --feature share.version=2 --dry-run
~~~

Sau khi kiểm tra feature dependencies và điều kiện cluster, operator mới nâng thật.

Điểm cần nhớ: broker software có thể đã là 4.4 nhưng share group DLQ vẫn chưa hoạt động nếu feature level cần thiết chưa được finalize.

### 8.3. group.version và streams.version

Các feature như `group.version` và `streams.version` điều khiển các capability/protocol liên quan đến consumer groups và Kafka Streams groups.

Chúng có thể thay đổi khả năng tương thích của group protocol. Ví dụ, một phiên bản protocol mới có thể thay đổi cách coordinator xử lý group, rebalance hoặc assignment.

Không tăng feature level của group chỉ để “đồng bộ số version” với broker. Trước hết cần kiểm tra:

- Tất cả broker có hỗ trợ level đích không?
- Client library và ứng dụng có hỗ trợ protocol đó không?
- Feature có dependency với metadata.version hoặc feature khác không?
- Có thay đổi hành vi khiến rollback bị giới hạn không?

Dùng `feature-dependencies` để xem dependency cụ thể thay vì tự suy luận.

## 9. metadata.version có thể tăng nhiều lần trong một release

Không nên giả định mỗi software release chỉ có một metadata version.

Kafka 4.4 có nhiều metadata revisions được dùng để gate các thay đổi khác nhau:

~~~text
4.4-IV1: hỗ trợ CIDR notation trong ACL host patterns
4.4-IV2: hỗ trợ unregister controller khỏi cluster metadata
~~~

Hai ví dụ này cho thấy cùng một software release có thể có nhiều metadata version. Mỗi revision là một mốc feature gate riêng; không suy ra một release luôn có đủ IV0, IV1, IV2. Các revision có thể được thêm khi có thay đổi metadata/RPC cần version hóa. Vì vậy:

- `4.4.0` là software release.
- `4.4-IV2` là metadata version.
- `33` là numeric feature level của metadata version đó.

Một số thay đổi tính năng yêu cầu metadata version cụ thể. Ví dụ trong Kafka 4.4, thao tác unregister controller cần `metadata.version=4.4-IV2`. Điều này cho thấy metadata version có thể là điều kiện tiên quyết cho một API/capability mới.

## 10. Quy trình nâng cấp an toàn

Một quy trình nâng cấp có hai pha lớn: nâng software trên các node, sau đó finalize feature levels của cluster.

~~~mermaid
flowchart TD
    A["Inventory software, roles, clients, feature state"] --> B["Đọc upgrade guide cho source và target"]
    B --> C["Kiểm tra prerequisites, backup, health"]
    C --> D["Rolling upgrade broker/controller binaries"]
    D --> E["Kiểm tra mọi node hỗ trợ target levels"]
    E --> F["Test cluster behavior và application compatibility"]
    F --> G["version-mapping + dry-run"]
    G --> H["Finalize release/feature levels"]
    H --> I["describe và kiểm tra feature/API"]
    I --> J["Theo dõi, cập nhật runbook và client rollout"]
~~~

### Bước 1: Inventory cluster

Ghi nhận:

- Software version từng broker.
- Software version từng controller.
- Node roles: broker, controller hay combined.
- Kafka client versions.
- Connect worker và connector plugin versions.
- Kafka Streams application versions.
- Current metadata.version.
- Current feature levels.
- Static/dynamic KRaft quorum.
- Storage directory format/tool version nếu có kế hoạch dùng lại data directory khi rollback.

Dùng:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 describe
~~~

Ghi lại output trước khi thay đổi.

### Bước 2: Kiểm tra upgrade path

Đọc upgrade guide của đúng phiên bản nguồn và đích. Kiểm tra:

- Phiên bản nguồn có được hỗ trợ nâng trực tiếp không?
- Có cần nâng qua intermediate release không?
- Có phải chuyển ZooKeeper sang KRaft trước không?
- Client tối thiểu là phiên bản nào?
- Có API/config đã bị loại bỏ không?
- Có thay đổi metadata không?
- Có feature nào tự động finalize khi chạy release upgrade không?
- Có yêu cầu migration riêng cho Streams, Connect hoặc plugin không?

Ví dụ Kafka 4.4:

- Chỉ hỗ trợ KRaft; ZooKeeper mode đã bị loại bỏ.
- Server upgrade trực tiếp được mô tả từ Kafka 3.3.x đến 4.3.0.
- KRaft cluster cũ hơn 3.3.x được khuyến nghị đi qua Kafka 3.9.x.
- Cluster ZooKeeper phải migrate sang KRaft trước khi nâng lên 4.4.

Đừng lấy một upgrade path áp dụng cho mọi phiên bản.

### Bước 3: Kiểm tra ứng dụng và client

Broker upgrade và client upgrade là hai công việc có liên quan nhưng độc lập.

Kiểm tra:

- Java client version.
- Spring Kafka version.
- Kafka Streams API đã dùng.
- Connect plugin compatibility.
- Custom serializer/deserializer.
- Interceptor, partitioner và callback.
- API hoặc config đã deprecated/removed.
- Protocol feature mới có được ứng dụng sử dụng hay không.

Kafka 4.0 đã loại bỏ nhiều API cũ; tài liệu yêu cầu broker/client tối thiểu phù hợp trước khi nâng lên 4.0. Không chỉ kiểm tra broker binary rồi kết luận ứng dụng đã tương thích.

### Bước 4: Chuẩn bị vận hành

Trước khi rolling upgrade:

- Xác nhận cluster khỏe.
- Xác nhận không có offline partition.
- Kiểm tra ISR và controller quorum.
- Kiểm tra disk, network và replication lag.
- Xác nhận backup/restore plan và cluster ID.
- Lưu cấu hình broker/controller.
- Lưu feature state hiện tại.
- Xác nhận quyền ACL cho Admin API cần dùng.
- Chuẩn bị theo dõi log và alert.

Không thực hiện nâng cấp metadata version trong lúc cluster đang mất replica hoặc controller quorum không ổn định.

### Bước 5: Rolling upgrade software

Với broker, nâng từng node theo upgrade guide. Không dừng tất cả broker cùng lúc.

Với KRaft controller chuyên dụng, nâng theo thứ tự và nhịp bảo đảm quorum vẫn có majority hoạt động. Không restart đồng thời phần lớn voter. Với combined mode, broker và controller cùng nằm trên node nên không thể roll/scale controller tách biệt khỏi broker.

Trong giai đoạn này, giữ feature levels ở mức cũ cho tới khi tất cả node cần thiết đã chạy binary hỗ trợ target.

### Bước 6: Kiểm tra khả năng hỗ trợ feature

Sau rolling upgrade:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 describe
~~~

Kiểm tra các node, controller và broker đã có SupportedMaxVersion đủ cho feature level mục tiêu.

Đồng thời kiểm tra:

- Broker registration.
- Controller quorum.
- Partition leadership.
- ISR.
- Produce/Fetch.
- Consumer group stability.
- Connect task state.
- Streams thread/task state.
- Application error rate và latency.

### Bước 7: Xem mapping và dry-run

Xem mapping:

~~~bash
bin/kafka-features.sh version-mapping --release-version 4.4
~~~

Dry-run release upgrade:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --release-version 4.4 --dry-run
~~~

Dry-run giúp validate thao tác mà không thực hiện feature update. Đọc output và xử lý lỗi dependency/compatibility trước khi chạy thật.

Đọc kỹ danh sách feature sẽ thay đổi. Lệnh upgrade theo release cập nhật nhiều production feature levels theo mapping, không chỉ metadata.version. Nếu mapping nâng kraft.version từ 0 lên 1, hãy lập cả bước migrate static quorum sang dynamic quorum và cập nhật cấu hình controller trên toàn bộ node theo KRaft guide; không xem release upgrade là thao tác chỉ đổi một con số.

### Bước 8: Finalize feature levels

Khi cluster đã được xác minh, thực hiện lệnh release upgrade theo hướng dẫn của phiên bản đích:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --release-version 4.4
~~~

Lệnh này cập nhật các production feature levels theo mapping của release. Nó không cài binary, không restart broker và không thay thế rolling upgrade software.

Nếu chỉ muốn nâng một feature cụ thể, có thể dùng `--feature feature-name=level` sau khi đã kiểm tra dependency và compatibility.

### Bước 9: Xác minh sau finalize

Chạy lại:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 describe
~~~

Đối chiếu:

- FinalizedVersionLevel.
- Metadata version đã finalize.
- Các feature độc lập.
- Epoch.
- API versions hỗ trợ.
- Application behavior.

Không chỉ nhìn lệnh upgrade trả về thành công. Cần xác nhận feature state trong cluster và kiểm tra các luồng nghiệp vụ.

### Bước 10: Theo dõi sau nâng cấp

Theo dõi trong cửa sổ phù hợp với traffic:

- Broker/controller logs.
- Request error rate.
- Produce/Fetch latency.
- Under-replicated/offline partitions.
- Consumer lag và rebalance.
- Streams/Connect task errors.
- Disk/network/CPU.
- Authentication/authorization errors.
- Business SLI/SLO.

Nếu có feature mới được bật, kiểm thử hành vi cụ thể của feature đó.

## 11. Các lệnh quản lý feature cần biết

### 11.1. Describe

Xem feature state hiện tại:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 describe
~~~

### 11.2. Version mapping

Xem feature levels tương ứng với release:

~~~bash
bin/kafka-features.sh version-mapping --release-version 4.4
~~~

### 11.3. Feature dependencies

Kiểm tra dependency của feature level:

~~~bash
bin/kafka-features.sh feature-dependencies --feature share.version=2
~~~

Nếu có nhiều feature cần kiểm tra, có thể truyền nhiều đối số `--feature` theo cú pháp của tool.

### 11.4. Upgrade một feature

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --feature kraft.version=1 --dry-run
~~~

Sau khi xác minh:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --feature kraft.version=1
~~~

### 11.5. Upgrade theo release

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --release-version 4.4 --dry-run
~~~

Thực hiện thật chỉ sau khi dry-run và kiểm tra vận hành đạt yêu cầu.

### 11.6. Downgrade feature

Tool có lệnh downgrade để hạ feature level khi version và metadata cho phép. Tuy nhiên, không được xem đây là nút rollback an toàn cho mọi feature.

Một số metadata version có thay đổi metadata không thể đảo ngược. Kafka có thể từ chối downgrade để bảo vệ cluster. Tool có tùy chọn `--unsafe` trong một số lệnh downgrade/disable, nhưng thao tác này có thể phá hủy metadata hoặc làm cluster không thể đọc trạng thái cũ. Không sử dụng `--unsafe` như một kế hoạch khôi phục thông thường.

### 11.7. Lưu ý về --metadata

Trong các tài liệu Kafka cũ, operator thường dùng:

~~~bash
bin/kafka-features.sh upgrade --metadata 3.9
~~~

Ở CLI hiện hành, tùy chọn `--metadata` đã deprecated. Nên dùng:

~~~bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 upgrade --release-version 4.4
~~~

Hoặc nâng feature cụ thể bằng `--feature` nếu đó là mục tiêu có chủ đích.

Luôn kiểm tra `kafka-features.sh --help` của đúng binary đang chạy; cú pháp có thể thay đổi giữa các release.


## 12. Rollback: ranh giới nằm ở feature/metadata state

Rollback phần mềm và downgrade metadata là hai thao tác khác nhau.

### 12.1. Trước khi finalize feature level mới

Nếu chỉ nâng binary mà chưa finalize metadata/feature level mới, cluster có thể còn nằm trong compatibility window của software cũ và mới.

Trong tình huống này, rollback binary có thể khả thi nếu:

- Upgrade path của Kafka cho phép.
- Metadata version hiện tại vẫn được binary cũ hỗ trợ.
- Chưa dùng feature/API mới yêu cầu binary mới.
- Data directory và storage format tương thích.
- Các client/app không ghi dữ liệu theo format mà binary cũ không hiểu.

Không giả định rollback luôn an toàn chỉ vì chưa chạy feature upgrade. Hãy kiểm tra đúng source/target version guide.

### 12.2. Sau khi finalize metadata.version mới

Khi metadata version được nâng, cluster có thể bắt đầu ghi metadata record theo format mới hoặc sử dụng RPC mới. Nếu version đích có metadata changes, binary cũ có thể không đọc hoặc xử lý được trạng thái đó.

Trong Kafka 4.4, `4.4-IV2` được đánh dấu có metadata changes. Tài liệu upgrade 4.4 nêu metadata downgrade không được hỗ trợ ở release này vì có các thay đổi metadata. Do đó, không được giả định có thể quay binary về 4.3 sau khi finalize 4.4 metadata.

### 12.3. Downgrade có thể phụ thuộc từng version

MetadataVersion có thuộc tính cho biết version đó có thay đổi metadata hay không. Downgrade chỉ có thể được xem xét nếu các metadata version nằm giữa source và target không có thay đổi metadata theo quy tắc của release.

Ví dụ một release có metadata version không thay đổi metadata có thể cho phép downgrade trong một số trường hợp. Điều đó không biến mọi feature level thành reversible.

### 12.4. Feature đã được ứng dụng sử dụng

Một feature có thể làm thay đổi hành vi hoặc protocol mà client/application đang dựa vào.

Ví dụ Kafka 4.4 hỗ trợ static membership cho Kafka Streams với Streams Rebalance Protocol. Tính năng này yêu cầu cả broker và client từ 4.4 trở lên. Nếu chuẩn bị downgrade broker xuống dưới 4.4, phải gỡ `group.instance.id` khỏi các Streams application dùng `group.protocol=streams` và restart ứng dụng trước theo upgrade guide.

Vì vậy, rollback checklist phải kiểm tra:

- Metadata version.
- Mọi finalized feature levels.
- Feature mà ứng dụng đã thực sự sử dụng.
- Client/Streams/Connect versions.
- Storage directory format.
- Các thay đổi metadata đã được ghi.
- Khả năng restore từ backup nếu downgrade không hỗ trợ.

## 13. Kafka 4.4: các ràng buộc cần nhớ

### 13.1. ZooKeeper không còn được hỗ trợ

Kafka 4.4 chỉ hỗ trợ KRaft. Cluster ZooKeeper phải migrate sang KRaft trước khi nâng lên 4.4.

KRaft cluster từ 3.3.x đến 4.3.0 có upgrade path trực tiếp theo tài liệu 4.4. Với KRaft version cũ hơn 3.3.x, tài liệu khuyến nghị đi qua 3.9.x trước khi lên 4.4.x.

### 13.2. Metadata version tối thiểu

Kafka 4.4 yêu cầu software và metadata versions ở mức 3.3.x trở lên theo upgrade guide. Không chỉ nhìn broker binary; hãy kiểm tra feature state của cluster.

### 13.3. Metadata 4.4-IV2

Một số capability mới yêu cầu metadata version cụ thể. Ví dụ thao tác unregister controller cần `4.4-IV2`.

Trong mã nguồn Kafka, `4.4-IV2` tương ứng feature level 33. Hãy xác minh mapping bằng `version-mapping` của binary đích.

### 13.4. Storage directory format và kafka-storage tool

Kafka 4.4 có thay đổi quan trọng: storage directories được format bởi `kafka-storage` tool không còn forward-compatible theo cách cũ. Broker phải có version bằng hoặc mới hơn version của tool đã format directory, bất kể giá trị `--release-version` khi format.

Vì vậy, khi chuẩn bị rollback hoặc thay thế node:

- Ghi nhận version của `kafka-storage.sh` đã format data directory.
- Dùng tool version phù hợp với broker.
- Không cho rằng chỉ cần giữ metadata.version cũ là mọi data directory có thể được mở bởi binary cũ.
- Kiểm tra tài liệu release đích trước khi format hoặc tái sử dụng directory.

Đây là một ràng buộc về software/tool compatibility và storage format; nó khác với metadata.version.

## 14. Một số tình huống vận hành

### 14.1. Binary mới nhưng feature level cũ

**Hiện tượng**

- Tất cả broker chạy Kafka 4.4.0.
- `SupportedMaxVersion` đã tăng.
- `FinalizedVersionLevel` của metadata.version vẫn là 4.3-IV0.

**Giải thích**

Cluster đã hoàn tất rolling upgrade software nhưng operator chưa finalize feature level mới.

**Cách xử lý**

- Kiểm tra tất cả broker/controller.
- Kiểm tra application compatibility.
- Chạy version-mapping.
- Chạy dry-run.
- Finalize khi cluster sẵn sàng.

Không tự động finalize chỉ để làm hai con số giống nhau.

### 14.2. Một broker hỗ trợ level mới, broker khác chưa hỗ trợ

**Hiện tượng**

- Broker mới có SupportedMaxVersion cao.
- Broker còn lại có SupportedMaxVersion thấp hơn.
- Cluster chưa thể nâng feature lên target level.

**Cách xử lý**

- Xác định node nào chưa được upgrade.
- Kiểm tra node role và software version.
- Hoàn thành rolling upgrade.
- Kiểm tra lại feature support trên các node.

### 14.3. Feature upgrade bị từ chối

**Nguyên nhân có thể**

- Một node chưa hỗ trợ level đích.
- Feature dependency chưa thỏa mãn.
- Metadata version chưa đủ.
- Feature đang ở trạng thái không cho phép update.
- Controller không thể xác thực update.
- Client ACL hoặc kết nối Admin API không đủ quyền.

**Cách xử lý**

1. Đọc error cụ thể từ CLI.
2. Chạy describe.
3. Chạy version-mapping.
4. Chạy feature-dependencies.
5. Xác minh software version trên node liên quan.
6. Chỉ thử lại sau khi điều kiện đã được xử lý.

Không ép downgrade/disable bằng `--unsafe` chỉ để bỏ qua lỗi.

### 14.4. Đã nâng metadata nhưng muốn quay về binary cũ

**Hiện tượng**

- Upgrade software đã xong.
- Feature level đã finalize.
- Phát hiện lỗi và muốn rollback.

**Cách xử lý**

- Xác định metadata version hiện tại và version target của binary cũ.
- Kiểm tra metadata change flags và upgrade guide.
- Kiểm tra feature levels khác đã được finalize.
- Kiểm tra ứng dụng đã sử dụng protocol/feature mới chưa.
- Chỉ downgrade nếu release hỗ trợ rõ ràng.
- Nếu metadata thay đổi không thể đảo ngược, sử dụng recovery/restore plan đã chuẩn bị.

Không thay binary cũ vào cluster rồi hy vọng nó tự đọc được metadata mới.

## 15. Lab: quan sát software version và feature levels

### Mục tiêu

Thực hành đọc feature state, xem mapping và mô phỏng quy trình nâng cấp theo hai pha trên cluster lab.

### Bước 1: Chuẩn bị cluster KRaft

Dùng cluster lab có broker/controller tương thích với phiên bản Kafka đang học. Ghi lại node IDs, roles và software versions.

Không thực hiện lab downgrade trên cluster production.

### Bước 2: Xem feature state hiện tại

~~~bash
bin/kafka-features.sh --bootstrap-server localhost:9092 describe
~~~

Ghi lại:

- metadata.version.
- kraft.version.
- group.version.
- streams.version.
- share.version.
- SupportedMinVersion.
- SupportedMaxVersion.
- FinalizedVersionLevel.
- Epoch.

### Bước 3: Xem mapping của release

~~~bash
bin/kafka-features.sh version-mapping --release-version 4.4
~~~

So sánh mapping với feature state hiện tại. Ghi lại feature nào sẽ thay đổi nếu finalize release upgrade.

### Bước 4: Kiểm tra dependency

Ví dụ:

~~~bash
bin/kafka-features.sh feature-dependencies --feature share.version=2
~~~

Ghi lại dependency mà tool báo. Nếu feature không có dependency, cũng ghi nhận điều đó.

### Bước 5: Kiểm tra API versions

~~~bash
bin/kafka-cluster.sh api-versions --bootstrap-server localhost:9092
~~~

So sánh API capabilities với metadata/feature state. Xác định chúng trả lời hai câu hỏi khác nhau.

### Bước 6: Chạy dry-run

~~~bash
bin/kafka-features.sh --bootstrap-server localhost:9092 upgrade --release-version 4.4 --dry-run
~~~

Đọc output và xác định lệnh sẽ thay đổi những feature nào. Không chạy lệnh thật nếu cluster lab chưa được chuẩn bị theo upgrade path.

### Bước 7: Thực hiện rolling upgrade trong lab

Nếu lab có nhiều node và phiên bản nguồn/đích phù hợp:

- Nâng từng broker.
- Nâng controller theo quy trình quorum.
- Giữ feature levels cũ trong khi rolling.
- Kiểm tra cluster health sau mỗi node.
- Xác nhận tất cả node hỗ trợ target levels.

### Bước 8: Finalize feature levels

Sau khi cluster đã ổn định, chạy lệnh release upgrade trong lab:

~~~bash
bin/kafka-features.sh --bootstrap-server localhost:9092 upgrade --release-version 4.4
~~~

### Bước 9: Xác minh

~~~bash
bin/kafka-features.sh --bootstrap-server localhost:9092 describe
~~~

So sánh trước và sau:

- Software versions.
- SupportedMaxVersion.
- FinalizedVersionLevel.
- Epoch.
- API versions.

### Bước 10: Viết kết luận

Trả lời:

1. Vì sao software version có thể cao hơn metadata.version?
2. SupportedMaxVersion khác FinalizedVersionLevel thế nào?
3. Metadata version 4.4-IV2 tương ứng numeric level nào?
4. `kraft.version=1` biểu thị capability gì?
5. Vì sao không thể suy luận `share.version=2` mới hơn `kraft.version=1`?
6. Khi nào cần chạy version-mapping?
7. Vì sao metadata downgrade có thể bị chặn?
8. Có thể rollback binary sau khi finalize metadata mới không? Cần kiểm tra điều kiện nào?

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách hiểu đúng |
|---|---|---|
| Coi software version và metadata.version là một | Nghĩ binary upgrade tự bật feature mới | Software và cluster feature state là hai pha |
| Thấy broker 4.4 thì cho rằng metadata đã là 4.4 | Bỏ qua finalize step | Kiểm tra FinalizedVersionLevel |
| Coi mọi feature level dùng chung một thang số | So sánh share.version=2 với kraft.version=1 | Mỗi feature có version space riêng |
| Coi metadata.version là Kafka API version | Chọn sai công cụ kiểm tra compatibility | Dùng api-versions cho protocol API |
| Dùng inter.broker.protocol.version cho KRaft | Cấu hình theo quy trình cũ | KRaft quản lý cluster feature qua metadata.version |
| Chạy upgrade --release-version trước rolling upgrade | Finalize feature khi node chưa hỗ trợ | Nâng binary, xác minh rồi mới finalize |
| Chỉ kiểm tra một broker | Bỏ sót node có SupportedMaxVersion thấp | Kiểm tra các broker/controller |
| Dùng --unsafe như rollback bình thường | Có thể phá hủy metadata | Chỉ dùng khi hiểu rõ hậu quả và có recovery plan |
| Cho rằng mọi metadata version đều downgrade được | Cluster có thể không đọc được dữ liệu metadata mới | Kiểm tra metadata change flag và release guide |
| Bỏ qua storage tool version | Broker cũ có thể không mở được directory | Kiểm tra kafka-storage format compatibility |
| Không kiểm tra client/application | API hoặc protocol mới làm app lỗi | Lập compatibility matrix cho clients, Streams, Connect |
| Coi kraft.version=0 là không chạy KRaft | Chẩn đoán sai quorum | Level 0 có thể là static quorum |
| Bỏ qua feature dependencies | Upgrade bị từ chối hoặc tạo trạng thái không mong muốn | Dùng feature-dependencies |
| Không lưu feature state trước nâng cấp | Khó so sánh và khôi phục | Lưu output describe trước/sau |

## 17. Checklist production

- [ ] Ghi nhận software version của từng broker và controller.
- [ ] Ghi nhận client, Connect, Streams và plugin versions.
- [ ] Xác nhận cluster đang chạy KRaft.
- [ ] Xác nhận source release nằm trong upgrade path được hỗ trợ.
- [ ] Lưu output kafka-features.sh describe trước nâng cấp.
- [ ] Xác định metadata.version hiện tại.
- [ ] Xác định từng feature level hiện tại.
- [ ] Kiểm tra SupportedMinVersion/SupportedMaxVersion của node.
- [ ] Đọc release notes và migration guide.
- [ ] Kiểm tra API/config đã deprecated hoặc removed.
- [ ] Kiểm tra storage directory format và kafka-storage tool version.
- [ ] Xác nhận backup/restore và recovery plan.
- [ ] Rolling upgrade từng broker.
- [ ] Rolling upgrade controller theo quorum safety.
- [ ] Kiểm tra ISR, controller, request và application health.
- [ ] Chạy version-mapping cho release đích.
- [ ] Chạy feature-dependencies cho feature cần bật.
- [ ] Chạy dry-run trước khi finalize.
- [ ] Finalize metadata/feature levels sau khi tất cả node hỗ trợ.
- [ ] Kiểm tra describe sau finalize.
- [ ] Kiểm tra API versions và ứng dụng.
- [ ] Ghi rõ rollback boundary trước khi bật feature mới.
- [ ] Không dùng unsafe downgrade nếu chưa có phương án khôi phục đã kiểm chứng.

## 18. Tài liệu tham khảo

- [Apache Kafka 4.4 – Upgrading](https://kafka.apache.org/44/getting-started/upgrade/)
- [Apache Kafka 4.4 – KRaft](https://kafka.apache.org/44/operations/kraft/)
- [Apache Kafka 4.2 – ZooKeeper to KRaft migration concepts](https://kafka.apache.org/42/getting-started/zk2kraft/)
- [Apache Kafka – FeatureCommand source](https://github.com/apache/kafka/blob/trunk/tools/src/main/java/org/apache/kafka/tools/FeatureCommand.java)
- [Apache Kafka – MetadataVersion source](https://github.com/apache/kafka/blob/trunk/server-common/src/main/java/org/apache/kafka/server/common/MetadataVersion.java)
- [KIP-778 – KRaft to KRaft Upgrades](https://cwiki.apache.org/confluence/display/KAFKA/KIP-778%3A+KRaft+to+KRaft+Upgrades)

Software version cho biết binary nào đang chạy. Metadata version cho biết cluster đang sử dụng mức metadata capability nào. Feature level cho biết từng tính năng đang ở mức nào. Trong quy trình nâng cấp, hãy nâng software trước, kiểm tra capability của toàn bộ node, rồi mới finalize feature levels theo mapping và hướng dẫn của release đích.
