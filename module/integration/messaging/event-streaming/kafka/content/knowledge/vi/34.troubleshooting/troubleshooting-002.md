# Lỗi TLS, SASL và phân quyền theo topic hoặc group

## Mục tiêu

Khi một Java/Spring Kafka application không kết nối được broker hoặc nhận lỗi khi produce/consume, nguyên nhân thường nằm ở một trong ba tầng bảo mật:

1. **TLS** thiết lập kênh mã hóa, xác minh chứng chỉ broker và có thể xác thực client bằng certificate.
2. **SASL** xác thực danh tính client bằng cơ chế như SCRAM, PLAIN, Kerberos hoặc OAuth.
3. **ACL** quyết định principal đã xác thực được phép thực hiện thao tác nào trên topic, consumer group, cluster hoặc transactional ID.

Ba tầng này có thể được bật độc lập hoặc kết hợp. Ví dụ SASL_SSL dùng TLS để mã hóa đường truyền và SASL để xác thực username/token. SSL client authentication có thể dùng certificate để xác thực client. ACL là bước authorization sau khi broker đã xác định principal.

Một lỗi TLS handshake không được xử lý bằng cách thêm ACL. Một lỗi SASL authentication không được xử lý bằng cách cấp quyền WRITE trên topic. Một lỗi authorization cũng không được xử lý bằng cách thay truststore nếu certificate chain đã hợp lệ.

Sau bài học, bạn có thể:

- Phân biệt TLS handshake, SASL authentication và ACL authorization.
- Đọc log và phân loại lỗi theo tầng transport, authentication hoặc authorization.
- Chẩn đoán truststore, keystore, certificate chain, SAN, hostname verification và mutual TLS.
- Chẩn đoán sai SASL mechanism, JAAS login module, username/password, SCRAM, Kerberos và OAuth.
- Xác định Kafka principal thực tế mà broker nhìn thấy.
- Kiểm tra ACL theo principal, host, operation, resource và resource pattern.
- Cấp quyền tối thiểu cho producer, consumer, consumer group và transactional producer.
- Cấu hình SSL/SASL trong Java Kafka client và Spring Boot.
- Dùng Kafka CLI để kiểm tra kết nối và liệt kê ACL có hiệu lực.
- Xây dựng quy trình xử lý sự cố có thể tái lập mà không mở quyền quá rộng.

## 1. Phân biệt ba tầng bảo mật

### 1.1. Luồng kết nối

~~~mermaid
sequenceDiagram
    participant C as Kafka Client
    participant T as TLS Layer
    participant S as SASL Layer
    participant B as Kafka Broker
    participant A as Authorizer / ACL

    C->>T: TCP connect và TLS ClientHello
    T->>C: Certificate, handshake và encrypted channel
    C->>S: SASL handshake/authenticate nếu dùng SASL
    S->>B: Xác thực credential/token
    B->>A: Tạo principal và kiểm tra operation/resource
    A-->>B: Allow hoặc Deny
    B-->>C: API response hoặc authorization error
~~~

Thứ tự thực tế phụ thuộc security protocol:

- PLAINTEXT: không có TLS và không có SASL.
- SSL: TLS mã hóa kết nối; broker có thể yêu cầu client certificate để xác thực mTLS.
- SASL_PLAINTEXT: SASL authentication trên kết nối không mã hóa.
- SASL_SSL: TLS mã hóa kết nối và SASL xác thực client.

Trong production, ưu tiên SSL hoặc SASL_SSL. SASL/PLAIN và SCRAM nên được dùng trên TLS để tránh lộ credential hoặc dữ liệu xác thực trên đường truyền.

### 1.2. Bảng phân loại nhanh

| Tầng | Câu hỏi | Dấu hiệu lỗi thường gặp |
|---|---|---|
| Network/listener | Client có tới đúng broker endpoint không? | Connection refused, timeout, no route, wrong port |
| TLS | Client có tin certificate và hostname broker không? | SSLHandshakeException, PKIX path building failed, SAN mismatch |
| SASL | Broker có xác thực được client không? | SaslAuthenticationException, invalid credentials, unsupported mechanism |
| ACL | Principal có quyền trên resource và operation không? | TopicAuthorizationException, GroupAuthorizationException |
| Client config | Producer/consumer có dùng đúng security properties không? | Một client hoạt động, client khác lỗi; AdminClient lỗi riêng |

### 1.3. Nguyên tắc điều tra

1. Ghi lại bootstrap server, listener/port, security.protocol và SASL mechanism đang dùng.
2. Xác nhận DNS, route và TCP tới từng broker endpoint mà cluster quảng bá.
3. Kiểm tra TLS trước khi thay đổi SASL hoặc ACL.
4. Xác nhận principal broker đã nhận sau authentication.
5. Liệt kê ACL theo resource pattern có thể match, không chỉ ACL literal.
6. Cấp đúng operation trên đúng topic/group.
7. Thử lại bằng CLI với cùng client properties, sau đó mới kiểm tra Spring application.

Không dùng một tài khoản admin để thử toàn bộ ứng dụng. Nếu admin kết nối được nhưng service account không kết nối được, phải xác định phần khác nhau trong certificate, credential, principal hoặc ACL.

## 2. Chẩn đoán network và listener trước TLS

### 2.1. Kiểm tra bootstrap và advertised.listeners

bootstrap.servers chỉ là danh sách địa chỉ ban đầu để client tìm cluster metadata. Sau đó client kết nối tới các broker endpoint được trả về từ metadata.

Vì vậy, có thể xảy ra tình huống:

- Client kết nối được bootstrap broker.
- Broker trả về advertised.listeners chứa hostname nội bộ hoặc IP không truy cập được từ client.
- Client thất bại khi kết nối partition leader hoặc coordinator ở broker khác.

Kiểm tra:

- DNS resolve hostname của tất cả broker advertised.
- Port tương ứng với listener mà client được phép dùng.
- Firewall/security group cho phép client tới từng broker.
- advertised.listeners chứa FQDN/IP có trong certificate SAN.
- Client không dùng controller listener làm bootstrap endpoint cho traffic producer/consumer thông thường.

