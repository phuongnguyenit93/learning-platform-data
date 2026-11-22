# Quyền tối thiểu cho producer, consumer, Streams và Connect

Trong Kafka, xác thực (authentication) trả lời câu hỏi **client là ai**, còn phân quyền (authorization) quyết định client đó được làm gì trên topic, consumer group, transactional ID và các tài nguyên khác. Một producer đã đăng nhập thành công vẫn có thể bị từ chối ghi topic; một consumer có thể kết nối broker nhưng không được phép tham gia consumer group.

Nguyên tắc least privilege là cấp đúng thao tác trên đúng tài nguyên mà một workload cần. Producer của dịch vụ đơn hàng chỉ được ghi topic sự kiện đơn hàng; consumer báo cáo chỉ được đọc topic đó bằng group riêng; Kafka Streams được đọc input, ghi output và quản lý internal topics của chính ứng dụng; Kafka Connect được truy cập internal topics của worker cùng các topic mà từng connector cần.

Không dùng một tài khoản chung cho tất cả ứng dụng. Khi một service bị lộ credential, phạm vi ACL hẹp giúp giới hạn dữ liệu mà kẻ tấn công có thể đọc, ghi hoặc xóa.

## 1. Authentication và authorization là hai lớp khác nhau

Luồng truy cập cơ bản:

~~~mermaid
flowchart LR
    APP["Producer / Consumer / Streams / Connect"] --> TLS["TLS: mã hóa kết nối"]
    TLS --> AUTHN["Authentication: xác định principal"]
    AUTHN --> ACL["Authorization: kiểm tra ACL"]
    ACL --> RESOURCE["Topic / Group / Transactional ID"]
    ACL -->|Từ chối| DENY["Authorization exception"]
~~~

Các cơ chế thường gặp:

| Cơ chế | Vai trò | Ví dụ |
|---|---|---|
| TLS | Mã hóa dữ liệu trên đường truyền; có thể xác thực client bằng certificate | SSL listener, mutual TLS |
| SASL/SCRAM | Xác thực username/password theo cơ chế challenge-response | SCRAM-SHA-256, SCRAM-SHA-512 |
| SASL/OAUTHBEARER | Xác thực bằng access token do identity provider cấp | JWT/OAuth 2.0 |
| SASL/PLAIN | Gửi username/password trong SASL exchange; phải chạy bên trong TLS | SASL_SSL + PLAIN |
| Kerberos/GSSAPI | Xác thực bằng ticket trong môi trường Kerberos | SASL_SSL + GSSAPI |
| Kafka ACL | Cấp quyền sau khi principal được xác định | User:orders-producer được WRITE lên orders.events |

TLS không tự quyết định một user được đọc topic nào. SASL cũng không thay thế ACL. Một client có thể xác thực đúng nhưng vẫn nhận lỗi TOPIC_AUTHORIZATION_FAILED hoặc GROUP_AUTHORIZATION_FAILED khi thao tác vượt quyền.

## 2. Principal đại diện cho service identity

Kafka authorizer kiểm tra principal mà broker nhận được sau khi authentication hoàn tất. Với SASL/SCRAM, principal thường có dạng:

~~~text
User:orders-producer
User:orders-reporting
User:orders-enricher
User:connect-worker-prod
~~~

Với mutual TLS, principal mặc định có thể dựa trên distinguished name của certificate, ví dụ:

~~~text
User:CN=orders-producer,OU=ServiceAccounts,O=Example
~~~

Có thể dùng ssl.principal.mapping.rules để ánh xạ certificate DN thành tên ngắn, dễ quản lý hơn. Quy tắc ánh xạ phải nhất quán trên các broker/controller có thực hiện authorization.

Một số nguyên tắc đặt principal:

- Tách identity theo workload và môi trường, ví dụ orders-producer-prod và orders-producer-staging.
- Không dùng tài khoản cá nhân của kỹ sư làm credential chạy ứng dụng.
- Không dùng cùng principal cho producer, consumer, Streams và Connect nếu chúng có phạm vi dữ liệu khác nhau.
- Tách tài khoản runtime khỏi tài khoản quản trị ACL.
- Đặt tên ổn định để có thể audit, rotate và thu hồi đúng workload.
- Giữ đúng chữ hoa/chữ thường; principal Kafka có phân biệt chữ hoa/chữ thường.

## 3. Bật authorizer cho KRaft

