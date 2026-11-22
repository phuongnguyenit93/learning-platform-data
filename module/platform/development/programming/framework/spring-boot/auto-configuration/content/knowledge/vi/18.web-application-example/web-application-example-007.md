# Dùng ứng dụng không web để kiểm chứng cấu hình web không bị kích hoạt

## 1. Mục tiêu và tình huống sử dụng

Một dự án Spring Boot có thể chứa dependency web nhưng vẫn cần chạy như **ứng dụng nền (batch), command-line hoặc worker**. Ví dụ:
- Job đọc dữ liệu, xử lý và ghi kết quả theo lịch.
- Consumer nhận message từ broker, xử lý rồi kết thúc.
- Công cụ nhập/xuất dữ liệu chạy bằng lệnh.
- Ứng dụng dùng thư viện web để gọi HTTP ra ngoài nhưng không cung cấp HTTP endpoint cho người dùng.

Trong các trường hợp đó, cần xác minh Spring Boot tạo **ApplicationContext không web** và các auto-configuration chỉ dành cho servlet/reactive web không được áp dụng.

Bài học tập trung vào ba việc:

1. Phân biệt **có thư viện web trên classpath** với **ứng dụng đang chạy ở chế độ web**.
2. Chọn `WebApplicationType.NONE` hoặc property tương ứng để tạo non-web context.
3. Kiểm chứng `@ConditionalOnWebApplication` và `@ConditionalOnNotWebApplication` bằng test và báo cáo condition.

Ví dụ sử dụng **Spring Boot 3.5.x, Java 17+**. Khi áp dụng cho phiên bản khác, hãy đối chiếu API và package đúng version.

## 2. Classpath web không đồng nghĩa ứng dụng web

Khi thêm `spring-boot-starter-web`, classpath thường có Spring MVC, Servlet API và embedded server (ví dụ Tomcat). Theo mặc định, Spring Boot dò classpath để quyết định `WebApplicationType`; với MVC hiện diện, ứng dụng thường được chọn là **SERVLET**.

Tuy nhiên, nếu cùng một codebase cần chạy worker/batch, có thể chủ động chọn **NONE**. Khi đó Spring Boot tạo context không web, dù các class servlet/MVC vẫn tồn tại trong JAR.

Ba loại chính:

| `WebApplicationType` | Loại context | Mục đích |
| --- | --- | --- |
| `SERVLET` | Servlet `WebApplicationContext` | Ứng dụng MVC/Servlet |
| `REACTIVE` | Reactive web context | Ứng dụng WebFlux |
| `NONE` | Context thông thường, không web | Batch, CLI, worker, scheduler |

**Điểm quan trọng:** `WebApplicationType.NONE` không gỡ Spring MVC, Servlet API hay Tomcat khỏi classpath. Nó chọn loại ApplicationContext mà ứng dụng sẽ sử dụng, từ đó các web condition đánh giá theo loại context và môi trường thực tế.

Spring Boot Reference giải thích rằng nếu classpath đủ thành phần để chạy web server thì server thường được tự động khởi động; có thể tắt hành vi này bằng `spring.main.web-application-type=none`. Xem [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html).

## 3. Các condition dành cho ứng dụng web

Spring Boot cung cấp hai annotation chính:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
~~~

### 3.1. @ConditionalOnWebApplication

Điều kiện match khi ứng dụng được nhận diện là web application. Có thể giới hạn loại:

~~~java
@ConditionalOnWebApplication
class AnyWebConfiguration {
}

@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
class ServletOnlyConfiguration {
}

@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE)
class ReactiveOnlyConfiguration {
}
~~~

Đây là ba ví dụ lựa chọn độc lập:
- Không truyền `type`: áp dụng cho web application nói chung, gồm servlet hoặc reactive.
- `SERVLET`: chỉ yêu cầu servlet web application.
- `REACTIVE`: chỉ yêu cầu reactive web application.

### 3.2. @ConditionalOnNotWebApplication

Điều kiện match khi context không được nhận diện là web application:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
class WorkerOnlyConfiguration {

