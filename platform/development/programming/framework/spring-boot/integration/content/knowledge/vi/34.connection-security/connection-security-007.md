# Phân biệt xác thực tới broker, cơ sở dữ liệu và HTTP service

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp hệ thống qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration. Trọng tâm là cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát những luồng tích hợp thực tế. Khi một luồng gọi qua nhiều hệ thống, mỗi bước có **trust boundary**, cơ chế xác thực và phạm vi quyền khác nhau.

Giả sử Order Service nhận HTTP request, ghi PostgreSQL, xuất sự kiện sang Kafka, Inventory Service đọc sự kiện, ghi một database khác rồi gọi Pricing HTTP API. Trong một luồng như vậy có ít nhất bốn danh tính độc lập:

- Client bên ngoài gọi **Order HTTP API**.
- **Order Service** đăng nhập PostgreSQL và Kafka.
- **Inventory Service** đăng nhập Kafka và database của chính nó.
- **Inventory Service** lấy token phù hợp để gọi **Pricing HTTP API**.

Không thể dùng chung một `Authorization: Bearer ...` cho tất cả đích. Kafka có SASL/TLS/ACL, PostgreSQL có user/role và phương thức xác thực được server cấu hình, RabbitMQ có virtual host và permissions, Redis có ACL, còn HTTP API thường dùng OAuth2 access token, API key, mTLS hoặc chữ ký request. Một kết nối TLS thành công cũng **không chứng minh** caller được phép thực hiện mọi thao tác nghiệp vụ.

Bài thuộc chương **Bảo mật kết nối**, đề mục **Phân biệt xác thực tới broker, cơ sở dữ liệu và HTTP service**.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **identity**, **authentication**, **authorization**, **TLS server authentication**, **mTLS client authentication** và **business authorization**.
2. Xác định danh tính nào được dùng ở mỗi điểm trong một integration flow.
3. Cấu hình kết nối Kafka bằng SASL_SSL, SCRAM và quyền topic/consumer group.
4. Phân biệt RabbitMQ credentials, virtual host, configure/write/read permissions và TLS.
5. Cấu hình PostgreSQL JDBC qua user/password, SCRAM và `sslmode=verify-full`.
6. Hiểu Redis ACL, MongoDB authSource/X.509 và sự khác biệt so với HTTP security.
7. Thiết kế HTTP service-to-service authentication bằng OAuth2 client credentials hoặc mTLS.
8. Tránh nhầm inbound OAuth2 resource server với outbound OAuth2 client.
9. Áp dụng least privilege, secrets/CA rotation và credential isolation theo môi trường.
10. Phân loại lỗi xác thực, phân quyền và lỗi mạng để không retry sai.
11. Viết integration tests cho invalid credentials, thiếu quyền, sai certificate và token hết hạn.
12. Xây checklist production cho một luồng kết nối có nhiều security boundaries.

> **Nguyên tắc:** Xác thực trả lời **“bạn là ai?”**; phân quyền trả lời **“bạn được làm gì trên tài nguyên nào?”**. TLS bảo vệ và có thể xác thực **peer ở tầng transport**; nó không tự thay thế quyền nghiệp vụ của Kafka, database hay HTTP service.

---

## 1. Vẽ các security boundaries của một luồng tích hợp

~~~mermaid
flowchart LR
    U["External user / client"] -->|"HTTPS bearer token"| A["Order API"]
    A -->|"JDBC user + SCRAM / TLS"| D1[("Orders PostgreSQL")]
    A -->|"Kafka SASL_SSL / topic ACL"| K["Kafka cluster"]
    K -->|"SASL_SSL / group ACL"| I["Inventory Service"]
    I -->|"DB role + TLS"| D2[("Inventory PostgreSQL")]
    I -->|"OAuth2 access token / mTLS"| H["Pricing HTTP API"]
    I -. "Redis ACL + TLS" .-> C["Redis cache"]
~~~

**Mỗi mũi tên có chính sách riêng.** Dù hai service nằm trong cùng VPC hoặc cùng Kubernetes namespace, network location **không đủ** để chứng minh identity hay authorization. Mỗi peer cần được xác minh theo policy của nó.

Một cách inventory connections:

| Caller | Đích | Danh tính cần có | Kiểm tra phân quyền |
| --- | --- | --- | --- |
| Browser/mobile client | Order API | End-user JWT/session | Chỉ được xem/sửa order của mình |
| Order Service | Orders PostgreSQL | `order_app` database role | SELECT/INSERT/UPDATE trên schema/tables được cấp |
| Order Service | Kafka broker | Kafka principal từ SASL/cert | WRITE lên `orders.events`, không phải mọi topics |
| Inventory Service | Kafka broker | Kafka consumer principal | READ topic, READ consumer group tương ứng |
| Inventory Service | Inventory PostgreSQL | `inventory_app` DB role | CRUD trong phạm vi inventory |
| Inventory Service | Pricing API | OAuth2 client/service identity | `pricing.read` scope **và** resource policy |
| Inventory Service | Redis | ACL user `inventory_cache` | Chỉ các commands/key patterns cần thiết |
| Admin/migration job | DB/schema | Migration identity riêng | DDL cần thiết, không cấp cho app runtime |

**Không dùng một tài khoản quản trị cho tất cả các mũi tên.** Nếu Kafka credential bị lộ, quyền thiệt hại nên giới hạn ở Kafka resources đúng service; nó không được đồng thời mở database hay HTTP admin API.

### 1.1. Câu hỏi “ai xác thực ai?”

Trong kết nối TLS phổ biến:

1. Client kết nối đến host.
2. Server cung cấp certificate và chain.
3. Client kiểm chứng CA, thời hạn, hostname/SAN và các điều kiện TLS.
4. Nếu cấu hình **mTLS**, client còn trình certificate/private key để server kiểm chứng.
5. Tầng ứng dụng/broker/database thực hiện authentication/authorization theo policy của nó.

Đừng coi client có truststore chứa CA là nó đã có **client identity**: truststore giúp **kiểm tra server**, còn keystore chứa private key/client cert mới có thể dùng để xác thực client theo mTLS.

### 1.2. Ba lớp bảo vệ khác nhau

| Lớp | Ví dụ | Thất bại thường gặp |
| --- | --- | --- |
| Transport encryption/peer validation | TLS, CA, hostname verification | `SSLHandshakeException`, certificate unknown |
| Authentication | SASL SCRAM, DB user/password, HTTP bearer | Invalid credentials, token expired |
| Authorization | Kafka ACL, DB GRANT, HTTP scope/tenant | Authenticated nhưng bị từ chối thao tác |

**Mốc rất quan trọng:** TLS handshake thành công **không** chứng minh username/password đúng. Password đúng **không** chứng minh role được SELECT. HTTP JWT signature hợp lệ **không** chứng minh token có audience/scope/tenant phù hợp.

---

## 2. So sánh broker, database và HTTP service theo lớp

| Khía cạnh | Kafka | RabbitMQ | PostgreSQL | Redis | HTTP service |
| --- | --- | --- | --- | --- | --- |
| Danh tính client | SASL principal hoặc TLS certificate principal | Username/vhost hoặc TLS client cert qua cơ chế phù hợp | DB role/user, tùy `pg_hba.conf` | ACL username/password | OAuth2 client/user, mTLS identity, API key |
| Xác thực thông dụng | SASL SCRAM, GSSAPI, OAUTHBEARER; mTLS | AMQP SASL PLAIN trên TLS, EXTERNAL khi cấu hình | Password SCRAM-SHA-256, certificate, GSS, IAM provider-specific | ACL AUTH + TLS | Bearer JWT/opaque token, API key, HMAC, mTLS |
| Authorization | Topic/group/cluster ACL hoặc RBAC | Vhost và configure/write/read regex permissions | CONNECT/schema USAGE/table/row privileges | Commands, key patterns và categories | Scopes/roles/audience + domain ACL |
| TLS trust | Kafka SSL truststore/PEM config | AMQPS TLS/CA/hostname | JDBC driver TLS CA/hostname | TLS trust và Redis endpoint | HTTPS server certificate/hostname |
| Client private key | Chỉ cần nếu dùng mTLS | Chỉ cần nếu broker đòi client cert | Chỉ cần nếu DB dùng cert auth | Provider-specific mTLS support | Chỉ cần nếu HTTP mTLS |
| “Login OK” chứng minh | Principal được chấp nhận | Đăng nhập/vhost theo policy | DB session authenticated | ACL session authenticated | Token/key accepted theo endpoint |
| Không tự chứng minh | Có WRITE/READ mọi topic/group | Quyền mọi queue/exchange | DDL hoặc SELECT mọi table | Mọi key/command | Mọi resource/tenant |
| Reuse credential | Không nên xuyên hệ | Không nên xuyên hệ | Không nên xuyên hệ | Không nên xuyên hệ | Token phải đúng audience/scope |

Những backend khác như MongoDB, MySQL, Elasticsearch, Pulsar cũng có security model riêng. **Không sao chép JDBC properties sang Kafka, hay bearer token vào DB password field**, trừ khi một driver/provider cụ thể chính thức hỗ trợ mô hình token IAM/OAuth đã được cấu hình.

## 3. Phân biệt authentication method và TLS

### 3.1. Server-auth TLS

Một connection `postgresql://db.internal:5432`, `broker.internal:9093` hay `https://api.internal` có thể dùng TLS để:

- Mã hóa traffic.
- Phát hiện tampering trong đường truyền.
- Xác thực endpoint server nếu certificate được kiểm tra đúng.

Nếu client bỏ qua hostname validation hoặc trust mọi certificate, connection vẫn có thể mã hóa nhưng **không bảo đảm đúng server cần kết nối**.

### 3.2. mTLS (mutual TLS)

