# Canary, kiểm tra tương thích schema và theo dõi sau nâng cấp

Nâng cấp Kafka là thay đổi có thể ảnh hưởng đồng thời đến broker, KRaft metadata, producer, consumer, schema, Kafka Connect và Kafka Streams. Một cluster khởi động thành công sau khi thay binary chưa có nghĩa hệ thống đã nâng cấp an toàn. Client có thể gặp lỗi protocol, consumer có thể rebalance liên tục, schema mới có thể không đọc được dữ liệu cũ, connector có thể dừng task và stream application có thể mất nhiều thời gian phục hồi state.

Canary rollout giúp giới hạn phạm vi ảnh hưởng: triển khai thay đổi cho một broker, một nhóm client hoặc một phần traffic trước; quan sát hành vi thực tế; chỉ mở rộng khi các health gate đạt. Schema compatibility kiểm tra khả năng đọc/ghi giữa các phiên bản event trong thời gian producer và consumer cùng tồn tại. Post-upgrade monitoring xác nhận cluster đã ổn định và nghiệp vụ tiếp tục xử lý đúng.

Bài này trình bày quy trình nâng cấp Kafka theo từng giai đoạn, tập trung vào canary, schema compatibility, rolling upgrade, KRaft feature level, tương thích client/connector/Streams, theo dõi sau nâng cấp và rollback.

## 1. Phạm vi của một lần nâng cấp

Một hệ thống Kafka có nhiều thành phần với vòng đời và khả năng tương thích khác nhau:

| Thành phần | Nội dung cần kiểm tra |
|---|---|
| Broker | Binary version, listener, protocol, config và log format |
| KRaft | Controller quorum, metadata version/feature level, snapshot và voter membership |
| Producer | Client library, serializer, compression, authentication và retry behavior |
| Consumer | Client library, deserializer, group protocol, offset commit và rebalance |
| Schema Registry | Schema version, compatibility mode, subject naming và schema references |
| Kafka Connect | Worker version, connector plugin, converter, config/offset/status topics |
| Kafka Streams | Client/library version, topology, state store, changelog và processing guarantee |
| Hạ tầng | JVM, OS, container image, TLS, SASL, DNS, storage và monitoring agent |
| Ứng dụng | Event contract, database migration, downstream API và business invariant |

Không gom mọi thay đổi vào một lần triển khai nếu không thể xác định thành phần nào gây lỗi. Tách broker upgrade, schema evolution và application rollout thành các thay đổi có thể quan sát và kiểm soát riêng khi điều kiện cho phép.

## 2. Phân biệt compatibility trước khi chọn thứ tự nâng cấp

Compatibility không phải một khái niệm duy nhất.

**Broker protocol compatibility** quyết định broker mới và cũ có thể giao tiếp trong giai đoạn rolling upgrade hay không. Một số release có cơ chế giữ inter-broker protocol ở mức cũ trong khi binary đã được nâng cấp.

**Metadata compatibility** quyết định broker/controller có thể đọc và cập nhật metadata format nào. Với KRaft, metadata version hoặc feature level là một trục riêng với binary version.

**Client compatibility** quyết định client library cũ/mới có thể kết nối, xác thực và dùng API với broker hiện tại hay không.

**Schema compatibility** quyết định writer và reader có thể trao đổi record qua các phiên bản schema khác nhau hay không.

**Application compatibility** bao gồm logic nghiệp vụ, database, connector, stream state và side effect. Schema hợp lệ vẫn có thể gây lỗi nếu ý nghĩa field thay đổi.

| Trục tương thích | Câu hỏi cần trả lời |
|---|---|
| Broker ↔ broker | Các version có hỗ trợ rolling upgrade theo thứ tự dự kiến không? |
| Broker ↔ controller | KRaft role và metadata feature level có tương thích không? |
| Client ↔ broker | Client version có hỗ trợ protocol, auth và API của broker không? |
| Writer ↔ reader | Consumer cũ/mới đọc được record mới/cũ không? |
| Connector ↔ cluster | Plugin và worker version có hỗ trợ API/config hiện tại không? |
| State ↔ application | State/changelog có thể phục hồi bằng binary/topology mới không? |

Trước khi lập kế hoạch, đọc upgrade guide và release notes của từng version nguồn/đích. Không tự suy luận rằng có thể bỏ qua một major/minor release hoặc downgrade binary sau khi metadata đã được nâng cấp.

## 3. Lập upgrade plan và inventory

Upgrade plan cần có:

- Version hiện tại, version mục tiêu và đường nâng cấp được hỗ trợ.
- Danh sách broker, controller, combined node và role của từng node.
- Phiên bản Java/JVM, OS, container image và thư viện Kafka client.
- Producer, consumer, Connect worker, connector plugin và Streams application đang chạy.
- Topic quan trọng, replication factor, min.insync.replicas, retention và cleanup policy.
- Schema subjects, schema types, compatibility mode và consumer nào còn dùng schema cũ.
- Cấu hình broker/topic động, file cấu hình tĩnh, ACL, listener và certificate.
- KRaft metadata version/feature level hiện tại và các feature đã bật.
- RPO/RTO, maintenance window, owner, approver và kênh incident.
- Canary cohort, metric baseline, health gate, stop condition và rollback/forward plan.

