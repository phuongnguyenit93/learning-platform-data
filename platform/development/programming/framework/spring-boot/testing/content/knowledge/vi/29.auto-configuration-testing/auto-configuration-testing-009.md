# WebApplicationContextRunner và ReactiveWebApplicationContextRunner

## 1. Mục tiêu: kiểm thử auto-configuration theo đúng loại web application

Khi xây dựng một Spring Boot starter, một thư viện chia sẻ hoặc một module tự cấu hình, thường phải tạo bean **chỉ khi** ứng dụng đang chạy trên Spring MVC/Servlet hoặc **chỉ khi** đang chạy Spring WebFlux/Reactive. Những điều kiện này không thể được kiểm chứng đầy đủ bằng cách tạo một `ApplicationContext` thường rồi assert một bean tồn tại.

Ví dụ một thư viện audit có hai integration points:

- **Servlet:** một `HandlerInterceptor` dùng cho ứng dụng Spring MVC, đặt header `X-Audit-Mode`.
- **Reactive:** một `WebFilter` dùng cho Spring WebFlux, đặt cùng header nhưng thực thi qua một `Mono<Void>`.
- Ứng dụng có thể tắt tính năng bằng `lab.audit.enabled=false`.
- Người dùng có thể tự khai báo bean để thay thế default của starter.
- Nếu cả MVC và WebFlux xuất hiện trên classpath, **loại ApplicationContext thực tế** vẫn phải quyết định điều kiện `@ConditionalOnWebApplication`, không chỉ sự hiện diện của dependency.

Hai công cụ phù hợp ở Spring Boot 3.3 là **`WebApplicationContextRunner`** và **`ReactiveWebApplicationContextRunner`**. Chúng tạo ra các web application contexts có kiểm soát, áp dụng chính auto-configurations cần kiểm tra, thay đổi môi trường/property/user bean per test rồi tự đóng context sau callback.

Bài học thuộc nhóm **Kiểm thử auto-configuration**, tập trung trực tiếp vào **“WebApplicationContextRunner và ReactiveWebApplicationContextRunner”**. Ví dụ dùng **Java 17+**, **Spring Boot 3.3.5**, **Spring Framework 6.1** và JUnit Jupiter. Đây là bộ test cho một thư viện auto-configuration; không cần chạy HTTP server hoặc sử dụng Docker.

### Sau bài học, bạn có thể

1. Phân biệt `ApplicationContextRunner`, `WebApplicationContextRunner` và `ReactiveWebApplicationContextRunner`.
2. Tạo Servlet web context với `MockServletContext` và reactive web context tương ứng.
3. Kiểm tra `@ConditionalOnWebApplication(type=SERVLET/REACTIVE)` đúng trong cả hai môi trường.
4. Dùng `AutoConfigurations.of(...)` để chỉ nạp auto-configuration under test.
5. Dùng `withPropertyValues(...)` để kiểm tra default, disabled, custom values và property không hợp lệ.
6. Dùng `withUserConfiguration(...)` hoặc `withBean(...)` để kiểm chứng `@ConditionalOnMissingBean` back-off.
7. Dùng AssertJ kiểm tra bean có mặt/vắng mặt, cấu hình và hành vi nhỏ của bean.
8. Tách kiểm thử **điều kiện tạo bean** khỏi kiểm thử MVC HandlerMapping hoặc WebFlux filter chain thật.
9. Hiểu các điểm cần bổ sung cho `@ConditionalOnClass`, cấu hình classpath tùy chọn, production starter registration và condition evaluation reports.
10. Viết test ngắn, độc lập mà không cần mở toàn bộ `@SpringBootTest` cho mỗi tổ hợp điều kiện.

## 2. Ba runner: chọn công cụ theo ApplicationContext

| Runner | Context chính | Phù hợp với | Không tự làm |
| --- | --- | --- | --- |
| `ApplicationContextRunner` | `AnnotationConfigApplicationContext` không-web | Auto-config chung: cache, service, repository policy | Không tự tạo Servlet/Reactive web context |
| `WebApplicationContextRunner` | Servlet `ConfigurableWebApplicationContext` với mock ServletContext | `@ConditionalOnWebApplication(SERVLET)`, `HandlerInterceptor`, Servlet beans | Không tự chạy embedded Tomcat/HTTP request |
| `ReactiveWebApplicationContextRunner` | `ConfigurableReactiveWebApplicationContext` | `@ConditionalOnWebApplication(REACTIVE)`, WebFlux `WebFilter`, reactive infrastructure | Không tự dựng Netty/WebFlux HTTP pipeline đầy đủ |

Một runner tạo **context mới cho mỗi lần `run(...)`**, và đóng nó sau khi callback hoàn thành. Không cần `@DirtiesContext` hay `Thread.sleep` để quản lý lifecycle trong ví dụ.

```text
JUnit @Test
    |
    +-- runner.withConfiguration(AutoConfigurations.of(...))
    |        |
    |        +-- withPropertyValues("lab.audit.enabled=true")
    |        +-- withUserConfiguration(UserOverrides.class)
    |        +-- withBean(...), nếu test cần
    |
    +-- run(context -> {
             assertThat(context).hasSingleBean(...);
             assertThat(context).doesNotHaveBean(...);
         })
         |
         +-- context được đóng khi run kết thúc
```

### Lý do không dùng ApplicationContextRunner cho mọi thứ

`@ConditionalOnWebApplication` quan sát **web application context/environment** chứ không chỉ có `spring-webmvc` hay `spring-webflux` trên classpath. Một `ApplicationContextRunner` thường phải làm hai web-only auto-configurations **không match**. Đây là một negative test rất có giá trị; nếu một web-only bean xuất hiện trong plain context, guard của auto-configuration có thể đã sai hoặc quá rộng.

## 3. Servlet và Reactive là hai kiểu điều kiện khác nhau

Spring Boot có:

```java
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET)
```

và:

```java
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.REACTIVE)
```

Đây là **snippets annotation**, chưa phải lớp Java độc lập. `Type.ANY` dùng khi cả Servlet và Reactive đều chấp nhận được, nhưng nếu bean thực sự gọi API của `HttpServletRequest` thì không nên dùng ANY.

| Môi trường | SERVLET condition | REACTIVE condition |
| --- | --- | --- |
| `WebApplicationContextRunner` | Match | Không match |
| `ReactiveWebApplicationContextRunner` | Không match | Match |
| `ApplicationContextRunner` | Không match | Không match |

Bảng mô tả **ngữ cảnh runner mặc định của Spring Boot 3.3** và auto-configurations của demo. Nếu ứng dụng có custom context factory/parent context, cần xác minh type/environment cụ thể của test.

### Có cả spring-webmvc và spring-webflux trên classpath thì sao?

Trong ứng dụng Boot thông thường, **nếu cả MVC lẫn WebFlux có mặt, Boot ưu tiên Servlet/MVC** khi tự suy luận web application type. Điều này không có nghĩa reactive auto-configuration phải kích hoạt trong một Servlet context.

Với runner, bạn **chọn loại context tường minh**: `new WebApplicationContextRunner()` hoặc `new ReactiveWebApplicationContextRunner()`. Khi cần test cả hai nhánh của một starter, hãy dùng hai runner; đừng cố thay đổi `spring.main.web-application-type=reactive` trong một plain `ApplicationContextRunner` rồi nghĩ nó đã tự biến thành reactive context.

Đối với full `@SpringBootTest` có cả hai starters, muốn ép reactive test cần cấu hình `spring.main.web-application-type=reactive` theo hướng dẫn Boot; đây là vấn đề **khác** runner tự chọn context factory.

## 4. Testing auto-configuration khác testing controller endpoint

`WebApplicationContextRunner` **không phải** `MockMvc` và `ReactiveWebApplicationContextRunner` **không phải** `WebTestClient`. Trong bài này:

- Ta kiểm tra bean có được đăng ký theo đúng loại web application không.
- Ta kiểm tra default bean biến mất khi feature disabled hoặc user override.
- Ta kiểm tra method `ServletAuditInterceptor.preHandle(...)` bằng mock request/response riêng.
- Ta kiểm tra `ReactiveAuditFilter.filter(...)` bằng `MockServerWebExchange` và `Mono.empty()`.
- Ta **không** kết luận một request HTTP đã đi qua DispatcherServlet/HandlerMapping hoặc WebFlux `WebHttpHandlerBuilder`.