Trong KRaft, Kafka có StandardAuthorizer lưu ACL trong cluster metadata log. Cấu hình authorizer trên các node Kafka theo vai trò triển khai, gồm broker, controller hoặc node kết hợp broker/controller:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
super.users=User:kafka-acl-admin
allow.everyone.if.no.acl.found=false
~~~

Ý nghĩa:

- authorizer.class.name bật cơ chế kiểm tra ACL.
- super.users khai báo principal quản trị được miễn các kiểm tra ACL thông thường. Dùng danh sách rất nhỏ và bảo vệ credential của các principal này.
- allow.everyone.if.no.acl.found=false giữ hành vi mặc định: resource không có ACL phù hợp chỉ cho super user truy cập.

Không thêm producer, consumer hoặc connector runtime vào super.users. Làm như vậy sẽ bỏ qua mục tiêu giới hạn quyền.

Nếu bật allow.everyone.if.no.acl.found=true, mọi resource chưa có ACL có thể được truy cập bởi tất cả principal. Cấu hình này có thể hữu ích trong giai đoạn chuyển đổi có kiểm soát, nhưng không phù hợp làm mặc định cho cluster production.

### Các loại resource và operation

| Resource | Dùng để bảo vệ | Operation thường gặp |
|---|---|---|
| Topic | Dữ liệu record và metadata của topic | READ, WRITE, CREATE, DELETE, ALTER, DESCRIBE |
| Group | Consumer group và offset | READ, DESCRIBE, DELETE |
| Cluster | Thao tác phạm vi toàn cluster | CREATE, ALTER, CLUSTER_ACTION, DESCRIBE |
| TransactionalId | Transaction coordinator và producer transaction | WRITE, DESCRIBE |
| User | Một số thao tác delegation token | CREATE_TOKENS, DESCRIBE_TOKENS |

Không cấp ALL chỉ để làm một lỗi authorization biến mất. Hãy đọc exception để biết resource và operation nào bị từ chối, sau đó cấp đúng quyền đó.

## 4. Ma trận quyền tối thiểu theo workload

Giả sử hệ thống có các tài nguyên:

- Topic đầu vào: orders.events.
- Topic đầu ra: orders.enriched.
- Consumer group: orders-reporting.
- Kafka Streams application.id: orders-enricher.
- Connect worker group.id: connect-prod.
- Connect internal topics: connect-configs, connect-offsets, connect-status.

Ma trận khái quát:

| Workload | Resource | Quyền cần thiết |
|---|---|---|
| Producer | Topic đích | WRITE; DESCRIBE nếu client cần metadata và chưa được bao hàm bởi quyền hiệu lực |
| Producer tạo topic | Topic hoặc Cluster | CREATE chỉ khi workload thực sự được phép tạo topic |
| Producer giao dịch | TransactionalId | WRITE và DESCRIBE trên ID/prefix của chính producer |
| Consumer | Topic nguồn | READ |
| Consumer | Consumer group | READ trên group ID của ứng dụng |
| Kafka Streams | Input topic | READ và DESCRIBE |
| Kafka Streams | Output topic | WRITE và DESCRIBE |
| Kafka Streams | Internal repartition/changelog topics | READ, WRITE, DESCRIBE; CREATE nếu ứng dụng tự tạo topic |
| Kafka Streams | Group mang application.id | READ; DESCRIBE khi dùng Streams group protocol hoặc API yêu cầu |
| Kafka Connect worker | Connect group | READ |
| Kafka Connect worker | Config/offset/status topics | READ và WRITE; CREATE chỉ khi worker cần tạo topic chưa tồn tại |
| Source connector | Topic đích | WRITE; CREATE chỉ khi connector được cấu hình tự tạo topic |
| Sink connector | Topic nguồn và group riêng | READ trên topic, READ trên group |
| Sink connector | DLQ topic | WRITE chỉ khi cấu hình DLQ |

Ma trận thực tế còn phụ thuộc phiên bản Kafka, group protocol, exactly-once, connector plugin và việc topic đã được provision trước hay chưa. Hãy kiểm thử ACL với đúng phiên bản client/broker của môi trường.

## 5. Producer: chỉ được ghi topic được giao

Giả sử orders-producer chỉ phát sự kiện vào orders.events. Tạo ACL:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer \
  --operation Write \
  --operation Describe \
  --topic orders.events
~~~

