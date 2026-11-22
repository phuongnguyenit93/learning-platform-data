# SASL/PLAIN, SASL/SCRAM, Kerberos và OAuthBearer

Kafka cần xác thực client trước khi cho phép client sử dụng API của broker. Trong môi trường production, producer, consumer, Kafka Connect worker và Kafka Streams application thường kết nối qua listener được bảo vệ bằng TLS và SASL. Cơ chế SASL quyết định cách client chứng minh danh tính; authorizer và ACL quyết định danh tính đó được phép làm gì.

Bài này tập trung vào bốn cơ chế SASL thường gặp:

- **SASL/PLAIN:** xác thực bằng username/password, cấu hình đơn giản và thường dùng cùng TLS.
- **SASL/SCRAM:** xác thực username/password bằng challenge-response, không gửi password trực tiếp trong quá trình SASL authentication.
- **SASL/GSSAPI (Kerberos):** xác thực bằng ticket Kerberos và service principal, phù hợp môi trường đã có KDC hoặc Active Directory.
- **SASL/OAUTHBEARER:** xác thực bằng access token do OAuth 2.0/OIDC identity provider cấp.

Mỗi cơ chế có cách cấp credential, cấu hình broker/client, vòng đời secret và cách xử lý sự cố khác nhau. Chọn cơ chế dựa trên hạ tầng identity hiện có, khả năng vận hành, yêu cầu bảo mật và cách cấp quyền cho principal.

## 1. Authentication, authorization và TLS

Ba lớp này giải quyết ba vấn đề khác nhau:

| Lớp | Câu hỏi | Thành phần Kafka |
|---|---|---|
| TLS | Kết nối có được mã hóa và xác minh certificate không? | SSL listener, truststore, keystore |
| Authentication | Client là ai? | SASL mechanism hoặc client certificate |
| Authorization | Client được phép làm gì? | Authorizer, ACL, principal |

Ví dụ một producer xác thực thành công với principal **User:orders-writer**. Điều đó không tự động cho phép producer ghi mọi topic. Authorizer vẫn kiểm tra ACL để quyết định principal này có quyền Write trên topic orders hay không.

Tương tự, consumer xác thực thành công vẫn có thể bị từ chối nếu thiếu quyền Read trên topic hoặc quyền Read trên consumer group.

### 1.1. SASL là gì?

SASL (Simple Authentication and Security Layer) là lớp xác thực được Kafka dùng để thương lượng và thực hiện một cơ chế authentication.

Một số giá trị cấu hình phổ biến:

- **security.protocol=SASL_SSL:** dùng SASL trên kết nối TLS.
- **security.protocol=SASL_PLAINTEXT:** dùng SASL nhưng không mã hóa kết nối.
- **sasl.mechanism=PLAIN:** chọn SASL/PLAIN.
- **sasl.mechanism=SCRAM-SHA-512:** chọn SCRAM-SHA-512.
- **sasl.mechanism=GSSAPI:** chọn Kerberos qua GSSAPI.
- **sasl.mechanism=OAUTHBEARER:** chọn OAuth bearer token.

Trong production, thường chọn SASL_SSL. SASL xác thực danh tính, còn TLS mã hóa traffic, xác minh broker certificate và bảo vệ thông tin trao đổi trên mạng.

### 1.2. Luồng kết nối tổng quát

~~~mermaid
sequenceDiagram
    participant C as Kafka client
    participant B as Kafka broker
    participant A as Authorizer
    C->>B: Mở kết nối TLS
    B-->>C: Broker certificate
    C->>B: SASL handshake + mechanism
    B-->>C: SASL challenge / response
    C->>B: Authentication proof / token
    B-->>C: Authentication success
    C->>B: Produce / Fetch / Metadata request
    B->>A: Kiểm tra principal và ACL
    A-->>B: Allow hoặc Deny
    B-->>C: Kết quả API
~~~

Với SASL_SSL, TLS handshake diễn ra trước SASL exchange. Khi authentication thành công, các request Kafka vẫn được kiểm tra authorization theo từng tài nguyên và operation.

### 1.3. Listener và security protocol

Broker có thể mở nhiều listener với chính sách khác nhau, ví dụ listener nội bộ cho broker-to-broker traffic và listener bên ngoài cho application:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,EXTERNAL://0.0.0.0:9093
advertised.listeners=INTERNAL://kafka-1.internal:9092,EXTERNAL://kafka-1.example.com:9093
listener.security.protocol.map=INTERNAL:SASL_SSL,EXTERNAL:SASL_SSL
inter.broker.listener.name=INTERNAL
~~~

Tên listener do quản trị viên đặt. Cần cấu hình advertised.listeners sao cho client nhận được địa chỉ có thể truy cập và certificate hostname khớp với tên broker.

Có thể giới hạn cơ chế SASL theo listener bằng các thuộc tính listener-prefixed. Điều này hữu ích khi listener nội bộ dùng SCRAM còn listener dành cho service bên ngoài dùng OAuthBearer. Kiểm tra đúng tên listener và cơ chế được bật trong cấu hình broker thực tế.

Không mở listener SASL_PLAINTEXT ra mạng không tin cậy. Nếu cần lab local, ghi rõ đó là cấu hình thử nghiệm.

## 2. SASL/PLAIN

SASL/PLAIN dùng username và password để xác thực. Cơ chế này đơn giản, dễ tích hợp với hệ thống quản lý tài khoản hiện có, nhưng password cần được bảo vệ nghiêm ngặt.

Trong SASL/PLAIN, client gửi thông tin xác thực trong SASL exchange. Vì vậy, luôn dùng TLS để mã hóa đường truyền. PLAIN không tự mã hóa password.

### 2.1. Khi nào dùng PLAIN?

PLAIN có thể phù hợp khi:

- Hệ thống có ít service account và cần cấu hình nhanh.
- Identity provider hoặc quy trình provisioning hiện có cấp username/password.
- Có TLS bắt buộc và quản lý secret an toàn.
- Cần tương thích với một connector hoặc client hỗ trợ rộng rãi.

Cân nhắc SCRAM hoặc OAuthBearer khi cần cơ chế xác thực có challenge-response hoặc token lifecycle tốt hơn.

### 2.2. Cấu hình broker cho PLAIN

Ví dụ listener EXTERNAL sử dụng SASL_SSL và PLAIN:

~~~properties
listeners=EXTERNAL://0.0.0.0:9093
advertised.listeners=EXTERNAL://kafka-1.example.com:9093
listener.security.protocol.map=EXTERNAL:SASL_SSL

