# Thay thế starter cũ khi không có phiên bản tương thích

Một dự án Spring Boot có thể đang dùng starter Spring Cloud Alibaba cũ nhưng cần nâng Spring Boot, Spring Cloud hoặc Java lên phiên bản mới hơn. Nếu release train hiện tại không có starter tương thích, việc ép Maven tải một phiên bản gần giống hoặc ghi đè dependency bắc cầu thường dẫn đến lỗi khó dự đoán: ứng dụng có thể biên dịch nhưng hỏng lúc khởi động, mất auto-configuration hoặc lỗi khi gọi dịch vụ.

Cách xử lý bền vững là xác định **năng lực mà starter đang cung cấp**, sau đó thay bằng abstraction chuẩn của Spring, Java SDK chính thức của Alibaba Cloud hoặc một adapter nội bộ. Không phải mọi starter đều cần được thay bằng một starter khác. Với RDS và Redis, Spring Boot đã có tích hợp chuẩn; với OSS, RocketMQ hoặc API riêng của nhà cung cấp, SDK chính thức có thể là lựa chọn phù hợp; với discovery, circuit breaking và distributed transaction, cần đánh giá kỹ mức tương đương trước khi đổi thư viện.

Bài học này tập trung vào quy trình thay thế starter cũ trong ứng dụng Spring Boot tích hợp Alibaba Cloud. Mục tiêu là giữ hành vi nghiệp vụ, kiểm soát dependency và tạo đường nâng cấp rõ ràng khi hệ sinh thái framework thay đổi.

Sau bài học, bạn có thể:

- Nhận diện starter không tương thích bằng release train và dependency tree.
- Tách chức năng của starter khỏi mã nghiệp vụ trước khi thay thư viện.
- Chọn giữa Spring Boot/Spring Cloud abstraction, SDK chính thức và adapter tự quản lý.
- Thay thế các nhóm tích hợp dữ liệu, messaging, discovery/config, traffic protection và object storage.
- Lập kế hoạch kiểm thử, rollout và rollback mà không phải nâng cấp đồng loạt toàn bộ hệ thống.

## 1. Vì sao starter cũ không còn tương thích?

Starter thường gom dependency và auto-configuration để ứng dụng sử dụng một dịch vụ với ít cấu hình. Tuy nhiên, starter không phải API độc lập với nền tảng. Nó thường phụ thuộc vào:

- Phiên bản Spring Boot và cách Spring Boot đăng ký auto-configuration.
- Spring Framework, Spring Cloud Commons và Spring Cloud release train.
- Java baseline, ví dụ chuyển từ Java 8/11 sang Java 17/21.
- Namespace Jakarta (`jakarta.*`) thay cho Java EE (`javax.*`) ở các thế hệ Spring Framework mới.
- Phiên bản client SDK, HTTP client, serializer, logging và thư viện transitive.
- Cách nạp cấu hình, bootstrap context, bean lifecycle và cơ chế quan sát/metrics.

Một starter cũ có thể vẫn biên dịch với một số dependency mới nhưng không được kiểm thử trong tổ hợp đó. Việc ứng dụng khởi động thành công cũng chưa chứng minh các luồng đăng ký service, refresh config, gửi message hoặc transaction hoạt động đúng.

### 1.1. Phân biệt ba loại vấn đề

| Loại vấn đề | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Không có release tương thích | Release train chính thức không liệt kê phiên bản Spring Boot/Spring Cloud đang dùng | Chọn bộ phiên bản được hỗ trợ hoặc thay năng lực của starter |
| Xung đột dependency | `NoSuchMethodError`, `ClassNotFoundException`, `NoClassDefFoundError`, lỗi linkage hoặc nhiều phiên bản cùng xuất hiện | Kiểm tra dependency tree, BOM và dependency convergence |
| Thay đổi API/cấu hình | App khởi động nhưng property không còn hiệu lực, bean không được tạo hoặc hành vi khác | Đối chiếu migration guide, auto-configuration condition và integration test |

Không nên kết luận mọi lỗi khởi động đều do starter. Trước tiên lấy stack trace đầy đủ, xác định class/method gây lỗi và xem dependency nào cung cấp class đó.

