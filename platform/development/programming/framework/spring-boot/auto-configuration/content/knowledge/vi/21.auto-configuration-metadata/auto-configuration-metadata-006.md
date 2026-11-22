# Quy ước đặt tên starter bên thứ ba và tránh chiếm namespace Spring Boot

## 1. Namespace là một phần của hợp đồng thư viện

Một starter là điểm vào để ứng dụng thêm dependency, nhận các thư viện nền tảng, auto-configuration và cấu hình mặc định. Nếu tên artifact, Java package hoặc property prefix trùng với namespace của Spring Boot, thư viện có thể gây nhầm lẫn khi cài đặt và xung đột khi Spring Boot bổ sung tính năng mới.

Có ba phạm vi cần thiết kế riêng:

1. **Namespace phát hành:** Maven `groupId`, `artifactId` và tên module Gradle; xác định tọa độ dependency.
2. **Namespace mã nguồn:** Java package chứa API, implementation và auto-configuration; xác định quyền sở hữu class.
3. **Namespace cấu hình:** prefix của `application.yml` hoặc `application.properties`; xác định thư viện nào sở hữu và có thể thay đổi property.

Ví dụ xuyên suốt bài dùng thư viện giả định Northstar Audit:

| Phạm vi | Namespace do thư viện sở hữu |
|---|---|
| Maven group | `io.northstar` |
| Auto-configuration artifact | `northstar-spring-boot` |
| Starter artifact | `northstar-spring-boot-starter` |
| Java package | `io.northstar.audit.autoconfigure` |
| Property prefix | `northstar.audit` |

Tên ví dụ không đại diện cho artifact đã phát hành. Khi áp dụng, thay bằng domain, tên dự án và thương hiệu mà tổ chức thực sự sở hữu.

## 2. Quy tắc tên module bên thứ ba

Spring Boot dành tiền tố module `spring-boot` cho artifact chính thức. **Module bên thứ ba không được bắt đầu bằng `spring-boot`, kể cả khi Maven `groupId` đã khác.** Nếu nhiều nhà cung cấp cùng dùng tiền tố này, người dùng khó nhận ra nguồn gốc artifact và có thể nhầm với hỗ trợ chính thức của Spring Boot.

Tên nên bắt đầu bằng tên dự án hoặc tổ chức, sau đó mô tả vai trò tích hợp:

~~~text
northstar-spring-boot
northstar-spring-boot-starter
northstar-spring-boot-starter-test
northstar-spring-boot-starter-messaging
~~~

Một số tên cần tránh:

~~~text
spring-boot-starter-northstar
spring-boot-northstar-starter
spring-boot-audit
~~~

Đổi `groupId` sang `io.northstar` không làm cho artifact bắt đầu bằng `spring-boot` trở thành tên phù hợp.

### 2.1. Phân biệt `groupId`, `artifactId` và tên module

Tọa độ Maven có dạng:

~~~text
groupId:artifactId:version
~~~

Ví dụ:

~~~text
io.northstar:northstar-spring-boot-starter:1.2.0
~~~

- `groupId` xác định nhóm phát hành, thường theo domain đảo ngược mà tổ chức kiểm soát.
- `artifactId` xác định module cụ thể. Với starter bên thứ ba, tên nên bắt đầu bằng thương hiệu/dự án.
- `version` xác định bản phát hành và phải được quản lý nhất quán giữa các module cùng release train.

Gradle cũng công bố dependency bằng tọa độ tương tự:

~~~groovy
dependencies {
    implementation 'io.northstar:northstar-spring-boot-starter:1.2.0'
}
~~~

Không nên nhầm tên thư mục trong repository với tọa độ đã publish. Một dự án có thể dùng thư mục `boot-integration` nhưng artifact công khai là `northstar-spring-boot`; người dùng và repository resolve tọa độ được khai báo trong build.

### 2.2. Chọn tên theo số lượng module

