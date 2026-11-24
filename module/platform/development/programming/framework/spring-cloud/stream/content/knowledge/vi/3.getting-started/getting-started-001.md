# Chọn Java, Spring Boot, Spring Cloud BOM và phiên bản Stream tương thích

Trước khi viết hàm Supplier, Function hoặc Consumer, cần chọn một bộ phiên bản Java và Spring có thể làm việc cùng nhau. Spring Cloud Stream nằm trên Spring Boot và sử dụng Spring Cloud Function cùng binder để kết nối với hệ thống thông điệp. Vì vậy, việc chọn từng thư viện theo phiên bản mới nhất một cách độc lập dễ tạo ra xung đột dependency hoặc một tổ hợp không được hỗ trợ.

Quy trình an toàn là xác định JDK và phiên bản Spring Boot trước, tra bảng tương thích để chọn Spring Cloud release train, rồi để BOM của release train quản lý phiên bản Spring Cloud Stream và các thành phần Spring Cloud liên quan. Sau đó mới chọn binder cho Kafka, RabbitMQ hoặc Pulsar và kiểm tra phiên bản client tương ứng.

## 1. Hiểu các lớp phiên bản

Một ứng dụng Spring Cloud Stream thường có các lớp thành phần sau:

| Thành phần | Trách nhiệm quản lý phiên bản |
|---|---|
| JDK | Trình biên dịch và môi trường chạy Java; phải đáp ứng yêu cầu của Spring Boot và các thư viện được dùng |
| Spring Boot | Cung cấp nền tảng ứng dụng, auto-configuration, plugin build và BOM cho nhiều thư viện nền tảng |
| Spring Cloud release train | Tập hợp các dự án Spring Cloud có phiên bản được kiểm thử cùng nhau; BOM của train quản lý các dependency Spring Cloud |
| Spring Cloud Stream | Cung cấp mô hình lập trình hướng thông điệp, binding và binder abstraction; phiên bản thường được quản lý qua Spring Cloud BOM |
| Binder và thư viện client | Kết nối với broker cụ thể, ví dụ Kafka, RabbitMQ hoặc Pulsar; có thêm yêu cầu tương thích riêng |
| Broker | Máy chủ Kafka, RabbitMQ hoặc Pulsar được triển khai trong môi trường chạy; phiên bản broker phải tương thích với client và tính năng sử dụng |

Các lớp này liên quan nhưng không thay thế cho nhau. spring-boot-dependencies quản lý các thư viện trong hệ sinh thái Spring Boot. spring-cloud-dependencies quản lý các dự án thuộc Spring Cloud release train. BOM là tập hợp quy tắc quản lý phiên bản; import BOM không tự thêm tất cả thư viện vào ứng dụng.

Ví dụ, thêm spring-cloud-starter-stream-kafka vào dependencies mới đưa Kafka binder vào classpath. Import spring-cloud-dependencies giúp Maven hoặc Gradle biết phiên bản phù hợp của starter và các thư viện Spring Cloud liên quan mà không cần ghi version cho từng dependency.

## 2. Chọn JDK và phiên bản Java đích

### 2.1. Phân biệt JDK, Java compiler và Java runtime

JDK được dùng để biên dịch mã nguồn và chạy các công cụ build. Ứng dụng đã đóng gói cần một Java runtime tương thích khi triển khai. Trong môi trường CI và production, cần kiểm tra cả hai nơi vì máy phát triển có thể dùng JDK mới hơn máy chủ.

Ba thông tin cần thống nhất:

- **JDK chạy build:** phiên bản Java thực tế mà Maven hoặc Gradle đang sử dụng.
- **Java toolchain hoặc compiler release:** phiên bản API và bytecode mà mã nguồn được biên dịch cho.
- **JRE/JDK chạy ứng dụng:** phiên bản Java trên máy chủ hoặc image container.

Không nên chỉ nhìn java -version rồi kết luận build đang dùng đúng JDK. Maven và Gradle có thể chạy bằng một Java khác do JAVA_HOME, IDE hoặc cấu hình toolchain.

Kiểm tra môi trường:

