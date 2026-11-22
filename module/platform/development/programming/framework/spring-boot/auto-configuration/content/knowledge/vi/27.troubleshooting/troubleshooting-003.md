# NoClassDefFoundError do tham chiếu lớp tùy chọn quá sớm

> **Spring Boot Auto Configuration → Xử lý sự cố.** Bài học giải thích vì sao thư viện có thể biên dịch thành công nhưng ứng dụng tiêu thụ lại thất bại với NoClassDefFoundError khi thiếu dependency tùy chọn. Trọng tâm là thời điểm JVM phải phân giải kiểu trong class signature, giới hạn của @ConditionalOnClass trên @Bean method, cách cô lập integration trong nested static configuration, và cách xác minh bằng Maven dependency tree, FilteredClassLoader cùng một consumer độc lập. Ví dụ dùng Java 17+, Maven và Spring Boot 3.3.13.

## 1. Hiện tượng và nguyên nhân cốt lõi

Một thư viện cung cấp tính năng JDBC tùy chọn. Module auto-configuration được biên dịch khi spring-jdbc có trên compile classpath. Nhà phát triển đánh dấu dependency là optional để ứng dụng chỉ dùng core không phải kéo JDBC vào.

Ứng dụng tiêu thụ chỉ khai báo thư viện auto-configuration, không có spring-jdbc trên runtime classpath. Khi Spring khởi động, ứng dụng bất ngờ dừng với lỗi dạng:

~~~text
java.lang.NoClassDefFoundError:
  org/springframework/jdbc/core/JdbcTemplate

Caused by: java.lang.ClassNotFoundException:
  org.springframework.jdbc.core.JdbcTemplate
~~~

Đây là dạng lỗi đại diện. Stack trace và lớp bị thiếu cụ thể có thể khác tùy thời điểm JVM phải phân giải kiểu, classloader và dependency bị thiếu. Điều cần điều tra là vì sao một class thuộc integration tùy chọn lại bị chạm tới khi ứng dụng không định dùng integration đó.

Nguyên nhân phổ biến trong auto-configuration là tham chiếu trực tiếp một optional type quá sớm trong class hoặc method signature. Một condition có thể được thiết kế để bỏ qua tính năng khi class không có, nhưng JVM hoặc Spring đã phải đọc kiểu đó trước khi condition được đánh giá.

Ví dụ dễ gặp:

~~~java
@AutoConfiguration
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnClass(name =
            "org.springframework.jdbc.core.JdbcTemplate")
    NoticeJdbcHistoryWriter noticeJdbcHistoryWriter(
            JdbcTemplate jdbcTemplate) {

        return new NoticeJdbcHistoryWriter(jdbcTemplate);
    }
}
~~~

Ý định của code là: nếu JdbcTemplate không có thì method không được áp dụng. Nhưng method signature đã tham chiếu JdbcTemplate. Trước khi method-level condition được áp dụng, JVM có thể phải load class và xử lý các method references. Nếu type không có, lỗi linkage có thể xảy ra trước khi Spring kịp bỏ qua bean method.

Spring Boot ghi rõ trường hợp này trong Javadoc ConditionalOnClass: condition trên @Bean method không bảo vệ được return type có thể bị JVM load trước; cách xử lý là tách condition sang một configuration class riêng. Tham khảo: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html.

## 2. Phân biệt các lỗi class loading thường gặp

Không phải mọi lỗi class loading đều có cùng nguyên nhân. Hãy đọc chính xác exception type, tên class và phần Caused by.

| Lỗi | Ý nghĩa thường gặp | Hướng điều tra |
| --- | --- | --- |
| ClassNotFoundException | API load class tường minh như Class.forName(...) không tìm thấy class | Classloader, runtime classpath, tên class |
| NoClassDefFoundError | JVM cần một class khi liên kết/thực thi nhưng không thể tìm thấy hoặc class trước đó không khởi tạo thành công | Dependency runtime, class signature, static initializer |
| NoSuchMethodError | Class có mặt nhưng phiên bản được nạp không có method mà code đã compile cần | Version conflict, dependency mediation |
| NoSuchFieldError | Class có mặt nhưng field được tham chiếu không tồn tại ở version runtime | Version conflict, binary compatibility |
| AbstractMethodError | Runtime implementation không cung cấp method mà caller mong đợi | Phiên bản interface/implementation không tương thích |
| ExceptionInInitializerError | Static initializer ném exception khi class được khởi tạo | Exception đầu tiên trong static initializer |
| NoClassDefFoundError: Could not initialize class ... | Class đã thất bại trong lần khởi tạo trước; lần dùng sau không thể tiếp tục | Tìm exception gốc ở lần khởi tạo đầu tiên |

ClassNotFoundException thường là exception có checked type từ API load class tường minh. NoClassDefFoundError là một LinkageError do JVM phát ra khi cần liên kết class trong lúc chạy. Đừng chỉ nhìn tên NoClassDefFoundError rồi kết luận rằng file JAR hoàn toàn không tồn tại.

Ví dụ, class JdbcTemplate có thể có mặt nhưng một class khác mà nó phụ thuộc lại bị loại khỏi runtime classpath. Khi đó tên class trong error message có thể là dependency bắc cầu, không phải class mà code của bạn gọi trực tiếp.

### 2.1. Vì sao compile thành công nhưng runtime thất bại?

Compile và runtime có thể dùng classpath khác nhau.

- Trong module thư viện, Maven đưa dependency khai báo vào compile classpath để biên dịch code.
- Nếu dependency có optional=true, Maven không truyền dependency đó một cách bắc cầu đến consumer.
- Consumer có thể compile và chạy core feature mà không có optional integration.
- Nhưng nếu auto-configuration của thư viện buộc JVM phân giải optional type ngay khi nạp cấu hình, consumer sẽ lỗi dù không định dùng integration.

