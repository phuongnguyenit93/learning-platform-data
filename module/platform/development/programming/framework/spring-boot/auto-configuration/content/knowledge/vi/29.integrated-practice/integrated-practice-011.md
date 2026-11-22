# Lập ma trận kiểm thử và tài liệu giao ước để hoàn thiện thư viện tự cấu hình

## 1. Mục tiêu: thư viện phải dễ tích hợp, dễ kiểm chứng và có hành vi được cam kết rõ ràng

Một thư viện Spring Boot auto-configuration hoàn thiện cần làm tốt ba việc:

1. **Tự cấu hình đúng:** bean chỉ xuất hiện khi điều kiện phù hợp, dependency cần thiết có mặt, property hợp lệ và ứng dụng chưa cung cấp implementation thay thế.
2. **Có thể kiểm thử:** mỗi nhánh điều kiện, giá trị cấu hình, đường override, classpath và môi trường được kiểm tra bằng một bộ test có mục đích rõ ràng.
3. **Có giao ước sử dụng:** người dùng biết starter cung cấp gì, property nào được hỗ trợ, giá trị mặc định, điều kiện kích hoạt, bean nào có thể thay thế, lỗi nào xảy ra và phiên bản nào đã được kiểm thử.

Chỉ có unit tests cho service là chưa đủ. Auto-configuration còn phụ thuộc Environment, classpath, bean definitions, thứ tự cấu hình, web application type và dependency graph của consumer. README chỉ có vài dòng cài đặt cũng chưa đủ nếu không nói rõ default behavior và cách ứng dụng tùy biến.

Bài học dùng **Spring Boot 3.3.13, Spring Framework 6.1 và Java 17+**. Ví dụ xây dựng thư viện catalog-spring-boot-autoconfigure, sau đó kiểm thử qua ApplicationContextRunner, một consumer application và các bước kiểm tra artifact đã đóng gói.

Sau bài học, bạn có thể:

- Chọn đúng tầng kiểm thử cho từng rủi ro.
- Lập test matrix bao phủ condition, property, bean override, classpath, web context, failure và packaging.
- Dùng ApplicationContextRunner, FilteredClassLoader, WebApplicationContextRunner và @SpringBootTest.
- Kiểm tra file auto-configuration imports và configuration metadata trong JAR.
- Viết tài liệu giao ước gồm activation rules, properties, beans, override points, dependency requirements, failure behavior và compatibility.
- Đặt các kiểm tra vào CI theo mức độ rủi ro và thời điểm chạy.
- Xác định điều kiện hoàn tất trước khi phát hành starter.

## 2. Giao ước của một auto-configuration library gồm những gì?

Một auto-configuration library không chỉ là tập hợp các @Bean methods. Khi người dùng thêm dependency, họ đang chấp nhận một hợp đồng hành vi. Hợp đồng đó nên trả lời được các câu hỏi sau:

| Phần của giao ước | Câu hỏi người dùng cần được trả lời |
| --- | --- |
| Activation | Cần dependency/class/property/profile nào để auto-configuration hoạt động? |
| Defaults | Nếu không khai báo property, giá trị mặc định là gì? |
| Conditions | Khi nào bean được tạo, khi nào bị bỏ qua? |
| Bean API | Bean type nào được cung cấp? Bean nào là extension point? |
| Override | Người dùng có thể cung cấp bean riêng để thay thế không? |
| Configuration | Property nào được hỗ trợ, kiểu dữ liệu và giới hạn ra sao? |
| Dependencies | Thư viện kéo theo dependency nào? Dependency nào là optional? |
| Startup | Bean có kết nối mạng hoặc đọc file ngay lúc startup không? |
| Errors | Cấu hình sai hoặc dependency không sẵn sàng gây lỗi gì và ở thời điểm nào? |
| Compatibility | Spring Boot, Java và phiên bản thư viện bên thứ ba nào đã được kiểm thử? |
| Packaging | JAR có auto-configuration imports và metadata cần thiết không? |
| Migration | Khi property, bean hoặc default thay đổi, người dùng cần làm gì? |

Nếu một hành vi có thể làm consumer thay đổi kết quả khi nâng version, hành vi đó cần được ghi rõ và có test bảo vệ.

### 2.1. Phân biệt implementation detail với public contract

Không phải mọi class trong package autoconfigure đều là API công khai.

Ví dụ:

- CatalogClient là interface mà ứng dụng được phép inject và thay thế.
- CatalogProperties là public configuration API nếu người dùng được khuyến khích bind hoặc import trực tiếp.
- DefaultCatalogClient có thể là implementation detail nếu thư viện không cam kết concrete type.
- Tên bean nội bộ, helper condition và thứ tự method trong source không nên bị người dùng phụ thuộc nếu tài liệu không công bố.

Hãy quyết định rõ class nào là public API. Những type được công bố trong README, Javadoc hoặc ví dụ consumer sẽ trở thành điểm người dùng dựa vào khi nâng version.

### 2.2. Giao ước bao gồm cả hành vi khi không kích hoạt

Người dùng cần biết:

- Property enabled=false có loại toàn bộ auto-configuration không?
- Nếu dependency optional không có mặt, ứng dụng có tiếp tục chạy không?
- Nếu user bean đã tồn tại, default bean có back off không?
- Nếu property thiếu, feature mặc định bật hay tắt?
- Nếu cấu hình sai, lỗi xảy ra khi bind properties, khi refresh context hay ở lần gọi service đầu tiên?

Các trường hợp không kích hoạt cũng cần được kiểm thử. Một starter tốt không làm ứng dụng thất bại chỉ vì một tính năng optional không được sử dụng.

## 3. Chia kiểm thử thành các tầng có mục đích riêng

Không nên dùng một loại test để cố chứng minh mọi thứ. Mỗi tầng trả lời một nhóm câu hỏi.

| Tầng | Công cụ | Mục tiêu | Thời gian tương đối |
| --- | --- | --- | --- |
| Unit tests | JUnit, AssertJ, Mockito khi cần | Logic thuần, mapping, retry policy, parser và validation helper | Nhanh |
| Auto-configuration tests | ApplicationContextRunner | Condition, property binding, bean creation, back-off và failure | Nhanh |
| Environment/classpath tests | Runner + FilteredClassLoader | Dependency optional, class missing, property source khác nhau | Nhanh |
| Web-context tests | WebApplicationContextRunner, ReactiveWebApplicationContextRunner | Servlet/reactive conditions và web-specific beans | Nhanh đến vừa |
| Consumer integration tests | @SpringBootTest trong ứng dụng consumer | Artifact thực tế được discovery, bind và sử dụng | Vừa |
| Packaging tests | Maven verify, kiểm tra nội dung JAR | Imports file, metadata, dependency scopes và resources | Nhanh |
| Compatibility matrix | CI trên nhiều Boot/JDK/dependency versions | Xác nhận support range đã công bố | Vừa đến lâu |
| End-to-end tests | Test environment có service thật hoặc container | Protocol, authentication, timeout, serialization và network behavior | Lâu |
| Release verification | Consumer project dùng đúng artifact version | Kiểm tra trải nghiệm cài đặt sau publish | Vừa |

