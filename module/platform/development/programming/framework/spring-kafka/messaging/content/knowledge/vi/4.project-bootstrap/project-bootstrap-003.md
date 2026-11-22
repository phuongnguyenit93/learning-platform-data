# Khai báo spring-boot-starter-kafka

## 1. Mục tiêu của dependency Kafka trong Spring Boot

Để một ứng dụng Spring Boot gửi và nhận sự kiện Kafka, ứng dụng cần thư viện Kafka client, phần tích hợp Spring Kafka và cơ chế auto-configuration của Spring Boot. Cách khai báo được khuyến nghị cho các dự án Spring Boot 4.x là thêm dependency chính thức `spring-boot-starter-kafka`.

Starter là một dependency descriptor tập hợp các thư viện cần thiết và cấu hình tích hợp phù hợp với hệ sinh thái Spring Boot. Sau khi thêm starter, ứng dụng có thể cấu hình kết nối qua `spring.kafka.*`, inject `KafkaTemplate` để gửi record và dùng `@KafkaListener` để nhận record. Nhờ dependency injection, các thành phần hạ tầng được Spring quản lý trong ApplicationContext.

Trong module `SPRING_KAFKA_MESSAGING`, starter này là bước khởi đầu cho các nội dung tiếp theo về topic, partition, consumer group, serialization, retry, dead-letter, transaction và kiểm thử. Nó cung cấp thư viện phía ứng dụng; nó **không cài đặt hoặc tự khởi chạy Kafka broker**. Bạn vẫn cần một cụm Kafka cục bộ, trong Docker hoặc trên môi trường dùng chung.

## 2. Chọn đúng dependency theo phiên bản Spring Boot

Tên dependency phụ thuộc dòng Spring Boot đang sử dụng:

| Phiên bản nền tảng | Dependency thường dùng | Ghi chú |
|---|---|---|
| Spring Boot 4.x | `org.springframework.boot:spring-boot-starter-kafka` | Starter chính thức cho Kafka, bao gồm phần tích hợp Kafka của Spring Boot và Spring Kafka |
| Spring Boot 3.x | `org.springframework.kafka:spring-kafka` | Các dự án Boot 3 thường khai báo Spring Kafka trực tiếp; dùng tài liệu đúng phiên bản Boot để kiểm tra auto-configuration và phiên bản tương thích |
| Ứng dụng Spring Framework không dùng Spring Boot | `org.springframework.kafka:spring-kafka` | Tự cấu hình các factory, template, listener container và các thành phần hạ tầng cần thiết |

Với dự án Spring Boot 4.x, không thay starter bằng riêng `spring-kafka` nếu ứng dụng cần Boot auto-configuration. Starter `spring-boot-starter-kafka` kích hoạt phần tích hợp Boot, bao gồm binding `spring.kafka.*`, cấu hình `KafkaTemplate` và hạ tầng cho `@KafkaListener`. Chỉ thêm thư viện `spring-kafka` có thể khiến ứng dụng có class Kafka nhưng thiếu các bean và cấu hình Boot mong đợi.

Không nên trộn dependency của các dòng Spring Boot khác nhau trong cùng một dự án. Trước khi thêm thư viện, xác định phiên bản Spring Boot đang được quản lý bởi parent POM, plugin Gradle hoặc BOM của dự án.

## 3. Khai báo dependency bằng Maven

Nếu dự án dùng Spring Boot parent hoặc đã import `spring-boot-dependencies` BOM, chỉ cần khai báo artifact và để Spring Boot quản lý phiên bản:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>
</dependencies>
```

Thông thường không cần thêm thẻ `<version>` cho starter. Spring Boot BOM cung cấp bộ phiên bản đã được kiểm thử tương thích giữa Spring Boot, Spring Kafka và Apache Kafka client. Khi nâng cấp Spring Boot, dependency management sẽ cập nhật các phiên bản liên quan theo bộ tương ứng.

Nếu dự án không dùng Spring Boot parent, có thể import BOM trong `dependencyManagement`:

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
    </dependencies>
</dependencyManagement>
```

