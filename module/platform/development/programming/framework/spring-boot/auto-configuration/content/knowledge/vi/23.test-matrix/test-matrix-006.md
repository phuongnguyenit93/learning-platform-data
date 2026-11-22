# WebApplicationContextRunner và ReactiveWebApplicationContextRunner

## 1. Vì sao cần runner riêng cho ứng dụng web?

Khi kiểm thử auto-configuration, loại ApplicationContext có thể quyết định condition nào khớp. Ví dụ:

~~~java
@ConditionalOnWebApplication(type = Type.SERVLET)
~~~

chỉ khớp trong servlet web application context. Một test dùng `ApplicationContextRunner` mặc định tạo `AnnotationConfigApplicationContext`, tức context không phải web. Vì vậy condition servlet sẽ không khớp, dù test class có dependency Spring MVC trên classpath.

Spring Boot cung cấp hai runner chuyên biệt:

- **`WebApplicationContextRunner`**: chạy một servlet-based `ConfigurableWebApplicationContext`.
- **`ReactiveWebApplicationContextRunner`**: chạy một `ConfigurableReactiveWebApplicationContext`.

Cả hai kế thừa cơ chế của `AbstractApplicationContextRunner`: cấu hình context, thêm property, đăng ký bean, nạp auto-configuration, thay classloader và chạy callback để assertion. Khác biệt chính là loại web context được tạo.

Bài dùng **Java 17 và Spring Boot 3.3.13** làm baseline minh họa. Nếu dự án chạy release khác, kiểm tra Javadoc của đúng version; API overload mới có thể chỉ xuất hiện ở các release sau.

## 2. Phân biệt ba loại context runner

| Runner | Context nền | Dùng khi |
| --- | --- | --- |
| `ApplicationContextRunner` | `AnnotationConfigApplicationContext` | Cấu hình không phụ thuộc web |
| `WebApplicationContextRunner` | `AnnotationConfigServletWebApplicationContext` với `MockServletContext` | Auto-configuration dành cho Servlet/Spring MVC |
| `ReactiveWebApplicationContextRunner` | `AnnotationConfigReactiveWebApplicationContext` | Auto-configuration dành cho Spring WebFlux |

### 2.1. ApplicationContextRunner

Runner thông thường:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyAutoConfiguration.class));
~~~

Nó phù hợp với properties, service, repository abstraction, bean mặc định và điều kiện không phụ thuộc web.

Nếu class đang kiểm thử có:

~~~java
@ConditionalOnWebApplication
~~~

thì dùng runner thường có thể khiến auto-configuration bị bỏ qua vì context không phải web. Đây không phải lỗi runner; test đang tạo một loại context khác với điều kiện của code.

### 2.2. WebApplicationContextRunner

Constructor mặc định tạo một `AnnotationConfigServletWebApplicationContext` và gắn `MockServletContext`. Điều này giúp condition nhận diện servlet web context mà không phải khởi chạy Tomcat, Jetty hoặc Undertow.

~~~java
private final WebApplicationContextRunner servletRunner =
        new WebApplicationContextRunner();
~~~

Callback nhận `AssertableWebApplicationContext`, cho phép kiểm tra bean và truy cập context servlet.

### 2.3. ReactiveWebApplicationContextRunner

Constructor mặc định tạo `AnnotationConfigReactiveWebApplicationContext`. Context này được nhận diện là reactive web application context, nên phù hợp với `@ConditionalOnWebApplication(type = Type.REACTIVE)`.

~~~java
private final ReactiveWebApplicationContextRunner reactiveRunner =
        new ReactiveWebApplicationContextRunner();
~~~

Callback nhận `AssertableReactiveWebApplicationContext`.

**Cần nhớ:** cả hai runner mô phỏng đúng loại web ApplicationContext để kiểm thử bean/condition. Chúng không khởi chạy một embedded web server thật. Với test HTTP endpoint hoặc lifecycle server, dùng MockMvc, WebTestClient hoặc `@SpringBootTest(webEnvironment = RANDOM_PORT)` phù hợp hơn.

## 3. Khi nào chọn servlet, reactive hoặc non-web?

Lựa chọn runner theo condition mà code cần kiểm thử, không theo tên test hay việc dependency có mặt.

