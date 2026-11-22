# Mô tả thuộc tính, kiểu dữ liệu và giá trị mặc định trong Spring Boot Configuration Metadata

## 1. Bài toán: ứng dụng đọc được cấu hình, nhưng người viết cấu hình có hiểu đúng không?

Giả sử một dự án Spring Boot có nhóm thuộc tính điều khiển client giao hàng:

```yaml
delivery:
  endpoint: https://api.example.invalid/v1
  connect-timeout: 2s
  max-attempts: 3
  mode: STANDARD
```

Các khóa này có thể được liên kết vào một lớp `@ConfigurationProperties`. Nhưng khi mở file YAML, người mới tham gia dự án sẽ đặt những câu hỏi:

- `delivery.endpoint` dùng để kết nối tới đâu? Có cho phép `http://` hay phải là `https://`?
- `connect-timeout` tính bằng giây, mili giây hay một đơn vị mặc định?
- `max-attempts` là tổng số lần gọi hay số lần **thử lại sau lần đầu**?
- `mode` có những giá trị nào?
- Nếu một khóa không xuất hiện, ứng dụng sử dụng giá trị mặc định nào?
- Khóa `delivery.connection-timeout` có phải tên hợp lệ không, hay chỉ là lỗi gõ nhầm?
- Khi đổi tên một khóa trong phiên bản mới, IDE có cách nào cảnh báo người viết cấu hình?

Spring Boot có cơ chế **Configuration Metadata** để mô tả tập khóa cấu hình được hỗ trợ. Trong trường hợp thông dụng, annotation processor `spring-boot-configuration-processor` thu thập thông tin từ những lớp `@ConfigurationProperties` rồi sinh một tệp JSON trên classpath.

Ví dụ metadata có thể nói rằng:

```json
{
  "name": "delivery.max-attempts",
  "type": "java.lang.Integer",
  "description": "Maximum number of total delivery attempts.",
  "defaultValue": 3
}
```

IDE có hỗ trợ Spring Boot có thể dùng thông tin đó để gợi ý tên khóa, đưa ra mô tả, kiểu giá trị và cảnh báo khi người viết nhập cấu hình không đúng. **Metadata là dữ liệu mô tả hỗ trợ công cụ; nó không phải một nguồn giá trị cấu hình được ưu tiên hoặc một validator runtime.**

Bài này tập trung vào ba thuộc tính cốt lõi trong metadata:

1. **`description`** — giải thích ý nghĩa của thuộc tính.
2. **`type`** — kiểu dữ liệu được khai báo cho thuộc tính.
3. **`defaultValue`** — thông tin về giá trị mặc định có thể xác định được tại thời điểm tạo metadata.

Ngoài ra, chúng ta sẽ tìm hiểu cách sinh file, cách bổ sung metadata thủ công và cách phân biệt metadata với behavior thực tế của `@ConfigurationProperties`.

## 2. Metadata nằm ở đâu và ai sử dụng?

Một tệp Spring Boot Configuration Metadata được sinh theo quy ước:

```text
META-INF/spring-configuration-metadata.json
```

Khi dùng Maven hoặc Gradle và annotation processor đã được cấu hình, tệp có thể xuất hiện trong thư mục output của lần biên dịch rồi được đóng gói vào JAR cùng với các class.

Sơ đồ:

```text
Các lớp @ConfigurationProperties
         |
         | annotation processor tại thời điểm biên dịch
         v
META-INF/spring-configuration-metadata.json
         |
         +----> IDE / tooling / tài liệu tự động
         |
         +----> Có thể được đóng gói vào JAR
         
Trong lúc ứng dụng chạy:
application.yml / ENV / CLI
         |
         v
Spring Environment
         |
         v
Spring Boot Binder
         |
         v
Đối tượng @ConfigurationProperties
```

Hai luồng trên liên quan nhưng **khác trách nhiệm**:

- Luồng metadata diễn ra chủ yếu khi build và được công cụ phát triển đọc.
- Luồng binding diễn ra khi ứng dụng nhận cấu hình thực tế và tạo đối tượng Java.
- Dữ liệu trong JSON metadata không tự được Spring Boot Binder dùng làm nguồn quyết định giá trị ứng dụng.
- Việc một IDE gợi ý giá trị hợp lệ không tự bảo đảm ứng dụng có runtime validation cho giá trị đó.
- Một ứng dụng vẫn có thể bind các khóa trong YAML khi thiếu metadata, miễn là lớp configuration properties được đăng ký và binder hoạt động bình thường.

Thông thường nên dùng metadata để **nâng chất lượng trải nghiệm lập trình** và giảm lỗi tên khóa trước khi chạy ứng dụng; muốn kiểm soát khởi động cần bổ sung type conversion, Bean Validation hoặc kiểm tra nghiệp vụ phù hợp.

## 3. Cấu trúc của một tệp metadata

Tệp `spring-configuration-metadata.json` được biểu diễn bằng JSON và có các nhóm thông tin chính:

```json
{
  "groups": [],
  "properties": [],
  "hints": []
}
```

### 3.1. groups — nhóm cấu hình

Một group thường đại diện cho một namespace hoặc một đối tượng cấu hình, chẳng hạn:

```json
{
  "name": "delivery",
  "type": "com.example.delivery.DeliveryProperties",
  "sourceType": "com.example.delivery.DeliveryProperties"
}
```

Group giúp công cụ hiểu những thuộc tính `delivery.*` liên quan tới lớp cấu hình nào. Những trường có mặt thực tế phụ thuộc phiên bản Spring Boot, cấu trúc nguồn và cách annotation processor phát hiện class/bean.

### 3.2. properties — từng khóa cấu hình

Một entry có thể có những thông tin như:

```json
{
  "name": "delivery.connect-timeout",
  "type": "java.time.Duration",
  "description": "Time allowed to establish a network connection.",
  "sourceType": "com.example.delivery.DeliveryProperties",
  "defaultValue": "2s"
}
```

Các trường quan trọng:

| Trường | Ý nghĩa | Có luôn tồn tại? |
| --- | --- | --- |
| `name` | Tên property canonical, thường ở dạng kebab-case | Trường cốt lõi của entry |
| `type` | Tên kiểu Java của thuộc tính | Có thể thiếu hoặc khác biểu diễn nếu không suy ra được |
| `description` | Văn bản giải thích thuộc tính | Có thể thiếu nếu source không có Javadoc/metadata bổ sung |
| `defaultValue` | Mặc định mà công cụ có thể mô tả | Có thể thiếu nếu processor không suy ra được |
| `sourceType` | Class khai báo hoặc cung cấp property | Tùy ngữ cảnh |
| `deprecation` | Thông tin thuộc tính đã cũ | Chỉ có khi được khai báo |

**Không đọc một file JSON minh họa như bằng chứng rằng mọi phiên bản Spring Boot đều sinh chính xác những trường và cách viết giống nhau.** File thực tế là sản phẩm của processor và mã nguồn đang build.

### 3.3. hints — gợi ý giá trị hoặc cách nhập

`hints` có thể giúp IDE đưa ra lựa chọn cho một property, chẳng hạn:

```json
{
  "name": "delivery.mode",
  "values": [
    {
      "value": "STANDARD",
      "description": "Normal delivery handling."
    },
    {
      "value": "EXPRESS",
      "description": "Prioritize fast delivery."
    }
  ]
}
```

Các gợi ý này không tự biến property thành một enum hoặc giới hạn runtime. Với enum Java, IDE có thể có sẵn gợi ý từ type; với `String` nhận một tập giá trị quy ước, metadata bổ sung có thể cung cấp danh sách gợi ý.

## 4. Chuẩn bị spring-boot-configuration-processor

**Mục tiêu:** thêm annotation processor vào quá trình biên dịch, không biến nó thành một dependency nghiệp vụ bắt buộc lúc chạy.