~~~bash
java -version
javac -version
mvn -version
./gradlew --version
~~~

Chỉ chạy lệnh tương ứng với build tool mà dự án sử dụng. Trên Windows, Gradle Wrapper có thể được gọi bằng gradlew.bat --version; Maven Wrapper có thể được gọi bằng mvnw.cmd -version.

### 2.2. Chọn phiên bản Java đáp ứng giao điểm yêu cầu

Trước hết, đọc mục System Requirements của đúng phiên bản Spring Boot. Mỗi dòng Boot quy định phiên bản Java tối thiểu và phạm vi Java được hỗ trợ. Binder hoặc thư viện bên thứ ba có thể đặt yêu cầu cao hơn. Phiên bản được chọn phải thỏa mãn tất cả ràng buộc này.

Với dự án mới, Java LTS thường là lựa chọn dễ vận hành vì thời gian cập nhật bảo mật và hỗ trợ dài hơn. Java 21 là ví dụ phù hợp cho bộ phiên bản minh họa trong bài này. Spring Boot 4.x yêu cầu tối thiểu Java 17; chọn Java 21 vẫn cần xác nhận đúng dòng Boot, binder và thư viện phụ trợ đang dùng hỗ trợ phiên bản đó.

Đặt phiên bản Java rõ ràng trong build để máy của từng thành viên không tự chọn một mức khác nhau. Ví dụ với Maven:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

Với Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Toolchain giúp Gradle chọn JDK phù hợp để biên dịch. Nếu CI hoặc môi trường triển khai dùng Java khác, hãy cấu hình rõ phiên bản đó trong pipeline và container image. Không biên dịch bytecode cho Java mới hơn runtime production có thể chạy.

## 3. Chọn Spring Boot trước Spring Cloud

Spring Boot quản lý nhiều dependency nền tảng như Spring Framework, logging, JSON, web server và các thư viện tích hợp. Khi chọn Boot, cần cân nhắc:

1. Dòng Boot còn được hỗ trợ và nhận bản sửa lỗi bảo mật.
2. Phiên bản Java của tổ chức đáp ứng yêu cầu của dòng Boot đó.
3. Các thư viện quan trọng khác trong ứng dụng có phiên bản tương thích.
4. Maven hoặc Gradle Wrapper đáp ứng yêu cầu build của dòng Boot.
5. Hệ thống CI, IDE và image triển khai có thể dùng cùng cấu hình Java.

Với Maven, spring-boot-starter-parent là lựa chọn phổ biến. Parent cung cấp cấu hình compiler, plugin và dependency management theo Spring Boot. Nếu dự án đã phải kế thừa một parent POM nội bộ, có thể import spring-boot-dependencies BOM thay vì kế thừa thêm một parent khác.

Với Gradle, plugin org.springframework.boot kết hợp dependency management hoặc BOM platform giúp quản lý dependency theo cùng dòng Boot. Hãy dùng Gradle Wrapper được commit trong repository để mọi máy và CI dùng cùng phiên bản Gradle.

Không tự đặt phiên bản riêng cho Spring Framework, Jackson, logging hoặc các dependency nền tảng mà Boot đã quản lý, trừ khi có lý do tương thích được kiểm chứng. Override tùy tiện có thể làm mất bộ phiên bản đã được Spring Boot kiểm thử.

## 4. Tra bảng tương thích để chọn Spring Cloud release train

Spring Cloud phát hành theo release train. Tên phiên bản sử dụng dạng lịch YYYY.MINOR.PATCH, ví dụ 2025.1.5. Hai thành phần đầu xác định release train; phần cuối là service release chứa các bản sửa lỗi và cập nhật tương thích trong train đó.

