# Quy ước đặt tên starter bên thứ ba và tránh chiếm namespace Spring Boot

## 1. Vì sao phải thiết kế tên starter và namespace ngay từ đầu?

Một starter giúp ứng dụng thêm một dependency để nhận các thư viện, auto-configuration và cấu hình mặc định cần thiết cho một công nghệ. Khi xây dựng starter cho thư viện của riêng mình, nhà phát triển cần đặt tên để người dùng nhận ra **nhà cung cấp và tính năng**, đồng thời không làm người dùng nhầm starter bên thứ ba với starter chính thức của Spring Boot.

Spring Boot dành tiền tố module `spring-boot` cho artifact chính thức. Tài liệu Spring Boot 3.3 quy định: **starter bên thứ ba không được bắt đầu tên module bằng `spring-boot`, kể cả khi dùng Maven `groupId` khác**. Quy ước thông thường là đặt tên dự án hoặc thương hiệu trước, sau đó là `-spring-boot-starter`.

Ví dụ, thư viện giả định tên `acme` nên dùng:

- `com.acme:acme-spring-boot` — module chứa API tích hợp và auto-configuration.
- `com.acme:acme-spring-boot-starter` — module starter gom các dependency cần thiết.
- `com.acme:acme-spring-boot-starter-test` — starter hỗ trợ kiểm thử nếu dự án cung cấp bộ test riêng.

Không nên đặt artifact bên thứ ba là `spring-boot-starter-acme` hoặc `spring-boot-acme-starter`. Đổi `groupId` sang `com.acme` không làm tên bắt đầu bằng `spring-boot` trở nên phù hợp.

Ngoài tên artifact, thư viện còn cần một **package Java riêng** và một **namespace cấu hình riêng**. Ba phạm vi này liên quan nhưng có mục đích khác nhau:

| Phạm vi | Ví dụ nên dùng | Tránh dùng |
|---|---|---|
| Maven/Gradle artifact | `acme-spring-boot-starter` | `spring-boot-starter-acme` |
| Java package | `com.acme.report.autoconfigure` | `org.springframework.boot.autoconfigure.acme` |
| Configuration property prefix | `acme.report` | `spring.acme.report`, `server.acme`, `management.acme` |

Mục tiêu là để người dùng biết chính xác thư viện nào sở hữu module, package và các khóa cấu hình.

## 2. Quy tắc đặt tên artifact bên thứ ba

### 2.1. Tiền tố thuộc về dự án hoặc nhà cung cấp

Các starter chính thức có dạng `spring-boot-starter-*`. Spring Boot dành quy ước đó cho artifact của mình. Starter bên thứ ba thường bắt đầu bằng tên dự án:

```text
thirdpartyproject-spring-boot-starter
acme-spring-boot-starter
mycompany-observability-spring-boot-starter
```

Tên nên:

- Bắt đầu bằng thương hiệu, tên dự án hoặc tên tổ chức sở hữu thư viện.
- Mô tả tích hợp Spring Boot bằng hậu tố `-spring-boot` hoặc `-spring-boot-starter`.
- Nhất quán giữa module auto-configuration, starter và test starter.
- Ngắn, ổn định và không phụ thuộc vào một implementation nội bộ dễ thay đổi.

| Tên module | Đánh giá | Lý do |
|---|---|---|
| `acme-spring-boot-starter` | **Nên dùng** | Tên dự án đứng trước; đúng quy ước bên thứ ba |
| `acme-spring-boot` | **Nên dùng** | Module auto-configuration theo ví dụ Spring Boot |
| `acme-spring-boot-starter-test` | **Nên dùng** | Test starter giữ cùng namespace tên |
| `spring-boot-starter-acme` | **Tránh** | Bắt đầu bằng tiền tố dành cho starter chính thức |
| `spring-boot-acme-starter` | **Tránh** | Vẫn bắt đầu bằng `spring-boot` |
| `acme-starter` | Có thể dùng nhưng kém rõ | Không thể hiện rõ tích hợp Spring Boot |
| `starter-acme-spring` | Kém rõ | Không theo quy ước dễ nhận diện |

