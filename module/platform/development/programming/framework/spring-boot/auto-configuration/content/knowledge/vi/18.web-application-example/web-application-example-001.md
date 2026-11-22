# Lần theo điều kiện servlet của WebMvcAutoConfiguration

## 1. Mục tiêu: hiểu vì sao Spring Boot bật hoặc bỏ qua MVC auto-configuration

Trong một ứng dụng Spring Boot, có thể thấy các bean như `DispatcherServlet`, `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, message converters và resource handlers xuất hiện mà không khai báo từng bean. Phần lớn hạ tầng Spring MVC mặc định được cấu hình bởi:

~~~java
org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration
~~~

Để hiểu khi nào lớp này được áp dụng, hãy lần theo các condition đặt ngay trên class. Trong Spring Boot 3.3.x, có ba cổng chính:

1. Ứng dụng phải là **servlet-based web application**.
2. Runtime classpath phải có đủ các class của Servlet API và Spring MVC.
3. Chưa có bean kiểu `WebMvcConfigurationSupport` để Spring Boot có thể nhường quyền cấu hình MVC cho ứng dụng.

Các điều kiện ở cấp class kết hợp theo logic **AND**: tất cả phải khớp thì auto-configuration mới được áp dụng. Chỉ cần một điều kiện không khớp, phần cấu hình MVC mặc định của class này sẽ không được đăng ký.

Bài dùng **Spring Boot 3.3.13, Java 17+** làm phiên bản tham chiếu. Nếu dự án chạy phiên bản khác, trước hết xác nhận version thực tế và đọc source/Javadoc của đúng release; package, dependency và annotation có thể thay đổi giữa các major version.

## 2. Tìm đúng class trong đúng artifact

Với Spring Boot 3.3.x, class nằm trong package:

~~~text
org.springframework.boot.autoconfigure.web.servlet
~~~

Artifact chứa class là:

~~~text
spring-boot-autoconfigure-3.3.13.jar
~~~

Có thể xác nhận bằng Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-autoconfigure
~~~

Sau đó tìm class trong JAR:

~~~bash
jar tf path/to/spring-boot-autoconfigure-3.3.13.jar | grep WebMvcAutoConfiguration
~~~

Kết quả cần có entry tương ứng:

~~~text
org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.class
~~~

Trong Spring Boot 3.x, danh sách auto-configuration được công bố qua resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đọc resource trong JAR:

~~~bash
unzip -p path/to/spring-boot-autoconfigure-3.3.13.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports | grep WebMvcAutoConfiguration
~~~

Dòng tương ứng là tên đầy đủ:

~~~text
org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration
~~~

Đây là bước xác nhận class được khai báo là auto-configuration candidate. Sau đó vẫn cần đọc condition để biết candidate có thực sự được áp dụng trong ứng dụng hiện tại không.

**Đừng dùng package của Spring Boot 4 để tìm class Boot 3.** Boot 4 đã tái cấu trúc một số module/package; với Boot 3.3.x, tên đầy đủ vẫn là `org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration`.

## 3. Đọc các annotation trên WebMvcAutoConfiguration

Phần quan trọng nhất của class trong Spring Boot 3.3.x có dạng:

~~~java
@AutoConfiguration(after = {
        DispatcherServletAutoConfiguration.class,
        TaskExecutionAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
@ConditionalOnWebApplication(type = Type.SERVLET)
@ConditionalOnClass({
        Servlet.class,
        DispatcherServlet.class,
        WebMvcConfigurer.class
})
@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)
@AutoConfigureOrder(Ordered.HIGHEST_PRECEDENCE + 10)
public class WebMvcAutoConfiguration {
    // Các bean và nested configuration của Spring MVC.
}
~~~

Đây là phần khai báo trọng tâm được rút gọn để học condition; source của đúng patch version có thể còn import/runtime hints hoặc chi tiết khác.

| Annotation | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| `@ConditionalOnWebApplication(type = SERVLET)` | Chỉ áp dụng trong servlet web application | Context hiện tại có phải servlet web application không? |
| `@ConditionalOnClass(...)` | Chỉ áp dụng khi các class cần thiết có trên runtime classpath | Servlet API và Spring MVC có mặt không? |
| `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` | Nhường chỗ nếu ứng dụng đã cung cấp hạ tầng MVC cấp thấp | Có cấu hình MVC thay thế đã đăng ký không? |
| `@AutoConfiguration(after = ...)` | Sắp xếp thời điểm xử lý tương đối với auto-configuration khác | Các cấu hình prerequisite cần được xử lý trước lớp này là gì? |
| `@AutoConfigureOrder(...)` | Đặt mức ưu tiên chung trong thứ tự auto-configuration | Thứ tự ưu tiên tổng quát của candidate này là gì? |

Hai annotation cuối là **ordering metadata**, không phải condition bật/tắt. Không được hiểu `after = DispatcherServletAutoConfiguration.class` là điều kiện bảo đảm DispatcherServlet tồn tại; nó chỉ khai báo quan hệ xử lý giữa các auto-configuration.

## 4. Cổng thứ nhất: @ConditionalOnWebApplication(type = SERVLET)

### 4.1. Ý nghĩa của SERVLET

Spring Boot hỗ trợ nhiều kiểu ứng dụng:

- **SERVLET:** ứng dụng web dựa trên Servlet API, thường dùng Spring MVC.
- **REACTIVE:** ứng dụng web reactive, thường dùng Spring WebFlux.
- **NONE:** ứng dụng không khởi chạy web application context.

`@ConditionalOnWebApplication(type = Type.SERVLET)` chỉ khớp khi context/environment được nhận diện là **servlet web application**. Nó không chỉ kiểm tra xem có một file Servlet API trong classpath hay không.

Về mặt khái niệm, servlet web application được nhận diện thông qua web context/environment phù hợp, chẳng hạn Spring `WebApplicationContext`, session scope hoặc `ConfigurableWebEnvironment`. Ứng dụng Spring Boot chạy embedded Tomcat/Jetty/Undertow thường dùng `ServletWebServerApplicationContext`.

### 4.2. Phân biệt loại ứng dụng với classpath

Hai tình huống có thể cùng chứa Servlet API nhưng khác kết quả:

| Tình huống | Classpath có Servlet API? | Loại context | Condition SERVLET |
| --- | --- | --- | --- |
| Ứng dụng Spring MVC chạy web bình thường | Có | SERVLET | Khớp |
| Ứng dụng có starter-web nhưng ép chạy non-web | Có | NONE | Không khớp |
| Ứng dụng WebFlux thuần | Thường không có Spring MVC DispatcherServlet | REACTIVE | Không khớp |

Có thể ép Spring Boot chạy non-web bằng:

~~~properties
spring.main.web-application-type=none
~~~

Hoặc command line:

~~~bash
java -jar target/app.jar --spring.main.web-application-type=none
~~~

Ngay cả khi dependency `spring-boot-starter-web` vẫn còn trên classpath, condition SERVLET không khớp nếu ứng dụng được cấu hình chạy kiểu NONE.

Với WebFlux thuần, loại ứng dụng là REACTIVE; `WebMvcAutoConfiguration` không phải cấu hình dành cho context đó. Không nên nhầm điều kiện này với `@ConditionalOnClass`: một condition xét **loại context**, condition còn lại xét **sự hiện diện của class**.

### 4.3. Spring Boot xác định WebApplicationType ở đâu?

Khi khởi động, `SpringApplication` suy luận loại ứng dụng từ classpath, trừ khi người dùng cấu hình rõ `spring.main.web-application-type`. Có thể xem kết quả trong code:

~~~java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.SpringApplication;

SpringApplication application =
        new SpringApplication(MyApplication.class);

System.out.println(application.getWebApplicationType());
~~~

Đây là đoạn minh họa có thể đặt trong main trước khi gọi `run`; `MyApplication.class` là class khởi động của dự án. Với ứng dụng web MVC thông thường, kết quả là:

~~~text
SERVLET
~~~

Nếu ứng dụng đặt `spring.main.web-application-type=none`, kết quả tương ứng là:

~~~text
NONE
~~~

Đừng chỉ suy luận loại ứng dụng từ tên starter. Hãy kiểm tra cấu hình thực tế và báo cáo condition khi chạy.

## 5. Cổng thứ hai: @ConditionalOnClass

Khai báo trong Spring Boot 3.3.x:

~~~java
@ConditionalOnClass({
        jakarta.servlet.Servlet.class,
        org.springframework.web.servlet.DispatcherServlet.class,
        org.springframework.web.servlet.config.annotation.WebMvcConfigurer.class
})
~~~

Ba class có vai trò khác nhau:

| Class | Thuộc thư viện | Vì sao cần? |
| --- | --- | --- |
| `jakarta.servlet.Servlet` | Jakarta Servlet API | Có API nền tảng cho servlet web application |
| `org.springframework.web.servlet.DispatcherServlet` | Spring Web MVC | Có front controller xử lý request của Spring MVC |
| `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` | Spring Web MVC | Có API callback để cấu hình MVC |

Điều kiện yêu cầu **đủ cả ba class** trên runtime classpath. Nếu thiếu một class, `WebMvcAutoConfiguration` không được áp dụng.

### 5.1. Starter thường cung cấp các class này

Trong ứng dụng thông thường, dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

kéo Spring Web MVC và Servlet API phù hợp vào dependency graph. Starter cũng thường cung cấp embedded servlet container như Tomcat thông qua dependency mặc định.

Tuy nhiên, không nên kết luận chỉ từ tên dependency. Hãy kiểm tra runtime dependency tree:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework,org.springframework.boot,jakarta.servlet
~~~

Nếu `spring-webmvc` bị exclude hoặc có scope khiến nó không xuất hiện lúc chạy, `DispatcherServlet` và `WebMvcConfigurer` có thể không có trên runtime classpath.

### 5.2. Boot 3 dùng jakarta.servlet, không phải javax.servlet

Spring Boot 3 chuyển sang Jakarta EE namespace. Vì vậy condition của Boot 3 tham chiếu:

~~~java
jakarta.servlet.Servlet.class
~~~

Không được nhầm với namespace của ứng dụng Spring Boot 2 cũ:

~~~java
javax.servlet.Servlet.class
~~~

Một ứng dụng trộn dependency Spring Boot 2/Spring Framework 5 với Jakarta Servlet hoặc Spring Boot 3/Spring Framework 6 với thư viện cũ dùng `javax.servlet` có thể gặp lỗi tương thích. Khi điều tra condition, phải đối chiếu major version và package thực tế trong JAR.

### 5.3. Cách kiểm tra nhanh bằng classpath

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
~~~

Có thể mở JAR để kiểm tra class:

~~~bash
jar tf path/to/spring-webmvc.jar | grep DispatcherServlet
~~~

Với Servlet API, kiểm tra dependency tương ứng và class `jakarta/servlet/Servlet.class`. Nếu class thiếu, hãy sửa dependency/runtime packaging; thêm `@EnableWebMvc` không thể bù cho class bị thiếu.

## 6. Cổng thứ ba: @ConditionalOnMissingBean(WebMvcConfigurationSupport.class)

Đây là condition thể hiện cơ chế **back off** của Spring Boot.

~~~java
@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)
~~~

Ý nghĩa: Boot chỉ áp dụng MVC auto-configuration mặc định nếu context chưa có bean thuộc kiểu `WebMvcConfigurationSupport` (hoặc subtype phù hợp).

### 6.1. Vì sao @EnableWebMvc làm Boot back off?

Spring Framework cung cấp annotation:

~~~java
@EnableWebMvc
~~~

Annotation này import cấu hình MVC của Spring Framework, cụ thể là `DelegatingWebMvcConfiguration`. Lớp này kế thừa `WebMvcConfigurationSupport`.

Vì vậy khi ứng dụng thêm `@EnableWebMvc`, một bean thuộc kiểu `WebMvcConfigurationSupport` được đăng ký. Condition `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` không còn khớp và `WebMvcAutoConfiguration` nhường chỗ.

Kết quả:

- Spring MVC vẫn có thể hoạt động vì cấu hình do `@EnableWebMvc` cung cấp.
- Các tùy chỉnh mặc định riêng của Spring Boot MVC có thể không còn được áp dụng.
- Người phát triển chịu trách nhiệm cấu hình đầy đủ hơn cho MVC.

### 6.2. WebMvcConfigurer không làm Boot back off

Nếu mục tiêu chỉ là thêm interceptor, formatter, CORS mapping, resource handler hoặc view controller, thường chỉ cần khai báo một bean `WebMvcConfigurer`:

~~~java
@Configuration(proxyBeanMethods = false)
public class MyMvcConfiguration implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example");
    }
}
~~~

Class này có kiểu `WebMvcConfigurer`, không phải `WebMvcConfigurationSupport`. Vì vậy condition `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` vẫn khớp; Spring Boot giữ các mặc định MVC và tích hợp thêm callback của bạn.

**Đây là khác biệt cần nhớ:**

| Cấu hình người dùng | Bean liên quan | Boot MVC auto-configuration |
| --- | --- | --- |
| Chỉ khai báo `WebMvcConfigurer` | Một callback configurer | Vẫn được áp dụng |
| Dùng `@EnableWebMvc` | `DelegatingWebMvcConfiguration`, subtype của `WebMvcConfigurationSupport` | Back off |
| Tự khai báo subtype `WebMvcConfigurationSupport` | Bean hỗ trợ MVC cấp thấp | Back off |

Không dùng `@EnableWebMvc` chỉ vì muốn thêm một interceptor. Dùng nó khi thật sự muốn nắm toàn quyền cấu hình MVC và chấp nhận tự quản lý các phần Boot thường cung cấp.

### 6.3. Nếu cần thay các thành phần lõi nhưng vẫn giữ Boot customization

Spring Boot cung cấp `WebMvcRegistrations` để cung cấp các implementation tùy chỉnh cho một số thành phần như:

- `RequestMappingHandlerMapping`
- `RequestMappingHandlerAdapter`
- `ExceptionHandlerExceptionResolver`

Cách này cho phép Boot và Spring MVC tiếp tục thực hiện các bước cấu hình tiếp theo trên thành phần được thay thế. Sau đó có thể tiếp tục dùng `WebMvcConfigurer` cho các callback mở rộng. Không nên tự kế thừa `WebMvcConfigurationSupport` nếu mục tiêu chỉ là thay một vài component.

## 7. Ba condition kết hợp thành một quyết định

Có thể đọc logic của class như sau:

~~~text
WebMvcAutoConfiguration candidate được phát hiện
              |
              v
Có phải servlet web application?
@ConditionalOnWebApplication(SERVLET)
        | false -> bỏ qua
        | true
        v
Có đủ Servlet + DispatcherServlet + WebMvcConfigurer?
@ConditionalOnClass(...)
        | false -> bỏ qua
        | true
        v
Đã có WebMvcConfigurationSupport bean chưa?
@ConditionalOnMissingBean(...)
        | có -> back off
        | chưa có
        v
WebMvcAutoConfiguration được áp dụng
              |
              v
Đăng ký nested MVC configuration và các bean phù hợp
~~~

Đây là sơ đồ logic, không phải cam kết về thứ tự thực thi nội bộ chính xác của mọi condition. Khi Spring Boot xử lý class, các điều kiện ở cấp class đều phải khớp; nếu một điều kiện không khớp, cấu hình này không được áp dụng.

**Đừng gộp ba điều kiện thành một:** có class Servlet trên classpath không chứng minh context là servlet web application; context là servlet không chứng minh Spring MVC có đủ class; có đủ class cũng không có nghĩa Boot sẽ cấu hình mặc định nếu người dùng đã thay thế MVC infrastructure.

## 8. Sau khi ba điều kiện khớp, class làm gì?

Trong Spring Boot 3.3.x, `WebMvcAutoConfiguration` chứa các nested configuration, đáng chú ý là:

- `WebMvcAutoConfigurationAdapter`: triển khai `WebMvcConfigurer`, kết nối các tùy chỉnh MVC của Boot.
- `EnableWebMvcConfiguration`: cấu hình nền dựa trên `DelegatingWebMvcConfiguration` của Spring Framework.

Nested configuration đăng ký `WebMvcProperties` và `WebProperties`, rồi dùng chúng để cấu hình nhiều phần MVC. Tùy bean method và condition riêng, Boot có thể cung cấp:

- `ContentNegotiatingViewResolver` và `BeanNameViewResolver`.
- Static resource handling và WebJars.
- Tích hợp `Converter`, `GenericConverter` và `Formatter`.
- Cấu hình message converters.
- `MessageCodesResolver`.
- Hỗ trợ static welcome page `index.html`.
- `ConfigurableWebBindingInitializer`.
- Một số filter và thành phần MVC theo condition riêng.

Không phải tất cả bean này đều được đăng ký vô điều kiện. Từng bean method có thể có `@ConditionalOnMissingBean`, `@ConditionalOnBean`, `@ConditionalOnProperty` hoặc condition khác. Vì vậy sau khi class-level condition khớp, vẫn phải đọc condition ở bean method nếu một bean cụ thể không xuất hiện.

### 8.1. Phân biệt với DispatcherServletAutoConfiguration

Hai lớp thường bị nhầm:

| Class | Trách nhiệm chính |
| --- | --- |
| `DispatcherServletAutoConfiguration` | Đăng ký `DispatcherServlet` và registration phù hợp cho servlet application |
| `WebMvcAutoConfiguration` | Cấu hình hạ tầng Spring MVC: mappings, adapters, converters, formatters, resources và các thành phần MVC khác |

`WebMvcAutoConfiguration` khai báo `after = DispatcherServletAutoConfiguration.class` để thể hiện thứ tự xử lý tương đối. Điều này không có nghĩa class đầu tiên là một condition bắt buộc thay cho `@ConditionalOnWebApplication` hay `@ConditionalOnClass`.

## 9. Ví dụ chạy được: MVC mặc định và WebMvcConfigurer tùy chỉnh

Ví dụ dùng **Java 17+ và Spring Boot 3.3.13**. Mục tiêu là thấy ứng dụng MVC bình thường vẫn nhận cấu hình mặc định của Boot khi chỉ thêm một `WebMvcConfigurer`.

### 9.1. Cấu trúc

~~~text
webmvc-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── WebMvcTraceApplication.java
    │   │   ├── HelloController.java
    │   │   └── ApiMvcConfiguration.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/demo/
            ├── WebMvcTraceTests.java
            └── NonWebContextTests.java
~~~

### 9.2. pom.xml

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
    <artifactId>webmvc-condition-demo</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 9.3. WebMvcTraceApplication.java

**src/main/java/com/example/demo/WebMvcTraceApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebMvcTraceApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebMvcTraceApplication.class, args);
    }
}
~~~

### 9.4. HelloController.java

**src/main/java/com/example/demo/HelloController.java**

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public String hello() {
        return "Hello MVC";
    }
}
~~~

### 9.5. ApiMvcConfiguration.java

**src/main/java/com/example/demo/ApiMvcConfiguration.java**

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example");
    }
}
~~~

Class chỉ triển khai `WebMvcConfigurer`; không có `@EnableWebMvc` và không kế thừa `WebMvcConfigurationSupport`. Vì thế nó bổ sung CORS mapping mà không làm Boot MVC auto-configuration back off.

### 9.6. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: webmvc-condition-demo
~~~

Không cần đặt `spring.main.web-application-type`; với starter-web, Spring Boot nhận diện đây là ứng dụng servlet bình thường.

### 9.7. Chạy ứng dụng và bật condition report

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Gửi request:

~~~bash
curl http://localhost:8080/api/hello
~~~

Output body:

~~~text
Hello MVC
~~~

Trong log khởi động, tìm `WebMvcAutoConfiguration` ở Condition Evaluation Report. Với ứng dụng này, kỳ vọng các điều kiện cấp class đều khớp:

- Context là servlet web application.
- `jakarta.servlet.Servlet`, `DispatcherServlet` và `WebMvcConfigurer` có trên runtime classpath.
- Chưa có bean `WebMvcConfigurationSupport` do ứng dụng tự khai báo.

Các bean MVC mặc định được Boot cấu hình; `ApiMvcConfiguration` bổ sung CORS.

### 9.8. Test xác nhận hạ tầng MVC được đăng ký

**src/test/java/com/example/demo/WebMvcTraceTests.java**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class WebMvcTraceTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    MockMvc mockMvc;

    @Test
    void servletMvcInfrastructureIsPresent() {
        assertThat(context.getBeanNamesForType(
                WebMvcConfigurationSupport.class)).isNotEmpty();
    }

    @Test
    void controllerWorksWithBootMvcDefaultsAndCustomConfigurer()
            throws Exception {
        mockMvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello MVC"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Kỳ vọng **hai test pass**. Test đầu xác nhận có MVC configuration support; test thứ hai xác nhận endpoint vẫn hoạt động khi ứng dụng có một `WebMvcConfigurer` tùy chỉnh.

## 10. Thử nghiệm làm condition SERVLET không khớp

Classpath của project vẫn có starter-web và các class MVC, nhưng ta ép ứng dụng chạy kiểu NONE.

Có thể chạy:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --spring.main.web-application-type=none"
~~~

Lúc này:

- `@ConditionalOnClass` vẫn có thể khớp vì dependency không bị gỡ khỏi classpath.
- `@ConditionalOnWebApplication(type = SERVLET)` không khớp vì application context được cấu hình non-web.
- `WebMvcAutoConfiguration` không được áp dụng.

Đây là thí nghiệm tốt để chứng minh **có Servlet class không đồng nghĩa với servlet web application**. Controller class vẫn có thể được component scan như bean, nhưng không có MVC web context để dispatch HTTP request.

### Test cho non-web context

**src/test/java/com/example/demo/NonWebContextTests.java**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.main.web-application-type=none")
class NonWebContextTests {

    @Autowired
    ApplicationContext context;

    @Test
    void servletMvcAutoConfigurationDoesNotApply() {
        assertThat(context.getBeanNamesForType(
                WebMvcConfigurationSupport.class)).isEmpty();
    }
}
~~~

Test này giữ nguyên dependency MVC, chỉ đổi loại application context. Kỳ vọng test pass vì không có bean MVC infrastructure từ auto-configuration.

## 11. Thử nghiệm làm condition @ConditionalOnMissingBean không khớp

Trong project ở mục 9, sửa `ApiMvcConfiguration` thành:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
@EnableWebMvc
public class ApiMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example");
    }
}
~~~

Chạy lại với `--debug`:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Lần này:

- Servlet web application condition vẫn có thể khớp.
- Các class Servlet/MVC vẫn hiện diện.
- `@EnableWebMvc` import cấu hình dựa trên `DelegatingWebMvcConfiguration`, là subtype của `WebMvcConfigurationSupport`.
- `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` không khớp.
- `WebMvcAutoConfiguration` back off.

Trong báo cáo điều kiện, tìm `WebMvcAutoConfiguration` ở Negative matches. Lý do sẽ liên quan đến bean `WebMvcConfigurationSupport` đã tồn tại; câu chữ cụ thể phụ thuộc version.

Spring MVC vẫn có thể hoạt động nhờ `@EnableWebMvc`, nhưng các tùy chỉnh Boot MVC không còn được tự động bổ sung theo cách cũ. Đây là hành vi dự kiến của annotation này, không phải lỗi khởi động.

Sau thí nghiệm, bỏ `@EnableWebMvc` để trở lại cách tùy chỉnh được khuyến nghị khi muốn giữ defaults của Boot.

## 12. Đọc Condition Evaluation Report theo ba cổng

Khi chạy với `--debug`, tìm:

~~~text
WebMvcAutoConfiguration
~~~

Có thể gặp các kết quả mang ý nghĩa sau:

| Điều kiện | Positive match khi | Negative match khi |
| --- | --- | --- |
| `@ConditionalOnWebApplication(SERVLET)` | Context là servlet web application | Context là NONE hoặc REACTIVE |
| `@ConditionalOnClass` | Cả ba class yêu cầu đều có trên classpath | Thiếu Servlet API hoặc Spring MVC class |
| `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` | Chưa có bean hỗ trợ MVC thay thế | Đã có bean hỗ trợ MVC, thường do `@EnableWebMvc` |

Ví dụ minh họa ý nghĩa của một negative match:

~~~text
WebMvcAutoConfiguration:
   Did not match:
      - @ConditionalOnMissingBean
        found bean of type WebMvcConfigurationSupport
~~~

Đây là **log giả lập rút gọn**, không phải nguyên văn output được bảo đảm của mọi phiên bản.

Để đọc report chính xác:

1. Tìm đúng tên class `WebMvcAutoConfiguration`.
2. Phân biệt class-level condition với condition trên từng bean method.
3. Xác định condition đầu tiên không khớp và thông điệp giải thích.
4. Đối chiếu với loại context, runtime classpath và bean do ứng dụng đăng ký.
5. Nếu class-level conditions đều khớp nhưng một bean cụ thể không có, tìm method `@Bean` và condition riêng của method đó.
6. Nếu bean được đăng ký nhưng khởi tạo thất bại, đọc stack trace; Condition Evaluation Report không thay thế lỗi constructor/factory method.

Có thể xem endpoint `/actuator/conditions` nếu ứng dụng đã thêm Actuator, expose endpoint và bảo vệ truy cập phù hợp. `--debug` không tự cài Actuator hoặc mở endpoint này.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Có jakarta.servlet.Servlet nhưng WebMvcAutoConfiguration không chạy | Context không phải servlet web application | Kiểm tra `spring.main.web-application-type` và web context |
| Có starter-web nhưng condition class không khớp | Dependency runtime bị exclude, scope sai hoặc version không tương thích | Kiểm tra runtime dependency tree và class trong JAR |
| Dùng Boot 3 nhưng code tìm javax.servlet.Servlet | Nhầm namespace Boot 2 với Jakarta của Boot 3 | Dùng `jakarta.servlet.Servlet` và dependency phù hợp |
| WebMvcAutoConfiguration back off sau khi thêm @EnableWebMvc | DelegatingWebMvcConfiguration là subtype của WebMvcConfigurationSupport | Bỏ @EnableWebMvc nếu chỉ cần customization |
| Thêm WebMvcConfigurer mà nghĩ Boot sẽ back off | Nhầm WebMvcConfigurer với WebMvcConfigurationSupport | Có thể giữ WebMvcConfigurer để mở rộng mặc định Boot |
| Bean DispatcherServlet có nhưng thiếu view resolver hoặc resource handling | DispatcherServletAutoConfiguration và WebMvcAutoConfiguration là hai cấu hình khác nhau | Đọc condition report của từng class |
| Class-level condition khớp nhưng một bean method không xuất hiện | Condition riêng của bean method không khớp | Đọc condition tại method đó |
| Đổi version Boot nhưng source IDE vẫn cũ | Source attachment hoặc dependency runtime chưa cập nhật | Xác nhận dependency tree và mở source JAR đúng version |
| Đưa @EnableWebMvc vào test config làm kết quả khác production | Test đã thay đổi điều kiện back-off | Kiểm tra test configuration và Condition Evaluation Report |

## 14. Checklist lần theo điều kiện servlet

Khi cần giải thích tại sao Spring MVC auto-configuration có hoặc không có trong một ứng dụng:

1. Xác nhận version Spring Boot đang chạy.
2. Tìm đúng artifact chứa `WebMvcAutoConfiguration`.
3. Mở source/Javadoc đúng release, không dùng class cùng tên của major version khác.
4. Đọc `@ConditionalOnWebApplication(type = SERVLET)`.
5. Kiểm tra runtime classpath có `jakarta.servlet.Servlet`, `DispatcherServlet` và `WebMvcConfigurer`.
6. Kiểm tra có bean `WebMvcConfigurationSupport` hay cấu hình `@EnableWebMvc` không.
7. Bật `--debug` và tìm class trong Condition Evaluation Report.
8. Nếu class được áp dụng, tiếp tục đọc condition của bean method cần điều tra.
9. Xác nhận bằng integration test/MockMvc trong servlet context.
10. Thử non-web hoặc `@EnableWebMvc` để hiểu từng nhánh condition.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `@ConditionalOnWebApplication(type = SERVLET)` và `@ConditionalOnClass(Servlet.class)` khác nhau ở điểm nào?  
**Đáp án:** Một condition kiểm tra ứng dụng/context có phải servlet web application không; condition kia kiểm tra class có trên runtime classpath không. Có class Servlet chưa đủ để chứng minh context là servlet web application.

**Câu 2.** Vì sao ứng dụng có `spring-boot-starter-web` nhưng đặt `spring.main.web-application-type=none` thì MVC auto-configuration không chạy?  
**Đáp án:** Classpath condition có thể khớp, nhưng servlet web application condition không khớp vì context được ép thành non-web.

**Câu 3.** Ba class mà `@ConditionalOnClass` của Boot 3.3.x yêu cầu là gì?  
**Đáp án:** `jakarta.servlet.Servlet`, `org.springframework.web.servlet.DispatcherServlet` và `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`.

**Câu 4.** Vì sao `@EnableWebMvc` làm `WebMvcAutoConfiguration` back off?  
**Đáp án:** Nó import `DelegatingWebMvcConfiguration`, một subtype của `WebMvcConfigurationSupport`; condition `@ConditionalOnMissingBean` không còn khớp.

**Câu 5.** Thêm một bean `WebMvcConfigurer` có làm Boot MVC auto-configuration back off không?  
**Đáp án:** Không. WebMvcConfigurer là callback mở rộng, không phải WebMvcConfigurationSupport. Đây là cách thường dùng để giữ mặc định Boot và thêm customization.

**Câu 6.** `after = DispatcherServletAutoConfiguration.class` có phải condition để MVC auto-configuration được bật không?  
**Đáp án:** Không. Đây là metadata sắp xếp thứ tự xử lý auto-configuration; điều kiện bật/tắt nằm ở các annotation `@Conditional...`.

## 16. Tài liệu tham khảo chính thức

- [WebMvcAutoConfiguration — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html)
- [Servlet Web Applications — Spring Boot 3.3 Reference](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [ConditionalOnWebApplication — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html)
- [WebMvcRegistrations — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcRegistrations.html)

**Ghi nhớ:** `WebMvcAutoConfiguration` chỉ áp dụng khi **context là servlet web application**, **Servlet API và Spring MVC class có trên runtime classpath**, và **chưa có WebMvcConfigurationSupport do ứng dụng cung cấp**. `WebMvcConfigurer` giúp mở rộng cấu hình mặc định; `@EnableWebMvc` chuyển quyền cấu hình MVC sang ứng dụng. Đọc ba cổng condition theo đúng version là cách nhanh nhất để hiểu vì sao Spring Boot có hoặc không có hạ tầng MVC.