Ví dụ dependency:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-jdbc</artifactId>
    <optional>true</optional>
</dependency>
~~~

Dependency optional vẫn được dùng khi build module sở hữu nó. Thuộc tính optional nói với Maven rằng consumer không tự động nhận dependency này qua quan hệ bắc cầu. Ứng dụng cần JDBC phải tự khai báo dependency thích hợp.

Đây là hợp đồng hợp lý cho integration thực sự tùy chọn, nhưng chỉ an toàn nếu code core và auto-configuration có thể được nạp khi integration vắng mặt.

## 3. JVM phải phân giải kiểu ở đâu?

JVM không nhất thiết load và resolve mọi class được nhắc trong constant pool ngay tại thời điểm load class. Việc phân giải có thể diễn ra khi class hoặc member thực sự được sử dụng. Tuy nhiên, framework có thể yêu cầu reflection hoặc metadata về method để xử lý configuration, khiến kiểu trong method signature bị resolve sớm hơn dự kiến.

Các vị trí dễ tạo liên kết đến optional type gồm:

- Superclass hoặc interface mà auto-configuration kế thừa/implements.
- Field type hoặc constructor parameter của outer configuration.
- Kiểu trả về, parameter hoặc generic signature của @Bean method.
- Annotation chứa class literal hoặc annotation attribute cần resolve.
- Static field initializer, static block hoặc lời gọi tĩnh.
- Class.forName(...) hoặc reflection chạy vô điều kiện.
- @Import(OptionalConfiguration.class) trên outer configuration.
- Custom Condition được nạp và tham chiếu optional type trước khi classpath condition bảo vệ nó.
- Helper class được outer configuration gọi trong constructor hoặc static initializer.

Ví dụ outer configuration không an toàn:

~~~java
@AutoConfiguration
public class NoticeAutoConfiguration
        extends JdbcBasedConfiguration {

    private final JdbcTemplate jdbcTemplate;

    public NoticeAutoConfiguration(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
~~~

Chỉ cần JVM phải load outer configuration, nó đã gặp các kiểu JDBC trong hierarchy, field hoặc constructor. Condition ở một bean method khác không thể bảo vệ các tham chiếu này.

Một ví dụ khác là import trực tiếp optional config:

~~~java
@AutoConfiguration
@Import(NoticeJdbcConfiguration.class)
public class NoticeAutoConfiguration {
}
~~~

Nếu NoticeJdbcConfiguration có method signature dùng JdbcTemplate và được import vô điều kiện, optional boundary đã bị phá vỡ.

Quy tắc thiết kế: outer/core auto-configuration phải có thể được load khi optional integration hoàn toàn không có trên classpath. Chỉ nested configuration được bảo vệ mới tham chiếu optional API.

## 4. @ConditionalOnClass an toàn ở class-level như thế nào?

Spring Boot xử lý annotation metadata của configuration class bằng ASM trước khi load class đó. Vì vậy, @ConditionalOnClass trên một configuration class có thể tham chiếu class chưa có trên runtime classpath mà vẫn cho phép Boot kiểm tra metadata.

Ví dụ class-level:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(JdbcTemplate.class)
static class JdbcConfiguration {
}
~~~

Hoặc dùng tên class:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(
        name = "org.springframework.jdbc.core.JdbcTemplate"
)
static class JdbcConfiguration {
}
~~~

Cả hai dạng có thể dùng trực tiếp trên configuration class. Dùng name là lựa chọn tiện lợi khi muốn giữ outer configuration không cần import optional type hoặc khi tạo composed/meta-annotation.

**Lưu ý về meta-annotation:** nếu dùng @ConditionalOnClass hoặc @ConditionalOnMissingClass bên trong annotation tổng hợp do thư viện tự tạo, hãy dùng thuộc tính name. Spring Boot Javadoc chỉ bảo đảm việc đọc class literal bằng ASM khi annotation được đặt trực tiếp trên component bị điều kiện hóa, không áp dụng cùng cách cho meta-annotation.

Tham khảo: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html.

### 4.1. Vì sao method-level condition không đủ?

Xem ví dụ:

~~~java
@Bean
@ConditionalOnClass(JdbcTemplate.class)
NoticeJdbcHistoryWriter noticeJdbcHistoryWriter(
        JdbcTemplate jdbcTemplate) {
    return new NoticeJdbcHistoryWriter(jdbcTemplate);
}
~~~

Condition được đặt trên method, nhưng Spring phải phân tích method metadata, bao gồm return type và parameter type. JVM có thể đã load hoặc resolve các kiểu này trước khi method condition có cơ hội loại method.

Vì thế, không dùng method-level @ConditionalOnClass như một lá chắn cho chính method signature chứa optional type. Hãy chuyển method vào một nested @Configuration có class-level condition.

## 5. Mẫu sửa chuẩn: nested static configuration

Cấu trúc nên có ba ranh giới:

~~~text
NoticeAutoConfiguration
  |
  +-- NoticeClient bean
  |     Không tham chiếu optional JDBC API
  |
  +-- JdbcConfiguration (static nested class)
        @ConditionalOnClass(JdbcTemplate)
        @ConditionalOnProperty(...)
        |
        +-- NoticeJdbcHistoryWriter bean
              Signature có JdbcTemplate
~~~

Outer class chỉ chứa core bean và nested configuration declaration. Nested configuration chịu trách nhiệm bảo vệ toàn bộ phần code cần optional library.

Mẫu tổng quát:

~~~java
@AutoConfiguration
public class MyAutoConfiguration {

    // Các bean core không cần optional library.

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.OptionalClient")
    static class OptionalClientConfiguration {

        @Bean
        OptionalAdapter optionalAdapter(OptionalClient client) {
            return new OptionalAdapter(client);
        }
    }
}
~~~

Khi optional class vắng mặt:
1. Boot đọc metadata của nested configuration.
2. @ConditionalOnClass không match.
3. Nested configuration không được áp dụng.
4. Các method signature chứa optional type không cần được xử lý như bean methods hoạt động.
5. Outer auto-configuration và các bean core vẫn có thể tiếp tục.

Khi optional class có mặt:
1. Class condition match.
2. Boot xử lý nested configuration.
3. Các bean methods có thể tham chiếu optional API.
4. Các condition bean/property còn lại quyết định bean cụ thể có được đăng ký hay không.

Nên dùng nested class static để nó không giữ implicit reference đến instance của outer class. Đặt proxyBeanMethods=false nếu không cần gọi chéo các @Bean method qua proxy.

### 5.1. Cô lập từng integration riêng

Nếu thư viện hỗ trợ JDBC, Kafka và Redis, hãy tách thành các nested configuration:

~~~java
@AutoConfiguration
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    NoticeClient noticeClient() {
        return new NoticeClient("auto");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.springframework.jdbc.core.JdbcTemplate")
    static class JdbcConfiguration {
        // Chỉ code JDBC ở đây.
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.springframework.kafka.core.KafkaTemplate")
    static class KafkaConfiguration {
        // Chỉ code Kafka ở đây.
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.springframework.data.redis.core.RedisTemplate")
    static class RedisConfiguration {
        // Chỉ code Redis ở đây.
    }
}
~~~

Một integration thiếu dependency không nên làm các integration khác hoặc core bean bị lỗi. Mỗi nested configuration có condition riêng, property riêng và bean riêng.

Không đưa optional type vào import, field hoặc method signature của outer class. Cũng không dùng component scan rộng để tìm mọi integration class, vì scan có thể buộc Spring xem xét các type không được bảo vệ.

## 6. Ví dụ hoàn chỉnh với Spring Boot 3.3.13

Ta tạo một auto-configuration thư viện thông báo với hai phần:
- NoticeClient: core feature, không cần JDBC.
- NoticeJdbcHistoryWriter: integration tùy chọn, cần JdbcTemplate.

Khi consumer không có Spring JDBC, core vẫn chạy. Khi consumer có Spring JDBC, bật property và cung cấp bean JdbcTemplate, writer mới được tạo.

### 6.1. Cấu trúc thư mục

~~~text
notice-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/notice/
    │   │   └── NoticeClient.java
    │   ├── java/com/acme/notice/autoconfigure/
    │   │   └── NoticeAutoConfiguration.java
    │   ├── java/com/acme/notice/jdbc/
    │   │   └── NoticeJdbcHistoryWriter.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/notice/autoconfigure/
            └── NoticeAutoConfigurationOptionalJdbcTest.java
~~~

### 6.2. pom.xml của module auto-configuration

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.acme.notice</groupId>
    <artifactId>notice-autoconfigure</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
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

Trong module này, spring-jdbc có mặt trên compile/test classpath để biên dịch integration JDBC. Maven optional bảo đảm consumer không tự động nhận dependency đó qua dependency graph.

spring-boot-autoconfigure là dependency cần thiết để biên dịch auto-configuration. Test starter chỉ phục vụ kiểm thử.

### 6.3. NoticeClient.java — core không phụ thuộc JDBC

Tệp src/main/java/com/acme/notice/NoticeClient.java:

~~~java
package com.acme.notice;

public record NoticeClient(String source) {

    public String send(String message) {
        return source + ":" + message;
    }
}
~~~

Class này chỉ dùng Java chuẩn. Nó có thể được load và sử dụng trong ứng dụng không có Spring JDBC.

### 6.4. NoticeJdbcHistoryWriter.java — chỉ dành cho integration JDBC

Tệp src/main/java/com/acme/notice/jdbc/NoticeJdbcHistoryWriter.java:

~~~java
package com.acme.notice.jdbc;

import org.springframework.jdbc.core.JdbcTemplate;

public class NoticeJdbcHistoryWriter {

    private final JdbcTemplate jdbcTemplate;

    public NoticeJdbcHistoryWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public String jdbcTemplateType() {
        return this.jdbcTemplate.getClass().getSimpleName();
    }
}
~~~

Class này tham chiếu trực tiếp JdbcTemplate. Điều đó phù hợp vì đây là implementation của integration JDBC. Điều cần bảo đảm là không có core configuration nào load class này khi JDBC vắng mặt.

### 6.5. NoticeAutoConfiguration.java — outer class không tham chiếu JDBC

Tệp src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;
import com.acme.notice.jdbc.NoticeJdbcHistoryWriter;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@AutoConfiguration
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    NoticeClient noticeClient() {
        return new NoticeClient("auto");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "org.springframework.jdbc.core.JdbcTemplate"
    )
    @ConditionalOnProperty(
            prefix = "acme.notice.jdbc",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    static class JdbcConfiguration {

        @Bean
        @ConditionalOnBean(JdbcTemplate.class)
        @ConditionalOnMissingBean(NoticeJdbcHistoryWriter.class)
        NoticeJdbcHistoryWriter noticeJdbcHistoryWriter(
                JdbcTemplate jdbcTemplate) {

            return new NoticeJdbcHistoryWriter(jdbcTemplate);
        }
    }
}
~~~

Trong ví dụ này, NoticeAutoConfiguration không khai báo field, constructor hoặc method signature có kiểu JdbcTemplate. Tất cả tham chiếu JDBC nằm trong nested JdbcConfiguration.

Có thể thấy NoticeJdbcHistoryWriter và JdbcTemplate được import trong cùng source file, nhưng chỉ nested configuration dùng chúng trong bean method. Khi muốn ranh giới rõ hơn nữa, có thể chuyển JdbcConfiguration sang file riêng; nguyên tắc quan trọng vẫn là class đó phải được condition bảo vệ trước khi Spring xử lý method signature.

Hai condition ở nested configuration có nhiệm vụ khác nhau:
- ConditionalOnClass(name=...): kiểm tra API JDBC có trên classpath.
- ConditionalOnProperty: kiểm tra người dùng có bật integration hay không.

Hai condition trên bean method:
- ConditionalOnBean(JdbcTemplate.class): chỉ tạo writer khi context có bean JDBC.
- ConditionalOnMissingBean(NoticeJdbcHistoryWriter.class): cho phép ứng dụng tự cung cấp writer thay thế.

### 6.6. AutoConfiguration.imports

Tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
~~~

Spring Boot phát hiện outer auto-configuration từ imports file. Nested JdbcConfiguration được quản lý bên trong outer class và không cần đăng ký thành một candidate độc lập.

### 6.7. Test bằng ApplicationContextRunner và FilteredClassLoader

Tệp src/test/java/com/acme/notice/autoconfigure/NoticeAutoConfigurationOptionalJdbcTest.java:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;
import com.acme.notice.jdbc.NoticeJdbcHistoryWriter;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeAutoConfigurationOptionalJdbcTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeAutoConfiguration.class
                    ));

    @Test
    void coreStartsWhenJdbcClassesAreMissing() {
        runner.withClassLoader(
                new FilteredClassLoader("org.springframework.jdbc")
        ).withPropertyValues("acme.notice.jdbc.enabled=true")
         .run(context -> {
             assertThat(context).hasNotFailed();
             assertThat(context).hasSingleBean(NoticeClient.class);
             assertThat(context).doesNotHaveBean(
                     "noticeJdbcHistoryWriter"
             );
         });
    }

    @Test
    void jdbcIntegrationStaysDisabledWhenPropertyIsFalse() {
        runner.withPropertyValues("acme.notice.jdbc.enabled=false")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context).doesNotHaveBean(
                            "noticeJdbcHistoryWriter"
                    );
                });
    }

    @Test
    void jdbcClassAndPropertyAreNotEnoughWithoutJdbcTemplateBean() {
        runner.withPropertyValues("acme.notice.jdbc.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context).doesNotHaveBean(
                            "noticeJdbcHistoryWriter"
                    );
                });
    }

    @Test
    void writerIsCreatedWhenClassPropertyAndBeanArePresent() {
        runner.withPropertyValues("acme.notice.jdbc.enabled=true")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NoticeJdbcHistoryWriter.class);

                    NoticeJdbcHistoryWriter writer =
                            context.getBean(NoticeJdbcHistoryWriter.class);

                    assertThat(writer.jdbcTemplateType())
                            .isEqualTo("JdbcTemplate");
                });
    }

    @Test
    void applicationWriterOverridesDefaultWriter() {
        NoticeJdbcHistoryWriter custom =
                new NoticeJdbcHistoryWriter(new JdbcTemplate());

        runner.withPropertyValues("acme.notice.jdbc.enabled=true")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .withBean(NoticeJdbcHistoryWriter.class, () -> custom)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NoticeJdbcHistoryWriter.class);

                    assertThat(context.getBean(NoticeJdbcHistoryWriter.class))
                            .isSameAs(custom);
                });
    }
}
~~~

