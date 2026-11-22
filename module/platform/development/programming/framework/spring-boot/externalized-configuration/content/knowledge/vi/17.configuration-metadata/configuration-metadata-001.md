# Configuration metadata là gì và hỗ trợ IDE ra sao trong Spring Boot 3.3?

## 1. Tổng quan

Khi viết một ứng dụng Spring Boot, bạn có thể gặp các khóa sau:

```properties
spring.application.name=inventory-service
server.port=8081
management.endpoint.health.show-details=when-authorized
```

Trong IDE có hỗ trợ Spring, bạn thường thấy tính năng gợi ý tên khóa, hiển thị kiểu dữ liệu, mô tả, giá trị mặc định hoặc lời cảnh báo khi sử dụng khóa cấu hình đã deprecated. Công cụ không cần khởi động toàn bộ ứng dụng để hiểu những điều này. Thay vào đó, nó có thể đọc **Spring Boot configuration metadata** được đóng gói cùng các thư viện.

Khi tự tạo nhóm cấu hình như:

```yaml
acme:
  mail:
    enabled: true
    retry-count: 3
    timeout: 5s
    channel: email
```

bạn có thể cung cấp metadata cho `acme.mail.*` để IDE gợi ý tương tự các thuộc tính `spring.*` hoặc `server.*`.

Bài học thuộc nhóm **Metadata cấu hình** của chủ đề **Spring Boot Externalized Configuration**, áp dụng với **Spring Boot 3.3.x** và Java **17+**. Nội dung bao gồm:

- Configuration metadata là gì, nằm ở đâu, có cấu trúc ra sao.
- Tại sao metadata không phải nguồn giá trị cấu hình runtime.
- IDE dùng metadata để gợi ý khóa, kiểu, mô tả và giá trị thế nào.
- Cách sinh metadata bằng `spring-boot-configuration-processor`.
- Cấu hình Maven và Gradle.
- Cách khai báo `@ConfigurationProperties`, field Javadoc, record, nested object.
- Cách bổ sung `additional-spring-configuration-metadata.json`.
- `groups`, `properties`, `hints`, providers và deprecation.
- Giới hạn hỗ trợ theo IDE/plugin và cách xử lý khi metadata không được nhận.
- Phương pháp kiểm tra đầu ra build và phân biệt lỗi tooling với lỗi Binder.

## 2. Configuration metadata là gì?

**Configuration metadata** là dữ liệu *mô tả* những thuộc tính cấu hình được một ứng dụng hoặc thư viện Spring Boot công bố. Metadata thường được lưu thành JSON tại:

```text
META-INF/spring-configuration-metadata.json
```

Trong đó có thể có:

```json
{
  "groups": [
    {
      "name": "acme.mail",
      "type": "example.metadata.MailProperties",
      "sourceType": "example.metadata.MailProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.mail.timeout",
      "type": "java.time.Duration",
      "description": "Timeout for one outbound mail request.",
      "defaultValue": "5s"
    }
  ],
  "hints": [
    {
      "name": "acme.mail.channel",
      "values": [
        {"value": "email"},
        {"value": "smtp-api"}
      ]
    }
  ]
}
```

Đây là ví dụ cấu trúc JSON, không phải khẳng định byte-for-byte về một file do annotation processor tạo ra.

Metadata nói: “có nhóm `acme.mail`, có property `acme.mail.timeout` dạng `Duration`, và có các giá trị nên gợi ý cho `acme.mail.channel`.”

Nó **không nói** rằng ứng dụng đang chạy đã thực sự dùng `timeout=5s`.

Một mô hình tư duy:

```text
Mã Java có @ConfigurationProperties
           |
           v
spring-boot-configuration-processor
           |
           v
META-INF/spring-configuration-metadata.json
           |
           v
IDE / công cụ hỗ trợ cấu hình
  - Gợi ý tên khóa
  - Hiển thị mô tả
  - Gợi ý kiểu và giá trị
  - Cảnh báo khóa deprecated
```

Đường đi **runtime** lại khác:

```text
application.yaml / environment / CLI / import
           |
           v
Config Data + PropertySource precedence
           |
           v
Binder + ConversionService + validation
           |
           v
Bean @ConfigurationProperties
           |
           v
Service sử dụng giá trị có hiệu lực
```

Đừng nhầm hai sơ đồ.

## 3. Phân biệt metadata, file cấu hình và model Java

| Thành phần | Nằm ở đâu? | Mục đích |
| --- | --- | --- |
| `application.properties` | Trong classpath hoặc vị trí cấu hình khác | Cung cấp giá trị thực tế |
| `application.yaml` | Trong classpath hoặc vị trí cấu hình khác | Cung cấp giá trị thực tế |
| Biến môi trường | Môi trường của tiến trình Java | Một nguồn giá trị có thứ tự ưu tiên riêng |
| `@ConfigurationProperties` | Mã Java | Mô hình liên kết nhóm cấu hình có kiểu |
| `spring-configuration-metadata.json` | `META-INF` trong output/JAR | Mô tả thuộc tính cho tooling |
| `additional-spring-configuration-metadata.json` | `src/main/resources/META-INF` | Bổ sung/chỉnh metadata lúc build |
| `@Validated` / Bean Validation | Mã Java | Ràng buộc dữ liệu khi binding/validation |

Ví dụ:

```properties
acme.mail.timeout=3s
```

trong file chung, nhưng biến môi trường có:

```text
ACME_MAIL_TIMEOUT=10s
```

Metadata có thể mô tả default `"5s"`. Khi Spring Boot chạy, giá trị có hiệu lực có thể là `10s` từ biến môi trường. Metadata không ghi đè biến môi trường và không tự thêm một `PropertySource` mới.

**Metadata là bản mô tả hợp đồng cấu hình cho công cụ, không phải tệp chứa các giá trị được ưu tiên khi khởi động.**

## 4. IDE nhận được lợi ích gì?

Một IDE hoặc extension có hỗ trợ metadata Spring Boot có thể thực hiện những chức năng sau:

