# Khai báo annotation processor trong Gradle và Maven cho metadata cấu hình Spring Boot

## 1. Bài toán: IDE hiểu được các thuộc tính cấu hình tự định nghĩa

Spring Boot có nhiều thuộc tính quen thuộc như `server.port`, `spring.application.name` hay `spring.datasource.url`. Với các thuộc tính của framework, IDE thường có thể gợi ý tên khóa, hiển thị mô tả và cảnh báo một số cách dùng không phù hợp.

Nhưng dự án cũng thường định nghĩa nhóm cấu hình riêng:

~~~yaml
app:
  notification:
    enabled: true
    sender-name: catalog-service
    max-retries: 4
    retry-delay: 5s
~~~

Và Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        String senderName,
        int maxRetries,
        Duration retryDelay
) {}
~~~

Ứng dụng có thể bind các giá trị vào `NotificationProperties` mà không cần một file metadata riêng. Tuy nhiên, một IDE chưa biết về các property tùy biến của dự án có thể không gợi ý được `app.notification.sender-name` hay không hiển thị mô tả khi lập trình viên sửa `application.yml`.

Để hỗ trợ công cụ phát triển, Spring Boot cung cấp **`spring-boot-configuration-processor`**: một Java annotation processor xử lý thông tin từ các kiểu `@ConfigurationProperties` tại **thời điểm biên dịch** rồi sinh metadata cấu hình dưới dạng JSON.

Khi cấu hình build đúng, chuỗi hoạt động có thể hình dung:

~~~text
Class/record @ConfigurationProperties
               │
               ▼
       Java compilation
               │
               ▼
spring-boot-configuration-processor
               │
               ▼
META-INF/spring-configuration-metadata.json
               │
               ▼
IDE / công cụ phát triển đọc metadata
               │
               ▼
Gợi ý tên thuộc tính, kiểu, mô tả, giá trị mặc định...
~~~

**Mục tiêu của bài:** biết cách khai báo processor trong **Gradle** và **Maven**, phân biệt dependency biên dịch với dependency chạy ứng dụng, hiểu file JSON được tạo ở đâu, xử lý những trường hợp kết hợp **Lombok** hoặc dự án nhiều module, và kiểm chứng kết quả bằng build thực tế.

## 2. Annotation processor là gì?

Trong Java, annotation như `@ConfigurationProperties`, `@Component` hoặc `@Deprecated` có thể xuất hiện trong mã nguồn. Nhưng **annotation không tự động đồng nghĩa với việc một công cụ nào đó sẽ sinh file**.

Một **annotation processor** là thành phần được trình biên dịch Java gọi trong quá trình annotation processing. Nó có thể đọc thông tin về các annotation, class, method, field, constructor hoặc type element để tạo thêm mã nguồn hay tài nguyên.

Spring Boot configuration processor dùng cơ chế này để tạo **metadata mô tả thuộc tính cấu hình**. Nó không cần khởi động application context, không cần kết nối cơ sở dữ liệu và không cần chạy web server để phát hiện các kiểu `@ConfigurationProperties` có thể xử lý.

Phân biệt ba trách nhiệm:

| Thành phần | Vai trò |
| --- | --- |
| `@ConfigurationProperties` | Khai báo prefix và kiểu Java đích để bind cấu hình |
| Spring Boot Binder | Khi ứng dụng chạy, lấy property source rồi liên kết giá trị vào Java object |
| `spring-boot-configuration-processor` | Khi biên dịch, tạo metadata JSON cho IDE/công cụ |

Một class `@ConfigurationProperties` **vẫn có thể bind thành công mà không có processor**. Ngược lại, thêm processor mà quên đăng ký bean `@ConfigurationProperties` thì metadata có thể được tạo, nhưng ứng dụng vẫn có thể không có bean cấu hình để inject.

Đây là sự khác biệt then chốt: **metadata phục vụ trải nghiệm công cụ và tài liệu hóa, không thay thế runtime binding**.

## 3. Tên artifact và file được sinh ra

Artifact dùng cho dự án Spring Boot:

~~~text
org.springframework.boot:spring-boot-configuration-processor
~~~

Tên file đầu ra chuẩn:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Khi biên dịch bằng Maven, một vị trí thường gặp là:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Với Gradle và Java source set `main`, vị trí thường gặp là:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Đường dẫn chính xác phụ thuộc toolchain, source set, plugin và cấu trúc build. Điều quan trọng là **file nằm trong output của compilation**, từ đó thường có thể được đóng gói vào JAR.

Một JSON metadata minh họa:

~~~json
{
  "groups": [
    {
      "name": "app.notification",
      "type": "com.example.demo.config.NotificationProperties",
      "sourceType": "com.example.demo.config.NotificationProperties"
    }
  ],
  "properties": [
    {
      "name": "app.notification.enabled",
      "type": "java.lang.Boolean",
      "sourceType": "com.example.demo.config.NotificationProperties"
    },
    {
      "name": "app.notification.sender-name",
      "type": "java.lang.String",
      "sourceType": "com.example.demo.config.NotificationProperties"
    },
    {
      "name": "app.notification.retry-delay",
      "type": "java.time.Duration",
      "sourceType": "com.example.demo.config.NotificationProperties"
    }
  ]
}
~~~

Đây là **ví dụ hình dạng JSON**, không phải cam kết rằng từng field, tên type hay thứ tự phần tử trong file được sinh ở mọi phiên bản sẽ giống hệt.

Một file metadata có thể có các nhóm dữ liệu:

- `groups`: các nhóm cấu hình và kiểu nguồn.
- `properties`: tên property, type, source, mô tả, default nếu processor có đủ thông tin.
- `hints`: gợi ý giá trị/nhà cung cấp giá trị cho một số thuộc tính.

Công cụ IDE có thể đọc JSON để hỗ trợ code completion. Tài liệu API của Spring Boot và bản metadata thực tế là nguồn chuẩn để hiểu các trường có thể xuất hiện.

## 4. Chuẩn bị một class cấu hình mẫu

Để minh họa hai build tool trên cùng một ví dụ, giả sử có:

~~~text
src/
  main/
    java/com/example/demo/
      DemoApplication.java
      config/ClientProperties.java
    resources/
      application.yml
~~~

`ClientProperties.java`:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Thiết lập HTTP client khi gọi dịch vụ catalog.
 */
@ConfigurationProperties(prefix = "app.catalog-client")
public record ClientProperties(
        String baseUrl,
        Duration connectTimeout,
        int maxRetries
) {}
~~~

`application.yml`:

~~~yaml
app:
  catalog-client:
    base-url: https://catalog.example.org
    connect-timeout: 3s
    max-retries: 4
~~~

`DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Ở đây `@ConfigurationPropertiesScan` đăng ký bean cấu hình trong package được quét. Đây là **cơ chế runtime** tách biệt với việc configuration processor nhận diện annotation và sinh metadata.

Tên canonical của ba property là:

~~~properties
app.catalog-client.base-url
app.catalog-client.connect-timeout
app.catalog-client.max-retries
~~~

Sau khi được cấu hình, processor có thể đưa thông tin về những property này vào metadata để IDE nhận diện chúng.

## 5. Gradle Groovy DSL: khai báo bằng `annotationProcessor`

Trong dự án sử dụng `build.gradle` (Groovy DSL), cách khai báo phổ biến:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Nếu dự án dùng dependency management hoặc BOM của Spring Boot đúng cách, có thể không cần ghi version riêng tại dòng `annotationProcessor` vì phiên bản artifact được quản lý cùng các dependency Spring Boot.

**Ý nghĩa của `annotationProcessor` trong Gradle:**

- Đưa processor vào **annotation processor path** của task compile.
- Cho phép trình biên dịch gọi processor để sinh metadata.
- Không tự động đưa processor vào **runtime classpath** như một dependency `implementation`.
- Giúp phân tách một công cụ **chỉ phục vụ build** với thư viện mà ứng dụng cần khi chạy.

Một ví dụ gần với dự án thực tế:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trong ví dụ đầy đủ, hai chuỗi `<spring-boot-version>` và `<dependency-management-plugin-version>` là **placeholder hướng dẫn**: thay bằng phiên bản plugin phù hợp với dự án trước khi chạy. Với một dự án Spring Boot đã được tạo sẵn, thường chỉ cần bổ sung đúng **một dòng `annotationProcessor`** trong block `dependencies`, không cần viết lại toàn bộ file build.

Một số dự án quản lý version qua Gradle version catalog hoặc platform BOM thay vì plugin dependency-management. Khi đó dùng cơ chế quản lý version đang có của dự án, tránh khai báo trùng hoặc thay đổi version không cần thiết.

## 6. Gradle Kotlin DSL: khai báo trong `build.gradle.kts`

Nếu dự án sử dụng Kotlin DSL, cú pháp khác Groovy DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")

    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )
}
~~~

Ví dụ block đầy đủ hơn:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-plugin-version>"
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Lưu ý:

- `build.gradle` là Groovy DSL: `annotationProcessor 'group:artifact'`.
- `build.gradle.kts` là Kotlin DSL: `annotationProcessor("group:artifact")`.
- Dòng khai báo thường nằm trong module **chứa source code `@ConfigurationProperties`**, không nhất thiết là module chứa `main()` nếu dự án nhiều module.
- Một dự án Java dùng file build Kotlin DSL **không có nghĩa mã nguồn Java đã chuyển thành Kotlin**. Ở đây Kotlin chỉ là ngôn ngữ của build script.

### Lệnh biên dịch Gradle

Linux/macOS:

~~~bash
./gradlew clean classes
~~~

Windows:

~~~powershell
.\gradlew.bat clean classes
~~~

Gradle sẽ biên dịch các class của source set `main`. Nếu Java annotation processing được kích hoạt và processor tìm được class cấu hình phù hợp, metadata sẽ có mặt trong output compile.

Sau khi build, tìm file:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Nếu dự án có cấu trúc compile hoặc output khác, kiểm tra task `compileJava` và vị trí output do Gradle báo thay vì mặc định chắc chắn mọi dự án phải có cùng đường dẫn.

## 7. Vì sao không nên chỉ dùng `implementation` cho processor ở Gradle?

Hai cấu hình nhìn tương tự nhưng có mục đích khác:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

và:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Với Gradle hiện đại, processor cần nằm trên **annotation processor path** để chạy đúng trong `compileJava`. Đặt artifact ở `implementation` không phải cách khai báo chuyên biệt và có thể không kích hoạt annotation processing như kỳ vọng.

Ngoài ra, `implementation` còn mô tả một thư viện mà mã ứng dụng phụ thuộc lúc biên dịch và có thể có mặt trên runtime classpath. Điều này không đúng mục tiêu của configuration processor: ứng dụng **không cần nó để bind cấu hình khi đang chạy**.

Bảng so sánh:

| Gradle configuration | Mục đích chính | Có phù hợp cho configuration processor? |
| --- | --- | --- |
| `implementation` | Thư viện mã ứng dụng sử dụng | Không phải lựa chọn khuyến nghị |
| `compileOnly` | Có mặt khi compile, không có mặt khi runtime | Chưa đủ để bảo đảm processor được chạy |
| `annotationProcessor` | Processor được compiler gọi khi biên dịch Java | **Có** |
| `runtimeOnly` | Thư viện cần khi chạy nhưng không compile | Không |
| `testAnnotationProcessor` | Processor cho nguồn test Java | Chỉ khi cần xử lý annotation của source set test |

Không thêm cả `implementation` lẫn `annotationProcessor` cho cùng processor nếu không có lý do kỹ thuật cụ thể. Thông thường chỉ cần `annotationProcessor`.

## 8. Maven: cách khai báo dependency `optional` thông dụng

Trong dự án sử dụng Maven và Spring Boot parent hoặc BOM quản lý dependency, cách gọn thường thấy:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

`optional=true` của Maven có nghĩa dependency này không được tự động kéo theo như một **transitive dependency** khi một dự án khác phụ thuộc vào module hiện tại. Đây là lựa chọn hợp lý cho công cụ phục vụ build.

Nhưng cần hiểu chính xác:

- `optional=true` **không phải** một chỉ thị “tắt runtime” trong mọi cơ chế đóng gói.
- `optional=true` **không tự bật** annotation processing nếu môi trường build đã tắt processor.
- Với dự án dùng explicit processor path, có thể cần đặt processor trên đường dẫn riêng qua Maven Compiler Plugin.
- Khi cấu hình `annotationProcessorPaths`, các processor không nằm trong danh sách có thể không được Maven Compiler Plugin phát hiện như khi dùng cơ chế classpath discovery trước đó.

Do đó, **khai báo optional dependency** và **cấu hình compiler processor path** là hai cách tiếp cận có thể bổ sung hoặc thay thế tùy build; cần tránh thêm nhiều cấu hình lặp lại chỉ vì sao chép từ các bài hướng dẫn khác nhau.

## 9. Maven: ví dụ `pom.xml` dùng Spring Boot parent

Một POM tối giản cho dự án Java/Spring Boot có thể bắt đầu:

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
    <artifactId>config-metadata-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
~~~

**Chú ý phiên bản:** `3.3.13` ở đây là một **ví dụ của dòng Spring Boot 3.3**, không phải khuyến nghị sử dụng phiên bản đó cho một dự án mới. Trong công việc thực tế, giữ version Boot đã được dự án quyết định và dùng các thành phần tương thích, đặc biệt khi hệ thống đã có parent, BOM hoặc cấu hình quản lý dependency riêng.

Maven lệnh compile:

~~~bash
mvn clean compile
~~~

Với một build hỗ trợ annotation processor discovery thông thường, compiler có thể nạp processor từ các dependency thích hợp và tạo metadata. Tuy vậy, trên một số Java toolchain mới hoặc cấu hình compiler có giới hạn annotation processing, **dependency optional đơn thuần không bảo đảm processor thực thi**. Khi cần cấu hình đáng tin cậy và tường minh, sử dụng processor path như phần kế tiếp.

## 10. Maven Compiler Plugin: chỉ định annotation processor path

Một cách rõ ràng hơn là khai báo processor trong `maven-compiler-plugin`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                        <version>${spring.boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong snippet này, `spring.boot.version` là **property tự khai báo** hoặc được cung cấp theo build của dự án; nó không nhất thiết xuất hiện sẵn chỉ vì ứng dụng dùng Spring Boot. Trước khi sử dụng, phải bảo đảm property có giá trị, ví dụ:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring.boot.version>3.3.13</spring.boot.version>
</properties>
~~~

Nếu parent đã cố định version khác, phải cập nhật `spring.boot.version` cho khớp; tránh vô tình cho processor chạy khác dòng version với Spring Boot đang biên dịch.

Ý nghĩa:

- `annotationProcessorPaths`: compiler chỉ định những artifact dành cho annotation processing.
- `parameters=true`: giữ thông tin tên tham số khi biên dịch Java, hữu ích cho constructor binding; **không phải điều kiện tương đương với việc sinh metadata**.
- `spring-boot-configuration-processor` nằm trong processor path: phục vụ sinh metadata.

Với các phiên bản Maven Compiler Plugin mới hơn, cách cấu hình processor có thể thay đổi, ví dụ cơ chế dependency type chuyên dụng ở các thế hệ plugin mới. Bài này trình bày cú pháp `annotationProcessorPaths` phổ biến của Maven Compiler Plugin 3.x. Hãy đối chiếu cấu hình tương thích với plugin Maven mà dự án đang dùng.

### Khi nào chọn dependency optional, khi nào chọn explicit processor path?

- Dự án Maven Boot truyền thống, parent/BOM đã quản lý version và annotation processing đang hoạt động: khai báo `optional` thường là bước đơn giản.
- Build muốn xác định chính xác processor nào được compiler gọi: dùng `annotationProcessorPaths`.
- Build có thêm Lombok/MapStruct hoặc processor khác: dùng processor path tường minh, đưa đầy đủ các processor cần thiết vào cấu hình.
- Build dùng JDK/toolchain mà processor discovery bị hạn chế: cấu hình explicit processor path và chạy compile để xác minh.

Không tự xóa annotation processor path đã tồn tại trong POM khi thêm Spring Boot processor. Nếu plugin đã có processor paths, **bổ sung artifact vào danh sách** thay vì thay danh sách bằng một processor duy nhất.

## 11. Gradle và Maven: so sánh nhanh

| Nội dung | Gradle | Maven |
| --- | --- | --- |
| File build thường gặp | `build.gradle` / `build.gradle.kts` | `pom.xml` |
| Khai báo processor cơ bản | `annotationProcessor(...)` | Dependency optional hoặc `annotationProcessorPaths` |
| Lệnh biên dịch | `./gradlew clean classes` | `mvn clean compile` |
| Đầu ra thường gặp | `build/classes/java/main/META-INF/...` | `target/classes/META-INF/...` |
| Nơi quản lý version | Plugin/BOM/platform/version catalog | Parent/BOM/dependency management/property |
| Phân tách build-time/runtime | `annotationProcessor` | Processor path hoặc chính sách dependency và packaging |
| Processor cho module khác | Khai báo ở module chứa class | Khai báo trong module Maven có source đó |
| Có cần khởi động Spring Boot? | Không | Không |

Không nên cho rằng metadata chỉ được tạo nếu gọi `bootRun` hoặc `spring-boot:run`. Cả hai đều không phải cách xác nhận annotation processing đơn giản nhất. Hãy bắt đầu từ tác vụ **compile**.

## 12. Kiểm tra file JSON sau khi build

Với Gradle:

~~~bash
./gradlew clean classes
~~~

Với Maven:

~~~bash
mvn clean compile
~~~

Sau đó kiểm tra vị trí output tương ứng.

Linux/macOS, ví dụ Gradle:

~~~bash
find build -name spring-configuration-metadata.json -print
~~~

Linux/macOS, ví dụ Maven:

~~~bash
find target -name spring-configuration-metadata.json -print
~~~

Trên PowerShell:

~~~powershell
Get-ChildItem -Path .\build -Recurse -Filter spring-configuration-metadata.json
Get-ChildItem -Path .\target -Recurse -Filter spring-configuration-metadata.json
~~~

Chỉ chạy lệnh trên thư mục phù hợp với build tool đang dùng; không nhất thiết dự án có cả `build` lẫn `target`.

Nếu tìm thấy file, có thể mở và kiểm tra các key dự kiến:

~~~json
{
  "name": "app.catalog-client.base-url",
  "type": "java.lang.String"
}
~~~

Metadata thực tế có thể chứa thêm `sourceType`, `description` hoặc các thuộc tính khác. Đừng sửa trực tiếp file được sinh trong `build/` hoặc `target/` vì lần compile tiếp theo có thể ghi lại nó.

### Kiểm tra bên trong JAR

Sau khi đóng gói:

~~~bash
./gradlew bootJar
~~~

hoặc:

~~~bash
mvn package
~~~

Có thể dùng công cụ `jar` của JDK để xem danh sách file trong archive:

~~~bash
jar tf path/to/application.jar
~~~

Với Spring Boot executable JAR, tài nguyên classpath của ứng dụng thường được đặt dưới `BOOT-INF/classes/`, do đó có thể thấy:

~~~text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
~~~

Nhưng metadata cũng có thể nằm trong JAR của một **module thư viện** mà ứng dụng phụ thuộc. Khi đó artifact chứa nguồn `@ConfigurationProperties` mới là nơi tự nhiên để kiểm tra metadata. Không nên mặc định phải tìm đúng một bản metadata ở root của executable JAR.

## 13. IDE sử dụng metadata như thế nào?

Khi IDE hoặc extension Spring hỗ trợ đọc metadata, lập trình viên có thể được hỗ trợ lúc gõ:

~~~yaml
app:
  catalog-client:
    base-url: https://catalog.example.org
~~~

Ví dụ một số hành vi:

- Gợi ý `app.catalog-client.base-url`.
- Gợi ý `connect-timeout` khi đang chỉnh nhóm `app.catalog-client`.
- Hiển thị type `java.time.Duration`.
- Hiển thị mô tả property nếu có metadata thích hợp.
- Cảnh báo một số thuộc tính không biết hoặc cách dùng không phù hợp theo khả năng của công cụ.
- Hỗ trợ gợi ý enum hoặc hints nếu metadata chứa đủ thông tin.

Tuy nhiên, việc có file JSON **không bảo đảm mọi IDE đều có một danh sách gợi ý y hệt**. Kết quả còn tùy phiên bản IDE/plugin, index cache, project import, module dependency và cách công cụ hiểu metadata.

Một quy trình khi không thấy autocomplete:

1. Build lại module có `@ConfigurationProperties`.
2. Xác nhận metadata JSON thực sự tồn tại và chứa key.
3. Refresh/reimport dự án trong IDE.
4. Kiểm tra plugin hỗ trợ Spring/Spring Boot configuration.
5. Xem IDE có nhận dependency giữa module đang sửa YAML và module chứa metadata không.
6. Chỉ sau đó mới điều tra thêm về source class hoặc processor.

Điều quan trọng là **trước tiên kiểm tra output build**, tránh kết luận processor không chạy chỉ vì một IDE tạm thời chưa cập nhật gợi ý.

## 14. Thêm Javadoc để metadata có mô tả hữu ích

Processor có thể sử dụng thông tin từ source code, bao gồm một số Javadoc, để cung cấp mô tả cho thuộc tính cấu hình.

Ví dụ JavaBean:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog-client")
public class ClientProperties {

    /**
     * Địa chỉ gốc của Catalog API.
     */
    private String baseUrl;

    /**
     * Thời gian tối đa để thiết lập kết nối.
     */
    private Duration connectTimeout = Duration.ofSeconds(3);

    /**
     * Số lần thử lại tối đa khi gặp lỗi tạm thời.
     */
    private int maxRetries = 2;

    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Metadata có thể chứa các mô tả tương ứng với từng property nếu processor trích xuất được chúng. Với Java record, Javadoc dành cho record components hoặc phần mô tả tham số cần tuân theo cách mà processor/phiên bản hỗ trợ.

Một số lưu ý:

- Mô tả nên giải thích **ý nghĩa vận hành và đơn vị**, không chỉ lặp lại tên Java field.
- Nếu property là `Duration`, nói rõ đây là thời gian kết nối, đọc response hay chờ shutdown.
- Nếu property là `boolean`, nói rõ trạng thái `true`/`false` có tác dụng gì.
- Nếu có default, mô tả rõ nguồn default và trường hợp áp dụng.
- Không đặt secret hoặc thông tin nội bộ nhạy cảm vào metadata description.

Ví dụ description “Số lần thử lại tối đa khi gặp lỗi tạm thời” hữu ích hơn “maxRetries property”.

## 15. Metadata có tự suy ra default không?

Processor có thể xác định một số giá trị mặc định từ field initializer hoặc thông tin cấu hình mà nó hiểu được, nhưng **không phải mọi default runtime đều có thể suy ra ở thời điểm compile**.

Ví dụ đơn giản:

~~~java
private int maxRetries = 3;
~~~

Processor có thể đưa default `3` vào metadata.

Nhưng một số trường hợp khó hoặc không thể suy ra tĩnh:

~~~java
private Duration timeout = calculateTimeout();
~~~

~~~java
public ClientProperties(Environment environment) {
    this.timeout = environment.getProperty(
            "app.client.timeout", Duration.class, Duration.ofSeconds(5));
}
~~~

Hoặc default phụ thuộc profile, biến môi trường, cấu hình ngoài JAR, bean khác hay logic runtime.

Vì vậy:

- `defaultValue` trong metadata là **thông tin mô tả để hỗ trợ công cụ**.
- Giá trị thực tế vẫn được Binder quyết định theo property sources và các mặc định lúc chạy.
- IDE hiển thị default không có nghĩa đó là giá trị chắc chắn của production.

Nếu metadata không chứa một default mà bạn biết có trong code, không nên vội sửa JSON được sinh; trước hết xác định default đó có nằm trong trường hợp processor có thể phát hiện tĩnh hay không.

## 16. Annotation processor không phải Bean Validation

Giả sử record:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) @Max(32) int threadCount
) {}
~~~

Có ba vai trò riêng:

1. `spring-boot-configuration-processor` sinh metadata cho tooling trong quá trình compile.
2. Spring Boot Binder tạo `WorkerProperties` từ cấu hình khi ứng dụng chạy.
3. Bean Validation kiểm tra `@Min(1)` và `@Max(32)` khi validation được kích hoạt và có provider phù hợp.

Nếu muốn validation chạy, dependency thường dùng là:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Hoặc Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đây là dependency **khác** với `spring-boot-configuration-processor`.

Có processor không đồng nghĩa các constraint `@Min` sẽ tự chạy. Có Bean Validation provider cũng không đồng nghĩa file metadata được sinh. Không dùng một dependency để thay cho dependency còn lại.

## 17. Annotation processor không tự đăng ký `@ConfigurationProperties` bean

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl) {}
~~~

Thêm Gradle dependency:

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

có thể giúp tạo metadata về `app.client.base-url`, nhưng **không tự tạo bean `ClientProperties`**.

Để Spring sử dụng class làm bean cấu hình, cần cơ chế đăng ký thích hợp. Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

Hoặc:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {}
~~~

Cũng có tình huống JavaBean `@ConfigurationProperties` được bind khi bean được tạo bằng `@Bean`, nhưng constructor binding bất biến có những quy tắc riêng. Phần annotation processor không giải quyết thay cho việc lựa chọn kiểu binding và bean registration.

Nếu ứng dụng báo lỗi không tìm thấy bean cấu hình, đừng kết luận “thiếu configuration processor” ngay lập tức. Hãy kiểm tra scan, package, cách đăng ký và constructor binding trước.

## 18. Maven và Lombok: hai processor có thể cần chạy cùng nhau

Nhiều dự án dùng **Lombok** để sinh getter, setter và constructor:

~~~java
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Getter
@Setter
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private String baseUrl;
    private int maxRetries;
}
~~~

Cùng lúc, Spring Boot configuration processor cần quan sát mô hình cấu hình để sinh metadata. Vì Lombok có thể thay đổi cấu trúc class trong quá trình annotation processing, **thứ tự tương tác giữa các processor** có thể ảnh hưởng khả năng phát hiện property.

Ví dụ Maven Compiler Plugin với processor paths được khai báo:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.projectlombok</groupId>
                        <artifactId>lombok</artifactId>
                        <version>${lombok.version}</version>
                    </path>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                        <version>${spring.boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Các property `lombok.version` và `spring.boot.version` phải có giá trị tương thích trong POM/effective build; đây là **mẫu cấu hình**, không phải một POM đầy đủ tự chạy khi thiếu property.

Khi Lombok được dùng, thường cần bảo đảm Lombok được xử lý trước khi configuration processor trích xuất thông tin. Việc liệt kê Lombok trước trong cấu hình là một cách tổ chức thường dùng, nhưng **không nên coi thứ tự text XML là bằng chứng tuyệt đối** rằng mọi Java compiler/plugin đều áp dụng đúng thứ tự mong muốn. Hãy chạy build thực tế và kiểm tra metadata có đủ property do Lombok tạo accessor hay không.

Một cách tránh phụ thuộc vào cơ chế sinh getter/setter phức tạp là dùng **Java record** cho các nhóm cấu hình chỉ có dữ liệu:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        int maxRetries
) {}
~~~

Record thường dễ đọc và cung cấp thông tin component rõ ràng cho processor hơn việc phụ thuộc vào một loạt annotation code generation.

## 19. Gradle và Lombok: dependencies nên được khai báo riêng

Với Gradle Groovy DSL:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    compileOnly("org.projectlombok:lombok")
    annotationProcessor("org.projectlombok:lombok")

    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Ở đây:

- `compileOnly` cho phép Java source sử dụng các annotation của Lombok khi biên dịch.
- `annotationProcessor 'lombok'` cho phép Lombok xử lý annotation.
- `annotationProcessor 'spring-boot-configuration-processor'` cho phép Spring Boot tạo metadata.

Nếu Gradle chưa quản lý version Lombok qua BOM hoặc configuration khác, cần bổ sung version phù hợp. Đừng copy mù ba dòng vào một dự án đã dùng Lombok plugin hoặc convention plugin có sẵn, vì nó có thể đã thiết lập các processor path.

Khi metadata thiếu property từ class có Lombok:

1. Xác nhận Lombok hoạt động và code biên dịch đúng.
2. Xác nhận Spring processor có mặt trên compile annotation processor path.
3. Chạy clean compile để loại bỏ kết quả cũ.
4. Đọc JSON thực tế và so sánh các key kỳ vọng.
5. Nếu cần, thay đổi cách khai báo Lombok/processor theo cấu hình được khuyến nghị cho phiên bản build tool.
6. Cân nhắc chuyển các class cấu hình đơn giản sang record hoặc getter/setter tường minh.

## 20. Không nên dùng `-parameters` để thay thế processor

Một số dự án phải giữ tên constructor parameters để hỗ trợ constructor binding của `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        String baseUrl,
        int maxConnections
) {}
~~~

