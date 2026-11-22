# Liệt kê giao thức, dữ liệu lưu trữ và hệ thống bên ngoài

Trước khi nâng cấp Java, thay đổi thư viện hoặc thay thế một dịch vụ, cần biết ứng dụng đang giao tiếp với những thành phần nào và trao đổi dữ liệu bằng cách nào. Một module có thể chỉ có vài controller nhìn thấy từ bên ngoài nhưng lại phụ thuộc vào nhiều cơ sở dữ liệu, message broker, dịch vụ xác thực, hệ thống thanh toán, kho file và tác vụ batch. Nếu bỏ sót một kết nối, thay đổi tưởng như chỉ ảnh hưởng một module có thể làm hỏng một luồng nghiệp vụ ở nơi khác.

**Khảo sát hệ thống** là quá trình thu thập và xác minh các kết nối, hợp đồng dữ liệu, nơi lưu trữ và phụ thuộc bên ngoài trước khi lập kế hoạch migration. Kết quả cần trả lời được: thành phần nào giao tiếp với thành phần nào, dùng giao thức gì, dữ liệu có cấu trúc ra sao, ai sở hữu hai đầu kết nối, phiên bản nào đang được dùng và điều gì có thể bị ảnh hưởng khi một phía thay đổi.

## 1. Xác định phạm vi khảo sát

Hãy bắt đầu từ ranh giới của ứng dụng hoặc module đang được migration. Liệt kê các luồng đi vào, đi ra và các luồng nội bộ có thể vượt qua ranh giới đó.

- **Kết nối đi vào (inbound):** hệ thống khác gọi REST API, gửi message, đẩy file, gọi callback hoặc truy cập một giao diện được công bố.
- **Kết nối đi ra (outbound):** ứng dụng gọi dịch vụ khác, truy vấn database, gửi message, ghi file hoặc gọi API của nhà cung cấp.
- **Kết nối nội bộ:** các module trong cùng hệ thống gọi nhau qua interface Java, HTTP nội bộ, message broker hoặc dùng chung database/schema.
- **Luồng dữ liệu lưu trữ:** dữ liệu được ghi hôm nay có thể được đọc bởi phiên bản mới, một batch job, báo cáo hoặc hệ thống khác trong tương lai.
- **Luồng vận hành:** health check, service discovery, cấu hình từ xa, secrets, log forwarding, metrics, tracing và cơ chế triển khai cũng có thể là phụ thuộc cần khảo sát.

Không giới hạn phạm vi ở những lời gọi xuất hiện trực tiếp trong một class. Một luồng có thể đi qua gateway, adapter, queue, scheduled job hoặc nền tảng tích hợp trước khi tới đích. Cần ghi nhận cả các thành phần trung gian có thể biến đổi dữ liệu hoặc quyết định định tuyến.

Phân biệt ba khái niệm sau để tránh nhầm lẫn:

- **Giao thức (protocol):** quy tắc trao đổi thông tin, ví dụ HTTPS, AMQP, JDBC hoặc SFTP.
- **Hợp đồng (contract):** cấu trúc và ý nghĩa của request, response, message, file hoặc dữ liệu lưu trữ.
- **Hệ thống/đầu tích hợp (system/endpoint):** thành phần cụ thể mà ứng dụng kết nối, ví dụ `customer-service`, cụm PostgreSQL hoặc nhà cung cấp thanh toán.

Hai hệ thống có thể cùng dùng HTTPS nhưng có hợp đồng, cách xác thực và chính sách phiên bản hoàn toàn khác nhau. Ghi mỗi thông tin vào đúng nhóm giúp đánh giá migration chính xác hơn.

## 2. Liệt kê các giao thức và cách trao đổi dữ liệu

Một giao thức cho biết hai phía truyền thông tin như thế nào. Khi kiểm kê, hãy ghi cả giao thức ở tầng truyền tải và định dạng payload nếu chúng có thể thay đổi độc lập.

### 2.1. Giao tiếp đồng bộ qua HTTP

Các kiểu tích hợp thường gặp gồm REST/JSON, SOAP/XML, GraphQL và các HTTP API nội bộ. Với mỗi kết nối, cần ghi:

- Địa chỉ logic hoặc tên service, môi trường và đường dẫn endpoint; không đưa token hay thông tin bí mật vào tài liệu.
- HTTP method, path, query parameter, header và content type.
- Cấu trúc request/response, kiểu dữ liệu, trường bắt buộc/tùy chọn, enum, đơn vị và giá trị mặc định.
- Cách xác thực: OAuth2, JWT, API key, mutual TLS, session hoặc cơ chế riêng.
- Timeout, retry, circuit breaker, rate limit, pagination và giới hạn kích thước.
- Ý nghĩa của HTTP status, mã lỗi nghiệp vụ và quy tắc xử lý lỗi.
- Phiên bản API, chính sách deprecation và những consumer đang gọi endpoint.

