# Phân biệt metadata tự cấu hình và metadata thuộc tính cấu hình

## 1. Vì sao Spring Boot có nhiều loại metadata?

Khi xây dựng một thư viện Spring Boot, bạn thường gặp nhiều file dưới thư mục META-INF. Tên của chúng khá giống nhau, nhưng mỗi file giải quyết một việc khác nhau:

- Spring Boot cần biết auto-configuration class nào là ứng viên để import vào ứng dụng.
- Spring Boot có thể dùng metadata điều kiện để loại sớm những auto-configuration chắc chắn không phù hợp, giảm công việc khi khởi động.
- IDE cần biết những property nào thư viện hỗ trợ, kiểu dữ liệu, mô tả, giá trị mặc định và các lựa chọn gợi ý để hoàn thành cấu hình trong application.yml.

Ba nhu cầu này không dùng chung một file. Với Spring Boot 3.3, cần phân biệt tối thiểu ba artifact:

1. META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
2. META-INF/spring-autoconfigure-metadata.properties
3. META-INF/spring-configuration-metadata.json

Ngoài ra, thư viện có thể cung cấp file metadata thuộc tính viết tay:

META-INF/additional-spring-configuration-metadata.json

Bài này giải thích mục đích, thời điểm tạo, nơi Spring Boot/IDE sử dụng và cách kiểm tra từng file trong JAR. Ví dụ dùng Java 17+, Maven và Spring Boot 3.3.13.

## 2. Bảng phân biệt nhanh

| File | Ai tạo? | Ai sử dụng? | Mục đích |
|---|---|---|---|
| AutoConfiguration.imports | Tác giả thư viện duy trì trong resources | Spring Boot lúc tìm auto-configuration candidates | Khai báo class nào được phép tham gia cơ chế auto-configuration |
| spring-autoconfigure-metadata.properties | Annotation processor spring-boot-autoconfigure-processor | Spring Boot trong giai đoạn lọc sớm candidates | Tối ưu bằng cách loại sớm một số cấu hình không thể khớp điều kiện đã biết |
| spring-configuration-metadata.json | Annotation processor spring-boot-configuration-processor, có thể được bổ sung thủ công | IDE và công cụ hỗ trợ cấu hình | Mô tả groups, properties, kiểu, default, deprecation và hints cho người viết cấu hình |
| additional-spring-configuration-metadata.json | Tác giả thư viện viết thủ công | Configuration processor trong lúc build | Bổ sung hoặc tinh chỉnh metadata thuộc tính trước khi tạo file JSON chính |

Điểm cần nhớ:

- **Imports trả lời “có auto-configuration class nào?”**
- **Auto-config metadata trả lời “có thể loại sớm class nào dựa trên condition đã biết?”**
- **Configuration metadata trả lời “người dùng có thể cấu hình những key nào và IDE nên hướng dẫn ra sao?”**

File metadata thuộc tính không làm cho một auto-configuration được import. File metadata auto-config cũng không tạo gợi ý cho application.yml. Một file có thể tồn tại mà hai file còn lại không có; chúng phục vụ các luồng khác nhau.

## 3. AutoConfiguration.imports: danh sách ứng viên auto-configuration

### 3.1. Vai trò

Spring Boot đọc file:

META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

từ các JAR trên classpath. Mỗi dòng là tên đầy đủ của một auto-configuration class. Ví dụ:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
com.acme.catalog.autoconfigure.CatalogWebAutoConfiguration
```

Spring Boot dùng danh sách này trong cơ chế @EnableAutoConfiguration (được gộp trong @SpringBootApplication) để tìm các cấu hình tự động có thể áp dụng.

File này là **đầu vào đăng ký candidate**. Nếu class không được công bố trong imports và không được nạp bằng một đường riêng, Spring Boot không tự tìm class chỉ vì class có annotation @AutoConfiguration.

Có thể thêm comment bắt đầu bằng ký tự #. Mỗi class nên nằm trong package riêng dành cho auto-configuration và không nên bị component scan thông thường tìm thấy.

### 3.2. Ai tạo file này?

Trong ví dụ thông thường, tác giả thư viện **tạo file resource này bằng tay**. Hai annotation processor nói ở các mục sau không thay thế vai trò khai báo danh sách candidate của file imports.

Cấu trúc source:

```text
catalog-autoconfigure/
└── src/main/
    ├── java/
    │   └── com/acme/catalog/autoconfigure/
    │       └── CatalogAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung file imports:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

