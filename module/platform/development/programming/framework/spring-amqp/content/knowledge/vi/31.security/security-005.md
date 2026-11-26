# Quản lý mật khẩu, chứng chỉ và bí mật theo môi trường

Một ứng dụng **Spring AMQP** có thể gửi message bằng `RabbitTemplate` và nhận bằng `@RabbitListener` rất ổn định ở môi trường phát triển, nhưng liên tục mất kết nối khi đưa lên staging hoặc production. Nguyên nhân không nhất thiết nằm ở exchange, queue, binding hay listener: tài khoản RabbitMQ không đúng vhost, mật khẩu đã được xoay vòng, chứng chỉ TLS hết hạn, CA chưa được tin cậy, hoặc tên máy chủ không khớp chứng chỉ đều có thể khiến kết nối không được thiết lập.

Nguy hiểm hơn, việc khắc phục tạm thời bằng cách **ghi mật khẩu vào `application.yml`**, dùng chung tài khoản `guest`, hoặc **tắt xác minh chứng chỉ** có thể khiến hệ thống hoạt động trở lại nhưng mở ra nguy cơ lộ dữ liệu, bị giả mạo broker hay chiếm quyền publish/consume.

Bài thuộc chương **Bảo mật** của module **SPRING_AMQP**, tập trung vào **quản lý mật khẩu, chứng chỉ và bí mật theo môi trường**. Phạm vi là kết nối RabbitMQ qua Spring Boot/Spring AMQP, quản trị danh tính, phân quyền, TLS/mTLS, vòng đời secret và cách kiểm chứng để luồng bất đồng bộ vẫn đáng tin cậy khi chuyển môi trường hoặc thay đổi thông tin xác thực.

Sau bài học, bạn có thể:

- Phân biệt **authentication**, **authorization**, **mã hóa kết nối TLS** và **bảo vệ dữ liệu nghiệp vụ**.
- Cấu hình `spring.rabbitmq.*` mà không ghi mật khẩu hay private key vào Git, image hoặc log.
- Chọn giữa biến môi trường, secret được mount thành file, `configtree:` và secret manager theo từng môi trường.
- Thiết lập TLS một chiều hoặc mTLS với **CA trust**, **certificate**, **private key**, **hostname verification** và `SslBundle`.
- Áp dụng RabbitMQ **vhost và permission theo vai trò**, tách tài khoản publisher/consumer/admin.
- Lập quy trình **xoay vòng mật khẩu, chứng chỉ, CA** có kiểm tra kết nối, độ trễ publish, consumer recovery và khả năng khôi phục.

## 1. Phân biệt bốn lớp bảo vệ

Một kết nối RabbitMQ an toàn không thể đánh giá chỉ bằng câu hỏi “có mật khẩu không?”.

| Lớp bảo vệ | Câu hỏi | Cơ chế thường dùng | Nếu thiếu |
| --- | --- | --- | --- |
| **Authentication** | Ứng dụng này là ai? | Username/password, xác thực X.509 với cơ chế `EXTERNAL` khi được cấu hình | Người không được phép có thể mạo danh ứng dụng |
| **Authorization** | Tài khoản được làm gì, ở vhost nào? | RabbitMQ vhost, `configure/write/read` permissions, topic permissions | Consumer có thể publish/xóa topology ngoài nhiệm vụ |
| **Transport security** | Kết nối tới đúng broker và có bị nghe lén không? | TLS, trust CA, xác minh certificate và hostname; mTLS khi cần | Mật khẩu và payload có nguy cơ bị lộ hoặc gửi tới broker giả mạo |
| **Data/application security** | Payload, log và dữ liệu lưu trữ được bảo vệ thế nào? | Không nhét secret vào message, kiểm soát schema, mã hóa dữ liệu nhạy cảm, disk encryption, retention | Dù TLS an toàn, dữ liệu vẫn có thể lộ ở DB, log, DLQ hoặc disk |

**TLS một chiều** thường có nghĩa client **xác minh broker**, trong khi client vẫn dùng username/password để đăng nhập vào RabbitMQ. **mTLS** bổ sung chứng chỉ client để broker xác minh danh tính kết nối ở tầng TLS. Tuy nhiên, **mTLS không tự động thay username/password**: chỉ khi RabbitMQ và client cùng cấu hình cơ chế SASL `EXTERNAL`/x.509 authentication phù hợp thì chứng chỉ mới có thể đóng vai trò danh tính đăng nhập thay cho mật khẩu.

```mermaid
flowchart LR
    A["Spring AMQP app<br/>RabbitTemplate / @RabbitListener"] -->|"TLS: chứng minh broker<br/>và mã hóa kết nối"| B["RabbitMQ"]
    A -->|"Username/password<br/>hoặc EXTERNAL nếu bật"| C["Authentication"]
    C --> D["Authorization<br/>vhost + configure/write/read"]
    D --> E["Exchange / Queue / Binding"]
    E --> F["Business processing<br/>DB + ACK + retry"]
    S["Secret manager / mounted secrets"] -.->|"Cấp thông tin xác thực<br/>và CA/client key"| A
```

Các cơ chế xác nhận giao nhận `publisher confirm`, `publisher return` và consumer `ack/nack` không thay thế authentication hay TLS. Ngược lại, một connection đã xác thực thành công cũng **không đảm bảo message được định tuyến hoặc nghiệp vụ đã commit**.

## 2. Tách cấu hình theo môi trường, không sao chép secret

Ứng dụng thường có ít nhất ba môi trường:

