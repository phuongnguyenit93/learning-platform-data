# Tương thích Spring Kafka và Kafka client khi nâng cấp hệ thống

Một ứng dụng Spring Kafka có thể chạy ổn định trong nhiều tháng nhưng bắt đầu gặp lỗi sau khi nâng cấp Spring Boot, Spring Kafka, thư viện `kafka-clients` hoặc Kafka broker. Những lỗi đó không chỉ là `ClassNotFoundException` hay `NoSuchMethodError` lúc khởi động. Có trường hợp ứng dụng vẫn khởi động và kết nối bình thường nhưng thay đổi hành vi consumer group, offset commit, retry, serialization hoặc transaction khiến dữ liệu bị xử lý lặp, mất khả năng khôi phục hoặc tăng lag.

Trong nhóm **Nâng cấp và tương thích** của **Spring Kafka Reliability Operations**, bài **Tương thích Spring Kafka và Kafka client** trình bày cách xác định những lớp phụ thuộc, lựa chọn một tổ hợp phiên bản có thể vận hành, kiểm tra tác động trước khi nâng cấp và thiết kế kiểm thử hồi quy tin cậy.

Mục tiêu không phải ghi nhớ một bảng phiên bản bất biến, vì những bản phát hành và chính sách hỗ trợ thay đổi theo thời gian. Điều quan trọng là hiểu **ai quản lý phiên bản, ở lớp nào cần tương thích, tính năng nào phụ thuộc phiên bản broker, và bằng chứng kiểm thử nào đủ để phát hành an toàn**.

Ví dụ mã sử dụng chủ yếu **Java 17, Spring Boot 3.x, Spring Kafka 3.x** và cú pháp Gradle/Maven thông dụng. Với Spring Boot/Spring Kafka thế hệ mới, cần đối chiếu hướng dẫn migration và yêu cầu JDK tương ứng trước khi dùng nguyên mã. Những chuỗi như `3.x.y` trong tài liệu là placeholder phiên bản, không phải khuyến nghị phiên bản cụ thể đã được xác minh cho mọi dự án.

## 1. Bản đồ các thành phần cần tương thích

Một dịch vụ dùng `@KafkaListener` thường có nhiều lớp phụ thuộc:

```text
Application code
  |  @KafkaListener, KafkaTemplate, error handlers
  v
Spring Boot (dependency management + auto-configuration)
  |
  +-- Spring Framework / Spring Security / Micrometer
  |
  v
Spring for Apache Kafka (spring-kafka)
  |
  +-- Listener container, annotation, retry/DLT
  +-- KafkaTemplate, KafkaTransactionManager
  +-- Serialization helpers, events, testing integrations
  |
  v
Apache Kafka Java client (kafka-clients)
  |
  +-- KafkaConsumer / KafkaProducer / AdminClient
  +-- Kafka protocol requests/responses
  +-- Group coordination and record delivery
  |
  v
Kafka brokers + controllers + cluster configuration
  |
  +-- Protocol/features and broker versions
  +-- Topic configuration, ACL, quotas
  +-- Consumer group protocol compatibility
  +-- Transaction coordinator
  |
  v
Message data contract / downstream systems
```

Ngoài Kafka runtime, ứng dụng còn phụ thuộc:

- **JDK:** phiên bản Java được Spring Boot, Spring Framework, Spring Kafka và Kafka client yêu cầu.
- **Build tooling:** Gradle/Maven plugins và dependency-management/BOM.
- **Schema tooling:** JSON/Avro/Protobuf, Schema Registry, serializer/deserializer từ bên thứ ba.
- **Security:** TLS, SASL, ACL, chứng chỉ và client authentication.
- **Observability:** Micrometer, Spring Observation, tracing và client metrics.
- **Test runtime:** `spring-kafka-test`, Embedded Kafka, Testcontainers, broker image và JUnit.

Vì thế, câu hỏi “Spring Kafka phiên bản X có dùng được Kafka broker Y không?” chỉ giải quyết **một phần** của bài toán nâng cấp.

## 2. Ba loại tương thích cần kiểm tra riêng

### 2.1. Tương thích API/binary ở JVM

`spring-kafka` được biên dịch dựa trên những API cụ thể của `kafka-clients` và Spring Framework. Khi thay một JAR bằng phiên bản không nằm trong tổ hợp đã được hỗ trợ, lỗi có thể xuất hiện trước khi ứng dụng tạo được consumer:

```text
java.lang.NoSuchMethodError: ...
java.lang.NoClassDefFoundError: ...
java.lang.ClassNotFoundException: ...
java.lang.AbstractMethodError: ...
```

Ví dụ một version của Spring Kafka gọi method mới từ Kafka client, nhưng runtime classpath lại chứa `kafka-clients` cũ hơn. Source code ứng dụng có thể compile thành công trong một môi trường nhưng runtime vẫn lỗi nếu dependency resolution khác nhau.

**Kết luận:** Kiểm tra phiên bản đã được giải quyết trên **runtime classpath**, không chỉ nhìn dòng khai báo trong `build.gradle` hay `pom.xml`.

### 2.2. Tương thích giao thức giữa Kafka client và broker

Kafka dùng một giao thức có cơ chế thương lượng API version giữa client và broker. Nhờ đó, **không bắt buộc số phiên bản client trùng số phiên bản broker** trong mọi trường hợp. Một client mới có thể kết nối với broker cũ và sử dụng các API/features được hỗ trợ chung.

Nhưng:

- Một tính năng mới có thể cần broker đủ mới.
- Broker cũ có thể không hiểu một API request/version mới.
- Một client có thể loại bỏ phương thức hoặc cơ chế kết nối đã quá cũ.
- Một tổ hợp kết nối thành công chưa chứng minh các tính năng transaction, group protocol hoặc security đều hoạt động.
- Các nâng cấp Kafka lớn có thể thay đổi điều kiện triển khai broker, Java runtime hoặc cơ chế metadata.

**Kết luận:** Tương thích wire protocol khác với tương thích Java API và khác với việc một tính năng cụ thể được hỗ trợ.

### 2.3. Tương thích hành vi ứng dụng

Hai bộ phiên bản đều khởi động được nhưng vẫn có thể khác nhau về:

- Thời điểm commit offset với các ack mode.
- Listener container lifecycle và behavior khi shutdown.
- Error handling, backoff, seek, retry, dead-letter publication.
- Consumer group assignment và rebalance.
- Serializer/deserializer defaults và headers.
- Kafka transaction, producer fencing, idempotence.
- Metrics, event payload, logging và tracing.
- Giá trị mặc định của Kafka client/Spring container.

Đây là loại rủi ro dễ bị bỏ qua nhất. Với hệ thống tin cậy, **bài test “gửi một message rồi nhận một message” chỉ là bước đầu**, chưa đủ chứng minh nâng cấp an toàn.

## 3. Đọc ma trận phiên bản đúng cách

Một cách hiểu khái quát về các dòng sản phẩm:

| Thành phần | Thế hệ phổ biến để tham chiếu | Cần kiểm tra |
| --- | --- | --- |
| Spring Boot 3.x | Thường đi với Spring Framework 6.x, Java 17+ và Spring Kafka 3.x theo BOM | Chính xác **minor/patch** nào được BOM quản lý. |
| Spring Kafka 3.x | Được thiết kế cho hệ sinh thái Spring Framework 6.x và các Kafka Java client tương ứng | Bản `kafka-clients` đã được project kiểm thử/hỗ trợ. |
| Spring Boot 4.x / Spring Kafka 4.x | Thế hệ có thay đổi yêu cầu platform/API so với 3.x | Migration guide, Java baseline, Spring Framework và Kafka client đang dùng. |
| Kafka Java client 3.x / 4.x | Triển khai KafkaConsumer, KafkaProducer, AdminClient | Binary API, tính năng mới, broker minima và removed/deprecated APIs. |
| Kafka broker 3.x / 4.x | Cung cấp protocol, group coordination, transaction và cluster features | Chính sách rolling upgrade, broker feature level và loại controller. |

