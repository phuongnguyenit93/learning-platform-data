# Quản lý secret, xoay vòng chứng chỉ và thông tin xác thực

## Mục tiêu

Một Kafka cluster an toàn cần bảo vệ danh tính của broker, controller, ứng dụng và người vận hành. Mật khẩu SASL, private key, client certificate, truststore, OAuth client secret và token đều là tài sản nhạy cảm. Chỉ bật TLS hoặc SASL chưa đủ: hệ thống còn phải lưu secret an toàn, cấp quyền đúng phạm vi, xoay vòng trước khi hết hạn và thu hồi nhanh khi có dấu hiệu lộ lọt.

Bài học này tập trung vào vòng đời secret và credential trong Kafka: nơi lưu, cách cấp cho broker/client, cách xoay vòng mật khẩu SCRAM và chứng chỉ TLS, cũng như cách xác minh và xử lý lỗi sau khi thay đổi.

Sau bài học, bạn có thể:

- Phân biệt mã hóa đường truyền, xác thực và phân quyền.
- Phân loại secret, certificate, private key, token và trust anchor.
- Lưu secret bằng secret manager hoặc file mount có kiểm soát.
- Cấu hình TLS, mTLS và SASL/SCRAM cho Kafka client.
- Quản lý SCRAM credentials trong KRaft và xoay vòng không gián đoạn bằng principal mới.
- Xoay vòng CA, broker certificate và client certificate theo chiến lược trust overlap.
- Dùng Kafka Connect ConfigProvider để tham chiếu secret bên ngoài.
- Kiểm tra ACL, certificate chain, SAN, hạn chứng chỉ và trạng thái kết nối.
- Xây dựng runbook thu hồi credential khi bị lộ.

## 1. Bốn lớp bảo vệ cần phân biệt

Kafka security có nhiều lớp, mỗi lớp giải quyết một câu hỏi riêng:

| Lớp | Câu hỏi | Cơ chế tiêu biểu |
|---|---|---|
| Encryption in transit | Dữ liệu có bị đọc trên đường truyền không? | TLS |
| Authentication | Kết nối đang mang danh tính nào? | TLS client certificate, SASL/SCRAM, SASL/OAUTHBEARER, Kerberos |
| Authorization | Danh tính đó được phép làm gì? | Kafka ACL, StandardAuthorizer |
| Secret lifecycle | Credential được lưu, cấp, xoay vòng và thu hồi thế nào? | Secret manager, certificate authority, automation, audit |

Ví dụ, một producer kết nối bằng SASL/SCRAM qua TLS:

- TLS mã hóa kết nối và xác minh certificate của broker.
- SCRAM xác thực username/password của producer.
- ACL quyết định producer có được ghi vào topic hay không.
- Secret manager cung cấp password và hỗ trợ thay password theo phiên bản.

Nếu chỉ bật SASL mà không cấu hình authorizer, broker có thể xác thực được danh tính nhưng chưa giới hạn quyền của danh tính đó. Nếu chỉ bật TLS mà không yêu cầu client certificate hoặc SASL, TLS có thể chỉ xác thực server và mã hóa đường truyền; client chưa có danh tính riêng để phân quyền.

### 1.1. Secret nào cần quản lý?

| Loại dữ liệu | Ví dụ | Tác động khi bị lộ |
|---|---|---|
| Password | SCRAM password, SASL/PLAIN password | Người khác có thể đăng nhập bằng principal đó |
| Private key | Broker TLS key, client mTLS key, OAuth signing key | Có thể giả mạo broker hoặc client tùy certificate/identity |
| Keystore password | Mật khẩu mở JKS/PKCS12 | Có thể mở keystore nếu có file tương ứng |
| Truststore | CA certificate | Bản thân CA certificate là public; thay đổi trust anchor có thể mở rộng bên nào được tin cậy |
| OAuth client secret | Client credentials secret | Có thể lấy token với quyền của client |
| Access token | OAuth bearer token | Có thể truy cập trong thời gian token còn hiệu lực |
| JAAS config | Username/password hoặc keytab path | Có thể làm lộ credential và cấu hình xác thực |
| Admin credential | Tài khoản quản trị cluster | Có thể thay ACL, topic, user và cấu hình broker |

Không phải mọi file security đều là secret. CA certificate và truststore thường chứa public certificate, nhưng vẫn cần bảo vệ tính toàn vẹn vì kẻ tấn công có thể thêm CA không đáng tin. Private key, password và token phải được giữ bí mật.

## 2. Nguyên tắc quản lý secret

### 2.1. Không lưu secret trong source code

Không commit các nội dung sau vào Git:

- Password trong application.properties, server.properties hoặc file connector.
- Private key, keystore có thể mở bằng password yếu hoặc đã ghi kèm password.
- OAuth client secret, bearer token, API key.
- File JAAS có password thật.
- File dump cấu hình đã được render secret.

Không đưa secret vào Docker image, log, metric label, command-line argument, ticket, chat hoặc ảnh chụp màn hình. Việc xóa một secret khỏi commit mới không làm secret biến mất khỏi Git history; nếu đã lộ, cần rotate/revoke ngay.

### 2.2. Ưu tiên secret manager hoặc file mount có kiểm soát

Ứng dụng có thể lấy secret từ:

- Secret manager tập trung như Vault hoặc cloud secret manager.
- Kubernetes Secret được mount vào container qua volume read-only.
- File được agent/sidecar cập nhật với quyền truy cập tối thiểu.
- Environment variable được inject tại runtime khi nền tảng triển khai có kiểm soát phù hợp.

Chọn cơ chế theo môi trường và khả năng refresh. Environment variable tiện cho container nhưng thường khó cập nhật trong process đang chạy và có thể xuất hiện trong dump/process diagnostics. File mount cho phép agent thay file nhưng ứng dụng vẫn cần cơ chế reload hoặc restart để đọc giá trị mới.

