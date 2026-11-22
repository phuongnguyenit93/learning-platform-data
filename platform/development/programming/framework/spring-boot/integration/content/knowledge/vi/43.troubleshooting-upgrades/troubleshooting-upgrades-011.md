# Rà soát thay đổi phiên bản client, driver, broker và Spring Data

Một ứng dụng Spring Boot có thể biên dịch thành công sau khi nâng cấp dependency nhưng vẫn gặp lỗi ở môi trường thật: client Redis kết nối được nhưng không đọc nổi dữ liệu cache cũ, JDBC driver thay đổi cơ chế xác thực hoặc kiểu dữ liệu trả về, consumer Kafka nhận bản ghi nhưng không giải mã được payload, hoặc Spring Data thay đổi cách suy diễn truy vấn. Ngược lại, broker có thể được nâng cấp độc lập với ứng dụng, làm lộ ra những giả định cũ về protocol, cơ chế ACK, timeout hay metadata.

Vì vậy, **rà soát thay đổi phiên bản** cần đánh giá cả mã nguồn, dependency graph, giao thức trên mạng, dữ liệu đang lưu, trạng thái đang xử lý, cách triển khai và khả năng quay lui. Đây là chủ đề trong chương **Gỡ lỗi và nâng cấp** của module **SPRING_BOOT_INTEGRATION**: tổ chức các luồng tích hợp Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker và adapter Spring Integration, chú trọng cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Lập bản đồ phiên bản của Spring Boot, Spring Framework, Spring Data, Spring Integration, client thư viện, driver, database và message broker trong một dịch vụ.
2. Phân biệt **tương thích nhị phân**, **tương thích API**, **tương thích giao thức**, **tương thích định dạng dữ liệu** và **tương thích hành vi vận hành**.
3. Đọc dependency graph và release notes theo đúng phiên bản đang dùng, nhận diện override làm lệch các thành phần do BOM quản lý.
4. Lập ma trận **client cũ/mới – server cũ/mới**, bao gồm thời gian ứng dụng cũ và mới chạy đồng thời trong rollout.
5. Thiết kế kiểm thử hợp đồng, tích hợp, failover và rollback cho JDBC, Redis, HTTP, Kafka/RabbitMQ/JMS và Spring Data.
6. Đề xuất quy trình nâng cấp theo giai đoạn, tiêu chí dừng và kế hoạch phục hồi an toàn cho dữ liệu, schema, message/offset và cache.

## 2. Nâng phiên bản là thay đổi một đồ thị phụ thuộc

Trong một ứng dụng tích hợp, thường không có duy nhất “phiên bản Redis” hoặc “phiên bản Kafka”. Mỗi kết nối gồm ít nhất ứng dụng, client library, protocol và dịch vụ phía bên kia; ngoài ra còn serialization, TLS, schema và tầng Spring Data/Spring Integration.

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> BOM["Boot-managed dependency set / BOM"]
    BOM --> SD["Spring Data + Spring Data store modules"]
    BOM --> SI["Spring Integration adapters"]
    BOM --> HTTP["HTTP client / Reactor Netty / HttpClient"]
    BOM --> JDBC["JDBC driver / Hibernate / connection pool"]
    BOM --> MSG["Kafka / AMQP / JMS client"]
    SD --> REDIS["Redis client: Lettuce / Jedis"]
    SD --> ORM["JPA / JDBC / repository abstraction"]
    JDBC --> DB[("Database server")]
    REDIS --> RS[("Redis server / Sentinel / Cluster")]
    MSG --> BROKER[("Message broker + topic/queue")]
    HTTP --> API["External HTTP service"]
    SI --> DB
    SI --> BROKER
    SI --> API
~~~

Một dependency được nâng có thể kéo theo nhiều thay đổi khác. Ví dụ đổi Spring Boot minor release thường đổi một số phiên bản Spring Data, Hibernate, driver, Micrometer, Reactor và client được quản lý. Nếu ứng dụng tự override một thư viện con, nó có thể chạy với tổ hợp chưa được kiểm thử chung, dù mỗi thư viện riêng lẻ đều là bản mới.

### 2.1. Sáu lớp tương thích

| Lớp | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| **Biên dịch/API** | Mã nguồn còn dùng được các class, method, annotation và configuration property không? | Package chuyển từ javax sang jakarta; method đã bị bỏ |
| **Nhị phân/runtime** | Phiên bản dependency được tải thật có khớp API mà code đã biên dịch không? | NoSuchMethodError, NoClassDefFoundError, LinkageError |
| **Giao thức/kết nối** | Client mới có thương lượng protocol, TLS, SASL, ACL, authentication với server hiện tại không? | Handshake fail, unsupported protocol, auth refused |
| **Dữ liệu lưu trữ / payload** | Phiên bản mới đọc được dữ liệu cũ, dữ liệu mới có đọc ngược được không? | JSON type metadata đổi, Avro schema incompatible |
| **Ngữ nghĩa xử lý** | Transaction, ACK, retry, timeout, ordering, commit/rollback và dedupe có đổi không? | Giao dịch lặp, consumer commit offset sớm |
| **Vận hành** | Metrics, health probe, topology discovery, deployment, startup và rollback còn hợp lệ không? | Readiness fail sau nâng client; failover kéo dài |

**Kết luận kỹ thuật:** kiểm tra “build xanh” chỉ xác nhận một phần của hai lớp đầu; cần test với server thật và dữ liệu có sẵn để xác nhận những lớp còn lại.

## 3. Bước đầu: lập kiểm kê phiên bản và ranh giới tích hợp

Trước khi nâng cấp, lưu một bản kiểm kê ở **môi trường đang vận hành**, không chỉ dựa trên file cấu hình trong source control.

| Thành phần | Cần thu thập | Nguồn bằng chứng |
|---|---|---|
| Java / runtime | Java version thực tế, vendor, JDK/JRE flags | Runtime logs, image digest, deployment manifest |
| Spring Boot / Framework | Phiên bản plugin, BOM, dependency resolution, profile đang bật | Build file, dependency tree, startup info |
| Spring Data | Release train/module JPA, JDBC, Redis, Mongo nếu có | Effective runtimeClasspath |
| Spring Integration | Core + các adapter HTTP/JDBC/Kafka/AMQP/SFTP/JMS | Dependency tree và bean configuration |
| HTTP client | RestClient/RestTemplate/WebClient, Apache HttpClient/Reactor Netty, TLS config | Client bean, dependency graph |
| DB driver | JDBC driver, connection pool, Hibernate dialect, DB server version | Effective dependency, JDBC metadata, DB query |
| Redis | Lettuce/Jedis, server, Sentinel/Cluster topology, serializer | Client config, INFO, startup logs |
| Broker | Kafka/RabbitMQ/JMS client, broker, wire protocol, group/queue properties | Broker admin API, config, client logs |
| Serialization | Jackson/Avro/Protobuf, schema registry, content type, header conventions | Contract tests, message fixtures |
| Hạ tầng | Container images, TLS certificates, proxies, service mesh, DNS | Deployment/runtime configuration |