Spring Cloud release train có bảng tương thích với các thế hệ Spring Boot. Hãy dùng bảng chính thức tại [Spring Cloud - Version Mappings](https://spring.io/projects/spring-cloud/) để chọn train theo Boot đang sử dụng. Không suy ra phiên bản Cloud từ số phiên bản Boot hoặc chọn cùng số major một cách máy móc.

Tại thời điểm biên soạn bài học (24/11/2026), trang Spring Cloud công bố các cặp chính sau:

| Spring Cloud release train | Spring Boot tương thích được công bố | Ghi chú |
|---|---|---|
| 2025.1.x (Oakwood) | 4.0.x; 4.1.x từ 2025.1.2 | Dòng được dùng trong ví dụ thực hành |
| 2025.0.x (Northfields) | 3.5.x | Trang hỗ trợ đánh dấu train này đã hết vòng đời |
| 2024.0.x (Moorgate) | 3.4.x | Train cũ, không chọn cho dự án mới |

Bảng trên là quan hệ tương thích giữa các dòng, không phải khuyến nghị dùng mọi bản patch của Boot hoặc Cloud. Khi đã chọn train, tiếp tục kiểm tra trạng thái hỗ trợ và lấy service release GA mới nhất còn được duy trì của train đó.

Spring Cloud 2026.0.0 đã được phát hành và bao gồm Spring Cloud Stream 5.1.0. Tuy nhiên, bảng Version Mappings trên trang Spring Cloud tại thời điểm biên soạn chưa liệt kê quan hệ Boot cho train 2026.0.x. Không tự giả định rằng chỉ cần ghép nó với Spring Boot 4.2.x vì hai số phiên bản cùng năm. Hãy đợi hoặc kiểm tra thông báo tương thích chính thức trước khi chọn train này cho một dự án cần tổ hợp được công bố rõ ràng.

### 4.1. Ví dụ về một bộ phiên bản đã có mapping

Để minh họa một bộ phiên bản có quan hệ tương thích được công bố, có thể dùng:

| Thành phần | Phiên bản minh họa |
|---|---|
| JDK | Java 21 |
| Spring Boot | 4.1.3 |
| Spring Cloud release train | 2025.1.5 |
| Spring Cloud Stream | 5.0.5, được release train quản lý |

Spring Cloud 2025.1.x hỗ trợ Spring Boot 4.1.x từ service release 2025.1.2. Release 2025.1.5 bao gồm Spring Cloud Stream 5.0.5. Vì vậy, ví dụ này thể hiện cách ghép phiên bản dựa trên mapping và BOM đã công bố. Khi áp dụng vào dự án thực tế, vẫn cần chọn bản patch Boot mới nhất phù hợp với chính sách hỗ trợ và kiểm thử lại toàn bộ ứng dụng.

## 5. Để Spring Cloud BOM quản lý Spring Cloud Stream

Sau khi xác định Spring Boot và release train, import BOM org.springframework.cloud:spring-cloud-dependencies. BOM này quản lý các dự án Spring Cloud trong train, trong đó có Spring Cloud Function và Spring Cloud Stream.

Không cần tự chọn phiên bản spring-cloud-stream riêng nếu ứng dụng đã dùng một Spring Cloud release train tương thích. Việc ghi version riêng cho Stream hoặc binder có thể khiến các thành phần trong cùng hệ sinh thái lệch khỏi bộ phiên bản đã được train quản lý.

Spring Cloud BOM là BOM-only: nó chứa thông tin dependency management, không tự cung cấp plugin hoặc tự thêm starter vào classpath. Ứng dụng vẫn phải khai báo dependency mà nó thật sự sử dụng.

### 5.1. Cấu hình Maven với Kafka binder

Ví dụ sau dùng Spring Boot 4.1.3, Spring Cloud 2025.1.5 và Java 21. Các phiên bản trong ví dụ minh họa một tổ hợp đã có mapping tương thích; khi bắt đầu dự án mới, kiểm tra service release mới nhất trên trang chính thức trước khi khóa phiên bản.

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.3</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>stream-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2025.1.5</spring-cloud.version>
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
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-stream-test-binder</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Điểm cần chú ý:

- Parent POM quản lý các dependency và plugin thuộc Spring Boot.
- spring-cloud.version chọn đúng Spring Cloud release train.
- spring-cloud-dependencies quản lý phiên bản của các dependency Spring Cloud.
- spring-cloud-starter-stream-kafka thêm Kafka binder vào ứng dụng.
- spring-cloud-stream-test-binder hỗ trợ kiểm thử binding mà không cần broker thật trong các bài test phù hợp.
- Không ghi version riêng cho các dependency Spring Cloud đã được BOM quản lý.

Nếu tổ chức dùng parent POM riêng, có thể thay phần parent bằng cấu hình import spring-boot-dependencies BOM và cấu hình plugin Maven tương ứng. Không cần vừa kế thừa Spring Boot parent vừa import lại Boot BOM một cách dư thừa.

### 5.2. Cấu hình Gradle

Với Gradle, có thể dùng Spring Boot plugin và dependency management plugin để import cùng release train BOM:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.3'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', '2025.1.5')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-stream-kafka'

    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Gradle Wrapper phải dùng phiên bản Gradle được Spring Boot plugin đang chọn hỗ trợ. Không chỉ kiểm tra Gradle cài toàn máy; hãy kiểm tra gradle-wrapper.properties vì CI thường chạy Wrapper.