Không coi ConfigMap hoặc file cấu hình thường là secret store. Nếu dùng Kubernetes, hạn chế RBAC đọc Secret, bật encryption at rest cho etcd theo nền tảng, chỉ mount secret vào container cần dùng và tránh đưa secret vào image layer.

### 2.3. Least privilege và tách danh tính

Mỗi ứng dụng nên có principal riêng, ví dụ:

~~~text
svc-order-producer
svc-inventory-consumer
svc-payment-consumer
svc-kafka-connect
svc-kafka-streams
ops-kafka-admin
~~~

Không dùng chung tài khoản admin cho producer, consumer, Connect và Streams. Khi một service bị xâm nhập, principal riêng giúp giới hạn phạm vi ACL cần thu hồi.

Mỗi secret cần có:

- Owner chịu trách nhiệm.
- Mục đích và service sử dụng.
- Nơi lưu và cách cấp quyền truy cập.
- Ngày tạo, ngày hết hạn hoặc lịch rotate.
- Phiên bản hiện tại và quy trình rollback.
- Audit trail cho việc đọc, tạo, rotate và revoke.

### 2.4. Không nhầm rotation với restart

Thay secret trong secret manager không tự động thay credential bên trong mọi Kafka client đang chạy. Một producer/consumer đã được khởi tạo thường giữ cấu hình xác thực trong vòng đời instance. Cần thiết kế cách reload hoặc rolling restart/recreate client để nạp credential mới.

Tương tự, thay file certificate trên đĩa không có nghĩa TLS connection đang mở lập tức đổi certificate. Thay đổi thường có hiệu lực với connection mới sau khi broker/client reload cấu hình hoặc khởi động lại.

## 3. TLS, keystore và truststore

TLS cung cấp mã hóa đường truyền và xác thực certificate. Các khái niệm cần phân biệt:

| Thành phần | Nội dung |
|---|---|
| Private key | Khóa bí mật dùng để chứng minh danh tính hoặc ký |
| Certificate | Public key cùng danh tính, thời hạn và chữ ký CA |
| Certificate chain | Certificate leaf và intermediate CA dẫn tới trust anchor |
| Keystore | Lưu private key và certificate chain của chính node/client |
| Truststore | Lưu CA certificate được tin cậy khi xác minh peer |
| CA | Certificate Authority ký và phát hành certificate |
| SAN | Subject Alternative Name chứa DNS/IP mà certificate đại diện |

Broker dùng keystore để chứng minh danh tính server. Client dùng truststore để kiểm tra broker certificate. Nếu bật mutual TLS (mTLS), broker còn xác thực client certificate; khi đó broker phải trust CA đã ký certificate của client.

### 3.1. TLS server authentication

Client xác minh certificate của broker và mã hóa kết nối. Ví dụ cấu hình client:

~~~properties
security.protocol=SSL
ssl.truststore.location=/run/secrets/kafka/cluster-truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=<INJECTED_AT_RUNTIME>
ssl.endpoint.identification.algorithm=https
ssl.enabled.protocols=TLSv1.2,TLSv1.3
~~~

ssl.endpoint.identification.algorithm=https bật hostname verification. Đây là mặc định của Kafka client từ Kafka 2.0; giữ xác minh hostname để certificate phải khớp DNS/IP mà client kết nối. Không tắt bằng chuỗi rỗng chỉ để bỏ qua lỗi SAN.

Certificate của broker cần có SAN khớp hostname/IP được quảng bá trong advertised.listeners. Nếu client kết nối broker-1.kafka.internal, SAN phải có DNS name đó. Nếu client kết nối bằng IP, SAN phải có IP tương ứng.

### 3.2. mTLS

Với mTLS, client cũng có keystore chứa private key và certificate:

~~~properties
security.protocol=SSL
ssl.truststore.location=/run/secrets/kafka/cluster-truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=<INJECTED_AT_RUNTIME>

ssl.keystore.location=/run/secrets/kafka/client-identity.p12
ssl.keystore.type=PKCS12
ssl.keystore.password=<INJECTED_AT_RUNTIME>
ssl.key.password=<INJECTED_AT_RUNTIME>
~~~

Trên broker listener, đặt ssl.client.auth=required để bắt buộc client có certificate được tin cậy. Nếu dùng listener riêng, cấu hình theo prefix listener.name.<listener>.ssl.client.auth. Kafka khuyến cáo tránh requested vì client không có certificate vẫn có thể kết nối thành công, dễ tạo cảm giác sai rằng mTLS đã được bắt buộc.

Broker cần truststore chứa CA ký client certificate. Trong cluster nội bộ, certificate của broker cũng cần phù hợp cả serverAuth và clientAuth nếu broker vừa đóng vai server vừa đóng vai client trong giao tiếp giữa các broker.

### 3.3. TLS broker configuration

Ví dụ cấu hình minh họa cho broker:

~~~properties
listeners=INTERNAL://:9093,EXTERNAL://:9094
advertised.listeners=INTERNAL://broker-1.kafka.internal:9093,EXTERNAL://broker-1.example.net:9094
listener.security.protocol.map=INTERNAL:SASL_SSL,EXTERNAL:SASL_SSL
inter.broker.listener.name=INTERNAL

listener.name.external.ssl.keystore.location=/run/secrets/kafka/broker-external.p12
listener.name.external.ssl.keystore.type=PKCS12
listener.name.external.ssl.keystore.password=<INJECTED_AT_RUNTIME>
listener.name.external.ssl.key.password=<INJECTED_AT_RUNTIME>
listener.name.external.ssl.truststore.location=/run/secrets/kafka/client-ca.p12
listener.name.external.ssl.truststore.type=PKCS12
listener.name.external.ssl.truststore.password=<INJECTED_AT_RUNTIME>
listener.name.external.ssl.client.auth=required

ssl.enabled.protocols=TLSv1.2,TLSv1.3
~~~

Đây là ví dụ cấu hình listener, không phải file production hoàn chỉnh. Cần cấu hình riêng SASL mechanism/JAAS cho listener, inter-broker protocol, controller listener của KRaft và các listener thực tế của cluster.