Với Java class thông thường, compiler flag:

~~~text
-parameters
~~~

có thể giúp lưu tên tham số constructor trong bytecode để Binder xác định tên property.

Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Nhưng:

- `-parameters` giúp **giữ tên tham số cho reflection/binding** khi cần.
- `spring-boot-configuration-processor` giúp **tạo JSON metadata cho IDE**.
- Hai cơ chế không thay thế nhau.

Một dự án có thể bind constructor đúng nhưng không có metadata vì thiếu processor. Một dự án cũng có thể sinh metadata nhưng gặp lỗi binding vì thiếu tên tham số hoặc sai registration/constructor.

## 21. Dự án Maven không dùng Spring Boot parent

Có dự án không kế thừa `spring-boot-starter-parent` mà sử dụng BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring.boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi đó, cần cung cấp `spring.boot.version` trong phần `properties` hoặc từ cấu hình build phù hợp, và cần bảo đảm các plugin Maven có version/tùy chỉnh phù hợp vì BOM **quản lý dependency** nhưng không hoàn toàn thay cho parent trong việc quản lý plugin.

Với khai báo dependency thông thường:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

dependency management có thể cấp version cho artifact.

Nhưng với `maven-compiler-plugin` và `annotationProcessorPaths`, việc suy luận version từ dependencyManagement phụ thuộc phiên bản Maven Compiler Plugin và cơ chế resolve tương ứng. Để cách ví dụ hoạt động rõ ràng trên plugin 3.x, khai báo version tường minh trong processor path qua một property đã định nghĩa là lựa chọn dễ hiểu:

~~~xml
<path>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <version>${spring.boot.version}</version>
</path>
~~~

Không hardcode processor version lệch với BOM chỉ vì một bài hướng dẫn cũ dùng version khác.

## 22. Dự án Gradle nhiều module: khai báo ở đúng module

Giả sử dự án:

~~~text
settings.gradle
build.gradle
config-model/
  build.gradle
  src/main/java/.../ClientProperties.java
application/
  build.gradle
  src/main/java/.../DemoApplication.java
~~~

Nếu `ClientProperties` nằm trong module `config-model`, processor cần được cấu hình cho task compile của **module đó**.

Ví dụ `config-model/build.gradle`:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.springframework.boot:spring-boot'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Đây là một cấu hình minh họa. Module thực tế cần cơ chế version management phù hợp; nếu không có BOM/platform, dependency `spring-boot` và processor cần version cụ thể.

Module application:

~~~groovy
dependencies {
    implementation project(':config-model')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Nếu chỉ đặt `annotationProcessor` ở module `application` nhưng các class `@ConfigurationProperties` cần xử lý nằm trong `config-model`, metadata có thể không xuất hiện trong artifact của module nguồn.

Quy tắc:

> Processor cần tham gia **compilation nơi source code mang `@ConfigurationProperties` được biên dịch**.

Với Maven multi-module cũng vậy: đưa dependency/processor path vào module có class cấu hình, hoặc cấu hình được kế thừa thích hợp trong parent POM của các module liên quan.

## 23. Metadata trong thư viện dùng lại cho nhiều ứng dụng

Một thư viện tự viết starter hoặc module chung có thể cung cấp:

~~~java
@ConfigurationProperties(prefix = "acme.payment")
public record PaymentProperties(
        String endpoint,
        int maxRetries
) {}
~~~

Nếu thư viện sinh metadata trong JAR của chính nó, IDE của những ứng dụng phụ thuộc có thể đọc metadata này, tùy khả năng của IDE và cách dependency được import.

Đây là một lợi ích quan trọng: **metadata không chỉ hữu ích trong ứng dụng cuối** mà còn giúp các thư viện cấu hình tùy biến dễ sử dụng.

Cần phân biệt:

- Metadata mô tả `acme.payment.endpoint` và `acme.payment.max-retries`.
- Auto-configuration hoặc một cơ chế đăng ký bean phù hợp mới thực sự tạo/điều kiện hóa bean ở runtime.
- Việc đóng gói metadata trong thư viện không tự làm thư viện trở thành Spring Boot starter hoàn chỉnh.
- Một property có metadata không đồng nghĩa nó luôn hoạt động trong mọi ứng dụng; runtime có thể phụ thuộc bean/auto-configuration hoặc điều kiện riêng.

Với thư viện công khai, mô tả và hints trong metadata nên được xem như một phần trải nghiệm API cấu hình.

## 24. `additional-spring-configuration-metadata.json` để bổ sung thông tin

Có những thông tin mà processor không thể tự suy ra đầy đủ, ví dụ một property có giá trị hợp lệ thuộc danh sách tên được xác định ngoài source hoặc muốn cung cấp mô tả/hints bổ sung.

Spring Boot hỗ trợ file bổ sung:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "app.catalog-client.base-url",
      "type": "java.lang.String",
      "description": "URL gốc dùng để gọi dịch vụ Catalog."
    }
  ],
  "hints": [
    {
      "name": "app.catalog-client.mode",
      "values": [
        {
          "value": "sandbox",
          "description": "Sử dụng môi trường thử nghiệm."
        },
        {
          "value": "production",
          "description": "Sử dụng môi trường thật."
        }
      ]
    }
  ]
}
~~~