Spring Boot khuyến nghị dùng ApplicationContextRunner để tạo một ApplicationContext có cấu hình xác định cho từng tổ hợp user beans, Environment và classpath. Runner không thay thế integration test của ứng dụng consumer; nó kiểm tra auto-configuration cô lập và nhanh.

**Lưu ý native:** ApplicationContextRunner không chạy được khi chính test suite được biên dịch thành native image. Hãy chạy các test này trên JVM; native integration tests là một tầng riêng nếu thư viện công bố hỗ trợ native.

## 4. Lập test matrix trước khi viết test

Test matrix là bản đồ giữa hành vi được cam kết, input, kết quả mong đợi và loại test. Nó giúp phát hiện khoảng trống trước khi release.

### 4.1. Matrix theo điều kiện kích hoạt

| Nhóm | Trường hợp | Kết quả mong đợi | Test phù hợp | Ưu tiên |
| --- | --- | --- | --- | --- |
| Feature property | Property không có | Đúng default đã công bố | ApplicationContextRunner | P0 |
| Feature property | enabled=true | Default beans được tạo | Runner | P0 |
| Feature property | enabled=false | Feature beans không được tạo | Runner | P0 |
| Feature property | Giá trị sai kiểu/không hợp lệ | Binding/validation fail rõ ràng hoặc hành vi đã công bố | Runner | P0 |
| Classpath | Dependency bắt buộc có mặt | Cấu hình liên quan được áp dụng | Runner | P0 |
| Classpath | Dependency optional bị thiếu | Chỉ phần phụ thuộc bị bỏ qua; context vẫn hợp lệ | FilteredClassLoader | P0 |
| Bean condition | Không có user bean | Default bean được tạo | Runner | P0 |
| Bean condition | Có user bean cùng type | Default bean back off | Runner | P0 |
| Bean condition | Có nhiều candidate | @Primary/qualifier hoặc lỗi được định nghĩa rõ | Runner | P1 |
| Resource condition | Resource có mặt | Nhánh tương ứng được bật | Runner | P1 |
| Resource condition | Resource thiếu | Nhánh bị bỏ qua hoặc startup fail theo contract | Runner | P1 |
| Web condition | Servlet context | Chỉ servlet beans được tạo | Web runner | P1 |
| Web condition | Reactive context | Chỉ reactive beans được tạo | Reactive runner | P1 |
| Web condition | Non-web context | Không tạo web-specific beans | Runner | P1 |
| Profile | Profile được hỗ trợ bật | Behavior theo contract | Runner/consumer test | P1 |
| Ordering | Auto-config khác được nạp cùng | Thứ tự bean definitions đúng | Runner | P1 |

### 4.2. Matrix theo property và dữ liệu

| Nhóm property | Trường hợp cần test | Điều cần khẳng định |
| --- | --- | --- |
| Default | Không khai báo key | Giá trị mặc định đúng |
| Override | Giá trị do application.properties cung cấp | Binding đúng |
| Environment | Environment variable hoặc system property | Relaxed binding và precedence đúng |
| Command line | --acme.catalog.timeout=750ms | Giá trị có thể override theo quy tắc Spring Boot |
| Duration | 750ms, 2s, giá trị thiếu unit | Conversion và unit đúng |
| Numeric | Minimum, maximum, ngoài range | Constraint được thực thi |
| String | Rỗng, toàn khoảng trắng, ký tự đặc biệt | Validation và escaping đúng |
| Collection | Rỗng, một phần tử, nhiều phần tử, phần tử sai | Binding và validation của từng item |
| Nested object | Thiếu field con, object hợp lệ | Nested validation có cascade khi cần |
| Deprecated key | Key cũ và key mới cùng xuất hiện | Precedence/migration được định nghĩa rõ |
| Unknown key | Consumer gõ sai prefix hoặc property | Metadata/documentation giúp phát hiện; không hứa Boot luôn reject mọi unknown key |

Spring Boot hỗ trợ nhiều nguồn external configuration và một thứ tự ưu tiên property source xác định. Test nên dùng withPropertyValues cho các trường hợp đơn giản; những trường hợp liên quan Environment thật có thể dùng @SpringBootTest, @DynamicPropertySource hoặc property source phù hợp.

### 4.3. Matrix theo bean contract

| Hành vi | Test case | Assertion |
| --- | --- | --- |
| Default bean | Không có user implementation | Có đúng một bean theo interface |
| User override | Đăng ký bean cùng type | Default bean không được tạo |
| Customization callback | Cung cấp customizer | Customizer được áp dụng theo thứ tự công bố |
| Multiple candidates | Hai implementation | Injection resolution rõ ràng |
| Bean naming | Người dùng dùng @Qualifier nếu được hỗ trợ | Tên/qualifier được giữ ổn định |
| Lazy/eager | Bean được tạo theo chính sách | Lỗi xuất hiện đúng thời điểm |
| Lifecycle | Context đóng | Disposable resource được đóng nếu contract yêu cầu |
| Failure | Constructor/factory method ném exception | Lỗi có nguyên nhân và thông báo có thể hành động |

Không nên assert implementation class cụ thể nếu tài liệu chỉ hứa interface. Hãy assert public type, behavior và override semantics.

### 4.4. Matrix theo dependency và môi trường

| Trục | Các tổ hợp cần cân nhắc |
| --- | --- |
| Spring Boot | Mỗi minor line mà thư viện công bố hỗ trợ; ít nhất version thấp nhất và cao nhất |
| Java | Minimum supported JDK và các LTS đang công bố hỗ trợ |
| Dependency bên thứ ba | Version tối thiểu, version được khuyến nghị, version mới nhất trong dải hỗ trợ |
| Optional module | Có/không có module; chỉ feature phụ thuộc module đó bị ảnh hưởng |
| Application type | Non-web, Servlet, Reactive nếu thư viện hỗ trợ |
| Build tool | Maven/Gradle nếu thư viện cung cấp hướng dẫn cho cả hai |
| Runtime | JVM; Native Image nếu thư viện có tuyên bố hỗ trợ |
| Platform | OS/architecture quan trọng đối với dependency native hoặc file/network behavior |

Không cần chạy mọi tích Descartes của tất cả trục. Chọn tổ hợp có rủi ro cao, boundary versions và các cặp dependency thường xung đột. Ghi rõ những tổ hợp chưa kiểm thử.

## 5. Ví dụ thư viện dùng xuyên suốt

