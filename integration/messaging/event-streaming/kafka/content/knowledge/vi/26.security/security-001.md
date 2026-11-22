# Bề mặt tấn công và ranh giới tin cậy trong hệ thống Kafka

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này đặt Kafka trong góc nhìn an ninh hệ thống: xác định tài sản cần bảo vệ, các điểm có thể bị tấn công, ranh giới tin cậy giữa client, broker, controller, connector và hệ thống đích, sau đó chọn biện pháp phòng vệ phù hợp.

Một Kafka cluster không chỉ là các broker nhận record. Hệ thống còn có producer, consumer, ứng dụng quản trị, KRaft controller quorum, Connect worker, Streams application, Schema Registry, hệ thống lưu secret, monitoring và các dịch vụ bên ngoài. Mỗi thành phần có danh tính, quyền truy cập, luồng dữ liệu và mức độ tin cậy khác nhau. Nếu chỉ bật TLS ở cổng broker nhưng để REST API, JMX, controller listener hoặc credential mở rộng quyền, hệ thống vẫn có thể bị xâm nhập.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện tài sản cần bảo vệ trong một Kafka deployment.
- Vẽ trust boundary giữa client, broker, controller, worker và hệ thống ngoài.
- Phân biệt data plane, control plane và management plane.
- Xác định attack surface qua listener, REST API, JMX, plugin, credential và internal topic.
- Giải thích sự khác nhau giữa mã hóa, xác thực và phân quyền.
- Chọn TLS, mutual TLS hoặc SASL phù hợp với client và cluster.
- Áp dụng ACL theo nguyên tắc least privilege cho producer, consumer và service account.
- Hiểu vai trò của StandardAuthorizer trong Kafka chạy KRaft.
- Bảo vệ inter-broker và controller communication.
- Bảo vệ Kafka Connect, Kafka Streams, Schema Registry và công cụ quản trị.
- Quản lý secret, certificate, key và vòng đời credential.
- Thiết kế network segmentation, audit, monitoring và quy trình ứng phó sự cố.
- Xây dựng threat model và checklist hardening cho môi trường production.

## 2. Kafka security bắt đầu từ tài sản cần bảo vệ

Trước khi chọn cơ chế bảo mật, hãy xác định thứ gì có giá trị và hậu quả nếu bị đọc, sửa, xóa hoặc làm gián đoạn.

| Tài sản | Ví dụ | Rủi ro khi bị xâm phạm |
|---|---|---|
| Event data | Đơn hàng, thanh toán, thông tin khách hàng, log | Lộ dữ liệu, sửa dữ liệu, giả mạo sự kiện |
| Topic metadata | Topic name, partition, config, retention | Lộ cấu trúc hệ thống hoặc thay đổi cấu hình |
| Consumer offsets | Vị trí đọc của consumer group | Replay, bỏ sót hoặc làm gián đoạn xử lý |
| Transaction state | Trạng thái giao dịch producer | Làm sai luồng giao dịch hoặc ảnh hưởng availability |
| Identity và credential | SASL password, certificate, token | Kẻ tấn công mạo danh service |
| KRaft metadata | Cluster metadata và quorum state | Mất khả năng điều phối cluster |
| Connect configuration | JDBC URL, API key, connector class | Đọc dữ liệu nguồn hoặc ghi dữ liệu sang đích trái phép |
| Streams state | State store, changelog, repartition data | Rò rỉ hoặc làm sai kết quả xử lý |
| Schema và contract | Avro/Protobuf/JSON schema | Giả mạo schema, phá tương thích dữ liệu |
| Management interface | REST API, JMX, admin UI | Chiếm quyền vận hành cluster |
| Audit và telemetry | Security log, metrics, traces | Mất khả năng phát hiện và điều tra sự cố |

Không phải dữ liệu nào cũng cần cùng mức bảo vệ. Event thanh toán, token xác thực hoặc dữ liệu định danh có thể cần kiểm soát nghiêm ngặt hơn dữ liệu telemetry không nhạy cảm. Phân loại dữ liệu giúp xác định ai được đọc, retention bao lâu, có cần mã hóa ở tầng ứng dụng hay không và log nào được phép lưu.

## 3. Data plane, control plane và management plane

Có thể chia hệ thống Kafka thành ba mặt phẳng để dễ xác định ranh giới tin cậy.

- **Data plane:** producer, consumer, broker listener và luồng record.
- **Control plane:** broker coordination, replication, KRaft controller quorum, metadata và thao tác thay đổi trạng thái cluster.
- **Management plane:** Kafka Connect REST API, Schema Registry API, JMX, admin UI, CI/CD và công cụ vận hành.

~~~mermaid
flowchart TB
    subgraph DATA["Data plane"]
      P[Producer services] -->|TLS + SASL/mTLS| B[Kafka broker]
      B -->|TLS + SASL/mTLS| C[Consumer services]
      B --> R[Replication traffic]
    end
    subgraph CONTROL["Control plane - KRaft"]
      K1[Controller 1] <--> K2[Controller 2]
      K2 <--> K3[Controller 3]
      K1 <--> B
      K2 <--> B
      K3 <--> B
    end
    subgraph MGMT["Management plane"]
      A[Admin / CI pipeline] -->|Protected REST/API| X[Connect workers]
      A -->|Protected API| S[Schema Registry]
      O[Monitoring / JMX] --> B
      O --> X
    end
    X --> B
    S --> P
~~~

Sơ đồ chỉ thể hiện các luồng chính. Trong thực tế, mỗi kết nối cần một policy cụ thể: nguồn nào được kết nối, listener nào được dùng, danh tính nào được chấp nhận và resource nào được phép truy cập.

### 3.1. Ranh giới tin cậy thường gặp

1. **Client-to-broker:** ứng dụng bên ngoài gửi hoặc đọc record qua listener client.
2. **Broker-to-broker:** broker trao đổi replication, metadata và request nội bộ.
3. **Broker-to-controller:** broker gửi request quản trị và nhận metadata từ KRaft controller.
4. **Controller quorum:** các controller trao đổi metadata log và quorum communication.
5. **Worker-to-broker:** Connect và Streams dùng Kafka protocol để đọc/ghi topic và internal topic.
6. **Admin-to-management API:** người vận hành gọi REST API, JMX hoặc admin UI.
7. **Connector-to-external system:** plugin kết nối database, object storage, SaaS hoặc HTTP endpoint.
8. **Application-to-secret provider:** service lấy password, token hoặc certificate.
9. **Monitoring-to-cluster:** hệ thống metrics/logging truy cập endpoint quan sát.

