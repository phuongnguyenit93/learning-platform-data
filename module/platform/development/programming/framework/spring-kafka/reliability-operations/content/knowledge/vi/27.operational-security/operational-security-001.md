# SASL và TLS

Một ứng dụng Spring Kafka kết nối tới broker phải chứng minh **kết nối được phép**, **danh tính client hợp lệ** và **dữ liệu trên đường truyền được bảo vệ**. Hai cơ chế thường gặp là **TLS (Transport Layer Security)** và **SASL (Simple Authentication and Security Layer)**. TLS mã hóa kênh kết nối và xác minh chứng chỉ của phía server; SASL xác thực client theo cơ chế như SCRAM, PLAIN, GSSAPI/Kerberos hoặc OAUTHBEARER. Kafka ACL/authorizer là lớp riêng quyết định principal đã xác thực được phép đọc topic, ghi topic, tham gia consumer group hay sử dụng transactional ID hay không.

Trong Spring Kafka, cấu hình bảo mật thường được truyền tới producer, consumer và AdminClient qua Kafka client properties. Cấu hình phổ biến cho production là **SASL_SSL**: TLS bảo vệ kết nối, còn SASL xác thực client. Nếu dùng mutual TLS (mTLS), client cũng trình chứng chỉ của mình cho broker. TLS và SASL giải quyết các vấn đề khác nhau; bật một cơ chế không tự động thay thế cơ chế còn lại.

Bài học thuộc chương **Bảo mật vận hành** của Spring Kafka Reliability Operations. Nội dung đi từ mô hình bảo mật, cấu hình Spring Boot, truststore/keystore, SCRAM, ACL, secret và certificate rotation tới runbook điều tra lỗi kết nối production.

## 1. Phân biệt TLS, SASL và Kafka ACL

Ba lớp thường xuất hiện cùng nhau:

| Lớp | Câu hỏi được trả lời | Cơ chế |
|---|---|---|
| **TLS** | Kết nối có được mã hóa và server có đúng danh tính không? | Chứng chỉ X.509, CA trust, hostname verification, TLS handshake. |
| **SASL** | Client là ai? | SCRAM, PLAIN, GSSAPI/Kerberos, OAUTHBEARER hoặc cơ chế broker hỗ trợ. |
| **Authorization** | Principal này được phép làm gì? | Kafka authorizer và ACL/resource policy. |

Một luồng SASL_SSL:

~~~text
Spring Kafka application
        |
        | 1. TLS handshake
        |    - xác minh broker certificate
        |    - thiết lập kênh mã hóa
        v
     Kafka broker
        |
        | 2. SASL authentication
        |    - SCRAM / PLAIN / OAuth / Kerberos
        |    - xác định principal
        v
     Authenticated principal
        |
        | 3. Authorization
        |    - topic READ / WRITE
        |    - group READ
        |    - transactional ID permissions
        v
     Kafka operation được cho phép
~~~

Một client có thể TLS handshake thành công và SASL xác thực thành công, nhưng khi đọc topic vẫn nhận `TopicAuthorizationException`. Khi đó cần sửa ACL, không phải thay truststore hoặc đổi mật khẩu.

**TLS không tự xác thực quyền nghiệp vụ của client**, SASL không tự mã hóa dữ liệu khi dùng `SASL_PLAINTEXT`, và ACL không thay thế TLS/SASL để bảo vệ đường truyền.

## 2. Các giá trị security.protocol

Kafka client dùng thuộc tính `security.protocol` để chọn loại kết nối:

| Giá trị | TLS encryption | SASL authentication | Cách sử dụng |
|---|---:|---:|---|
| `PLAINTEXT` | Không | Không | Chỉ phù hợp mạng/lab được bảo vệ theo mô hình riêng; tránh dùng cho traffic production nhạy cảm. |
| `SSL` | Có | Không | TLS server authentication, có thể bật client certificate/mTLS. |
| `SASL_PLAINTEXT` | Không | Có | Có SASL nhưng thông tin truyền qua network không được TLS bảo vệ. |
| `SASL_SSL` | Có | Có | Phổ biến cho production khi cần cả mã hóa và SASL authentication. |

Nếu dùng `SASL_PLAINTEXT`, username/password hoặc thông tin xác thực SASL có thể bị lộ trên đường truyền nếu mạng không có lớp bảo vệ tương đương. Không chọn nó chỉ để cấu hình đơn giản hơn khi client và broker giao tiếp qua mạng không đáng tin cậy.

Với TLS-only, `security.protocol=SSL` vẫn có thể xác thực client bằng chứng chỉ nếu broker yêu cầu client authentication. Đó là **mTLS**; không cần SASL nếu hệ thống chủ động dùng certificate identity làm principal.

## 3. Chọn cơ chế SASL

Kafka hỗ trợ nhiều SASL mechanism; broker và client phải thống nhất mechanism được bật và cấu hình:

| Mechanism | Mô tả | Lưu ý vận hành |
|---|---|---|
| `PLAIN` | Username/password theo SASL PLAIN. | Chỉ dùng qua TLS trong mạng production; quản lý password như secret. |
| `SCRAM-SHA-256` | Challenge-response dựa trên salted password và SHA-256. | Phải cấu hình credential phía broker; phù hợp xác thực username/password. |
| `SCRAM-SHA-512` | SCRAM với SHA-512. | Thường được chọn khi broker/client hỗ trợ; vẫn cần credential lifecycle và TLS. |
| `GSSAPI` | Kerberos authentication. | Cần principal, keytab, ticket và cấu hình realm/KDC. |
| `OAUTHBEARER` | Xác thực dựa trên OAuth bearer token. | Cần token acquisition/refresh, issuer, audience, TLS và callback/config tương ứng. |

Không phải mọi Kafka cluster hoặc managed Kafka service đều bật tất cả mechanism. Xác nhận **broker listener**, Kafka version, managed service policy và client library hỗ trợ cơ chế được chọn.

### PLAIN và SCRAM khác nhau thế nào?

PLAIN gửi credential trong SASL exchange; TLS là lớp bảo vệ đường truyền quan trọng để credential không bị quan sát trên mạng. SCRAM dùng challenge-response và không gửi password nguyên văn như PLAIN, nhưng **SCRAM không thay thế TLS**: TLS vẫn bảo vệ traffic, metadata, payload và giảm nguy cơ MITM.

SCRAM credential phải được tạo/cấp ở broker hoặc control plane của managed service. Chỉ thêm username/password vào Spring Boot client không tự tạo principal trên Kafka cluster.

## 4. TLS server authentication: truststore

Khi client kết nối TLS tới broker, nó cần xác minh certificate chain của broker. **Truststore** chứa CA certificate hoặc certificate chain mà client tin cậy.

~~~text
Kafka broker certificate
       |
       v
Intermediate CA
       |
       v
Root CA
       |
       v
Client truststore
  - root CA / trusted chain
       |
       v
TLS server certificate validation
~~~

Client phải xác minh:
- Certificate còn hiệu lực (NotBefore, NotAfter).
- Certificate chain dẫn tới CA được tin cậy.
- Hostname client kết nối khớp với Subject Alternative Name (SAN) của certificate.
- TLS protocol/cipher phù hợp với policy.
- Certificate chưa bị thu hồi nếu hệ thống có kiểm tra revocation phù hợp.

**Không tắt hostname verification để chữa lỗi certificate.** Thuộc tính Kafka client `ssl.endpoint.identification.algorithm` thường mặc định dùng `https` để xác minh hostname. Đặt giá trị rỗng có thể bỏ xác minh hostname và mở ra nguy cơ man-in-the-middle. Hãy cấp lại certificate với SAN chứa hostname mà client thực sự sử dụng.

## 5. mTLS: client keystore và broker trust

Với mutual TLS, broker cũng xác minh client certificate. Khi đó cần hai hướng trust:

~~~text
Client:
  truststore -> tin CA cấp broker certificate
  keystore   -> giữ client certificate + private key

Broker:
  truststore -> tin CA cấp client certificate
  keystore   -> giữ broker certificate + private key
~~~

Phân biệt:
- **Truststore** chứa certificate dùng để xác minh peer.
- **Keystore** chứa certificate và private key của chính endpoint.
- Password của keystore và password bảo vệ private key có thể khác nhau.
- Một truststore có thể chứa nhiều CA để hỗ trợ giai đoạn rotation.
- Client certificate identity có thể được broker ánh xạ thành principal theo cấu hình Kafka.

Nếu cluster chỉ dùng TLS server authentication, client thường chỉ cần truststore; không cần keystore client. Nếu broker yêu cầu client certificate, client phải được cấp certificate phù hợp và cấu hình keystore.

## 6. Cấu hình Spring Boot với SASL_SSL và SCRAM

Ví dụ cấu hình producer, consumer và admin dùng chung security properties:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093,kafka-2.example.net:9093

    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-app" password="INJECTED_SECRET";'
      "[ssl.truststore.location]": /etc/kafka/tls/truststore.p12
      "[ssl.truststore.password]": "INJECTED_TRUSTSTORE_PASSWORD"
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https

    consumer:
      group-id: orders-service-v1
      enable-auto-commit: false

    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
~~~

`INJECTED_SECRET` và `INJECTED_TRUSTSTORE_PASSWORD` là placeholder; phải được thay bằng giá trị lấy từ secret manager hoặc cơ chế inject secret của deployment. Không commit password thật vào Git, Docker image hoặc log.