Ta xây dựng một auto-configuration nhỏ cho Catalog client. Giao ước của ví dụ:

- Feature bật mặc định nếu property không có.
- acme.catalog.enabled=false tắt auto-configuration.
- Default client chỉ được tạo nếu ứng dụng chưa cung cấp CatalogClient.
- Endpoint không được để trống.
- Timeout mặc định là hai giây.
- Số lần thử từ 1 đến 10, mặc định là 3.
- Client trong ví dụ lưu cấu hình; phần gọi mạng có thể được triển khai ở adapter riêng.

### 5.1. Cấu trúc module

~~~text
catalog-parent/
├── pom.xml
├── catalog-spring-boot-autoconfigure/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/acme/catalog/autoconfigure/
│       │   ├── CatalogProperties.java
│       │   ├── CatalogClient.java
│       │   ├── DefaultCatalogClient.java
│       │   └── CatalogAutoConfiguration.java
│       ├── main/resources/META-INF/spring/
│       │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│       └── test/java/com/acme/catalog/autoconfigure/
│           └── CatalogAutoConfigurationTests.java
├── catalog-spring-boot-starter/
│   └── pom.xml
└── catalog-consumer/
    ├── pom.xml
    └── src/test/java/demo/consumer/
        └── CatalogStarterIntegrationTests.java
~~~

Tách autoconfigure và starter giúp phân biệt code cấu hình với dependency bundle. Với thư viện rất nhỏ và không có optional features, có thể gộp hai module; khi có nhiều integration tùy chọn, tách module giúp consumer chỉ chọn đúng phần cần dùng.

### 5.2. Properties class

File CatalogProperties.java:

~~~java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    private boolean enabled = true;

    @NotBlank
    private String endpoint = "https://catalog.example.test";

    @NotNull
    private Duration timeout = Duration.ofSeconds(2);

    @Min(1)
    @Max(10)
    private int maxAttempts = 3;

    public boolean isEnabled() {
        return this.enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getEndpoint() {
        return this.endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return this.timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return this.maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

@ConfigurationProperties gom các property liên quan thành một object có kiểu. @Validated kích hoạt Bean Validation khi properties được bind; @NotBlank, @NotNull, @Min và @Max mô tả các ràng buộc.

### 5.3. Public bean contract

File CatalogClient.java:

~~~java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

public interface CatalogClient {

    String endpoint();

    Duration timeout();

    int maxAttempts();
}
~~~

File DefaultCatalogClient.java:

~~~java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

public record DefaultCatalogClient(
        String endpoint,
        Duration timeout,
        int maxAttempts) implements CatalogClient {
}
~~~

Trong hợp đồng công khai, ứng dụng inject CatalogClient. DefaultCatalogClient là implementation mặc định; nếu không muốn hỗ trợ người dùng phụ thuộc concrete type, hãy ghi rõ đó là implementation detail.

### 5.4. Auto-configuration

File CatalogAutoConfiguration.java:

~~~java
package com.acme.catalog.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "acme.catalog",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    public CatalogClient catalogClient(CatalogProperties properties) {
        return new DefaultCatalogClient(
            properties.getEndpoint(),
            properties.getTimeout(),
            properties.getMaxAttempts()
        );
    }
}
~~~

Condition ở class level quyết định feature có áp dụng hay không. @ConditionalOnMissingBean trên method cho phép ứng dụng cung cấp CatalogClient riêng để thay thế default.

Khai báo return type càng cụ thể càng tốt khi condition phụ thuộc bean type. Với public contract này, CatalogClient là abstraction được hỗ trợ; không cần công bố tên bean nếu người dùng có thể inject theo type.

### 5.5. Đăng ký auto-configuration

File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
~~~

Spring Boot tìm file imports trong JAR đã publish. Mỗi dòng là tên đầy đủ của một auto-configuration class. Auto-configuration nên được đăng ký qua imports file, nằm trong package riêng và không được tìm bằng component scanning. Không bật @ComponentScan trong auto-configuration; dùng @Import cho cấu hình cụ thể khi cần.

## 6. POM và annotation processors

Một module auto-configuration thường cần spring-boot-autoconfigure, validation implementation nếu sử dụng Jakarta constraints, test starter và các annotation processors.

Ví dụ POM cho catalog-spring-boot-autoconfigure:

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
    <artifactId>catalog-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        </path>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Hai processor phục vụ hai mục đích khác nhau:

| Processor | File metadata | Mục đích |
| --- | --- | --- |
| spring-boot-autoconfigure-processor | META-INF/spring-autoconfigure-metadata.properties | Thu thập condition metadata để Spring Boot có thể lọc nhanh auto-configuration không phù hợp |
| spring-boot-configuration-processor | META-INF/spring-configuration-metadata.json | Mô tả property để IDE hỗ trợ completion, type, default và description |

Nếu dùng Maven compiler plugin với annotationProcessorPaths, hãy liệt kê các processor cần chạy ở đó. Với Lombok, cần cấu hình thứ tự annotation processors theo hướng dẫn tương ứng để Lombok chạy trước configuration processor.

### 6.1. Configuration metadata là một phần của trải nghiệm developer

Thêm Javadoc cho từng property. Spring Boot dùng mô tả field để tạo metadata; đối với record, mô tả record component nên được ghi qua Javadoc @param.

Ví dụ:

~~~java
/**
 * Configuration for the Acme catalog client.
 */
@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    /**
     * Whether to enable the Acme catalog integration.
     */
    private boolean enabled = true;

    /**
     * Base URL used by the catalog client.
     */
    @NotBlank
    private String endpoint = "https://catalog.example.test";

    /**
     * Timeout for a catalog request.
     */
    @NotNull
    private Duration timeout = Duration.ofSeconds(2);

    // Remaining fields and accessors...
}
~~~

Description nên mô tả ý nghĩa, không lặp lại tên property hoặc chỉ nói “the value”. Với boolean, bắt đầu bằng “Whether” hoặc “Enable”; với Duration, ghi rõ đơn vị mặc định nếu người dùng có thể nhập giá trị không kèm suffix.

### 6.2. Additional metadata

Khi property không được phát hiện tự động, cần gợi ý giá trị hoặc muốn bổ sung mô tả, có thể thêm:

File src/main/resources/META-INF/additional-spring-configuration-metadata.json:

~~~json
{
  "properties": [
    {
      "name": "acme.catalog.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether to enable the Acme catalog integration.",
      "defaultValue": true
    }
  ],
  "hints": [
    {
      "name": "acme.catalog.mode",
      "values": [
        {
          "value": "sync",
          "description": "Use synchronous request processing."
        },
        {
          "value": "async",
          "description": "Use asynchronous request processing."
        }
      ]
    }
  ]
}
~~~