**Bảng trên không phải ma trận bảo đảm tương thích cho từng cặp version.** Một `Spring Boot 3.2.x` và `Spring Boot 3.4.x` có thể quản lý những patch Spring Kafka/Kafka client khác nhau. Chỉ dùng bảng để xác định **những tài liệu và dependency cần kiểm tra**, không để chọn patch version theo phỏng đoán.

Để tạo một ma trận chính thức cho dự án, ghi **version chính xác**:

```text
Application build:
  JDK runtime: ...
  Spring Boot: ...
  Spring Framework: ...
  spring-kafka: ...
  kafka-clients: ...
  spring-kafka-test: ...
  Serializer/Schema Registry clients: ...

Environment:
  Kafka broker version(s): ...
  Metadata/controller mode: ...
  Inter-broker / feature level: ...
  Security mechanism: ...
  Kafka topics and retention: ...
```

Sau đó đối chiếu tổ hợp này với release notes, compatibility documentation và kết quả integration test.

### Quy tắc hữu ích

**Ưu tiên dùng tổ hợp do Spring Boot BOM quản lý**, trừ khi có một lý do rõ ràng để ghi đè. BOM không thay thế test, nhưng giúp tránh những tổ hợp JAR vô tình lệch phiên bản.

## 4. Ai quyết định phiên bản `kafka-clients` thực sự?

Trong ứng dụng Spring Boot, nhiều dependency được quản lý bằng Spring Boot BOM hoặc plugin dependency management. `spring-kafka` có thể kéo `kafka-clients` theo quan hệ transitive; đồng thời một thư viện khác có thể yêu cầu Kafka client khác.

Ví dụ:

```text
spring-boot-starter-...
   |
   +-- spring-kafka: phiên bản A
         |
         +-- kafka-clients: phiên bản B

another-library
   |
   +-- kafka-clients: phiên bản C

Gradle/Maven resolver
   |
   v
runtimeClasspath: kafka-clients phiên bản được chọn
```

Có thể xảy ra **dependency convergence conflict** nếu các module áp dụng BOM không đồng nhất.

Đừng kết luận rằng thêm:

```groovy
implementation("org.apache.kafka:kafka-clients:some-version")
```

là đủ để “nâng cấp Kafka”. Dòng khai báo có thể ép Kafka client vượt tổ hợp mà Spring Kafka hiện tại đã được kiểm thử; nó không nâng Spring Kafka, Spring Framework hoặc broker.

### Đọc dependency graph với Gradle

Trong dự án Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
```

Cần đọc:

- Phiên bản được **selected**.
- Module nào yêu cầu một version khác.
- Version nào bị nâng/hạ do BOM, constraint hoặc conflict resolution.
- Có khác nhau giữa `compileClasspath`, `runtimeClasspath` và `testRuntimeClasspath` không.
- Có nhiều classloader hoặc fat JAR khác với kết quả kiểm tra local không.

Những lệnh này dùng để **kiểm tra dependency** trong workflow nâng cấp thực tế; bản thân bài học không yêu cầu chạy build của một repository cụ thể.

### Đọc dependency graph với Maven

```bash
mvn dependency:tree -Dincludes=org.springframework.kafka:spring-kafka
mvn dependency:tree -Dincludes=org.apache.kafka:kafka-clients
mvn dependency:tree -Dverbose
```

Khi có nhiều module, kiểm tra module thực sự đóng gói ứng dụng và module chạy test. Một parent POM quản lý dependency có thể khác với những dependency được đóng vào executable JAR của module cuối.

## 5. Ví dụ khai báo dependency theo BOM

### 5.1. Gradle với Spring Boot

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.x.y'
    id 'io.spring.dependency-management' version '1.x.y'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

`3.x.y` và `1.x.y` là placeholder: dự án cần khai báo **các version thực sự có trên repository** và được hỗ trợ bởi plugin tương ứng. Trong dự án dùng Gradle native platform/BOM thay cho dependency-management plugin, cách khai báo khác nhau nhưng mục tiêu vẫn là có **một nguồn quản lý version thống nhất**.

Nếu ứng dụng dùng một starter riêng của tổ chức đã bao gồm `spring-kafka`, tránh thêm declaration trực tiếp chỉ để thay version mà chưa kiểm tra transitive dependency.

### 5.2. Maven với Spring Boot parent

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.x.y</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.kafka</groupId>
            <artifactId>spring-kafka</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.kafka</groupId>
            <artifactId>spring-kafka-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Không tự đặt version cho từng `spring-kafka` và `kafka-clients` nếu chưa cần override. Hãy xem effective POM hoặc dependency tree để biết kết quả.

### 5.3. Khi thật sự cần override Kafka client

Có trường hợp yêu cầu nâng Kafka client vì bản vá bảo mật hoặc một khả năng cụ thể. Khi đó:

1. Xác định **lỗ hổng/tính năng** đang yêu cầu thay đổi.
2. Kiểm tra release notes và tested dependency range của Spring Kafka.
3. Kiểm tra API bị đổi/xóa, deserializer, group protocol, transaction và broker hỗ trợ.
4. Override có chủ đích ở một điểm tập trung.
5. Kiểm tra resolved runtime classpath và package cuối cùng.
6. Chạy regression + integration với broker thật.
7. Ghi lý do override, người sở hữu và ngày dự kiến gỡ.

Việc ép một client version có thể hợp lệ trong một phạm vi được Spring Kafka xác nhận, nhưng **không mặc định mọi patch/minor/major đều an toàn**. Không chỉ dựa vào Semantic Versioning theo suy đoán, nhất là khi chạm đến public Java API hoặc native dependencies.

## 6. Lỗi binary compatibility: dấu hiệu và cách điều tra

### `NoSuchMethodError` hoặc `NoClassDefFoundError`

Ví dụ ứng dụng gặp lỗi sau khi deploy:

```text
java.lang.NoSuchMethodError:
  org.apache.kafka.clients.consumer.SomeType.someMethod(...)
```

Các bước điều tra:

1. Xác định class/method và JAR đang được nạp ở runtime.
2. Lấy `runtimeClasspath` của module deploy, không chỉ `testRuntimeClasspath`.
3. Kiểm tra có một bản `kafka-clients` được bundle từ thư viện third-party hoặc shared classpath không.
4. So sánh dependency graph giữa bản deploy lỗi và bản chạy tốt.
5. Xác định tương thích với phiên bản Spring Kafka bằng release notes.
6. Xây dựng lại artifact với dependency convergence rõ ràng.
7. Chạy smoke test và consumer/producer integration test.

Không sửa bằng cách thêm thật nhiều version JAR vào classpath. Trong hầu hết ứng dụng Java, có nhiều version của cùng class trên classpath dẫn tới hành vi chọn class không dự đoán như mong muốn.

### Compile thành công nhưng startup thất bại

Bản compile có thể sử dụng một classpath khác bản production:

```text
CI compile:    kafka-clients X
Prod runtime: kafka-clients Y
```

Rủi ro này xuất hiện khi:

- Dùng provided dependencies không đúng.
- Container image nạp JAR ngoài.
- Build plugin repackaging có exclude/override.
- Một runtime khác cung cấp thư viện chung.
- Dependency lockfile không được áp dụng nhất quán.

Cần đưa kiểm tra resolved dependencies của **artifact được deploy** vào hồ sơ phát hành, không chỉ lưu danh sách khai báo.

## 7. Wire protocol compatibility với Kafka broker

Kafka client sử dụng requests như metadata, fetch, produce, offset commit, group coordination, transaction coordinator và admin operations. Broker chỉ hỗ trợ những API/version nhất định. Kafka client thường có cơ chế tìm khả năng broker thông qua `ApiVersions`, nhưng không có nghĩa broker hỗ trợ mọi tính năng mới.

```text
Kafka client 4.x
    |
    | negotiate protocol API versions
    v