Tạo ma trận version:

| Thành phần | Hiện tại | Mục tiêu | Đường nâng cấp | Owner |
|---|---|---|---|---|
| Kafka broker | Version đang chạy | Version đích | Theo upgrade guide | Platform |
| KRaft metadata | Feature level hiện tại | Feature level dự kiến | Sau khi binary sẵn sàng | Platform |
| Java client | Version hiện tại | Version đích | Kiểm tra client compatibility | Application |
| Schema | Subject/version hiện tại | Schema mới | Compatibility test | Data owner |
| Connect/plugin | Worker/plugin hiện tại | Worker/plugin đích | Kiểm tra plugin matrix | Integration |
| Streams | Library/topology hiện tại | Library/topology đích | State restore test | Application |

Không nâng cấp thư viện client, schema, broker và JVM cùng lúc nếu không cần thiết. Nếu sự cố xuất hiện, thay đổi theo từng lớp giúp xác định nguyên nhân nhanh hơn.

## 4. Baseline trước nâng cấp

Baseline là số liệu tham chiếu để phân biệt lỗi có sẵn với lỗi do upgrade.

### 4.1. Cluster baseline

Ghi nhận:

- Broker API response và broker/controller membership.
- Active controller, KRaft voter quorum, metadata replication lag.
- Offline partition, under-replicated partition, ISR shrink/expand.
- Produce/fetch request rate và p95/p99 request latency.
- Request error, timeout, network processor idle và request handler idle.
- CPU, heap, GC pause, disk usage, disk latency và network throughput.
- Authentication/authorization failure.

Ví dụ lệnh kiểm tra broker:

~~~bash
kafka-broker-api-versions.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG"
~~~

Kiểm tra topic và ISR:

~~~bash
kafka-topics.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --describe --topic orders.events
~~~

Với KRaft, kiểm tra quorum bằng CLI phù hợp với phiên bản đang chạy:

~~~bash
kafka-metadata-quorum.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  describe --status

kafka-metadata-quorum.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  describe --replication
~~~

### 4.2. Application baseline

| Nhóm | Metric cần ghi |
|---|---|
| Producer | Send rate, error/retry rate, request latency, buffer available, batch size |
| Consumer | Lag, records consumed, processing latency, commit failure, rebalance count |
| Connect | Connector/task state, source/sink record rate, retry, DLQ và offset progress |
| Streams | Task state, rebalance, state restore, commit latency, changelog lag |
| Schema | Registration/compatibility error, registry latency, subject/version |
| Business | Event accepted, event completed, duplicate, invalid event và end-to-end latency |

Baseline phải bao phủ giờ cao điểm và chu kỳ batch quan trọng. Nếu chỉ chụp số liệu lúc tải thấp, so sánh sau upgrade có thể gây kết luận sai.

## 5. Canary rollout là gì?

Canary là triển khai thay đổi lên một phạm vi nhỏ để kiểm tra hành vi thực tế trước khi mở rộng. Canary có thể áp dụng cho nhiều lớp:

- **Broker canary:** nâng cấp một broker trước, quan sát cluster và partition do broker đó phục vụ.
- **Client canary:** nâng cấp một instance producer/consumer hoặc một nhóm ứng dụng nhỏ.
- **Schema canary:** đăng ký schema mới và phát event thử nghiệm qua consumer đã được nâng cấp.
- **Traffic canary:** chỉ gửi một tỷ lệ nhỏ traffic qua phiên bản ứng dụng mới.
- **Connector/Streams canary:** nâng cấp một connector/task hoặc một ứng dụng stream ở môi trường/cụm thử nghiệm trước.

Canary không có nghĩa là chạy hai writer không kiểm soát trên cùng dữ liệu. Nếu hai phiên bản ứng dụng cùng nhận traffic, cần bảo đảm event contract và side effect tương thích trong giai đoạn coexistence.

~~~mermaid
flowchart TD
    A[Inventory và baseline] --> B[Compatibility gates]
    B --> C[Staging rehearsal]
    C --> D[Canary: một broker/client/cohort nhỏ]
    D --> E{Health gates đạt?}
    E -->|Không| F[Stop rollout và điều tra]
    E -->|Có| G[Expand cohort]
    G --> H{Metrics ổn định?}
    H -->|Không| F
    H -->|Có| I[Rollout toàn hệ thống]
    I --> J[Post-upgrade observation]
    J --> K[Đóng change khi đủ bằng chứng]
~~~

## 6. Thiết kế cohort và health gate

Chia rollout thành các cohort có thể nhận diện và rollback độc lập.

Ví dụ:

| Giai đoạn | Phạm vi minh họa | Điều kiện chuyển bước |
|---|---|---|
| Staging | Cluster và ứng dụng thử nghiệm | Functional test, compatibility và recovery pass |
| Canary | Một broker hoặc một instance ứng dụng | Không có lỗi mới, latency/lag trong ngưỡng |
| Cohort 1 | Nhóm nhỏ broker/client hoặc 5% traffic | Metric ổn định qua một chu kỳ tải đại diện |
| Cohort 2 | Khoảng 25% traffic | Không tăng lỗi, rebalance hoặc lag bất thường |
| Cohort 3 | Khoảng 50% traffic | Cluster và nghiệp vụ vẫn đạt SLA |
| General rollout | Phần còn lại | Có operator theo dõi và rollback plan sẵn sàng |