Processor tự merge file bổ sung vào spring-configuration-metadata.json. File bổ sung là optional; chỉ tạo khi cần metadata mà annotation processor không thể suy ra.

## 7. Kiểm thử auto-configuration bằng ApplicationContextRunner

Runner cho phép kiểm tra từng trường hợp với một context độc lập. Mỗi test nên đại diện cho một tổ hợp property/user beans/classpath có ý nghĩa.

### 7.1. Tạo runner dùng chung

File CatalogAutoConfigurationTests.java:

~~~java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(CatalogAutoConfiguration.class)
            );

    @Test
    void createsDefaultClientWhenEnabledPropertyIsMissing() {
        this.contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CatalogClient.class);

            CatalogClient client = context.getBean(CatalogClient.class);

            assertThat(client).isInstanceOf(DefaultCatalogClient.class);
            assertThat(client.endpoint())
                .isEqualTo("https://catalog.example.test");
            assertThat(client.timeout()).isEqualTo(Duration.ofSeconds(2));
            assertThat(client.maxAttempts()).isEqualTo(3);
        });
    }

    @Test
    void backsOffWhenFeatureIsDisabled() {
        this.contextRunner
            .withPropertyValues("acme.catalog.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(CatalogClient.class);
                assertThat(context).doesNotHaveBean(CatalogProperties.class);
            });
    }

    @Test
    void bindsCustomProperties() {
        this.contextRunner
            .withPropertyValues(
                "acme.catalog.enabled=true",
                "acme.catalog.endpoint=https://catalog.test",
                "acme.catalog.timeout=750ms",
                "acme.catalog.max-attempts=5"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();

                CatalogClient client = context.getBean(CatalogClient.class);

                assertThat(client.endpoint())
                    .isEqualTo("https://catalog.test");
                assertThat(client.timeout()).isEqualTo(Duration.ofMillis(750));
                assertThat(client.maxAttempts()).isEqualTo(5);
            });
    }

    @Test
    void backsOffWhenUserProvidesCatalogClient() {
        this.contextRunner
            .withUserConfiguration(UserCatalogConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CatalogClient.class);

                CatalogClient client = context.getBean(CatalogClient.class);

                assertThat(client.endpoint())
                    .isEqualTo("https://custom.example.test");
            });
    }

    @Test
    void rejectsBlankEndpoint() {
        this.contextRunner
            .withPropertyValues("acme.catalog.endpoint= ")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasStackTraceContaining("must not be blank");
            });
    }

    @Test
    void rejectsMaxAttemptsOutsideSupportedRange() {
        this.contextRunner
            .withPropertyValues("acme.catalog.max-attempts=0")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasStackTraceContaining("must be greater than or equal to 1");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return new DefaultCatalogClient(
                "https://custom.example.test",
                Duration.ofSeconds(1),
                1
            );
        }
    }
}
~~~

### 7.2. Vì sao từng test quan trọng?

- **Default case:** xác nhận behavior khi người dùng chỉ thêm starter, không cần khai báo property.
- **Disabled case:** xác nhận feature thực sự tắt và properties bean không bị tạo ngoài ý muốn.
- **Binding case:** xác nhận relaxed binding, Duration conversion và giá trị được truyền tới bean.
- **Back-off case:** xác nhận ứng dụng có thể thay default implementation.
- **Validation cases:** xác nhận lỗi được phát hiện lúc startup thay vì xuất hiện sau khi client được dùng.

Các test này không gọi HTTP thật. Chúng kiểm tra contract của auto-configuration và object được tạo. Protocol/network behavior thuộc integration test riêng.

### 7.3. Kiểm thử optional dependency bằng FilteredClassLoader

Nếu một integration chỉ hoạt động khi SDK bên thứ ba có mặt, hãy cô lập cấu hình đó:

~~~java
@AutoConfiguration
public class OptionalCatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    static class VendorSdkConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient vendorCatalogClient(CatalogProperties properties) {
            return new VendorCatalogClient(
                new com.vendor.catalog.CatalogSdk(properties.getEndpoint())
            );
        }
    }
}
~~~

Đặt @ConditionalOnClass trên nested configuration giúp cô lập phần code phụ thuộc optional SDK. Không đặt condition chỉ trên @Bean method có return type hoặc signature tham chiếu class có thể vắng mặt, vì JVM có thể cần load class đó trước khi condition method được áp dụng.

Test classpath thiếu SDK:

~~~java
@Test
void optionalIntegrationIsSkippedWhenVendorSdkIsMissing() {
    this.contextRunner
        .withConfiguration(
            AutoConfigurations.of(OptionalCatalogAutoConfiguration.class)
        )
        .withClassLoader(new FilteredClassLoader(CatalogSdk.class))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(VendorCatalogClient.class);
        });
}
~~~

CatalogSdk.class trong test được cung cấp bởi test dependency hoặc test fixture. FilteredClassLoader mô phỏng việc class/package không tồn tại khi ứng dụng thực chạy.

Nếu dùng composed meta-annotation chứa @ConditionalOnClass, cần chú ý cách khai báo name theo hướng dẫn Spring Boot. Với condition trên configuration class, ASM có thể đọc annotation metadata mà không phải load optional class theo cách thông thường.

### 7.4. Kiểm thử web-specific auto-configuration

Nếu thư viện chỉ tạo servlet bean, dùng WebApplicationContextRunner. Nếu chỉ tạo reactive bean, dùng ReactiveWebApplicationContextRunner.

~~~java
private final WebApplicationContextRunner webRunner =
    new WebApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(CatalogWebAutoConfiguration.class)
        );
~~~

Test servlet context:

~~~java
@Test
void createsServletAdapterOnlyInServletContext() {
    this.webRunner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).hasSingleBean(CatalogServletAdapter.class);
    });
}
~~~

Nếu cùng một thư viện hỗ trợ servlet và reactive, viết test riêng cho hai context. Không dùng một non-web ApplicationContextRunner để suy ra behavior của web application.

### 7.5. Hiển thị condition report khi test khó hiểu

Có thể gắn listener để log ConditionEvaluationReport:

~~~java
new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(CatalogAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
    )
    .run(context -> {
        // Assertions for the selected condition branch.
    });
~~~

Condition report giúp xác định condition nào match/no-match. Khi test thất bại, vẫn cần đọc exception chain nếu lỗi xảy ra ở bean creation hoặc configuration binding.

## 8. Ma trận kiểm thử hoàn chỉnh cho Catalog library

Từ các behavior trên, ma trận release có thể được viết như sau:

| ID | Scenario | Input/setup | Expected result | Level |
| --- | --- | --- | --- | --- |
| CAT-001 | Default activation | Không khai báo enabled | Default client có mặt | Runner |
| CAT-002 | Explicit enable | enabled=true | Default client có mặt | Runner |
| CAT-003 | Explicit disable | enabled=false | Không có Catalog beans | Runner |
| CAT-004 | Property binding | Endpoint, timeout, attempts tùy chỉnh | Bean nhận đúng giá trị | Runner |
| CAT-005 | Blank endpoint | Endpoint chỉ có whitespace | Context fail validation | Runner |
| CAT-006 | Attempts too small | max-attempts=0 | Context fail validation | Runner |
| CAT-007 | Attempts too large | max-attempts=11 | Context fail validation | Runner |
| CAT-008 | User override | User đăng ký CatalogClient | Default bean back off | Runner |
| CAT-009 | Optional SDK present | SDK có trên classpath | SDK integration có thể được tạo | Runner |
| CAT-010 | Optional SDK missing | Filter SDK khỏi classpath | Context không fail; integration bị bỏ qua | Runner |
| CAT-011 | Servlet mode | Servlet context | Servlet adapter có mặt | Web runner |
| CAT-012 | Reactive mode | Reactive context | Reactive adapter có mặt | Reactive runner |
| CAT-013 | Non-web mode | Generic context | Không có web adapter | Runner |
| CAT-014 | Custom property source | Property từ Environment/test override | Giá trị ưu tiên đúng | Runner/integration |
| CAT-015 | Configuration ordering | Load cùng auto-config phụ thuộc | Bean definitions được đăng ký đúng thứ tự | Runner |
| CAT-016 | Context close | Đóng context | Disposable resource được đóng | Runner |
| CAT-017 | Imports discovery | Consumer chỉ phụ thuộc JAR | Auto-configuration được tìm thấy | Consumer test |
| CAT-018 | Metadata packaging | Build JAR | Hai metadata files cần thiết có mặt | Packaging |
| CAT-019 | Dependency scopes | Inspect dependency tree | SDK optional không bị kéo vào sai module | Build check |
| CAT-020 | Consumer override | Consumer tự khai báo client | Hành vi override như contract | Consumer test |
| CAT-021 | Supported Boot/JDK | Mỗi tổ hợp đã công bố | Compile và test pass | CI matrix |
| CAT-022 | Runtime failure | Fake transport trả lỗi/timeout | Exception/retry behavior đúng | Integration |
| CAT-023 | Documentation example | Consumer sample dùng đúng README | Build và test pass | Docs verification |
| CAT-024 | Upgrade compatibility | Artifact version trước và mới | Không có thay đổi contract ngoài release note | Compatibility |

### 8.1. P0, P1 và P2

Không phải mọi test đều cần chạy trên mọi pull request.

- **P0 — bắt buộc trước merge:** default activation, enabled/disabled, property binding/validation, user override, optional class missing, imports packaging và consumer smoke test.
- **P1 — chạy trên CI chính hoặc trước release:** web contexts, ordering, resource cleanup, supported Boot/JDK matrix, dependency scope và configuration metadata.
- **P2 — nightly hoặc release qualification:** nhiều phiên bản SDK, network integration, native target, performance/startup và migration test.

Mỗi hàng trong matrix cần có một test ID hoặc đường dẫn test cụ thể. Nếu một scenario được loại bỏ, ghi lý do thay vì để nó biến mất khỏi checklist.

### 8.2. Tránh tổ hợp test bùng nổ

Giả sử có 8 property, 3 profile, 2 web modes và 4 dependency versions. Kiểm mọi tổ hợp có thể tạo ra hàng trăm hoặc hàng nghìn test.

Cách thực tế:

1. Kiểm riêng từng property ở default, boundary và invalid values.
2. Kiểm các condition độc lập bằng test nhỏ.
3. Kiểm một số tổ hợp quan trọng có ảnh hưởng lẫn nhau.
4. Kiểm user override trong mọi nhánh tạo bean quan trọng.
5. Kiểm các dependency optional ở trạng thái có và không có.
6. Chọn boundary version trong compatibility matrix.
7. Dùng consumer integration test cho các luồng end-to-end.

Mục tiêu là kiểm tra rủi ro và giao ước, không phải tạo mọi hoán vị không có ý nghĩa.

## 9. Consumer integration test: kiểm tra đúng artifact người dùng cài

ApplicationContextRunner thường nạp trực tiếp class auto-configuration. Nó không chứng minh file imports đã được đóng gói đúng hoặc dependency graph của starter đã hoàn chỉnh.

Consumer project độc lập trả lời câu hỏi quan trọng hơn: **một ứng dụng chỉ thêm starter dependency có thực sự nhận được hành vi được tài liệu hứa không?**

### 9.1. Consumer POM

Ví dụ consumer phụ thuộc starter đã publish hoặc đã install vào local Maven repository:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>catalog-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Consumer không import trực tiếp CatalogAutoConfiguration và không component scan package thư viện. Spring Boot phải tự tìm auto-configuration qua JAR imports file.

### 9.2. Consumer application properties

File src/test/resources/application.properties:

~~~properties
acme.catalog.enabled=true
acme.catalog.endpoint=https://consumer.example.test
acme.catalog.timeout=1s
acme.catalog.max-attempts=4
~~~

### 9.3. Consumer integration test

File CatalogStarterIntegrationTests.java:

~~~java
package demo.consumer;

import java.time.Duration;

import com.acme.catalog.autoconfigure.CatalogClient;
import com.acme.catalog.autoconfigure.DefaultCatalogClient;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class CatalogStarterIntegrationTests {

    @Autowired
    private CatalogClient catalogClient;

    @Test
    void starterDiscoversAndConfiguresCatalogClient() {
        assertThat(catalogClient)
            .isInstanceOf(DefaultCatalogClient.class);

        assertThat(catalogClient.endpoint())
            .isEqualTo("https://consumer.example.test");

        assertThat(catalogClient.timeout())
            .isEqualTo(Duration.ofSeconds(1));

        assertThat(catalogClient.maxAttempts())
            .isEqualTo(4);
    }
}
~~~

Nếu concrete class không thuộc public contract, consumer test nên assert behavior qua CatalogClient thay vì isInstanceOf(DefaultCatalogClient.class). Trong ví dụ này assertion concrete type chỉ minh họa default implementation; release test ổn định hơn khi chỉ phụ thuộc interface.

### 9.4. Chạy consumer sau khi đóng gói thư viện

Nếu consumer nằm trong cùng Maven reactor, build module và dependency liên quan theo reactor. Nếu consumer là project độc lập, cài/publish library trước rồi chạy consumer:

~~~bash
mvn -f catalog-spring-boot-autoconfigure/pom.xml clean install
mvn -f catalog-spring-boot-starter/pom.xml clean install
mvn -f catalog-consumer/pom.xml clean verify
~~~