sasl.enabled.mechanisms=PLAIN
listener.name.external.plain.sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required \
  user_admin="replace-with-admin-secret" \
  user_orders_writer="replace-with-orders-writer-secret" \
  user_orders_reader="replace-with-orders-reader-secret";
~~~

Trong JAAS server-side của PlainLoginModule, option có tiền tố user_ theo sau là username sẽ khai báo password mà broker chấp nhận. Ví dụ user_orders_writer tương ứng user orders_writer.

Cấu hình mặc định này lưu password dạng rõ trong JAAS configuration của broker. Cần giới hạn quyền đọc file và cân nhắc callback handler tùy chỉnh để lấy/kiểm tra password từ nguồn identity bên ngoài. Cần cấu hình keystore/truststore TLS cho listener. Đường dẫn và password trong ví dụ cần được quản lý bằng secret store hoặc Kafka ConfigProvider; không commit secret thật vào Git.

### 2.3. Cấu hình client Java

Client dùng username/password của service account:

~~~java
Properties props = new Properties();

props.put("bootstrap.servers", "kafka-1.example.com:9093");
props.put("security.protocol", "SASL_SSL");
props.put("sasl.mechanism", "PLAIN");
props.put(
    "sasl.jaas.config",
    "org.apache.kafka.common.security.plain.PlainLoginModule required "
        + "username=\"orders_writer\" "
        + "password=\"__ORDERS_WRITER_PASSWORD_FROM_SECRET_PROVIDER__\";"
);
props.put(
    "ssl.truststore.location",
    "/etc/kafka/secrets/client.truststore.p12"
);
props.put("ssl.truststore.type", "PKCS12");
~~~

Chuỗi placeholder trong ví dụ phải được thay bằng secret lấy ở runtime từ environment, secret manager hoặc ConfigProvider theo deployment platform. Nó không phải cú pháp tự động được Kafka thay thế trong mọi môi trường.

Nếu dùng sasl.jaas.config trong client properties, mỗi client instance có thể có identity riêng. Cách này thường dễ quản lý hơn JAAS file dùng chung cho nhiều ứng dụng.

### 2.4. Cấu hình JAAS file

Có thể khai báo JAAS trong file cấu hình Java bằng java.security.auth.login.config. Tuy nhiên, cần đảm bảo file chỉ đọc được bởi tài khoản chạy process và không chứa secret dùng chung không cần thiết.

Ví dụ client JAAS:

~~~text
KafkaClient {
  org.apache.kafka.common.security.plain.PlainLoginModule required
  username="orders_writer"
  password="replace-with-secret";
};
~~~

Khởi động JVM:

~~~bash
java \
  -Djava.security.auth.login.config=/etc/kafka/client-jaas.conf \
  -jar orders-producer.jar
~~~

Khi sử dụng JAAS file, client Kafka tìm login context KafkaClient. Nếu cấu hình trực tiếp sasl.jaas.config, property đó được ưu tiên cho client tương ứng và không cần dựa vào login context dùng chung.

### 2.5. Ưu và nhược điểm

**Ưu điểm:**
- Dễ hiểu và dễ cấu hình.
- Có mặt trong nhiều Kafka client và connector.
- Dễ ánh xạ service account thành principal.

**Nhược điểm:**
- Broker phải có nơi lưu password được chấp nhận.
- Client phải bảo vệ password và tránh ghi log.
- Nếu không dùng TLS, credential có thể bị lộ trên mạng.
- Rotation password cần cập nhật đồng bộ broker và client.

PLAIN phù hợp khi có quy trình secret rotation tốt và TLS được thực thi trên mọi kết nối.

## 3. SASL/SCRAM

SCRAM (Salted Challenge Response Authentication Mechanism) xác thực username/password bằng challenge-response. Kafka hỗ trợ:

- SCRAM-SHA-256
- SCRAM-SHA-512

Client không gửi password nguyên bản trong quá trình SASL authentication. Thay vào đó, client và broker trao đổi challenge/proof được tính từ password, salt và số vòng lặp.

SCRAM giảm rủi ro lộ password trong authentication exchange, nhưng không thay thế TLS. TLS vẫn bảo vệ toàn bộ traffic, metadata và chống một số kiểu can thiệp trên đường truyền.

### 3.1. Cách SCRAM hoạt động

Ở mức khái quát:

1. Client gửi username và thông tin khởi tạo.
2. Broker trả challenge có salt và iteration count.
3. Client tính proof từ password và challenge.
4. Broker tính toán và so sánh proof.
5. Hai bên xác nhận authentication thành công hoặc thất bại.

Broker không cần giữ password dạng rõ. Kafka lưu SCRAM credential gồm các thành phần dẫn xuất như salt, stored key và server key.

### 3.2. Cấu hình broker

Bật cơ chế SCRAM:

~~~properties
listeners=EXTERNAL://0.0.0.0:9093
advertised.listeners=EXTERNAL://kafka-1.example.com:9093
listener.security.protocol.map=EXTERNAL:SASL_SSL

sasl.enabled.mechanisms=SCRAM-SHA-512
~~~

Nếu broker-to-broker traffic cũng dùng SCRAM, cấu hình inter-broker listener và mechanism tương ứng. Đảm bảo credential cho principal broker đã được provision trước khi chuyển listener nội bộ sang cơ chế này.

Với cluster mới, credential SCRAM dùng cho inter-broker authentication phải được tạo trước khi broker khởi động lần đầu. Có thể dùng kafka-storage.sh để thêm credential ban đầu khi format KRaft storage; kafka-configs.sh dùng để tạo/cập nhật user khi cluster đã chạy.

### 3.3. Tạo SCRAM credential

Với cluster KRaft, SCRAM credentials được quản lý trong Kafka metadata. Có thể tạo hoặc thay đổi credential bằng kafka-configs.sh:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1.example.com:9093 \
  --alter \
  --add-config 'SCRAM-SHA-512=[iterations=8192,password=replace-with-secret]' \
  --entity-type users \
  --entity-name orders_writer
~~~

Đây là lệnh minh họa. Cần xác thực quyền quản trị trước khi thay đổi user credential. Không dùng password thật trong shell history, script chia sẻ hoặc log CI/CD; dùng secret injection và công cụ provisioning được kiểm soát.

Có thể kiểm tra SCRAM config đã được gắn với user:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1.example.com:9093 \
  --describe \
  --entity-type users \
  --entity-name orders_writer
~~~

Không phải mọi dạng output đều hiển thị password; SCRAM credential không được coi như plaintext password có thể đọc lại.