Không trích token, password, private key, connection string chứa secret hay dữ liệu khách hàng vào báo cáo phiên bản. Dùng thông tin được chuẩn hoá, tên môi trường và commit/image digest để so sánh.

### 3.1. Cần ghi rõ ai quản lý phiên bản

- **Được Boot/BOM quản lý:** ưu tiên không gắn phiên bản trực tiếp cho từng starter và dependency nếu không có lý do được ghi nhận.
- **Override có chủ đích:** ghi module, phiên bản override, lý do, bằng chứng tương thích và thời hạn gỡ bỏ.
- **Dependency bắc cầu:** vẫn có thể xuất hiện từ một SDK bên ngoài và làm thay đổi classpath.
- **Hạ tầng độc lập:** database hoặc broker do đội nền tảng quản lý có lịch nâng cấp riêng; chỉ nhìn Git của ứng dụng sẽ thiếu bức tranh.

Với nhiều microservice cùng đọc/ghi một topic hoặc một schema DB, phải lập kiểm kê cả những **client khác** chứ không riêng service đang nâng.

## 4. Xem dependency graph và quản lý BOM

Ví dụ với Gradle, trước khi sửa version hãy xem dependency thực sự được chọn:

~~~bash
# Ví dụ lệnh Gradle, chạy tại project tương ứng khi thực hiện nâng cấp.
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-data-redis

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency kafka-clients

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency postgresql
~~~

Với Maven:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Mục tiêu của các lệnh là phát hiện:

- Có **hai nhánh dependency** yêu cầu cùng artifact ở các version khác nhau không?
- Runtime chọn version nào và chọn vì quy tắc nào (BOM, constraint, override, nearest definition)?
- Có client đời cũ được SDK khác kéo vào, làm xuất hiện duplicate class hoặc API cũ không?
- Có một **Spring Data module** được nâng độc lập trong khi Spring Framework/Spring Data Commons vẫn ở release train khác không?
- Có nhiều logging, JSON, Netty, Jackson, SSL provider hoặc Jakarta/Javax API không tương thích không?

Đối với Gradle/Maven, nên giữ log dependency resolution của **trước** và **sau** thay đổi. So sánh bản chọn ở runtimeClasspath, không chỉ bản mà build file khai báo.

### 4.1. Giữ các dependency liên quan cùng bộ phiên bản

Trong Spring Boot, starters và dependency management cung cấp bộ version đã được kiểm thử phối hợp. Ví dụ một build file có thể để BOM quản lý phiên bản:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.integration:spring-integration-core'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là minh hoạ cấu trúc Gradle, dùng **placeholder** cho version chứ không phải file có thể chạy nguyên văn. Với Spring Boot Gradle plugin và cơ chế quản lý dependency đang sử dụng, hãy đối chiếu hướng dẫn plugin phù hợp; có dự án dùng BOM với Gradle platform mà không dùng dependency-management plugin.

**Không nâng riêng Spring Data Commons** chỉ để “lấy version mới nhất” nếu chưa kiểm tra sự tương thích của toàn bộ Spring Data release train và các store module. Với dependency bị ép version do CVE, cần xác định những API/behavior liên quan, chạy test và lưu lý do override để tránh lâu dài bỏ quên.

### 4.2. Kiểm tra startup sau nâng cấp

Một lỗi startup là dấu hiệu có ích:

| Triệu chứng | Hướng điều tra |
|---|---|
| **NoSuchMethodError** | Thư viện runtime khác phiên bản kỳ vọng; xem dependencyInsight |
| **ClassNotFoundException / NoClassDefFoundError** | Chưa có dependency, class chuyển package hoặc binary conflict |
| **BeanCreationException** | Property cũ, bean cấu hình thay đổi, driver/health dependency lỗi |
| **UnsatisfiedDependencyException** | Auto-configuration bị thay đổi hoặc component không còn được tạo |
| **UnsupportedClassVersionError** | Bytecode được biên dịch cho Java mới hơn runtime |
| **ClassCastException** khi deserialize | Serializer/type metadata hoặc package tên class đã thay |
| **Authentication/SSL handshake failure** | TLS/cipher/cert/credential/protocol hoặc server policy thay đổi |

Không sửa triệu chứng bằng cách tắt mọi auto-configuration hoặc bỏ health check. Tìm root cause đầu tiên trong exception chain, xác định dependency thực sự được chọn và thử lại bằng một kịch bản tái hiện nhỏ.

## 5. Release notes và ma trận tương thích: kiểm tra đúng chiều

Một đợt nâng cấp có thể theo một trong hai hướng:

- **Nâng client trước:** ứng dụng mới nói chuyện với server/broker cũ.
- **Nâng server trước:** ứng dụng cũ nói chuyện với server/broker mới.

Cả hai hướng phải được đánh giá vì rolling deployment tạo thời gian **client cũ và client mới cùng tồn tại**.

| Ma trận | Server/broker cũ | Server/broker mới |
|---|---|---|
| **Client cũ** | Baseline đang hoạt động | Phải kiểm tra nếu nâng hạ tầng trước |
| **Client mới** | Phải kiểm tra nếu nâng ứng dụng trước | Trạng thái đích sau nâng cấp |

Ma trận này phải mở rộng thêm **producer cũ/mới, consumer cũ/mới, schema payload cũ/mới**, bởi một broker chuyển đổi thành công vẫn có thể truyền dữ liệu mà service cũ không đọc được.

### 5.1. Đọc tài liệu nào?

Với mỗi cặp thành phần được thay:

1. Trang **system requirements** hoặc **supported versions** của đúng release.
2. **Migration/upgrade guide** của version nguồn đến version đích, kể cả các bản trung gian phải đi qua.
3. **Release notes/changelog**, breaking changes, deprecation và security changes.
4. Tài liệu **protocol/compatibility** của server/broker, wire-format, client authentication.
5. Các thay đổi **default configuration**: timeout, retry, serializer, pooling, auto-create, consumer ACK, TLS, metrics.
6. Quy trình **rollback/rolling upgrade** và điều kiện không quay lại được, nhất là với dữ liệu/schema hoặc feature level của broker.