Đây là kiểm thử có giá trị cao trước release vì nó xác nhận dependency coordinates, transitive dependencies và auto-configuration discovery từ artifact đã đóng gói.

## 10. Kiểm tra nội dung JAR và metadata

Một test trong module có thể pass trong khi JAR phát hành thiếu imports file. Hãy kiểm tra chính artifact.

Build:

~~~bash
mvn clean verify
~~~

Liệt kê nội dung JAR:

~~~bash
jar tf target/catalog-spring-boot-autoconfigure-1.0.0.jar
~~~

Các file quan trọng cần tìm:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring-configuration-metadata.json
~~~

- Imports file phải liệt kê đúng configuration classes.
- Auto-configuration metadata có thể được tạo bởi spring-boot-autoconfigure-processor.
- Configuration metadata phải mô tả property, type, default và description cần thiết.

Nếu processor không được cấu hình, một hoặc nhiều metadata files có thể không được sinh. Hãy xem đây là lỗi build configuration nếu thư viện công bố cung cấp IDE metadata hoặc cần condition metadata.

### 10.1. Kiểm tra dependency graph

Chạy:

~~~bash
mvn dependency:tree
~~~

Đọc kết quả để xác nhận:

- spring-boot-autoconfigure có version được quản lý tương thích.
- SDK optional không bị starter kéo vào nếu feature đó thực sự tùy chọn.
- Validation provider có mặt khi contract dựa vào Bean Validation.
- Không kéo theo hai version không tương thích của cùng một thư viện.
- Test-only dependency không xuất hiện ở runtime graph của consumer.

autoconfigure module nên đánh dấu dependency thư viện nền tảng là optional khi phù hợp để consumer có thể tự chọn dependency set. Starter module sẽ cung cấp bộ dependency mặc định có chủ đích. Không đưa mọi integration optional vào một starter duy nhất nếu điều đó khiến consumer phải kéo theo những thư viện họ không sử dụng.

## 11. Viết tài liệu giao ước cho người dùng thư viện

README nên giúp một developer mới có thể thêm dependency, bật/tắt feature, cấu hình và thay default bean mà không cần đọc source code.

### 11.1. README outline đề xuất

~~~markdown
# Acme Catalog Spring Boot Starter

## What it provides
- CatalogClient auto-configuration
- Default request timeout and retry settings
- Optional vendor transport integration

## Requirements
- Spring Boot: supported versions
- Java: supported versions
- Optional SDK: version range

## Installation
Maven and Gradle coordinates.

## Quick start
A minimal application.properties example and injection example.

## Auto-configuration behavior
- Activation conditions
- Default enabled/disabled behavior
- Optional classpath conditions
- User-defined bean back-off behavior

## Configuration properties
A complete property table with type, default, validation and description.

## Beans and customization
- Public bean types
- Custom implementation example
- Customizer/callback extension points
- Ordering and qualifier notes

## Startup and runtime behavior
- What is initialized at startup
- When network calls happen
- Timeout and retry behavior
- Resource cleanup

## Failure behavior
- Invalid configuration
- Missing optional dependency
- Remote service unavailable
- Actionable troubleshooting

## Compatibility
Spring Boot, Java, SDK and platform support matrix.

## Migration
Deprecated properties and behavior changes by version.

## Testing
How to run unit, auto-configuration and consumer tests.

## License and support
Support channels and issue reporting.
~~~

### 11.2. Bảng property phải đủ thông tin

Ví dụ phần README:

| Property | Type | Default | Validation | Behavior |
| --- | --- | --- | --- | --- |
| acme.catalog.enabled | boolean | true | Boolean | Tắt toàn bộ Catalog auto-configuration khi false |
| acme.catalog.endpoint | String | https://catalog.example.test | Không được blank | Base endpoint của client |
| acme.catalog.timeout | Duration | 2s | Không null, phải dương theo contract | Request timeout |
| acme.catalog.max-attempts | int | 3 | Từ 1 đến 10 | Tổng số lần thử theo định nghĩa của thư viện |

Không chỉ ghi “timeout in milliseconds” nếu binder chấp nhận duration suffix. Ghi rõ 750ms, 2s, 1m có ý nghĩa ra sao và default unit khi người dùng không chỉ định suffix.

Nếu một property chỉ có hiệu lực khi optional module được cài, hãy ghi rõ điều đó trong cột Behavior hoặc một ghi chú riêng.

### 11.3. Công bố activation conditions

Ví dụ:

~~~markdown
Catalog auto-configuration is activated when:

1. acme.catalog.enabled is absent or true.
2. The Catalog auto-configuration module is present.
3. Any optional integration requiring a vendor SDK is activated only when that SDK is present.

The default CatalogClient backs off when the application provides its own
CatalogClient bean.
~~~

Hãy mô tả chính xác matchIfMissing, class conditions và bean back-off. Tránh dùng câu mơ hồ như “auto-configures automatically” mà không nói điều kiện.

### 11.4. Công bố bean và extension points

Ví dụ:

| Bean type | Khi nào được tạo | Cách override |
| --- | --- | --- |
| CatalogClient | Feature enabled và chưa có user bean | Cung cấp @Bean CatalogClient |
| CatalogProperties | Auto-configuration được kích hoạt | Cấu hình qua property sources |
| CatalogMetricsBinder | Metrics dependency có mặt và bean chưa được thay thế | Cung cấp implementation riêng nếu API hỗ trợ |

Với mỗi bean công khai, ghi type, lifecycle, dependency, qualifiers và cách thay thế nếu đó là phần thư viện cam kết.

### 11.5. Công bố failure behavior

Người dùng cần biết lỗi xảy ra ở đâu:

| Tình huống | Behavior được cam kết | Hành động |
| --- | --- | --- |
| Endpoint blank | Startup fail do validation | Cung cấp endpoint hợp lệ |
| Timeout không hợp lệ | Startup fail do validation | Dùng duration dương |
| Optional SDK thiếu | Optional integration không được tạo | Thêm SDK nếu cần feature đó |
| User cung cấp CatalogClient | Default client back off | Kiểm bean type và qualifier |
| Remote service không phản hồi | Client báo lỗi theo timeout/retry contract | Kiểm endpoint, credentials và network |

Nếu service kết nối mạng ngay trong startup, ghi rõ startup timeout và failure policy. Nếu connection chỉ được tạo khi request đầu tiên, nói rõ điều đó để người vận hành hiểu thời điểm lỗi có thể xuất hiện.

## 12. Compatibility matrix và quy tắc versioning

Không công bố “supports Spring Boot 3+” nếu CI chỉ chạy một version. Ghi version range đã được kiểm thử.

Ví dụ support matrix:

| Thành phần | Supported range (ví dụ) | Bằng chứng cần lưu |
| --- | --- | --- |
| Spring Boot | 3.3.x | CI build/test ở minimum và latest patch |
| Java | 17, 21 | JDK matrix |
| Catalog vendor SDK | 2.4.x | Dependency matrix và integration tests |
| Maven | 3.8+ | Maven wrapper hoặc CI image |
| Servlet container | Chỉ nếu có web adapter | Web-context integration test |
| GraalVM Native Image | Chỉ khi được công bố | Native build/run trên target đã nêu |

Đây là ví dụ cách trình bày. Thư viện phải thay range bằng những tổ hợp thực sự hỗ trợ.

### 12.1. Phân biệt source compatibility, binary compatibility và behavior compatibility

- **Source compatibility:** consumer source code vẫn compile.
- **Binary compatibility:** artifact mới vẫn tương thích với bytecode consumer đã compile trước đó.
- **Behavior compatibility:** cùng property và dependency set vẫn tạo cùng bean, default và side effect.

Một thay đổi có thể giữ compile thành công nhưng vẫn phá behavior, ví dụ thay default enabled, thay condition hoặc đổi bean back-off. Vì thế compatibility review phải bao gồm cả test hành vi.

### 12.2. Những thay đổi cần đánh giá như breaking changes

- Xóa hoặc đổi tên property.
- Đổi kiểu dữ liệu hoặc đơn vị của property.
- Thay default làm feature bật/tắt khác trước.
- Thay bean type hoặc bỏ extension point.
- Đổi @ConditionalOnMissingBean khiến user override không còn hoạt động.
- Đổi transitive dependencies hoặc loại bỏ module mà starter từng cung cấp.
- Thay exception/failure timing theo cách consumer dựa vào.
- Thu hẹp dải Spring Boot/JDK/SDK hỗ trợ.

### 12.3. Deprecation và migration

Khi đổi property, hãy:

1. Công bố key mới và key cũ.
2. Đánh dấu key cũ deprecated trong configuration metadata/Javadoc.
3. Ghi version bắt đầu deprecated.
4. Mô tả precedence nếu cả hai key cùng được cấu hình.
5. Giữ compatibility trong khoảng thời gian đã công bố.
6. Thêm test cho key cũ, key mới và cả hai cùng có mặt.
7. Viết migration guide trước khi xóa key cũ.

Không xóa property chỉ vì code đã chuyển sang tên mới. Người dùng có thể còn nhiều deployment config chưa được cập nhật.

## 13. Tổ chức CI theo vòng đời phát triển

Một pipeline hợp lý có thể chia thành bốn nhóm.

### 13.1. Pull request

Chạy nhanh để ngăn regression phổ biến:

- Compile và static checks.
- Unit tests.
- ApplicationContextRunner matrix P0.
- Optional classpath tests.
- Metadata generation.
- JAR imports verification.
- Consumer smoke test với dependency trong reactor.

### 13.2. Main branch

Mở rộng phạm vi:

- Supported Java versions.
- Supported Spring Boot patch versions.
- SDK minimum/current versions.
- Servlet/reactive contexts nếu có.
- Dependency tree checks.
- Consumer integration tests.

### 13.3. Nightly

Chạy các kiểm tra tốn thời gian:

- Full dependency compatibility combinations.
- Container-backed integration tests.
- Network failure, retry, timeout và recovery.
- Native Image tests nếu thư viện công bố hỗ trợ.
- Startup/performance regression nếu đó là yêu cầu sản phẩm.

### 13.4. Release candidate

Dùng đúng artifact candidate:

1. Build JAR/starter.
2. Cài hoặc publish vào staging repository.
3. Tạo consumer project chỉ phụ thuộc coordinates của candidate.
4. Chạy quick start và integration tests.
5. Kiểm JAR contents, generated metadata và dependency tree.
6. Kiểm README examples và migration guide.
7. Lưu test reports, dependency versions và checksum.
8. Chỉ phát hành khi support matrix và release notes khớp bằng chứng CI.

Không dùng consumer project tham chiếu source classes trong reactor làm bằng chứng duy nhất cho packaging. Một consumer dùng artifact đã đóng gói có thể phát hiện imports file hoặc dependency bị thiếu.

## 14. Tài liệu ví dụ cũng cần được kiểm thử

Một README có code không compile sẽ khiến consumer mất thời gian dù thư viện đúng.

Các cách giữ docs đồng bộ:

- Đặt sample application trong thư mục samples/ hoặc module catalog-consumer.
- Dùng chính sample đó trong CI.
- Copy property examples vào test fixtures nếu chúng đại diện cho default contract.
- Kiểm version coordinates trong docs khớp release candidate.
- Mỗi property trong bảng tài liệu có ít nhất một test cho default hoặc behavior quan trọng.
- Mỗi extension point có một test override.
- Mỗi optional feature có test classpath present/missing.
- Migration guide có test cho old/new property nếu thay đổi behavior.

Một ví dụ tối thiểu trong README nên được kiểm thử như một consumer thật: thêm starter, khai báo properties, inject interface và chạy application context.

## 15. Những lỗi thường gặp khi hoàn thiện thư viện

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ test service logic | Condition và back-off có thể sai mà test vẫn pass | Thêm ApplicationContextRunner matrix |
| Chỉ test class trực tiếp | Không kiểm tra imports file trong JAR | Thêm consumer project dùng artifact |
| Không test property missing | Default behavior không được bảo vệ | Test property vắng mặt riêng |
| Chỉ test enabled=true | Feature có thể không tắt được | Test false và default |
| Không test user bean override | Starter có thể chiếm bean của ứng dụng | Test @ConditionalOnMissingBean |
| Không test optional class missing | Consumer không dùng integration vẫn có thể fail startup | Dùng FilteredClassLoader |
| Chỉ test non-web context | Servlet/reactive condition có thể sai | Dùng đúng web context runner |
| Chỉ assert bean exists | Bean có thể nhận sai property/default | Assert giá trị và behavior |
| Không kiểm metadata | IDE không gợi ý hoặc hiển thị property sai | Kiểm generated JSON trong JAR |
| Không kiểm dependency tree | Starter kéo dependency không cần thiết hoặc sai version | Chạy mvn dependency:tree |
| README không có property table | Consumer phải đọc source để biết cấu hình | Công bố type/default/validation/activation |
| Không ghi bean override contract | Người dùng không biết cách thay implementation | Tài liệu interface và back-off behavior |
| Không công bố support matrix | Người dùng suy diễn support range quá rộng | Ghi version và CI evidence |
| Đổi default mà không migration note | Nâng version có thể đổi behavior production | Treat default changes as contract changes |
| Dùng @ComponentScan trong auto-configuration | Có thể quét nhầm package ứng dụng | Đăng ký imports và dùng @Import cụ thể |
| Condition trên method signature chứa optional class | JVM có thể load type trước khi condition method được xét | Cô lập optional integration trong nested configuration |
| Chạy ApplicationContextRunner trong native test | Runner không hỗ trợ native image | Chạy runner trên JVM; dùng native integration test riêng |
| Chỉ kiểm thử source module | JAR publish có thể thiếu metadata/resources | Package verification và consumer smoke test |