    @Bean
    WorkerService workerService() {
        return new WorkerService();
    }
}
~~~

Đây là cấu hình phù hợp cho bean chỉ nên xuất hiện trong batch/CLI/worker. Nếu một ứng dụng được khởi động bằng servlet hoặc reactive context, cấu hình này không match.

### 3.3. Spring nhận diện web application như thế nào?

Theo Spring Boot 3.5 Reference, servlet-based web application được nhận diện qua một trong các dấu hiệu như:
- Context là `WebApplicationContext`;
- Có session scope;
- Environment là `ConfigurableWebEnvironment`.

Reactive web application được nhận diện qua:
- Context là `ReactiveWebApplicationContext`;
- Hoặc environment là `ConfigurableReactiveWebEnvironment`.

Do đó, condition dựa trên **loại ApplicationContext/Environment**, không chỉ dựa vào việc có class `DispatcherServlet` hay `WebClient` trên classpath. Xem [Spring Boot 3.5 — Condition Annotations](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html).

## 4. Chọn WebApplicationType.NONE trong Java

Cách tường minh nhất là tạo `SpringApplication` rồi đặt loại ứng dụng trước khi gọi `run`:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
~~~

**Thứ tự có ý nghĩa:** phải đặt `WebApplicationType.NONE` trước `run(args)`, vì Boot cần biết loại context trong lúc chuẩn bị khởi động.

Có thể dùng `SpringApplicationBuilder`:

~~~java
new SpringApplicationBuilder(BatchApplication.class)
        .web(WebApplicationType.NONE)
        .run(args);
~~~

Cách này hữu ích khi cần dựng parent/child context hoặc cấu hình bằng fluent API.

## 5. Chọn NONE bằng application.properties hoặc YAML

Không phải lúc nào cũng muốn sửa Java code. Có thể đặt property trong `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
~~~

Hoặc trong `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Có thể truyền khi khởi động:

~~~bash
java -jar target/batch-app.jar --spring.main.web-application-type=none
~~~

Với Maven Spring Boot Plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments="--spring.main.web-application-type=none"
~~~

Trên Windows PowerShell với Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run '-Dspring-boot.run.arguments=--spring.main.web-application-type=none'
~~~

Nếu cùng property được khai báo ở nhiều nguồn, Spring Environment áp dụng quy tắc ưu tiên nguồn cấu hình. Đối số ứng dụng `--spring.main.web-application-type=none` thường có độ ưu tiên cao hơn property trong file.

**Chọn một cách làm chủ đạo** cho mỗi ứng dụng. Nếu code đã gọi `setWebApplicationType`, tránh cấu hình rải rác nhiều nguồn khiến người vận hành khó biết loại context thực tế.

## 6. Phân biệt NONE với server.port=-1

Đây là lỗi cấu hình phổ biến.

| Cấu hình | Loại ApplicationContext | Có web server lắng nghe HTTP? | Web condition |
| --- | --- | --- | --- |
| `spring.main.web-application-type=none` | Non-web context | Không | `@ConditionalOnWebApplication` không match |
| `server.port=-1` | Vẫn là web context | Không mở HTTP port | Web condition vẫn có thể match |
| `server.port=0` | Web context | Có server, dùng port ngẫu nhiên | Web condition match nếu các điều kiện khác đạt |

Nếu chỉ muốn tắt listener nhưng vẫn cần `WebApplicationContext`, `server.port=-1` là lựa chọn phù hợp. Nếu muốn xác minh **cấu hình web không được kích hoạt**, hãy chọn `WebApplicationType.NONE`.

Spring Boot Reference nêu rõ `server.port=-1` tắt HTTP endpoint nhưng vẫn tạo `WebApplicationContext`; do đó nó không tương đương NONE. Xem [Embedded Web Servers — Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html).

## 7. Ví dụ chạy được: cùng classpath web, chạy ứng dụng batch không web

Ví dụ sau cố ý dùng `spring-boot-starter-web` để chứng minh classpath có MVC/Servlet nhưng ứng dụng vẫn có thể chạy non-web khi chọn NONE.

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>non-web-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Cố ý có đầy đủ Spring MVC và embedded server trên classpath. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 7.2. Mã ứng dụng