### 1.2. Kiểm tra tương thích trước khi quyết định

Với Maven, kiểm tra dependency tree và phiên bản hiệu lực:

```bash
mvn -q dependency:tree -Dverbose
mvn -q help:effective-pom
```

Có thể lọc theo nhóm thư viện liên quan khi output quá dài:

```bash
mvn dependency:tree -Dincludes=com.alibaba.cloud,com.alibaba.nacos,io.seata,com.alibaba.csp,org.apache.rocketmq
```

Với Gradle, dùng `dependencies` và `dependencyInsight` cho configuration phù hợp, ví dụ `runtimeClasspath`. Kiểm tra cả compile và runtime classpath vì một số lỗi chỉ xuất hiện khi chạy.

Trước khi sửa dependency, ghi lại:

1. Spring Boot, Spring Framework, Spring Cloud và Java version hiện tại.
2. Spring Cloud Alibaba release train và các starter đang dùng.
3. Client SDK thực tế được kéo vào, kể cả dependency bắc cầu.
4. Những bean, annotation, property và API mà mã ứng dụng đang gọi.
5. Các hành vi cần giữ: retry, timeout, serialization, transaction, discovery, config refresh, metrics và health check.

Đối chiếu ma trận tương thích và migration guide chính thức của đúng release. Không suy luận rằng hai phiên bản có số gần nhau là tương thích. Không tự ghim một phiên bản client mới hơn để “sửa” lỗi nếu starter chưa được kiểm thử với client đó.

## 2. Nguyên tắc chọn phương án thay thế

Có ba hướng chính. Chọn hướng ít tạo coupling nhất nhưng vẫn đáp ứng được tính năng và vận hành.

### 2.1. Ưu tiên abstraction chuẩn của Spring

Nếu năng lực đã có trong Spring Boot hoặc Spring Cloud, dùng abstraction đó trước. Ví dụ:

- JDBC, JPA và Redis: Spring Boot Data starters.
- HTTP client: `RestClient`, `WebClient` hoặc HTTP interface phù hợp phiên bản Spring.
- Circuit breaker: Spring Cloud CircuitBreaker với implementation được hỗ trợ, chẳng hạn Resilience4j.
- Messaging: Spring Cloud Stream khi binder tương thích, hoặc abstraction nội bộ khi cần dùng client trực tiếp.
- Health check và metrics: Spring Boot Actuator/Micrometer.

Abstraction chuẩn giúp tầng nghiệp vụ ít phụ thuộc vào một vendor. Tuy nhiên, abstraction có thể không phơi bày toàn bộ tính năng riêng của Alibaba Cloud; khi cần, giữ phần đặc thù trong adapter.

### 2.2. Dùng SDK chính thức khi cần tính năng nhà cung cấp

Với dịch vụ đặc thù như Object Storage Service (OSS), SDK chính thức thường cung cấp API sát với sản phẩm: upload multipart, presigned URL, versioning, lifecycle hoặc các tùy chọn bảo mật. SDK không tự động có nghĩa là Spring starter; ứng dụng có thể tạo bean client và gọi SDK qua một service adapter.

Ưu điểm là theo kịp API dịch vụ và không phải chờ một starter cộng đồng. Đổi lại, mã ứng dụng cần quản lý lifecycle client, credential provider, timeout, retry, connection pool và mapping lỗi.

### 2.3. Tạo adapter nội bộ để cô lập SDK

Không để type của SDK lan khắp controller, domain và service nghiệp vụ. Tạo interface theo nhu cầu của ứng dụng, sau đó cài đặt bằng SDK hiện tại. Ví dụ:

```java
public interface ObjectStorage {
    StoredObject put(String key, byte[] content, String contentType);

    byte[] get(String key);

    void delete(String key);
}
```

Implementation `AliyunObjectStorage` có thể gọi OSS SDK; implementation test dùng fake hoặc local emulator nếu có. Khi cần đổi SDK hoặc chuyển sang nhà cung cấp khác, phần thay đổi chủ yếu nằm trong adapter và cấu hình.

Adapter nên phản ánh use case thật của ứng dụng. Không tạo interface khổng lồ sao chép toàn bộ API của vendor, vì như vậy chỉ chuyển coupling từ SDK sang một interface khó thay đổi.

