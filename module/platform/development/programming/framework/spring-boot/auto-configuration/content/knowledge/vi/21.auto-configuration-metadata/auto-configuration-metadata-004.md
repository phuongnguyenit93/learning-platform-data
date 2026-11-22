# spring-boot-configuration-processor và spring-configuration-metadata.json

## 1. Mục tiêu: giúp IDE hiểu cấu hình của ứng dụng

Khi phát triển một Spring Boot starter hoặc auto-configuration, người dùng thường khai báo cấu hình trong `application.properties` hoặc `application.yaml`. Ví dụ:

~~~properties
acme.client.endpoint=https://api.example.test
acme.client.connect-timeout=2s
acme.client.mode=standard
~~~

Ứng dụng có thể bind các key này vào một class được đánh dấu `@ConfigurationProperties`. Tuy nhiên, nếu chỉ có class Java, IDE có thể không biết đầy đủ:
- Những property nào được thư viện hỗ trợ;
- Kiểu dữ liệu của từng property;
- Mô tả và giá trị mặc định;
- Những giá trị hợp lệ hoặc gợi ý autocomplete;
- Property nào đã deprecated và được thay bằng key nào.

Spring Boot giải quyết vấn đề này bằng **configuration metadata**. Annotation processor `spring-boot-configuration-processor` đọc các class/method có `@ConfigurationProperties` trong lúc compile và tạo file:

~~~text
META-INF/spring-configuration-metadata.json
~~~

IDE và các công cụ hỗ trợ cấu hình có thể dùng file đó để cung cấp completion, documentation và gợi ý giá trị khi người dùng sửa application configuration.

**Điều cần phân biệt:** metadata là mô tả dành cho công cụ phát triển. Nó không tự bind property, không tự tạo bean và không thay thế `@ConfigurationProperties` hoặc Spring Binder ở runtime.

Bài viết dùng **Spring Boot 3.5.16, Java 17+ và Maven/Gradle** làm mốc ví dụ.

## 2. Hai processor có tên gần giống nhưng nhiệm vụ khác nhau

Trong hệ sinh thái Spring Boot có hai annotation processor thường gặp:

| Processor | File được tạo | Mục đích |
| --- | --- | --- |
| `spring-boot-configuration-processor` | `META-INF/spring-configuration-metadata.json` | Mô tả configuration properties cho IDE, autocomplete và documentation |
| `spring-boot-autoconfigure-processor` | `META-INF/spring-autoconfigure-metadata.properties` | Thu thập một số condition metadata để Spring Boot lọc sớm auto-configuration không phù hợp, hỗ trợ startup |

Bài này tập trung vào processor thứ nhất.

Không nhầm hai file:
- `spring-configuration-metadata.json` mô tả property mà người dùng có thể cấu hình.
- `spring-autoconfigure-metadata.properties` là metadata phục vụ việc đánh giá/lọc auto-configuration.

Một dự án starter có thể dùng cả hai processor nếu vừa cung cấp `@ConfigurationProperties` vừa có các lớp auto-configuration cần metadata condition.

## 3. Cơ chế hoạt động

Luồng tạo metadata:

~~~text
Java/Kotlin source
       |
       v
@ConfigurationProperties
       |
       v
spring-boot-configuration-processor
       |
       v
Annotation processing trong compile
       |
       v
META-INF/spring-configuration-metadata.json
       |
       v
Đóng gói vào JAR
       |
       v
IDE đọc metadata để hỗ trợ application.properties/YAML
~~~

Processor được chạy trong giai đoạn biên dịch. Nó phân tích source model, tên property, kiểu, mô tả và một số default value có thể suy ra tĩnh.

Ví dụ class:

~~~java
@ConfigurationProperties("acme.client")
public class AcmeClientProperties {
    private String endpoint;
    private int maxConnections;
}
~~~

có thể tạo metadata cho:
- `acme.client.endpoint`;
- `acme.client.max-connections`.

