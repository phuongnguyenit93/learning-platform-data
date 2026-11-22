# Upgrade broker và client độc lập trong Spring Kafka

Trong hệ thống Kafka, việc nâng phiên bản **Kafka broker** không nhất thiết buộc tất cả producer và consumer nâng phiên bản Java client trong cùng một thời điểm. Một cluster có thể phục vụ nhiều ứng dụng Java, Python, Go hoặc Kafka Streams với vòng đời triển khai khác nhau. Tương tự, đội ứng dụng có thể cần nâng **Spring Kafka** hoặc thư viện `kafka-clients` để sửa lỗi và tăng cường bảo mật trước khi đội nền tảng nâng cluster.

Khả năng nâng **broker và client độc lập** có được nhờ giao thức Kafka hỗ trợ thương lượng khả năng giữa client và broker. Tuy nhiên, điều đó **không có nghĩa mọi tổ hợp phiên bản luôn tương thích**, mọi tính năng mới chạy được với broker cũ hay việc nâng Kafka cluster hoàn toàn không ảnh hưởng đến dữ liệu đang xử lý.

Trong **Spring Kafka Reliability Operations → Nâng cấp và tương thích**, bài học này hướng dẫn cách xây dựng **ma trận tương thích, thứ tự nâng cấp, quy trình rollout và rollback an toàn**, đồng thời kiểm thử message delivery, offset, retry/DLT, transaction, schema và bảo mật ở từng giai đoạn.

```text
           Đội ứng dụng A                  Đội ứng dụng B
        Spring Boot / Kafka            Spring Boot / Kafka
       kafka-clients version X        kafka-clients version Y
                |                              |
                | Kafka wire protocol          |
                +---------------+--------------+
                                |
                                v
                      Kafka broker cluster
                  broker versions trong một
                  rolling upgrade có kiểm soát
                                |
                        KRaft controllers
                   + metadata feature levels
```

**Thông điệp chính:** nâng broker và client tách thời điểm là một khả năng kiến trúc hữu ích; để khai thác an toàn, cần giữ hai bản hợp đồng riêng: **hợp đồng wire protocol** giữa các thành phần Kafka và **hợp đồng nghiệp vụ** về payload, key, ordering, offset, retry và side effect.

## 1. Trước tiên, “phiên bản Kafka” là phiên bản nào?

Trong một ứng dụng Spring Boot, có nhiều lớp phiên bản độc lập tương đối với nhau:

| Lớp | Nơi tồn tại | Trách nhiệm | Khi nâng cấp cần kiểm tra |
| --- | --- | --- | --- |
| **Kafka broker** | Cluster máy chủ | Lưu log, replication, group coordinator, transaction coordinator, protocol APIs | Rolling upgrade, feature level, cluster health, client compatibility |
| **KRaft controller** | Controller quorum | Quản lý metadata của cluster và trạng thái các broker | Quorum, hướng dẫn upgrade đúng release, metadata compatibility |
| **Apache Kafka Java client** (`org.apache.kafka:kafka-clients`) | Trong producer/consumer JVM | Gửi/nhận record, metadata, commit offset, giao thức broker | Wire API, broker feature availability, client config và JDK |
| **Spring Kafka** (`org.springframework.kafka:spring-kafka`) | Trong Spring application | `@KafkaListener`, containers, `KafkaTemplate`, error handlers, retry topics, transactions | API/binary compatibility với Kafka client và Spring Framework |
| **Spring Boot** | Ứng dụng | Dependency management, auto-configuration, properties và lifecycle | Ma trận hỗ trợ Boot/Spring Kafka/Framework/Java |
| **Schema Registry / serializer** | Thư viện và service ngoài | Avro/JSON Schema/Protobuf, payload evolution | Schema compatibility, serializer version, subject strategy |
| **Kafka Connect/Streams** | Các ứng dụng đặc thù | Connector tasks hoặc stateful stream processing | Tài liệu nâng cấp riêng, state store, assignment và protocol |

Ví dụ trong một hệ thống, broker có thể được nâng trước, nhưng ứng dụng vẫn dùng Spring Kafka 3.x và Kafka Java client thuộc dependency tree do Spring Boot 3.x quản lý. Điều này **không mặc định yêu cầu** bạn nâng Spring Boot major version cùng lúc với broker.

Ngược lại, nâng Spring Boot có thể đồng thời kéo theo phiên bản Spring Kafka, Kafka clients, Jackson và Spring Framework mới. Đây là một **nâng cấp ứng dụng nhiều lớp**, ngay cả khi Kafka broker không thay đổi.

### 1.1. Ba kiểu thay đổi cần phân biệt

```text
Thay đổi A: Broker only
  broker B1 -> B2
  client C1 giữ nguyên

Thay đổi B: Client only
  broker B1 giữ nguyên
  kafka-clients C1 -> C2

Thay đổi C: Application stack
  Spring Boot / Spring Kafka / Java / kafka-clients cùng thay đổi
  broker B1 giữ nguyên
```

Kiểm thử cho A, B và C khác nhau. Một test “producer gửi và consumer nhận được một message” có ích nhưng chưa chứng minh transactional semantics, rebalance hoặc retry/DLT không thay đổi sau nâng cấp.

## 2. Vì sao broker và client có thể nâng riêng?

Apache Kafka dùng một giao thức request/response qua TCP. Mỗi loại request có tên API và các version của cấu trúc request/response tương ứng. Kafka clients có thể dùng `ApiVersionsRequest` để biết broker hỗ trợ những API versions nào, sau đó chọn phương thức giao tiếp phù hợp.

```text
Kafka Java client C2                        Broker B1
        |                                      |
        |------ ApiVersionsRequest ---------->|
        |<----- Supported API versions --------|
        |                                      |
        |------ ProduceRequest(version K) ---->|
        |<----- ProduceResponse(version K) ----|
```

Nếu client mới có khả năng dùng một API version chưa được broker cũ hỗ trợ, client thường phải chọn phiên bản giao thức tương thích cho thao tác đó hoặc **không sử dụng được tính năng mới**. Một tính năng yêu cầu broker hỗ trợ cụ thể không thể được “bật” chỉ bằng cách nâng JAR client.

### 2.1. Wire compatibility không đồng nghĩa feature parity

| Điều muốn làm | Client mới + broker cũ | Broker mới + client cũ |
| --- | --- | --- |
| Produce/consume thông thường | Thường có đường tương thích nếu cặp phiên bản được hỗ trợ | Thường có đường tương thích nếu cặp phiên bản được hỗ trợ |
| Dùng Kafka API hoặc group protocol mới | Có thể bị giới hạn bởi broker cũ | Client cũ có thể không biết tính năng mới |
| Giao dịch / idempotent producer | Cần coordinator và các API/version tương ứng | Cần client có implementation phù hợp |
| Schema mới | Phụ thuộc serializer và consumer, không chỉ broker | Broker không tự giải mã/validate business schema theo cách ứng dụng kỳ vọng |
| Spring Kafka retry/DLT mới | Phụ thuộc Spring Kafka và các topic/ACL | Broker mới không tự tạo policy retry của ứng dụng |
| Quản lý metadata KRaft | Thuộc control plane của cluster | Java producer/consumer không tự nâng metadata feature level |

**Không nên ghi trong tài liệu vận hành rằng “Kafka hỗ trợ backward compatibility nên mọi client đều chạy được với mọi broker”.** Giới hạn thực tế phụ thuộc **cặp release, API, client language, security settings và tính năng cụ thể**. Phải đối chiếu release notes/compatibility guidance của chính hai phiên bản mục tiêu.

### 2.2. Tương thích giữa broker khác phiên bản trong lúc rolling upgrade

Một cluster đang rolling upgrade có thể tạm thời có broker chạy hai phiên bản. Đây là tình huống **broker-to-broker compatibility**, khác với Java client-to-broker compatibility.

Ví dụ:

```text
Trước nâng cấp:
  broker-1 = version N
  broker-2 = version N
  broker-3 = version N

Giữa rolling upgrade:
  broker-1 = version N+1
  broker-2 = version N
  broker-3 = version N

Sau khi hoàn tất binary rollout:
  broker-1 = version N+1
  broker-2 = version N+1
  broker-3 = version N+1
```

