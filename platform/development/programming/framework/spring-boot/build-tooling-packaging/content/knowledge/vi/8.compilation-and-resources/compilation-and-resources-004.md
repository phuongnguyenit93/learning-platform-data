# Sinh metadata cấu hình bằng spring-boot-configuration-processor

## 1. Mục tiêu bài học

Khi một dự án Spring Boot có các cấu hình tự định nghĩa như `demo.client.timeout` hoặc `demo.client.retry.max-attempts`, IDE sẽ hỗ trợ người lập trình tốt hơn nếu biết **tên khóa, kiểu dữ liệu, mô tả, giá trị gợi ý và trạng thái deprecated** của chúng. Spring Boot cung cấp **`spring-boot-configuration-processor`** để sinh thông tin này từ mã nguồn Java trong lúc biên dịch.

Sau bài này, bạn có thể:

- Giải thích annotation processor khác với cơ chế **bind giá trị khi ứng dụng chạy**.
- Cấu hình `spring-boot-configuration-processor` cho Maven và Gradle theo cách phù hợp với Java hiện đại.
- Viết lớp `@ConfigurationProperties` mà processor đọc được, gồm JavaBean và Java `record`.
- Xác định nội dung và vị trí file **`META-INF/spring-configuration-metadata.json`** được sinh.
- Sử dụng Javadoc để tạo mô tả, nhận biết thuộc tính lồng nhau, kiểu dữ liệu và giá trị mặc định.
- Bổ sung **`META-INF/additional-spring-configuration-metadata.json`** cho những thông tin processor không suy ra được.
- Kiểm tra metadata bằng lệnh build và nội dung artifact; chẩn đoán lỗi thiếu gợi ý cấu hình trong IDE.

**Phạm vi:** Spring Boot 3.5.x, Java 17+; các tên artifact và đường dẫn chính bên dưới cũng được dùng ở những dòng Spring Boot gần đây, nhưng cấu hình compiler/plugin phải đối chiếu với dòng thực tế. Những ví dụ hoàn chỉnh trong bài dùng **Spring Boot 3.5.16** để có tọa độ Maven rõ ràng, không ngụ ý mọi dự án bắt buộc dùng phiên bản này.

## 2. Metadata cấu hình là gì và để làm gì?

**Configuration metadata** là tài liệu máy đọc được, thường là JSON, mô tả các khóa cấu hình của một thư viện hoặc ứng dụng. Spring Boot và một số IDE hiểu định dạng này để hiện completion, kiểu dữ liệu, tooltip mô tả, gợi ý giá trị và cảnh báo khi dùng thuộc tính không còn khuyến nghị.

Ví dụ một ứng dụng tự định nghĩa:

~~~properties
demo.client.name=inventory
demo.client.timeout=5s
demo.client.retry.max-attempts=4
~~~

Một IDE hỗ trợ Spring Boot metadata có thể gợi ý các khóa `demo.client.*` trong `application.properties` hoặc `application.yml`, vì project có file metadata công bố khóa và kiểu. Việc IDE hiện gợi ý còn phụ thuộc extension/plugin, project import và cache của IDE; metadata tồn tại không có nghĩa mọi trình soạn thảo đều có trải nghiệm giống nhau.

### 2.1. Ba thành phần phải phân biệt

| Thành phần | Diễn ra ở đâu? | Làm gì? |
| --- | --- | --- |
| `@ConfigurationProperties` và Spring Boot Binder | Chủ yếu lúc Spring ApplicationContext khởi tạo/chạy | Đọc `Environment` và bind giá trị vào object cấu hình |
| `spring-boot-configuration-processor` | **Lúc Java compile** | Phân tích source declarations/annotations và sinh JSON metadata |
| IDE hoặc công cụ tiêu thụ metadata | Khi viết, kiểm tra, khám phá cấu hình | Dùng JSON để autocomplete, hiển thị mô tả/hints |

