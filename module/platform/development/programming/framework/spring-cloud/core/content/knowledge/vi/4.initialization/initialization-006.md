# Chạy ứng dụng bằng Maven, Gradle và executable JAR

Bài học thuộc chương **Khởi tạo** của module **SPRING_CLOUD_CORE**. Mục tiêu là biết build, chạy, đóng gói và kiểm tra một ứng dụng Spring Boot có sử dụng các abstraction Spring Cloud bằng hai công cụ phổ biến là **Maven** và **Gradle**, sau đó chạy ứng dụng từ **executable JAR** trong môi trường gần với production.

Trong hệ thống phân tán, việc chạy được một tiến trình mới là bước đầu. Ứng dụng còn phải nhận đúng cấu hình, dùng đúng bộ phiên bản Spring Boot/Spring Cloud, đăng ký hoặc tra cứu dịch vụ khi có tích hợp discovery, và cung cấp đủ tín hiệu để kiểm tra trạng thái. Các lệnh trong bài dùng placeholder cho phiên bản; hãy thay bằng bộ phiên bản tương thích đã được dự án lựa chọn.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt chạy ứng dụng từ mã nguồn với chạy gói executable JAR.
2. Dùng Maven Wrapper hoặc Gradle Wrapper để resolve dependency, compile, test và đóng gói ứng dụng.
3. Cấu hình Spring Boot Maven Plugin hoặc Gradle Boot Plugin để tạo artifact có thể chạy bằng `java -jar`.
4. Truyền profile, port và cấu hình bên ngoài khi chạy ứng dụng.
5. Kiểm tra dependency tree và tránh ghép phiên bản Spring Cloud không tương thích với Spring Boot.
6. Chạy nhiều instance local để quan sát discovery và giao tiếp dịch vụ.
7. Chẩn đoán các lỗi thường gặp như sai JDK, thiếu dependency, port đã được sử dụng, thiếu cấu hình hoặc không kết nối được registry.

## 2. Mô hình build và chạy

Quy trình cơ bản:

~~~mermaid
flowchart TD
    SRC["Mã nguồn + cấu hình"] --> BUILD["Maven hoặc Gradle"]
    BUILD --> DEPS["Resolve dependencies"]
    DEPS --> COMPILE["Compile và test"]
    COMPILE --> PACKAGE["Đóng gói executable JAR"]
    PACKAGE --> ART["Artifact .jar"]
    ART --> JVM["java -jar"]
    SRC --> DEV["spring-boot:run / bootRun"]
    DEV --> JVMDEV["JVM chạy từ classpath phát triển"]
    JVM --> CONFIG["Profile + environment + command line"]
    JVMDEV --> CONFIG
    CONFIG --> APP["Spring ApplicationContext"]
    APP --> CLOUD["Spring Cloud abstractions / integrations"]
~~~

Có hai đường chạy thường dùng:

- **Chạy trực tiếp bằng plugin:** `spring-boot:run` với Maven hoặc `bootRun` với Gradle. Cách này thuận tiện khi phát triển vì plugin chạy ứng dụng từ output/classes và runtime classpath của dự án.
- **Chạy executable JAR:** build artifact trước, sau đó khởi chạy bằng `java -jar`. Đây là cách kiểm tra gói đã đóng và gần với cách triển khai một ứng dụng Spring Boot độc lập.

Hai cách dùng cùng mã nguồn nhưng môi trường classpath và cách truyền tham số có thể khác. Vì vậy, trước khi phát hành nên kiểm tra cả lệnh chạy plugin lẫn artifact đã đóng gói.

## 3. Điều kiện tiên quyết và chuẩn bị môi trường

### 3.1. Công cụ cần có

- JDK được phiên bản Spring Boot đã chọn hỗ trợ.
- Maven hoặc Gradle; ưu tiên Wrapper được commit cùng dự án.
- IDE/editor và terminal.
- Quyền truy cập repository chứa dependency.
- Nếu ứng dụng có discovery hoặc config server: endpoint registry/config server và thông tin xác thực cần thiết cho môi trường thử nghiệm.
- Công cụ HTTP như `curl` để kiểm tra endpoint.

