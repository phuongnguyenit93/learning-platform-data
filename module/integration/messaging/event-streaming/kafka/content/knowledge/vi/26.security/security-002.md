# TLS cho client, broker và controller

Kafka truyền dữ liệu qua mạng giữa client, broker và các controller của KRaft. Nếu các kết nối này không được mã hóa, record, credential hoặc metadata có thể bị quan sát trên đường truyền. TLS (Transport Layer Security) tạo kênh mã hóa, xác thực máy chủ và, khi cấu hình mutual TLS (mTLS), xác thực cả client bằng chứng chỉ.

Trong Kafka, bật TLS cho một listener không có nghĩa mọi luồng mạng trong cluster đều đã được bảo vệ. Cần xác định riêng các kết nối client-to-broker, broker-to-broker và broker/controller-to-controller. Với KRaft, controller listener cũng phải được cấu hình đúng để bảo vệ traffic điều khiển và quorum.

TLS cung cấp bảo mật ở tầng transport. ACL vẫn quyết định principal được phép đọc topic, ghi topic, tạo topic hoặc thực hiện thao tác quản trị nào. Mã hóa đường truyền không thay thế authorization, bảo mật dữ liệu lưu trữ hay quản lý secret.

## 1. TLS bảo vệ những gì?

TLS tạo một phiên kết nối có các thuộc tính chính:

- **Confidentiality:** mã hóa dữ liệu trên đường truyền để bên thứ ba không đọc được payload.
- **Integrity:** phát hiện dữ liệu bị thay đổi trong quá trình truyền.
- **Server authentication:** client xác minh broker/controller đang kết nối có chứng chỉ hợp lệ do CA tin cậy cấp.
- **Client authentication:** nếu bật mTLS, broker/controller xác minh chứng chỉ của client hoặc node kết nối đến.

Ví dụ các kết nối trong Kafka:

~~~mermaid
flowchart TB
    C["Java / Spring client"] -->|"TLS"| B1["Kafka broker 1"]
    C2["Kafka Connect / Streams"] -->|"TLS"| B2["Kafka broker 2"]
    B1 <-->|"Inter-broker TLS"| B2
    B1 <-->|"KRaft controller listener TLS"| K1["Controller 1"]
    B2 <-->|"KRaft controller listener TLS"| K2["Controller 2"]
    K1 <-->|"Controller quorum TLS"| K2
~~~

Cần bảo vệ từng đường kết nối theo yêu cầu triển khai. Nếu client kết nối qua external listener còn broker nội bộ dùng listener khác, mỗi listener có thể có certificate, truststore và chính sách client authentication riêng.

TLS bảo vệ dữ liệu khi đang truyền. Nó không tự mã hóa log segment, local state store, file cấu hình, backup hoặc dữ liệu đã ghi vào database. Những nơi đó cần cơ chế encryption-at-rest và kiểm soát quyền truy cập riêng.

## 2. One-way TLS và mutual TLS

### 2.1. One-way TLS

Trong one-way TLS, broker trình chứng chỉ máy chủ. Client xác minh certificate chain và hostname của broker.

Luồng:

1. Client kết nối tới broker hostname/port.
2. Broker gửi certificate chain.
3. Client xác minh certificate được ký bởi CA tin cậy và còn hiệu lực.
4. Client kiểm tra hostname kết nối khớp Subject Alternative Name (SAN).
5. Hai bên thương lượng cipher/protocol và tạo session key.
6. Dữ liệu Kafka được truyền qua kênh TLS đã mã hóa.

One-way TLS xác thực broker với client. Nếu listener không yêu cầu client certificate, broker không xác thực danh tính client bằng TLS certificate. Ứng dụng có thể dùng SASL hoặc một cơ chế xác thực khác, hoặc giới hạn quyền bằng cấu hình phù hợp.

### 2.2. Mutual TLS (mTLS)

Trong mTLS, hai bên đều trình certificate:

- Broker trình server certificate để client xác minh broker.
- Client trình client certificate để broker xác minh client.

Broker cấu hình `ssl.client.auth=required` trên listener SSL để bắt buộc client certificate. Broker cần truststore chứa CA đã cấp client certificate. Client vẫn cần truststore để xác minh server certificate và keystore chứa private key/client certificate của chính nó.

