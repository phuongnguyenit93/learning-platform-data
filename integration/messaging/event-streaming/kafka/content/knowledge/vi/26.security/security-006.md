# Ánh xạ principal và phân biệt xác thực với phân quyền

Kafka bảo vệ broker bằng hai lớp có trách nhiệm khác nhau. Authentication (xác thực) xác định client là ai; authorization (phân quyền) quyết định danh tính đó được thực hiện thao tác nào trên topic, consumer group, cluster hoặc resource khác. Giữa hai lớp này còn có bước ánh xạ danh tính thành principal mà Kafka dùng trong ACL và audit log.

Principal mapping rất quan trọng khi Kafka dùng nhiều cơ chế bảo mật. Một client có thể xác thực bằng SASL/SCRAM, Kerberos, OAuth bearer token hoặc TLS client certificate. Mỗi cơ chế có dạng danh tính đầu vào khác nhau. Broker cần chuẩn hóa chúng thành principal nhất quán, ví dụ User:orders-service, để ACL có thể áp dụng đúng.

## 1. Chuỗi xử lý identity trong Kafka

Một request Kafka đi qua các bước khái quát:

~~~mermaid
flowchart LR
    A[Client connection] --> B[Authentication]
    B --> C[Authenticated identity]
    C --> D[Principal builder / mapping]
    D --> E[KafkaPrincipal]
    E --> F[Authorizer]
    F -->|Allowed| G[Execute request]
    F -->|Denied| H[AuthorizationException]
~~~

| Bước | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Client chứng minh danh tính bằng cách nào? | SCRAM username/password, Kerberos ticket, OAuth token, TLS certificate |
| Authenticated identity | Cơ chế xác thực trả về identity nào? | orders-prod, Kerberos principal, token subject, X.500 DN |
| Principal mapping | Identity được chuẩn hóa thành tên principal nào? | User:orders-prod |
| Authorization | Principal có quyền gì trên resource? | User:orders-prod được WRITE vào topic orders.events |
| Audit | Request nào được cho phép/từ chối? | Principal, operation, resource, client address và kết quả |

Authentication thành công không đồng nghĩa request được phép. Một client có credential hợp lệ vẫn có thể nhận TopicAuthorizationException nếu principal không có ACL WRITE trên topic đích.

## 2. KafkaPrincipal là gì?

Kafka biểu diễn danh tính đã xác thực bằng đối tượng principal. Principal mặc định có hai thành phần:

- **Principal type:** loại danh tính, thường là User.
- **Principal name:** tên đã chuẩn hóa, ví dụ orders-service-prod.

Trong CLI và ACL, principal thường được viết theo dạng User:<name>, ví dụ:

~~~text
User:orders-service-prod
User:payments-consumer-prod
User:kafka-platform-admin
~~~

Tên principal không phải Kafka topic, consumer group hay username được gửi trong payload. Nó là danh tính do lớp bảo mật của kết nối tạo ra và broker dùng để kiểm tra quyền.

### Principal cần ổn định

Principal là khóa liên kết giữa authentication, ACL, audit và vận hành. Nếu cùng một service lúc thì được map thành User:orders-prod, lúc lại thành User:CN=orders-prod,OU=Apps,O=Example, ACL có thể không còn khớp.

Nên thống nhất quy ước tên:

- Có namespace theo ứng dụng hoặc workload.
- Phân biệt môi trường như dev, staging và prod.
- Không dùng tên người vận hành cho service identity.
- Không đưa thông tin bí mật vào principal name.
- Tránh đổi principal name khi xoay vòng password hoặc certificate.

Credential có thể được thay thế trong khi principal giữ nguyên. Điều đó giúp xoay vòng secret mà không phải tạo lại toàn bộ ACL.

## 3. Authentication: các cơ chế phổ biến

Kafka hỗ trợ nhiều cơ chế xác thực. Cơ chế được chọn phải phù hợp với listener, client library và hạ tầng danh tính.