Một dự án Gradle cũng có thể quản lý BOM bằng platform(...) hoặc enforcedPlatform(...). Chỉ dùng enforcedPlatform khi thật sự muốn ép phiên bản trên toàn dependency graph và hiểu rõ ảnh hưởng đến các thư viện khác. Với cấu hình Spring Boot thông thường, plugin dependency management hoặc platform BOM là đủ.

## 6. Chọn binder theo broker

Spring Cloud Stream có mô hình lập trình chung, nhưng binder là dependency cụ thể kết nối ứng dụng với broker. Chỉ thêm binder mà ứng dụng cần. Không thêm nhiều binder cùng lúc nếu không có yêu cầu dùng nhiều hệ thống môi giới.

| Broker | Dependency thường dùng | Nơi kiểm tra tương thích |
|---|---|---|
| Apache Kafka | org.springframework.cloud:spring-cloud-starter-stream-kafka hoặc spring-cloud-stream-binder-kafka | Spring Cloud Stream Kafka Binder reference; phiên bản Kafka client và broker |
| RabbitMQ | org.springframework.cloud:spring-cloud-starter-stream-rabbit hoặc spring-cloud-stream-binder-rabbit | Spring Cloud Stream Rabbit Binder reference; phiên bản Rabbit client và broker |
| Apache Pulsar | org.springframework.pulsar:spring-pulsar-spring-cloud-stream-binder | Spring for Apache Pulsar và Pulsar Binder reference; phiên bản Spring Pulsar, Pulsar client và broker |

Kafka và RabbitMQ binder thuộc hệ sinh thái Spring Cloud Stream và thường được quản lý qua Spring Cloud release train BOM. Pulsar binder được cung cấp trong hệ sinh thái Spring for Apache Pulsar; cần kiểm tra BOM nào quản lý artifact và phiên bản tương thích của nó. Không giả định rằng mọi dependency có chữ stream trong tên đều được spring-cloud-dependencies quản lý.

Ví dụ, khi đổi từ Kafka sang RabbitMQ, thay dependency binder và cấu hình kết nối, sau đó kiểm tra lại các thuộc tính đặc thù như exchange, queue, routing key và acknowledgement. Với Pulsar, cần xem cả cấu hình schema, subscription, tenant, namespace và các thuộc tính riêng của Pulsar binder. Việc giữ nguyên mã hàm không làm cho mọi thuộc tính cấu hình hoặc ngữ nghĩa broker trở nên giống nhau.

### 6.1. Kiểm tra client và broker

Binder thường kéo theo client library tương ứng. Cần xác định:

- Phiên bản broker đang chạy trong môi trường phát triển, staging và production.
- Phiên bản client mà binder đã chọn thông qua dependency management.
- Các tính năng của broker mà ứng dụng cần sử dụng, ví dụ transaction, header, partition, schema hoặc cơ chế xác nhận.
- Ma trận tương thích chính thức giữa client và broker.
- Các yêu cầu TLS, authentication, serializer và plugin ở môi trường triển khai.