Kafka hỗ trợ JKS, PKCS12 và PEM với default SSL engine factory hiện đại. Với PEM, private key được đặt trong ssl.keystore.key, certificate chain trong ssl.keystore.certificate.chain và CA certificate trong ssl.truststore.certificates. ssl.keystore.password và ssl.truststore.password không dùng cho PEM; nếu private key PEM được mã hóa, dùng ssl.key.password.

Với JKS/PKCS12, ssl.keystore.password mở keystore, còn ssl.key.password mở private key. Hai giá trị có thể giống hoặc khác nhau. Không mặc định rằng chỉ cần rotate một password là đã rotate certificate.

## 4. SASL và credential

SASL xác thực principal thông qua cơ chế được bật trên listener. Kafka hỗ trợ các cơ chế phổ biến:

| Cơ chế | Cách xác thực | Lưu ý |
|---|---|---|
| PLAIN | Username/password | Chỉ dùng qua TLS để bảo vệ password trên đường truyền |
| SCRAM-SHA-256 / SCRAM-SHA-512 | Challenge-response dùng salted verifier | Nên kết hợp TLS; phù hợp service account |
| OAUTHBEARER | OAuth bearer token/JWT | Dùng token ngắn hạn, issuer/audience đúng và cơ chế refresh production |
| GSSAPI (Kerberos) | Ticket/keytab | Phù hợp môi trường có Kerberos/KDC |

Ví dụ client dùng SCRAM qua TLS:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="svc-orders-v2" password="<INJECTED_AT_RUNTIME>";

ssl.truststore.location=/run/secrets/kafka/cluster-truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=<INJECTED_AT_RUNTIME>
ssl.endpoint.identification.algorithm=https
~~~

Các chuỗi INJECTED_AT_RUNTIME là placeholder của ví dụ. Kafka client không tự mở rộng cú pháp ENV_VAR hoặc placeholder tùy ý trong file properties. Ứng dụng hoặc nền tảng triển khai phải lấy secret từ secret manager rồi dựng Properties trước khi tạo Producer/Consumer. Không ghi Properties đã render ra log.

### 4.1. SCRAM trong KRaft

Trong KRaft, triển khai mặc định của Kafka lưu SCRAM credential trong metadata log. Broker không lưu password thô; nó lưu salted credential material như salt, iteration count, StoredKey và ServerKey.

Kafka hỗ trợ SCRAM-SHA-256 và SCRAM-SHA-512. Cấu hình credential có thể được tạo ban đầu bằng kafka-storage.sh khi format storage hoặc được tạo/cập nhật động bằng kafka-configs.sh sau khi cluster chạy. Credential dùng cho inter-broker authentication phải được chuẩn bị trước khi broker khởi động.

SCRAM phải đi cùng TLS. Nếu không mã hóa đường truyền, attacker có thể quan sát quá trình trao đổi và thực hiện tấn công từ điển/offline tùy điều kiện.

Ví dụ tạo credential cho user mới trong cluster đang chạy:

~~~bash
bin/kafka-configs.sh --bootstrap-server broker-1:9092 --alter --add-config 'SCRAM-SHA-512=[iterations=8192,password=<SECRET_FROM_SECURE_ADMIN_WORKFLOW>]' --entity-type users --entity-name svc-orders-v2 --command-config admin.properties
~~~

Đây là cú pháp minh họa. Không paste password thật vào command history, terminal recording, process list hoặc ticket. Trong production, dùng quy trình quản trị secret-safe để truyền password; admin.properties cũng phải được bảo vệ như một secret.

Kiểm tra metadata credential đã tồn tại:

~~~bash
bin/kafka-configs.sh --bootstrap-server broker-1:9092 --describe --entity-type users --entity-name svc-orders-v2 --command-config admin.properties
~~~

Không có API nào cho phép đọc lại password gốc từ SCRAM metadata. Nếu quên password, hãy rotate bằng credential mới thay vì tìm cách trích xuất.

### 4.2. SASL/PLAIN

PLAIN gửi username/password trong SASL exchange. Chỉ sử dụng qua SASL_SSL, không dùng SASL_PLAINTEXT trên mạng không tin cậy. Trong môi trường production, có thể dùng callback handler để lấy và xác minh password từ nguồn bên ngoài thay vì lưu password rõ trong JAAS file.

### 4.3. OAUTHBEARER

OAuth phù hợp khi tổ chức đã có Identity Provider và muốn cấp token ngắn hạn. Broker cần xác minh token theo issuer, audience, chữ ký và thời gian hợp lệ. Client phải refresh token trước khi hết hạn.

Không dùng unsecured JWT implementation mặc định của Kafka cho production; implementation này chỉ phù hợp dev/test. Production cần built-in JWT retriever được hỗ trợ hoặc callback handler tùy chỉnh để lấy và xác minh token an toàn.

Nếu dùng client_credentials, client có thể lấy token bằng client secret hoặc client assertion. Client assertion dùng private key ký JWT ngắn hạn, giúp private key không phải gửi tới Identity Provider. Dù vậy, private key và client secret vẫn cần secret lifecycle, access control và rotation.

## 5. Authorization bằng ACL

Authentication tạo ra KafkaPrincipal; authorization quyết định principal được phép thực hiện operation nào trên resource nào.

Trong KRaft, Kafka cung cấp StandardAuthorizer. Cấu hình này phải có trên tất cả node tham gia cluster metadata, gồm broker, controller và node kết hợp:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
~~~

ACL có thể áp dụng cho Topic, Group, Cluster, TransactionalId, DelegationToken và User. Dùng principal theo service và cấp operation tối thiểu.

Ví dụ cấp quyền producer trên topic:

~~~bash
bin/kafka-acls.sh --bootstrap-server broker-1:9092 --add --allow-principal User:svc-orders-producer --producer --topic orders.v1 --command-config admin.properties
~~~

Ví dụ cấp quyền consumer trên topic và group:

~~~bash
bin/kafka-acls.sh --bootstrap-server broker-1:9092 --add --allow-principal User:svc-inventory-consumer --consumer --topic orders.v1 --group inventory-service --command-config admin.properties
~~~