**Processor không tự tạo Spring bean, không tự bind giá trị, không nạp `application.properties` vào ứng dụng và không thực hiện validation.** Ứng dụng vẫn cần đăng ký `@ConfigurationProperties` qua `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc một cơ chế bean phù hợp. Nếu cần kiểm tra dữ liệu khi chạy, sử dụng Bean Validation/validator và cấu hình binding riêng.

Không nên xem metadata là một tệp cấu hình cần deploy để Spring Boot hoạt động: ứng dụng có thể bind và chạy khi metadata không được sinh, nhưng IDE và người tiêu thụ tài liệu cấu hình sẽ thiếu thông tin hỗ trợ.

## 3. Luồng xử lý khi biên dịch

~~~text
Java source:
  @ConfigurationProperties(prefix = "demo.client")
  class DemoClientProperties { ... }
                 |
                 | javac / Maven Compiler / Gradle JavaCompile
                 v
Spring Boot configuration annotation processor
  - nhận diện classes / factory methods có annotation
  - đọc getters/setters hoặc constructor components
  - suy ra tên khóa, kiểu dữ liệu, mô tả từ Javadoc
  - cố suy ra một số default values
                 |
                 | có thể merge metadata khai báo thủ công
                 v
META-INF/spring-configuration-metadata.json
                 |
                 | nằm trong output classes và artifact JAR
                 v
IDE / thư viện đọc metadata phục vụ completion và tài liệu
~~~

Processor thuộc cơ chế **Java annotation processing**. Với Maven, compiler plugin gọi processor lúc phase `compile`; với Gradle, task `compileJava` thực thi nó khi đã khai báo trên `annotationProcessor` path. **Đừng nhầm processor này với Spring AOT processor hoặc GraalVM native-image config**: đó là các cơ chế khác và có đầu ra khác.

Các thông tin có thể xuất hiện trong metadata gồm:

- **`groups`**: nhóm cấu hình, thường xuất phát từ prefix.
- **`properties`**: khóa đầy đủ, kiểu dữ liệu, mô tả, nguồn khai báo, default và deprecated nếu suy ra được.
- **`hints`**: gợi ý danh sách giá trị hoặc provider hỗ trợ IDE.
- **`ignored`**: những mục được loại khỏi metadata theo khai báo bổ sung.

Tên file chính thức được các công cụ tìm kiếm trong classpath là **`META-INF/spring-configuration-metadata.json`**.

## 4. Cấu hình processor bằng Maven

### 4.1. Tại sao nên dùng annotationProcessorPaths?

Trước đây có những project khai báo `spring-boot-configuration-processor` như dependency thông thường với `<optional>true</optional>`. Cách này phụ thuộc cơ chế tìm processor trên classpath của compiler/JDK và không phải cấu hình rõ ràng nhất ở Java mới. **Từ JDK 23, javac không tự quét classpath để chạy annotation processors nếu build chưa cho phép một cách tường minh.** Vì vậy hãy cấu hình processor trên **annotation processor path** hoặc cơ chế khai báo processor được compiler plugin hỗ trợ, thay vì chỉ hy vọng nó chạy nhờ dependency thông thường.

Theo tài liệu Spring Boot 3.5, với Maven nên dùng **Maven Compiler Plugin 3.12.0 trở lên** và khai báo processor:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                        <version>3.5.16</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đoạn này thuộc **`pom.xml`**, không phải file POM độc lập. Nếu parent POM hoặc BOM đã quản lý version cho processor/plugin theo cơ chế build hiện hành, bạn có thể dùng version được quản lý và kiểm tra effective POM; việc pin cả hai version trong ví dụ giúp lệnh có thể giải quyết artifact trong project minh họa.

**Lưu ý khi dự án có parent Maven riêng:** BOM `spring-boot-dependencies` quản lý dependencies, nhưng import BOM **không tự import Maven plugin management của `spring-boot-starter-parent`**. Kiểm tra cấu hình Maven Compiler Plugin và `spring-boot-maven-plugin` của parent riêng để tránh bỏ sót hoặc ghi trùng cấu hình.

### 4.2. Không biến processor thành runtime dependency

Processor dành cho **build time**. Khi đặt nó trong `annotationProcessorPaths`, bạn không cần khai báo thêm processor là `compile` hoặc `runtime` dependency của ứng dụng chỉ để sinh metadata. Việc có file JSON trong JAR là kết quả build, không đòi hỏi processor phải nằm trên runtime classpath.

Nếu một project Maven cũ vẫn dùng dependency optional, cần xem Java version và compiler plugin cụ thể; với JDK mới, **chỉ thêm optional dependency mà không bật annotation processing có thể khiến JSON không xuất hiện**.

## 5. Cấu hình processor bằng Gradle

### 5.1. Gradle Groovy DSL

Trong project Gradle dùng Spring Boot và Java, khai báo processor ở configuration **`annotationProcessor`** của module chứa `@ConfigurationProperties`:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.5.16'
}
~~~

Nếu project đã có dependency management quản lý version cho configuration này, có thể không cần pin `:3.5.16`, nhưng phải kiểm tra dependency resolution thật. Ví dụ pin tường minh vì chỉ yêu cầu đúng processor cho Spring Boot 3.5.16.

### 5.2. Gradle Kotlin DSL

Với `build.gradle.kts`:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor:3.5.16")
}
~~~

`annotationProcessor` **khác** `implementation` và `runtimeOnly`. Đưa processor vào `implementation` đơn thuần không bảo đảm Gradle gọi nó khi biên dịch. Trong build đa module, khai báo processor ở **module biên dịch lớp cấu hình**, không chỉ ở module chạy ứng dụng.

### 5.3. Khi có additional-spring-configuration-metadata.json

Nếu có file metadata bổ sung trong `src/main/resources/META-INF/`, tài liệu Spring Boot đề xuất để task `compileJava` phụ thuộc vào kết quả `processResources`, giúp processor nhìn thấy metadata bổ sung khi xử lý source.

Gradle Groovy DSL:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

Gradle Kotlin DSL:

~~~kotlin
tasks.named("compileJava") {
    inputs.files(tasks.named("processResources"))
}
~~~

Điểm cần hiểu là **thứ tự và dependency dữ liệu của build tasks**: file bổ sung phải có sẵn cho processor tại thời điểm biên dịch. Nếu không dùng additional metadata, không nhất thiết thêm task configuration này. Trong project có convention plugins hoặc task graph đặc biệt, xác minh không tạo vòng phụ thuộc build tasks.

Lệnh kiểm tra:

~~~bash
./gradlew clean compileJava
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean compileJava
~~~

Output thường nằm tại `build/classes/java/main/META-INF/spring-configuration-metadata.json`; khi đóng gói, kiểm tra đường dẫn trong artifact thực tế. Nếu project dùng Kotlin hoặc annotation processing khác, cần xét thêm cấu hình toolchain/plugin riêng thay vì sao chép nguyên một lệnh dành cho Java.

## 6. Ví dụ Maven đầy đủ: sinh metadata từ JavaBean

### 6.1. Cấu trúc

Tạo project Spring Initializr: **Java**, **Maven**, **Spring Boot 3.5.16**, **Java 17**, packaging **JAR**. Ví dụ dưới dùng `spring-boot-starter`, không yêu cầu Spring Web hay database.

~~~text
metadata-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/
└── src/
    └── main/
        ├── java/com/example/metadatademo/
        │   ├── MetadataDemoApplication.java
        │   └── DemoClientProperties.java
        └── resources/
            ├── application.properties
            └── META-INF/
                └── additional-spring-configuration-metadata.json
~~~

File additional ở đây sẽ được thêm trong mục 9. Nếu chưa cần thông tin bổ sung, **không tạo file đó** ở bước đầu; processor vẫn có thể sinh metadata từ Java source.

### 6.2. File pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>metadata-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>3.5.16</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ dùng Boot starter parent để nhận dependency management và executable packaging thông thường. Nếu thực hành trong repository đã có parent riêng, không đặt parent thứ hai; chỉ lấy phần compiler processor phù hợp với POM hiện tại, đồng thời quản lý versions/plugins qua parent hoặc module.

### 6.3. File DemoClientProperties.java

Tạo `src/main/java/com/example/metadatademo/DemoClientProperties.java`:

~~~java
package com.example.metadatademo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Cấu hình kết nối đến dịch vụ khách hàng.
 */
@ConfigurationProperties(prefix = "demo.client")
public class DemoClientProperties {

    /** Tên hiển thị của client. */
    private String name = "local-client";

    /** Thời gian chờ phản hồi từ dịch vụ. */
    private Duration timeout = Duration.ofSeconds(2);

    /** Quy tắc retry khi gọi dịch vụ. */
    private Retry retry = new Retry();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public static class Retry {

        /** Số lần thử tối đa. */
        private int maxAttempts = 3;

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }
    }
}
~~~

Các điểm quan trọng:

- `@ConfigurationProperties(prefix = "demo.client")` mô tả prefix cho binder và processor.
- **Getters/setters** tạo model JavaBean để processor đọc được các thuộc tính; tên Java `maxAttempts` được biểu diễn thành khóa cấu hình canonical `max-attempts`.
- `Duration` là kiểu cấu hình mà Spring Boot có cơ chế chuyển đổi từ chuỗi như `5s`; metadata ghi thông tin kiểu dữ liệu giúp IDE hỗ trợ đúng hơn.
- `Retry` là **static nested class**, được processor xem là nhóm con; vì vậy khóa dự kiến là `demo.client.retry.max-attempts`, không phải `demo.client.max-attempts`.
- Javadoc ngay trên fields được dùng làm nguồn cho các mô tả `description` nếu processor đang biên dịch source của lớp này. Nên viết **văn bản thuần**, tránh phụ thuộc các Javadoc tags hoặc HTML formatting mà JSON metadata không xử lý.

Processor có thể suy ra những default value đơn giản như `name = "local-client"` hoặc `maxAttempts = 3`. Nhưng biểu thức `Duration.ofSeconds(2)` **không nên được kỳ vọng sẽ tự biến thành JSON defaultValue**: giá trị khởi tạo bằng method call có thể cần mô tả thủ công. Việc có hoặc không có `defaultValue` trong JSON không thay đổi default runtime thực tế của object.

### 6.4. File MetadataDemoApplication.java

Tạo `src/main/java/com/example/metadatademo/MetadataDemoApplication.java`:

~~~java
package com.example.metadatademo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MetadataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showClientConfiguration(DemoClientProperties props) {
        return args -> System.out.println(
                "client=" + props.getName()
                + ", timeout=" + props.getTimeout()
                + ", attempts=" + props.getRetry().getMaxAttempts()
        );
    }
}
~~~

`@ConfigurationPropertiesScan` đăng ký lớp cấu hình để **runtime binding** hoạt động. Nó khác annotation processor, dù cùng dựa trên `@ConfigurationProperties`. Bean `ApplicationRunner` chỉ in giá trị để kiểm chứng, không phải thành phần bắt buộc để sinh metadata.

### 6.5. File application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
demo.client.name=inventory
demo.client.timeout=5s
demo.client.retry.max-attempts=4
~~~

Khi ứng dụng chạy thành công, binder đọc các khóa này và đưa vào `DemoClientProperties`. Java `Duration.ofSeconds(5).toString()` trả về `PT5S`, nên runner có dòng output **chính xác**:

~~~text
client=inventory, timeout=PT5S, attempts=4
~~~

Spring Boot cũng in các log khởi động tùy môi trường, vì vậy chỉ dự đoán **dòng do runner phát ra**, không dự đoán toàn bộ stdout. Ứng dụng không có `spring-boot-starter-web` nên ví dụ không yêu cầu HTTP server hoặc cổng 8080.

### 6.6. Build, sinh JSON và chạy

Linux/macOS tại project root:

~~~bash
./mvnw clean compile
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean compile
.\mvnw.cmd spring-boot:run
~~~

Nếu project không có Maven Wrapper, dùng Maven cài sẵn bằng `mvn clean compile` và `mvn spring-boot:run`, với điều kiện Maven/JDK tương thích. Khi chạy `compile`, Maven Compiler Plugin gọi Spring Boot annotation processor đã cấu hình ở `pom.xml`.

Sau compile, tìm file:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Trên Linux/macOS:

~~~bash
cat target/classes/META-INF/spring-configuration-metadata.json
~~~

Trên PowerShell:

~~~powershell
Get-Content .\target\classes\META-INF\spring-configuration-metadata.json
~~~

Lệnh `cat`/`Get-Content` chỉ đọc file. Nếu file không tồn tại, xem mục troubleshooting ở cuối bài, không vội kết luận rằng runtime binding không hoạt động.

## 7. Metadata được sinh ra có dạng gì?

Bên dưới là **mô hình rút gọn minh họa**, không phải byte-for-byte output cố định của compiler: output thật có thể chứa nhiều thuộc tính như `sourceType`, `defaultValue`, `description` và sắp xếp khác theo phiên bản processor.

~~~json
{
  "groups": [
    {
      "name": "demo.client",
      "type": "com.example.metadatademo.DemoClientProperties"
    },
    {
      "name": "demo.client.retry",
      "type": "com.example.metadatademo.DemoClientProperties$Retry"
    }
  ],
  "properties": [
    {
      "name": "demo.client.name",
      "type": "java.lang.String",
      "description": "Tên hiển thị của client."
    },
    {
      "name": "demo.client.timeout",
      "type": "java.time.Duration",
      "description": "Thời gian chờ phản hồi từ dịch vụ."
    },
    {
      "name": "demo.client.retry.max-attempts",
      "type": "java.lang.Integer",
      "description": "Số lần thử tối đa."
    }
  ]
}
~~~

**Không chép file JSON mô phỏng này để thay file được sinh**. Hãy để processor tạo output thật và đọc file thật bằng lệnh ở mục 6.6; manual additions có tệp riêng như mục 9.

Ý nghĩa của các trường:

| Trường | Tác dụng |
| --- | --- |
| `groups[].name` | Prefix/nhóm chứa các thuộc tính |
| `properties[].name` | Khóa cấu hình đầy đủ theo dạng canonical (thường kebab-case) |
| `properties[].type` | Kiểu Java giúp IDE suy luận value |
| `properties[].description` | Văn bản giải thích, thường đến từ Javadoc |
| `properties[].defaultValue` | Giá trị mặc định **nếu processor suy ra hoặc được khai báo bổ sung** |
| `properties[].deprecation` | Thông tin deprecated khi được khai báo/nhận diện |
| `hints[]` | Gợi ý giá trị hoặc provider trợ giúp khi nhập liệu |

File metadata không tự quyết định thứ tự ưu tiên giữa `application.yml`, environment variables và command-line arguments. Việc resolve property sources và relaxed binding thuộc phần Spring Boot runtime.

## 8. Java records, nested properties, giới hạn suy luận

### 8.1. Immutable configuration qua Java record

Từ Java 17, bạn có thể dùng `record` làm mô hình cấu hình bất biến. Dưới đây là **một lớp source thay thế để minh họa**, không được khai báo cùng prefix `demo.client` với ví dụ JavaBean trước đó trong cùng ứng dụng nếu không cố ý dùng chung namespace.

Tạo `MailProperties.java` trong package `com.example.metadatademo` của một project Spring Boot:

~~~java
package com.example.metadatademo;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Cấu hình hệ thống thư.
 *
 * @param sender địa chỉ người gửi.
 * @param retryCount số lần thử lại.
 */
@ConfigurationProperties(prefix = "demo.mail")
public record MailProperties(String sender, int retryCount) {
}
~~~

Với `@ConfigurationPropertiesScan` (hoặc `@EnableConfigurationProperties(MailProperties.class)`), runtime có thể bind theo constructor của record. Processor phân tích các record components để sinh các khóa như `demo.mail.sender` và `demo.mail.retry-count`. **Để mô tả các record components**, Javadoc đặt `@param` trên class-level Javadoc như ví dụ, không phải Javadoc trên instance fields (record không khai báo fields theo cách JavaBean thông thường).

Trong Spring Boot 3.x, một record có một canonical constructor thường không cần gắn `@ConstructorBinding`. Nếu class có nhiều constructor hoặc constructor đặc biệt, các quy tắc lựa chọn constructor và processor cần xem theo phiên bản Boot cụ thể.

### 8.2. Nested class và @NestedConfigurationProperty

Processor tự nhận diện **inner/nested class** như `Retry` trong ví dụ và sinh prefix con. Nếu property là một type độc lập đặt ở class khác, bạn có thể dùng `@NestedConfigurationProperty` để **gợi ý cho processor** rằng nó là nested metadata.

Ví dụ minh họa thành phần trong một lớp `@ConfigurationProperties`:

~~~java
import org.springframework.boot.context.properties.NestedConfigurationProperty;

@NestedConfigurationProperty
private RemoteOptions remote;
~~~

Đây là **đoạn field**, không phải lớp Java độc lập; nó giả định type `RemoteOptions` đã có. Annotation này phục vụ **metadata discovery**, không tạo bean và không phải là công tắc bật/tắt binder runtime. Với collections/maps, processor có quy tắc nhận diện riêng; nó thường mô tả map/list như một property, không nhất thiết liệt kê vô hạn keys động thành từng mục JSON.

### 8.3. Method @Bean được gắn @ConfigurationProperties

Processor còn nhận diện các method có `@ConfigurationProperties`, thường gặp khi cấu hình bean thư viện bên thứ ba qua một factory method:

~~~java
@Bean
@ConfigurationProperties(prefix = "vendor.connection")
VendorConnectionSettings vendorConnectionSettings() {
    return new VendorConnectionSettings();
}
~~~

Đây là **đoạn trong một class `@Configuration`**, yêu cầu type/method phù hợp và bean có thể bind. Nếu type `VendorConnectionSettings` là compiled dependency mà processor không có source trong module, một số mô tả/default có thể không suy ra được. Trường hợp này metadata thủ công có thể bổ sung. Annotation do người dùng tự tạo **meta-annotated** với `@ConfigurationProperties` không được processor tự nhận diện như một annotation trực tiếp theo tài liệu Spring Boot 3.5.

### 8.4. Vì sao defaultValue có thể thiếu?

Processor dùng heuristic tĩnh để đọc initializer từ source. Không kỳ vọng nó đánh giá mọi biểu thức Java, đọc các constant nằm ở class khác hoặc tự suy ra mặc định của mọi `List`/`Map`. Ví dụ:

~~~java
private Duration timeout = Duration.ofSeconds(2);
~~~

Runtime thực sự có default `PT2S`, nhưng processor có thể không ghi `defaultValue`. Đây là hạn chế suy luận ở compile time, không phải sai giá trị Spring binder. Khi metadata cần default chính xác để IDE hiển thị, dùng file `additional-spring-configuration-metadata.json`.

## 9. Bổ sung metadata thủ công và hints

### 9.1. Tại sao cần thêm file manual metadata?

Có ba tình huống thường gặp:

1. Property được đọc trực tiếp qua `@Value` hoặc `Environment.getProperty(...)`, không có class `@ConfigurationProperties` để processor suy ra.
2. Processor phát hiện property nhưng thiếu `description`, không suy ra được `defaultValue` hoặc chưa có deprecated information.
3. Bạn muốn IDE gợi ý **những giá trị cụ thể** cho người dùng khi nhập property.

Tạo file chính xác ở:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Khi processor chạy, nội dung file bổ sung được **merge vào metadata đầu ra**. Tệp additional không thay thế `spring-configuration-metadata.json` do processor sinh. Khi có tên property trùng một mục đã phát hiện, các trường được khai báo như `description`, `defaultValue`, `deprecation` có thể ghi đè thông tin processor suy ra; thuộc tính mới chưa được phát hiện có thể được thêm như một property.

### 9.2. Ví dụ JSON bổ sung hoàn chỉnh

~~~json
{
  "properties": [
    {
      "name": "demo.client.timeout",
      "description": "Giới hạn thời gian chờ kết nối của client.",
      "defaultValue": "PT2S"
    },
    {
      "name": "demo.feature-toggle",
      "type": "java.lang.Boolean",
      "description": "Bật một tính năng tùy chọn do ứng dụng đọc qua Environment.",
      "defaultValue": false
    }
  ],
  "hints": [
    {
      "name": "demo.client.name",
      "values": [
        {
          "value": "inventory",
          "description": "Client gọi dịch vụ kho."
        },
        {
          "value": "orders",
          "description": "Client gọi dịch vụ đơn hàng."
        }
      ]
    }
  ]
}
~~~

Ý nghĩa:

- `demo.client.timeout` đã được phát hiện từ JavaBean; manual metadata bổ sung **defaultValue PT2S** mà processor không chắc tự suy ra từ `Duration.ofSeconds(2)`.
- `demo.feature-toggle` là một khóa **minh họa** có thể được ứng dụng đọc bằng `Environment` hoặc `@Value`. JSON chỉ mô tả khóa, **không tự làm ứng dụng đọc hoặc sử dụng nó**.
- `hints` đưa ra **gợi ý** `inventory` và `orders` cho IDE, không tự cấm người dùng nhập tên khác. Muốn kiểm tra hợp lệ thật phải dùng logic binding/validation riêng.

**Đừng ghi secrets, mật khẩu hoặc tokens vào metadata**: file JSON được đóng cùng artifact và có thể được đọc bởi người sử dụng thư viện. Chỉ ghi mô tả/hints/default không nhạy cảm.

### 9.3. Deprecated properties và metadata

Khi đổi tên property, có thể cần thông báo khóa cũ đã deprecated và khóa thay thế, ví dụ:

~~~json
{
  "properties": [
    {
      "name": "demo.client.old-name",
      "type": "java.lang.String",
      "description": "Tên client cũ.",
      "deprecation": {
        "level": "warning",
        "reason": "Dùng tên khóa mới để thống nhất cấu hình.",
        "replacement": "demo.client.name"
      }
    }
  ]
}
~~~

JSON này là **ví dụ một khai báo thủ công độc lập**, có thể đưa mục `properties` vào file additional JSON đang dùng. Nó **chỉ tạo cảnh báo/tài liệu ở metadata**, không tự làm Spring Boot chấp nhận alias giữa `demo.client.old-name` và `demo.client.name`. Nếu cần tương thích ngược ở runtime, code/binder phải thực sự hỗ trợ khóa cũ. Metadata ghi `deprecation` không thay cho migration logic.

Spring Boot cũng có `@DeprecatedConfigurationProperty` trên accessor thích hợp để processor ghi deprecation metadata, nhưng annotation đó không tạo alias runtime và không tự đảm bảo backward compatibility.

## 10. Kiểm tra metadata sau compile và sau package

### 10.1. Maven

Linux/macOS:

~~~bash
./mvnw clean compile
./mvnw clean package
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean compile
.\mvnw.cmd clean package
~~~

File sinh lúc compile thường là:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Khi Spring Boot Maven Plugin đóng executable JAR, metadata ứng dụng nằm dưới classes của archive (thường `BOOT-INF/classes/META-INF/spring-configuration-metadata.json`). Liệt kê entries:

~~~bash
jar tf target/metadata-demo-0.0.1-SNAPSHOT.jar
~~~

Tìm tên `spring-configuration-metadata.json` trong output. Tên JAR trong ví dụ đến từ `artifactId/version` của POM ở mục 6; nếu project thực tế dùng tên khác, phải dùng artifact thật trong `target/`.

Nếu xây thư viện **JAR thông thường**, metadata ở `META-INF/spring-configuration-metadata.json` tại gốc JAR (không có `BOOT-INF/classes`). Đây là một lý do cần hiểu **loại artifact thực tế** khi kiểm tra đường dẫn.

### 10.2. Gradle

Linux/macOS:

~~~bash
./gradlew clean compileJava
./gradlew bootJar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean compileJava
.\gradlew.bat bootJar
~~~

`bootJar` yêu cầu Spring Boot Gradle plugin. File trung gian thường ở:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

File trong executable JAR cũng phụ thuộc layout của Spring Boot plugin. Với Gradle library module dùng task `jar` thay `bootJar`, kiểm tra nội dung JAR thông thường. Khi build nhiều modules, cần nhìn output của **module chứa source `@ConfigurationProperties`**, không chỉ root build directory.

### 10.3. Kiểm tra JSON một cách có ý nghĩa

Đừng chỉ kiểm tra file tồn tại. Mở JSON và xác nhận:

- `groups` có prefix `demo.client` (nếu processor phát hiện).
- `properties` có `demo.client.name`, `demo.client.timeout` và `demo.client.retry.max-attempts`.
- `description` lấy từ Javadoc source đúng, và `defaultValue` thủ công có hiệu lực sau khi thêm additional metadata.
- `hints` đã được merge, không bị bỏ qua vì task order/cache.
- File JSON cuối được đóng gói cùng artifact mà IDE/consumer thực sự sử dụng.

Sau khi import/build lại project trong IDE, mở `application.properties` và thử completion sau `demo.client.`. Nếu không có gợi ý dù JSON đúng, kiểm tra Spring tooling/plugin của IDE và việc reload project/classpath trước khi sửa Java code.

## 11. Lombok và nhiều annotation processors

Khi dự án dùng **Lombok** để sinh getter/setter/constructors, việc metadata processor nhìn thấy model có thể phụ thuộc **thứ tự chạy annotation processors**. Tài liệu Spring Boot yêu cầu cấu hình để Lombok chạy trước `spring-boot-configuration-processor`.

- **Maven:** xem cấu hình Maven Compiler Plugin `annotationProcessorPaths` và `annotationProcessors` (hoặc cơ chế tương đương theo version plugin) để bảo đảm thứ tự thích hợp.
- **Gradle:** khai báo các processor qua configuration `annotationProcessor` và sắp xếp/cấu hình phù hợp theo hướng dẫn Spring Boot và Lombok version sử dụng.

Ví dụ Gradle Groovy DSL có cả hai artifact:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.42'
    annotationProcessor 'org.projectlombok:lombok:1.18.42'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.5.16'
}
~~~

`1.18.42` là **giá trị minh họa**, phải kiểm tra bản Lombok hỗ trợ JDK/compiler của dự án. Thứ tự khai báo phù hợp theo tài liệu là một điều kiện cần, nhưng build thực tế còn chịu ảnh hưởng plugin/toolchain. Nếu annotation processing chạy hai lần (ví dụ vì AspectJ plugin cùng một compiler invocation), có thể phát sinh output trùng/ghi đè; hãy cấu hình một đường xử lý chính và bảo đảm processor không bị gọi lặp.

Các build scripts/IDE integrations khác nhau có thể dùng processor path và Java compiler settings riêng. Đừng chỉ dựa vào “IDE compile thành công” nếu CI dùng lệnh Gradle/Maven khác và file JSON trong JAR biến mất.

## 12. Troubleshooting: không sinh JSON hoặc IDE không autocomplete

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| Không thấy `spring-configuration-metadata.json` sau `compile` | Processor không trên annotation processor path, processing bị disable hoặc compile task không chạy | Kiểm tra Maven Compiler Plugin/Gradle `annotationProcessor`; chạy clean compile và đọc log |
| Java 23+ build xong nhưng không có metadata | Dựa vào implicit classpath processor discovery đã thay đổi | Khai báo processor tường minh qua `annotationProcessorPaths`/`annotationProcessor` |
| Maven không giải quyết được `spring-boot-configuration-processor` | Sai version, BOM/parent không quản lý, repository/proxy lỗi | Kiểm tra tọa độ/version và repository, effective POM |
| JSON có nhưng thiếu `demo.client.*` | Class không gắn `@ConfigurationProperties` hoặc không nằm trong source đang compile | Kiểm tra annotation, module source và compile output |
| JSON có name/type nhưng không có description | Source không có Javadoc phù hợp hoặc type chỉ có dưới dạng compiled dependency | Thêm Javadoc thuần tại source hoặc metadata thủ công |
| Thiếu `defaultValue` của `Duration` hay collections | Processor không suy ra initializer phức tạp hoặc dữ liệu ở class khác | Khai báo default trong file additional metadata |
| Không có `retry.max-attempts` | Nested type bị hiểu sai hoặc không có getter/setter/mapping phù hợp | Kiểm tra nested class structure, accessor, `@NestedConfigurationProperty` nếu type riêng |
| Additional hints không xuất hiện | File sai đường dẫn, JSON lỗi hoặc build task không đưa resource tới processor trước compile | Kiểm tra `src/main/resources/META-INF`, task `processResources`, clean rebuild |
| Lombok class có field nhưng metadata thiếu properties | Lombok chưa chạy trước configuration processor hoặc cấu hình compiler path thiếu processor | Sắp xếp processors, kiểm tra JDK/Lombok và build log |
| Runtime vẫn không bind dù metadata đầy đủ | Chưa đăng ký `@ConfigurationProperties` bean, sai prefix hoặc cấu hình môi trường | Thêm `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` và kiểm tra property sources |
| IDE không gợi ý nhưng file JSON đúng | IDE chưa import/reload project, chưa bật Spring support hoặc cache chưa cập nhật | Reload Maven/Gradle, kiểm tra extension và restart indexing |
| File có ở `target/classes` nhưng không trong JAR | Packaging/resource filtering/exclusion hoặc build chọn module sai | Kiểm tra `jar tf`, Gradle/Maven packaging plugin và output artifact thật |
| Metadata có gợi ý nhưng user nhập giá trị khác vẫn chạy | `hints` không phải validation | Áp dụng Bean Validation, enum type hoặc validator runtime phù hợp |
| Metadata chỉ hiển thị sau chạy app | Nhầm giai đoạn build với runtime, build task chưa compile đúng | Kiểm tra metadata sau `compile`, không cần khởi động ứng dụng |

### Cách khoanh vùng lỗi theo bốn lớp

**Lớp 1 — Source model:** Xác nhận `@ConfigurationProperties`, getters/setters hoặc record constructor, prefix và nested type. Chỉ sửa source nếu metadata không thể được suy ra từ định nghĩa hiện tại.

**Lớp 2 — Build/processor:** Xác nhận đúng processor artifact/version, compiler plugin/toolchain, `annotationProcessorPaths` hoặc Gradle `annotationProcessor` và clean compile thành công.

**Lớp 3 — Output/artifact:** Đọc trực tiếp `META-INF/spring-configuration-metadata.json`, xem additional metadata có được merge và đóng gói hay chưa.

**Lớp 4 — IDE/runtime:** Nếu JSON đã đúng, mới kiểm tra IDE support và runtime binder. Đừng sửa metadata để chữa lỗi Spring bean registration hoặc `Environment` precedence.

## 13. Bài tập thực hành

**Bài 1 — Sinh metadata:** Tạo project Maven Java 17 Boot 3.5.x có processor; thêm `DemoClientProperties` như mục 6, chạy `./mvnw clean compile`. Tìm JSON và liệt kê ba khóa `demo.client.name`, `demo.client.timeout` và `demo.client.retry.max-attempts`. Ghi nhận `defaultValue` nào được processor tự suy ra.

**Bài 2 — Bổ sung default:** Thêm `additional-spring-configuration-metadata.json` để công bố default `PT2S` cho timeout. Rebuild sạch, đọc JSON và kiểm tra defaultValue của `demo.client.timeout`, đồng thời không thay đổi giá trị Java runtime.

**Bài 3 — Tách runtime khỏi metadata:** Tạm bỏ `@ConfigurationPropertiesScan` nhưng giữ processor. Kiểm tra xem file metadata còn sinh được không và ứng dụng có còn lấy được `DemoClientProperties` như một bean không. Sau đó khôi phục scanning. Câu trả lời cần giải thích hai pipeline độc lập.

**Bài 4 — Record:** Tạo `MailProperties` record, dùng `@param` mô tả components. Kiểm tra các khóa `demo.mail.sender` và `demo.mail.retry-count` trong metadata. Giải thích vì sao record không cần JavaBean setters.

**Bài 5 — Đóng gói:** Tạo executable JAR, chạy `jar tf`, tìm file metadata dưới layout của archive. Giải thích vì sao IDE có thể dùng file metadata này khi ứng dụng chưa được chạy.

## 14. Checklist hoàn thành

- [ ] Có lớp `@ConfigurationProperties` được khai báo và đăng ký đúng ở runtime khi cần binding.
- [ ] Maven/Gradle build có `spring-boot-configuration-processor` trên **annotation processor path**, tương thích JDK.
- [ ] Đã chạy `clean compile` và tìm được `META-INF/spring-configuration-metadata.json`.
- [ ] Metadata có đúng prefix, tên property, kiểu, mô tả và nested keys.
- [ ] Phân biệt rõ **metadata compile time** với **binding/validation runtime**.
- [ ] Với defaults phức tạp/hints, file additional được đặt đúng path và merge vào kết quả.
- [ ] Nếu có Lombok/AspectJ hoặc Java 23+, đã kiểm tra thứ tự/đường chạy processor.
- [ ] File metadata nằm trong artifact JAR dự kiến, không chỉ trong thư mục build tạm.
- [ ] Đã thử IDE completion và kiểm tra IDE/plugin khi cần, không nhầm IDE cache với lỗi runtime.
- [ ] Metadata không chứa secrets và không tuyên bố hints là validation.

## 15. Tài liệu chính thức

- Spring Boot 3.5 — Annotation Processor và automatic metadata: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.5 — Configuration Metadata Format: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/format.html
- Spring Boot 3.5 — Providing Manual Hints: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/manual-hints.html
- Spring Boot 3.5 — Externalized Configuration và @ConfigurationProperties: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Maven Compiler Plugin — Compiler configuration và annotation processing: https://maven.apache.org/plugins/maven-compiler-plugin/
- Gradle — Java Plugin, annotationProcessor configuration: https://docs.gradle.org/current/userguide/java_plugin.html

**Kết quả cần đạt:** Từ các lớp cấu hình Java của dự án, bạn có thể tự sinh file `spring-configuration-metadata.json` ở compile time, bổ sung metadata không suy ra được, xác minh file có trong artifact và giải thích vì sao IDE hỗ trợ completion mà không làm thay đổi cơ chế runtime binding của Spring Boot.