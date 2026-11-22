# Tương thích Spring Boot và kafka-clients

Một ứng dụng Spring Kafka không chỉ có một phiên bản cần quan tâm. Khi build, ứng dụng nhận các thư viện từ Spring Boot, Spring Kafka và Apache Kafka. Khi chạy, Kafka client kết nối đến Kafka broker được triển khai riêng. Khi kiểm thử, dự án còn có thể dùng spring-kafka-test hoặc embedded broker. Các thành phần này có liên quan nhưng không phải một sản phẩm duy nhất và cũng không bắt buộc mang cùng số phiên bản.

Spring Boot cung cấp dependency management thông qua BOM để chọn một tập phiên bản đã được kiểm tra cùng nhau. Spring Kafka xây trên Apache Kafka client API. Vì vậy, khi nâng cấp, cần bảo đảm phiên bản Spring Kafka tương thích với Spring Framework và phiên bản Kafka client mà nó sử dụng; đồng thời kiểm tra Kafka client có giao tiếp được với broker hiện tại hay không.

Bài học hướng dẫn cách đọc quan hệ phiên bản, dùng BOM đúng cách, xác định phiên bản thực tế trong Maven/Gradle, override khi có lý do, phân biệt client với broker, xử lý khác biệt Spring Kafka 3.x/4.x và xây dựng quy trình nâng cấp có kiểm soát.

> Các phiên bản minh họa trong bài được đối chiếu theo tài liệu stable tại ngày 17-11-2026. Đây là ảnh chụp của BOM tại thời điểm tham chiếu; khi triển khai, luôn kiểm tra dependency management của đúng bản Spring Boot đang dùng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt Spring Boot, Spring Framework, Spring Kafka, kafka-clients và Kafka broker.
- Giải thích vai trò của Spring Boot BOM trong việc chọn phiên bản dependency.
- Đọc phiên bản Spring Kafka và Kafka client được Boot quản lý.
- Khai báo dependency đúng cách trong Maven và Gradle.
- Phân biệt cách khai báo Spring Kafka trên Boot 3.x và Boot 4.x.
- Override kafka.version hoặc spring-kafka.version khi có lý do kỹ thuật.
- Phát hiện nhiều phiên bản kafka-clients cùng xuất hiện trong dependency graph.
- Phân biệt tương thích thư viện Java với tương thích giao thức client-broker.
- Kiểm tra yêu cầu Java, Spring Framework và build tool trước khi nâng cấp.
- Nhận diện thay đổi quan trọng khi chuyển từ Spring Kafka 3.x lên 4.x.
- Cập nhật embedded Kafka test theo KRaft.
- Lập ma trận kiểm thử và kế hoạch rollout khi nâng cấp.

## 1. Có những phiên bản nào trong một ứng dụng Spring Kafka?

Một ứng dụng thường có ít nhất năm thành phần phiên bản cần phân biệt:

| Thành phần | Vai trò | Được quản lý ở đâu? |
|---|---|---|
| Spring Boot | Nền tảng ứng dụng, auto-configuration và dependency management | Parent/BOM hoặc Gradle plugin |
| Spring Framework | Container, DI, transaction, retry và các API nền | Thường do Spring Boot quản lý |
| Spring Kafka | KafkaTemplate, @KafkaListener, listener container, error handling và tích hợp Spring | Được Spring Boot BOM quản lý hoặc khai báo trực tiếp |
| Apache Kafka client (kafka-clients) | Producer, Consumer, AdminClient và giao thức nói chuyện với broker | Thường do Spring Boot BOM quản lý thông qua kafka.version |
| Kafka broker | Cluster thực tế lưu partition, nhận produce/fetch và quản lý consumer group | Được triển khai và nâng cấp độc lập với ứng dụng |

Ngoài ra, dự án có thể sử dụng:

- spring-kafka-test để kiểm thử tích hợp.
- kafka-streams nếu dùng Kafka Streams.
- kafka-streams-test-utils cho test topology.
- Schema Registry client, serializer Avro/Protobuf/JSON Schema.
- Kafka Connect client hoặc thư viện vendor.
- Testcontainers hoặc embedded Kafka broker.

Không nên suy ra phiên bản broker từ phiên bản kafka-clients trong pom.xml. Broker thường nằm ở môi trường hạ tầng, container image hoặc dịch vụ Kafka được quản trị riêng.

## 2. Phân biệt Spring Kafka và kafka-clients

spring-kafka là thư viện tích hợp Kafka vào hệ sinh thái Spring. Nó cung cấp abstraction và cơ chế quản lý vòng đời như:

- KafkaTemplate để gửi record.
- @KafkaListener để khai báo listener.
- ConcurrentMessageListenerContainer để quản lý consumer.
- KafkaAdmin và NewTopic để quản lý topic.
- Error handler, retry, DLT và transaction integration.
- Message converter, serializer/deserializer integration và observation.

kafka-clients là thư viện Apache Kafka cung cấp API client cấp thấp:

- KafkaProducer.
- KafkaConsumer.
- AdminClient.
- ProducerRecord, ConsumerRecord.
- Serializer, deserializer và các cấu hình client.
- Network protocol và các request/response với broker.

Spring Kafka gọi API của kafka-clients. Nếu nâng kafka-clients lên một phiên bản có thay đổi API mà Spring Kafka chưa hỗ trợ, ứng dụng có thể lỗi biên dịch hoặc lỗi runtime như NoSuchMethodError.

Ngược lại, nếu Spring Kafka mới cần một API của Kafka client nhưng runtime lại nạp client cũ, ứng dụng cũng có thể khởi động thất bại.

Vì vậy, không nên tự nâng riêng kafka-clients chỉ vì thấy phiên bản Apache Kafka mới hơn. Hãy kiểm tra phiên bản Spring Kafka và dependency management của Spring Boot trước.

## 3. BOM của Spring Boot giải quyết vấn đề gì?

BOM (Bill of Materials) là tập quy tắc quản lý phiên bản dependency. Spring Boot phát hành BOM spring-boot-dependencies chứa các phiên bản thư viện được lựa chọn đồng bộ.

Khi dự án dùng Spring Boot parent hoặc import BOM, các dependency được quản lý có thể khai báo mà không cần ghi version ở từng dependency.

Ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

Maven lấy version của spring-kafka từ dependency management đang có hiệu lực.

Lợi ích:

- Giảm số version phải tự quản lý.
- Giữ Spring Framework và các thư viện Spring cùng một baseline.
- Giảm nguy cơ dependency kéo theo một Kafka client khác với client dự kiến.
- Khi nâng Boot, các dependency được quản lý có thể được nâng đồng bộ.
- Dễ tái lập dependency graph giữa môi trường local, CI và production.

BOM không bảo đảm mọi thư viện bên thứ ba trong ứng dụng đều tương thích. Nó chỉ quản lý các dependency có trong danh sách của BOM và các dependency được kế thừa theo quy tắc build tool. Một thư viện khác có thể khai báo version riêng hoặc kéo theo dependency không cùng baseline.

Tài liệu Spring Boot khuyến nghị dùng Maven hoặc Gradle để tận dụng dependency management và cho phép override khi có nhu cầu cụ thể. Xem [Spring Boot – Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html).

## 4. Ví dụ phiên bản được Spring Boot quản lý

Bảng dưới đây minh họa dependency graph của hai dòng Spring Boot stable tại ngày 17-11-2026:

| Spring Boot | Spring Framework baseline | Spring Kafka | kafka-clients | Java tối thiểu |
|---|---|---|---|---:|
| 3.5.16 | 6.2.19 | 3.3.16 | 3.9.2 | 17 |
| 4.1.2 | 7.0.10 | 4.1.2 | 4.2.2 | 17 |

Các giá trị này được lấy từ system requirements và managed dependency coordinates của từng bản Boot. Hãy xem:

- [Spring Boot 3.5.16 – System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5.16 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.1.2 – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.1.2 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)

Bảng này không có nghĩa Spring Kafka 3.3.16 luôn cần Kafka client 3.9.2 hoặc mọi phiên bản Boot 4 đều dùng Kafka client 4.2.2. Đây là các version cụ thể do BOM của hai bản Boot đang xét lựa chọn.

Khi dùng Spring Boot 3.5.16, dependency management chọn Spring Kafka 3.3.16 và Kafka client 3.9.2. Khi dùng Spring Boot 4.1.2, BOM chọn Spring Kafka 4.1.2 và Kafka client 4.2.2.

Nếu một bản Boot patch mới được phát hành, các giá trị trong BOM có thể thay đổi. Không copy bảng này vào dự án như một bộ version phải pin thủ công.

## 5. Spring Boot 3.x: khai báo Spring Kafka không cần version

Với Spring Boot 3.5, cách thông thường là khai báo trực tiếp spring-kafka và để BOM chọn version.

Maven với Spring Boot parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

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
~~~

Không khai báo version cho spring-kafka, spring-kafka-test hoặc kafka-clients nếu chúng đang được BOM quản lý.

Nếu dự án không dùng Spring Boot parent, có thể import spring-boot-dependencies trong dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo spring-kafka như dependency thông thường mà không cần version.

Spring Boot 3.5 quản lý Spring Kafka trong BOM nhưng không có spring-boot-starter-kafka như starter chính thức của dòng Boot 4. Không lấy ví dụ dependency của Boot 4 áp dụng máy móc cho Boot 3.5.

