# mTLS và định danh bằng chứng chỉ

Mutual TLS (mTLS) là cơ chế TLS trong đó cả client và server đều trình certificate để xác thực danh tính. Với Kafka, broker xác thực certificate của producer, consumer, Kafka Connect worker hoặc ứng dụng Kafka Streams; client đồng thời xác thực certificate của broker để tránh kết nối nhầm endpoint.

mTLS cung cấp mã hóa dữ liệu trên đường truyền và xác thực peer ở cấp kết nối. Certificate hợp lệ không tự cấp quyền đọc hoặc ghi topic. Kafka cần ánh xạ certificate thành principal rồi áp dụng ACL để quyết định principal đó được phép làm gì.

Bài học này trình bày PKI, CA, certificate chain, keystore và truststore; cấu hình mTLS trên broker/listener, client Java/Spring, Kafka Connect và Kafka Streams; cách ánh xạ Distinguished Name (DN) thành Kafka principal; cấp ACL, triển khai KRaft, xoay vòng certificate và xử lý lỗi handshake.

## 1. TLS và mTLS

### 1.1. TLS xác thực server

Trong kết nối TLS thông thường:

1. Client kết nối đến broker.
2. Broker gửi certificate server và certificate chain.
3. Client kiểm tra chữ ký chain bằng CA trong truststore.
4. Client kiểm tra thời hạn, mục đích sử dụng và hostname của broker.
5. Hai bên thương lượng khóa phiên và thuật toán mã hóa.
6. Kết nối được mã hóa.

Client biết mình đang nói chuyện với broker hợp lệ. Broker chưa nhất thiết biết danh tính client ở cấp certificate.

### 1.2. mTLS xác thực cả hai đầu

Với mTLS, broker yêu cầu client trình certificate:

1. Client xác thực certificate server như TLS thông thường.
2. Broker gửi yêu cầu client certificate.
3. Client gửi certificate và chứng minh sở hữu private key tương ứng.
4. Broker kiểm tra certificate chain của client bằng truststore của broker.
5. Broker xác định principal từ certificate DN hoặc principal builder tùy chỉnh.
6. Kafka authorization kiểm tra ACL của principal trước khi thực hiện request.

~~~mermaid
sequenceDiagram
    participant C as Kafka client
    participant B as Kafka broker
    C->>B: ClientHello
    B->>C: Server certificate
    C->>C: Xác minh chain và hostname bằng truststore
    C->>B: Client certificate + proof of private key
    B->>B: Xác minh client chain bằng truststore
    B->>B: DN -> Kafka principal
    B->>B: Kiểm tra ACL
    B-->>C: Cho phép request hoặc trả authorization error
~~~

CA không cần tham gia trực tuyến vào mỗi lần handshake nếu certificate đã được ký và chuỗi tin cậy đã có sẵn. TLS provider/JVM xác minh chữ ký và chain bằng trust material đã cấu hình.

### 1.3. Phân biệt mã hóa, xác thực và phân quyền

| Lớp | Câu hỏi được trả lời | Thành phần |
|---|---|---|
| Encryption | Dữ liệu trên mạng có bị đọc lén không? | TLS cipher và session key |
| Server authentication | Client có kết nối đúng broker không? | Broker certificate, client truststore, hostname verification |
| Client authentication | Broker có xác định được client không? | Client certificate, broker truststore, mTLS |
| Identity mapping | Certificate tương ứng principal nào? | DN, ssl.principal.mapping.rules, KafkaPrincipalBuilder |
| Authorization | Principal có quyền trên topic/group/cluster không? | Authorizer và ACL |

Handshake thành công không chứng minh client có quyền produce hoặc consume. Nếu certificate được chấp nhận nhưng ACL không cho phép thao tác, Kafka vẫn từ chối request.

## 2. PKI, CA và certificate chain

mTLS dựa trên Public Key Infrastructure (PKI). PKI quản lý việc phát hành, xác minh, gia hạn và thu hồi certificate.

### 2.1. CA là gì?

Certificate Authority (CA) là tổ chức hoặc hệ thống có quyền ký certificate. CA có cặp khóa public/private riêng:

- CA private key dùng để ký certificate.
- CA certificate chứa public key và thông tin định danh CA.
- Client và broker tin cậy CA certificate trong truststore.
- Certificate do CA ký được xác minh qua chữ ký số và chain of trust.

Trong môi trường doanh nghiệp, thường dùng corporate CA hoặc PKI service tập trung. Với lab, có thể tạo CA riêng để ký certificate thử nghiệm.

CA private key có quyền rất lớn. Nếu bị lộ, kẻ tấn công có thể phát hành certificate giả được mọi hệ thống tin CA đó chấp nhận. Vì vậy, CA private key cần được bảo vệ bằng HSM, quyền truy cập hạn chế hoặc quy trình ký tập trung; không phân phối CA private key cho broker hay ứng dụng.

### 2.2. Certificate của broker và client

Mỗi broker và mỗi workload client nên có certificate riêng.

| Thành phần | Subject/CN gợi ý | SAN / EKU |
|---|---|---|
| Broker 1 | broker-1 | SAN có DNS broker-1; serverAuth và clientAuth khi broker giao tiếp hai chiều |
| Broker 2 | broker-2 | SAN có DNS broker-2; serverAuth và clientAuth khi cần |
| Controller | controller-1 | SAN có endpoint controller; clientAuth/serverAuth theo vai trò |
| Order producer | orders-producer | clientAuth |
| Billing consumer | billing-consumer | clientAuth |
| Kafka Connect worker | connect-worker-1 | clientAuth |
| Kafka Streams app | order-streams | clientAuth |

Không nên dùng chung một client certificate cho mọi ứng dụng. Certificate riêng giúp xác định workload, cấp ACL theo nguyên tắc least privilege, thu hồi một client bị xâm phạm mà không ảnh hưởng client khác và theo dõi lịch sử kết nối.

### 2.3. Subject và Subject Alternative Name

Certificate X.509 có subject DN, ví dụ:

~~~text
CN=orders-producer,OU=KafkaClients,O=Example,C=VN
~~~

DN có thể được Kafka dùng làm principal. Tuy nhiên, DN không phải hostname của broker.