Kiểm tra ACL của topic:

~~~bash
bin/kafka-acls.sh --bootstrap-server broker-1:9092 --list --topic orders.v1 --command-config admin.properties
~~~

Với producer dùng transactional.id, Kafka Streams, Connect hoặc service quản trị, cần cấp thêm quyền cho transactional ID, internal topics, consumer group và cluster operations tương ứng. Không sao chép nguyên ACL của admin sang mọi service chỉ để làm cho ứng dụng chạy.

### 5.1. Default deny trong KRaft

Nếu không cấu hình authorizer, các principal đã xác thực có thể có quyền rộng trên cluster. Nếu cấu hình StandardAuthorizer nhưng không có ACL khớp resource, quyền truy cập bị từ chối, ngoại trừ principal trong super.users.

super.users bỏ qua ACL check; xem danh sách này như root account. Không đưa tài khoản ứng dụng thường vào đây. allow.everyone.if.no.acl.found=true mở resource chưa có ACL cho mọi principal, chỉ nên dùng trong giai đoạn migration có kiểm soát và không giữ làm trạng thái production lâu dài.

### 5.2. Broker, controller và service principal

Trong KRaft, cần bảo vệ cả:

- Client-facing listener.
- Inter-broker listener.
- Controller listener.
- Kết nối broker-controller.
- Kết nối công cụ quản trị.
- Kết nối Connect/Streams/MirrorMaker.

Không để controller listener công khai cho client nghiệp vụ. Dùng network segmentation và principal riêng cho broker/controller. Nếu cấu hình custom principal builder, kiểm tra khả năng serialize/deserialize principal khi broker forward request tới KRaft controller.

## 6. Lưu secret trong Kafka Connect và ứng dụng Java

### 6.1. Kafka Connect ConfigProvider

Kafka Connect hỗ trợ ConfigProvider để lấy password, API key và credential từ nguồn ngoài. Các provider tích hợp gồm:

- FileConfigProvider: đọc properties file được mount.
- DirectoryConfigProvider: đọc nội dung file theo key trong thư mục.
- EnvVarConfigProvider: đọc environment variable.
- Custom ConfigProvider: tích hợp Vault hoặc secret service riêng.

Ví dụ cấu hình worker:

~~~properties
config.providers=fileProvider,envProvider

config.providers.fileProvider.class=org.apache.kafka.common.config.provider.FileConfigProvider
config.providers.fileProvider.param.allowed.paths=/run/secrets/connect

config.providers.envProvider.class=org.apache.kafka.common.config.provider.EnvVarConfigProvider
config.providers.envProvider.param.allowlist.pattern=^KAFKA_CONNECT_.*
~~~

Connector có thể tham chiếu credential trong file properties:

~~~properties
database.user=${fileProvider:/run/secrets/connect/orders-db.properties:username}
database.password=${fileProvider:/run/secrets/connect/orders-db.properties:password}
~~~

File secret cần quyền đọc giới hạn cho user chạy Connect. Dùng allowed.paths hoặc allowlist.pattern để thu hẹp phạm vi provider được phép truy cập. Không đưa secret vào plugin.path; Connect cần đọc đường dẫn plugin trước khi ConfigProvider được khởi tạo.

ConfigProvider là cơ chế của Kafka Connect, không phải cú pháp nội suy mặc định của mọi Kafka Java client. Với Producer/Consumer/Streams, ứng dụng phải lấy secret từ secret manager hoặc runtime injection rồi truyền giá trị vào cấu hình client.

### 6.2. Secret cho Java/Spring

Ứng dụng Java nên có một lớp cấu hình chịu trách nhiệm lấy secret và dựng Kafka Properties. Có thể tích hợp Spring Cloud Vault, cloud secret manager, Kubernetes volume hoặc custom provider.

Ví dụ cấu hình không chứa password thật:

~~~java
Properties kafkaProperties = new Properties();
kafkaProperties.put("bootstrap.servers", brokers);
kafkaProperties.put("security.protocol", "SASL_SSL");
kafkaProperties.put("sasl.mechanism", "SCRAM-SHA-512");

String username = secretProvider.read("kafka/orders/username");
String password = secretProvider.read("kafka/orders/password");

// Hàm buildJaasConfig phải escape chuỗi theo cú pháp JAAS.
kafkaProperties.put(
        "sasl.jaas.config",
        buildJaasConfig(username, password));

KafkaProducer<String, String> producer =
        new KafkaProducer<>(kafkaProperties);
~~~

buildJaasConfig cần escape dấu nháy, dấu gạch chéo và ký tự đặc biệt đúng cú pháp JAAS; không nối chuỗi tùy tiện với password chưa escape. Không log kafkaProperties, sasl.jaas.config hoặc exception có thể chứa credential.

Producer/Consumer đã được tạo không tự nhận secret mới chỉ vì secret manager đã cập nhật. Với cách triển khai đơn giản, rolling restart service hoặc recreate client sau khi đọc secret mới. Nếu cần reload không gián đoạn, thiết kế lifecycle manager để tạo client mới, chuyển traffic, drain client cũ rồi close.

### 6.3. Secret trong REST API và connector config

Kafka Connect REST API có thể nhận connector config chứa password hoặc reference của ConfigProvider. Giới hạn quyền gọi REST API, dùng TLS và authentication ở mạng quản trị, không public endpoint ra Internet.

Không giả định password được mask trong REST response, log hoặc config dump ở mọi phiên bản/plugin. Dùng provider reference, hạn chế quyền truy cập worker config topic và không bật debug logging có thể in credential.

## 7. Quy trình xoay vòng SCRAM credential

Xoay vòng credential có thể thực hiện theo hai cách:

1. Cập nhật password của cùng một username.
2. Tạo principal mới, cấp cùng quyền, chuyển client sang principal mới rồi thu hồi principal cũ.

