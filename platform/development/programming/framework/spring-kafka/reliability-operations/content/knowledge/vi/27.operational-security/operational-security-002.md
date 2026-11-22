# JAAS configuration

Kafka sử dụng **JAAS (Java Authentication and Authorization Service)** để cấu hình thông tin đăng nhập cho một số cơ chế xác thực SASL. Trong Spring Kafka, JAAS thường xuất hiện khi consumer hoặc producer kết nối tới cluster yêu cầu **SASL/PLAIN**, **SASL/SCRAM**, **SASL/GSSAPI (Kerberos)** hoặc **SASL/OAUTHBEARER**.

Một cấu hình JAAS đúng phải trả lời được: ứng dụng đăng nhập bằng LoginModule nào, dùng credential hoặc identity nào, cơ chế SASL nào được broker hỗ trợ, cấu hình được nạp từ đâu, và secret được bảo vệ ra sao. Cấu hình sai có thể khiến ứng dụng không khởi động, SASL handshake thất bại, broker từ chối authentication, hoặc tạo ra một hệ thống hoạt động trong môi trường test nhưng không an toàn khi triển khai production.

Bài học này thuộc chương **Bảo mật vận hành** của module **Spring Kafka Reliability Operations**. Nội dung tập trung vào cấu trúc JAAS, cấu hình client qua sasl.jaas.config, file JAAS tĩnh, cách Spring Boot truyền security properties tới Kafka clients, sự khác nhau giữa PLAIN/SCRAM/Kerberos/OAuth, quản lý secrets, rotation, chẩn đoán và runbook vận hành.

## 1. JAAS giải quyết phần nào của bảo mật Kafka?

Khi một Kafka client kết nối broker, có nhiều lớp bảo mật khác nhau:

1. **Transport security:** TLS mã hóa đường truyền và có thể xác thực broker hoặc client certificate.
2. **Authentication:** broker xác minh client là ai. Với SASL, cơ chế xác thực có thể sử dụng JAAS LoginModule.
3. **Authorization:** broker quyết định principal đã xác thực có được phép đọc topic, ghi topic, dùng consumer group hoặc thực hiện thao tác quản trị không.
4. **Application identity:** service và workload được cấp credential riêng, có vòng đời và quyền riêng.

JAAS chủ yếu cấu hình **login identity và credential cho authentication**. Nó không thay thế TLS, không tự định nghĩa ACL và không quyết định consumer được phép đọc topic nào.

Sơ đồ:

~~~text
Spring Boot application
        |
        v
KafkaProducer / KafkaConsumer
        |
        +-- SSL/TLS: mã hóa và xác thực transport
        |
        +-- SASL mechanism
                |
                v
             JAAS LoginModule
                |
                v
          SASL authentication exchange
                |
                v
          Kafka broker xác thực principal
                |
                v
          Kafka authorizer kiểm tra ACL
                |
                v
          Topic / group / cluster operation
~~~

Nếu authentication thành công nhưng ACL thiếu, client vẫn có thể nhận lỗi authorization. Nếu TLS handshake thất bại, JAAS LoginModule thậm chí chưa được sử dụng. Xác định đúng lớp lỗi sẽ giúp tránh thay credential khi vấn đề thực tế là truststore hoặc ACL.

## 2. JAAS LoginContext và LoginModule

JAAS định nghĩa một **LoginContext** tham chiếu tới một cấu hình đăng nhập. Cấu hình đó chứa một hoặc nhiều **LoginModule** cùng control flags và options.

Một entry có dạng tổng quát:

~~~text
KafkaClient {
    com.example.security.ExampleLoginModule required
        optionOne="value"
        optionTwo="another-value";
};
~~~

Các thành phần:

- **KafkaClient:** tên application/login context được yêu cầu.
- **LoginModule class:** lớp triển khai cơ chế đăng nhập.
- **required/requisite/sufficient/optional:** control flag quyết định cách kết quả của module ảnh hưởng toàn bộ login.
- **Options:** các tham số module cần để lấy identity, credential hoặc thiết lập subject.
- **Semicolon:** kết thúc khai báo LoginModule.
- **Closing brace and semicolon:** kết thúc entry JAAS.

Trong Kafka, các LoginModule phổ biến thuộc Kafka client hoặc JDK, ví dụ:

| Cơ chế | LoginModule thường dùng |
|---|---|
| SASL/PLAIN | org.apache.kafka.common.security.plain.PlainLoginModule |
| SASL/SCRAM | org.apache.kafka.common.security.scram.ScramLoginModule |
| SASL/GSSAPI | com.sun.security.auth.module.Krb5LoginModule |
| SASL/OAUTHBEARER | org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule |

Module class phải có trên classpath/runtime của process. Với LoginModule tùy biến, cả client và runtime phải có dependency tương ứng, đồng thời class phải triển khai đúng JAAS API.

## 3. Control flags của LoginModule

JAAS hỗ trợ bốn control flags chính:

| Flag | Ý nghĩa khái quát |
|---|---|
| required | Module phải thành công; login tiếp tục chạy các module còn lại trước khi tổng hợp kết quả |
| requisite | Module phải thành công; nếu thất bại, login dừng ngay |
| sufficient | Thành công có thể đủ để login thành công nếu các module required trước đó không thất bại |
| optional | Kết quả không bắt buộc quyết định login thành công nếu module khác đã cung cấp kết quả cần thiết |

Với cấu hình Kafka SASL thông thường, ví dụ thường thấy là một LoginModule với flag **required**:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="orders-reader"
    password="...";
~~~

Không tự thêm nhiều LoginModules hoặc đổi control flags để “thử cho chạy”. Kafka client SASL JAAS property thường được thiết kế cho một login module entry trong cấu hình client; hãy tuân theo tài liệu của Kafka client version đang sử dụng. Một JAAS file tĩnh có thể chứa nhiều entries và module theo cú pháp JAAS, nhưng cách Kafka chọn context vẫn phụ thuộc tên context và cơ chế client.

## 4. Hai cách cung cấp JAAS cho Kafka client

Kafka client có thể nhận JAAS configuration theo hai cách phổ biến:

**Cách A — Inline property sasl.jaas.config**

- Cấu hình trực tiếp trong Kafka client properties.
- Có thể đặt riêng cho producer, consumer hoặc admin client.
- Dễ truyền qua Spring Boot configuration và secret manager.
- Không cần tạo file JAAS riêng cho ứng dụng.
- Có thể override static JAAS context theo Kafka client behavior.

**Cách B — JAAS file tĩnh**

- Tạo file chứa named login contexts, ví dụ KafkaClient.
- JVM nạp file qua system property java.security.auth.login.config.
- Nhiều Java components có thể dùng chung context.
- Cần quản lý file, mount, permissions và process startup.
- Một cấu hình sai có thể ảnh hưởng nhiều clients trong cùng JVM.

