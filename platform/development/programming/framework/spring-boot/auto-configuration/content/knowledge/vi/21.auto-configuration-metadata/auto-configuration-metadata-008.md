# Metadata thuộc tính lỗi thời và hướng dẫn khóa thay thế

## 1. Vì sao cần đánh dấu property đã lỗi thời?

Properties là một phần API công khai của thư viện Spring Boot. Người dùng có thể lưu chúng trong `application.yml`, `application.properties`, biến môi trường, ConfigMap, Helm chart, pipeline triển khai hoặc tham số command line. Khi một key cần đổi tên, đổi ý nghĩa hoặc bị loại bỏ, việc thay đổi âm thầm có thể khiến ứng dụng:

- Tiếp tục dùng key cũ mà không biết key đó sắp bị loại bỏ.
- Không biết key mới nào thay thế key cũ.
- Bị mất cấu hình sau khi nâng phiên bản thư viện.
- Dùng một giá trị mặc định khác vì key cũ không còn được bind.
- Có tài liệu và gợi ý IDE không khớp với hành vi runtime.

Spring Boot cung cấp **configuration metadata** để IDE và công cụ hỗ trợ cấu hình hiển thị tên property, kiểu dữ liệu, mô tả, default và thông tin deprecation. Khi một property lỗi thời, metadata có thể chỉ ra:

- Mức độ deprecation: `warning` hoặc `error`.
- Lý do property bị thay thế.
- Tên đầy đủ của property thay thế.
- Phiên bản bắt đầu deprecate.

Trong bài này, ví dụ dùng Java 17 và Spring Boot 3.3.13. Đây là baseline minh họa để mã và dependency cụ thể; với dự án thực tế, dùng đúng release line mà thư viện hỗ trợ.

**Điểm quan trọng:** deprecation metadata giúp người dùng biết phải sửa cấu hình. Nó không tự thực hiện migration key, không tự chuyển giá trị cũ sang key mới và không tự phát log cảnh báo ở runtime.

## 2. Configuration metadata nằm ở đâu?

Spring Boot đóng gói metadata trong JAR tại:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Metadata được chia thành một số nhóm:

| Nhóm | Mục đích |
| --- | --- |
| `groups` | Mô tả nhóm/prefix cấu hình, ví dụ `acme.client` |
| `properties` | Mô tả từng key có giá trị, ví dụ `acme.client.endpoint` |
| `hints` | Gợi ý giá trị hợp lệ hoặc nguồn cung cấp gợi ý cho IDE |
| `ignored` | Các property bị chủ động loại khỏi metadata được tạo |

Ví dụ cấu trúc rút gọn:

~~~json
{
  "groups": [
    {
      "name": "acme.client",
      "type": "com.acme.ClientProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.client.endpoint",
      "type": "java.lang.String",
      "description": "Base endpoint used by the client."
    }
  ],
  "hints": []
}
~~~

File này chủ yếu phục vụ trải nghiệm phát triển: autocomplete, contextual help, validation/gợi ý trong IDE và tài liệu cấu hình. Annotation processor tạo phần lớn metadata từ class được đánh dấu `@ConfigurationProperties`; các trường hợp đặc biệt có thể bổ sung metadata thủ công.

Đừng nhầm metadata với runtime configuration:

- `@ConfigurationProperties` và Binder quyết định giá trị nào được bind vào object.
- `@DeprecatedConfigurationProperty` giúp annotation processor tạo metadata deprecation.
- `additional-spring-configuration-metadata.json` bổ sung hoặc điều chỉnh metadata.
- Code migration/alias hoặc việc loại bỏ accessor mới quyết định runtime còn chấp nhận key cũ hay không.

## 3. Bốn trường deprecation trong metadata

Trong mỗi phần tử của mảng `properties`, thông tin deprecation nằm trong object `deprecation`:

~~~json
{
  "name": "acme.client.url",
  "type": "java.lang.String",
  "deprecation": {
    "level": "warning",
    "reason": "Use the endpoint property instead.",
    "replacement": "acme.client.endpoint",
    "since": "2.0.0"
  }
}
~~~