| Đặc điểm | One-way TLS | Mutual TLS |
|---|---|---|
| Client xác minh broker | Có | Có |
| Broker xác minh client bằng certificate | Không | Có |
| Client cần truststore | Có, nếu không dùng trust roots hệ điều hành | Có |
| Client cần keystore | Không bắt buộc | Có |
| Broker cần truststore cho client CA | Không bắt buộc nếu không xác thực client cert | Có |
| Danh tính client | Có thể dùng SASL hoặc cơ chế khác | Có thể lấy từ certificate principal |

Các giá trị phổ biến của `ssl.client.auth` ở phía broker:

| Giá trị | Hành vi |
|---|---|
| `none` | Không yêu cầu client certificate |
| `requested` | Yêu cầu client certificate nhưng chấp nhận client không gửi certificate |
| `required` | Bắt buộc client gửi certificate hợp lệ |

`requested` thường hữu ích trong giai đoạn chuyển đổi, nhưng không tương đương mTLS bắt buộc. Khi mục tiêu là xác thực mọi client bằng certificate, dùng `required` sau khi đã cấp certificate cho tất cả client hợp lệ.

## 3. Certificate, private key, keystore và truststore

Để cấu hình TLS, cần hiểu các thành phần:

- **Certificate:** chứa public key, subject, issuer, thời hạn và các thuộc tính xác thực.
- **Private key:** bí mật được dùng để chứng minh bên sở hữu certificate; không được gửi cho client khác.
- **CA (Certificate Authority):** tổ chức/hệ thống ký certificate.
- **Certificate chain:** certificate của server/client cùng intermediate CA dẫn tới root CA được tin cậy.
- **Keystore:** lưu private key và certificate chain của chính tiến trình.
- **Truststore:** lưu CA hoặc certificate mà tiến trình tin cậy khi xác minh peer.

Quy tắc ghi nhớ:

| Thành phần | Dùng để |
|---|---|
| Broker keystore | Broker trình server certificate và private key |
| Broker truststore | Broker xác minh client certificate trong mTLS hoặc peer certificate |
| Client truststore | Client xác minh broker certificate |
| Client keystore | Client trình certificate/private key khi mTLS |

Kafka/Java hỗ trợ nhiều định dạng keystore. PKCS12 (.p12, .pfx) thường là lựa chọn thuận tiện; JKS cũng có thể được sử dụng. Phải đặt `ssl.keystore.type` và `ssl.truststore.type` đúng với file thực tế.

Không nhầm truststore với keystore. Đưa private key của broker vào truststore của client là sai mô hình và làm tăng rủi ro lộ khóa.

## 4. SAN, hostname verification và certificate chain

Certificate hợp lệ về chữ ký vẫn có thể bị từ chối nếu hostname không khớp.

Ví dụ client kết nối tới:

~~~text
broker-1.kafka.example.net:9093
~~~

Server certificate cần có SAN phù hợp, chẳng hạn:

~~~text
DNS:broker-1.kafka.example.net
~~~

Nếu client kết nối bằng IP, certificate cần có IP SAN tương ứng. Không nên dựa vào Common Name cũ thay cho SAN.

Kafka client hỗ trợ hostname verification. Giữ cấu hình:

~~~properties
ssl.endpoint.identification.algorithm=https
~~~

Giá trị `https` bật kiểm tra hostname theo quy tắc endpoint identification của Java. Không đặt thành chuỗi rỗng chỉ để né lỗi certificate mismatch. Hãy sửa SAN hoặc địa chỉ trong `advertised.listeners`.

Certificate chain phải đầy đủ và được truststore tin cậy. Các lỗi thường gặp:

- Broker chỉ gửi leaf certificate nhưng thiếu intermediate CA.
- Client truststore chưa import CA đúng.
- Certificate hết hạn hoặc chưa đến thời điểm hiệu lực.
- SAN thiếu hostname được quảng bá.
- Dùng certificate cho clientAuth nhưng thiếu EKU serverAuth ở broker, hoặc ngược lại.
- Máy client/broker lệch đồng hồ đáng kể.

## 5. Cấu hình TLS cơ bản trên broker

Kafka broker có thể dùng SSL listener bằng cách ánh xạ listener name sang security protocol `SSL`.

Ví dụ cấu hình listener:

~~~properties
listeners=INTERNAL://0.0.0.0:9093
advertised.listeners=INTERNAL://broker-1.kafka.example.net:9093
listener.security.protocol.map=INTERNAL:SSL
inter.broker.listener.name=INTERNAL
~~~

