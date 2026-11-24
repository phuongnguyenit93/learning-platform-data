# @NestedConfigurationProperty khi cấu trúc lồng nhau cần được nhận diện rõ

Spring Boot cho phép gom các cấu hình liên quan thành những nhóm lồng nhau, chẳng hạn `acme.client.timeout`, `acme.client.base-url` hoặc `acme.security.enabled`. Khi cấu trúc lồng nhau dùng một class riêng nằm ngoài class `@ConfigurationProperties` gốc, **`@NestedConfigurationProperty` giúp configuration metadata processor nhận diện kiểu đó như một nhóm cấu hình con**.

Điểm cần phân biệt là annotation này chủ yếu phục vụ **metadata dành cho công cụ phát triển**. Nó không phải lệnh yêu cầu Spring Binder tạo object, không thay thế getter/setter hay constructor binding, và cũng không tự đăng ký reflection hints cho GraalVM Native Image. Runtime binding, configuration metadata và Spring AOT là ba công việc liên quan nhưng khác nhau.

Bài này xây dựng một cấu hình Spring Boot có nhóm lồng nhau, giải thích khi nào cần annotation, kiểm tra metadata được sinh ra và xác minh cấu hình trên JVM lẫn native executable.

## 1. Vì sao cần nhận diện cấu trúc lồng nhau?

Giả sử ứng dụng có cấu hình kết nối đến một dịch vụ bên ngoài:

~~~yaml
acme:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
    read-timeout: 5s
  security:
    enabled: true
    issuer-uri: https://identity.example.test
~~~

Các property có quan hệ theo nhóm:

- `acme.client.*` mô tả cấu hình HTTP client.
- `acme.security.*` mô tả cấu hình xác thực.
- Prefix `acme` gom chúng vào một nhóm cấu hình của ứng dụng.

Một class `@ConfigurationProperties` có thể biểu diễn cấu trúc đó bằng các object lồng nhau. Ví dụ, `AcmeProperties` có field `client` kiểu `ClientSettings` và field `security` kiểu `SecuritySettings`.

Có hai câu hỏi khác nhau:

1. **Spring Binder có bind được các property vào object không?** Đây là câu hỏi về runtime binding.
2. **IDE và công cụ metadata có hiển thị đúng các nhóm và property lồng nhau để autocomplete/documentation không?** Đây là câu hỏi về configuration metadata.

`@NestedConfigurationProperty` giúp câu hỏi thứ hai trong những trường hợp metadata processor không tự nhận ra kiểu lồng nhau.

## 2. Annotation thực sự làm gì?

`org.springframework.boot.context.properties.NestedConfigurationProperty` đánh dấu một field hoặc method trong class `@ConfigurationProperties` để **configuration metadata processor xem kiểu đó như một nested group**.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    @NestedConfigurationProperty
    private ClientSettings client = new ClientSettings();

    public ClientSettings getClient() {
        return client;
    }
}
~~~

Nếu `ClientSettings` là class độc lập bên ngoài `AcmeProperties`, annotation cho metadata processor biết rằng các thuộc tính của nó thuộc nhóm `acme.client`.

### Annotation không làm những việc sau