Không suy rằng mọi client cùng major mới đều tương thích với mọi server cùng major cũ. Chính sách tương thích khác nhau giữa Kafka, PostgreSQL, Redis, RabbitMQ và các driver. **Phiên bản hỗ trợ phải được xác nhận từ tài liệu của release cụ thể trước khi triển khai**; các ví dụ trong bài này không thay thế release matrix.

## 6. Rà soát Spring Boot, Spring Framework, Spring Data và Spring Integration

Một thay đổi Spring Boot có thể kéo theo thay đổi API và implementation trong các tầng framework liên quan.

### 6.1. Spring Data repositories và query semantics

Kiểm tra các điểm:

- **Repository method derivation:** tên method, cách suy diễn trường/quan hệ, sorting, pagination, null handling.
- **Custom queries:** JPQL/SQL native, tên parameter, projection, constructor expressions và query validation.
- **Transaction:** readOnly, propagation, isolation, lazy loading, thay đổi flush hoặc commit behavior.
- **Data conversion:** enum mapping, UUID, Instant/LocalDateTime, numeric precision/scale và converter tùy chỉnh.
- **Optimistic locking:** version field và hành vi khi update version cũ.
- **JPA provider:** Spring Data JPA thường làm việc cùng Hibernate; một thay đổi Hibernate/dialect có thể làm SQL sinh ra khác dù repository method giữ nguyên.
- **Schema migration:** Flyway/Liquibase và thứ tự chạy khi context start.

**Điểm kiểm thử trọng yếu:** so sánh **dữ liệu và transaction effect**, không chỉ assert repository method được gọi. Một derived query chuyển cách bind value có thể trả tập kết quả khác nhưng không làm ứng dụng crash.

### 6.2. Spring Data Redis và client Lettuce/Jedis

Một thay đổi Spring Data Redis/client có thể ảnh hưởng:

- Serializer key/value/hash, metadata kiểu Java hoặc JSON polymorphism.
- Kiểu trả về của operation, transaction pipeline và conversion.
- Timeout, reconnect, connection pooling, topology refresh của Sentinel/Cluster.
- Redis protocol (RESP), ACL/TLS, hostname được Cluster công bố, redirection MOVED/ASK.
- Redis cache TTL, prefix, key naming và invalidation.

Nếu cache dùng **JDK serialization** hoặc serializer chứa tên class, đổi package/class có thể khiến dữ liệu cũ không đọc được. Nếu Redis chứa **session, lock, idempotency marker hoặc state quan trọng**, không được coi việc flush cache là giải pháp nâng cấp mặc định.

### 6.3. Spring Integration adapters

Với adapter HTTP, JDBC, Kafka, AMQP, JMS, Redis, SFTP hoặc file inbound:

- Kiểm tra bean/DSL API và factory signature trong release mới.
- Giữ nguyên hợp đồng channel: **DirectChannel** đồng bộ hay **ExecutorChannel** bất đồng bộ.
- Xác minh **poller**, scheduling, maxMessagesPerPoll, timeout và errorChannel.
- Kiểm tra transaction advice, ACK boundary, retry, dead-letter/recoverer.
- Đảm bảo headers, payload conversion, charset/content-type và correlation ID không thay đổi.
- Nếu đã cấu hình **idempotent receiver** hoặc metadata store, xác minh format/key của state và TTL tương thích.

Một adapter mới nhận thông điệp thành công nhưng thay đổi thời điểm ACK có thể tạo rủi ro mất/lặp dữ liệu; chỉ test một happy path sẽ bỏ lỡ.

### 6.4. Java và namespace Jakarta

Khi đi qua ranh giới major release của Spring Boot/Spring Framework, kiểm tra yêu cầu Java runtime, thư viện bên thứ ba, servlet/JPA/JMS API và namespace **javax.** / **jakarta.**. Ví dụ hệ Spring Boot 3 dùng các Jakarta EE API hiện đại; code hoặc thư viện cũ còn bám vào một số **javax** API có thể cần thay đổi.

Không thay toàn bộ **javax.*** bằng **jakarta.*** một cách máy móc: một số package Java SE như **javax.net** vẫn hợp lệ. Chỉ migrate API thuộc ranh giới chuyển namespace được ghi trong tài liệu tương ứng.

## 7. Driver JDBC và database: kiểm tra cả giao dịch, kiểu dữ liệu và TLS

JDBC driver là lớp chuyển yêu cầu SQL/connection của Java sang giao thức database. Một thay đổi driver có thể hiện ra ở runtime dù entity và repository không đổi.

| Nhóm | Vấn đề cần kiểm thử | Kết quả sai thường gặp |
|---|---|---|
| **Kết nối** | JDBC URL, DNS, socket timeout, TLS, authentication mechanism | Chạy local được, production handshake fail |
| **Pool** | Validation query, maxLifetime/idleTimeout, leak detection, driver socket timeout | Pool cạn, thread treo, reconnect không ổn |
| **Kiểu dữ liệu** | UUID, JSON/JSONB, timezone, timestamp, decimal precision, enum, bytea | Lệch giờ, mất precision, mapping sai |
| **SQL behavior** | Prepared statements, batch inserts, generated keys, fetch size, cursor | Duplicate key, memory spike, query regression |
| **Transaction** | Isolation, autocommit, savepoint, rollback, commit timeout | Retry sai hoặc commit không rõ trạng thái |
| **Metadata/schema** | Dialect, SQL generation, migration ordering, identifier quoting | Query mới không tương thích schema |
| **Quan sát** | Error code, SQLState, exception translation, metrics | Retry policy không nhận diện đúng loại lỗi |

### 7.1. Exception classification có thể cần cập nhật

Trong Spring, driver exception thường được dịch sang nhóm **DataAccessException**. Nhưng lỗi cụ thể từ SQLState/vendor code và khả năng retry cần được kiểm tra sau upgrade.

Ví dụ:

- **Deadlock/lock timeout** có thể retry trong một số transaction idempotent.
- **Unique constraint violation** có thể là duplicate nghiệp vụ đã biết hoặc conflict thực sự; không retry mù.
- **Connection reset lúc COMMIT** tạo trạng thái kết quả chưa xác định; không giả định transaction rollback.
- **Authentication failure** và **missing column** là lỗi cấu hình/schema, không nên retry liên tục.

Cần giữ test cho mapping exception của những tình huống thực sự tồn tại trong hệ thống. Không dựa vào việc tên class exception giữ nguyên để kết luận các code/causes của driver luôn giống nhau.

### 7.2. Schema phải tương thích trong rolling deploy

Nếu application cũ và mới cùng truy cập DB một thời gian, migration nên theo hướng **expand → migrate → contract**:

~~~mermaid
flowchart LR
    A["1. Expand: thêm cột/bảng/constraint tương thích ngược"] --> B["2. Deploy app hỗ trợ schema cũ + mới"]
    B --> C["3. Backfill/chuyển dữ liệu có kiểm soát"]
    C --> D["4. Chuyển read/write sang schema mới"]
    D --> E["5. Verify không còn client cũ"]
    E --> F["6. Contract: xóa cấu trúc cũ ở release sau"]
~~~

Không thay kiểu/xóa cột mà bản ứng dụng cũ còn đọc hoặc ghi nếu muốn rollback an toàn. Trước khi bật constraint mới, backfill và kiểm tra dữ liệu hiện có. Với bảng lớn, cần đánh giá lock, thời gian migration, index build và ảnh hưởng latency; thay đổi driver không làm rủi ro schema biến mất.

## 8. HTTP client: từ request có thể phát đến phản hồi đã mất

Một thay đổi **RestTemplate**, **RestClient**, **WebClient**, Apache HttpClient, Reactor Netty hoặc HTTP client SDK có thể kéo theo:

- Default connect/read/response timeout và khả năng đặt tổng deadline.
- Redirect, proxy, TLS truststore, hostname verification, DNS caching.
- Connection pooling, keep-alive, idle eviction, HTTP/1.1 hoặc HTTP/2 negotiation.
- Cách serialize JSON, charset, compression và content negotiation.
- Cách mapping HTTP 4xx/5xx/429 thành exception và trigger retry.
- Header propagation: Authorization, Idempotency-Key, traceparent, correlation ID.
- Retry tự động của SDK hoặc load balancer; có thể chồng lên retry tại application.

**Timeout không đồng nghĩa thất bại ở server.** Nếu HTTP POST có tác dụng phụ bị timeout sau khi server commit, ứng dụng phải tra cứu theo request ID hoặc dùng idempotency key trước khi lặp lại. Đợt nâng client đôi khi làm thay đổi tần suất timeout, dễ khiến duplicate tăng dù logic nghiệp vụ không đổi.

### 8.1. Hợp đồng HTTP cần được giữ

| Kiểm thử | Điều cần xác minh |
|---|---|
| URL, method, query | Không thay encode path, query parameter, redirect ngoài ý muốn |
| Header | Authorization, content type, idempotency key, correlation ID |
| Payload | JSON field names, null/default, numeric precision, enum, date/time |
| Response mapping | 2xx/4xx/5xx, response body, error handling |
| Timeout/retry | Tổng số request tới server, backoff, deadline và retry safety |
| TLS/proxy | Hostname verification, certificate trust, proxy và DNS trong hạ tầng thật |
| Streaming | Body lớn không bị giữ toàn bộ trong RAM, đóng stream khi lỗi |

Dùng HTTP stub như WireMock/MockWebServer để kiểm tra request contract, và ít nhất một integration test với server/proxy thật hoặc mô phỏng network failure để kiểm tra timeout, retry và connection reuse.

## 9. Redis server/client: tương thích dữ liệu và failover

Redis thường bị coi là cache “có thể xóa sạch”. Điều này chỉ đúng khi Redis thực sự là bản sao không quan trọng và ứng dụng chấp nhận tải fallback. Redis cũng có thể chứa session, distributed lock, rate-limit state, idempotency token hoặc Redis Streams.

### 9.1. Các câu hỏi khi nâng Redis/Lettuce/Jedis

1. Client mới có kết nối được **server hiện tại** với TLS, ACL, RESP và cấu hình cluster hay không?
2. Client cũ có kết nối được **server mới** trong giai đoạn rolling upgrade hay không?
3. Serializer mới có đọc được key/value/hash đang tồn tại không? Ngược lại, app cũ có đọc được dữ liệu do app mới ghi không?
4. Key prefix, TTL, cache name, session ID, lock token và idempotency marker có đổi không?
5. Trong Sentinel/Cluster failover, client có cập nhật địa chỉ primary/slot mapping và xử lý redirection như trước không?
6. Nếu có Redis Streams, consumer group, pending entries, ACK, replay và retention có còn đúng hợp đồng không?

### 9.2. Test dữ liệu đã được ghi từ phiên bản cũ

Một **wire-format compatibility test** dùng fixture bytes được tạo bởi serializer cũ và đã được lưu làm contract fixture trong repository test:

~~~java
// Ví dụ ý tưởng: đọc bytes đã lưu từ phiên bản cũ trong test resources.
@Test
void newSerializerCanReadLegacyValue() throws Exception {
    byte[] legacyBytes;
    try (var stream = getClass().getResourceAsStream(
            "/contracts/redis/order-v1.bin")) {
        assertThat(stream).isNotNull();
        legacyBytes = stream.readAllBytes();
    }

    Object decoded = redisTemplate.getValueSerializer()
            .deserialize(legacyBytes);

    assertThat(decoded).isInstanceOf(OrderSnapshot.class);
    assertThat(((OrderSnapshot) decoded).status()).isEqualTo("PAID");
}
~~~

Đây là **đoạn mã minh họa**: **redisTemplate**, **OrderSnapshot**, AssertJ và fixture bytes phải được triển khai trong project. Không tạo bytes fixture bằng serializer mới rồi dùng nó để kiểm tra khả năng đọc dữ liệu cũ; như thế không chứng minh tương thích ngược.

Với cache mất hiệu lực có thể tái dựng, một migration có thể đổi prefix/namespace, chạy song song và làm ấm cache mới. Với session/idempotency/lock, cần kế hoạch nâng cấp dữ liệu và tránh trường hợp hai ứng dụng cũ/mới không hiểu trạng thái của nhau.

### 9.3. Failover và timeouts

Trong Redis Cluster, client phải xử lý thay đổi topology và các phản hồi chuyển hướng. Trong Redis Sentinel, client cần khám phá primary mới; command gửi trong quá trình failover có thể timeout. Không coi retry tự động là an toàn cho **INCR, LPUSH, XADD** hoặc thao tác giữ lock có side effect: lệnh có thể đã thực hiện nhưng phản hồi mất.

**Kiểm thử sau upgrade** nên gây disconnect/failover trong môi trường test tương ứng, đo thời gian phục hồi, số lỗi/timeout và khả năng đọc lại dữ liệu cũ. Một container Redis standalone không thể thay thế test Sentinel/Cluster nếu production dùng topology đó.

## 10. Kafka: client–broker, schema và consumer group