TLS keystore và truststore:

~~~properties
ssl.keystore.location=/etc/kafka/secrets/broker-1.keystore.p12
ssl.keystore.type=PKCS12
ssl.keystore.password=<BROKER_KEYSTORE_PASSWORD>
ssl.key.password=<BROKER_PRIVATE_KEY_PASSWORD>

ssl.truststore.location=/etc/kafka/secrets/cluster.truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=<BROKER_TRUSTSTORE_PASSWORD>

ssl.enabled.protocols=TLSv1.2,TLSv1.3
ssl.client.auth=required
~~~

Đây là ví dụ mTLS cho listener broker. Nếu chỉ cần one-way TLS, có thể không cấu hình broker client authentication (`ssl.client.auth=none`) và không cần client certificate. Client vẫn phải xác minh certificate broker.

### 5.1. Listener-specific TLS configuration

Một broker có thể có nhiều listener, ví dụ `INTERNAL`, `EXTERNAL` và `CONTROLLER`. Có thể dùng cấu hình TLS mặc định `ssl.*` hoặc cấu hình riêng cho listener bằng prefix:

~~~properties
listener.name.internal.ssl.keystore.location=/etc/kafka/secrets/internal-broker.p12
listener.name.internal.ssl.truststore.location=/etc/kafka/secrets/internal-truststore.p12

listener.name.external.ssl.keystore.location=/etc/kafka/secrets/external-broker.p12
listener.name.external.ssl.truststore.location=/etc/kafka/secrets/external-truststore.p12
~~~

Tên listener trong prefix được viết thường. Cấu hình listener-specific cho phép dùng certificate hoặc trust policy riêng cho từng mạng. Kiểm tra precedence và các thuộc tính được hỗ trợ trong Kafka version đang triển khai.

Không đặt cùng một private key/certificate cho mọi broker nếu có thể cấp certificate riêng cho từng node. Certificate riêng giúp định danh node và giới hạn tác động khi một khóa bị lộ.

## 6. TLS giữa các broker

Broker-to-broker traffic có thể gồm replication fetch, metadata và các request nội bộ. Nếu listener nội bộ dùng SSL, các broker phải:

- Tin cậy CA cấp certificate của nhau.
- Có certificate/private key hợp lệ nếu listener yêu cầu mTLS.
- Kết nối tới hostname khớp SAN của peer.
- Dùng đúng listener name và security protocol.
- Có network route/firewall cho port nội bộ.

Vì broker vừa nhận kết nối TLS như server vừa mở kết nối tới broker khác như client, certificate dùng chung cho hai vai trò cần có extended key usage phù hợp cho cả `serverAuth` và `clientAuth`. Nếu tách certificate theo listener/role, cấp EKU đúng với vai trò của từng certificate.

Ví dụ dùng listener `INTERNAL` cho inter-broker communication:

~~~properties
listeners=INTERNAL://0.0.0.0:9093
advertised.listeners=INTERNAL://broker-1.kafka.example.net:9093
listener.security.protocol.map=INTERNAL:SSL
inter.broker.listener.name=INTERNAL
~~~

Khi đã dùng `inter.broker.listener.name`, không đồng thời cấu hình `security.inter.broker.protocol`. Đây là hai cách chọn security protocol cho inter-broker listener; cấu hình đồng thời sẽ gây xung đột.

Nếu cluster có cả listener nội bộ và external, chỉ quảng bá listener phù hợp cho client tương ứng. Không để client bên ngoài nhận địa chỉ broker nội bộ không thể định tuyến hoặc certificate không khớp hostname.

## 7. TLS cho KRaft controller listener và quorum

Trong KRaft, broker và controller trao đổi metadata qua controller listener. Các controller cũng trao đổi với nhau để duy trì metadata quorum. Bảo vệ controller listener bằng TLS để mã hóa và xác thực luồng điều khiển.

Ví dụ node kết hợp broker và controller trong môi trường lab:

~~~properties
process.roles=broker,controller
node.id=1

listeners=INTERNAL://0.0.0.0:9093,CONTROLLER://0.0.0.0:9094
advertised.listeners=INTERNAL://broker-1.kafka.example.net:9093

listener.security.protocol.map=INTERNAL:SSL,CONTROLLER:SSL
inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER

controller.quorum.voters=1@controller-1.kafka.example.net:9094,2@controller-2.kafka.example.net:9094,3@controller-3.kafka.example.net:9094
~~~

Trong ví dụ, `INTERNAL` bảo vệ inter-broker traffic và `CONTROLLER` bảo vệ broker/controller cùng controller quorum traffic. `advertised.listeners` chỉ quảng bá broker listener; controller listener không được đưa vào danh sách advertised client listeners.

Mỗi node cần cấu hình certificate/trust phù hợp với listener mà node phục vụ. Nếu dùng mTLS, controller phải tin cậy certificate của broker kết nối vào controller listener, và các controller phải tin cậy certificate của nhau.

### 7.1. Listener-specific certificate cho controller

Ví dụ cấu hình keystore/truststore riêng cho controller listener:

~~~properties
listener.name.controller.ssl.keystore.location=/etc/kafka/secrets/controller-1.p12
listener.name.controller.ssl.keystore.type=PKCS12
listener.name.controller.ssl.keystore.password=<CONTROLLER_KEYSTORE_PASSWORD>
listener.name.controller.ssl.key.password=<CONTROLLER_PRIVATE_KEY_PASSWORD>

listener.name.controller.ssl.truststore.location=/etc/kafka/secrets/controller-truststore.p12
listener.name.controller.ssl.truststore.type=PKCS12
listener.name.controller.ssl.truststore.password=<CONTROLLER_TRUSTSTORE_PASSWORD>
listener.name.controller.ssl.client.auth=required
~~~

Tương tự, `listener.name.internal.ssl.*` có thể cấu hình riêng cho inter-broker listener. Nếu broker/controller dùng chung certificate, SAN phải bao gồm tất cả hostname mà peer dùng để kết nối. Tách certificate theo role/listener thường giúp quản lý quyền và xoay vòng rõ ràng hơn.

### 7.2. Broker-only và controller-only nodes

Với cluster tách role:

- Broker-only node bind broker listener và cấu hình `controller.listener.names` để kết nối tới controller quorum.
- Controller-only node bind controller listener và không cần quảng bá broker listener cho client.
- Các controller phải có quorum voter endpoint và certificate SAN khớp hostname trong voter endpoint.
- Broker và controller phải thống nhất listener name/security protocol map.

Không sao chép nguyên cấu hình combined-role sang dedicated-role mà không chỉnh `process.roles`, `listeners`, `advertised.listeners` và endpoint theo đúng vai trò node.

## 8. Kết hợp SSL và SASL_SSL

Kafka có hai lựa chọn thường gặp:

| Protocol | Ý nghĩa |
|---|---|
| `SSL` | TLS bảo vệ kết nối; có thể dùng mTLS để xác thực client bằng certificate |
| `SASL_SSL` | TLS mã hóa đường truyền kết hợp SASL authentication |

`SSL` với mTLS phù hợp khi muốn dùng certificate làm danh tính client. `SASL_SSL` phù hợp khi cần SASL mechanism như SCRAM hoặc OAUTHBEARER trên kênh TLS.

Ví dụ client dùng SASL_SSL sẽ có dạng:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=<SASL_LOGIN_CONFIGURATION>

ssl.truststore.location=/etc/kafka/secrets/client.truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=<CLIENT_TRUSTSTORE_PASSWORD>
ssl.endpoint.identification.algorithm=https
~~~

TLS vẫn cần truststore để xác minh broker. SASL credentials không thay thế TLS server certificate. Nếu hệ thống kết hợp thêm client certificate, cần hiểu rõ principal được Kafka dùng cho authorization và cấu hình listener tương ứng; không giả định mọi danh tính được gộp tự động.

## 9. Cấu hình Java producer, consumer và AdminClient

Các Kafka Java clients dùng chung cấu hình security cơ bản.

### 9.1. Client dùng one-way TLS

~~~java
Properties props = new Properties();

props.put("bootstrap.servers",
    "broker-1.kafka.example.net:9093,broker-2.kafka.example.net:9093");
props.put("security.protocol", "SSL");

props.put("ssl.truststore.location",
    "/etc/app/secrets/kafka.truststore.p12");
props.put("ssl.truststore.type", "PKCS12");
props.put("ssl.truststore.password", truststorePassword);