Spring Boot map `spring.kafka.properties` vào Kafka client properties dùng chung. Nếu producer, consumer và AdminClient cần security settings khác nhau, cấu hình `spring.kafka.producer.properties`, `spring.kafka.consumer.properties` và `spring.kafka.admin.properties` theo phiên bản Boot đang sử dụng. Tránh cấu hình hai giá trị khác nhau cho cùng một key ở nhiều cấp mà không hiểu quy tắc merge/override.

Phần quan trọng là Kafka property cuối cùng mà client nhận. Khi điều tra, inspect cấu hình đã được resolved theo cách không làm lộ credential.

## 7. JAAS config cho SCRAM

Với SCRAM, Kafka client thường dùng JAAS login module:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="orders-app"
    password="SECRET_FROM_SECRET_MANAGER";
~~~

Cấu hình có thể được truyền qua `sasl.jaas.config` trong Kafka client properties. Đây là chuỗi JAAS nên cần cẩn thận với dấu nháy, dấu chấm phẩy và escaping khi đặt trong YAML, environment variable hoặc Helm chart.

Ví dụ cấu hình Java từ secret được inject:

~~~java
Map<String, Object> props = new HashMap<>();
props.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "SASL_SSL");
props.put(SaslConfigs.SASL_MECHANISM, "SCRAM-SHA-512");

String username = credentials.username();
String password = credentials.password();

String jaas = "org.apache.kafka.common.security.scram.ScramLoginModule required "
        + "username=\"" + escapeJaas(username) + "\" "
        + "password=\"" + escapeJaas(password) + "\";";

props.put(SaslConfigs.SASL_JAAS_CONFIG, jaas);
~~~

Đây là code minh họa; `credentials` phải đến từ secret provider an toàn và hàm `escapeJaas` phải xử lý đúng ký tự đặc biệt theo grammar JAAS. Nếu username/password chứa dấu nháy hoặc backslash, nối chuỗi trực tiếp mà không escape có thể tạo cấu hình sai hoặc mở đường injection cấu hình.

Không log biến `jaas`, vì chuỗi này chứa password. Cũng không đưa nguyên giá trị vào exception message, tracing attribute hoặc actuator endpoint.

## 8. Cấu hình truststore và keystore trong Spring Boot

TLS server authentication:

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.location]": /etc/kafka/tls/broker-truststore.p12
      "[ssl.truststore.password]": "INJECTED_TRUSTSTORE_PASSWORD"
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
~~~

TLS mutual authentication:

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL

      "[ssl.truststore.location]": /etc/kafka/tls/broker-truststore.p12
      "[ssl.truststore.password]": "INJECTED_TRUSTSTORE_PASSWORD"
      "[ssl.truststore.type]": PKCS12

      "[ssl.keystore.location]": /etc/kafka/tls/client-keystore.p12
      "[ssl.keystore.password]": "INJECTED_KEYSTORE_PASSWORD"
      "[ssl.keystore.type]": PKCS12
      "[ssl.key.password]": "INJECTED_PRIVATE_KEY_PASSWORD"

      "[ssl.endpoint.identification.algorithm]": https
~~~

Các file path phải tồn tại và đọc được bên trong **container/runtime thực tế**. Đường dẫn tồn tại trên máy developer không có nghĩa nó tồn tại trong pod. Kiểm tra volume mount, file permission, owner, format PKCS12/JKS và password.

Một số keystore dùng cùng password cho store và private key; một số khác dùng riêng. Đặt `ssl.key.password` nếu private key cần password riêng. Không giả định truststore password luôn bắt buộc để đọc mọi loại truststore; cấu hình theo store format và policy của hệ thống.

## 9. Kết hợp SASL với mTLS

Một client có thể sử dụng cả SASL authentication và TLS client certificate:

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-app" password="INJECTED_SECRET";'

      "[ssl.truststore.location]": /etc/kafka/tls/broker-truststore.p12
      "[ssl.truststore.password]": "INJECTED_TRUSTSTORE_PASSWORD"
      "[ssl.truststore.type]": PKCS12

      "[ssl.keystore.location]": /etc/kafka/tls/client-keystore.p12
      "[ssl.keystore.password]": "INJECTED_KEYSTORE_PASSWORD"
      "[ssl.keystore.type]": PKCS12
      "[ssl.key.password]": "INJECTED_PRIVATE_KEY_PASSWORD"
~~~

Trong mô hình này:
- TLS xác minh broker và mã hóa kênh.
- Client certificate có thể được broker yêu cầu và xác minh.
- SASL xác thực principal theo SCRAM.
- Authorizer/ACL quyết định quyền thực hiện Kafka operation.

Cần xác nhận broker listener được cấu hình hỗ trợ cả TLS client authentication và SASL mechanism. Không phải mọi managed Kafka service cho phép tùy ý kết hợp mTLS với SASL; làm theo contract của provider.

## 10. Cấu hình security riêng cho producer, consumer và admin

Nhiều ứng dụng dùng chung một cluster và cùng credential cho producer/consumer/admin. Tuy nhiên, một số hệ thống cần principal hoặc broker endpoint khác nhau theo chức năng.

