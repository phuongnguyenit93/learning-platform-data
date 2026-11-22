# Bật báo cáo tự cấu hình bằng --debug hoặc debug=true

## 1. Báo cáo điều kiện dùng để làm gì?

Spring Boot Auto Configuration tự động quyết định cấu hình nào phù hợp với ứng dụng dựa trên classpath, bean đã đăng ký, property, web application type và nhiều điều kiện khác. Khi một bean hoặc một auto-configuration không xuất hiện như mong đợi, câu hỏi thường gặp là:

- Auto-configuration đó có được phát hiện không?
- `@ConditionalOnClass` có tìm thấy class cần thiết không?
- `@ConditionalOnProperty` có nhận đúng giá trị cấu hình không?
- `@ConditionalOnBean` có thấy bean phụ thuộc không?
- `@ConditionalOnMissingBean` có phát hiện bean do ứng dụng tự khai báo không?
- Vì sao một cấu hình được áp dụng hoặc bị bỏ qua?

Spring Boot cung cấp **Condition Evaluation Report** (báo cáo đánh giá điều kiện) để giải thích nhiều quyết định này. Có thể yêu cầu Spring Boot hiển thị báo cáo khi ứng dụng khởi động bằng một trong hai cách:

~~~bash
java -jar target/my-app.jar --debug
~~~

Hoặc khai báo property:

~~~properties
debug=true
~~~

Trong YAML:

~~~yaml
debug: true
~~~

Hai cách trên đều bật chế độ debug của Spring Boot, trong đó có báo cáo điều kiện tự cấu hình. Đây là công cụ chẩn đoán rất hữu ích khi phát triển starter, thư viện hoặc ứng dụng sử dụng nhiều auto-configuration.

**Điểm cần nhớ:** `--debug` hoặc `debug=true` bật báo cáo điều kiện và debug logging cho một nhóm logger lõi được Spring Boot lựa chọn. Chúng **không đồng nghĩa với việc đặt toàn bộ ứng dụng ở DEBUG**, không tự bật Java remote debugger và cũng không tự expose một endpoint HTTP.

## 2. Hai cách bật báo cáo

### 2.1. Dùng command-line argument --debug

Khi chạy JAR:

~~~bash
java -jar target/my-app.jar --debug
~~~

Có thể viết tường minh:

~~~bash
java -jar target/my-app.jar --debug=true
~~~

Đây là application argument theo cú pháp Spring Boot. Đảm bảo đối số được truyền tới tiến trình ứng dụng, không chỉ đặt thành một tham số cho Maven/Gradle mà plugin build không chuyển tiếp.

Với Maven Spring Boot Plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Trên Maven, có thể truyền nhiều application arguments trong cùng một chuỗi:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --acme.reports.enabled=true"
~~~

Với Gradle:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Trên Windows PowerShell, có thể dùng wrapper và dấu nháy kép:

~~~powershell
.\gradlew.bat bootRun --args="--debug"
~~~

Nếu chạy từ IDE, thêm `--debug` vào **Program arguments** của Run Configuration. Không đặt nó vào VM options: VM options dành cho JVM, còn `--debug` là argument của ứng dụng Spring Boot.

### 2.2. Dùng property debug=true

Trong `application.properties`:

~~~properties
debug=true
~~~

Trong `application.yml`:

~~~yaml
debug: true
~~~

Có thể đặt property trong file cấu hình theo profile, ví dụ `application-dev.yml`, nếu muốn bật chế độ này trong môi trường phát triển. Cần nhớ property có thể bị override bởi nguồn cấu hình có độ ưu tiên cao hơn.

Cũng có thể dùng:

~~~bash
java -jar target/my-app.jar --debug=false
~~~

để tắt chế độ được bật từ nguồn cấu hình thấp hơn, tùy theo thứ tự ưu tiên property sources. Command-line arguments của Spring Boot thường có độ ưu tiên cao hơn file application configuration.

### 2.3. Nên chọn cách nào?

| Nhu cầu | Cách nên dùng |
| --- | --- |
| Chẩn đoán nhanh một lần trên máy dev | Thêm `--debug` khi chạy |
| Bật mặc định cho profile phát triển | `debug=true` trong `application-dev.yml` |
| Kiểm tra ứng dụng đóng gói trên môi trường kiểm thử | Truyền `--debug` vào lệnh chạy JAR |
| Muốn bật/tắt theo lần triển khai | Dùng property hoặc command-line argument theo môi trường |
| Muốn toàn bộ package cụ thể có log DEBUG | Cấu hình `logging.level.<logger>` riêng |

