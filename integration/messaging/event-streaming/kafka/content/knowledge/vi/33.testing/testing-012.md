# Kiểm thử ACL, TLS và cấu hình sai

Bảo mật Kafka cần được kiểm thử theo từng lớp thay vì chỉ xác nhận rằng client kết nối được broker. Một kết nối thành công mới chứng minh một phần của đường truyền; nó chưa chứng minh danh tính được xác thực đúng, quyền truy cập được giới hạn đúng, hay cấu hình sai sẽ bị phát hiện an toàn.

Trong bài này, **TLS** bảo vệ đường truyền và xác minh peer; **SASL** xác thực danh tính client; **ACL** quyết định principal được phép thực hiện thao tác nào trên topic, consumer group, transactional ID hoặc cluster. Với KRaft, authorizer phải được cấu hình trên broker/controller theo topology triển khai. Các bài test cần có cả trường hợp được phép và bị từ chối.

## 1. Mục tiêu và phạm vi kiểm thử

Một bộ kiểm thử tốt cần chứng minh các thuộc tính sau:

1. Client hợp lệ kết nối đúng listener, xác minh đúng chứng thư và hostname.
2. Client không tin CA, certificate hết hạn hoặc hostname không khớp bị từ chối.
3. Client có credentials đúng được xác thực; credentials sai hoặc thiếu bị từ chối.
4. Principal hợp lệ chỉ thực hiện được đúng các thao tác ACL đã cấp.
5. Principal không có ACL không đọc/ghi được tài nguyên ngoài phạm vi.
6. Consumer group, transactional ID và cluster-level permissions không bị bỏ sót.
7. Cấu hình listener, SASL, TLS, authorizer hoặc ACL sai tạo lỗi có thể chẩn đoán và không làm lộ bí mật.
8. Sau khi sửa cấu hình, dịch vụ hoạt động lại mà không nới quyền quá mức.

Không dùng một bài test duy nhất để kết luận toàn bộ security đã đúng. Hãy kiểm thử từng lớp và ghi lại principal, listener, resource, operation, expected result và evidence.

## 2. Phân biệt TLS, SASL và ACL

| Lớp | Câu hỏi được trả lời | Ví dụ lỗi |
|---|---|---|
| Network/listener | Client có tới đúng endpoint và protocol không? | DNS, firewall, port, advertised listener sai |
| TLS | Hai đầu có thiết lập kênh mã hóa và tin chứng thư của nhau không? | CA không tin cậy, certificate hết hạn, SAN không khớp |
| SASL | Client là principal nào? | Username/password sai, mechanism không khớp |
| ACL authorization | Principal đó được làm gì trên resource nào? | TopicAuthorizationException, GroupAuthorizationException |
| Application contract | Ứng dụng có xử lý lỗi đúng không? | Retry vô hạn, log lộ credentials, fallback sai |

**TLS không tự cấp quyền Kafka.** Client có thể hoàn tất TLS nhưng vẫn bị ACL từ chối. **SASL authentication không thay ACL.** Xác thực thành công chỉ tạo principal; authorizer vẫn phải quyết định quyền. **ACL không sửa được lỗi TLS/SASL.** Nếu handshake hoặc authentication thất bại thì request chưa đi tới bước authorization thông thường.

Kafka có thể dùng SSL một mình, SASL_PLAINTEXT, SASL_SSL hoặc listener khác nhau cho client, inter-broker và controller. Môi trường production thường ưu tiên TLS; nếu dùng SASL thì thường chọn SASL_SSL để credentials không truyền trên kênh plaintext.

## 3. Mô hình kiểm thử KRaft và StandardAuthorizer

Trong KRaft, Kafka có thể dùng StandardAuthorizer:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
allow.everyone.if.no.acl.found=false
super.users=User:cluster-admin
~~~

`allow.everyone.if.no.acl.found=false` thể hiện chính sách deny-by-default khi resource chưa có ACL phù hợp. Cần xác nhận giá trị hiệu lực theo phiên bản và cấu hình thực tế. `super.users` là quyền đặc biệt, không dùng cho tài khoản ứng dụng; principal được khai báo ở đây có thể vượt qua các ACL thông thường.

Các điểm phải kiểm tra theo topology:

- Broker và controller đều có cấu hình authorizer tương thích với phiên bản Kafka đang chạy.
- Listener controller và inter-broker có security protocol, principal và quyền cần thiết để các node trao đổi.
- Client listener không vô tình dùng cấu hình nội bộ hoặc mở quyền rộng hơn.
- Principal sau SASL hoặc TLS mapping đúng như ACL mong đợi.
- Các thay đổi ACL được ghi nhận và nhìn thấy nhất quán trên các node.