Ví dụ, hai API đều trả JSON nhưng có thể khác nhau ở cách biểu diễn thời gian (`UTC` hay giờ địa phương), tiền (`decimal` hay số nguyên theo đơn vị nhỏ nhất), trường thiếu (`null` hay không xuất hiện) và cách biểu đạt lỗi. Những khác biệt này có thể làm hỏng consumer dù endpoint vẫn trả HTTP 200.

Với SOAP, ngoài URL và HTTP transport, cần ghi WSDL, XSD, namespace, SOAP version, operation, quy tắc fault và chính sách bảo mật. Nếu client được sinh từ WSDL, cần lưu phiên bản hợp đồng dùng để sinh mã và cách tái sinh stub khi hợp đồng thay đổi.

Với GraphQL, ghi schema, query/mutation được sử dụng, kiểu scalar tùy chỉnh, quy tắc nullability, pagination và cách xử lý field bị loại bỏ. Với API có versioning, cần ghi rõ version nằm trong URL, header hay media type.

### 2.2. Giao tiếp bất đồng bộ qua message

Ứng dụng Java thường trao đổi bất đồng bộ qua Kafka, RabbitMQ, JMS hoặc dịch vụ queue của cloud. Một message broker làm giảm phụ thuộc thời điểm giữa producer và consumer, nhưng không loại bỏ phụ thuộc hợp đồng dữ liệu.

Với từng luồng message, hãy ghi:

- Broker, cluster, virtual host hoặc namespace và môi trường tương ứng.
- Topic, queue, exchange, routing key, subscription hoặc consumer group.
- Producer, consumer và nhóm chịu trách nhiệm vận hành từng đầu.
- Định dạng payload: JSON, Avro, Protobuf, XML, byte array hay định dạng riêng.
- Schema/version, schema registry và quy tắc tương thích nếu có.
- Delivery semantics: at-most-once, at-least-once hoặc cơ chế gần với exactly-once trong phạm vi cụ thể.
- Thứ tự message, partition key, deduplication, idempotency và khả năng xử lý message lặp.
- Retry, backoff, dead-letter queue (DLQ), thời gian lưu message và cách phát lại.
- Chính sách acknowledgement, offset/consumer position và hành vi khi consumer dừng giữa chừng.

Không nên chỉ ghi “ứng dụng dùng Kafka”. Cần biết topic nào mang sự kiện gì, ai phát và ai đọc. Ví dụ, thay đổi tên một trường trong event `OrderCreated` có thể ảnh hưởng nhiều consumer độc lập mà nhóm phát triển producer không trực tiếp quản lý.

Đặc biệt chú ý message có thể tồn tại lâu hơn một lần triển khai. Một consumer mới có thể đọc lại message cũ còn lưu trong broker; một consumer cũ có thể nhận message mới sau khi producer được nâng cấp. Vì vậy, hợp đồng event cần được đánh giá theo cả hai chiều phiên bản.

### 2.3. Trao đổi file và batch

Nhiều tích hợp không dùng API trực tiếp mà trao đổi file qua SFTP, FTPS, thư mục dùng chung, object storage hoặc cơ chế import/export theo lịch. Hãy ghi:

- Kênh truyền và vị trí logic của file; phân biệt môi trường test và production.
- Ai tạo file, ai nhận file, ai xác nhận đã xử lý và ai chịu trách nhiệm khi file bị thiếu.
- Định dạng: CSV, TSV, fixed-width, Excel, XML, JSON, ZIP hoặc định dạng nhị phân.
- Encoding, delimiter, quote/escape, line ending, timezone, định dạng ngày và quy ước decimal.
- Tên file, quy tắc đặt tên, thư mục đến/đi, tần suất, lịch chạy và thời hạn nhận file.
- Quy tắc header, thứ tự cột, trường bắt buộc, mã hóa giá trị và cách biểu diễn bản ghi lỗi.
- Cách phát hiện file hoàn tất, checksum, chữ ký, mã hóa, chống xử lý trùng và lưu trữ sau xử lý.

Ví dụ, một batch job có thể vẫn chạy thành công nhưng dữ liệu bị sai nếu nhà cung cấp đổi `dd/MM/yyyy` thành `MM/dd/yyyy`, đổi encoding sang UTF-8 có BOM hoặc thêm cột vào đầu file trong khi chương trình đọc theo vị trí. Vì vậy, cần kiểm tra hợp đồng file bằng dữ liệu mẫu đại diện, bao gồm file rỗng, ký tự tiếng Việt, giá trị biên và bản ghi lỗi.

### 2.4. Kết nối database và giao thức truy cập dữ liệu