| Điều kiện của auto-configuration | Runner phù hợp |
| --- | --- |
| `@ConditionalOnWebApplication(type = SERVLET)` | `WebApplicationContextRunner` |
| `@ConditionalOnWebApplication(type = REACTIVE)` | `ReactiveWebApplicationContextRunner` |
| `@ConditionalOnWebApplication(type = ANY)` | Một hoặc cả hai web runner, tùy các nhánh cần kiểm tra |
| `@ConditionalOnWebApplication` không chỉ định type | Thường kiểm tra cả servlet và reactive |
| Không có điều kiện web | `ApplicationContextRunner` |
| `@ConditionalOnNotWebApplication` | `ApplicationContextRunner` |

Một auto-configuration có thể kết hợp nhiều condition:

~~~java
@ConditionalOnWebApplication(type = Type.SERVLET)
@ConditionalOnClass(DispatcherServlet.class)
@ConditionalOnProperty(prefix = "acme.web", name = "enabled", havingValue = "true")
~~~

Khi test, cần tạo đúng servlet context, có class cần thiết trên classpath và truyền property bật tính năng. Nếu thiếu một trong các điều kiện, bean sẽ không được đăng ký.

## 4. Các phương thức chung mà hai runner kế thừa

Hai web runner dùng chung phần lớn API của `AbstractApplicationContextRunner`:

| API | Tác dụng |
| --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Nạp auto-configuration cần kiểm thử |
| `withUserConfiguration(...)` | Thêm cấu hình do ứng dụng cung cấp |
| `withBean(...)` | Đăng ký bean test trực tiếp |
| `withPropertyValues(...)` | Thêm property cho lần chạy |
| `withSystemProperties(...)` | Thêm system property |
| `withClassLoader(...)` | Thay classloader, thường dùng để mô phỏng class bị thiếu |
| `withInitializer(...)` | Thêm ApplicationContextInitializer |
| `withParent(...)` | Tạo quan hệ parent context |
| `run(context -> ...)` | Tạo context, chạy assertion rồi đóng context |

Các phương thức cấu hình trả về runner mới theo kiểu fluent API. Có thể định nghĩa runner nền dùng chung rồi tạo biến thể theo từng test:

~~~java
private final WebApplicationContextRunner servletRunner =
        new WebApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        ServletFeatureAutoConfiguration.class));

@Test
void disabledFeatureDoesNotCreateBean() {
    this.servletRunner
            .withPropertyValues("acme.web.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(ServletFeature.class);
            });
}
~~~

Mỗi lần gọi `run`, runner tạo context riêng, thực hiện callback và đóng context sau đó. Không lưu bean instance của một lần chạy để dùng ở lần chạy khác.

## 5. Ví dụ hoàn chỉnh: cùng một thư viện hỗ trợ hai web stack

Ta xây một thư viện nhỏ có thể tạo một bean đánh dấu stack đang hoạt động:

- Trong servlet context, đăng ký `WebStack.Servlet`.
- Trong reactive context, đăng ký `WebStack.Reactive`.
- Nếu context không phải web, không đăng ký bean nào.
- Nếu ứng dụng đã cung cấp `WebStack`, auto-configuration mặc định phải back off.

Ví dụ dùng cả hai starter trong test classpath để hai loại auto-configuration đều có thể được nạp. Hai runner sẽ chọn context riêng, nên có thể kiểm tra từng stack độc lập.

### 5.1. Cấu trúc project

~~~text
web-context-runner-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/webstack/
    │   │   ├── WebStack.java
    │   │   └── autoconfigure/
    │   │       ├── ServletStackAutoConfiguration.java
    │   │       └── ReactiveStackAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/webstack/
            └── WebStackAutoConfigurationTests.java
~~~

### 5.2. pom.xml

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
    <groupId>com.example</groupId>
    <artifactId>web-context-runner-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Hai starter web được đưa vào để test cả hai nhánh classpath. Không có server nào tự khởi chạy khi gọi các context runner.

Nếu một ứng dụng thật có cả Spring MVC và WebFlux trên classpath, Spring Boot khi tự suy luận loại ứng dụng thường ưu tiên MVC. Đây là quy tắc của quá trình tạo context qua `SpringApplication`; trong ví dụ này, runner tạo trực tiếp context servlet hoặc reactive theo lựa chọn của test, không dựa vào suy luận đó.

### 5.3. WebStack.java

**src/main/java/com/example/webstack/WebStack.java**

~~~java
package com.example.webstack;

public interface WebStack {

    String kind();

    record Servlet() implements WebStack {
        @Override
        public String kind() {
            return "servlet";
        }
    }