Khi build JAR, resource được đóng gói với đúng đường dẫn dưới META-INF/spring/. Không đổi tên file tùy ý, không đặt nhầm dưới package Java và không ghi tên bean thay cho tên class.

### 3.3. Không nhầm imports với metadata điều kiện

Giả sử JAR có imports nhưng không có spring-autoconfigure-metadata.properties. Spring Boot vẫn biết candidate nào cần xét và vẫn có thể đánh giá các condition theo cơ chế thông thường.

Ngược lại, có một file metadata điều kiện nhưng không công bố auto-configuration class trong imports thì file điều kiện không phải danh sách thay thế cho imports. Candidate list và condition metadata là hai phần riêng.

### 3.4. Quan hệ với spring.factories

Ở các phiên bản Spring Boot cũ, thư viện thường đăng ký auto-configuration qua key org.springframework.boot.autoconfigure.EnableAutoConfiguration trong META-INF/spring.factories. Cách công bố auto-configuration hiện đại của Spring Boot 3.x là file AutoConfiguration.imports.

spring.factories vẫn có thể được dùng cho một số SPI/extension point khác; điều đó không làm nó trở thành file candidate list thay thế cho imports trong Boot 3.x.

## 4. spring-autoconfigure-metadata.properties: metadata điều kiện để lọc sớm

### 4.1. Vai trò

File:

META-INF/spring-autoconfigure-metadata.properties

được tạo bởi annotation processor:

org.springframework.boot:spring-boot-autoconfigure-processor

Processor thu thập một số condition có thể suy ra từ auto-configuration source và ghi metadata vào file properties. Spring Boot có thể đọc file này để **eagerly filter** những auto-configuration chắc chắn không phù hợp trước khi thực hiện đầy đủ các bước cấu hình.

Mục tiêu chính là **tối ưu thời gian khởi động**, đặc biệt khi ứng dụng có nhiều auto-configuration từ nhiều starter.

Ví dụ: một auto-configuration chỉ áp dụng khi class com.vendor.sdk.Client có trên classpath. Nếu metadata đã cho phép Boot biết điều kiện classpath đó, Boot có thể loại sớm candidate khi class không tồn tại.

### 4.2. Đây không phải danh sách candidate

File này không có nhiệm vụ công bố toàn bộ auto-configuration class. Việc công bố vẫn do AutoConfiguration.imports đảm nhiệm.

Cũng không nên tự viết file này để thay thế annotation điều kiện trong code. Condition thật vẫn cần được khai báo trong auto-configuration bằng các annotation như:

- @ConditionalOnClass
- @ConditionalOnMissingClass
- @ConditionalOnBean
- @ConditionalOnMissingBean
- Các condition khác phù hợp với yêu cầu

Processor chỉ tạo một biểu diễn metadata cho các điều kiện mà nó hỗ trợ/đọc được. Nó không biến mọi logic Java tùy chỉnh thành một biểu thức metadata có thể đánh giá trước.

### 4.3. Nếu file metadata này không tồn tại thì sao?

Thông thường, auto-configuration vẫn hoạt động. Spring Boot vẫn đọc candidate list, rồi thực hiện việc đánh giá condition theo quy trình thông thường. Ứng dụng có thể mất lợi ích lọc sớm, nhưng thiếu file metadata này **không có nghĩa auto-configuration bị tắt**.

Đây là khác biệt quan trọng so với imports:

- Thiếu imports: class không được công bố qua cơ chế auto-configuration.
- Thiếu auto-config metadata: candidate vẫn có thể được xét; Boot không có chỉ mục tối ưu tương ứng.

### 4.4. Tạo file bằng processor

Với Maven, có thể cấu hình spring-boot-autoconfigure-processor trong annotation processor path của Maven Compiler Plugin. Ví dụ cấu hình đầy đủ nằm ở mục 7.