| Trường | Ý nghĩa | Cách viết tốt |
| --- | --- | --- |
| `level` | Mức độ deprecation: `warning` hoặc `error`; mặc định là `warning` | Chọn theo việc property còn được hỗ trợ hay đã ngừng quản lý |
| `reason` | Lý do ngắn gọn khiến property bị deprecate | Nêu vấn đề và hành động người dùng nên làm |
| `replacement` | Tên đầy đủ của property thay thế | Dùng canonical key, ví dụ `acme.client.endpoint` |
| `since` | Phiên bản bắt đầu deprecate | Ghi version thư viện/Boot mà contract công bố deprecation |

### 3.1. level=warning

`warning` là mức mặc định. Property vẫn được xem là còn hỗ trợ trong giai đoạn chuyển tiếp. Công cụ cấu hình có thể hiển thị cảnh báo và gợi ý property thay thế, trong khi thư viện vẫn giữ khả năng bind key cũ.

Ví dụ:

~~~json
{
  "name": "acme.client.url",
  "type": "java.lang.String",
  "deprecation": {
    "level": "warning",
    "reason": "Renamed to make the meaning explicit.",
    "replacement": "acme.client.endpoint",
    "since": "2.0.0"
  }
}
~~~

Dùng mức này khi thư viện còn giữ getter/setter hoặc constructor binding để tương thích ngược. Người dùng có thời gian chuyển cấu hình trước khi key cũ bị loại bỏ.

### 3.2. level=error

`error` biểu thị property đã không còn được quản lý/hỗ trợ và metadata không xem nó là key còn bind. Đây là tín hiệu mạnh để IDE/công cụ cảnh báo người dùng không tiếp tục sử dụng key cũ.

Ví dụ:

~~~json
{
  "name": "acme.client.legacy-url",
  "type": "java.lang.String",
  "deprecation": {
    "level": "error",
    "reason": "This property was removed. Configure the endpoint property instead.",
    "replacement": "acme.client.endpoint",
    "since": "3.0.0"
  }
}
~~~

Cần phân biệt **metadata báo key đã bị loại bỏ** với **runtime code thực sự không còn bind key đó**. Metadata JSON là dữ liệu mô tả cho tooling; chỉ thêm `level=error` không tự viết logic chuyển đổi, không tự xóa field Java và không tự tạo exception trong Spring Binder. Khi muốn key cũ không còn được bind, hãy loại accessor/constructor parameter tương ứng hoặc triển khai chính sách từ chối rõ ràng ở runtime. Metadata error giúp người dùng biết key đã ngừng hỗ trợ.

### 3.3. reason

Viết lý do có thể hành động được. Ví dụ tốt:

~~~text
The url property was renamed to endpoint to clarify that it is a base URI.
Use acme.client.endpoint instead.
~~~

Tránh lý do mơ hồ như `Old property`, `Deprecated` hoặc `Use new config`. Nên cho biết:

1. Điều gì thay đổi.
2. Vì sao thay đổi.
3. Người dùng cần cấu hình key nào.

Mô tả nên ngắn, dễ đọc trong IDE. Spring Boot khuyến nghị viết thành đoạn ngắn; dòng đầu nêu ý chính và dòng cuối kết thúc bằng dấu chấm.

### 3.4. replacement

`replacement` là **tên đầy đủ của property mới**, không phải tên field Java và không phải chỉ phần suffix.

Đúng:

~~~json
"replacement": "acme.client.endpoint"
~~~

Không rõ ràng:

~~~json
"replacement": "endpoint"
~~~

Nếu property cũ không có một property thay thế trực tiếp, có thể bỏ trường `replacement`. Trong trường hợp cần chuyển nhiều key cũ thành một cấu trúc mới, hãy mô tả mapping chi tiết trong reason, migration guide và release notes; một trường replacement đơn lẻ không diễn tả đầy đủ phép biến đổi phức tạp.

## 4. Dùng @DeprecatedConfigurationProperty trong code

Spring Boot cung cấp annotation:

~~~java
org.springframework.boot.context.properties.DeprecatedConfigurationProperty
~~~

Annotation này:

- Phải đặt trên **getter** của property lỗi thời trong class `@ConfigurationProperties`.
- Cho annotation processor biết property cần tạo deprecation metadata.
- Có các thuộc tính `reason`, `replacement`, `since`.
- Không có thuộc tính `level`; metadata sinh tự động luôn giả định `warning`, vì code vẫn xử lý property đó.
- **Không ảnh hưởng trực tiếp đến quá trình binding.**

Nên dùng cùng annotation Java `@Deprecated` để code Java/Kotlin tiêu thụ accessor cũ cũng nhận biết API đã lỗi thời.

