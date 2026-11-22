# Quản lý phiên bản Spring Kafka và Kafka client tương thích

Một ứng dụng Spring Kafka chạy ổn định cần nhiều thành phần phiên bản tương thích với nhau: Java runtime, Spring Boot, Spring Framework, Spring Kafka, Apache Kafka client và Kafka broker. Các thành phần này có vòng đời phát hành riêng. Vì vậy, không thể chỉ nhìn số phiên bản broker hoặc Spring Kafka rồi kết luận toàn bộ hệ thống tương thích.

Cách quản lý an toàn là xác định rõ từng lớp, dùng dependency management để khóa một bộ thư viện nhất quán, kiểm tra phiên bản thực tế mà build tool phân giải và kiểm thử với broker mục tiêu. Khi nâng cấp major version, cần đọc migration guide vì API, test infrastructure và hành vi runtime có thể thay đổi.

Bài học này trình bày cách đọc quan hệ phiên bản, cách dùng Spring Boot BOM, cách kiểm tra Kafka client với broker, cách phát hiện xung đột dependency và quy trình nâng cấp Spring Kafka trong dự án Java/Spring.

## 1. Các thành phần phiên bản cần quản lý

Một ứng dụng thường có các lớp sau:

| Thành phần | Vai trò | Điều cần kiểm tra |
|---|---|---|
| Java JDK | Runtime và compiler của ứng dụng | Phiên bản tối thiểu của Spring Boot, Spring Framework và Kafka client |
| Spring Boot | Nền tảng ứng dụng, auto-configuration và dependency management | BOM đang quản lý Spring Framework, Spring Kafka và Kafka client nào |
| Spring Framework | Container, dependency injection, messaging, transaction và retry infrastructure | Yêu cầu của nhánh Spring Kafka đang dùng |
| Spring Kafka | KafkaTemplate, @KafkaListener, listener container, error handler và integration | Yêu cầu Spring Framework và kafka-clients |
| kafka-clients | Java producer, consumer, admin và protocol implementation | API mà Spring Kafka cần và protocol mà broker hỗ trợ |
| kafka-streams | Runtime cho Kafka Streams | Phải kiểm tra phiên bản cùng dòng với Kafka client |
| kafka broker | Cluster lưu trữ và phục vụ record | Tương thích client/broker, API version và tính năng cluster |
| spring-kafka-test | Test utilities và embedded Kafka | Nên cùng phiên bản Spring Kafka; Kafka test artifacts phải được quản lý đồng bộ |

Các thành phần này liên quan nhưng không phải cùng một sản phẩm. Ví dụ Spring Kafka 4.2.0 không có nghĩa broker bắt buộc phải chạy Kafka 4.2.0. Spring Kafka là thư viện tích hợp ở phía ứng dụng; kafka-clients là thư viện giao tiếp với broker; broker là phần mềm server chạy trong cluster.

## 2. Phân biệt ba loại tương thích

### 2.1. Tương thích thư viện Spring

Spring Kafka gọi API của Spring Framework và dựa vào các abstraction của framework. Nếu dùng Spring Kafka mới với Spring Framework quá cũ, có thể gặp lỗi thiếu class, thiếu method hoặc lỗi khi khởi tạo listener container.

Ví dụ một major version Spring Kafka chuyển sang Spring Framework 7. Các ứng dụng còn dùng Spring Framework 6 không thể mặc định nâng riêng Spring Kafka lên major mới mà không kiểm tra yêu cầu tương thích.

### 2.2. Tương thích giữa Spring Kafka và kafka-clients

Spring Kafka xây dựng API tiện dụng trên Kafka Java client. Các class như KafkaProducer, KafkaConsumer, ConsumerRecord, ProducerRecord và AdminClient đến từ thư viện kafka-clients.

Spring Kafka có thể yêu cầu một phiên bản client tối thiểu vì nó gọi các method hoặc dùng các kiểu dữ liệu chỉ xuất hiện từ phiên bản đó. Nếu dependency resolution chọn client thấp hơn, ứng dụng có thể lỗi lúc compile hoặc runtime.

Không nên chỉ khai báo một phiên bản Spring Kafka rồi thêm một phiên bản kafka-clients bất kỳ. Nếu phải override, cần kiểm tra release notes và dependency management của đúng nhánh Spring Kafka.

### 2.3. Tương thích Kafka client với broker

