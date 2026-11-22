# Cung cấp ứng dụng tiêu thụ tối thiểu để xác nhận tự khám phá từ dependency

## 1. Mục tiêu: kiểm tra đường đi thực tế của một starter

Một thư viện Spring Boot starter có thể chứa auto-configuration để đăng ký bean mặc định cho ứng dụng sử dụng thư viện. Việc class auto-configuration tồn tại trong JAR **chưa chứng minh** Spring Boot đã khám phá và áp dụng nó.

Cách xác nhận đáng tin cậy là tạo **một ứng dụng tiêu thụ độc lập**:

1. Build và cài JAR starter vào Maven local repository hoặc publish vào repository nội bộ.
2. Khai báo starter như một dependency bình thường trong ứng dụng tiêu thụ.
3. Chỉ dùng @SpringBootApplication để khởi động; không @Import auto-configuration và không component-scan package của starter.
4. Inject bean mà starter cung cấp.
5. Chạy integration test hoặc ứng dụng thật và xác nhận hành vi của bean.

Bài này tạo hai project Maven tách biệt, dùng **Java 17+ và Spring Boot 3.3.13**:

- `greeting-spring-boot-autoconfigure`: thư viện cung cấp auto-configuration.
- `consumer-app`: ứng dụng nhỏ chỉ phụ thuộc vào JAR đã cài, sử dụng bean được khám phá tự động.

Bài test của consumer là bằng chứng quan trọng: nếu bỏ file đăng ký auto-configuration khỏi JAR hoặc dependency không được resolve đúng, context sẽ không tạo được `GreetingService` và test sẽ thất bại.

## 2. Cấu trúc hai project

Tạo hai thư mục ngang hàng:

~~~text
auto-configuration-demo/
├── greeting-spring-boot-autoconfigure/
│   ├── pom.xml
│   └── src/
│       └── main/
│           ├── java/com/acme/greeting/
│           │   ├── GreetingProperties.java
│           │   ├── GreetingService.java
│           │   └── autoconfigure/GreetingAutoConfiguration.java
│           └── resources/
│               └── META-INF/spring/
│                   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── consumer-app/
    ├── pom.xml
    └── src/
        ├── main/
        │   ├── java/com/acme/consumer/ConsumerApplication.java
        │   └── resources/application.yml
        └── test/
            └── java/com/acme/consumer/GreetingAutoDiscoveryTests.java
~~~

Package ứng dụng là `com.acme.consumer`, còn thư viện ở `com.acme.greeting`. Component scan mặc định của `@SpringBootApplication` chỉ quét package ứng dụng và các package con; nó không quét package sibling của starter. Vì vậy bean `GreetingService` xuất hiện trong consumer là bằng chứng cho đường khám phá auto-configuration.

## 3. Project thư viện: khai báo auto-configuration

### 3.1. POM của starter

Tệp `greeting-spring-boot-autoconfigure/pom.xml`:

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

    <groupId>com.acme</groupId>
    <artifactId>greeting-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>
    <name>Greeting Spring Boot Auto-configuration</name>

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
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
~~~

Thư viện cần `spring-boot-autoconfigure` cho annotation và cơ chế auto-configuration. `spring-boot-configuration-processor` là optional, giúp sinh metadata cho IDE khi dùng `@ConfigurationProperties`. Nếu starter cần API hoặc implementation của bên thứ ba, khai báo dependency tương ứng và cân nhắc dependency nào optional.

### 3.2. Lớp cấu hình properties

Tệp `src/main/java/com/acme/greeting/GreetingProperties.java`:

~~~java
package com.acme.greeting;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {

    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

Lớp nhận cấu hình từ các key bắt đầu bằng `acme.greeting`. Giá trị mặc định `Hello` được dùng nếu không có property `acme.greeting.prefix`. Việc đăng ký properties được thực hiện trong auto-configuration ở phần sau.

### 3.3. API mà consumer sẽ sử dụng

Tệp `src/main/java/com/acme/greeting/GreetingService.java`:

~~~java
package com.acme.greeting;

public class GreetingService {

    private final String prefix;

    public GreetingService(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

Đây là bean đơn giản để làm bằng chứng. Ứng dụng tiêu thụ không cần biết auto-configuration được triển khai trong package nào; nó chỉ phụ thuộc API `GreetingService`.

### 3.4. Auto-configuration tạo bean mặc định

Tệp `src/main/java/com/acme/greeting/autoconfigure/GreetingAutoConfiguration.java`:

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingProperties;
import com.acme.greeting.GreetingService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingProperties properties) {
        return new GreetingService(properties.getPrefix());
    }
}
~~~

Ba phần quan trọng:

- `@AutoConfiguration` đánh dấu lớp cấu hình tự động của starter.
- `@ConditionalOnProperty` bật tính năng khi `acme.greeting.enabled=true`; nếu property thiếu, `matchIfMissing=true` cho phép dùng mặc định.
- `@ConditionalOnMissingBean(GreetingService.class)` chỉ tạo bean mặc định khi ứng dụng chưa cung cấp bean tương thích. Nếu consumer tự định nghĩa `GreetingService`, auto-configuration sẽ back off.

`@EnableConfigurationProperties` đăng ký `GreetingProperties` để Spring bind cấu hình. Method `greetingService` nhận properties qua dependency injection và tạo service.

### 3.5. Đăng ký auto-configuration trong JAR

Tạo đúng file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung file chỉ có một dòng:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Đây là bước quyết định cho auto-discovery trong Spring Boot 3.3. Spring Boot đọc danh sách class từ resource này trên runtime classpath. Tên class phải đúng hoàn toàn, bao gồm package và chữ hoa/chữ thường.

**Không thay file này bằng component scan.** Starter không yêu cầu consumer quét package `com.acme.greeting`. Consumer cũng không cần tự viết `@Import(GreetingAutoConfiguration.class)`; nếu phải làm vậy thì ví dụ không còn chứng minh auto-discovery từ dependency.

Spring Boot 2.7+ và 3.x dùng file `AutoConfiguration.imports` để đăng ký auto-configuration. Cách đăng ký auto-configuration cũ qua `spring.factories` không còn là cơ chế đăng ký chính trong Boot 3.

## 4. Build và cài starter vào Maven local repository

Mở terminal ở thư mục `auto-configuration-demo` và chạy:

~~~bash
mvn -f greeting-spring-boot-autoconfigure/pom.xml clean install
~~~

Lệnh này biên dịch, đóng gói JAR và cài artifact `com.acme:greeting-spring-boot-autoconfigure:1.0.0` vào Maven local repository, thường là `~/.m2/repository`.

Sau khi build, kiểm tra JAR đã chứa class và file imports:

~~~bash
jar tf greeting-spring-boot-autoconfigure/target/greeting-spring-boot-autoconfigure-1.0.0.jar
~~~

Trong danh sách cần thấy các entry tương tự:

~~~text
com/acme/greeting/GreetingProperties.class
com/acme/greeting/GreetingService.class
com/acme/greeting/autoconfigure/GreetingAutoConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nếu file imports không nằm trong JAR, hãy kiểm tra vị trí resource và Maven resource packaging. File tồn tại trong source tree nhưng đặt sai thư mục sẽ không được Spring Boot đọc khi consumer chạy.

Nếu dùng repository nội bộ thay cho Maven local, publish đúng artifact/version vào repository đó và bảo đảm consumer có cấu hình repository tương ứng. Các bước sau không thay đổi: consumer chỉ khai báo dependency bình thường.

## 5. Project consumer: chỉ khai báo dependency

### 5.1. POM của ứng dụng tiêu thụ

Tệp `consumer-app/pom.xml`:

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

    <groupId>com.acme</groupId>
    <artifactId>consumer-app</artifactId>
    <version>1.0.0</version>
    <name>Minimal Auto-configuration Consumer</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>greeting-spring-boot-autoconfigure</artifactId>
            <version>1.0.0</version>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dependency quan trọng là `com.acme:greeting-spring-boot-autoconfigure:1.0.0`. Consumer không khai báo trực tiếp `spring-boot-autoconfigure`, không copy class của starter và không import auto-configuration bằng tay. Maven resolve starter JAR từ local repository hoặc repository đã publish.

### 5.2. Ứng dụng Spring Boot tối thiểu

Tệp `consumer-app/src/main/java/com/acme/consumer/ConsumerApplication.java`:

~~~java
package com.acme.consumer;

import com.acme.greeting.GreetingService;

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
    ApplicationRunner greetingCheck(GreetingService greetingService) {
        return args -> System.out.println(
                "AUTO_DISCOVERY_OK: " + greetingService.greet("Ada"));
    }
}
~~~