### 4.1. Ví dụ: đổi acme.client.url thành acme.client.endpoint

Giả sử version 2.0 của thư viện đổi tên key từ:

~~~yaml
acme:
  client:
    url: https://api.example.test
~~~

sang:

~~~yaml
acme:
  client:
    endpoint: https://api.example.test
~~~

Trong giai đoạn tương thích, class properties có thể giữ cả hai accessor:

**ClientProperties.java**

~~~java
package com.acme.client;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;

@ConfigurationProperties(prefix = "acme.client")
public class ClientProperties {

    private String endpoint;

    // Accessor cũ được giữ để tương thích với cấu hình đã phát hành.
    private String url;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    @Deprecated
    @DeprecatedConfigurationProperty(
            reason = "The url property was renamed to endpoint for clarity. "
                    + "Use acme.client.endpoint instead.",
            replacement = "acme.client.endpoint",
            since = "2.0.0")
    public String getUrl() {
        return url;
    }

    @Deprecated
    public void setUrl(String url) {
        this.url = url;
    }

    /**
     * The new property takes precedence when both keys are configured.
     */
    public String effectiveEndpoint() {
        return endpoint != null ? endpoint : url;
    }
}
~~~

Giải thích:

- `getEndpoint()/setEndpoint()` tạo property mới `acme.client.endpoint`.
- `getUrl()/setUrl()` vẫn cho Binder nhận property cũ `acme.client.url`.
- `@Deprecated` đánh dấu accessor Java cũ.
- `@DeprecatedConfigurationProperty` đặt trên getter cũ để processor sinh metadata.
- `effectiveEndpoint()` là logic runtime do thư viện tự viết: dùng key mới nếu có; nếu không, fallback sang key cũ.

**Chú ý:** Spring Boot không tự gọi `effectiveEndpoint()` và cũng không tự hiểu `replacement` là alias. Thư viện chủ động giữ hai property và định nghĩa cách chọn giá trị. Nếu cả hai key cùng xuất hiện, ví dụ này quy định key mới thắng. Đây là chính sách của code, cần được test và ghi trong tài liệu.

### 4.2. Metadata tự sinh dự kiến

Sau khi compile với configuration processor, metadata sẽ có property mới và property cũ. Phần deprecation của key cũ có dạng tương tự:

~~~json
{
  "name": "acme.client.url",
  "type": "java.lang.String",
  "sourceType": "com.acme.client.ClientProperties",
  "deprecation": {
    "level": "warning",
    "reason": "The url property was renamed to endpoint for clarity. Use acme.client.endpoint instead.",
    "replacement": "acme.client.endpoint",
    "since": "2.0.0"
  }
}
~~~

Metadata processor có thể sinh thêm description, group và source information. Ví dụ trên chỉ minh họa phần quan trọng cần kiểm tra; không phải toàn bộ file JSON.

### 4.3. Không đặt annotation lên setter thay cho getter

Sai mục đích:

~~~java
@DeprecatedConfigurationProperty(replacement = "acme.client.endpoint")
public void setUrl(String url) {
    this.url = url;
}
~~~

Đúng:

~~~java
@DeprecatedConfigurationProperty(replacement = "acme.client.endpoint")
public String getUrl() {
    return url;
}
~~~

Annotation được thiết kế cho getter và annotation processor tìm deprecation metadata từ getter. Có thể đồng thời đánh dấu setter bằng `@Deprecated`, nhưng `@DeprecatedConfigurationProperty` phải nằm trên getter.

## 5. Bổ sung metadata thủ công bằng additional-spring-configuration-metadata.json

Có những trường hợp không thể giữ getter cũ chỉ để sinh metadata:

- Property đã bị xóa khỏi Java class.
- Property không bind vào `@ConfigurationProperties` class.
- Muốn tiếp tục hiển thị thông tin deprecation sau khi accessor cũ bị loại bỏ.
- Cần đặt `level=error`, điều mà `@DeprecatedConfigurationProperty` không hỗ trợ.
- Muốn điều chỉnh description, default hoặc deprecation của metadata được sinh tự động.

Khi đó, tạo file:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

### 5.1. Giữ hint sau khi xóa accessor cũ

Giả sử version 3.0 đã xóa `getUrl()/setUrl()`, chỉ còn property `acme.client.endpoint`. Ta vẫn muốn IDE báo key cũ không còn được hỗ trợ:

~~~json
{
  "properties": [
    {
      "name": "acme.client.url",
      "type": "java.lang.String",
      "description": "Removed in version 3.0.0. Configure acme.client.endpoint instead.",
      "deprecation": {
        "level": "error",
        "reason": "The url property was removed in 3.0.0. Configure endpoint instead.",
        "replacement": "acme.client.endpoint",
        "since": "3.0.0"
      }
    }
  ]
}
~~~

File bổ sung được annotation processor merge vào file metadata chính. Khi property đã không còn trong class properties, entry thủ công vẫn có thể giữ thông tin để tooling nhận biết key cũ.

**Runtime vẫn phải được xử lý bằng code thực tế:** nếu class không còn accessor `url` hoặc constructor parameter tương ứng, Binder không có property đích để bind theo mô hình JavaBean/constructor hiện tại. File JSON không thay thế việc loại accessor hay viết migration logic.

### 5.2. Bổ sung deprecation cho property được phát hiện tự động

Nếu annotation processor đã tìm thấy `acme.client.url`, manual metadata có thể ghi đè các trường metadata như description, default value và deprecation khi những trường này được cung cấp.

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "acme.client.url",
      "deprecation": {
        "level": "warning",
        "reason": "Use the endpoint property instead.",
        "replacement": "acme.client.endpoint",
        "since": "2.0.0"
      }
    }
  ]
}
~~~

Chỉ cần `name` để nhận diện property đã tồn tại; các trường được cung cấp sẽ điều chỉnh metadata tương ứng. Nếu property không được phát hiện trong module hiện tại, entry thủ công có thể được thêm như một property metadata mới.

### 5.3. Khi nào dùng ignored thay vì deprecation?

Metadata có phần `ignored.properties` để loại những property bị chủ động bỏ qua khỏi danh sách metadata được tạo. Đây không phải cách thay thế cho deprecation guidance:

- Dùng `deprecation` khi muốn người dùng thấy key cũ và biết key thay thế.
- Dùng `ignored` khi muốn loại một property khỏi metadata do nó không nên được gợi ý như cấu hình được hỗ trợ.
- Không xóa property khỏi metadata chỉ vì nó cũ nếu người dùng cần thông tin migration.

## 6. Tạo metadata bằng Spring Boot Configuration Processor

Dependency processor thường được khai báo là optional vì đây là công cụ build-time:

**Maven**

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Nếu cấu hình annotation processor tường minh bằng Maven Compiler Plugin:

~~~xml
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
                        <version>3.3.13</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong ví dụ trên, phiên bản processor được căn chỉnh với Spring Boot 3.3.13. Nếu build có Lombok hoặc annotation processor khác, hãy khai báo chúng trong `annotationProcessorPaths` và bảo đảm thứ tự xử lý phù hợp.

**Gradle**

~~~groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-configuration-processor:3.3.13"
}
~~~

Nếu dùng `additional-spring-configuration-metadata.json` với Gradle, task `compileJava` cần phụ thuộc vào `processResources` để metadata bổ sung có mặt khi annotation processor chạy:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

Sau khi build, kiểm tra:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Và trong JAR đã đóng gói:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Đừng chỉ kiểm tra source JSON trong `src/main/resources`: cần xác nhận file metadata cuối cùng sau khi processor merge đã được tạo và đóng gói vào artifact phát hành.

## 7. Ví dụ project Maven hoàn chỉnh và test migration

Ví dụ dưới đây minh họa giai đoạn version 2.0: key mới là `acme.client.endpoint`, key cũ `acme.client.url` vẫn bind với mức warning và được chuyển thành giá trị hiệu lực theo quy tắc new-key-wins.

### 7.1. Cấu trúc

~~~text
client-metadata-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/client/
    │   │   └── ClientProperties.java
    │   └── resources/
    └── test/
        └── java/com/acme/client/
            └── ClientPropertiesTests.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>client-metadata-demo</artifactId>
    <version>2.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. ClientProperties.java

Tạo file `src/main/java/com/acme/client/ClientProperties.java` bằng class đầy đủ ở mục 4.1.

### 7.4. ClientPropertiesTests.java

