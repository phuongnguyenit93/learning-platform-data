# Authentication failure

Trong **Spring Kafka Reliability Operations**, **Authentication failure** là lỗi xảy ra khi Kafka client không chứng minh được danh tính với broker hoặc một thành phần xác thực trung gian. Lỗi có thể khiến producer không gửi được records, consumer không fetch được dữ liệu, AdminClient không truy vấn được cluster hoặc listener container không thể duy trì hoạt động bình thường.

Cần phân biệt **authentication** và **authorization**:

- **Authentication (AuthN)** trả lời: client là ai, và thông tin xác thực có hợp lệ không?
- **Authorization (AuthZ)** trả lời: principal đã xác thực có được phép thực hiện thao tác này trên topic, group, cluster hoặc transactional ID không?

Một username/password sai, token hết hạn, certificate không được tin cậy hoặc Kerberos ticket không hợp lệ là vấn đề xác thực. Một principal đăng nhập thành công nhưng thiếu quyền READ trên topic hoặc quyền WRITE trên topic là vấn đề authorization. Hai lỗi có thể cùng làm consumer/producer thất bại, nhưng cách sửa khác nhau.

Trong phần **Health và readiness**, mục tiêu không chỉ là phát hiện exception. Ứng dụng cần biểu diễn đúng trạng thái phụ thuộc Kafka, tránh báo healthy khi không thể thực hiện công việc bắt buộc, đồng thời tránh restart loop khi broker hoặc credential provider đang gặp sự cố.

Quy trình vận hành nên là: **phân loại lỗi → xác định principal và cơ chế bảo mật → kiểm tra client/broker configuration → sửa credentials hoặc quyền → khôi phục client an toàn → xác nhận đúng thao tác Kafka → cập nhật readiness**.

## 1. Authentication failure xuất hiện ở đâu?

Spring Kafka sử dụng Kafka clients bên dưới. Một ứng dụng có thể khởi tạo nhiều loại client với mục đích khác nhau:

- **KafkaConsumer**: subscribe, join group, poll và fetch records.
- **KafkaProducer**: gửi records, có thể tham gia transaction.
- **KafkaTemplate**: abstraction của Spring Kafka trên producer.
- **KafkaAdmin/AdminClient**: mô tả cluster, kiểm tra topic và thực hiện administrative operations.
- **Transactional producer**: cần thêm quyền với transactional ID.
- **Consumer group coordinator**: kiểm tra quyền tham gia và sử dụng group.

Mỗi client có thể dùng cùng hoặc khác security configuration. Nếu producer và consumer sử dụng principal khác nhau, việc một client hoạt động không chứng minh client còn lại được xác thực đúng.

Ví dụ:

~~~text
order-service
  |
  +-- KafkaConsumer
  |     principal = User:orders-reader
  |     group = orders-service
  |     topic = orders.events
  |
  +-- KafkaProducer
  |     principal = User:orders-writer
  |     topic = orders.projected
  |
  +-- KafkaAdmin
        principal = User:orders-admin-check
~~~

Trong thực tế, không nhất thiết phải tạo ba principal. Sơ đồ nhấn mạnh rằng cần xác định **client nào phát sinh lỗi** và credentials/ACL nào đang áp dụng cho client đó.

## 2. Authentication và authorization khác nhau thế nào?

| Thuộc tính | Authentication | Authorization |
|---|---|---|
| Câu hỏi | Client là ai? | Client được phép làm gì? |
| Kiểm tra | Password, token, certificate, Kerberos ticket | ACL, role, policy, resource permission |
| Thời điểm | Thường khi thiết lập hoặc xác thực connection/session | Khi client gọi operation trên resource |
| Ví dụ lỗi | SASL authentication failed | Topic authorization failed |
| Hướng xử lý | Sửa identity, secret, mechanism, trust | Cấp đúng quyền cho principal |
| Tác động | Client không xác thực được với broker | Có thể kết nối được nhưng operation bị từ chối |

Một consumer có thể hoàn tất SASL handshake nhưng vẫn không đọc được topic vì thiếu quyền READ. Tương tự, producer có thể xác thực thành công nhưng không được WRITE vào topic.

Không đổi password khi nguyên nhân thực sự là ACL. Cũng không cấp quyền rộng như superuser chỉ để che lỗi authentication.

## 3. Các loại lỗi thường gặp

| Nhóm lỗi | Dấu hiệu | Điều cần kiểm tra |
|---|---|---|
| SASL username/password | Authentication failed | Username, password, mechanism, JAAS |
| SASL mechanism mismatch | Broker/client không thống nhất mechanism | SCRAM-SHA-256/512, PLAIN, GSSAPI, OAUTHBEARER |
| OAuth token | Token expired/invalid/audience mismatch | Issuer, audience, scope, callback handler, clock |
| TLS trust | PKIX path building hoặc certificate unknown | Truststore, CA chain, hostname |
| TLS client certificate | Bad certificate/handshake failure | Keystore, cert validity, client-auth policy |
| Kerberos | Login/GSS initiate failure | Principal, keytab, SPN, clock skew, DNS |
| Topic authorization | TopicAuthorizationException | READ/WRITE/DESCRIBE ACL |
| Group authorization | GroupAuthorizationException | GROUP resource ACL |
| Transaction authorization | Transactional ID authorization failure | WRITE/DESCRIBE trên transactional ID |
| Cluster authorization | Cluster operation bị từ chối | Cluster ACL/admin role |
| Network/connectivity | Timeout, disconnect, DNS failure | Broker endpoint, firewall, routing |

**Timeout không tự động là authentication failure.** Network không tới được broker, DNS lỗi hoặc broker không sẵn sàng có thể khiến client không hoàn tất handshake mà không phải do credentials sai.

## 4. Những exception cần nhận diện

Kafka client có các exception liên quan tới authentication và authorization. Các loại thường gặp gồm:

- **AuthenticationException**: lớp lỗi xác thực chung trong Kafka client.
- **SaslAuthenticationException**: SASL authentication thất bại.
- **TopicAuthorizationException**: thiếu quyền trên topic.
- **GroupAuthorizationException**: thiếu quyền trên consumer group.
- **ClusterAuthorizationException**: thiếu quyền trên cluster-level operation.
- **TransactionalIdAuthorizationException**: thiếu quyền với transactional ID.
- **SSLHandshakeException** hoặc lỗi SSL tương ứng: TLS handshake thất bại, cần kiểm tra certificate/trust.
- **TimeoutException**: operation quá thời gian; cần điều tra network/broker và không mặc định coi là credential failure.