1. **Auto-completion tên khóa:** sau khi gõ `acme.mail.`, nó có thể gợi ý `enabled`, `timeout`, `retry-count`, `channel`.
2. **Mô tả ngữ cảnh:** di chuột lên `timeout` có thể thấy giải thích từ metadata.
3. **Kiểu dữ liệu:** biết `timeout` là `Duration` và `retry-count` là số nguyên.
4. **Giá trị gợi ý:** với enum hoặc `hints`, IDE có thể đề xuất các lựa chọn như `email`, `smtp-api`.
5. **Default value:** IDE có thể hiển thị giá trị mặc định mà metadata mô tả.
6. **Deprecated warning:** khi gõ khóa cũ, IDE có thể thông báo khóa thay thế.
7. **Điều hướng tới source:** trường `sourceType` có thể giúp công cụ liên kết property với class Java.
8. **Cảnh báo khóa không biết:** tùy plugin, IDE có thể phát hiện một số lỗi đánh máy.

Tuy nhiên, metadata không ép buộc mọi IDE phải hiển thị tính năng giống nhau. Khả năng hỗ trợ phụ thuộc editor, extension, phiên bản, cấu hình project và classpath.

Nếu một editor thuần văn bản không hiện completion, không thể suy ra file metadata bị sai. Ngược lại, IDE hiện completion cũng không chứng minh ứng dụng runtime đang đọc được khóa.

## 5. Ba mảng chính: `groups`, `properties`, `hints`

Trong Spring Boot 3.3, metadata JSON thường có ba vùng:

```json
{
  "groups": [],
  "properties": [],
  "hints": []
}
```

### `groups`

Group gom các property có chung ngữ cảnh. Ví dụ:

```json
{
  "name": "acme.mail",
  "type": "example.metadata.MailProperties",
  "sourceType": "example.metadata.MailProperties"
}
```

Group `acme.mail` không nhất thiết tự có giá trị. Nó là không gian tên cho `acme.mail.timeout`, `acme.mail.enabled`, v.v.

Các thuộc tính của group có thể chứa tên, kiểu, class nguồn hoặc method nguồn. Một số group lồng có thể được sinh ra khi processor nhận diện object lồng trong model Java.

### `properties`

Mỗi phần tử thể hiện một property cụ thể:

```json
{
  "name": "acme.mail.retry-count",
  "type": "java.lang.Integer",
  "description": "Maximum number of retries.",
  "sourceType": "example.metadata.MailProperties",
  "defaultValue": 3
}
```

Ý nghĩa các trường thông dụng:

| Trường | Ý nghĩa |
| --- | --- |
| `name` | Tên đầy đủ dạng canonical, ví dụ `acme.mail.retry-count` |
| `type` | Kiểu Java mà thuộc tính tương ứng |
| `description` | Mô tả ngắn cho người cấu hình |
| `sourceType` | Class Java góp phần khai báo property |
| `defaultValue` | Giá trị mặc định được mô tả nếu có thể xác định |
| `deprecation` | Thông tin ngừng khuyến nghị dùng thuộc tính |

Không bắt buộc mọi property phải có đủ mọi trường. Nếu processor không xác định được description hoặc defaultValue, dữ liệu có thể được bỏ qua.

### `hints`

Hint giúp công cụ hỗ trợ nhập giá trị:

```json
{
  "name": "acme.mail.channel",
  "values": [
    {
      "value": "email",
      "description": "Send messages using email."
    },
    {
      "value": "smtp-api",
      "description": "Send messages through the SMTP API."
    }
  ]
}
```

`hints.values` đề xuất giá trị; `hints.providers` có thể gợi ý nguồn nội dung động, ví dụ tên class hay profile.

**HINT KHÔNG ĐỒNG NGHĨA VALIDATION.** Nếu trường Java là `String`, giá trị ngoài danh sách vẫn có thể được Binder nhận nếu không có enum, validation hoặc logic chặn riêng.

## 6. Metadata đến từ đâu?

Các starter chính thức của Spring Boot đã mang metadata cho nhiều thuộc tính cấu hình. Khi ứng dụng phụ thuộc vào starter, IDE có thể đọc metadata của dependency JAR.

Còn với property riêng của ứng dụng, cách thông dụng là:

```java
@ConfigurationProperties(prefix = "acme.mail")
public class MailProperties {
    // ...
}
```

và dùng annotation processor:

```text
org.springframework.boot:spring-boot-configuration-processor
```

Processor chạy lúc **biên dịch Java**. Nó không phải Spring bean chạy trong ApplicationContext khi ứng dụng khởi động.

```text
Compile
  |
  +-- javac đọc class có @ConfigurationProperties
  +-- Annotation processor phân tích metadata
  |
  v
META-INF/spring-configuration-metadata.json
```

Một dự án có thể **chạy runtime bình thường mà không có processor**, nhưng IDE có thể không nhận metadata của các property tự định nghĩa. Một thư viện cũng có thể mang metadata tốt nhưng runtime thiếu auto-configuration hoặc bean registration, khi đó IDE gợi ý khóa mà ứng dụng chưa chắc sử dụng.

## 7. Ví dụ `@ConfigurationProperties` với JavaBean

Ta xây dựng nhóm `acme.mail` để minh họa.

Tạo `src/main/java/example/metadata/MailProperties.java`:

```java
package example.metadata;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.mail")
public class MailProperties {

    // Whether outbound mail is enabled.
    private boolean enabled = true;

    // Number of retries after a failed send.
    private int retryCount = 3;

    // Timeout for one outbound mail request.
    private Duration timeout = Duration.ofSeconds(5);

    // Transport name for mail delivery.
    private String channel = "email";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public String getChannel() {
        return channel;
    }

    public void setChannel(String channel) {
        this.channel = channel;
    }
}
```

Ví dụ sử dụng comment một dòng để giữ code gọn. **Khi muốn processor tự lấy description, nên viết JavaDoc thật trên field**, chẳng hạn khối JavaDoc bắt đầu bằng dấu sao kép và kết thúc đúng cú pháp Java. Trong dự án thực tế, mô tả nên giải thích ý nghĩa nghiệp vụ, không chỉ lặp lại tên field.

Các property canonical tương ứng:

```text
acme.mail.enabled
acme.mail.retry-count
acme.mail.timeout
acme.mail.channel
```

Dữ liệu YAML:

```yaml
acme:
  mail:
    enabled: true
    retry-count: 4
    timeout: 3s
    channel: email
```

`retryCount` trong Java ánh xạ tới `retry-count` trong cấu hình nhờ relaxed binding của Spring Boot.

### Đăng ký bean runtime

```java
package example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MetadataApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` giúp đăng ký kiểu `MailProperties` trong application context. Nó phục vụ **runtime**; annotation processor phục vụ **metadata khi biên dịch**.

## 8. Cấu hình Maven

Với một project Maven dùng Spring Boot 3.3.x và dependency management phù hợp:

```xml
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
```

`optional=true` thể hiện processor phục vụ biên dịch và không nên tự động thành dependency transitively bắt buộc đối với những project tiêu thụ thư viện.

Một số build dùng `maven-compiler-plugin` và annotation processor path tường minh. Khi đó cần đảm bảo processor thực sự được compiler chạy, không chỉ xuất hiện như một dependency chưa được xử lý.

Chạy:

```bash
./mvnw clean compile
```

Khi biên dịch thành công và annotation processor chạy đúng, output thông dụng:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Một số build có cấu hình output đặc biệt; hãy kiểm tra artifact thật thay vì dựa tuyệt đối vào đường dẫn mặc định.

### Maven với nhiều processor

Nếu project cũng dùng Lombok hoặc MapStruct, phải đảm bảo cấu hình annotation processing tương thích. Các processor khác có thể ảnh hưởng thứ tự hoặc nguồn Java được xử lý. Nếu metadata thiếu, hãy xem compiler configuration và output thay vì chỉ thêm dependency nhiều lần.

## 9. Cấu hình Gradle

Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
```

`annotationProcessor` nói rõ dependency tham gia Java annotation processing. Không nên cho rằng đưa processor vào `implementation` là cấu hình đúng nhất để Gradle chạy nó.

Chạy:

```bash
./gradlew clean build
```

Metadata có thể được tạo trong output của `compileJava` và được đưa vào artifact đã đóng gói. Đường dẫn chính xác phụ thuộc source sets, Gradle version và cấu hình build.

### Gradle với manual metadata

Nếu bạn tạo:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

processor phải nhận file này lúc biên dịch. Spring Boot 3.3 hướng dẫn đưa task `processResources` thành một input của `compileJava`:

```groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
```

Với Kotlin DSL, có thể biểu diễn tương đương:

```kotlin
tasks.named<JavaCompile>("compileJava") {
    inputs.files(tasks.named("processResources"))
}
```

Nếu dùng Kotlin DSL, đảm bảo type `JavaCompile` được resolve trong script (import thích hợp nếu cần). Cấu hình này liên quan **thời điểm processor nhìn thấy file bổ sung**, không làm thay đổi ưu tiên của runtime configuration.

## 10. File được sinh và file do người phát triển quản lý

Cần phân biệt:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

là **file nguồn** do bạn có thể tạo và sửa.

Trong khi:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

hoặc file tương ứng tại output Gradle là **file sinh** bởi annotation processor.

Một cây thư mục ví dụ:

```text
my-service/
├── pom.xml
├── src/main/java/example/metadata/
│   ├── MetadataApplication.java
│   └── MailProperties.java
└── src/main/resources/
    ├── application.yaml
    └── META-INF/
        └── additional-spring-configuration-metadata.json

Sau build:
target/classes/
├── application.yaml
└── META-INF/
    ├── additional-spring-configuration-metadata.json
    └── spring-configuration-metadata.json
```

Không chỉnh trực tiếp file được sinh trong `target/classes` rồi mong giữ mãi: `clean` và build lại có thể xóa thay đổi đó.

Muốn điều chỉnh metadata, sửa **Java source, JavaDoc, annotation hoặc file bổ sung** rồi biên dịch lại.

## 11. JavaDoc giúp tooltip hữu ích hơn

Một property chỉ có tên `timeout` thường chưa đủ cho người sử dụng cấu hình.

Một mô tả có ích:

> Maximum time allowed for one outbound mail request.

Nó giải thích đối tượng được đo, không chỉ nói “timeout”.

Trong Java source, bạn có thể đặt JavaDoc ở field, ví dụ mô tả dưới đây là ý tưởng về văn bản JavaDoc:

```java
// JavaDoc field trong source thật:
// Maximum time allowed for one outbound mail request.
// The value is a Duration, for example 5s or 250ms.
private Duration timeout = Duration.ofSeconds(5);
```

Để annotation processor trích xuất vào metadata, dùng **JavaDoc block hợp lệ** trong dự án thật, không chỉ comment `//` như đoạn minh họa trên.

Các mô tả nên:

- Ngắn, có chủ ngữ và giải thích giá trị điều khiển gì.
- Nêu đơn vị khi quan trọng.
- Nêu phạm vi áp dụng, ví dụ mỗi request hay toàn lô.
- Làm rõ mối liên hệ với profile hoặc tính năng bật/tắt.
- Tránh lặp lại tên thuộc tính một cách vô nghĩa.
- Không chứa secret hoặc thông tin nội bộ nhạy cảm.

Nếu không có mô tả, IDE vẫn có thể gợi ý tên khóa, nhưng trải nghiệm tự tìm hiểu qua tooltip bị hạn chế.

## 12. Record và constructor binding

Với Java 17, model cấu hình có thể là record:

```java
package example.metadata;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme.client")
public record ClientProperties(
        String endpoint,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("3") int retryCount
) {
}
```

Các thuộc tính tương ứng:

```text
acme.client.endpoint
acme.client.timeout
acme.client.retry-count
```

Spring Boot 3.3 có thể dùng constructor binding cho record với constructor canonical phù hợp. Metadata processor mô tả kiểu thuộc tính dựa trên khai báo được hỗ trợ.

`@DefaultValue` trên record component là một nguồn thông tin mặc định rõ ràng cho Binder. Tuy nhiên, **metadata mặc định không phải cơ chế cấp giá trị runtime**. Runtime default được quyết định bởi Binder, code và các nguồn cấu hình; metadata mô tả chúng cho tooling.

Đừng giả định processor có thể chạy mọi logic tính default, chẳng hạn:

```java
private Duration timeout = createTimeoutFromEnvironment();
```