Không sao chép cấu hình KRaft của một topology khác rồi áp dụng trực tiếp. Listener, controller quorum, `process.roles`, `controller.listener.names` và `inter.broker.listener.name` phụ thuộc cách triển khai cụ thể.

## 4. Kiểm thử TLS

### 4.1. Những điều cần xác minh

TLS test không chỉ là kiểm tra port mở. Tối thiểu phải xác minh:

- Broker trình certificate chain mà client tin cậy.
- Certificate còn hạn và có Extended Key Usage phù hợp với vai trò.
- Subject Alternative Name (SAN) chứa hostname mà client sử dụng.
- Client bật hostname verification.
- Phiên bản TLS và cipher suite nằm trong policy được chấp nhận.
- Nếu dùng mutual TLS (mTLS), broker yêu cầu và xác minh certificate client.
- Certificate rotation không làm gián đoạn bất ngờ hoặc khiến client tin CA không mong muốn.

Hostname verification đặc biệt quan trọng khi client kết nối tới địa chỉ lấy từ `advertised.listeners`. Client có thể bootstrap tới broker đầu tiên thành công nhưng sau đó nhận metadata trỏ tới hostname khác; nếu certificate không có SAN cho hostname đó, request tiếp theo sẽ thất bại.

### 4.2. Broker listener dùng SSL

Ví dụ listener client SSL độc lập:

~~~properties
listeners=CLIENT://:9093,CONTROLLER://:9094
advertised.listeners=CLIENT://kafka-1.example.net:9093
listener.security.protocol.map=CLIENT:SSL,CONTROLLER:SSL
controller.listener.names=CONTROLLER

listener.name.client.ssl.keystore.location=/etc/kafka/secrets/broker.p12
listener.name.client.ssl.keystore.password=${BROKER_KEYSTORE_PASSWORD}
listener.name.client.ssl.keystore.type=PKCS12
listener.name.client.ssl.truststore.location=/etc/kafka/secrets/client-ca.jks
listener.name.client.ssl.truststore.password=${CLIENT_CA_PASSWORD}
listener.name.client.ssl.client.auth=required
ssl.enabled.protocols=TLSv1.2,TLSv1.3
~~~

Đây là cấu hình minh họa, không phải file server hoàn chỉnh. Tên prefix listener được chuẩn hóa thành chữ thường trong property `listener.name.client...`. Với mTLS, `client.auth=required` yêu cầu client certificate; nếu chỉ muốn TLS server-side thì không bật yêu cầu này. Cấu hình SSL của controller/inter-broker listener cần được thiết kế riêng theo topology, không giả định chúng dùng cùng truststore hoặc keystore.

Nếu dùng SASL_SSL, protocol map của listener tương ứng là `SASL_SSL` và cần cấu hình SASL mechanism/JAAS cho listener đó. Không trộn cấu hình SSL thuần với SASL_SSL mà không đồng bộ cả client lẫn broker.

### 4.3. Client truststore và hostname verification

Ví dụ client properties khi dùng SSL thuần:

~~~properties
security.protocol=SSL
ssl.truststore.location=/etc/app/kafka-truststore.jks
ssl.truststore.password=${KAFKA_TRUSTSTORE_PASSWORD}
ssl.truststore.type=JKS
ssl.endpoint.identification.algorithm=https
~~~

`ssl.endpoint.identification.algorithm=https` bật kiểm tra hostname theo chuẩn HTTPS. Không đặt giá trị rỗng để né lỗi SAN trong production; phải sửa certificate hoặc hostname. Truststore nên chỉ chứa CA cần thiết, không tùy tiện import mọi certificate vào truststore dùng chung.

Nếu dùng mTLS, bổ sung client keystore:

~~~properties
ssl.keystore.location=/etc/app/client-keystore.p12
ssl.keystore.password=${KAFKA_KEYSTORE_PASSWORD}
ssl.keystore.type=PKCS12
ssl.key.password=${KAFKA_KEY_PASSWORD}
~~~

Không đưa password thật vào repository, image, command history hoặc log. Dùng secret manager hay cơ chế inject secret phù hợp môi trường triển khai.

### 4.4. Kiểm tra handshake bằng OpenSSL

Kiểm tra server certificate chain và hostname:

~~~bash
openssl s_client \
  -connect kafka-1.example.net:9093 \
  -servername kafka-1.example.net \
  -CAfile ca.crt \
  -verify_hostname kafka-1.example.net \
  -verify_return_error
~~~

Với mTLS, cung cấp client certificate và private key:

~~~bash
openssl s_client \
  -connect kafka-1.example.net:9093 \
  -servername kafka-1.example.net \
  -CAfile ca.crt \
  -verify_hostname kafka-1.example.net \
  -cert client.crt \
  -key client.key \
  -verify_return_error
