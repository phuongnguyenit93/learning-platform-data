# Xác định phiên bản Spring Framework, Java và thư viện giao thức tương thích

## Mục tiêu

Khi thêm messaging vào một ứng dụng Spring, cần chọn một bộ phiên bản có thể cùng biên dịch, chạy và giao tiếp với hệ thống đích. Không thể kết luận tương thích chỉ bằng cách nhìn số major của Spring Framework. Phải kiểm tra cả JDK, module Spring, dự án tích hợp, Java client của giao thức và phiên bản broker/provider.

Sau bài này, có thể:

- Xác định JDK dùng để build và JDK thực tế trên môi trường chạy.
- Chọn đúng thế hệ Spring Framework theo yêu cầu Java và namespace Jakarta.
- Tra cứu phiên bản tương thích của Spring Integration, Spring AMQP, Spring for Apache Kafka và Spring JMS.
- Quản lý dependency bằng BOM để tránh các module Spring bị lệch phiên bản.
- Kiểm tra dependency graph và xác nhận kết nối với broker thật.

## 1. Tương thích là một tập hợp nhiều lớp

Một ứng dụng messaging thường có các lớp phiên bản sau:

| Lớp | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Java runtime | JDK 17, 21 hoặc 25 | JDK tối thiểu mà mọi thư viện yêu cầu; JDK cài trên máy/container chạy ứng dụng. |
| Java compiler target | `--release 17` | Bytecode và Java API mà mã nguồn được phép sử dụng. |
| Spring Framework | `spring-core`, `spring-messaging`, `spring-jms`, `spring-websocket` | Phiên bản framework, baseline JDK và Jakarta EE namespace. |
| Spring integration project | Spring Integration, Spring AMQP, Spring for Apache Kafka | Phiên bản dự án tích hợp hỗ trợ Spring Framework nào. |
| Protocol client | RabbitMQ `amqp-client`, Kafka `kafka-clients`, JMS provider client | Phiên bản Java client tối thiểu và API/protocol mà client hỗ trợ. |
| Server/broker | RabbitMQ, Apache Kafka, ActiveMQ Artemis | Broker hỗ trợ protocol, feature và client version nào. |
| Build/runtime platform | Maven, Gradle, Tomcat, application server, container image | Build tool và môi trường deploy có đáp ứng yêu cầu của thư viện không. |

Hãy phân biệt ba khái niệm:

- **Minimum requirement:** mức thấp nhất được tài liệu dự án công bố. Đây là điều kiện cần, không tự động chứng minh mọi tổ hợp phía trên mức đó đều đã được kiểm thử.
- **Tested/recommended combination:** tổ hợp mà dự án hoặc Spring Boot release train công bố hỗ trợ và kiểm thử.
- **Wire-protocol compatibility:** khả năng Java client và broker trao đổi theo protocol. Điều này độc lập với việc các class Java có tương thích ở compile time hay không.

Ví dụ, `spring-kafka` có thể tương thích với một phiên bản Spring Framework nhưng Kafka broker vẫn cần đáp ứng ma trận client/broker của Apache Kafka. Tương tự, `spring-rabbit` dùng RabbitMQ Java client; phiên bản Spring AMQP không phải phiên bản RabbitMQ server.

## 2. Chọn thế hệ Spring Framework theo JDK và namespace

Mốc tham khảo từ trang hỗ trợ chính thức của Spring Framework tại ngày 07-11-2026:

| Spring Framework | Dải JDK được công bố | Nền tảng Jakarta/Java EE | Trạng thái hỗ trợ cộng đồng |
|---|---|---|---|
| 5.3.x | JDK 8–21 | Java EE 7–8, namespace `javax.*` | Hỗ trợ mã nguồn mở kết thúc tháng 08-2024; còn lựa chọn hỗ trợ thương mại. |
| 6.2.x | JDK 17–25 | Jakarta EE 9–10, namespace `jakarta.*` | Hỗ trợ mã nguồn mở kết thúc tháng 06-2026; có lựa chọn hỗ trợ dài hạn thương mại. |
| 7.0.x | JDK 17–25+ | Jakarta EE 11–12, namespace `jakarta.*` | Thế hệ production hiện tại tại thời điểm ghi bài. |