| Thành phần | Development | Staging | Production |
| --- | --- | --- | --- |
| RabbitMQ | Broker cục bộ hoặc sandbox cô lập | Cluster/môi trường kiểm thử giống production | Cluster production có giám sát và SLA |
| Tài khoản | User riêng cho dev | Service account riêng cho staging | Service account riêng từng ứng dụng/vai trò |
| Vhost | `orders-dev` | `orders-staging` | `orders-prod` |
| TLS | CA nội bộ hoặc CA dev được tin cậy; cổng plaintext chỉ ở loopback thật sự cô lập | TLS bắt buộc, xác minh đầy đủ | TLS bắt buộc, xác minh đầy đủ; mTLS nếu yêu cầu |
| Nguồn secret | Secret cục bộ không commit | Secret manager/volume bảo vệ | Secret manager, cơ chế cấp phát/audit và rotation |
| Quyền | Hạn chế theo nhu cầu test | Gần production nhưng **không chung credential** | Least privilege, chia quyền publish/consume/admin |
| Rotation | Tập dượt được | Thử trước các thay đổi thật | Quy trình thay đổi có canary, rollback và kiểm tra |

**Không dùng một mật khẩu cho cả ba môi trường.** Nếu một máy lập trình hoặc CI job bị lộ credential dev, credential đó không được phép truy cập production. Tương tự, không cấp chung private key/certificate client cho các namespace, ứng dụng hoặc nhóm có vòng đời khác nhau.

### 2.1. Những gì được lưu trong mã nguồn

Trong Git có thể lưu **cấu hình không nhạy cảm**: hostname, vhost logic, tên SSL bundle, tên biến môi trường, timeout, retry/backoff, tên queue/exchange/binding. Không commit:

- Username/password thật trong `application.yml`, `application-prod.yml`, `docker-compose.yml`, Helm values hay file `.env` được track.
- Client **private key**, file PKCS#12/JKS có private key, keystore password, access token, API key của secret manager.
- Connection URI có chứa `amqp://user:password@host` hoặc `amqps://user:password@host`.
- File debug, crash dump hoặc log in nội dung `Environment`/`ConnectionFactory` mà có thể chứa secret.

**CA certificate công khai không giống private key.** Một CA certificate phục vụ xác minh server thông thường có thể được phân phối qua cấu hình hoặc hệ thống trust store, nhưng vẫn phải quản lý nguồn CA đáng tin cậy để tránh bị thay thế trái phép. Client certificate là phần **public** của danh tính mTLS; **private key tương ứng phải được giữ bí mật**.

## 3. Spring Boot: đọc credential từ cấu hình ngoài

Với Spring Boot dùng `spring-boot-starter-amqp` và RabbitMQ **AMQP 0-9-1**, các thuộc tính phổ biến nằm dưới `spring.rabbitmq.*`. Một cấu hình cơ sở **không có secret thật**:

```yaml
# application.yml — có thể đưa vào Git
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: ${RABBITMQ_PORT:5671}
    virtual-host: ${RABBITMQ_VHOST}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
      verify-hostname: true
      validate-server-certificate: true
```

`${RABBITMQ_PASSWORD}` là **placeholder** mà Spring giải quyết tại runtime, không phải mật khẩu. Không đặt giá trị mặc định kiểu `${RABBITMQ_PASSWORD:admin123}` cho secret; khi secret thiếu, nên để ứng dụng **khởi động thất bại rõ ràng** thay vì kết nối bằng một mật khẩu yếu bất ngờ.

Spring Boot hỗ trợ relaxed binding, ví dụ biến môi trường `SPRING_RABBITMQ_PASSWORD` có thể ánh xạ trực tiếp vào thuộc tính `spring.rabbitmq.password`. Nếu dùng biến riêng `RABBITMQ_PASSWORD` thì tham chiếu tường minh bằng placeholder như trên.

**Biến môi trường là bước tiến so với hardcode, nhưng chưa phải nơi lưu secret lý tưởng cho mọi hệ thống.** Giá trị có thể bị lộ qua quyền xem process/container, bản chụp chẩn đoán, thao tác debug hoặc công cụ vận hành. Khi môi trường hỗ trợ secret volume/secret manager, dùng nguồn được cấp phát với ACL/RBAC chặt chẽ.

### 3.1. Không nhét credential vào connection URI

Tránh:

```yaml
# KHÔNG LÀM: URL chứa mật khẩu ngay trong file cấu hình.
spring:
  rabbitmq:
    addresses: "amqps://orders-api:real-password@rabbitmq.prod.example:5671"
```

Thay vào đó, tách host/port (hoặc URI **không có userinfo**) khỏi username/password. URI có credential dễ xuất hiện nguyên văn trong log, tracing, dashboard, báo cáo lỗi hoặc bản sao cấu hình.

Nếu khai báo cả `addresses` lẫn `host/port`, Spring Boot ưu tiên `addresses` cho đích kết nối; cần thống nhất cách cấu hình, tránh tưởng ứng dụng dùng hostname trong `host` nhưng thực ra vẫn kết nối tới URI khác.

### 3.2. RabbitTemplate và @RabbitListener dùng cùng nguồn credential

Khi Boot tạo `CachingConnectionFactory` từ các thuộc tính trên, `RabbitTemplate`, listener container và `RabbitAdmin` có thể sử dụng connection factory đó:

```java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class SecureOrderMessaging {
    private final RabbitTemplate template;

    public SecureOrderMessaging(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(String eventId, String payload) {
        template.convertAndSend(
                "orders.events", "order.created", payload,
                message -> {
                    message.getMessageProperties().setMessageId(eventId);
                    return message;
                });
    }
}

@org.springframework.stereotype.Component
class SecureOrderListener {
    @RabbitListener(queues = "orders.jobs")
    public void handle(String payload) {
        // Gọi service nghiệp vụ: transaction, idempotency, retry...
    }
}
```

**Không truyền password vào constructor của mỗi publisher/listener** và không ghi password vào message header. Cấu hình kết nối nên được quản lý tập trung. Đoạn code chỉ minh họa việc dùng chung connection factory; topology `orders.events`/`orders.jobs` và binding phải được khai báo trước hoặc tạo bởi thành phần có đủ quyền.

## 4. Dùng secret được mount thành file và Spring configtree