Với Kafka chạy ZooKeeper ở các phiên bản cũ, cách lưu trữ/provision SCRAM credential có thể khác. Khi migrate ZooKeeper mode sang KRaft, phải theo tài liệu migration của đúng phiên bản thay vì giả định storage path giống nhau.

### 3.4. Cấu hình client SCRAM

Client dùng ScramLoginModule:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required \
  username="orders_writer" \
  password="replace-with-secret";
~~~

Ví dụ Java:

~~~java
Properties props = new Properties();

props.put("bootstrap.servers", "kafka-1.example.com:9093");
props.put("security.protocol", "SASL_SSL");
props.put("sasl.mechanism", "SCRAM-SHA-512");
props.put(
    "sasl.jaas.config",
    "org.apache.kafka.common.security.scram.ScramLoginModule required "
        + "username=\"orders_writer\" "
        + "password=\"" + secretProvider.get("orders-writer-password") + "\";"
);
props.put("ssl.truststore.location", "/etc/kafka/client.truststore.p12");
props.put("ssl.truststore.type", "PKCS12");
~~~

secretProvider là thành phần minh họa của ứng dụng, không phải API Kafka. Không nối secret vào log hoặc exception message. Với hệ thống thực tế, ưu tiên ConfigProvider hoặc secret injection do nền tảng triển khai hỗ trợ.

### 3.5. Chọn SHA-256 hay SHA-512

| Cơ chế | Đặc điểm |
|---|---|
| SCRAM-SHA-256 | Dựa trên SHA-256, tương thích rộng |
| SCRAM-SHA-512 | Dựa trên SHA-512, thường được chọn cho deployment mới nếu mọi client hỗ trợ |

Cần thống nhất mechanism giữa broker listener và client. Một client cấu hình SCRAM-SHA-256 không thể tự xác thực với listener chỉ bật SCRAM-SHA-512.

Iteration count càng cao thì chi phí tính proof càng lớn, làm tăng chi phí brute-force nhưng cũng tăng CPU khi authentication. Chọn giá trị theo threat model và tải kết nối, sau đó benchmark và kiểm thử reconnect storm.

### 3.6. Rotation credential

Có thể tạo credential mới cho service account, cập nhật client, xác nhận kết nối, rồi thu hồi credential cũ theo quy trình của cluster. Nếu username được giữ nguyên, thay đổi password cần phối hợp thời điểm rollout để tránh client cũ và broker không còn cùng credential.

Với yêu cầu zero-downtime, có thể dùng hai principal trong giai đoạn chuyển đổi:
1. Tạo principal mới.
2. Cấp ACL tương đương tối thiểu cần thiết.
3. Rollout client sang principal mới.
4. Xác minh traffic và audit log.
5. Thu hồi principal cũ.

Không giữ nhiều credential cũ vô thời hạn. Gắn owner, mục đích, thời hạn và quy trình thu hồi cho từng service account.

## 4. Kerberos qua SASL/GSSAPI

Kerberos là hệ thống xác thực dựa trên ticket. Client xác thực với Key Distribution Center (KDC), nhận ticket và dùng service ticket để chứng minh danh tính với Kafka broker.

Kafka dùng SASL mechanism GSSAPI để tích hợp Kerberos.

Kerberos thường phù hợp với:
- Hạ tầng doanh nghiệp đã có Active Directory hoặc MIT Kerberos.
- Môi trường Hadoop/data platform tích hợp Kerberos.
- Tổ chức quản lý danh tính tập trung bằng realm và service principal.
- Hệ thống cần SSO và không muốn phân phối password Kafka riêng cho từng ứng dụng.

### 4.1. Các thành phần Kerberos

| Thành phần | Vai trò |
|---|---|
| KDC | Cấp ticket và quản lý principal |
| Realm | Miền quản trị Kerberos |
| Principal | Danh tính của user/service |
| TGT | Ticket Granting Ticket, dùng để xin service ticket |
| Service ticket | Ticket dùng để xác thực với Kafka service |
| Keytab | File chứa key của principal, dùng cho login không tương tác |
| krb5.conf | Cấu hình realm, KDC và mapping hostname |

Ví dụ principal:

~~~text
kafka/kafka-1.example.com@EXAMPLE.COM
orders-producer@EXAMPLE.COM
orders-consumer@EXAMPLE.COM
~~~

Broker principal thường có dạng service/fully-qualified-hostname@REALM. Tên service phải khớp với sasl.kerberos.service.name mà client sử dụng và với principal được provision trong KDC.

### 4.2. Luồng xác thực Kerberos

~~~mermaid
sequenceDiagram
    participant C as Kafka client
    participant K as Kerberos KDC
    participant B as Kafka broker
    C->>K: AS-REQ / xác thực principal
    K-->>C: TGT
    C->>K: TGS-REQ xin ticket cho kafka/host
    K-->>C: Service ticket
    C->>B: SASL GSSAPI exchange
    B-->>C: GSSAPI mutual authentication
    C->>B: Kafka API request
~~~

Client thường dùng keytab hoặc ticket cache để lấy TGT. Sau đó client xin service ticket cho broker và hoàn tất GSSAPI exchange.

### 4.3. Cấu hình Kerberos phía broker

Ví dụ listener nội bộ dùng GSSAPI:

~~~properties
listeners=INTERNAL://0.0.0.0:9092
advertised.listeners=INTERNAL://kafka-1.example.com:9092
listener.security.protocol.map=INTERNAL:SASL_SSL
sasl.enabled.mechanisms=GSSAPI

listener.name.internal.gssapi.sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required \
  useKeyTab=true \
  storeKey=true \
  keyTab="/etc/security/keytabs/kafka-1.keytab" \
  principal="kafka/kafka-1.example.com@EXAMPLE.COM";

sasl.kerberos.service.name=kafka
~~~

Cần tạo principal và keytab tương ứng trên KDC. Mỗi broker thường có principal riêng theo hostname. Đảm bảo file keytab chỉ được đọc bởi user chạy Kafka broker.

### 4.4. Cấu hình client Kerberos

Ví dụ Java client dùng keytab:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=GSSAPI
sasl.kerberos.service.name=kafka
sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required \
  useKeyTab=true \
  storeKey=true \
  keyTab="/etc/security/keytabs/orders-producer.keytab" \
  principal="orders-producer@EXAMPLE.COM";
~~~

Có thể dùng ticket cache thay keytab nếu môi trường cấp ticket qua kinit hoặc SSO. Với service chạy không tương tác, keytab thường dễ tự động hóa hơn nhưng phải được bảo vệ như credential nhạy cảm.