Lệnh kiểm tra TCP trên Linux:

~~~bash
nc -vz broker1.example.com 9093
~~~

Trên Windows PowerShell:

~~~powershell
Test-NetConnection broker1.example.com -Port 9093
~~~

Nếu TCP chưa thông, chưa cần thay truststore hoặc cấp ACL.

### 2.2. Nhận biết sai listener hoặc sai port

Các listener có thể dùng security protocol khác nhau. Ví dụ:

| Listener | Port | Protocol |
|---|---:|---|
| INTERNAL | 9092 | PLAINTEXT hoặc SASL_PLAINTEXT |
| CLIENT | 9093 | SASL_SSL |
| CONTROLLER | 9094 | SSL hoặc SASL_SSL tùy cấu hình cluster |

Bảng chỉ là ví dụ. Phải đối chiếu listener.security.protocol.map và advertised.listeners của cluster thực tế.

Nếu client gửi TLS ClientHello tới PLAINTEXT port hoặc gửi Kafka plaintext tới SSL port, log thường có lỗi handshake hoặc thông báo dữ liệu không đúng protocol. Hãy xác nhận port trước khi chỉnh certificate.

## 3. Chẩn đoán TLS và certificate

### 3.1. Truststore và keystore khác nhau

| Thành phần | Chứa gì | Dùng khi nào |
|---|---|---|
| Truststore | Certificate CA hoặc certificate mà client tin cậy | Client xác minh certificate của broker |
| Keystore | Private key và certificate chain của chính client | Client chứng minh danh tính khi broker yêu cầu mTLS |
| Broker keystore | Private key và certificate của broker | Broker cung cấp certificate trong TLS handshake |
| Broker truststore | CA dùng để tin client certificate | Broker xác minh client khi bật mTLS |

Với TLS một chiều thông thường, client cần truststore để tin broker. Client chỉ cần keystore nếu broker yêu cầu client certificate hoặc hệ thống dùng mTLS.

Không import private key của broker vào client truststore. Truststore chỉ cần CA/certificate công khai cần tin; private key phải được bảo vệ trong keystore của chủ sở hữu.

### 3.2. Lỗi PKIX path building failed

Thông báo thường thấy:

~~~text
javax.net.ssl.SSLHandshakeException
sun.security.validator.ValidatorException:
PKIX path building failed
unable to find valid certification path to requested target
~~~

Nguyên nhân thường gặp:

- Client truststore chưa có CA ký certificate broker.
- Thiếu intermediate CA trong certificate chain mà broker gửi.
- Client đang dùng nhầm truststore hoặc sai file path.
- Truststore password/type không đúng nên file không được load.
- Certificate broker được ký bởi CA mới nhưng client chưa cập nhật truststore.
- Client truststore chứa certificate cũ đã hết hạn hoặc bị thay thế.

Cách kiểm tra:

1. Xác nhận file truststore mà process thực sự đọc.
2. Liệt kê certificate trong truststore.
3. Kiểm tra issuer/subject của certificate broker.
4. Xác nhận chuỗi từ broker certificate tới CA gốc được tin cậy.
5. Cập nhật truststore bằng CA certificate hợp lệ và triển khai lại client.

Liệt kê truststore PKCS12:

~~~bash
keytool -list -v -keystore client.truststore.p12 -storetype PKCS12
~~~

Kiểm tra certificate server:

~~~bash
openssl s_client -connect broker1.example.com:9093 -servername broker1.example.com -showcerts -verify_return_error
~~~

Không tắt certificate validation để chữa lỗi PKIX. Hãy sửa trust chain hoặc truststore.

### 3.3. Lỗi hostname hoặc SAN mismatch

Ví dụ:

~~~text
SSLHandshakeException:
No subject alternative DNS name matching broker1.example.com found
~~~

TLS hostname verification kiểm tra hostname client dùng để kết nối có khớp với Subject Alternative Name (SAN) trong certificate broker hay không.

Nguyên nhân:

- Client dùng alias DNS không có trong SAN.
- advertised.listeners trả hostname khác hostname trong certificate.
- Client kết nối bằng IP nhưng certificate chỉ có DNS SAN.
- Certificate được cấp trước khi đổi tên broker.
- Certificate signing request có SAN nhưng CA không copy SAN vào certificate cuối.

Cách xử lý:

1. Ghi chính xác hostname client kết nối sau khi nhận metadata.
2. Kiểm tra SAN trong certificate được broker gửi.
3. Cấp lại certificate có DNS SAN/IP SAN phù hợp.
4. Cập nhật advertised.listeners để dùng endpoint đã được certificate bao phủ.
5. Kiểm tra lại tất cả broker, không chỉ bootstrap broker.

Kiểm tra SAN và thời hạn:

~~~bash
openssl x509 -in broker.crt -noout -dates -ext subjectAltName
~~~

Hostname verification được bật mặc định cho Kafka client từ Kafka 2.0. Không đặt ssl.endpoint.identification.algorithm thành chuỗi rỗng trong production để bỏ qua SAN mismatch. Việc này làm giảm khả năng chống man-in-the-middle.

### 3.4. Certificate hết hạn hoặc chưa có hiệu lực

Dấu hiệu:

- Certificate expired.
- Certificate not yet valid.
- TLS handshake đột nhiên lỗi sau một đợt rotate certificate.

Kiểm tra:

- notBefore và notAfter.
- Đồng hồ hệ thống và NTP trên broker/client.
- Certificate chain sau rotate.
- Tất cả broker đã nhận certificate mới chưa.
- Client truststore có CA mới chưa.

Đồng hồ lệch có thể khiến certificate hợp lệ bị xem là chưa có hiệu lực hoặc đã hết hạn.

### 3.5. Lỗi mTLS: broker yêu cầu client certificate

Dấu hiệu:

- Broker log báo client certificate required.
- TLS handshake thất bại với bad_certificate hoặc certificate_unknown.
- Client kết nối được ở môi trường không bật mTLS nhưng lỗi ở production.

Kiểm tra:

- Broker có ssl.client.auth=required không.
- Client có keystore đúng không.
- Keystore có private key và certificate chain hay chỉ có certificate công khai.
- Certificate client có Client Authentication Extended Key Usage nếu CA profile giới hạn usage.
- Broker truststore có CA ký client certificate không.
- Certificate chưa hết hạn và private key khớp certificate.

Client properties ví dụ khi broker yêu cầu mTLS:

~~~properties
security.protocol=SSL
ssl.truststore.location=/etc/kafka/client.truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=${KAFKA_TRUSTSTORE_PASSWORD}

ssl.keystore.location=/etc/kafka/client.keystore.p12
ssl.keystore.type=PKCS12
ssl.keystore.password=${KAFKA_KEYSTORE_PASSWORD}
ssl.key.password=${KAFKA_KEY_PASSWORD}
~~~

Nếu dùng SASL_SSL và mTLS đồng thời, vẫn cần các ssl.keystore properties cùng sasl.mechanism và sasl.jaas.config.

### 3.6. Certificate chain và Extended Key Usage

Trong một số môi trường enterprise, CA ký certificate nhưng bỏ intermediate certificate hoặc chỉ cấp Extended Key Usage cho serverAuth. Khi broker giao tiếp nội bộ với broker khác, mỗi broker vừa đóng vai client vừa đóng vai server; certificate profile cần cho phép đúng mục đích sử dụng.

Khi TLS handshake giữa broker thất bại nhưng client application vẫn kết nối được, kiểm tra cả inter-broker listener, truststore và certificate usage của broker.

### 3.7. TLS protocol/cipher không tương thích

Dấu hiệu:

- No appropriate protocol.
- No cipher suites in common.
- Protocol version alert.

Kiểm tra:

- ssl.enabled.protocols phía broker và ssl.protocol/ssl.enabled.protocols phía client.
- Phiên bản Java/JDK và security provider.
- Cipher suite policy của JVM.
- Broker/client có đang loại bỏ TLS version cũ không.
- Proxy/load balancer có terminate TLS và dùng protocol khác không.

Ưu tiên TLS version hiện đại được cả broker, client và tổ chức hỗ trợ. Không hạ xuống SSL/TLS cũ để né lỗi mà chưa đánh giá tác động bảo mật.

## 4. Chẩn đoán SASL authentication

### 4.1. Cấu hình client cần khớp broker

Kafka 4.4 hỗ trợ các SASL mechanisms:

| Mechanism | Danh tính dựa trên | Kiểm tra chính |
|---|---|---|
| PLAIN | Username/password | JAAS module, credential và TLS |
| SCRAM-SHA-256 | Username/password với challenge-response | Mechanism, credential, user record |
| SCRAM-SHA-512 | Username/password với challenge-response | Mechanism, credential, user record |
| GSSAPI | Kerberos principal/ticket | KDC, keytab, SPN, service name, clock |
| OAUTHBEARER | OAuth bearer token/JWT | Issuer, audience, scope, expiry, signature, JWKS/callback |

Client và listener phải thống nhất security.protocol và mechanism được broker bật. SASL_SSL yêu cầu cấu hình TLS đầy đủ bên cạnh SASL.

### 4.2. Lỗi mechanism không được hỗ trợ

Dấu hiệu:

- Unsupported SASL mechanism.
- No enabled mechanism found.
- SaslHandshakeException.

Kiểm tra:

1. Client sasl.mechanism có đúng tên và chữ hoa/thường không.
2. Listener có bật mechanism đó trong sasl.enabled.mechanisms không.
3. Client đang kết nối đúng listener/port không.
4. Nếu nhiều listener, listener-specific configuration có bật mechanism không.
5. Broker và client Kafka version có hỗ trợ mechanism đã chọn không.

Ví dụ client:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
~~~

Nếu broker chỉ bật SCRAM-SHA-256 mà client dùng SCRAM-SHA-512, handshake sẽ thất bại dù username/password đúng.

### 4.3. Lỗi username/password hoặc JAAS

Dấu hiệu:

- SaslAuthenticationException: Authentication failed.
- Invalid username or password.
- Login module initialization failed.
- JAAS configuration entry not found.

Với SCRAM:

- Dùng ScramLoginModule.
- Username phải khớp principal credential đã tạo ở broker.
- Password phải khớp credential đang lưu trong cluster.
- Client mechanism phải trùng mechanism credential/listener cho phép.

Ví dụ:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-writer" password="${KAFKA_PASSWORD}";
~~~

Với PLAIN:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="orders-writer" password="${KAFKA_PASSWORD}";
~~~

PLAIN truyền thông tin xác thực qua SASL exchange; luôn dùng TLS trong production. Không lưu password trực tiếp trong repository, Docker image hoặc file config có quyền đọc rộng.

### 4.4. JAAS precedence và nhiều client trong một JVM

Kafka client có thể nhận JAAS từ:

- sasl.jaas.config trên từng producer/consumer/AdminClient.
- Static JAAS file được trỏ bởi java.security.auth.login.config.

Nếu cả hai được cấu hình, sasl.jaas.config của client được ưu tiên. Cấu hình per-client cho phép các producer/consumer trong cùng JVM dùng credential khác nhau.

Nếu một ứng dụng Spring có producer dùng được nhưng consumer lỗi, kiểm tra xem producer và consumer có override properties riêng hay không. Đừng chỉ kiểm tra application-level properties chung.

### 4.5. SCRAM credential trong KRaft

Với cơ chế SCRAM mặc định của Kafka, credential được lưu trong metadata log của KRaft. Khi xác thực lỗi:

- Xác nhận user credential đã được tạo trên đúng cluster.
- Xác nhận credential dùng đúng SHA-256 hoặc SHA-512.
- Kiểm tra password rotation có hoàn tất trên cluster chưa.
- Kiểm tra client có kết nối nhầm cluster hoặc môi trường staging/production không.
- Kiểm tra metadata/controller quorum và log khi quản trị credential.

Không nhầm việc tạo ACL cho User:orders-writer với việc tạo SCRAM credential. Credential tạo danh tính; ACL cấp quyền sau authentication.

### 4.6. Kerberos/GSSAPI

