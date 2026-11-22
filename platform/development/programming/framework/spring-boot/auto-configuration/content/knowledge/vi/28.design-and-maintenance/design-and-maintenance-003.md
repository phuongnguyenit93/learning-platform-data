# Giao ước không có dependency thì không gây lỗi ngoài phạm vi tính năng

## 1. Mục tiêu: thiếu thư viện tùy chọn chỉ tắt đúng integration đó

Một thư viện Spring Boot thường hỗ trợ nhiều tính năng. Phần cốt lõi có thể hoạt động độc lập, trong khi một số integration cần thêm thư viện bên ngoài, chẳng hạn Jackson, Kafka, Redis hoặc SDK của nhà cung cấp.

Một starter tốt phải giữ được giao ước:

- Nếu thư viện tùy chọn **không có trên classpath**, ứng dụng vẫn khởi động và các tính năng cốt lõi vẫn dùng được.
- Bean thuộc integration tùy chọn không được đăng ký khi dependency cần thiết vắng mặt.
- Class tham chiếu API tùy chọn không bị JVM buộc phải load khi integration chưa được bật.
- Nếu thư viện đã có nhưng bean hạ tầng mà integration cần chưa được cung cấp, integration không được làm hỏng những phần không liên quan.
- Khi người dùng chủ động bật tính năng và dependency cần thiết có mặt, integration được cấu hình bình thường.
- Người dùng có thể thay bean mặc định bằng implementation của họ.

Ví dụ: một thư viện audit có API ghi sự kiện cốt lõi. Tính năng mã hóa sự kiện thành JSON cần Jackson. Nếu ứng dụng không dùng JSON, việc không có Jackson không được khiến AuditService hoặc các bean audit cơ bản thất bại.

Bài viết sử dụng **Spring Boot 3.5.16, Spring Framework 6.2 và Java 17+**. Ví dụ chính dùng các condition của Spring Boot, nested configuration và ApplicationContextRunner.

## 2. Phân biệt ba trạng thái: class có mặt, bean có mặt và tính năng được bật

Một optional integration thường cần nhiều điều kiện độc lập:

| Điều kiện | Câu hỏi | Annotation thường dùng |
| --- | --- | --- |
| Classpath | Thư viện cần thiết có thật sự được đóng gói không? | @ConditionalOnClass, @ConditionalOnMissingClass |
| ApplicationContext | Bean hạ tầng cần dùng đã được cung cấp chưa? | @ConditionalOnBean, @ConditionalOnMissingBean |
| Cấu hình người dùng | Người dùng có chủ động bật tính năng không? | @ConditionalOnProperty |

Ví dụ với tính năng JSON:

- ObjectMapper phải có mặt trên classpath.
- Một bean ObjectMapper phải có trong context, có thể do Spring Boot hoặc ứng dụng cung cấp.
- Property acme.audit.json.enabled phải được đặt thành true.
- Nếu ứng dụng đã tự cung cấp AuditJsonCodec, auto-configuration không tạo codec mặc định thứ hai.

Có thể hình dung luồng quyết định:

~~~text
AuditAutoConfiguration được phát hiện
                 |
                 v
AuditService cốt lõi được đăng ký
                 |
                 v
Jackson class có trên classpath?
          /              \
        Không             Có
         |                |
  Bỏ qua JSON config     ObjectMapper bean có?
                          /          \
                        Không        Có
                         |            |
                 Bỏ qua JSON config  Property enabled?
                                      /          \
                                    Không        Có
                                     |            |
                              Bỏ qua JSON config  Tạo JSON codec
~~~

Các điều kiện này trả lời những câu hỏi khác nhau. Chỉ kiểm tra classpath không chứng minh rằng bean hạ tầng đã được cấu hình. Chỉ kiểm tra property cũng không làm cho một class còn thiếu xuất hiện trên classpath.

## 3. Vì sao thiếu optional dependency có thể gây NoClassDefFoundError?

Giả sử một thư viện có auto-configuration:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnClass(ObjectMapper.class)
    AuditJsonCodec auditJsonCodec(ObjectMapper objectMapper) {
        return new JacksonAuditJsonCodec(objectMapper);
    }
}
~~~

Ý định là chỉ tạo AuditJsonCodec khi Jackson có mặt. Tuy nhiên, method signature của @Bean đã tham chiếu trực tiếp đến ObjectMapper.

JVM có thể cần load và xử lý kiểu trong method signature trước khi condition của method được đánh giá. Khi Jackson không có trên classpath, lỗi linkage có thể xảy ra trước lúc Spring kịp bỏ qua method.

Thông báo có thể là:

~~~text
java.lang.NoClassDefFoundError:
com/fasterxml/jackson/databind/ObjectMapper
~~~