Tỷ lệ trên chỉ là ví dụ. Chọn kích thước cohort theo số broker, partition placement, tải, khả năng cô lập và thời gian phát hiện lỗi.

Health gate phải có ngưỡng định lượng:

- Không có offline partition ngoài kế hoạch.
- ISR đáp ứng min.insync.replicas của topic quan trọng.
- KRaft quorum giữ majority và metadata replication không tăng lag bất thường.
- Producer error/retry và p95/p99 latency không vượt ngưỡng.
- Consumer lag không tăng liên tục; rebalance hoàn tất trong thời gian dự kiến.
- Connect task và Streams task ở trạng thái RUNNING/đúng trạng thái mong muốn.
- Schema registration và deserialization không phát sinh lỗi mới.
- Business canary event đi qua đầy đủ producer → Kafka → consumer → downstream.

Không chuyển cohort chỉ vì đã hết thời gian chờ. Phải quan sát qua ít nhất một chu kỳ tải đại diện và xác nhận metric đạt.

## 7. Kiểm tra tương thích schema

Schema là hợp đồng dữ liệu giữa producer và consumer. Trong một đợt rollout, phiên bản producer mới và consumer cũ có thể cùng hoạt động; dữ liệu đã ghi trước đó vẫn có thể được replay nhiều ngày hoặc nhiều tháng sau.

Schema compatibility cần xét cả hai chiều:

- Reader mới đọc dữ liệu do writer cũ tạo ra.
- Reader cũ đọc dữ liệu do writer mới tạo ra.

Nếu topic có retention dài hoặc consumer có thể replay lịch sử, chỉ so sánh schema mới với schema gần nhất có thể chưa đủ. Cần xem xét compatibility với tất cả phiên bản schema còn có thể xuất hiện trong log.

### 7.1. Các compatibility mode phổ biến

Các mode dưới đây là khái niệm thường dùng trong Schema Registry, ví dụ Confluent Schema Registry. Kafka broker không tự thực hiện mọi quy tắc schema này; cần xác định schema registry và serializer đang dùng.

| Mode | Ý nghĩa | Tình huống triển khai |
|---|---|---|
| BACKWARD | Reader dùng schema mới đọc được dữ liệu theo schema trước | Thường nâng consumer trước producer |
| FORWARD | Reader dùng schema cũ đọc được dữ liệu theo schema mới | Có thể cần producer mới trước consumer |
| FULL | Hỗ trợ cả backward và forward giữa hai phiên bản | Khi producer/consumer cũ và mới cùng tồn tại |
| BACKWARD_TRANSITIVE | Backward với tất cả phiên bản trước | Khi cần đọc dữ liệu lịch sử |
| FORWARD_TRANSITIVE | Forward với tất cả phiên bản trước | Khi reader cũ còn có thể gặp dữ liệu mới |
| FULL_TRANSITIVE | Backward và forward với tất cả phiên bản trước | Hợp đồng cần tương thích rộng qua nhiều đời schema |

Tên mode, mặc định và phạm vi kiểm tra tùy sản phẩm/version. Không dựa vào default; đọc cấu hình compatibility thực tế của từng subject.

### 7.2. Ví dụ thay đổi schema an toàn

Schema Avro v1:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.orders",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amount", "type": "long"}
  ]
}
~~~

Schema v2 thêm field có default:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.orders",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amount", "type": "long"},
    {"name": "currency", "type": "string", "default": "VND"}
  ]
}
~~~

Với Avro, default cho field mới giúp reader mới xử lý record cũ không có field đó. Nhưng cần kiểm tra đúng schema type, union/default semantics và compatibility mode bằng công cụ thực tế trước khi đăng ký.

### 7.3. Những thay đổi schema cần thận trọng

| Thay đổi | Rủi ro |
|---|---|
| Thêm field bắt buộc không có default | Reader mới có thể không đọc record cũ |
| Xóa field đang được consumer sử dụng | Consumer hoặc logic nghiệp vụ có thể lỗi |
| Đổi field type | Có thể không tương thích hoặc làm thay đổi ý nghĩa |
| Đổi enum symbol | Reader cũ có thể gặp symbol chưa biết |
| Đổi unit/semantic, ví dụ cents thành dollars | Schema có thể hợp lệ nhưng dữ liệu sai nghiệp vụ |
| Đổi subject naming strategy | Schema mới có thể được đăng ký ở subject khác |
| Xóa schema version | Có thể phá reader/replay hoặc schema reference |

Với Protobuf, tránh tái sử dụng field number đã xóa; dùng reserved cho field number/name nếu cần. Với JSON Schema, kiểm tra required, additionalProperties, default và validation rule. Quy tắc cụ thể khác nhau theo format; không áp dụng máy móc ví dụ Avro cho mọi schema.

### 7.4. Transitive compatibility và retention

Giả sử topic giữ dữ liệu 90 ngày nhưng producer deploy schema mới mỗi tuần. Consumer mới có thể phải đọc record từ nhiều schema version. Nếu compatibility chỉ so với latest, một thay đổi có thể tương thích với phiên bản ngay trước nhưng không còn tương thích với dữ liệu cũ hơn.