Với Gradle, khai báo processor ở configuration annotationProcessor:

```groovy
dependencies {
    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
}
```

Không đưa processor vào dependency runtime của ứng dụng tiêu thụ. Đây là công cụ dành cho quá trình biên dịch module thư viện.

## 5. spring-configuration-metadata.json: metadata thuộc tính dành cho IDE

### 5.1. Vai trò

File:

META-INF/spring-configuration-metadata.json

mô tả các key cấu hình mà một thư viện hoặc Spring Boot hỗ trợ. Các IDE tương thích có thể dùng metadata này để:

- Gợi ý tên key khi người dùng gõ trong application.properties hoặc application.yml.
- Gợi ý kiểu dữ liệu phù hợp.
- Hiển thị mô tả và giá trị mặc định.
- Đưa ra các giá trị hợp lệ hoặc ví dụ qua hints.
- Đánh dấu property đã deprecated và gợi ý key thay thế.

Phần lớn file này được tạo lúc compile bằng processor:

org.springframework.boot:spring-boot-configuration-processor

Processor tìm các class/method được đánh dấu @ConfigurationProperties và phân tích property từ constructor, record component, getter/setter và các cấu trúc được hỗ trợ.

### 5.2. Metadata không phải cơ chế bind runtime

Đây là điểm cần nhớ nhất:

**File JSON chỉ mô tả cấu hình cho công cụ hỗ trợ; nó không tự đăng ký bean, không tự tạo property và không thay thế Binder của Spring Boot.**

Ví dụ, nếu metadata khai báo:

```json
{
  "properties": [
    {
      "name": "acme.catalog.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether the catalog integration is enabled."
    }
  ]
}
```

IDE có thể gợi ý acme.catalog.enabled. Nhưng nếu ứng dụng không có class @ConfigurationProperties tương ứng, không đăng ký properties bean và không có code đọc key đó, thì metadata JSON không khiến tính năng tự bật/tắt.

Runtime binding vẫn cần cấu trúc code phù hợp, ví dụ @ConfigurationProperties được đăng ký bằng @EnableConfigurationProperties hoặc cơ chế scan tương ứng. Các điều kiện như @ConditionalOnProperty vẫn được đánh giá từ Environment, không đọc file metadata JSON để quyết định.

### 5.3. Các nhóm dữ liệu trong JSON

Metadata có những phần chính:

| Phần | Nội dung |
|---|---|
| groups | Nhóm/namespace chứa các property liên quan; group không tự mang giá trị cấu hình |
| properties | Danh sách key cấu hình, type, description, source và default |
| hints | Gợi ý giá trị hợp lệ, mô tả lựa chọn hoặc provider hỗ trợ nội dung gợi ý |
| ignored | Những property được chủ động loại khỏi danh sách metadata được tạo |

Ví dụ rút gọn:

```json
{
  "groups": [
    {
      "name": "acme.catalog",
      "type": "com.acme.catalog.CatalogProperties",
      "sourceType": "com.acme.catalog.CatalogProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.catalog.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether the catalog integration is enabled.",
      "defaultValue": false,
      "sourceType": "com.acme.catalog.CatalogProperties"
    },
    {
      "name": "acme.catalog.timeout",
      "type": "java.time.Duration",
      "description": "Maximum time to wait for a catalog response.",
      "defaultValue": "3s",
      "sourceType": "com.acme.catalog.CatalogProperties"
    }
  ],
  "hints": [
    {
      "name": "acme.catalog.mode",
      "values": [
        {
          "value": "fast",
          "description": "Prioritize throughput."
        },
        {
          "value": "safe",
          "description": "Prefer conservative request behavior."
        }
      ]
    }
  ]
}
```

Đây là JSON minh họa để hiểu cấu trúc, không phải output chính xác của processor cho mọi class. Thứ tự thuộc tính, sourceType và các giá trị được phát hiện phụ thuộc source code.

### 5.4. Ý nghĩa một số thuộc tính metadata