Annotation processor phân tích source khi compile; nó không khởi động toàn bộ ứng dụng và không biết được mọi giá trị tính động.

## 13. Nested configuration properties

Xét cấu hình:

```yaml
acme:
  client:
    endpoint: https://api.example.test
    security:
      enabled: true
      mode: strict
```

Một lớp JavaBean có object nested:

```java
@ConfigurationProperties(prefix = "acme.client")
public class ClientProperties {

    private URI endpoint;
    private final Security security = new Security();

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Security getSecurity() {
        return security;
    }

    public static class Security {
        private boolean enabled;
        private String mode = "strict";

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getMode() {
            return mode;
        }

        public void setMode(String mode) {
            this.mode = mode;
        }
    }
}
```

Các import tiêu biểu:

```java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
```

Processor có thể mô tả prefix nested `acme.client.security` và các khóa con `acme.client.security.enabled`, `acme.client.security.mode`.

### `@NestedConfigurationProperty`

Khi object nested là một class riêng và processor không tự nhận diện rõ là nested property, có thể dùng:

```java
import org.springframework.boot.context.properties.NestedConfigurationProperty;
```

Ví dụ:

```java
@ConfigurationProperties(prefix = "acme.client")
public class ClientProperties {

    @NestedConfigurationProperty
    private SecurityOptions security = new SecurityOptions();

    public SecurityOptions getSecurity() {
        return security;
    }

    public void setSecurity(SecurityOptions security) {
        this.security = security;
    }
}
```

Trong đó `SecurityOptions` là một kiểu riêng có các thuộc tính con.

`@NestedConfigurationProperty` chủ yếu có ý nghĩa với **cấu trúc metadata được sinh**, không phải một annotation tự biến đổi quy tắc runtime binding.

### `List` và `Map`

Với:

```java
private List<String> recipients;
private Map<String, Integer> quotas;
```

metadata thường mô tả **thuộc tính collection**, không sinh một property cố định cho mọi chỉ số hoặc key dữ liệu có thể thêm về sau.

IDE có thể biết `acme.mail.recipients` là `List<String>`, nhưng không nhất thiết biết runtime sẽ có bao nhiêu phần tử.

## 14. Metadata thủ công: khi annotation processor không đủ

Đặt file tại:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Dùng khi cần:

- Mô tả khóa không được khai báo qua `@ConfigurationProperties`.
- Bổ sung description hoặc defaultValue cho những trường hợp processor không suy ra được.
- Bổ sung tập giá trị gợi ý cho một property `String`.
- Thêm provider để IDE gợi ý tên class, bean, resource hoặc profile.
- Bổ sung thông tin deprecated và replacement.
- Mô tả một key động hoặc key của `Map`.

Ví dụ:

```json
{
  "properties": [
    {
      "name": "acme.mail.channel",
      "type": "java.lang.String",
      "description": "Transport used to send mail notifications.",
      "defaultValue": "email"
    }
  ],
  "hints": [
    {
      "name": "acme.mail.channel",
      "values": [
        {"value": "email", "description": "Send through email."},
        {"value": "smtp-api", "description": "Use the SMTP API gateway."}
      ]
    }
  ]
}
```

Nếu annotation processor đã phát hiện property tự động, metadata bổ sung có thể override những thông tin mô tả/default/deprecation được chỉ định theo quy tắc merging của Spring Boot.

Nếu file bổ sung khai một property **không có code đọc giá trị**, IDE vẫn có thể đề xuất khóa đó; nhưng không có nghĩa ứng dụng tự nhiên có chức năng mới. Metadata không làm runtime sử dụng một key mà code chưa hỗ trợ.

## 15. `hints.values` và kiểu enum

Giả sử kênh thông báo chỉ gồm:

```text
EMAIL
SMS
PUSH
```

Một model có thể dùng enum:

```java
public enum Channel {
    EMAIL, SMS, PUSH
}

@ConfigurationProperties(prefix = "acme.notify")
public record NotifyProperties(Channel channel) {}
```

Enum có lợi vì:

- Hạn chế tập trạng thái trong Java.
- Binder có thể thực hiện chuyển đổi enum.
- IDE có thể gợi ý các enum constants khi metadata và plugin hỗ trợ.
- Không cần viết danh sách hints thủ công chỉ để mô tả đúng các giá trị của enum.

Nếu doanh nghiệp cho phép plugin bên ngoài bổ sung tên channel động, `String` cộng hints có thể phù hợp hơn:

```json
{
  "hints": [
    {
      "name": "acme.notify.channel",
      "values": [
        {"value": "email"},
        {"value": "sms"},
        {"value": "push"}
      ]
    }
  ]
}
```

**HINT LÀ GỢI Ý** — không phải giới hạn runtime. Với property `String`, một giá trị khác vẫn có thể bind thành công trừ khi ứng dụng có validation riêng.

### Provider `"any"`

Khi muốn IDE gợi ý các giá trị phổ biến nhưng vẫn cho phép nhập khác:

```json
{
  "hints": [
    {
      "name": "acme.notify.channel",
      "values": [
        {"value": "email"},
        {"value": "sms"}
      ],
      "providers": [
        {"name": "any"}
      ]
    }
  ]
}
```

`any` là một provider chính thức cho phép giá trị khác với danh sách gợi ý. Nó không thay đổi validation runtime.

## 16. Value providers theo ngữ cảnh

Ngoài `values`, Spring Boot metadata cho phép dùng `providers`.

| Provider | Hướng gợi ý |
| --- | --- |
| `any` | Không giới hạn ở các giá trị được liệt kê |
| `class-reference` | Tên class trên classpath, có thể giới hạn theo interface/base type |
| `handle-as` | Xử lý đầu vào như một kiểu Java khác |
| `logger-name` | Tên logger và nhóm logger |
| `spring-bean-reference` | Tên Spring bean |
| `spring-profile-name` | Tên Spring profile |

Ví dụ gợi ý class:

```json
{
  "hints": [
    {
      "name": "acme.worker.strategy-class",
      "providers": [
        {
          "name": "class-reference",
          "parameters": {
            "target": "example.worker.WorkStrategy"
          }
        }
      ]
    }
  ]
}
```