~~~mermaid
sequenceDiagram
    participant C as Service client
    participant S as Server / broker / DB
    C->>S: TLS ClientHello
    S-->>C: Server certificate
    C->>C: Verify trusted CA + SAN/hostname
    S-->>C: CertificateRequest nếu mTLS required
    C->>S: Client certificate + proof of private key
    S->>S: Validate client cert/identity policy
    Note over C,S: Có thể tiếp tục SASL/password/OAuth hoặc map certificate identity
    C->>S: Application request
~~~

mTLS có thể dùng **cùng** với SASL/password/token, hoặc được map thành một application principal nếu server/plugin hỗ trợ. Quy tắc phải xác định rõ ở cả hai phía.

Ví dụ:

- Kafka `security.protocol=SSL` với client certificate và broker principal mapping/ACL có thể dùng TLS principal thay SASL.
- Kafka `SASL_SSL` dùng TLS cho transport và SASL mechanism cho Kafka authentication; không tự đòi client certificate.
- RabbitMQ có thể dùng TLS client certificate với authentication mechanism/plugin phù hợp; chỉ bật TLS không tự đăng nhập bằng certificate.
- PostgreSQL `hostssl` có thể đòi client certificate qua cấu hình `pg_hba.conf`; client certificate không tự đồng nghĩa có mọi DB privileges.
- HTTP gateway có thể xác thực mTLS service identity, nhưng backend vẫn cần role/resource authorization.

### 3.3. Truststore và keystore không hoán đổi vai trò

| Thành phần | Chứa gì | Dùng cho |
| --- | --- | --- |
| Truststore | CA certificates / trusted roots | Client xác minh certificate phía đích |
| Keystore/key material | Client private key + certificate chain | Client chứng minh identity khi mTLS |
| DB password | Secret liên quan DB role | Database authentication |
| SASL password | Secret tương ứng broker principal | Kafka/Rabbit auth mechanism |
| OAuth client secret | Secret của OAuth client | Xin access token từ authorization server |
| OAuth access token | Token được AS cấp, có expiry/audience | Gọi resource server theo policy |
| API key | Secret/key do API provider cấp | Thao tác HTTP theo provider contract |

Không lưu private key trong source repo hoặc log `javax.net.debug=all`/HTTP headers vào hệ thống quan sát không có redaction. Secret phải được quản lý và rotate.

---

## 4. Kafka: broker authentication khác topic/group authorization

Kafka producer và consumer kết nối brokers, không phải HTTP REST endpoint. Các layer thường gặp:

1. TLS đến broker: `SSL` hoặc `SASL_SSL`.
2. Broker principal: SASL SCRAM/GSSAPI/OAUTHBEARER hoặc mTLS mapping.
3. Authorization: ACL/RBAC cho operations trên topics, groups và cluster resources.
4. Message payload/header: hợp đồng dữ liệu, correlation, idempotency; **không tự là user authentication**.

### 4.1. Kafka security.protocol

| Protocol | Transport encryption | Kafka client authentication |
| --- | --- | --- |
| `PLAINTEXT` | Không | Không ở tầng Kafka protocol; network trust không đủ |
| `SSL` | TLS | Có thể dùng certificate authentication nếu broker configured |
| `SASL_PLAINTEXT` | Không | SASL nhưng không mã hóa — tránh production |
| `SASL_SSL` | TLS | SASL authentication trên TLS |

`SASL_SSL` **không phải** “TLS client certificate bắt buộc”. SASL mechanism do `sasl.mechanism` và broker listeners cấu hình; TLS có thể chỉ server-auth. Với TLS client auth trên Kafka, kiểm tra `ssl.client.auth` phía broker và principal mapping.

### 4.2. Spring Boot Kafka producer với SCRAM

Một ví dụ `application.yml` cho Spring Boot 3.x:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.internal.example:9093
      - kafka-2.internal.example:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule
        required username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
      ssl.truststore.location: /etc/certs/kafka-truststore.p12
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
      ssl.truststore.type: PKCS12
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

**Yêu cầu đi kèm:**

- `KAFKA_USERNAME`, `KAFKA_PASSWORD`, truststore password phải lấy từ secret injection, **không hardcode**.
- Bootstrap brokers và advertised listeners phải trỏ đến hostname được certificate SAN bao phủ.
- Verify server hostname/CA; không tắt hostname verification bằng cách gán giá trị rỗng cho `ssl.endpoint.identification.algorithm`.
- `acks: all` liên quan acknowledgement/durability; **không quyết định authentication**.
- Producer serializers liên quan data contract; không quyết định authorization.
- `SCRAM-SHA-512` chỉ hoạt động khi Kafka cluster/listeners đã hỗ trợ và provision user đúng.
- Định dạng JAAS có dấu `;` kết thúc. Kiểm tra cách Spring config interpolation và quoting của environment/container thực tế.
- Nếu sử dụng PEM và SSL bundles/Cloud vendor IAM, property names có thể khác; theo Kafka client/provider version.

### 4.3. Kafka consumer: cần cả topic và group permissions

~~~yaml
spring:
  kafka:
    consumer:
      group-id: inventory-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
~~~

Đoạn consumer này **kế thừa** `spring.kafka.properties` chung nếu app cấu hình vậy. Consumer cần Kafka principal có quyền:

- READ trên topic `orders.events` (và các quyền metadata phù hợp).
- READ trên consumer group `inventory-projection`.
- Các quyền topic/group khác nếu dùng transactional consumer, DLT publishing hoặc topic auto creation theo policy.

**Lỗi phân quyền topic không đồng nghĩa sai password.** User có thể authenticate thành công nhưng bị broker từ chối READ topic hoặc group. Cần phân biệt `SaslAuthenticationException` với `TopicAuthorizationException`, `GroupAuthorizationException` và các lỗi networking/TLS.

### 4.4. Producer và consumer có nên dùng chung principal?

Nếu một service vừa publish, vừa consume, có thể cần quyền khác nhau. Một principal chung làm cấu hình dễ hơn nhưng tăng blast radius:

~~~text
order-producer principal  -> WRITE orders.events
inventory-consumer        -> READ orders.events + READ group inventory-projection
dlq-relay                 -> READ retry-topic + WRITE dlq-topic
schema-registry-client    -> Quyền riêng theo Schema Registry provider
~~~

Tách principal theo deployment/workload và least privilege khi có thể. Kafka authorization không có khái niệm “HTTP user logged in” trừ khi ứng dụng chủ động mô hình hóa end-user identity, audit và ACL riêng.

### 4.5. Kafka OAUTHBEARER và managed IAM

Kafka có SASL `OAUTHBEARER`, nhưng nó **không đồng nghĩa** bearer header HTTP. Cần Kafka login callback handler/token retrieval, broker listener hỗ trợ token validation và quyền Kafka principal. Các cloud providers có thể cung cấp IAM/managed auth mechanisms hoặc callback khác chuẩn; dùng configuration đúng của vendor.

Không copy OAuth2 access token từ HTTP inbound request vào `sasl.jaas.config` và kỳ vọng Kafka broker hiểu: token audience, trust, validator, lifecycle và Java client callback khác.

### 4.6. Kafka mTLS principal

Nếu broker configured SSL client-auth, certificate identity có thể map thành principal thông qua broker principal builder/mapper. Khi đó:

- Client có private key/cert.
- Broker trust CA phù hợp.
- Hostname verification phía client vẫn cần.
- Topic/group ACL gắn với **mapped principal**, không nhất thiết là raw certificate DN.
- Certificate rotation có thể thay DN/SAN hoặc principal mapping, gây mất quyền dù TLS handshake thành công.

Kafka `SSL` mode không có SASL username/password theo mặc định. Nếu dùng `SASL_SSL`, một số triển khai vẫn yêu cầu TLS client certificate; điều đó là yêu cầu cụ thể của cluster, không phải định nghĩa mặc định của tên mode.

### 4.7. Authentication và producer ACK là hai vấn đề khác

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant K as Kafka broker
    participant C as Consumer
    P->>K: TLS/SASL handshake
    K-->>P: Authentication accepted
    P->>K: Produce event E-100
    K->>K: Check topic WRITE ACL + append
    K-->>P: Producer ACK per acks configuration
    K->>C: Deliver record to consumer
    C->>C: Process with inbox/idempotency
~~~

Authentication broker cho phép xác định **principal**, ACL quyết định **được publish/read chỗ nào**, còn producer ACK cho biết trạng thái broker acknowledgement theo config. Không có bước nào tự chứng minh consumer đã COMMIT SQL transaction.

---

## 5. RabbitMQ: username/password, virtual host và ba loại permission

RabbitMQ không dùng Kafka SASL property names. AMQP 0-9-1 thường dùng username/password với cơ chế xác thực do broker hỗ trợ, virtual host và quyền trên exchanges/queues.

### 5.1. Spring Boot RabbitMQ cấu hình

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal.example
    port: 5671
    virtual-host: /orders
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
      validate-server-certificate: true
      verify-hostname: true
~~~

Giả định RabbitMQ broker đã bật TLS listener ở cổng 5671, certificate phù hợp hostname, user tồn tại và được cấp quyền trên `/orders`.

**Lưu ý phiên bản:** Các property `spring.rabbitmq.ssl.*` tồn tại trong các Spring Boot dòng hỗ trợ tương ứng, nhưng vị trí trust/key stores và SSL bundle integration có thể khác theo Boot version. Kiểm tra actual configuration metadata và test handshake, không copy properties từ Kafka vào RabbitMQ.

### 5.2. Virtual host là resource namespace

RabbitMQ `virtual-host: /orders` không phải path HTTP hay Kubernetes namespace. Một RabbitMQ user có thể đăng nhập được nhưng **không có permissions trên vhost** cần dùng.

RabbitMQ permissions cho user trên mỗi vhost thường gồm ba regex:

| Quyền | Ý nghĩa cơ bản | Ví dụ resource |
| --- | --- | --- |
| `configure` | Khai báo/xóa/điều chỉnh exchanges/queues phù hợp | Queue `orders.retry` |
| `write` | Publish/send vào exchanges/paths phù hợp | Exchange `orders.exchange` |
| `read` | Consume/get/bind theo broker operation policy | Queue `orders.events.inventory` |

