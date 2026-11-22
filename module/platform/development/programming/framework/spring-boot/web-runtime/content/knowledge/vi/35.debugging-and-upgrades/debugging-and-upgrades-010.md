# Đối chiếu điều kiện tự cấu hình khi thêm bean hoặc @EnableWebMvc/@EnableWebFlux

**Một thay đổi nhỏ như thêm @Bean, @EnableWebMvc hoặc @EnableWebFlux có thể làm ứng dụng Spring Boot đổi hành vi dù không sửa một controller nào.** Ví dụ: static resources trả 404, Jackson/codec thay đổi, CORS biến mất, default service bean không còn được tạo, hoặc một framework component bị thay bằng bean của ứng dụng. Khi gỡ lỗi, cần xác định **điều kiện auto-configuration nào đã match hoặc không match, bean nào tạo ra khác biệt và HTTP behavior nào thực sự thay đổi**. Không nên kết luận chung chung rằng “Spring Boot bị tắt”.

Bài thuộc **Spring Boot - web-runtime → Gỡ lỗi và nâng cấp**, với đề bài **Đối chiếu điều kiện tự cấu hình khi thêm bean hoặc @EnableWebMvc/@EnableWebFlux**. Nội dung và ví dụ neo vào **Spring Boot 3.3.13, Java 17, Maven**, dùng hai dự án **MVC/Servlet** và **WebFlux/reactive** độc lập, conditional user bean, condition report, static resource, CORS và HTTP integration tests. Các thuộc tính và tình huống được chỉ rõ theo phiên bản; trước khi áp dụng cho bản Boot khác phải xác minh source/Javadoc và report thực tế.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích **@SpringBootApplication, @EnableAutoConfiguration, @ComponentScan** và lúc Spring Boot đăng ký default beans.
2. Đọc ý nghĩa **@ConditionalOnClass, @ConditionalOnWebApplication, @ConditionalOnBean, @ConditionalOnMissingBean, @ConditionalOnProperty, @ConditionalOnSingleCandidate**.
3. Phân biệt auto-configuration **class-level backoff**, **method-level backoff** và **bean override/name conflict**.
4. Biết vì sao một @Bean trả đúng type có thể thay default bean bằng cơ chế MissingBean chứ không cần trùng bean name.
5. Xác định Boot đang chọn **SERVLET/MVC** hay **REACTIVE/WebFlux**, đặc biệt khi hai starters cùng tồn tại.
6. Giải thích **WebMvcAutoConfiguration** phụ thuộc không có **WebMvcConfigurationSupport**, và tác động của **@EnableWebMvc**.
7. Giải thích **WebFluxAutoConfiguration** phụ thuộc không có **WebFluxConfigurationSupport**, và tác động của **@EnableWebFlux**.
8. Mở rộng Boot bằng **WebMvcConfigurer/WebFluxConfigurer** không gắn @Enable để giữ Boot defaults khi có thể.
9. Biết mục đích của **WebMvcRegistrations** và **WebHttpHandlerBuilderCustomizer**.
10. Sử dụng **--debug**, **ConditionEvaluationReport**, **/actuator/conditions**, **/actuator/beans**, **/actuator/mappings**.
11. Viết test HTTP thực kiểm chứng **default bean/custom bean**, **static file**, **CORS** và **condition outcomes**.
12. Lập quy trình nâng cấp/hồi quy có thể giải thích từ **condition → bean/mapping → runtime behavior**.

## 2. Auto-configuration là cấu hình *có điều kiện*

### 2.1. Vòng xử lý ở mức khái niệm

@**SpringBootApplication** có @SpringBootConfiguration, @EnableAutoConfiguration và @ComponentScan. Spring Boot thu thập các auto-configurations theo classpath, environment và các bean definitions đã được đăng ký, rồi chỉ kích hoạt phần thỏa điều kiện.

~~~text
Dependencies + spring.* properties + active profiles
                        |
                        v
          ApplicationContext + user configs
                        |
                        v
             Auto-configuration candidates
                |       |        |
                v       v        v
           OnClass   OnBean   OnWebApplication
                |       |        |
                +-------+--------+
                        |
               match hoặc not match
                        |
               tạo/bỏ qua bean defaults
                        |
                        v
     DispatcherServlet / DispatcherHandler / HTTP routes
~~~

Vì nhiều auto-configurations dùng **@ConditionalOnMissingBean**, user-defined bean sẽ có cơ hội **thay phần mặc định**. Nhưng chỉ có **những conditions liên quan** thay đổi; không có lý do mặc định để mọi auto-configuration khác biến mất.

### 2.2. “Back off” là gì?

Ví dụ giả định:

~~~java
@AutoConfiguration
class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return name -> "default:" + name;
    }
}
~~~

Khi app chưa có GreetingService, Boot tạo defaultGreetingService. Khi một user configuration cung cấp:

~~~java
@Bean
GreetingService greetingService() {
    return name -> "custom:" + name;
}
~~~

thì điều kiện **@ConditionalOnMissingBean(GreetingService.class)** không match và defaultGreetingService không được tạo. Đây là **method-level bean backoff**; những bean của Tomcat, Jackson, Actuator hoặc MVC vẫn có thể được Boot tạo bình thường. Hai snippets được triển khai thành project runnable ở mục 8.

### 2.3. Các condition phổ biến

| Condition | Điều được kiểm tra | Ví dụ |
| --- | --- | --- |
| @ConditionalOnClass | Class có trong classpath? | Servlet/DispatcherServlet có mặt để xét MVC. |
| @ConditionalOnMissingClass | Class không có mặt? | Không tạo integration khi thiếu dependency. |
| @ConditionalOnWebApplication | Context type là SERVLET/REACTIVE? | MVC và WebFlux không cùng auto-config trong default app. |
| @ConditionalOnBean | Bean cùng type/name/annotation có tồn tại? | Chỉ tạo adapter khi dependency bean được cấu hình. |
| @ConditionalOnMissingBean | Không có bean match? | User bean làm default không được tạo. |
| @ConditionalOnSingleCandidate | Có một bean/candidate thích hợp? | Default integration với một DataSource. |
| @ConditionalOnProperty | Property match giá trị? | Tùy chọn tính năng theo configuration. |
| @ConditionalOnResource | Resource có tồn tại? | Bật một phần cấu hình nếu có file/classpath resource. |
| @ConditionalOnExpression | SpEL expression đúng? | Điều kiện động phức tạp; tránh nếu không cần. |