Cách thứ hai hỗ trợ overlap và rollback tốt hơn vì hai principal có thể cùng tồn tại trong giai đoạn chuyển đổi. Kafka SCRAM lưu một credential cho mỗi user/mechanism; không nên giả định cùng username có thể đồng thời chấp nhận hai password khác nhau.

### 7.1. Rotation không gián đoạn bằng principal mới

Giả sử service đang dùng svc-orders-v1:

~~~mermaid
sequenceDiagram
    participant A as Admin
    participant K as Kafka KRaft
    participant S as Secret Manager
    participant C as Orders Service

    A->>K: Tạo SCRAM user svc-orders-v2
    A->>K: Cấp ACL tương đương và tối thiểu
    A->>S: Lưu credential v2
    S->>C: Cấp secret v2
    C->>K: Kết nối bằng svc-orders-v2
    C->>K: Produce/consume kiểm tra thành công
    A->>K: Thu hồi ACL và credential v1
~~~

Các bước thực hiện:

1. Kiểm kê service, group, topic, transactional ID và ACL của principal cũ.
2. Tạo principal SCRAM mới với password ngẫu nhiên đủ mạnh.
3. Cấp ACL tối thiểu tương đương với chức năng thật của service.
4. Lưu credential mới vào secret manager dưới version mới.
5. Cập nhật deployment để service đọc secret mới.
6. Rolling restart hoặc recreate Kafka client để tạo connection bằng credential mới.
7. Xác minh authentication, produce/consume, lag, error rate và audit log.
8. Theo dõi một khoảng thời gian đủ dài để chắc chắn không còn instance dùng principal cũ.
9. Thu hồi ACL và xóa SCRAM mechanism của principal cũ.
10. Đánh dấu rotation hoàn tất, lưu audit event và thời điểm revoke.

Nếu service cũ vẫn còn connection mở, việc xóa credential không nhất thiết làm connection đó bị ngắt ngay lập tức. Chủ động recycle client/connection và kiểm tra telemetry để xác nhận principal cũ không còn được dùng.

### 7.2. Cập nhật password cùng username

Kafka hỗ trợ cập nhật SCRAM credential động bằng kafka-configs.sh; credential mới được dùng để xác thực các connection mới. Tuy nhiên, client đang dùng password cũ có thể không tạo được connection mới sau khi password bị thay.

Chỉ dùng cách này khi đã có kế hoạch phối hợp client rollout hoặc chấp nhận một cửa sổ gián đoạn. Nếu cần overlap, hãy tạo principal mới như quy trình trên.

### 7.3. Xoay vòng credential broker/inter-broker

Credential giữa broker và controller là credential hạ tầng, không giống credential của ứng dụng. Chúng có thể ảnh hưởng quorum, replication, controller communication và khả năng khởi động cluster.

Lập kế hoạch riêng:

- Chuẩn bị credential/JAAS cho mọi broker và controller liên quan.
- Kiểm tra listener và SASL mechanism đang dùng.
- Xác nhận mọi node có thể xác thực với credential mới trước khi thu hồi credential cũ.
- Thực hiện rolling theo thứ tự và quy trình phù hợp với topology KRaft.
- Theo dõi quorum, under-replicated partitions, request failures và controller logs.
- Không xóa credential cũ cho đến khi mọi node đã chuyển thành công.

Credential inter-broker ban đầu phải được chuẩn bị trước khi broker khởi động. Không chạy kafka-storage.sh format trên storage đã dùng chỉ để rotate password; format là thao tác khởi tạo storage, không phải quy trình rotation.

## 8. Quy trình xoay vòng TLS certificate

Certificate rotation cần quản lý cả leaf certificate, private key, CA chain, truststore và các connection đang mở.

### 8.1. Inventory trước khi rotate

Liệt kê:

- Certificate của từng broker và controller.
- Certificate của client nếu dùng mTLS.
- CA root và intermediate CA đang được trust.
- Listener sử dụng certificate nào: external, internal, inter-broker, controller.
- Service nào kết nối tới listener đó.
- SAN cần có theo DNS/IP trong advertised.listeners.
- Ngày hết hạn và owner của từng certificate.

Kiểm tra cả Connect, Streams, MirrorMaker, AdminClient, monitoring exporter, CLI và công cụ vận hành. Chỉ kiểm tra broker certificate là chưa đủ vì client mTLS cũng có thể sắp hết hạn.

### 8.2. Trust overlap khi đổi CA

Khi chuyển từ CA cũ sang CA mới, không thay truststore và certificate trong cùng một bước. Dùng giai đoạn overlap:

1. Phát hành CA mới và phân phối CA certificate mới tới truststore của broker, controller, client và các service cần xác minh certificate.
2. Giữ CA cũ trong truststore trong thời gian chuyển đổi.
3. Phát hành leaf certificate mới từ CA mới, có SAN, key usage, extended key usage và chain hợp lệ.
4. Cập nhật broker certificate từng node/listener; sau đó cập nhật client certificate nếu dùng mTLS.
5. Tạo connection mới và kiểm tra handshake, hostname verification, authentication và ACL.
6. Drain/restart các client còn giữ TLS connection cũ.
7. Chỉ gỡ CA cũ sau khi xác nhận không còn certificate cũ và không còn client phụ thuộc CA đó.

Nếu leaf certificate mới vẫn do cùng CA ký, việc thay keystore thường đơn giản hơn. Khi thay CA, trust overlap là bước quan trọng để tránh broker hoặc client không tin certificate của peer trong giai đoạn đổi CA.

### 8.3. Xoay vòng keystore broker

Kafka 4.4 hỗ trợ cập nhật động keystore của listener đang tồn tại mà không cần restart broker. Các config được cập nhật theo từng broker và phải có prefix listener.name.<listener>.:

- ssl.keystore.type
- ssl.keystore.location
- ssl.keystore.password
- ssl.key.password

Ví dụ cấu hình đích cho listener external:

~~~properties
listener.name.external.ssl.keystore.type=PKCS12
listener.name.external.ssl.keystore.location=/run/secrets/kafka/broker-external-v2.p12
listener.name.external.ssl.keystore.password=<INJECTED_AT_RUNTIME>
listener.name.external.ssl.key.password=<INJECTED_AT_RUNTIME>
~~~

