# Tách tích hợp bổ sung thành các cấu hình độc lập

> **Spring Boot Auto Configuration → Thư viện tự cấu hình.** Bài học giải thích cách chia một thư viện thành auto-configuration lõi và các auto-configuration tích hợp tùy chọn. Mục tiêu là để ứng dụng chỉ nạp tính năng cần dùng, giữ dependency tùy chọn khỏi core, kiểm soát thứ tự và điều kiện, tránh lỗi thiếu class khi thư viện bổ sung không có trên classpath, đồng thời kiểm thử từng tích hợp độc lập. Ví dụ dùng Java 17+, Maven và Spring Boot 3.3.x.

## 1. Vì sao cần tách tích hợp bổ sung?

Giả sử một thư viện thông báo có chức năng lõi là NoticeClient. Theo thời gian, người dùng muốn tích hợp thêm:
- Jackson để chuyển dữ liệu thông báo thành JSON.
- JDBC để lưu lịch sử gửi.
- Micrometer để ghi metrics.
- Kafka để phát sự kiện.
- SDK của nhà cung cấp để gửi thông báo thật.

Nếu dồn tất cả vào một lớp NoticeAutoConfiguration, thư viện dễ gặp các vấn đề:

1. Ứng dụng chỉ cần chức năng lõi nhưng phải kéo thêm Jackson, JDBC, Kafka hoặc SDK không dùng đến.
2. Thiếu một dependency bổ sung có thể khiến toàn bộ auto-configuration không load được, kể cả phần core vốn không cần dependency đó.
3. Một condition sai có thể vô tình chặn mọi bean, dù chỉ một tích hợp bị thiếu.
4. Cấu hình lõi và tích hợp có chu kỳ phát triển, phiên bản và yêu cầu bảo trì khác nhau.
5. Test khó phân biệt lỗi của core với lỗi của adapter.
6. Tài liệu bật/tắt và thứ tự cấu hình trở nên khó hiểu.

Thiết kế tốt thường chia theo **khả năng độc lập**:
- **Core auto-configuration:** cung cấp các bean nền, không phụ thuộc thư viện tích hợp tùy chọn.
- **Integration auto-configuration:** mỗi tích hợp có lớp cấu hình riêng, chỉ được áp dụng khi dependency và bean nền cần thiết có mặt.
- **Starter:** gom các artifact mà người dùng thường muốn sử dụng cùng nhau. Starter chủ yếu là dependency descriptor, không cần chứa logic cấu hình lớn.

Ví dụ kiến trúc:

~~~text
                  Ứng dụng Spring Boot
                           |
            +--------------+--------------+
            |              |              |
            v              v              v
       Core starter   JSON starter   JDBC starter
            |              |              |
            v              v              v
     core-autoconfig  json-autoconfig jdbc-autoconfig
            |              |              |
            +--------------+--------------+
                           |
                           v
                    Core API / Client
~~~

Mỗi integration được thêm riêng. Một ứng dụng chỉ dùng core có thể chỉ phụ thuộc core artifact; ứng dụng cần JSON thêm JSON integration; ứng dụng cần JDBC thêm JDBC integration.

**Tách cấu hình không chỉ là chia một class Java thành nhiều file.** Mục tiêu là tách đúng dependency, điều kiện, đăng ký auto-configuration, hợp đồng bean và kiểm thử.

## 2. Phân biệt core, integration và starter

| Thành phần | Trách nhiệm | Có nên phụ thuộc integration khác? |
| --- | --- | --- |
| Core API / core library | Các type và hành vi nền mà tính năng khác sử dụng | Không |
| Core auto-configuration | Tạo bean lõi và cấu hình mặc định | Không nên phụ thuộc thư viện tích hợp tùy chọn |
| Integration library | Adapter nối core với thư viện bên ngoài | Có thể phụ thuộc core và thư viện tương ứng |
| Integration auto-configuration | Tạo bean adapter khi đủ classpath, bean và property | Chỉ tham chiếu dependency thuộc integration đó |
| Starter | Gom dependency để người dùng cài đặt thuận tiện | Có thể gom core và một hoặc nhiều integration |
| Demo / application | Chọn các module thực sự cần | Tự quyết định integration nào được thêm |

Ví dụ đặt tên artifact:

~~~text
notice/
├── notice-core
├── notice-core-autoconfigure
├── notice-jackson
├── notice-jackson-autoconfigure
├── notice-jdbc
├── notice-jdbc-autoconfigure
├── notice-spring-boot-starter
└── notice-jackson-spring-boot-starter
~~~

Không phải dự án nào cũng cần tám artifact. Với thư viện nhỏ, có thể gộp core API và core auto-configuration; khi số lượng tích hợp tăng, tách module giúp kiểm soát dependency và version tốt hơn.

### 2.1. Core phải không biết integration tùy chọn

Core không nên import ObjectMapper, JdbcTemplate, KafkaTemplate hoặc class từ SDK bên ngoài nếu các thư viện đó không phải dependency bắt buộc của core.

Ví dụ core API:

~~~java
package demo.notice.core;

public final class NoticeClient {

    public String send(String message) {
        return "sent:" + message;
    }
}
~~~

Đây là type độc lập. Nó không biết dữ liệu sẽ được serialize bằng Jackson, lưu vào database hay phát qua Kafka. Các tích hợp bổ sung phụ thuộc vào core API và thực hiện vai trò adapter.

Lợi ích:
- Người dùng core không phải cài Jackson hoặc JDBC.
- Thay một thư viện JSON không buộc sửa core.
- Core có thể được kiểm thử mà không cần dựng database hoặc broker.
- Integration có thể được phát hành và nâng cấp riêng nếu hợp đồng tương thích.

### 2.2. Integration phụ thuộc core, không kéo ngược core vào integration

Một adapter JSON có thể dùng NoticeClient và Jackson:

