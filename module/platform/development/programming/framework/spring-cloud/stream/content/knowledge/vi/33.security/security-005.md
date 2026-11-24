# Tách tài khoản quản trị khỏi tài khoản chạy ứng dụng

## 1. Vì sao phải tách hai loại tài khoản?

Trong hệ thống Spring Cloud Stream, ứng dụng kết nối tới Kafka, RabbitMQ hoặc Pulsar để publish và consume message. Broker cũng cần người hoặc hệ thống tự động tạo topic, queue, namespace, virtual host, ACL, policy, quota và cấu hình bảo mật. Hai nhóm công việc này có phạm vi quyền rất khác nhau.

- **Tài khoản quản trị (administrative identity):** dùng bởi quản trị viên hoặc pipeline provisioning để tạo, thay đổi và kiểm tra tài nguyên broker. Quyền có thể bao gồm quản lý topic/namespace, cấp ACL, cấu hình policy, tạo user/role và thay đổi cấu hình cluster.
- **Tài khoản chạy ứng dụng (runtime identity):** dùng bởi service khi ứng dụng khởi động và xử lý message. Quyền thường chỉ cần đọc một số topic/queue, ghi một số destination và tham gia đúng consumer group/subscription.

Nếu ứng dụng dùng credential quản trị, một lỗi cấu hình, lỗ hổng trong dependency hoặc việc lộ secret có thể cho phép kẻ tấn công xóa topic, tạo user, thay ACL hoặc đọc dữ liệu ngoài phạm vi nghiệp vụ. Tách danh tính giúp giới hạn thiệt hại: runtime chỉ có thể thực hiện các thao tác mà chức năng của service yêu cầu.

~~~mermaid
flowchart TD
    H[Platform administrator] -->|MFA / short-lived admin identity| P[Provisioning pipeline]
    P -->|Create topics, queues, ACLs, policies| B[(Messaging broker)]
    S[Spring Cloud Stream application] -->|Runtime credential from secret manager| R[Least-privilege runtime principal]
    R -->|Read / write only approved destinations| B
    R -. No user, ACL or cluster administration .-> B
~~~

Nguyên tắc cốt lõi là ứng dụng chỉ được cấp quyền cần để thực hiện luồng message của nó. Quyền quản trị tài nguyên broker được thực hiện trong quy trình riêng, có người chịu trách nhiệm và có thể kiểm toán.

## 2. Phân biệt danh tính, vai trò và credential

Các khái niệm này thường bị gọi chung là “user”, nhưng chúng có ý nghĩa khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Identity / principal | Danh tính được broker xác thực | svc-orders-prod, platform-provisioner |
| Role | Tập quyền gắn với danh tính | orders-consumer, topic-provisioner |
| Credential | Bằng chứng để chứng minh danh tính | Password, client certificate, SASL secret, OAuth token |
| ACL / permission | Quyền trên resource cụ thể | Read topic orders.events, Write topic orders.accepted |
| Destination | Nơi ứng dụng gửi hoặc nhận message | Kafka topic, Rabbit exchange/queue, Pulsar topic |

Một runtime principal có thể được cấp quyền đọc topic đầu vào và ghi topic đầu ra. Tài khoản quản trị có thể được cấp role provisioning trong phạm vi cluster hoặc namespace. Credential là vật liệu xác thực; nó không thay thế việc thiết kế quyền.

Tên danh tính nên thể hiện service, môi trường và mục đích, ví dụ svc-order-processor-prod. Tránh dùng một tài khoản chung application cho tất cả service vì khi audit sẽ khó xác định service nào đã thực hiện thao tác.

## 3. Mô hình hai luồng cấp quyền

Một quy trình triển khai an toàn có hai luồng độc lập:

1. **Provisioning:** pipeline hoặc administrator tạo destination, group/subscription, policy và quyền cho runtime principal.
2. **Runtime:** ứng dụng lấy credential runtime từ secret manager, kết nối broker và chỉ đọc/ghi các destination đã được cấp.

Ví dụ khi triển khai order-processor:

| Công việc | Danh tính thực hiện | Quyền cần có |
|---|---|---|
| Tạo topic orders.events | Provisioner | Create/Describe topic |
| Tạo topic orders.accepted | Provisioner | Create/Describe topic |
| Cấp ACL cho service | Provisioner | Alter ACL trong phạm vi được giao |
| Consume orders.events | Runtime principal | Read topic, Describe topic, Read group |
| Produce orders.accepted | Runtime principal | Write topic, Describe topic |
| Xóa topic production | Administrator theo quy trình phê duyệt | Quyền quản trị có kiểm soát |

Ứng dụng không cần quyền tạo user hoặc cấp ACL để thực hiện việc đọc/ghi message thường ngày. Nếu binder cần kiểm tra metadata hoặc khai báo resource khi khởi động, hãy xác định chính xác quyền tối thiểu mà binder version yêu cầu và cân nhắc provision resource trước.

## 4. Quyền tối thiểu cho ứng dụng Spring Cloud Stream

Trước khi cấp quyền, liệt kê mọi thao tác messaging của service:

- Input binding nào consume?
- Output binding nào produce?
- Service có cần consumer group hoặc subscription riêng không?
- Có retry topic, dead-letter queue (DLQ) hoặc retry destination không?
- Binder có cần đọc metadata, khai báo exchange/queue hoặc kiểm tra schema không?
- Ứng dụng có thực sự cần tạo destination tự động không?

Từ danh sách này, tạo một permission matrix. Ví dụ:

| Resource | Runtime svc-order-processor-prod | Provisioner |
|---|---|---|
| orders.events | Read, Describe | Create, Describe, Alter |
| orders.accepted | Write, Describe | Create, Describe, Alter |
| orders.retry | Write/Read theo retry flow | Create, Describe, Alter |
| orders.DLT | Write hoặc Read theo error flow | Create, Describe, Alter |
| Consumer group order-processor | Read | Quản lý theo chính sách cluster |
| ACL và user | Không | Cấp quyền trong phạm vi được giao |
| Cluster configuration | Không | Chỉ role quản trị phù hợp |

Không cấp quyền chỉ vì “có thể cần sau này”. Khi chức năng mới yêu cầu thêm destination, thay đổi quyền qua provisioning pipeline và review thay đổi như một phần của release.

## 5. Kafka: tách principal quản trị và principal ứng dụng

Kafka xác thực client thành principal, ví dụ User:svc-order-processor-prod. Authorization có thể dùng ACL hoặc cơ chế authorizer tương ứng của nền tảng Kafka. Tài khoản quản trị có quyền quản lý topic và ACL; runtime principal chỉ được cấp quyền trên topic và consumer group mà service sử dụng.

Ví dụ các quyền cần thiết cho service đọc topic đầu vào và ghi topic đầu ra:

~~~text
Principal: User:svc-order-processor-prod

Topic orders.events:
  Read
  Describe

Topic orders.accepted:
  Write
  Describe

Group order-processor:
  Read
~~~

Các quyền chính xác phụ thuộc Kafka version, authorizer và thao tác binder thực hiện. Ví dụ ACL CLI minh họa với Kafka ACL authorizer:

~~~bash
kafka-acls.sh --bootstrap-server kafka.prod.example:9093 \
  --command-config admin-client.properties \
  --add --allow-principal 'User:svc-order-processor-prod' \
  --operation Read --operation Describe \
  --topic orders.events

kafka-acls.sh --bootstrap-server kafka.prod.example:9093 \
  --command-config admin-client.properties \
  --add --allow-principal 'User:svc-order-processor-prod' \
  --operation Write --operation Describe \
  --topic orders.accepted

kafka-acls.sh --bootstrap-server kafka.prod.example:9093 \
  --command-config admin-client.properties \
  --add --allow-principal 'User:svc-order-processor-prod' \
  --operation Read --group order-processor
~~~

Các lệnh trên chạy bằng credential quản trị được cấp riêng trong admin-client.properties. Không đóng gói file quản trị đó trong image hoặc classpath của ứng dụng. Pipeline provisioning nên giữ file/secret trong môi trường thực thi riêng, có quyền truy cập được kiểm soát.

## 6. Kafka: tránh tự động tạo topic bằng quyền runtime

