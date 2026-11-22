# Khi nào nên tách starter khỏi mã tự cấu hình và khi nào có thể gộp?

## 1. Bài toán kiến trúc

Khi phát triển thư viện tích hợp Spring Boot, có hai phần thường đi cùng nhau nhưng có nhiệm vụ khác nhau:

- **Auto-configuration** là mã Java mô tả cách Spring Boot tự tạo và cấu hình bean: điều kiện áp dụng, property cần bind, dependency cần có và cách cho phép ứng dụng ghi đè mặc định.
- **Starter** là artifact Maven/Gradle giúp người dùng thêm một dependency duy nhất để nhận được thư viện cùng những dependency thường cần cho trường hợp sử dụng đó.

Có thể phát hành hai phần thành **hai module riêng**, hoặc **gộp mã auto-configuration và dependency descriptor vào cùng một module**. Spring Boot cho phép cả hai cách. Quyết định phụ thuộc số lượng integration, dependency tùy chọn, các biến thể sản phẩm và nhu cầu tái sử dụng.

Câu hỏi cần trả lời không phải “một dự án chuẩn bắt buộc có bao nhiêu module?”, mà là:

1. Có ai cần dùng auto-configuration mà không muốn dùng dependency bundle mặc định của starter không?
2. Có nhiều biến thể hoặc integration tùy chọn cần được chọn độc lập không?
3. Mã auto-configuration có giá trị tái sử dụng bởi nhiều starter khác nhau không?
4. Chi phí phát hành, quản lý version và kiểm thử thêm module có được bù lại bằng tính linh hoạt thực tế không?

**Quy tắc quyết định:** tách khi mã auto-configuration là một thành phần tái sử dụng độc lập hoặc cần nhiều cách đóng gói dependency; gộp khi auto-configuration nhỏ, chỉ có một cách sử dụng phổ biến và không có dependency tùy chọn cần tách riêng.

Bài viết dùng Spring Boot **3.5.x**, Java 17+ và Maven để minh họa. Tên module và cấu trúc có thể điều chỉnh theo Gradle hoặc hệ thống build khác.

## 2. Phân biệt ba trách nhiệm: core library, auto-configuration và starter

Trong thư viện tích hợp có thể có ba lớp trách nhiệm:

| Thành phần | Chứa gì? | Người dùng cần khi nào? |
| --- | --- | --- |
| **Core library** | API nghiệp vụ, client, model, protocol, xử lý chính; lý tưởng là ít phụ thuộc Spring nếu có thể | Khi cần dùng thư viện độc lập với Spring Boot hoặc tích hợp bằng cách khác |
| **Auto-configuration module** | Các lớp `@AutoConfiguration`, `@ConfigurationProperties`, điều kiện, bean mặc định và callback API | Khi muốn dùng logic tích hợp Spring Boot nhưng tự chọn dependency và cách đóng gói |
| **Starter module** | Chủ yếu là dependency descriptor, kéo auto-configuration, core library và các dependency cần cho kịch bản phổ biến | Khi muốn thêm một dependency duy nhất và bắt đầu sử dụng nhanh |

Không phải thư viện nào cũng cần đủ ba module. Nếu phần core vốn đã là một thư viện độc lập, có thể giữ riêng. Nếu dự án chỉ có một vài bean Spring và không có logic nào cần tái sử dụng ngoài Boot, core library riêng có thể không cần thiết.

**Starter thường là một JAR gần như rỗng về mã nguồn.** Nhiệm vụ chính của nó là khai báo dependency phù hợp. Mã Java của auto-configuration nên nằm trong module có trách nhiệm rõ ràng, hoặc cùng module với starter nếu dự án chọn cách gộp.

### Sơ đồ khi tách

~~~text
Ứng dụng Spring Boot
        |
        v
acme-spring-boot-starter
        |
        +--------------------+
        |                    |
        v                    v
acme-spring-boot       acme-client
(auto-configuration)  (core library)
        |
        v
spring-boot-autoconfigure
~~~

Starter kéo các artifact cần thiết. Module auto-configuration chứa mã Spring Boot integration và có thể đánh dấu dependency core là optional để module này được dùng trong những dependency composition khác.

### Sơ đồ khi gộp

~~~text
Ứng dụng Spring Boot
        |
        v
acme-spring-boot-starter
        |
        +-- Auto-configuration classes
        +-- Configuration properties
        +-- META-INF/...AutoConfiguration.imports
        +-- Required library dependencies