Kafka broker 3.x
    |
    +-- API supported by both? -> Có thể sử dụng
    |
    +-- Requested feature unsupported? -> Fail / fallback theo client
```

Sơ đồ minh họa; **không tự khẳng định mọi tổ hợp 4.x client → 3.x broker được hỗ trợ**. Cần kiểm tra minimum broker version của client/tính năng đang bật.

### Kiểm tra ba mức

- **Mức 1: kết nối:** TLS/SASL, broker metadata, advertised listener, broker discovery.
- **Mức 2: CRUD dữ liệu:** producer gửi, consumer đọc, offset commit và rebalancing.
- **Mức 3: tính năng nâng cao:** transactions, idempotent producer, cooperative rebalance, group protocol mới, AdminClient features, delegation tokens và những cấu hình phụ thuộc broker.

Một ứng dụng “đã subscribe thành công” chưa chứng minh transaction coordinator và DLT/retry hoạt động đúng.

### `UnsupportedVersionException`

Nếu client yêu cầu API mà broker không hỗ trợ, có thể gặp `UnsupportedVersionException` hoặc những lỗi khả năng feature tương tự. Khi điều tra:

1. Xem operation nào gọi API unsupported.
2. Xem version Kafka broker, Kafka client và feature level.
3. Xem tính năng nào mới được bật khi nâng cấp.
4. Kiểm tra có fallback được hỗ trợ hay phải nâng broker.
5. Thử trong môi trường broker cùng version với production.

Không “sửa” bằng cách tắt toàn bộ tính năng tin cậy như idempotence hay transactions mà không đánh giá hậu quả về mất/trùng dữ liệu.

## 8. Kafka broker version khác với cluster feature level

Trong một số tiến trình nâng cấp broker, **binary version đang chạy** và **feature level được bật** không nhất thiết giống nhau ngay sau rolling upgrade. Kafka cluster có cơ chế quản lý tính năng/metadata tùy thế hệ Kafka; việc nâng binary chưa đồng nghĩa mọi feature mới đều hoạt động.

Đặc biệt cần xem:

- Cluster sử dụng KRaft hay còn phụ thuộc một cơ chế controller cũ theo phiên bản broker.
- Broker/controller quorum đang ở trạng thái hỗn hợp hay thống nhất.
- Những feature level nào được phép nâng sau khi toàn cluster ổn định.
- Các broker mới có đang phục vụ clients cũ trong giai đoạn rolling upgrade không.
- Tính năng consumer group/transaction nào yêu cầu feature level cao hơn.

**Kafka 4.0 là mốc chuyển đổi quan trọng ở phía broker vì thế hệ này dùng KRaft và không còn vận hành theo ZooKeeper mode cũ.** Đây là vấn đề nâng cấp **cluster/controller**, không có nghĩa một ứng dụng Spring Kafka lập tức cần sửa `@KafkaListener` chỉ vì broker đổi mode metadata.

Tuy vậy, không áp dụng quy trình rolling upgrade bất kỳ qua mốc lớn mà không theo tài liệu Kafka broker tương ứng. Quy tắc cập nhật controller, broker và feature level phải dựa trên kế hoạch cluster riêng.

## 9. Java/JDK compatibility

Ngay cả khi Spring Kafka và Kafka client tương thích nhau về API, JDK có thể là yếu tố chặn.

Ví dụ cần xác định:

- Phiên bản Java **tối thiểu** của Spring Boot đang dùng.
- Phiên bản Java tối thiểu của Spring Framework/Spring Kafka.
- Phiên bản Java tối thiểu của `kafka-clients` đang chạy.
- Java của Gradle/Maven runtime và Java toolchain để compile.
- Java trong container image production.
- TLS provider, JDK crypto policy, CA store và những thay đổi liên quan tới chứng chỉ.

Các bản Spring Boot 3.x sử dụng baseline Java 17, nhưng **không suy luận rằng mọi Boot 4.x và Spring Kafka 4.x sẽ hỗ trợ chính xác cùng tập JDK/runtime**. Kiểm tra bảng yêu cầu platform của bản phát hành mục tiêu.

### Vì sao compile toolchain chưa đủ?

`gradle java.toolchain = 17` có thể bảo đảm compile/test bằng toolchain mong muốn, nhưng image deploy vẫn có thể chứa một JRE khác. Nếu binary được biên dịch cho class file version cao hơn JVM runtime, lỗi khởi động như `UnsupportedClassVersionError` xuất hiện.

Nên ghi JDK version thực tế trong artifact manifest hoặc startup diagnostic, đồng thời kiểm tra container image đã được deploy trong môi trường staging.

## 10. Tương thích khi nâng Spring Kafka major/minor

Spring Kafka cung cấp API cao hơn Kafka Java client. Khi nâng, các loại thay đổi có thể gồm:

| Nhóm API | Tác động có thể xuất hiện |
| --- | --- |
| `KafkaTemplate` | Kiểu kết quả gửi, callback/future API và exception handling. |
| `@KafkaListener` | Annotation attributes, container factory settings, endpoint handling. |
| `ConcurrentMessageListenerContainer` | Lifecycle, thread naming, pause/resume, event emission. |
| Error handlers | API thay đổi hoặc loại bỏ các handler cũ, cách chuyển record sang recovery/DLT. |
| Retry topics | Cấu hình topic suffix/backoff/endpoint và feature defaults. |
| `KafkaTransactionManager` | Transaction synchronization, propagation và producer coordination. |
| Serialization | JSON mapper, headers và trusted packages. |
| Metrics/events | Tên observation, metric tags, event interfaces. |
| Testing | Embedded Kafka APIs và cách cấu hình broker bootstrap property. |

Một ví dụ chuyển đổi API từng được thấy khi hệ sinh thái nâng version là xử lý kết quả từ `KafkaTemplate.send(...)`. Ứng dụng viết code phụ thuộc chặt vào kiểu future/callback của một dòng version có thể phải sửa khi dòng mới chuyển API sang một kiểu future khác.

Nguyên tắc: **đọc migration guide của cả Spring Kafka lẫn Spring Boot**, sau đó biên dịch thử các module sử dụng API công khai. Đừng chỉ xem release notes Kafka broker.

### Những việc nên làm trước khi tăng major version

1. Ghi lại tập API ứng dụng đang dùng, đặc biệt custom `ConsumerFactory`, `ProducerFactory`, listener factory và error handlers.
2. Tìm các deprecation warnings đã tồn tại trong version hiện tại.
3. Loại bỏ API deprecated bằng bản thay thế **trước** khi chuyển major nếu có thể.
4. Nâng Spring Boot/Spring Framework và Spring Kafka theo tổ hợp đã được xác nhận.
5. Chạy compile, unit, integration, performance và chaos test.
6. Xem thay đổi default config trong client và container.
7. Kiểm tra log/metrics/alerts có cần sửa field name hoặc event filtering không.

### Đừng import API theo mẫu mà bỏ qua phiên bản

Ví dụ code mới sử dụng `DefaultErrorHandler` không có nghĩa mọi phiên bản Spring Kafka cũ đều hiểu class này. Tương tự, tên package, overload hoặc constructor có thể khác giữa hai dòng.

Khi lấy snippet từ tài liệu, chọn **documentation version khớp với dependency của dự án**, thay vì sao chép mặc định trang latest rồi nghĩ code sẽ hoạt động ở mọi version.

## 11. Consumer group protocol và rebalance

Consumer group là một trong các khu vực cần kiểm thử sau nâng cấp Kafka client/broker. Một số thế hệ Kafka hỗ trợ cách phối hợp group mới hoặc các assignment strategy khác nhau.

Những cấu hình cần xem:

- `group.id` và cách chia consumer group giữa service versions.
- `partition.assignment.strategy` trong classic consumer group protocol.
- `group.protocol` và các cấu hình liên quan nếu Kafka client/broker hỗ trợ consumer group protocol mới.
- `max.poll.interval.ms`, `max.poll.records`.
- `session.timeout.ms` và heartbeat configuration theo loại group protocol đang sử dụng.
- `client.id`, static membership và giới hạn số consumer instances.
- Listener container concurrency so với số partitions.

Không sao chép nguyên cấu hình `heartbeat.interval.ms` sang một giao thức group khác mà không đọc lại ngữ nghĩa. Một số tham số do client điều khiển ở classic protocol có thể do broker điều khiển trong cơ chế mới.

### Ví dụ rủi ro khi rolling deployment

```text
Old consumers (version A)         New consumers (version B)
           |                                  |
           +---------- same group ------------+
                              |
                              v
                    Kafka group coordinator
                              |
                              v
                  partition assignments change