### 4.1. Maven

Đối với dự án Maven Spring Boot dùng parent/BOM quản lý phiên bản, có thể khai báo:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Một số dự án cấu hình `maven-compiler-plugin` với `annotationProcessorPaths` hoặc chính sách xử lý annotation tường minh. Trong trường hợp đó, phải bảo đảm processor nằm trong đường dẫn processor tương ứng; chỉ thêm một dependency nhưng compiler không chạy annotation processing thì metadata sẽ không được sinh.

Với project dùng plugin và wrapper thông dụng, chạy:

```bash
./mvnw clean compile
```

Trên Windows có thể dùng:

```bat
mvnw.cmd clean compile
```

Sau build, kiểm tra đường dẫn dự kiến:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Đường dẫn trên chỉ là dạng thường gặp của output Maven, có thể khác nếu project cấu hình lại thư mục build.

### 4.2. Gradle Groovy DSL

Trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
```

Nếu cần test Spring Boot:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Sau đó:

```bash
./gradlew clean classes
```

Trên Windows dùng `gradlew.bat clean classes`. Với Java project, một đường dẫn output thông dụng:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

### 4.3. Gradle Kotlin DSL

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )
}
```

Dùng `annotationProcessor` thay vì tự đưa processor vào runtime classpath chỉ để tạo JSON. Với mã Kotlin, cơ chế annotation processing có thể yêu cầu cấu hình kapt/KSP hoặc công cụ phù hợp theo phiên bản build. Đừng giả định cấu hình Java `annotationProcessor` tự xử lý mọi class Kotlin.

### 4.4. Vì sao processor là thành phần build-time?

Metadata được rút ra từ các class và annotation ở lúc biên dịch. Không cần một bean runtime tên `ConfigurationMetadataProcessor` để xử lý YAML khi server chạy.

Nếu xóa metadata khỏi JAR nhưng giữ nguyên class đã biên dịch và cấu hình binder, ứng dụng vẫn có thể khởi động và bind cấu hình như trước; điều bị ảnh hưởng chủ yếu là trải nghiệm của công cụ đọc metadata.

Do đó, khi thấy IDE không gợi ý property, nên kiểm tra bước build/metadata trước, **không vội kết luận binder runtime bị lỗi**.

## 5. Ví dụ đầu tiên: tạo lớp @ConfigurationProperties có mô tả rõ

Ta xây một project Spring Boot 3.x, Java 17+, sử dụng một cấu hình client giao hàng.

Tạo file:

```text
src/main/java/com/example/delivery/DeliveryProperties.java
```

Ví dụ JavaBean để minh họa cách processor đọc Javadoc của field:

```java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Settings for the outbound delivery API integration.
 */
@ConfigurationProperties(prefix = "delivery")
public class DeliveryProperties {

    /**
     * Base URI for the delivery API.
     * Configure this for the target deployment environment.
     */
    private URI endpoint;

    /**
     * Maximum time allowed to establish an outbound connection.
     */
    private Duration connectTimeout = Duration.ofSeconds(2);

    /**
     * Total number of attempts including the initial request.
     */
    private int maxAttempts = 3;

    /**
     * Whether the delivery integration is enabled.
     */
    private boolean enabled = false;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Lớp ví dụ có bốn thuộc tính:

| Java field | Tên khóa chuẩn | Kiểu dữ liệu | Giá trị khởi tạo |
| --- | --- | --- | --- |
| `endpoint` | `delivery.endpoint` | `URI` | `null` (chưa cấp) |
| `connectTimeout` | `delivery.connect-timeout` | `Duration` | 2 giây |
| `maxAttempts` | `delivery.max-attempts` | `int` | 3 |
| `enabled` | `delivery.enabled` | `boolean` | false |

Các comment `/** ... */` là **Javadoc**. Đây là nguồn quan trọng để processor lấy description cho thuộc tính trong trường hợp class kiểu JavaBean. Comment thông thường như `// max attempts` không phải cách đáng tin cậy để sinh trường `description`.

Trong ví dụ, `getXxx` và `setXxx` tạo nên JavaBean accessors cho binder. Spring Boot có thể dùng các setter để liên kết những giá trị từ cấu hình ngoài.

## 6. Đăng ký bean và đọc cấu hình tại runtime

Ta đăng ký `DeliveryProperties` qua `@EnableConfigurationProperties`, không chỉ viết annotation rồi để lớp nằm im trong source.

```java
package com.example.delivery;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeliveryApplication.class, args);
    }

    @Bean
    ApplicationRunner printDeliverySettings(DeliveryProperties properties) {
        return args -> {
            System.out.println("enabled = " + properties.isEnabled());
            System.out.println("endpoint = " + properties.getEndpoint());
            System.out.println(
                "connectTimeout = " + properties.getConnectTimeout());
            System.out.println(
                "maxAttempts = " + properties.getMaxAttempts());
        };
    }
}
```

Ví dụ `application.yml`:

```yaml
delivery:
  endpoint: https://api.example.invalid/v1
```

Khi khởi động, ba giá trị `enabled`, `connectTimeout` và `maxAttempts` vẫn có thể dùng giá trị khởi tạo trong lớp; `endpoint` nhận URI từ YAML.

Một kết quả minh họa:

```text
enabled = false
endpoint = https://api.example.invalid/v1
connectTimeout = PT2S
maxAttempts = 3
```

**Điểm phân biệt cốt lõi:**

- Binder tạo hoặc cập nhật đối tượng `DeliveryProperties` theo cách đăng ký phù hợp.
- Giá trị khởi tạo Java có tác dụng runtime vì đó là trạng thái ban đầu của object.
- Metadata `defaultValue` có thể mô tả trạng thái này cho công cụ, nhưng không phải nguồn làm phát sinh runtime default.
- Nếu môi trường cung cấp `--delivery.max-attempts=8`, giá trị được bind là `8` dù metadata có mô tả default `3`.

Đường dẫn `api.example.invalid` chỉ dùng cho minh họa, không phải dịch vụ mà chương trình này sẽ tự gọi.

## 7. Mô tả bằng Javadoc: viết điều người cấu hình thật sự cần biết

Một trường metadata `description` tốt không chỉ lặp lại tên khóa.

Không nên chỉ viết:

```java
/** Max attempts. */
private int maxAttempts = 3;
```

Vì người dùng vẫn chưa biết một “attempt” là gì. Nên viết:

```java
/**
 * Maximum number of total delivery attempts, including the first request.
 * The value must be greater than zero.
 */
private int maxAttempts = 3;
```

Nội dung này giải thích hai điểm có thể bị hiểu sai:

1. Đây là **tổng** số lần gọi, không phải số lần retry bổ sung.
2. Giá trị phải dương theo hợp đồng vận hành.

Tương tự, với thời lượng:

```java
/**
 * Maximum time allowed to establish an outbound connection.
 * Values such as "500ms" and "2s" are supported.
 */
private Duration connectTimeout = Duration.ofSeconds(2);
```

Với endpoint:

```java
/**
 * URI of the delivery API for the active environment.
 * Do not include access tokens in this URI.
 */
private URI endpoint;
```

### Phân biệt mô tả và validator

Một description ghi “must be positive” không tự tạo kiểm tra dương cho Java `int`. Nếu cần kiểm tra lúc khởi động, dùng Bean Validation hoặc cơ chế kiểm tra phù hợp.

Ví dụ:

```java
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public class DeliveryProperties {

    /**
     * Total number of attempts including the initial call.
     */
    @Min(1)
    private int maxAttempts = 3;

    // getters/setters...
}
```