Tên class và cách exception được bọc có thể phụ thuộc Kafka client version và call path. Hãy đọc root cause và broker/client logs thay vì chỉ phân loại theo exception ngoài cùng.

Một lỗi ở KafkaAdmin có thể xuất hiện trong startup hoặc health check, còn lỗi ở consumer có thể được phát hiện trong poll/fetch. Producer có thể trả lỗi qua send future. Không phải mọi authentication exception đều đi qua listener method.

## 5. SASL và TLS làm hai việc khác nhau

Kafka có thể dùng TLS để bảo vệ kênh truyền và xác thực certificate; SASL để xác thực principal theo cơ chế được cấu hình.

Một số security protocols:

| Protocol | Ý nghĩa |
|---|---|
| PLAINTEXT | Không TLS/SASL |
| SSL | TLS; có thể dùng client certificate authentication nếu broker cấu hình |
| SASL_PLAINTEXT | SASL authentication trên kết nối không TLS |
| SASL_SSL | SASL authentication bên trong TLS connection |

Trong production, **SASL_SSL** thường được chọn khi dùng SASL mechanism và muốn mã hóa kênh truyền. Nếu dùng mutual TLS, client certificate cũng tham gia xác thực ở tầng TLS.

Không nhầm:
- Truststore thường chứa CA/certificate chain mà client tin cậy để xác minh broker.
- Keystore chứa client certificate và private key khi client cần trình certificate.
- SASL credentials là username/password, token hoặc thông tin đăng nhập theo mechanism.
- ACL là quyền của principal sau khi broker xác định danh tính.

Một client có thể dùng TLS thành công nhưng SASL thất bại; hoặc SASL credentials đúng nhưng TLS trust chain không hợp lệ.

## 6. Cấu hình SASL_SSL với SCRAM

Ví dụ Spring Boot cấu hình dùng SCRAM-SHA-512:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.example.internal:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="INJECTED_USERNAME" password="INJECTED_SECRET";
~~~

Các giá trị INJECTED_USERNAME và INJECTED_SECRET là placeholder minh họa; cung cấp credentials thật qua secret management phù hợp. Không commit password vào source control hoặc đưa vào log.

Nếu producer, consumer và admin dùng principal khác nhau, cấu hình chung dưới spring.kafka.properties có thể không phù hợp. Spring Boot hỗ trợ cấu hình client-specific properties cho producer, consumer và admin; đặt credentials đúng scope để tránh vô tình dùng principal sai.

Ví dụ định hướng:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: INJECTED_CONSUMER_JAAS_CONFIG
    producer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: INJECTED_PRODUCER_JAAS_CONFIG
~~~

Cần xác minh property binding theo Spring Boot version và cách ứng dụng tạo KafkaAdmin/KafkaTemplate/ConsumerFactory tùy chỉnh.

## 7. SASL mechanism mismatch

Client và broker phải thống nhất mechanism được cấu hình. Các mechanism phổ biến:

- **PLAIN**: username/password; chỉ dùng trên kết nối TLS trong production trừ khi có security exception được phê duyệt.
- **SCRAM-SHA-256 / SCRAM-SHA-512**: challenge-response dựa trên secret đã đăng ký ở broker.
- **OAUTHBEARER**: token-based authentication.
- **GSSAPI**: Kerberos.
- Các mechanism khác tùy Kafka distribution và broker configuration.

Một số ví dụ mismatch:

- Client khai báo SCRAM-SHA-512 nhưng broker listener chỉ bật SCRAM-SHA-256.
- Client dùng GSSAPI trong khi listener không hỗ trợ Kerberos.
- Client cấu hình SASL mechanism nhưng security.protocol lại là SSL.
- Client kết nối nhầm listener/port với security protocol khác.
- Broker principal được provision cho mechanism khác với client.

Hãy kiểm tra đúng **bootstrap endpoint và listener**. Một Kafka cluster có thể mở nhiều listeners, mỗi listener có protocol, authentication và mapping principal khác nhau.

## 8. SCRAM username/password và JAAS

Khi dùng SCRAM, Kafka client cần login module phù hợp cùng username/password. Các lỗi thường gặp:

- Secret được mount sai key hoặc sai file path.
- Username bị thừa whitespace/newline.
- Password bị escape sai trong YAML/JAAS.
- Secret rotation chỉ cập nhật Kubernetes Secret nhưng client hiện hữu vẫn dùng credential cũ.
- Client kết nối nhầm broker listener.
- Principal chưa được provision SCRAM credential trên cluster.
- Client và broker không thống nhất SCRAM mechanism.

Không log nội dung JAAS config vì nó có thể chứa password. Khi cần debug, log **mechanism, secret version/reference, source type và principal đã được phê duyệt**, không log secret value.

Nếu dùng nhiều clients, xác minh từng factory nhận đúng JAAS config. Một ConsumerFactory đúng không đảm bảo KafkaAdmin hoặc producer cũng dùng đúng.

## 9. OAUTHBEARER và token expiry

Với OAUTHBEARER, client thường cần callback/login handler để lấy token. Lỗi có thể đến từ:

- Token đã hết hạn.
- Issuer không đúng.
- Audience không khớp broker.
- Scope/claims không đủ.
- Clock skew giữa client, identity provider và broker.
- TLS không tin cậy identity provider.
- Callback handler không tải được secret/client credentials.
- Token refresh thất bại hoặc token cache giữ giá trị cũ.

Không đưa access token, refresh token hoặc client secret vào span, log hay exception message. Chỉ ghi error category như oauth_token_expired hoặc oauth_issuer_mismatch nếu được allowlist.

Đối với token rotation, cần kiểm tra callback handler có thực sự lấy token mới và Kafka client có cơ chế re-authentication phù hợp phiên bản hay không. Không giả định thay biến môi trường là token trong một Kafka connection đang mở tự đổi.

## 10. Kerberos/GSSAPI

Nếu dùng Kerberos, các thành phần cần khớp:

- Principal của client.
- Keytab và file permissions.
- Service principal name của Kafka broker.
- DNS và hostname resolution.
- Realm và krb5 configuration.
- Clock synchronization.
- Ticket lifetime và renewal policy.
- SASL mechanism GSSAPI.

Ví dụ property phía client:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=GSSAPI
sasl.kerberos.service.name=kafka
sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required useKeyTab=true storeKey=true keyTab="/secure/path/client.keytab" principal="orders-client@EXAMPLE.COM";
~~~

Đường dẫn và principal là dữ liệu giả. Không in keytab, JAAS secret hoặc ticket cache vào logs. Nếu login ban đầu thành công nhưng ticket không được renew, sự cố có thể chỉ xuất hiện sau khi service chạy một thời gian.

## 11. TLS truststore và certificate failure

TLS failure có thể bị hiểu nhầm là authentication failure vì cả hai đều làm kết nối Kafka thất bại.

Các dấu hiệu:
- PKIX path building failed.
- Certificate expired hoặc not yet valid.
- Hostname verification failure.
- Unknown CA.
- Bad certificate khi broker yêu cầu client certificate.
- TLS protocol/cipher mismatch.

Truststore dùng để xác minh certificate chain của broker. Keystore được dùng khi client cần trình certificate của chính nó, ví dụ mutual TLS.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      ssl.truststore.location: /secure/path/kafka.truststore
      ssl.truststore.password: INJECTED_TRUSTSTORE_SECRET
      ssl.keystore.location: /secure/path/client.keystore
      ssl.keystore.password: INJECTED_KEYSTORE_SECRET
      ssl.key.password: INJECTED_PRIVATE_KEY_SECRET
~~~

Nếu chỉ cần xác minh broker bằng truststore, client có thể không cần keystore. Không cấu hình client certificate khi broker không yêu cầu nếu policy không cần.

Không tắt hostname verification hoặc chuyển sang trust-all để “fix nhanh”. Điều đó làm suy yếu bảo vệ kết nối và có thể che lỗi certificate provisioning.

## 12. Authentication khác authorization trong ACL

Sau khi broker xác thực principal, broker áp dụng ACL/authorizer cho từng operation.

Ví dụ quyền cần cân nhắc:

| Client role | Resource | Operation thường cần |
|---|---|---|
| Consumer | Topic | READ, DESCRIBE |
| Consumer | Group | READ |
| Producer | Topic | WRITE, có thể DESCRIBE tùy operation |
| Transactional producer | Transactional ID | WRITE, DESCRIBE theo yêu cầu |
| Admin/health checker | Cluster/topic | Các quyền describe/admin cụ thể |

Quyền thực tế phụ thuộc operation, broker authorizer, Kafka version và security policy. Không cấp quyền rộng hơn chỉ để health check thành công.

Một consumer có thể authenticate thành công nhưng fetch topic bị TopicAuthorizationException. Một health check gọi describe cluster có thể thất bại do thiếu cluster DESCRIBE dù consumer vẫn đọc topic bình thường. Vì vậy health check phải kiểm tra **đúng capability cần thiết**.

## 13. Producer và consumer có thể có principal khác nhau

Trong một service, tách principal có thể giảm blast radius:

~~~text
orders-reader:
  READ orders.events
  READ group orders-service

orders-writer:
  WRITE orders.projected

orders-admin-observer:
  DESCRIBE một số resources cần thiết
~~~

Nếu producer và consumer dùng chung principal, cần cấp đúng quyền tối thiểu cho tất cả operations. Nếu tách principal, cấu hình credentials theo từng client factory và kiểm tra secret rotation cho từng identity.

Đừng suy ra “Kafka đã kết nối” từ một client duy nhất. Producer send thành công không chứng minh consumer được phép join group; consumer poll thành công không chứng minh producer có WRITE ACL.

## 14. Authentication failure ở startup và runtime

Lỗi có thể xảy ra ở nhiều thời điểm:

| Thời điểm | Ví dụ | Hành động |
|---|---|---|
| Application startup | KafkaAdmin không xác thực được | Kiểm tra admin client config và startup policy |
| Consumer start | SASL/TLS handshake thất bại | Kiểm tra consumer principal và listener |
| Consumer poll/fetch | Token hết hạn hoặc ACL bị revoke | Kiểm tra runtime auth/reauth và permissions |
| Producer send | Producer credentials sai hoặc WRITE ACL thiếu | Kiểm tra producer identity và topic ACL |
| Transaction begin/commit | Transactional ID ACL hoặc producer fencing | Kiểm tra transaction identity và ownership |
| Health check | Probe client không có quyền cần thiết | Kiểm tra health check principal/operation |
| Credential rotation | Client cũ dùng secret cũ | Recreate/refresh client theo cơ chế hỗ trợ |

Một lỗi xuất hiện lúc startup không giống lỗi sau vài giờ chạy. Runtime failure có thể chỉ xảy ra khi token/certificate hết hạn hoặc connection cần re-authenticate.

## 15. Spring Kafka listener container và lỗi authentication

Listener container gọi KafkaConsumer ở background. Lỗi authentication có thể được ném từ các thao tác client như poll hoặc fetch; consumer thread có thể log error, dừng hoặc không phục hồi theo cách application mong muốn tùy Kafka client/Spring Kafka version và loại exception.

Không giả định **CommonErrorHandler** có thể retry mọi authentication failure. Error handler chủ yếu xử lý exception từ quá trình listener record processing; lỗi xác thực ở Kafka client protocol/connection xảy ra ngoài business listener và không phải record failure thông thường.

Khi gặp lỗi:

1. Đọc root cause và broker log.
2. Xác định container còn running hay đã stopped.
3. Kiểm tra có tiếp tục poll/assignment hay không.
4. Xem exception có lặp lại theo mỗi reconnect không.
5. Kiểm tra credentials/mechanism và broker listener.
6. Sửa secret/ACL/trust chain.
7. Recreate hoặc restart đúng client/container nếu cần.
8. Xác minh consumer nhận được records và offset tiến.

Không nuốt authentication exception trong listener rồi return thành công. Không commit offsets để bỏ qua vấn đề credentials.

## 16. KafkaTemplate và producer send failure

KafkaTemplate gửi message bất đồng bộ. Authentication/authorization errors có thể xuất hiện qua send future hoặc producer client logs.