Producer không cần READ trên topic chỉ để gửi record. Nếu topic được đội nền tảng tạo sẵn, producer cũng không cần CREATE hoặc DELETE. Cách này tránh việc một lỗi cấu hình producer tự tạo topic sai partition count, replication factor hoặc retention.

### Producer idempotent

Producer idempotent giúp tránh ghi trùng do retry trong phạm vi semantics của Kafka producer. ACL authorization cho IdempotentWrite phụ thuộc phiên bản broker và cách producer được cấu hình. Một số cấu hình/version yêu cầu quyền IdempotentWrite trên Cluster; transactional producer có transactional ID được cấp WRITE sẽ tự bao hàm idempotence theo cơ chế Kafka.

Nếu ACL matrix của phiên bản đang chạy yêu cầu IdempotentWrite, cấp quyền này có chủ đích:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer \
  --operation IdempotentWrite \
  --cluster
~~~

Đây là quyền trên Cluster resource, nên không thêm một cách máy móc. Xác minh phiên bản và lỗi authorization trước khi cấp.

### Producer transactional

Nếu producer dùng transactional.id có prefix orders-producer-tx-, cấp WRITE và DESCRIBE trên đúng prefix:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer \
  --operation Write \
  --operation Describe \
  --transactional-id orders-producer-tx- \
  --resource-pattern-type prefixed
~~~

Producer giao dịch vẫn cần WRITE trên các topic đích. Nếu dùng sendOffsetsToTransaction để commit offset của consumer group trong cùng transaction, principal còn cần quyền phù hợp trên group và topic mà consumer đã đọc. Không cấp quyền trên mọi transactional ID.

### Không cấp CREATE cho producer nếu không cần

Lệnh tiện ích --producer của kafka-acls có thể tạo ACL WRITE, DESCRIBE và CREATE trên topic. Khi cần giới hạn chặt, hãy dùng --operation tường minh như ví dụ trên để tránh cấp CREATE ngoài nhu cầu.

## 6. Consumer: giới hạn cả topic và group

Consumer cần hai phạm vi quyền:

1. READ trên topic để fetch record.
2. READ trên consumer group để join group, heartbeat và commit/fetch offset.

Ví dụ:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-reporting \
  --operation Read \
  --operation Describe \
  --topic orders.events

bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-reporting \
  --operation Read \
  --group orders-reporting
~~~

Nếu consumer đổi group.id thành orders-reporting-v2, ACL trên group cũ không tự áp dụng cho group mới. Cần provision quyền mới hoặc dùng prefix hẹp nếu nhiều group cùng thuộc một workload và naming convention được kiểm soát.

Không cấp quyền đọc tất cả topic chỉ vì consumer cần subscribe bằng regex. Nếu regex bao phủ nhiều topic, hãy tạo ACL theo prefix được quản lý và bảo đảm prefix đó không chứa dữ liệu của workload khác.

## 7. Kafka Streams: input, output, internal topics và application.id

Kafka Streams là thư viện chạy bên trong ứng dụng Java. Từ góc nhìn broker, nó là một Kafka client có một principal. Principal đó phải có quyền trên:

- Input topics mà topology đọc.
- Output topics mà topology ghi.
- Internal repartition và changelog topics.
- Consumer group mặc định có tên bằng application.id.
- Transactional ID nếu dùng exactly-once processing.

Ví dụ application.id là orders-enricher:

~~~properties
application.id=orders-enricher
bootstrap.servers=kafka-1:9093,kafka-2:9093
processing.guarantee=exactly_once_v2
~~~

ACL cho topic input và output:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-enricher \
  --operation Read \
  --operation Describe \
  --topic orders.events

bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-enricher \
  --operation Write \
  --operation Describe \
  --topic orders.enriched
~~~

Internal topics thường có prefix application.id. Có thể cấp READ, WRITE và DESCRIBE cho prefix hẹp của chính ứng dụng:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-enricher \
  --operation Read \
  --operation Write \
  --operation Describe \
  --topic orders-enricher- \
  --resource-pattern-type prefixed
~~~

Nếu ứng dụng tự tạo internal topics, cần thêm CREATE trên topic prefix đó:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-enricher \
  --operation Create \
  --topic orders-enricher- \
  --resource-pattern-type prefixed
~~~

