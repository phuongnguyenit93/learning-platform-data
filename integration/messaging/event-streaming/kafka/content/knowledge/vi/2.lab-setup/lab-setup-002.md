# Chọn phiên bản broker, Java client và JDK tương thích

Một môi trường Kafka chỉ hoạt động ổn định khi ba lớp phiên bản khớp nhau: broker chạy trên JDK được hỗ trợ, ứng dụng dùng Java client tương thích với broker, và framework như Spring Kafka được quản lý bằng một bộ dependency phù hợp. Chỉ nhìn số phiên bản Kafka là chưa đủ. Cần kiểm tra cả giao thức client–broker, runtime Java và tương thích API của framework.

Trong module này, người học xây dựng ứng dụng Java/Spring Kafka và thực hành trên broker KRaft. Vì vậy, nên chọn một bộ phiên bản rõ ràng, cố định trong suốt bài lab, ghi lại lựa chọn và chỉ nâng cấp sau khi kiểm tra ma trận tương thích.

## 1. Ba lớp tương thích

### Broker và JDK chạy broker

Broker là tiến trình Kafka Server. JDK của broker phải đáp ứng yêu cầu runtime của đúng phiên bản Kafka đang chạy. Yêu cầu này có thể khác yêu cầu của Java client: một bản Kafka có thể cho phép thư viện client chạy trên JDK thấp hơn JDK tối thiểu của broker.