Kafka binder có thể hỗ trợ tự tạo topic hoặc tăng partition tùy cấu hình. Nếu runtime principal được cấp quyền Create/Alter để binder tự provision, danh tính ứng dụng sẽ có phạm vi lớn hơn quyền produce/consume thông thường.

Với production, cân nhắc tạo topic và ACL trước bằng pipeline quản trị, sau đó tắt cơ chế auto-create/auto-add-partitions nếu phù hợp với kiến trúc và binder version.

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          autoCreateTopics: false
          autoAddPartitions: false
~~~

Tên property và hành vi mặc định cần được kiểm tra theo phiên bản Kafka binder đang dùng. Một số cluster cũng có thể tự tạo topic theo broker-level setting; tắt auto-create ở binder không thay thế việc cấu hình broker và ACL đúng.

Nếu ứng dụng thực sự cần tạo destination động, không cấp quyền cluster-wide cho mọi instance. Hãy dùng provisioning service riêng hoặc một danh tính tự động có giới hạn resource, kiểm soát input và audit.

## 7. Kafka: cấu hình runtime credential cho Spring Cloud Stream

Ứng dụng chỉ nhận credential runtime. Ví dụ với SASL/SCRAM qua biến môi trường:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: ${KAFKA_RUNTIME_JAAS}
~~~

KAFKA_RUNTIME_JAAS phải được secret manager hoặc nền tảng triển khai inject vào process. Giá trị thật không nằm trong repository, Dockerfile, image layer, log hoặc file cấu hình được commit.

Runtime principal cần quyền Read/Describe trên topic input, Write/Describe trên topic output và quyền Read trên consumer group nếu ứng dụng consume. Nếu binder cần thêm thao tác như DescribeConfigs hoặc IdempotentWrite, xác minh từ cấu hình producer/consumer thực tế và chỉ cấp phần cần thiết.

## 8. Kafka: tài khoản quản trị nên được sử dụng ở đâu?

Tài khoản quản trị Kafka có thể được sử dụng bởi:

- Pipeline tạo topic, partition, retention và cleanup policy.
- Pipeline cấp hoặc thu hồi ACL cho service principal.
- Quy trình tạo/quản lý SCRAM user hoặc certificate mapping.
- Công cụ vận hành kiểm tra cluster và thay đổi cấu hình được phê duyệt.

Tài khoản này không nên được sử dụng bởi:

- Spring Boot application khi khởi động.
- Kafka binder producer/consumer.
- Job xử lý message theo lịch chạy hàng ngày.
- Script nằm trong image runtime.
- Developer laptop để chạy service production.

Nếu cần kiểm tra quyền runtime, đăng nhập bằng chính runtime principal trong một job kiểm tra riêng với phạm vi read/write thử nghiệm. Không thử “sửa lỗi ACL” bằng cách thay credential runtime thành admin.

## 9. RabbitMQ: tách administrator, management tag và permission trên virtual host

RabbitMQ có user, virtual host và permission riêng. Administrator có thể tạo vhost, user, policy và cấp permission. Runtime user của ứng dụng chỉ nên có quyền trên virtual host và resource cần thiết.

RabbitMQ phân biệt user tags với resource permissions:

- User tag như administrator, management hoặc monitoring kiểm soát khả năng truy cập giao diện/quản trị management.
- Permission trên virtual host kiểm soát quyền configure, write và read đối với exchange/queue.

Có management tag không đồng nghĩa với việc user được cấp mọi quyền trên mọi vhost; ngược lại, một ứng dụng có thể cần quyền đọc/ghi queue nhưng không cần management UI.

Ví dụ tạo vhost và user bằng tài khoản quản trị:

~~~bash
rabbitmqctl add_vhost /orders
rabbitmqctl add_user svc_order_processor_prod "$RABBIT_RUNTIME_PASSWORD"
rabbitmqctl set_permissions -p /orders svc_order_processor_prod \
  '^orders\.(events|accepted|retry|DLT)$' \
  '^orders\.(accepted|retry|DLT)$' \
  '^orders\.(events|retry)$'
~~~

Các biểu thức regex ở ví dụ chỉ minh họa phạm vi resource; cần điều chỉnh theo tên exchange/queue thực tế và cách binder provision. Không cấp tag administrator hoặc management cho runtime user.