Kafka client và broker giao tiếp qua Kafka protocol. Client và broker không bắt buộc có cùng số phiên bản. Client dùng cơ chế ApiVersions để biết broker hỗ trợ API version nào và chọn request phù hợp.

Tuy vậy, một client mới kết nối được broker cũ không có nghĩa mọi tính năng mới đều dùng được. Một số API, config hoặc protocol feature chỉ có ở broker mới. Ngược lại, client quá cũ có thể không hiểu protocol mới mà broker yêu cầu.

Cần phân biệt:

- **Binary/API compatibility:** ứng dụng có thể load các class và gọi các method cần thiết hay không.
- **Client/broker protocol compatibility:** Kafka client và broker có thể trao đổi request/response hay không.
- **Feature compatibility:** tính năng cụ thể có được cả client và broker hỗ trợ hay không.
- **Operational compatibility:** cách nâng cấp, rolling restart, metadata, KRaft và test infrastructure có tương thích hay không.

## 3. Bộ phiên bản tham chiếu và cách đọc ma trận

Phiên bản phát hành thay đổi liên tục. Bảng dưới đây là một snapshot tham chiếu theo dependency management chính thức được kiểm tra ngày 20-11-2026, không phải ma trận bất biến cho mọi dự án.

### 3.1. Bộ dependency Spring Boot 4.2.0

Spring Boot 4.2.0 hiện quản lý các dependency sau:

| Thành phần | Phiên bản được quản lý |
|---|---:|
| Spring Boot | 4.2.0 |
| Spring Framework | 7.1.0 |
| Spring Kafka | 4.2.0 |
| spring-kafka-test | 4.2.0 |
| kafka-clients | 4.4.0 |
| kafka-streams | 4.4.0 |
| Java tối thiểu của Spring Boot | 17 |

Khi dùng Spring Boot 4.2.0, nên để BOM của Boot quản lý các dependency trên. Không cần thêm version riêng cho từng artifact nếu chưa có lý do rõ ràng.

Tài liệu Quick Tour của Spring Kafka 4.2.0 liệt kê Kafka Clients 4.0.x, Spring Framework 7.0.0 và Java tối thiểu 17 cho ví dụ tương thích. Trong khi đó, BOM Spring Boot 4.2.0 hiện quản lý kafka-clients 4.4.0 và Spring Framework 7.1.0. Đây là lý do phải phân biệt ví dụ/baseline của một trang hướng dẫn với phiên bản cụ thể được BOM của ứng dụng chọn. Khi dùng Boot, hãy kiểm tra dependency management thực tế của đúng release Boot.

### 3.2. Các nhánh Spring Kafka đang được công bố

Trang tài liệu Spring Kafka hiện liệt kê các nhánh stable như 4.2.0, 4.1.3, 4.0.9, 3.3.16, 3.2.10 và 3.1.10. Số patch có thể thay đổi sau khi có bản vá bảo mật hoặc sửa lỗi.

Không suy luận rằng hai nhánh major có thể thay thế trực tiếp cho nhau. Trước khi chọn phiên bản, hãy mở:

- Quick Tour/Compatibility của nhánh Spring Kafka.
- Change History hoặc migration guide.
- Dependency management của Spring Boot đang dùng.
- Kafka client/broker compatibility của phiên bản Apache Kafka mục tiêu.

### 3.3. Một ví dụ lịch sử để hiểu yêu cầu client

Change History của Spring Kafka ghi:

| Nhánh Spring Kafka | Kafka client tối thiểu hoặc mốc nâng cấp được ghi nhận |
|---|---|
| 3.0 | Yêu cầu kafka-clients 3.3.1 |
| 3.1 | Yêu cầu kafka-clients 3.6.0 |
| 3.2 | Yêu cầu kafka-clients 3.7.0 |
| 4.0 | Nâng lên Apache Kafka client 4.0.0 |

Đây là các mốc trong lịch sử phát hành, không phải khuyến nghị override client cho mọi bản patch của nhánh đó. Khi triển khai, hãy dùng đúng tài liệu của phiên bản Spring Kafka cụ thể và BOM của Boot nếu có.

## 4. Dùng Spring Boot dependency management

Spring Boot cung cấp BOM quản lý phiên bản các thư viện thường dùng. Khi dự án dùng parent hoặc dependency management của Boot, hãy khai báo dependency mà không gắn version riêng.

### 4.1. Maven với Spring Boot