| Field | Ý nghĩa |
|---|---|
| name | Tên đầy đủ của group/property |
| type | Kiểu Java hoặc generic type của property |
| description | Mô tả dành cho người cấu hình |
| sourceType | Class đóng góp property/group |
| sourceMethod | Method đóng góp group/property nếu có |
| defaultValue | Giá trị mặc định được biết hoặc khai báo |
| deprecation | Thông tin property đã deprecated |
| values | Các lựa chọn gợi ý cho một property |
| providers | Provider có thể cung cấp gợi ý động cho IDE |

Tên property trong metadata thường dùng dạng chữ thường, phân tách bằng dấu chấm, ví dụ acme.catalog.request-timeout. Đây cũng là dạng canonical nên dùng trong tài liệu cấu hình.

### 5.5. Metadata deprecation

Một property có thể chứa:

```json
{
  "name": "acme.catalog.legacy-mode",
  "type": "java.lang.String",
  "deprecation": {
    "level": "warning",
    "reason": "Use acme.catalog.mode instead.",
    "replacement": "acme.catalog.mode",
    "since": "1.4"
  }
}
```

Ý nghĩa:

- level có thể là warning hoặc error; nếu bỏ trống, mặc định là warning.
- reason giải thích lý do deprecated.
- replacement chỉ ra property thay thế.
- since ghi phiên bản bắt đầu deprecated.

Với mức warning, property vẫn có thể được bind để hỗ trợ giai đoạn chuyển đổi. Với mức error, property không còn được quản lý và không được bind theo metadata deprecation. Hãy chọn mức phù hợp với chính sách tương thích ngược của thư viện.

Metadata deprecation chỉ mô tả trạng thái và hỗ trợ IDE. Nếu property cũ cần tiếp tục hoạt động như alias, code binding/migration của thư viện phải thực hiện điều đó; chỉ thêm JSON không tự chuyển giá trị cũ sang key mới.

## 6. additional-spring-configuration-metadata.json: bổ sung metadata thủ công

Không phải mọi property đều được phát hiện tự động. Một số trường hợp cần bổ sung:

- Property được đọc thủ công từ Environment, không nằm trong bean @ConfigurationProperties.
- Default động hoặc collection default mà processor không thể suy ra chính xác.
- Mô tả cần cụ thể hơn.
- Giá trị gợi ý cho IDE.
- Thông tin deprecation hoặc replacement.
- Metadata của property không được khai báo theo cấu trúc Java thông thường.

Tạo file nguồn:

src/main/resources/META-INF/additional-spring-configuration-metadata.json

Ví dụ:

```json
{
  "properties": [
    {
      "name": "acme.catalog.timeout",
      "type": "java.time.Duration",
      "description": "Maximum time to wait for a catalog response.",
      "defaultValue": "3s"
    },
    {
      "name": "acme.catalog.legacy-mode",
      "type": "java.lang.String",
      "deprecation": {
        "level": "warning",
        "reason": "Use acme.catalog.mode instead.",
        "replacement": "acme.catalog.mode",
        "since": "1.4"
      }
    }
  ],
  "hints": [
    {
      "name": "acme.catalog.mode",
      "values": [
        {
          "value": "fast",
          "description": "Prioritize throughput."
        },
        {
          "value": "safe",
          "description": "Prefer conservative request behavior."
        }
      ]
    }
  ],
  "ignored": {
    "properties": [
      {
        "name": "acme.catalog.internal-cache-path"
      }
    ]
  }
}
```

Configuration processor sẽ merge các mục thủ công này vào metadata chính spring-configuration-metadata.json.

Quy tắc merge quan trọng:

1. Nếu property đã được tự động phát hiện, metadata thủ công có thể ghi đè các thuộc tính như description, defaultValue và deprecation.
2. Nếu property chưa được phát hiện trong module, mục thủ công có thể được thêm vào metadata.
3. Các mục trong ignored.properties được dùng để loại property tương ứng khỏi danh sách properties của metadata được tạo.
4. File additional là tùy chọn; không cần tạo nếu không có metadata bổ sung.

**File additional không phải file cấu hình runtime.** Đặt một key trong file này không làm cho Binder tự nhận key đó, không tạo bean và không tự thay đổi hành vi auto-configuration. Nếu muốn key thực sự hoạt động, code của thư viện phải đọc/bind key đó.