### 2.2. `groupId` và `artifactId` không phải cùng một thứ

Một tọa độ Maven có dạng:

```text
groupId:artifactId:version
```

Ví dụ:

```text
com.acme:acme-spring-boot-starter:1.0.0
```

- `groupId` xác định namespace phát hành artifact, thường dựa trên domain/tổ chức mà nhà phát triển kiểm soát.
- `artifactId` xác định tên module cụ thể trong nhóm đó.
- `version` xác định phiên bản được phát hành.

Spring Boot nhấn mạnh quy tắc tên module **không bắt đầu bằng `spring-boot` ngay cả khi Maven groupId khác**. Vì vậy, không dùng `org.example:spring-boot-starter-acme` với lý do groupId đã phân biệt được nhà cung cấp.

Với Gradle, cùng ý tưởng thể hiện qua tọa độ:

```groovy
dependencies {
    implementation 'com.acme:acme-spring-boot-starter:1.0.0'
}
```

Khi publish, giữ `groupId` và tên dự án ổn định. Đổi tên artifact sau khi người dùng đã phụ thuộc vào nó có thể khiến tọa độ cũ không còn được resolve và buộc người dùng cập nhật dependency.

## 3. Chọn cấu trúc module phù hợp

Tài liệu Spring Boot mô tả hai module điển hình:

1. Module auto-configuration, ví dụ `acme-spring-boot`, chứa API tích hợp và các lớp cấu hình tự động.
2. Module starter, ví dụ `acme-spring-boot-starter`, gom module auto-configuration cùng thư viện và dependency thường cần thiết để người dùng chỉ cần thêm một dependency.

Cấu trúc tham khảo:

```text
acme-parent/
├── acme-core/
│   └── API và logic nghiệp vụ độc lập Spring
├── acme-spring-boot/
│   ├── API tích hợp Spring Boot
│   ├── ReportAutoConfiguration.java
│   ├── ReportProperties.java
│   └── META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── acme-spring-boot-starter/
│   └── pom.xml / build.gradle
└── acme-spring-boot-starter-test/
    └── test fixtures và dependency kiểm thử (nếu cần)
```

Tên và số lượng module phụ thuộc vào độ phức tạp của thư viện:

| Trường hợp | Cấu trúc phù hợp |
|---|---|
| Có nhiều tính năng tùy chọn hoặc nhiều cách tích hợp | Tách module auto-configuration và starter |
| Một tích hợp nhỏ, không có dependency tùy chọn | Có thể gộp auto-configuration vào `acme-spring-boot-starter` |
| Có bộ test fixture hoặc integration test dùng chung | Thêm `acme-spring-boot-starter-test` |
| Có API/logic nghiệp vụ dùng được ngoài Spring | Tách `acme-core` để không buộc module core phụ thuộc Spring Boot |

Tách module giúp người dùng lựa chọn. Một ứng dụng có thể chỉ phụ thuộc vào module auto-configuration để tự quyết định dependency; ứng dụng khác dùng starter để nhận bộ dependency mặc định mà nhà cung cấp đề xuất.

### 3.1. Module auto-configuration

Module `acme-spring-boot` thường chứa:

- Các lớp `@AutoConfiguration`.
- `@ConfigurationProperties` và các kiểu cấu hình.
- Callback/interface cho phép tùy chỉnh khởi tạo component.
- Các điều kiện classpath, property, bean hoặc resource.
- Metadata hỗ trợ IDE và lọc auto-configuration.
- File `AutoConfiguration.imports` để Spring Boot tìm thấy cấu hình.

Nó **không phải** module gom mọi dependency runtime của người dùng. Các thư viện tích hợp tùy chọn nên được khai báo theo cách không ép mọi ứng dụng phải cài chúng.

### 3.2. Module starter

Starter thường là một JAR gần như rỗng về mã nguồn. Nhiệm vụ chính là khai báo dependency:

- Module auto-configuration của thư viện.
- Thư viện nền tảng mà tích hợp cần.
- Starter Spring Boot hoặc các starter liên quan cần thiết.
- Những dependency mặc định thực sự hữu ích cho trường hợp dùng phổ biến.