Nếu cần bảo vệ annotation routing, JSON binding, MVC interceptors được thực sự add vào registry hoặc WebFlux filter ordering, hãy bổ sung `@WebMvcTest`, `@WebFluxTest`, `MockMvc`, `WebTestClient` hoặc integration test với full configuration.

## 5. Những điều kiện thường đặt trên auto-configuration

Một auto-configuration tốt thường có nhiều lớp điều kiện:

| Điều kiện | Vai trò | Test cần có |
| --- | --- | --- |
| `@ConditionalOnWebApplication(type=...)` | Chọn đúng web stack | Servlet/Reactive/non-web contexts |
| `@ConditionalOnClass(SomeType.class)` | Chỉ khi thư viện optional có mặt | Classpath-present và simulated-absent |
| `@ConditionalOnProperty` | Bật/tắt bằng property | Default, true, false, unexpected value |
| `@ConditionalOnMissingBean` | Người dùng override default | `withUserConfiguration` hoặc `withBean` |
| `@ConditionalOnBean` | Đòi một collaborator có sẵn | Có/không có bean dependency |
| `@ConditionalOnResource` | Chỉ khi resource tồn tại | Resource/classpath simulation |
| `@ConditionalOnNotWebApplication` | Chỉ chạy trong môi trường không-web | Plain runner vs web runners |

**`@ConditionalOnMissingBean` phụ thuộc thứ tự xử lý bean definitions.** Spring Boot khuyến nghị đặt loại condition này trong auto-configuration để auto-config được xử lý **sau user-defined configuration**. Không đặt một fallback bean trong regular `@Configuration` bất kỳ rồi giả định nó sẽ tự nhường cho user bean được khai báo sau.

## 6. Cấu trúc project Java 17+ đầy đủ

Ví dụ tạo một **library-like module**, không có `@SpringBootApplication` và không có runnable main method: mục tiêu là chạy **Gradle tests** để xác minh hai auto-configurations. Module có file khai báo imports để người dùng có thể đóng gói dưới dạng starter/autoconfigure JAR.

```text
web-context-runner-lab/
├── settings.gradle
├── build.gradle
├── src/main/
│   ├── java/com/example/audit/
│   │   ├── servlet/ServletAuditInterceptor.java
│   │   ├── reactive/ReactiveAuditFilter.java
│   │   └── autoconfigure/
│   │       ├── ServletAuditAutoConfiguration.java
│   │       └── ReactiveAuditAutoConfiguration.java
│   └── resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── src/test/java/com/example/audit/
    └── AuditAutoConfigurationTests.java
```

**Lưu ý về đóng gói:** hai classes `@AutoConfiguration` nằm trong package `com.example.audit.autoconfigure`. Thư viện production không được dựa vào component scanning tùy ý để tìm chúng: Spring Boot sử dụng file `AutoConfiguration.imports`. Trong tests, `AutoConfigurations.of(...)` chọn đích trực tiếp. Vì là library module, Gradle `bootJar` bị tắt và plain `jar` được bật, tránh lỗi thiếu main class khi build.

Bài đặt cả MVC và WebFlux dependencies trong **một lab** để có thể test cả hai loại context. Một production starter nên tách optional dependencies/variants cho gọn và không kéo cả hai web stacks vào ứng dụng nếu không cần; ở đây đây là lựa chọn học tập có chủ đích.

## 7. settings.gradle và build.gradle

### settings.gradle

```groovy
rootProject.name = 'web-context-runner-lab'
```

### build.gradle

```groovy
plugins {
    id 'java-library'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('bootJar') {
    enabled = false
}

tasks.named('jar') {
    enabled = true
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

### Tại sao dependency như vậy?

- `spring-boot-starter-web`: Servlet API, Spring MVC `HandlerInterceptor` và Boot autoconfigure classes.
- `spring-boot-starter-webflux`: Spring WebFlux `WebFilter`, Reactor `Mono` và reactive web context support.
- `spring-boot-starter-test`: context runners, AssertJ, Spring Test mock Servlet/Reactive request types và JUnit Jupiter.
- `junit-platform-launcher`: hỗ trợ Gradle/JUnit Platform.
- `java-library`: phù hợp cấu trúc library, không yêu cầu một executable application.

**Không chạy `bootRun`** từ project này: không có class main. Chạy `gradle test` hoặc `gradle build`. Với ứng dụng Spring Boot thật, hãy dùng một app project riêng làm consumer của thư viện auto-config này.

Nếu chưa có Gradle Wrapper, dùng Gradle cài sẵn tương thích hoặc tạo Wrapper bằng tooling dự án; không coi lỗi `./gradlew: file not found` là lỗi của test code.

## 8. ServletAuditInterceptor.java

`src/main/java/com/example/audit/servlet/ServletAuditInterceptor.java`:

```java
package com.example.audit.servlet;

import java.util.Objects;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

public final class ServletAuditInterceptor
        implements HandlerInterceptor {

    private final String headerValue;

    public ServletAuditInterceptor(String headerValue) {
        this.headerValue = Objects.requireNonNull(headerValue);
    }

    public String headerValue() {
        return headerValue;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        response.setHeader("X-Audit-Mode", headerValue);
        return true;
    }
}
```

Đây là một **Servlet HandlerInterceptor** thực: `preHandle(...)` chạy trước khi controller handler được gọi (nếu interceptor đã được đăng ký trong MVC interceptor registry). Demo viết response header và cho phép request tiếp tục.

**Phân biệt bean registration với MVC registration:** chỉ có một bean type `HandlerInterceptor` **không tự chứng minh** interceptor đã được thêm vào mọi MVC `HandlerMapping`. Với production, cần một `WebMvcConfigurer.addInterceptors(...)` hoặc cơ chế MVC registration phù hợp. Bộ test runner sẽ xác nhận interceptor bean được tạo/hoạt động; integration test riêng phải xác nhận nó thật sự chạy trong HTTP pipeline.

### Tại sao return true?

`true` nghĩa là cho phép tiếp tục xử lý handler chain. Nếu trả `false`, request sẽ bị dừng ở interceptor; khi ấy phải có một response/status phù hợp. Bài này chỉ thêm header không thay đổi control flow.

### Đừng ghi PII vào X-Audit-Mode

Header trong bài là chuỗi cố định `servlet-default` hoặc `custom`, không chứa access token, username hoặc request body. Production audit logic phải xem xét an toàn/logging/PII riêng; không đưa secrets vào response headers.

## 9. ReactiveAuditFilter.java

`src/main/java/com/example/audit/reactive/ReactiveAuditFilter.java`:

```java
package com.example.audit.reactive;

import java.util.Objects;

import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class ReactiveAuditFilter implements WebFilter {

    private final String headerValue;

    public ReactiveAuditFilter(String headerValue) {
        this.headerValue = Objects.requireNonNull(headerValue);
    }

    public String headerValue() {
        return headerValue;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse()
                .getHeaders()
                .set("X-Audit-Mode", headerValue);

        return chain.filter(exchange);
    }
}
```

`WebFilter` là một phần của **Spring WebFlux reactive web pipeline**. Nó nhận `ServerWebExchange` và `WebFilterChain`, trả về `Mono<Void>`. Đây không phải `jakarta.servlet.Filter` và cũng không dùng `HttpServletRequest`.

Trong lab, logic nhỏ được gọi trực tiếp trong test với một mock WebExchange. Trong full reactive application, việc filter bean có tham gia vào pipeline còn phụ thuộc WebFlux infrastructure; muốn xác nhận network/request integration và ordering thì bổ sung `WebTestClient` hoặc real HTTP integration test.

### Vì sao không block() trong production filter?

Filter return `chain.filter(exchange)` để giữ reactive composition. Không chèn `block()` trong handler/filter production. Test có thể gọi `.block(Duration.ofSeconds(2))` trên **Mono mock hoàn thành ngay** để đợi test observable side effect; đó là code test, không phải mẫu xử lý request reactive ngoài đời thực.

## 10. ServletAuditAutoConfiguration.java

`src/main/java/com/example/audit/autoconfigure/ServletAuditAutoConfiguration.java`:

```java
package com.example.audit.autoconfigure;

