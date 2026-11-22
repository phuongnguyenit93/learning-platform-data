# Cấu hình web không khớp vì loại context khác với dự kiến

## Mục tiêu học tập

Một auto-configuration có thể cung cấp bean chỉ dành cho Spring MVC, Spring WebFlux hoặc mọi ứng dụng web. Khi bean không xuất hiện dù dependency đã có, nguyên nhân thường nằm ở việc **ApplicationContext thực tế không thuộc loại mà condition yêu cầu**.

Các tình huống thường gặp:

- Cấu hình dùng `@ConditionalOnWebApplication(type = SERVLET)`, nhưng test dùng `ApplicationContextRunner`, vốn tạo context non-web.
- Ứng dụng có cả Spring MVC và WebFlux, nhưng Spring Boot chọn Servlet stack theo mặc định.
- Ứng dụng chỉ cần `WebClient` để gọi API từ một service nền, nhưng auto-configuration lại yêu cầu Reactive web context.
- Test tự tạo `AnnotationConfigApplicationContext`, dù classpath có đầy đủ Servlet hoặc Reactive dependency.
- Profile test đặt `spring.main.web-application-type=none`, khiến Boot tạo non-web context.

Bài học này giải thích cách Spring Boot xác định loại ứng dụng, cách `@ConditionalOnWebApplication` đánh giá context, cách phân biệt Servlet và Reactive, và cách tái hiện lỗi bằng các context runner.

Sau bài học, bạn có thể:

- Phân biệt `WebApplicationType` với `ConditionalOnWebApplication.Type`.
- Dự đoán kết quả condition trong context non-web, Servlet và Reactive.
- Hiểu vì sao có cả MVC và WebFlux nhưng ứng dụng vẫn chạy theo Servlet stack.
- Phân biệt web server với web ApplicationContext.
- Chọn đúng condition cho server-side integration và client-only library.
- Viết test bằng `ApplicationContextRunner`, `WebApplicationContextRunner` và `ReactiveWebApplicationContextRunner`.
- Dùng Condition Evaluation Report và dependency tree để tìm nguyên nhân.

## 1. Bắt đầu bằng loại ApplicationContext thực tế

Spring Boot chọn loại ApplicationContext khi SpringApplication khởi động. Ba loại ứng dụng chính là `WebApplicationType.NONE`, `WebApplicationType.SERVLET` và `WebApplicationType.REACTIVE`.