Tên property được chuẩn hóa theo dạng lowercase kebab-case, kể cả khi tên Java field dùng camelCase.

### Metadata không phải cơ chế binding

Có ba việc riêng biệt:

1. `@ConfigurationProperties` mô tả cấu trúc cấu hình mà Spring Binder có thể bind.
2. `@EnableConfigurationProperties`, `@ConfigurationPropertiesScan` hoặc một cơ chế đăng ký phù hợp làm properties object tham gia ApplicationContext.
3. `spring-boot-configuration-processor` tạo metadata để công cụ phát triển hiểu cấu hình.

Nếu chỉ thêm một entry vào JSON nhưng không có code đọc/bind property, ứng dụng không tự nhiên bắt đầu xử lý key đó. Metadata thủ công chỉ bổ sung thông tin cho IDE.

Ngược lại, một property có thể được bind và hoạt động dù metadata không được tạo; khi đó IDE có thể thiếu completion hoặc mô tả.

## 4. Cấu hình processor với Maven

Spring Boot 3.5 hướng dẫn dùng `maven-compiler-plugin` phiên bản **3.12.0 trở lên** và thêm processor vào `annotationProcessorPaths`.

Ví dụ POM rút gọn cho dự án Boot 3.5.16:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>acme-metadata-demo</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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
</project>
~~~

Điểm cần nhớ:
- Processor được khai báo trong compiler plugin, nên chỉ tham gia annotation processing lúc build.
- Version processor nên đồng bộ với Spring Boot version mà dự án đang dùng.
- Nếu dùng nhiều annotation processor, ví dụ Lombok, phải khai báo chúng trong `annotationProcessorPaths`. Đảm bảo Lombok chạy **trước** `spring-boot-configuration-processor` theo hướng dẫn của Spring Boot.
- Nếu dự án dùng AspectJ và annotation processing đã chạy qua plugin khác, tránh chạy processor hai lần.

Một số cấu hình Maven cũ khai báo `spring-boot-configuration-processor` như dependency có `optional=true`. Với Maven Compiler Plugin hiện đại, cấu hình annotation processor path tường minh giúp kiểm soát processor được chạy và tránh đưa processor vào dependency runtime của consumer.

Chạy:

~~~bash
mvn clean compile
~~~

Sau khi compile, kiểm tra file:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Nếu không thấy file, kiểm tra annotation processor có được gọi trong Maven compiler plugin hay không, class có `@ConfigurationProperties` hay chưa và source có compile thành công không.

## 5. Cấu hình processor với Gradle

Với Gradle, khai báo processor trong configuration `annotationProcessor`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Chạy:

~~~bash
./gradlew clean compileJava
~~~

Metadata thường nằm ở:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Nếu dùng file `additional-spring-configuration-metadata.json`, cấu hình task để resources được xử lý trước khi annotation processor chạy:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

Dòng cấu hình này bảo đảm additional metadata đã có sẵn khi `compileJava` thực thi. Với Gradle Kotlin DSL, có thể dùng cú pháp tương ứng:

~~~kotlin
tasks.named<JavaCompile>("compileJava") {
    inputs.files(tasks.named("processResources"))
}
~~~

Không khai báo processor trong `implementation` chỉ để chạy annotation processing. `annotationProcessor` là configuration dành cho nhiệm vụ này.

## 6. Ví dụ Java: tạo metadata từ @ConfigurationProperties

Tạo file `src/main/java/com/example/metadata/AcmeClientProperties.java`:

~~~java
package com.example.metadata;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public class AcmeClientProperties {

    /**
     * Base endpoint of the Acme service.
     */
    private String endpoint = "https://api.example.test";

    /**
     * Maximum time to wait for one request.
     */
    private Duration connectTimeout = Duration.ofSeconds(2);

    /**
     * Request processing mode.
     */
    private Mode mode = Mode.STANDARD;

    /**
     * Retry configuration.
     */
    private Retry retry = new Retry();

    /**
     * Protocol used to reach the service.
     */
    private String protocol = "https";

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Mode getMode() {
        return mode;
    }

    public void setMode(Mode mode) {
        this.mode = mode;
    }

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public String getProtocol() {
        return protocol;
    }

    public void setProtocol(String protocol) {
        this.protocol = protocol;
    }

    public enum Mode {
        STANDARD,
        BULK
    }

    public static class Retry {

        /**
         * Maximum number of attempts.
         */
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

Processor có thể phát hiện các property như:

| Java field | Property được tạo |
| --- | --- |
| `endpoint` | `acme.client.endpoint` |
| `connectTimeout` | `acme.client.connect-timeout` |
| `mode` | `acme.client.mode` |
| `retry.maxAttempts` | `acme.client.retry.max-attempts` |
| `protocol` | `acme.client.protocol` |

Các mô tả trong Javadoc field có thể được dùng làm `description` khi source của class đang được compile. Nên viết mô tả ngắn, rõ nghĩa, plain text; không dựa vào Markdown hoặc HTML vì Javadoc field được đưa vào JSON metadata mà không qua bộ xử lý Markdown.

**Đăng ký properties để runtime binding:** class có `@ConfigurationProperties` chưa tự động trở thành bean trong mọi ứng dụng. Ví dụ:

~~~java
package com.example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(AcmeClientProperties.class)
public class MetadataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }
}
~~~

`@EnableConfigurationProperties` phục vụ runtime binding. Annotation processor có thể đọc class properties trong lúc compile ngay cả khi cần một bước đăng ký bean riêng để ứng dụng sử dụng object đó.

## 7. Processor phát hiện property, mô tả và default như thế nào?

Processor thu thập metadata từ class hoặc method có `@ConfigurationProperties`.

### 7.1. JavaBean với getter/setter

Với class mutable thông thường, processor tìm các getter/setter chuẩn. Các kiểu collection và map có xử lý riêng; trong một số trường hợp chỉ cần getter cũng đủ để nhận diện property.

Tên property theo JavaBean convention:
- `getConnectTimeout()` → `connect-timeout`;
- `isEnabled()` → `enabled`;
- `getRetry().getMaxAttempts()` → `retry.max-attempts`.

### 7.2. Constructor binding và record

Nếu class có một constructor tham số duy nhất, processor có thể tạo một property cho từng constructor parameter, trừ trường hợp constructor được đánh dấu `@Autowired`. Với constructor được đánh dấu `@ConstructorBinding`, property được tạo theo tham số của constructor đó.

Với Java record, mô tả component nên đặt bằng Javadoc `@param` ở class-level, vì record không có instance field tường minh để đặt field Javadoc thông thường.

Ví dụ:

~~~java
/**
 * Acme client settings.
 *
 * @param endpoint Base endpoint of the service.
 * @param timeout Maximum request duration.
 */
@ConfigurationProperties("acme.client")
public record AcmeClientRecordProperties(
        String endpoint,
        Duration timeout) {
}
~~~

### 7.3. Nested properties

Processor tự nhận diện inner class như nested properties. Trong ví dụ `AcmeClientProperties`, class `Retry` là static nested class nên property được biểu diễn dưới namespace `acme.client.retry`.

Nếu kiểu nested là một class thông thường nằm ở file khác, có thể dùng `@NestedConfigurationProperty` trên field hoặc getter để chỉ rõ rằng kiểu đó cần được xem như một nhóm thuộc tính lồng nhau:

~~~java
@NestedConfigurationProperty
private Retry retry;
~~~

Annotation này hỗ trợ **metadata generation**; nó không thay đổi cách Spring Binder bind object. Collection và map đã được processor nhận diện riêng nên không cần dùng annotation này cho chúng.

### 7.4. Lombok

Processor hỗ trợ các annotation Lombok thông dụng như `@Data`, `@Value`, `@Getter` và `@Setter`. Khi cấu hình nhiều processor, phải bảo đảm Lombok chạy trước Spring Boot configuration processor để các accessor cần thiết có thể được nhận diện.