Hostname verification dựa trên Subject Alternative Name (SAN) trong certificate server. Ví dụ broker được truy cập bằng:

~~~text
broker-1.kafka.example.net
~~~

Certificate broker cần SAN tương ứng:

~~~text
DNS:broker-1.kafka.example.net
DNS:broker-1
IP:10.10.20.11
~~~

Nếu client kết nối bằng IP nhưng certificate chỉ có DNS SAN, hostname verification có thể thất bại. Hãy thiết kế advertised.listeners và SAN khớp với endpoint client thực sự sử dụng.

### 2.4. Extended Key Usage và Key Usage

Extended Key Usage (EKU) giới hạn certificate được dùng cho mục đích nào:

- serverAuth: xác thực server trong TLS.
- clientAuth: xác thực client trong TLS.

Client certificate thường cần clientAuth. Broker certificate cần serverAuth khi nhận kết nối client. Broker còn là TLS client khi kết nối broker khác hoặc controller; do đó certificate dùng cho inter-broker/controller communication có thể cần cả serverAuth và clientAuth.

Key Usage thường bao gồm digitalSignature; tùy loại khóa và thuật toán, có thể cần keyEncipherment hoặc keyAgreement. Hãy để PKI phát hành profile đúng cho Kafka thay vì tự sửa extension sau khi ký.

Kafka có thể từ chối handshake nếu CA chỉ phát hành broker certificate với serverAuth trong khi broker cũng phải đóng vai client để kết nối nội bộ cluster.

### 2.5. Certificate chain

Một certificate được ký bởi intermediate CA thường cần đi kèm intermediate certificate để tạo chuỗi đến root CA.

~~~text
Root CA
  |
  +-- Intermediate CA
        |
        +-- broker-1 certificate
        |
        +-- orders-producer certificate
~~~

Keystore của broker/client cần chứa private key và certificate chain phù hợp. Truststore cần chứa CA certificate mà bên đó tin cậy. Thiếu intermediate certificate có thể khiến JVM không xây dựng được chain dù certificate leaf còn hạn.

## 3. Keystore và truststore

### 3.1. Keystore giữ danh tính của chính mình

Keystore thường chứa private key của broker hoặc client, certificate leaf tương ứng và certificate chain dẫn đến CA. Private key phải được giữ bí mật. Không đưa keystore chứa private key lên source control, không gắn vào image công khai và không dùng chung giữa các môi trường.

### 3.2. Truststore giữ CA mà mình tin cậy

Truststore chứa CA certificate hoặc trust anchor dùng để xác minh certificate peer.

- Broker truststore chứa CA ký client certificates.
- Client truststore chứa CA ký broker certificates.
- Broker truststore cho inter-broker traffic chứa CA ký certificate của các broker peer.

Truststore không cần private key của CA. Chỉ phân phối public CA certificate.

Lưu ý về phạm vi tin cậy: khi import CA certificate vào truststore, broker tin các certificate hợp lệ được CA đó ký, không chỉ một leaf certificate cụ thể. Nếu nhiều nhóm workload có mức tin cậy khác nhau, hãy dùng CA hoặc truststore tách biệt theo trust domain, đồng thời ánh xạ principal và cấp ACL riêng cho từng workload.

### 3.3. Bảng cấu hình theo góc nhìn mỗi bên

| Thành phần | Keystore | Truststore |
|---|---|---|
| Kafka broker | Private key + broker certificate chain | CA ký client certificates và peer cần tin |
| Kafka producer | Private key + producer certificate chain | CA ký broker certificates |
| Kafka consumer | Private key + consumer certificate chain | CA ký broker certificates |
| Kafka Connect worker | Private key + worker certificate chain | CA ký broker certificates |
| Kafka Streams app | Private key + application certificate chain | CA ký broker certificates |

Trong mTLS, cả hai bên đều có keystore và truststore. Keystore trả lời “tôi là ai”; truststore trả lời “tôi tin certificate nào”.

### 3.4. JKS, PKCS12 và PEM

| Định dạng | Đặc điểm |
|---|---|
| JKS | Định dạng Java cũ, vẫn được hỗ trợ |
| PKCS12 | Định dạng tiêu chuẩn, phù hợp trao đổi giữa công cụ |
| PEM | Certificate và private key ở dạng text Base64; thuận tiện cho container và secret |

Với Kafka 4.4, default SSL engine factory hỗ trợ JKS, PKCS12 và PEM. PEM có giới hạn riêng: private key cần ở định dạng PKCS#8; truststore/keystore password không dùng như với JKS/PKCS12; private key được mã hóa cần cấu hình key password tương ứng.

## 4. TLS handshake và kiểm tra certificate

### 4.1. Broker xác minh client certificate

Broker cần truststore chứa CA đã ký client certificate. Khi nhận client certificate, TLS stack kiểm tra:

- Chữ ký certificate và certificate chain.
- Thời hạn notBefore/notAfter.
- CA có nằm trong truststore không.
- EKU và Key Usage có phù hợp không.
- Certificate có hợp lệ theo chính sách PKI/SSL provider đang triển khai không.
- Proof of possession có chứng minh client nắm private key tương ứng không.

Nếu client không gửi certificate trong khi broker yêu cầu, hoặc certificate không được tin cậy, TLS handshake thất bại trước khi Kafka request được xử lý.

### 4.2. Client xác minh broker certificate

Client cần truststore chứa CA ký broker certificate. Client cũng phải kiểm tra hostname của endpoint.

Kafka client mặc định dùng:

~~~properties
ssl.endpoint.identification.algorithm=https
~~~

Không nên đặt giá trị rỗng chỉ để bỏ qua lỗi hostname. Nếu hostname verification thất bại, hãy kiểm tra SAN, DNS, advertised.listeners và địa chỉ bootstrap thay vì tắt kiểm tra.

### 4.3. Certificate hết hạn và certificate bị thu hồi

Certificate hết hạn sẽ không còn hợp lệ. Certificate bị thu hồi có thể vẫn còn trong thời hạn nhưng đã bị CA/PKI vô hiệu hóa.

Phân biệt:
- Expiration: hết hạn theo notAfter.
- Revocation: bị thu hồi trước ngày hết hạn.
- Trust removal: bỏ CA khỏi truststore, khiến certificate thuộc CA đó không còn được tin.
- Key compromise: private key bị lộ, cần thu hồi certificate và thay khóa.