Việc Kafka cho phép một giai đoạn mixed-broker như trên **có giới hạn theo đường upgrade chính thức**, không cho phép để cluster ở trạng thái mixed versions tùy ý trong thời gian dài. Nếu version N và N+1 không nằm trong đường nâng cấp được hỗ trợ, phải đi qua các bước trung gian hoặc migration riêng.

## 3. Bốn ô của ma trận tương thích

Trước mỗi nâng cấp, dựng một ma trận **2 × 2**:

| | Broker hiện tại B1 | Broker mục tiêu B2 |
| --- | --- | --- |
| **Client hiện tại C1** | (1) Baseline đang chạy | (2) Trạng thái sau broker-first |
| **Client mục tiêu C2** | (3) Trạng thái sau client-first | (4) Đích cuối |

Nếu muốn **nâng broker trước**, phải chứng minh ô **(2)**: client C1 vẫn làm các nghiệp vụ cần thiết với broker B2. Nếu muốn **nâng client trước**, phải chứng minh ô **(3)**: client C2 hoạt động với broker B1 mà không vô tình kích hoạt một tính năng chưa được hỗ trợ.

Nên đặt cả bốn ô vào một test plan thay vì chỉ test đích **(4)**. Nhiều sự cố chỉ xảy ra trong trạng thái chuyển tiếp: một ứng dụng cũ chưa được nâng, một Kafka Streams service dùng assignment cũ, hoặc một container Spring Kafka retry vẫn chạy với serializer khác.

### 3.1. Ví dụ bảng quyết định minh họa

Giả sử dự án đang chạy:

```text
Kafka broker: version B1
Spring Boot: version S1
Spring Kafka: version SK1
kafka-clients: version C1

Đích đến:
Kafka broker: version B2
Spring Boot: giữ S1 trong pha đầu
Spring Kafka / kafka-clients: nâng sau sang SK2 / C2
```

Bảng chuẩn bị:

| Tổ hợp | Nội dung test | Tiêu chí pass |
| --- | --- | --- |
| B1 + C1 | Baseline | Throughput, lag, errors, offset và output đã có mốc đo |
| B2 + C1 | Broker-first transition | Produce, consume, rebalance, retry/DLT, auth và transaction nếu dùng |
| B1 + C2 | Client-first transition | Không có `UnsupportedVersionException`, config mới không yêu cầu broker feature |
| B2 + C2 | Final state | Pass functional, failure-path và performance regression |

Ký hiệu B1/B2/C1/C2 cố ý **không gắn cặp version cụ thể**. Không nên suy ra mọi cặp Kafka 3.x/4.x đều hợp lệ từ bảng này; bản release thực tế và các bước migration bắt buộc phải được xác nhận trước rollout.

## 4. Những thay đổi có thể phá tương thích dù protocol vẫn hoạt động

Một client có thể kết nối và lấy metadata thành công nhưng xử lý nghiệp vụ vẫn sai. Các vùng rủi ro:

1. **Deserializer/serializer:** payload Avro/Protobuf/JSON thay schema, subject hoặc header.
2. **Consumer group protocol:** thay assignment protocol, `group.protocol` hoặc assignor.
3. **Offsets:** thay `group.id`, `auto.offset.reset`, ack mode hoặc chính sách commit.
4. **Transactions:** thay `transactional.id`, isolation level hoặc Kafka transaction manager.
5. **Retry/DLT:** thay tên topics, container factory, backoff, commit behavior, serializer chuyển tiếp.
6. **Security:** thay SASL mechanism, mTLS, truststore, ACL hoặc principal mapping.
7. **Runtime:** thay JDK baseline hoặc cách đóng/mở client trong container.
8. **Broker metadata/features:** bật tính năng cluster mới trước khi toàn bộ components đủ khả năng.
9. **Operational capacity:** rebalance lâu, ISR giảm, throughput hoặc latency thay đổi.

Vì vậy một smoke test cơ bản chỉ là **cửa đầu**, không phải chứng nhận toàn bộ upgrade.

## 5. KRaft, ZooKeeper và metadata feature level

Khi nói “nâng Kafka broker”, cần phân biệt **nâng binary của broker** với **nâng mức tính năng metadata của cluster**.

### 5.1. ZooKeeper và KRaft không phải một thay đổi nhỏ

Các thế hệ Kafka trước đây có thể dùng **ZooKeeper** để quản lý cluster metadata. Kafka hiện đại dùng **KRaft** với controller quorum. Apache Kafka **4.0 loại bỏ ZooKeeper mode**; vì vậy một cluster còn dựa vào ZooKeeper phải hoàn tất đường migration được hỗ trợ **trước khi** chuyển sang Kafka 4.x.

```text
Hệ thống cũ:
  Kafka brokers <--> ZooKeeper ensemble

Hệ thống mới:
  Kafka brokers <--> KRaft controller quorum

Không làm:
  Nâng thẳng binary broker 4.x trên cluster còn ở ZooKeeper mode
  rồi kỳ vọng nó tiếp tục khởi động như cũ.
```

Migration ZooKeeper → KRaft là **một dự án hạ tầng riêng**, có preflight, snapshot/backup, hướng dẫn phiên bản và khả năng quay lui được xác định theo từng giai đoạn. Không trộn migration đó với việc nâng đồng loạt Spring Boot clients trong cùng một đợt nếu không có nhu cầu và test đầy đủ.

### 5.2. `metadata.version` là gì?

Trong KRaft, mức tính năng metadata của cluster được quản lý thông qua **feature level**, thường biểu thị bằng `metadata.version`. Thao tác nâng binary broker không nhất thiết đồng nghĩa đã kích hoạt ngay mọi metadata feature mới.

```text
Pha A: Binary rollout
  controller/broker binaries nâng lên bản mục tiêu
  metadata.version vẫn ở mức được hỗ trợ cho upgrade/rollback

Pha B: Observe
  kiểm tra ISR, elections, client API, group, transaction, lag

Pha C: Feature finalization
  sau khi xác nhận tương thích và hết nhu cầu rollback binary,
  nâng metadata feature level theo runbook release tương ứng
```

Đây là **mô hình khái niệm**, không phải cam kết mọi phiên bản cho phép giữ feature level cũ mãi hoặc rollback tự do. Kafka release cụ thể có thể yêu cầu thứ tự nâng controller/broker và feature finalization khác nhau.

Lệnh quan sát trong cluster KRaft:

```bash
kafka-features.sh \
  --bootstrap-server broker1:9092 \
  describe
```

Lệnh dùng để xem các feature levels mà cluster công bố. Cú pháp thay đổi feature level và các tham số như `--release-version` phụ thuộc Kafka release; **không sao chép lệnh nâng feature level từ một bài viết của release khác rồi chạy trên production**.

### 5.3. Phân biệt với `inter.broker.protocol.version`

Trong tài liệu nâng cấp Kafka ở các thế hệ dùng ZooKeeper, bạn thường thấy `inter.broker.protocol.version` (IBP) và đôi khi `log.message.format.version`. Những thiết lập này có ý nghĩa theo thời kỳ và kiến trúc cụ thể. Với KRaft và Kafka releases mới, quy trình kiểm soát compatibility chủ yếu dựa vào các **feature levels**, nhất là `metadata.version`.

**Không áp dụng máy móc quy trình “giữ IBP, nâng binaries rồi bật IBP” từ Kafka đời cũ cho một KRaft cluster hiện đại.** Đầu tiên hãy xác nhận cluster mode và release đích, sau đó dùng upgrade guide tương ứng.

### 5.4. Controller quorum là một thành phần phải lập kế hoạch

Trong KRaft, controller quorum cần còn đủ thành viên hoạt động để quản lý metadata. Khi rolling restart controller:

- Không dừng cùng lúc nhiều controller khiến quorum mất khả dụng.
- Kiểm tra leader/controller election và metadata replication health.
- Tuân theo thứ tự upgrade controller và broker của release mục tiêu.
- Với mô hình node **combined broker/controller**, restart một node ảnh hưởng cả hai vai trò; kế hoạch capacity/quorum càng quan trọng.
- Theo dõi quá trình KRaft metadata convergence trước khi tiếp tục node tiếp theo.