Mỗi ranh giới phải có xác thực, phân quyền, mã hóa và kiểm soát network phù hợp. Không nên mặc định rằng hai thành phần cùng VPC, cùng Kubernetes namespace hoặc cùng subnet là đáng tin cậy.

## 4. Threat modeling cho Kafka

Threat modeling giúp tìm các đường tấn công trước khi triển khai. Có thể dùng STRIDE làm khung phân loại:

| Nhóm | Câu hỏi trong hệ thống Kafka | Ví dụ |
|---|---|---|
| Spoofing | Ai có thể giả danh service hoặc broker? | Dùng credential bị đánh cắp để giả làm producer |
| Tampering | Ai có thể sửa event, config hoặc metadata? | Principal có Write vào topic thanh toán |
| Repudiation | Có thể phủ nhận thao tác quản trị không? | Xóa topic mà không có audit trail |
| Information disclosure | Ai có thể đọc dữ liệu hoặc secret? | Consumer trái phép đọc topic chứa PII |
| Denial of service | Ai có thể làm cluster hoặc downstream quá tải? | Mở nhiều connection hoặc gửi record quá lớn |
| Elevation of privilege | Principal có thể vượt quyền không? | Connector REST mở cho người dùng không tin cậy |

### 4.1. Xác định threat actor

Các nguồn rủi ro không chỉ là hacker từ Internet:

- Người dùng nội bộ có quyền quá rộng.
- Workload bị xâm nhập trong cùng mạng.
- Dependency hoặc connector plugin bị cài mã độc.
- Credential bị lộ trong source code, log hoặc CI artifact.
- Máy developer hoặc jump host bị chiếm quyền.
- Admin UI hoặc REST API cấu hình sai.
- Producer hợp lệ nhưng bị lỗi hoặc bị lợi dụng để phát dữ liệu độc hại.
- Nhà cung cấp hoặc hệ thống tích hợp bên ngoài bị xâm phạm.

### 4.2. Vẽ data flow trước khi cấp quyền

Với mỗi luồng, ghi rõ:

- Ai là nguồn dữ liệu?
- Ai là consumer?
- Topic nào được đọc hoặc ghi?
- Luồng có đi qua Connect, Streams hoặc Schema Registry không?
- Credential được lấy từ đâu?
- Dữ liệu đi qua network zone nào?
- Ai có thể thay đổi connector, ACL, retention hoặc schema?
- Log và audit được gửi tới đâu?

Nếu không mô tả được luồng dữ liệu, rất khó cấp ACL tối thiểu hoặc xác định phạm vi ảnh hưởng khi credential bị lộ.

## 5. Attack surface trong Kafka deployment

Attack surface là tập hợp các điểm mà actor có thể tương tác với hệ thống và tạo ra hành vi không mong muốn.

| Bề mặt | Ví dụ thao tác | Kiểm soát chính |
|---|---|---|
| Broker client listener | Produce, fetch, metadata request | TLS, SASL/mTLS, ACL, network policy |
| Inter-broker listener | Replication, broker requests | Listener riêng, TLS/SASL, firewall nội bộ |
| KRaft controller listener | Metadata và quorum communication | Chỉ cho broker/controller được phép truy cập |
| Kafka Admin API | Tạo/xóa topic, ACL, config | ACL cluster/topic, admin identity riêng |
| Connect REST API | Tạo/sửa/xóa connector | TLS, authentication, authorization, audit |
| Schema Registry API | Đăng ký hoặc đọc schema | Authentication, authorization, compatibility policy |
| JMX | Metrics và management operations | Network isolation, authentication/TLS, read-only exporter |
| Admin UI | Xem và thay đổi cluster | SSO/MFA, RBAC, audit |
| Plugin path | Nạp connector/converter/SMT | Supply-chain control, checksum, review, image hardening |
| Secret provider | Lấy token/password | IAM tối thiểu, rotation, audit |
| Host/container | Process, filesystem, socket | OS hardening, patching, runtime security |
| Backup và log | Bản sao dữ liệu, cấu hình, secret | Encryption, access control, retention |

Một cổng không được công khai vẫn có thể bị truy cập từ workload bị xâm nhập trong cùng network. Vì vậy, network segmentation cần đi cùng identity và authorization.

## 6. Listener và network boundary

Kafka có thể cấu hình nhiều listener cho các nhóm kết nối khác nhau. Ví dụ:

- CLIENT: producer và consumer.
- INTERNAL: broker-to-broker.
- CONTROLLER: broker/controller communication trong KRaft.

Không nên dùng một listener duy nhất cho mọi mục đích nếu các nhóm kết nối có mức tin cậy và policy khác nhau.

### 6.1. Phân biệt các thuộc tính listener

| Thuộc tính | Vai trò |
|---|---|
| listeners | Địa chỉ và port mà broker bind để nhận kết nối |
| advertised.listeners | Địa chỉ broker công bố cho client sau bootstrap |
| listener.security.protocol.map | Ánh xạ tên listener sang PLAINTEXT, SSL, SASL_PLAINTEXT hoặc SASL_SSL |
| inter.broker.listener.name | Listener broker dùng để giao tiếp với broker khác |
| controller.listener.names | Listener dành cho KRaft controller communication |

Bootstrap server chỉ là điểm bắt đầu khám phá cluster. Sau đó client kết nối đến địa chỉ trong metadata broker trả về. Nếu advertised.listeners công bố hostname hoặc port không thể truy cập từ client network, kết nối sẽ thất bại dù bootstrap ban đầu thành công.

### 6.2. Ví dụ tách listener trong KRaft

Ví dụ minh họa cho broker có các listener riêng:

~~~properties
listeners=CLIENT://0.0.0.0:9093,INTERNAL://0.0.0.0:9094,CONTROLLER://0.0.0.0:9095
advertised.listeners=CLIENT://broker-1.internal:9093,INTERNAL://broker-1.internal:9094

listener.security.protocol.map=CLIENT:SASL_SSL,INTERNAL:SASL_SSL,CONTROLLER:SSL
inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER
~~~

Các giá trị cần điều chỉnh theo topology và phiên bản triển khai. Controller listener không phải listener cho producer/consumer thông thường và không nên xuất hiện trong advertised.listeners dành cho client.

Nếu dùng dedicated controller nodes, chỉ broker và controller trong quorum được truy cập controller listener theo đúng cấu hình. Không mở port này ra mạng người dùng, mạng ứng dụng hoặc Internet.