| Thiết kế | Tên gợi ý | Khi phù hợp |
|---|---|---|
| Một module gộp code và dependency | `northstar-spring-boot-starter` | Tích hợp nhỏ, không có nhiều dependency tùy chọn |
| Module auto-configuration | `northstar-spring-boot` | Muốn ứng dụng hoặc starter khác tái sử dụng phần tích hợp |
| Module gom dependency mặc định | `northstar-spring-boot-starter` | Muốn người dùng chỉ khai báo một dependency |
| Test support riêng | `northstar-spring-boot-starter-test` | Có fixture hoặc cấu hình thay thế chỉ dùng trong test |
| Nhiều flavor độc lập | `northstar-spring-boot-starter-messaging` | Có thể bật từng tích hợp theo dependency riêng |

Nếu thư viện có nhiều flavor, tên vẫn bắt đầu bằng `northstar`. Không đổi thứ tự thành `spring-boot-starter-northstar-messaging`.

## 3. Chia module theo trách nhiệm

Cấu trúc thường dùng:

~~~text
northstar-parent/
├── northstar-core/
│   └── API và logic nghiệp vụ độc lập Spring
├── northstar-spring-boot/
│   ├── NorthstarAuditAutoConfiguration.java
│   ├── AuditProperties.java
│   └── META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── northstar-spring-boot-starter/
│   └── pom.xml hoặc build.gradle
└── northstar-spring-boot-starter-test/
    └── test fixtures và test auto-configuration
~~~

`northstar-core` không cần phụ thuộc Spring Boot nếu logic audit có thể dùng trong ứng dụng Java khác. Module `northstar-spring-boot` chứa adapter cho Spring Boot, còn starter gom các dependency thường dùng.

### 3.1. Module auto-configuration

Module này có thể chứa:

- Lớp `@AutoConfiguration` và các nested configuration có điều kiện.
- Lớp `@ConfigurationProperties` cùng metadata mô tả property.
- Callback hoặc extension point để ứng dụng tùy chỉnh khởi tạo.
- Điều kiện classpath, bean, property, resource và loại ứng dụng.
- Tài nguyên `AutoConfiguration.imports` để Boot tìm cấu hình.
- Test kiểm tra điều kiện và bean mặc định.

Giữ dependency của thư viện tích hợp ở dạng tùy chọn khi có thể. Nhờ vậy, ứng dụng chỉ dùng một phần thư viện không phải mang theo client hoặc SDK của những tính năng khác.

### 3.2. Module starter

Starter thường là JAR gần như rỗng về mã nguồn. Vai trò của nó là khai báo dependency để ứng dụng có đủ thành phần cần thiết cho trường hợp sử dụng phổ biến:

- Module auto-configuration của Northstar.
- Thư viện client Northstar cần ở runtime.
- Core Spring Boot starter, trực tiếp hoặc thông qua một starter khác.
- Các starter nền tảng mà tích hợp thực sự cần.

Starter nên thể hiện một lựa chọn dependency có chủ đích. Nếu thư viện có nhiều tích hợp tùy chọn, tạo các starter nhỏ theo flavor thay vì kéo mọi SDK vào một starter duy nhất.

### 3.3. Test starter

Test starter có thể cung cấp fixture, fake client, cấu hình in-memory hoặc helper để kiểm tra tích hợp. Dependency test không nên bị kéo vào ứng dụng production chỉ vì ứng dụng dùng starter runtime.

Tên test starter vẫn giữ thương hiệu ở đầu: `northstar-spring-boot-starter-test`.

## 4. Package Java thuộc quyền sở hữu của nhà cung cấp

Dùng package theo domain đảo ngược mà tổ chức kiểm soát. Với ví dụ này:

~~~text
io.northstar.audit
io.northstar.audit.api
io.northstar.audit.core
io.northstar.audit.autoconfigure
io.northstar.audit.autoconfigure.properties
~~~

Không đặt class bên thứ ba vào package thuộc Spring như `org.springframework.boot` hoặc `org.springframework.boot.autoconfigure`. Package đó dành cho Spring; việc tự thêm class vào đó có thể tạo xung đột classpath và khiến code phụ thuộc vào chi tiết nội bộ.

Nên phân chia package theo vai trò:

- `api`: interface mà ứng dụng có thể gọi hoặc implement.
- `core`: logic không phụ thuộc Spring.
- `autoconfigure`: các class cấu hình tự động.
- `autoconfigure.properties`: nhóm property và kiểu cấu hình nếu số lượng đủ lớn.
- `internal`: implementation không phải API công khai, nếu cần tách rõ.

Tránh package quá chung như `util` hoặc `config` ở root của thư viện lớn. Package cụ thể giúp người dùng hiểu class thuộc tích hợp nào và giảm khả năng va chạm với dependency khác.

## 5. Đăng ký auto-configuration bằng imports file

Spring Boot tìm auto-configuration trong JAR đã publish qua tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Trong module `northstar-spring-boot`, file có thể chứa:

~~~text
io.northstar.audit.autoconfigure.NorthstarAuditAutoConfiguration
io.northstar.audit.autoconfigure.NorthstarAuditMetricsAutoConfiguration
~~~

Mỗi dòng là tên lớp đầy đủ của một auto-configuration. Có thể thêm comment bắt đầu bằng `#`. Nếu auto-configuration là nested class, tên lớp dùng `$` để ngăn cách class chứa và nested class.

**Auto-configuration chỉ được nạp khi được liệt kê trong imports file.** Không dựa vào component scanning để tìm nó và không bật component scan từ auto-configuration nhằm dò các component khác. Nếu cần đăng ký một cấu hình hoặc component cụ thể, dùng `@Import` với class đích.

Ví dụ:

~~~java
package io.northstar.audit.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@Import(AuditInfrastructureConfiguration.class)
public class NorthstarAuditAutoConfiguration {
}
~~~

`AuditInfrastructureConfiguration` là cấu hình cụ thể thuộc cùng thư viện. Cách này giới hạn rõ các class được import, giúp kiểm soát phạm vi khởi động và tránh quét nhầm component trong package con.

### 5.1. Khi đổi tên hoặc di chuyển auto-configuration

Tên auto-configuration có thể được tham chiếu trong `before`, `after` hoặc exclusions của ứng dụng khác. Khi phải thay package hoặc tên class đã phát hành, Spring Boot hỗ trợ tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Ví dụ ánh xạ tên cũ sang tên mới:

~~~text
io.northstar.audit.autoconfigure.NorthstarAuditAutoConfiguration=io.northstar.audit.autoconfigure.core.NorthstarAuditAutoConfiguration
~~~

Khi dùng cơ chế replacements, cập nhật `AutoConfiguration.imports` để chỉ liệt kê class thay thế. Tài nguyên này giúp Spring Boot xử lý tham chiếu tới class cũ trong metadata ordering/exclusion; nó không tự thay thế mọi import Java hoặc API công khai trong mã ứng dụng. Thay đổi package public vẫn cần kế hoạch tương thích và migration riêng.

## 6. Property prefix phải là namespace riêng

Nếu starter cung cấp cấu hình, mọi khóa nên nằm dưới một prefix duy nhất do thư viện sở hữu. Ví dụ:

~~~yaml
northstar:
  audit:
    enabled: true
    endpoint: https://audit.example.test
    connect-timeout: 2s
    batch-size: 250
~~~

Các namespace như `spring`, `server` và `management` thuộc Spring Boot. Không đặt property của thư viện bên thứ ba vào những nhóm này. Ví dụ sau nên tránh:

~~~yaml
spring:
  audit:
    enabled: true

server:
  northstar:
    endpoint: https://audit.example.test

management:
  northstar:
    batch-size: 250
~~~

Việc một property có thể bind về mặt kỹ thuật không có nghĩa thư viện nên sở hữu namespace đó. Spring Boot có thể mở rộng các nhóm cấu hình của mình trong phiên bản sau; khóa của thư viện đặt nhầm vào đó có thể trùng tên hoặc thay đổi ý nghĩa.

### 6.1. Thiết kế tên property ổn định

Dùng cấu trúc phân cấp có ý nghĩa:

~~~text
northstar.audit.enabled
northstar.audit.endpoint
northstar.audit.connect-timeout
northstar.audit.batch-size
northstar.audit.include-principal
~~~

Một vài quy tắc hữu ích:

- Dùng chữ thường và dấu gạch nối trong tên property.
- Nhóm các khóa theo chức năng, không tạo prefix mới cho từng field.
- Dùng `Duration` cho thời gian thay vì `long` không có đơn vị.
- Dùng kiểu dữ liệu cụ thể như `URI`, `Duration`, `DataSize`, enum và collection khi phù hợp.
- Đặt mặc định có chủ đích và ghi rõ đơn vị khi giá trị không dùng đơn vị chuẩn.
- Không dùng tên chung như `enabled` ở root toàn bộ ứng dụng.

Property prefix là một phần API của starter. Khi người dùng đã lưu `northstar.audit.connect-timeout` trong cấu hình triển khai, đổi tên khóa có thể làm tích hợp mất cấu hình sau khi nâng cấp.

## 7. Ví dụ `@ConfigurationProperties` và auto-configuration

Lớp properties đặt trong package riêng và có prefix do thư viện sở hữu:

~~~java
package io.northstar.audit.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "northstar.audit")
public class AuditProperties {

    /**
     * Whether the Northstar audit integration is enabled.
     */
    private boolean enabled = false;

    /**
     * Endpoint used to submit audit events.
     */
    private URI endpoint;

    /**
     * Timeout for establishing a connection to the audit service.
     */
    private Duration connectTimeout = Duration.ofSeconds(2);

    /**
     * Maximum number of events sent in one batch.
     */
    private int batchSize = 250;

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

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }
}
~~~

Đây là JavaBean properties class. Spring Boot Binder ánh xạ `connect-timeout` sang `connectTimeout`. Các field Javadoc là mô tả plain text để annotation processor đưa vào metadata; không viết Markdown hoặc HTML trong những mô tả này.

Một interface API có thể được định nghĩa trong module core:

~~~java
package io.northstar.audit.api;

public interface AuditService {
    void publish(String event);
}
~~~

Implementation mặc định:

~~~java
package io.northstar.audit.autoconfigure;

import io.northstar.audit.api.AuditService;

final class DefaultAuditService implements AuditService {

    private final AuditProperties properties;

    DefaultAuditService(AuditProperties properties) {
        this.properties = properties;
    }

    @Override
    public void publish(String event) {
        // Gửi event bằng client do thư viện tích hợp cung cấp.
        // Phần triển khai transport phụ thuộc API client thực tế.
    }
}
~~~

Auto-configuration đăng ký properties và bean mặc định:

~~~java
package io.northstar.audit.autoconfigure;

import io.northstar.audit.api.AuditService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(AuditProperties.class)
public class NorthstarAuditAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "northstar.audit",
            name = "enabled",
            havingValue = "true"
    )
    @ConditionalOnMissingBean(AuditService.class)
    AuditService auditService(AuditProperties properties) {
        return new DefaultAuditService(properties);
    }
}
~~~

Đây là ví dụ cấu trúc; phần gửi event cần được nối với client thực tế. Hai điều kiện thể hiện rõ: ứng dụng phải bật `northstar.audit.enabled=true`, và thư viện chỉ tạo bean mặc định khi chưa có `AuditService` do ứng dụng cung cấp.

## 8. Ghi metadata để IDE hỗ trợ người dùng

Spring Boot có hai loại metadata thường được dùng trong module auto-configuration:

| Tài nguyên | Mục đích |
|---|---|
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Khai báo auto-configuration được Boot nạp |
| `META-INF/spring-configuration-metadata.json` | Mô tả property, kiểu dữ liệu, group, default và hint cho IDE |
| `META-INF/spring-autoconfigure-metadata.properties` | Thông tin condition giúp Boot lọc sớm auto-configuration không phù hợp |

Hai metadata file không thay thế imports file. Imports file quyết định class nào là auto-configuration candidate; configuration metadata mô tả các khóa cấu hình; auto-configure metadata ghi nhận điều kiện để hỗ trợ lọc sớm.