Khi dùng GSSAPI, kiểm tra:

- Kerberos realm và KDC có truy cập được không.
- Principal trong keytab có đúng không.
- Service principal name của Kafka broker có đúng tên service và hostname không.
- sasl.kerberos.service.name có khớp broker service name không.
- DNS forward/reverse có nhất quán theo chính sách Kerberos không.
- Đồng hồ client, broker và KDC có lệch quá giới hạn không.
- Keytab còn hiệu lực và chứa đúng principal không.
- JAAS dùng đúng Krb5LoginModule, keyTab và principal.

Lỗi ticket expired, clock skew hoặc server not found in Kerberos database thường là vấn đề Kerberos/KDC/SPN, không phải ACL topic.

### 4.7. OAuth/OAUTHBEARER

Khi dùng OAUTHBEARER, kiểm tra:

- Client lấy được token từ token endpoint hoặc assertion provider.
- Token chưa hết hạn tại thời điểm broker xác minh.
- Issuer và audience được broker chấp nhận.
- Chữ ký JWT hợp lệ và signing key có trong JWKS.
- Scope/claim cần thiết tồn tại.
- Broker có callback handler hoặc cấu hình validation phù hợp.
- Client có cơ chế refresh token trước khi hết hạn.
- Đồng hồ hệ thống đồng bộ.

Nếu token hợp lệ nhưng principal được map khác dự kiến, kiểm tra claim được dùng để tạo KafkaPrincipal. Sau authentication, ACL vẫn được kiểm tra riêng.

## 5. Chẩn đoán ACL theo topic và consumer group

### 5.1. Authentication thành công chưa có nghĩa được phép truy cập

Kafka tạo KafkaPrincipal sau authentication. Authorizer dùng principal đó để kiểm tra operation trên resource.

Trong KRaft, Apache Kafka cung cấp StandardAuthorizer:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
super.users=User:kafka-admin
~~~

StandardAuthorizer cần được cấu hình nhất quán trên các node KRaft liên quan: broker, controller hoặc node combined broker/controller.

ACL được lưu trong cluster metadata log. Khi authorizer được bật và không có ACL phù hợp với resource, hành vi mặc định là deny, ngoại trừ super.users.

### 5.2. Cấu trúc một ACL

Một ACL gồm:

- Principal: danh tính broker đã xác thực, ví dụ User:orders-writer.
- Host: địa chỉ IP nguồn được phép hoặc bị từ chối.
- Operation: Read, Write, Describe, Create, Delete, Alter, ClusterAction, IdempotentWrite...
- Resource type: Topic, Group, Cluster, TransactionalId, DelegationToken hoặc User.
- Resource pattern: LITERAL, PREFIXED hoặc wildcard.
- Permission: ALLOW hoặc DENY.

Ví dụ:

| Principal | Operation | Resource type | Resource name | Pattern | Permission |
|---|---|---|---|---|---|
| User:orders-writer | Write | Topic | orders.v1 | LITERAL | ALLOW |
| User:orders-writer | Describe | Topic | orders.v1 | LITERAL | ALLOW |
| User:orders-reader | Read | Topic | orders.v1 | LITERAL | ALLOW |
| User:orders-reader | Read | Group | orders-consumer | LITERAL | ALLOW |
| User:orders-reader | Describe | Group | orders-consumer | LITERAL | ALLOW |

### 5.3. Producer cần quyền gì?

Producer thông thường cần:

- Write trên topic để gửi record.
- Describe trên topic cho các thao tác metadata.
- Create chỉ khi ứng dụng được phép tạo topic hoặc đang dựa vào auto topic creation.

Không cấp Create mặc định cho service chỉ có nhiệm vụ publish vào topic đã được provision sẵn.

Producer bật idempotence có thể cần IdempotentWrite trên Cluster resource theo ACL model. Transactional producer cần quyền trên TransactionalId, thường gồm Describe và Write cho transactional ID tương ứng.

### 5.4. Consumer cần quyền gì?

Consumer group cần quyền ở cả topic và group:

- Read trên topic để fetch record.
- Read trên group để join, heartbeat và commit offset.
- Describe trên topic/group cho metadata và offset fetch/describe operations theo API được dùng.

Một consumer có thể fetch record được nhưng commit/fetch offset lỗi nếu thiếu quyền trên group hoặc topic tương ứng.

Consumer group ID là resource riêng. Cấp Read topic mà không cấp quyền group không đủ để consumer group hoạt động bình thường.

### 5.5. Các authorization error thường gặp

| Error | Resource thường liên quan | Kiểm tra |
|---|---|---|
| TOPIC_AUTHORIZATION_FAILED | Topic | Principal có Read/Write/Describe trên đúng topic không? |
| GROUP_AUTHORIZATION_FAILED | Group | Principal có Read/Describe trên đúng group ID không? |
| CLUSTER_AUTHORIZATION_FAILED | Cluster | Có operation yêu cầu quyền cluster như IdempotentWrite hoặc quản trị không? |
| TRANSACTIONAL_ID_AUTHORIZATION_FAILED | TransactionalId | Producer có Describe/Write trên transactional ID không? |

Lỗi có thể xuất hiện ở metadata request, fetch, offset commit, group coordinator hoặc transaction coordinator. Ghi lại API operation và resource bị từ chối thay vì chỉ dựa vào thông báo tổng quát ở ứng dụng.

### 5.6. Principal không giống username ứng dụng nghĩ

Với SASL/PLAIN hoặc SCRAM, principal mặc định thường dựa trên username đã xác thực.

Với SSL client authentication, principal mặc định có thể chứa X.500 distinguished name của certificate, ví dụ:

~~~text
User:CN=orders-writer,OU=ServiceUsers,O=Example
~~~

Broker có thể thay đổi cách ánh xạ DN sang short name bằng ssl.principal.mapping.rules. Nếu ACL cấp cho User:orders-writer nhưng principal thực tế là User:CN=orders-writer,... thì ACL không match.

Kiểm tra broker log để xác định principal thực tế. Không đoán principal từ tên service hoặc file certificate.

### 5.7. Literal, prefixed và wildcard ACL