Tạo `src/main/java/example/BatchApplication.java`:

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.context.WebApplicationContext;

@SpringBootApplication(proxyBeanMethods = false)
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    @ConditionalOnWebApplication(
            type = ConditionalOnWebApplication.Type.SERVLET)
    WebFeature webFeature() {
        return new WebFeature();
    }

    @Bean
    @ConditionalOnNotWebApplication
    BatchFeature batchFeature() {
        return new BatchFeature();
    }

    @Bean
    CommandLineRunner reportContextMode(
            ConfigurableApplicationContext context) {

        return args -> {
            System.out.println(
                    "WEB_APPLICATION_CONTEXT="
                            + (context instanceof WebApplicationContext));

            System.out.println(
                    "WEB_FEATURE_PRESENT="
                            + context.containsBean("webFeature"));

            System.out.println(
                    "BATCH_FEATURE_PRESENT="
                            + context.containsBean("batchFeature"));
        };
    }

    static class WebFeature {
    }

    static class BatchFeature {
    }
}
~~~

Giải thích:
- `setWebApplicationType(WebApplicationType.NONE)` yêu cầu Spring Boot tạo non-web context.
- `webFeature()` chỉ được đăng ký khi context là servlet web application.
- `batchFeature()` chỉ được đăng ký khi context không phải web application.
- `CommandLineRunner` in ra loại context và sự hiện diện của hai bean sau khi context khởi động.

### 7.3. Chạy ứng dụng

~~~bash
mvn spring-boot:run
~~~

Hoặc:

~~~bash
java -jar target/non-web-condition-demo-1.0.0.jar
~~~

**Output của ba dòng kiểm chứng:**

~~~text
WEB_APPLICATION_CONTEXT=false
WEB_FEATURE_PRESENT=false
BATCH_FEATURE_PRESENT=true
~~~

Spring Boot vẫn có thể in banner và log khởi động. Ba dòng trên là output do `CommandLineRunner` của ví dụ tạo ra; chúng không đại diện toàn bộ console output.

Vì starter web vẫn có trong classpath nhưng không có `WebApplicationContext`, bean chỉ dành cho servlet không được đăng ký và bean batch được đăng ký. Ứng dụng không khởi động embedded web server.

### 7.4. Thử bỏ chế độ NONE

Để thấy khác biệt, tạm bỏ dòng:

~~~java
application.setWebApplicationType(WebApplicationType.NONE);
~~~

Với `spring-boot-starter-web` vẫn trên classpath, Boot thường tự phát hiện servlet application. Khi các dependency và điều kiện khác phù hợp:
- `WEB_APPLICATION_CONTEXT=true`;
- `WEB_FEATURE_PRESENT=true`;
- `BATCH_FEATURE_PRESENT=false`.

Kết quả cụ thể phụ thuộc property và điều kiện khác, nhưng đây là đối chứng hữu ích để xác nhận condition đã được viết đúng.

## 8. Kiểm thử condition bằng ApplicationContextRunner

Spring Boot Test cung cấp hai runner quan trọng:

- `ApplicationContextRunner`: tạo context thông thường, phù hợp để kiểm tra non-web condition.
- `WebApplicationContextRunner`: tạo servlet web context, phù hợp để kiểm tra cấu hình chỉ hoạt động trong servlet application.

Nếu kiểm thử auto-configuration chỉ dành cho reactive application, dùng `ReactiveWebApplicationContextRunner`.

Spring Boot Reference khuyến nghị sử dụng runner phù hợp với loại context mà auto-configuration yêu cầu. Xem [Creating Your Own Auto-configuration — Simulating a Web Context](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html).

### 8.1. Dependency test