## 6. Spring Boot 4.x: sử dụng starter Kafka

Spring Boot 4 cung cấp starter chính thức:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka</artifactId>
</dependency>
~~~

Starter đưa các dependency cần thiết và auto-configuration Kafka vào ứng dụng. Version được quản lý bởi Spring Boot BOM.

Với Spring Boot 4.1.2:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu cần sử dụng KafkaTemplate, @KafkaListener hoặc spring.kafka.*, starter này cung cấp tích hợp Spring Kafka. Không cần thêm một version spring-kafka khác bằng tay.

Nếu cần khai báo thư viện Spring Kafka trực tiếp thay vì starter, có thể dùng org.springframework.kafka:spring-kafka và vẫn để BOM Boot quản lý version.

Tài liệu tham khảo: [Spring Kafka Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html) và [Spring Boot Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html).

## 7. Cấu hình Gradle theo Spring Boot BOM

Gradle có thể dùng plugin io.spring.dependency-management hoặc cơ chế BOM native của Gradle.

Ví dụ dùng plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-kafka'
    testImplementation 'org.springframework.boot:spring-boot-starter-kafka-test'
}
~~~

Không cần ghi version cho starter. Spring Boot plugin và dependency management plugin đưa BOM của Boot vào dependency management.

Nếu dùng Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-kafka")
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
~~~

Với Spring Boot 3.5, dependency thường dùng là:

~~~groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

Nếu dùng native BOM support, có thể import BOM bằng platform():

~~~kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.2"))
    implementation("org.springframework.boot:spring-boot-starter-kafka")
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
~~~

Không kết hợp nhiều cơ chế dependency management một cách tùy tiện. Hãy xác định BOM nào là nguồn quản lý chính và kiểm tra version cuối cùng được resolve.

## 8. Không khai báo version riêng cho kafka-clients nếu không cần

Một lỗi phổ biến là thêm kafka-clients với version khác vì muốn sử dụng một API mới:

~~~xml
<!-- Không nên làm nếu chưa kiểm tra compatibility -->
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-clients</artifactId>
    <version>4.2.2</version>
</dependency>
~~~

Nếu Spring Boot 3.5 đang quản lý Spring Kafka 3.3.x và Kafka client 3.9.2, việc ép client lên 4.2.2 có thể tạo ra tổ hợp chưa được hỗ trợ. Spring Kafka có thể gọi API khác với API runtime đang nạp.

Hãy chỉ khai báo trực tiếp kafka-clients khi ứng dụng thực sự dùng API Apache Kafka trực tiếp và có lý do để quản lý dependency đó. Trong trường hợp thông thường, spring-kafka đã kéo theo Kafka client phù hợp.

Nếu cần một version Kafka client khác, hãy kiểm tra:

- Spring Kafka version có hỗ trợ Kafka client đó không?
- Spring Boot BOM có property override tương ứng không?
- Kafka Streams và các module Kafka khác có cần cùng version không?
- spring-kafka-test có sử dụng broker/test dependency tương ứng không?
- Các thư viện khác có kéo thêm kafka-clients version khác không?

Một dependency graph chỉ có một version Kafka client hiệu lực. Nếu nhiều version được khai báo, Maven/Gradle sẽ giải quyết theo quy tắc mediation/constraint. Version cuối cùng có thể không phải version bạn tưởng tượng khi đọc riêng một dòng dependency.

## 9. Override kafka.version khi có lý do

Spring Boot dùng property kafka.version để quản lý phiên bản các module Apache Kafka, bao gồm kafka-clients và các module liên quan như kafka-streams.

Ví dụ dưới đây minh họa property override cho một tổ hợp Spring Kafka 4.1.2 và Kafka client 4.0.0 được tài liệu Spring Kafka dùng làm mẫu. Đây không phải cấu hình mặc định của Spring Boot 4.1.2 và không nên chép sang Boot 3.5:

~~~xml
<properties>
    <kafka.version>4.0.0</kafka.version>
    <spring-kafka.version>4.1.2</spring-kafka.version>
</properties>
~~~

Khi dự án dùng Spring Boot parent hoặc BOM có hỗ trợ property này, các dependency Kafka được quản lý có thể được đổi theo property.

Ví dụ Gradle với io.spring.dependency-management:

~~~groovy
ext['kafka.version'] = '4.0.0'
ext['spring-kafka.version'] = '4.1.2'

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.apache.kafka:kafka-streams'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

Chỉ override khi đã kiểm tra version đó tương thích với Spring Kafka và các module đang dùng.

Không override Kafka client chỉ để đồng bộ số phiên bản với broker. Client và broker có chu kỳ phát hành độc lập; cần căn cứ vào compatibility matrix và API thực tế.