- LITERAL: áp dụng cho resource có tên chính xác.
- PREFIXED: áp dụng cho resource có tên bắt đầu bằng prefix đã khai báo.
- Wildcard resource *: áp dụng rộng cho mọi resource cùng loại.

Ví dụ cấp quyền producer cho mọi topic bắt đầu bằng orders.:

~~~bash
kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --add --allow-principal User:orders-writer --operation Write --operation Describe --topic orders. --resource-pattern-type prefixed
~~~

Prefix ACL tiện cho nhiều topic nhưng có phạm vi rộng hơn literal. Chỉ dùng khi naming convention và boundary giữa tenant/service đã rõ.

### 5.8. ACL DENY và quyền rộng

Một ACL DENY có thể làm principal bị từ chối dù tồn tại một ACL ALLOW khác phù hợp. Khi điều tra, phải kiểm tra cả allow và deny, host condition, resource pattern và principal mapping.

Không dùng User:* hoặc topic * để chữa nhanh production authorization failure. Không thêm mọi service vào super.users.

### 5.9. allow.everyone.if.no.acl.found

Mặc định allow.everyone.if.no.acl.found là false: resource không có ACL match chỉ super users được truy cập.

Đặt true sẽ cho phép mọi principal truy cập resource không có ACL nào. Đây không phải cách xử lý lỗi authorization an toàn cho production. Chỉ cân nhắc trong môi trường dev/test hoặc giai đoạn rollout có kiểm soát, sau đó trở lại default deny.

## 6. Dùng kafka-acls.sh để kiểm tra và sửa quyền

### 6.1. Tạo admin.properties để kết nối an toàn

Các lệnh ACL cần một AdminClient có quyền quản trị phù hợp. File command config nên dùng security protocol, truststore và credential riêng cho admin:

~~~properties
security.protocol=SASL_SSL
ssl.truststore.location=/etc/kafka/admin.truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=${KAFKA_ADMIN_TRUSTSTORE_PASSWORD}
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="kafka-admin" password="${KAFKA_ADMIN_PASSWORD}";
~~~

Trong production, lấy secret từ secret manager hoặc cơ chế externalized config. File minh họa không chứa password thật.

### 6.2. Liệt kê ACL cho một topic và mọi pattern match

~~~bash
kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --list --topic orders.v1 --resource-pattern-type match
~~~

Resource pattern type match giúp xem các ACL literal, wildcard và prefixed có ảnh hưởng tới topic này. Chỉ list literal có thể bỏ sót ACL wildcard/prefix đang áp dụng.

### 6.3. Liệt kê ACL cho consumer group

~~~bash
kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --list --group orders-consumer
~~~

Kiểm tra đúng group ID runtime của consumer. Nếu ứng dụng tạo group ID theo environment, tenant hoặc suffix động, ACL literal có thể không match group thực tế.

### 6.4. Cấp quyền tối thiểu cho producer

~~~bash
kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --add --allow-principal User:orders-writer --operation Write --operation Describe --topic orders.v1
~~~

Nếu service cần tự tạo topic, cấp Create có chủ đích và xem xét quyền ở Topic hoặc Cluster resource theo chính sách triển khai. Thường nên để platform/admin provision topic trước.

### 6.5. Cấp quyền cho consumer topic và group

~~~bash
kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --add --allow-principal User:orders-reader --operation Read --operation Describe --topic orders.v1

kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --add --allow-principal User:orders-reader --operation Read --group orders-consumer

kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --add --allow-principal User:orders-reader --operation Describe --group orders-consumer
~~~

Lệnh cuối cấp Describe cho group để hỗ trợ các thao tác offset fetch/describe khi client cần. Kiểm tra error cụ thể và API version để chỉ cấp operation cần thiết cho workload.

Kafka CLI có tiện ích --consumer, tạo Read/Describe trên topic và Read trên consumer group. Nếu log chỉ ra thiếu Describe trên group, cấp thêm quyền Describe như ví dụ trên.

### 6.6. Producer idempotent và transactional

Idempotent producer:

~~~bash
kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --add --allow-principal User:orders-writer --operation IdempotentWrite --cluster
~~~

Transactional producer:

~~~bash
kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --add --allow-principal User:orders-transactional --operation Describe --operation Write --transactional-id orders-service-tx- --resource-pattern-type prefixed
~~~

Nếu transactional.id có suffix động, cân nhắc prefixed resource pattern phù hợp và kiểm tra phạm vi prefix để không cấp quyền cho workload khác.

### 6.7. Xác minh sau khi cấp ACL

~~~bash
kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --list --topic orders.v1 --resource-pattern-type match

kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --list --group orders-consumer
~~~

Sau đó thử producer/consumer bằng service account thực tế. Không chỉ thử bằng admin account vì admin có thể bypass ACL thông qua super.users.

## 7. Cấu hình TLS/SASL trong Java và Spring Boot

### 7.1. Kafka client properties

Ví dụ Java client dùng SASL_SSL và SCRAM-SHA-512:

~~~properties
bootstrap.servers=broker1.example.com:9093,broker2.example.com:9093
security.protocol=SASL_SSL
ssl.truststore.location=/etc/kafka/client.truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=${KAFKA_TRUSTSTORE_PASSWORD}
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="${KAFKA_PASSWORD}";
~~~

Nếu broker không yêu cầu mTLS, không cần client keystore. Nếu broker yêu cầu mTLS, thêm ssl.keystore.location, ssl.keystore.type, ssl.keystore.password và ssl.key.password.

### 7.2. Spring Boot application.properties

Spring Boot có thể bind security protocol, SSL properties và các Kafka client properties bổ sung:

~~~properties
spring.kafka.bootstrap-servers=broker1.example.com:9093,broker2.example.com:9093
spring.kafka.security.protocol=SASL_SSL

spring.kafka.ssl.trust-store-location=file:/etc/kafka/client.truststore.p12
spring.kafka.ssl.trust-store-type=PKCS12
spring.kafka.ssl.trust-store-password=${KAFKA_TRUSTSTORE_PASSWORD}

