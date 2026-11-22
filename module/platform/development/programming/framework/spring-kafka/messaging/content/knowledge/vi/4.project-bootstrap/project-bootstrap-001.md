# Chọn starter và phiên bản tương thích

Khi khởi tạo một ứng dụng Spring Kafka, quyết định đầu tiên không phải là chọn một phiên bản Kafka client bất kỳ, mà là xác định nền tảng Spring đang dùng và để các thư viện liên quan đi theo một bộ phiên bản tương thích. Một dự án có thể biên dịch thành công nhưng vẫn gặp lỗi lúc chạy nếu Spring Boot, Spring Framework, Spring Kafka, Kafka client hoặc thư viện kiểm thử bị trộn từ những dòng phiên bản không tương thích.

Spring Kafka cung cấp `KafkaTemplate`, `@KafkaListener`, listener container và các tích hợp với Kafka client. Spring Boot bổ sung auto-configuration và dependency management để giảm cấu hình thủ công. Chọn đúng dependency và dùng đúng bộ phiên bản giúp ứng dụng khởi động ổn định, đồng thời tạo nền tảng cho các bài học tiếp theo về producer, consumer, serialization, retry và transaction.

## 1. Xác định loại ứng dụng trước khi chọn dependency

Có hai cách tích hợp chính:

| Loại dự án | Dependency thường dùng | Cách quản lý cấu hình |
| --- | --- | --- |
| Spring Boot 4.x | `org.springframework.boot:spring-boot-starter-kafka` | Boot starter và auto-configuration |
| Spring Boot 3.x và các dòng Boot cũ hơn | `org.springframework.kafka:spring-kafka` | Dùng Spring Boot dependency management/BOM; Boot auto-configure khi có Spring Kafka trên classpath |
| Spring Framework, không dùng Boot | `org.springframework.kafka:spring-kafka` | Tự quản lý phiên bản và cấu hình producer, consumer, listener container, admin |

Tên dependency có thể thay đổi theo dòng Spring Boot. Vì vậy, hãy xem tài liệu của đúng dòng Boot đang dùng hoặc chọn dependency “Spring for Apache Kafka” trên Spring Initializr. Với Spring Boot 4, Spring Kafka Quick Tour hiện hướng dẫn dùng `spring-boot-starter-kafka`. Với các dòng Boot trước đó, cách tích hợp phổ biến là khai báo `spring-kafka` và để BOM của Boot quản lý phiên bản.

Nếu ứng dụng dùng trực tiếp Spring Kafka, `spring-kafka` là thư viện tích hợp cốt lõi. Không cần khai báo riêng `kafka-clients` trong trường hợp thông thường vì Spring Kafka đã khai báo client phù hợp theo dependency của nó. Chỉ thêm các artifact Kafka khác, chẳng hạn `kafka-streams`, khi ứng dụng thật sự dùng chức năng tương ứng.

## 2. Chọn dependency cho Spring Boot

### Spring Boot 4.x: dùng Kafka starter

Với dự án Spring Boot 4, khai báo starter Kafka do Boot cung cấp. Starter kéo các thành phần cần thiết vào classpath và phối hợp với cơ chế auto-configuration của Boot.

Maven:

```xml
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
```

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

Không ghi version trực tiếp cho các dependency này khi dự án đã dùng Spring Boot parent hoặc BOM. Boot sẽ chọn các phiên bản thuộc bộ dependency mà dòng Boot đó quản lý.

### Spring Boot 3.x và các dòng Boot cũ hơn: dùng `spring-kafka`

Ở các dòng Boot chưa cung cấp Kafka starter riêng, khai báo thư viện Spring Kafka trực tiếp. Auto-configuration của Boot nhận diện các thành phần Kafka trên classpath và có thể tạo các bean phổ biến như `KafkaTemplate`, `KafkaAdmin` và listener container factory mặc định.

Maven:

```xml
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
```

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

Các đoạn trên giả định dự án đã áp dụng Spring Boot dependency management, chẳng hạn qua `spring-boot-starter-parent` trong Maven hoặc plugin/dependency platform tương ứng trong Gradle. Nếu không có BOM, build tool không tự biết phiên bản nào cần dùng; khi đó phải khai báo một bộ phiên bản đã được xác minh tương thích.

### Tạo dự án bằng Spring Initializr