### 7.5. Giới hạn khi trích default value

Processor dùng heuristic để suy ra default value từ source model. Việc suy ra chỉ đáng tin khi:
- Kiểu đang được compile từ source hiện tại;
- Default được biểu diễn tĩnh;
- Giá trị không phụ thuộc logic runtime hoặc constant ở class khác mà processor không phân tích được.

Một số trường hợp processor không thể tự suy ra:
- Collection có giá trị mặc định được tạo bằng nhiều lệnh;
- Giá trị mặc định lấy từ constant hoặc method khác;
- Kiểu chỉ có compiled class từ dependency, không có source;
- Giá trị động hoặc biểu thức phức tạp như `Duration.ofSeconds(2)`.

Khi default không được phát hiện, bổ sung bằng manual metadata. Không tự giả định JSON đã chứa đầy đủ default chỉ vì Java field có initializer.

## 8. Cấu trúc spring-configuration-metadata.json

File được tạo trong JAR tại:

~~~text
META-INF/spring-configuration-metadata.json
~~~

JSON có bốn phần chính:

| Phần | Vai trò |
| --- | --- |
| `groups` | Nhóm property theo prefix hoặc namespace |
| `properties` | Mỗi property mà người dùng có thể khai báo |
| `hints` | Giá trị gợi ý, provider hoặc hỗ trợ autocomplete |
| `ignored` | Property được chủ động loại khỏi danh sách metadata thông thường |

Ví dụ rút gọn:

~~~json
{
  "groups": [
    {
      "name": "acme.client",
      "type": "com.example.metadata.AcmeClientProperties",
      "sourceType": "com.example.metadata.AcmeClientProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.client.endpoint",
      "type": "java.lang.String",
      "description": "Base endpoint of the Acme service.",
      "sourceType": "com.example.metadata.AcmeClientProperties",
      "defaultValue": "https://api.example.test"
    },
    {
      "name": "acme.client.retry.max-attempts",
      "type": "java.lang.Integer",
      "description": "Maximum number of attempts.",
      "sourceType": "com.example.metadata.AcmeClientProperties$Retry",
      "defaultValue": 3
    }
  ],
  "hints": [],
  "ignored": {
    "properties": []
  }
}
~~~

Đây là JSON minh họa cấu trúc. Metadata thực tế còn phụ thuộc processor có suy ra được type/default/description hay không.

### 8.1. Group

Một group là namespace cấp cao, không phải property có giá trị riêng. Ví dụ `acme.client` gom các property:
- `acme.client.endpoint`;
- `acme.client.connect-timeout`;
- `acme.client.retry.max-attempts`.

Một property không bắt buộc phải thuộc group. Các thuộc tính có thể được khai báo độc lập.

Các thuộc tính group thường gồm:
- `name`: tên group;
- `type`: kiểu Java đại diện;
- `description`: mô tả;
- `sourceType`: kiểu source đóng góp metadata;
- `sourceMethod`: method đóng góp group nếu có.

### 8.2. Property

Mỗi entry trong `properties` mô tả một key:
- `name`: tên đầy đủ, lowercase và phân tách bằng dấu chấm;
- `type`: kiểu Java hoặc generic type;
- `description`: mô tả;
- `sourceType`: class đóng góp property;
- `defaultValue`: giá trị mặc định nếu biết;
- `deprecation`: thông tin deprecated nếu có.

Primitive type được biểu diễn bằng wrapper tương ứng, ví dụ `int` thành `java.lang.Integer`.

### 8.3. Hints

Hints giúp IDE đưa ra gợi ý cấu hình. Ví dụ `acme.client.protocol` có thể nhận `http` hoặc `https`:

~~~json
{
  "hints": [
    {
      "name": "acme.client.protocol",
      "values": [
        {
          "value": "https",
          "description": "Use encrypted HTTP transport."
        },
        {
          "value": "http",
          "description": "Use plain HTTP transport."
        }
      ]
    }
  ]
}
~~~

