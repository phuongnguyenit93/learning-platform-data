# Khôi phục ứng dụng, schema, connector và secret ngoài dữ liệu topic

Khôi phục Kafka sau sự cố đa cụm không chỉ là đưa topic data sang cluster dự phòng. Một ứng dụng có thể kết nối được broker nhưng vẫn không xử lý được event nếu thiếu schema tương thích, connector config, plugin, credential, certificate, ACL hoặc cấu hình triển khai. Các thành phần này thuộc control plane và runtime của hệ thống event streaming; chúng cần được backup, version hóa và khôi phục theo đúng thứ tự.

Bài học này tập trung vào những tài sản nằm ngoài record của topic: mã ứng dụng và cấu hình runtime, Schema Registry, Kafka Connect, Kafka Streams, danh tính bảo mật, secret và quy trình failover/failback. Dữ liệu topic vẫn cần được bảo vệ bằng replication hoặc backup riêng, nhưng không thể dùng bản sao topic để thay thế toàn bộ cấu hình vận hành.

## 1. Vì sao khôi phục topic là chưa đủ?

Một pipeline điển hình có nhiều thành phần phụ thuộc:

~~~mermaid
flowchart LR
    SRC["Database / Service"] --> CONN["Kafka Connect"]
    CONN --> TOPIC["Kafka topics"]
    TOPIC --> STREAM["Kafka Streams"]
    STREAM --> OUT["Output topics"]
    OUT --> APP["Spring consumer"]
    APP --> DB["Database / API"]
    SCHEMA["Schema Registry"] -.-> CONN
    SCHEMA -.-> STREAM
    SCHEMA -.-> APP
    SECRETS["Secret manager / PKI"] -.-> CONN
    SECRETS -.-> STREAM
    SECRETS -.-> APP
    ACL["ACL / Identity"] -.-> TOPIC
    DEPLOY["Artifact / deployment config"] -.-> CONN
    DEPLOY -.-> STREAM
    DEPLOY -.-> APP
~~~

Topic có thể đã được replicate sang DR cluster nhưng:

- Consumer mới không resolve được schema ID hoặc subject/version cần thiết.
- Source connector không biết offset cuối cùng đã đọc từ database.
- Sink connector chạy sai consumer group và phát lại dữ liệu không đúng điểm.
- Kafka Streams không có application artifact, cấu hình hoặc state store phù hợp.
- Client không đăng nhập được vì thiếu SCRAM credential, certificate hoặc secret.
- Principal đăng nhập được nhưng bị từ chối vì ACL của cluster đích chưa được tạo.
- Connector plugin hoặc converter không có trên worker mới.
- Ứng dụng trỏ nhầm bootstrap server, Schema Registry URL hoặc secret path.

Do đó, kế hoạch DR phải mô tả riêng cách bảo vệ và phục hồi từng loại tài sản.

## 2. Lập danh mục tài sản cần khôi phục

Tạo inventory cho từng pipeline và gắn owner chịu trách nhiệm:

| Tài sản | Nội dung cần lưu | Cách khôi phục |
|---|---|---|
| Application artifact | JAR/container image, version, digest, SBOM | Pull đúng immutable artifact từ registry |
| Application config | Bootstrap servers, group ID, topic names, feature flags, timeout | GitOps/config repository |
| Schema Registry | Subject, version, schema text, references, compatibility config | Export/import bằng API hoặc công cụ phù hợp |
| Connect worker | Worker properties, group.id, internal topic names, plugin list | Provision worker từ IaC/image đã version hóa |
| Connector | Connector config, task settings, converter, SMT, source/sink settings | Restore config qua Connect REST API hoặc GitOps |
| Connector offsets | Source position hoặc sink consumer offsets | API/tooling tương thích phiên bản và connector |
| Kafka Streams | Artifact, application.id, topology config, SerDe, state policy | Deploy lại và restore/rebuild state |
| Security | ACL, principal, SCRAM credentials, certificate, trust chain | Recreate từ identity/PKI/secret system |
| Secret | Password, token, key, database credential | Secret manager với version và rotation policy |
| Operations | DNS, endpoint, alert, dashboard, runbook | IaC và monitoring-as-code |

Inventory phải ghi thêm phiên bản tương thích, dependency, backup location, RPO/RTO, ngày kiểm tra restore gần nhất và người sở hữu. Một file cấu hình đã backup nhưng không biết dùng cho phiên bản connector nào vẫn có thể không khôi phục được hệ thống.

### Phân loại dữ liệu backup

- **Declarative configuration**: có thể lưu trong Git dưới dạng YAML/JSON/Properties, không chứa secret plaintext.
- **Immutable artifact**: JAR, container image, plugin bundle và SBOM được lưu theo version/digest.
- **Stateful metadata**: schema versions, connector offsets, consumer offsets, ACL và identity cần quy trình export/restore riêng.
- **Secret material**: lưu trong secret manager/PKI, có audit, version, quyền truy cập và quy trình rotation.
- **Runtime state tạm thời**: task assignment, process ID, local cache hoặc local state có thể được tạo lại; không phải lúc nào cũng cần backup byte-for-byte.