| WebApplicationType | Context điển hình | Ý nghĩa |
| --- | --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` | Ứng dụng không chạy như web app và không khởi động embedded web server |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | Ứng dụng web Servlet, thường dùng Spring MVC |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | Ứng dụng web Reactive, thường dùng Spring WebFlux |

Enum này thuộc package `org.springframework.boot`. Nó điều khiển cách SpringApplication tạo context và khởi động web server.

Có thể đặt loại ứng dụng bằng property:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Hoặc đặt trực tiếp khi bootstrap:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class AcmeApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(AcmeApplication.class);

        application.setWebApplicationType(WebApplicationType.REACTIVE);
        application.run(args);
    }
}
~~~

Nếu context thực tế là Servlet, một condition yêu cầu Reactive có thể không khớp dù dependency WebFlux vẫn nằm trong classpath. Ngược lại, Servlet-only condition không khớp trong Reactive context dù servlet API có thể xuất hiện gián tiếp trong dependency tree.

## 2. Phân biệt hai enum có tên gần giống nhau

Spring Boot có hai enum riêng, phục vụ hai mục đích:

| Enum | Package | Giá trị | Vai trò |
| --- | --- | --- | --- |
| `WebApplicationType` | `org.springframework.boot` | `NONE`, `SERVLET`, `REACTIVE` | Chọn loại ApplicationContext khi SpringApplication khởi động |
| `ConditionalOnWebApplication.Type` | `org.springframework.boot.autoconfigure.condition` | `ANY`, `SERVLET`, `REACTIVE` | Chọn loại web context mà condition chấp nhận |

Ví dụ:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;

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

@ConditionalOnNotWebApplication
class BackgroundWorkerConfiguration {
}
~~~

Mặc định `@ConditionalOnWebApplication` dùng `type = ANY`, vì vậy cả Servlet và Reactive web application đều có thể khớp.

Không nhầm `ConditionalOnWebApplication.Type.ANY` với `WebApplicationType.NONE`. ANY có nghĩa là chấp nhận bất kỳ web context nào; NONE có nghĩa ứng dụng không phải web app.

## 3. @ConditionalOnWebApplication kiểm tra điều gì?

`@ConditionalOnWebApplication` là condition của Spring Boot, dùng để giới hạn configuration theo loại web application:

- `ANY`: bất kỳ web application nào.
- `SERVLET`: chỉ Servlet-based web application.
- `REACTIVE`: chỉ Reactive-based web application.

Servlet web application được nhận diện qua các đặc điểm như Spring `WebApplicationContext`, session scope hoặc `ConfigurableWebEnvironment`. Reactive web application sử dụng `ReactiveWebApplicationContext` hoặc `ConfigurableReactiveWebEnvironment`.

Điểm quan trọng: **dependency web có mặt chưa đủ để condition khớp**. Context đang đánh giá condition cũng phải thuộc loại tương ứng.

Ví dụ, test sau tạo context non-web:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(MyServletAutoConfiguration.class))
        .run(context -> {
            // Servlet condition không khớp trong context non-web.
        });
~~~

Mặc dù test runtime có thể chứa spring-webmvc, ApplicationContextRunner mặc định tạo một AnnotationConfigApplicationContext. Đây không phải Servlet WebApplicationContext.

## 4. Spring Boot chọn Servlet hay Reactive như thế nào?

Khi dùng SpringApplication và không ép loại ứng dụng bằng cấu hình, Boot suy luận loại web từ classpath:

1. Nếu Spring MVC có mặt, Boot chọn Servlet web application.
2. Nếu Spring MVC không có mặt nhưng Spring WebFlux có mặt, Boot chọn Reactive web application.
3. Nếu cả hai không có, Boot chọn non-web application.

**Nếu cả Spring MVC và WebFlux đều có mặt, Spring MVC được ưu tiên theo mặc định.**

Đây là lựa chọn có chủ đích. Nhiều ứng dụng MVC thêm WebFlux chỉ để dùng `WebClient` làm HTTP client bất đồng bộ; việc có WebFlux trên classpath không có nghĩa ứng dụng muốn chạy Reactive server.

Ví dụ:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

Với cả hai starter, ứng dụng thường chạy theo Servlet stack. Nếu muốn chạy WebFlux, hãy đặt rõ:

~~~properties
spring.main.web-application-type=reactive
~~~

Hoặc gọi `application.setWebApplicationType(WebApplicationType.REACTIVE)` trước khi chạy ứng dụng.

### 4.1. WebClient không đồng nghĩa với Reactive server

`WebClient` là HTTP client. Nó có thể được sử dụng trong:
- Ứng dụng Spring MVC.
- Ứng dụng Spring WebFlux.
- Ứng dụng non-web như batch job hoặc scheduled worker, nếu dependency client cần thiết có mặt.

Vì vậy, nếu thư viện chỉ cung cấp client gọi HTTP, điều kiện thường phù hợp là `@ConditionalOnClass(WebClient.class)` hoặc property condition. Không nên yêu cầu `@ConditionalOnWebApplication(type = REACTIVE)` nếu thư viện không cần Reactive server context.

Ngược lại, nếu thư viện đăng ký `WebFilter`, `ServerWebExchange`, `HandlerMapping` hoặc cấu hình WebFlux server, Reactive context là một phần của hợp đồng và condition REACTIVE phù hợp.

Tương tự, `Filter`, `HttpServletRequest`, `HandlerInterceptor` và API Servlet thuộc Servlet stack. Một Servlet integration nên được giới hạn bằng condition SERVLET khi cần.

## 5. Web ApplicationContext không đồng nghĩa với server đang lắng nghe cổng

Một lỗi chẩn đoán phổ biến là nghĩ condition chỉ khớp khi embedded web server đang chạy. Thực tế, web context và server lifecycle là hai khái niệm liên quan nhưng khác nhau.

Ví dụ, đặt:

~~~properties
server.port=-1
~~~

có thể tắt HTTP endpoints trong khi ứng dụng vẫn tạo một `WebApplicationContext`. Điều này hữu ích cho một số bài test cần web infrastructure nhưng không cần mở cổng.

Ngược lại:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

yêu cầu Spring Boot tạo non-web ApplicationContext. Khi đó `@ConditionalOnWebApplication` không khớp và `@ConditionalOnNotWebApplication` có thể khớp.

Một ứng dụng Servlet có thể được triển khai dạng WAR vào servlet container hoặc dùng embedded server. Nếu cần phân biệt kiểu triển khai WAR truyền thống, dùng condition riêng `@ConditionalOnWarDeployment`; không suy ra điều đó chỉ từ `@ConditionalOnWebApplication(type = SERVLET)`.

## 6. Tách classpath condition khỏi web-context condition

Hai condition trả lời hai câu hỏi khác nhau:

- `@ConditionalOnClass`: API/framework class có trên classpath không?
- `@ConditionalOnWebApplication`: ApplicationContext hiện tại có phải loại web mà feature yêu cầu không?

Một Servlet integration có thể cần cả hai:

~~~java
package com.acme.web.servlet;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;

@AutoConfiguration
@ConditionalOnClass(name = "org.springframework.web.servlet.DispatcherServlet")
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
public class AcmeServletAutoConfiguration {
}
~~~

Một Reactive integration tương ứng:

~~~java
package com.acme.web.reactive;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;

@AutoConfiguration
@ConditionalOnClass(name = "org.springframework.web.reactive.DispatcherHandler")
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE)
public class AcmeReactiveAutoConfiguration {
}
~~~

Ở đây:
- Classpath condition bảo đảm API của stack tương ứng có mặt.
- Web condition bảo đảm ứng dụng thực sự dùng đúng loại web context.
- Nếu một trong hai condition không khớp, cấu hình không được áp dụng.

Tách Servlet và Reactive configuration thành các class riêng cũng giúp tránh để class hoặc method signature của một stack tùy chọn bị resolve trong ứng dụng chỉ dùng stack còn lại.

### 6.1. Không dùng classpath condition thay cho web condition

Nếu chỉ viết:

~~~java
@ConditionalOnClass(name = "org.springframework.web.servlet.DispatcherServlet")
class ServletConfiguration {
}
~~~

cấu hình có thể được xem xét trong một context non-web nếu servlet API có mặt trên classpath. Điều đó có thể không phù hợp nếu bean cần một Servlet WebApplicationContext.

### 6.2. Không dùng web condition thay cho classpath condition

Nếu một integration có dependency tùy chọn và chỉ viết:

~~~java
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
class ReactiveConfiguration {
}
~~~

condition chỉ nói về context. Nó không bảo đảm mọi thư viện WebFlux/adapter class mà implementation cần đều có mặt. Bổ sung classpath condition khi dependency thực sự là tùy chọn.

### 6.3. Bảo vệ optional types ở cấp configuration class

Nếu bean method có return type hoặc parameter type từ thư viện tùy chọn, không nên chỉ đặt condition trên method rồi giả định JVM không cần resolve signature. Với optional stack, tách configuration class riêng và đặt `@ConditionalOnClass` ở class-level. Spring Boot có thể đọc metadata class-level trước khi load configuration class, giúp tránh lỗi do kiểu không tồn tại.

## 7. Chọn condition theo đúng loại tính năng

| Tính năng của thư viện | Condition thường phù hợp | Lý do |
| --- | --- | --- |
| Servlet Filter hoặc MVC interceptor | `@ConditionalOnWebApplication(SERVLET)` + classpath condition nếu cần | Phụ thuộc Servlet context/API |
| WebFlux WebFilter hoặc HandlerFunction | `@ConditionalOnWebApplication(REACTIVE)` + classpath condition | Phụ thuộc Reactive context/API |
| Bean dùng chung cho mọi web stack | `@ConditionalOnWebApplication` (ANY) | Cần web context nhưng không phụ thuộc stack cụ thể |
| HTTP client WebClient | `@ConditionalOnClass(WebClient.class)` | Client có thể dùng trong MVC, WebFlux hoặc non-web |
| RestClient/RestTemplate | Classpath condition và property nếu cần | HTTP client không yêu cầu server-side web context |
| Batch/scheduled worker | `@ConditionalOnNotWebApplication` nếu thật sự chỉ dành cho non-web | Feature dành riêng cho ứng dụng non-web |
| Shared library không cần web API | Không dùng web condition | Tránh vô tình loại khỏi ứng dụng non-web |

Điều kiện cần phản ánh vai trò thực tế của bean, không chỉ package của dependency.

## 8. Test bằng ba loại ApplicationContextRunner

Spring Boot 3.3 cung cấp ba runner hữu ích:

- `ApplicationContextRunner`: context non-web tiêu chuẩn.
- `WebApplicationContextRunner`: Servlet-based web context.
- `ReactiveWebApplicationContextRunner`: Reactive web context.

Ba runner giúp kiểm tra condition trong đúng môi trường. Không nên dùng ApplicationContextRunner mặc định để kết luận Servlet hoặc Reactive condition bị lỗi trong production.

**Tệp:** `src/test/java/example/web/WebStackConditionTests.java`

~~~java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class WebStackConditionTests {

    private final AutoConfigurations autoConfigurations =
            AutoConfigurations.of(WebStackAutoConfiguration.class);

    @Test
    void standardApplicationContextRunnerCreatesNonWebContext() {
        new ApplicationContextRunner()
                .withConfiguration(this.autoConfigurations)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AnyWebMarker.class);
                    assertThat(context).doesNotHaveBean(ServletMarker.class);
                    assertThat(context).doesNotHaveBean(ReactiveMarker.class);
                    assertThat(context).hasSingleBean(NonWebMarker.class);
                });
    }

    @Test
    void servletRunnerMatchesAnyAndServletConditions() {
        new WebApplicationContextRunner()
                .withConfiguration(this.autoConfigurations)
                .run(context -> {
                    assertThat(context).hasSingleBean(AnyWebMarker.class);
                    assertThat(context).hasSingleBean(ServletMarker.class);
                    assertThat(context).doesNotHaveBean(ReactiveMarker.class);
                    assertThat(context).doesNotHaveBean(NonWebMarker.class);
                });
    }

    @Test
    void reactiveRunnerMatchesAnyAndReactiveConditions() {
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(this.autoConfigurations)
                .run(context -> {
                    assertThat(context).hasSingleBean(AnyWebMarker.class);
                    assertThat(context).doesNotHaveBean(ServletMarker.class);
                    assertThat(context).hasSingleBean(ReactiveMarker.class);
                    assertThat(context).doesNotHaveBean(NonWebMarker.class);
                });
    }

    static class AnyWebMarker {
    }

    static class ServletMarker {
    }

    static class ReactiveMarker {
    }

    static class NonWebMarker {
    }

    @AutoConfiguration
    static class WebStackAutoConfiguration {

        @Bean
        @ConditionalOnWebApplication
        AnyWebMarker anyWebMarker() {
            return new AnyWebMarker();
        }

        @Bean
        @ConditionalOnWebApplication(
                type = ConditionalOnWebApplication.Type.SERVLET)
        ServletMarker servletMarker() {
            return new ServletMarker();
        }

        @Bean
        @ConditionalOnWebApplication(
                type = ConditionalOnWebApplication.Type.REACTIVE)
        ReactiveMarker reactiveMarker() {
            return new ReactiveMarker();
        }

        @Bean
        @ConditionalOnNotWebApplication
        NonWebMarker nonWebMarker() {
            return new NonWebMarker();
        }
    }
}
~~~

### 8.1. Đọc kết quả

**Test 1 — ApplicationContextRunner**

Runner mặc định tạo non-web AnnotationConfigApplicationContext. Nó không biến thành web context chỉ vì spring-webmvc và spring-webflux có mặt trong test classpath.

- ANY không khớp.
- SERVLET không khớp.
- REACTIVE không khớp.
- NOT WEB khớp.

**Test 2 — WebApplicationContextRunner**

Runner tạo Servlet-based ConfigurableWebApplicationContext. Nó không cần khởi động embedded server thật chỉ để kiểm tra condition.

- ANY khớp.
- SERVLET khớp.
- REACTIVE không khớp.
- NOT WEB không khớp.

**Test 3 — ReactiveWebApplicationContextRunner**

Runner tạo ConfigurableReactiveWebApplicationContext.

- ANY khớp.
- SERVLET không khớp.
- REACTIVE khớp.
- NOT WEB không khớp.

Bộ test này chứng minh context type là yếu tố trực tiếp trong web condition. Nó cũng cho thấy việc kiểm tra classpath đơn thuần không thể thay thế test context.

## 9. Dependency và lệnh chạy test

Ví dụ dùng Java 17+, Spring Boot 3.3.x, JUnit 5 và AssertJ. Trong Gradle Groovy DSL, giả sử version Spring Boot được quản lý bằng plugin hoặc BOM:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Hai web starter được thêm trong test scope để có cả Servlet và Reactive test infrastructure. Nếu test module đã có các dependency tương ứng, không cần khai báo trùng.

Chạy riêng test class:

~~~bash
# Linux/macOS
./gradlew test --tests "example.web.WebStackConditionTests"

# Windows
gradlew.bat test --tests "example.web.WebStackConditionTests"
~~~

**Kết quả mong đợi:** ba test PASS. Các test chỉ kiểm tra bean registration, không mở cổng HTTP và không cần gọi service ngoài.

## 10. Kiểm thử khi ứng dụng có cả MVC và WebFlux

Một trường hợp thực tế:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

Nếu khởi động bằng SpringApplication với cấu hình mặc định, Boot ưu tiên MVC và chọn Servlet context. Do đó:
- `@ConditionalOnWebApplication(type = SERVLET)` có thể khớp.
- `@ConditionalOnWebApplication(type = REACTIVE)` không khớp.
- `@ConditionalOnWebApplication` mặc định ANY có thể khớp.

Nếu ứng dụng thực sự muốn chạy WebFlux server, đặt rõ:

~~~properties
spring.main.web-application-type=reactive
~~~

Với integration test dùng `@SpringBootTest`, có thể đặt:

~~~java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
class ReactiveApplicationTests {
}
~~~

Hoặc ép loại trực tiếp trên SpringApplication trước khi gọi run. Đừng cố sửa lỗi bằng cách chỉ thêm WebFlux dependency nếu MVC vẫn đang được chọn.

### 10.1. Phân biệt test slice

- `@WebMvcTest`: tập trung vào thành phần Spring MVC/Servlet.
- `@WebFluxTest`: tập trung vào thành phần Spring WebFlux/Reactive.
- `@SpringBootTest(webEnvironment = NONE)`: tạo môi trường non-web.
- `@SpringBootTest(webEnvironment = MOCK)`: dùng web context phù hợp khi ứng dụng có web stack; loại stack vẫn phụ thuộc cách Boot xác định web application type.
- `RANDOM_PORT` hoặc `DEFINED_PORT`: khởi chạy server thực tế với port tương ứng.

Nếu ứng dụng có cả hai stack và test slice không phản ánh loại context mong muốn, hãy đặt rõ `spring.main.web-application-type` và kiểm tra runner/test annotation đang sử dụng.

## 11. Những nguyên nhân khác khiến web condition không khớp

### 11.1. Ứng dụng bị cấu hình thành NONE

Tìm các giá trị:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Property có thể nằm trong profile riêng, biến môi trường, command line, ConfigMap hoặc file cấu hình được import. Nếu một profile test đặt NONE, web auto-configuration sẽ không khớp trong profile đó.

### 11.2. Test dựng context bằng tay

Đoạn code:

~~~java
new AnnotationConfigApplicationContext(MyConfiguration.class);
~~~

luôn tạo context non-web. Việc dependency Servlet/Reactive có mặt trong test runtime không thay đổi class của context này.

Nếu muốn test Servlet condition, dùng WebApplicationContextRunner hoặc tạo đúng Servlet WebApplicationContext. Nếu muốn test Reactive condition, dùng ReactiveWebApplicationContextRunner.

### 11.3. Custom ApplicationContextFactory

Ứng dụng có thể cấu hình factory tùy chỉnh cho SpringApplication. Nếu factory trả về context không thuộc loại web dự kiến, condition có thể không khớp dù WebApplicationType hoặc classpath có vẻ đúng.

Kiểm tra:
- Class của context được factory tạo.
- Interface web mà context triển khai.
- Environment được context sử dụng.
- Cấu hình factory có bị override trong test/profile không.

### 11.4. Chỉ có Servlet API nhưng không có Spring MVC context

Một dependency có thể đưa Servlet API vào classpath vì integration khác, nhưng ứng dụng không nhất thiết dùng Spring MVC. Classpath có Servlet type không tự biến AnnotationConfigApplicationContext thành Servlet WebApplicationContext.

Nếu feature chỉ cần Servlet API và có thể chạy ngoài Spring web context, hãy đánh giá lại xem có nên dùng `@ConditionalOnWebApplication` hay chỉ dùng classpath condition.

### 11.5. Dùng condition ở sai phạm vi

Nếu đặt condition trên class-level, toàn bộ configuration class sẽ bị loại khi condition không khớp. Nếu chỉ một bean cần Servlet context, cân nhắc đặt condition trên bean method thay vì loại cả class.

Tuy nhiên, nếu configuration class tham chiếu trực tiếp API tùy chọn trong method signatures, hãy tách class-level configuration riêng để bảo vệ việc resolve kiểu.

### 11.6. Nhầm web application với WAR deployment

`@ConditionalOnWebApplication(type = SERVLET)` có thể khớp cả ứng dụng Servlet chạy embedded server lẫn ứng dụng Servlet triển khai trong container. Nếu feature chỉ dành cho WAR deployment truyền thống, dùng condition riêng `@ConditionalOnWarDeployment`.

### 11.7. Dùng nhầm context cha/con

Một ứng dụng có thể có root context và child context. Hãy xác định condition đang được đánh giá trong context nào. Một bean hoặc web infrastructure được đăng ký ở context khác không tự động có nghĩa context hiện tại có cùng loại web context.

## 12. Chẩn đoán bằng Condition Evaluation Report

Khi ứng dụng khởi động nhưng một auto-configuration không xuất hiện, chạy với debug:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot ghi Condition Evaluation Report. Tìm tên configuration class hoặc condition liên quan, sau đó xác định:

- Configuration có bị loại do classpath condition không?
- Web condition yêu cầu ANY, SERVLET hay REACTIVE?
- Context hiện tại có được nhận diện là Servlet hoặc Reactive không?
- Một property/profile condition khác có phủ quyết configuration không?
- Một condition khác trong cùng configuration có không khớp không?

Không nên chỉ nhìn một annotation rồi kết luận. Nhiều condition trên cùng configuration thường kết hợp theo AND: tất cả phải khớp thì configuration mới được áp dụng.

### 12.1. Kiểm tra context type lúc runtime

Khi cần xác nhận trực tiếp, có thể log class của context và Environment:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
class ContextTypeProbe {

    private static final Logger log =
            LoggerFactory.getLogger(ContextTypeProbe.class);

    ContextTypeProbe(ApplicationContext context) {
        log.info("ApplicationContext type: {}",
                context.getClass().getName());
        log.info("Environment type: {}",
                context.getEnvironment().getClass().getName());
    }
}
~~~

Ví dụ log minh họa dạng thông tin cần kiểm tra:

~~~text
ApplicationContext type: org.springframework.boot.web.servlet.context.AnnotationConfigServletWebServerApplicationContext
Environment type: org.springframework.web.context.support.StandardServletEnvironment
~~~

Tên class cụ thể phụ thuộc Boot version, context factory và cách khởi động. Đây là ví dụ định dạng, không phải stdout cố định cho mọi ứng dụng.

### 12.2. Kiểm tra dependency tree

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree
~~~

Tìm:
- spring-boot-starter-web.
- spring-boot-starter-webflux.
- spring-webmvc.
- spring-webflux.
- Servlet API.
- Các dependency transitively kéo theo web stack.

Dependency tree cho biết thư viện nào có mặt. Nó không tự cho biết context thực tế được tạo; cần kết hợp với WebApplicationType, ApplicationContextFactory và runtime context class.

## 13. Quy trình xử lý sự cố theo thứ tự

1. **Đọc condition yêu cầu gì.** ANY, SERVLET hay REACTIVE? Có thêm classpath/property condition không?
2. **Xác nhận context thực tế.** Kiểm tra class ApplicationContext, Environment và WebApplicationType.
3. **Kiểm tra property hiệu lực.** Tìm `spring.main.web-application-type` trong profile, môi trường triển khai và command line.
4. **Kiểm tra cả hai web stack.** Nếu MVC và WebFlux cùng có mặt, nhớ MVC được ưu tiên theo mặc định.
5. **Xác định test runner.** ApplicationContextRunner là non-web; dùng đúng runner cho Servlet/Reactive.
6. **Kiểm tra custom factory.** Đảm bảo context factory không tạo context khác dự kiến.
7. **Đọc Condition Evaluation Report.** Tìm lý do cụ thể của từng condition.
8. **Kiểm tra dependency tree.** Xác nhận stack và API cần thiết có trong runtime classpath.
9. **Đánh giá lại ranh giới feature.** Client-only có thể không cần web condition; server integration cần điều kiện đúng stack.
10. **Thêm regression test.** Test cả context mong muốn và context không mong muốn để tránh lỗi tái diễn.

## 14. Lỗi thường gặp

1. **Thấy WebFlux trên classpath rồi nghĩ app là Reactive.** Nếu Spring MVC cũng có mặt, Boot chọn Servlet theo mặc định.
2. **Dùng ApplicationContextRunner để test Servlet condition.** Runner này tạo non-web context; dùng WebApplicationContextRunner.
3. **Dùng ApplicationContextRunner để test Reactive condition.** Dùng ReactiveWebApplicationContextRunner hoặc context Reactive được dựng đúng cách.
4. **Nhầm WebApplicationType với ConditionalOnWebApplication.Type.** Một enum chọn context, enum kia giới hạn condition.
5. **Dùng REACTIVE cho WebClient client-only.** WebClient có thể dùng trong MVC hoặc non-web; chỉ yêu cầu Reactive context nếu bean phụ thuộc Reactive server APIs.
6. **Dùng ANY cho Servlet-only bean.** Condition có thể khớp trong Reactive context dù bean cần Servlet API.
7. **Chỉ kiểm tra classpath.** Class có mặt không chứng minh context đúng loại.
8. **Chỉ kiểm tra context.** Context đúng không chứng minh optional API có mặt; thêm classpath condition nếu cần.
9. **Đặt spring.main.web-application-type=none trong test.** Property này khiến web conditions không khớp.
10. **Nhầm server.port=-1 với web-application-type=none.** Port -1 vẫn có thể giữ WebApplicationContext; NONE tạo non-web context.
11. **Tạo AnnotationConfigApplicationContext thủ công rồi mong nó thành web context.** Chọn context class hoặc runner phù hợp.
12. **Để MVC và WebFlux cùng có mặt mà không chọn stack rõ ràng.** Boot ưu tiên MVC; đặt type rõ nếu chủ đích là Reactive.
13. **Đặt classpath condition trên method có optional type.** Tách class-level configuration để tránh resolve signature trước khi condition bảo vệ.
14. **Không đọc Condition Evaluation Report.** Có thể một condition khác đang loại configuration; bật --debug.
15. **Dùng @ConditionalOnWarDeployment để kiểm tra mọi Servlet app.** Embedded Servlet app không phải WAR deployment truyền thống.
16. **Giả định web context luôn có server đang lắng nghe.** WebApplicationContext có thể tồn tại mà không mở HTTP port.
17. **Không kiểm tra context hierarchy.** Condition được đánh giá trong context cụ thể; đừng suy luận từ bean ở context khác.
18. **Chỉ kiểm thử nhánh mong muốn.** Cần kiểm thử non-web, Servlet và Reactive để phát hiện cấu hình bị kích hoạt nhầm.

## 15. Checklist review auto-configuration web

### Context và điều kiện

- [ ] Đã xác định bean dành cho Servlet, Reactive hay mọi web context.
- [ ] Dùng đúng `ConditionalOnWebApplication.Type`.
- [ ] Dùng `ConditionalOnNotWebApplication` cho feature chỉ dành cho non-web nếu cần.
- [ ] Đã phân biệt WebApplicationType với ConditionalOnWebApplication.Type.
- [ ] Không nhầm client library với server-side web integration.
- [ ] Đã cân nhắc classpath condition cho optional framework APIs.

### Bootstrap và môi trường

- [ ] Property `spring.main.web-application-type` không bị override ngoài ý muốn.
- [ ] Nếu MVC và WebFlux cùng có mặt, stack được chọn là stack mong muốn.
- [ ] Custom ApplicationContextFactory trả về context đúng loại.
- [ ] Đã phân biệt web context với embedded server và WAR deployment.

### Test và chẩn đoán

- [ ] Non-web condition được kiểm tra bằng ApplicationContextRunner.
- [ ] Servlet condition được kiểm tra bằng WebApplicationContextRunner.
- [ ] Reactive condition được kiểm tra bằng ReactiveWebApplicationContextRunner.
- [ ] Test bao gồm cả nhánh khớp và không khớp.
- [ ] Condition Evaluation Report được kiểm tra khi lỗi xảy ra.
- [ ] Dependency tree và runtime context type đã được xác nhận.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Test dùng ApplicationContextRunner nhưng có spring-boot-starter-web trên test classpath. Vì sao `@ConditionalOnWebApplication(SERVLET)` vẫn không khớp?

**Đáp án:** ApplicationContextRunner mặc định tạo một non-web AnnotationConfigApplicationContext. Dependency có mặt không tự biến context thành Servlet WebApplicationContext.

**Câu 2.** Ứng dụng có cả spring-boot-starter-web và spring-boot-starter-webflux. Boot chọn stack nào theo mặc định?

**Đáp án:** Servlet/MVC được ưu tiên. Muốn Reactive server, đặt spring.main.web-application-type=reactive hoặc cấu hình WebApplicationType.REACTIVE khi bootstrap.

**Câu 3.** Một service chạy nền dùng WebClient để gọi API. Có nên yêu cầu `@ConditionalOnWebApplication(REACTIVE)` không?

**Đáp án:** Không, nếu service chỉ cần HTTP client. Kiểm tra classpath của WebClient và dependency cần thiết; Reactive web context chỉ cần cho server-side WebFlux integration.

**Câu 4.** Khác biệt giữa server.port=-1 và spring.main.web-application-type=none là gì?

**Đáp án:** server.port=-1 có thể tắt HTTP endpoints nhưng vẫn tạo WebApplicationContext. web-application-type=none yêu cầu ứng dụng dùng non-web context.

**Câu 5.** Muốn kiểm tra Servlet và Reactive condition mà không khởi động embedded server, nên dùng runner nào?

**Đáp án:** WebApplicationContextRunner cho Servlet và ReactiveWebApplicationContextRunner cho Reactive. Cả hai tạo context phù hợp để đánh giá condition.

**Câu 6.** `@ConditionalOnWebApplication` mặc định nhận loại nào?

**Đáp án:** ANY, nghĩa là chấp nhận bất kỳ web application nào, bao gồm Servlet và Reactive.

**Câu 7.** Muốn xác nhận condition không khớp do context type, cần xem gì?

**Đáp án:** Condition Evaluation Report, class thực tế của ApplicationContext, Environment type, WebApplicationType hiệu lực và property/profile cấu hình web application type.

## 17. Ghi nhớ

Một web condition chỉ khớp khi loại ApplicationContext thực tế phù hợp với loại mà annotation yêu cầu. Spring Boot phân biệt non-web, Servlet và Reactive; nếu MVC và WebFlux cùng có mặt, MVC được ưu tiên theo mặc định. `@ConditionalOnWebApplication` mặc định nhận ANY, còn SERVLET và REACTIVE giới hạn vào từng stack.

Hãy phân biệt server-side integration với HTTP client. Một WebClient không biến ứng dụng thành Reactive web application. Khi test, chọn đúng runner: ApplicationContextRunner cho non-web, WebApplicationContextRunner cho Servlet và ReactiveWebApplicationContextRunner cho Reactive. Cuối cùng, dùng Condition Evaluation Report và runtime context class để xác nhận nguyên nhân trước khi thay dependency hoặc sửa condition.

### Tài liệu Spring Boot 3.3 chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — WebApplicationType Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html)
- [Spring Boot 3.3 — ConditionalOnWebApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html)
- [Spring Boot 3.3 — ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.3 — WebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html)
- [Spring Boot 3.3 — ReactiveWebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html)
- [Spring Boot 3.3 — Core Features: Web Environment](https://docs.spring.io/spring-boot/docs/3.3.0-M2/reference/html/features.html)