Spring Framework 6.0 trở lên yêu cầu Java 17+. Framework 7.0 giữ mức JDK tối thiểu là 17, đồng thời khuyến nghị JDK 25 cho production. Các bản JDK LTS được Spring kiểm thử và hỗ trợ gồm 17, 21 và 25; những bản JDK trung gian có thể chỉ được hỗ trợ best-effort.

Các hệ quả quan trọng:

- Ứng dụng còn phụ thuộc thư viện `javax.jms.*`, `javax.servlet.*` hoặc API Java EE cũ cần đánh giá kỹ trước khi chuyển sang Spring 6/7.
- Spring 6/7 dùng namespace `jakarta.*`. Đổi dependency mà không chuyển import và provider API có thể gây lỗi biên dịch hoặc lỗi nạp class.
- Spring Framework 6.2 vẫn có thể chạy trên JDK 17, nhưng thời điểm ghi bài đã hết hỗ trợ mã nguồn mở. Với dự án mới, nên ưu tiên một nhánh còn được hỗ trợ.
- Spring Framework 7.1 đang ở giai đoạn preview/release candidate tại thời điểm ghi bài. Không dùng bản preview cho production nếu chưa chủ động chấp nhận rủi ro phát hành trước GA.

Tham khảo trang [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions) và [Spring Framework Overview](https://docs.spring.io/spring-framework/reference/overview.html).

## 3. Mốc tương thích cho các thư viện messaging

Các dự án Spring có lịch phát hành riêng. Số phiên bản của Spring Integration, Spring AMQP và Spring Kafka không cần giống số phiên bản Spring Framework. Hãy dùng ma trận của chính dự án tích hợp.

### Ví dụ bộ phiên bản thuộc thế hệ hiện tại

Các phiên bản dưới đây là một snapshot tham khảo tại ngày 07-11-2026, không phải một quy tắc cố định cho mọi dự án:

| Thành phần | Phiên bản minh họa | Yêu cầu tương thích quan trọng |
|---|---:|---|
| Java | 17 trở lên | Là baseline của Framework 7.0 và các integration line nêu dưới đây. |
| Spring Framework | 7.0.10 | JDK 17+; Jakarta EE 11 baseline. |
| Spring Integration | 7.1.2 | Java 17+ và Spring Framework 7.0 trở lên. |
| Spring AMQP / `spring-rabbit` | 4.1.2 | Spring Framework tối thiểu 7.0.0; RabbitMQ Java client `amqp-client` tối thiểu 5.28.0. |
| Spring for Apache Kafka | 4.1.2 | Spring Framework 7.0.0; Java tối thiểu 17; dòng Kafka client tương thích là 4.2.x. |
| Spring Boot (nếu dùng) | 4.1.2 | Dùng BOM của Boot để lấy bộ dependency đã được release train quản lý. |

Một số lưu ý khi đọc bảng:

- Spring Integration 7.1.x yêu cầu Spring Framework 7.0 trở lên. Vì vậy Integration 7.1.x có thể đi cùng Framework 7.0.x; không suy luận rằng hai số minor phải giống nhau.
- Spring AMQP 4.1.x yêu cầu Spring Framework 7.0.0 trở lên và `amqp-client` 5.28.0 trở lên. Nếu sử dụng RabbitMQ Streams, còn phải kiểm tra `stream-client`; tài liệu Spring AMQP 4.1 nêu mức tối thiểu 1.5.0.
- Ma trận Spring for Apache Kafka 4.1.x ghép với Kafka clients 4.2.x, Spring Boot 4.1.x và Spring Integration for Apache Kafka 7.1.x. Tài liệu quick tour của Spring Kafka 4.1 cũng xác nhận Spring Framework 7.0.0 và Java 17 là baseline.
- Đây là yêu cầu ở phía thư viện/client. Phiên bản broker Kafka hoặc RabbitMQ vẫn phải được đối chiếu với ma trận của chính broker.

Nguồn: [Spring Integration requirements](https://docs.spring.io/spring-integration/reference/preface.html), [Spring AMQP compatibility](https://docs.spring.io/spring-amqp/reference/introduction/quick-tour.html), [Spring Kafka quick tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html), [Spring Kafka client compatibility matrix](https://spring.io/projects/spring-kafka), [Spring projects and release lines](https://spring.io/projects).

## 4. Kiểm tra theo từng protocol

### JMS

Spring JMS là module của Spring Framework, sử dụng API JMS do provider cung cấp.

- Với Spring Framework 5.x, ứng dụng thường làm việc với namespace `javax.jms.*` và provider thuộc thế hệ Java EE cũ.
- Với Spring Framework 6.x/7.x, dùng namespace `jakarta.jms.*`. Cần chọn JMS provider/client cung cấp đúng Jakarta Messaging API mà framework yêu cầu.
- Kiểm tra phiên bản client của provider (ví dụ ActiveMQ Artemis hoặc một JMS provider khác), phiên bản broker, transaction mode và các tính năng JMS đang sử dụng.
- Không đưa đồng thời hai API `javax.jms` và `jakarta.jms` vào classpath rồi kỳ vọng chúng thay thế được cho nhau. Tên package khác nhau nên đây là hai kiểu Java khác nhau.

Khi nâng từ Spring 5 lên Spring 6/7, lỗi `ClassNotFoundException: javax.jms...` hoặc lỗi không tìm thấy class `jakarta.jms...` thường cho thấy API/provider không cùng thế hệ.

### RabbitMQ qua Spring AMQP

Các thành phần cần đối chiếu:

1. Spring Framework.
2. Spring AMQP và module `spring-rabbit`.
3. RabbitMQ Java client `com.rabbitmq:amqp-client`.
4. RabbitMQ server và các tính năng broker được sử dụng.

Spring AMQP 4.1.2 yêu cầu Spring Framework 7.0.0 trở lên và `amqp-client` 5.28.0 trở lên. Khi dùng RabbitMQ Streams, kiểm tra thêm `stream-client` theo tài liệu của đúng nhánh Spring AMQP.

Không tự nâng `amqp-client` lên một major mới chỉ vì Maven Central đã có bản mới. Spring AMQP có thể phụ thuộc vào API cụ thể của client. Hãy dùng phiên bản được Spring AMQP release train hỗ trợ, rồi xác nhận broker server có hỗ trợ protocol và feature cần thiết.

### Apache Kafka qua Spring for Apache Kafka

Các thành phần cần đối chiếu:

1. Spring Framework.
2. Spring for Apache Kafka (`spring-kafka`).
3. Apache Kafka Java client (`kafka-clients`).
4. Kafka broker và protocol/API version.
5. Nếu dùng Spring Integration Kafka adapter, kiểm tra thêm phiên bản `spring-integration-kafka`.

Theo ma trận Spring Kafka, nhánh 4.1.x tương thích với Kafka clients 4.2.x, Spring Boot 4.1.x và Spring Integration for Apache Kafka 7.1.x. Đừng lấy phiên bản Kafka broker thay cho phiên bản `kafka-clients`: đây là hai sản phẩm khác nhau.

Khi đổi Kafka client, hãy kiểm tra ma trận client/broker của Apache Kafka, các API broker được client sử dụng, serializer/deserializer, authentication mechanism và cấu hình TLS/SASL. Một ứng dụng biên dịch thành công chưa chứng minh client đã kết nối và sử dụng được broker production.

### WebSocket và STOMP

`spring-messaging` và `spring-websocket` là các module thuộc cùng phiên bản Spring Framework; hãy để Framework BOM quản lý chúng cùng nhau.

Nếu dùng simple broker tích hợp sẵn, nó chỉ hỗ trợ một tập con các STOMP command và không có đầy đủ tính năng của một broker chuyên dụng. Nếu dùng broker relay, broker ngoài phải hỗ trợ STOMP và các tính năng mà ứng dụng yêu cầu. Kiểm tra phiên bản STOMP, heartbeat, acknowledgement, authentication và cấu hình TCP/TLS.

Tham khảo [Spring WebSocket message flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html) và [external STOMP broker relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html).

## 5. Quy trình chọn phiên bản

Thực hiện theo thứ tự sau để tránh chọn dependency trước khi biết môi trường chạy:

1. **Chốt môi trường Java.** Ghi rõ JDK dùng ở máy build, IDE, CI, container và production. Nếu production chỉ có JDK 17 thì không thể phát hành bytecode yêu cầu Java 21.
2. **Chọn nhánh Spring Framework còn được hỗ trợ.** Kiểm tra baseline JDK, Jakarta EE namespace, thời gian hỗ trợ và các API đã bị loại bỏ.
3. **Chọn Spring integration project.** Đọc mục Requirements/Compatibility của đúng nhánh Spring Integration, Spring AMQP hoặc Spring Kafka. Kiểm tra cả minimum Spring Framework và minimum Java.
4. **Chọn protocol client.** Kiểm tra client version do thư viện Spring yêu cầu hoặc release train quản lý. Không tự pin một client major mới nếu chưa có xác nhận tương thích.
5. **Kiểm tra broker/provider.** Đối chiếu ma trận client/server của RabbitMQ, Apache Kafka hoặc JMS provider. Kiểm tra thêm protocol, authentication, TLS, serializer và feature.
6. **Quản lý phiên bản tập trung.** Nếu dùng Spring Boot, ưu tiên BOM của Boot. Nếu không dùng Boot, dùng Spring Framework BOM cho các module Framework và khai báo release line của từng dự án tích hợp theo tài liệu chính thức.
7. **Kiểm tra dependency graph đã giải quyết.** Đọc dependency tree và effective POM, không chỉ đọc các version khai báo trực tiếp.
8. **Build và kiểm thử tích hợp.** Chạy test trên đúng JDK mục tiêu và kết nối đến broker cùng major/version dự kiến triển khai.

## 6. Ví dụ Maven khi không dùng Spring Boot

Ví dụ dưới đây minh họa một bộ phiên bản theo thế hệ Framework 7.0 tại ngày 07-11-2026. Nó sử dụng Framework BOM để đồng bộ các artifact thuộc Spring Framework; các dự án Spring Integration, Spring AMQP và Spring Kafka có release line riêng nên được khai báo riêng.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>messaging-version-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
        <spring-integration.version>7.1.2</spring-integration.version>
        <spring-amqp.version>4.1.2</spring-amqp.version>
        <spring-kafka.version>4.1.2</spring-kafka.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>${spring-framework.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>${spring-integration.version}</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.amqp</groupId>
            <artifactId>spring-rabbit</artifactId>
            <version>${spring-amqp.version}</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.kafka</groupId>
            <artifactId>spring-kafka</artifactId>
            <version>${spring-kafka.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ý nghĩa của cấu hình:

- `spring-framework-bom` quản lý phiên bản đồng bộ cho `spring-messaging`, `spring-core`, `spring-context` và các module Framework khác.
- Spring Integration, Spring AMQP và Spring Kafka có nhịp phát hành riêng. Không giả định Framework BOM sẽ quản lý tất cả artifact thuộc các dự án đó.
- Phiên bản Java release là 17. Nếu build bằng JDK 21 hoặc 25, mã vẫn chỉ được biên dịch theo Java 17 API/bytecode.
- Các Java client của RabbitMQ và Kafka thường được kéo theo dependency của integration library. Kiểm tra phiên bản thực tế bằng dependency tree trước khi override.
- Nếu dùng thêm `spring-integration-kafka`, chọn cùng release line Spring Integration 7.1.x và kiểm tra ma trận Spring Kafka tương ứng.

Đây là ví dụ cấu hình dependency, không thay thế việc kiểm tra phiên bản broker và kiểm thử kết nối. Khi dự án dùng một bộ release train khác, hãy thay toàn bộ các version theo ma trận đã xác nhận thay vì thay từng số một cách độc lập.

## 7. Ví dụ khi dùng Spring Boot

Spring Boot cung cấp dependency management BOM được thiết kế và kiểm thử với một tập phiên bản cụ thể của Spring và thư viện bên thứ ba. Khi dùng Boot, cách an toàn thông thường là khai báo starter mà không ghi version riêng:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
</dependencies>
~~~

Không khai báo version độc lập cho `spring-rabbit`, `spring-kafka`, `spring-core` hoặc Kafka/Rabbit client khi BOM đã quản lý chúng, trừ khi có lý do kỹ thuật rõ ràng và đã kiểm thử. Việc override có thể làm lệch bộ dependency mà phiên bản Boot đó đã kiểm thử.

Với Gradle, có thể dùng dependency management plugin của Spring Boot hoặc import BOM bằng Gradle platform. Ví dụ khi dùng native BOM support:

~~~kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.2"))

    implementation("org.springframework.boot:spring-boot-starter-amqp")
    implementation("org.springframework.boot:spring-boot-starter-kafka")
    implementation("org.springframework.boot:spring-boot-starter-integration")
}
~~~

Tham khảo [Spring Boot dependency management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html). Nếu dự án không dùng Spring Boot, không cần thêm Boot chỉ để lấy BOM; có thể quản lý Framework BOM và từng integration release line trực tiếp như ví dụ Maven trước.

## 8. Xác minh JDK và dependency thực tế

Version khai báo trong POM chưa chắc là version cuối cùng Maven chọn. Dependency bắc cầu, dependency management và version override có thể làm thay đổi kết quả.

### Kiểm tra JDK

~~~bash
java -version
javac -version
mvn -v
~~~

- `java -version` cho biết Java chạy lệnh `java` trong shell.
- `javac -version` cho biết compiler được gọi từ PATH.
- `mvn -v` cho biết JDK mà Maven đang sử dụng.
- IDE, CI và container có thể dùng JDK khác shell hiện tại. Hãy kiểm tra từng môi trường.

Trong Maven, `maven.compiler.release` đặt mức Java API và bytecode mục tiêu. Với Gradle, có thể khai báo toolchain và compiler release:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
~~~

Nếu thư viện yêu cầu Java 17 thì đặt target 17 không làm nó chạy được trên Java 11. Runtime vẫn phải đáp ứng baseline của thư viện.

### Kiểm tra dependency graph bằng Maven

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree -Dverbose
mvn clean verify
~~~

- Effective POM cho thấy version sau khi parent POM, BOM và properties được áp dụng.
- Dependency tree cho thấy dependency trực tiếp và bắc cầu, bao gồm phiên bản được chọn và các version bị loại.
- `clean verify` kiểm tra compile, test và các phase verification được cấu hình trong project.

Tập trung kiểm tra các nhóm artifact:

- `org.springframework` — Spring Framework.
- `org.springframework.integration` — Spring Integration.
- `org.springframework.amqp` — Spring AMQP.
- `org.springframework.kafka` — Spring for Apache Kafka.
- `org.apache.kafka` — Kafka Java client.
- `com.rabbitmq` — RabbitMQ Java client.
- `jakarta.jms` hoặc `javax.jms` — JMS API.

### Kiểm tra bằng Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
./gradlew dependencyInsight --dependency amqp-client --configuration runtimeClasspath
./gradlew clean test
~~~

`dependencyInsight` giúp xác định dependency nào yêu cầu một version, version nào được chọn và vì sao Gradle chọn version đó.

## 9. Kiểm thử tương thích với broker/provider

Build thành công chỉ chứng minh mã nguồn và classpath có thể biên dịch/liên kết ở mức nhất định. Để xác nhận bộ phiên bản messaging, cần có integration test hoặc smoke test với broker thực tế.

### Với RabbitMQ

- Dùng đúng RabbitMQ server version dự kiến production.
- Xác nhận kết nối, TLS, username/password hoặc cơ chế xác thực đang dùng.
- Publish một message, nhận message, kiểm tra routing key, exchange, queue và acknowledgement.
- Nếu dùng RabbitMQ Streams, kiểm tra thêm stream plugin và client library tương ứng.

### Với Kafka

- Dùng broker version dự kiến production hoặc môi trường có cùng major/API.
- Xác nhận bootstrap connection, TLS/SASL, topic, partition và consumer group.
- Gửi một record rồi đọc lại bằng consumer; kiểm tra serializer/deserializer, key, headers, offset và commit behavior.
- Đối chiếu Kafka client/broker compatibility matrix của Apache Kafka, đặc biệt khi nâng major.

### Với JMS

- Dùng đúng provider và broker version sẽ triển khai.
- Kiểm tra API namespace (`jakarta.jms` hay `javax.jms`), connection factory, transaction và acknowledgement mode.
- Thử gửi/nhận trong cả luồng thành công và luồng rollback/retry nếu ứng dụng sử dụng các tính năng đó.

### Với STOMP/WebSocket

- Xác nhận broker hỗ trợ STOMP và phiên bản command cần dùng.
- Kiểm tra CONNECT, SUBSCRIBE, SEND, heartbeat, authentication và reconnect.
- Nếu ứng dụng dựa vào ACK/RECEIPT hoặc clustering, không coi simple broker là thay thế tương đương cho một broker STOMP đầy đủ.

## 10. Dấu hiệu thường gặp khi version không tương thích

| Lỗi hoặc biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `UnsupportedClassVersionError` | Runtime Java thấp hơn mức bytecode của ứng dụng hoặc dependency. | `java -version`, `mvn -v`, compiler release và JDK runtime trong container. |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu dependency, sai namespace hoặc thư viện không có trên runtime classpath. | Dependency tree, artifact bị exclude và khác biệt `javax.*`/ `jakarta.*`. |
| `NoSuchMethodError` | Các module cùng thư viện được nạp ở những version không tương thích. | Effective POM, dependency tree, BOM và dependency override. |
| `NoSuchFieldError` hoặc `AbstractMethodError` | API binary giữa caller và implementation không khớp. | Tìm class đến từ JAR nào; đồng bộ các module liên quan. |
| Ứng dụng khởi động nhưng không kết nối broker | Sai endpoint, TLS/SASL, credentials, protocol hoặc broker version. | Log connection, network, broker logs và cấu hình client. |
| Kafka báo lỗi API/version hoặc feature không hỗ trợ | Client và broker không cùng mức hỗ trợ API/feature. | Kafka client/broker compatibility matrix và cấu hình broker. |
| RabbitMQ channel bị đóng hoặc broker từ chối thao tác | Broker không chấp nhận protocol operation, quyền hoặc topology. | RabbitMQ logs, protocol version, permissions, exchange/queue declaration và client docs. |
| JMS không tìm thấy class | Provider kéo API `javax.jms` trong khi ứng dụng yêu cầu `jakarta.jms`, hoặc ngược lại. | Provider client, API dependency và imports. |

Không nên chữa lỗi bằng cách ép tất cả dependency lên version mới nhất. Trước hết xác định class hoặc client nào gây lỗi, xem dependency graph và đối chiếu compatibility matrix của release line tương ứng.

## 11. Checklist trước khi chốt version

- [ ] Đã ghi nhận JDK ở máy build, CI, IDE và production.
- [ ] Compiler release không cao hơn JDK runtime mục tiêu.
- [ ] Spring Framework branch đáp ứng baseline Java và còn chính sách hỗ trợ phù hợp.
- [ ] Namespace `javax.*`/ `jakarta.*` khớp với provider và container.
- [ ] Spring Integration / AMQP / Kafka release line hỗ trợ Framework đang chọn.
- [ ] Java protocol client đáp ứng minimum version và release matrix của adapter.
- [ ] Broker/provider hỗ trợ protocol và feature ứng dụng cần.
- [ ] BOM hoặc dependency management được dùng nhất quán; không có override ngoài ý muốn.
- [ ] Dependency tree không có các module Spring Framework bị lệch phiên bản.
- [ ] Build và test chạy trên đúng JDK mục tiêu.
- [ ] Integration test đã gửi và nhận message qua broker/provider dự kiến production.
- [ ] Đã ghi lại các version trong tài liệu build/deployment để lần nâng cấp sau có thể tái lập.

## Ghi nhớ

Hãy chọn phiên bản theo thứ tự: **JDK runtime → Spring Framework → Spring integration library → protocol client → broker/provider**. Mỗi lớp có ma trận riêng. BOM giúp giữ các dependency trong một release train nhất quán; dependency tree cho biết phiên bản thực sự được nạp; integration test xác nhận đường truyền hoạt động với broker thật.

Số phiên bản trong bài là snapshot ngày 07-11-2026. Trước mỗi lần nâng cấp hoặc tạo project mới, hãy mở lại tài liệu chính thức của đúng release line và kiểm tra ma trận mới nhất thay vì sao chép nguyên các patch version.

## Tài liệu chính thức

- [Spring Framework Versions: JDK range, Jakarta EE level và support status](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions)
- [Spring Framework Reference: Overview](https://docs.spring.io/spring-framework/reference/overview.html)
- [Spring Integration Reference: Requirements](https://docs.spring.io/spring-integration/reference/preface.html)
- [Spring AMQP Reference: Compatibility](https://docs.spring.io/spring-amqp/reference/introduction/quick-tour.html)
- [Spring for Apache Kafka: Compatibility matrix](https://spring.io/projects/spring-kafka)
- [Spring for Apache Kafka Reference: Quick Tour](https://docs.spring.io/spring-kafka/reference/quick-tour.html)
- [Spring Boot: Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Apache Kafka: Compatibility Matrix](https://cwiki.apache.org/confluence/display/KAFKA/Compatibility+Matrix)