Kiểm tra JDK và Wrapper:

~~~bash
java -version
./mvnw -version
./gradlew --version
~~~

Trên Windows PowerShell hoặc Command Prompt, dùng `mvnw.cmd` và `gradlew.bat`. Không cần cài Maven/Gradle toàn cục nếu dự án đã cung cấp Wrapper. Wrapper chọn phiên bản build tool được khai báo trong dự án; JDK vẫn phải được cài phù hợp.

### 3.2. Vì sao nên dùng Wrapper?

Wrapper giúp mọi thành viên và CI chạy cùng phiên bản Maven/Gradle của dự án, giảm khác biệt do máy cá nhân. Wrapper **không** tự chọn JDK đúng và cũng không bảo đảm các repository dependency luôn sẵn sàng.

Nếu Wrapper không chạy:

1. Kiểm tra JDK có trong `PATH` và `JAVA_HOME` có trỏ đến JDK hợp lệ.
2. Kiểm tra quyền thực thi script trên Unix-like OS.
3. Kiểm tra proxy, DNS và quyền truy cập Maven/Gradle distribution.
4. Không thay phiên bản Wrapper tùy tiện khi chỉ gặp lỗi mạng hoặc thiếu JDK.

### 3.3. Kiểm tra cấu trúc dự án

Một dự án đơn module thường có cấu trúc gần như sau:

~~~text
spring-cloud-lab/
├── mvnw
├── mvnw.cmd
├── gradlew
├── gradlew.bat
├── pom.xml                  # nếu dùng Maven
├── build.gradle.kts         # nếu dùng Gradle Kotlin DSL
├── gradle/
│   └── wrapper/
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   │       ├── application.yml
│   │       └── application-local.yml
│   └── test/
│       └── java/
└── README.md
~~~

Thông thường một dự án chọn Maven **hoặc** Gradle làm build system chính. Cấu trúc trên minh họa các file Wrapper có thể xuất hiện trong repository; không cần tạo cả hai hệ thống build nếu dự án đã thống nhất một công cụ.

## 4. Chọn phiên bản Spring Boot và Spring Cloud trước khi build

Spring Cloud được phát hành theo **release train**. Một release train chỉ hỗ trợ một số dòng Spring Boot nhất định. Việc dependency tải về thành công không chứng minh bộ phiên bản đang dùng tương thích.

Trước khi chạy lệnh build, xác định:

- JDK mà dự án hỗ trợ.
- Phiên bản Spring Boot.
- Spring Cloud release train tương thích với phiên bản Boot đó.
- Phiên bản plugin build và các dependency bổ sung.
- Các starter/integration thực sự cần dùng, ví dụ discovery provider hoặc load balancing.

Dùng **Spring Cloud BOM** để quản lý phiên bản các module Cloud theo cùng release train. Không đặt phiên bản độc lập cho từng thư viện Cloud nếu không có yêu cầu đặc biệt đã được kiểm chứng.

### 4.1. Ví dụ cấu hình Maven

Ví dụ phần chính của `pom.xml`:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_COMPATIBLE_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-cloud-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>REPLACE_WITH_SUPPORTED_JDK_VERSION</java.version>
        <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>

        <!-- Chỉ thêm khi ứng dụng cần client-side load balancing -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
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
~~~

Các chuỗi `REPLACE_WITH_...` là placeholder phải thay bằng phiên bản thực tế. Không thể build nguyên mẫu khi chưa thay chúng. Ví dụ dùng Spring Boot parent để quản lý dependency Boot; nếu dự án đã dùng parent nội bộ hoặc một BOM khác, cần tích hợp Spring Cloud BOM theo cấu trúc hiện tại thay vì thêm parent thứ hai.