import com.example.audit.servlet.ServletAuditInterceptor;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.web.servlet.HandlerInterceptor;

@AutoConfiguration
@ConditionalOnClass(HandlerInterceptor.class)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnProperty(
        prefix = "lab.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class ServletAuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ServletAuditInterceptor.class)
    ServletAuditInterceptor servletAuditInterceptor(
            Environment environment) {

        String label = environment.getProperty(
                "lab.audit.label", "servlet-default");

        return new ServletAuditInterceptor(label);
    }
}
```

### Các điều kiện hoạt động như thế nào?

- `@AutoConfiguration`: lớp là ứng viên auto-configuration, không phải controller, service hay component do scan tình cờ tìm thấy.
- `@ConditionalOnClass(HandlerInterceptor.class)`: cần có Spring MVC integration API.
- `@ConditionalOnWebApplication(Type.SERVLET)`: không kích hoạt trong reactive hoặc plain contexts.
- `@ConditionalOnProperty(...)`: bật khi flag `lab.audit.enabled=true`, và **bật mặc định khi flag vắng mặt** vì `matchIfMissing=true`.
- `@ConditionalOnMissingBean(ServletAuditInterceptor.class)`: nếu người dùng đã khai báo một bean đúng type này, starter **không tạo default bean trùng**.
- `Environment.getProperty("lab.audit.label", "servlet-default")`: lấy label có thể override ở mỗi test, không hardcode một test-only value vào production config.
- Bean method trả **concrete type** `ServletAuditInterceptor` để Spring nhìn thấy type khi đánh giá missing-bean condition.

### Vì sao không bật bean chỉ bằng @ConditionalOnClass?

Nếu chỉ kiểm tra MVC `HandlerInterceptor` có trên classpath, một app WebFlux **đồng thời phụ thuộc spring-webmvc** có thể vô tình nhận Servlet bean không tương thích. Web-type condition là phần thiết yếu khi tính năng chỉ chạy một stack cụ thể.

### Custom bean và thứ tự

`@ConditionalOnMissingBean` được đặt trong auto-configuration do Boot load sau user-defined bean definitions. Test ở phần sau dùng `withUserConfiguration(...)` để bảo đảm starter backs off. Không dùng `spring.main.allow-bean-definition-overriding=true` như cách tránh duplicate beans: nó che một lỗi thiết kế mà back-off condition phải giải quyết.

## 11. ReactiveAuditAutoConfiguration.java

`src/main/java/com/example/audit/autoconfigure/ReactiveAuditAutoConfiguration.java`:

```java
package com.example.audit.autoconfigure;

import com.example.audit.reactive.ReactiveAuditFilter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.web.server.WebFilter;

@AutoConfiguration
@ConditionalOnClass(WebFilter.class)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE)
@ConditionalOnProperty(
        prefix = "lab.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class ReactiveAuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReactiveAuditFilter.class)
    ReactiveAuditFilter reactiveAuditFilter(
            Environment environment) {

        String label = environment.getProperty(
                "lab.audit.label", "reactive-default");

        return new ReactiveAuditFilter(label);
    }
}
```

Các điều kiện tương tự servlet nhưng **Reactive type** và **WebFilter class**. Khi test chạy bằng `ReactiveWebApplicationContextRunner`, nó có thể tạo `ReactiveAuditFilter`, không tạo `ServletAuditInterceptor`. Khi test chạy bằng `WebApplicationContextRunner`, kết quả ngược lại.

Cả hai auto-configuration dùng chung `lab.audit.enabled` và `lab.audit.label` để dễ so sánh, nhưng mỗi nhánh có default label riêng. Trong một starter production, namespace cần đủ đặc thù với tổ chức/library, tránh dùng `spring.*` hoặc `server.*` cho custom settings; `lab.audit.*` chỉ là namespace học tập.

### Vì sao không tạo bean type WebFilter trực tiếp?

Bean method khai báo trả `ReactiveAuditFilter` cụ thể giúp `@ConditionalOnMissingBean(ReactiveAuditFilter.class)` hoạt động rõ. Nếu trả generic `WebFilter` và khi có nhiều filters khác trong app, việc điều kiện hóa theo toàn bộ `WebFilter` có thể vô tình tắt audit filter chỉ vì có security filter hoặc tracing filter không liên quan. Chọn bean condition theo feature-specific type hoặc qualifier/marker phù hợp.

## 12. Đăng ký auto-configurations bằng file imports

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
com.example.audit.autoconfigure.ServletAuditAutoConfiguration
com.example.audit.autoconfigure.ReactiveAuditAutoConfiguration
```

Spring Boot 3.x tìm ứng viên auto-configuration trong file này khi ứng dụng consumer bật `@EnableAutoConfiguration` (thường qua `@SpringBootApplication`). Đây là cách register production starter đúng; **không dùng `spring.factories` theo kiểu đăng ký auto-config của tutorial Spring Boot 2.0 cũ**.

Trong test runner, ta vẫn chọn explicit:

```java
.withConfiguration(AutoConfigurations.of(
        ServletAuditAutoConfiguration.class,
        ReactiveAuditAutoConfiguration.class))
```

Điều này giới hạn context ở chính các auto-configurations muốn kiểm tra; runner không khởi động tất cả Spring Boot auto-config classes chỉ vì file imports tồn tại. **Phân biệt** cách production discovery và cách test explicit selection là yếu tố quan trọng trong kiểm thử starter.

### Tại sao không đặt @AutoConfiguration trong component scan?

Nếu app `@SpringBootApplication` nằm ở package cha chứa starter `@AutoConfiguration` và scan bao trùm nó, auto-config có thể được xử lý như regular configuration **trước** user bean definitions. Khi ấy `@ConditionalOnMissingBean` có thể đánh giá sai và mất khả năng back off. Với starter, đặt auto-config trong package riêng không nằm dưới component scan ứng dụng, và nạp qua imports.

## 13. Test class đầy đủ: cả Servlet, Reactive và non-web

Tạo `src/test/java/com/example/audit/AuditAutoConfigurationTests.java`:

```java
package com.example.audit;

import java.time.Duration;

import com.example.audit.autoconfigure.ReactiveAuditAutoConfiguration;
import com.example.audit.autoconfigure.ServletAuditAutoConfiguration;
import com.example.audit.reactive.ReactiveAuditFilter;
import com.example.audit.servlet.ServletAuditInterceptor;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.server.MockServerWebExchange;

import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final WebApplicationContextRunner servletRunner =
            new WebApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ServletAuditAutoConfiguration.class,
                            ReactiveAuditAutoConfiguration.class));

    private final ReactiveWebApplicationContextRunner reactiveRunner =
            new ReactiveWebApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ServletAuditAutoConfiguration.class,
                            ReactiveAuditAutoConfiguration.class));

    private final ApplicationContextRunner plainRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ServletAuditAutoConfiguration.class,
                            ReactiveAuditAutoConfiguration.class));

    @Test
    void servletRunnerCreatesOnlyServletBean() {
        servletRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(ServletAuditInterceptor.class);
            assertThat(context)
                    .doesNotHaveBean(ReactiveAuditFilter.class);
            assertThat(context.getBean(
                    ServletAuditInterceptor.class).headerValue())
                    .isEqualTo("servlet-default");
        });
    }

    @Test
    void reactiveRunnerCreatesOnlyReactiveBean() {
        reactiveRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(ReactiveAuditFilter.class);
            assertThat(context)
                    .doesNotHaveBean(ServletAuditInterceptor.class);
            assertThat(context.getBean(
                    ReactiveAuditFilter.class).headerValue())
                    .isEqualTo("reactive-default");
        });
    }

    @Test
    void plainRunnerCreatesNeitherWebBean() {
        plainRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .doesNotHaveBean(ServletAuditInterceptor.class);
            assertThat(context)
                    .doesNotHaveBean(ReactiveAuditFilter.class);
        });
    }

    @Test
    void servletFeatureCanBeDisabledByProperty() {
        servletRunner
                .withPropertyValues("lab.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(ServletAuditInterceptor.class);
                    assertThat(context)
                            .doesNotHaveBean(ReactiveAuditFilter.class);
                });
    }

    @Test
    void reactiveFeatureCanBeDisabledByProperty() {
        reactiveRunner
                .withPropertyValues("lab.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(ReactiveAuditFilter.class);
                    assertThat(context)
                            .doesNotHaveBean(ServletAuditInterceptor.class);
                });
    }

    @Test
    void servletLabelComesFromEnvironment() {
        servletRunner
                .withPropertyValues("lab.audit.label=servlet-custom")
                .run(context -> {
                    assertThat(context).hasSingleBean(
                            ServletAuditInterceptor.class);
                    assertThat(context.getBean(
                            ServletAuditInterceptor.class).headerValue())
                            .isEqualTo("servlet-custom");
                });
    }

    @Test
    void reactiveLabelComesFromEnvironment() {
        reactiveRunner
                .withPropertyValues("lab.audit.label=reactive-custom")
                .run(context -> {
                    assertThat(context).hasSingleBean(
                            ReactiveAuditFilter.class);
                    assertThat(context.getBean(
                            ReactiveAuditFilter.class).headerValue())
                            .isEqualTo("reactive-custom");
                });
    }

    @Test
    void servletAutoConfigBacksOffForUserConfiguration() {
        servletRunner
                .withUserConfiguration(UserServletOverride.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            ServletAuditInterceptor.class);
                    assertThat(context)
                            .doesNotHaveBean("servletAuditInterceptor");
                    assertThat(context.getBean(
                            ServletAuditInterceptor.class).headerValue())
                            .isEqualTo("app-servlet");
                });
    }

    @Test
    void reactiveAutoConfigBacksOffForUserBean() {
        reactiveRunner
                .withBean(
                        ReactiveAuditFilter.class,
                        () -> new ReactiveAuditFilter("app-reactive"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(ReactiveAuditFilter.class);
                    assertThat(context)
                            .doesNotHaveBean("reactiveAuditFilter");
                    assertThat(context.getBean(
                            ReactiveAuditFilter.class).headerValue())
                            .isEqualTo("app-reactive");
                });
    }

    @Test
    void servletInterceptorSetsResponseHeader()
            throws Exception {
        servletRunner.run(context -> {
            ServletAuditInterceptor interceptor = context.getBean(
                    ServletAuditInterceptor.class);
            MockHttpServletRequest request =
                    new MockHttpServletRequest("GET", "/test");
            MockHttpServletResponse response =
                    new MockHttpServletResponse();

            assertThat(interceptor.preHandle(
                    request, response, new Object())).isTrue();
            assertThat(response.getHeader("X-Audit-Mode"))
                    .isEqualTo("servlet-default");
        });
    }

    @Test
    void reactiveWebFilterSetsResponseHeader() {
        reactiveRunner.run(context -> {
            ReactiveAuditFilter filter = context.getBean(
                    ReactiveAuditFilter.class);
            MockServerWebExchange exchange =
                    MockServerWebExchange.from(
                            MockServerHttpRequest.get("/test"));

            filter.filter(
                    exchange,
                    ignored -> Mono.empty())
                    .block(Duration.ofSeconds(2));

            assertThat(exchange.getResponse()
                    .getHeaders()
                    .getFirst("X-Audit-Mode"))
                    .isEqualTo("reactive-default");
        });
    }

    @Test
    void modifiedRunnerDoesNotMutateBaseRunner() {
        WebApplicationContextRunner customized =
                servletRunner.withPropertyValues(
                        "lab.audit.label=one-test-only");

        customized.run(context ->
                assertThat(context.getBean(
                        ServletAuditInterceptor.class).headerValue())
                        .isEqualTo("one-test-only"));

        servletRunner.run(context ->
                assertThat(context.getBean(
                        ServletAuditInterceptor.class).headerValue())
                        .isEqualTo("servlet-default"));
    }

    @Test
    void nonTrueEnabledValueDoesNotMatchCondition() {
        reactiveRunner
                .withPropertyValues(
                        "lab.audit.enabled=unexpected")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(ReactiveAuditFilter.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserServletOverride {

        @Bean
        ServletAuditInterceptor customServletInterceptor() {
            return new ServletAuditInterceptor("app-servlet");
        }
    }
}
```

**Số lượng: 13 phương thức `@Test`**. Ba runner là fields độc lập, nhưng mỗi test gọi `run(...)` để tạo context mới. Không có `@SpringBootTest`, `@BeforeEach`, database hoặc embedded server cần quản lý thủ công.

### Kiểm tra type cụ thể chứ không chỉ bean name

Test `servletRunnerCreatesOnlyServletBean` assert có đúng một `ServletAuditInterceptor` và **không có** `ReactiveAuditFilter`. Ngược lại, `reactiveRunnerCreatesOnlyReactiveBean` assert đúng một reactive filter và không có Servlet interceptor. `plainRunnerCreatesNeitherWebBean` kiểm tra guard không-web. Kết quả này mạnh hơn chỉ assert `context.isActive()`.

### Kiểm tra back-off chứ không chỉ default

Hai tests custom bean quan trọng vì auto-configuration thường là **default cho người dùng**, không phải một bean được phép ghi đè mọi lựa chọn.

- `withUserConfiguration(UserServletOverride.class)` tạo bean `customServletInterceptor` trước khi auto-configuration fallback được đánh giá.
- `withBean(ReactiveAuditFilter.class, supplier)` đăng ký direct user bean; default `reactiveAuditFilter` không được tạo.
- Assert **hasSingleBean** bắt lỗi hai instances cùng type khi `@ConditionalOnMissingBean` bị loại bỏ.
- Assert **doesNotHaveBean("servletAuditInterceptor")` / `doesNotHaveBean("reactiveAuditFilter")`** kiểm tra fallback bean không tồn tại, không chỉ suy từ value.

### Kiểm tra hành vi nhưng không bịa HTTP transport

Servlet test dùng `MockHttpServletRequest`/`MockHttpServletResponse` rồi gọi chính method `preHandle(...)`. Reactive test dùng `MockServerWebExchange` và một `WebFilterChain` lambda trả `Mono.empty()`. Chúng xác nhận **bean behavior** trong JVM; không có HTTP socket/embedded server thực.

### Kiểm tra không rò cấu hình giữa tests

`withPropertyValues(...)` **trả một runner được tùy chỉnh**, không sửa mọi context đã tạo trước đó. Test `modifiedRunnerDoesNotMutateBaseRunner` chạy một context với label custom và một context mới từ runner gốc, kiểm tra giá trị mặc định còn nguyên. Đây là cơ sở để viết nhiều scenario tests không cần `@DirtiesContext`.

## 14. Lưu ý về test scope và run lifecycle

Runner giữ **công thức tạo context**, không giữ một shared live context giữa test methods. Mỗi `run(context -> ...)`:

1. Chuẩn bị một context factory theo loại runner.
2. Áp dụng user configurations, auto-configurations và properties.
3. Refresh context, kích hoạt conditions và tạo beans phù hợp.
4. Chạy callback với assertable context.
5. Đóng context dù assertions thất bại theo lifecycle của utility.

Không nên giữ tham chiếu một bean từ callback rồi sử dụng sau khi `run` kết thúc, vì bean/context có thể đã bị đóng. Những singleton beans có lifecycle resources (connection pools, schedulers, threads) cần được cleanup khi context đóng; runner không tự làm những external side effects ngoài Spring lifecycle.

Nếu test cần kiểm tra `@PreDestroy` hoặc đóng resource, có thể ghi nhận event bằng helper bên ngoài context và assert sau `run`, nhưng phải giữ isolation giữa tests.

### ContextRunner khác @SpringBootTest cache

`@SpringBootTest` dùng Spring TestContext cache để có thể tái sử dụng contexts giữa nhiều tests có cấu hình giống nhau. ContextRunner tối ưu cho nhiều **tổ hợp điều kiện nhỏ**, mỗi lần chạy context độc lập và đóng ngay. Nó không tự bật toàn bộ Boot auto-config của một executable app.

## 15. withConfiguration(AutoConfigurations.of(...)) dùng để làm gì?

Trong demo:

```java
.withConfiguration(AutoConfigurations.of(
    ServletAuditAutoConfiguration.class,
    ReactiveAuditAutoConfiguration.class))