Ví dụ dùng Spring Boot 4.2.0:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Starter Kafka giúp Boot cấu hình dependency và auto-configuration tương ứng. Không ghi version cho starter hoặc spring-kafka-test khi BOM đang quản lý chúng.

Nếu ứng dụng cần Kafka Streams, thêm dependency tương ứng nhưng cũng để BOM quản lý version:

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-streams</artifactId>
</dependency>
~~~

### 4.2. Gradle với Spring Boot

Ví dụ:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    implementation 'org.apache.kafka:kafka-streams'
}
~~~

Nếu dự án dùng Gradle platform hoặc version catalog riêng, phải xác nhận platform đó import đúng Spring Boot BOM. Chỉ khai báo plugin Boot mà không dùng dependency management tương ứng có thể khiến version được resolve theo một nguồn khác.

### 4.3. Vì sao không nên gắn version riêng từng dependency?

Ví dụ cấu hình dễ gây lệch:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
    <version>4.2.0</version>
</dependency>

<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-clients</artifactId>
    <version>3.6.0</version>
</dependency>
~~~

Spring Kafka 4.2.0 được ghép với kafka-clients 3.6.0 có thể thiếu API mà Spring Kafka cần. Kết quả có thể là compile error, NoSuchMethodError hoặc NoClassDefFoundError.

Khi dùng Boot, hãy để BOM quyết định version. Chỉ override khi đã kiểm tra compatibility và có kiểm thử cho bộ phiên bản mới.

## 5. Dùng Spring Kafka khi không có Spring Boot

Ứng dụng Spring Framework thuần có thể khai báo trực tiếp Spring Kafka.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
    <version>4.2.0</version>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka:4.2.0'
}
~~~

Khi không có Boot BOM, hãy để POM của Spring Kafka cung cấp dependency transitive tương ứng, trừ khi dự án có dependency management riêng đã được xác minh. Nếu thêm kafka-clients trực tiếp, phải đối chiếu với yêu cầu của nhánh Spring Kafka.

Nếu dùng Kafka Streams, hãy đồng bộ kafka-streams với kafka-clients theo cùng release line. Nếu dùng spring-kafka-test, giữ version của test artifact tương ứng với spring-kafka.

## 6. Khi nào cần override phiên bản Kafka client?

Có thể cần override trong các trường hợp:

- Cluster đã nâng broker và ứng dụng cần client có API mới.
- Có một bản vá Kafka client cần thiết cho ứng dụng.
- Ứng dụng dùng tính năng chỉ có ở client mới hơn.
- Cần đồng bộ Kafka Streams và Kafka client.
- Embedded Kafka test cần dùng đúng Kafka version mà ứng dụng đang kiểm thử.

Tuy nhiên, override client không có nghĩa cứ chọn bản mới nhất là an toàn. Cần kiểm tra Spring Kafka có hỗ trợ client đó không và broker mục tiêu có hỗ trợ protocol cần thiết không.

### 6.1. Maven override trong Spring Boot

Tài liệu Spring Kafka hướng dẫn có thể dùng property dependency management của Boot:

~~~xml
<properties>
    <kafka.version>4.4.0</kafka.version>
    <spring-kafka.version>4.2.0</spring-kafka.version>
</properties>
~~~

Sau đó khai báo dependency không version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Property kafka.version ảnh hưởng các dependency Kafka do dependency management của Boot quản lý, bao gồm client và Streams. spring-kafka.version dùng khi muốn chọn Spring Kafka release khác với release Boot đang quản lý.

Chỉ dùng override khi phiên bản Spring Kafka được chọn hỗ trợ Spring Boot/Spring Framework đang dùng. Không coi hai property này là cách bỏ qua compatibility requirement.

### 6.2. Gradle override

Ví dụ với plugin dependency management:

~~~groovy
ext["kafka.version"] = "4.4.0"
ext["spring-kafka.version"] = "4.2.0"

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
    implementation 'org.apache.kafka:kafka-streams'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

Sau khi override, phải xem dependency graph để xác nhận tất cả artifact Kafka đã dùng cùng version mong muốn. Nếu một plugin hoặc thư viện khác mang theo kafka-clients riêng, Gradle có thể chọn version khác theo conflict resolution.

## 7. Kafka client và broker không cần cùng version

Ví dụ một ứng dụng có:

- Spring Kafka 4.2.0.
- kafka-clients 4.4.0.
- Kafka broker 4.0.x.