Chọn transitive mode hoặc kiểm tra toàn bộ schema version còn được sử dụng khi:

- Consumer replay dữ liệu dài ngày.
- Backfill hoặc reprocessing thường xuyên.
- Nhiều ứng dụng nâng cấp không đồng thời.
- Event được lưu trữ ngoài Kafka và có thể được nạp lại.

## 8. Kiểm tra Schema Registry trước khi rollout

Quy trình kiểm tra:

1. Xác định schema subject thực tế của topic và key/value.
2. Kiểm tra naming strategy: TopicNameStrategy, RecordNameStrategy hoặc TopicRecordNameStrategy nếu nền tảng sử dụng.
3. Đọc compatibility mode đang áp dụng ở global và subject level.
4. Lấy schema version mới nhất và tất cả version còn cần hỗ trợ.
5. Chạy compatibility check trong CI trước khi merge/deploy.
6. Kiểm tra schema reference, serializer/deserializer và dependency.
7. Đăng ký schema mới theo quy trình đã phê duyệt.
8. Phát canary record và đọc bằng consumer version cũ/mới.

Ví dụ gọi compatibility API của Schema Registry:

~~~bash
curl -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data-binary @compatibility-request.json \
  "$SCHEMA_REGISTRY_URL/compatibility/subjects/orders-value/versions/latest"
~~~

File compatibility-request.json chứa schema mới theo format mà registry yêu cầu, ví dụ:

~~~json
{
  "schemaType": "AVRO",
  "schema": "{\"type\":\"record\",\"name\":\"OrderCreated\",\"namespace\":\"com.example.orders\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amount\",\"type\":\"long\"},{\"name\":\"currency\",\"type\":\"string\",\"default\":\"VND\"}]}"
}
~~~

API và content type cần khớp với Schema Registry đang dùng. Khi registry bật authentication, thêm cơ chế auth phù hợp và lấy secret từ secret manager; không ghi credential vào shell history hoặc tài liệu.

Kết quả compatibility pass chỉ xác nhận quy tắc schema của registry. Nó không chứng minh consumer xử lý đúng semantics, database migration tương thích hay mọi schema version lịch sử đều có thể deserialize. Vẫn phải chạy integration test và replay test.

## 9. Thứ tự triển khai producer và consumer

Thứ tự phụ thuộc compatibility mode và khả năng coexistence.

### BACKWARD

Reader mới đọc được record cũ. Thường triển khai consumer mới trước, sau đó mới cho producer phát field/schema mới:

1. Consumer mới được triển khai nhưng vẫn xử lý được record cũ.
2. Xác minh canary consumer đọc record cũ và record mẫu.
3. Hoàn tất rollout consumer mới cho mọi instance có thể nhận record của topic, hoặc cô lập routing để consumer cũ không nhận record mới.
4. Chỉ sau đó mới cho producer phát field/schema mới.
5. Theo dõi deserialization và business result; retire consumer cũ sau khi xác nhận không còn luồng nào cần version đó.

### FORWARD

Reader cũ đọc được record mới. Có thể cần producer phát schema mới trước khi consumer mới được rollout, nhưng phải kiểm tra toàn bộ consumer đang tồn tại và semantics:

1. Xác nhận mọi consumer cũ đọc được record mới.
2. Canary producer phát record schema mới.
3. Theo dõi consumer cũ và downstream.
4. Nâng consumer theo cohort.
5. Retire reader cũ sau khi xác nhận.

### FULL

Hai chiều tương thích giúp phiên bản cũ và mới cùng tồn tại dễ hơn, nhưng không loại bỏ yêu cầu kiểm tra semantics, transitive compatibility, field meaning và side effect.

Không dùng một thứ tự rollout cố định cho mọi schema. Hãy viết rõ writer/reader version nào tồn tại ở từng giai đoạn và kiểm tra từng cặp có thể gặp nhau.

## 10. Canary cho schema và event contract

Một schema canary nên kiểm tra:

- Producer mới serialize thành công.
- Schema ID/version được đăng ký và resolve đúng.
- Consumer cũ đọc được event mới nếu compatibility yêu cầu.
- Consumer mới đọc được record cũ trong log.
- Field default, nullability, enum và nested record hoạt động đúng.
- Event được ghi xuống database hoặc downstream đúng đơn vị/ngữ nghĩa.
- Không tăng deserialization error, DLT hoặc invalid event.

Ví dụ rollout event OrderCreated:

| Bước | Producer | Consumer | Mục tiêu |
|---|---|---|---|
| 0 | v1 | v1 | Baseline |
| 1 | v1 | v2 canary | Consumer mới đọc dữ liệu cũ |
| 2 | v1 | v2 toàn bộ | Không còn reader cũ trong đường nhận record mới |
| 3 | v2 canary | v2 toàn bộ | Kiểm tra producer mới và business result |
| 4 | v2 | v2 | Mở rộng producer sau khi health gate đạt |

Nếu đã kiểm tra FULL compatibility, reader v1 có thể tiếp tục đọc record v2 trong giai đoạn coexistence; khi đó có thể giữ consumer v1 trong cohort canary để xác minh thực tế. Với BACKWARD-only, không để consumer v1 nhận record v2 nếu reader cũ không hỗ trợ schema mới. Có thể dùng topic canary/routing riêng, nhưng phải kiểm tra đúng subject/schema ID và semantics. Nếu không thể chạy consumer cũ song song hoặc route riêng, cần maintenance window và kế hoạch dừng/restart có kiểm soát.