Không giả định “restart từng broker một” luôn đầy đủ nếu controller đang chạy trên node riêng hoặc release yêu cầu thao tác controller trước/sau broker.

## 6. Kiểm kê hiện trạng trước khi nâng cấp

Một upgrade plan nên bắt đầu bằng **inventory**, không bắt đầu bằng lệnh deploy.

| Nhóm | Cần thu thập |
| --- | --- |
| Cluster | Kafka version từng broker/controller, cluster mode (KRaft/ZooKeeper), metadata feature level |
| Topology | Số brokers, controllers, racks, số partitions, replication factor, ISR |
| Client | Ngôn ngữ, `kafka-clients`/librdkafka version, Spring Boot/Spring Kafka version |
| Java | JDK runtime, container image/base OS, TLS provider |
| Consumer | `group.id`, member count, assignment strategy, group protocol, static membership |
| Producer | `acks`, `enable.idempotence`, retries, transaction settings, compression |
| Topics | Partition count, retention, min ISR, compaction, retry/DLT topology |
| Serialization | JSON/Avro/Protobuf, Schema Registry/subject compatibility, header convention |
| Security | SASL/SSL, certificates, ACL, OAuth, SCRAM, principal mapping |
| Operations | Alerts, lag dashboards, error rate, throughput, rollback windows |
| Dependencies | Connect, Streams, MirrorMaker, ksqlDB, admin clients, CDC components |

Một Java application có thể dùng nhiều Kafka-related libraries. Hãy kiểm tra **runtime dependency tree**, không chỉ version khai báo trực tiếp trong `build.gradle`.

### 6.1. Kiểm tra Java client dependency

Với Gradle:

```bash
./gradlew dependencyInsight \
  --dependency kafka-clients \
  --configuration runtimeClasspath
```

Trong Windows PowerShell:

```powershell
.\gradlew.bat dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
```

Đây là **lệnh tham khảo để người học tự thực hiện**, không phải bước bắt buộc do bài viết tự chạy. Output giúp biết `org.apache.kafka:kafka-clients` thực sự được resolve phiên bản nào, có dependency override hoặc conflict không. Nếu nâng Spring Boot hoặc Spring Kafka, kiểm tra lại cây dependency sau thay đổi.

### 6.2. Kiểm tra phiên bản CLI và broker capabilities

```bash
# Version của bộ Kafka CLI đang được sử dụng.
kafka-topics.sh --version

# API versions broker công bố.
kafka-broker-api-versions.sh \
  --bootstrap-server broker1:9092

# KRaft feature levels (khi áp dụng cho release/cluster mode).
kafka-features.sh \
  --bootstrap-server broker1:9092 \
  describe
```

**`kafka-topics.sh --version` là version bộ CLI**, không nhất thiết là version của mọi broker khi cluster mixed-version. `kafka-broker-api-versions.sh` hữu ích để quan sát API capabilities, nhưng không thay thế việc lấy version/config thực tế từ monitoring và release inventory.

Với cluster dùng SASL_SSL/mTLS, các lệnh CLI cần `--command-config client.properties` tương ứng; tệp này chứa credentials/truststore reference và phải được bảo vệ. Không dán password trực tiếp vào log/ticket.

### 6.3. Kiểm tra topics và consumer groups

```bash
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --topic orders.events

kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-service
```

Thu thập baseline về partition leaders, ISR, consumer offsets và lag. Với nhiều groups, tự động hóa inventory bằng công cụ quản trị phù hợp thay vì chỉ xem một topic minh họa.

## 7. Kịch bản A: nâng broker trước, giữ client cũ

Đây là một chiến lược thường được chọn khi cluster do platform team quản lý và có nhiều ứng dụng cần nâng theo lịch riêng.

```text
Trước:
  Kafka cluster B1
       |---- Spring Kafka client C1
       |---- Python client P1
       +---- Kafka Streams S1

Pha broker:
  Kafka cluster B2
       |---- Spring Kafka client C1 (giữ nguyên)
       |---- Python client P1 (giữ nguyên)
       +---- Kafka Streams S1 (giữ nguyên)

Pha ứng dụng về sau:
  Kafka cluster B2
       |---- Spring Kafka client C2
       |---- Python client P2 khi đến lịch
       +---- Kafka Streams S2 theo kế hoạch riêng
```

### 7.1. Điều kiện trước khi broker-first

1. Tất cả client versions hiện tại còn nằm trong dải tương thích mà Kafka release đích hỗ trợ.
2. Không có ứng dụng lệ thuộc vào một API/behavior đã bị xóa hoặc thay đổi mà không có migration.
3. Cluster có đủ replication, controller quorum và capacity để rolling restart.
4. Broker binary target đã được thử với workload/client hiện tại trong staging.
5. Nhóm vận hành biết giai đoạn nào có thể rollback binaries và giai đoạn nào feature finalization có thể hạn chế quay lui.
6. Kafka Connect/Streams/client không-Java cũng đã được tính đến.

### 7.2. Các pha triển khai khuyến nghị

```text
P0 Preflight: inventory + compatibility release notes + baseline
      |
      v
P1 Staging: cluster tương tự prod, B2 + C1, failure tests
      |
      v
P2 Chọn canary/batch broker theo upgrade guide
      |
      v
P3 Rolling broker/controller một cách tuần tự, theo dõi quorum/ISR
      |
      v
P4 Soak: client C1 chạy trên B2, đo chức năng và reliability
      |
      v
P5 Chốt tính năng cluster mới sau khi hết nhu cầu rollback
      |
      v
P6 Lên lịch nâng từng nhóm client sau
```

Không khởi động lại mọi broker cùng lúc. Một rolling restart có thể gây leader elections, consumer rebalances và producer retries; các hệ thống cần xử lý được **sự gián đoạn có giới hạn**, không được giả định zero-error.

### 7.3. Trong quá trình mixed-broker version

Một broker mới có thể là leader của partition mà client cũ đang gửi message; một broker cũ vẫn có thể là coordinator của consumer group. Cần quan sát:

- Producer errors/latency, metadata refresh và retries.
- Leader elections, offline partitions, ISR shrink/expand.
- Consumer group rebalances, lag và partition assignment.
- Transaction coordination và aborted transactions nếu có.
- Retry/DLT forwarding đến topic đích và quyền ACL.
- Cross-broker replication và network/disk saturation.

Nếu SLO bị vượt ngưỡng, **dừng rollout** và điều tra trước khi tiếp tục node khác. Rollout binary “hoàn tất” không đủ để bật feature level mới ngay.

## 8. Kịch bản B: nâng client trước, giữ broker cũ

Chiến lược client-first phù hợp khi ứng dụng cần sửa CVE, nâng Spring Boot/Spring Kafka để được hỗ trợ lâu dài hoặc dùng API client mới, trong khi platform chưa sẵn sàng nâng broker.

```text
Trước:
  Spring Boot S1 / Spring Kafka SK1 / kafka-clients C1
                       |
                       v
                  Broker B1

Sau client-first:
  Spring Boot S2 / Spring Kafka SK2 / kafka-clients C2
                       |
             protocol negotiation
                       |
                       v
                  Broker B1
```