Với dự án mới, có thể chọn phiên bản Spring Boot phù hợp với JDK và chọn dependency **Spring for Apache Kafka** trên Spring Initializr. Initializr tạo cấu hình build tương ứng với dòng Boot được chọn. Sau khi sinh dự án, vẫn cần kiểm tra file `pom.xml` hoặc `build.gradle` để hiểu dependency thực tế và xác nhận dự án đang dùng đúng BOM.

## 3. Dùng Spring Kafka không có Spring Boot

Trong ứng dụng chỉ dùng Spring Framework, khai báo `spring-kafka` với phiên bản cụ thể:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
    <version>${spring.kafka.version}</version>
</dependency>
```

`${spring.kafka.version}` ở đây là property do dự án tự định nghĩa bằng một phiên bản đã kiểm tra trong tài liệu phát hành Spring Kafka. Có thể dùng Gradle tương tự:

```groovy
ext {
    springKafkaVersion = findProperty('springKafkaVersion')
}

dependencies {
    implementation "org.springframework.kafka:spring-kafka:${springKafkaVersion}"
}
```

Property `springKafkaVersion` cần được định nghĩa trong `gradle.properties` bằng phiên bản đã xác minh từ tài liệu phát hành. Khi không dùng Boot, đội phát triển cũng phải cấu hình các thành phần như `ProducerFactory`, `KafkaTemplate`, `ConsumerFactory`, `ConcurrentKafkaListenerContainerFactory` và `KafkaAdmin` theo nhu cầu.

## 4. Hiểu các lớp phiên bản cần tương thích

Một ứng dụng Spring Kafka có nhiều lớp phụ thuộc. Cần kiểm tra chúng theo chuỗi sau:

```text
JDK
  └── Spring Boot (nếu sử dụng)
        ├── Spring Framework
        ├── Spring for Apache Kafka
        │     └── Apache Kafka client (kafka-clients)
        └── Các thư viện kiểm thử liên quan

Kafka broker (môi trường chạy/kiểm thử; kiểm tra tương thích riêng)
```

### JDK và Spring Boot

Spring Boot đặt ra phiên bản Java tối thiểu và các phiên bản Java được hỗ trợ cho mỗi dòng phát hành. Hãy chọn JDK trước, sau đó chọn dòng Boot còn hỗ trợ JDK đó. Không nên chỉ nhìn vào phiên bản Spring Kafka để kết luận dự án chạy được trên JDK hiện tại.

### Spring Boot và Spring Framework

Mỗi dòng Spring Boot được xây dựng trên một dòng Spring Framework tương ứng. Không tự nâng riêng `spring-core`, `spring-context` hoặc các module Spring Framework khác vượt khỏi bộ phiên bản Boot quản lý nếu không có yêu cầu và xác nhận tương thích rõ ràng.

### Spring Kafka và Kafka client

Spring Kafka sử dụng Apache Kafka Java client, thường là artifact `org.apache.kafka:kafka-clients`. Phiên bản Spring Kafka xác định phạm vi client mà nó được phát triển và kiểm thử cùng. Khi dùng Spring Boot, BOM thường quản lý cả hai nhóm dependency. Nếu tự nâng `kafka-clients` nhưng giữ Spring Kafka cũ, có thể gặp thay đổi API, hành vi hoặc lỗi ở runtime.

### Kafka client và Kafka broker

Phiên bản Kafka client trong ứng dụng không nhất thiết phải trùng số phiên bản với Kafka broker. Client và broker giao tiếp qua protocol; khả năng tương tác phụ thuộc ma trận tương thích và tính năng mà ứng dụng sử dụng. Cần kiểm tra tài liệu tương thích của Apache Kafka cho cặp client/broker cụ thể, đặc biệt khi dùng transaction, Admin API, protocol hoặc tính năng mới.

### Thư viện kiểm thử

`spring-kafka-test` nên đi cùng phiên bản Spring Kafka của ứng dụng. Nếu dùng Embedded Kafka, cần kiểm tra thêm phiên bản Kafka server/client mà bộ kiểm thử sử dụng. Nếu dùng Testcontainers, image Kafka trong test cũng cần phù hợp với client và tính năng mà ứng dụng kiểm thử.

Tài liệu Spring Kafka 4.1.2, chẳng hạn, nêu bộ quick tour tương ứng với Kafka Clients 4.0.x, Spring Framework 7.0.0 và Java tối thiểu 17. Đây là ví dụ về cách tài liệu phát hành công bố phạm vi tương thích, không phải quy tắc áp dụng cho mọi phiên bản Spring Kafka. Luôn mở tài liệu đúng phiên bản thư viện của dự án.

## 5. Vì sao nên để Spring Boot BOM quản lý phiên bản?

Spring Boot cung cấp một bộ dependency management đã được kiểm tra cùng nhau. Khi dự án dùng Boot parent hoặc import `spring-boot-dependencies`, có thể khai báo dependency mà không cần lặp lại version ở từng dòng.

Ví dụ, dependency trong Maven không có thẻ `<version>`:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
```