Chỉ cấp CREATE khi ứng dụng thật sự phải tạo internal topics. Có thể để tài khoản provisioning tạo trước các topic này với partition count, replication factor và cleanup policy đúng yêu cầu; khi đó runtime không cần CREATE. Tên internal topic có thể thay đổi theo topology và phiên bản, vì vậy hãy kiểm tra bằng Topology.describe() và tài liệu của phiên bản đang triển khai.

Group của Streams mặc định dùng application.id:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-enricher \
  --operation Read \
  --group orders-enricher
~~~

Với group.protocol=streams trên Kafka 4.4 trở lên, cần thêm DESCRIBE trên group và các topic được topology sử dụng. Group protocol này cũng yêu cầu DESCRIBE trên source/internal topics; CREATE trên internal topics chỉ cần khi chúng chưa được tạo sẵn. Hãy đối chiếu ACL matrix của broker version trước khi rollout.

Khi bật exactly_once_v2, Kafka Streams dùng transactional producer. Cấp WRITE và DESCRIBE trên prefix transactional ID được ứng dụng sử dụng, thay vì mở quyền trên mọi transactional ID:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-enricher \
  --operation Write \
  --operation Describe \
  --transactional-id orders-enricher- \
  --resource-pattern-type prefixed
~~~

Transactional ID thực tế có thể chứa process/thread identifier và phụ thuộc phiên bản Kafka Streams. Kiểm tra cấu hình, log và ACL error của phiên bản đang chạy để chọn prefix phù hợp.

## 8. Kafka Connect: tách quyền worker và quyền connector

Kafka Connect có hai lớp client:

- Worker dùng Kafka client để tham gia Connect cluster và đọc/ghi config, offset, status internal topics.
- Source/sink connector dùng producer/consumer để ghi hoặc đọc dữ liệu nghiệp vụ.

Theo mặc định, các connector trên cùng worker chia sẻ principal mà worker dùng để xác thực với Kafka. Vì vậy, nếu dùng chung principal, ACL của worker phải bao gồm cả internal topics lẫn topic nghiệp vụ của các connector. Muốn tách quyền theo connector, cần cấu hình client override với credential riêng và chính sách override cho phép đúng các cấu hình bảo mật cần thiết.

### ACL cho Connect worker

Giả sử:

- group.id là connect-prod.
- config.storage.topic là connect-configs.
- offset.storage.topic là connect-offsets.
- status.storage.topic là connect-status.

Worker cần READ trên group:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-worker-prod \
  --operation Read \
  --group connect-prod
~~~

Worker cần READ và WRITE trên ba internal topics:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-worker-prod \
  --operation Read \
  --operation Write \
  --topic connect-configs

bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-worker-prod \
  --operation Read \
  --operation Write \
  --topic connect-offsets

bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-worker-prod \
  --operation Read \
  --operation Write \
  --topic connect-status
~~~

Nếu worker phải tự tạo internal topic chưa tồn tại, cần CREATE trên từng topic tương ứng. Có thể tạo topic trước bằng tài khoản provisioning để worker không cần quyền CREATE. Trong distributed mode, config topic nên có một partition; config, offset và status topics nên được replicate và cấu hình compaction theo hướng dẫn của Kafka Connect.

Nếu bật exactly-once support cho Connect hoặc exactly.once.source.support ở trạng thái preparing, worker có thể cần WRITE và DESCRIBE trên transactional ID của Connect cluster, có dạng connect-cluster-connect-prod. Với Kafka cũ hơn 2.8, kiểm tra thêm yêu cầu IdempotentWrite theo tài liệu tương ứng; quyền IdempotentWrite cluster đã deprecated cho các phiên bản mới.

Ví dụ cấp quyền transactional ID cho worker khi exactly-once support được bật:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-worker-prod \
  --operation Write \
  --operation Describe \
  --transactional-id connect-cluster-connect-prod
~~~

### ACL cho Source connector

Source connector ghi dữ liệu vào topic Kafka. Ví dụ connector orders-cdc ghi vào raw-orders:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-orders-cdc \
  --operation Write \
  --topic raw-orders
~~~

Nếu connector được bật topic.creation.enable và cần tự tạo topic chưa tồn tại, cấp thêm CREATE trên topic đích. Nếu topic được provision sẵn, không cấp CREATE.

Một số CDC connector còn dùng topic schema history hoặc topic nội bộ riêng ngoài framework Kafka Connect. Các topic đó phải được cấp ACL theo tài liệu của plugin cụ thể.