Muốn constraint được đánh giá, project cần một validation provider tương thích, thường thông qua `spring-boot-starter-validation` ở ứng dụng Boot. Metadata có thể hỗ trợ IDE, còn `@Min(1)` trong hệ thống validation mới là quy tắc runtime.

Một lý do quan trọng để viết description đủ chi tiết là nó thường xuất hiện trong IDE ngay tại chỗ người dùng khai báo property. Điều này giúp người phát triển hiểu ý nghĩa mà không phải tìm đến class Java.

## 8. Kiểu dữ liệu trong metadata đến từ đâu?

Processor thường xác định kiểu thông qua khai báo Java.

Ví dụ:

```java
private String senderName;
private int maxAttempts;
private boolean enabled;
private Duration connectTimeout;
private URI endpoint;
private List<String> tags;
private Map<String, Integer> limits;
```

Trong metadata, trường `type` thường là tên kiểu Java đủ điều kiện, chẳng hạn:

```text
java.lang.String
java.lang.Integer
java.lang.Boolean
java.time.Duration
java.net.URI
java.util.List<java.lang.String>
java.util.Map<java.lang.String,java.lang.Integer>
```

Biểu diễn của primitive như `int` có thể được metadata chuẩn hóa thành kiểu bao `java.lang.Integer`. Với những kiểu generic, annotation processor có thể cung cấp dạng kiểu tổng quát mà công cụ hiểu được.

**Metadata type không giống kiểu dữ liệu YAML.** Trong YAML, một value có thể xuất hiện dưới dạng `2s` hoặc `true`. Binder chịu trách nhiệm chuyển sang `Duration`, `Boolean` hoặc kiểu Java khác.

```text
YAML text: connect-timeout: 2s
                  |
                  v
Metadata type: java.time.Duration  (gợi ý cho IDE)
                  |
                  v
Spring Boot Binder runtime: Duration.ofSeconds(2)
```

Không phải cứ metadata nói `Duration` là mọi cách viết thời lượng đều hợp lệ. Khả năng chuyển đổi phụ thuộc binder, conversion service và phiên bản thư viện. Với kiểu tự định nghĩa, có thể cần converter phù hợp.

### Enum và type metadata

Ví dụ:

```java
public enum DeliveryMode {
    STANDARD,
    EXPRESS
}
```

Một class cấu hình:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        DeliveryMode mode
) {}
```

Processor có thể mô tả `type` bằng tên đầy đủ của enum, giúp IDE gợi ý những hằng số enum mà dự án định nghĩa.

Ví dụ:

```yaml
delivery:
  mode: EXPRESS
```

Binder runtime vẫn thực hiện việc chuyển kiểu. Nếu cấu hình cung cấp tên không tồn tại hoặc một giá trị không được converter chấp nhận, ứng dụng có thể lỗi binding; metadata không tự thêm enum constant mới.

## 9. Mặc định: cần phân biệt ba nơi khác nhau

Từ “default” trong cấu hình Spring Boot thường được dùng cho **ba khái niệm**:

1. Giá trị khởi tạo trong class Java hoặc giá trị do constructor binding quy định.
2. Giá trị mặc định trong file `application.yml` hoặc một nguồn cấu hình có ưu tiên thấp hơn.
3. Trường **`defaultValue` trong JSON metadata**, chủ yếu phục vụ công cụ.

Ba giá trị có thể giống nhau nhưng chúng **không phải cùng một cơ chế**.

### 9.1. Mặc định trong JavaBean

```java
@ConfigurationProperties(prefix = "delivery")
public class DeliveryProperties {

    private int maxAttempts = 3;
    private boolean enabled = false;

    // getters/setters...
}
```

Khi không có nguồn cấu hình ghi đè những field này, object có thể giữ các giá trị khởi tạo là `3` và `false`. Annotation processor có thể suy ra một số giá trị khởi tạo đơn giản và ghi vào metadata.

Không phải mọi biểu thức Java đều được processor giải tích đầy đủ. Ví dụ một default phụ thuộc hàm tùy ý, biến runtime hoặc kết quả gọi dịch vụ không nên được kỳ vọng tự xuất hiện chính xác trong JSON metadata.

### 9.2. Mặc định tại constructor binding bằng @DefaultValue

Với record hoặc class dùng constructor binding, có thể khai báo `@DefaultValue`:

```java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        URI endpoint,

        @DefaultValue("2s")
        Duration connectTimeout,

        @DefaultValue("3")
        int maxAttempts,

        @DefaultValue("false")
        boolean enabled
) {}
```

Trong cơ chế constructor binding được Spring Boot hỗ trợ, khi thuộc tính vắng mặt, binder có thể dùng giá trị từ `@DefaultValue` để tạo đối tượng. Processor cũng có thể dùng thông tin đó để mô tả mặc định trong metadata.

Với Spring Boot 3 và record chỉ có một constructor phù hợp, không cần thêm `@ConstructorBinding` trong ví dụ đơn giản này. Nếu dùng nhiều constructor hoặc cấu hình đăng ký bean khác, phải tuân theo quy tắc constructor binding của phiên bản dự án.

Đừng tự đặt Spring bean như `HttpClient` hoặc `Repository` thành một tham số constructor của `@ConfigurationProperties` record chỉ để inject dependency. Constructor binding ở đây là **liên kết dữ liệu cấu hình**, không phải phương thức injection của service thông thường.

### 9.3. Mặc định trong application.yml

```yaml
delivery:
  connect-timeout: 2s
  max-attempts: 3
  enabled: false
```

Đây là một **nguồn cấu hình runtime**. Nếu không có nguồn ưu tiên cao hơn ghi đè, binder lấy những giá trị này. Nếu chỉ thay:

```yaml
delivery:
  max-attempts: 5
```

mà không biên dịch lại lớp `@ConfigurationProperties`, file metadata được sinh từ source Java **không tự đổi thành `defaultValue: 5`**. Processor không có nhiệm vụ coi mọi giá trị ở mọi file YAML, profile hoặc secret store là default compile-time.

Đó là nguyên nhân cần hiểu rõ khi một IDE hiện “default = 3” trong khi ứng dụng đang chạy với `5` từ YAML hoặc `8` từ biến môi trường.

### 9.4. Mặc định trong metadata có tác dụng runtime không?

Không nên coi entry:

```json
{
  "name": "delivery.max-attempts",
  "type": "java.lang.Integer",
  "defaultValue": 3
}
```

là một lệnh yêu cầu binder điền `3` vào record. Đây là **thông tin mô tả**. Nếu class không khai báo runtime default và các nguồn thực tế cũng không cung cấp giá trị, chỉ có JSON metadata không làm property tự nhận 3.

Muốn mặc định thực sự có hiệu lực, hãy đặt nó trong cấu hình runtime hoặc biểu diễn trong lớp binding theo API được Spring Boot hỗ trợ.

## 10. Mặc định kiểu dữ liệu đặc biệt

### 10.1. Duration

```java
@DefaultValue("250ms")
Duration retryDelay
```

Khi không có giá trị cấu hình, binder có thể chuyển mặc định này thành một `Duration` tương đương 250 mili giây.

Nếu muốn thời lượng mặc định 2 giây, có thể viết:

```java
@DefaultValue("2s")
Duration connectTimeout
```

Một file metadata có thể thể hiện `defaultValue` dưới dạng văn bản như `"2s"`, nhưng định dạng cụ thể của output có thể phụ thuộc phiên bản và cách processor xử lý nguồn.

Khi viết description, nên giải thích thời lượng này dùng cho **connect**, **read**, hay tổng deadline của request. Hai thuộc tính cùng kiểu `Duration` không nhất thiết cùng nghĩa.

### 10.2. DataSize

Với những giới hạn bộ nhớ hoặc payload, Spring Boot có kiểu `DataSize`:

```java
import org.springframework.util.unit.DataSize;