## 3. Bản đồ thay thế theo năng lực Alibaba Cloud

Bảng sau là điểm bắt đầu để phân loại starter. Tên artifact cụ thể và API phải được kiểm tra theo release đang dùng; không xem bảng này là khẳng định mọi sản phẩm đều có một starter thay thế trực tiếp.

| Năng lực cũ | Hướng thay thế thường phù hợp | Điểm cần giữ hoặc đánh giá |
|---|---|---|
| Kết nối ApsaraDB RDS | Spring Boot JDBC/JPA + JDBC driver của engine | Transaction, pool, TLS, migration, SQL và timeout |
| Kết nối Tair/Redis | Spring Boot Data Redis + Lettuce/Jedis | Auth, TLS, cluster/proxy mode, serialization và TTL |
| OSS | Alibaba Cloud OSS Java SDK bọc trong adapter nội bộ | Credential provider, multipart, retry, URL và quyền bucket/object |
| RocketMQ | RocketMQ Java client chính thức; hoặc Spring Cloud Stream binder tương thích | Producer/consumer lifecycle, group, retry, ordering, ACL và idempotency |
| Nacos discovery/config | Nacos client được hỗ trợ hoặc chuyển sang discovery/config platform khác | Registry semantics, config refresh, namespace, health và bootstrap |
| Sentinel | Sentinel core tích hợp có kiểm soát hoặc Spring Cloud CircuitBreaker/Resilience4j | Flow control/hotspot không tương đương circuit breaker cơ bản |
| Seata | Seata client/server trong release tương thích; hoặc thiết kế local transaction + outbox/Saga/TCC | Global transaction, compensation, locking, timeout và failure recovery |
| Credential và secret | Credential provider/secret manager của nền tảng | Rotation, workload identity, least privilege và audit |

Một số thay thế là tương đương về mục đích nhưng không tương đương về semantics. Ví dụ Resilience4j cung cấp circuit breaker, retry, rate limiter và bulkhead theo cấu hình; nó không tự thay toàn bộ flow control theo resource, hotspot parameter hoặc dashboard rule của Sentinel. Tương tự, outbox/Saga không phải bản sao của Seata AT; đó là lựa chọn kiến trúc với mô hình nhất quán khác.

## 4. Thay starter dữ liệu bằng Spring Boot Data

Đây thường là nhóm dễ thay nhất vì RDS và Redis đã có tích hợp chuẩn trong Spring Boot. Ứng dụng không cần starter Alibaba riêng chỉ để tạo JDBC `DataSource` hoặc Redis connection factory.

### 4.1. RDS qua JDBC/JPA

Thay starter cũ bằng `spring-boot-starter-jdbc` hoặc `spring-boot-starter-data-jpa` và driver đúng engine:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>com.mysql</groupId>
        <artifactId>mysql-connector-j</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Ví dụ cấu hình endpoint private của RDS bằng biến môi trường:

```yaml
spring:
  datasource:
    url: ${RDS_JDBC_URL}
    username: ${RDS_USERNAME}
    password: ${RDS_PASSWORD}
    hikari:
      maximum-pool-size: ${RDS_POOL_MAX:10}
      connection-timeout: 30000
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
```

Để schema migration cho Flyway/Liquibase. Đặt `maximum-pool-size` theo tổng số replica và giới hạn kết nối của RDS. Nếu bật TLS, cấu hình driver xác minh certificate/hostname theo hướng dẫn của engine; không bỏ qua xác minh TLS để làm cho kết nối thành công.

### 4.2. Tair qua Spring Data Redis

Thay starter cũ bằng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Cấu hình endpoint và credential:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME:}
      password: ${REDIS_PASSWORD}
      timeout: 2s
      ssl:
        enabled: ${REDIS_SSL_ENABLED:false}