Ví dụ xử lý lỗi không log payload:

~~~java
kafkaTemplate.send("orders.created", event)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error(
                "Kafka publish failed: topic={}, errorType={}",
                "orders.created",
                error.getClass().getSimpleName()
            );
            publishHealthState.recordFailure(
                classifyKafkaFailure(error)
            );
        } else {
            publishHealthState.recordSuccess();
        }
    });
~~~

publishHealthState và classifyKafkaFailure là domain helpers minh họa. Không log event.toString(), raw key hoặc exception message chưa kiểm soát.

Nếu dùng transactional KafkaTemplate, send future thành công chưa đồng nghĩa transaction đã commit. Health state của transactional producer cần được cập nhật theo kết quả transaction lifecycle phù hợp, không chỉ theo send acknowledgement.

## 17. KafkaAdmin/AdminClient có thể có quyền khác

Spring Kafka có thể dùng KafkaAdmin để tạo/kiểm tra topic hoặc thực hiện administrative operations. AdminClient có thể được cấu hình bằng credentials khác hoặc dùng chung properties.

Một health check dựa trên AdminClient có thể thất bại vì:
- Admin principal sai credentials.
- Principal không có quyền DESCRIBE cluster.
- Broker không hỗ trợ listener/protocol được cấu hình.
- Timeout/network issue.
- Cluster đang unavailable.

Điều này **không luôn chứng minh consumer principal cũng không thể fetch**. Nếu health indicator gọi describeCluster, nó kiểm tra khả năng describe cluster của principal đó, không tự chứng minh WRITE/READ trên mọi topic.

Định nghĩa health contract theo vai trò ứng dụng và principal thực tế. Không thêm quyền cluster-admin vào consumer chỉ để một dashboard báo UP.

## 18. Kiểm tra credentials mà không làm lộ secret

Một quy trình debug tốt kiểm tra:

- Secret reference/version.
- File mount path và file permissions.
- Environment variable **có tồn tại** hay không, không in value.
- Username/principal đã được duyệt.
- SASL mechanism và security.protocol.
- Broker listener endpoint/port.
- Certificate subject/issuer/expiry, không in private key.
- Token expiry/audience/issuer metadata đã được phép ghi.
- JAAS module class và cấu trúc config.
- ACL của principal qua admin process được cấp quyền.

Không dùng log statement như:

~~~java
log.info("Kafka JAAS config: {}", jaasConfig);
log.info("Kafka password: {}", password);
log.info("OAuth token: {}", token);
~~~

Khi cần chứng minh hai secret có giống nhau hay không, dùng secret manager/version metadata hoặc công cụ kiểm tra được phê duyệt, không in password ra terminal/log.

## 19. Secret injection trong Spring Boot

Một ứng dụng có thể nhận credentials qua environment variables, mounted secret files, config tree hoặc secret manager. Cần đảm bảo:

- Placeholder được resolve đúng ở startup.
- Không commit secret trong application.yml.
- Không in effective configuration chứa password.
- Không đưa secret vào Actuator env/configprops endpoints.
- Secret files chỉ có quyền đọc tối thiểu.
- Rotation có owner và rollout procedure.
- Mỗi Kafka client nhận đúng credential scope.

Nếu dùng Spring Boot configuration import/config tree, kiểm tra đường dẫn và tên property thực tế. Không giả định file mount mới tự cập nhật một bean hoặc Kafka client đã khởi tạo.

## 20. Credential rotation: vì sao cần kế hoạch?

Credential rotation có thể tạo khoảng thời gian mà một số instances dùng secret cũ và số khác dùng secret mới. Nếu broker chỉ chấp nhận một credential ở một thời điểm, rollout không phối hợp có thể gây outage.

Một kế hoạch rotation thường gồm:

1. Provision credential mới hoặc certificate mới.
2. Đảm bảo broker/identity provider chấp nhận credential mới.
3. Cập nhật secret store và version reference.
4. Rollout hoặc refresh Kafka clients theo cơ chế hỗ trợ.
5. Xác minh producer, consumer và admin operations.
6. Theo dõi authentication failure và reconnect rates.
7. Sau khi toàn bộ clients dùng credential mới, thu hồi credential cũ.
8. Xác minh không còn instance hoặc batch job dùng credential cũ.

Nếu broker/identity provider hỗ trợ overlap credentials, tận dụng khoảng overlap để rollout không gián đoạn. Nếu không, cần một maintenance window hoặc cơ chế cutover có kiểm soát.

## 21. Secret update không tự refresh mọi Kafka client

Thay đổi environment variable của Pod thường cần tạo Pod mới. Một mounted secret file có thể được cập nhật bởi Kubernetes, nhưng Kafka client đã tạo không nhất thiết tự đọc lại file hay đổi credentials trên connection hiện tại.

Tùy mechanism:
- OAuth callback handler có thể lấy token mới theo cơ chế refresh.
- Kerberos login module có thể renew ticket theo cấu hình.
- SCRAM credentials thường được dùng khi client xác thực connection; reconnect/recreate có thể cần thiết để dùng secret mới.
- TLS certificates có thể được đọc khi tạo SSL context; rotation cần xác định cách context/connection được tái tạo.

Không giả định **Spring Cloud refresh** tự thay mọi properties trong ConsumerFactory/ProducerFactory và các Kafka clients đang chạy. Phải kiểm tra lifecycle của client, callback handler và phiên bản framework.

Một rollout an toàn thường tạo clients mới bằng secret mới, xác minh hoạt động rồi mới loại bỏ clients cũ.

## 22. Phục hồi client sau khi sửa credentials

Khi credential sai đã được sửa, không nên chỉ xóa alert. Xác minh:

1. Secret version mới đã đến đúng instance.
2. Kafka client mới dùng config đó.
3. TLS/SASL handshake thành công.
4. Producer có thể thực hiện send operation cần thiết.
5. Consumer có thể join group và fetch topic được phép.
6. Transactional producer có thể initialize/commit nếu service dùng transaction.
7. ACL vẫn đúng với principal mới.
8. Consumer lag bắt đầu giảm và listener success rate tăng.
9. Không còn auth exception lặp theo reconnect.
10. Readiness chỉ trở lại UP khi capability bắt buộc đã hoạt động.