## 3. Xác định RPO và RTO cho từng thành phần

RPO (Recovery Point Objective) là mức dữ liệu hoặc trạng thái có thể chấp nhận mất tính theo thời gian. RTO (Recovery Time Objective) là thời gian mục tiêu để khôi phục dịch vụ.

Không nên gán một RPO/RTO duy nhất cho cả cluster. Ví dụ:

| Thành phần | RPO cần xem xét | RTO cần xem xét |
|---|---|---|
| Application artifact | Bản release đã được publish | Thời gian deploy lại |
| Application config | Commit config gần nhất đã phê duyệt | Thời gian render và rollout |
| Schema Registry | Schema version và compatibility config đã publish | Thời gian import và kiểm tra client |
| Connector config | Cấu hình connector cuối cùng đã áp dụng | Thời gian tạo lại connector/tasks |
| Connector offsets | Source position/consumer position gần nhất | Thời gian xác định và resume đúng vị trí |
| ACL/identity | Principal và quyền đã provision | Thời gian recreate và xác minh |
| Secret/certificate | Secret version còn hiệu lực | Thời gian cấp/rotate và deploy |
| Streams state | Changelog/offset có thể replay hoặc restore | Thời gian restore/rebuild state |

Ví dụ, ứng dụng có thể deploy trong 5 phút nhưng connector CDC cần 30 phút để xác định source offset an toàn. Khi đó RTO toàn pipeline không phải 5 phút. Thành phần có thời gian phục hồi dài nhất hoặc phụ thuộc nối tiếp thường quyết định RTO thực tế.

## 4. Quản lý application artifact và cấu hình runtime

### Lưu artifact bất biến

Với Java/Spring Kafka, lưu JAR hoặc container image theo release ID và digest:

- Không ghi đè image tag như `latest` làm nguồn duy nhất cho DR.
- Lưu checksum hoặc image digest để xác nhận đúng binary.
- Giữ SBOM, dependency lock/version và thông tin build.
- Giữ phiên bản JDK, Spring Boot, Spring Kafka và Kafka client tương thích.
- Lưu plugin/serializer/converter dùng bởi ứng dụng.

Ví dụ manifest triển khai:

~~~yaml
application:
  name: orders-consumer
  image: registry.example.com/orders-consumer@sha256:REPLACE_WITH_DIGEST
  replicas: 3
  config:
    bootstrapServers: kafka-dr.example.net:9093
    schemaRegistryUrl: https://schema-dr.example.net
    consumerGroup: orders-reporting
    inputTopic: orders.events
~~~

Các giá trị trên chỉ minh họa. Credential và private key không được đặt trong manifest hoặc repository. Khi failover, thay endpoint bằng config của DR environment, còn artifact giữ đúng version đã kiểm thử.

### Tách config theo môi trường

Một ứng dụng nên có:

- Cấu hình chung: serializer, retry policy, timeout và business behavior.
- Cấu hình môi trường: bootstrap server, topic alias, Schema Registry endpoint, group ID.
- Secret reference: tên secret hoặc path trong secret manager.

Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP}
      auto-offset-reset: none
    properties:
      schema.registry.url: ${SCHEMA_REGISTRY_URL}

app:
  environment: ${APP_ENVIRONMENT}
  credentials:
    secret-reference: ${KAFKA_CLIENT_SECRET_REF}
~~~

`auto-offset-reset: none` làm ứng dụng báo lỗi nếu không có committed offset hợp lệ. Điều này có thể phù hợp khi cần tránh vô tình đọc lại từ earliest/latest, nhưng runbook phải có bước xử lý offset tường minh. Nếu dùng `earliest` hoặc `latest`, cần hiểu rõ hệ quả khi group chưa có offset ở DR cluster.

### Consumer group offsets và offset translation

Committed offsets của consumer group được lưu trong internal topic `__consumer_offsets` của từng Kafka cluster. Chúng không tự xuất hiện ở DR chỉ vì business topics đã được replicate. Không copy raw `__consumer_offsets` như một topic nghiệp vụ hoặc giả định offset số ở hai cluster luôn tương ứng.

Nếu dùng MirrorMaker 2, thiết kế và kiểm tra checkpoint/offset-sync flow. Checkpoint chứa mapping giữa offset của source cluster và offset tương ứng ở target cluster; cơ chế đồng bộ group offset sang target phụ thuộc cấu hình và phiên bản. Trong failover, dùng offset translation/checkpoint đã xác minh hoặc một quy trình reset offset có kiểm soát. Nếu không có checkpoint, chọn rõ replay từ earliest, latest hay vị trí nghiệp vụ đã lưu.

Trước khi mở consumer ở DR:

- Ghi nhận group ID, topic/partition và committed offset ở primary.
- Xác định target offset đã được dịch theo checkpoint hay cần replay.
- Kiểm tra topic/partition ở DR có cùng mapping và đã catch up đến đâu.
- Dùng idempotency/deduplication ở consumer hoặc downstream nếu replay có thể tạo duplicate.
- Chạy canary và đối chiếu business sequence trước khi mở toàn bộ traffic.