Không nên để debug mode bật vô thời hạn trong môi trường production nếu không cần thiết: log có thể dài hơn và tiết lộ thêm thông tin cấu trúc ứng dụng. Hãy kiểm soát log và quyền truy cập như với các log vận hành khác.

## 3. Condition Evaluation Report hiển thị những gì?

Khi debug mode được bật, Spring Boot ghi ra báo cáo điều kiện của các auto-configuration đã tham gia quá trình đánh giá. Tùy phiên bản và loại cấu hình, báo cáo thường có các nhóm:

- **Positive matches:** các condition đã khớp. Ví dụ, class cần thiết có mặt, property có giá trị đúng hoặc chưa có bean thay thế.
- **Negative matches:** các condition không khớp. Đây thường là nơi đầu tiên cần xem khi bean mặc định không xuất hiện.
- **Exclusions:** các auto-configuration bị loại trừ tường minh.
- **Unconditional classes:** các cấu hình không cần điều kiện tương ứng.

Báo cáo có thể liệt kê cả kết quả ở cấp class auto-configuration và cấp method `@Bean`. Một class có thể được nạp nhưng một bean method bên trong bị condition loại; vì vậy cần đọc đúng tên class/method thay vì chỉ nhìn thấy tên class trong log.

### Ví dụ cách đọc một kết quả

Giả sử thư viện có bean mặc định:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@ConditionalOnMissingBean(ReportClient.class)
ReportClient reportClient() {
    return new ReportClient();
}
~~~

Nếu cấu hình là:

~~~yaml
acme:
  reports:
    enabled: false
~~~

Condition `@ConditionalOnProperty` không khớp. Báo cáo sẽ cho biết bean method không được đăng ký vì giá trị property không thỏa điều kiện. Cách diễn đạt/log line cụ thể thay đổi theo phiên bản, nhưng ý nghĩa cần tìm là:

~~~text
Negative matches:
   ReportsAutoConfiguration#reportClient
      - ConditionalOnProperty: acme.reports.enabled
        did not match (property value was not true)
~~~

Đây là **minh họa rút gọn để giải thích cấu trúc**, không phải bản chép nguyên văn log cố định của mọi phiên bản Spring Boot.

Nếu đổi property thành `true` và không có ReportClient do ứng dụng cung cấp, các condition phù hợp sẽ xuất hiện trong Positive matches:

~~~text
Positive matches:
   ReportsAutoConfiguration#reportClient
      - ConditionalOnProperty: acme.reports.enabled matched
      - ConditionalOnMissingBean: no ReportClient bean found
~~~

Nếu ứng dụng đã tự khai báo ReportClient, condition `@ConditionalOnMissingBean` không còn khớp; default bean được bỏ qua. Báo cáo giúp phân biệt trường hợp **feature bị tắt** với trường hợp **ứng dụng đã cung cấp bean thay thế**.

## 4. Quy trình đọc báo cáo theo vấn đề

Khi bean mong đợi không xuất hiện, hãy làm theo trình tự sau:

1. **Tìm đúng auto-configuration hoặc bean method.** Dùng tên class đầy đủ hoặc tên method `@Bean`; đừng suy luận từ một dòng log chung.
2. **Đọc Negative matches trước.** Tìm condition không khớp và lý do: thiếu class, sai property, bean prerequisite chưa có, web type không phù hợp hoặc bean thay thế đã tồn tại.
3. **Đọc Positive matches để xác nhận điều kiện nào đã đúng.** Một auto-configuration có nhiều condition; một condition đúng không có nghĩa mọi condition khác cũng đúng.
4. **Kiểm tra Exclusions.** Auto-configuration có thể bị loại bởi `exclude`, `excludeName`, `spring.autoconfigure.exclude` hoặc cơ chế loại trừ tương ứng.
5. **Kiểm tra cấu hình thực tế.** Đối chiếu key, giá trị, profile đang active, command-line arguments và environment variables. Báo cáo điều kiện cho biết kết quả đánh giá; nó không phải lúc nào cũng chỉ ra đầy đủ nguồn gốc mọi giá trị.
6. **Kiểm tra bean người dùng tự khai báo.** Một bean cùng kiểu có thể làm `@ConditionalOnMissingBean` không khớp. Điều đó có thể là hành vi mong muốn.
7. **Kiểm tra lỗi sau giai đoạn condition.** Condition có thể khớp nhưng bean vẫn lỗi khi khởi tạo do constructor dependency, exception trong factory method hoặc lỗi kết nối.