@DefaultValue("8MB")
DataSize maxPayloadSize
```

Metadata type có thể nêu `org.springframework.util.unit.DataSize`. Runtime binder xử lý cú pháp phù hợp theo converter của Spring Boot.

Đừng dùng `@Min` trực tiếp lên `DataSize` như với `int` nếu validation provider không có validator tương ứng. Type metadata và validation constraint là hai khía cạnh tách biệt.

### 10.3. Enum

```java
@DefaultValue("STANDARD")
DeliveryMode mode
```

Khi thiếu thuộc tính và constructor binding được cấu hình đúng, default có thể là `DeliveryMode.STANDARD`. Metadata giúp IDE biết kiểu enum và có thể đưa ra các giá trị hợp lệ.

### 10.4. Collection

```java
Map<String, String> headers
List<String> regions
```

Một collection có thể có mặc định hoặc cấu trúc phức tạp. Tuy nhiên, không nên giả định processor sẽ tự suy ra mọi giá trị mặc định của list/map từ biểu thức Java hoặc cấu hình YAML. Với collection, tài liệu mô tả nên nêu quy tắc thêm/xóa, cú pháp phần tử và liệu có cho phép khóa động.

## 11. File metadata thực tế có thể trông như thế nào?

Với class `DeliveryProperties` ở phần 5, output minh họa có cấu trúc gần như:

```json
{
  "groups": [
    {
      "name": "delivery",
      "type": "com.example.delivery.DeliveryProperties",
      "sourceType": "com.example.delivery.DeliveryProperties"
    }
  ],
  "properties": [
    {
      "name": "delivery.endpoint",
      "type": "java.net.URI",
      "description": "Base URI for the delivery API. Configure this for the target deployment environment.",
      "sourceType": "com.example.delivery.DeliveryProperties"
    },
    {
      "name": "delivery.connect-timeout",
      "type": "java.time.Duration",
      "description": "Maximum time allowed to establish an outbound connection.",
      "sourceType": "com.example.delivery.DeliveryProperties"
    },
    {
      "name": "delivery.max-attempts",
      "type": "java.lang.Integer",
      "description": "Total number of attempts including the initial call.",
      "sourceType": "com.example.delivery.DeliveryProperties",
      "defaultValue": 3
    },
    {
      "name": "delivery.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether the delivery integration is enabled.",
      "sourceType": "com.example.delivery.DeliveryProperties",
      "defaultValue": false
    }
  ],
  "hints": []
}
```

**Đây là JSON minh họa về schema và nội dung mong đợi, không phải một tệp được sao chép từ build thực tế.** Processor có thể sinh description khác nếu Javadoc nguồn khác, có thể biểu diễn default thời lượng khác hoặc có/không có những trường tùy khả năng suy luận.

Điều bạn cần kiểm tra trong output thật:

- Có group `delivery` không?
- Các khóa có đúng dạng canonical `delivery.*` không?
- `type` có khớp khai báo Java không?
- `description` có chứa Javadoc cần thiết không?
- `defaultValue` nào xuất hiện và lý do?
- Có thông tin bổ sung dành cho công cụ như `hints` không?

Nếu không thấy một field optional trong JSON, đừng kết luận ứng dụng runtime đã mất giá trị cấu hình. Hãy phân tích cơ chế sinh metadata trước.

## 12. Javadoc cho record và constructor-bound properties

Với record, source code gọn hơn:

```java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Configuration for outbound delivery requests.
 *
 * @param endpoint target service URI
 * @param connectTimeout maximum time allowed to establish a connection
 * @param maxAttempts total attempts including the first call
 */
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        URI endpoint,
        @DefaultValue("2s") Duration connectTimeout,
        @DefaultValue("3") int maxAttempts
) {}
```

Javadoc `@param` mô tả các thành phần của record theo quy ước Java. Khi dùng annotation processor, khả năng thu thập description từ record/constructor và các trường source có thể phụ thuộc phiên bản processor.

Vì vậy, với class record:

1. Viết mô tả cho từng tham số ở nơi phù hợp, thay vì chỉ viết một dòng Javadoc chung.
2. Dùng `@DefaultValue` để làm rõ default của constructor binding.
3. **Kiểm tra file JSON được sinh** sau build để xác nhận những description mong muốn thực sự xuất hiện.
4. Nếu một property không thể tự mô tả đầy đủ qua source, cân nhắc metadata bổ sung có chủ đích.

Điều quan trọng không phải ép mọi kiểu class tạo JSON giống hệt nhau; mục tiêu là đưa ra metadata chính xác để công cụ và người viết cấu hình hiểu hợp đồng.

## 13. Bổ sung metadata thủ công bằng additional-spring-configuration-metadata.json

Không phải lúc nào annotation processor cũng hiểu đủ thông tin. Một property có thể:

- Được đọc thủ công từ `Environment`, không có field `@ConfigurationProperties` tương ứng.
- Có description nghiệp vụ dài hơn những gì processor rút ra.
- Cần danh sách giá trị gợi ý cho người cấu hình.
- Cần ghi chú về một khóa đã đổi tên hoặc bị deprecated.
- Được tạo thông qua cấu trúc mà processor không suy luận đầy đủ.

Spring Boot hỗ trợ file bổ sung theo đường dẫn quy ước:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Đây là file **nguồn do dự án quản lý**, khác với `spring-configuration-metadata.json` **được sinh khi build**.

Một ví dụ:

```json
{
  "properties": [
    {
      "name": "delivery.legacy-region",
      "type": "java.lang.String",
      "description": "Legacy region identifier used by an older integration."
    }
  ],
  "hints": [
    {
      "name": "delivery.mode",
      "values": [
        {
          "value": "STANDARD",
          "description": "Use the normal delivery workflow."
        },
        {
          "value": "EXPRESS",
          "description": "Prefer fast delivery processing."
        }
      ]
    }
  ]
}
```

Khi annotation processor và resource processing được cấu hình phù hợp, metadata bổ sung được dùng để hoàn thiện thông tin tạo ra. Nó có thể cung cấp property chưa được processor khám phá hoặc thêm các thông tin hỗ trợ công cụ.

**Không nhầm file bổ sung với `application.yml`.** Khai báo `delivery.legacy-region` trong metadata không khiến ứng dụng tự nhận giá trị hoặc tự tạo Java field tên `legacyRegion`.

### Khi nào nên khai báo description thủ công?

Ví dụ một property `delivery.mode` được sử dụng bởi một adapter tích hợp, nhưng description trong source class không đủ rõ. Một entry metadata bổ sung có thể đưa ra mô tả vận hành đầy đủ hơn.

Tuy vậy, nếu class `@ConfigurationProperties` đã sở hữu một field và bạn có quyền sửa source, thường dễ bảo trì hơn khi viết Javadoc đúng tại field đó. Đừng tạo hai nơi mô tả mâu thuẫn nhau nếu không có lý do.

### Khi nào cần lưu ý thứ tự build?

File bổ sung nằm trong `src/main/resources`, còn annotation processor chạy trong bước biên dịch. Ở một số cấu hình Gradle/Maven, phải bảo đảm resource bổ sung có thể được processor đọc ở giai đoạn phù hợp để kết quả được tổng hợp đúng.

Nếu JSON bổ sung không xuất hiện trong output hoặc không được kết hợp như dự kiến, hãy kiểm tra:

- Processor có được kích hoạt không?
- File có ở đúng đường dẫn `META-INF` không?
- JSON có đúng cú pháp không?
- Compile và process resources diễn ra theo thứ tự nào?
- Artifact cuối cùng chứa những tệp metadata nào?

Không giải quyết bằng cách sửa trực tiếp file được sinh trong `build/` hoặc `target/`, vì lần build sau sẽ ghi đè thay đổi thủ công.

## 14. Hints cho giá trị: khi một String có những lựa chọn phổ biến

Giả sử class dùng:

```java
/**
 * Delivery workflow mode.
 */