## 7. Ví dụ hoàn chỉnh: tạo cả hai loại metadata bằng Maven

Ví dụ này tạo một module thư viện catalog-autoconfigure. Module có:

- Một auto-configuration class được công bố bằng imports.
- Một properties class để Binder nhận cấu hình.
- Một bean client minh họa.
- Hai annotation processor để tạo metadata build-time.
- Một file additional metadata viết tay để bổ sung hints và deprecation.

### 7.1. Cấu trúc thư mục

```text
catalog-autoconfigure/
├── pom.xml
└── src/
    └── main/
        ├── java/com/acme/catalog/
        │   ├── CatalogClient.java
        │   ├── CatalogProperties.java
        │   └── autoconfigure/
        │       └── CatalogAutoConfiguration.java
        └── resources/META-INF/
            ├── additional-spring-configuration-metadata.json
            └── spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.acme</groupId>
    <artifactId>catalog-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
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
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
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
```

Hai processor được đặt trong annotationProcessorPaths nên phục vụ compile. Chúng không phải dependency mà ứng dụng tiêu thụ cần dùng để chạy runtime. Giữ phiên bản processor đồng bộ với phiên bản Spring Boot mà module đang dùng.

Với Gradle, cấu hình tương đương:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")
    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )
}
```

### 7.3. CatalogProperties.java

```java
package com.acme.catalog;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.catalog")
public class CatalogProperties {

    /**
     * Whether the catalog integration is enabled.
     */
    private boolean enabled = false;

    /**
     * Maximum time to wait for a catalog response.
     */
    private Duration timeout;

    /**
     * Selects the request handling mode.
     */
    private String mode = "fast";

    /**
     * Legacy timeout key retained during migration.
     */
    private Duration legacyTimeout;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }

    public Duration getLegacyTimeout() {
        return legacyTimeout;
    }

    public void setLegacyTimeout(Duration legacyTimeout) {
        this.legacyTimeout = legacyTimeout;
    }
}
```

Configuration processor có thể dùng @ConfigurationProperties và JavaBean accessors để phát hiện các property. Javadoc của field được dùng để tạo description. Default đơn giản, được khai báo trực tiếp trong source, có thể được suy ra.

Trong ví dụ, timeout không được gán trực tiếp trong field. Auto-configuration sẽ dùng default 3 giây khi cả key mới và key cũ đều thiếu; additional metadata mô tả default hiệu lực đó cho IDE.

### 7.4. CatalogClient.java

```java
package com.acme.catalog;

import java.time.Duration;

public record CatalogClient(Duration timeout, String mode) {
}
```

Đây là kiểu client tối giản để minh họa việc nhận cấu hình. Trong thư viện thực tế, client sẽ gọi SDK hoặc dịch vụ của catalog.

### 7.5. CatalogAutoConfiguration.java

```java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(CatalogClient.class)
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogClient catalogClient(CatalogProperties properties) {
        Duration timeout = properties.getTimeout();

        if (timeout == null) {
            timeout = properties.getLegacyTimeout();
        }

        if (timeout == null) {
            timeout = Duration.ofSeconds(3);
        }

        return new CatalogClient(timeout, properties.getMode());
    }
}
```

Ở đây:

- @AutoConfiguration đánh dấu class cấu hình tự động.
- @ConditionalOnClass và @ConditionalOnProperty quyết định khi nào cấu hình được áp dụng.
- @EnableConfigurationProperties đăng ký properties bean để Binder bind giá trị từ Environment.
- @ConditionalOnMissingBean cho phép ứng dụng thay client mặc định.
- Code Java thực hiện fallback từ key cũ sang key mới; metadata deprecation chỉ thông báo cho IDE, không tự viết logic fallback.

### 7.6. AutoConfiguration.imports

File:

src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Nội dung:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

Đây là file do tác giả thư viện duy trì. Khi đóng gói JAR, Spring Boot dùng file này để phát hiện CatalogAutoConfiguration.

### 7.7. additional-spring-configuration-metadata.json

File:

src/main/resources/META-INF/additional-spring-configuration-metadata.json

Nội dung:

```json
{
  "properties": [
    {
      "name": "acme.catalog.timeout",
      "type": "java.time.Duration",
      "description": "Maximum time to wait for a catalog response.",
      "defaultValue": "3s"
    },
    {
      "name": "acme.catalog.legacy-timeout",
      "type": "java.time.Duration",
      "deprecation": {
        "level": "warning",
        "reason": "Use acme.catalog.timeout instead.",
        "replacement": "acme.catalog.timeout",
        "since": "1.4"
      }
    }
  ],
  "hints": [
    {
      "name": "acme.catalog.mode",
      "values": [
        {
          "value": "fast",
          "description": "Prioritize throughput."
        },
        {
          "value": "safe",
          "description": "Prefer conservative request behavior."
        }
      ]
    }
  ]
}
```

Processor sẽ merge thông tin này với metadata tự phát hiện từ CatalogProperties. Trong ví dụ, key legacy vẫn được code bind và dùng khi key mới chưa được cung cấp; metadata chỉ đánh dấu nó là deprecated và hướng người dùng sang key mới.

### 7.8. Build và kiểm tra JAR

Từ thư mục chứa pom.xml, chạy:

```bash
mvn clean package
```

Sau khi build thành công, JAR dự kiến chứa các resource chính:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring-configuration-metadata.json
META-INF/additional-spring-configuration-metadata.json
```