### Backup deployment configuration

Lưu cùng release:

- Deployment manifest/Helm values/Kustomize overlay.
- ConfigMap hoặc cấu hình không nhạy cảm.
- Resource request/limit, autoscaling và health probe.
- Service account, network policy và DNS.
- Lệnh rollout/rollback.
- Phiên bản schema, connector và plugin tương thích với binary.

Không chỉ backup file đang chạy trên host. Git/IaC phải là nguồn cấu hình có thể tái tạo, còn runtime cần được đối chiếu để phát hiện drift.

## 5. Backup và restore Schema Registry

Schema Registry lưu schema theo subject/version và quản lý compatibility. Producer/consumer dùng serializer để đăng ký, tra cứu hoặc resolve schema. Khi chuyển cluster, schema cần được restore trước khi triển khai producer/consumer phụ thuộc vào chúng.

### Những gì phải backup

- Danh sách subject.
- Tất cả schema version còn cần thiết.
- Schema type: AVRO, JSON hoặc PROTOBUF.
- Schema references và dependency giữa các subject.
- Compatibility mode toàn cục và theo subject.
- Registry mode hoặc trạng thái read-only nếu được sử dụng.
- Quy tắc subject naming strategy của từng ứng dụng.
- Cấu hình authentication/TLS và endpoint.

Không chỉ export latest version. Một consumer cũ có thể vẫn cần schema version trước đó để đọc record đã lưu trong retention.

### Export qua Schema Registry API

Ví dụ lấy danh sách subject:

~~~bash
curl --fail --silent --show-error \
  --user "$SCHEMA_REGISTRY_USER:$SCHEMA_REGISTRY_PASSWORD" \
  "$SCHEMA_REGISTRY_URL/subjects"
~~~

Lấy danh sách version của một subject:

~~~bash
curl --fail --silent --show-error \
  --user "$SCHEMA_REGISTRY_USER:$SCHEMA_REGISTRY_PASSWORD" \
  "$SCHEMA_REGISTRY_URL/subjects/orders-value/versions"
~~~

Lấy schema và metadata của một version:

~~~bash
curl --fail --silent --show-error \
  --user "$SCHEMA_REGISTRY_USER:$SCHEMA_REGISTRY_PASSWORD" \
  "$SCHEMA_REGISTRY_URL/subjects/orders-value/versions/3"
~~~

Lưu kết quả export vào artifact storage được kiểm soát quyền truy cập. Không đưa username/password vào shell history hoặc log CI; trong pipeline thực tế hãy lấy credential từ secret manager.

Lấy compatibility config:

~~~bash
curl --fail --silent --show-error \
  --user "$SCHEMA_REGISTRY_USER:$SCHEMA_REGISTRY_PASSWORD" \
  "$SCHEMA_REGISTRY_URL/config"

curl --fail --silent --show-error \
  --user "$SCHEMA_REGISTRY_USER:$SCHEMA_REGISTRY_PASSWORD" \
  "$SCHEMA_REGISTRY_URL/config/orders-value"
~~~

API và response field có thể khác theo sản phẩm/phiên bản Schema Registry. Kiểm tra tài liệu của registry đang triển khai và lưu cả global config lẫn subject-level override.

### Import schema vào DR registry

Đăng ký schema version bằng endpoint phù hợp của registry:

~~~bash
curl --fail --silent --show-error \
  --user "$SCHEMA_REGISTRY_USER:$SCHEMA_REGISTRY_PASSWORD" \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -X POST \
  "$SCHEMA_REGISTRY_URL/subjects/orders-value/versions" \
  --data-binary @orders-value-v3.json
~~~

Ví dụ file payload có dạng:

~~~json
{
  "schemaType": "AVRO",
  "schema": "{\"type\":\"record\",\"name\":\"Order\",\"namespace\":\"com.example\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"}]}",
  "references": []
}
~~~

Schema có references phải import dependency trước, sau đó mới import schema phụ thuộc. Kiểm tra compatibility config trước khi đăng ký; nếu registry DR đang có subject/version khác, đăng ký có thể bị từ chối hoặc tạo version sequence khác.

### Schema ID không mặc nhiên giống nhau giữa hai registry

Schema Registry thường cấp ID theo registry/cluster. Export rồi đăng ký schema vào registry mới không đảm bảo schema ID được giữ nguyên. Record Avro/Protobuf/JSON Schema có thể chứa schema ID trong wire format; consumer ở DR cần resolve đúng ID đó.

Vì vậy, với DR phải chọn rõ một trong các chiến lược:

1. Dùng cơ chế replication/backup của sản phẩm Schema Registry để bảo toàn schema ID khi chuyển cluster.
2. Dùng import mode hoặc công cụ export/import có hỗ trợ bảo toàn ID theo tài liệu phiên bản đang dùng.
3. Nếu không thể giữ ID, chuyển đổi/republish dữ liệu theo schema ID mới bằng quy trình được kiểm thử; không chỉ copy raw topic bytes rồi kỳ vọng consumer resolve được.