Nếu IDE có hỗ trợ, nó có thể tìm class tương thích với `WorkStrategy` trong project.

### `handle-as`

Một property có type Java `String` nhưng ngữ nghĩa là đường dẫn resource:

```properties
acme.notify.template=classpath:/mail/welcome.txt
```

Metadata:

```json
{
  "hints": [
    {
      "name": "acme.notify.template",
      "providers": [
        {
          "name": "handle-as",
          "parameters": {
            "target": "org.springframework.core.io.Resource"
          }
        }
      ]
    }
  ]
}
```

IDE có thể cung cấp hỗ trợ như khi property là `Resource`. Điều này **không làm field Java thật tự đổi từ `String` sang `Resource`**.

Provider còn phụ thuộc hỗ trợ của IDE. Không nên suy ra JSON sai chỉ vì một plugin không hiện gợi ý `spring-bean-reference`.

## 17. Gợi ý cho key và value của Map

Giả sử cấu hình:

```yaml
acme:
  labels:
    team: order
    environment: staging
```

Java:

```java
@ConfigurationProperties(prefix = "acme")
public record AcmeProperties(Map<String, String> labels) {}
```

Với `Map`, metadata cho phép dùng hai hậu tố đặc biệt:

```json
{
  "hints": [
    {
      "name": "acme.labels.keys",
      "values": [
        {"value": "team"},
        {"value": "environment"},
        {"value": "cost-center"}
      ]
    },
    {
      "name": "acme.labels.values",
      "values": [
        {"value": "internal"},
        {"value": "public"}
      ],
      "providers": [
        {"name": "any"}
      ]
    }
  ]
}
```

`.keys` và `.values` nói đến thành phần Map, **không phải hai runtime property riêng** mà code buộc phải bind.

Một `Map<String, String>` có thể có nhiều entry không biết trước. Metadata không tự quét dữ liệu runtime để liệt kê tất cả key tồn tại trong mọi môi trường.

## 18. Deprecated property và gợi ý migration

Một ứng dụng đổi tên:

```text
acme.notify.sender-name
```

thành:

```text
acme.notify.from-name
```

Metadata có thể cung cấp thông tin deprecated:

```json
{
  "name": "acme.notify.sender-name",
  "type": "java.lang.String",
  "deprecation": {
    "level": "warning",
    "reason": "Use the clearer from-name property.",
    "replacement": "acme.notify.from-name",
    "since": "2.1"
  }
}
```

Các trường:

- `level`: `warning` hoặc `error`.
- `reason`: lý do không còn khuyến nghị.
- `replacement`: khóa nên chuyển sang.
- `since`: phiên bản bắt đầu deprecated.

`warning` thường dùng khi khóa cũ vẫn được xử lý nhưng nên thay. `error` phù hợp khi khóa không còn được quản lý theo mô tả metadata.

### `@DeprecatedConfigurationProperty`

Spring Boot 3.3 có:

```java
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;
```

Với một JavaBean getter đã deprecated:

```java
@Deprecated
@DeprecatedConfigurationProperty(
        reason = "Use acme.notify.from-name instead.",
        replacement = "acme.notify.from-name"
)
public String getSenderName() {
    return fromName;
}
```

Annotation hỗ trợ processor sinh metadata deprecated. Nó **không tự tạo alias runtime** hay tự chuyển một giá trị cấu hình cũ thành mới. Code vẫn phải quyết định có hỗ trợ khóa cũ và quy tắc ưu tiên khi cả hai xuất hiện hay không.

Khi property cũ đã bị xóa khỏi code, có thể giữ một entry deprecated `"level": "error"` trong manual metadata để IDE tiếp tục nhắc người dùng rằng khóa này không còn hiệu lực.

## 19. `defaultValue` không phải default runtime

Một metadata property có:

```json
{
  "name": "acme.notify.timeout",
  "type": "java.time.Duration",
  "defaultValue": "5s"
}
```

không có nghĩa Spring Boot sẽ tự cấp `5s` chỉ vì file JSON có trường đó.

Default runtime có thể đến từ:

- Field initializer của JavaBean.
- `@DefaultValue` trong constructor binding.
- Cấu hình chung trong file.
- Một PropertySource khác.
- Logic ứng dụng được thiết kế rõ ràng.

Trong metadata, `defaultValue` là **dữ liệu mô tả cho công cụ**. Nếu mô tả này sai với hành vi runtime, IDE có thể hướng dẫn người dùng sai.

Một annotation processor cũng không thể suy luận mọi default được tính động:

```java
private Duration timeout = determineTimeoutAtRuntime();
```

Nó không gọi hàm này trong quá trình compile để tìm giá trị thật.

### Metadata và `@DefaultValue`

Record:

```java
@ConfigurationProperties(prefix = "acme.retry")
public record RetryProperties(
        @DefaultValue("3") int attempts,
        @DefaultValue("250ms") Duration pause
) {}
```

`@DefaultValue` là cách biểu đạt default cho Binder constructor binding. Processor có thể sử dụng thông tin này khi mô tả thuộc tính, nhưng cần phân biệt hai vai trò: một bên tạo dữ liệu khi bind, một bên mô tả cho tooling.

## 20. Metadata không thay thế Bean Validation

Có metadata cho:

```text
acme.notify.retry-count: Integer
```

không chứng minh giá trị sau hợp lệ:

```properties
acme.notify.retry-count=-100
```

`-100` vẫn là số nguyên. Nếu nghiệp vụ không cho retry âm, model có thể dùng:

```java
@Min(0)
private int retryCount;
```

và khai báo `@Validated` trên lớp cấu hình, cùng implementation Jakarta Bean Validation phù hợp.

Tương tự:

```properties
acme.notify.timeout=-5s
```

có thể chuyển đổi thành `Duration` âm. Cần validation nếu không cho timeout âm.

Phân biệt:

| Cơ chế | Vai trò |
| --- | --- |
| Metadata | Thông tin cho IDE và tooling |
| Binder | Ánh xạ tên và chuyển dữ liệu thành kiểu Java |
| Bean Validation | Kiểm tra constraint đã khai báo |
| Nghiệp vụ | Kiểm tra quan hệ, chính sách và điều kiện vận hành |