```

là cách đưa **auto-configuration candidates** vào context runner theo semantics của Spring Boot, để chúng được đánh giá giống cơ chế auto-config thông thường, gồm ordering/conditions.

**Không nhầm với `withUserConfiguration(...)`**:

| API | Dùng cho | Ví dụ |
| --- | --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Auto-configurations muốn test | Servlet/ReactiveAuditAutoConfiguration |
| `withUserConfiguration(...)` | Regular user `@Configuration` muốn kiểm tra override | UserServletOverride |
| `withBean(Type.class, supplier)` | Một bean user-defined nhỏ | ReactiveAuditFilter("app-reactive") |
| `withPropertyValues("k=v")` | External configuration theo scenario | lab.audit.enabled=false |
| `withClassLoader(...)` | Simulate classpath availability | FilteredClassLoader cho optional library |
| `withInitializer(...)` | Condition report/logging hoặc custom initializer | ConditionEvaluationReportLoggingListener |
| `withParent(...)` | Parent-child context scenarios | Parent bean search/visibility |
| `run(...)` | Execute và assert trong callback | hasSingleBean/doesNotHaveBean |

Nếu auto-configuration của starter phụ thuộc `JacksonAutoConfiguration`, `WebMvcAutoConfiguration` hay `CodecAutoConfiguration`, cần đưa đúng các dependencies đó vào `AutoConfigurations.of(...)` khi muốn test integration giữa chúng. Nhưng **không import cả Boot auto-config catalog** để sửa một lỗi test, vì điều đó làm mất kiểm soát môi trường/độ nhanh của runner.

## 16. @ConditionalOnProperty: matchIfMissing và havingValue

Trong hai auto-config classes:

```java
@ConditionalOnProperty(
    prefix = "lab.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
```

nghĩa là:

| lab.audit.enabled | Kỳ vọng |
| --- | --- |
| Không khai báo | Enabled, do `matchIfMissing=true` |
| `true` | Enabled |
| `false` | Disabled |
| `unexpected` | Không match vì `havingValue="true"` |

`@ConditionalOnProperty` không phải một validator cho mọi kiểu dữ liệu; nó kiểm tra giá trị property theo semantics condition. Nếu cần một config property typed như `Duration timeout` hoặc `URI endpoint`, dùng `@ConfigurationProperties` với validation riêng. Đừng chỉ xem condition match để kết luận value hợp lệ.

Trong test, thêm một property bằng:

```java
servletRunner
    .withPropertyValues(
        "lab.audit.enabled=true",
        "lab.audit.label=my-label")
    .run(context ->
        assertThat(context.getBean(
            ServletAuditInterceptor.class).headerValue())
            .isEqualTo("my-label"));
```

Đây là **snippet trực tiếp dùng fields từ test class**; không phải file test độc lập. Giá trị từ `withPropertyValues` nằm trong context riêng của lần chạy, không ghi `application.yml` hay system properties.

### Vì sao custom value phải được kiểm tra thực tế?

Một test `hasSingleBean` sẽ vẫn PASS nếu implementation vô tình bỏ qua `lab.audit.label` và luôn dùng default. Assertion `headerValue()==custom` buộc auto-config thật dùng Spring Environment đúng.

## 17. @ConditionalOnMissingBean: đúng type, đúng thời điểm

Spring Boot định nghĩa `@ConditionalOnMissingBean` để cung cấp fallback khi user chưa có bean. Trong demo, điều kiện đặt **trên bean method** với type cụ thể:

```java
@Bean
@ConditionalOnMissingBean(ServletAuditInterceptor.class)
ServletAuditInterceptor servletAuditInterceptor(
        Environment environment) {
    return new ServletAuditInterceptor(
            environment.getProperty(
                    "lab.audit.label", "servlet-default"));
}
```

Nếu user config có:

```java
@Bean
ServletAuditInterceptor customServletInterceptor() {
    return new ServletAuditInterceptor("app-servlet");
}
```

thì fallback auto-config không nên tạo một bean thứ hai. Test kiểm tra both type count và bean name.

### Cảnh báo về thứ tự đăng ký

Condition trên bean nhìn vào **definitions đã được xử lý tại thời điểm đánh giá**, không scan trước toàn bộ tương lai. Spring Boot khuyến nghị `@ConditionalOnMissingBean` trong auto-configurations do chúng được xử lý sau regular user configuration. Nếu bạn đặt condition fallback trong một `@Configuration` thường rồi import sai thứ tự, back-off có thể không đúng như production.

### Đừng dùng Allow Bean Definition Overriding để che lỗi

`withAllowBeanDefinitionOverriding(true)` hoặc property `spring.main.allow-bean-definition-overriding=true` có thể khiến hai definitions cùng tên ghi đè nhau tùy ordering. Đó không phải bằng chứng auto-configuration được thiết kế đúng. Ưu tiên condition back-off và test assertions `hasSingleBean`.

## 18. @ConditionalOnClass và FilteredClassLoader

`@ConditionalOnClass` cho phép một starter chỉ kích hoạt khi thư viện tùy chọn xuất hiện. Hai auto configs kiểm tra các loại API:

- Servlet branch: `HandlerInterceptor.class`.
- Reactive branch: `WebFilter.class`.

Trong lab cả hai starters đều nằm trên classpath, nên **bài test chính không mô phỏng thiếu dependency**. Để kiểm tra optional classpath, Spring Boot cung cấp `FilteredClassLoader` cùng `runner.withClassLoader(...)`.

Một pattern minh họa cho **một auto-configuration khác** (không phải file runnable của lab vì `VendorClientAutoConfiguration`/`VendorClient` chưa được định nghĩa):

```java
new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        VendorClientAutoConfiguration.class))
    .withClassLoader(
        new FilteredClassLoader(VendorClient.class))
    .run(context ->
        assertThat(context).doesNotHaveBean("vendorClient"));
```

### Bẫy class loading của optional API

Không chỉ thêm một `@ConditionalOnClass` vào `@Bean` method có return type của một library **đang vắng mặt**; JVM có thể phải resolve return types trong quá trình đọc method metadata trước khi method-level condition được áp dụng. Spring Boot khuyến nghị đặt điều kiện classpath ở **class-level** hoặc một nested `@Configuration` được cô lập, tránh lỗi `NoClassDefFoundError` trước khi condition làm việc.

Ví dụ kiến trúc:

```java
@AutoConfiguration
class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.api.Client")
    static class VendorPresentConfiguration {

        // @Bean Client client(...) chỉ nằm trong
        // class riêng được condition ở cấp class.
    }
}
```

Đây là **snippet kiến trúc**; `com.vendor.api.Client` chưa được thêm vào project. Không tuyên bố đoạn này compile độc lập thành runnable code.

`FilteredClassLoader` mô phỏng classpath visibility, không thay thế việc chạy một module consumer thực sự thiếu dependency trong build. Với auto-config phức tạp, test thêm bản consumer nhỏ chỉ có optional classpath cần thiết để bắt lỗi linkage.

## 19. ConditionEvaluationReport và chẩn đoán tại sao bean vắng mặt

Khi một test `doesNotHaveBean(...)` PASS, cần hiểu vì sao nó vắng mặt:

- Web type không match?
- Property flag tắt?
- Optional class không tồn tại?
- User bean khiến auto-config backs off?
- Dependency bean vắng mặt hoặc auto-config ordering sai?

Spring Boot cung cấp `ConditionEvaluationReport` và logging listener:

```java
new WebApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        ServletAuditAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(
            LogLevel.INFO))
    .run(context -> {
        assertThat(context).hasNotFailed();
    });
```

**Snippet này cần imports**:
`org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener`,
`org.springframework.boot.logging.LogLevel`,
`WebApplicationContextRunner` và `AutoConfigurations`. Nó dùng auto-config class từ project. Log report phụ thuộc logger configuration; không coi sự xuất hiện một dòng text cố định là assertion bắt buộc.

### Đọc trực tiếp report

Có thể lấy report từ bean factory của source context, ví dụ kiến trúc:

```java
ConditionEvaluationReport report =
    ConditionEvaluationReport.get(
        context.getSourceApplicationContext().getBeanFactory());
