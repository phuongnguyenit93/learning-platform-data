# Phân biệt thay thế placeholder lúc chạy với lọc tài nguyên lúc dựng

## 1. Hai thời điểm thay thế giá trị khác nhau

Trong **Spring Boot Externalized Configuration**, có hai kỹ thuật nhìn qua khá giống nhau: chèn một dấu hiệu vào file cấu hình rồi chờ nó được thay bằng giá trị. Tuy nhiên, chúng diễn ra ở **hai giai đoạn hoàn toàn khác**:

1. **Property placeholder resolution lúc chạy (runtime)**: Spring Boot đọc cấu hình, dùng **Environment** và các **PropertySource** để giải quyết biểu thức như **${remote.url:https://api.example.invalid}** khi một giá trị được sử dụng.
2. **Resource filtering/expansion lúc dựng (build time)**: Maven hoặc Gradle đọc các tệp tài nguyên, thay những token đã chọn bằng giá trị của hệ thống build, rồi sao chép **nội dung đã thay** vào output như **target/classes** hoặc **build/resources/main** để đóng gói.

Câu hỏi quan trọng không phải “có dấu placeholder hay không”, mà là **ai thay**, **thay ở giai đoạn nào**, và **giá trị nằm lại ở đâu**.

| Tiêu chí | Placeholder runtime của Spring | Resource filtering build time |
| --- | --- | --- |
| Công cụ xử lý | Spring **Environment** và property resolver | Maven Resources Plugin, Gradle **processResources** hoặc task lọc tài nguyên |
| Thời điểm | Khi ứng dụng chạy và sử dụng property | Trong bước xử lý resources khi build |
| Cú pháp thường thấy | **${name}**, **${name:default}** | Maven có **@project.version@**; Gradle **expand** thường dùng **${buildVersion}** |
| Giá trị đầu vào | File Config Data, biến môi trường, system property, command-line, các PropertySource khác | Project/build properties, các biến/giá trị được build script cấp |
| Kết quả | Giá trị được giải quyết trong **Environment** của lượt chạy | Bytes của tài nguyên đầu ra đã bị thay đổi trước khi đóng gói |
| Đổi môi trường có cần build lại? | Không nhất thiết: cấp cấu hình mới khi khởi động cùng artifact | Có, nếu muốn thay giá trị đã được đóng gói bằng build filtering |
| Dùng cho | Endpoint, timeout, feature flags, thông số môi trường | Version, build timestamp, thông tin artifact hoặc metadata bất biến |
| Lưu ý bảo mật | Secret nên đến từ nguồn runtime được bảo vệ | Secret build-time dễ bị ghi cố định vào JAR, layer image hoặc artifact lưu trữ |

Ví dụ ngắn:

~~~properties
app.version=@project.version@
app.endpoint=${remote.url:https://sandbox.example.invalid}
~~~

Trong một dự án Maven kế thừa **spring-boot-starter-parent** có resource filtering phù hợp:

- Maven thay **@project.version@** bằng version dự án khi dựng.
- Maven **để nguyên** biểu thức **${remote.url:...}**.
- Khi chạy, Spring Boot giải quyết **${remote.url:...}** dựa trên cấu hình của môi trường đích.

Đó là mô hình **“một bản dựng, nhiều môi trường chạy”**.

## 2. Vòng đời của tài nguyên và placeholder

Hình dung quy trình:

~~~text
Git repository
  ├─ pom.xml / build.gradle
  └─ src/main/resources/application.properties
         |
         | Maven process-resources / Gradle processResources
         v
  target/classes/application.properties
  hoặc build/resources/main/application.properties
         |
         | Đóng gói JAR
         v
  app.jar (BOOT-INF/classes/application.properties)
         |
         | Khởi động: java -jar app.jar
         v
  Spring Boot tạo Environment, nạp Config Data và PropertySource
         |
         | @Value, @ConfigurationProperties, Environment.getProperty
         v
  Giá trị cuối dùng trong ứng dụng
~~~

**Build time** làm việc chủ yếu với **nội dung file trước khi đóng gói**. **Runtime** làm việc với **các property và nguồn cấu hình của tiến trình đang chạy**.

Một giá trị đã bị Maven/Gradle thay thành chuỗi thông thường sẽ không tự trở thành biến môi trường mới ở runtime. Ngược lại, một expression Spring được giữ nguyên trong file đã đóng gói vẫn có cơ hội lấy giá trị từ môi trường máy đích.

### 2.1. Một ví dụ có hai môi trường

Ở bước build, project có version **1.8.0**. File source:

~~~properties
app.build-version=@project.version@
app.remote-url=${remote.url:https://default.example.invalid}
~~~

Sau Maven filtering:

~~~properties
app.build-version=1.8.0
app.remote-url=${remote.url:https://default.example.invalid}
~~~

**Lượt chạy ở staging:**

~~~bash
REMOTE_URL=https://staging.example.invalid java -jar app.jar
~~~

Ứng dụng có thể nhận:

~~~text
app.build-version = 1.8.0
app.remote-url    = https://staging.example.invalid
~~~

**Lượt chạy ở production:**

~~~bash
REMOTE_URL=https://production.example.invalid java -jar app.jar
~~~

Cùng một JAR có thể nhận:

~~~text
app.build-version = 1.8.0
app.remote-url    = https://production.example.invalid
~~~

Điểm bất biến là **version đã được đóng gói**; điểm thay đổi là **property runtime**.

## 3. Placeholder runtime của Spring Boot

Spring Boot cho phép dùng **${...}** trong giá trị của **application.properties** và **application.yml**. Khi ứng dụng sử dụng một property, giá trị của nó có thể được giải quyết qua **Environment**.

Ví dụ:

~~~properties
spring.application.name=orders-service
app.display-name=${spring.application.name}
app.remote-url=${remote.url:https://sandbox.example.invalid}
app.request-timeout=${remote.timeout:5s}
~~~

Ý nghĩa:

- **${spring.application.name}** dùng giá trị một property khác trong Environment.
- **${remote.url:https://sandbox.example.invalid}** tìm **remote.url**; nếu không có, dùng URL mặc định.
- **${remote.timeout:5s}** dùng timeout từ nguồn runtime nếu có; nếu không, sử dụng **5s**.

**Dấu hai chấm** phân tách tên property với giá trị mặc định. Không nên hiểu mọi dấu hai chấm bên trong chuỗi là cú pháp YAML hay cú pháp resource filtering. Trong **application.yml**, hãy đặt các biểu thức có dấu hai chấm trong dấu nháy khi phù hợp để rõ ràng.

### 3.1. Ví dụ YAML

~~~yaml
spring:
  application:
    name: orders-service

app:
  display-name: "${spring.application.name}"
  remote-url: "${remote.url:https://sandbox.example.invalid}"
  request-timeout: "${remote.timeout:5s}"
~~~

Các biểu thức này không yêu cầu build tool thay thế. Spring Boot có thể đọc tệp chứa nguyên văn **${...}**, sau đó giải quyết theo nguồn runtime.

### 3.2. Chọn tên property dạng canonical

Spring Boot khuyến nghị dùng tên **lower-case kebab-case** trong placeholder để tận dụng relaxed binding. Ví dụ nên viết:

~~~properties
app.total-price=${pricing.total-price:0}
~~~

thay vì phụ thuộc vào cách viết **${pricing.totalPrice}**. Cách canonical giúp Spring Boot xem xét các dạng tên property tương ứng trong những nguồn như biến môi trường.

Ví dụ biến môi trường cho **pricing.total-price** theo quy tắc relaxed binding là **PRICING_TOTALPRICE**: dấu chấm đổi thành gạch dưới và dấu gạch ngang bị bỏ.

### 3.3. Runtime không có nghĩa là tự cập nhật liên tục

Tên gọi “thay lúc chạy” **không đồng nghĩa** với việc Spring Boot tự phát hiện một biến môi trường mới sau khi tiến trình đã khởi động.

Thông thường **@Value** được tiêm khi bean được tạo, còn **@ConfigurationProperties** được bind trong vòng đời ApplicationContext. Nếu sửa biến môi trường ở terminal khác, một tiến trình Java đã chạy không tự nhận lại giá trị chỉ vì placeholder tồn tại. Nên khởi động lại ứng dụng hoặc dùng cơ chế refresh được thiết kế rõ ràng.

## 4. Đọc giá trị bằng @Value, Environment và @ConfigurationProperties

Giả sử trong dự án Spring Boot 3.3, Java 21 và **spring-boot-starter-web** có:

~~~properties
app.remote-url=${remote.url:https://default.example.invalid}
app.timeout=${remote.timeout:5s}
~~~

Có thể đọc qua **Environment**:

~~~java
package com.example.config;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RuntimeSettings {
    private final Environment environment;

    public RuntimeSettings(Environment environment) {
        this.environment = environment;
    }

    public String remoteUrl() {
        return environment.getProperty("app.remote-url");
    }

    public String timeout() {
        return environment.getProperty("app.timeout");
    }
}
~~~

Hoặc qua **@Value**:

~~~java
package com.example.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class HttpEndpoint {

    private final String url;

    public HttpEndpoint(
            @Value("${app.remote-url}") String url) {
        this.url = url;
    }

    public String url() {
        return url;
    }
}
~~~

Ở ví dụ trên, **@Value("${app.remote-url}")** tìm **app.remote-url**, và giá trị property đó có thể chứa placeholder tham chiếu **remote.url**. Spring giải quyết chuỗi tham chiếu trước khi dùng làm tham số constructor.

Nếu có nhiều tham số có cấu trúc, **@ConfigurationProperties** thường dễ bảo trì hơn:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppOptions(
        String remoteUrl,
        Duration timeout) {
}
~~~

Ứng dụng cần đăng ký scan:

~~~java
package com.example.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigApplication.class, args);
    }
}
~~~

Bộ Binder nhận giá trị đã được giải quyết và chuyển **5s** thành **Duration**. Điều này là việc của Spring Boot runtime, không phải Maven hay Gradle resource filtering.

## 5. Placeholder runtime và thứ tự ưu tiên nguồn cấu hình

Khi giải quyết **${remote.url:default}**, Spring Boot tìm property **remote.url** trong các PropertySource. Có thể có nhiều nguồn cùng cấp giá trị:

~~~text
application.properties: remote.url=https://from-file.example.invalid
environment:            REMOTE_URL=https://from-env.example.invalid
command line:           --remote.url=https://from-cli.example.invalid
~~~

Trong cấu hình Spring Boot thông thường, biến môi trường ưu tiên cao hơn Config Data file, và tham số command-line ưu tiên cao hơn biến môi trường. Vì thế, nếu cả ba đều hiện diện và không có nguồn khác ưu tiên cao hơn, placeholder sẽ dùng giá trị từ command-line.

Ví dụ:

~~~bash
java -jar app.jar \
  --remote.url=https://from-cli.example.invalid
~~~

Đây là một cách **thay cấu hình runtime**, không tạo lại JAR.

**Giá trị mặc định sau dấu hai chấm** được dùng khi key tham chiếu không được cung cấp theo cơ chế giải quyết property. Nó không phải một “nguồn cấu hình toàn cục” mới, và cũng không thay thế quy tắc ưu tiên giữa các PropertySource.

### 5.1. Không có giá trị mặc định

~~~properties
app.needed-url=${remote.required-url}
~~~

Nếu **remote.required-url** không có, việc resolve tại vị trí sử dụng có thể gây lỗi unresolved placeholder, tùy cơ chế truy cập và cấu hình resolver. Với key bắt buộc, nên chủ động validation khi khởi động thay vì âm thầm dùng một endpoint giả.

### 5.2. Tránh vòng tham chiếu

~~~properties
app.first=${app.second}
app.second=${app.first}
~~~

Đây là phụ thuộc vòng tròn, không có giá trị cuối hợp lý. Cần thiết kế property chain theo một chiều và chọn nơi đặt giá trị gốc rõ ràng.

## 6. Resource filtering của Maven là gì?

**Maven resource filtering** thuộc giai đoạn build. Plugin xử lý resources đọc những tệp được đánh dấu cần lọc, tìm token theo delimiter được cấu hình, rồi viết nội dung đã thay vào thư mục output.

Khi sử dụng **spring-boot-starter-parent**, Spring Boot thiết lập mặc định thuận tiện cho tệp cấu hình ứng dụng, cho phép tham chiếu **Maven project properties** bằng token kiểu:

~~~text
@project.version@
@project.artifactId@
@project.build.sourceEncoding@
@java.version@
~~~

Ví dụ **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.8.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**src/main/resources/application.properties**:

~~~properties
spring.application.name=@project.artifactId@
app.build-version=@project.version@
app.java-target=@java.version@
app.remote-url=${remote.url:https://default.example.invalid}
~~~

Khi chạy:

~~~bash
./mvnw clean package
~~~

Maven xử lý tài nguyên và đóng gói những giá trị build metadata. Bản file đã được xử lý trong **target/classes/application.properties** sẽ tương đương:

~~~properties
spring.application.name=orders-service
app.build-version=1.8.0
app.java-target=21
app.remote-url=${remote.url:https://default.example.invalid}
~~~

Ở đây dấu **@...@** đã được xử lý khi build; dấu **${...}** vẫn được giữ cho Spring Boot khi runtime.

**Lưu ý về version ví dụ:** **3.3.13** là ví dụ cho một phiên bản thuộc dòng Spring Boot 3.3; trong dự án thật chọn phiên bản đã được tổ chức phê duyệt và sẵn có trong repository. **1.8.0** là version giả định của ứng dụng, không phải version Spring Boot.

### 6.1. Vì sao Maven ưu tiên @...@ cho cấu hình Spring Boot?

Maven Resources Plugin có thể nhận các delimiter khác nhau, bao gồm kiểu **${...}** nếu bật default delimiters. Nhưng Spring cũng dùng **${...}** làm placeholder runtime. Nếu cả build tool và Spring cùng cố xử lý dấu **${...}**, có thể xảy ra:

- Maven thay một biểu thức vốn phải chờ đến runtime.
- Build fail vì token không tìm được biến trong context của build.
- Giá trị môi trường hoặc mật khẩu bị chèn cố định vào artifact.
- Hai nhóm developer nhận kết quả build khác nhau chỉ vì build properties khác nhau.

Cấu hình **spring-boot-starter-parent** dùng delimiter **@...@** cho filtering giúp phân biệt rõ:

~~~text
@project.version@       -> Maven xử lý lúc build
${remote.url:default}   -> Spring Boot xử lý lúc runtime
~~~

Việc tránh xung đột là lý do kỹ thuật của quy ước này, không chỉ là lựa chọn thẩm mỹ.

### 6.2. Nếu không dùng spring-boot-starter-parent

Khi không kế thừa starter parent, Maven không đương nhiên áp dụng cùng quy tắc lọc tài nguyên. Nếu muốn lọc file cấu hình ứng dụng, phải cấu hình **maven-resources-plugin** và resource filtering tương ứng.

Ví dụ phần có thể đặt trong **build** của **pom.xml**:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-resources-plugin</artifactId>
            <configuration>
                <delimiters>
                    <delimiter>@</delimiter>
                </delimiters>
                <useDefaultDelimiters>false</useDefaultDelimiters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**useDefaultDelimiters=false** là thành phần quan trọng để không cho build tool xử lý nhầm dấu **${...}** dùng bởi Spring.

Khi sử dụng cấu hình lọc resources chung, không nên filter mọi file nhị phân. Với hình ảnh, font, certificate hoặc tài nguyên nhị phân, hãy giữ chúng ở nhóm resources không lọc để tránh thay đổi bytes ngoài ý muốn.

### 6.3. Phạm vi filtering của Maven

Tài liệu Spring Boot mô tả cấu hình parent cho **production resources**. **src/test/resources** không tự động được lọc theo cùng cách đó. Nếu test đang đọc token **@project.version@** trong một file test riêng, đừng mặc nhiên cho rằng Maven đã thay nó chỉ vì **src/main/resources/application.properties** được lọc.

Ngoài ra, một số cách chạy trực tiếp từ **src/main/resources**, ví dụ cấu hình hot reload có lựa chọn thêm source resources trực tiếp vào classpath, có thể bỏ qua bản **target/classes** đã được Maven filtering. Khi cần kiểm chứng, hãy thử chính artifact đã đóng gói thay vì chỉ dựa trên hành vi chạy trong IDE.

## 7. Resource expansion của Gradle

Gradle cũng có thể thay giá trị build-time, nhưng **không nên giả định** mọi tệp cấu hình Spring Boot tự được xử lý giống Maven starter parent. Bạn cần cấu hình task **processResources** nếu muốn expansion.

Ví dụ một **build.gradle** dùng Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.8.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

tasks.named('processResources') {
    filesMatching('application.properties') {
        expand(buildVersion: project.version.toString())
    }
}
~~~

Trong **src/main/resources/application.properties**:

~~~properties
app.build-version=${buildVersion}
app.remote-url=\${remote.url:https://default.example.invalid}
~~~

Khi chạy:

~~~bash
./gradlew clean bootJar
~~~

Gradle **processResources** thay **${buildVersion}** bằng **1.8.0**. Trong tệp template, biểu thức runtime **${remote.url:...}** có dấu escape **\** ở phía trước để **Gradle SimpleTemplateEngine** không cố giải quyết nó.

Tệp đã xử lý trong output được kỳ vọng tương đương:

~~~properties
app.build-version=1.8.0
app.remote-url=${remote.url:https://default.example.invalid}
~~~

Sau đó Spring Boot mới dùng **remote.url** của môi trường chạy để giải quyết placeholder còn lại.

### 7.1. Tại sao Gradle dễ xung đột hơn?

Theo tài liệu Spring Boot, **Gradle expand** sử dụng Groovy **SimpleTemplateEngine** và xử lý token kiểu **${...}**. Đây cũng là kiểu Spring Boot dùng cho runtime. Vì vậy nếu khai báo:

~~~groovy
tasks.named('processResources') {
    expand(project.properties)
}
~~~

để filter toàn bộ resources, các placeholder Spring trong **application.properties** hoặc **application.yml** có thể bị Gradle hiểu nhầm là biểu thức build-time.

Ví dụ source:

~~~properties
app.remote-url=${remote.url:https://runtime.example.invalid}
~~~

Biểu thức này có ý nghĩa hợp lệ với Spring, nhưng không có ý nghĩa như một biến Gradle đơn giản; không thể giả định build tool sẽ luôn giữ nguyên nó. Một chiến lược an toàn là:

1. Giới hạn **filesMatching** chỉ ở những template thực sự cần expansion.
2. Escape các token Spring **\${...}** ở những file được Gradle lọc.
3. Hoặc thiết kế một file metadata build riêng, còn **application.yml** không tham gia filtering.

### 7.2. Khi nào dùng expand(project.properties)?

Nếu dùng **expand(project.properties)**, Gradle có thể đọc các property của Gradle project như **name**, **version**, **description**. Nhưng vì phạm vi key rộng, khả năng tên đụng vào placeholder runtime cũng tăng lên.

Với nhu cầu chỉ đưa version vào artifact, cấu hình rõ **expand(buildVersion: project.version.toString())** và giới hạn file giúp người đọc hiểu chính xác điều gì được phép biến đổi.

**Lưu ý:** ví dụ Gradle trên dùng cú pháp Groovy DSL (**build.gradle**). Với Kotlin DSL (**build.gradle.kts**), cú pháp cấu hình task và map tham số cần chuyển sang Kotlin tương ứng.

## 8. Cách ít xung đột nhất với Gradle: chỉ lọc file metadata riêng

Một thiết kế dễ bảo trì là **không filter application.properties**. Thay vào đó, tạo **build-meta.properties** chứa dữ liệu đã biết khi build, rồi import vào Spring Boot bằng Config Data.

Cấu trúc:

~~~text
src/main/resources/
├── application.properties
└── build-meta.properties
~~~

**application.properties**: chỉ dùng placeholder runtime, không được Gradle expand:

~~~properties
spring.application.name=orders-service
spring.config.import=classpath:build-meta.properties

app.remote-url=${remote.url:https://default.example.invalid}
app.timeout=${remote.timeout:5s}
~~~

**build-meta.properties**: chỉ dùng build placeholder:

~~~properties
app.build-version=${buildVersion}
~~~

**build.gradle**:

~~~groovy
version = '1.8.0'

tasks.named('processResources') {
    filesMatching('build-meta.properties') {
        expand(buildVersion: project.version.toString())
    }
}
~~~

Khi build, **build-meta.properties** được thay thành:

~~~properties
app.build-version=1.8.0
~~~

Trong khi **application.properties** giữ nguyên:

~~~properties
spring.application.name=orders-service
spring.config.import=classpath:build-meta.properties
app.remote-url=${remote.url:https://default.example.invalid}
app.timeout=${remote.timeout:5s}
~~~

Đây là cách tách nhiệm vụ:

- **build-meta.properties** chứa thông tin gắn với bản dựng.
- **application.properties** chứa cấu hình cho mỗi lượt khởi động.
- **spring.config.import** làm Spring Boot đọc file metadata như một nguồn cấu hình bổ sung.
- Maven/Gradle không cần cố xử lý các placeholder runtime.

Một số dự án cũng dùng **spring-boot:build-info** (Maven) hoặc task **bootBuildInfo** (Gradle) để tạo metadata build theo chuẩn Spring Boot, rồi đọc từ **BuildProperties** khi cần. Cách này phù hợp nếu mục tiêu chỉ là công bố thông tin build, không nhất thiết phải chèn version vào **application.properties**.

## 9. Thực hành so sánh trước và sau build

Một cách học rõ nhất là kiểm tra **ba phiên bản của cùng một file**:

1. File source trong repository.
2. File resource sau Maven/Gradle processing.
3. Giá trị Spring Boot cung cấp khi ứng dụng chạy.

### 9.1. Trước khi build

Ví dụ Maven **src/main/resources/application.properties**:

~~~properties
app.build-version=@project.version@
app.remote-url=${remote.url:https://sandbox.example.invalid}
~~~

Ở trạng thái này, cả hai token còn nguyên văn.

### 9.2. Sau khi build

Chạy:

~~~bash
./mvnw clean package
~~~

Mở **target/classes/application.properties**. Nếu Maven filtering được cấu hình đúng, file sẽ tương tự:

~~~properties
app.build-version=1.8.0
app.remote-url=${remote.url:https://sandbox.example.invalid}
~~~

**1.8.0** đã được đóng gói. **${remote.url:...}** vẫn còn trong resource và chờ Spring xử lý.

Với Gradle, kiểm tra **build/resources/main/application.properties** hoặc file metadata chuyên dụng tương ứng. Đừng chỉ xem **src/main/resources** rồi kết luận filtering có hoạt động hay không.

### 9.3. Lúc chạy

Tạo một endpoint quan sát hai giá trị không nhạy cảm:

~~~java
package com.example.config;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigDemoController {

    private final Environment environment;

    public ConfigDemoController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/config-demo")
    public Map<String, String> show() {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("buildVersion",
                environment.getProperty("app.build-version", "unknown"));
        result.put("remoteUrl",
                environment.getProperty("app.remote-url", "unknown"));
        return result;
    }
}
~~~

Khởi động:

~~~bash
REMOTE_URL=https://staging.example.invalid java -jar app.jar
~~~

Gọi:

~~~bash
curl http://localhost:8080/config-demo
~~~

Kết quả minh họa:

~~~json
{
  "buildVersion": "1.8.0",
  "remoteUrl": "https://staging.example.invalid"
}
~~~

Dừng ứng dụng và chạy **cùng artifact** với biến khác:

~~~bash
REMOTE_URL=https://production.example.invalid java -jar app.jar
~~~

Kết quả:

~~~json
{
  "buildVersion": "1.8.0",
  "remoteUrl": "https://production.example.invalid"
}
~~~

Đây là bằng chứng trực quan rằng **version bị cố định khi build**, còn **remoteUrl do runtime quyết định**.

Nếu kiểm tra JAR trực tiếp, resource của Spring Boot executable JAR thường nằm dưới **BOOT-INF/classes/**. Công cụ như **jar tf** cho phép liệt kê nội dung; cách giải nén hoặc xem nội dung file có thể tùy hệ điều hành và công cụ sẵn có. Quan trọng là đối chiếu bản đóng gói, không chỉ bản source.

## 10. Phạm vi cấu hình thực tế và trường hợp dùng

### 10.1. Giá trị nên được định nghĩa tại build time

Một số ví dụ:

- Version module hoặc artifact, ví dụ **1.8.0**.
- Tên artifact/build name.
- Git commit SHA, **nếu** pipeline có cơ chế rõ ràng cung cấp giá trị đó.
- Build timestamp, **nếu** quá trình build cần metadata này.
- Thông tin tương thích của gói đã phát hành.

Những thông tin ấy mô tả **sản phẩm được build ra**, nên thường không đổi khi chuyển JAR qua staging, UAT và production.

Không nên dùng resource filtering để “đóng gói” mật khẩu hoặc token của môi trường triển khai. Dù file source chỉ chứa placeholder, file sau filtering sẽ chứa giá trị thật và có thể tồn tại trong artifact repository, cache CI, container image layer hoặc bản backup.

### 10.2. Giá trị nên được cấp tại runtime

Một số ví dụ:

- URL database và connection pool.
- Endpoint API bên ngoài.
- Timeout/circuit breaker và ngưỡng retry tùy môi trường.
- Feature flag được cấu hình tại thời điểm deploy.
- Cấu hình port, log level, namespace hoặc account.
- Credential/secrets từ cơ chế cấp runtime được kiểm soát.

Những thông số đó mô tả **một lượt chạy cụ thể**. Tách chúng khỏi build giúp triển khai đúng nguyên tắc **build once, deploy many**.

### 10.3. Những tình huống có thể cần cả hai

Ví dụ một API gửi header chứa build version nhưng sử dụng một endpoint phụ thuộc môi trường:

~~~properties
app.build-version=@project.version@
app.partner-url=${partner.url:https://sandbox-partner.example.invalid}
~~~

Runtime có thể biết cả hai giá trị, nhưng nguồn gốc của chúng khác nhau. Điều này hoàn toàn bình thường nếu team có quy ước rõ ràng và build filtering không chạm nhầm vào runtime placeholders.

## 11. Không nhầm Maven POM interpolation với Spring placeholders

Trong **pom.xml**, Maven dùng cú pháp kiểu:

~~~xml
<version>${revision}</version>
~~~

Đây là Maven model/property interpolation khi xử lý POM, **không phải** Spring Environment property resolution của ứng dụng.

Trong file **application.properties** được Maven resource filtering, cách được Spring Boot khuyến nghị với **spring-boot-starter-parent** là:

~~~properties
app.version=@project.version@
~~~

Đừng suy ra rằng vì Maven hiểu **${project.version}** trong **pom.xml** nên nó cũng nên đọc mọi **${...}** trong **application.yml**. Hai file, hai hệ thống placeholder và hai mục đích khác nhau.

Một giá trị **@project.version@** chưa được thay trong resource sau build thường có nghĩa là **filtering chưa được áp dụng phù hợp** hoặc token không có dữ liệu build tương ứng; Spring Boot không tự biết rằng **@project.version@** là cú pháp Maven.

## 12. Khi nào dùng profile, khi nào dùng build filtering?

Spring Boot hỗ trợ **application-dev.yml**, **application-prod.yml** và các profile khác. Những file này được xét khi ứng dụng chạy dựa trên active profiles:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

**Profile** là một phần của Config Data runtime. Nếu bạn đóng gói cả **application-dev.yml** và **application-prod.yml** trong cùng JAR, việc chọn file theo profile xảy ra lúc chạy, **không phải** Maven/Gradle đã “biên dịch” hai profile đó thành một giá trị duy nhất.

So sánh:

~~~text
Build filtering:
src/main/resources -> thay token build -> artifact

Spring profile:
artifact + spring.profiles.active -> chọn Config Data runtime
~~~

Bởi vậy, một file **application-prod.yml** có thể chứa placeholder runtime như:

~~~yaml
app:
  endpoint: "${partner.prod-url:https://default.example.invalid}"
~~~

và giá trị **partner.prod-url** vẫn có thể đến từ biến môi trường hoặc cấu hình ngoài khi production chạy.

Tránh tạo mỗi môi trường một JAR riêng chỉ để nhúng endpoint vào file cấu hình ở giai đoạn build. Điều đó làm phức tạp khả năng chứng minh rằng các môi trường đang chạy **cùng một artifact** đã được kiểm thử.

## 13. Resource filtering trong CI/CD và reproducibility

Một pipeline thường có các bước:

~~~text
Source code
  |
  v
Build + unit tests
  |
  v
Artifact registry (app.jar / Docker image)
  |
  +----------------+
  |                |
  v                v
Staging          Production
  |                |
  v                v
Runtime env      Runtime env
  |                |
  v                v
Spring resolves placeholders independently
~~~

Nếu version **1.8.0** và commit SHA được nhúng lúc build, chúng nên giữ nguyên giữa staging và production cho cùng artifact.

Ngược lại, nếu pipeline rebuild JAR trước mỗi lần deploy chỉ để thay **db.url** hoặc **partner.url** bằng Maven filtering, bạn đã tạo ra **những artifact khác nhau**, dù source commit có giống nhau.

Phân biệt này quan trọng với:

- **Truy xuất nguồn gốc:** cùng artifact hash giữa các môi trường.
- **Quy trình rollback:** triển khai lại artifact cũ cùng tập cấu hình phù hợp.
- **Quản lý thay đổi:** cập nhật cấu hình không nhất thiết đồng nghĩa sửa source/build.
- **Bảo mật:** bí mật ở runtime tránh bị lưu sẵn trong artifact phát hành.
- **Khả năng tái lập:** metadata build bất biến có thể được kiểm tra trên bản đã đóng gói.

### 13.1. Cẩn trọng với cache và log build

Nếu build script đọc secret rồi mở rộng vào resource, secret có thể rơi vào:

- **target/classes** hoặc **build/resources/main**.
- JAR hoặc WAR.
- Lớp Docker image.
- Build cache hoặc artifact cache.
- Log của plugin hoặc hệ thống CI/CD nếu vô tình in ra nội dung.

Không coi việc không commit secret vào Git là đủ nếu build filtering vẫn đưa secret vào artifact. Nên dùng biến môi trường, Secret Manager hoặc cơ chế mount secret ở runtime.

## 14. Các lỗi thường gặp và cách xử lý

### 14.1. Maven để nguyên @project.version@

**Triệu chứng:**

~~~properties
app.build-version=@project.version@
~~~

xuất hiện nguyên vẹn trong **target/classes/application.properties**.

**Nguyên nhân thường gặp:** không kế thừa starter parent, chưa bật filtering cho resources hoặc đã tùy chỉnh plugin làm mất delimiter **@**.

**Hướng xử lý:** kiểm tra cấu hình resources và maven-resources-plugin. Nếu không dùng starter parent, cấu hình rõ **filtering=true**, delimiter **@** và **useDefaultDelimiters=false**, rồi build lại.

### 14.2. Gradle lỗi khi gặp placeholder runtime

**Triệu chứng:** **processResources** lỗi khi cố đánh giá **${remote.url:...}**.

**Nguyên nhân:** **expand(...)** của Gradle xử lý token **${...}** bằng Groovy template engine, trong khi token vốn dành cho Spring.

**Hướng xử lý:** escape placeholder runtime trong các file được lọc (**\${...}**) hoặc lọc file metadata riêng thay vì lọc tất cả application resources.

### 14.3. Thay giá trị biến môi trường nhưng không thấy cập nhật

**Triệu chứng:** đổi **REMOTE_URL** sau khi Java đã chạy nhưng giá trị endpoint không đổi.

**Nguyên nhân:** tiến trình hiện tại không tự nhận thay đổi của môi trường bên ngoài, và bean có thể đã được bind khi ApplicationContext khởi tạo.

**Hướng xử lý:** khởi động lại ứng dụng với biến môi trường mới, hoặc áp dụng cơ chế refresh chính thức nếu dự án có yêu cầu cập nhật runtime động.

### 14.4. Chạy ở IDE khác với chạy artifact đóng gói

**Triệu chứng:** khi **java -jar** thì version đúng, còn khi chạy từ source/resources trực tiếp lại thấy **@project.version@**.

**Nguyên nhân:** IDE hoặc chế độ chạy đã bypass bước xử lý resources hoặc đang dùng tài nguyên source thay vì output đã filter.

**Hướng xử lý:** kiểm tra classpath và các bước build của từng cách chạy. Đối với giá trị build metadata, thử từ artifact đã đóng gói.

### 14.5. Coi placeholder runtime là phép thay thế văn bản trong source file

**Triệu chứng:** tìm trong **src/main/resources** hoặc file trong JAR vẫn thấy **${remote.url:...}**, nên kết luận Spring không làm việc.

**Nguyên nhân:** Spring không nhất thiết ghi lại file; nó giải quyết **giá trị được đọc** qua Environment.

**Hướng xử lý:** đọc **Environment.getProperty(...)** hoặc **@ConfigurationProperties** ở lượt chạy, không chỉ nhìn nội dung source file.

### 14.6. Lẫn cú pháp @...@ và ${...}

**Triệu chứng:** property trả về nguyên **@project.version@** hoặc **${buildVersion}**.

**Nguyên nhân:** token dành cho công cụ xử lý khác hoặc không có nguồn giá trị phù hợp.

**Hướng xử lý:** xác định token phải được xử lý lúc build hay runtime. Nếu build, kiểm tra file output sau processResources; nếu runtime, kiểm tra PropertySources và tên key.

### 14.7. Dùng build filtering để giấu secret

**Triệu chứng:** source chỉ có **@db.password@**, nhưng sau build **application.properties** chứa password thật.

**Nguyên nhân:** filtering thay bằng giá trị thật và đóng gói vào artifact.

**Hướng xử lý:** chuyển secret sang hệ thống cấp runtime; thu hồi bí mật đã lộ, thay artifact/cache bị ảnh hưởng và rà soát pipeline theo chính sách bảo mật.

### 14.8. Lọc nhầm file nhị phân

**Triệu chứng:** resource như ảnh, chứng chỉ hoặc tệp nén bị lỗi sau build.

**Nguyên nhân:** filtering hoạt động trên bytes/văn bản với giả định không phù hợp cho tài nguyên nhị phân.

**Hướng xử lý:** chỉ lọc file text đã chọn; tách tài nguyên nhị phân ra nhóm không filter.

## 15. Thực hành: xác định ai thay placeholder

### Bài A — Runtime placeholder không cần build lại

1. Tạo **application.properties** có **app.remote-url=${remote.url:https://default.example.invalid}**.
2. Viết một bean đọc **Environment.getProperty("app.remote-url")**.
3. Build JAR.
4. Chạy lần một với **REMOTE_URL=https://staging.example.invalid**.
5. Dừng rồi chạy lần hai với **REMOTE_URL=https://production.example.invalid**.

**Kết quả cần quan sát:** cùng một JAR nhưng nhận URL khác nhau ở hai lượt chạy.

### Bài B — Maven filtering chèn build version

1. Dùng dự án Maven có **spring-boot-starter-parent**, khai báo version **1.8.0**.
2. Thêm **app.build-version=@project.version@** vào file cấu hình.
3. Chạy **./mvnw clean package**.
4. Đọc **target/classes/application.properties**.
5. Đọc giá trị property khi chạy JAR.

**Kết quả cần quan sát:** token **@project.version@** đã thành **1.8.0** trong file sau build; thay biến môi trường thông thường không làm sửa bytes của bản JAR.

### Bài C — Gradle chỉ lọc metadata

1. Tạo file **build-meta.properties** với **app.build-version=${buildVersion}**.
2. Dùng **filesMatching('build-meta.properties') { expand(buildVersion: project.version.toString()) }**.
3. Giữ placeholder runtime trong **application.properties** và import **classpath:build-meta.properties**.
4. Build bằng **./gradlew bootJar**.
5. Đối chiếu **build/resources/main/** và chạy ứng dụng với biến môi trường.

**Kết quả cần quan sát:** build metadata được chèn trước khi đóng gói, còn placeholder Spring được giữ đến khi ứng dụng chạy.

### Bài D — Nhận diện xung đột

1. Trong một nhánh thử nghiệm, bật Gradle **expand(project.properties)** lên file **application.properties** có **${remote.url:...}**.
2. Quan sát build có thể lỗi hoặc xử lý không như ý định.
3. Chuyển sang lọc riêng metadata hoặc escape token runtime.
4. Build lại và đối chiếu resource output.

**Kết quả cần quan sát:** hai hệ thống placeholder dùng cùng cú pháp có thể tranh nhau xử lý; cần quy ước ranh giới rõ.

### Bài E — Phân loại dữ liệu cấu hình

Với những key sau, hãy xác định nên thuộc build-time hay runtime:

| Key | Phân loại khuyến nghị | Lý do |
| --- | --- | --- |
| **app.build-version** | Build-time | Mô tả artifact |
| **app.git-commit** | Build-time, nếu được pipeline cấp | Mô tả nguồn của artifact |
| **spring.datasource.url** | Runtime | Thay theo môi trường triển khai |
| **spring.datasource.password** | Runtime, có kiểm soát secret | Không nên đóng gói bí mật |
| **app.partner-url** | Runtime | Phụ thuộc nơi ứng dụng chạy |
| **app.request-timeout** | Runtime | Có thể điều chỉnh theo môi trường |
| **app.build-timestamp** | Build-time, nếu cần | Thuộc thông tin bản dựng |

## 16. Ghi nhớ

- **Spring placeholder ${...}** được giải quyết thông qua **Environment** ở runtime; nó không cần thay đổi file đã đóng gói.
- **Maven/Gradle resource filtering** sửa nội dung tài nguyên trong giai đoạn build; giá trị được chèn có mặt trong output/artifact.
- Với **spring-boot-starter-parent**, token **@project.version@** giúp tách build metadata khỏi placeholder runtime kiểu **${...}**.
- Với **Gradle expand**, phải chú ý xung đột cú pháp **${...}**; nên escape token Spring trong file bị filter hoặc dùng file metadata riêng.
- Giá trị **bất biến theo artifact** thích hợp cho build-time; giá trị **thay theo môi trường** thích hợp cho runtime.
- Thay một biến môi trường khi process đang chạy thường không tự cập nhật bean đã được bind.
- Không filter secret thật vào JAR hoặc container image.
- Muốn biết **đã được thay ở giai đoạn nào**, kiểm tra file trong **target/classes** hoặc **build/resources/main**, rồi kiểm tra giá trị runtime từ **Environment**.

**Tài liệu tham khảo chính thức:**

- Spring Boot 3.3 — Externalized Configuration, mục *Property Placeholders*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot — *How-to: Properties and Configuration*, mục *Automatically Expand Properties at Build Time*: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
- Maven Resources Plugin — Filtering: https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html
- Gradle User Manual — Process resources và copy/expand: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Copy.html