Đừng suy luận tất cả điều kiện đều so **bean name**. Rất nhiều điều kiện được khai báo bằng **type**, đôi khi còn xét search strategy qua parent contexts hoặc bean annotation. Muốn biết chính xác thì đọc condition annotation tại Boot version và message thực tế.

### 2.4. Bean registration order và metadata

@ConditionalOnMissingBean đánh giá dựa vào các bean definitions **đã được xử lý đến thời điểm condition chạy**, không phải tự instantiate mọi runtime object để tìm type thực tế. Boot thiết kế auto-configuration sau user configuration để user beans có thể thay default. Dùng MissingBean tùy tiện trong một @Configuration thông thường có thứ tự không rõ có thể dẫn tới kết quả bất ngờ.

Với custom starter, dùng **@AutoConfiguration**, đăng ký trong **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**, đặt điều kiện phù hợp và dùng AutoConfigureBefore/After khi thứ tự auto-config có phụ thuộc thật. **@DependsOn** chỉ điều chỉnh initialization dependency; nó không thay thế việc tính toán auto-configuration conditions.

### 2.5. Ba lỗi không giống nhau

~~~text
@ConditionalOnMissingBean thấy user bean
    -> default bean được bỏ qua có chủ đích

Hai bean definitions cùng tên
    -> có thể BeanDefinitionOverrideException

Hai beans cùng interface, injection không có qualifier/primary
    -> có thể NoUniqueBeanDefinitionException
~~~

**@Primary** giúp chọn candidate trong injection; không làm những bean khác biến mất. **@Qualifier** chỉ định dependency cụ thể; không đồng nghĩa vô hiệu hóa auto-configuration. Đừng bật **spring.main.allow-bean-definition-overriding=true** để che nguyên nhân chưa phân tích.

## 3. MVC và WebFlux được chọn theo web application type

### 3.1. Spring MVC/Servlet

**spring-boot-starter-web** thông thường cung cấp Spring MVC, Jakarta Servlet và embedded Tomcat. Boot chọn **ServletWebServerApplicationContext** và auto-configure DispatcherServlet/WebMvc khi conditions phù hợp.

### 3.2. Spring WebFlux/reactive

**spring-boot-starter-webflux** thông thường có Spring WebFlux và Reactor Netty, dẫn đến **ReactiveWebServerApplicationContext** và DispatcherHandler khi app được chọn loại REACTIVE.

### 3.3. Nếu có cả hai starters?

Trong **Spring Boot 3.3**, khi có cả MVC và WebFlux trên classpath, **MVC có precedence mặc định**. Nhiều dự án MVC dùng starter-webflux chỉ để gọi outbound HTTP bằng WebClient:

~~~text
starter-web                     -> thường SERVLET/MVC
starter-webflux                 -> thường REACTIVE/WebFlux
starter-web + starter-webflux   -> mặc định SERVLET/MVC
~~~

Đừng kết luận một app đang chạy WebFlux server chỉ vì trong POM có WebClient, Mono hoặc spring-webflux.

### 3.4. Ép web application type

Có thể chủ động khai báo:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

hoặc Java:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
~~~

Đây là snippet cần MyApplication/imports. Ép REACTIVE khi classpath có cả hai starters là lựa chọn phải **test lại mappings, web server, security, HTTP codecs và blocking dependencies**. Không dùng nó để chữa bừa lỗi @EnableWebFlux.

### 3.5. Ba thứ hoàn toàn khác nhau

- Có **dependency WebFlux**: classes và APIs có trên classpath.
- Chọn **WebApplicationType.REACTIVE**: Boot tạo reactive web context.
- Gắn **@EnableWebFlux**: đưa Spring Framework WebFlux configuration vào context, khiến Boot WebFlux auto-configuration tương ứng có thể back off.

**@EnableWebMvc không phải nút bật MVC server trong Spring Boot**; **@EnableWebFlux không phải nút chuyển Tomcat MVC thành Netty WebFlux**.

## 4. WebMvcAutoConfiguration: điều kiện bị ảnh hưởng bởi @EnableWebMvc

### 4.1. Javadoc của Boot 3.3

WebMvcAutoConfiguration có các điều kiện class-level quan trọng:

~~~java
@ConditionalOnWebApplication(type = SERVLET)
@ConditionalOnClass({
    jakarta.servlet.Servlet.class,
    org.springframework.web.servlet.DispatcherServlet.class,
    org.springframework.web.servlet.config.annotation.WebMvcConfigurer.class
})
@ConditionalOnMissingBean(
    org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport.class
)
~~~

Đây là **trích lược annotations**, không phải class Java độc lập. Những nested configurations và @Bean methods còn có điều kiện riêng.

**@EnableWebMvc** import **DelegatingWebMvcConfiguration** (là subtype của WebMvcConfigurationSupport), nên trong Servlet context điều kiện **@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)** trên WebMvcAutoConfiguration không match. Một @Configuration **extends WebMvcConfigurationSupport** cũng có thể gây backoff như vậy.

**Chỉ implements WebMvcConfigurer** không đăng ký replacement bean kiểu WebMvcConfigurationSupport, nên **thường vẫn giữ WebMvcAutoConfiguration**.

### 4.2. Điều gì có thể mất khi dùng @EnableWebMvc?

Theo tài liệu Boot 3.3, WebMvcAutoConfiguration đóng góp thêm:
- static resource handlers (static files, WebJars);
- static index.html welcome page;
- **ContentNegotiatingViewResolver**, **BeanNameViewResolver**;
- đăng ký Converter/GenericConverter/Formatter beans;
- HttpMessageConverters integration;
- MessageCodesResolver, ConfigurableWebBindingInitializer;
- customizations và resource/formatting properties Boot khác tùy version.

Sau khi thêm @EnableWebMvc, **framework MVC infrastructure vẫn được tạo**, nên một @RestController có thể còn trả JSON 200. Nhưng **Boot-specific tiện ích không tự được đảm bảo**. Một biểu hiện dễ nhận biết là **GET /marker.txt** từ **src/main/resources/static** đổi từ 200 thành 404 nếu app không tự cấu hình resource handler.

**Không kết luận @EnableWebMvc tắt toàn bộ Spring Boot**: embedded server, actuator, Jackson hoặc Spring Security còn có auto-configurations riêng.

### 4.3. Customization đúng mức

Muốn thêm interceptor, CORS, formatters, converters, view controllers hoặc resource handlers, ưu tiên:

~~~java
@Configuration(proxyBeanMethods = false)
public class WebConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Register application-specific interceptors.
    }
}
~~~

Snippet cần imports. **Không thêm @EnableWebMvc** nếu muốn giữ các mặc định Boot. Khi chỉ đổi đường dẫn static hoặc content-negotiation behavior được Boot expose bằng property, ưu tiên properties trước.

### 4.4. WebMvcRegistrations

Khi cần thay **RequestMappingHandlerMapping, RequestMappingHandlerAdapter hoặc ExceptionHandlerExceptionResolver** nhưng vẫn muốn giữ Boot MVC customizations, có thể dùng **WebMvcRegistrations**. Đây là extension point sâu hơn WebMvcConfigurer. Những custom instances vẫn có initialization/configuration của Spring MVC, vì thế phải test ordering, argument resolvers, interceptors, exception handling và security.

### 4.5. Khi nào thật sự dùng @EnableWebMvc?

Khi **cố ý tiếp quản toàn bộ MVC web configuration**, đã có test đảm bảo những features trước đây do Boot bổ sung được tái cấu hình hoặc không còn cần. Không thêm annotation chỉ vì nghĩ nó bắt buộc để đăng ký controller trong Spring Boot.

## 5. WebFluxAutoConfiguration và @EnableWebFlux

### 5.1. Bản chất điều kiện

Trong Spring Boot 3.3, **WebFluxAutoConfiguration** hướng tới **REACTIVE** web application và có condition liên quan **WebFluxConfigurationSupport**. Annotation **@EnableWebFlux** import **DelegatingWebFluxConfiguration**, một subclass của WebFluxConfigurationSupport. Do đó WebFluxAutoConfiguration không còn match điều kiện MissingBean tương ứng.

Hai lý do **khác nhau** có thể cùng khiến WebFluxAutoConfiguration negative:
- app không phải reactive web application (có cả web và webflux starters nên Boot chọn MVC);
- app là reactive nhưng đã có WebFluxConfigurationSupport do @EnableWebFlux.

**Luôn đọc OnWebApplicationCondition và OnBeanCondition để biết nguyên nhân thật**.

### 5.2. Những Boot WebFlux defaults có thể mất

Boot bổ sung vào Spring WebFlux defaults:
- HttpMessageReader/HttpMessageWriter codec configuration;
- static resources, WebJars và welcome page integration;
- formatters, CodecCustomizer, WebFlux properties;
- các phần error-handling/resources customization theo từng Boot auto-configuration.

Khi @EnableWebFlux back off WebFluxAutoConfiguration, WebFlux framework core vẫn có **DispatcherHandler và @RestController**, nhưng Boot resource/codec customizations có thể bị mất. Test JSON, static, CORS, errors, content-types và security thay vì chỉ xem ứng dụng có khởi động.

### 5.3. Dùng WebFluxConfigurer

~~~java
@Configuration(proxyBeanMethods = false)
public class ReactiveWebConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://docs.example.test")
                .allowedMethods("GET");
    }
}
~~~

Đây là snippet; có file đầy đủ ở project WebFlux. **Không thêm @EnableWebFlux** nếu chỉ muốn CORS/formatters. Khi cần custom codecs, xem **configureHttpMessageCodecs** hoặc **CodecCustomizer**; khi cần custom HttpHandler builder, Spring Boot có **WebHttpHandlerBuilderCustomizer**. Không dùng reactive handler để che blocking JDBC trên Netty event loop.

### 5.4. Security stack liên quan

MVC Servlet dùng **SecurityFilterChain** và Servlet Filter, còn reactive WebFlux dùng **SecurityWebFilterChain** và WebFilter. Đổi web application type có thể ảnh hưởng authentication/authorization/CSRF/Actuator. @EnableWebMvc/@EnableWebFlux không tự chuyển đổi security rules. Sau mỗi migration phải test các route bảo vệ và CORS preflight.

## 6. Đọc Conditions Evaluation Report đúng cách

### 6.1. In report khi startup

~~~bash
java -jar target/application.jar --debug
~~~

Đường dẫn application.jar là ví dụ. Spring Boot có thể in **CONDITIONS EVALUATION REPORT** ở startup, gồm **Positive matches**, **Negative matches**, exclusions/unconditional classes tùy phiên bản.

Tìm các entries:
- WebMvcAutoConfiguration hoặc WebFluxAutoConfiguration;
- DispatcherServletAutoConfiguration;
- ServletWebServerFactoryAutoConfiguration / ReactiveWebServerFactoryAutoConfiguration;
- JacksonAutoConfiguration / HttpMessageConvertersAutoConfiguration;
- ErrorMvcAutoConfiguration / ErrorWebFluxAutoConfiguration.

**Negative match không mặc định là lỗi.** Khi app là Servlet, WebFluxAutoConfiguration negative vì không phải reactive application là điều bình thường.

### 6.2. Actuator /actuator/conditions

Trong local lab có starter-actuator:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,conditions,beans,mappings"
~~~

Kiểm tra:

~~~bash
curl -i http://localhost:8080/actuator/conditions
curl -i http://localhost:8080/actuator/beans
curl -i http://localhost:8080/actuator/mappings
~~~

Conditions endpoint của Spring Boot 3.3 trả các phần như:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {},
      "negativeMatches": {},
      "unconditionalClasses": []
    }
  }
}
~~~

**JSON trên chỉ minh họa shape**, report thực có keys theo configuration class/method và condition messages; có thể có nested contexts/parentId.

**Bảo mật:** conditions, beans, mappings có thể tiết lộ class names, bean names, route structures và internal configuration. Chỉ expose ở lab hoặc management network có auth; không mở public endpoints trong production chỉ để debug.

### 6.3. Diễn giải một negative match

~~~text
WebMvcAutoConfiguration:
  OnBeanCondition for @ConditionalOnMissingBean
  WebMvcConfigurationSupport was not met
  because DelegatingWebMvcConfiguration is already defined.
~~~

Đây là **message dạng minh họa**, không phải output cố định. Nó cho biết user/configuration đã cung cấp MVC infrastructure nên Boot không tạo phần MVC auto-configuration tương ứng. Tìm @EnableWebMvc hoặc một class extends WebMvcConfigurationSupport.

### 6.4. Positive match không đảm bảo mọi bean đã tạo

Một class-level positive match không có nghĩa mọi @Bean method bên trong cũng match. Cần xem method-level outcomes, bean inventory và thực tế HTTP. Mappings có thể biến mất vì @Profile, component scan boundary, type mismatch, security, route conflicts hoặc resource path, không phải chỉ vì @Enable.