private String mode = "STANDARD";
```

Vì `String` chấp nhận rất nhiều giá trị, chỉ có metadata type `java.lang.String` không cho IDE biết nhóm có hai chế độ phổ biến.

Có thể thêm hint:

```json
{
  "hints": [
    {
      "name": "delivery.mode",
      "values": [
        {
          "value": "STANDARD",
          "description": "Normal priority."
        },
        {
          "value": "EXPRESS",
          "description": "Higher priority."
        }
      ]
    }
  ]
}
```

Một IDE hỗ trợ metadata có thể hiển thị hai lựa chọn này.

Phân biệt:

- **Hint**: gợi ý người viết cấu hình trong IDE.
- **Java enum**: kiểu dữ liệu có tập giá trị xác định được.
- **Validation**: cơ chế kiểm tra đầu vào theo luật ứng dụng lúc runtime.
- **Default**: giá trị được chọn khi thuộc tính vắng mặt.

Nếu yêu cầu chỉ cho phép hai giá trị, nên cân nhắc đổi sang enum:

```java
public enum DeliveryMode {
    STANDARD,
    EXPRESS
}
```

Và dùng `DeliveryMode mode` trong properties. Khi đó kiểu dữ liệu giúp biểu đạt hợp đồng mạnh hơn một chuỗi tùy ý. Metadata hint có thể bổ sung giải thích, nhưng không thay thế việc chọn mô hình Java thích hợp.

## 15. Mô tả nested properties và nhóm cấu hình

Cấu hình thường có nhiều cấp:

```yaml
delivery:
  retry:
    max-attempts: 3
    backoff: 500ms
  security:
    verify-tls: true
```

Một mô hình:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        Retry retry,
        Security security
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}

    public record Security(
            boolean verifyTls
    ) {}
}
```

Tên khóa có thể được metadata thể hiện:

```text
delivery.retry.max-attempts
delivery.retry.backoff
delivery.security.verify-tls
```

Processor có thể khám phá nested properties dựa vào kiểu dữ liệu và cách khai báo. Với những class riêng không hiển nhiên là nhóm nested, Spring Boot cung cấp annotation `@NestedConfigurationProperty` để hỗ trợ nhận diện metadata cấu hình lồng nhau trong trường hợp phù hợp.

**Lưu ý:** `@NestedConfigurationProperty` chủ yếu hướng đến cơ chế nhận diện metadata; nó không phải công tắc bắt Binder runtime từ chối mọi cấu hình không có annotation. Với inner class hoặc một kiểu được binder hỗ trợ trực tiếp, không nhất thiết phải thêm annotation chỉ để có cú pháp YAML lồng nhau.

Description nên mô tả **ý nghĩa từng thuộc tính**, không chỉ tên nhóm:

- `delivery.retry.max-attempts`: tổng số lần gửi bao gồm lần đầu.
- `delivery.retry.backoff`: khoảng chờ giữa các lần thử theo chính sách.
- `delivery.security.verify-tls`: có kiểm tra TLS cho kết nối outbound hay không.

Khi một group có nhiều thuộc tính, mô tả này còn giúp người viết cấu hình phát hiện việc đặt giá trị sai cấp.

## 16. Metadata và đơn vị của Duration/DataSize

Một trường `type` là `java.time.Duration` giúp IDE biết đây là thời lượng. Nhưng người vận hành cần hiểu **đơn vị và ngữ nghĩa**.

Ví dụ:

```java
/**
 * Time allowed to establish the connection.
 * Use values with units, for example "250ms" or "2s".
 */
private Duration connectTimeout = Duration.ofSeconds(2);
```

Với Spring Boot, những annotation như `@DurationUnit` và `@DataSizeUnit` có thể quy định đơn vị mặc định khi binding một giá trị không có hậu tố đơn vị trong các trường hợp được hỗ trợ.

Ví dụ:

```java
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.convert.DurationUnit;

@DurationUnit(ChronoUnit.SECONDS)
private Duration connectTimeout = Duration.ofSeconds(2);
```

Khi không có hậu tố, binder có thể hiểu con số theo giây trong ngữ cảnh này. Nhưng mô tả metadata vẫn nên khuyến khích dùng `2s` hoặc `500ms` để tránh mơ hồ ở file cấu hình.

Không nên coi `description` hoặc `type` là nơi quyết định đơn vị runtime. Annotation chuyển đổi, conversion service, kiểu Java và giá trị nguồn mới quyết định kết quả binding.

### Dữ liệu DataSize

```java
import org.springframework.util.unit.DataSize;

/**
 * Maximum permitted payload size.
 * Example: "8MB".
 */
private DataSize maxPayloadSize = DataSize.ofMegabytes(8);
```

Metadata có thể cho IDE biết kiểu `DataSize` và description; ứng dụng vẫn cần validation nếu không cho phép kích thước âm hoặc vượt giới hạn nghiệp vụ.

## 17. Deprecation metadata: mô tả thuộc tính đã cũ

Khi hệ thống đổi tên một khóa, ví dụ từ `delivery.retries` sang `delivery.max-attempts`, metadata có thể giúp IDE cảnh báo người viết cấu hình.

Một entry metadata bổ sung minh họa:

```json
{
  "properties": [
    {
      "name": "delivery.retries",
      "type": "java.lang.Integer",
      "description": "Legacy retry setting.",
      "deprecation": {
        "level": "warning",
        "reason": "The name is ambiguous about total attempts.",
        "replacement": "delivery.max-attempts"
      }
    }
  ]
}
```

Ý nghĩa:

- `level` diễn đạt mức độ deprecated cho công cụ.
- `reason` giải thích vì sao tên cũ không nên tiếp tục dùng.
- `replacement` chỉ ra tên thay thế được khuyến nghị.

**Deprecation metadata không tự di chuyển giá trị cấu hình.** Nếu runtime code không còn nhận `delivery.retries`, việc IDE gợi ý `delivery.max-attempts` không bảo đảm deployment cũ vẫn chạy đúng.

Muốn hỗ trợ một giai đoạn chuyển tiếp, cần thiết kế cơ chế compatibility hoặc migration rõ ràng. Khi hết giai đoạn hỗ trợ, loại bỏ tên cũ khỏi code và cập nhật cấu hình của môi trường triển khai.

Với JavaBean properties, Spring Boot có thể khai thác các annotation deprecation chuyên dụng trong điều kiện thích hợp. Nhưng với bài tập metadata, file JSON bổ sung giúp thấy rõ việc một tên cũ được đánh dấu và mô tả hướng thay thế.

## 18. Metadata không phải schema validation toàn cục

Khi IDE có thông tin:

```json
{
  "name": "delivery.max-attempts",
  "type": "java.lang.Integer",
  "defaultValue": 3
}
```

người dùng có thể mong rằng mọi cách khai báo sai sẽ tự bị chặn. Cần phân biệt nhiều tình huống.

| Tình huống | Metadata giúp gì? | Runtime xử lý thế nào? |
| --- | --- | --- |
| Gõ `delivery.max-attemtps` | IDE có thể không gợi ý, có thể cảnh báo tên lạ | `ignoreUnknownFields`, binder và nguồn thực tế quyết định |
| Gõ `delivery.max-attempts=abc` | IDE biết kiểu số, có thể cảnh báo | Conversion sang `int` thường lỗi |
| Gõ `delivery.max-attempts=-5` | Có thể thấy description | `int` vẫn chuyển được; cần validation như `@Min(1)` |
| Không khai báo `delivery.max-attempts` | IDE có thể hiện default metadata | Runtime default phụ thuộc Java/Binder/YAML, không phụ thuộc JSON |
| Đổi file theo profile | Metadata vẫn mô tả cùng property | Runtime lấy giá trị từ nguồn ưu tiên phù hợp |
| Đặt token vào URI | Metadata có thể nêu khuyến nghị | Cần chính sách bảo mật riêng |