Sau đó khai báo `spring-boot-starter-kafka` trong `<dependencies>` mà không chỉ định phiên bản riêng. Giá trị `${spring-boot.version}` phải thống nhất với phiên bản Spring Boot mà dự án lựa chọn.

Đối với dự án Spring Boot 3.x, dependency tương ứng thường là:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
```

Vẫn sử dụng Spring Boot dependency management để quản lý phiên bản; không tự chọn một phiên bản Spring Kafka bất kỳ rồi ghép với Boot 3.x.

## 4. Khai báo dependency bằng Gradle

Với Gradle Groovy DSL, dự án Spring Boot 4.x có thể khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
}
```

Với Gradle Kotlin DSL (`build.gradle.kts`):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-kafka")
}
```

Các ví dụ trên giả định dự án đã áp dụng Spring Boot Gradle plugin hoặc cơ chế dependency management tương ứng để quản lý phiên bản. Nếu dự án dùng Spring Boot 3.x, dependency thường dùng là `org.springframework.kafka:spring-kafka`:

```kotlin
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
}
```

Không khai báo đồng thời starter Kafka và một phiên bản `spring-kafka` khác chỉ để ép nâng/hạ version. Nếu có nhu cầu override, cần làm theo hướng dẫn tương thích của đúng dòng Spring Boot và kiểm tra toàn bộ dependency graph.

## 5. Dependency dùng cho kiểm thử

Kiểm thử producer/consumer có thể cần thư viện test riêng. Với Spring Boot 4.x, có thể thêm Kafka test starter:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
```

Với Spring Boot 3.x hoặc dự án khai báo Spring Kafka trực tiếp, thường dùng:

```kotlin
dependencies {
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

Test dependency cung cấp công cụ hỗ trợ kiểm thử tích hợp, chẳng hạn broker nhúng và tiện ích kiểm tra listener. Chỉ thêm dependency test vào test scope (`testImplementation` hoặc Maven `<scope>test</scope>`), không đóng gói nó vào runtime của ứng dụng. Việc chọn test broker và cách khởi chạy broker cần phù hợp với phiên bản Kafka client và phiên bản Spring Kafka đang sử dụng.

## 6. Starter đưa những thành phần nào vào ứng dụng?

Với Spring Boot 4.x, `spring-boot-starter-kafka` kéo theo phần tích hợp Kafka của Spring Boot và Spring Kafka. Từ đó ứng dụng có thể sử dụng các thành phần tiêu biểu:

| Thành phần | Vai trò |
|---|---|
| Spring Boot Kafka auto-configuration | Đọc cấu hình `spring.kafka.*` và tạo hạ tầng phù hợp trong ApplicationContext |
| `ProducerFactory` | Tạo và quản lý Kafka producer |
| `KafkaTemplate` | API gửi record từ service nghiệp vụ |
| `ConsumerFactory` | Tạo Kafka consumer theo cấu hình |
| Listener container factory | Tạo listener container cho các endpoint nhận message |
| `@KafkaListener` infrastructure | Phát hiện endpoint và kết nối phương thức listener với container |
| `KafkaAdmin` | Hỗ trợ thao tác quản trị Kafka, ví dụ khai báo topic bằng `NewTopic` |

Đây là các abstraction của Spring; Kafka broker vẫn là tiến trình riêng. Khi ứng dụng khởi động, Boot tạo bean dựa trên classpath, cấu hình và các bean tùy chỉnh đã khai báo. Nếu ứng dụng cung cấp factory hoặc template riêng, cần cấu hình rõ để listener và publisher sử dụng đúng bean.

Với ứng dụng Spring Framework không dùng Boot, chỉ thêm `spring-kafka` sẽ không tự động tạo toàn bộ hạ tầng. Bạn phải khai báo `ProducerFactory`, `KafkaTemplate`, `ConsumerFactory`, listener container factory và bật xử lý annotation bằng `@EnableKafka` theo nhu cầu.

## 7. Cấu hình kết nối tối thiểu

Sau khi khai báo dependency, tạo `application.yml` hoặc bổ sung các thuộc tính sau vào file cấu hình hiện có:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: spring-kafka-messaging
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

app:
  kafka:
    topic: messaging-demo
```