### 6.5. Đọc bằng API trong test

Boot API **ConditionEvaluationReport.get(context.getBeanFactory())** cho phép tìm **getConditionAndOutcomesBySource()**. Những outcomes có **isFullMatch()** để kiểm tra một source được đánh giá match đầy đủ không. Điều này hữu ích để biến giả thuyết “Bean A làm condition B back off” thành regression test.

## 7. Ma trận thay đổi và dấu hiệu

| Hành động | Kết quả điển hình | Bằng chứng quan trọng |
| --- | --- | --- |
| Thêm @Bean đúng interface có MissingBean | Default bean method back off | OnBeanCondition và bean count. |
| Thêm @Bean cùng name với default non-conditional | Có thể name conflict | BeanDefinitionOverrideException. |
| Hai beans cùng type không qualifier | Injection ambiguity | NoUniqueBeanDefinitionException. |
| Thêm WebMvcConfigurer | Boot MVC auto-config thường vẫn match | Static/mappings/interceptors. |
| Thêm @EnableWebMvc | WebMvcAutoConfiguration back off | WebMvcConfigurationSupport bean. |
| Extends WebMvcConfigurationSupport | Có thể back off tương tự | OnBeanCondition. |
| Thêm WebFluxConfigurer | Boot WebFlux auto-config thường vẫn match | Codec/static/CORS. |
| Thêm @EnableWebFlux | WebFluxAutoConfiguration back off ở REACTIVE app | WebFluxConfigurationSupport bean. |
| Thêm starter-webflux vào MVC | Boot mặc định vẫn SERVLET/MVC | Context type và DispatcherServlet. |
| Ép web-application-type=reactive | Reactive context được chọn | DispatcherHandler/Netty/security stack. |
| Exclude auto-config class | Cả class bị loại có chủ đích | Exclusions/report. |
| Nâng Boot version | Điều kiện/API/defaults có thể khác | Diff report, dependency tree, HTTP tests. |

## 8. Project MVC: conditional user bean và @EnableWebMvc

Project A minh họa hai loại backoff **độc lập**:
1. **GreetingService** user bean làm default bean của custom GreetingAutoConfiguration back off.
2. **@EnableWebMvc** làm WebMvcAutoConfiguration back off, khiến Boot static resource mapping không còn theo mặc định. **WebMvcConfigurer không @Enable** vẫn giữ Boot defaults.

### 8.1. Cây project

~~~text
mvc-conditions-lab/
  pom.xml
  src/main/java/com/example/mvcconditions/
    MvcConditionsApplication.java
    GreetingService.java
    GreetingController.java
    CustomGreetingConfiguration.java
    MvcExtensionConfiguration.java
    ManualMvcConfiguration.java
  src/main/java/com/example/mvcconditions/autoconfig/
    GreetingAutoConfiguration.java
  src/main/resources/
    application.yml
    static/marker.txt
    META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports
  src/test/java/com/example/mvcconditions/
    MvcDefaultHttpTest.java
    MvcCustomHttpTest.java
    MvcManualHttpTest.java
~~~

### 8.2. pom.xml

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
    <artifactId>mvc-conditions-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

### 8.3. MvcConditionsApplication.java

~~~java
package com.example.mvcconditions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcConditionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcConditionsApplication.class, args);
    }
}
~~~

### 8.4. GreetingService.java

~~~java
package com.example.mvcconditions;

@FunctionalInterface
public interface GreetingService {
    String greet(String name);
}
~~~

### 8.5. GreetingAutoConfiguration.java

~~~java
package com.example.mvcconditions.autoconfig;

import com.example.mvcconditions.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService defaultGreetingService() {
        return name -> "default:" + name;
    }
}
~~~

**Quan trọng:** register auto-configuration qua file chính xác:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.mvcconditions.autoconfig.GreetingAutoConfiguration
~~~

Nếu thiếu/sai file này, user app không có GreetingService default và injection có thể fail. Tên fully qualified class phải khớp. Trong Boot 3.3 không dùng cách cũ đăng ký qua spring.factories cho auto-configuration này.

### 8.6. CustomGreetingConfiguration.java

~~~java
package com.example.mvcconditions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class CustomGreetingConfiguration {

    @Bean
    public GreetingService greetingService() {
        return name -> "custom:" + name;
    }
}
~~~

User bean trả đúng type GreetingService và có tên khác default bean. Khi active profile custom, defaultGreetingService không được tạo vì @ConditionalOnMissingBean. MVC auto-configuration không bị ảnh hưởng bởi type này.

### 8.7. GreetingController.java

~~~java
package com.example.mvcconditions;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/api/greet")
    public Map<String, String> greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return Map.of("value", service.greet(name));
    }
}
~~~

### 8.8. MvcExtensionConfiguration.java

~~~java
package com.example.mvcconditions;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
@Profile("mvc-configurer")
public class MvcExtensionConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler) {
                response.addHeader("X-Demo-Configurer", "active");
                return true;
            }
        }).addPathPatterns("/api/**");
    }
}
~~~

Đây là **extension**, không có @EnableWebMvc. Nó thêm interceptor header cho API, trong khi Boot static resources vẫn được tự phục vụ.

### 8.9. ManualMvcConfiguration.java

~~~java
package com.example.mvcconditions;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
@Profile("mvc-manual")
@EnableWebMvc
public class ManualMvcConfiguration implements WebMvcConfigurer {
    // Cố ý không đăng ký static resource handler trong mode này.
}
~~~

Khi active profile mvc-manual, @EnableWebMvc import DelegatingWebMvcConfiguration; Boot WebMvcAutoConfiguration sẽ không match condition MissingBean(WebMvcConfigurationSupport). Controller vẫn có thể chạy, nhưng /marker.txt sẽ trả 404 vì Boot static resource mapping không được đăng ký trong demo này.

### 8.10. application.yml

~~~yaml
spring:
  application:
    name: mvc-conditions-lab

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,conditions,beans,mappings"
~~~

### 8.11. static/marker.txt

**src/main/resources/static/marker.txt**:

~~~text
mvc-static-ok
~~~

### 8.12. Chạy ba profiles

~~~bash
mvn clean package

# Default mode.
java -jar target/mvc-conditions-lab-0.0.1-SNAPSHOT.jar

# Dừng process trước rồi chạy extension + custom service.
java -jar target/mvc-conditions-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=custom,mvc-configurer