Cách kiểm tra CRL/OCSP phụ thuộc Kafka version, JVM, SSL engine factory và chính sách PKI. Không giả định chỉ thêm certificate vào truststore là đã có quy trình thu hồi hoàn chỉnh; hãy xác minh cơ chế revocation đang bật và được kiểm thử.

## 5. Bật mTLS trên Kafka broker

### 5.1. Tạo listener SSL

Kafka server hỗ trợ nhiều listener. Mỗi listener có tên, địa chỉ bind và security protocol.

~~~properties
listeners=CLIENT://0.0.0.0:9093
advertised.listeners=CLIENT://broker-1.kafka.example.net:9093
listener.security.protocol.map=CLIENT:SSL
inter.broker.listener.name=CLIENT
~~~

Trong production thường tách listener cho client traffic và broker-to-broker traffic. Cấu hình trên chỉ minh họa một listener SSL.

### 5.2. Cấu hình keystore và truststore của broker

Ví dụ dùng PKCS12:

~~~properties
listener.name.client.ssl.keystore.type=PKCS12
listener.name.client.ssl.keystore.location=/etc/kafka/tls/broker-1.p12
listener.name.client.ssl.keystore.password=<BROKER_STORE_PASSWORD>
listener.name.client.ssl.key.password=<BROKER_KEY_PASSWORD>

listener.name.client.ssl.truststore.type=PKCS12
listener.name.client.ssl.truststore.location=/etc/kafka/tls/client-ca.p12
listener.name.client.ssl.truststore.password=<CLIENT_CA_STORE_PASSWORD>

listener.name.client.ssl.client.auth=required
listener.name.client.ssl.enabled.protocols=TLSv1.2,TLSv1.3
~~~

Trong cấu hình listener-prefixed, tên listener được viết thường trong prefix: listener.name.client.ssl.*.

Nếu chỉ có một SSL listener, có thể dùng cấu hình ssl.* chung. Khi có nhiều listener và mỗi listener dùng certificate/truststore khác nhau, cấu hình theo listener giúp tách biệt trust boundary.

### 5.3. Ý nghĩa ssl.client.auth

| Giá trị | Hành vi |
|---|---|
| none | Không yêu cầu client certificate |
| requested | Yêu cầu client certificate nhưng cho phép client không gửi |
| required | Client bắt buộc phải gửi certificate hợp lệ |

Với listener cần mTLS, dùng required. Giá trị requested thường tạo cảm giác đã bật mTLS nhưng client cấu hình sai vẫn có thể kết nối mà không có certificate. Chỉ dùng requested khi thực sự cần chế độ tương thích có chủ đích.

### 5.4. Tách keystore theo listener

Nếu broker có listener client-facing và inter-broker, nên cân nhắc dùng keystore riêng. Điều này giảm hậu quả khi private key của listener client-facing bị lộ: key đó không thể được dùng để giả mạo broker trên listener nội bộ.

Cũng có thể dùng truststore riêng cho từng listener để chỉ chấp nhận CA phù hợp với nhóm client tương ứng.

## 6. mTLS cho inter-broker communication

Broker giao tiếp với broker khác để replication partition, đồng bộ metadata và thực hiện các hoạt động cluster. Nếu dùng mTLS, mỗi broker phải có certificate và truststore để xác thực peer.

~~~properties
listeners=CLIENT://0.0.0.0:9093,INTERNAL://0.0.0.0:9094
advertised.listeners=CLIENT://broker-1.kafka.example.net:9093,INTERNAL://broker-1.internal:9094

listener.security.protocol.map=CLIENT:SSL,INTERNAL:SSL
inter.broker.listener.name=INTERNAL

listener.name.client.ssl.client.auth=required
listener.name.internal.ssl.client.auth=required
~~~

Broker cần certificate cho listener tương ứng và truststore chứa CA ký certificate của các peer. Certificate dùng trên INTERNAL listener phải có SAN phù hợp với địa chỉ broker mà peer xác minh.

Nếu mỗi broker dùng một CA hoặc trust domain khác nhau, phải thiết kế truststore sao cho mọi broker cần giao tiếp đều xác minh được nhau. Không mở listener INTERNAL ra mạng client; dùng firewall, security group hoặc network policy để giới hạn nguồn kết nối.

## 7. mTLS trong KRaft

KRaft có hai loại kết nối nội bộ cần phân biệt:

- Broker listener: client traffic và inter-broker traffic.
- Controller listener: broker-controller và controller-controller communication.

Controller listener không phải endpoint dành cho producer/consumer thông thường. Cần cô lập listener này khỏi client network.

Ví dụ cấu trúc KRaft combined broker/controller:

~~~properties
process.roles=broker,controller
listeners=BROKER://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093

inter.broker.listener.name=BROKER
controller.listener.names=CONTROLLER
controller.quorum.bootstrap.servers=controller-1.kafka.internal:9093,controller-2.kafka.internal:9093,controller-3.kafka.internal:9093

listener.security.protocol.map=BROKER:SSL,CONTROLLER:SSL
listener.name.broker.ssl.client.auth=required
listener.name.controller.ssl.client.auth=required
~~~

Đây là cấu trúc minh họa listener. Phải bổ sung keystore/truststore và certificate phù hợp cho từng listener, đồng thời cấu hình nhất quán trên tất cả node theo role.

Với dedicated broker và dedicated controller, broker vẫn cần biết controller listener và các SSL properties tương ứng để kết nối controller quorum. Controller cần cấu hình listener cho kết nối broker và controller khác.

Certificate dùng cho giao tiếp broker/controller có thể cần cả serverAuth và clientAuth vì một node có thể vừa nhận kết nối vừa khởi tạo kết nối TLS.

## 8. Client certificate trở thành Kafka principal thế nào?

Sau khi TLS xác thực certificate, Kafka cần xác định tên principal để áp dụng ACL.

### 8.1. Mặc định dùng Distinguished Name

Ví dụ client certificate có DN:

~~~text
CN=orders-producer,OU=KafkaClients,O=Example,C=VN
~~~

Mặc định principal SSL được tạo từ DN của certificate:

~~~text
User:CN=orders-producer,OU=KafkaClients,O=Example,C=VN
~~~

DN là định danh X.500, không phải tên topic hay client ID. Hai certificate có DN khác nhau có thể ánh xạ thành hai principal khác nhau.

### 8.2. Ánh xạ DN bằng ssl.principal.mapping.rules

DN thường dài và chứa nhiều thành phần. Có thể dùng ssl.principal.mapping.rules để chuyển DN thành short name.

~~~properties
ssl.principal.mapping.rules=RULE:^CN=([^,]+),OU=KafkaClients.*$/$1/,DEFAULT
~~~

Certificate có DN CN=orders-producer,OU=KafkaClients,O=Example,C=VN được ánh xạ thành principal User:orders-producer.

Các rule được đánh giá theo thứ tự; rule đầu tiên khớp sẽ được dùng. DEFAULT giữ cách ánh xạ mặc định nếu không có rule nào khớp.

Không viết regex chỉ dựa trên CN mà bỏ qua OU/O nếu có nguy cơ nhiều nhóm certificate cùng tên CN. Hãy chọn quy tắc đủ chặt để tránh hai danh tính khác nhau bị ánh xạ vào cùng principal.

### 8.3. Custom KafkaPrincipalBuilder

Với nhu cầu định danh phức tạp hơn, có thể triển khai KafkaPrincipalBuilder và cấu hình principal.builder.class.

Custom builder có thể dùng thông tin certificate, SAN hoặc extension để tạo principal theo chuẩn nội bộ. Tuy nhiên, trong KRaft, custom principal cần triển khai KafkaPrincipalSerde để principal có thể được serialize/deserialize khi broker forward request tới controller.

Chỉ dùng custom builder khi quy tắc mapping mặc định không đáp ứng được. Một builder tùy chỉnh sai có thể khiến authorization khác nhau giữa broker và controller.

## 9. Authentication không thay thế ACL authorization

mTLS xác nhận client sở hữu certificate được CA tin cậy ký. Kafka ACL xác định principal đó có quyền thực hiện thao tác gì.

Trong KRaft, authorizer mặc định của Kafka là:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
~~~

Khi bật authorizer, nếu không có ACL phù hợp thì request bị từ chối, trừ principal trong super.users. Nếu không cấu hình authorizer, các principal đã xác thực có thể có quyền rộng theo cấu hình mặc định của cluster.

Với KRaft, cấu hình StandardAuthorizer phải nhất quán trên tất cả node có role broker hoặc controller. Đồng thời bảo đảm principal broker/controller có quyền cluster cần thiết hoặc được khai báo có chủ đích trong super.users.

### 9.1. Cấp quyền producer

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server broker-1.kafka.example.net:9093 \
  --command-config admin-mtls.properties \
  --add \
  --allow-principal User:orders-producer \
  --producer \
  --topic orders
~~~

Convenience option --producer tạo các quyền cần thiết cho producer theo ACL model của Kafka. Trong production, kiểm tra ACL được tạo và chỉ cấp đúng resource/operation cần thiết.

### 9.2. Cấp quyền consumer

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server broker-1.kafka.example.net:9093 \
  --command-config admin-mtls.properties \
  --add \
  --allow-principal User:billing-consumer \
  --consumer \
  --topic invoices \
  --group billing-service
~~~

Consumer thường cần quyền READ/DESCRIBE trên topic và READ trên consumer group.

### 9.3. Xem ACL của principal

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server broker-1.kafka.example.net:9093 \
  --command-config admin-mtls.properties \
  --list \
  --principal User:orders-producer
~~~

Nếu TLS handshake thành công nhưng producer nhận TOPIC_AUTHORIZATION_FAILED, hãy kiểm tra principal mapping và ACL của topic. Nếu consumer nhận GROUP_AUTHORIZATION_FAILED, kiểm tra ACL group.

### 9.4. super.users

super.users là danh sách principal bỏ qua ACL check. Đây là quyền rất rộng, cần giới hạn cho broker/controller hoặc tài khoản quản trị thực sự cần thiết.

~~~properties
super.users=User:broker-admin;User:controller-admin;User:kafka-security-admin
~~~

Principal SSL DN có thể chứa dấu phẩy, do đó Kafka dùng dấu chấm phẩy để phân tách super users. Không đưa mọi client certificate vào danh sách này.

## 10. Cấu hình mTLS cho Java Kafka producer/consumer

Client cần hai nhóm thông tin: truststore để xác minh broker và keystore để gửi client certificate, chứng minh sở hữu private key.

Ví dụ file client-mtls.properties:

~~~properties
bootstrap.servers=broker-1.kafka.example.net:9093,broker-2.kafka.example.net:9093
security.protocol=SSL

ssl.truststore.type=PKCS12
ssl.truststore.location=/etc/app/kafka/broker-ca.p12
ssl.truststore.password=<TRUSTSTORE_PASSWORD>

ssl.keystore.type=PKCS12
ssl.keystore.location=/etc/app/kafka/orders-producer.p12
ssl.keystore.password=<KEYSTORE_PASSWORD>
ssl.key.password=<PRIVATE_KEY_PASSWORD>

ssl.endpoint.identification.algorithm=https
ssl.enabled.protocols=TLSv1.2,TLSv1.3
~~~

Cùng bộ cấu hình có thể dùng cho producer, consumer và AdminClient nếu tất cả sử dụng cùng identity. Trong production nên cấp certificate riêng theo workload và dùng cấu hình phù hợp cho từng client.

### 10.1. Producer Java

~~~java
import java.util.Properties;

import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.config.SslConfigs;

Properties props = new Properties();

props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
          "broker-1.kafka.example.net:9093");
props.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "SSL");
props.put(SslConfigs.SSL_TRUSTSTORE_TYPE_CONFIG, "PKCS12");
props.put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG,
          "/etc/app/kafka/broker-ca.p12");
props.put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG,
          truststorePassword);
props.put(SslConfigs.SSL_KEYSTORE_TYPE_CONFIG, "PKCS12");
props.put(SslConfigs.SSL_KEYSTORE_LOCATION_CONFIG,
          "/etc/app/kafka/orders-producer.p12");
props.put(SslConfigs.SSL_KEYSTORE_PASSWORD_CONFIG,
          keystorePassword);