## 10. RabbitMQ: hiểu ba loại permission

RabbitMQ quản lý ba loại permission trên mỗi virtual host:

- configure: tạo, xóa hoặc thay đổi resource như exchange và queue theo phạm vi regex.
- write: publish vào exchange hoặc thực hiện thao tác ghi tương ứng.
- read: consume từ queue hoặc thực hiện thao tác đọc tương ứng.

Spring Cloud Stream Rabbit binder có thể khai báo exchange, queue và binding khi khởi động. Nếu để binder tự provision, runtime user thường cần quyền configure trên các tên resource tương ứng ngoài quyền đọc/ghi. Đây là lý do cần quyết định rõ cách provisioning.

Hai mô hình triển khai:

1. **Pre-provision:** administrator/pipeline tạo exchange, queue và binding trước. Runtime user chỉ nhận quyền cần cho publish/consume nếu binder được cấu hình không tự khai báo resource.
2. **Runtime declaration có giới hạn:** runtime user được cấp configure trên một tập tên resource cụ thể, không có quyền quản trị user/vhost/policy.

Không dùng regex .* cho mọi permission nếu ứng dụng chỉ cần vài destination. Khi đổi tên destination, thay đổi regex và resource qua review.

## 11. RabbitMQ: cấu hình runtime credential

Ví dụ cấu hình kết nối runtime:

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: ${RABBITMQ_PORT:5671}
    username: ${RABBITMQ_RUNTIME_USERNAME}
    password: ${RABBITMQ_RUNTIME_PASSWORD}
    virtual-host: /orders
    ssl:
      enabled: true
~~~

Tên property SSL và cách cấu hình truststore/client certificate có thể khác theo Spring Boot/Rabbit client version. Cấu hình phải bật xác thực server certificate và dùng trust material phù hợp; không tắt kiểm tra hostname để né lỗi TLS.

Tài khoản runtime được giới hạn trong vhost /orders. Nếu ứng dụng cần publish sang /operations, hãy tạo binder/connection riêng và user riêng cho vhost đó, hoặc cấp permission có chủ đích theo kiến trúc. Không dùng một administrator password để kết nối tất cả vhost.

## 12. RabbitMQ: không cấp quyền quản trị chỉ để xem queue

Ứng dụng thường không cần Management HTTP API. Health indicator hoặc metrics có thể dùng endpoint/credential riêng tùy cấu hình. Nếu cần giám sát broker, nên cấp user monitoring chỉ đọc số liệu và tách nó khỏi runtime message principal.

Không đưa management credential vào Spring Cloud Stream binder chỉ để kiểm tra queue. Binder kết nối AMQP để publish/consume; management API là bề mặt quản trị riêng.

Khi điều tra backlog, administrator hoặc monitoring identity có thể xem queue state. Runtime service chỉ cần xử lý message trong phạm vi quyền đã được cấp.

## 13. Pulsar: tách superuser, admin role và runtime role

Pulsar xác thực client thành role và hỗ trợ authorization theo tenant, namespace và topic. Role quản trị có thể quản lý tenant/namespace, policy, permission và resource. Runtime role của ứng dụng thường chỉ cần quyền produce và/hoặc consume trên namespace/topic đã xác định.

Ví dụ phân tách:

| Role | Công việc | Phạm vi |
|---|---|---|
| platform-admin | Quản trị cluster và cấu hình bảo mật | Cluster theo chính sách tổ chức |
| namespace-provisioner | Tạo namespace, topic, policy và grant permission | Tenant/namespace được giao |
| svc-orders-prod | Consume và produce event đơn hàng | Namespace commerce/orders |
| svc-audit-prod | Consume event để audit | Namespace/topic audit được cấp |

Không dùng superuser token cho ứng dụng. Superuser có thể vượt qua nhiều ranh giới quyền; nếu bị lộ, phạm vi ảnh hưởng rất lớn.

## 14. Pulsar: cấp quyền producer và consumer theo namespace

Ví dụ minh họa thao tác quản trị bằng Pulsar admin CLI:

~~~bash
pulsar-admin namespaces grant-permission commerce/orders \
  --role svc-orders-prod \
  --actions produce,consume