props.put("ssl.endpoint.identification.algorithm", "https");
props.put("ssl.enabled.protocols", "TLSv1.2,TLSv1.3");
~~~

Producer, consumer và AdminClient có thể dùng các property này. Mỗi client vẫn cần các cấu hình riêng như serializers, group ID hoặc request timeout.

### 9.2. Client dùng mTLS

Bổ sung client keystore:

~~~java
props.put("ssl.keystore.location",
    "/etc/app/secrets/orders-client.p12");
props.put("ssl.keystore.type", "PKCS12");
props.put("ssl.keystore.password", keystorePassword);
props.put("ssl.key.password", privateKeyPassword);
~~~

Client truststore xác minh broker. Client keystore cho phép broker xác minh client. Không chia sẻ một client private key cho tất cả ứng dụng; cấp certificate riêng theo service hoặc workload để có thể thu hồi và audit từng principal.

### 9.3. Dùng chung cấu hình cho nhiều client

Ví dụ tạo AdminClient:

~~~java
try (AdminClient admin = AdminClient.create(props)) {
    var cluster = admin.describeCluster();
    System.out.println(cluster.clusterId().get());
}
~~~

Tương tự, có thể truyền properties cho `KafkaProducer` và `KafkaConsumer`. Bảo đảm client truststore/keystore được mount ở đúng đường dẫn và process có quyền đọc file.

## 10. Cấu hình TLS trong Spring Boot

Spring Boot có thể cấu hình security properties chung cho Kafka clients:

~~~properties
spring.kafka.bootstrap-servers=broker-1.kafka.example.net:9093,broker-2.kafka.example.net:9093

spring.kafka.properties.security.protocol=SSL
spring.kafka.properties.ssl.truststore.location=/etc/app/secrets/kafka.truststore.p12
spring.kafka.properties.ssl.truststore.type=PKCS12
spring.kafka.properties.ssl.truststore.password=<CLIENT_TRUSTSTORE_PASSWORD>
spring.kafka.properties.ssl.endpoint.identification.algorithm=https
spring.kafka.properties.ssl.enabled.protocols=TLSv1.2,TLSv1.3
~~~

Với mTLS, bổ sung:

~~~properties
spring.kafka.properties.ssl.keystore.location=/etc/app/secrets/orders-client.p12
spring.kafka.properties.ssl.keystore.type=PKCS12
spring.kafka.properties.ssl.keystore.password=<CLIENT_KEYSTORE_PASSWORD>
spring.kafka.properties.ssl.key.password=<CLIENT_PRIVATE_KEY_PASSWORD>
~~~

Các property chung có thể được dùng bởi producer, consumer và admin client do Spring Boot tạo. Nếu một component cần security setting riêng, dùng cấu hình riêng cho producer/consumer/admin và kiểm tra property precedence của phiên bản Spring Boot đang chạy.

Kafka Streams, Kafka Connect, MirrorMaker và các công cụ quản trị có cấu hình client riêng. Không giả định việc cấu hình `spring.kafka.*` tự động bảo vệ một Connect worker hoặc một process khác.

## 11. Tạo và phân phối truststore

Một quy trình certificate thông thường:

1. Tạo hoặc nhận CA nội bộ từ hệ thống PKI của tổ chức.
2. Tạo private key và CSR riêng cho từng broker, controller hoặc client.
3. Đưa hostname/IP cần dùng vào SAN.
4. CA ký CSR với extended key usage phù hợp (serverAuth/clientAuth).
5. Đóng gói private key và certificate chain vào PKCS12 keystore của node/client.
6. Import CA root/intermediate vào truststore của các peer cần tin cậy.
7. Cấp file cho đúng workload qua secret manager hoặc cơ chế mount an toàn.
8. Xác minh chain, SAN, thời hạn và quyền đọc file trước khi khởi động.

Ví dụ import CA vào truststore PKCS12:

~~~bash
keytool -importcert \
  -alias kafka-root-ca \
  -file kafka-root-ca.crt \
  -keystore client.truststore.p12 \
  -storetype PKCS12
~~~

Kiểm tra nội dung keystore/truststore:

~~~bash
keytool -list -v \
  -keystore client.truststore.p12 \
  -storetype PKCS12
~~~

Lệnh import CA không tạo server certificate và không nhập private key. Keystore của broker/client phải chứa private key tương ứng với certificate đã được CA ký.