### 6.3. Network segmentation

Có thể tách network zone như sau:

- Client zone: ứng dụng producer/consumer.
- Broker zone: broker nhận client traffic và replication.
- Controller zone: KRaft controller quorum.
- Integration zone: Connect, Streams và Schema Registry.
- Management zone: admin UI, CI/CD, bastion và JMX exporter.
- External zone: database, object storage, API nhà cung cấp.

Dùng firewall, Kubernetes NetworkPolicy, security group hoặc service mesh policy để chỉ cho phép luồng cần thiết. Network policy nên được kiểm tra cả ingress và egress; connector có thể mở kết nối outbound đến hệ thống ngoài.

## 7. Mã hóa dữ liệu trên đường truyền bằng TLS

TLS bảo vệ tính bí mật và toàn vẹn của dữ liệu khi di chuyển qua network. Nó giúp ngăn nghe lén và sửa đổi traffic giữa client với broker hoặc giữa các thành phần nội bộ.

Kafka có các protocol security phổ biến:

| Protocol | Mã hóa TLS | Xác thực SASL | Ghi chú |
|---|---|---|---|
| PLAINTEXT | Không | Không | Chỉ phù hợp lab hoặc network cô lập có kiểm soát |
| SSL | Có | Không bắt buộc; có thể dùng client certificate | Có thể bật mutual TLS |
| SASL_PLAINTEXT | Không | Có | Credential đi trên kết nối không mã hóa, tránh dùng production |
| SASL_SSL | Có | Có | Lựa chọn phổ biến cho SASL qua TLS |

TLS server authentication giúp client xác minh broker certificate. Mutual TLS (mTLS) yêu cầu client cũng trình certificate để server xác minh danh tính ở tầng TLS.

### 7.1. Client TLS configuration

Ví dụ cấu hình client dùng SASL_SSL:

~~~properties
security.protocol=SASL_SSL
ssl.truststore.location=/etc/kafka/security/client.truststore.jks
ssl.truststore.password=<inject-from-secret-store>
ssl.endpoint.identification.algorithm=https

sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=<inject-scram-login-module-config>
~~~

Đây là cấu hình minh họa. Secret phải được inject từ secret manager hoặc cơ chế deployment an toàn; không commit password vào Git hoặc file cấu hình dùng chung.

### 7.2. Kiểm tra certificate

Cần quản lý:

- CA tin cậy.
- SAN/hostname trên certificate phải khớp địa chỉ broker mà client kết nối.
- Thời hạn certificate và lịch rotation.
- Private key với file permission tối thiểu.
- Thu hồi certificate khi service hoặc host bị xâm phạm.
- Truststore được cập nhật đồng bộ khi thay CA.

Không tắt hostname verification để né lỗi certificate. Hãy sửa SAN, DNS hoặc advertised.listeners cho đúng.

### 7.3. TLS cho replication và controller

Mã hóa client traffic là chưa đủ. Broker-to-broker và broker-to-controller cũng có thể mang metadata hoặc dữ liệu record trong quá trình replication.

Cần xác định listener nội bộ nào dùng TLS, CA nào được tin cậy và principal nào được phép kết nối. Nếu controller quorum dùng listener riêng, cần giới hạn network và certificate/identity cho đúng broker/controller.

## 8. Xác thực: xác định ai đang kết nối

Authentication trả lời câu hỏi: “Client này là ai?”

Kafka hỗ trợ nhiều cơ chế, lựa chọn tùy môi trường và identity provider.

| Cơ chế | Cách hoạt động | Trường hợp sử dụng |
|---|---|---|
| SASL/SCRAM | Username/password được xác minh bằng SCRAM challenge | Service account, triển khai tương đối đơn giản |
| SASL/GSSAPI | Kerberos ticket xác thực principal | Hệ thống doanh nghiệp có Kerberos |
| SASL/OAUTHBEARER | OAuth bearer token được xác minh | Tích hợp identity provider và token lifecycle |
| SSL client authentication | Certificate client xác thực qua mTLS | Workload có PKI và certificate lifecycle |
| SASL/PLAIN | Username/password qua SASL | Chỉ dùng khi được bảo vệ bằng TLS |

SASL/PLAIN trên PLAINTEXT không bảo vệ credential khỏi nghe lén. Nếu dùng PLAIN, phải kết hợp TLS và quản lý credential nghiêm ngặt.

### 8.1. SASL/SCRAM

SCRAM dùng username/password với cơ chế challenge-response thay vì gửi password thô như PLAIN. Tuy vậy, credential vẫn cần được bảo vệ khi tạo, phân phối và lưu trữ.

Ví dụ client properties:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-producer" password="<injected-secret>";
~~~

Không đưa dòng có password thật vào repository, log, shell history hoặc tài liệu học tập. Với Java, có thể lấy JAAS config từ secret provider rồi truyền vào Properties lúc runtime.

### 8.2. SASL/OAUTHBEARER

OAuth bearer phù hợp khi tổ chức có identity provider phát hành access token. Cần kiểm tra:

- Issuer và audience.
- Signature và thuật toán được phép.
- Thời hạn token.
- Cơ chế refresh.
- Clock skew.
- Cách map token claim thành Kafka principal.
- Hành vi khi identity provider không khả dụng.

Token có thời hạn ngắn giảm thời gian sử dụng nếu bị lộ, nhưng client phải refresh đúng cách. Không ghi token vào log hoặc metric label.

### 8.3. Mutual TLS

Với mTLS, client certificate xác thực workload ở tầng TLS. Kafka có thể map certificate identity thành principal dùng cho ACL.

Cần có quy trình cấp, renew và revoke certificate. Certificate không được chia sẻ giữa nhiều service không liên quan vì sẽ làm mất khả năng phân biệt principal và điều tra.

### 8.4. Authentication không thay thế authorization

Client có thể xác thực thành công nhưng vẫn không có quyền đọc topic hoặc tạo topic. Sau authentication, Kafka authorizer kiểm tra principal có được phép thực hiện operation trên resource hay không.

## 9. Phân quyền bằng ACL và StandardAuthorizer

Authorization trả lời câu hỏi: “Principal này được phép làm gì trên resource nào?”

Trong Kafka chạy KRaft, StandardAuthorizer là authorizer phổ biến để kiểm tra ACL. Ví dụ cấu hình:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
allow.everyone.if.no.acl.found=false
super.users=User:cluster-admin
~~~