Khi Docker/Kubernetes hoặc secret manager đưa thông tin bí mật vào một volume, Spring Boot có thể đọc từng file như một property qua `spring.config.import=configtree:...`.

Ví dụ một workload được mount vào thư mục:

```text
/run/secrets/rabbitmq/
  spring.rabbitmq.username  # nội dung: tên service account
  spring.rabbitmq.password  # nội dung: password thật, KHÔNG đưa vào Git

/run/certs/rabbitmq/
  ca.pem                    # CA xác thực RabbitMQ server
```

Khi tên file là `spring.rabbitmq.username` và `spring.rabbitmq.password`, chúng được ánh xạ thành đúng hai thuộc tính tương ứng:

```yaml
# application-prod.yml — chỉ chứa đường dẫn
spring:
  config:
    import: "configtree:/run/secrets/rabbitmq/"
  rabbitmq:
    host: rabbitmq.prod.example
    port: 5671
    virtual-host: orders-prod
    ssl:
      enabled: true
      bundle: rabbitmq-trust

  ssl:
    bundle:
      pem:
        rabbitmq-trust:
          truststore:
            certificate: "file:/run/certs/rabbitmq/ca.pem"
```

Chọn **`configtree:` không có `optional:`** khi secret mount là yêu cầu bắt buộc. Nếu mount thiếu, startup cần báo lỗi; dùng `optional:configtree:` chỉ khi thực sự có đường dự phòng được thiết kế và kiểm soát.

**Không lưu hai bộ thông tin xác thực mâu thuẫn** giữa biến môi trường, configtree và file profile rồi mặc định đoán nguồn nào thắng. Spring Boot có thứ tự ưu tiên nguồn cấu hình (*property source precedence*); kiểm tra nguồn thực tế được bind vào connection factory mà **không in giá trị secret**.

Tệp secret cần quyền truy cập tối thiểu theo UID/GID của ứng dụng, container security context và RBAC của platform. **Kubernetes Secret được mã hóa base64 trong manifest không đồng nghĩa đã được mã hóa an toàn**; bảo vệ secret ở rest, quyền truy cập API, lưu trữ GitOps và quyền mount là trách nhiệm riêng.

### Khi nào dùng secret manager?

Với môi trường lớn, có thể dùng Vault, AWS Secrets Manager, Azure Key Vault, Google Secret Manager hoặc hệ thống quản lý bí mật nội bộ để cấp/luân chuyển secret. Tùy tích hợp, dữ liệu có thể được inject qua volume, môi trường runtime, sidecar hoặc Spring Config integration.

Đánh giá theo: **quyền truy cập theo workload identity**, audit, version, TTL/expiry, rotation, mã hóa, network và hành vi khi dịch vụ cấp secret tạm không sẵn sàng. Không yêu cầu ứng dụng gọi secret manager mỗi lần xử lý message nếu có thể cấp phát/cached credential an toàn tại vòng đời connection.

## 5. TLS: trust broker certificate, không chỉ bật cổng 5671

AMQP 0-9-1 không mã hóa mặc định khi dùng kết nối plaintext (thường là **5672**). Kết nối TLS trực tiếp thường sử dụng **5671**, nhưng cổng thực tế do vận hành cấu hình; một port number tự nó không chứng minh đã bật TLS.

Trong **server-authenticated TLS**, RabbitMQ trình certificate chain và Spring client kiểm tra:

1. Chuỗi chứng chỉ có kết thúc tại CA mà ứng dụng tin cậy không?
2. Chứng chỉ còn hiệu lực, đúng mục đích (EKU) và không bị từ chối theo chính sách TLS không?
3. **Hostname** mà ứng dụng kết nối có khớp một mục trong **Subject Alternative Name (SAN)** của chứng chỉ không?
4. Phiên bản TLS và cipher suite hai bên có tương thích không?

Nếu ứng dụng kết nối tới `rabbitmq.prod.example` nhưng chứng chỉ chỉ có `DNS:rabbitmq.internal`, việc CA được tin cậy **chưa đủ**; hostname verification phải từ chối kết nối.

**Không dùng những “cách sửa” sau trong production:** `verify-hostname=false`, `validate-server-certificate=false`, TrustManager chấp nhận mọi chứng chỉ, hoặc tắt TLS để tránh lỗi handshake. Cách đúng là dùng tên DNS đúng, cấp lại chứng chỉ đúng SAN và phân phối CA hợp lệ.

### 5.1. SslBundle PEM cho TLS một chiều

Với Spring Boot hỗ trợ SSL bundles, ví dụ dùng `spring.rabbitmq.ssl.bundle` và nguồn CA dưới `spring.ssl.bundle.pem`:

```yaml
spring:
  rabbitmq:
    host: rabbitmq.prod.example
    port: 5671
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
      bundle: rabbitmq-client-trust
      verify-hostname: true

  ssl:
    bundle:
      pem:
        rabbitmq-client-trust:
          truststore:
            certificate: "file:/run/certs/rabbitmq/ca-chain.pem"
```

Trong cấu hình này, **truststore** chứa CA/chain được tin cậy để xác minh **broker**. Nó không chứa private key của client và **không bật mTLS**. Tên `rabbitmq-client-trust` chỉ là tên bundle logic; đường dẫn phải tồn tại, được cấp quyền đọc cho service và chứa chứng chỉ phù hợp.

**SSL bundle là tính năng phụ thuộc phiên bản Spring Boot**; hãy xác minh `spring.rabbitmq.ssl.bundle` được hỗ trợ trong version chạy thực tế, đặc biệt nếu nâng cấp từ ứng dụng Boot cũ.

### 5.2. Cách thay thế: truststore JKS/PKCS12

Nếu tổ chức quản lý trust material bằng Java KeyStore, có thể cấu hình qua các property trực tiếp thay vì SSL bundle:

```yaml
# Cách thay thế SSL bundle, KHÔNG trộn hai cấu hình một cách tùy tiện.
spring:
  rabbitmq:
    host: rabbitmq.prod.example
    port: 5671
    ssl:
      enabled: true
      trust-store: "file:/run/certs/rabbitmq/truststore.p12"
      trust-store-type: PKCS12
      trust-store-password: ${RABBITMQ_TRUSTSTORE_PASSWORD}
      verify-hostname: true
      validate-server-certificate: true
```

**Password của truststore** bảo vệ truy cập file container, không phải mật khẩu đăng nhập RabbitMQ. Nó cũng phải lấy từ nguồn bí mật; không đặt cùng file keystore được đưa lên Git. Nếu bundle đã được sử dụng, nên giữ một chiến lược cấu hình TLS nhất quán và kiểm chứng bằng integration test.

## 6. mTLS: chứng chỉ client và danh tính RabbitMQ là hai việc

Với **mutual TLS (mTLS)**:

- Client xác minh **certificate của broker** dựa trên CA/hostname.
- Broker yêu cầu và xác minh **certificate của client** dựa trên CA tin cậy.
- Client cần **client certificate + private key** tương ứng, được phép truy cập đúng ứng dụng.

Thêm `keystore` vào bundle để client có thể trình chứng chỉ:

```yaml
spring:
  rabbitmq:
    host: rabbitmq.prod.example
    port: 5671
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
      bundle: rabbitmq-mtls
      verify-hostname: true

  ssl:
    bundle:
      pem:
        rabbitmq-mtls:
          truststore:
            certificate: "file:/run/certs/rabbitmq/server-ca.pem"
          keystore:
            certificate: "file:/run/secrets/rabbitmq/client.crt"
            private-key: "file:/run/secrets/rabbitmq/client.key"
```

Ví dụ **vẫn dùng username/password** để authenticate ở tầng AMQP. Chứng chỉ client là bước kiểm tra danh tính kết nối ở tầng TLS; broker phải cấu hình yêu cầu/xác minh client certificate (ví dụ `verify_peer` và `fail_if_no_peer_cert`), chứ không phải client tự khai báo mTLS là đủ.

Nếu muốn **chỉ xác thực bằng x.509 thay cho password**, RabbitMQ cần bật và cấu hình plugin `rabbitmq_auth_mechanism_ssl`, cơ chế `EXTERNAL`, quy tắc ánh xạ danh tính chứng chỉ sang RabbitMQ user và permissions tương ứng; phía Java client cũng phải dùng SASL EXTERNAL. **Không xóa `username/password` trong YAML rồi mặc định mTLS sẽ tự đăng nhập được.**

### 6.1. Các thành phần chứng chỉ và vòng đời

| Thành phần | Chứa gì? | Nằm ở đâu? | Cần giữ bí mật? |
| --- | --- | --- | --- |
| `server.crt` và chain | Public certificate của broker | Broker, phân phối khi handshake | Không phải secret; phải bảo đảm tính xác thực |
| `server.key` | Private key của broker | Broker/secret manager | **Có, bảo vệ chặt** |
| `ca.pem` / truststore | CA dùng xác minh broker hoặc client | Client/broker theo vai trò | Public nhưng phải bảo vệ tính toàn vẹn |
| `client.crt` | Public certificate của ứng dụng | Client, trình trong mTLS | Không phải secret; gắn với định danh |
| `client.key` | Private key của ứng dụng | Secret mount/client key store | **Có, bảo vệ chặt** |
| `client.p12` | Có thể chứa certificate và private key | Client secret store | **Có**, cả file và password |
| `username/password` | AMQP identity | Broker auth backend và nguồn secret của client | **Có**, không đưa vào log/Git |

Đừng đánh đồng **certificate hết hạn** với **mật khẩu sai**. Đây là các lớp xác thực khác nhau, có biểu hiện lỗi và quy trình xoay vòng khác nhau.

## 7. RabbitMQ: vhost và least privilege

Trong RabbitMQ, user có quyền trên **vhost cụ thể** và ba nhóm resource permission:

- **`configure`:** tạo/đổi/xóa hoặc khai báo các resource phù hợp.
- **`write`:** publish tới exchange/resource được phép.
- **`read`:** consume từ queue/resource được phép.

Một người dùng có quyền truy cập vhost **không mặc nhiên có tất cả các quyền**. Regex được broker dùng để so khớp **tên resource**, không phải mọi logic business event. Topic exchange có thể cần thêm **topic permissions** nếu áp dụng kiểm soát routing key.

Giả sử platform **đã tạo** vhost `orders-prod`, exchange `orders.events`, queue `orders.jobs` và binding. Hai service account được cấp quyền tối thiểu:

```bash
# Minh họa lệnh quản trị, chạy bởi operator có quyền.
# User orders-api chỉ được publish vào exchange orders.events.
rabbitmqctl set_permissions -p orders-prod orders-api \
  '^$' '^orders\.events$' '^$'

# User orders-worker chỉ được consume từ queue orders.jobs.
rabbitmqctl set_permissions -p orders-prod orders-worker \
  '^$' '^$' '^orders\.jobs$'
```

**`^$`** ở đây là regex không khớp tên resource thông thường, dùng để không cấp nhóm quyền đó. Những user này **không có quyền tự tạo queue/binding**; topology do operator/IaC hoặc một principal provision riêng quản lý.

Quyền cần được thiết kế theo **các operation thực sự dùng**. Nếu ứng dụng sử dụng `RabbitAdmin` tự declare exchange/queue/binding ở startup, nó sẽ cần quyền bổ sung phù hợp; khi đó phải quyết định có đáng đánh đổi least privilege hay không. Với production, thường tách **topology provisioning** khỏi **data-plane producer/consumer**.

### 7.1. Tách quyền theo vai trò