Nâng Kafka client hoặc broker tác động tới protocol negotiation, security, producer delivery, consumer assignment, offset và transaction/idempotence. Kafka có cơ chế tương thích client/broker theo chính sách của từng release; **không suy luận version support chỉ từ tên phiên bản**.

| Phần | Cần kiểm tra |
|---|---|
| **Client ↔ broker** | Version support, API versions negotiation, SASL/TLS, endpoints, ACL |
| **Producer** | Acks, retries, idempotence, max.in.flight, batching, compression, transaction ID |
| **Consumer** | Group protocol/assignment, rebalance, max.poll.interval, auto/manual commit, offset reset |
| **Schema** | Avro/Protobuf/JSON Schema compatibility, schema registry, nullable fields, enum evolution |
| **Kafka Streams/transactions** | Changelog/state store, application ID, transaction state và recovery |
| **Operations** | Topic config, retention, compaction, feature level, rolling broker upgrade/rollback |
| **Spring Kafka** | Listener container, error handler, recoverer/DLT, ack mode, message converter |

### 10.1. Producer mới và consumer cũ phải đồng tồn tại

Trong rolling deploy có thể xảy ra:

- Producer mới viết payload với field mới; consumer cũ vẫn phải giải mã được.
- Consumer mới đọc backlog nhiều ngày do producer cũ phát; schema mới phải xử lý dạng cũ.
- Một consumer instance mới join chung group với instance cũ, có thể gây rebalance hoặc thay đổi phân phối partition.
- Các message đang retry/DLT mang header từ phiên bản cũ; listener mới phải hiểu hoặc có cách cách ly.

**Chỉ thử producer mới với consumer mới là chưa đủ.** Test cả hai chiều dữ liệu ở ranh giới phiên bản và giữ một topic có bản tin lịch sử để thử replay.

### 10.2. Offset và ACK là điểm không được bỏ qua

Nếu consumer được refactor sang chế độ ACK khác, việc commit offset **trước khi side effect DB commit** có thể làm mất message khi process crash. Nếu commit offset sau DB commit, message có thể redeliver khi ACK mất; downstream cần idempotent.

Tình huống thử nghiệm:

~~~mermaid
sequenceDiagram
    participant K as Kafka Broker
    participant C as Spring Kafka Consumer
    participant D as Business DB
    K->>C: Deliver event E
    C->>D: Persist business effect
    D-->>C: Commit OK
    C--xK: Offset commit lost / process crash
    K->>C: Redeliver event E
    C->>D: Apply with unique eventId
    D-->>C: Already processed, no duplicate effect
    C->>K: Commit offset
~~~

Trong Kafka, các cấu hình transaction và exactly-once processing có phạm vi cụ thể. Không xem việc dùng Kafka transactions là bảo đảm giao dịch nguyên tử với database ngoài Kafka. Với DB, dùng unique key/inbox/outbox và idempotency để chứng minh kết quả nghiệp vụ.

### 10.3. Nâng broker có quy trình riêng

Với cluster Kafka, cần đọc hướng dẫn cụ thể về rolling restart, quorum/controller, feature level và khả năng downgrade. Thay đổi metadata/feature level có thể hạn chế rollback dù binary cũ vẫn có thể khởi động. Không tùy tiện nâng nhiều broker và bật feature mới đồng thời khi chưa có bằng chứng và phương án backup/recovery.

Đo ít nhất consumer lag, rebalance count/duration, produce/consume errors, throughput, p95/p99 latency, under-replicated partitions và tình trạng DLT trước, trong, sau nâng cấp.

## 11. RabbitMQ, AMQP, JMS và broker khác

Với RabbitMQ hoặc broker JMS, cần kiểm tra độc lập **client library**, **adapter của Spring**, **server/broker**, **protocol** và **topology**.

### 11.1. RabbitMQ / AMQP

- Kiểm tra client Java, Spring AMQP, Spring Integration AMQP adapter và RabbitMQ server theo compatibility matrix.
- Đối chiếu **queue/exchange/binding declarations**, arguments, durability, TTL, dead-letter và quorum/classic queue behavior đang dùng.
- Kiểm tra **prefetch**, manual/auto ACK, publisher confirms, returns, retry/requeue, consumer concurrency.
- Đọc rõ cơ chế recovery sau disconnect, heartbeats, connection/channel limits và broker alarms.
- Thử publish timeout sau khi broker nhận message; không retry với giả định message chắc chắn chưa tồn tại.
- Giữ consumer cũ đọc được payload do producer mới phát và ngược lại.

Một lỗi thường gặp là **PRECONDITION_FAILED** khi ứng dụng mới khai báo queue cùng tên với arguments khác queue đã tồn tại. Đây là thay đổi topology/hợp đồng, không phải lỗi transient để retry vô hạn.

### 11.2. JMS và nhà cung cấp

Với JMS, ngoài broker compatibility còn có vấn đề chuyển API giữa **javax.jms** và **jakarta.jms** khi thay stack/framework. Kiểm tra driver JMS provider, listener container, session transaction, acknowledgment, redelivery policy và DLQ. Không giả định nâng một thư viện API sẽ tự chuyển driver bên dưới sang namespace mới.

Cũng cần thử phục hồi session sau failover; một consumer đã nhận message nhưng chưa ACK có thể nhận lại, vì vậy handler phải đủ idempotent.

## 12. Payload và schema: tương thích dữ liệu quan trọng hơn version string

Nhiều sự cố sau nâng cấp không bắt nguồn từ protocol mà từ việc message/data format đổi trong khi hàng triệu bản ghi cũ vẫn tồn tại.

### 12.1. Ma trận đọc–ghi định dạng

| Writer | Reader | Cần kiểm tra |
|---|---|---|
| **Producer cũ** | **Consumer mới** | Consumer mới đọc được backlog, null/enum/default và schema cũ |
| **Producer mới** | **Consumer cũ** | Consumer cũ bỏ qua field mới hoặc báo lỗi theo hợp đồng |
| **Cache writer cũ** | **Cache reader mới** | Serialization, key prefix, value type/TTL |
| **Cache writer mới** | **Cache reader cũ** | Rollback ứng dụng có đọc được state do bản mới ghi không |
| **DB writer cũ** | **DB reader mới** | New schema vẫn hiểu các row cũ |
| **DB writer mới** | **DB reader cũ** | Rolling deployment và rollback không hỏng vì column/enum mới |

**Tương thích ngược** và **tương thích xuôi** phải được định nghĩa theo vai trò reader/writer. Không mặc nhiên một schema có thể thêm trường thì mọi client cũ sẽ chấp nhận: có consumer deserialize strict, validation unknown-field hoặc enum switch không có default.

### 12.2. Những thay đổi thường gây đứt hợp đồng