Nếu client hiện hữu không thể refresh credentials, recreate đúng factory/container theo lifecycle an toàn. Tránh restart tất cả services khi chỉ một principal bị ảnh hưởng.

## 23. Readiness và liveness phải tách biệt

Trong Kubernetes/Spring Boot Actuator, **readiness** và **liveness** có ý nghĩa khác:

- **Readiness**: instance có nên nhận thêm traffic/công việc theo contract ứng dụng không?
- **Liveness**: process có còn sống và có khả năng tiếp tục hoạt động không?

Nếu Kafka là dependency bắt buộc cho service xử lý order, authentication failure kéo dài có thể khiến service **not ready**. Nhưng nó không tự động chứng minh JVM cần restart.

Không dùng authentication failure của broker làm liveness failure ngay lập tức. Nếu credentials sai do secret deployment, restart liên tục cùng một config không sửa được vấn đề và tạo crash loop.

Với consumer worker không nhận HTTP traffic, readiness có thể được dùng cho deployment orchestration/availability; cần định nghĩa rõ nó có nghĩa “đã kết nối và có thể xử lý workload” hay chỉ “process đã start”.

## 24. Spring Boot Actuator readiness probes

Spring Boot Actuator có thể bật Kubernetes probe endpoints trong các phiên bản hỗ trợ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Các endpoint readiness/liveness thường được cung cấp dưới health probe paths của Actuator. Cấu hình chính xác phụ thuộc Spring Boot version và management server setup.

Một readiness group có thể include các health contributors cần thiết, ví dụ readiness state và một Kafka capability indicator nếu ứng dụng đã cấu hình:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,kafkaAccess
~~~

Tên contributor kafkaAccess chỉ dùng nếu ứng dụng thực sự có indicator đó. Đừng thêm một contributor chỉ để nó xuất hiện trên dashboard; kiểm tra indicator đang thực hiện operation nào và principal nào được sử dụng.

**Liveness nên tập trung vào trạng thái process/application**, không nên phụ thuộc trực tiếp vào Kafka nếu broker outage không có nghĩa JVM đã chết.

## 25. Kafka health indicator không chứng minh mọi quyền

Một Kafka health indicator có thể thực hiện một operation quản trị hoặc mô tả cluster. Nếu operation đó thành công, nó chứng minh client dùng cho health check có thể thực hiện operation đó.

Nó không tự chứng minh:
- Consumer có READ ACL trên mọi topic.
- Consumer có quyền READ trên group cụ thể.
- Producer có WRITE ACL trên output topic.
- Transactional producer có quyền với transactional ID.
- Consumer listener đang xử lý records thành công.
- Offset commit đang tiến.
- Downstream database/API đang healthy.

Ngược lại, một health check thất bại vì thiếu cluster DESCRIBE không nhất thiết có nghĩa listener principal không thể consume.

Hãy đặt tên health detail đúng với capability được kiểm tra, ví dụ kafka-admin-describe thay vì kafka-processing-ready.

## 26. Readiness theo capability của ứng dụng

Một policy tốt nên phản ánh vai trò thực tế:

| Service role | Capability quan trọng |
|---|---|
| Kafka producer API | Có thể publish vào topic bắt buộc |
| Kafka consumer worker | Có thể authenticate, join group và fetch từ topic cần xử lý |
| Kafka Streams app | Có thể đọc input, ghi output và sử dụng internal topics/state stores theo ACL |
| Transactional processor | Có thể đọc input và commit transaction/output/offset |
| Admin utility | Có quyền administrative operations được yêu cầu |
| Optional integration | Có thể degrade mà không làm toàn service unready nếu domain cho phép |

Một check chỉ gọi describeCluster không đủ để chứng minh producer API có WRITE ACL. Một poll rỗng cũng không phải bằng chứng chắc chắn đã fetch thành công từ topic cần xử lý. Readiness phải dựa trên **operation đúng với vai trò**, hoặc trạng thái runtime được cập nhật từ operation thực.

Không tạo message giả vào production topic chỉ để probe nếu không có thiết kế synthetic traffic và cleanup an toàn.

## 27. Ví dụ health state riêng cho Kafka capability

Một ứng dụng có thể lưu trạng thái gần nhất của thao tác Kafka thực tế rồi expose qua HealthIndicator. Ví dụ đơn giản:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
public class KafkaAccessState {

    public record Snapshot(
            boolean available,
            String operation,
            String failureKind) {
    }

    private final AtomicReference<Snapshot> current =
            new AtomicReference<>(
                new Snapshot(false, "not_verified", "unknown")
            );

    public void success(String operation) {
        current.set(new Snapshot(true, operation, "none"));
    }

    public void failure(String operation, String kind) {
        current.set(new Snapshot(false, operation, kind));
    }

    public Snapshot snapshot() {
        return current.get();
    }
}
~~~

Health indicator:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("kafkaAccess")
public class KafkaAccessHealthIndicator implements HealthIndicator {

    private final KafkaAccessState state;

    public KafkaAccessHealthIndicator(KafkaAccessState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        var snapshot = state.snapshot();

        if (snapshot.available()) {
            return Health.up()
                    .withDetail("operation", snapshot.operation())
                    .build();
        }

        return Health.down()
                .withDetail("operation", snapshot.operation())
                .withDetail("failureKind", snapshot.failureKind())
                .build();
    }
}
~~~

Đây là ví dụ state-based health indicator; nó không tự thực hiện Kafka authentication. Producer/consumer integration phải cập nhật state sau **operation thành công/thất bại phù hợp**, và cần quản lý freshness/last-success timestamp.

Không lưu raw exception message hoặc credential trong health details. Nếu dùng nhiều clients, nên có state riêng cho producer, consumer và admin thay vì một boolean chung.

## 28. Không để health check tạo thêm authentication storm

Một probe có thể chạy mỗi vài giây. Nếu mỗi lần nó tạo một AdminClient mới, gọi cluster metadata và đóng client, authentication failure có thể tạo nhiều connections/retries/logs.

Hạn chế:

- Tái sử dụng client/health contributor theo framework.
- Không tạo KafkaAdmin/AdminClient mới ở mỗi health request.
- Không gửi synthetic messages liên tục vào business topic.
- Có timeout ngắn và rõ ràng cho probe.
- Cache kết quả trong khoảng hợp lý khi phù hợp.
- Tách readiness operation khỏi deep diagnostics.
- Không log password/token khi probe thất bại.
- Rate-limit hoặc deduplicate repeated health errors.