| Danh tính | Quyền thường cần | Không nên cấp mặc định |
| --- | --- | --- |
| `orders-api` | Publish đúng exchange trong vhost riêng | Đọc mọi queue, xóa queue, administrator tag |
| `orders-worker` | Consume đúng queue, có thể publish kết quả tới exchange cụ thể nếu nghiệp vụ cần | Quyền cấu hình toàn vhost |
| `orders-topology-deployer` | Declare/change topology trong phạm vi được quản lý | Dùng làm credential cho runtime message handler |
| `monitoring` | Quyền xem metrics/management theo backend và tags cần thiết | Publish tùy ý hoặc đọc payload mọi queue |

**Không dùng `guest/guest` trong production.** RabbitMQ mặc định hạn chế user `guest` chỉ kết nối từ loopback; mở khóa kết nối remote cho tài khoản này, nhất là với mật khẩu mặc định, là thực hành không an toàn. Tạo service user riêng và lưu secret an toàn.

## 8. Các profile Spring Boot và mô hình deploy

Mục tiêu là **cùng một artifact ứng dụng** có thể chạy ở dev/staging/prod nhờ external configuration, không phải build ra các JAR chứa ba bộ secret.

Ví dụ cách chia **cấu hình không nhạy cảm**:

```yaml
# application-dev.yml
spring:
  rabbitmq:
    host: localhost
    port: 5671
    virtual-host: orders-dev
    ssl:
      enabled: true
      bundle: rabbitmq-dev-ca
```

```yaml
# application-staging.yml
spring:
  rabbitmq:
    host: rabbitmq.staging.example
    port: 5671
    virtual-host: orders-staging
    ssl:
      enabled: true
      bundle: rabbitmq-staging-ca
```

```yaml
# application-prod.yml
spring:
  rabbitmq:
    host: rabbitmq.prod.example
    port: 5671
    virtual-host: orders-prod
    ssl:
      enabled: true
      bundle: rabbitmq-prod-ca
```

Mỗi profile cần nguồn CA và credential **riêng**, được inject lúc deploy. Các bundle `rabbitmq-dev-ca`, `rabbitmq-staging-ca`, `rabbitmq-prod-ca` phải được khai báo bằng cấu hình runtime hoặc file profile phù hợp; đoạn trên là **phần cấu hình đích kết nối**, không phải bộ cấu hình chạy hoàn chỉnh.

Khi chạy:

```bash
# Ví dụ chọn profile; không truyền password qua tham số dòng lệnh.
java -jar app.jar --spring.profiles.active=staging
```

**Không cho dev/staging kết nối production bằng cách chỉ đổi profile thủ công** nếu không có kiểm soát quyền. Có thể bổ sung network policies, RBAC, workload identity, secret policy và quy trình phát hành để một service staging không bao giờ được cấp credential production.

### Những lớp bảo vệ bổ sung

- **Network:** broker chỉ mở cổng cần thiết trong mạng được kiểm soát; TLS không thay thế firewall/NetworkPolicy.
- **Secrets:** secret chỉ mount vào đúng workload; không đưa vào image layer, build args, CI artifact, Helm values public hoặc test snapshot.
- **Observability:** redact password/token/key trong log, Spring Actuator config endpoints, APM, exception handling và công cụ support.
- **Broker:** kiểm soát management UI/API, vhost, user tags và audit log tách biệt với quyền AMQP.
- **Message:** nếu payload chứa PII/financial data, áp dụng chính sách data classification và retention/DLQ phù hợp; TLS không mã hóa message “end-to-end” khi broker đã giải mã kết nối.

## 9. Xoay vòng mật khẩu: tránh cắt kết nối đồng loạt

Giả sử `orders-api` đang dùng mật khẩu cũ. Việc đổi mật khẩu trên broker rồi mới deploy ứng dụng có thể làm **kết nối mới bị từ chối**. Kết nối AMQP đã xác thực trước đó có thể còn mở và hoạt động, khiến lỗi chỉ bộc lộ khi broker restart hoặc listener reconnect.

**Không mặc định rằng sửa secret file/biến môi trường sẽ làm `CachingConnectionFactory` dùng mật khẩu mới ngay lập tức.** Tùy cách binding, bean, lifecycle và client implementation, credential có thể được đọc từ startup hoặc connection factory đã lưu giá trị. Phải có **restart/refresh/reconnect có kiểm soát**, và kiểm thử hành vi cụ thể.

### Quy trình khuyến nghị khi dùng username/password

1. **Kiểm kê phạm vi:** xác định các app, instance, connection và vhost dùng credential cũ; biết publisher/consumer nào bị ảnh hưởng.
2. **Tạo credential mới:** nếu backend không hỗ trợ hai password đồng thời cho một user, tạo **service user mới** với quyền tương đương và giới hạn phù hợp để có giai đoạn song song.
3. **Cấp secret mới:** đưa credential vào secret manager/volume của đúng môi trường; không in giá trị vào log, CI output hoặc câu lệnh chứa literal password.
4. **Triển khai canary/rolling:** cho một phần instance lấy secret mới, thiết lập TLS/authentication và kiểm tra subscribe/publish bằng quyền thực tế.
5. **Quan sát luồng:** connection errors, consumer count, outbox pending, publisher confirm/return, queue depth, DLQ, p95/p99 latency và số redelivery.
6. **Chuyển hết instance:** restart hoặc làm mới connection theo quy trình được kiểm chứng; bảo đảm old credential không còn được ứng dụng dùng.
7. **Thu hồi credential cũ:** khóa/xóa user cũ, kiểm tra và **đóng các connection cũ nếu cần thu hồi truy cập ngay**, đồng thời ghi nhận audit.
8. **Đóng thay đổi:** đối soát business event/outbox và xác minh không mất message hay tạo side effect trùng do recovery.

**Không sửa một user đang chạy đồng thời trên hàng trăm instance rồi hy vọng mọi connection tự cập nhật.** Kế hoạch có **hai danh tính trong giai đoạn chuyển tiếp** thường giảm rủi ro hơn, nhưng cần xác định quyền và thời hạn tồn tại của danh tính cũ, tránh quên thu hồi.