### 8.1. Configuration metadata processor

Thêm `spring-boot-configuration-processor` vào annotation processor để sinh `spring-configuration-metadata.json` từ class `@ConfigurationProperties`. Javadoc trên field được dùng làm description. Với record, mô tả component nên được đặt trong class-level Javadoc bằng tag `@param`.

Spring Boot khuyến nghị mô tả nhất quán:

- Boolean: bắt đầu bằng “Whether” hoặc “Enable”.
- Collection: nêu dạng dữ liệu, ví dụ “Comma-separated list”.
- Thời lượng: dùng `Duration`; ghi đơn vị mặc định nếu không có suffix.
- Không mở đầu bằng “The” hoặc “A”.
- Không lặp giá trị mặc định trong description trừ khi mặc định được quyết định lúc runtime.

### 8.2. Auto-configuration metadata processor

`spring-boot-autoconfigure-processor` thu thập condition của auto-configuration và sinh `spring-autoconfigure-metadata.properties`. Nếu metadata có mặt, Spring Boot có thể lọc sớm các cấu hình không match, giúp giảm công việc khởi động.

Đây là metadata tối ưu hóa và không thay thế việc viết condition đúng. Sau khi build, kiểm tra JAR có file được sinh và nội dung tương ứng với các class thực tế.

## 9. Dependency tùy chọn và starter không phình to

Giả sử Northstar có core API và một client HTTP tùy chọn:

- Module auto-configuration cần compile với kiểu client để khai báo bean.
- Ứng dụng chỉ dùng phần core không nhất thiết cần client HTTP.
- Starter tiêu chuẩn có thể chọn đưa client HTTP vào runtime vì đó là lựa chọn mặc định của starter.

Trong Maven, module auto-configuration có thể đánh dấu dependency client là optional:

~~~xml
<dependency>
    <groupId>io.northstar</groupId>
    <artifactId>northstar-audit-client</artifactId>
    <version>2.4.0</version>
    <optional>true</optional>
</dependency>
~~~

Starter có thể khai báo dependency client như dependency runtime thông thường:

~~~xml
<dependency>
    <groupId>io.northstar</groupId>
    <artifactId>northstar-audit-client</artifactId>
    <version>2.4.0</version>
</dependency>
~~~

Trong Gradle, `compileOnly` có thể dùng để biên dịch module auto-configuration với kiểu client mà không đưa client thành runtime dependency mặc định của module đó; starter thêm client bằng `implementation`.

Khi client là tùy chọn, đặt các method có chữ ký tham chiếu tới client bên trong nested configuration được bảo vệ bằng `@ConditionalOnClass`. Spring Boot đọc metadata condition ở cấp class; điều kiện trên riêng `@Bean` method có thể đến quá muộn vì JVM đã phải xử lý chữ ký method. Tách nested configuration giúp cô lập kiểu tùy chọn.

Không đưa mọi client, database driver, SDK cloud hoặc integration không cần thiết vào starter mặc định. Nếu nhiều người dùng chỉ cần một phần, tạo starter theo flavor để họ chọn dependency phù hợp.

## 10. Ví dụ cấu trúc Maven

Parent POM có thể gom module và import Spring Boot BOM:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>io.northstar</groupId>
    <artifactId>northstar-parent</artifactId>
    <version>1.2.0</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
        <spring-boot.version>3.3.13</spring-boot.version>
    </properties>

    <modules>
        <module>northstar-core</module>
        <module>northstar-spring-boot</module>
        <module>northstar-spring-boot-starter</module>
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
~~~

Đây là parent POM minh họa. Dự án cũng có thể dùng `spring-boot-starter-parent`; điều quan trọng là tất cả module dùng cùng baseline Spring Boot đã chọn.

Module auto-configuration có tọa độ:

~~~xml
<artifactId>northstar-spring-boot</artifactId>
~~~

Dependencies chính:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>io.northstar</groupId>
        <artifactId>northstar-core</artifactId>
        <version>1.2.0</version>
    </dependency>

    <dependency>
        <groupId>io.northstar</groupId>
        <artifactId>northstar-audit-client</artifactId>
        <version>2.4.0</version>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