Với database, ghi loại hệ quản trị và phiên bản, driver JDBC, hostname/service name ở dạng cấu hình không chứa bí mật, database/schema, kiểu kết nối, TLS, connection pool và cơ chế failover. Ghi rõ ứng dụng dùng JDBC trực tiếp, Spring JDBC, JPA/Hibernate, MyBatis hay một adapter khác.

Ngoài giao thức JDBC, hợp đồng dữ liệu còn gồm SQL dialect, kiểu dữ liệu, collation, timezone, constraint, transaction isolation, stored procedure, trigger và quyền truy cập. Một phiên bản driver mới hoặc thay đổi database engine có thể ảnh hưởng kiểu dữ liệu, câu SQL, hành vi transaction và hiệu năng.

Nếu ứng dụng kết nối qua proxy, database gateway hoặc read replica, hãy ghi lại các tầng này. Chúng có thể áp dụng giới hạn kết nối, định tuyến đọc/ghi hoặc chính sách timeout khác với database chính.

### 2.5. Các giao tiếp khác

Tùy kiến trúc, hệ thống còn có thể dùng TCP socket, WebSocket, RMI, LDAP, SMTP, DNS, gRPC, multicast, giao thức thiết bị hoặc SDK riêng của nhà cung cấp. Không nên bỏ qua một kết nối chỉ vì nó không phải REST API.

Với mỗi giao thức đặc thù, hãy xác định phiên bản, cơ chế framing/encoding, timeout, xác thực, mã lỗi, giới hạn payload, cách reconnect và khả năng tương thích giữa client/server. Nếu giao tiếp được bọc trong SDK, cần ghi cả phiên bản SDK và phiên bản dịch vụ từ xa mà SDK hỗ trợ.

## 3. Liệt kê dữ liệu lưu trữ

Dữ liệu lưu trữ là một phần của hợp đồng hệ thống. Ứng dụng mới có thể phải đọc dữ liệu được ghi từ nhiều năm trước; rollback có thể khiến phiên bản cũ đọc dữ liệu vừa được phiên bản mới cập nhật. Do đó, khảo sát cần bao quát cả cấu trúc, ý nghĩa, vòng đời và các bên đọc/ghi dữ liệu.

### 3.1. Cơ sở dữ liệu quan hệ

Với mỗi database/schema, ghi:

- Chủ sở hữu dữ liệu và mục đích nghiệp vụ.
- Table, view, materialized view, sequence, function, procedure và trigger liên quan.
- Primary key, foreign key, unique constraint, check constraint và index quan trọng.
- Kiểu cột, độ dài, precision/scale, nullability, default, collation và timezone.
- Quy tắc tạo/cập nhật/xóa, soft delete, audit field và version/optimistic locking.
- Quan hệ giữa bảng, dữ liệu tham chiếu và các giá trị enum được lưu dưới dạng text hoặc số.
- Migration history, công cụ migration và thứ tự áp dụng schema.
- Các ứng dụng, job, báo cáo hoặc người dùng khác cùng đọc/ghi schema.

Không giả định database thuộc riêng một service chỉ vì service đó là nơi tạo bảng ban đầu. Một báo cáo, stored procedure hoặc ứng dụng cũ có thể đang truy cập trực tiếp. Nếu thay đổi tên cột, kiểu dữ liệu hoặc constraint mà không biết các consumer này, migration có thể gây lỗi ngoài phạm vi mã nguồn đang sửa.

### 3.2. NoSQL và dữ liệu bán cấu trúc

Với document database, key-value store, wide-column store hoặc graph database, hãy ghi collection/bucket/key pattern, document shape, partition key, index, TTL, consistency model và cách truy vấn. Xác định trường nào bắt buộc, trường nào có thể vắng mặt, kiểu dữ liệu có thể thay đổi theo thời gian và cách ứng dụng xử lý document cũ.

Nếu dữ liệu có schema linh hoạt, nên thu thập các phiên bản document đang tồn tại từ nhiều thời điểm. Schema trong mã nguồn hiện tại không nhất thiết phản ánh toàn bộ dữ liệu đã lưu trong production.

### 3.3. Cache, search index và dữ liệu dẫn xuất

Cache Redis, local cache, search index, read model, materialized view và bảng tổng hợp thường có thể tái tạo, nhưng vẫn có hợp đồng riêng. Ghi key pattern, cấu trúc value, TTL, namespace, chiến lược invalidation, phiên bản serialization và nguồn dữ liệu để rebuild.

Nếu một phiên bản mới đổi cấu trúc object trong cache, phiên bản cũ có thể không deserialize được trong thời gian hai phiên bản cùng chạy. Có thể cần namespace/version key mới, cơ chế đọc hai định dạng trong thời gian chuyển tiếp hoặc xóa cache có kiểm soát. Không nên xóa cache production tùy tiện khi chưa đánh giá tải rebuild và tác động nghiệp vụ.