Test đầu tiên mô phỏng ứng dụng không có Spring JDBC dù test module vẫn có dependency JDBC trên classpath. FilteredClassLoader ẩn package khỏi classloader của context. Nếu optional boundary được thiết kế đúng, context vẫn khởi động, core bean vẫn có và bean JDBC không xuất hiện.

Các test còn lại tách rõ từng điều kiện:
- Class có mặt nhưng property false: integration bị tắt.
- Class và property đều match nhưng không có JdbcTemplate bean: writer không được tạo.
- Class, property và bean dependency đều có: writer được tạo.
- Ứng dụng cung cấp writer riêng: auto-configuration back off.

### 6.8. Chạy test

Từ thư mục có pom.xml:

~~~bash
mvn clean test
~~~

Kỳ vọng năm test đều PASS. Nếu test coreStartsWhenJdbcClassesAreMissing thất bại với NoClassDefFoundError, kiểm tra stack trace để tìm class nào đang bị load trước khi nested condition có hiệu lực.

Test này xác minh behavior trong một context có classloader bị lọc. Nó không thay thế kiểm thử consumer độc lập, nơi optional dependency thật sự không được resolve vào runtime classpath.

## 7. Consumer độc lập: xác minh optional dependency không bị kéo theo

FilteredClassLoader hữu ích để mô phỏng thiếu class, nhưng cần thêm một kiểm tra ở mức artifact. Hãy build và install module auto-configuration, sau đó tạo một ứng dụng tiêu thụ riêng chỉ phụ thuộc artifact đó.

### 7.1. Build và cài module thư viện

Từ thư mục notice-autoconfigure:

~~~bash
mvn clean install
~~~

Artifact được cài vào local Maven repository. Dependency spring-jdbc có scope compile/runtime trong module phát hành nhưng được đánh dấu optional, vì vậy consumer không tự động nhận nó.

### 7.2. POM của consumer