| Cơ chế | Client chứng minh danh tính bằng | Identity đầu vào thường gặp |
|---|---|---|
| TLS mutual authentication | Client certificate được CA tin cậy ký | X.500 Distinguished Name (DN) của certificate |
| SASL/PLAIN | Username/password | Username |
| SASL/SCRAM | Challenge-response dựa trên username/password và secret SCRAM | Username |
| SASL/GSSAPI | Kerberos ticket | Kerberos principal |
| SASL/OAUTHBEARER | OAuth 2.0 bearer token | Token principal/subject theo validator và builder |
| PLAINTEXT | Không có authentication ở tầng Kafka | Principal anonymous theo cấu hình mặc định |

PLAINTEXT không cung cấp xác thực hay mã hóa đường truyền. Không dùng nó cho listener truy cập từ mạng không tin cậy. Nếu chỉ dùng SASL mà không dùng TLS, thông tin và dữ liệu có thể không được bảo vệ trên đường truyền theo yêu cầu bảo mật.

### SASL username

Với SASL/PLAIN hoặc SASL/SCRAM, username là identity được xác thực. Khi dùng principal builder mặc định, username thường trở thành principal kiểu User với tên tương ứng.

Ví dụ:

~~~text
SASL username: orders-service-prod
Kafka principal: User:orders-service-prod
~~~

Password hoặc SCRAM credential chỉ chứng minh client sở hữu credential. Nó không quyết định quyền đọc/ghi topic. ACL vẫn được kiểm tra theo principal sau xác thực.

### TLS client certificate

Với mutual TLS, client gửi certificate trong TLS handshake. Broker kiểm tra certificate chain theo truststore và chính sách TLS. Sau khi xác thực, subject DN của certificate được dùng làm identity đầu vào cho principal builder mặc định, có thể được rút gọn bằng SSL principal mapping rules.

Certificate phải có danh tính ổn định, được cấp bởi CA mà broker tin cậy và được xoay vòng theo quy trình. Không nên dùng certificate của một người để chạy nhiều service vì audit sẽ không phân biệt được workload.

### Kerberos

SASL/GSSAPI dùng Kerberos principal, thường có dạng:

~~~text
orders/worker-01@EXAMPLE.COM
~~~

Principal có service component, host component và realm. Kafka có thể ánh xạ Kerberos principal thành local name bằng sasl.kerberos.principal.to.local.rules. Điều này hữu ích khi muốn ACL theo service name ổn định thay vì theo hostname của từng worker.

### OAuth bearer token

Với SASL/OAUTHBEARER, token được xác minh theo validator/introspection hoặc cơ chế JWT phù hợp. Principal name được lấy từ thông tin token theo cấu hình và implementation đang dùng. Với JWT, claim sub thường là định danh subject, nhưng không nên giả định mọi token validator hoặc custom builder đều dùng cùng một claim.

Các claim như groups, roles hoặc scope không tự động trở thành ACL Kafka trong mọi cấu hình. Nếu cần map claim thành principal hoặc quyền, phải triển khai cơ chế principal builder/authorizer phù hợp hoặc ánh xạ danh tính ở hệ thống cấp token. Không coi việc token chứa groups=admins là bằng chứng Kafka tự cấp quyền admin.

## 4. Principal mapping không phải authentication

Principal mapping chỉ chuẩn hóa danh tính sau khi client đã được xác thực. Nó không kiểm tra password, không xác minh certificate chain và không kiểm tra chữ ký token.

Ví dụ:

~~~text
Certificate subject:
CN=orders-prod,OU=KafkaServices,O=Example Corp

Sau SSL principal mapping:
User:orders-prod

ACL:
User:orders-prod được WRITE trên topic orders.events
~~~

Nếu certificate không hợp lệ, TLS handshake thất bại trước khi ACL được kiểm tra. Nếu certificate hợp lệ nhưng mapping tạo ra principal khác với ACL, request bị từ chối ở authorization.

Phân biệt đúng hai lớp giúp điều tra lỗi nhanh:

| Lỗi | Lớp | Ví dụ |
|---|---|---|
| TLS handshake failed | TLS/authentication | Certificate hết hạn hoặc CA không được tin cậy |
| SASL authentication failed | Authentication | Password sai, mechanism không khớp |
| OAuth token validation failed | Authentication | Token hết hạn, issuer/audience không hợp lệ |
| TopicAuthorizationException | Authorization | Principal không có READ/WRITE trên topic |
| GroupAuthorizationException | Authorization | Principal không có quyền trên consumer group |