Không giả định hai registry độc lập sẽ tự cấp cùng ID dù schema text giống hệt. Trong failover drill, lấy một record thực từ topic đã replicate, resolve schema ID bằng DR registry và chạy consumer decode end-to-end.

## 6. Backup và restore Kafka Connect

Kafka Connect distributed mode lưu cấu hình và trạng thái connector vào các internal topics. Worker process có thể được tạo lại, nhưng config, offsets và plugin phải sẵn sàng.

### Những gì cần backup

| Thành phần | Nội dung |
|---|---|
| Worker config | `bootstrap.servers`, `group.id`, internal topic names, converters, REST settings, security |
| Connector config | Connector class, topics, source/sink settings, transforms, error handling, secret references |
| Plugin inventory | Plugin name/version, JARs, converter, SMT và dependency |
| Internal topics | Config, offset và status topics; replication/compaction config |
| Connector offsets | Source position hoặc sink offsets nếu cần resume chính xác |
| REST/network | Worker REST endpoint, authentication, TLS và network policy |

Các worker cùng một Connect cluster phải dùng cùng `group.id` và cùng tên internal topics. Nếu vô tình khởi động DR worker với group/config topic của production trong khi production còn hoạt động, hai nhóm worker có thể tranh quyền điều phối connector. Khi failover phải fencing hoặc dừng worker cũ theo kế hoạch.

### Backup connector configuration qua REST API

Liệt kê connector:

~~~bash
curl --fail --silent --show-error \
  "$CONNECT_URL/connectors"
~~~

Lấy cấu hình một connector:

~~~bash
curl --fail --silent --show-error \
  "$CONNECT_URL/connectors/orders-source/config"
~~~

Lấy trạng thái để kiểm tra task/worker:

~~~bash
curl --fail --silent --show-error \
  "$CONNECT_URL/connectors/orders-source/status"
~~~

Lưu config JSON vào repository hoặc artifact storage có versioning sau khi loại bỏ secret plaintext. Ưu tiên lưu secret reference thay cho password thực.

### Worker internal topics

Các topic thường được cấu hình qua:

~~~properties
group.id=connect-prod
config.storage.topic=connect-configs
offset.storage.topic=connect-offsets
status.storage.topic=connect-status
config.storage.replication.factor=3
offset.storage.replication.factor=3
status.storage.replication.factor=3
~~~

Trong distributed mode, config topic thường cần một partition và các internal topics cần cleanup policy phù hợp (thường là compact). Hãy tạo/provision chúng theo tài liệu Kafka Connect của phiên bản đang dùng và kiểm tra replication factor đủ cho số broker/cluster.

Khi restore cùng Connect cluster trên cùng Kafka cluster, giữ đúng internal topic và group identity để worker tiếp tục trạng thái. Khi khôi phục sang Kafka cluster khác, không chỉ đổi `bootstrap.servers` rồi trỏ vào các internal topics trống; cần quyết định restore config/offset như thế nào và kiểm tra connector semantics.

### Khôi phục connector config

Sau khi worker đã sẵn sàng, tạo connector qua REST API:

~~~bash
curl --fail --silent --show-error \
  -H "Content-Type: application/json" \
  -X POST \
  "$CONNECT_URL/connectors" \
  --data-binary @orders-source.json
~~~

File connector JSON:

~~~json
{
  "name": "orders-source",
  "config": {
    "connector.class": "com.example.OrdersSourceConnector",
    "tasks.max": "4",
    "topic.prefix": "orders",
    "connection.url": "jdbc:postgresql://db-dr.example.net:5432/orders",
    "connection.user": "orders_cdc",
    "connection.password": "${file:/opt/connect-secrets/orders.properties:password}"
  }
}
~~~

Ví dụ dùng FileConfigProvider; worker phải khai báo provider và có quyền đọc file:

~~~properties
config.providers=file
config.providers.file.class=org.apache.kafka.common.config.provider.FileConfigProvider
config.providers.file.param.allowed.paths=/opt/connect-secrets
~~~

File secret phải được provision riêng, owner/mode giới hạn và không nằm trong Git hoặc image. Với secret manager khác, dùng ConfigProvider/plugin được tổ chức phê duyệt. Khả năng masking và hiển thị config qua REST phụ thuộc provider/connector; luôn xem REST API và log là bề mặt có thể lộ thông tin nhạy cảm.

### Connector offsets và nguy cơ duplicate/missing

Source connector thường lưu source offset như database log sequence number, binlog position, WAL LSN hoặc cursor API. Sink connector thường dùng Kafka consumer offsets. Nếu restore connector với offset sai:

- Offset quá cũ có thể phát lại event, tạo duplicate ở downstream.
- Offset quá mới có thể bỏ sót event.
- Source database đã purge log cũ có thể không còn khả năng resume tại offset đã backup.
- Sink có thể đọc lại topic từ đầu nếu group ID mới không có committed offset.