Quyền thực tế cho AMQP operations có thể liên quan cả source/destination trong binding hoặc các rule riêng. Đừng dựa vào mỗi regex tên queue rồi assume publish/consume chắc thành công.

### 5.3. Tách publisher và consumer privileges

Ví dụ policy:

~~~text
order-publisher:
  vhost=/orders
  configure=none (nếu topology provision trước)
  write=^orders\.exchange$
  read=none

inventory-consumer:
  vhost=/orders
  configure=none
  write=none (trừ error/DLQ publishing nếu cần)
  read=^orders\.events\.inventory$
~~~

Đây là **mô hình quyền minh họa**, không phải nguyên văn lệnh `rabbitmqctl set_permissions`. Trong một số trường hợp, consumer cần quyền phụ cho binding/declare/queue maintenance. Nên provisioning topology bằng identity/operator riêng; app runtime chỉ nhận quyền tối thiểu.

### 5.4. RabbitMQ guest user và môi trường

Tài khoản `guest` mặc định trên RabbitMQ thường bị giới hạn loopback remote login theo default broker configuration. Không dùng `guest/guest` làm credential production, không mở quyền guest remote chỉ vì gặp login failure.

### 5.5. AMQPS TLS và client certificate

Khi bật `ssl.enabled`, client xác minh server TLS. Điều đó **không** tự biến username/password thành mTLS. Nếu muốn xác thực client certificate:

1. Broker yêu cầu/verify client cert.
2. Client cấu hình keystore/client private key.
3. Broker có mechanism/plugin ánh xạ certificate thành user (ví dụ EXTERNAL theo triển khai).
4. User đó được cấp vhost permissions.
5. Kiểm thử cert rotation, revoked/expired cert và permission denial.

**TLS success, RabbitMQ login success, queue READ permission và publisher confirm** là bốn checkpoint khác nhau.

### 5.6. `@RabbitListener` không tự có quyền

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventsListener {

    @RabbitListener(queues = "orders.events.inventory")
    public void handle(OrderEvent event) {
        // Business processing.
    }
}
~~~

`OrderEvent` là DTO ứng dụng. Listener container dùng `ConnectionFactory` và credentials của service; annotation **không cấp quyền broker**. Nếu thiếu READ permission/queue/vhost, listener có thể lỗi lúc startup hoặc khi consume. Đồng thời, nhận message không chứng minh consumer có quyền ghi PostgreSQL.

### 5.7. DLQ/publisher confirms tách khỏi authorization

Publisher confirms và consumer ACK là **delivery/progress semantics**, không phải authentication mechanism. Một user có WRITE vào exchange nhưng không có configure queue vẫn có thể publish nếu topology đã provision; một publisher confirm thành công không chứng minh consumer đã commit DB.

---

## 6. PostgreSQL: database user, `pg_hba.conf`, TLS và GRANT

Database authentication có nhiều tầng:

1. TLS server identity — driver xác minh đúng PostgreSQL endpoint.
2. Authentication method — PostgreSQL `pg_hba.conf` lựa chọn rule theo connection/client/role/database.
3. Database role — principal đã xác thực.
4. Authorization — quyền `CONNECT`, `USAGE`, `SELECT`, `INSERT`, `UPDATE`, `EXECUTE` và row-level policies.
5. Transaction — quyền không đồng nghĩa SQL transaction đã COMMIT.