props.put(SslConfigs.SSL_KEY_PASSWORD_CONFIG,
          privateKeyPassword);
props.put(SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG,
          "https");
~~~

Không hardcode password vào source code. Đọc secret từ secret manager, environment được bảo vệ hoặc Kafka ConfigProvider phù hợp với nền tảng.

### 10.2. Consumer Java

~~~java
import java.util.Properties;

import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.config.SslConfigs;
import org.apache.kafka.common.serialization.StringDeserializer;

Properties props = new Properties();

props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
          "broker-1.kafka.example.net:9093");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-service");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class.getName());

props.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "SSL");
props.put(SslConfigs.SSL_TRUSTSTORE_TYPE_CONFIG, "PKCS12");
props.put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG,
          "/etc/app/kafka/broker-ca.p12");
props.put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG,
          truststorePassword);
props.put(SslConfigs.SSL_KEYSTORE_TYPE_CONFIG, "PKCS12");
props.put(SslConfigs.SSL_KEYSTORE_LOCATION_CONFIG,
          "/etc/app/kafka/billing-consumer.p12");
props.put(SslConfigs.SSL_KEYSTORE_PASSWORD_CONFIG,
          keystorePassword);
props.put(SslConfigs.SSL_KEY_PASSWORD_CONFIG,
          privateKeyPassword);
~~~

Consumer certificate cần được ánh xạ thành principal có ACL READ trên topic và READ trên group.

## 11. Cấu hình mTLS với Spring Boot và Spring Kafka

Spring Kafka dùng Kafka client bên dưới. Vì vậy, cấu hình mTLS dùng cùng các property security.protocol và ssl.*.

Ví dụ application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - broker-1.kafka.example.net:9093
      - broker-2.kafka.example.net:9093
    properties:
      security.protocol: SSL
      ssl.truststore.type: PKCS12
      ssl.truststore.location: /etc/app/kafka/broker-ca.p12
      ssl.truststore.password: KAFKA_TRUSTSTORE_PASSWORD_FROM_SECRET
      ssl.keystore.type: PKCS12
      ssl.keystore.location: /etc/app/kafka/order-service.p12
      ssl.keystore.password: KAFKA_KEYSTORE_PASSWORD_FROM_SECRET
      ssl.key.password: KAFKA_PRIVATE_KEY_PASSWORD_FROM_SECRET
      ssl.endpoint.identification.algorithm: https
      ssl.enabled.protocols: TLSv1.2,TLSv1.3
~~~

spring.kafka.properties áp dụng các property chung cho Kafka clients do Spring Boot cấu hình. Nếu producer, consumer và AdminClient cần certificate khác nhau, có thể cấu hình riêng trong các nhóm producer/consumer/admin properties thay vì dùng chung một identity.

Các giá trị có hậu tố FROM_SECRET trong ví dụ là placeholder. Hãy inject password thật từ secret manager hoặc property source được bảo vệ. Không đưa file PKCS12 hoặc private key vào thư mục resources bên trong JAR. Mount certificate từ secret store hoặc secret volume với quyền file hạn chế.

## 12. Kafka Connect và Kafka Streams dùng mTLS

### 12.1. Kafka Connect worker

Kafka Connect worker là Kafka client. Cấu hình kết nối broker cần truststore và client keystore tương ứng:

~~~properties
bootstrap.servers=broker-1.kafka.example.net:9093,broker-2.kafka.example.net:9093
security.protocol=SSL

ssl.truststore.type=PKCS12
ssl.truststore.location=/etc/kafka-connect/tls/broker-ca.p12
ssl.truststore.password=<TRUSTSTORE_PASSWORD>

ssl.keystore.type=PKCS12
ssl.keystore.location=/etc/kafka-connect/tls/connect-worker.p12
ssl.keystore.password=<KEYSTORE_PASSWORD>
ssl.key.password=<PRIVATE_KEY_PASSWORD>

ssl.endpoint.identification.algorithm=https
~~~

Worker identity cần ACL cho internal topics của Connect, connector topics và các resource cần thiết. Nếu connector task tạo Kafka producer/consumer riêng hoặc override client properties, kiểm tra cấu hình prefix producer.* và consumer.* để chắc chắn chúng dùng security config phù hợp.

mTLS giữa Connect worker và Kafka broker không tự bảo vệ REST API của Kafka Connect. REST listener cần TLS/authentication riêng nếu API được truy cập qua mạng không tin cậy.

### 12.2. Kafka Streams

Kafka Streams cũng nhận các client properties chuẩn:

~~~properties
application.id=orders-enrichment-v1
bootstrap.servers=broker-1.kafka.example.net:9093

security.protocol=SSL
ssl.truststore.type=PKCS12
ssl.truststore.location=/etc/orders-streams/tls/broker-ca.p12
ssl.truststore.password=<TRUSTSTORE_PASSWORD>

ssl.keystore.type=PKCS12
ssl.keystore.location=/etc/orders-streams/tls/orders-streams.p12
ssl.keystore.password=<KEYSTORE_PASSWORD>
ssl.key.password=<PRIVATE_KEY_PASSWORD>
ssl.endpoint.identification.algorithm=https
~~~

Principal của Streams application cần ACL trên input/output topics, consumer group và internal changelog/repartition topics. Nếu dùng exactly-once, cần thêm quyền cho transactional ID theo cấu hình ứng dụng.

## 13. Dùng PEM trực tiếp trong Kafka configuration

Kafka hỗ trợ PEM cho broker và client. Ví dụ cấu hình client:

~~~properties
security.protocol=SSL

ssl.keystore.type=PEM
ssl.keystore.certificate.chain=<CLIENT_CERTIFICATE_CHAIN_PEM>
ssl.keystore.key=<CLIENT_PRIVATE_KEY_PEM>

ssl.truststore.type=PEM
ssl.truststore.certificates=<BROKER_CA_CERTIFICATE_PEM>

ssl.endpoint.identification.algorithm=https
~~~

Trong PEM:

- ssl.keystore.certificate.chain chứa certificate chain dạng PEM.
- ssl.keystore.key chứa private key dạng PEM.
- ssl.truststore.certificates chứa CA certificate tin cậy.
- ssl.keystore.password và ssl.truststore.password không được sử dụng như với JKS/PKCS12.
- Nếu private key được mã hóa, dùng ssl.key.password theo hỗ trợ của SSL engine factory.