~~~

OpenSSL xác minh TLS handshake, không chứng minh SASL hoặc Kafka ACL hoạt động. Cần dùng Kafka client CLI để kiểm tra các lớp tiếp theo. Nếu dùng TLS version/cipher policy riêng, có thể thêm tùy chọn phù hợp cho OpenSSL để kiểm tra đúng policy.

### 4.5. Negative tests cho TLS

| Test | Thay đổi có chủ đích | Kết quả mong đợi |
|---|---|---|
| CA không tin cậy | Dùng truststore thiếu CA ký broker cert | TLS handshake thất bại |
| Certificate hết hạn | Dùng cert hết hạn trong lab | Client từ chối cert |
| SAN không khớp | Kết nối bằng hostname không có trong SAN | Hostname verification thất bại |
| Không gửi client cert | Broker yêu cầu mTLS | Handshake bị từ chối |
| Client cert không tin cậy | Client cert do CA khác ký | Broker từ chối client |
| Client cert hết hạn | Dùng cert hết hạn | Broker từ chối client |
| Protocol không tương thích | Ép client dùng TLS version bị cấm | Handshake thất bại |
| Sai port/listener | Kết nối nhầm listener hoặc plaintext port | Protocol/handshake error |

Negative test phải chạy trong môi trường test riêng. Không thay certificate hoặc TLS policy trên broker production chỉ để chứng minh một test case.

## 5. Kiểm thử SASL authentication

### 5.1. SASL/SCRAM là gì?

SASL xác thực principal. Với SCRAM, broker lưu verifier/credential material và client chứng minh biết secret mà không gửi password dạng plaintext như SASL/PLAIN. Cấu hình cơ chế, credential provisioning và listener phải khớp nhau.

Ví dụ cấu hình client SASL_SSL với SCRAM-SHA-512:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-app" password="${ORDERS_APP_PASSWORD}";
ssl.truststore.location=/etc/app/kafka-truststore.jks
ssl.truststore.password=${KAFKA_TRUSTSTORE_PASSWORD}
ssl.endpoint.identification.algorithm=https
~~~

Đoạn JAAS trên là minh họa. Trong triển khai thực tế, thay placeholder bằng secret được inject an toàn; không ghi password vào file cấu hình được commit.

Broker listener phải bật đúng SASL mechanism. Với SCRAM, credential cho user phải được provision trong Kafka metadata/config theo quy trình quản trị phù hợp với phiên bản Kafka. Không giả định chỉ tạo ACL là đủ để tạo SASL user.

### 5.2. Negative tests cho SASL

- Username không tồn tại.
- Password sai.
- Không gửi SASL credentials.
- Client dùng SCRAM-SHA-256 trong khi listener chỉ cho SCRAM-SHA-512.
- Client gửi PLAIN nhưng broker không bật PLAIN.
- Client kết nối nhầm listener không hỗ trợ SASL.
- Secret bị rotate ở broker nhưng client vẫn dùng secret cũ.
- Credential hết hiệu lực hoặc bị thu hồi theo chính sách nội bộ.

Kết quả mong đợi là authentication bị từ chối trước authorization. Không chấp nhận việc ứng dụng tự động fallback sang PLAINTEXT hoặc principal dùng chung khi SASL thất bại.

### 5.3. Phân biệt lỗi authentication và authorization

| Dấu hiệu | Lớp thường gây lỗi | Hướng điều tra |
|---|---|---|
| SaslAuthenticationException | SASL authentication | Username, password, mechanism, JAAS và listener |
| SSLHandshakeException | TLS | CA, SAN, expiry, client cert và protocol |
| TopicAuthorizationException | ACL topic | Principal, topic pattern và operation |
| GroupAuthorizationException | ACL consumer group | Principal, group ID và Read permission |
| ClusterAuthorizationException | ACL cluster | Cluster resource và operation |
| TransactionalIdAuthorizationException | ACL transactional ID | Transactional ID pattern và Write permission |
| TimeoutException hoặc disconnect | Có thể là network/listener/TLS/auth | Đối chiếu client exception với broker log; không kết luận chỉ từ timeout |

Tên exception có thể được bọc trong KafkaException, ExecutionException hoặc callback của framework. Ghi nhận root cause, broker log và request context thay vì chỉ assert một chuỗi thông báo.

## 6. Kiểm thử ACL authorization

### 6.1. Tạo ACL theo nguyên tắc least privilege

Giả sử principal User:orders-app chỉ cần produce vào topic orders:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-app \
  --operation Write \
  --operation Describe \
  --topic orders
~~~

Consumer có group ID orders-reader-v1 cần quyền đọc topic và consumer group:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-reader \
  --operation Read \
  --operation Describe \
  --topic orders

kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-reader \
  --operation Read \
  --group orders-reader-v1
~~~

Các quyền Describe tường minh trong ví dụ giúp policy dễ đọc; Kafka có quan hệ implication giữa một số operation, do đó ACL tối thiểu chính xác có thể khác theo thao tác và phiên bản. Xác minh bằng test thực tế, không cấp All chỉ để làm cho lệnh chạy được.

Tài khoản quản trị dùng trong --command-config cần quyền quản trị ACL trên resource liên quan hoặc là superuser theo policy. Không dùng tài khoản admin để chạy test positive/negative của ứng dụng vì nó sẽ che khuất lỗi phân quyền.

### 6.2. ACL cho transactional producer

Producer dùng transaction cần quyền trên transactional ID tương ứng. Ví dụ cấp quyền cho prefix orders-tx-:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-tx-app \
  --operation Write \
  --transactional-id orders-tx- \
  --resource-pattern-type prefixed
~~~

Nếu producer bật idempotence, kiểm tra yêu cầu cluster-level IdempotentWrite của phiên bản Kafka đang dùng. Không cấp quyền transactional ID hoặc cluster rộng hơn nhu cầu chỉ để bỏ lỗi. Test cả initTransactions, beginTransaction, send, commit và abort trong môi trường test.

### 6.3. ACL cho các thao tác quản trị

Một số thao tác không chỉ phụ thuộc ACL topic:

| Hành động | Resource/operation cần xem xét |
|---|---|
| Produce | Topic: Write; Describe có thể cần tùy API |
| Consume | Topic: Read; Group: Read |
| Commit offset | Group: Read |
| Tạo topic | Cluster: Create hoặc quyền Create trên resource theo policy/phiên bản |
| Xóa topic | Topic: Delete |
| Thay đổi topic config | Topic: AlterConfigs |
| Đọc topic config | Topic: DescribeConfigs |
| Transactional producer | Transactional ID: Write; kiểm tra IdempotentWrite nếu dùng idempotence |
| Quản lý ACL | Cluster: Alter hoặc quyền quản trị tương ứng |
| Describe cluster | Cluster: Describe |

Đây là bản đồ định hướng, không phải danh sách thay thế authorization matrix của từng API. Một lệnh CLI có thể gọi nhiều API và cần nhiều quyền hơn dự kiến. Hãy kiểm tra broker authorization log để biết resource và operation thực sự bị từ chối.

### 6.4. Literal, prefixed và wildcard

Kafka ACL có resource pattern literal và prefixed. Ví dụ cấp Read cho topic có prefix orders-:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-reader \
  --operation Read \
  --topic orders- \
  --resource-pattern-type prefixed
~~~

Cần test các tên nằm trong và ngoài prefix, ví dụ orders-created, orders-dead-letter và payments. Không dùng wildcard * nếu chỉ cần một tập topic. Kiểm tra ACL list để xác nhận pattern được lưu như dự định.

### 6.5. Deny ACL và default deny

Nếu một principal khớp cả allow và deny ACL, deny có ưu tiên trong quyết định authorization thông thường. Superuser có thể được xử lý đặc biệt. Khi test deny, đảm bảo principal không nằm trong super.users, không dùng admin credential và không có ACL wildcard khác vô tình cho phép thao tác.

Với deny-by-default, principal không có ACL phù hợp phải bị từ chối. Đây là test quan trọng cho topic mới được tạo: không để topic chưa có ACL trở thành public do cấu hình allow.everyone.if.no.acl.found không đúng.

## 7. Bộ test ACL positive và negative

Giả sử có ba principal:

- User:orders-producer: chỉ ghi topic orders.
- User:orders-consumer: chỉ đọc topic orders với group orders-reader-v1.
- User:payments-app: chỉ có quyền trên topic payments.

| ID | Principal | Thao tác | Resource | Kết quả mong đợi |
|---|---|---|---|---|
| ACL-01 | orders-producer | Produce | orders | Allow |
| ACL-02 | orders-producer | Consume | orders | Deny |
| ACL-03 | orders-producer | Produce | payments | Deny |
| ACL-04 | orders-consumer | Consume | orders, đúng group | Allow |
| ACL-05 | orders-consumer | Consume | orders, group khác | Deny |
| ACL-06 | orders-consumer | Consume | payments | Deny |
| ACL-07 | payments-app | Produce | payments | Allow |
| ACL-08 | payments-app | Produce | orders | Deny |
| ACL-09 | principal không có ACL | List/consume topic được bảo vệ | Topic bất kỳ | Deny |
| ACL-10 | orders-producer | Tạo topic mới | Cluster/topic | Deny nếu không được cấp Create |
| ACL-11 | orders-tx-app | Transaction commit | Đúng transactional ID | Allow |
| ACL-12 | orders-tx-app | Transaction dùng ID khác | Transactional ID khác | Deny |
| ACL-13 | orders-reader | Consume | Topic có prefix được phép | Allow |
| ACL-14 | orders-reader | Consume | Topic ngoài prefix | Deny |
| ACL-15 | user thường | Alter ACL | Cluster | Deny |