### 9.1. Quan hệ với độ tin cậy message

Rotation có thể làm ngắt channel đang publish hoặc consume:

- Producer mất kết nối trước publisher confirm: **không chắc message đã vào broker hay chưa**. Dùng transactional outbox, retry cùng event ID và consumer idempotent.
- Consumer đã commit DB nhưng connection mất trước `basicAck`: broker có thể redeliver message khi subscription phục hồi; cần khóa idempotency.
- Listener không có quyền đọc queue sau rotation: app “sống” nhưng nghiệp vụ đứng lại; cần readiness/alert ở mức subscriber.
- Credential mới có quyền publish thiếu exchange: kết nối login thành công nhưng publish bị từ chối; test quyền thực tế, không chỉ test TCP handshake.

Rotation chỉ thành công khi **danh tính mới hoạt động đúng với exchange/queue/binding nghiệp vụ**, không phải chỉ khi TLS connect được.

## 10. Xoay vòng chứng chỉ TLS, mTLS và CA

Thông thường có ba loại vòng đời riêng:

| Thành phần đang xoay | Ai sở hữu? | Rủi ro nếu làm sai |
| --- | --- | --- |
| Broker **server certificate** | Nhóm vận hành RabbitMQ/PKI | Client không tin server hoặc SAN không khớp |
| Client **certificate/private key** cho mTLS | Platform hoặc service team | Broker từ chối client cert; mất private key gây rủi ro chiếm danh tính |
| **CA/root/intermediate** | PKI/security team | Hàng loạt client/broker mất trust khi cert mới được ký bởi CA chưa phân phối |

### 10.1. Thứ tự thay CA an toàn

1. Phân phối **trust bundle chứa CA cũ và mới** đến các client đủ điều kiện, đúng môi trường.
2. Xác minh các client vẫn kết nối được broker hiện tại, không tắt hostname verification.
3. Thay broker certificate bằng chứng chỉ ký bởi CA mới, có SAN/eku/thời hạn phù hợp.
4. Xác minh instance mới kết nối và instance đang chạy reconnect được.
5. Sau giai đoạn quan sát, loại CA cũ khỏi truststore nếu không còn được dùng.

Với **mTLS client certificate**, chiều trust còn lại cũng cần được cập nhật: broker phải tin CA mới **trước** khi client trình certificate ký bởi CA đó. Nếu dự kiến xoay cả hai chiều, lập thứ tự cụ thể và kiểm thử trên staging.

**Không giả định chỉ cần thay file `ca.pem` hoặc `client.key` trên volume là mọi connection đang mở tự reload.** TLS handshake tạo trạng thái phiên kết nối; service có thể cần rolling restart hoặc SSL-context reload được phiên bản/framework hỗ trợ rõ ràng. Kiểm chứng bằng một **connection mới** sau thay đổi, không chỉ nhìn heartbeat trên connection cũ.

### 10.2. Theo dõi thời hạn và bảo vệ private key

- Cảnh báo trước khi certificate/CA hết hạn theo cửa sổ đủ dài cho quy trình phát hành.
- Theo dõi certificate chain, SAN, EKU, issuer và trạng thái thu hồi theo chính sách PKI.
- Hạn chế mount private key với chế độ đọc tối thiểu, tránh sao chép sang logs/artifacts hoặc chia sẻ giữa nhiều workload.
- Tập dượt mất một certificate, đổi CA và rollback trong môi trường kiểm thử.
- Xử lý **rò rỉ private key** như một sự cố an ninh: thu hồi/cấp lại, cập nhật trust/authorization và đối soát truy cập.

## 11. Chẩn đoán lỗi: mật khẩu hay chứng chỉ?

| Dấu hiệu | Tầng lỗi khả dĩ | Điều nên kiểm tra |
| --- | --- | --- |
| `SSLHandshakeException` / `PKIX path building failed` | TLS trust | CA trong truststore có ký certificate broker không, chain/intermediate có đầy đủ không? |
| `No subject alternative DNS name matching...` | TLS hostname | Hostname cấu hình và SAN của broker certificate có khớp không? |
| `certificate expired` / `unknown_ca` / `bad_certificate` | TLS certificate | Thời hạn, issuer, EKU, broker/client CA và mTLS requirement |
| `ACCESS_REFUSED - Login was refused` | AMQP authentication | Username/password, vhost, guest loopback restriction, auth backend |
| Login thành công, declare/publish/consume bị `ACCESS_REFUSED` | RabbitMQ authorization | `configure/write/read` permissions, topology owner, topic permissions |
| Connection TLS ổn nhưng `@RabbitListener` không nhận message | Subscription/topology | Queue, binding, routing key, consumer count, quyền `read` và listener startup |
| Sau rotation chỉ một số pod lỗi | Secret propagation/lifecycle | Pod nào dùng secret version nào, connection cũ hay mới, rollout status |
| Publisher confirm timeout tăng, outbox tồn đọng | Sự cố kết nối, broker hoặc publish | Không kết luận chỉ là lỗi auth; kiểm tra connection, flow control, disk, quorum |

### 11.1. Kiểm tra handshake mà không lộ secret

Trong môi trường được phép, có thể dùng OpenSSL để kiểm tra chứng chỉ broker **mà không cần truyền password**:

```bash
# Chỉ chạy ở môi trường được phép, dùng CA phù hợp.
openssl s_client \
  -connect rabbitmq.staging.example:5671 \
  -servername rabbitmq.staging.example \
  -CAfile /run/certs/rabbitmq/ca.pem \
  -verify_return_error
```

Đây là kiểm tra **TLS certificate/chain**, không phải một phép thử đầy đủ quyền publish/consume của RabbitMQ. Với TLS đúng, vẫn cần một phép thử ứng dụng thực tế bằng tài khoản có scope tối thiểu.