Cấu hình chứa private key PEM vẫn là secret. Không ghi giá trị này vào Git, log, shell history hoặc file cấu hình có quyền đọc rộng. Nên dùng secret manager/config provider và kiểm soát quyền truy cập.

## 14. Certificate issuance và quy trình cấp phát

Một quy trình cấp phát có kiểm soát thường gồm:

1. Workload tạo private key tại nơi sẽ sử dụng.
2. Workload tạo Certificate Signing Request (CSR) chứa subject và SAN cần thiết.
3. PKI kiểm tra yêu cầu và ký CSR theo certificate profile.
4. Workload nhận certificate và intermediate chain.
5. Certificate được cài vào keystore hoặc secret volume.
6. CA certificate được cài vào truststore của peer.
7. Client/broker kiểm tra chain, SAN, EKU và thời hạn.
8. Principal được ánh xạ và ACL được cấp.
9. Kiểm thử kết nối trước khi đưa workload vào production.

### 14.1. Tạo keystore và CSR bằng keytool

~~~bash
keytool -genkeypair \
  -alias orders-producer \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -storetype PKCS12 \
  -keystore orders-producer.p12 \
  -dname "CN=orders-producer,OU=KafkaClients,O=Example,C=VN"

keytool -certreq \
  -alias orders-producer \
  -keystore orders-producer.p12 \
  -storetype PKCS12 \
  -file orders-producer.csr
~~~

CSR được gửi cho CA/PKI để ký. Khi tạo certificate broker, yêu cầu phải có SAN chứa DNS/IP mà client dùng để kết nối. Khi tạo client certificate, yêu cầu certificate profile có EKU clientAuth.

Ví dụ tạo CSR cho broker cần SAN:

~~~bash
keytool -certreq \
  -alias broker-1 \
  -keystore broker-1.p12 \
  -storetype PKCS12 \
  -file broker-1.csr \
  -ext SAN=DNS:broker-1.kafka.example.net,IP:10.10.20.11
~~~

Không dùng self-signed leaf certificate trong production nếu chính sách tổ chức yêu cầu CA tập trung.

### 14.2. Import CA và certificate đã ký

~~~bash
keytool -importcert \
  -alias kafka-root-ca \
  -file kafka-root-ca.crt \
  -keystore orders-producer.p12 \
  -storetype PKCS12

keytool -importcert \
  -alias orders-producer \
  -file orders-producer-signed.crt \
  -keystore orders-producer.p12 \
  -storetype PKCS12
~~~

Cần bảo đảm certificate được import đúng alias của private key entry và chain có đầy đủ intermediate CA. Kiểm tra kết quả:

~~~bash
keytool -list -v \
  -keystore orders-producer.p12 \
  -storetype PKCS12
~~~

### 14.3. Kiểm tra certificate bằng OpenSSL

~~~bash
openssl x509 \
  -in broker-1.crt \
  -noout \
  -subject \
  -issuer \
  -dates \
  -ext subjectAltName \
  -ext extendedKeyUsage
~~~

Kiểm tra chain:

~~~bash
openssl verify \
  -CAfile root-ca.crt \
  -untrusted intermediate-ca.crt \
  broker-1.crt
~~~

Certificate phải còn hạn, chain hợp lệ, SAN đúng endpoint và EKU phù hợp với vai trò.

## 15. Kiểm thử mTLS với Kafka

### 15.1. Kiểm tra TLS handshake

~~~bash
openssl s_client \
  -connect broker-1.kafka.example.net:9093 \
  -servername broker-1.kafka.example.net \
  -CAfile broker-ca.crt \
  -cert orders-producer.crt \
  -key orders-producer.key \
  -verify_hostname broker-1.kafka.example.net \
  -verify_return_error \
  -showcerts
~~~

Lệnh này kiểm tra lớp TLS, không thay thế kiểm thử Kafka protocol hoặc ACL.

### 15.2. Kiểm thử producer

Tạo file client-mtls.properties với truststore và keystore của producer, sau đó:

~~~bash
bin/kafka-console-producer.sh \
  --bootstrap-server broker-1.kafka.example.net:9093 \
  --topic orders \
  --producer.config client-mtls.properties
~~~

Gửi một record và xác nhận producer không nhận lỗi authentication/authorization.

### 15.3. Kiểm thử consumer

~~~bash
bin/kafka-console-consumer.sh \
  --bootstrap-server broker-1.kafka.example.net:9093 \
  --topic orders \
  --group orders-consumer-lab \
  --consumer.config consumer-mtls.properties \
  --from-beginning
~~~

Nếu handshake thành công nhưng consumer không đọc được, kiểm tra ACL topic và group.

### 15.4. Kiểm thử negative cases

Một bài test mTLS cần xác nhận cả các trường hợp bị từ chối:

- Client không gửi certificate.
- Client gửi certificate tự ký không nằm trong truststore.
- Certificate đã hết hạn.
- Certificate có EKU không phù hợp.
- Client kết nối bằng hostname không có trong SAN.
- Certificate hợp lệ nhưng principal không có ACL.
- Certificate hợp lệ nhưng principal mapping tạo ra tên khác với ACL dự kiến.

Nếu chỉ test một client hợp lệ, chưa thể chứng minh listener đang bắt buộc mTLS.

## 16. Xoay vòng certificate và CA

Certificate có thời hạn. Xoay vòng cần được lên lịch trước khi certificate hết hạn.

### 16.1. Xoay vòng leaf certificate cùng CA

Một quy trình phổ biến:

1. Tạo key pair mới.
2. Gửi CSR mới cho CA hiện tại.
3. Kiểm tra SAN, EKU, chain và thời hạn.
4. Cài certificate mới vào keystore.
5. Cập nhật broker/client theo rolling process hoặc dynamic broker config nếu hỗ trợ.
6. Khởi tạo kết nối mới và xác minh principal/ACL.
7. Theo dõi lỗi handshake và connection churn.
8. Thu hồi certificate cũ sau khi chắc chắn không còn workload sử dụng.

Không dùng lại private key cũ nếu mục tiêu xoay vòng là thay khóa sau một sự cố lộ key.