Cấu hình krb5.conf và JVM:

~~~bash
export KRB5_CONFIG=/etc/krb5.conf
kinit -kt /etc/security/keytabs/orders-producer.keytab orders-producer@EXAMPLE.COM
klist
~~~

Trên Windows, đường dẫn và cách cung cấp Kerberos configuration khác theo JVM và domain environment. Không sao chép nguyên đường dẫn Linux vào service Windows.

### 4.5. Những lỗi Kerberos thường gặp

- **Clock skew:** đồng hồ client, broker và KDC lệch nhau quá giới hạn.
- **Unknown principal:** principal chưa tồn tại hoặc sai realm.
- **Server not found in Kerberos database:** service principal không khớp hostname/service name.
- **Keytab mismatch:** keytab cũ sau khi principal key được rotate.
- **DNS canonicalization:** hostname client dùng khác hostname trong service principal.
- **KDC unreachable:** network, firewall hoặc DNS không tới được KDC.
- **Ticket expired:** TGT/service ticket hết hạn hoặc renewal thất bại.

Kerberos phụ thuộc DNS và đồng bộ thời gian rất chặt. Khi debug, kiểm tra hostname thực tế mà client dùng để kết nối, principal broker, realm và key version trong keytab trước khi thay đổi Kafka ACL.

## 5. OAuthBearer qua SASL/OAUTHBEARER

OAuthBearer dùng access token làm bằng chứng xác thực. Token thường do OAuth 2.0 authorization server hoặc OpenID Connect provider cấp. Kafka broker xác minh token và ánh xạ subject/claims thành principal.

OAuthBearer phù hợp khi:
- Tổ chức đã có identity provider.
- Service account dùng OAuth client credentials flow.
- Cần token có thời hạn và khả năng thu hồi/rotate.
- Nhiều ứng dụng cần dùng chung hệ thống identity.
- Cần ánh xạ claims, tenant hoặc audience vào chính sách truy cập.

SASL/OAUTHBEARER chỉ xác thực token. Kafka vẫn cần authorizer/ACL để kiểm tra quyền truy cập topic, group và cluster.

### 5.1. Access token và claims

JWT access token thường có các claim:

| Claim | Ý nghĩa |
|---|---|
| iss | Issuer phát hành token |
| sub | Subject, danh tính được xác thực |
| aud | Audience, dịch vụ được phép nhận token |
| exp | Thời điểm token hết hạn |
| iat | Thời điểm phát hành |
| nbf | Thời điểm token bắt đầu hợp lệ |
| scope hoặc scp | Phạm vi quyền theo hệ thống identity provider |
| client_id | OAuth client đã yêu cầu token, tùy provider |

Broker cần xác minh chữ ký token, issuer, audience, thời hạn và các claim cần thiết theo policy. Không chỉ decode JWT rồi tin vào payload; payload có thể bị giả mạo nếu không kiểm tra chữ ký.

Với opaque token, broker cần introspection hoặc custom validator phù hợp. Cơ chế JWKS validation áp dụng cho JWT có chữ ký và không tự thay thế introspection cho opaque token.

### 5.2. Luồng OAuthBearer

~~~mermaid
sequenceDiagram
    participant C as Kafka client
    participant I as OAuth identity provider
    participant B as Kafka broker
    participant A as Kafka authorizer
    C->>I: Client credentials / token request
    I-->>C: Access token
    C->>B: SASL OAUTHBEARER + bearer token
    B->>I: Lấy JWKS hoặc introspection theo cấu hình
    I-->>B: Public keys / token status
    B-->>C: Authentication success hoặc failure
    C->>B: Kafka API request
    B->>A: Principal + resource + operation
    A-->>B: Allow hoặc Deny
~~~

Client lấy token thông qua JWT retriever được cấu hình; Kafka 4.4 có retriever mặc định hỗ trợ Client Credentials flow với HTTP/HTTPS token endpoint. Broker xác minh token bằng validator callback handler. Có thể thay các thành phần mặc định bằng implementation riêng nếu identity provider yêu cầu flow hoặc policy khác.

### 5.3. Cấu hình client OAuthBearer

Ví dụ cấu hình cơ bản:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=OAUTHBEARER
sasl.jaas.config=org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required;
sasl.oauthbearer.client.credentials.client.id=orders-producer
sasl.oauthbearer.client.credentials.client.secret=replace-with-oauth-client-secret
sasl.oauthbearer.scope=orders.write
sasl.oauthbearer.token.endpoint.url=https://id.example.com/oauth2/token
~~~

Với Kafka 4.4, JWT retriever mặc định dùng Client Credentials flow khi token endpoint là HTTP/HTTPS; có thể cấu hình jwt retriever khác nếu identity provider dùng grant type khác. Các thuộc tính client ID, client secret và scope được tách riêng khỏi JAAS module. Kiểm tra version Kafka client và yêu cầu của identity provider trước khi triển khai.

Client credentials như client secret phải được lấy từ secret manager hoặc ConfigProvider phù hợp. Không đặt secret vào mã nguồn hoặc file cấu hình chia sẻ.

### 5.4. Cấu hình broker xác minh JWT

Broker có thể dùng OAuthBearer validator callback handler tích hợp và JWKS endpoint để xác minh chữ ký JWT:

~~~properties
sasl.enabled.mechanisms=OAUTHBEARER
listener.name.external.oauthbearer.sasl.jaas.config=org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required;
listener.name.external.oauthbearer.sasl.server.callback.handler.class=org.apache.kafka.common.security.oauthbearer.OAuthBearerValidatorCallbackHandler

listener.name.external.oauthbearer.sasl.oauthbearer.jwks.endpoint.url=https://id.example.com/.well-known/jwks.json
listener.name.external.oauthbearer.sasl.oauthbearer.expected.issuer=https://id.example.com/
listener.name.external.oauthbearer.sasl.oauthbearer.expected.audience=kafka-cluster
~~~

Tên property ở trên dùng listener EXTERNAL; thay external bằng tên listener thực tế của cluster. JAAS module có thể được đặt trong listener-prefixed property hoặc KafkaServer section của static JAAS file. JWKS endpoint cung cấp public key để xác minh chữ ký JWT. Broker có thể cache key và refresh theo cấu hình. Khi identity provider rotate signing key, broker cần tải key mới trong thời gian phù hợp.

Khi cấu hình JWKS endpoint, phải cấu hình expected issuer và expected audience. Issuer và audience phải khớp token thực tế. Không bật allow.unverified.issuer hoặc allow.unverified.audience trong production vì token phát cho service khác hoặc issuer không tin cậy có thể bị chấp nhận nhầm vào Kafka.