~~~

Quyền produce và consume ở ví dụ được cấp trên namespace commerce/orders. Nếu service chỉ cần consume, bỏ produce; nếu chỉ phát event, bỏ consume. Có thể cấp quyền topic-level khi mô hình authorization và phiên bản Pulsar hỗ trợ, giúp giới hạn hẹp hơn.

Việc tạo tenant/namespace, đặt retention, backlog quota, subscription policy hoặc cấp role là công việc provisioning. Runtime role không nên được phép tự cấp quyền hoặc sửa policy namespace.

## 15. Pulsar: runtime authentication bằng token hoặc TLS

Pulsar hỗ trợ nhiều phương thức xác thực, ví dụ token hoặc TLS certificate. Runtime credential cần đại diện cho role ứng dụng và được giới hạn bằng authorization policy.

Ví dụ minh họa cấu hình client token theo Spring Boot Pulsar client properties:

~~~yaml
spring:
  pulsar:
    client:
      service-url: ${PULSAR_SERVICE_URL}
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        params:
          token: ${PULSAR_RUNTIME_TOKEN}
~~~

Đường dẫn property và cách truyền tham số authentication phụ thuộc phiên bản Spring Boot Pulsar client và Spring Cloud Stream Pulsar binder. Xác nhận cấu hình được hỗ trợ trong dependency version của dự án; không sao chép nguyên xi giữa các phiên bản nếu cấu trúc property thay đổi.

Token được phát cho svc-orders-prod chỉ có quyền produce/consume đã cấp. Không cấp token của platform-admin cho application pod. Token cần có TTL hoặc quy trình thu hồi/rotation phù hợp.

## 16. Bảng so sánh cách tách quyền theo broker

| Broker | Danh tính quản trị | Danh tính runtime | Quyền runtime thường cần |
|---|---|---|---|
| Kafka | Principal quản lý topic, ACL, user và cluster policy | SASL/OAuth/mTLS principal của service | Read/Describe topic, Write topic, Read group |
| RabbitMQ | User quản lý vhost, user, policy và permission | User riêng trong virtual host | Read/Write; Configure giới hạn nếu binder tự provision |
| Pulsar | Superuser/admin/provisioner role | Role xác thực bằng token hoặc TLS | Produce/Consume trên namespace/topic |

Tên permission và chi tiết authorization khác nhau theo broker version và plugin. Mục tiêu thiết kế giống nhau: runtime principal chỉ có quyền trên resource mà service sử dụng.

## 17. Không đặt admin credential trong cấu hình ứng dụng

Không lưu admin username/password, superuser token hoặc client certificate quản trị trong:

- application.yml hoặc application-prod.yml được commit.
- Dockerfile, build argument hoặc image layer.
- GitHub Actions/GitLab CI log hoặc artifact công khai.
- Kubernetes ConfigMap.
- file test fixture được đóng gói vào JAR.
- biến môi trường dùng chung cho mọi service.

Runtime credential cũng là secret, nhưng cần được quản lý riêng và không được thay bằng admin credential. Secret runtime chỉ được cấp cho workload cụ thể, namespace cụ thể và môi trường cụ thể.

Ví dụ cấu hình chỉ tham chiếu biến môi trường:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: ${KAFKA_RUNTIME_JAAS}
~~~

File cấu hình chứa tên biến; secret manager/secret mount cung cấp giá trị. Không in giá trị secret khi debug.

## 18. Secret manager và cấp phát theo workload

Một nền tảng triển khai có thể lấy runtime secret từ:

- Kubernetes Secret được đồng bộ từ external secret manager.
- HashiCorp Vault hoặc cloud secret manager.
- Workload identity và token ngắn hạn do nền tảng phát hành.
- Certificate manager cấp client certificate cho mTLS.

Luồng tham khảo:

~~~mermaid
sequenceDiagram
    participant W as Workload identity
    participant SM as Secret manager
    participant A as Spring Cloud Stream app
    participant B as Broker
    W->>SM: Authenticate workload
    SM->>W: Runtime secret for this service
    W->>A: Mount / inject runtime credential
    A->>B: Authenticate as svc-orders-prod
    B-->>A: Authorize only assigned topics / queues