## 16. Checklist release readiness

### Auto-configuration behavior

- [ ] Có activation conditions được mô tả rõ.
- [ ] Property missing/default, true và false đã được test.
- [ ] Property invalid và boundary values đã được test.
- [ ] Default beans có @ConditionalOnMissingBean phù hợp.
- [ ] User-defined beans được test.
- [ ] Optional dependencies có classpath-present và classpath-missing tests.
- [ ] Web contexts được test nếu có web-specific beans.
- [ ] Auto-configuration ordering có test khi ordering là một phần behavior.

### Configuration metadata

- [ ] Property prefix thuộc namespace riêng của thư viện.
- [ ] Field Javadoc mô tả từng property.
- [ ] Type/default/validation khớp README.
- [ ] spring-configuration-metadata.json được tạo.
- [ ] Additional metadata chỉ được thêm khi cần.
- [ ] Deprecated property có replacement và migration note.

### Packaging và dependencies

- [ ] AutoConfiguration.imports nằm trong JAR.
- [ ] spring-autoconfigure-metadata.properties được tạo nếu processor được cấu hình.
- [ ] Optional dependency có scope/optional flag đúng.
- [ ] Starter chứa bộ dependency mặc định có chủ đích.
- [ ] dependency:tree không có xung đột không mong muốn.
- [ ] Consumer test dùng artifact đã đóng gói.

### Documentation và compatibility

- [ ] README có quick start chạy được.
- [ ] Bảng property có type/default/validation/behavior.
- [ ] Bean types và override points được mô tả.
- [ ] Failure behavior và troubleshooting được ghi rõ.
- [ ] Spring Boot/JDK/SDK support matrix phản ánh CI.
- [ ] Breaking changes và deprecations có migration guide.
- [ ] Release notes phản ánh thay đổi behavior.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao unit test cho DefaultCatalogClient chưa đủ để hoàn thiện starter?  
**Đáp án:** Nó không kiểm tra auto-configuration conditions, property binding, user bean back-off, classpath, imports discovery hoặc dependency graph của consumer.

**Câu 2.** ApplicationContextRunner phù hợp nhất với loại test nào?  
**Đáp án:** Test các tổ hợp Environment, user configuration, classpath và conditions trong một context cô lập, nhanh.

**Câu 3.** Khi nào dùng FilteredClassLoader?  
**Đáp án:** Khi cần mô phỏng một class hoặc package không có trên runtime classpath, đặc biệt với dependency optional.

**Câu 4.** Vì sao consumer integration test phải phụ thuộc JAR đã đóng gói?  
**Đáp án:** Để xác nhận auto-configuration imports, resources, metadata và transitive dependencies có trong artifact thực sự được người dùng cài.

**Câu 5.** spring-boot-autoconfigure-processor và spring-boot-configuration-processor tạo metadata gì?  
**Đáp án:** Processor đầu thu thập condition metadata; processor sau tạo configuration metadata cho property và IDE assistance.

**Câu 6.** Vì sao cần test khi enabled không được khai báo?  
**Đáp án:** Vì matchIfMissing và default behavior là một phần contract; chỉ test true/false không chứng minh default hoạt động đúng.

**Câu 7.** Nếu user cung cấp CatalogClient, default bean nên được xử lý thế nào?  
**Đáp án:** Nếu contract cho phép override, @ConditionalOnMissingBean(CatalogClient.class) phải làm default bean back off.

**Câu 8.** Có cần test mọi tổ hợp property, profile, SDK và JDK không?  
**Đáp án:** Không. Hãy dùng test từng chiều, boundary cases, các tổ hợp có rủi ro và compatibility matrix có chủ đích.

**Câu 9.** Thay default timeout từ 2 giây thành 10 giây có thể là breaking change không?  
**Đáp án:** Có thể. Nó thay behavior và latency contract của consumer dù source code vẫn compile.

**Câu 10.** Vì sao README sample nên được chạy trong CI?  
**Đáp án:** Để bảo đảm dependency coordinates, property names, bean injection và ví dụ vẫn hoạt động như tài liệu công bố.

**Câu 11.** Khi nào dùng WebApplicationContextRunner?  
**Đáp án:** Khi auto-configuration phụ thuộc Servlet web context. Với Reactive context, dùng ReactiveWebApplicationContextRunner.

**Câu 12.** Khi nào có thể công bố một version range được hỗ trợ?  
**Đáp án:** Khi các version đại diện trong range đã được build/test theo compatibility matrix và các giới hạn chưa kiểm thử được ghi rõ.

## 18. Ghi nhớ và tài liệu tham khảo

- Giao ước auto-configuration gồm activation conditions, defaults, properties, beans, override behavior, dependencies, failure behavior và support matrix.
- Dùng ApplicationContextRunner để kiểm tra từng tổ hợp Environment/user beans/classpath; dùng FilteredClassLoader để mô phỏng dependency optional bị thiếu.
- Dùng WebApplicationContextRunner hoặc ReactiveWebApplicationContextRunner khi behavior phụ thuộc web context.
- Consumer integration tests phải dùng artifact đã đóng gói để xác nhận imports discovery và dependency graph.
- Kiểm tra AutoConfiguration.imports, spring-autoconfigure-metadata.properties và spring-configuration-metadata.json trong JAR.
- Dùng Javadoc của @ConfigurationProperties và configuration metadata để cải thiện IDE completion.
- README cần property table, bean override contract, failure behavior, compatibility và migration guide.
- CI nên có P0 cho pull request, compatibility tests cho main/release và integration matrix rộng hơn cho nightly.
- Thay default, property, bean type hoặc activation conditions có thể là behavior-breaking change dù source code vẫn compile.

Tài liệu chính thức Spring Boot 3.3.13:

1. [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — imports file, condition annotations, ApplicationContextRunner, FilteredClassLoader, starter modules, naming và configuration key guidelines.
2. [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html) — property sources, precedence, binding và configuration properties.
3. [Configuration Metadata: Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html) — sinh metadata từ @ConfigurationProperties và additional metadata.
4. [Configuration Metadata Format](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html) — groups, properties, hints và ignored items.
5. [ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html) — runner cho auto-configuration tests.
6. [FilteredClassLoader Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html) — mô phỏng classpath thiếu class/package.
7. [WebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html) — kiểm thử Servlet web context.
8. [ReactiveWebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html) — kiểm thử Reactive web context.
9. [Spring Boot Auto-configuration Processor](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.custom-starter.autoconfigure-module) — condition metadata và cấu hình annotation processor.