Tên principal và cú pháp cần phù hợp với authentication mechanism, principal mapping và phiên bản Kafka. Super user có quyền vượt ACL nên phải được giới hạn rất chặt, theo dõi và bảo vệ như tài khoản quản trị hệ thống.

### 9.1. Nguyên tắc least privilege

Mỗi service chỉ được cấp quyền cần thiết:

- Producer chỉ ghi vào topic mà nó sở hữu.
- Consumer chỉ đọc topic và group của nó.
- Connect worker chỉ truy cập internal topic và topic nghiệp vụ được cấu hình.
- Streams application chỉ đọc input, ghi output và quản lý internal resource cần thiết.
- Admin automation có quyền quản trị riêng, không dùng credential của ứng dụng nghiệp vụ.

Không cấp All trên cluster cho mọi service chỉ để tránh lỗi authorization. Khi một principal bị xâm nhập, ACL hẹp sẽ giới hạn phạm vi ảnh hưởng.

### 9.2. Ví dụ ACL cho producer

Ví dụ principal orders-producer được ghi và mô tả topic orders:

~~~bash
kafka-acls.sh --bootstrap-server broker-1.internal:9093 --command-config admin-client.properties --add --allow-principal User:orders-producer --operation Write --operation Describe --topic orders
~~~

Producer không cần quyền Read trên topic nếu chỉ gửi record. Các API đặc biệt như transaction hoặc idempotence có thể yêu cầu quyền bổ sung trên transactional ID hoặc cluster resource tùy phiên bản và cách cấu hình. Hãy kiểm tra lỗi authorization thực tế và cấp đúng operation cần thiết.

### 9.3. Ví dụ ACL cho consumer

Consumer cần quyền đọc topic và quyền sử dụng consumer group:

~~~bash
kafka-acls.sh --bootstrap-server broker-1.internal:9093 --command-config admin-client.properties --add --allow-principal User:orders-consumer --operation Read --operation Describe --topic orders
~~~

~~~bash
kafka-acls.sh --bootstrap-server broker-1.internal:9093 --command-config admin-client.properties --add --allow-principal User:orders-consumer --operation Read --group orders-service
~~~

Không dùng cùng một principal cho mọi consumer group nếu cần cô lập quyền theo service. Một consumer đọc được topic nhưng không có quyền group phù hợp có thể gặp lỗi khi join group hoặc commit offset.

### 9.4. Quản lý ACL và kiểm tra quyền

Các thao tác ACL nên được thực hiện qua pipeline hoặc công cụ quản trị có audit:

- Liệt kê ACL hiện tại.
- Tạo ACL theo service account.
- Xác minh principal và resource pattern.
- Kiểm thử truy cập bằng đúng credential của workload.
- Thu hồi ACL khi service ngừng hoạt động.
- Định kỳ rà soát quyền không còn sử dụng.

Ưu tiên resource cụ thể hoặc prefix pattern có phạm vi rõ ràng. Tránh wildcard rộng như mọi principal, mọi topic hoặc mọi group nếu không có lý do vận hành được phê duyệt.

## 10. Bảo vệ KRaft control plane

KRaft thay thế ZooKeeper bằng controller quorum quản lý metadata. Vì controller có quyền điều phối trạng thái cluster, controller listener và metadata quorum là tài sản đặc biệt nhạy cảm.

Các nguyên tắc:

- Tách controller listener khỏi client listener.
- Chỉ broker/controller cần thiết được truy cập controller listener.
- Không quảng bá controller endpoint cho producer/consumer.
- Bảo vệ quorum traffic bằng network segmentation và TLS.
- Giới hạn OS account, file permission và quyền truy cập controller host.
- Bảo vệ metadata log, snapshot và backup.
- Giám sát thay đổi cluster metadata và controller quorum health.
- Giữ danh sách super user và broker/controller principal ở mức tối thiểu.

Controller listener không phải một cổng admin HTTP. Đây là Kafka protocol listener dùng cho control plane. Không cho ứng dụng nghiệp vụ kết nối trực tiếp vào listener này.

### 10.1. Broker identity và controller identity

Broker và controller có thể cần principal riêng tùy deployment. Nếu một process chạy combined broker/controller role, identity và listener policy cần được cấu hình nhất quán với mô hình đó.

Không dùng certificate hoặc credential của producer làm credential inter-broker. Nếu một producer bị xâm phạm, kẻ tấn công không nên có khả năng giả làm broker hoặc controller.

### 10.2. Metadata và internal topics

Một số topic nội bộ chứa trạng thái vận hành:

- __consumer_offsets lưu offset và metadata consumer group.
- __transaction_state lưu trạng thái transaction.
- Kafka Connect có config, offset và status topic riêng.
- Kafka Streams tạo changelog và repartition topic theo topology.

Các topic này không nên được cấp quyền đọc/ghi tùy tiện cho ứng dụng nghiệp vụ. Không xóa hoặc sửa chúng bằng tay khi cluster đang hoạt động nếu không có quy trình phục hồi được kiểm soát.

## 11. Bảo vệ Kafka Connect và plugin

Kafka Connect tạo thêm một ranh giới tin cậy vì connector plugin có thể truy cập cả Kafka lẫn hệ thống ngoài.

Một connector có thể:

- Đọc bảng database và ghi dữ liệu vào Kafka.
- Đọc topic và ghi vào database.
- Gọi API bên ngoài.
- Truy cập object storage.
- Dùng credential hoặc token được cấu hình trong connector.

Người có quyền tạo hoặc cập nhật connector có thể thay đổi nơi dữ liệu được đọc hoặc gửi đến. Vì vậy, quyền REST API Connect có thể tương đương quyền thay đổi luồng dữ liệu của tổ chức.

### 11.1. Bảo vệ Connect REST API

- Không expose REST endpoint công khai.
- Dùng TLS và authentication/authorization phù hợp.
- Giới hạn truy cập theo management network.
- Phân quyền create, update, pause, restart và delete theo role.
- Ghi audit cho mọi thay đổi connector.
- Chặn connector class không nằm trong allowlist nội bộ nếu triển khai hỗ trợ policy.
- Không cho user tùy ý cấu hình URL đích hoặc file path nhạy cảm.
- Kiểm tra egress để ngăn connector gửi dữ liệu đến endpoint không được phép.

Kafka broker ACL không tự động bảo vệ Connect REST API. Đây là hai lớp bảo mật riêng.

### 11.2. Plugin supply chain