Với search index, ghi mapping/analyzer, alias, quy trình reindex và cách đồng bộ dữ liệu. Thay đổi mapping có thể yêu cầu tạo index mới và chuyển alias thay vì sửa trực tiếp index đang dùng.

### 3.4. File, object storage và dữ liệu lưu trữ dài hạn

Ghi bucket/container, prefix, quy tắc đặt tên, metadata, content type, encoding, encryption, retention, lifecycle, versioning và quyền truy cập. Xác định file được tạo bởi ứng dụng nào, ai đọc, có liên kết trong database hay được gửi ra ngoài không.

Các định dạng lưu trữ như PDF, ảnh, CSV, JSON, ZIP hoặc file nhị phân có thể được tiêu thụ bởi một ứng dụng khác nhiều năm sau. Nếu thay đổi cấu trúc hoặc thuật toán mã hóa, cần biết cách đọc lại dữ liệu cũ và cách xử lý file đã phát hành.

### 3.5. Event log, audit, session và dữ liệu vận hành

Khảo sát event store, audit log, lịch sử thay đổi, session, token được lưu, idempotency record, bảng outbox/inbox và dữ liệu phục vụ retry. Các dữ liệu này thường bị bỏ quên vì không nằm trong bảng nghiệp vụ chính, nhưng có thể quyết định khả năng khôi phục và tính đúng đắn sau migration.

Ghi rõ thời gian lưu, quy tắc xóa, định dạng payload, dữ liệu nhạy cảm, quyền truy cập và khả năng replay. Nếu event hoặc audit record được giữ lâu dài, định dạng mới phải có chiến lược đọc dữ liệu cũ.

## 4. Liệt kê các hệ thống bên ngoài

Hệ thống bên ngoài là thành phần nằm ngoài phạm vi triển khai và quyền kiểm soát trực tiếp của module đang khảo sát. Nó có thể do một nhóm nội bộ khác vận hành, một công ty đối tác cung cấp hoặc một nền tảng cloud quản lý.

Những nhóm thường gặp:

- **Danh tính và truy cập:** Identity Provider, OAuth/OIDC, LDAP, SSO, dịch vụ cấp token và quản lý khóa/chứng thư.
- **Thanh toán và tài chính:** cổng thanh toán, ngân hàng, đối soát, hóa đơn điện tử và hệ thống thuế.
- **Thông báo và liên lạc:** SMTP/email, SMS, push notification, chat hoặc dịch vụ gửi thông báo.
- **Dữ liệu và nghiệp vụ:** CRM, ERP, hệ thống kho, vận chuyển, quản lý khách hàng, đối tác và nguồn dữ liệu tham chiếu.
- **Nền tảng kỹ thuật:** cloud storage, secrets manager, service discovery, configuration server, monitoring, logging, tracing và feature flag.
- **Tích hợp dữ liệu:** data warehouse, ETL/ELT, BI, hệ thống báo cáo và nền tảng chia sẻ dữ liệu.
- **Dịch vụ do nhà cung cấp quản lý:** API SaaS, SDK thương mại, license server, dịch vụ xác minh hoặc dịch vụ định danh.

Với mỗi hệ thống, hãy ghi tên và mục đích, chủ sở hữu kỹ thuật/nghiệp vụ, đầu mối hỗ trợ, môi trường, cách kết nối, phiên bản API/SDK, hợp đồng dữ liệu, cơ chế xác thực, quota, SLA, lịch bảo trì và quy trình xử lý sự cố. Ghi thêm vùng mạng, firewall, DNS, proxy, certificate và allowlist nếu chúng ảnh hưởng đến kết nối.

Thông tin bí mật như password, private key, access token và connection string có credential không được chép vào tài liệu khảo sát. Chỉ ghi tên secret/config key, nơi quản lý, người hoặc nhóm chịu trách nhiệm và cách xoay vòng. Khi cần chia sẻ tài liệu, người đọc phải biết nơi tìm cấu hình an toàn mà không nhận được giá trị bí mật.

Đối với hệ thống của bên thứ ba, cần xác định điều gì xảy ra khi dịch vụ chậm, ngừng hoạt động, thay đổi API hoặc hết quota. Ghi timeout, retry, fallback, circuit breaker, giới hạn tần suất và cơ chế đối soát. Một dependency có thể không gây lỗi build nhưng vẫn là rủi ro lớn khi nâng cấp do hợp đồng hoặc chính sách của nhà cung cấp thay đổi độc lập.

## 5. Truy vết từ mã nguồn đến kết nối thực tế trong Java

Mã nguồn giúp tìm các điểm kết nối, nhưng cấu hình runtime và bằng chứng vận hành mới cho biết hệ thống thực sự kết nối tới đâu. Nên kết hợp nhiều nguồn để tránh kết luận từ một dấu vết đơn lẻ.

