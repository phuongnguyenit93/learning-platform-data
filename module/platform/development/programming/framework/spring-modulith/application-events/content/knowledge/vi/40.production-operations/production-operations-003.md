# Quản lý credential

## Mục tiêu

Ứng dụng Spring Modulith có thể giao tiếp với Kafka, RabbitMQ, Schema Registry, database, HTTP API và hệ thống quản lý khóa. Mỗi kết nối có thể cần username/password, API key, token, client certificate hoặc private key. Nếu credential bị hard-code, dùng chung quá rộng, không xoay vòng hoặc xuất hiện trong log, một lỗi cấu hình nhỏ có thể trở thành sự cố bảo mật production.

**Quản lý credential** là quá trình cấp phát, lưu trữ, sử dụng, luân chuyển, thu hồi và kiểm toán thông tin xác thực của workload. Mục tiêu là để mỗi thành phần chỉ có danh tính và quyền cần thiết, credential có vòng đời rõ ràng và có thể thu hồi nhanh khi bị lộ.

Sau bài học, bạn có thể:

- Phân biệt password, API key, token, certificate và private key.
- Xác định credential theo từng kết nối trong luồng application event.
- Lưu và cấp credential qua secret manager hoặc workload identity.
- Cấu hình Spring Boot để tham chiếu secret mà không đưa giá trị bí mật vào source code.
- Áp dụng least privilege, credential riêng cho từng workload và môi trường.
- Xoay vòng, thu hồi, kiểm toán và xử lý credential bị lộ.

## 1. Credential trong luồng application event

`ApplicationEventPublisher` dùng để phát event trong cùng Spring application context và bản thân lời gọi này không cần password hoặc API key. Credential xuất hiện khi event được lưu trữ hoặc đi qua ranh giới hạ tầng.

Các kết nối thường gặp:

| Thành phần | Credential có thể cần | Mục đích |
| --- | --- | --- |
| Kafka producer | SASL username/password, OAuth token hoặc client certificate | Xác thực workload được phép publish. |
| Kafka consumer | SASL/OAuth identity hoặc client certificate | Xác thực workload được phép consume. |
| RabbitMQ | Username/password hoặc client certificate | Xác thực kết nối tới broker và vhost. |
| Schema Registry | API key, OAuth token hoặc service credential | Đăng ký/đọc schema theo quyền được cấp. |
| Database của Event Publication Registry | Database username/password, certificate hoặc workload identity | Lưu và truy vấn trạng thái publication. |
| Outbox/inbox database | Database credential | Lưu message cần phát và message đã xử lý. |
| HTTP webhook/API | OAuth access token, API key hoặc mTLS certificate | Xác thực lời gọi tới hệ thống nhận. |
| KMS/secret manager | Workload identity hoặc token ngắn hạn | Lấy/unwrap key và đọc secret được cấp quyền. |

Mỗi kết nối là một ranh giới bảo mật riêng. Credential Kafka không nên được dùng để truy cập Schema Registry hoặc database nếu các hệ thống đó có thể cấp danh tính riêng. Consumer cũng không nên dùng chung credential với producer khi hai vai trò có quyền khác nhau.

### Credential không phải event payload

Không đưa password, API key, access token, refresh token, private key hoặc nội dung secret vào application event, header, message key hay metadata broker. Event chỉ nên mang dữ liệu nghiệp vụ và định danh tham chiếu cần thiết. Nếu consumer cần truy cập một hệ thống, consumer lấy credential bằng danh tính workload của chính nó.

Không gửi secret qua `ApplicationEventPublisher` để “chuyển” cho module khác. Các module nên gọi API nội bộ được kiểm soát hoặc lấy secret theo identity và quyền của workload.

## 2. Phân loại credential và vòng đời

Credential có nhiều dạng và yêu cầu vận hành khác nhau:

| Loại | Ví dụ | Điểm cần quản lý |
| --- | --- | --- |
| Password | Database password, RabbitMQ password | Độ mạnh, quyền, rotation, tránh lộ trong log/process arguments. |
| API key | Schema Registry key, webhook key | Scope, ngày hết hạn, giới hạn dịch vụ và khả năng thu hồi. |
| Access token | OAuth2 bearer token | Audience, scope, expiry, issuer và cách refresh. |
| Client certificate | mTLS certificate | Certificate chain, SAN, EKU, expiry và private key tương ứng. |
| Private key | TLS key, signing key | Bảo vệ key material, quyền sử dụng và quy trình rotation/revocation. |
| Cloud/workload identity | Managed identity, service account identity | Trust relationship, role binding và phạm vi tài nguyên được phép truy cập. |