## 5. SSL principal mapping rules

Với TLS client authentication, ssl.principal.mapping.rules cho phép chuyển subject DN thành tên principal dễ quản lý. Rules được xét theo thứ tự; rule đầu tiên khớp sẽ được dùng. Nếu không rule nào khớp, DEFAULT giữ DN theo cách biểu diễn mặc định.

Ví dụ certificate DN:

~~~text
CN=orders-service,OU=KafkaApps,O=Example Corp
~~~

Rule:

~~~properties
ssl.principal.mapping.rules=RULE:^CN=([^,]+),OU=KafkaApps.*$/$1/L,DEFAULT
~~~

Kết quả mong muốn:

~~~text
User:orders-service
~~~

Các thành phần của rule:

| Thành phần | Ý nghĩa |
|---|---|
| RULE: | Bắt đầu một rule regex |
| ^CN=([^,]+),OU=KafkaApps.*$ | Regex khớp DN và capture giá trị CN |
| $1 | Thay bằng nội dung capture group thứ nhất |
| L | Chuyển kết quả thành chữ thường |
| DEFAULT | Rule dự phòng nếu không rule nào trước đó khớp |

### Vì sao cần kiểm tra DN thực tế?

X.500 DN có thể chứa nhiều thuộc tính và thứ tự hiển thị phụ thuộc cách chuẩn hóa/biểu diễn. Dấu phẩy, dấu cộng, ký tự escape và tên thuộc tính có thể làm regex đơn giản không khớp như dự kiến.

Trước khi áp dụng rule:

1. Lấy subject DN thực tế từ certificate được client dùng.
2. Xác định định dạng DN mà Kafka principal builder nhận.
3. Viết regex khớp đúng cấu trúc đã quan sát.
4. Kiểm tra nhiều certificate: service, admin, certificate cũ và certificate mới.
5. Xác minh principal cuối cùng trong broker log/audit.
6. Chạy negative test với certificate không thuộc namespace được phép.

Không viết regex quá rộng như lấy mọi chuỗi sau CN= nếu CA cấp certificate cho nhiều loại đối tượng khác nhau. Hai certificate khác nhau có thể bị map về cùng principal và vô tình chia sẻ ACL.

### Rule order và fallback

Rules được đánh giá từ trái sang phải. Rule tổng quát đặt trước rule cụ thể có thể bắt nhầm certificate. Hãy đặt rule đặc thù trước, rule dự phòng cuối cùng.

Không bỏ DEFAULT nếu chính sách yêu cầu mọi certificate chưa biết vẫn cần một principal xác định để bị từ chối theo ACL. Mapping thành DN đầy đủ thường giúp phân biệt identity tốt hơn so với gom tất cả certificate lạ thành một principal chung.

## 6. Kerberos principal-to-local mapping

Kerberos principal thường chứa hostname và realm:

~~~text
orders/worker-01@EXAMPLE.COM
orders/worker-02@EXAMPLE.COM
~~~

Nếu ACL cần áp dụng chung cho service orders, có thể dùng sasl.kerberos.principal.to.local.rules để chuyển hai identity về cùng local name theo quy tắc đã thiết kế.

Ví dụ minh họa cấu hình:

~~~properties
sasl.kerberos.principal.to.local.rules=DEFAULT
~~~

DEFAULT dùng quy tắc local-name mặc định của Kerberos integration. Nếu cần loại bỏ host component hoặc realm, có thể khai báo rule theo cú pháp Hadoop/Kerberos principal mapping mà Kafka hỗ trợ. Cú pháp chi tiết phụ thuộc số thành phần principal và regex; cần kiểm thử với principal thực tế trước khi đưa vào broker.

Không xóa realm hoặc host một cách tùy tiện. Nếu hai realm hoặc hai service khác nhau bị map về cùng local name, chúng sẽ chia sẻ principal và có thể nhận cùng ACL.

## 7. Default principal builder

Kafka sử dụng principal builder để tạo KafkaPrincipal từ authentication context. Builder mặc định là org.apache.kafka.common.security.authenticator.DefaultKafkaPrincipalBuilder.