~~~java
package demo.notice.jackson;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.NoticeClient;

public final class NoticeJsonFormatter {

    private final ObjectMapper objectMapper;
    private final NoticeClient noticeClient;

    public NoticeJsonFormatter(
            ObjectMapper objectMapper,
            NoticeClient noticeClient) {
        this.objectMapper = objectMapper;
        this.noticeClient = noticeClient;
    }

    public String format(String message) {
        try {
            return objectMapper.writeValueAsString(
                    new NoticePayload(
                            message,
                            noticeClient.send(message)
                    )
            );
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Cannot serialize notice payload",
                    exception
            );
        }
    }

    public record NoticePayload(String message, String delivery) {
    }
}
~~~

Đây là lớp adapter trong module JSON. Nó có thể sử dụng core và Jackson; core không cần biết NoticeJsonFormatter tồn tại.

## 3. Tách auto-configuration theo ranh giới tính năng

Một thư viện có thể khai báo nhiều lớp @AutoConfiguration. Mỗi lớp đại diện một nhóm bean có điều kiện và dependency tương đối độc lập.

~~~text
NoticeCoreAutoConfiguration
    └── NoticeClient

NoticeJacksonAutoConfiguration
    └── NoticeJsonFormatter

NoticeJdbcAutoConfiguration
    ├── NoticeHistoryRepository
    └── JDBC adapter

NoticeKafkaAutoConfiguration
    └── NoticeEventPublisher
~~~

Một lớp integration thường cần ba loại condition:

- @ConditionalOnClass: thư viện tích hợp có trên classpath.
- @ConditionalOnBean: bean nền mà adapter cần đã được đăng ký.
- @ConditionalOnProperty: người dùng có bật tính năng này hay không.

Có thể thêm @ConditionalOnMissingBean để cho phép ứng dụng tự cung cấp adapter thay thế.

Ví dụ khái quát:

~~~java
@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
@ConditionalOnBean(NoticeClient.class)
@ConditionalOnProperty(
        prefix = "demo.notice.json",
        name = "enabled",
        havingValue = "true"
)
public class NoticeJacksonAutoConfiguration {
    // Đăng ký các bean chỉ dành cho tích hợp Jackson.
}
~~~

Trong code thật, cần cân nhắc class nào có thể tham chiếu trực tiếp type tùy chọn. Phần 5 giải thích cách cô lập type tùy chọn an toàn.

### 3.1. Vì sao mỗi integration nên có condition riêng?

Nếu Jackson không có, chỉ NoticeJacksonAutoConfiguration nên không match. NoticeCoreAutoConfiguration vẫn có thể tạo NoticeClient.

Nếu người dùng tắt JSON bằng demo.notice.json.enabled=false, bean JSON không được tạo; core vẫn hoạt động.

Nếu người dùng tự cung cấp NoticeJsonFormatter, @ConditionalOnMissingBean cho phép auto-configuration nhường cho bean thay thế.

Đây là hành vi mong muốn: **một integration bị thiếu hoặc bị tắt không kéo theo việc tắt những tính năng độc lập khác**.

### 3.2. Đặt condition ở đúng phạm vi

Nếu condition nằm trên toàn lớp auto-configuration, tất cả bean được khai báo trong lớp chịu ảnh hưởng của condition đó. Nếu chỉ một bean cần dependency hoặc property riêng, có thể đặt condition ở method hoặc một lớp cấu hình lồng nhau.

Ví dụ một integration có hai bean:
- NoticeJsonFormatter cần Jackson.
- NoticeJsonMetrics cần Micrometer.

Không nên đặt @ConditionalOnClass cho Jackson trên một lớp bao trùm cả hai bean nếu điều đó khiến thiếu Jackson làm mất luôn metrics vốn không cần Jackson. Hãy tách thành hai nested configuration hoặc hai auto-configuration độc lập.

## 4. Đăng ký nhiều auto-configuration trong Spring Boot 3

Với Spring Boot 3.x, thư viện đăng ký auto-configuration trong file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi auto-configuration được ghi bằng tên lớp đầy đủ, mỗi dòng một class.

Core artifact:

~~~text
demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration
~~~

JSON integration artifact:

~~~text
demo.notice.jackson.autoconfigure.NoticeJacksonAutoConfiguration
~~~

Boot đọc các file imports trên classpath và tổng hợp candidate từ các artifact khác nhau. Vì thế mỗi module có thể đóng góp auto-configuration của chính nó.

Lưu ý:
- File phải nằm trong src/main/resources/META-INF/spring/.
- Tên package và class phải khớp chính xác.
- Một class có trong JAR nhưng không được đăng ký hoặc import thì không tự trở thành auto-configuration candidate.
- Khi build nhiều JAR, từng JAR có thể mang file imports riêng; cơ chế Boot đọc và kết hợp các file này.
- Không dùng thứ tự dòng trong file làm hợp đồng ordering; khai báo before / after tường minh khi cần.

### 4.1. Ordering giữa core và integration

Nếu JSON integration dùng bean NoticeClient, có thể khai báo:

~~~java
@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)
public class NoticeJacksonAutoConfiguration {
}
~~~

Khi cả hai cấu hình được tìm thấy, Boot xử lý core trước integration. Điều này đặc biệt quan trọng khi integration có @ConditionalOnBean(NoticeClient.class).

Ordering điều khiển thứ tự xử lý auto-configuration và đăng ký bean definition. Nó không thay thế dependency injection khi tạo instance; factory method vẫn nên nhận NoticeClient qua tham số.

### 4.2. Dùng afterName khi không muốn phụ thuộc compile-time

Nếu một integration có thể phụ thuộc một auto-configuration khác chỉ ở runtime, có thể dùng afterName / beforeName:

~~~java
@AutoConfiguration(
    afterName = "demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration"
)
public class OptionalAdapterAutoConfiguration {
}
~~~

Tên phải là fully qualified class name. Cách này tránh tham chiếu class trực tiếp, nhưng tên chuỗi cần được test vì trình biên dịch không kiểm tra chính tả.

### 4.3. Tránh vòng ordering

Không khai báo:
- A after B
- B after A

Đó là vòng ràng buộc thứ tự. Hãy vẽ dependency graph và chọn một hướng: integration phụ thuộc core, nên integration đứng sau core.

## 5. Cô lập class tùy chọn để không gây lỗi khi thiếu dependency

Đây là điểm dễ gây lỗi nhất khi tách integration.

Giả sử Jackson là tùy chọn. Nếu class core có method signature tham chiếu ObjectMapper, ứng dụng chỉ cài core có thể gặp lỗi load class trước khi condition có cơ hội loại cấu hình.

Không nên viết một lớp core như:

~~~java
@Configuration
class CoreConfiguration {

    @Bean
    NoticeJsonFormatter formatter(ObjectMapper mapper) {
        // ...
    }
}
~~~

nếu core không đảm bảo Jackson luôn có mặt.

### 5.1. Đặt class tham chiếu type tùy chọn trong module riêng

Cách rõ ràng nhất là:
- notice-core-autoconfigure chỉ tham chiếu core API và Spring Boot.
- notice-jackson-autoconfigure phụ thuộc core và Jackson.
- Ứng dụng chỉ cần core thì không thêm artifact JSON.

Khi JSON module không nằm trên classpath, class NoticeJacksonAutoConfiguration cũng không tồn tại trong runtime artifact; core không có bất kỳ reference nào đến nó.

### 5.2. Dùng @ConditionalOnClass với tên class và nested configuration

Trong module JSON, có thể viết:

~~~java
package demo.notice.jackson.autoconfigure;

import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.NoticeClient;
import demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration;
import demo.notice.jackson.NoticeJsonFormatter;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class NoticeJacksonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(NoticeClient.class)
    @ConditionalOnProperty(
            prefix = "demo.notice.json",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(NoticeJsonFormatter.class)
        NoticeJsonFormatter noticeJsonFormatter(
                ObjectMapper objectMapper,
                NoticeClient noticeClient) {

            return new NoticeJsonFormatter(objectMapper, noticeClient);
        }
    }
}
~~~

Đây là code của module JSON, module này có Jackson trên compile classpath nên import ObjectMapper hợp lệ. Outer auto-configuration kiểm tra classpath bằng tên chuỗi; nested configuration chứa method signature tham chiếu type tùy chọn và chỉ được xử lý khi điều kiện outer match.

Trong ví dụ thực tế, bổ sung import NoticeCoreAutoConfiguration nếu khác package. Đoạn code được trình bày để minh họa cách tổ chức; phần 7 cung cấp project đầy đủ với các import và package thống nhất.

### 5.3. Tránh đặt condition ở method nếu method signature đã cần type tùy chọn

Cách sau dễ gặp vấn đề:

~~~java
@Bean
@ConditionalOnClass(ObjectMapper.class)
NoticeJsonFormatter formatter(ObjectMapper mapper) {
    return new NoticeJsonFormatter(mapper);
}
~~~

Condition trên method không phải lúc nào cũng bảo vệ được việc JVM/Spring introspect kiểu tham số của method. Khi type có thể không tồn tại, hãy đặt condition ở cấp configuration và cô lập method trong class/nested configuration chỉ được xử lý sau khi condition classpath đã match.

### 5.4. Class literal và tên chuỗi

- @ConditionalOnClass(ObjectMapper.class) phù hợp khi class được tham chiếu an toàn trong module chứa annotation.
- @ConditionalOnClass(name = "...") dùng tên chuỗi, tránh resolve class literal khi metadata được đọc.
- Tách integration artifact là ranh giới mạnh nhất: core không cần biết type tùy chọn tồn tại hay không.

Không dùng @ConditionalOnClass như cách thay thế dependency management. Nếu integration thực sự cần Jackson để chạy, module integration phải khai báo dependency tương ứng; condition chỉ giúp auto-configuration không áp dụng khi môi trường thiếu class.

## 6. Optional dependency, integration artifact và starter

Có hai khái niệm dễ nhầm:

**Optional dependency** trong Maven mô tả dependency mà module hiện tại sử dụng nhưng không muốn tự động truyền cho mọi consumer theo cách mặc định. **Optional integration artifact** là một JAR riêng mà ứng dụng chỉ thêm khi muốn chức năng tích hợp đó.

Ví dụ:
- notice-core-autoconfigure không phụ thuộc Jackson.
- notice-jackson-autoconfigure phụ thuộc core và Jackson.
- notice-jackson-spring-boot-starter kéo core, JSON auto-config và Jackson.
- notice-spring-boot-starter chỉ kéo core nếu mục tiêu là starter tối giản.

Một starter có thể chỉ chứa POM:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo.notice</groupId>
    <artifactId>notice-jackson-spring-boot-starter</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-core-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-jackson-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Đây là POM minh họa cho starter do cùng một dự án phát hành. Nếu artifact JSON auto-config đã khai báo Jackson là dependency compile/runtime bắt buộc, dependency sẽ được kéo theo khi ứng dụng thêm module đó. Nếu muốn để ứng dụng tự chọn phiên bản Jackson, có thể cân nhắc dependency management/optional strategy nhưng phải bảo đảm runtime contract rõ ràng.

Không tạo một starter duy nhất kéo mọi integration nếu người dùng thường chỉ cần một phần nhỏ. Một lựa chọn là starter core và các starter chuyên biệt như notice-jackson-spring-boot-starter, notice-jdbc-spring-boot-starter.

## 7. Ví dụ multi-module hoàn chỉnh với core và Jackson integration