Đây là ba thành phần khác nhau. Việc client có version cao hơn broker không tự động là lỗi, nhưng cần kiểm tra compatibility matrix và feature mà ứng dụng sử dụng.

Kafka protocol có cơ chế ApiVersions. Client gửi request để biết broker hỗ trợ API version nào. Client mới có thể dùng phiên bản request cũ hơn nếu broker chưa hỗ trợ request mới.

### 7.1. Đọc compatibility matrix của Apache Kafka

Ma trận Kafka 4.4 mô tả các thay đổi lớn từ Kafka 4.0. Theo bảng client/broker forward compatibility của Kafka 4.0:

| Phiên bản client | Tương thích với Kafka 4.0 |
|---|---|
| 0.x, 1.x, 2.0 | Không tương thích |
| 2.1 đến 2.8 | Tương thích một phần |
| 3.x | Tương thích đầy đủ theo ma trận |

Kafka 4.0 loại bỏ các protocol trước 0.10.x. Vì vậy, client rất cũ không thể tiếp tục kết nối chỉ bằng cách giữ broker ở KRaft.

Bảng trên là ma trận cụ thể cho broker Kafka 4.0, không nên tự động áp dụng cho mọi broker release về sau. Hãy mở trang compatibility của đúng phiên bản broker đích.

### 7.2. Client mới không có nghĩa mọi tính năng mới chạy được

Giả sử client hỗ trợ một API hoặc consumer group protocol mới nhưng broker chưa hỗ trợ, ứng dụng không thể sử dụng tính năng đó. Có thể client fallback sang protocol cũ hoặc broker trả lỗi không hỗ trợ request, tùy API và cấu hình.

Một số config là client-side, một số do broker quản lý. Cần kiểm tra tài liệu config để xác định thành phần nào phải nâng cấp.

### 7.3. Broker upgrade và application upgrade là hai kế hoạch riêng

Một kế hoạch nâng cấp có thể gồm:

1. Nâng broker theo rolling upgrade plan của Apache Kafka.
2. Xác nhận cluster ổn định và protocol/feature tương thích.
3. Nâng kafka-clients của từng ứng dụng.
4. Nâng Spring Kafka và Spring Boot nếu cần.
5. Kiểm thử transaction, consumer group, serialization và error handling.
6. Chuyển traffic dần và theo dõi.

Không nhất thiết nâng tất cả cùng một lúc. Tuy nhiên, không được tự ý thay đổi client version nếu chưa xác định broker version và các feature đang dùng.

## 8. Java version là một phần của compatibility

Một bộ thư viện có thể tương thích về API nhưng không chạy được nếu Java runtime quá cũ.

Spring Boot 4.2.0 yêu cầu tối thiểu Java 17 và Spring Framework 7.1.0 trở lên. Spring Kafka 4.x cũng gắn với thế hệ Spring Framework 7 và Java 17.

Kafka 4.0 có yêu cầu Java riêng theo module:

| Module Kafka 4.0 | Java 11 | Java 17 | Java 23 |
|---|---:|---:|---:|
| Client | Hỗ trợ | Hỗ trợ | Hỗ trợ |
| Streams | Hỗ trợ | Hỗ trợ | Hỗ trợ |
| Connect | Không hỗ trợ | Hỗ trợ | Hỗ trợ |
| Server | Không hỗ trợ | Hỗ trợ | Hỗ trợ |

Java 8 đã bị loại khỏi Kafka 4.0. Khi chạy Kafka client trong ứng dụng, hãy kiểm tra yêu cầu của client và Spring stack. Khi chạy broker hoặc Kafka Connect, hãy kiểm tra yêu cầu runtime riêng của server/module.

Lỗi UnsupportedClassVersionError thường cho thấy bytecode được build bằng JDK mới hơn runtime đang chạy. Đây không phải lỗi Kafka protocol.

## 9. Những thay đổi cần chú ý khi nâng Spring Kafka major version

Major version có thể loại bỏ API deprecated, nâng Kafka client và thay đổi test infrastructure. Trước khi nâng, hãy đọc Change History của nhánh đích.

### 9.1. Spring Kafka 3.0

Một số thay đổi đáng chú ý:

- Kafka client yêu cầu từ 3.3.1.
- Future từ KafkaTemplate và ReplyingKafkaTemplate chuyển sang CompletableFuture thay cho ListenableFuture.
- Một số KafkaHeaders cũ đã deprecated ở 2.9 bị loại bỏ.
- EOSMode.V1 không còn được hỗ trợ.

Nếu code đang dùng ListenableFuture callback, cần chuyển sang CompletableFuture API phù hợp.

Ví dụ:

~~~java
CompletableFuture<SendResult<String, String>> future =
        kafkaTemplate.send("orders", "order-100", payload);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Send failed", exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.info("Sent to partition={}, offset={}",
            metadata.partition(), metadata.offset());
});
~~~

### 9.2. Spring Kafka 4.0

Spring Kafka 4.0 nâng Apache Kafka client lên 4.0.0 và có các thay đổi lớn:

- Loại bỏ chức năng dựa trên ZooKeeper; test broker embedded chỉ còn KRaft.
- EmbeddedKafkaZKBroker bị loại bỏ và dùng EmbeddedKafkaKraftBroker.
- EmbeddedKafkaRule của JUnit 4 bị loại bỏ.
- Các thuộc tính ZooKeeper trong @EmbeddedKafka bị loại bỏ.
- Constructor ConsumerRecords yêu cầu thêm Map parameter; code tự tạo ConsumerRecords cần cập nhật.
- Overload deprecated sendOffsetsToTransaction nhận String consumerGroupId bị loại bỏ.
- Spring Kafka loại bỏ dependency Spring Retry để dùng retry support của Spring Framework 7.
- Annotation @Backoff đổi thành @BackOff; thuộc tính backoff trong @RetryableTopic đổi thành backOff.
- Các lớp Jackson 2 có counterpart Jackson 3; lớp Jackson 2 tiếp tục hoạt động nhưng đã deprecated.
- Kafka 4.0 loại bỏ các protocol cũ trước 0.10.x.

Ví dụ thay đổi annotation retry:

~~~java
// Cách dùng trước major 4
@RetryableTopic(
    backoff = @Backoff(
        delay = 2_000,
        maxDelay = 10_000,
        multiplier = 2
    )
)

// Cách dùng ở Spring Kafka 4
@RetryableTopic(
    backOff = @BackOff(
        delay = 2_000,
        maxDelay = 10_000,
        multiplier = 2
    )
)
~~~

Không chỉ sửa tên annotation. Cần rà soát import, Spring Retry dependency, các class retry custom và test của listener error handler.

### 9.3. Spring Kafka 4.1

Một thay đổi tiện ích là @KafkaListener hỗ trợ thuộc tính ackMode, cho phép một listener ghi đè AckMode mặc định của container factory.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    ackMode = "MANUAL"
)
public void listen(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    process(event);
    acknowledgment.acknowledge();
}
~~~

Khi nâng từ 4.0 lên 4.1, đọc Change History để xem các thay đổi của share consumer acknowledgment và retry topic configuration nếu ứng dụng dùng những tính năng đó.

### 9.4. Spring Kafka 4.2

Spring Kafka 4.2 bổ sung và điều chỉnh các tính năng như:

- Hỗ trợ share consumer acknowledgment modes.
- Share consumer async commits.
- Share consumer error handling và lifecycle events.
- Hỗ trợ Kafka Streams native DLQ.
- Cấu hình group protocol cho Kafka Streams.
- Thay đổi default sameIntervalTopicReuseStrategy trong RetryTopicConfigurationBuilder sang SINGLE_TOPIC.

Nếu ứng dụng dùng share consumer hoặc Kafka Streams DLQ, hãy kiểm tra behavior mới trong Change History trước khi rollout.

## 10. Kiểm tra dependency thực tế mà ứng dụng đang chạy

Không dựa riêng vào version khai báo trong file build. Dependency mediation có thể chọn một version khác vì BOM, transitive dependency hoặc plugin.

### 10.1. Maven dependency tree

Dùng:

~~~bash
mvn dependency:tree
~~~

Lọc các artifact liên quan:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.kafka:*,org.apache.kafka:*
~~~

Kết quả cần kiểm tra:

- Chỉ có một version Spring Kafka được resolve.
- spring-kafka-test cùng version với spring-kafka.
- kafka-clients đúng version được BOM hoặc compatibility matrix yêu cầu.
- kafka-streams và kafka-streams-test-utils cùng release line.
- Không có dependency khác kéo một Kafka client cũ vào runtime.