Với các cơ chế phổ biến:

- SASL identity được dùng làm principal name theo danh tính đã xác thực.
- SSL client identity được xây dựng từ certificate DN, có thể qua SSL mapping rules.
- Kerberos có thể áp dụng local name rules.
- OAuth bearer sử dụng principal name do token/validator cung cấp theo implementation.
- Kết nối không xác thực có thể được biểu diễn bằng anonymous principal.

Tên và chi tiết hành vi cần được xác nhận theo Kafka version và cơ chế authentication đang dùng. Khi sử dụng principal builder mặc định, nên ưu tiên các mapping property có sẵn thay vì viết custom builder không cần thiết.

### Khi nào cần custom KafkaPrincipalBuilder?

Chỉ cân nhắc custom builder khi mapping mặc định không biểu diễn được mô hình identity, ví dụ:

- Chuẩn hóa subject từ token theo claim nội bộ.
- Tạo principal type riêng cho workload hoặc tenant.
- Chuẩn hóa identity từ nhiều authentication provider về một naming convention.
- Bổ sung logic mapping phức tạp cần kiểm soát bằng code.

Custom builder là thành phần bảo mật chạy trong broker. Lỗi trong builder có thể làm mọi client không xác thực được hoặc bị map sai principal. Cần kiểm thử kỹ, quản lý version plugin và triển khai đồng nhất trên broker.

Ví dụ khung cấu hình:

~~~properties
principal.builder.class=com.example.kafka.security.WorkloadPrincipalBuilder
~~~

Builder cần triển khai interface KafkaPrincipalBuilder và trả về principal đúng loại/name. Với các topology broker cần serialize principal khi forward request, implementation còn phải đáp ứng yêu cầu serialization principal của phiên bản Kafka tương ứng. Không copy một class ví dụ mà bỏ qua contract của broker release đang chạy.

### Trách nhiệm của custom builder

- Không tự xác thực password hoặc token thay authentication provider.
- Không tin username/header do client tự gửi nếu không được cơ chế xác thực ràng buộc.
- Không map các identity khác nhau về cùng principal nếu chưa có quyết định chia sẻ quyền.
- Chuẩn hóa case và Unicode một cách nhất quán.
- Trả lỗi rõ ràng khi identity thiếu hoặc không hợp lệ.
- Có unit test cho từng authentication context được hỗ trợ.
- Có integration test với broker thật và authorizer.

## 8. Authorizer: phân quyền theo principal

Sau khi principal được tạo, authorizer kiểm tra ACL hoặc policy tương ứng. Trong KRaft, authorizer chuẩn là org.apache.kafka.metadata.authorizer.StandardAuthorizer. Các cluster ZooKeeper cũ có thể dùng AclAuthorizer theo phiên bản Kafka tương ứng.

Ví dụ cấu hình KRaft:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
allow.everyone.if.no.acl.found=false
super.users=User:kafka-platform-admin
~~~

allow.everyone.if.no.acl.found=false thiết lập deny-by-default cho resource chưa có ACL phù hợp. super.users là danh sách principal được miễn kiểm tra ACL; không đưa principal runtime vào danh sách này.

Principal mapping và authorizer là hai khâu khác nhau:

1. Mapping quyết định client trở thành principal nào.
2. ACL quyết định principal đó được làm gì.

Nếu mapping sai, ACL đúng vẫn có thể từ chối request. Nếu mapping gom nhiều service vào cùng principal, ACL có thể cấp quyền rộng hơn dự kiến cho tất cả service đó.

## 9. ACL phải dùng principal sau mapping

Giả sử certificate của Order Service có DN:

~~~text
CN=orders-service-prod,OU=KafkaApps,O=Example Corp
~~~

SSL mapping rút gọn thành:

~~~text
User:orders-service-prod
~~~

Khi cấp ACL, dùng principal đã map:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-service-prod \
  --operation Write \
  --topic orders.events
~~~

Nếu ACL được cấp cho DN đầy đủ nhưng principal thực tế là short name, hoặc ngược lại, request sẽ không khớp ACL như mong muốn.

### Ví dụ quyền producer và consumer