# Dừng process trước rồi chạy full MVC manual mode.
java -jar target/mvc-conditions-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=mvc-manual --debug
~~~

Không chạy ba JAR cùng lúc trên port 8080. Gọi:

~~~bash
curl -i "http://localhost:8080/api/greet?name=Lan"
curl -i http://localhost:8080/marker.txt
curl -i http://localhost:8080/actuator/conditions
~~~

| Mode | /api/greet | /marker.txt | Điều kiện |
| --- | --- | --- | --- |
| default | {"value":"default:Lan"}, HTTP 200 | 200, mvc-static-ok | WebMvcAutoConfiguration positive |
| custom,mvc-configurer | {"value":"custom:Lan"}, header X-Demo-Configurer: active | 200 | Default GreetingService bean backs off; MVC positive |
| mvc-manual | Controller HTTP 200 | 404 | WebMvcAutoConfiguration negative vì WebMvcConfigurationSupport |

Đây là **kỳ vọng** để người học chạy/test, không phải stdout đã được ghi nhận trên một máy thực.

## 9. HTTP integration tests cho MVC

### 9.1. MvcDefaultHttpTest.java

~~~java
package com.example.mvcconditions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MvcDefaultHttpTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void defaultBeanAndStaticFileWork() {
        var api = http.getForEntity(
                "/api/greet?name=Lan", String.class);
        var file = http.getForEntity(
                "/marker.txt", String.class);

        assertThat(api.getStatusCode().value()).isEqualTo(200);
        assertThat(api.getBody()).contains("default:Lan");
        assertThat(file.getStatusCode().value()).isEqualTo(200);
        assertThat(file.getBody()).contains("mvc-static-ok");
    }

    @Test
    void bootMvcAutoConfigMatches() {
        var report = ConditionEvaluationReport.get(
                context.getBeanFactory());
        var outcomes = report.getConditionAndOutcomesBySource()
                .get(WebMvcAutoConfiguration.class.getName());

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isTrue();
    }
}
~~~

### 9.2. MvcCustomHttpTest.java

~~~java
package com.example.mvcconditions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import com.example.mvcconditions.autoconfig.GreetingAutoConfiguration;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles({"custom", "mvc-configurer"})
class MvcCustomHttpTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void userBeanBacksOffButBootStaticResourcesRemain() {
        var api = http.getForEntity(
                "/api/greet?name=Lan", String.class);
        var file = http.getForEntity(
                "/marker.txt", String.class);

        assertThat(api.getStatusCode().value()).isEqualTo(200);
        assertThat(api.getBody()).contains("custom:Lan");
        assertThat(api.getHeaders()
                .getFirst("X-Demo-Configurer"))
                .isEqualTo("active");
        assertThat(file.getStatusCode().value()).isEqualTo(200);
    }

    @Test
    void customAutoConfigBeanMethodDoesNotMatch() {
        String source = GreetingAutoConfiguration.class.getName()
                + "#defaultGreetingService";
        var outcomes = ConditionEvaluationReport.get(
                context.getBeanFactory())
            .getConditionAndOutcomesBySource().get(source);

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isFalse();
    }
}
~~~

Tùy Boot version, cách in key của method trong report có thể khác; trong Boot 3.3 tên source thường là ClassName#methodName. Mục đích test là phân biệt **bean-level backoff** với tắt cả web auto-config.

### 9.3. MvcManualHttpTest.java

~~~java
package com.example.mvcconditions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("mvc-manual")
class MvcManualHttpTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void frameworkMvcWorksButBootStaticMappingIsAbsent() {
        var api = http.getForEntity(
                "/api/greet?name=Lan", String.class);
        var file = http.getForEntity(
                "/marker.txt", String.class);

        assertThat(api.getStatusCode().value()).isEqualTo(200);
        assertThat(file.getStatusCode().value()).isEqualTo(404);
    }

    @Test
    void webMvcAutoConfigBacksOff() {
        var outcomes = ConditionEvaluationReport.get(
                context.getBeanFactory())
            .getConditionAndOutcomesBySource()
            .get(WebMvcAutoConfiguration.class.getName());

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isFalse();
    }
}
~~~

RANDOM_PORT khiến Tomcat chạy qua HTTP thật; test không chỉ chạy MockMvc. Profiles khác nhau tạo contexts khác nhau, không sửa active profiles khi app đã startup. Chạy:

~~~bash
mvn test
~~~

## 10. Project WebFlux độc lập để kiểm tra @EnableWebFlux

### 10.1. Vì sao phải tách project?

Nếu vô tình thêm starter-web vào project WebFlux, Boot có thể chọn MVC mặc định và condition “not a reactive web application” sẽ che vấn đề @EnableWebFlux. Project B **chỉ có starter-webflux** và dùng reactive controller. Ba chế độ:
- default: Boot WebFlux auto-config phục vụ /marker.txt.
- flux-configurer: CORS extension nhưng không @EnableWebFlux, static vẫn hoạt động.
- flux-manual: @EnableWebFlux, Boot WebFluxAutoConfiguration backs off, controller vẫn xử lý request nhưng static marker 404 nếu không tự đăng ký resource handler.

### 10.2. Cây project

~~~text
webflux-conditions-lab/
  pom.xml
  src/main/java/com/example/fluxconditions/
    FluxConditionsApplication.java
    FluxGreetingController.java
    FluxExtensionConfiguration.java
    ManualFluxConfiguration.java
  src/main/resources/
    application.yml
    static/marker.txt
  src/test/java/com/example/fluxconditions/
    FluxDefaultHttpTest.java
    FluxConfigurerHttpTest.java
    FluxManualHttpTest.java
~~~

### 10.3. pom.xml

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
    <artifactId>webflux-conditions-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

### 10.4. FluxConditionsApplication.java

~~~java
package com.example.fluxconditions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxConditionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxConditionsApplication.class, args);
    }
}
~~~

### 10.5. FluxGreetingController.java

~~~java
package com.example.fluxconditions;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class FluxGreetingController {

    @GetMapping("/api/greet")
    public Mono<Map<String, String>> greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return Mono.just(
                Map.of("value", "reactive:" + name));
    }
}
~~~

Mono.just chỉ giúp minh họa reactive stack, không phải benchmark WebFlux hoặc non-blocking database I/O.

### 10.6. FluxExtensionConfiguration.java

~~~java
package com.example.fluxconditions;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
@Profile("flux-configurer")
public class FluxExtensionConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://docs.example.test")
                .allowedMethods("GET");
    }
}
~~~