Với Spring Boot microservice, **sasl.jaas.config** thường là lựa chọn thuận tiện vì security configuration có thể được gắn theo từng Kafka client factory. JAAS file tĩnh phù hợp khi môi trường đã có quy trình quản lý JVM-wide JAAS hoặc cần chia sẻ login context giữa nhiều thư viện.

## 5. Cấu trúc sasl.jaas.config

Ví dụ SASL/SCRAM-SHA-512:

~~~properties
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="secret";
~~~

Một JAAS entry inline gồm:

- Tên LoginModule class.
- Control flag.
- Module options, thường là username/password hoặc identity-specific settings.
- Kết thúc bằng dấu chấm phẩy.

Property **sasl.mechanism** và **sasl.jaas.config** phải phù hợp với listener/broker configuration. Chỉ đặt username/password không làm client tự chọn đúng SASL mechanism.

Ví dụ PLAIN:

~~~properties
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="orders-reader" password="secret";
~~~

Ví dụ SCRAM:

~~~properties
sasl.mechanism=SCRAM-SHA-256
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="secret";
~~~

Credential trong ví dụ chỉ là placeholder. Không commit password thật vào source code, application.yml, Docker image, build artifact hoặc log.

## 6. Cấu hình Spring Boot cho SASL/JAAS

Spring Boot có thể chuyển Kafka client properties qua các thuộc tính Spring Kafka. Một cách tổng quát là dùng **spring.kafka.properties** cho các Kafka properties chung:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1.example.net:9093,broker2.example.net:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: KAFKA_SASL_JAAS_CONFIG_SECRET_REFERENCE
~~~

Giá trị secret reference ở ví dụ tượng trưng cho biến môi trường hoặc secret provider được inject khi deploy. Spring placeholder có thể dùng trong application configuration, nhưng secret thật phải đến từ secret manager hoặc nền tảng triển khai, không commit vào repository.

Có thể cấu hình riêng producer và consumer nếu chúng dùng principal hoặc credential khác nhau:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1.example.net:9093
    consumer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: KAFKA_CONSUMER_JAAS_SECRET_REFERENCE
    producer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: KAFKA_PRODUCER_JAAS_SECRET_REFERENCE
~~~

Kiểu binding cụ thể và precedence giữa common properties, consumer.properties, producer.properties và admin.properties cần được xác nhận theo Spring Boot version. Không giả định property chung luôn thắng property riêng hoặc ngược lại; kiểm tra effective configuration của từng client factory.

### 6.1. Producer và consumer có thể dùng principal riêng

Một service có thể:

- Consumer đọc orders.events bằng principal orders-reader.
- Producer ghi orders.audit bằng principal orders-writer.
- Admin client chỉ dùng principal có quyền describe/config ở mức cần thiết.

Tách principal giúp least privilege và điều tra audit rõ hơn. Nếu mọi client dùng một admin credential, sự cố credential leakage có thể ảnh hưởng toàn cluster.

## 7. Tạo Kafka properties trong Java

Khi tạo Kafka client factory thủ công, có thể cấu hình security properties trong Map:

~~~java
Map<String, Object> props = new HashMap<>();

props.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "broker1.example.net:9093"
);
props.put(
    CommonClientConfigs.SECURITY_PROTOCOL_CONFIG,
    "SASL_SSL"
);
props.put(
    SaslConfigs.SASL_MECHANISM,
    "SCRAM-SHA-512"
);
props.put(
    SaslConfigs.SASL_JAAS_CONFIG,
    jaasConfigFromSecret
);
~~~

Map này có thể được dùng để tạo DefaultKafkaConsumerFactory hoặc producer factory phù hợp.

Không log toàn bộ Map vì sasl.jaas.config chứa credential. Khi debug effective properties, hãy mask password/token và chỉ hiển thị:

- security.protocol;
- sasl.mechanism;
- broker endpoint đã được làm sạch;
- secret reference/version, nếu có;
- trạng thái đã cấu hình credential hay chưa.

## 8. SASL/PLAIN

SASL/PLAIN truyền username/password trong SASL exchange. Cơ chế này phải được sử dụng trên kết nối **TLS** trong môi trường production để bảo vệ credential trên đường truyền.

Client JAAS:

~~~text
org.apache.kafka.common.security.plain.PlainLoginModule required
    username="orders-reader"
    password="replace-with-secret";
~~~

Client properties:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
~~~

Ở phía broker, cấu hình PLAIN server cần cách xác minh credential của user. Với cấu hình đơn giản, JAAS server module có thể khai báo user entries theo định dạng option do Kafka PLAIN module hỗ trợ, ví dụ:

~~~text
org.apache.kafka.common.security.plain.PlainLoginModule required
    username="broker-interbroker"
    password="broker-secret"
    user_orders-reader="reader-secret"
    user_orders-writer="writer-secret";
~~~

Các option user_* ở broker side là cơ chế ví dụ của PlainLoginModule để xác minh users. Không dùng nguyên credential ví dụ trong production. Với hệ thống thực tế, cần đánh giá cách lưu và rotation credentials; không để file broker JAAS chứa nhiều user passwords dễ đọc nếu có giải pháp secret integration phù hợp.

PLAIN không mã hóa password ở cấp cơ chế SASL. **SASL_SSL** là lựa chọn thường cần thiết để bảo vệ trao đổi qua mạng. Chỉ dùng SASL_PLAINTEXT trong môi trường lab được cô lập và không chứa credential thật.

## 9. SASL/SCRAM

SCRAM là cơ chế challenge-response dựa trên mật khẩu, giảm việc gửi password trực tiếp như PLAIN. Kafka hỗ trợ SCRAM-SHA-256 và SCRAM-SHA-512.

Client JAAS:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="orders-reader"
    password="replace-with-secret";
~~~

Client properties:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
~~~

Broker phải được cấu hình listener hỗ trợ SASL/SCRAM và có credential SCRAM của user trong metadata/configuration phù hợp. Tạo credential thường được thực hiện bằng công cụ quản trị Kafka hoặc control plane của nền tảng, không phải bằng cách chỉ thêm username/password của mọi client vào broker JAAS file.

Ví dụ lệnh quản trị minh họa:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server broker1.example.net:9093 \
  --alter \
  --add-config 'SCRAM-SHA-512=[iterations=8192,password=replace-me]' \
  --entity-type users \
  --entity-name orders-reader
~~~

Cú pháp và cách xác thực admin client phải phù hợp với Kafka version/distribution. Password trong command line có thể xuất hiện trong shell history hoặc process inspection; trong production, dùng cơ chế credential injection/secret-safe tooling được nền tảng hỗ trợ.

SCRAM vẫn nên chạy qua TLS để bảo vệ metadata, broker identity và toàn bộ traffic. Không coi SCRAM là sự thay thế cho mã hóa transport.