### Đọc theo loại condition

| Condition | Câu hỏi khi đọc báo cáo | Hướng xử lý thường gặp |
| --- | --- | --- |
| `@ConditionalOnClass` | Class yêu cầu có trong runtime classpath không? | Kiểm tra dependency scope, dependency bị exclude và phiên bản thư viện |
| `@ConditionalOnMissingClass` | Class nào đang có mặt khiến condition không khớp? | Kiểm tra classpath và mục đích của nhánh fallback |
| `@ConditionalOnProperty` | Property có tồn tại và có đúng giá trị mong đợi không? | Kiểm tra prefix, key, profile và nguồn override |
| `@ConditionalOnBean` | Bean prerequisite đã được đăng ký khi condition được xét chưa? | Kiểm tra ordering giữa auto-configuration và bean người dùng |
| `@ConditionalOnMissingBean` | Đã có bean cùng kiểu/tên khiến default nhường chỗ chưa? | Kiểm tra custom bean, kiểu trả về và phạm vi tìm kiếm |
| `@ConditionalOnWebApplication` | Ứng dụng có đúng web application type không? | Kiểm tra dependency web và application type |
| `@ConditionalOnResource` | Resource được yêu cầu có trên classpath không? | Kiểm tra đường dẫn và đóng gói resource |

**Một condition không khớp chưa chắc là lỗi.** Ví dụ, auto-configuration cung cấp default chỉ khi thiếu bean custom thì Negative match của `@ConditionalOnMissingBean` có thể là kết quả hoàn toàn đúng. Phải đối chiếu với mục tiêu thiết kế.

## 5. Ví dụ hoàn chỉnh chạy được: bật và đọc báo cáo điều kiện

Ví dụ dưới đây dùng Java 17+ và Spring Boot 3.3.5. Ta tạo một auto-configuration có điều kiện để có thể quan sát cả Positive và Negative matches.

### 5.1. Cấu trúc project

~~~text
condition-report-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/
    │   │   │   └── DemoApplication.java
    │   │   └── library/
    │   │       ├── ReportClient.java
    │   │       └── autoconfigure/
    │   │           └── ReportsAutoConfiguration.java
    │   └── resources/
    │       ├── application.yml
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/app/
            └── ReportsAutoConfigurationTest.java
~~~

Package ứng dụng là `com.example.app`; package thư viện giả lập là `com.example.library`. Nhờ tách package, component scan mặc định của ứng dụng không tự quét auto-configuration. Spring Boot phát hiện class thư viện qua resource `AutoConfiguration.imports`, đúng như khi thư viện được đóng gói thành JAR riêng.

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>condition-report-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 5.3. ReportClient.java

**src/main/java/com/example/library/ReportClient.java**

~~~java
package com.example.library;

public record ReportClient(String endpoint) {
    public String describe() {
        return "ReportClient endpoint=" + endpoint;
    }
}
~~~

Đây là một record Java 17, chỉ lưu endpoint để minh họa bean được tạo. Ví dụ không gửi HTTP request thật.

### 5.4. ReportsAutoConfiguration.java

**src/main/java/com/example/library/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.library.autoconfigure;

import com.example.library.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.invalid");
    }
}
~~~

Có hai condition:

- `@ConditionalOnProperty` chỉ cho phép đăng ký default client khi `acme.reports.enabled=true`. Property vắng mặt được xem là không khớp vì `matchIfMissing=false`.
- `@ConditionalOnMissingBean` chỉ đăng ký default nếu ứng dụng chưa cung cấp `ReportClient`.

### 5.5. Đăng ký auto-configuration

Tạo file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.library.autoconfigure.ReportsAutoConfiguration
~~~

Đây là tên class đầy đủ để Spring Boot phát hiện auto-configuration. Nếu thiếu resource này, class có thể không được xử lý qua cơ chế auto-configuration dù code Java đã compile thành công.

### 5.6. application.yml

**src/main/resources/application.yml**

~~~yaml
debug: false

acme:
  reports:
    enabled: false
~~~

Để bắt đầu, feature bị tắt. Ta sẽ bật báo cáo bằng command-line argument `--debug`, sau đó thay đổi giá trị feature để quan sát kết quả condition.