~~~bash
# Producer chỉ ghi topic orders.events
kafka-acls.sh \
  --bootstrap-server kafka-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-service-prod \
  --operation Write \
  --topic orders.events

# Consumer đọc topic orders.events
kafka-acls.sh \
  --bootstrap-server kafka-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:payments-reader-prod \
  --operation Read \
  --topic orders.events

# Consumer dùng group payments-service-prod
kafka-acls.sh \
  --bootstrap-server kafka-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:payments-reader-prod \
  --operation Read \
  --group payments-service-prod
~~~

Các lệnh cần chạy bằng principal quản trị ACL. admin.properties chứa credential quản trị riêng; không dùng credential này trong producer/consumer runtime.

## 10. Principal mapping cho môi trường nhiều listener

Kafka broker có thể mở nhiều listener với security protocol khác nhau. Ví dụ:

~~~properties
listeners=INTERNAL://:9092,EXTERNAL://:9093
listener.security.protocol.map=INTERNAL:SASL_PLAINTEXT,EXTERNAL:SASL_SSL
inter.broker.listener.name=INTERNAL

listener.name.external.ssl.client.auth=required
listener.name.external.sasl.enabled.mechanisms=SCRAM-SHA-512
~~~

Ví dụ trên minh họa hai listener; cấu hình thực tế còn cần SASL/SSL properties, truststore/keystore và inter-broker authentication phù hợp. Không dùng SASL_PLAINTEXT trên mạng không tin cậy.

Mapping rules là cấu hình broker ảnh hưởng tới principal được tạo cho kết nối. Nếu cluster có nhiều listener, hãy xác minh property được áp dụng đúng listener và đúng cơ chế. Kafka hỗ trợ listener-prefixed broker configs cho nhiều thuộc tính; cú pháp cụ thể phải khớp phiên bản và config được hỗ trợ.

Không giả định client chọn listener nào cũng có cùng authentication mechanism. Internal replication, controller/broker communication và external client có thể có identity khác nhau.

## 11. Cấu hình client SASL/SCRAM

Ví dụ producer dùng SCRAM qua TLS:

~~~properties
bootstrap.servers=kafka-1:9093,kafka-2:9093
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-service-prod" password="KAFKA_PASSWORD_FROM_SECRET";
ssl.truststore.location=/etc/kafka/secrets/client.truststore.p12
ssl.truststore.password=TRUSTSTORE_PASSWORD_FROM_SECRET
~~~

Username orders-service-prod là identity đầu vào; với principal builder mặc định, ACL thường dùng User:orders-service-prod. Không cần SSL principal mapping cho username SASL, trừ khi có custom principal builder thay đổi cách map.

Kafka client không tự động nội suy biến môi trường trong mọi cách chạy. Ví dụ trên là template; production phải render secret bằng secret manager/config provider và không commit password vào repository, container image hoặc log.

## 12. Cấu hình client mutual TLS

Ví dụ client dùng certificate:

~~~properties
bootstrap.servers=kafka-1:9094,kafka-2:9094
security.protocol=SSL
ssl.truststore.location=/etc/kafka/secrets/ca-truststore.p12
ssl.truststore.password=TRUSTSTORE_PASSWORD_FROM_SECRET
ssl.keystore.location=/etc/kafka/secrets/orders-client.p12
ssl.keystore.password=KEYSTORE_PASSWORD_FROM_SECRET
ssl.key.password=PRIVATE_KEY_PASSWORD_FROM_SECRET
~~~

Broker listener cần yêu cầu client authentication và trust CA cấp certificate:

~~~properties
listener.name.external.ssl.client.auth=required
ssl.client.auth=required
ssl.principal.mapping.rules=RULE:^CN=([^,]+),OU=KafkaApps.*$/$1/L,DEFAULT
~~~

Hai thuộc tính ssl.client.auth và listener-prefixed form cần được cấu hình theo listener/version; tránh khai báo trùng lặp hoặc nhầm scope. Với một listener duy nhất, global property có thể đủ. Với nhiều listener, kiểm tra broker config đã resolve để xác nhận chính sách client auth áp dụng đúng endpoint.

Sau handshake, subject DN được map thành principal. Nếu mapping lấy CN, bảo đảm CA có chính sách cấp CN duy nhất trong namespace KafkaApps; nếu không, hai certificate có thể trùng principal.

