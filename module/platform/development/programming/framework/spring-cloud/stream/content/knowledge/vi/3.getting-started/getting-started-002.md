# Thiết lập Maven hoặc Gradle và quản lý phiên bản phụ thuộc

Một ứng dụng Spring Cloud Stream cần ba nhóm thành phần: nền tảng Spring Boot để khởi chạy ứng dụng, thư viện Spring Cloud Stream để khai báo và vận hành các binding, và binder để kết nối với hệ thống nhắn tin như Kafka, RabbitMQ hoặc Pulsar. Khi tạo dự án, việc chọn đúng dependency và đồng bộ phiên bản giữa Spring Boot với Spring Cloud quan trọng không kém việc viết hàm `Supplier`, `Function` hay `Consumer`.

Maven và Gradle đều có thể quản lý các thành phần này. Maven dùng `pom.xml` cùng cơ chế dependency management; Gradle khai báo plugin, repository và dependency trong các file build. Cả hai đều có thể nhập Spring Cloud BOM (Bill of Materials) để dùng một tập phiên bản tương thích cho các thư viện Spring Cloud.

## 1. Hiểu các lớp dependency của một ứng dụng

Trước khi thêm thư viện, cần phân biệt vai trò của từng nhóm:

| Nhóm | Vai trò | Ví dụ |
| --- | --- | --- |
| Spring Boot | Khởi tạo ứng dụng, cấu hình tự động, quản lý vòng đời và các thành phần nền tảng | `spring-boot-starter`, `spring-boot-starter-actuator` |
| Spring Cloud Stream | Mô hình binding, tích hợp hàm và các abstraction xử lý thông điệp | `spring-cloud-stream` |
| Binder | Kết nối mô hình binding với một broker cụ thể | Kafka binder, Rabbit binder, Pulsar binder |
| Test | Hỗ trợ kiểm thử ứng dụng và luồng message | `spring-boot-starter-test`, `spring-cloud-stream-test-binder` |

Trong phần lớn ứng dụng, nên khai báo starter của binder đang sử dụng. Starter sẽ kéo theo các thư viện cần thiết, bao gồm phần lõi Spring Cloud Stream và tích hợp broker tương ứng. Ví dụ:

| Hệ thống nhắn tin | Dependency thường dùng |
| --- | --- |
| Apache Kafka | `org.springframework.cloud:spring-cloud-starter-stream-kafka` |
| RabbitMQ | `org.springframework.cloud:spring-cloud-starter-stream-rabbit` |
| Apache Pulsar | `org.springframework.cloud:spring-cloud-stream-binder-pulsar` |

Tên artifact và cách đóng gói có thể thay đổi theo dòng phiên bản của binder. Hãy đối chiếu tài liệu của đúng phiên bản Spring Cloud Stream đang dùng trước khi thêm binder Pulsar hoặc một binder mở rộng. Chỉ thêm các binder mà ứng dụng thực sự cần; mỗi binder đưa thêm thư viện client và cấu hình riêng vào classpath.

Nếu chỉ cần dùng Kafka, không phải khai báo riêng cả `spring-cloud-stream` và Kafka client bằng tay. `spring-cloud-starter-stream-kafka` là điểm bắt đầu phù hợp cho ứng dụng Spring Boot thông thường. Chỉ khai báo dependency mức thấp khi dự án có yêu cầu đặc biệt hoặc đang xây dựng một tích hợp tùy chỉnh.

## 2. Chọn phiên bản Spring Boot và Spring Cloud tương thích

Spring Boot và Spring Cloud phát hành theo các chu kỳ riêng. Spring Cloud gom nhiều dự án con thành các release train; mỗi release train được kiểm thử với một dải phiên bản Spring Boot nhất định. Vì vậy, không nên chọn phiên bản Boot và Cloud độc lập chỉ vì mỗi thư viện đều có bản mới.

Quy trình chọn phiên bản nên thực hiện theo thứ tự:

1. Xác định phiên bản Java mà môi trường triển khai hỗ trợ.
2. Chọn dòng Spring Boot phù hợp với Java và yêu cầu vận hành của dự án.
3. Tra bảng tương thích chính thức của Spring Cloud để chọn release train hỗ trợ dòng Spring Boot đó.
4. Dùng BOM của release train để quản lý Spring Cloud Stream và các binder thuộc train đó.
5. Kiểm tra tài liệu của binder cụ thể, nhất là khi sử dụng Pulsar hoặc binder ngoài bộ Spring Cloud chính.

Spring Cloud BOM thường có tọa độ `org.springframework.cloud:spring-cloud-dependencies`. Phiên bản của BOM là phiên bản release train, ví dụ `2023.0.1`, chứ không phải phiên bản của riêng `spring-cloud-stream`. BOM quản lý phiên bản cho nhiều module Spring Cloud để các module đó được dùng đồng bộ.

Ví dụ trong các cấu hình dưới đây dùng cặp phiên bản minh họa Spring Boot `3.2.4` và Spring Cloud `2023.0.1`. Đây là ví dụ để giải thích cách khai báo; khi tạo dự án mới, hãy thay bằng cặp phiên bản còn được hỗ trợ và được bảng tương thích Spring Cloud xác nhận. Không nâng riêng một binder hoặc `spring-cloud-stream` lên phiên bản khác BOM nếu chưa kiểm tra tương thích.

### BOM giải quyết vấn đề gì?

Nếu tự đặt phiên bản cho từng dependency, một dự án có thể vô tình kết hợp các bản Spring Cloud Stream, binder Kafka, binder Rabbit và thư viện nền tảng được phát hành hoặc kiểm thử ở các thời điểm khác nhau. Các khác biệt này có thể gây lỗi phân giải dependency, `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi cấu hình khi ứng dụng khởi động.

BOM tập trung các phiên bản được quản lý vào một nơi. Sau khi nhập BOM, dependency trong phần khai báo thông thường không cần ghi `<version>` hoặc phiên bản trong chuỗi tọa độ Gradle. Cơ chế này giảm việc ghim phiên bản rời rạc và giúp nâng cấp có kiểm soát.

Lưu ý: nhập BOM chỉ quản lý phiên bản, không tự thêm tất cả thư viện vào ứng dụng. Muốn sử dụng Kafka binder, dự án vẫn phải khai báo dependency Kafka binder trong danh sách dependencies.

## 3. Cấu hình dự án Maven

Maven dùng file `pom.xml`. Có thể bắt đầu bằng Spring Boot parent để nhận cấu hình build và dependency management mặc định của Spring Boot, sau đó nhập Spring Cloud BOM trong `dependencyManagement`.

Ví dụ `pom.xml` tối giản cho ứng dụng dùng Kafka:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>order-stream</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.4</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2023.0.1</spring-cloud.version>
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
            <artifactId>spring-cloud-starter-stream-kafka</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-stream-test-binder</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Các phần quan trọng:

- `spring-boot-starter-parent` cung cấp cấu hình build Maven và quản lý dependency thuộc Spring Boot. Nếu tổ chức đã có parent POM riêng, không thể khai báo hai parent; khi đó có thể giữ parent của tổ chức và nhập `spring-boot-dependencies` BOM cùng `spring-cloud-dependencies` BOM theo quy ước của dự án.
- `java.version` xác định mức Java dùng để biên dịch. Phiên bản Java cần đáp ứng yêu cầu của dòng Spring Boot đã chọn và môi trường chạy thực tế.
- `spring-cloud.version` lưu phiên bản release train. Chỉ cần thay giá trị này khi thực hiện một đợt nâng cấp đã kiểm tra tương thích.
- `dependencyManagement` nhập BOM. Các dependency Spring Cloud bên dưới được quản lý phiên bản thông qua BOM nên không cần khai báo `<version>` riêng.
- `spring-cloud-starter-stream-kafka` cung cấp tích hợp Kafka cho binding.
- `spring-cloud-stream-test-binder` được đặt ở scope `test`, chỉ phục vụ kiểm thử và không cần có trong runtime production.
- `spring-boot-maven-plugin` hỗ trợ đóng gói và chạy ứng dụng Spring Boot.

Nếu ứng dụng dùng RabbitMQ, thay Kafka starter bằng `spring-cloud-starter-stream-rabbit`. Nếu cần nhiều broker trong cùng một ứng dụng, có thể khai báo nhiều binder, nhưng phải cấu hình binder tương ứng cho từng binding và kiểm thử cách Spring Cloud Stream lựa chọn binder. Với Pulsar, thêm artifact binder được tài liệu phiên bản đang dùng chỉ định và kiểm tra phiên bản tương thích với Spring Cloud Stream.

### Trường hợp không dùng Spring Boot parent

Một dự án có thể cần giữ parent POM của công ty hoặc của một nền tảng nội bộ. Maven chỉ cho phép một parent trực tiếp, vì vậy không thể vừa kế thừa parent của tổ chức vừa kế thừa `spring-boot-starter-parent`. Cách thường dùng là nhập BOM của Spring Boot và Spring Cloud vào `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.2.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Khi dùng cách này, dự án cũng cần tự cấu hình các plugin build mà Spring Boot parent thường cung cấp. Hãy kiểm tra POM hiệu lực để hiểu dependency và plugin cuối cùng Maven sử dụng.