Đây là lý do @ConditionalOnClass trên một @Bean method không phải lúc nào cũng đủ để cô lập optional type.

Spring Boot khuyến nghị đặt các method tham chiếu optional type trong một configuration class riêng, có @ConditionalOnClass ở cấp class. Spring đọc metadata của configuration để đánh giá condition trước khi load cấu hình tùy chọn đó.

### 3.1. Cấu trúc an toàn: nested static configuration

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    // Các bean cốt lõi không tham chiếu Jackson.

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name =
            "com.fasterxml.jackson.databind.ObjectMapper")
    static class JacksonConfiguration {

        @Bean
        AuditJsonCodec auditJsonCodec(ObjectMapper objectMapper) {
            return new JacksonAuditJsonCodec(objectMapper);
        }
    }
}
~~~

Điểm quan trọng:

- AuditAutoConfiguration không có field, constructor hay method signature tham chiếu ObjectMapper.
- JacksonConfiguration được cô lập thành nested static configuration.
- @ConditionalOnClass đặt trên configuration class để Spring đánh giá sự hiện diện của thư viện trước khi xử lý các method phụ thuộc nó.
- Nếu Jackson vắng mặt, phần JSON configuration không được kích hoạt; các bean cốt lõi vẫn có thể được tạo.

Có thể dùng @ConditionalOnClass(ObjectMapper.class) trực tiếp trên configuration class vì Spring Boot đọc annotation metadata bằng ASM trước khi load class. Thuộc tính name dạng chuỗi cũng phù hợp và hữu ích khi muốn tránh tham chiếu class tùy chọn ngay trong source của lớp ngoài.

**Không chuyển optional type trở lại lớp ngoài** qua return type, tham số method, field, superclass, interface hoặc static initializer. Làm như vậy sẽ phá vỡ ranh giới class-loading mà nested configuration đang tạo ra.

## 4. Dùng điều kiện đúng với từng loại dependency

### 4.1. @ConditionalOnClass: thư viện có trên classpath

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "com.fasterxml.jackson.databind.ObjectMapper")
static class JacksonConfiguration {
}
~~~

Dùng khi tính năng phụ thuộc vào một class hoặc thư viện cụ thể.

@ConditionalOnClass chỉ xác nhận class được yêu cầu có thể được tìm thấy. Nó không xác nhận:

- Một bean tương ứng đã được tạo.
- Phiên bản thư viện tương thích với API mà code sử dụng.
- Property của tính năng đã được bật.
- Dịch vụ ngoài đã kết nối thành công.

Nếu cần class không xuất hiện, có thể dùng @ConditionalOnMissingClass.

### 4.2. @ConditionalOnBean: bean hạ tầng đã được cung cấp

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(type =
        "com.fasterxml.jackson.databind.ObjectMapper")
static class JacksonConfiguration {
}
~~~

Dùng khi integration cần một collaborator do Spring quản lý, ví dụ ObjectMapper, RedisConnectionFactory, KafkaTemplate, DataSource hoặc một SDK client.

Class có trên classpath không có nghĩa bean đã có trong context. Ví dụ ứng dụng thêm jackson-databind nhưng không cấu hình ObjectMapper; integration cần mapper không nên giả định bean đó tồn tại.

Khi condition không match, Spring bỏ qua configuration tùy chọn. Phần cốt lõi không cần phụ thuộc vào bean đó.

### 4.3. @ConditionalOnProperty: người dùng chủ động bật tính năng

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.audit.json",
        name = "enabled",
        havingValue = "true")
static class JacksonConfiguration {
}
~~~

Property:

~~~properties
acme.audit.json.enabled=true
~~~

Khi không khai báo property, condition trên không match vì matchIfMissing mặc định là false.

Cách opt-in rõ ràng phù hợp với integration làm tăng dependency, tiêu thụ tài nguyên hoặc mở rộng hành vi ứng dụng. Người dùng có thể thêm thư viện mà vẫn giữ tính năng tắt cho đến khi chủ động bật.

### 4.4. @ConditionalOnMissingBean: cho phép ứng dụng thay implementation mặc định

~~~java
@Bean
@ConditionalOnMissingBean(AuditJsonCodec.class)
AuditJsonCodec auditJsonCodec(ObjectMapper objectMapper) {
    return new JacksonAuditJsonCodec(objectMapper);
}
~~~

Nếu ứng dụng cung cấp AuditJsonCodec riêng, auto-configuration không đăng ký codec mặc định.

Đây là một phần của hợp đồng mở rộng starter. Không ép người dùng phải dùng implementation của thư viện nếu họ đã có cách triển khai phù hợp.

### 4.5. Kết hợp điều kiện

Một optional integration có thể cần đồng thời class, bean và property:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "com.fasterxml.jackson.databind.ObjectMapper")
@ConditionalOnBean(type =
        "com.fasterxml.jackson.databind.ObjectMapper")