## 10. SASL/GSSAPI và Kerberos

GSSAPI thường tích hợp Kafka với Kerberos. JAAS LoginModule phổ biến là JDK **Krb5LoginModule**.

Ví dụ client JAAS:

~~~text
com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    storeKey=true
    keyTab="/var/run/secrets/kafka/orders-reader.keytab"
    principal="orders-reader@EXAMPLE.COM"
    serviceName="kafka";
~~~

Client property:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=GSSAPI
~~~

Một số môi trường dùng SASL_PLAINTEXT trên network đã được bảo vệ riêng, nhưng TLS vẫn là lựa chọn cần đánh giá cho transport confidentiality/integrity và broker identity.

Kerberos còn phụ thuộc:

- Realm và KDC configuration.
- DNS/service principal naming.
- Keytab permissions.
- Ticket validity/renewal.
- Clock synchronization.
- Kafka broker service principal.
- JVM krb5 configuration.

### 10.1. krb5.conf

JVM có thể cần biết cấu hình Kerberos:

~~~text
[libdefaults]
  default_realm = EXAMPLE.COM
  dns_lookup_kdc = true
  rdns = false
~~~

Có thể cung cấp file bằng system property:

~~~text
-Djava.security.krb5.conf=/etc/krb5.conf
~~~

Đường dẫn, realm và KDC phải theo môi trường thật. Không copy keytab từ laptop developer vào image hoặc repository.

### 10.2. Keytab và principal

Keytab chứa material cho phép xác thực bằng Kerberos principal. Bảo vệ như secret có giá trị cao:

- File permissions chỉ cho process user đọc.
- Mount read-only.
- Không đưa vào container image layer.
- Không log nội dung hoặc base64 của file.
- Rotation theo quy trình KDC.
- Tránh chia sẻ cùng một principal cho nhiều ứng dụng không liên quan.

Nếu dùng ticket cache thay vì keytab, cần hiểu process lifecycle, cache location và renewal. Một client khởi động thành công nhưng ticket hết hạn sau nhiều giờ có thể chỉ bộc lộ lỗi khi reconnect.

## 11. SASL/OAUTHBEARER

SASL/OAUTHBEARER dùng OAuth bearer tokens cho authentication. JAAS LoginModule là:

~~~text
org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required;
~~~

Nhưng cấu hình JAAS entry đơn giản **không tự tạo ra token hợp lệ**. Kafka client cần callback handler hoặc cơ chế hỗ trợ lấy token phù hợp với môi trường identity provider.

Client properties có thể gồm:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=OAUTHBEARER
sasl.login.callback.handler.class=com.example.kafka.security.TokenCallbackHandler
~~~

Callback handler cần triển khai đúng Kafka client API và:

- Lấy token từ identity provider hoặc workload identity.
- Xác minh audience/scope cần thiết.
- Quản lý token expiry và refresh.
- Không log token.
- Xử lý timeout, rate limit và identity provider outage.

Kafka broker cũng cần cấu hình OAuth bearer validator/callback handler phù hợp để xác minh token và ánh xạ principal. Client login thành công về mặt lấy token không bảo đảm broker chấp nhận token hoặc ACL cho phép thao tác.

Không nhúng access token dài hạn vào source code hoặc file JAAS. Token thường có vòng đời ngắn; dùng callback/credential provider và cơ chế refresh có kiểm soát.

## 12. SASL mechanism phải khớp broker listener

Một Kafka listener có thể hỗ trợ một hoặc nhiều SASL mechanisms theo broker configuration.

Ví dụ khái niệm:

~~~properties
listeners=SASL_SSL://0.0.0.0:9093
advertised.listeners=SASL_SSL://broker1.example.net:9093
listener.security.protocol.map=SASL_SSL:SASL_SSL
sasl.enabled.mechanisms=SCRAM-SHA-512,PLAIN
~~~

Client chọn một mechanism:

~~~properties
sasl.mechanism=SCRAM-SHA-512
~~~

Nếu client chọn PLAIN nhưng listener chỉ hỗ trợ SCRAM-SHA-512, authentication sẽ thất bại dù username/password đúng.

Tương tự, **security.protocol** phải khớp listener endpoint:

| Client protocol | Broker listener | Ý nghĩa |
|---|---|---|
| PLAINTEXT | PLAINTEXT | Không SASL, không TLS |
| SSL | SSL | TLS, không SASL |
| SASL_PLAINTEXT | SASL listener không TLS | SASL nhưng transport không mã hóa |
| SASL_SSL | SASL_SSL listener | SASL trên TLS |

Không thể dùng JAAS để biến một PLAINTEXT listener thành SASL listener. Broker listener phải được cấu hình và mở đúng endpoint.

## 13. JAAS file tĩnh cho Kafka client

Một JAAS file có thể định nghĩa named context:

~~~text
KafkaClient {
    org.apache.kafka.common.security.scram.ScramLoginModule required
        username="orders-reader"
        password="replace-with-secret";
};
~~~

JVM nạp file qua:

~~~text
-Djava.security.auth.login.config=/etc/kafka/jaas.conf
~~~

Kafka client có thể tìm context **KafkaClient** trong JAAS configuration khi không dùng inline sasl.jaas.config theo behavior của Kafka client.

Các điểm vận hành:

- File phải tồn tại và process user có quyền đọc.
- Đường dẫn phải đúng trong container, không phải host path.
- File nên mount read-only.
- Secret phải được cấp qua secret manager/Kubernetes Secret hoặc cơ chế tương đương.
- Không đặt file trong source tree hoặc image layer.
- JVM system property phải được truyền đúng lúc process khởi động.
- Khi thay file, cần biết LoginContext/client có reload hay phải tạo lại client.

Không giả định sửa file trên disk sẽ tự động cập nhật LoginContext đang chạy. Credential refresh behavior phụ thuộc LoginModule và Kafka client lifecycle.

## 14. Static JAAS context và client inline override

Kafka client có thể nhận inline property:

~~~properties
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="secret";
~~~

Khi property này được cấu hình, client sử dụng entry đó cho SASL login thay vì dựa vào static JAAS context theo quy tắc của Kafka client.

Lợi ích:

- Producer/consumer có thể dùng principal khác nhau.
- Nhiều Kafka clusters trong cùng JVM có thể có credentials riêng.
- Không cần thay đổi JVM-wide JAAS file cho từng client.
- Spring Boot có thể bind security settings theo factory.

Static JAAS phù hợp với môi trường có cấu hình login context ở cấp JVM. Nếu nhiều libraries cùng dựa vào KafkaClient, cần thống nhất ownership để tránh một file global chứa credential cho quá nhiều thành phần.

## 15. Broker-side JAAS và listener-specific configuration