Consumer chỉ khai báo Boot và thư viện:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>com.acme.notice</groupId>
        <artifactId>notice-autoconfigure</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

Không khai báo spring-jdbc trong consumer. Consumer không cần biết NoticeJdbcHistoryWriter hoặc JdbcTemplate nếu chỉ dùng core.

### 7.3. ConsumerApplication.java

~~~java
package demo.consumer;

import com.acme.notice.NoticeClient;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }

    @Bean
    ApplicationRunner report(NoticeClient client) {
        return args -> System.out.println(
                "notice: " + client.send("hello")
        );
    }
}
~~~

Ứng dụng không import hoặc tham chiếu optional integration. Spring Boot tự phát hiện NoticeAutoConfiguration qua AutoConfiguration.imports trong JAR.

### 7.4. Kiểm tra dependency graph

Từ thư mục consumer:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-jdbc
~~~

Nếu optional dependency được khai báo đúng, lệnh không liệt kê spring-jdbc trong dependency tree của consumer.

Kiểm tra toàn bộ dependency nếu cần:

~~~bash
mvn dependency:tree
~~~

Điều này giúp phát hiện một starter khác vô tình kéo Spring JDBC vào. Nếu tree có spring-jdbc, truy ngược nhánh dependency thay vì kết luận rằng optional flag không hoạt động.

### 7.5. Chạy consumer

~~~bash
mvn clean package
java -jar target/notice-consumer-1.0.0.jar
~~~

Output xác định của ví dụ:

~~~text
notice: auto:hello
~~~

Core bean được tạo và chạy. JDBC nested configuration bị bỏ qua vì class không có trên runtime classpath. Ứng dụng không cần thêm dependency JDBC chỉ để dùng NoticeClient.

Nếu người dùng muốn bật history, họ phải thêm dependency JDBC/starter tương ứng, cấu hình DataSource và bảo đảm JdbcTemplate bean được tạo. Sau đó đặt:

~~~properties
acme.notice.jdbc.enabled=true
~~~

Property không tự cài dependency. Nó chỉ bật feature sau khi điều kiện classpath và bean dependency đã đáp ứng.

## 8. Các lỗi thiết kế cần tìm khi điều tra

### 8.1. Optional type nằm trong outer @Bean signature

Không an toàn:

~~~java
@AutoConfiguration
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.SearchClient")
    SearchAdapter searchAdapter(SearchClient client) {
        return new SearchAdapter(client);
    }
}
~~~

Sửa bằng nested configuration:

~~~java
@AutoConfiguration
public class SearchAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.SearchClient")
    static class SearchConfiguration {

        @Bean
        SearchAdapter searchAdapter(SearchClient client) {
            return new SearchAdapter(client);
        }
    }
}
~~~

### 8.2. Optional type nằm trong superclass hoặc interface

Không an toàn:

~~~java
@AutoConfiguration
public class JdbcAutoConfiguration extends JdbcSupportBase {
}
~~~

Nếu JdbcSupportBase phụ thuộc JDBC, outer class không còn độc lập. Chuyển logic vào helper hoặc nested configuration được bảo vệ. Đừng để core configuration kế thừa implementation của optional module.

### 8.3. Optional type nằm trong field hoặc constructor

Không an toàn:

~~~java
@AutoConfiguration
public class MetricsAutoConfiguration {

    private final OptionalRegistry registry;

    public MetricsAutoConfiguration(OptionalRegistry registry) {
        this.registry = registry;
    }
}
~~~

Không inject optional dependency vào constructor của outer configuration. Đặt dependency vào method của nested config hoặc factory method chỉ được xử lý khi classpath condition match.

### 8.4. Optional type trong static initializer

Không an toàn:

~~~java
static {
    OptionalClient.initializeGlobalDefaults();
}
~~~

Static initializer chạy khi class được khởi tạo. Condition không thể hoàn tác side effect đã xảy ra. Chuyển việc khởi tạo vào bean factory method trong nested configuration; tránh khởi tạo toàn cục ở thời điểm class loading.

### 8.5. Class literal và reflection vô điều kiện

Không an toàn:

~~~java
private static final Class<?> CLIENT_TYPE = OptionalClient.class;
~~~

Hoặc:

~~~java
Class.forName("com.vendor.OptionalClient");
~~~

Nếu đoạn code chạy khi outer configuration được load, nó có thể ném lỗi trước khi Spring condition bảo vệ integration. Nếu cần kiểm tra class, ưu tiên @ConditionalOnClass hoặc ClassUtils.isPresent(...) với classloader phù hợp trong custom condition không có tham chiếu tĩnh đến optional type.

Không dùng Class.forName(...) mặc định với initialization nếu mục tiêu chỉ là kiểm tra sự hiện diện; thao tác đó có thể khởi tạo class và chạy static initializer. Trong hầu hết auto-configuration, condition chuẩn của Spring Boot là lựa chọn phù hợp hơn.

### 8.6. Meta-annotation dùng class literal

Khi tạo annotation tổng hợp:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(OptionalClient.class)
public @interface ConditionalOnOptionalClient {
}
~~~

Đây không phải cách an toàn theo quy tắc meta-annotation của ConditionalOnClass. Dùng tên class:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.OptionalClient")
public @interface ConditionalOnOptionalClient {
}
~~~

Spring Boot ghi rõ value class literal chỉ được xử lý an toàn khi annotation nằm trực tiếp trên component bị điều kiện hóa; với composed annotation phải dùng name.

## 9. Quy trình chẩn đoán NoClassDefFoundError

Đi từ exception gốc đến dependency graph và vị trí tham chiếu.

### Bước 1: xác định class thực sự bị thiếu

Đọc dòng đầu và toàn bộ cause chain:

~~~text
NoClassDefFoundError: org/springframework/jdbc/core/JdbcTemplate
Caused by: ClassNotFoundException:
  org.springframework.jdbc.core.JdbcTemplate
~~~

Ghi lại binary name chính xác, không chỉ ghi tên integration chung chung. Nếu message là Could not initialize class, tìm lỗi static initialization đầu tiên trong log trước đó.

### Bước 2: tìm nơi class bị tham chiếu

Trong stack trace, tìm frame đầu tiên thuộc code thư viện hoặc Spring đang phân tích configuration. Kiểm tra:
- Outer auto-configuration có field/constructor/method signature chứa type đó không?
- @Bean method nào có return/parameter type đó?
- Condition nằm ở class hay method?
- Nested configuration đã được dùng để cô lập optional type chưa?
- Có custom condition, static initializer hoặc @Import vô điều kiện không?

Nếu frame nằm trong reflection như getDeclaredMethods, getDeclaredConstructors hoặc Spring configuration parser, hãy kiểm tra method signatures của configuration class đang được parse.

### Bước 3: xem dependency tree ở consumer

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-jdbc
~~~

Có thể xem dependency tree chi tiết:

~~~bash
mvn dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Và truy nguyên một dependency cụ thể:

~~~bash
./gradlew dependencyInsight --dependency spring-jdbc --configuration runtimeClasspath
~~~

So sánh compile classpath và runtime classpath. Class có trong IDE hoặc test không có nghĩa class đó được đóng gói vào ứng dụng chạy thật.

### Bước 4: kiểm tra optional, scope và exclusion

Trong POM thư viện, kiểm tra:
- Dependency có bị đánh dấu optional ngoài ý muốn không?
- Consumer có cần tự khai báo integration không?
- Có exclusion loại mất class hoặc dependency bắc cầu không?
- Version có được dependency management override không?
- Có dùng provided trong khi ứng dụng thực sự cần dependency ở runtime không?

Nếu integration là bắt buộc, hãy cung cấp starter kéo dependency cần thiết. Nếu integration là tùy chọn, giữ optional dependency nhưng bảo vệ mọi tham chiếu đến nó.

### Bước 5: kiểm tra artifact đã phát hành

Kiểm tra JAR:

~~~bash
jar tf target/notice-autoconfigure-1.0.0.jar
~~~

Đảm bảo:
- Outer auto-configuration class có mặt.
- Nested configuration và integration class có mặt trong artifact nếu module cung cấp chúng.
- AutoConfiguration.imports có đúng FQCN.
- Dependency version trong POM phát hành là version dự kiến.

Nếu class có trong JAR nhưng dependency nó cần không có trong consumer, đây vẫn là lỗi runtime classpath. Đừng nhầm sự tồn tại của class file với sự tồn tại của toàn bộ dependency graph.

### Bước 6: chạy consumer không có optional dependency

Tạo một consumer riêng, chỉ khai báo core/autoconfigure artifact. Kiểm tra:
- Dependency tree không có optional artifact.
- Context khởi động thành công.
- Core bean có mặt.
- Optional bean không có.
- Không có NoClassDefFoundError.

Đây là bằng chứng thực tế rằng ranh giới optional hoạt động.

### Bước 7: thêm dependency và bật feature để kiểm tra nhánh dương

Sau khi nhánh thiếu dependency chạy ổn, thêm dependency optional, cấu hình property và bean nền. Xác nhận integration được kích hoạt đúng.

Một thư viện tốt cần kiểm tra cả hai phía:
- Không có optional dependency: core vẫn chạy.
- Có optional dependency và điều kiện đủ: integration chạy.

## 10. Không dùng catch LinkageError để che lỗi cấu hình

Một cách sửa sai là bắt lỗi:

~~~java
try {
    Class.forName("org.springframework.jdbc.core.JdbcTemplate");
}
catch (NoClassDefFoundError ex) {
    // Ignore and continue
}
~~~

Hoặc:

~~~java
try {
    return new NoticeJdbcHistoryWriter(...);
}
catch (LinkageError error) {
    return null;
}
~~~

Cách này có nhiều vấn đề:
- Condition đã được đánh giá quá muộn; cấu hình có thể đã lỗi khi load.
- Có thể nuốt một lỗi version incompatibility hoặc lỗi static initialization thực sự.
- ApplicationContext có thể tiếp tục với trạng thái không đầy đủ.
- Lỗi chỉ xuất hiện khi request chạm vào code đó.
- Stack trace gốc bị che và khó chẩn đoán.

LinkageError là lỗi liên kết JVM, không phải cơ chế bật/tắt feature thông thường. Hãy mô tả dependency và điều kiện ở metadata/configuration level để Spring loại cấu hình trước khi load optional implementation.

Nếu một thư viện bên ngoài ném lỗi trong static initializer, hãy sửa dependency hoặc code khởi tạo. Đừng biến lỗi đó thành fallback im lặng.

## 11. Khi nào cần thêm dependency thay vì sửa auto-configuration?

Không phải mọi NoClassDefFoundError đều là bug của thư viện. Có thể người dùng đang bật feature nhưng quên dependency cần thiết.

| Tình huống | Cách xử lý |
| --- | --- |
| Feature được thiết kế tùy chọn, người dùng không dùng | Auto-configuration phải bỏ qua an toàn khi class vắng mặt |
| Feature tùy chọn được bật nhưng dependency chưa có | Báo rõ dependency cần cài hoặc để condition không match theo contract đã tài liệu hóa |
| Feature là yêu cầu bắt buộc của starter | Starter cần kéo dependency đó vào runtime classpath |
| Dependency có class nhưng thiếu dependency bắc cầu | Sửa exclusion/version conflict hoặc POM |
| Class có mặt nhưng method/field không tương thích | Đồng bộ version, kiểm tra dependency mediation |
| Class load thất bại do static initializer | Sửa nguyên nhân trong initializer hoặc môi trường |
| Code tham chiếu optional type ở outer config | Cô lập type vào nested configuration có class-level condition |