Ở các phiên bản Kafka Connect có Connector Offsets REST API (Kafka 3.5 trở lên), có thể kiểm tra endpoint `GET /connectors/{name}/offsets`; thao tác thay/reset offset qua API yêu cầu connector ở trạng thái phù hợp, thường phải stop connector trước. Endpoint cụ thể và payload phụ thuộc version; xác minh bằng tài liệu REST API của release đang chạy.

Với các phiên bản hỗ trợ API này, thao tác chuẩn gồm GET để đọc offsets, PATCH để thay offsets và DELETE để reset offsets của connector. Thực hiện PATCH/DELETE khi connector đã dừng, dùng payload đúng format của plugin và ghi lại offset cũ trước khi thay đổi. Không suy diễn source offset của connector này sang connector khác dù cùng đọc một database; mỗi plugin có thể định nghĩa partition/offset schema riêng.

Không chỉnh trực tiếp `connect-offsets` bằng cách produce record thủ công. Dùng REST API được hỗ trợ hoặc công cụ chính thức của connector/plugin. Trước khi thay offset, ghi lại offset hiện tại, source retention window và kế hoạch xử lý duplicate/idempotency.

### Plugin và converter phải khớp

Connector config có thể hợp lệ về JSON nhưng worker vẫn không khởi động được task nếu thiếu JAR hoặc version plugin khác. Backup:

- Plugin artifact và checksum.
- Kafka Connect runtime version.
- Converter/Serde và schema registry client version.
- SMT và dependency.
- Java runtime version.
- Connector-specific config và license nếu có.

Khôi phục plugin lên tất cả worker trước khi tạo connector. Kiểm tra endpoint `GET /connector-plugins` trên worker/cluster và xác nhận version trước khi start.

## 7. Khôi phục Kafka Streams application và state

Kafka Streams là ứng dụng Java chạy topology trên Kafka. Khi DR, cần khôi phục binary, cấu hình, schema/Serde, security và state strategy.

### Những gì cần lưu

- Application artifact và digest.
- `application.id`.
- Topology/version và source/sink topic names.
- SerDe, schema registry endpoint và subject naming strategy.
- Processing guarantee và transactional configuration.
- State store definitions, retention/window/grace settings.
- `num.stream.threads`, instance resources và `state.dir`.
- Security principal, secret reference và ACL.
- Cấu hình internal repartition/changelog topics.

### Local state và changelog

Local state store thường có thể được tạo lại từ changelog topic hoặc replay input topic. Local RocksDB directory không phải backup duy nhất của state. Nếu xóa local state, Kafka Streams có thể restore từ changelog; nếu changelog không còn, cần rebuild từ input history đủ dài hoặc nguồn dữ liệu gốc.

Trong DR cluster:

- Xác định input topics đã được replicate đến đâu.
- Xác định changelog/repartition topics có được replicate và tương thích topology không.
- Kiểm tra consumer offsets/checkpoints đã được đồng bộ hoặc cần reset/replay.
- Đảm bảo source topic có đủ history để rebuild state nếu không restore changelog.
- Tính thời gian restore state vào RTO.

Không mặc định rằng chỉ replicate business topics là đủ để phục hồi ngay mọi stateful topology. Nếu không replicate internal topics, cần chấp nhận rebuild state từ input topics và đo thời gian thực tế.

### application.id và chạy đồng thời

`application.id` xác định consumer group và namespace internal topics của Kafka Streams trên một cluster. Khi failover, bảo đảm chỉ một active deployment điều khiển cùng logical workload trên cùng cluster. Hai instance cùng `application.id` trong cùng cluster thường là các member của một application group và chia task; điều này khác với chạy hai cluster độc lập.

Nếu chạy active-active trên hai cluster, dùng application ID và output strategy được thiết kế rõ ràng. Tránh hai ứng dụng cùng ghi vào một downstream logical stream mà không có quy tắc deduplication, conflict resolution hoặc ownership.

Nếu dùng cùng application ID trên cluster DR riêng, đó vẫn là namespace độc lập ở cluster đó; tuy nhiên, không tự động chứng minh offset/changelog mapping đã tương thích. Kiểm tra topology, internal topic names, partition count và semantics của offset translation trước khi restore.

### Exactly-once và transactional IDs

Exactly-once processing phụ thuộc Kafka transaction, producer identity, input offsets và output records. Khi chuyển cluster:

- Provision ACL cho topic, group, internal topics và transactional ID.
- Dùng đúng processing guarantee và client version.
- Không reuse transactional ID từ một producer còn đang hoạt động ở cluster cũ theo cách gây fencing ngoài dự kiến.
- Xác minh output không bị duplicate/missing trong failover test.

Exactly-once trong một Kafka cluster không tự tạo exactly-once end-to-end giữa hai cluster hoặc giữa Kafka và database. Downstream side effect vẫn cần idempotency, deduplication hoặc transaction boundary riêng.