Một client mới có thể kết nối với broker cũ nhưng không phải mọi tính năng đều khả dụng. Ngược lại, nâng broker mà không kiểm tra client và binder có thể làm thay đổi hành vi giao thức. Vì vậy, cần kiểm thử tích hợp bằng đúng loại broker và phiên bản gần production.

## 7. Xác minh phiên bản dependency thực tế

Khai báo trong file build chỉ thể hiện yêu cầu của dự án. Phiên bản cuối cùng được chọn còn phụ thuộc BOM, dependency bắc cầu và quy tắc phân giải của build tool. Sau khi import BOM và thêm binder, hãy xem dependency graph để biết ứng dụng thật sự dùng phiên bản nào.

Với Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.cloud,org.springframework.kafka,org.springframework.amqp,org.springframework.pulsar
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-stream --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
~~~

Khi xem kết quả, kiểm tra các điểm sau:

1. Chỉ có một dòng Spring Boot chủ đạo trong dependency graph.
2. Spring Cloud Stream, Spring Cloud Function và binder đến từ cùng release train đã chọn.
3. Không có phiên bản cũ bị kéo vào ngoài dự kiến.
4. Spring Kafka, Spring AMQP hoặc Spring Pulsar tương thích với binder tương ứng.
5. Không có dependency bị override thủ công mà chưa có lý do và kiểm thử.

Nếu thấy cùng một thư viện xuất hiện nhiều phiên bản, cần tìm dependency nào kéo phiên bản không mong muốn. Có thể dùng dependency exclusion trong trường hợp có căn cứ, nhưng không nên loại bỏ thư viện chỉ để build qua mà chưa hiểu tác động lúc chạy.

## 8. Build và chạy thử sau khi khóa phiên bản

Sau khi cấu hình JDK, Boot, Cloud BOM và binder:

1. Kiểm tra phiên bản Java mà build tool thực sự sử dụng.
2. Làm mới dependency trong IDE để đồng bộ với file build.
3. Build project bằng Maven Wrapper hoặc Gradle Wrapper.
4. Chạy unit test và test binder.
5. Chạy integration test với đúng broker và phiên bản client dự kiến triển khai.
6. Khởi động ứng dụng và kiểm tra log khởi tạo binder, kết nối broker, destination và consumer.
7. Gửi một thông điệp thử, xác minh payload được nhận và xử lý đúng.

Ví dụ lệnh build:

~~~bash
./mvnw clean verify
~~~

Hoặc:

~~~bash
./gradlew clean test
~~~

Build thành công là điều kiện cần, nhưng chưa chứng minh broker production tương thích. Một test binder trong JVM không kiểm tra được mọi hành vi riêng của Kafka, RabbitMQ hoặc Pulsar. Cần có integration test cho kết nối, xác nhận, partition, retry, DLQ và schema mà ứng dụng sử dụng.

## 9. Lập kế hoạch nâng cấp phiên bản

Không nên nâng đồng thời Java, Spring Boot, Spring Cloud, binder và broker trong một thay đổi lớn nếu chưa có kiểm thử hồi quy đầy đủ. Khi nâng cấp, thực hiện theo một quy trình có thể truy vết:

1. Ghi lại bộ phiên bản hiện tại từ dependency graph và môi trường runtime.
2. Đọc release notes và migration guide của Spring Boot, Spring Cloud và binder.
3. Kiểm tra bảng tương thích để xác định release train đích.
4. Chọn service release GA mới nhất còn được hỗ trợ trong train đó.
5. Cập nhật BOM và JDK theo yêu cầu; để BOM quản lý dependency liên quan.
6. Xử lý API hoặc cấu hình đã deprecated, sau đó chạy test và integration test.
7. Triển khai staging, theo dõi log và metric trước khi nâng production.

Khi một release train hết vòng đời, ứng dụng có thể vẫn chạy nhưng sẽ không còn nhận các bản sửa lỗi và bảo mật từ nhánh đó. Cần lên kế hoạch chuyển sang train còn hỗ trợ thay vì duy trì lâu dài một tổ hợp cũ chỉ vì nó vẫn build được.