Connector, converter và SMT là mã chạy trong Connect worker process. Plugin không đáng tin có thể đọc dữ liệu mà worker truy cập hoặc thực thi hành vi ngoài dự kiến.

Cần:

- Chỉ cài plugin từ nguồn tin cậy.
- Pin version và checksum.
- Quét dependency và image.
- Review mã hoặc nhà cung cấp plugin.
- Giữ plugin version đồng nhất trên các worker.
- Hạn chế quyền filesystem và network của worker.
- Không mount Docker socket hoặc host path nhạy cảm nếu không cần.
- Cập nhật plugin theo quy trình change management.

## 12. Bảo vệ Kafka Streams và Schema Registry

### 12.1. Kafka Streams

Streams application thường có quyền đọc input topic, ghi output topic và sử dụng internal topic/state store. Dùng principal riêng cho từng application.id.

Cần kiểm soát:

- Read trên input topics.
- Write trên output topics.
- Quyền cần thiết trên repartition/changelog topics.
- Consumer group và application identity.
- Quyền tạo hoặc quản lý internal resources.
- Thư mục state.dir và quyền filesystem.
- Secret hoặc credential của hệ thống ngoài mà processor gọi.

Không cấp quyền rộng trên toàn cluster cho Streams application chỉ vì topology tạo internal topic. Có thể provision trước resource hoặc giới hạn ACL theo prefix, tùy cách vận hành.

### 12.2. Schema Registry

Schema Registry thường là dịch vụ riêng, có REST API và storage backend. Bảo vệ Schema Registry độc lập với broker:

- TLS và authentication cho REST API.
- Authorization theo subject hoặc schema resource nếu phiên bản hỗ trợ.
- Giới hạn ai được đăng ký schema mới.
- Compatibility policy để ngăn thay đổi phá vỡ consumer.
- Bảo vệ credential của Schema Registry khi truy cập Kafka.
- Audit schema registration và deletion.

Schema hợp lệ về cú pháp không có nghĩa event hợp lệ về nghiệp vụ. Consumer vẫn cần validation và xử lý dữ liệu không tin cậy.

## 13. Quản lý secret, token và certificate

Secret thường bị lộ qua các con đường đơn giản hơn lỗi giao thức:

- Commit password vào Git.
- In Properties hoặc JAAS config ra log.
- Đưa token vào command-line argument.
- Lưu credential trong Docker image.
- Chia sẻ file keystore/truststore giữa nhiều service.
- Để secret trong CI artifact hoặc build log.
- Không thu hồi credential sau khi nhân sự hoặc service ngừng hoạt động.

### 13.1. Nguyên tắc quản lý secret

1. Dùng secret manager hoặc secret store được kiểm soát.
2. Cấp secret riêng cho từng workload.
3. Giới hạn quyền đọc secret theo identity.
4. Rotation có kế hoạch và có thể rollback.
5. Không log secret hoặc token.
6. Thu hồi credential khi service bị xâm phạm hoặc ngừng hoạt động.
7. Kiểm tra secret trong Git history và CI logs.
8. Tách certificate client khỏi certificate broker/controller.

### 13.2. Lấy cấu hình từ environment

Ví dụ Java đọc JAAS config từ environment do deployment inject:

~~~java
Properties properties = new Properties();

properties.put("bootstrap.servers", "broker-1.internal:9093");
properties.put("security.protocol", "SASL_SSL");
properties.put("sasl.mechanism", "SCRAM-SHA-512");

String jaasConfig = System.getenv("KAFKA_SASL_JAAS_CONFIG");

if (jaasConfig == null || jaasConfig.isBlank()) {
    throw new IllegalStateException(
        "Missing Kafka SASL configuration"
    );
}

properties.put("sasl.jaas.config", jaasConfig);
~~~

Environment variable là cách minh họa để tách secret khỏi source code; nó không tự động là secret manager. Cần bảo vệ process environment, container metadata, crash dump và quyền truy cập host. Trong môi trường có secret provider, ưu tiên cơ chế tích hợp và cấp secret ngắn hạn nếu có thể.

### 13.3. Rotation không làm gián đoạn dịch vụ

Quy trình rotation nên có các bước:

- Tạo credential hoặc certificate mới.
- Cập nhật trust/identity configuration theo thứ tự tương thích.
- Chuyển client sang credential mới.
- Xác nhận kết nối và authorization.
- Thu hồi credential cũ sau thời gian chuyển tiếp.
- Theo dõi lỗi authentication và reconnect.

Với certificate CA rotation, có thể cần giai đoạn trust cả CA cũ và mới trước khi thay certificate trên toàn bộ thành phần. Thiết kế cụ thể phụ thuộc PKI và cách rollout.

## 14. Bảo vệ dữ liệu khi lưu trữ

TLS bảo vệ dữ liệu trên đường truyền, nhưng không tự mã hóa file log trên disk.

Các lớp bảo vệ at rest:

- Encryption at rest trên volume hoặc disk của broker.
- Encryption cho backup và snapshot.
- IAM và filesystem permission giới hạn truy cập dữ liệu.
- Mã hóa field nhạy cảm ở tầng ứng dụng nếu cần.
- Retention và compaction phù hợp chính sách dữ liệu.
- Quản lý key encryption và rotation.
- Kiểm soát truy cập vào log, dump và bản sao môi trường test.

Kafka không tự động mã hóa từng field trong payload theo một chính sách dữ liệu chung. Nếu consumer có quyền đọc topic, broker authorization không che riêng một field khỏi consumer đó. Với dữ liệu nhạy cảm, cân nhắc tokenization hoặc application-level encryption trước khi ghi vào Kafka.

### 14.1. Retention không phải cơ chế xóa tức thời

Retention xác định khi nào segment có thể đủ điều kiện xóa; nó không phải lệnh xóa dữ liệu ngay lập tức. Compaction cũng có thể giữ nhiều phiên bản key cho đến khi cleaner chạy và tombstone được giữ trong thời gian cấu hình.

Không hứa với nghiệp vụ rằng thay retention.ms sẽ xóa mọi bản sao ngay tức thì. Cần tính cả replica, backup, object storage, sink database, log và bản sao downstream.

### 14.2. Data minimization

Không đưa password, access token, private key hoặc dữ liệu định danh không cần thiết vào event. Một khi record được replicate đến nhiều broker và consumer, phạm vi xóa và kiểm soát bản sao sẽ phức tạp hơn.

Chỉ publish các field cần cho nghiệp vụ downstream. Đặt retention theo mục đích sử dụng và chính sách pháp lý của tổ chức.