```

Với tài khoản chỉ có password, không khai báo username nếu loại tài khoản/phiên bản client yêu cầu như vậy. Với tài khoản tùy chỉnh, truyền username và password riêng. Kiểm tra cấu hình cluster/proxy mode của Tair; endpoint proxy có thể được dùng như một Redis endpoint thông thường, trong khi direct connection có thể yêu cầu client cluster-aware.

Sau khi thay, kiểm thử các hành vi từng được starter cũ cung cấp: serialization, key prefix, TTL, connection timeout, reconnect, TLS, health indicator và metrics. Không chỉ kiểm tra `PING`; hãy thử thao tác thực tế với key có namespace dành riêng cho test.

## 5. Thay starter OSS bằng SDK và adapter

Nếu starter OSS cũ không tương thích, ứng dụng có thể dùng OSS Java SDK trực tiếp. Chọn đúng thế hệ SDK được Alibaba Cloud duy trì và tài liệu hóa tại thời điểm triển khai; không trộn API của SDK thế hệ cũ và mới trong cùng một ví dụ hoặc tự ghim một version chưa được xác minh.

### 5.1. Thiết kế ranh giới ứng dụng

Một interface nhỏ giúp domain không phụ thuộc vào `OSSClient`, request object hay exception class của vendor:

```java
public interface DocumentStorage {
    void upload(String documentId, byte[] bytes, String contentType);

    DownloadedDocument download(String documentId);

    void remove(String documentId);
}
```

Implementation adapter chịu trách nhiệm:

- Ánh xạ `documentId` thành object key an toàn, không lấy trực tiếp đường dẫn do người dùng gửi.
- Chọn bucket theo cấu hình môi trường và kiểm tra bucket/region tương ứng.
- Tạo client bằng credential provider thay vì nhúng AccessKey/SecretKey trong mã.
- Đặt connect/read timeout, retry có giới hạn và cấu hình multipart theo kích thước file.
- Chuyển exception SDK thành lỗi ứng dụng có ý nghĩa, giữ nguyên cause để chẩn đoán.
- Đóng client khi ứng dụng shutdown nếu SDK yêu cầu lifecycle quản lý rõ ràng.

### 5.2. Cấu hình credential và quyền

Trong môi trường Alibaba Cloud, ưu tiên cơ chế danh tính workload/role phù hợp với môi trường chạy (ví dụ RAM role cho ECS hoặc cơ chế workload identity được nền tảng hỗ trợ) thay cho AccessKey dài hạn đặt trong file. Nếu buộc phải dùng AccessKey, lưu trong secret manager, giới hạn quyền bucket/object, xoay vòng và không ghi credential ra log.

Phân biệt quyền upload, download, delete và tạo presigned URL. Một service chỉ upload tài liệu có thể không cần quyền xóa bucket hoặc liệt kê toàn bộ object. Cấu hình bucket private và chỉ phát presigned URL với thời hạn, method và phạm vi object cần thiết.

### 5.3. Kiểm thử adapter

Unit test có thể mock interface client hoặc mock transport ở tầng adapter. Integration test cần một bucket test riêng, prefix riêng và credential giới hạn. Kiểm tra upload/download byte-for-byte, content type, object key, quyền từ chối, timeout, retry và multipart. Không dùng bucket production để chạy test tự động xóa object.

## 6. Thay starter RocketMQ khi binder không tương thích

Nếu RocketMQ Binder hiện tại không hỗ trợ release train đang dùng, có hai lựa chọn:

1. Chọn một binder/release tương thích đã được công bố và kiểm thử với Spring Cloud Stream của dự án.
2. Dùng RocketMQ Java client chính thức trực tiếp, bọc producer/consumer trong adapter nội bộ.

Không tự nâng riêng binder hoặc client transitive rồi giả định binary compatibility. Binder và client có thể phụ thuộc vào cùng một tập API/behavior cụ thể của broker.

### 6.1. Giữ hợp đồng event độc lập với client

Định nghĩa event theo hợp đồng ứng dụng, không dùng message object nội bộ của SDK làm domain event:

```java
public record OrderCreated(
    String eventId,
    String orderId,
    long occurredAtEpochMillis,
    int schemaVersion
) {}