Không đưa mọi integration tùy chọn vào starter chỉ vì chúng có thể hữu ích cho một số người dùng. Dependency thừa làm classpath lớn hơn, tăng nguy cơ xung đột và có thể khiến auto-configuration ngoài ý muốn được kích hoạt.

Spring Boot yêu cầu starter phải tham chiếu core starter `spring-boot-starter` trực tiếp hoặc gián tiếp. Nếu starter đã phụ thuộc một starter khác vốn kéo core starter vào, không cần thêm lặp lại.

### 3.3. Test starter

Nếu thư viện cung cấp test support, dùng tên theo cùng quy tắc:

```text
acme-spring-boot-starter-test
```

Module này có thể chứa test fixture, mock, auto-configuration thay thế hoặc dependency chỉ cần trong test. Không đặt test helper vào starter runtime nếu ứng dụng production không cần chúng.

## 4. Ví dụ Maven multi-module

Một parent POM có thể khai báo module và quản lý phiên bản Spring Boot bằng BOM:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
        <spring-boot.version>3.3.13</spring-boot.version>
    </properties>

    <modules>
        <module>acme-core</module>
        <module>acme-spring-boot</module>
        <module>acme-spring-boot-starter</module>
    </modules>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>3.3.13</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Đây là POM parent minh họa; trong dự án thực tế có thể dùng `spring-boot-starter-parent` hoặc BOM riêng theo chính sách build. Không nên tự chỉ định phiên bản Spring Framework riêng lẻ nếu Spring Boot BOM đã quản lý phiên bản tương thích.

### 4.1. POM cho module auto-configuration

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>acme-spring-boot</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-core</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client</artifactId>
            <version>1.0.0</version>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
```

`acme-client` là ví dụ về thư viện client tùy chọn. Khai báo `optional` trong Maven có nghĩa dependency này không tự động được truyền tiếp tới mọi ứng dụng chỉ phụ thuộc vào module auto-configuration. Module starter có thể chủ động thêm `acme-client` như dependency runtime mặc định.

Với auto-configuration có các điều kiện classpath, cần cô lập các method tham chiếu tới client tùy chọn để khi client không có mặt, JVM không phải nạp sớm kiểu của thư viện trước khi điều kiện classpath có hiệu lực.

### 4.2. POM cho starter

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>acme-spring-boot-starter</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

Starter không cần thêm Java class nếu nhiệm vụ chỉ là gom dependency. Nó có thể có POM và README hướng dẫn sử dụng. Khi thêm dependency khác, chỉ đưa vào những gì người dùng điển hình cần để tích hợp chạy được.

### 4.3. Ứng dụng sử dụng starter

Ứng dụng chỉ cần khai báo tọa độ starter:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
```

Ứng dụng nhận module auto-configuration và các dependency mặc định thông qua quan hệ phụ thuộc của starter. Người dùng không phải tự khai báo từng JAR nếu họ chọn cách dùng starter này.

## 5. Ví dụ Gradle cho cùng cấu trúc

Nếu dự án dùng Gradle, có thể giữ nguyên quy tắc tên module:

```groovy
// settings.gradle
rootProject.name = 'acme-parent'

include 'acme-core'
include 'acme-spring-boot'
include 'acme-spring-boot-starter'
```

Module auto-configuration:

```groovy
// acme-spring-boot/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    api 'org.springframework.boot:spring-boot-autoconfigure'
    implementation project(':acme-core')

    compileOnly 'com.acme:acme-client:1.0.0'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
```

Module starter:

```groovy
// acme-spring-boot-starter/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    implementation project(':acme-spring-boot')
    implementation 'com.acme:acme-client:1.0.0'
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Đây là mẫu Gradle cho dự án đã cấu hình dependency management/BOM Spring Boot. `compileOnly` của client trong module auto-configuration giúp module biên dịch mà không ép dependency client thành runtime dependency chung; starter thêm client ở runtime cho trường hợp sử dụng mặc định. Điều chỉnh `api`/`implementation` theo việc kiểu của dependency có xuất hiện trong API công khai hay không.

Không cần khai báo version riêng cho mọi dependency Spring Boot khi BOM/plugin đã quản lý phiên bản. Hãy chọn baseline Spring Boot mà thư viện hỗ trợ và kiểm thử trên các phiên bản tương thích đã công bố.

## 6. Package Java phải thuộc namespace của nhà cung cấp

Artifact name không quyết định Java package. Một module tên `acme-spring-boot` nên đặt class trong package do tổ chức sở hữu, ví dụ:

```text
com.acme.report
com.acme.report.core
com.acme.report.autoconfigure
com.acme.report.autoconfigure.properties
```

Một auto-configuration có thể là:

```java
package com.acme.report.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(ReportClient.class)
@EnableConfigurationProperties(ReportProperties.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ReportService reportService(ReportClient client, ReportProperties properties) {
        return new DefaultReportService(client, properties);
    }
}
```

Đây là đoạn cấu hình minh họa; `ReportClient`, `ReportProperties`, `ReportService` và `DefaultReportService` thuộc thư viện `com.acme` và cần được định nghĩa tương ứng.

Không đặt class của thư viện bên thứ ba vào package do Spring sở hữu như `org.springframework.boot` hoặc `org.springframework.boot.autoconfigure`. Package riêng giúp tránh xung đột tên lớp, tránh phụ thuộc vào package nội bộ và làm rõ quyền sở hữu API.

### Auto-configuration không phải component được quét thông thường

Spring Boot tìm auto-configuration thông qua file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Trong module `acme-spring-boot`, nội dung file ví dụ:

```text
com.acme.report.autoconfigure.ReportAutoConfiguration
```

Mỗi dòng là một FQCN của auto-configuration. Có thể liệt kê nhiều class, một class mỗi dòng. Với nested class không phải top-level, dùng ký hiệu `$` giữa tên class chứa và tên nested class.

Spring Boot yêu cầu auto-configuration được nạp bằng imports file; **không dùng component scanning làm cơ chế tìm auto-configuration**. Auto-configuration cũng không nên tự bật component scan để tìm các component khác. Dùng `@Import` cụ thể khi cần đăng ký cấu hình bổ sung.

Phân biệt:

- Component scan của ứng dụng tìm các `@Component` trong package scan.
- `AutoConfiguration.imports` đăng ký các lớp auto-configuration được thư viện phát hành.
- `@Import` đăng ký một cấu hình hoặc component cụ thể mà auto-configuration cần.

## 7. Configuration property phải dùng prefix do thư viện sở hữu

Nếu starter cung cấp các khóa cấu hình, hãy đặt prefix riêng theo tên dự án hoặc tổ chức:

```yaml
acme:
  report:
    enabled: true
    endpoint: https://reports.example.test
    timeout: 3s
```

Ví dụ class properties:

```java
package com.acme.report.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.report")
public class ReportProperties {

    /**
     * Whether the Acme report integration is enabled.
     */
    private boolean enabled = true;

    /**
     * Endpoint used to submit reports.
     */
    private URI endpoint;