Kiểm tra danh sách file:

```bash
jar tf target/catalog-autoconfigure-1.0.0.jar
```

Các file metadata do processor tạo thường nằm trong output directory của module trước khi đóng gói. File imports và additional metadata đến từ resources của dự án.

Có thể kiểm tra riêng nội dung JSON trong target/classes/META-INF/spring-configuration-metadata.json để chắc chắn có các key:

- acme.catalog.enabled
- acme.catalog.timeout
- acme.catalog.mode
- acme.catalog.legacy-timeout

Cấu trúc JSON và thứ tự entry có thể thay đổi theo processor; kiểm tra key, type, description, default và deprecation thay vì so sánh toàn file theo một thứ tự cố định.

### 7.9. Kiểm tra trải nghiệm IDE

Cài JAR thư viện vào local repository hoặc publish vào repository thử nghiệm, rồi thêm nó làm dependency của một ứng dụng Spring Boot nhỏ.

Trong application.yml, thử gõ:

```yaml
acme:
  catalog:
    enabled: true
    timeout: 5s
    mode: safe
```

Trong IDE có hỗ trợ Spring configuration metadata, người dùng nên nhận được:

- Gợi ý key acme.catalog.enabled, timeout và mode.
- Kiểu Boolean cho enabled.
- Kiểu Duration cho timeout.
- Mô tả cho từng property.
- Gợi ý giá trị fast/safe cho mode.
- Thông tin deprecated cho legacy-timeout nếu nhập key cũ.

Nếu IDE không hiện gợi ý, kiểm tra JAR có file JSON, processor có chạy lúc compile, ứng dụng tiêu thụ có đúng phiên bản JAR và IDE có hỗ trợ Spring Boot configuration metadata không.

## 8. Vì sao cần hai annotation processor?

| Processor | Artifact được tạo | Nội dung | Lợi ích |
|---|---|---|---|
| spring-boot-autoconfigure-processor | spring-autoconfigure-metadata.properties | Metadata của các condition được hỗ trợ trên auto-configuration | Giúp Spring Boot lọc sớm candidate không phù hợp |
| spring-boot-configuration-processor | spring-configuration-metadata.json | Property groups, key, type, description, default, hints và deprecation | Giúp IDE và công cụ hỗ trợ cấu hình |

Chúng có thể cùng chạy trong một module, như ví dụ Maven ở trên. Không có yêu cầu phải chọn một trong hai; mỗi processor tạo artifact khác nhau.

### 8.1. Nếu chỉ dùng autoconfigure processor

Auto-configuration có thể được tối ưu lọc sớm, nhưng người dùng không nhất thiết nhận được gợi ý property phong phú trong IDE. Nếu thư viện có @ConfigurationProperties, nên bật thêm configuration processor.

### 8.2. Nếu chỉ dùng configuration processor