Broker cũng có thể dùng JAAS để xác thực client hoặc đăng nhập vào cluster khác trong một số cơ chế.

Một file JAAS tĩnh cho broker thường có context **KafkaServer**. Ví dụ cấu hình PLAIN đơn giản:

~~~text
KafkaServer {
    org.apache.kafka.common.security.plain.PlainLoginModule required
        username="broker-interbroker"
        password="interbroker-secret"
        user_orders-reader="reader-secret"
        user_orders-writer="writer-secret";
};
~~~

Broker khởi động với:

~~~text
-Djava.security.auth.login.config=/etc/kafka/kafka_server_jaas.conf
~~~

Trong Kafka broker, listener/mechanism-specific JAAS properties có thể được cấu hình theo dạng:

~~~properties
listener.name.sasl_ssl.plain.sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="broker-interbroker" password="secret" user_orders-reader="reader-secret";
~~~

Tên listener và mechanism trong property phải theo quy tắc lowercase tương ứng. Cú pháp chính xác phụ thuộc Kafka broker version và security setup.

Đừng nhầm:

- **Client JAAS:** credential client dùng để đăng nhập broker.
- **Broker JAAS:** module/credential broker dùng cho cơ chế server-side hoặc inter-broker SASL.
- **Inter-broker authentication:** broker xác thực với broker khác, nếu cluster dùng SASL cho internal traffic.

Một client có thể đăng nhập thành công vào external listener nhưng broker-to-broker communication vẫn lỗi do inter-broker mechanism hoặc credential riêng.

## 16. SCRAM broker credentials không giống PLAIN user options

Với PLAIN, một cấu hình JAAS đơn giản có thể chứa user_* options để server kiểm tra password. Với SCRAM, credential user thường được quản lý qua Kafka metadata/configuration theo cơ chế SCRAM.

Không copy mẫu PLAIN user_* vào SCRAM LoginModule rồi kỳ vọng broker nhận credential. Cần tạo SCRAM credential cho principal theo Kafka administration mechanism và cấu hình listener hỗ trợ mechanism tương ứng.

Broker-side JAAS cũng có thể cần username/password cho **inter-broker client authentication**. Đó là identity broker dùng để kết nối broker khác, không phải danh sách mọi user consumer.

## 17. Spring Boot profiles và nhiều môi trường

Không nên dùng cùng một JAAS string hard-coded cho local, staging và production.

Một cấu hình profile:

~~~yaml
spring:
  kafka:
    bootstrap-servers: KAFKA_BOOTSTRAP_SERVERS_SECRET_REFERENCE
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: KAFKA_SASL_JAAS_CONFIG_SECRET_REFERENCE
~~~

Các giá trị non-secret như mechanism/endpoint có thể cấu hình theo environment. Secret nên được inject bởi nền tảng, không commit vào profile.

Local development có thể dùng một Kafka dev cluster riêng và principal hạn chế. Đừng tắt TLS hoặc chuyển sang PLAIN password thật chỉ để làm cấu hình local giống production đơn giản hơn.

## 18. Kubernetes Secret và JAAS inline string

Một Kubernetes Secret có thể cung cấp biến môi trường:

~~~yaml
env:
  - name: KAFKA_SASL_JAAS_CONFIG
    valueFrom:
      secretKeyRef:
        name: orders-kafka-auth
        key: sasl-jaas-config
~~~

Ứng dụng dùng secret injection theo cấu hình Spring Boot ở phần trước.

Kubernetes Secret cần được bảo vệ:

- Bật encryption at rest cho backing store theo chính sách cluster.
- RBAC giới hạn ai được đọc Secret.
- Không in toàn bộ Pod environment trong diagnostic endpoints/logs.
- Tránh expose Actuator env/configprops endpoints không được bảo vệ.
- Dùng namespace/service account riêng theo workload.
- Hạn chế quyền exec vào container production.

Một Secret dạng environment variable thường được đọc lúc process start. Cập nhật Secret không nhất thiết cập nhật environment variable trong process đang chạy; rollout/restart có kiểm soát có thể cần thiết để credential mới có hiệu lực.

## 19. Mount JAAS file dưới dạng Secret volume

Nếu dùng static JAAS file:

~~~yaml
volumes:
  - name: kafka-jaas
    secret:
      secretName: orders-kafka-jaas
      defaultMode: 0400
containers:
  - name: orders-service
    volumeMounts:
      - name: kafka-jaas
        mountPath: /etc/kafka
        readOnly: true
~~~

JVM:

~~~text
-Djava.security.auth.login.config=/etc/kafka/jaas.conf
~~~

Ví dụ YAML cần được ghép vào Pod spec đầy đủ theo ứng dụng. Xác nhận file path, owner/group và quyền đọc trong image. Nếu process chạy non-root, mode 0400 có thể không cho user đó đọc nếu ownership không phù hợp; cần thiết kế securityContext/volume permissions có chủ đích.

Không mount Secret read-write cho ứng dụng chỉ cần đọc. Không copy file JAAS vào image bằng Dockerfile COPY.

## 20. Không đưa JAAS secrets vào command line hoặc logs

Một lỗi thường gặp là chạy:

~~~text
java -Dsasl.jaas.config="...password=secret..." -jar app.jar
~~~

Credential có thể xuất hiện trong process arguments, shell history, diagnostic tools hoặc deployment manifests. Kafka client property không nên được truyền bằng cách làm lộ password ở command line.

Ưu tiên:

- Secret manager hoặc workload identity.
- Environment variable được inject có kiểm soát.
- Mounted Secret file với permissions phù hợp.
- Callback handler lấy token/credential động.
- Redaction trong logs, tracing và exception reporting.

Không log sasl.jaas.config. Không đưa password vào exception message hoặc startup configuration dump.

## 21. Secret rotation cho SCRAM/PLAIN

Rotation phải được phối hợp giữa broker credential và client credential. Một quy trình tổng quát:

1. Tạo credential mới hoặc cơ chế song song được nền tảng hỗ trợ.
2. Cấp quyền đúng cho principal mới.
3. Cập nhật Secret Manager/Kubernetes Secret.
4. Tạo/restart clients theo rollout có kiểm soát để nạp credential mới.
5. Xác minh authentication và authorization trên mọi replicas.
6. Theo dõi authentication failures, reconnects và consumer lag.
7. Thu hồi credential cũ sau khi mọi clients đã chuyển.

Không đổi password phía broker trước khi biết clients nào đang dùng credential đó. Một lần rotation đồng loạt có thể khiến hàng trăm consumers reconnect thất bại và gây rebalance storm.

Nếu cơ chế credential hỗ trợ nhiều credential/overlap trong quá trình chuyển đổi, dùng cửa sổ overlap để giảm downtime. Cách triển khai cụ thể phụ thuộc Kafka version và credential provider.