    record Reactive() implements WebStack {
        @Override
        public String kind() {
            return "reactive";
        }
    }

    record Custom(String kind) implements WebStack {
    }
}
~~~

Dùng record để dữ liệu ví dụ ngắn gọn. Các implementation chỉ đánh dấu stack, không khởi chạy server và không xử lý request.

### 5.4. ServletStackAutoConfiguration.java

**src/main/java/com/example/webstack/autoconfigure/ServletStackAutoConfiguration.java**

~~~java
package com.example.webstack.autoconfigure;

import com.example.webstack.WebStack;
import jakarta.servlet.Servlet;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.servlet.DispatcherServlet;

@AutoConfiguration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnClass({Servlet.class, DispatcherServlet.class})
public class ServletStackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(WebStack.class)
    WebStack.Servlet servletStack() {
        return new WebStack.Servlet();
    }
}
~~~

Có ba lớp quyết định:

1. Context phải là servlet web application.
2. Servlet API và Spring MVC `DispatcherServlet` phải có trên classpath.
3. Chưa có bean `WebStack` do ứng dụng cung cấp.

Điều kiện thứ ba nằm trên bean method, vì vậy class có thể được xử lý nhưng default bean vẫn back off khi người dùng có implementation riêng.

### 5.5. ReactiveStackAutoConfiguration.java

**src/main/java/com/example/webstack/autoconfigure/ReactiveStackAutoConfiguration.java**

~~~java
package com.example.webstack.autoconfigure;

import com.example.webstack.WebStack;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.DispatcherHandler;
import reactor.core.publisher.Mono;

@AutoConfiguration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@ConditionalOnClass({DispatcherHandler.class, Mono.class})
public class ReactiveStackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(WebStack.class)
    WebStack.Reactive reactiveStack() {
        return new WebStack.Reactive();
    }
}
~~~

Ở đây classpath gate kiểm tra thành phần Spring WebFlux và Reactor. Context gate vẫn cần khớp; chỉ có `DispatcherHandler` trong classpath không biến một servlet context thành reactive context.

### 5.6. Đăng ký auto-configuration

Tạo file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.webstack.autoconfigure.ServletStackAutoConfiguration
com.example.webstack.autoconfigure.ReactiveStackAutoConfiguration
~~~

Đây là discovery resource của Spring Boot 3.x. Trong các test bên dưới, `AutoConfigurations.of(...)` nạp class trực tiếp để kiểm thử logic condition. Việc test nạp class trực tiếp **không tự xác minh resource imports đã được đóng gói đúng**; kiểm tra artifact đã build/publish cần một consumer smoke test riêng.

## 6. Thiết lập hai runner và kiểm thử nhánh đúng

### 6.1. Khai báo runner dùng chung

Trong test:

~~~java
private final AutoConfigurations configurations =
        AutoConfigurations.of(
                ServletStackAutoConfiguration.class,
                ReactiveStackAutoConfiguration.class);

private final WebApplicationContextRunner servletRunner =
        new WebApplicationContextRunner()
                .withConfiguration(configurations);

private final ReactiveWebApplicationContextRunner reactiveRunner =
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(configurations);
~~~

Mỗi runner có context factory khác nhau. Không thay servlet runner bằng reactive runner chỉ để test chạy được; làm vậy sẽ thay đổi điều kiện đang được kiểm tra.

### 6.2. Servlet runner chỉ đăng ký bean servlet

~~~java
@Test
void servletContextAppliesOnlyServletConfiguration() {
    this.servletRunner.run(context -> {
        assertThat(context).hasSingleBean(WebStack.class);
        assertThat(context).hasSingleBean(WebStack.Servlet.class);
        assertThat(context).doesNotHaveBean(WebStack.Reactive.class);

        assertThat(context.getBean(WebStack.class).kind())
                .isEqualTo("servlet");
    });
}
~~~

Kết quả mong đợi: `WebStack.Servlet` tồn tại và `WebStack.Reactive` không tồn tại. Dù cả hai loại class đều có trong dependency graph, condition web application type loại nhánh reactive.

### 6.3. Reactive runner chỉ đăng ký bean reactive

~~~java
@Test
void reactiveContextAppliesOnlyReactiveConfiguration() {
    this.reactiveRunner.run(context -> {
        assertThat(context).hasSingleBean(WebStack.class);
        assertThat(context).hasSingleBean(WebStack.Reactive.class);
        assertThat(context).doesNotHaveBean(WebStack.Servlet.class);

        assertThat(context.getBean(WebStack.class).kind())
                .isEqualTo("reactive");
    });
}
~~~