### 6.1. Spring Boot JDBC với TLS xác minh hostname

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://orders-db.internal.example:5432/orders?sslmode=verify-full
    username: ${ORDERS_DB_USERNAME}
    password: ${ORDERS_DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3000
      max-lifetime: 1800000
~~~

`sslmode=verify-full` của PostgreSQL JDBC driver yêu cầu xác minh certificate chain và hostname. Client phải trust CA phát hành certificate, ví dụ thông qua Java truststore/driver-specific `sslrootcert` property tùy cách deploy. Đừng assume CA nội bộ tự ở JRE truststore.

**Không dùng** `sslmode=require` như đồng nghĩa của full server identity verification. Các `sslmode` có semantics khác nhau (`disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`). Khi cần chống MITM, dùng `verify-full` với trust anchors đúng.

### 6.2. `pg_hba.conf` quyết định cách authentication

Ví dụ conceptual phía DB:

~~~text
# type   database  user         address           auth-method
hostssl  orders    order_app    10.20.0.0/16      scram-sha-256
~~~

Đây là server configuration minh họa, phải kết hợp firewall/network policy và PostgreSQL TLS config. Không tự chỉnh `pg_hba.conf` của production nếu không có change control. `hostssl` yêu cầu TLS; `scram-sha-256` quy định password authentication protocol tương ứng.

PostgreSQL còn hỗ trợ client certificate, GSS/SSPI, LDAP/PAM và các plugin/IAM proxy theo môi trường. **`sslmode` của client không chọn DB authentication method**, và SCRAM password không tự kiểm tra hostname certificate.

### 6.3. Database role và schema/table privileges

Một role `order_app` có thể xác thực nhưng không đọc được bảng:

~~~sql
-- Ví dụ quản trị, không chạy bằng runtime application identity.
CREATE ROLE order_app LOGIN;

GRANT CONNECT ON DATABASE orders TO order_app;
GRANT USAGE ON SCHEMA app TO order_app;

GRANT SELECT, INSERT, UPDATE
ON TABLE app.orders, app.order_outbox
TO order_app;
~~~

`CREATE ROLE`/`GRANT` là DDL/DCL **do database admin/migration provisioning role** thực hiện; không cho app tự cấp quyền lúc khởi động.

Một role SELECT được bảng `orders` không có nghĩa có quyền SELECT tất cả `public.*`, chạy schema migrations, tạo extension hoặc đọc PII của schema khác. Với PostgreSQL, còn có object ownership, sequences (nếu dùng serial/identity), row-level security và default privileges cho objects tạo sau.

### 6.4. Migration account khác runtime account

~~~text
migration_db_identity:
  DDL cần thiết, create/alter objects có kiểm soát.

order_app_runtime:
  SELECT/INSERT/UPDATE trên tables cần thiết.
  Không DROP TABLE/CREATE EXTENSION/ALTER ROLE.
~~~

Flyway/Liquibase có thể dùng credential riêng trong job/pipeline hoặc datasource/migration settings phù hợp. Không cấp DDL `SUPERUSER` cho application chỉ để startup migration “dễ hơn”.

### 6.5. Database password vs IAM token

Một số cloud DB providers cho phép IAM database authentication token ngắn hạn. Token có thể được truyền ở chỗ JDBC password hoặc qua credential provider cụ thể, nhưng cần **provider-specific connector/refresh mechanism**; không coi token OAuth2 dùng cho HTTP Pricing API là một DB password mặc định.

Hikari connection pool có nhiều connections với lifecycle dài; token hết hạn thường ảnh hưởng **mở connection mới**, không đồng nghĩa mọi connection đang tồn tại lập tức invalid. Phải kiểm tra chính sách provider, token refresh và pool recycling khi rotate.

### 6.6. Khi nào dùng PostgreSQL client certificate?

DB server có thể yêu cầu TLS client cert và/hoặc map cert DN sang DB role. Cần đúng `pg_hba.conf`, `pg_ident.conf` khi mapping, client key/cert config và database privileges. `sslmode=verify-full` chỉ kiểm chứng server, **không tự xuất trình client certificate**.

### 6.7. SQLSTATE giúp phân biệt lỗi

| SQLSTATE (PostgreSQL) | Nhóm | Hàm ý |
| --- | --- | --- |
| `28P01` | `invalid_password` | Credentials sai hoặc không được chấp nhận |
| `28000` | `invalid_authorization_specification` | Auth/role/access context lỗi |
| `42501` | `insufficient_privilege` | Login thành công nhưng thiếu quyền SQL |
| `08001`/`08006` | Connection problems | Network/connection failure, không phải tự động sai password |
| `40001` | Serialization failure | Transaction concurrency, có thể retry **toàn transaction** an toàn theo contract |
| `40P01` | Deadlock detected | Concurrency/locking, không phải authentication |

Đừng retry login sai password hàng nghìn lần làm account bị lock/throttled hoặc che lỗi rotation. Với SQL transaction commit timeout, kết quả có thể **UNKNOWN** và cần business key reconciliation, không mặc định rollback.

 
## 7. Redis: ACL user và key/command permissions

Redis không dùng Kafka SASL SCRAM hay PostgreSQL `pg_hba.conf`. Với Redis 6+ ACL, một kết nối thường gửi **username/password** qua `AUTH`/client handshake, sau đó Redis kiểm tra command categories, command names và key patterns của ACL user.

### 7.1. Spring Boot Redis với ACL và TLS

Một cấu hình Spring Boot 3.x sử dụng Lettuce mặc định:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      timeout: 2s
      connect-timeout: 1s
~~~

Giả định Redis hỗ trợ TLS listener ở cổng được chọn và Java client trust certificate đúng. Một số Spring Boot 4.x versions có thay đổi property namespace/starter; kiểm tra metadata cụ thể.

**Không nhầm:**

- `username/password` xác thực Redis ACL principal.
- TLS mã hóa và kiểm tra server; không tự cấp quyền truy cập keys.
- `host/port` và connection timeout là network configuration.
- TTL/cache names là dữ liệu ứng dụng, không phải auth permissions.
- `spring.data.redis.password` không phải JWT token mặc định.

### 7.2. Redis ACL ví dụ

Một policy theo nguyên lý least privilege:

~~~text
ACL user: inventory_cache
Allowed key pattern: cache:inventory:*
Allowed commands: GET, SET, DEL, PING and
  protocol/client handshake commands needed by the driver.
No access: CONFIG, FLUSHALL, arbitrary KEYS, admin commands.
~~~

Lệnh quản trị Redis ở môi trường test có thể dùng:

~~~text
ACL SETUSER inventory_cache on >REDACTED-PASSWORD ~cache:inventory:* +get +set +del +ping
~~~

**Đây chỉ là ví dụ minh họa**, không chạy literal password/ACL trên production. Client Redis có thể cần thêm commands cho handshake, Lua, `MGET`, `EXPIRE`, `UNLINK`, transactions, pub/sub hoặc Spring Cache implementation; policies phải dựa trên **commands ứng dụng thực sự sử dụng**. `REDIS_USERNAME`/password vẫn cần secret injection và rotation.

### 7.3. Redis `NOAUTH`, `WRONGPASS`, `NOPERM`

| Tình huống | Ý nghĩa |
| --- | --- |
| `NOAUTH Authentication required` | Chưa authenticate một Redis session theo policy |
| `WRONGPASS invalid username-password pair or user is disabled` | Credential/user không được chấp nhận |
| `NOPERM ...` | Đã xác thực nhưng không được phép command/key |
| TLS handshake error | Chưa xác minh transport/peer thành công |
| Connection timeout | Lỗi network/availability, chưa chứng minh sai credential |

Không retry `WRONGPASS` vô hạn và cũng không tắt ACL hay TLS để “fix” timeout. Khi một Spring cache operation fail do `NOPERM`, xác định chính xác command và key pattern; có thể vì code mới dùng `MGET`/`EXPIRE` chưa được cấp, không phải vì credentials sai.

### 7.4. Cache ACL không thay business data authorization

Một Redis user được phép đọc `cache:inventory:*` có thể thấy nhiều tenants nếu keys/values dùng chung. Cache keys phải chứa namespace/tenant phù hợp, nhưng chỉ dựa vào tenant ID do HTTP client gửi vẫn thiếu authorization. Business service phải kiểm tra caller identity và quyền truy cập SKU/tenant **trước khi cache read/write**.

---

## 8. MongoDB và các database khác: principal và authentication database

Mỗi database có cơ chế riêng, không gán chung là “JDBC password”.

### 8.1. MongoDB `authSource`

MongoDB thường dùng SCRAM-based authentication với credential được quản lý theo **authentication database**. Ví dụ URI được inject qua secret:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${INVENTORY_MONGODB_URI}
~~~

Giá trị URI conceptual:

~~~text
mongodb://inventory_app:<redacted>@mongo-1.internal:27017/inventory
  ?authSource=admin
  &tls=true
~~~

Một URI thực tế phải ở **một dòng**, percent-encode user/password chứa ký tự đặc biệt và có CA/hostname verification phù hợp. Không log full URI có password. `authSource=admin` chỉ có nghĩa là credentials được authenticate against `admin` database; **không** cấp admin privileges trong inventory database.

MongoDB cũng hỗ trợ X.509 authentication và cloud mechanisms theo deployment; phải cấu hình đúng driver/mechanism, roles và TLS client certificate khi có yêu cầu.

### 8.2. Vai trò MongoDB khác PostgreSQL

MongoDB roles/privileges theo databases/collections/actions; PostgreSQL dùng roles, schemas, tables, sequences và row-level security. Không copy SQL `GRANT SELECT` thành MongoDB user role một cách máy móc. Khi Spring Data MongoDB kết nối thành công nhưng `find` hoặc `update` bị unauthorized, đây là lỗi resource privileges, không nhất thiết sai credentials.

### 8.3. MySQL/MariaDB và SQL Server

Các relational DB khác có driver-specific TLS verification và auth mechanisms:

- MySQL có TLS `sslMode` như `VERIFY_IDENTITY` ở các Connector/J versions tương ứng, cùng authentication plugin policy.
- SQL Server JDBC có `encrypt`, `trustServerCertificate` và hostname/certificate config, cùng SQL/AD authentication models.
- PostgreSQL có `sslmode=verify-full`.
- R2DBC không nhất thiết dùng đúng URL/property names của JDBC counterpart.

**Không viết một `ssl=true` “phổ quát” cho mọi driver**. Mỗi driver phải được kiểm thử khả năng xác minh server identity và endpoint rotation.

---

## 9. HTTP service authentication: bearer token, mTLS, API key và HMAC

HTTP service có thể dùng nhiều cơ chế; phần lớn ứng dụng Spring Boot hiện đại dùng OAuth2/OIDC khi cần identity/token delegation hoặc client credentials giữa services.

### 9.1. Các cơ chế thường gặp

| Phương pháp | Client gửi | Server xác thực | Khi phù hợp | Rủi ro |
| --- | --- | --- | --- | --- |
| OAuth2 bearer access token | `Authorization: Bearer ...` | Signature/JWKS hoặc introspection và policy | Service-to-service/user delegation | Token leak, wrong audience/scope |
| API key | Header theo provider contract | Lookup/hash/key policy | API provider simple integrations | Long-lived key, thiếu fine-grained claims |
| HTTP Basic | Base64 username:password trong Authorization | Credential store | Legacy/intranet (vẫn cần TLS) | Long-lived credentials/replay |
| HTTP mTLS | Client certificate/private key trong TLS | Cert CA/identity mapping | Strong workload peer identity | Cert renewal/trust management |
| HMAC request signature | Signature, timestamp, nonce, signed bytes | Shared secret/key + canonical request | Webhooks/partner APIs | Clock skew, replay/canonicalization |
| Cookie/session | Session cookie | Session store/CSRF policy | Browser-oriented apps | Không nên reuse như M2M credential |
| OAuth2 token exchange/on-behalf-of | Downstream-specific token | Authorization server + resource server | User delegation giữa services | Confused-deputy/cross-audience |

### 9.2. Authorization: Bearer là application header

~~~http
GET /v1/prices/SKU-A HTTP/1.1
Host: pricing.internal.example
Authorization: Bearer <redacted>
Accept: application/json
~~~

Access token không thay TLS; HTTP client vẫn phải xác minh HTTPS hostname/certificate. Token bị lộ qua log/proxy có thể được sử dụng lại đến khi hết hạn/revoked. Không log raw Authorization header.

**Bearer header không phải Kafka SASL_SSL login** và không phải PostgreSQL password. Các cơ chế đó có thể sử dụng token trong triển khai riêng, nhưng phải cấu hình đúng protocol và audience.

### 9.3. Client credentials là **service identity**, không phải end-user identity

~~~mermaid
sequenceDiagram
    participant I as Inventory Service
    participant AS as OAuth Authorization Server
    participant P as Pricing Resource Server
    I->>AS: POST token endpoint: client_credentials + client auth
    AS->>AS: Validate client, policy, requested scopes
    AS-->>I: Access token (expiry, audience/scope semantics)
    I->>P: HTTPS GET + Bearer access token
    P->>P: Verify token + audience + scope + domain access
    P-->>I: Price result / 401 / 403
~~~

Không nhầm `client_id` với identity của người dùng đang đăng nhập Order API. Client credentials đại diện service/workload và các quyền đã được authorization server/provider cấp.

### 9.4. Spring Boot OAuth2 client configuration

Spring Boot 3.x/Spring Security 6.x ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    // Nếu cùng service cũng nhận incoming bearer tokens:
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          pricing:
            provider: pricing-idp
            client-id: ${PRICING_CLIENT_ID}
            client-secret: ${PRICING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - pricing.read
        provider:
          pricing-idp:
            token-uri: https://identity.internal.example/oauth2/token
~~~

Phía authorization server phải provision client `pricing`, cho phép grant `client_credentials`, scope phù hợp và xác nhận resource audience. Việc client yêu cầu `pricing.read` không có nghĩa server **đã cấp** hoặc resource server mặc nhiên chấp nhận.

### 9.5. RestClient outbound OAuth2 token interceptor

Với **Spring Security versions có `OAuth2ClientHttpRequestInterceptor` (ví dụ Spring Security 6.4+)**, có thể tích hợp OAuth2 authorized-client manager vào `RestClient`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PricingOAuthClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean
    RestClient pricingRestClient(
            RestClient.Builder builder,
            OAuth2AuthorizedClientManager serviceAuthorizedClientManager) {

        var oauthInterceptor =
                new OAuth2ClientHttpRequestInterceptor(
                        serviceAuthorizedClientManager);

        return builder
                .baseUrl("https://pricing.internal.example")
                .requestInterceptor(oauthInterceptor)
                .build();
    }
}
~~~

Các class sử dụng ở đây có version constraints. Với Boot 3.2/Spring Security 6.2 hoặc Spring Boot 4/Spring Security 7, kiểm tra integration API tương ứng, và không assume helper interceptor có sẵn ở mọi version. `AuthorizedClientServiceOAuth2AuthorizedClientManager` phù hợp **service/background jobs ngoài HTTP servlet request**; nếu workflow dùng user delegation, mô hình manager/principal khác.

Ví dụ request gắn client registration/principal tương ứng:

~~~java
import org.springframework.web.client.RestClient;

import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

public class PricingGateway {

    private final RestClient restClient;

    public PricingGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    public PriceQuote quote(String sku) {
        return restClient.get()
                .uri("/v1/prices/{sku}", sku)
                .attributes(clientRegistrationId("pricing"))
                .attributes(principal("inventory-service"))
                .retrieve()
                .body(PriceQuote.class);
    }
}
~~~

`PriceQuote` là DTO ứng dụng. Khi triển khai thật, kiểm tra helper `principal(...)` và `clientRegistrationId(...)` của đúng Spring Security version; authenticated principal key phải được lựa chọn có chủ đích, không ngầm dùng ID của end-user cho client credentials. HTTP transport cần connect/read timeout, TLS trust và giới hạn concurrent requests.

### 9.6. Không nhầm Resource Server với OAuth2 Client

Một service có thể vừa nhận HTTP bearer token, vừa gọi service khác:

| Thành phần | Vai trò | Spring dependency/config |
| --- | --- | --- |
| Inbound endpoint | **OAuth2 Resource Server** xác minh access token của caller | Resource server JWT/opaque validation |
| Outbound HTTP caller | **OAuth2 Client** xin và gắn access token phù hợp | Client registration/authorized-client manager |
| Authorization Server | Cấp token, quản lý clients/scopes/claims | Hệ thống IAM/IdP độc lập |
| Downstream Resource Server | Kiểm token riêng theo audience/scope/domain | Chính sách phía Pricing API |

Ví dụ inbound resource server JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.internal.example/
~~~

Đây chỉ là một phần cấu hình inbound resource server; còn cần HTTP security chain, authorization policy và kiểm audience theo cách phù hợp version. **Có `issuer-uri` không tự tạo client credentials cho outbound Pricing API.**

### 9.7. Audience và scope là hai kiểm tra khác nhau

Token có thể có:

~~~json
{
  "iss": "https://identity.internal.example/",
  "sub": "inventory-service",
  "aud": ["pricing-api"],
  "scope": "pricing.read",
  "exp": 1795260000
}
~~~

Đây là claims minh họa (không phải token có chữ ký). Pricing API nên xác minh issuer, signature/key, expiration, audience, scope/role và domain policies như tenant/warehouse. Một token cấp cho **Kafka gateway** hoặc **Order API** không nên được Pricing API chấp nhận chỉ vì cùng issuer.

### 9.8. Không tự forward inbound token

~~~text
External user --JWT(aud=order-api)--> Order Service
Order Service --?--> Pricing API
~~~

Chuyển thẳng user bearer token qua downstream tạo rủi ro **wrong audience**, vượt quyền và confused deputy. Nếu downstream cần hành động thay người dùng, dùng delegated access/token exchange/on-behalf-of flow **do IdP hỗ trợ**, và kiểm tra tenant/resource permissions. Nếu downstream chỉ cần service-level pricing reference data, dùng client-credentials token riêng.

### 9.9. WebClient và reactive context

Với Spring WebFlux, OAuth2 client integration có các filters/managers riêng; servlet `OAuth2ClientHttpRequestInterceptor` của `RestClient` không tự thay thế reactive `WebClient` security filter. Khi gọi trong Reactor chain, bảo đảm principal/authorized client và Reactor context được propagate phù hợp, không dùng `ThreadLocal` từ một servlet request trong background consumer.

### 9.10. API key và HMAC

API key thường dùng header do provider quyết định:

~~~http
GET /v1/tax-rates HTTP/1.1
Host: tax.partner.example
X-API-Key: <redacted>
~~~

Tên header `X-API-Key` **không phải chuẩn bắt buộc**. Không nhúng key trong URL/query string vì dễ đi vào logs, proxy analytics và browser history. Rotation nên có overlap windows nếu provider hỗ trợ.

HMAC signing cần canonical method/path/query/body, timestamp, nonce, key identifier và clock-skew allowance theo contract provider. Nếu ký body trước khi Jackson serialize mà bytes thật thay đổi, signature verification sẽ lỗi. Chữ ký không tự thay TLS, authorization hoặc anti-replay storage.

---

## 10. Mô hình identity cho Spring Integration adapters

Một luồng Spring Integration có thể bắt đầu từ inbound HTTP, tạo message rồi route sang AMQP, JDBC hoặc HTTP outbound adapter.

~~~mermaid
flowchart LR
    A["HTTP Gateway\nuser/token"] --> C["IntegrationFlow"]
    C --> P["JDBC Adapter\nDB role"]
    C --> K["Kafka Adapter\nKafka principal"]
    C --> R["RabbitMQ Adapter\nAMQP user/vhost"]
    C --> H["HTTP Outbound Gateway\nOAuth client token"]
    C --> D["Redis Cache Adapter\nACL user"]
~~~

**Cấu hình adapter chủ yếu sử dụng credentials của connection factory/client**, không tự “mang theo” user identity từ message headers.

### 10.1. Headers không thay authentication

Một Integration Message có thể chứa:

~~~text
headers:
  correlationId=...
  tenantId=...
  traceparent=...
payload:
  OrderConfirmed(...)
~~~

`tenantId` trong message header là **dữ liệu** cho routing/business policy, không phải credential đã xác thực bởi Kafka/DB/HTTP. Nếu message đến từ broker do bên không tin cậy có thể publish, attacker có thể giả mạo header. Phải kiểm identity của publisher qua broker ACL, validate payload/signature nếu cần và kiểm tenant authorization ở consumer.

### 10.2. Dịch identity qua trust boundaries

Một service được authenticated vào Kafka dưới principal `inventory-consumer`, sau đó gọi HTTP Pricing API dưới OAuth client `inventory-service`:

- Kafka chỉ biết principal có READ topic/group.
- Pricing chỉ biết token của OAuth client (hoặc delegated user nếu thật sự có).
- Database chỉ biết DB role `inventory_app`.
- Application phải audit `eventId`, `operationId`, `tenantId` và mối liên hệ nhân quả qua các stages.

Đừng tuyên bố “Kafka đã xác thực message nên không cần validate inbound data”: broker authenticates **connection principal**, không đảm bảo mọi business field của event đều hợp lệ.

### 10.3. Không serialize secrets vào outbox/inbox

Outbox cần lưu **durable business intent**:

~~~json
{
  "eventId": "8e6d6e12-d0e2-4b15-8865-1b53a6bc7b39",
  "aggregateId": "ORD-100",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "payload": {"orderId": "ORD-100", "amountMinor": 150000}
}
~~~

Không đưa Kafka password, OAuth access token, DB password hoặc API key vào persisted event payload. Relay lấy credential **mới nhất theo runtime secret source** khi gửi. Nếu outbox job chạy lại sau nhiều ngày, một access token cũ gần như chắc hết hạn.

### 10.4. Service account khác business actor

Một command có thể được tạo bởi end-user `user-123` nhưng được xử lý qua inventory service principal. Ghi audit tách biệt:

~~~text
transportPrincipal: inventory-service
businessActor: user-123 (được xác minh ở upstream, có trust chain)
operationId: K-100
tenant: tenant-A
~~~

Không dùng actor truyền qua message như “đã xác thực end-user” nếu không có hệ thống chứng thực provenance và policy chấp nhận trust chain đó. Các thông tin user context phải được tối thiểu hóa và bảo vệ privacy.

---

## 11. Secrets: injection, scope, rotation và lifecycle

### 11.1. Không hardcode

Sai:

~~~yaml
spring:
  datasource:
    password: my-secret-password

  kafka:
    properties:
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="admin" password="admin123";
~~~

Một YAML commit vào repo có thể bị nhân bản vào build logs, container images và backups. Secret cũng không được xuất trong Spring Actuator config/env endpoints hoặc exception messages.

### 11.2. Externalized config

~~~yaml
spring:
  datasource:
    username: ${ORDERS_DB_USERNAME}
    password: ${ORDERS_DB_PASSWORD}

  rabbitmq:
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}

  data:
    redis:
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
~~~