    /**
     * Timeout for sending a report.
     */
    private Duration timeout = Duration.ofSeconds(3);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Prefix `acme.report` thuộc về thư viện. Không dùng các namespace Spring Boot đang sở hữu như:

- `spring.*`
- `server.*`
- `management.*`

Ví dụ nên tránh:

```yaml
spring:
  report:
    enabled: true

management:
  acme:
    endpoint: https://reports.example.test

server:
  acme:
    timeout: 3s
```

Dù những khóa này có thể bind về mặt kỹ thuật, chúng xâm phạm namespace của Spring Boot hoặc một nhóm chức năng khác. Spring Boot có thể bổ sung các khóa trong những namespace đó ở phiên bản tương lai; khi ấy thư viện có thể xung đột, bị override hoặc thay đổi hành vi ngoài dự kiến.

**Quy tắc thực hành:** mọi khóa của thư viện nên bắt đầu bằng một prefix duy nhất mà nhà cung cấp kiểm soát, chẳng hạn `acme`, `mycompany.observability` hoặc `vendor.messaging`.

### 7.1. Tên khóa nên ổn định và có ý nghĩa

Nhóm cấu hình theo chức năng:

```yaml
acme:
  report:
    enabled: true
    endpoint: https://reports.example.test
    connect-timeout: 2s
    read-timeout: 5s
```

Dùng relaxed binding để ánh xạ `connect-timeout` vào field `connectTimeout`. Tránh các tên quá chung như `enabled` ở root toàn ứng dụng; prefix giúp xác định tính năng sở hữu khóa.

### 7.2. Viết Javadoc cho từng property

Spring Boot khuyến nghị mô tả các khóa cấu hình bằng field Javadoc để metadata và IDE có thể cung cấp trợ giúp. Với kiểu boolean, mô tả thường bắt đầu bằng “Whether” hoặc “Enable”; với collection, nêu rõ dạng dữ liệu; với `Duration`, mô tả đơn vị mặc định nếu khác milliseconds.

Thêm annotation processor phù hợp để sinh metadata cấu hình. Khi publish, kiểm tra file `META-INF/spring-configuration-metadata.json` có chứa prefix và mô tả đúng. Metadata không thay thế validation, nhưng cải thiện khả năng khám phá cấu hình của người dùng.

## 8. Dependency tùy chọn và điều kiện classpath

Một module auto-configuration có thể tích hợp với thư viện client tùy chọn. Nếu dependency đó bị kéo vào tất cả ứng dụng, người dùng có thể nhận thêm JAR không cần thiết hoặc kích hoạt auto-configuration ngoài dự kiến.

Spring Boot hướng dẫn đánh dấu dependency tới thư viện tích hợp là optional trong module auto-configuration để module đó dễ được tái sử dụng. Starter sẽ quyết định dependency nào nên có mặt trong bộ mặc định.

Ví dụ:

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(ReportClient.class)
    @EnableConfigurationProperties(ReportProperties.class)
    static class ReportClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        ReportService reportService(
                ReportClient client,
                ReportProperties properties) {
            return new DefaultReportService(client, properties);
        }
    }
}
```

Nested configuration tách riêng các method tham chiếu tới client tùy chọn. Condition classpath ở cấp cấu hình con giúp tránh nạp sớm các chữ ký method sử dụng kiểu không có trong runtime classpath. Cần bảo đảm các class và method tham chiếu client tùy chọn đều nằm trong phạm vi được cô lập phù hợp.

Không thêm dependency tùy chọn vào starter mặc định nếu phần lớn người dùng không cần nó. Có thể phát hành starter riêng cho flavor đó, ví dụ `acme-spring-boot-starter-reporting` hoặc `acme-spring-boot-starter-cloud`, miễn vẫn giữ tên dự án đứng trước.

## 9. Metadata và các file cần có khi đóng gói

Một module auto-configuration thường cần quan tâm đến những file metadata sau:

| File | Vai trò |
|---|---|
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Khai báo auto-configuration candidate cho Spring Boot |
| `META-INF/spring-configuration-metadata.json` | Mô tả configuration properties cho IDE và công cụ |
| `META-INF/spring-autoconfigure-metadata.properties` | Metadata condition để Boot có thể lọc sớm một số auto-configuration |

Không phải mọi dự án cần tự tạo cả ba file bằng tay. Annotation processor và build tool có thể sinh metadata tương ứng. Khi đóng gói JAR, hãy kiểm tra file cần thiết thực sự nằm trong artifact phát hành.

Đối với Gradle, annotation processor cho metadata điều kiện auto-configuration có thể khai báo:

```groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'
}
```

Đối với configuration properties, dùng `spring-boot-configuration-processor` theo hướng dẫn Spring Boot. Hai processor phục vụ metadata khác nhau; đừng nhầm file condition metadata với file mô tả property.

## 10. Kiểm thử starter từ góc nhìn người dùng

Không chỉ kiểm tra module auto-configuration riêng lẻ. Một bài kiểm thử tích hợp quan trọng là tạo ứng dụng mẫu chỉ phụ thuộc vào **starter công khai**, rồi xác nhận:

1. Dependency graph có các thư viện cần thiết.
2. Auto-configuration được nạp từ imports file trong JAR.
3. Property prefix riêng được bind.
4. Bean mặc định được tạo khi điều kiện phù hợp.
5. Bean người dùng có thể override mặc định.
6. Tính năng tùy chọn không kích hoạt khi dependency tương ứng vắng mặt.
7. Không cần component scan package nội bộ của thư viện.

Một test cơ bản cho properties/bean có thể dùng `ApplicationContextRunner`:

```java
package com.acme.report.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReportAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ReportAutoConfiguration.class)
                    );

    @Test
    void bindsPropertiesUnderOwnedNamespace() {
        runner.withPropertyValues(
                        "acme.report.enabled=true",
                        "acme.report.endpoint=https://reports.example.test",
                        "acme.report.timeout=1500ms"
                )
                .run(context -> {
                    assertTrue(context.containsBean("reportProperties"));

                    ReportProperties properties =
                            context.getBean(ReportProperties.class);

                    assertEquals(
                            "https://reports.example.test",
                            properties.getEndpoint().toString()
                    );
                    assertEquals(
                            java.time.Duration.ofMillis(1500),
                            properties.getTimeout()
                    );
                });
    }
}
```

Đoạn test giả định `ReportAutoConfiguration` đăng ký `ReportProperties` bằng `@EnableConfigurationProperties(ReportProperties.class)`. Test dùng `ApplicationContextRunner` để kiểm tra binding; nó không chứng minh imports file đã được đóng gói đúng, vì class được truyền trực tiếp vào `AutoConfigurations.of`.

Để kiểm tra artifact thực tế, cần có consumer smoke test phụ thuộc tọa độ `com.acme:acme-spring-boot-starter` đã publish hoặc install vào repository local. Consumer đó chỉ khai báo starter, không khai báo trực tiếp module auto-configuration và không component-scan package thư viện.

## 11. Quy trình xác minh artifact trước khi phát hành

### 11.1. Kiểm tra tên tọa độ

Xác nhận artifact phát hành có đúng dạng:

```text
com.acme:acme-spring-boot:1.0.0
com.acme:acme-spring-boot-starter:1.0.0
com.acme:acme-spring-boot-starter-test:1.0.0
```

Không có module bên thứ ba nào bắt đầu bằng `spring-boot`.

### 11.2. Kiểm tra dependency graph

Với Maven:

```bash
mvn dependency:tree
```

Với Gradle:

```bash
./gradlew dependencies
```

Xác nhận starter mang theo đúng module auto-configuration và các dependency cần thiết; dependency tùy chọn không bị kéo vào ngoài ý định.

### 11.3. Kiểm tra nội dung JAR

Sau khi build:

```bash
jar tf acme-spring-boot-1.0.0.jar
jar tf acme-spring-boot-starter-1.0.0.jar
```

Trong JAR auto-configuration, xác nhận có:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-configuration-metadata.json
```