Đây là các giá trị cần áp dụng bằng dynamic per-broker configuration workflow, không phải chỉ sửa file server.properties rồi chờ broker tự đọc lại. Dùng kafka-configs.sh hoặc AdminClient theo quy trình quản trị để cập nhật từng broker và kiểm tra kết quả.

Với inter-broker listener, broker chỉ cho phép thay keystore nếu certificate mới được trust bởi truststore đang cấu hình cho listener. Để tránh client authentication failure khi thay leaf certificate bằng dynamic update, Kafka docs yêu cầu certificate mới được ký bởi cùng CA đã ký certificate cũ. Nếu đổi CA, thực hiện trust overlap trước.

### 8.4. Xoay vòng truststore broker

Kafka 4.4 cũng hỗ trợ cập nhật động truststore của listener đang tồn tại:

- ssl.truststore.type
- ssl.truststore.location
- ssl.truststore.password

Truststore mới được dùng để xác thực các connection mới. Với inter-broker listener, keystore hiện tại phải được trust bởi truststore mới. Không loại CA đang ký certificate của broker/client còn hoạt động.

Thay truststore chỉ áp dụng cho connection mới; connection TLS đã thiết lập không tự động handshake lại. Cần kiểm tra client reconnect hoặc chủ động recycle connection theo kế hoạch.

### 8.5. Xoay vòng certificate phía client

Client certificate thường được đọc khi Kafka client tạo SSL context. Sau khi secret manager cập nhật file keystore, ứng dụng cần tạo Kafka client mới hoặc restart theo rolling plan để dùng certificate mới.

Với mTLS, trình tự an toàn:

1. Thêm CA mới vào truststore của broker.
2. Cấp client certificate mới.
3. Cập nhật file/secret của service.
4. Rolling restart/recreate Kafka client.
5. Kiểm tra principal mapping, ACL và handshake.
6. Thu hồi certificate cũ sau khi toàn bộ instance chuyển xong.
7. Gỡ CA cũ khỏi truststore khi không còn client nào cần.

Không chỉ kiểm tra certificate còn hạn. Cần kiểm tra SAN, issuer, chain, key usage, extended key usage và thuật toán được JVM/Kafka chấp nhận.

## 9. Kiểm tra certificate và kết nối

### 9.1. Xem certificate

~~~bash
openssl x509 -in broker.crt -noout -subject -issuer -dates -ext subjectAltName -ext extendedKeyUsage
~~~

Kiểm tra:

- notBefore và notAfter.
- Subject và issuer.
- SAN có DNS/IP đúng không.
- Extended Key Usage có serverAuth/clientAuth phù hợp không.
- Chain có intermediate CA cần thiết không.

### 9.2. Kiểm tra keystore PKCS12/JKS

~~~bash
keytool -list -v -keystore broker.p12 -storetype PKCS12
~~~

Không đưa password thật vào command line nếu shell/process auditing có thể ghi lại. Dùng cơ chế nhập password an toàn hoặc secret-safe execution environment.

### 9.3. Kiểm tra TLS handshake

~~~bash
openssl s_client -connect broker-1.example.net:9094 -servername broker-1.example.net -verify_return_error -CAfile ca-chain.pem
~~~

-servername truyền SNI; -verify_return_error khiến lỗi xác minh CA được trả về rõ ràng. Kết quả cần xác nhận chain hợp lệ và certificate đúng hostname. Lệnh này kiểm tra TLS server side; nếu broker yêu cầu mTLS, cần thêm client certificate và private key phù hợp.

### 9.4. Kiểm tra SCRAM/ACL

Sau khi đổi credential:

1. Tạo kết nối mới bằng principal mới.
2. Gửi một record vào topic được cấp quyền.
3. Đọc record bằng consumer group đã cấp quyền.
4. Thử truy cập topic ngoài phạm vi để xác nhận bị từ chối.
5. Kiểm tra broker log để biết principal thực tế.
6. Kiểm tra ACL và audit để chắc chắn principal cũ đã ngừng hoạt động.

Không chỉ kiểm tra client có thể bootstrap. Phải kiểm tra đúng operation nghiệp vụ như produce, consume, commit offset, transaction hoặc Connect task.

## 10. Bảo mật Kafka Connect, Streams và KRaft

### 10.1. Kafka Connect

Kafka Connect worker dùng client config để truy cập Kafka internal topics. Connector có thể có credential riêng để kết nối database, object storage hoặc API.

- Bảo vệ worker config và REST API.
- Dùng ConfigProvider để lấy connector secret từ nguồn ngoài.
- Cấp ACL riêng cho config/offset/status topics và business topics.
- Đồng bộ secret provider plugin và quyền file trên tất cả worker.
- Tránh ghi connector config có resolved password vào log.
- Rotate database credential của connector độc lập với Kafka worker credential.

### 10.2. Kafka Streams

Kafka Streams sử dụng Kafka producer/consumer bên trong ứng dụng. Cấu hình security.protocol, SASL, TLS và credential provider phải được cấp như một client application bình thường.

Principal của Streams cần quyền đọc input topics, ghi output topics, truy cập consumer group và các internal repartition/changelog topics. Không dùng principal admin để tránh phải cấu hình ACL.

### 10.3. KRaft controller và metadata

KRaft controller giữ metadata log chứa thông tin cluster như topic metadata, ACL và SCRAM credentials theo cơ chế mặc định. Bảo vệ controller listener và network giữa broker-controller; giới hạn truy cập storage, backup và host.

Kafka không tự mã hóa log segment, index, snapshot hoặc controller metadata trên đĩa. Nếu yêu cầu bảo mật dữ liệu at rest, dùng encryption ở filesystem/block device hoặc storage layer, mã hóa backup và bảo vệ KMS key. TLS chỉ bảo vệ đường truyền.

## 11. Lịch rotation và automation