Thêm vào `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Giữ `spring-boot-starter-web` ở dependency chính để servlet API có trên test classpath.

### 8.2. Auto-configuration minh họa

Tạo file `src/test/java/example/WebConditionTests.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class WebConditionTests {

    static class WebFeature {
    }

    static class BatchFeature {
    }

    @AutoConfiguration
    static class ModeAutoConfiguration {

        @Bean
        @ConditionalOnWebApplication(
                type = ConditionalOnWebApplication.Type.SERVLET)
        WebFeature webFeature() {
            return new WebFeature();
        }

        @Bean
        @ConditionalOnNotWebApplication
        BatchFeature batchFeature() {
            return new BatchFeature();
        }
    }

    private final ApplicationContextRunner nonWebRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ModeAutoConfiguration.class));

    private final WebApplicationContextRunner servletRunner =
            new WebApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ModeAutoConfiguration.class));

    @Test
    void servletOnlyBeanIsAbsentFromNonWebContext() {
        nonWebRunner.run(context -> {
            assertThat(context).doesNotHaveBean(WebFeature.class);
            assertThat(context).hasSingleBean(BatchFeature.class);
        });
    }

    @Test
    void servletOnlyBeanIsPresentInServletContext() {
        servletRunner.run(context -> {
            assertThat(context).hasSingleBean(WebFeature.class);
            assertThat(context).doesNotHaveBean(BatchFeature.class);
        });
    }
}
~~~

### 8.3. Chạy test

~~~bash
mvn test -Dtest=WebConditionTests
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=WebConditionTests'
~~~

**Kết quả kỳ vọng:** hai test PASS:
1. Context mặc định của `ApplicationContextRunner` không đăng ký `WebFeature`, nhưng có `BatchFeature`.
2. `WebApplicationContextRunner` đăng ký `WebFeature`, không đăng ký `BatchFeature`.

Đây là đối chứng tốt: cùng một auto-configuration, chỉ đổi loại context và kết quả condition đổi theo. Test runner không cần mở một cổng HTTP công khai.

## 9. Kiểm tra auto-configuration thật và Condition Evaluation Report

Ví dụ trên dùng custom configuration để kiểm tra nguyên tắc condition. Khi điều tra ứng dụng thật, cần kiểm tra cả auto-configuration do Spring Boot cung cấp.

Một số cấu hình web phổ biến có điều kiện web:
- `WebMvcAutoConfiguration`: dành cho servlet web application và các class MVC cần thiết.
- `DispatcherServletAutoConfiguration`: cấu hình DispatcherServlet cho servlet application.
- `WebFluxAutoConfiguration`: cấu hình WebFlux khi ứng dụng được nhận diện reactive và classpath phù hợp.
- Các cấu hình server/servlet container: cần đúng loại context và dependency.

Không phải mọi auto-configuration có chữ "web" trong tên đều dùng cùng một condition. Đọc annotation của class cụ thể để xác nhận.

### 9.1. Bật debug report

Chạy:

~~~bash
java -jar target/non-web-condition-demo-1.0.0.jar --debug
~~~

Spring Boot in **Conditions Evaluation Report**. Tìm các source web-related và xem condition không match, ví dụ condition yêu cầu servlet web application. Message thực tế phụ thuộc class và version; không hard-code message vào test hoặc tài liệu vận hành.

### 9.2. Actuator conditions endpoint

Nếu ứng dụng có Actuator, có thể expose endpoint conditions:

~~~properties
management.endpoints.web.exposure.include=health,conditions
~~~

Trong một **web application**, có thể gọi:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

Một ứng dụng được cấu hình `WebApplicationType.NONE` không có embedded web server để phục vụ HTTP endpoint; do đó không thể mặc định dùng URL trên để kiểm tra non-web application. Với non-web app, dùng log `--debug`, truy cập `ConditionEvaluationReport` trong test hoặc một công cụ quan sát khác phù hợp.

### 9.3. Kiểm tra bean inventory

Có thể dùng Actuator `/actuator/beans` khi có web management context được expose, hoặc đọc bean definitions trong test. Nhưng đừng kết luận toàn bộ web auto-configuration đã tắt chỉ vì không thấy một bean cụ thể; phải xét source condition và toàn bộ context liên quan.

## 10. Cách kiểm tra bằng API trong code