Lab dưới đây có ba Maven module:
1. notice-core-autoconfigure: cung cấp NoticeClient.
2. notice-jackson-autoconfigure: tích hợp Jackson và tạo NoticeJsonFormatter.
3. notice-demo: ứng dụng dùng cả hai module để quan sát kết quả.

Core module không phụ thuộc Jackson. Khi bỏ module JSON khỏi dependencies của ứng dụng, core vẫn chạy.

Yêu cầu: JDK 17+, Maven và kết nối để tải dependencies. Ví dụ dùng Spring Boot 3.3.13.

### 7.1. Cấu trúc thư mục

~~~text
notice-platform/
├── pom.xml
├── notice-core-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/notice/core/
│       │   ├── NoticeClient.java
│       │   └── autoconfigure/NoticeCoreAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── notice-jackson-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/notice/jackson/
│       │   ├── NoticeJsonFormatter.java
│       │   └── autoconfigure/NoticeJacksonAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── notice-demo/
    ├── pom.xml
    └── src/main/
        └── java/demo/app/NoticeDemoApplication.java
~~~

### 7.2. Parent pom.xml

Tệp notice-platform/pom.xml:

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
    <groupId>demo.notice</groupId>
    <artifactId>notice-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <properties>
        <java.version>17</java.version>
    </properties>
    <modules>
        <module>notice-core-autoconfigure</module>
        <module>notice-jackson-autoconfigure</module>
        <module>notice-demo</module>
    </modules>
</project>
~~~

Maven reactor build theo thứ tự dependency graph; thứ tự module trong POM không thay thế việc khai báo dependency giữa các module.

### 7.3. Core module pom.xml

Tệp notice-core-autoconfigure/pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.notice</groupId>
        <artifactId>notice-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>notice-core-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Không có dependency Jackson, JDBC hoặc Kafka trong core module. spring-boot-autoconfigure cung cấp các annotation và cơ chế auto-configuration cần thiết.

### 7.4. Core API: NoticeClient.java

Tệp notice-core-autoconfigure/src/main/java/demo/notice/core/NoticeClient.java:

~~~java
package demo.notice.core;

public final class NoticeClient {

    public String send(String message) {
        return "sent:" + message;
    }
}
~~~

Đây là core API đơn giản để lab có output xác định. Trong thư viện thật, class có thể quản lý queue hoặc giao tiếp với service, nhưng không nên phụ thuộc Jackson chỉ để adapter JSON có thể tồn tại.

### 7.5. NoticeCoreAutoConfiguration.java

Tệp notice-core-autoconfigure/src/main/java/demo/notice/core/autoconfigure/NoticeCoreAutoConfiguration.java:

~~~java
package demo.notice.core.autoconfigure;

import demo.notice.core.NoticeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class NoticeCoreAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeClient.class)
    NoticeClient noticeClient() {
        return new NoticeClient();
    }
}
~~~

Core mặc định bật khi không có property; đặt demo.notice.enabled=false sẽ tắt bean mặc định. Ứng dụng có thể tự cung cấp NoticeClient nếu cần thay thế.

### 7.6. Đăng ký core auto-configuration

Tệp notice-core-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports chứa:

~~~text
demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration
~~~

Tên class đầy đủ phải đúng từng ký tự. Nếu không có tệp này, Boot không tự tìm thấy core auto-configuration chỉ vì JAR đã nằm trên classpath.

### 7.7. JSON module pom.xml

Tệp notice-jackson-autoconfigure/pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.notice</groupId>
        <artifactId>notice-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>notice-jackson-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-core-autoconfigure</artifactId>
            <version>@@PROJECT_VERSION@@</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Jackson chỉ được thêm vào module integration. Core module không cần biết dependency này tồn tại.

### 7.8. NoticeJsonFormatter.java

Tệp notice-jackson-autoconfigure/src/main/java/demo/notice/jackson/NoticeJsonFormatter.java:

~~~java
package demo.notice.jackson;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.NoticeClient;

public final class NoticeJsonFormatter {

    private final ObjectMapper objectMapper;
    private final NoticeClient noticeClient;

    public NoticeJsonFormatter(
            ObjectMapper objectMapper,
            NoticeClient noticeClient) {
        this.objectMapper = objectMapper;
        this.noticeClient = noticeClient;
    }

    public String format(String message) {
        try {
            NoticePayload payload = new NoticePayload(
                    message,
                    noticeClient.send(message)
            );
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Cannot serialize notice payload",
                    exception
            );
        }
    }

    public record NoticePayload(String message, String delivery) {
    }
}
~~~

NoticeJsonFormatter là adapter. Nó kết hợp JSON serialization và core client, nhưng không đưa bất kỳ reference nào ngược về core.

### 7.9. NoticeJacksonAutoConfiguration.java

Tệp notice-jackson-autoconfigure/src/main/java/demo/notice/jackson/autoconfigure/NoticeJacksonAutoConfiguration.java:

~~~java
package demo.notice.jackson.autoconfigure;

import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.NoticeClient;
import demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration;
import demo.notice.jackson.NoticeJsonFormatter;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class NoticeJacksonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(NoticeClient.class)
    @ConditionalOnProperty(
            prefix = "demo.notice.json",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(NoticeJsonFormatter.class)
        NoticeJsonFormatter noticeJsonFormatter(
                ObjectMapper objectMapper,
                NoticeClient noticeClient) {
            return new NoticeJsonFormatter(objectMapper, noticeClient);
        }
    }
}
~~~

Có bốn điểm đáng chú ý:

1. @AutoConfiguration(after = NoticeCoreAutoConfiguration.class) đặt integration sau core.
2. @ConditionalOnClass(name = "...ObjectMapper") chỉ áp dụng integration khi Jackson có trên classpath.
3. Nested configuration yêu cầu NoticeClient và demo.notice.json.enabled=true.
4. @ConditionalOnMissingBean cho phép ứng dụng tự cung cấp NoticeJsonFormatter.