public interface OrderEventPublisher {
    void publish(OrderCreated event);
}
```

Implementation RocketMQ chuyển event thành message theo serializer đã chọn, gắn key/tag/header phù hợp và gửi qua client. Consumer chuyển message về hợp đồng nội bộ rồi gọi application service. Điều này giúp thay client mà không sửa domain.

### 6.2. Những hành vi không được bỏ sót

- Producer phải xử lý timeout và kết quả gửi không xác định: broker có thể đã nhận message dù client chưa nhận được response.
- Consumer phải idempotent vì message có thể được giao lại.
- Cấu hình consumer group ổn định và tách theo ứng dụng/môi trường.
- Định nghĩa retry policy, backoff, retry limit và dead-letter queue.
- Nếu cần thứ tự theo aggregate, dùng message key/sharding key và chế độ ordered phù hợp; không giả định ordering toàn topic.
- Theo dõi backlog, consumer lag, message age, retry và DLQ.
- Quản lý ACL/credential, TLS và endpoint theo instance ApsaraMQ for RocketMQ.

Nếu nghiệp vụ cần đảm bảo event được phát sau khi database commit, dùng transactional outbox hoặc transaction message theo khả năng broker và kiến trúc. Không chỉ gọi `publish()` sau `repository.save()` rồi giả định hai thao tác nguyên tử. Outbox ghi business data và event record trong cùng local database transaction; publisher retry gửi event, còn consumer xử lý idempotent.

## 7. Thay starter Nacos, Sentinel và Seata: cần đánh giá semantics

Nhóm này khó thay hơn vì starter có thể tích hợp sâu vào Spring lifecycle, discovery, rule engine hoặc transaction propagation. Trước khi đổi, phải xác định rõ tính năng nào đang được dùng.

### 7.1. Nacos discovery/config

Nếu starter Nacos không có release tương thích:

- Kiểm tra có client Nacos Java được hỗ trợ độc lập với starter hay không; nếu dùng trực tiếp, tạo adapter quản lý đăng ký, subscription, config fetch và lifecycle.
- Nếu chạy trên Kubernetes, cân nhắc Kubernetes Service/DNS cho discovery và ConfigMap/Secret hoặc config platform phù hợp cho cấu hình. Việc chuyển đổi cần đánh giá health, rollout, namespace và cách cập nhật cấu hình.
- Nếu hệ thống đang chuẩn hóa Spring Cloud Commons, cân nhắc một implementation `DiscoveryClient` tương thích hoặc nền tảng discovery khác. Kiểm tra load balancing, instance metadata, health và deregistration khi shutdown.
- Với centralized config, chọn một config service có cơ chế refresh được hỗ trợ. Không tự viết polling config rồi thay đổi bean tùy tiện trong runtime.

Nếu gọi Nacos Java client trực tiếp, không để client nằm rải rác trong mọi service nghiệp vụ. Adapter nên cung cấp một contract nội bộ cho việc resolve service/config. Kiểm thử trường hợp registry mất kết nối, instance stale, config update và ứng dụng khởi động khi Nacos chưa sẵn sàng.

### 7.2. Sentinel traffic protection

Nếu cần circuit breaker cơ bản, Spring Cloud CircuitBreaker với Resilience4j có thể là lựa chọn tự nhiên. Tuy nhiên, hãy đối chiếu tính năng:

| Nhu cầu đang dùng | Khả năng thay thế cần đánh giá |
|---|---|
| Circuit breaker theo tỷ lệ lỗi/độ trễ | Resilience4j CircuitBreaker có thể đáp ứng nếu cấu hình threshold/window phù hợp |
| Retry có giới hạn | Resilience4j Retry hoặc retry policy của client; tránh retry lồng nhau |
| Bulkhead/concurrency limit | Resilience4j Bulkhead hoặc giới hạn concurrency ở executor/client |
| Rate limit theo resource | Resilience4j RateLimiter hoặc gateway/platform rate limiting |
| Hotspot theo tham số cụ thể | Cần thiết kế riêng ở gateway/application hoặc giữ một cơ chế hỗ trợ tính năng này |
| Rule động từ dashboard và rule persistence | Phải thay cả nơi quản trị, lưu trữ, phân phối và audit rule |

Không thay Sentinel bằng một circuit breaker rồi tuyên bố đã giữ nguyên mọi rule. Nếu đang dùng hotspot parameter hoặc system protection, cần kiểm kê từng rule và thiết kế cơ chế tương đương. Dùng fallback có ý nghĩa nghiệp vụ; không trả dữ liệu giả để che lỗi dependency.

### 7.3. Seata distributed transaction

Nếu Seata client/server chưa có tổ hợp tương thích, không nên tự sửa bytecode, override dependency nội bộ hoặc ghép client và TC khác release chỉ để vượt qua lỗi khởi động.

Trước tiên xác định hệ thống thực sự cần distributed transaction hay chỉ đang dùng annotation vì tiện lợi:

- Nếu dữ liệu nằm trong một database, ưu tiên local transaction của Spring (`@Transactional`).
- Nếu cần phát event sau khi commit database, cân nhắc transactional outbox.
- Nếu workflow nhiều bước, kéo dài hoặc có hệ thống ngoài, cân nhắc Saga với compensation và state machine bền vững.
- Nếu có thể thiết kế reservation/confirm/cancel, TCC có thể phù hợp nhưng mỗi bước phải idempotent và chịu được gọi lặp.
- Nếu vẫn cần semantics Seata, giữ Seata trong một phiên bản Spring Boot/Cloud được hỗ trợ hoặc cô lập service đó thành workload nâng cấp riêng. Xác minh database, driver, TC và client theo cùng compatibility matrix.

Outbox, Saga, TCC và Seata AT có mô hình nhất quán khác nhau. Chuyển đổi cần thay đổi thiết kế nghiệp vụ, trạng thái, retry và quy trình đối soát; không phải chỉ thay dependency trong `pom.xml`.

## 8. Tạo cấu hình client theo chuẩn ứng dụng

Sau khi thay starter, gom cấu hình vào namespace riêng của ứng dụng thay vì rải property vendor ở nhiều nơi. Ví dụ:

```yaml
app:
  storage:
    provider: aliyun-oss
    bucket: ${OSS_BUCKET}
    region: ${OSS_REGION}
    endpoint: ${OSS_ENDPOINT}
  messaging:
    provider: rocketmq
    topic-order-created: ${ORDER_CREATED_TOPIC}
    consumer-group: ${ORDER_CONSUMER_GROUP}