## 22. Secret rotation cho Kerberos

Kerberos rotation liên quan principal/keytab và ticket renewal:

- Cấp keytab mới theo quy trình KDC.
- Kiểm tra principal và service principal name.
- Cập nhật Secret volume an toàn.
- Xác định Kafka LoginModule có reload keytab hay cần re-login/recreate client.
- Theo dõi ticket expiry và renewal failures.
- Rollout clients để tránh tất cả members reconnect cùng lúc.
- Thu hồi keytab cũ sau khi xác minh toàn bộ workload.

Một file keytab được cập nhật trên volume không bảo đảm LoginModule đang chạy tự động nạp key mới. Hãy kiểm tra lifecycle thực tế và lên lịch client reauthentication/recreation nếu cần.

## 23. OAuth token refresh

OAuth bearer thường dùng token ngắn hạn. Cần:

- Token callback handler có thể lấy token mới.
- Refresh trước khi hết hạn với safety margin.
- Xử lý identity provider timeout/rate limit.
- Không log bearer token.
- Xác minh audience, issuer và scopes.
- Phân biệt lỗi lấy token với broker từ chối token.
- Theo dõi thời gian tới expiry và refresh failures.

Không giải quyết token expiry bằng cách tăng thời hạn token vô hạn hoặc đặt access token tĩnh trong JAAS file. Dùng workload identity hoặc client credentials flow phù hợp với security policy.

## 24. Principal mapping và authorization

Authentication xác định principal. Broker authorizer sau đó kiểm tra ACL hoặc policy.

~~~text
JAAS/SASL login thành công
        |
        v
Principal = User:orders-reader
        |
        v
ACL check:
  READ orders.events
  READ group inventory-worker
        |
        +-- Allowed -> consume
        |
        +-- Denied -> authorization exception
~~~

Broker có thể dùng principal builder hoặc principal mapping rules để chuẩn hóa tên principal. Với Kerberos, principal như orders-reader@EXAMPLE.COM có thể được ánh xạ thành tên ngắn theo cấu hình broker.

Không sửa JAAS password khi lỗi thực tế là ACL. Authentication failure thường có dấu hiệu SASL handshake/login; authorization failure thường xảy ra sau khi broker đã xác định principal và kiểm tra operation.

## 25. TLS truststore vẫn cần khi dùng SASL_SSL

JAAS không cấu hình trust chain TLS. Với SASL_SSL, client còn phải tin cậy certificate broker:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      ssl.truststore.location: /var/run/secrets/kafka/client.truststore.p12
      ssl.truststore.password: KAFKA_TRUSTSTORE_PASSWORD_SECRET_REFERENCE
      ssl.truststore.type: PKCS12
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: KAFKA_SASL_JAAS_CONFIG_SECRET_REFERENCE
~~~

Đây là ví dụ client truststore. Không phải mọi cluster đều yêu cầu truststore password hoặc file riêng; có thể dùng JVM truststore hoặc PEM-based configuration tùy Kafka client version.

Nếu broker certificate không được tin cậy, lỗi xảy ra ở TLS handshake trước SASL. Thay JAAS password sẽ không sửa được truststore/certificate issue.

Nếu dùng mTLS, client certificate/key configuration thuộc SSL properties; đó là một lớp xác thực transport khác. Có thể kết hợp mTLS với SASL, nhưng cần xác định broker listener và policy hỗ trợ cả hai.

## 26. Tách authentication và authorization khi đọc lỗi

| Triệu chứng | Lớp có khả năng lỗi | Kiểm tra |
|---|---|---|
| TLS handshake failed | SSL/TLS | Certificate chain, hostname, truststore |
| No matching SASL mechanism | SASL negotiation | Broker enabled mechanisms và client sasl.mechanism |
| JAAS configuration error | JAAS parsing/login | LoginModule, control flag, options, semicolon |
| Authentication failed | SASL credential/identity | Username/password, SCRAM credential, token, Kerberos |
| Group authorization failed | Broker ACL | Group resource permissions |
| Topic authorization failed | Broker ACL | READ/WRITE/Describe permissions |
| Token expired/invalid | OAuth | Issuer, audience, expiry, callback refresh |
| GSS initiate failed | Kerberos | Keytab, principal, KDC, DNS, clock |

Lỗi có thể được wrap bởi Kafka client hoặc Spring Kafka. Đọc **root cause chain** và broker logs khi có quyền truy cập, không chỉ exception đầu tiên trong application log.

## 27. Những lỗi cú pháp JAAS thường gặp

### Thiếu dấu chấm phẩy

Sai:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="reader"
    password="secret"
~~~

Đúng:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="reader"
    password="secret";
~~~

### Sai tên LoginModule

Một typo trong package/class khiến LoginModule không load được. Kiểm tra tên chính xác và dependency Kafka client/JDK.

### Sai quote hoặc escape

Password có ký tự đặc biệt cần được biểu diễn đúng trong JAAS string, YAML, shell và environment variable. Nhiều lớp parser có thể làm biến đổi backslash/quote.

### Dùng sai context name

Static JAAS file có KafkaClient nhưng client/library yêu cầu context khác, hoặc JVM đang load file khác.

### SASL mechanism không khớp

ScramLoginModule nhưng sasl.mechanism=PLAIN, hoặc ngược lại.

### Trộn YAML quoting với JAAS syntax

YAML string cần được quote/escape đúng. Cách an toàn là đặt JAAS string qua secret reference, không viết trực tiếp password phức tạp trong YAML.

## 28. Ví dụ cấu hình YAML và escaping

JAAS string có dấu ngoặc kép, dấu cách và dấu chấm phẩy. Nếu inline trong YAML:

~~~yaml
spring:
  kafka:
    properties:
      sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="replace-me";'
~~~

Single quotes bên ngoài giúp giữ nguyên double quotes trong JAAS string. Nếu password chứa single quote, backslash hoặc ký tự YAML đặc biệt, cần escaping đúng theo YAML và JAAS parser; không ghép chuỗi bằng cách nối raw user input.

Trong production, nên đưa toàn bộ JAAS string từ secret injection:

~~~yaml
sasl.jaas.config: KAFKA_SASL_JAAS_CONFIG_SECRET_REFERENCE
~~~

Secret value phải chứa đúng một JAAS entry hoàn chỉnh. Khi inject qua CI/CD, kiểm tra newline/trailing whitespace và quoting nhưng không in secret ra pipeline logs.

## 29. Nhiều Kafka clusters trong cùng Spring Boot application

Một ứng dụng có thể kết nối nhiều clusters:

~~~text
Spring Boot service
   |
   +-- Primary Kafka
   |     +-- orders-reader principal
   |
   +-- Audit Kafka
         +-- audit-writer principal
~~~