### 10.7. ManualFluxConfiguration.java

~~~java
package com.example.fluxconditions;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
@Profile("flux-manual")
@EnableWebFlux
public class ManualFluxConfiguration implements WebFluxConfigurer {
    // Không addResourceHandlers: cố ý bỏ Boot static default.
}
~~~

### 10.8. application.yml, marker.txt

~~~yaml
spring:
  application:
    name: webflux-conditions-lab
server:
  port: 8080
management:
  endpoints:
    web:
      exposure:
        include: "health,conditions,beans,mappings"
~~~

**src/main/resources/static/marker.txt**:

~~~text
flux-static-ok
~~~

### 10.9. Chạy ba modes

~~~bash
mvn clean package

# Default reactive mode.
java -jar target/webflux-conditions-lab-0.0.1-SNAPSHOT.jar

# Dừng process trước rồi chạy flux-configurer.
java -jar target/webflux-conditions-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=flux-configurer

# Dừng process trước rồi chạy manual mode.
java -jar target/webflux-conditions-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=flux-manual --debug
~~~

Không chạy MVC và WebFlux JARs cùng port 8080. Gọi:

~~~bash
curl -i http://localhost:8080/api/greet
curl -i http://localhost:8080/marker.txt
curl -i -H "Origin: https://docs.example.test" \
  http://localhost:8080/api/greet
curl -i http://localhost:8080/actuator/conditions
~~~

Kỳ vọng:
- Default: /api/greet trả {"value":"reactive:Lan"}, /marker.txt 200, Boot WebFluxAutoConfiguration positive.
- flux-configurer: CORS Access-Control-Allow-Origin cho Origin được phép, static marker vẫn 200.
- flux-manual: /api/greet 200, static marker 404; WebFluxAutoConfiguration negative do WebFluxConfigurationSupport.

Request không có Origin không bắt buộc có CORS response header. Để test CORS phải gửi Origin hợp lệ như ví dụ.

## 11. HTTP integration tests cho WebFlux

Dùng **java.net.http.HttpClient của JDK 17** để tránh phụ thuộc vào bean test client setup. @SpringBootTest(RANDOM_PORT) vẫn khởi chạy Reactor Netty HTTP server thực. Điều kiện được kiểm tra bằng ConditionEvaluationReport giống project MVC.

### 11.1. FluxDefaultHttpTest.java

~~~java
package com.example.fluxconditions;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FluxDefaultHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ConfigurableApplicationContext context;

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
                .GET().build();
        return HttpClient.newHttpClient().send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void bootReactiveConfigServesJsonAndStatic() throws Exception {
        var api = get("/api/greet");
        var marker = get("/marker.txt");

        assertThat(api.statusCode()).isEqualTo(200);
        assertThat(api.body()).contains("reactive:Lan");
        assertThat(marker.statusCode()).isEqualTo(200);
        assertThat(marker.body()).contains("flux-static-ok");
    }

    @Test
    void webFluxAutoConfigurationMatches() {
        var outcomes = ConditionEvaluationReport.get(
                context.getBeanFactory())
            .getConditionAndOutcomesBySource()
            .get(WebFluxAutoConfiguration.class.getName());

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isTrue();
    }
}
~~~

### 11.2. FluxConfigurerHttpTest.java

~~~java
package com.example.fluxconditions;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("flux-configurer")
class FluxConfigurerHttpTest {

    @LocalServerPort
    int port;

    @Test
    void corsExtensionKeepsStaticResources() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        var originRequest = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/api/greet"))
                .header("Origin", "https://docs.example.test")
                .GET().build();

        var api = client.send(
                originRequest,
                HttpResponse.BodyHandlers.ofString());

        var marker = client.send(
            HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/marker.txt"))
                .GET().build(),
            HttpResponse.BodyHandlers.ofString());

        assertThat(api.statusCode()).isEqualTo(200);
        assertThat(api.headers()
                .firstValue("Access-Control-Allow-Origin"))
                .contains("https://docs.example.test");
        assertThat(marker.statusCode()).isEqualTo(200);
    }
}
~~~

### 11.3. FluxManualHttpTest.java