## 15. Rủi ro theo từng loại thao tác

| Thao tác | Rủi ro | Biện pháp |
|---|---|---|
| Produce | Giả mạo event, spam, payload quá lớn | Identity riêng, ACL Write, quota, validation |
| Consume | Đọc trái phép hoặc exfiltrate dữ liệu | ACL Read và group, network policy, audit |
| Create topic | Tạo topic trái phép, tiêu thụ tài nguyên | ACL Create, naming policy, quota |
| Alter config | Giảm retention, đổi cleanup, làm mất durability | Quyền Alter/AlterConfigs hạn chế, review và audit |
| Delete topic | Mất dữ liệu và gián đoạn consumer | Quyền Delete riêng, approval, backup/retention review |
| Alter ACL | Mở rộng quyền trái phép | Admin principal riêng, audit và rà soát định kỳ |
| Transactional producer | Chiếm transactional ID hoặc ảnh hưởng giao dịch | ACL transactional ID và giới hạn principal |
| Connect create/update | Chuyển hướng dữ liệu sang hệ thống ngoài | REST authorization, plugin allowlist, egress control |
| Schema registration | Phá compatibility hoặc giả mạo schema | Registry authorization, compatibility policy |
| JMX access | Lộ metric hoặc thực hiện management operation | Isolate endpoint, read-only exporter, authentication |
| KRaft access | Thay đổi metadata hoặc ảnh hưởng quorum | Controller listener isolation và identity riêng |

### 15.1. Giảm rủi ro cạn tài nguyên và denial-of-service

Một principal đã xác thực và có ACL hợp lệ vẫn có thể gửi quá nhiều request hoặc record lớn, làm tăng CPU, network, disk và queue pressure. ACL kiểm soát quyền truy cập resource, không phải cơ chế giới hạn throughput.

Cần kết hợp:

- Client quota theo user hoặc client.id để giới hạn producer byte rate, consumer byte rate và request utilization.
- Giới hạn kích thước request/record batch ở client, topic và broker theo phiên bản, tránh payload bất thường.
- Giới hạn connection và theo dõi connection churn theo listener.
- Theo dõi request queue, network processor, disk latency, disk usage và replication lag.
- Đặt retention, quota dung lượng và cảnh báo disk watermark để tránh topic tăng vô hạn.
- Dùng firewall, gateway hoặc network-level rate control để giảm traffic không mong muốn trước broker.
- Tách quota giữa workload quan trọng để một producer lỗi không chiếm hết capacity của cluster.

Quota cần được thiết kế theo tải thực tế và phân bổ giữa các service. Nếu quota quá thấp, service hợp lệ có thể bị throttling; nếu chỉ cấu hình quota mà không giới hạn ACL, principal vẫn có thể truy cập resource không thuộc phạm vi của nó.

## 16. Ví dụ cấu hình client Java có bảo mật

Ví dụ producer dùng SASL_SSL và SCRAM. Credential được cung cấp qua environment tại runtime.

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

public class SecureProducerFactory {

    public static KafkaProducer<String, String> create() {
        String jaasConfig =
            System.getenv("KAFKA_SASL_JAAS_CONFIG");

        if (jaasConfig == null || jaasConfig.isBlank()) {
            throw new IllegalStateException(
                "KAFKA_SASL_JAAS_CONFIG is required"
            );
        }

        Properties properties = new Properties();

        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "broker-1.internal:9093,broker-2.internal:9093"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );

        properties.put("security.protocol", "SASL_SSL");
        properties.put("sasl.mechanism", "SCRAM-SHA-512");
        properties.put("sasl.jaas.config", jaasConfig);
        properties.put(
            "ssl.truststore.location",
            "/etc/kafka/security/client.truststore.jks"
        );
        properties.put(
            "ssl.endpoint.identification.algorithm",
            "https"
        );

        return new KafkaProducer<>(properties);
    }
}
~~~

Producer này vẫn cần ACL Write trên topic mục tiêu. TLS/SASL chỉ thiết lập kênh mã hóa và identity; authorizer mới quyết định principal có được ghi hay không.

Không hardcode truststore password hoặc JAAS secret trong class. Dùng secret provider, protected file mount hoặc runtime injection phù hợp môi trường.

## 17. Audit, monitoring và phát hiện bất thường

Security cần được quan sát liên tục. Một cấu hình bảo mật đúng hôm nay có thể trở nên nguy hiểm khi thêm service account, plugin hoặc listener mới.

### 17.1. Audit cần ghi nhận

- Authentication success/failure.
- Authorization denied.
- Principal được dùng cho request.
- ACL được tạo, sửa hoặc xóa.
- Topic được tạo, xóa hoặc đổi config.
- Connector được tạo, cập nhật, pause, restart hoặc delete.
- Schema được đăng ký hoặc xóa.
- Thay đổi listener, certificate và security config.
- Truy cập admin UI, JMX và secret provider.

Audit log nên có timestamp, actor, action, resource, source address, result và correlation/request ID nếu có. Không ghi password, token hoặc private key.

### 17.2. Metric và dấu hiệu bất thường

| Tín hiệu | Có thể chỉ ra |
|---|---|
| Authentication failure tăng đột biến | Credential hết hạn, client sai config hoặc dò credential |
| Authorization denied tăng | ACL thiếu hoặc actor đang thử truy cập trái phép |
| Connection count tăng bất thường | Client lỗi, scan hoặc denial-of-service |
| Produce/Fetch throughput tăng đột biến | Producer bị lỗi hoặc dữ liệu bị exfiltrate |
| Topic mới xuất hiện ngoài change window | Tạo topic trái phép hoặc automation sai |
| ACL wildcard hoặc super user thay đổi | Mở rộng quyền ngoài dự kiến |
| Consumer group lạ | Principal mới đang đọc dữ liệu |
| Connect connector mới hoặc config đổi | Luồng dữ liệu bị chuyển hướng |
| Controller quorum bất ổn | Vấn đề control plane hoặc network |
| Disk usage tăng bất thường | Retention, spam hoặc backlog |
| TLS handshake failure | Certificate hết hạn, trust chain sai hoặc scan |
| JMX/API truy cập từ subnet lạ | Management plane bị lộ |

### 17.3. Alert có ngữ cảnh

Kết hợp metric với baseline:

- Số authentication failure trên mỗi principal.
- Số topic/ACL thay đổi ngoài lịch triển khai.
- Số lần connector config thay đổi.
- Dung lượng dữ liệu theo topic và principal nếu telemetry hỗ trợ.
- Consumer lag và throughput theo group.
- Số connection theo listener và source network.
- Tình trạng certificate còn bao nhiêu ngày trước expiry.