## 8. Khôi phục principal, ACL, credential và certificate

Security state là phần dễ bị quên vì nó không nằm trong topic nghiệp vụ.

### ACL

Export ACL hiện tại để audit:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-prod.example.net:9093 \
  --command-config admin-client.properties \
  --list
~~~

Không chỉ lưu output terminal. Lưu ACL dưới dạng Infrastructure as Code hoặc danh sách lệnh provisioning có version, owner và resource scope. Khi tạo DR cluster, review principal, topic/group/transactional ID và resource pattern trước khi áp dụng.

ACL của Kafka là metadata của cluster. Replicate topic data không có nghĩa ACL tự xuất hiện ở cluster đích. Recreate ACL bằng tài khoản admin có kiểm soát, sau đó test cả thao tác được phép và thao tác phải bị từ chối.

### SCRAM credentials

Principal User:orders-producer và ACL cho principal đó không đồng nghĩa password SCRAM đã tồn tại trên cluster DR. Credential SCRAM được quản lý trong metadata của cluster; cần tạo/cấp lại qua quy trình identity provisioning.

Ví dụ cú pháp CLI để tạo SCRAM credential trên cluster đích:

~~~bash
bin/kafka-configs.sh --bootstrap-server kafka-dr.example.net:9093 \
  --command-config admin-client.properties \
  --alter \
  --entity-type users \
  --entity-name orders-producer \
  --add-config 'SCRAM-SHA-512=[iterations=8192,password=INJECT_FROM_SECRET_MANAGER]'
~~~

Đây là minh họa cú pháp; không paste password thật vào shell history, process list hoặc log CI. Dùng secret injection và quy trình quản trị credential của môi trường. Sau khi provision, cập nhật secret reference cho client và kiểm tra authentication.

### TLS và PKI

Backup hoặc có khả năng cấp lại:

- CA chain và truststore cần thiết.
- Certificate cho broker, client và Connect REST API.
- Private key được bảo vệ trong HSM/secret store hoặc cơ chế PKI.
- Subject/SAN, expiry, key usage và principal mapping rule.
- Quy trình rotate/revoke và danh sách certificate serial.

Không copy private key production sang DR nếu chính sách PKI yêu cầu identity riêng. Cấp certificate cho hostname/listener của DR, kiểm tra SAN và trust chain, sau đó deploy qua secret store/PKI.

### ACL không thay thế authentication

Khi client báo lỗi, phân biệt:

| Lỗi | Kiểm tra |
|---|---|
| Authentication failed | Password/token, SASL mechanism, certificate, truststore |
| TOPIC_AUTHORIZATION_FAILED | Principal và ACL trên topic |
| GROUP_AUTHORIZATION_FAILED | ACL trên consumer group |
| TRANSACTIONAL_ID_AUTHORIZATION_FAILED | ACL trên transactional ID |
| SSL handshake failure | SAN, CA chain, hostname verification, protocol/cipher |

Không cấp super user cho ứng dụng chỉ để vượt qua lỗi khi DR. Tạo đúng credential và ACL theo least privilege.

## 9. Secret management và rotation

Secret bao gồm password database, SASL credential, OAuth token, private key, cloud credential, API key và connector password.

Quy tắc:

- Không commit secret plaintext vào Git, connector JSON, Helm values hoặc image.
- Backup secret qua secret manager có versioning, audit và access policy.
- Lưu secret reference trong config repository.
- Có quy trình cấp quyền truy cập secret cho DR automation và người trực.
- Xác định secret nào được replicate, secret nào phải cấp lại ở DR.
- Rotate credential sau failover nếu nghi ngờ lộ hoặc theo policy.
- Kiểm tra token issuer, audience, expiry và network route ở DR.
- Đảm bảo đồng hồ hệ thống được đồng bộ để token/certificate validation hoạt động.

Một quy trình DR chỉ khôi phục được secret nếu có cả quyền truy cập vào secret manager. Backup secret không có nghĩa mọi người vận hành đều được quyền đọc; cần break-glass access có audit.

## 10. Thứ tự khôi phục theo dependency

Thứ tự gợi ý cho một DR cluster mới:

1. Xác nhận DR Kafka cluster, listener, DNS, network và metadata quorum khỏe.
2. Provision identity/secret manager access, CA và certificate cho DR.
3. Tạo principal, SCRAM/OAuth identity và ACL.
4. Khôi phục Schema Registry, subject, version, references và compatibility config.
5. Provision Connect worker internal topics, worker config và plugin.
6. Khôi phục connector config, source/sink offsets theo chiến lược đã chọn.
7. Deploy Kafka Streams artifact, application config và state restore/rebuild.
8. Deploy Spring producer/consumer với endpoint và secret của DR.
9. Chạy smoke test schema encode/decode, produce/consume và connector source/sink.
10. Mở traffic theo từng workload và theo dõi duplicate, lag, latency, ISR.