- Đổi JSON field name hoặc nesting.
- Đổi **int64** sang **string**, **decimal** sang floating point làm mất chính xác.
- Đổi timestamp từ UTC sang local timezone hoặc đổi format.
- Thêm enum value nhưng consumer cũ không có nhánh xử lý.
- Thay content-type/header type identifier mà converter dùng để giải mã.
- Bỏ field bắt buộc, sửa ý nghĩa semantic của cùng tên field.
- Thay serializer Redis có metadata Java class name.
- Đổi chính sách null, empty, default và version field.

Nếu dùng schema registry, phải kiểm tra compatibility rule thực tế của subject/version; một rule cấu hình đúng vẫn cần consumer contract test để bắt lỗi mapping nghiệp vụ.

### 12.3. Quy trình thay hợp đồng an toàn

1. Viết fixture hoặc snapshot từ **phiên bản cũ** trước khi nâng.
2. Test reader mới trên dữ liệu cũ.
3. Test reader cũ trên dữ liệu mà writer mới tạo, nếu có overlap/rollback.
4. Sửa writer theo hướng hỗ trợ song song (dual-read/dual-write nếu cần và có kế hoạch kiểm soát).
5. Backfill có checkpoint và idempotency; kiểm tra số bản ghi/đối soát.
6. Chỉ bỏ schema/field cũ khi chắc chắn không còn consumer hoặc dữ liệu cần đọc theo format đó.

## 13. Cấu hình và default behavior: phần dễ bị bỏ sót

Thay đổi phiên bản có thể giữ nguyên class/API nhưng đổi giá trị mặc định. Cần so sánh **effective configuration** trước và sau, không chỉ grep những property có trong application.yml.

| Hạng mục | Khả năng thay đổi | Kịch bản cần test |
|---|---|---|
| Timeout | Connect, socket, command, request, idle | Dependency chậm 2–5 lần baseline |
| Retry | Attempts, backoff, jitter, loại exception | HTTP 429/503, DB deadlock, timeout sau side effect |
| Pool | Min/max idle, max lifetime, queue | Tải tăng, dependency mất rồi phục hồi |
| Serialization | Jackson naming/typing, date/time | Round-trip và đọc fixture version cũ |
| Error handling | Exception mapping, DLQ, recoverer | Bad record, poison message, failed ACK |
| Health/readiness | Thành phần nào được tính bắt buộc | Redis cache down nhưng DB vẫn hoạt động; broker bắt buộc down |
| TLS/auth | Protocol/cipher, CA, credentials | Certificate rollover, ACL deny, SASL failure |
| Metrics/tracing | Meter name, tags, trace propagation | Dashboard/alerts còn phát hiện được lỗi |
| Scheduler/consumer | Thread count, prefetch, poll interval, rebalance | Dưới tải và khi rolling deploy |

Khi sử dụng Spring Boot Actuator, kiểm tra endpoint health/readiness thể hiện **khả năng phục vụ hợp đồng nghiệp vụ**. Không tự tạo vòng lặp restart toàn bộ pod vì một cache tùy chọn tạm thời không phản hồi.

## 14. Kiểm thử nâng cấp theo tầng

Một kế hoạch thử nghiệm nên tăng dần mức độ thực tế và chi phí:

~~~mermaid
flowchart TD
    A["Dependency diff + compile + static checks"] --> B["Unit tests: mapping, validators, exception classification"]
    B --> C["Contract tests: old/new payload, SQL, HTTP"]
    C --> D["Integration tests với DB/Redis/broker versions tương ứng"]
    D --> E["Failure tests: timeout, failover, retry, restart"]
    E --> F["Staging shadow/canary + đo SLO"]
    F --> G["Rollout có giám sát + rollback gate"]
~~~

### 14.1. Ma trận kiểm thử tối thiểu

| Tình huống | Test | Bằng chứng cần thu |
|---|---|---|
| Client mới → server cũ | Kết nối + thao tác đọc/ghi + lỗi | Protocol, TLS, latency, correctness |
| Client cũ → server mới | Kết nối + thao tác trọng yếu | Rollout hạ tầng không phá dịch vụ cũ |
| Producer cũ → consumer mới | Replay message lịch sử | Payload deserialize và outcome DB đúng |
| Producer mới → consumer cũ | Publish schema mới trong overlap | Consumer cũ xử lý hoặc từ chối có kiểm soát |
| DB schema mới → app cũ | Đọc/ghi trong giai đoạn expand | Rollback app vẫn có thể hoạt động |
| Cache cũ → app mới | Đọc key/value thực đã snapshot | TTL/type/serializer tương thích |
| App mới → cache cũ sau rollback | Chạy bản cũ trên state do bản mới ghi | Không crash, không bỏ sót session/state |
| Broker/client failover | Ngắt kết nối/restart node test | Retry hữu hạn, không mất/nhân đôi side effect |
| API timeout sau commit | Stub mất response sau side effect | Idempotency/đối soát tránh duplicate |
| Lô dữ liệu lớn | Tải, cold cache, nhiều partition | Throughput/lag/p99 trong SLO |

Có thể dùng **Testcontainers** với image version được chỉ định cho DB/Redis/broker; nhưng chỉ một container Kafka hoặc Redis standalone chưa đủ để chứng minh failover cluster thực. Những tình huống liên quan phân vùng mạng, leader election và rolling upgrade cần topology thử nghiệm phù hợp.

### 14.2. Một số assertion quan trọng

Một test Kafka/HTTP/DB không nên chỉ assert “không ném exception”. Cần kiểm tra:

- **Dữ liệu đích có đúng một tác động nghiệp vụ** theo event ID/idempotency key dù message redelivery hoặc HTTP retry.
- **Transaction rollback** những resource thuộc cùng transaction, và side effect ngoài transaction được đối soát.
- **Không mất thứ tự quan trọng** theo business key/version khi consumer group rebalance.
- **Checkpoint/offset** không tiến trước khi bản ghi bắt buộc đã được commit.
- **Cache cũ** có thể đọc được khi upgrade; dữ liệu cache mới không phá rollback nếu có yêu cầu đọc ngược.
- **Health/metrics/trace** phản ánh lỗi tương tự baseline và alert còn hoạt động.

### 14.3. Kiểm thử so sánh hai phiên bản

Khi có thể, chạy cùng bộ input với bản hiện hành và bản mới trong môi trường độc lập. So sánh:

- JSON/HTTP response theo contract, không so dữ liệu ngẫu nhiên như UUID/timestamp nếu không chuẩn hoá.
- SQL row count, unique key, version và transaction effect.
- Event payload, headers, partition key, ordering và DLQ.
- Latency percentiles, throughput, thread/connection count và memory.
- Phân phối exception, retry count và hành vi recovery.