Ý nghĩa các thuộc tính chính:

- `bootstrap-servers`: địa chỉ broker mà ứng dụng dùng để khởi tạo kết nối và lấy metadata. Có thể khai báo nhiều broker, phân tách bằng dấu phẩy.
- `consumer.group-id`: tên consumer group mặc định. Các instance cùng group sẽ chia nhau partition của topic.
- `consumer.auto-offset-reset`: vị trí bắt đầu khi group chưa có offset hợp lệ; `earliest` yêu cầu đọc từ record cũ nhất còn lưu, `latest` bắt đầu từ record mới được ghi sau khi group tham gia. Thuộc tính này không ghi đè committed offset đang hợp lệ.
- `key-serializer` và `value-serializer`: chuyển key/value thành byte khi producer gửi record.
- `key-deserializer` và `value-deserializer`: chuyển byte về kiểu dữ liệu khi consumer nhận record.
- `app.kafka.topic`: thuộc tính do ứng dụng tự định nghĩa để tránh hard-code tên topic ở nhiều nơi.

Ví dụ dùng `StringSerializer` và `StringDeserializer` để bắt đầu với payload dạng chuỗi. Khi chuyển sang JSON hoặc Avro, cần cấu hình serializer/deserializer và schema tương ứng; không chỉ đổi kiểu generic của `KafkaTemplate` là đủ.

## 8. Tạo publisher và listener đầu tiên

Khi Spring Boot auto-configuration đã hoạt động, có thể inject `KafkaTemplate` trực tiếp:

```java
@Component
public class DemoEventPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final String topic;

    public DemoEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            @Value("${app.kafka.topic}") String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.topic = topic;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String key, String payload) {
        return kafkaTemplate.send(topic, key, payload);
    }
}
```

`KafkaTemplate` được Boot cấu hình từ `spring.kafka.*`. Phương thức `send` trả về future; ứng dụng nên quan sát kết quả để log metadata hoặc xử lý lỗi gửi. Không nên bỏ qua future nếu sự kiện đại diện cho một thay đổi nghiệp vụ quan trọng.

Consumer có thể khai báo bằng `@KafkaListener`:

```java
@Component
public class DemoEventListener {

    @KafkaListener(topics = "${app.kafka.topic}")
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
```

Với Spring Boot và starter Kafka, hạ tầng listener được auto-configure; thông thường không cần tự khai báo `@EnableKafka`. Khi chạy ứng dụng, listener container sẽ kết nối tới broker và poll record. Nếu broker không chạy hoặc địa chỉ `bootstrap-servers` sai, listener có thể không khởi động ổn định và producer không gửi được record.

Ví dụ trên minh họa cách kiểm tra dependency và cấu hình. Trong ứng dụng thật, nên chuyển xử lý nghiệp vụ ra service riêng, thêm event ID, kiểm soát lỗi và thiết kế handler idempotent để chịu được trường hợp record được giao lại.

## 9. Kiểm tra dependency đã được nạp

Sau khi thêm dependency, chạy lệnh phù hợp với build tool để xác nhận starter và các thư viện liên quan xuất hiện trong dependency graph.

**Maven:**

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:*,org.springframework.kafka:*,org.apache.kafka:*
```

**Gradle:**

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
```

Trên Windows có thể dùng `gradlew.bat` thay cho `./gradlew`. Kiểm tra các điểm sau:

1. `spring-boot-starter-kafka` có mặt trong runtime dependency graph đối với dự án Boot 4.x.
2. Có thư viện Spring Kafka và Apache Kafka client tương thích được kéo vào.
3. Không có nhiều phiên bản Spring Kafka hoặc Kafka client bị ép vào cùng runtime ngoài ý muốn.
4. Dependency test chỉ xuất hiện trong test classpath, không nằm trong runtime classpath.

Nếu build không tải được dependency, kiểm tra repository Maven/Gradle, proxy, mạng và phiên bản JDK trước khi đổi phiên bản thư viện.