Nếu bật exactly-once source support, source task có thể cần WRITE và DESCRIBE trên transactional ID theo từng task. Với group.id connect-prod và connector tên orders-cdc, prefix thường dùng cho task ID là connect-prod-orders-cdc-:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-orders-cdc \
  --operation Write \
  --operation Describe \
  --transactional-id connect-prod-orders-cdc- \
  --resource-pattern-type prefixed
~~~

Trong chế độ exactly-once source, connector có thể còn cần DESCRIBE trên offsets storage topic. Chỉ cấp các quyền này khi connector hỗ trợ và worker đã bật exactly-once source support; tên transactional ID phải khớp với group.id, connector name và task ID hiệu lực.

### ACL cho Sink connector

Sink connector orders-search đọc orders.events bằng consumer group mặc định connect-orders-search:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-orders-search \
  --operation Read \
  --operation Describe \
  --topic orders.events

bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-orders-search \
  --operation Read \
  --group connect-orders-search
~~~

Nếu connector đặt consumer.group.id hoặc consumer.override.group.id, ACL phải áp dụng đúng group ID hiệu lực đó.

Nếu cấu hình errors.deadletterqueue.topic.name=orders-search-dlq, principal của sink connector cần WRITE trên topic DLQ:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:connect-orders-search \
  --operation Write \
  --topic orders-search-dlq
~~~

Với sink connector hỗ trợ exactly-once, consumer cần đọc ở isolation.level=read_committed để bỏ qua record thuộc transaction đã abort. Cấu hình này không tự làm connector đạt exactly-once; plugin sink phải hỗ trợ semantics đó và worker/connector phải được cấu hình tương ứng.

### Tách principal theo connector

Để connector không dùng chung quyền dữ liệu với worker:

1. Tạo principal riêng cho từng source/sink connector.
2. Cấu hình producer/consumer override của connector với security credentials riêng.
3. Bật chính sách connector.client.config.override.policy theo allowlist phù hợp phiên bản Kafka.
4. Chỉ cho phép các key cấu hình cần thiết; không mở override tùy ý.
5. Cấp ACL của principal connector trên topic/group mà connector đó thực sự dùng.
6. Giữ ACL internal topics của Connect worker trên principal worker.

Ví dụ connector có thể khai báo client override riêng (các giá trị secret phải được inject từ secret store):

~~~json
{
  "name": "orders-search",
  "config": {
    "connector.class": "com.example.OrdersSinkConnector",
    "topics": "orders.events",
    "consumer.override.security.protocol": "SASL_SSL",
    "consumer.override.sasl.mechanism": "SCRAM-SHA-512",
    "consumer.override.sasl.jaas.config": "org.apache.kafka.common.security.scram.ScramLoginModule required username=\"connect-orders-search\" password=\"INJECT_FROM_SECRET_STORE\";"
  }
}
~~~

Đây là cấu hình minh họa; plugin có thể có các thuộc tính riêng. Worker phải cho phép những key override này theo connector.client.config.override.policy và phiên bản Kafka. Khi dùng override, principal của connector cần ACL trên topic/group nghiệp vụ; worker principal vẫn cần ACL trên internal topics của Connect.

Từ Kafka 4.2, tài liệu khuyến nghị dùng Allowlist cho connector.client.config.override.policy; chính sách này sẽ là mặc định từ Kafka 5.0. Những override có thể nạp class như sasl.jaas.config hoặc sasl.login.class có thể dẫn đến thực thi mã trong worker JVM. Chỉ cho phép chúng khi REST API chỉ dành cho người vận hành đáng tin cậy.

## 9. Bảo vệ Kafka Connect REST API và secrets

Connect REST API là control plane quản lý mọi connector trong cùng cluster. Mặc định REST API không bật authentication. Người truy cập được API có thể tạo, sửa, dừng, restart hoặc xóa connector; API không có cơ chế phân quyền riêng theo connector.

Vì vậy:

- Đặt REST API trong management network, không expose trực tiếp ra Internet.
- Bật HTTPS cho REST listener hoặc đặt reverse proxy có mTLS/OIDC/authentication phù hợp.
- Chỉ cấp quyền gọi REST API cho operator được tin cậy như quản trị viên Connect.
- Tách Connect cluster nếu các team không tin cậy lẫn nhau cần quyền quản trị độc lập.
- Chỉ cài plugin, converter, SMT và REST extension từ nguồn tin cậy; plugin chạy trong worker JVM với quyền của tiến trình.
- Bảo vệ file cấu hình worker, plugin path và filesystem của host.