## 11. Canary và rolling upgrade broker

Broker upgrade cần theo đúng upgrade guide của version nguồn/đích. Các release có thể thay đổi yêu cầu về Java runtime, inter-broker protocol, log message format và KRaft metadata.

Quy trình tổng quát:

1. Xác nhận cluster khỏe và không có maintenance/reassignment khác đang chạy.
2. Chọn broker canary có blast radius thấp; kiểm tra partition leader/replica và rack placement.
3. Xác nhận replica ISR ở broker khác đủ đáp ứng min ISR khi broker canary dừng.
4. Lưu cấu hình hiện tại, package/image digest và trạng thái feature level.
5. Nâng cấp một broker theo release guide.
6. Khởi động broker, kiểm tra registration, listener, log và metrics.
7. Chờ replica catch up, ISR ổn định và request latency trở về baseline.
8. Theo dõi qua chu kỳ tải đại diện.
9. Chỉ sau khi canary đạt health gate mới tiếp tục broker tiếp theo.
10. Lặp lại cho đến hết broker/controller theo đúng thứ tự của release guide.

Với topic replication factor 1, partition trên broker dừng có thể mất availability. Với broker kết hợp controller role, việc restart còn ảnh hưởng KRaft quorum; đánh giá voter majority trước khi thao tác.

Không restart nhiều broker cùng lúc chỉ để rút ngắn thời gian. Không chạy reassignment hoặc preferred leader election đồng thời với rolling upgrade nếu chưa đánh giá tải và blast radius.

## 12. Inter-broker protocol và log message format

Một số đường nâng cấp Kafka hỗ trợ nâng binary trước nhưng tạm giữ inter-broker protocol ở mức cũ. Cách này cho phép broker mới giao tiếp với broker cũ trong rolling upgrade. Sau khi toàn bộ broker đã chạy version mới và xác minh ổn định, operator mới chuyển protocol/feature theo hướng dẫn.

Log message format cũng có thể có bước chuyển riêng. Không giả định binary version mới đồng nghĩa mọi record lập tức được ghi ở format mới.

Nguyên tắc:

- Kiểm tra release guide để biết có cần đặt inter-broker protocol version hay không.
- Giữ protocol compatibility trong giai đoạn mixed-version nếu upgrade guide yêu cầu.
- Không tự đặt giá trị protocol/format theo suy đoán.
- Chỉ nâng protocol/format sau khi tất cả broker đạt điều kiện.
- Kiểm tra consumer/client cũ có đọc được record format mới không.
- Không downgrade protocol hoặc binary sau khi đã bật feature không tương thích nếu release guide không cho phép.

Các thuộc tính và cơ chế đã thay đổi qua các Kafka release. Với version hiện đại, feature level có thể thay thế hoặc mở rộng vai trò của một số cấu hình cũ; chỉ dùng tham số được tài liệu của đúng version hỗ trợ.

## 13. KRaft metadata version và feature level

Trong KRaft, metadata log lưu trạng thái cluster và được replicate bởi controller quorum. Binary version và metadata version/feature level là hai khái niệm khác nhau.

Một số upgrade path cho phép nâng binary trong khi giữ metadata feature level cũ để duy trì khả năng tương thích. Sau khi toàn bộ node cần thiết đã nâng cấp và cluster ổn định, operator có thể nâng metadata feature level theo hướng dẫn release.

Quy tắc vận hành:

- Ghi nhận controller voter set, active controller và metadata replication trước upgrade.
- Giữ majority voter trong suốt quá trình.
- Thực hiện controller/broker theo thứ tự được quy định cho version nguồn/đích; không áp dụng một thứ tự chung cho mọi release hoặc combined node.
- Chỉ nâng metadata feature level khi toàn bộ node liên quan đã đáp ứng version requirement.
- Hiểu rõ feature level nào có thể downgrade và feature nào không thể đảo ngược.
- Có backup/restore plan cho metadata theo tài liệu KRaft; không tự copy live metadata directory.
- Không chạy storage format hoặc sửa metadata file thủ công như một cách rollback.

Nâng metadata feature level có thể là điểm không thể quay lại binary cũ. Hãy xem bước này là commit point của upgrade, có phê duyệt riêng và chỉ thực hiện sau thời gian quan sát đủ dài.

## 14. Nâng cấp Kafka client library

Client library thường có thể nâng độc lập với broker nếu version matrix cho phép. Nên canary từng ứng dụng:

1. Nâng một instance producer hoặc consumer.
2. Giữ nguyên schema và business logic nếu có thể.
3. Kiểm tra TLS/SASL, DNS, bootstrap và API compatibility.
4. Theo dõi send/consume rate, request latency, retries và errors.
5. Với consumer, theo dõi rebalance, commit, poll interval và lag.
6. Mở rộng theo cohort.
7. Sau khi ổn định, mới kết hợp thay đổi schema hoặc application logic khác.

Kiểm tra các cấu hình có thể thay đổi hành vi:

- Producer idempotence, acks, retries, delivery timeout và max in-flight requests.
- Compression type, batch size, linger và request size.
- Consumer group protocol, session/heartbeat/poll timeout và partition assignment.
- Deserializer, schema registry client và authentication.
- Transactional ID và transaction timeout.

Không copy cấu hình từ client version cũ sang version mới mà không đọc release notes. Một số default hoặc behavior có thể đổi theo phiên bản.

## 15. Nâng cấp Kafka Connect và connector plugin

Kafka Connect có worker version, converter, SMT và connector plugin; chúng có thể có compatibility matrix riêng.

Quy trình:

1. Inventory connector name, type, plugin version, task count và external system.
2. Lưu connector config và trạng thái offset hiện tại theo quy trình bảo mật.
3. Kiểm tra plugin có hỗ trợ worker version và Java runtime mục tiêu.
4. Chạy test với topic mẫu và external system thử nghiệm.
5. Nâng worker theo quy trình rolling của Connect deployment.
6. Canary một connector ít rủi ro hoặc một task nếu connector hỗ trợ.
7. Kiểm tra task state, source/sink record rate, retry, DLQ và external side effect.
8. Mở rộng từng nhóm connector.

Connector source có thể phát lại record nếu source offset hoặc task state bị reset. Connector sink có thể ghi trùng nếu external sink không idempotent. Kiểm tra behavior sau restart, không chỉ nhìn trạng thái RUNNING.

Không thay đổi đồng thời plugin, converter, schema và connector config nếu chưa có test chứng minh tương thích.

## 16. Nâng cấp Kafka Streams

Kafka Streams version mới có thể thay đổi behavior của topology, state store, serialization hoặc processing guarantee.

Trước upgrade:

- Kiểm tra compatibility giữa Streams library và broker/client.
- Xác nhận application.id, internal topic naming và partition count.
- Lưu cấu hình topology và state store.
- Xác định changelog/repartition topic retention và replication.
- Test restore state từ changelog ở môi trường tương đương production.
- Kiểm tra rolling deployment, standby replica và rebalance behavior.

Trong canary:

- Theo dõi state restore duration và changelog lag.
- Theo dõi task migration, rebalance và commit latency.
- Kiểm tra RocksDB/state store errors, disk usage và local state rebuild.
- Đối chiếu output topic và business invariant.
- Kiểm tra duplicate hoặc missing output sau restart.

Nếu topology thay đổi không tương thích với state cũ, cần versioned application ID hoặc migration/rebuild plan rõ ràng. Không xóa changelog/repartition topic để chữa lỗi state restore khi chưa xác định hậu quả.

## 17. Theo dõi trong và sau nâng cấp

Quan sát theo ba lớp: cluster, client/integration và business.

### 17.1. Broker và KRaft

| Metric/tín hiệu | Điều cần phát hiện |
|---|---|
| Offline partitions | Partition không có leader |
| Under-replicated partitions | Replica chưa theo kịp |
| ISR shrink/expand | Replica liên tục rời/vào ISR |
| Active controller changes | Controller election bất thường |
| Metadata quorum lag | Controller voter không bắt kịp metadata |
| Request latency p95/p99 | Broker xử lý chậm |
| Request error/timeout | Client không thể hoàn tất request |
| Request handler/network idle | Thread pool hoặc network processor bão hòa |
| GC pause/heap | JVM pressure hoặc allocation tăng |
| Disk latency/free space | I/O chậm hoặc nguy cơ đầy disk |

### 17.2. Producer và consumer

Producer:

- Record send rate và byte rate.
- Request latency p95/p99.
- Error, retry, timeout và delivery failure.
- Buffer available bytes và waiting threads.
- Batch size, compression ratio và serialization error.

Consumer:

- Lag theo group/topic/partition.
- Records consumed và processing latency.
- Rebalance count/duration.
- Commit failure và offset reset.
- Deserialization error, skipped record và DLT rate.
- Poll interval và thời gian xử lý mỗi batch.

### 17.3. Connect, Streams và schema

| Thành phần | Theo dõi |
|---|---|
| Connect | Connector/task state, source/sink throughput, retry, DLQ, offset progress |
| Streams | Task state, restore lag, rebalance, commit latency, state store error |
| Schema Registry | Compatibility failure, registration rate, 4xx/5xx, request latency |
| Application | Invalid event, duplicate, business failure và end-to-end latency |

Không dựa vào một dashboard tổng. Cần drill-down tới broker, topic, partition, consumer group, connector và schema subject gây bất thường.

## 18. Theo dõi theo baseline và canary event

So sánh metric sau upgrade với baseline ở cùng khung tải, không chỉ so sánh một giá trị tức thời.

Ví dụ:

| Metric | Baseline | Sau canary | Hành động |
|---|---:|---:|---|
| Producer p99 latency | 35 ms | 42 ms | Theo dõi nếu tăng nằm trong ngưỡng cho phép |
| Produce error rate | 0,02% | 0,03% | Kiểm tra loại lỗi và xu hướng |
| Consumer lag | 8.000 | 8.500 | Chấp nhận nếu lag ổn định và throughput bình thường |
| Rebalance/min | 0,1 | 2,5 | Dừng rollout, kiểm tra group churn |
| Deserialization failure | 0 | 12 | Dừng rollout schema/client, xác định schema/record lỗi |