Trong một test hoặc công cụ chẩn đoán, có thể xác nhận context có phải web không:

~~~java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.web.context.WebApplicationContext;

boolean isWeb =
        applicationContext instanceof WebApplicationContext;
~~~

Đây là phép kiểm tra hữu ích với servlet context. Với reactive application, cần kiểm tra `ReactiveWebApplicationContext`; nếu muốn phân biệt đầy đủ servlet/reactive/none, có thể kiểm tra loại context tương ứng hoặc dùng `WebApplicationType` mà ứng dụng đã cấu hình.

Đừng dùng phép kiểm tra classpath như:

~~~java
ClassUtils.isPresent(
        "org.springframework.web.servlet.DispatcherServlet",
        classLoader);
~~~

để kết luận ứng dụng đang chạy ở chế độ web. Nó chỉ cho biết class có thể được tải, không nói context hiện tại là servlet web context.

## 11. Những tình huống dễ gây hiểu nhầm

| Tình huống | Điều gì thực sự xảy ra? | Cách kiểm tra |
| --- | --- | --- |
| Có `spring-boot-starter-web`, không đặt NONE | Boot thường tự chọn servlet application | Xem context type và web conditions |
| Có starter web, đặt `WebApplicationType.NONE` | Class web còn trên classpath, context là non-web | Kiểm tra `WebApplicationContext` và marker bean |
| Đặt `server.port=-1` | Web context vẫn được tạo, chỉ không mở HTTP port | Không dùng làm bằng chứng cho non-web |
| Chỉ có `spring-boot-starter-webflux` | Boot thường chọn reactive khi không có MVC | Kiểm tra `WebApplicationType.REACTIVE` |
| Có cả MVC và WebFlux | Boot mặc định thường ưu tiên servlet | Đặt rõ `spring.main.web-application-type=reactive` nếu muốn reactive |
| Dùng `ApplicationContextRunner` | Test tạo generic non-web context | Dùng `WebApplicationContextRunner` cho servlet positive case |
| Dùng `@SpringBootTest(webEnvironment = NONE)` | Test không khởi chạy web server, nhưng loại context cần xét theo cấu hình web type của test | Nếu mục tiêu là non-web context, đặt `spring.main.web-application-type=none` rõ ràng |
| Một bean web vẫn xuất hiện trong NONE context | Có thể bean đến từ user configuration hoặc condition khác không phụ thuộc web | Tìm source bean và annotation của nó |
| Không có server nhưng web condition vẫn match | Có thể dùng `server.port=-1` hoặc một web context không chạy listener | Kiểm tra context type, không chỉ port |

### Không phải mọi cấu hình có liên quan HTTP đều bị tắt

Ví dụ, ứng dụng batch có thể cần `RestClient` hoặc `WebClient` để **gọi API bên ngoài**. Các client này có thể được cấu hình dựa trên classpath và không đòi hỏi ứng dụng phải là web server. Vì vậy, `WebApplicationType.NONE` không có nghĩa gỡ toàn bộ HTTP client support.

Điều cần xác nhận là **các bean chỉ dành cho inbound web server / servlet / reactive web context** không được đăng ký khi context non-web. Phân biệt inbound server với outbound HTTP client để tránh vô tình loại bỏ khả năng gọi dịch vụ bên ngoài.

## 12. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Có starter web nên server vẫn chạy trong batch | Boot tự dò classpath và chọn servlet | Đặt `WebApplicationType.NONE` hoặc `spring.main.web-application-type=none` |
| Chỉ đặt `server.port=-1` rồi kỳ vọng web condition false | Port không quyết định loại ApplicationContext | Dùng NONE nếu cần non-web context |
| Dùng `@ConditionalOnWebApplication` cho batch bean | Điều kiện ngược mục đích | Dùng `@ConditionalOnNotWebApplication` |
| Test web condition bằng ApplicationContextRunner rồi kỳ vọng match | Runner tạo generic non-web context | Dùng WebApplicationContextRunner cho servlet case |
| Dùng classpath check để xác định web mode | Class có thể hiện diện dù context không web | Kiểm tra context/environment hoặc ConditionEvaluationReport |
| Tưởng NONE gỡ thư viện web khỏi JAR | NONE chỉ chọn loại context | Gỡ dependency nếu thật sự muốn loại khỏi artifact |
| Vẫn thấy một bean web trong NONE | Bean có thể do user config hoặc condition khác tạo | Truy vết bean definition và source |
| Dùng Actuator HTTP endpoint trong app NONE | Không có web server phục vụ HTTP | Dùng `--debug`, test hoặc công cụ chẩn đoán khác |
| Có cả MVC và WebFlux, Boot chọn sai kiểu mong muốn | Cơ chế auto-detect ưu tiên servlet khi MVC hiện diện | Đặt explicit `spring.main.web-application-type` |

