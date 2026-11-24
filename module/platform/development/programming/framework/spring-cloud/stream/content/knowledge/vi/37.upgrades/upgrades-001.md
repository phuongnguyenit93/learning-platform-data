# Đọc tài liệu đúng phiên bản và ma trận tương thích Spring Cloud

Khi học và nâng cấp Spring Cloud Stream, lỗi thường không xuất phát từ cú pháp Java mà từ việc áp dụng tài liệu của **một thế hệ Spring khác** vào dependency đang chạy. Một ví dụ `@StreamListener` của Spring Cloud Stream cũ không thể được coi là hướng dẫn chuẩn cho dự án dùng functional model `Supplier`/`Function`/`Consumer`. Tương tự, một thuộc tính binder hoặc API của Spring Boot 4 không đương nhiên tồn tại trong dự án Boot 3.

Muốn hiểu chính xác cách cấu hình binding cho Kafka, RabbitMQ hoặc Pulsar, cần xác định cả **phiên bản Spring Boot**, **Spring Cloud release train**, **Spring Cloud Stream/binder** và **thư viện broker bên dưới**. Sau đó mới chọn đúng trang reference, release notes, migration guide và API Javadoc. Bài học trình bày quy trình tra cứu, ví dụ Maven/Gradle, cách kiểm tra dependency thực tế và một kế hoạch nâng cấp có kiểm chứng.

> **Mốc tham chiếu:** Các phiên bản phát hành được nêu trong bảng dưới đây được đối chiếu với thông báo chính thức đến ngày **24/11/2026**. Trạng thái hỗ trợ và patch release có thể thay đổi. Khi triển khai ở thời điểm khác, hãy kiểm tra lại trang Spring Cloud, trang từng dự án và release notes, thay vì xem bảng trong bài là cam kết hỗ trợ vĩnh viễn.

## 1. Vì sao “phiên bản Spring” không chỉ là một con số?

Một ứng dụng Spring Cloud Stream có nhiều tầng:

~~~mermaid
flowchart TD
    A[Java / Gradle / Maven] --> B[Spring Boot]
    B --> C[Spring Cloud release train BOM]
    C --> D[Spring Cloud Stream + Function]
    D --> E[Kafka Binder / Rabbit Binder / Kafka Streams Binder]
    E --> F[Spring Kafka / Spring AMQP / Kafka Streams / Pulsar client]
    F --> G[Kafka / RabbitMQ / Pulsar broker]
~~~

Mỗi tầng có lịch phát hành và yêu cầu tương thích riêng. Ví dụ, có thể thấy trong một dự án:

| Tên/version | Vai trò |
|---|---|
| Spring Boot `4.2.0` | Nền tảng auto-configuration, lifecycle, Actuator và dependency management |
| Spring Cloud `2026.0.0` | Release train/BOM tập hợp các phiên bản Spring Cloud phù hợp |
| Spring Cloud Stream `5.1.0` | Framework binding và functional programming cho message-driven app |
| Kafka binder `5.1.0` | Module tích hợp Spring Cloud Stream với Kafka, được quản lý theo train |
| Kafka client / Spring Kafka | Thư viện kết nối và xử lý Kafka bên dưới, có version riêng |
| Kafka broker | Dịch vụ ngoài ứng dụng, cần xét khả năng tương thích client/protocol |

Đừng suy luận “Spring Cloud 2026.0 nghĩa là Spring Cloud Stream 2026.0”. Spring Cloud dùng **calendar versioning** cho release train, còn project như Spring Cloud Stream có version theo chuỗi riêng. Một train có thể chứa nhiều project với số major khác nhau.

## 2. Ma trận tương thích Spring Boot — Spring Cloud — Stream

Theo bảng Spring Cloud và các thông báo phát hành chính thức:

| Spring Boot | Spring Cloud release train | Spring Cloud Stream | Ghi chú |
|---|---|---|---|
| **4.2.0** | **2026.0.0 — Paddington** | **5.1.0** | GA ngày 20/11/2026 |
| **4.0.x / 4.1.x** | **2025.1.x — Oakwood** | **5.0.x** | Hỗ trợ Boot 4.1.x từ các bản service release phù hợp; `2025.1.5` xác nhận cả hai dòng |
| **3.5.x** | **2025.0.x — Northfields** | **4.3.x** | Kiểm tra support/EOL trước khi dùng |
| **3.4.x** | **2024.0.x — Moorgate** | **4.2.x** | Nhánh cũ, kiểm tra support/EOL |
| **3.2.x / 3.3.x** | **2023.0.x — Leyton** | **4.1.x** | Boot 3.3.x được hỗ trợ từ service release phù hợp |