### 5.7. DemoApplication.java

**src/main/java/com/example/app/DemoApplication.java**

~~~java
package com.example.app;

import com.example.library.ReportClient;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner inspect(ObjectProvider<ReportClient> provider) {
        return args -> {
            ReportClient client = provider.getIfAvailable();
            System.out.println(
                    "reportClient=" +
                    (client == null ? "absent" : client.describe()));
        };
    }
}
~~~

Dùng `ObjectProvider` để demo có thể khởi động trong cả hai trường hợp: có hoặc không có ReportClient. Nếu inject trực tiếp `ReportClient` bắt buộc, ứng dụng sẽ fail startup khi property tắt và bean không tồn tại; khi đó khó quan sát kết quả Negative match bằng runner.

### 5.8. Chạy khi feature đang tắt

Từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Vì `application.yml` đặt `acme.reports.enabled=false`, Condition Evaluation Report sẽ cho thấy method `reportClient` không khớp điều kiện property. Dòng output của runner là:

~~~text
reportClient=absent
~~~

Trong log, tìm nhóm **Negative matches** và tên `ReportsAutoConfiguration#reportClient`. Bạn sẽ thấy condition `acme.reports.enabled` không thỏa. Chi tiết thông điệp có thể khác theo phiên bản và cách bind property.

### 5.9. Chạy khi bật feature

Truyền cả debug flag và property bật tính năng:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --acme.reports.enabled=true"
~~~

Kết quả runner:

~~~text
reportClient=ReportClient endpoint=https://reports.example.invalid
~~~

Lần này `@ConditionalOnProperty` khớp và `@ConditionalOnMissingBean` khớp vì chưa có bean thay thế. Tìm tên method `reportClient` trong nhóm **Positive matches** của Condition Evaluation Report.

Có thể chạy JAR đã đóng gói theo cách tương đương:

~~~bash
mvn package
java -jar target/condition-report-demo-1.0.0.jar --debug --acme.reports.enabled=true
~~~

Hai lệnh Maven ở trên là **hai lần chạy riêng biệt**: một lần để quan sát feature tắt và một lần để quan sát feature bật.

### 5.10. Kiểm tra custom bean làm default nhường chỗ

Trong ứng dụng thật, có thể tự cung cấp ReportClient. Khi đó `@ConditionalOnMissingBean` làm default bean không được đăng ký, dù feature đã bật.

Tạo class cấu hình tùy chỉnh (nếu muốn thử bằng ứng dụng chạy):

~~~java
package com.example.app;

import com.example.library.ReportClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CustomReportConfiguration {

    @Bean
    ReportClient customReportClient() {
        return new ReportClient("https://custom.example.invalid");
    }
}
~~~

Class nằm trong package `com.example.app`, nên được component scan của DemoApplication phát hiện. Chạy lại với:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --acme.reports.enabled=true"
~~~

Runner sẽ in:

~~~text
reportClient=ReportClient endpoint=https://custom.example.invalid
~~~

Trong báo cáo, `@ConditionalOnProperty` vẫn khớp nhưng `@ConditionalOnMissingBean` không khớp vì đã tìm thấy bean custom. **Đây không phải lỗi:** thư viện đang nhường quyền sở hữu bean cho ứng dụng đúng như contract.

Nếu đã thêm `CustomReportConfiguration`, hãy xóa class đó hoặc bỏ khỏi component scan khi muốn quay lại thí nghiệm default bean ở mục 5.9.

## 6. Test condition độc lập bằng ApplicationContextRunner

Báo cáo debug rất hữu ích để điều tra khi chạy ứng dụng, nhưng thư viện nên có test tự động cho các nhánh condition. Thêm dependency `spring-boot-starter-test` đã có trong POM.

**src/test/java/com/example/app/ReportsAutoConfigurationTest.java**

~~~java
package com.example.app;

import com.example.library.ReportClient;
import com.example.library.autoconfigure.ReportsAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenEnabled() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo(
                                    "https://reports.example.invalid");
                });
    }

    @Test
    void doesNotCreateClientWhenDisabled() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(ReportClient.class));
    }

    @Test
    void missingPropertyDoesNotEnableClient() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean(ReportClient.class));
    }

    @Test
    void backsOffWhenApplicationProvidesClient() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://custom.example.invalid");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {
        @Bean
        ReportClient customReportClient() {
            return new ReportClient("https://custom.example.invalid");
        }
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Kỳ vọng **bốn test pass**. Chúng kiểm tra property true, property false, property vắng mặt và custom bean. ApplicationContextRunner giúp kiểm tra auto-configuration riêng biệt mà không cần chạy toàn bộ ứng dụng hoặc bật debug logging trong mỗi test.