Để sinh metadata, cấu hình Maven Compiler Plugin phiên bản 3.12.0 trở lên với hai annotation processor:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.12.1</version>
    <configuration>
        <release>17</release>
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
~~~

Module starter có artifact ID `northstar-spring-boot-starter` và chủ yếu chứa dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>io.northstar</groupId>
        <artifactId>northstar-spring-boot</artifactId>
        <version>1.2.0</version>
    </dependency>

    <dependency>
        <groupId>io.northstar</groupId>
        <artifactId>northstar-audit-client</artifactId>
        <version>2.4.0</version>
    </dependency>
</dependencies>
~~~

Starter có thể là JAR không chứa Java class nào. Đây là thiết kế bình thường: nó tồn tại để cung cấp một tập dependency đã được chọn. Nếu starter phụ thuộc vào một starter khác đã kéo `spring-boot-starter` vào, không cần khai báo core starter lặp lại.

## 11. Ví dụ cấu trúc Gradle

Trong `settings.gradle`:

~~~groovy
rootProject.name = 'northstar-parent'

include 'northstar-core'
include 'northstar-spring-boot'
include 'northstar-spring-boot-starter'
~~~

Module auto-configuration:

~~~groovy
// northstar-spring-boot/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    api platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    api 'org.springframework.boot:spring-boot-autoconfigure'

    implementation project(':northstar-core')
    compileOnly 'io.northstar:northstar-audit-client:2.4.0'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Module starter:

~~~groovy
// northstar-spring-boot-starter/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation project(':northstar-spring-boot')
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'io.northstar:northstar-audit-client:2.4.0'
}
~~~

Trong Gradle, `compileOnly` không đồng nghĩa với việc client đã được đóng gói vào starter. Starter cần khai báo runtime dependency nếu muốn người dùng chỉ thêm starter là có client. Nếu một kiểu dependency xuất hiện trong public API của module, cân nhắc `api` hoặc `compileOnlyApi` phù hợp với hợp đồng mà module công bố.

## 12. Kiểm thử từ module đến starter đã publish

Có hai mức kiểm thử khác nhau.

### 12.1. Kiểm thử auto-configuration trực tiếp

Dùng `ApplicationContextRunner` để kiểm tra:

- Property prefix có bind đúng không.
- Khi `northstar.audit.enabled=false`, bean mặc định không xuất hiện.
- Khi property bật, bean mặc định xuất hiện.
- Khi ứng dụng tự cung cấp `AuditService`, auto-configuration nhường chỗ.
- Khi thư viện client tùy chọn vắng mặt, cấu hình phụ thuộc client không làm context lỗi.

Ví dụ kiểm thử cấu hình cơ bản:

~~~java
package io.northstar.audit.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NorthstarAuditAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    NorthstarAuditAutoConfiguration.class
                            )
                    );

    @Test
    void doesNotCreateServiceWhenDisabled() {
        runner.withPropertyValues("northstar.audit.enabled=false")
                .run(context ->
                        assertFalse(context.containsBean("auditService"))
                );
    }

    @Test
    void createsServiceWhenEnabled() {
        runner.withPropertyValues("northstar.audit.enabled=true")
                .run(context ->
                        assertTrue(context.containsBean("auditService"))
                );
    }
}
~~~

Ví dụ này giả định implementation mặc định không cần client ngoài và được khai báo đúng như auto-configuration ở mục 7. Với cấu hình thực tế, thêm test cho bean override, property không hợp lệ và classpath tùy chọn bằng `FilteredClassLoader`.

### 12.2. Consumer smoke test cho starter

Test dùng `AutoConfigurations.of(NorthstarAuditAutoConfiguration.class)` đăng ký class trực tiếp. Vì vậy nó **không chứng minh** file imports đã được đóng gói hoặc starter có dependency transitives đúng.

Tạo một ứng dụng consumer nhỏ chỉ khai báo:

~~~xml
<dependency>
    <groupId>io.northstar</groupId>
    <artifactId>northstar-spring-boot-starter</artifactId>
    <version>1.2.0</version>