Spring Boot hỗ trợ cấu hình client-specific properties theo các namespace tương ứng, tùy phiên bản:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.example.net:9093

    consumer:
      group-id: orders-reader-v1
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="READER_SECRET";'

    producer:
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-writer" password="WRITER_SECRET";'

    admin:
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-admin" password="ADMIN_SECRET";'
~~~

Đây là ví dụ về phân tách principal, không phải khuyến nghị cấp quyền admin rộng cho application. Thường runtime service **không cần** quyền quản trị cluster; schema/topic provisioning có thể do deployment pipeline hoặc platform team đảm nhiệm bằng principal riêng.

Khi cấu hình nhiều client factory bằng Java, cần chắc chắn producer, consumer và AdminClient đều nhận security properties phù hợp. Một listener có thể chạy được nhưng producer send fail nếu hai factory dùng principal khác nhau hoặc truststore khác nhau.

## 11. SASL authentication không phải Kafka authorization

Sau khi SASL xác thực thành công, broker có principal. Authorizer quyết định principal có quyền trên resource hay không.

Ví dụ quyền theo workload:

| Principal | Resource | Quyền thường cần |
|---|---|---|
| `User:orders-writer` | Topic `orders.created` | WRITE; có thể cần DESCRIBE theo operation/client. |
| `User:orders-reader` | Topic `orders.created` | READ và DESCRIBE theo cấu hình/operation. |
| `User:orders-reader` | Group `orders-reader-v1` | READ để tham gia group và commit offset. |
| `User:orders-writer` | Transactional ID prefix | Quyền phù hợp để sử dụng transaction nếu producer transactional. |
| Deployment/admin principal | Topic/group/cluster | Chỉ cấp quyền quản trị thực sự cần. |

ACL chính xác phụ thuộc Kafka version, operation, resource pattern, transactional/idempotent producer và authorizer policy. Đừng copy một danh sách ACL rộng cho mọi service. Dùng **least privilege** và kiểm tra các operation mà ứng dụng thực sự thực hiện.

Các lỗi có thể phân loại:
- `SaslAuthenticationException`: credential, mechanism, JAAS hoặc auth backend.
- `TopicAuthorizationException`: principal đã xác thực nhưng thiếu quyền topic.
- `GroupAuthorizationException`: thiếu quyền consumer group.
- `TransactionalIdAuthorizationException`: thiếu quyền trên transactional ID.
- `ClusterAuthorizationException`: thiếu quyền cluster-level cho operation tương ứng.

Nếu SASL auth thành công nhưng `poll()` hoặc `send()` bị authorization error, thay password thường không giúp. Xác định **principal hiệu lực** và resource/operation bị từ chối.

## 12. SCRAM credential lifecycle

Với SCRAM, credential được quản lý ở Kafka broker/control plane. Một quy trình production cần:
- Principal riêng cho từng service hoặc workload.
- Không dùng chung user admin cho tất cả producer/consumer.
- Mật khẩu đủ mạnh, lưu trong secret manager.
- Quy trình cấp mới, rotate và revoke có kiểm soát.
- Theo dõi authentication failures sau rotation.
- Có thể dùng hai principal trong giai đoạn chuyển đổi nếu nền tảng hỗ trợ.

Một cách rotation an toàn thường là tạo credential/principal mới, cấp ACL tối thiểu tương ứng, deploy secret mới cho một canary instance, xác minh produce/consume, rồi rollout các instance còn lại và cuối cùng thu hồi credential cũ. Nếu đổi password ngay trên cùng principal mà không có giai đoạn overlap, các pod chưa được cập nhật có thể mất kết nối khi credential cũ không còn hợp lệ.

Không để password cũ và mới đồng thời tồn tại vô thời hạn. Ghi rõ thời điểm revoke, owner, ứng dụng phụ thuộc và cách rollback.

## 13. Certificate lifecycle và rotation

Certificate có ngày hết hạn; rotation cần có kế hoạch trước khi broker/client certificate hết hạn.

### Rotate CA của broker

Một quy trình chuyển CA có overlap:

~~~text
Giai đoạn 1:
  Client truststore tin CA cũ

Giai đoạn 2:
  Cập nhật client truststore để tin CA cũ + CA mới
  Rollout client và xác nhận TLS vẫn hoạt động

Giai đoạn 3:
  Broker chuyển sang certificate do CA mới cấp

Giai đoạn 4:
  Xác nhận mọi client đã kết nối bằng certificate mới

Giai đoạn 5:
  Gỡ CA cũ khỏi truststore sau khi không còn broker dùng certificate cũ
~~~

### Rotate client certificate trong mTLS