Metadata không thay thế:

- `@Validated` và Jakarta Bean Validation.
- Cơ chế `ignoreUnknownFields` của `@ConfigurationProperties`.
- Type conversion của Spring Boot Binder.
- Các bài test khởi động với profile và nguồn cấu hình thật.
- Quy trình quản lý secret, phân quyền và giám sát triển khai.

Một sản phẩm cấu hình tốt thường có **metadata rõ**, **binding có kiểu** và **validation có chủ đích**. Ba lớp này hỗ trợ lẫn nhau nhưng không hoán đổi chức năng.

## 19. Metadata và nguồn cấu hình có ưu tiên khác nhau

Giả sử class Java có:

```java
private int maxAttempts = 3;
```

Metadata có thể sinh:

```json
{
  "name": "delivery.max-attempts",
  "type": "java.lang.Integer",
  "defaultValue": 3
}
```

File `application.yml`:

```yaml
delivery:
  max-attempts: 4
```

File `application-prod.yml`:

```yaml
delivery:
  max-attempts: 5
```

Khởi động:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --delivery.max-attempts=8
```

Trong tình huống Spring Boot chuẩn, command-line argument có ưu tiên cao hơn các file Config Data tương ứng, nên bean nhận `8`.

Dù vậy, metadata vẫn có thể nói **defaultValue = 3** vì đó là mặc định được nhận diện tại build-time. Metadata không cần đổi thành 4, 5 hoặc 8 mỗi khi môi trường chạy khác.

Bảng:

| Nguồn | Giá trị minh họa | Vai trò |
| --- | --- | --- |
| Field initializer Java | `3` | Runtime default của object khi không override |
| Metadata `defaultValue` | `3` | Mô tả compile-time cho công cụ |
| `application.yml` | `4` | Nguồn Config Data runtime |
| `application-prod.yml` | `5` | Nguồn Config Data theo profile |
| Command-line argument | `8` | Nguồn runtime có ưu tiên cao hơn trong ví dụ |
| Giá trị bean cuối cùng | `8` | Kết quả runtime sau khi áp dụng precedence |

Đừng gọi giá trị ở metadata là “giá trị thực tế đang chạy”. Nếu cần quan sát runtime, dùng một phương thức chẩn đoán an toàn để tra cứu `Environment` hoặc đối tượng `@ConfigurationProperties` đã được tạo.

## 20. Thực hành: sinh metadata rồi đọc từng field

Hãy thực hiện một lượt thực hành có thể lặp lại.

### Bước 1 — Tạo cấu hình

```yaml
delivery:
  endpoint: https://api.example.invalid/v1
  mode: STANDARD
```

### Bước 2 — Tạo class có Javadoc và default

```java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "delivery")
public class DeliveryProperties {

    /**
     * Target URI for outbound delivery requests.
     */
    private URI endpoint;

    /**
     * Timeout for opening the network connection.
     */
    private Duration connectTimeout = Duration.ofSeconds(2);

    /**
     * Total number of requests allowed, including the first attempt.
     */
    private int maxAttempts = 3;

    /**
     * Requested delivery mode.
     */
    private String mode = "STANDARD";

    public URI getEndpoint() {
        return endpoint;
    }
    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }
    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public String getMode() {
        return mode;
    }
    public void setMode(String mode) {
        this.mode = mode;
    }
}
```

### Bước 3 — Đăng ký properties

```java
@SpringBootApplication
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DeliveryApplication.class, args);
    }
}
```

Imports cần có:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
```

### Bước 4 — Thêm processor

Gradle:

```groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
```

Hoặc Maven dùng dependency đã trình bày ở phần 4, bảo đảm annotation processing được bật.

### Bước 5 — Biên dịch

Gradle:

```bash
./gradlew clean classes
```

Maven:

```bash
./mvnw clean compile
```

### Bước 6 — Mở metadata được sinh

Tìm file `META-INF/spring-configuration-metadata.json` trong output build. Trong một project Gradle Java, thường dưới:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

Với Maven, thường dưới:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Quan sát từng property `delivery.endpoint`, `delivery.connect-timeout`, `delivery.max-attempts` và `delivery.mode`. Đối với mỗi property, ghi lại:

- `name`
- `type`
- `description`
- `defaultValue` nếu có

Đừng so sánh JSON với một file mẫu theo từng byte. Mục tiêu là hiểu ý nghĩa và sự có mặt của các field liên quan.

### Bước 7 — Đổi Javadoc và build lại

Ví dụ đổi comment của `maxAttempts` từ:

```java
/** Total requests allowed. */
```

thành:

```java
/**
 * Total delivery attempts including the first request.
 */
```

Build lại. Kiểm tra `description` của `delivery.max-attempts` có được cập nhật. Nếu không, xác nhận processor có chạy, compiler có biên dịch lại source và IDE có đọc đúng output mới hay không.

### Bước 8 — Đổi runtime nhưng không đổi source

Giữ Java và metadata như cũ, khởi động với:

```bash
java -jar app.jar --delivery.max-attempts=7
```

Kết quả runtime của bean có thể là 7; metadata vẫn mô tả mặc định compile-time của lớp. Thực hành này làm rõ ranh giới giữa **tooling** và **runtime configuration**.

## 21. Bổ sung hint cho một thuộc tính mode

Giả sử người viết cấu hình phải chọn `STANDARD` hoặc `EXPRESS` nhưng class Java vẫn tạm dùng `String`. Tạo file:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Nội dung:

```json
{
  "hints": [
    {
      "name": "delivery.mode",
      "values": [
        {
          "value": "STANDARD",
          "description": "Normal delivery processing."
        },
        {
          "value": "EXPRESS",
          "description": "Faster processing with higher priority."
        }
      ]
    }
  ]
}
```

Sau khi build và IDE cập nhật metadata, thử mở `application.yml`, gõ `delivery.mode` rồi xem công cụ có hiển thị những lựa chọn/hint không.

Nếu IDE không hiện danh sách ngay, chưa thể kết luận cấu hình metadata sai. Các IDE khác nhau có mức hỗ trợ metadata và cách cache khác nhau; đôi khi cần reload Gradle/Maven project, build lại hoặc làm mới indexing.

Điều quan trọng là file bổ sung đã được đặt đúng nơi, có JSON hợp lệ, và output metadata có thông tin cần thiết.

## 22. Từ thông tin metadata đến tài liệu cấu hình cho nhóm

Metadata có thể hỗ trợ công cụ, nhưng nhóm phát triển vẫn cần một bảng hợp đồng cấu hình dành cho vận hành. Ví dụ:

| Thuộc tính | Kiểu Java | Mặc định ứng dụng | Mô tả |
| --- | --- | --- | --- |
| `delivery.endpoint` | `URI` | Không có mặc định | Endpoint của API giao hàng |
| `delivery.connect-timeout` | `Duration` | 2 giây | Thời gian tối đa mở kết nối |
| `delivery.max-attempts` | `int` | 3 | Tổng lần gọi gồm lần đầu |
| `delivery.mode` | `String` hoặc enum | `STANDARD` | Chế độ xử lý yêu cầu |

Cần phân biệt “mặc định ứng dụng” trong bảng với trường metadata `defaultValue`. Bảng nên mô tả **behavior runtime thực sự** của class và nguồn cấu hình dùng chung; file JSON chỉ là một trong những đầu vào để tạo tài liệu.

Nếu một giá trị chỉ có ở `application-dev.yml` chứ không có trong class, tài liệu deployment phải nói rõ “giá trị của profile dev”, không nên ghi nhầm thành “default cho mọi môi trường”.