### 16.2. Xoay vòng CA

Khi đổi CA, không xóa CA cũ trước khi các peer đã tin CA mới.

~~~mermaid
flowchart TD
    A["Truststore chỉ có CA cũ"] --> B["Thêm CA mới, giữ CA cũ"]
    B --> C["Phát hành và triển khai certificate mới"]
    C --> D["Xác minh mọi client/broker đã dùng chain mới"]
    D --> E["Xóa CA cũ khỏi truststore"]
    E --> F["Theo dõi kết nối và lỗi xác thực"]
~~~

Trong giai đoạn overlap, truststore chứa cả CA cũ và mới. Khi toàn bộ certificate đã được chuyển đổi, có thể bỏ CA cũ. Nếu xóa CA cũ quá sớm, các client chưa kịp đổi certificate sẽ mất kết nối.

### 16.3. Dynamic update trên Kafka broker

Kafka 4.4 hỗ trợ cập nhật một số keystore và truststore của listener ở cấp broker mà không cần restart broker, thông qua dynamic broker configuration.

Các cấu hình cần prefix theo listener, ví dụ:

~~~text
listener.name.client.ssl.keystore.location
listener.name.client.ssl.keystore.password
listener.name.client.ssl.key.password
listener.name.client.ssl.truststore.location
listener.name.client.ssl.truststore.password
~~~

Truststore mới được dùng để xác minh các kết nối mới. Xóa CA khỏi truststore có thể khiến client dùng CA đó không thể tạo kết nối mới. Kết nối TLS đã thiết lập không tự động đổi certificate chỉ vì file store được cập nhật.

Khả năng cập nhật phụ thuộc loại property và Kafka version. Hãy kiểm tra update mode của từng broker config, thử trên staging và có rollback plan trước khi thay đổi listener production.

### 16.4. Quản lý private key và secret

- Không commit keystore/private key vào Git.
- Không copy private key CA đến application host.
- Dùng secret manager, HSM hoặc secret volume.
- Giới hạn file permission cho private key.
- Tách certificate theo môi trường dev/test/staging/prod.
- Ghi lại owner, serial number, expiry, issuer và principal mapping.
- Theo dõi certificate sắp hết hạn bằng monitoring hoặc PKI inventory.
- Thu hồi certificate bị lộ và phát hành certificate mới với key mới.

## 17. mTLS kết hợp SASL_SSL

Kafka hỗ trợ cả TLS client authentication và SASL authentication. Hai cơ chế có thể kết hợp trên listener SASL_SSL.

| Cấu hình | Encryption | Authentication |
|---|---|---|
| SSL + mTLS | TLS | Client certificate |
| SASL_SSL | TLS | SASL mechanism |
| SASL_SSL + mTLS | TLS | SASL và client certificate |

mTLS phù hợp khi tổ chức đã có PKI và muốn dùng certificate làm workload identity. SASL phù hợp khi cần username/password, SCRAM, Kerberos hoặc OAuth token. Kết hợp cả hai có thể tạo thêm một lớp kiểm tra nhưng cũng làm tăng độ phức tạp vận hành, principal mapping và troubleshooting.

Không nhầm security.protocol=SSL với SASL_SSL. Nếu dùng mTLS thuần, client cấu hình security.protocol=SSL; nếu dùng SASL trên TLS, client dùng SASL_SSL cùng các SASL properties tương ứng.

## 18. Lỗi thường gặp khi triển khai mTLS

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| PKIX path building failed | Truststore thiếu CA hoặc intermediate | Kiểm tra truststore và chain |
| Received fatal alert: certificate_unknown | Peer không tin certificate | Kiểm tra CA, alias và truststore |
| bad_certificate | Certificate sai mục đích, chain hoặc thời hạn | Kiểm tra EKU, Key Usage, dates |
| No subject alternative names matching | SAN không khớp hostname/IP kết nối | Kiểm tra advertised.listeners và SAN |
| UnrecoverableKeyException | Password store/key sai hoặc key không đọc được | Kiểm tra keystore password và key password |
| Keystore was tampered with, or password was incorrect | Sai password hoặc file store hỏng | Kiểm tra file/secret và store type |
| Client kết nối được nhưng bị authorization failed | Principal chưa có ACL hoặc DN mapping sai | Kiểm tra principal log và ACL |
| Client không gửi certificate | Client chưa cấu hình keystore hoặc listener yêu cầu mTLS | Kiểm tra ssl.keystore.* |
| Broker-to-broker handshake fail | Broker certificate thiếu clientAuth/serverAuth hoặc peer CA không được tin | Kiểm tra EKU và truststore inter-broker |
| KRaft controller không kết nối broker | Controller listener chưa cấu hình SSL hoặc certificate/CA sai | Kiểm tra controller.listener.names và listener-prefixed properties |
| Một số client kết nối, số khác lỗi | Certificate profile hoặc CA chain không đồng nhất | Kiểm tra từng certificate |
| Sau rotation nhiều kết nối lỗi | Trust overlap chưa đủ hoặc client vẫn dùng certificate cũ | Kiểm tra rollout và truststore |
| TLS thành công nhưng producer không ghi được | ACL thiếu WRITE hoặc principal mapping không đúng | Kiểm tra TOPIC_AUTHORIZATION_FAILED |
| Consumer đọc được topic nhưng không join group | Thiếu quyền group hoặc group ID không khớp ACL | Kiểm tra GROUP_AUTHORIZATION_FAILED |

### 18.1. Quy trình chẩn đoán theo lớp

1. Kiểm tra TCP reachability và listener port.
2. Kiểm tra broker certificate, issuer, SAN và thời hạn.
3. Kiểm tra client certificate, issuer, EKU và thời hạn.
4. Kiểm tra truststore ở cả broker và client.
5. Kiểm tra hostname verification.
6. Xác nhận TLS handshake thành công.
7. Xác nhận DN được ánh xạ thành principal mong muốn.
8. Kiểm tra ACL của principal trên topic, group và transactional ID.
9. Kiểm tra broker/controller listener riêng nếu lỗi chỉ xuất hiện trong cluster KRaft.
10. Kiểm tra log SSL handshake và authorization trên broker.