~~~

Credential nên được cấp theo service và môi trường. Không dùng một secret cho development, staging và production. Khi service bị xóa hoặc đổi quyền sở hữu, thu hồi credential tương ứng.

Nếu nền tảng hỗ trợ workload identity hoặc short-lived token, ưu tiên cơ chế này để giảm thời gian credential tồn tại. Nếu dùng password tĩnh, phải có rotation và quy trình phân phối an toàn.

## 19. Rotation credential không làm gián đoạn ứng dụng

Rotation cần được thiết kế trước khi secret hết hạn. Quy trình phổ biến:

1. Tạo credential mới cho cùng runtime principal hoặc principal phiên bản mới.
2. Cấp đúng ACL/permission cho credential mới.
3. Đưa secret mới vào secret manager.
4. Khởi động hoặc reload workload theo khả năng hỗ trợ của client/binder.
5. Xác nhận connection mới được xác thực và message flow hoạt động.
6. Thu hồi credential cũ sau khi mọi instance đã chuyển đổi.
7. Ghi audit event và thời điểm rotation.

Với một số cơ chế, có thể giữ đồng thời hai credential trong một giai đoạn ngắn. Với cơ chế không hỗ trợ nhiều credential cùng lúc, cần rollout có kiểm soát hoặc dùng principal phiên bản mới rồi chuyển traffic.

Không thu hồi credential cũ trước khi credential mới được xác minh. Cũng không để credential cũ tồn tại vô thời hạn sau rotation.

## 20. Phân tách theo môi trường và theo service

Mỗi môi trường cần identity và resource scope riêng:

| Môi trường | Runtime principal | Broker scope |
|---|---|---|
| Development | svc-orders-dev | Cluster/topic development |
| Staging | svc-orders-stg | Cluster/topic staging |
| Production | svc-orders-prod | Cluster/topic production |

Không dùng svc-orders-dev để truy cập production chỉ vì tiện cấu hình. Không dùng chung principal cho order-processor, billing-service và audit-service; mỗi service có luồng dữ liệu và trách nhiệm khác nhau.

Nếu nhiều instance của cùng một service cần chia sẻ consumer group, chúng có thể dùng chung runtime principal của service hoặc danh tính workload được cấp theo cơ chế nền tảng. Nếu tổ chức yêu cầu audit theo instance, có thể dùng principal riêng cho workload instance/replica, nhưng cần quản lý số lượng ACL và rotation phù hợp.

## 21. Quyền quản trị phải có thời hạn và có audit

Quyền admin có thể gây tác động lớn, do đó nên được cấp theo vai trò và thời hạn:

- Administrator người dùng xác thực bằng danh tính cá nhân và MFA.
- Pipeline provisioning dùng service identity riêng, không chia sẻ password của con người.
- Quyền admin được giới hạn cluster, tenant hoặc namespace theo trách nhiệm.
- Thay đổi production được review và lưu lại người yêu cầu, người duyệt, nội dung thay đổi.
- Credential quản trị có rotation và quy trình thu hồi.
- Break-glass account được cất giữ, giám sát và chỉ dùng trong sự cố được ghi nhận.

Không dùng một tài khoản admin chung cho cả đội. Danh tính riêng giúp truy vết ai hoặc pipeline nào đã thay ACL, xóa topic hay đổi policy.

## 22. Provisioning pipeline nên idempotent và có kiểm soát

Pipeline tạo resource và quyền cần có thể chạy lại an toàn. Một lần chạy lại không nên tạo thêm user trùng, cấp ACL rộng hơn hoặc xóa resource ngoài phạm vi.

~~~mermaid
flowchart TD
    A[Review change request] --> B[Validate destination and permission matrix]
    B --> C[Provisioner authenticates with admin identity]
    C --> D[Create / verify broker resources]
    D --> E[Grant least-privilege runtime permissions]
    E --> F[Verify runtime principal access]
    F --> G[Publish audit result]
~~~

Pipeline nên kiểm tra:

- Destination có đúng naming convention và owner không?
- Runtime principal có tồn tại không?
- ACL đã có chưa; nếu có thì có đúng phạm vi không?
- Permission mới có rộng hơn permission được review không?
- Topic/queue policy có phù hợp retention, DLQ và quota không?
- Sau khi cấp quyền, runtime principal đọc/ghi được đúng resource cần thiết không?
- Resource ngoài phạm vi có tiếp tục bị từ chối không?

Kiểm tra cả quyền được phép và quyền bị từ chối giúp phát hiện cấu hình ACL quá rộng.

## 23. Kiểm thử quyền runtime theo nguyên tắc allow và deny

Một test security tốt không chỉ xác nhận service có thể đọc topic hợp lệ. Nó cũng cần xác nhận service không thể thực hiện thao tác quản trị hoặc truy cập resource ngoài phạm vi.

Ví dụ ma trận kiểm thử:

| Thao tác | Kết quả mong đợi |
|---|---|
| Consume orders.events | Cho phép |
| Produce orders.accepted | Cho phép |
| Consume payroll.events | Từ chối |
| Tạo topic mới | Từ chối |
| Xóa topic production | Từ chối |
| Tạo broker user hoặc grant ACL | Từ chối |
| Đọc metadata cần thiết của topic được cấp | Cho phép nếu binder cần |

Thử nghiệm bằng runtime credential thật trong môi trường kiểm thử. Không dùng admin credential trong test rồi suy ra runtime permission đúng.

## 24. Kiểm tra binder không vô tình dùng admin credential

Khi có nhiều binder hoặc nhiều broker, cần kiểm tra từng connection:

1. Tên binder và endpoint có đúng cluster/vhost/namespace không?
2. Username/principal/token được inject có phải runtime identity không?
3. Credential có thuộc môi trường đúng không?
4. ACL có chỉ bao phủ destination của binding không?
5. Binder có tự động tạo resource và do đó yêu cầu quyền Configure/Create không?
6. Có cấu hình global hoặc biến môi trường nào vô tình override credential không?
7. Log có ghi principal/username hoặc endpoint nhạy cảm không? Nếu có, cần lọc dữ liệu nhạy cảm.

Với nhiều binder, mỗi binder có thể cần runtime principal riêng. Ví dụ kafka-orders-prod chỉ đọc topic đơn hàng, còn kafka-analytics-prod chỉ ghi topic phân tích. Không dùng admin credential chung để giải quyết vấn đề kết nối giữa các binder.

## 25. Giới hạn quyền khi binder cần tự khai báo resource

Một số binder hỗ trợ auto provisioning exchange/queue/topic hoặc DLQ. Cần phân biệt quyền ứng dụng xử lý message và quyền khai báo resource:

- Produce/consume là hoạt động dữ liệu trong runtime.
- Create/declare/configure là hoạt động thay đổi topology broker.
- Grant/revoke ACL hoặc policy là hoạt động quản trị bảo mật.

Nếu binder bắt buộc declare resource lúc khởi động, có thể cấp quyền Configure hẹp cho tên exchange/queue được phép. Không vì vậy mà cấp quyền tạo user, sửa vhost hoặc quản lý cluster.

Một lựa chọn khác là provision resource trước và cấu hình binder không tự tạo. Cách này thường giúp runtime principal có ít quyền hơn và việc thay đổi topology được kiểm soát qua pipeline.

## 26. Xử lý khi runtime credential bị lộ

Nếu nghi ngờ runtime secret bị lộ:

1. Xác định service, môi trường, principal và destination bị ảnh hưởng.
2. Tạo credential thay thế hoặc principal mới với cùng quyền tối thiểu.
3. Phân phối credential mới qua secret manager.
4. Rollout/reconnect workload và xác nhận message flow.
5. Thu hồi credential cũ.
6. Kiểm tra audit log của broker để tìm hoạt động bất thường.
7. Kiểm tra ACL hoặc permission có bị thay đổi trái phép không.
8. Nếu cần, tạm thời thu hẹp hoặc thu hồi quyền và xử lý backlog theo runbook.
9. Ghi nhận nguyên nhân lộ secret và cập nhật quy trình.

Không phản ứng bằng cách thay credential runtime thành admin để “khôi phục nhanh”. Nếu credential runtime có quyền hẹp, việc thu hồi sẽ giới hạn phạm vi sự cố.