### 5.1. Kiểm tra dependency và cấu hình

Đọc `build.gradle`, `settings.gradle` hoặc `pom.xml` để tìm driver, client và integration library. Ví dụ:

| Dấu vết trong dự án Java | Khả năng cần khảo sát |
|---|---|
| Spring Web, `RestClient`, `WebClient`, `RestTemplate`, OpenFeign | HTTP API và service discovery |
| `WebServiceTemplate`, SOAP client, WSDL-generated classes | SOAP service và schema XML |
| gRPC stub, Protobuf | gRPC service và message schema |
| `KafkaTemplate`, `@KafkaListener` | Kafka topic, producer và consumer |
| `JmsTemplate`, `@JmsListener`, AMQP client | Queue, exchange và subscription |
| JDBC driver, `DataSource`, `JdbcTemplate` | Database, schema và connection pool |
| JPA/Hibernate, MyBatis | Mapping entity, SQL và schema database |
| Flyway hoặc Liquibase | Lịch sử thay đổi cấu trúc dữ liệu |
| S3/cloud storage SDK, SFTP client | Object storage hoặc trao đổi file |
| SMTP/mail client, LDAP/OIDC/OAuth client | Email, danh tính và truy cập |
| Redis client, search client | Cache hoặc search index |

Dependency chỉ cho biết khả năng tích hợp. Một thư viện có thể nằm trong classpath nhưng không được kích hoạt; ngược lại, kết nối có thể được tạo động qua reflection, plugin hoặc cấu hình bên ngoài. Vì vậy cần lần theo nơi tạo client, nơi inject bean, nơi đọc endpoint và nơi gửi/nhận dữ liệu.

### 5.2. Tìm các điểm vào/ra trong mã nguồn

Tìm controller, listener, scheduled job, command-line runner, adapter, repository, client wrapper và các lớp chuyển đổi dữ liệu. Theo dõi luồng từ điểm bắt đầu tới nơi gọi network hoặc ghi/đọc storage.

Trong Spring Boot, các dấu vết có thể gồm `@RestController`, `@KafkaListener`, `@JmsListener`, `@Scheduled`, `DataSource`, `EntityManager`, `WebClient.Builder`, `RestClient.Builder` và các bean client tự định nghĩa. Không nên chỉ tìm annotation: một adapter có thể gọi một service khác thông qua interface, còn phần triển khai thực tế được chọn theo cấu hình.

Tìm cả cấu hình trong `application.yml`, `application-<profile>.yml`, biến môi trường, ConfigMap, secret reference, deployment manifest và cấu hình của nền tảng. Khi tài liệu hóa, chỉ ghi tên key và nguồn cung cấp; không sao chép giá trị bí mật hoặc dữ liệu production nhạy cảm.

### 5.3. Đối chiếu với môi trường đang chạy

Mã nguồn có thể khác với cấu hình production. Hãy đối chiếu bằng các nguồn được phép truy cập như service registry, API gateway, message broker console, database catalog, cloud resource inventory, deployment manifest, log, metric và distributed trace.

Quan sát runtime giúp xác nhận:

- Endpoint hoặc topic nào thực sự được gọi.
- Tần suất, lưu lượng, kích thước payload và thời điểm cao điểm.
- Consumer/producer nào đang hoạt động.
- Lỗi timeout, retry, DLQ và kết nối thất bại có thường xuyên xảy ra không.
- Có client hoặc ứng dụng ngoài dự kiến đang truy cập database/API không.
- Phiên bản, schema hoặc cấu hình thực tế có khớp với tài liệu hay không.

Không suy ra rằng một kết nối không tồn tại chỉ vì không thấy trong một khoảng log ngắn. Job theo tháng, tác vụ đối soát hoặc luồng chỉ chạy khi có sự kiện hiếm có thể không xuất hiện trong thời gian quan sát. Cần hỏi owner và kiểm tra lịch vận hành, tài liệu hợp đồng cùng lịch sử triển khai.

## 6. Mẫu bảng kiểm kê tích hợp

Mỗi kết nối nên có một dòng hoặc một bản ghi riêng. Nếu một hệ thống có nhiều API, topic hoặc schema với owner và vòng đời khác nhau, hãy tách chúng để đánh giá độc lập.