## 7. Phân biệt --debug với logging.level và Actuator

Ba cơ chế thường bị nhầm:

| Công cụ | Mục đích | Có tự bật Condition Evaluation Report không? |
| --- | --- | --- |
| `--debug` hoặc `debug=true` | Bật debug mode của Spring Boot và báo cáo điều kiện | **Có**, theo cơ chế báo cáo điều kiện của Boot |
| `logging.level.root=DEBUG` | Đặt mức log cho root logger | Không phải cách thay thế đáng tin cậy cho debug flag |
| `logging.level.com.example=DEBUG` | Bật log DEBUG cho package cụ thể | Không tự bật Condition Evaluation Report |
| Actuator `/actuator/conditions` | Endpoint quan sát điều kiện runtime khi Actuator/endpoint được cấu hình | Là cơ chế riêng, cần dependency và exposure/access phù hợp |

Ví dụ chỉ muốn log DEBUG cho package ứng dụng:

~~~yaml
logging:
  level:
    com.example: DEBUG
~~~

Điều này không tương đương với:

~~~yaml
debug: true
~~~

Ngược lại, `debug: true` cũng **không có nghĩa mọi logger trong ứng dụng đều ở DEBUG**. Spring Boot chọn một nhóm logger lõi để cung cấp thêm thông tin chẩn đoán. Nếu cần log chi tiết cho package riêng, cấu hình `logging.level` phù hợp bên cạnh debug flag.

### Actuator conditions endpoint

Nếu ứng dụng có Spring Boot Actuator và endpoint `conditions` được bật/expose, có thể truy vấn:

~~~text
/actuator/conditions
~~~

Endpoint này trình bày thông tin condition qua HTTP. Nó khác với báo cáo được ghi vào startup log khi dùng `--debug`. Không mặc định rằng thêm `debug=true` sẽ tự thêm Actuator, tự expose endpoint hoặc mở quyền truy cập. Trong production, chỉ expose endpoint cần thiết và bảo vệ quyền truy cập; báo cáo điều kiện có thể tiết lộ tên class, property và cấu trúc nội bộ.

## 8. Những gì báo cáo có và không có

**Báo cáo hữu ích để trả lời:**

- Auto-configuration đã được xét có condition nào khớp/không khớp?
- Bean method bị bỏ qua vì property nào hoặc bean thay thế nào?
- Một class cần thiết có mặt trên classpath không?
- Cấu hình có bị exclude không?
- Một auto-configuration đã được áp dụng vì điều kiện nào?

**Báo cáo không thay thế:**

- Stack trace khi bean constructor/factory method ném exception.
- Trace mọi lời gọi method trong ứng dụng.
- Debugger breakpoint hoặc remote JVM debugging.
- Phân tích đầy đủ nguồn gốc mọi property và mọi giá trị bí mật.
- Xác nhận một kết nối database/HTTP thực sự hoạt động.
- Test hành vi nghiệp vụ của bean sau khi khởi tạo.

Một auto-configuration có thể **match** nhưng bean vẫn fail khi khởi tạo vì dependency khác không giải quyết được. Ngược lại, condition không match có thể là thiết kế đúng: ví dụ user đã cung cấp bean thay thế. Hãy đọc báo cáo cùng với startup exception, dependency tree, cấu hình thực tế và test.