Có thể dùng mvn help:effective-pom để xem dependency management sau khi parent/BOM được áp dụng.

### 10.2. Gradle dependency insight

Dùng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra một artifact cụ thể:

~~~bash
./gradlew dependencyInsight \
  --dependency kafka-clients \
  --configuration runtimeClasspath
~~~

Kiểm tra Spring Kafka:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-kafka \
  --configuration runtimeClasspath
~~~

Gradle hiển thị version được chọn và lý do chọn version đó. Nếu thấy selected by rule, by conflict resolution hoặc constraint từ platform, hãy xác định nguồn quyết định trước khi override.

### 10.3. Kiểm tra runtime

Có thể log package implementation version khi ứng dụng khởi động:

~~~java
log.info(
    "Spring Kafka version: {}",
    org.springframework.kafka.core.KafkaTemplate.class
        .getPackage()
        .getImplementationVersion()
);

log.info(
    "Kafka client version: {}",
    org.apache.kafka.clients.consumer.KafkaConsumer.class
        .getPackage()
        .getImplementationVersion()
);
~~~

Manifest implementation version có thể rỗng tùy cách đóng gói. Dependency tree của build artifact vẫn là nguồn kiểm tra quan trọng hơn.

## 11. Phân biệt lỗi dependency với lỗi broker

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| NoSuchMethodError | Runtime load version class khác với version compile | dependency tree, duplicate JAR, classpath |
| NoClassDefFoundError | Thiếu module hoặc class đã bị loại bỏ | dependency tree, migration guide |
| UnsupportedClassVersionError | Java runtime thấp hơn bytecode | java -version, Maven/Gradle toolchain |
| UnsupportedVersionException | Broker không hỗ trợ Kafka API request | Broker version, client/broker compatibility |
| ConfigException | Config không tồn tại hoặc không hợp lệ với client version | Client config docs và tên config |
| Consumer không dùng được group protocol mới | Client/broker chưa hỗ trợ hoặc chưa bật protocol | Kafka version, group.protocol, broker configs |
| Embedded Kafka test lỗi ZooKeeper class | Test code còn dùng ZooKeeper-based API sau khi nâng Kafka 4 | @EmbeddedKafka, broker class, test dependencies |
| ClassCastException giữa Kafka classes | Nhiều classloader hoặc nhiều version artifact | Dependency tree và packaged JAR |
| Spring Retry class missing | Spring Kafka 4.x đã chuyển retry infrastructure | Import, dependency và @BackOff migration |
| Serialization test khác production | Test broker/client hoặc serializer version lệch | spring-kafka-test, kafka-clients, schema/serde |

Đừng sửa lỗi UnsupportedVersionException bằng cách thêm dependency Spring. Đây thường là vấn đề protocol/API giữa client và broker. Tương tự, không nâng broker để chữa một NoSuchMethodError do classpath ứng dụng.

## 12. Kiểm thử bộ phiên bản trước khi triển khai

Một bộ dependency resolve thành công chưa chứng minh ứng dụng hoạt động đúng. Cần kiểm thử cả API, protocol và behavior.

### 12.1. Unit test

Kiểm thử:

- Producer callback và xử lý exception.
- Consumer listener logic.
- Serializer/deserializer.
- Header mapping.
- Error handler, retry và DLT routing.
- Transaction boundary và acknowledgment.
- Các class custom implement Kafka interface.

### 12.2. Embedded Kafka test

spring-kafka-test cung cấp embedded Kafka để kiểm thử integration. Dùng nó để kiểm tra:

- Producer gửi record.
- Consumer nhận record.
- Offset và acknowledgment.
- Topic/partition setup.
- Listener container.
- Error handler và DLT.
- Serialization/deserialization.

Từ Spring Kafka 4.0, embedded Kafka chỉ dùng KRaft. Nếu test code còn phụ thuộc ZooKeeper broker hoặc JUnit 4 EmbeddedKafkaRule, cần migration.

Embedded Kafka hữu ích nhưng không thay thế kiểm thử với broker thật. Nó không đại diện đầy đủ cho security, ACL, replication, broker rolling upgrade, network partition và tải production.

### 12.3. Integration test với broker mục tiêu

Dùng broker đúng version dự kiến production hoặc một cluster staging tương thích. Kiểm tra:

- Authentication và TLS/SASL.
- Topic metadata và ACL.
- Producer acks, retries và idempotence.
- Consumer group rebalance.
- Transaction và read_committed.
- KRaft metadata behavior.
- Kafka Streams nếu có.
- Retry/DLT và shutdown/restart.

Nếu ứng dụng cần client mới nhưng production broker cũ, integration test phải dùng chính broker cũ để phát hiện API chưa hỗ trợ.

## 13. Quy trình nâng cấp Spring Kafka có kiểm soát

Một quy trình thực tế:

~~~mermaid
flowchart TD
    A["Kiểm kê Java, Boot, Framework, Spring Kafka, client và broker"] --> B["Đọc compatibility matrix và release notes"]
    B --> C["Chọn bộ phiên bản mục tiêu"]
    C --> D["Cập nhật BOM hoặc dependency management"]
    D --> E["Kiểm tra dependency tree"]
    E --> F{"Có dependency lệch hoặc duplicate?"}
    F -->|Có| G["Sửa constraint/exclusion/override"]
    G --> E
    F -->|Không| H["Compile và unit test"]
    H --> I["Embedded Kafka và integration test"]
    I --> J{"Test pass?"}
    J -->|Không| K["Sửa migration/API/config"]
    K --> H
    J -->|Có| L["Deploy staging và test broker mục tiêu"]
    L --> M["Canary production"]
    M --> N["Theo dõi error, lag, rebalance và transaction"]
    N --> O["Mở rộng rollout hoặc rollback"]
~~~

### 13.1. Kiểm kê trước nâng cấp

Ghi lại:

- JDK build và runtime.
- Spring Boot version.
- Spring Framework version.
- Spring Kafka version.
- kafka-clients version.
- kafka-streams version.
- spring-kafka-test version.
- Kafka broker version và mode KRaft/ZooKeeper.
- Serializer, schema registry, security và connector phụ thuộc.

### 13.2. Đọc release notes và migration guide

Tìm các mục:

- Minimum Java version.
- Spring Framework requirement.
- Kafka client version change.
- Deprecated API bị loại bỏ.
- Config đổi tên hoặc đổi default.
- Embedded Kafka test changes.
- Transaction và consumer group protocol changes.
- Jackson/serialization changes.
- Spring Retry hoặc error handling changes.

### 13.3. Nâng dependency có chủ đích

Nếu dùng Spring Boot, ưu tiên nâng Boot BOM trong một nhánh thay đổi riêng. Chỉ override Spring Kafka hoặc kafka-clients khi có lý do đã xác minh.

Nếu không dùng Boot, dùng compatibility requirement của Spring Kafka và dependency management của dự án để khóa version.

### 13.4. Kiểm thử và rollout

- Compile toàn bộ module.
- Chạy unit và integration test.
- Chạy test với broker mục tiêu.
- Kiểm thử consumer restart và rebalance.
- Kiểm thử transaction abort/commit.
- Kiểm thử DLT và retry.
- Canary một instance hoặc một nhóm consumer.
- Theo dõi producer error, consumer lag, rebalance và exception.
- Chỉ mở rộng rollout khi các chỉ số ổn định.

Rollback ứng dụng không luôn đồng nghĩa rollback broker. Nếu broker đã nâng cấp, ứng dụng cũ phải còn tương thích với broker mới theo ma trận. Lập kế hoạch rollback riêng cho ứng dụng và cluster.

## 14. Lab: kiểm tra và khóa phiên bản trong một ứng dụng

Mục tiêu: tạo một Spring Boot project, xác nhận dependency được quản lý và kiểm tra ứng dụng kết nối broker.

### Bước 1: Khai báo dependency

Dùng Spring Boot parent/BOM và starter Kafka, không gắn version riêng cho Kafka client.

### Bước 2: Resolve dependency graph

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.kafka:*,org.apache.kafka:*
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight \
  --dependency kafka-clients \
  --configuration runtimeClasspath
~~~

Ghi lại version được resolve của Spring Kafka và kafka-clients.

### Bước 3: Kiểm tra JDK

~~~bash
java -version
~~~

Xác nhận runtime đáp ứng minimum Java của Boot và Spring Kafka đang chọn.

### Bước 4: Chạy ứng dụng với broker mục tiêu

Cấu hình bootstrap servers, security và topic. Khởi động producer/consumer đơn giản, gửi một record và xác nhận consumer nhận được.

### Bước 5: Chạy integration test