~~~java
package com.example.fluxconditions;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("flux-manual")
class FluxManualHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ConfigurableApplicationContext context;

    private int status(String path) throws Exception {
        var request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
                .GET().build();
        var response = HttpClient.newHttpClient().send(
                request, HttpResponse.BodyHandlers.discarding());
        return response.statusCode();
    }

    @Test
    void manualModeWorksButBootStaticMappingIsAbsent()
            throws Exception {
        assertThat(status("/api/greet")).isEqualTo(200);
        assertThat(status("/marker.txt")).isEqualTo(404);
    }

    @Test
    void webFluxAutoConfigurationBacksOff() {
        var outcomes = ConditionEvaluationReport.get(
                context.getBeanFactory())
            .getConditionAndOutcomesBySource()
            .get(WebFluxAutoConfiguration.class.getName());

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isFalse();
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Hai Spring Boot projects có POM độc lập**, vì thế tests MVC và WebFlux kiểm tra hai web stacks riêng, không dựa vào một classpath trộn để suy đoán. Các assertions phản ánh điều kiện Spring Boot 3.3; khi upgrade, phải đọc report và chạy tests thật.

## 12. Khi thêm bean vẫn cần lưu ý những điều gì?

### 12.1. Return type của @Bean

Nếu condition kiểm tra một interface mà @Bean method chỉ khai báo return type **Object**, Spring có thể không nhận ra type thật ở thời điểm condition evaluation:

~~~java
@Bean
Object myService() {
    return new MyServiceImpl();
}
~~~

Đây là snippet vì chưa có MyServiceImpl. Nên khai báo return type phù hợp với contract:

~~~java
@Bean
MyService myService() {
    return new MyServiceImpl();
}
~~~

Condition không phải lúc nào cũng tạo mọi bean trước để xác định runtime class; metadata và bean definitions rất quan trọng.

### 12.2. @Primary/@Qualifier có giới hạn

@Primary giúp giải quyết candidate ưu tiên trong injection, không tự bỏ những bean khác khỏi context. @Qualifier giúp xác định bean. Nếu auto-config dùng @ConditionalOnSingleCandidate, việc có @Primary có thể ảnh hưởng outcome; phải đọc condition/report của **đúng class**.

### 12.3. Thêm SecurityFilterChain

Trong MVC Servlet app, thêm một custom **SecurityFilterChain** có thể khiến default security chain back off. Đây là customization có rủi ro authorization/CSRF nếu bạn không thiết lập đầy đủ rules. Với reactive app cần xem **SecurityWebFilterChain**. Không suy luận từ việc custom MVC web config rằng authentication vẫn y nguyên; phải test route/Actuator access.

### 12.4. MessageConverters, codecs và error handling

Thêm HttpMessageConverter hoặc CodecCustomizer có thể làm thay Accept/Content-Type behavior, tạo **406/415**, JSON không giống trước hoặc custom error body. Một bean ErrorAttributes hoặc ErrorWebExceptionHandler có thể can thiệp error representation. Muốn debug, đọc condition report của các auto-configurations liên quan và thực hiện HTTP tests; không đổ mọi lỗi lên @EnableWebMvc.

### 12.5. Không thay auto-config bằng broad exclusions

~~~java
@SpringBootApplication(
    exclude = SomeAutoConfiguration.class)
~~~

Đây là snippet minh họa; **SomeAutoConfiguration** chưa định nghĩa. Exclusion có thể cần thiết trong kiến trúc đặc biệt, nhưng sẽ khiến **cả class** bị loại; phải xác định những beans/features bạn cần thay thế. Đừng exclude chỉ vì một negative match vốn hoàn toàn bình thường.

## 13. Quy trình gỡ lỗi/upgrade có thể lặp lại

### Bước 1 — Chụp nền

Ghi Java version, Spring Boot/Framework versions, active profiles, properties, dependency tree, Servlet vs Reactive context type. Chạy app hiện tại và lưu request/response cho:
- một JSON endpoint;
- một static file trong classpath;
- CORS preflight;
- validation và error handling;
- security-protected endpoint;
- /actuator/health.

### Bước 2 — Thêm đúng một thay đổi

Chỉ thêm custom @Bean, chỉ thêm WebMvcConfigurer, hoặc chỉ thêm @EnableWebMvc/@EnableWebFlux. Nếu vừa thay dependencies, vừa upgrade Boot, vừa thêm bean và vừa thay security thì khó xác định root cause.

### Bước 3 — So sánh condition report

Tìm entry chuyển positive → negative hoặc bean method backoff. Xác định lý do chính xác:
- OnClassCondition;
- OnWebApplicationCondition;
- OnBeanCondition;
- OnPropertyCondition;
- explicitly excluded auto-configuration.

Nếu negative match do “not a reactive web application”, đừng chữa bằng cách thêm @EnableWebFlux; trước tiên xác định web application type và starters.

### Bước 4 — So sánh beans/mappings

Xem bean type/name/aliases, handler mapping, resource handler, Jackson/codec, filters, error mappings. **/actuator/beans/mappings phải được bảo vệ**. Một condition class match chưa bảo đảm các method-level beans cũng được tạo.

### Bước 5 — Chạy HTTP regression tests

Test bằng RANDOM_PORT, WebTestClient khi phù hợp, ngoài ra kiểm tra:
- HTTP 200/400/404/405/406/415;
- static resource và index page;
- Accept/Content-Type negotiation;
- CORS Origin và OPTIONS;
- security/login/CSRF/Actuator;
- formatter/date/time conversion;
- error JSON và validation;
- reactive streaming nếu stack dùng WebFlux.

### Bước 6 — Sửa nhỏ nhất, khóa regression

Thông thường bỏ @EnableWebMvc/@EnableWebFlux nếu không cần takeover, dùng WebMvcConfigurer/WebFluxConfigurer hoặc properties; sửa @Bean return type, qualifier/condition, hoặc dùng extension point chuyên biệt. Thêm tests chứng minh root cause đã được khắc phục. Đối với nâng cấp framework, đọc release notes/migration guide của version mục tiêu.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| Static /css/app.css 404 sau @EnableWebMvc | Boot MVC static auto-mapping không còn | WebMvcAutoConfiguration negative, chuyển WebMvcConfigurer. |
| /marker.txt 404 trong WebFlux sau @EnableWebFlux | Boot reactive resource auto-mapping không còn | WebFluxAutoConfiguration negative, dùng WebFluxConfigurer. |
| MVC still works dù @EnableWebMvc | Spring Framework MVC infrastructure vẫn chạy | Phân biệt core MVC với Boot additions. |
| Custom bean không thay default | Type/profile hoặc registration order không đúng | OnBeanCondition, method return type và active profiles. |
| Trùng bean name gây startup fail | BeanDefinitionOverrideException | Đổi tên/conditional thay vì bật overriding mù quáng. |
| Hai beans cùng interface gây ambiguity | NoUniqueBeanDefinitionException | @Qualifier/@Primary hoặc sửa conditions. |
| WebFluxAutoConfiguration not reactive | Boot đang chọn SERVLET | Dependency tree và web application type. |
| Thêm starter-webflux nhưng vẫn Tomcat | MVC precedence | Chỉ dùng WebClient hoặc tách reactive project. |
| @EnableWebFlux không chuyển server | Annotation điều khiển framework web config, không phải Boot web type | Kiểm tra context type và lựa chọn stack. |
| CORS OPTIONS fail | Configurer sai stack hoặc Security intercept | CORS registry, filter chain, preflight. |
| Error JSON hoặc converters đổi | Backoff/codec/custom converter | Conditions, mappings, Accept/Content-Type. |
| /actuator/conditions 404 | Chưa thêm Actuator hoặc chưa expose | starter-actuator và exposure include. |
| /actuator/conditions 401/403 | Endpoint được bảo vệ | Dùng quyền hợp lệ; không public hóa. |
| --debug có nhiều negative matches | Negative match bình thường khi không cần feature | Đọc lý do từng entry. |
| AutoConfiguration.imports không được nhận | Sai path/name/class | Kiểm tra resource trong JAR. |
| Static works ở test nhưng fail ở JAR | Resource file packaging/location | Kiểm tra JAR contents, classpath. |
| Tests fail theo thứ tự khi dùng profiles | Shared context/mutable state hoặc profile collision | Tách contexts, tắt parallel khi cần. |
| Nâng Boot gây drift | Conditions/properties/defaults đổi theo version | Diff report và HTTP contract. |

## 15. Bài tập thực hành

### Bài 1 — User bean backoff
Chạy MVC project default và profile custom. So /actuator/conditions cho GreetingAutoConfiguration#defaultGreetingService; giải thích vì sao default method negative nhưng WebMvcAutoConfiguration vẫn positive.

### Bài 2 — Mở rộng MVC giữ Boot defaults
Bật mvc-configurer, xác nhận header X-Demo-Configurer và /marker.txt HTTP 200. Thêm một formatter/CORS mapping mà không có @EnableWebMvc.

### Bài 3 — MVC takeover
Bật mvc-manual, quan sát /api/greet 200, /marker.txt 404. Tìm WebMvcConfigurationSupport trong condition message. Bỏ @EnableWebMvc và chạy lại.

### Bài 4 — WebFlux CORS
Bật flux-configurer; gửi Origin header và kiểm tra Access-Control-Allow-Origin; static marker vẫn 200. So conditions.

### Bài 5 — WebFlux takeover
Bật flux-manual; xác nhận controller vẫn hoạt động nhưng static mapping mất. Nếu muốn full-control, tự đăng ký resource handler rồi so phần nào Boot không còn tự cung cấp.

### Bài 6 — Hai starters
Thêm starter-webflux vào MVC app chỉ để dùng WebClient; xác minh vẫn SERVLET. Giải thích vì sao @EnableWebFlux không phải cách chuyển toàn service sang reactive.

### Bài 7 — Duplicate bean
Bỏ @ConditionalOnMissingBean khỏi demo auto config trong một bản sao lab rồi bật profile custom. Quan sát lỗi injection ambiguity. Sau đó thử trùng bean name và phân biệt hai lỗi.

### Bài 8 — Upgrade
Nâng một Spring Boot version trong môi trường được phép, diff ConditionEvaluationReport, bean list và HTTP responses. Lập bảng: condition → bean/mapping → runtime effect → fix.

## 16. Checklist trước khi merge

- [ ] Đã xác định chính xác Servlet MVC hay Reactive WebFlux.
- [ ] Có dependency tree, Java/Boot/Framework version, active profiles.
- [ ] Đã xem --debug hoặc ConditionEvaluationReport.
- [ ] Biết điều kiện không match là class-level hay method-level.
- [ ] Đã rà @EnableWebMvc, @EnableWebFlux, WebMvcConfigurationSupport và WebFluxConfigurationSupport.
- [ ] Đã rà @Bean types, names, @ConditionalOnMissingBean, @Primary, @Qualifier.
- [ ] Không bật bean overriding toàn app để che lỗi.
- [ ] Ưu tiên WebMvcConfigurer/WebFluxConfigurer khi chỉ cần mở rộng.
- [ ] Xác minh static resources, index.html và WebJars nếu dùng.
- [ ] HTTP conversions, JSON codecs, CORS, error handling được test.
- [ ] Security/Actuator access không bị thay ngoài chủ đích.
- [ ] Có HTTP integration tests qua RANDOM_PORT.
- [ ] /actuator/conditions, beans, mappings không public trên Internet.
- [ ] Có regression tests trước và sau Boot upgrade.
- [ ] Không đổi nhiều biến cùng lúc khi gỡ lỗi.
- [ ] Có kế hoạch rollback nếu web stack/configuration đổi lớn.

## 17. Câu hỏi tự kiểm tra

**1. Có phải @EnableAutoConfiguration luôn tạo mọi defaults?** Không, mỗi class và method có conditions.

**2. User bean có tắt hết Spring Boot không?** Không, thường chỉ phần có MissingBean liên quan back off.

**3. WebMvcConfigurer giống @EnableWebMvc?** Không, một cái mở rộng, một cái nhận quyền MVC framework configuration.

**4. @EnableWebMvc có làm Jackson/Actuator/Security toàn bộ biến mất?** Không, những auto-configurations khác có điều kiện riêng.

**5. @EnableWebFlux có làm MVC app tự thành Netty server?** Không, Boot web type được quyết định khác.

**6. Hai starters trong Boot 3.3 chọn gì mặc định?** MVC/Servlet.

**7. @ConditionalOnMissingBean phụ thuộc bean name hay type?** Tùy annotation attributes; nhiều điều kiện dùng type.

**8. Khi nào dùng WebMvcRegistrations?** Khi cần thay core MVC components nhưng vẫn giữ Boot customizations.

**9. Khi nào dùng WebHttpHandlerBuilderCustomizer?** Khi cần tùy chỉnh HttpHandler builder của Boot WebFlux.

**10. Đọc condition report thế nào?** Startup --debug, /actuator/conditions được bảo vệ hoặc API trong test.

**11. Positive match có đảm bảo static file hoạt động?** Không; cần kiểm tra resource handler, file location, security và HTTP thực.

**12. Tại sao static 404 sau @EnableWebMvc?** Boot WebMvcAutoConfiguration có thể back off, còn framework MVC không tự thay thế mọi Boot static mapping.

## 18. Tài liệu tham khảo

1. [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): cơ chế backoff và conditions report.
2. [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): WebMvcAutoConfiguration, WebMvcConfigurer, @EnableWebMvc, WebMvcRegistrations.
3. [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): WebFluxAutoConfiguration, WebFluxConfigurer, @EnableWebFlux, WebHttpHandlerBuilderCustomizer và MVC precedence.
4. [Spring Boot 3.3 — WebMvcAutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html): @ConditionalOnWebApplication/@ConditionalOnClass/@ConditionalOnMissingBean.
5. [Spring Boot 3.3 — WebFluxAutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html): reactive conditions và WebFluxConfigurationSupport.
6. [Spring Boot 3.3 — Conditions Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): positiveMatches/negativeMatches.
7. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): exposure và bảo mật.
8. [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): web type, RANDOM_PORT.
9. [Spring Framework 6.1 — MVC Config](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-config.html): MVC infrastructure và extension points.
10. [Spring Framework 6.1 — WebFlux Config](https://docs.spring.io/spring-framework/reference/6.1/web/webflux/config.html): WebFlux configuration và resource handlers.

**Kết luận:** Khi thêm user bean hoặc @EnableWebMvc/@EnableWebFlux, hãy xác định **web application type**, đọc **ConditionEvaluationReport** và chỉ ra **điều kiện nào không match**, rồi kiểm chứng **bean/mapping/HTTP response** thật. Một bean cùng type có thể làm một default bean back off, còn @EnableWebMvc/@EnableWebFlux tiếp quản phần web framework configuration và có thể làm mất Boot-specific defaults. Với nhu cầu tùy chỉnh thông thường, ưu tiên **WebMvcConfigurer/WebFluxConfigurer không có @Enable**, dùng properties/extension points phù hợp và khóa regression bằng test HTTP cùng condition outcomes.