Connector config có thể chứa credential của database, cloud storage hoặc API. Trong distributed mode, config được lưu vào config.storage.topic. Nếu nhúng password trực tiếp trong connector config, người có quyền đọc topic này có thể lấy được nội dung đó.

Ưu tiên ConfigProvider/secret manager để chỉ lưu tham chiếu secret trong config topic. Tuy vậy, người có quyền gọi REST API có thể đọc cấu hình connector và có thể resolve secret reference; ConfigProvider không thay thế việc giới hạn REST API. File-based provider cần giới hạn allowed.paths và quyền đọc file trên host.

## 10. Cấu hình authentication cho client

Ví dụ client dùng SASL_SSL với SCRAM-SHA-512:

~~~properties
bootstrap.servers=kafka-1:9093,kafka-2:9093
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-producer" password="INJECT_FROM_SECRET_STORE";
~~~

Chuỗi INJECT_FROM_SECRET_STORE chỉ là placeholder. Đưa secret vào runtime qua secret manager, file được bảo vệ hoặc cơ chế triển khai phù hợp; không commit password vào Git, Docker image hay log.

Nếu dùng mutual TLS:

~~~properties
bootstrap.servers=kafka-1:9093,kafka-2:9093
security.protocol=SSL
ssl.truststore.location=/etc/kafka/secrets/client.truststore.jks
ssl.keystore.location=/etc/kafka/secrets/orders-producer.keystore.jks
ssl.keystore.password=INJECT_FROM_SECRET_STORE
ssl.key.password=INJECT_FROM_SECRET_STORE
~~~

Truststore xác minh certificate của broker; keystore chứa certificate/private key của client. Bảo vệ file và password bằng quyền filesystem, secret manager và quy trình rotate certificate.

## 11. Cấu hình Spring Kafka

Spring Boot có thể truyền các thuộc tính Kafka client qua spring.kafka.properties:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9093,kafka-2:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-producer" password="INJECT_FROM_SECRET_STORE";
    producer:
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: orders-reporting
      properties:
        isolation.level: read_committed
~~~

Ví dụ dùng cùng principal cho producer và consumer để minh họa cấu hình client; trong production nên tách identity/credential theo vai trò. Nếu cùng một Spring application vừa produce vừa consume, có thể cấu hình producer/consumer properties riêng khi cần principal khác nhau. ACL phải khớp với principal thực tế của từng client.

## 12. Cấu hình Kafka Streams với security properties

Kafka Streams dùng các Kafka client nội bộ. Có thể cấu hình security trên Properties truyền vào StreamsConfig:

~~~java
Properties props = new Properties();
props.put(StreamsConfig.APPLICATION_ID_CONFIG, "orders-enricher");
props.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "kafka-1:9093,kafka-2:9093"
);
props.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "SASL_SSL");
props.put(SaslConfigs.SASL_MECHANISM, "SCRAM-SHA-512");
props.put(
    SaslConfigs.SASL_JAAS_CONFIG,
    "org.apache.kafka.common.security.scram.ScramLoginModule required "
        + "username=\"orders-enricher\" "
        + "password=\"INJECT_FROM_SECRET_STORE\";"
);
props.put(
    StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
    StreamsConfig.EXACTLY_ONCE_V2
);
~~~

Các import cần thiết gồm Properties, CommonClientConfigs, SaslConfigs, StreamsConfig. Credential trong ví dụ là placeholder; hãy nạp từ secret store khi khởi động.

Không cấu hình một principal dùng được mọi topic. ACL cho orders-enricher chỉ nên bao phủ input topic, output topic, internal topics theo application.id, group của ứng dụng và transactional ID khi dùng EOS.

## 13. Tài khoản quản trị ACL và lệnh KRaft

Tạo file admin-client.properties để kafka-acls CLI xác thực bằng principal quản trị:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="kafka-acl-admin" password="INJECT_FROM_SECRET_STORE";
~~~

Từ Kafka KRaft, quản lý ACL qua Admin API bằng --bootstrap-server. Không dùng --zookeeper cho cluster KRaft.

Ví dụ liệt kê ACL của principal:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --list \
  --principal User:orders-producer
~~~