Không commit keystore, private key, password hoặc file secret vào Git. Dùng secret manager, quyền file tối thiểu và quy trình cấp phát có audit.

## 12. Principal và ACL khi dùng mTLS

Khi SSL client authentication được bật, Kafka có thể lấy principal từ subject DN của client certificate. `ssl.principal.mapping.rules` cho phép ánh xạ DN sang tên principal phù hợp với quy ước tổ chức.

Ví dụ DN certificate:

~~~text
CN=orders-service,OU=Applications,O=Example Corp
~~~

Có thể ánh xạ thành principal dễ quản lý như `orders-service`, tùy rule và cấu hình Kafka. Cần kiểm thử mapping thực tế trong broker log trước khi cấp ACL.

TLS xác minh danh tính và mã hóa kết nối. Authorizer/ACL mới quyết định principal được phép làm gì:

- Producer cần quyền WRITE/DESCRIBE trên topic.
- Consumer cần READ/DESCRIBE trên topic và quyền READ trên group.
- Admin automation cần quyền quản trị đúng resource.
- Broker/controller cần quyền và cấu hình nội bộ phù hợp với cluster mode.

Không cấp quyền `*` hoặc quyền cluster-wide chỉ để xử lý một lỗi TLS. Nếu handshake thành công nhưng thao tác bị từ chối, kiểm tra principal và ACL thay vì thay certificate.

## 13. Certificate rotation không gián đoạn

Certificate có thời hạn. Nếu để hết hạn, client hoặc node có thể không kết nối được. Xoay vòng cần có giai đoạn hai CA/certificate cùng được tin cậy.

Quy trình an toàn thường là:

1. Cấp CA/certificate mới và xác minh SAN/EKU.
2. Cập nhật truststore của peer để tin cậy CA mới trong khi CA cũ vẫn còn.
3. Phân phối truststore mới theo đợt.
4. Thay certificate/keystore của từng broker hoặc controller theo rolling procedure phù hợp.
5. Xác minh handshake, replication, controller quorum và client traffic sau mỗi node.
6. Xoay certificate của các client/workload.
7. Chờ tất cả peer chuyển sang chain mới.
8. Gỡ CA cũ khỏi truststore sau khi chắc chắn không còn certificate cũ đang được sử dụng.

Không thay CA trust và leaf certificate đồng thời trên toàn cluster nếu chưa có kế hoạch rollback. Nếu peer chưa tin CA mới, handshake sẽ thất bại.

Việc reload SSL material có thể phụ thuộc Kafka version và loại cấu hình. Một số cấu hình hỗ trợ cập nhật động; một số triển khai cần restart/reload broker hoặc client. Kiểm tra khả năng dynamic update của phiên bản cụ thể và dùng rolling restart nếu cần. Không giả định đổi file trên disk sẽ tự động được JVM nạp lại.

## 14. Kiểm tra TLS trước khi kết nối Kafka

Dùng OpenSSL kiểm tra server certificate và chain:

~~~bash
openssl s_client \
  -connect broker-1.kafka.example.net:9093 \
  -servername broker-1.kafka.example.net \
  -showcerts \
  -verify_return_error
~~~

Kiểm tra:

- Certificate chain có đầy đủ không.
- CA có được tin cậy không.
- Certificate còn hiệu lực không.
- SAN có khớp hostname không.
- TLS protocol/cipher có được thương lượng không.

Lệnh trên kiểm tra TLS handshake ở tầng mạng; nó không xác minh Kafka protocol, SASL, principal mapping hay ACL. Sau khi TLS pass, dùng Kafka CLI hoặc một ứng dụng thử nghiệm với cùng security properties để xác minh Kafka authentication và authorization.

Với mTLS, cần cung cấp client certificate/private key cho công cụ kiểm tra, ví dụ tham số `-cert` và `-key` của OpenSSL. Không đưa private key vào command history hoặc log dùng chung.