Kết quả mong đợi là `reactive`. Test này chứng minh context reactive không bị nhầm với servlet chỉ vì test runtime có cả hai starter.

### 6.4. ApplicationContextRunner không khớp hai nhánh web

Dùng runner thường làm control test:

~~~java
@Test
void nonWebContextDoesNotApplyEitherWebConfiguration() {
    new ApplicationContextRunner()
            .withConfiguration(this.configurations)
            .run(context -> {
                assertThat(context).doesNotHaveBean(WebStack.class);
            });
}
~~~

Đây là minh họa rõ nhất vì sao test condition web cần runner chuyên biệt. Classpath có đủ servlet và reactive API nhưng context không phải web, nên không nhánh nào đăng ký bean.

## 7. Kiểm thử classpath condition bằng FilteredClassLoader

Web runner giúp tạo đúng loại context. Nó không tự bảo đảm mọi dependency có mặt. Nếu muốn kiểm tra `@ConditionalOnClass`, có thể loại một class khỏi classloader trong một lần chạy.

### 7.1. Thiếu Spring MVC DispatcherServlet

~~~java
@Test
void servletConfigurationBacksOffWhenMvcClassIsMissing() {
    this.servletRunner
            .withClassLoader(new FilteredClassLoader(DispatcherServlet.class))
            .run(context -> {
                assertThat(context).doesNotHaveBean(WebStack.Servlet.class);
                assertThat(context).doesNotHaveBean(WebStack.class);
            });
}
~~~

Context vẫn là servlet web context, nhưng classpath condition không khớp vì thiếu `DispatcherServlet`. Đây là cách tách riêng hai nguyên nhân: web context đúng nhưng dependency cần thiết không có.

### 7.2. Thiếu Reactive DispatcherHandler

~~~java
@Test
void reactiveConfigurationBacksOffWhenWebFluxClassIsMissing() {
    this.reactiveRunner
            .withClassLoader(new FilteredClassLoader(DispatcherHandler.class))
            .run(context -> {
                assertThat(context).doesNotHaveBean(WebStack.Reactive.class);
                assertThat(context).doesNotHaveBean(WebStack.class);
            });
}
~~~

Reactive context vẫn tồn tại, nhưng classpath gate không khớp. Nếu chỉ dùng `ApplicationContextRunner`, test sẽ không chứng minh được nhánh classpath này vì condition web đã không khớp ngay từ đầu.

### 7.3. Phân biệt lỗi context và lỗi classpath

| Test setup | Web condition | Class condition | Kết quả |
| --- | --- | --- | --- |
| Servlet runner, đủ MVC classes | Khớp | Khớp | Bean servlet được tạo |
| Servlet runner, thiếu DispatcherServlet | Khớp | Không khớp | Không có bean servlet |
| Reactive runner, đủ WebFlux classes | Khớp | Khớp | Bean reactive được tạo |
| Reactive runner, thiếu DispatcherHandler | Khớp | Không khớp | Không có bean reactive |
| ApplicationContextRunner, đủ cả hai stacks | Không khớp | Có thể khớp | Không có bean web |

Mỗi test nên thay đổi một yếu tố chính để nguyên nhân của kết quả dễ đọc.

## 8. Kiểm thử user bean khiến auto-configuration back off

Một auto-configuration tốt thường tạo default chỉ khi ứng dụng chưa cung cấp implementation. Hai cấu hình mẫu dùng:

~~~java
@ConditionalOnMissingBean(WebStack.class)
~~~

Có thể xác minh bằng user configuration:

~~~java
@Configuration(proxyBeanMethods = false)
static class CustomWebStackConfiguration {

    @Bean
    WebStack customWebStack() {
        return new WebStack.Custom("custom");
    }
}
~~~

Test trong servlet context:

~~~java
@Test
void servletConfigurationBacksOffForCustomBean() {
    this.servletRunner
            .withUserConfiguration(CustomWebStackConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(WebStack.class);
                assertThat(context).hasBean("customWebStack");
                assertThat(context).doesNotHaveBean(WebStack.Servlet.class);

                assertThat(context.getBean(WebStack.class).kind())
                        .isEqualTo("custom");
            });
}
~~~