Vai trò:

- `spring-configuration-metadata.json` thường là **file sinh tự động** trong output build.
- `additional-spring-configuration-metadata.json` là **file source** do dự án quản lý, dùng để thêm hoặc điều chỉnh thông tin metadata theo định dạng Spring Boot hỗ trợ.
- Khi build được cấu hình phù hợp, metadata bổ sung có thể được kết hợp với metadata sinh ra để IDE sử dụng.

Không sửa trực tiếp file sinh trong `build/classes` hoặc `target/classes`. Nếu muốn thêm mô tả, dùng Javadoc và/hoặc additional metadata đúng nơi.

### Lưu ý Gradle về thứ tự task

Ở một số cấu hình Gradle, task compile Java và task xử lý resources có thứ tự ảnh hưởng đến thời điểm processor nhìn thấy file additional metadata. Nếu cần **merge** additional metadata vào JSON sinh tự động tại compile time, hãy bảo đảm task chuẩn bị file additional metadata đã hoàn tất trước khi processor thực thi.

Không nên tự ý sửa task graph toàn dự án nếu chưa có dấu hiệu lỗi. Trước tiên kiểm tra JSON đầu ra và tài liệu tương ứng với phiên bản Gradle/Spring Boot đang dùng.

## 25. Metadata khác với `spring.factories` và auto-configuration imports