Nếu dùng common spring.kafka.properties cho cả hai, rất dễ vô tình dùng cùng credential hoặc security protocol cho mọi client. Với nhiều clusters, tạo **named KafkaProperties/ConsumerFactory/ProducerFactory** riêng, mỗi factory có:

- bootstrap servers riêng;
- security.protocol riêng;
- sasl.mechanism riêng;
- sasl.jaas.config riêng;
- SSL trust material riêng nếu cần;
- principal/ACL phù hợp.

Không đưa hai clusters khác nhau vào cùng một bootstrap list nếu chúng không thuộc cùng một Kafka cluster hoặc không chia sẻ security/metadata semantics.

## 30. Cấu hình AdminClient và Kafka Streams

AdminClient, Kafka Streams và Kafka Connect có security configuration riêng theo client/runtime.

- AdminClient cần SASL/JAAS properties khi gọi describe/config/ACL operations.
- Kafka Streams cần cấu hình cho internal consumers/producers và có thể có properties riêng.
- Kafka Connect worker và connector có thể dùng worker-level hoặc connector-level overrides tùy deployment.

Không giả định cấu hình consumer factory trong Spring Kafka tự động áp dụng cho mọi AdminClient hoặc Kafka Streams instance được tạo độc lập.

Nếu ứng dụng dùng Spring Kafka Admin, xác nhận AdminClient properties được tạo từ đúng Boot configuration. Nếu tạo AdminClient thủ công, truyền security properties phù hợp và không log JAAS.

## 31. Credential scope và least privilege

Một principal nên có quyền tối thiểu theo vai trò:

| Principal | Quyền gợi ý |
|---|---|
| orders-reader | READ/Describe topic orders.events và READ group orders-worker |
| orders-writer | WRITE/Describe topic orders.audit |
| orders-admin | Chỉ quyền quản trị được phê duyệt, không dùng cho runtime listener |
| broker-interbroker | Quyền và identity dành cho broker-to-broker communication |

Tên quyền/ACL cụ thể phụ thuộc authorizer và Kafka distribution. Nguyên tắc là producer không cần quyền đọc mọi topic; consumer không cần quyền tạo topic hoặc sửa cluster config.

Tách credential theo workload giúp:

- Thu hồi một service mà không ảnh hưởng toàn hệ thống.
- Audit principal rõ hơn.
- Giới hạn blast radius khi secret bị lộ.
- Rotation theo từng service.

## 32. JAAS và secret management

Một quy trình secret an toàn:

~~~text
Secret manager / workload identity
             |
             v
Deployment platform inject secret
             |
             v
Spring Boot binds property
             |
             v
Kafka client LoginModule
             |
             v
SASL authentication
~~~

Các nguyên tắc:

- Không hard-code password/token trong Git.
- Không đưa secrets vào Docker build args hoặc image layers.
- Không lưu secret trong Helm values đã commit.
- Không in ApplicationContext Environment/config props chứa secrets.
- Mask secret trong startup diagnostics.
- Phân quyền đọc secret theo workload identity.
- Có audit access và rotation.
- Xóa secret khỏi shell history và CI logs nếu vô tình lộ.

Nếu credential bị lộ, coi đó là incident: revoke/rotate, kiểm tra access logs, rà soát principal permissions và đánh giá data access. Chỉ sửa file cấu hình mà không thu hồi credential cũ không giải quyết exposure.

## 33. Quan sát JAAS login và SASL handshake

Một số Kafka client logs có thể giúp chẩn đoán:

- LoginModule initialization.
- SASL mechanism negotiation.
- Authentication exchange.
- Callback handler errors.
- Reauthentication/credential refresh.
- Broker disconnect/reconnect.

Tên logger và mức chi tiết phụ thuộc Kafka client version. Bật DEBUG/TRACE có thể tạo rất nhiều logs và làm lộ metadata nhạy cảm. Không giả định logs luôn mask password/token đúng như mong đợi.

Quy trình:

1. Bắt đầu với application exception và root cause.
2. Xác định TLS, SASL negotiation, JAAS login hay ACL.
3. Bật logger hẹp trong thời gian ngắn nếu cần.
4. Redact credentials/token trước khi gửi log ra hệ thống ticket/chat.
5. Tắt verbose logging sau khi có bằng chứng.

Không dùng debug logs chứa raw JAAS config trong production.

## 34. Kiểm tra effective security configuration

Khi cấu hình nhiều layers, hãy kiểm tra client thực sự nhận:

- bootstrap.servers;
- security.protocol;
- sasl.mechanism;
- JAAS config đã được cung cấp hay chưa;
- SSL truststore type/location;
- callback handler class;
- client.id/group.id.

Không in raw sasl.jaas.config hoặc token. Có thể log:

~~~text
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config.present=true
sasl.username=orders-reader
credential.source=kubernetes-secret/orders-kafka-auth
~~~

Username cũng có thể là dữ liệu nhạy cảm theo policy; nếu cần, mask hoặc log principal đã chuẩn hóa.

Nếu Spring Boot common properties và consumer-specific properties cùng khai báo security settings, hãy xác minh **effective config của từng client factory** thay vì đoán precedence.

## 35. JAAS configuration và lifecycle của Kafka client

JAAS LoginContext thường được tạo trong quá trình Kafka client authentication. Khi credential thay đổi:

- Một số callback handler có thể lấy token mới khi re-login.
- Static JAAS file không nhất thiết được đọc lại cho LoginContext đang tồn tại.
- Environment variables không tự đổi trong process đang chạy.
- Kafka producer/consumer đã tạo có thể cần close/recreate để dùng config mới.
- Spring Kafka listener container cần lifecycle restart có kiểm soát nếu factory/config mới yêu cầu client mới.

Không cập nhật Secret rồi giả định client đang chạy đã dùng password mới. Xác minh bằng authentication event, client reconnect và rollout behavior.

## 36. Connection pool và nhiều consumer clients

Một ConcurrentMessageListenerContainer có thể tạo nhiều child consumers. Nếu mỗi child consumer sử dụng SASL, credential/login behavior có thể được khởi tạo cho từng client instance.

Khi rollout hoặc reconnect đồng loạt:

- Nhiều clients cùng đăng nhập.
- Identity provider/KDC có thể chịu tải tăng.
- Broker authentication rate tăng.
- Rebalance và reconnect có thể xảy ra đồng thời.

Rotation nên được rollout dần, readiness/liveness và retry/backoff phù hợp, tránh tất cả pods restart cùng lúc nếu group cần duy trì capacity.

## 37. Kerberos clock skew và DNS

Kerberos phụ thuộc timestamp và service principal resolution. Các lỗi:

- Client clock lệch so với KDC.
- DNS reverse lookup trả hostname khác service principal.
- Broker principal dùng service name/realm khác client kỳ vọng.
- Keytab chứa principal không đúng.
- Ticket hết hạn hoặc renewal không hoạt động.