## 13. OAuth: subject, groups và roles

OAuth token có thể chứa nhiều claim:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "orders-service-prod",
  "aud": "kafka-cluster",
  "scope": "orders.write",
  "groups": ["commerce-services"],
  "exp": 1795179000
}
~~~

Trong ví dụ:

- iss xác định issuer.
- sub thường xác định subject/client identity.
- aud xác định audience mà token dành cho.
- scope mô tả phạm vi token.
- groups có thể là claim riêng của identity provider.
- exp là thời điểm hết hạn.

Kafka cần validator kiểm tra chữ ký/issuer/audience/expiry theo cơ chế đã triển khai. Principal name được lấy từ token principal/validator hoặc custom builder. Authorizer mặc định vẫn kiểm tra ACL theo principal, không tự hiểu mọi group/role claim như role-based access control.

Nếu muốn dùng groups/roles để cấp quyền, có thể:

- Phát token với subject tương ứng service account có principal ổn định.
- Ánh xạ group/role ở identity provider thành principal name theo chính sách rõ ràng.
- Dùng custom authorizer nếu thực sự cần authorization theo claims.

Không tạo principal kiểu User:admin chỉ vì token có scope admin mà chưa kiểm tra issuer, audience, token validation và mapping policy.

## 14. Principal mapping và multi-tenancy

Trong cluster nhiều tenant, principal cần phản ánh ranh giới tenant và service. Ví dụ:

~~~text
User:tenant-a.orders-api.prod
User:tenant-a.payments-worker.prod
User:tenant-b.orders-api.prod
~~~

ACL có thể cấp topic prefix theo tenant:

~~~text
tenant-a.orders.*
tenant-b.orders.*
~~~

Tuy nhiên, chỉ đặt tenant trong tên principal không tự tạo cách ly dữ liệu. Cần kết hợp:

- ACL giới hạn topic, group và transactional ID theo tenant.
- Principal mapping không cho tenant tự chọn tên principal tùy ý.
- Identity provider cấp credential riêng cho từng workload.
- Không cho tenant tạo principal có tên trùng platform admin.
- Quản lý prefix/resource pattern để không overlap ngoài ý muốn.
- Audit thao tác tạo/sửa ACL và mapping.

Nếu dùng wildcard hoặc prefix quá rộng, một principal tenant có thể truy cập dữ liệu tenant khác. Hãy kiểm thử negative access giữa các tenant.

## 15. super.users và principal quản trị

super.users liệt kê principal được miễn kiểm tra ACL. Ví dụ:

~~~properties
super.users=User:kafka-platform-admin;User:kafka-breakglass
~~~

Chỉ đưa principal quản trị nền tảng hoặc break-glass đã được kiểm soát vào danh sách này. Không đưa principal ứng dụng runtime vào super.users; nếu làm vậy, ACL giới hạn topic/group cho principal đó không còn là ranh giới bảo vệ hiệu quả.

Tên trong super.users phải khớp principal thực tế sau mapping. Nếu certificate admin được map thành User:kafka-admin nhưng broker khai báo User:CN=kafka-admin,OU=Admins,O=Example, principal đó có thể không được nhận diện như mong muốn.

Break-glass credential cần được cất trong secret manager, có người chịu trách nhiệm, audit và quy trình xoay vòng. Không chia sẻ credential admin cho pipeline ứng dụng.

## 16. Audit log và điều tra principal

Khi authorization thất bại, cần xác định principal cuối cùng mà broker đã nhìn thấy. Không chỉ nhìn username trong client config hoặc subject DN trên certificate.

Thông tin hữu ích:

- Listener nhận kết nối.
- Authentication mechanism.
- Principal type và principal name.
- Client address/host.
- Operation bị yêu cầu.
- Resource type và resource name.
- ACL decision: allow/deny.
- Request correlation ID và timestamp.

Ví dụ log có thể thể hiện principal User:orders-service-prod bị từ chối WRITE trên topic payments.events. Từ đó có thể thấy authentication đã thành công; lỗi nằm ở authorization/resource scope.