Với mỗi case, lưu lại principal thực tế, topic/group/transactional ID, operation, exit code hoặc exception, broker log và ACL snapshot trước/sau test.

## 8. Chạy test bằng Kafka CLI

Tạo file producer.properties cho principal producer và consumer.properties cho principal consumer. Cả hai phải dùng listener bảo mật, truststore và SASL settings đúng principal. Dùng admin.properties riêng cho lệnh quản trị ACL.

Produce một record:

~~~bash
kafka-console-producer.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --producer.config producer.properties \
  --topic orders
~~~

Consume với group đã được cấp quyền:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --consumer.config consumer.properties \
  --topic orders \
  --group orders-reader-v1 \
  --from-beginning
~~~

Thử truy cập topic ngoài quyền trong môi trường test:

~~~bash
kafka-console-producer.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --producer.config producer.properties \
  --topic payments
~~~

Lệnh cuối phải thất bại do authorization. Không đánh giá kết quả chỉ bằng việc CLI in lỗi: xác nhận broker log ghi đúng principal và resource. Consumer với --from-beginning chỉ đọc dữ liệu còn retention; không xem việc thiếu record cũ là lỗi ACL nếu dữ liệu đã hết hạn.

Xem ACL hiện có:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --list
~~~

Để tránh xóa ACL nhầm, lưu snapshot ACL trước test và chỉ xóa đúng principal/resource vừa tạo. Không chạy lệnh xóa ACL rộng trên môi trường dùng chung.

## 9. Kiểm thử cấu hình sai có kiểm soát

Cấu hình sai thường gây lỗi khó phân biệt: sai listener hoặc advertised address có thể biểu hiện như timeout; sai truststore gây handshake failure; sai SASL mechanism gây authentication failure; sai ACL gây authorization failure. Hãy thay đổi một biến mỗi lần để giữ quan hệ nguyên nhân-kết quả.

### 9.1. Ma trận fault injection

| ID | Cấu hình cố ý sai | Triệu chứng mong đợi | Lớp lỗi |
|---|---|---|---|
| CFG-01 | Client dùng nhầm port PLAINTEXT thay SSL | Protocol/handshake error | Listener |
| CFG-02 | advertised.listeners trả hostname không resolve được | Bootstrap được nhưng request sau thất bại/timeout | Metadata/network |
| CFG-03 | Advertised hostname không có trong SAN | Hostname verification error | TLS |
| CFG-04 | Client truststore thiếu CA | SSL handshake failure | TLS trust |
| CFG-05 | Broker yêu cầu mTLS nhưng client không có cert | Handshake bị từ chối | TLS client auth |
| CFG-06 | SASL mechanism client không khớp broker | Authentication failure | SASL |
| CFG-07 | Username/password sai | SASL authentication failure | SASL |
| CFG-08 | Principal đúng nhưng thiếu ACL Write | Produce bị authorization deny | ACL |
| CFG-09 | Consumer có Topic Read nhưng thiếu Group Read | Consumer group operation bị deny | ACL |
| CFG-10 | Topic filter hoặc ACL pattern sai | Chỉ một tập topic được truy cập | ACL/resource naming |
| CFG-11 | Listener protocol map không khớp listener | Broker không khởi động hoặc client handshake lỗi | Broker config |
| CFG-12 | Authorizer class sai/không tương thích | Broker không khởi động hoặc authorization không hoạt động | Authorizer |
| CFG-13 | Controller/inter-broker listener security không khớp | Node không join hoặc cluster mất quorum | Internal listener |

### 9.2. Nguyên tắc fault injection

1. Chọn cluster lab cô lập và lưu bản cấu hình đang hoạt động.
2. Ghi baseline: broker health, controller quorum, listener endpoints, client success và ACL snapshot.
3. Chọn một lỗi nhỏ, tác động lên một broker/client hoặc một principal test.
4. Dự đoán trước log và exception mong đợi.
5. Thực hiện thay đổi, quan sát client, broker log và metrics.
6. Khôi phục cấu hình ngay sau test; xác minh node/cluster health trở lại baseline.
7. Ghi lại thời gian phát hiện, thời gian phục hồi và false positive.