Nếu chạy **shadow traffic**, yêu cầu side effect được vô hiệu hóa hoặc ghi sang sink riêng; không replay request tạo thanh toán/đơn hàng thật vào môi trường production.

## 15. Kế hoạch nâng cấp theo giai đoạn và khả năng quay lui

Một đợt nâng cấp cần có **người chịu trách nhiệm**, **tiêu chí chấp nhận**, **điểm dừng** và **đường rollback** đã kiểm chứng. Với dependency ràng buộc chặt, thay nhiều thành phần cùng lúc làm khó xác định nguyên nhân.

### 15.1. Các giai đoạn

1. **Baseline:** ghi dependency graph, image digest, SLO, error rate, p95/p99, consumer lag, DB pool, Redis failover và số liệu idempotency/duplicate hiện hành.
2. **Phân tích thay đổi:** đọc release notes, breaking changes, support matrix và security advisories; ghi mục tiêu, mức độ bắt buộc, feature đã deprecated và risk owner.
3. **Thử nghiệm local/CI:** nâng trong nhánh riêng; chạy compile, contract test, integration test với client cũ/mới và server cũ/mới.
4. **Staging tương đương:** thử rolling deploy, reboot/reconnect, backlog replay, schema migration, rollback ứng dụng với dữ liệu do bản mới ghi.
5. **Canary:** triển khai vào tỷ lệ nhỏ có kiểm soát; so error/latency/lag với baseline theo cùng loại traffic.
6. **Rollout tăng dần:** mở thêm instance/partition theo năng lực giám sát; giữ phiên bản cũ còn hoạt động nếu tương thích.
7. **Hoàn tất:** xác nhận dữ liệu không mất/trùng ngoài hợp đồng, dashboard/alert, consumer lag, transaction success; cập nhật tài liệu/runbook.
8. **Contract cleanup:** chỉ xoá code/schema tương thích cũ sau khi không còn client cũ và đường rollback không cần dữ liệu ấy.

**Không nên** vừa nâng broker, vừa đổi payload schema, vừa đổi JDBC driver trong một lần rollout trừ khi có lý do kỹ thuật bắt buộc và bộ kiểm thử/rollback được thiết kế đủ để cô lập nguyên nhân.

### 15.2. Cổng chấp nhận và điều kiện dừng

Các ngưỡng dưới đây là **ví dụ minh họa**, cần thay bằng SLO cụ thể của dịch vụ:

| Chỉ báo | Ví dụ điều kiện theo dõi | Quyết định |
|---|---|---|
| HTTP 5xx / gRPC error | Tăng đáng kể so với baseline theo canary cohort | Dừng rollout, điều tra |
| p95/p99 latency | Vượt ngân sách request trong thời gian đánh giá | Tạm dừng/tối ưu hoặc rollback |
| DB connection pool | Cạn pool, wait queue kéo dài | Giảm traffic tới bản mới |
| Redis reconnect/timeout | Tăng đột biến hoặc failover recovery chậm | Dừng nâng client/topology |
| Consumer lag | Tăng liên tục, không có khả năng drain | Dừng rollout, xử lý assignment/throughput |
| Duplicate / unknown result | Xuất hiện tác động nghiệp vụ lặp hoặc không rõ trạng thái | Ngừng tác vụ rủi ro, đối soát |
| DLQ/quarantine | Tăng rõ theo schema mới | Khóa producer mới, điều tra payload |

**Rollback không phải lúc nào cũng chỉ là redeploy image cũ.** Nếu bản mới đã ghi schema hoặc payload mà bản cũ không hiểu, đưa binary cũ trở lại có thể khiến lỗi nặng hơn. Phải kiểm chứng rollback compatibility **trước** khi bật format/schema mới hoặc có quy trình khôi phục dữ liệu thích hợp.

### 15.3. Nếu phải nâng server/broker trước

Với database hoặc message broker do nền tảng quản lý:

- Xác minh mọi client hiện hành tương thích với server target.
- Thực hiện theo thứ tự/rolling procedure được nhà cung cấp hỗ trợ.
- Không bật feature level hoặc loại bỏ protocol cũ trước khi client đã chuyển đủ.
- Bảo vệ backup/snapshot và metadata; đánh giá khả năng downgrade riêng.
- Giám sát toàn bộ client, không chỉ service trực tiếp tham gia thay đổi.

## 16. Gỡ lỗi sau nâng cấp: quy trình dựa trên bằng chứng

Khi phát hiện lỗi, thay vì đoán “do Spring Boot mới”, hãy đi từ dấu hiệu tới ranh giới gây lỗi.

### 16.1. Quy trình triage

1. **Thu nhận triệu chứng:** thời điểm bắt đầu, cohort/canary, request/message ID, exception root cause, broker/db logs, trạng thái feature flags.
2. **So sánh phiên bản:** binary và runtimeClasspath thực tế trước/sau, image digest, plugin/BOM, config/default, hạ tầng/broker hiện tại.
3. **Xác định lớp lỗi:** startup/API, protocol/auth/TLS, serializer/schema, query/transaction, ACK/retry hoặc topology.
4. **Tái hiện có kiểm soát:** replay fixture cũ, kết nối tới server cùng version, mô phỏng timeout/failover và dùng request ID để theo dõi side effect.
5. **Khoanh vùng:** dùng feature flag hoặc canary routing, dừng producer viết payload mới nếu có nguy cơ phá consumer cũ.
6. **Ra quyết định:** rollback nếu data contract còn tương thích, hotfix config/mapping hoặc tạm dừng xử lý và đối soát nếu kết quả không rõ.
7. **Xác minh phục hồi:** error rate giảm, backlog drain, không phát sinh duplicate/mất dữ liệu, alert và trace vẫn hoạt động.
8. **Ghi nhận root cause:** nguyên nhân sâu, kiểm thử còn thiếu và cập nhật upgrade checklist.

### 16.2. Bảng triệu chứng → điểm kiểm tra