Đây là ứng dụng tiêu thụ hoàn chỉnh. Điểm cần giữ nguyên khi thử nghiệm:

- Chỉ có `@SpringBootApplication`; không có `@Import`.
- Không khai báo `@ComponentScan("com.acme.greeting")`.
- Package gốc là `com.acme.consumer`, tách biệt với package starter `com.acme.greeting`.
- `GreetingService` được inject vào `ApplicationRunner`. Nếu starter không được phát hiện hoặc condition không khớp, context sẽ không tạo được bean và ứng dụng không thể khởi động bình thường.

Runner in một dòng đánh dấu để dễ nhận biết ứng dụng đã sử dụng bean từ starter.

### 5.3. Property của consumer

Tệp `consumer-app/src/main/resources/application.yml`:

~~~yaml
acme:
  greeting:
    prefix: "Welcome"
~~~

Không khai báo `acme.greeting.enabled`. Starter dùng `matchIfMissing=true` nên tính năng mặc định được bật. Giá trị `prefix` được bind vào `GreetingProperties` và truyền cho `GreetingService`.

Khi chạy, dòng ứng dụng mong đợi là:

~~~text
AUTO_DISCOVERY_OK: Welcome, Ada!
~~~

Spring Boot có thể in banner và log startup trước hoặc sau dòng này tùy logging configuration; nội dung dòng đánh dấu do `ApplicationRunner` in ra là cố định với cấu hình trên.

## 6. Integration test ở phía consumer

Tạo tệp `consumer-app/src/test/java/com/acme/consumer/GreetingAutoDiscoveryTests.java`:

~~~java
package com.acme.consumer;

import com.acme.greeting.GreetingService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = ConsumerApplication.class)
class GreetingAutoDiscoveryTests {

    @Autowired
    ApplicationContext applicationContext;

    @Autowired
    GreetingService greetingService;

    @Test
    void starterBeanIsDiscoveredFromDependency() {
        assertThat(applicationContext.containsBean("greetingService"))
                .isTrue();

        assertThat(applicationContext.getBeansOfType(GreetingService.class))
                .hasSize(1);

        assertThat(greetingService.greet("Ada"))
                .isEqualTo("Welcome, Ada!");
    }
}
~~~

Test chạy trong project consumer, nơi starter chỉ được nhìn thấy như một dependency JAR. Nó không tự nạp cấu hình bằng `@Import`. Việc inject thành công `GreetingService`, tìm được bean theo tên và kiểm tra hành vi cuối là bằng chứng tích hợp rằng Spring Boot đã khám phá auto-configuration từ dependency.

Không nên chỉ test class `GreetingAutoConfiguration` bằng cách import trực tiếp vào `ApplicationContextRunner` rồi kết luận đã xác minh auto-discovery. Kiểu test đó hữu ích để kiểm tra logic condition riêng lẻ, nhưng bỏ qua bước đăng ký class từ resource `AutoConfiguration.imports`. Integration test trong consumer kiểm tra toàn bộ đường đi: đóng gói → dependency resolution → auto-discovery → bean registration → injection.

Chạy test từ project consumer:

~~~bash
mvn -f consumer-app/pom.xml clean verify
~~~

Kết quả mong đợi: `GreetingAutoDiscoveryTests` chạy thành công và có một test PASS. Nếu test thất bại ở bước inject, xem condition report và kiểm tra JAR trước khi sửa consumer bằng cách import class thủ công.

## 7. Chạy ứng dụng consumer như người dùng thư viện thật

Sau khi starter đã được cài và consumer đã build:

~~~bash
mvn -f consumer-app/pom.xml spring-boot:run
~~~

Hoặc đóng gói rồi chạy JAR:

~~~bash
mvn -f consumer-app/pom.xml clean package
java -jar consumer-app/target/consumer-app-1.0.0.jar
~~~

Dòng xác nhận mong đợi:

~~~text
AUTO_DISCOVERY_OK: Welcome, Ada!
~~~

Đây là smoke test qua đường khởi động ứng dụng thật. Nó xác nhận bean có thể được inject và dùng khi consumer chạy, ngoài phạm vi của một unit test condition.

Có thể kiểm tra dependency được resolve:

~~~bash
mvn -f consumer-app/pom.xml dependency:tree -Dincludes=com.acme:greeting-spring-boot-autoconfigure
~~~

Kết quả cần chỉ ra dependency `com.acme:greeting-spring-boot-autoconfigure:jar:1.0.0` trong dependency tree. Nếu Maven báo không tìm thấy artifact, hãy cài starter trước hoặc publish nó vào repository mà consumer đang dùng.

## 8. Phân biệt auto-discovery, component scan và @Import

| Cơ chế | Spring tìm class bằng cách nào? | Có chứng minh starter tự khám phá không? |
|---|---|---|
| `AutoConfiguration.imports` | Spring Boot đọc tên auto-configuration từ resource trong JAR trên classpath | **Có** |
| `@ComponentScan` | Quét package để tìm component/configuration | Không; có thể làm bean xuất hiện dù file imports bị thiếu |
| `@Import(GreetingAutoConfiguration.class)` | Ứng dụng tham chiếu trực tiếp class cấu hình | Không; consumer đang tự nạp cấu hình |
| `ApplicationContextRunner.withConfiguration(...)` | Test khai báo trực tiếp auto-configuration cần thử | Không tự chứng minh discovery từ dependency |
| `@SpringBootTest` trong consumer chỉ phụ thuộc JAR | Boot khởi động ứng dụng và đọc imports | **Có**, nếu package consumer không quét starter và không import class thủ công |

Một consumer test tốt phải cố ý **không** thêm component scan rộng như `@SpringBootApplication(scanBasePackages = "com.acme")`. Nếu scan cả `com.acme.greeting`, bean có thể xuất hiện từ component scan hoặc cấu hình được scan, khiến test không còn cô lập cơ chế imports.

Đây là lý do package consumer và starter được đặt ở hai nhánh sibling. Nó làm cho lỗi đăng ký imports dễ bộc lộ thay vì bị component scan che đi.

## 9. Kiểm tra điều kiện và tình huống back-off

Sau khi test đường tự khám phá cơ bản thành công, có thể kiểm tra hành vi starter theo điều kiện.

### 9.1. Tắt tính năng bằng property

Chạy consumer với:

~~~bash
mvn -f consumer-app/pom.xml spring-boot:run -Dspring-boot.run.arguments=--acme.greeting.enabled=false
~~~

Auto-configuration bị tắt bởi `@ConditionalOnProperty`. Trong consumer hiện tại không có user bean thay thế, vì vậy việc inject `GreetingService` sẽ thất bại khi tạo `ApplicationRunner`. Đây là hành vi dự kiến: tính năng đã bị tắt và không có bean nào cung cấp dependency đó.

Để test property disable mà không làm ứng dụng chính phụ thuộc bean, tạo test context riêng hoặc dùng `ApplicationContextRunner` trong project starter. Không kết luận “auto-discovery hỏng” chỉ vì người dùng đã chủ động đặt property tắt tính năng.

### 9.2. Ứng dụng cung cấp bean riêng

Nếu consumer định nghĩa bean `GreetingService` của riêng mình, `@ConditionalOnMissingBean(GreetingService.class)` sẽ làm bean mặc định back off khi user definition đã được xử lý trước auto-configuration. Điều này cho phép ứng dụng thay implementation theo hợp đồng starter mà không cần trùng tên bean.

Ví dụ cấu hình tùy chỉnh trong consumer:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomGreetingConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return new GreetingService("Hi");
    }
}
~~~