Không cố ý làm sai controller quorum, inter-broker security hoặc toàn bộ listener trên cluster production. Fault injection ở lớp control plane có thể làm mất quorum và ảnh hưởng toàn cluster.

### 9.3. Kiểm tra listener và metadata

Dùng công cụ Kafka để kiểm tra endpoint và API:

~~~bash
kafka-broker-api-versions.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config client.properties
~~~

Lệnh này kiểm tra kết nối và khả năng trao đổi API với broker, không thay thế kiểm thử produce/consume/ACL. Khi client bootstrap thành công nhưng produce/consume timeout, kiểm tra metadata response và tất cả hostname/port trong advertised.listeners, không chỉ bootstrap server.

Các property cần rà soát cùng nhau:

- listeners: địa chỉ và listener broker bind.
- advertised.listeners: địa chỉ broker công bố cho client.
- listener.security.protocol.map: ánh xạ tên listener sang protocol.
- inter.broker.listener.name: listener dùng cho broker-to-broker traffic.
- controller.listener.names: listener controller trong KRaft.
- sasl.enabled.mechanisms và cấu hình JAAS theo listener.
- SSL keystore, truststore, client-auth policy và certificate SAN.

Không công khai controller listener cho client ứng dụng. Không đưa listener nội bộ vào advertised.listeners cho client ngoài mạng broker.

### 9.4. Kiểm tra cấu hình hiệu lực

Với quyền quản trị phù hợp, dùng kafka-configs.sh --describe để xem dynamic config của broker/topic/user theo phiên bản và loại entity:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --entity-type brokers \
  --entity-name 1 \
  --describe
~~~

Lưu ý: lệnh này không nhất thiết hiển thị mọi static property trong file cấu hình broker. Đối chiếu file triển khai, startup logs, dynamic config và tài liệu đúng phiên bản. Không paste output có secret vào ticket/chat; redact password, JAAS và private key.

## 10. Kiểm thử bằng Spring Kafka

### 10.1. Cấu hình Spring Boot client

Ví dụ cấu hình ứng dụng producer/consumer dùng SASL_SSL và SCRAM:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-app" password="${ORDERS_APP_PASSWORD}";
      ssl.endpoint.identification.algorithm: https
    ssl:
      trust-store-location: file:/etc/app/kafka-truststore.jks
      trust-store-password: ${KAFKA_TRUSTSTORE_PASSWORD}
      trust-store-type: JKS
~~~

Tên property và khả năng bind phụ thuộc Spring Boot version. Với mTLS, cấu hình thêm client key store và key password theo reference của phiên bản Spring Boot đang dùng. Không đưa password literal vào application.yml được commit.

Tách profile rõ ràng: test profile dùng broker test và test credentials; production profile lấy secret từ secret manager. Không để test vô tình kết nối cluster production.

### 10.2. Kiểm tra authorization trong integration test

Ví dụ JUnit 5 kiểm tra producer không có quyền ghi vào topic bị khóa. Test phải chạy bằng credential thực sự thiếu quyền, không phải admin:

~~~java
@SpringBootTest
class KafkaAclIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void shouldRejectProduceToForbiddenTopic() {
        assertThatThrownBy(() ->
                kafkaTemplate.send("payments-private", "order-1", "payload")
                    .get(10, TimeUnit.SECONDS)
        ).hasRootCauseInstanceOf(TopicAuthorizationException.class);
    }
}
~~~

Đoạn test giả định JUnit 5, AssertJ và Spring Kafka đã có trong project. Nếu exception được bọc khác theo version/client, kiểm tra cause chain và broker log; không làm assertion quá mong manh bằng cách so khớp toàn bộ message.

Test tương ứng cho consumer cần xác minh cả quyền Read trên topic và Read trên group. Một consumer không thể subscribe thành công chỉ vì có quyền topic nếu group authorization bị thiếu.

### 10.3. Test TLS/SASL ở cấp ứng dụng

Nên tách test theo mục tiêu:

- Test cấu hình đúng: producer gửi, consumer nhận record qua listener bảo mật.
- Test sai credentials: client không authenticate và không được fallback.
- Test truststore sai: client không hoàn tất TLS handshake.
- Test hostname sai: endpoint verification từ chối certificate.
- Test ACL sai: TLS/SASL vẫn thành công nhưng thao tác topic/group bị deny.

Không cần cố bắt đúng một exception duy nhất cho mọi TLS provider hoặc client version. Assert rằng request thất bại ở đúng lớp, đồng thời xác minh evidence ở log/metric.

### 10.4. Chạy integration test trong pipeline

Pipeline có thể dùng Kafka test cluster riêng, container hoặc ephemeral environment. Nếu cần kiểm tra ACL/TLS thật, môi trường test phải bật đúng listener, authorizer và credentials; broker mặc định không bảo mật sẽ không kiểm tra được các negative cases.