Khi soạn description cho người triển khai, nên bao gồm:

1. Mục đích của property.
2. Kiểu và đơn vị nếu cần.
3. Khi nào bắt buộc phải khai báo.
4. Giá trị hợp lệ hoặc phạm vi cho phép.
5. Mặc định runtime, nếu thật sự có.
6. Tác động khi thay đổi hoặc cấu hình sai.
7. Lưu ý bảo mật nếu property liên quan đến secret.

Không nhất thiết mọi thông tin đều nằm vừa trong một comment Javadoc ngắn. Nhưng nên bảo đảm description giúp người dùng hiểu **hợp đồng của thuộc tính**, không chỉ lặp lại tên field.

## 23. Những lỗi phổ biến khi tạo configuration metadata

### 23.1. Không thấy file spring-configuration-metadata.json

Nguyên nhân có thể là chưa thêm annotation processor, compiler không chạy annotation processing, class không được xử lý hoặc build output nằm ở thư mục khác.

Cách xử lý: kiểm tra cấu hình Gradle/Maven, biên dịch lại và tìm đúng `META-INF/spring-configuration-metadata.json` trong output.

### 23.2. Chỉ thêm @ConfigurationProperties nhưng quên processor

`@ConfigurationProperties` phục vụ binding; JSON metadata được sinh bởi processor. Một ứng dụng có thể đọc được YAML mà không có file metadata như mong muốn. Cần thêm `spring-boot-configuration-processor` nếu muốn tooling metadata tự động.

### 23.3. Nhầm comment // với Javadoc

```java
// Maximum attempts
private int maxAttempts;
```

Không nên kỳ vọng comment thông thường này xuất hiện dưới dạng `description`. Dùng:

```java
/**
 * Total delivery attempts including the initial request.
 */
private int maxAttempts;
```

### 23.4. Metadata type đúng nhưng value runtime lỗi

Trường `type=java.lang.Integer` chỉ cho công cụ biết kiểu dự kiến. Nếu YAML ghi `delivery.max-attempts=abc`, Binder vẫn không thể chuyển giá trị sang `int`. Không sửa vấn đề conversion chỉ bằng cách thay JSON metadata.

### 23.5. Metadata default khác giá trị đang chạy

Nếu class mặc định 3 nhưng deployment truyền `--delivery.max-attempts=8`, cả metadata `defaultValue=3` và runtime value 8 đều có thể đúng theo trách nhiệm của mình.

### 23.6. Khai defaultValue thủ công nhưng runtime không có default

Một entry JSON khai `"defaultValue": 3` không tự điền 3 vào một property thiếu ở runtime. Nếu cần mặc định thật, bổ sung vào class binding hoặc nguồn cấu hình có hiệu lực.

### 23.7. Description quá mơ hồ

`"Timeout."` không cho biết timeout nào, đơn vị nào hoặc đối tượng nào chịu ảnh hưởng. Hãy mô tả cụ thể “time allowed to establish a connection” và gợi ý đơn vị phù hợp.

### 23.8. Quá nhiều kiểu String

Dùng `String` cho timeout, size, endpoint và mode khiến metadata khó thể hiện cấu trúc và giảm khả năng conversion/validation có kiểu. Ưu tiên `Duration`, `DataSize`, `URI`, enum và kiểu thích hợp nếu binder hỗ trợ.

### 23.9. Lẫn annotation javax.validation của dự án cũ

Nếu muốn runtime validation trong Spring Boot 3, sử dụng các annotation phù hợp thuộc `jakarta.validation` và một validation provider. Metadata không thay thế việc chuẩn bị dependency validation.

### 23.10. Mô tả secret bằng giá trị thật

Không đưa token thật, password thật hay URL kèm thông tin xác thực vào Javadoc, metadata hint hoặc `defaultValue`. JSON metadata có thể nằm trong JAR và được IDE đọc; nó không phải kho bí mật.

### 23.11. Sửa file build output bằng tay

Sửa `build/classes/.../spring-configuration-metadata.json` có thể tạo kết quả tạm thời nhưng bị ghi đè ở lần compile sau. Hãy sửa source, annotation hoặc `additional-spring-configuration-metadata.json`.

### 23.12. Mặc định thời lượng không ghi đơn vị

Nếu description chỉ ghi “default: 3000” mà không nói mili giây hay giây, người dùng dễ nhầm. Nên mô tả bằng `3s` hoặc `3000ms` và dùng kiểu `Duration` để mã thể hiện ý nghĩa.

### 23.13. Không kiểm tra metadata của nested object

Nếu `delivery.retry.max-attempts` không có trong JSON, có thể processor chưa nhận diện kiểu lồng nhau. Kiểm tra cấu trúc Java và annotation hỗ trợ nested metadata khi thích hợp.

### 23.14. Nhầm metadata hint với giá trị bắt buộc

Một danh sách `values` trong `hints` thường nhằm hỗ trợ IDE; nó không nhất thiết là bộ kiểm tra tất cả giá trị đầu vào khi chạy. Với tập giá trị cố định, nên dùng enum hoặc validation.

### 23.15. Quên refresh IDE sau khi build

IDE có thể cache metadata từ lần build trước. Nếu JSON output đã cập nhật nhưng gợi ý vẫn cũ, reload project, build/indexing theo công cụ thay vì sửa YAML tùy tiện.

## 24. Cách kiểm tra metadata trong artifact cuối cùng

Khi đóng gói bằng Spring Boot Gradle plugin, tạo JAR:

```bash
./gradlew bootJar
```

Với Maven và plugin tương ứng, có thể dùng:

```bash
./mvnw package
```

Sau đó kiểm tra metadata trong output hoặc JAR. Với executable JAR của Spring Boot, các resource thuộc application thường nằm dưới vị trí tương ứng với `BOOT-INF/classes/META-INF/`.

Ví dụ đường dẫn mong đợi trong JAR:

```text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Cách bố trí có thể khác với ordinary library JAR. Với library module, resource metadata thường ở `META-INF/spring-configuration-metadata.json` ngay trong JAR. Điều quan trọng là metadata có sẵn trên classpath để IDE/tooling có thể đọc khi cần.

Nếu module có các `@ConfigurationProperties` dùng bởi ứng dụng khác, đóng gói metadata trong library JAR giúp các project tiêu thụ cũng được gợi ý khi khai báo property thuộc module đó.

Trong workspace nhiều module, nên kiểm tra metadata được sinh **ở đúng module khai báo properties**, không chỉ nhìn một output của ứng dụng tổng.

## 25. Tương thích giữa metadata, source code và phiên bản Spring Boot

Metadata là một định dạng được Spring Boot mô tả. Nhưng khả năng suy luận từ source code thay đổi theo loại class và phiên bản processor.

Các trường hợp cần chú ý:

- JavaBean với field/getter/setter.
- Constructor-bound class.
- Java record.
- Kotlin data class.
- Nested properties.
- Collection, Map và generic type.
- Property có mặc định từ annotation hay biểu thức khởi tạo.
- Property được cung cấp qua `@Bean` hoặc một adapter thư viện.

Với class khó suy luận, không nên hứa rằng compiler sẽ tự biết mọi thông tin. Hãy **kiểm tra output thật** và cung cấp metadata bổ sung nếu cần.

Đồng thời, khi dự án nâng cấp Spring Boot, nên để processor và runtime nằm trong cùng hệ thống quản lý phiên bản của Boot, tránh tự gắn một processor phiên bản quá xa so với những annotation hay kiểu nguồn đang sử dụng.

Đừng cố suy ra chính sách runtime chỉ từ metadata mà chưa xét bean registration, binding, conversion và validation của phiên bản ứng dụng.

## 26. Bài tập tự thực hành

### Bài 1 — Chọn description có ý nghĩa

Cho property `reports.max-rows` kiểu `int`. So sánh:

```text
A. Maximum rows.
B. Maximum number of data rows included in one exported report.
   Must be at least 1.