IDE có thể cảnh báo sớm, nhưng **không thay thế kiểm tra runtime** và không đảm bảo mọi giá trị người dùng nhập đều hợp lệ.

## 21. Metadata cho thuộc tính chỉ dùng qua `@Value`

Ví dụ:

```java
@Service
public class GreetingService {

    private final String text;

    public GreetingService(
            @Value("${acme.greeting.text:Hello}") String text
    ) {
        this.text = text;
    }
}
```

Đừng mặc định `spring-boot-configuration-processor` sẽ tự sinh một metadata model đầy đủ cho mọi `@Value` trong ứng dụng.

Nếu property không có `@ConfigurationProperties`, có thể mô tả thủ công:

```json
{
  "properties": [
    {
      "name": "acme.greeting.text",
      "type": "java.lang.String",
      "description": "Greeting shown on the landing screen."
    }
  ]
}
```

Nếu nhiều thuộc tính có cùng prefix, thường nên gom chúng thành một `@ConfigurationProperties` hơn là duy trì hàng loạt `@Value` và entry JSON riêng.

Khi dùng `@Value`, Spring Boot khuyến nghị viết placeholder theo tên canonical kebab-case để tận dụng mức hỗ trợ relaxed lookup hiện có:

```java
@Value("${acme.notify.retry-count:3}")
```

thay vì dùng các biến thể tùy ý của camelCase.

## 22. Thực hành hoàn chỉnh với Maven

### Bước 1 — chuẩn bị dependencies

Tạo dự án Spring Boot 3.3.x, Java 17, có `spring-boot-starter`, thêm processor:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Project cần dependency management/parent phù hợp để đồng bộ phiên bản.

### Bước 2 — tạo model

`src/main/java/example/metadata/MailProperties.java` như ví dụ JavaBean ở mục 7, có prefix `acme.mail`.

### Bước 3 — tạo application

`MetadataApplication.java` với:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class MetadataApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }
}
```

### Bước 4 — tạo `application.properties`

```properties
spring.application.name=metadata-demo

acme.mail.enabled=true
acme.mail.retry-count=2
acme.mail.timeout=3s
acme.mail.channel=email
```

### Bước 5 — tạo hints

Tại:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

nội dung:

```json
{
  "hints": [
    {
      "name": "acme.mail.channel",
      "values": [
        {
          "value": "email",
          "description": "Use email delivery."
        },
        {
          "value": "smtp-api",
          "description": "Use the configured SMTP API gateway."
        }
      ]
    }
  ]
}
```

### Bước 6 — build

```bash
./mvnw clean compile
```

### Bước 7 — kiểm tra metadata sinh

Mở:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Một số phần có thể xuất hiện:

```text
group acme.mail
property acme.mail.enabled
property acme.mail.retry-count
property acme.mail.timeout
property acme.mail.channel
hint acme.mail.channel
```

Tổ chức JSON thật có thể khác ở thứ tự và các trường tùy chọn.

### Bước 8 — thử trong IDE

Mở `application.properties` và gõ:

```text
acme.mail.
```

Nếu IDE có Spring Boot metadata support và đã index project, nó có thể gợi ý các property của nhóm trên. Khi nhập `channel`, nó có thể gợi ý `email` và `smtp-api`.

Mở `application.yaml` rồi gõ:

```yaml
acme:
  mail:
```

IDE có thể gợi ý các tên con theo cấu trúc YAML. Cùng một metadata phục vụ cả YAML lẫn `.properties`, không cần tạo hai file metadata khác nhau.

### Bước 9 — khởi động ứng dụng

```bash
./mvnw spring-boot:run
```

Bean cấu hình được tạo bởi cơ chế runtime `@ConfigurationPropertiesScan` và Binder. Metadata hỗ trợ editor, không phải thành phần quyết định giá trị cấu hình.

## 23. Kiểm tra JAR đầu ra

Khi phát hành thư viện hoặc starter, metadata nên nằm trong artifact JAR để IDE của ứng dụng tiêu thụ cũng dùng được.

Dùng JDK:

```bash
jar tf target/ten-jar-thuc-te.jar
```

Tìm `spring-configuration-metadata.json`.

Một JAR thư viện có thể lưu trực tiếp:

```text
META-INF/spring-configuration-metadata.json
```

Một Spring Boot executable JAR có thể đặt resource ứng dụng trong cấu trúc như:

```text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Vị trí phụ thuộc kiểu đóng gói. Hãy kiểm tra artifact thật, đừng khẳng định mọi JAR Spring có cùng đường dẫn bên trong archive.

Nếu bạn phát hành một starter, hãy kiểm tra JAR thư viện mà project tiêu thụ sẽ phụ thuộc vào, không chỉ output `target/classes` trên máy phát triển.

## 24. Khi IDE không gợi ý: phân tách ba tầng

### Tầng 1 — annotation processing

Câu hỏi:

- Có dependency processor chưa?
- Maven/Gradle có chạy annotation processing không?
- Model có `@ConfigurationProperties` không?
- Có compiler config làm processor bị bỏ qua không?
- Build output có file metadata không?

Nếu chưa có file, đây là vấn đề **generation**.

### Tầng 2 — IDE / project index

Nếu file metadata tồn tại:

- IDE đã mở đúng module và nhập dependencies chưa?
- Spring Boot plugin/extension có được cài và bật không?
- Project đã reload sau khi build chưa?
- IDE có dùng output/annotation processing mới không?
- IDE có hỗ trợ `hints.values` hoặc provider cụ thể đó không?

Nếu chỉ một editor không gợi ý, không được kết luận runtime binder sai.

### Tầng 3 — runtime configuration

Nếu IDE gợi ý key nhưng bean có giá trị không mong đợi:

- Profile nào đang hoạt động?
- Có tệp ngoài JAR hoặc `spring.config.import` không?
- Có biến môi trường hoặc đối số CLI ghi đè không?
- Có typo trong property thật không?
- Bean `@ConfigurationProperties` đã đăng ký chưa?
- Kiểu có chuyển đổi được không?
- Validation có từ chối không?

Không sửa lỗi runtime bằng cách thêm `hint` nếu root cause là nguồn cấu hình hoặc binding.