~~~

Cùng một JAR vừa chứa mã tự cấu hình vừa khai báo dependency cần thiết. Spring Boot vẫn nạp auto-configuration qua imports file; việc gộp artifact không làm mất cơ chế condition hoặc bean back-off.

## 3. Khi nào nên tách thành auto-configuration module và starter module?

### 3.1. Có nhiều integration hoặc dependency tùy chọn

Đây là lý do mạnh nhất để tách. Ví dụ một thư viện Acme có thể kết nối tới dịch vụ bằng:
- HTTP client;
- Kafka;
- JMS;
- Redis cache;
- một transport nội bộ do khách hàng cung cấp.

Không phải ứng dụng nào cũng cần tất cả các transport. Nếu một starter duy nhất kéo mọi dependency, ứng dụng chỉ dùng HTTP vẫn nhận thêm Kafka, JMS và Redis trên classpath. Điều đó làm tăng dependency graph, bề mặt cấu hình và nguy cơ xung đột version.

Có thể tổ chức:

~~~text
acme-client
acme-spring-boot
acme-spring-boot-starter
acme-spring-boot-starter-kafka
acme-spring-boot-starter-jms
acme-spring-boot-starter-redis
~~~

Trong đó:
- `acme-spring-boot` chứa API và auto-configuration chung;
- starter cơ bản cung cấp dependency tối thiểu cho HTTP;
- starter Kafka bổ sung Kafka integration;
- starter JMS bổ sung JMS integration;
- starter Redis bổ sung cache integration.

Mỗi starter chỉ kéo dependency phù hợp. Các ứng dụng cũng có thể phụ thuộc trực tiếp vào `acme-spring-boot` rồi tự chọn transport mà họ cần.

### 3.2. Có nhiều cách đóng gói dependency cho cùng một auto-configuration

Một nhóm nền tảng có thể muốn cung cấp một starter tối giản; nhóm sản phẩm khác muốn starter đã tích hợp metrics, tracing hoặc client cụ thể. Cả hai có thể dùng chung một module auto-configuration.

Ví dụ:

~~~text
acme-spring-boot
    ^
    |
    +-- acme-spring-boot-starter-minimal
    |
    +-- acme-spring-boot-starter-observed
    |
    +-- company-platform-acme-starter
~~~

Nếu auto-configuration và starter bị gộp cứng trong một artifact, các đội muốn một dependency bundle khác có thể phải kéo thêm những dependency không cần thiết hoặc tự lặp lại mã cấu hình.

Tách giúp **tái sử dụng logic auto-configuration** trong khi mỗi starter thể hiện một lựa chọn dependency riêng.

### 3.3. Có người dùng muốn tự phối dependency

Một thư viện có thể được dùng trong:
- ứng dụng Spring Boot;
- ứng dụng Spring Framework không dùng Boot;
- một starter do công ty khác duy trì;
- ứng dụng chỉ muốn property binding/callback API nhưng tự tạo client bean;
- hệ thống cần thay transport hoặc implementation mặc định.

Nếu auto-configuration module có thể được dùng độc lập, downstream có thể thêm nó cùng dependency mà họ chọn. Starter mặc định chỉ là một cách đóng gói tiện lợi, không phải cách sử dụng duy nhất.

### 3.4. Cần phát hành và kiểm thử các thành phần theo nhịp khác nhau

Tách có thể hữu ích khi:
- core library có chu kỳ release riêng;
- auto-configuration hỗ trợ nhiều version của thư viện;
- dependency bundle thay đổi nhanh hơn API cấu hình;
- nhiều nhóm chịu trách nhiệm các starter khác nhau;
- muốn kiểm thử auto-configuration độc lập với từng dependency bundle.

Tuy nhiên, tách module cũng tạo thêm trách nhiệm: đồng bộ version, dependency management, publish order, compatibility matrix và pipeline CI. Chỉ nên làm khi lợi ích này có thật.

## 4. Khi nào có thể gộp?

Spring Boot Reference nói rõ: nếu auto-configuration tương đối đơn giản và **không có tính năng tùy chọn**, gộp auto-configuration với starter là lựa chọn hợp lệ.

Các dấu hiệu phù hợp để gộp:

- Chỉ có một thư viện nền tảng và một integration mặc định.
- Dependency cần thiết là bắt buộc cho hầu hết người dùng.
- Không có nhiều flavor hoặc starter opinion khác nhau.
- Không có downstream cần phụ thuộc vào auto-configuration riêng.
- Mã tự cấu hình nhỏ, ít callback và không cần versioning độc lập.
- Dự án nhỏ hoặc nội bộ, lợi ích của module bổ sung chưa bù được chi phí duy trì.

Ví dụ:

~~~text
acme-spring-boot-starter
    ├── src/main/java/.../AcmeAutoConfiguration.java
    ├── src/main/java/.../AcmeProperties.java
    ├── src/main/resources/META-INF/spring/
    │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── pom.xml
~~~

Trong một artifact:
- POM khai báo dependency cần thiết;
- source chứa auto-configuration;
- imports file đăng ký class với Spring Boot;
- metadata property được tạo khi build.

**Gộp artifact không có nghĩa gộp mọi trách nhiệm vào một class.** Vẫn nên chia package/class theo cấu hình, properties, integration và điều kiện để mã dễ đọc và kiểm thử.

### Không nên tạo module chỉ vì “có thể sau này cần”

Một dự án nhỏ có thể bắt đầu với một starter duy nhất. Khi xuất hiện nhu cầu thực tế như Kafka flavor, optional transport hoặc downstream starter khác, có thể tách module ở một release có kế hoạch. Việc tạo sẵn nhiều module chưa có người dùng hoặc use case làm tăng số artifact, version và build step mà chưa mang lại giá trị.

## 5. Bảng quyết định nhanh

| Câu hỏi | Nếu câu trả lời là “có” | Hướng nên cân nhắc |
| --- | --- | --- |
| Có nhiều transport hoặc integration tùy chọn? | Mỗi ứng dụng cần chọn một nhóm dependency khác nhau | Tách auto-configuration và các starter theo flavor |
| Có downstream muốn tự tạo starter? | Họ cần logic auto-config nhưng có dependency bundle riêng | Phát hành auto-configuration module độc lập |
| Có người dùng cần dùng library mà không dùng starter? | Họ muốn tự chọn dependency hoặc tự cấu hình bean | Tách core/auto-configuration theo trách nhiệm |
| Có nhiều starter cùng dùng chung một logic auto-config? | Không muốn copy/paste cấu hình | Tách module dùng chung |
| Chỉ có một integration và dependency bắt buộc? | Mọi người dùng đều cần cùng một bộ dependency | Có thể gộp |
| Auto-configuration rất nhỏ, không có optional features? | Không có lợi ích rõ ràng từ artifact riêng | Có thể gộp |
| Việc tách làm tăng release/compatibility overhead đáng kể? | Chưa có lợi ích đủ lớn | Giữ cấu trúc đơn giản, đánh giá lại khi có use case |

Một tiêu chí hữu ích là **dependency graph**: nếu starter kéo một dependency mà nhiều ứng dụng không cần, hoặc nếu nhiều starter phải lặp lại cùng một dependency/auto-config code, đã có tín hiệu nên tách.

## 6. Ví dụ kiến trúc Maven khi tách

Giả sử có thư viện core `acme-client` với API tạo client. Dự án phát hành hai module Spring Boot:

- `acme-spring-boot-autoconfigure`: chứa properties, auto-configuration và test của chúng;
- `acme-spring-boot-starter`: dependency descriptor dành cho người dùng muốn cấu hình mặc định.

Tên `-autoconfigure` là cách đặt tên tường minh thường gặp. Tài liệu Spring Boot 3.5 cũng minh họa module auto-configuration bằng tên `acme-spring-boot` và starter bằng `acme-spring-boot-starter`. Tên artifact không phải điều kiện runtime; quan trọng là vai trò và dependency graph.

### 6.1. Cấu trúc repository

~~~text
acme-parent/
├── pom.xml
├── acme-client/
│   ├── pom.xml
│   └── src/main/java/com/example/acme/AcmeClient.java
├── acme-spring-boot-autoconfigure/
│   ├── pom.xml
│   ├── src/main/java/com/example/acme/autoconfigure/
│   │   ├── AcmeAutoConfiguration.java
│   │   └── AcmeProperties.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/acme/autoconfigure/
│       └── AcmeAutoConfigurationTests.java
└── acme-spring-boot-starter/
    └── pom.xml
~~~

### 6.2. POM của auto-configuration module

Ví dụ rút gọn, giả sử parent/BOM đã quản lý version Spring Boot và các plugin:

~~~xml
<artifactId>acme-spring-boot-autoconfigure</artifactId>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-client</artifactId>
        <version>1.4.0</version>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