Mỗi credential nên có metadata:

- `credentialId`: định danh tham chiếu, không phải giá trị secret.
- `owner`: service/team chịu trách nhiệm.
- `purpose`: kết nối hoặc thao tác được phép.
- `environment`: dev, test, staging hoặc production.
- `scope`: topic, queue, database/schema hoặc API cụ thể.
- `issuedAt`, `expiresAt`, `rotationDueAt` nếu có.
- `source`: secret manager, workload identity provider hoặc PKI.
- `status`: active, rotation-pending, revoked hoặc expired.
- `lastRotatedAt` và thông tin audit liên quan.

Không ghi giá trị password/token/private key vào catalog. Catalog chỉ lưu metadata và tham chiếu tới secret manager theo quyền truy cập phù hợp.

## 3. Lưu credential an toàn

### Secret manager là nguồn quản lý chính

Production credential nên được lưu trong secret manager hoặc hệ thống quản lý danh tính của nền tảng, chẳng hạn Vault, cloud secret manager, Kubernetes integration với secret provider hoặc dịch vụ PKI/KMS được tổ chức phê duyệt.

Secret manager thường cung cấp:

- Mã hóa khi lưu và kiểm soát truy cập theo identity.
- Audit ai đọc hoặc thay đổi secret, vào thời điểm nào.
- Versioning và rotation.
- Secret động hoặc credential có thời hạn ngắn.
- Phân tách quyền đọc, ghi, rotate và revoke.
- Khả năng thu hồi hoặc thay thế secret khi có sự cố.

Ứng dụng nên lấy đúng secret cần thiết lúc khởi động hoặc theo cơ chế refresh được hỗ trợ. Không tải toàn bộ secret của môi trường vào một process nếu service chỉ cần một vài credential.

### Không hard-code secret

Không đặt giá trị bí mật trực tiếp trong:

- Java source, YAML/properties hoặc file cấu hình được commit.
- Dockerfile, container image, Helm values công khai hoặc manifest lưu trong Git.
- Test fixture, sample payload, tài liệu, screenshot hoặc ticket.
- Command line, shell history hoặc log startup.
- CI output, build artifact và file dump.

Các file `.env` dùng cho local development cũng cần nằm ngoài version control, có quyền truy cập phù hợp và không được dùng làm cơ chế quản lý credential production.

### Environment variable chỉ là kênh cấp phát

Tham chiếu secret qua environment variable có thể tiện cho ứng dụng, nhưng environment variable không tự trở thành secret manager. Cần kiểm soát ai có thể đọc process environment, cấu hình container/orchestrator, crash dump và công cụ debug.

Với nền tảng hỗ trợ, ưu tiên workload identity hoặc mount secret qua volume có quyền hạn chế. Nếu dùng environment variable, chỉ cấp cho đúng container/process, không in toàn bộ environment khi debug và có quy trình refresh/restart khi secret đổi.

### Phân tách theo môi trường

Dev, test, staging và production phải dùng credential riêng. Không sao chép credential production xuống máy developer hoặc CI. Test dùng secret giả lập và broker/database riêng. Staging nên có identity và quyền gần production nhưng chỉ truy cập tài nguyên staging.

## 4. Workload identity và nguyên tắc least privilege

Khi nền tảng hỗ trợ, dùng workload identity/managed identity để ứng dụng chứng minh danh tính mà không cần lưu một password dài hạn. Ví dụ Kubernetes service account được liên kết với cloud IAM role, hoặc workload trong cloud dùng managed identity để đọc secret từ vault.

Ưu tiên credential ngắn hạn và tự động cấp phát khi phù hợp. Token ngắn hạn giảm thời gian một credential bị lộ còn có thể sử dụng; tuy vậy, issuer, audience, scope, clock skew và refresh failure vẫn cần được quản lý.

### Mỗi workload một identity

Tạo identity riêng cho producer, consumer và service quản trị. Ví dụ:

| Identity | Quyền tối thiểu gợi ý |
| --- | --- |
| `orders-event-producer` | Ghi topic `orders.events` cần thiết. |
| `inventory-event-consumer` | Đọc topic cần thiết và dùng consumer group được cấp. |
| `schema-reader-orders` | Đọc subject/schema của Orders. |
| `schema-publisher-orders` | Đăng ký schema cho subject được chỉ định. |
| `event-ops-admin` | Quyền quản trị theo quy trình break-glass, không dùng cho runtime. |

Tên trên là ví dụ. Quyền thực tế phải theo ACL và cấu trúc broker của hệ thống.

### Least privilege

Credential chỉ nên có quyền cần thiết cho một mục đích:

- Producer không cần quyền consume mọi topic.
- Consumer không cần quyền tạo/xóa topic hoặc quản trị broker.
- Runtime service không cần quyền đọc mọi secret trong vault.
- Ứng dụng không cần quyền rotate/revoke credential của chính nó nếu nền tảng có thể thực hiện việc đó.
- Quyền production không nên được cấp cho developer hoặc pipeline không có nhiệm vụ triển khai production.

Tách quyền đọc secret khỏi quyền quản trị secret. Người hoặc workload có quyền deploy ứng dụng không nhất thiết cần đọc plaintext mọi credential được ứng dụng sử dụng.

## 5. Cấp secret cho Spring Boot

Ứng dụng nên tham chiếu secret qua property placeholder hoặc cơ chế secret integration được nền tảng hỗ trợ. File cấu hình chứa tên property và cấu trúc, không chứa giá trị bí mật.

Ví dụ Kafka SASL_SSL:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
      ssl.endpoint.identification.algorithm: https
```

`KAFKA_SASL_JAAS_CONFIG` được cấp từ secret manager hoặc cơ chế injection của runtime. Không ghi giá trị JAAS chứa username/password vào YAML đã commit. Mechanism và protocol phải khớp cấu hình broker.

Ví dụ RabbitMQ:

```yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: ${RABBITMQ_PORT:5671}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: ${RABBITMQ_VHOST:/orders}
    ssl:
      enabled: true
```

Ví dụ database:

```yaml
spring:
  datasource:
    url: ${EVENT_DATABASE_URL}
    username: ${EVENT_DATABASE_USERNAME}
    password: ${EVENT_DATABASE_PASSWORD}