Starter LoadBalancer chỉ là ví dụ cho ứng dụng có nhu cầu phân giải service ID và chọn instance ở phía client. Nó không tự cung cấp một registry server hoặc tự đăng ký ứng dụng vào Eureka/Consul. Registry provider cần dependency và cấu hình riêng.

### 4.2. Ví dụ cấu hình Gradle Kotlin DSL

Trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "REPLACE_WITH_COMPATIBLE_BOOT_VERSION"
    id("io.spring.dependency-management") version "REPLACE_WITH_PLUGIN_VERSION"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

val springCloudVersion = "REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN"

dependencyManagement {
    imports {
        mavenBom("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion")
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Chỉ thêm nếu ứng dụng cần client-side load balancing
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Trong ví dụ trên, Java toolchain 17 chỉ là lựa chọn minh họa. Hãy đổi thành JDK được bộ Spring Boot của dự án hỗ trợ và được môi trường build cung cấp. Phiên bản plugin Spring Boot, plugin dependency management và Spring Cloud release train phải được chọn có chủ đích.

Có thể đưa release train vào `gradle.properties` để quản lý tập trung; nếu làm vậy, thay khai báo biến trong build script bằng cách đọc property tương ứng. Không trộn cách quản lý dependency của nhiều plugin nếu chưa hiểu thứ tự áp dụng.

### 4.3. Khi nào cần starter Cloud?

Một số nguyên tắc:

- Spring Boot starter cung cấp nhóm dependency và auto-configuration cho khả năng Boot tương ứng.
- Spring Cloud Commons chứa các abstraction chung; nhiều integration starter kéo Commons vào dạng dependency bắc cầu.
- Spring Cloud LoadBalancer cung cấp cơ chế chọn instance ở client khi được tích hợp đúng.
- Eureka, Consul hoặc provider khác cần module tích hợp tương ứng và cấu hình kết nối tới registry.
- Spring Cloud Context cung cấp cơ chế liên quan application context và refresh scope; việc có dependency không có nghĩa mọi bean tự động refresh.
- BOM quản lý phiên bản, **không tự thêm** mọi thư viện Cloud vào ứng dụng.

Chỉ thêm những starter cần thiết. Dependency thừa làm tăng thời gian khởi động, bề mặt cấu hình và nguy cơ xung đột.

## 5. Build và chạy bằng Maven

### 5.1. Chạy trực tiếp trong quá trình phát triển

Chạy ứng dụng:

~~~bash
./mvnw spring-boot:run
~~~

Chạy với profile và port riêng:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.profiles.active=local --server.port=8081"
~~~

Plugin khởi chạy ứng dụng từ classpath phát triển. Khi thay đổi mã nguồn, cần build/run lại hoặc dùng cơ chế reload phù hợp. Đường chạy này thuận tiện để thử cấu hình nhưng không thay thế việc kiểm tra artifact cuối cùng.

### 5.2. Compile và chạy test

~~~bash
./mvnw test
~~~

Lệnh này chạy test ở pha test. Nếu dự án có integration test được cấu hình ở pha riêng, hãy chạy đúng profile hoặc Maven plugin tương ứng. Không mặc định rằng `test` đã bao gồm mọi kiểm tra nhiều dịch vụ, registry hoặc hạ tầng bên ngoài.

### 5.3. Đóng gói ứng dụng

~~~bash
./mvnw clean package
~~~

Sau khi thành công, Maven thường đặt artifact trong thư mục `target/`. Tên file phụ thuộc `artifactId`, `version` và cấu hình final name. Kiểm tra file thực tế thay vì đoán tên JAR.

Chạy artifact:

~~~bash
java -jar target/spring-cloud-lab-1.0.0.jar
~~~

Nếu cần chỉ định profile và port:

~~~bash
java -jar target/spring-cloud-lab-1.0.0.jar --spring.profiles.active=local --server.port=8081
~~~

Nếu dự án không tạo executable JAR, hãy kiểm tra Spring Boot Maven Plugin đã được khai báo và thực hiện goal `repackage` trong quy trình package chưa.

### 5.4. Kiểm tra dependency với Maven

~~~bash
./mvnw dependency:tree
~~~

Lọc kết quả theo nhóm Spring Cloud khi cần:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud
~~~

Khi có xung đột, đọc cây dependency để xác định thư viện nào kéo phiên bản ngoài mong đợi. Không chữa lỗi bằng cách thêm phiên bản ngẫu nhiên cho dependency con; kiểm tra BOM, parent và dependency management trước.

## 6. Build và chạy bằng Gradle

### 6.1. Chạy trực tiếp

~~~bash
./gradlew bootRun
~~~

Chạy với tham số ứng dụng:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local --server.port=8081'
~~~

Cú pháp quote phụ thuộc shell. Trên Windows Command Prompt, có thể dùng dấu ngoặc kép cho phần tham số. Nếu build dùng nhiều project/module, chạy task tại đúng module hoặc dùng đường dẫn task đầy đủ.

### 6.2. Chạy test và đóng gói

~~~bash
./gradlew test
./gradlew clean bootJar
~~~

Gradle Boot Plugin tạo executable archive bằng task `bootJar`. Artifact thường nằm trong `build/libs/`. Nếu dự án đồng thời tạo JAR Java thường và Boot JAR, cần phân biệt hai loại artifact.

Chạy gói:

~~~bash
java -jar build/libs/spring-cloud-lab-1.0.0.jar
~~~

Truyền profile và port:

~~~bash
java -jar build/libs/spring-cloud-lab-1.0.0.jar --spring.profiles.active=local --server.port=8081
~~~

### 6.3. Kiểm tra dependency với Gradle

Xem dependency runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem lý do một dependency được chọn:

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
~~~

Tên configuration có thể khác theo plugin và module. Với project đa module, chạy task trên đúng module chứa ứng dụng.

## 7. Executable JAR là gì và vì sao cần kiểm tra nó?

JAR Java thông thường là archive chứa class và resource. **Executable JAR của Spring Boot** được đóng gói theo định dạng mà Boot launcher có thể khởi chạy, thường gồm:

- Class và resource của ứng dụng.
- Dependency runtime được đóng gói cùng ứng dụng.
- Metadata để xác định launcher và lớp main của ứng dụng.

Do đó, executable JAR thường có thể chạy bằng:

~~~bash
java -jar app.jar
~~~

Một file JAR có đuôi `.jar` chưa chắc là executable Spring Boot JAR. Nếu chạy mà nhận lỗi không có main manifest attribute hoặc không tìm được lớp, hãy kiểm tra loại artifact và cấu hình plugin.

Có thể liệt kê nội dung archive bằng JDK:

~~~bash
jar tf target/spring-cloud-lab-1.0.0.jar
~~~

Trong cấu trúc Boot JAR phổ biến, bạn có thể thấy các thư mục như `BOOT-INF/classes` và `BOOT-INF/lib`. Chi tiết layout có thể thay đổi theo phiên bản/cấu hình; mục tiêu là xác nhận class ứng dụng và dependency runtime đã được đóng gói.

### 7.1. Phân biệt các lệnh chạy

| Cách chạy | Dữ liệu được sử dụng | Mục đích chính |
| --- | --- | --- |
| `spring-boot:run` | Output/classes và dependency từ Maven project. | Phát triển, thử nhanh cấu hình. |
| `bootRun` | Runtime classpath của Gradle project. | Phát triển, thử nhanh cấu hình. |
| `java -jar app.jar` | Artifact đã đóng gói. | Kiểm tra gói triển khai và chạy độc lập. |

Nếu chạy bằng plugin thành công nhưng JAR lỗi, có thể thiếu resource, profile, dependency runtime hoặc cấu hình plugin đóng gói. Luôn chạy thử đúng file artifact sẽ phát hành.

## 8. Truyền cấu hình khi chạy

Spring Boot hỗ trợ externalized configuration. Cùng một artifact có thể nhận giá trị khác nhau theo môi trường mà không cần build lại, miễn là ứng dụng được thiết kế để đọc các thuộc tính đó.

### 8.1. Cấu hình cơ bản

Ví dụ `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  greeting: "Hello from local default"
~~~

Profile local trong `application-local.yml`:

~~~yaml
server:
  port: 8081

app:
  greeting: "Hello from local profile"
~~~

Kích hoạt profile:

~~~bash
java -jar app.jar --spring.profiles.active=local
~~~

Hoặc dùng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=local java -jar app.jar
~~~

Cú pháp khai báo biến môi trường trong PowerShell khác Bash:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
java -jar app.jar
~~~

### 8.2. Thứ tự ưu tiên cấu hình

Nhiều nguồn có thể cung cấp cùng một property: file cấu hình, profile, biến môi trường, tham số dòng lệnh hoặc nguồn cấu hình tích hợp. Spring Boot có quy tắc precedence giữa các property source; hãy tra cứu tài liệu đúng phiên bản khi cần xác định nguồn nào thắng.

Một cách kiểm tra hữu ích là thay một giá trị trong môi trường lab bằng các nguồn khác nhau, khởi động lại và quan sát giá trị thực tế. Tránh đặt nhiều nguồn cùng cấu hình một khóa trong production mà không có quy ước rõ ràng.

### 8.3. Nạp thêm file cấu hình bên ngoài

Có thể chỉ định thư mục cấu hình bổ sung khi chạy:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

Thư mục `./config/` phải tồn tại nếu muốn cung cấp file ở đó; tiền tố `optional:` cho phép ứng dụng tiếp tục khi vị trí không có. `spring.config.additional-location` bổ sung vị trí tìm kiếm; `spring.config.location` có semantics thay thế các vị trí mặc định, nên chỉ dùng khi thực sự muốn kiểm soát lại toàn bộ nguồn cấu hình.

Không đặt mật khẩu, token hoặc private key trực tiếp trong repository hay file cấu hình được commit. Dùng secret store hoặc cơ chế inject secret của môi trường triển khai, giới hạn quyền đọc và tránh ghi giá trị bí mật vào log.

### 8.4. JVM arguments và application arguments

Hai nhóm tham số nằm ở hai phía của `-jar`:

~~~bash
java -Xms256m -Xmx512m -Duser.timezone=UTC -jar app.jar --spring.profiles.active=local --server.port=8081
~~~

- Trước `-jar`: tùy chọn của JVM như heap và system property `-D...`.
- Sau tên JAR: tham số ứng dụng, thường là Spring Boot command-line properties như `--server.port=8081`.

Nhầm vị trí tham số có thể khiến JVM báo lỗi hoặc ứng dụng không nhận cấu hình như mong đợi.

## 9. Chạy nhiều instance để thử nghiệm Spring Cloud

Một ứng dụng Spring Boot có thể chạy nhiều tiến trình với cùng artifact nhưng khác port và instance metadata. Ví dụ mở hai terminal:

Terminal A:

~~~bash
java -jar app.jar --spring.profiles.active=local --server.port=8081
~~~

Terminal B:

~~~bash
java -jar app.jar --spring.profiles.active=local --server.port=8082
~~~

Cả hai tiến trình dùng cùng `spring.application.name` nếu chúng là hai instance của cùng service. Khi có discovery provider, cần cấu hình mỗi instance đăng ký đúng địa chỉ/port có thể truy cập từ các dịch vụ khác. Nếu chạy trong container hoặc nhiều máy, `localhost` của mỗi môi trường không đại diện cho cùng một host.

### 9.1. Những điều cần xác minh

- Hai tiến trình thực sự chạy và lắng nghe trên hai port khác nhau.
- Tên ứng dụng/service ID giống nhau khi chúng là cùng một logical service.
- Registry có ghi nhận từng instance với địa chỉ và port đúng.
- Discovery client của bên gọi nhìn thấy danh sách instance như kỳ vọng.
- Load balancer chọn instance hợp lệ và request thực sự tới đúng tiến trình.
- Khi dừng một tiến trình, hành vi cập nhật registry, cache và lựa chọn instance phù hợp với cơ chế đã cấu hình.

**Chỉ khởi chạy hai tiến trình không tự tạo service discovery.** Cần dependency/provider, cấu hình và registry tương ứng. Spring Cloud Commons định nghĩa abstraction; nó không tự khởi chạy Eureka/Consul server.

### 9.2. Cấu hình ứng dụng và refresh scope

Nếu ứng dụng dùng `@RefreshScope`, việc chạy bằng Maven, Gradle hay JAR không thay đổi bản chất của refresh scope. Bean chỉ phản ánh giá trị mới khi nguồn cấu hình thực sự cập nhật và quy trình refresh được hỗ trợ đã được kích hoạt. Sửa biến môi trường trong terminal sau khi process đang chạy không thay đổi môi trường của process đó.

Khi thử refresh trên nhiều instance, ghi nhận revision cấu hình ở từng instance. Một instance được refresh không có nghĩa các instance còn lại tự động được refresh. Quy trình vận hành cần có cách phân phối thay đổi và xác minh trạng thái đồng nhất theo yêu cầu hệ thống.

## 10. Kiểm tra ứng dụng sau khi khởi động

Một ứng dụng được xem là khởi động thành công khi log cho thấy context hoàn tất và server lắng nghe; tuy nhiên cần kiểm tra thêm chức năng và dependency.

### 10.1. Kiểm tra HTTP endpoint

Nếu ứng dụng có controller cung cấp endpoint:

~~~bash
curl -i http://localhost:8081/
~~~

Thay path theo API thật của ứng dụng. HTTP 404 có thể chỉ ra endpoint không tồn tại, không nhất thiết tiến trình không chạy. Connection refused thường cho thấy không có process lắng nghe ở địa chỉ/port đó hoặc kết nối bị chặn.

### 10.2. Kiểm tra Actuator nếu đã cài và cấu hình

Nếu dependency Actuator có trong runtime classpath và endpoint được expose phù hợp:

~~~bash
curl -i http://localhost:8081/actuator/health
~~~

Endpoint health, readiness, metrics và các endpoint quản trị khác phụ thuộc dependency, cấu hình, security và phiên bản Spring Boot. Không giả định chúng tự có hoặc được public. Trong production chỉ expose endpoint cần thiết và bảo vệ bằng network policy/xác thực phù hợp.

### 10.3. Kiểm tra trạng thái Spring Cloud

Với ứng dụng có discovery hoặc config integration, kiểm tra thêm:

- Service ID mà ứng dụng đăng ký.
- Registry host/port và trạng thái kết nối.
- Instance ID, host, port và metadata.
- Kết quả lookup từ phía caller.
- Giá trị cấu hình/profile mà ứng dụng đang sử dụng.
- Log startup cho thấy integration nào đã được auto-configure.

Không nên kết luận discovery hoạt động chỉ từ việc log có nhắc tên thư viện. Hãy thực hiện một lookup hoặc request thực tế qua abstraction/client.

## 11. Quy trình phát triển và phát hành có thể lặp lại

Một quy trình gọn cho mỗi thay đổi:

1. Xác nhận JDK và phiên bản build tool bằng Wrapper.
2. Kiểm tra thay đổi dependency, đặc biệt Spring Boot parent/BOM và Spring Cloud BOM.
3. Chạy compile/test; đọc lỗi dependency trước khi sửa code.
4. Chạy plugin (`spring-boot:run` hoặc `bootRun`) với profile local để thử nhanh.
5. Đóng gói executable JAR.
6. Chạy chính JAR đó trong môi trường local với cấu hình tách khỏi artifact.
7. Kiểm tra endpoint, health/readiness nếu có, discovery và một luồng gọi dịch vụ nếu ứng dụng dùng chúng.
8. Lưu phiên bản JDK, Boot, Cloud, build tool và lệnh chạy vào log triển khai hoặc release metadata.

Ví dụ CI tối thiểu với Maven:

~~~bash
./mvnw --batch-mode clean verify
~~~

Với Gradle:

~~~bash
./gradlew --no-daemon clean check bootJar
~~~

Task CI thực tế phụ thuộc cấu hình dự án; cần đảm bảo integration test và packaging được chạy đúng. Không thêm `-DskipTests` hoặc `-x test` như cách xử lý mặc định khi build lỗi.

### 11.1. Reproducibility

Để người khác có thể tái tạo bản build, lưu hoặc kiểm soát:

- Wrapper và cấu hình repository.
- Phiên bản JDK/toolchain.
- Phiên bản plugin và dependency management.
- BOM và release train.
- Profile build cần thiết (nếu có).
- Artifact name, checksum và commit/version nguồn.

Không dùng dynamic dependency version hoặc snapshot không kiểm soát trong release production nếu quy trình chưa có cơ chế pin và kiểm tra phù hợp.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `Unsupported class file major version` hoặc lỗi bytecode | JDK dùng để chạy/build không phù hợp với bytecode/plugin. | Kiểm tra `java -version`, `JAVA_HOME`, toolchain và JDK mà IDE/CI dùng. |
| Không resolve được dependency | Repository, proxy, DNS, credentials hoặc tọa độ/version sai. | Kiểm tra repository access và log Maven/Gradle; không vội nâng version. |
| Lỗi tương thích Spring Boot/Spring Cloud | Release train không hỗ trợ dòng Boot đang dùng hoặc dependency bị override. | Đối chiếu compatibility matrix, BOM và dependency tree. |
| Maven chạy được nhưng JAR không chạy | Plugin repackage chưa cấu hình, chạy nhầm artifact hoặc thiếu runtime dependency. | Kiểm tra plugin, loại JAR và nội dung archive. |
| Gradle `bootRun` thành công nhưng `bootJar` lỗi | Task packaging, main class, resource hoặc runtime configuration khác. | Chạy `clean bootJar`, xem log task và thử đúng artifact. |
| `Port already in use` | Một process khác chiếm port. | Dừng process cũ hoặc chọn port khác bằng `--server.port`. |
| Ứng dụng khởi động nhưng gọi service ID thất bại | Chưa có LoadBalancer/provider, registry sai hoặc lookup rỗng. | Kiểm tra dependency, service ID, registry và danh sách instance. |
| Không kết nối được registry | Sai host/port, DNS, firewall, credentials hoặc registry chưa sẵn sàng. | Kiểm tra từ chính môi trường chạy ứng dụng, không chỉ từ máy host. |
| Thay file cấu hình nhưng output không đổi | Nguồn config chưa được nạp; bean đã giữ giá trị; chưa refresh/restart. | Kiểm tra Environment, property source, scope và quy trình refresh. |
| Actuator trả 404 | Thiếu starter, endpoint không expose, management port/path khác. | Kiểm tra dependency, endpoint exposure, security và cấu hình management. |
| Chạy plugin được nhưng JAR không tìm thấy file config | File nằm ngoài artifact nhưng đường dẫn làm việc lúc chạy khác. | Chỉ định location rõ ràng, kiểm tra working directory và quyền file. |

Khi chẩn đoán, thay đổi từng yếu tố một. Nếu đồng thời đổi JDK, Boot, Cloud BOM, profile và registry, rất khó xác định thay đổi nào giải quyết được lỗi.

## 13. Bài thực hành: đóng gói và chạy hai instance

### Mục tiêu

Tạo một ứng dụng Spring Boot đơn giản có endpoint trả về tên ứng dụng và instance ID. Build bằng **một** trong hai hệ thống Maven hoặc Gradle, chạy bằng plugin, sau đó đóng gói và chạy bằng executable JAR. Nếu môi trường có discovery provider, đăng ký hai instance để quan sát.

### Các bước

1. Tạo ứng dụng với một endpoint kiểm tra, ví dụ `GET /info`.
2. Đặt `spring.application.name=inventory-service` và cấu hình `instance-id` riêng qua biến môi trường hoặc property.
3. Xác nhận JDK và cặp phiên bản Boot/Cloud.
4. Chạy test và khởi động bằng plugin build.
5. Đóng gói JAR và liệt kê nội dung archive.
6. Chạy hai tiến trình cùng artifact trên port 8081 và 8082, mỗi tiến trình có instance ID khác nhau.
7. Gọi endpoint của từng port và xác nhận phản hồi đúng instance.
8. Nếu có registry integration, kiểm tra cả hai instance xuất hiện trong registry và caller lookup được service ID.
9. Dừng một instance, quan sát registry/cache/caller; ghi rõ thời gian hội tụ và lỗi trung gian.
10. Khởi động lại và kiểm tra phục hồi.

Ví dụ endpoint đơn giản:

~~~java
@RestController
class InstanceController {
    private final Environment environment;

    InstanceController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/info")
    Map<String, String> info() {
        return Map.of(
            "application", environment.getProperty("spring.application.name", "unknown"),
            "instance", environment.getProperty("app.instance-id", "local")
        );
    }
}
~~~

Đây là ví dụ minh họa cho endpoint kiểm thử; cần import Spring Web, Spring Environment và Map theo cấu trúc dự án. Trong production, không công khai các thông tin nội bộ ngoài những gì chính sách vận hành cho phép.

Chạy hai tiến trình từ cùng artifact:

~~~bash
java -jar app.jar --server.port=8081 --app.instance-id=inventory-a
java -jar app.jar --server.port=8082 --app.instance-id=inventory-b
~~~

Mở hai terminal riêng để chạy song song. Không chạy hai lệnh trong cùng terminal theo cách tuần tự nếu process đầu chưa kết thúc.

### Bảng ghi kết quả

| Kiểm tra | Kết quả mong đợi | Kết quả thực tế |
| --- | --- | --- |
| Build/test | Task hoàn tất, không có lỗi. | Tự ghi |
| Plugin run | Endpoint phản hồi đúng. | Tự ghi |
| Executable JAR | Chạy được bằng `java -jar`. | Tự ghi |
| Instance A/B | Hai port và ID phân biệt. | Tự ghi |
| Registry (nếu có) | Hai instance được công bố với địa chỉ đúng. | Tự ghi |
| Dừng A | Quan sát được hành vi khi một instance mất. | Tự ghi |
| Khôi phục A | Instance quay lại theo cơ chế provider. | Tự ghi |

## 14. Checklist hoàn thành

- [ ] Kiểm tra được JDK và build tool qua Wrapper.
- [ ] Giải thích được Maven `spring-boot:run` khác `package` + `java -jar` như thế nào.
- [ ] Giải thích được Gradle `bootRun` khác `bootJar` + `java -jar` như thế nào.
- [ ] Cấu hình được Spring Boot Maven Plugin hoặc Gradle Boot Plugin để tạo executable JAR.
- [ ] Chọn được Spring Cloud release train tương thích và dùng BOM quản lý phiên bản.
- [ ] Truyền profile, port, JVM option và application argument đúng vị trí.
- [ ] Nạp được cấu hình từ file bên ngoài hoặc environment theo môi trường.
- [ ] Phân biệt được chạy nhiều tiến trình với việc cấu hình discovery/registry.
- [ ] Kiểm tra được artifact thực tế sau khi đóng gói, không chỉ chạy từ IDE/plugin.
- [ ] Biết kiểm tra health, dependency, registry và log startup khi ứng dụng không hoạt động.
- [ ] Ghi lại được các phiên bản và lệnh chạy để tái tạo môi trường.

**Tài liệu cần đối chiếu khi thực hành:** Spring Boot Reference về build systems, Maven/Gradle plugins, executable archives và externalized configuration; Spring Cloud release train/compatibility matrix và tài liệu của integration đang dùng. Luôn kiểm tra theo phiên bản cụ thể của dự án trước khi sao chép cấu hình vào production.