Số liệu là ví dụ minh họa, không phải ngưỡng mặc định. Mỗi hệ thống phải đặt SLO và ngưỡng cảnh báo theo workload.

Canary event nên có eventId duy nhất, version, timestamp và marker để truy vết. Gửi qua đúng serializer, topic, partition key và consumer path. Xác minh record được deserialize, xử lý và ghi downstream đúng một lần theo semantics ứng dụng.

## 19. Stop condition và rollback

Dừng rollout khi có một trong các dấu hiệu:

- Offline partition hoặc ISR giảm dưới min ISR ngoài kế hoạch.
- KRaft quorum mất majority hoặc metadata replication lag tăng liên tục.
- Broker crash loop hoặc không register lại.
- Producer timeout/error/retry tăng vượt ngưỡng.
- Consumer rebalance liên tục, lag tăng nhanh hoặc commit failure.
- Schema compatibility check fail hoặc deserialization error xuất hiện.
- Connect task FAILED hoặc external side effect bị ghi trùng.
- Streams state restore không hoàn tất hoặc output sai.
- Business canary thất bại.

Rollback phải được quyết định theo loại thay đổi:

| Thành phần | Khả năng rollback |
|---|---|
| Application client | Thường có thể redeploy binary cũ nếu broker/schema vẫn tương thích |
| Schema | Không xóa schema version đã được ghi dữ liệu; ưu tiên deploy schema/consumer sửa tương thích |
| Connector plugin | Có thể quay plugin/worker về version cũ nếu config/state tương thích |
| Broker binary | Chỉ downgrade nếu upgrade guide cho phép và chưa vượt compatibility/metadata boundary |
| Inter-broker protocol | Có thể giữ hoặc quay về mức cũ trong phạm vi release hỗ trợ |
| KRaft metadata feature level | Có thể không downgrade được sau khi feature đã được nâng |
| Data format/retention | Có thể không khôi phục record đã ghi/xóa theo format hoặc policy mới |

Không coi downgrade binary là rollback mặc định. Sau khi metadata feature level được nâng, một số thay đổi có thể không tương thích với binary cũ. Khi đó cần forward fix hoặc restore theo quy trình chính thức.

## 20. Quy trình rollback/forward recovery

1. Dừng rollout và khóa việc mở rộng cohort.
2. Ghi nhận version và trạng thái từng broker/client/schema.
3. Xác định lớp gây lỗi từ metric/log và canary event.
4. Fence hoặc cô lập thành phần gây side effect nếu cần.
5. Nếu client/app lỗi, redeploy phiên bản ổn định đã được kiểm tra tương thích.
6. Nếu schema lỗi, dừng producer phát schema mới; giữ schema version đã đăng ký và triển khai reader/writer tương thích.
7. Nếu broker lỗi, dùng rollback binary chỉ khi upgrade guide cho phép; không sửa metadata hoặc format storage thủ công.
8. Nếu đã qua metadata feature boundary, thực hiện forward fix hoặc recovery theo runbook của release.
9. Xác minh cluster, consumer offset, data integrity và business flow.
10. Ghi nhận nguyên nhân, RPO/RTO ảnh hưởng và điều kiện thử lại.

Luôn giữ package/image cũ, config snapshot, schema version, connector config và bằng chứng baseline trong thời gian change window. Không lưu secret plaintext trong artifact rollback.

## 21. Theo dõi sau khi hoàn tất upgrade

Sau khi rollout toàn hệ thống, duy trì observation window đủ dài để bao phủ:

- Ít nhất một chu kỳ tải cao điểm.
- Batch job, scheduled producer và consumer.
- Retention/compaction hoặc log cleaner cycle nếu thay đổi có ảnh hưởng.
- Consumer restart/rebalance và replay test.
- Connector polling/flush cycle.
- Streams state recovery hoặc standby promotion.
- Backup/restore hoặc DR replication nếu upgrade ảnh hưởng tới những thành phần đó.

Trong observation window:

1. So sánh metric với baseline.
2. Kiểm tra error log và warning mới.
3. Xác minh không có offline/under-replicated partition.
4. Xác minh KRaft quorum và metadata replication ổn định.
5. Xác minh schema subjects, compatibility mode và consumer deserialization.
6. Kiểm tra producer/consumer throughput, lag và business completion.
7. Kiểm tra Connect/Streams task và downstream side effect.
8. Xác nhận alert vẫn hoạt động và không bị mute ngoài kế hoạch.
9. Lưu version inventory cuối cùng và đóng change.

Không đóng change ngay khi tất cả pod/process đã RUNNING. Chỉ đóng khi hệ thống đã qua observation window và business owner xác nhận.

## 22. Lab: canary schema và client upgrade

Mục tiêu: triển khai schema v2 thêm field optional, canary consumer mới, canary producer mới và theo dõi metric trước khi mở rộng.

### Bước 1: ghi baseline

Ghi producer send rate/error, consumer lag, deserialization error, end-to-end latency và business completion. Lưu schema subject và compatibility mode hiện tại.

### Bước 2: tạo schema v2

Thêm field currency với default phù hợp. Chạy compatibility API/CI test. Nếu test fail, không đăng ký schema và xác định consumer/record nào chưa tương thích.

### Bước 3: nâng consumer canary