| Trường | Nội dung cần ghi |
|---|---|
| ID | Mã định danh ổn định cho kết nối hoặc luồng dữ liệu |
| Tên luồng | Tên nghiệp vụ dễ hiểu, ví dụ `order-created-to-fulfillment` |
| Hướng | Inbound, outbound hoặc internal |
| Provider / Consumer | Thành phần tạo và thành phần nhận dữ liệu |
| Hệ thống đích/nguồn | Tên service, database, broker, bucket hoặc vendor |
| Giao thức | HTTPS, JDBC, Kafka, AMQP, SFTP, gRPC... |
| Hợp đồng | Endpoint/topic/table/file format, schema và version |
| Xác thực | OAuth2, mTLS, API key, service account...; không ghi secret |
| Dữ liệu | Trường chính, định dạng, encoding, timezone, phân loại dữ liệu |
| Tần suất/lưu lượng | Real-time, event-driven, hourly, daily, volume ước lượng có nguồn |
| Lỗi và phục hồi | Timeout, retry, DLQ, idempotency, fallback, replay |
| Owner | Nhóm sở hữu mỗi đầu và đầu mối hỗ trợ |
| Môi trường | Dev, test, staging, production và khác biệt cấu hình |
| Bằng chứng | Đường dẫn code/config, contract, dashboard hoặc tài liệu đã xác minh |
| Trạng thái | Đã xác minh, cần xác nhận, không còn sử dụng hoặc chưa rõ |
| Rủi ro migration | Thành phần và phiên bản có thể bị ảnh hưởng |

Ví dụ minh họa một dòng kiểm kê:

| Trường | Giá trị ví dụ |
|---|---|
| ID | `INT-ORDER-01` |
| Tên luồng | Gửi sự kiện đơn hàng đã tạo |
| Hướng | Outbound từ Order Service; inbound tới Fulfillment Service |
| Provider / Consumer | Order Service / Fulfillment Service |
| Hệ thống đích | Kafka cluster, topic `order.created` |
| Giao thức | Kafka, payload JSON |
| Hợp đồng | Event `OrderCreated`, schema version 2 |
| Xác thực | Service account và TLS; secret được quản lý ở secret store |
| Dữ liệu | Order ID, customer ID, currency, total, occurredAt |
| Lỗi và phục hồi | At-least-once, consumer idempotent, retry và DLQ |
| Owner | Nhóm Order / nhóm Fulfillment / nhóm Platform |
| Bằng chứng | Producer class, listener class, topic config và schema registry |
| Trạng thái | Đã xác minh ở staging; cần xác nhận consumer cũ trong production |
| Rủi ro migration | Consumer phiên bản cũ có thể không đọc được trường mới hoặc enum mới |

Các giá trị trên chỉ minh họa cách điền. Khi khảo sát một hệ thống thực tế, mọi giá trị phải được lấy từ code, cấu hình, owner hoặc bằng chứng runtime tương ứng.

## 7. Mẫu kiểm kê dữ liệu lưu trữ

Ngoài bảng tích hợp, nên lập danh mục riêng cho từng kho dữ liệu. Một kho có thể có nhiều bảng hoặc collection, nhưng cần giữ được quan hệ giữa dữ liệu và các ứng dụng sử dụng nó.

| Trường | Câu hỏi cần trả lời |
|---|---|
| Kho dữ liệu | Database, schema, collection, bucket, cache hay index nào? |
| Owner | Nhóm nào chịu trách nhiệm về ý nghĩa và chất lượng dữ liệu? |
| Producer | Thành phần nào tạo hoặc cập nhật dữ liệu? |
| Consumer | Thành phần, batch, báo cáo hoặc đối tác nào đọc dữ liệu? |
| Schema/version | Cấu trúc hiện tại và các phiên bản cũ được nhận diện ra sao? |
| Ràng buộc | Khóa, nullability, unique, precision, timezone, encoding? |
| Vòng đời | Retention, archive, delete, TTL và backup? |
| Migration | Công cụ, lịch sử, thứ tự và khả năng rollback? |
| Dữ liệu lịch sử | Phiên bản mới có đọc được dữ liệu cũ không? |
| Chuyển đổi | Có backfill, dual-write, reindex hoặc transform không? |
| Bảo vệ | Phân loại dữ liệu, encryption, access control và audit? |
| Bằng chứng | DDL, migration script, entity mapping, catalog hoặc truy vấn đã xác minh? |

Đặc biệt ghi nhận các bảng dùng chung và những truy cập ngoài ứng dụng. Database catalog có thể cho biết object tồn tại, nhưng không nhất thiết cho biết đầy đủ ứng dụng nào đang dùng nó. Cần đối chiếu query log, quyền truy cập, source code và owner của các hệ thống liên quan.

## 8. Đánh giá tác động tương thích từ danh mục khảo sát

Sau khi có danh mục, nối mỗi thay đổi dự kiến với các provider, consumer, hợp đồng và dữ liệu có liên quan. Không đánh giá rủi ro chỉ theo số lượng endpoint; một file đối soát chạy mỗi tháng có thể quan trọng hơn một API ít dùng nhưng không có phương án thay thế.

Với từng kết nối, hãy hỏi:

1. Bên nào có thể được nâng cấp trước? Có giai đoạn provider mới chạy cùng consumer cũ hoặc ngược lại không?
2. Hợp đồng có thay đổi tên, kiểu, trường bắt buộc, enum, encoding, đơn vị, timezone hoặc ý nghĩa không?
3. Có dữ liệu cũ, message tồn đọng, file chưa xử lý hoặc cache được tạo bởi phiên bản trước không?
4. Có consumer ngoài phạm vi nhóm đang làm việc không? Ai xác nhận họ đã sẵn sàng?
5. Nếu một phía rollback, dữ liệu đã ghi bởi phiên bản mới có còn đọc được không?
6. Có thể chạy contract test hoặc kiểm thử tích hợp với phiên bản thật ở cả hai phía không?
7. Có cách quan sát và phát hiện lỗi sau triển khai: metric, log, trace, DLQ, reconciliation hay cảnh báo không?

Có thể phân nhóm kết quả để lập kế hoạch:

- **Đã xác minh và tương thích:** có bằng chứng kiểm thử hoặc hợp đồng xác nhận các tổ hợp phiên bản được hỗ trợ.
- **Cần thay đổi phối hợp:** provider và consumer phải được triển khai theo thứ tự hoặc cần giai đoạn chuyển tiếp.
- **Chưa đủ bằng chứng:** chưa rõ owner, consumer, schema hoặc hành vi runtime; cần điều tra trước khi chốt kế hoạch.
- **Không còn sử dụng:** có bằng chứng rằng kết nối đã ngừng hoạt động và owner xác nhận có thể loại bỏ.

Không đánh dấu một kết nối là không sử dụng chỉ vì không tìm thấy trong mã nguồn đang đọc. Cần xác nhận với owner và kiểm tra các luồng theo lịch, luồng hiếm hoặc consumer bên ngoài.

## 9. Quy trình thực hiện khảo sát

Một quy trình thực tế có thể triển khai theo các bước sau:

**Bước 1 — Vẽ ranh giới và luồng nghiệp vụ.** Xác định module, môi trường, các luồng inbound/outbound và các nhóm dữ liệu chính. Bắt đầu từ use case để không bỏ sót kết nối chỉ xuất hiện ở một nhánh nghiệp vụ.

**Bước 2 — Tìm dấu vết trong mã nguồn và dependency.** Liệt kê client, listener, repository, scheduled job, adapter, schema, migration script và cấu hình. Ghi lại file/class hoặc vị trí cụ thể làm bằng chứng.

**Bước 3 — Kiểm tra cấu hình triển khai.** Đối chiếu profile, biến môi trường, secret reference, service discovery, gateway, broker, database và tài nguyên cloud. Không đưa giá trị bí mật vào báo cáo.

**Bước 4 — Xác nhận với owner hai phía.** Hỏi về consumer/producer đang hoạt động, phiên bản hợp đồng, lịch chạy, SLA, quota, thay đổi đã lên kế hoạch và đầu mối hỗ trợ. Mỗi kết nối cần có người xác nhận hoặc trạng thái chưa rõ.

**Bước 5 — Đối chiếu bằng chứng runtime.** Dùng log, metric, trace, broker dashboard, database catalog và lịch batch để xác nhận đường đi thực tế. Ghi rõ thời gian quan sát để tránh nhầm dữ liệu cũ với trạng thái hiện tại.

**Bước 6 — Lập danh mục và ma trận phiên bản.** Gắn provider/consumer, schema, protocol, owner và các phiên bản có thể cùng tồn tại. Đánh dấu những luồng dùng chung hoặc có dữ liệu tồn đọng.

**Bước 7 — Nối danh mục với kế hoạch migration.** Với mỗi thay đổi, xác định kiểm thử cần chạy, thứ tự triển khai, phương án rollback, cách theo dõi và điều kiện hoàn tất. Những khoảng trống thông tin phải được giữ ở trạng thái cần xác minh, không tự suy đoán.

## 10. Những phụ thuộc thường bị bỏ sót

Một số kết nối ít xuất hiện trong luồng xử lý chính nhưng có thể gây sự cố sau migration:

- Scheduled job, cron, batch cuối ngày/tháng và tác vụ chỉ chạy khi có dữ liệu đặc biệt.
- Callback/webhook từ đối tác gọi vào hệ thống sau một khoảng trễ.
- Message cũ đang nằm trong queue hoặc event store và được replay sau triển khai.
- File đã xuất ra đối tác, file đang chờ import hoặc file lưu trữ cần đọc lại.
- Báo cáo, BI, ETL và script vận hành truy cập trực tiếp database.
- Ứng dụng mobile hoặc client desktop có chu kỳ cập nhật chậm hơn backend.
- Cache, session, token, cookie hoặc dữ liệu serialize giữa các phiên bản ứng dụng.
- Certificate, DNS, firewall rule, proxy, allowlist, TLS version và cipher suite.
- Health check, readiness/liveness probe, service discovery và cấu hình autoscaling.
- Monitoring agent, log shipper, tracing exporter và alert rule phụ thuộc tên metric hoặc cấu trúc log.
- License server, dịch vụ xác minh, cổng thanh toán hoặc vendor API có quota và lịch bảo trì riêng.
- Secret rotation, key encryption và dữ liệu được mã hóa bằng khóa cũ.