1. Cấp client certificate mới có SAN/subject và identity mapping phù hợp.
2. Đảm bảo broker truststore tin CA cấp certificate mới.
3. Cập nhật secret/keystore trong canary instance.
4. Khởi tạo lại hoặc refresh Kafka client theo cơ chế hỗ trợ của ứng dụng.
5. Xác minh TLS handshake, principal và ACL.
6. Rollout phần còn lại.
7. Thu hồi certificate cũ theo chính sách PKI.

Kafka client không nhất thiết tự reload truststore/keystore khi file mount thay đổi. Thực tế thường cần tạo lại client/producer/consumer hoặc rolling restart theo cách framework và version hỗ trợ. Không giả định cập nhật Kubernetes Secret volume là mọi kết nối đang mở lập tức dùng certificate mới.

## 14. Quản lý secret trong Kubernetes và deployment

Không hard-code SASL password, truststore password hoặc private key password trong:
- Git repository.
- `application.yml` được commit.
- Dockerfile hoặc image layer.
- Helm values công khai.
- Log, exception message hoặc actuator environment endpoint không được bảo vệ.

Một deployment có thể mount secret dưới dạng file:

~~~yaml
volumes:
  - name: kafka-security
    secret:
      secretName: orders-kafka-security

containers:
  - name: orders-service
    volumeMounts:
      - name: kafka-security
        mountPath: /etc/kafka/tls
        readOnly: true
~~~

Tên secret và file keys cần khớp với manifest/secret manager thực tế. Chỉ service account được cấp quyền đọc secret tương ứng. File permission nên giới hạn user chạy ứng dụng; private key không được world-readable.

Với password environment variable, cần hiểu cách secret được inject và cách ứng dụng resolve config. Tránh in toàn bộ environment hoặc `Environment` object vào log. Nếu dùng external secret provider, cần theo dõi secret refresh và vòng đời client đang giữ credential cũ.

## 15. Broker listener và advertised.listeners

Client chỉ có thể kết nối đúng khi broker listener và địa chỉ quảng bá phù hợp với môi trường client.

Ví dụ client bootstrap vào `kafka-bootstrap.example.net:9093`, nhưng broker metadata có thể trả về hostname riêng của từng broker. Tất cả địa chỉ được quảng bá phải:
- Resolve được từ network của ứng dụng.
- Có route/firewall phù hợp.
- Dùng port/listener đúng security protocol.
- Có hostname khớp SAN của broker certificate.
- Dùng cùng cơ chế authentication mà client cấu hình.

Một lỗi thường gặp là bootstrap hostname có certificate hợp lệ nhưng hostname trong `advertised.listeners` của một broker không nằm trong SAN. TLS handshake ban đầu thành công, sau đó client kết nối broker cụ thể lại thất bại.

Không chỉ kiểm tra bootstrap address. Kiểm tra toàn bộ broker endpoints mà client nhận từ metadata, đặc biệt khi dùng Kubernetes, private DNS, load balancer hoặc multi-region network.

## 16. TLS protocol, cipher và hostname verification

Kafka client có các thuộc tính TLS như:
- `ssl.protocol`
- `ssl.enabled.protocols`
- `ssl.cipher.suites`
- `ssl.endpoint.identification.algorithm`
- `ssl.truststore.location`, `ssl.truststore.type`, `ssl.truststore.password`
- `ssl.keystore.location`, `ssl.keystore.type`, `ssl.keystore.password`, `ssl.key.password`

Chỉ bật protocol/cipher được tổ chức và broker hỗ trợ. Không hạ xuống TLS version yếu để “làm kết nối chạy được” nếu chưa có đánh giá bảo mật. Hostname verification cần được giữ bật trừ khi có thiết kế bảo vệ tương đương được phê duyệt.

Khi gặp `SSLHandshakeException`, cần kiểm tra:
1. Client đang kết nối hostname nào?
2. Broker certificate có SAN khớp hostname không?
3. Chain có đầy đủ intermediate CA không?
4. Truststore có đúng CA và đúng file path không?
5. Certificate đã hết hạn/chưa có hiệu lực chưa?
6. TLS protocol/cipher có tương thích không?
7. Có proxy/load balancer thay certificate không?

Không giải quyết bằng cách tắt `ssl.endpoint.identification.algorithm`; điều đó che lỗi identity và làm giảm khả năng chống MITM.

## 17. Bảo vệ principal và least privilege

Một service chỉ cần publish `orders.created` không nên có quyền đọc mọi topic, tạo topic, xóa topic hoặc thay đổi ACL cluster-wide.

Thiết kế principal:
- Một principal cho mỗi workload hoặc trust boundary.
- Tách runtime producer và consumer nếu có lý do bảo mật và khả năng vận hành.
- Cấp quyền trên đúng topic và group pattern.
- Với transactional producer, cấp quyền cho transactional ID prefix theo policy.
- Tách principal của CI/CD/admin khỏi runtime application.
- Định kỳ rà soát principal không còn sử dụng và ACL quá rộng.