Tên file trong thư mục `META-INF` có thể làm người mới nhầm lẫn:

~~~text
META-INF/spring-configuration-metadata.json
META-INF/additional-spring-configuration-metadata.json
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Chúng không có cùng chức năng.

- **Configuration metadata JSON:** giúp IDE/tooling hiểu property.
- **Additional configuration metadata JSON:** bổ sung thông tin metadata.
- **`spring.factories`:** một cơ chế đăng ký factory/extension lịch sử trong hệ sinh thái Spring, với mục đích khác metadata.
- **`AutoConfiguration.imports`:** tài nguyên dùng để liệt kê auto-configuration trong các phiên bản Spring Boot liên quan.

Không cố đưa class `@ConfigurationProperties` vào `spring-configuration-metadata.json` bằng tay rồi kỳ vọng Spring Boot tự tạo bean. File này không phải danh sách bean registration.

Nếu bạn xây dựng starter, cần hiểu rõ phần **công bố metadata cho IDE** và phần **auto-configure runtime** là hai việc độc lập nhưng bổ sung cho nhau.

## 26. Khi nào processor không tạo được đủ metadata?

Một số tình huống điển hình:

1. Class không có `@ConfigurationProperties` hoặc annotation không nằm ở nơi processor hỗ trợ.
2. Source code chứa property theo cách động khiến processor không xác định được schema tĩnh.
3. Class dùng JavaBean binding nhưng thiếu thông tin accessor thích hợp.
4. Class dùng Lombok nhưng annotation processing hoặc thứ tự processor chưa hoạt động đúng.
5. Annotation processor chỉ được thêm vào module khác, không phải module chứa source.
6. Build chỉ chạy task không biên dịch module đã thay đổi.
7. Build cache hoặc output cũ chưa được cập nhật.
8. Compiler plugin tắt annotation processing bằng lựa chọn như `-proc:none`.
9. Version của processor, Boot và toolchain không tương thích.
10. IDE chưa tải lại module hoặc chưa index file metadata đã sinh.

Với constructor binding, record, nested class, map/list và các generic type phức tạp, khả năng mô tả của processor cũng phụ thuộc cách loại hình Java đó được phát hiện và giới hạn hỗ trợ theo phiên bản.

Không cần có tất cả mọi property trong metadata để Binder chạy được. Nếu một property thiếu, xác định nó có phải thành phần tĩnh có thể phân tích được không trước khi coi đây là lỗi build.

## 27. Phân biệt compiler processor với runtime property source

Cách công cụ biên dịch nhận metadata:

~~~text
Java source @ConfigurationProperties
             │
             ▼
Annotation processor
             │
             ▼
spring-configuration-metadata.json
~~~

Cách ứng dụng chạy nhận giá trị:

~~~text
application.yml + env + CLI + ...
               │
               ▼
Environment / Config Data
               │
               ▼
ConfigurationProperties Binder
               │
               ▼
ClientProperties instance
~~~

Hai đường đi có thể có cùng class `ClientProperties` nhưng mục đích hoàn toàn khác.

Ví dụ cấu hình:

~~~yaml
app:
  catalog-client:
    connect-timeout: 5s
~~~

Metadata có thể nói property `connect-timeout` mang type `Duration` và mô tả “thời gian thiết lập kết nối”, nhưng khi chạy ứng dụng có thể nhận `connect-timeout=2s` từ environment variable ưu tiên cao hơn.

Metadata **không lưu runtime effective value** và cũng không xác định profile đang hoạt động. Nó chủ yếu cung cấp schema/tài liệu tĩnh cho công cụ.

## 28. Cách chẩn đoán theo thứ tự để tránh sửa build mù

Khi IDE không gợi ý custom property, làm theo từng bước.

### Bước 1 — Kiểm tra class nguồn

Đảm bảo annotation đúng:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl) {}
~~~

Không nhầm với:

~~~java
@Value("${app.client.base-url}")
private String baseUrl;
~~~

Configuration processor chủ yếu xử lý mô hình `@ConfigurationProperties`, không tự tạo metadata đầy đủ cho những biến `@Value` phân tán ở khắp code.