Khi GSSAPI login lỗi, kiểm tra:

1. NTP/clock synchronization trên node và KDC.
2. Principal trong keytab.
3. Kafka broker service principal.
4. DNS forward/reverse.
5. krb5.conf realm/KDC.
6. Keytab file permissions.
7. Ticket validity và renewal.

Đừng thay username/password SCRAM khi cluster thực tế đang dùng GSSAPI.

## 38. OAuth callback handler và token errors

Với OAUTHBEARER, cần tách:

- Token acquisition failure: không lấy được token từ IdP.
- Token refresh failure: token sắp hết hạn nhưng refresh thất bại.
- Broker validation failure: broker không tin issuer/audience/signature.
- Authorization failure: principal được xác thực nhưng ACL không cho phép.

Logs nên ghi:

~~~text
event=oauth_token_refresh_failed
provider=corp-idp
reason=timeout
token_present=true
token_value=REDACTED
~~~

Không ghi token hoặc JWT payload đầy đủ nếu có claim nhạy cảm. Khi debug JWT, chỉ trích xuất các claim không nhạy cảm cần thiết và tuân theo policy bảo mật.

## 39. JAAS và lỗi AuthenticationException

Khi client nhận AuthenticationException, đừng bắt exception rồi retry vô hạn với cùng credential. Nếu password sai hoặc user chưa được tạo, retry không làm vấn đề biến mất.

Một policy phù hợp:

- Phân loại lỗi credential/configuration là non-retryable hoặc retry chậm có giới hạn.
- Phát alert sớm.
- Giữ readiness phản ánh khả năng kết nối theo yêu cầu service.
- Tránh crash loop quá nhanh làm broker/IdP bị bão login.
- Sau khi credential được sửa, tạo lại client/container theo lifecycle.

Với transient network/IdP outage, retry có backoff và jitter có thể phù hợp. Với ACL denial, cần sửa authorization policy.

## 40. Runbook: SASL authentication failed

### Bước 1 — Xác nhận endpoint

Đúng bootstrap server, port, listener và environment chưa? Client có kết nối nhầm cluster hoặc port PLAINTEXT không?

### Bước 2 — Kiểm tra security protocol

Client security.protocol có khớp listener không? SASL_SSL cần TLS certificate trust đúng trước khi SASL chạy.

### Bước 3 — Kiểm tra mechanism

Client sasl.mechanism có nằm trong broker sasl.enabled.mechanisms không? PLAIN/SCRAM/GSSAPI/OAUTHBEARER có khớp JAAS LoginModule không?

### Bước 4 — Kiểm tra JAAS parsing

LoginModule class đúng? Options có đúng? Control flag có hợp lệ? Inline string có dấu chấm phẩy và escaping đúng? File context có đúng tên không?

### Bước 5 — Xác minh credential source

Secret reference có tồn tại? Pod mount/inject đúng version? Username/principal có đúng? Password có bị whitespace/newline thêm vào không? Secret rotation có rollout process chưa?

### Bước 6 — Kiểm tra broker-side identity

PLAIN server user config, SCRAM credential, Kerberos service principal hoặc OAuth validator có tương ứng không?

### Bước 7 — Kiểm tra TLS/Kerberos/OAuth riêng

TLS truststore/hostname, Kerberos realm/keytab/clock, hoặc OAuth issuer/audience/expiry/callback.

### Bước 8 — Kiểm tra broker logs

Nếu được phép, đối chiếu broker authentication logs để xác định handshake bị từ chối vì mechanism, credential hay principal.

Không đưa password, keytab content hoặc bearer token vào ticket khi báo lỗi.

## 41. Runbook: Authentication thành công nhưng topic access bị từ chối

Triệu chứng: consumer kết nối được nhưng nhận TopicAuthorizationException hoặc GroupAuthorizationException.

1. Xác định principal sau authentication/principal mapping.
2. Xác nhận consumer group name và topic name chính xác.
3. Kiểm tra ACL READ/Describe cho topic.
4. Kiểm tra ACL READ cho consumer group.
5. Với producer, kiểm tra WRITE/Describe và transactional ID ACL nếu dùng transactions.
6. Kiểm tra cluster authorizer và principal builder/mapping.
7. Cấp quyền tối thiểu qua quy trình change được phê duyệt.
8. Xác minh bằng consumer/producer operation thực tế.

Không thay JAAS credentials nếu principal đã authenticate đúng và chỉ thiếu ACL.

## 42. Runbook: ứng dụng chạy được lúc đầu nhưng lỗi sau vài giờ

Khả năng:

- OAuth token hết hạn và refresh callback lỗi.
- Kerberos ticket/keytab renewal không hoạt động.
- Credential đã rotation nhưng một số pods chưa reload.
- Broker reauthentication/connection renewal kích hoạt lỗi.
- Secret volume/env version không đồng nhất giữa replicas.

Kiểm tra:

1. Timestamp authentication success cuối và failure đầu.
2. Token/ticket expiry timeline.
3. Callback refresh logs đã redact.
4. Pod/instance nào đang dùng secret version nào.
5. Client reconnect/re-authentication behavior.
6. Broker authentication failures và group rebalance.
7. Cơ chế tạo lại Kafka clients sau khi secret đổi.

Khôi phục theo đúng credential provider lifecycle, không chỉ restart một pod ngẫu nhiên rồi bỏ qua các replicas còn lại.

## 43. Runbook: JAAS file không được load

1. Kiểm tra JVM system property java.security.auth.login.config.
2. Xác minh absolute path trong container.
3. Kiểm tra volume mount và file tồn tại.
4. Kiểm tra process user có quyền đọc.
5. Xác minh file encoding và syntax.
6. Xác nhận context name KafkaClient/KafkaServer theo client/broker.
7. Kiểm tra inline sasl.jaas.config có override static context không.
8. Kiểm tra file được nạp ở process startup và client đã được tạo trước/sau thời điểm nào.
9. Không in file ra console để debug.

Nếu dùng Spring Boot, kiểm tra xem property được bind trực tiếp qua sasl.jaas.config hay app thực sự dựa vào static file.

## 44. Kiểm thử cấu hình JAAS

Một bộ kiểm thử bảo mật nên có:

### 44.1. Happy path với SASL/SCRAM

- Tạo principal test có quyền tối thiểu.
- Cấu hình SASL_SSL và SCRAM mechanism.
- Consumer đọc topic được cấp quyền.
- Producer chỉ ghi được topic được cấp quyền.

### 44.2. Credential sai

- Dùng password sai.
- Xác nhận authentication failure được phân loại rõ.
- Không có retry storm hoặc crash loop vô hạn.
- Logs không chứa secret.

### 44.3. Mechanism không khớp