Gợi ý các stage:

1. Static validation: parse YAML/properties, phát hiện secret literal, kiểm tra required properties.
2. Broker startup: node khởi động, controller quorum và listener health.
3. TLS handshake: CA đúng/sai, SAN đúng/sai, mTLS nếu bật.
4. SASL authentication: credential đúng/sai, mechanism đúng/sai.
5. ACL authorization: allow/deny trên topic, group, transaction ID.
6. Application integration: Spring producer/consumer, retry và exception handling.
7. Cleanup: xóa test topic, test ACL, user/credential và secret tạm.

Không chạy test negative đồng thời trên cùng một principal/resource nếu các test có thể thay ACL hoặc rotate credential; điều đó tạo race và làm kết quả không xác định.

## 11. Log, metric và bằng chứng kiểm thử

Một test case nên lưu evidence đủ để truy vết nhưng không chứa secret:

- Timestamp, environment và Kafka version.
- Broker/listener/hostname đã kết nối.
- Principal sau authentication hoặc principal mapping.
- Resource type, resource name, pattern type và operation.
- Kết quả expected/actual, exception class và root cause.
- Broker authorization log hoặc authentication log tương ứng.
- ACL snapshot và config diff đã redact.
- Thời gian phát hiện và thời gian khôi phục.

Các tín hiệu cần theo dõi:

| Nhóm | Tín hiệu |
|---|---|
| TLS | Handshake failure, certificate expiry, protocol/cipher mismatch |
| SASL | Authentication failure theo listener/mechanism |
| ACL | Authorization denied theo principal/resource/operation |
| Broker | Listener startup error, connection count, request error rate |
| KRaft | Controller quorum health, metadata propagation |
| Application | Produce/consume failure, retry count, startup failure |
| Secrets | Certificate expiry, rotation age, failed secret retrieval |

Tên metric và logger thay đổi theo Kafka version và hệ thống monitoring. Xác định metric/log thực tế từ release đang dùng; không tạo alert dựa trên một tên metric chưa được xác minh.

## 12. Troubleshooting theo thứ tự

Khi client thất bại, đi từ lớp thấp tới cao:

1. **Network:** DNS, route, firewall, port và advertised endpoint.
2. **Listener:** đúng protocol map, listener bind và endpoint được công bố.
3. **TLS:** CA chain, SAN, expiry, client certificate, TLS version.
4. **SASL:** mechanism, username, password/credential provisioning và JAAS.
5. **Principal mapping:** xác minh client thực sự trở thành principal nào.
6. **ACL:** resource pattern, operation, group ID, transactional ID và deny ACL.
7. **Application:** timeout/retry, error handling, serializer và business flow.

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra đầu tiên |
|---|---|---|
| Connection refused | Port/listener/firewall | listeners, service và network |
| Bootstrap được nhưng request timeout | Advertised hostname/port không tới được | Metadata và advertised.listeners |
| SSL handshake failure | Truststore, SAN, expiry, protocol | OpenSSL và client TLS logs |
| SASL authentication failed | Secret/mechanism/JAAS | Listener SASL config và credential |
| Topic authorization failed | Thiếu topic operation hoặc sai principal | ACL list và broker authorization log |
| Group authorization failed | Thiếu Group Read hoặc group ID không khớp | ACL trên group resource |
| Transactional ID authorization failed | Thiếu quyền transactional ID | Transactional ID pattern/Write |
| Chỉ một broker bị lỗi TLS | Cert hoặc advertised hostname khác biệt | Certificate SAN của từng broker |
| Sau rotation client vẫn lỗi | Truststore/keystore cache hoặc secret rollout chưa đồng nhất | Restart/refresh theo quy trình và cert chain |
| Broker không khởi động sau đổi config | Property sai, listener map hoặc authorizer không tương thích | Startup log và config diff |

Không khắc phục authorization bằng cách thêm User wildcard hoặc Operation All cho ứng dụng. Không khắc phục TLS bằng cách tắt hostname verification. Những cách này che lỗi thay vì sửa nguyên nhân.

## 13. Runbook kiểm thử an toàn và rollback

Trước test:

- Xác định owner, cửa sổ test, cluster lab và người có quyền rollback.
- Sao lưu broker config, ACL snapshot và certificate inventory.
- Tạo principal/topic/group/transactional ID riêng cho test.
- Xác nhận không dùng superuser trong test ứng dụng.
- Định nghĩa expected failure và điều kiện dừng test.

Sau test:

1. Khôi phục config đã thay đổi và xác minh broker/controller health.
2. Xác nhận listener bảo mật hoạt động trên từng broker.
3. Chạy lại positive TLS/SASL test.
4. Chạy lại ACL allow/deny smoke test.
5. Thu hồi ACL, user và certificate tạm theo phạm vi đã tạo.
6. Xóa test topic nếu policy cho phép; không xóa topic dùng chung.
7. Xác nhận không còn secret tạm trong file, log hoặc pipeline artifact.
8. Ghi kết quả, lỗi còn tồn tại, người chịu trách nhiệm và thời hạn xử lý.

Rollback không chỉ là copy file cấu hình cũ. Nếu test đã rotate certificate, thay credential hoặc ACL thì phải khôi phục cả secret store, truststore/keystore và ACL state tương ứng.

## 14. Bài lab: kiểm thử bảo mật Kafka từ đầu đến cuối

Thực hiện trên một cluster KRaft test độc lập:

1. Bật StandardAuthorizer và deny-by-default.
2. Tạo listener TLS cho client; kiểm tra certificate chain và SAN.
3. Bật SASL/SCRAM trên listener SASL_SSL và tạo principal ứng dụng test.
4. Tạo topic orders và payments; tạo group orders-reader-v1.
5. Cấp ACL Write cho orders-producer trên orders.
6. Cấp ACL Read cho orders-consumer trên orders và group orders-reader-v1.
7. Chạy positive produce/consume test và lưu kết quả.
8. Thử orders-producer ghi payments; xác nhận authorization deny.
9. Thử orders-consumer đọc bằng group khác; xác nhận group authorization deny.
10. Dùng password sai; xác nhận SASL authentication failure.
11. Dùng truststore sai hoặc hostname sai; xác nhận TLS failure.
12. Thử certificate client không được CA tin cậy nếu lab bật mTLS.
13. Thử một cấu hình advertised hostname sai trong môi trường cô lập; quan sát bootstrap/metadata behavior rồi rollback.
14. Khôi phục cấu hình đúng, chạy smoke test và thu hồi tài nguyên test.

Bảng ghi nhận:

| Case | Principal | Lớp kiểm tra | Expected | Actual | Evidence |
|---|---|---|---|---|---|
| TLS-01 | orders-producer | TLS hợp lệ | Allow handshake | | |
| TLS-02 | orders-producer | CA không tin cậy | Deny handshake | | |
| TLS-03 | orders-producer | SAN sai | Deny hostname verification | | |
| SASL-01 | orders-producer | Credentials đúng | Authenticated | | |
| SASL-02 | orders-producer | Password sai | Authentication denied | | |
| ACL-01 | orders-producer | Write orders | Allow | | |
| ACL-02 | orders-producer | Write payments | Deny | | |
| ACL-03 | orders-consumer | Read orders, đúng group | Allow | | |
| ACL-04 | orders-consumer | Read orders, group khác | Deny | | |
| CFG-01 | test client | Advertised hostname sai | Connection/metadata failure | | |
| CFG-02 | test broker | Listener map sai | Startup/connection failure | | |

## 15. Checklist hoàn tất

- [ ] Đã phân biệt network, TLS, SASL, ACL và application behavior.
- [ ] KRaft StandardAuthorizer được cấu hình đúng theo topology.
- [ ] Default authorization policy là deny-by-default theo yêu cầu.
- [ ] Ứng dụng không dùng superuser hoặc principal wildcard.
- [ ] TLS chain, SAN, expiry, hostname verification và mTLS được kiểm thử.
- [ ] SASL mechanism và credential đúng/sai đều có test.
- [ ] ACL allow/deny được kiểm thử cho topic, group và transactional ID.
- [ ] Literal/prefixed pattern và deny precedence được kiểm tra.
- [ ] Listener, advertised.listeners, controller và inter-broker security được rà soát.
- [ ] Cấu hình sai được fault-inject trong lab và rollback thành công.
- [ ] Spring Kafka integration test xác minh cả success và expected failure.
- [ ] Log/metric evidence không chứa password, JAAS secret hoặc private key.
- [ ] Có quy trình certificate/credential rotation và rollback.
- [ ] Có smoke test sau thay đổi và định kỳ kiểm tra quyền.

Một hệ thống Kafka an toàn không chỉ cần bật TLS hoặc tạo vài ACL. Cần chứng minh đường truyền tin cậy, principal được xác thực chính xác, quyền được giới hạn theo resource và operation, cấu hình sai bị phát hiện đúng lớp, và mọi thay đổi đều có rollback. Positive test chứng minh luồng hợp lệ vẫn chạy; negative test chứng minh người dùng hoặc cấu hình không hợp lệ thực sự bị chặn. Cả hai cùng cần thiết để tránh bảo mật hình thức và giảm nguy cơ sự cố khi thay đổi broker, certificate, credentials hoặc ACL.