Vì class này nằm trong module JSON, compile dependency Jackson có mặt. Outer class dùng tên chuỗi trong condition; nested class giữ method signature cần ObjectMapper. Core module hoàn toàn không tham chiếu đến JSON type.

### 7.10. Đăng ký JSON auto-configuration

Tệp notice-jackson-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports chứa:

~~~text
demo.notice.jackson.autoconfigure.NoticeJacksonAutoConfiguration
~~~

Khi ứng dụng có cả hai JAR, Boot đọc hai imports files và tìm thấy hai cấu hình. Khi ứng dụng chỉ có core JAR, JSON auto-configuration không tồn tại trên classpath và không thể ảnh hưởng đến core.

### 7.11. Demo app pom.xml

Tệp notice-demo/pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.notice</groupId>
        <artifactId>notice-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>notice-demo</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-core-autoconfigure</artifactId>
            <version>@@PROJECT_VERSION@@</version>
        </dependency>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-jackson-autoconfigure</artifactId>
            <version>@@PROJECT_VERSION@@</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

spring-boot-starter-json cung cấp cấu hình Jackson và ObjectMapper cho ứng dụng. Integration module cung cấp formatter; nó không nên giả định ObjectMapper sẽ luôn có bean nếu ứng dụng không cài hạ tầng tạo mapper.

Nếu ứng dụng không cần JSON, bỏ dependency notice-jackson-autoconfigure và spring-boot-starter-json; core vẫn hoạt động.

### 7.12. NoticeDemoApplication.java

Tệp notice-demo/src/main/java/demo/app/NoticeDemoApplication.java:

~~~java
package demo.app;

import demo.notice.core.NoticeClient;
import demo.notice.jackson.NoticeJsonFormatter;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NoticeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NoticeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(
            ObjectProvider<NoticeClient> clients,
            ObjectProvider<NoticeJsonFormatter> formatters) {

        return args -> {
            NoticeClient client = clients.getIfAvailable();
            NoticeJsonFormatter formatter = formatters.getIfAvailable();

            System.out.println("core client present: " + (client != null));
            System.out.println("json formatter present: " + (formatter != null));

            if (formatter != null) {
                System.out.println(
                        "formatted: " + formatter.format("hello")
                );
            }
        };
    }
}
~~~

ObjectProvider được dùng vì integration là tùy chọn. ApplicationRunner vẫn chạy khi JSON module bị bỏ khỏi classpath hoặc property JSON bị tắt.

## 8. Build và quan sát từng tổ hợp integration

Từ thư mục notice-platform:

~~~bash
mvn -q clean package
~~~

### 8.1. Có core và JSON, bật JSON

Chạy:

~~~bash
java -jar notice-demo/target/notice-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.json.enabled=true
~~~

Stdout do chương trình in:

~~~text
core client present: true
json formatter present: true
formatted: {"message":"hello","delivery":"sent:hello"}
~~~

Core bean được tạo; JSON integration thấy core bean và ObjectMapper, property cho phép nên tạo formatter.

### 8.2. Có cả hai module nhưng tắt JSON

Chạy:

~~~bash
java -jar notice-demo/target/notice-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.json.enabled=false
~~~

Stdout:

~~~text
core client present: true
json formatter present: false
~~~

JSON integration không tạo formatter, nhưng core vẫn có. Đây là bằng chứng property của integration không tắt core.

### 8.3. Tắt core

Chạy:

~~~bash
java -jar notice-demo/target/notice-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.enabled=false --demo.notice.json.enabled=true
~~~

Stdout:

~~~text
core client present: false
json formatter present: false
~~~

JSON integration cần NoticeClient, nên condition @ConditionalOnBean không match. Không có core thì adapter không được tạo.

### 8.4. Chỉ dùng core, bỏ integration dependency

Trong notice-demo/pom.xml, xóa hai dependency:
- notice-jackson-autoconfigure
- spring-boot-starter-json

Giữ notice-core-autoconfigure và spring-boot-starter. Build lại:

~~~bash
mvn -q clean package
~~~

Chạy:

~~~bash
java -jar notice-demo/target/notice-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Stdout mong đợi sau khi thay source ứng dụng bằng bản core-only ở dưới:

~~~text
core client present: true
json formatter present: false
~~~

Application class ban đầu import NoticeJsonFormatter, nên nếu bỏ module JSON hoàn toàn, phải thay ứng dụng bằng phiên bản core-only dưới đây để source code không còn compile-time dependency đến type tùy chọn.

~~~java
package demo.app;

import demo.notice.core.NoticeClient;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NoticeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NoticeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ObjectProvider<NoticeClient> clients) {
        return args -> {
            NoticeClient client = clients.getIfAvailable();
            System.out.println("core client present: " + (client != null));
            System.out.println("json formatter present: false");
        };
    }
}
~~~

Đây là phiên bản source thay thế cho demo core-only. Nó chứng minh ứng dụng không cần import class từ module JSON khi integration bị bỏ khỏi dependency graph.

## 9. Kiểm thử từng cấu hình độc lập bằng ApplicationContextRunner

Test theo module giúp lỗi của integration không làm khó xác định lỗi core. Nên có các nhóm:
- Core test: bean core có được tạo theo property và back off khi user cung cấp bean.
- Integration test: formatter chỉ được tạo khi core, Jackson và property đều đáp ứng.
- Optional dependency test: thiếu class tùy chọn thì integration không match.
- User override test: bean do ứng dụng cung cấp được giữ lại.
- Starter test: khi ứng dụng dùng starter tổng hợp, toàn bộ các integration dự kiến có mặt.

Trong notice-demo/pom.xml, thêm dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 9.1. Test core độc lập