Variables được inject bởi orchestrator/secret manager; không ghi `.env` có secrets vào git. Trong Kubernetes, secrets có thể được mount files hoặc injected env; bảo vệ RBAC, encryption at rest, audit và pod permissions. Env vars vẫn có rủi ro qua process inspection/crash dump/diagnostics, không coi chúng tuyệt đối an toàn.

### 11.3. Rotate không chỉ thay secret store

Một secret manager cập nhật password/certificate **không đồng nghĩa** tất cả clients đang chạy dùng value mới.

| Client | Rotation behavior cần kiểm chứng |
| --- | --- |
| Kafka Java producer/consumer | SASL credential config có thể được chụp khi tạo client; cần client/container restart/recreation |
| RabbitMQ CachingConnectionFactory | Connections đang sống có credential cũ; cần cơ chế recovery/recreate |
| HikariCP JDBC pool | Existing connections có thể tồn tại; new connections cần credential mới |
| Redis Lettuce pool/connection | Reconnect có thể cần credential mới |
| RestClient OAuth2 | Access token được cache đến expiry; client credentials refresh token acquisition theo manager |
| mTLS client | TLS sessions/private key loading có thể cần reload/connection recycle |

Quy trình rotation phải có **old/new overlap** khi backend hỗ trợ, kiểm tra new connections, healthy rollouts và rollback. Không revoke credential cũ trước khi workers còn dùng nó trừ khi incident yêu cầu ngay.

### 11.4. Secret scope và environment isolation

Tạo danh tính riêng cho:

- Dev/staging/prod.
- Region/cluster nếu blast radius cần tách.
- Producer và consumer nếu quyền khác nhau.
- Runtime app và schema migration job.
- Human administrator và automation.
- HTTP client registrations theo downstream audience/scope.

Không lưu một “master integration password” có quyền vào Kafka, database, RabbitMQ và Pricing API.

### 11.5. Certificate rotation

TLS certificates có trust chain, SAN, expiry và private keys; cần:

1. Phát hành cert mới có SAN/CA phù hợp.
2. Đảm bảo clients trust CA mới trước khi server switch nếu CA đổi.
3. Deploy server cert mới, quan sát handshake.
4. Deploy/rotate client cert cho mTLS theo policy.
5. Recycle connections/sessions được yêu cầu.
6. Xóa CA/credential cũ sau overlap window.
7. Test negative cert revoked/expired/unknown signer.

Không xử lý cert expiry bằng cách tắt hostname verification hoặc trust-all.

---

## 12. Không nhầm authentication failure với connectivity/authorization failure

Một hệ thống thường gom mọi lỗi vào `ConnectionFailedException`. Đây là sai lầm vì policy retry của chúng khác nhau.