Liệt kê mọi ACL ảnh hưởng đến topic, gồm literal, wildcard và prefixed patterns:

~~~bash
bin/kafka-acls.sh --bootstrap-server kafka-1:9093 \
  --command-config admin-client.properties \
  --list \
  --topic orders.events \
  --resource-pattern-type match
~~~

Trên Windows, dùng script tương ứng trong bin\windows, ví dụ kafka-acls.bat. Tên file command config và secret phải được bảo vệ như credential quản trị.

Tài khoản quản trị ACL là tài khoản đặc quyền. Chỉ dùng nó trong quy trình provisioning có audit; không đưa credential này vào ứng dụng producer, consumer, Streams hoặc Connect.

## 14. Kiểm thử quyền theo nguyên tắc allow và deny

Sau khi cấp ACL, cần kiểm tra cả thao tác được phép và thao tác phải bị từ chối.

| Kiểm thử | Kết quả mong đợi |
|---|---|
| orders-producer ghi orders.events | Thành công |
| orders-producer ghi payments.events | Bị từ chối |
| orders-producer đọc orders.events | Bị từ chối nếu không có ACL READ |
| orders-reporting đọc orders.events với group orders-reporting | Thành công |
| orders-reporting đọc payments.events | Bị từ chối |
| orders-reporting dùng group khác | Bị từ chối nếu group đó không được cấp |
| orders-enricher đọc input và ghi output | Thành công |
| orders-enricher ghi topic của ứng dụng khác | Bị từ chối |
| Connect sink đọc topic đã khai báo | Thành công |
| Connect sink đọc topic ngoài phạm vi | Bị từ chối |

Một số lỗi authorization thường gặp:

| Lỗi | Ý nghĩa | Hướng kiểm tra |
|---|---|---|
| TOPIC_AUTHORIZATION_FAILED | Principal không có quyền trên topic | Kiểm tra topic name, operation và principal |
| GROUP_AUTHORIZATION_FAILED | Không có quyền trên consumer group | Kiểm tra group.id hiệu lực |
| TRANSACTIONAL_ID_AUTHORIZATION_FAILED | Không có quyền trên transactional ID | Kiểm tra transactional.id và prefix ACL |
| CLUSTER_AUTHORIZATION_FAILED | Thao tác yêu cầu quyền Cluster | Xác định API nào đang gọi CREATE/ALTER/IdempotentWrite |
| Authentication failed | Credential, certificate hoặc SASL config sai | Kiểm tra listener, mechanism, secret và trust chain |

Đừng khắc phục bằng cách thêm ALL trên cluster hoặc wildcard topic. Hãy xác định chính xác principal, resource và operation trong log broker/client, sau đó cấp quyền hẹp nhất.

## 15. Quy trình triển khai least privilege

1. Liệt kê workload: producer, consumer, Streams app, Connect worker và từng connector.
2. Gán principal riêng cho từng workload hoặc connector cần tách quyền.
3. Liệt kê topic nguồn/đích, group ID, application.id, transactional ID và internal topic prefix.
4. Xác định thao tác tối thiểu cho từng tài nguyên.
5. Tạo topic, group policy và internal topics bằng tài khoản provisioning khi phù hợp.
6. Cấu hình TLS/SASL và secret injection cho từng client.
7. Tạo ACL literal cho user topics; chỉ dùng prefixed pattern cho internal resources có namespace riêng.
8. Kiểm tra ACL hiệu lực, bao gồm wildcard và prefix đang áp dụng.
9. Chạy kiểm thử positive và negative trước khi đưa ứng dụng vào production.
10. Ghi nhận owner, mục đích, ngày cấp và thời hạn rà soát cho mỗi principal/ACL.
11. Rotate credential/certificate và thu hồi ACL khi workload ngừng hoạt động.