Khi dùng mTLS, cần hiểu broker ánh xạ certificate DN/subject thành principal như thế nào. Certificate có cùng CA không đồng nghĩa tất cả certificate có cùng quyền; principal mapping và ACL quyết định quyền thực tế.

Không đặt tên principal dựa trên user cuối cùng hoặc truyền credential của từng end user vào Kafka client nếu kiến trúc không yêu cầu. Thông thường ứng dụng dùng workload identity, còn authorization nghiệp vụ được thực hiện ở tầng service.

## 18. Phân loại lỗi kết nối bảo mật

| Triệu chứng/log | Lớp có thể lỗi | Kiểm tra đầu tiên |
|---|---|---|
| `SSLHandshakeException` | TLS handshake/certificate/protocol | Trust chain, SAN/hostname, expiry, TLS/cipher, keystore. |
| `SaslAuthenticationException` | SASL authentication | Username/password, JAAS, mechanism, broker listener. |
| `UnsupportedSaslMechanismException` | SASL mechanism mismatch | Broker enabled mechanisms và client `sasl.mechanism`. |
| `TopicAuthorizationException` | ACL topic | Principal hiệu lực, topic và operation READ/WRITE/DESCRIBE. |
| `GroupAuthorizationException` | ACL group | Group ID và quyền READ tương ứng. |
| `TransactionalIdAuthorizationException` | ACL transactional ID | Transactional ID/prefix và quyền của principal. |
| `ConfigException` liên quan SSL/SASL | Client configuration | Property name, type, JAAS syntax, store path/password. |
| `UnknownHostException` / connect timeout | DNS/network/listener | Bootstrap và advertised broker endpoints, firewall, route. |
| Authentication success nhưng send fail | Authorization hoặc producer config | Topic ACL, transactional ACL, idempotence/acks. |
| Chỉ một broker lỗi TLS | Certificate/listener không đồng nhất | Broker hostname, certificate SAN/chain và advertised.listeners. |

Đừng gộp tất cả thành “Kafka auth lỗi”. Xác định lỗi xảy ra trước TLS, trong SASL exchange hay sau khi principal đã được xác thực.

## 19. Kiểm tra certificate và truststore

Có thể dùng OpenSSL từ môi trường được phép để xem certificate endpoint:

~~~bash
openssl s_client \
  -connect kafka-1.example.net:9093 \
  -servername kafka-1.example.net \
  -showcerts
~~~

Lệnh này giúp xem certificate chain và kết quả TLS handshake từ máy đang chạy lệnh. Nó không chứng minh SASL authentication hoặc Kafka ACL hoạt động.

Có thể kiểm tra thông tin certificate:

~~~bash
openssl x509 -in broker.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

Với PKCS12/JKS, dùng `keytool` phù hợp:
- Liệt kê alias và certificate chain.
- Xác nhận certificate CA đúng.
- Xác nhận client keystore có private key entry nếu dùng mTLS.
- Xác nhận expiry và subject/SAN.
- Không xuất private key ra nơi không được bảo vệ.

Không gửi file private key, truststore có secret hoặc password lên ticket/chat/log không bảo mật để nhờ kiểm tra.

## 20. Kiểm thử end-to-end security

Một smoke test cần xác nhận cả ba lớp:

**TLS**
- Client kết nối đúng broker listener.
- Certificate chain hợp lệ.
- Hostname verification thành công.
- Nếu mTLS, broker chấp nhận client certificate.

**SASL**
- Client xác thực bằng principal mong muốn.
- Mechanism client và broker thống nhất.
- Credential lấy từ secret đúng version.

**Authorization**
- Producer gửi được topic được cấp quyền.
- Consumer đọc được topic và group được cấp quyền.
- Nếu dùng transaction, producer commit được transaction ID.
- Operation bị cấm vẫn bị từ chối (negative test) để xác nhận least privilege.

Ví dụ smoke test theo nghiệp vụ:
1. Dùng principal của service gửi một record test vào topic được cho phép.
2. Dùng consumer group test được cấp quyền đọc topic đó.
3. Xác nhận record nhận được và offset tiến.
4. Thử truy cập một topic không được cấp quyền; mong đợi authorization failure.
5. Nếu dùng transactional producer, thử transaction begin/send/commit.
6. Ghi lại principal, broker endpoint, topic/group và kết quả mà không log credential.

Chỉ kiểm tra `openssl s_client` là chưa đủ; nó chỉ xác nhận một phần TLS, không kiểm tra SASL, ACL, producer send hoặc consumer poll.

## 21. Runbook: SASL authentication thất bại

Giả sử service liên tục báo `SaslAuthenticationException` sau khi deploy.

**Bước 1 — Xác nhận endpoint.** Kiểm tra bootstrap server, port và listener được dùng có yêu cầu đúng security protocol không.

**Bước 2 — Kiểm tra mechanism.** Client `sasl.mechanism` có nằm trong danh sách broker listener bật không? SCRAM-SHA-256 và SCRAM-SHA-512 không thể hoán đổi tùy ý.