Một số deployment dùng callback handler riêng để introspect opaque token hoặc thực hiện policy bổ sung. Khi dùng handler tùy chỉnh, kiểm tra source, version, timeout, TLS trust, cache và failure mode.

Nếu cluster dùng OAUTHBEARER cho inter-broker communication, mỗi broker cũng cần lấy access token của chính nó để kết nối broker khác. Cấu hình JWT retriever hoặc login callback handler phù hợp với Kafka version cùng token endpoint/client credential trên inter-broker listener, đồng thời bảo đảm token có issuer và audience mà các broker còn lại chờ đợi. Chỉ cấu hình server-side validator là chưa đủ cho chiều kết nối broker-to-broker.

### 5.5. Cẩn trọng với unsecured OAuthBearer handler

Implementation OAuthBearer mặc định không production của Kafka tạo và xác minh unsecured JWT theo các JAAS claim options. Đây là chế độ dành cho DEV/TEST, không phải xác thực token của identity provider.

Không dùng unsecured JWT mode trong production. Token tự khai báo claim không chứng minh được danh tính của issuer đáng tin cậy. Với Kafka 4.4, dùng JWT retriever cho client credentials hoặc JWT bearer grant, và broker validator cùng JWKS/issuer/audience phù hợp; nếu dùng opaque token thì triển khai validator/introspection handler riêng.

Production phải xác minh token từ identity provider đáng tin, kiểm tra issuer/audience/expiry/signature và bảo vệ token trên đường truyền bằng TLS.

### 5.6. Token expiry, refresh và clock skew

Access token thường có thời hạn ngắn. Client cần JWT retriever hoặc login component có thể lấy token mới trước khi token hiện tại hết hạn theo refresh policy của Kafka client.

Broker cần xử lý:
- Token hết hạn.
- Token chưa tới thời điểm nbf.
- Clock skew giữa broker và issuer.
- JWKS key rotation.
- Identity provider tạm thời unavailable.
- Token endpoint rate limit.
- Token có issuer/audience sai.

Không nên cấp token sống quá dài chỉ để tránh refresh. Hãy dùng access token có thời hạn phù hợp, refresh flow an toàn và monitoring cho lỗi token endpoint.

Kafka client có cơ chế tự refresh token trước khi hết hạn. Các cấu hình như sasl.login.refresh.window.factor, sasl.login.refresh.window.jitter, sasl.login.refresh.min.period.seconds và sasl.login.refresh.min.buffer.seconds điều khiển lịch refresh; chỉ điều chỉnh sau khi đo và xác định default không phù hợp.

## 6. So sánh bốn cơ chế

| Tiêu chí | PLAIN | SCRAM | Kerberos/GSSAPI | OAuthBearer |
|---|---|---|---|---|
| Credential | Username/password | Username/password + SCRAM credential | Ticket và principal | Access token |
| Exchange | PLAIN authentication payload | Challenge-response | GSSAPI ticket exchange | Bearer token |
| Password gửi trực tiếp | Có trong SASL exchange; cần TLS | Không gửi password nguyên bản | Không gửi password Kafka | Không gửi password Kafka |
| Hạ tầng phụ thuộc | Broker credential config | Kafka SCRAM credential store | KDC/AD, DNS, time sync | OAuth/OIDC provider |
| Vòng đời | Password rotation | SCRAM credential rotation | Keytab/ticket renewal | Token expiry/refresh |
| Điểm mạnh | Đơn giản, dễ tích hợp | Challenge-response, không lưu password rõ | SSO và identity tập trung | Token ngắn hạn, tích hợp identity provider |
| Điểm cần chú ý | Bảo vệ password và TLS | Provision credential, iteration, TLS | DNS, principal, KDC, clock | Callback handler, token validation, JWKS/introspection |

### 6.1. Chọn cơ chế theo môi trường

- **PLAIN:** lab hoặc hệ thống nhỏ có TLS và secret management chặt.
- **SCRAM:** service account Kafka-native, muốn xác thực password theo challenge-response và quản lý credential trong cluster.
- **Kerberos:** tổ chức đã có Active Directory/KDC và quy trình quản trị principal/keytab.
- **OAuthBearer:** hệ thống có OAuth 2.0/OIDC identity provider và cần token-based authentication.

Không có cơ chế nào thay thế authorization. Dù dùng PLAIN, SCRAM, Kerberos hay OAuthBearer, vẫn phải cấp ACL theo nguyên tắc least privilege.

## 7. Cấu hình broker nhiều cơ chế và listener

Một cluster có thể bật nhiều SASL mechanism, nhưng nên giới hạn cơ chế theo listener và nhóm client để giảm bề mặt tấn công.

Ví dụ minh họa:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,EXTERNAL://0.0.0.0:9093
advertised.listeners=INTERNAL://kafka-1.internal:9092,EXTERNAL://kafka-1.example.com:9093
listener.security.protocol.map=INTERNAL:SASL_SSL,EXTERNAL:SASL_SSL
inter.broker.listener.name=INTERNAL

listener.name.internal.sasl.enabled.mechanisms=SCRAM-SHA-512
listener.name.external.sasl.enabled.mechanisms=PLAIN,OAUTHBEARER

sasl.mechanism.inter.broker.protocol=SCRAM-SHA-512
~~~

Đây là cấu hình định hướng. Từng mechanism cần credential/JAAS/callback handler riêng và TLS keystore/truststore phù hợp. Không sao chép một JAAS stanza cho tất cả listener nếu principal khác nhau.

Với Kerberos, có thể cấu hình listener chỉ bật GSSAPI và JAAS broker principal tương ứng. Với OAuthBearer, cần cấu hình callback handler trên đúng listener/broker và trust cho JWKS/token endpoint.

### 7.1. Listener-prefixed JAAS

Đối với cơ chế cần JAAS, có thể khai báo JAAS config theo listener và mechanism:

~~~properties
listener.name.external.plain.sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required \
  user_orders_writer="replace-with-secret";

listener.name.internal.gssapi.sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required \
  useKeyTab=true \
  storeKey=true \
  keyTab="/etc/security/keytabs/kafka.keytab" \
  principal="kafka/kafka-1.example.com@EXAMPLE.COM";
~~~

Tên prefix phải dùng lowercase listener name và mechanism name theo quy tắc Kafka. Kiểm tra chính xác tên property với Kafka version đang chạy.

### 7.2. Inter-broker authentication