## 4. Cấu hình dự án Gradle

Gradle quản lý plugin và thư viện qua `build.gradle` hoặc `build.gradle.kts`. Ví dụ dưới đây dùng Groovy DSL, plugin Spring Boot và plugin Spring Dependency Management để nhập Spring Cloud BOM.

Ví dụ `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.2.4'
    id 'io.spring.dependency-management' version '1.1.4'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

ext {
    set('springCloudVersion', '2023.0.1')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-stream-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ở cấu hình này, `org.springframework.boot` là plugin build của Spring Boot, còn `io.spring.dependency-management` hỗ trợ áp dụng dependency management theo BOM. `springCloudVersion` là phiên bản release train được nhập vào `dependencyManagement`. Dependency Kafka và test binder vì thế không cần ghi phiên bản riêng.

Một lựa chọn khác là dùng BOM trực tiếp bằng Gradle `platform`:

```groovy
dependencies {
    implementation platform('org.springframework.cloud:spring-cloud-dependencies:2023.0.1')
    implementation 'org.springframework.cloud:spring-cloud-starter-stream-kafka'

    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
```

`platform(...)` đưa các quy tắc quản lý phiên bản từ BOM vào cấu hình dependency của Gradle. Nên chọn một cách quản lý BOM thống nhất cho dự án và tránh nhập cùng một BOM theo nhiều cơ chế nếu không có lý do rõ ràng. Với dự án nhiều module, có thể đặt phiên bản và quy tắc dependency tập trung ở build gốc hoặc convention plugin để các module không tự chọn các dòng Spring Cloud khác nhau.

## 5. Chọn binder và cấu hình dependency theo môi trường

Dependency xác định binder có mặt trong ứng dụng; cấu hình Spring Cloud Stream xác định binding nào dùng binder nào và kết nối tới destination nào. Hai việc này liên quan nhưng không thay thế nhau.

Ví dụ, một ứng dụng chỉ dùng Kafka có thể khai báo Kafka starter và cấu hình broker:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.in
          group: order-service
        processOrder-out-0:
          destination: orders.out
      kafka:
        binder:
          brokers: localhost:9092
```

Tên binding `processOrder-in-0` và `processOrder-out-0` được hình thành từ tên bean hàm và quy ước của Spring Cloud Stream. Dependency Kafka binder giúp ứng dụng có khả năng kết nối Kafka; cấu hình `brokers` chỉ định địa chỉ broker cho môi trường đang chạy.

Nếu cần kết nối cả Kafka và RabbitMQ, ứng dụng có thể khai báo hai binder dependency. Khi có nhiều binder trên classpath, không nên để lựa chọn binder phụ thuộc vào suy đoán hoặc cấu hình mặc định ngoài ý muốn. Hãy đặt binder mặc định hoặc chỉ định rõ binder ở từng binding theo cấu hình được phiên bản Spring Cloud Stream hỗ trợ. Đồng thời, cấu hình riêng thông tin kết nối của mỗi binder.

Không nên đóng gói tất cả binder chỉ để “phòng khi cần”. Dependency thừa làm tăng kích thước ứng dụng, thời gian giải quyết dependency và bề mặt cấu hình. Hãy thêm binder khi có một luồng nghiệp vụ thực sự cần nó.

## 6. Quản lý phiên bản trong dự án nhiều module

Ở dự án nhiều module, cách quản lý phiên bản cần nhất quán giữa các module dùng Spring Cloud Stream. Ví dụ, module `order-consumer` và `order-publisher` có thể dùng các binder khác nhau nhưng vẫn nên lấy phiên bản Spring Cloud từ cùng một release train, trừ khi kiến trúc đã xác định rõ một ngoại lệ.

Với Maven, đặt `spring-cloud.version` và BOM ở parent POM chung để các module con kế thừa. Nếu module con cần binder Kafka hoặc Rabbit, module đó khai báo starter tương ứng nhưng không tự đặt phiên bản. Không khai báo lại một phiên bản Spring Cloud riêng trong từng module.

Với Gradle, đặt BOM hoặc version catalog ở build gốc, convention plugin hay một nền tảng dependency nội bộ. Module con chỉ khai báo thư viện cần dùng. Cách này giúp nâng cấp release train tại một điểm và làm rõ module nào thực sự phụ thuộc binder nào.

Nếu một thư viện bên thứ ba kéo theo phiên bản Spring Cloud Stream hoặc Spring Kafka khác, hãy kiểm tra cây dependency trước khi thêm exclusion hay ghi đè. Exclusion có thể giải quyết một xung đột cụ thể nhưng cũng có thể loại bỏ thư viện mà binder cần lúc chạy.

## 7. Kiểm tra dependency đã được giải quyết

Sau khi cấu hình build, hãy xác minh dependency thực tế thay vì chỉ kiểm tra file khai báo.

Các lệnh Maven thường dùng:

```bash
# Biên dịch và chạy kiểm thử
./mvnw clean verify

# Xem cây dependency của các thư viện Spring Cloud
./mvnw dependency:tree -Dincludes=org.springframework.cloud

# Xem POM hiệu lực sau khi áp dụng parent và BOM
./mvnw help:effective-pom
```

Trên Windows, có thể dùng `mvnw.cmd` thay cho `./mvnw`. Nếu dự án chưa có Maven Wrapper, dùng lệnh `mvn` khi máy đã cài Maven phù hợp.

Các lệnh Gradle thường dùng:

```bash
# Chạy kiểm thử
./gradlew clean test

# Xem dependency runtime
./gradlew dependencies --configuration runtimeClasspath

# Tìm nơi khai báo phiên bản spring-cloud-stream được chọn
./gradlew dependencyInsight --dependency spring-cloud-stream --configuration runtimeClasspath
```

Trên Windows, dùng `gradlew.bat`. Khi xem kết quả, chú ý phiên bản của `spring-cloud-stream`, binder, Spring Integration và thư viện client của broker. Nếu cùng một thư viện xuất hiện nhiều yêu cầu phiên bản, hãy hiểu quy tắc chọn phiên bản của Maven hoặc Gradle và xác định dependency nào đưa phiên bản đó vào cây.

Một lần build thành công là tín hiệu tốt nhưng chưa đủ để khẳng định cấu hình đúng cho production. Hãy chạy kiểm thử ứng dụng, kiểm thử binding bằng test binder và kiểm thử tích hợp với broker thật hoặc môi trường tương đương. Với Kafka, RabbitMQ và Pulsar, kiểm tra thêm quyền truy cập, tạo tài nguyên, định tuyến, consumer group hoặc subscription theo binder đã chọn.

## 8. Những lỗi cấu hình dependency thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy class hoặc binder khi khởi động | Chưa thêm binder dependency hoặc dùng sai artifact | Kiểm tra dependency tree và tài liệu binder theo phiên bản đang dùng. |
| Lỗi `NoSuchMethodError` hoặc `ClassNotFoundException` | Các module Spring Cloud hoặc thư viện nền tảng không tương thích | Kiểm tra Spring Boot, Spring Cloud BOM và các phiên bản bị ghi đè. |
| Dependency được tải về nhưng không có binding hoạt động | Có thư viện binder nhưng chưa chọn hàm hoặc chưa cấu hình binding | Kiểm tra `spring.cloud.function.definition`, tên binding và cấu hình destination. |
| Ứng dụng kết nối nhầm broker khi có nhiều binder | Không chỉ định binder phù hợp cho binding hoặc cấu hình mặc định không như dự kiến | Khai báo binder cho từng binding và cấu hình kết nối tương ứng. |
| Test chạy được nhưng ứng dụng production thiếu thư viện | Đặt binder hoặc thư viện cần thiết ở scope chỉ dành cho test | Đưa binder runtime vào `implementation` hoặc scope compile/runtime phù hợp; chỉ để test binder trong test scope. |
| Nâng cấp một dependency làm phát sinh lỗi ở module khác | Ghi phiên bản riêng làm lệch BOM hoặc có dependency bắc cầu xung đột | Bỏ ghim phiên bản không cần thiết, kiểm tra cây dependency và nâng cấp theo một kế hoạch thống nhất. |

Không nên chữa lỗi bằng cách thêm ngẫu nhiên phiên bản mới nhất vào từng dependency. Trước tiên hãy xác định thành phần nào đang quản lý phiên bản, dependency nào kéo phiên bản xung đột vào và release train hiện tại hỗ trợ những gì. Chỉ ghi đè dependency management khi có yêu cầu rõ ràng, có kiểm thử và có tài liệu giải thích.

## 9. Quy trình nâng cấp dependency an toàn

Khi cần nâng Spring Boot hoặc Spring Cloud, hãy thực hiện theo một chu trình có thể kiểm tra:

1. Ghi nhận phiên bản Java, Spring Boot, Spring Cloud release train và binder đang dùng.
2. Chọn cặp Boot và Cloud được bảng tương thích xác nhận; kiểm tra yêu cầu Java tối thiểu.
3. Cập nhật phiên bản BOM hoặc parent/plugin ở một nơi quản lý tập trung.
4. Chạy dependency tree hoặc dependency insight để tìm phiên bản bị thay đổi và dependency bị ghi đè.
5. Biên dịch, chạy unit test và test binder.
6. Chạy integration test với broker tương ứng, bao gồm gửi/nhận message, retry và DLQ nếu ứng dụng sử dụng các chức năng đó.
7. Kiểm tra cấu hình triển khai, image runtime và môi trường production trước khi phát hành.

Với ứng dụng có Kafka Streams, cần kiểm tra cả phiên bản Kafka Streams được binder sử dụng, khả năng khôi phục state store và tương thích topology sau nâng cấp. Với RabbitMQ hoặc Pulsar, kiểm tra các thay đổi trong client và binder liên quan tới xác nhận, subscription, routing hoặc provisioning.

## 10. Maven hay Gradle?

Hai công cụ đều hỗ trợ tốt Spring Boot và Spring Cloud Stream. Maven thường phù hợp với dự án muốn cấu trúc XML rõ ràng, quy ước build thống nhất và hệ sinh thái plugin theo vòng đời Maven. Gradle phù hợp với dự án cần build script linh hoạt, cấu hình theo convention plugin hoặc quản lý nhiều module bằng Kotlin/Groovy DSL.

Việc chọn công cụ nên dựa vào chuẩn của nhóm, hệ thống CI/CD và cách các module hiện có được build. Không cần đổi từ Maven sang Gradle chỉ để dùng Spring Cloud Stream. Điều quan trọng là dự án có một nơi quản lý phiên bản rõ ràng, dùng cặp Spring Boot/Spring Cloud tương thích và kiểm tra dependency thực tế trước khi triển khai.

## Kết luận

Để khởi tạo ứng dụng Spring Cloud Stream, hãy chọn Spring Boot phù hợp với Java, chọn Spring Cloud release train theo bảng tương thích, nhập `spring-cloud-dependencies` BOM và khai báo binder cần dùng. Maven thực hiện việc này bằng `dependencyManagement`; Gradle có thể dùng Spring Dependency Management plugin hoặc `platform`. Khi phiên bản được quản lý tập trung và dependency tree được kiểm tra, ứng dụng sẽ có nền tảng ổn định để tiếp tục cấu hình hàm, binding, destination, consumer group và các cơ chế giao nhận thông điệp.