Đây là ví dụ mở rộng; nếu thêm vào consumer thì kết quả mong đợi của test phải đổi thành `Hi, Ada!`. Không giữ assertion `Welcome, Ada!` khi đã cố ý cung cấp bean thay thế.

### 9.3. Kiểm tra điều kiện bằng report

Khi bean không xuất hiện, chạy consumer với `--debug`:

~~~bash
mvn -f consumer-app/pom.xml spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Condition Evaluation Report giúp xem:

- `GreetingAutoConfiguration` có được xử lý hay không.
- `@ConditionalOnProperty` khớp hay không.
- `@ConditionalOnMissingBean` có back off do user bean không.
- Auto-configuration có bị exclude hay không.

Nếu cần dùng Actuator `conditions` endpoint, hãy expose có giới hạn và bảo vệ bằng Spring Security/network policy; report có thể tiết lộ classpath và cấu trúc cấu hình nội bộ. Không mở endpoint chẩn đoán ra public chỉ để kiểm tra starter.

## 10. Các lỗi thường gặp khi xác nhận auto-discovery

### 10.1. JAR không chứa AutoConfiguration.imports

**Triệu chứng:** class auto-configuration tồn tại trong source hoặc JAR, nhưng report không cho thấy nó được xử lý.

**Nguyên nhân:** file resource đặt sai đường dẫn, sai tên hoặc không được đóng gói.