File imports phải chứa đúng FQCN của auto-configuration. Starter JAR có thể chỉ chứa metadata Maven và không có class Java; đó là bình thường đối với starter chỉ gom dependency.

### 11.4. Kiểm tra package và configuration namespace

- Các class của thư viện nằm trong package do tổ chức sở hữu, ví dụ `com.acme...`.
- Không có class bên thứ ba trong package `org.springframework.boot...`.
- Mọi property bắt đầu bằng `acme.` hoặc prefix do nhà cung cấp kiểm soát.
- Không có property tự đặt trong `spring.`, `server.` hoặc `management.`.
- Các field properties có mô tả và metadata tương ứng.

### 11.5. Kiểm tra với một ứng dụng mẫu

Tạo consumer app nhỏ, chỉ thêm starter dependency. Khởi động context, xem Condition Evaluation Report nếu cần và kiểm tra bean/property. Đây là cách xác nhận trải nghiệm thực của người dùng, bao gồm dependency transitive và cơ chế tìm auto-configuration.

## 12. Các lỗi thường gặp

1. **Đặt tên `spring-boot-starter-acme` vì thấy starter chính thức dùng cùng mẫu.** Đây là tiền tố dành cho artifact chính thức. Đổi thành `acme-spring-boot-starter`.
2. **Cho rằng groupId riêng cho phép artifact bắt đầu bằng `spring-boot`.** Tài liệu Spring Boot nói rõ quy tắc tên module vẫn áp dụng dù groupId khác.
3. **Đặt property trong `spring.acme`.** Prefix `spring` thuộc namespace Spring Boot. Dùng `acme`.
4. **Đặt property trong `management.acme` hoặc `server.acme`.** Hai namespace này phục vụ chức năng Spring Boot riêng; dùng prefix của thư viện.
5. **Đặt class vào `org.springframework.boot.autoconfigure`.** Package đó không thuộc thư viện bên thứ ba. Tạo package riêng như `com.acme.report.autoconfigure`.
6. **Dùng component scan để nạp auto-configuration.** Đăng ký FQCN qua `AutoConfiguration.imports`.
7. **Cho starter chứa mọi dependency có thể có.** Starter chỉ nên đưa dependency thường cần; tách flavor tùy chọn khi cần.
8. **Không đánh dấu dependency client tùy chọn ở module auto-configuration.** Module tích hợp trở nên khó tái sử dụng và kéo dependency không cần thiết vào ứng dụng.
9. **Quên core starter.** Custom starter phải tham chiếu `spring-boot-starter` trực tiếp hoặc gián tiếp.
10. **Quên metadata property.** Người dùng khó khám phá khóa cấu hình trong IDE; thêm Javadoc và annotation processor.
11. **Chỉ test class auto-configuration, không test starter JAR.** Test runner có thể đăng ký class trực tiếp và bỏ qua lỗi thiếu imports file; thêm consumer smoke test.
12. **Không kiểm tra JAR sau publish.** File imports hoặc metadata có thể không được đóng gói dù source tree nhìn đúng.