Điểm quan trọng:
- `spring-boot-autoconfigure` cung cấp API auto-configuration.
- `acme-client` được khai báo optional để người dùng có thể dùng auto-configuration module mà tự chọn cách cung cấp library dependency.
- `spring-boot-autoconfigure-processor` tạo metadata tối ưu condition khi build; cấu hình annotation processor theo hướng dẫn của Boot.
- Nếu auto-configuration cần thêm API Spring Boot, Spring Framework hoặc thư viện khác ở compile time, khai báo dependency đúng scope và version management.

**Maven optional có ý nghĩa gì?** Dependency optional vẫn có mặt khi build/test chính module này, nhưng không tự được truyền xuống dependency graph của người dùng như dependency thông thường. Vì vậy starter phải khai báo rõ các library dependency mà nó muốn cung cấp cho ứng dụng.

### 6.3. POM của starter module

~~~xml
<artifactId>acme-spring-boot-starter</artifactId>

<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-spring-boot-autoconfigure</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-client</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

Starter:
- phụ thuộc vào auto-configuration module;
- kéo core library cần cho kịch bản cơ bản;
- kéo core Spring Boot starter trực tiếp hoặc gián tiếp;
- không thêm mọi dependency tùy chọn chỉ để “phòng khi cần”.

Nếu HTTP integration cần một HTTP client cụ thể, hãy đưa dependency đó vào starter HTTP tương ứng hoặc starter cơ bản khi nó thật sự là dependency bắt buộc. Nếu Kafka là tùy chọn, tạo starter Kafka riêng.

Trong dự án thật, nên quản lý version qua parent POM hoặc BOM để tránh lặp version ở nhiều module. Các artifact nội bộ của cùng một release cần được publish với version tương thích.

## 7. Ví dụ mã auto-configuration trong module riêng

### 7.1. Configuration properties

File `AcmeProperties.java`:

~~~java
package com.example.acme.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("acme.client")
public record AcmeProperties(URI endpoint, Duration timeout) {
}
~~~

Hai property được bind:
- `acme.client.endpoint`: địa chỉ dịch vụ Acme;
- `acme.client.timeout`: timeout kết nối hoặc request theo hợp đồng của core client.

Trong thư viện thực tế, cần Javadoc mô tả rõ từng property, đơn vị của duration nếu có default khác milliseconds và quy tắc validation. Hãy dùng namespace thuộc sở hữu của dự án, ví dụ `acme.client`, tránh đưa key riêng vào namespace `spring`, `server` hoặc `management`.

### 7.2. Auto-configuration

Giả sử core library có class `AcmeClient` và constructor nhận endpoint/timeout:

~~~java
package com.example.acme.autoconfigure;

import com.example.acme.AcmeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AcmeClient.class)
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(AcmeClient.class)
        AcmeClient acmeClient(AcmeProperties properties) {
            return new AcmeClient(
                    properties.endpoint(),
                    properties.timeout());
        }
    }
}
~~~