spring.kafka.properties[sasl.mechanism]=SCRAM-SHA-512
spring.kafka.properties[sasl.jaas.config]=org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
~~~

Các thuộc tính dưới spring.kafka.properties được chuyển thành Kafka client properties dùng chung. Nếu producer, consumer hoặc AdminClient cần credential khác nhau, cấu hình phần properties riêng của client tương ứng.

### 7.3. Cấu hình riêng producer/consumer

Ví dụ khi producer và consumer dùng service account khác nhau:

~~~properties
spring.kafka.producer.security.protocol=SASL_SSL
spring.kafka.producer.properties[sasl.mechanism]=SCRAM-SHA-512
spring.kafka.producer.properties[sasl.jaas.config]=org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_PRODUCER_USERNAME}" password="${KAFKA_PRODUCER_PASSWORD}";

spring.kafka.consumer.security.protocol=SASL_SSL
spring.kafka.consumer.properties[sasl.mechanism]=SCRAM-SHA-512
spring.kafka.consumer.properties[sasl.jaas.config]=org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_CONSUMER_USERNAME}" password="${KAFKA_CONSUMER_PASSWORD}";
~~~

Đảm bảo SSL truststore được cấu hình cho cả producer và consumer nếu chúng dùng security profile riêng. AdminClient cũng có thể cần cấu hình riêng nếu ứng dụng tự tạo topic hoặc gọi Admin API.

### 7.4. Kiểm tra cấu hình Spring có thực sự được áp dụng

Khi CLI kết nối được nhưng Spring application lỗi:

- Kiểm tra profile đang active.
- Kiểm tra biến môi trường đã được inject vào process chưa.
- Kiểm tra property precedence giữa application.yml, profile file, environment và command line.
- Kiểm tra producer/consumer/AdminClient có override properties riêng không.
- Kiểm tra SSL bundle hoặc truststore path có tồn tại trong container runtime không.
- Kiểm tra JAAS string có dấu quote/semicolon đúng không.
- Kiểm tra clientId và principal trong broker log để xác định client đang dùng credential nào.

Không in toàn bộ effective config nếu có sasl.jaas.config, password hoặc token. Log tên property và trạng thái đã cấu hình; mask secret.

## 8. Bảng symptom → nguyên nhân → hướng xử lý

| Symptom/log | Tầng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|---|
| Connection refused | Network/listener | Sai host/port, listener chưa bind hoặc firewall | Kiểm tra TCP, listeners và port |
| Timeout sau bootstrap | Network/metadata | advertised.listeners trả endpoint không tới được | Kiểm tra DNS, route và certificate của mọi broker |
| Unsupported or unrecognized SSL message | TLS/listener | Client dùng TLS sai port hoặc broker port không bật TLS | Đối chiếu security.protocol và listener map |
| PKIX path building failed | TLS | Thiếu CA/intermediate hoặc truststore sai | Kiểm tra chain và import CA đúng |
| No subject alternative DNS name | TLS | Hostname client dùng không có trong SAN | Cấp lại certificate hoặc sửa advertised endpoint |
| Certificate expired/not yet valid | TLS | Certificate hết hạn hoặc clock lệch | Kiểm tra validity và NTP, rotate certificate |
| bad_certificate | TLS/mTLS | Client cert thiếu, không trusted hoặc sai usage | Kiểm tra client keystore và broker truststore |
| No common protocol/cipher | TLS | Broker/JDK không có TLS/cipher chung | Đối chiếu TLS version và cipher policy |
| Unsupported SASL mechanism | SASL | Client mechanism không được listener bật | Đồng bộ sasl.mechanism và sasl.enabled.mechanisms |
| Authentication failed | SASL | Username/password sai hoặc credential chưa tồn tại | Kiểm tra credential trên đúng cluster |
| JAAS configuration error | SASL | Login module, property syntax hoặc JAAS section sai | Kiểm tra sasl.jaas.config và mechanism |
| Kerberos clock skew | SASL/GSSAPI | Client/broker/KDC lệch giờ | Đồng bộ NTP, kiểm tra ticket và keytab |
| OAuth token invalid/expired | SASL/OAUTHBEARER | Issuer/audience/scope/expiry/JWKS không hợp lệ | Kiểm tra token claims và broker validator |
| TOPIC_AUTHORIZATION_FAILED | ACL | Thiếu Read/Write/Describe hoặc principal mismatch | Kiểm tra topic ACL và principal |
| GROUP_AUTHORIZATION_FAILED | ACL | Thiếu quyền trên group ID | Kiểm tra group ACL và runtime group.id |
| CLUSTER_AUTHORIZATION_FAILED | ACL | Thiếu quyền trên Cluster resource | Xác định API yêu cầu cluster operation |
| TRANSACTIONAL_ID_AUTHORIZATION_FAILED | ACL | Thiếu Describe/Write trên transactional ID | Cấp quyền đúng transactional ID |
| Producer gửi được nhưng consumer không commit | ACL/group | Thiếu quyền trên group hoặc topic cho offset API | Kiểm tra Read/Describe ở cả group và topic |
| AdminClient tạo topic lỗi | ACL | Thiếu Create/Alter/Describe phù hợp | Xác định operation của Admin API rồi cấp quyền tối thiểu |
| CLI admin được, service account lỗi | ACL | Admin là super user hoặc có quyền rộng | Thử bằng đúng service principal và liệt kê ACL match |

## 9. Quy trình xử lý sự cố theo từng bước

### Bước 1 — Thu thập thông tin

- [ ] Bootstrap servers và port.
- [ ] Listener/security protocol mà client cần dùng.
- [ ] Kafka client version và broker version.
- [ ] security.protocol.
- [ ] sasl.mechanism nếu dùng SASL.
- [ ] Hostname thực tế sau metadata discovery.
- [ ] Principal dự kiến và principal trong broker log.
- [ ] Topic name và group.id runtime.
- [ ] API operation và full exception chain.
- [ ] Thời điểm lỗi, thay đổi certificate, credential hoặc ACL gần nhất.

Không gửi password, private key, token hoặc nội dung JAAS có secret trong ticket/log.

### Bước 2 — Kiểm tra kết nối TCP