**Không dùng `curl -v`, debug wire logging hoặc in `ConnectionFactory`/**`Environment` một cách tùy tiện khi chúng có thể làm lộ Authorization/connection URI/secret. Khi chia sẻ log để hỗ trợ, phải redact giá trị nhạy cảm và chỉ giữ error code, host logic, vhost, certificate metadata an toàn.

## 12. Thực hành: một cấu hình, ba môi trường

Hãy dùng một service Spring Boot nhỏ có `RabbitTemplate` publish `order.created` và `@RabbitListener` đọc `orders.jobs`. Chuẩn bị ba vhost hoặc broker test tách biệt và các secret **giả lập**, không sử dụng secret production để học.

1. **Tách secret khỏi source:** loại mọi giá trị password thật khỏi `application.yml`, dùng placeholder hoặc `configtree:`. Quét repository/history/CI artifacts theo quy trình nội bộ; nếu phát hiện secret bị commit, phải **rotate** chứ không chỉ xóa dòng.
2. **Dev với CA nội bộ:** cấp broker certificate có SAN khớp hostname dev, cấu hình trust bundle; kết nối TLS và publish/consume thành công.
3. **Test sai CA:** thay CA trust bằng một CA không ký broker certificate trong môi trường test. Kỳ vọng TLS handshake bị từ chối; **không** sửa bằng cách tắt xác minh.
4. **Test sai hostname:** kết nối tới tên DNS không nằm trong SAN. Kỳ vọng hostname verification thất bại; sửa DNS/certificate.
5. **Test sai password:** dùng credential test không hợp lệ. Kỳ vọng auth bị từ chối; phân biệt rõ với `SSLHandshakeException`.
6. **Test quyền tối thiểu:** dùng tài khoản producer publish đúng exchange nhưng không được consume queue; tài khoản consumer đọc queue nhưng không được tạo/xóa queue. Kiểm tra broker audit/connection logs.
7. **Test mất secret mount:** bỏ mount hoặc thiếu file `spring.rabbitmq.password`. Kiểm tra service thất bại sớm thay vì tự fallback vào tài khoản `guest`.
8. **Test rotation có chuyển tiếp:** tạo user mới, deploy một instance dùng credential mới, publish/consume message thử, rồi chuyển các instance còn lại trước khi thu hồi user cũ.
9. **Test mTLS (nếu triển khai):** dùng certificate client hợp lệ và certificate từ CA không được broker tin. Phân biệt mTLS handshake với SASL `EXTERNAL`.
10. **Test recovery:** ngắt một connection ngay sau khi DB commit nhưng trước consumer ack. Kiểm tra redelivery, idempotency, backlog/outbox và log/metrics trong quá trình khôi phục.

**Tiêu chí đạt:** ứng dụng không chứa secret trong artifact/log; không kết nối được khi CA hoặc hostname không hợp lệ; tài khoản chỉ có đúng quyền được cấp; rotation không gây mất message hoặc xử lý nghiệp vụ trùng; staging/prod không dùng chung danh tính.

## 13. Giám sát bảo mật và độ tin cậy khi thay secret

Không nên chỉ theo dõi `rabbitmq_connection_open`. Một connection TLS thành công chưa có nghĩa mọi listener đều đã subscribe và producer đã được phân quyền publish vào exchange.

| Lớp | Chỉ báo nên theo dõi | Hành động nếu bất thường |
| --- | --- | --- |
| Secret lifecycle | Thời hạn password/token/cert, version đã deploy, số workload còn dùng version cũ | Chuẩn bị rotation, khoanh vùng rollout |
| TLS | Handshake failures, certificate validation/hostname errors, cert gần hết hạn | Kiểm tra CA, SAN, clock, TLS config |
| Authentication | Login failures theo service/vhost, attempts bất thường | Phân biệt deploy sai credential với tấn công |
| Authorization | Permission denied khi publish/consume/declare | Điều chỉnh permission **tối thiểu**, không cấp `.*` toàn vhost cho tiện |
| Publisher | Confirm ACK/NACK/unknown, returned message, outbox age | Đảm bảo event không bị mất khi kết nối bị ảnh hưởng |
| Consumer | Consumer count, redelivery, unacked, listener restarts, DLQ | Đo khả năng đọc queue và ngăn duplicate |
| Nghiệp vụ | Số event chưa hoàn tất theo SLA, idempotency hits, thiếu kết quả | Xác minh end-to-end reliability |

Không gắn **password, token, private key hoặc toàn bộ certificate PEM** làm metric label. Có thể gắn tên service, môi trường, vhost logic và **secret version không nhạy cảm** theo chính sách tổ chức, nhưng phải tránh tạo label có cardinality cao hoặc làm lộ thông tin nội bộ không cần thiết.

### Readiness khác liveness

- **Liveness:** tiến trình còn hoạt động và có thể tiếp tục vận hành hay không?
- **Readiness:** instance có đủ điều kiện tiếp nhận/sản xuất công việc theo vai trò hay không (kết nối đã xác thực, consumer đang subscribe, quyền cần thiết khả dụng)?

Nếu rotation làm listener mất quyền `read`, process có thể vẫn “live” nhưng **không ready để xử lý message**. Thiết kế health checks theo vai trò; tránh ép liveness thất bại liên tục chỉ vì một dependency tạm chập chờn, gây restart loop.

## 14. Tình huống thực tế và quyết định phù hợp

### Tình huống A: mật khẩu nằm trong Git từ nhiều tuần trước

Xóa password khỏi commit mới **không xóa nó khỏi Git history, cache, image và bản clone đã tồn tại**. Phải coi secret đã bị lộ, **rotate hoặc thu hồi**, tìm nơi từng được sử dụng, điều tra audit log, sửa pipeline để tránh tái diễn, rồi mới cân nhắc xử lý lịch sử repository theo chính sách.

### Tình huống B: certificate broker hết hạn trong đêm

Mọi instance mở connection mới sẽ có nguy cơ handshake thất bại; các connection cũ có thể vẫn đang chạy cho đến khi cần reconnect. Không tắt xác minh để “sống qua đêm”. Thay certificate hợp lệ, kiểm tra SAN/chain, kiểm thử kết nối mới và theo dõi quá trình phục hồi listener/outbox.

### Tình huống C: staging dùng chung credential production

Đây là lỗi phân tách môi trường. Tạo danh tính và vhost riêng, cấp permission tối thiểu, triển khai lại từ secret manager đúng namespace, thu hồi credential đã dùng chung và đối soát truy cập. Không dựa chỉ vào profile `staging` trong mã nguồn để ngăn một credential có quyền production.

### Tình huống D: đã bật mTLS nhưng vẫn đăng nhập sai mật khẩu

TLS handshake có thể thành công vì broker chấp nhận client certificate, trong khi RabbitMQ vẫn yêu cầu username/password theo cơ chế SASL đang cấu hình. Cần quyết định rõ: giữ **mTLS + password** hai lớp, hay bật **x.509/EXTERNAL authentication** đúng quy trình. Không nhầm “chứng chỉ đã được chấp nhận” với “đã được phép consume queue”.

### Tình huống E: xoay mật khẩu xong queue backlog tăng nhanh

Kiểm tra consumer mới có subscribe thật không, tài khoản mới có quyền `read` không, credential mount ở pod nào, và liệu `@RabbitListener` có bị retry liên tục. Khi phục hồi có thể có redelivery; idempotency và DLQ/retry cần hoạt động. Mật khẩu đã đổi thành công ở secret manager chưa phải kết thúc sự cố.

## 15. Checklist trước khi đưa lên production

| Câu hỏi kiểm tra | Tiêu chí đạt |
| --- | --- |
| Secret có trong source/JAR/image/CI output không? | **Không**; chỉ có reference đến nguồn secret |
| Mỗi môi trường có user/vhost/cert riêng không? | Có, quyền không chồng lấn không cần thiết |
| TLS có xác minh CA và hostname không? | Có, không bật trust-all hoặc `verify-hostname=false` |
| Client certificate/private key có được quản lý riêng? | Có, mount quyền hạn chế, rotation/revocation được kiểm thử |
| User runtime có quyền tối thiểu không? | Đúng `configure/write/read` theo operation; topology-admin tách riêng nếu phù hợp |
| Khi secret không có thì app làm gì? | Fail fast hoặc báo readiness không đạt; không fallback credential yếu |
| Credential/cert đổi thì connection đang chạy ra sao? | Có kế hoạch refresh/rolling restart đã thử nghiệm |
| Rotation ảnh hưởng publisher/consumer thế nào? | Theo dõi confirm, outbox, consumer count, redelivery và kết quả nghiệp vụ |
| Có cách thu hồi quyền khẩn cấp không? | Có, kể cả kết nối cũ nếu cần |
| Secret có rò trong log, metrics, message, DLQ không? | Có kiểm tra và cơ chế redact/retention |

**Nguyên tắc tổng kết:** tách **secret** khỏi **cấu hình không nhạy cảm**, tách **danh tính giữa môi trường/vai trò**, xác minh **broker bằng TLS đúng chuẩn**, và xem **rotation là một lần thay đổi hạ tầng có ảnh hưởng đến dòng message**. Bảo mật tốt và độ tin cậy giao nhận phải được kiểm chứng cùng nhau, không tách thành hai việc độc lập.

## 16. Câu hỏi tự kiểm tra

1. Vì sao `spring.rabbitmq.password=...` trong một file `application-prod.yml` được commit vào Git là rủi ro ngay cả khi repository là private?
2. Phân biệt vai trò **truststore**, **client keystore**, **server certificate** và **private key** trong kết nối TLS/mTLS.
3. Bật TLS với CA đúng nhưng không xác minh hostname có thể tạo ra rủi ro gì?
4. Vì sao mTLS với client certificate chưa tự động thay thế username/password của RabbitMQ?
5. `configure`, `write`, `read` permissions áp dụng ra sao cho một publisher chỉ gửi vào exchange và consumer chỉ đọc từ queue?
6. `configtree:/run/secrets/rabbitmq/` khác gì với đặt secret trong biến môi trường? Trong trường hợp nào import thiếu file nên làm startup thất bại?
7. Vì sao đổi password trên secret manager chưa chắc làm connection đang mở sử dụng mật khẩu mới?
8. Nếu cần xoay CA ký certificate của broker, nên cập nhật truststore client trước hay thay server certificate trước?
9. Sau rotation, publisher mất kết nối trước confirm và consumer mất kết nối trước ACK. Hai trạng thái bất định khác nhau là gì? Hệ thống cần cơ chế nào để tránh mất/lặp nghiệp vụ?
10. Một service staging kết nối production thành công nhưng không thể consume queue: có thể là lỗi authentication, authorization hay topology? Làm sao phân loại mà không log password?

## Tài liệu tham khảo

- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): `spring.rabbitmq.*` và cấu hình client RabbitMQ.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.rabbitmq.ssl.enabled`, `bundle`, `verify-hostname`, `trust-store` và các property liên quan.
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): cấu hình CA trust và client certificate/key từ PEM/JKS/PKCS12.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): placeholder, cấu hình theo môi trường và `configtree:` cho secret files.
- [RabbitMQ — TLS Support](https://www.rabbitmq.com/docs/ssl): TLS/mTLS, certificate verification, server/client certificates.
- [RabbitMQ — Authentication, Authorisation, Access Control](https://www.rabbitmq.com/docs/access-control): users, vhosts, permission regex, topic permission và quản lý quyền.
- [RabbitMQ — Credentials and Passwords](https://www.rabbitmq.com/docs/passwords): password management, authentication bằng certificate.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ảnh hưởng khi connection mất giữa publish/confirm và xử lý/ack.