Triển khai một instance consumer mới nhưng chưa thay producer. Xác minh consumer mới đọc được record cũ, deserialize đúng và ghi downstream chính xác.

### Bước 4: hoàn tất rollout consumer

Với BACKWARD-only, nâng tất cả consumer có thể nhận record của topic lên version mới trước khi producer phát schema v2. Nếu dùng FULL và đã kiểm tra reader cũ đọc được record mới, có thể giữ một consumer cũ trong cohort canary để quan sát.

### Bước 5: nâng producer canary

Cho một producer instance phát schema v2. Xác minh consumer xử lý đúng, không tăng deserialization error/DLT và business result chính xác.

### Bước 6: mở rộng cohort và quan sát

Mở rộng producer theo nhóm sau mỗi health gate. Retire client cũ khi không còn dependency. Giữ schema version lịch sử và theo dõi qua observation window. Xác nhận business owner và đóng change.

## 23. Lab: broker rolling upgrade trong staging

1. Tạo staging cluster có topology gần production.
2. Chạy workload producer/consumer đại diện và lưu baseline.
3. Xác nhận version upgrade path, Java runtime, protocol và KRaft feature level.
4. Chọn broker canary; kiểm tra replica ISR và controller voter majority.
5. Nâng binary broker đầu tiên theo release guide.
6. Kiểm tra broker registration, topic leader, ISR, request latency và client errors.
7. Chờ metric ổn định qua chu kỳ tải đại diện.
8. Tiếp tục từng broker theo thứ tự đã phê duyệt.
9. Chỉ nâng inter-broker protocol/metadata feature level ở bước được release guide yêu cầu.
10. Chạy producer/consumer/Connect/Streams regression và DR validation.
11. Ghi thời gian, lỗi, metric và rollback boundary.

Không dùng lab này để thử downgrade sau metadata feature upgrade nếu chưa có môi trường disposable và quy trình chính thức cho đúng version.

## 24. Mẫu upgrade checklist

~~~text
CHANGE ID:
CLUSTER / ENVIRONMENT:
SOURCE VERSION:
TARGET VERSION:
UPGRADE PATH:
REQUESTER / APPROVER / OPERATOR:
APPLICATION OWNERS:

INVENTORY:
- Broker/controller roles:
- Java/JVM:
- Producer/consumer clients:
- Schema subjects/modes:
- Connect workers/plugins:
- Streams applications:
- KRaft metadata feature level:

PRE-CHECK:
- Cluster health:
- ISR / offline partitions:
- KRaft quorum:
- Disk / CPU / GC / network:
- Producer / consumer baseline:
- Connect / Streams baseline:
- Schema compatibility:
- Backup / restore readiness:

CANARY:
- Canary resource:
- Cohort size:
- Observation duration:
- Health gates:
- Stop conditions:

EXECUTION:
1.
2.
3.

ROLLBACK / FORWARD RECOVERY:
- Binary boundary:
- Protocol/metadata boundary:
- Client rollback:
- Schema rollback/forward fix:

POST-CHECK:
- Broker / KRaft:
- Partition / ISR:
- Producer / consumer:
- Schema / deserialization:
- Connect / Streams:
- Business canary:
- Observation window:

RESULT:
VERIFIER:
COMPLETED AT:
FOLLOW-UP:
~~~

## 25. Ghi nhớ

| Nội dung | Nguyên tắc |
|---|---|
| Upgrade path | Theo đúng release guide của version nguồn và đích |
| Canary | Thử phạm vi nhỏ, có metric và health gate trước khi mở rộng |
| Schema | Kiểm tra reader/writer cũ-mới và dữ liệu lịch sử |
| BACKWARD/FORWARD/FULL | Chọn theo thứ tự rollout và khả năng coexistence |
| Transitive | Cân nhắc khi topic giữ dữ liệu lâu hoặc cần replay |
| Broker | Rolling từng node, chờ ISR và quorum ổn định |
| KRaft | Binary version và metadata feature level là hai trục riêng |
| Client | Nâng từng cohort, theo dõi retry, lag và rebalance |
| Connect/Streams | Kiểm tra plugin, offset, state restore và side effect |
| Rollback | Biết rõ điểm không thể downgrade; chuẩn bị forward recovery |
| Post-upgrade | Theo dõi cluster, integration và business qua observation window |

Canary, schema compatibility và post-upgrade monitoring phải là các cổng kiểm soát của cùng một quy trình. Nâng cấp chỉ được xem là hoàn tất khi broker/KRaft ổn định, client và connector tương thích, consumer đọc được dữ liệu cũ/mới theo hợp đồng, và luồng nghiệp vụ đạt SLO trong observation window.

## 26. Tài liệu tham khảo

- Apache Kafka – [Upgrade Guide](https://kafka.apache.org/documentation/#upgrade)
- Apache Kafka – [KRaft](https://kafka.apache.org/documentation/#kraft)
- Apache Kafka – [Broker Configs](https://kafka.apache.org/documentation/#brokerconfigs)
- Apache Kafka – [Producer Configs](https://kafka.apache.org/documentation/#producerconfigs)
- Apache Kafka – [Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- Apache Kafka – [Kafka Connect](https://kafka.apache.org/documentation/#connect)
- Confluent – [Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- Confluent – [Schema Registry API](https://docs.confluent.io/platform/current/schema-registry/develop/api.html)