Thứ tự có thể thay đổi nếu một ứng dụng không phụ thuộc Schema Registry hoặc connector. Tuy nhiên, không start producer/consumer dùng schema trước khi schema đã sẵn sàng; không start connector trước khi plugin, credential, ACL và offset policy đã được xác nhận.

~~~mermaid
flowchart TD
    A["DR cluster và network sẵn sàng"] --> B["Secrets, PKI, principal và ACL"]
    B --> C["Schema Registry và compatibility"]
    C --> D["Connect worker, plugins và internal topics"]
    D --> E["Connector config và offsets"]
    C --> F["Streams / Spring application artifacts"]
    E --> G["Smoke test pipeline"]
    F --> G
    G --> H["Mở traffic theo từng workload"]
    H --> I["Theo dõi lag, duplicate, latency và error"]
~~~

## 11. Failover runbook

### Trước khi tuyên bố failover

- Xác định phạm vi outage: Kafka cluster, AZ, Schema Registry, Connect hay secret provider.
- Chọn cluster đích và xác nhận topic replication/checkpoint status.
- Xác định primary đã được fencing hoặc không còn ghi vào downstream dùng chung.
- Kiểm tra RPO thực tế: offset/schema/config/connector position gần nhất.
- Thông báo owner của source system, consumer và database downstream theo quy trình incident.

Fencing rất quan trọng. Nếu primary vẫn hoạt động và tiếp tục nhận write trong lúc DR cũng được mở, hai nơi có thể phát sinh event khác nhau cho cùng business key. Replication một chiều không tự giải quyết xung đột active-active.

### Thực hiện failover

1. Đặt primary ở chế độ không nhận traffic mới hoặc fencing workload theo kế hoạch.
2. Xác nhận topic replication/checkpoint đã đạt điểm phục hồi chấp nhận được.
3. Khôi phục identity, ACL, certificate và secret ở DR.
4. Import schema và kiểm tra schema ID/subject resolution.
5. Khởi động Connect worker, restore connector config và xác minh offsets.
6. Khởi động Streams application và chờ state restore/rebuild.
7. Deploy Spring applications trỏ đến DR endpoints.
8. Chạy smoke test với record canary có correlation ID.
9. Mở traffic theo nhóm nhỏ, quan sát error rate, lag, duplicate và downstream consistency.
10. Chuyển ownership/incident state sang DR và ghi lại thời điểm failover.

### Xác minh end-to-end

- Producer serialize bằng schema đúng.
- Consumer deserialize được record từ topic đã replicate.
- Connector source tiếp tục tại source position đã xác minh.
- Connector sink ghi đúng downstream và không replay ngoài policy.
- Streams state store restore đủ và topology xử lý đúng.
- ACL chỉ cho phép thao tác đã dự kiến.
- Secret không xuất hiện trong log/config response.
- p95/p99 latency và lag trong SLO.

## 12. Failback về primary

Failback không đơn giản là đổi bootstrap server về cluster cũ. Trong thời gian DR hoạt động, primary có thể đã stale về topic data, schema, connector offset, secret và application config.

Quy trình:

1. Chọn thời điểm failback và xác định DR là nguồn dữ liệu/ownership hiện tại.
2. Đồng bộ hoặc reconcile topic data từ DR về primary theo chiến lược replication.
3. Cập nhật schema registry ở primary, bao gồm version, reference, compatibility và schema ID strategy.
4. Recreate/verify ACL, principal, SCRAM credential và certificate.
5. Cập nhật Connect worker/plugin/config và source/sink offsets.
6. Đảm bảo Streams changelog/input/offset có thể restore hoặc rebuild tại primary.
7. Deploy application artifact/config tương ứng và kiểm thử bằng traffic canary.
8. Fencing DR writers tại thời điểm cutover để tránh split brain.
9. Chuyển traffic theo từng bước, xác minh không có duplicate/missing ngoài RPO đã thống nhất.
10. Giữ DR sẵn sàng ở vai trò standby và cập nhật lại backup/restore point.

Không xóa connector offsets hoặc reset consumer group chỉ để “bắt đầu sạch” nếu chưa xác định replay semantics. Việc reset có thể tạo duplicate hoặc bỏ sót dữ liệu.

## 13. Kiểm thử khôi phục định kỳ

Backup chỉ đáng tin khi đã thử restore. Mỗi lần diễn tập cần ghi:

| Kiểm thử | Tiêu chí PASS |
|---|---|
| Restore application artifact | Pull đúng digest, startup thành công |
| Restore config | Không thiếu endpoint, topic, group hoặc feature flag |
| Restore schema | Consumer DR resolve được schema của record đã replicate |
| Restore Connect | Plugin load được, connector config hợp lệ, task RUNNING |
| Restore connector offsets | Source/sink tiếp tục đúng điểm đã chọn, duplicate nằm trong policy |
| Restore Streams | State restore/rebuild xong trong RTO |
| Restore ACL/identity | Client login được và chỉ có đúng quyền |
| Restore secret/certificate | Secret resolve được, TLS/SASL handshake thành công |
| End-to-end pipeline | Canary đi qua source, topic, processing và sink |
| Failback | Cutover không tạo split brain hoặc sai offset |