Đây là bảng theo **nhánh** chứ không phải lời khẳng định mọi tổ hợp patch trong cùng một nhánh đều tương thích. Ví dụ, một bản service release mới có thể mới bổ sung hỗ trợ một patch/minor Boot hoặc sửa vấn đề phát sinh sau nâng cấp. Với production, phải xác minh **cặp phiên bản chính xác**, không chỉ nhìn hai số đầu.

Các bản train có dấu đã hết vòng hỗ trợ nguồn mở trên trang dự án vẫn có thể tồn tại ở Maven Central và có tài liệu reference. **Có artifact tải được không có nghĩa là còn được bảo trì hoặc được nhận security fix.** Với môi trường được hỗ trợ thương mại, cần đối chiếu chính sách riêng và entitlement của tổ chức.

## 3. Release train khác phiên bản một thư viện

Spring Cloud theo định dạng tương tự `YYYY.MINOR.MICRO`, ví dụ:

~~~text
2026.0.0   Spring Cloud release train (Paddington)
5.1.0      Spring Cloud Stream được phát hành trong train trên
4.2.0      Spring Boot version tương thích với train
~~~

Trong một release train:

- `2026` là năm trong tên train, **không phải số major semantic version** của một project.
- `.0` xác định dòng train trong năm; có thể còn train `.1` cùng năm.
- `.0` cuối chỉ bản phát hành cụ thể của train; những bản như `2025.1.5` là service release với fixes/cập nhật.
- Tên như *Paddington*, *Oakwood*, *Northfields* giúp nhận diện dòng nhưng không được dùng thay cho Maven coordinate.

Mỗi module vẫn phát hành artifact theo version của nó. BOM `org.springframework.cloud:spring-cloud-dependencies` xác định những version phối hợp đã được Spring công bố. Đặt một version Spring Cloud Stream thủ công khác BOM có thể kéo theo Spring Cloud Function, Commons hoặc Spring Integration không tương thích.

Một quy tắc an toàn: **chọn Boot trước → chọn Cloud release train phù hợp → dùng BOM → kiểm tra các module mà BOM resolve ra**.

## 4. Nguồn tin nào đáng tin khi đọc tài liệu?

Nên ưu tiên theo thứ tự:

1. **Trang dự án Spring Cloud**: ma trận Boot ↔ release train và liên kết vòng đời hỗ trợ.
2. **Spring Cloud release announcement/release notes**: xác nhận cặp patch mới được hỗ trợ, dự án nào được nâng cấp, breaking changes và security fixes.
3. **Spring Cloud Train Reference**: xem release train đang đưa các project cụ thể lên version nào.
4. **Spring Cloud Stream Reference đã chọn version**: cách cấu hình functional binding, Kafka/Rabbit/Kafka Streams binder, retry/DLQ, partitioning và testing.
5. **Reference/Javadoc của thư viện cấp dưới**: Spring Kafka, Spring AMQP, Apache Kafka/Pulsar API.
6. **Source code, changelog, issue/PR và bài viết cộng đồng**: chỉ dùng để bổ sung, xác minh đúng tag/version; không ưu tiên hơn tài liệu chính thức.

Lưu ý một trang dự án có thể cập nhật bảng tổng quan chậm hơn thông báo GA. Ví dụ, Spring Cloud `2026.0.0` được công bố ngày 20/11/2026 với Spring Boot `4.2.0` và Stream `5.1.0`. Nếu bảng tổng quan chưa kịp hiển thị dòng mới, sử dụng release announcement và trang Train Reference tương ứng để xác minh, rồi kiểm tra lại khi bảng được cập nhật.

## 5. Đừng đọc nhầm trang “current” hoặc “latest”

Trang tài liệu Spring thường có bộ chọn version, gồm **Stable**, **Preview**, **Snapshot** và các bản cũ. URL không ghim version có thể được chuyển sang phiên bản ổn định mới nhất tại thời điểm mở.