### Bước 2 — Kiểm tra Gradle/Maven khai báo processor

Gradle:

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Hoặc explicit processor path nếu build dùng cơ chế đó.

### Bước 3 — Biên dịch sạch

~~~bash
./gradlew clean classes
~~~

hoặc:

~~~bash
mvn clean compile
~~~

### Bước 4 — Kiểm tra file JSON

Tìm:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Mở file và kiểm tra xem property `app.client.base-url` có xuất hiện không.

### Bước 5 — Phân biệt processor không chạy và processor chạy nhưng thiếu field

- **Không có JSON**: xem lại processor path, task compile, Java toolchain, annotation processing bị tắt hoặc source set.
- **Có JSON nhưng thiếu property**: xem lại cấu trúc class, accessor, record component, Lombok, nested type hoặc giới hạn suy luận.
- **JSON đủ property nhưng IDE không gợi ý**: refresh IDE, plugin hỗ trợ metadata, indexing và module dependencies.
- **IDE gợi ý được nhưng runtime không bind**: kiểm tra bean registration, prefix, property source precedence và kiểu Java. Đây không còn là vấn đề metadata.

### Bước 6 — Không sửa nguồn ngoài phạm vi cần thiết

Trong một dự án lớn, không nên thay cả hệ thống plugin/bom chỉ vì một property không được IDE gợi ý. Ưu tiên thay đổi nhỏ, kiểm tra build rồi xác nhận output.

## 29. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Gradle build thành công nhưng không có JSON | Thiếu `annotationProcessor` | Thêm processor vào đúng module |
| Có `implementation` nhưng processor không chạy | Processor không ở annotation processor path | Sử dụng `annotationProcessor` |
| Maven có dependency optional nhưng không có JSON | Annotation processing bị tắt/giới hạn, hoặc compiler chưa nạp processor | Cấu hình explicit processor path và kiểm tra compile |
| Maven compiler có processor paths nhưng thiếu metadata | Chưa thêm Spring processor vào danh sách paths | Bổ sung artifact thay vì thay toàn bộ danh sách |
| Sau khi bật Lombok, metadata thiếu trường | Processor không quan sát được accessor/constructor sau Lombok | Kiểm tra cấu hình cả hai processors và compile sạch |
| Metadata chỉ có trong module library | Processor chạy nơi class được biên dịch | Kiểm tra artifact/module tương ứng |
| File JSON tồn tại nhưng IDE chưa gợi ý | IDE chưa index/reimport module | Reload/refresh và kiểm tra plugin IDE |
| Metadata có key nhưng runtime báo thiếu bean | Chưa scan/enable configuration properties | Dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Property có type nhưng không có description | Processor không thu được Javadoc/hints | Bổ sung Javadoc hoặc additional metadata |
| Không thấy defaultValue trong JSON | Default phụ thuộc runtime hoặc processor không suy luận được | Không sửa file generated trực tiếp; xem lại cách mô tả default |
| Dùng `@Value` nhưng không sinh metadata | Không phải mô hình `@ConfigurationProperties` cần processor mô tả | Gom cấu hình vào type `@ConfigurationProperties` khi phù hợp |
| Thêm `-parameters` nhưng vẫn không có JSON | `-parameters` không kích hoạt configuration processor | Khai báo processor riêng |
| JAR chứa processor như dependency chạy | Dependency scope/configuration chưa phù hợp | Đặt trên processor path riêng |
| Processor version lệch Spring Boot | Version bị hardcode hoặc BOM/parent không quản lý đúng | Đồng bộ phiên bản với Boot của dự án |
| JSON trong `build/` sửa rồi bị mất | File là build output | Sửa source/Javadoc/additional metadata rồi build lại |

## 30. Một bài thử nhỏ với Gradle

Giả sử ứng dụng chỉ có:

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.retry")
public record RetryProperties(
        int maxAttempts,
        Duration backoff
) {}
~~~

`build.gradle` cần dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Chạy:

~~~bash
./gradlew clean classes
~~~

Kiểm tra output:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Trong `properties`, mong đợi các tên như:

~~~text
demo.retry.max-attempts
demo.retry.backoff
~~~

Có thể kiểm tra bằng IDE, terminal hoặc một chương trình nhỏ đọc JSON. Không cần start ứng dụng chỉ để quan sát những key này.

Thử đổi một tên record component, ví dụ `maxAttempts` thành `attemptLimit`, rồi compile lại. Nếu processor chạy và IDE đã refresh, metadata mới có thể mô tả:

~~~text
demo.retry.attempt-limit
~~~

Đây là cách minh họa rằng metadata xuất phát từ **schema Java tại compile time**, không phải từ tập các key tình cờ xuất hiện trong YAML runtime.

## 31. Một bài thử nhỏ với Maven

Cùng record `RetryProperties` ở trên, thêm trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Nếu build sử dụng processor path tường minh, hãy bảo đảm Spring processor được liệt kê trong `annotationProcessorPaths`.

Chạy:

~~~bash
mvn clean compile
~~~

Kiểm tra:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Khi metadata có hai property `demo.retry.max-attempts` và `demo.retry.backoff`, bước biên dịch metadata đã hoạt động cho class đó.

Nếu file không xuất hiện, đừng kết luận rằng runtime binding sai. Hãy xem lại **effective POM**, Java compiler plugin, trạng thái annotation processing và việc class có thực sự được compile trong module hiện tại không.

Một số Java toolchain mới yêu cầu cấu hình processor tường minh thay vì dựa vào classpath scanning, nên explicit processor path là lựa chọn đáng cân nhắc khi cấu hình cũ không hoạt động.

## 32. Bài tập thực hành

### Bài 1 — Chọn Gradle configuration

Dự án `build.gradle` hiện chỉ có:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter'
~~~

Hãy thêm một dependency để sinh metadata cấu hình.

**Đáp án:**

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

Chọn `annotationProcessor` vì artifact cần được compiler gọi tại thời điểm build, không phải thư viện runtime của ứng dụng.

### Bài 2 — Kotlin DSL

Viết khai báo tương đương trong `build.gradle.kts`.

**Đáp án:**

~~~kotlin
annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
~~~

### Bài 3 — Maven dependency

Một dự án Spring Boot dùng parent/BOM đã quản lý version. Viết cấu hình dependency cơ bản.

**Đáp án:**

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Nếu build dùng explicit processor paths hoặc không tự phát hiện processor, cần cấu hình tương ứng tại compiler plugin.

### Bài 4 — Phân biệt processor và Binder

Ứng dụng có `@ConfigurationPropertiesScan`, bind đúng `app.client.base-url` nhưng IDE không autocomplete. Thêm processor có mục đích gì?