```

Mô tả B hữu ích hơn vì nói rõ **đối tượng bị giới hạn**, **thời điểm áp dụng** và **ràng buộc**. Hãy viết Javadoc tương ứng.

### Bài 2 — Dự đoán type

Cho:

```java
private String name;
private int maxRows;
private Duration flushInterval;
private URI uploadEndpoint;
private Map<String, Integer> rowLimits;
```

Hãy dự đoán `type` mà metadata có thể thể hiện cho từng property. Sau đó build và mở JSON để đối chiếu biểu diễn kiểu thực tế.

### Bài 3 — Phân biệt ba default

Class có `maxRows = 100`; YAML có `max-rows: 250`; dòng lệnh có `--reports.max-rows=500`. Hỏi:

1. Runtime bean thường nhận bao nhiêu?
2. Metadata compile-time có thể ghi mặc định bao nhiêu?
3. Nếu bỏ tham số dòng lệnh, giá trị runtime lấy từ đâu?
4. Nếu bỏ cả YAML và tham số, giá trị khởi tạo Java có ý nghĩa gì?

### Bài 4 — Viết record có @DefaultValue

Tạo `ReportProperties` với `Duration flushInterval` mặc định `5s`, `int maxRows` mặc định 100 và `boolean enabled` mặc định false. Đăng ký record qua `@EnableConfigurationProperties`, sau đó chạy ứng dụng không khai báo các khóa này để quan sát behavior.

### Bài 5 — Thêm metadata cho một String property

Một nhóm muốn người dùng chọn `reports.format` là `CSV` hoặc `JSON`. Viết `additional-spring-configuration-metadata.json` có một hint với hai giá trị và description tương ứng. Giải thích vì sao hint chưa thay thế enum hoặc validation.

### Bài 6 — Tìm lỗi trong JSON

Cho:

```json
{
  "properties": [
    {
      "name": "reports.max-rows",
      "type": "java.lang.Integer",
      "description": "Maximum number of exported data rows.",
      "defaultValue": 100
    }
  ]
}
```

Nếu Java không có default và YAML cũng không khai báo `reports.max-rows`, chỉ có JSON này có khiến ứng dụng tự lấy 100 không? Vì sao?

### Bài 7 — Metadata của nested class

Viết cấu hình:

```yaml
reports:
  export:
    timeout: 5s
    max-rows: 100
```

Tạo kiểu lồng nhau và kiểm tra JSON có `reports.export.timeout` cùng `reports.export.max-rows` hay không. Nếu thiếu, kiểm tra cấu trúc khai báo nested properties và phiên bản processor.

### Bài 8 — Phân biệt metadata và validation

Tạo property `reports.max-rows` mặc định 100, nhưng yêu cầu runtime không cho phép số 0. Viết Javadoc, thêm `@Min(1)` cùng `@Validated` và validation provider, rồi chạy với `--reports.max-rows=0`. Giải thích điều gì do metadata hỗ trợ và điều gì do validation runtime thực hiện.

### Bài 9 — Mô tả property deprecated

Một khóa `reports.output-path` được đổi thành `reports.destination`. Viết metadata deprecation với reason và replacement, rồi nêu những bước migration runtime vẫn phải thực hiện để deployment cũ không lỗi.

### Bài 10 — Quan sát khi dùng profile

Giữ Java default `5s`, đặt `flush-interval: 3s` trong `application.yml` và `1s` trong `application-prod.yml`. Chạy với profile prod và so sánh runtime `Duration` với default metadata. Tại sao hai con số khác nhau không có nghĩa annotation processor bị lỗi?

## 27. Tóm tắt quy trình làm việc thực tế

Khi thêm một nhóm cấu hình mới, có thể theo trình tự:

1. **Định nghĩa prefix và các property:** ví dụ `delivery.*`.
2. **Chọn kiểu Java có ý nghĩa:** `Duration` cho thời gian, `URI` cho endpoint, enum cho giá trị tập hợp cố định.
3. **Viết Javadoc:** làm rõ chức năng, đơn vị, phạm vi và điều kiện bắt buộc.
4. **Định nghĩa default runtime có chủ đích:** field initializer, `@DefaultValue` hoặc file cấu hình chung theo thiết kế.
5. **Đăng ký `@ConfigurationProperties`:** đảm bảo binder runtime thực sự tạo bean.
6. **Cấu hình `spring-boot-configuration-processor`:** để build sinh metadata.
7. **Kiểm tra `spring-configuration-metadata.json`:** xác nhận `name`, `type`, `description`, `defaultValue` nếu có.
8. **Thêm metadata bổ sung khi cần:** đặc biệt cho hints hoặc thuộc tính không thể tự suy luận.
9. **Kiểm thử cấu hình runtime:** thử thiếu property, sai kiểu, sai constraint và override theo profile.
10. **Không để secret trong metadata:** JSON có thể được phân phối cùng artifact.

Luồng tổng hợp:

```text
Source code @ConfigurationProperties
       |
       +-- Java type -----------> type
       |
       +-- Javadoc -------------> description
       |
       +-- Runtime default -----> defaultValue (nếu suy ra được)
       |
       +-- Additional metadata -> hints / thông tin bổ sung
       |
       v
spring-boot-configuration-processor
       |
       v
META-INF/spring-configuration-metadata.json
       |
       v
IDE gợi ý và hỗ trợ người viết cấu hình

Trong khi đó:

ENV / YAML / CLI / Profiles
       |
       v
Environment -> Binder -> Validation -> Bean runtime
```

Hai luồng này bổ sung nhau: metadata giúp **viết cấu hình đúng hơn**; binding và validation giúp **chạy cấu hình đúng hơn**.

## 28. Ghi nhớ

Ba trường metadata cần nhớ:

- **`description`**: cung cấp văn bản giải thích *thuộc tính dùng để làm gì*; thường lấy từ Javadoc hoặc metadata bổ sung.
- **`type`**: cho biết *kiểu Java của giá trị cấu hình*; thường do processor suy ra từ khai báo `@ConfigurationProperties`.
- **`defaultValue`**: mô tả *mặc định được nhận diện ở build-time*; có thể thiếu nếu không suy ra được. Đây **không phải** một nguồn default runtime tự động.

Spring Boot sinh metadata khi có processor phù hợp:

```text
org.springframework.boot:spring-boot-configuration-processor
```

File output thường là:

```text
META-INF/spring-configuration-metadata.json
```

Khi cần bổ sung mô tả hoặc gợi ý, có thể tạo:

```text
META-INF/additional-spring-configuration-metadata.json
```

Những điều không được đánh đồng:

1. Có metadata **không có nghĩa** ứng dụng tự kiểm tra mọi giá trị.
2. Có `defaultValue` trong JSON **không có nghĩa** Binder tự dùng nó khi thiếu property.
3. Metadata ghi kiểu `Integer` **không có nghĩa** một giá trị `abc` trở nên hợp lệ.
4. IDE gợi ý một tên khóa **không có nghĩa** property đó chắc chắn được cấp trong môi trường chạy.
5. Giá trị trên môi trường production **không nhất thiết** trùng default mô tả lúc biên dịch.

Viết metadata tốt là một phần của việc tạo ra **hợp đồng cấu hình dễ tìm, dễ hiểu và dễ duy trì**, đặc biệt khi codebase có nhiều module và nhiều nhóm `@ConfigurationProperties`.

Tài liệu tham khảo chính thức:

- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html)
- [Spring Boot — Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot — Adding Additional Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html#appendix.configuration-metadata.annotation-processor.adding-additional-metadata)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)