~~~java
package demo.notice;

import demo.notice.core.NoticeClient;
import demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeCoreAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeCoreAutoConfiguration.class
                    ));

    @Test
    void coreIsEnabledByDefault() {
        runner.run(context ->
                assertThat(context).hasSingleBean(NoticeClient.class)
        );
    }

    @Test
    void coreCanBeDisabled() {
        runner.withPropertyValues("demo.notice.enabled=false")
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(NoticeClient.class)
                );
    }

    @Test
    void userClientMakesCoreAutoConfigurationBackOff() {
        runner.withBean(
                NoticeClient.class,
                () -> new NoticeClient()
        ).run(context ->
                assertThat(context).hasSingleBean(NoticeClient.class)
        );
    }
}
~~~

Test này chỉ nạp core auto-configuration; nó không cần ObjectMapper, Jackson integration hay web server.

### 9.2. Test JSON integration

~~~java
package demo.notice;

import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration;
import demo.notice.jackson.NoticeJsonFormatter;
import demo.notice.jackson.autoconfigure.NoticeJacksonAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeJacksonAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withBean(ObjectMapper.class, ObjectMapper::new)
                    .withConfiguration(AutoConfigurations.of(
                            NoticeJacksonAutoConfiguration.class,
                            NoticeCoreAutoConfiguration.class
                    ));

    @Test
    void formatterIsCreatedWhenCoreJacksonAndPropertyArePresent() {
        runner.withPropertyValues("demo.notice.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeJsonFormatter.class);
                    NoticeJsonFormatter formatter =
                            context.getBean(NoticeJsonFormatter.class);
                    assertThat(formatter.format("hello"))
                            .isEqualTo(
                                "{\"message\":\"hello\",\"delivery\":\"sent:hello\"}"
                            );
                });
    }

    @Test
    void formatterIsSkippedWhenFeatureIsDisabled() {
        runner.withPropertyValues("demo.notice.json.enabled=false")
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(NoticeJsonFormatter.class)
                );
    }

    @Test
    void formatterIsSkippedWhenCoreIsDisabled() {
        runner.withPropertyValues(
                "demo.notice.enabled=false",
                "demo.notice.json.enabled=true"
        ).run(context ->
                assertThat(context)
                        .doesNotHaveBean(NoticeJsonFormatter.class)
        );
    }
}
~~~

AutoConfigurations.of(...) cố ý liệt kê integration trước core. Annotation after trên JSON auto-configuration diễn đạt quan hệ thứ tự; test kiểm tra kết quả cuối cùng thay vì dựa vào thứ tự dòng trong imports file.

Với Spring Boot 3.3.13 và Jackson, kỳ vọng 3 test JSON và 3 test core đều PASS. Nếu muốn kiểm tra thiếu Jackson class, có thể dùng FilteredClassLoader từ Spring Boot test để cô lập package Jackson; khi đó cần bảo đảm test chỉ tham chiếu integration class theo cách không buộc resolve optional type trước khi condition được đánh giá.

### 9.3. Vì sao test từng module quan trọng?

Nếu core test fail, vấn đề nằm ở core API, core condition hoặc bean definition. Nếu core test pass nhưng JSON test fail, điều tra:
- Jackson có trên test runtime classpath không?
- ObjectMapper có bean không?
- NoticeClient có được tạo không?
- demo.notice.json.enabled có đúng tên và giá trị không?
- JSON imports file có đúng FQCN không?
- Ordering có bảo đảm condition nhìn thấy core bean definition không?

Tách test theo module giúp chẩn đoán nhanh hơn và giảm số dependency cần khởi tạo cho mỗi test.

## 10. Những integration khác nên tách thế nào?

### 10.1. JDBC integration

Một NoticeJdbcAutoConfiguration nên nằm trong artifact JDBC riêng. Nó có thể cần:
- JdbcTemplate hoặc DataSource.
- @ConditionalOnClass(JdbcTemplate.class).
- @ConditionalOnBean(DataSource.class).
- @ConditionalOnProperty(prefix="demo.notice.jdbc", name="enabled", havingValue="true").
- @ConditionalOnMissingBean(NoticeHistoryRepository.class).

Không đưa JdbcTemplate hoặc DataSource vào core API nếu core không cần database. Ứng dụng chỉ dùng core/JSON không phải cài JDBC driver.

### 10.2. Kafka integration

Một NoticeKafkaAutoConfiguration có thể yêu cầu:
- Kafka client/Spring Kafka có trên classpath.
- KafkaTemplate hoặc producer bean cần thiết.
- Topic và serializer được cấu hình.
- Property riêng như demo.notice.kafka.enabled.

Nếu Kafka thiếu hoặc bị tắt, core vẫn chạy. Không để bean lõi có constructor bắt buộc nhận KafkaTemplate nếu Kafka chỉ là integration tùy chọn.

### 10.3. Metrics integration

Một NoticeMetricsAutoConfiguration có thể phụ thuộc Micrometer. Nó nên đăng ký meter binder hoặc listener riêng khi MeterRegistry có mặt. Core không cần import MeterRegistry nếu không bắt buộc ghi metrics.

### 10.4. Web integration

Một NoticeWebAutoConfiguration có thể tạo controller/endpoint hoặc converter khi Spring MVC/WebFlux có trên classpath. Nếu tích hợp dành cho MVC, không nên vô tình làm nó yêu cầu WebFlux; hãy kiểm tra classpath và application type cụ thể.

### 10.5. Bảng quyết định

| Tích hợp | Dependency thuộc module nào? | Condition điển hình | Core có cần biết? |
| --- | --- | --- | --- |
| Jackson JSON | notice-jackson-autoconfigure | ObjectMapper + NoticeClient + property | Không |
| JDBC history | notice-jdbc-autoconfigure | JdbcTemplate / DataSource + property | Không |
| Kafka publisher | notice-kafka-autoconfigure | KafkaTemplate + property | Không |
| Metrics | notice-metrics-autoconfigure | MeterRegistry + property | Không |
| MVC endpoint | notice-webmvc-autoconfigure | Spring MVC classpath + property | Không |