Nếu broker-to-broker traffic dùng SASL, phải cấu hình mechanism, principal/credential và protocol cho inter-broker listener. Mọi broker phải có cấu hình tương thích.

Một lỗi phổ biến là client bên ngoài kết nối được nhưng broker không thể trao đổi metadata/replication vì inter-broker principal chưa được provision hoặc listener nội bộ không bật mechanism tương ứng.

Thực hiện rollout bảo mật cluster theo từng bước và theo hướng dẫn của Kafka version. Không đổi inter-broker protocol trên toàn cluster khi chưa có đường kết nối tương thích cho tất cả broker.

## 8. Authorization bằng ACL sau khi authentication

Sau khi authentication, Kafka tạo principal. Với các cơ chế SASL, principal thường có dạng User:principal-name, nhưng có thể được tùy chỉnh bằng principal builder hoặc mapping rule.

Ví dụ producer orders_writer cần ghi topic orders:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.com:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders_writer \
  --operation Write \
  --operation Describe \
  --topic orders
~~~

Consumer orders_reader cần đọc topic và group:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.com:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders_reader \
  --operation Read \
  --operation Describe \
  --topic orders

kafka-acls.sh \
  --bootstrap-server kafka-1.example.com:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders_reader \
  --operation Read \
  --group orders-consumer-group
~~~

Ví dụ là ACL tối thiểu minh họa. Một ứng dụng có thể cần thêm quyền trên transactional ID, consumer group, cluster hoặc internal topics tùy chức năng. Cấp đúng resource và operation cần thiết; tránh cấp All hoặc wildcard rộng nếu không có lý do.

### 8.1. Principal mapping

Kerberos principal có thể chứa service, hostname và realm. OAuth token có thể chứa subject dạng URI hoặc ID dài. Nếu dùng trực tiếp toàn bộ chuỗi làm Kafka principal, ACL sẽ khó quản lý.

Có thể dùng principal builder/mapping để chuẩn hóa danh tính, ví dụ ánh xạ orders-producer@EXAMPLE.COM thành User:orders-producer. Quy tắc mapping phải duy nhất và tránh làm hai identity khác nhau thành cùng một principal.

Với OAuthBearer, cần quyết định claim nào đại diện principal: sub, client ID hay claim tùy chỉnh. Không dùng scope như principal nếu scope chỉ mô tả quyền; principal nên định danh actor.

## 9. Cấu hình TLS cho SASL_SSL

SASL_SSL yêu cầu TLS certificate và trust chain hợp lệ.

Ví dụ client properties:

~~~properties
security.protocol=SASL_SSL
ssl.truststore.location=/etc/kafka/secrets/client.truststore.p12
ssl.truststore.password=replace-with-truststore-secret
ssl.truststore.type=PKCS12
ssl.endpoint.identification.algorithm=https
~~~

Nếu broker yêu cầu mutual TLS, client còn cần keystore chứa client certificate và private key:

~~~properties
ssl.keystore.location=/etc/kafka/secrets/client.keystore.p12
ssl.keystore.password=replace-with-keystore-secret
ssl.key.password=replace-with-private-key-secret
ssl.keystore.type=PKCS12
~~~

Mutual TLS có thể bổ sung xác thực certificate ở tầng TLS cùng SASL, nhưng cần hiểu rõ principal mapping và authorization. Không giả định client certificate tự động thay thế SASL username/token.

Các điểm cần kiểm tra:
- Certificate chưa hết hạn.
- SAN chứa hostname broker trong advertised.listeners.
- Truststore chứa CA chain đúng.
- Private key được bảo vệ.
- Broker và client thống nhất TLS version/cipher theo policy.
- Không tắt hostname verification để né lỗi certificate.

## 10. Cấu hình client dùng chung cho Producer và Consumer

Có thể dùng chung các thuộc tính security cơ bản cho KafkaProducer và KafkaConsumer:

~~~java
Properties securityProps = new Properties();

securityProps.put("bootstrap.servers", "kafka-1.example.com:9093");
securityProps.put("security.protocol", "SASL_SSL");
securityProps.put("sasl.mechanism", "SCRAM-SHA-512");
securityProps.put(
    "ssl.truststore.location",
    "/etc/kafka/secrets/client.truststore.p12"
);
securityProps.put("ssl.truststore.type", "PKCS12");
~~~

Producer:

~~~java
Properties producerProps = new Properties();
producerProps.putAll(securityProps);
producerProps.put(
    "sasl.jaas.config",
    "org.apache.kafka.common.security.scram.ScramLoginModule required "
        + "username=\"orders_writer\" "
        + "password=\"__ORDERS_WRITER_PASSWORD_FROM_SECRET_PROVIDER__\";"
);
producerProps.put(
    ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class
);
producerProps.put(
    ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class
);

KafkaProducer<String, String> producer =
    new KafkaProducer<>(producerProps);
~~~

Consumer:

~~~java
Properties consumerProps = new Properties();
consumerProps.putAll(securityProps);
consumerProps.put(
    "sasl.jaas.config",
    "org.apache.kafka.common.security.scram.ScramLoginModule required "
        + "username=\"orders_reader\" "
        + "password=\"__ORDERS_READER_PASSWORD_FROM_SECRET_PROVIDER__\";"
);
consumerProps.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
consumerProps.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
consumerProps.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "orders-consumer-group"
);

KafkaConsumer<String, String> consumer =
    new KafkaConsumer<>(consumerProps);
~~~

Trong thực tế producer và consumer nên dùng principal riêng vì quyền của chúng khác nhau. Không dùng cùng một credential chỉ để tiện cấu hình.

## 11. Bảo vệ credential và rotation

Credential là tài sản bảo mật. Việc dùng SASL mechanism đúng vẫn không an toàn nếu secret bị commit vào Git, in ra log hoặc cấp quyền quá rộng.

### 11.1. Không hard-code secret

Tránh:
- Đưa password vào source code.
- Commit JAAS file chứa password.
- Ghi token vào log.
- Truyền secret qua command line trong CI nếu hệ thống lưu process arguments.
- Chia sẻ cùng một service account cho nhiều ứng dụng không liên quan.
- Dùng một credential admin cho producer/consumer thông thường.

Nên:
- Dùng secret manager hoặc Kafka ConfigProvider.
- Phân quyền đọc secret theo workload identity.
- Giới hạn quyền file keytab, keystore và truststore.
- Che secret trong CI/CD logs.
- Audit việc đọc và thay đổi credential.
- Có quy trình revoke và rotate khi nhân sự/service thay đổi.