Ví dụ các điểm khởi đầu:

~~~text
Spring Cloud Stream 4.3:
https://docs.spring.io/spring-cloud-stream/reference/4.3/index.html

Spring Cloud Stream 5.0:
https://docs.spring.io/spring-cloud-stream/reference/5.0/index.html

Spring Cloud Train Reference:
https://docs.spring.io/spring-cloud-release/reference/index.html
~~~

Đối với Spring Cloud Stream `5.1.0`, đi từ trang Spring Cloud Train `2026.0.0` và chọn liên kết tài liệu của project `spring-cloud-stream 5.1.0`. Không suy đoán rằng một URL tự tạo theo số version sẽ tồn tại hoặc đã cập nhật nội dung; kiểm tra tiêu đề version hiển thị ở đầu trang.

Trước khi dùng ví dụ, ghi lại:

- Tên project và **version hiển thị trong trang**.
- Đường dẫn URL và branch/tag tương ứng.
- Phiên bản của Spring Boot/Cloud trong dự án đang học.
- Tình trạng Stable/Preview/Snapshot.
- Ngày công bố release notes hoặc ngày bản build được phát hành.

Một snippet lấy từ bản `4.3` có thể khác `5.0` hoặc `5.1` ngay cả khi đường dẫn phần hướng dẫn giống nhau. Ngược lại, có nhiều API/thuộc tính không thay đổi; hãy xác minh thay vì tự giả định mọi thứ đều breaking.

## 6. Ví dụ: tìm đúng tài liệu cho Kafka Binder

Giả sử ứng dụng có:

~~~text
Spring Boot          3.5.x
Spring Cloud         2025.0.x
Spring Cloud Stream  4.3.x
Binder               kafka
~~~

Quy trình đọc tài liệu:

1. Mở phần Spring Cloud release train tương ứng và xác nhận Boot `3.5.x` thuộc train `2025.0.x`.
2. Mở reference **Spring Cloud Stream 4.3.x**.
3. Chọn mục **Kafka Binder**, không chọn nhầm **Kafka Streams Binder**.
4. Tìm property consumer/producer trong configuration options của cùng version.
5. Kiểm tra Javadoc của Spring Kafka và Kafka clients **theo version đã resolve** nếu dùng API cấp thấp.
6. Viết test gửi và nhận bằng Kafka broker, xác nhận tên binding, group, key/header, retry/DLQ.

Nếu ví dụ nói đến `KStream`, `KTable`, `StreamsBuilder` hoặc `application.id`, đó có thể là ví dụ của **Kafka Streams Binder** chứ không phải message-channel Kafka Binder nhận `Consumer<Message<T>>` thông thường. Dùng nhầm sẽ dẫn đến cấu hình sai dù hai phần đều có chữ “Kafka”.

Với RabbitMQ, chọn phần **RabbitMQ Binder** tương ứng phiên bản Stream. Với Pulsar, kiểm tra cả việc module Pulsar binder có thuộc phiên bản Stream được hỗ trợ hay không và release notes của Spring for Apache Pulsar/Pulsar client. Không mặc định mọi binder bên thứ ba được Spring Cloud BOM quản lý.

## 7. Sử dụng Spring Cloud BOM trong Maven

Với cặp được công bố ngày 20/11/2026, ví dụ Maven tối giản:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>order-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-stream</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-stream-binder-kafka</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Điểm chính:** Không khai báo version thủ công cho `spring-cloud-stream` và `spring-cloud-stream-binder-kafka`. Spring Cloud BOM sẽ quản lý chúng theo train đã chọn; Spring Boot parent/BOM quản lý phần lớn dependency nền tảng.

`java.version=21` là lựa chọn minh họa cho dự án, không phải kết luận mọi phiên bản Spring Boot đều bắt buộc Java 21. Với một train khác, cần tra Java baseline, Gradle/Maven yêu cầu và container runtime trong reference Spring Boot tương ứng.

Nếu dùng Spring Boot với parent khác, có thể import `spring-boot-dependencies` trong `dependencyManagement` thay parent, nhưng phải quản lý plugin và thứ tự BOM thích hợp. Không ghép dependency management của hai train Spring Cloud khác nhau trong cùng module.

## 8. Sử dụng BOM trong Gradle Kotlin DSL