```

Phải có `context` từ callback runner, import `ConditionEvaluationReport` và dùng API tương ứng chính xác của Spring Boot version. Đây là snippet debug, **không thuộc 13 methods trong project**. Khi cần assert một condition cụ thể, xét `report.getConditionAndOutcomesBySource()`, nhưng tránh test quá chặt vào wording của message — text báo cáo có thể thay đổi giữa versions.

### Đừng đoán nguyên nhân chỉ từ missing bean

Nếu context startup thất bại, assert bean vắng mặt có thể che lỗi gốc; hãy kiểm tra `assertThat(context).hasNotFailed()` trước hoặc lấy `context.getStartupFailure()` để xem root cause. Nếu ConditionEvaluationReport nói classpath mismatch thì sửa dependency/guard, không đổi expected value cho test xanh.

## 20. Cách kiểm tra context startup failure

Với auto-configurations tạo beans phức tạp, một bean factory method có thể ném exception, binding fail hoặc thiếu constructor dependency. `run(...)` vẫn cung cấp assertable context để xem startup failure trong các trường hợp được runner hỗ trợ.

Pattern test:

```java
runner.run(context -> {
    assertThat(context).hasFailed();
    Throwable root = context.getStartupFailure();
    assertThat(root).isNotNull();
});
```

Đây là **snippet**, trong đó `runner` phải được khai báo và cấu hình để cố ý fail. Không chạy nó trên runners của demo mặc định vì các auto-configurations trong ví dụ được thiết kế để khởi tạo thành công.

Nếu dùng `assertThat(context).hasNotFailed()` và một condition sai, lỗi test sẽ định vị ngay startup failure thay vì cho một `NoSuchBeanDefinitionException` lan ra từ `context.getBean(...)`.

## 21. Vì sao WebApplicationContextRunner không tự xác nhận MVC routing?

`WebApplicationContextRunner` có mock ServletContext, nhưng trong demo ta **chỉ import hai auto-configurations của lab**, không dựng đầy đủ:

- `DispatcherServlet`.
- `WebMvcAutoConfiguration`.
- MVC `HandlerMapping` và `HandlerAdapter`.
- `MockMvc` wiring cho một controller route.

Vì vậy test `servletInterceptorSetsResponseHeader` **gọi trực tiếp interceptor method**, không phát một Servlet request qua DispatcherServlet. Để production interceptor hoạt động, cần đăng ký nó trong MVC:

```java
@Configuration(proxyBeanMethods = false)
class AuditMvcRegistration implements WebMvcConfigurer {

    private final ServletAuditInterceptor audit;

    AuditMvcRegistration(ServletAuditInterceptor audit) {
        this.audit = audit;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(audit);
    }
}
```

Đây là **snippet mở rộng** cần imports `Configuration`, `WebMvcConfigurer` và `InterceptorRegistry`; không thuộc project chính. Trong production starter cần đưa config registration này đúng Servlet conditional branch, không dựa vào một bean tồn tại là MVC tự đăng ký. Viết `@WebMvcTest` với controller và `MockMvc` hoặc `@SpringBootTest` cho integration routing.

### Không nhầm test bean với test security filter chain

Một `HandlerInterceptor` không phải thay thế cho Spring Security `SecurityFilterChain`. Nếu đặt auth logic trong interceptor, cần kiểm tra nó được áp dụng đúng paths và thứ tự filter/handler; security authentication/authorization nên dùng infrastructure đúng cho nó. Các tests trong bài chỉ thêm một header demo, không mang mục tiêu bảo mật.

## 22. Vì sao ReactiveWebApplicationContextRunner không tự xác nhận WebFlux pipeline?

Reactive runner tạo một reactive context, nhưng không tự thiết lập đầy đủ HTTP routing, codecs, handler strategies và Netty server. `ReactiveAuditFilter` được tạo đúng type do condition, còn test `reactiveWebFilterSetsResponseHeader` gọi method với `MockServerWebExchange`.

Một full WebFlux request thường đi qua:

```text
HTTP request
  -> HttpHandler / WebHttpHandlerBuilder
  -> WebFilter chain
  -> DispatcherHandler / RouterFunction
  -> HandlerAdapter / message codecs
  -> HTTP response