~~~java
package com.acme.client;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClientPropertiesTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PropertiesConfiguration.class);

    @Test
    void legacyKeyStillBindsDuringWarningPeriod() {
        runner.withPropertyValues(
                "acme.client.url=https://legacy.example.test")
                .run(context -> {
                    assertThat(context).hasSingleBean(ClientProperties.class);

                    ClientProperties properties =
                            context.getBean(ClientProperties.class);

                    assertThat(properties.getUrl())
                            .isEqualTo("https://legacy.example.test");
                    assertThat(properties.effectiveEndpoint())
                            .isEqualTo("https://legacy.example.test");
                });
    }

    @Test
    void replacementKeyBinds() {
        runner.withPropertyValues(
                "acme.client.endpoint=https://new.example.test")
                .run(context -> {
                    ClientProperties properties =
                            context.getBean(ClientProperties.class);

                    assertThat(properties.getEndpoint())
                            .isEqualTo("https://new.example.test");
                    assertThat(properties.effectiveEndpoint())
                            .isEqualTo("https://new.example.test");
                });
    }

    @Test
    void replacementWinsWhenBothKeysArePresent() {
        runner.withPropertyValues(
                "acme.client.url=https://legacy.example.test",
                "acme.client.endpoint=https://new.example.test")
                .run(context -> {
                    ClientProperties properties =
                            context.getBean(ClientProperties.class);

                    assertThat(properties.effectiveEndpoint())
                            .isEqualTo("https://new.example.test");
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class PropertiesConfiguration {
    }
}
~~~

Chạy:

~~~bash
mvn clean test
~~~

Kỳ vọng **ba test pass**:

1. Key cũ vẫn bind trong giai đoạn warning.
2. Key mới bind bình thường.
3. Nếu cả hai key cùng có, code của thư viện chọn key mới.

Các lời gọi `getUrl()` trong test có thể tạo compiler deprecation warning. Điều đó là có chủ đích: test đang xác nhận tương thích của accessor cũ.

### 7.5. Kiểm tra metadata được sinh

Sau `mvn clean test`, kiểm tra file:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Tìm `acme.client.url` và xác nhận có:

~~~json
"deprecation": {
  "level": "warning",
  "reason": "The url property was renamed to endpoint for clarity. Use acme.client.endpoint instead.",
  "replacement": "acme.client.endpoint",
  "since": "2.0.0"
}
~~~

Có thể kiểm tra bằng lệnh:

~~~bash
grep -n -A8 -B2 '"name": "acme.client.url"' target/classes/META-INF/spring-configuration-metadata.json
~~~

Trên PowerShell:

~~~powershell
Select-String -Path target/classes/META-INF/spring-configuration-metadata.json -Pattern 'acme.client.url' -Context 0,8
~~~

Nội dung metadata có thể khác về thứ tự field hoặc thêm thuộc tính khác. Điều cần xác nhận là đúng tên property, mức warning, lý do, replacement và since.

## 8. Lộ trình deprecation an toàn qua nhiều release

Không nên deprecate và xóa property cùng lúc nếu thư viện đã có người dùng. Một lộ trình dễ quản lý:

### Giai đoạn A — giới thiệu key mới

Version 2.0:

- Công bố `acme.client.endpoint`.
- Giữ `acme.client.url` để tương thích.
- Gắn `@Deprecated` và `@DeprecatedConfigurationProperty` lên getter cũ.
- Đặt metadata level mặc định là warning.
- Nếu cả hai key xuất hiện, quy định rõ key nào thắng.
- Cập nhật tài liệu, ví dụ YAML, release notes và migration guide.

### Giai đoạn B — nhắc lại và đo mức sử dụng

Trong các bản patch/minor tiếp theo:

- Duy trì alias runtime theo chính sách đã công bố.
- Nêu thời điểm dự kiến bỏ key cũ.
- Nếu có telemetry/logging, chỉ ghi cảnh báo theo cách không làm lộ giá trị property hoặc secret; không log raw config.
- Không tự thêm startup warning cho mọi người dùng nếu thư viện chưa có chính sách logging rõ ràng.
- Kiểm thử cả cấu hình chỉ có key cũ và chỉ có key mới.

### Giai đoạn C — bỏ runtime alias

Trong một major release có breaking change:

- Xóa getter/setter cũ hoặc constructor parameter cũ.
- Giữ property mới và kiểm thử rằng key mới vẫn bind.
- Thêm manual metadata với `level=error`, replacement và since để IDE vẫn giải thích key cũ.
- Cập nhật migration guide, changelog và ví dụ cấu hình.
- Nếu muốn từ chối rõ ràng khi ứng dụng vẫn khai báo key cũ, triển khai kiểm tra riêng (ví dụ kiểm tra Environment sớm hoặc validation có chủ đích); metadata error một mình không tạo runtime exception.

### Giai đoạn D — dọn metadata khi không còn cần thiết

Sau một hoặc nhiều release, nếu không còn nhu cầu nhắc người dùng về key cũ, có thể loại entry metadata lỗi thời. Quyết định này tùy vòng đời thư viện và nhu cầu hỗ trợ migration; đừng xóa hướng dẫn khi vẫn còn một lượng cấu hình cũ đáng kể.

## 9. Các trường hợp replacement không đơn giản

### 9.1. Đổi tên một-một

Đây là trường hợp dễ nhất:

~~~text
acme.client.url  ->  acme.client.endpoint
~~~

Metadata có thể dùng trực tiếp `replacement`.

### 9.2. Một key cũ tách thành nhiều key mới

Ví dụ:

~~~text
acme.client.timeout
    -> acme.client.connect-timeout
    -> acme.client.read-timeout
~~~

Một trường `replacement` không thể mô tả hai key thay thế. Hãy viết reason chỉ rõ mapping, cung cấp migration guide và triển khai runtime chuyển đổi theo quy tắc đã công bố. Không chọn tùy tiện một replacement rồi để người dùng nghĩ đó là mapping đầy đủ.

### 9.3. Nhiều key cũ hợp nhất thành một object

Ví dụ:

~~~text
acme.client.ssl-key-store
acme.client.ssl-key-store-password
    -> acme.client.ssl.bundle
~~~

Có thể chỉ định replacement cùng nhóm mới nếu hợp lý, nhưng phải mô tả cách chuyển giá trị, nơi lưu secret và những thuộc tính nào không còn tương đương. Một key replacement không thể mang theo toàn bộ dữ liệu của hai key cũ.

### 9.4. Đổi kiểu dữ liệu

Ví dụ key cũ là milliseconds dạng integer, key mới là `Duration`:

~~~text
acme.client.timeout-ms=3000
acme.client.timeout=3s
~~~

Metadata có thể chỉ tên key mới, nhưng runtime migration cần chuyển đơn vị chính xác. Test các biên như 0, số âm, overflow và giá trị không hợp lệ. Không giả định IDE sẽ tự đổi `3000` thành `3s`.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| IDE không hiển thị key cũ là deprecated | Thiếu processor, annotation đặt sai vị trí hoặc metadata không đóng gói | Đặt annotation trên getter, build và kiểm tra JAR |
| Gắn `@DeprecatedConfigurationProperty` lên setter | Annotation processor không tìm metadata theo getter | Chuyển annotation sang getter; setter có thể chỉ dùng `@Deprecated` |
| Tưởng annotation tự chuyển key cũ sang mới | Nhầm metadata với runtime binder | Giữ alias getter/setter và viết logic migration rõ ràng |
| Tưởng `replacement` tự đổi YAML | Replacement chỉ là hướng dẫn metadata | Cập nhật config files qua migration guide hoặc code migration |
| Muốn dùng level=error nhưng annotation không có thuộc tính đó | Annotation chỉ sinh warning | Dùng additional metadata JSON |
| Xóa accessor cũ nhưng không giữ hướng dẫn | Metadata tự sinh cho accessor cũ cũng biến mất | Thêm manual metadata với level=error |
| Metadata error nhưng runtime vẫn đọc key cũ | Code vẫn có accessor/constructor parameter hoặc custom migration | Xem lại runtime model; metadata không thay thế logic loại bỏ |
| Key cũ và mới cùng được cấu hình cho kết quả khó đoán | Không định nghĩa precedence | Viết logic ưu tiên và test trường hợp cả hai |
| Replacement chỉ ghi suffix | Không đủ tên property | Ghi full canonical property path |
| Reason quá chung chung | Người dùng không biết vì sao/đổi sang đâu | Viết lý do và hành động cụ thể |
| Metadata source đúng nhưng JAR không có file | Processor không chạy hoặc resource không được đóng gói | Kiểm tra annotation processor và output sau build |
| Đổi key trong code nhưng không đổi docs | Contract bị lệch giữa metadata, README và sample | Đồng bộ release notes, YAML mẫu, docs và tests |

## 11. Checklist review trước khi phát hành

### Metadata

- [ ] Key cũ có tên đầy đủ, canonical và đúng namespace.
- [ ] `level` phù hợp: warning khi còn hỗ trợ, error khi đã bỏ.
- [ ] `reason` nói rõ lý do và hành động cần làm.
- [ ] `replacement` là full property name, không chỉ suffix.
- [ ] `since` là version bắt đầu deprecate.
- [ ] Annotation đặt trên getter nếu dùng `@DeprecatedConfigurationProperty`.
- [ ] Manual metadata nằm đúng đường dẫn và được merge.
- [ ] Metadata cuối cùng được đóng gói trong JAR.

### Runtime compatibility

- [ ] Đã quyết định key cũ còn bind trong bao lâu.
- [ ] Alias runtime có code rõ ràng, không dựa vào metadata.
- [ ] Đã định nghĩa precedence nếu cả key cũ và mới cùng xuất hiện.
- [ ] Key mới được test độc lập.
- [ ] Key cũ được test trong giai đoạn warning.
- [ ] Khi bỏ key cũ, runtime model không còn bind nó hoặc có chính sách từ chối rõ ràng.
- [ ] Không log giá trị secret trong cảnh báo.

### Documentation/release

- [ ] YAML mẫu dùng key mới.
- [ ] Migration guide có ví dụ trước/sau.
- [ ] Release notes nêu version deprecate và version dự kiến loại bỏ.
- [ ] Ma trận tương thích của các phiên bản thư viện được cập nhật.
- [ ] Consumer test xác nhận artifact đã publish chứa metadata đúng.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `@DeprecatedConfigurationProperty` phải đặt trên đâu?  
**Đáp án:** Trên getter của property cũ trong class `@ConfigurationProperties`. Có thể đánh dấu setter bằng `@Deprecated`, nhưng annotation metadata phải ở getter.

**Câu 2.** Annotation này có thay đổi runtime binding không?  
**Đáp án:** Không. Nó chỉ giúp `spring-boot-configuration-processor` sinh metadata deprecation. Getter/setter và code migration mới quyết định property cũ có còn bind/được sử dụng không.

**Câu 3.** Vì sao annotation sinh ra level warning?  
**Đáp án:** Annotation không có thuộc tính level và được dùng khi code vẫn xử lý property cũ; do đó metadata tự động giả định warning.

**Câu 4.** Khi accessor cũ đã bị xóa nhưng muốn IDE vẫn chỉ replacement, dùng gì?  
**Đáp án:** Thêm entry trong `META-INF/additional-spring-configuration-metadata.json` với deprecation level error, reason, replacement và since.

**Câu 5.** Trường replacement cần ghi `endpoint` hay `acme.client.endpoint`?  
**Đáp án:** Ghi full property name `acme.client.endpoint`.

**Câu 6.** Thêm `level=error` vào JSON có tự ném exception khi ứng dụng khai báo key cũ không?  
**Đáp án:** Không. Metadata phục vụ tooling; nếu muốn runtime từ chối key cũ, cần bỏ accessor hoặc triển khai kiểm tra/validation riêng.

**Câu 7.** Nếu cả key cũ và key mới cùng được khai báo, Spring Boot có tự hiểu replacement để chọn key mới không?  
**Đáp án:** Không. Thư viện phải định nghĩa precedence trong runtime code và kiểm thử trường hợp cả hai key cùng tồn tại.

**Câu 8.** Nếu một property cũ được thay bằng hai property mới, có thể chỉ ghi một replacement rồi coi như đủ không?  
**Đáp án:** Không. Hãy mô tả mapping nhiều key trong reason/migration guide và triển khai chuyển đổi có chủ đích.

## 13. Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot — Metadata Format](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html)
- [Spring Boot — Generating Metadata with the Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html)
- [DeprecatedConfigurationProperty — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3.9/api/java/org/springframework/boot/context/properties/DeprecatedConfigurationProperty.html)

**Ghi nhớ:** Metadata deprecation là lời hướng dẫn có cấu trúc cho người dùng và IDE. `@DeprecatedConfigurationProperty` đặt trên getter để sinh warning metadata khi key cũ vẫn được hỗ trợ; additional metadata cho phép giữ hint error sau khi accessor cũ bị loại bỏ. **Replacement không tự migrate runtime configuration**: thư viện phải duy trì alias, định nghĩa precedence, kiểm thử tương thích và công bố lộ trình bỏ key cũ.