Không chờ tới ngày hết hạn mới bắt đầu rotate. Xây lịch theo loại credential:

| Tài sản | Tín hiệu cần rotate | Cách quản lý |
|---|---|---|
| SCRAM password | Theo policy, nghi ngờ lộ hoặc thay owner | Principal mới/overlap, rolling client |
| OAuth client secret | Gần hết hạn hoặc bị lộ | Tạo secret mới ở IdP, cập nhật client, revoke secret cũ |
| OAuth token | Gần hết hạn | Refresh tự động trước expiry |
| Broker certificate | Trước notAfter hoặc thay CA/key | Trust overlap, update keystore từng listener |
| Client mTLS certificate | Trước notAfter hoặc thay identity | Trust overlap, rolling client |
| CA root/intermediate | Theo PKI lifecycle | Phân phối trust trước, thay leaf sau, gỡ CA cũ cuối cùng |
| Admin credential | Theo policy và khi có thay đổi nhân sự | Tách admin principal, audit và revoke |

Automation nên:

- Đọc ngày hết hạn từ certificate inventory.
- Cảnh báo trước các mốc 90/60/30/7 ngày theo policy.
- Tạo ticket cho owner và gắn service phụ thuộc.
- Tạo secret version mới, không ghi đè mù giá trị cũ.
- Triển khai theo canary/rolling và xác minh từng broker/client.
- Ghi audit event nhưng không ghi secret value.
- Chỉ revoke bản cũ sau khi health check thành công.

Không rotate đồng loạt tất cả broker, controller và client trong một lần. Chia nhỏ phạm vi để có thể xác định node hoặc service gây lỗi và rollback.

## 12. Xử lý khi secret hoặc certificate bị lộ

Khi nghi ngờ credential bị lộ:

1. Xác định principal, private key hoặc token nào bị ảnh hưởng.
2. Xác định service, group, topic, listener và môi trường sử dụng.
3. Tạo credential mới hoặc certificate mới từ nguồn tin cậy.
4. Cấp ACL tối thiểu cho principal mới và chuyển workload.
5. Thu hồi ACL, SCRAM credential, token hoặc certificate cũ.
6. Nếu private key CA/root bị lộ, thực hiện quy trình incident PKI; chỉ đổi leaf certificate là chưa đủ.
7. Kiểm tra audit log, broker log, network flow và các hành động bất thường.
8. Kiểm tra Git history, CI logs, container images, backups và artifact để tìm bản sao secret.
9. Đánh giá dữ liệu đã bị đọc/ghi trái phép và thông báo theo incident policy.
10. Lưu timeline, nguyên nhân, phạm vi và biện pháp ngăn tái diễn.

Thu hồi password hoặc certificate không tự xóa dữ liệu đã bị truy cập. Cần kiểm tra audit và business data để đánh giá ảnh hưởng.

## 13. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| SSLHandshakeException | CA không được trust, certificate hết hạn, SAN sai, chain thiếu | Xem certificate, truststore, hostname và system clock |
| No subject alternative DNS name matching | SAN không khớp hostname trong bootstrap/advertised listener | Kiểm tra DNS, advertised.listeners và SAN |
| PKIX path building failed | Thiếu root/intermediate CA hoặc truststore sai | Kiểm tra chain và truststore đang được client dùng |
| UnrecoverableKeyException | Sai keystore/key password hoặc sai store type | Kiểm tra PKCS12/JKS, ssl.keystore.password, ssl.key.password |
| SaslAuthenticationException | Username/password sai, mechanism không bật hoặc listener sai | Kiểm tra principal, credential version, SASL mechanism và listener prefix |
| TopicAuthorizationException | Principal xác thực được nhưng thiếu ACL | Kiểm tra principal, topic, operation và ACL |
| GroupAuthorizationException | Thiếu quyền trên consumer group | Cấp READ cho group cần dùng |
| ConfigProvider không resolve | Alias/class sai, file không tồn tại hoặc provider không có quyền đọc | Kiểm tra config.providers, classpath, allowed.paths và file permission |
| Kết nối cũ vẫn chạy sau rotate | Connection đã xác thực trước khi credential đổi | Rolling restart/recreate client và theo dõi principal |
| Một broker lỗi sau CA rotation | Trust overlap thiếu hoặc keystore/truststore update sai thứ tự | Kiểm tra CA cũ/mới trên tất cả peer và controller |

### 13.1. Lỗi hostname verification

Không tắt ssl.endpoint.identification.algorithm để chữa lỗi SAN. Kiểm tra hostname mà client thật sự kết nối, DNS alias, advertised.listeners và SAN của certificate. Với load balancer, mọi broker endpoint mà client nhận từ metadata đều cần certificate hợp lệ.

### 13.2. Lỗi sau khi rotate password

Kiểm tra:

- Service đã đọc secret version mới chưa?
- Kafka client instance đã được recreate chưa?
- Username và SCRAM mechanism có đúng không?
- Secret có bị escape sai trong JAAS string không?
- Principal mới đã được tạo trong KRaft metadata chưa?
- ACL của principal mới đã đủ cho operation cần thiết chưa?

Nếu connection mới thành công nhưng request bị authorization denied, lỗi nằm ở ACL chứ không phải password.

### 13.3. Lỗi sau khi rotate certificate

Kiểm tra:

- Certificate mới có đúng SAN và EKU không?
- Chain có đầy đủ intermediate CA không?
- Truststore của peer đã có CA mới chưa?
- Broker đã nhận dynamic config/restart thành công chưa?
- Client có đang dùng connection cũ không?
- Clock của broker/client có lệch quá lớn không?
- Với inter-broker listener, certificate mới có được trust bởi truststore hiện tại không?

## 14. Checklist trước và sau rotation

### Trước rotation