```

Các property này là contract nội bộ, không phải property tự động được Spring hoặc Alibaba Cloud hiểu. Lớp `@ConfigurationProperties` của ứng dụng cần validate giá trị, tạo bean client và báo lỗi sớm nếu thiếu endpoint/credential. Không ghi secret trong namespace config thông thường; chỉ tham chiếu đến secret runtime.

Ví dụ cấu trúc cấu hình:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
    @NotBlank String provider,
    @NotBlank String bucket,
    @NotBlank String region,
    @NotBlank String endpoint
) {}
```

Đăng ký properties theo cơ chế phù hợp với phiên bản Spring Boot, ví dụ `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Nếu project còn dùng Spring Boot cũ với `javax.validation`, không sao chép nguyên import `jakarta.validation` của ví dụ; chọn namespace theo Java/Spring generation hiện tại.

## 9. Quy trình migration có kiểm soát

Một lần thay starter nên được thực hiện theo từng năng lực, có thể triển khai độc lập nếu kiến trúc cho phép.

### Bước 1: Lập inventory

Ghi lại starter, bean auto-configured, annotation, property, SDK transitive và các luồng nghiệp vụ đang phụ thuộc. Dùng dependency tree, condition evaluation report của Spring Boot (`--debug`) và log khởi động để xác định bean nào được tạo.

### Bước 2: Viết contract và baseline

Định nghĩa hành vi quan sát được trước khi đổi: request/response, event schema, transaction boundary, timeout, retry, ordering, serialization, error mapping và metrics. Tạo integration test cho các luồng quan trọng. Baseline này giúp phát hiện việc thay thế đã vô tình bỏ một tính năng.

### Bước 3: Chọn phương án và kiểm tra license/support

Đối chiếu compatibility matrix chính thức, Java baseline, release cadence, license và trạng thái bảo trì. Xác định ai chịu trách nhiệm nâng client SDK, xử lý CVE, theo dõi breaking change và vận hành endpoint. Với dịch vụ managed, kiểm tra region/edition có hỗ trợ tính năng và protocol cần dùng.

### Bước 4: Cô lập phần phụ thuộc

Tạo adapter hoặc cấu hình Spring riêng cho năng lực đó. Tránh để controller/domain phụ thuộc trực tiếp vào vendor SDK. Giữ contract ổn định và đưa endpoint, timeout, credential, pool vào cấu hình runtime.

### Bước 5: Thay dependency và dọn dependency cũ

Xóa starter cũ khi implementation mới đã thay thế hoàn chỉnh. Không giữ hai auto-configuration cùng tạo bean cạnh tranh. Dùng BOM được hỗ trợ để quản lý version; kiểm tra dependency convergence và không override transitive một cách tùy tiện.

### Bước 6: Kiểm thử nhiều lớp

- Unit test cho adapter và mapping lỗi.
- Context test để xác minh Spring tạo đúng bean và property binding.
- Integration test với dịch vụ test hoặc Testcontainers khi phù hợp.
- Contract test cho message schema và API giữa service.
- Failure test: timeout, mất mạng, credential sai, broker unavailable, duplicate message, config refresh, consumer restart và transaction rollback.
- Security test: quyền tối thiểu, TLS validation, secret không xuất hiện trong log và không thể truy cập tài nguyên ngoài phạm vi.

### Bước 7: Rollout theo canary và quan sát

Triển khai một nhóm instance hoặc một service ít rủi ro trước. So sánh error rate, latency, connection count, message lag, retry và business outcome trước/sau. Giữ khả năng rollback artifact/config nếu adapter mới có lỗi. Không chạy hai consumer cùng group hoặc hai publisher đồng thời mà không hiểu tác động duplicate/ordering.

### Bước 8: Xóa đường cũ sau khi xác nhận

Khi luồng mới ổn định, xóa property, bean, dependency và code adapter cũ. Kiểm tra dependency tree lần cuối để chắc rằng starter cũ không còn bị kéo vào gián tiếp. Cập nhật runbook, dashboard và hướng dẫn local development.

## 10. Ví dụ kiểm tra dependency và cấu hình sau migration

Với Maven, BOM Spring Boot nên quản lý phiên bản các starter Spring Boot. Spring Cloud BOM và Spring Cloud Alibaba BOM cần được chọn theo ma trận tương thích chính thức; không đặt một BOM tùy ý chỉ để ép một artifact lên phiên bản mới.

Một cấu trúc POM minh họa:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <!-- Import Spring Cloud / Spring Cloud Alibaba BOM chỉ khi
             các phiên bản đã được xác nhận tương thích với Boot ở trên. -->
    </dependencies>
</dependencyManagement>
```