**Kiểm tra:** dùng `jar tf` để xác nhận entry `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Kiểm tra class name trong file khớp package/class đã build.

### 10.2. Consumer dùng nhầm version starter

**Triệu chứng:** sửa starter nhưng consumer vẫn không thấy thay đổi.

**Nguyên nhân:** Maven local repository hoặc repository nội bộ còn artifact version cũ, consumer khai báo version khác, hoặc dependency mediation chọn version khác.

**Khắc phục:** build/install đúng version, kiểm tra `dependency:tree` và xác nhận JAR được resolve đúng. Trong môi trường nhóm, dùng version release/snapshot có quy trình rõ; không dựa vào việc overwrite một version release đã publish.

### 10.3. Component scan che lỗi imports

**Triệu chứng:** bean xuất hiện dù xóa file imports.

**Nguyên nhân:** consumer đang scan package starter hoặc dùng @Import trực tiếp.

**Khắc phục:** giới hạn package scan của consumer và bỏ import thủ công trong bài test auto-discovery. Giữ package sibling như ví dụ.

### 10.4. Class condition hoặc property condition không khớp

**Triệu chứng:** auto-configuration có được khám phá nhưng bean method không được đăng ký.

**Nguyên nhân:** dependency optional không có trên runtime classpath, property false, key sai hoặc matchIfMissing không đúng ý định.

**Khắc phục:** xem Condition Evaluation Report, effective property và dependency tree. Đừng thay bằng @Import để vượt qua condition; như vậy test không còn kiểm tra behavior thực.

### 10.5. User bean khiến default back off

**Triệu chứng:** auto-configuration xuất hiện trong report nhưng bean mặc định không có.

**Nguyên nhân:** @ConditionalOnMissingBean tìm thấy bean user đã đăng ký.

**Đánh giá:** thường là hành vi đúng. Kiểm tra bean nào được inject thay vì chỉ đếm bean default.

### 10.6. Test chỉ chạy trong module starter

**Triệu chứng:** ApplicationContextRunner test của starter PASS, nhưng consumer thật không thấy bean.

**Nguyên nhân:** test starter import auto-configuration trực tiếp, bỏ qua file imports và dependency packaging.

**Khắc phục:** giữ integration test riêng ở consumer project, phụ thuộc JAR starter đã cài và không import auto-configuration thủ công.

### 10.7. Dùng cơ chế đăng ký của Boot 2.x trong Boot 3.x

**Triệu chứng:** tài liệu cũ hướng dẫn khai báo auto-configuration trong `spring.factories` nhưng consumer Boot 3.3 không khám phá class.

**Nguyên nhân:** dùng nhầm cơ chế đăng ký auto-configuration cũ.

**Khắc phục:** đăng ký class trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Nếu thư viện phải hỗ trợ nhiều thế hệ Boot, thiết kế artifact/version và metadata tương thích có chủ đích thay vì copy file cũ máy móc.

### 10.8. Consumer không resolve được dependency

**Triệu chứng:** Maven báo `Could not find artifact com.acme:...`.

**Nguyên nhân:** starter chưa được install/publish, version không khớp hoặc consumer dùng repository khác.

**Khắc phục:** chạy `mvn clean install` ở project starter trước; sau đó chạy dependency tree ở consumer. Với CI, publish starter trước khi build integration consumer hoặc dùng reactor multi-module có thứ tự dependency rõ ràng.

## 11. Checklist hoàn tất

| Bước | Bằng chứng cần có | Hoàn thành khi |
|---|---|---|
| Build starter | Maven build thành công | Có JAR đúng version |
| Đóng gói metadata | Kết quả `jar tf` | JAR chứa file AutoConfiguration.imports |
| Đăng ký class | Nội dung imports | Đúng fully qualified class name |
| Resolve dependency | Maven dependency tree | Consumer lấy đúng artifact/version |
| Cô lập component scan | Package và annotation của consumer | Không scan starter, không @Import |
| Khởi động context | `@SpringBootTest` | Context khởi động và inject service |
| Kiểm tra hành vi | Assertion greeting | Giá trị `Welcome, Ada!` đúng |
| Chạy ứng dụng | Output của ApplicationRunner | Có dòng `AUTO_DISCOVERY_OK: Welcome, Ada!` |
| Kiểm tra điều kiện | Debug report khi cần | Hiểu class/property/bean condition |

Không coi riêng việc Maven compile thành công là bằng chứng auto-discovery. Compile chỉ chứng minh consumer có thể tham chiếu API trên classpath; nó không chứng minh Spring Boot đã đọc resource imports hoặc đăng ký bean.

## 12. Câu hỏi tự kiểm tra

1. Vì sao consumer test cần phụ thuộc JAR đã build/install thay vì import class auto-configuration trực tiếp? **Để kiểm tra toàn bộ đường đi đóng gói artifact, resolve dependency, đọc imports và đăng ký bean.**
2. File đăng ký auto-configuration của Boot 3.3 nằm ở đâu? **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
3. Consumer có cần @Import(GreetingAutoConfiguration.class) không? **Không.** Nếu phải import thủ công thì chưa chứng minh auto-discovery.
4. Vì sao package consumer và starter được đặt ở hai nhánh sibling? **Để component scan mặc định không quét starter, tránh che lỗi file imports.**
5. @ConditionalOnProperty matchIfMissing=true có ý nghĩa gì trong ví dụ? **Nếu acme.greeting.enabled không được khai báo, tính năng vẫn được bật.**
6. Khi consumer định nghĩa GreetingService riêng, bean default sẽ thế nào? **@ConditionalOnMissingBean làm auto-configuration back off nếu user bean đã được xử lý trước.**
7. ApplicationContextRunner import trực tiếp auto-configuration có chứng minh imports resource được đọc không? **Không.** Cần integration test trong consumer thực sự phụ thuộc JAR.
8. JAR có class GreetingAutoConfiguration nhưng thiếu AutoConfiguration.imports. Spring Boot có tự quét toàn bộ JAR để tìm class không? **Không.** Class cần được đăng ký theo cơ chế auto-configuration.
9. Maven build starter thành công nhưng consumer không resolve artifact. Kiểm tra gì? **Install/publish, version, repository và dependency:tree.**
10. Condition report cho biết default bean back off do user bean. Đó có nhất thiết là lỗi không? **Không.** Thường là hợp đồng tùy biến của starter hoạt động đúng.

## 13. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): đăng ký auto-configuration, file imports, ordering, conditions và kiểm thử.
- [Spring Boot 3.3 — AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): annotation đánh dấu auto-configuration.
- [Spring Boot 3.3 — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): hành vi back-off khi user bean đã có.
- [Spring Boot 3.3 — ConfigurationProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): bind cấu hình ngoài vào bean properties.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): ApplicationContextRunner và kiểm tra condition của auto-configuration.