**Bước 3 — Kiểm tra JAAS.** Login module có đúng mechanism không? Username/password có được resolve từ secret mới nhất không? Dấu nháy, dấu chấm phẩy và escaping có hợp lệ không?

**Bước 4 — Kiểm tra credential lifecycle.** Secret có bị rotate/revoke giữa rollout? Pod cũ còn dùng password cũ? Principal có bị disable không?

**Bước 5 — Kiểm tra TLS trước SASL.** Nếu TLS handshake thất bại, SASL exchange chưa thể hoàn tất; đọc lỗi gốc thay vì chỉ nhìn wrapper exception.

**Bước 6 — Kiểm tra broker logs/control plane.** Xác định principal hoặc mechanism bị từ chối theo thông tin an toàn mà broker cung cấp.

**Bước 7 — Canary credential.** Kiểm tra bằng một instance hoặc client test dùng cùng endpoint và secret version, không phát tán thay đổi tới mọi pod trước khi xác nhận.

**Bước 8 — Xác nhận.** Producer/consumer tạo kết nối mới, xác thực thành công và thực hiện đúng operation được cấp quyền.

Không in JAAS string, password hoặc token vào log để tìm nguyên nhân. Hãy ghi secret version/rotation ID, không ghi secret value.

## 22. Runbook: TLS handshake thất bại

Triệu chứng: `SSLHandshakeException`, `PKIX path building failed`, `No subject alternative DNS name matching` hoặc lỗi protocol/cipher.

1. Xác nhận hostname broker mà client thực sự kết nối, bao gồm các địa chỉ từ advertised metadata.
2. Kiểm tra certificate SAN, issuer, validity period và chain.
3. Xác nhận truststore trong container đúng file, format và secret version.
4. Với mTLS, kiểm tra keystore có private key và client certificate chain phù hợp.
5. Kiểm tra file mount permission và password store/key.
6. Xác nhận TLS protocol/cipher được broker/client hỗ trợ.
7. Nếu vừa rotate CA, xác minh truststore có cả CA cũ/mới trong giai đoạn overlap.
8. Sửa certificate hoặc trust chain; giữ hostname verification bật.
9. Tạo lại Kafka clients/rolling restart theo quy trình cần thiết để load material mới.
10. Xác nhận tất cả broker endpoints trong metadata đều TLS handshake thành công.

Không tắt hostname verification để workaround lỗi SAN. Cần sửa certificate hoặc advertised hostname.

## 23. Runbook: SASL thành công nhưng bị authorization denied

Giả sử log có `TopicAuthorizationException` khi producer gửi.

1. Xác định principal broker đã authenticate thành công.
2. Xác nhận topic name và cluster đang truy cập.
3. Xác định operation bị từ chối: WRITE, READ, DESCRIBE, group access hay transaction.
4. Kiểm tra ACL/resource pattern của đúng principal.
5. Nếu consumer, kiểm tra quyền topic và group ID thực tế, không chỉ group ID dự kiến trong YAML.
6. Nếu transactional producer, kiểm tra transactional ID/prefix permissions.
7. Cấp đúng quyền tối thiểu theo quy trình quản trị.
8. Khởi tạo lại thao tác và xác nhận operation được cho phép; negative test trên resource không được cấp quyền vẫn phải bị từ chối.

Không cấp quyền superuser hoặc wildcard toàn cluster để giải quyết một lỗi thiếu ACL trên một topic.

## 24. Rotation không gây outage

Một quy trình rotation nên có owner, lịch, canary và điều kiện hoàn tất:

~~~text
Chuẩn bị credential/certificate mới
             |
             v
Cập nhật trust/ACL để chấp nhận identity mới
             |
             v
Mount secret/material mới ở canary
             |
             v
Tạo Kafka client connection mới
             |
             v
Kiểm tra TLS + SASL + ACL + produce/consume
             |
       Thành công?
        /      \
      Không     Có
       |         |
       v         v
Rollback     Rollout các pod
hoặc sửa         |
                 v
        Xác nhận không còn client cũ
                 |
                 v
        Thu hồi credential/certificate cũ
~~~

Đối với CA rotation, truststore thường phải tin cả CA cũ và mới trước khi broker chuyển certificate. Đối với SCRAM rotation, có thể cần principal mới để tạo overlap; đổi password ngay trên cùng username có thể làm pod cũ thất bại. Với mTLS, broker phải tin CA của certificate mới trước khi client rollout.

Không thu hồi credential/certificate cũ ngay khi canary thành công; đợi rollout hoàn tất, xác nhận mọi instance đã dùng identity mới và có thể rollback trong cửa sổ đã định.

## 25. Observability cho security operations