- Không tự tạo instance cho `ClientSettings`.
- Không tự bind property nếu object không thể được Spring Binder khởi tạo hoặc cập nhật.
- Không thay thế `@ConfigurationProperties`, `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.
- Không đăng ký reflection hints, resource hints hay JSON serialization hints.
- Không thay đổi cách Jackson bind request body.
- Không phải annotation để đánh dấu một bean Spring mới.

**Quy tắc quan trọng:** nếu ứng dụng bind thất bại ở runtime, thêm `@NestedConfigurationProperty` chưa chắc sửa được lỗi. Hãy kiểm tra cấu trúc class, khả năng khởi tạo, property name và cách đăng ký configuration properties.

## 3. Khi nào cần và khi nào không cần?

Configuration metadata processor có thể tự nhận diện một số cấu trúc lồng nhau. Annotation thường hữu ích nhất khi kiểu nested là **class độc lập** mà processor không thể suy ra đó là một nhóm cấu hình con từ cấu trúc source.

| Cấu trúc | Có cần `@NestedConfigurationProperty`? | Giải thích |
| --- | --- | --- |
| Nested class được khai báo bên trong class `@ConfigurationProperties` | Thường không | Metadata processor có thể nhận diện cấu trúc inner class |
| Field có kiểu là class độc lập, không mang `@ConfigurationProperties` riêng | Thường cần nếu muốn metadata biểu diễn nó như nested group | Annotation làm rõ ý định cho metadata processor |
| Field có kiểu là một class tự mang `@ConfigurationProperties` | Không cần cho mục đích nested metadata | Kiểu đó đã có metadata/configuration properties riêng |
| Collection hoặc array | Thường không | Metadata processor nhận diện kiểu phần tử theo quy tắc collection |
| Map | Thường không | Map được xử lý theo cấu trúc metadata tương ứng |
| Một object Java bất kỳ không liên quan tới cấu hình | Không | Không biến object đó thành cấu hình Spring |

Ví dụ nested class bên trong class cấu hình:

~~~java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    private final Client client = new Client();

    public Client getClient() {
        return client;
    }

    public static class Client {
        private URI baseUrl;

        public URI getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(URI baseUrl) {
            this.baseUrl = baseUrl;
        }
    }
}
~~~

Trong trường hợp này, `Client` là nested class của `AcmeProperties`; annotation thường không cần thiết để metadata processor nhận diện cấu trúc.

Ngược lại, nếu `ClientSettings` nằm trong file Java riêng và chỉ được tham chiếu bằng field, hãy cân nhắc thêm `@NestedConfigurationProperty` để metadata hiển thị rõ nhóm `acme.client`.

## 4. Ví dụ hoàn chỉnh với class lồng nhau độc lập

Tạo package `com.example.nativeimage.config`.

**`AcmeProperties.java`**

~~~java
package com.example.nativeimage.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.NestedConfigurationProperty;

@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    @NestedConfigurationProperty
    private final ClientSettings client = new ClientSettings();

    @NestedConfigurationProperty
    private final SecuritySettings security = new SecuritySettings();

    public ClientSettings getClient() {
        return client;
    }

    public SecuritySettings getSecurity() {
        return security;
    }
}
~~~

**`ClientSettings.java`**

~~~java
package com.example.nativeimage.config;

import java.net.URI;
import java.time.Duration;

public class ClientSettings {

    private URI baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(2);
    private Duration readTimeout = Duration.ofSeconds(5);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

**`SecuritySettings.java`**

~~~java
package com.example.nativeimage.config;

import java.net.URI;

public class SecuritySettings {

    private boolean enabled = true;
    private URI issuerUri;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public URI getIssuerUri() {
        return issuerUri;
    }

    public void setIssuerUri(URI issuerUri) {
        this.issuerUri = issuerUri;
    }
}
~~~

Đăng ký properties trong ứng dụng:

~~~java
package com.example.nativeimage;

import com.example.nativeimage.config.AcmeProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(AcmeProperties.class)
public class NativeImageApplication {

    public static void main(String[] args) {
        SpringApplication.run(NativeImageApplication.class, args);
    }
}
~~~

Có thể dùng `@ConfigurationPropertiesScan` thay cho `@EnableConfigurationProperties` nếu muốn quét các class properties trong package phù hợp. Chọn một cách đăng ký rõ ràng, tránh vô tình đăng ký cùng một properties class nhiều lần.

### Cấu hình YAML tương ứng

**`src/main/resources/application.yml`**

~~~yaml
acme:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
    read-timeout: 5s
  security:
    enabled: true
    issuer-uri: https://identity.example.test
~~~

Spring Boot Binder chuyển các tên kebab-case như `base-url` sang property Java tương ứng `baseUrl`, đồng thời chuyển chuỗi duration như `2s` thành `Duration`.

Trong ví dụ này, nested objects được khởi tạo trước bằng field initializer. Binder cập nhật giá trị thông qua JavaBean accessors. `@NestedConfigurationProperty` chỉ làm rõ nested group cho metadata; chính getter/setter và Binder mới tham gia quá trình bind thực tế.

## 5. Kiểm tra runtime binding độc lập với metadata

Có thể inject `AcmeProperties` vào một bean để quan sát giá trị đã bind:

~~~java
package com.example.nativeimage;

import com.example.nativeimage.config.AcmeProperties;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationReport implements CommandLineRunner {

    private final AcmeProperties properties;

    public ConfigurationReport(AcmeProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(String... args) {
        System.out.println("client.baseUrl="
                + properties.getClient().getBaseUrl());
        System.out.println("client.connectTimeout="
                + properties.getClient().getConnectTimeout());
        System.out.println("security.enabled="
                + properties.getSecurity().isEnabled());
    }
}
~~~

Với file YAML phía trên, giá trị dự kiến gồm:

~~~text
client.baseUrl=https://api.example.test
client.connectTimeout=PT2S
security.enabled=true
~~~

`Duration.toString()` biểu diễn hai giây dưới dạng `PT2S`. Nếu ứng dụng bind được các giá trị này, đó là bằng chứng runtime binding hoạt động trong lần chạy JVM đang kiểm tra. Nó chưa chứng minh metadata autocomplete được sinh đầy đủ, và cũng chưa chứng minh native executable bind thành công.

Có thể kiểm tra thêm bằng test:

~~~java
@SpringBootTest
class AcmePropertiesTests {

    @Autowired
    AcmeProperties properties;

    @Test
    void bindsNestedClientSettings() {
        assertEquals(
                URI.create("https://api.example.test"),
                properties.getClient().getBaseUrl()
        );
        assertEquals(
                Duration.ofSeconds(2),
                properties.getClient().getConnectTimeout()
        );
        assertTrue(properties.getSecurity().isEnabled());
    }
}
~~~

Ví dụ test cần import `URI`, `Duration`, các assertion JUnit tương ứng và chạy trong application context có cấu hình YAML mẫu.

## 6. Configuration metadata processor tạo ra gì?

Spring Boot cung cấp `spring-boot-configuration-processor`, một annotation processor đọc các class `@ConfigurationProperties` và tạo file metadata cho IDE, tài liệu và công cụ hỗ trợ cấu hình.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Đây là dependency phục vụ **compile-time annotation processing**. Không cần thêm nó như thư viện runtime của ứng dụng chỉ để Binder hoạt động.

Sau khi compile, metadata thường được tạo tại:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Với Gradle, vị trí thường là:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Đường dẫn cụ thể phụ thuộc build tool và cấu hình output. Có thể kiểm tra sau một lần compile sạch:

~~~bash
# Maven
./mvnw clean compile

# Gradle
./gradlew clean compileJava
~~~

Sau đó mở file metadata và tìm các property như:

~~~json
{
  "groups": [
    {
      "name": "acme.client",
      "type": "com.example.nativeimage.config.ClientSettings"
    },
    {
      "name": "acme.security",
      "type": "com.example.nativeimage.config.SecuritySettings"
    }
  ],
  "properties": [
    {
      "name": "acme.client.base-url",
      "type": "java.net.URI"
    },
    {
      "name": "acme.client.connect-timeout",
      "type": "java.time.Duration"
    },
    {
      "name": "acme.security.enabled",
      "type": "java.lang.Boolean"
    }
  ]
}
~~~

Đây là **ví dụ minh họa cấu trúc metadata**, không phải bản sao nguyên văn đầu ra của một phiên bản processor cụ thể. Metadata thực tế có thể có thêm `sourceType`, `defaultValue`, `description`, `deprecation` và các trường khác.

### Annotation ảnh hưởng đến metadata ra sao?

Nếu `ClientSettings` và `SecuritySettings` là các class độc lập, annotation giúp processor nhận diện chúng như các nhóm con của `AcmeProperties`. Kết quả mong muốn là công cụ IDE có thể gợi ý:

- `acme.client.base-url`
- `acme.client.connect-timeout`
- `acme.client.read-timeout`
- `acme.security.enabled`
- `acme.security.issuer-uri`

Nếu metadata thiếu một nhóm, hãy kiểm tra annotation processor có chạy hay không, class properties có được nhận diện đúng không và cấu trúc source có cho phép processor suy ra các property không.
## 7. Phân biệt configuration metadata với Spring AOT

Trong dự án Native Image, có ít nhất ba hoạt động khác nhau:

| Hoạt động | Công cụ | Mục tiêu | Kết quả |
| --- | --- | --- | --- |
| Configuration metadata processing | `spring-boot-configuration-processor` | Hỗ trợ IDE, autocomplete và tài liệu cấu hình | `spring-configuration-metadata.json` |
| Runtime configuration binding | Spring Boot Binder | Đọc property và bind vào object khi ứng dụng chạy hoặc trong quá trình chuẩn bị context phù hợp | Instance cấu hình đã nhận giá trị |
| Spring AOT processing | Spring Boot AOT engine | Phân tích application context và chuẩn bị mã/metadata cho native | Generated initialization code và runtime hints phù hợp |

`@NestedConfigurationProperty` tác động đến **metadata processing**. Nó không tự yêu cầu Spring AOT sinh thêm reflection hints và không phải cơ chế để native executable tìm thấy một class mà build không có.

Spring AOT nhận biết các configuration properties được đăng ký qua `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan` và chuẩn bị hỗ trợ cho binding trong native theo cơ chế của phiên bản Spring Boot đang dùng. Vì vậy, hãy bảo đảm class properties được đăng ký rõ ràng và nằm trong build input.

### Sơ đồ tổng quan

~~~mermaid
flowchart TD
    S["Class @ConfigurationProperties"] --> M["Configuration metadata processor"]
    S --> R["Spring configuration binding"]
    A["@NestedConfigurationProperty"] --> M
    M --> J["spring-configuration-metadata.json"]
    R --> B["Bind properties vào object"]
    B --> C["Spring AOT phân tích context"]
    C --> H["Generated code và runtime hints"]
    H --> N["GraalVM Native Image"]
    N --> X["Native runtime"]
~~~

Sơ đồ nhấn mạnh annotation đi vào nhánh metadata processor. Runtime binding và Spring AOT có đầu vào/chức năng riêng.

## 8. Tác động tới GraalVM Native Image

Khi build native, ứng dụng cần đảm bảo:

1. `AcmeProperties` được Spring nhận diện và đăng ký.
2. `ClientSettings` và `SecuritySettings` có thể được tạo hoặc cập nhật theo mô hình binding đã chọn.
3. Các property source cần thiết có trong runtime environment.
4. Các type converter cần thiết có sẵn.
5. AOT processing nhìn thấy cấu hình properties và sinh hỗ trợ phù hợp.
6. Native executable được kiểm thử với cùng bộ cấu hình mà ứng dụng sẽ sử dụng.

**Không thêm `@NestedConfigurationProperty` chỉ để sửa lỗi native reflection.** Nếu lỗi xuất hiện ở native nhưng JVM hoạt động, cần đọc exception cụ thể và xác định tầng lỗi: thiếu configuration properties registration, lỗi constructor/binding, converter, reflection hoặc một thư viện JSON khác.

### Build và kiểm thử

Với Maven project đã cấu hình Spring AOT và native profile:

~~~bash
./mvnw -Pnative clean native:compile
~~~

Với Gradle project đã cấu hình Native Build Tools:

~~~bash
./gradlew clean nativeCompile
~~~

Lệnh cụ thể phụ thuộc cấu hình plugin/profile của project. Sau build, chạy native executable với file `application.yml` hoặc environment variables tương ứng và xác nhận các giá trị nested đã bind đúng.

Nên chạy cùng test trên JVM và native:

- Kiểm tra giá trị mặc định khi không cung cấp property.
- Kiểm tra nested property được override bằng YAML.
- Kiểm tra cùng property qua environment variable.
- Kiểm tra conversion cho `URI`, `Duration`, enum hoặc kiểu custom.
- Kiểm tra validation nếu cấu hình có ràng buộc.
- Kiểm tra property bắt buộc bị thiếu hoặc sai định dạng.

Nếu dùng environment variables, Spring Boot relaxed binding thường ánh xạ các tên như `ACME_CLIENT_CONNECTTIMEOUT` theo quy tắc tên property. Hãy kiểm tra quy tắc chính xác và tránh tự suy ra tên biến từ tên field; đặc biệt với dấu gạch nối, collection index và map key.

## 9. Nested properties với immutable objects và constructor binding

Không phải mọi cấu hình đều dùng JavaBean setter. Spring Boot cũng hỗ trợ constructor binding cho configuration properties bất biến, bao gồm record trong các phiên bản Java/Spring Boot phù hợp.

Ví dụ record:

~~~java
@ConfigurationProperties(prefix = "acme")
public record AcmeProperties(
        ClientSettings client,
        SecuritySettings security
) {
    public record ClientSettings(
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout
    ) {
    }

    public record SecuritySettings(
            boolean enabled,
            URI issuerUri
    ) {
    }
}
~~~

Trong mô hình này, nested record nằm trong cấu trúc properties và Spring Binder tạo object theo constructor binding. `@NestedConfigurationProperty` không phải annotation kích hoạt constructor binding. Việc nhận diện metadata cho inner types và khả năng binding được quyết định bởi cấu trúc type, cách đăng ký properties và phiên bản Spring Boot.

Nếu dùng nested class độc lập trong immutable configuration, hãy kiểm tra constructor/record component và cách binder suy ra property names. Không thêm annotation metadata để thay thế constructor binding contract.

### Validation cho nhóm lồng nhau

Có thể dùng Bean Validation để kiểm tra nested group:

~~~java
@ConfigurationProperties(prefix = "acme")
@Validated
public class AcmeProperties {

    @Valid
    @NestedConfigurationProperty
    private final ClientSettings client = new ClientSettings();

    public ClientSettings getClient() {
        return client;
    }
}
~~~

Field lồng nhau dùng `@Valid` để cascade validation nếu `ClientSettings` có các constraint như `@NotNull`, `@NotBlank` hoặc `@Min`. `@NestedConfigurationProperty` vẫn chỉ phục vụ metadata processor; hai annotation giải quyết hai nhiệm vụ khác nhau.

## 10. Đừng nhầm với JSON binding của Jackson

Tên module có cả Binding và JSON, nên cần phân biệt rõ:

- `@ConfigurationProperties` bind cấu hình ứng dụng từ properties, YAML, environment variables và các property sources khác.
- Jackson bind JSON request/response thành object Java, thường qua `@RequestBody`, `ObjectMapper`, serializer/deserializer.
- `@NestedConfigurationProperty` không điều khiển Jackson serialization/deserialization.

Ví dụ JSON request:

~~~json
{
  "customer": {
    "id": "C-100",
    "name": "Lan"
  }
}
~~~

Nếu `OrderRequest` có field `CustomerRequest customer`, Jackson sẽ xử lý nested JSON dựa trên cấu trúc class, constructor, accessors, annotations và cấu hình ObjectMapper. Thêm `@NestedConfigurationProperty` lên field đó không phải cách để Jackson nhận diện nested JSON.

Trong Native Image, Jackson có thể cần reflection/binding metadata hoặc integration hints tùy kiểu DTO và cách cấu hình. Đó là chủ đề riêng với configuration metadata do `spring-boot-configuration-processor` tạo ra.

## 11. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| IDE không gợi ý `acme.client.*` | Metadata processor chưa chạy hoặc nested type chưa được nhận diện | Kiểm tra dependency annotation processor và `@NestedConfigurationProperty` |
| Metadata có group nhưng runtime không bind | Class chưa đăng ký, object không khởi tạo được hoặc accessors không phù hợp | Kiểm tra `@EnableConfigurationProperties`, scan, constructor/getter/setter |
| JVM bind được nhưng native không bind | AOT/native configuration khác, class hoặc converter không được nhận diện | Kiểm tra AOT log, exception gốc và native test |
| Thêm annotation nhưng không thay đổi runtime | Hành vi đúng vì annotation không điều khiển binding | Sửa cấu trúc class hoặc đăng ký properties theo yêu cầu thực tế |
| Nested property bị null | Object không được khởi tạo hoặc binder không thể tạo nested type theo mô hình đã chọn | Kiểm tra field initializer, setter hoặc constructor binding |
| `Duration`/`URI` conversion lỗi | Giá trị cấu hình sai hoặc converter không phù hợp | Kiểm tra input format và conversion service |
| Property không xuất hiện trong metadata | Annotation processor không thấy source hoặc kiểu lồng nhau chưa được đánh dấu | Kiểm tra compile task và output metadata JSON |
| JSON request không bind nested object | Jackson DTO/constructor/accessors hoặc hints chưa đúng | Kiểm tra ObjectMapper và JSON binding metadata; annotation nested config không liên quan |

### Quy trình điều tra theo đúng tầng

1. **IDE/autocomplete sai:** kiểm tra `spring-boot-configuration-processor`, compile output và metadata JSON.
2. **JVM runtime binding sai:** kiểm tra prefix, property name, đăng ký configuration properties, object construction và type conversion.
3. **Native runtime binding sai:** so sánh JVM/native cùng input, xem AOT/native logs và lỗi gốc.
4. **JSON request binding sai:** kiểm tra DTO, Jackson configuration, constructor/accessors và native hints dành cho JSON.
5. **Sau khi sửa:** build sạch, đọc lại metadata nếu thay đổi cấu trúc source và chạy test trên native executable.

## 12. Bài thực hành: thêm một nested group vào cấu hình native

Tạo một Spring Boot application với prefix `acme` và class `AcmeProperties`. Tách `ClientSettings` thành class Java độc lập; thêm `@NestedConfigurationProperty` lên field `client`.

Thực hiện:

1. Khai báo `spring-boot-configuration-processor` trong Maven hoặc Gradle annotation processor.
2. Đăng ký `AcmeProperties` bằng `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.
3. Tạo `application.yml` có `acme.client.base-url`, `connect-timeout`, `read-timeout`.
4. Compile và mở `META-INF/spring-configuration-metadata.json`; xác minh group/property lồng nhau xuất hiện.
5. Chạy trên JVM, inject `AcmeProperties` và kiểm tra giá trị đã bind.
6. Build native executable bằng Spring AOT/GraalVM.
7. Chạy native với cùng YAML và environment variables; so sánh kết quả.
8. Bỏ annotation trong một nhánh thử nghiệm, compile lại và quan sát ảnh hưởng đến metadata; xác minh runtime binding không được kết luận chỉ từ thay đổi metadata.
9. Tạo một JSON request DTO có cấu trúc nested tương tự và kiểm thử riêng để chứng minh annotation này không điều khiển Jackson.

### Câu hỏi tự kiểm tra

1. `@NestedConfigurationProperty` được dùng bởi thành phần nào của Spring Boot?
2. Vì sao annotation có thể cải thiện IDE autocomplete nhưng không làm thay đổi runtime binding?
3. Khi nào nested class được nhận diện mà không cần annotation?
4. Vì sao `spring-boot-configuration-processor` không phải dependency runtime bắt buộc?
5. Configuration metadata JSON khác generated code của Spring AOT ở điểm nào?
6. Nếu nested property bind được trên JVM nhưng native thất bại, nên kiểm tra những lớp vấn đề nào?
7. `@NestedConfigurationProperty` có tác động đến Jackson `@RequestBody` không? Vì sao?
8. Vì sao phải kiểm tra cả metadata JSON lẫn native executable?

**Tiêu chí đạt:** giải thích đúng vai trò metadata của `@NestedConfigurationProperty`; chọn đúng trường hợp cần đánh dấu nested type độc lập; cấu hình được `@ConfigurationProperties` và nested binding; kiểm tra được configuration metadata do annotation processor tạo ra; phân biệt metadata với runtime binding và Spring AOT; đồng thời xác minh cấu hình hoạt động trên native executable mà không nhầm annotation này với Jackson hints.