Các bản M (milestone), RC (release candidate) và SNAPSHOT phục vụ thử nghiệm trước khi phát hành. Production thông thường nên dùng bản GA đã phát hành. Nếu cần thử một bản preview để đánh giá tính năng, phải khóa phiên bản thử nghiệm riêng, ghi rõ rủi ro và không để nó trở thành dependency ngoài ý muốn của bản phát hành.

## 10. Những lỗi chọn phiên bản thường gặp

**Chọn Spring Cloud theo số năm mà không xem bảng mapping.** Release train được kiểm thử với một số thế hệ Boot cụ thể. Hãy chọn theo bảng tương thích chính thức.

**Dùng Spring Cloud Stream mới nhất cùng Spring Boot cũ.** Stream có thể yêu cầu các phiên bản Spring Framework, Spring Cloud Function hoặc Spring Messaging khác với bộ dependency Boot cũ đang quản lý.

**Ghi version riêng cho từng starter Spring Cloud.** Cách này có thể làm lệch các module trong cùng release train. Hãy import Spring Cloud BOM rồi bỏ version khỏi các dependency do BOM quản lý.

**Cho rằng Spring Cloud BOM thay thế Spring Boot BOM.** Hai BOM quản lý các nhóm dependency khác nhau. Dùng Boot parent hoặc Boot BOM cho nền tảng Boot, đồng thời import Cloud BOM cho các dự án Spring Cloud.

**Chỉ nâng phiên bản trong IDE.** IDE có thể dùng JDK hoặc Gradle khác với CI. Kiểm tra Wrapper, JAVA_HOME, toolchain và image runtime.

**Bỏ qua phiên bản client của broker.** Ứng dụng có thể compile nhưng không hỗ trợ tính năng hoặc giao thức mà broker đang chạy yêu cầu. Kiểm tra binder, client và broker cùng nhau.

**Coi build thành công là đủ.** Build không xác minh đầy đủ kết nối, xác nhận, retry, DLQ, schema hoặc transaction. Phải kiểm thử trên broker thực tế.

## 11. Quy trình chọn phiên bản cho dự án mới

Khi bắt đầu một dự án Spring Cloud Stream, có thể dùng trình tự sau:

1. Xác định Java LTS được tổ chức hỗ trợ và kiểm tra yêu cầu Java tối thiểu của Spring Boot.
2. Chọn dòng Spring Boot còn được hỗ trợ, có patch phù hợp với hệ thống.
3. Tra bảng Spring Cloud Version Mappings để xác định release train tương thích với Boot.
4. Chọn service release GA mới nhất của train còn được duy trì.
5. Import spring-cloud-dependencies BOM để quản lý Spring Cloud Stream, Function và binder.
6. Thêm đúng binder cho Kafka, RabbitMQ hoặc Pulsar; kiểm tra BOM quản lý binder đó.
7. Xem dependency tree để xác nhận phiên bản thực tế.
8. Build, chạy test binder và integration test với broker tương ứng.
9. Khóa JDK, Wrapper và image runtime trong CI/CD để tái lập cùng một bộ phiên bản.

Khi thực hiện đúng thứ tự này, ứng dụng có một nền tảng phiên bản nhất quán. Nhóm phát triển có thể tập trung vào thiết kế hàm, binding và hợp đồng thông điệp, đồng thời biết rõ dependency nào chịu trách nhiệm quản lý từng lớp của hệ thống.

## Tài liệu tham khảo chính thức

- [Spring Boot - System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): yêu cầu Java và build tool của từng phiên bản Boot.
- [Spring Cloud - Version Mappings](https://spring.io/projects/spring-cloud/): bảng tương thích giữa Spring Boot và Spring Cloud release train.
- [Spring Cloud - Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions): tình trạng hỗ trợ và các service release.
- [Spring Cloud - Release History](https://github.com/spring-cloud/spring-cloud-release/releases): nội dung từng release train, gồm các phiên bản Spring Cloud Stream được phát hành.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html): dependency, binder và cấu hình Spring Cloud Stream.
- [Spring Cloud Stream - Apache Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html): dependency và cấu hình binder cho Pulsar.