| Điểm kết nối | Lỗi authentication | Lỗi authorization | Lỗi transport/capacity |
| --- | --- | --- | --- |
| Kafka | `SaslAuthenticationException` | Topic/group authorization exception | Broker unavailable, TLS handshake, timeout |
| RabbitMQ | Login rejected/AMQP ACCESS_REFUSED (tuỳ handshake) | Vhost/queue/exchange access denied | Connection reset, heartbeat timeout |
| PostgreSQL | SQLSTATE `28P01` | SQLSTATE `42501` | SQLSTATE `08xxx`, pool timeout |
| Redis | `NOAUTH`, `WRONGPASS` | `NOPERM` | Connection refused, TLS timeout |
| MongoDB | AuthenticationException/code 18 theo driver | Unauthorized/code 13 theo driver | Server selection timeout |
| HTTP API | HTTP 401 hoặc provider auth error | HTTP 403/insufficient_scope | 502/503/504, DNS, TLS, read timeout |
| TLS/mTLS | Cert invalid/untrusted (TLS layer) | TLS principal authenticated nhưng app ACL denies | TCP refused, DNS failure |

**Cẩn thận với các mã lỗi:** một proxy/API có thể trả 401/403 không theo thông lệ; một RabbitMQ server có thể trả `ACCESS_REFUSED` trong login handshake lẫn permission paths. Đọc **phase, broker logs và root cause**, không chỉ tên exception.

### 12.1. HTTP 401 và 403

- **401 Unauthorized:** request thiếu/không có valid authentication credentials theo HTTP auth semantics; response thường có challenge.
- **403 Forbidden:** server hiểu request nhưng từ chối vì authorization policy; authenticated client vẫn có thể gặp.
- OAuth bearer errors có thể mang `invalid_token`, `insufficient_scope` và challenge details theo chuẩn tương ứng.

Một 401 do token hết hạn có thể được giải quyết bằng **token refresh rồi retry có giới hạn**. Một 403 do scope/tenant thiếu thường cần provisioning/authorization change, không sửa bằng retry dồn dập. Không tự refresh để vượt security policy.

### 12.2. TLS errors

`SSLHandshakeException` có thể do:

- Client không trust CA/server chain.
- Hostname không nằm trong SAN.
- Certificate expired/not yet valid.
- Unsupported TLS version/cipher.
- Server yêu cầu client certificate nhưng client không gửi.
- Client certificate chain không được server trust.
- Revocation/identity mapping policy.

Một SASL password đúng không sửa được TLS handshake fail xảy ra **trước khi** authentication protocol hoàn tất.

### 12.3. Pool connection failure

Hikari connection-acquisition timeout hoặc Kafka network disconnect có thể xảy ra sau khi credentials được chấp nhận. Đừng rotate passwords bừa bãi khi vấn đề thật là pool exhausted hoặc broker quorum unavailable.

### 12.4. Unknown business outcome

Ngay cả khi đã authenticated và authorized, request có thể được xử lý rồi response bị mất:

~~~mermaid
sequenceDiagram
    participant C as Integration Service
    participant A as HTTP Partner
    participant D as Partner DB
    C->>A: HTTPS POST /reserve + Bearer token + Idempotency-Key K-100
    A->>A: Validate token, scope, tenant
    A->>D: INSERT reservation
    D-->>A: COMMIT
    A--xC: Response lost
    C->>C: Network timeout → UNKNOWN
    C->>A: Lookup status / replay same K-100
    A-->>C: Stored receipt
~~~

Authentication failure trước application execution có thể được phân loại theo contract, nhưng **timeout sau gửi command** không chứng minh transaction rollback. Cần stable operationId, target idempotency và status lookup; không tạo command ID mới sau read timeout.

---

## 13. Retry policy theo nguyên nhân

| Nhóm lỗi | Tự retry? | Điều kiện |
| --- | --- | --- |
| Invalid password/API key | Không nóng | Refresh secret/config, verify provisioning |
| Expired OAuth access token | Có thể 1 lần | Manager acquire token mới, không bypass forbidden |
| Missing Kafka topic/group ACL | Không nóng | Operator cấp quyền đúng |
| Missing RabbitMQ vhost/read/write | Không nóng | Fix broker permissions |
| DB SQLSTATE 42501 | Không nóng | Fix GRANT/role |
| Redis NOPERM | Không nóng | Sửa ACL command/key policy |
| TLS cert expired/SAN mismatch | Không nóng | Sửa trust/PKI, không disable verification |
| Network connection refused/503 | Bounded retries | Exponential backoff/jitter/deadline |
| HTTP 429 | Có thể | Honor `Retry-After` và rate limit |
| SQL deadlock/serialization retry | Có thể | Retry **toàn transaction**, dùng stable business identity |
| Timeout sau gửi POST/COMMIT | Outcome UNKNOWN | Query status hoặc idempotent replay |
| Malformed payload/schema mismatch | Không | Fix contract |
| Kafka consumer rebalance | Framework handling | Preserve offset/inbox semantics, không biến thành auth retry |

Retries phải có **budget xuyên tầng**. Không để HTTP adapter retry 3 lần, business workflow retry 5 lần và broker listener retry 10 lần mà không tính số attempts tối đa. Auth failure thường cần **human/operator intervention hoặc secret rotation**, không cần thundering herd.

---

## 14. Test security ở đúng boundary, không chỉ test service method

### 14.1. Test matrix bắt buộc

| ID | Môi trường | Fault injection | Kỳ vọng |
| --- | --- | --- | --- |
| SEC-01 | Kafka producer | Wrong SASL password | Authentication fails, no publish |
| SEC-02 | Kafka producer | Valid principal, no WRITE ACL | Authorization denied, no message |
| SEC-03 | Kafka consumer | Valid principal, no group READ | Cannot join/read group |
| SEC-04 | Kafka TLS | Untrusted CA/SAN mismatch | Handshake fails, không disable verification |
| SEC-05 | RabbitMQ | Wrong username/password | Login fails |
| SEC-06 | RabbitMQ | Valid user, wrong vhost | Vhost access denied |
| SEC-07 | RabbitMQ | Valid user, no queue READ | Consume rejected |
| SEC-08 | PostgreSQL | Wrong password | SQLSTATE auth failure |
| SEC-09 | PostgreSQL | Valid login, no table SELECT | SQLSTATE insufficient privilege |
| SEC-10 | PostgreSQL TLS | Server cert wrong hostname | `verify-full` rejects |
| SEC-11 | Redis | Wrong ACL password | WRONGPASS |
| SEC-12 | Redis | Valid ACL but forbidden key/command | NOPERM |
| SEC-13 | HTTP client | Missing bearer token | 401/challenge |
| SEC-14 | HTTP client | Valid token, wrong audience/scope | Reject per API policy |
| SEC-15 | HTTP client | Expired token | Refresh/acquire correctly, no infinite retry |
| SEC-16 | HTTP mTLS | Missing/untrusted client certificate | TLS/client identity rejected |
| SEC-17 | Multi-hop | Kafka message forged tenantId | Consumer domain authorization rejects |
| SEC-18 | Credential rotation | New secret active, old revoked | New connections succeed; no leak |
| SEC-19 | Integration | After COMMIT, response lost | UNKNOWN + idempotent reconciliation |
| SEC-20 | Logging | Auth fails with secret-bearing config | No credentials/tokens in logs |

### 14.2. Kafka tests với broker thật

Dùng Kafka Testcontainers hoặc managed test environment có TLS/SASL/ACL cấu hình phù hợp. Embedded/mock Kafka producer không chứng minh broker authorization.

Acceptance case:

~~~text
Given Kafka principal order-producer has WRITE orders.events
When client publishes event E-100
Then broker acknowledges according to acks configuration

Given same principal lacks WRITE billing.events
When client publishes to billing.events
Then broker rejects by ACL
And no unauthorized message appears
And service does not retry indefinitely
~~~

Nếu test environment không bật Kafka authorizer/ACL, test “no WRITE ACL” sẽ không có ý nghĩa. Phải provision broker security cho negative tests thật.

### 14.3. RabbitMQ tests

Dùng RabbitMQ Testcontainers với users/vhosts/permissions được tạo bởi bootstrap/test admin. Test publisher chỉ WRITE, consumer chỉ READ, missing vhost và TLS cases độc lập.

Không chỉ assert `@RabbitListener` Java method xử lý payload rồi kết luận authentication an toàn. Listener authentication diễn ra tại AMQP connection/channel setup.

### 14.4. PostgreSQL tests

Với PostgreSQL Testcontainers, provision ít nhất:

- `order_app` runtime user chỉ CRUD bảng cần thiết.
- `order_migrator` DDL identity riêng.
- `unauthorized_app` không có SELECT target table.
- Password sai và SQLSTATE failure case.
- TLS verification test trong môi trường TLS-enabled phù hợp.

Một test thực tế:

~~~sql
-- Chạy bằng provisioning/migration identity:
GRANT CONNECT ON DATABASE orders TO order_app;
GRANT USAGE ON SCHEMA app TO order_app;
GRANT SELECT ON TABLE app.orders TO order_app;
REVOKE ALL ON TABLE app.secrets FROM order_app;
~~~

Sau đó chạy JDBC bằng runtime user, assert đọc `app.orders` được nhưng `app.secrets` bị từ chối. Những GRANT/REVOKE phải được áp trong test fixture riêng, không ở app business method.

### 14.5. HTTP OAuth2 contract tests

Dùng mock authorization server/token endpoint + MockWebServer/WireMock cho downstream:

1. Client credentials token request đúng client registration, grant type và auth.
2. Gateway **không gửi request business** nếu token acquisition thất bại.
3. Resource server nhận đúng token audience/scope và expiry.
4. Token thiếu scope bị 403; client không retry nóng.
5. Access token hết hạn được manager acquire lại theo policy.
6. Không forward token end-user sai audience.
7. HTTP redirect đến unrelated origin không nhận Authorization header/secret do policy.
8. Timeout sau side effect dùng stable Idempotency-Key.

Với Spring Security, tránh kiểm thử chỉ bằng mock `SecurityContextHolder` rồi suy outbound manager/HTTP interceptor hoạt động; nên có một test với actual RestClient/WebClient config và token endpoint stub.

### 14.6. Test mTLS

Tạo CA và certificates **chỉ dùng trong test**, có SAN theo host test, với private keys nằm trong ephemeral test environment:

- Trusted CA + matching hostname: handshake OK.
- Unknown CA: fail.
- Wrong hostname/SAN: fail.
- Expired/not-yet-valid: fail.
- Missing client cert khi server `needClientAuth`: fail.
- Client cert hợp lệ nhưng application authorization thiếu: handshake OK, business denied.
- Rotation: overlap CA/trust, new connection succeeds.

Không đưa test private keys/certificates dùng chung vào production secret store; không tắt validation để test “succeeded”.

### 14.7. Khi Testcontainers không đủ

Kafka TLS/SASL + ACL hoặc RabbitMQ certificate auth cần server config thật. Nếu không thể dựng trong CI vì hạn chế quyền/PKI, nêu rõ test coverage gap và bổ sung staging security regression với cô lập dữ liệu; **không khai báo PASS cho một negative auth test mà broker thực tế không bật security**.

---

## 15. Giám sát và phân loại tín hiệu bảo mật

### 15.1. Metrics đề xuất

| Metric/event | Ý nghĩa |
| --- | --- |
| `integration.authn.failure` by target | Credentials/token/certificate fail |
| `integration.authz.denied` by resource class | Principal thiếu quyền |
| `integration.tls.handshake.failure` | Server trust/client cert failure |
| `integration.oauth.token.acquire.failure` | OAuth2 client registration/token endpoint |
| `integration.oauth.token.refresh` | Token lifecycle |
| `integration.kafka.topic.authorization.denied` | Kafka topic ACL |
| `integration.kafka.group.authorization.denied` | Consumer group permission |
| `integration.rabbitmq.vhost.denied` | RabbitMQ vhost access |
| `integration.db.insufficient_privilege` | SQL GRANT/RLS |
| `integration.redis.acl.denied` | Redis command/key ACL |
| `integration.connection.retries` | Connection retry activity |
| `integration.business.outcome_unknown` | Remote result not confirmed |
| `integration.secret.rotation.failed` | New credential activation issue |

Những metric names là **đề xuất application instrumentation**, không khẳng định Spring Actuator/Micrometer tạo sẵn tất cả. Framework/client libraries có logging/metrics riêng; cần map vào taxonomy thống nhất nhưng không làm lộ secrets.

### 15.2. Cardinality và privacy

Prometheus tags nên dùng `target_type=kafka|rabbitmq|jdbc|redis|http`, `downstream=pricing`, `error_category=authentication|authorization|tls|network`, `environment=prod`. **Không gắn access token, password, full certificate subject, raw SQL, email, operationId hay username có cardinality cao vào metrics labels.**

Structured logs có thể chứa:

~~~json
{
  "service": "inventory-service",
  "downstream": "pricing",
  "boundary": "http-oauth2",
  "errorCategory": "authorization",
  "operationId": "K-100",
  "action": "price.read",
  "result": "denied"
}
~~~

Một `operationId` trong log phải có access control và retention phù hợp; không cho vào metrics label. Không log Authorization header, OAuth client secret, SASL JAAS config có password, full JDBC URL chứa secret hoặc Redis AUTH values.

### 15.3. Alerts theo lỗi gốc

- Nhiều Kafka auth failures **ngay sau rollout** → secret/config/provider mismatch.
- RabbitMQ vhost denied → wrong vhost hoặc permission provisioning.
- SQLSTATE 42501 → missing DB grants, không phải Hikari pool tuning.
- HTTP 403 chỉ trên một tenant → domain permission/scope policy.
- TLS handshake failures tăng cùng ngày CA rotation → trust overlap/hostname/SAN.
- Token acquisition failures → IdP availability/client secret rotation.
- Tăng connection timeouts cùng Hikari pending → capacity, không tự coi auth.

Một alert chỉ ghi “connection failed” sẽ khiến operator phải mò nhiều hệ thống; nên giữ `phase`/`target` và sanitized error category.

---

## 16. Runbook xử lý sự cố xác thực kết nối

| Triệu chứng | Kiểm tra đầu tiên | Không nên làm |
| --- | --- | --- |
| Kafka SASL login rejected | SASL mechanism, listener, principal, secret, JAAS formatting | Tắt SASL/đổi PLAINTEXT |
| Kafka TopicAuthorizationException | Topic ACL principal, resource name và operation | Cấp cluster admin cho app |
| Kafka GroupAuthorizationException | Group ID, consumer group ACL | Dùng group admin toàn cluster |
| Kafka SSL handshake failure | CA, SAN, hostname, TLS version, client cert policy | Disable endpoint identification |
| RabbitMQ login rejected | Username/password, vhost, mechanism, guest restrictions | Mở guest remote login |
| RabbitMQ ACCESS_REFUSED khi declare/bind | configure/write/read resource permissions | Cấp `.*` toàn vhost không review |
| PostgreSQL 28P01 | DB role/password, provider token/rotation | Retry login nóng |
| PostgreSQL 42501 | Schema USAGE/table GRANT/RLS/sequence privileges | Dùng SUPERUSER runtime |
| PostgreSQL certificate verify failed | `sslmode=verify-full`, root CA, hostname | Hạ xuống `sslmode=disable` |
| Redis WRONGPASS | ACL username/password, disabled user | Bỏ ACL |
| Redis NOPERM | Commands/keys application thật sự dùng | Cấp `+@all ~*` vô cớ |
| MongoDB unauthorized | authSource, role, db/collection | Cấp root role |
| HTTP 401 invalid_token | Expiry, issuer, JWKS, audience, token acquisition | Forward token khác audience |
| HTTP 403 insufficient_scope | Scope/role/tenant policy | Retry vô hạn |
| OAuth token endpoint 401 | Client registration secret, grant/client auth mode | Log client secret để debug |
| mTLS client cert rejected | Client key/cert/CA, EKU, SAN/mapping | Trust all certificate |
| Cache/DB timeout | Network/pool/time budget | Rotate secret không có bằng chứng |
| After remote COMMIT response lost | Operation ID, remote receipt/status | Tạo command mới với UUID khác |

### 16.1. Quy trình chẩn đoán có hệ thống

1. **Xác định chính xác boundary**: Kafka producer, Kafka consumer, RabbitMQ, PostgreSQL, Redis hay HTTP Pricing API?
2. **Xác định giai đoạn**: DNS/TCP → TLS handshake → authentication → authorization → business command → acknowledgement.
3. **Đối chiếu identity thật**: service principal/DB role/OAuth client registration, không dựa tên pod.
4. **Kiểm secrets/CA** mà không in giá trị: source, version, mount, permissions, expiry/rotation.
5. **Kiểm backend policy**: topic/group ACL, vhost permissions, SQL GRANT, Redis ACL, HTTP audience/scope/tenant.
6. **Xác nhận network** và DNS/SAN/hostname nếu thất bại trước authentication.
7. **Kiểm pool/capacity** nếu sự cố intermittent và backend auth logs không báo reject.
8. **Phân loại retry**: authz/authn permanent, token refresh bounded, network transient, business outcome unknown.
9. **Reproduce bằng test identity tối thiểu** trong môi trường an toàn, không sử dụng production secrets.
10. **Ghi audit và sửa policy** đúng mức, không cấp toàn quyền hoặc hạ TLS.
11. **Kiểm sau rotation/rollout** trên new connections, không chỉ existing pooled sessions.
12. **Bảo vệ business outcome**: nếu request đã có thể COMMIT, reconciliation với stable operationId.

---

## 17. Case study: Order Service → Kafka → Inventory → PostgreSQL → Pricing API

### 17.1. Yêu cầu

Một event `OrderConfirmed` xuất phát từ Order Service:

~~~json
{
  "eventId": "e1001f0a-27e7-4bf8-aee6-8e49ab7523a7",
  "orderId": "ORD-100",
  "tenantId": "TENANT-A",
  "amountMinor": 150000,
  "schemaVersion": 2
}
~~~

Luồng:

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant K as Kafka
    participant I as Inventory Service
    participant D as Inventory DB
    participant AS as OAuth IdP
    participant P as Pricing API
    O->>K: SASL_SSL producer: event E-100
    K->>K: Check topic WRITE ACL
    K-->>O: ACK
    K->>I: Consumer group: deliver E-100
    I->>I: Validate schema + authenticated service trust
    I->>D: JDBC role inventory_app: inbox + reserve
    D-->>I: COMMIT
    I->>AS: client_credentials pricing.read
    AS-->>I: Token aud=pricing-api
    I->>P: HTTPS Bearer token, tenant policy
    P-->>I: Pricing result
    I->>K: Commit offset/ACK according to Kafka listener policy
~~~

Trong thiết kế thực, **gọi Pricing API và commit offset** cần sắp xếp theo business/transaction contract. Nếu remote Pricing request có side effect, dùng outbox/saga/idempotency, không giữ PostgreSQL transaction mở qua HTTP call nhiều giây. Diagram trên thể hiện các boundaries, **không phải một transaction ACID xuyên hệ**.

### 17.2. Credential inventory

| Identity | Dùng cho | Chỉ có quyền |
| --- | --- | --- |
| `order-producer` | Kafka | WRITE `orders.confirmed` |
| `inventory-consumer` | Kafka | READ `orders.confirmed` + READ group `inventory-v2` |
| `inventory_app` | PostgreSQL | CRUD inventory/inbox/outbox tables |
| `inventory_cache` | Redis | Key namespace `cache:inventory:*` và commands cần |
| `inventory-pricing-client` | OAuth2 | Lấy token `pricing.read` audience Pricing API |
| `inventory-migrator` | PostgreSQL migration | DDL có kiểm soát qua deployment job |

Không dùng `order-producer` như DB user hoặc `inventory_app` như HTTP bearer token. Quyền từ mũi tên Kafka không tự lan sang HTTP.

### 17.3. Test lỗi tập trung

**Scenario A — Kafka READ permission bị thu hồi:**

~~~text
Given consumer authenticates with valid SCRAM secret
When Kafka denies READ on topic orders.confirmed
Then listener cannot process records
And metrics show authorization denied
And service does not endlessly reconnect with same permission error
~~~