### 11.2. Rotation theo cơ chế

| Cơ chế | Thành phần cần rotate |
|---|---|
| PLAIN | Password ở broker và client |
| SCRAM | SCRAM credential trong Kafka và password client |
| Kerberos | Keytab/principal key và ticket renewal |
| OAuthBearer | Client secret/certificate nếu dùng client credentials; token được refresh theo expiry; signing key/JWKS được rotate ở issuer |

Với OAuthBearer, phân biệt client credential và access token. Client secret dùng để xin token; access token dùng trong SASL authentication. Không lưu token lâu dài nếu có thể xin token mới an toàn.

### 11.3. Quy trình rotation an toàn

1. Xác định owner và tất cả client đang dùng credential.
2. Tạo credential mới hoặc principal mới.
3. Cấp ACL đúng phạm vi.
4. Triển khai client theo từng nhóm.
5. Xác nhận authentication và API authorization.
6. Theo dõi lỗi login, reconnect và request denied.
7. Thu hồi credential cũ sau khi không còn client sử dụng.
8. Cập nhật inventory và thời điểm rotation tiếp theo.

Không thu hồi credential cũ trước khi xác nhận rollout mới đã hoàn tất, trừ trường hợp xử lý incident cần revoke ngay.

## 12. Kafka Connect và Kafka Streams dùng SASL

Kafka Connect worker và Kafka Streams application đều là Kafka clients. Chúng cần security config cho mọi kết nối Kafka mà chúng tạo ra.

### 12.1. Kafka Connect

Worker có thể dùng SASL_SSL/SCRAM:

~~~properties
bootstrap.servers=kafka-1.example.com:9093,kafka-2.example.com:9093
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required \
  username="connect_worker" \
  password="replace-with-connect-secret";

ssl.truststore.location=/etc/kafka/secrets/connect.truststore.p12
ssl.truststore.type=PKCS12
~~~

Connector có thể tạo Kafka producer/consumer riêng hoặc dùng connector-specific client overrides. Cần kiểm tra connector nào kế thừa worker security config và connector nào cần cấu hình riêng.

Không đưa password vào connector config REST API nếu config được lưu trong topic và có thể truy cập bởi nhiều operator. Dùng ConfigProvider/secret management được Kafka Connect deployment hỗ trợ.

### 12.2. Kafka Streams

Kafka Streams dùng cấu hình security tương tự:

~~~java
Properties props = new Properties();

props.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "order-analytics"
);
props.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "kafka-1.example.com:9093,kafka-2.example.com:9093"
);
props.put("security.protocol", "SASL_SSL");
props.put("sasl.mechanism", "SCRAM-SHA-512");
props.put(
    "sasl.jaas.config",
    "org.apache.kafka.common.security.scram.ScramLoginModule required "
        + "username=\"streams_order_analytics\" "
        + "password=\"__STREAMS_PASSWORD_FROM_SECRET_PROVIDER__\";"
);
props.put(
    "ssl.truststore.location",
    "/etc/kafka/secrets/streams.truststore.p12"
);
~~~

Principal của Kafka Streams thường cần quyền trên input topics, output topics, consumer group/application ID, internal repartition/changelog topics và transactional IDs nếu bật exactly-once. Dùng ACL phù hợp với topology và version.

## 13. Kiểm tra kết nối và troubleshooting

Khi SASL login thất bại, phân loại lỗi trước khi thay đổi cấu hình.

### 13.1. Authentication failed

Triệu chứng:
- SaslAuthenticationException.
- Authentication failed.
- Invalid username or password.
- Unsupported SASL mechanism.

Kiểm tra:
1. security.protocol có đúng SASL_SSL không?
2. Client và listener có cùng sasl.mechanism không?
3. Broker listener có bật mechanism không?
4. Username/password hoặc credential có chính xác không?
5. JAAS module class có đúng với mechanism không?
6. SCRAM credential đã được tạo chưa?
7. Kerberos principal/keytab/ticket còn hợp lệ không?
8. OAuth token có signature, issuer, audience và expiry hợp lệ không?

### 13.2. SSL handshake failed

Triệu chứng:
- SSLHandshakeException.
- PKIX path building failed.
- Hostname verification failed.
- Certificate expired.

Kiểm tra:
- Truststore có CA chain đúng không?
- Broker certificate có SAN khớp hostname advertised không?
- Certificate có hết hạn hoặc bị revoke không?
- Client có dùng đúng truststore path/type không?
- TLS version và cipher có tương thích không?

Không đổi security.protocol về SASL_PLAINTEXT để bỏ qua lỗi certificate trong production.

### 13.3. Authentication thành công nhưng authorization bị từ chối

Triệu chứng:
- TopicAuthorizationException.
- GroupAuthorizationException.
- ClusterAuthorizationException.
- TransactionalIdAuthorizationException.

Điều này thường có nghĩa SASL authentication đã thành công, nhưng principal thiếu ACL. Kiểm tra principal thực tế, topic/group/transactional ID và operation đang bị từ chối.

Không sửa bằng cách cấp quyền All trên toàn cluster nếu chưa xác định resource cần thiết.

### 13.4. Kerberos-specific troubleshooting

~~~bash
klist
kvno kafka/kafka-1.example.com@EXAMPLE.COM
kinit -kt /etc/security/keytabs/orders-producer.keytab orders-producer@EXAMPLE.COM
~~~

Các lệnh trên giúp kiểm tra ticket cache, xin service ticket và login bằng keytab. Thay principal/hostname theo môi trường.

Kiểm tra DNS forward/reverse, đồng hồ NTP, KDC reachability, krb5.conf, keytab permission và service principal của từng broker.

### 13.5. OAuth-specific troubleshooting

Kiểm tra:
- Token endpoint có truy cập được từ client không?
- JWKS endpoint có truy cập được từ broker không?
- Token signature có dùng key hiện tại không?
- iss và aud có khớp không?
- exp và nbf có hợp lệ không?
- Clock skew có nằm trong policy không?
- Callback handler có đúng class/version không?
- Token endpoint có rate limit hoặc lỗi TLS không?
- Principal được tạo từ claim nào?

Không log raw bearer token để debug. Có thể log issuer, key ID, expiry, request correlation ID và principal sau khi đã loại bỏ thông tin nhạy cảm.

## 14. Kiểm thử bằng Kafka CLI

Có thể dùng --command-config để cung cấp client security properties cho các công cụ Kafka.

Ví dụ client-scram.properties:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required \
  username="orders_reader" \
  password="replace-with-reader-secret";