@ConditionalOnProperty(
        prefix = "acme.audit.json",
        name = "enabled",
        havingValue = "true")
static class JacksonConfiguration {
}
~~~

Chỉ khi cả ba điều kiện phù hợp, cấu hình JSON mới được xử lý.

Không thêm condition chỉ để làm code có vẻ an toàn. Mỗi condition nên tương ứng với một yêu cầu thực sự của integration và có test cho cả trường hợp match lẫn không match.

## 5. Đừng để optional type rò vào API cốt lõi

Giả sử AuditService chỉ ghi nhận sự kiện. Nếu class này có constructor nhận ObjectMapper, thì toàn bộ chức năng audit đã bị phụ thuộc vào Jackson:

~~~java
public class AuditService {

    private final ObjectMapper objectMapper;

    public AuditService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }
}
~~~

Ngay cả khi người dùng không dùng JSON, Spring vẫn phải giải quyết dependency ObjectMapper để tạo AuditService.

Thiết kế tốt hơn là tách API cốt lõi và adapter tùy chọn:

~~~java
public record AuditEvent(String action, String actor) {
}
~~~

~~~java
public class AuditService {

    public AuditEvent createEvent(String action, String actor) {
        return new AuditEvent(action, actor);
    }
}
~~~

~~~java
public interface AuditJsonCodec {

    String encode(AuditEvent event);
}
~~~

AuditService và AuditEvent không biết Jackson tồn tại. Chỉ implementation JacksonAuditJsonCodec trong nested configuration mới tham chiếu ObjectMapper.

Lợi ích:

- API cốt lõi không bị khóa vào một JSON library.
- Người dùng có thể dùng serializer khác hoặc không serialize.
- Optional dependency có thể vắng mặt mà không ảnh hưởng bean cốt lõi.
- Test core không phải tạo mapper hoặc kéo thư viện JSON vào context.
- Integration có thể thay thế bằng implementation riêng qua @ConditionalOnMissingBean.

Nếu cần kết nối API cốt lõi với một khả năng tùy chọn, dùng interface thuộc module cốt lõi hoặc một provider có thể vắng mặt. Tránh đưa class của thư viện ngoài vào chữ ký public của API cốt lõi.

## 6. Quản lý dependency trong Maven, Gradle và starter modules

Điều kiện runtime chỉ có ý nghĩa khi dependency được khai báo đúng trong artifact.

### 6.1. Maven optional dependency

Trong module auto-configuration:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
~~~

optional=true có nghĩa dependency vẫn có sẵn khi build và test module này, nhưng không tự được truyền thành dependency bắc cầu cho project tiêu thụ module.

Vì vậy:

- Module auto-configuration có thể compile phần Jackson integration.
- Consumer không tự nhận Jackson chỉ vì thêm module auto-configuration.
- Nếu consumer muốn dùng JSON integration, họ phải thêm Jackson hoặc một starter chuyên biệt đưa Jackson vào classpath.

**Optional dependency và @ConditionalOnClass giải quyết hai vấn đề khác nhau.** Maven optional kiểm soát dependency propagation; Spring condition kiểm soát cấu hình runtime. Một mình optional=true không ngăn NoClassDefFoundError nếu code vẫn tham chiếu optional type ở lớp được load vô điều kiện.

### 6.2. Gradle compileOnly

Với Gradle, một thư viện tùy chọn có thể được khai báo:

~~~kotlin
dependencies {
    compileOnly("com.fasterxml.jackson.core:jackson-databind")

    testImplementation("com.fasterxml.jackson.core:jackson-databind")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

compileOnly cho phép module biên dịch với API Jackson mà không tự đưa dependency đó vào runtime classpath của consumer. Test vẫn cần dependency để chạy nhánh integration có Jackson.

Consumer muốn bật tính năng phải tự khai báo runtime dependency hoặc dùng starter chuyên biệt.

### 6.3. Tách starter theo tính năng tùy chọn

Khi thư viện có nhiều integration, có thể tổ chức module như sau:

~~~text
acme-audit/
├── acme-audit-core
├── acme-audit-spring-boot-autoconfigure
├── acme-audit-spring-boot-starter
├── acme-audit-spring-boot-starter-json
└── acme-audit-spring-boot-starter-kafka
~~~

| Module | Dependency và trách nhiệm |
| --- | --- |
| acme-audit-core | API sự kiện và logic cốt lõi |
| acme-audit-spring-boot-autoconfigure | Auto-configuration, properties và optional integration |
| acme-audit-spring-boot-starter | Các dependency cần thiết cho chức năng audit cơ bản |
| acme-audit-spring-boot-starter-json | Starter cơ bản cùng Jackson và cấu hình JSON cần thiết |
| acme-audit-spring-boot-starter-kafka | Starter cơ bản cùng Kafka integration |

Cách chia này giúp consumer chọn đúng tính năng cần dùng. Không bắt mọi ứng dụng cài Kafka, Redis hoặc Jackson chỉ vì muốn sử dụng một API cốt lõi.

Với một thư viện nhỏ chỉ có một tính năng, không cần tách nhiều module. Chỉ tạo starter riêng khi nó làm dependency contract rõ hơn.

## 7. Ví dụ hoàn chỉnh: audit core hoạt động khi Jackson vắng mặt

Ví dụ này chứng minh các trạng thái sau:

1. AuditService luôn có thể được tạo.
2. JSON codec chỉ xuất hiện khi Jackson có trên classpath, có ObjectMapper bean và property được bật.
3. Ứng dụng có thể thay codec mặc định.
4. Thiếu Jackson không làm context cốt lõi thất bại.

### 7.1. Cấu trúc dự án

~~~text
audit-optional-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/audit/
    │   │   ├── AuditEvent.java
    │   │   ├── AuditService.java
    │   │   ├── AuditJsonCodec.java
    │   │   └── autoconfigure/
    │   │       └── AuditAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/audit/
            └── AuditAutoConfigurationTests.java
~~~

### 7.2. Maven dependencies

File pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>audit-optional-demo</artifactId>
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
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Dependency Jackson được đánh dấu optional. Module này vẫn compile được JSON integration và test nhánh có Jackson, trong khi consumer không tự nhận dependency đó.

### 7.3. API cốt lõi không phụ thuộc Jackson

File AuditEvent.java:

~~~java
package com.example.audit;

public record AuditEvent(String action, String actor) {
}
~~~

File AuditService.java:

~~~java
package com.example.audit;

public class AuditService {

    public AuditEvent createEvent(String action, String actor) {
        return new AuditEvent(action, actor);
    }
}
~~~

File AuditJsonCodec.java:

~~~java
package com.example.audit;

public interface AuditJsonCodec {

    String encode(AuditEvent event);
}
~~~

Ba type này không import bất kỳ class nào của Jackson.

### 7.4. Auto-configuration tách riêng phần JSON

File autoconfigure/AuditAutoConfiguration.java:

~~~java
package com.example.audit.autoconfigure;

import com.example.audit.AuditJsonCodec;
import com.example.audit.AuditService;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration")
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AuditService auditService() {
        return new AuditService();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name =
            "com.fasterxml.jackson.databind.ObjectMapper")
    @ConditionalOnBean(type =
            "com.fasterxml.jackson.databind.ObjectMapper")
    @ConditionalOnProperty(
            prefix = "acme.audit.json",
            name = "enabled",
            havingValue = "true")
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditJsonCodec.class)
        AuditJsonCodec auditJsonCodec(ObjectMapper objectMapper) {
            return event -> {
                try {
                    return objectMapper.writeValueAsString(event);
                }
                catch (JsonProcessingException exception) {
                    throw new IllegalStateException(
                            "Could not encode audit event as JSON",
                            exception);
                }
            };
        }
    }
}
~~~

Phân tích:

- Bean AuditService nằm ở configuration ngoài và không phụ thuộc Jackson.
- JacksonConfiguration là nested static configuration.
- @ConditionalOnClass yêu cầu ObjectMapper có mặt.
- @ConditionalOnBean yêu cầu context đã có mapper bean.
- @ConditionalOnProperty yêu cầu người dùng bật acme.audit.json.enabled=true.
- @ConditionalOnMissingBean(AuditJsonCodec.class) cho phép ứng dụng cung cấp codec riêng.
- afterName đặt auto-configuration sau Jackson auto-configuration của Spring Boot nếu auto-configuration đó có mặt, để bean condition có thể nhìn thấy mapper do Boot đăng ký.

Các import Jackson xuất hiện trong file source vì module auto-configuration cần compile nested integration. Tuy nhiên, các method và chữ ký tham chiếu Jackson nằm bên trong nested configuration được bảo vệ bởi class condition. Không chuyển ObjectMapper vào method hoặc field của lớp AuditAutoConfiguration bên ngoài.

### 7.5. Đăng ký auto-configuration

Tạo file:

src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Nội dung:

~~~text
com.example.audit.autoconfigure.AuditAutoConfiguration
~~~

Spring Boot phát hiện auto-configuration qua file imports. Không cần component scan toàn package để tìm lớp cấu hình này.

## 8. Kiểm thử classpath có và không có dependency

ApplicationContextRunner tạo context nhỏ để kiểm tra từng tổ hợp condition. FilteredClassLoader cho phép mô phỏng một class hoặc package không có trên runtime classpath.