Nếu feature được bật tường minh nhưng dependency thiếu, có hai cách thiết kế:
- Silent back-off: ứng dụng tiếp tục chạy core, integration không xuất hiện. Phù hợp khi feature thực sự tùy chọn và người dùng có thể chưa cài dependency.
- Fail-fast có thông báo rõ: dùng custom validation/startup check ở nơi phù hợp nếu bật feature mà thiếu dependency là cấu hình không hợp lệ theo contract sản phẩm.

Dù chọn cách nào, không để lỗi linkage ngẫu nhiên quyết định hành vi. Hãy tài liệu hóa property, dependency và điều kiện bắt buộc.

## 12. Kiểm thử chống tái phát

Một bộ test tốt nên có các kịch bản:

| Kịch bản | Class optional | Property | Bean dependency | Kết quả |
| --- | --- | --- | --- | --- |
| Core-only consumer | Không | Bật hoặc thiếu | Không | Core chạy, integration vắng |
| JDBC có nhưng feature tắt | Có | false | Có | Integration vắng |
| JDBC có, feature bật, thiếu bean | Có | true | Không | Integration vắng |
| JDBC có, feature bật, đủ bean | Có | true | Có | Integration xuất hiện |
| User override | Có | true | Có | Giữ bean tùy chỉnh |
| Dependency version không tương thích | Có nhưng sai version | true | Có/không | Phát hiện lỗi binary compatibility trong test/build |

Dùng FilteredClassLoader để mô phỏng classpath thiếu nhanh trong ApplicationContextRunner. Dùng consumer độc lập để xác minh Maven optional dependency thật sự không truyền sang runtime. Hai cách bổ trợ nhau.

Spring Boot tài liệu hóa cách dùng FilteredClassLoader trong auto-configuration tests để giả lập class hoặc package không tồn tại. Tham khảo: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html.

## 13. Những lỗi phổ biến cần tránh

1. **Đặt @ConditionalOnClass trên @Bean method có optional return type.** JVM có thể phải load return/parameter type trước khi condition áp dụng.
2. **Đưa optional class vào outer configuration constructor.** Outer config cần được load trước khi Spring đánh giá nested bean conditions.
3. **Đưa optional type vào superclass hoặc interface.** JVM cần xử lý hierarchy khi load outer class.
4. **Dùng optional type trong field hoặc static initializer.** Việc phân giải/khởi tạo có thể xảy ra quá sớm.
5. **Import optional configuration vô điều kiện.** @Import trực tiếp không tự tạo classpath guard.
6. **Đặt class literal trong custom meta-annotation.** Composed @ConditionalOnClass phải dùng name.
7. **Nghĩ rằng condition ở outer class bảo vệ mọi method trong mọi tình huống.** Cần cô lập method signature có optional type trong nested configuration theo hướng dẫn Boot.
8. **Chỉ test trên classpath đầy đủ.** Test thường không phát hiện lỗi optional boundary.
9. **Chỉ test với FilteredClassLoader.** Vẫn cần consumer artifact độc lập để xác minh dependency graph Maven.
10. **Dùng Class.forName vô điều kiện.** Có thể tạo linkage/initialization error trước khi condition được xử lý.
11. **Bắt NoClassDefFoundError rồi bỏ qua.** Điều này che lỗi dependency và trạng thái cấu hình không đầy đủ.
12. **Nhầm compile classpath với runtime classpath.** IDE compile thành công không chứng minh executable có đủ dependency.
13. **Đánh dấu dependency optional nhưng không tài liệu hóa.** Consumer không biết cần thêm artifact nào để bật feature.
14. **Dùng provided hoặc exclusion sai mục đích.** Dependency cần ở runtime có thể bị loại khỏi executable.
15. **Để core class phụ thuộc optional implementation.** Một bean core có thể kéo optional type vào class loading chain.
16. **Đặt mọi integration trong một configuration khổng lồ.** Một optional class có thể làm hỏng các feature độc lập.
17. **Không kiểm tra dependency bắc cầu.** Class lỗi có thể là dependency của optional class chứ không phải type được gọi trực tiếp.
18. **Nhầm NoSuchMethodError với NoClassDefFoundError.** Một lỗi thường do version mismatch, lỗi kia liên quan class linkage/initialization.
19. **Không phân biệt class vắng với class khởi tạo thất bại.** Message Could not initialize class yêu cầu tìm exception đầu tiên.
20. **Chỉ xác minh bean vắng mặt.** Hãy xác minh context không fail và core feature vẫn hoạt động.
21. **Không kiểm thử nhánh dương.** Guard có thể quá chặt và vô tình vô hiệu hóa integration khi dependency đã có.
22. **Dùng component scan rộng để tìm integration.** Điều này có thể khiến Spring phân tích optional class ngoài ranh giới đã bảo vệ.

## 14. Quy trình thiết kế optional integration an toàn