~~~powershell
Test-NetConnection broker1.example.com -Port 9093
~~~

Nếu TCP fail, kiểm tra DNS, firewall, route, broker listener và port. Không chuyển sang chỉnh ACL.

### Bước 3 — Kiểm tra TLS

~~~bash
openssl s_client -connect broker1.example.com:9093 -servername broker1.example.com -showcerts -verify_return_error
~~~

Xác nhận certificate chain, expiry và SAN. Nếu cần, kiểm tra truststore bằng keytool. Giữ hostname verification bật.

### Bước 4 — Kiểm tra SASL bằng cùng client properties

~~~bash
kafka-broker-api-versions.sh --bootstrap-server broker1.example.com:9093 --command-config client.properties
~~~

Nếu TLS/SASL không hoàn tất, lệnh sẽ thất bại trước khi kiểm tra quyền topic/group. Xác nhận mechanism, JAAS và credential.

### Bước 5 — Kiểm tra ACL

Dùng admin client có quyền quản trị:

~~~bash
kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --list --topic orders.v1 --resource-pattern-type match

kafka-acls.sh --bootstrap-server broker1.example.com:9093 --command-config admin.properties --list --group orders-consumer
~~~

Đối chiếu principal chính xác, topic, group, operation, host và resource pattern. Nếu producer idempotent hoặc transactional, kiểm tra thêm Cluster và TransactionalId resource.

### Bước 6 — Thử bằng đúng service account

Dùng command config của service account để chạy một producer/consumer smoke test. Nếu service account hoạt động bằng CLI nhưng Spring lỗi, tập trung vào property binding, profile, file path, container mount và client-specific override.

### Bước 7 — Cấp quyền nhỏ nhất và kiểm tra lại

Thêm ACL cho đúng principal/resource/operation. Chạy lại smoke test. Nếu thành công, ghi nhận ACL thay đổi, owner, lý do và quy trình thu hồi khi không còn cần.

## 10. Cấu hình broker KRaft và quản trị an toàn

### 10.1. StandardAuthorizer

Ví dụ phần cấu hình authorization cho KRaft:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
super.users=User:kafka-admin
allow.everyone.if.no.acl.found=false
~~~

Cấu hình này phải được áp dụng nhất quán trên các node KRaft liên quan. super.users là principal bypass ACL; chỉ giữ các principal quản trị được kiểm soát chặt.

### 10.2. Listener security mapping

Ví dụ rút gọn cho client listener dùng SASL_SSL:

~~~properties
listeners=CLIENT://0.0.0.0:9093
advertised.listeners=CLIENT://broker1.example.com:9093
listener.security.protocol.map=CLIENT:SASL_SSL
sasl.enabled.mechanisms=SCRAM-SHA-512
~~~

Đây chỉ là phần minh họa client listener. Cấu hình cluster thật còn phải có controller listener, inter-broker listener, KRaft quorum và credential cho broker-to-broker communication theo topology đang triển khai. Không thay toàn bộ server.properties bằng đoạn ví dụ này.

### 10.3. Bootstrap super user và ACL

Khi bật StandardAuthorizer, cần bảo đảm có một đường quản trị hợp lệ:

- Cấu hình super.users cho admin principal được bảo vệ.
- Xác nhận principal thực tế khớp đúng chuỗi trong super.users.
- Dùng admin.properties với TLS/SASL phù hợp để gọi kafka-acls.sh.
- Cấp ACL cho service account sau khi xác minh principal.
- Không dùng service account nghiệp vụ làm super user.

Trong KRaft, admin request có thể được broker forward tới active controller. Với custom principal builder, principal cần hỗ trợ serialization/deserialization cho cơ chế forwarding KRaft.

## 11. Các tình huống ACL thực tế

### 11.1. Producer ghi được topic A nhưng không ghi được topic B

Kiểm tra:

- Topic B có tên khác prefix/literal pattern không.
- ACL có gắn đúng principal không.
- Topic B có ACL DENY hoặc wildcard/prefix rule khác không.
- Producer có dùng đúng cluster/listener không.
- Nếu topic B chưa tồn tại, auto-create có bị cấm hoặc thiếu Create không.

Không cấp WRITE trên toàn bộ topic chỉ vì một topic thiếu ACL.

### 11.2. Consumer fetch được nhưng offset commit bị từ chối

Kiểm tra:

- Read trên topic.
- Read trên consumer group.
- Describe trên topic và group nếu API offset fetch cần.
- Group ID runtime có đúng group được cấp ACL không.
- Ứng dụng có tạo group ID theo environment hoặc tenant không.

Offset commit/fetch có thể kiểm tra quyền trên cả group và topic. Chỉ cấp Read topic chưa đủ.

### 11.3. Consumer subscribe được nhưng không thấy topic metadata

Kiểm tra:

- Describe trên topic.
- Topic name đúng chính tả/case.
- ACL literal/prefixed/wildcard có match không.
- Topic có tồn tại và được quảng bá qua cluster metadata không.
- Client có kết nối được mọi broker endpoint không.

Nếu lỗi là metadata authorization, kiểm tra Describe. Nếu lỗi là fetch authorization, kiểm tra Read.

### 11.4. Producer idempotent hoặc transaction bị từ chối

Kiểm tra:

- IdempotentWrite trên Cluster nếu producer dùng idempotence và broker yêu cầu ACL này.
- Describe/Write trên TransactionalId.
- Transactional ID thực tế có prefix/suffix khác ACL đã cấp không.
- Producer có đang dùng transactional.id khác giữa các environment không.

### 11.5. SSL principal không khớp ACL

Kiểm tra certificate DN broker nhận và ssl.principal.mapping.rules. Nếu mapping rule thay đổi, ACL cũ có thể không còn khớp principal mới. Thử liệt kê ACL bằng principal và kiểm tra broker log sau authentication.

## 12. Hardening và vận hành