Theo dõi những tín hiệu sau:
- Số lần TLS handshake failure theo broker endpoint.
- SASL authentication failures theo service/principal đã được sanitize.
- Authorization denied theo resource/operation.
- Certificate expiry sắp tới và thời gian còn lại.
- Secret/certificate version đang dùng ở mỗi pod.
- Kafka connection/reconnect rate.
- Producer send failures và consumer poll/lag sau rotation.
- Transaction commit/abort nếu transactional producer dùng principal mới.
- Thời gian từ rollout tới khi toàn bộ pod xác nhận security material mới.

Không đưa password, token, private key hoặc toàn bộ JAAS string vào logs/traces/metrics. Có thể ghi principal name hoặc credential version nếu policy cho phép; không log dữ liệu xác thực.

Các metric names là do platform hoặc ứng dụng instrument, không mặc định có cùng tên ở mọi Kafka exporter/managed service. Alert nên phân biệt **authentication failure** với **authorization failure** và **TLS handshake failure** để route đúng đội phụ trách.

## 26. Những lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `SASL_PLAINTEXT` trên mạng không đáng tin | SASL credentials không được TLS bảo vệ. | Chuyển sang `SASL_SSL` nếu cluster hỗ trợ. |
| Client dùng mechanism khác broker | SASL auth fail hoặc unsupported mechanism. | Thống nhất mechanism và broker listener config. |
| Truststore thiếu intermediate CA | PKIX path validation thất bại. | Cài đầy đủ CA chain tin cậy. |
| Broker certificate SAN không khớp advertised hostname | TLS hostname verification fail. | Sửa SAN hoặc advertised listener hostname. |
| Tắt hostname verification để chạy được | Mất bảo vệ identity chống MITM. | Giữ verification và sửa certificate. |
| Mỗi pod có secret version khác nhau | Một số replica kết nối, một số thất bại. | Canary/rollout và quan sát secret version. |
| Password nằm trong Git/log | Lộ credential và cần rotation khẩn cấp. | Thu hồi, rotate, dùng secret manager, kiểm tra log retention. |
| Principal xác thực được nhưng không có ACL | Topic/group/transaction operation bị từ chối. | Cấp quyền tối thiểu đúng resource. |
| Chỉ test TLS bằng OpenSSL | Không kiểm tra SASL hoặc Kafka ACL. | Thực hiện Kafka produce/consume smoke test. |
| Secret file được cập nhật nhưng client vẫn lỗi | Kafka client vẫn giữ SSL context/credential cũ. | Tạo lại client hoặc rolling restart theo lifecycle. |

## 27. Checklist trước production

- [ ] Chọn đúng `security.protocol` (`SASL_SSL` hoặc `SSL` theo mô hình đã phê duyệt).
- [ ] Broker listener bật SASL mechanism tương ứng.
- [ ] TLS certificate chain hợp lệ và hostname verification vẫn bật.
- [ ] Truststore/keystore có đúng file path, format, password và permission trong runtime.
- [ ] mTLS được cấu hình đầy đủ nếu broker yêu cầu client certificate.
- [ ] SASL JAAS config lấy credential từ secret manager, không commit/log secret.
- [ ] Principal riêng theo workload; không dùng admin credential trong runtime nếu không cần.
- [ ] ACL cấp đúng topic, group và transactional ID resource.
- [ ] Producer, consumer và AdminClient đều nhận security properties phù hợp.
- [ ] Bootstrap và toàn bộ advertised broker endpoints đều DNS/network/TLS reachable.
- [ ] Có quy trình rotate credential/certificate với overlap, canary và rollback.
- [ ] Biết Kafka client có cần recreate/restart để load secret/certificate mới hay không.
- [ ] Có smoke test TLS + SASL + authorization + produce/consume.
- [ ] Có alert riêng cho TLS, authentication và authorization failure.
- [ ] Không log password, token, private key hoặc JAAS string.
- [ ] Có runbook phân loại lỗi và người chịu trách nhiệm cho broker, PKI, identity và application.

## 28. Kết luận

**TLS và SASL bảo vệ hai lớp khác nhau của kết nối Kafka.** TLS mã hóa đường truyền và xác minh certificate identity; SASL xác thực client theo cơ chế broker hỗ trợ; Kafka ACL quyết định principal có được phép thực hiện operation cụ thể hay không. Trong nhiều môi trường production, `SASL_SSL` là lựa chọn phổ biến, kết hợp truststore để xác minh broker và có thể thêm keystore nếu cần mTLS.

Vận hành an toàn đòi hỏi quản lý credential/certificate như tài sản có vòng đời: lưu trong secret manager, cấp quyền least privilege, rotate theo giai đoạn có overlap, xác nhận mọi broker endpoint và kiểm thử đủ TLS, SASL lẫn ACL. Khi phân loại sự cố theo đúng lớp, đội vận hành có thể sửa trust chain, credential, mechanism hoặc ACL chính xác mà không vô tình tắt hostname verification hay cấp quyền rộng chỉ để làm kết nối chạy lại.