- [ ] Có owner và inventory cho secret/certificate.
- [ ] Xác định đầy đủ broker, controller, client, Connect và Streams phụ thuộc.
- [ ] Có credential/certificate mới và đã kiểm tra hạn, chain, SAN, key usage.
- [ ] Truststore đã có CA mới trước khi thay certificate nếu đổi CA.
- [ ] ACL cho principal mới đã được cấp tối thiểu.
- [ ] Secret mới đã được lưu ở secret manager và quyền truy cập đã kiểm tra.
- [ ] Có kế hoạch canary, rolling, rollback và thời gian quan sát.
- [ ] Có admin access dự phòng để sửa cấu hình nếu rotation thất bại.

### Sau rotation

- [ ] Client mới xác thực thành công.
- [ ] Produce/consume/commit hoặc transaction hoạt động đúng.
- [ ] Broker/controller quorum và replication khỏe mạnh.
- [ ] Không còn TLS/SASL/authz error bất thường.
- [ ] Service cũ đã ngừng dùng credential cũ.
- [ ] Principal/credential/certificate cũ đã được revoke đúng thời điểm.
- [ ] CA cũ chỉ bị gỡ khi không còn certificate phụ thuộc.
- [ ] Audit log có rotation event nhưng không chứa secret value.
- [ ] Certificate inventory và secret version được cập nhật.

## 15. Bài thực hành và tự kiểm tra

### Thực hành A — TLS và SAN

1. Tạo CA lab và certificate broker có SAN DNS phù hợp với địa chỉ client kết nối.
2. Tạo PKCS12 keystore và truststore.
3. Cấu hình broker listener TLS.
4. Cấu hình console producer/consumer dùng truststore.
5. Dùng openssl s_client kiểm tra chain và hostname.
6. Thử kết nối bằng hostname không có trong SAN và quan sát lỗi xác minh.
7. Khôi phục SAN đúng và xác nhận kết nối thành công.

### Thực hành B — SCRAM và ACL

1. Tạo principal svc-orders-v1 với SCRAM-SHA-512.
2. Cấp ACL producer chỉ trên topic orders.v1.
3. Kết nối bằng SASL_SSL và gửi record.
4. Thử ghi topic khác để xác nhận bị từ chối.
5. Tạo svc-orders-v2, cấp ACL cần thiết và lưu password vào secret manager.
6. Rolling restart producer sang principal mới.
7. Xác nhận traffic hoạt động rồi thu hồi principal cũ.

### Thực hành C — Certificate rotation với trust overlap

1. Tạo CA mới và leaf certificate mới.
2. Thêm CA mới vào truststore, giữ CA cũ.
3. Cập nhật broker certificate từng node/listener theo quy trình của phiên bản Kafka.
4. Tạo connection mới và xác nhận certificate mới được trình bày.
5. Cập nhật client mTLS certificate nếu có.
6. Drain connection cũ.
7. Gỡ CA cũ sau khi toàn bộ client/broker đã chuyển đổi.

### Thực hành D — ConfigProvider cho Kafka Connect

1. Tạo file properties chứa credential database trong thư mục secret mount.
2. Cấu hình FileConfigProvider và allowed.paths.
3. Tạo connector dùng placeholder cho username/password.
4. Kiểm tra connector chạy và REST config không làm lộ secret.
5. Thay secret version và restart/reconfigure connector theo cách plugin hỗ trợ.
6. Kiểm tra log, quyền file và audit.

### Câu hỏi tự kiểm tra

1. Encryption in transit, authentication và authorization khác nhau như thế nào?
2. Vì sao chỉ bật SASL mà không cấu hình authorizer chưa đủ?
3. Keystore và truststore khác nhau ở dữ liệu nào?
4. SAN liên quan thế nào tới advertised.listeners?
5. Khi nào cần mTLS và broker phải cấu hình gì để bắt buộc client certificate?
6. Vì sao SASL/PLAIN và SCRAM nên chạy qua TLS?
7. KRaft lưu SCRAM credential ở đâu?
8. Vì sao tạo principal mới giúp rotation ít gián đoạn hơn đổi password cùng username?
9. Vì sao phải cấp ACL cho principal mới trước khi chuyển client?
10. Vì sao phải thêm CA mới vào truststore trước khi thay leaf certificate?
11. Dynamic keystore/truststore update của broker có tác dụng ngay trên connection đã mở không?
12. ConfigProvider của Kafka Connect khác cách Java client lấy secret thế nào?
13. Vì sao super.users cần được bảo vệ như root credential?
14. Kafka có tự mã hóa log segment và controller metadata trên đĩa không?
15. Cần làm gì khi private key hoặc SCRAM credential bị lộ?

## Kết luận

Quản lý secret trong Kafka là một vòng đời liên tục gồm inventory, cấp phát, phân quyền, rotate, xác minh và revoke. TLS bảo vệ đường truyền; SASL hoặc mTLS xác thực principal; StandardAuthorizer và ACL giới hạn operation. Khi rotate SCRAM, principal mới cho phép chuyển client theo từng đợt trước khi thu hồi principal cũ. Khi rotate certificate, trust overlap giúp broker, controller và client tiếp tục tin nhau trong giai đoạn đổi CA. Kafka Connect có ConfigProvider để tham chiếu secret bên ngoài, còn Java client cần tích hợp secret manager ở cấp ứng dụng. Mọi rotation phải có health check, audit, rollback và xác nhận không còn workload sử dụng credential cũ.

## Tài liệu tham khảo

- [Apache Kafka 4.4 — Security Model](https://kafka.apache.org/44/security/security-model/)
- [Apache Kafka 4.4 — Encryption and Authentication using SSL](https://kafka.apache.org/44/security/encryption-and-authentication-using-ssl/)
- [Apache Kafka 4.4 — Authentication using SASL](https://kafka.apache.org/44/security/authentication-using-sasl/)
- [Apache Kafka 4.4 — Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/)
- [Apache Kafka 4.4 — Broker Configs](https://kafka.apache.org/44/configuration/broker-configs/)
- [Apache Kafka 4.4 — Kafka Connect Configs](https://kafka.apache.org/44/configuration/kafka-connect-configs/)
- [Apache Kafka 4.4 — Configuration Providers](https://kafka.apache.org/44/configuration/configuration-providers/)