Nếu dùng embedded Kafka, kafka.version cũng có thể ảnh hưởng đến các module broker được sử dụng trong test. Khi đó, phải kiểm thử lại test harness chứ không chỉ kiểm tra compile của ứng dụng.

## 10. Override spring-kafka.version

Spring Kafka cũng có property version trong dependency management của Spring Boot. Có thể dùng spring-kafka.version khi muốn sử dụng một bản Spring Kafka khác với bản BOM mặc định và tổ hợp đó được hỗ trợ.

Maven:

~~~xml
<properties>
    <spring-kafka.version>3.3.16</spring-kafka.version>
</properties>
~~~

Trong ví dụ này, 3.3.16 là version Spring Boot 3.5.16 đang quản lý tại ngày tham chiếu. Giữ nguyên giá trị chỉ pin tường minh version hiện tại; nếu cần đổi, hãy chọn một bản Spring Kafka thuộc dòng tương thích với Spring Framework của Boot đang dùng và kiểm thử lại dependency graph.

Gradle:

~~~groovy
ext['spring-kafka.version'] = '3.3.16'

dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

Property này cần được hiểu là thay version của Spring Kafka family, không phải một công tắc biến mọi tổ hợp Spring Framework thành tương thích.

Ví dụ, không nên lấy Spring Kafka 4.1.x gắn vào một ứng dụng Boot 3.5 chỉ vì có thể ghi đè property. Boot 3.5 dùng Spring Framework 6.2, trong khi Spring Kafka 4.x được xây trên Spring Framework 7.0. Một version override như vậy có thể tạo lỗi class/method ở runtime.

Tương tự, không nâng spring-kafka-test độc lập với spring-kafka. Hai artifact cần cùng một baseline để test framework và runtime framework có API tương thích.

Tài liệu Spring Kafka có hướng dẫn override tại [Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html). Hãy đọc ví dụ theo đúng dòng tài liệu stable đang sử dụng.

## 11. Phân biệt version của client với version của broker

kafka-clients là thư viện chạy bên trong ứng dụng Spring. Kafka broker là server trong cluster. Chúng giao tiếp qua Kafka protocol.

Không có quy tắc bắt buộc client version phải bằng broker version.

Ví dụ:

~~~text
Spring Boot application
  Spring Kafka 3.3.x
  kafka-clients 3.9.x
          |
          | Kafka protocol
          v
Kafka broker cluster 3.9.x
~~~

Hoặc một client mới hơn có thể giao tiếp với broker cũ nếu các API protocol cần thiết còn được hỗ trợ và không sử dụng tính năng chỉ có ở broker mới.

Tương thích client-broker phụ thuộc vào:

- Kafka protocol API versions.
- Tính năng producer/consumer mà ứng dụng sử dụng.
- Các API bị loại bỏ hoặc thay đổi qua major version.
- Metadata version và khả năng của broker.
- Cấu hình consumer group protocol.
- Transaction, idempotent producer và các tính năng broker mới.
- Client library của vendor nếu không phải Apache Kafka client.

Không nên nhìn kafka-clients 4.x rồi kết luận broker phải là 4.x. Cũng không nên suy ra broker 3.x chắc chắn hỗ trợ mọi tính năng mới của client 4.x.

## 12. Kafka 4 client và broker cũ

Kafka 4.0 loại bỏ các protocol API cũ trước 0.10.x. Khi nâng Java client lên Kafka 4.0, tài liệu Apache Kafka yêu cầu broker phải từ 2.1 trở lên; client 4.0 không tương thích với broker cũ hơn ngưỡng đó.

Hãy phân biệt hai chiều kiểm tra. Yêu cầu broker từ 2.1 trở lên ở trên là điều kiện để client 4.0 kết nối tới broker cũ. Ma trận compatibility của Apache Kafka cũng kiểm tra chiều ngược lại: các client 2.1–2.8 chỉ tương thích một phần với broker Kafka 4.0, còn client 3.x được liệt kê là tương thích đầy đủ với broker Kafka 4.0. Không đảo chiều hai kết luận này.

Khi nâng client, hãy kiểm tra ma trận của đúng phiên bản Kafka đích và các API mà ứng dụng sử dụng:

- [Apache Kafka – Compatibility](https://kafka.apache.org/43/getting-started/compatibility/)
- [Apache Kafka – Upgrading](https://kafka.apache.org/40/getting-started/upgrade/)

Các giới hạn này liên quan giao thức client-broker. Chúng không thay thế việc kiểm tra Spring Kafka có tương thích với API Kafka client đã chọn hay không.

## 13. Kafka 4 broker và KRaft là vấn đề khác với Kafka 4 client

Kafka 4 broker chỉ hỗ trợ KRaft; ZooKeeper mode đã bị loại bỏ. Đây là thay đổi của phía server và cách quản lý metadata cluster.

Kafka 4 client không có nghĩa cluster broker bắt buộc phải nâng lên Kafka 4 cùng lúc. Ứng dụng có thể nâng client trước trong phạm vi protocol compatibility, sau đó lên kế hoạch nâng broker riêng.

Khi nâng broker từ Kafka 3.x lên Kafka 4.x:

- Cluster ZooKeeper phải được migrate sang KRaft trước.
- Cluster KRaft cần đáp ứng yêu cầu phiên bản và metadata version.
- Phải kiểm tra quá trình rolling upgrade.
- Phải kiểm tra feature level trước khi finalize upgrade.
- Không giả định có thể downgrade metadata sau khi đã nâng feature level nếu Kafka version không hỗ trợ.

Tài liệu Apache Kafka 4.0 nêu broker có thể được nâng từ các bản 3.3.x đến 3.9.x sau khi đáp ứng điều kiện KRaft; cluster đang dùng ZooKeeper cần migration trước. Xem [Kafka 4.0 Upgrade Guide](https://kafka.apache.org/40/getting-started/upgrade/).

Đừng nhầm thay đổi này với việc nâng dependency kafka-clients trong ứng dụng. Một bên là nâng thư viện client, bên kia là thay đổi nền tảng server và metadata của cluster.

## 14. Yêu cầu Java và build tool

Phiên bản Spring Boot đặt ra yêu cầu runtime và build tool. Phiên bản Kafka client cũng có yêu cầu riêng, nhưng trong ứng dụng Spring Boot cần đáp ứng yêu cầu cao nhất của toàn bộ stack.

Tại ngày tham chiếu:

| Nền tảng | Java tối thiểu | Spring Framework | Build tool |
|---|---:|---|---|
| Spring Boot 3.5.16 | 17 | 6.2.19 trở lên | Maven 3.6.3+, Gradle 7.6.4+ hoặc 8.4+ |
| Spring Boot 4.1.2 | 17 | 7.0.10 trở lên | Maven 3.6.3+, Gradle 8.14+ hoặc 9.x |

Spring Boot 4.1.2 yêu cầu Java 17 trở lên và Spring Framework 7.0.10 trở lên. Boot 3.5.16 yêu cầu Java 17 trở lên và Spring Framework 6.2.19 trở lên.

Không chỉ kiểm tra JDK ở máy developer. Cần kiểm tra:

- JDK trong CI.
- JDK trong Docker image hoặc runtime platform.
- Maven/Gradle wrapper.
- Toolchain được cấu hình trong Gradle.
- maven.compiler.release hoặc Java toolchain.
- Plugin compiler, test và packaging.
- JDK được dùng để chạy test embedded Kafka.

Một project compile bằng JDK 21 local nhưng CI vẫn chạy JDK 17 có thể thất bại nếu bytecode target hoặc plugin được cấu hình không đồng nhất.

## 15. Spring Kafka 4.x có những thay đổi cần chú ý nào?

Nâng từ Spring Kafka 3.3 lên 4.0 là major upgrade, không nên xem như chỉ đổi version trong BOM.

Một số thay đổi đáng chú ý:

| Khu vực | Spring Kafka 3.3 | Spring Kafka 4.0 trở lên |
|---|---|---|
| Spring Framework | Dòng 6.x | Dòng 7.x |
| Kafka client baseline | Dòng 3.x | Kafka 4.0 trở lên |
| Embedded Kafka | Có thể dùng hạ tầng ZooKeeper hoặc KRaft tùy cấu hình | Chỉ KRaft |
| EmbeddedKafkaZKBroker | Còn tồn tại | Bị loại bỏ |
| EmbeddedKafkaRule JUnit 4 | Có | Bị loại bỏ |
| Retry API | Dựa vào Spring Retry trong một số cấu hình | Chuyển sang retry support của Spring Framework 7 và Spring Kafka |
| Annotation backoff | @Backoff | @BackOff |
| Jackson | Jackson 2 là lựa chọn phổ biến | Hỗ trợ Jackson 3, ưu tiên Jackson 3 nếu có |

Spring Kafka 4.0 còn có các thay đổi API khác như constructor của ConsumerRecords, một số API Kafka Streams và các deprecated API bị loại bỏ. Hãy đọc change history và migration guide trước khi nâng cấp.

Nguồn tham khảo: [Spring Kafka Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html).

## 16. Thay đổi retry annotation khi lên Spring Kafka 4

Spring Kafka 4 loại bỏ dependency Spring Retry và dùng retry support của Spring Framework 7. Điều này ảnh hưởng đến một số API và cấu hình retry.

Ví dụ trước đây:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
            delay = 2000,
            maxDelay = 10000,
            multiplier = 2
    )
)
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Trong Spring Kafka 4:

~~~java
@RetryableTopic(
    attempts = "4",
    backOff = @BackOff(
            delay = 2000,
            maxDelay = 10000,
            multiplier = 2
    )
)
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Thay đổi không chỉ là tên annotation. Các kiểu API liên quan Spring Retry như BackOffPolicy, BinaryExceptionClassifier hoặc callback cũ có thể cần chuyển sang API tương ứng của Spring Framework 7/Spring Kafka 4.

Không chỉ sửa tên annotation rồi kết luận upgrade hoàn tất. Hãy tìm các import và class Spring Retry trong code, test và custom error handler.

## 17. Embedded Kafka test thay đổi khi lên Spring Kafka 4

Spring Kafka 4 chỉ còn embedded Kafka chạy KRaft. Các API liên quan ZooKeeper bị loại bỏ.

Những thay đổi cần rà soát:

- EmbeddedKafkaZKBroker bị loại bỏ.
- EmbeddedKafkaKraftBroker là broker implementation.
- EmbeddedKafkaRule của JUnit 4 bị loại bỏ.
- Thuộc tính kraft trong @EmbeddedKafka không còn cần thiết vì KRaft là chế độ duy nhất.
- Các thuộc tính ZooKeeper như zookeeperPort, zkConnectionTimeout, zkSessionTimeout bị loại bỏ.
- Import và test utilities có thể thay đổi package.
- Cấu hình replication factor trong test cần phù hợp với KRaft và số broker.

Ví dụ annotation test theo kiểu mới:

~~~java
@SpringBootTest
@EmbeddedKafka(
    topics = "orders",
    partitions = 3,
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {
    // Integration tests
}
~~~

Không đưa thuộc tính kraft = true vào ví dụ mới vì Spring Kafka 4 không còn lựa chọn ZooKeeper embedded broker.

Nếu dự án vẫn dùng Spring Kafka 3.3, test framework có thể có các API cũ và chế độ KRaft tùy cấu hình. Hãy kiểm tra phiên bản dependency trước khi sao chép test code giữa hai nhánh major.

## 18. Cách kiểm tra dependency graph thực tế

Không chỉ đọc pom.xml hoặc build.gradle. Cần xem version cuối cùng mà build tool đã resolve.

### Maven

Xem tất cả dependency liên quan Kafka:

~~~bash
mvn dependency:tree -Dincludes=org.apache.kafka,org.springframework.kafka
~~~

Xem effective POM và các property sau khi import BOM:

~~~bash
mvn help:effective-pom
~~~

Nếu cần kiểm tra riêng Kafka client:

~~~bash
mvn dependency:tree -Dincludes=org.apache.kafka:kafka-clients
~~~

### Gradle

Xem dependency graph runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm lý do một version được chọn:

~~~bash
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
~~~

Kiểm tra Spring Kafka:

~~~bash
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
~~~

Đặc biệt chú ý:

- Có bao nhiêu version kafka-clients được yêu cầu?
- Version nào thực sự được chọn?
- Dependency nào kéo version đó vào?
- Có kafka-streams khác version với kafka-clients không?
- spring-kafka-test có cùng version với spring-kafka không?
- Có thư viện vendor đóng gói Kafka client riêng không?

Nếu dependency graph chứa nhiều version trong quá trình resolve, hãy tìm nguồn kéo version khác trước khi ép resolution strategy.

## 19. Kiểm tra dependency alignment trong multi-module project

Một dự án có thể gồm nhiều module:

~~~text
messaging-platform
  |
  +-- order-service
  |     +-- spring-kafka
  |
  +-- billing-service
  |     +-- spring-kafka
  |
  +-- event-contract
  |     +-- không cần kafka-clients nếu chỉ chứa DTO
  |
  +-- integration-tests
        +-- spring-kafka-test
        +-- embedded Kafka
~~~

Nếu mỗi module import một BOM khác nhau, runtime hoặc test classpath có thể bị lệch.

Nên:

- Đặt một Spring Boot version thống nhất trong build root khi các service dùng chung build.
- Import một BOM chính cho các dependency Spring.
- Không khai báo version Kafka client rải rác trong từng module.
- Giữ spring-kafka và spring-kafka-test cùng baseline.
- Nếu dùng Kafka Streams, align kafka-streams với Kafka client version.
- Kiểm tra dependency graph của module test riêng, không chỉ module application.
- Tránh để shared library đóng gói hoặc shade một bản kafka-clients khác.

Nếu mỗi service được build/deploy độc lập, mỗi service có thể có BOM riêng. Khi đó, cần kiểm tra protocol compatibility với broker và không giả định tất cả service phải chạy cùng phiên bản client.

## 20. Ma trận kiểm thử khi nâng cấp

Một lần nâng cấp không nên chỉ dừng ở mvn test thành công. Hãy kiểm tra cả build, startup, message flow, broker và test harness.

| Lớp kiểm thử | Điều cần xác minh |
|---|---|
| Compile | Không còn API hoặc import bị loại bỏ |
| Application context | Boot auto-configuration tạo được KafkaTemplate và listener factory |
| Producer | Serializer, key, headers, retry và send result hoạt động |
| Consumer | Deserializer, group membership, offset và rebalance hoạt động |
| Retry/DLT | Error handler, retry topic, recoverer và partition routing đúng |
| Transaction | Producer transaction, offset transaction và rollback đúng |
| Security | SSL, SASL, JAAS, truststore và ACL kết nối được |
| Observability | Metrics, tracing và log không mất thông tin |
| Integration test | spring-kafka-test hoặc Testcontainers hoạt động với client/broker đã chọn |
| Broker compatibility | Client mới nói chuyện được với cluster hiện tại |
| Load test | Latency, throughput, memory và rebalance không suy giảm ngoài dự kiến |

Với upgrade major, nên có một môi trường staging sử dụng phiên bản broker gần production. Embedded Kafka phù hợp cho test logic nhưng không thay thế hoàn toàn kiểm thử với broker triển khai thật, đặc biệt với security, replication, ACL và rolling upgrade.

## 21. Quy trình nâng cấp theo từng lớp

Không nâng đồng thời mọi thành phần trong một thay đổi lớn nếu không có lý do.

Một quy trình tham khảo:

1. **Kiểm kê:** ghi lại Boot, Spring Framework, Spring Kafka, Kafka client, broker, Java và build tool.
2. **Đọc BOM đích:** xác định version Spring Kafka và kafka-clients mà Boot mới quản lý.
3. **Kiểm tra Java:** nâng JDK và build tool nếu bản Boot đích yêu cầu.
4. **Nâng Boot:** đổi parent/plugin/BOM và bỏ version override không còn cần.
5. **Kiểm tra dependency graph:** xác nhận chỉ có một Kafka client version phù hợp.
6. **Sửa API:** cập nhật các API Spring Kafka/Kafka client đã deprecated hoặc removed.
7. **Nâng test:** cập nhật spring-kafka-test, embedded broker, JUnit và KRaft test setup.
8. **Chạy integration test:** kiểm tra producer, consumer, retry, transaction và security.
9. **Kiểm tra broker compatibility:** đối chiếu client mới với cluster đang chạy.
10. **Triển khai staging:** quan sát log, consumer lag, rebalance và throughput.
11. **Rolling rollout:** nâng từng service instance theo kế hoạch, giữ khả năng rollback code khi còn tương thích.
12. **Nâng broker riêng:** nếu cần nâng server, làm theo quy trình upgrade Kafka và migration KRaft của Apache Kafka.

Nếu nâng từ Spring Boot 3.5 lên 4.1, hãy xem đây là migration major vì Spring Framework chuyển từ 6.2 sang 7.0 và Spring Kafka chuyển từ 3.x sang 4.x.

## 22. Tách kế hoạch nâng client và broker

Một kế hoạch có thể chia thành hai đường độc lập:

~~~mermaid
flowchart TD
    A["Kiểm kê dependency và broker"] --> B["Nâng ứng dụng Spring Boot"]
    B --> C["Nâng Spring Kafka / kafka-clients"]
    C --> D["Test với broker hiện tại"]
    D --> E["Triển khai ứng dụng"]
    E --> F["Đánh giá broker upgrade"]
    F --> G{"Cluster đã ở KRaft?"}
    G -->|Có| H["Lập kế hoạch nâng broker"]
    G -->|Không| I["Migration ZooKeeper sang KRaft"]
    I --> H
    H --> J["Rolling upgrade broker"]
    J --> K["Xác minh metadata và feature level"]
~~~

Ví dụ, ứng dụng có thể chuyển sang Spring Kafka 4 và Kafka client 4 trước khi cluster broker nâng major, miễn là client-broker compatibility được xác nhận. Việc nâng broker lên Kafka 4 lại yêu cầu KRaft.

Không đưa thay đổi kafka-clients và broker lên production trong cùng một bước nếu chưa có kế hoạch quan sát và rollback riêng. Nếu xảy ra lỗi, việc tách thay đổi giúp xác định nguyên nhân nhanh hơn.

## 23. Các lỗi thường gặp

**Pin spring-kafka version thủ công trong khi đã dùng Boot BOM.** Dependency có thể lệch khỏi Spring Framework hoặc các module khác. Bỏ version để BOM quản lý, trừ khi có lý do override được xác nhận.

**Nâng riêng kafka-clients.** Spring Kafka có thể gọi API không tồn tại trong client runtime. Kiểm tra compatibility và dependency graph trước.

**Dùng Spring Kafka 4 với Spring Framework 6.** Spring Kafka 4 dựa trên Spring Framework 7. Nâng Boot/Spring Framework theo tổ hợp được hỗ trợ.

**Dùng spring-kafka-test khác version spring-kafka.** Test API và runtime API có thể không tương thích. Align hai artifact.

**Nghĩ Kafka client phải cùng version broker.** Client và broker có thể khác version trong giới hạn protocol compatibility. Kiểm tra ma trận Apache Kafka.

**Nghĩ Kafka 4 client buộc broker phải ở Kafka 4.** Client và broker upgrade là hai việc riêng. Kiểm tra ngưỡng protocol và tính năng đang dùng.

**Nâng Kafka 4 broker khi cluster còn ZooKeeper mode.** Kafka 4 broker chỉ hỗ trợ KRaft. Migration metadata phải được hoàn thành theo hướng dẫn Apache Kafka.

**Dùng EmbeddedKafkaZKBroker sau khi nâng Spring Kafka 4.** API này đã bị loại bỏ. Chuyển sang KRaft test infrastructure.

**Giữ @Backoff khi nâng Spring Kafka 4.** API đã chuyển sang @BackOff và retry support mới. Rà soát import, annotation và custom retry configuration.

**Chỉ chạy unit test.** Unit test không chứng minh broker compatibility, transaction, rebalance hoặc security. Bổ sung integration test với broker phù hợp.

**Chỉ đọc dependency khai báo, không xem dependency được resolve.** Dependency mediation có thể chọn version khác. Dùng dependency:tree hoặc dependencyInsight.

**Dùng một bộ version của bài hướng dẫn cũ cho dự án hiện tại.** BOM thay đổi theo patch release. Kiểm tra tài liệu của đúng version Boot.

## 24. Checklist tương thích trước khi merge

- [ ] Đã xác định Spring Boot version và BOM đang có hiệu lực.
- [ ] Đã xác định Spring Framework version do Boot quản lý.
- [ ] Đã xác định Spring Kafka version được resolve.
- [ ] Đã xác định kafka-clients version thực tế.
- [ ] Đã xác định broker version và broker mode (KRaft/ZooKeeper).
- [ ] Java runtime đáp ứng yêu cầu của Boot và thư viện.
- [ ] Maven/Gradle wrapper đáp ứng yêu cầu build.
- [ ] Không có nhiều Kafka client version ngoài dự kiến.
- [ ] spring-kafka và spring-kafka-test được align.
- [ ] kafka-streams và các Kafka module khác được align nếu sử dụng.
- [ ] Mọi override kafka.version hoặc spring-kafka.version đều có lý do và test.
- [ ] Đã kiểm tra client-broker compatibility matrix.
- [ ] Đã rà API deprecated/removed trong Spring Kafka và Kafka client.
- [ ] Embedded Kafka test đã được cập nhật theo KRaft nếu lên Spring Kafka 4.
- [ ] Retry, DLT, transaction, security và observability đã được kiểm thử.
- [ ] Có kế hoạch rollout và rollback phù hợp.
- [ ] Broker upgrade được lập kế hoạch riêng với application upgrade.

## Kết luận

Tương thích Spring Kafka phụ thuộc vào nhiều lớp: Spring Boot quản lý dependency bằng BOM, Spring Kafka sử dụng API của kafka-clients, còn Kafka broker là hệ thống server giao tiếp qua protocol. Hãy để BOM quản lý version trong trường hợp thông thường, kiểm tra dependency graph thực tế và chỉ override khi đã xác minh tổ hợp tương thích. Khi nâng Spring Boot hoặc Spring Kafka major, cần rà yêu cầu Java/Spring Framework, API retry, embedded Kafka KRaft và các thay đổi Kafka client. Cuối cùng, kiểm thử cả ứng dụng lẫn broker hiện tại trước khi rollout; không suy ra broker version từ client version hoặc coi các số version phải giống nhau.

## Tài liệu tham khảo

- [Spring Boot – Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot – Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot 3.5 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.1 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Kafka – Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html)
- [Spring Kafka – Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html)
- [Spring Kafka – Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [Apache Kafka – Compatibility](https://kafka.apache.org/43/getting-started/compatibility/)
- [Apache Kafka – Upgrade Guide](https://kafka.apache.org/40/getting-started/upgrade/)