Ví dụ `build.gradle.kts` dùng Spring Boot Gradle plugin và dependency-management plugin:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.2.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

repositories {
    mavenCentral()
}

val springCloudVersion = "2026.0.0"

dependencyManagement {
    imports {
        mavenBom("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion")
    }
}

dependencies {
    implementation("org.springframework.cloud:spring-cloud-stream")
    implementation("org.springframework.cloud:spring-cloud-stream-binder-kafka")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Đây là một **phương án** quản lý version. Gradle còn hỗ trợ BOM qua `platform(...)` và dependency constraints native. Chọn một chiến lược nhất quán; tránh vừa nhập nhiều BOM bằng các cơ chế khác nhau vừa override version project tùy tiện.

Khi muốn nâng cấp trong cùng một release train, chỉnh version BOM ở một chỗ rồi kiểm tra dependency graph. Khi chuyển train (ví dụ `2025.1.x` sang `2026.0.0`), nâng cấp cả Boot và Cloud theo ma trận, không chỉ đổi một trong hai.

## 9. Version khai báo khác version thực sự được tải

File `pom.xml` hoặc `build.gradle.kts` mô tả mong muốn, nhưng dependency resolution có thể chọn version khác do:

- Dependency transitive từ binder, starter hoặc thư viện thứ ba.
- `dependencyManagement`, BOM import order hoặc Gradle platform constraints.
- Version override ở parent/module khác.
- Forced version, resolution strategy, dependency substitution.
- Một dependency trực tiếp khai báo version không theo BOM.
- Library bên thứ ba đưa vào API Spring cũ hoặc shaded Kafka client.

Để biết **thực tế runtime** đang dùng gì, chạy trên dự án của chính mình:

~~~bash
# Gradle, chỉ là lệnh minh họa; chạy khi có dự án thực tế.
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-stream --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Trong CI, lưu dependency tree hoặc SBOM của artifact đã phát hành. Khi điều tra lỗi, so sánh bản phát hành đang chạy với kết quả resolution chứ không chỉ nhìn biến `springCloudVersion` trong source.

Không thực hiện các lệnh đó trên một kho mã không thuộc phạm vi được phép; trong bài học chúng chỉ là ví dụ thao tác cho người học.

## 10. Kiểm tra Spring Cloud Compatibility Verifier

Spring Cloud Commons có cơ chế `CompatibilityVerifier` nhằm phát hiện một số tổ hợp Spring Boot và Cloud không phù hợp lúc ứng dụng khởi động. Khi được bật và gặp Boot version ngoài dải chấp nhận, ứng dụng có thể dừng và hiển thị thông báo về cặp phiên bản.

Những property cần biết:

~~~yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
      # Danh sách được phép, chỉ minh họa; không tùy tiện ghi đè để ép chạy.
      # compatible-boot-versions:
      #   - 4.2.x
~~~

**Quan trọng:** mặc định của `spring.cloud.compatibility-verifier.enabled` có thể khác theo dòng Spring Cloud Commons; reference configuration của một số phiên bản hiện hành ghi mặc định là `false`. Do đó, không thể chỉ dựa vào việc ứng dụng startup thành công để khẳng định ma trận đã hợp lệ. Hãy xem đúng trang configuration properties và dependency source của phiên bản đã resolve.

Không tắt verifier hoặc tự thêm `compatible-boot-versions` chỉ để vượt thông báo không tương thích. Property này chỉ thay đổi bước kiểm tra, **không** biến một tổ hợp dependency sai thành được hỗ trợ. Kiểm tra lại bảng release train, BOM và release notes trước khi thay đổi cấu hình.

## 11. Phân biệt version của binder và version broker

Spring Cloud Stream có binder khác nhau:

| Binder | Java module cần đọc | Thành phần runtime quan trọng |
|---|---|---|
| Kafka message-channel binder | `spring-cloud-stream-binder-kafka` | Spring Kafka, Kafka client, Kafka brokers |
| Kafka Streams binder | `spring-cloud-stream-binder-kafka-streams` | Kafka Streams library, state store, broker/partition |
| RabbitMQ binder | `spring-cloud-stream-binder-rabbit` | Spring AMQP, RabbitMQ Java client, RabbitMQ server |
| Pulsar binder | Module Pulsar binder đúng dòng Stream | Pulsar client, schema/serialization, Pulsar broker |

Chọn đúng Spring Cloud train mới là **điều kiện cần**, chưa đủ để bảo đảm tương thích với broker production. Cần kiểm tra thêm:

- Version protocol/broker tối thiểu và tối đa mà Java client hỗ trợ.
- Authentication: SASL_SSL, TLS, OAuth, SCRAM, truststore/certificate.
- Kafka `min.insync.replicas`, transactions, idempotence và admin topic provisioning.
- Kafka Streams state directory, RocksDB, changelog, repartition, serde và topology upgrade.
- RabbitMQ quorum/classic queue, publisher confirms, dead-letter exchange và queue arguments.
- Pulsar subscription, acknowledgement, native DLQ, schema registry và phiên bản client.
- Binder bên thứ ba có release tương ứng với train hay không.

Không suy ra phiên bản Kafka broker từ phiên bản Spring Cloud. Client và broker có chính sách tương thích riêng; tra tài liệu Apache Kafka hoặc nhà cung cấp broker theo đúng bản đang chạy.

## 12. Đọc đúng loại tài liệu: Stream, Function hay Kafka Streams?

Một ví dụ trong tài liệu Spring có thể đến từ nhiều tầng khác nhau:

| Thấy trong ví dụ | Nên kiểm tra tài liệu |
|---|---|
| `Consumer<Message<Order>>`, `StreamBridge`, `spring.cloud.stream.bindings` | Spring Cloud Stream core và binder liên quan |
| `Function<KStream<K,V>, KStream<K,R>>` | Spring Cloud Stream Kafka Streams Binder và Apache Kafka Streams DSL |
| `spring.cloud.function.definition` hoặc function composition | Spring Cloud Function + Spring Cloud Stream của cùng version |
| `@KafkaListener`, `Acknowledgment`, `KafkaTemplate` | Spring for Apache Kafka |
| `@RabbitListener`, `RabbitTemplate` | Spring AMQP |
| Pulsar acknowledgement/subscription | Spring for Apache Pulsar và binder cụ thể |
| `@StreamListener`, `@EnableBinding` | Tài liệu Spring Cloud Stream mô hình cũ; cần đối chiếu migration |

Đừng sao chép `@KafkaListener` vào một bài mẫu chỉ yêu cầu functional binder mà bỏ qua các lớp abstraction khác nhau. Cũng đừng kết luận `StreamBridge.send` giống hoàn toàn với gửi bằng `KafkaTemplate`: hai API có lifecycle, error propagation và configuration khác nhau.

Khi đọc code trên diễn đàn, hỏi “Ví dụ này đang hướng tới **version nào, programming model nào, binder nào**?” trước khi dùng.

## 13. Dấu hiệu đã dùng nhầm tài liệu

Các tín hiệu dễ thấy:

- Một import không tồn tại trong dependency graph đang dùng.
- IDE không tìm thấy annotation `@EnableBinding` hoặc interface `Source`/`Sink` trong code mới.
- Property binder được tài liệu ghi nhưng configuration metadata không nhận diện.
- Ví dụ yêu cầu class/method đã deprecated hoặc được chuyển package.
- Tên binding tài liệu dùng `input`/`output`, trong khi functional model hiện tại tạo `processOrder-in-0`/`processOrder-out-0`.
- Một blog dùng Spring Boot 2.x nhưng dự án đang dùng Boot 4.x.
- Spring Cloud release train đã lên major mới còn sample cũ dùng Maven version riêng từng module.
- Ví dụ Kafka Streams dùng API DSL mà project chỉ có message-channel binder.

Không sửa từng import một cách đoán mò. Đầu tiên xác định version và BOM, sau đó chuyển sang reference cùng dòng và kiểm tra migration notes. Nếu API đã bị loại bỏ, cần đổi cách triển khai, không chỉ đổi tên package.

## 14. Đọc release notes trước khi chuyển train

Mỗi khi nâng cấp từ dòng Cloud này sang dòng khác, nên đọc **cả**:

1. Release notes của Spring Boot mới và migration guide từ Boot cũ.
2. Release notes của Spring Cloud release train đích.
3. Spring Cloud Stream release notes và guide của binder đang dùng.
4. Spring Cloud Function/Commons nếu app dùng function routing/composition.
5. Spring Kafka, Spring AMQP, Spring Pulsar và Kafka Streams nếu có API trực tiếp.
6. Security advisories/CVE liên quan đến những module thực sự nằm trên classpath.
7. Deprecation/removal, JDK/Gradle/Maven minimum, configuration property đổi tên và default behavior đổi.

Ví dụ chuyển từ **Boot 3.5 / Cloud 2025.0 / Stream 4.3** sang **Boot 4.2 / Cloud 2026.0 / Stream 5.1** đi qua nhiều thế hệ thay đổi. Không coi đó là patch upgrade.

Thông báo `2026.0.0` có các thay đổi đáng đọc trước khi cập nhật, ví dụ Spring Cloud Bus được chuyển vào Spring Cloud Stream; một số thành phần/reactive Kafka binder hoặc Schema Registry có ghi chú deprecated. Đây là những điểm cần đánh giá nếu dự án đang dùng chúng, không phải lý do tự động loại bỏ mọi dependency có tên tương tự.

## 15. Lập bảng đánh giá ảnh hưởng cho dự án đang chạy

Một mẫu hữu ích trước khi sửa build file:

| Hạng mục | Hiện tại | Mục tiêu | Câu hỏi cần xác minh |
|---|---|---|---|
| Java runtime | 17/21 | Theo Boot đích | Image/JDK build và runtime có phù hợp? |
| Spring Boot | 3.5.x | 4.2.x | Có breaking change trong auto-config và starter không? |
| Spring Cloud | 2025.0.x | 2026.0.x | Release train nào hỗ trợ Boot mục tiêu? |
| Spring Cloud Stream | 4.3.x | 5.1.x | Function binding, content type, error handling có thay đổi? |
| Kafka binder | 4.3.x | 5.1.x | Producer/consumer options có đổi? |
| Kafka Streams binder | Nếu có | Phù hợp train | State store, serde, restore, EOS có đổi? |
| Broker | Kafka/Rabbit/Pulsar | Giữ hoặc nâng | Client protocol, TLS/SASL, schema compatibility? |
| Observability | Metrics/log hiện tại | Không mất chỉ báo | Health endpoint, Micrometer/Actuator có đổi? |
| Triển khai | Container/Kubernetes | Rolling rollout | Probe, SIGTERM, CPU/memory, rollback thế nào? |

Điền số version thật từ `dependency:tree`/`dependencyInsight`. Với ứng dụng có nhiều binder hoặc partner-maintained binder, thêm dòng riêng cho mỗi binder và kiểm tra matrix của nhà cung cấp.

## 16. Quy trình nâng cấp có kiểm chứng

Một workflow thực tế:

~~~mermaid
flowchart TD
    A[Liệt kê dependency thực tế] --> B[Chọn Boot + Cloud train chính thức]
    B --> C[Chọn đúng docs và release notes]
    C --> D[Đổi BOM/plugin và cập nhật code]
    D --> E[Compile + unit + Test Binder]
    E --> F[Integration test với broker thật]
    F --> G{Kết quả và semantics đạt?}
    G -->|Không| H[Phân tích dependency / sửa cấu hình]
    H --> D
    G -->|Có| I[Canary và quan sát lag/DLQ]
    I --> J[Rollout có rollback plan]
~~~

Các bước nên làm lần lượt:

1. Đóng băng baseline đang chạy: version, manifest/dependency tree, schema và cấu hình binder.
2. Kiểm tra mục tiêu vẫn được bảo trì và tương thích Boot/Cloud/Stream.
3. Đổi BOM và Spring Boot plugin/parent theo cặp mục tiêu.
4. Kiểm tra JDK/toolchain và dependency resolution trước khi sửa mã.
5. Sửa các API/thuộc tính bị đổi theo migration guide; tránh override bản transitive tùy tiện.
6. Chạy unit test, Test Binder test rồi test gửi/nhận với broker thật.
7. Kiểm tra restart, retry/DLQ, consumer group offset và state restore nếu có Kafka Streams.
8. Đóng gói image, scan CVE, canary và theo dõi business outcome.
9. Rollout có giới hạn cùng kế hoạch rollback và đánh giá compatibility schema.

Một tổ hợp dependency khởi động thành công nhưng thay đổi behavior retry hoặc commit offset vẫn có thể làm hỏng yêu cầu nghiệp vụ; phải test hành vi, không chỉ test compilation.

## 17. Ma trận kiểm thử riêng cho Spring Cloud Stream

| Kịch bản | Lý do cần kiểm tra sau nâng cấp |
|---|---|
| `Supplier` phát định kỳ | Poller và producer conversion còn đúng? |
| `Function` chuyển đổi payload | Content type, function binding names và routing giữ nguyên? |
| `Consumer` theo group | Offset/ack mode và consumer assignment phù hợp? |
| `StreamBridge` gửi dynamic destination | Binder name, cache, output binding behavior có đổi? |
| Kafka partition key/header | Ordering và partition assignment còn đúng? |
| Kafka retry/DLQ | Message lỗi được thử đúng số lần và đi đúng DLQ? |
| RabbitMQ queue/DLX | Queue arguments và redelivery có thay đổi? |
| Pulsar subscription/ack | Broker/client và binder semantics còn phù hợp? |
| Kafka Streams aggregate/window/join | Store names, changelog, serde, state restore và interactive query? |
| Graceful restart | Không mất message, xử lý duplicate an toàn? |
| Multi-instance deployment | Rebalance, readiness và backlog recovery đạt SLO? |
| Schema evolution | Producer cũ và consumer mới, rồi producer mới và consumer cũ có đọc được? |

Tùy dự án có thể bỏ những dòng không liên quan, nhưng phải kiểm tra cả *đường thành công* và *đường lỗi*. Những test cần broker thật không thể thay hoàn toàn bằng Spring Integration Test Binder chạy trong JVM.

## 18. Xử lý lỗi runtime sau khi đổi train

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
|---|---|---|
| App báo Boot/Cloud không tương thích | Chọn nhầm release train hoặc patch combination | Đối chiếu ma trận và announcement, kiểm tra effective BOM |
| `NoSuchMethodError` / `ClassNotFoundException` | Transitive library bị override hoặc API major thay đổi | Kiểm tra runtimeClasspath và dependency tree |
| Bean binder không được tạo | Thiếu binder artifact, auto-configuration hoặc version lệch | Kiểm tra dependency, conditions report và binder name |
| Property không còn hiệu lực | Tên property/default thay đổi theo version | Mở config options đúng version và metadata configuration |
| Consumer không đọc message | Binding name/destination/group khác trước | Đối chiếu binding, topic, group offset và logs |
| Kafka Streams restore fail | Store/changelog/serde/topology compatibility có vấn đề | Kiểm tra application.id, state.dir, changelog và migration guide |
| Serialization error | Schema/client mismatch | Kiểm tra payload bytes, serializer, contentType và schema ID |
| Retry/DLQ thay đổi | Binder/container error handler config thay đổi | Integration test cho poison message và count attempts |
| Container image chạy khác local | JDK/runtime hoặc environment bị lệch | Kiểm tra image Java version, env, secret, advertised listeners |

Đừng chữa `NoSuchMethodError` bằng cách tự thêm ngẫu nhiên một JAR mới vào classpath. Trước tiên xác định class nào được load từ dependency nào, phiên bản đã resolve và lý do nó bị đưa vào. Sau đó chọn lại dependency theo BOM hoặc nâng đối tác đi kèm.

## 19. Tình huống: bài blog dùng Boot 2 nhưng dự án dùng Boot 4

Giả sử người học tìm được ví dụ:

~~~java
// Ví dụ mang tính lịch sử, không phải khuyến nghị cho dự án mới.
@StreamListener(Sink.INPUT)
public void consume(String payload) {
    System.out.println(payload);
}
~~~

Với functional model của Spring Cloud Stream hiện đại, nên tra tài liệu của version dự án và viết:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<String> processOrder() {
        return payload -> System.out.println(payload);
    }
}
~~~