```

Các property SSL, trust store và client certificate cần được cấu hình thêm theo driver và phiên bản Spring Boot/connector đang dùng. Placeholder chỉ giải quyết việc đưa giá trị vào cấu hình; nó không tự bật TLS, xác minh chứng thư hoặc giới hạn quyền database.

### Kiểm tra cấu hình bắt buộc khi khởi động

Nếu một credential bắt buộc bị thiếu, ứng dụng nên fail fast với thông báo chỉ nêu tên property/secret reference, không in giá trị. Tránh fallback sang tài khoản mặc định, anonymous access hoặc plaintext chỉ để service khởi động được.

Có thể dùng validation cho cấu hình typed `@ConfigurationProperties`, nhưng không log object cấu hình chứa password/token. Nếu dùng `toString()` tự sinh, bảo đảm trường nhạy cảm được che hoặc loại khỏi output.

## 6. Credential cho từng hạ tầng event

### Kafka

Kafka có thể xác thực bằng SASL/SCRAM, SASL/OAUTHBEARER hoặc TLS client certificate tùy cấu hình cluster. Kết nối có xác thực phải đi qua TLS (`SASL_SSL`) khi dùng password/token để credential không truyền dưới dạng plaintext.

Quản lý riêng:

- Principal producer và consumer.
- ACL theo topic, consumer group và transactional ID nếu có.
- Secret/token cho từng môi trường.
- Trust store và client certificate nếu dùng mTLS.
- Credential cho Schema Registry nếu registry tách biệt.

Không dùng superuser/admin credential trong `spring.kafka` của runtime service. Khi một consumer chỉ cần đọc `orders.events`, không cấp quyền đọc toàn bộ cluster.

### RabbitMQ

Mỗi service nên có RabbitMQ user hoặc identity riêng, gắn với vhost và permissions phù hợp. Giới hạn quyền configure/write/read theo exchange, queue và routing key cần dùng. Không dùng `guest` hoặc tài khoản quản trị mặc định cho ứng dụng production.

Nếu dùng TLS/mTLS, quản lý client certificate và private key riêng cho workload. Password broker và certificate là hai credential khác nhau, cần rotation và audit tương ứng.

### Schema Registry

Schema Registry thường có credential và authorization riêng với broker. Producer đăng ký schema có thể cần quyền ghi subject; consumer chỉ cần đọc schema. Không cấp một API key có quyền quản trị toàn registry cho mọi ứng dụng.

### Database và Event Publication Registry

Database credential dùng cho Event Publication Registry/outbox/inbox phải thuộc service identity của ứng dụng. Dùng account runtime riêng, không dùng tài khoản migration/admin. Tách quyền DDL migration khỏi quyền DML cần thiết khi chạy ứng dụng.

Nếu database hỗ trợ IAM authentication hoặc certificate-based authentication, cân nhắc credential ngắn hạn thay cho password tĩnh. Bật TLS cho kết nối database từ xa theo policy của nền tảng.

### HTTP API và webhook

Ưu tiên OAuth2 client credentials hoặc workload identity khi hệ thống đích hỗ trợ. Token nên có audience và scope cụ thể, thời hạn ngắn, được cache/refresh an toàn. Nếu dùng API key, giới hạn key cho một service và endpoint cần thiết; không dùng chung key trên nhiều ứng dụng.

## 7. Rotation không gây gián đoạn

Credential cần được xoay vòng định kỳ theo policy và ngay khi có dấu hiệu bị lộ. Rotation cần được thiết kế trước để tránh downtime hoặc tạo ra một khoảng thời gian không có credential hợp lệ.

Một quy trình rotation thường gồm:

1. Tạo credential mới hoặc version mới trong secret manager/identity provider.
2. Cấp quyền tối thiểu tương đương cho credential mới.
3. Cấu hình broker/API/database chấp nhận credential mới; giữ credential cũ trong khoảng overlap nếu nền tảng hỗ trợ.
4. Cập nhật secret reference hoặc mount cho workload.
5. Rolling restart/reload theo cơ chế ứng dụng hỗ trợ.
6. Xác minh mọi instance kết nối thành công bằng credential mới.
7. Theo dõi authentication failure và traffic còn dùng credential cũ.
8. Thu hồi credential cũ sau khi xác nhận không còn workload sử dụng.
9. Ghi nhận thời điểm, người thực hiện và kết quả rotation.

### Chiến lược overlap

Nếu broker cho phép nhiều principal, có thể tạo principal mới, triển khai ứng dụng chuyển sang principal mới rồi thu hồi principal cũ. Với password của một user chỉ có một giá trị hoạt động, cần dùng cơ chế hỗ trợ đổi password có phối hợp hoặc tạo user thay thế để có thời gian overlap.

Với mTLS, có thể cập nhật trust store để tin CA/certificate mới trước, triển khai certificate client mới, xác minh kết nối rồi mới loại bỏ trust cũ. Trình tự cụ thể phụ thuộc PKI và broker.

Không giả định mọi secret tự động được reload khi secret manager đổi version. Một số thư viện chỉ đọc credential lúc khởi tạo connection factory; khi đó cần refresh bean, recreate client hoặc rolling restart theo cách đã kiểm thử.

### Theo dõi hạn dùng

Theo dõi `expiresAt` của token/certificate/API key và đặt cảnh báo trước thời hạn. Cảnh báo cần đủ sớm để xử lý lỗi cấp phát, deploy hoặc đồng bộ giữa nhiều instance. Không chỉ cảnh báo vào ngày hết hạn.

## 8. Thu hồi và xử lý credential bị lộ

Khi nghi ngờ credential bị lộ, ưu tiên giới hạn khả năng sử dụng credential đó và xác định phạm vi ảnh hưởng.

Quy trình phản ứng:

1. Xác định credential ID, owner, service và các tài nguyên nó có thể truy cập.
2. Thu hồi hoặc disable credential bị lộ; nếu cần, chặn principal/identity ở broker hoặc API.
3. Cấp credential thay thế và triển khai theo quy trình khẩn cấp có kiểm soát.
4. Kiểm tra audit log để tìm thời điểm, nguồn và thao tác đáng ngờ.
5. Xác định message, topic, database hoặc secret khác có thể bị truy cập.
6. Xoay các credential liên quan nếu có nguy cơ lộ chéo.
7. Kiểm tra log, CI artifact, image, dump và repository để tìm bản sao còn tồn tại.
8. Ghi incident timeline, quyết định thu hồi và bằng chứng xác minh.

Xóa secret khỏi file hiện tại không làm credential cũ mất hiệu lực. Nếu secret từng được commit, phải rotate/revoke giá trị đó và xử lý lịch sử repository/artifact theo quy trình incident. Không dựa vào việc xóa một dòng code để coi sự cố đã được giải quyết.

### Break-glass access

Tài khoản khẩn cấp cần được kiểm soát riêng, có MFA/approval theo policy, thời hạn ngắn và audit đầy đủ. Không dùng break-glass credential cho ứng dụng runtime hoặc tác vụ định kỳ. Sau khi sử dụng, rà soát hành động và rotate nếu policy yêu cầu.

## 9. Bảo vệ secret trong log, trace và công cụ vận hành

Credential có thể bị lộ gián tiếp qua exception, startup log, HTTP header, debug dump hoặc actuator endpoint.

- Không log `Authorization`, `Cookie`, SASL JAAS config, password hoặc private key.
- Che token/API key trong request/response logging và tracing instrumentation.
- Không log toàn bộ environment variables hoặc `@ConfigurationProperties` chứa secret.
- Không đưa secret vào metric label, span attribute, exception message hoặc correlation metadata.
- Hạn chế quyền truy cập heap dump, thread dump và crash dump vì chúng có thể chứa credential trong bộ nhớ.
- Giới hạn quyền truy cập actuator/configuration endpoint và tắt endpoint không cần thiết.
- Không gửi secret trong event, header broker hoặc dead-letter payload.

Nếu cần chẩn đoán, log credential reference, principal ID, endpoint logic và error category thay vì giá trị bí mật. Ví dụ `credentialRef=secret/orders/kafka-producer` hữu ích hơn username/password thật.

## 10. CI/CD và quản lý credential triển khai

Pipeline build/test không nên cần production secret. Unit test và module test dùng fake credential; integration test dùng secret tạm thời cho broker/container hoặc môi trường test riêng.

Trong pipeline deploy:

- Dùng workload identity/OIDC federation tới cloud hoặc secret manager khi có thể.
- Tránh lưu long-lived cloud access key trong CI variables nếu có cơ chế identity ngắn hạn.
- Chỉ job deploy production được cấp quyền đọc secret production.
- Tách quyền build artifact khỏi quyền triển khai và đọc credential.
- Không in secret khi step thất bại; mask output nhưng không coi masking là biện pháp bảo vệ duy nhất.
- Không đóng gói secret vào JAR, image hoặc artifact.
- Audit pipeline identity và lần truy cập secret.

Pull request chỉ chứa secret reference và cấu hình không nhạy cảm. Secret thật được cấp khi workload chạy trong môi trường đích.

## 11. Quan sát và kiểm toán credential

Vận hành production cần biết credential nào sắp hết hạn, workload nào đang dùng và lần rotation gần nhất có thành công không.

Các chỉ số/trạng thái hữu ích:

- Credential sắp hết hạn theo owner/service/environment.
- Tuổi credential kể từ lần rotate gần nhất.
- Authentication failure theo endpoint và principal (không chứa secret value).
- Số instance còn dùng credential version cũ sau rotation.
- Secret access denied hoặc access pattern bất thường.
- Token refresh failure và tỷ lệ token sắp hết hạn.
- Certificate handshake failure và certificate expiry.
- Lần đọc/rotate/revoke secret trong audit log.

Metric nên dùng dimension có cardinality giới hạn như service, credential type, environment và endpoint. Không dùng secret value, token subject tùy ý hoặc request ID làm label metric. Credential ID chỉ nên đưa vào log/audit có kiểm soát nếu số lượng lớn.

### Audit trail

Audit cần ghi ai hoặc workload nào đã đọc, tạo, rotate, revoke credential; secret reference nào bị tác động; thời gian và kết quả. Không ghi plaintext secret vào audit. Đồng bộ thời gian hệ thống giúp đối chiếu log giữa secret manager, broker, orchestrator và ứng dụng.

## 12. Kiểm thử quản lý credential

Các bài kiểm thử nên xác minh cả cấu hình hợp lệ và nhánh từ chối:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Thiếu credential bắt buộc | Ứng dụng fail fast; thông báo không lộ giá trị secret. |
| Credential sai | Broker/API từ chối xác thực và metric/log ghi nhận đúng loại lỗi. |
| Credential hợp lệ nhưng thiếu ACL | Authentication thành công nhưng thao tác bị từ chối. |
| Producer và consumer dùng identity riêng | Mỗi identity chỉ có quyền đúng vai trò. |
| Secret được rotate | Workload chuyển sang version mới và kết nối hoạt động. |
| Credential cũ bị revoke | Instance còn dùng credential cũ không thể tiếp tục truy cập. |
| Token hết hạn | Refresh hoặc tái xác thực theo policy; không fallback sang anonymous. |
| Certificate sai hostname/CA | TLS client từ chối kết nối. |
| Secret manager unavailable | Ứng dụng xử lý theo policy an toàn, không log secret hoặc chuyển sang credential mặc định. |
| Log/trace khi lỗi | Không xuất hiện password, token, API key hay private key. |

Test nên dùng broker/database/container riêng và credential giả lập. Không bao giờ đưa production credential vào integration test, snapshot, fixture hoặc báo cáo CI.

## 13. Những lỗi quản lý credential thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Hard-code password trong YAML/Git | Secret tồn tại trong history và artifact. | Dùng secret manager và rotate giá trị đã lộ. |
| Dùng chung admin credential | Một service bị xâm nhập có thể kiểm soát toàn hệ thống. | Identity riêng, ACL và least privilege. |
| Dùng environment variable như secret vault | Credential có thể lộ qua process/debug/dump. | Kiểm soát injection, ưu tiên workload identity/secret volume. |
| Không có rotation plan | Credential tồn tại quá lâu và khó thay khi có sự cố. | Rotation schedule, overlap và expiry alert. |
| Rotate secret nhưng không reload client | Một số instance tiếp tục dùng credential cũ. | Xác minh refresh/recreate connection và rolling restart. |
| Chỉ xóa secret khỏi source | Credential đã commit vẫn còn hiệu lực. | Revoke/rotate và xử lý bản sao lịch sử/artifact. |
| Log request header hoặc config object | Token/password xuất hiện trong log. | Redact và chỉ log reference/error category. |
| Dùng credential production trong CI/test | Tăng phạm vi lộ secret và khó kiểm soát truy cập. | Identity/secret riêng cho từng môi trường. |
| Coi TLS là authorization | Workload đã mã hóa vẫn có thể có quyền quá rộng. | ACL, scope và database grants riêng. |

## 14. Quy trình áp dụng

Khi quản lý credential cho ứng dụng Spring Modulith:

1. Lập danh sách mọi kết nối: Kafka, RabbitMQ, Schema Registry, database, HTTP API và KMS.
2. Xác định loại credential, owner, purpose, environment, scope và expiry cho từng kết nối.
3. Tạo workload identity riêng cho producer, consumer và service quản trị.
4. Lưu secret trong secret manager/PKI; cấp qua identity hoặc secret injection có kiểm soát.
5. Cấu hình Spring Boot bằng secret reference; fail fast nếu credential bắt buộc thiếu.
6. Áp dụng TLS, authentication và least privilege/ACL ở từng hạ tầng.
7. Thiết lập rotation, overlap, reload/rolling restart và cảnh báo hết hạn.
8. Chuẩn bị quy trình revoke và incident response khi credential bị lộ.
9. Redact secret khỏi log, trace, dump, CI output và event payload.
10. Kiểm thử credential sai/hết hạn, quyền thiếu, rotation, revocation và audit trail.

Quản lý credential tốt giúp từng producer, consumer và thành phần vận hành có danh tính riêng, quyền vừa đủ và vòng đời có thể kiểm soát. Khi secret được cấp từ nguồn tin cậy, không xuất hiện trong source/event/log, được xoay vòng và thu hồi có kiểm chứng, luồng application event của Spring Modulith có thể vận hành production an toàn và dễ điều tra hơn.