IDE có thể hiểu các property, nhưng điều đó không giúp Spring Boot tìm auto-configuration class. Bạn vẫn phải công bố candidate bằng imports và có thể mất lợi ích lọc condition sớm nếu thiếu autoconfigure metadata processor.

### 8.3. Nếu không dùng processor nào

Ứng dụng vẫn có thể chạy nếu imports và code runtime đúng. Nhưng:

- Không có metadata condition được tạo để lọc sớm.
- Không có file JSON được sinh tự động cho IDE.
- Người dùng có ít hỗ trợ completion/documentation hơn.
- Thư viện cần tự duy trì metadata thủ công nếu muốn cung cấp trải nghiệm tương tự.

Không nên thêm processor chỉ vì thấy một file META-INF trong JAR của thư viện khác; hãy xác định nhu cầu và module thực sự chứa source tương ứng.

## 9. Thời điểm tạo và sử dụng: nhìn theo vòng đời

```text
SOURCE CODE + RESOURCES
        |
        | Maven/Gradle compile
        v
ANNOTATION PROCESSORS
        |
        +--> spring-autoconfigure-metadata.properties
        |
        +--> spring-configuration-metadata.json
        |       ^
        |       |
        |       +-- additional-spring-configuration-metadata.json
        |
        v
PACKAGED LIBRARY JAR
        |
        +--> AutoConfiguration.imports
        +--> spring-autoconfigure-metadata.properties
        +--> spring-configuration-metadata.json
        |
        +------------------------------+
                                       |
                     +-----------------+------------------+
                     |                                    |
                     v                                    v
              SPRING BOOT RUNTIME                      IDE / EDITOR
                     |                                    |
             imports: discover candidates          configuration JSON:
                     |                              completion/documentation
             autoconfigure metadata:
             eager condition filtering
                     |
             evaluate remaining conditions
                     |
             register applicable bean definitions
                     |
             bind @ConfigurationProperties
```

Sơ đồ nhấn mạnh rằng hai file JSON/properties không được dùng thay nhau. File imports và autoconfigure metadata phục vụ cơ chế phát hiện/lọc cấu hình lúc runtime; configuration metadata phục vụ công cụ soạn cấu hình.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Auto-configuration class có annotation nhưng không được phát hiện | Thiếu hoặc sai tên file imports, tên class không đúng | Kiểm tra AutoConfiguration.imports trong JAR |
| Có imports nhưng không thấy spring-autoconfigure-metadata.properties | Processor chưa được cấu hình hoặc không có source condition phù hợp để ghi metadata | Kiểm tra annotation processor path và output compile |
| Thiếu autoconfigure metadata khiến ứng dụng không chạy | Nhầm file tối ưu thành file đăng ký candidate | Giữ imports; metadata condition không thay thế candidate list |
| IDE không gợi ý key | Không có configuration processor hoặc JSON không được đóng gói | Kiểm tra processor và JAR |
| IDE gợi ý key nhưng runtime không nhận | Metadata JSON có key nhưng code không bind/đọc key | Thêm @ConfigurationProperties/Binder hoặc logic đọc property |
| JSON có default khác hành vi thực tế | Default metadata không đồng bộ với code | Đồng bộ field initializer, fallback runtime và additional metadata |
| Thêm additional metadata nhưng JSON không đổi | File đặt sai path hoặc processor không chạy | Kiểm tra META-INF/additional-spring-configuration-metadata.json và build sạch |
| Property deprecated vẫn hoạt động dù metadata cảnh báo | Mức warning vẫn cho phép binding hoặc code có alias | Đây có thể là chủ đích tương thích ngược; kiểm tra deprecation level và code |
| Property có hint nhưng IDE không gợi ý | IDE không đọc metadata hoặc key/hint không khớp | Kiểm tra file JSON cuối và hỗ trợ của IDE |
| Processor JAR xuất hiện trong executable app không mong muốn | Khai báo processor như dependency runtime thông thường | Dùng annotationProcessorPaths/annotationProcessor hoặc loại processor khỏi repackage |
| Metadata chỉ có type, thiếu description | Thiếu Javadoc phù hợp hoặc source chỉ là compiled dependency | Thêm Javadoc vào source hoặc additional metadata thủ công |
| Default collection không được sinh đúng | Processor không suy ra được giá trị collection phức tạp | Khai báo defaultValue bằng additional metadata |
| Thay tên class auto-config nhưng quên imports | Resource vẫn tham chiếu class cũ | Cập nhật imports cùng lúc với refactor package/class |