- Client chọn mechanism broker không bật.
- Xác nhận lỗi được phân loại là SASL negotiation/configuration.

### 44.4. ACL thiếu

- Authentication thành công với principal hợp lệ.
- Thu hồi READ topic hoặc group ACL.
- Xác nhận lỗi authorization được phân biệt với authentication failure.

### 44.5. TLS trust lỗi

- Dùng truststore không tin cậy broker test certificate.
- Xác nhận lỗi xảy ra ở TLS handshake và không bị nhầm thành JAAS password.

### 44.6. Secret rotation

- Chuyển từ credential cũ sang credential mới theo quy trình.
- Rollout clients dần.
- Xác nhận tất cả instances kết nối lại.
- Thu hồi credential cũ sau khi hoàn tất.

### 44.7. OAuth expiry/refresh

- Dùng token có expiry ngắn trong test.
- Mô phỏng IdP timeout và refresh failure.
- Xác nhận callback không log token và client có policy reconnect phù hợp.

### 44.8. Kerberos

- Dùng realm/KDC test.
- Kiểm tra principal/keytab.
- Kiểm tra clock skew và ticket renewal.

Không dùng credential production thật trong integration tests hoặc CI logs.

## 45. Kiểm tra Spring Boot property binding

Khi cấu hình nhiều factories, test cần xác nhận:

- Consumer factory nhận đúng sasl.mechanism và JAAS credential source.
- Producer factory dùng principal riêng nếu được yêu cầu.
- AdminClient không vô tình dùng admin credential rộng hơn cần thiết.
- Không có factory nào fallback sang PLAINTEXT ngoài ý muốn.
- Secret chưa được resolve sẽ fail fast, không âm thầm dùng default credential.
- Startup diagnostics không in raw JAAS string.

Có thể dùng test configuration/bean inspection và một broker test có SASL. Không chỉ assert YAML string tồn tại; phải xác minh Kafka client thực tế có thể authenticate và được authorize.

## 46. Những sai lầm cấu hình thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Chỉ đặt username/password | Broker không biết mechanism phù hợp | Cấu hình sasl.mechanism và JAAS LoginModule tương ứng |
| Dùng PLAIN trên đường truyền không mã hóa | Credential có thể bị lộ | Dùng SASL_SSL |
| Nhầm JAAS với ACL | Authentication thành công nhưng operation bị từ chối | Kiểm tra principal và ACL |
| Nhầm SASL failure với TLS failure | Sửa sai lớp | Đọc handshake/root cause |
| Static context name sai | LoginContext không tìm thấy entry | Kiểm tra KafkaClient/KafkaServer và file |
| Thiếu semicolon | JAAS parse failure | Dùng entry syntax hoàn chỉnh |
| SCRAM credential chỉ đặt trong client JAAS | Broker không có credential để xác minh | Tạo user SCRAM ở broker metadata/control plane |
| Copy PLAIN user_* options sang SCRAM | Server configuration sai | Dùng credential management của SCRAM |
| Hard-code secret trong YAML/Git | Secret exposure | Secret manager/injection |
| Truyền password trong JVM command line | Có thể lộ qua process inspection/history | Secret-safe injection |
| Cập nhật Secret nhưng không recreate client | Client vẫn dùng credential cũ | Hiểu reload/re-login lifecycle và rollout |
| Một admin principal cho mọi clients | Blast radius lớn | Tách principals least privilege |
| OAuth token tĩnh trong JAAS | Token hết hạn, auth outage | Callback handler/refresh |
| Kerberos keytab sai principal | GSSAPI login thất bại | Kiểm tra keytab, realm và service principal |
| Không đồng bộ clock | Kerberos ticket bị từ chối | NTP và clock monitoring |
| Log toàn bộ properties | Có thể lộ password/token | Redaction và allowlist |
| Cho rằng KafkaClient static file áp dụng mọi client | Một số clients có inline override hoặc context riêng | Kiểm tra effective config từng factory |

## 47. Checklist production

Trước khi triển khai JAAS configuration:

1. Đã xác định đúng authentication mechanism mà broker listener hỗ trợ chưa?
2. security.protocol có khớp endpoint và yêu cầu TLS không?
3. LoginModule class có sẵn trong runtime không?
4. JAAS syntax, control flag, options và semicolon có hợp lệ không?
5. Client dùng inline sasl.jaas.config hay static JAAS file, và ownership đã rõ chưa?
6. Static context name KafkaClient/KafkaServer có đúng không?
7. Spring Boot consumer, producer và admin clients có effective security config phù hợp riêng không?
8. Broker-side PLAIN/SCRAM/Kerberos/OAuth configuration đã được provision chưa?
9. Principal có least privilege ACL không?
10. TLS truststore/certificate có được cấu hình độc lập với JAAS không?
11. Secret có được lấy từ secret manager/workload identity thay vì Git/image không?
12. Logs, Actuator và diagnostics có mask JAAS/password/token không?
13. Kubernetes Secret RBAC, encryption at rest và volume permissions có phù hợp không?
14. Rotation có overlap/rollout/reconnect plan không?
15. OAuth token refresh hoặc Kerberos ticket renewal có được kiểm thử không?
16. Nhiều replicas có thể reconnect đồng loạt gây authentication storm không?
17. Có phân biệt AuthenticationException và authorization failures không?
18. Có quan sát SASL handshake, TLS và broker authentication logs trong incident không?
19. Có integration tests cho wrong credential, mechanism mismatch, TLS, ACL và rotation không?
20. Có runbook rollback/rotate/revoke credential khi bị lộ hoặc auth outage không?

## 48. Kết luận

**JAAS configuration** là một phần của lớp authentication khi Kafka client sử dụng SASL. Trong Spring Kafka, cách cấu hình thường thuận tiện nhất là truyền LoginModule entry qua **sasl.jaas.config**, kết hợp **security.protocol** và **sasl.mechanism** phù hợp. JAAS file tĩnh với context KafkaClient/KafkaServer vẫn hữu ích trong những môi trường quản lý login ở cấp JVM hoặc broker.

Vận hành an toàn đòi hỏi phân biệt PLAIN, SCRAM, GSSAPI và OAUTHBEARER; hiểu credential nằm ở client, broker hay identity provider; tách authentication khỏi TLS và ACL; quản lý secret bằng nền tảng; và có kế hoạch rotation/re-authentication. Khi có lỗi, xác định nó xảy ra ở TLS handshake, JAAS parsing/login, SASL negotiation, broker authentication hay authorization trước khi thay đổi credential.

Một cấu hình JAAS tốt không chỉ giúp client đăng nhập thành công. Nó phải giới hạn principal đúng quyền, giữ credential khỏi logs/artifacts, hỗ trợ rotation có kiểm soát và cung cấp đủ bằng chứng để điều tra authentication failures mà không làm gián đoạn toàn bộ consumer group.