Hint không tự validate runtime value. Nếu property chỉ chấp nhận một tập giá trị cố định, dùng Java enum hoặc validation phù hợp để đảm bảo code thực sự kiểm soát giá trị; metadata chỉ giúp IDE gợi ý.

### 8.4. Ignored

Phần `ignored.properties` liệt kê key được chủ động bỏ khỏi danh sách property thông thường. Đây là cách xử lý metadata cho property không nên hiển thị trong completion/documentation.

Ignored metadata không xóa field Java, không sửa bean và không tự vô hiệu hóa logic runtime. Nó chỉ tác động đến nội dung metadata được tạo.

## 9. Bổ sung metadata thủ công

Không phải property nào cũng xuất phát từ class `@ConfigurationProperties`. Một số key có thể được đọc trực tiếp bằng `Environment`, `Binder` hoặc `@Value`. Ngoài ra, processor có thể không suy ra default hoặc mô tả mong muốn.

Đặt file tại:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Ví dụ cho dự án Acme:

~~~json
{
  "properties": [
    {
      "name": "acme.client.connect-timeout",
      "defaultValue": "2s",
      "description": "Maximum time to wait for one request."
    },
    {
      "name": "acme.client.mode",
      "defaultValue": "standard",
      "description": "Request processing mode."
    },
    {
      "name": "acme.client.protocol",
      "type": "java.lang.String",
      "defaultValue": "https",
      "description": "Transport scheme used to reach the service."
    }
  ],
  "hints": [
    {
      "name": "acme.client.protocol",
      "values": [
        {
          "value": "https",
          "description": "Use encrypted HTTP transport."
        },
        {
          "value": "http",
          "description": "Use plain HTTP transport."
        }
      ]
    }
  ],
  "ignored": {
    "properties": [
      {
        "name": "acme.client.internal-cache-size"
      }
    ]
  }
}
~~~

Processor tự merge nội dung này vào file metadata chính.

Quy tắc merge:
- Nếu property đã được tự động phát hiện, manual metadata có thể ghi đè `description`, `defaultValue` và thông tin `deprecation` khi có khai báo tương ứng.
- Nếu property chưa được phát hiện trong module hiện tại, manual metadata có thể thêm property mới.
- `ignored.properties` loại property tương ứng khỏi phần `properties` của file metadata được tạo.
- File additional metadata là tùy chọn; không cần tạo file rỗng nếu không có nội dung bổ sung.

**Lưu ý quan trọng:** nếu thêm property mới chỉ trong JSON, code vẫn phải thực sự đọc/bind property đó. Metadata không làm xuất hiện một field Java hay tự tạo hành vi cho ứng dụng.

### 9.1. Default của Duration và collection

Trong ví dụ Java, `connectTimeout` có default `Duration.ofSeconds(2)`. Processor có thể không suy ra biểu thức đó; manual metadata khai báo:

~~~json
{
  "name": "acme.client.connect-timeout",
  "defaultValue": "2s"
}
~~~

Với collection, ví dụ:

~~~java
private List<String> regions =
        new ArrayList<>(List.of("ap-southeast-1", "ap-northeast-1"));
~~~

processor không tự suy ra đầy đủ default collection trong mọi trường hợp. Có thể bổ sung:

~~~json
{
  "name": "acme.client.regions",
  "defaultValue": [
    "ap-southeast-1",
    "ap-northeast-1"
  ]
}
~~~

Định dạng default phải phù hợp kiểu property và cách Spring Boot chuyển đổi giá trị cấu hình.

## 10. Gợi ý giá trị và provider

Một hint có thể khai báo `values` hoặc `providers`.

### 10.1. Value hints

Dùng khi tập giá trị tương đối ổn định và có thể mô tả tĩnh:

~~~json
{
  "hints": [
    {
      "name": "acme.client.protocol",
      "values": [
        {"value": "http"},
        {"value": "https"}
      ]
    }
  ]
}
~~~