## 11. Checklist phát hành thư viện auto-configuration

Trước khi phát hành JAR, kiểm tra:

1. **Candidate list:** imports có đúng tên đầy đủ của tất cả auto-configuration cần công bố không?
2. **Package:** auto-config có nằm ngoài vùng component scan thông thường của ứng dụng không?
3. **Conditions:** classpath, property và missing-bean conditions có được khai báo trong source code không?
4. **Autoconfigure processor:** module chứa auto-config có chạy spring-boot-autoconfigure-processor không?
5. **Configuration processor:** module chứa @ConfigurationProperties có chạy spring-boot-configuration-processor không?
6. **Properties Javadoc:** key có mô tả rõ, kiểu và default có khớp hành vi runtime không?
7. **Additional metadata:** hints, deprecation và property thủ công có đúng schema JSON không?
8. **JAR:** cả imports và metadata đã nằm trong artifact sau build chưa?
9. **Consumer test:** ứng dụng mẫu thêm starter có discover auto-config và nhận được gợi ý property trong IDE không?
10. **Không nhầm vai trò:** không dùng metadata JSON để thay code binding, không dùng condition metadata để thay imports.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** File nào liệt kê tên auto-configuration class để Spring Boot phát hiện?

**Đáp án:** META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.

**Câu 2.** File spring-autoconfigure-metadata.properties được tạo bởi processor nào và dùng để làm gì?

**Đáp án:** spring-boot-autoconfigure-processor tạo file này để Spring Boot lọc sớm một số auto-configuration theo condition đã biết, tối ưu startup.

**Câu 3.** File spring-configuration-metadata.json có làm Binder tự nhận property không?

**Đáp án:** Không. Nó mô tả property cho IDE/công cụ. Runtime binding vẫn cần @ConfigurationProperties được đăng ký hoặc code đọc property phù hợp.

**Câu 4.** Muốn bổ sung hint cho một key mà processor không suy ra được, dùng file nào?

**Đáp án:** META-INF/additional-spring-configuration-metadata.json; configuration processor merge nó vào metadata JSON chính.

**Câu 5.** Nếu bỏ spring-autoconfigure-metadata.properties nhưng giữ imports và code condition, auto-configuration có thể chạy không?

**Đáp án:** Có. Candidate vẫn được tìm qua imports và condition vẫn được đánh giá bình thường; chỉ mất bước lọc sớm dựa trên metadata đó.

**Câu 6.** Nếu chỉ thêm key vào additional metadata nhưng không có property bean hoặc logic đọc key, giá trị trong application.yml có tự được sử dụng không?

**Đáp án:** Không. Metadata không tạo binding hoặc thay đổi hành vi runtime.

**Câu 7.** Property có deprecation level warning có còn được bind không?

**Đáp án:** Có. Warning cho phép tiếp tục bind trong giai đoạn chuyển đổi; mức error thể hiện property không còn được quản lý và không được bind.

## 13. Ghi nhớ

- **AutoConfiguration.imports** là danh sách auto-configuration candidates; tác giả thư viện duy trì.
- **spring-autoconfigure-metadata.properties** do autoconfigure processor tạo để lọc condition sớm và cải thiện startup.
- **spring-configuration-metadata.json** do configuration processor tạo để IDE hỗ trợ completion, documentation và hints.
- **additional-spring-configuration-metadata.json** là đầu vào thủ công để bổ sung/tinh chỉnh metadata thuộc tính.
- Metadata thuộc tính không thay thế @ConfigurationProperties, Binder hoặc logic đọc Environment.
- Metadata điều kiện không thay thế imports và condition annotations trong source.
- Nên kiểm tra JAR cuối cùng và thử một ứng dụng tiêu thụ thật để xác nhận cả runtime discovery lẫn trải nghiệm IDE.

### Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot 3.3 — Generating Metadata by Using the Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot 3.3 — Metadata Format](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html)