Đừng nâng **chỉ** Kafka Java client bằng một version override tùy tiện rồi bỏ qua ma trận tương thích **Spring Kafka ↔ kafka-clients**. Một thay đổi binary API của thư viện có thể gây `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi khởi tạo trong JVM dù client vẫn có thể giao tiếp về mặt wire protocol với broker.

### 8.1. Thứ tự client-first an toàn

1. Xác định Java/JDK baseline của Spring Boot/Spring Kafka/Kafka clients mục tiêu.
2. Chọn tổ hợp version được Boot/Spring Kafka hỗ trợ, ưu tiên dependency management chính thức.
3. Kiểm tra các cấu hình Kafka cũ có còn hợp lệ, bị deprecated hoặc đổi default không.
4. Chạy integration test C2 với broker B1, không kích hoạt tính năng chỉ có ở B2.
5. Canary một số app instances, quan sát group rebalances, retry/DLT và output.
6. Rolling client instances theo deployment policy, không restart toàn bộ consumer group khi không cần thiết.
7. Giữ cấu hình/binary C1 để rollback **trước khi** thực hiện thay đổi schema/message format hoặc application state không tương thích.

### 8.2. Một số tính năng client mới vẫn cần broker mới

Ví dụ:

- Một consumer group protocol mới cần broker/coordinator hiểu protocol đó.
- Một request API version mới có thể không được broker cũ hỗ trợ.
- Một tính năng transaction, partition assignment hoặc authorization mới có dependency phía broker.
- Một serializer/client mới có thể ghi payload mà consumer cũ không đọc được, bất kể broker version.

Nếu client mục tiêu có feature cần broker B2, phải **đặt feature đó ở trạng thái chưa kích hoạt** cho tới sau broker upgrade, hoặc chọn broker-first. Đừng trông chờ client tự fallback về semantic cũ khi tính năng đã được cấu hình bắt buộc.

## 9. Spring Boot và Spring Kafka: tránh dependency override không kiểm soát

Trong Spring Boot, `spring-kafka` và `kafka-clients` thường được quản lý bằng BOM/dependency management. Ví dụ Gradle minh họa:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<BOOT_VERSION>'
    id 'io.spring.dependency-management' version '<PLUGIN_VERSION>'
}

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Hai placeholder `<BOOT_VERSION>` và `<PLUGIN_VERSION>` phải thay bằng các phiên bản **được dự án chọn theo ma trận hỗ trợ**; đoạn này minh họa dependency ownership, không phải một `build.gradle` có thể chạy nguyên văn.

### 9.1. Vì sao không nên `force` Kafka client version?

Một ví dụ rủi ro:

```groovy
configurations.all {
    resolutionStrategy.force(
        'org.apache.kafka:kafka-clients:<ARBITRARY_VERSION>'
    )
}
```

Nếu version Kafka client đó ngoài khoảng đã được Spring Kafka release mục tiêu thử nghiệm, code ứng dụng có thể compile nhưng lỗi lúc runtime. Tốt hơn là:

- Nâng Spring Boot/Spring Kafka tới bộ dependency đã được phát hành và hỗ trợ.
- Chỉ override khi có lý do rõ ràng (ví dụ bản vá bảo mật) và release notes cho phép.
- Kiểm tra **`runtimeClasspath`**, không chỉ `compileClasspath`.
- Chạy test với broker hiện tại và broker mục tiêu.
- Ghi lại ngoại lệ dependency override trong ADR và kế hoạch quay lui.

### 9.2. Cấu hình Spring Kafka mẫu để kiểm thử tương thích

`application.yml` minh họa cho string messages:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000

    consumer:
      group-id: orders-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest

    listener:
      ack-mode: record
```

Các giá trị trên chỉ là baseline minh họa. `enable.idempotence=true` yêu cầu producer/client/broker hỗ trợ đầy đủ các điều kiện liên quan và không được có các cấu hình xung đột. `acks=all` bảo đảm xác nhận theo tập replica đang ở ISR và policy broker, **không thay thế** business idempotency, và không có nghĩa Kafka sẽ không bao giờ mất dữ liệu trong mọi tình huống thảm họa.

Nếu ứng dụng đã có transaction/offset strategy riêng, không thay ack mode hoặc idempotence giữa một migration chỉ để theo ví dụ; phải đo đúng behavior hiện tại trước và sau.

## 10. Consumer group rebalances trong rolling client upgrade

Mỗi lần một application instance bị restart, consumer group có thể cần rebalance hoặc chuyển partitions. Khi nâng nhiều instances, hiện tượng này có thể làm consumer lag tăng, processor nhận lại record hoặc side effect bị gọi lặp.

```text
Group orders-service
  Instance A / client C1
  Instance B / client C1
  Instance C / client C1

Rollout:
  A -> C2 (B,C vẫn C1)
  quan sát assignment và lag
  B -> C2 (A,C vẫn hoạt động)
  C -> C2
```

**Không giả định hai consumer client versions luôn có thể cùng một group với mọi assignment strategy.** Với `partition.assignment.strategy`, `group.protocol`, remote assignor và Spring Kafka container config, phải kiểm tra giao thức nhóm/assignor có tương thích trong giai đoạn mixed members không.

### 10.1. Classic và consumer group protocol mới

Kafka các release mới có hỗ trợ **consumer group protocol mới** ngoài kiểu classic, được điều khiển bằng cấu hình như `group.protocol=consumer` trên client có hỗ trợ. Việc có thể bật protocol này phụ thuộc Kafka brokers/group coordinators và client versions.

Không chuyển toàn bộ group từ classic sang protocol mới **đồng thời** với nâng broker/client mà không test. Nên coi đổi group protocol là một **feature migration riêng**, có plan cho assignment behavior, metrics, compatibility, rollback và giá trị config được chấp nhận.

### 10.2. Cooperative assignment và static membership

Một số chiến lược như cooperative-sticky assignment và static membership (`group.instance.id`) có thể giúp giảm rebalance disruption trong tình huống phù hợp, nhưng:

- Cần thống nhất config trên các members cùng group.
- `group.instance.id` phải **duy nhất** giữa các instances; trùng ID gây fencing/lỗi.
- Rolling deploy Kubernetes có thể tạo overlap giữa Pod cũ và mới, cần cân nhắc instance identity.
- Nếu processor đã ghi side effect nhưng chưa commit offset trước rebalance, record vẫn có thể được giao lại.

Đừng dùng static membership như một cơ chế chống duplicate nghiệp vụ. Nó chỉ ảnh hưởng đến thành viên nhóm/assignment; business handler vẫn phải idempotent.

## 11. Producer reliability khi broker và client nâng riêng

Sau nâng cấp, producer có thể thay đổi cách chọn API version, compression, error mapping hoặc default config (tùy version). Cần kiểm tra không chỉ message có đến broker, mà còn **hành vi khi leader thay đổi và request được retry**.

### 11.1. Một baseline producer có kiểm soát

```java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> template;

    public OrderPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String payload) {
        return template.send("orders.events", orderId, payload);
    }
}
```

Đoạn trên minh họa kiểu return `CompletableFuture` trong các Spring Kafka version hiện đại, cần imports từ `java.util.concurrent`, `KafkaTemplate` và `SendResult`. Khi nâng từ Spring Kafka đời cũ, API `KafkaTemplate.send`/kiểu future có thể thay đổi; **compile/runtime tests** phải bao gồm các điểm gọi này, không chỉ integration test broker.

Thao tác từ caller:

```java
publisher.publish("order-123", "{\"event\":\"CREATED\"}")
    .whenComplete((result, error) -> {
        if (error != null) {
            // Phân loại và ghi nhận lỗi; không coi là đã gửi thành công.
        } else {
            // Broker đã acknowledge theo producer config.
        }
    });
```

`ack` từ Kafka producer không chứng minh downstream consumer đã xử lý nghiệp vụ. Nếu record được publish lại sau timeout do ứng dụng tạo request mới, producer idempotence cấp protocol có thể **không deduplicate** hai business messages độc lập. Cần stable event ID/outbox theo hợp đồng nghiệp vụ.

### 11.2. Các failure paths cần test

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Broker leader restart | Producer retry và phục hồi, không mất output theo SLA |
| Kafka broker unavailable ngắn | Có timeout hợp lý, không treo request vô hạn |
| ISR tụt dưới `min.insync.replicas` | Producer `acks=all` có thể bị từ chối theo policy bảo vệ dữ liệu |
| Request timeout sau broker ack | App xử lý trạng thái không rõ kết quả bằng event ID/idempotency |
| Message lớn hoặc compression thay đổi | Broker/client config không gây serialization/record size failure |
| ACL hoặc TLS thay đổi | Producer authenticate/authorize, lỗi phân loại rõ |
| Mixed broker versions | Không có lỗi API version/metadata refresh bất thường |

### 11.3. `acks=all`, ISR và downtime