Nếu giá trị được giới hạn trong code, enum thường là lựa chọn tốt hơn vì compiler và binder có thể kiểm soát kiểu. Hint chỉ là hỗ trợ cho editor.

### 10.2. Value providers

Provider gắn ý nghĩa cho property để IDE có thể tìm gợi ý theo ngữ cảnh. Một số provider được Spring Boot định nghĩa:

| Provider | Mục đích |
| --- | --- |
| `any` | Cho phép nhập thêm giá trị tùy ý |
| `class-reference` | Gợi ý class có trên project classpath, có thể giới hạn target type |
| `handle-as` | Yêu cầu editor xử lý property như một kiểu khác |
| `logger-name` | Gợi ý tên logger và logger group |
| `spring-bean-reference` | Gợi ý tên bean phù hợp |
| `spring-profile-name` | Gợi ý Spring profile có trong project |

Ví dụ gợi ý tên bean:

~~~json
{
  "hints": [
    {
      "name": "acme.client.interceptor",
      "providers": [
        {
          "name": "spring-bean-reference",
          "parameters": {
            "target": "org.springframework.web.client.RestClientCustomizer"
          }
        }
      ]
    }
  ]
}
~~~

Provider không bảo đảm mọi IDE đều triển khai giống nhau. IDE có thể hỗ trợ một số provider hoặc chưa hỗ trợ provider cụ thể; vì vậy hãy xem đây là content assistance, không phải API runtime.

Với map, hint có thể áp dụng riêng cho key hoặc value bằng hậu tố `.keys` và `.values`. Ví dụ `acme.client.routes.keys` và `acme.client.routes.values`.

## 11. Đánh dấu property deprecated

Khi đổi tên property, nên giúp người dùng biết key cũ đã lỗi thời và key mới là gì.

Với JavaBean properties, dùng `@DeprecatedConfigurationProperty` trên getter cũ:

~~~java
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;

@Deprecated
@DeprecatedConfigurationProperty(
        replacement = "acme.client.endpoint",
        since = "1.4.0")
public String getBaseUrl() {
    return this.endpoint;
}

@Deprecated
public void setBaseUrl(String baseUrl) {
    this.endpoint = baseUrl;
}
~~~

Nếu getter/setter cũ vẫn ánh xạ vào property mới, ứng dụng có thể tiếp tục bind key cũ trong giai đoạn chuyển tiếp. Annotation đưa thông tin deprecation và replacement vào metadata.

`@DeprecatedConfigurationProperty`:
- Nên đặt trên getter công bố property cũ;
- Có thể chỉ rõ `replacement` và `since`;
- Mặc định tạo deprecation level dạng warning;
- Không có thuộc tính để chọn level trong annotation này, vì code vẫn đang xử lý property cũ.

Khi muốn giữ thông báo cho một property đã bị loại bỏ khỏi code, có thể khai báo deprecation trong manual metadata. Không nên xóa alias khỏi code trước khi đã lên kế hoạch migration cho người dùng.

## 12. Metadata cho type nằm ở module khác

Nếu `@ConfigurationProperties` sử dụng một class nested nằm trong module khác, processor hiện tại có thể chỉ nhìn thấy compiled class chứ không có source để trích Javadoc/default.

Các lựa chọn:
1. Bổ sung manual metadata cho property/type đó.
2. Đặt metadata source cho type trong module sở hữu type.
3. Nếu type là class thông thường mà bạn kiểm soát, cân nhắc `@ConfigurationPropertiesSource` theo API của phiên bản Boot đang dùng.
4. Nếu type bên ngoài không thuộc quyền kiểm soát, cung cấp metadata tương ứng trong classpath theo quy ước Spring Boot.

Một file metadata cho type có thể được đặt theo dạng:

~~~text
META-INF/spring/configuration/metadata/com.example.SomeType.json
~~~

Điều này hữu ích trong multi-module project, nơi module A khai báo properties nhưng kiểu nested thực tế được định nghĩa trong module B.