</dependency>
~~~

Consumer test nên khởi động Spring Boot bình thường, không thêm trực tiếp `northstar-spring-boot` và không component-scan package `io.northstar`. Nếu auto-configuration vẫn được tìm thấy và các bean/property hoạt động, đây là bằng chứng mạnh hơn rằng artifact đã đóng gói đúng.

## 13. Kiểm tra artifact trước khi phát hành

### 13.1. Tọa độ artifact

Danh sách phát hành nên có dạng:

~~~text
io.northstar:northstar-core:1.2.0
io.northstar:northstar-spring-boot:1.2.0
io.northstar:northstar-spring-boot-starter:1.2.0
io.northstar:northstar-spring-boot-starter-test:1.2.0
~~~

Không có module bên thứ ba nào bắt đầu bằng `spring-boot`.

### 13.2. Dependency graph

Với Maven:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew :northstar-spring-boot-starter:dependencies
~~~

Kiểm tra starter kéo đúng auto-configuration module và runtime client cần thiết. Kiểm tra dependency tùy chọn không xuất hiện ở những consumer chỉ cần core hoặc auto-configuration.

### 13.3. Nội dung JAR

Liệt kê tài nguyên trong JAR:

~~~bash
jar tf northstar-spring-boot-1.2.0.jar
jar tf northstar-spring-boot-starter-1.2.0.jar
~~~

Trong JAR auto-configuration, tìm:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-configuration-metadata.json
META-INF/spring-autoconfigure-metadata.properties
~~~

Không phải project nào cũng sinh cả hai file metadata. Nếu có `@ConfigurationProperties`, kiểm tra configuration metadata; nếu bật auto-configure processor, kiểm tra condition metadata. Imports file phải có trong JAR và chứa đúng FQCN.

Starter JAR chỉ gom dependencies có thể không chứa class Java; điều đó không phải lỗi. Kiểm tra POM/module metadata của starter để xác nhận dependency được publish đúng.

### 13.4. Kiểm tra property metadata trong IDE

Dùng IDE hỗ trợ Spring Boot để thử các khóa `northstar.audit.*`. Kiểm tra gợi ý property, kiểu, mô tả và default value có đúng không. Metadata sai có thể khiến người dùng nhập nhầm cấu hình dù ứng dụng vẫn biên dịch.

## 14. Tương thích và thay đổi namespace qua phiên bản

Artifact name, package public và property prefix đều có thể trở thành hợp đồng mà ứng dụng phụ thuộc.

Trước khi phát hành phiên bản mới:

1. Giữ tọa độ `groupId:artifactId` ổn định nếu không có lý do lớn để đổi.
2. Không đổi property prefix hoặc tên khóa chỉ để đồng bộ nội bộ; nếu buộc phải đổi, lập kế hoạch deprecation và migration.
3. Không di chuyển package public mà không đánh giá ảnh hưởng tới import của người dùng.
4. Khi đổi tên auto-configuration, cập nhật imports file và xem xét `AutoConfiguration.replacements` cho tham chiếu ordering/exclusion.
5. Giữ dependency Spring Boot tương thích bằng BOM của baseline đã công bố.
6. Kiểm thử trên các phiên bản Spring Boot mà thư viện tuyên bố hỗ trợ; không mặc định mọi major version đều tương thích.

Spring Boot 3.3 yêu cầu Java 17 trở lên. Nếu starter nhắm vào Boot 3.3, đặt Java release và kiểm thử theo baseline đó. Không tự chọn một phiên bản Spring Framework khác với phiên bản Spring Boot quản lý trừ khi có lý do và kiểm thử tương thích cụ thể.

## 15. Những lỗi thiết kế thường gặp