Không tắt hostname verification hoặc chuyển ssl.client.auth sang none để che lỗi. Hãy sửa SAN, chain, truststore hoặc client identity đúng nguyên nhân.

## 19. Lab: thiết lập mTLS cho Kafka local

Mục tiêu: cấu hình một broker SSL listener yêu cầu client certificate, kết nối bằng console producer/consumer và xác nhận ACL theo principal.

### Bước 1: Chuẩn bị CA lab

Dùng một CA dành riêng cho lab. Tạo CA private key và CA certificate bằng công cụ PKI hoặc OpenSSL. Không sử dụng CA lab trong production.

### Bước 2: Tạo broker key pair và CSR

Tạo PKCS12 keystore cho broker, dùng SAN chứa hostname mà client sẽ truy cập. Gửi CSR cho CA lab ký với EKU serverAuth và certificate chain phù hợp.

### Bước 3: Tạo client key pair và CSR

Tạo certificate riêng cho producer và consumer. Dùng subject khác nhau để có thể kiểm tra principal mapping và ACL độc lập. Yêu cầu EKU clientAuth.

### Bước 4: Tạo truststore

- Broker truststore chứa CA ký producer/consumer certificate.
- Client truststore chứa CA ký broker certificate.

Import CA public certificate, không import CA private key.

### Bước 5: Cấu hình broker listener

Bật listener SSL, cấu hình keystore/truststore và:

~~~properties
listener.name.client.ssl.client.auth=required
~~~

Khởi động broker và xác nhận listener đang lắng nghe.

### Bước 6: Cấu hình client properties

Tạo producer properties và consumer properties với:

- security.protocol=SSL
- ssl.truststore.*
- ssl.keystore.*
- ssl.key.password
- ssl.endpoint.identification.algorithm=https

Dùng certificate riêng cho từng client.

### Bước 7: Kiểm thử handshake

Dùng OpenSSL s_client hoặc Kafka console producer/consumer. Thử kết nối không có client certificate; broker phải từ chối nếu listener dùng required.

### Bước 8: Kiểm tra principal

Đọc broker log hoặc sử dụng ACL test để xác nhận DN được ánh xạ thành principal mong muốn. Nếu dùng ssl.principal.mapping.rules, thử cả certificate khớp rule và certificate fallback DEFAULT.

### Bước 9: Cấp ACL

Cấp producer principal quyền ghi topic orders. Cấp consumer principal quyền đọc topic orders và group orders-lab.

### Bước 10: Kiểm thử quyền

- Producer đúng certificate và ACL: ghi thành công.
- Producer đúng certificate nhưng không có ACL: bị authorization từ chối.
- Client không có certificate: TLS handshake thất bại.
- Client có certificate không được CA tin: TLS handshake thất bại.
- Client có certificate hợp lệ nhưng SAN broker không khớp: hostname verification thất bại.

### Bước 11: Thử xoay vòng certificate

Phát hành certificate mới cùng CA. Cập nhật keystore của client và kết nối lại. Sau đó thử thêm CA mới vào truststore, chuyển certificate sang CA mới và cuối cùng loại CA cũ khỏi truststore.

### Bước 12: Ghi kết quả

Ghi certificate serial/subject, principal mapping, ACL, kết quả handshake, kết quả producer/consumer và thời gian rotation.

## 20. Checklist production

- [ ] Có PKI/CA được quản lý và bảo vệ.
- [ ] CA private key không nằm trên broker/client.
- [ ] Mỗi broker và workload có certificate riêng.
- [ ] Broker certificate có SAN khớp advertised endpoint.
- [ ] Certificate có EKU phù hợp với vai trò client/server.
- [ ] Broker/client có đầy đủ certificate chain.
- [ ] Keystore chứa private key và certificate của chính node.
- [ ] Truststore chứa CA cần tin cậy, không chứa private key.
- [ ] Listener mTLS đặt ssl.client.auth=required.
- [ ] Không dùng requested như giải pháp thay thế cho required.
- [ ] Client giữ hostname verification mặc định.
- [ ] Dùng TLS 1.2 trở lên; ưu tiên TLS 1.3 nếu môi trường hỗ trợ.
- [ ] Listener client, inter-broker và controller được phân tách hợp lý.
- [ ] Controller listener KRaft không mở cho client network.
- [ ] DN mapping tạo principal ổn định và không trùng ngoài ý muốn.
- [ ] StandardAuthorizer/ACL được cấu hình và kiểm tra.
- [ ] Không đưa workload thông thường vào super.users.
- [ ] Producer, consumer, Connect và Streams có certificate identity riêng.
- [ ] Secret/private key được externalize và giới hạn quyền đọc.
- [ ] Có inventory serial, issuer, owner và expiry của certificate.
- [ ] Có kế hoạch rotation leaf certificate và CA với trust overlap.
- [ ] Có quy trình thu hồi certificate bị lộ.
- [ ] Đã kiểm thử negative cases và authorization failures.
- [ ] Đã kiểm tra inter-broker và KRaft controller connections.
- [ ] Có log/monitoring cho handshake failure, expiry và ACL denial.

## 21. Tài liệu tham khảo

- [Apache Kafka 4.4 – Encryption and Authentication using SSL](https://kafka.apache.org/44/security/encryption-and-authentication-using-ssl/)
- [Apache Kafka 4.4 – Security Model](https://kafka.apache.org/44/security/security-model/)
- [Apache Kafka 4.4 – Listener Configuration](https://kafka.apache.org/44/security/listener-configuration/)
- [Apache Kafka 4.4 – Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/)
- [Apache Kafka 4.4 – Broker Configs](https://kafka.apache.org/44/configuration/broker-configs/)
- [Apache Kafka 4.4 – Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 – Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Java keytool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html)
- [OpenSSL documentation](https://docs.openssl.org/)

mTLS bảo vệ kết nối Kafka bằng cách xác thực certificate của cả client và broker. Để triển khai đúng, cần quản lý CA và certificate chain, xác minh SAN/EKU, cấu hình keystore/truststore theo từng listener, ánh xạ DN thành principal và cấp ACL theo workload. Quy trình rotation và thu hồi certificate phải được chuẩn bị từ đầu để việc thay khóa không làm gián đoạn producer, consumer, Connect, Streams hoặc giao tiếp nội bộ KRaft.