## 13. Kiểm tra metadata sau khi build

Sau khi chạy:

~~~bash
mvn clean compile
~~~

Kiểm tra file được tạo:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Có thể xem nhanh nội dung bằng:

~~~powershell
Get-Content target/classes/META-INF/spring-configuration-metadata.json
~~~

Sau khi đóng gói JAR:

~~~bash
mvn package
jar tf target/acme-metadata-demo-1.0.0.jar
~~~

Với một library JAR thông thường, metadata nằm ở `META-INF/spring-configuration-metadata.json`. Với executable Spring Boot JAR, nội dung ứng dụng thường nằm trong `BOOT-INF/classes/META-INF/spring-configuration-metadata.json`.

Có thể kiểm tra riêng:

~~~powershell
jar tf target/acme-metadata-demo-1.0.0.jar | Select-String "spring-configuration-metadata.json"
~~~

Khi publish library/starter, cần xác nhận metadata thực sự được đóng gói trong artifact được publish, không chỉ tồn tại trong workspace của module.

## 14. Kiểm thử runtime binding và metadata generation

Dùng `ApplicationContextRunner` để xác nhận property vẫn được bind vào object. Ví dụ test sau không kiểm tra JSON metadata; nó kiểm tra hành vi runtime riêng biệt.

Tạo file `src/test/java/com/example/metadata/AcmeClientPropertiesTests.java`:

~~~java
package com.example.metadata;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeClientPropertiesTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PropertiesConfiguration.class);

    @Test
    void bindsConfigurationProperties() {
        runner.withPropertyValues(
                "acme.client.endpoint=https://internal.example.test",
                "acme.client.connect-timeout=3s",
                "acme.client.mode=bulk",
                "acme.client.retry.max-attempts=5",
                "acme.client.protocol=http"
        ).run(context -> {
            assertThat(context)
                    .hasSingleBean(AcmeClientProperties.class);

            AcmeClientProperties properties =
                    context.getBean(AcmeClientProperties.class);

            assertThat(properties.getEndpoint())
                    .isEqualTo("https://internal.example.test");

            assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(3));

            assertThat(properties.getMode())
                    .isEqualTo(AcmeClientProperties.Mode.BULK);

            assertThat(properties.getRetry().getMaxAttempts())
                    .isEqualTo(5);

            assertThat(properties.getProtocol())
                    .isEqualTo("http");
        });
    }

    @Test
    void configurationMetadataWasGenerated() {
        assertThat(new ClassPathResource(
                "META-INF/spring-configuration-metadata.json").exists())
                .isTrue();
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AcmeClientProperties.class)
    static class PropertiesConfiguration {
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng:** hai test PASS:
- Test thứ nhất xác nhận Binder chuyển các giá trị property thành kiểu Java phù hợp, bao gồm `Duration`, enum và nested property.
- Test thứ hai xác nhận file metadata đã được copy vào classpath build output.

Hai test chứng minh hai khía cạnh khác nhau. Runtime binding có thể hoạt động dù metadata thiếu; metadata có thể tồn tại nhưng property vẫn cần được đăng ký và bind đúng trong ApplicationContext.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thấy `spring-configuration-metadata.json` sau compile | Processor chưa được cấu hình hoặc class chưa có `@ConfigurationProperties` | Kiểm tra Maven annotationProcessorPaths hoặc Gradle annotationProcessor |
| IDE không autocomplete property | File metadata không có trong JAR/module hoặc IDE chưa đọc lại project | Kiểm tra target/classes và artifact đã publish, reload project |
| Property bind được nhưng không có mô tả | Javadoc không có hoặc class chỉ có compiled bytecode | Thêm Javadoc source hoặc manual metadata |
| Default Duration/List không xuất hiện | Processor không suy ra biểu thức động/collection | Khai báo `defaultValue` trong additional metadata |
| Thêm JSON metadata nhưng ứng dụng không nhận key | Metadata chỉ mô tả cho IDE | Thêm code đọc/bind property thực tế |
| Metadata cũ sau khi đổi property | Build incremental hoặc artifact chưa được rebuild | Chạy clean build và kiểm tra JAR mới |
| Lombok property không được nhận diện đúng | Lombok chạy sau Spring processor | Sắp xếp Lombok trước configuration processor |
| Additional metadata không được merge trên Gradle | `compileJava` chạy trước `processResources` | Thêm task dependency theo hướng dẫn |
| Property bị trùng hoặc mô tả không đúng | Manual metadata override hoặc khai báo lặp | Kiểm tra property name và nguồn metadata |
| IDE không hiển thị provider hint | IDE chưa hỗ trợ provider đó | Kiểm tra khả năng hỗ trợ của IDE; đừng dựa vào hint để validate runtime |

## 16. Checklist khi phát hành starter hoặc auto-configuration

Trước khi publish artifact:

1. Mỗi class properties có prefix rõ ràng và tên key theo kebab-case.
2. Property có Javadoc ngắn, dễ hiểu và không chứa markup phức tạp.
3. Default value được processor trích đúng hoặc bổ sung bằng manual metadata.
4. Nested property được mô tả đúng; class ngoài dùng `@NestedConfigurationProperty` khi cần.
5. Deprecated property có replacement và thời điểm deprecation.
6. Additional metadata chỉ chứa property/hint thực sự cần bổ sung.
7. Processor được khai báo ở compile-time, không trở thành runtime dependency không cần thiết.
8. Nếu có Lombok, annotation processor được sắp xếp đúng thứ tự.
9. Build sạch tạo `META-INF/spring-configuration-metadata.json`.
10. JAR được publish chứa file metadata.
11. Runtime binding được test độc lập với metadata.
12. Consumer smoke test xác nhận người dùng starter có completion và binding hoạt động.

Với thư viện auto-configuration, metadata tốt giúp người dùng khám phá public configuration contract mà không cần mở source code hoặc đoán property từ tên bean.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `spring-boot-configuration-processor` tạo file nào và để làm gì?

**Đáp án:** Tạo `META-INF/spring-configuration-metadata.json` để IDE/công cụ cấu hình hiển thị property, kiểu, mô tả, default và hints.

**Câu 2.** Metadata JSON có tự làm cho một property được bind không?

**Đáp án:** Không. Runtime binding vẫn cần `@ConfigurationProperties` và cơ chế đăng ký/bind phù hợp. Metadata chỉ hỗ trợ công cụ phát triển.

**Câu 3.** Maven nên khai báo processor ở đâu theo cấu hình Spring Boot 3.5 hiện đại?

**Đáp án:** Trong `maven-compiler-plugin`, `annotationProcessorPaths`, dùng phiên bản plugin 3.12.0 trở lên.

**Câu 4.** Gradle khai báo processor ở configuration nào?

**Đáp án:** `annotationProcessor`.

**Câu 5.** Vì sao default của `Duration.ofSeconds(2)` có thể không xuất hiện?

**Đáp án:** Processor chỉ suy ra default khi biểu thức có thể phân tích tĩnh; biểu thức gọi method có thể không được nhận diện. Bổ sung `defaultValue` trong additional metadata.

**Câu 6.** `additional-spring-configuration-metadata.json` được merge vào đâu?

**Đáp án:** Processor merge vào `META-INF/spring-configuration-metadata.json` khi compile. File additional là tùy chọn.

**Câu 7.** `spring-boot-autoconfigure-processor` có thay thế configuration processor không?

**Đáp án:** Không. Nó tạo `spring-autoconfigure-metadata.properties` phục vụ lọc condition auto-configuration sớm, khác mục đích property metadata.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Generating Your Own Metadata by Using the Annotation Processor: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.5 — Metadata Format: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/format.html
- Spring Boot 3.5 — Providing Manual Hints: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/manual-hints.html
- Spring Boot 3.5 — Configuration Metadata overview: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/index.html
- Spring Boot 3.5 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