Trong dự án thực tế, Spring Boot parent hoặc dependency management hiện có có thể đã import Boot BOM; tránh import lặp lại không cần thiết. Đặt version trong một nơi có chủ đích và dùng Maven Enforcer/dependency convergence để phát hiện version conflict.

Sau khi thay, kiểm tra:

```bash
mvn -q clean verify
mvn -q dependency:tree -Dverbose
```

Chạy ứng dụng với `--debug` ở môi trường test nếu cần xem condition evaluation report. Kiểm tra không còn hai bean `DataSource`, `RedisConnectionFactory`, `ObjectMapper`, producer hoặc consumer cạnh tranh ngoài dự kiến. Với Spring Boot 3+, rà soát các thư viện còn tham chiếu `javax.*` và kiểm tra integration có hỗ trợ Jakarta.

## 11. Lỗi thường gặp khi thay starter

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `NoSuchMethodError` sau khi app khởi động | Client SDK và starter không cùng API version | Xem dependency tree, loại version conflict và dùng BOM/release train tương thích |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Dependency bị exclude hoặc API chuyển package | Xác định artifact cung cấp class, kiểm tra Java/Jakarta namespace và runtime classpath |
| Spring không tạo bean như trước | Auto-configuration cũ đã bị xóa hoặc condition không còn đúng | Khai báo bean/configuration tường minh hoặc dùng starter chuẩn; kiểm tra condition report |
| Property cũ không còn tác dụng | Prefix/property name hoặc cơ chế bootstrap thay đổi | Đối chiếu migration guide và test binding bằng `@ConfigurationProperties` |
| Nacos config không refresh | Adapter mới chỉ đọc config lúc khởi động hoặc listener không được đăng ký | Thiết kế refresh rõ ràng; chỉ refresh bean hỗ trợ thay đổi runtime |
| Redis kết nối được nhưng lệnh lỗi auth | Cách truyền username/password thay đổi giữa loại tài khoản/client | Kiểm tra loại account và cấu hình riêng từng trường |
| Message bị gửi hoặc xử lý trùng | Producer timeout không rõ kết quả hoặc consumer không idempotent | Event ID, idempotency key, outbox và retry có giới hạn |
| Circuit breaker hoạt động khác Sentinel | Thay một phần chức năng bằng implementation có semantics khác | Lập rule mapping, bổ sung rate limit/hotspot ở lớp phù hợp và kiểm thử tải |
| Global transaction bị treo hoặc rollback không đầy đủ | Client/TC/database không cùng tổ hợp hỗ trợ hoặc boundary thay đổi | Kiểm tra mode, datasource proxy, TC, undo log và recovery; không ép phối hợp version |