## 25. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không có file metadata sinh | Chưa chạy processor | Cấu hình processor trong Maven/Gradle |
| Có processor nhưng không có property mới | Class không được phát hiện hoặc cấu trúc không được phân tích | Kiểm tra `@ConfigurationProperties`, accessors, source |
| Hints không xuất hiện | File additional ở sai vị trí | Kiểm tra `src/main/resources/META-INF/` |
| Gradle không merge additional | Processor chạy trước khi resources sẵn sàng | Cấu hình task input/processResources theo hướng dẫn |
| Description rỗng | Thiếu JavaDoc được processor nhận diện | Viết JavaDoc hoặc bổ sung thủ công |
| DefaultValue không khớp | Giá trị runtime được tính động hoặc nguồn khác | Không dùng metadata làm bằng chứng runtime |
| JavaBean nested không được mô tả | Kiểu nested không được processor nhận diện | Xem `@NestedConfigurationProperty` |
| IDE không gợi ý dù JSON có | Plugin chưa hỗ trợ hoặc chưa index | Reload project, kiểm tra extension |
| Gợi ý sai các khóa đã bỏ | Metadata cũ trong cache hoặc dependency cũ | Rebuild/reload và kiểm tra artifact |
| Giá trị ngoài hints vẫn bind | Hints không phải validator | Dùng enum/Bean Validation |
| Key deprecated không hiện warning | Metadata thiếu `deprecation` hoặc IDE không hỗ trợ | Bổ sung thông tin migration |
| `@Value` property không có metadata | Processor chủ yếu phục vụ config properties có kiểu | Dùng manual metadata hoặc model `@ConfigurationProperties` |
| Runtime chạy nhưng IDE báo unknown | Metadata chưa đủ, binding linh hoạt hơn tooling | Kiểm tra file metadata và source |
| IDE gợi ý nhưng app bỏ qua | Key có trong manual metadata nhưng code không đọc | Kiểm tra runtime consumer |
| Chỉnh file trong `target` rồi mất | File sinh bị build ghi lại | Sửa source hoặc additional metadata |
| Cần gợi ý Map key | Metadata không biết tất cả key động | Dùng hint `.keys` |
| Trùng metadata trong nhiều module | Nhiều module cùng prefix | Kiểm tra ownership và phiên bản dependencies |

## 26. Metadata trong thư viện dùng chung

Ví dụ dự án viết starter:

```text
acme-notification-spring-boot-starter
```

Nó công bố nhóm:

```java
@ConfigurationProperties(prefix = "acme.notifications")
public class NotificationsProperties {
    // ...
}
```

Nếu JAR starter chứa metadata, ứng dụng tiêu thụ có thể nhận gợi ý `acme.notifications.*` trong IDE mà không cần mở source của thư viện.

Luồng:

```text
Mã nguồn thư viện
  |
  +-- @ConfigurationProperties
  +-- JavaDoc
  +-- Additional hints nếu cần
  |
  v
Build + annotation processor
  |
  v
JAR có metadata
  |
  v
Ứng dụng phụ thuộc vào JAR
  |
  v
IDE đọc metadata dependency
  |
  v
Code completion cho acme.notifications.*
```

Nhưng **metadata không thay thế auto-configuration**: thư viện vẫn phải đăng ký bean, import các thành phần cần thiết, có điều kiện kích hoạt phù hợp nếu cần, và sử dụng đúng cơ chế Spring Boot runtime.

Metadata là một phần của trải nghiệm người dùng **đối với API cấu hình**, không phải toàn bộ chức năng thư viện.

## 27. Metadata deprecated không tự làm migration

Giả sử API cũ dùng:

```properties
acme.notify.sender-name=Service
```

API mới dùng:

```properties
acme.notify.from-name=Service
```

Metadata có thể thông báo:

```json
{
  "name": "acme.notify.sender-name",
  "deprecation": {
    "level": "warning",
    "replacement": "acme.notify.from-name"
  }
}
```

Nhưng không phải vì `replacement` có trong JSON mà Spring Boot Binder sẽ tự đồng bộ hai khóa.

Nếu thư viện muốn tiếp tục hỗ trợ khóa cũ, code phải giữ xử lý tương ứng. Nếu muốn ưu tiên khóa mới khi cả hai có mặt, cũng cần quy tắc cụ thể trong runtime code hoặc cấu hình.

Khi thật sự loại bỏ khóa cũ, metadata có thể giữ một lời cảnh báo `"error"` thủ công để hỗ trợ editor, nhưng **không hồi sinh hành vi runtime** đã xóa.

## 28. Dùng metadata trong quy trình nâng cấp Spring Boot

Khi cập nhật Spring Boot hoặc một starter, metadata có thể thay đổi:

- Có key mới.
- Key cũ đổi tên.
- Default được điều chỉnh.
- Key trở thành deprecated.
- Hints hoặc sourceType thay đổi.

IDE có thể khai thác metadata từ phiên bản dependency mới để giúp người dùng cập nhật `application.yaml`. Nhưng nên đọc release notes và kiểm thử ứng dụng; metadata không bảo đảm phát hiện mọi thay đổi hành vi.

Với nhánh Spring Boot 3.3, các class và annotation processor nên được quản lý đồng bộ phiên bản. Không trộn tùy tiện Spring Boot 3.3 với processor/auto-configuration từ nhánh khác rồi kỳ vọng metadata nhất quán.

## 29. Bài tập tự kiểm tra

### Bài 1 — metadata và giá trị cuối

Metadata ghi `defaultValue=3` cho `acme.mail.retry-count`. Lệnh chạy cấp:

```bash
java -jar app.jar --acme.mail.retry-count=9
```

**Hỏi:** Giá trị trong bean nhất thiết phải là 3 không?

**Đáp án:** Không. Đối số CLI có thể cung cấp 9 theo thứ tự ưu tiên runtime. Metadata chỉ mô tả default.

### Bài 2 — processor

Class:

```java
@ConfigurationProperties(prefix = "acme.cache")
public record CacheProperties(int maxSize) {}
```

**Hỏi:** Thành phần nào có thể sinh `spring-configuration-metadata.json`?

**Đáp án:** `spring-boot-configuration-processor` được kích hoạt trong Java compilation.