Test trong reactive context:

~~~java
@Test
void reactiveConfigurationBacksOffForCustomBean() {
    this.reactiveRunner
            .withUserConfiguration(CustomWebStackConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(WebStack.class);
                assertThat(context).hasBean("customWebStack");
                assertThat(context).doesNotHaveBean(WebStack.Reactive.class);

                assertThat(context.getBean(WebStack.class).kind())
                        .isEqualTo("custom");
            });
}
~~~

Các test này xác nhận auto-configuration nhường chỗ trong cả hai loại context. Nếu muốn kiểm thử riêng thứ tự đăng ký, có thể đọc Condition Evaluation Report; không nên thêm ordering annotation chỉ để làm assertion pass khi chưa hiểu dependency giữa các cấu hình.

## 9. File test hoàn chỉnh

**src/test/java/com/example/webstack/WebStackAutoConfigurationTests.java**

~~~java
package com.example.webstack;

import com.example.webstack.autoconfigure.ReactiveStackAutoConfiguration;
import com.example.webstack.autoconfigure.ServletStackAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.boot.test.util.FilteredClassLoader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.DispatcherHandler;
import org.springframework.web.servlet.DispatcherServlet;

import static org.assertj.core.api.Assertions.assertThat;

class WebStackAutoConfigurationTests {

    private final AutoConfigurations configurations =
            AutoConfigurations.of(
                    ServletStackAutoConfiguration.class,
                    ReactiveStackAutoConfiguration.class);

    private final WebApplicationContextRunner servletRunner =
            new WebApplicationContextRunner()
                    .withConfiguration(configurations);

    private final ReactiveWebApplicationContextRunner reactiveRunner =
            new ReactiveWebApplicationContextRunner()
                    .withConfiguration(configurations);

    @Test
    void servletContextAppliesOnlyServletConfiguration() {
        servletRunner.run(context -> {
            assertThat(context).hasSingleBean(WebStack.class);
            assertThat(context).hasSingleBean(WebStack.Servlet.class);
            assertThat(context).doesNotHaveBean(WebStack.Reactive.class);
            assertThat(context.getBean(WebStack.class).kind())
                    .isEqualTo("servlet");
        });
    }

    @Test
    void reactiveContextAppliesOnlyReactiveConfiguration() {
        reactiveRunner.run(context -> {
            assertThat(context).hasSingleBean(WebStack.class);
            assertThat(context).hasSingleBean(WebStack.Reactive.class);
            assertThat(context).doesNotHaveBean(WebStack.Servlet.class);
            assertThat(context.getBean(WebStack.class).kind())
                    .isEqualTo("reactive");
        });
    }

    @Test
    void nonWebContextAppliesNeitherConfiguration() {
        new ApplicationContextRunner()
                .withConfiguration(configurations)
                .run(context ->
                        assertThat(context).doesNotHaveBean(WebStack.class));
    }

    @Test
    void missingServletClassDisablesServletConfiguration() {
        servletRunner
                .withClassLoader(new FilteredClassLoader(DispatcherServlet.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(WebStack.Servlet.class);
                    assertThat(context).doesNotHaveBean(WebStack.class);
                });
    }

    @Test
    void missingReactiveClassDisablesReactiveConfiguration() {
        reactiveRunner
                .withClassLoader(new FilteredClassLoader(DispatcherHandler.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(WebStack.Reactive.class);
                    assertThat(context).doesNotHaveBean(WebStack.class);
                });
    }