```

Test runner trong bài dừng ở **bean construction + direct filter behavior**, không đến tầng network. Nếu cần verify WebFilter order và rule với actual route:

- Dùng `@WebFluxTest` + `WebTestClient` cho slice có router/controller phù hợp.
- Hoặc `@SpringBootTest(webEnvironment = RANDOM_PORT)` với HTTP client khi phải test real server.
- Import cấu hình chính xác để chain có filter muốn test; không chỉ tạo WebFilter bean rồi giả sử test đã gửi request.
- Với reactive behavior phức tạp, dùng `StepVerifier` thay vì `block()` trong production.

## 23. Cả MVC và WebFlux trên classpath: một bài test cần có

Lab cố ý thêm cả hai starters. Tình huống này giúp tách hai sự thật:

1. **Classpath presence**: Spring MVC và WebFlux APIs đều tồn tại trong JVM.
2. **Context type**: runner là Servlet hoặc Reactive theo constructor được dùng.

`@ConditionalOnClass(WebFilter.class)` có thể match cả trong Servlet runner vì WebFilter nằm trên classpath, nhưng `@ConditionalOnWebApplication(REACTIVE)` không match. Tương tự, Servlet branch không match trong Reactive runner. Hai conditions kết hợp tạo ra bean đúng **cho mỗi môi trường**, thay vì bị kích hoạt chéo.

Nếu bạn chỉ test bằng `new ApplicationContextRunner()`, cả hai web conditions false và cả hai beans biến mất. Điều này không đủ để kết luận auto-config hoạt động ở một MVC/WebFlux application.

### Cách nhận diện sai runner

- Test cho WebFlux nhưng dùng `WebApplicationContextRunner`: reactive bean không xuất hiện vì type không match.
- Test cho MVC nhưng dùng `ReactiveWebApplicationContextRunner`: Servlet bean không xuất hiện.
- Dùng `ApplicationContextRunner` rồi thêm `spring.main.web-application-type=servlet`: nếu context factory vẫn không-web, điều kiện có thể vẫn không match.
- Cả hai deps có mặt trong full `@SpringBootTest` nhưng tưởng Spring tự tạo reactive app: mặc định MVC có ưu tiên.
- Chỉ chạy Servlet tests và quên reactive branch: starter có thể sai ở một web stack nhưng CI vẫn xanh.

## 24. So sánh runner với các slice test phổ biến

| Công cụ | Độ rộng | Dùng khi |
| --- | --- | --- |
| `ApplicationContextRunner` | Non-web context nhỏ | Test auto-config không phụ thuộc web type |
| `WebApplicationContextRunner` | Servlet web context nhỏ | Test MVC/Servlet conditional beans |
| `ReactiveWebApplicationContextRunner` | Reactive web context nhỏ | Test WebFlux conditional beans |
| `@WebMvcTest` | MVC stack/controller slice | Routing, binding, controller/filter behavior |
| `@WebFluxTest` | WebFlux controller/handler slice | Reactive routing và serialization |
| `@RestClientTest` | Outbound HTTP client slice | RestClient/RestTemplate và mock HTTP responses |
| `@SpringBootTest` | Boot application context | Full wiring/integration, nhiều components |
| Real HTTP server test | Socket/network boundary | TLS/proxy/network/timeouts |

**Không có runner nào thay thế tất cả các test khác.** Mỗi phương án trả lời một câu hỏi: điều kiện bean, MVC route, reactive endpoint, outbound client hay integration toàn ứng dụng.

### Khi nào chỉ cần ApplicationContextRunner?

Một auto-config không quan tâm web type, ví dụ cung cấp `Clock`, cache codec hay serializer nếu dependency có mặt, có thể test bằng `ApplicationContextRunner`. Đừng mở Servlet/Reactive context nếu không có requirement liên quan web — nó làm mục tiêu test mơ hồ và có thể đưa thêm scopes/beans ngoài dự kiến.

## 25. @ConfigurationProperties trong web auto-configuration

Ví dụ dùng `Environment.getProperty` vì chỉ có hai settings `enabled` và `label`. Với settings phức tạp (URI, Duration, nested lists), dùng typed `@ConfigurationProperties` và enable đúng bean:

```java
@ConfigurationProperties(prefix = "lab.audit")
public record AuditProperties(
        boolean enabled,
        String label
) {
}
```

Snippet record này **không thay thế trực tiếp** hai auto-configurations hiện tại nếu không thêm binding/register và default policy. Một cấu hình dùng record có thể khai báo:

```java
@EnableConfigurationProperties(AuditProperties.class)
```

trên auto-config class cần type đó; dùng `withPropertyValues("lab.audit.label=...")` trong runner để kiểm tra binding. Nếu cần Bean Validation với `@Validated` và Jakarta constraints, add validation starter và test both valid/invalid property cases.

**Không quên default và null handling** khi chuyển từ `Environment.getProperty("...", default)` sang Java record: record chỉ có constructor values, nếu không cấu hình field `label` có thể null. Một test auto-config default phải bảo vệ logic fallback được triển khai thật chứ không suy từ code cũ.

## 26. Classpath simulation: khi nào kiểm tra thêm?

Một thư viện có optional Servlet/WebFlux integrations cần hai ma trận:

| Input | Kỳ vọng |
| --- | --- |
| MVC API + Servlet context | Servlet bean có thể được tạo |
| WebFlux API + Reactive context | Reactive bean có thể được tạo |
| MVC API present + Reactive context | Servlet bean phải vắng |
| WebFlux API present + Servlet context | Reactive bean phải vắng |
| Không có MVC classes | Servlet auto-config backing off, không linkage error |
| Không có WebFlux classes | Reactive auto-config backing off, không linkage error |
| Feature disabled | Không tạo bean dù type/classpath match |
| User-provided bean | Không tạo duplicate default |

Lab kiểm tra năm nhóm đầu tiên về **context type, flag, override**, nhưng **không có runnable classpath-hidden tests** trong 13 methods. Để thực sự bảo vệ optional dependencies khi publish starter, thêm một set tests dùng `FilteredClassLoader` trên isolated config, và một consumer build chỉ có một starter. Không ép chúng vào một test mà classloader filtering có thể vô tình làm return type của chính test class không resolve.

### Tại sao không chỉ assert hasSingleBean với tất cả starters trên classpath?

Nếu một auto-config quên `@ConditionalOnClass` nhưng test runtime luôn có library optional, test không phát hiện lỗi thiếu-dependency ở consumer. Mô phỏng classpath thiếu library là test riêng có giá trị đặc biệt với starter vendors.

## 27. Không kiểm thử bằng shared mutable state

Các fields `servletRunner`, `reactiveRunner` và `plainRunner` là **immutable-style runner recipes**. Mỗi `withPropertyValues(...)`, `withUserConfiguration(...)`, `withBean(...)` trả một recipe biến thể; `run` tạo và đóng context riêng.

Không:

- Reuse một `ApplicationContext` sống suốt cả test suite rồi thêm/xóa bean definitions giữa methods.
- Dựa vào thứ tự JUnit để test B hưởng properties từ test A.
- Dùng static mutable registry để ghi nhận số beans từ các contexts khác nhau mà không reset.
- Tự gọi `System.setProperty("lab.audit.enabled", "false")` trong test rồi quên restore; điều này rò global state sang tests khác.
- Giữ context/bean sau callback và gọi method khi bean đã đóng.
- Dùng `@DirtiesContext` để giải quyết một lỗi test runner vốn tự tạo context mới.

Nếu test phải đặt system properties hoặc custom classloader, nên dùng các hooks của runner và giữ scope ngắn trong từng callback để không làm ô nhiễm JVM.

## 28. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Servlet bean không xuất hiện trong plain runner | Plain context không phải Servlet web | Dùng WebApplicationContextRunner |
| Reactive bean không xuất hiện trong servlet runner | `Type.REACTIVE` không match | Dùng ReactiveWebApplicationContextRunner |
| Cả hai beans cùng xuất hiện trong servlet context | Thiếu/sai `@ConditionalOnWebApplication` | Thêm type-specific guards |
| Bean vẫn có khi enabled=false | `@ConditionalOnProperty` sai prefix/name/havingValue | Assert exact property key |
| Không có bean khi flag vắng mặt | `matchIfMissing=false` hoặc policy khác | Xác định default cần thiết |
| User bean tồn tại nhưng starter vẫn tạo default | Thiếu/sai `@ConditionalOnMissingBean` hoặc ordering | Test withUserConfiguration/withBean |
| Bean bị skip vì có unrelated WebFilter | Condition dùng `WebFilter` quá rộng | Dùng feature-specific type/marker |
| `NoClassDefFoundError` khi optional API vắng | @Bean signature bị resolve sớm | Isolate class-level @ConditionalOnClass |
| Error “no ServletContext” | Dùng plain runner hoặc custom context factory sai | Web runner với mock ServletContext |
| Reactive HTTP test không có server | Runner chỉ tạo context nhỏ | WebTestClient/full server integration |
| MVC interceptor bean có nhưng không chạy trong HTTP | Chưa đăng ký addInterceptors | WebMvcConfigurer + MVC integration test |
| Test chỉ assert context.isActive() | Không kiểm tra conditions/default/override | Assert bean presence/absence và behavior |
| Hai starters khiến full app dùng MVC | Boot mặc định ưu tiên MVC | Set correct web type trong full test nếu cần |
| Imported too many auto-configs | Context nặng, side effects ngoài chủ đề | Chỉ import targeted AutoConfigurations.of |
| Classpath test PASS nhưng consumer jar fail | Thiếu actual optional-dependency scenario | Test filtered classloader/consumer fixture |
| Test fail theo thứ tự | Shared static state/system properties | Dùng per-run properties/beans |
| Thấy missing bean nhưng không đọc startup failure | Context đã fail vì dependency | assert hasNotFailed và ConditionEvaluationReport |
| Dùng Spring Boot 4 imports với Boot 3.3 | API/package khác phiên bản | Giữ imports Boot 3.3 đúng |

### Quy trình debug

1. Xác nhận Java 17+, Spring Boot 3.3.5 và starters dependencies.
2. Xác nhận test đang dùng đúng runner type.
3. Xác nhận `AutoConfigurations.of(...)` chứa auto-config class under test.
4. Xác nhận config class có `@ConditionalOnWebApplication(Type.SERVLET/REACTIVE)`.
5. Xác nhận `@ConditionalOnClass` của optional web API.
6. Xác nhận `@ConditionalOnProperty` đúng prefix, name, havingValue và matchIfMissing.
7. Xác nhận user bean được đăng ký **trước** fallback auto-config và missing-bean condition đúng feature type.
8. Kiểm tra `assertThat(context).hasNotFailed()` trước khi dereference beans.
9. Nếu bean vắng, xem ConditionEvaluationReport để phân biệt web/class/property/bean conditions.
10. Kiểm tra bean value/behavior, không chỉ tồn tại.
11. Nếu muốn chứng minh HTTP pipeline, thêm MockMvc/WebTestClient integration test đúng stack.
12. Chạy Gradle tests độc lập và cả suite, xem JUnit HTML/XML report.

## 29. Ma trận test của project

| Method | Runner | Điều xác minh |
| --- | --- | --- |
| `servletRunnerCreatesOnlyServletBean` | Servlet | Chỉ Servlet bean, default label |
| `reactiveRunnerCreatesOnlyReactiveBean` | Reactive | Chỉ Reactive bean, default label |
| `plainRunnerCreatesNeitherWebBean` | Plain | Không web bean |
| `servletFeatureCanBeDisabledByProperty` | Servlet | Flag false tắt servlet |
| `reactiveFeatureCanBeDisabledByProperty` | Reactive | Flag false tắt reactive |
| `servletLabelComesFromEnvironment` | Servlet | Property custom label |
| `reactiveLabelComesFromEnvironment` | Reactive | Property custom label |
| `servletAutoConfigBacksOffForUserConfiguration` | Servlet | withUserConfiguration back-off |
| `reactiveAutoConfigBacksOffForUserBean` | Reactive | withBean back-off |
| `servletInterceptorSetsResponseHeader` | Servlet | Direct interceptor method |
| `reactiveWebFilterSetsResponseHeader` | Reactive | Direct reactive WebFilter method |
| `modifiedRunnerDoesNotMutateBaseRunner` | Servlet | Runner recipe isolation |
| `nonTrueEnabledValueDoesNotMatchCondition` | Reactive | havingValue=true không match unexpected |

**Tổng: 13 phương thức `@Test` từ source**. Đây là ma trận assertions được thiết kế, không phải một report JUnit đã được chạy và quan sát.

### Lệnh chạy

Khi project đã có Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.audit.AuditAutoConfigurationTests'
./gradlew test
./gradlew build
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat build
```