Lợi ích của cách làm này:

- Giảm nguy cơ chọn nhầm phiên bản Spring Kafka không tương thích với Spring Framework.
- Giữ `spring-kafka`, `spring-kafka-test` và Kafka client ở một bộ phiên bản đồng bộ.
- Giúp nâng cấp theo dòng Spring Boot có kiểm soát.
- Làm file build ngắn và dễ review hơn.

BOM không loại bỏ nhu cầu kiểm tra. Khi nâng Boot, cần xem release notes, Java baseline, thay đổi dependency và các cấu hình đã deprecated. Không nên nâng một thư viện đơn lẻ chỉ vì thấy phiên bản mới hơn trên Maven Central.

## 6. Khi nào cần override phiên bản do Boot quản lý?

Chỉ override khi có lý do cụ thể, ví dụ cần một bản sửa lỗi đã được xác nhận, cần dùng tính năng Kafka client mới hoặc phải tương thích với một môi trường broker nhất định. Trước khi override, kiểm tra hướng dẫn của Spring Kafka cho dòng Boot tương ứng và chạy kiểm thử tích hợp.

Tài liệu Spring Kafka có hướng dẫn dùng các property của dependency management như `spring-kafka.version` để thay phiên bản Spring Kafka và `kafka.version` để thay nhóm Kafka client/Streams khi Boot BOM hỗ trợ cách override đó. Tên property và cách cấu hình cần đối chiếu với tài liệu đúng phiên bản Boot.

Ví dụ Maven minh họa việc đặt property, không phải khuyến nghị một con số cụ thể:

```xml
<properties>
    <spring-kafka.version>VERSION_DA_XAC_MINH</spring-kafka.version>
    <kafka.version>KAFKA_CLIENT_VERSION_DA_XAC_MINH</kafka.version>
</properties>
```

Không nên override riêng `kafka-clients` bằng cách thêm một dependency version khác ở cuối file mà không xem dependency mediation. Kết quả có thể là một phần thư viện Kafka ở phiên bản này, phần còn lại ở phiên bản khác. Nếu cần thay đổi, dùng cơ chế override chính thức của BOM và kiểm tra toàn bộ dependency tree.

## 7. Cấu hình kết nối sau khi đã chọn dependency

Sau khi thêm đúng dependency, cấu hình kết nối broker trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
```

Spring Boot có thể auto-configure `KafkaTemplate` và listener container khi Spring Kafka hiện diện trên classpath. Producer, consumer, admin và listener có thể được tinh chỉnh qua nhóm thuộc tính `spring.kafka.*`. Các thiết lập serializer/deserializer, security, retry và transaction nên được bổ sung theo yêu cầu từng bài học, thay vì sao chép một cấu hình lớn khi chưa hiểu tác dụng.

Ví dụ này chỉ minh họa cấu hình tối thiểu để ứng dụng biết địa chỉ broker và consumer group. Nó không tạo Kafka broker và cũng không chứng minh broker đang sẵn sàng. Môi trường local, test và production nên có cấu hình riêng, đặc biệt với địa chỉ kết nối và thông tin xác thực.

## 8. Kiểm tra phiên bản thực tế mà build đã chọn

Đừng chỉ đọc file khai báo dependency; hãy xem phiên bản cuối cùng sau khi Maven hoặc Gradle giải quyết dependency.

Với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.kafka,org.apache.kafka
```

Trên Windows có thể chạy:

```powershell
.\mvnw.cmd dependency:tree -Dincludes=org.springframework.kafka,org.apache.kafka
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
```

Khi xem kết quả, xác nhận:

1. Chỉ có một phiên bản Spring Kafka được chọn trong runtime classpath.
2. `kafka-clients` là phiên bản được Spring Kafka/Boot BOM dự kiến.
3. `spring-kafka-test` khớp với Spring Kafka của ứng dụng.
4. Không có dependency trực tiếp hoặc dependency bắc cầu ép một module Spring Framework sang phiên bản khác ngoài bộ Boot quản lý.
5. Các thư viện Kafka bổ sung như `kafka-streams` (nếu có) cùng một dòng client phù hợp.

Nếu dependency tree hiển thị nhiều phiên bản yêu cầu nhưng chỉ một phiên bản được chọn, hãy đọc các dòng `omitted for conflict` hoặc kết quả `dependencyInsight` để biết dependency nào đã yêu cầu phiên bản khác. Đây là cách tìm nguyên nhân xung đột thay vì thêm một version override theo phỏng đoán.

## 9. Những lỗi thường gặp khi chọn starter và phiên bản

| Lỗi | Hệ quả có thể gặp | Cách xử lý |
| --- | --- | --- |
| Dùng tên starter không có trong dòng Boot đang chọn | Build không tìm thấy artifact | Kiểm tra tài liệu đúng dòng Boot; dùng `spring-kafka` nếu đó là cách tích hợp của dòng đó |
| Khai báo version riêng cho `spring-kafka` trong dự án đã dùng Boot BOM | Có thể lệch khỏi bộ phiên bản Boot kiểm thử | Bỏ version riêng hoặc override qua property được tài liệu hỗ trợ |
| Nâng `kafka-clients` độc lập | Lỗi API hoặc hành vi không tương thích | Kiểm tra ma trận Spring Kafka/client và dùng cơ chế override chính thức |
| Dùng `spring-kafka-test` khác phiên bản với ứng dụng | Lỗi khi chạy kiểm thử hoặc broker nhúng | Để BOM quản lý hoặc đồng bộ phiên bản test artifact |
| Chọn JDK thấp hơn mức tối thiểu của Boot/Spring Kafka | Không biên dịch hoặc không khởi động | Chọn JDK được hỗ trợ hoặc dùng dòng thư viện phù hợp hơn |
| Cho rằng client và broker phải cùng version | Nâng cấp không cần thiết hoặc bỏ qua ma trận protocol | Kiểm tra tài liệu tương thích client/broker và tính năng cần dùng |

## 10. Quy trình lựa chọn đề xuất

Khi bắt đầu một dự án mới, thực hiện theo thứ tự:

1. Xác định JDK mà môi trường build và production có thể sử dụng.
2. Chọn dòng Spring Boot còn được hỗ trợ và tương thích với JDK đó.
3. Chọn dependency Kafka theo dòng Boot: Kafka starter nếu dòng Boot cung cấp; nếu không, dùng `spring-kafka` theo hướng dẫn chính thức.
4. Để Boot BOM quản lý Spring Kafka và Kafka client trong trường hợp thông thường.
5. Kiểm tra broker Kafka dự kiến sử dụng và tính năng cần dùng với tài liệu tương thích client/broker.
6. Thêm `spring-kafka-test` hoặc Testcontainers cho kiểm thử tích hợp với phiên bản phù hợp.
7. Chạy dependency tree, khởi động ứng dụng và thực hiện một bài kiểm thử gửi/nhận với broker thật hoặc broker kiểm thử.

## 11. Kết luận

Chọn starter đúng theo dòng Spring Boot và để dependency management quản lý phiên bản là cách khởi đầu an toàn cho ứng dụng Spring Kafka. Với Spring Boot 4, dùng Kafka starter theo tài liệu Boot hiện hành; với các dòng Boot cũ hơn, khai báo `spring-kafka` và để BOM quản lý phiên bản. Với Spring Framework không dùng Boot, cần chọn phiên bản Spring Kafka tương thích với JDK, Spring Framework và Kafka client rồi tự cấu hình hạ tầng.

Hãy xem JDK, Spring Boot, Spring Framework, Spring Kafka, Kafka client, broker và thư viện kiểm thử như một bộ phụ thuộc cần được xác minh cùng nhau. Chỉ override khi có lý do rõ ràng, kiểm tra dependency tree sau khi thay đổi và chạy kiểm thử tích hợp trước khi đưa cấu hình vào môi trường vận hành.

## Tài liệu tham khảo

- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Kafka — Quick Tour và Compatibility](https://docs.spring.io/spring-kafka/reference/quick-tour.html)
- [Spring Kafka — Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html)