Health check phải quan sát hệ thống, không làm tăng tải cho broker đang gặp sự cố.

## 29. Kubernetes readiness behavior khi Kafka auth thất bại

Khi readiness probe thất bại, Kubernetes thường đánh dấu Pod **NotReady** và loại nó khỏi các Service endpoints phù hợp. Nó không tự động restart container chỉ vì readiness fail.

Khi liveness probe thất bại, kubelet có thể restart container sau số lần failure được cấu hình.

Một chiến lược phổ biến:

~~~text
Kafka auth failure
  |
  +--> Readiness: DOWN nếu Kafka là dependency bắt buộc
  |
  +--> Liveness: UP nếu JVM/process vẫn hoạt động
  |
  +--> Alert: credential/authentication incident
  |
  +--> Recovery: sửa secret/ACL và refresh clients
  |
  +--> Readiness: UP sau capability verification
~~~

Nếu một worker không phục vụ HTTP requests, readiness semantics vẫn cần thống nhất với deployment system. Một Pod NotReady có thể ảnh hưởng rollout và autoscaling; không dùng readiness như công cụ che lỗi lâu dài mà không có alert.

## 30. Startup readiness và consumer assignment

Một consumer application có thể start JVM và tạo listener container nhưng chưa có assignment hoặc chưa fetch được topic.

Các giai đoạn:

~~~text
PROCESS_STARTED
  -> CONFIG_LOADED
  -> KAFKA_CLIENT_CREATED
  -> AUTHENTICATION_SUCCEEDED
  -> GROUP_JOINED
  -> PARTITIONS_ASSIGNED
  -> REQUIRED_FETCH_OPERATION_SUCCEEDED
  -> READY
~~~

Đây là state model gợi ý, không phải các trạng thái Spring Kafka enum chuẩn.

Readiness cho consumer quan trọng có thể cần chờ assignment và bằng chứng client thực hiện được operation cần thiết. Tuy nhiên, đừng chờ một record business thật mới đánh dấu ready nếu topic có thể idle dài. Có thể dùng assignment/authenticated operation state cùng SLA, nhưng cần biết operation nào thực sự kiểm tra quyền đọc.

Các Spring Kafka application events như consumer started/stopped và partition assigned/revoked có thể hỗ trợ quan sát lifecycle. Event started một mình không chứng minh fetch permission hay processing success.

## 31. Authorization failure không nên bị sửa bằng restart

Nếu authentication thành công nhưng consumer thiếu READ ACL, restart sẽ tạo lại đúng principal với đúng quyền thiếu. Lỗi sẽ lặp.

Một số thao tác cần quyền riêng:

- READ trên topic.
- READ trên consumer group.
- WRITE trên output topic.
- DESCRIBE trên topic/cluster khi client thực hiện metadata operation.
- Quyền transactional ID cho producer giao dịch.
- Quyền tạo/alter topic cho AdminClient nếu ứng dụng thực hiện việc đó.

Cấp đúng quyền tối thiểu cho principal. Nếu broker authorizer có policy inheritance hoặc prefix ACL, kiểm tra chính sách thực tế trước khi cấp rộng.

Đừng cấp superuser chỉ để health indicator chuyển UP.

## 32. Quy trình điều tra theo lớp

Khi nhận Authentication failure:

**Lớp 1 — Client identity**

1. Xác định client type: consumer, producer, admin hay transactional producer.
2. Xác định principal/username/certificate subject đã được duyệt.
3. Xác định secret reference/version.
4. Kiểm tra đúng Kafka bootstrap endpoint/listener.

**Lớp 2 — Protocol**

5. Kiểm tra security.protocol.
6. Kiểm tra sasl.mechanism.
7. Kiểm tra JAAS module/callback handler.
8. Kiểm tra TLS trust chain/hostname/client certificate.
9. Kiểm tra token/ticket validity và clock skew.

**Lớp 3 — Broker/identity provider**

10. Đối chiếu broker authentication logs.
11. Kiểm tra listener đang hỗ trợ mechanism nào.
12. Kiểm tra principal được provision đúng không.
13. Kiểm tra identity provider/token issuer nếu OAuth.
14. Kiểm tra Kerberos service principal/keytab nếu GSSAPI.

**Lớp 4 — Authorization**

15. Kiểm tra topic/group/cluster/transactional ID ACL.
16. Kiểm tra đúng operation bị từ chối.
17. Phân biệt health-check principal với workload principal.

**Lớp 5 — Application health**

18. Kiểm tra container running/assignment.
19. Kiểm tra producer future/consumer poll errors.
20. Cập nhật readiness theo capability.
21. Xác minh sau sửa và ghi lại root cause.

## 33. Credential rotation không gây outage

Một rollout rotation nên tránh tình huống broker đã thu hồi credential cũ trước khi clients dùng credential mới.

Quy trình khuyến nghị:

1. Tạo credential/certificate/token mới.
2. Provision broker hoặc identity provider để chấp nhận credential mới.
3. Lưu vào secret manager với version rõ.
4. Cập nhật workload config.
5. Xác định Kafka clients có cần restart/recreate hay callback refresh.
6. Rollout từng instance hoặc từng client group.
7. Xác minh producer/consumer/admin operations bằng principal mới.
8. Theo dõi AuthenticationException và reconnects.
9. Chờ toàn fleet không còn dùng credential cũ.
10. Thu hồi credential cũ.
11. Kiểm tra scheduled jobs, batch workers và tools cũng đã được rotate.

Nếu không có overlap credentials, dùng maintenance window hoặc coordinated cutover. Không revoke credential cũ trước khi xác nhận client mới hoạt động.

## 34. Secret update không tự refresh mọi Kafka client

Thay đổi environment variable của Pod thường cần tạo Pod mới. Một mounted secret file có thể được cập nhật bởi Kubernetes, nhưng Kafka client đã tạo không nhất thiết tự đọc lại file hay đổi credentials trên connection hiện tại.