Diễn tập cả trường hợp mất Schema Registry, mất Connect worker, secret manager không truy cập được và certificate hết hạn. Những lỗi này có thể làm pipeline dừng dù broker và topic vẫn khỏe.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ replicate topic data | Thiếu schema, ACL, connector hoặc secret | Inventory toàn bộ control plane |
| Chỉ export latest schema | Record cũ không decode được | Backup mọi version còn cần trong retention |
| Giả định schema ID giống nhau | Consumer không resolve wire-format ID | Dùng registry replication/import mode hoặc migration đã kiểm thử |
| Restore connector config nhưng quên plugin | Task không khởi động | Pin plugin version và kiểm tra plugin inventory |
| Restore Connect với offset trống | Source/sink replay hoặc skip dữ liệu | Xác định offset policy và dùng API hỗ trợ |
| Copy raw internal topics tùy tiện | Connect/Streams state không nhất quán | Dùng quy trình backup/restore được hỗ trợ |
| Lưu password trong Git | Credential bị lộ | Secret manager và reference |
| Restore ACL nhưng quên SCRAM credential | Authentication thất bại | Provision identity và ACL thành hai bước |
| Chạy primary và DR cùng ghi | Split brain, duplicate hoặc conflict | Fencing và ownership rõ ràng |
| Failback không cập nhật schema/config | Ứng dụng lỗi sau cutback | Đồng bộ cả data plane và control plane |
| Không kiểm tra restore | Backup hỏng hoặc thiếu dependency | DR drill theo lịch và đo RTO/RPO |

## 15. Checklist vận hành

### Trước sự cố

- [ ] Có inventory application, schema, connector, plugin, ACL, identity và secret.
- [ ] Artifact được pin bằng version/digest và có thể pull từ DR.
- [ ] Config được version hóa, không chứa secret plaintext.
- [ ] Schema Registry được export/replicate và có chiến lược schema ID.
- [ ] Connect worker/internal topics/connector config có backup.
- [ ] Connector offset strategy được tài liệu hóa theo từng plugin.
- [ ] ACL và credential có thể recreate trên cluster khác.
- [ ] Certificate/CA và secret manager có DR access.
- [ ] Đã diễn tập failover/failback và đo RTO/RPO.

### Khi failover

- [ ] Primary đã được fencing hoặc ownership đã chuyển rõ ràng.
- [ ] DR cluster, topic replication và schema resolution đạt điều kiện.
- [ ] Principal, ACL, secret và certificate hoạt động.
- [ ] Connect plugin, config và offsets đúng.
- [ ] Streams state restore/rebuild hoàn tất.
- [ ] Application trỏ đúng DR endpoint.
- [ ] Canary và downstream consistency PASS.

### Sau failover/failback

- [ ] Ghi nhận RPO/RTO thực tế và mọi sai lệch.
- [ ] Cập nhật source of truth, owner và incident timeline.
- [ ] Rotate secret nếu cần.
- [ ] Đồng bộ lại primary/DR và cập nhật backup.
- [ ] Đóng các quyền break-glass tạm thời.
- [ ] Cập nhật runbook và lịch diễn tập tiếp theo.

## 16. Bài tập tự kiểm tra

1. Vì sao replicate topic data chưa đủ để khôi phục một pipeline Kafka?
2. Những thông tin nào cần backup cho Schema Registry ngoài schema text?
3. Vì sao schema ID có thể khác giữa hai registry độc lập?
4. Kafka Connect worker internal topics có vai trò gì?
5. Vì sao không nên chỉnh trực tiếp `connect-offsets` bằng producer thông thường?
6. Source connector offset khác sink connector consumer offset ở điểm nào?
7. Kafka Streams có thể phục hồi local state store bằng cách nào?
8. ACL và SCRAM credential khác nhau như thế nào?
9. Secret manager và PKI cần được đưa vào DR plan ra sao?
10. Vì sao phải fencing primary trước khi mở traffic ở DR?
11. Failback cần đồng bộ những tài sản control plane nào?
12. Làm thế nào để chứng minh một backup thực sự đáp ứng RPO/RTO?

## Kết luận

Khôi phục ứng dụng, schema, connector và secret là phần bắt buộc của DR Kafka. Artifact phải bất biến và có thể deploy lại; config phải version hóa; Schema Registry cần giữ đủ subject/version/reference và compatibility; Connect cần worker config, plugin, connector config và offset strategy; Streams cần artifact, application identity và kế hoạch restore/rebuild state; security cần principal, ACL, credential, certificate và secret.

Hãy quản lý các tài sản này như một hệ thống có dependency, không phải các file backup rời rạc. Khôi phục theo thứ tự, fencing primary trước khi failover, xác minh schema/offset/identity và chạy end-to-end canary. Chỉ một DR drill có đo RPO/RTO và kiểm thử failback mới chứng minh được hệ thống có thể hoạt động khi cluster chính gặp sự cố.