Danh sách này là gợi ý để đặt câu hỏi, không phải bằng chứng rằng hệ thống đang dùng tất cả các thành phần trên. Chỉ đưa vào danh mục những phụ thuộc được xác minh hoặc đánh dấu rõ là giả thuyết cần kiểm tra.

## 11. Đầu ra cần có trước khi bắt đầu migration

Một cuộc khảo sát hữu ích nên tạo được các đầu ra có thể review và cập nhật:

- **Sơ đồ context/dependency:** thể hiện module đang khảo sát, hệ thống bên ngoài, broker, database và hướng trao đổi dữ liệu.
- **Danh mục tích hợp:** từng endpoint, topic, queue, file flow, database connection và external system, kèm provider/consumer, owner và hợp đồng.
- **Danh mục dữ liệu:** kho lưu trữ, schema, bảng/collection, producer/consumer, retention và lịch sử migration.
- **Bộ hợp đồng mẫu:** OpenAPI/WSDL/Protobuf/Avro schema, JSON mẫu, DDL, file mẫu hoặc event mẫu đã được xác nhận.
- **Ma trận phiên bản:** các tổ hợp provider/consumer và dữ liệu cũ/mới có thể cùng tồn tại.
- **Danh sách khoảng trống và rủi ro:** thông tin chưa xác minh, consumer chưa rõ, thay đổi cần phối hợp và cách kiểm thử.
- **Danh sách owner và nguồn bằng chứng:** ai xác nhận nội dung nào, kiểm tra ở đâu và lần xác minh gần nhất.

Sơ đồ có thể bắt đầu đơn giản:

~~~text
                  +----------------------+
                  |  External Partner    |
                  |  HTTPS / JSON        |
                  +----------+-----------+
                             ^
                             | outbound API
                             |
+----------------------------+-----------------------------+
|                    Java Application                       |
|                                                           |
|  REST Controller ---> Business Service ---> Repository    |
|          |                  |                 |            |
|          |                  +----> Kafka      |            |
|          |                         producer   |            |
|          |                                    v            |
|          |                              +-----------+      |
|          |                              | Database  |      |
|          |                              +-----------+      |
|          |                                                 |
|          +---- inbound API                                 |
+-----------------------------------------------------------+
                             |
                             v
                    +------------------+
                    | Kafka Broker     |
                    | topic: ...       |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    | Other Consumer   |
                    +------------------+
~~~

Sơ đồ thực tế cần ghi tên thành phần, protocol, chiều dữ liệu và owner. Nếu có nhiều consumer, tách từng consumer để thấy rõ tác động của thay đổi schema.

## 12. Tiêu chí hoàn tất khảo sát

Có thể xem khảo sát đủ cơ sở để lập kế hoạch migration khi:

- Các luồng inbound, outbound, internal và dữ liệu lưu trữ quan trọng đã được liệt kê.
- Mỗi kết nối có provider, consumer, protocol, hợp đồng hoặc trạng thái thiếu thông tin rõ ràng.
- Các kho dữ liệu có owner, schema, producer/consumer và chiến lược migration/rollback được xác định.
- Các hệ thống bên ngoài có đầu mối, môi trường, xác thực, giới hạn và cơ chế xử lý sự cố được ghi nhận.
- Danh mục mã nguồn đã được đối chiếu với cấu hình và bằng chứng runtime trong phạm vi có thể truy cập.
- Những consumer ngoài nhóm, tác vụ hiếm, dữ liệu tồn đọng và kết nối dùng chung đã được xem xét.
- Rủi ro tương thích được gắn với các phiên bản cụ thể và có cách kiểm thử hoặc người chịu trách nhiệm xác minh.
- Không có credential hoặc secret value trong tài liệu khảo sát.

Khảo sát hệ thống không phải một bản liệt kê thư viện hay endpoint đơn thuần. Giá trị của nó nằm ở việc làm rõ toàn bộ đường đi của dữ liệu, hợp đồng giữa các thành phần và người chịu trách nhiệm cho từng đầu kết nối. Khi những thông tin này đã được xác minh, nhóm phát triển mới có thể chọn thứ tự nâng cấp, thiết kế giai đoạn chuyển tiếp, kiểm thử các cặp phiên bản và chuẩn bị rollback với rủi ro có thể kiểm soát.