Tùy mechanism:
- OAuth callback handler có thể lấy token mới theo cơ chế refresh.
- Kerberos login module có thể renew ticket theo cấu hình.
- SCRAM credentials thường được dùng khi client xác thực connection; reconnect/recreate có thể cần thiết để dùng secret mới.
- TLS certificates có thể được đọc khi tạo SSL context; rotation cần xác định cách context/connection được tái tạo.

Không giả định **Spring Cloud refresh** tự thay mọi properties trong ConsumerFactory/ProducerFactory và các Kafka clients đang chạy. Phải kiểm tra lifecycle của client, callback handler và phiên bản framework.

Một rollout an toàn thường tạo clients mới bằng secret mới, xác minh hoạt động rồi mới loại bỏ clients cũ.

## 35. Phục hồi client sau khi sửa credentials

Khi credential sai đã được sửa, không nên chỉ xóa alert. Xác minh:

1. Secret version mới đã đến đúng instance.
2. Kafka client mới dùng config đó.
3. TLS/SASL handshake thành công.
4. Producer có thể thực hiện send operation cần thiết.
5. Consumer có thể join group và fetch topic được phép.
6. Transactional producer có thể initialize/commit nếu service dùng transaction.
7. ACL vẫn đúng với principal mới.
8. Consumer lag bắt đầu giảm và listener success rate tăng.
9. Không còn auth exception lặp theo reconnect.
10. Readiness chỉ trở lại UP khi capability bắt buộc đã hoạt động.

Nếu client hiện hữu không thể refresh credentials, recreate đúng factory/container theo lifecycle an toàn. Tránh restart tất cả services khi chỉ một principal bị ảnh hưởng.

## 36. Metrics và logging cho authentication incidents

Metrics hữu ích:

| Metric | Mục đích |
|---|---|
| kafka.auth.failure.count | Số lần auth failure |
| kafka.authorization.failure.count | Số lần authZ bị từ chối |
| kafka.client.reconnect.count | Client reconnect |
| kafka.client.connection.error.count | Connection errors |
| kafka.consumer.assignment.count | Partition assignment |
| kafka.consumer.poll.rate | Poll loop |
| kafka.consumer.lag | Backlog |
| kafka.producer.send.failure | Publish failure |
| kafka.transaction.abort.count | Transaction failures |
| kafka.readiness.state | Trạng thái capability |
| kafka.credential.version | Version/reference đã duyệt, không phải secret |
| kafka.auth.last_success_timestamp | Lần operation thành công gần nhất |

Tên metric là convention gợi ý; một số cần custom instrumentation. Không dùng username, token, raw exception hoặc event ID làm metric tags nếu chúng tạo cardinality hoặc lộ thông tin.

Structured log an toàn:

~~~text
event=kafka_authentication_failure
service=orders-service
instance=orders-pod-2
client_type=consumer
principal=orders-reader
mechanism=SCRAM-SHA-512
security_protocol=SASL_SSL
failure_kind=sasl_authentication
secret_version=kv-2026-11
listener_id=ordersListener
~~~

Principal chỉ ghi khi policy cho phép. Không log JAAS string, password, OAuth token, private key hoặc raw headers.

## 37. Alerting và giảm nhiễu

Authentication failure có thể phát sinh ở mọi reconnect, nên một lỗi credential duy nhất có thể tạo nhiều logs.

Nên:

- Group theo service, instance, client type và principal đã được phê duyệt.
- Deduplicate repeated events trong một incident.
- Phân biệt AuthN với AuthZ và TLS/network.
- Correlate với secret rotation/deployment timeline.
- Cảnh báo khi readiness down liên tục hoặc workload lag vượt SLA.
- Không page cho từng reconnect nếu incident đã được mở.
- Cảnh báo riêng khi credential rotation sắp hết overlap window.
- Có escalation khi ACL thiếu quyền production-critical.
- Không restart loop khi broker/identity provider outage diện rộng.

Một auth failure đơn lẻ trong rollout có thể là transient; nhiều instances thất bại cùng lúc với cùng principal thường cần điều tra secret/config/provisioning chung.

## 38. Integration test cho authentication failure

Không chỉ mock exception. Nên có các test theo từng lớp:

1. **Invalid SASL credentials**: broker từ chối handshake; client không thể thực hiện operation.
2. **Wrong SASL mechanism**: client/broker mismatch tạo lỗi tương ứng.
3. **TLS trust failure**: client không tin certificate chain; kiểm tra phân loại không nhầm với ACL.
4. **Authorization denied**: xác thực thành công nhưng principal thiếu READ/WRITE/Group permission.
5. **Credential rotation**: client cũ và client mới hoạt động theo overlap/rollout policy.
6. **OAuth token expiry**: callback refresh hoặc readiness transition đúng theo cơ chế hỗ trợ.
7. **Consumer recovery**: sau khi sửa credentials và recreate client, consumer join group và fetch được.
8. **Producer recovery**: sau khi sửa, send thành công và transaction commit nếu workload yêu cầu.
9. **Health behavior**: readiness chuyển DOWN khi capability bắt buộc thất bại; liveness không fail chỉ vì broker credential sai.
10. **Health check permission**: indicator không đòi quyền rộng hơn workload.
11. **Secret safety**: logs/spans/health details không chứa password/token.
12. **Retry storm protection**: repeated auth errors được deduplicate và không kích hoạt restart vô hạn.

Với broker test container, authentication/ACL features cần cấu hình tương ứng; không phải image mặc định nào cũng hỗ trợ đầy đủ SCRAM/OAuth/Kerberos. Nếu dùng broker mock, ghi rõ giới hạn vì mock có thể không mô phỏng handshake/ACL thực.

## 39. Kiểm tra readiness trong test

Một test readiness nên xác minh **semantics**, không chỉ HTTP status:

- Khi application start nhưng chưa xác thực được Kafka, readiness không báo UP nếu Kafka là dependency bắt buộc.
- Liveness vẫn UP khi JVM và process khỏe.
- Khi principal được sửa và client thực hiện operation cần thiết, readiness trở lại UP.
- Một lỗi AdminClient DESCRIBE không làm readiness DOWN nếu workload không cần operation đó và policy không yêu cầu.
- Một consumer thiếu topic READ ACL phải không được coi là ready cho workload consume.
- Một producer thiếu WRITE ACL phải không được coi là ready cho workload publish.
- Health response chỉ chứa error category và metadata an toàn.