Một cảnh báo có tên principal, resource và source address sẽ hữu ích hơn cảnh báo chung “Kafka security error”.

## 18. Ứng phó sự cố bảo mật

Khi phát hiện credential bị lộ hoặc principal có hành vi bất thường:

1. Xác định principal, source host, listener và thời điểm.
2. Xác định topic, group, connector hoặc resource đã truy cập.
3. Thu thập audit, broker log, controller log và network telemetry.
4. Thu hồi hoặc rotate credential/certificate bị lộ.
5. Tạm thời thu hẹp ACL hoặc chặn network path có rủi ro.
6. Kiểm tra topic, ACL, connector config, schema và consumer group có bị thay đổi không.
7. Đánh giá dữ liệu có bị đọc, sửa, xóa hoặc chuyển ra ngoài không.
8. Khôi phục cấu hình từ nguồn kiểm soát nếu có thay đổi trái phép.
9. Xác minh workload hợp lệ đã kết nối lại bằng credential mới.
10. Lưu bằng chứng và ghi lại nguyên nhân gốc.

Không xóa log hoặc topic ngay khi phát hiện sự cố. Bảo toàn bằng chứng, xác định phạm vi ảnh hưởng và tuân thủ quy trình incident response của tổ chức.

### 18.1. Nếu producer credential bị lộ

- Thu hồi hoặc rotate credential.
- Xác định topic principal có quyền Write.
- Kiểm tra record bất thường theo timestamp, key, source metadata và event ID.
- Kiểm tra transactional ID nếu producer dùng transaction.
- Xem downstream có thực hiện side effect từ event giả hay không.
- Cân nhắc quarantine hoặc rebuild dữ liệu nếu event giả đã được xử lý.

### 18.2. Nếu consumer credential bị lộ

- Thu hồi credential và ACL Read liên quan.
- Xác định topic/group mà principal truy cập được.
- Đánh giá dữ liệu đã bị đọc hoặc exfiltrate.
- Kiểm tra group offset và hành vi commit bất thường.
- Xem credential có được dùng ở service khác do chia sẻ identity không.
- Tách service account nếu trước đây nhiều workload dùng chung.

### 18.3. Nếu Connect REST bị xâm phạm

- Chặn truy cập REST endpoint từ nguồn không tin cậy.
- Kiểm tra connector mới, config thay đổi và plugin được nạp.
- Kiểm tra egress từ worker đến database/API/object storage.
- Rotate secret của hệ thống nguồn/đích có thể bị truy cập.
- Kiểm tra dữ liệu bị đọc hoặc gửi sang destination lạ.
- Khôi phục connector config từ snapshot đã kiểm chứng.
- Kiểm tra integrity của worker image và plugin directory.

## 19. Hardening baseline theo môi trường

| Lớp | Lab | Staging | Production |
|---|---|---|---|
| Listener | Có thể dùng PLAINTEXT trong môi trường local cô lập | TLS và identity thử nghiệm | Listener tách biệt, TLS và auth bắt buộc |
| Authentication | Tối giản để học protocol | Principal riêng theo service | SCRAM/OAuth/mTLS theo identity policy |
| Authorization | ACL cơ bản | Least privilege cho producer/consumer | ACL đầy đủ, review và audit |
| KRaft | Controller local hoặc cluster lab | Listener nội bộ được giới hạn | Controller quorum cô lập và bảo vệ |
| Connect REST | Local-only | Protected endpoint | TLS, authentication, authorization, audit |
| Secret | Giá trị test không nhạy cảm | Secret store staging | Secret manager, rotation và access audit |
| Storage | Disk local | Volume encryption | Encryption at rest, backup encryption |
| Monitoring | Log cơ bản | Security metrics và alerts | Audit tập trung, alert và incident runbook |
| Plugin | Plugin mẫu | Version pin và scan | Allowlist, checksum, review và patch |
| Admin access | Developer local | Role-based | MFA/SSO, bastion và approval |

Không mang cấu hình lab vào production. PLAINTEXT, credential dùng chung, wildcard ACL và REST API mở có thể tiện cho thử nghiệm nhưng không tạo ranh giới tin cậy đủ an toàn.

## 20. Checklist đánh giá ranh giới tin cậy

Khi review một Kafka deployment, hãy kiểm tra:

1. Đã liệt kê dữ liệu, metadata, credential và management endpoint cần bảo vệ chưa?
2. Đã phân loại data plane, control plane và management plane chưa?
3. Producer/consumer chỉ truy cập client listener cần thiết chưa?
4. Broker-to-broker listener có được tách và bảo vệ không?
5. KRaft controller listener có bị giới hạn khỏi client network không?
6. advertised.listeners có công bố đúng địa chỉ cho từng network zone không?
7. Có dùng TLS cho dữ liệu nhạy cảm và traffic nội bộ không?
8. Hostname verification có được bật và certificate có SAN đúng không?
9. Authentication có principal riêng cho từng workload không?
10. Authorization có ACL least privilege cho topic và consumer group không?
11. Super user có ít, được bảo vệ và audit không?
12. Connect REST, Schema Registry API và JMX có được bảo vệ riêng không?
13. Plugin có nguồn tin cậy, version pin và checksum không?
14. Connect worker có egress policy giới hạn destination không?
15. Secret có nằm ngoài source code, image, log và artifact không?
16. Certificate/token có rotation và revocation plan không?
17. Internal topics có ACL, replication và retention phù hợp không?
18. Data at rest và backup có encryption/access control không?
19. Có audit cho ACL, topic, connector và schema changes không?
20. Có runbook khi principal bị lộ hoặc management API bị xâm phạm không?

## 21. Bài tập thực hành

### Bài 1: Vẽ trust boundary

1. Vẽ producer, consumer, broker, KRaft controller, Connect, Streams, Schema Registry và database.
2. Đánh dấu data plane, control plane và management plane.
3. Vẽ từng network connection.
4. Ghi principal và resource mà mỗi thành phần truy cập.
5. Xác định ba trust boundary có rủi ro cao nhất.
6. Đề xuất firewall, TLS và ACL cho từng boundary.

### Bài 2: So sánh protocol bảo mật

1. Tạo Kafka lab local.
2. Kết nối lần lượt bằng PLAINTEXT và SASL_SSL.
3. Quan sát cấu hình client và server.
4. Giải thích protocol nào mã hóa traffic và protocol nào xác thực principal.
5. Thử certificate hostname mismatch.
6. Khôi phục certificate/SAN đúng và xác minh TLS handshake.