`acks=all` kết hợp replication factor và `min.insync.replicas` là một phần của chiến lược độ bền. Trong rolling broker upgrade, ISR có thể tạm giảm vì replica đang restart. Nếu xuống dưới ngưỡng min ISR, producer có thể nhận lỗi thay vì chấp nhận ghi thiếu replica.

Đây thường là **hành vi an toàn theo policy**, không phải dấu hiệu cần lập tức hạ `min.insync.replicas` hoặc bật unclean leader election. Giảm bảo vệ dữ liệu chỉ để rollout không báo lỗi có thể gây nguy cơ mất record.

## 12. Consumer offset và acknowledgment không được đổi ngoài ý muốn

Nâng client không đồng nghĩa nên đổi `group.id`, ack mode hoặc offset reset policy. Những tham số này quyết định cách hệ thống tiếp tục xử lý sau restart.

```text
Partition orders.events-0
offset:         100 101 102 103 104 105
                      ^
                 committed next offset = 101

Client C1 restart thành C2:
  nếu giữ group.id và committed offset,
  consumer tiếp tục từ offset được group lưu theo protocol.

Nếu đổi group.id:
  đây là một group khác; offset khởi đầu theo auto.offset.reset
  hoặc seek policy mới, có thể đọc lại/hụt dữ liệu.
```

Với `AckMode.RECORD`, commit strategy khác `MANUAL`, `MANUAL_IMMEDIATE` hoặc Kafka transactions. Nếu trong cùng đợt upgrade đổi ack mode, khó quy lỗi khi phát sinh duplicate hoặc mất dữ liệu.

### 12.1. Test những thời điểm crash nguy hiểm

1. Handler hoàn tất side effect database nhưng chưa commit Kafka offset.
2. Process chết sau khi poll record nhưng trước khi handler commit side effect.
3. Rebalance xảy ra khi callback xử lý lâu.
4. Retry/DLT forwarding đã publish thành công nhưng nhánh commit offset gốc lỗi.
5. Consumer được restart với group ID cũ nhưng cấu hình deserializer khác.

**At-least-once delivery** có thể giao lại record ở một số điểm trên. Để chống duplicate, dùng unique business key, inbox/dedup store hoặc transactional outbox theo kiến trúc. Một broker/client version mới không tự biến side effect HTTP/JDBC thành exactly-once.

## 13. Kafka transactions và Streams cần kế hoạch riêng

Với producer transactional hoặc consumer dùng `isolation.level=read_committed`, ma trận tương thích phải bao gồm:

- Transaction coordinator và `transactional.id` lifecycle.
- Commit/abort, fencing và timeout.
- Read-committed visibility khi broker leader thay đổi.
- Kafka transaction manager cấu hình trong Spring Kafka.
- Chuyển tiếp offsets trong transaction khi phù hợp mô hình EOS.

Non-blocking retry topic của Spring Kafka có giới hạn khi kết hợp container transactions; đừng tự bật `@RetryableTopic` trong một pipeline transactional mà không kiểm tra tài liệu phiên bản và chọn kiến trúc đúng.

### 13.1. Streams và stateful processing

Kafka Streams có task assignment, internal topics, changelog, repartition topics, local state stores và cơ chế version riêng. Nâng `kafka-streams` library không nên bị xem như chỉ thay `kafka-clients` trong một stateless `@KafkaListener`.

Các phép thử bổ sung:

- Một Kafka Streams instance mới và cũ có thể đồng tồn tại theo upgrade guide hay không.
- Internal topic config/replication/partitioning có thay đổi không.
- Local state restoration từ changelog sau restart có đúng không.
- Exactly-once processing mode còn tương thích không.
- Topology mới có yêu cầu reset application state hoặc migration store format không.

Nếu chỉ xây Spring Kafka record listeners, không cần triển khai Streams tests. Nhưng một kế hoạch nâng **broker toàn cluster** phải kiểm kê những ứng dụng Streams đang tiêu thụ cluster đó.

## 14. Schema và serialization: tương thích độc lập với broker

Broker Kafka thường không hiểu ý nghĩa của một JSON field `status` hoặc Avro schema của nghiệp vụ. Vì vậy một broker upgrade có thể chạy trơn tru trong khi producer/consumer mới **phá payload compatibility**.

Ví dụ JSON cũ:

```json
{
  "orderId": "O123",
  "amount": 100
}
```

Phiên bản mới:

```json
{
  "orderId": "O123",
  "amount": {
    "currency": "USD",
    "value": 100
  }
}
```

Nếu consumer cũ kỳ vọng `amount` là số nguyên, nó có thể lỗi deserialization hoặc business mapping. Đây là thay đổi **schema/application contract**, không phải Kafka wire protocol.

### 14.1. Cách nâng payload an toàn

- Dùng Schema Registry và chế độ compatibility phù hợp (backward/forward/full) nếu tổ chức áp dụng Avro/Protobuf/JSON Schema.
- Thiết kế thêm field có default hoặc giữ định dạng cũ trong một giai đoạn chuyển tiếp.
- Triển khai consumer có thể đọc cả format cũ và mới trước khi producer phát format mới, khi phù hợp.
- Test schema evolution với **message đã lưu từ phiên bản trước**, không chỉ message được cả producer và consumer mới tạo.
- Kiểm soát `type headers`, trusted packages và serializer config khi nâng Spring Kafka.
- Đặt message/event version vào hợp đồng nghiệp vụ nếu schema registry không đủ mô tả logic chuyển đổi.

Đối với DLT, nếu bản ghi cũ bị lỗi deserialization, ứng dụng mới cần biết cách đọc **raw bytes** hoặc giữ metadata gốc để điều tra. Đừng giả định nâng broker tự chuyển đổi những message đã được lưu trong Kafka.

## 15. Bảo mật và Java runtime có thể làm upgrade thất bại

Một client mới có thể không kết nối được broker cũ do **TLS/SASL**, dù Kafka request protocol tương thích.

| Thành phần | Rủi ro | Biện pháp |
| --- | --- | --- |
| TLS | Cipher/certificate chain/hostname verification khác | Test TLS handshake bằng runtime image mới |
| SASL SCRAM/PLAIN | Credential hoặc broker listener config thay đổi | Kiểm tra auth trên staging theo principal thật |
| OAuth/OIDC | Token audience/issuer/clock skew hoặc client library thay đổi | Smoke test refresh token và reauthentication |
| ACL | Retry/DLT topics, consumer group hoặc transactional ID thiếu quyền | Test cả success path và failure path |
| Java version | Spring Boot/Spring Kafka/Kafka client mới cần runtime JDK khác | Chốt Java/JDK matrix và container base image |
| Truststore/keystore | Path, password, format JKS/PKCS12 hoặc mount bị đổi | Kiểm tra image/deployment manifest |
| Network/DNS | Bootstrap broker, advertised listeners, load balancer | Test kết nối tới **mọi advertised broker** chứ không chỉ bootstrap |

**Đừng nâng quyền ACL wildcard hoặc tắt TLS hostname verification để “sửa lỗi tương thích”**. Hãy xác định sai lệch cấu hình cụ thể, sửa CA/listener/principal đúng phạm vi và giữ audit thay đổi.

### 15.1. Bootstrap hoạt động không chứng minh toàn cluster truy cập được

Kafka client dùng bootstrap address ban đầu, sau đó nhận metadata chứa **advertised listeners của các brokers**. Nếu ứng dụng mới đổi container network, DNS hoặc certificate trust, nó có thể kết nối bootstrap nhưng thất bại khi producer/consumer tới broker leader khác.

Smoke test nên gửi record tới nhiều partitions (qua keys khác nhau hoặc explicit partition trong môi trường test) để chạm nhiều leaders, thay vì chỉ gửi một record đến một partition.

## 16. Retry topic và DLT có thay đổi khi nâng không?

Trong Spring Kafka, non-blocking retry thường tạo **các listener containers cho retry và DLT topics** dựa trên `@RetryableTopic` hoặc `RetryTopicConfiguration`. Khi nâng Spring Kafka, số retry topics, cách đặt suffix/reuse, default fatal exception classifier, container factory hoặc error handling có thể thay đổi tùy release.