```

Trong thời gian rolling deploy:

- Consumer mới và cũ có thể cùng nằm trong một group.
- Assignment và rebalance xảy ra khi instances join/leave.
- Các listener đang xử lý có thể phải revoke partitions.
- Record chưa commit có thể được phân phối lại.
- Một feature group mới có thể không hỗ trợ mixed-mode như ứng dụng mong đợi.

Với ứng dụng có SLA hoặc yêu cầu thứ tự nghiêm ngặt, thử **mixed-version rollout** trên staging trước. Không giả định mọi consumer group đều có thể chuyển protocol cùng lúc mà không cần kế hoạch.

### Những phép đo quan trọng

- Số lần rebalance và thời lượng rebalance.
- Assignment của partitions trước/sau rollout.
- Consumer lag theo partition.
- Offset commit success/failure.
- Số event retry/redelivery.
- Message ordering theo key trong partition.
- Thời gian drain của old pods khi shutdown.

## 12. Ack mode và offset commit sau nâng cấp

Spring Kafka hỗ trợ nhiều chế độ acknowledge qua listener container. Một số hệ thống dùng record listener, số khác dùng batch listener hoặc manual acknowledgment.

Ví dụ:

```java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
```

Cách này chỉ là ví dụ cấu hình; ứng dụng dùng manual ack phải bảo đảm listener nhận và gọi `Acknowledgment.acknowledge()` đúng thời điểm.

Các trường hợp cần kiểm tra:

| Trường hợp | Rủi ro sau nâng cấp |
| --- | --- |
| Listener thành công | Offset có được commit đúng sau xử lý không? |
| Listener ném exception | Offset chưa xử lý có được redeliver/retry đúng không? |
| Handler recover và gửi DLT | Commit của record gốc có đúng chính sách không? |
| Shutdown/rebalance giữa processing | Có redelivery hợp lệ, không mất dữ liệu không? |
| Manual ack trước external side effect | Dữ liệu có thể mất nếu side effect fail sau ack. |
| Manual ack sau external side effect | Có duplicate nếu commit/ack lỗi sau khi side effect hoàn tất. |
| Batch listener có một record lỗi | Cách chọn failed index và xử lý phần còn lại có đúng không? |

Cần phân biệt **at-least-once** và **exactly-once trong phạm vi Kafka transaction**. Đổi phiên bản client có thể thay đổi thứ tự/điều kiện khi commit lỗi hoặc timeout; nếu business side effect ở database/HTTP, vẫn cần idempotency.

## 13. Error handling, retry và DLT: tương thích hành vi

Nhiều ứng dụng dùng `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, `ErrorHandlingDeserializer` hoặc `@RetryableTopic`.

Điều nên kiểm tra sau nâng cấp:

1. **Deserialization failure:** lỗi xảy ra trước hay sau khi listener nhận record? Error handler nào được gọi?
2. **Listener failure:** retry blocking bao nhiêu lần, backoff như thế nào?
3. **Non-retryable exception:** loại lỗi nào được phân loại fatal ngay?
4. **DLT routing:** topic name, partition, headers và serializer có còn đúng?
5. **Recovery failure:** nếu DLT publish thất bại, record gốc có được retry không?
6. **Offset commit:** một record đã recover có bị replay ngoài ý muốn không?
7. **Retry-topic scheduling:** delay/backoff và topic topology có đúng sau deploy không?
8. **Retries across restarts:** offset/transaction và dedup nghiệp vụ có bảo toàn không?

Ví dụ một cấu hình lỗi cho Spring Kafka 3.x:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    var backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
```

Các import chính:

```java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.util.backoff.FixedBackOff;
```

Đây là mẫu **minh họa policy** chứ không phải cấu hình production hoàn chỉnh. Nó cần topic DLT, producer serializer có khả năng gửi payload bị lỗi, chính sách phân loại exception và hiểu số lần retry được tính theo API của version đang dùng.

### Tại sao test DLT không thể chỉ assert “topic tồn tại”?

Ví dụ payload JSON bị lỗi deserialization có thể không trở thành object mà listener mong đợi. Nếu DLT producer serializer chỉ hỗ trợ kiểu object đã deserialized, việc publish raw bytes lỗi có thể tiếp tục fail.

Cần test với cả:

- Payload đúng và listener xử lý thành công.
- Payload có cấu trúc sai.
- Schema version mới/cũ.
- Lỗi nghiệp vụ có thể retry.
- Lỗi fatal phải đi DLT.
- DLT tạm thời không ghi được.
- Header thông tin lỗi và key của original record.

Một số thay đổi do nâng library serialization có thể làm error handler trông như “bị hỏng”, trong khi thực chất producer DLT không còn serialize đúng dữ liệu lỗi.

## 14. Serializer và deserializer: tương thích dữ liệu

Tương thích JAR không bảo đảm tương thích **message schema**. Với JSON, Avro, Protobuf hoặc custom binary format, consumer cũ và mới có thể hiểu dữ liệu khác nhau.

### 14.1. JSON và type headers

Spring Kafka JSON serializer/deserializer có thể sử dụng type information trong headers theo cấu hình. Một producer nâng cấp có thể gửi header kiểu Java cụ thể mà một consumer ở module khác không biết hoặc không được tin cậy để deserialize.

Các quyết định cần rõ:

- Có dùng type headers hay một contract DTO cố định?
- Tên Java class/package có bị đưa vào header không?
- Consumer có cho phép những trusted packages nào?
- Khi refactor package, consumer cũ có đọc lại được message đã lưu trên topic không?
- Có default target type khi header thiếu/không hợp lệ không?
- Có cần schema registry thay vì phụ thuộc Java class name?

Không cấu hình trusted packages thành wildcard toàn hệ thống chỉ để bỏ lỗi deserialize mà không đánh giá rủi ro bảo mật. Chỉ cho phép những type/package thực sự được dùng.

### 14.2. Schema evolution

Ví dụ một record sự kiện:

```json
{
  "eventId": "evt-01",
  "customerId": "c-01",
  "amountCents": 10000
}
```

Phiên bản mới bổ sung:

```json
{
  "eventId": "evt-02",
  "customerId": "c-01",
  "amountCents": 10000,
  "currency": "USD"
}
```

Producer mới có thể gửi thêm trường `currency`; consumer cũ có đọc được không tùy serializer, validation và cơ chế bỏ qua unknown fields. Ngược lại, nếu consumer mới yêu cầu bắt buộc `currency` mà record cũ trên topic chưa có trường đó, việc replay/rewind có thể fail.

Do đó test phải kiểm tra:

- **New consumer đọc old message.**
- **Old consumer đọc new message** nếu rollout yêu cầu mixed versions.
- Optional/default fields và unknown fields.
- Schema compatibility rules của registry nếu dùng Avro/Protobuf.
- Record đã lưu trong retention window và DLT/retry topics.
- Các message replay từ backup hoặc cluster migration.

### 14.3. Không nâng Schema Registry client một cách cô lập

Serializer Avro/Protobuf từ bên thứ ba có thể kéo phiên bản Kafka client, Jackson hoặc thư viện khác. Khi nâng:

1. Xem dependency tree.
2. Kiểm tra registry/server compatibility.
3. Test schema lookup/registration và cache.
4. Test broker topic data thực tế với schema cũ/mới.
5. Đảm bảo credentials TLS/SASL vẫn được cấu hình đúng.
6. Kiểm tra DLT serializer cho record lỗi.

## 15. Producer idempotence, transactions và exactly-once

Một ứng dụng xử lý tin cậy có thể dùng:

- Producer idempotence.
- Kafka transaction.
- Container/producer transaction integration.
- Database transaction.
- Remote HTTP side effects.

Đây **không phải cùng một phạm vi nhất quán**.

### Producer idempotence

Idempotent producer giúp tránh một số dạng duplicate do producer retry theo hợp đồng Kafka producer. Nó không ngăn ứng dụng **gửi cùng một business event hai lần** với các lần gọi `send()` độc lập và business ID khác nhau.

### Kafka transactions

Kafka transactions có thể liên kết việc publish records và offset commit trong phạm vi Kafka khi cấu hình consume-process-produce theo mô hình được hỗ trợ. Tuy nhiên, transaction Kafka **không tự rollback** một thao tác gửi email, gọi payment API hoặc commit vào database bên ngoài.

Ví dụ:

```text
Kafka record offset=100
       |
       v