## 11. Thiết kế property và back-off cho từng integration

Mỗi tích hợp nên có namespace riêng để không xung đột:

~~~yaml
demo:
  notice:
    enabled: true
    json:
      enabled: true
    jdbc:
      enabled: false
    kafka:
      enabled: false
    metrics:
      enabled: true
~~~

Một số nguyên tắc:
- demo.notice.enabled điều khiển core.
- demo.notice.json.enabled điều khiển JSON adapter.
- demo.notice.jdbc.enabled điều khiển lưu lịch sử.
- demo.notice.kafka.enabled điều khiển publisher.
- Property của integration không nên âm thầm thay đổi hành vi core.
- Mặc định của từng integration cần được ghi trong metadata/README và kiểm thử riêng.

Khi core bị tắt, integration cần bean core cũng phải không match. Khi integration bị tắt, core không bị tắt theo. Đây là tính độc lập một chiều: integration phụ thuộc core, core không phụ thuộc integration.

### 11.1. @ConditionalOnMissingBean bảo vệ khả năng thay thế

~~~java
@Bean
@ConditionalOnMissingBean(NoticeJsonFormatter.class)
NoticeJsonFormatter noticeJsonFormatter(
        ObjectMapper mapper,
        NoticeClient client) {
    return new NoticeJsonFormatter(mapper, client);
}
~~~

Nếu ứng dụng đã cung cấp formatter riêng, auto-configuration không tạo formatter mặc định. Hãy khai báo return type cụ thể để condition theo type có thể đánh giá chính xác.

Back-off chỉ quyết định có tạo bean mặc định hay không. Nó không xóa bean user, không tự sửa dependency của bean user và không đảm bảo bean user hoạt động đúng.

### 11.2. Tránh property của integration đặt trên core class

Không nên đặt @ConditionalOnProperty(prefix="demo.notice.json", ...) trên NoticeCoreAutoConfiguration nếu chỉ JSON cần được bật/tắt. Làm vậy sẽ khiến thiếu hoặc tắt JSON làm mất luôn NoticeClient.

Hãy đặt property condition trên đúng auto-configuration hoặc nested configuration của JSON.

## 12. Tổ chức dependency và version giữa các module

Khi phát hành nhiều artifact, cần giữ version tương thích:

- Core API và core auto-configuration phải tương thích với nhau.
- JSON integration phải khai báo dải version core mà nó hỗ trợ.
- Starter nên quản lý version các artifact nội bộ thống nhất.
- Dependency của thư viện bên ngoài nên được quản lý bằng Spring Boot BOM hoặc BOM riêng.
- Không để integration kéo một version core khác gây duplicate class hoặc binary incompatibility.

Một dự án có thể dùng parent POM để quản lý version nội bộ. Khi phát hành cho người dùng bên ngoài, có thể cung cấp BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó consumer khai báo dependency mà không lặp version nếu BOM đã quản lý chúng. Đây là cấu hình dependency management minh họa; BOM phải được phát hành riêng và liệt kê các artifact/version tương ứng.

Không nên tăng version core tùy tiện mà không test integrations. Một thay đổi public API ở core có thể ảnh hưởng toàn bộ adapter; cần chạy test matrix giữa các module trước khi phát hành.

## 13. Lỗi thường gặp khi tách integration

1. **Để core import class tùy chọn.** Ứng dụng không cài integration vẫn có thể gặp lỗi load class.
2. **Chỉ chia class nhưng vẫn giữ mọi dependency trong một artifact.** Dependency graph không thay đổi, người dùng vẫn phải kéo thư viện không cần.
3. **Quên đăng ký integration trong AutoConfiguration.imports.** JAR có class nhưng Boot không tự nạp cấu hình.
4. **Sai FQCN trong imports.** Auto-configuration không được phát hiện.
5. **Condition trên method nhưng optional type nằm trong method signature.** Class có thể bị introspect trước khi condition method bảo vệ được nó.
6. **Đặt condition integration trên core.** Tắt một adapter làm mất bean lõi.
7. **Không dùng after khi condition phụ thuộc bean của auto-configuration khác.** @ConditionalOnBean có thể được đánh giá trước khi bean nền được đăng ký.
8. **Dùng ordering thay cho dependency injection.** Ordering giúp condition nhìn thấy definition; injection vẫn cần thể hiện dependency khi tạo instance.
9. **Thiếu @ConditionalOnMissingBean.** User khó thay adapter mặc định và có thể gặp nhiều bean cùng type.
10. **Không kiểm thử trường hợp dependency vắng mặt.** Integration có thể hoạt động khi đủ classpath nhưng làm core lỗi khi thiếu thư viện tùy chọn.
11. **Starter kéo tất cả integrations.** Ứng dụng nhỏ phải cài nhiều dependency không cần thiết.
12. **Tất cả integrations dùng chung một property enabled.** Người dùng không thể tắt một adapter riêng mà giữ core và các adapter khác.
13. **Core API chứa type của thư viện ngoài.** Dependency tùy chọn trở thành dependency bắt buộc ở public API.
14. **Không kiểm tra runtime classpath.** Build/test trong IDE có dependency nhưng executable JAR/container lại thiếu.
15. **Không đồng bộ version giữa các module.** Adapter có thể gọi API không tồn tại trong version core được resolve.
16. **Tạo vòng phụ thuộc module.** Core phụ thuộc integration trong khi integration lại phụ thuộc core; cần giữ dependency một chiều.
17. **Cho rằng thiếu integration đồng nghĩa thiếu core.** Nếu tách đúng, core hoạt động độc lập.
18. **Không phân biệt auto-configuration với starter.** Auto-configuration chứa logic tạo bean; starter chủ yếu gom dependencies.
19. **Dùng component scan để đăng ký mọi integration.** Thư viện Boot 3 nên dùng AutoConfiguration.imports; component scan có thể làm cấu hình xuất hiện ngoài dự kiến.
20. **Chỉ test context khởi động.** Cần assert bean nào có/vắng theo từng module và property, không chỉ kiểm tra startup thành công.