### Bài 3 — metadata không thay `@ConfigurationPropertiesScan`

IDE gợi ý khóa `acme.cache.max-size`, nhưng Spring Boot không có bean `CacheProperties`.

**Hỏi:** Vì sao?

**Đáp án:** Metadata không đăng ký runtime bean. Cần scan hoặc enable `@ConfigurationProperties` phù hợp.

### Bài 4 — hint có phải validation?

```json
{
  "name": "acme.mail.channel",
  "values": [{"value": "email"}]
}
```

**Hỏi:** Cấu hình `channel=sms` chắc chắn bị từ chối không?

**Đáp án:** Không. Hint chỉ hỗ trợ editor; runtime phụ thuộc kiểu và validation.

### Bài 5 — `@Value`

Service đọc:

```java
@Value("${acme.mail.title}")
String title;
```

**Hỏi:** Có tự động được tạo metadata đầy đủ cho key này không?

**Đáp án:** Không nên giả định. Có thể mô tả trong additional metadata hoặc dùng model cấu hình có kiểu.

### Bài 6 — nested object

Kiểu `SecurityOptions` là class độc lập và IDE không gợi ý `acme.client.security.enabled`.

**Hỏi:** Annotation nào liên quan đến việc đánh dấu nested property cho processor?

**Đáp án:** `@NestedConfigurationProperty`, đặt trên field hoặc khai báo phù hợp.

### Bài 7 — Gradle

**Hỏi:** Cấu hình dependency nào dành cho annotation processor?

**Đáp án:** `annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'` trong Groovy DSL hoặc cú pháp Kotlin DSL tương ứng.

### Bài 8 — file bổ sung

**Hỏi:** File nguồn thủ công cần đặt ở đâu?

**Đáp án:**

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

### Bài 9 — `Map` keys

Bạn muốn IDE gợi ý `team`, `environment` cho `acme.labels`, dùng hint name nào?

**Đáp án:** `acme.labels.keys`, không phải một runtime property tên `acme.labels.keys`.

### Bài 10 — IDE không gợi ý

Build đã có file metadata, nhưng editor thiếu hoàn thành tên khóa.

**Hỏi:** Nên sửa Spring Boot runtime đầu tiên không?

**Đáp án:** Không. Hãy kiểm tra IDE/plugin, import project và index output. Runtime có thể hoạt động hoàn toàn bình thường.

### Bài 11 — deprecated

Khóa cũ `acme.mail.sender` được thay bằng `acme.mail.from`.

**Hỏi:** Metadata nên có gì?

**Đáp án:** `deprecation` với `reason`, `replacement` và có thể `level`, `since`.

### Bài 12 — defaultValue

Bạn thêm `"defaultValue": "5s"` vào manual metadata cho một key không có default trong code hoặc tệp runtime.

**Hỏi:** Spring Boot có tự cấp 5s không?

**Đáp án:** Không. Metadata không tạo default runtime.

## 30. Checklist áp dụng

- [ ] Tên prefix có rõ và theo canonical kebab-case không?
- [ ] `@ConfigurationProperties` mô tả các nhóm cấu hình được hỗ trợ chưa?
- [ ] Java type có hợp lý (`Duration`, enum, `URI`, `DataSize`) không?
- [ ] Maven/Gradle có dùng `spring-boot-configuration-processor` đúng cách không?
- [ ] Đã build và thấy `META-INF/spring-configuration-metadata.json` chưa?
- [ ] Mô tả cho các key quan trọng có hữu ích với người cấu hình không?
- [ ] Default được mô tả có khớp hành vi runtime không?
- [ ] `additional-spring-configuration-metadata.json` chỉ bổ sung những phần cần thiết không?
- [ ] Hints không bị hiểu nhầm là validator runtime chứ?
- [ ] Các key deprecated có thông tin migration phù hợp không?
- [ ] Nested object và collection được diễn đạt hợp lý không?
- [ ] JAR phát hành có mang metadata không?
- [ ] IDE hoặc plugin hỗ trợ Spring Boot metadata đã được bật chưa?
- [ ] Có kiểm thử runtime binding/validation riêng thay vì dựa vào gợi ý IDE không?
- [ ] Metadata không chứa thông tin bí mật không nên phát hành không?

## 31. Tổng kết

Một công thức:

```text
@ConfigurationProperties
        +
spring-boot-configuration-processor
        |
        v
META-INF/spring-configuration-metadata.json
        |
        +-- groups
        +-- properties
        +-- hints
        |
        v
IDE hỗ trợ Spring Boot
        |
        +-- completion tên khóa
        +-- mô tả nhanh
        +-- type/default hints
        +-- giá trị gợi ý
        +-- cảnh báo deprecated
```

Những điều cần nhớ:

1. **Configuration metadata mô tả API cấu hình cho tooling**; nó không phải file giá trị runtime.
2. **`spring-boot-configuration-processor` sinh metadata lúc compile** từ các kiểu cấu hình được hỗ trợ, đặc biệt `@ConfigurationProperties`.
3. File chuẩn là `META-INF/spring-configuration-metadata.json`.
4. File bổ sung thủ công thường đặt tại `src/main/resources/META-INF/additional-spring-configuration-metadata.json`.
5. **`groups`, `properties`, `hints` có trách nhiệm khác nhau**. Hints hỗ trợ IDE nhưng không cưỡng chế tập giá trị runtime.
6. Mức hỗ trợ tùy IDE/plugin; có metadata không đồng nghĩa mọi editor đều hiển thị completion giống nhau.
7. Metadata **không thay** Binder, validation, profile, thứ tự ưu tiên nguồn hoặc test khởi động.

Khi xây dựng một ứng dụng hoặc starter Spring Boot có nhiều thuộc tính tự định nghĩa, metadata tốt giúp cấu hình trở nên **dễ khám phá, có mô tả và ít lỗi khi soạn thảo**, đồng thời giữ nguyên ranh giới với các cơ chế runtime.

## Tài liệu tham khảo

- Spring Boot 3.3 — Configuration Metadata Specification: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
- Spring Boot 3.3 — Metadata Format: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html
- Spring Boot 3.3 — Annotation Processor: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.3 — Manual Hints: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/manual-hints.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