Spring @KafkaListener
       |
       +-- Write local DB committed
       |
       +-- Publish Kafka output in Kafka TX
               |
               +-- Kafka TX abort
               |
               v
Local DB commit không tự biến mất
```

Nếu nghiệp vụ cần phối hợp database và Kafka bền vững, thường phải cân nhắc transactional outbox hoặc một cơ chế orchestration có idempotency/reconciliation, thay vì mặc định rằng bật Kafka transactions tạo “global exactly-once”.

### `transactional.id` và fencing

Khi dùng Kafka transactional producer, thay đổi naming/prefix của transactional IDs lúc rolling deploy có thể ảnh hưởng cách producer instances được định danh và cơ chế fencing. Cần tránh tái sử dụng identity không đúng giữa nhiều active instances, đồng thời không đổi vô tội vạ trong khi đang điều tra recovery.

### Kiểm thử transaction qua nâng cấp

- Producer gửi rồi commit transaction: consumer `read_committed` nhìn thấy record.
- Producer abort transaction: consumer `read_committed` không nhìn thấy record đã abort.
- Process chết trước commit: output không được công bố như đã commit.
- Consumer restart: offset và output không tạo side effect nghiệp vụ trùng.
- Rolling deploy với multiple instances: transactional IDs/fencing không tạo lỗi bất thường.
- Broker coordinator version/feature: transaction API hoạt động đúng trên môi trường mục tiêu.

Không chỉ assert message xuất hiện ở topic: với transactions cần phân biệt **committed**, **aborted** và **uncommitted** behavior.

## 16. Consumer/producer configuration defaults có thể thay đổi

Một sai lầm khi nâng library là tin rằng cấu hình không đổi đồng nghĩa hành vi không đổi. Nhiều property đang sử dụng **default** chứ không được khai báo rõ.

Tạo hồ sơ so sánh trước/sau:

| Property | Vì sao quan trọng |
| --- | --- |
| `bootstrap.servers` | Đích kết nối, advertised listeners và khả năng failover. |
| `client.id` | Nhận diện client trên metrics/broker logs. |
| `group.id` | Duy trì consumer group identity qua deploy. |
| `auto.offset.reset` | Hành vi khi group không có committed offset. |
| `enable.auto.commit` | Nếu container quản lý ack/commit, cần tránh cấu hình xung đột. |
| `max.poll.interval.ms` | Thời gian tối đa giữa polls theo Kafka group semantics. |
| `max.poll.records` | Tác động xử lý batch và độ trễ quay lại poll. |
| `isolation.level` | `read_committed` hay `read_uncommitted`. |
| `acks` | Bảo đảm producer acknowledgment. |
| `enable.idempotence` | Liên quan duplicate do producer retry. |
| `delivery.timeout.ms` | Ngân sách thời gian producer có thể gửi. |
| `request.timeout.ms` | Thời gian chờ request. |
| `retries` | Retry producer và tương tác với delivery timeout. |
| `partition.assignment.strategy` | Chiến lược phân phối partitions. |
| `group.protocol` | Giao thức group được hỗ trợ theo client/broker. |
| `security.protocol` | `PLAINTEXT`, `SSL`, `SASL_SSL`, ... |
| `sasl.mechanism` | Cơ chế xác thực phải được broker hỗ trợ. |

Không nên hardcode mọi property chỉ để giữ default cũ. Điều cần thiết là **hiểu những default có ảnh hưởng đến semantics** và cấu hình tường minh những quyết định nghiệp vụ cần ổn định.

### Ví dụ test profile

```yaml
spring:
  kafka:
    consumer:
      group-id: reliability-compat-it
      auto-offset-reset: earliest
      properties:
        isolation.level: read_committed
    producer:
      acks: all
      properties:
        enable.idempotence: true