1. **Đặt artifact thành `spring-boot-starter-northstar`.** Đổi thành tên có thương hiệu đứng trước như `northstar-spring-boot-starter`.
2. **Cho rằng `groupId` riêng cho phép artifact bắt đầu bằng `spring-boot`.** Quy tắc tên module vẫn áp dụng dù groupId khác.
3. **Đặt class vào `org.springframework.boot.*`.** Tạo package theo domain của tổ chức.
4. **Đặt property vào `spring.*`, `server.*` hoặc `management.*`.** Dùng prefix riêng như `northstar.audit`.
5. **Dùng component scan để nạp auto-configuration.** Đăng ký class qua `AutoConfiguration.imports`; dùng `@Import` cho cấu hình phụ trợ cụ thể.
6. **Đưa mọi SDK tùy chọn vào starter mặc định.** Tách flavor starter và để module auto-configuration đánh dấu dependency tùy chọn.
7. **Không có core starter trong dependency graph.** Starter phải phụ thuộc `spring-boot-starter` trực tiếp hoặc gián tiếp.
8. **Không sinh property metadata.** IDE không thể gợi ý tốt các khóa do thư viện sở hữu.
9. **Nhầm hai loại metadata.** Imports file đăng ký auto-configuration; configuration metadata mô tả property; auto-configure metadata hỗ trợ lọc condition.
10. **Chỉ kiểm thử class cấu hình.** Test runner đăng ký class trực tiếp có thể bỏ qua lỗi imports file; thêm consumer smoke test.
11. **Đổi tên auto-configuration mà quên references.** Kiểm tra các thuộc tính `before`, `after`, exclusions và file replacements.
12. **Không kiểm tra dependency transitives sau publish.** Consumer có thể thiếu client runtime hoặc kéo theo thư viện không cần thiết.

## 16. Checklist phát hành

| Hạng mục | Tiêu chí đạt |
|---|---|
| Artifact naming | Module bên thứ ba bắt đầu bằng tên dự án, không bắt đầu `spring-boot` |
| Maven coordinates | `groupId` thuộc tổ chức; `artifactId` ổn định |
| Module layout | Phân biệt core, auto-configuration, starter và test support khi cần |
| Java package | Package nằm trong namespace của nhà cung cấp |
| Auto-configuration discovery | Imports file có trong JAR, đúng FQCN |
| Component scanning | Auto-configuration không là target của scan và không bật scan rộng |
| Property namespace | Prefix riêng, không chiếm `spring`, `server`, `management` |
| Property documentation | Field Javadoc rõ, metadata được sinh và kiểm tra |
| Optional dependencies | Module auto-configuration không ép dependency tùy chọn vào mọi consumer |
| Core starter | Có `spring-boot-starter` trực tiếp hoặc gián tiếp |
| Compatibility | Java/Spring Boot baseline và matrix hỗ trợ được công bố |
| Tests | Unit/runner tests và consumer smoke test đều đạt |
| Packaging | JAR, dependency tree và metadata được kiểm tra sau build |

## 17. Ghi nhớ

- Tên module starter bên thứ ba không bắt đầu bằng `spring-boot`, kể cả khi Maven `groupId` khác.
- Dùng tên dự án đứng trước, chẳng hạn `northstar-spring-boot-starter`.
- Package Java phải thuộc domain/tổ chức sở hữu; không đặt class trong package Spring.
- Property prefix phải là namespace riêng, chẳng hạn `northstar.audit`; tránh `spring`, `server`, `management`.
- Auto-configuration được đăng ký qua `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Module auto-configuration có thể đánh dấu client tùy chọn; starter quyết định bộ dependency mặc định.
- Core Spring Boot starter phải xuất hiện trực tiếp hoặc gián tiếp trong dependency graph.
- Dùng processor để sinh property metadata và auto-configuration metadata; kiểm tra đúng file trong JAR.
- Consumer smoke test xác minh trải nghiệm sử dụng starter tốt hơn việc chỉ kiểm tra class auto-configuration.
- Tên artifact, package public và property prefix là hợp đồng cần được bảo vệ qua các lần phát hành.

### Tài liệu Spring Boot 3.3 chính thức

- Build Systems — Starters và quy tắc tên bên thứ ba: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Creating Your Own Auto-configuration — naming, module structure, imports, property namespace và optional dependencies: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Configuration Metadata — định dạng metadata cấu hình: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