## 16. Những lỗi thiết kế quyền thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Dùng chung principal cho mọi service | Một credential bị lộ có thể đọc/ghi nhiều domain | Tách principal theo workload |
| Cấp ALL trên mọi topic | Runtime có thể đọc, ghi, xóa hoặc thay đổi nhiều dữ liệu | Cấp operation cụ thể trên topic cụ thể |
| Cấp CREATE/DELETE cho producer | Ứng dụng có thể tạo hoặc xóa tài nguyên ngoài trách nhiệm | Để provisioning/admin quản lý topic |
| Chỉ cấp READ topic cho consumer | Consumer không join/commit được group | Cấp READ trên group ID |
| Quên internal topics của Streams | Streams không tạo được changelog/repartition topic | Cấp quyền prefix nội bộ hoặc provision topic trước |
| Cấp cluster CREATE cho Streams không giới hạn | Ứng dụng có thể tạo topic tùy ý | Cấp CREATE trên prefix internal topic hoặc pre-create |
| Connect dùng một principal quá rộng | Một connector có thể truy cập topic của connector khác | Dùng credential override theo connector và policy hạn chế |
| Expose Connect REST API công khai | Người ngoài có thể thay đổi connector và cấu hình worker | Giới hạn mạng, HTTPS và authentication |
| Lưu password trong connector config | Secret có thể nằm trong config topic/log | Dùng ConfigProvider và bảo vệ REST/config topic |
| Dùng super.users cho runtime | ACL không còn giới hạn được service | Chỉ dùng super user cho quản trị |

## 17. Bài tập thực hành

Thiết lập quyền cho một pipeline đơn hàng:

- orders-producer ghi orders.events.
- orders-reporting đọc orders.events với group orders-reporting.
- orders-enricher đọc orders.events, ghi orders.enriched và dùng application.id orders-enricher.
- Connect source ghi raw-orders.
- Connect sink đọc orders.enriched bằng group connect-search-sink và ghi lỗi vào connect-search-dlq.

Yêu cầu:

1. Tạo principal riêng cho từng workload.
2. Tạo ACL literal cho user topics.
3. Tạo ACL prefix hẹp cho internal topics của Streams.
4. Chỉ cấp CREATE khi runtime phải tự tạo internal topic.
5. Cấp ACL group đúng group ID thực tế.
6. Bảo vệ Connect config/offset/status topics bằng principal worker.
7. Thử ghi/đọc một topic ngoài phạm vi và xác nhận bị từ chối.
8. Liệt kê ACL hiệu lực bằng resource-pattern-type match.
9. Thu hồi quyền producer rồi xác nhận ứng dụng không thể tiếp tục ghi.
10. Ghi lại ma trận quyền để đội vận hành có thể audit và tái tạo.

## 18. Bài tập tự kiểm tra

1. Authentication khác authorization ở điểm nào?
2. Vì sao producer cần WRITE trên topic nhưng không cần READ?
3. Vì sao consumer phải có quyền trên cả topic và group?
4. Khi nào producer cần quyền trên TransactionalId?
5. Vì sao Kafka Streams cần ACL cho internal repartition/changelog topics?
6. Khi nào có thể bỏ CREATE khỏi principal Kafka Streams?
7. Kafka Connect worker principal khác connector data principal ở điểm nào?
8. Vì sao Connect REST API cần được bảo vệ như một control plane quản trị?
9. Vì sao không nên dùng super.users cho ứng dụng runtime?
10. Làm thế nào để kiểm tra một ACL prefixed hoặc wildcard có đang cấp quyền ngoài dự kiến?

## Kết luận

Least privilege trong Kafka bắt đầu bằng việc định danh rõ từng workload và tài nguyên mà nó cần truy cập. Producer chỉ ghi topic được giao; consumer chỉ đọc topic bằng group riêng; Streams chỉ truy cập input, output, internal topics và application group của chính nó; Connect worker quản lý internal topics, còn từng connector chỉ đọc/ghi các topic trong phạm vi tích hợp.

KRaft StandardAuthorizer và kafka-acls CLI cho phép quản lý ACL tập trung. Dùng principal riêng, ACL literal hoặc prefix hẹp, tách tài khoản provisioning khỏi runtime, bảo vệ Connect REST API và secret, rồi kiểm thử cả thao tác được phép lẫn bị từ chối. Khi phiên bản Kafka hoặc chế độ exactly-once thay đổi, hãy đối chiếu ACL matrix của đúng phiên bản trước khi rollout.

## Tài liệu tham khảo

- Apache Kafka 4.4 — Authorization and ACLs: https://kafka.apache.org/44/security/authorization-and-acls/
- Apache Kafka 4.4 — Streams Security: https://kafka.apache.org/44/streams/developer-guide/security/
- Apache Kafka 4.4 — Kafka Connect Security Model: https://kafka.apache.org/44/security/security-model-connect/
- Apache Kafka Connect User Guide — ACL requirements and connector security: https://kafka.apache.org/44/kafka-connect/user-guide/