**Đáp án:** bổ sung metadata cho công cụ phát triển. Processor không phải thành phần bắt buộc để runtime Binder liên kết property, và không thay thế bean registration.

### Bài 5 — Kiểm tra file sinh

Sau khi chạy `mvn clean compile`, tìm file JSON ở đâu?

**Đáp án:** thông thường `target/classes/META-INF/spring-configuration-metadata.json`. Với Gradle Java compile, thường là `build/classes/java/main/META-INF/spring-configuration-metadata.json`. Trong môi trường build khác, tìm file theo tên trong compilation output.

### Bài 6 — Dependency optional có nghĩa gì?

`<optional>true</optional>` trong POM có nghĩa processor chắc chắn sẽ không nằm trong mọi artifact runtime và chắc chắn được compiler gọi không?

**Đáp án:** không. `optional` chủ yếu điều khiển tính transitive của Maven dependency. Cách compiler phát hiện processor và cách đóng gói artifact còn phụ thuộc plugin/build. Muốn chủ động phân tách processor path, dùng cấu hình compiler phù hợp.

### Bài 7 — Lombok và processor

Class `@ConfigurationProperties` dùng Lombok để sinh getter/setter, Gradle chỉ khai báo `compileOnly lombok`. Điều gì còn thiếu?

**Đáp án gợi ý:** cần Lombok trên `annotationProcessor` để nó thực thi; đồng thời cần Spring Boot configuration processor nếu muốn metadata. Nếu metadata vẫn thiếu trường, kiểm tra sự tương tác và thứ tự của các processor trong build thực tế.

### Bài 8 — Nhiều module

`ClientProperties` ở module `config-model`, `main()` ở module `application`. Chỉ khai báo Spring processor tại module `application` có chắc tạo metadata trong JAR `config-model` không?

**Đáp án:** không. Processor cần tham gia compilation của module chứa source mang annotation, tức `config-model`. Việc đặt processor chỉ ở ứng dụng cuối không tự sinh lại metadata cho source đã được biên dịch ở thư viện khác.

### Bài 9 — File metadata khác runtime config

`spring-configuration-metadata.json` có entry `app.worker.thread-count`, nhưng biến môi trường đặt `APP_WORKER_THREADCOUNT=10`. Runtime chọn gì?

**Đáp án:** metadata chỉ mô tả tên và kiểu property. Giá trị runtime do Binder/PropertySource precedence quyết định. Nếu biến môi trường là nguồn hiệu lực và chuyển kiểu hợp lệ, `thread-count` có thể là 10; metadata không khóa cứng giá trị.

### Bài 10 — Cần mô tả/hints bổ sung

Processor tạo tên `app.client.mode` nhưng IDE không gợi ý các lựa chọn `sandbox` và `production`. Có thể bổ sung bằng cách nào?

**Đáp án:** dùng cơ chế metadata hints trong `additional-spring-configuration-metadata.json` hoặc mô hình type phù hợp như enum, sau đó biên dịch lại và kiểm tra metadata/IDE. Không chỉnh sửa trực tiếp JSON được sinh trong build output.

## 33. Checklist áp dụng vào dự án

Trước khi đánh dấu việc cấu hình metadata hoàn tất, kiểm tra:

1. Có class/record `@ConfigurationProperties` rõ ràng, prefix canonical hợp lệ.
2. Xác định **module thực sự biên dịch** class cấu hình.
3. Với Gradle Java, thêm `spring-boot-configuration-processor` vào `annotationProcessor`.
4. Với Maven, khai báo processor qua dependency optional hoặc processor path phù hợp với compiler plugin/toolchain.
5. Đồng bộ version processor với phiên bản Spring Boot mà dự án đang dùng.
6. Nếu dùng Lombok/MapStruct, kiểm tra tất cả processors cần thiết và sự tương tác giữa chúng.
7. Chạy clean compile.
8. Tìm `META-INF/spring-configuration-metadata.json` trong output của module.
9. Kiểm tra ít nhất một tên property tự định nghĩa có mặt trong JSON.
10. Nếu thiếu mô tả hoặc hints, thêm Javadoc hoặc additional metadata thích hợp.
11. Reimport/refresh IDE khi file JSON đã có nhưng autocomplete chưa cập nhật.
12. Kiểm tra runtime bean được đăng ký riêng, không đánh đồng metadata với binder/validation/auto-configuration.
13. Không đưa dữ liệu nhạy cảm vào metadata description hoặc literal defaults không cần thiết.
14. Với module thư viện, xác minh metadata được đóng gói vào artifact của chính module đó.
15. Dùng cùng quy trình trên CI để phát hiện build không tạo metadata như dự kiến.

Checklist trên là các bước kỹ thuật để quản lý công cụ build; nó không có nghĩa mọi class cấu hình phải sinh cùng một số lượng property hay mọi IDE phải hiển thị cùng một giao diện.

## 34. Ghi nhớ

- `spring-boot-configuration-processor` là **annotation processor chạy khi biên dịch**, không phải Spring Boot Binder runtime.
- Artifact chuẩn: `org.springframework.boot:spring-boot-configuration-processor`.
- File sinh: **`META-INF/spring-configuration-metadata.json`**.
- **Gradle Groovy DSL:** `annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'`.
- **Gradle Kotlin DSL:** `annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")`.
- **Maven:** thường khai báo dependency với `<optional>true</optional>`; có thể chỉ định bằng `maven-compiler-plugin`/`annotationProcessorPaths` để kiểm soát compiler processor path.
- `optional` của Maven không đồng nghĩa bảo đảm processor chạy hoặc chắc chắn bị loại khỏi mọi runtime artifact.
- **Đặt processor ở module chứa class `@ConfigurationProperties`**, nhất là với multi-module.
- Nếu có **Lombok**, cấu hình cả Lombok processor và Spring Boot processor, sau đó xác minh metadata thực tế.
- `-parameters` phục vụ việc giữ tên constructor parameters; nó không thay cho annotation processor.
- Metadata giúp IDE completion, mô tả và hints; **không tự đăng ký bean**, không bật Bean Validation, không quyết định runtime property values.
- Với mô tả/hints bổ sung, dùng `additional-spring-configuration-metadata.json` và **không sửa file được sinh trong `build/` hoặc `target/`**.
- Cách kiểm chứng chắc chắn nhất là **compile rồi đọc JSON**, sau đó mới kiểm tra trải nghiệm IDE.

## Tài liệu tham khảo

- [Spring Boot Reference — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot Reference — Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Gradle User Manual — Annotation Processing](https://docs.gradle.org/current/userguide/java_plugin.html#sec:java_compile_avoidance)
- [Apache Maven Compiler Plugin — Annotation Processor Paths](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