```

Đây là profile kiểm thử minh họa cho những behavior cụ thể; nó không tự bật Kafka transactions và không phải cấu hình bắt buộc cho mọi application. Nếu test không tạo transactional messages, `read_committed` vẫn đọc được messages đã gửi bình thường.

## 17. Kafka listener container và concurrency

Spring Kafka dùng listener containers để quản lý consumer threads. Sau nâng cấp cần xem:

- Container factory có được tạo bởi Spring Boot auto-configuration hay cấu hình custom không.
- `@KafkaListener(containerFactory = "...")` trỏ đúng bean không.
- `concurrency` so với số partition.
- `AckMode`, `pollTimeout`, `monitorInterval`, `noPollThreshold`.
- `CommonErrorHandler` và transaction manager.
- Lifecycle: auto-startup, pause/resume, shutdown timeout.
- Event listeners: idle/non-responsive/consumer paused/resumed/stopped.

Một ví dụ cấu hình Spring Kafka 3.x:

```java
@Configuration
@EnableKafka
public class OrderKafkaConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    orderListenerFactory(
            ConsumerFactory<String, String> consumerFactory,
            CommonErrorHandler commonErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory
                        <String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setCommonErrorHandler(commonErrorHandler);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

Các import liên quan:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.ContainerProperties;
```

Với ba partitions, concurrency ba có thể sử dụng ba consumer threads; với một partition, tăng concurrency lên ba không khiến một partition được xử lý song song bởi ba consumers trong cùng group.

### Non-responsive monitor cũng thuộc phạm vi tương thích

Sau nâng version, test các events như `NonResponsiveConsumerEvent` nếu ứng dụng dựa vào chúng để alert hoặc automation. Thời điểm phát event chịu ảnh hưởng `pollTimeout × noPollThreshold` và chu kỳ monitor; test cần threshold tường minh, không dựa vào defaults không được kiểm tra.

## 18. Embedded Kafka và `spring-kafka-test`

Test runtime có thể là nguồn gây lệch phiên bản:

```text
Application runtime:
  spring-kafka     A
  kafka-clients    B

Test runtime:
  spring-kafka-test C
  kafka-clients    D
  Kafka broker test classes E
```

Nên để `spring-kafka-test` tương ứng dòng/bản với `spring-kafka` đang dùng, trừ khi tài liệu hỗ trợ xác nhận khác. Đừng chỉ nâng dependency runtime rồi giữ test library từ một dòng major cũ.

### Embedded Kafka không tương đương môi trường production

Embedded Kafka rất hữu ích để test:

- Topic creation và consumer assignment.
- Send/receive message.
- Listener container startup.
- Ack/offset, retry và DLT ở mức cơ bản.
- Kafka events trong phạm vi broker test.

Nhưng:

- Embedded broker version đến từ test dependencies; không chắc bằng broker production.
- Cấu hình KRaft/ZooKeeper có thể khác theo thế hệ Spring Kafka/Kafka.
- Một broker đơn không mô phỏng failover/cross-zone/network partition của cluster nhiều brokers.
- TLS/SASL/ACL/quotas có thể chưa được bật.
- Startup và leader election có thể khác production.

Vì vậy, dùng cả **Embedded Kafka** và **Testcontainers/cluster test** khi yêu cầu reliability cao.

### Testcontainers với broker version chính xác

Một bài test dùng image Kafka/Confluent có thể chọn broker version gần production. Khi nâng client, tối thiểu nên test với broker **old** và **target** nếu doanh nghiệp có giai đoạn rolling upgrade.

Bản image và runtime metadata phải được ghi vào test report. Đừng để tag `latest` làm môi trường thay đổi giữa hai lần chạy CI.

## 19. Ví dụ integration test tối thiểu bằng Embedded Kafka

Mục đích: xác nhận một `@KafkaListener` do Spring Kafka quản lý có thể nhận message qua `KafkaTemplate` và broker test, đồng thời tránh race startup.

Ví dụ dùng Spring Kafka 3.x và Spring Boot 3.x:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=compat-integration-test",
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "spring.kafka.consumer.key-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.producer.key-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "compat-integration-test",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@Import(KafkaCompatibilityIT.FixtureConfig.class)
class KafkaCompatibilityIT {

    @Autowired
    private KafkaTemplate<String, String> template;

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Autowired
    private Probe probe;

    @Test
    void producerAndListenerCanExchangeRecord() throws Exception {
        var container =
                registry.getListenerContainer("compat-listener");

        assertThat(container).isNotNull();

        ContainerTestUtils.waitForAssignment(container, 1);

        template.send(
                "compat-integration-test",
                "order-1",
                "hello-version-check").get(10, TimeUnit.SECONDS);

        assertThat(probe.received.await(10, TimeUnit.SECONDS))
                .isTrue();

        assertThat(probe.payload.get())
                .isEqualTo("hello-version-check");
    }

    static final class Probe {
        final CountDownLatch received = new CountDownLatch(1);
        final AtomicReference<String> payload = new AtomicReference<>();

        @KafkaListener(
                id = "compat-listener",
                topics = "compat-integration-test")
        void onMessage(String value) {
            payload.set(value);
            received.countDown();
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    @EnableKafka
    static class FixtureConfig {

        @Bean
        Probe probe() {
            return new Probe();
        }
    }
}
```

Ví dụ giả định ứng dụng có cấu hình Spring Boot để tạo `KafkaTemplate`, `ConsumerFactory`, `ProducerFactory` và infrastructure listener. Test phải chạy trên dependency `spring-kafka-test` phù hợp, và class fixture được nạp vào context. Với project dùng các loại serializer khác, cần điều chỉnh template/record model.

Đây là **smoke integration test**, không chứng minh an toàn của transactions, retry/DLT, rolling upgrade hoặc mixed-version group. Nó là phép kiểm tra đầu tiên để phát hiện lỗi binary/protocol/configuration cơ bản.

### Lý do chờ partition assignment

Nếu gửi record trước khi consumer join group và đang dùng `auto.offset.reset=latest`, có thể gây test flakiness. `ContainerTestUtils.waitForAssignment(...)` giúp xác nhận consumer thực sự sở hữu partition trước khi gửi.

## 20. Ma trận integration test cho nâng cấp

Khi định nâng từ bộ dependency A sang B, lập ma trận như sau:

| Bộ ứng dụng | Broker | Mục tiêu |
| --- | --- | --- |
| **Current app** | **Current broker** | Baseline trước nâng cấp. |
| **Target app** | **Current broker** | Kiểm tra client/framework mới với broker cũ trong rollout. |
| **Current app** | **Target broker** | Kiểm tra ứng dụng cũ với broker đã nâng. |
| **Target app** | **Target broker** | Kiểm tra trạng thái cuối sau nâng cấp. |
| **Mixed app versions** | Current/target broker theo kế hoạch | Kiểm tra cùng consumer group và rolling deployment. |

Đây là ma trận **logic**; nếu đường nâng cấp cụ thể không hỗ trợ một cặp, phải ghi nó là **unsupported** và điều chỉnh trình tự rollout, không cố ép test như một cặp bắt buộc.

### Bộ kịch bản tối thiểu

| Nhóm | Kịch bản | Assertion quan trọng |
| --- | --- | --- |
| Connectivity | Producer/consumer kết nối TLS/SASL | Không lỗi auth/metadata, topic accessible. |
| Producer | Send/ack thành công | Record được broker ghi theo chính sách acks. |
| Consumer | Poll và process | Đúng payload, key, headers, partition. |
| Offset | Restart sau commit | Không xử lý lại ngoài hợp đồng. |
| Redelivery | Process fail trước commit | Record được retry/redeliver theo policy. |
| Serialization | Old/new schema | Consumer tương thích các payload cần hỗ trợ. |
| Error handler | Retry rồi DLT | Số lần retry, DLT payload và headers đúng. |
| Transactions | Commit/abort | `read_committed` phân biệt record hợp lệ. |
| Group rebalance | Join/leave/rolling deploy | Assignment hợp lệ, không mất side effect. |
| Long processing | Gần/vượt poll interval | Cảnh báo/rebalance/recovery đúng. |
| Shutdown | Graceful pod termination | Commit, drain và container lifecycle phù hợp. |
| Network fault | Broker tạm thời không truy cập được | Sau recovery tiếp tục xử lý, không retry storm. |
| Security | Certificate/token rotation | Client reconnect thành công theo policy. |
| Performance | Throughput, lag, latency | Không regress ngoài ngưỡng chấp nhận. |

Với system chỉ dùng producer mà không có listener, không cần chạy toàn bộ consumer-group test. Với hệ thống tài chính dùng Kafka transactions hoặc outbox, test correctness khi crash lại là ưu tiên cao nhất.

## 21. Test hành vi khi lỗi và restart

Một số lỗi chỉ xuất hiện khi có crash giữa hai bước.

### 21.1. Listener xử lý xong nhưng offset chưa commit

```text
Poll record offset 100
     |
     v
Business side effect committed
     |
     X process crashes before offset commit
     |
Restart
     |
     v
offset 100 delivered again
```

Đây là một tình huống at-least-once điển hình. Sau nâng Kafka client hoặc đổi ack mode, cần test idempotency của writer/remote operation, không chỉ assert số lần listener được gọi trong một lần chạy bình thường.

### 21.2. DLT publish thất bại

Giả lập producer DLT không gửi được. Kiểm tra record gốc được giữ/retry theo policy, không bị commit như đã recover khi thực chất DLT chưa có record.

### 21.3. Consumer bị kẹt

Dùng latch trong listener và monitor `NonResponsiveConsumerEvent`. Xác nhận nâng version không làm mất cơ chế cảnh báo hoặc thay đổi ngưỡng không được phát hiện.

### 21.4. Rebalance trong lúc xử lý

Cho hai consumer instances cùng group, giữ một listener đang xử lý rồi stop instance. Xác nhận offset/side effect không mất và business key vẫn idempotent.

### 21.5. Producer transaction abort

Gửi record trong một transaction, cố ý abort, đọc bằng `read_committed`. Không được coi record abort là dữ liệu nghiệp vụ hợp lệ.

## 22. Nâng cấp broker và client: thứ tự triển khai

Không có một thứ tự duy nhất cho mọi tổ hợp, nhưng quy trình thường an toàn hơn khi **giữ phạm vi thay đổi nhỏ**.

### Pha chuẩn bị

1. Ghi current/target versions chính xác của JDK, Boot, Framework, Spring Kafka, Kafka client và broker.
2. Kiểm tra ma trận hỗ trợ chính thức và broker/client minimum versions.
3. Đọc migration guides cho những major/minor version có thay đổi hành vi.
4. Kiểm tra topic configs, ACL, transactions, group protocol và schema registry.
5. Sao lưu/công bố baseline metrics, consumer lag, error rate và DLT backlog.
6. Chạy dependency graph trên artifact.
7. Chuẩn bị rollback plan và tiêu chí dừng rollout.

### Pha kiểm thử

1. Nâng dependency trên nhánh riêng, không đổi tất cả components cùng lúc khi không cần thiết.
2. Chạy compile và unit tests.
3. Chạy Embedded Kafka smoke tests.
4. Chạy Testcontainers/broker matrix với versions mục tiêu.
5. Chạy lỗi mạng/rebalance/retry/DLT/transaction tests tương ứng nghiệp vụ.
6. So sánh throughput và consumer lag với baseline.
7. Kiểm tra dashboards/alerts còn đo đúng sau thay đổi.

### Pha triển khai

1. Chọn canary instance/topic/group hoặc phạm vi traffic phù hợp.
2. Quan sát startup, authentication, broker metadata và first records.
3. Nâng thêm replicas theo giới hạn rollout, theo dõi rebalance.
4. Kiểm tra group offsets và side effects trong thời gian thực.
5. Chỉ nâng feature level/consumer group protocol mới khi được phê duyệt và tương thích.
6. Thu hồi old instances theo graceful shutdown.
7. Giữ artifact/config rollback sẵn có.

### Pha hậu kiểm

- DLT/retry backlog không tăng bất thường.
- Consumer lag và rebalance ổn định.
- Không có message bị mất hoặc side effect trùng ngoài hợp đồng.
- Chỉ số publish/processing success rate khớp baseline.
- Không có classpath errors và metrics exporter vẫn hoạt động.
- Ghi lại version đã triển khai và quyết định về override dependencies.

**Đừng nâng client, broker, schema registry, JVM và cơ chế group protocol cùng lúc nếu không có yêu cầu bắt buộc.** Khi nhiều biến thay đổi đồng thời, rất khó xác định nguyên nhân lỗi.

## 23. Rolling upgrade và rollback có điều kiện

Rollback ứng dụng không đơn giản chỉ là chạy lại JAR cũ nếu nâng cấp đã thay đổi dữ liệu hoặc protocol.

Trước khi tuyên bố có thể rollback, phải trả lời:

- Consumer cũ có đọc được message do producer mới gửi không?
- DLT/retry topic mới có chứa headers/schema mà app cũ hiểu không?
- Topic configuration hoặc ACL đã thay đổi theo cách app cũ không dùng được không?
- Broker feature level mới có còn chấp nhận client cũ không?
- Consumer group đang dùng giao thức mới có thể quay về hành vi cũ theo lộ trình hỗ trợ không?
- Kafka transactions / transactional IDs của app cũ có bị fencing/conflict không?
- Có migration state ở database hoặc external systems đi kèm không?

Một kế hoạch rollback tốt phải **xác minh tính tương thích ngược** trước khi rollout, chứ không chỉ giữ lại container image cũ.

### Canary và blue/green

Canary thích hợp khi có thể đưa một phần traffic/partition sang version mới và quan sát. Blue/green có thể cần group ID riêng hoặc nguồn dữ liệu riêng, vì hai deployment cùng consumer group sẽ chia partitions, không tự tạo “mirror test” của toàn bộ traffic.

Nếu tạo group mới để shadow consume, nó có offset riêng; phải kiểm tra rằng shadow listener **không thực hiện side effect** trong hệ thống production. Không chạy song song hai consumer groups cùng ghi một đích không idempotent chỉ để “so sánh version”.

## 24. Security compatibility khi nâng cấp

Có thể ứng dụng lỗi sau nâng dù Kafka client hoàn toàn tương thích về protocol, vì security handshake bị ảnh hưởng bởi JDK hoặc broker config.

Các yếu tố:

- TLS protocol/cipher suites được JDK mới chấp nhận.
- CA truststore và cách nạp certificate.
- Hostname verification, broker SAN và advertised listeners.
- SASL mechanism: PLAIN/SCRAM/OAUTHBEARER/Kerberos tùy hệ thống.
- Token expiry/refresh với OAuth.
- Kafka ACL cho consumer group, topic, transactions và idempotent producer.
- Secret rotation và truststore/key material.
- Network proxy, load balancer và DNS behavior.

Một lỗi `SSLHandshakeException` không phải bằng chứng Spring Kafka không tương thích Kafka broker về API. Hãy chẩn đoán security layer riêng.

### Không ghi secret để debug

Khi thu log Kafka client configs hoặc Spring Boot configuration properties, cần che/mask:

- SASL JAAS config.
- Password/secret/token.
- Private keys.
- Credential trong endpoint URLs.
- Message payload chứa dữ liệu nhạy cảm.

Các trường như `client.id`, `group.id`, broker host và error class thường hữu ích hơn việc in toàn bộ config raw.

## 25. Quan sát tương thích qua log và metrics

Một bản nâng cấp “không có exception” vẫn có thể làm tăng lag, retry hoặc end-to-end latency.

Cần theo dõi ít nhất:

| Tín hiệu | Điều nên so sánh trước/sau |
| --- | --- |
| Consumer lag theo partition | Có tăng kéo dài hoặc mất cân bằng không. |
| Poll frequency / processing duration | Consumer có quay lại poll đúng nhịp không. |
| Rebalance count/duration | Có quá nhiều lần group rejoin không. |
| Offset commit failures | Có thay đổi commit semantics hoặc coordinator error không. |
| Producer send latency/P95/P99 | Có tăng khi acks/transactions thay đổi không. |
| Producer record error/retry rate | Có lỗi broker, timeout hoặc quota không. |
| DLT publish rate | Tăng do lỗi business hay do deserializer bị thay đổi. |
| Retry count/backoff | Có retry storm hoặc policy khác trước không. |
| Transaction abort/fencing | Có producer identity conflicts không. |
| Deserialization errors | Có schema/type headers thay đổi không. |
| JVM CPU/GC/threads | Client/Spring update làm thay đổi footprint không. |
| Kafka broker/network | Quota, request latency, connection churn. |

Nên thêm metadata của deploy vào log/observability như application version, Spring Kafka version, Kafka client version và environment, nhưng không dùng `messageKey` hay `offset` làm metric label vì cardinality lớn.

### Ví dụ log có cấu trúc

```text
INFO kafka.consumer.started
  applicationVersion=2026.11.16
  listenerId=orders-listener
  groupId=orders-service
  springKafkaVersion=<resolved-version>
  kafkaClientVersion=<resolved-version>

WARN kafka.consumer.rebalance
  listenerId=orders-listener
  assignedPartitions=...
  durationMs=...

ERROR kafka.message.deserialize.failed
  listenerId=orders-listener
  errorType=...
  schemaVersion=...
```

Trong thực tế, version có thể lấy từ build metadata/package implementation version hoặc thư viện version utility tương ứng. Không đoán version từ tên JAR hardcoded nếu artifact shading/repackaging có thể thay đổi.

## 26. Những lỗi nâng cấp thường gặp

### 26.1. Chỉ nâng `kafka-clients`, giữ nguyên Spring Kafka major

Có thể gây `NoSuchMethodError` hoặc thay đổi API behavior không được hỗ trợ. Trước khi override, kiểm tra version range được Spring Kafka kiểm thử, compatibility notes và regression tests.

### 26.2. Coi broker và client phải có cùng số version

Không phải quy tắc chung của Kafka protocol. Nhưng cũng không có bảo đảm mọi cặp version sẽ hỗ trợ mọi feature. Cần phân biệt kết nối cơ bản và khả năng nâng cao.

### 26.3. Chỉ xem dependency khai báo

Gradle/Maven có thể resolve version khác do BOM/conflict. Kiểm tra runtime classpath và packaged artifact.

### 26.4. Giữ `spring-kafka-test` từ một dòng khác

Có thể làm Embedded Kafka hoặc test utilities lỗi dù runtime đang đúng. Đồng bộ test dependencies với runtime.

### 26.5. Chỉ dùng Embedded Kafka để đại diện production

Embedded broker không nhất thiết khớp version, mode, TLS/SASL, cluster topology và network. Bổ sung broker matrix qua Testcontainers/staging.

### 26.6. Không test dữ liệu đã lưu trong topic

Producer mới và consumer mới hoạt động với message mới, nhưng consumer mới không đọc được record cũ. Phải test schema evolution/replay/retention.

### 26.7. Không test DLT và retry

Path thông thường chạy thành công, nhưng lỗi deserialize hoặc DLT publish làm listener kẹt. Test lỗi có chủ đích và verify offset.

### 26.8. Bật giao thức consumer group mới ngay khi nâng dependency

Một số tính năng yêu cầu broker/group support và có điều kiện mixed-version. Nâng protocol là thay đổi behavior riêng, cần test và rollout riêng.

### 26.9. Thay đổi ack mode không kiểm chứng side effect

Manual ack, record/batch commit và transactions có thể thay đổi điều kiện redelivery. Xác minh cả crash/rebalance.

### 26.10. Tăng thread count để “chữa” lag sau nâng cấp

Có thể tăng rebalance, overload DB/remote API và làm phức tạp thứ tự xử lý. Phải đo bottleneck và số partitions trước.

### 26.11. Không xét JDK/TLS

JDK runtime cũ tạo `UnsupportedClassVersionError`; TLS handshake có thể fail vì thay đổi cipher/truststore. Chẩn đoán platform và security riêng.

### 26.12. Không chuẩn bị rollback cho schema mới

Nếu producer mới gửi message mà consumer cũ không đọc được, rollback app cũ sẽ fail. Phải thiết kế backward/forward compatibility trước rollout.

## 27. Bài tập thực hành: nâng Spring Kafka trong hệ thống đơn hàng

Giả sử một hệ thống nhận đơn hàng qua Kafka:

```text
orders-api
  |
  v
Topic: orders.events (6 partitions)
  |
  v
orders-consumer-service
  +-- @KafkaListener
  +-- JSON deserialization
  +-- validates business event
  +-- writes PostgreSQL
  +-- DefaultErrorHandler
  +-- DeadLetterPublishingRecoverer -> orders.events.DLT
  |
  v
Business processing result
```

Tổ chức muốn nâng Spring Boot/Spring Kafka và Kafka client, nhưng trong giai đoạn đầu Kafka broker chưa được nâng. Consumer service chạy nhiều replicas, sử dụng cùng `group.id`.

### Phần A – Lập bản đồ dependency

1. Ghi current/target Java, Boot, Framework, Spring Kafka, Kafka client và Kafka broker versions.
2. Chạy `dependencyInsight` hoặc `dependency:tree` trên module deploy.
3. Xác định `spring-kafka-test` và JSON/schema dependencies.
4. Ghi các Kafka client properties có ảnh hưởng đến retry, commit, group protocol và transaction.
5. Đọc release notes/migration docs cho chính xác các version sẽ nâng.

### Phần B – Xây ma trận compatibility

1. Current application với current broker.
2. Target application với current broker.
3. Current application với target broker nếu kế hoạch cluster có giai đoạn này.
4. Target application với target broker.
5. Old/new consumer replicas cùng group trong rolling deployment.
6. Ghi rõ tổ hợp nào unsupported theo tài liệu chính thức thay vì giả định có thể chạy.

### Phần C – Test dữ liệu và lỗi

1. Gửi một JSON order hợp lệ, assert được ghi một lần.
2. Gửi JSON sai schema, assert đi qua error handler/DLT đúng policy.
3. Gửi dữ liệu cũ trong retention window, assert consumer mới đọc được.
4. Gửi schema mới, assert consumer cũ đọc được nếu rollback yêu cầu.
5. Gây lỗi database sau khi listener nhận message; assert redelivery và idempotency.
6. Tạm dừng một replica trong lúc xử lý, xác nhận group rebalance không mất record.
7. Test shutdown/drain và startup của replica mới.
8. Gây broker connection disruption, đo recovery và lag.

### Phần D – Release gates

Đặt các điều kiện phát hành ví dụ:

- Không có unresolved classpath/API errors.
- Tất cả compatibility tests bắt buộc pass.
- DLT/deserialize error rate không tăng bất thường.
- Consumer lag quay về baseline sau rollout.
- Không có duplicate side effect ngoài hợp đồng.
- Rollback plan đã được kiểm chứng trên thông điệp do producer mới tạo.
- Có alert cho rebalance storm, transaction abort và retry/DLT backlog.
- Ghi snapshot resolved dependencies và versions triển khai.

### Câu hỏi tự đánh giá

- Vì sao Spring Kafka version và `kafka-clients` version không nên được chọn độc lập tùy tiện?
- Vì sao Kafka broker cũ và client mới có thể kết nối nhưng một tính năng mới lại lỗi?
- Chỉ thấy một message được nhận qua Embedded Kafka đã đủ kết luận production upgrade an toàn chưa?
- Lỗi `NoSuchMethodError` gợi ý kiểm tra lớp tương thích nào?
- Vì sao cần test consumer cũ đọc message do producer mới gửi trước khi rollback?
- Thay đổi `max.poll.interval.ms` có giải quyết được listener gọi HTTP vô hạn không?
- Kafka transactions có bảo đảm rollback database và remote HTTP side effect không?
- Khi mixed-version consumers cùng group, những tín hiệu nào cần giám sát?
- Tại sao `spring-kafka-test` cũng cần được kiểm tra khi nâng runtime?
- Khi nào nên nâng feature level/protocol riêng khỏi việc nâng JAR ứng dụng?

## 28. Tài liệu tham khảo

- [Spring for Apache Kafka – Reference Documentation](https://docs.spring.io/spring-kafka/reference/): listener containers, producers, consumers, error handling, transactions và testing.
- [Spring for Apache Kafka – Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html): những thay đổi giữa các phiên bản và migration notes.
- [Spring for Apache Kafka – Spring Boot Integration](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html): cấu hình `@KafkaListener` và các listener containers.
- [Spring for Apache Kafka – Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): Kafka transaction và những giới hạn khi phối hợp tài nguyên khác.
- [Spring for Apache Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): error handlers, recoverers và DLT.
- [Spring for Apache Kafka – Testing](https://docs.spring.io/spring-kafka/reference/testing.html): Embedded Kafka và utility hỗ trợ integration test.
- [Spring Boot Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): dependency versions được quản lý bởi dòng Spring Boot đang dùng.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): clients, brokers, protocol, security và upgrade guidance.
- [Apache Kafka Protocol Guide](https://kafka.apache.org/protocol.html): API versioning và Kafka wire protocol.
- [Apache Kafka Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): poll, groups, assignment và consumer properties.
- [Apache Kafka Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): idempotence, delivery timeouts và producer properties.
- [Testcontainers Kafka Module](https://java.testcontainers.org/modules/kafka/): kiểm thử tích hợp với broker version cụ thể.