Nếu service có nhiều chức năng độc lập, có thể cần readiness groups riêng cho từng capability thay vì một Kafka boolean toàn ứng dụng.

## 40. Runbook production khi authentication failure

**Xác định**

1. Xác định service/instance/client type/listener ID.
2. Thu thập exception class và root cause an toàn.
3. Xác định principal, security protocol và mechanism.
4. Xác định broker listener/endpoint và thời điểm bắt đầu.

**Kiểm tra xác thực**

5. Kiểm tra secret reference/version và injection.
6. Kiểm tra JAAS/module/callback configuration.
7. Kiểm tra OAuth issuer/audience/expiry hoặc Kerberos principal/ticket.
8. Kiểm tra TLS certificate chain, expiry, hostname và keystore/truststore.
9. Đối chiếu broker authentication logs.

**Kiểm tra authorization**

10. Xác minh principal được provision đúng.
11. Kiểm tra ACL cho topic/group/cluster/transactional ID.
12. Kiểm tra health-check principal và operation có phù hợp.
13. Không cấp quyền rộng hoặc superuser để chữa tạm.

**Phục hồi**

14. Cập nhật credential/ACL/certificate đúng nơi.
15. Refresh hoặc recreate Kafka clients theo cơ chế hỗ trợ.
16. Restart đúng container/instance nếu cần, tránh toàn fleet.
17. Xác minh producer send hoặc consumer fetch thật sự thành công.
18. Kiểm tra lag, offsets, transactions và duplicate side effects.

**Readiness và đóng incident**

19. Giữ readiness DOWN khi capability bắt buộc chưa hoạt động.
20. Giữ liveness UP nếu process vẫn khỏe.
21. Chờ operation success bằng principal đúng trước khi báo ready.
22. Ghi root cause, secret version và hành động rotation.
23. Xác minh credential cũ đã được thu hồi sau overlap.

## 41. Những lỗi triển khai thường gặp

**Nhầm authentication với authorization.** Đổi password khi thiếu ACL không sửa được lỗi.

**Dùng một health check AdminClient để đại diện mọi client.** Nó không chứng minh consumer/producer có quyền thực hiện operation nghiệp vụ.

**Cấp superuser cho workload.** Làm tăng blast radius và che vấn đề ACL.

**Log JAAS/password/token.** Tạo thêm bản sao secret trong logs.

**Dùng SASL_PLAINTEXT trong mạng không được bảo vệ.** Credentials có thể không được mã hóa trên đường truyền.

**Tắt TLS hostname verification hoặc trust-all.** Che lỗi certificate và làm yếu xác thực broker.

**Cập nhật Kubernetes Secret nhưng không refresh Kafka client.** Client hiện hữu có thể vẫn dùng credential cũ.

**Restart pod theo liveness khi auth fail.** Cùng config sai sẽ tạo crash loop.

**Coi container running là authenticated.** Lifecycle state không chứng minh operation thành công.

**Coi Admin describe thành công là có quyền consume.** READ/Group ACL là riêng.

**Không tách producer/consumer principals khi cần.** Một client lỗi có thể làm mờ client còn lại.

**Retry authentication vô hạn không backoff.** Tạo connection/authentication storm.

**Đóng incident khi handshake thành công.** Workload vẫn có thể thiếu topic/group/transaction permission.

## 42. Checklist trước production

**Identity và protocol**

- [ ] Mỗi Kafka client dùng đúng principal.
- [ ] security.protocol và sasl.mechanism khớp broker listener.
- [ ] JAAS/callback configuration đúng.
- [ ] TLS truststore/keystore được cấu hình theo nhu cầu.
- [ ] OAuth/Kerberos token/ticket refresh có kế hoạch.
- [ ] Secret không xuất hiện trong source/log/span/Actuator.

**Authorization**

- [ ] Consumer có READ/Group permission cần thiết.
- [ ] Producer có WRITE permission trên topic.
- [ ] Transactional producer có quyền transactional ID.
- [ ] Admin/health check chỉ có quyền cần thiết.
- [ ] Không dùng superuser cho workload thông thường.

**Health/readiness**

- [ ] Readiness phản ánh capability Kafka bắt buộc.
- [ ] Liveness không phụ thuộc trực tiếp vào broker outage.
- [ ] Health check dùng đúng principal và operation.
- [ ] Container running không bị coi là bằng chứng authenticated.
- [ ] Readiness phục hồi sau operation thành công thực tế.

**Rotation và recovery**

- [ ] Có secret versioning và overlap/rollout policy.
- [ ] Biết client nào cần recreate sau rotation.
- [ ] Auth failures được deduplicate và backoff.
- [ ] Không restart loop khi broker/identity provider outage.
- [ ] Có runbook ACL, TLS, SASL và OAuth/Kerberos.
- [ ] Sau recovery kiểm tra lag, offsets, transaction và idempotency.

**Testing**

- [ ] Test invalid credentials và mechanism mismatch.
- [ ] Test TLS trust và authorization riêng.
- [ ] Test credential rotation.
- [ ] Test readiness/liveness behavior.
- [ ] Test producer/consumer capability riêng.
- [ ] Test logs và spans không lộ secrets.

## 43. Kết luận

**Authentication failure** trong Spring Kafka có thể làm producer, consumer, KafkaAdmin hoặc transactional producer không thực hiện được operation. Muốn xử lý chính xác, cần phân biệt **authentication** (xác minh principal) với **authorization** (quyền trên topic, group, cluster và transactional ID), đồng thời tách lỗi SASL, TLS, OAuth, Kerberos khỏi network timeout.

Trong phần **Health và readiness**, không được coi container running là bằng chứng Kafka đã authenticated, và cũng không dùng liveness để restart liên tục khi credentials sai. Readiness nên phản ánh capability Kafka thực sự cần cho vai trò ứng dụng; health check phải dùng đúng principal/operation, không đòi quyền rộng hơn workload.

Khi khắc phục, kiểm tra client type, protocol, mechanism, secret version, certificate/token/ticket, broker logs và ACL. Thực hiện rotation có overlap khi có thể, refresh/recreate đúng Kafka clients, xác minh thao tác produce/consume/transaction thành công rồi mới đánh dấu ready. **Không log credentials, không cấp superuser để chữa tạm và không đóng incident chỉ vì handshake đã thành công**.