**Scenario B — PostgreSQL role thiếu INSERT:**

~~~text
Given Kafka consumer authenticated and authorized
When INSERT inventory_reservations is denied
Then local SQL transaction rolls back
And Kafka offset is not advanced as business-applied
And message can be retried/parked according to listener policy
~~~

**Scenario C — Pricing scope thiếu:**

~~~text
Given Inventory authenticates to Pricing OAuth token endpoint
When token lacks pricing.read scope
Then Pricing denies the read
And application records authz failure without leaking token
And retry does not turn the event into a duplicate reservation
~~~

**Scenario D — mất response sau commit:**

~~~text
Given Inventory DB COMMIT for operationId K-100
When Pricing API response is lost or Kafka offset commit fails
Then outcome/progress is reconciled using stable identities
And duplicate event processing is blocked by inbox/unique constraint
~~~

**Đây là điểm nối quan trọng giữa bảo mật và reliability:** Đủ quyền để nhận event không có nghĩa mọi downstream actions thành công; lỗi auth/permission có thể xảy ra **giữa workflow** và phải được xử lý theo transaction/idempotency boundaries.

---

## 18. Anti-pattern thường gặp

| Anti-pattern | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Dùng chung password cho Kafka, DB, RabbitMQ, HTTP | Blast radius quá lớn, không đúng protocol | Service identity/secret per boundary |
| Bật TLS rồi coi auth/ACL đã xong | TLS transport ≠ application authorization | Kiểm principal và resource permissions |
| Chỉ kiểm certificate CA, tắt hostname verify | MITM/wrong peer | CA + SAN/hostname validation |
| Dùng truststore như client mTLS identity | Truststore không chứa private key client | Client key/cert khi server yêu cầu |
| Cấu hình Kafka `SASL_SSL` mà nghĩ bắt buộc mTLS | SASL và TLS client auth là khác nhau | Chọn mechanism theo broker listener |
| Kafka producer có acks=all nên coi consumer applied | Broker ACK ≠ DB COMMIT | Inbox/consumer processing receipt |
| Kafka consumer có topic READ nhưng thiếu group READ | Khác resource ACL | Provision cả topic và group |
| RabbitMQ user có login nhưng không có vhost access | Credentials ≠ vhost permission | Per-vhost grants |
| Cho RabbitMQ app `configure/write/read=.*` vô điều kiện | Quyền quá rộng | Declare topology riêng, least privilege |
| Dùng PostgreSQL `postgres` superuser cho app | Có DDL/admin quyền lớn | Runtime role riêng |
| Chọn `sslmode=require` như verify-full | Không bảo đảm hostname verification như verify-full | Full cert/hostname verification |
| Cache Redis AUTH đúng là truy cập mọi keys | ACL theo commands/patterns | Prefix, command restrictions |
| Đọc `tenantId` từ Kafka header làm auth identity | Header có thể giả mạo | Domain authz và provenance policy |
| Forward inbound JWT qua mọi downstream | Wrong audience/confused deputy | Service token/token exchange |
| Dùng OAuth2 resource server config để tự gọi HTTP | Inbound verifier không xin token | OAuth2 client registration/manager |
| Hardcode access token trong `application.yml` | Hết hạn/lộ secret | Token acquisition/refresh |
| Lưu access token vào outbox | Token stale/PII leakage | Lưu business intent, lấy credential lúc relay |
| Ghi full JDBC URL, SASL JAAS, Authorization vào logs | Rò secret | Sanitized diagnostics |
| Retry 401/403/28P01/NOPERM liên tục | Không sửa được quyền, gây outage | Fail fast + operator action |
| Tắt TLS/mTLS khi handshake lỗi | Giảm bảo mật, có thể lộ credentials | Sửa cert/CA/SAN |
| Chỉ test service mock mà không bật ACL broker | Test không kiểm tra authz thật | Secure integration test |
| Rotate secret nhưng không recycle connections | Client vẫn dùng credential cũ | Rotation rollout/new-connection validation |
| Timeout sau POST được coi là chưa commit | Remote outcome UNKNOWN | Stable key/status lookup |
| Dùng một account runtime để chạy migrations | Quyền rộng lâu dài | Separate migration identity |

---

## 19. Checklist production

### A. Nhận diện boundaries

- [ ] Liệt kê mọi outbound/inbound connection theo caller, target, environment.
- [ ] Tách rõ transport TLS, client authentication và resource authorization.
- [ ] Có service principal riêng cho Kafka/Rabbit/DB/Redis/HTTP theo nhu cầu.
- [ ] Không reuse credentials hoặc forward token sai audience.
- [ ] Kiểm end-user authorization và workload authentication độc lập.
- [ ] Không tin tenant/correlation headers như đã authenticated.

### B. Kafka và RabbitMQ

- [ ] Kafka `security.protocol`, `sasl.mechanism`, JAAS/provider và TLS trust đúng.
- [ ] Kafka producer WRITE topic và consumer READ topic/group được cấp tối thiểu.
- [ ] Không dùng `SASL_PLAINTEXT` khi có credentials trên mạng không tin cậy.
- [ ] Kafka mTLS identity mapping (nếu dùng) được test với certificate rotation.
- [ ] RabbitMQ dùng đúng vhost và quyền configure/write/read.
- [ ] RabbitMQ TLS verify server cert/hostname, không dùng guest remote.
- [ ] Publisher confirm/consumer ACK được hiểu là delivery, không phải business auth.

### C. Databases và cache

- [ ] PostgreSQL `sslmode=verify-full` với CA/SAN đúng trong môi trường yêu cầu TLS.
- [ ] DB role runtime không có DDL/admin quyền không cần.
- [ ] Migration identity độc lập với runtime role.
- [ ] Database permissions bao gồm đúng schema/tables/sequences/RLS.
- [ ] R2DBC/JDBC/MongoDB/Redis dùng driver-specific auth/TLS config.
- [ ] Redis ACL user chỉ được key patterns/commands cần thiết.
- [ ] Cache không thay authoritative business authorization.

### D. HTTP services

- [ ] OAuth2 client credentials registration/manager phù hợp security framework version.
- [ ] Client token được cấp đúng issuer, audience, scopes, expiry và target service.
- [ ] Resource server validate token và domain permissions độc lập.
- [ ] Token acquisition/cache/refresh/revocation có runbook.
- [ ] Không forward inbound JWT sang downstream không đúng audience.
- [ ] API keys/HMAC/mTLS có canonicalization, verification và rotation phù hợp.
- [ ] HTTPS hostname/server certificate được xác minh, không trust-all.

### E. Secrets, reliability và operations

- [ ] Secret injection từ secret manager/orchestrator, không hardcode.
- [ ] Client key, passwords, tokens không vào logs, metrics, outbox, Git.
- [ ] Có credential/certificate rotation overlap và new-connection tests.
- [ ] Không retry nóng authentication/authorization permanent failures.
- [ ] Retry network transient có budget/backoff/jitter/deadline.
- [ ] Commands có stable operationId/idempotency và UNKNOWN reconciliation.
- [ ] Có secure integration tests cho invalid auth, denied ACL, wrong SAN, wrong audience.
- [ ] Logs/metrics phân loại authn, authz, TLS, network và business commit.
- [ ] Có alert khi credentials/certificates sắp hết hạn và khi permission drift.
- [ ] Incident runbook không yêu cầu tắt security để khôi phục.

**Ghi nhớ:** Kafka và RabbitMQ xác thực **broker client principal** rồi kiểm quyền trên topic/group hoặc vhost/exchange/queue; PostgreSQL xác thực **database role** rồi kiểm `GRANT`/RLS; Redis dùng **ACL user** cùng command/key permissions; HTTP service dùng **bearer token, API key, HMAC hoặc mTLS** rồi kiểm audience/scope/resource policy. TLS bảo vệ transport và xác thực server, mTLS có thể xác thực client; không cơ chế nào một mình bảo đảm **remote business transaction** đã hoàn thành. Trong Spring Boot Integration, hãy cấu hình **mỗi boundary theo protocol của nó**, cấp quyền tối thiểu, quản lý secret rotation và kiểm thử cả lỗi xác thực lẫn lỗi phân quyền/đường truyền.

## Tài liệu tham khảo

- [Spring Boot — Kafka](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): cấu hình `spring.kafka.*`, producer và consumer.
- [Apache Kafka — Security](https://kafka.apache.org/documentation/#security): SASL, TLS, ACL và security protocols.
- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/documentation/#security_authz): resource operations/permissions.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): RabbitMQ ConnectionFactory và SSL config.
- [RabbitMQ — Authentication](https://www.rabbitmq.com/docs/access-control): users, authentication mechanisms và authorization.
- [RabbitMQ — TLS](https://www.rabbitmq.com/docs/ssl): server/client TLS certificates và validation.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): delivery acknowledgement semantics.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource/Hikari/JDBC configuration.
- [PostgreSQL — Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html): `pg_hba.conf`, supported auth mechanisms.
- [PostgreSQL — Database Roles and Privileges](https://www.postgresql.org/docs/current/user-manag.html): roles, privileges và grants.
- [PostgreSQL JDBC — SSL](https://jdbc.postgresql.org/documentation/ssl/): JDBC TLS trust và `sslmode`.
- [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): Redis user/command/key permissions.
- [Spring Data Redis — Reference](https://docs.spring.io/spring-data/redis/reference/): Lettuce, Redis connection và ACL.
- [MongoDB — Authentication](https://www.mongodb.com/docs/manual/core/authentication/): SCRAM, authSource, X.509.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized clients, client credentials.
- [Spring Security — RestClient OAuth2](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): `OAuth2ClientHttpRequestInterceptor` và manager.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): inbound bearer validation.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token và errors.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client credentials grant.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound tokens/client authentication.
- [Spring Integration — Reference](https://docs.spring.io/spring-integration/reference/): adapters, flows và messaging boundaries.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate-safe processing.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): durable integration intents và retry.