    @Test
    void servletConfigurationBacksOffForCustomBean() {
        servletRunner
                .withUserConfiguration(CustomWebStackConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(WebStack.class);
                    assertThat(context).hasBean("customWebStack");
                    assertThat(context).doesNotHaveBean(WebStack.Servlet.class);
                    assertThat(context.getBean(WebStack.class).kind())
                            .isEqualTo("custom");
                });
    }

    @Test
    void reactiveConfigurationBacksOffForCustomBean() {
        reactiveRunner
                .withUserConfiguration(CustomWebStackConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(WebStack.class);
                    assertThat(context).hasBean("customWebStack");
                    assertThat(context).doesNotHaveBean(WebStack.Reactive.class);
                    assertThat(context.getBean(WebStack.class).kind())
                            .isEqualTo("custom");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomWebStackConfiguration {

        @Bean
        WebStack customWebStack() {
            return new WebStack.Custom("custom");
        }
    }
}
~~~

Chạy toàn bộ test:

~~~bash
mvn clean test
~~~

Kỳ vọng **bảy test pass**. Mỗi runner tạo context riêng rồi đóng context sau callback; test không cần cổng HTTP hoặc embedded server.

## 10. Khi nào runner không đủ?

Hai runner này kiểm thử **điều kiện và bean trong web ApplicationContext**. Chúng không thay thế mọi loại kiểm thử web.

| Mục tiêu | Công cụ phù hợp |
| --- | --- |
| Condition servlet/reactive có khớp không? | WebApplicationContextRunner / ReactiveWebApplicationContextRunner |
| Bean mặc định có được tạo hoặc back off không? | Web runner + Assertable context |
| Thiếu class trên classpath thì auto-config có tắt không? | Web runner + FilteredClassLoader |
| Controller MVC xử lý HTTP request với mock servlet infrastructure | `@WebMvcTest` hoặc `@SpringBootTest` + MockMvc |
| Controller WebFlux xử lý request trong mock environment | `@WebFluxTest` hoặc `@SpringBootTest` + WebTestClient |
| Kiểm thử server thật, port, connector và network | `@SpringBootTest(webEnvironment = RANDOM_PORT)` |
| Xác minh starter JAR có discovery metadata đúng | Consumer smoke test với artifact đã đóng gói |

### 10.1. Không nhầm WebApplicationContextRunner với MockMvc

`WebApplicationContextRunner` cung cấp servlet context với `MockServletContext`; bản thân runner không cung cấp đầy đủ workflow gửi request như MockMvc. Nếu cần kiểm thử routing, controller advice, filter chain hoặc response body, hãy dùng công cụ MVC test phù hợp.

### 10.2. Không nhầm ReactiveWebApplicationContextRunner với WebTestClient

`ReactiveWebApplicationContextRunner` tạo reactive ApplicationContext; nó không tự gửi HTTP request. Để kiểm tra endpoint WebFlux, dùng WebTestClient trong mock web test hoặc kết nối đến server thật trong integration test.

### 10.3. Kiểm tra discovery metadata riêng

Trong test mẫu, `AutoConfigurations.of(...)` nạp trực tiếp class được chỉ định. Cách này tập trung vào condition và bean behavior, nhưng không xác minh Spring Boot tìm thấy class qua:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Để kiểm tra phân phối, build JAR, tạo một ứng dụng consumer độc lập chỉ thêm starter, rồi khởi động context và xác nhận bean xuất hiện. Đây là smoke test cho metadata và dependency POM, khác với unit test condition.

## 11. Khi cả Spring MVC và WebFlux cùng có trên classpath

Một dự án có thể dùng MVC cho server và WebFlux `WebClient` cho outbound HTTP. Khi cả Spring MVC và WebFlux có mặt, `SpringApplication` thường chọn MVC làm web application type mặc định.

Điều này không có nghĩa không thể kiểm thử reactive auto-configuration. `ReactiveWebApplicationContextRunner` tạo reactive context trực tiếp, nên có thể kiểm tra nhánh reactive dù test classpath có cả hai starter.

Nếu cần kiểm thử **ứng dụng Spring Boot thật** chạy WebFlux trong khi cả hai stacks cùng có mặt, hãy chỉ định rõ:

~~~properties
spring.main.web-application-type=reactive
~~~

Hoặc trong test:

~~~java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
class ReactiveApplicationTests {
}
~~~

Đừng nhầm việc runner chọn context cho test cô lập với việc SpringApplication tự phát hiện web application type khi khởi chạy ứng dụng.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Servlet condition không khớp dù có starter-web | Dùng ApplicationContextRunner non-web | Dùng WebApplicationContextRunner |
| Reactive condition không khớp dù có spring-webflux | Context vẫn là non-web hoặc servlet | Dùng ReactiveWebApplicationContextRunner |
| Nghĩ runner sẽ mở cổng HTTP | Nhầm context runner với server integration test | Dùng RANDOM_PORT khi cần server thật |
| Test servlet và reactive cho cùng một bean | Hai auto-configuration không phân biệt web type hoặc cùng điều kiện | Đặt type rõ ràng trong @ConditionalOnWebApplication |
| Test thiếu class nhưng condition vẫn match | FilteredClassLoader lọc nhầm class hoặc class khác vẫn thỏa điều kiện | Filter đúng class được annotation yêu cầu |
| Test không chứng minh imports resource | Dùng AutoConfigurations.of để nạp class trực tiếp | Thêm consumer smoke test với JAR đã đóng gói |
| Có cả MVC và WebFlux nhưng ứng dụng chạy MVC | SpringApplication ưu tiên MVC khi tự dò | Đặt web-application-type=reactive nếu ứng dụng cần WebFlux |
| Test runner dùng chung mutable state | Giữ instance/configuration có state ngoài context | Tạo fixture immutable và mỗi lần run một context mới |
| Bean custom không làm default back off | Custom bean không cùng type hoặc được cấu hình sai | Kiểm tra return type và @ConditionalOnMissingBean |
| Dùng runner để test controller response | Runner chỉ xác nhận context/bean | Dùng MockMvc hoặc WebTestClient |

## 13. Checklist chọn và viết test

Trước khi viết test auto-configuration:

1. Đọc condition trên class và bean method.
2. Xác định context cần là non-web, servlet hay reactive.
3. Chọn đúng runner.
4. Bảo đảm dependency classpath cần thiết có mặt.
5. Dùng `withConfiguration(AutoConfigurations.of(...))` để nạp class cần test.
6. Dùng `withPropertyValues` cho từng nhánh property.
7. Dùng `withClassLoader(FilteredClassLoader(...))` cho nhánh thiếu dependency.
8. Dùng `withUserConfiguration` để xác nhận bean tùy chỉnh khiến auto-configuration back off.
9. Assertion theo type và name, không chỉ kiểm tra context khởi động.
10. Dùng MockMvc/WebTestClient hoặc server test nếu cần kiểm tra HTTP.
11. Test consumer độc lập nếu cần xác minh imports resource và POM đã publish.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `ApplicationContextRunner` không phù hợp để kiểm thử `@ConditionalOnWebApplication(type = SERVLET)`?  
**Đáp án:** Constructor mặc định tạo non-web `AnnotationConfigApplicationContext`, nên condition servlet không khớp.

**Câu 2.** `WebApplicationContextRunner` mặc định tạo context nào?  
**Đáp án:** `AnnotationConfigServletWebApplicationContext` với `MockServletContext`.

**Câu 3.** `ReactiveWebApplicationContextRunner` mặc định tạo context nào?  
**Đáp án:** `AnnotationConfigReactiveWebApplicationContext`.

**Câu 4.** Hai runner có tự khởi động embedded server không?  
**Đáp án:** Không. Chúng tạo web ApplicationContext để kiểm tra condition và bean; dùng RANDOM_PORT hoặc test client khi cần HTTP/server.

**Câu 5.** Làm sao chứng minh bean servlet không xuất hiện vì thiếu DispatcherServlet, thay vì vì context không phải servlet?  
**Đáp án:** Dùng WebApplicationContextRunner để condition servlet khớp, sau đó dùng FilteredClassLoader loại DispatcherServlet để chỉ làm classpath condition thất bại.

**Câu 6.** `AutoConfigurations.of(...)` có xác minh file AutoConfiguration.imports không?  
**Đáp án:** Không. Nó đăng ký class trực tiếp cho test. Cần consumer smoke test với JAR đã đóng gói để xác minh discovery metadata.

**Câu 7.** Khi ứng dụng có cả MVC và WebFlux, tại sao reactive runner vẫn có thể test reactive auto-configuration?  
**Đáp án:** Runner tạo trực tiếp reactive ApplicationContext; nó không phụ thuộc việc SpringApplication tự suy luận loại context từ classpath.

**Câu 8.** Muốn kiểm tra controller trả HTTP response đúng, dùng runner nào?  
**Đáp án:** Dùng MockMvc cho MVC hoặc WebTestClient cho WebFlux; runner chuyên biệt tập trung vào context/condition/bean.

## 15. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, phần Testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [WebApplicationContextRunner — Spring Boot API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html)
- [ReactiveWebApplicationContextRunner — Spring Boot API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html)
- [ApplicationContextRunner — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)

**Ghi nhớ:** Chọn runner theo **loại ApplicationContext mà condition yêu cầu**. `WebApplicationContextRunner` kiểm thử servlet stack; `ReactiveWebApplicationContextRunner` kiểm thử reactive stack; `ApplicationContextRunner` kiểm thử non-web. Dùng chúng để xác minh condition, bean và back-off trong context cô lập; dùng MockMvc, WebTestClient hoặc server integration test cho HTTP behavior.