## 15. Những lỗi TLS thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `PKIX path building failed` | Client không tin CA hoặc thiếu intermediate certificate | Cập nhật truststore và certificate chain |
| `No subject alternative DNS name matching` | SAN không khớp hostname broker được quảng bá | Sửa SAN hoặc advertised.listeners |
| `SSLHandshakeException` | Protocol/cipher mismatch, certificate hoặc client-auth không hợp lệ | Kiểm tra handshake log, TLS version và trust |
| `bad_certificate` | Peer gửi certificate không được tin cậy hoặc sai EKU | Kiểm tra CA, EKU, validity và truststore |
| `certificate_required` | Listener yêu cầu mTLS nhưng client không gửi certificate | Cấp client keystore và cấu hình đúng |
| Broker không thể replicate | Inter-broker listener hoặc truststore sai | Kiểm tra listener map, keystore, SAN và network |
| KRaft controller quorum mất kết nối | Controller listener TLS không tương thích hoặc certificate hết hạn | Kiểm tra controller listener, voter endpoint và certificate |
| TLS handshake thành công nhưng bị `TopicAuthorizationException` | Principal không có ACL phù hợp | Kiểm tra principal mapping và ACL |
| Client kết nối được một broker nhưng fail broker khác | Certificate/SAN/truststore giữa các broker không đồng nhất | Kiểm tra từng advertised broker endpoint |
| Thay certificate nhưng process vẫn dùng certificate cũ | SSL material chưa được reload | Kiểm tra dynamic config support hoặc rolling restart |
| Kết nối chỉ lỗi ở production | DNS, proxy, firewall hoặc certificate chain khác môi trường test | Kiểm tra endpoint thực tế và đường mạng |

## 16. TLS cho các thành phần Kafka khác

Mỗi process Kafka client cần security properties phù hợp:

| Thành phần | Kết nối cần bảo vệ |
|---|---|
| Java/Spring producer | Client tới broker |
| Java/Spring consumer | Client tới broker |
| AdminClient | Client tới broker/controller qua API được hỗ trợ |
| Kafka Connect worker | Worker tới broker và các hệ thống đích/nguồn nếu connector hỗ trợ TLS |
| Kafka Streams | Internal producer/consumer tới broker |
| MirrorMaker | Source cluster và target cluster |
| Monitoring/exporter | Client tới broker hoặc endpoint quản trị |

Kafka Connect có thể cần cấu hình TLS riêng cho worker producer/consumer/admin client và connector plugin. TLS kết nối từ connector tới database/REST API là một kênh khác, cần cấu hình riêng trong plugin.

Kafka Streams dùng các producer/consumer nội bộ; cấu hình security của Streams application phải được truyền vào client properties. Không chỉ kiểm tra producer bên ngoài mà quên internal clients.

## 17. Checklist triển khai TLS

- [ ] Đã xác định mọi luồng client-to-broker, broker-to-broker và KRaft controller.
- [ ] Listener name được ánh xạ đúng sang `SSL` hoặc `SASL_SSL`.
- [ ] Keystore chứa private key và certificate chain của đúng node/client.
- [ ] Truststore chứa CA tin cậy cần thiết.
- [ ] SAN khớp hostname trong bootstrap và advertised.listeners.
- [ ] Hostname verification được bật.
- [ ] TLS protocol/cipher phù hợp chính sách bảo mật.
- [ ] Đã chọn rõ one-way TLS hay mTLS.
- [ ] Nếu mTLS, client certificate được yêu cầu và trust đúng CA.
- [ ] Inter-broker listener sử dụng TLS nhất quán trên các broker.
- [ ] KRaft controller listener và quorum traffic được bảo vệ.
- [ ] Controller listener không được quảng bá như client listener.
- [ ] Broker/controller nodes có certificate và truststore phù hợp với role.
- [ ] Principal mapping và ACL được kiểm tra riêng.
- [ ] Kafka Connect, Streams, MirrorMaker và AdminClient có security config riêng.
- [ ] Secret không được lưu trong Git hoặc log.
- [ ] Có lịch theo dõi expiry và quy trình rotation/rollback.
- [ ] Đã kiểm thử handshake, replication, quorum và authorization.

TLS bảo vệ các kết nối Kafka bằng mã hóa và xác thực certificate. Cần cấu hình đúng từng listener cho client, broker và KRaft controller; kiểm tra SAN theo hostname được quảng bá; và quản lý truststore/keystore theo từng node hoặc workload. Khi dùng mTLS, certificate giúp xác định client nhưng ACL vẫn quyết định quyền truy cập. Một triển khai an toàn còn cần xoay vòng certificate có giai đoạn chồng lấp, giám sát expiry và kiểm thử cả handshake lẫn hoạt động replication/quorum sau thay đổi.