ssl.truststore.location=/etc/kafka/secrets/client.truststore.p12
ssl.truststore.type=PKCS12
~~~

File client-scram-writer.properties dùng cùng TLS/mechanism nhưng thay username/password bằng principal writer:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required \
  username="orders_writer" \
  password="replace-with-writer-secret";
ssl.truststore.location=/etc/kafka/secrets/client.truststore.p12
ssl.truststore.type=PKCS12
~~~

Đọc topic:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka-1.example.com:9093 \
  --topic orders \
  --group orders-debug \
  --from-beginning \
  --consumer.config client-scram.properties
~~~

Gửi record:

~~~bash
kafka-console-producer.sh \
  --bootstrap-server kafka-1.example.com:9093 \
  --topic orders \
  --producer.config client-scram-writer.properties
~~~

File client-scram-writer.properties phải dùng principal có quyền Write trên topic; không tái sử dụng credential reader trong ví dụ consumer.

Không dùng credential production trong file test nằm ở thư mục chia sẻ hoặc máy cá nhân không được quản lý. Xóa/thu hồi file và credential sau khi hoàn tất lab.

## 15. Production hardening checklist

| Hạng mục | Câu hỏi |
|---|---|
| Listener | Listener nội bộ và bên ngoài có được tách biệt không? |
| Protocol | Mọi listener không tin cậy có dùng SASL_SSL không? |
| Mechanism | Chỉ bật SASL mechanism cần thiết không? |
| Authentication | Credential/token/keytab có được cấp theo service identity riêng không? |
| Authorization | ACL có theo least privilege cho topic, group, cluster và transactional ID không? |
| TLS | Certificate, trust chain, hostname verification và rotation có được quản lý không? |
| Secret storage | Password, client secret và keytab có nằm ngoài source control không? |
| PLAIN | Có bắt buộc TLS và có rotation password không? |
| SCRAM | Credential đã provision, iteration phù hợp và có rotation plan chưa? |
| Kerberos | KDC, DNS, NTP, principal và keytab có được giám sát không? |
| OAuth | Token signature, issuer, audience, expiry và JWKS refresh có được xác minh không? |
| Principal mapping | Mapping không làm trùng identity khác nhau chứ? |
| Inter-broker | Broker-to-broker authentication có hoạt động sau rollout không? |
| Connect/Streams | Internal topics, consumer groups và transactional IDs có ACL phù hợp không? |
| Monitoring | Có metric authentication failure, authorization denied và token renewal failure không? |
| Incident response | Có quy trình revoke credential và audit log không? |

## 16. Các anti-pattern thường gặp

- **Dùng SASL_PLAINTEXT trên mạng production:** credential/token có thể bị nghe lén.
- **Dùng PLAIN nhưng nghĩ password đã được mã hóa:** PLAIN không tự mã hóa payload.
- **Dùng một tài khoản cho mọi service:** khó audit và khó revoke đúng phạm vi.
- **Cấp ACL wildcard quá rộng:** một service compromise có thể ảnh hưởng toàn cluster.
- **Commit JAAS file có secret:** credential có thể tồn tại lâu trong Git history.
- **Đưa bearer token vào log:** người có log access có thể dùng token trước khi hết hạn.
- **Dùng OAuth unsecured handler trong production:** token claim không được xác minh bởi issuer tin cậy.
- **Không kiểm tra audience:** token dành cho service khác có thể được chấp nhận nhầm.
- **Dùng keytab chung cho mọi broker:** khó rotate và tăng phạm vi ảnh hưởng khi lộ key.
- **Bỏ qua DNS/time sync với Kerberos:** authentication lỗi dù password/keytab tưởng như đúng.
- **Chỉ test authentication:** producer/consumer vẫn có thể fail vì ACL thiếu.
- **Đổi inter-broker protocol đồng loạt không có rollout plan:** broker có thể mất kết nối replication/control plane.

## 17. Quy trình chọn và triển khai SASL

1. Xác định identity provider và cách cấp danh tính cho workload.
2. Xác định client types: Java producer/consumer, Connect, Streams, CLI và broker.
3. Chọn mechanism phù hợp: PLAIN, SCRAM, GSSAPI hoặc OAUTHBEARER.
4. Thiết kế listener và yêu cầu TLS.
5. Provision broker credential, SCRAM user, Kerberos principal/keytab hoặc OAuth client/provider.
6. Cấu hình broker listener và inter-broker authentication nếu cần.
7. Cấu hình client JAAS/callback handler và TLS trust.
8. Cấp ACL tối thiểu cho principal.
9. Kiểm thử authentication riêng với authorization.
10. Kiểm thử reconnect, rotation, broker restart và identity provider outage.
11. Bật monitoring và audit log.
12. Triển khai theo từng nhóm client và giữ phương án rollback.

Không chuyển cơ chế xác thực của toàn cluster trong một lần nếu chưa xác minh từng broker và từng loại client tương thích.

## 18. Kết luận

SASL/PLAIN, SASL/SCRAM, Kerberos và OAuthBearer đều giúp Kafka xác thực client nhưng dùng credential và hạ tầng khác nhau. PLAIN đơn giản nhưng phải luôn đi cùng TLS; SCRAM dùng challenge-response và credential được quản lý trong Kafka; Kerberos dựa trên KDC, principal, ticket và keytab; OAuthBearer dùng access token cần xác minh chữ ký, issuer, audience và thời hạn.

Sau khi xác thực, Kafka vẫn kiểm tra authorization bằng principal và ACL. Vì vậy, một triển khai production phải thiết kế đồng thời listener, TLS, SASL mechanism, credential lifecycle, principal mapping, ACL và quy trình rotation.

Hãy bắt đầu từ identity provider đang có, chọn cơ chế phù hợp với workload, cấp quyền tối thiểu, kiểm thử cả authentication lẫn authorization và giám sát quá trình refresh/rotation. Một kết nối SASL chỉ an toàn khi credential được bảo vệ từ lúc cấp phát đến lúc thu hồi.

## Tài liệu tham khảo

- Apache Kafka Security: https://kafka.apache.org/44/security/security-overview/
- Apache Kafka SASL Authentication: https://kafka.apache.org/44/security/authentication-using-sasl/
- Apache Kafka Encryption and SSL: https://kafka.apache.org/44/security/encryption-and-authentication-using-ssl/
- Apache Kafka Authorization and ACLs: https://kafka.apache.org/44/security/authorization-and-acls/
- Apache Kafka OAuthBearer API: https://kafka.apache.org/44/javadoc/org/apache/kafka/common/security/oauthbearer/package-summary.html