Không log password, SCRAM secret, OAuth bearer token, private key hoặc JAAS string đã giải mã. Log subject DN hoặc principal name theo chính sách dữ liệu tổ chức.

### Kiểm tra ACL hiện có

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1:9093 \
  --command-config admin.properties \
  --list \
  --principal User:orders-service-prod
~~~

Liệt kê ACL theo topic:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1:9093 \
  --command-config admin.properties \
  --list \
  --topic orders.events
~~~

ACL list cho biết policy được cấu hình; broker log/audit giúp xác định principal thực tế và request nào bị từ chối. Cần dùng cả hai khi điều tra.

## 17. Troubleshooting theo lớp

| Triệu chứng | Lớp cần kiểm tra | Nguyên nhân có thể |
|---|---|---|
| TLS handshake failure | TLS/authentication | Truststore, certificate chain, hostname verification, certificate hết hạn |
| Client certificate không được gửi | Client TLS config | Keystore sai hoặc listener không yêu cầu/không nhận mTLS như dự kiến |
| SASL authentication failed | Authentication | Username/password, mechanism, JAAS config, SCRAM credential |
| Kerberos login failed | Authentication | Keytab, principal, ticket cache, clock skew, service principal |
| OAuth token rejected | Authentication | Issuer, audience, signature, expiry, JWKS/introspection endpoint |
| Request principal khác dự kiến | Principal mapping | SSL rules, Kerberos local rules, custom builder, case/regex |
| TopicAuthorizationException | Authorization | ACL thiếu hoặc principal mapping không khớp |
| GroupAuthorizationException | Authorization | ACL resource GROUP thiếu hoặc group ID khác |
| ClusterAuthorizationException | Authorization | ACL trên CLUSTER thiếu cho operation |
| Admin CLI thấy ACL nhưng request vẫn bị từ chối | Mapping/ACL evaluation | ACL dùng principal khác, DENY khớp, host/pattern không khớp |
| Một số listener hoạt động, listener khác lỗi | Listener configuration | Security protocol, mechanism, truststore hoặc mapping config không đồng nhất |

### Trình tự điều tra đề xuất

1. Xác nhận client kết nối đúng bootstrap/listener.
2. Xác định security protocol và SASL mechanism hoặc TLS client-auth.
3. Kiểm tra authentication error trước; nếu handshake/login thất bại thì chưa đến bước ACL.
4. Lấy principal cuối cùng từ broker log/audit.
5. So sánh principal với ssl.principal.mapping.rules, Kerberos local rules hoặc custom builder.
6. Liệt kê ACL theo principal/resource và kiểm tra DENY, host, literal/prefix pattern.
7. Chạy thao tác tối thiểu được phép và thao tác ngoài phạm vi để xác minh policy.
8. Ghi lại mapping rule/config version cùng kết quả test.

Không chữa authorization error bằng cách chuyển ứng dụng sang credential admin hoặc thêm principal runtime vào super.users.

## 18. Xoay vòng credential và thay đổi mapping

Xoay password hoặc certificate không nhất thiết phải đổi principal. Đây là lợi ích của principal mapping ổn định:

- Credential cũ được thay bằng credential mới.
- Credential mới xác thực thành cùng principal.
- ACL tiếp tục áp dụng mà không cần tạo lại.
- Sau khi rollout xong, thu hồi credential cũ.

Thay đổi mapping rule lại khác: cùng certificate có thể trở thành principal khác. Trước khi thay đổi:

1. Xác định principal cũ và principal mới cho từng identity.
2. Tạo ACL cho principal mới nếu cần giai đoạn chuyển tiếp.
3. Deploy mapping rule đồng nhất trên broker.
4. Xác minh client thực tế được map đúng.
5. Thu hồi ACL cũ sau khi không còn client sử dụng principal cũ.

Mapping rule sai có thể ảnh hưởng toàn bộ kết nối TLS. Nên có cấu hình rollback và kiểm thử trên staging với certificate thực tế trước production.

## 19. Kiểm thử principal mapping

Một bộ test nên kiểm tra cả danh tính hợp lệ lẫn trường hợp bị từ chối:

| Test | Kết quả mong đợi |
|---|---|
| SCRAM user orders-service-prod đăng nhập | Principal là User:orders-service-prod theo builder mặc định |
| Certificate CN orders-service-prod khớp rule | Principal map về User:orders-service-prod |
| Certificate không khớp rule cụ thể | Fallback theo DEFAULT; không gom vào principal runtime chung |
| Hai certificate service khác nhau | Tạo hai principal khác nhau |
| Kerberos worker-01 và worker-02 cùng service | Chỉ map về cùng local principal nếu chính sách chủ ý |
| Token hết hạn | Authentication thất bại |
| Token subject khác | Principal khác theo mapping policy |
| Principal hợp lệ ghi topic được cấp | Thành công |
| Principal hợp lệ ghi topic ngoài phạm vi | Authorization bị từ chối |
| Tenant A truy cập topic tenant B | Authorization bị từ chối |
| Runtime principal gọi thao tác admin | Authorization bị từ chối |

Với custom builder, viết unit test cho regex/claim mapping và integration test trên broker. Kiểm tra cả log principal và kết quả ACL; không chỉ xác nhận client kết nối thành công.

## 20. Checklist production

- Chọn authentication mechanism theo workload và trust boundary.
- Dùng TLS cho kết nối qua mạng không tin cậy.
- Cấp identity riêng cho mỗi service/environment.
- Xác định principal name cuối cùng trước khi tạo ACL.
- Dùng SSL principal mapping rules cho certificate DN khi cần.
- Dùng Kerberos local rules có kiểm soát nếu cần rút gọn principal.
- Chỉ triển khai custom KafkaPrincipalBuilder khi mapping mặc định không đáp ứng.
- Không coi OAuth group/scope claim tự động là ACL role.
- Giữ principal ổn định qua credential rotation.
- Đảm bảo ACL dùng đúng principal sau mapping.
- Kiểm tra super.users và không đưa runtime principal vào đó.
- Dùng deny-by-default nếu phù hợp chính sách.
- Kiểm tra listener-specific authentication và mapping config.
- Audit principal, resource, operation và quyết định authorization.
- Không log password, token, private key hoặc secret JAAS.
- Test negative access, multi-tenant isolation và admin boundary.
- Có kế hoạch rollback khi thay mapping rule hoặc principal builder.

## 21. Những nhầm lẫn thường gặp

- **Authentication thành công nghĩa là được phép ghi topic:** authentication chỉ xác định identity; authorizer mới quyết định quyền.
- **Username luôn là principal cuối cùng:** SSL, Kerberos, OAuth hoặc custom builder có thể tạo principal khác.
- **SSL principal mapping xác minh certificate:** TLS trust validation xác minh certificate; mapping chỉ đổi tên principal sau authentication.
- **Principal mapping là role mapping:** mapping tạo danh tính; ACL mới cấp quyền theo resource/operation.
- **OAuth groups tự động trở thành Kafka ACL:** authorizer mặc định kiểm tra principal, không tự hiểu mọi claim như role.
- **Hai certificate có cùng CN luôn an toàn:** nếu map cùng CN, chúng chia sẻ principal và ACL.
- **Đổi mapping rule chỉ ảnh hưởng log:** principal mới có thể làm ACL cũ không còn khớp.
- **SASL/SCRAM cần SSL principal mapping:** mapping SSL dành cho certificate DN; SASL username được xử lý theo principal builder.
- **Custom principal builder là cách sửa ACL thiếu:** builder thay đổi danh tính; không nên dùng để né authorization policy.
- **super.users chỉ là một ACL admin:** đây là danh sách principal bỏ qua ACL checks, có quyền rất rộng.
- **Có thể debug bằng cách cấp ALL:** cấp quyền rộng che mất principal/resource mismatch và tạo rủi ro.

Authentication chứng minh client là ai; principal mapping chuẩn hóa identity đó thành KafkaPrincipal; authorization dùng principal cuối cùng để đánh giá ACL. Khi thiết kế, hãy giữ principal ổn định, map certificate/Kerberos/token theo quy tắc có kiểm thử và cấp ACL đúng tên sau mapping. Tách ba khâu này giúp điều tra lỗi rõ ràng, giới hạn quyền theo workload và tránh việc một thay đổi credential hoặc mapping vô tình mở rộng quyền truy cập.