Binding mặc định là `processOrder-in-0`:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
~~~

Điểm cần học không chỉ là đổi annotation: mô hình binding, discovery function, cách khai báo destination/group và dependency được quản lý theo các thế hệ khác nhau. Các thuộc tính của ví dụ cũ phải được kiểm tra lại trong reference đúng version.

## 20. Không coi “latest” là khuyến nghị nâng cấp vô điều kiện

Đọc tài liệu mới nhất giúp biết tính năng mới, nhưng một dự án production phải cân đối:

- Chương trình hỗ trợ của Spring Boot/Cloud và policy của tổ chức.
- Security fix có trong patch release thuộc **đúng train** hay yêu cầu chuyển train.
- Binder bên thứ ba đã có phiên bản tương thích chưa.
- Broker production, schema registry và client libraries có được kiểm thử cùng nhau không.
- Khả năng canary, rollback và kiểm soát duplicate/event ordering.
- Chi phí thay đổi Java, plugin, dependency, Docker base image và CI.

Không chọn một bản pre-release `-M`, `-RC` hoặc `-SNAPSHOT` cho production chỉ vì đường link nằm cao nhất trong docs. Ngược lại, giữ một train đã hết hỗ trợ vô thời hạn cũng có rủi ro security. Mục tiêu là **phiên bản đang được hỗ trợ, tương thích với hệ thống thực và đã qua test**.