## 13. Checklist thiết kế starter bên thứ ba

| Hạng mục | Kết quả mong muốn |
|---|---|
| Tên module | Bắt đầu bằng tên dự án/tổ chức, không bắt đầu `spring-boot` |
| Maven groupId | Namespace của nhà cung cấp, ví dụ `com.acme` |
| Auto-configuration module | `acme-spring-boot` |
| Starter module | `acme-spring-boot-starter` |
| Test starter (nếu có) | `acme-spring-boot-starter-test` |
| Java package | Namespace riêng như `com.acme.report.autoconfigure` |
| Auto-configuration registration | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Property prefix | Prefix riêng như `acme.report` |
| Dependency tùy chọn | Được cô lập/đánh dấu optional ở module auto-configuration |
| Core starter | Có `spring-boot-starter` trực tiếp hoặc gián tiếp |
| Property metadata | Có Javadoc và metadata được sinh |
| Verification | Dependency tree, JAR contents và consumer smoke test đều đạt |

## 14. Ghi nhớ

- Starter bên thứ ba **không bắt đầu tên module bằng `spring-boot`**, bất kể `groupId` là gì.
- Dùng tên dự án trước, ví dụ `acme-spring-boot-starter`.
- Tách `acme-spring-boot` và `acme-spring-boot-starter` khi cần phân biệt code auto-configuration với dependency bundle.
- Dùng package Java do nhà cung cấp sở hữu, ví dụ `com.acme...`.
- Đăng ký auto-configuration bằng `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; không dùng component scan để tìm auto-configuration.
- Mọi configuration property phải nằm dưới namespace riêng, ví dụ `acme.report`; tránh `spring`, `server` và `management`.
- Starter là dependency descriptor; không nên chứa các dependency tùy chọn không cần thiết.
- Đánh dấu dependency thư viện tích hợp tùy chọn ở module auto-configuration và để starter quyết định dependency mặc định.
- Kiểm tra JAR đã publish và một ứng dụng consumer thực tế, không chỉ kiểm tra source code.

### Tài liệu Spring Boot 3.3 chính thức

- Build Systems — Starters và quy tắc tên bên thứ ba: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Creating Your Own Auto-configuration — module starter, naming, configuration keys, imports và dependency optional: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