Khi chưa có Wrapper nhưng có Gradle tương thích trên máy:

```bash
gradle test
gradle build
```

Test reports được sinh sau khi chạy:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**Chưa thực thi Gradle trong quá trình biên soạn bài**. Expected behavior từ source là test kiểm chứng các trường hợp trên; chỉ báo cáo PASS sau khi Gradle chạy thành công và JUnit report xác nhận số passed/failed/skipped thực.

## 30. Bài tập thực hành

1. Chạy `AuditAutoConfigurationTests`; quan sát cả Servlet và Reactive runners không cần server TCP.
2. Đổi `Type.REACTIVE` thành `Type.SERVLET` trong Reactive auto-config ở sandbox; test nào phát hiện?
3. Bỏ `@ConditionalOnWebApplication` ở Servlet auto-config, chạy non-web/reactive tests.
4. Đổi `matchIfMissing=true` thành false, xem default tests.
5. Đổi `havingValue="true"` thành false, kiểm tra tests property-disabled.
6. Bỏ `@ConditionalOnMissingBean`, xem custom user bean test thất bại do duplicate type.
7. Chuyển `@ConditionalOnMissingBean` sang supertype `WebFilter.class`, phân tích tại sao dễ vô tình back off bởi filter không liên quan.
8. Thêm một user configuration với `@Bean ServletAuditInterceptor`, xác minh đúng một bean.
9. Thêm một label property ở reactive runner, kiểm tra custom value xuất hiện trên mock response.
10. Thử dùng `ApplicationContextRunner` cho Servlet-only feature; giải thích vì sao guard không match.
11. Dùng `ConditionEvaluationReportLoggingListener` để in điều kiện đã match/mismatch.
12. Thêm một nested config dùng `@ConditionalOnClass` với một optional fake API, test bằng `FilteredClassLoader`.
13. Tạo consumer module chỉ phụ thuộc `spring-boot-starter-web`, xem reactive auto-config có back off và không gây linkage error.
14. Tạo consumer module chỉ có `spring-boot-starter-webflux` và xác minh Servlet auto-config không kích hoạt.
15. Thêm `WebMvcConfigurer` đăng ký interceptor rồi dùng `MockMvc` với một controller thử nghiệm.
16. Tạo một reactive route `RouterFunction` và dùng `WebTestClient` kiểm tra WebFilter được gọi trong pipeline.
17. Thêm `@ConfigurationProperties` typed Duration, dùng `withPropertyValues` cho valid/invalid values.
18. Thử `@ConditionalOnBean` với required collaborator và test khi absent/present.
19. Bổ sung `withParent` để kiểm tra bean search strategy trong parent-child contexts.
20. Chạy toàn suite và kiểm tra condition report/Gradle HTML report trước khi kết luận PASS.

## 31. Checklist QA trước khi merge

- [ ] Đã chọn đúng WebApplicationContextRunner hay ReactiveWebApplicationContextRunner?
- [ ] Test cả plain context để bảo vệ negative web conditions?
- [ ] Target auto-configurations được đưa qua `AutoConfigurations.of(...)`?
- [ ] Các `@ConditionalOnWebApplication` chỉ định đúng SERVLET/REACTIVE?
- [ ] `@ConditionalOnClass` đặt đúng cấp cho optional APIs?
- [ ] `@ConditionalOnProperty` có tests cho default, false, true và unexpected?
- [ ] `@ConditionalOnMissingBean` dùng feature-specific type, không quá rộng?
- [ ] Có test user override bằng withUserConfiguration/withBean?
- [ ] Test beans cụ thể và số lượng, không chỉ application context active?
- [ ] Có test config property thật tác động lên bean?
- [ ] Có test bean method behavior nhưng không suy nó đã chạy qua HTTP pipeline?
- [ ] Có phân biệt direct method call với MockMvc/WebTestClient integration?
- [ ] Nếu cả MVC và WebFlux có mặt, đã kiểm tra context type được chọn?
- [ ] File `AutoConfiguration.imports` chứa đúng fully-qualified config classes?
- [ ] Auto-config package không bị component scan của consumer bắt tình cờ?
- [ ] Production starter có optional deps và classpath tests phù hợp?
- [ ] Không dùng bean overriding để che missing-bean condition?
- [ ] Context được đóng sau `run`, không giữ bean đã destroy?
- [ ] Không dùng static mutable state hay system props rò giữa tests?
- [ ] ConditionEvaluationReport được dùng khi cần giải thích mismatch?
- [ ] Test startup failures không bị che bởi một assertion thiếu bean?
- [ ] Đã đối chiếu imports/APIs với Spring Boot 3.3.5?
- [ ] Không tuyên bố Gradle PASS nếu chưa có execution report?
- [ ] Không để test code gọi endpoint hoặc secrets production?
- [ ] CI có chạy cả Servlet và Reactive scenarios, không chỉ một phía?

## 32. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition annotations, runner tests, `AutoConfigurations.of`, `FilteredClassLoader` và ConditionEvaluationReport.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): test context, MVC/Reactive type detection và các test slices.
- [Spring Boot 3.3 — ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): non-web runner và fluent APIs.
- [Spring Boot 3.3 — WebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html): Servlet context runner và MockServletContext.
- [Spring Boot 3.3 — ReactiveWebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html): reactive context runner.
- [Spring Boot 3.3 — ConditionalOnWebApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html): Type.SERVLET/REACTIVE/ANY.
- [Spring Boot 3.3 — ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): bean back-off.
- [Spring Boot 3.3 — ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): havingValue và matchIfMissing.
- [Spring Framework — HandlerInterceptor](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): MVC interceptor registration.
- [Spring Framework — WebFlux WebFilter](https://docs.spring.io/spring-framework/reference/web/webflux-web-handler-api.html): reactive filter chain/handler infrastructure.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test` và test lifecycle.

## 33. Tổng kết

**`WebApplicationContextRunner`** và **`ReactiveWebApplicationContextRunner`** cho phép thử các Spring Boot auto-configurations phụ thuộc loại web context mà không mở toàn bộ ứng dụng hay HTTP server. Chúng đặc biệt hữu ích khi xây starter cần bật một bean trên Spring MVC nhưng không bật trên WebFlux, hoặc ngược lại.

Một bộ test đáng tin cần kiểm tra **cả ba môi trường Servlet, Reactive, non-web**, property flag, user bean override và bean behavior. Dùng `AutoConfigurations.of(...)` để nạp đúng auto-configurations, `withPropertyValues(...)` để mô phỏng môi trường, `withUserConfiguration(...)`/`withBean(...)` để chứng minh `@ConditionalOnMissingBean` back off, rồi AssertJ để xác nhận số lượng/type/giá trị bean.

Nhớ giới hạn: **bean tồn tại không chứng minh nó đã tham gia MVC/WebFlux HTTP pipeline**; cần MockMvc/WebTestClient hoặc integration test khi muốn chứng minh wiring ở tầng request. Nếu starter có optional dependencies, thêm classpath-absence tests bằng `FilteredClassLoader` và một consumer module thực. Bài mẫu dùng Java 17+, Spring Boot 3.3.5 và 13 test methods như một nền tảng có thể tái hiện, trong khi kết quả PASS thật phải được xác minh qua Gradle/CI report trước khi công bố.