## 10. Những lỗi thường gặp khi khai báo starter

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không inject được `KafkaTemplate` | Thiếu starter Kafka hoặc auto-configuration không được kích hoạt; cấu hình bean tùy chỉnh chưa đúng | Kiểm tra dependency theo dòng Boot, component/configuration và điều kiện auto-configuration |
| `spring.kafka.*` không có tác dụng | Đang dùng dependency Spring Kafka trực tiếp nhưng thiếu phần tích hợp Boot cần thiết, hoặc YAML sai cấu trúc | Với Boot 4.x dùng `spring-boot-starter-kafka`; kiểm tra indent và tên property |
| `NoClassDefFoundError` hoặc `NoSuchMethodError` | Phiên bản Spring Kafka, Spring Framework hoặc Kafka client không tương thích | Dùng Boot BOM; bỏ version override không cần thiết và xem dependency tree |
| Listener không nhận được record | Broker không truy cập được, topic sai, group không được gán partition hoặc deserializer lỗi | Kiểm tra broker, topic, group, partition assignment và log listener |
| Producer gửi lỗi serialization | Serializer không hỗ trợ kiểu payload hoặc cấu hình producer không khớp kiểu dữ liệu | Đồng bộ serializer/deserializer và kiểu key/value |
| Build thành công nhưng chạy không kết nối được Kafka | Starter chỉ cung cấp thư viện phía ứng dụng, broker chưa chạy hoặc địa chỉ sai | Khởi động Kafka và xác minh `bootstrap-servers` |

Không giải quyết lỗi bằng cách thêm nhiều phiên bản dependency một cách thử-sai. Hãy xác định dòng Spring Boot, để BOM quản lý phiên bản và kiểm tra dependency graph trước khi thay đổi cấu hình.

## 11. Quy trình khởi tạo đề xuất

1. Xác định phiên bản Spring Boot và JDK được dự án hỗ trợ.
2. Chọn dependency phù hợp: Boot 4.x dùng `spring-boot-starter-kafka`; Boot 3.x làm theo hướng dẫn đúng phiên bản, thường khai báo `spring-kafka`.
3. Để Spring Boot dependency management quản lý phiên bản; tránh pin riêng Kafka client và Spring Kafka khi chưa có yêu cầu tương thích cụ thể.
4. Thêm cấu hình `bootstrap-servers`, group ID và serializer/deserializer tối thiểu.
5. Xác nhận dependency graph và đảm bảo Kafka broker đang hoạt động.
6. Inject `KafkaTemplate`, khai báo `@KafkaListener`, sau đó kiểm tra một record đi hết luồng gửi và nhận.
7. Bổ sung cấu hình JSON, retry, dead-letter, transaction và test theo nhu cầu nghiệp vụ ở các bước tiếp theo.

## 12. Tổng kết

- `spring-boot-starter-kafka` là starter chính thức của Spring Boot 4.x để tích hợp Apache Kafka.
- Dự án Spring Boot 3.x có thể dùng `org.springframework.kafka:spring-kafka` theo hướng dẫn tương ứng với phiên bản Boot đó.
- Dùng Maven hoặc Gradle và để Spring Boot BOM quản lý phiên bản dependency.
- Starter cung cấp tích hợp phía ứng dụng như `KafkaTemplate`, consumer factory và listener infrastructure; nó không cài đặt Kafka broker.
- `spring.kafka.*` cấu hình kết nối và hành vi producer/consumer; serializer/deserializer phải tương thích với kiểu dữ liệu.
- Xác minh dependency tree trước khi xử lý lỗi thiếu bean hoặc xung đột phiên bản.

Sau khi dependency và kết nối cơ bản hoạt động, dự án đã có nền tảng để triển khai các luồng publish-subscribe bằng `KafkaTemplate` và `@KafkaListener`, rồi mở rộng sang các cơ chế tin cậy và vận hành của Spring Kafka.

## Tài liệu tham khảo

- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot Reference — Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring for Apache Kafka — Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html)