## 21. Checklist tra tài liệu trước mỗi thay đổi

- Đã xác định Spring Boot version đang chạy.
- Đã xác định Spring Cloud release train từ BOM/effective POM.
- Đã xác định Spring Cloud Stream và từng binder từ dependency đã resolve.
- Đã đối chiếu cặp Boot/Cloud với ma trận chính thức và release notes của patch cụ thể.
- Đã kiểm tra Java/toolchain, Maven/Gradle, runtime image và broker versions.
- Đã chọn reference đúng version, không chỉ dựa vào URL “current/latest”.
- Đã phân biệt message-channel Kafka binder với Kafka Streams binder.
- Đã kiểm tra nguồn sample là functional model hay annotation model cũ.
- Đã so khớp property name và default behavior với version binder thực tế.
- Đã đọc migration/deprecation/security notes của Boot, Cloud, Stream và client liên quan.
- Đã kiểm tra thư viện/binder bên thứ ba có hỗ trợ train mới hay chưa.
- Đã tránh override dependency và tắt compatibility verifier chỉ để né lỗi.
- Đã chạy đủ unit, broker integration, restart/retry/DLQ và schema compatibility tests.
- Đã có kế hoạch canary, rollout và rollback cùng các chỉ báo nghiệp vụ.
- Đã ghi lại version/docs URL/dependency graph để đồng đội tái hiện được kết quả.