## 27. Những lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Cách sửa |
|---|---|---|
| Dùng admin user trong application.yml | Lộ credential có quyền rộng | Tạo runtime principal riêng |
| Dùng cùng một user cho mọi service | Không cô lập sự cố và khó audit | Một identity theo service/môi trường |
| Runtime được quyền tạo/xóa mọi topic | Lỗi ứng dụng có thể phá dữ liệu | Pre-provision hoặc giới hạn resource |
| Rabbit runtime user có tag administrator | Có quyền management không cần thiết | Bỏ admin tag, chỉ cấp vhost permission |
| Pulsar application dùng superuser token | Vượt qua ranh giới authorization | Token cho role produce/consume riêng |
| Kafka runtime có quyền Alter ACL | Có thể tự mở rộng quyền | Chỉ provisioner được cấp quyền ACL |
| Secret đặt trong ConfigMap hoặc Git | Credential dễ bị lộ | Secret manager/Secret mount |
| Không rotation credential | Secret tồn tại quá lâu | Lịch rotation và quy trình chuyển đổi |
| Không kiểm tra thao tác bị từ chối | ACL có thể quá rộng | Negative authorization tests |
| Cấp quyền .* cho tiện | Runtime truy cập resource ngoài nghiệp vụ | Regex/ACL theo destination cụ thể |

## 28. Checklist trước khi triển khai production

- [ ] Runtime principal riêng cho service và môi trường.
- [ ] Không có admin password/token trong application config hoặc image.
- [ ] Kafka ACL chỉ cho phép topic/group cần thiết.
- [ ] RabbitMQ user không có administrator/management tag nếu không cần; permission giới hạn theo vhost/resource.
- [ ] Pulsar role chỉ có produce/consume trên namespace/topic được giao.
- [ ] Topic, queue, DLQ và policy đã được provision theo quy trình.
- [ ] Auto-create/declare được cấu hình phù hợp với mô hình quyền.
- [ ] Secret được lấy từ secret manager hoặc workload identity.
- [ ] TLS và xác thực broker được bật, kiểm tra certificate đúng.
- [ ] Có rotation và thu hồi credential.
- [ ] Có audit log cho thay đổi quyền quản trị.
- [ ] Test cho phép thao tác hợp lệ và từ chối thao tác ngoài phạm vi.
- [ ] Log không in password, token, JAAS config hoặc private key.
- [ ] Có runbook xử lý khi runtime credential bị lộ.

## 29. Quy trình triển khai có phân tách quyền

1. Thiết kế binding và liệt kê topic/queue/group/subscription mà service cần.
2. Tạo permission matrix cho runtime principal.
3. Review resource, quyền và môi trường trước khi thay đổi production.
4. Provisioner xác thực bằng administrative identity để tạo resource và ACL.
5. Secret manager cấp runtime credential cho workload cụ thể.
6. Spring Cloud Stream binder kết nối bằng runtime identity.
7. Kiểm tra allow/deny bằng runtime credential.
8. Theo dõi broker audit log và metric sau rollout.
9. Rotation credential theo lịch và thu hồi credential cũ.
10. Khi service ngừng hoạt động, thu hồi runtime principal và dọn quyền theo quy trình.

Tách tài khoản quản trị khỏi tài khoản chạy ứng dụng là một ranh giới bảo mật quan trọng của hệ thống messaging. Administrator hoặc provisioning pipeline quản lý topology, user và ACL; Spring Cloud Stream runtime chỉ dùng danh tính có quyền đọc/ghi đúng destination nghiệp vụ. Áp dụng cùng nguyên tắc cho Kafka principal/ACL, RabbitMQ user/vhost permissions và Pulsar role/namespace permissions; kết hợp secret manager, rotation, audit và kiểm thử cả thao tác được phép lẫn bị từ chối để giảm phạm vi ảnh hưởng khi ứng dụng hoặc credential gặp sự cố.

## Tài liệu tham khảo

- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/documentation/#security_authz)
- [RabbitMQ — Access Control](https://www.rabbitmq.com/docs/access-control)
- [Apache Pulsar — Authorization](https://pulsar.apache.org/docs/security-authorization/)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)