```text
Main topic            orders.events
Retry destinations    orders.events-retry-...
DLT                   orders.events-dlt

Spring Kafka version SK1
   |
   +-- đang còn backlog ở retry topics SK1

Deploy SK2 thay đổi retry topic naming
   |
   +-- listeners mới chỉ đọc topics SK2?
   +-- backlog SK1 có bị bỏ quên?
```

Nâng **broker only** không bắt buộc thay Spring Kafka retry topology. Nhưng nếu nâng **client stack**, phải inventory retry topic graph và consumer groups:

1. Liệt kê main/retry/DLT topics do application quản lý.
2. Xác định naming strategy, suffix, topic reuse và số partitions.
3. Kiểm tra lag từng retry topic trước deploy.
4. So sánh listeners của release cũ và mới.
5. Giữ cơ chế drain/migrate backlog cũ nếu naming thay đổi.
6. Test record retryable đến đích và non-retryable vào DLT đúng policy.
7. Test KafkaTemplate forward thành công với serializer/ACL mới.

Không xóa retry/DLT topics cũ chỉ vì app đã lên phiên bản mới. Chúng có thể chứa **work chưa được xử lý** ngay cả khi main topic lag bằng 0.

## 17. Kiểm thử compatibility với staging cluster

Một môi trường `@EmbeddedKafka` rất hữu ích để test Spring listener wiring, nhưng **không mô phỏng đầy đủ rolling upgrade của multi-broker KRaft cluster**. Để kiểm tra tương thích broker/client thực sự, cần staging cluster có cấu hình gần production:

- Broker/controller layout phù hợp.
- Kafka release đúng B1/B2.
- TLS/SASL/ACL tương tự production.
- Replication factor, `min.insync.replicas`, partitions và retention tương tự.
- Consumer group với nhiều members để thử rebalance.
- Retry topics và DLT.
- Một bộ messages từ phiên bản schema cũ.

### 17.1. Ma trận test chức năng và reliability

| Bài test | B1 + C1 | B2 + C1 | B1 + C2 | B2 + C2 |
| --- | :---: | :---: | :---: | :---: |
| Producer send/ack | Baseline | Bắt buộc | Bắt buộc | Bắt buộc |
| Consumer receive/commit offset | Baseline | Bắt buộc | Bắt buộc | Bắt buộc |
| Restart/rebalance không mất dữ liệu | Baseline | Bắt buộc | Bắt buộc | Bắt buộc |
| Exception → retry → success | Baseline | Bắt buộc nếu dùng | Bắt buộc nếu dùng | Bắt buộc nếu dùng |
| Hết retry → DLT | Baseline | Bắt buộc nếu dùng | Bắt buộc nếu dùng | Bắt buộc nếu dùng |
| Transaction commit/abort | Baseline | Bắt buộc nếu dùng | Bắt buộc nếu dùng | Bắt buộc nếu dùng |
| Schema cũ/mới | Baseline | Theo hợp đồng | Bắt buộc khi đổi serializer | Bắt buộc |
| Security/ACL/TLS | Baseline | Bắt buộc | Bắt buộc | Bắt buộc |
| Rolling broker disruption | Theo rehearsal | Bắt buộc trong staging | Không áp dụng nếu chỉ client | Bắt buộc nếu cùng đợt |
| JDK/runtime startup | Baseline | Client không đổi | Bắt buộc | Bắt buộc |

Nếu một ô không thuộc đường tương thích được Kafka release hỗ trợ, **không cố ép test pass**: hãy đổi thứ tự upgrade hoặc thêm bước trung gian. Ma trận phải dựa trên release documentation chứ không chỉ kết quả thử của một topic nhỏ.

### 17.2. Smoke test Spring Kafka bằng producer/consumer thật

Ví dụ Spring Boot 3.x + Spring Kafka 3.x. Test kết nối tới **staging Kafka cluster**, không cần tự tạo broker trong test.

Listener probe:

```java
package com.example.kafka.upgrade;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class UpgradeProbeListener {

    final BlockingQueue<String> received =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        id = "upgradeSmokeListener",
        topics = "upgrade.smoke",
        groupId = "upgrade-smoke-consumer"
    )
    public void onMessage(String value) {
        received.add(value);
    }
}
```

Integration test:

```java
package com.example.kafka.upgrade;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.utils.ContainerTestUtils;

@SpringBootTest
class KafkaUpgradeSmokeTest {

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    UpgradeProbeListener listener;

    @Test
    void producerAndConsumerCommunicateWithTargetBroker()
            throws Exception {

        MessageListenerContainer container =
            Objects.requireNonNull(
                registry.getListenerContainer("upgradeSmokeListener"));

        // Topic upgrade.smoke có 1 partition trong fixture này.
        ContainerTestUtils.waitForAssignment(container, 1);

        String message = "upgrade-probe-" + UUID.randomUUID();
        template.send("upgrade.smoke", message, message)
            .get(10, TimeUnit.SECONDS);

        assertThat(listener.received.poll(10, TimeUnit.SECONDS))
            .isEqualTo(message);
    }
}
```

Điều kiện để dùng test này:

1. Topic `upgrade.smoke` được **pre-provision trong staging** với một partition, principal có quyền `READ`/`WRITE` và group permission.
2. Spring Boot test dùng đúng broker B1 hoặc B2 trong từng ô ma trận; không trỏ tới production.
3. Group ID/topic được **isolate** khi test chạy song song, hoặc có cleanup và correlation rõ ràng. Nếu topic chung chứa records cũ, queue có thể nhận một record khác trước message test.
4. Producer và consumer có `StringSerializer`/`StringDeserializer` hoặc cấu hình payload nhất quán.
5. `KafkaListenerEndpointRegistry` đăng ký được listener và container có assignment trước khi gửi.

Test trên **chỉ chứng minh đường produce/consume cơ bản**; nó không chứng minh offset commit bền vững, transactional semantics, retry/DLT, broker rolling restart hay bảo mật trên mọi listener.

### 17.3. Bài test crash/replay và idempotency

Với event `order-123`, xây kịch bản:

```text
Producer gửi order-123, broker ack.
Consumer C1/C2 nhận message.
DB commit kết quả order-123.
Consumer process chết trước Kafka offset commit.
App restart, message được redeliver nếu offset chưa commit.

Kỳ vọng nghiệp vụ:
  processed_orders(order_id=order-123) có đúng 1 effect,
  retry/replay có log,
  committed offset cuối tiến về đúng vị trí.
```

Để kiểm chứng, output DB cần **unique business key hoặc idempotent upsert**, không chỉ nhìn `@KafkaListener` đã được gọi đúng một lần. Nếu handler gọi external API, phải có idempotency key hoặc cách đối soát trạng thái đích.

### 17.4. Rebalance và rolling broker test

Trong staging:

1. Khởi động nhiều members cùng consumer group.
2. Gửi tập records có event IDs duy nhất, đủ trải qua nhiều partitions.
3. Rolling restart một broker/controller theo upgrade guide.
4. Ghi lại rebalances, leader elections, lag, producer errors, xử lý message bị lặp.
5. Chạy lại kịch bản với old/new client versions.
6. Đối soát **tập business keys cuối**; không mất, không nhân đôi effects.

Nếu một test CI dùng single-node Kafka Testcontainers, nó không thể đại diện đầy đủ cho kiểm chứng ISR hoặc controller quorum trong rolling broker upgrade. Cần một môi trường HA/staging riêng cho các failure mode đó.

## 18. Observability và tiêu chí go/no-go

Nên ghi baseline theo các khoảng thời gian có tải đại diện, sau đó so sánh trong lúc rolling upgrade và sau khi ổn định.

| Nhóm | Tín hiệu cần quan sát | Ý nghĩa |
| --- | --- | --- |
| Broker | Offline partitions, under-replicated partitions, ISR shrink | Độ bền và availability |
| Controllers | Quorum health, metadata lag, elections | Control plane có ổn định không |
| Producer | Send error rate, request latency p95/p99, retries, timeouts | Client có gặp lỗi protocol/network/ISR |
| Consumer | Group rebalance rate, commit failures, lag, fetch latency | Consumer có duy trì tiến độ không |
| Application | Processing failures, side-effect duplicate conflicts, output completeness | Độ tin cậy nghiệp vụ |
| Retry/DLT | Retry lag, oldest pending age, DLT arrivals | Lỗi downstream có bị che khỏi main lag |
| Security | SASL/TLS/authorization failures | Principal/cert/config có tương thích |
| Resource | CPU, memory, GC, network, disk I/O | Có regression hoặc contention |
| API compatibility | `UnsupportedVersionException`, unknown config/API errors | Cặp client-broker có thiếu khả năng |