- Dùng SASL_SSL hoặc SSL cho production traffic.
- Giữ hostname verification bật và cấp certificate có SAN chính xác.
- Rotate certificate trước khi hết hạn; có kế hoạch phân phối CA/truststore.
- Dùng SCRAM-SHA-256/512 hoặc cơ chế identity phù hợp với hạ tầng.
- Chỉ dùng PLAIN khi được bọc trong TLS.
- Quản lý password/token/private key qua secret manager hoặc externalized configuration.
- Dùng principal riêng cho producer, consumer, Connect, Streams và admin.
- Cấp ACL theo topic/group và operation tối thiểu.
- Không bật allow.everyone.if.no.acl.found=true trong steady-state production.
- Giới hạn super.users và audit mọi thay đổi ACL.
- Kiểm tra ACL theo resource pattern match, không chỉ literal.
- Không log JAAS string, password, token hoặc private key.
- Theo dõi certificate expiry, authentication failure và authorization failure.
- Kiểm tra inter-broker/controller listener và service account riêng với client application.

## 13. Bài thực hành và tự kiểm tra

### Thực hành A — TLS truststore và hostname

1. Dựng một broker lab có SSL listener.
2. Tạo CA lab và certificate broker có DNS SAN.
3. Tạo client truststore chứa CA.
4. Kết nối bằng Kafka CLI với security.protocol=SSL.
5. Xóa CA khỏi truststore và ghi nhận lỗi PKIX.
6. Dùng hostname không có trong SAN và ghi nhận hostname verification error.
7. Khôi phục truststore/certificate đúng và kết nối lại.

### Thực hành B — SASL/SCRAM

1. Bật listener SASL_SSL và mechanism SCRAM-SHA-512.
2. Tạo credential cho principal orders-writer và orders-reader.
3. Kết nối bằng client properties đúng.
4. Đổi mechanism sang SCRAM-SHA-256 khi broker chỉ bật SHA-512 và quan sát lỗi.
5. Thử password sai.
6. Khôi phục credential và xác nhận authentication thành công.

### Thực hành C — ACL theo topic và group

1. Bật StandardAuthorizer trên KRaft lab.
2. Tạo principal orders-writer và orders-reader.
3. Cấp Write/Describe cho producer trên orders.v1.
4. Cấp Read/Describe cho consumer trên topic và Read/Describe trên group orders-consumer.
5. Thử ghi vào topic payments.v1 và xác nhận bị từ chối.
6. Thử dùng group ID khác và xác nhận group ACL không match.
7. Dùng resource-pattern-type match để xem ACL có hiệu lực.
8. Cấp đúng ACL thiếu và thử lại.

### Thực hành D — Spring Boot security configuration

1. Cấu hình Spring Kafka dùng SASL_SSL/SCRAM.
2. Đưa username/password vào environment hoặc secret store.
3. Cấu hình truststore path/password/type.
4. Chạy producer và consumer với principal riêng.
5. Cố ý cấu hình sai truststore, mechanism và credential ở từng lượt.
6. Đối chiếu lỗi Spring với Kafka CLI dùng cùng client properties.
7. Kiểm tra log không lộ secret.

### Câu hỏi tự kiểm tra

1. TLS, SASL và ACL giải quyết ba vấn đề nào?
2. SASL_SSL khác SSL ở bước nào?
3. Truststore và keystore chứa loại dữ liệu gì?
4. Vì sao PKIX path building failed không phải lỗi ACL?
5. SAN mismatch xảy ra khi nào?
6. Vì sao không nên tắt hostname verification trong production?
7. Khi nào client cần keystore cho mTLS?
8. SASL/PLAIN nên được dùng với transport nào?
9. Client và broker phải thống nhất những SASL properties nào?
10. sasl.jaas.config khác static JAAS file ra sao?
11. SCRAM credential và Kafka ACL khác nhau thế nào?
12. Kerberos GSSAPI cần kiểm tra những thành phần nào?
13. OAuth token cần kiểm tra issuer, audience và expiry ra sao?
14. Principal SSL mặc định có thể khác username ứng dụng như thế nào?
15. Producer cần quyền gì trên topic?
16. Consumer cần quyền gì trên topic và group?
17. Vì sao consumer có thể fetch được nhưng commit offset thất bại?
18. Khi nào producer cần IdempotentWrite trên Cluster?
19. Transactional producer cần quyền trên resource nào?
20. Resource pattern PREFIXED khác LITERAL như thế nào?
21. Vì sao chỉ list ACL literal có thể bỏ sót quyền đang áp dụng?
22. StandardAuthorizer lưu ACL ở đâu trong KRaft?
23. allow.everyone.if.no.acl.found=true ảnh hưởng thế nào tới resource chưa có ACL?
24. Vì sao admin CLI thành công chưa chứng minh service account có quyền?
25. Quy trình điều tra nào giúp phân biệt TLS, SASL và authorization nhanh nhất?

## Kết luận

Chẩn đoán bảo mật Kafka cần đi theo đúng thứ tự: network/listener, TLS, SASL rồi ACL. TLS xác minh certificate chain và hostname; SASL xác thực credential/token để tạo principal; ACL quyết định principal có quyền trên topic, group, cluster hoặc transactional ID. Khi authorization lỗi, phải kiểm tra đúng principal thực tế, operation và resource pattern. Producer thường cần Write/Describe trên topic; consumer cần Read trên topic và quyền phù hợp trên group để join, heartbeat và commit/fetch offset. KRaft dùng StandardAuthorizer và lưu ACL trong metadata log. Cấu hình đúng, cấp quyền tối thiểu và thử bằng chính service account sẽ giúp xử lý lỗi có kiểm soát mà không mở rộng quyền hoặc làm suy yếu TLS.

## Tài liệu tham khảo

- [Apache Kafka 4.4 — Security Overview](https://kafka.apache.org/44/security/security-overview/)
- [Apache Kafka 4.4 — Encryption and Authentication using SSL](https://kafka.apache.org/44/security/encryption-and-authentication-using-ssl/)
- [Apache Kafka 4.4 — Authentication using SASL](https://kafka.apache.org/44/security/authentication-using-sasl/)
- [Apache Kafka 4.4 — Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/)
- [Apache Kafka 4.4 — Security Model](https://kafka.apache.org/44/security/security-model/)
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/)
- [Spring Cloud Stream — Kafka Binder Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html)