Ví dụ trên minh họa các nguyên tắc:
- `@AutoConfiguration` đánh dấu class cấu hình được Boot nạp.
- `@EnableConfigurationProperties` đăng ký và bind properties.
- Nested configuration có `@ConditionalOnClass` để cô lập phần tham chiếu đến thư viện tùy chọn.
- `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp `AcmeClient` riêng; bean mặc định sẽ back off khi bean phù hợp đã có.
- Method trả về đúng kiểu `AcmeClient` để condition có đủ type information.

**Tại sao đặt class condition trên nested configuration?** Khi dependency là optional, không nên để một method trong class luôn được xử lý có return type hoặc reference trực tiếp đến class có thể vắng mặt. Tách nhánh có điều kiện giúp class tùy chọn không bị nạp/xử lý trong trường hợp thư viện không có trên runtime classpath.

Đây là cấu hình minh họa; constructor và package của `AcmeClient` phải khớp API core library thực tế.

### 7.3. Đăng ký auto-configuration

Trong module auto-configuration, tạo file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

~~~text
com.example.acme.autoconfigure.AcmeAutoConfiguration
~~~

Spring Boot 3.x đọc file này từ JAR đã publish; mỗi dòng là một fully qualified class name. Auto-configuration phải được đăng ký qua imports file. Không dùng component scan để tìm các lớp auto-configuration; dùng `@Import` cho những cấu hình cụ thể cần kết hợp.

Nếu có nhiều cấu hình riêng, ví dụ `AcmeAutoConfiguration` và `AcmeKafkaAutoConfiguration`, có thể khai báo nhiều dòng và quản lý thứ tự bằng `before`/`after` hoặc annotation ordering phù hợp.

## 8. Khi gộp auto-configuration và starter vào một module

Với dự án nhỏ, có thể đặt cả POM dependency và mã auto-configuration trong cùng artifact:

~~~text
acme-spring-boot-starter/
├── pom.xml
└── src/main/
    ├── java/com/example/acme/autoconfigure/
    │   ├── AcmeAutoConfiguration.java
    │   └── AcmeProperties.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

POM khai báo:
- dependency Spring Boot cần để viết auto-configuration;
- core library bắt buộc;
- `spring-boot-starter` trực tiếp hoặc gián tiếp;
- annotation processor và plugin build phù hợp.

Khi người dùng thêm một dependency `acme-spring-boot-starter`, họ nhận cả mã cấu hình và dependency cần thiết. Không cần publish artifact autoconfigure riêng.

### Ví dụ POM rút gọn cho module gộp

~~~xml
<artifactId>acme-spring-boot-starter</artifactId>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-client</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

Với cách gộp, dependency `acme-client` có thể là dependency bắt buộc của starter. Nếu sau này nó trở thành optional hoặc có nhiều transport khác nhau, hãy cân nhắc tách module thay vì kéo mọi thư viện vào starter chung.

**Dù gộp, vẫn cần kiểm thử auto-configuration độc lập.** Có một artifact không có nghĩa bỏ qua condition tests, properties tests hoặc kiểm tra imports file.

## 9. Kiểm thử auto-configuration độc lập với starter

Auto-configuration module nên có test riêng. `ApplicationContextRunner` cho phép kiểm tra các tổ hợp:
- library có trên classpath;
- library bị loại khỏi classpath;
- property có/không có;
- user bean được cung cấp;
- auto-configuration mặc định có back off đúng không.

Ví dụ test với JUnit 5 và AssertJ:

~~~java
package com.example.acme.autoconfigure;

import java.net.URI;
import java.time.Duration;

import com.example.acme.AcmeClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenLibraryIsPresent() {
        runner.withPropertyValues(
                "acme.client.endpoint=https://api.example.test",
                "acme.client.timeout=2s"
        ).run(context ->
                assertThat(context).hasSingleBean(AcmeClient.class));
    }

    @Test
    void userClientMakesDefaultBeanBackOff() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .withPropertyValues(
                        "acme.client.endpoint=https://api.example.test",
                        "acme.client.timeout=2s"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context).hasBean("customAcmeClient");
                    assertThat(context).doesNotHaveBean("acmeClient");
                });
    }

    @Test
    void missingOptionalLibraryDisablesClientConfiguration() {
        runner.withClassLoader(new FilteredClassLoader(AcmeClient.class))
                .run(context ->
                        assertThat(context).doesNotHaveBean("acmeClient"));
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new AcmeClient(
                    URI.create("https://custom.example.test"),
                    Duration.ofSeconds(1));
        }
    }
}
~~~

Test trên giả định constructor của core `AcmeClient` nhận `URI` và `Duration` như ví dụ. Nếu API thật khác, thay phần tạo object nhưng giữ các assertion về condition và bean back-off.

### 9.1. Vì sao cần test FilteredClassLoader?

Khi dependency được khai báo optional, test phải chứng minh auto-configuration **không lỗi khi class vắng mặt**. `FilteredClassLoader` mô phỏng runtime classpath thiếu một class hoặc package.

Không chỉ assert rằng không có bean; test cần khởi động context thành công để phát hiện lỗi linkage do một method signature hoặc class-level reference chạm vào optional dependency quá sớm.

### 9.2. Vì sao cần test user override?

Một auto-configuration tốt cung cấp default nhưng cho phép ứng dụng tự định nghĩa bean. `@ConditionalOnMissingBean` là một trong các cơ chế phổ biến để làm điều đó.

Test user override chứng minh:
- bean do ứng dụng định nghĩa được giữ;
- bean mặc định không bị đăng ký thêm;
- không xuất hiện hai bean cùng kiểu gây mơ hồ injection.

### 9.3. Test starter như một consumer thật

Test trong auto-configuration module chưa chứng minh starter JAR đã kéo đúng dependency hoặc imports file đã được đóng gói đúng. Nên có ít nhất một consumer smoke test:
1. Tạo module/sample app chỉ khai báo dependency starter.
2. Không import auto-configuration class thủ công.
3. Khởi động bằng `SpringApplication` hoặc `@SpringBootTest`.
4. Xác nhận bean mặc định được đăng ký.
5. Kiểm tra dependency tree để chắc starter không kéo các integration không mong muốn.

Đây là test packaging/integration; `ApplicationContextRunner` trong auto-config module là test logic condition. Hai tầng bổ sung cho nhau.

## 10. Optional dependencies và nhiều starter flavor

Khi tách module, phải phân biệt dependency **optional trong auto-configuration module** và dependency **được starter chọn kéo vào**.

Ví dụ:

| Artifact | Acme core | Kafka | Redis | Auto-configuration |
| --- | --- | --- | --- | --- |
| `acme-spring-boot-autoconfigure` | Optional | Optional | Optional | Có |
| `acme-spring-boot-starter` | Bắt buộc | Không | Không | Kéo autoconfigure |
| `acme-spring-boot-starter-kafka` | Bắt buộc | Bắt buộc | Không | Kéo autoconfigure |
| `acme-spring-boot-starter-redis` | Bắt buộc | Không | Bắt buộc | Kéo autoconfigure |

Nếu mỗi starter chỉ kéo dependency phù hợp, ứng dụng không cần Redis sẽ không nhận Redis client chỉ vì dùng Acme HTTP starter.

Trong auto-configuration, tách các nhánh bằng class condition:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(KafkaTemplate.class)
static class KafkaConfiguration {

    // Các bean Kafka-specific đặt tại đây.
}
~~~

Đây là đoạn minh họa; trong code thật, mọi type reference đến Kafka nên nằm trong nhánh được cô lập bằng condition để ứng dụng không có Kafka dependency vẫn khởi động được.

**Không biến mọi dependency thành optional một cách máy móc.** Nếu auto-configuration không thể hoạt động khi thiếu một dependency, hãy:
- đánh dấu dependency optional và dùng condition để bỏ qua tính năng;
- hoặc coi dependency đó là bắt buộc trong module/starter tương ứng;
- hoặc tách một starter flavor riêng.

Mục tiêu là dependency graph phản ánh đúng hợp đồng sử dụng.

## 11. Metadata và chất lượng trải nghiệm người dùng

Một starter tốt không chỉ giúp ứng dụng compile. Người dùng cần biết property nào được hỗ trợ, kiểu dữ liệu, ý nghĩa, default và giá trị hợp lệ.

Với `@ConfigurationProperties`:
- Dùng prefix riêng, ví dụ `acme.client`.
- Viết Javadoc cho từng field/property.
- Dùng kiểu `Duration` cho khoảng thời gian thay vì số nguyên không có đơn vị rõ ràng.
- Tạo metadata bằng `spring-boot-configuration-processor` khi thích hợp.
- Kiểm tra file `META-INF/spring-configuration-metadata.json` trong artifact build.

Trong auto-configuration module, Spring Boot còn có annotation processor `spring-boot-autoconfigure-processor` để thu thập condition metadata vào:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Metadata condition có thể giúp Boot lọc sớm auto-configuration không phù hợp, hỗ trợ thời gian khởi động. Với Maven, tài liệu Boot 3.5 hướng dẫn cấu hình annotation processor thông qua `maven-compiler-plugin` từ phiên bản 3.12.0 trở lên; với Gradle, khai báo trong configuration `annotationProcessor`.

Đừng nhầm hai file:
- `spring-configuration-metadata.json` mô tả property cho IDE và người dùng.
- `spring-autoconfigure-metadata.properties` chứa metadata điều kiện để tối ưu việc lọc auto-configuration.

## 12. Versioning, dependency management và tương thích

Tách module giúp tái sử dụng nhưng cũng yêu cầu quản lý version rõ ràng.

### Khi tách

- Giữ các artifact cùng release tương thích, ví dụ core 1.4.x, autoconfigure 1.4.x và starter 1.4.x.
- Quản lý version Spring Boot bằng parent/BOM phù hợp, không để mỗi module tự kéo một phiên bản Boot khác nhau.
- Kiểm thử các cặp version core library và Boot mà bạn cam kết hỗ trợ.
- Nếu starter flavor có lifecycle riêng, công bố rõ version của nó tương thích với autoconfigure nào.
- Tránh để module starter phụ thuộc ngược vào module autoconfigure qua một vòng dependency.
- Không để core library phụ thuộc ngược vào starter; core phải là nền thấp hơn trong dependency graph.

### Khi gộp

- Một artifact version hóa cùng mã auto-configuration và dependency bundle.
- Ít artifact và release pipeline đơn giản hơn.
- Nếu dependency transitive thay đổi, cần đánh giá ảnh hưởng tới mọi ứng dụng đang dùng starter.
- Khi thêm optional integration, cân nhắc tách starter flavor hoặc module riêng để tránh làm dependency graph phình lên.

Một BOM riêng có thể hữu ích khi có nhiều artifact và cần quản lý version đồng bộ. Với một starter duy nhất, BOM riêng thường chưa cần thiết.

## 13. Tên artifact và package

Với thư viện bên thứ ba, không đặt tên module bắt đầu bằng `spring-boot`. Prefix này được dành cho artifact chính thức của Spring Boot.

Tên ví dụ:
- `acme-spring-boot-autoconfigure`: module auto-configuration;
- `acme-spring-boot-starter`: starter thông thường;
- `acme-spring-boot-starter-kafka`: starter cho Kafka;
- `acme-spring-boot-starter-test`: test starter nếu thực sự có test-specific auto-configuration.

Spring Boot 3.5 Reference minh họa auto-configuration module tên `acme-spring-boot` và starter `acme-spring-boot-starter`. Suffix `-autoconfigure` là lựa chọn đặt tên dễ hiểu, không phải điều kiện để Boot nhận diện module.

Package auto-configuration nên tách khỏi package component scan của ứng dụng tiêu thụ. Auto-configuration được nạp qua `AutoConfiguration.imports`; không cần component scan toàn bộ package của thư viện.

## 14. Starter test có cần tách riêng không?

Một số thư viện cần hỗ trợ kiểm thử cho ứng dụng tiêu thụ, chẳng hạn:
- fake/in-memory transport;
- test fixture;
- embedded server;
- mock bean hoặc utility cấu hình test;
- test-specific auto-configuration thay external dependency bằng implementation trong bộ nhớ.

Nếu các công cụ này có giá trị dùng chung và không nên nằm trong runtime starter, có thể phát hành:

~~~text
acme-spring-boot-starter-test
~~~

Người dùng thêm nó ở scope test:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-starter-test</artifactId>
    <version>1.4.0</version>
    <scope>test</scope>
</dependency>
~~~

Không cần tạo test starter chỉ để chứa một helper nhỏ chỉ được dùng trong một module. Tách khi test integration là một API hỗ trợ chính thức cho nhiều ứng dụng hoặc nhiều nhóm.

## 15. Các sai lầm kiến trúc thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Một starter kéo mọi integration tùy chọn | Dependency graph lớn, dễ xung đột và tăng bề mặt cấu hình | Tách starter theo flavor hoặc integration |
| Auto-configuration module bắt buộc kéo toàn bộ library | Downstream không thể tự chọn dependency | Đánh dấu dependency tùy chọn và dùng class condition khi phù hợp |
| Starter không khai báo core library vì nghĩ autoconfigure optional sẽ truyền xuống | Ứng dụng chỉ thêm starter nhưng thiếu library runtime | Starter khai báo dependency core rõ ràng |
| Gộp tất cả vào một module dù có nhiều starter khác nhau | Các starter lặp dependency hoặc kéo thừa | Tách module auto-configuration dùng chung |
| Tách module quá sớm | Nhiều artifact, version, pipeline và tài liệu hơn cần thiết | Bắt đầu đơn giản; tách khi có nhu cầu thật |
| Đặt dependency tùy chọn vào starter cơ bản | Người dùng không dùng tính năng vẫn nhận dependency | Đưa vào starter flavor phù hợp |
| Auto-configuration dùng component scan | Có thể quét nhầm package ứng dụng hoặc nạp cấu hình ngoài dự kiến | Đăng ký qua imports file và dùng `@Import` |
| Không có `AutoConfiguration.imports` | Auto-configuration JAR không được Boot tự nạp | Kiểm tra file resource trong JAR đã build |
| Optional class xuất hiện ở method signature ngoài nhánh condition | Có thể gặp lỗi class loading khi dependency vắng mặt | Cô lập trong nested configuration có `@ConditionalOnClass` |
| Không test classpath thiếu library | Starter không an toàn khi optional integration không có | Dùng `FilteredClassLoader` |
| Chỉ test auto-configuration mà không test starter | Có thể thiếu dependency hoặc imports resource trong artifact | Thêm consumer smoke test |
| Không quản lý version giữa các module | Dễ gặp NoSuchMethodError hoặc dependency convergence issue | Dùng parent/BOM và compatibility matrix |

## 16. Quy trình quyết định và triển khai

Có thể dùng checklist sau trước khi tạo module:

1. Liệt kê library runtime thực sự cần và dependency tùy chọn.
2. Xác định có ai cần dùng auto-configuration mà không dùng starter mặc định không.
3. Xác định có nhiều starter flavor hoặc integration độc lập không.
4. Nếu chỉ có một integration bắt buộc, cân nhắc gộp.
5. Nếu có nhiều dependency composition, tạo auto-configuration module độc lập và các starter dependency-only.
6. Giữ core library độc lập với Spring Boot nếu nó có giá trị ngoài hệ sinh thái Boot.
7. Viết condition rõ ràng cho classpath, property và user bean override.
8. Đăng ký auto-configuration trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
9. Tạo configuration metadata và condition metadata.
10. Test default, property disabled, missing optional class, user override và các starter flavor.
11. Thêm consumer smoke test để xác nhận artifact đã publish hoạt động khi chỉ khai báo starter.
12. Kiểm tra dependency tree và xác nhận starter không kéo các integration không được chọn.

### Kết quả quyết định nên được ghi như thế nào?

Một quyết định kiến trúc ngắn gọn nên giải thích:
- **Vì sao tách/gộp:** use case thực tế và số lượng dependency composition.
- **Module nào sở hữu trách nhiệm nào:** core, auto-config, starter, test starter.
- **Dependency nào bắt buộc/tùy chọn:** và starter nào kéo chúng.
- **Tương thích:** version Spring Boot và version library được hỗ trợ.
- **Kiểm thử:** test nào chứng minh back-off, missing class và packaging.

Nếu không có lý do thực tế cho một artifact riêng, giữ một module đơn giản thường dễ bảo trì hơn. Khi có nhiều cách đóng gói hoặc nhiều người tiêu thụ auto-configuration, tách module tạo ra ranh giới có ích và cho phép tái sử dụng.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Starter có bắt buộc phải chứa mã Java auto-configuration không?

**Đáp án:** Không. Starter thường chỉ là dependency descriptor. Mã auto-configuration có thể nằm trong module riêng mà starter kéo vào.

**Câu 2.** Khi nào nên tách auto-configuration và starter?

**Đáp án:** Khi có nhiều flavor/optional dependency, downstream muốn tự phối dependency hoặc nhiều starter dùng chung logic auto-configuration.

**Câu 3.** Khi nào có thể gộp?

**Đáp án:** Khi auto-configuration đơn giản, không có tính năng tùy chọn, một dependency bundle đáp ứng gần như mọi người dùng và không cần artifact auto-config độc lập.

**Câu 4.** Vì sao dependency của thư viện trong auto-configuration module thường được đánh dấu optional?

**Đáp án:** Để module auto-configuration có thể được dùng mà không bắt buộc kéo library dependency vào mọi consumer. Khi library không có, condition classpath cho phép Boot bỏ qua nhánh cấu hình tương ứng.

**Câu 5.** Starter cần khai báo gì nếu dependency core trong auto-configuration module là optional?

**Đáp án:** Starter phải khai báo core library như dependency thông thường nếu đó là thành phần cần thiết cho kịch bản sử dụng mặc định.

**Câu 6.** Làm thế nào chứng minh auto-configuration hoạt động khi optional library không có?

**Đáp án:** Dùng `ApplicationContextRunner` với `FilteredClassLoader` để mô phỏng thiếu class và xác nhận context khởi động mà không đăng ký bean phụ thuộc class đó.

**Câu 7.** Vì sao cần consumer smoke test?

**Đáp án:** Test trong auto-configuration module không chứng minh starter đã đóng gói đúng imports file và dependency transitive. Consumer test kiểm tra trải nghiệm sử dụng thật: thêm starter là Boot tự nạp cấu hình.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, phần Creating Your Own Starter, autoconfigure module, starter module và test starter: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Reference — Build Systems, phần Starters và quy ước đặt tên: https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html
- Spring Boot 3.5 Reference — Configuration Metadata: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/index.html
- Spring Boot 3.5 API — `AutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.5 API — `ConditionalOnClass`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