1. Liệt kê các dependency chỉ cần cho integration, không cần cho core.
2. Đánh dấu dependency Maven optional nếu consumer phải tự chọn integration.
3. Giữ outer auto-configuration chỉ tham chiếu core types và Spring Boot APIs luôn có.
4. Tạo một nested static @Configuration cho mỗi integration.
5. Đặt @ConditionalOnClass trực tiếp trên nested configuration, dùng name nếu phù hợp.
6. Thêm @ConditionalOnProperty nếu feature cần bật tường minh.
7. Đặt các @Bean method có optional return/parameter type bên trong nested configuration.
8. Dùng @ConditionalOnBean khi bean nền phải tồn tại.
9. Dùng @ConditionalOnMissingBean để consumer có thể override.
10. Tránh outer constructor, field, superclass, static initializer và import tham chiếu optional type.
11. Dùng FilteredClassLoader để test khi class/package bị thiếu.
12. Build/install artifact và tạo consumer độc lập.
13. Kiểm tra dependency tree runtime của consumer.
14. Chạy consumer core-only và xác nhận core vẫn hoạt động.
15. Thêm optional dependency, bật feature và xác nhận integration hoạt động.
16. Kiểm tra version compatibility và exclusion nếu vẫn gặp linkage error.

## 15. Checklist nghiệm thu

- [ ] Đã xác định chính xác binary name trong NoClassDefFoundError.
- [ ] Đã đọc đầy đủ cause chain và phân biệt lỗi class missing với initialization failure.
- [ ] Đã kiểm tra runtime dependency tree của consumer.
- [ ] Dependency optional được đánh dấu có chủ đích và có tài liệu.
- [ ] Outer auto-configuration không tham chiếu optional type trong hierarchy, field hoặc constructor.
- [ ] Outer @Bean methods không có optional type trong return/parameter signature.
- [ ] Mỗi integration có nested static configuration riêng.
- [ ] @ConditionalOnClass nằm ở cấp nested configuration.
- [ ] Composed/meta-annotation dùng name thay vì class literal.
- [ ] Optional bean methods chỉ nằm trong configuration được bảo vệ.
- [ ] Property condition và bean conditions được đặt đúng tầng.
- [ ] Không có Class.forName hoặc static initializer optional chạy vô điều kiện.
- [ ] Không dùng catch LinkageError để che lỗi.
- [ ] Test classpath thiếu bằng FilteredClassLoader.
- [ ] Test classpath đầy đủ và bean dependency có mặt.
- [ ] Test user bean override nếu starter hỗ trợ.
- [ ] Consumer độc lập không có optional dependency vẫn khởi động.
- [ ] Dependency tree consumer không có optional artifact khi chưa khai báo.
- [ ] Consumer bật integration sau khi thêm dependency hoạt động đúng.
- [ ] Đã kiểm tra artifact JAR và imports metadata.
- [ ] Đã phân biệt lỗi missing class với lỗi version incompatibility.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao thư viện compile được nhưng consumer lại gặp NoClassDefFoundError?  
**Đáp án:** Compile classpath của module thư viện có dependency, nhưng dependency optional không được Maven truyền sang consumer. Runtime có thể thiếu class mà outer configuration hoặc method signature đã tham chiếu quá sớm.

**Câu 2.** Vì sao @ConditionalOnClass trên @Bean method không đủ bảo vệ optional return type?  
**Đáp án:** JVM có thể load hoặc xử lý method signature trước khi method condition được đánh giá. Spring Boot khuyến nghị tách method vào một configuration class riêng có class-level condition.

**Câu 3.** Vì sao @ConditionalOnClass trên configuration class an toàn hơn?  
**Đáp án:** Spring Boot đọc annotation metadata bằng ASM trước khi load configuration class, nên có thể bỏ qua class khi dependency không tồn tại.

**Câu 4.** Vì sao nên dùng nested static configuration?  
**Đáp án:** Nó cô lập method signatures, field và implementation cần optional API; outer configuration vẫn load được khi integration vắng mặt.

**Câu 5.** optional=true trong Maven có nghĩa gì?  
**Đáp án:** Dependency vẫn được dùng để build module khai báo nó, nhưng không tự động truyền bắc cầu sang consumer. Consumer cần tự khai báo nếu dùng feature đó.

**Câu 6.** ClassNotFoundException và NoClassDefFoundError khác nhau thế nào?  
**Đáp án:** ClassNotFoundException thường đến từ API load class tường minh; NoClassDefFoundError là LinkageError khi JVM cần class để liên kết/thực thi hoặc class trước đó không khởi tạo thành công.

**Câu 7.** Dùng công cụ nào để test class optional vắng mặt trong ApplicationContextRunner?  
**Đáp án:** FilteredClassLoader, ví dụ new FilteredClassLoader("org.springframework.jdbc"), rồi assert context không fail và core bean vẫn có.

**Câu 8.** Nếu class optional có mặt nhưng không có bean JdbcTemplate thì sao?  
**Đáp án:** Classpath condition match nhưng ConditionalOnBean(JdbcTemplate.class) không match, nên bean JDBC adapter không được tạo.

**Câu 9.** Vì sao không nên bắt NoClassDefFoundError để bỏ qua?  
**Đáp án:** Đây là lỗi linkage nghiêm trọng; bắt nó có thể che dependency/version bug và để ứng dụng chạy trong trạng thái không đầy đủ.

**Câu 10.** Cần kiểm tra gì nếu error message là Could not initialize class?  
**Đáp án:** Tìm exception đầu tiên trong static initializer hoặc lần khởi tạo class trước đó. Không mặc định đó là dependency JAR bị thiếu.

## 17. Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 Javadoc — ConditionalOnClass: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3.13 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 Javadoc — FilteredClassLoader: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.3.13 Javadoc — ConditionalOnBean: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3.13 Javadoc — ConditionalOnMissingBean: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Maven — Optional Dependencies and Dependency Exclusions: https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html
- Java SE 17 API — LinkageError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html
- Java SE 17 API — NoClassDefFoundError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html