Tên metric/JMX cụ thể có thể khác theo Kafka version và công cụ monitoring. Không hard-code mọi panel với tên metric của release cũ rồi kết luận metric biến mất là broker đã khỏe. Đối chiếu exporter/dashboard theo version mới.

### 18.1. Mẫu go/no-go gate

Ví dụ bảng được owner hệ thống điền **ngưỡng thực tế**:

```text
Gate G1: Controller quorum healthy                PASS/FAIL
Gate G2: OfflinePartitions = 0                     PASS/FAIL
Gate G3: ISR/reassignment trong ngưỡng quy định     PASS/FAIL
Gate G4: Producer p99 latency < SLO                PASS/FAIL
Gate G5: Consumer lag phục hồi trong cửa sổ SLA    PASS/FAIL
Gate G6: Retry/DLT forward success                 PASS/FAIL
Gate G7: Business output reconciliation 100%       PASS/FAIL
Gate G8: Rollback path còn khả dụng                PASS/FAIL
```

Không tự áp dụng ngưỡng latency tùy tiện như “p99 phải dưới 10 ms” cho mọi cluster. Với hệ thống đang xử lý rất nhiều partitions hoặc có cross-region replication, chọn thresholds từ baseline, SLO và khả năng chịu lỗi cụ thể.

### 18.2. Cảnh báo trong khi mixed versions

Các dấu hiệu nên dừng rollout:

- Controller quorum không ổn định hoặc mất khả năng cập nhật metadata.
- Partitions offline hoặc ISR phục hồi chậm bất thường.
- Producer bắt đầu báo hàng loạt errors/timeout/authorization failures.
- Consumer groups rebalance liên tục hoặc commit thất bại.
- Retry/DLT forwarding failure, lag tăng nhưng business success rate giảm.
- Clients không tương thích API/protocol hoặc schema.
- Output có dấu hiệu mất/duplicate vượt chính sách.
- Broker process mới không thể join cluster vì cấu hình/feature level không tương thích.

Đừng tiếp tục nâng broker tiếp theo chỉ để đạt đủ tỷ lệ rollout khi các gate về dữ liệu đang thất bại.

## 19. Rollback: broker rollback không giống client rollback

Một bản rollback tốt phải có **điều kiện có thể quay lui đã được xác nhận trước deployment**.

### 19.1. Client rollback

Nếu chỉ nâng Spring Kafka/client code và không thay schema payload hoặc business state, rollback thường là triển khai lại image trước. Nhưng vẫn phải kiểm tra:

- Consumer group ID/offsets có bị thay đổi không?
- Message format mới đã được publish chưa, client cũ còn đọc được không?
- Kafka Streams state/changelog có được phiên bản cũ hiểu không?
- Retry/DLT topics có thay naming và còn backlog không?
- Database schema migration có tương thích với code cũ không?
- TLS/cert/secret rotation có khiến image cũ không kết nối được không?

Vì vậy “rollback Helm chart” không phải luôn là rollback dữ liệu.

### 19.2. Broker binary rollback

Nếu broker binaries mới đã rolling xong nhưng cluster metadata feature level **chưa** được nâng và release docs cho phép quay lui, rollback binaries có thể còn khả dụng theo một trình tự được hỗ trợ.

**Không tự động hạ binary version sau khi nâng `metadata.version` hoặc bật tính năng/record format mới**. Có những thay đổi feature level/metadata không thể đảo ngược trực tiếp; cần kiểm tra tài liệu release và khả năng recover theo snapshot/backup đã được thực nghiệm.

### 19.3. Plan A và Plan B

```text
Upgrade lỗi trước feature finalization:
  Dừng rollout
  → kiểm tra cluster/clients
  → rollback binaries nếu release hỗ trợ
  → đối soát logs và output

Upgrade lỗi sau feature finalization:
  Dừng rollout
  → không hạ binary mù quáng
  → theo đường recovery/migration của release tương ứng
  → giữ evidence, kiểm tra dữ liệu
```

Trong cả hai trường hợp, không xóa topic, không reset consumer group offsets và không thay `transactional.id` ngẫu nhiên chỉ vì muốn application “chạy xanh” trở lại.

## 20. Troubleshooting các lỗi hay gặp sau upgrade

| Hiện tượng | Giả thuyết cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `UnsupportedVersionException` | Client dùng API/feature broker không hỗ trợ | Kiểm tra ApiVersions và feature flag; đổi thứ tự upgrade hoặc tắt feature mới |
| `NoSuchMethodError` / `ClassNotFoundException` | JAR Spring Kafka/Kafka clients binary mismatch | So `runtimeClasspath`, BOM và dependency overrides |
| Producer báo `NotEnoughReplicas`/`NotEnoughReplicasAfterAppend` | ISR thấp hơn policy | Khôi phục replica/ISR, không hạ durability mù quáng |
| Client kết nối bootstrap nhưng send timeout | `advertised.listeners`, DNS, TLS/leader access | Thử truy cập từng broker, xem metadata và network |
| `TopicAuthorizationException` | ACL topic mới, retry/DLT, principal thay đổi | Cấp đúng resource/action, không wildcard |
| Consumer group liên tục rebalance | Assignment/group protocol không tương thích hoặc heartbeat/poll chậm | Kiểm tra version/config members và processing time |
| Lỗi commit offset | Coordinator/rebalance hoặc commit policy thay đổi | Xem group state và ack mode, tránh skip lỗi |
| Message duplicate sau rollout | At-least-once replay, retry, đổi group ID hoặc writer không idempotent | Đối soát business key, offset timeline và side effects |
| Main lag 0 nhưng công việc chưa xong | Retry/DLT backlog | Quan sát tất cả retry destinations |
| Schema deserialization lỗi | Producer mới thay payload hoặc headers | Restore compatibility, dùng fixture cũ |
| Kafka Streams không start | State store/internal topic hoặc Streams API change | Theo upgrade guide của Streams, không reset state bừa bãi |
| Broker mới không join cluster | Feature level, controller quorum, configs không tương thích | Dừng rollout, tra đúng release guide và log controller |
| Client mới báo lỗi TLS | JDK/truststore/ciphers/hostname validation | Sửa trust chain và listener, giữ security |

### 20.1. Không gọi mọi lỗi là “Kafka version mismatch”

Một lỗi `TimeoutException` có thể do broker overload, network, DNS, ISR hay ACL chứ không nhất thiết do wire protocol. Ngược lại, một API compatibility issue có thể biểu hiện rõ hơn qua `UnsupportedVersionException` hoặc log cấu hình bị từ chối.

Quy trình debug hiệu quả:

1. Ghi rõ **client version, broker version và thời điểm rollout**.
2. Lấy stack trace/exact exception, correlation ID và broker logs liên quan.
3. Kiểm tra Kafka APIs/feature level và config đang áp dụng.
4. Loại trừ network, auth, topic/partition/ISR và serialization.
5. Đối chiếu cùng test case trên B1/C1, B2/C1, B1/C2 và B2/C2.
6. Chỉ đổi một lớp version/config tại một thời điểm nếu cần tái hiện lỗi.

Điều này tránh xu hướng rollback toàn bộ cluster khi lỗi thực tế chỉ là một KafkaTemplate dùng serializer sai sau khi nâng Spring Boot.

## 21. Quy trình nâng cấp mẫu cho một hệ thống nhiều nhóm

Giả sử tổ chức có:

```text
Cluster orders-kafka
  3+ brokers, KRaft controllers, nhiều topics và consumer groups

Ứng dụng:
  orders-api       : Spring Kafka producer
  billing-worker   : Spring Kafka transactional consumer
  reporting-worker : Spring Kafka consumer với retry/DLT
  audit-connector  : Kafka Connect
  fraud-pipeline   : Kafka Streams
```