## 14. Quy trình thực tế khi tách một integration khỏi auto-configuration lớn

1. **Liệt kê bean và dependency:** ghi rõ bean nào thuộc core, bean nào chỉ phục vụ integration.
2. **Xác định chiều phụ thuộc:** integration dùng core; core không tham chiếu integration.
3. **Tách source/package/artifact:** chuyển adapter và cấu hình riêng sang module integration.
4. **Tách dependency:** dependency bên ngoài chỉ nằm trong module cần nó.
5. **Tạo imports file:** mỗi auto-configuration được đăng ký đúng một lần trong artifact sở hữu nó.
6. **Đặt condition:** classpath, bean nền và property của integration.
7. **Khai báo ordering:** dùng after khi condition phụ thuộc bean do core auto-configuration đăng ký.
8. **Giữ back-off:** cho phép user thay adapter bằng @ConditionalOnMissingBean.
9. **Tách test:** core-only, integration-on, integration-off, missing dependency và user override.
10. **Kiểm tra dependency tree và executable artifact:** xác nhận core-only không kéo thư viện tùy chọn.
11. **Cập nhật starter và metadata:** người dùng biết dependency nào bật integration nào.
12. **Chạy compatibility tests:** bảo đảm version core và từng integration tương thích.

## 15. Checklist trước khi phát hành thư viện nhiều integration

- [ ] Core API không tham chiếu type từ integration tùy chọn.
- [ ] Core auto-configuration chỉ tạo bean nền.
- [ ] Mỗi integration có auto-configuration độc lập.
- [ ] Dependency ngoài chỉ được khai báo trong module thực sự cần nó.
- [ ] Mỗi artifact có AutoConfiguration.imports với FQCN chính xác.
- [ ] Condition classpath bảo vệ đúng module và không chặn core.
- [ ] Condition bean xác định dependency nền cần có.
- [ ] Property riêng điều khiển từng integration.
- [ ] Ordering after / before phản ánh dependency giữa auto-configuration.
- [ ] Bean mặc định có @ConditionalOnMissingBean khi cần hỗ trợ override.
- [ ] Optional class được cô lập để thiếu class không làm hỏng core.
- [ ] Core-only test không cần dependency integration.
- [ ] Integration test có các ca enabled, disabled, core missing và user override.
- [ ] Starter chỉ kéo những integration mà người dùng thực sự muốn.
- [ ] Version core/integration được quản lý nhất quán.
- [ ] Executable JAR/container được kiểm tra runtime dependency.
- [ ] README và configuration metadata mô tả đúng property, default và artifact cần cài.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng chỉ cần core nhưng không có Jackson. Thiết kế nào giúp ứng dụng vẫn chạy?  
**Đáp án:** Core API và core auto-configuration không tham chiếu Jackson; JSON adapter nằm trong artifact riêng và chỉ được thêm khi cần.

**Câu 2.** Vì sao NoticeJacksonAutoConfiguration cần @ConditionalOnClass?  
**Đáp án:** Để integration chỉ được áp dụng khi Jackson có trên runtime classpath; thiếu thư viện JSON không làm core bị lỗi.

**Câu 3.** Vì sao nên dùng @AutoConfiguration(after = NoticeCoreAutoConfiguration.class)?  
**Đáp án:** Integration có thể dùng @ConditionalOnBean(NoticeClient.class) và cần core bean definition được xử lý trước.

**Câu 4.** Tắt demo.notice.json.enabled có nên làm NoticeClient biến mất không?  
**Đáp án:** Không. Property JSON chỉ điều khiển JSON integration; core có property riêng.

**Câu 5.** @ConditionalOnMissingBean(NoticeJsonFormatter.class) bảo vệ điều gì?  
**Đáp án:** Cho phép ứng dụng tự cung cấp formatter; auto-configuration không tạo formatter mặc định khi bean phù hợp đã có.

**Câu 6.** Tại sao không nên đặt ObjectMapper trong API của core?  
**Đáp án:** Làm Jackson trở thành dependency của core và khiến ứng dụng chỉ dùng core phải biết thư viện JSON.

**Câu 7.** Starter khác auto-configuration ở điểm nào?  
**Đáp án:** Starter chủ yếu gom dependency để người dùng cài đặt; auto-configuration chứa logic đăng ký bean có điều kiện.

**Câu 8.** Nếu integration thiếu class nhưng condition đặt trên method có signature dùng class đó, rủi ro là gì?  
**Đáp án:** Spring/JVM có thể cần introspect method signature trước khi condition method bảo vệ được nó. Nên cô lập type trong cấu hình riêng có condition classpath ở cấp lớp.

## 17. Kết luận và tài liệu tham khảo

Tách integration thành các cấu hình độc lập giúp core giữ dependency nhỏ, adapter được bật theo classpath/bean/property, và mỗi tính năng có thể được phát triển, kiểm thử và phát hành riêng. Dependency graph nên đi một chiều: **integration phụ thuộc core; core không phụ thuộc integration**. Với từng auto-configuration, hãy giữ imports, condition, ordering và back-off đúng phạm vi.

Tài liệu chính thức:
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot Reference — Auto-configuration Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).
- [Spring Boot Javadoc — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
- [Spring Boot Javadoc — ConditionalOnClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html).
- [Spring Boot Javadoc — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)