## Tổng kết

Đọc tài liệu đúng phiên bản là bước đầu của mọi thay đổi Spring Cloud Stream. Hãy chọn **Spring Boot version trước**, xác định **Spring Cloud release train tương thích**, quản lý Spring Cloud Stream và binder bằng **BOM**, rồi đọc **reference và release notes của đúng phiên bản**. Ma trận release train chỉ giải quyết tương thích ở tầng Spring; Kafka/RabbitMQ/Pulsar broker, schema, client và binder bên thứ ba vẫn cần kiểm tra riêng.

Tính đến 24/11/2026, ví dụ mới nhất đã được công bố là Spring Boot `4.2.0`, Spring Cloud `2026.0.0` và Spring Cloud Stream `5.1.0`; trong khi Spring Cloud `2025.1.5` là train cho Spring Boot `4.0.x/4.1.x`. Các cặp này không phải khuyến nghị tự động chuyển production sang bản mới nhất: quyết định nâng cấp phải dựa trên support, dependency thực tế, thay đổi API và kiểm thử dữ liệu end-to-end.

## Tài liệu tham khảo

- [Spring Cloud project — ma trận Spring Boot / Spring Cloud release train](https://spring.io/projects/spring-cloud)
- [Spring Cloud Train Reference — dự án và phiên bản thuộc train](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud 2026.0.0 / Paddington GA, 20/11/2026](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud 2025.1.5 / Oakwood, 20/11/2026](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/)
- [Spring Cloud Stream 5.0 reference](https://docs.spring.io/spring-cloud-stream/reference/5.0/index.html)
- [Spring Cloud Stream 4.3 reference](https://docs.spring.io/spring-cloud-stream/reference/4.3/index.html)
- [Spring Cloud Stream project — binder và release trains](https://spring.io/projects/spring-cloud-stream)
- [Spring Cloud release — supported versions và support policy](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Cloud Commons — compatibility verifier properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Boot project — reference và support](https://spring.io/projects/spring-boot)