## 13. Quy trình kiểm chứng trong dự án thật

1. **Kiểm tra dependency:** xem có `spring-boot-starter-web`, `spring-boot-starter-webflux`, Servlet API hoặc server implementation nào trên classpath.
2. **Xác định chế độ khởi động:** tìm `setWebApplicationType`, `spring.main.web-application-type`, `SpringApplicationBuilder.web(...)` và các nguồn cấu hình ghi đè.
3. **Kiểm tra context type:** xác nhận context hiện tại là generic, servlet hay reactive.
4. **Đọc condition của auto-configuration cần kiểm tra:** xem `@ConditionalOnWebApplication`, `@ConditionalOnNotWebApplication`, `@ConditionalOnClass`, `@ConditionalOnMissingBean` và điều kiện khác.
5. **Bật condition report:** chạy `--debug`, đọc source web condition và message.
6. **Kiểm tra bean inventory:** xác nhận bean web cụ thể không có trong context non-web; kiểm tra nguồn bean nếu nó vẫn xuất hiện.
7. **Viết test hai chiều:** một test non-web và một test servlet/reactive positive control bằng runner phù hợp.
8. **Kiểm tra ứng dụng sau đóng gói:** chạy JAR với property NONE trong môi trường tương tự production, vì cấu hình profile/command line có thể khác test.

Một kết luận có chất lượng phải chỉ ra được: **loại context thực tế, condition source, bean cụ thể và test chứng minh**. Chỉ nói "không thấy cổng 8080" là chưa đủ để khẳng định web auto-configuration đã không chạy.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Dự án có `spring-boot-starter-web`, nhưng đặt `spring.main.web-application-type=none`. Các class servlet có bị xóa khỏi classpath không?

**Đáp án:** Không. Dependency vẫn tồn tại; Boot tạo non-web context và các web condition được đánh giá theo context đó.

**Câu 2.** `server.port=-1` có tương đương `WebApplicationType.NONE` không?

**Đáp án:** Không. `server.port=-1` có thể tắt HTTP listener nhưng vẫn tạo `WebApplicationContext`, nên web condition vẫn có thể match.

**Câu 3.** Annotation nào phù hợp cho bean chỉ dùng trong ứng dụng batch?

**Đáp án:** `@ConditionalOnNotWebApplication`.

**Câu 4.** Dùng runner nào để kiểm tra cấu hình chỉ dành cho servlet web application?

**Đáp án:** `WebApplicationContextRunner`. Dùng `ApplicationContextRunner` để kiểm tra non-web context và `ReactiveWebApplicationContextRunner` cho reactive context.

**Câu 5.** Vì sao một HTTP client vẫn có thể tồn tại trong ứng dụng NONE?

**Đáp án:** Outbound HTTP client không đồng nghĩa ứng dụng đang cung cấp inbound web server. Điều kiện của client có thể dựa vào classpath và bean, không yêu cầu web application context.

## 15. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Embedded Web Servers (disable server, `spring.main.web-application-type=none`, khác biệt với `server.port=-1`): https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 — Creating Your Own Auto-configuration (web application conditions, runner cho servlet/reactive context): https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `WebApplicationType`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.5 API — `ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html
- Spring Boot 3.5 API — `ConditionalOnNotWebApplication`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnNotWebApplication.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 API — `WebApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html