Dùng spring-kafka-test đúng version với Spring Kafka. Nếu dùng Spring Kafka 4.x, kiểm tra test infrastructure đang chạy KRaft và không còn import ZooKeeper-based test classes.

### Bước 6: Thử thay đổi Kafka client có kiểm soát

Trong một branch thử nghiệm, override kafka.version bằng phiên bản đã được kiểm tra trong compatibility matrix. Resolve lại dependency tree, compile và chạy test. So sánh kết quả với bộ version do Boot BOM quản lý.

### Bước 7: Ghi lại bộ phiên bản

Lưu lại trong tài liệu vận hành hoặc build metadata:

- Java version.
- Spring Boot/Spring Framework.
- Spring Kafka.
- kafka-clients/kafka-streams.
- Broker target.
- Ngày kiểm tra compatibility.
- Link release notes và test result.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Cho rằng Spring Kafka version phải bằng Kafka broker version | Nâng cấp không cần thiết hoặc ghép version sai | Tách Spring library, client và broker |
| Override kafka-clients lên bản mới nhất | Có thể vượt yêu cầu/support của Spring Kafka hoặc broker | Đọc compatibility và release notes |
| Chỉ nhìn version trong build.gradle/pom.xml | Không thấy version thực tế được resolve | Chạy dependency tree/insight |
| Trộn spring-kafka-test khác version | Test behavior lệch runtime hoặc lỗi class | Đồng bộ test artifact với Spring Kafka |
| Dùng Kafka Streams version khác Kafka client | API/runtime mismatch | Dùng cùng release line theo BOM |
| Dùng embedded ZooKeeper test sau Spring Kafka 4.0 | Class và test API đã bị loại bỏ | Chuyển sang KRaft embedded broker |
| Nâng Spring Kafka 4 nhưng giữ Spring Framework cũ | Thiếu API framework và lỗi khởi tạo | Nâng theo bộ tương thích |
| Không kiểm tra Java runtime | UnsupportedClassVersionError | Đồng bộ JDK build và runtime |
| Chỉ test với embedded broker | Bỏ sót security/replication/protocol mismatch | Test với broker mục tiêu |
| Nâng broker và client cùng lúc không có rollback plan | Khó xác định nguồn lỗi | Tách kế hoạch nâng broker và ứng dụng |

## 16. Checklist trước production

- [ ] Đã ghi nhận JDK build/runtime.
- [ ] Đã xác định Spring Boot và Spring Framework version.
- [ ] Đã xác định Spring Kafka version.
- [ ] Đã kiểm tra kafka-clients và kafka-streams thực tế.
- [ ] spring-kafka-test cùng version với Spring Kafka.
- [ ] Đã đọc compatibility matrix của Spring Kafka.
- [ ] Đã đọc client/broker compatibility của Apache Kafka mục tiêu.
- [ ] Đã kiểm tra KRaft/ZooKeeper requirements.
- [ ] Không có nhiều version Kafka client trong runtime classpath.
- [ ] Đã kiểm tra Maven effective POM hoặc Gradle dependency insight.
- [ ] Đã đọc migration guide khi nâng major version.
- [ ] Đã kiểm thử producer, consumer, transaction và error handler.
- [ ] Đã kiểm thử Embedded Kafka với đúng version test artifact.
- [ ] Đã kiểm thử với broker mục tiêu và security thật.
- [ ] Có kế hoạch canary, monitoring và rollback riêng cho app/broker.
- [ ] Đã ghi lại bộ phiên bản và ngày xác minh.

## 17. Tài liệu tham khảo

- [Spring Kafka – Quick Tour and Compatibility](https://docs.spring.io/spring-kafka/reference/quick-tour.html)
- [Spring Kafka – Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html)
- [Spring Kafka – Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [Spring Boot – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Apache Kafka 4.4 – Compatibility](https://kafka.apache.org/44/getting-started/compatibility/)
- [Apache Kafka 4.4 – Upgrade Guide](https://kafka.apache.org/44/getting-started/upgrade/)

Quản lý phiên bản Spring Kafka là quản lý một bộ tương thích gồm Java, Spring Boot, Spring Framework, Spring Kafka, Kafka client và broker. Hãy để BOM quản lý dependency khi có thể, kiểm tra version thực tế được resolve và đọc migration guide trước mỗi lần nâng major. Chỉ sau khi test với broker mục tiêu và xác nhận behavior ổn định mới triển khai bộ phiên bản mới vào production.