## 12. Checklist trước khi phát hành

- [ ] Đã xác nhận Spring Boot, Spring Cloud, Spring Cloud Alibaba, Java và SDK version theo tài liệu tương thích.
- [ ] Đã xác định mọi năng lực mà starter cũ cung cấp và hành vi cần giữ.
- [ ] Đã chọn abstraction chuẩn, SDK chính thức hoặc adapter phù hợp cho từng năng lực.
- [ ] Không còn dependency conflict, duplicate auto-configuration hoặc bean cạnh tranh.
- [ ] Endpoint, credential, TLS, timeout và retry được cấu hình qua runtime config/secret store.
- [ ] IAM/RAM role và ACL tuân theo least privilege.
- [ ] Có integration test cho luồng dữ liệu, messaging, discovery/config hoặc transaction liên quan.
- [ ] Đã kiểm thử timeout, duplicate, restart, retry, rollback và mất kết nối.
- [ ] Metrics, logs, tracing, dashboard và runbook phản ánh implementation mới.
- [ ] Có canary/rollback plan và đã xác định tiêu chí dừng rollout.
- [ ] Đã xóa starter/property/code cũ sau khi xác nhận thay thế hoàn chỉnh.

## 13. Kết luận

Khi starter cũ không có phiên bản tương thích, hãy thay theo năng lực mà nó cung cấp. Spring Boot Data phù hợp với RDS và Redis; SDK chính thức phù hợp với API đặc thù như OSS; RocketMQ client có thể được bọc trong adapter khi binder không tương thích; còn Nacos, Sentinel và Seata cần đánh giá semantics kỹ trước khi chuyển sang giải pháp khác. Compatibility matrix, dependency tree, contract test và rollout có quan sát là các bước giúp nâng cấp có kiểm soát. Mục tiêu là giữ hợp đồng nghiệp vụ ổn định và làm cho phần phụ thuộc nhà cung cấp có ranh giới rõ ràng.

## Tài liệu tham khảo

- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/): dependency management, auto-configuration, data access, configuration properties và Actuator.
- [Spring Cloud Reference](https://docs.spring.io/spring-cloud/docs/current/reference/html/): Spring Cloud Commons, LoadBalancer, CircuitBreaker và các abstraction tích hợp.
- [Spring Cloud Alibaba Documentation](https://sca.aliyun.com/en/docs/): release train, compatibility và hướng dẫn tích hợp theo phiên bản.
- [Alibaba Cloud SDK for Java](https://www.alibabacloud.com/help/en/sdk/developer-reference/java): lựa chọn SDK, credential và cách gọi API dịch vụ Alibaba Cloud.
- [Alibaba Cloud OSS SDK Documentation](https://www.alibabacloud.com/help/en/oss/developer-reference/overview-14): SDK và API Object Storage Service.
- [Apache RocketMQ Documentation](https://rocketmq.apache.org/docs/): Java client, producer, consumer, retry và transaction message.
- [Seata Documentation](https://seata.apache.org/docs/): transaction mode, kiến trúc và compatibility của Seata.
- [Sentinel Documentation](https://sentinelguard.io/en-us/docs/introduction.html): flow control, circuit breaking và rule management.