Nếu một auto-configuration hoàn toàn không xuất hiện trong báo cáo, hãy kiểm tra nó có trên classpath không, resource `AutoConfiguration.imports` có được đóng gói đúng không, class có bị exclude không và artifact có đúng phiên bản không. Báo cáo condition không thể giải thích chi tiết một class chưa bao giờ trở thành ứng viên được nạp.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra / sửa |
| --- | --- | --- |
| Chạy với `--debug` nhưng không thấy report | Argument chưa được truyền tới ứng dụng, hoặc đang xem sai log | Kiểm tra Run Configuration/Maven/Gradle arguments và startup output |
| Đặt `debug=true` nhưng command line có `--debug=false` | Nguồn command line override file cấu hình | Bỏ override hoặc truyền true |
| Bean không xuất hiện và Negative match nói property sai | Sai prefix/key, giá trị không đúng, profile khác hoặc nguồn override | Đối chiếu canonical key, property sources và active profiles |
| `@ConditionalOnMissingBean` không khớp | Ứng dụng/starter khác đã đăng ký bean phù hợp | Kiểm tra kiểu bean và xác định đây có phải hành vi mong muốn |
| Auto-configuration không thấy trong report | Không được phát hiện, thiếu resource/import hoặc bị exclude | Kiểm tra dependency, JAR resource và exclusion |
| Condition match nhưng startup vẫn lỗi | Lỗi xảy ra ở bước tạo bean hoặc dependency injection | Đọc stack trace gốc và constructor/factory method |
| Log quá dài | Bật debug trong môi trường nhiều auto-configuration | Chỉ bật khi cần, lưu log có kiểm soát và tắt sau chẩn đoán |
| Mong muốn log mọi class ở DEBUG | Hiểu nhầm debug flag là root logger DEBUG | Cấu hình `logging.level` cho package/logger cụ thể |
| Nghĩ `--debug` bật debugger | Nhầm debug log với JVM debugging | Dùng debugger/JPDA riêng nếu cần breakpoint |

## 10. Checklist chẩn đoán nhanh

Khi một bean do auto-configuration cung cấp không xuất hiện:

1. Chạy lại với `--debug` hoặc bật `debug=true`.
2. Tìm tên auto-configuration và bean method trong **Negative matches**.
3. Đọc condition đầu tiên không khớp; sửa đúng nguyên nhân, không sửa theo phỏng đoán.
4. Nếu property không đúng, kiểm tra canonical key, active profile, command-line args và environment variables.
5. Nếu bean prerequisite chưa có, kiểm tra classpath, thứ tự auto-configuration và `@ConditionalOnBean`.
6. Nếu default bean nhường chỗ, kiểm tra custom bean và `@ConditionalOnMissingBean`.
7. Nếu condition match nhưng startup lỗi, đọc stack trace và kiểm tra bước tạo bean.
8. Viết `ApplicationContextRunner` test cho nhánh đã sửa để tránh hồi quy.
9. Tắt debug sau khi chẩn đoán nếu môi trường không cần log đó thường xuyên.

Đừng bắt đầu bằng cách thêm `@Primary` hoặc thay đổi thứ tự dependency khi chưa biết condition nào thất bại. `@Primary` chỉ chọn ứng viên lúc inject; nó không làm cho một condition đăng ký bean tự khớp.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Muốn xem lý do auto-configuration khớp hoặc không khớp, dùng cách nào nhanh nhất?  
**Đáp án:** Chạy ứng dụng với `--debug` hoặc bật property `debug=true`, sau đó đọc Condition Evaluation Report.

**Câu 2.** `debug=true` có đặt mọi logger của ứng dụng thành DEBUG không?  
**Đáp án:** Không. Spring Boot bật debug logging cho một nhóm logger lõi được chọn và báo cáo điều kiện. Logger riêng cần `logging.level` nếu muốn chi tiết hơn.

**Câu 3.** Negative match của `@ConditionalOnMissingBean` có nhất thiết là lỗi không?  
**Đáp án:** Không. Có thể ứng dụng đã cung cấp bean tùy chỉnh nên default auto-configuration chủ động nhường chỗ.

**Câu 4.** Một condition đã match nhưng bean không khởi tạo được. Cần xem gì tiếp theo?  
**Đáp án:** Startup exception/stack trace, constructor dependency và factory method. Condition report không thay thế chẩn đoán lỗi khởi tạo.

**Câu 5.** `--debug` có tự mở `/actuator/conditions` không?  
**Đáp án:** Không. Endpoint đó thuộc Actuator, cần dependency, cấu hình exposure và quyền truy cập phù hợp.

**Câu 6.** Nếu class auto-configuration không hề xuất hiện trong báo cáo, nên kiểm tra gì?  
**Đáp án:** Dependency/classpath, file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, nội dung tên class và các cấu hình exclude.

**Ghi nhớ:** `--debug` và `debug=true` là hai cách bật chế độ chẩn đoán điều kiện của Spring Boot. Đọc **Positive matches**, **Negative matches** và **Exclusions** để biết vì sao auto-configuration được áp dụng hoặc bị bỏ qua; sau đó kiểm tra property, classpath, bean thay thế và startup exception. Dùng báo cáo để tìm nguyên nhân, rồi xác nhận cách sửa bằng test tự động.