Một kế hoạch thực tế:

### Pha 1 — Khóa phạm vi và inventoy

Chốt broker target release, Java clients hiện có, trạng thái KRaft, yêu cầu JDK và nhóm ứng dụng đặc thù. Ghi lại đường upgrade được Apache Kafka/Spring chấp nhận. Inventory mọi retry topics, Connect plugins và Streams internal topics.

### Pha 2 — Staging compatibility matrix

Chạy baseline B1/C1 và hai trạng thái chuyển tiếp B2/C1, B1/C2 khi release hỗ trợ. Không chỉ test producer `orders-api`, mà cả billing transactions, reporting DLT, Connect và Streams state recovery.

### Pha 3 — Broker rolling upgrade

Nâng theo đúng guide controller/broker, một nhóm nhỏ mỗi lượt. Mỗi bước có gate controller quorum, leader elections, ISR, produce/consume và consumer lag. Giữ metadata feature level tại mức an toàn theo release trong giai đoạn rollback window.

### Pha 4 — Soak với clients cũ

Cho workloads cũ hoạt động dưới tải đại diện, quan sát các bản ghi thực, retry failures, transaction aborts và schema payload. Chỉ khi có đủ bằng chứng mới tiếp tục finalization nếu cần.

### Pha 5 — Nâng client theo ứng dụng

Nâng theo nhóm ít rủi ro trước, ví dụ stateless producer/consumer; đến transactional consumer và Kafka Streams sau khi có test chuyên biệt. Rolling deployment để giảm rebalance; bảo vệ `group.id`, assignment và ack behavior.

### Pha 6 — Tính năng mới là thay đổi riêng

Bật consumer group protocol mới, thay compression/record format, metadata feature levels hoặc retry topic naming trong **những change request riêng**, với ma trận tương thích và rollback riêng. Không gộp “đổi protocol + nâng broker + nâng Spring Boot + đổi schema” thành một ticket khó điều tra.

### Pha 7 — Đối soát và đóng thay đổi

Đối chiếu số business events đã được nhận, trạng thái thành công, pending retry, DLT/quarantine, output cuối và lag. Xác nhận không còn retry topic cũ bị bỏ quên, không có consumer group mất offset, tài liệu vận hành đã ghi release versions mới.

## 22. Mẫu ADR và checklist trước go-live

Một **Architecture Decision Record** ngắn:

```markdown
# ADR: Independent Kafka Broker and Spring Kafka Client Upgrade

## Context
- Cluster Kafka hiện tại: B1, chế độ KRaft.
- Spring Boot / Spring Kafka / kafka-clients hiện tại: S1/SK1/C1.
- Broker mục tiêu: B2; client mục tiêu sau đó: C2.
- Billing dùng transactions, reporting dùng retry/DLT.

## Decision
- Nâng broker-first nếu B2 + C1 nằm trong compatibility window.
- Giữ client configs và business schemas trong pha broker rollout.
- Chạy staging compatibility matrix và failure tests trước.
- Finalize metadata feature level chỉ sau soak và rollback window.
- Nâng Spring Kafka/clients theo từng service, không force JAR.

## Consequences
- Cần thêm staging, test cluster và thời gian theo dõi.
- Mixed versions chỉ tồn tại trong cửa sổ upgrade được hỗ trợ.
- Client rollback phụ thuộc message/schema và application state.

## Validation
- Controller quorum, ISR, produce/consume, transactions, retry/DLT.
- Consumer rebalances, lag recovery và business idempotency.
- Bằng chứng test B1+C1, B2+C1, B1+C2 và B2+C2.
```

Các ký hiệu version là placeholders, không phải ma trận hỗ trợ chính thức. Thay bằng số release và link release notes chính xác của dự án.

### Checklist triển khai

| Câu hỏi | Điều kiện cần đạt |
| --- | --- |
| Đã biết broker/client versions thực tế chưa? | Inventory từng broker/controller và từng app runtime |
| Đã tra release notes cho đường nâng cấp chưa? | Không suy diễn từ major version chung |
| Cluster mode đã xác nhận chưa? | KRaft/ZooKeeper, migration prerequisites |
| Có plan `metadata.version`/feature finalization chưa? | Tách khỏi binary upgrade, biết rollback limit |
| Controller quorum và ISR có đủ headroom? | Rolling restart không phá availability/SLO |
| Đã test B2+C1 trước broker-first? | Có evidence producer, consumer, errors, transaction |
| Đã test B1+C2 trước client-first? | Không kích hoạt broker-only feature ngoài hỗ trợ |
| BOM Spring Boot/Spring Kafka có tương thích? | Runtime dependency tree và JDK đúng |
| `group.id`/assignment/ack mode được giữ? | Không gây đọc lại hoặc bỏ sót ngoài policy |
| Có test side effect idempotency? | Redelivery/rebalance không nhân đôi business output |
| Retry/DLT topic graph có được giữ? | Không mất backlog hoặc quyền chuyển tiếp |
| Producer/consumer có đủ ACL/TLS? | Smoke test bằng identity production-like |
| Có test schema cũ/mới? | Consumer xử lý được payload từ release trước |
| Có theo dõi go/no-go metrics? | Alert quorum, ISR, lag, errors, DLT và data checks |
| Có rollback plan trước feature finalization? | Đã biết điểm không quay lui và evidence cần giữ |
| Có runbook cho hard failure/recovery? | Dừng rollout và xử lý theo release guide |

## 23. Kết luận

Kafka được thiết kế để **broker và client có thể tiến hóa tương đối độc lập** nhờ việc thương lượng phiên bản API, nhưng khả năng đó có giới hạn và phải được kiểm chứng cho **cặp version thực tế**. Một Java client có thể còn giao tiếp với broker mới, trong khi một Spring Kafka feature, Kafka Streams state, consumer group protocol hoặc payload schema vẫn không tương thích.

Để nâng cấp an toàn:

1. Tách **broker binary**, **KRaft metadata feature level**, **Kafka Java client** và **Spring Boot/Spring Kafka stack** thành các lớp thay đổi riêng.
2. Dựng ma trận **B1/C1, B2/C1, B1/C2, B2/C2** và chọn broker-first/client-first dựa trên compatibility thật.
3. Nâng cluster bằng **rolling upgrade theo release guide**, bảo vệ controller quorum, ISR và business output.
4. Nâng ứng dụng theo từng service, tránh thay group ID, schema, retry naming, transaction và client version cùng lúc.
5. Kiểm thử **failure paths, retry/DLT, rebalances, transactions và idempotency**, không chỉ producer gửi thành công một message.
6. Finalize cluster features chỉ khi đã có đủ bằng chứng và hiểu giới hạn rollback.

Trong **Spring Kafka Reliability Operations**, một đợt nâng cấp thành công không được định nghĩa bằng việc mọi Pod và broker đều chạy binary mới. Nó được định nghĩa bằng **khả năng duy trì xử lý, bảo toàn message và business effects, quan sát được lỗi, cùng một đường phục hồi có thể giải thích và diễn tập**.

## Tài liệu tham khảo

- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): giao thức client, broker, consumer groups, configuration, security và upgrade guides.
- [Apache Kafka — Upgrade Guide](https://kafka.apache.org/documentation/#upgrade): điều kiện và thứ tự nâng cấp theo Kafka release.
- [Apache Kafka — Protocol Guide](https://kafka.apache.org/protocol.html): API versions, requests/responses và khả năng tương thích wire protocol.
- [Apache Kafka — KRaft](https://kafka.apache.org/documentation/#kraft): controller quorum và cluster metadata trong KRaft.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): các API `KafkaTemplate`, listener container, acknowledgment, transactions, retry topics và testing.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): phạm vi Kafka transactions/EOS và những giới hạn liên quan.
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): retry/DLT topology và giới hạn vận hành.
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, test utilities và integration tests.
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): auto-configuration, Kafka properties và dependency integration.
- [Gradle Dependency Management](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): kiểm tra resolved runtime dependency tree khi nâng Kafka client.