### 8.1. Test class hoàn chỉnh

File src/test/java/com/example/audit/AuditAutoConfigurationTests.java:

~~~java
package com.example.audit;

import com.example.audit.autoconfigure.AuditAutoConfiguration;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AuditAutoConfiguration.class));

    @Test
    void coreServiceWorksWhenJacksonIsMissing() {
        this.contextRunner
                .withClassLoader(
                        new FilteredClassLoader("com.fasterxml.jackson"))
                .withPropertyValues("acme.audit.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).doesNotHaveBean(AuditJsonCodec.class);
                });
    }

    @Test
    void jsonFeatureIsDisabledWhenPropertyIsMissing() {
        this.contextRunner
                .withUserConfiguration(JacksonMapperConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).doesNotHaveBean(AuditJsonCodec.class);
                });
    }

    @Test
    void jsonFeatureIsDisabledWhenMapperBeanIsMissing() {
        this.contextRunner
                .withPropertyValues("acme.audit.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).doesNotHaveBean(AuditJsonCodec.class);
                });
    }

    @Test
    void jsonFeatureWorksWhenDependencyBeanAndPropertyArePresent() {
        this.contextRunner
                .withUserConfiguration(JacksonMapperConfiguration.class)
                .withPropertyValues("acme.audit.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).hasSingleBean(AuditJsonCodec.class);

                    AuditJsonCodec codec =
                            context.getBean(AuditJsonCodec.class);

                    assertThat(codec.encode(
                            new AuditEvent("LOGIN", "alice")))
                            .isEqualTo(
                                    "{\"action\":\"LOGIN\",\"actor\":\"alice\"}");
                });
    }

    @Test
    void userCodecMakesDefaultCodecBackOff() {
        this.contextRunner
                .withUserConfiguration(
                        JacksonMapperConfiguration.class,
                        CustomCodecConfiguration.class)
                .withPropertyValues("acme.audit.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditJsonCodec.class);

                    AuditJsonCodec codec =
                            context.getBean(AuditJsonCodec.class);

                    assertThat(codec.encode(
                            new AuditEvent("LOGIN", "alice")))
                            .isEqualTo("custom:alice");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class JacksonMapperConfiguration {

        @Bean
        ObjectMapper objectMapper() {
            return new ObjectMapper();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomCodecConfiguration {

        @Bean
        AuditJsonCodec customAuditJsonCodec() {
            return event -> "custom:" + event.actor();
        }
    }
}
~~~

### 8.2. Chạy test

~~~bash
mvn test -Dtest=AuditAutoConfigurationTests
~~~

Kết quả mong đợi: **5 test PASS**.

| Test | Classpath | Mapper bean | Property | Kết quả |
| --- | --- | --- | --- | --- |
| Core without Jackson | Thiếu Jackson | Không có | true | Core hoạt động, JSON codec vắng mặt |
| Property missing | Có Jackson | Có | Không khai báo | JSON codec vắng mặt |
| Mapper missing | Có Jackson | Không có | true | JSON codec vắng mặt |
| All conditions match | Có Jackson | Có | true | JSON codec được tạo |
| User codec supplied | Có Jackson | Có | true | Codec mặc định back off |

Test đầu tiên là bằng chứng quan trọng nhất: dù property yêu cầu JSON, việc thiếu thư viện Jackson không làm AuditService thất bại hoặc khiến context không khởi động.

FilteredClassLoader("com.fasterxml.jackson") ẩn package Jackson trong classloader của context test. Đây là cách mô phỏng runtime thiếu thư viện mà không phải gỡ dependency khỏi project test.

## 9. Khi dependency có mặt nhưng bean chưa có

Một lỗi thường gặp là chỉ dùng @ConditionalOnClass:

~~~java
@ConditionalOnClass(name =
        "com.fasterxml.jackson.databind.ObjectMapper")
static class JacksonConfiguration {
}
~~~

Class Jackson có thể có trên classpath, nhưng không có bean ObjectMapper trong context. Khi đó @Bean method cần mapper vẫn có thể thất bại vì không resolve được dependency.

Nếu integration cần bean do Spring quản lý, thêm @ConditionalOnBean.

Có hai lựa chọn thiết kế:

1. **Yêu cầu ứng dụng cung cấp bean:** phù hợp khi cần dùng mapper đã được cấu hình chung, ví dụ mapper do Spring Boot hoặc ứng dụng tạo.
2. **Tự tạo collaborator trong integration:** phù hợp khi thư viện có default hợp lý và không cần dùng cấu hình chung. Khi đó phải kiểm tra xung đột và cho phép user override bằng @ConditionalOnMissingBean.

Không nên vừa giả định bean có sẵn, vừa không khai báo điều kiện hoặc default. Hợp đồng dependency cần rõ ràng.

## 10. Condition ordering: đừng để @ConditionalOnBean chạy quá sớm

@ConditionalOnBean và @ConditionalOnMissingBean đánh giá những bean definitions đã được xử lý tại thời điểm condition chạy. Nếu một auto-configuration cần bean do auto-configuration khác cung cấp, thứ tự có thể ảnh hưởng kết quả.

Ví dụ, Jackson mapper có thể được tạo bởi JacksonAutoConfiguration. Nếu custom integration kiểm tra ObjectMapper trước khi Jackson auto-configuration được xử lý, condition có thể không match.

Có thể khai báo thứ tự:

~~~java
@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration")
public class AuditAutoConfiguration {
}
~~~

afterName dùng chuỗi tên class nên lớp auto-configuration ngoài không cần import type Jackson auto-configuration.

Một số lưu ý:

- Auto-configuration ordering điều khiển thứ tự đăng ký bean definitions.
- Nó không quyết định thứ tự khởi tạo instance; dependency graph quyết định việc đó.
- User-defined bean definitions được xử lý trước auto-configuration, nên bean do ứng dụng khai báo thường có thể được condition nhìn thấy.
- Không dựa vào thứ tự ngẫu nhiên của classpath hoặc thứ tự file imports.

Nếu optional bean có thể được tạo bởi một auto-configuration cụ thể, hãy dùng ordering rõ ràng và kiểm thử cả trường hợp dependency có và không có.

## 11. Không dùng catch NoClassDefFoundError làm cơ chế optional dependency

Một cách dễ nghĩ đến là:

~~~java
try {
    Class.forName("com.example.optional.OptionalClient");
}
catch (Throwable exception) {
    // Bỏ qua và tiếp tục.
}
~~~

Hoặc bắt NoClassDefFoundError quanh toàn bộ quá trình tạo bean.

Đây không phải thiết kế tốt vì:

- Lỗi linkage có thể xuất hiện sau khi class đã được load một phần.
- Catch Throwable có thể nuốt cả lỗi nghiêm trọng của JVM.
- Một lỗi phiên bản không tương thích có thể bị hiểu nhầm là dependency tùy chọn vắng mặt.
- Context có thể tiếp tục với trạng thái thiếu một bean mà phần khác đang kỳ vọng.
- Test khó chứng minh rõ feature nào được bật hoặc tắt.

Dùng condition của Spring Boot để quyết định bean có được đăng ký hay không. Nếu class có mặt nhưng phiên bản không tương thích, đó là lỗi dependency/version cần giải quyết bằng dependency management và kiểm thử tương thích, không phải trường hợp optional library không tồn tại.

## 12. Khi người dùng bật tính năng nhưng dependency vẫn thiếu

Cần phân biệt hai tình huống:

**Tính năng không được yêu cầu:** property không bật hoặc không có thư viện. Hành vi mặc định nên là bỏ qua integration, giữ nguyên phần cốt lõi.

**Người dùng chủ động bật tính năng nhưng quên dependency:** ví dụ acme.audit.json.enabled=true nhưng Jackson không có. Có thể chọn một trong hai chính sách:

- Giữ integration không hoạt động và ghi condition report/diagnostic rõ ràng.
- Fail fast bằng thông báo có thể hành động, chỉ khi property bật tính năng đó.

Nếu chọn fail fast, lỗi phải nói rõ cần thêm dependency nào và thuộc tính nào đã kích hoạt tính năng. Không nên làm các tính năng cốt lõi thất bại chỉ vì thư viện tùy chọn chưa được yêu cầu.

Với starter dùng trong production, chính sách nên được ghi trong tài liệu cấu hình và được test riêng. Không để người dùng phải suy đoán vì sao bean tùy chọn không xuất hiện.

## 13. Các loại optional integration khác

Cùng một nguyên tắc áp dụng ngoài Jackson:

| Integration | Điều kiện classpath | Điều kiện bean thường gặp |
| --- | --- | --- |
| Redis | RedisConnectionFactory API có mặt | Có RedisConnectionFactory |
| Kafka | Kafka client classes có mặt | Có KafkaTemplate hoặc factory cần thiết |
| JDBC | JDBC driver/Boot JDBC classes phù hợp | Có DataSource |
| Web MVC | Servlet/MVC classes có mặt | Context là servlet web application |
| Metrics | Micrometer API có mặt | Có registry phù hợp |
| Cloud SDK | SDK client class có mặt | Có client/configuration bean được cung cấp |

Ví dụ Redis integration:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "org.springframework.data.redis.connection.RedisConnectionFactory")
@ConditionalOnBean(type =
        "org.springframework.data.redis.connection.RedisConnectionFactory")
@ConditionalOnProperty(
        prefix = "acme.cache.redis",
        name = "enabled",
        havingValue = "true")
static class RedisConfiguration {
    // Các bean Redis-specific được khai báo tại đây.
}
~~~

Các class trong ví dụ này phải được cô lập trong configuration tùy chọn. Không để RedisConnectionFactory xuất hiện trong chữ ký bean của configuration cốt lõi.

## 14. Kiểm thử ma trận optional dependency

Một auto-configuration library nên kiểm tra ít nhất các trường hợp:

| Trạng thái | Kỳ vọng |
| --- | --- |
| Optional class vắng mặt | Context core khởi động; optional bean không tồn tại |
| Optional class có mặt, property tắt | Optional bean không tồn tại |
| Optional class có mặt, property bật, collaborator bean vắng mặt | Context core khởi động; optional bean không tồn tại hoặc theo policy rõ ràng |
| Optional class có mặt, collaborator bean có, property bật | Optional bean được tạo |
| User đã cung cấp optional bean | Default bean back off |
| Optional integration không có dependency | Các API và bean cốt lõi vẫn dùng được |
| Dependency có mặt nhưng phiên bản không tương thích | Test/build phát hiện lỗi tương thích; không nuốt linkage error |

Có thể dùng:

- ApplicationContextRunner cho condition, property và user bean.
- FilteredClassLoader để mô phỏng thiếu class/package.
- ConditionEvaluationReport để kiểm tra lý do condition match hoặc không match.
- Integration test với đúng dependency và service test khi cần kiểm tra giao tiếp thật.

Đừng chỉ kiểm tra “context không failed”. Hãy assert đồng thời:

- Bean core vẫn tồn tại.
- Optional bean vắng mặt khi thiếu dependency.
- Optional bean có mặt khi mọi điều kiện match.
- User bean được giữ khi auto-configuration phải back off.

## 15. Chẩn đoán khi ứng dụng vẫn lỗi dù đã có @ConditionalOnClass

Làm theo trình tự:

1. Xác định exception gốc: NoClassDefFoundError, ClassNotFoundException, UnsatisfiedDependencyException hay BeanCreationException.
2. Tìm class tùy chọn xuất hiện trong stack trace hoặc chữ ký bean method.
3. Kiểm tra class đó nằm trong configuration cốt lõi hay nested optional configuration.
4. Kiểm tra condition đặt ở class level hay chỉ trên @Bean method.
5. Kiểm tra optional type có rò vào constructor, field, superclass, interface hoặc static initializer của class luôn được load không.
6. Kiểm tra bean collaborator có tồn tại trong ApplicationContext không.
7. Kiểm tra property đã bật đúng prefix và tên chưa.
8. Kiểm tra auto-configuration ordering nếu collaborator được tạo bởi auto-configuration khác.
9. Dùng FilteredClassLoader để tái hiện trường hợp dependency vắng mặt.
10. Kiểm tra dependency graph Maven/Gradle để xác nhận optional dependency không bị kéo vào ngoài ý muốn.
11. Chạy test với dependency có mặt để xác nhận integration vẫn hoạt động.
12. Đọc condition report để biết chính xác vì sao cấu hình bị bỏ qua.

Một class condition match không đảm bảo mọi dependency khác của bean đã sẵn sàng. Hãy kiểm tra cả classpath, bean graph và property.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Optional type xuất hiện trong outer auto-configuration | JVM có thể resolve class khi dependency vắng mặt | Cô lập trong nested static configuration |
| Chỉ dùng @ConditionalOnProperty | Property bật nhưng class cần thiết không có | Thêm @ConditionalOnClass |
| Chỉ dùng @ConditionalOnClass | Class có nhưng collaborator bean chưa tồn tại | Thêm @ConditionalOnBean hoặc tạo default phù hợp |
| Optional dependency không đánh dấu optional trong Maven | Consumer bị kéo thêm thư viện dù không dùng | Dùng optional=true hoặc starter riêng |
| Starter cơ bản kéo tất cả integration | Dependency tree lớn và xung đột version | Tách starter theo tính năng |
| API core nhận trực tiếp optional SDK type | Tính năng core cũng cần thư viện ngoài | Dùng interface thuộc module core |
| Dùng Class.forName và catch Throwable | Che giấu lỗi linkage và lỗi thật | Dùng Spring condition |
| @ConditionalOnBean chạy trước auto-config tạo collaborator | Integration bị bỏ qua dù collaborator sẽ xuất hiện sau | Dùng after/afterName và test ordering |
| User bean không được bảo vệ bằng @ConditionalOnMissingBean | Default và custom bean cùng tồn tại | Cho phép override có chủ đích |
| Chỉ test dependency có mặt | Không phát hiện lỗi khi thiếu optional library | Test với FilteredClassLoader |
| Chỉ test context không fail | Không chứng minh optional bean đã bị bỏ qua đúng cách | Assert cả core bean và optional bean |
| Dùng condition để che phiên bản library không tương thích | Lỗi runtime khó chẩn đoán | Quản lý version và test compatibility |

## 17. Checklist thiết kế optional integration

### Classpath và module

- [ ] Xác định rõ dependency nào bắt buộc và dependency nào tùy chọn.
- [ ] Maven optional hoặc Gradle compileOnly được khai báo đúng.
- [ ] Starter cơ bản không kéo dependency của integration không được yêu cầu.
- [ ] Có starter riêng nếu một nhóm optional dependency thường được dùng cùng nhau.

### Auto-configuration

- [ ] Auto-configuration được đăng ký qua AutoConfiguration.imports.
- [ ] Không dùng component scan rộng để tìm configuration trong thư viện.
- [ ] Optional type chỉ xuất hiện trong nested configuration được bảo vệ.
- [ ] Có @ConditionalOnClass cho thư viện cần thiết.
- [ ] Có @ConditionalOnBean nếu cần collaborator bean.
- [ ] Có @ConditionalOnProperty nếu tính năng cần opt-in.
- [ ] Default bean dùng @ConditionalOnMissingBean để hỗ trợ override.
- [ ] Ordering được khai báo nếu condition phụ thuộc auto-configuration khác.

### API và test

- [ ] API core không tham chiếu optional library.
- [ ] Optional integration dùng interface hoặc adapter phù hợp.
- [ ] Test classpath thiếu dependency bằng FilteredClassLoader.
- [ ] Test classpath có dependency nhưng thiếu collaborator bean.
- [ ] Test property tắt và property bật.
- [ ] Test user-defined bean override.
- [ ] Test chứng minh bean core vẫn hoạt động khi optional feature vắng mặt.
- [ ] Không nuốt NoClassDefFoundError hoặc Throwable để giả vờ dependency optional.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao @ConditionalOnClass trên @Bean method có thể chưa đủ để bảo vệ optional type?

**Đáp án:** JVM có thể load kiểu trong method signature trước khi condition của method được đánh giá. Hãy cô lập method tham chiếu optional type trong nested configuration có class-level @ConditionalOnClass.

**Câu 2.** @ConditionalOnClass và @ConditionalOnBean khác nhau thế nào?

**Đáp án:** Một annotation kiểm tra class có trên classpath; annotation còn lại kiểm tra bean tương ứng đã có trong ApplicationContext.

**Câu 3.** Khi nào dùng @ConditionalOnProperty?

**Đáp án:** Khi người dùng cần chủ động bật hoặc tắt optional feature qua cấu hình, thay vì tự động bật chỉ vì thư viện có trên classpath.

**Câu 4.** Maven optional=true có tự ngăn NoClassDefFoundError không?

**Đáp án:** Không. Nó chỉ ngăn dependency được truyền bắc cầu cho consumer. Code vẫn cần class-level condition và cô lập optional type.

**Câu 5.** Vì sao API cốt lõi không nên nhận ObjectMapper nếu JSON là optional?

**Đáp án:** Vì mọi consumer của API core sẽ phải resolve Jackson. Tách serializer thành interface/adapter tùy chọn giúp core hoạt động độc lập.

**Câu 6.** FilteredClassLoader dùng để làm gì?

**Đáp án:** Tạo test classloader mô phỏng class hoặc package không có trên runtime classpath, giúp kiểm tra auto-configuration khi dependency vắng mặt.

**Câu 7.** @ConditionalOnMissingBean bảo vệ điều gì?

**Đáp án:** Ngăn auto-configuration tạo bean mặc định khi ứng dụng đã cung cấp bean phù hợp, giúp custom implementation được ưu tiên.

**Câu 8.** Vì sao @ConditionalOnBean có thể không match dù bean sẽ được tạo sau đó?

**Đáp án:** Bean conditions đánh giá những bean definitions đã được xử lý tới thời điểm condition chạy. Cần sắp xếp auto-configuration phù hợp bằng after hoặc afterName.

**Câu 9.** Nếu người dùng bật feature nhưng thiếu dependency, nên xử lý ra sao?

**Đáp án:** Theo policy đã công bố: báo condition/diagnostic rõ ràng hoặc fail fast với thông báo dependency cần thêm. Trường hợp không yêu cầu feature thì không làm lỗi các tính năng cốt lõi.

## 19. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Creating Your Own Auto-configuration, class conditions, bean conditions, starter modules và optional dependencies: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — ConditionalOnClass: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 API — ConditionalOnBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.5 API — ConditionalOnProperty: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.5 API — ConditionalOnMissingBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.5 API — FilteredClassLoader: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.5 API — ApplicationContextRunner: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