Ví dụ, tài liệu Kafka 4.4 ghi nhận Java 17, 21 và 25 được hỗ trợ đầy đủ; Java 11 chỉ được hỗ trợ cho một số module như clients và Streams. Kafka 4.0 đã loại bỏ Java 8 và không còn hỗ trợ chạy server bằng Java 11. Vì thế, nếu cùng một máy hoặc container chạy cả broker và ứng dụng, hãy chọn JDK đáp ứng yêu cầu của broker trước. [Tài liệu Java Version của Kafka](https://kafka.apache.org/44/operations/java-version/).

### Java client và broker

Ứng dụng Java không nhúng broker. Nó dùng thư viện `org.apache.kafka:kafka-clients` để gửi request qua Kafka protocol đến broker. Client và broker trao đổi các API như Produce, Fetch, Metadata, FindCoordinator và JoinGroup.

Kafka duy trì khả năng tương thích giao thức theo cả hai chiều trong phạm vi các phiên bản được hỗ trợ: client mới có thể giao tiếp với broker cũ và client cũ có thể giao tiếp với broker mới. Tuy nhiên, điều đó không có nghĩa mọi tính năng mới đều dùng được với mọi broker cũ. API protocol có thể chưa tồn tại ở broker, bị giới hạn bởi phiên bản API tối đa mà hai phía cùng hỗ trợ, hoặc bị loại bỏ ở một major release.

Phải phân biệt **protocol compatibility** với **Java API compatibility**. Một ứng dụng có thể kết nối được đến broker nhưng vẫn không biên dịch hoặc chạy được nếu code sử dụng API đã bị xóa khỏi phiên bản `kafka-clients` mới. Tương tự, nâng client có thể làm lộ khác biệt về cấu hình, serializer, callback hoặc hành vi mặc định.

### Spring Boot và Spring Kafka

`spring-kafka` cung cấp các abstraction như `KafkaTemplate`, `@KafkaListener`, listener container và error handler. Spring Boot bổ sung auto-configuration và dependency management. Vì Spring Kafka phụ thuộc vào Kafka client, phiên bản của ba thành phần Spring Boot, Spring Kafka và `kafka-clients` cần được xem như một bộ.

Khi dùng Spring Boot, hãy ưu tiên dependency management của Spring Boot hoặc starter Kafka tương ứng. Không tự gán một phiên bản `kafka-clients` khác chỉ vì muốn nó trùng số với broker. Tài liệu Spring Kafka xác nhận Boot quản lý phiên bản Kafka dependencies; nếu thực sự cần thay đổi client hoặc Streams, có thể cấu hình thuộc tính `kafka.version` và phải kiểm tra bộ phiên bản được hỗ trợ. [Spring Kafka: Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html).

## 2. Chọn phiên bản broker

### Ưu tiên bản phát hành còn được hỗ trợ

Với môi trường mới, hãy chọn một bản stable thuộc danh sách supported releases của Apache Kafka, sau đó cố định patch version. Không lấy image `latest` cho lab, CI hoặc production vì tag đó có thể trỏ sang bản khác vào lần tải tiếp theo.

Tại thời điểm biên soạn (20-11-2026), trang tải xuống Apache Kafka liệt kê Kafka 4.4.0 là bản phát hành được hỗ trợ, phát hành ngày 22-10-2026. Đây là lựa chọn cụ thể phù hợp cho lab mới trong bài này; nếu học vào thời điểm khác, hãy kiểm tra lại danh sách supported releases và release notes trước khi chốt phiên bản. [Apache Kafka Downloads](https://kafka.apache.org/downloads/).

Ví dụ cố định image cho môi trường lab:

```bash
docker pull apache/kafka:4.4.0
docker run --name kafka-lab -p 9092:9092 apache/kafka:4.4.0
```

Trong một môi trường cần tái lập chính xác hơn, hãy ghi cả image digest bên cạnh tag. Tag cố định giúp tránh tự động đổi patch; digest còn xác định chính xác image bytes được sử dụng.

### Xem xét KRaft và ZooKeeper

Kafka 4.x vận hành bằng KRaft; ZooKeeper-based functionality đã bị loại bỏ từ Kafka 4.0. Nếu đang xây dựng lab mới, chọn Kafka 4.x giúp học mô hình controller quorum hiện hành. Nếu đang nâng cấp một cluster Kafka 3.x cũ dùng ZooKeeper, phải lập kế hoạch migration sang KRaft riêng và làm theo tài liệu nâng cấp của đúng phiên bản. Không thể coi việc thay tag image là một quy trình nâng cấp cluster.

Kafka 3.x có thể vẫn cần thiết khi hệ thống hiện hữu hoặc connector/framework của tổ chức chưa sẵn sàng cho 4.x. Trong trường hợp đó, chọn patch release 3.x còn được hỗ trợ, xác minh yêu cầu JDK và compatibility matrix của phiên bản đó, rồi mới chọn client.

### Không nhầm bản phân phối với thư viện Java

Tên file phân phối như `kafka_2.13-4.4.0.tgz` là gói Kafka server được build với Scala 2.13. Phần `_2.13` là phiên bản Scala của bản phân phối, không phải phiên bản Java client và không có nghĩa ứng dụng Java phải cài Scala 2.13. Ứng dụng Java dùng Maven/Gradle dependency `org.apache.kafka:kafka-clients`.

## 3. Chọn JDK cho broker và ứng dụng

JDK là bộ công cụ và runtime Java; JRE/JVM là phần thực thi bytecode. Trong triển khai hiện đại, image thường đóng gói runtime cần thiết. Cần kiểm tra JDK trong chính môi trường chạy tiến trình, vì JDK trên máy phát triển không bảo đảm giống JDK trong Docker hoặc máy chủ.

Với Kafka 4.4, bảng dưới đây tóm tắt hướng chọn theo tài liệu Java Version của Apache Kafka:

| JDK | Kafka broker 4.4 | Java client 4.4 | Nhận xét |
| --- | --- | --- | --- |
| Java 8 | Không hỗ trợ | Không nên dùng | Đã bị loại bỏ từ Kafka 4.0. |
| Java 11 | Không hỗ trợ cho server | Được hỗ trợ cho nhóm module client/Streams liên quan | Không dùng làm JDK chung cho broker và ứng dụng lab. |
| Java 17 | Hỗ trợ đầy đủ | Hỗ trợ | Mức nền phù hợp với Kafka 4.x và Spring Framework hiện đại. |
| Java 21 | Hỗ trợ đầy đủ | Hỗ trợ | Lựa chọn LTS cân bằng cho lab Java/Spring. |
| Java 25 | Hỗ trợ đầy đủ | Hỗ trợ | LTS mới hơn; xác minh thêm mọi plugin, agent và thư viện bên thứ ba của dự án. |

Đối với lab trong module, có thể dùng **JDK 21** cho cả broker và ứng dụng để giữ cấu hình đơn giản. JDK 17 cũng phù hợp nếu môi trường học tập đã chuẩn hóa ở mức này. Nếu chọn Java 25, cần kiểm tra toàn bộ toolchain và dependency của ứng dụng, dù Kafka 4.4 hỗ trợ đầy đủ phiên bản này. [Ma trận Java chính thức](https://kafka.apache.org/44/operations/java-version/).

### Kiểm tra JDK thực tế

Chạy các lệnh sau trong terminal nơi bạn sẽ build và chạy ứng dụng:

```bash
java -version
javac -version
```

Với Maven Wrapper:

```bash
./mvnw -version
```

Với Gradle Wrapper:

```bash
./gradlew -version
```

Trên Windows PowerShell, dùng wrapper tương ứng là `.\mvnw.cmd -version` và `.\gradlew.bat -version`.

Các lệnh wrapper cho biết JVM mà Maven hoặc Gradle đang sử dụng. Nếu build bằng JDK 21 nhưng chạy container bằng Java 17, ứng dụng vẫn có thể lỗi nếu bytecode hoặc dependency cần Java 21. Hãy xác định rõ Java version dùng để compile (`--release` hoặc toolchain) và Java version dùng để chạy.

## 4. Chọn Java client

### Dùng đúng artifact

Với Java producer, consumer hoặc AdminClient thuần, dependency chính là `org.apache.kafka:kafka-clients`. Ví dụ dùng Kafka 4.4.0 cho lab đồng phiên bản với broker:

**Maven**

```xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-clients</artifactId>
    <version>4.4.0</version>
</dependency>
```

**Gradle**

```kotlin
dependencies {
    implementation("org.apache.kafka:kafka-clients:4.4.0")
}
```

Đồng phiên bản broker và client là cách khởi đầu dễ hiểu cho lab: giảm số biến khi kiểm tra protocol, cấu hình và tính năng. Trong hệ thống thực tế, client không bắt buộc luôn trùng số với broker; có thể chạy khác phiên bản nếu compatibility matrix và yêu cầu tính năng cho phép.

Nếu ứng dụng dùng Kafka Streams, dependency `kafka-streams` nên được căn chỉnh cùng release line với `kafka-clients`, trừ khi tài liệu phiên bản chỉ dẫn khác. Tránh để hai phiên bản Kafka client khác nhau cùng xuất hiện trong runtime classpath.

### Chọn client mới hơn hoặc cũ hơn broker

Trước khi dùng client khác phiên bản broker, hãy trả lời các câu hỏi:

1. Client và broker có hỗ trợ chung các API protocol mà ứng dụng cần không?
2. Client có gửi request hoặc dùng feature chỉ có ở broker mới hơn không?
3. Broker có còn hỗ trợ API version mà client cũ sử dụng không?
4. Phiên bản client có thay đổi hoặc loại bỏ Java API mà code đang dùng không?
5. Nếu dùng Kafka Streams, state store, changelog, EOS và giao thức rebalance có tương thích với runtime broker và phiên bản Streams hiện tại không?

Ma trận compatibility của Apache Kafka 4.x cho biết các client/Streams 3.x có mức tương thích giao thức với broker 4.0, trong khi một số phiên bản client 2.x chỉ tương thích một phần và các client quá cũ không còn tương thích. Đây là ví dụ cho thấy không nên suy luận rằng mọi phiên bản đều giao tiếp được chỉ vì Kafka duy trì tương thích hai chiều. Khi nâng cấp, hãy đọc ma trận của major version đích và hướng dẫn migration. [Kafka Compatibility](https://kafka.apache.org/44/getting-started/compatibility/).

## 5. Nếu ứng dụng dùng Spring Boot

Trong dự án Spring Boot, hãy để Boot quản lý phiên bản Spring Kafka và Kafka client bằng BOM. Dùng starter mà phiên bản Boot cung cấp:

Với Spring Boot 4.x, starter Kafka có tên `spring-boot-starter-kafka`. Với các dòng Spring Boot 3.x, cách khai báo phổ biến là dependency `org.springframework.kafka:spring-kafka` và để BOM của Boot quản lý version. Hãy đối chiếu đúng tài liệu của dòng Boot đang dùng; không sao chép tên starter từ major version khác.

Ví dụ cho Spring Boot 3.x:

**Gradle**

```kotlin
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
}
```

**Maven**

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
```

Trong cả hai trường hợp, không ghi version nếu dự án đang import Spring Boot dependency management/BOM.

**Gradle**

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-kafka")
}
```

**Maven**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka</artifactId>
</dependency>
```

Không khai báo một phiên bản tùy ý cho starter hoặc `kafka-clients` khi Boot đã quản lý dependency. Nếu dùng Spring Kafka trực tiếp ngoài Boot, hãy chọn phiên bản Spring Kafka theo tài liệu của nó, rồi dùng phiên bản `kafka-clients` mà release đó yêu cầu. Ví dụ, tài liệu Spring Kafka 4.1.2 nêu client 4.0.x và Spring Framework 7.0.0 cho quick tour, với Java tối thiểu 17. [Spring Kafka Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html).

Nếu thật sự phải override Kafka client trong ứng dụng Boot, dùng cơ chế dependency management được tài liệu Spring Kafka hướng dẫn, chẳng hạn thuộc tính `kafka.version`; sau đó kiểm tra dependency tree, chạy integration test và xác minh tính tương thích với Spring Kafka đang dùng. Không override chỉ để các con số phiên bản trông giống nhau.

### Kiểm tra phiên bản đã resolve

Với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.apache.kafka:kafka-clients,org.apache.kafka:kafka-streams,org.springframework.kafka:spring-kafka
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
```

Đừng chỉ đọc version khai báo trong `build.gradle` hoặc `pom.xml`. Dependency management, transitive dependency hoặc version conflict có thể khiến runtime nhận một version khác. Kết quả resolve mới là thứ ứng dụng thực sự sử dụng.

## 6. Bộ phiên bản tham khảo cho lab

Với một lab mới, có thể bắt đầu bằng cấu hình sau:

| Thành phần | Lựa chọn lab | Lý do |
| --- | --- | --- |
| Kafka broker | Apache Kafka 4.4.0, KRaft | Bản phát hành được hỗ trợ tại thời điểm biên soạn; phù hợp học KRaft. |
| Broker JDK | JDK 21 | Kafka 4.4 hỗ trợ đầy đủ; LTS và tương thích tốt với hệ sinh thái Java. |
| Java client thuần | `org.apache.kafka:kafka-clients:4.4.0` | Đồng release với broker để đơn giản hóa bài thực hành. |
| Ứng dụng Spring Boot | Boot BOM + starter Kafka mà Boot hỗ trợ | Giữ phiên bản Spring Kafka và Kafka client theo bộ dependency đã kiểm thử. |
| Java compile target | Java 21 | Khớp runtime lab; khai báo rõ toolchain/release trong build. |

Đây là baseline giảng dạy, không phải yêu cầu bắt buộc cho mọi production cluster. Một tổ chức có thể cần Kafka 3.9.x do phụ thuộc cũ, dùng JDK 17, hoặc chạy client khác phiên bản broker. Khi đó, quyết định phải dựa trên support policy của nhà cung cấp, ma trận compatibility và kế hoạch nâng cấp.

## 7. Khai báo Java toolchain

Để tránh IDE, Gradle/Maven và terminal dùng các JDK khác nhau, hãy khai báo toolchain trong build.

**Gradle Kotlin DSL**

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

**Maven compiler**

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

`toolchain` hoặc `maven.compiler.release` xác định phiên bản ngôn ngữ/API mục tiêu khi compile. Chúng không tự cài JDK và cũng không thay thế việc kiểm tra JVM thực tế chạy ứng dụng. Máy build cần có JDK phù hợp; môi trường chạy cần có runtime đáp ứng bytecode đã tạo.

## 8. Xác minh broker và client sau khi khởi động

Sau khi chạy broker, xác minh endpoint có phản hồi và broker quảng bá đúng địa chỉ mà client có thể truy cập. Với Kafka CLI, có thể kiểm tra API versions mà broker hỗ trợ:

```bash
bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```

Lệnh này hữu ích để xác nhận kết nối và xem các API version mà broker công bố. Nó không thay thế integration test cho serializer, authentication, authorization hoặc transaction.

Tiếp theo, chạy một smoke test producer/consumer:

1. Tạo một topic lab có ít nhất một partition.
2. Gửi một record có key và value từ Java producer.
3. Đọc record bằng Java consumer với group ID mới.
4. Khởi động lại consumer với cùng group ID để xác minh hành vi offset.
5. Kiểm tra log và exception nếu client không thể negotiate API hoặc xác thực kết nối.

Với Spring Boot, chạy một integration test dùng đúng dependency đã resolve. Nếu test dùng embedded Kafka, hãy bảo đảm phiên bản `spring-kafka-test`, Kafka client và broker embedded được quản lý nhất quán. Tài liệu Spring Kafka có hướng dẫn riêng cho embedded KRaft broker và dependency override.

## 9. Nhận diện lỗi do sai phiên bản

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM đang chạy thấp hơn phiên bản bytecode được compile hoặc dependency yêu cầu. | Kiểm tra `java -version`, `javac -version`, build tool và runtime image. |
| `NoSuchMethodError` hoặc `ClassNotFoundException` trong package Kafka | Dependency conflict hoặc nhiều phiên bản Kafka client trên classpath. | Dùng `dependency:tree` hoặc `dependencyInsight`; kiểm tra runtime classpath. |
| `UnsupportedVersionException` hoặc lỗi API version | Client và broker không có API protocol chung cho request đang dùng, hoặc tính năng không được hỗ trợ. | Xác minh broker/client versions, API versions và compatibility matrix. |
| Ứng dụng Spring không khởi động do lỗi bean hoặc method | Phiên bản Spring Boot, Spring Kafka hoặc Spring Framework không tương thích. | Kiểm tra BOM, starter và tài liệu tương thích Spring Kafka. |
| Client timeout hoặc không kết nối được | Có thể sai `bootstrap.servers`, listener/advertised listener, DNS, firewall hoặc TLS; chưa chắc là sai version. | Kiểm tra endpoint từ chính môi trường chạy ứng dụng và log broker. |

Không nên xử lý mọi lỗi kết nối bằng cách nâng hoặc hạ Kafka client. Trước hết hãy phân biệt lỗi runtime Java, lỗi dependency, lỗi protocol và lỗi mạng/cấu hình.

## 10. Quy trình chọn và cố định phiên bản

1. Xác định phiên bản broker còn được hỗ trợ và tính năng cần dùng, đặc biệt KRaft hay ZooKeeper ở cluster cũ.
2. Đọc yêu cầu JDK của broker; chọn một JDK LTS được hỗ trợ cho broker và ứng dụng.
3. Nếu dùng Java thuần, chọn `kafka-clients` theo compatibility matrix; đồng phiên bản với broker là baseline đơn giản cho lab.
4. Nếu dùng Spring Boot, để BOM quản lý Spring Kafka và Kafka client; chỉ override khi có lý do và đã xác minh.
5. Cố định version/tag trong build file, Docker Compose hoặc manifest triển khai; tránh `latest`, `+` và version range không kiểm soát.
6. In dependency tree, kiểm tra JDK ở build/runtime và chạy producer-consumer integration test.
7. Ghi phiên bản broker, client, JDK, Spring Boot và Spring Kafka vào README vận hành hoặc tài liệu release của dự án.

Trước mỗi lần nâng cấp, đọc release notes và upgrade guide của cả broker lẫn client. Với Kafka Streams, phải xem thêm runtime compatibility, state store, changelog và quy trình nâng cấp ứng dụng có state. Nâng broker và nâng client là hai thay đổi có thể triển khai theo các nhịp khác nhau; không gộp chúng thành một thao tác thiếu kiểm soát.

## 11. Ghi nhớ

- Broker, Java client và JDK là ba thành phần có ma trận tương thích riêng.
- Kafka 4.x yêu cầu JDK 17 trở lên cho broker; Kafka 4.4 hỗ trợ đầy đủ Java 17, 21 và 25. Java 11 chỉ phù hợp với một số module client/Streams, không phải broker.
- Java producer/consumer sử dụng artifact `org.apache.kafka:kafka-clients`; hậu tố Scala trong tên gói phân phối Kafka không phải phiên bản Java.
- Client và broker có thể khác phiên bản nếu giao thức và tính năng được hỗ trợ; đồng phiên bản là cách đơn giản để bắt đầu lab.
- Ứng dụng Spring Boot nên để BOM quản lý `spring-kafka` và `kafka-clients`; override version phải có chủ đích và được kiểm thử.
- Kiểm tra JVM thực tế, dependency đã resolve, API versions và một luồng gửi/nhận thật trước khi xem môi trường là sẵn sàng.

## Tài liệu tham khảo

- [Apache Kafka Downloads](https://kafka.apache.org/downloads/) — danh sách release được hỗ trợ và gói phân phối.
- [Apache Kafka 4.4 Java Version](https://kafka.apache.org/44/operations/java-version/) — JDK được hỗ trợ cho server, client và Streams.
- [Apache Kafka 4.4 Compatibility](https://kafka.apache.org/44/getting-started/compatibility/) — tương thích server, client và các phiên bản protocol.
- [Apache Kafka Quickstart](https://kafka.apache.org/quickstart/) — yêu cầu Java và cách chạy lab cục bộ.
- [Spring Kafka Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html) — yêu cầu Spring Framework, Java và Kafka client.
- [Spring Kafka: Override Spring Boot Dependencies](https://docs.spring.io/spring-kafka/reference/appendix/override-boot-dependencies.html) — quản lý và override Kafka dependencies trong ứng dụng Boot.