### Bài 3: ACL least privilege

1. Tạo principal orders-producer.
2. Cấp Write và Describe cho topic orders.
3. Dùng principal đó gửi record thành công.
4. Thử đọc topic và xác nhận bị từ chối nếu chưa cấp Read.
5. Tạo principal orders-consumer.
6. Cấp Read trên topic và group orders-service.
7. Xác minh consumer đọc được đúng resource cần thiết.

### Bài 4: Tách listener

1. Cấu hình CLIENT và INTERNAL listener trong môi trường lab.
2. Chọn protocol cho từng listener.
3. Đặt advertised.listeners phù hợp network client.
4. Xác nhận producer kết nối CLIENT.
5. Xác nhận broker replication dùng INTERNAL.
6. Kiểm tra controller listener không được expose cho client application.

### Bài 5: Bảo vệ Connect REST

1. Khởi động Connect distributed mode.
2. Liệt kê endpoint REST có thể truy cập.
3. Đặt REST API sau network boundary được bảo vệ.
4. Bật authentication/TLS theo cơ chế triển khai.
5. Tạo connector bằng principal được phép.
6. Thử cập nhật connector bằng principal không có quyền.
7. Kiểm tra audit và worker log.

### Bài 6: Xử lý credential bị lộ

1. Tạo service account riêng cho producer lab.
2. Giả lập credential bị lộ trong môi trường test.
3. Thu hồi hoặc rotate credential.
4. Thu hẹp ACL nếu cần.
5. Xác minh producer cũ không thể kết nối.
6. Xác minh producer mới hoạt động với credential mới.
7. Ghi lại quy trình và thời gian phục hồi.

## 22. Câu hỏi tự kiểm tra

1. Attack surface trong Kafka deployment gồm những thành phần nào?
2. Data plane, control plane và management plane khác nhau ra sao?
3. Vì sao không nên xem mọi workload trong cùng subnet là đáng tin cậy?
4. TLS bảo vệ điều gì và không giải quyết điều gì?
5. PLAINTEXT, SSL, SASL_PLAINTEXT và SASL_SSL khác nhau thế nào?
6. Authentication khác authorization ở đâu?
7. SCRAM khác SASL/PLAIN như thế nào?
8. mTLS xác thực client bằng cách nào?
9. Vì sao principal nên riêng cho từng workload?
10. StandardAuthorizer có vai trò gì trong KRaft?
11. Producer cần ACL nào để ghi topic?
12. Consumer cần quyền nào trên topic và group?
13. Vì sao super.users phải được giới hạn?
14. Tại sao controller listener không nên mở cho client?
15. advertised.listeners ảnh hưởng đến kết nối sau bootstrap thế nào?
16. Connect REST API và Kafka broker ACL là hai lớp bảo mật ra sao?
17. Vì sao connector plugin là một phần của supply chain risk?
18. Secret nên được lưu và rotation như thế nào?
19. TLS có mã hóa file log trên disk không?
20. Khi credential bị lộ, cần thu thập và xử lý những gì trước khi khôi phục?

## Kết luận

Bảo mật Kafka cần được thiết kế theo ranh giới tin cậy và luồng dữ liệu thực tế. Broker listener, inter-broker traffic, KRaft controller, Connect REST, Schema Registry, JMX, plugin, secret provider và hệ thống ngoài đều là các bề mặt cần kiểm soát.

TLS bảo vệ dữ liệu trên đường truyền; SASL hoặc mTLS xác thực danh tính; ACL và StandardAuthorizer giới hạn principal được làm gì trên topic, group và resource. Network segmentation giảm khả năng tiếp cận, còn secret management, certificate rotation, plugin review, audit và monitoring giúp duy trì bảo mật trong suốt vòng đời hệ thống.

Không có một cấu hình đơn lẻ bảo vệ toàn bộ Kafka. Hãy bắt đầu bằng asset inventory và threat model, tách data/control/management plane, cấp quyền least privilege, bảo vệ KRaft và REST endpoint, sau đó kiểm thử cả đường đi hợp lệ lẫn đường truy cập bị từ chối. Khi có sự cố, thu hồi identity, giới hạn phạm vi, bảo toàn audit evidence và xác minh dữ liệu trước khi đưa hệ thống trở lại hoạt động.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Attack surface | Tập hợp điểm mà actor có thể tương tác với hệ thống và tạo rủi ro. |
| Trust boundary | Ranh giới giữa các thành phần hoặc zone có mức độ tin cậy khác nhau. |
| Data plane | Mặt phẳng truyền và xử lý record. |
| Control plane | Mặt phẳng điều phối broker, controller và cluster metadata. |
| Management plane | REST API, JMX, admin UI và công cụ vận hành. |
| Threat model | Mô hình hóa tài sản, actor, luồng dữ liệu, mối đe dọa và biện pháp kiểm soát. |
| TLS | Giao thức mã hóa và bảo vệ tính toàn vẹn kết nối. |
| mTLS | TLS yêu cầu cả server và client xác thực bằng certificate. |
| SASL | Framework xác thực client với Kafka. |
| SCRAM | Cơ chế SASL dùng challenge-response dựa trên username/password. |
| OAuthBearer | Cơ chế SASL sử dụng bearer token từ identity provider. |
| Authentication | Xác minh danh tính của principal. |
| Authorization | Kiểm tra principal có quyền thực hiện operation trên resource. |
| ACL | Quy tắc phân quyền cho principal trên Kafka resource. |
| StandardAuthorizer | Kafka authorizer phổ biến trong KRaft để kiểm tra ACL. |
| Listener | Endpoint broker bind để nhận kết nối theo protocol/security policy. |
| advertised.listeners | Địa chỉ broker công bố trong metadata cho client kết nối. |
| KRaft controller listener | Listener dành cho broker/controller control-plane communication. |
| Secret rotation | Thay credential, token hoặc key theo chu kỳ hoặc khi có sự cố. |
| Supply-chain security | Kiểm soát nguồn gốc, dependency và integrity của plugin/image. |
| Least privilege | Chỉ cấp quyền tối thiểu cần cho nhiệm vụ của principal. |
| Data at rest | Dữ liệu được lưu trên disk, volume, backup hoặc snapshot. |
| Audit trail | Dấu vết ghi nhận actor, hành động, resource, thời điểm và kết quả. |