| Triệu chứng sau upgrade | Giả thuyết ưu tiên | Cách chứng minh |
|---|---|---|
| Compile được, startup NoSuchMethodError | Binary incompatibility / dependency override | Effective dependency graph và classpath |
| Chỉ fail với dữ liệu cache cũ | Serializer, type metadata, package rename | Replay bytes snapshot cũ |
| DB query chậm hơn nhiều | SQL generation, driver fetch size, plan/index | SQL log, EXPLAIN, connection/latency metrics |
| Lỗi TLS sau nâng driver/client | Cipher, truststore, hostname, cert chain | Controlled handshake test và server log |
| Consumer Kafka liên tục rebalance | Client group behavior, poll interval, processing time | Group logs, lag, assignment events |
| DLQ tăng dù broker không lỗi | Payload/schema/headers/exception converter | Replay message trước nâng cấp |
| Redis Cluster seed connect được nhưng lệnh fail | Advertised node address, topology refresh, redirection | Network reachability tới từng node, client logs |
| Duplicate sau retry HTTP | Timeout sau commit, retry defaults | Request ID ở server và số side effect |
| Endpoint health chuyển DOWN | Readiness indicator/config/default thay đổi | Health group và nghiệp vụ bắt buộc thực sự |
| Migrate DB xong rollback app không chạy | Schema mới không tương thích bản cũ | Rollback test trên snapshot đã migrate |

Tìm nguyên nhân bằng bằng chứng từ từng lớp. Không “chữa” sự cố bằng cách tăng timeout vô hạn, nuốt exception, tắt xác thực TLS hoặc chuyển tất cả lỗi dữ liệu sang skip.

## 17. Case study: nâng Spring Boot và Kafka client trong dịch vụ xử lý đơn hàng

Giả sử một dịch vụ nhận REST request, lưu **orders** và **outbox** trong PostgreSQL, phát event **OrderCreated** qua Kafka, consumer khác đọc event và cập nhật Redis cache. Dự án nâng Spring Boot cùng các thư viện được BOM quản lý; broker Kafka và database không thay phiên bản trong giai đoạn đầu.

~~~mermaid
flowchart LR
    API["HTTP POST /orders"] --> DB[("PostgreSQL: orders + outbox")]
    DB --> OUT["Outbox Publisher"]
    OUT --> K[("Kafka topic orders.events")]
    K --> C["Consumer cũ và mới cùng tồn tại"]
    C --> R[("Redis cache")]
    REG["Schema contract fixtures + replay"] -.-> OUT
    REG -.-> C
    MET["Error/lag/duplicates/p99 dashboards"] -.-> DB
    MET -.-> C
~~~

**Rủi ro được nhận diện trước:**

- Spring Data JPA/Hibernate có thể thay SQL hoặc mapping timestamp/UUID.
- JDBC driver hoặc pool config có thể thay thời gian kết nối và mapping exception.
- Kafka client/Spring Kafka có thể đổi default handler/ACK behavior hoặc metric.
- Producer mới có thể viết enum/event header mà consumer cũ không hiểu.
- Redis serializer/key prefix mới có thể làm dữ liệu cache cũ không đọc được khi rollback.

**Kế hoạch thử nghiệm:**

1. Xuất dependency graph bản hiện hành; xác định mọi override liên quan.
2. Kiểm tra lệnh **POST /orders** tạo đúng một row và một outbox event trong cùng transaction.
3. Dùng payload fixtures cũ để chạy consumer mới, và payload mới để chạy consumer cũ.
4. Giả lập producer gửi thành công nhưng mất ACK; publisher phải dùng event ID idempotent để không tạo tác động nghiệp vụ trùng khi retry.
5. Giả lập consumer commit DB nhưng chưa commit offset; redelivery vẫn cho một kết quả nghiệp vụ.
6. Đọc Redis key/value cũ từ fixture bytes; nếu đổi format, chạy cache namespace mới và có kế hoạch xử lý rollback.
7. Triển khai canary, theo dõi HTTP p99, JDBC pool, consumer lag, DLQ và duplicate count.
8. Chỉ rollout rộng khi test rollback với schema/message đã do bản mới viết thành công.

**Sự cố giả định:** sau canary, tỷ lệ message vào DLT tăng. Kiểm tra cho thấy consumer cũ không nhận diện được enum value mới do producer mới phát. Cách xử lý là ngừng phát enum mới, khôi phục writer theo contract cũ, nâng consumer trước rồi mới mở lại feature producer; không tăng retry DLT vô hạn vì cùng payload vẫn không đọc được.

**Tiêu chí hoàn tất:** giao dịch đã nhận không mất/trùng ngoài hợp đồng, schema/message tương thích trong khoảng chạy song song, backlog có thể drain, cảnh báo còn đúng và rollback có thể thực hiện mà không phá dữ liệu mới đã ghi.

## 18. Checklist rà soát thay đổi phiên bản

- [ ] Đã lưu baseline phiên bản **runtime thực**, dependency graph, cấu hình, image digest, service topology và SLO.
- [ ] Đã lập ma trận client cũ/mới với server/broker cũ/mới cho mọi kết nối quan trọng.
- [ ] Đã đọc system requirements, supported-version matrix, migration guide, release notes của đúng version.
- [ ] Đã kiểm tra BOM và override; không trộn Spring Data release train hoặc Spring Framework/Spring Integration không tương thích.
- [ ] Đã kiểm tra Java runtime, namespace Jakarta/Javax, plugin build và binary compatibility.
- [ ] Đã thử query/transaction/SQLState và JDBC connection pool/TLS với database thực.
- [ ] Đã thử serializer, key prefix, TTL, failover và dữ liệu Redis trước upgrade.
- [ ] Đã thử HTTP timeout, status mapping, retry, TLS, idempotency key và payload conversion.
- [ ] Đã thử broker ACK/offset, redelivery, DLT, consumer group, producer/consumer cũ/mới và schema fixtures.
- [ ] Đã thử Spring Integration channel, poller, errorChannel, ACK và transaction boundary nếu dùng adapter.
- [ ] Đã thử rolling deployment, schema expand-contract và rollback ứng dụng với dữ liệu do phiên bản mới tạo.
- [ ] Có kiểm thử latency, throughput, consumer lag, database pool, retry/duplicate và kết quả không rõ trạng thái.
- [ ] Có canary, cảnh báo, điều kiện dừng và kế hoạch phục hồi theo từng lớp.
- [ ] Có owner, runbook, bản ghi tương thích đã xác minh và ngày dự kiến loại bỏ code/config cũ.

**Điểm cần nhớ:** phiên bản client, driver, broker và Spring Data chỉ là nhãn của nhiều hợp đồng kỹ thuật. Một đợt nâng cấp an toàn phải chứng minh **cả ứng dụng cũ và mới nói chuyện đúng với hệ thống nguồn/đích, đọc được dữ liệu cần đọc, xử lý lỗi/ACK/transaction như mong đợi và có thể phục hồi khi một bước không thành công**. Những bằng chứng đó đến từ dependency graph, tài liệu tương thích, contract fixtures, integration tests, fault injection và giám sát rollout.
